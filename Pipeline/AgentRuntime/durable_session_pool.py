"""Provider-neutral durable records for resumable provider conversations.

This module is the durable-state counterpart of two contracts that already
exist here and that it deliberately reuses rather than restates:

* :mod:`provider_sessions` names one conversation and proves it from a
  transcript (`ProviderSessionBinding` / `ProviderSessionConfirmation`);
* :mod:`session_lifecycle` decides every budget, failure-streak, context, and
  retirement question (`start_assignment` / `finish_assignment` / ...).

What this module adds is the record between those two: which conversations a
pool knows about, which exact assignment currently owns one, and which are no
longer safe to reuse. It is the same state machine `Pipeline/ExecutionCrew/
session_pool.py` applies to crew roles -- idle, active, probation, quarantined,
expired, retired -- generalized so that other owners (a task supervisor, a
decomposition author, a decomposition reviewer) can pool conversations without
inventing a weaker protocol. The ExecutionCrew pool remains the authority for
crew roles and is not changed by this module.

The rules are the ones every pool owner in this repository already obeys.

Adopt on confirm. A provider that names its own thread (Codex) has no trusted
identity before its first call. A cold lease therefore carries no session ID,
and the record adopts exactly the UUID the provider transcript proved, only at
check-in, only when that proof matches the lease. A pre-bound conversation
keeps the identity the pool chose. An exit code, a caller assertion, or an
unparseable transcript proves nothing and quarantines.

Stable-only compatibility. A conversation is offered back only to an
assignment whose :class:`SessionScope` is exactly equal: protocol, provider,
role, session class, workload class, model, reasoning effort, repository,
the fingerprint of the exact resume control the provider needs, and whatever
extra exact bindings the owner chose to make part of identity (a task ID for
a task-bound owner; nothing for a repository-wide one). Per-assignment facts
travel on the lease and in the authority capsule instead, never in the key.

Explicit boundaries. Checkout makes a record invisible to every other
assignment. Check-in requires the exact lease and a settlement whose confirmed
identity matches it. Uncertainty -- a timeout, a transport failure, a missing
or contradictory identity -- never resumes: it retires or quarantines. A
settlement replayed with identical content is a no-op; a different replay for
the same lease fails closed. An active assignment is never expired, stolen, or
retired by age: only the owner that proves the assignment is stranded may
retire it, and it does so as an interruption, never as a resume.

Bounded lifetime. Assignment budgets, failure streaks, and context retirement
come from the committed lifecycle policy. Age and idle expiry come from an
explicit :class:`SessionLifetimePolicy` the owner states. Nothing here is
immortal, and nothing here contacts a provider, starts a process, or deletes
provider history.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from typing import Any, Callable, Iterable, Mapping

from .provider_sessions import (
    PROVIDER_SESSION_SCHEMA_VERSION,
    ProviderSessionBinding,
    ProviderSessionConfirmation,
    ProviderSessionError,
    validate_session_id,
)
from .session_lifecycle import (
    ASSIGNMENT_OUTCOMES,
    WORKLOAD_CLASSES,
    SessionLifecycleError,
    SessionLifecycleState,
    SessionLifecycleTelemetry,
    cancel_assignment,
    finish_assignment,
    observe_between_assignments,
    retire_interrupted_assignment,
    start_assignment,
)


DURABLE_SESSION_POOL_SCHEMA_VERSION = "1.0"
SESSION_STATES = frozenset(
    {"idle", "active", "probation", "quarantined", "expired", "retired"}
)
_TIMED_STATES = frozenset({"idle", "probation"})
SETTLEMENT_OUTCOMES = frozenset(
    (ASSIGNMENT_OUTCOMES - {"idle", "waiting"}) | {"uncertain"}
)
FAILED_SETTLEMENT_OUTCOMES = frozenset(SETTLEMENT_OUTCOMES - {"completed"})
DEFAULT_MAX_CONCURRENT_ASSIGNMENTS = 10
_SUPPORTED_PROVIDERS = frozenset({"claude-code", "openai-codex"})
# Codex names its own thread and reports it in `thread.started`, so the pool
# cannot mint that identity in advance. Claude accepts a pool-chosen
# `--session-id`, so the identity is known at checkout.
_PROVIDER_ASSIGNS_SESSION_ID = frozenset({"openai-codex"})
# Codex cannot reproduce its start-time sandbox policy on `exec resume` without
# an operator-verified argument (see the adapter's CODEX_RESUME_SANDBOX_BLOCKER).
# A conversation that could never be resumed must never be pooled, so a scope
# for such a provider must carry the fingerprint of that exact verified control.
_PROVIDER_REQUIRES_RESUME_CONTROL = frozenset({"openai-codex"})

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*(?:-[a-z0-9_]+)*$")
_BINDING_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class DurableSessionPoolError(RuntimeError):
    """Raised when pool identity, compatibility, evidence, or lifetime fails closed."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_text(moment: dt.datetime) -> str:
    if type(moment) is not dt.datetime or moment.tzinfo is None:
        raise DurableSessionPoolError("pool timestamps must be timezone-aware datetimes")
    return moment.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any, *, field: str) -> dt.datetime:
    if type(value) is not str or not value:
        raise DurableSessionPoolError(f"{field} must be an ISO-8601 UTC timestamp")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise DurableSessionPoolError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise DurableSessionPoolError(f"{field} must carry an explicit UTC offset")
    return parsed.astimezone(dt.timezone.utc)


def _session_id(value: Any, *, field: str = "session_id") -> str:
    try:
        return validate_session_id(value, field=field)
    except ProviderSessionError as exc:
        raise DurableSessionPoolError(str(exc)) from exc


def _text(value: Any, *, field: str, pattern: re.Pattern[str] | None = None) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise DurableSessionPoolError(f"{field} must be a non-empty unpadded string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise DurableSessionPoolError(f"{field} must be valid UTF-8") from exc
    if pattern is not None and pattern.fullmatch(value) is None:
        raise DurableSessionPoolError(f"{field} has an unsupported form")
    return value


def _optional_text(value: Any, *, field: str) -> str | None:
    return None if value is None else _text(value, field=field)


def _count(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise DurableSessionPoolError(f"{field} must be a non-negative integer")
    return value


def _percent(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or type(value) is not int or not 0 <= value <= 100:
        raise DurableSessionPoolError(f"{field} must be an integer percentage in 0..100")
    return value


def _member(value: Any, allowed: Iterable[str], *, field: str) -> str:
    permitted = frozenset(allowed)
    if type(value) is not str or value not in permitted:
        raise DurableSessionPoolError(f"{field} must be one of {sorted(permitted)}")
    return value


def _pairs(value: Any, *, field: str) -> tuple[tuple[str, str], ...]:
    """Validate a sorted, unique tuple of exact ``(name, value)`` text pairs."""

    if isinstance(value, Mapping):
        items = tuple(value.items())
    elif isinstance(value, (list, tuple)):
        items = tuple(tuple(item) if isinstance(item, list) else item for item in value)
    else:
        raise DurableSessionPoolError(f"{field} must be a mapping or a sequence of pairs")
    result: list[tuple[str, str]] = []
    for item in items:
        if type(item) is not tuple or len(item) != 2:
            raise DurableSessionPoolError(f"{field} entries must be (name, value) pairs")
        name, text = item
        result.append(
            (_text(name, field=f"{field} name", pattern=_BINDING_NAME), _text(text, field=f"{field}[{name}]"))
        )
    names = [name for name, _ in result]
    if len(set(names)) != len(names):
        raise DurableSessionPoolError(f"{field} names must be unique")
    return tuple(sorted(result))


def _expect_fields(value: Any, expected: set[str], *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DurableSessionPoolError(f"{where} must be an object")
    unknown, missing = set(value) - expected, expected - set(value)
    if unknown:
        raise DurableSessionPoolError(f"unsupported {where} fields: {sorted(unknown)}")
    if missing:
        raise DurableSessionPoolError(f"missing {where} fields: {sorted(missing)}")
    return value


def resume_contract_fingerprint(argument: Iterable[str] | None) -> str | None:
    """Return the exact fingerprint of one resume-control argv fragment.

    ``None`` means the provider needs no extra control to resume. Anything else
    is hashed element-wise so that two fragments differing in any byte -- and a
    fragment supplied as one string versus two -- never share a fingerprint.
    """

    if argument is None:
        return None
    parts = tuple(argument)
    if not parts or any(type(part) is not str or not part for part in parts):
        raise DurableSessionPoolError(
            "a resume control must be a non-empty sequence of non-empty strings"
        )
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return digest.hexdigest()


@dataclass(frozen=True)
class SessionScope:
    """The exact stable identity a conversation must share to be reusable.

    Everything here survives an assignment. Per-assignment facts (run, turn,
    round, source commit, artifact hashes) belong on the lease and in the
    authority capsule and are deliberately absent from the key, unless an
    owner chooses to bind one through ``bindings`` -- a task-bound supervisor
    binds its task ID here precisely so another task can never inherit it.
    """

    protocol_version: str
    provider_identifier: str
    role: str
    session_class: str
    workload_class: str
    model: str
    reasoning_effort: str | None
    repository_identity: str
    resume_contract: str | None = None
    bindings: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _text(self.protocol_version, field="protocol_version")
        provider = _text(
            self.provider_identifier, field="provider_identifier", pattern=_IDENTIFIER
        )
        if provider not in _SUPPORTED_PROVIDERS:
            raise DurableSessionPoolError(f"unsupported pool provider: {provider}")
        _text(self.role, field="role", pattern=_IDENTIFIER)
        session_class = _member(
            self.session_class, {"worker", "architect"}, field="session_class"
        )
        workload_class = _member(self.workload_class, WORKLOAD_CLASSES, field="workload_class")
        if (session_class == "architect") != (workload_class == "admission_cycle"):
            raise DurableSessionPoolError(
                "an architect session runs admission cycles and a worker session runs "
                "fast, standard, or deep assignments"
            )
        _text(self.model, field="model")
        _optional_text(self.reasoning_effort, field="reasoning_effort")
        _text(self.repository_identity, field="repository_identity")
        if self.resume_contract is not None:
            _text(self.resume_contract, field="resume_contract", pattern=_SHA256)
        if provider in _PROVIDER_REQUIRES_RESUME_CONTROL and self.resume_contract is None:
            raise DurableSessionPoolError(
                f"{provider} conversations cannot be pooled without a verified resume "
                "control: the adapter refuses to resume without one, so a pooled "
                "conversation would never be resumable"
            )
        object.__setattr__(self, "bindings", _pairs(self.bindings, field="bindings"))

    @property
    def provider_assigns_session_id(self) -> bool:
        return self.provider_identifier in _PROVIDER_ASSIGNS_SESSION_ID

    def key(self) -> str:
        return "\n".join(
            (
                DURABLE_SESSION_POOL_SCHEMA_VERSION,
                self.protocol_version,
                self.provider_identifier,
                self.role,
                self.session_class,
                self.workload_class,
                self.model,
                "" if self.reasoning_effort is None else self.reasoning_effort,
                self.repository_identity,
                "" if self.resume_contract is None else self.resume_contract,
                *(f"{name}={value}" for name, value in self.bindings),
            )
        )

    def key_sha256(self) -> str:
        return hashlib.sha256(self.key().encode("utf-8")).hexdigest()

    def binding(self, name: str) -> str | None:
        for key, value in self.bindings:
            if key == name:
                return value
        return None

    def to_dict(self) -> dict[str, Any]:
        value = {name: getattr(self, name) for name in _SCOPE_FIELDS}
        value["bindings"] = [list(pair) for pair in self.bindings]
        return value

    @classmethod
    def from_dict(cls, value: Any) -> "SessionScope":
        _expect_fields(value, set(_SCOPE_FIELDS), where="session scope")
        values = {name: value[name] for name in _SCOPE_FIELDS}
        return cls(**values)


_SCOPE_FIELDS = tuple(SessionScope.__dataclass_fields__)


@dataclass(frozen=True)
class SessionLease:
    """One exclusive checkout of a conversation for one exact assignment."""

    pool_schema_version: str
    lease_id: str
    record_id: str
    session_id: str | None
    mode: str
    scope: SessionScope
    assignment: tuple[tuple[str, str], ...]
    checked_out_at_utc: str
    prior_completed_assignment_count: int
    probation_retry: bool = False

    def __post_init__(self) -> None:
        if self.pool_schema_version != DURABLE_SESSION_POOL_SCHEMA_VERSION:
            raise DurableSessionPoolError("unsupported pool schema version")
        _session_id(self.lease_id, field="lease_id")
        _session_id(self.record_id, field="record_id")
        _member(self.mode, {"start", "resume"}, field="mode")
        if self.session_id is not None:
            _session_id(self.session_id)
        elif self.mode == "resume":
            raise DurableSessionPoolError("a resume lease requires an exact session_id")
        if type(self.scope) is not SessionScope:
            raise DurableSessionPoolError("a lease requires an exact SessionScope")
        if self.mode == "start" and self.session_id is not None and (
            self.scope.provider_assigns_session_id or self.session_id != self.record_id
        ):
            raise DurableSessionPoolError(
                "a start lease may pre-bind only the pool-chosen record identity, and "
                "only for a provider that accepts a caller-chosen session id"
            )
        if self.mode == "start" and self.session_id is None and not self.scope.provider_assigns_session_id:
            raise DurableSessionPoolError(
                "a start lease for a caller-named provider must carry its session id"
            )
        object.__setattr__(self, "assignment", _pairs(self.assignment, field="assignment"))
        parse_utc(self.checked_out_at_utc, field="checked_out_at_utc")
        _count(self.prior_completed_assignment_count, field="prior_completed_assignment_count")
        if type(self.probation_retry) is not bool:
            raise DurableSessionPoolError("probation_retry must be boolean")

    @property
    def assignment_id(self) -> str:
        """The lifecycle assignment identity, which is this exact lease."""

        return self.lease_id

    @property
    def is_resume(self) -> bool:
        return self.mode == "resume"

    def assignment_value(self, name: str) -> str | None:
        for key, value in self.assignment:
            if key == name:
                return value
        return None

    def binding(self) -> ProviderSessionBinding:
        return ProviderSessionBinding(
            self.scope.provider_identifier, self.scope.role, self.mode, self.session_id
        )

    def to_dict(self) -> dict[str, Any]:
        value = {name: getattr(self, name) for name in _LEASE_FIELDS}
        value["scope"] = self.scope.to_dict()
        value["assignment"] = [list(pair) for pair in self.assignment]
        return value

    @classmethod
    def from_dict(cls, value: Any) -> "SessionLease":
        _expect_fields(value, set(_LEASE_FIELDS), where="session lease")
        values = {name: value[name] for name in _LEASE_FIELDS}
        values["scope"] = SessionScope.from_dict(value["scope"])
        return cls(**values)


_LEASE_FIELDS = tuple(SessionLease.__dataclass_fields__)


def confirmation_from_dict(value: Any) -> ProviderSessionConfirmation:
    fields = {"provider_identifier", "role", "mode", "session_id"}
    _expect_fields(value, fields | {"schema_version"}, where="provider session confirmation")
    if value["schema_version"] != PROVIDER_SESSION_SCHEMA_VERSION:
        raise DurableSessionPoolError("unsupported provider session confirmation schema version")
    try:
        return ProviderSessionConfirmation(
            value["provider_identifier"], value["role"], value["mode"], value["session_id"]
        )
    except ProviderSessionError as exc:
        raise DurableSessionPoolError(str(exc)) from exc


@dataclass(frozen=True)
class AssignmentSettlement:
    """What one exact assignment durably proved when it ended.

    ``outcome`` uses the committed lifecycle vocabulary plus ``uncertain``, which
    is the honest word for a timeout, a transport failure, or a transcript that
    could not be read: the provider may or may not have received the turn, so
    the conversation is retired rather than resumed. ``confirmed_session`` is
    the identity the provider transcript proved, or ``None`` when it proved
    nothing; a process exit code never appears here at all. ``evidence`` carries
    the exact facts the owner bound (artifact hashes, round identities) and is
    journaled verbatim, never prompts or provider text.
    """

    pool_schema_version: str
    lease_id: str
    record_id: str
    outcome: str
    confirmed_session: ProviderSessionConfirmation | None
    known_context_window_percent: int | None
    evidence: tuple[tuple[str, str], ...]
    detail: str

    def __post_init__(self) -> None:
        if self.pool_schema_version != DURABLE_SESSION_POOL_SCHEMA_VERSION:
            raise DurableSessionPoolError("unsupported pool schema version")
        _session_id(self.lease_id, field="lease_id")
        _session_id(self.record_id, field="record_id")
        _member(self.outcome, SETTLEMENT_OUTCOMES, field="outcome")
        if self.confirmed_session is not None and type(self.confirmed_session) is not ProviderSessionConfirmation:
            raise DurableSessionPoolError(
                "confirmed_session must be an exact ProviderSessionConfirmation or None"
            )
        _percent(self.known_context_window_percent, field="known_context_window_percent")
        object.__setattr__(self, "evidence", _pairs(self.evidence, field="evidence"))
        if type(self.detail) is not str:
            raise DurableSessionPoolError("detail must be text")
        object.__setattr__(self, "detail", " ".join(self.detail.split())[:600])

    @property
    def is_reusable(self) -> bool:
        return self.outcome == "completed"

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        value = {name: getattr(self, name) for name in _SETTLEMENT_FIELDS}
        value["confirmed_session"] = (
            None if self.confirmed_session is None else self.confirmed_session.to_dict()
        )
        value["evidence"] = [list(pair) for pair in self.evidence]
        return value

    @classmethod
    def from_dict(cls, value: Any) -> "AssignmentSettlement":
        _expect_fields(value, set(_SETTLEMENT_FIELDS), where="assignment settlement")
        values = {name: value[name] for name in _SETTLEMENT_FIELDS}
        confirmed = value["confirmed_session"]
        values["confirmed_session"] = None if confirmed is None else confirmation_from_dict(confirmed)
        return cls(**values)


_SETTLEMENT_FIELDS = tuple(AssignmentSettlement.__dataclass_fields__)


@dataclass(frozen=True)
class SessionRecord:
    """One conversation the pool knows about, and its current availability."""

    record_id: str
    scope: SessionScope
    state: str
    created_at_utc: str
    session_id: str | None = None
    completed_assignment_count: int = 0
    idle_since_utc: str | None = None
    active_lease: SessionLease | None = None
    quarantine_reason: str | None = None
    probation_reason: str | None = None
    expiry_reason: str | None = None
    lifecycle: SessionLifecycleState | None = None

    def __post_init__(self) -> None:
        _session_id(self.record_id, field="record_id")
        if type(self.scope) is not SessionScope:
            raise DurableSessionPoolError("a record requires an exact SessionScope")
        if self.state not in SESSION_STATES:
            raise DurableSessionPoolError(f"unsupported session state: {self.state!r}")
        parse_utc(self.created_at_utc, field="created_at_utc")
        if self.session_id is not None:
            _session_id(self.session_id)
        _count(self.completed_assignment_count, field="completed_assignment_count")
        lifecycle = self.lifecycle
        if lifecycle is not None:
            if type(lifecycle) is not SessionLifecycleState:
                raise DurableSessionPoolError("lifecycle must be an exact SessionLifecycleState")
            if lifecycle.session_id != self.session_id:
                raise DurableSessionPoolError("lifecycle names a different conversation")
            if (
                lifecycle.role != self.scope.role
                or lifecycle.provider_identifier != self.scope.provider_identifier
                or lifecycle.session_class != self.scope.session_class
            ):
                raise DurableSessionPoolError("lifecycle identity differs from its session scope")
            if lifecycle.completed_assignments != self.completed_assignment_count:
                raise DurableSessionPoolError("lifecycle and pool assignment counts disagree")
        if self.state == "active":
            lease = self.active_lease
            if type(lease) is not SessionLease:
                raise DurableSessionPoolError("an active session requires its exact lease")
            if lease.record_id != self.record_id:
                raise DurableSessionPoolError("active lease names a different session record")
            if lease.scope != self.scope:
                raise DurableSessionPoolError("active lease scope differs from its session")
            if lease.session_id != self.session_id:
                raise DurableSessionPoolError("active lease names a different session identity")
            if self.idle_since_utc is not None:
                raise DurableSessionPoolError("an active session cannot also be idle")
            if lease.prior_completed_assignment_count != self.completed_assignment_count:
                raise DurableSessionPoolError(
                    "active lease prior assignment count differs from the conversation's history"
                )
            if lifecycle is None:
                # Only a cold start has no lifecycle: nothing has been
                # accounted because nothing has been proven yet, whether the
                # pool chose the identity (Claude) or the provider will name
                # it (Codex). A warm resume must carry its assigned lifecycle.
                if lease.mode != "start" or self.completed_assignment_count != 0:
                    raise DurableSessionPoolError(
                        "only a fresh start lease may hold no lifecycle state"
                    )
            else:
                if lifecycle.phase != "assigned":
                    raise DurableSessionPoolError("an active session requires an assigned lifecycle")
                if lifecycle.active_assignment_id != lease.assignment_id:
                    raise DurableSessionPoolError("lifecycle names a different active assignment")
                if lifecycle.active_workload_class != self.scope.workload_class:
                    raise DurableSessionPoolError(
                        "assigned lifecycle workload class differs from its session scope"
                    )
        elif self.active_lease is not None:
            raise DurableSessionPoolError(f"a {self.state} session must not hold a lease")
        elif lifecycle is not None and lifecycle.phase == "assigned":
            raise DurableSessionPoolError("only an active session may hold an assigned lifecycle")
        if self.state in _TIMED_STATES:
            if self.idle_since_utc is None:
                raise DurableSessionPoolError(f"a {self.state} session requires its idle-since timestamp")
            if self.session_id is None:
                raise DurableSessionPoolError(f"a {self.state} session requires a confirmed session identity")
            if lifecycle is None or lifecycle.phase != "between_assignments":
                raise DurableSessionPoolError(
                    f"a {self.state} session requires an available lifecycle between assignments"
                )
            expected_streak = 0 if self.state == "idle" else 1
            if lifecycle.consecutive_provider_output_failures != expected_streak:
                raise DurableSessionPoolError(
                    f"pool state {self.state!r} requires a counted failure streak of "
                    f"{expected_streak}, not {lifecycle.consecutive_provider_output_failures}"
                )
            parse_utc(self.idle_since_utc, field="idle_since_utc")
        elif self.state != "active" and self.idle_since_utc is not None:
            raise DurableSessionPoolError(f"a {self.state} session must not be idle-timed")
        retired_lifecycle = lifecycle is not None and lifecycle.phase == "retired"
        if self.state == "retired" and not retired_lifecycle:
            raise DurableSessionPoolError("a retired session requires its lifecycle retirement decision")
        if retired_lifecycle and self.state != "retired":
            raise DurableSessionPoolError(
                f"a lifecycle retired for {lifecycle.retirement_reason!r} must be recorded as "
                f"retired, not as {self.state!r}"
            )
        if (self.quarantine_reason is None) != (self.state != "quarantined"):
            raise DurableSessionPoolError("quarantine_reason is required exactly when quarantined")
        if (self.probation_reason is None) != (self.state != "probation"):
            raise DurableSessionPoolError("probation_reason is required exactly when on probation")
        if (self.expiry_reason is None) != (self.state != "expired"):
            raise DurableSessionPoolError("expiry_reason is required exactly when expired")

    @property
    def retirement_reason(self) -> str | None:
        return None if self.lifecycle is None else self.lifecycle.retirement_reason

    def age_seconds(self, now: dt.datetime) -> float:
        return (now - parse_utc(self.created_at_utc, field="created_at_utc")).total_seconds()

    def idle_seconds(self, now: dt.datetime) -> float | None:
        if self.idle_since_utc is None:
            return None
        return (now - parse_utc(self.idle_since_utc, field="idle_since_utc")).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "scope": self.scope.to_dict(),
            "state": self.state,
            "created_at_utc": self.created_at_utc,
            "session_id": self.session_id,
            "completed_assignment_count": self.completed_assignment_count,
            "idle_since_utc": self.idle_since_utc,
            "active_lease": None if self.active_lease is None else self.active_lease.to_dict(),
            "quarantine_reason": self.quarantine_reason,
            "probation_reason": self.probation_reason,
            "expiry_reason": self.expiry_reason,
            "lifecycle": None if self.lifecycle is None else self.lifecycle.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SessionRecord":
        fields = {
            "record_id", "scope", "state", "created_at_utc", "session_id",
            "completed_assignment_count", "idle_since_utc", "active_lease",
            "quarantine_reason", "probation_reason", "expiry_reason", "lifecycle",
        }
        _expect_fields(value, fields, where="session record")
        lifecycle = value["lifecycle"]
        if lifecycle is not None:
            try:
                lifecycle = SessionLifecycleState.from_dict(lifecycle)
            except SessionLifecycleError as exc:
                raise DurableSessionPoolError(str(exc)) from exc
        lease = value["active_lease"]
        return cls(
            record_id=value["record_id"],
            scope=SessionScope.from_dict(value["scope"]),
            state=value["state"],
            created_at_utc=value["created_at_utc"],
            session_id=value["session_id"],
            completed_assignment_count=value["completed_assignment_count"],
            idle_since_utc=value["idle_since_utc"],
            active_lease=None if lease is None else SessionLease.from_dict(lease),
            quarantine_reason=value["quarantine_reason"],
            probation_reason=value["probation_reason"],
            expiry_reason=value["expiry_reason"],
            lifecycle=lifecycle,
        )


@dataclass(frozen=True)
class SessionLifetimePolicy:
    """Explicit age and idle bounds an owner states for its conversations.

    ``max_age_seconds`` bounds a conversation from its creation, however busy
    it is between assignments, so nothing is immortal. ``idle_lifetime_seconds``
    bounds how long a returned conversation waits for its next assignment.
    Either may be ``None`` only when the other is not: an owner must state at
    least one bound. Neither ever applies to an active assignment.
    """

    max_age_seconds: float | None
    idle_lifetime_seconds: float | None

    def __post_init__(self) -> None:
        for name in ("max_age_seconds", "idle_lifetime_seconds"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or type(value) not in {int, float} or value <= 0:
                raise DurableSessionPoolError(f"{name} must be a positive number or None")
        if self.max_age_seconds is None and self.idle_lifetime_seconds is None:
            raise DurableSessionPoolError("a lifetime policy must state at least one bound")

    def expiry_reason(self, record: SessionRecord, now: dt.datetime) -> str | None:
        if record.state not in _TIMED_STATES:
            return None
        if self.max_age_seconds is not None and record.age_seconds(now) >= self.max_age_seconds:
            return "max_session_age"
        idle = record.idle_seconds(now)
        if idle is not None and (
            idle < 0
            or (self.idle_lifetime_seconds is not None and idle >= self.idle_lifetime_seconds)
        ):
            return "idle_lifetime"
        return None


class DurableSessionPool:
    """Records of resumable conversations, shared by owners of different roles.

    Sessions are created lazily: nothing is launched until an assignment asks
    for one and no compatible idle conversation exists. Every budget and
    retirement decision comes from the committed AgentRuntime lifecycle policy
    and is applied only at an assignment boundary.
    """

    def __init__(
        self,
        *,
        lifetime: SessionLifetimePolicy,
        sessions: Iterable[SessionRecord] = (),
        settlements: Mapping[str, str] | None = None,
        max_concurrent_assignments: int = DEFAULT_MAX_CONCURRENT_ASSIGNMENTS,
        clock: Callable[[], dt.datetime] = utc_now,
        identity_factory: Callable[[], str] | None = None,
        telemetry_sink: Callable[[SessionLifecycleTelemetry], None] | None = None,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if type(lifetime) is not SessionLifetimePolicy:
            raise DurableSessionPoolError("the pool requires an exact SessionLifetimePolicy")
        if (
            isinstance(max_concurrent_assignments, bool)
            or type(max_concurrent_assignments) is not int
            or max_concurrent_assignments < 1
        ):
            raise DurableSessionPoolError("max_concurrent_assignments must be a positive integer")
        self.lifetime = lifetime
        self.max_concurrent_assignments = max_concurrent_assignments
        self.clock = clock
        self.identity_factory = identity_factory or (lambda: str(uuid.uuid4()))
        self.telemetry_sink = telemetry_sink
        self.event_sink = event_sink
        self._sessions: dict[str, SessionRecord] = {}
        self._settlements: dict[str, str] = {}
        for session in sessions:
            self._insert(session)
        for lease_id, digest in (settlements or {}).items():
            self._settlements[_session_id(lease_id, field="settled lease id")] = _text(
                digest, field="settlement digest", pattern=_SHA256
            )
        self._validate_pool_state()

    # ------------------------------------------------------------- inspection

    @property
    def sessions(self) -> tuple[SessionRecord, ...]:
        return tuple(self._sessions[key] for key in sorted(self._sessions))

    def sessions_for(self, state: str) -> tuple[SessionRecord, ...]:
        return tuple(item for item in self.sessions if item.state == state)

    def session(self, record_id: str) -> SessionRecord | None:
        return self._sessions.get(_session_id(record_id, field="record_id"))

    def sessions_in_scope(self, scope: SessionScope) -> tuple[SessionRecord, ...]:
        return tuple(item for item in self.sessions if item.scope == scope)

    @property
    def active_assignment_count(self) -> int:
        return len(self.sessions_for("active"))

    def is_settled(self, lease_id: str) -> bool:
        return _session_id(lease_id, field="lease_id") in self._settlements

    def _insert(self, session: SessionRecord) -> None:
        if type(session) is not SessionRecord:
            raise DurableSessionPoolError("pool accepts only exact SessionRecord values")
        if session.record_id in self._sessions:
            raise DurableSessionPoolError(f"duplicate session record {session.record_id}")
        self._sessions[session.record_id] = session

    def _validate_pool_state(self) -> None:
        session_ids: set[str] = set()
        lease_ids: set[str] = set()
        for session in self.sessions:
            if session.session_id is not None:
                if session.session_id in session_ids:
                    raise DurableSessionPoolError(
                        f"duplicate provider session identity {session.session_id}"
                    )
                session_ids.add(session.session_id)
            lease = session.active_lease
            if lease is None:
                continue
            if lease.lease_id in lease_ids:
                raise DurableSessionPoolError(f"duplicate active lease {lease.lease_id}")
            if lease.lease_id in self._settlements:
                raise DurableSessionPoolError(
                    f"active lease {lease.lease_id} is already recorded as settled"
                )
            lease_ids.add(lease.lease_id)
        if self.active_assignment_count > self.max_concurrent_assignments:
            raise DurableSessionPoolError("pool holds more active leases than its capacity")

    def _emit(self, event: str, **fields: Any) -> None:
        if self.event_sink is None:
            return
        record = {"schema_version": DURABLE_SESSION_POOL_SCHEMA_VERSION, "event": event}
        record.update(fields)
        self.event_sink(record)

    def _emit_telemetry(self, telemetry: SessionLifecycleTelemetry) -> None:
        if self.telemetry_sink is not None:
            self.telemetry_sink(telemetry)

    def _new_identity(self, what: str) -> str:
        return _session_id(self.identity_factory(), field=f"{what} identity")

    def _moment(self, now: dt.datetime | None) -> dt.datetime:
        moment = self.clock() if now is None else now
        utc_text(moment)
        return moment

    # --------------------------------------------------------------- checkout

    def checkout(
        self,
        *,
        scope: SessionScope,
        assignment: Mapping[str, str] | Iterable[tuple[str, str]],
        now: dt.datetime | None = None,
        exclusive: bool = False,
        allow_probation_retry: bool = False,
    ) -> SessionLease:
        """Reserve one conversation for one assignment, creating one if needed.

        A compatible idle conversation is resumed unless the committed lifecycle
        policy refuses the next assignment, in which case it retires here and a
        fresh one is requested. ``exclusive`` refuses the checkout outright when
        any conversation in this exact scope is already active, which is how a
        task-bound owner keeps exactly one active lease per task. A probation
        conversation is offered only when the caller deliberately asks for the
        one controlled retry the committed policy allows.
        """

        if type(scope) is not SessionScope:
            raise DurableSessionPoolError("checkout requires an exact SessionScope")
        moment = self._moment(now)
        if self.active_assignment_count >= self.max_concurrent_assignments:
            raise DurableSessionPoolError("pool capacity is fully committed to active assignments")
        if exclusive and any(item.state == "active" for item in self.sessions_in_scope(scope)):
            raise DurableSessionPoolError(
                "this scope already holds an active lease; it must be checked in or "
                "reconciled by the authoritative owner before another checkout"
            )
        self.expire(now=moment)
        assignment_pairs = _pairs(assignment, field="assignment")
        lease_id = self._new_identity("lease")
        candidates = [
            item for item in self.sessions_in_scope(scope)
            if item.state == "idle" or (allow_probation_retry and item.state == "probation")
        ]
        # Warmest first, deterministic tie-break so a restored pool always
        # selects the same conversation.
        candidates.sort(key=lambda item: (item.state == "probation", item.idle_since_utc or "", item.record_id))
        selected: SessionRecord | None = None
        lifecycle: SessionLifecycleState | None = None
        for candidate in candidates:
            started = self._start(candidate, lease_id=lease_id)
            if started.phase != "assigned":
                self._sessions[candidate.record_id] = SessionRecord(
                    record_id=candidate.record_id,
                    scope=candidate.scope,
                    state="retired",
                    created_at_utc=candidate.created_at_utc,
                    session_id=candidate.session_id,
                    completed_assignment_count=candidate.completed_assignment_count,
                    lifecycle=started,
                )
                self._emit(
                    "retire", record_id=candidate.record_id, session_id=candidate.session_id,
                    reason=started.retirement_reason, at="checkout",
                )
                continue
            selected, lifecycle = candidate, started
            break
        if selected is None:
            record_id = self._new_identity("record")
            if record_id in self._sessions:
                raise DurableSessionPoolError(f"duplicate session record {record_id}")
            session_id = None if scope.provider_assigns_session_id else record_id
            mode, prior, created, probation = "start", 0, utc_text(moment), False
        else:
            record_id = selected.record_id
            session_id = selected.session_id
            mode, prior, created = "resume", selected.completed_assignment_count, selected.created_at_utc
            probation = selected.state == "probation"
        lease = SessionLease(
            pool_schema_version=DURABLE_SESSION_POOL_SCHEMA_VERSION,
            lease_id=lease_id,
            record_id=record_id,
            session_id=session_id,
            mode=mode,
            scope=scope,
            assignment=assignment_pairs,
            checked_out_at_utc=utc_text(moment),
            prior_completed_assignment_count=prior,
            probation_retry=probation,
        )
        self._sessions[record_id] = SessionRecord(
            record_id=record_id,
            scope=scope,
            state="active",
            created_at_utc=created,
            session_id=session_id,
            completed_assignment_count=prior,
            active_lease=lease,
            lifecycle=lifecycle,
        )
        self._validate_pool_state()
        self._emit(
            "cold_start" if mode == "start" else "resume",
            record_id=record_id, lease_id=lease_id, session_id=session_id, mode=mode,
            probation_retry=probation, prior_completed_assignment_count=prior,
            scope_sha256=scope.key_sha256(), assignment=dict(assignment_pairs),
        )
        return lease

    def _start(self, session: SessionRecord, *, lease_id: str) -> SessionLifecycleState:
        if session.lifecycle is None:
            raise DurableSessionPoolError("a reusable session must carry its lifecycle state")
        try:
            transition = start_assignment(
                session.lifecycle, assignment_id=lease_id,
                workload_class=session.scope.workload_class,
            )
        except SessionLifecycleError as exc:
            raise DurableSessionPoolError(str(exc)) from exc
        self._emit_telemetry(transition.telemetry)
        return transition.state

    # --------------------------------------------------------------- check-in

    def check_in(
        self,
        *,
        lease: SessionLease,
        settlement: AssignmentSettlement,
        now: dt.datetime | None = None,
    ) -> SessionRecord:
        """Return a conversation to the pool, or withdraw it, from durable proof.

        The settlement's confirmed identity must equal the lease: a resume must
        confirm exactly the UUID it named; a start of a pool-named conversation
        must confirm the pool's UUID; a start of a provider-named conversation
        adopts exactly the UUID it confirmed. A missing or contradictory
        identity never becomes one. Replaying an identical settlement is a
        no-op; a different settlement for an already-settled lease fails closed.
        """

        if type(lease) is not SessionLease:
            raise DurableSessionPoolError("an exact SessionLease is required")
        if type(settlement) is not AssignmentSettlement:
            raise DurableSessionPoolError("an exact AssignmentSettlement is required")
        if settlement.lease_id != lease.lease_id or settlement.record_id != lease.record_id:
            raise DurableSessionPoolError("settlement names a different lease or record")
        moment = self._moment(now)
        digest = settlement.digest()
        settled = self._settlements.get(lease.lease_id)
        if settled is not None:
            if settled != digest:
                raise DurableSessionPoolError(
                    f"lease {lease.lease_id} was already settled with different content"
                )
            record = self._sessions.get(lease.record_id)
            if record is None:
                raise DurableSessionPoolError("settled lease names a record the pool no longer holds")
            return record
        session = self._leased_session(lease)
        trusted_id = session.session_id
        confirmed = settlement.confirmed_session
        mismatch = self._confirmation_mismatch(lease, confirmed)
        if settlement.outcome == "uncertain":
            record = self._retire_uncertain(session, lease, settlement, session_id=trusted_id)
        elif mismatch is not None:
            record = self._withdraw(
                session, f"provider session identity was not proven: {mismatch}",
                outcome="identity_failure", settlement=settlement, session_id=trusted_id,
            )
        else:
            assert confirmed is not None
            proven_id = trusted_id or confirmed.session_id
            if any(
                other.record_id != session.record_id and other.session_id == proven_id
                for other in self.sessions
            ):
                record = self._withdraw(
                    session, "confirmed identity already belongs to another pooled conversation",
                    outcome="identity_failure", settlement=settlement, session_id=trusted_id,
                )
            elif settlement.is_reusable:
                lifecycle = self._finish(session, outcome="completed", settlement=settlement, session_id=proven_id)
                assert lifecycle is not None
                if lifecycle.phase == "retired":
                    record = SessionRecord(
                        record_id=session.record_id, scope=session.scope, state="retired",
                        created_at_utc=session.created_at_utc, session_id=lifecycle.session_id,
                        completed_assignment_count=lifecycle.completed_assignments,
                        lifecycle=lifecycle,
                    )
                else:
                    record = SessionRecord(
                        record_id=session.record_id, scope=session.scope, state="idle",
                        created_at_utc=session.created_at_utc, session_id=lifecycle.session_id,
                        completed_assignment_count=lifecycle.completed_assignments,
                        idle_since_utc=utc_text(moment), lifecycle=lifecycle,
                    )
                self._sessions[session.record_id] = record
            else:
                lifecycle = self._finish(
                    session, outcome=settlement.outcome, settlement=settlement, session_id=proven_id
                )
                if (
                    lifecycle is not None
                    and lifecycle.phase == "between_assignments"
                    and lifecycle.consecutive_provider_output_failures > 0
                ):
                    record = SessionRecord(
                        record_id=session.record_id, scope=session.scope, state="probation",
                        created_at_utc=session.created_at_utc, session_id=lifecycle.session_id,
                        completed_assignment_count=lifecycle.completed_assignments,
                        idle_since_utc=utc_text(moment),
                        probation_reason=f"assignment ended {settlement.outcome}: {settlement.detail}",
                        lifecycle=lifecycle,
                    )
                    self._sessions[session.record_id] = record
                else:
                    record = self._settle_failed(
                        session, f"assignment ended {settlement.outcome}: {settlement.detail}",
                        lifecycle=lifecycle, session_id=proven_id,
                    )
        self._settlements[lease.lease_id] = digest
        self._validate_pool_state()
        self._emit(
            "check_in", record_id=record.record_id, lease_id=lease.lease_id,
            session_id=record.session_id, outcome=settlement.outcome, state=record.state,
            retirement_reason=record.retirement_reason,
            quarantine_reason=record.quarantine_reason,
            probation_reason=record.probation_reason,
            completed_assignment_count=record.completed_assignment_count,
            known_context_window_percent=settlement.known_context_window_percent,
            evidence=dict(settlement.evidence), detail=settlement.detail,
        )
        return record

    @staticmethod
    def _confirmation_mismatch(
        lease: SessionLease, confirmed: ProviderSessionConfirmation | None
    ) -> str | None:
        if confirmed is None:
            return "no confirmed session identity"
        if confirmed.provider_identifier != lease.scope.provider_identifier:
            return "provider differs from the lease"
        if confirmed.role != lease.scope.role:
            return "role differs from the lease"
        if confirmed.mode != lease.mode:
            return "mode differs from the lease"
        if lease.session_id is not None and confirmed.session_id != lease.session_id:
            return "session id differs from the lease"
        return None

    def cancel(self, lease: SessionLease) -> SessionRecord | None:
        """Return an exact never-invoked lease without charging an assignment."""

        session = self._leased_session(lease)
        if session.lifecycle is None:
            del self._sessions[session.record_id]
            self._settlements[lease.lease_id] = hashlib.sha256(b"cancelled").hexdigest()
            self._validate_pool_state()
            self._emit("cancel", record_id=session.record_id, lease_id=lease.lease_id, discarded=True)
            return None
        try:
            transition = cancel_assignment(session.lifecycle, assignment_id=lease.assignment_id)
        except SessionLifecycleError as exc:
            raise DurableSessionPoolError(str(exc)) from exc
        self._emit_telemetry(transition.telemetry)
        state = "probation" if transition.state.consecutive_provider_output_failures else "idle"
        record = SessionRecord(
            record_id=session.record_id, scope=session.scope, state=state,
            created_at_utc=session.created_at_utc, session_id=session.session_id,
            completed_assignment_count=session.completed_assignment_count,
            idle_since_utc=lease.checked_out_at_utc,
            probation_reason=("uninvoked retry returned" if state == "probation" else None),
            lifecycle=transition.state,
        )
        self._sessions[session.record_id] = record
        self._settlements[lease.lease_id] = hashlib.sha256(b"cancelled").hexdigest()
        self._validate_pool_state()
        self._emit("cancel", record_id=session.record_id, lease_id=lease.lease_id, discarded=False)
        return record

    def retire_interrupted(self, lease: SessionLease, *, detail: str) -> SessionRecord:
        """Retire an active assignment whose owner is provably gone.

        Only the authoritative owner holding the exact pool lock may call this,
        and only after it has proven the assignment is stranded. The uncertain
        conversation is retired as interrupted, never resumed or contacted.
        """

        session = self._leased_session(lease)
        settlement = AssignmentSettlement(
            pool_schema_version=DURABLE_SESSION_POOL_SCHEMA_VERSION,
            lease_id=lease.lease_id, record_id=lease.record_id, outcome="uncertain",
            confirmed_session=None, known_context_window_percent=None, evidence=(),
            detail=f"interrupted assignment: {detail}",
        )
        record = self._retire_uncertain(session, lease, settlement, session_id=session.session_id)
        self._settlements[lease.lease_id] = settlement.digest()
        self._validate_pool_state()
        self._emit(
            "interrupted", record_id=record.record_id, lease_id=lease.lease_id,
            session_id=record.session_id, state=record.state, detail=settlement.detail,
        )
        return record

    def observe(
        self,
        record_id: str,
        *,
        observation: str,
        known_context_window_percent: int | None = None,
        now: dt.datetime | None = None,
    ) -> SessionRecord:
        """Record a zero-cost observation or an explicit between-assignment retirement."""

        session = self._sessions.get(_session_id(record_id, field="record_id"))
        if session is None:
            raise DurableSessionPoolError("pool does not hold this session record")
        if session.state == "active":
            raise DurableSessionPoolError(
                "an active assignment is never interrupted by a between-assignment observation"
            )
        if session.state not in _TIMED_STATES or session.lifecycle is None:
            raise DurableSessionPoolError("only an idle or probation session can be observed")
        try:
            transition = observe_between_assignments(
                session.lifecycle, observation=observation,
                known_context_window_percent=known_context_window_percent,
            )
        except SessionLifecycleError as exc:
            raise DurableSessionPoolError(str(exc)) from exc
        self._emit_telemetry(transition.telemetry)
        lifecycle = transition.state
        if lifecycle.phase == "retired":
            record = SessionRecord(
                record_id=session.record_id, scope=session.scope, state="retired",
                created_at_utc=session.created_at_utc, session_id=session.session_id,
                completed_assignment_count=lifecycle.completed_assignments, lifecycle=lifecycle,
            )
        else:
            record = SessionRecord(
                record_id=session.record_id, scope=session.scope, state=session.state,
                created_at_utc=session.created_at_utc, session_id=session.session_id,
                completed_assignment_count=lifecycle.completed_assignments,
                idle_since_utc=session.idle_since_utc,
                probation_reason=session.probation_reason, lifecycle=lifecycle,
            )
        self._sessions[session.record_id] = record
        self._validate_pool_state()
        self._emit(
            "observe", record_id=record.record_id, session_id=record.session_id,
            observation=observation, state=record.state, retirement_reason=record.retirement_reason,
        )
        return record

    def _withdraw(
        self,
        session: SessionRecord,
        reason: str,
        *,
        outcome: str,
        settlement: AssignmentSettlement | None,
        session_id: str | None,
    ) -> SessionRecord:
        lifecycle = self._finish(session, outcome=outcome, settlement=settlement, session_id=session_id)
        return self._settle_failed(session, reason, lifecycle=lifecycle, session_id=session_id)

    def _retire_uncertain(
        self,
        session: SessionRecord,
        lease: SessionLease,
        settlement: AssignmentSettlement,
        *,
        session_id: str | None,
    ) -> SessionRecord:
        """Retire a conversation whose provider outcome is unknowable."""

        lifecycle = session.lifecycle
        if lifecycle is None:
            # A cold provider-named conversation with no proven identity has
            # nothing to account against; it is withdrawn without an identity.
            return self._settle_failed(
                session, f"uncertain outcome: {settlement.detail}", lifecycle=None, session_id=None
            )
        try:
            transition = retire_interrupted_assignment(lifecycle, assignment_id=lease.assignment_id)
        except SessionLifecycleError as exc:
            raise DurableSessionPoolError(str(exc)) from exc
        self._emit_telemetry(transition.telemetry)
        return self._settle_failed(
            session, f"uncertain outcome: {settlement.detail}",
            lifecycle=transition.state, session_id=session_id,
        )

    def _settle_failed(
        self,
        session: SessionRecord,
        reason: str,
        *,
        lifecycle: SessionLifecycleState | None,
        session_id: str | None,
    ) -> SessionRecord:
        if lifecycle is not None and lifecycle.phase == "retired":
            settled = SessionRecord(
                record_id=session.record_id, scope=session.scope, state="retired",
                created_at_utc=session.created_at_utc, session_id=lifecycle.session_id,
                completed_assignment_count=lifecycle.completed_assignments, lifecycle=lifecycle,
            )
        else:
            settled = SessionRecord(
                record_id=session.record_id, scope=session.scope, state="quarantined",
                created_at_utc=session.created_at_utc,
                session_id=session_id if lifecycle is None else lifecycle.session_id,
                completed_assignment_count=(
                    session.completed_assignment_count if lifecycle is None
                    else lifecycle.completed_assignments
                ),
                quarantine_reason=" ".join(reason.split())[:600],
                lifecycle=lifecycle,
            )
        self._sessions[session.record_id] = settled
        return settled

    def _finish(
        self,
        session: SessionRecord,
        *,
        outcome: str,
        settlement: AssignmentSettlement | None,
        session_id: str | None,
    ) -> SessionLifecycleState | None:
        """Apply the committed end-of-assignment policy at this exact boundary.

        A provider-named conversation has no lifecycle until its identity is
        confirmed, so its first start and finish are applied together here,
        under the exact identity the caller proved.
        """

        lifecycle = session.lifecycle
        if lifecycle is None:
            if session.active_lease is None or session_id is None:
                return None
            try:
                created = SessionLifecycleState.create(
                    provider_identifier=session.scope.provider_identifier,
                    role=session.scope.role, session_id=session_id,
                    session_class=session.scope.session_class,
                )
                started = start_assignment(
                    created, assignment_id=session.active_lease.assignment_id,
                    workload_class=session.scope.workload_class,
                )
            except SessionLifecycleError as exc:
                raise DurableSessionPoolError(str(exc)) from exc
            self._emit_telemetry(started.telemetry)
            lifecycle = started.state
        if lifecycle.phase != "assigned":
            return lifecycle
        try:
            transition = finish_assignment(
                lifecycle, assignment_id=lifecycle.active_assignment_id or "", outcome=outcome,
                known_context_window_percent=(
                    None if settlement is None else settlement.known_context_window_percent
                ),
                latency_sample=None,
            )
        except SessionLifecycleError as exc:
            raise DurableSessionPoolError(str(exc)) from exc
        self._emit_telemetry(transition.telemetry)
        return transition.state

    def _leased_session(self, lease: SessionLease) -> SessionRecord:
        if type(lease) is not SessionLease:
            raise DurableSessionPoolError("an exact SessionLease is required")
        session = self._sessions.get(lease.record_id)
        if session is None:
            raise DurableSessionPoolError("lease names a session this pool does not hold")
        if session.state != "active" or session.active_lease is None:
            raise DurableSessionPoolError("lease names a session that is not checked out")
        if session.active_lease != lease:
            raise DurableSessionPoolError("lease is stale: the session holds a different lease")
        return session

    # -------------------------------------------------------------- lifetime

    def expire(self, *, now: dt.datetime | None = None) -> tuple[SessionRecord, ...]:
        """Expire returned conversations beyond the owner's age or idle bounds.

        Only ``idle`` and ``probation`` conversations are on the clock. An
        active assignment is never expired or stolen however long it runs.
        """

        moment = self._moment(now)
        expired: list[SessionRecord] = []
        for session in self.sessions:
            reason = self.lifetime.expiry_reason(session, moment)
            if reason is None:
                continue
            replacement = SessionRecord(
                record_id=session.record_id, scope=session.scope, state="expired",
                created_at_utc=session.created_at_utc, session_id=session.session_id,
                completed_assignment_count=session.completed_assignment_count,
                expiry_reason=reason, lifecycle=session.lifecycle,
            )
            self._sessions[session.record_id] = replacement
            expired.append(replacement)
            self._emit("expire", record_id=session.record_id, session_id=session.session_id, reason=reason)
        return tuple(expired)

    # ------------------------------------------------------------ durability

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DURABLE_SESSION_POOL_SCHEMA_VERSION,
            "lifetime": {
                "max_age_seconds": self.lifetime.max_age_seconds,
                "idle_lifetime_seconds": self.lifetime.idle_lifetime_seconds,
            },
            "max_concurrent_assignments": self.max_concurrent_assignments,
            "sessions": [session.to_dict() for session in self.sessions],
            "settlements": dict(sorted(self._settlements.items())),
        }

    @classmethod
    def from_dict(
        cls,
        value: Any,
        *,
        lifetime: SessionLifetimePolicy,
        clock: Callable[[], dt.datetime] = utc_now,
        identity_factory: Callable[[], str] | None = None,
        telemetry_sink: Callable[[SessionLifecycleTelemetry], None] | None = None,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> "DurableSessionPool":
        fields = {"schema_version", "lifetime", "max_concurrent_assignments", "sessions", "settlements"}
        _expect_fields(value, fields, where="session pool state")
        if value["schema_version"] != DURABLE_SESSION_POOL_SCHEMA_VERSION:
            raise DurableSessionPoolError("unsupported pool schema version")
        stored = _expect_fields(
            value["lifetime"], {"max_age_seconds", "idle_lifetime_seconds"}, where="pool lifetime"
        )
        if (
            stored["max_age_seconds"] != lifetime.max_age_seconds
            or stored["idle_lifetime_seconds"] != lifetime.idle_lifetime_seconds
        ):
            raise DurableSessionPoolError(
                "durable pool lifetime policy differs from this owner's committed policy"
            )
        if not isinstance(value["sessions"], list) or not isinstance(value["settlements"], Mapping):
            raise DurableSessionPoolError("pool sessions must be an array and settlements an object")
        return cls(
            lifetime=lifetime,
            sessions=[SessionRecord.from_dict(item) for item in value["sessions"]],
            settlements=value["settlements"],
            max_concurrent_assignments=value["max_concurrent_assignments"],
            clock=clock, identity_factory=identity_factory,
            telemetry_sink=telemetry_sink, event_sink=event_sink,
        )


def strict_json(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant: {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = item
        return result

    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=reject_duplicates)


class DurableSessionPoolStore:
    """Atomic, verified, caller-located durable pool state outside the repository."""

    def __init__(self, path: Path | str, *, lifetime: SessionLifetimePolicy) -> None:
        resolved = Path(path).expanduser().resolve()
        if resolved == _REPOSITORY_ROOT or resolved.is_relative_to(_REPOSITORY_ROOT):
            raise DurableSessionPoolError("pool state must be stored outside the repository working tree")
        if type(lifetime) is not SessionLifetimePolicy:
            raise DurableSessionPoolError("the store requires an exact SessionLifetimePolicy")
        self.path = resolved
        self.lifetime = lifetime

    def load(
        self,
        *,
        clock: Callable[[], dt.datetime] = utc_now,
        identity_factory: Callable[[], str] | None = None,
        telemetry_sink: Callable[[SessionLifecycleTelemetry], None] | None = None,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> DurableSessionPool:
        if not self.path.exists():
            return DurableSessionPool(
                lifetime=self.lifetime, clock=clock, identity_factory=identity_factory,
                telemetry_sink=telemetry_sink, event_sink=event_sink,
            )
        if not self.path.is_file():
            raise DurableSessionPoolError("pool state path is not a regular file")
        try:
            payload = strict_json(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            raise DurableSessionPoolError(
                f"durable pool state is unreadable or malformed: {type(exc).__name__}"
            ) from exc
        return DurableSessionPool.from_dict(
            payload, lifetime=self.lifetime, clock=clock, identity_factory=identity_factory,
            telemetry_sink=telemetry_sink, event_sink=event_sink,
        )

    def save(self, pool: DurableSessionPool) -> Path:
        if type(pool) is not DurableSessionPool:
            raise DurableSessionPoolError("only an exact DurableSessionPool may be persisted")
        payload = (json.dumps(pool.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            if self.path.read_bytes() != payload:
                raise DurableSessionPoolError(f"durable pool write could not be verified: {self.path}")
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        return self.path


def append_journal_line(path: Path, record: Mapping[str, Any]) -> None:
    """Append one fsynced JSON line; a failure here is reported, never hidden."""

    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def authority_capsule(
    *,
    role: str,
    mode: str,
    prior_completed_assignment_count: int,
    current: Mapping[str, str],
    allowed_actions: Iterable[str],
    capabilities: Iterable[str],
    obligations: Iterable[str] = (),
) -> str:
    """Return the explicit fresh-authority capsule for one pooled invocation.

    Remembered context must never widen current authority. On a resume the
    capsule closes and revokes every earlier assignment in the conversation;
    on a start it states that the conversation holds no prior authority. It
    then restates, exactly and completely, the facts and actions that apply to
    this invocation and declares everything else recall only.
    """

    _member(mode, {"start", "resume"}, field="mode")
    facts = _pairs(current, field="current")
    actions = tuple(allowed_actions) or ("(none)",)
    granted = tuple(capabilities) or ("(none)",)
    obliged = tuple(obligations)
    if mode == "resume":
        opening = [
            "New assignment capsule (resumed conversation).",
            "",
            f"The preceding assignment in this conversation is closed "
            f"({prior_completed_assignment_count} completed before this one). Every "
            "authorization it carried is revoked. Earlier prompts, observations, "
            "paths, plans, and conclusions in this conversation are context only: "
            "they grant no authority, describe no current state, and must not be "
            "acted on unless this invocation restates them.",
        ]
    else:
        opening = [
            "New assignment capsule (new conversation).",
            "",
            "This conversation holds no prior assignment and no prior authority.",
        ]
    lines = [
        *opening,
        "",
        f"Current role: {role}",
        *(f"Current {name.replace('_', ' ')}: {value}" for name, value in facts),
        f"Current capabilities: {', '.join(granted)}",
        "Current allowed actions:",
        *(f"- {item}" for item in actions),
    ]
    if obliged:
        lines.extend(["Current obligations:", *(f"- {item}" for item in obliged)])
    lines.extend(
        [
            "",
            "Only this assignment may be acted on. The deterministic state and allowed "
            "actions stated in this invocation are the only current state and the only "
            "current authority.",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "DEFAULT_MAX_CONCURRENT_ASSIGNMENTS",
    "DURABLE_SESSION_POOL_SCHEMA_VERSION",
    "FAILED_SETTLEMENT_OUTCOMES",
    "SESSION_STATES",
    "SETTLEMENT_OUTCOMES",
    "AssignmentSettlement",
    "DurableSessionPool",
    "DurableSessionPoolError",
    "DurableSessionPoolStore",
    "SessionLease",
    "SessionLifetimePolicy",
    "SessionRecord",
    "SessionScope",
    "append_journal_line",
    "authority_capsule",
    "confirmation_from_dict",
    "parse_utc",
    "resume_contract_fingerprint",
    "strict_json",
    "utc_now",
    "utc_text",
]
