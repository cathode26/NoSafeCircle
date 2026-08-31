#!/usr/bin/env python3
"""Repo-wide stale-read regression tests for direct Issue transitions."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.issue_workflow_store as store_module  # noqa: E402
from Pipeline.TaskReviewAgent.claim_refs import _exact_authority_failures  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_issue import (  # noqa: E402
    DownstreamIssueCoordinator,
)
from Pipeline.TaskReviewAgent.downstream_resilience import (  # noqa: E402
    _release_active_lease as release_resilience_lease,
)
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    ResumableDownstreamIssueCoordinator,
)
from Pipeline.TaskReviewAgent.goal_loop_guard import GuardedTaskController  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    STATE_LABELS,
    WorkflowPhase,
    WorkflowState,
    labels_for_state,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    IssueWorkflowStoreError,
)
from Pipeline.TaskReviewAgent.mainline_reintegration import (  # noqa: E402
    _advance_automation_only_issue,
    _block_current_lease,
)
from Pipeline.TaskReviewAgent.production_pipeline import (  # noqa: E402
    ProductionTaskController,
)
from Pipeline.TaskReviewAgent.tests.issue_workflow_smoke_test import (  # noqa: E402
    LaggyMemoryIssueBackend,
)


TASK_ID = "NSC-777"
WORKER = "post-mutation-verification-agent"
CONTRACT_HASH = "a" * 64
SOURCE_HEAD = "1" * 40
HUMAN_HEAD = "2" * 40
EVIDENCE_HEAD = "3" * 40
INTEGRATED_HEAD = "4" * 40
BRANCH = "nsc-777-post-mutation-verification"
CHECKOUT = r"C:\NSC\NSC\NSC-777"
PROPOSAL_SHA = "b" * 64
DRAFT_SHA = "c" * 64


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def task() -> dict[str, Any]:
    return {
        "id": TASK_ID,
        "title": "Synthetic post-mutation verification task",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Exercise bounded Issue verification.",
        "depends_on": [],
        "exclusive_resources": [],
        "acceptance_criteria": [],
        "completion_gates": [],
        "task_contract_sha256": CONTRACT_HASH,
    }


@contextmanager
def immediate_verification_reads(attempts: int = 3) -> Iterator[None]:
    original = store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS
    store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS = (0.0,) * attempts
    try:
        yield
    finally:
        store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS = original


def active_service(
    phase: WorkflowPhase,
) -> tuple[LaggyMemoryIssueBackend, IssueWorkflowService]:
    backend = LaggyMemoryIssueBackend(stale_reads_per_update=0)
    item = task()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda _task_id: item,
        worker_id=WORKER,
    )
    service.acquire_agent_lease(
        task=item,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Prepare the requested workflow phase.",
        expected_validation="The synthetic transition is exact.",
        now="2026-08-31T10:00:00Z",
    )
    if phase is WorkflowPhase.IMPLEMENTATION:
        return backend, service

    service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HUMAN_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Synthetic implementation is ready.",
        completed_checks=("Python fixture passed.",),
        human_steps=("Validate the synthetic behavior.",),
        expected_result="The synthetic behavior passes.",
        now="2026-08-31T10:01:00Z",
    )
    service.apply_human_result(
        task_id=TASK_ID,
        result_body=(
            "## Human validation result\n\n"
            "Result: PASS\n"
            f"Tested commit: `{HUMAN_HEAD}`\n"
        ),
        actor_id="cathode26",
        now="2026-08-31T10:02:00Z",
    )
    service.acquire_agent_lease(
        task=item,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Prepare delivery evidence.",
        expected_validation="The delivery transition is exact.",
        now="2026-08-31T10:03:00Z",
    )
    if phase is WorkflowPhase.DELIVERY_EVIDENCE:
        return backend, service

    request_delivery_review(service)
    apply_delivery_approval(service)
    service.acquire_agent_lease(
        task=item,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Prepare merge closeout.",
        expected_validation="The closeout transition is exact.",
        now="2026-08-31T10:06:00Z",
    )
    return backend, service


def request_delivery_review(service: IssueWorkflowService) -> dict[str, Any]:
    return DownstreamIssueCoordinator(service).request_delivery_review(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HUMAN_HEAD,
        checkout_path=CHECKOUT,
        draft_path=r"C:\Temp\delivery-draft.json",
        draft_sha256=DRAFT_SHA,
        proposal_path=r"C:\Temp\delivery-proposal.json",
        proposal_sha256=PROPOSAL_SHA,
        surface_summary=("Pipeline/TaskReviewAgent/synthetic.py",),
        gate_summary=("VAL-001 <- synthetic result",),
        now="2026-08-31T10:04:00Z",
    )


def apply_delivery_approval(service: IssueWorkflowService) -> dict[str, Any]:
    return DownstreamIssueCoordinator(service).apply_delivery_review(
        task_id=TASK_ID,
        result_body=(
            "## Human delivery evidence review\n\n"
            "Decision: APPROVE\n"
            f"Proposal SHA256: `{PROPOSAL_SHA}`\n"
        ),
        actor_id="cathode26",
        now="2026-08-31T10:05:00Z",
    )


class FakeWorkflow:
    def __init__(self, service: IssueWorkflowService) -> None:
        self.issue_workflow = service
        self.worker_id = WORKER

    def observe_goal_state(self) -> dict[str, Any]:
        return {}

    def acquire_agent_lease(self, **_values: Any) -> dict[str, Any]:
        return {"status": "synthetic_reacquire"}


def controller(service: IssueWorkflowService) -> SimpleNamespace:
    return SimpleNamespace(
        workflow=FakeWorkflow(service),
        task_id=TASK_ID,
        state={},
    )


def build_goal_loop_release() -> tuple[LaggyMemoryIssueBackend, Callable[[], Any]]:
    backend, service = active_service(WorkflowPhase.IMPLEMENTATION)
    guarded = GuardedTaskController(controller(service))
    return backend, lambda: guarded._release_active_lease(["synthetic checkout blocker"])


def build_pipeline_blocker() -> tuple[LaggyMemoryIssueBackend, Callable[[], Any]]:
    backend, service = active_service(WorkflowPhase.IMPLEMENTATION)
    item = controller(service)
    return backend, lambda: ProductionTaskController.record_pipeline_blocker(
        item,
        summary="Synthetic pipeline blocker.",
        details=("Synthetic blocker detail.",),
    )


def build_delivery_handoff() -> tuple[LaggyMemoryIssueBackend, Callable[[], Any]]:
    backend, service = active_service(WorkflowPhase.DELIVERY_EVIDENCE)
    return backend, lambda: request_delivery_review(service)


def build_delivery_approval() -> tuple[LaggyMemoryIssueBackend, Callable[[], Any]]:
    backend, service = active_service(WorkflowPhase.DELIVERY_EVIDENCE)
    request_delivery_review(service)
    return backend, lambda: apply_delivery_approval(service)


def build_pending_check_release() -> tuple[LaggyMemoryIssueBackend, Callable[[], Any]]:
    backend, service = active_service(WorkflowPhase.MERGE_CLOSEOUT)
    return backend, lambda: DownstreamIssueCoordinator(service).release_for_pending_checks(
        task_id=TASK_ID,
        pull_request_url="https://example.invalid/pull/104",
        head_commit=EVIDENCE_HEAD,
        reason="Synthetic checks are pending.",
        now="2026-08-31T10:07:00Z",
    )


def build_completion() -> tuple[LaggyMemoryIssueBackend, Callable[[], Any]]:
    backend, service = active_service(WorkflowPhase.MERGE_CLOSEOUT)
    return backend, lambda: DownstreamIssueCoordinator(service).complete(
        task_id=TASK_ID,
        pull_request_url="https://example.invalid/pull/104",
        pull_request_number=104,
        merged_commit=EVIDENCE_HEAD,
        conformant_record_id="synthetic-conformance-record",
        now="2026-08-31T10:08:00Z",
    )


def build_evidence_head_release() -> tuple[LaggyMemoryIssueBackend, Callable[[], Any]]:
    backend, service = active_service(WorkflowPhase.MERGE_CLOSEOUT)
    return backend, lambda: ResumableDownstreamIssueCoordinator(
        service
    ).release_for_pending_checks(
        task_id=TASK_ID,
        pull_request_url="https://example.invalid/pull/104",
        head_commit=EVIDENCE_HEAD,
        reason="Synthetic checks are pending.",
        now="2026-08-31T10:09:00Z",
    )


def build_resilience_release() -> tuple[LaggyMemoryIssueBackend, Callable[[], Any]]:
    backend, service = active_service(WorkflowPhase.IMPLEMENTATION)
    item = controller(service)
    return backend, lambda: release_resilience_lease(
        item,
        reason="synthetic_deterministic_failure",
        details={"action": "synthetic_action", "error": "synthetic failure"},
    )


def build_mainline_blocker() -> tuple[LaggyMemoryIssueBackend, Callable[[], Any]]:
    backend, service = active_service(WorkflowPhase.DELIVERY_EVIDENCE)
    item = controller(service)
    return backend, lambda: _block_current_lease(
        item,
        reason="synthetic mainline blocker",
        details={"main_head": SOURCE_HEAD},
    )


def build_automation_only_advance() -> tuple[
    LaggyMemoryIssueBackend, Callable[[], Any]
]:
    backend, service = active_service(WorkflowPhase.DELIVERY_EVIDENCE)
    item = controller(service)
    receipt = {
        "prior_task_head": HUMAN_HEAD,
        "main_head": SOURCE_HEAD,
        "integrated_commit": INTEGRATED_HEAD,
        "receipt_sha256": "d" * 64,
        "human_tested_commit": HUMAN_HEAD,
    }
    return backend, lambda: _advance_automation_only_issue(item, receipt)


CASES = (
    ("goal-loop active lease release", build_goal_loop_release),
    ("production pipeline blocker", build_pipeline_blocker),
    ("delivery-review handoff", build_delivery_handoff),
    ("delivery-review approval", build_delivery_approval),
    ("pending-check lease release", build_pending_check_release),
    ("completion", build_completion),
    ("resumable evidence-head release", build_evidence_head_release),
    ("deterministic-failure lease release", build_resilience_release),
    ("mainline integration blocker", build_mainline_blocker),
    ("automation-only integration release", build_automation_only_advance),
)


def test_all_direct_transitions_retry_only_reads() -> None:
    with immediate_verification_reads():
        for name, build in CASES:
            backend, action = build()
            comments_before = backend.add_comment_calls
            updates_before = backend.update_issue_calls
            backend.stale_reads_per_update = 2
            action()
            require(
                backend.add_comment_calls == comments_before + 1,
                f"{name} replayed or omitted its one event comment",
            )
            require(
                backend.update_issue_calls == updates_before + 1,
                f"{name} replayed or omitted its one Issue update",
            )


def test_all_direct_transitions_exhaust_without_replaying_mutations() -> None:
    with immediate_verification_reads():
        for name, build in CASES:
            backend, action = build()
            comments_before = backend.add_comment_calls
            updates_before = backend.update_issue_calls
            backend.stale_reads_per_update = 100
            try:
                action()
            except IssueWorkflowStoreError as exc:
                require(
                    "bounded read attempt(s)" in str(exc),
                    f"{name} failed for an unexpected reason: {exc}",
                )
            else:
                raise AssertionError(f"{name} accepted exhausted stale reads")
            require(
                backend.add_comment_calls == comments_before + 1,
                f"{name} replayed its event comment after exhausted reads",
            )
            require(
                backend.update_issue_calls == updates_before + 1,
                f"{name} replayed its Issue update after exhausted reads",
            )


def test_state_label_restoration_retries_only_its_single_update() -> None:
    backend, service = active_service(WorkflowPhase.IMPLEMENTATION)
    snapshot = service.find(TASK_ID)
    assert snapshot is not None and snapshot.state is not None
    comments_before = backend.add_comment_calls
    updates_before = backend.update_issue_calls
    backend.issues[snapshot.issue_number]["labels"].append(
        {"name": STATE_LABELS[WorkflowState.AGENT_READY.value]}
    )
    backend.stale_reads_per_update = 2
    backend.update_issue(
        snapshot.issue_number,
        labels=labels_for_state(snapshot.state.state, snapshot.labels),
    )
    with immediate_verification_reads():
        service.verify_post_mutation_state(
            TASK_ID,
            snapshot.state,
            transition_name="state-label restoration",
        )
    require(
        backend.add_comment_calls == comments_before,
        "state-label verification added an event comment",
    )
    require(
        backend.update_issue_calls == updates_before + 1,
        "state-label verification replayed its one Issue update",
    )

    exhausted_backend, exhausted_service = active_service(WorkflowPhase.IMPLEMENTATION)
    exhausted_snapshot = exhausted_service.find(TASK_ID)
    assert exhausted_snapshot is not None and exhausted_snapshot.state is not None
    exhausted_comments = exhausted_backend.add_comment_calls
    exhausted_updates = exhausted_backend.update_issue_calls
    exhausted_backend.issues[exhausted_snapshot.issue_number]["labels"].append(
        {"name": STATE_LABELS[WorkflowState.AGENT_READY.value]}
    )
    exhausted_backend.stale_reads_per_update = 100
    exhausted_backend.update_issue(
        exhausted_snapshot.issue_number,
        labels=labels_for_state(
            exhausted_snapshot.state.state,
            exhausted_snapshot.labels,
        ),
    )
    with immediate_verification_reads():
        try:
            exhausted_service.verify_post_mutation_state(
                TASK_ID,
                exhausted_snapshot.state,
                transition_name="state-label restoration",
            )
        except IssueWorkflowStoreError:
            pass
        else:
            raise AssertionError("state-label restoration accepted exhausted stale reads")
    require(
        exhausted_backend.add_comment_calls == exhausted_comments,
        "exhausted state-label verification added an event comment",
    )
    require(
        exhausted_backend.update_issue_calls == exhausted_updates + 1,
        "exhausted state-label verification replayed its Issue update",
    )


def test_claim_handoff_exact_authority_reread_is_bounded_and_read_only() -> None:
    backend, service = active_service(WorkflowPhase.IMPLEMENTATION)
    snapshot = service.find(TASK_ID)
    assert snapshot is not None and snapshot.state is not None
    result = {"workflow_state": snapshot.state.to_dict()}
    comments_before = backend.add_comment_calls
    updates_before = backend.update_issue_calls
    backend._stale_reads_remaining = 2
    with immediate_verification_reads():
        failures = _exact_authority_failures(
            issue_workflow=service,
            task_id=TASK_ID,
            result=result,
        )
    require(not failures, f"claim authority reread did not tolerate stale reads: {failures}")
    require(
        backend.add_comment_calls == comments_before
        and backend.update_issue_calls == updates_before,
        "claim authority reread performed a durable mutation",
    )

    backend._stale_reads_remaining = 100
    with immediate_verification_reads():
        failures = _exact_authority_failures(
            issue_workflow=service,
            task_id=TASK_ID,
            result=result,
        )
    require(failures, "claim authority reread accepted exhausted stale reads")
    require(
        backend.add_comment_calls == comments_before
        and backend.update_issue_calls == updates_before,
        "exhausted claim authority reread performed a durable mutation",
    )


def main() -> int:
    tests = (
        test_all_direct_transitions_retry_only_reads,
        test_all_direct_transitions_exhaust_without_replaying_mutations,
        test_state_label_restoration_retries_only_its_single_update,
        test_claim_handoff_exact_authority_reread_is_bounded_and_read_only,
    )
    for test_case in tests:
        test_case()
        print(f"PASS {test_case.__name__}")
    print(
        "TaskReviewAgent repo-wide post-mutation verification tests: "
        f"PASS ({len(tests)} tests, {len(CASES)} direct transition paths)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
