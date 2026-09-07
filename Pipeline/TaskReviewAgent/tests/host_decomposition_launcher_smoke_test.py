#!/usr/bin/env python3
"""No-network tests for the host decomposition lifecycle boundary."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.host_decomposition_launcher as launcher  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
)


TASK_ID = "NSC-777"
SOURCE_HEAD = "1" * 40
VALIDATION_POLICY_RELATIVE = (
    "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
)
PLAN_ID = "GDP-" + "a" * 64
D1C_SUBJECT = f"taskgraph: apply {TASK_ID} decomposition {PLAN_ID}"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class RecordingService:
    def __init__(self) -> None:
        self.releases: list[dict] = []
        self.completions: list[dict] = []

    def release_decomposition_lease(self, **values):
        self.releases.append(dict(values))
        return {"status": "agent_ready"}

    def complete_decomposition(self, **values):
        self.completions.append(dict(values))
        return {"status": "complete"}

    @staticmethod
    def find(_task_id):
        return None


class RecordingClaimClient:
    def __init__(self) -> None:
        self.receipt = object()
        self.released: list[object] = []

    def acquire(self, **_values):
        return self.receipt

    def release(self, receipt):
        self.released.append(receipt)
        return {"status": "released"}


def arguments() -> SimpleNamespace:
    return SimpleNamespace(
        task_id=TASK_ID,
        compose_project="nosafecircle-m2a",
        providers="codex,claude",
        max_calls=4,
    )


def test_git_timeout_is_normalized_for_lease_and_artifact_cleanup() -> None:
    with tempfile.TemporaryDirectory() as text:
        source = Path(text)
        timeout = subprocess.TimeoutExpired(
            cmd=("git", "push", "origin", "fixture:refs/heads/main"),
            timeout=180.0,
        )
        with patch.object(launcher.subprocess, "run", side_effect=timeout):
            try:
                launcher._git(source, "push", "origin", "fixture:refs/heads/main")
            except RuntimeError as exc:
                require("git push origin" in str(exc), str(exc))
                require("timed out after 180 seconds" in str(exc), str(exc))
                require(exc.__cause__ is timeout, repr(exc.__cause__))
            except subprocess.TimeoutExpired as exc:
                raise AssertionError(
                    "raw TimeoutExpired bypassed launcher cleanup"
                ) from exc
            else:
                raise AssertionError("timed-out git call unexpectedly succeeded")


def test_exact_d1c_commit_uses_subject_and_sole_authorized_parent() -> None:
    with tempfile.TemporaryDirectory() as text:
        source = Path(text) / "source"
        source.mkdir()

        def fixture_git(*args: str) -> str:
            result = subprocess.run(
                ("git", "-C", str(source), *args),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30.0,
            )
            if result.returncode != 0:
                raise AssertionError(
                    f"fixture git failed ({result.returncode}): {args}\n{result.stderr}"
                )
            return result.stdout.strip()

        fixture_git("init", "-b", "main")
        fixture_git("config", "user.name", "D1C Fixture")
        fixture_git(
            "config", "user.email", "d1c-fixture@nosafecircle.invalid"
        )
        (source / "base.txt").write_text("base\n", encoding="utf-8")
        fixture_git("add", "base.txt")
        fixture_git("commit", "-m", "fixture base")
        authorized_head = fixture_git("rev-parse", "HEAD")
        subject = f"taskgraph: apply {TASK_ID} decomposition {PLAN_ID}"
        fixture_git("commit", "--allow-empty", "-m", subject)
        exact_commit = fixture_git("rev-parse", "HEAD")
        fixture_git("commit", "--allow-empty", "-m", "later unrelated main change")
        fixture_git("commit", "--allow-empty", "-m", subject)
        current_head = fixture_git("rev-parse", "HEAD")

        found = launcher._exact_d1c_commit(
            source,
            task_id=TASK_ID,
            plan_id=PLAN_ID,
            authorized_head=authorized_head,
            current_head=current_head,
        )
        require(found == exact_commit, f"expected {exact_commit}, found {found}")


def test_proposal_failure_releases_durable_lease_without_killing_scheduler() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        output = root / "outputs"
        output.mkdir()
        service = RecordingService()
        original = launcher.subprocess.run
        launcher.subprocess.run = lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=7
        )
        try:
            result = launcher._run_proposal(
                args=arguments(),
                workspace=root,
                output_root=output,
                source_head=SOURCE_HEAD,
                service=service,
            )
        finally:
            launcher.subprocess.run = original
        require(result == 3, f"handled proposal failure returned {result}")
        require(len(service.releases) == 1, str(service.releases))
        require(
            service.releases[0].get("task_id") == TASK_ID,
            str(service.releases),
        )


def test_stale_authorized_plan_releases_to_fresh_decomposition() -> None:
    service = RecordingService()
    handoff = SimpleNamespace(
        event_type=WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED,
        details={
            "graph_delta_plan_id": PLAN_ID,
            "head_commit": SOURCE_HEAD,
            "artifact_root": "C:/fixture/output",
        },
    )
    snapshot = SimpleNamespace(events=(handoff,))
    original = launcher.inspect_authorized_decomposition_replay
    launcher.inspect_authorized_decomposition_replay = lambda **_values: SimpleNamespace(
        plan_id=PLAN_ID,
        authorized_source_head=SOURCE_HEAD,
        inspection=SimpleNamespace(
            status="stale_or_partial",
            reason="fixture exact plan is absent",
        ),
    )
    try:
        result = launcher._apply_approved_plan(
            args=arguments(),
            source=Path("C:/fixture/source"),
            source_head="2" * 40,
            service=service,
            claim_client=SimpleNamespace(),
            prelease_snapshot=snapshot,
        )
    finally:
        launcher.inspect_authorized_decomposition_replay = original
    require(result == 3, str(result))
    require(len(service.releases) == 1, str(service.releases))
    require(
        "main moved" in service.releases[0].get("reason", ""),
        str(service.releases),
    )
    require(
        service.releases[0].get("retry_phase") is None,
        "stale authorization should use the default fresh-decomposition phase",
    )


def test_malformed_proposal_artifact_releases_durable_lease() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        output = root / "outputs"
        output.mkdir()
        service = RecordingService()
        original = launcher.subprocess.run

        def fake_run(*args, **kwargs):
            (output / "new-run").mkdir()
            return subprocess.CompletedProcess(args=args[0], returncode=0)

        launcher.subprocess.run = fake_run
        try:
            result = launcher._run_proposal(
                args=arguments(),
                workspace=root,
                output_root=output,
                source_head=SOURCE_HEAD,
                service=service,
            )
        finally:
            launcher.subprocess.run = original
        require(result == 3, str(result))
        require(len(service.releases) == 1, str(service.releases))
        require("artifacts" in service.releases[0]["reason"], str(service.releases))


def test_provider_start_error_releases_durable_lease() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        output = root / "outputs"
        output.mkdir()
        service = RecordingService()
        original = launcher.subprocess.run

        def fail_start(*_args, **_kwargs):
            raise FileNotFoundError("docker fixture missing")

        launcher.subprocess.run = fail_start
        try:
            result = launcher._run_proposal(
                args=arguments(),
                workspace=root,
                output_root=output,
                source_head=SOURCE_HEAD,
                service=service,
            )
        finally:
            launcher.subprocess.run = original
        require(result == 3, str(result))
        require(len(service.releases) == 1, str(service.releases))
        require("could not start" in service.releases[0]["reason"], str(service.releases))


def test_output_observation_error_releases_durable_lease() -> None:
    class FailingOutputRoot:
        def __init__(self) -> None:
            self.scans = 0

        @staticmethod
        def mkdir(**_values) -> None:
            return None

        def iterdir(self):
            self.scans += 1
            if self.scans == 1:
                return iter(())
            raise OSError("fixture output scan failure")

        @staticmethod
        def __str__() -> str:
            return "C:/fixture/decomposition-output"

    service = RecordingService()
    original = launcher.subprocess.run
    launcher.subprocess.run = lambda *args, **kwargs: subprocess.CompletedProcess(
        args=args[0], returncode=0
    )
    try:
        try:
            launcher._run_proposal(
                args=arguments(),
                workspace=Path("C:/fixture/workspace"),
                output_root=FailingOutputRoot(),
                source_head=SOURCE_HEAD,
                service=service,
            )
        except OSError as exc:
            require("output scan failure" in str(exc), str(exc))
        else:
            raise AssertionError("post-provider output scan failure did not propagate")
    finally:
        launcher.subprocess.run = original
    require(len(service.releases) == 1, str(service.releases))
    require("after provider exit" in service.releases[0]["reason"], str(service.releases))


def test_scheduler_proposal_rejects_wrong_run_directory_and_escaped_paths() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        output = root / "outputs"
        output.mkdir()
        service = RecordingService()
        args = arguments()
        args.run_id = "scheduler-nsc-777-exact-result"
        args.task_contract_sha256 = "a" * 64
        original = launcher.subprocess.run

        def wrong_directory(*args, **_kwargs):
            (output / "untrusted-other-run").mkdir()
            return subprocess.CompletedProcess(args=args[0], returncode=0)

        launcher.subprocess.run = wrong_directory
        try:
            result = launcher._run_proposal(
                args=args,
                workspace=root,
                output_root=output,
                source_head=SOURCE_HEAD,
                service=service,
            )
        finally:
            launcher.subprocess.run = original
        require(result == 3, str(result))
        require(len(service.releases) == 1, str(service.releases))

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        output = root / "outputs"
        output.mkdir()
        service = RecordingService()
        args = arguments()
        args.run_id = "scheduler-nsc-777-escaped-result"
        args.task_contract_sha256 = "a" * 64

        def escaped_paths(*command_args, **_kwargs):
            run_dir = output / args.run_id
            run_dir.mkdir()
            (run_dir / "decomposition_run_result.json").write_text(
                json.dumps(
                    {
                        "task_id": TASK_ID,
                        "run_id": args.run_id,
                        "run_status": "review_ready",
                        "source_identity": {"head_commit": SOURCE_HEAD},
                        "task_execution_contract_identity": {"sha256": "a" * 64},
                        "graph_delta_path": "../graph_delta.json",
                        "decomposition_result_path": "../decomposition_result.json",
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args=command_args[0], returncode=0)

        launcher.subprocess.run = escaped_paths
        try:
            result = launcher._run_proposal(
                args=args,
                workspace=root,
                output_root=output,
                source_head=SOURCE_HEAD,
                service=service,
            )
        finally:
            launcher.subprocess.run = original
        require(result == 3, str(result))
        require(len(service.releases) == 1, str(service.releases))
        require("non-canonical" in service.releases[0]["reason"], str(service.releases))


def test_apply_artifact_error_releases_global_claim() -> None:
    service = RecordingService()
    claims = RecordingClaimClient()
    handoff = SimpleNamespace(
        event_type=WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED,
        details={
            "graph_delta_plan_id": PLAN_ID,
            "head_commit": SOURCE_HEAD,
            "artifact_root": "C:/fixture/missing-output",
        },
    )
    snapshot = SimpleNamespace(events=(handoff,))
    original_git = launcher._git
    original_replay = launcher.inspect_authorized_decomposition_replay
    launcher._git = lambda _source, *git_args: SOURCE_HEAD
    launcher.inspect_authorized_decomposition_replay = lambda **_values: SimpleNamespace(
        plan_id=PLAN_ID,
        authorized_source_head=SOURCE_HEAD,
        artifact_root=Path("C:/fixture/missing-output"),
        graph_delta=object(),
        inspection=SimpleNamespace(status="fresh_source", reason="fixture fresh"),
    )
    try:
        try:
            launcher._apply_approved_plan(
                args=arguments(),
                source=Path("C:/fixture/source"),
                source_head=SOURCE_HEAD,
                service=service,
                claim_client=claims,
                prelease_snapshot=snapshot,
            )
        except OSError:
            pass
        else:
            raise AssertionError("missing authorized artifacts did not fail closed")
    finally:
        launcher._git = original_git
        launcher.inspect_authorized_decomposition_replay = original_replay
    require(claims.released == [claims.receipt], str(claims.released))


def run_fixture_git(repo: Path, *args: str) -> str:
    """Run one real Git command in a disposable fixture repository."""

    result = subprocess.run(
        ("git", "-C", str(repo), *args),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120.0,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"fixture git failed ({result.returncode}): {args}\n{result.stderr}"
        )
    return result.stdout.strip()


def initialize_fixture_repository(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run_fixture_git(path, "init", "-b", "main")
    run_fixture_git(path, "config", "user.name", "D1C Fixture")
    run_fixture_git(path, "config", "user.email", "d1c-fixture@nosafecircle.invalid")
    run_fixture_git(path, "config", "core.autocrlf", "false")
    run_fixture_git(path, "config", "commit.gpgsign", "false")


class PushRaceRepository:
    """A real origin plus the shared D1C checkout and one sibling task clone.

    Every ancestry, HEAD, cleanliness and reset decision the push-race
    recovery makes is answered by real Git against these repositories, so the
    safety-critical discriminator is exercised instead of stubbed.
    """

    def __init__(self, root: Path) -> None:
        self.origin = root / "origin.git"
        run_fixture_git(root, "init", "--bare", "-b", "main", "origin.git")
        self.source = self._task_clone(root / "source")
        (self.source / "base.txt").write_text("base\n", encoding="utf-8")
        run_fixture_git(self.source, "add", "base.txt")
        run_fixture_git(self.source, "commit", "-m", "fixture base")
        run_fixture_git(self.source, "push", "origin", "main")
        self.base = run_fixture_git(self.source, "rev-parse", "HEAD")
        self.sibling = self._task_clone(root / "sibling")

    def _task_clone(self, path: Path) -> Path:
        initialize_fixture_repository(path)
        run_fixture_git(path, "remote", "add", "origin", str(self.origin))
        return path

    def apply_local_d1c_commit(self, subject: str) -> str:
        """Create the exact local D1C commit apply_graph_delta would create."""

        (self.source / "applied_graph.json").write_text(
            '{"applied": true}\n', encoding="utf-8"
        )
        run_fixture_git(self.source, "add", "applied_graph.json")
        run_fixture_git(self.source, "commit", "-m", subject)
        return run_fixture_git(self.source, "rev-parse", "HEAD")

    def land_sibling_commit(self, subject: str) -> str:
        """Publish one unrelated sibling-task commit on the real origin/main."""

        run_fixture_git(self.sibling, "fetch", "origin", "main")
        run_fixture_git(self.sibling, "checkout", "-B", "main", "origin/main")
        run_fixture_git(self.sibling, "commit", "--allow-empty", "-m", subject)
        run_fixture_git(self.sibling, "push", "origin", "main")
        return run_fixture_git(self.sibling, "rev-parse", "HEAD")

    def rewind_main_to_unrelated_history(self, subject: str) -> str:
        """Force origin/main onto history that shares no commit with the base."""

        run_fixture_git(self.sibling, "checkout", "--orphan", "rewound")
        run_fixture_git(self.sibling, "commit", "--allow-empty", "-m", subject)
        run_fixture_git(self.sibling, "push", "--force", "origin", "rewound:main")
        return run_fixture_git(self.sibling, "rev-parse", "HEAD")

    def published_main(self) -> str:
        return run_fixture_git(self.origin, "rev-parse", "main")

    def source_head(self) -> str:
        return run_fixture_git(self.source, "rev-parse", "HEAD")

    def source_is_clean(self) -> bool:
        return not run_fixture_git(
            self.source, "status", "--porcelain=v1", "--untracked-files=all"
        )

    def main_contains(self, commit: str) -> bool:
        """True only when origin genuinely holds this exact commit on main.

        Membership is read out of the bare origin itself, so a commit the
        remote never received answers False instead of being assumed present.
        """

        return commit in run_fixture_git(self.origin, "rev-list", "main").splitlines()


def decomposition_fixture() -> SimpleNamespace:
    return SimpleNamespace(parent_task=SimpleNamespace(to_dict=lambda: {"id": TASK_ID}))


def replay_fixture(
    *, authorized_head: str, status: str, reason: str, artifact_root: Path
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_id=PLAN_ID,
        authorized_source_head=authorized_head,
        artifact_root=artifact_root,
        graph_delta=object(),
        inspection=SimpleNamespace(status=status, reason=reason),
    )


def apply_patches(*, replay, applied, hooked_git):
    return (
        patch.object(
            launcher, "inspect_authorized_decomposition_replay", return_value=replay
        ),
        patch.object(launcher, "_git", side_effect=hooked_git),
        patch.object(launcher, "_load_json", return_value={}),
        patch.object(
            launcher.DecompositionResult,
            "from_dict",
            return_value=decomposition_fixture(),
        ),
        patch.object(launcher, "apply_graph_delta", return_value=applied),
    )


def test_is_ancestor_decides_real_git_ancestry_and_fails_closed() -> None:
    """The push-race discriminator itself must answer real Git ancestry."""

    with tempfile.TemporaryDirectory() as text:
        source = Path(text) / "source"
        initialize_fixture_repository(source)
        run_fixture_git(source, "commit", "--allow-empty", "-m", "fixture base")
        base = run_fixture_git(source, "rev-parse", "HEAD")
        run_fixture_git(source, "commit", "--allow-empty", "-m", D1C_SUBJECT)
        applied = run_fixture_git(source, "rev-parse", "HEAD")
        run_fixture_git(source, "commit", "--allow-empty", "-m", "sibling on top")
        descendant = run_fixture_git(source, "rev-parse", "HEAD")
        run_fixture_git(source, "checkout", "-b", "diverged", base)
        run_fixture_git(source, "commit", "--allow-empty", "-m", "diverged sibling")
        diverged = run_fixture_git(source, "rev-parse", "HEAD")

        require(
            launcher._is_ancestor(source, base, applied),
            "the authorized base is an ancestor of the D1C commit",
        )
        require(
            launcher._is_ancestor(source, applied, descendant),
            "a commit is an ancestor of work integrated on top of it",
        )
        require(
            launcher._is_ancestor(source, applied, applied),
            "an identical commit is an ancestor of itself",
        )
        require(
            not launcher._is_ancestor(source, applied, diverged),
            "a diverged sibling does not contain the D1C commit",
        )
        require(
            not launcher._is_ancestor(source, descendant, applied),
            "ancestry must not be answered symmetrically",
        )
        try:
            launcher._is_ancestor(source, "0" * 40, applied)
        except RuntimeError as exc:
            require("merge-base --is-ancestor failed" in str(exc), str(exc))
        else:
            raise AssertionError(
                "an unknown revision silently answered the ancestry question"
            )


def test_discard_unpublished_local_commit_enforces_its_single_commit_contract() -> None:
    """The reset helper must prove its own precondition before reset --hard.

    It documents that it can only ever discard the exact commit this process
    just created. Against a shared checkout that has to be enforced here, not
    inferred from caller-side invariants that live in other modules.
    """

    with tempfile.TemporaryDirectory() as text:
        source = Path(text) / "source"
        initialize_fixture_repository(source)
        run_fixture_git(source, "commit", "--allow-empty", "-m", "fixture base")
        base = run_fixture_git(source, "rev-parse", "HEAD")
        run_fixture_git(source, "commit", "--allow-empty", "-m", D1C_SUBJECT)
        applied = run_fixture_git(source, "rev-parse", "HEAD")
        run_fixture_git(source, "commit", "--allow-empty", "-m", "later local commit")
        ahead_by_two = run_fixture_git(source, "rev-parse", "HEAD")

        try:
            launcher._discard_unpublished_local_commit(
                source, expected_head=ahead_by_two, restore_to=base,
            )
        except RuntimeError as exc:
            require("exactly that one commit" in str(exc), str(exc))
        else:
            raise AssertionError(
                "the reset helper discarded more local commits than its "
                "documented contract allows"
            )
        require(
            run_fixture_git(source, "rev-parse", "HEAD") == ahead_by_two,
            "a refused discard must not move HEAD",
        )

        run_fixture_git(source, "checkout", "-B", "published", applied)
        try:
            launcher._discard_unpublished_local_commit(
                source, expected_head=applied, restore_to=ahead_by_two,
            )
        except RuntimeError as exc:
            require("exactly that one commit" in str(exc), str(exc))
        else:
            raise AssertionError(
                "the reset helper discarded a commit the restore target already "
                "contains, so it was never unpublished"
            )
        require(
            run_fixture_git(source, "rev-parse", "HEAD") == applied,
            "a refused discard must not move HEAD",
        )

        run_fixture_git(source, "checkout", "-B", "remote", base)
        run_fixture_git(
            source, "commit", "--allow-empty", "-m", "unrelated sibling integration"
        )
        sibling = run_fixture_git(source, "rev-parse", "HEAD")
        run_fixture_git(source, "checkout", "published")

        (source / "concurrent.txt").write_text("other writer\n", encoding="utf-8")
        try:
            launcher._discard_unpublished_local_commit(
                source, expected_head=applied, restore_to=sibling,
            )
        except RuntimeError as exc:
            require("concurrent uncommitted changes" in str(exc), str(exc))
        else:
            raise AssertionError("the reset helper ran against a dirty shared checkout")
        (source / "concurrent.txt").unlink()

        try:
            launcher._discard_unpublished_local_commit(
                source, expected_head=applied, restore_to="0" * 40,
            )
        except RuntimeError as exc:
            require("git rev-list" in str(exc), str(exc))
        else:
            raise AssertionError("an unknown restore target was silently accepted")
        require(
            run_fixture_git(source, "rev-parse", "HEAD") == applied,
            "a refused discard must not move HEAD",
        )

        launcher._discard_unpublished_local_commit(
            source, expected_head=applied, restore_to=sibling,
        )
        require(
            run_fixture_git(source, "rev-parse", "HEAD") == sibling,
            "a genuine lost race must restore the checkout to the verified remote",
        )


def test_unpushed_local_d1c_commit_is_retried_without_reapplying_graph() -> None:
    """A genuine first push failure must not strand main ahead of origin/main."""

    with tempfile.TemporaryDirectory() as text:
        repo = PushRaceRepository(Path(text))
        applied_commit = repo.apply_local_d1c_commit(D1C_SUBJECT)
        service = RecordingService()
        claims = RecordingClaimClient()
        real_git = launcher._git
        push_attempts: list[tuple[str, ...]] = []
        fail_first_push = {"value": True}

        def hooked_git(source, *git_args):
            if git_args[:1] != ("push",):
                return real_git(source, *git_args)
            push_attempts.append(git_args)
            if fail_first_push["value"]:
                fail_first_push["value"] = False
                raise RuntimeError("fixture genuine transport failure")
            return real_git(source, *git_args)

        replay = replay_fixture(
            authorized_head=repo.base,
            status="already_applied",
            reason="the exact D1C graph is already present locally",
            artifact_root=Path(text) / "decomposition-output",
        )
        applied = SimpleNamespace(
            status="already_applied",
            reason="fixture exact replay",
            new_commit_sha=None,
        )
        patches = apply_patches(
            replay=replay, applied=applied, hooked_git=hooked_git
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            try:
                launcher._apply_approved_plan(
                    args=arguments(),
                    source=repo.source,
                    source_head=applied_commit,
                    service=service,
                    claim_client=claims,
                    prelease_snapshot=SimpleNamespace(),
                )
            except RuntimeError as exc:
                require("transport failure" in str(exc), str(exc))
            else:
                raise AssertionError("genuine D1C push failure was reported as success")
            require(
                not repo.main_contains(applied_commit),
                "the failed push must not have published anything",
            )

            result = launcher._apply_approved_plan(
                args=arguments(),
                source=repo.source,
                source_head=applied_commit,
                service=service,
                claim_client=claims,
                prelease_snapshot=SimpleNamespace(),
            )

        require(result == 0, str(result))
        require(repo.published_main() == applied_commit, repo.published_main())
        require(len(push_attempts) == 2, str(push_attempts))
        require(claims.released == [claims.receipt, claims.receipt], str(claims.released))
        require(
            service.completions
            == [
                {
                    "task_id": TASK_ID,
                    "graph_delta_plan_id": PLAN_ID,
                    "applied_commit": applied_commit,
                }
            ],
            str(service.completions),
        )
        require(not service.releases, str(service.releases))


def test_unrelated_concurrent_push_discards_local_commit_and_retries() -> None:
    """A sibling task's legitimate merge winning the push race must not crash.

    Ten tasks integrate to the same origin/main concurrently. The pre-push
    check only proves origin/main was still the authorized base at that
    instant; an ordinary, unrelated commit from another task can still land
    on origin/main before this exact push lands. That must be recovered the
    same way an earlier "main moved" observation is recovered -- release the
    lease and require a fresh D1B.2 proposal -- instead of raising all the
    way out as an unhandled decomposition_launcher_exception, and it must
    leave the shared controller checkout exactly at the new origin/main
    rather than diverged from it.

    The sibling commit lands on the real origin inside the push window, so
    the push is genuinely rejected and real Git decides the recovery.
    """

    with tempfile.TemporaryDirectory() as text:
        repo = PushRaceRepository(Path(text))
        applied_commit = repo.apply_local_d1c_commit(D1C_SUBJECT)
        service = RecordingService()
        claims = RecordingClaimClient()
        real_git = launcher._git
        sibling = {}

        def hooked_git(source, *git_args):
            if git_args[:1] != ("push",):
                return real_git(source, *git_args)
            # The sibling task wins the race for this exact ref while this
            # push is in flight, so the real push is genuinely rejected.
            sibling["commit"] = repo.land_sibling_commit("sibling task integration")
            return real_git(source, *git_args)

        replay = replay_fixture(
            authorized_head=repo.base,
            status="fresh_source",
            reason="fixture fresh",
            artifact_root=Path(text) / "decomposition-output",
        )
        applied = SimpleNamespace(
            status="applied",
            reason="fixture applied",
            new_commit_sha=applied_commit,
        )
        patches = apply_patches(
            replay=replay, applied=applied, hooked_git=hooked_git
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = launcher._apply_approved_plan(
                args=arguments(),
                source=repo.source,
                source_head=repo.base,
                service=service,
                claim_client=claims,
                prelease_snapshot=SimpleNamespace(),
            )

        require(result == 3, str(result))
        require(repo.published_main() == sibling["commit"], repo.published_main())
        require(
            not repo.main_contains(applied_commit),
            "the discarded commit must never have reached origin/main",
        )
        require(
            repo.source_head() == sibling["commit"],
            f"the shared checkout was left diverged from origin/main: {repo.source_head()}",
        )
        require(repo.source_is_clean(), "the recovered checkout must be clean")
        require(not service.completions, f"a lost race recorded a completion: {service.completions}")
        require(len(service.releases) == 1, str(service.releases))
        require(
            "unrelated commit" in service.releases[0]["reason"], str(service.releases)
        )
        require(claims.released == [claims.receipt], str(claims.released))


def test_published_d1c_commit_is_kept_when_main_advances_after_a_lost_report() -> None:
    """A push that landed must not be discarded because main then moved on.

    `_git` raises on its own 180 s timeout, so a push the remote already
    accepted can be reported as a failure. If an unrelated sibling task then
    integrates on top of this exact D1C commit, origin/main is a descendant
    of it rather than equal to it. The commit is provably durable on
    origin/main, so this is a successful publication: it must be completed
    with that exact applied_commit rather than reset out of the shared
    checkout and returned to D1B for a decomposition main already contains.
    """

    with tempfile.TemporaryDirectory() as text:
        repo = PushRaceRepository(Path(text))
        applied_commit = repo.apply_local_d1c_commit(D1C_SUBJECT)
        service = RecordingService()
        claims = RecordingClaimClient()
        real_git = launcher._git
        sibling = {}

        def hooked_git(source, *git_args):
            if git_args[:1] != ("push",):
                return real_git(source, *git_args)
            # The remote accepts this exact push and only the transport
            # report is lost; the sibling task then integrates on top of it.
            real_git(source, *git_args)
            sibling["commit"] = repo.land_sibling_commit("sibling task integration")
            raise RuntimeError("git push origin timed out after 180 seconds")

        replay = replay_fixture(
            authorized_head=repo.base,
            status="fresh_source",
            reason="fixture fresh",
            artifact_root=Path(text) / "decomposition-output",
        )
        applied = SimpleNamespace(
            status="applied",
            reason="fixture applied",
            new_commit_sha=applied_commit,
        )
        patches = apply_patches(
            replay=replay, applied=applied, hooked_git=hooked_git
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = launcher._apply_approved_plan(
                args=arguments(),
                source=repo.source,
                source_head=repo.base,
                service=service,
                claim_client=claims,
                prelease_snapshot=SimpleNamespace(),
            )

        require(
            repo.main_contains(applied_commit),
            "fixture did not publish the exact D1C commit",
        )
        require(repo.published_main() == sibling["commit"], repo.published_main())
        require(
            repo.source_head() == applied_commit,
            "a D1C commit that is durably on origin/main was reset out of the "
            f"shared checkout (head={repo.source_head()}, applied={applied_commit})",
        )
        require(
            result == 0 and not service.releases,
            "a durably published D1C application was returned for re-proposal "
            f"(exit={result}, releases={service.releases})",
        )
        require(
            service.completions
            == [
                {
                    "task_id": TASK_ID,
                    "graph_delta_plan_id": PLAN_ID,
                    "applied_commit": applied_commit,
                }
            ],
            f"the applied_commit provenance was dropped: {service.completions}",
        )
        require(claims.released == [claims.receipt], str(claims.released))


def test_rewound_origin_main_after_a_failed_push_fails_closed() -> None:
    """An origin/main that does not contain our commit and did not advance
    from the pre-push observation is not a recoverable race.

    A force-pushed or rewound main must surface as the original push failure
    with the local commit untouched, never as a silent discard.
    """

    with tempfile.TemporaryDirectory() as text:
        repo = PushRaceRepository(Path(text))
        applied_commit = repo.apply_local_d1c_commit(D1C_SUBJECT)
        service = RecordingService()
        claims = RecordingClaimClient()
        real_git = launcher._git
        rewound = {}

        def hooked_git(source, *git_args):
            if git_args[:1] != ("push",):
                return real_git(source, *git_args)
            rewound["commit"] = repo.rewind_main_to_unrelated_history(
                "unrelated rewound history"
            )
            return real_git(source, *git_args)

        replay = replay_fixture(
            authorized_head=repo.base,
            status="fresh_source",
            reason="fixture fresh",
            artifact_root=Path(text) / "decomposition-output",
        )
        applied = SimpleNamespace(
            status="applied",
            reason="fixture applied",
            new_commit_sha=applied_commit,
        )
        patches = apply_patches(
            replay=replay, applied=applied, hooked_git=hooked_git
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            try:
                launcher._apply_approved_plan(
                    args=arguments(),
                    source=repo.source,
                    source_head=repo.base,
                    service=service,
                    claim_client=claims,
                    prelease_snapshot=SimpleNamespace(),
                )
            except RuntimeError as exc:
                require("git push origin" in str(exc), str(exc))
            else:
                raise AssertionError(
                    "a rewound origin/main was recovered instead of failing closed"
                )

        require(repo.published_main() == rewound["commit"], repo.published_main())
        require(
            repo.source_head() == applied_commit,
            f"an unexplained remote discarded the local commit: {repo.source_head()}",
        )
        require(not service.completions, str(service.completions))
        require(not service.releases, str(service.releases))
        require(claims.released == [claims.receipt], str(claims.released))


def test_compose_command_is_exact_review_only_service() -> None:
    command = launcher.build_compose_command(
        task_id=TASK_ID,
        project="nosafecircle-m2a",
        providers="codex,claude",
        max_calls=4,
    )
    require("round-robin-decompose" in command, str(command))
    require(
        any(item.endswith("run_round_robin_decomposition.py") for item in command),
        str(command),
    )
    require(command[command.index("--task-id") + 1] == TASK_ID, str(command))
    require("apply_graph_delta.py" not in command, str(command))


def test_scheduler_decomposition_run_writes_identity_bound_terminal_result() -> None:
    originals = {
        name: getattr(launcher, name)
        for name in (
            "repo_root",
            "_git",
            "load_committed_task",
            "validate_decomposition_selection",
            "GhIssueBackend",
            "IssueWorkflowService",
            "DurableTaskCheckoutManager",
            "RealTaskObserver",
            "_acquire_workflow_lease",
            "_checkout_observation",
            "_run_proposal",
        )
    }

    class Service:
        releases = []
        snapshot = None

        @classmethod
        def find(cls, _task_id):
            return cls.snapshot

        @classmethod
        def release_decomposition_lease(cls, **values):
            cls.releases.append(dict(values))
            return {"status": "agent_ready"}

    class CheckoutManager:
        prepared_status = "created"

        def __init__(self, **values):
            self.checkout_path = Path(values["checkout_root"]) / values["task_id"]

        @staticmethod
        def expected_branch(_observation):
            return "nsc-777-decomposition-fixture"

        @staticmethod
        def prepare(_observation):
            if CheckoutManager.prepared_status == "oserror":
                raise OSError("fixture disk failure")
            return {
                "status": CheckoutManager.prepared_status,
                "reasons": ["fixture checkout conflict"],
            }

    class Observer:
        def __init__(self, *_args):
            pass

        @staticmethod
        def observe_goal_state():
            return {}

    def fake_git(_source, *args):
        if args[:3] == ("symbolic-ref", "--short", "HEAD"):
            return "main"
        if args[:2] == ("status", "--porcelain=v1"):
            return ""
        if args[:2] == ("rev-parse", "HEAD"):
            return SOURCE_HEAD
        raise AssertionError(f"unexpected git fixture command: {args}")

    try:
        launcher.repo_root = lambda value: value
        launcher._git = fake_git
        launcher.load_committed_task = lambda *_args: {
            "id": TASK_ID,
            "task_contract_sha256": "a" * 64,
        }
        launcher.validate_decomposition_selection = lambda *_args: None
        launcher.GhIssueBackend = lambda **_values: object()
        launcher.IssueWorkflowService = lambda **_values: Service()
        launcher.DurableTaskCheckoutManager = CheckoutManager
        launcher.RealTaskObserver = Observer
        launcher._checkout_observation = lambda **_values: {}

        cases = (
            (
                0,
                "human_action_required",
                {"status": "acquired", "issue_number": 777},
                "created",
                True,
                False,
                777,
                False,
                False,
            ),
            (
                3,
                "blocked",
                {"status": "acquired", "issue_number": 777},
                "created",
                True,
                False,
                777,
                False,
                False,
            ),
            (
                3,
                "blocked",
                {"status": "blocked", "reasons": ["claim conflict"]},
                "created",
                False,
                False,
                None,
                False,
                False,
            ),
            (
                3,
                "blocked",
                {"status": "acquired", "issue_number": 777},
                "blocked",
                False,
                True,
                777,
                False,
                False,
            ),
            (
                2,
                "error",
                {"status": "acquired", "issue_number": 777},
                "oserror",
                False,
                True,
                777,
                True,
                False,
            ),
            (
                2,
                "error",
                {"status": "acquired", "issue_number": 777},
                "created",
                True,
                True,
                777,
                False,
                True,
            ),
        )
        for index, (
            expected_code,
            terminal_status,
            lease_result,
            checkout_status,
            provider_expected,
            release_expected,
            expected_issue_number,
            resumed,
            proposal_raises,
        ) in enumerate(
            cases,
            start=1,
        ):
            with tempfile.TemporaryDirectory() as text:
                root = Path(text)
                source = root / "source"
                source.mkdir()
                run_id = f"scheduler-nsc-777-decomposition-{index}"
                launcher._acquire_workflow_lease = lambda **_values: (
                    object(),
                    lease_result,
                )
                CheckoutManager.prepared_status = checkout_status
                Service.releases = []
                Service.snapshot = (
                    SimpleNamespace(issue_number=777, state=None) if resumed else None
                )
                provider_calls = []

                def run_proposal(**_values):
                    provider_calls.append(True)
                    if proposal_raises:
                        Service.snapshot = SimpleNamespace(
                            valid=True,
                            issue_number=777,
                            state=SimpleNamespace(
                                state=WorkflowState.AGENT_WORKING,
                                worker_id="decomposition-scheduler-worker",
                            ),
                        )
                        raise OSError("fixture proposal publication failure")
                    return expected_code

                launcher._run_proposal = run_proposal
                command = [
                    "--task-id",
                    TASK_ID,
                    "--source",
                    str(source),
                    "--checkout-root",
                    str(root / "checkouts"),
                    "--output-root",
                    str(root / "provider-output"),
                    "--worker-id",
                    "decomposition-scheduler-worker",
                    "--scheduler-output-root",
                    str(root / "scheduler-output"),
                    "--run-id",
                    run_id,
                    "--admission-source-head",
                    SOURCE_HEAD,
                    "--task-contract-sha256",
                    "a" * 64,
                ]
                if resumed:
                    command.extend(("--admission-issue-number", "777"))
                result = launcher.main(command)
                require(result == expected_code, str(result))
                require(bool(provider_calls) is provider_expected, str(provider_calls))
                require(bool(Service.releases) is release_expected, str(Service.releases))
                result_path = (
                    root
                    / "scheduler-output"
                    / TASK_ID
                    / run_id
                    / "run_result.json"
                )
                payload = json.loads(result_path.read_text(encoding="utf-8"))
                require(payload["terminal_status"] == terminal_status, str(payload))
                require(payload["exit_code"] == expected_code, str(payload))
                require(payload["pid"] == os.getpid(), str(payload))
                require(
                    payload["issue_number"] == expected_issue_number,
                    str(payload),
                )
    finally:
        for name, value in originals.items():
            setattr(launcher, name, value)


def test_unprovable_child_template_blocks_before_any_durable_mutation() -> None:
    """A missing child template stops a fresh decomposition before anything happens.

    The preflight runs before the workflow lease, before the durable checkout,
    and before the provider, so an unprovable template map costs one deterministic
    read and leaves no claim, no Issue transition, no checkout, and no graph
    mutation behind. This is the ordering the audit exists to guarantee; the
    remaining decomposition tests only prove the audit's verdicts.
    """

    originals = {
        name: getattr(launcher, name)
        for name in (
            "repo_root",
            "_git",
            "load_committed_task",
            "GhIssueBackend",
            "IssueWorkflowService",
            "DurableTaskCheckoutManager",
            "RealTaskObserver",
            "_acquire_workflow_lease",
            "_checkout_observation",
            "_run_proposal",
        )
    }
    parent = {
        "schema_version": "2.0",
        "id": TASK_ID,
        "contract_revision": 1,
        "contract_disposition": "active",
        "title": "Fixture decomposition parent",
        "reconciliation_key": "fixture-decomposition-parent",
        "kind": "implementation",
        "execution_scope": "needs_execution_decomposition",
        "decomposition_state": "concrete",
        "parent": "NSC-001",
        "depends_on": [],
        "exclusive_resources": ["repo-file:Assets/Fixture/Alpha.cs"],
        "acceptance_criteria": [],
        "completion_gates": [],
        "downstream_integration_obligations": [],
        "provenance": {"origin": "fixture", "gauntlet_id": "fixture-gauntlet-v1"},
        "task_contract_sha256": "a" * 64,
    }

    def fake_git(_source, *args):
        if args[:3] == ("symbolic-ref", "--short", "HEAD"):
            return "main"
        if args[:2] == ("status", "--porcelain=v1"):
            return ""
        if args[:2] == ("rev-parse", "HEAD"):
            return SOURCE_HEAD
        raise AssertionError(f"unexpected git fixture command: {args}")

    mutations: list[str] = []

    class Service:
        @staticmethod
        def find(_task_id):
            return None

        @staticmethod
        def release_decomposition_lease(**_values):
            mutations.append("release_decomposition_lease")
            return {"status": "agent_ready"}

        @staticmethod
        def publish_decomposition_handoff(**_values):
            mutations.append("publish_decomposition_handoff")

        @staticmethod
        def complete_decomposition(**_values):
            mutations.append("complete_decomposition")

    class CheckoutManager:
        def __init__(self, **values):
            self.checkout_path = Path(values["checkout_root"]) / values["task_id"]

        @staticmethod
        def expected_branch(_observation):
            return "nsc-777-decomposition-fixture"

        @staticmethod
        def prepare(_observation):
            mutations.append("checkout_prepare")
            return {"status": "created", "reasons": []}

    class Observer:
        def __init__(self, *_args):
            pass

        @staticmethod
        def observe_goal_state():
            return {}

    def acquire(**_values):
        mutations.append("acquire_workflow_lease")
        return object(), {"status": "acquired", "issue_number": 777}

    def run_proposal(**_values):
        mutations.append("run_proposal")
        return 0

    try:
        launcher.repo_root = lambda value: value
        launcher._git = fake_git
        launcher.load_committed_task = lambda *_args, **_kwargs: dict(parent)
        launcher.GhIssueBackend = lambda **_values: object()
        launcher.IssueWorkflowService = lambda **_values: Service()
        launcher.DurableTaskCheckoutManager = CheckoutManager
        launcher.RealTaskObserver = Observer
        launcher._acquire_workflow_lease = acquire
        launcher._checkout_observation = lambda **_values: {}
        launcher._run_proposal = run_proposal

        with tempfile.TemporaryDirectory() as text:
            root = Path(text)
            source = root / "source"
            (source / "Tasks").mkdir(parents=True)
            (source / "Tasks" / f"{TASK_ID}.yaml").write_text(
                json.dumps(parent, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            policy = source / VALIDATION_POLICY_RELATIVE
            policy.parent.mkdir(parents=True, exist_ok=True)
            # The parent is machine-approved and selectable, and the committed
            # template map does not carry it. That is the exact G12 shape.
            policy.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "tasks": {},
                        "decomposition_child_templates": {},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            run_id = "scheduler-nsc-777-decomposition-policy"
            result = launcher.main(
                [
                    "--task-id",
                    TASK_ID,
                    "--source",
                    str(source),
                    "--checkout-root",
                    str(root / "checkouts"),
                    "--output-root",
                    str(root / "provider-output"),
                    "--worker-id",
                    "decomposition-scheduler-worker",
                    "--scheduler-output-root",
                    str(root / "scheduler-output"),
                    "--run-id",
                    run_id,
                    "--admission-source-head",
                    SOURCE_HEAD,
                    "--task-contract-sha256",
                    "a" * 64,
                ]
            )
            require(result == 2, str(result))
            require(mutations == [], f"a durable mutation happened first: {mutations}")
            require(
                not (root / "checkouts").exists(),
                "a task checkout was created before the policy was proven",
            )
            payload = json.loads(
                (root / "scheduler-output" / TASK_ID / run_id / "run_result.json").read_text(
                    encoding="utf-8"
                )
            )
            require(payload["terminal_status"] == "error", str(payload))
            require(payload["issue_number"] is None, str(payload))
    finally:
        for name, value in originals.items():
            setattr(launcher, name, value)


def test_apply_resume_uses_historical_contract_and_skips_fresh_validation() -> None:
    current_head = "2" * 40
    old_hash = "a" * 64
    current_hash = "b" * 64
    prelease = SimpleNamespace(
        issue_number=777,
        valid=True,
        state=SimpleNamespace(
            phase=WorkflowPhase.DECOMPOSITION_APPLY,
            branch="main",
            task_contract_sha256=old_hash,
        ),
        events=(),
    )

    class Service:
        @staticmethod
        def find(_task_id):
            return prelease

    class CheckoutManager:
        def __init__(self, **values):
            self.checkout_path = Path(values["checkout_root"]) / values["task_id"]

    load_calls: list[dict] = []

    def load_task(_source, _task_id, **kwargs):
        load_calls.append(dict(kwargs))
        if kwargs:
            require(kwargs.get("commit") == SOURCE_HEAD, str(kwargs))
            require(kwargs.get("expected_sha256") == old_hash, str(kwargs))
            return {
                "id": TASK_ID,
                "task_contract_sha256": old_hash,
                "exclusive_resources": ["logical:historical-parent"],
            }
        return {
            "id": TASK_ID,
            "task_contract_sha256": current_hash,
            "exclusive_resources": [],
        }

    def fake_git(_source, *args):
        if args[:3] == ("symbolic-ref", "--short", "HEAD"):
            return "main"
        if args[:2] == ("status", "--porcelain=v1"):
            return ""
        if args[:2] == ("rev-parse", "HEAD"):
            return current_head
        raise AssertionError(f"unexpected git fixture command: {args}")

    acquired: list[dict] = []

    def acquire(**values):
        acquired.append(values)
        return object(), {"status": "acquired", "issue_number": 777}

    applied: list[dict] = []

    def apply_approved(**values):
        applied.append(values)
        return 0

    replay = SimpleNamespace(
        authorized_source_head=SOURCE_HEAD,
        inspection=SimpleNamespace(status="already_applied", reason="fixture replay"),
    )
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source = root / "source"
        source.mkdir()
        run_id = "scheduler-nsc-777-applied-replay"
        with (
            patch.object(launcher, "repo_root", side_effect=lambda value: value),
            patch.object(launcher, "_git", side_effect=fake_git),
            patch.object(launcher, "load_committed_task", side_effect=load_task),
            patch.object(
                launcher,
                "validate_decomposition_selection",
                side_effect=AssertionError(
                    "already-applied parent reached fresh decomposition validation"
                ),
            ),
            patch.object(launcher, "GhIssueBackend", return_value=object()),
            patch.object(launcher, "IssueWorkflowService", return_value=Service()),
            patch.object(launcher, "DurableTaskCheckoutManager", CheckoutManager),
            patch.object(
                launcher,
                "inspect_authorized_decomposition_replay",
                return_value=replay,
            ),
            patch.object(launcher, "_acquire_workflow_lease", side_effect=acquire),
            patch.object(
                launcher, "_apply_approved_plan", side_effect=apply_approved
            ) as apply_mock,
            patch.object(
                launcher,
                "_release_owned_decomposition_lease",
                return_value=True,
            ) as release_mock,
        ):
            result = launcher.main(
                [
                    "--task-id",
                    TASK_ID,
                    "--source",
                    str(source),
                    "--checkout-root",
                    str(root / "checkouts"),
                    "--output-root",
                    str(root / "provider-output"),
                    "--worker-id",
                    "decomposition-replay-worker",
                    "--scheduler-output-root",
                    str(root / "scheduler-output"),
                    "--run-id",
                    run_id,
                    "--admission-source-head",
                    current_head,
                    "--task-contract-sha256",
                    current_hash,
                    "--admission-issue-number",
                    "777",
                ]
            )
            retry_run_id = "scheduler-nsc-777-completion-retry"
            apply_mock.side_effect = launcher.DecompositionApplyRetryableError(
                "fixture remote-confirmed completion failure"
            )
            retry_result = launcher.main(
                [
                    "--task-id",
                    TASK_ID,
                    "--source",
                    str(source),
                    "--checkout-root",
                    str(root / "checkouts"),
                    "--output-root",
                    str(root / "provider-output"),
                    "--worker-id",
                    "decomposition-replay-worker",
                    "--scheduler-output-root",
                    str(root / "scheduler-output"),
                    "--run-id",
                    retry_run_id,
                    "--admission-source-head",
                    current_head,
                    "--task-contract-sha256",
                    current_hash,
                    "--admission-issue-number",
                    "777",
                ]
            )
        require(result == 0, str(result))
        require(retry_result == 3, str(retry_result))
        require(
            load_calls
            == [
                {},
                {"commit": SOURCE_HEAD, "expected_sha256": old_hash},
                {},
                {"commit": SOURCE_HEAD, "expected_sha256": old_hash},
            ],
            str(load_calls),
        )
        require(len(acquired) == 2, str(acquired))
        require(
            acquired[0]["task"]["task_contract_sha256"] == current_hash,
            str(acquired),
        )
        require(acquired[0]["source_head"] == current_head, str(acquired))
        require(
            acquired[0]["expected_workflow_contract_sha256"] == old_hash,
            str(acquired),
        )
        require(len(applied) == 1, str(applied))
        release_mock.assert_called_once()
        payload = json.loads(
            (
                root
                / "scheduler-output"
                / TASK_ID
                / run_id
                / "run_result.json"
            ).read_text(encoding="utf-8")
        )
        require(payload["terminal_status"] == "completed", str(payload))
        require(payload["task_contract_sha256"] == current_hash, str(payload))
        retry_payload = json.loads(
            (
                root
                / "scheduler-output"
                / TASK_ID
                / retry_run_id
                / "run_result.json"
            ).read_text(encoding="utf-8")
        )
        require(retry_payload["terminal_status"] == "blocked", str(retry_payload))
        require(retry_payload["exit_code"] == 3, str(retry_payload))


def test_codex_only_d1b1_proposal_uses_real_validation_and_truthful_handoff() -> None:
    from Pipeline.AgentRuntime.providers.fake import FakeProvider
    from TaskDecomposition.live_decomposition import run_live_decomposition
    from TaskDecomposition.tests.test_support import create_repository, decomposed_result, protected_bytes

    with tempfile.TemporaryDirectory(prefix="codex-only-decomposition-") as text:
        root = Path(text)
        source = root / "source"
        tasks = create_repository(source)
        before = protected_bytes(source)
        head = launcher._git(source, "rev-parse", "HEAD")
        args = arguments()
        args.task_id = "NSC-010"
        args.providers = "codex"
        args.provider_allowlist = ("codex",)
        args.run_id = "codex-only-proposal"
        output = root / "output"
        calls = []
        handoffs = []
        service = RecordingService()
        service.publish_decomposition_handoff = lambda **values: handoffs.append(values)

        class CodexFixture:
            provider_identifier = "openai-codex"

            def invoke(self, request, model):
                calls.append(request)
                return FakeProvider(structured_output=decomposed_result(tasks["NSC-010"])).invoke(request, model)

        def factory(provider, _source, role):
            require(provider == "codex" and role == "task_decomposer", (provider, role))
            key, configuration = launcher.provider_configuration(provider)
            return key, configuration, {"openai-codex": CodexFixture()}

        original_run = subprocess.run
        compose_calls = []

        def run(command, **kwargs):
            if command[0] == "git":
                return original_run(command, **kwargs)
            require(command[0] == "docker", str(command))
            require("codex-decompose" in command and "round-robin-decompose" not in command, str(command))
            require(not any("claude" in item for item in command), str(command))
            require("--max-calls" not in command and "--provider" in command, str(command))
            compose_calls.append(command)
            result = run_live_decomposition(
                source=source, output_root=output, task_id=args.task_id,
                provider_name="codex", run_id=args.run_id, provider_factory=factory,
                _require_physical_read_only_source=False,
            )
            require(result["run_status"] == "review_ready", str(result))
            return subprocess.CompletedProcess(command, 0)

        with patch.object(launcher.subprocess, "run", side_effect=run):
            result = launcher._run_proposal(args=args, workspace=source, output_root=output,
                                          source_head=head, service=service)
        require(result == 0 and len(compose_calls) == len(calls) == len(handoffs) == 1, str(handoffs))
        require(not service.releases and not service.completions, str(service.__dict__))
        summary = handoffs[0]["summary"]
        require("D1B.1" in summary and "Independent provider review was unavailable" in summary
                and "review_only_not_applied" in summary, summary)
        result_path = output / args.run_id / "decomposition_run_result.json"
        evidence = json.loads(result_path.read_text(encoding="utf-8"))
        require(evidence.get("independent_approver_provider") is None, str(evidence))
        require(evidence["actual_provider"] == "openai-codex" and evidence["authority"] == "review_only_not_applied", str(evidence))
        require(launcher._git(source, "rev-parse", "HEAD") == head, "proposal changed source HEAD")
        require(launcher._git(source, "status", "--porcelain=v1") == "", "proposal dirtied source")
        require(protected_bytes(source) == before, "proposal changed protected graph/canon")
        valid_run_id = args.run_id
        for index, (field, invalid) in enumerate((
            ("actual_provider", "claude-code"),
            ("authority", "applied"),
            ("independent_approver_provider", "codex"),
        )):
            args.run_id = f"codex-only-invalid-{index}"

            def forged(command, **_kwargs):
                invalid_dir = output / args.run_id
                shutil.copytree(output / valid_run_id, invalid_dir)
                tampered = {**evidence, "run_id": args.run_id, field: invalid}
                (invalid_dir / "decomposition_run_result.json").write_text(json.dumps(tampered), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0)

            with patch.object(launcher.subprocess, "run", side_effect=forged):
                rejected = launcher._run_proposal(args=args, workspace=source, output_root=output,
                                                 source_head=head, service=service)
            require(rejected == 3 and len(handoffs) == 1, f"forged {field} reached handoff")
        require(len(calls) == 1 and not service.completions, "negative check started another provider or applied graph")
        for providers in ("claude", "codex,claude"):
            try:
                launcher.build_compose_command(task_id=args.task_id, project=args.compose_project,
                                               providers=providers, max_calls=4, provider_allowlist=("codex",))
            except ValueError as exc:
                require("not in provider_allowlist" in str(exc), str(exc))
            else:
                raise AssertionError("Codex-only host accepted forbidden decomposition command")


def main() -> int:
    tests = (
        test_codex_only_d1b1_proposal_uses_real_validation_and_truthful_handoff,
        test_git_timeout_is_normalized_for_lease_and_artifact_cleanup,
        test_exact_d1c_commit_uses_subject_and_sole_authorized_parent,
        test_proposal_failure_releases_durable_lease_without_killing_scheduler,
        test_stale_authorized_plan_releases_to_fresh_decomposition,
        test_malformed_proposal_artifact_releases_durable_lease,
        test_provider_start_error_releases_durable_lease,
        test_output_observation_error_releases_durable_lease,
        test_scheduler_proposal_rejects_wrong_run_directory_and_escaped_paths,
        test_apply_artifact_error_releases_global_claim,
        test_is_ancestor_decides_real_git_ancestry_and_fails_closed,
        test_discard_unpublished_local_commit_enforces_its_single_commit_contract,
        test_unpushed_local_d1c_commit_is_retried_without_reapplying_graph,
        test_unrelated_concurrent_push_discards_local_commit_and_retries,
        test_published_d1c_commit_is_kept_when_main_advances_after_a_lost_report,
        test_rewound_origin_main_after_a_failed_push_fails_closed,
        test_compose_command_is_exact_review_only_service,
        test_scheduler_decomposition_run_writes_identity_bound_terminal_result,
        test_apply_resume_uses_historical_contract_and_skips_fresh_validation,
        test_unprovable_child_template_blocks_before_any_durable_mutation,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"host decomposition launcher tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
