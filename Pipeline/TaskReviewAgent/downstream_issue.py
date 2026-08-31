"""Durable Issue transitions for delivery review, PR waiting, and closeout."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Iterable

from .actor_policy import default_actor_policy
from .contracts import SHA256_RE, TaskReviewContractError
from .issue_workflow import (
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    labels_for_state,
    render_event_comment,
    strip_fenced_blocks,
    transition,
    update_issue_body,
    utc_now,
)
from .issue_workflow_store import IssueWorkflowService


DELIVERY_REVIEW_RE = re.compile(
    r"(?im)^\s*Decision:\s*(APPROVE|REQUEST_CHANGES)\s*$.*?"
    r"^\s*Proposal SHA256:\s*`?([0-9a-f]{64})`?\s*$",
    re.DOTALL,
)


class DownstreamIssueError(TaskReviewContractError):
    """Raised when a downstream Issue transition cannot be proven safe."""


@dataclass(frozen=True)
class HumanDeliveryReview:
    decision: str
    proposal_sha256: str
    body: str

    def __post_init__(self) -> None:
        if self.decision not in ("approve", "request_changes"):
            raise DownstreamIssueError("delivery review decision is invalid")
        if not SHA256_RE.fullmatch(self.proposal_sha256):
            raise DownstreamIssueError("delivery review proposal SHA-256 is invalid")
        if not isinstance(self.body, str) or not self.body.strip():
            raise DownstreamIssueError("delivery review body must be non-empty")


def parse_human_delivery_review(body: str) -> HumanDeliveryReview | None:
    if not isinstance(body, str):
        return None
    # The agent's review-request comment shows the approval template inside a
    # fenced block; quoted template text must never parse as a human decision.
    match = DELIVERY_REVIEW_RE.search(strip_fenced_blocks(body))
    if match is None:
        return None
    return HumanDeliveryReview(
        decision=match.group(1).casefold(),
        proposal_sha256=match.group(2),
        body=body,
    )


def _meaningful(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DownstreamIssueError(f"{field} must be non-empty")
    return value.strip()


class DownstreamIssueCoordinator:
    """Keep downstream human decisions in the existing hashed Issue journal."""

    def __init__(self, service: IssueWorkflowService) -> None:
        self.service = service
        self.worker_id = service.worker_id

    def request_delivery_review(
        self,
        *,
        task_id: str,
        branch: str,
        head_commit: str,
        checkout_path: str,
        draft_path: str,
        draft_sha256: str,
        proposal_path: str,
        proposal_sha256: str,
        surface_summary: Iterable[str],
        gate_summary: Iterable[str],
        now: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.service.find(task_id)
        if snapshot is None or not snapshot.valid or snapshot.state is None:
            raise DownstreamIssueError("delivery review requires a valid managed Issue")
        state = snapshot.state
        if (
            state.state is not WorkflowState.AGENT_WORKING
            or state.worker_id != self.worker_id
            or state.phase is not WorkflowPhase.DELIVERY_EVIDENCE
        ):
            raise DownstreamIssueError(
                "delivery review requires this worker's delivery_evidence lease"
            )
        branch = _meaningful(branch, "branch")
        head_commit = _meaningful(head_commit, "head_commit")
        checkout_path = _meaningful(checkout_path, "checkout_path")
        draft_path = _meaningful(draft_path, "draft_path")
        proposal_path = _meaningful(proposal_path, "proposal_path")
        if not SHA256_RE.fullmatch(draft_sha256):
            raise DownstreamIssueError("draft_sha256 is invalid")
        if not SHA256_RE.fullmatch(proposal_sha256):
            raise DownstreamIssueError("proposal_sha256 is invalid")
        if state.head_commit != head_commit or state.branch != branch:
            raise DownstreamIssueError(
                "delivery review branch/commit differs from the human-tested state"
            )

        next_state, event = transition(
            state,
            event_type=WorkflowEventType.BLOCKED,
            actor_type=WorkflowActor.AGENT,
            actor_id=self.worker_id,
            to_state=WorkflowState.BLOCKED,
            to_phase=WorkflowPhase.DELIVERY_EVIDENCE,
            details={
                "review_kind": "delivery_spec",
                "branch": branch,
                "head_commit": head_commit,
                "checkout_path": checkout_path,
                "draft_path": draft_path,
                "draft_sha256": draft_sha256,
                "proposal_path": proposal_path,
                "proposal_sha256": proposal_sha256,
            },
            now=now or utc_now(),
        )
        # BLOCKED may be owned by either actor. This blocker is deliberately a
        # human approval boundary, so make that ownership visible in the dashboard.
        next_state = replace(next_state, current_actor=WorkflowActor.HUMAN)
        surfaces = [str(item).strip() for item in surface_summary if str(item).strip()]
        gates = [str(item).strip() for item in gate_summary if str(item).strip()]
        summary = "\n".join(
            (
                "The delivery evidence draft and exact approval proposal are ready for Vincent.",
                "",
                f"- **Branch:** `{branch}`",
                f"- **Validated commit:** `{head_commit}`",
                f"- **Checkout:** `{checkout_path}`",
                f"- **Review draft:** `{draft_path}`",
                f"- **Draft SHA-256:** `{draft_sha256}`",
                f"- **Approval proposal:** `{proposal_path}`",
                f"- **Proposal SHA-256:** `{proposal_sha256}`",
                "",
                "### Proposed conformance surfaces",
                *([f"- {item}" for item in surfaces] or ["- None recorded."]),
                "",
                "### Proposed gate evidence",
                *([f"- {item}" for item in gates] or ["- None recorded."]),
                "",
                "### What Vincent needs to do",
                "1. Review the proposed surfaces, semantic roles, evidence mappings, and gate notes above.",
                "2. Post the exact approval template below, or request changes with concrete notes.",
                "3. Add the `nsc-state:agent-ready` label. The Issue Action will validate this proposal hash.",
                "",
                "```text",
                "## Human delivery evidence review",
                "",
                "Decision: APPROVE",
                f"Proposal SHA256: `{proposal_sha256}`",
                "",
                "Notes:",
                "Approved as proposed.",
                "```",
                "",
                "For changes, use `Decision: REQUEST_CHANGES` with the same proposal SHA-256 and explain the correction.",
            )
        )
        self.service.backend.add_comment(
            snapshot.issue_number,
            render_event_comment(event, summary),
        )
        self.service.backend.update_issue(
            snapshot.issue_number,
            body=update_issue_body(
                snapshot.body,
                next_state,
                next_action=(
                    "Review the exact delivery-evidence proposal, post APPROVE or "
                    "REQUEST_CHANGES with its SHA-256, then apply `nsc-state:agent-ready`."
                ),
            ),
            labels=labels_for_state(next_state.state, snapshot.labels),
            assignees=[self.service.assignee],
        )
        verified = self.service.verify_post_mutation_state(
            task_id,
            next_state,
            transition_name="delivery review handoff",
        )
        return {"status": "human_delivery_review", **verified.to_dict()}

    def apply_delivery_review(
        self,
        *,
        task_id: str,
        result_body: str,
        actor_id: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.service.find(task_id)
        if snapshot is None or not snapshot.valid or snapshot.state is None:
            raise DownstreamIssueError("delivery review result requires a valid Issue")
        state = snapshot.state
        if (
            state.state is not WorkflowState.BLOCKED
            or state.phase is not WorkflowPhase.DELIVERY_EVIDENCE
            or state.current_actor is not WorkflowActor.HUMAN
        ):
            raise DownstreamIssueError(
                "delivery review result requires a human-owned delivery_evidence blocker"
            )
        if not default_actor_policy().is_authorized_human(actor_id):
            raise DownstreamIssueError(
                f"delivery review authority requires the authorized human operator "
                f"login; {actor_id!r} is not authorized"
            )
        result = parse_human_delivery_review(result_body)
        if result is None:
            raise DownstreamIssueError(
                "delivery review comment must contain Decision: APPROVE|REQUEST_CHANGES "
                "and Proposal SHA256: <64-hex>"
            )
        if not snapshot.events:
            raise DownstreamIssueError("delivery review has no blocking workflow event")
        request_event = snapshot.events[-1]
        expected_sha = request_event.details.get("proposal_sha256")
        if (
            request_event.event_type is not WorkflowEventType.BLOCKED
            or request_event.details.get("review_kind") != "delivery_spec"
            or expected_sha != result.proposal_sha256
        ):
            raise DownstreamIssueError(
                "delivery review does not match the current proposal identity"
            )
        next_phase = (
            WorkflowPhase.MERGE_CLOSEOUT
            if result.decision == "approve"
            else WorkflowPhase.DELIVERY_EVIDENCE
        )
        next_state, event = transition(
            state,
            event_type=WorkflowEventType.UNBLOCKED,
            actor_type=WorkflowActor.HUMAN,
            actor_id=_meaningful(actor_id, "actor_id"),
            to_state=WorkflowState.AGENT_READY,
            to_phase=next_phase,
            details={
                "review_kind": "delivery_spec",
                "decision": result.decision,
                "proposal_sha256": result.proposal_sha256,
                "human_comment_body": result.body,
            },
            now=now or utc_now(),
        )
        decision_text = (
            "approved; the next agent may finalize evidence and continue closeout"
            if result.decision == "approve"
            else "changes requested; the next agent must revise the delivery proposal"
        )
        self.service.backend.add_comment(
            snapshot.issue_number,
            render_event_comment(
                event,
                f"Human delivery evidence review was **{decision_text}** for proposal `{result.proposal_sha256}`.",
            ),
        )
        self.service.backend.update_issue(
            snapshot.issue_number,
            body=update_issue_body(
                snapshot.body,
                next_state,
                next_action=(
                    "A generic agent should resume this Issue and use the exact delivery "
                    f"review decision: {result.decision}."
                ),
            ),
            labels=labels_for_state(next_state.state, snapshot.labels),
            assignees=[self.service.assignee],
        )
        verified = self.service.verify_post_mutation_state(
            task_id,
            next_state,
            transition_name="delivery review result",
        )
        return {"status": "agent_ready", **verified.to_dict()}

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
        next_state, event = transition(
            state,
            event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
            actor_type=WorkflowActor.AGENT,
            actor_id=self.worker_id,
            to_state=WorkflowState.AGENT_READY,
            to_phase=WorkflowPhase.MERGE_CLOSEOUT,
            details={
                "reason": _meaningful(reason, "reason"),
                "pull_request_url": _meaningful(pull_request_url, "pull_request_url"),
                "head_commit": _meaningful(head_commit, "head_commit"),
            },
            now=now or utc_now(),
        )
        self.service.backend.add_comment(
            snapshot.issue_number,
            render_event_comment(
                event,
                "The agent released its lease while pull-request checks are pending. "
                f"A later generic agent should resume `{pull_request_url}` at `{head_commit}`.",
            ),
        )
        self.service.backend.update_issue(
            snapshot.issue_number,
            body=update_issue_body(
                snapshot.body,
                next_state,
                next_action=(
                    "Resume merge closeout after the recorded pull-request checks finish."
                ),
            ),
            labels=labels_for_state(next_state.state, snapshot.labels),
            assignees=[self.service.assignee],
        )
        verified = self.service.verify_post_mutation_state(
            task_id,
            next_state,
            transition_name="pending-check lease release",
        )
        return {"status": "agent_ready", **verified.to_dict()}

    def complete(
        self,
        *,
        task_id: str,
        pull_request_url: str,
        pull_request_number: int,
        merged_commit: str,
        conformant_record_id: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.service.find(task_id)
        if snapshot is None or not snapshot.valid or snapshot.state is None:
            raise DownstreamIssueError("completion requires a valid Issue")
        state = snapshot.state
        if (
            state.state is not WorkflowState.AGENT_WORKING
            or state.worker_id != self.worker_id
            or state.phase is not WorkflowPhase.MERGE_CLOSEOUT
        ):
            raise DownstreamIssueError(
                "completion requires this worker's merge_closeout lease"
            )
        if not isinstance(pull_request_number, int) or pull_request_number <= 0:
            raise DownstreamIssueError("pull_request_number must be positive")
        next_state, event = transition(
            state,
            event_type=WorkflowEventType.COMPLETED,
            actor_type=WorkflowActor.AGENT,
            actor_id=self.worker_id,
            to_state=WorkflowState.COMPLETE,
            to_phase=WorkflowPhase.MERGE_CLOSEOUT,
            details={
                "pull_request_url": _meaningful(pull_request_url, "pull_request_url"),
                "pull_request_number": pull_request_number,
                "merged_commit": _meaningful(merged_commit, "merged_commit"),
                "conformant_record_id": _meaningful(
                    conformant_record_id, "conformant_record_id"
                ),
            },
            now=now or utc_now(),
        )
        self.service.backend.add_comment(
            snapshot.issue_number,
            render_event_comment(
                event,
                "Task closeout completed.\n\n"
                f"- **Pull request:** {pull_request_url}\n"
                f"- **Merged commit:** `{merged_commit}`\n"
                f"- **Conformance record:** `{conformant_record_id}`\n"
                "- **Post-merge TaskGraph state:** `conformant`",
            ),
        )
        self.service.backend.update_issue(
            snapshot.issue_number,
            body=update_issue_body(
                snapshot.body,
                next_state,
                next_action="No further workflow action is required.",
            ),
            labels=labels_for_state(next_state.state, snapshot.labels),
            assignees=[self.service.assignee],
        )
        verified = self.service.verify_post_mutation_state(
            task_id,
            next_state,
            transition_name="completion",
        )
        return {"status": "complete", **verified.to_dict()}
