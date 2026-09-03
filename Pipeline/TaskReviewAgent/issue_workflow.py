"""Deterministic GitHub Issue workflow state and append-only event contracts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping

from .actor_policy import ActorPolicy, actor_login, default_actor_policy
from .contracts import (
    GIT_SHA_RE,
    SHA256_RE,
    TaskReviewContractError,
    canonical_json,
    semantic_sha256,
    validate_task_id,
)

WORKFLOW_SCHEMA_VERSION = "1.0"
STATE_MARKER = "nsc-workflow-state"
EVENT_MARKER = "nsc-workflow-event"
DASHBOARD_BEGIN = "<!-- nsc-workflow-dashboard:start -->"
DASHBOARD_END = "<!-- nsc-workflow-dashboard:end -->"
STATE_RE = re.compile(
    rf"<!--\s*{re.escape(STATE_MARKER)}\s*(\{{.*?\}})\s*-->",
    re.DOTALL,
)
EVENT_RE = re.compile(
    rf"<!--\s*{re.escape(EVENT_MARKER)}\s*(\{{.*?\}})\s*-->",
    re.DOTALL,
)
HUMAN_RESULT_RE = re.compile(
    r"(?im)^\s*Result:\s*(PASS|FAIL)\s*$.*?"
    r"^\s*Tested commit:\s*`?([0-9a-f]{40})`?\s*$",
    re.DOTALL,
)
DECOMPOSITION_RESULT_RE = re.compile(
    r"(?im)^\s*Result:\s*(APPROVE|REJECT)\s*$.*?"
    r"^\s*Reviewed plan_id:\s*`?(GDP-[0-9a-f]{64})`?\s*$",
    re.DOTALL,
)
HISTORY_MIGRATION_MANIFEST_RE = re.compile(
    r"^Pipeline/TaskGraph/migrations/repository-history-identity-"
    r"([a-z0-9][a-z0-9._-]*)\.json$"
)

STATE_LABELS = {
    "agent_ready": "nsc-state:agent-ready",
    "agent_working": "nsc-state:agent-working",
    "human_action_required": "nsc-state:human-action",
    "blocked": "nsc-state:blocked",
    "complete": "nsc-state:complete",
}
ALL_STATE_LABELS = frozenset(STATE_LABELS.values())


class WorkflowState(str, Enum):
    AGENT_READY = "agent_ready"
    AGENT_WORKING = "agent_working"
    HUMAN_ACTION_REQUIRED = "human_action_required"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class WorkflowPhase(str, Enum):
    IMPLEMENTATION = "implementation"
    REPAIR = "repair"
    UNITY_RUNTIME_VALIDATION = "unity_runtime_validation"
    DELIVERY_EVIDENCE = "delivery_evidence"
    MERGE_CLOSEOUT = "merge_closeout"
    DECOMPOSITION = "decomposition"
    DECOMPOSITION_APPLY_AUTHORIZATION = "decomposition_apply_authorization"
    DECOMPOSITION_APPLY = "decomposition_apply"


class WorkflowActor(str, Enum):
    AGENT = "agent"
    HUMAN = "human"
    NONE = "none"


class WorkflowEventType(str, Enum):
    WORKFLOW_INITIALIZED = "workflow_initialized"
    AGENT_LEASE_ACQUIRED = "agent_lease_acquired"
    AGENT_LEASE_RELEASED = "agent_lease_released"
    HUMAN_HANDOFF_CREATED = "human_handoff_created"
    HUMAN_VALIDATION_PASSED = "human_validation_passed"
    HUMAN_VALIDATION_FAILED = "human_validation_failed"
    TASK_CONTRACT_MIGRATED = "task_contract_migrated"
    REPOSITORY_HISTORY_MIGRATED = "repository_history_migrated"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"
    COMPLETED = "completed"
    DECOMPOSITION_HANDOFF_CREATED = "decomposition_handoff_created"
    DECOMPOSITION_APPLICATION_APPROVED = "decomposition_application_approved"
    DECOMPOSITION_APPLICATION_REJECTED = "decomposition_application_rejected"


class WorkflowContractError(TaskReviewContractError):
    """Raised when issue workflow state or history is invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _string(value: Any, *, field: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if type(value) is not str or not value.strip():
        raise WorkflowContractError(f"{field} must be a non-empty string")
    return value.strip()


def _sha(
    value: Any,
    *,
    field: str,
    optional: bool = False,
    sha256: bool = False,
) -> str | None:
    text = _string(value, field=field, optional=optional)
    if text is None:
        return None
    pattern = SHA256_RE if sha256 else GIT_SHA_RE
    if not pattern.fullmatch(text):
        raise WorkflowContractError(f"{field} has an invalid identity")
    return text


def _enum(value: Any, enum_type: type[Enum], *, field: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise WorkflowContractError(f"{field} is invalid: {value!r}") from exc


def _details(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise WorkflowContractError("event details must be an object")
    try:
        normalized = json.loads(canonical_json(dict(value)))
    except (TypeError, ValueError) as exc:
        raise WorkflowContractError("event details must be finite JSON") from exc
    if not isinstance(normalized, dict):
        raise WorkflowContractError("event details must remain an object")
    return normalized


def _history_migration_details(details: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "migration_id",
        "manifest_path",
        "rewrite_report_sha256",
        "old_head_commit",
        "new_head_commit",
        "head_tree",
        "old_human_handoff_commit",
        "new_human_handoff_commit",
    }
    if set(details) != expected:
        raise WorkflowContractError(
            "repository history migration details keys mismatch; "
            f"missing={sorted(expected-set(details))}, "
            f"extras={sorted(set(details)-expected)}"
        )
    migration_id = _string(details.get("migration_id"), field="migration_id")
    manifest_path = _string(details.get("manifest_path"), field="manifest_path")
    match = HISTORY_MIGRATION_MANIFEST_RE.fullmatch(manifest_path or "")
    if match is None or match.group(1) != migration_id:
        raise WorkflowContractError(
            "repository history migration manifest_path and migration_id disagree"
        )
    rewrite_report_sha256 = _sha(
        details.get("rewrite_report_sha256"),
        field="rewrite_report_sha256",
        sha256=True,
    )
    old_head_commit = _sha(details.get("old_head_commit"), field="old_head_commit")
    new_head_commit = _sha(details.get("new_head_commit"), field="new_head_commit")
    head_tree = _sha(details.get("head_tree"), field="head_tree")
    old_handoff = _sha(
        details.get("old_human_handoff_commit"),
        field="old_human_handoff_commit",
        optional=True,
    )
    new_handoff = _sha(
        details.get("new_human_handoff_commit"),
        field="new_human_handoff_commit",
        optional=True,
    )
    if old_head_commit == new_head_commit:
        raise WorkflowContractError(
            "repository history migration must change the workflow head commit"
        )
    if (old_handoff is None) != (new_handoff is None):
        raise WorkflowContractError(
            "repository history migration handoff commits must both be null or both be Git SHAs"
        )
    return {
        "migration_id": migration_id,
        "manifest_path": manifest_path,
        "rewrite_report_sha256": rewrite_report_sha256,
        "old_head_commit": old_head_commit,
        "new_head_commit": new_head_commit,
        "head_tree": head_tree,
        "old_human_handoff_commit": old_handoff,
        "new_human_handoff_commit": new_handoff,
    }


@dataclass(frozen=True)
class IssueWorkflowState:
    task_id: str
    state: WorkflowState
    phase: WorkflowPhase
    current_actor: WorkflowActor
    task_contract_sha256: str
    state_version: int = 0
    last_event_id: str | None = None
    worker_id: str | None = None
    lease_id: str | None = None
    branch: str | None = None
    head_commit: str | None = None
    checkout_path: str | None = None
    human_handoff_commit: str | None = None
    human_result: str | None = None
    updated_at_utc: str = "1970-01-01T00:00:00Z"
    schema_version: str = WORKFLOW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != WORKFLOW_SCHEMA_VERSION:
            raise WorkflowContractError("unsupported workflow schema_version")
        object.__setattr__(self, "task_id", validate_task_id(self.task_id))
        object.__setattr__(self, "state", _enum(self.state, WorkflowState, field="state"))
        object.__setattr__(self, "phase", _enum(self.phase, WorkflowPhase, field="phase"))
        object.__setattr__(
            self,
            "current_actor",
            _enum(self.current_actor, WorkflowActor, field="current_actor"),
        )
        object.__setattr__(
            self,
            "task_contract_sha256",
            _sha(
                self.task_contract_sha256,
                field="task_contract_sha256",
                sha256=True,
            ),
        )
        if type(self.state_version) is not int or self.state_version < 0:
            raise WorkflowContractError("state_version must be a non-negative integer")
        object.__setattr__(
            self,
            "last_event_id",
            _sha(self.last_event_id, field="last_event_id", optional=True, sha256=True),
        )
        object.__setattr__(
            self,
            "worker_id",
            _string(self.worker_id, field="worker_id", optional=True),
        )
        object.__setattr__(
            self,
            "lease_id",
            _sha(self.lease_id, field="lease_id", optional=True, sha256=True),
        )
        object.__setattr__(self, "branch", _string(self.branch, field="branch", optional=True))
        object.__setattr__(
            self,
            "head_commit",
            _sha(self.head_commit, field="head_commit", optional=True),
        )
        object.__setattr__(
            self,
            "checkout_path",
            _string(self.checkout_path, field="checkout_path", optional=True),
        )
        object.__setattr__(
            self,
            "human_handoff_commit",
            _sha(
                self.human_handoff_commit,
                field="human_handoff_commit",
                optional=True,
            ),
        )
        if self.human_result not in (None, "pass", "fail"):
            raise WorkflowContractError("human_result must be pass, fail, or null")
        object.__setattr__(
            self,
            "updated_at_utc",
            _string(self.updated_at_utc, field="updated_at_utc"),
        )
        self._validate_semantics()

    def _validate_semantics(self) -> None:
        if self.state_version == 0 and self.last_event_id is not None:
            raise WorkflowContractError("version-zero state cannot name a last event")
        if self.state_version > 0 and self.last_event_id is None:
            raise WorkflowContractError("nonzero state_version requires last_event_id")
        if self.state is WorkflowState.AGENT_WORKING:
            if self.current_actor is not WorkflowActor.AGENT:
                raise WorkflowContractError("agent_working requires current_actor=agent")
            if self.worker_id is None or self.lease_id is None:
                raise WorkflowContractError("agent_working requires worker_id and lease_id")
        elif self.worker_id is not None or self.lease_id is not None:
            raise WorkflowContractError("only agent_working may retain worker_id/lease_id")
        if self.state is WorkflowState.HUMAN_ACTION_REQUIRED:
            if self.current_actor is not WorkflowActor.HUMAN:
                raise WorkflowContractError(
                    "human_action_required requires current_actor=human"
                )
            if not all((self.branch, self.head_commit, self.checkout_path)):
                raise WorkflowContractError(
                    "human_action_required requires branch, head_commit, and checkout_path"
                )
            if self.human_handoff_commit != self.head_commit:
                raise WorkflowContractError(
                    "human_handoff_commit must match head_commit during human action"
                )
            if self.human_result is not None:
                raise WorkflowContractError(
                    "human_action_required cannot already contain a human result"
                )
        if self.state is WorkflowState.AGENT_READY:
            if self.current_actor is not WorkflowActor.AGENT:
                raise WorkflowContractError("agent_ready requires current_actor=agent")
        if self.state is WorkflowState.COMPLETE:
            if self.current_actor is not WorkflowActor.NONE:
                raise WorkflowContractError("complete requires current_actor=none")
        if self.human_result is not None and self.state not in (
            WorkflowState.AGENT_READY,
            WorkflowState.AGENT_WORKING,
            WorkflowState.BLOCKED,
            WorkflowState.COMPLETE,
        ):
            raise WorkflowContractError("human result is not valid in the current state")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "state": self.state.value,
            "phase": self.phase.value,
            "current_actor": self.current_actor.value,
            "worker_id": self.worker_id,
            "lease_id": self.lease_id,
            "branch": self.branch,
            "head_commit": self.head_commit,
            "checkout_path": self.checkout_path,
            "task_contract_sha256": self.task_contract_sha256,
            "state_version": self.state_version,
            "last_event_id": self.last_event_id,
            "human_handoff_commit": self.human_handoff_commit,
            "human_result": self.human_result,
            "updated_at_utc": self.updated_at_utc,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "IssueWorkflowState":
        if not isinstance(value, Mapping):
            raise WorkflowContractError("workflow state must be an object")
        expected = {
            "schema_version",
            "task_id",
            "state",
            "phase",
            "current_actor",
            "worker_id",
            "lease_id",
            "branch",
            "head_commit",
            "checkout_path",
            "task_contract_sha256",
            "state_version",
            "last_event_id",
            "human_handoff_commit",
            "human_result",
            "updated_at_utc",
        }
        if set(value) != expected:
            raise WorkflowContractError(
                f"workflow state keys mismatch; missing={sorted(expected-set(value))}, "
                f"extras={sorted(set(value)-expected)}"
            )
        return cls(**dict(value))


@dataclass(frozen=True)
class IssueWorkflowEvent:
    task_id: str
    sequence: int
    previous_event_id: str | None
    event_type: WorkflowEventType
    from_state: WorkflowState
    to_state: WorkflowState
    from_phase: WorkflowPhase
    to_phase: WorkflowPhase
    actor_type: WorkflowActor
    actor_id: str
    task_contract_sha256: str
    occurred_at_utc: str
    details: dict[str, Any]
    event_id: str
    schema_version: str = WORKFLOW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != WORKFLOW_SCHEMA_VERSION:
            raise WorkflowContractError("unsupported event schema_version")
        object.__setattr__(self, "task_id", validate_task_id(self.task_id))
        if type(self.sequence) is not int or self.sequence < 1:
            raise WorkflowContractError("event sequence must be a positive integer")
        object.__setattr__(
            self,
            "previous_event_id",
            _sha(
                self.previous_event_id,
                field="previous_event_id",
                optional=True,
                sha256=True,
            ),
        )
        if self.sequence == 1 and self.previous_event_id is not None:
            raise WorkflowContractError("first event cannot have previous_event_id")
        if self.sequence > 1 and self.previous_event_id is None:
            raise WorkflowContractError("later event requires previous_event_id")
        object.__setattr__(
            self,
            "event_type",
            _enum(self.event_type, WorkflowEventType, field="event_type"),
        )
        object.__setattr__(
            self,
            "from_state",
            _enum(self.from_state, WorkflowState, field="from_state"),
        )
        object.__setattr__(
            self,
            "to_state",
            _enum(self.to_state, WorkflowState, field="to_state"),
        )
        object.__setattr__(
            self,
            "from_phase",
            _enum(self.from_phase, WorkflowPhase, field="from_phase"),
        )
        object.__setattr__(
            self,
            "to_phase",
            _enum(self.to_phase, WorkflowPhase, field="to_phase"),
        )
        object.__setattr__(
            self,
            "actor_type",
            _enum(self.actor_type, WorkflowActor, field="actor_type"),
        )
        object.__setattr__(self, "actor_id", _string(self.actor_id, field="actor_id"))
        object.__setattr__(
            self,
            "task_contract_sha256",
            _sha(
                self.task_contract_sha256,
                field="task_contract_sha256",
                sha256=True,
            ),
        )
        object.__setattr__(
            self,
            "occurred_at_utc",
            _string(self.occurred_at_utc, field="occurred_at_utc"),
        )
        object.__setattr__(self, "details", _details(self.details))
        object.__setattr__(
            self,
            "event_id",
            _sha(self.event_id, field="event_id", sha256=True),
        )
        if semantic_sha256(self.identity_payload()) != self.event_id:
            raise WorkflowContractError("event_id does not match event payload")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "sequence": self.sequence,
            "previous_event_id": self.previous_event_id,
            "event_type": self.event_type.value,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "from_phase": self.from_phase.value,
            "to_phase": self.to_phase.value,
            "actor_type": self.actor_type.value,
            "actor_id": self.actor_id,
            "task_contract_sha256": self.task_contract_sha256,
            "occurred_at_utc": self.occurred_at_utc,
            "details": self.details,
        }

    def to_dict(self) -> dict[str, Any]:
        return {"event_id": self.event_id, **self.identity_payload()}

    @classmethod
    def create(cls, **values: Any) -> "IssueWorkflowEvent":
        payload = dict(values)
        payload.setdefault("schema_version", WORKFLOW_SCHEMA_VERSION)
        normalized = {
            **payload,
            "event_type": WorkflowEventType(payload["event_type"]).value,
            "from_state": WorkflowState(payload["from_state"]).value,
            "to_state": WorkflowState(payload["to_state"]).value,
            "from_phase": WorkflowPhase(payload["from_phase"]).value,
            "to_phase": WorkflowPhase(payload["to_phase"]).value,
            "actor_type": WorkflowActor(payload["actor_type"]).value,
            "details": _details(payload.get("details")),
        }
        return cls(event_id=semantic_sha256(normalized), **normalized)

    @classmethod
    def from_dict(cls, value: Any) -> "IssueWorkflowEvent":
        if not isinstance(value, Mapping):
            raise WorkflowContractError("workflow event must be an object")
        expected = {
            "event_id",
            "schema_version",
            "task_id",
            "sequence",
            "previous_event_id",
            "event_type",
            "from_state",
            "to_state",
            "from_phase",
            "to_phase",
            "actor_type",
            "actor_id",
            "task_contract_sha256",
            "occurred_at_utc",
            "details",
        }
        if set(value) != expected:
            raise WorkflowContractError("workflow event keys do not match contract")
        return cls(**dict(value))


@dataclass(frozen=True)
class HumanValidationResult:
    result: str
    tested_commit: str
    body: str

    def __post_init__(self) -> None:
        if self.result not in ("pass", "fail"):
            raise WorkflowContractError("human result must be pass or fail")
        object.__setattr__(
            self,
            "tested_commit",
            _sha(self.tested_commit, field="tested_commit"),
        )
        object.__setattr__(self, "body", _string(self.body, field="human result body"))


@dataclass(frozen=True)
class DecompositionApplicationResult:
    result: str
    reviewed_plan_id: str
    body: str

    def __post_init__(self) -> None:
        if self.result not in ("approve", "reject"):
            raise WorkflowContractError(
                "decomposition application result must be approve or reject"
            )
        if re.fullmatch(r"GDP-[0-9a-f]{64}", self.reviewed_plan_id) is None:
            raise WorkflowContractError("reviewed_plan_id has an invalid identity")
        object.__setattr__(self, "body", _string(self.body, field="decomposition result body"))


_FENCE_LINE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")


def strip_fenced_blocks(body: str) -> str:
    """Remove fenced code blocks so instructional templates can never parse.

    The agent handoff comment shows the human-result template inside a fenced
    ```` ```text ```` block. Text inside any fence is quoted material, not a
    statement by the comment author, so result parsing must never read it.

    A fence opens with three or more consecutive backticks or tildes after
    optional indentation; the marker character and the opening run length are
    tracked. A close requires the SAME marker character, a run at least as
    long as the opening run, and nothing but whitespace after it — so a
    four-backtick outer fence is never closed early by a three-backtick line
    quoted inside it. An unterminated fence is dropped through the end of the
    body (fail closed).
    """

    kept: list[str] = []
    fence_marker: str | None = None
    fence_length = 0
    for line in body.splitlines():
        match = _FENCE_LINE_RE.match(line)
        if fence_marker is None:
            if match is not None:
                run = match.group(1)
                fence_marker = run[0]
                fence_length = len(run)
                continue
            kept.append(line)
        elif (
            match is not None
            and match.group(1)[0] == fence_marker
            and len(match.group(1)) >= fence_length
            and not match.group(2).strip()
        ):
            fence_marker = None
            fence_length = 0
    return "\n".join(kept)


def parse_human_validation_result(body: str) -> HumanValidationResult | None:
    if type(body) is not str:
        return None
    match = HUMAN_RESULT_RE.search(strip_fenced_blocks(body))
    if not match:
        return None
    return HumanValidationResult(match.group(1).casefold(), match.group(2), body)


def parse_decomposition_application_result(
    body: str,
) -> DecompositionApplicationResult | None:
    if type(body) is not str:
        return None
    match = DECOMPOSITION_RESULT_RE.search(strip_fenced_blocks(body))
    if not match:
        return None
    return DecompositionApplicationResult(
        match.group(1).casefold(), match.group(2), body
    )


def _comment_body(item: Any) -> str | None:
    body = item.get("body") if isinstance(item, Mapping) else item
    return body if type(body) is str else None


def _comment_reference(item: Any, index: int) -> str:
    if isinstance(item, Mapping) and item.get("id") is not None:
        return f"comment {item.get('id')}"
    return f"comment at position {index}"


def _anchor_comment_index(comments: list[Any], event_id: str) -> int | None:
    """Locate the comment that carries the workflow event ``event_id``."""

    for index, item in enumerate(comments):
        body = _comment_body(item)
        if body is None:
            continue
        for match in EVENT_RE.findall(body):
            try:
                value = json.loads(match)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping) and value.get("event_id") == event_id:
                return index
    return None


def human_comments_after_event(
    comments: Iterable[Any],
    *,
    after_event_id: str,
    policy: ActorPolicy | None = None,
) -> tuple[list[Any], list[str]]:
    """Return authorized-human comments posted after a workflow event comment.

    Workflow-event comments (agent/automation authored) are excluded, as is any
    comment without an authorized human author. If the anchoring event comment
    cannot be found, no comment is eligible (fail closed) and the reason names
    the missing event.
    """

    policy = policy or default_actor_policy()
    items = list(comments)
    anchor = _anchor_comment_index(items, after_event_id)
    if anchor is None:
        return [], [
            f"the comment carrying workflow event {after_event_id} was not found; "
            "no later human comment can be proven to follow it"
        ]
    candidates = []
    for item in items[anchor + 1 :]:
        body = _comment_body(item)
        if body is None:
            continue
        if EVENT_RE.search(body):
            continue
        login = actor_login(item)
        if login is None or not policy.is_authorized_human(login):
            continue
        candidates.append(item)
    return candidates, []


def find_human_validation_result(
    comments: Iterable[Any],
    *,
    after_event_id: str,
    expected_commit: str,
    policy: ActorPolicy | None = None,
) -> tuple[HumanValidationResult | None, list[str]]:
    """Select the latest trustworthy human validation result.

    A result counts only when it was posted after the comment carrying the
    current handoff event, is not itself a workflow event comment, was authored
    by the authorized human operator, and names the exact handoff commit.
    Rejected near-matches are reported for diagnostics.
    """

    policy = policy or default_actor_policy()
    items = list(comments)
    anchor = _anchor_comment_index(items, after_event_id)
    if anchor is None:
        return None, [
            f"the comment carrying handoff event {after_event_id} was not found; "
            "no human result can be proven to follow the current handoff"
        ]
    reasons: list[str] = []
    selected: HumanValidationResult | None = None
    for index, item in enumerate(items[anchor + 1 :], start=anchor + 1):
        body = _comment_body(item)
        if body is None:
            continue
        if EVENT_RE.search(body):
            continue
        parsed = parse_human_validation_result(body)
        if parsed is None:
            continue
        reference = _comment_reference(item, index)
        login = actor_login(item)
        if login is None:
            reasons.append(
                f"{reference} contains a validation result but has no author identity; rejected"
            )
            continue
        if not policy.is_authorized_human(login):
            reasons.append(
                f"{reference} validation result author {login!r} is not the authorized "
                "human operator; rejected"
            )
            continue
        if parsed.tested_commit != expected_commit:
            reasons.append(
                f"{reference} tested commit {parsed.tested_commit} does not match the "
                f"handoff commit {expected_commit}; rejected"
            )
            continue
        selected = parsed
    return selected, reasons


def initial_state(
    *,
    task_id: str,
    task_contract_sha256: str,
    phase: WorkflowPhase = WorkflowPhase.IMPLEMENTATION,
    now: str | None = None,
) -> IssueWorkflowState:
    return IssueWorkflowState(
        task_id=task_id,
        state=WorkflowState.AGENT_READY,
        phase=phase,
        current_actor=WorkflowActor.AGENT,
        task_contract_sha256=task_contract_sha256,
        updated_at_utc=now or utc_now(),
    )


def transition(
    state: IssueWorkflowState,
    *,
    event_type: WorkflowEventType,
    actor_type: WorkflowActor,
    actor_id: str,
    to_state: WorkflowState,
    to_phase: WorkflowPhase | None = None,
    details: Mapping[str, Any] | None = None,
    now: str | None = None,
) -> tuple[IssueWorkflowState, IssueWorkflowEvent]:
    target_phase = to_phase or state.phase
    _validate_transition(state, event_type, actor_type, to_state, target_phase, details or {})
    occurred = now or utc_now()
    event = IssueWorkflowEvent.create(
        task_id=state.task_id,
        sequence=state.state_version + 1,
        previous_event_id=state.last_event_id,
        event_type=event_type,
        from_state=state.state,
        to_state=to_state,
        from_phase=state.phase,
        to_phase=target_phase,
        actor_type=actor_type,
        actor_id=actor_id,
        task_contract_sha256=state.task_contract_sha256,
        occurred_at_utc=occurred,
        details=dict(details or {}),
    )
    updates: dict[str, Any] = {
        "state": to_state,
        "phase": target_phase,
        "state_version": event.sequence,
        "last_event_id": event.event_id,
        "updated_at_utc": occurred,
    }
    if to_state is WorkflowState.AGENT_WORKING:
        updates.update(
            current_actor=WorkflowActor.AGENT,
            worker_id=event.details.get("worker_id"),
            lease_id=event.details.get("lease_id"),
            human_result=state.human_result,
        )
    else:
        updates.update(worker_id=None, lease_id=None)
        if to_state is WorkflowState.HUMAN_ACTION_REQUIRED:
            updates.update(
                current_actor=WorkflowActor.HUMAN,
                branch=event.details.get("branch"),
                head_commit=event.details.get("head_commit"),
                checkout_path=event.details.get("checkout_path"),
                human_handoff_commit=event.details.get("head_commit"),
                human_result=None,
            )
        elif to_state is WorkflowState.AGENT_READY:
            updates.update(
                current_actor=WorkflowActor.AGENT,
                human_result=(
                    "pass"
                    if event_type is WorkflowEventType.HUMAN_VALIDATION_PASSED
                    else "fail"
                    if event_type is WorkflowEventType.HUMAN_VALIDATION_FAILED
                    else state.human_result
                ),
            )
        elif to_state is WorkflowState.BLOCKED:
            updates.update(current_actor=actor_type)
        elif to_state is WorkflowState.COMPLETE:
            updates.update(current_actor=WorkflowActor.NONE)
    if event_type is WorkflowEventType.TASK_CONTRACT_MIGRATED:
        updates.update(
            task_contract_sha256=event.details["new_task_contract_sha256"],
            current_actor=WorkflowActor.AGENT,
            worker_id=None,
            lease_id=None,
            branch=event.details.get("branch") or state.branch,
            head_commit=event.details.get("head_commit") or state.head_commit,
            checkout_path=event.details.get("checkout_path") or state.checkout_path,
            human_handoff_commit=event.details.get("human_handoff_commit"),
            human_result=event.details.get("human_result"),
        )
    if event_type is WorkflowEventType.REPOSITORY_HISTORY_MIGRATED:
        updates.update(
            current_actor=WorkflowActor.NONE,
            worker_id=None,
            lease_id=None,
            head_commit=event.details["new_head_commit"],
            human_handoff_commit=event.details["new_human_handoff_commit"],
            human_result=state.human_result,
        )
    return replace(state, **updates), event


def _validate_transition(
    state: IssueWorkflowState,
    event_type: WorkflowEventType,
    actor_type: WorkflowActor,
    to_state: WorkflowState,
    to_phase: WorkflowPhase,
    details: Mapping[str, Any],
) -> None:
    if event_type is WorkflowEventType.REPOSITORY_HISTORY_MIGRATED:
        if state.state is not WorkflowState.COMPLETE:
            raise WorkflowContractError(
                "repository history migration is allowed only from complete workflow state"
            )
        if state.phase is not WorkflowPhase.MERGE_CLOSEOUT:
            raise WorkflowContractError(
                "repository history migration requires merge_closeout phase"
            )
        if (
            to_state is not WorkflowState.COMPLETE
            or to_phase is not WorkflowPhase.MERGE_CLOSEOUT
            or actor_type is not WorkflowActor.HUMAN
        ):
            raise WorkflowContractError(
                "repository history migration must be a human complete-to-complete merge_closeout transition"
            )
        parsed = _history_migration_details(details)
        if state.head_commit is None or parsed["old_head_commit"] != state.head_commit:
            raise WorkflowContractError(
                "repository history migration old_head_commit does not match Issue state"
            )
        if parsed["old_human_handoff_commit"] != state.human_handoff_commit:
            raise WorkflowContractError(
                "repository history migration old_human_handoff_commit does not match Issue state"
            )
        return

    if event_type is WorkflowEventType.TASK_CONTRACT_MIGRATED:
        if state.state is WorkflowState.COMPLETE:
            raise WorkflowContractError("complete workflow state cannot migrate task contract")
        if to_state is not WorkflowState.AGENT_READY or actor_type is not WorkflowActor.AGENT:
            raise WorkflowContractError("task contract migration must return the Issue to agent_ready")
        old_hash = _sha(
            details.get("old_task_contract_sha256"),
            field="old_task_contract_sha256",
            sha256=True,
        )
        new_hash = _sha(
            details.get("new_task_contract_sha256"),
            field="new_task_contract_sha256",
            sha256=True,
        )
        if old_hash != state.task_contract_sha256 or new_hash == old_hash:
            raise WorkflowContractError("task contract migration hash identities are invalid")
        for key in ("branch", "checkout_path"):
            _string(details.get(key), field=key)
        for key in ("head_commit", "human_handoff_commit"):
            _sha(details.get(key), field=key)
        if details.get("human_result") not in (None, "pass", "fail"):
            raise WorkflowContractError("task contract migration human_result is invalid")
        return

    allowed = {
        (WorkflowState.AGENT_READY, WorkflowEventType.AGENT_LEASE_ACQUIRED): (
            WorkflowState.AGENT_WORKING,
            WorkflowActor.AGENT,
        ),
        (WorkflowState.AGENT_WORKING, WorkflowEventType.HUMAN_HANDOFF_CREATED): (
            WorkflowState.HUMAN_ACTION_REQUIRED,
            WorkflowActor.AGENT,
        ),
        (WorkflowState.HUMAN_ACTION_REQUIRED, WorkflowEventType.HUMAN_VALIDATION_PASSED): (
            WorkflowState.AGENT_READY,
            WorkflowActor.HUMAN,
        ),
        (WorkflowState.HUMAN_ACTION_REQUIRED, WorkflowEventType.HUMAN_VALIDATION_FAILED): (
            WorkflowState.AGENT_READY,
            WorkflowActor.HUMAN,
        ),
        (WorkflowState.AGENT_WORKING, WorkflowEventType.AGENT_LEASE_RELEASED): (
            WorkflowState.AGENT_READY,
            WorkflowActor.AGENT,
        ),
        (WorkflowState.AGENT_WORKING, WorkflowEventType.BLOCKED): (
            WorkflowState.BLOCKED,
            WorkflowActor.AGENT,
        ),
        (WorkflowState.HUMAN_ACTION_REQUIRED, WorkflowEventType.BLOCKED): (
            WorkflowState.BLOCKED,
            WorkflowActor.HUMAN,
        ),
        (WorkflowState.BLOCKED, WorkflowEventType.UNBLOCKED): (
            WorkflowState.AGENT_READY,
            WorkflowActor.HUMAN,
        ),
        (WorkflowState.AGENT_WORKING, WorkflowEventType.COMPLETED): (
            WorkflowState.COMPLETE,
            WorkflowActor.AGENT,
        ),
        (
            WorkflowState.AGENT_WORKING,
            WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED,
        ): (
            WorkflowState.HUMAN_ACTION_REQUIRED,
            WorkflowActor.AGENT,
        ),
        (
            WorkflowState.HUMAN_ACTION_REQUIRED,
            WorkflowEventType.DECOMPOSITION_APPLICATION_APPROVED,
        ): (
            WorkflowState.AGENT_READY,
            WorkflowActor.HUMAN,
        ),
        (
            WorkflowState.HUMAN_ACTION_REQUIRED,
            WorkflowEventType.DECOMPOSITION_APPLICATION_REJECTED,
        ): (
            WorkflowState.AGENT_READY,
            WorkflowActor.HUMAN,
        ),
    }
    expected = allowed.get((state.state, event_type))
    if expected is None:
        raise WorkflowContractError(
            f"event {event_type.value} is not valid from {state.state.value}"
        )
    if to_state is not expected[0] or actor_type is not expected[1]:
        raise WorkflowContractError("transition target state or actor is invalid")
    if event_type is WorkflowEventType.AGENT_LEASE_ACQUIRED:
        _string(details.get("worker_id"), field="lease worker_id")
        _sha(details.get("lease_id"), field="lease_id", sha256=True)
    if event_type is WorkflowEventType.HUMAN_HANDOFF_CREATED:
        for key in ("branch", "checkout_path"):
            _string(details.get(key), field=key)
        _sha(details.get("head_commit"), field="head_commit")
        if to_phase is not WorkflowPhase.UNITY_RUNTIME_VALIDATION:
            raise WorkflowContractError("human handoff must enter unity_runtime_validation")
    if event_type is WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED:
        for key in ("branch", "checkout_path", "decomposition_run_id", "artifact_root"):
            _string(details.get(key), field=key)
        _sha(details.get("head_commit"), field="head_commit")
        plan_id = _string(details.get("graph_delta_plan_id"), field="graph_delta_plan_id")
        if re.fullmatch(r"GDP-[0-9a-f]{64}", plan_id or "") is None:
            raise WorkflowContractError("graph_delta_plan_id has an invalid identity")
        if to_phase is not WorkflowPhase.DECOMPOSITION_APPLY_AUTHORIZATION:
            raise WorkflowContractError(
                "decomposition handoff must enter decomposition_apply_authorization"
            )
    if event_type in (
        WorkflowEventType.HUMAN_VALIDATION_PASSED,
        WorkflowEventType.HUMAN_VALIDATION_FAILED,
    ):
        tested_commit = _sha(details.get("tested_commit"), field="tested_commit")
        if tested_commit != state.human_handoff_commit:
            raise WorkflowContractError(
                "human result tested_commit does not match handoff commit"
            )
        expected_phase = (
            WorkflowPhase.DELIVERY_EVIDENCE
            if event_type is WorkflowEventType.HUMAN_VALIDATION_PASSED
            else WorkflowPhase.REPAIR
        )
        if to_phase is not expected_phase:
            raise WorkflowContractError("human result selected the wrong next phase")
    if event_type in (
        WorkflowEventType.DECOMPOSITION_APPLICATION_APPROVED,
        WorkflowEventType.DECOMPOSITION_APPLICATION_REJECTED,
    ):
        plan_id = _string(details.get("reviewed_plan_id"), field="reviewed_plan_id")
        if re.fullmatch(r"GDP-[0-9a-f]{64}", plan_id or "") is None:
            raise WorkflowContractError("reviewed_plan_id has an invalid identity")
        expected_phase = (
            WorkflowPhase.DECOMPOSITION_APPLY
            if event_type is WorkflowEventType.DECOMPOSITION_APPLICATION_APPROVED
            else WorkflowPhase.DECOMPOSITION
        )
        if to_phase is not expected_phase:
            raise WorkflowContractError(
                "decomposition application result selected an invalid next phase"
            )


def render_state_block(state: IssueWorkflowState) -> str:
    return f"<!-- {STATE_MARKER}\n{json.dumps(state.to_dict(), indent=2, sort_keys=True)}\n-->"


def render_dashboard(state: IssueWorkflowState, *, next_action: str | None = None) -> str:
    lines = [
        DASHBOARD_BEGIN,
        "## Workflow status",
        "",
        f"- **Current state:** `{state.state.value}`",
        f"- **Current owner:** `{state.current_actor.value}`",
        f"- **Phase:** `{state.phase.value}`",
    ]
    if state.branch:
        lines.append(f"- **Branch:** `{state.branch}`")
    if state.head_commit:
        lines.append(f"- **Commit:** `{state.head_commit}`")
    if state.checkout_path:
        lines.append(f"- **Checkout:** `{state.checkout_path}`")
    if next_action:
        lines.extend(("", "### Next action", "", next_action.strip()))
    lines.extend((DASHBOARD_END, "", render_state_block(state)))
    return "\n".join(lines)


def update_issue_body(
    body: str,
    state: IssueWorkflowState,
    *,
    next_action: str | None = None,
) -> str:
    body = body or ""
    body = STATE_RE.sub("", body)
    start = body.find(DASHBOARD_BEGIN)
    end = body.find(DASHBOARD_END)
    if start >= 0 and end >= start:
        end += len(DASHBOARD_END)
        body = (body[:start] + body[end:]).strip()
    managed = render_dashboard(state, next_action=next_action)
    return managed + ("\n\n" + body.strip() if body.strip() else "") + "\n"


def parse_state(body: str) -> IssueWorkflowState | None:
    matches = STATE_RE.findall(body or "")
    if not matches:
        return None
    if len(matches) != 1:
        raise WorkflowContractError("issue body contains multiple workflow state blocks")
    try:
        value = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise WorkflowContractError("workflow state block is not valid JSON") from exc
    return IssueWorkflowState.from_dict(value)


def render_event_comment(event: IssueWorkflowEvent, summary: str) -> str:
    return (
        f"## Workflow event: {event.event_type.value}\n\n"
        f"{summary.strip()}\n\n"
        f"<!-- {EVENT_MARKER}\n"
        f"{json.dumps(event.to_dict(), indent=2, sort_keys=True)}\n"
        "-->"
    )


MAX_IGNORED_COMMENT_DIAGNOSTICS = 10


def parse_events(
    comments: Iterable[Any],
    *,
    ignored_diagnostics: list[str] | None = None,
) -> tuple[IssueWorkflowEvent, ...]:
    """Parse workflow events, trusting only authorized event-comment authors.

    The repository is public: any account can post a comment containing an
    ``nsc-workflow-event`` block. A comment whose author is missing or is not
    on the committed actor allow-list carries NO workflow authority: its
    event-shaped content is ignored entirely for event-chain construction, so
    an outside commenter can neither inject an event nor invalidate an
    otherwise valid authorized chain. Each ignored comment is reported (up to
    a bound) through ``ignored_diagnostics`` as non-authoritative visibility.

    An AUTHORIZED comment with a malformed event block still fails closed —
    the trusted history itself requires repair.
    """

    policy = default_actor_policy()
    events: list[IssueWorkflowEvent] = []
    ignored: list[str] = []
    for index, item in enumerate(comments):
        body = item.get("body") if isinstance(item, Mapping) else item
        if type(body) is not str:
            continue
        matches = EVENT_RE.findall(body)
        if not matches:
            continue
        login = actor_login(item)
        if login is None:
            ignored.append(
                f"ignored event-shaped {_comment_reference(item, index)}: it has no "
                "author identity and carries no workflow authority"
            )
            continue
        if not policy.is_authorized_actor(login):
            ignored.append(
                f"ignored event-shaped {_comment_reference(item, index)} by "
                f"unauthorized login {login!r}: it carries no workflow authority"
            )
            continue
        if len(matches) > 1:
            raise WorkflowContractError("one issue comment contains multiple workflow events")
        try:
            value = json.loads(matches[0])
        except json.JSONDecodeError as exc:
            raise WorkflowContractError("workflow event block is not valid JSON") from exc
        events.append(IssueWorkflowEvent.from_dict(value))
    if ignored_diagnostics is not None and ignored:
        ignored_diagnostics.extend(ignored[:MAX_IGNORED_COMMENT_DIAGNOSTICS])
        if len(ignored) > MAX_IGNORED_COMMENT_DIAGNOSTICS:
            ignored_diagnostics.append(
                f"...and {len(ignored) - MAX_IGNORED_COMMENT_DIAGNOSTICS} more "
                "ignored authority-shaped comments"
            )
    return tuple(events)


def validate_event_chain(
    state: IssueWorkflowState,
    events: Iterable[IssueWorkflowEvent],
) -> tuple[IssueWorkflowEvent, ...]:
    ordered = sorted(events, key=lambda event: event.sequence)
    if len({event.sequence for event in ordered}) != len(ordered):
        raise WorkflowContractError("workflow event history contains duplicate sequences")
    if len({event.event_id for event in ordered}) != len(ordered):
        raise WorkflowContractError("workflow event history contains duplicate event IDs")
    previous: IssueWorkflowEvent | None = None
    expected_contract_sha256 = (
        ordered[0].task_contract_sha256 if ordered else state.task_contract_sha256
    )
    expected_history_head: str | None = None
    expected_history_handoff: str | None = None
    for index, event in enumerate(ordered, start=1):
        if event.task_id != state.task_id:
            raise WorkflowContractError("workflow event task does not match issue state")
        if event.task_contract_sha256 != expected_contract_sha256:
            raise WorkflowContractError("workflow event contract hash changed without a migration event")
        if event.sequence != index:
            raise WorkflowContractError("workflow event sequences are not contiguous")
        expected_previous = previous.event_id if previous else None
        if event.previous_event_id != expected_previous:
            raise WorkflowContractError("workflow event previous_event_id chain is broken")
        if previous is not None:
            if event.from_state is not previous.to_state:
                raise WorkflowContractError("workflow state chain is broken")
            if event.from_phase is not previous.to_phase:
                raise WorkflowContractError("workflow phase chain is broken")
        if event.event_type is WorkflowEventType.TASK_CONTRACT_MIGRATED:
            old_hash = event.details.get("old_task_contract_sha256")
            new_hash = event.details.get("new_task_contract_sha256")
            if old_hash != expected_contract_sha256:
                raise WorkflowContractError("task contract migration old hash is not current")
            _sha(new_hash, field="new_task_contract_sha256", sha256=True)
            if new_hash == old_hash:
                raise WorkflowContractError("task contract migration did not change identity")
            expected_contract_sha256 = new_hash
        if event.event_type is WorkflowEventType.REPOSITORY_HISTORY_MIGRATED:
            if (
                event.from_state is not WorkflowState.COMPLETE
                or event.to_state is not WorkflowState.COMPLETE
                or event.from_phase is not WorkflowPhase.MERGE_CLOSEOUT
                or event.to_phase is not WorkflowPhase.MERGE_CLOSEOUT
                or event.actor_type is not WorkflowActor.HUMAN
            ):
                raise WorkflowContractError(
                    "repository history migration event has an invalid state, phase, or actor"
                )
            parsed = _history_migration_details(event.details)
            if expected_history_head is not None and parsed["old_head_commit"] != expected_history_head:
                raise WorkflowContractError(
                    "repository history migration head chain is broken"
                )
            if (
                expected_history_handoff is not None
                and parsed["old_human_handoff_commit"] != expected_history_handoff
            ):
                raise WorkflowContractError(
                    "repository history migration human-handoff chain is broken"
                )
            expected_history_head = parsed["new_head_commit"]
            expected_history_handoff = parsed["new_human_handoff_commit"]
        previous = event
    if expected_contract_sha256 != state.task_contract_sha256:
        raise WorkflowContractError("Issue state does not use the final migrated contract hash")
    if state.state_version != len(ordered):
        raise WorkflowContractError("state_version does not match workflow event count")
    if not ordered:
        if state.last_event_id is not None:
            raise WorkflowContractError("empty event chain cannot have last_event_id")
        return ()
    last = ordered[-1]
    if state.last_event_id != last.event_id:
        raise WorkflowContractError("issue state does not point to the final workflow event")
    if state.state is not last.to_state or state.phase is not last.to_phase:
        raise WorkflowContractError("issue state does not match final workflow event")
    if last.event_type is WorkflowEventType.REPOSITORY_HISTORY_MIGRATED:
        parsed = _history_migration_details(last.details)
        if state.head_commit != parsed["new_head_commit"]:
            raise WorkflowContractError(
                "Issue state head_commit does not match final repository history migration"
            )
        if state.human_handoff_commit != parsed["new_human_handoff_commit"]:
            raise WorkflowContractError(
                "Issue state human_handoff_commit does not match final repository history migration"
            )
    return tuple(ordered)


def labels_for_state(state: WorkflowState | str, existing: Iterable[str] = ()) -> list[str]:
    state_value = WorkflowState(state).value
    retained = [label for label in existing if label not in ALL_STATE_LABELS]
    return sorted({*retained, STATE_LABELS[state_value]})


def issue_is_agent_ready(body: str, labels: Iterable[str], comments: Iterable[Any]) -> bool:
    state = parse_state(body)
    if state is None:
        return False
    validate_event_chain(state, parse_events(comments))
    return (
        state.state is WorkflowState.AGENT_READY
        and STATE_LABELS[WorkflowState.AGENT_READY.value] in set(labels)
    )
