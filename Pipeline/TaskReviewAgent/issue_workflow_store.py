"""GitHub Issue persistence for the durable No Safe Circle workflow controller."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
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

# GitHub origin remote forms accepted as durable Issue-authority evidence.
# Only these three shapes are recognized; anything else fails closed rather
# than guessing a repository.
_GITHUB_HTTPS_ORIGIN_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)
_GITHUB_SCP_SSH_ORIGIN_RE = re.compile(
    r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$"
)
_GITHUB_SSH_URL_ORIGIN_RE = re.compile(
    r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)
_OWNER_OR_REPO_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# Matches `scheme://userinfo@` for ANY URI scheme (RFC 3986 scheme grammar),
# not only http(s): an unsupported credential-bearing origin such as
# ssh://user:secret@github.com/... must still be redacted before an error
# message is built, even though that form is never accepted as a supported
# GitHub remote (see _parse_github_repository).
_CREDENTIAL_PREFIX_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*://)[^/@]+@")
DEFAULT_ASSIGNEE = "cathode26"
VINCENT_INBOX_TITLE = "NSC-Vincent"
VINCENT_INBOX_MARKER = "<!-- nsc-vincent-inbox -->"
VINCENT_NOTIFICATION_MARKER_PREFIX = "<!-- nsc-vincent-notification:"
LABEL_DEFINITIONS = {
    "nsc-state:agent-ready": ("1d76db", "Ready for a generic agent to resume"),
    "nsc-state:agent-working": ("5319e7", "Currently leased by an agent"),
    "nsc-state:human-action": ("d4c5f9", "Waiting for Vincent's Unity/runtime work"),
    "nsc-state:blocked": ("b60205", "Blocked on a human decision or external dependency"),
    "nsc-state:complete": ("0e8a16", "Workflow and closeout finished"),
}

# Positive, structurally-proven benign blocked_kind values for
# acquire_agent_lease()'s "status": "blocked" result. These name ONLY the two
# post-claim races where another AUTHORIZED worker already holds valid
# durable authority -- ordinary concurrent ownership, never a symptom of an
# invalid/tampered Issue, a contract mismatch, or an operational failure.
# Every other blocked result omits blocked_kind entirely and callers must
# treat an absent/unrecognized blocked_kind as unsafe to retry.
BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER = "durable_ownership_by_other"
BLOCKED_KIND_DURABLE_RESOURCE_RESERVATION_CONFLICT = "durable_resource_reservation_conflict"

# GitHub can briefly expose a mixed/stale read after a successful Issue mutation
# (for example an updated body before the newest event comment is visible).
# The mutation itself must NEVER be repeated merely because verification lagged.
# Retry only the read side, for a finite total wait of 15 seconds, then fail closed.
POST_MUTATION_VERIFICATION_DELAYS_SECONDS = (0.0, 1.0, 2.0, 4.0, 8.0)


class IssueWorkflowStoreError(TaskReviewContractError):
    """Raised when GitHub Issue workflow state cannot be changed safely."""


def _redact_origin(url: str) -> str:
    """Strip embedded HTTPS basic-auth credentials before an error message."""

    return _CREDENTIAL_PREFIX_RE.sub(r"\1", url)


def _parse_github_repository(origin: str) -> tuple[str, str] | None:
    """Parse a Git origin remote URL into a GitHub ``(owner, repo)`` pair.

    Returns ``None`` for anything that is not exactly one of the supported
    GitHub remote shapes (HTTPS, SSH URL, or SCP-style SSH) with a well-formed
    owner and repository segment. Never guesses from a partial match.
    """

    text = origin.strip()
    for pattern in (
        _GITHUB_HTTPS_ORIGIN_RE,
        _GITHUB_SCP_SSH_ORIGIN_RE,
        _GITHUB_SSH_URL_ORIGIN_RE,
    ):
        match = pattern.match(text)
        if match is None:
            continue
        owner = match.group("owner")
        repo = match.group("repo")
        if not _OWNER_OR_REPO_SEGMENT_RE.match(owner):
            return None
        if not _OWNER_OR_REPO_SEGMENT_RE.match(repo):
            return None
        return owner, repo
    return None


def _normalize_owner_repo(value: str) -> str:
    """Validate and canonicalize an explicit ``owner/repo`` assertion string."""

    text = str(value).strip()
    if text.count("/") != 1:
        raise IssueWorkflowStoreError(
            f"repository {value!r} must be exactly one 'owner/repo' segment"
        )
    owner, _, repo = text.partition("/")
    if not _OWNER_OR_REPO_SEGMENT_RE.match(owner) or not _OWNER_OR_REPO_SEGMENT_RE.match(repo):
        raise IssueWorkflowStoreError(f"repository {value!r} is malformed")
    return f"{owner}/{repo}"


def _origin_remote_url(source_root: Path) -> str:
    try:
        result = subprocess.run(
            ("git", "-C", str(source_root), "remote", "get-url", "origin"),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IssueWorkflowStoreError(
            f"could not read the Git 'origin' remote for source checkout "
            f"{source_root}: {exc}"
        ) from exc
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise IssueWorkflowStoreError(
            f"source checkout {source_root} has no readable Git 'origin' remote"
            + (f": {stderr}" if stderr else "")
        )
    origin = result.stdout.strip()
    if not origin:
        raise IssueWorkflowStoreError(
            f"source checkout {source_root} has an empty Git 'origin' remote URL"
        )
    return origin


def resolve_issue_backend_repository(
    source_root: Path | str,
    *,
    repository: str | None = None,
) -> str:
    """Bind durable GitHub Issue authority to the source checkout's Git origin.

    The checkout's ``origin`` remote is the ONLY repository authority: this
    never falls back to :data:`REPOSITORY`, the current working directory,
    ``gh``'s notion of the current repository, or an environment variable.
    Fails closed when the origin is missing, unreadable, or not a recognized
    GitHub remote.

    ``repository`` may be supplied as an explicit assertion (e.g. a
    ``--repo`` CLI argument) that MUST match the origin-resolved repository,
    case-insensitively. A mismatch raises before any GitHub Issue read or
    write is attempted.
    """

    root = Path(source_root).resolve()
    origin = _origin_remote_url(root)
    parsed = _parse_github_repository(origin)
    if parsed is None:
        raise IssueWorkflowStoreError(
            f"source checkout {root} 'origin' remote is not a supported GitHub "
            f"repository remote: {_redact_origin(origin)!r}"
        )
    owner, repo = parsed
    resolved = f"{owner}/{repo}"
    if repository is None:
        return resolved
    asserted = _normalize_owner_repo(repository)
    if asserted.casefold() != resolved.casefold():
        raise IssueWorkflowStoreError(
            f"explicit repository {repository!r} does not match {resolved!r} "
            f"resolved from {root}'s Git 'origin' remote; refusing to bind "
            "durable GitHub Issue authority to a different repository"
        )
    return resolved


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


class IssueWorkflowReader(Protocol):
    def find(self, task_id: str) -> IssueWorkflowSnapshot | None: ...


def verify_post_mutation_state(
    reader: IssueWorkflowReader,
    task_id: str,
    expected_state: IssueWorkflowState,
    *,
    transition_name: str,
) -> IssueWorkflowSnapshot:
    """Verify one completed mutation with bounded read-only retries."""

    # GitHub Issue body/label/comment reads may become mutually visible at
    # slightly different times. Only reads are retried here; the mutation that
    # produced expected_state is NEVER repeated by this helper.
    attempts = 0
    last_reason = "no verification read completed"

    for delay_seconds in POST_MUTATION_VERIFICATION_DELAYS_SECONDS:
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        attempts += 1
        try:
            verified = reader.find(task_id)
        except IssueWorkflowStoreError as exc:
            last_reason = f"verification read failed: {exc}"
            continue

        if verified is None:
            last_reason = "managed Issue is not visible yet"
            continue

        if not verified.valid:
            detail = "; ".join(verified.reasons) or "snapshot marked invalid"
            last_reason = f"workflow snapshot is not coherent yet: {detail}"
            continue

        if verified.state == expected_state:
            return verified

        if verified.state is None:
            last_reason = "managed workflow state is not visible yet"
            continue

        observed = verified.state
        differing_fields = sorted(
            key
            for key, value in observed.to_dict().items()
            if expected_state.to_dict().get(key) != value
        )
        last_reason = (
            f"observed state_version={observed.state_version} "
            f"state={observed.state.value} phase={observed.phase.value}; "
            f"expected state_version={expected_state.state_version} "
            f"state={expected_state.state.value} phase={expected_state.phase.value}; "
            f"exact fields differ: {differing_fields}"
        )

        # A valid older state may simply be stale and is safe to reread. A
        # valid same-version mismatch or a newer state is not a stale
        # predecessor of our expected transition, so fail closed.
        if observed.state_version >= expected_state.state_version:
            break

    raise IssueWorkflowStoreError(
        f"{transition_name} transition could not be verified after "
        f"{attempts} bounded read attempt(s): {last_reason}; "
        "the durable mutation was not repeated"
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
        vincent_inbox_title: str | None = None,
    ) -> None:
        self.backend = backend
        self.task_loader = task_loader
        self.worker_id = str(worker_id).strip()
        self.assignee = str(assignee).strip()
        if not self.worker_id or not self.assignee:
            raise IssueWorkflowStoreError("worker_id and assignee must be non-empty")
        self.vincent_inbox_title = None
        if vincent_inbox_title is not None:
            normalized_inbox_title = str(vincent_inbox_title).strip()
            if not normalized_inbox_title:
                raise IssueWorkflowStoreError("vincent_inbox_title must be non-empty when configured")
            self.vincent_inbox_title = normalized_inbox_title

    def find(self, task_id: str) -> IssueWorkflowSnapshot | None:
        task_id = validate_task_id(task_id)
        candidates = _find_candidates(self.backend.list_issues(), task_id)
        if len(candidates) > 1:
            raise IssueWorkflowStoreError(
                f"multiple open GitHub Issues match {task_id}: "
                + ", ".join(str(item.get("number")) for item in candidates)
            )
        return _snapshot(self.backend, candidates[0]) if candidates else None

    def verify_post_mutation_state(
        self,
        task_id: str,
        expected_state: IssueWorkflowState,
        *,
        transition_name: str,
    ) -> IssueWorkflowSnapshot:
        return verify_post_mutation_state(
            self,
            task_id,
            expected_state,
            transition_name=transition_name,
        )

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
        conflicts, diagnostics, _blocked_kind = self._resource_conflicts_classified(task)
        return conflicts, diagnostics

    def _resource_conflicts_classified(
        self,
        task: Mapping[str, Any],
    ) -> tuple[list[str], list[str], str | None]:
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

        The third return value is
        :data:`BLOCKED_KIND_DURABLE_RESOURCE_RESERVATION_CONFLICT` if and only
        if ``conflicts`` is non-empty and EVERY entry is a proven exclusive-
        resource overlap against another currently-valid, authorized, managed
        Issue -- never a loose text match. Any inspection failure, invalid or
        unparseable Issue, or task-load failure mixed into the same result
        forces this back to ``None``, so a real repair-worthy failure can
        never be misclassified as ordinary concurrent ownership.
        """

        selected_resources = set(task.get("exclusive_resources") or [])
        conflicts: list[str] = []
        diagnostics: list[str] = []
        all_benign = True
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
                all_benign = False
                continue
            if snapshot.state is not None and snapshot.state.task_id == task.get("id"):
                continue
            if not snapshot.valid or snapshot.state is None:
                conflicts.append(
                    f"Issue #{number} claims managed workflow state but is invalid and "
                    f"must be repaired before resource coordination: "
                    + "; ".join(snapshot.reasons)
                )
                all_benign = False
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
                all_benign = False
                continue
            overlap = sorted(
                selected_resources & set(other.get("exclusive_resources") or [])
            )
            if overlap:
                conflicts.append(
                    f"{snapshot.state.task_id} reserves overlapping resources: {overlap}"
                )
        blocked_kind = (
            BLOCKED_KIND_DURABLE_RESOURCE_RESERVATION_CONFLICT
            if conflicts and all_benign
            else None
        )
        return conflicts, diagnostics, blocked_kind

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
        conflicts, coordination_diagnostics, resource_blocked_kind = (
            self._resource_conflicts_classified(task)
        )
        if conflicts:
            blocked: dict[str, Any] = {
                "status": "blocked",
                "reasons": conflicts,
                "coordination_diagnostics": coordination_diagnostics,
            }
            if resource_blocked_kind is not None:
                blocked["blocked_kind"] = resource_blocked_kind
            return blocked
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
            blocked = {
                "status": "blocked",
                "reasons": [f"workflow state is {state.state.value}, not agent_ready"],
                "coordination_diagnostics": coordination_diagnostics,
                **snapshot.to_dict(),
            }
            if state.state is WorkflowState.AGENT_WORKING:
                # The same-worker AGENT_WORKING case already returned
                # "resumed" above, so reaching here with AGENT_WORKING proves
                # this is a DIFFERENT, already-authenticated worker's valid
                # durable lease -- ordinary concurrent ownership, not an
                # invalid or tampered Issue.
                blocked["blocked_kind"] = BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER
            return blocked
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
        verified = self.verify_post_mutation_state(
            task_id,
            next_state,
            transition_name="GitHub Issue lease",
        )
        return {
            "status": "acquired",
            "coordination_diagnostics": coordination_diagnostics,
            **verified.to_dict(),
        }


    def _find_vincent_inbox(self) -> dict[str, Any] | None:
        # Resolve the configured human-action inbox before any handoff mutation.
        if self.vincent_inbox_title is None:
            return None

        matches = [
            issue
            for issue in self.backend.list_issues()
            if str(issue.get("state") or "").upper() != "CLOSED"
            and issue.get("title") == self.vincent_inbox_title
        ]
        if len(matches) != 1:
            raise IssueWorkflowStoreError(
                f"configured Vincent inbox {self.vincent_inbox_title!r} must resolve to "
                f"exactly one open Issue; found {len(matches)}"
            )

        inbox = matches[0]
        if VINCENT_INBOX_MARKER not in str(inbox.get("body") or ""):
            raise IssueWorkflowStoreError(
                f"configured Vincent inbox {self.vincent_inbox_title!r} is missing "
                f"the required marker {VINCENT_INBOX_MARKER!r}"
            )
        if not issue_author_authorized(inbox):
            raise IssueWorkflowStoreError(
                f"configured Vincent inbox {self.vincent_inbox_title!r} is not authored "
                "by an authorized workflow actor"
            )
        if type(inbox.get("number")) is not int:
            raise IssueWorkflowStoreError("configured Vincent inbox has no integer Issue number")
        return inbox

    @staticmethod
    def _vincent_notification_marker(
        *,
        task_id: str,
        source_issue_number: int,
        head_commit: str,
    ) -> str:
        digest = semantic_sha256(
            {
                "schema_version": "1.0",
                "task_id": validate_task_id(task_id),
                "source_issue_number": source_issue_number,
                "head_commit": head_commit,
            }
        )
        return f"{VINCENT_NOTIFICATION_MARKER_PREFIX}{digest} -->"

    def _matching_vincent_notifications(
        self,
        *,
        issue_number: int,
        marker: str,
    ) -> list[dict[str, Any]]:
        matches = []
        for comment in self.backend.get_comments(issue_number):
            if marker not in str(comment.get("body") or ""):
                continue
            login = actor_login(comment)
            if login is not None and default_actor_policy().is_authorized_actor(login):
                matches.append(comment)
        return matches

    def _ensure_vincent_notification(
        self,
        *,
        inbox: Mapping[str, Any] | None,
        source_issue: IssueWorkflowSnapshot,
        task_id: str,
        branch: str,
        head_commit: str,
        checkout_path: str,
    ) -> str:
        # The source Issue is already authoritative before this method runs.
        # An uncertain notification write is followed only by bounded reads.
        if inbox is None:
            return "disabled"

        inbox_number = inbox.get("number")
        if type(inbox_number) is not int:
            raise IssueWorkflowStoreError("configured Vincent inbox has no integer Issue number")

        marker = self._vincent_notification_marker(
            task_id=task_id,
            source_issue_number=source_issue.issue_number,
            head_commit=head_commit,
        )
        existing = self._matching_vincent_notifications(
            issue_number=inbox_number,
            marker=marker,
        )
        if len(existing) > 1:
            raise IssueWorkflowStoreError(
                "multiple authorized NSC-Vincent notifications already match this handoff"
            )
        if existing:
            return "existing"

        notification = "\n".join(
            (
                "## Vincent attention required",
                "",
                f"Source Issue: #{source_issue.issue_number} — {source_issue.title}",
                f"Why: `{task_id}` is waiting for your Unity/runtime validation.",
                "Action: Open the source Issue and follow its current human checklist.",
                "Report result: Comment on the source Issue, not here.",
                "Afterward: Delete this NSC-Vincent notification comment.",
                "",
                f"- **Branch:** `{branch}`",
                f"- **Commit to test:** `{head_commit}`",
                f"- **Checkout:** `{checkout_path}`",
                "",
                marker,
            )
        )

        uncertain_error_types = (
            IssueWorkflowStoreError,
            OSError,
            subprocess.TimeoutExpired,
        )
        mutation_error: Exception | None = None
        try:
            self.backend.add_comment(inbox_number, notification)
        except uncertain_error_types as exc:
            # The remote comment may have been accepted even when the local
            # process reports a timeout/transport failure. Never repeat this
            # write based on the exception alone.
            mutation_error = exc

        attempts = 0
        last_reason = "notification was not visible"
        for delay_seconds in POST_MUTATION_VERIFICATION_DELAYS_SECONDS:
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            attempts += 1
            try:
                matches = self._matching_vincent_notifications(
                    issue_number=inbox_number,
                    marker=marker,
                )
            except uncertain_error_types as exc:
                # Verification is read-only. Transient GitHub/process errors
                # remain inside the bounded retry loop and never authorize a
                # second add_comment call.
                last_reason = (
                    f"verification read attempt {attempts} failed transiently: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

            if len(matches) == 1:
                return "created"
            if len(matches) > 1:
                raise IssueWorkflowStoreError(
                    "multiple authorized NSC-Vincent notifications were observed after "
                    "one handoff notification mutation"
                )
            last_reason = "no authorized matching notification is visible yet"

        suffix = (
            f"; add_comment reported uncertain outcome: "
            f"{type(mutation_error).__name__}: {mutation_error}"
            if mutation_error is not None
            else ""
        )
        raise IssueWorkflowStoreError(
            f"NSC-Vincent notification could not be verified after {attempts} bounded "
            f"read attempt(s): {last_reason}; the notification mutation was not repeated"
            f"{suffix}"
        )

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

        if state.state is WorkflowState.HUMAN_ACTION_REQUIRED:
            exact_retry = (
                state.phase is WorkflowPhase.UNITY_RUNTIME_VALIDATION
                and state.branch == branch
                and state.head_commit == head_commit
                and state.human_handoff_commit == head_commit
                and state.checkout_path == checkout_path
            )
            if not exact_retry:
                raise IssueWorkflowStoreError(
                    "human handoff retry does not match the durable human-owned handoff"
                )
            vincent_inbox = self._find_vincent_inbox()
            notification_status = self._ensure_vincent_notification(
                inbox=vincent_inbox,
                source_issue=snapshot,
                task_id=task_id,
                branch=branch,
                head_commit=head_commit,
                checkout_path=checkout_path,
            )
            return {
                "status": "human_action_required",
                "vincent_notification": notification_status,
                **snapshot.to_dict(),
            }

        if state.state is not WorkflowState.AGENT_WORKING or state.worker_id != self.worker_id:
            raise IssueWorkflowStoreError(
                "human handoff requires this worker's active lease"
            )

        # Resolve/validate the human inbox BEFORE mutating the source task Issue.
        vincent_inbox = self._find_vincent_inbox()
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
        verified = self.verify_post_mutation_state(
            task_id,
            next_state,
            transition_name="human handoff",
        )
        notification_status = self._ensure_vincent_notification(
            inbox=vincent_inbox,
            source_issue=verified,
            task_id=task_id,
            branch=branch,
            head_commit=head_commit,
            checkout_path=checkout_path,
        )
        return {
            "status": "human_action_required",
            "vincent_notification": notification_status,
            **verified.to_dict(),
        }

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
        verified = self.verify_post_mutation_state(
            task_id,
            next_state,
            transition_name="human result",
        )
        return {"status": "agent_ready", **verified.to_dict()}

    def resource_conflicts(
        self,
        task: Mapping[str, Any],
    ) -> tuple[list[str], list[str]]:
        """Public read-only view of the durable exclusive-resource reservation scan.

        Returns the same ``(conflicts, diagnostics)`` shape as the internal
        acquisition path uses, so read-only callers (Stage 2 dispatch
        planning) can reuse the one committed reservation authority instead
        of reimplementing it.
        """

        return self._resource_conflicts(task)

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
        repository: str | None = None,
    ) -> None:
        self.source_root = Path(source_root).resolve()
        # Repository binding is resolved BEFORE any 'gh' presence/auth check
        # or Issue operation: a source checkout can never silently borrow
        # cathode26/NoSafeCircle's durable Issue authority merely because
        # REPOSITORY used to be the default. See resolve_issue_backend_repository.
        self.repository = resolve_issue_backend_repository(
            self.source_root, repository=repository
        )
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
        raw = subprocess.run(
            tuple(args),
            cwd=str(self.source_root),
            env=environment,
            text=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=180.0,
        )
        if not isinstance(raw.stdout, bytes) or not isinstance(raw.stderr, bytes):
            raise IssueWorkflowStoreError(
                "GitHub CLI did not return byte streams for stdout/stderr"
            )
        try:
            stdout = raw.stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IssueWorkflowStoreError(
                "GitHub CLI stdout was not valid UTF-8"
            ) from exc
        stderr = raw.stderr.decode("utf-8", errors="replace")
        result = subprocess.CompletedProcess(
            args=tuple(args),
            returncode=raw.returncode,
            stdout=stdout,
            stderr=stderr,
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
