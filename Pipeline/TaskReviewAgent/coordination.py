"""Read-only GitHub Issue coordination for the explicit TaskReviewAgent task."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Protocol, Sequence

from .contracts import TaskReviewContractError, validate_task_id


REPOSITORY = "cathode26/NoSafeCircle"
CLAIM_MARKER = "<!-- no-safe-circle-task-review-claim -->"
_TASK_MARKER_TEMPLATE = "<!-- no-safe-circle-task: {task_id} -->"
_WORKER_RE = re.compile(r"^\s*-\s*\*\*Worker:\*\*\s*`([^`]+)`\s*$", re.MULTILINE)


class CoordinationError(TaskReviewContractError):
    """Raised when GitHub coordination facts cannot be read safely."""


class CoordinationObserver(Protocol):
    def observe(
        self,
        *,
        task: dict[str, Any],
        source_head: str,
        checkout_path: str,
        branch: str,
    ) -> dict[str, Any]: ...


class StaticCoordinationObserver:
    """Deterministic injected coordination state used by checkout tests."""

    def __init__(self, *, worker_id: str, status: str = "claimed_by_worker") -> None:
        self.worker_id = worker_id
        self.status = status

    def observe(
        self,
        *,
        task: dict[str, Any],
        source_head: str,
        checkout_path: str,
        branch: str,
    ) -> dict[str, Any]:
        _ = (task, source_head, checkout_path, branch)
        return {
            "status": self.status,
            "worker_id": self.worker_id,
            "claim_worker_id": self.worker_id if self.status == "claimed_by_worker" else None,
            "issue_number": 777 if self.status != "available_missing" else None,
            "issue_url": "https://github.com/cathode26/NoSafeCircle/issues/777",
            "assignees": ["cathode26"] if self.status == "claimed_by_worker" else [],
            "reasons": [],
            "authority": "injected_test_coordination",
        }


def _decode(data: bytes, *, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CoordinationError(f"{label} was not valid UTF-8") from exc


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout_seconds: float = 120.0,
) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["GH_PAGER"] = "cat"
    environment["NO_COLOR"] = "1"
    try:
        result = subprocess.run(
            tuple(args),
            cwd=str(cwd),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CoordinationError(
            f"GitHub coordination command could not run: {' '.join(args)}"
        ) from exc
    if check and result.returncode != 0:
        stdout = _decode(result.stdout or b"", label="gh stdout").strip()
        stderr = _decode(result.stderr or b"", label="gh stderr").strip()
        detail = "\n".join(item for item in (stdout, stderr) if item)
        raise CoordinationError(
            f"GitHub coordination command failed ({result.returncode}): {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def _worker_from_comments(comments: Any) -> str | None:
    if not isinstance(comments, list):
        return None
    worker: str | None = None
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        body = comment.get("body")
        if type(body) is not str or CLAIM_MARKER not in body:
            continue
        match = _WORKER_RE.search(body)
        if match:
            worker = match.group(1).strip()
    return worker


class GhCoordinationObserver:
    """Observe the repository's assignment/claim convention without mutating GitHub."""

    def __init__(
        self,
        *,
        source_root: Path | str,
        task_id: str,
        worker_id: str,
        repository: str = REPOSITORY,
    ) -> None:
        self.source_root = Path(source_root).resolve()
        self.task_id = validate_task_id(task_id)
        self.worker_id = str(worker_id).strip()
        self.repository = repository
        if not self.worker_id:
            raise CoordinationError("worker_id must be non-empty")

    def _unavailable(self, reason: str) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "worker_id": self.worker_id,
            "claim_worker_id": None,
            "issue_number": None,
            "issue_url": None,
            "assignees": [],
            "reasons": [reason],
            "authority": "real_github_read_only",
        }

    def observe(
        self,
        *,
        task: dict[str, Any],
        source_head: str,
        checkout_path: str,
        branch: str,
    ) -> dict[str, Any]:
        _ = (task, source_head, checkout_path, branch)
        if shutil.which("gh") is None:
            return self._unavailable("GitHub CLI 'gh' is not installed")
        auth = _run(
            ("gh", "auth", "status", "--hostname", "github.com"),
            cwd=self.source_root,
            check=False,
        )
        if auth.returncode != 0:
            return self._unavailable("GitHub CLI is not authenticated for github.com")

        listed = _run(
            (
                "gh",
                "issue",
                "list",
                "--repo",
                self.repository,
                "--state",
                "all",
                "--limit",
                "1000",
                "--json",
                "number,title,state,assignees,url,body",
            ),
            cwd=self.source_root,
        )
        try:
            issues = json.loads(_decode(listed.stdout, label="gh issue list"))
        except json.JSONDecodeError as exc:
            raise CoordinationError("gh issue list did not return valid JSON") from exc
        if not isinstance(issues, list):
            raise CoordinationError("gh issue list must return a JSON array")

        marker = _TASK_MARKER_TEMPLATE.format(task_id=self.task_id)
        candidates = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            title = issue.get("title")
            body = issue.get("body")
            title_match = type(title) is str and (
                title == self.task_id or title.startswith(f"{self.task_id} —")
            )
            marker_match = type(body) is str and marker in body
            if title_match or marker_match:
                candidates.append(issue)

        if not candidates:
            return {
                "status": "available_missing",
                "worker_id": self.worker_id,
                "claim_worker_id": None,
                "issue_number": None,
                "issue_url": None,
                "assignees": [],
                "reasons": ["no GitHub Issue exists for the exact task ID"],
                "authority": "real_github_read_only",
            }
        if len(candidates) != 1:
            return {
                "status": "conflict",
                "worker_id": self.worker_id,
                "claim_worker_id": None,
                "issue_number": None,
                "issue_url": None,
                "assignees": [],
                "reasons": [
                    f"multiple GitHub Issues match {self.task_id}: "
                    + ", ".join(str(item.get("number")) for item in candidates)
                ],
                "authority": "real_github_read_only",
            }

        issue = candidates[0]
        number = issue.get("number")
        url = issue.get("url")
        state = str(issue.get("state") or "").upper()
        assignee_values = issue.get("assignees")
        assignees = sorted(
            {
                str(item.get("login"))
                for item in assignee_values
                if isinstance(item, dict) and item.get("login")
            }
        ) if isinstance(assignee_values, list) else []

        if state == "CLOSED":
            return {
                "status": "closed",
                "worker_id": self.worker_id,
                "claim_worker_id": None,
                "issue_number": number,
                "issue_url": url,
                "assignees": assignees,
                "reasons": ["the task's GitHub Issue is closed"],
                "authority": "real_github_read_only",
            }
        if not assignees:
            return {
                "status": "available_unassigned",
                "worker_id": self.worker_id,
                "claim_worker_id": None,
                "issue_number": number,
                "issue_url": url,
                "assignees": [],
                "reasons": ["the task's GitHub Issue is open and unassigned"],
                "authority": "real_github_read_only",
            }

        viewed = _run(
            (
                "gh",
                "issue",
                "view",
                str(number),
                "--repo",
                self.repository,
                "--json",
                "comments",
            ),
            cwd=self.source_root,
        )
        try:
            details = json.loads(_decode(viewed.stdout, label="gh issue view"))
        except json.JSONDecodeError as exc:
            raise CoordinationError("gh issue view did not return valid JSON") from exc
        claim_worker = _worker_from_comments(
            details.get("comments") if isinstance(details, dict) else None
        )
        if claim_worker == self.worker_id and "cathode26" in assignees:
            status = "claimed_by_worker"
            reasons: list[str] = []
        else:
            status = "claimed_by_other"
            reasons = [
                (
                    "task is assigned and latest TaskReviewAgent claim belongs to "
                    f"{claim_worker!r}"
                )
                if claim_worker
                else "task is assigned without a matching TaskReviewAgent worker claim"
            ]
        return {
            "status": status,
            "worker_id": self.worker_id,
            "claim_worker_id": claim_worker,
            "issue_number": number,
            "issue_url": url,
            "assignees": assignees,
            "reasons": reasons,
            "authority": "real_github_read_only",
        }
