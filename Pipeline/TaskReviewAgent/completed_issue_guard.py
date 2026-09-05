"""Prevent a completed task from being reinitialized as a duplicate GitHub Issue.

The workflow closes its managed Issue only after post-merge verification succeeds.
Historically, ``GhIssueBackend.list_issues`` returned open Issues only and
``_find_candidates`` discarded every closed Issue. The next observation in the
same supervisor run therefore saw no durable workflow for the just-completed task
and could create a new ``agent_ready / implementation`` Issue for it.

This layer makes closed, hash-valid ``complete`` Issues discoverable while keeping
closed incomplete/duplicate Issues out of the active queue. It does not reopen or
mutate completed workflows.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from . import issue_workflow_store as store
from .decomposition_undo_retirement import (
    PublishedUndoRetirementError,
    classify_retired_decomposition_completion,
)
from .issue_workflow import (
    WorkflowContractError,
    WorkflowState,
    parse_state,
)


_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}


def _issue_closed(issue: Mapping[str, Any]) -> bool:
    return str(issue.get("state") or "").upper() == "CLOSED"


def _matches_task(issue: Mapping[str, Any], task_id: str) -> bool:
    marker = store._task_marker(task_id)
    title = issue.get("title")
    body = issue.get("body")
    return (
        isinstance(title, str)
        and (title == task_id or title.startswith(f"{task_id} —"))
    ) or (isinstance(body, str) and marker in body)


def _closed_complete(issue: Mapping[str, Any]) -> bool:
    if not _issue_closed(issue):
        return False
    body = issue.get("body")
    if not isinstance(body, str):
        return False
    try:
        state = parse_state(body)
    except WorkflowContractError:
        return False
    return state is not None and state.state is WorkflowState.COMPLETE


def _completed_aware_candidates(
    issues: Iterable[dict[str, Any]],
    task_id: str,
) -> list[dict[str, Any]]:
    """Return active matches plus the canonical closed COMPLETE workflow.

    Closed non-complete Issues are ignored. They may be manually closed drafts,
    abandoned duplicates, or historical operator mistakes; none can authorize a
    new run. A closed COMPLETE Issue remains the durable terminal authority.
    """

    task_id = store.validate_task_id(task_id)
    candidates: list[dict[str, Any]] = []
    for issue in issues:
        if not _matches_task(issue, task_id):
            continue
        if not store.issue_author_authorized(issue):
            # Public-repository Issues from unauthorized logins never become
            # managed workflow authority, open or closed.
            continue
        if _issue_closed(issue) and not _closed_complete(issue):
            continue
        candidates.append(issue)
    return candidates


def _completed_aware_find(
    self: store.IssueWorkflowService,
    task_id: str,
) -> store.IssueWorkflowSnapshot | None:
    """Find current authority while honoring a verified decomposition retirement.

    A normal closed COMPLETE Issue remains terminal forever.  The sole
    exception is a valid closed ``decomposition_apply`` workflow carrying the
    exact authorized marker written by ``reset_task.py`` after it independently
    proved an already-published additive undo.  That Issue remains immutable
    audit history but no longer owns the replacement run.
    """

    task_id = store.validate_task_id(task_id)
    candidates = _completed_aware_candidates(self.backend.list_issues(), task_id)
    active: list[dict[str, Any]] = []
    deadline = (
        self.consistency_retry_budget.deadline()
        if self.consistency_retry_budget is not None
        else None
    )
    for issue in candidates:
        if not (_issue_closed(issue) and _closed_complete(issue)):
            active.append(issue)
            continue
        number = issue.get("number")
        if type(number) is not int or number < 1:
            raise store.IssueWorkflowStoreError(
                "closed completed Issue is missing a positive integer number"
            )
        try:
            retired = classify_retired_decomposition_completion(
                issue,
                self.backend.get_comments(number),
            )
        except PublishedUndoRetirementError as exc:
            raise store.IssueWorkflowStoreError(
                f"closed completed Issue #{number} has invalid published-undo "
                f"retirement evidence: {exc}"
            ) from exc
        if retired is not None:
            continue
        active.append(issue)

    if len(active) > 1:
        raise store.IssueWorkflowStoreError(
            f"multiple open GitHub Issues match {task_id}: "
            + ", ".join(str(item.get("number")) for item in active)
        )
    if not active:
        return None
    return store._consistent_snapshot(self.backend, active[0], deadline=deadline)


def _gh_list_all_issues(self: Any) -> list[dict[str, Any]]:
    # Complete pagination: `gh api --paginate` follows Link headers until the
    # listing is exhausted, so an old completed Issue past any fixed result
    # limit still remains discoverable terminal authority.
    return self._list_issues_via_api("all")


def _open_agent_ready_only(self: Any) -> list[dict[str, Any]]:
    # The base implementation owns coherence retries and fail-closed invalid
    # state handling. It also ignores closed Issues; this wrapper remains only
    # as the composition seam paired with completed-aware Issue discovery.
    return _ORIGINALS["list_agent_ready"](self)


def install_completed_issue_guard() -> None:
    """Install completed-Issue discovery exactly once."""

    global _INSTALLED
    if _INSTALLED:
        return
    _ORIGINALS.update(
        {
            "find_candidates": store._find_candidates,
            "find": store.IssueWorkflowService.find,
            "gh_list_issues": store.GhIssueBackend.list_issues,
            "list_agent_ready": store.IssueWorkflowService.list_agent_ready,
        }
    )
    store._find_candidates = _completed_aware_candidates
    store.IssueWorkflowService.find = _completed_aware_find
    store.GhIssueBackend.list_issues = _gh_list_all_issues
    store.IssueWorkflowService.list_agent_ready = _open_agent_ready_only
    _INSTALLED = True


__all__ = [
    "install_completed_issue_guard",
]
