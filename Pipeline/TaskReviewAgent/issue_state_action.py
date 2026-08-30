#!/usr/bin/env python3
"""Validate human Issue-label transitions for Unity results and delivery review."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.actor_policy import (  # noqa: E402
    actor_login,
    default_actor_policy,
)
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_issue import (  # noqa: E402
    DownstreamIssueCoordinator,
    parse_human_delivery_review,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    STATE_LABELS,
    WorkflowActor,
    WorkflowPhase,
    WorkflowState,
    find_human_validation_result,
    human_comments_after_event,
    parse_state,
)
from Pipeline.TaskReviewAgent.issue_workflow_action import (  # noqa: E402
    GitHubRestBackend,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    IssueWorkflowStoreError,
)


def _latest_delivery_review_body(comments: list[dict[str, Any]]) -> str | None:
    for comment in reversed(comments):
        body = comment.get("body")
        if type(body) is str and parse_human_delivery_review(body) is not None:
            return body
    return None


def main() -> int:
    event_path = os.getenv("GITHUB_EVENT_PATH")
    token = os.getenv("GITHUB_TOKEN")
    if not event_path or not token:
        print(
            "Issue workflow action requires GITHUB_EVENT_PATH and GITHUB_TOKEN",
            file=sys.stderr,
        )
        return 2

    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    if event.get("action") != "labeled":
        return 0
    label_name = ((event.get("label") or {}).get("name"))
    if label_name != STATE_LABELS[WorkflowState.AGENT_READY.value]:
        return 0

    issue = event.get("issue") or {}
    repository = ((event.get("repository") or {}).get("full_name"))
    issue_number = issue.get("number")
    sender_login = ((event.get("sender") or {}).get("login"))
    if type(repository) is not str or type(issue_number) is not int:
        print(
            "Issue workflow event is missing repository/issue identity",
            file=sys.stderr,
        )
        return 2

    backend = GitHubRestBackend(
        repository=repository,
        issue_number=issue_number,
        token=token,
    )
    state = None
    policy = default_actor_policy()
    try:
        state = parse_state(str(issue.get("body") or ""))
        if state is None:
            return 0
        # Managed actions can themselves add the agent-ready label. That event is
        # already represented by the hidden state/event chain and is a no-op here.
        if state.state is WorkflowState.AGENT_READY:
            return 0

        issue_author = actor_login(issue)
        if issue_author is None or not policy.is_authorized_actor(issue_author):
            raise IssueWorkflowStoreError(
                f"Issue #{issue_number} claims managed workflow state but its author "
                f"{issue_author!r} is not an authorized workflow actor"
            )
        if not policy.is_authorized_human(sender_login):
            raise IssueWorkflowStoreError(
                f"the nsc-state:agent-ready label was applied by {sender_login!r}, "
                "who is not the authorized human operator; only the authorized "
                "human login may hand a task back to agent work"
            )

        # The human has temporarily added agent-ready beside the authoritative state
        # label. Restore the current state label before parsing/verifying the journal.
        backend.restore_state_label(state.state)
        comments = backend.get_comments(issue_number)
        service = IssueWorkflowService(
            backend=backend,
            task_loader=lambda task_id: load_committed_task(ROOT, task_id),
            worker_id="github-issue-workflow-action",
        )

        if state.state is WorkflowState.HUMAN_ACTION_REQUIRED:
            if state.last_event_id is None or state.human_handoff_commit is None:
                raise IssueWorkflowStoreError(
                    "human_action_required state has no recorded handoff event/commit"
                )
            human_result, rejections = find_human_validation_result(
                comments,
                after_event_id=state.last_event_id,
                expected_commit=state.human_handoff_commit,
            )
            if human_result is None:
                raise IssueWorkflowStoreError(
                    "No authorized Human validation result was posted after the "
                    "current handoff. Post Result: PASS|FAIL with the exact Tested "
                    "commit before changing state."
                    + ("".join(f" {item}" for item in rejections))
                )
            result = service.apply_human_result(
                task_id=state.task_id,
                result_body=human_result.body,
                actor_id=sender_login,
            )
        elif (
            state.state is WorkflowState.BLOCKED
            and state.phase is WorkflowPhase.DELIVERY_EVIDENCE
            and state.current_actor is WorkflowActor.HUMAN
        ):
            if state.last_event_id is None:
                raise IssueWorkflowStoreError(
                    "blocked delivery review state has no recorded blocking event"
                )
            candidates, anchor_reasons = human_comments_after_event(
                comments,
                after_event_id=state.last_event_id,
            )
            result_body = _latest_delivery_review_body(candidates)
            if result_body is None:
                raise IssueWorkflowStoreError(
                    "No authorized Human delivery evidence review was posted after "
                    "the current review request. Post Decision: APPROVE|"
                    "REQUEST_CHANGES with the exact Proposal SHA256 before changing "
                    "state." + ("".join(f" {item}" for item in anchor_reasons))
                )
            result = DownstreamIssueCoordinator(service).apply_delivery_review(
                task_id=state.task_id,
                result_body=result_body,
                actor_id=sender_login,
            )
        else:
            raise IssueWorkflowStoreError(
                "nsc-state:agent-ready is not a valid human transition from "
                f"{state.state.value}/{state.phase.value}/{state.current_actor.value}"
            )

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        try:
            if state is not None:
                backend.restore_state_label(state.state)
            backend.add_comment(
                issue_number,
                "## Workflow state change rejected\n\n"
                "The managed Issue state did not change.\n\n"
                f"Reason: {exc}",
            )
        except Exception:
            pass
        print(f"Issue workflow transition failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
