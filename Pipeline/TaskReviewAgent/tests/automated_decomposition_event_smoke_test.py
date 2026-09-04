#!/usr/bin/env python3
"""Deterministic tests for automated private-gauntlet decomposition approval."""

from __future__ import annotations

import copy
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.contracts import semantic_sha256  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    AUTOMATED_DECOMPOSITION_EVIDENCE_AUTHORITY,
    AUTOMATED_DECOMPOSITION_EVIDENCE_SCHEMA_VERSION,
    AUTOMATED_DECOMPOSITION_POLICY_AUTHORITY,
    AUTOMATED_DECOMPOSITION_REVIEW_AUTHORITY,
    AUTOMATED_DECOMPOSITION_REVIEW_STATUS,
    AUTOMATED_VALIDATION_GAUNTLET_ID,
    AUTOMATED_VALIDATION_REPOSITORY,
    IssueWorkflowEvent,
    WorkflowActor,
    WorkflowContractError,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    parse_events,
    transition,
    validate_event_chain,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    IssueWorkflowStoreError,
    MemoryIssueBackend,
)

TASK_ID = "NSC-911"
CONTRACT_HASH = "a" * 64
PARENT_HASH = "b" * 64
SOURCE_COMMIT = "1" * 40
SOURCE_TREE = "2" * 40
PLAN_ID = "GDP-" + ("3" * 64)
GRAPH_DELTA_HASH = "4" * 64
DECOMPOSITION_RESULT_HASH = "5" * 64
POLICY_HASH = "6" * 64
BRANCH = "nsc-911-synthetic-gauntlet"
CHECKOUT = r"C:\NSC\Rehearsal\NSC-911"
WORKER_ID = "synthetic-decomposition-service"
PARENT_RESOURCES = [
    "repo-file:Assets/Gauntlet/MuffcabbageGauntlet911Alpha.cs",
    "repo-file:Assets/Gauntlet/MuffcabbageGauntlet911Alpha.cs.meta",
    "repo-file:Assets/Gauntlet/MuffcabbageGauntlet911Beta.cs",
    "repo-file:Assets/Gauntlet/MuffcabbageGauntlet911Beta.cs.meta",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_store_error(action, text: str) -> None:
    try:
        action()
    except IssueWorkflowStoreError as exc:
        require(text in str(exc), f"unexpected error: {exc}")
    else:
        raise AssertionError(f"expected IssueWorkflowStoreError containing {text!r}")


def expect_contract_error(action, text: str) -> None:
    try:
        action()
    except WorkflowContractError as exc:
        require(text in str(exc), f"unexpected error: {exc}")
    else:
        raise AssertionError(f"expected WorkflowContractError containing {text!r}")


def task() -> dict:
    return {
        "id": TASK_ID,
        "title": "Split the synthetic Alpha and Beta values",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "decomposable",
        "decomposition_state": "candidate",
        "execution_reason": "Exercise private rehearsal decomposition.",
        "depends_on": [],
        "exclusive_resources": list(PARENT_RESOURCES),
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "requirement": "Alpha and Beta are separate."}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "requirement": "Both exact child tests pass."}
        ],
        "provenance": {
            "origin": "human_approved_synthetic_gauntlet",
            "gauntlet_id": AUTOMATED_VALIDATION_GAUNTLET_ID,
            "requires_decomposition": True,
        },
        "task_contract_sha256": CONTRACT_HASH,
    }


class VerifyingService(IssueWorkflowService):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.post_verification_calls = 0

    def verify_post_mutation_state(self, *args, **kwargs):
        self.post_verification_calls += 1
        return super().verify_post_mutation_state(*args, **kwargs)


def waiting_service() -> tuple[VerifyingService, MemoryIssueBackend, dict]:
    backend = MemoryIssueBackend()
    selected = task()
    service = VerifyingService(
        backend=backend,
        task_loader=lambda _task_id: selected,
        worker_id=WORKER_ID,
    )
    service.acquire_agent_lease(
        task=selected,
        source_head=SOURCE_COMMIT,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Produce and independently review one exact graph delta.",
        expected_validation="Require a fresh disjoint two-child partition.",
        now="2026-09-04T13:00:00Z",
    )
    service.publish_decomposition_handoff(
        task_id=TASK_ID,
        source_head=SOURCE_COMMIT,
        checkout_path=CHECKOUT,
        decomposition_run_id="20260904-130100Z",
        artifact_root=(
            r"C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput"
            r"\NSC-911\20260904-130100Z"
        ),
        graph_delta_plan_id=PLAN_ID,
        graph_delta_sha256=GRAPH_DELTA_HASH,
        summary="Fresh two-child Alpha/Beta split passed independent review.",
        branch=BRANCH,
        now="2026-09-04T13:01:00Z",
    )
    state = service.find(TASK_ID).state
    assert state is not None
    evidence = {
        "schema_version": AUTOMATED_DECOMPOSITION_EVIDENCE_SCHEMA_VERSION,
        "authority": AUTOMATED_DECOMPOSITION_EVIDENCE_AUTHORITY,
        "repository": AUTOMATED_VALIDATION_REPOSITORY,
        "repository_private": True,
        "gauntlet_id": AUTOMATED_VALIDATION_GAUNTLET_ID,
        "task_id": TASK_ID,
        "handoff_event_id": state.last_event_id,
        "branch": BRANCH,
        "source_commit": SOURCE_COMMIT,
        "source_tree": SOURCE_TREE,
        "task_contract_sha256": CONTRACT_HASH,
        "graph_delta_plan_id": PLAN_ID,
        "graph_delta_sha256": GRAPH_DELTA_HASH,
        "decomposition_result_sha256": DECOMPOSITION_RESULT_HASH,
        "parent_contract_sha256": PARENT_HASH,
        "parent_exclusive_resources": list(PARENT_RESOURCES),
        "children": [
            {
                "task_id": "NSC-991",
                "task_contract_sha256": "7" * 64,
                "exclusive_resources": list(PARENT_RESOURCES[:2]),
            },
            {
                "task_id": "NSC-992",
                "task_contract_sha256": "8" * 64,
                "exclusive_resources": list(PARENT_RESOURCES[2:]),
            },
        ],
        "validation_policy_authority": AUTOMATED_DECOMPOSITION_POLICY_AUTHORITY,
        "validation_policy_sha256": POLICY_HASH,
        "review": {
            "authority": AUTOMATED_DECOMPOSITION_REVIEW_AUTHORITY,
            "status": AUTOMATED_DECOMPOSITION_REVIEW_STATUS,
            "fresh_plan_status": "fresh",
            "recomputed_plan_id": PLAN_ID,
            "exact_child_count": 2,
            "resources_disjoint": True,
            "resources_partition_parent": True,
        },
    }
    service.post_verification_calls = 0
    return service, backend, evidence


def test_exact_review_advances_without_fabricating_human_approval() -> None:
    service, backend, evidence = waiting_service()
    result = service.apply_automated_decomposition_result(
        task_id=TASK_ID,
        evidence=evidence,
        actor_id=WORKER_ID,
        now="2026-09-04T13:02:00Z",
    )
    state = service.find(TASK_ID).state
    assert state is not None
    require(result["status"] == "agent_ready", str(result))
    require(result["decision"] == "approve", str(result))
    require(state.state is WorkflowState.AGENT_READY, str(state))
    require(state.phase is WorkflowPhase.DECOMPOSITION_APPLY, str(state))
    require(state.current_actor is WorkflowActor.AGENT, str(state))
    require(state.human_result is None, "automated review fabricated human approval")
    require(service.post_verification_calls == 1, "post-verification was skipped")
    issue = backend.list_issues()[0]
    event = parse_events(backend.get_comments(issue["number"]))[-1]
    require(
        event.event_type
        is WorkflowEventType.AUTOMATED_DECOMPOSITION_APPLICATION_APPROVED,
        str(event),
    )
    require(event.actor_type is WorkflowActor.AGENT, str(event))
    require(event.actor_id == WORKER_ID, str(event))
    require(event.details == evidence, "decomposition evidence changed in persistence")
    require(result["automated_decomposition_event_id"] == event.event_id, str(result))


def _assert_rejected_without_mutation(mutator, expected: str) -> None:
    service, backend, evidence = waiting_service()
    issues_before = copy.deepcopy(backend.list_issues())
    comments_before = copy.deepcopy(backend.get_comments(issues_before[0]["number"]))
    mutator(evidence)
    expect_store_error(
        lambda: service.apply_automated_decomposition_result(
            task_id=TASK_ID,
            evidence=evidence,
            actor_id=WORKER_ID,
            now="2026-09-04T13:02:00Z",
        ),
        expected,
    )
    require(backend.list_issues() == issues_before, "invalid evidence mutated the Issue")
    require(
        backend.get_comments(issues_before[0]["number"]) == comments_before,
        "invalid evidence appended a workflow event",
    )
    require(service.post_verification_calls == 0, "invalid evidence reached verification")


def test_envelope_and_handoff_bindings_are_exact() -> None:
    cases = (
        (lambda e: e.update(extra=True), "keys mismatch"),
        (lambda e: e.pop("source_tree"), "keys mismatch"),
        (lambda e: e.update(repository="cathode26/NoSafeCircle"), "repository must be exactly"),
        (lambda e: e.update(repository_private=False), "repository_private must be exactly"),
        (lambda e: e.update(gauntlet_id="other"), "gauntlet_id must be exactly"),
        (lambda e: e.update(task_id="NSC-912"), "task_id does not match"),
        (lambda e: e.update(task_id="not-a-task"), "task_id has an invalid identity"),
        (lambda e: e.update(handoff_event_id="9" * 64), "handoff_event_id does not match"),
        (lambda e: e.update(branch="other"), "branch does not match"),
        (lambda e: e.update(source_commit="9" * 40), "source_commit does not match"),
        (lambda e: e.update(source_tree="bad"), "source_tree"),
        (lambda e: e.update(task_contract_sha256="9" * 64), "task contract"),
        (lambda e: e.update(parent_contract_sha256="bad"), "parent_contract_sha256"),
        (
            lambda e: e.update(graph_delta_plan_id="GDP-" + ("9" * 64)),
            "graph_delta_plan_id does not match",
        ),
        (lambda e: e.update(graph_delta_sha256="9" * 64), "graph_delta_sha256 does not match"),
        (lambda e: e.update(decomposition_result_sha256="bad"), "decomposition_result_sha256"),
        (lambda e: e.update(validation_policy_authority="wrong"), "validation_policy_authority"),
        (lambda e: e.update(validation_policy_sha256="bad"), "validation_policy_sha256"),
    )
    for mutator, expected in cases:
        _assert_rejected_without_mutation(mutator, expected)


def test_exact_two_child_disjoint_partition_is_required() -> None:
    cases = (
        (lambda e: e["children"].pop(), "exactly two children"),
        (lambda e: e["children"].reverse(), "task IDs must be sorted"),
        (lambda e: e["children"][1].update(task_id="NSC-991"), "sorted and unique"),
        (lambda e: e["children"][0].update(task_contract_sha256="bad"), "task_contract_sha256"),
        (
            lambda e: e["children"][1].update(
                exclusive_resources=list(e["children"][0]["exclusive_resources"])
            ),
            "resources must be disjoint",
        ),
        (
            lambda e: e["children"][1]["exclusive_resources"].__setitem__(
                0, "repo-file:Assets/Gauntlet/AAAAUnexpected.cs"
            ),
            "exactly partition",
        ),
        (
            lambda e: e["children"][0]["exclusive_resources"].reverse(),
            "sorted and unique",
        ),
        (
            lambda e: e["parent_exclusive_resources"].pop(),
            "exactly 4 resources",
        ),
        (
            lambda e: e["children"][0]["exclusive_resources"].__setitem__(
                0, "logical:not-a-file"
            ),
            "canonical Assets repo-file",
        ),
        (lambda e: e["children"][0].update(extra=True), "keys mismatch"),
    )
    for mutator, expected in cases:
        _assert_rejected_without_mutation(mutator, expected)


def test_review_decomposition_plan_result_is_pinned() -> None:
    cases = (
        (lambda e: e["review"].update(status="review_ready"), "review status"),
        (lambda e: e["review"].update(fresh_plan_status="already_applied"), "fresh_plan_status"),
        (
            lambda e: e["review"].update(
                recomputed_plan_id="GDP-" + ("9" * 64)
            ),
            "recomputed_plan_id",
        ),
        (lambda e: e["review"].update(exact_child_count=3), "exact_child_count"),
        (lambda e: e["review"].update(resources_disjoint=False), "resources_disjoint"),
        (
            lambda e: e["review"].update(resources_partition_parent=False),
            "resources_partition_parent",
        ),
        (lambda e: e["review"].update(extra=True), "keys mismatch"),
    )
    for mutator, expected in cases:
        _assert_rejected_without_mutation(mutator, expected)


def test_actor_phase_and_target_are_fail_closed() -> None:
    service, backend, evidence = waiting_service()
    issues_before = copy.deepcopy(backend.list_issues())
    expect_store_error(
        lambda: service.apply_automated_decomposition_result(
            task_id=TASK_ID,
            evidence=[],  # type: ignore[arg-type]
            actor_id=WORKER_ID,
            now="2026-09-04T13:02:00Z",
        ),
        "evidence must be an object",
    )
    expect_store_error(
        lambda: service.apply_automated_decomposition_result(
            task_id=TASK_ID,
            evidence=evidence,
            actor_id="another-worker",
            now="2026-09-04T13:02:00Z",
        ),
        "authenticated service worker",
    )
    require(backend.list_issues() == issues_before, "wrong actor mutated Issue")
    state = service.find(TASK_ID).state
    assert state is not None
    base = {
        "event_type": WorkflowEventType.AUTOMATED_DECOMPOSITION_APPLICATION_APPROVED,
        "actor_type": WorkflowActor.AGENT,
        "actor_id": WORKER_ID,
        "to_state": WorkflowState.AGENT_READY,
        "to_phase": WorkflowPhase.DECOMPOSITION_APPLY,
        "details": evidence,
        "now": "2026-09-04T13:02:00Z",
    }
    expect_contract_error(
        lambda: transition(state, **{**base, "actor_type": WorkflowActor.HUMAN}),
        "target state or actor",
    )
    expect_contract_error(
        lambda: transition(
            replace(state, phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION), **base
        ),
        "decomposition_apply_authorization phase",
    )
    expect_contract_error(
        lambda: transition(
            state, **{**base, "to_phase": WorkflowPhase.DECOMPOSITION}
        ),
        "must enter decomposition_apply",
    )


def test_event_chain_revalidates_handoff_and_evidence() -> None:
    service, backend, evidence = waiting_service()
    service.apply_automated_decomposition_result(
        task_id=TASK_ID,
        evidence=evidence,
        actor_id=WORKER_ID,
        now="2026-09-04T13:02:00Z",
    )
    snapshot = service.find(TASK_ID)
    assert snapshot is not None and snapshot.state is not None
    events = list(parse_events(backend.get_comments(snapshot.issue_number)))
    original = events[-1]
    forged_details = copy.deepcopy(original.details)
    forged_details["graph_delta_sha256"] = "9" * 64
    forged = IssueWorkflowEvent.create(
        task_id=original.task_id,
        sequence=original.sequence,
        previous_event_id=original.previous_event_id,
        event_type=original.event_type,
        from_state=original.from_state,
        to_state=original.to_state,
        from_phase=original.from_phase,
        to_phase=original.to_phase,
        actor_type=original.actor_type,
        actor_id=original.actor_id,
        task_contract_sha256=original.task_contract_sha256,
        occurred_at_utc=original.occurred_at_utc,
        details=forged_details,
    )
    events[-1] = forged
    forged_state = replace(snapshot.state, last_event_id=forged.event_id)
    expect_contract_error(
        lambda: validate_event_chain(forged_state, events),
        "graph_delta_sha256 does not match",
    )


def test_existing_human_approval_event_is_byte_compatible() -> None:
    service, backend, _evidence = waiting_service()
    body = (
        "## Decomposition application result\n\n"
        "Result: APPROVE\n"
        f"Reviewed plan_id: `{PLAN_ID}`\n"
    )
    result = service.apply_decomposition_result(
        task_id=TASK_ID,
        result_body=body,
        actor_id="cathode26",
        now="2026-09-04T13:02:00Z",
    )
    event = parse_events(backend.get_comments(result["issue_number"]))[-1]
    require(
        event.event_type is WorkflowEventType.DECOMPOSITION_APPLICATION_APPROVED,
        str(event),
    )
    require(event.actor_type is WorkflowActor.HUMAN, str(event))
    require(
        event.details
        == {
            "reviewed_plan_id": PLAN_ID,
            "human_comment_sha256": semantic_sha256({"body": body}),
        },
        str(event.details),
    )


def main() -> int:
    tests = (
        test_exact_review_advances_without_fabricating_human_approval,
        test_envelope_and_handoff_bindings_are_exact,
        test_exact_two_child_disjoint_partition_is_required,
        test_review_decomposition_plan_result_is_pinned,
        test_actor_phase_and_target_are_fail_closed,
        test_event_chain_revalidates_handoff_and_evidence,
        test_existing_human_approval_event_is_byte_compatible,
    )
    for test_case in tests:
        test_case()
        print(f"PASS {test_case.__name__}")
    print(f"PASS automated decomposition event smoke suite ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
