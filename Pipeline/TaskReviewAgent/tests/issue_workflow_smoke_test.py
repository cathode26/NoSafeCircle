#!/usr/bin/env python3
"""Deterministic tests for the durable GitHub Issue workflow controller."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    STATE_LABELS,
    IssueWorkflowEvent,
    WorkflowActor,
    WorkflowContractError,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    initial_state,
    labels_for_state,
    parse_events,
    parse_state,
    render_event_comment,
    transition,
    update_issue_body,
    validate_event_chain,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER,
    BLOCKED_KIND_DURABLE_RESOURCE_RESERVATION_CONFLICT,
    IssueWorkflowService,
    IssueWorkflowStoreError,
    MemoryIssueBackend,
)

TASK_ID = "NSC-777"
OTHER_TASK_ID = "NSC-778"
CONTRACT_HASH = "a" * 64
SOURCE_HEAD = "1" * 40
HANDOFF_HEAD = "2" * 40
CHECKOUT = r"C:\NSC\NSC\NSC-777"
BRANCH = "nsc-777-synthetic-workflow"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_error(action, text: str) -> None:
    try:
        action()
    except (WorkflowContractError, IssueWorkflowStoreError) as exc:
        require(text in str(exc), f"unexpected error: {exc}")
    else:
        raise AssertionError(f"expected workflow error containing {text!r}")


def task(
    task_id: str,
    resource: str = "unity-scene:Assets/Scenes/Test.unity",
) -> dict:
    return {
        "id": task_id,
        "title": f"Synthetic workflow task {task_id}",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Prove the durable issue workflow.",
        "depends_on": [],
        "exclusive_resources": [resource],
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "requirement": "The workflow is durable."}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "requirement": "The issue resumes safely."}
        ],
        "task_contract_sha256": CONTRACT_HASH if task_id == TASK_ID else "b" * 64,
    }


def test_state_event_round_trip_and_chain() -> None:
    state = initial_state(
        task_id=TASK_ID,
        task_contract_sha256=CONTRACT_HASH,
        now="2026-08-27T10:00:00Z",
    )
    state, lease = transition(
        state,
        event_type=WorkflowEventType.AGENT_LEASE_ACQUIRED,
        actor_type=WorkflowActor.AGENT,
        actor_id="agent-a",
        to_state=WorkflowState.AGENT_WORKING,
        details={"worker_id": "agent-a", "lease_id": "c" * 64},
        now="2026-08-27T10:01:00Z",
    )
    state, handoff = transition(
        state,
        event_type=WorkflowEventType.HUMAN_HANDOFF_CREATED,
        actor_type=WorkflowActor.AGENT,
        actor_id="agent-a",
        to_state=WorkflowState.HUMAN_ACTION_REQUIRED,
        to_phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
        details={
            "branch": BRANCH,
            "head_commit": HANDOFF_HEAD,
            "checkout_path": CHECKOUT,
        },
        now="2026-08-27T10:02:00Z",
    )
    state, failed = transition(
        state,
        event_type=WorkflowEventType.HUMAN_VALIDATION_FAILED,
        actor_type=WorkflowActor.HUMAN,
        actor_id="cathode26",
        to_state=WorkflowState.AGENT_READY,
        to_phase=WorkflowPhase.REPAIR,
        details={"tested_commit": HANDOFF_HEAD, "result": "fail"},
        now="2026-08-27T10:03:00Z",
    )

    body = update_issue_body(
        "# Original task body\n",
        state,
        next_action="Repair the failure.",
    )
    require(parse_state(body) == state, "state block round trip changed bytes")
    author = {"login": "cathode26"}
    comments = [
        {"author": author, "body": render_event_comment(lease, "lease")},
        {"author": author, "body": render_event_comment(handoff, "handoff")},
        {"author": author, "body": render_event_comment(failed, "failure")},
    ]
    events = parse_events(comments)
    require(validate_event_chain(state, events) == events, "valid chain was rejected")
    require(
        labels_for_state(state.state) == [STATE_LABELS["agent_ready"]],
        "agent-ready label was not selected",
    )

    tampered = json.loads(json.dumps(failed.to_dict()))
    tampered["details"]["result"] = "pass"
    expect_error(lambda: IssueWorkflowEvent.from_dict(tampered), "event_id")

    wrong_state = replace(state, last_event_id="d" * 64)
    expect_error(
        lambda: validate_event_chain(wrong_state, events),
        "final workflow event",
    )


def test_issue_service_handoff_human_result_and_resume() -> None:
    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    acquired = service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Implement the task and commit the exact branch.",
        expected_validation="Run checks, then hand Unity validation to Vincent.",
        now="2026-08-27T11:00:00Z",
    )
    require(acquired["status"] == "acquired", f"lease was not acquired: {acquired}")
    require(
        service.observe(TASK_ID)["status"] == "agent_working_by_worker",
        "working lease not observed",
    )

    handoff = service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Implemented the synthetic gameplay behavior and tests.",
        completed_checks=("TaskGraph validation passed.", "Branch was pushed."),
        human_steps=("Open the project.", "Enter Play Mode.", "Verify the behavior."),
        expected_result="The behavior matches AC-001.",
        now="2026-08-27T11:01:00Z",
    )
    require(handoff["status"] == "human_action_required", "handoff state was wrong")
    require(not service.list_agent_ready(), "human task incorrectly appeared agent-ready")

    wrong_result = """## Human validation result

Result: PASS
Tested commit: `3333333333333333333333333333333333333333`
"""
    expect_error(
        lambda: service.apply_human_result(
            task_id=TASK_ID,
            result_body=wrong_result,
            actor_id="cathode26",
            now="2026-08-27T11:02:00Z",
        ),
        "handoff commit",
    )

    failure_result = f"""## Human validation result

Result: FAIL
Tested commit: `{HANDOFF_HEAD}`

Failed step:
The player crossed the blocker.
"""
    ready = service.apply_human_result(
        task_id=TASK_ID,
        result_body=failure_result,
        actor_id="cathode26",
        now="2026-08-27T11:03:00Z",
    )
    require(ready["status"] == "agent_ready", "human failure did not return agent-ready")
    queue = service.list_agent_ready()
    require(len(queue) == 1, f"agent-ready queue was wrong: {queue}")
    require(
        queue[0]["workflow_state"]["phase"] == "repair",
        "failed human validation did not select repair phase",
    )

    next_agent = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-b",
    )
    resumed = next_agent.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Repair the human-reported blocker on the existing branch.",
        expected_validation="Commit, push, and return a new Unity checklist.",
        now="2026-08-27T11:04:00Z",
    )
    require(resumed["status"] == "acquired", "next agent could not resume the issue")
    require(
        resumed["workflow_state"]["worker_id"] == "agent-b",
        "new agent lease did not record its worker ID",
    )


def test_resource_conflict_and_tampered_history_fail_closed() -> None:
    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Reserve the shared scene.",
        expected_validation="Return it to human review.",
        now="2026-08-27T12:00:00Z",
    )
    blocked = service.acquire_agent_lease(
        task=tasks[OTHER_TASK_ID],
        source_head=SOURCE_HEAD,
        branch="nsc-778-other",
        checkout_path=r"C:\NSC\NSC\NSC-778",
        planned_approach="Attempt overlapping work.",
        expected_validation="Should be blocked.",
        now="2026-08-27T12:01:00Z",
    )
    require(blocked["status"] == "blocked", "resource conflict was not blocked")
    require("overlapping resources" in blocked["reasons"][0], "resource reason missing")
    # MEDIUM-1: a proven overlap against another currently-valid, authorized,
    # managed Issue is exactly the positively-typed benign resource-
    # reservation conflict Stage 3 may retry as ordinary claim_conflict.
    require(
        blocked.get("blocked_kind") == BLOCKED_KIND_DURABLE_RESOURCE_RESERVATION_CONFLICT,
        f"a proven durable resource-reservation overlap must carry the typed benign "
        f"blocked_kind: {blocked}",
    )

    issue_number = next(iter(backend.issues))
    backend.comments[issue_number][0]["body"] = backend.comments[issue_number][0][
        "body"
    ].replace('"worker_id": "agent-a"', '"worker_id": "tampered"')
    observed = service.observe(TASK_ID)
    require(observed["status"] == "conflict", "tampered event history was accepted")

    # An invalid/tampered managed Issue is never benign contention: acquiring
    # against it must fail closed with an exception, never a typed
    # blocked_kind that Stage 3 could retry.
    expect_error(
        lambda: service.acquire_agent_lease(
            task=tasks[TASK_ID],
            source_head=SOURCE_HEAD,
            branch=BRANCH,
            checkout_path=CHECKOUT,
            planned_approach="Resume after tampering.",
            expected_validation="Should fail closed, not retry.",
            now="2026-08-27T12:02:00Z",
        ),
        "invalid workflow state",
    )


def test_durable_ownership_by_other_is_typed_blocked_kind() -> None:
    """MEDIUM-1: another authorized worker's valid agent_working Issue for
    the SAME task, with no exclusive-resource overlap involved, must block
    with the positively-typed BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER --
    exactly the shape Stage 3 maps to ordinary claim_conflict."""

    backend = MemoryIssueBackend()
    solo_task = {
        **task(TASK_ID),
        "exclusive_resources": [],
    }
    tasks = {TASK_ID: solo_task}
    worker_a = IssueWorkflowService(
        backend=backend, task_loader=lambda task_id: tasks[task_id], worker_id="agent-a"
    )
    acquired = worker_a.acquire_agent_lease(
        task=solo_task,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Reserve the task.",
        expected_validation="Held by agent-a.",
        now="2026-08-27T13:00:00Z",
    )
    require(acquired["status"] == "acquired", f"setup lease was not acquired: {acquired}")

    worker_b = IssueWorkflowService(
        backend=backend, task_loader=lambda task_id: tasks[task_id], worker_id="agent-b"
    )
    blocked = worker_b.acquire_agent_lease(
        task=solo_task,
        source_head=SOURCE_HEAD,
        branch="nsc-777-worker-b",
        checkout_path=r"C:\NSC\NSC\NSC-777-worker-b",
        planned_approach="A different worker attempts the same task.",
        expected_validation="Should be blocked as ordinary durable ownership.",
        now="2026-08-27T13:01:00Z",
    )
    require(blocked["status"] == "blocked", f"a different worker's lease attempt was not blocked: {blocked}")
    require(
        blocked.get("blocked_kind") == BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER,
        f"another worker's valid agent_working Issue must carry the typed benign "
        f"blocked_kind: {blocked}",
    )

    # The SAME worker resuming its own lease must never carry a blocked_kind
    # (it is not even blocked -- "resumed" -- so this also proves the
    # blocked_kind is never emitted merely because the state is AGENT_WORKING).
    resumed = worker_a.acquire_agent_lease(
        task=solo_task,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Resume the held task.",
        expected_validation="Still held by agent-a.",
        now="2026-08-27T13:02:00Z",
    )
    require(resumed["status"] == "resumed", f"the owning worker could not resume: {resumed}")
    require("blocked_kind" not in resumed, f"a successful resume must never carry a blocked_kind: {resumed}")


def test_operational_resource_inspection_failure_is_not_benign() -> None:
    """MEDIUM-1 safety boundary: a task-load failure while scanning another
    Issue's reserved resources is an operational failure, not proven ordinary
    contention, even though a real overlap also exists elsewhere. Mixing one
    unprovable conflict into the result must suppress blocked_kind entirely."""

    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    holder = IssueWorkflowService(
        backend=backend, task_loader=lambda task_id: tasks[task_id], worker_id="agent-a"
    )
    holder.acquire_agent_lease(
        task=tasks[OTHER_TASK_ID],
        source_head=SOURCE_HEAD,
        branch="nsc-778-holder",
        checkout_path=r"C:\NSC\NSC\NSC-778",
        planned_approach="Reserve the shared scene under a different task.",
        expected_validation="Held by agent-a.",
        now="2026-08-27T14:00:00Z",
    )

    def failing_task_loader(task_id: str) -> dict:
        if task_id == OTHER_TASK_ID:
            raise RuntimeError("synthetic committed-task load outage")
        return tasks[task_id]

    challenger = IssueWorkflowService(
        backend=backend, task_loader=failing_task_loader, worker_id="agent-b"
    )
    blocked = challenger.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Attempt the overlapping resource.",
        expected_validation="Should be blocked, but never as benign contention.",
        now="2026-08-27T14:01:00Z",
    )
    require(blocked["status"] == "blocked", f"the resource scan should still block: {blocked}")
    require(
        "blocked_kind" not in blocked,
        f"an operational task-load failure must never be misclassified as benign "
        f"typed contention: {blocked}",
    )


def test_untyped_blocked_state_carries_no_blocked_kind() -> None:
    """MEDIUM-1 safety boundary: a workflow state other than agent_ready or
    agent_working (e.g. human_action_required) is an ordinary, unrelated
    blocked shape and must stay untyped/terminal."""

    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID)}
    service = IssueWorkflowService(
        backend=backend, task_loader=lambda task_id: tasks[task_id], worker_id="agent-a"
    )
    service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Implement the task and commit the exact branch.",
        expected_validation="Run checks, then hand Unity validation to Vincent.",
        now="2026-08-27T15:00:00Z",
    )
    service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Implemented the synthetic gameplay behavior and tests.",
        completed_checks=("TaskGraph validation passed.",),
        human_steps=("Open the project.",),
        expected_result="The behavior matches AC-001.",
        now="2026-08-27T15:01:00Z",
    )

    blocked = service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Attempt to re-acquire while awaiting human validation.",
        expected_validation="Should be blocked, but never as benign contention.",
        now="2026-08-27T15:02:00Z",
    )
    require(blocked["status"] == "blocked", f"human_action_required must still block: {blocked}")
    require(
        "blocked_kind" not in blocked,
        f"a non-agent_working blocked state must never carry a blocked_kind: {blocked}",
    )


def main() -> int:
    tests = (
        test_state_event_round_trip_and_chain,
        test_issue_service_handoff_human_result_and_resume,
        test_resource_conflict_and_tampered_history_fail_closed,
        test_durable_ownership_by_other_is_typed_blocked_kind,
        test_operational_resource_inspection_failure_is_not_benign,
        test_untyped_blocked_state_carries_no_blocked_kind,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent issue workflow smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
