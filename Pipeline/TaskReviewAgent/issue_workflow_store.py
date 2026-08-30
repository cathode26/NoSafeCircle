"""GitHub Issue persistence for the durable No Safe Circle workflow controller."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .actor_policy import actor_login, default_actor_policy
from .contracts import TaskReviewContractError, semantic_sha256, validate_task_id
from .issue_workflow import (
    ALL_STATE_LABELS,
    MAX_IGNORED_COMMENT_DIAGNOSTICS,
    STATE_LABELS,
    STATE_RE,
    IssueWorkflowEvent,
    IssueWorkflowState,
    WorkflowActor,
    WorkflowContractError,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    initial_state,
    issue_is_agent_ready,
    labels_for_state,
    parse_events,
    parse_human_validation_result,
    parse_state,
    render_event_comment,
    transition,
    update_issue_body,
    utc_now,
    validate_event_chain,
)

REPOSITORY = "cathode26/NoSafeCircle"
TASK_MARKER_TEMPLATE = "<!-- no-safe-circle-task: {task_id} -->"
DEFAULT_ASSIGNEE = "cathode26"
LABEL_DEFINITIONS = {
    "nsc-state:agent-ready": ("1d76db", "Ready for a generic agent to resume"),
    "nsc-state:agent-working": ("5319e7", "Currently leased by an agent"),
    "nsc-state:human-action": ("d4c5f9", "Waiting for Vincent's Unity/runtime work"),
    "nsc-state:blocked": ("b60205", "Blocked on a human decision or external dependency"),
    "nsc-state:complete": ("0e8a16", "Workflow and closeout finished"),
}


class IssueWorkflowStoreError(TaskReviewContractError):
    """Raised when GitHub Issue workflow state cannot be changed safely."""


class IssueBackend(Protocol):
    def list_issues(self) -> list[dict[str, Any]]: ...
    def get_comments(self, issue_number: int) -> list[dict[str, Any]]: ...
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
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]: ...
    def add_comment(self, issue_number: int, body: str) -> dict[str, Any]: ...
    def ensure_labels(self) -> None: ...


class TaskLoader(Protocol):
    def __call__(self, task_id: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class IssueWorkflowSnapshot:
    issue_number: int
    issue_url: str
    title: str
    body: str
    labels: tuple[str, ...]
    assignees: tuple[str, ...]
    state: IssueWorkflowState | None
    events: tuple[IssueWorkflowEvent, ...]
    managed: bool
    valid: bool
    reasons: tuple[str, ...]
    # Non-authoritative visibility: authority-shaped comments from unauthorized
    # or authorless accounts that were ignored during event-chain construction.
    # These never make the Issue invalid and never block coordination.
    ignored_comment_diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_number": self.issue_number,
            "issue_url": self.issue_url,
            "title": self.title,
            "labels": list(self.labels),
            "assignees": list(self.assignees),
            "managed": self.managed,
            "valid": self.valid,
            "reasons": list(self.reasons),
            "ignored_comment_diagnostics": list(self.ignored_comment_diagnostics),
            "workflow_state": self.state.to_dict() if self.state else None,
            "event_count": len(self.events),
            "last_event_id": self.events[-1].event_id if self.events else None,
        }


def _task_marker(task_id: str) -> str:
    return TASK_MARKER_TEMPLATE.format(task_id=validate_task_id(task_id))


def issue_author_authorized(issue: Mapping[str, Any]) -> bool:
    """True only when the Issue author is on the committed actor allow-list.

    The repository is public; an Issue created by any other login must never
    become managed workflow authority, no matter what its title or body claim.
    A missing author fails closed.
    """

    login = actor_login(issue)
    return login is not None and default_actor_policy().is_authorized_actor(login)


def _issue_labels(issue: Mapping[str, Any]) -> tuple[str, ...]:
    raw = issue.get("labels") or []
    result = []
    for item in raw:
        name = item.get("name") if isinstance(item, Mapping) else item
        if type(name) is str and name:
            result.append(name)
    return tuple(sorted(set(result)))


def _issue_assignees(issue: Mapping[str, Any]) -> tuple[str, ...]:
    raw = issue.get("assignees") or []
    result = []
    for item in raw:
        login = item.get("login") if isinstance(item, Mapping) else item
        if type(login) is str and login:
            result.append(login)
    return tuple(sorted(set(result)))


def _find_candidates(
    issues: Iterable[dict[str, Any]],
    task_id: str,
) -> list[dict[str, Any]]:
    marker = _task_marker(task_id)
    candidates = []
    for issue in issues:
        if str(issue.get("state") or "").upper() == "CLOSED":
            continue
        title = issue.get("title")
        body = issue.get("body")
        title_match = type(title) is str and (
            title == task_id or title.startswith(f"{task_id} —")
        )
        marker_match = type(body) is str and marker in body
        if (title_match or marker_match) and issue_author_authorized(issue):
            candidates.append(issue)
    return candidates


def _unauthorized_claimant_diagnostics(
    issues: Iterable[dict[str, Any]],
    task_id: str,
) -> list[str]:
    """Name open unauthorized Issues that imitate this task, without authority.

    An outside account can copy a task title or marker into a public Issue.
    Such an Issue never becomes the managed Issue, never reserves resources,
    and never blocks work — but it stays visible as a bounded non-authoritative
    diagnostic naming the Issue and login.
    """

    marker = _task_marker(task_id)
    diagnostics: list[str] = []
    for issue in issues:
        if str(issue.get("state") or "").upper() == "CLOSED":
            continue
        title = issue.get("title")
        body = issue.get("body")
        title_match = type(title) is str and (
            title == task_id or title.startswith(f"{task_id} —")
        )
        marker_match = type(body) is str and marker in body
        if (title_match or marker_match) and not issue_author_authorized(issue):
            diagnostics.append(
                f"ignored Issue #{issue.get('number')} by unauthorized login "
                f"{actor_login(issue)!r}: it imitates {task_id} but carries no "
                "workflow authority and reserves no resources"
            )
    return diagnostics[:MAX_IGNORED_COMMENT_DIAGNOSTICS]


def render_contract_body(task: Mapping[str, Any]) -> str:
    task_id = validate_task_id(task.get("id"))
    lines = [
        _task_marker(task_id),
        f"# {task_id} — {task.get('title', '')}",
        "",
        "## Task contract",
        "",
        f"- **Contract:** `Tasks/{task_id}.yaml`",
        f"- **Revision:** `{task.get('contract_revision')}`",
        f"- **Kind:** `{task.get('kind')}`",
        f"- **Execution scope:** `{task.get('execution_scope')}`",
        f"- **Decomposition:** `{task.get('decomposition_state')}`",
        "",
        "## What this task implements",
        "",
        str(task.get("execution_reason") or "No execution reason recorded."),
        "",
        "## Dependencies",
        "",
    ]
    dependencies = task.get("depends_on") or []
    lines.extend([f"- `{item}`" for item in dependencies] or ["- None."])
    lines.extend(("", "## Acceptance criteria", ""))
    criteria = task.get("acceptance_criteria") or []
    if criteria:
        for item in criteria:
            if isinstance(item, Mapping):
                lines.append(
                    f"- **{item.get('criterion_id', '')}** — "
                    f"{item.get('requirement', '')}"
                )
    else:
        lines.append("- None.")
    lines.extend(("", "## Completion gates", ""))
    gates = task.get("completion_gates") or []
    if gates:
        for item in gates:
            if isinstance(item, Mapping):
                lines.append(
                    f"- **{item.get('gate_id', '')}** — {item.get('requirement', '')}"
                )
    else:
        lines.append("- None.")
    lines.extend(("", "## Exclusive resources", ""))
    resources = task.get("exclusive_resources") or []
    lines.extend([f"- `{item}`" for item in resources] or ["- None."])
    return "\n".join(lines).rstrip() + "\n"


def _snapshot(
    backend: IssueBackend,
    issue: Mapping[str, Any],
) -> IssueWorkflowSnapshot:
    number = issue.get("number")
    if type(number) is not int:
        raise IssueWorkflowStoreError("GitHub Issue is missing an integer number")
    body = str(issue.get("body") or "")
    labels = _issue_labels(issue)
    assignees = _issue_assignees(issue)
    reasons: list[str] = []
    ignored_diagnostics: list[str] = []
    state = None
    events: tuple[IssueWorkflowEvent, ...] = ()
    try:
        state = parse_state(body)
        managed = state is not None
        if managed:
            if not issue_author_authorized(issue):
                raise WorkflowContractError(
                    f"Issue #{number} claims managed workflow state but its author "
                    f"{actor_login(issue)!r} is not an authorized workflow actor"
                )
            events = parse_events(
                backend.get_comments(number),
                ignored_diagnostics=ignored_diagnostics,
            )
            validate_event_chain(state, events)
            expected_label = STATE_LABELS[state.state.value]
            state_labels = set(labels) & ALL_STATE_LABELS
            if state_labels != {expected_label}:
                reasons.append(
                    f"workflow state label mismatch: expected {expected_label!r}, "
                    f"found {sorted(state_labels)}"
                )
    except WorkflowContractError as exc:
        managed = state is not None
        reasons.append(str(exc))
    return IssueWorkflowSnapshot(
        issue_number=number,
        issue_url=str(issue.get("url") or ""),
        title=str(issue.get("title") or ""),
        body=body,
        labels=labels,
        assignees=assignees,
        state=state,
        events=events,
        managed=managed,
        valid=not reasons,
        reasons=tuple(reasons),
        ignored_comment_diagnostics=tuple(ignored_diagnostics),
    )


class IssueWorkflowService:
    """Own the state machine while a backend performs GitHub persistence."""

    def __init__(
        self,
        *,
        backend: IssueBackend,
        task_loader: TaskLoader,
        worker_id: str,
        assignee: str = DEFAULT_ASSIGNEE,
    ) -> None:
        self.backend = backend
        self.task_loader = task_loader
        self.worker_id = str(worker_id).strip()
        self.assignee = str(assignee).strip()
        if not self.worker_id or not self.assignee:
            raise IssueWorkflowStoreError("worker_id and assignee must be non-empty")

    def find(self, task_id: str) -> IssueWorkflowSnapshot | None:
        task_id = validate_task_id(task_id)
        candidates = _find_candidates(self.backend.list_issues(), task_id)
        if len(candidates) > 1:
            raise IssueWorkflowStoreError(
                f"multiple open GitHub Issues match {task_id}: "
                + ", ".join(str(item.get("number")) for item in candidates)
            )
        return _snapshot(self.backend, candidates[0]) if candidates else None

    def observe(self, task_id: str) -> dict[str, Any]:
        task_id = validate_task_id(task_id)
        snapshot = self.find(task_id)
        # Unauthorized public Issues that imitate this task are visible as
        # non-authoritative diagnostics only; they never change the status.
        ignored_issues = _unauthorized_claimant_diagnostics(
            self.backend.list_issues(), task_id
        )
        if snapshot is None:
            return {
                "status": "agent_ready_uninitialized",
                "task_id": task_id,
                "worker_id": self.worker_id,
                "issue_number": None,
                "issue_url": None,
                "workflow_state": None,
                "reasons": ["no open Issue exists; the workflow can initialize it"],
                "ignored_issue_diagnostics": ignored_issues,
                "authority": "issue_workflow_read_write",
            }
        if not snapshot.valid:
            return {
                "status": "conflict",
                "task_id": task_id,
                "worker_id": self.worker_id,
                **snapshot.to_dict(),
                "ignored_issue_diagnostics": ignored_issues,
                "authority": "issue_workflow_read_write",
            }
        if not snapshot.managed or snapshot.state is None:
            return {
                "status": "agent_ready_uninitialized",
                "task_id": task_id,
                "worker_id": self.worker_id,
                **snapshot.to_dict(),
                "reasons": ["Issue exists but has no managed workflow state"],
                "ignored_issue_diagnostics": ignored_issues,
                "authority": "issue_workflow_read_write",
            }
        state = snapshot.state
        if state.state is WorkflowState.AGENT_WORKING:
            status = (
                "agent_working_by_worker"
                if state.worker_id == self.worker_id
                else "agent_working_by_other"
            )
        else:
            status = state.state.value
        return {
            "status": status,
            "task_id": task_id,
            "worker_id": self.worker_id,
            **snapshot.to_dict(),
            "ignored_issue_diagnostics": ignored_issues,
            "authority": "issue_workflow_read_write",
        }

    def _resource_conflicts(
        self,
        task: Mapping[str, Any],
    ) -> tuple[list[str], list[str]]:
        """Check every open workflow-claiming Issue for resource reservations.

        Every valid open AUTHORIZED managed Issue whose state is not COMPLETE
        reserves its committed task resources — including ``agent_ready``,
        because a paused Issue in repair, delivery evidence, pending checks,
        or merge closeout still owns its branch's write surfaces. An
        authorized Issue that claims workflow state but cannot be validated
        surfaces as a blocking coordination conflict requiring repair.

        An Issue whose author is NOT on the committed actor allow-list carries
        no workflow authority at all: it never reserves resources and never
        blocks work, because otherwise any public account could deny service
        by pasting state-looking text into an Issue. Such Issues are reported
        in the second returned list as bounded non-authoritative diagnostics.
        """

        selected_resources = set(task.get("exclusive_resources") or [])
        conflicts: list[str] = []
        diagnostics: list[str] = []
        # A resource-less candidate still scans every open Issue: an authorized
        # Issue claiming managed workflow state with an invalid event chain has
        # untrustworthy ownership/reservation state and must block coordination
        # until repaired, even when the selected task reserves nothing itself.
        for issue in self.backend.list_issues():
            if str(issue.get("state") or "").upper() == "CLOSED":
                # A closed COMPLETE Issue reserves nothing; a closed incomplete
                # duplicate carries no workflow authority (completed_issue_guard).
                continue
            number = issue.get("number")
            body = str(issue.get("body") or "")
            if STATE_RE.search(body) is None:
                # Plain repository Issue without a managed workflow claim.
                continue
            if not issue_author_authorized(issue):
                if len(diagnostics) < MAX_IGNORED_COMMENT_DIAGNOSTICS:
                    diagnostics.append(
                        f"ignored Issue #{number} by unauthorized login "
                        f"{actor_login(issue)!r}: it imitates managed workflow "
                        "state but carries no authority and reserves no resources"
                    )
                continue
            try:
                snapshot = _snapshot(self.backend, issue)
            except IssueWorkflowStoreError as exc:
                conflicts.append(
                    f"workflow Issue #{number} could not be inspected: {exc}"
                )
                continue
            if snapshot.state is not None and snapshot.state.task_id == task.get("id"):
                continue
            if not snapshot.valid or snapshot.state is None:
                conflicts.append(
                    f"Issue #{number} claims managed workflow state but is invalid and "
                    f"must be repaired before resource coordination: "
                    + "; ".join(snapshot.reasons)
                )
                continue
            if snapshot.state.state is WorkflowState.COMPLETE:
                continue
            if not selected_resources:
                # A valid Issue reserves resources only by actual overlap, and
                # overlap with an empty selection is impossible, so the other
                # task's resources need not be loaded.
                continue
            try:
                other = self.task_loader(snapshot.state.task_id)
            except Exception:
                conflicts.append(
                    f"could not inspect resources for reserved {snapshot.state.task_id}"
                )
                continue
            overlap = sorted(
                selected_resources & set(other.get("exclusive_resources") or [])
            )
            if overlap:
                conflicts.append(
                    f"{snapshot.state.task_id} reserves overlapping resources: {overlap}"
                )
        return conflicts, diagnostics

    def _initialize_issue(
        self,
        task: Mapping[str, Any],
        *,
        now: str,
    ) -> IssueWorkflowSnapshot:
        task_id = validate_task_id(task.get("id"))
        contract_hash = str(task.get("task_contract_sha256") or "")
        state = initial_state(
            task_id=task_id,
            task_contract_sha256=contract_hash,
            now=now,
        )
        body = update_issue_body(
            render_contract_body(task),
            state,
            next_action=(
                "A generic TaskReviewAgent may acquire an agent lease and continue the "
                "current phase."
            ),
        )
        labels = labels_for_state(state.state)
        existing = self.find(task_id)
        self.backend.ensure_labels()
        if existing is None:
            issue = self.backend.create_issue(
                title=f"{task_id} — {task.get('title', '')}",
                body=body,
                labels=labels,
                assignees=[self.assignee],
            )
        else:
            if existing.managed:
                return existing
            issue = self.backend.update_issue(
                existing.issue_number,
                body=body,
                labels=labels,
                assignees=[self.assignee],
            )
        return _snapshot(self.backend, issue)

    def acquire_agent_lease(
        self,
        *,
        task: Mapping[str, Any],
        source_head: str,
        branch: str,
        checkout_path: str,
        planned_approach: str,
        expected_validation: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        task_id = validate_task_id(task.get("id"))
        conflicts, coordination_diagnostics = self._resource_conflicts(task)
        if conflicts:
            return {
                "status": "blocked",
                "reasons": conflicts,
                "coordination_diagnostics": coordination_diagnostics,
            }
        occurred = now or utc_now()
        snapshot = self.find(task_id)
        if snapshot is None or not snapshot.managed:
            snapshot = self._initialize_issue(task, now=occurred)
        if not snapshot.valid or snapshot.state is None:
            raise IssueWorkflowStoreError(
                "cannot acquire a lease from invalid workflow state: "
                + "; ".join(snapshot.reasons)
            )
        state = snapshot.state
        if state.task_contract_sha256 != task.get("task_contract_sha256"):
            raise IssueWorkflowStoreError(
                "Issue workflow uses a different task contract hash"
            )
        if state.state is WorkflowState.AGENT_WORKING and state.worker_id == self.worker_id:
            return {
                "status": "resumed",
                "coordination_diagnostics": coordination_diagnostics,
                **snapshot.to_dict(),
            }
        if state.state is not WorkflowState.AGENT_READY:
            return {
                "status": "blocked",
                "reasons": [f"workflow state is {state.state.value}, not agent_ready"],
                "coordination_diagnostics": coordination_diagnostics,
                **snapshot.to_dict(),
            }
        lease_id = semantic_sha256(
            {
                "task_id": task_id,
                "worker_id": self.worker_id,
                "state_version": state.state_version,
                "source_head": source_head,
                "occurred_at_utc": occurred,
            }
        )
        next_state, event = transition(
            state,
            event_type=WorkflowEventType.AGENT_LEASE_ACQUIRED,
            actor_type=WorkflowActor.AGENT,
            actor_id=self.worker_id,
            to_state=WorkflowState.AGENT_WORKING,
            details={
                "worker_id": self.worker_id,
                "lease_id": lease_id,
                "source_head": source_head,
                "branch": branch,
                "checkout_path": checkout_path,
                "planned_approach": planned_approach.strip(),
                "expected_validation": expected_validation.strip(),
            },
            now=occurred,
        )
        comment = render_event_comment(
            event,
            "\n".join(
                (
                    "The generic TaskReviewAgent acquired this task.",
                    "",
                    f"- **Worker:** `{self.worker_id}`",
                    f"- **Base commit:** `{source_head}`",
                    f"- **Branch:** `{branch}`",
                    f"- **Checkout:** `{checkout_path}`",
                    "",
                    "### Planned approach",
                    planned_approach.strip(),
                    "",
                    "### Expected validation",
                    expected_validation.strip(),
                )
            ),
        )
        self.backend.add_comment(snapshot.issue_number, comment)
        updated_body = update_issue_body(
            snapshot.body,
            next_state,
            next_action=(
                "The current agent should continue the recorded phase and either create a "
                "human handoff, release the lease, or record a blocker."
            ),
        )
        self.backend.update_issue(
            snapshot.issue_number,
            body=updated_body,
            labels=labels_for_state(next_state.state, snapshot.labels),
            assignees=[self.assignee],
        )
        verified = self.find(task_id)
        if verified is None or not verified.valid or verified.state != next_state:
            raise IssueWorkflowStoreError(
                "GitHub Issue lease transition could not be verified; stop to avoid a "
                "split lease"
            )
        return {
            "status": "acquired",
            "coordination_diagnostics": coordination_diagnostics,
            **verified.to_dict(),
        }

    def publish_human_handoff(
        self,
        *,
        task_id: str,
        branch: str,
        head_commit: str,
        checkout_path: str,
        implementation_summary: str,
        completed_checks: Iterable[str],
        human_steps: Iterable[str],
        expected_result: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.find(task_id)
        if snapshot is None or not snapshot.valid or snapshot.state is None:
            raise IssueWorkflowStoreError("human handoff requires a valid managed Issue")
        state = snapshot.state
        if state.state is not WorkflowState.AGENT_WORKING or state.worker_id != self.worker_id:
            raise IssueWorkflowStoreError(
                "human handoff requires this worker's active lease"
            )
        occurred = now or utc_now()
        next_state, event = transition(
            state,
            event_type=WorkflowEventType.HUMAN_HANDOFF_CREATED,
            actor_type=WorkflowActor.AGENT,
            actor_id=self.worker_id,
            to_state=WorkflowState.HUMAN_ACTION_REQUIRED,
            to_phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
            details={
                "branch": branch,
                "head_commit": head_commit,
                "checkout_path": checkout_path,
                "implementation_summary": implementation_summary.strip(),
            },
            now=occurred,
        )
        checks = [str(item).strip() for item in completed_checks if str(item).strip()]
        steps = [str(item).strip() for item in human_steps if str(item).strip()]
        handoff_lines = [
            "The agent committed and pushed the implementation. Vincent now owns the next step.",
            "",
            f"- **Branch:** `{branch}`",
            f"- **Commit to test:** `{head_commit}`",
            f"- **Checkout:** `{checkout_path}`",
            "",
            "### What was implemented",
            implementation_summary.strip(),
            "",
            "### Checks already completed",
            *([f"- {item}" for item in checks] or ["- None recorded."]),
            "",
            "### Steps for Vincent",
            *(
                [f"{index}. {item}" for index, item in enumerate(steps, start=1)]
                or ["1. Review the recorded commit."]
            ),
            "",
            "### Expected result",
            expected_result.strip(),
            "",
            "### Record the result in this Issue",
            "",
            "Post a new comment using this exact shape, replacing both placeholders:",
            "",
            "```text",
            "## Human validation result",
            "",
            "Result: <PASS or FAIL>",
            "Tested commit: <40-character commit SHA>",
            "",
            "Completed steps:",
            "- ...",
            "",
            "Notes:",
            "...",
            "```",
            "",
            "The exact commit to test is recorded above in this handoff. For a "
            "failure, include the exact failed step, reproduction, expected result, "
            "and observed result.",
            "After posting the result, apply the `nsc-state:agent-ready` label. The "
            "Issue workflow action will move the task back to agent work.",
        ]
        self.backend.add_comment(
            snapshot.issue_number,
            render_event_comment(event, "\n".join(handoff_lines)),
        )
        updated_body = update_issue_body(
            snapshot.body,
            next_state,
            next_action=(
                "Test the exact recorded commit in Unity, post the Human validation "
                "result template, then apply `nsc-state:agent-ready`."
            ),
        )
        self.backend.update_issue(
            snapshot.issue_number,
            body=updated_body,
            labels=labels_for_state(next_state.state, snapshot.labels),
            assignees=[self.assignee],
        )
        verified = self.find(task_id)
        if verified is None or not verified.valid or verified.state != next_state:
            raise IssueWorkflowStoreError("human handoff transition could not be verified")
        return {"status": "human_action_required", **verified.to_dict()}

    def apply_human_result(
        self,
        *,
        task_id: str,
        result_body: str,
        actor_id: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.find(task_id)
        if snapshot is None or not snapshot.valid or snapshot.state is None:
            raise IssueWorkflowStoreError("human result requires a valid managed Issue")
        state = snapshot.state
        if state.state is not WorkflowState.HUMAN_ACTION_REQUIRED:
            raise IssueWorkflowStoreError(
                f"human result requires human_action_required, found {state.state.value}"
            )
        if not default_actor_policy().is_authorized_human(actor_id):
            raise IssueWorkflowStoreError(
                f"human validation authority requires the authorized human operator "
                f"login; {actor_id!r} is not authorized"
            )
        human_result = parse_human_validation_result(result_body)
        if human_result is None:
            raise IssueWorkflowStoreError(
                "human result comment must contain Result: PASS|FAIL and Tested commit: "
                "<40-sha>"
            )
        event_type = (
            WorkflowEventType.HUMAN_VALIDATION_PASSED
            if human_result.result == "pass"
            else WorkflowEventType.HUMAN_VALIDATION_FAILED
        )
        next_phase = (
            WorkflowPhase.DELIVERY_EVIDENCE
            if human_result.result == "pass"
            else WorkflowPhase.REPAIR
        )
        next_state, event = transition(
            state,
            event_type=event_type,
            actor_type=WorkflowActor.HUMAN,
            actor_id=actor_id,
            to_state=WorkflowState.AGENT_READY,
            to_phase=next_phase,
            details={
                "tested_commit": human_result.tested_commit,
                "result": human_result.result,
                "human_comment_sha256": semantic_sha256({"body": result_body}),
            },
            now=now or utc_now(),
        )
        self.backend.add_comment(
            snapshot.issue_number,
            render_event_comment(
                event,
                (
                    f"Human Unity validation recorded **{human_result.result.upper()}** "
                    f"for commit `{human_result.tested_commit}`. The next agent phase is "
                    f"`{next_phase.value}`."
                ),
            ),
        )
        updated_body = update_issue_body(
            snapshot.body,
            next_state,
            next_action=(
                "A generic agent should resume this Issue. Use the human result and "
                "current phase to continue from the recorded branch and commit."
            ),
        )
        self.backend.update_issue(
            snapshot.issue_number,
            body=updated_body,
            labels=labels_for_state(next_state.state, snapshot.labels),
            assignees=[self.assignee],
        )
        verified = self.find(task_id)
        if verified is None or not verified.valid or verified.state != next_state:
            raise IssueWorkflowStoreError("human result transition could not be verified")
        return {"status": "agent_ready", **verified.to_dict()}

    def list_agent_ready(self) -> list[dict[str, Any]]:
        ready = []
        for issue in self.backend.list_issues():
            snapshot = _snapshot(self.backend, issue)
            if not snapshot.valid or not snapshot.managed or snapshot.state is None:
                continue
            if issue_is_agent_ready(
                snapshot.body,
                snapshot.labels,
                self.backend.get_comments(snapshot.issue_number),
            ):
                ready.append(snapshot.to_dict())
        return sorted(ready, key=lambda item: (item["issue_number"], item["title"]))


class MemoryIssueBackend:
    """No-network backend for state-machine and race/failure tests."""

    def __init__(self, *, author_login: str = DEFAULT_ASSIGNEE) -> None:
        self.issues: dict[int, dict[str, Any]] = {}
        self.comments: dict[int, list[dict[str, Any]]] = {}
        self.next_issue = 1
        self.next_comment = 1
        self.labels: set[str] = set()
        # Issues and comments created through this backend model the operator's
        # authenticated gh session, so they carry the gh CLI author shape.
        self.author_login = author_login

    def list_issues(self) -> list[dict[str, Any]]:
        return [json.loads(json.dumps(item)) for _, item in sorted(self.issues.items())]

    def get_comments(self, issue_number: int) -> list[dict[str, Any]]:
        return json.loads(json.dumps(self.comments.get(issue_number, [])))

    def create_issue(
        self,
        *,
        title: str,
        body: str,
        labels: list[str],
        assignees: list[str],
    ) -> dict[str, Any]:
        number = self.next_issue
        self.next_issue += 1
        issue = {
            "number": number,
            "title": title,
            "body": body,
            "state": "OPEN",
            "url": f"https://example.invalid/issues/{number}",
            "author": {"login": self.author_login},
            "labels": [{"name": item} for item in labels],
            "assignees": [{"login": item} for item in assignees],
        }
        self.issues[number] = issue
        self.comments[number] = []
        return json.loads(json.dumps(issue))

    def update_issue(
        self,
        issue_number: int,
        *,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        issue = self.issues[issue_number]
        if body is not None:
            issue["body"] = body
        if labels is not None:
            issue["labels"] = [{"name": item} for item in labels]
        if assignees is not None:
            issue["assignees"] = [{"login": item} for item in assignees]
        return json.loads(json.dumps(issue))

    def add_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        comment = {
            "id": self.next_comment,
            "author": {"login": self.author_login},
            "body": body,
        }
        self.next_comment += 1
        self.comments.setdefault(issue_number, []).append(comment)
        return json.loads(json.dumps(comment))

    def ensure_labels(self) -> None:
        self.labels.update(LABEL_DEFINITIONS)


class GhIssueBackend:
    """Authenticated `gh` backend with a narrow Issue-only mutation surface."""

    def __init__(
        self,
        *,
        source_root: Path | str,
        repository: str = REPOSITORY,
    ) -> None:
        self.source_root = Path(source_root).resolve()
        self.repository = repository
        if shutil.which("gh") is None:
            raise IssueWorkflowStoreError("GitHub CLI 'gh' is not installed")
        auth = self._run(
            ("gh", "auth", "status", "--hostname", "github.com"),
            check=False,
        )
        if auth.returncode != 0:
            raise IssueWorkflowStoreError(
                "GitHub CLI is not authenticated for github.com"
            )

    def _run(
        self,
        args: Sequence[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["GH_PAGER"] = "cat"
        environment["NO_COLOR"] = "1"
        result = subprocess.run(
            tuple(args),
            cwd=str(self.source_root),
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=180.0,
        )
        if check and result.returncode != 0:
            raise IssueWorkflowStoreError(
                f"GitHub command failed ({result.returncode}): {' '.join(args)}\n"
                f"{result.stdout}\n{result.stderr}"
            )
        return result

    def _json(self, args: Sequence[str]) -> Any:
        result = self._run(args)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise IssueWorkflowStoreError("GitHub CLI returned invalid JSON") from exc

    def _list_issues_via_api(self, state: str) -> list[dict[str, Any]]:
        """List issues completely via `gh api --paginate`.

        `gh issue list --limit N` silently truncates after N results, which
        would forget old completed tasks and let them be reinitialized. The
        REST pagination follows Link headers to exhaustion, and any transport
        failure raises instead of returning a partial listing. `--paginate`
        emits one JSON array per page back-to-back, so the output is decoded
        as concatenated JSON documents. Pull requests share the REST issues
        endpoint and are excluded by their `pull_request` key.
        """

        result = self._run(
            (
                "gh",
                "api",
                "--paginate",
                f"repos/{self.repository}/issues?state={state}&per_page=100",
            )
        )
        decoder = json.JSONDecoder()
        text = result.stdout
        index = 0
        issues: list[dict[str, Any]] = []
        while True:
            while index < len(text) and text[index] in " \t\r\n":
                index += 1
            if index >= len(text):
                break
            try:
                page, index = decoder.raw_decode(text, index)
            except json.JSONDecodeError as exc:
                raise IssueWorkflowStoreError(
                    "GitHub issue listing returned invalid JSON"
                ) from exc
            if not isinstance(page, list):
                raise IssueWorkflowStoreError(
                    "GitHub issue listing page was not an array"
                )
            for item in page:
                if not isinstance(item, dict):
                    raise IssueWorkflowStoreError(
                        "GitHub issue listing entry was not an object"
                    )
                if "pull_request" in item:
                    continue
                html_url = item.get("html_url")
                if isinstance(html_url, str) and html_url:
                    # REST `url` is the API endpoint. gh issue list/view expose
                    # the browser URL as `url`, and workflow snapshots surface
                    # it through `issue_url`, so normalize to the browser URL.
                    item = {**item, "url": html_url}
                issues.append(item)
        return issues

    def list_issues(self) -> list[dict[str, Any]]:
        return self._list_issues_via_api("open")

    def get_comments(self, issue_number: int) -> list[dict[str, Any]]:
        value = self._json(
            (
                "gh",
                "issue",
                "view",
                str(issue_number),
                "--repo",
                self.repository,
                "--json",
                "comments",
            )
        )
        comments = value.get("comments") if isinstance(value, dict) else None
        if not isinstance(comments, list):
            raise IssueWorkflowStoreError("gh issue view did not return comments")
        return comments

    def create_issue(
        self,
        *,
        title: str,
        body: str,
        labels: list[str],
        assignees: list[str],
    ) -> dict[str, Any]:
        args = [
            "gh",
            "issue",
            "create",
            "--repo",
            self.repository,
            "--title",
            title,
            "--body",
            body,
        ]
        for label in labels:
            args.extend(("--label", label))
        for assignee in assignees:
            args.extend(("--assignee", assignee))
        result = self._run(tuple(args))
        url = result.stdout.strip()
        number_match = re.search(r"/(\d+)$", url)
        if not number_match:
            raise IssueWorkflowStoreError(
                "gh issue create did not return an Issue URL"
            )
        return self._view_issue(int(number_match.group(1)))

    def _view_issue(self, issue_number: int) -> dict[str, Any]:
        value = self._json(
            (
                "gh",
                "issue",
                "view",
                str(issue_number),
                "--repo",
                self.repository,
                "--json",
                "number,title,state,assignees,url,body,labels,author",
            )
        )
        if not isinstance(value, dict):
            raise IssueWorkflowStoreError("gh issue view did not return an object")
        return value

    def update_issue(
        self,
        issue_number: int,
        *,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        args = [
            "gh",
            "issue",
            "edit",
            str(issue_number),
            "--repo",
            self.repository,
        ]
        current = self._view_issue(issue_number)
        if body is not None:
            args.extend(("--body", body))
        if labels is not None:
            current_labels = set(_issue_labels(current))
            desired = set(labels)
            for label in sorted(current_labels - desired):
                args.extend(("--remove-label", label))
            for label in sorted(desired - current_labels):
                args.extend(("--add-label", label))
        if assignees is not None:
            current_assignees = set(_issue_assignees(current))
            desired_assignees = set(assignees)
            for assignee in sorted(current_assignees - desired_assignees):
                args.extend(("--remove-assignee", assignee))
            for assignee in sorted(desired_assignees - current_assignees):
                args.extend(("--add-assignee", assignee))
        if len(args) > 6:
            self._run(tuple(args))
        return self._view_issue(issue_number)

    def add_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        result = self._run(
            (
                "gh",
                "issue",
                "comment",
                str(issue_number),
                "--repo",
                self.repository,
                "--body",
                body,
            )
        )
        return {"url": result.stdout.strip(), "body": body}

    def ensure_labels(self) -> None:
        for name, (color, description) in LABEL_DEFINITIONS.items():
            self._run(
                (
                    "gh",
                    "label",
                    "create",
                    name,
                    "--repo",
                    self.repository,
                    "--color",
                    color,
                    "--description",
                    description,
                    "--force",
                )
            )
