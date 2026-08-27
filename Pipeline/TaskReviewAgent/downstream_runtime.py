"""Production-safe downstream wrappers for durable resume behavior."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .downstream_issue import DownstreamIssueCoordinator, DownstreamIssueError, _meaningful
from .downstream_pipeline import DownstreamTaskController
from .issue_workflow import (
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    labels_for_state,
    render_event_comment,
    transition,
    update_issue_body,
    utc_now,
)
from .issue_workflow_store import IssueWorkflowStoreError


class ResumableDownstreamIssueCoordinator(DownstreamIssueCoordinator):
    """Release a merge-closeout lease at the exact evidence commit to resume."""

    def release_for_pending_checks(
        self,
        *,
        task_id: str,
        pull_request_url: str,
        head_commit: str,
        reason: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.service.find(task_id)
        if snapshot is None or not snapshot.valid or snapshot.state is None:
            raise DownstreamIssueError("lease release requires a valid Issue")
        state = snapshot.state
        if (
            state.state is not WorkflowState.AGENT_WORKING
            or state.worker_id != self.worker_id
            or state.phase is not WorkflowPhase.MERGE_CLOSEOUT
        ):
            raise DownstreamIssueError(
                "pending-check release requires this worker's merge_closeout lease"
            )
        exact_head = _meaningful(head_commit, "head_commit")
        next_state, event = transition(
            state,
            event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
            actor_type=WorkflowActor.AGENT,
            actor_id=self.worker_id,
            to_state=WorkflowState.AGENT_READY,
            to_phase=WorkflowPhase.MERGE_CLOSEOUT,
            details={
                "reason": _meaningful(reason, "reason"),
                "pull_request_url": _meaningful(
                    pull_request_url, "pull_request_url"
                ),
                "head_commit": exact_head,
            },
            now=now or utc_now(),
        )
        # The implementation handoff commit was the previous durable resume point.
        # Delivery evidence is a later committed state on the same task branch, so a
        # future generic worker must resume the exact evidence commit recorded here.
        next_state = replace(next_state, head_commit=exact_head)
        self.service.backend.add_comment(
            snapshot.issue_number,
            render_event_comment(
                event,
                "The agent released its lease after publishing delivery evidence. "
                f"A later generic agent should resume `{pull_request_url}` at the exact "
                f"evidence commit `{exact_head}`.",
            ),
        )
        self.service.backend.update_issue(
            snapshot.issue_number,
            body=update_issue_body(
                snapshot.body,
                next_state,
                next_action=(
                    "Resume merge closeout at the recorded evidence commit after the "
                    "pull-request checks finish."
                ),
            ),
            labels=labels_for_state(next_state.state, snapshot.labels),
            assignees=[self.service.assignee],
        )
        verified = self.service.find(task_id)
        if verified is None or not verified.valid or verified.state != next_state:
            raise IssueWorkflowStoreError("lease release could not be verified")
        return {"status": "agent_ready", **verified.to_dict()}


class ResumableDownstreamTaskController(DownstreamTaskController):
    """Use durable proposal revision and evidence-commit handoff semantics."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        service = self.workflow.issue_workflow
        self.issue = (
            ResumableDownstreamIssueCoordinator(service)
            if service is not None
            else None
        )

    def _next_action(
        self,
        observation: Mapping[str, Any],
        state: Mapping[str, Any] | None,
    ) -> str:
        base = super()._next_action(observation, state)
        if (
            state is not None
            and state.get("state") == WorkflowState.AGENT_WORKING.value
            and state.get("phase") == WorkflowPhase.DELIVERY_EVIDENCE.value
            and base == "publish_delivery_review"
        ):
            latest = self._latest_delivery_approval()
            if (
                latest is not None
                and latest.get("decision") == "request_changes"
                and latest.get("proposal_sha256") == self.state.get("proposal_sha256")
            ):
                return "create_delivery_review_proposal"
        return base

    def finalize_delivery_evidence_and_open_pr(self) -> dict[str, Any]:
        result = super().finalize_delivery_evidence_and_open_pr()
        if self.issue is None:
            raise DownstreamIssueError("Issue workflow is unavailable")
        evidence_commit = self.state.get("evidence_commit")
        pull_request_url = self.state.get("pull_request_url")
        if not isinstance(evidence_commit, str) or not isinstance(
            pull_request_url, str
        ):
            raise DownstreamIssueError(
                "delivery finalization did not persist PR/evidence identities"
            )
        release = self.issue.release_for_pending_checks(
            task_id=self.task_id,
            pull_request_url=pull_request_url,
            head_commit=evidence_commit,
            reason=(
                "Delivery evidence was committed, TaskGraph derived conformant, and the "
                "pull request was opened. A future generic run should inspect checks and "
                "continue merge closeout."
            ),
        )
        return {**result, "status": "agent_ready", "release": release}
