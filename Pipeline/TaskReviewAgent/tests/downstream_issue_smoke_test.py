#!/usr/bin/env python3
"""Deterministic tests for downstream Issue approval and resume state."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.downstream_issue import (  # noqa: E402
    DownstreamIssueCoordinator,
    DownstreamIssueError,
)
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    ResumableDownstreamIssueCoordinator,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)

TASK_ID = "NSC-777"
CONTRACT_HASH = "a" * 64
SOURCE_HEAD = "1" * 40
HANDOFF_HEAD = "2" * 40
EVIDENCE_HEAD = "3" * 40
PROPOSAL_SHA = "b" * 64
DRAFT_SHA = "c" * 64
BRANCH = "nsc-777-downstream"
CHECKOUT = r"C:\NSC\NSC\NSC-777"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_error(action, text: str) -> None:
    try:
        action()
    except DownstreamIssueError as exc:
        require(text in str(exc), f"unexpected error: {exc}")
    else:
        raise AssertionError(f"expected downstream error containing {text!r}")


def task() -> dict:
    return {
        "id": TASK_ID,
        "title": "Synthetic downstream task",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Exercise downstream Issue state.",
        "depends_on": [],
        "exclusive_resources": [],
        "acceptance_criteria": [],
        "completion_gates": [
            {"gate_id": "VAL-001", "requirement": "Play Mode validation passes."}
        ],
        "task_contract_sha256": CONTRACT_HASH,
    }


def ready_delivery_service(*, worker: str = "agent-delivery"):
    backend = MemoryIssueBackend()
    item = task()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: item,
        worker_id="agent-implementation",
    )
    service.acquire_agent_lease(
        task=item,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Implement and hand off.",
        expected_validation="Vincent validates in Unity.",
        now="2026-08-27T16:00:00Z",
    )
    service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Implemented the synthetic behavior.",
        completed_checks=("Branch pushed.",),
        human_steps=("Open Unity.", "Verify the behavior."),
        expected_result="The behavior passes.",
        now="2026-08-27T16:01:00Z",
    )
    service.apply_human_result(
        task_id=TASK_ID,
        result_body=(
            "## Human validation result\n\n"
            "Result: PASS\n"
            f"Tested commit: `{HANDOFF_HEAD}`\n"
        ),
        actor_id="cathode26",
        now="2026-08-27T16:02:00Z",
    )
    delivery = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: item,
        worker_id=worker,
    )
    delivery.acquire_agent_lease(
        task=item,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Build authoritative delivery evidence.",
        expected_validation="TaskDelivery review then conformant closeout.",
        now="2026-08-27T16:03:00Z",
    )
    return backend, item, delivery


def request_review(service: IssueWorkflowService) -> dict:
    return DownstreamIssueCoordinator(service).request_delivery_review(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        draft_path=r"C:\Temp\delivery-draft.json",
        draft_sha256=DRAFT_SHA,
        proposal_path=r"C:\Temp\delivery-proposal.json",
        proposal_sha256=PROPOSAL_SHA,
        surface_summary=("Assets/Feature.cs — implementation",),
        gate_summary=("VAL-001 <- unity_01_results",),
        now="2026-08-27T16:04:00Z",
    )


def test_delivery_approval_and_evidence_head_resume() -> None:
    _, item, service = ready_delivery_service()
    handoff = request_review(service)
    state = handoff["workflow_state"]
    require(state["state"] == "blocked", "delivery review did not block")
    require(state["current_actor"] == "human", "delivery review is not human-owned")

    expect_error(
        lambda: DownstreamIssueCoordinator(service).apply_delivery_review(
            task_id=TASK_ID,
            result_body=(
                "## Human delivery evidence review\n\n"
                "Decision: APPROVE\n"
                f"Proposal SHA256: `{'d' * 64}`\n"
            ),
            actor_id="cathode26",
        ),
        "proposal identity",
    )
    approved = DownstreamIssueCoordinator(service).apply_delivery_review(
        task_id=TASK_ID,
        result_body=(
            "## Human delivery evidence review\n\n"
            "Decision: APPROVE\n"
            f"Proposal SHA256: `{PROPOSAL_SHA}`\n"
            "\nNotes:\nApproved as proposed.\n"
        ),
        actor_id="cathode26",
        now="2026-08-27T16:05:00Z",
    )
    require(
        approved["workflow_state"]["phase"] == "merge_closeout",
        "approval did not select merge closeout",
    )

    closeout = IssueWorkflowService(
        backend=service.backend,
        task_loader=lambda task_id: item,
        worker_id="agent-closeout",
    )
    closeout.acquire_agent_lease(
        task=item,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Finalize and publish evidence.",
        expected_validation="Resume exact evidence commit after PR checks.",
        now="2026-08-27T16:06:00Z",
    )
    released = ResumableDownstreamIssueCoordinator(closeout).release_for_pending_checks(
        task_id=TASK_ID,
        pull_request_url="https://example.invalid/pull/88",
        head_commit=EVIDENCE_HEAD,
        reason="Checks are pending.",
        now="2026-08-27T16:07:00Z",
    )
    resumed_state = released["workflow_state"]
    require(resumed_state["state"] == "agent_ready", "lease was not released")
    require(resumed_state["head_commit"] == EVIDENCE_HEAD, "evidence head was not persisted")
    require(
        resumed_state["human_handoff_commit"] == HANDOFF_HEAD,
        "human-tested commit identity was overwritten",
    )


def accept_unchanged_pass(
    service: IssueWorkflowService,
    *,
    now: str,
) -> dict:
    return DownstreamIssueCoordinator(service).accept_unchanged_delivery_after_human_pass(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        draft_path=r"C:\Temp\delivery-draft.json",
        draft_sha256=DRAFT_SHA,
        proposal_path=r"C:\Temp\delivery-proposal.json",
        proposal_sha256=PROPOSAL_SHA,
        now=now,
    )


def test_unchanged_human_pass_skips_second_approval() -> None:
    _, _, service = ready_delivery_service(worker="agent-auto-closeout")
    accepted = accept_unchanged_pass(service, now="2026-08-27T16:04:00Z")
    state = accepted["workflow_state"]
    require(state["state"] == "agent_ready", "automatic acceptance did not release the lease")
    require(state["phase"] == "merge_closeout", "automatic acceptance did not select closeout")
    require(state["human_result"] == "pass", "human PASS was not preserved")
    event = service.find(TASK_ID).events[-1]
    require(
        event.details.get("approval_basis") == "unchanged_human_validated_commit",
        "automatic acceptance did not record its authority basis",
    )
    require(
        event.details.get("authorized_by") == "cathode26",
        "automatic acceptance did not preserve the human authority identity",
    )


def test_legacy_delivery_review_blocker_is_automatically_recovered() -> None:
    _, _, service = ready_delivery_service(worker="agent-legacy-recovery")
    request_review(service)
    accepted = accept_unchanged_pass(service, now="2026-08-27T16:05:00Z")
    state = accepted["workflow_state"]
    require(state["state"] == "agent_ready", "legacy blocker was not released")
    require(
        state["phase"] == "delivery_evidence",
        "legacy blocker did not return through mainline reconciliation",
    )


def test_changed_commit_cannot_reuse_human_pass() -> None:
    _, _, service = ready_delivery_service(worker="agent-drift")
    expect_error(
        lambda: DownstreamIssueCoordinator(service).accept_unchanged_delivery_after_human_pass(
            task_id=TASK_ID,
            branch=BRANCH,
            head_commit=EVIDENCE_HEAD,
            checkout_path=CHECKOUT,
            draft_path=r"C:\Temp\delivery-draft.json",
            draft_sha256=DRAFT_SHA,
            proposal_path=r"C:\Temp\delivery-proposal.json",
            proposal_sha256=PROPOSAL_SHA,
        ),
        "unchanged human-tested commit",
    )


def test_delivery_changes_return_to_delivery_evidence() -> None:
    _, _, service = ready_delivery_service(worker="agent-revise")
    request_review(service)
    changed = DownstreamIssueCoordinator(service).apply_delivery_review(
        task_id=TASK_ID,
        result_body=(
            "## Human delivery evidence review\n\n"
            "Decision: REQUEST_CHANGES\n"
            f"Proposal SHA256: `{PROPOSAL_SHA}`\n"
            "\nNotes:\nMap VAL-001 only to the Play Mode XML.\n"
        ),
        actor_id="cathode26",
        now="2026-08-27T17:00:00Z",
    )
    require(
        changed["workflow_state"]["phase"] == "delivery_evidence",
        "requested changes did not return to delivery evidence",
    )
    require(
        changed["workflow_state"]["state"] == "agent_ready",
        "requested changes did not return agent-ready",
    )


def main() -> int:
    tests = (
        test_delivery_approval_and_evidence_head_resume,
        test_unchanged_human_pass_skips_second_approval,
        test_legacy_delivery_review_blocker_is_automatically_recovered,
        test_changed_commit_cannot_reuse_human_pass,
        test_delivery_changes_return_to_delivery_evidence,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent downstream Issue tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
