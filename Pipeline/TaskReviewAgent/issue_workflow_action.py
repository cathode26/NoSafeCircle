#!/usr/bin/env python3
"""Advance a human-owned Issue back to agent-ready after its label transition."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    STATE_LABELS,
    WorkflowState,
    parse_human_validation_result,
    parse_state,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    IssueWorkflowStoreError,
)


class GitHubRestBackend:
    """Minimal Actions-token backend for one Issue transition."""

    def __init__(self, *, repository: str, issue_number: int, token: str) -> None:
        self.repository = repository
        self.issue_number = issue_number
        self.token = token
        self.base = f"https://api.github.com/repos/{repository}"

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "NoSafeCircle-IssueWorkflow",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise IssueWorkflowStoreError(
                f"GitHub REST {method} {path} failed ({exc.code}): {detail}"
            ) from exc
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IssueWorkflowStoreError("GitHub REST returned invalid JSON") from exc

    def _issue(self) -> dict[str, Any]:
        value = self._request("GET", f"/issues/{self.issue_number}")
        if not isinstance(value, dict):
            raise IssueWorkflowStoreError(
                "GitHub REST issue response was not an object"
            )
        return value

    def list_issues(self) -> list[dict[str, Any]]:
        return [self._issue()]

    def get_comments(self, issue_number: int) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            query = urllib.parse.urlencode({"per_page": 100, "page": page})
            value = self._request(
                "GET",
                f"/issues/{issue_number}/comments?{query}",
            )
            if not isinstance(value, list):
                raise IssueWorkflowStoreError(
                    "GitHub REST issue comments response was not an array"
                )
            comments.extend(item for item in value if isinstance(item, dict))
            if len(value) < 100:
                break
            page += 1
        return comments

    def create_issue(self, **_: Any) -> dict[str, Any]:
        raise IssueWorkflowStoreError(
            "the Issue workflow action cannot create Issues"
        )

    def update_issue(
        self,
        issue_number: int,
        *,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if body is not None:
            payload["body"] = body
        if labels is not None:
            payload["labels"] = labels
        if assignees is not None:
            payload["assignees"] = assignees
        value = self._request("PATCH", f"/issues/{issue_number}", payload)
        if not isinstance(value, dict):
            raise IssueWorkflowStoreError(
                "GitHub REST issue update was not an object"
            )
        return value

    def add_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        value = self._request(
            "POST",
            f"/issues/{issue_number}/comments",
            {"body": body},
        )
        if not isinstance(value, dict):
            raise IssueWorkflowStoreError(
                "GitHub REST comment response was not an object"
            )
        return value

    def ensure_labels(self) -> None:
        return None

    def restore_human_action_label(self) -> None:
        issue = self._issue()
        labels = [
            item.get("name")
            for item in issue.get("labels") or []
            if isinstance(item, dict) and item.get("name")
        ]
        labels = [
            item
            for item in labels
            if item != STATE_LABELS[WorkflowState.AGENT_READY.value]
        ]
        if STATE_LABELS[WorkflowState.HUMAN_ACTION_REQUIRED.value] not in labels:
            labels.append(STATE_LABELS[WorkflowState.HUMAN_ACTION_REQUIRED.value])
        self.update_issue(self.issue_number, labels=sorted(set(labels)))


def _latest_human_result(comments: list[dict[str, Any]]) -> str | None:
    for comment in reversed(comments):
        body = comment.get("body")
        if type(body) is str and parse_human_validation_result(body) is not None:
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
    try:
        state = parse_state(str(issue.get("body") or ""))
        if state is None:
            return 0
        if state.state is not WorkflowState.HUMAN_ACTION_REQUIRED:
            raise IssueWorkflowStoreError(
                "nsc-state:agent-ready may be applied by a human only while the "
                "managed workflow is human_action_required"
            )
        # The human just added agent-ready, so restore the label matching the still-current
        # state before the service verifies and records the transition.
        backend.restore_human_action_label()
        result_body = _latest_human_result(backend.get_comments(issue_number))
        if result_body is None:
            raise IssueWorkflowStoreError(
                "No Human validation result comment was found. Post the handoff template "
                "with Result: PASS|FAIL and the exact Tested commit before changing state."
            )
        service = IssueWorkflowService(
            backend=backend,
            task_loader=lambda task_id: {
                "id": task_id,
                "exclusive_resources": [],
            },
            worker_id="github-issue-workflow-action",
        )
        result = service.apply_human_result(
            task_id=state.task_id,
            result_body=result_body,
            actor_id=actor_id,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        try:
            backend.restore_human_action_label()
            backend.add_comment(
                issue_number,
                "## Workflow state change rejected\n\n"
                "The Issue remains `human_action_required`.\n\n"
                f"Reason: {exc}",
            )
        except Exception:
            pass
        print(f"Issue workflow transition failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
