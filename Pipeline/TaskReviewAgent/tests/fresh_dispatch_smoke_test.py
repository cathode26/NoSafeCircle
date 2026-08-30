#!/usr/bin/env python3
"""Stage 3: crossing exactly one mutation boundary for generic no-TaskId dispatch.

Proves, against real disposable Git fixtures (a bare remote plus a checkout,
exactly like claim_refs_smoke_test.py and dispatch_plan_smoke_test.py's
production-wiring fixture), that:

- an existing actionable durable Issue always wins over fresh planning;
- a fresh candidate is selected, atomically claimed, and durably leased
  through exactly one mutation boundary, with the Stage 1 claim strictly
  preceding any Issue mutation and released only after the durable lease is
  re-read and verified;
- a lost claim race or an Issue-initialization failure is a normal typed
  result, never a substituted candidate and never Stage 4 retry;
- explicit fresh-TaskId admission is gated by the identical Stage 2 kernel
  generic dispatch uses, while a legitimate resume bypasses that gate
  entirely;
- the generic no-TaskId command in ``--mode observe`` never mutates.

No production GitHub Issue, claim ref, or checkout is touched: ``gh`` is
replaced by an in-memory fake and the remote is a disposable local bare repo.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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
    task_claim_ref,
)
from Pipeline.TaskReviewAgent.dispatch_plan import (  # noqa: E402
    build_dispatch_plan,
    evaluate_committed_fresh_candidate,
)
from Pipeline.TaskReviewAgent.dispatch_policy import load_dispatch_policy  # noqa: E402
from Pipeline.TaskReviewAgent.fresh_dispatch import (  # noqa: E402
    GENERIC_DISPATCH_DECISIONS,
    resolve_generic_dispatch,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import MemoryIssueBackend  # noqa: E402

NAMESPACE = "refs/nsc/claims"
SHARED_RESOURCE = "unity-scene:Assets/Scenes/StageThreeFixture.unity"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
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
        "title": f"Stage 3 fixture {task_id}",
        "contract_revision": 1,
        "contract_disposition": "active",
        "kind": "implementation",
        "type": "gameplay_system",
        "execution_scope": "single_agent",
        "execution_reason": "Stage 3 fresh-dispatch fixture.",
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
        "title": "Stage 3 fixture",
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
    run("git", "init", "-b", "main", str(seed), cwd=root)
    git(seed, "config", "user.name", "Stage 3 Fixture")
    git(seed, "config", "user.email", "stage3-fixture@example.invalid")
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
    git(seed, "commit", "-m", "Stage 3 fixture commit")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "main")
    run(
        "git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main", cwd=root
    )
    checkout = root / "checkout"
    run("git", "clone", str(remote), str(checkout), cwd=root)
    git(checkout, "config", "user.name", "Stage 3 Fixture")
    git(checkout, "config", "user.email", "stage3-fixture@example.invalid")
    return checkout, remote


_BACKEND_STORES: dict[str, MemoryIssueBackend] = {}


class SharedFakeGhIssueBackend:
    """No-`gh` stand-in shared, by repository root, across every construction.

    Stage 2 planning (``dispatch_plan.GhIssueBackend``) and Stage 3's own
    ``RealTaskReviewWorkflow`` (``real_workflow.GhIssueBackend``) each
    construct their own backend instance; keying the in-memory store by
    resolved ``source_root`` lets both observe the SAME Issue state, exactly
    like the real authenticated `gh` CLI would for one repository.
    """

    def __init__(self, *, source_root: Path) -> None:
        key = str(Path(source_root).resolve())
        if key not in _BACKEND_STORES:
            _BACKEND_STORES[key] = MemoryIssueBackend()
        self._inner = _BACKEND_STORES[key]
        self.key = key

    def list_issues(self) -> list[dict[str, Any]]:
        return self._inner.list_issues()

    def get_comments(self, issue_number: int) -> list[dict[str, Any]]:
        return self._inner.get_comments(issue_number)

    def create_issue(self, **kwargs: Any) -> dict[str, Any]:
        return self._inner.create_issue(**kwargs)

    def update_issue(self, issue_number: int, **kwargs: Any) -> dict[str, Any]:
        return self._inner.update_issue(issue_number, **kwargs)

    def add_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        return self._inner.add_comment(issue_number, body)

    def ensure_labels(self) -> None:
        self._inner.ensure_labels()

    @classmethod
    def reset(cls) -> None:
        _BACKEND_STORES.clear()

    @classmethod
    def store_for(cls, root: Path) -> MemoryIssueBackend:
        return _BACKEND_STORES[str(Path(root).resolve())]


class PatchedGhBackend:
    """Context manager: monkeypatch every production ``GhIssueBackend``
    module binding Stage 3 (and ``run_pipeline_agent``'s own
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


# ---------------------------------------------------------------------------
# 1/3/16/22. Resume-first, exact selection, no_safe_work, disabled autonomy.
# ---------------------------------------------------------------------------


def test_resume_beats_fresh_and_uses_exact_stage2_selection() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-resume-") as tmp:
        root = Path(tmp)
        tasks = {
            "NSC-601": make_task("NSC-601"),
            "NSC-602": make_task("NSC-602"),
        }
        states = {"NSC-601": "not_delivered", "NSC-602": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            plan_only = build_dispatch_plan(source=checkout, worker_id="stage3-fixture")
            require(plan_only.decision == "fresh_candidate", str(plan_only.decision))
            require(plan_only.selected_fresh_candidate["task_id"] == "NSC-601", "wrong Stage 2 selection")

            # An existing durable agent-ready Issue for the OTHER task must
            # win over the fresh candidate Stage 2 would otherwise select.
            from Pipeline.TaskReviewAgent.issue_workflow_store import IssueWorkflowService

            store = backend_cls.store_for(checkout)
            resumable = IssueWorkflowService(
                backend=backend_cls(source_root=checkout),
                task_loader=lambda task_id: tasks[task_id] | {"task_contract_sha256": _committed_sha(checkout, task_id)},
                worker_id="another-worker",
            )
            acquired = resumable.acquire_agent_lease(
                task=tasks["NSC-602"] | {"task_contract_sha256": _committed_sha(checkout, "NSC-602")},
                source_head=git(checkout, "rev-parse", "HEAD"),
                branch="nsc-602-task",
                checkout_path=r"C:\NSC\NSC\NSC-602",
                planned_approach="Already resumable.",
                expected_validation="N/A.",
            )
            require(acquired["status"] == "acquired", f"fixture setup failed: {acquired}")
            resumable.publish_human_handoff(
                task_id="NSC-602",
                branch="nsc-602-task",
                head_commit="9" * 40,
                checkout_path=r"C:\NSC\NSC\NSC-602",
                implementation_summary="Done.",
                completed_checks=("Pushed.",),
                human_steps=("Test in Unity.",),
                expected_result="Passes.",
            )
            resumable.apply_human_result(
                task_id="NSC-602",
                result_body=(
                    "## Human validation result\n\nResult: PASS\n"
                    f"Tested commit: `{'9' * 40}`\n\nCompleted steps:\n- Verified.\n"
                ),
                actor_id="cathode26",
            )

            result = resolve_generic_dispatch(source=checkout, worker_id="stage3-generic")
            require(result.decision == "resume_existing", f"resume did not win: {result.decision}")
            require(result.task_id == "NSC-602", f"wrong resume target: {result.task_id}")
            require(len(store.issues) == 1, "fresh dispatch created an extra Issue despite resume")


def _committed_sha(checkout: Path, task_id: str) -> str:
    contract = git(checkout, "show", f"HEAD:Tasks/{task_id}.yaml")
    import hashlib

    return hashlib.sha256(contract.encode("utf-8")).hexdigest()


def test_no_safe_work_is_a_normal_typed_result() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-no-safe-work-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-603": make_task("NSC-603")}
        states = {"NSC-603": "conformant"}
        checkout, _remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend():
            result = resolve_generic_dispatch(source=checkout, worker_id="stage3-generic")
        require(result.decision == "no_safe_work", f"unexpected decision: {result.decision}")
        require(result.task_id is None, str(result.task_id))


# ---------------------------------------------------------------------------
# Stage 2 / Stage 3 dependency-admission alignment: a "needs_testing"
# dependency is dispatch-satisfied (revalidation debt) end to end, without a
# task whose OWN derived state is "needs_testing" ever being treated as fresh
# work, and without Stage 3 rejecting a candidate Stage 2 already approved.
# ---------------------------------------------------------------------------


def test_needs_testing_dependency_is_dispatch_satisfied_without_wedge() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-needs-testing-") as tmp:
        root = Path(tmp)
        tasks = {
            "NSC-624": make_task("NSC-624"),
            "NSC-625": make_task("NSC-625", depends_on=["NSC-624"]),
        }
        states = {"NSC-624": "needs_testing", "NSC-625": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner

            plan = build_dispatch_plan(source=checkout, worker_id="stage3-needs-testing-worker")
            require(plan.decision == "fresh_candidate", str(plan.decision))
            candidate = plan.selected_fresh_candidate
            require(
                candidate["task_id"] == "NSC-625",
                f"Stage 2 did not select the needs_testing-dependent task: {candidate}",
            )
            require(candidate["eligible"], str(candidate["reason_codes"]))
            require(
                candidate["dependency_observations"]
                == [
                    {
                        "task_id": "NSC-624",
                        "state": "needs_testing",
                        "dispatch_satisfied": True,
                        "note": "revalidation_debt",
                    }
                ],
                str(candidate["dependency_observations"]),
            )

            # The exact divergence Fable found: Stage 2 approves this
            # candidate's dependency as dispatch-satisfied, and a lower
            # Stage 3 gate must not deterministically reject it anyway for
            # using a stricter, contradictory dependency predicate.
            result = resolve_generic_dispatch(source=checkout, worker_id="stage3-needs-testing-worker")
            require(
                result.decision == "fresh_started",
                "Stage 3 rejected a Stage 2-approved needs_testing-dependency "
                f"candidate: {result.decision}; reasons={result.reasons}",
            )
            require(result.task_id == "NSC-625", str(result.task_id))
            require(len(store.issues) == 1, "fresh dispatch did not create exactly one Issue")


def test_own_needs_testing_state_is_not_fresh_work() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-own-needs-testing-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-626": make_task("NSC-626")}
        states = {"NSC-626": "needs_testing"}
        checkout, _remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend():
            evaluation = evaluate_committed_fresh_candidate(
                source=checkout, task_id="NSC-626", worker_id="stage3-own-state-worker"
            )
            require(
                not evaluation.eligible,
                "a task whose OWN derived state is needs_testing was treated as fresh work",
            )
            require(
                evaluation.reason_codes == ("derived_state_not_fresh:needs_testing",),
                str(evaluation.reason_codes),
            )


# ---------------------------------------------------------------------------
# Artifact-kind eligibility must be consistent between Stage 2 and Stage 3:
# the current execution pipeline is implementation-only, so Stage 2 never
# ranks an artifact-kind task as fresh work in the first place.
# ---------------------------------------------------------------------------


def test_artifact_kind_is_rejected_by_stage2_and_never_reaches_stage3() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-artifact-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-627": make_task("NSC-627", kind="artifact")}
        states = {"NSC-627": "not_delivered"}
        checkout, _remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend():
            evaluation = evaluate_committed_fresh_candidate(
                source=checkout, task_id="NSC-627", worker_id="stage3-artifact-worker"
            )
            require(
                not evaluation.eligible,
                "Stage 2 admitted an artifact-kind task as fresh executable work",
            )
            require(evaluation.reason_codes == ("unsupported_kind",), str(evaluation.reason_codes))

            plan = build_dispatch_plan(source=checkout, worker_id="stage3-artifact-worker")
            require(
                plan.decision == "no_safe_work",
                f"Stage 2 still ranked an artifact-kind task as a fresh candidate: {plan.decision}",
            )


def test_autonomous_dispatch_remains_disabled() -> None:
    policy = load_dispatch_policy()
    require(policy.autonomous_dispatch is False, "committed dispatch policy enabled autonomous dispatch")


def test_fresh_dispatch_module_has_no_decomposition_routing() -> None:
    names = " ".join(dir(fresh_dispatch_module)).casefold()
    require("decompos" not in names, "fresh_dispatch module exposes decomposition routing")
    require(
        GENERIC_DISPATCH_DECISIONS
        == {
            "resume_existing",
            "fresh_started",
            "claim_conflict",
            "no_safe_work",
            "blocked_invalid_state",
            "claim_operational_error",
            "issue_initialization_blocked",
            "lease_acquired_claim_cleanup_required",
        },
        str(GENERIC_DISPATCH_DECISIONS),
    )


# ---------------------------------------------------------------------------
# 2/5/9/10/11/13/15/17. Successful fresh start: mutation order + continuation.
# ---------------------------------------------------------------------------


def test_fresh_dispatch_starts_and_continues_through_existing_pipeline() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-fresh-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-610": make_task("NSC-610")}
        states = {"NSC-610": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            claims_seen_during_create: dict[str, str] = {}
            real_create_issue = store.create_issue

            def observing_create_issue(**kwargs: Any) -> dict[str, Any]:
                claims_seen_during_create.update(remote_claims(remote))
                return real_create_issue(**kwargs)

            store.create_issue = observing_create_issue  # type: ignore[assignment]

            checkout_root = root / "operator"
            result = resolve_generic_dispatch(
                source=checkout,
                worker_id="stage3-fresh-worker",
                checkout_root=checkout_root,
            )

            require(result.decision == "fresh_started", f"unexpected decision: {result.decision}")
            require(result.task_id == "NSC-610", str(result.task_id))
            require(
                bool(claims_seen_during_create),
                "the Stage 1 claim ref did not exist yet when the Issue was created "
                "(claim must strictly precede Issue mutation)",
            )
            require(
                task_claim_ref(NAMESPACE, "NSC-610") in claims_seen_during_create,
                f"expected task claim ref during Issue init: {claims_seen_during_create}",
            )
            require(
                remote_claims(remote) == {},
                "ephemeral claim refs were not released after a verified handoff",
            )
            release = (result.lease_result or {}).get("ephemeral_claim", {}).get("release", {})
            require(release.get("status") == "released", f"release not reported: {result.lease_result}")

            store_after = backend_cls.store_for(checkout)
            require(len(store_after.issues) == 1, "exactly one Issue must be created")
            issue = next(iter(store_after.issues.values()))
            require("NSC-610" in issue["title"], f"Issue title missing task id: {issue['title']}")
            require(
                any(label["name"] == "nsc-state:agent-working" for label in issue["labels"]),
                f"Issue was not labeled agent-working: {issue['labels']}",
            )

            # "Existing orchestrator continuation": constructing a plain
            # RealTaskReviewWorkflow again (as run_pipeline_agent.py does)
            # must see the already-leased Issue and need no further mutation.
            from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow

            continuation = RealTaskReviewWorkflow(
                source=checkout,
                task_id="NSC-610",
                checkout_root=checkout_root,
                worker_id="stage3-fresh-worker",
            )
            observation = continuation.observe_goal_state()
            require(
                observation["coordination"]["status"] == "claimed_by_worker",
                f"continuation did not observe the durable lease: {observation['coordination']}",
            )


# ---------------------------------------------------------------------------
# 4. HEAD drift between planning and mutation blocks before any mutation.
# ---------------------------------------------------------------------------


def test_head_drift_between_plan_and_mutation_blocks_before_mutation() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-head-drift-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-611": make_task("NSC-611")}
        states = {"NSC-611": "not_delivered"}
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
                result = resolve_generic_dispatch(source=checkout, worker_id="stage3-drift-worker")
            finally:
                fresh_dispatch_module.build_dispatch_plan = real_plan  # type: ignore[assignment]

            require(result.decision == "blocked_invalid_state", f"unexpected decision: {result.decision}")
            require(
                any("HEAD moved" in reason for reason in result.reasons),
                str(result.reasons),
            )
            require(store.issues == {}, "a stale plan still mutated the durable Issue")
            require(remote_claims(remote) == {}, "a stale plan still created a claim ref")


# ---------------------------------------------------------------------------
# 6/7/21. Claim contention (same task, shared resource): typed, no mutation,
# and no retry against a different candidate.
# ---------------------------------------------------------------------------


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


class _RacingWorkflowFactory:
    """Build a ``RealTaskReviewWorkflow`` subclass that lets a foreign worker
    win a Stage 1 claim race in the window BETWEEN Stage 2's read-only plan
    (which already excludes an ALREADY-held claim from its candidate pool --
    see dispatch_plan_smoke_test.py's active-claim tests) and Stage 3's own
    atomic acquire. Patched into ``fresh_dispatch_module.RealTaskReviewWorkflow``
    for the duration of one call so the race is deterministic, not timing-based.
    """

    def __init__(self, *, real_cls: type, race: Callable[[], None]) -> None:
        outer = self

        class RacingWorkflow(real_cls):  # type: ignore[misc, valid-type]
            def acquire_agent_lease(self, **kwargs: Any) -> dict[str, Any]:
                outer._race()
                return super().acquire_agent_lease(**kwargs)

        self.cls = RacingWorkflow
        self._race = race


def test_same_task_claim_conflict_is_typed_with_no_issue_mutation_and_no_retry() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-claim-conflict-") as tmp:
        root = Path(tmp)
        tasks = {
            "NSC-612": make_task("NSC-612"),
            "NSC-613": make_task("NSC-613"),
        }
        states = {"NSC-612": "not_delivered", "NSC-613": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            racing = _RacingWorkflowFactory(
                real_cls=fresh_dispatch_module.RealTaskReviewWorkflow,
                race=lambda: _acquire_foreign_claim(
                    checkout=checkout, remote=remote, task_id="NSC-612", resources=[]
                ),
            )
            original = fresh_dispatch_module.RealTaskReviewWorkflow
            fresh_dispatch_module.RealTaskReviewWorkflow = racing.cls  # type: ignore[assignment]
            try:
                result = resolve_generic_dispatch(source=checkout, worker_id="stage3-conflict-worker")
            finally:
                fresh_dispatch_module.RealTaskReviewWorkflow = original  # type: ignore[assignment]
            require(result.decision == "claim_conflict", f"unexpected decision: {result.decision}")
            require(result.task_id == "NSC-612", "Stage 2's exact selection was not the one raced")
            require(
                store.issues == {},
                "a lost claim race must never initialize a durable Issue, and Stage 3 "
                "must never retry a different candidate after losing (Stage 4 only)",
            )


def test_shared_resource_claim_conflict_is_typed() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-shared-resource-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-614": make_task("NSC-614", exclusive_resources=[SHARED_RESOURCE])}
        states = {"NSC-614": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            racing = _RacingWorkflowFactory(
                real_cls=fresh_dispatch_module.RealTaskReviewWorkflow,
                race=lambda: _acquire_foreign_claim(
                    checkout=checkout,
                    remote=remote,
                    task_id="NSC-999",
                    resources=[SHARED_RESOURCE],
                ),
            )
            original = fresh_dispatch_module.RealTaskReviewWorkflow
            fresh_dispatch_module.RealTaskReviewWorkflow = racing.cls  # type: ignore[assignment]
            try:
                result = resolve_generic_dispatch(source=checkout, worker_id="stage3-conflict-worker")
            finally:
                fresh_dispatch_module.RealTaskReviewWorkflow = original  # type: ignore[assignment]
            require(result.decision == "claim_conflict", f"unexpected decision: {result.decision}")
            require(store.issues == {}, "shared-resource conflict still mutated the durable Issue")


# ---------------------------------------------------------------------------
# 8. Claim operational failure is distinguished from contention.
# ---------------------------------------------------------------------------


def test_claim_operational_failure_is_not_classified_as_contention() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-claim-operational-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-615": make_task("NSC-615")}
        states = {"NSC-615": "not_delivered"}
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
            result = resolve_generic_dispatch(source=checkout, worker_id="stage3-operational-worker")
            require(
                result.decision == "claim_operational_error",
                f"an operational push rejection was misclassified: {result.decision}",
            )
            require(store.issues == {}, "an operational claim failure still mutated the durable Issue")


def test_claim_policy_failure_maps_to_claim_operational_error() -> None:
    """A broken/deactivated committed claim policy (``ClaimPolicyError`` /
    ``ClaimCoordinationNotActivatedError`` from ``build_activated_claim_client``)
    must map to the typed ``claim_operational_error`` outcome instead of
    escaping ``resolve_generic_dispatch`` as an unhandled generic STOP."""

    from Pipeline.TaskReviewAgent.claim_policy import ClaimCoordinationNotActivatedError

    with tempfile.TemporaryDirectory(prefix="nsc-stage3-claim-policy-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-618": make_task("NSC-618")}
        states = {"NSC-618": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            real_cls = fresh_dispatch_module.RealTaskReviewWorkflow

            class DeactivatedPolicyWorkflow(real_cls):  # type: ignore[misc, valid-type]
                def acquire_agent_lease(self, **kwargs: Any) -> dict[str, Any]:
                    raise ClaimCoordinationNotActivatedError(
                        "synthetic: committed claim policy is not yet activated"
                    )

            fresh_dispatch_module.RealTaskReviewWorkflow = DeactivatedPolicyWorkflow  # type: ignore[assignment]
            try:
                result = resolve_generic_dispatch(source=checkout, worker_id="stage3-claim-policy-worker")
            finally:
                fresh_dispatch_module.RealTaskReviewWorkflow = real_cls  # type: ignore[assignment]
            require(
                result.decision == "claim_operational_error",
                f"a claim-policy failure escaped typing as claim_operational_error: {result.decision}",
            )
            require(store.issues == {}, "a claim-policy failure still mutated the durable Issue")
            require(remote_claims(remote) == {}, "a claim-policy failure still left a claim ref behind")


# ---------------------------------------------------------------------------
# 12/14. Issue-mutation failure paths: cleanup-required, malformed init.
# ---------------------------------------------------------------------------


def test_issue_initialization_failure_is_reported_and_claim_left_for_inspection() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-init-failure-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-616": make_task("NSC-616")}
        states = {"NSC-616": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner

            def failing_ensure_labels() -> None:
                from Pipeline.TaskReviewAgent.issue_workflow_store import IssueWorkflowStoreError

                raise IssueWorkflowStoreError("synthetic GitHub label API outage")

            store.ensure_labels = failing_ensure_labels  # type: ignore[assignment]

            result = resolve_generic_dispatch(source=checkout, worker_id="stage3-init-failure-worker")
            require(
                result.decision == "issue_initialization_blocked",
                f"unexpected decision: {result.decision}",
            )
            require(store.issues == {}, "a failed initialization must not leave a partial Issue")
            # Existing acquire_issue_lease_with_claims semantics: when the
            # Issue workflow call raises (rather than returning a normal
            # blocked/acquired dict), the claim is left in place for manual
            # inspection -- Stage 3 does not invent a stronger cleanup
            # guarantee than the primitive it reuses already provides.
            inspector = GitRefClaimClient(
                local_repository=checkout,
                remote=str(remote),
                namespace=NAMESPACE,
                worker_id="stage3-inspector",
            )
            require(
                len(inspector.inspect_claims()) == 1,
                "the claim ref from the failed initialization should remain for manual repair",
            )


def test_cleanup_failure_after_verified_lease_is_not_ordinary_success() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-cleanup-failure-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-617": make_task("NSC-617", exclusive_resources=[SHARED_RESOURCE])}
        states = {"NSC-617": "not_delivered"}
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
                    task_id="NSC-617",
                    exclusive_resources=[SHARED_RESOURCE],
                    source_head=git(worker_b_repo, "rev-parse", "HEAD"),
                )
                require(isinstance(reclaimed, ClaimAcquisition), f"sabotage reclaim failed: {reclaimed!r}")
                return issue

            store.create_issue = sabotaging_create_issue  # type: ignore[assignment]

            result = resolve_generic_dispatch(source=checkout, worker_id="stage3-cleanup-worker")
            require(
                result.decision == "lease_acquired_claim_cleanup_required",
                f"a cleanup failure returned an ordinary outcome: {result.decision}",
            )
            require(
                (result.lease_result or {}).get("issue_result", {}).get("status") == "acquired",
                f"the acquired durable lease fact was lost: {result.lease_result}",
            )


# ---------------------------------------------------------------------------
# 18/19/20. Explicit fresh-TaskId admission shares the Stage 2 kernel; resume
# bypasses the gate entirely; a blocked explicit task is never substituted.
# ---------------------------------------------------------------------------


def test_explicit_fresh_admission_shares_stage2_kernel_and_never_substitutes() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-explicit-") as tmp:
        root = Path(tmp)
        tasks = {
            "NSC-620": make_task("NSC-620"),
            "NSC-621": make_task("NSC-621", execution_scope="needs_execution_decomposition"),
        }
        states = {"NSC-620": "not_delivered", "NSC-621": "not_delivered"}
        checkout, _remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend():
            plan = build_dispatch_plan(source=checkout, worker_id="stage3-explicit-worker")
            eligible = evaluate_committed_fresh_candidate(
                source=checkout, task_id="NSC-620", worker_id="stage3-explicit-worker"
            )
            blocked = evaluate_committed_fresh_candidate(
                source=checkout, task_id="NSC-621", worker_id="stage3-explicit-worker"
            )
            require(eligible.eligible, f"explicit fresh admission diverged from Stage 2: {eligible.reason_codes}")
            require(plan.selected_fresh_candidate == eligible.to_dict(), "explicit/generic evaluation diverged")
            require(not blocked.eligible, "an explicit ineligible task was accepted")
            require(
                blocked.reason_codes == ("execution_scope_not_single_agent",),
                str(blocked.reason_codes),
            )
            require(blocked.task_id == "NSC-621", "a blocked explicit task's own id must be reported, never substituted")


def test_run_pipeline_agent_explicit_admission_wiring() -> None:
    calls: list[tuple[str, str, str]] = []

    class _StubEvaluation:
        def __init__(self, eligible: bool, reason_codes: tuple[str, ...]) -> None:
            self.eligible = eligible
            self.reason_codes = reason_codes

    def stub_evaluate(*, source: Path, task_id: str, worker_id: str):
        calls.append((str(source), task_id, worker_id))
        if task_id == "NSC-630":
            return _StubEvaluation(True, ())
        return _StubEvaluation(False, ("execution_scope_not_single_agent",))

    original = run_pipeline_agent_module.evaluate_committed_fresh_candidate
    run_pipeline_agent_module.evaluate_committed_fresh_candidate = stub_evaluate  # type: ignore[assignment]
    try:
        # Resume: an existing managed Issue phase must bypass the fresh-
        # admission gate entirely (the stub must never be called).
        run_pipeline_agent_module._require_explicit_fresh_admission(
            source=Path("/tmp/does-not-matter"),
            task_id="NSC-999",
            worker_id="w",
            selected_phase="implementation",
        )
        require(calls == [], "a legitimate resume routed through fresh evaluation")

        # Fresh + eligible: no exception.
        run_pipeline_agent_module._require_explicit_fresh_admission(
            source=Path("/tmp/does-not-matter"), task_id="NSC-630", worker_id="w", selected_phase=None
        )
        require(calls == [(str(Path("/tmp/does-not-matter")), "NSC-630", "w")], str(calls))

        # Fresh + blocked: raises referencing THIS task_id, never substitutes.
        try:
            run_pipeline_agent_module._require_explicit_fresh_admission(
                source=Path("/tmp/does-not-matter"), task_id="NSC-631", worker_id="w", selected_phase=None
            )
            raise AssertionError("a blocked explicit fresh task was silently admitted")
        except run_pipeline_agent_module.GenericSelectionError as exc:
            require("NSC-631" in str(exc), f"blocked explicit task_id missing from error: {exc}")
            require("execution_scope_not_single_agent" in str(exc), str(exc))
    finally:
        run_pipeline_agent_module.evaluate_committed_fresh_candidate = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# observe mode must never mutate for the generic no-TaskId command.
# ---------------------------------------------------------------------------


def test_generic_observe_mode_never_mutates() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-stage3-observe-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-640": make_task("NSC-640")}
        states = {"NSC-640": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            exit_code = run_pipeline_agent_module.main(
                ["--source", str(checkout), "--worker-id", "stage3-observe-worker", "--mode", "observe"]
            )
            require(exit_code == 0, f"observe mode failed: {exit_code}")
            require(store.issues == {}, "observe mode mutated the durable Issue backend")
            require(remote_claims(remote) == {}, "observe mode created a Stage 1 claim ref")


def test_explicit_observe_mode_does_not_require_fresh_admission() -> None:
    """``--mode observe --task-id NSC-...`` must stay read-only diagnostic
    behavior: it must not apply fresh-mutation admission and reject a task
    the operator merely wants to inspect."""

    with tempfile.TemporaryDirectory(prefix="nsc-stage3-observe-explicit-") as tmp:
        root = Path(tmp)
        tasks = {
            "NSC-641": make_task("NSC-641", execution_scope="needs_execution_decomposition")
        }
        states = {"NSC-641": "not_delivered"}
        checkout, remote = create_fixture(root, tasks=tasks, states=states)
        with PatchedGhBackend() as backend_cls:
            store = backend_cls(source_root=checkout)._inner
            exit_code = run_pipeline_agent_module.main(
                [
                    "--source",
                    str(checkout),
                    "--worker-id",
                    "stage3-observe-explicit-worker",
                    "--mode",
                    "observe",
                    "--task-id",
                    "NSC-641",
                ]
            )
            require(
                exit_code == 0,
                "explicit observe mode rejected an ineligible-for-fresh-mutation "
                f"task instead of just observing it: {exit_code}",
            )
            require(store.issues == {}, "explicit observe mode mutated the durable Issue")
            require(remote_claims(remote) == {}, "explicit observe mode created a Stage 1 claim ref")


# ---------------------------------------------------------------------------
# Small production composition test: the real main() no-TaskId route maps
# Stage 3's typed generic-dispatch outcomes to the documented exit codes.
# ---------------------------------------------------------------------------


def test_main_no_task_id_exit_code_mapping() -> None:
    from Pipeline.TaskReviewAgent.fresh_dispatch import GenericDispatchResult

    original = run_pipeline_agent_module.resolve_generic_dispatch
    stubbed_result: dict[str, GenericDispatchResult] = {}

    def stub(*, source: Path, worker_id: str, checkout_root: Path | None = None) -> GenericDispatchResult:
        return stubbed_result["value"]

    run_pipeline_agent_module.resolve_generic_dispatch = stub  # type: ignore[assignment]
    try:
        stubbed_result["value"] = GenericDispatchResult(decision="no_safe_work")
        exit_code = run_pipeline_agent_module.main(
            ["--source", str(ROOT), "--worker-id", "stage3-main-mapping-worker"]
        )
        require(exit_code == 0, f"no_safe_work must map to a normal exit: {exit_code}")

        stubbed_result["value"] = GenericDispatchResult(decision="claim_conflict", task_id="NSC-999")
        exit_code = run_pipeline_agent_module.main(
            ["--source", str(ROOT), "--worker-id", "stage3-main-mapping-worker"]
        )
        require(exit_code == 2, f"claim_conflict must map to a controlled nonzero exit: {exit_code}")

        stubbed_result["value"] = GenericDispatchResult(
            decision="blocked_invalid_state", task_id="NSC-999"
        )
        exit_code = run_pipeline_agent_module.main(
            ["--source", str(ROOT), "--worker-id", "stage3-main-mapping-worker"]
        )
        require(exit_code == 2, f"blocked_invalid_state must map to a controlled nonzero exit: {exit_code}")
    finally:
        run_pipeline_agent_module.resolve_generic_dispatch = original  # type: ignore[assignment]


def main() -> int:
    tests = (
        test_resume_beats_fresh_and_uses_exact_stage2_selection,
        test_no_safe_work_is_a_normal_typed_result,
        test_needs_testing_dependency_is_dispatch_satisfied_without_wedge,
        test_own_needs_testing_state_is_not_fresh_work,
        test_artifact_kind_is_rejected_by_stage2_and_never_reaches_stage3,
        test_autonomous_dispatch_remains_disabled,
        test_fresh_dispatch_module_has_no_decomposition_routing,
        test_fresh_dispatch_starts_and_continues_through_existing_pipeline,
        test_head_drift_between_plan_and_mutation_blocks_before_mutation,
        test_same_task_claim_conflict_is_typed_with_no_issue_mutation_and_no_retry,
        test_shared_resource_claim_conflict_is_typed,
        test_claim_operational_failure_is_not_classified_as_contention,
        test_claim_policy_failure_maps_to_claim_operational_error,
        test_issue_initialization_failure_is_reported_and_claim_left_for_inspection,
        test_cleanup_failure_after_verified_lease_is_not_ordinary_success,
        test_explicit_fresh_admission_shares_stage2_kernel_and_never_substitutes,
        test_run_pipeline_agent_explicit_admission_wiring,
        test_generic_observe_mode_never_mutates,
        test_explicit_observe_mode_does_not_require_fresh_admission,
        test_main_no_task_id_exit_code_mapping,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Stage 3 fresh-dispatch tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
