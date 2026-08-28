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

from Pipeline.TaskReviewAgent.downstream_issue import (  # noqa: E402
    DownstreamIssueCoordinator,
    parse_human_delivery_review,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    STATE_LABELS,
    WorkflowActor,
    WorkflowPhase,
    WorkflowState,
    parse_human_validation_result,
    parse_state,
)
from Pipeline.TaskReviewAgent.issue_workflow_action import (  # noqa: E402
    GitHubRestBackend,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    IssueWorkflowStoreError,
)


def _latest_matching_comment(
    comments: list[dict[str, Any]],
    parser,
) -> str | None:
    for comment in reversed(comments):
        body = comment.get("body")
        if type(body) is str and parser(body) is not None:
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
    actor_id = ((event.get("sender") or {}).get("login")) or "human"
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
    try:
        state = parse_state(str(issue.get("body") or ""))
        if state is None:
            return 0
        # Managed actions can themselves add the agent-ready label. That event is
        # already represented by the hidden state/event chain and is a no-op here.
        if state.state is WorkflowState.AGENT_READY:
            return 0

        # The human has temporarily added agent-ready beside the authoritative state
        # label. Restore the current state label before parsing/verifying the journal.
        backend.restore_state_label(state.state)
        comments = backend.get_comments(issue_number)
        service = IssueWorkflowService(
            backend=backend,
            task_loader=lambda task_id: {
                "id": task_id,
                "exclusive_resources": [],
            },
            worker_id="github-issue-workflow-action",
        )

        if state.state is WorkflowState.HUMAN_ACTION_REQUIRED:
            result_body = _latest_matching_comment(
                comments,
                parse_human_validation_result,
            )
            if result_body is None:
                raise IssueWorkflowStoreError(
                    "No Human validation result comment was found. Post Result: "
                    "PASS|FAIL with the exact Tested commit before changing state."
                )
            result = service.apply_human_result(
                task_id=state.task_id,
                result_body=result_body,
                actor_id=actor_id,
            )
        elif (
            state.state is WorkflowState.BLOCKED
            and state.phase is WorkflowPhase.DELIVERY_EVIDENCE
            and state.current_actor is WorkflowActor.HUMAN
        ):
            result_body = _latest_matching_comment(
                comments,
                parse_human_delivery_review,
            )
            if result_body is None:
                raise IssueWorkflowStoreError(
                    "No Human delivery evidence review was found. Post Decision: "
                    "APPROVE|REQUEST_CHANGES with the exact Proposal SHA256 before "
                    "changing state."
                )
            result = DownstreamIssueCoordinator(service).apply_delivery_review(
                task_id=state.task_id,
                result_body=result_body,
                actor_id=actor_id,
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
