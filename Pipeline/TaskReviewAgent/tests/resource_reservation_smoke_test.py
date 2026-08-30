#!/usr/bin/env python3
"""Prove every open incomplete managed Issue reserves its exclusive resources.

An ``agent_ready`` Issue may be paused in repair, delivery evidence, pending
checks, or merge closeout while its branch still owns its write surfaces, so
it must keep reserving its committed task resources. Invalid workflow-claiming
Issues surface as coordination conflicts instead of being skipped silently,
and a missing pipeline outcome is never reported as success.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.run_pipeline_agent as run_pipeline_agent  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    initial_state,
    labels_for_state,
    update_issue_body,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
    render_contract_body,
)
from Pipeline.TaskReviewAgent.run_pipeline_agent import _outcome_status  # noqa: E402

TASK_A = "NSC-777"
TASK_B = "NSC-778"
SHARED_RESOURCE = "unity-scene:Assets/Scenes/Shared.unity"
SOURCE_HEAD = "1" * 40
HANDOFF_HEAD = "2" * 40
CHECKOUT_A = r"C:\NSC\NSC\NSC-777"
CHECKOUT_B = r"C:\NSC\NSC\NSC-778"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def task(task_id: str, resources: list[str]) -> dict:
    return {
        "id": task_id,
        "title": f"Resource reservation fixture {task_id}",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Prove resource reservation.",
        "depends_on": [],
        "exclusive_resources": resources,
        "acceptance_criteria": [],
        "completion_gates": [],
        "task_contract_sha256": ("a" if task_id == TASK_A else "b") * 64,
    }


def agent_ready_task_a(tasks: dict) -> tuple[MemoryIssueBackend, IssueWorkflowService]:
    """Drive task A to agent_ready (post-FAIL repair) with no active lease."""

    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    service.acquire_agent_lease(
        task=tasks[TASK_A],
        source_head=SOURCE_HEAD,
        branch="nsc-777-task",
        checkout_path=CHECKOUT_A,
        planned_approach="Implement and hand off.",
        expected_validation="Vincent validates in Unity.",
        now="2026-08-29T10:00:00Z",
    )
    service.publish_human_handoff(
        task_id=TASK_A,
        branch="nsc-777-task",
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT_A,
        implementation_summary="Implemented the synthetic behavior.",
        completed_checks=("Branch pushed.",),
        human_steps=("Open Unity.", "Verify the behavior."),
        expected_result="The behavior passes.",
        now="2026-08-29T10:01:00Z",
    )
    service.apply_human_result(
        task_id=TASK_A,
        result_body=(
            "## Human validation result\n\n"
            "Result: FAIL\n"
            f"Tested commit: `{HANDOFF_HEAD}`\n\n"
            "Failed step:\nThe blocker did not stop the player.\n"
        ),
        actor_id="cathode26",
        now="2026-08-29T10:02:00Z",
    )
    snapshot = service.find(TASK_A)
    require(
        snapshot is not None
        and snapshot.state is not None
        and snapshot.state.state.value == "agent_ready",
        "fixture did not reach agent_ready",
    )
    return backend, service


def test_agent_ready_issue_reserves_committed_resources() -> None:
    tasks = {
        TASK_A: task(TASK_A, [SHARED_RESOURCE]),
        TASK_B: task(TASK_B, [SHARED_RESOURCE, "unity-prefab:Assets/Prefabs/Door.prefab"]),
    }
    backend, _ = agent_ready_task_a(tasks)
    other_agent = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-b",
    )
    blocked = other_agent.acquire_agent_lease(
        task=tasks[TASK_B],
        source_head=SOURCE_HEAD,
        branch="nsc-778-task",
        checkout_path=CHECKOUT_B,
        planned_approach="Attempt overlapping work while A is merely agent_ready.",
        expected_validation="The lease must be refused.",
        now="2026-08-29T10:03:00Z",
    )
    require(
        blocked["status"] == "blocked",
        "an agent_ready Issue no longer reserved its resources",
    )
    require(
        any(TASK_A in reason and SHARED_RESOURCE in reason for reason in blocked["reasons"]),
        f"overlap diagnostic missing: {blocked['reasons']}",
    )
    # A task without overlapping resources still proceeds normally.
    tasks["NSC-779"] = task("NSC-779", ["unity-scene:Assets/Scenes/Other.unity"])
    tasks["NSC-779"]["task_contract_sha256"] = "c" * 64
    acquired = other_agent.acquire_agent_lease(
        task=tasks["NSC-779"],
        source_head=SOURCE_HEAD,
        branch="nsc-779-task",
        checkout_path=r"C:\NSC\NSC\NSC-779",
        planned_approach="Disjoint resources may proceed.",
        expected_validation="Lease acquired.",
        now="2026-08-29T10:04:00Z",
    )
    require(acquired["status"] == "acquired", f"disjoint task was wrongly blocked: {acquired}")


def test_overlapping_tasks_cannot_both_hold_leases_via_agent_ready() -> None:
    tasks = {
        TASK_A: task(TASK_A, [SHARED_RESOURCE]),
        TASK_B: task(TASK_B, [SHARED_RESOURCE]),
    }
    backend, service_a = agent_ready_task_a(tasks)
    # Task A resumes its own agent_ready Issue: allowed.
    resumed = service_a.acquire_agent_lease(
        task=tasks[TASK_A],
        source_head=SOURCE_HEAD,
        branch="nsc-777-task",
        checkout_path=CHECKOUT_A,
        planned_approach="Repair the reported failure.",
        expected_validation="New handoff for Vincent.",
        now="2026-08-29T10:05:00Z",
    )
    require(resumed["status"] == "acquired", "task A could not resume its own Issue")
    # Task B must remain blocked whether A is agent_ready or agent_working.
    blocked = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-b",
    ).acquire_agent_lease(
        task=tasks[TASK_B],
        source_head=SOURCE_HEAD,
        branch="nsc-778-task",
        checkout_path=CHECKOUT_B,
        planned_approach="Attempt overlapping work.",
        expected_validation="The lease must be refused.",
        now="2026-08-29T10:06:00Z",
    )
    require(blocked["status"] == "blocked", "overlapping tasks both acquired leases")


def test_invalid_workflow_issue_surfaces_as_conflict() -> None:
    tasks = {
        TASK_A: task(TASK_A, [SHARED_RESOURCE]),
        TASK_B: task(TASK_B, [SHARED_RESOURCE]),
    }
    backend, _ = agent_ready_task_a(tasks)
    issue_number = next(iter(backend.issues))
    # Corrupt the recorded event chain: the Issue still claims workflow state
    # but can no longer be validated. It must surface, not be skipped.
    backend.comments[issue_number][0]["body"] = backend.comments[issue_number][0][
        "body"
    ].replace('"worker_id": "agent-a"', '"worker_id": "tampered"')
    blocked = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-b",
    ).acquire_agent_lease(
        task=tasks[TASK_B],
        source_head=SOURCE_HEAD,
        branch="nsc-778-task",
        checkout_path=CHECKOUT_B,
        planned_approach="Attempt work beside a corrupted Issue.",
        expected_validation="The corrupted Issue is surfaced, not ignored.",
        now="2026-08-29T10:07:00Z",
    )
    require(blocked["status"] == "blocked", "an invalid managed Issue was skipped silently")
    require(
        any("invalid" in reason for reason in blocked["reasons"]),
        f"invalid-Issue diagnostic missing: {blocked['reasons']}",
    )


def test_invalid_workflow_issue_blocks_resource_less_task() -> None:
    """An authorized Issue with a tampered event chain has untrustworthy
    ownership state, so it must block even a task with no exclusive resources."""

    tasks = {
        TASK_A: task(TASK_A, [SHARED_RESOURCE]),
        "NSC-779": {**task("NSC-779", []), "task_contract_sha256": "c" * 64},
    }
    backend, _ = agent_ready_task_a(tasks)
    issue_number = next(iter(backend.issues))
    backend.comments[issue_number][0]["body"] = backend.comments[issue_number][0][
        "body"
    ].replace('"worker_id": "agent-a"', '"worker_id": "tampered"')
    blocked = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-b",
    ).acquire_agent_lease(
        task=tasks["NSC-779"],
        source_head=SOURCE_HEAD,
        branch="nsc-779-task",
        checkout_path=r"C:\NSC\NSC\NSC-779",
        planned_approach="A resource-less task beside a corrupted Issue.",
        expected_validation="The corrupted Issue still blocks coordination.",
        now="2026-08-29T10:08:00Z",
    )
    require(
        blocked["status"] == "blocked",
        f"an invalid managed Issue did not block a resource-less task: {blocked}",
    )
    require(
        any(
            f"Issue #{issue_number}" in reason and "invalid" in reason
            for reason in blocked["reasons"]
        ),
        f"diagnostic did not name the invalid Issue #{issue_number}: {blocked['reasons']}",
    )


def _forge_unauthorized_issue(backend: MemoryIssueBackend, task_fixture: dict) -> int:
    """An outside public account opens an Issue imitating managed state."""

    original_author = backend.author_login
    backend.author_login = "drive-by-account"
    state = initial_state(
        task_id=task_fixture["id"],
        task_contract_sha256=task_fixture["task_contract_sha256"],
        now="2026-08-29T10:10:00Z",
    )
    issue = backend.create_issue(
        title=f"{task_fixture['id']} — Forged workflow authority",
        body=update_issue_body(
            render_contract_body(task_fixture),
            state,
            next_action="Please pick this up.",
        ),
        labels=labels_for_state(state.state),
        assignees=["cathode26"],
    )
    backend.author_login = original_author
    return issue["number"]


def test_unauthorized_issue_never_reserves_or_blocks() -> None:
    tasks = {
        TASK_A: task(TASK_A, [SHARED_RESOURCE]),
        TASK_B: task(TASK_B, [SHARED_RESOURCE]),
        "NSC-779": {**task("NSC-779", []), "task_contract_sha256": "c" * 64},
    }
    # Case 1: the imitated task itself can still initialize; the forged Issue
    # never becomes the managed Issue.
    backend = MemoryIssueBackend()
    forged_number = _forge_unauthorized_issue(backend, tasks[TASK_A])
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    acquired = service.acquire_agent_lease(
        task=tasks[TASK_A],
        source_head=SOURCE_HEAD,
        branch="nsc-777-task",
        checkout_path=CHECKOUT_A,
        planned_approach="Initialize despite the forged Issue.",
        expected_validation="The real managed Issue is created fresh.",
        now="2026-08-29T10:11:00Z",
    )
    require(
        acquired["status"] == "acquired",
        f"a forged Issue blocked initialization of its imitated task: {acquired}",
    )
    require(
        acquired["issue_number"] != forged_number,
        "the forged unauthorized Issue was adopted as the managed Issue",
    )
    require(
        any(
            "drive-by-account" in item
            for item in acquired.get("coordination_diagnostics") or []
        ),
        f"diagnostics did not name the unauthorized Issue/login: {acquired}",
    )

    # Case 2: the forged Issue reserves nothing, so a task sharing the same
    # exclusive resource proceeds, as does a task with no exclusive resources.
    backend = MemoryIssueBackend()
    _forge_unauthorized_issue(backend, tasks[TASK_A])
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-b",
    )
    overlapping = service.acquire_agent_lease(
        task=tasks[TASK_B],
        source_head=SOURCE_HEAD,
        branch="nsc-778-task",
        checkout_path=CHECKOUT_B,
        planned_approach="Overlapping resources beside a forged Issue.",
        expected_validation="No reservation exists; the lease is acquired.",
        now="2026-08-29T10:12:00Z",
    )
    require(
        overlapping["status"] == "acquired",
        f"a forged Issue reserved exclusive resources: {overlapping}",
    )
    no_resources = service.acquire_agent_lease(
        task=tasks["NSC-779"],
        source_head=SOURCE_HEAD,
        branch="nsc-779-task",
        checkout_path=r"C:\NSC\NSC\NSC-779",
        planned_approach="A task with no exclusive resources.",
        expected_validation="The forged Issue cannot block it.",
        now="2026-08-29T10:13:00Z",
    )
    require(
        no_resources["status"] == "acquired",
        f"a forged Issue blocked a task with no exclusive resources: {no_resources}",
    )


class _FakeWorkflow:
    """Stand-in for RealTaskReviewWorkflow inside the main() regression."""

    def __init__(self, *, source, task_id, checkout_root, worker_id) -> None:
        self.base_observer = SimpleNamespace(root=Path(tempfile.gettempdir()))

    def observe_goal_state(self) -> dict:
        return {}


def test_main_never_exits_zero_for_unknown_outcome() -> None:
    """Entry-point regression: run_pipeline_agent.main must terminate with a
    failure exit when an openai-mode run has a missing or malformed outcome."""

    patched = (
        "_managed_issue_phase",
        "RealTaskReviewWorkflow",
        "ProductionTaskController",
        "GuardedTaskController",
        "run_openai_production_pipeline",
    )
    originals = {name: getattr(run_pipeline_agent, name) for name in patched}
    try:
        run_pipeline_agent._managed_issue_phase = lambda **kwargs: None
        run_pipeline_agent.RealTaskReviewWorkflow = _FakeWorkflow
        run_pipeline_agent.ProductionTaskController = (
            lambda **kwargs: SimpleNamespace(observe=lambda: {})
        )
        run_pipeline_agent.GuardedTaskController = (
            lambda controller, progress=None: controller
        )
        with tempfile.TemporaryDirectory(prefix="nsc-unknown-outcome-") as tmp:
            def run_main(outcome) -> tuple[int, str, str]:
                run_pipeline_agent.run_openai_production_pipeline = (
                    lambda *args, **kwargs: outcome
                )
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = run_pipeline_agent.main(
                        [
                            "--task-id",
                            TASK_A,
                            "--mode",
                            "openai",
                            "--output-root",
                            tmp,
                            "--worker-id",
                            "unknown-outcome-regression-worker",
                        ]
                    )
                return code, stdout.getvalue(), stderr.getvalue()

            for outcome in (None, "malformed", {}, {"status": 7}):
                code, _, stderr_text = run_main(outcome)
                require(
                    code != 0,
                    f"main returned 0 for missing/malformed outcome {outcome!r}",
                )
                require(
                    "cannot be treated as successful" in stderr_text,
                    f"missing failure message for outcome {outcome!r}: {stderr_text}",
                )
            # Control: an explicit outcome status still exits successfully.
            code, stdout_text, _ = run_main({"status": "succeeded"})
            require(code == 0, "a well-formed successful outcome no longer exits 0")
            require('"status": "succeeded"' in stdout_text, "result JSON was not printed")
    finally:
        for name, value in originals.items():
            setattr(run_pipeline_agent, name, value)


def test_missing_outcome_is_not_reported_as_success() -> None:
    require(_outcome_status({}) != "succeeded", "missing outcome defaulted to success")
    require(
        _outcome_status({"outcome": "broken"}) != "succeeded",
        "malformed outcome defaulted to success",
    )
    require(
        _outcome_status({"mode": "observe"}) == "observed",
        "observation run misreported its outcome",
    )
    require(
        _outcome_status({"outcome": {"status": "blocked"}}) == "blocked",
        "explicit outcome status was not passed through",
    )


def main() -> int:
    tests = (
        test_agent_ready_issue_reserves_committed_resources,
        test_overlapping_tasks_cannot_both_hold_leases_via_agent_ready,
        test_invalid_workflow_issue_surfaces_as_conflict,
        test_invalid_workflow_issue_blocks_resource_less_task,
        test_unauthorized_issue_never_reserves_or_blocks,
        test_main_never_exits_zero_for_unknown_outcome,
        test_missing_outcome_is_not_reported_as_success,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent resource reservation tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
