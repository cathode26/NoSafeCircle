#!/usr/bin/env python3
"""Deterministic tests for the private synthetic automated-validation event."""

from __future__ import annotations

import copy
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    AUTOMATED_VALIDATION_EVIDENCE_AUTHORITY,
    AUTOMATED_VALIDATION_EVIDENCE_SCHEMA_VERSION,
    AUTOMATED_VALIDATION_GAUNTLET_ID,
    AUTOMATED_VALIDATION_REPOSITORY,
    WorkflowActor,
    WorkflowContractError,
    IssueWorkflowEvent,
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

TASK_ID = "NSC-912"
CONTRACT_HASH = "a" * 64
SOURCE_HEAD = "1" * 40
HANDOFF_HEAD = "2" * 40
HANDOFF_TREE = "3" * 40
BRANCH = "nsc-912-synthetic-gauntlet"
CHECKOUT = r"C:\NSC\Rehearsal\NSC-912"
WORKER_ID = "synthetic-validation-service"


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
        "title": "Set one synthetic ScriptableObject value",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Exercise private rehearsal automation.",
        "depends_on": [],
        "exclusive_resources": [
            "repo-file:Assets/SyntheticGauntlet/NSC912Value.cs"
        ],
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "requirement": "The value is 912."}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "requirement": "The exact Edit Mode test passes."}
        ],
        "provenance": {
            "origin": "human_approved_synthetic_gauntlet",
            "gauntlet_id": AUTOMATED_VALIDATION_GAUNTLET_ID,
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
        task_loader=lambda task_id: selected,
        worker_id=WORKER_ID,
    )
    service.acquire_agent_lease(
        task=selected,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Change the one exact synthetic value.",
        expected_validation="Run the committed exact Edit Mode filter.",
        now="2026-09-04T12:00:00Z",
    )
    service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Changed the synthetic value.",
        completed_checks=("Committed and pushed the exact branch.",),
        human_steps=("Confirm the synthetic value.",),
        expected_result="The value is 912.",
        now="2026-09-04T12:01:00Z",
    )
    state = service.find(TASK_ID).state
    assert state is not None
    evidence = {
        "schema_version": AUTOMATED_VALIDATION_EVIDENCE_SCHEMA_VERSION,
        "authority": AUTOMATED_VALIDATION_EVIDENCE_AUTHORITY,
        "repository": AUTOMATED_VALIDATION_REPOSITORY,
        "repository_private": True,
        "gauntlet_id": AUTOMATED_VALIDATION_GAUNTLET_ID,
        "task_id": TASK_ID,
        "handoff_event_id": state.last_event_id,
        "branch": BRANCH,
        "commit": HANDOFF_HEAD,
        "tree": HANDOFF_TREE,
        "task_contract_sha256": CONTRACT_HASH,
        "validation_policy_authority": (
            "committed_private_synthetic_gauntlet_validation_policy"
        ),
        "validation_policy_sha256": "4" * 64,
        "required_validations": [
            {
                "test_platform": "EditMode",
                "test_filter": "NoSafeCircle.SyntheticGauntlet.Tests.NSC912Tests",
            }
        ],
        "unity_validations": [
            {
                "test_platform": "EditMode",
                "test_filter": "NoSafeCircle.SyntheticGauntlet.Tests.NSC912Tests",
                "manifest_sha256": "5" * 64,
                "xml_sha256": "6" * 64,
                "log_sha256": "7" * 64,
                "commit": HANDOFF_HEAD,
                "tree": HANDOFF_TREE,
                "post_commit": HANDOFF_HEAD,
                "post_tree": HANDOFF_TREE,
                "repository_clean_before": True,
                "repository_clean_after": True,
                "total": 2,
                "passed": 2,
                "failed": 0,
                "skipped": 0,
            }
        ],
    }
    # Do not count setup transitions as verification of the method under test.
    service.post_verification_calls = 0
    return service, backend, evidence


def test_exact_evidence_advances_without_fabricating_human_pass() -> None:
    service, backend, evidence = waiting_service()
    result = service.apply_automated_validation(
        task_id=TASK_ID,
        evidence=evidence,
        actor_id=WORKER_ID,
        now="2026-09-04T12:02:00Z",
    )
    state = service.find(TASK_ID).state
    assert state is not None
    require(result["status"] == "agent_ready", str(result))
    require(state.state is WorkflowState.AGENT_READY, str(state))
    require(state.phase is WorkflowPhase.DELIVERY_EVIDENCE, str(state))
    require(state.current_actor is WorkflowActor.AGENT, str(state))
    require(state.human_result is None, "automated evidence fabricated human PASS")
    require(service.post_verification_calls == 1, "post-mutation verification was skipped")
    issue = backend.list_issues()[0]
    events = parse_events(backend.get_comments(issue["number"]))
    event = events[-1]
    require(
        event.event_type is WorkflowEventType.AUTOMATED_VALIDATION_PASSED,
        str(event),
    )
    require(event.actor_type is WorkflowActor.AGENT, str(event))
    require(event.actor_id == WORKER_ID, str(event))
    require(event.details == evidence, "evidence envelope changed during persistence")
    require(result["automated_validation_event_id"] == event.event_id, str(result))


def _assert_rejected_without_mutation(mutator, expected: str) -> None:
    service, backend, evidence = waiting_service()
    issue_before = copy.deepcopy(backend.list_issues())
    comments_before = copy.deepcopy(backend.get_comments(issue_before[0]["number"]))
    mutator(evidence)
    expect_store_error(
        lambda: service.apply_automated_validation(
            task_id=TASK_ID,
            evidence=evidence,
            actor_id=WORKER_ID,
            now="2026-09-04T12:02:00Z",
        ),
        expected,
    )
    require(backend.list_issues() == issue_before, "invalid evidence mutated the Issue")
    require(
        backend.get_comments(issue_before[0]["number"]) == comments_before,
        "invalid evidence appended a comment",
    )
    require(service.post_verification_calls == 0, "invalid evidence reached post-verification")


def test_envelope_identity_and_policy_are_strict() -> None:
    cases = (
        (lambda e: e.update(extra=True), "keys mismatch"),
        (lambda e: e.pop("tree"), "keys mismatch"),
        (lambda e: e.update(repository="cathode26/NoSafeCircle"), "repository must be exactly"),
        (lambda e: e.update(repository_private=False), "repository_private must be exactly"),
        (lambda e: e.update(gauntlet_id="other"), "gauntlet_id must be exactly"),
        (lambda e: e.update(task_id="NSC-913"), "task_id does not match"),
        (lambda e: e.update(task_id="not-a-task"), "task_id has an invalid identity"),
        (lambda e: e.update(handoff_event_id="8" * 64), "current handoff event"),
        (lambda e: e.update(branch="other"), "branch does not match"),
        (lambda e: e.update(commit="8" * 40), "current handoff"),
        (lambda e: e.update(tree="not-a-tree"), "tree has an invalid identity"),
        (lambda e: e.update(task_contract_sha256="8" * 64), "task contract does not match"),
        (
            lambda e: e.update(validation_policy_authority="uncommitted_policy"),
            "policy authority",
        ),
        (lambda e: e.update(validation_policy_sha256="bad"), "policy_sha256"),
    )
    for mutator, expected in cases:
        _assert_rejected_without_mutation(mutator, expected)


def test_platform_filter_and_unity_artifacts_are_strict() -> None:
    cases = (
        (lambda e: e.update(required_validations=[]), "non-empty list"),
        (
            lambda e: e["required_validations"][0].update(extra=True),
            "keys mismatch",
        ),
        (
            lambda e: e["required_validations"][0].update(test_platform="Runtime"),
            "EditMode or PlayMode",
        ),
        (
            lambda e: e["unity_validations"][0].update(test_filter="Different.Tests"),
            "does not exactly match",
        ),
        (
            lambda e: e["unity_validations"][0].update(manifest_sha256="bad"),
            "manifest_sha256",
        ),
        (
            lambda e: e["unity_validations"][0].update(xml_sha256="bad"),
            "xml_sha256",
        ),
        (
            lambda e: e["unity_validations"][0].update(log_sha256="bad"),
            "log_sha256",
        ),
        (
            lambda e: e["unity_validations"][0].update(post_commit="8" * 40),
            "post_commit does not match",
        ),
        (
            lambda e: e["unity_validations"][0].update(post_tree="8" * 40),
            "post_tree does not match",
        ),
        (
            lambda e: e["unity_validations"][0].update(repository_clean_before=1),
            "repository_clean_before",
        ),
        (
            lambda e: e["unity_validations"][0].update(repository_clean_after=False),
            "repository_clean_after",
        ),
        (
            lambda e: e["unity_validations"][0].update(passed=0, total=0),
            "one or more passing tests",
        ),
        (
            lambda e: e["unity_validations"][0].update(failed=1, total=3),
            "zero failures",
        ),
        (
            lambda e: e["unity_validations"][0].update(total=3),
            "must equal passed + failed + skipped",
        ),
        (
            lambda e: e["unity_validations"][0].update(extra=True),
            "keys mismatch",
        ),
    )
    for mutator, expected in cases:
        _assert_rejected_without_mutation(mutator, expected)


def test_multiple_required_validations_must_be_sorted_unique_and_exactly_covered() -> None:
    def duplicate(e):
        e["required_validations"].append(copy.deepcopy(e["required_validations"][0]))
        e["unity_validations"].append(copy.deepcopy(e["unity_validations"][0]))

    _assert_rejected_without_mutation(duplicate, "sorted and unique")

    def unsorted(e):
        second_required = {
            "test_platform": "PlayMode",
            "test_filter": "NoSafeCircle.SyntheticGauntlet.Tests.NSC912PlayModeTests",
        }
        second_unity = copy.deepcopy(e["unity_validations"][0])
        second_unity.update(second_required)
        e["required_validations"] = [second_required, *e["required_validations"]]
        e["unity_validations"] = [second_unity, *e["unity_validations"]]

    _assert_rejected_without_mutation(unsorted, "sorted and unique")

    _assert_rejected_without_mutation(
        lambda e: e["unity_validations"].clear(),
        "exactly cover",
    )


def test_actor_must_match_service_worker() -> None:
    service, backend, evidence = waiting_service()
    issue_before = copy.deepcopy(backend.list_issues())
    expect_store_error(
        lambda: service.apply_automated_validation(
            task_id=TASK_ID,
            evidence=evidence,
            actor_id="another-worker",
            now="2026-09-04T12:02:00Z",
        ),
        "authenticated service worker",
    )
    require(backend.list_issues() == issue_before, "wrong actor mutated the Issue")


def test_state_machine_rejects_wrong_actor_phase_and_target() -> None:
    service, _backend, evidence = waiting_service()
    state = service.find(TASK_ID).state
    assert state is not None
    base = {
        "event_type": WorkflowEventType.AUTOMATED_VALIDATION_PASSED,
        "actor_type": WorkflowActor.AGENT,
        "actor_id": WORKER_ID,
        "to_state": WorkflowState.AGENT_READY,
        "to_phase": WorkflowPhase.DELIVERY_EVIDENCE,
        "details": evidence,
        "now": "2026-09-04T12:02:00Z",
    }
    expect_contract_error(
        lambda: transition(state, **{**base, "actor_type": WorkflowActor.HUMAN}),
        "target state or actor",
    )
    expect_contract_error(
        lambda: transition(
            replace(state, phase=WorkflowPhase.DECOMPOSITION_APPLY_AUTHORIZATION),
            **base,
        ),
        "requires unity_runtime_validation",
    )
    expect_contract_error(
        lambda: transition(
            state,
            **{**base, "to_phase": WorkflowPhase.REPAIR},
        ),
        "must enter delivery_evidence",
    )


def test_event_chain_revalidates_evidence_instead_of_trusting_its_hash() -> None:
    service, backend, evidence = waiting_service()
    service.apply_automated_validation(
        task_id=TASK_ID,
        evidence=evidence,
        actor_id=WORKER_ID,
        now="2026-09-04T12:02:00Z",
    )
    snapshot = service.find(TASK_ID)
    assert snapshot is not None and snapshot.state is not None
    events = list(parse_events(backend.get_comments(snapshot.issue_number)))
    original = events[-1]
    forged_details = copy.deepcopy(original.details)
    forged_details["repository"] = "cathode26/NoSafeCircle"
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
        "repository must be exactly",
    )


def test_existing_human_pass_semantics_remain_unchanged() -> None:
    service, _backend, _evidence = waiting_service()
    result = service.apply_human_result(
        task_id=TASK_ID,
        result_body=(
            "## Human validation result\n\n"
            "Result: PASS\n"
            f"Tested commit: `{HANDOFF_HEAD}`\n"
        ),
        actor_id="cathode26",
        now="2026-09-04T12:02:00Z",
    )
    state = service.find(TASK_ID).state
    assert state is not None
    require(result["status"] == "agent_ready", str(result))
    require(state.human_result == "pass", "human PASS no longer records human_result")
    events = parse_events(service.backend.get_comments(result["issue_number"]))
    require(events[-1].event_type is WorkflowEventType.HUMAN_VALIDATION_PASSED, str(events[-1]))


def main() -> int:
    tests = (
        test_exact_evidence_advances_without_fabricating_human_pass,
        test_envelope_identity_and_policy_are_strict,
        test_platform_filter_and_unity_artifacts_are_strict,
        test_multiple_required_validations_must_be_sorted_unique_and_exactly_covered,
        test_actor_must_match_service_worker,
        test_state_machine_rejects_wrong_actor_phase_and_target,
        test_event_chain_revalidates_evidence_instead_of_trusting_its_hash,
        test_existing_human_pass_semantics_remain_unchanged,
    )
    for test_case in tests:
        test_case()
        print(f"PASS {test_case.__name__}")
    print(f"PASS automated validation event smoke suite ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
