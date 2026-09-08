#!/usr/bin/env python3
"""Regressions for the commit-keyed immutable admission snapshot.

Classification: pure/component tests over a temporary Git repository. No Unity
asset, no tracked repository file, no GitHub call, no network and no Docker is
involved: every test builds its own throwaway checkout under ``tempfile`` and
only reads from it.

Contract or gate mapping: regression-only invariants for the scheduler
admission path. These prove performance-shaped behavior (how many Git
processes and committed-contract loads one admission costs) and the safety
boundary that keeps that cheaper path honest. They prove no task acceptance
criterion or completion gate.

What each test would catch if the fix regressed:

* the bulk read must produce byte-identical contracts and hashes to the
  per-task ``git show`` loader it replaces, or every downstream contract-hash
  binding silently changes meaning;
* a malformed individual contract must reject only itself, never the whole
  repository observation;
* the snapshot must be reused only for the identical commit, and a moved HEAD
  must produce a different snapshot rather than stale committed authority;
* the decomposition policy must come from that exact commit even when the
  working-tree copy differs, without buying another Git process;
* the committed-path inventory must be lazy, loaded at most once, and never
  shared across commits;
* the cache must stay bounded so a long-running scheduler cannot accumulate
  obsolete commits;
* loading N committed contracts must cost a bounded number of Git processes
  rather than one per contract;
* production poll planning must consume that bounded snapshot instead of
  silently falling back to one ``git show`` per task; and
* enumeration must preserve the canonical ASCII, bounded task-ID contract.
"""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from collections import Counter
from contextlib import ExitStack
from typing import Any
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.committed_tasks import (  # noqa: E402
    CommittedTaskError,
    load_committed_task,
)
from Pipeline.TaskReviewAgent import polling_orchestrator as polling_module  # noqa: E402
from Pipeline.TaskReviewAgent.source_commit_snapshot import (  # noqa: E402
    SNAPSHOT_CACHE_LIMIT,
    SourceCommitSnapshotError,
    cached_snapshot_commits,
    discard_source_commit_snapshots,
    source_commit_admission_snapshot,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=120.0,
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def contract(task_id: str, **overrides: Any) -> dict[str, Any]:
    value = {
        "schema_version": "2.0",
        "id": task_id,
        "title": f"Snapshot fixture {task_id}",
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "contract_disposition": "active",
        "exclusive_resources": [],
        "depends_on": [],
        "acceptance_criteria": [],
        "completion_gates": [],
    }
    value.update(overrides)
    return value


def make_repository(root: Path, contracts: dict[str, Any]) -> tuple[Path, str]:
    """A throwaway checkout with exactly these committed task contracts."""

    source = root / "source"
    (source / "Tasks").mkdir(parents=True)
    git(source, "init", "-b", "main")
    git(source, "config", "user.name", "Snapshot Fixture")
    git(source, "config", "user.email", "snapshot-fixture@nosafecircle.invalid")
    for task_id, payload in contracts.items():
        text = payload if isinstance(payload, str) else json.dumps(payload, indent=2) + "\n"
        (source / "Tasks" / f"{task_id}.yaml").write_text(text, encoding="utf-8")
    git(source, "add", "Tasks")
    git(source, "commit", "-m", "fixture contracts")
    return source, git(source, "rev-parse", "HEAD")


# An audit hook can never be removed once installed, so exactly one hook is
# installed for the whole module and it counts into whichever Counter is
# currently active. Installing a hook per measurement would leave every earlier
# hook running and silently attribute later Git processes to earlier counters.
_ACTIVE_COUNTS: list[Counter] = []


def _audit(event: str, arguments: tuple[Any, ...]) -> None:
    if event != "subprocess.Popen" or not _ACTIVE_COUNTS:
        return
    executable, command = arguments[:2]
    if isinstance(command, str):
        command = shlex.split(command, posix=False)
    name = Path(str(executable or (command[0] if command else ""))).name.lower()
    if name not in {"git", "git.exe"}:
        return
    commands = _ACTIVE_COUNTS[-1]
    commands["total"] += 1
    for verb in ("show", "cat-file", "ls-tree", "rev-parse", "log", "rev-list"):
        if verb in command:
            commands[verb] += 1
            break


sys.addaudithook(_audit)


def count_git(callable_: Any) -> tuple[Any, Counter]:
    """Run ``callable_`` and count only the Git processes it itself spawns."""

    commands: Counter = Counter()
    _ACTIVE_COUNTS.append(commands)
    try:
        value = callable_()
    finally:
        _ACTIVE_COUNTS.pop()
    return value, commands


def test_bulk_read_matches_the_per_task_loader_exactly() -> None:
    """The snapshot must be the same answer as one git show per task.

    Every committed-contract hash in this pipeline binds admission identity, so
    the bulk read is only safe if its bytes and its ``task_contract_sha256``
    are indistinguishable from the loader it replaces.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-snapshot-equal-") as text:
        contracts = {
            "NSC-701": contract("NSC-701"),
            "NSC-702": contract("NSC-702", exclusive_resources=["repo-file:Assets/A.cs"]),
            "NSC-703": contract("NSC-703", depends_on=["NSC-701"]),
        }
        source, head = make_repository(Path(text), contracts)
        discard_source_commit_snapshots()
        snapshot = source_commit_admission_snapshot(source, head)

        require(snapshot.task_ids == ("NSC-701", "NSC-702", "NSC-703"), str(snapshot.task_ids))
        for task_id in snapshot.task_ids:
            direct = load_committed_task(source, task_id)
            pooled = snapshot.task(task_id)
            require(pooled == direct, f"{task_id}: snapshot contract differs from the direct load")
            require(
                pooled["task_contract_sha256"] == direct["task_contract_sha256"],
                f"{task_id}: contract hash differs from the direct load",
            )
        # An unknown task fails with the loader's own error class, so callers
        # that already handle a missing contract keep handling it.
        try:
            snapshot.task("NSC-799")
        except CommittedTaskError as exc:
            require("missing" in str(exc), str(exc))
        else:
            raise AssertionError("a missing committed contract was not refused")
        discard_source_commit_snapshots()


def test_one_malformed_contract_rejects_only_itself() -> None:
    """A bad contract must not blind the scheduler to every other task.

    The per-task loader raised only for the task it was asked about. A bulk
    read that parsed everything up front would turn one malformed file into a
    repository-wide observation failure and hide every admissible task.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-snapshot-malformed-") as text:
        contracts = {
            "NSC-711": contract("NSC-711"),
            # Valid JSON, but not a contract object: exactly the shape the
            # Stage 2 suite uses to prove a per-task load failure.
            "NSC-712": json.dumps(["deliberately", "not", "a", "contract"]) + "\n",
            "NSC-713": "{ this is not json at all",
            # Declares a different identity than its path.
            "NSC-714": json.dumps(contract("NSC-999"), indent=2) + "\n",
            "NSC-715": json.dumps(contract("NSC-715", exclusive_resources=["  "]), indent=2) + "\n",
        }
        source, head = make_repository(Path(text), contracts)
        discard_source_commit_snapshots()
        snapshot = source_commit_admission_snapshot(source, head)

        require(
            snapshot.task_ids == ("NSC-711", "NSC-712", "NSC-713", "NSC-714", "NSC-715"),
            f"enumeration must still list every committed contract: {snapshot.task_ids}",
        )
        require(snapshot.task("NSC-711")["id"] == "NSC-711", "the healthy contract still loads")
        for bad in ("NSC-712", "NSC-713", "NSC-714", "NSC-715"):
            try:
                snapshot.task(bad)
            except CommittedTaskError:
                continue
            raise AssertionError(f"{bad}: a malformed contract was accepted")
        # Proven again after the failures: one bad contract does not poison
        # the snapshot for the tasks that are fine.
        require(snapshot.task("NSC-711")["id"] == "NSC-711", "healthy contract still loads after failures")
        discard_source_commit_snapshots()


def test_source_commit_snapshot_reuses_bulk_authority_and_invalidates_on_head_change() -> None:
    """One commit is read once; a moved HEAD is a different snapshot."""

    with tempfile.TemporaryDirectory(prefix="nsc-snapshot-reuse-") as text:
        source, first_head = make_repository(
            Path(text), {"NSC-721": contract("NSC-721"), "NSC-722": contract("NSC-722")}
        )
        discard_source_commit_snapshots()

        first, first_counts = count_git(lambda: source_commit_admission_snapshot(source, first_head))
        require(first_counts["total"] >= 1, f"the first observation must read Git: {first_counts}")

        again, cached_counts = count_git(lambda: source_commit_admission_snapshot(source, first_head))
        require(again is first, "the identical commit must reuse the identical snapshot")
        require(
            cached_counts["total"] == 0,
            f"a cached commit must cost no further Git process: {cached_counts}",
        )

        # A new commit changes one contract. The old snapshot must keep the old
        # bytes and the new commit must be observed independently.
        (source / "Tasks" / "NSC-721.yaml").write_text(
            json.dumps(contract("NSC-721", title="Moved"), indent=2) + "\n", encoding="utf-8"
        )
        git(source, "add", "Tasks")
        git(source, "commit", "-m", "move head")
        second_head = git(source, "rev-parse", "HEAD")
        require(second_head != first_head, "fixture failed to move HEAD")

        second = source_commit_admission_snapshot(source, second_head)
        require(second is not first, "a moved HEAD must not reuse the previous snapshot")
        require(
            second.task("NSC-721")["title"] == "Moved",
            "the new snapshot must carry the new committed bytes",
        )
        require(
            first.task("NSC-721")["title"] != "Moved",
            "the old snapshot must still describe the commit it was keyed by",
        )
        require(
            first.task("NSC-721")["task_contract_sha256"]
            != second.task("NSC-721")["task_contract_sha256"],
            "a changed contract must change its bound hash",
        )
        # Fails closed on anything that is not one exact commit ID.
        for invalid in ("HEAD", "main", "", "0" * 39, "Z" * 40, None):
            try:
                source_commit_admission_snapshot(source, invalid)
            except SourceCommitSnapshotError:
                continue
            raise AssertionError(f"{invalid!r} was accepted as a source commit")
        discard_source_commit_snapshots()


def test_committed_path_snapshot_is_reused_only_for_identical_commit() -> None:
    """The path inventory is lazy, read at most once, and never crosses commits."""

    with tempfile.TemporaryDirectory(prefix="nsc-snapshot-paths-") as text:
        source, first_head = make_repository(Path(text), {"NSC-731": contract("NSC-731")})
        (source / "Assets").mkdir()
        (source / "Assets" / "Existing.cs").write_text("// committed\n", encoding="utf-8")
        git(source, "add", "Assets")
        git(source, "commit", "-m", "add asset")
        head = git(source, "rev-parse", "HEAD")
        discard_source_commit_snapshots()

        snapshot = source_commit_admission_snapshot(source, head)
        require(
            snapshot.cached_committed_paths() is None,
            "the path inventory must stay lazy until something probes it",
        )
        probe = snapshot.committed_path_probe()
        require(
            snapshot.cached_committed_paths() is None,
            "asking for the probe must not itself read the tree",
        )

        _first, first_counts = count_git(lambda: probe("Assets/Existing.cs"))
        require(_first is True, "a committed path must be found")
        require(first_counts["total"] == 1, f"the inventory costs one listing: {first_counts}")

        def probe_many() -> tuple[bool, ...]:
            return (
                probe("Assets/Existing.cs"),
                probe("assets/existing.cs"),
                probe("Assets\\Existing.cs"),
                probe("./Assets/Existing.cs"),
                probe("Assets/Missing.cs"),
            )

        answers, repeat_counts = count_git(probe_many)
        require(answers == (True, True, True, True, False), str(answers))
        require(
            repeat_counts["total"] == 0,
            f"a loaded inventory must not re-read the tree: {repeat_counts}",
        )
        # The same snapshot object serves every later probe at this commit.
        require(
            snapshot.committed_path_probe() is probe,
            "one commit must share exactly one path inventory",
        )

        # A different commit gets its own inventory and its own answers.
        (source / "Assets" / "Later.cs").write_text("// later\n", encoding="utf-8")
        git(source, "add", "Assets")
        git(source, "commit", "-m", "add later asset")
        later_head = git(source, "rev-parse", "HEAD")
        later = source_commit_admission_snapshot(source, later_head)
        require(later.committed_path_probe() is not probe, "commits must not share an inventory")
        require(later.committed_path_probe()("Assets/Later.cs") is True, "new commit sees the new path")
        require(
            probe("Assets/Later.cs") is False,
            "the earlier commit's inventory must not learn about a later commit's path",
        )
        discard_source_commit_snapshots()


def test_cache_is_bounded_and_explicitly_discardable() -> None:
    """A long-running scheduler must not accumulate obsolete commits."""

    with tempfile.TemporaryDirectory(prefix="nsc-snapshot-bounded-") as text:
        source, head = make_repository(Path(text), {"NSC-741": contract("NSC-741")})
        discard_source_commit_snapshots()
        heads = [head]
        for index in range(SNAPSHOT_CACHE_LIMIT + 2):
            (source / "Tasks" / "NSC-741.yaml").write_text(
                json.dumps(contract("NSC-741", title=f"Revision {index}"), indent=2) + "\n",
                encoding="utf-8",
            )
            git(source, "add", "Tasks")
            git(source, "commit", "-m", f"revision {index}")
            heads.append(git(source, "rev-parse", "HEAD"))
        for commit in heads:
            source_commit_admission_snapshot(source, commit)
            require(
                len(cached_snapshot_commits(source)) <= SNAPSHOT_CACHE_LIMIT,
                f"cache exceeded its bound: {cached_snapshot_commits(source)}",
            )
        cached = cached_snapshot_commits(source)
        require(heads[-1] in cached, "the newest commit must still be cached")
        require(heads[0] not in cached, "the oldest commit must have been evicted")

        discard_source_commit_snapshots(root=source, keep_commit=heads[-1])
        require(
            cached_snapshot_commits(source) == (heads[-1],),
            f"explicit discard must keep exactly the verified commit: {cached_snapshot_commits(source)}",
        )
        discard_source_commit_snapshots()
        require(cached_snapshot_commits(source) == (), "explicit discard must clear the cache")


def test_hundred_contract_load_is_bounded_not_one_process_per_contract() -> None:
    """Loading N committed contracts must not cost N Git processes.

    This is the production cost the 1,000-task component test cannot see,
    because that test injects an in-memory task loader. The unmodified loader
    spends one `git show` per contract, so at 1,000 contracts across ~1,262
    Stage-2 observations the live path implies over 1,262,000 processes.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-snapshot-hundred-") as text:
        contracts = {f"NSC-{800 + index}": contract(f"NSC-{800 + index}") for index in range(100)}
        source, head = make_repository(Path(text), contracts)
        discard_source_commit_snapshots()

        def load_every_contract_through_the_snapshot() -> list[str]:
            snapshot = source_commit_admission_snapshot(source, head)
            return [snapshot.task(task_id)["task_contract_sha256"] for task_id in snapshot.task_ids]

        pooled_hashes, pooled_counts = count_git(load_every_contract_through_the_snapshot)

        def load_every_contract_directly() -> list[str]:
            listing = git(source, "ls-tree", "-r", "--name-only", head, "--", "Tasks")
            ids = sorted(
                Path(line).name[: -len(".yaml")]
                for line in listing.splitlines()
                if line.strip().endswith(".yaml")
            )
            return [load_committed_task(source, task_id, commit=head)["task_contract_sha256"] for task_id in ids]

        direct_hashes, direct_counts = count_git(load_every_contract_directly)

        require(len(pooled_hashes) == 100, f"expected 100 contracts, saw {len(pooled_hashes)}")
        require(
            pooled_hashes == direct_hashes,
            "the bulk read produced different contract hashes than the per-task loader",
        )
        require(
            direct_counts["total"] >= 100,
            f"the per-task loader must still cost one process per contract: {direct_counts}",
        )
        require(
            pooled_counts["total"] <= 4,
            f"100 contracts must load in a bounded number of Git processes, saw {pooled_counts}",
        )
        # Complexity is bounded by the commit, not by how many times admission
        # asks: a second full pass over the same commit costs nothing.
        _repeat, repeat_counts = count_git(load_every_contract_through_the_snapshot)
        require(
            repeat_counts["total"] == 0,
            f"a repeated pass at one commit must cost no Git process: {repeat_counts}",
        )
        discard_source_commit_snapshots()


def test_snapshot_enumeration_uses_the_canonical_task_id_contract() -> None:
    """Bulk enumeration must not reopen loose, Unicode or unbounded IDs."""

    contracts = {
        "NSC-999": contract("NSC-999"),
        "NSC-1000": contract("NSC-1000"),
        "NSC-0000": contract("NSC-0000"),
        "NSC-١٢٣": contract("NSC-١٢٣"),
        "NSC-1000000000": contract("NSC-1000000000"),
    }
    with tempfile.TemporaryDirectory(prefix="nsc-snapshot-task-id-") as text:
        source, head = make_repository(Path(text), contracts)
        discard_source_commit_snapshots()
        snapshot = source_commit_admission_snapshot(source, head)
        require(
            snapshot.task_ids == ("NSC-1000", "NSC-999"),
            f"snapshot admitted a non-canonical task ID: {snapshot.task_ids}",
        )
        discard_source_commit_snapshots()


def test_policy_document_is_captured_from_the_exact_commit_without_git_show() -> None:
    """A dirty working-tree policy must never leak into commit-bound admission."""

    with tempfile.TemporaryDirectory(prefix="nsc-snapshot-policy-") as text:
        source, _initial = make_repository(
            Path(text), {"NSC-999": contract("NSC-999")}
        )
        relative = "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
        policy = source / relative
        policy.parent.mkdir(parents=True)
        policy.write_text(
            json.dumps({"schema_version": "1.0", "marker": "committed"}) + "\n",
            encoding="utf-8",
        )
        git(source, "add", relative)
        git(source, "commit", "-m", "commit policy authority")
        head = git(source, "rev-parse", "HEAD")
        policy.write_text(
            json.dumps({"schema_version": "1.0", "marker": "working-tree"}) + "\n",
            encoding="utf-8",
        )
        discard_source_commit_snapshots()

        snapshot, counts = count_git(
            lambda: source_commit_admission_snapshot(source, head)
        )
        document = snapshot.committed_json_document(relative)
        require(document["marker"] == "committed", str(document))
        require(
            counts["show"] == 0
            and counts["ls-tree"] == 1
            and counts["cat-file"] == 1,
            f"policy capture escaped the bounded bulk read: {counts}",
        )
        discard_source_commit_snapshots()


def test_production_poll_planner_uses_the_commit_snapshot() -> None:
    """The real poll planner must not fall back to one ``git show`` per task.

    Unit-testing the snapshot alone does not prove that production Stage 2
    consumes it. This drives :func:`build_poll_dispatch_plan` with its real
    task enumeration and loader composition while replacing only mutable
    GitHub/claim authority and the external taskcontrol subprocess.
    """

    class Workflow:
        def list_agent_ready(self) -> list[dict[str, Any]]:
            return []

        def find(self, _task_id: str) -> None:
            return None

        def resource_conflicts(
            self, _task: dict[str, Any]
        ) -> tuple[list[str], list[str]]:
            return [], []

    class StateProvider:
        def __init__(self, *, expected_task_ids: Any, **_values: Any) -> None:
            self.task_ids = tuple(expected_task_ids)

        def ensure_snapshot(self) -> dict[str, dict[str, Any]]:
            return {task_id: self(task_id) for task_id in self.task_ids}

        def __call__(self, task_id: str) -> dict[str, Any]:
            return {"task_id": task_id, "state": "not_delivered", "error": None}

    with tempfile.TemporaryDirectory(prefix="nsc-snapshot-production-poll-") as text:
        contracts = {
            f"NSC-{800 + index}": contract(f"NSC-{800 + index}")
            for index in range(100)
        }
        source, _head = make_repository(Path(text), contracts)
        discard_source_commit_snapshots()

        def build() -> Any:
            with ExitStack() as stack:
                stack.enter_context(
                    patch.object(
                        polling_module,
                        "repo_root",
                        side_effect=lambda value: Path(value).resolve(),
                    )
                )
                stack.enter_context(
                    patch.object(
                        polling_module,
                        "IssueWorkflowService",
                        return_value=Workflow(),
                    )
                )
                stack.enter_context(
                    patch.object(
                        polling_module.dispatch_plan_module,
                        "_read_only_claim_observation",
                        return_value=({}, None, {"status": "fixture"}, ()),
                    )
                )
                stack.enter_context(
                    patch.object(
                        polling_module.dispatch_plan_module,
                        "_LazyTaskcontrolStateProvider",
                        StateProvider,
                    )
                )
                return polling_module.build_poll_dispatch_plan(
                    source=source,
                    worker_id="snapshot-production-poll-test",
                    backend=object(),
                )

        first_plan, first_counts = count_git(build)
        second_plan, second_counts = count_git(build)

        observed_task_count = (
            len(first_plan.ranked_eligible_candidates)
            + len(first_plan.skipped_candidates)
        )
        require(
            observed_task_count == 100,
            f"production planner lost committed contracts: {observed_task_count}",
        )
        require(
            first_counts["show"] == 0,
            f"production planner still loads tasks with git show: {first_counts}",
        )
        require(
            first_counts["ls-tree"] <= 2 and first_counts["cat-file"] <= 1,
            f"first production plan did not use one bounded bulk snapshot: {first_counts}",
        )
        require(
            second_plan.source_commit == first_plan.source_commit,
            "unchanged source produced a different plan commit",
        )
        require(
            second_counts["show"] == 0
            and second_counts["ls-tree"] == 0
            and second_counts["cat-file"] == 0,
            f"unchanged source rebuilt immutable task authority: {second_counts}",
        )
        discard_source_commit_snapshots()


def main() -> int:
    tests = [
        test_bulk_read_matches_the_per_task_loader_exactly,
        test_one_malformed_contract_rejects_only_itself,
        test_source_commit_snapshot_reuses_bulk_authority_and_invalidates_on_head_change,
        test_committed_path_snapshot_is_reused_only_for_identical_commit,
        test_cache_is_bounded_and_explicitly_discardable,
        test_hundred_contract_load_is_bounded_not_one_process_per_contract,
        test_snapshot_enumeration_uses_the_canonical_task_id_contract,
        test_policy_document_is_captured_from_the_exact_commit_without_git_show,
        test_production_poll_planner_uses_the_commit_snapshot,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"source commit snapshot tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
