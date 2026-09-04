#!/usr/bin/env python3
"""Stage 4: per-invocation claim-contention retry for generic no-TaskId dispatch.

Proves, against real disposable Git fixtures (a bare remote plus one or more
real checkouts, exactly like claim_refs_smoke_test.py, dispatch_plan_smoke_test.py,
and fresh_dispatch_smoke_test.py's production-wiring fixtures), that the
generic no-TaskId command --

- retries ONLY after ordinary Stage 1 ``claim_conflict`` (same-task or
  shared-exclusive-resource arbitration loss), never after an operational,
  invalid-state, initialization, or cleanup failure;
- rebuilds full Stage 2 authority from scratch on every retried attempt, so
  resume-first preference is re-evaluated and can win mid-retry;
- never attempts an already-contended candidate again within one invocation;
- has no arbitrary retry-count cap and terminates finitely once every
  currently safe candidate has been tried;
- never substitutes a candidate for an explicit ``-TaskId`` request;
- never retries or mutates in ``--mode observe``;
- resolves real concurrent same-task and shared-resource contention between
  independent worker processes with at most one winner per task, no
  duplicate durable Issue ownership, and no global serialization of disjoint
  work.

This module is deliberately separate from fresh_dispatch_smoke_test.py (see
the Stage 4 task brief): Stage 3's single-attempt behavior is proven there
and must remain unchanged; this file proves the Stage 4 retry loop on top.

No production GitHub Issue, claim ref, or checkout is touched: ``gh`` is
replaced by an in-memory fake and every remote is a disposable local bare
repo.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.dispatch_plan as dispatch_plan_module  # noqa: E402
import Pipeline.TaskReviewAgent.fresh_dispatch as fresh_dispatch_module  # noqa: E402
import Pipeline.TaskReviewAgent.real_workflow as real_workflow_module  # noqa: E402
import Pipeline.TaskReviewAgent.run_pipeline_agent as run_pipeline_agent_module  # noqa: E402
from Pipeline.TaskReviewAgent.claim_refs import (  # noqa: E402
    ClaimAcquisition,
    GitRefClaimClient,
)
from Pipeline.TaskReviewAgent.fresh_dispatch import (  # noqa: E402
    GENERIC_CONTENTION_RETRY_DECISIONS,
    GenericDispatchRetryResult,
    resolve_generic_dispatch_with_contention_retry,
)
from Pipeline.TaskReviewAgent.dispatch_plan import (  # noqa: E402
    build_dispatch_plan,
    evaluate_committed_fresh_candidate,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)

NAMESPACE = "refs/nsc/claims"
SHARED_RESOURCE = "unity-scene:Assets/Scenes/StageFourFixture.unity"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(
    *args: str,
    cwd: Path,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120.0,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n{result.stdout}\n{result.stderr}"
        )
    return result


def git(repo: Path, *args: str, check: bool = True) -> str:
    return run("git", "-C", str(repo), *args, cwd=repo, check=check).stdout.strip()


def make_task(task_id: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "schema_version": "2.0",
        "id": task_id,
        "title": f"Stage 4 fixture {task_id}",
        "contract_revision": 1,
        "contract_disposition": "active",
        "kind": "implementation",
        "type": "gameplay_system",
        "execution_scope": "single_agent",
        "execution_reason": "Stage 4 contention-retry fixture.",
        "decomposition_state": "concrete",
        "decomposition_reason": "Already bounded.",
        "parent": "NSC-001",
        "depends_on": [],
        "exclusive_resources": [],
        "acceptance_criteria": [],
        "completion_gates": [],
        "downstream_integration_obligations": [],
    }
    base.update(overrides)
    return base


def _taskcontrol_stub_source(states: dict[str, str]) -> str:
    return f'''from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATES = {json.dumps(states)}

def git(*args):
    return subprocess.check_output(("git", "-C", str(ROOT), *args), text=True).strip()

if sys.argv[1:] == ["validate"]:
    print("taskcontrol validate: PASS")
    raise SystemExit(0)

if len(sys.argv) == 4 and sys.argv[1] == "state" and sys.argv[3] == "--json":
    task_id = sys.argv[2]
    print(json.dumps({{
        "task_id": task_id,
        "title": "Stage 4 fixture",
        "state": STATES.get(task_id, "unknown"),
        "head_commit": git("rev-parse", "HEAD"),
        "head_tree": git("rev-parse", "HEAD^{{tree}}"),
        "selected_record_id": None,
        "findings": [],
        "dirty_worktree": False,
    }}, sort_keys=True))
    raise SystemExit(0)

if sys.argv[1:] == ["states", "--json"]:
    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{{tree}}")
    print(json.dumps([
        {{
            "task_id": task_id,
            "state": state,
            "head_commit": head,
            "head_tree": tree,
            "selected_record_id": None,
            "findings": [],
            "dirty_worktree": False,
        }}
        for task_id, state in STATES.items()
    ]))
    raise SystemExit(0)

raise SystemExit(2)
'''


def create_fixture(
    root: Path,
    *,
    tasks: dict[str, dict[str, Any]],
    states: dict[str, str],
) -> tuple[Path, Path]:
    """One bare remote plus a real controller checkout with committed
    ``Tasks/*.yaml`` contracts and a deterministic ``taskcontrol.py`` stub."""

    remote = root / "remote.git"
    seed = root / "seed"
    run("git", "init", "--bare", str(remote), cwd=root)
    # Every claim commit uses Git's canonical empty tree. Without pre-seeding
    # that shared object, simultaneous local receive-pack processes on Windows
    # can all try to migrate 4b825dc... into the bare repository and one loses
    # to an NTFS/antivirus file lock. GitHub already has this universal object;
    # the fixture must model that stable remote instead of introducing an
    # unrelated, repeatable local-filesystem flake into the contention test.
    empty_tree = run(
        "git",
        "--git-dir",
        str(remote),
        "mktree",
        cwd=root,
        input_text="",
    ).stdout.strip()
    require(
        empty_tree == "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
        f"fixture did not pre-seed Git's canonical empty tree: {empty_tree}",
    )
    run("git", "init", "-b", "main", str(seed), cwd=root)
    git(seed, "config", "user.name", "Stage 4 Fixture")
    git(seed, "config", "user.email", "stage4-fixture@example.invalid")
    (seed / "Tasks").mkdir()
    (seed / "Pipeline" / "TaskGraph").mkdir(parents=True)
    for task_id, contract in tasks.items():
        (seed / f"Tasks/{task_id}.yaml").write_text(
            json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    (seed / "Pipeline/TaskGraph/taskcontrol.py").write_text(
        _taskcontrol_stub_source(states), encoding="utf-8", newline="\n"
    )
    git(seed, "add", ".")
    git(seed, "commit", "-m", "Stage 4 fixture commit")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "main")
    run(
        "git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main", cwd=root
    )
    checkout = root / "checkout"
    run("git", "clone", str(remote), str(checkout), cwd=root)
    git(checkout, "config", "user.name", "Stage 4 Fixture")
    git(checkout, "config", "user.email", "stage4-fixture@example.invalid")
    return checkout, remote


def clone_worker(root: Path, remote: Path, name: str) -> Path:
    """A second/third/... real checkout of the SAME bare remote, standing in
    for an independent worker process."""

    checkout = root / name
    run("git", "clone", str(remote), str(checkout), cwd=root)
    git(checkout, "config", "user.name", "Stage 4 Fixture")
    git(checkout, "config", "user.email", "stage4-fixture@example.invalid")
    return checkout


# ---------------------------------------------------------------------------
# Shared in-memory `gh` fake: keyed by an explicit shared key when multiple
# real checkouts of the SAME remote must observe the SAME durable Issue
# state, exactly like several real worker processes hitting one real GitHub
# repository would.
# ---------------------------------------------------------------------------

_BACKEND_STORES: dict[str, MemoryIssueBackend] = {}
_BACKEND_LOCKS: dict[str, threading.Lock] = {}
_ROOT_ALIASES: dict[str, str] = {}


def register_shared_root(path: Path, shared_key: str) -> None:
    """Make ``path`` (a real checkout directory) observe the same fake
    durable Issue store as every other root registered under ``shared_key``
    -- normally the shared bare remote's path, so independent clones of one
    remote behave like independent workers against one real repository."""

    _ROOT_ALIASES[str(Path(path).resolve())] = shared_key


class SharedFakeGhIssueBackend:
    """No-`gh` stand-in shared, by repository root, across every construction.

    ``MemoryIssueBackend`` itself (``next_issue += 1`` etc.) is not
    thread-safe; a real GitHub repository's API IS safe under concurrent
    requests. Real Stage 4 workers are separate OS processes each with their
    own interpreter and no shared Python object, so this in-process,
    multi-thread test fixture is the one place that discrepancy would
    matter. A single lock per shared store serializes the FAKE backend the
    same way real GitHub already does, so multi-worker tests exercise
    genuine Stage 1 Git-ref contention without an unrelated fixture race.
    """

    def __init__(self, *, source_root: Path) -> None:
        resolved = str(Path(source_root).resolve())
        key = _ROOT_ALIASES.get(resolved, resolved)
        if key not in _BACKEND_STORES:
            _BACKEND_STORES[key] = MemoryIssueBackend()
            _BACKEND_LOCKS[key] = threading.Lock()
        self._inner = _BACKEND_STORES[key]
        self._lock = _BACKEND_LOCKS[key]
        self.key = key

    def list_issues(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._inner.list_issues()

    def get_comments(self, issue_number: int) -> list[dict[str, Any]]:
        with self._lock:
            return self._inner.get_comments(issue_number)

    def create_issue(self, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            return self._inner.create_issue(**kwargs)

    def update_issue(self, issue_number: int, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            return self._inner.update_issue(issue_number, **kwargs)

    def add_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        with self._lock:
            return self._inner.add_comment(issue_number, body)

    def ensure_labels(self) -> None:
        with self._lock:
            self._inner.ensure_labels()

    @classmethod
    def reset(cls) -> None:
        _BACKEND_STORES.clear()
        _BACKEND_LOCKS.clear()
        _ROOT_ALIASES.clear()

    @classmethod
    def store_for(cls, root: Path) -> MemoryIssueBackend:
        resolved = str(Path(root).resolve())
        key = _ROOT_ALIASES.get(resolved, resolved)
        return _BACKEND_STORES[key]


class PatchedGhBackend:
    """Context manager: monkeypatch every production ``GhIssueBackend``
    module binding Stage 3/4 (and ``run_pipeline_agent``'s own
    ``_managed_issue_phase`` read) actually constructs, and restore them
    after."""

    def __enter__(self) -> type[SharedFakeGhIssueBackend]:
        SharedFakeGhIssueBackend.reset()
        self._original_dispatch = dispatch_plan_module.GhIssueBackend
        self._original_workflow = real_workflow_module.GhIssueBackend
        self._original_run_pipeline_agent = run_pipeline_agent_module.GhIssueBackend
        dispatch_plan_module.GhIssueBackend = SharedFakeGhIssueBackend  # type: ignore[assignment]
        real_workflow_module.GhIssueBackend = SharedFakeGhIssueBackend  # type: ignore[assignment]
        run_pipeline_agent_module.GhIssueBackend = SharedFakeGhIssueBackend  # type: ignore[assignment]
        return SharedFakeGhIssueBackend

    def __exit__(self, *exc_info: Any) -> None:
        dispatch_plan_module.GhIssueBackend = self._original_dispatch  # type: ignore[assignment]
        real_workflow_module.GhIssueBackend = self._original_workflow  # type: ignore[assignment]
        run_pipeline_agent_module.GhIssueBackend = self._original_run_pipeline_agent  # type: ignore[assignment]
        SharedFakeGhIssueBackend.reset()


def remote_claims(remote: Path, namespace: str = NAMESPACE) -> dict[str, str]:
    result = subprocess.run(
        ("git", "ls-remote", str(remote), f"{namespace}/*"),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=120.0,
    )
    claims: dict[str, str] = {}
    for line in result.stdout.splitlines():
        oid, _, ref = line.partition("\t")
        claims[ref] = oid
    return claims


def _committed_sha(checkout: Path, task_id: str) -> str:
    contract = git(checkout, "show", f"HEAD:Tasks/{task_id}.yaml")
    return hashlib.sha256(contract.encode("utf-8")).hexdigest()


def _acquire_foreign_claim(
    *, checkout: Path, remote: Path, task_id: str, resources: list[str]
) -> None:
    """Simulate another worker already holding the Stage 1 claim ref(s)."""

    client = GitRefClaimClient(
        local_repository=checkout, remote=str(remote), namespace=NAMESPACE, worker_id="foreign-worker"
    )
    acquisition = client.acquire(
        task_id=task_id, exclusive_resources=resources, source_head=git(checkout, "rev-parse", "HEAD")
    )
    require(isinstance(acquisition, ClaimAcquisition), f"fixture setup failed to hold a foreign claim: {acquisition!r}")


def _publish_agent_ready_issue(
    *, checkout: Path, backend_cls: type[SharedFakeGhIssueBackend], task: dict[str, Any]
) -> None:
    """Make ``task`` a legitimate durable agent-ready Issue via the SAME
    production IssueWorkflowService machinery Stage 3's resume test uses --
    a real acquire -> handoff -> human-PASS round trip, not a hand-built
    fixture row."""

    task_id = task["id"]
    service = IssueWorkflowService(
        backend=backend_cls(source_root=checkout),
        task_loader=lambda selected: task | {"task_contract_sha256": _committed_sha(checkout, selected)},
        worker_id="another-worker",
    )
    acquired = service.acquire_agent_lease(
        task=task | {"task_contract_sha256": _committed_sha(checkout, task_id)},
        source_head=git(checkout, "rev-parse", "HEAD"),
        branch=f"{task_id.lower()}-task",
        checkout_path=rf"C:\NSC\NSC\{task_id}",
        planned_approach="Appeared mid-retry.",
        expected_validation="N/A.",
    )
    require(acquired["status"] == "acquired", f"fixture setup failed: {acquired}")
    service.publish_human_handoff(
        task_id=task_id,
        branch=f"{task_id.lower()}-task",
        head_commit="9" * 40,
        checkout_path=rf"C:\NSC\NSC\{task_id}",
        implementation_summary="Done.",
        completed_checks=("Pushed.",),
        human_steps=("Test in Unity.",),
        expected_result="Passes.",
    )
    service.apply_human_result(
        task_id=task_id,
        result_body=(
            "## Human validation result\n\nResult: PASS\n"
            f"Tested commit: `{'9' * 40}`\n\nCompleted steps:\n- Verified.\n"
        ),
        actor_id="cathode26",
    )


class _SelectiveRacingFactory:
    """Patch ``RealTaskReviewWorkflow.acquire_agent_lease`` so that, ONLY for
    a task_id present in ``race_actions``, the given callable runs
    immediately before the real atomic Stage 1 claim attempt -- and only
    once per task_id (each entry is consumed on first use). Every other
    task_id proceeds exactly as production would."""

    def __init__(self, *, real_cls: type, race_actions: dict[str, Callable[[], None]]) -> None:
        outer = self

        class RacingWorkflow(real_cls):  # type: ignore[misc, valid-type]
            def acquire_agent_lease(self, **kwargs: Any) -> dict[str, Any]:
                action = outer.race_actions.pop(self.task_id, None)
                if action is not None:
                    action()
                return super().acquire_agent_lease(**kwargs)

        self.cls = RacingWorkflow
        self.race_actions = dict(race_actions)


def _patch_workflow(cls: type) -> Callable[[], None]:
    original = fresh_dispatch_module.RealTaskReviewWorkflow
    fresh_dispatch_module.RealTaskReviewWorkflow = cls  # type: ignore[assignment]

    def restore() -> None:
        fresh_dispatch_module.RealTaskReviewWorkflow = original  # type: ignore[assignment]

    return restore


# ---------------------------------------------------------------------------
# A/B/C. Single-invocation contention retry: alternate success, multiple
# consecutive losses, and full pool exhaustion.
# ---------------------------------------------------------------------------


def test_single_contention_then_alternate_success() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-alternate-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-701": make_task("NSC-701"), "NSC-702": make_task("NSC-702")}
        states = {"NSC-701": "not_delivered", "NSC-702": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            racing = _SelectiveRacingFactory(
                real_cls=fresh_dispatch_module.RealTaskReviewWorkflow,
                race_actions={
                    "NSC-701": lambda: _acquire_foreign_claim(
                        checkout=checkout, remote=remote, task_id="NSC-701", resources=[]
                    ),
                },
            )
            restore = _patch_workflow(racing.cls)
            try:
                result = resolve_generic_dispatch_with_contention_retry(
                    source=checkout, worker_id="stage4-alternate-worker"
                )
            finally:
                restore()

            require(result.decision == "fresh_started", f"unexpected decision: {result.decision}")
            require(result.task_id == "NSC-702", f"did not select the alternate candidate: {result.task_id}")
            require(result.contention_attempt_count == 1, str(result.contention_attempt_count))
            require(result.contended_task_ids == ("NSC-701",), str(result.contended_task_ids))
            require(len(result.contention_history) == 1, str(result.contention_history))
            attempt = result.contention_history[0]
            require(attempt.task_id == "NSC-701", str(attempt.to_dict()))
            require(attempt.classification == "claim_conflict", str(attempt.to_dict()))
            require(attempt.attempt_index == 1, str(attempt.to_dict()))
            require(attempt.plan_source_commit is not None, str(attempt.to_dict()))
            require(
                len(store.issues) == 1,
                "exactly one durable Issue must exist after a successful alternate start",
            )
            require(not result.exhausted_after_contention, "a successful alternate start is not pool exhaustion")


def test_multiple_consecutive_contention_losses_have_no_arbitrary_cap() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-multi-loss-") as tmp:
        root = Path(tmp)
        tasks = {tid: make_task(tid) for tid in ("NSC-711", "NSC-712", "NSC-713", "NSC-714")}
        states = {tid: "not_delivered" for tid in tasks}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            racing = _SelectiveRacingFactory(
                real_cls=fresh_dispatch_module.RealTaskReviewWorkflow,
                race_actions={
                    tid: (lambda tid=tid: _acquire_foreign_claim(
                        checkout=checkout, remote=remote, task_id=tid, resources=[]
                    ))
                    for tid in ("NSC-711", "NSC-712", "NSC-713")
                },
            )
            restore = _patch_workflow(racing.cls)
            try:
                result = resolve_generic_dispatch_with_contention_retry(
                    source=checkout, worker_id="stage4-multi-loss-worker"
                )
            finally:
                restore()

            require(result.decision == "fresh_started", f"unexpected decision: {result.decision}")
            require(result.task_id == "NSC-714", f"unexpected winner: {result.task_id}")
            require(result.contention_attempt_count == 3, str(result.contention_attempt_count))
            require(
                result.contended_task_ids == ("NSC-711", "NSC-712", "NSC-713"),
                str(result.contended_task_ids),
            )
            require(
                [attempt.task_id for attempt in result.contention_history]
                == ["NSC-711", "NSC-712", "NSC-713"],
                str([attempt.to_dict() for attempt in result.contention_history]),
            )
            require(
                [attempt.attempt_index for attempt in result.contention_history] == [1, 2, 3],
                str([attempt.to_dict() for attempt in result.contention_history]),
            )
            require(len(store.issues) == 1, "exactly one durable Issue must exist after the eventual win")


def test_all_candidates_contended_terminates_normally_with_no_infinite_loop() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-exhausted-") as tmp:
        root = Path(tmp)
        tasks = {tid: make_task(tid) for tid in ("NSC-721", "NSC-722", "NSC-723")}
        states = {tid: "not_delivered" for tid in tasks}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            racing = _SelectiveRacingFactory(
                real_cls=fresh_dispatch_module.RealTaskReviewWorkflow,
                race_actions={
                    tid: (lambda tid=tid: _acquire_foreign_claim(
                        checkout=checkout, remote=remote, task_id=tid, resources=[]
                    ))
                    for tid in tasks
                },
            )
            restore = _patch_workflow(racing.cls)
            try:
                result = resolve_generic_dispatch_with_contention_retry(
                    source=checkout, worker_id="stage4-exhausted-worker"
                )
            finally:
                restore()

            require(result.decision == "no_safe_work", f"unexpected decision: {result.decision}")
            require(result.task_id is None, str(result.task_id))
            require(result.contention_attempt_count == 3, str(result.contention_attempt_count))
            require(
                result.contended_task_ids == ("NSC-721", "NSC-722", "NSC-723"),
                str(result.contended_task_ids),
            )
            require(result.exhausted_after_contention, "pool exhaustion after contention must be flagged")
            require(store.issues == {}, "exhausted contention must never leave a partial durable Issue")
            require(not racing.race_actions, "not every seeded contention attempt actually fired")


# ---------------------------------------------------------------------------
# D. Resume-first is invariant on every refreshed plan, not just the first.
# ---------------------------------------------------------------------------


def test_resume_appearing_mid_retry_beats_another_fresh_candidate() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-resume-mid-retry-") as tmp:
        root = Path(tmp)
        tasks = {
            "NSC-731": make_task("NSC-731"),
            "NSC-732": make_task("NSC-732"),
            "NSC-750": make_task("NSC-750"),
        }
        states = {"NSC-731": "not_delivered", "NSC-732": "not_delivered", "NSC-750": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner

            def race_and_surface_resume() -> None:
                _acquire_foreign_claim(checkout=checkout, remote=remote, task_id="NSC-731", resources=[])
                _publish_agent_ready_issue(checkout=checkout, backend_cls=backend_cls, task=tasks["NSC-750"])

            racing = _SelectiveRacingFactory(
                real_cls=fresh_dispatch_module.RealTaskReviewWorkflow,
                race_actions={"NSC-731": race_and_surface_resume},
            )
            restore = _patch_workflow(racing.cls)
            try:
                result = resolve_generic_dispatch_with_contention_retry(
                    source=checkout, worker_id="stage4-resume-mid-retry-worker"
                )
            finally:
                restore()

            require(result.decision == "resume_existing", f"resume did not beat a fresh candidate mid-retry: {result.decision}")
            require(result.task_id == "NSC-750", f"wrong resume target: {result.task_id}")
            require(result.contention_attempt_count == 1, str(result.contention_attempt_count))
            require(result.contended_task_ids == ("NSC-731",), str(result.contended_task_ids))
            # NSC-732 was a perfectly safe fresh candidate; resume must still
            # have won over it, and no fresh Issue was created for it.
            require(len(store.issues) == 1, "a fresh candidate was started despite a legitimate mid-retry resume")


# ---------------------------------------------------------------------------
# E. Explicit -TaskId never substitutes, with or without contention elsewhere.
# ---------------------------------------------------------------------------


def test_explicit_task_id_never_substitutes_even_under_contention() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-explicit-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-741": make_task("NSC-741"), "NSC-742": make_task("NSC-742")}
        states = {"NSC-741": "not_delivered", "NSC-742": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            # A foreign worker already holds NSC-741's claim -- explicit
            # admission for NSC-741 must fail AS NSC-741, never fall through
            # to NSC-742 even though NSC-742 is a perfectly safe alternative.
            _acquire_foreign_claim(checkout=checkout, remote=remote, task_id="NSC-741", resources=[])

            evaluation = evaluate_committed_fresh_candidate(
                source=checkout, task_id="NSC-741", worker_id="stage4-explicit-worker"
            )
            require(not evaluation.eligible, "an actively-claimed explicit task was accepted as fresh work")
            require(evaluation.task_id == "NSC-741", "a blocked explicit task's own id must be reported")
            require(
                "active_stage1_task_claim" in evaluation.reason_codes,
                str(evaluation.reason_codes),
            )

            exit_code = run_pipeline_agent_module.main(
                [
                    "--source", str(checkout),
                    "--worker-id", "stage4-explicit-worker",
                    "--task-id", "NSC-741",
                ]
            )
            require(exit_code == 2, f"a blocked explicit task must fail closed, not silently succeed: {exit_code}")
            require(store.issues == {}, "explicit admission must never mutate before it is admitted")

            # The generic no-TaskId command, in the SAME contended fixture,
            # is free to select the alternative -- proving the exclusion is
            # a property of retry, not of explicit-task admission being
            # relaxed.
            generic_result = resolve_generic_dispatch_with_contention_retry(
                source=checkout, worker_id="stage4-generic-alt-worker"
            )
            require(generic_result.decision == "fresh_started", str(generic_result.decision))
            require(generic_result.task_id == "NSC-742", str(generic_result.task_id))


# ---------------------------------------------------------------------------
# F. Observe mode never retries or mutates, generic or explicit.
# ---------------------------------------------------------------------------


def test_generic_and_explicit_observe_never_retry_or_mutate() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-observe-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-751": make_task("NSC-751")}
        states = {"NSC-751": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner

            def _forbidden(*args: Any, **kwargs: Any) -> GenericDispatchRetryResult:
                raise AssertionError("observe mode must never call the Stage 4 retry resolver")

            original = run_pipeline_agent_module.resolve_generic_dispatch_with_contention_retry
            run_pipeline_agent_module.resolve_generic_dispatch_with_contention_retry = _forbidden  # type: ignore[assignment]
            try:
                exit_code = run_pipeline_agent_module.main(
                    ["--source", str(checkout), "--worker-id", "stage4-observe-worker", "--mode", "observe"]
                )
                require(exit_code == 0, f"generic observe mode failed: {exit_code}")

                exit_code = run_pipeline_agent_module.main(
                    [
                        "--source", str(checkout),
                        "--worker-id", "stage4-observe-explicit-worker",
                        "--mode", "observe",
                        "--task-id", "NSC-751",
                    ]
                )
                require(exit_code == 0, f"explicit observe mode failed: {exit_code}")
            finally:
                run_pipeline_agent_module.resolve_generic_dispatch_with_contention_retry = original  # type: ignore[assignment]

            require(store.issues == {}, "observe mode mutated the durable Issue backend")
            require(remote_claims(remote) == {}, "observe mode created a Stage 1 claim ref")


# ---------------------------------------------------------------------------
# G/H/I/J. Terminal (non-retryable) outcomes stay terminal.
# ---------------------------------------------------------------------------


def test_claim_operational_failure_is_terminal_not_retried() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-operational-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-761": make_task("NSC-761"), "NSC-762": make_task("NSC-762")}
        states = {"NSC-761": "not_delivered", "NSC-762": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        hook = remote / "hooks" / "pre-receive"
        hook.write_text(
            "#!/bin/sh\necho 'claims are administratively refused' >&2\nexit 1\n",
            encoding="utf-8",
            newline="\n",
        )
        hook.chmod(0o755)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            result = resolve_generic_dispatch_with_contention_retry(
                source=checkout, worker_id="stage4-operational-worker"
            )
            require(
                result.decision == "claim_operational_error",
                f"an operational push rejection was misclassified: {result.decision}",
            )
            require(result.contention_attempt_count == 0, "an operational failure must never be retried")
            require(result.contended_task_ids == (), str(result.contended_task_ids))
            require(store.issues == {}, "an operational claim failure still mutated the durable Issue")


def test_issue_initialization_failure_is_terminal_not_retried() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-init-failure-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-763": make_task("NSC-763"), "NSC-764": make_task("NSC-764")}
        states = {"NSC-763": "not_delivered", "NSC-764": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner

            def failing_ensure_labels() -> None:
                from Pipeline.TaskReviewAgent.issue_workflow_store import IssueWorkflowStoreError

                raise IssueWorkflowStoreError("synthetic GitHub label API outage")

            store.ensure_labels = failing_ensure_labels  # type: ignore[assignment]

            result = resolve_generic_dispatch_with_contention_retry(
                source=checkout, worker_id="stage4-init-failure-worker"
            )
            require(
                result.decision == "issue_initialization_blocked",
                f"unexpected decision: {result.decision}",
            )
            require(result.contention_attempt_count == 0, "an initialization failure must never be retried")
            require(store.issues == {}, "a failed initialization must not leave a partial Issue")


def test_cleanup_required_after_verified_lease_is_terminal_not_retried() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-cleanup-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-765": make_task("NSC-765", exclusive_resources=[SHARED_RESOURCE])}
        states = {"NSC-765": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        worker_b_repo = root / "worker-b"
        run("git", "clone", str(remote), str(worker_b_repo), cwd=root)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            real_create_issue = store.create_issue

            def sabotaging_create_issue(**kwargs: Any) -> dict[str, Any]:
                issue = real_create_issue(**kwargs)
                held = remote_claims(remote)
                run(
                    "git",
                    "push",
                    str(remote),
                    *(f":{ref}" for ref in sorted(held)),
                    cwd=worker_b_repo,
                )
                saboteur = GitRefClaimClient(
                    local_repository=worker_b_repo,
                    remote=str(remote),
                    namespace=NAMESPACE,
                    worker_id="worker-b",
                )
                reclaimed = saboteur.acquire(
                    task_id="NSC-765",
                    exclusive_resources=[SHARED_RESOURCE],
                    source_head=git(worker_b_repo, "rev-parse", "HEAD"),
                )
                require(isinstance(reclaimed, ClaimAcquisition), f"sabotage reclaim failed: {reclaimed!r}")
                return issue

            store.create_issue = sabotaging_create_issue  # type: ignore[assignment]

            result = resolve_generic_dispatch_with_contention_retry(
                source=checkout, worker_id="stage4-cleanup-worker"
            )
            require(
                result.decision == "lease_acquired_claim_cleanup_required",
                f"a cleanup failure returned an ordinary outcome: {result.decision}",
            )
            require(result.contention_attempt_count == 0, "a cleanup-required outcome must never be retried")
            require(
                (result.lease_result or {}).get("issue_result", {}).get("status") == "acquired",
                f"the acquired durable lease fact was lost: {result.lease_result}",
            )


def test_head_drift_is_terminal_not_retried() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-head-drift-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-766": make_task("NSC-766"), "NSC-767": make_task("NSC-767")}
        states = {"NSC-766": "not_delivered", "NSC-767": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            real_plan = fresh_dispatch_module.build_dispatch_plan

            def stale_plan(*args: Any, **kwargs: Any) -> Any:
                plan = real_plan(*args, **kwargs)
                import dataclasses

                return dataclasses.replace(plan, source_commit="0" * 40)

            fresh_dispatch_module.build_dispatch_plan = stale_plan  # type: ignore[assignment]
            try:
                result = resolve_generic_dispatch_with_contention_retry(
                    source=checkout, worker_id="stage4-drift-worker"
                )
            finally:
                fresh_dispatch_module.build_dispatch_plan = real_plan  # type: ignore[assignment]

            require(result.decision == "blocked_invalid_state", f"unexpected decision: {result.decision}")
            require(result.contention_attempt_count == 0, "HEAD drift must never be retried")
            require(store.issues == {}, "a stale plan still mutated the durable Issue")
            require(remote_claims(remote) == {}, "a stale plan still created a claim ref")


# ---------------------------------------------------------------------------
# Invariant guard: a refreshed plan re-selecting an already-excluded
# candidate is an internal contract violation, not another retry.
# ---------------------------------------------------------------------------


def test_reselecting_an_excluded_candidate_fails_closed_instead_of_looping() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-invariant-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-768": make_task("NSC-768")}
        states = {"NSC-768": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner

            from Pipeline.TaskReviewAgent.fresh_dispatch import GenericDispatchResult

            call_count = {"n": 0}
            real_single_attempt = fresh_dispatch_module.resolve_generic_dispatch

            def broken_single_attempt(*args: Any, **kwargs: Any) -> GenericDispatchResult:
                # Simulate a broken exclusion boundary: report claim_conflict
                # on the SAME task every time, regardless of the
                # excluded_task_ids passed in. Deliberately never calls
                # through to real Git/Issue machinery, so any durable Issue
                # created below can only be attributed to this loop failing
                # to fail closed -- never to unrelated fixture mutation.
                call_count["n"] += 1
                return GenericDispatchResult(
                    decision="claim_conflict",
                    task_id="NSC-768",
                    plan={"source_commit": git(checkout, "rev-parse", "HEAD")},
                )

            fresh_dispatch_module.resolve_generic_dispatch = broken_single_attempt  # type: ignore[assignment]
            try:
                result = resolve_generic_dispatch_with_contention_retry(
                    source=checkout, worker_id="stage4-invariant-worker"
                )
            finally:
                fresh_dispatch_module.resolve_generic_dispatch = real_single_attempt  # type: ignore[assignment]

            require(
                result.decision == "blocked_invalid_state",
                f"a re-selected already-excluded candidate did not fail closed: {result.decision}",
            )
            require(call_count["n"] == 2, f"the loop did not terminate after re-selection: {call_count['n']} calls")
            require(store.issues == {}, "a broken exclusion boundary still mutated the durable Issue")


# ---------------------------------------------------------------------------
# K/L. Real concurrent same-task and shared-resource contention between
# independent worker processes (real Git ref pushes, real threads).
# ---------------------------------------------------------------------------


def _run_concurrently(
    actions: list[Callable[[], Any]],
) -> tuple[list[Any], list[BaseException | None]]:
    barrier = threading.Barrier(len(actions))
    results: list[Any] = [None] * len(actions)
    errors: list[BaseException | None] = [None] * len(actions)

    def runner(index: int, action: Callable[[], Any]) -> None:
        try:
            barrier.wait(timeout=60)
            results[index] = action()
        except BaseException as exc:  # surfaced by the caller
            errors[index] = exc

    threads = [threading.Thread(target=runner, args=(i, action)) for i, action in enumerate(actions)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=180)
    for thread in threads:
        require(not thread.is_alive(), "a worker thread did not terminate (possible deadlock)")
    for error in errors:
        if error is not None:
            raise error
    return results, errors


def test_real_same_task_claim_contention_admits_at_most_one_winner() -> None:
    for attempt in range(3):
        with tempfile.TemporaryDirectory(prefix=f"nsc-stage4-real-race-{attempt}-") as tmp:
            root = Path(tmp)
            tasks = {tid: make_task(tid) for tid in ("NSC-770", "NSC-771", "NSC-772", "NSC-773")}
            states = {tid: "not_delivered" for tid in tasks}
            checkout_a, remote = create_fixture(root, tasks=tasks, states=states)
            checkout_b = clone_worker(root, remote, "worker-b")
            with PatchedGhBackend() as backend_cls:
                register_shared_root(checkout_a, str(remote))
                register_shared_root(checkout_b, str(remote))
                store = backend_cls(source_root=checkout_a)._inner

                results, _errors = _run_concurrently(
                    [
                        lambda: resolve_generic_dispatch_with_contention_retry(
                            source=checkout_a, worker_id="stage4-real-race-worker-a"
                        ),
                        lambda: resolve_generic_dispatch_with_contention_retry(
                            source=checkout_b, worker_id="stage4-real-race-worker-b"
                        ),
                    ]
                )

                for result in results:
                    # With threads released by a single barrier, a worker can
                    # win an already-released Stage 1 claim ref (the earlier
                    # winner released it after its OWN durable Issue was
                    # created) and only then discover the durable Issue is
                    # already agent_working for someone else. That TOCTOU
                    # window is real, but IssueWorkflowService now reports it
                    # as the positively-typed BLOCKED_KIND_DURABLE_OWNERSHIP_
                    # BY_OTHER, which Stage 3 maps to ordinary claim_conflict
                    # and Stage 4 retries past -- so this real race must
                    # settle as fresh_started or no_safe_work, never the
                    # terminal issue_initialization_blocked an unsafe/invalid
                    # block would produce.
                    require(
                        result.decision in ("fresh_started", "no_safe_work"),
                        f"unexpected real-contention decision: {result.decision}; reasons={result.reasons}",
                    )
                started = [r for r in results if r.decision == "fresh_started"]
                started_task_ids = [r.task_id for r in started]
                require(
                    len(started_task_ids) == len(set(started_task_ids)),
                    f"two workers both won the same task_id: {started_task_ids}",
                )
                require(remote_claims(remote) == {}, "a Stage 1 claim ref leaked after real contention resolved")
                require(
                    len(store.issues) == len(started),
                    "durable Issue count must match exactly the number of real winners (no duplicate ownership)",
                )
                if started:
                    return
    raise AssertionError("neither concurrent worker acquired any task across repeated real-race attempts")


def test_real_shared_resource_contention_lets_loser_acquire_disjoint_work() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-real-resource-") as tmp:
        root = Path(tmp)
        tasks = {
            "NSC-780": make_task("NSC-780", exclusive_resources=[SHARED_RESOURCE]),
            "NSC-781": make_task("NSC-781"),
        }
        states = {"NSC-780": "not_delivered", "NSC-781": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            # A real foreign worker wins the shared exclusive resource (via
            # a real Git ref push) for an unrelated task RIGHT AS NSC-780's
            # own atomic claim attempt happens -- timed like
            # fresh_dispatch_smoke_test.py's shared-resource test, so this
            # is a genuine Stage 3 claim_conflict Stage 4 must retry past,
            # not something Stage 2's read-only pre-filter already excluded
            # before the first plan was even built.
            racing = _SelectiveRacingFactory(
                real_cls=fresh_dispatch_module.RealTaskReviewWorkflow,
                race_actions={
                    "NSC-780": lambda: _acquire_foreign_claim(
                        checkout=checkout, remote=remote, task_id="NSC-999", resources=[SHARED_RESOURCE]
                    ),
                },
            )
            restore = _patch_workflow(racing.cls)
            try:
                result = resolve_generic_dispatch_with_contention_retry(
                    source=checkout, worker_id="stage4-real-resource-worker"
                )
            finally:
                restore()

            require(result.decision == "fresh_started", f"unexpected decision: {result.decision}")
            require(result.task_id == "NSC-781", f"loser did not acquire the disjoint candidate: {result.task_id}")
            require(result.contention_attempt_count == 1, str(result.contention_attempt_count))
            require(result.contended_task_ids == ("NSC-780",), str(result.contended_task_ids))
            require(len(store.issues) == 1, "exactly one durable Issue must exist")


# ---------------------------------------------------------------------------
# M. Disjoint work is not globally serialized: independent workers with
# independent candidates both make progress concurrently.
# ---------------------------------------------------------------------------


def test_disjoint_concurrency_is_not_globally_serialized() -> None:
    # Stage 2 ranks the fresh-candidate pool deterministically, so BOTH
    # workers can initially target the SAME numerically-first candidate
    # before Stage 4's exclusion cascades the loser onto the other disjoint
    # candidate. IssueWorkflowService's typed BLOCKED_KIND_DURABLE_OWNERSHIP_
    # BY_OTHER (see issue_workflow_store.py) makes that cascade deterministic
    # instead of sometimes terminating early, but a genuinely simultaneous
    # atomic push on the SAME claim ref can still legally produce a
    # zero-winner "transient_transaction_contention" (see claim_refs.py's
    # module docstring) -- unavoidable real Git-transaction timing, not the
    # production defect this repair fixed. The bounded rerun exists only for
    # that remaining platform-level timing case.
    for attempt in range(5):
        with tempfile.TemporaryDirectory(prefix=f"nsc-stage4-disjoint-{attempt}-") as tmp:
            root = Path(tmp)
            tasks = {
                "NSC-790": make_task("NSC-790", exclusive_resources=["unity-scene:A.unity"]),
                "NSC-791": make_task("NSC-791", exclusive_resources=["unity-scene:B.unity"]),
            }
            states = {"NSC-790": "not_delivered", "NSC-791": "not_delivered"}
            checkout_a, remote = create_fixture(root, tasks=tasks, states=states)
            checkout_b = clone_worker(root, remote, "worker-b")
            with PatchedGhBackend() as backend_cls:
                register_shared_root(checkout_a, str(remote))
                register_shared_root(checkout_b, str(remote))
                store = backend_cls(source_root=checkout_a)._inner

                results, _errors = _run_concurrently(
                    [
                        lambda: resolve_generic_dispatch_with_contention_retry(
                            source=checkout_a, worker_id="stage4-disjoint-worker-a"
                        ),
                        lambda: resolve_generic_dispatch_with_contention_retry(
                            source=checkout_b, worker_id="stage4-disjoint-worker-b"
                        ),
                    ]
                )

                for result in results:
                    require(
                        result.decision in ("fresh_started", "no_safe_work"),
                        "disjoint concurrency must terminate as an ordinary dispatch "
                        f"outcome, never an unsafe block: {result.decision}; reasons={result.reasons}",
                    )
                started = [r for r in results if r.decision == "fresh_started"]
                started_task_ids = [r.task_id for r in started]
                require(
                    len(started_task_ids) == len(set(started_task_ids)),
                    f"two workers both won the same task_id: {started_task_ids}",
                )
                require(
                    len(store.issues) == len(started),
                    "durable Issue count must match exactly the number of real winners "
                    "(no duplicate durable ownership)",
                )
                require(
                    remote_claims(remote) == {},
                    "a Stage 1 claim ref leaked after disjoint concurrency",
                )
                if len(started) == 2:
                    require(
                        set(started_task_ids) == {"NSC-790", "NSC-791"},
                        f"two disjoint candidates did not both get started: {started_task_ids}",
                    )
                    return
    raise AssertionError(
        "disjoint concurrency never let both independent workers each start their own "
        "disjoint task across repeated real-race attempts"
    )


# ---------------------------------------------------------------------------
# N. No duplicate authoritative Issue for one task under real contention.
# ---------------------------------------------------------------------------


def test_no_duplicate_authoritative_issue_when_only_one_candidate_exists() -> None:
    for attempt in range(5):
        with tempfile.TemporaryDirectory(prefix=f"nsc-stage4-no-dup-{attempt}-") as tmp:
            root = Path(tmp)
            tasks = {"NSC-795": make_task("NSC-795")}
            states = {"NSC-795": "not_delivered"}
            checkout_a, remote = create_fixture(root, tasks=tasks, states=states)
            checkout_b = clone_worker(root, remote, "worker-b")
            with PatchedGhBackend() as backend_cls:
                register_shared_root(checkout_a, str(remote))
                register_shared_root(checkout_b, str(remote))
                store = backend_cls(source_root=checkout_a)._inner

                results, _errors = _run_concurrently(
                    [
                        lambda: resolve_generic_dispatch_with_contention_retry(
                            source=checkout_a, worker_id="stage4-no-dup-worker-a"
                        ),
                        lambda: resolve_generic_dispatch_with_contention_retry(
                            source=checkout_b, worker_id="stage4-no-dup-worker-b"
                        ),
                    ]
                )
                started = [r for r in results if r.decision == "fresh_started"]
                require(len(started) <= 1, f"two workers both started the ONE candidate: {[r.task_id for r in started]}")
                require(len(store.issues) == len(started), "durable Issue count diverged from real winner count")
                if len(started) == 1:
                    require(remote_claims(remote) == {}, "a claim ref leaked after the single-candidate race resolved")
                    return
    raise AssertionError("neither worker ever won the single candidate across repeated real-race attempts")


# ---------------------------------------------------------------------------
# Multi-worker stress test (5 workers: fast and deterministic enough for
# routine CI; 10 is exercised by the larger Gauntlet separately).
# ---------------------------------------------------------------------------

STRESS_WORKER_COUNT = 5


def test_multi_worker_stress_no_duplicate_winners_no_leaks_no_hang() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage4-stress-") as tmp:
        root = Path(tmp)
        task_ids = [f"NSC-{800 + i}" for i in range(STRESS_WORKER_COUNT)]
        tasks = {tid: make_task(tid) for tid in task_ids}
        states = {tid: "not_delivered" for tid in task_ids}
        checkout_a, remote = create_fixture(root, tasks=tasks, states=states)
        checkouts = [checkout_a] + [
            clone_worker(root, remote, f"worker-{i}") for i in range(1, STRESS_WORKER_COUNT)
        ]
        with PatchedGhBackend() as backend_cls:
            for checkout in checkouts:
                register_shared_root(checkout, str(remote))
            store = backend_cls(source_root=checkout_a)._inner

            actions = [
                (lambda checkout=checkout, index=index: resolve_generic_dispatch_with_contention_retry(
                    source=checkout, worker_id=f"stage4-stress-worker-{index}"
                ))
                for index, checkout in enumerate(checkouts)
            ]
            results, _errors = _run_concurrently(actions)

            for result in results:
                require(
                    result.decision in GENERIC_CONTENTION_RETRY_DECISIONS,
                    f"stress worker returned an unsupported decision: {result.decision}",
                )
                # blocked_invalid_state / claim_operational_error /
                # lease_acquired_claim_cleanup_required indicate a real
                # infrastructure or invariant bug and must never occur under
                # ordinary contention. issue_initialization_blocked must also
                # never occur here: with STRESS_WORKER_COUNT threads released
                # by one barrier, a worker can win an already-released Stage 1
                # claim ref and only then discover the durable Issue was
                # already taken by a faster worker, but IssueWorkflowService
                # now reports that TOCTOU as the positively-typed
                # BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER, which Stage 3 maps
                # to ordinary claim_conflict and Stage 4 retries past.
                require(
                    result.decision not in (
                        "blocked_invalid_state",
                        "claim_operational_error",
                        "lease_acquired_claim_cleanup_required",
                        "issue_initialization_blocked",
                    ),
                    f"stress worker hit an infrastructure failure under ordinary contention: "
                    f"{result.decision}; reasons={result.reasons}",
                )

            started = [r for r in results if r.decision == "fresh_started"]
            started_task_ids = [r.task_id for r in started]
            require(
                len(started_task_ids) == len(set(started_task_ids)),
                f"duplicate task winners across {STRESS_WORKER_COUNT} workers: {started_task_ids}",
            )
            require(
                len(started) >= 2,
                f"expected multiple workers to acquire distinct useful tasks, got: {started_task_ids}",
            )
            require(
                len(store.issues) == len(started),
                "durable Issue count must match exactly the number of real winners",
            )
            require(remote_claims(remote) == {}, "a Stage 1 claim ref leaked after the stress race")

            total_contention_attempts = sum(r.contention_attempt_count for r in results)
            print(
                f"    (stress: {STRESS_WORKER_COUNT} workers, {len(started)} winners, "
                f"{total_contention_attempts} total contention attempts, 0 leaked claims)"
            )


def main() -> int:
    tests = (
        test_single_contention_then_alternate_success,
        test_multiple_consecutive_contention_losses_have_no_arbitrary_cap,
        test_all_candidates_contended_terminates_normally_with_no_infinite_loop,
        test_resume_appearing_mid_retry_beats_another_fresh_candidate,
        test_explicit_task_id_never_substitutes_even_under_contention,
        test_generic_and_explicit_observe_never_retry_or_mutate,
        test_claim_operational_failure_is_terminal_not_retried,
        test_issue_initialization_failure_is_terminal_not_retried,
        test_cleanup_required_after_verified_lease_is_terminal_not_retried,
        test_head_drift_is_terminal_not_retried,
        test_reselecting_an_excluded_candidate_fails_closed_instead_of_looping,
        test_real_same_task_claim_contention_admits_at_most_one_winner,
        test_real_shared_resource_contention_lets_loser_acquire_disjoint_work,
        test_disjoint_concurrency_is_not_globally_serialized,
        test_no_duplicate_authoritative_issue_when_only_one_candidate_exists,
        test_multi_worker_stress_no_duplicate_winners_no_leaks_no_hang,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Stage 4 contention-retry tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
