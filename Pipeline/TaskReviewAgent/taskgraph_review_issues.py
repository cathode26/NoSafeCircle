"""Materialize evidence-derived TaskGraph review debt as GitHub Issues.

This module is intentionally separate from the managed implementation Issue
state machine. Review-work Issues carry their own exact hidden marker and one
replaceable managed body block; they never carry ``nsc-workflow-state`` or the
normal implementation-task marker.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .committed_tasks import load_committed_task
from .contracts import TASK_ID_RE, TaskReviewContractError, validate_task_id
from .dispatch_plan import (
    TaskcontrolStateObservationError,
    _git_head,
    _taskcontrol_states_snapshot,
    list_committed_task_ids,
)
from .dispatch_policy import load_dispatch_policy
from .issue_queue import repo_root
from .issue_workflow_store import (
    POST_MUTATION_VERIFICATION_DELAYS_SECONDS,
    issue_author_authorized,
)


REVIEW_MARKER_TEMPLATE = "<!-- nsc-taskgraph-review: {task_id} -->"
MANAGED_BLOCK_START = "<!-- NSC_TASKGRAPH_REVIEW:START -->"
MANAGED_BLOCK_END = "<!-- NSC_TASKGRAPH_REVIEW:END -->"

REVIEW_STATES = frozenset(
    {
        "needs_testing",
        "needs_replan",
        "needs_human",
        "invalid_evidence",
        "ambiguous_evidence",
    }
)

_TITLE_PREFIX = {
    "needs_testing": "Revalidation",
    "needs_replan": "Replan",
    "needs_human": "Human Review",
    "invalid_evidence": "Evidence Investigation",
    "ambiguous_evidence": "Evidence Investigation",
}

_STATE_GUIDANCE = {
    "needs_testing": (
        "Previously delivered/evidenced work is no longer proven against current "
        "HEAD because a tracked conformance surface or lineage changed. This is not "
        "fresh implementation.",
        "An agent must prepare/run current-HEAD revalidation, determine required "
        "automated Unity gates and any human runtime/visual checks, and create a "
        "concrete human handoff only if human action is actually required.",
    ),
    "needs_replan": (
        "Prior evidence exists, but the current task contract no longer matches the "
        "evidenced contract revision/hash. This is not fresh implementation and must "
        "not be \"fixed\" by merely rerunning old tests.",
        "An agent must inspect the current task contract versus the selected prior "
        "evidence, determine what requirement/contract changed, and produce the "
        "bounded reconciliation/replanning action. Route Vincent only when a "
        "concrete decision/checklist is ready.",
    ),
    "needs_human": (
        "Current evidence exists but a required human approval/decision is missing.",
        "An agent must inspect the selected evidence and task completion gates, "
        "prepare the exact bounded human decision/checklist, then use the existing "
        "human-handoff/NSC-Vincent mechanism. Do not notify Vincent merely because "
        "the state exists.",
    ),
    "invalid_evidence": (
        "Committed evidence is structurally or semantically invalid.",
        "An agent must investigate the exact evaluator findings and repair/recreate "
        "evidence only through existing immutable evidence rules. Never rewrite "
        "historical evidence in place.",
    ),
    "ambiguous_evidence": (
        "More than one maximal current-valid evidence record prevents unique "
        "conformance.",
        "An agent must investigate the competing committed evidence lineages and "
        "resolve the ambiguity through the existing evidence model; do not choose by "
        "timestamp or Issue prose.",
    ),
}


class TaskGraphReviewIssueError(TaskReviewContractError):
    """Review Issue materialization could not be completed without guessing."""


class ReviewIssueBackend(Protocol):
    """Issue mutation surface needed by review-work materialization."""

    def list_issues(self) -> list[dict[str, Any]]: ...

    def create_issue(
        self,
        *,
        title: str,
        body: str,
        labels: list[str],
        assignees: list[str],
    ) -> dict[str, Any]: ...

    def update_issue(
        self,
        issue_number: int,
        *,
        title: str | None = None,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class TaskGraphReviewSnapshot:
    source_root: Path
    source_commit: str
    states: Mapping[str, Mapping[str, Any]]
    tasks: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class ReviewIssueMaterializationResult:
    source_commit: str
    inspected_task_count: int
    review_task_count: int
    created_task_ids: tuple[str, ...]
    updated_task_ids: tuple[str, ...]
    already_current_task_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_commit": self.source_commit,
            "inspected_task_count": self.inspected_task_count,
            "review_task_count": self.review_task_count,
            "created_task_ids": list(self.created_task_ids),
            "updated_task_ids": list(self.updated_task_ids),
            "already_current_task_ids": list(self.already_current_task_ids),
        }


@dataclass(frozen=True)
class _DesiredReviewIssue:
    task_id: str
    title: str
    body_block: str
    marker: str

    @property
    def new_body(self) -> str:
        return f"{self.marker}\n\n{self.body_block}\n"


def observe_taskgraph_review_snapshot(
    source: Path | str,
) -> TaskGraphReviewSnapshot:
    """Read one complete bulk TaskGraph state view from committed current HEAD.

    Contracts used for the Issue body are loaded before the final HEAD check,
    so a returned snapshot never combines evaluator state and task contracts
    from different commits.
    """

    root = repo_root(Path(source).resolve())
    policy = load_dispatch_policy()
    source_commit = _git_head(root)
    task_ids = list_committed_task_ids(root)
    states = _taskcontrol_states_snapshot(
        root,
        expected_task_ids=task_ids,
        source_commit=source_commit,
        recognized_states=policy.known_dependency_states,
    )
    tasks = {
        task_id: load_committed_task(root, task_id)
        for task_id in task_ids
        if states[task_id]["state"] in REVIEW_STATES
    }
    final_head = _git_head(root)
    if final_head != source_commit:
        raise TaskcontrolStateObservationError(
            f"Git HEAD moved from {source_commit} to {final_head} while review-work "
            "authority was being observed"
        )
    return TaskGraphReviewSnapshot(
        source_root=root,
        source_commit=source_commit,
        states=states,
        tasks=tasks,
    )


def _review_marker(task_id: str) -> str:
    return REVIEW_MARKER_TEMPLATE.format(task_id=validate_task_id(task_id))


def _issue_number(issue: Mapping[str, Any]) -> int:
    number = issue.get("number")
    if type(number) is not int:
        raise TaskGraphReviewIssueError(
            "GitHub review Issue observation is missing an integer number"
        )
    return number


def _is_open(issue: Mapping[str, Any]) -> bool:
    return str(issue.get("state") or "").upper() != "CLOSED"


def _marker_matches(
    issues: list[dict[str, Any]],
    task_id: str,
) -> list[dict[str, Any]]:
    marker = _review_marker(task_id)
    matches: list[dict[str, Any]] = []
    for issue in issues:
        if not _is_open(issue):
            continue
        if not issue_author_authorized(issue):
            continue
        body = issue.get("body")
        if type(body) is not str or marker not in body:
            continue
        if body.count(marker) != 1:
            raise TaskGraphReviewIssueError(
                f"open GitHub Issue #{_issue_number(issue)} contains the exact "
                f"review marker for {task_id} more than once"
            )
        matches.append(issue)
    return matches


def _require_unique_matches(
    issues: list[dict[str, Any]],
    task_ids: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for task_id in task_ids:
        matches = _marker_matches(issues, task_id)
        if len(matches) > 1:
            duplicates.append(
                f"{task_id} -> "
                + ", ".join(f"#{_issue_number(issue)}" for issue in matches)
            )
        elif matches:
            unique[task_id] = matches[0]
    if duplicates:
        raise TaskGraphReviewIssueError(
            "multiple open GitHub Issues carry the same exact TaskGraph review "
            "marker; no review Issue writes were attempted: "
            + "; ".join(duplicates)
        )
    return unique


def _completion_gates(task: Mapping[str, Any], task_id: str) -> tuple[tuple[str, str], ...]:
    raw = task.get("completion_gates")
    if not isinstance(raw, list):
        raise TaskGraphReviewIssueError(
            f"{task_id} completion_gates must be a list in the committed contract"
        )
    gates: list[tuple[str, str]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise TaskGraphReviewIssueError(
                f"{task_id} completion_gates[{index}] must be an object"
            )
        gate_id = item.get("gate_id")
        requirement = item.get("requirement")
        if (
            type(gate_id) is not str
            or not gate_id.strip()
            or type(requirement) is not str
            or not requirement.strip()
        ):
            raise TaskGraphReviewIssueError(
                f"{task_id} completion_gates[{index}] must preserve non-empty "
                "gate_id and requirement strings"
            )
        gates.append((gate_id, requirement))
    if len({gate_id for gate_id, _ in gates}) != len(gates):
        raise TaskGraphReviewIssueError(
            f"{task_id} completion_gates contains duplicate gate IDs"
        )
    return tuple(gates)


def _desired_issue(
    *,
    source_commit: str,
    state_row: Mapping[str, Any],
    task: Mapping[str, Any],
) -> _DesiredReviewIssue:
    task_id = validate_task_id(state_row.get("task_id"))
    if task.get("id") != task_id:
        raise TaskGraphReviewIssueError(
            f"committed task identity mismatch while rendering review work for {task_id}"
        )
    state = state_row.get("state")
    if state not in REVIEW_STATES:
        raise TaskGraphReviewIssueError(
            f"{task_id} has non-review state {state!r} at the review render boundary"
        )
    if state_row.get("head_commit") != source_commit:
        raise TaskGraphReviewIssueError(
            f"{task_id} review state is not bound to evaluated HEAD {source_commit}"
        )
    title = task.get("title")
    revision = task.get("contract_revision")
    if type(title) is not str or not title.strip():
        raise TaskGraphReviewIssueError(
            f"{task_id} committed task title must be a non-empty string"
        )
    if revision is None or isinstance(revision, (dict, list)):
        raise TaskGraphReviewIssueError(
            f"{task_id} committed task contract_revision is missing or malformed"
        )
    selected_record_id = state_row.get("selected_record_id")
    if selected_record_id is not None and (
        type(selected_record_id) is not str or not selected_record_id.strip()
    ):
        raise TaskGraphReviewIssueError(
            f"{task_id} selected evidence record ID is malformed"
        )
    selected_evidence = (
        f"`{selected_record_id}`" if selected_record_id is not None else "(none)"
    )
    gates = _completion_gates(task, task_id)
    meaning, next_action = _STATE_GUIDANCE[state]
    lines = [
        MANAGED_BLOCK_START,
        "## TaskGraph Review Work",
        "",
        f"- **Task ID:** `{task_id}`",
        f"- **Task title:** {title}",
        f"- **Evaluated current HEAD:** `{source_commit}`",
        f"- **Derived review state:** `{state}`",
        f"- **Selected evidence record:** {selected_evidence}",
        f"- **Task contract:** `Tasks/{task_id}.yaml`",
        f"- **Task contract revision:** `{revision}`",
        "",
        "### Current completion gates",
        "",
    ]
    if gates:
        lines.extend(
            f"- **{gate_id}** — {requirement}"
            for gate_id, requirement in gates
        )
    else:
        lines.append("- (none)")
    lines.extend(
        (
            "",
            "### Meaning",
            "",
            meaning,
            "",
            "### Next action",
            "",
            next_action,
            "",
            "This Issue is operational work only. TaskGraph and committed evidence "
            "remain authoritative.",
            MANAGED_BLOCK_END,
        )
    )
    return _DesiredReviewIssue(
        task_id=task_id,
        title=f"{_TITLE_PREFIX[state]} {task_id} — {title}",
        body_block="\n".join(lines),
        marker=_review_marker(task_id),
    )


def _updated_body(existing_body: str, desired: _DesiredReviewIssue) -> str:
    implementation_marker = (
        f"<!-- no-safe-circle-task: {desired.task_id} -->"
    )
    if implementation_marker in existing_body:
        raise TaskGraphReviewIssueError(
            f"review marker for {desired.task_id} is attached to a normal managed "
            "implementation Issue; refusing to merge the two Issue identities"
        )
    start_count = existing_body.count(MANAGED_BLOCK_START)
    end_count = existing_body.count(MANAGED_BLOCK_END)
    if start_count == 0 and end_count == 0:
        separator = ""
        if existing_body:
            separator = "\n" if existing_body.endswith("\n") else "\n\n"
        return f"{existing_body}{separator}{desired.body_block}\n"
    if start_count != 1 or end_count != 1:
        raise TaskGraphReviewIssueError(
            f"review Issue for {desired.task_id} has malformed managed block markers"
        )
    start = existing_body.index(MANAGED_BLOCK_START)
    end = existing_body.index(MANAGED_BLOCK_END)
    if end < start:
        raise TaskGraphReviewIssueError(
            f"review Issue for {desired.task_id} has reversed managed block markers"
        )
    marker_position = existing_body.index(desired.marker)
    if start <= marker_position < end + len(MANAGED_BLOCK_END):
        raise TaskGraphReviewIssueError(
            f"review Issue for {desired.task_id} stores its identity marker inside "
            "the replaceable managed block"
        )
    suffix_start = end + len(MANAGED_BLOCK_END)
    return (
        existing_body[:start]
        + desired.body_block
        + existing_body[suffix_start:]
    )


def _expected_issue_visible(
    backend: ReviewIssueBackend,
    desired: _DesiredReviewIssue,
    expected_body: str,
    *,
    operation: str,
) -> dict[str, Any]:
    attempts = 0
    last_reason = "no verification read completed"
    for delay_seconds in POST_MUTATION_VERIFICATION_DELAYS_SECONDS:
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        attempts += 1
        try:
            matches = _marker_matches(backend.list_issues(), desired.task_id)
        except Exception as exc:  # Read uncertainty is retried; writes never are.
            last_reason = f"verification read failed: {exc}"
            continue
        if len(matches) > 1:
            raise TaskGraphReviewIssueError(
                f"{operation} for {desired.task_id} exposed multiple open Issues "
                "with the exact review marker; the write was not repeated"
            )
        if not matches:
            last_reason = "marker-matched review Issue is not visible yet"
            continue
        issue = matches[0]
        if issue.get("title") == desired.title and issue.get("body") == expected_body:
            return issue
        last_reason = "marker-matched review Issue is visible with stale title/body"
    raise TaskGraphReviewIssueError(
        f"{operation} for {desired.task_id} could not be verified after {attempts} "
        f"bounded read attempt(s): {last_reason}; the write was not repeated"
    )


def _refresh_existing(
    backend: ReviewIssueBackend,
    issue: Mapping[str, Any],
    desired: _DesiredReviewIssue,
) -> bool:
    number = _issue_number(issue)
    body = issue.get("body")
    if type(body) is not str:
        raise TaskGraphReviewIssueError(
            f"review Issue #{number} for {desired.task_id} has no string body"
        )
    expected_body = _updated_body(body, desired)
    title_stale = issue.get("title") != desired.title
    body_stale = body != expected_body
    if not title_stale and not body_stale:
        return False
    try:
        backend.update_issue(
            number,
            title=desired.title if title_stale else None,
            body=expected_body if body_stale else None,
        )
    except Exception:
        # The edit may have been accepted before a timeout/transport error.
        # Verify read-only and never repeat the mutation.
        _expected_issue_visible(
            backend,
            desired,
            expected_body,
            operation="uncertain review Issue update",
        )
        return True
    _expected_issue_visible(
        backend,
        desired,
        expected_body,
        operation="review Issue update",
    )
    return True


def _create_or_accept_concurrent(
    backend: ReviewIssueBackend,
    desired: _DesiredReviewIssue,
) -> str:
    # A fresh read immediately before creation catches an Issue that became
    # visible after the scan (including a prior accepted-but-uncertain write).
    matches = _marker_matches(backend.list_issues(), desired.task_id)
    if len(matches) > 1:
        raise TaskGraphReviewIssueError(
            f"multiple open GitHub Issues match {desired.task_id} immediately "
            "before creation; no create was attempted"
        )
    if matches:
        return "updated" if _refresh_existing(backend, matches[0], desired) else "current"
    try:
        backend.create_issue(
            title=desired.title,
            body=desired.new_body,
            labels=[],
            assignees=[],
        )
    except Exception:
        # Never issue a duplicate-prone second create. The only recovery is a
        # bounded read for the exact hidden marker and exact desired content.
        _expected_issue_visible(
            backend,
            desired,
            desired.new_body,
            operation="uncertain review Issue create",
        )
        return "created"
    _expected_issue_visible(
        backend,
        desired,
        desired.new_body,
        operation="review Issue create",
    )
    return "created"


def materialize_taskgraph_review_issues(
    *,
    source_commit: str,
    states: Mapping[str, Mapping[str, Any]],
    tasks: Mapping[str, Mapping[str, Any]],
    backend: ReviewIssueBackend,
) -> ReviewIssueMaterializationResult:
    """Create or refresh exactly one open review-work Issue per review task."""

    if (
        type(source_commit) is not str
        or len(source_commit) != 40
        or any(character not in "0123456789abcdef" for character in source_commit)
    ):
        raise TaskGraphReviewIssueError("review materialization requires an exact HEAD SHA")

    desired: dict[str, _DesiredReviewIssue] = {}
    for task_id in sorted(states):
        if TASK_ID_RE.fullmatch(task_id) is None:
            raise TaskGraphReviewIssueError(
                f"review state snapshot contains malformed task ID {task_id!r}"
            )
        row = states[task_id]
        if row.get("state") not in REVIEW_STATES:
            continue
        task = tasks.get(task_id)
        if task is None:
            raise TaskGraphReviewIssueError(
                f"review state snapshot has no committed contract for {task_id}"
            )
        desired[task_id] = _desired_issue(
            source_commit=source_commit,
            state_row=row,
            task=task,
        )

    task_ids = tuple(sorted(desired))
    initial_issues = backend.list_issues()
    # Global duplicate/body preflight happens before the first write. A bad
    # mapping cannot leave an arbitrarily partial scan behind.
    existing = _require_unique_matches(initial_issues, task_ids)
    for task_id, issue in existing.items():
        body = issue.get("body")
        if type(body) is not str:
            raise TaskGraphReviewIssueError(
                f"review Issue #{_issue_number(issue)} for {task_id} has no string body"
            )
        _updated_body(body, desired[task_id])

    created: list[str] = []
    updated: list[str] = []
    current: list[str] = []
    for task_id in task_ids:
        issue = existing.get(task_id)
        if issue is not None:
            if _refresh_existing(backend, issue, desired[task_id]):
                updated.append(task_id)
            else:
                current.append(task_id)
            continue
        outcome = _create_or_accept_concurrent(backend, desired[task_id])
        if outcome == "created":
            created.append(task_id)
        elif outcome == "updated":
            updated.append(task_id)
        else:
            current.append(task_id)

    return ReviewIssueMaterializationResult(
        source_commit=source_commit,
        inspected_task_count=len(states),
        review_task_count=len(task_ids),
        created_task_ids=tuple(created),
        updated_task_ids=tuple(updated),
        already_current_task_ids=tuple(current),
    )


def materialize_current_taskgraph_review_issues(
    *,
    source: Path | str,
    backend: ReviewIssueBackend,
) -> ReviewIssueMaterializationResult:
    snapshot = observe_taskgraph_review_snapshot(source)
    return materialize_taskgraph_review_issues(
        source_commit=snapshot.source_commit,
        states=snapshot.states,
        tasks=snapshot.tasks,
        backend=backend,
    )


__all__ = [
    "MANAGED_BLOCK_END",
    "MANAGED_BLOCK_START",
    "REVIEW_MARKER_TEMPLATE",
    "REVIEW_STATES",
    "ReviewIssueMaterializationResult",
    "TaskGraphReviewIssueError",
    "TaskGraphReviewSnapshot",
    "materialize_current_taskgraph_review_issues",
    "materialize_taskgraph_review_issues",
    "observe_taskgraph_review_snapshot",
]
