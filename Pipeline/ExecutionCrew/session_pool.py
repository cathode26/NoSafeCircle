"""Role-scoped, resumable provider-session pool for reusable ExecutionCrew workers.

Pooling here means a resumable provider conversation, never a live process. This
module starts nothing, waits on nothing, and terminates nothing: it only records
which conversations exist, which assignment currently owns one, and which are no
longer safe to reuse. Every worker process lifetime stays owned by whoever
launched it.

Four ideas carry the design.

Role isolation. `contract_locality_auditor`, `implementer`, `test_author`, and
`validator` keep entirely separate pools. A conversation is offered back only for
the exact role that created it, so an Implementer's memory can never become a
Validator's context.

Stable-only compatibility. A session is reusable only when provider, exact model,
reasoning effort, role, capability class, repository identity, and protocol
version all match. Task ID, source commit, checkout, allowed paths, and the
assignment itself are deliberately excluded: they are refreshed on every
assignment and are never continuing authority. Anything uncertain starts fresh.

Explicit checkout and check-in. Checking out makes a session invisible to every
other assignment. Checking in requires the exact lease, task, worker run, role,
provider, and the provider-confirmed session identity, plus a durable result that
says the deterministic changed-path check accepted the work. A process exit code
proves nothing here.

Fail closed into quarantine. Anything unproven -- missing or malformed session
identity, transport failure, uncertain timeout, mismatched lease fields, missing
durable result, rejected changed paths, corrupt state, or an unknown protocol --
quarantines the conversation instead of recycling it. Quarantine and expiry only
stop the pool selecting a session; they never delete provider history or
credentials, and they never touch a running worker.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from typing import Any, Callable, Iterable, Mapping

from Pipeline.AgentRuntime.provider_sessions import (
    ProviderSessionBinding,
    ProviderSessionConfirmation,
    ProviderSessionError,
    validate_session_id,
)


POOL_SCHEMA_VERSION = "1.0"
# Bumped whenever the crew/session interaction contract changes in a way that
# makes an older live conversation unsafe to continue. It is part of the
# compatibility key, so a version change starts fresh sessions instead of
# resuming conversations that learned an older contract.
CREW_SESSION_PROTOCOL_VERSION = "1.0"

# One hour of idle reusability after a successful check-in. A session at exactly
# this age is already expired; reusability is the half-open window [0, 3600).
IDLE_SESSION_LIFETIME_SECONDS = 3600.0
DEFAULT_MAX_CONCURRENT_ASSIGNMENTS = 10

CREW_SESSION_ROLES = (
    "contract_locality_auditor",
    "implementer",
    "test_author",
    "validator",
)
CAPABILITY_CLASSES = frozenset({"low_cost", "standard", "high_reasoning"})
SESSION_STATES = frozenset({"idle", "active", "quarantined", "expired"})

# Codex names its own conversation and reports it in `thread.started`, so the
# pool cannot mint that identity in advance. Claude accepts `--session-id`, so
# the pool chooses it up front. Keeping this explicit means the pool never
# guesses which half of the contract applies.
_PROVIDER_ASSIGNS_SESSION_ID = frozenset({"openai-codex"})
_SUPPORTED_PROVIDERS = frozenset({"claude-code", "openai-codex"})

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*(?:-[a-z0-9_]+)*$")
_SLOT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class SessionPoolError(RuntimeError):
    """Raised when pool identity, compatibility, or lifecycle fails closed."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _utc_text(moment: dt.datetime) -> str:
    if type(moment) is not dt.datetime or moment.tzinfo is None:
        raise SessionPoolError("pool timestamps must be timezone-aware datetimes")
    return moment.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any, *, field: str) -> dt.datetime:
    if type(value) is not str or not value:
        raise SessionPoolError(f"{field} must be an ISO-8601 UTC timestamp")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise SessionPoolError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise SessionPoolError(f"{field} must carry an explicit UTC offset")
    return parsed.astimezone(dt.timezone.utc)


def _session_id(value: Any, *, field: str = "session_id") -> str:
    """Validate an exact provider session UUID, reported as a pool failure.

    The substrate's whole-value rule is reused verbatim; only the exception type
    is translated so every pool boundary fails closed with one error type.
    """

    try:
        return validate_session_id(value, field=field)
    except ProviderSessionError as exc:
        raise SessionPoolError(str(exc)) from exc


def _text(value: Any, *, field: str, pattern: re.Pattern[str] | None = None) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise SessionPoolError(f"{field} must be a non-empty unpadded string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise SessionPoolError(f"{field} has an unsupported form")
    return value


def _optional_text(value: Any, *, field: str) -> str | None:
    return None if value is None else _text(value, field=field)


def _count(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise SessionPoolError(f"{field} must be a non-negative integer")
    return value


def _expect_fields(value: Any, expected: set[str], *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SessionPoolError(f"{where} must be an object")
    unknown, missing = set(value) - expected, expected - set(value)
    if unknown:
        raise SessionPoolError(f"unsupported {where} fields: {sorted(unknown)}")
    if missing:
        raise SessionPoolError(f"missing {where} fields: {sorted(missing)}")
    return value


@dataclass(frozen=True)
class SessionCompatibility:
    """The stable identity a conversation must share to be reusable.

    Everything here survives an assignment. Task ID, source commit, checkout,
    and write paths are deliberately absent: they are refreshed per assignment
    and must never behave like continuing authority.
    """

    provider_identifier: str
    model: str
    reasoning_effort: str | None
    role: str
    capability_class: str
    repository_identity: str
    protocol_version: str = CREW_SESSION_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        provider = _text(self.provider_identifier, field="provider_identifier", pattern=_IDENTIFIER)
        if provider not in _SUPPORTED_PROVIDERS:
            raise SessionPoolError(f"unsupported pool provider: {provider}")
        role = _text(self.role, field="role", pattern=_IDENTIFIER)
        if role not in CREW_SESSION_ROLES:
            raise SessionPoolError(f"unsupported ExecutionCrew pool role: {role}")
        if self.capability_class not in CAPABILITY_CLASSES:
            raise SessionPoolError("capability_class is unsupported")
        object.__setattr__(self, "provider_identifier", provider)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "model", _text(self.model, field="model"))
        object.__setattr__(
            self, "reasoning_effort", _optional_text(self.reasoning_effort, field="reasoning_effort")
        )
        object.__setattr__(
            self, "repository_identity", _text(self.repository_identity, field="repository_identity")
        )
        object.__setattr__(
            self, "protocol_version", _text(self.protocol_version, field="protocol_version")
        )

    def key(self) -> str:
        """Return the exact stable-compatibility key the pool matches on."""

        return "\n".join(
            (
                POOL_SCHEMA_VERSION,
                self.protocol_version,
                self.provider_identifier,
                self.model,
                "" if self.reasoning_effort is None else self.reasoning_effort,
                self.role,
                self.capability_class,
                self.repository_identity,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_identifier": self.provider_identifier,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "role": self.role,
            "capability_class": self.capability_class,
            "repository_identity": self.repository_identity,
            "protocol_version": self.protocol_version,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SessionCompatibility":
        fields = {
            "provider_identifier", "model", "reasoning_effort", "role",
            "capability_class", "repository_identity", "protocol_version",
        }
        _expect_fields(value, fields, where="session compatibility")
        return cls(**{name: value[name] for name in fields})


@dataclass(frozen=True)
class AssignmentLease:
    """One exclusive checkout of a conversation for one exact assignment."""

    pool_schema_version: str
    lease_id: str
    record_id: str
    session_id: str | None
    mode: str
    provider_identifier: str
    model: str
    reasoning_effort: str | None
    role: str
    capability_class: str
    repository_identity: str
    protocol_version: str
    worker_slot_id: str
    task_id: str
    worker_run_id: str
    source_commit: str
    checkout_identity: str
    checked_out_at_utc: str
    prior_completed_assignment_count: int

    def __post_init__(self) -> None:
        if self.pool_schema_version != POOL_SCHEMA_VERSION:
            raise SessionPoolError("unsupported pool schema version")
        if self.mode not in {"start", "resume"}:
            raise SessionPoolError("lease mode must be exactly 'start' or 'resume'")
        _session_id(self.lease_id, field="lease_id")
        _session_id(self.record_id, field="record_id")
        if self.session_id is not None:
            _session_id(self.session_id)
        elif self.mode == "resume":
            raise SessionPoolError("a resume lease requires an exact session_id")
        _text(self.worker_slot_id, field="worker_slot_id", pattern=_SLOT)
        _text(self.task_id, field="task_id")
        _text(self.worker_run_id, field="worker_run_id", pattern=_SLOT)
        _text(self.source_commit, field="source_commit", pattern=_COMMIT)
        _text(self.checkout_identity, field="checkout_identity")
        _parse_utc(self.checked_out_at_utc, field="checked_out_at_utc")
        _count(self.prior_completed_assignment_count, field="prior_completed_assignment_count")
        # Re-validating through SessionCompatibility keeps one definition of the
        # stable identity rather than a second, drifting copy.
        self.compatibility()

    def compatibility(self) -> SessionCompatibility:
        return SessionCompatibility(
            self.provider_identifier, self.model, self.reasoning_effort, self.role,
            self.capability_class, self.repository_identity, self.protocol_version,
        )

    def session_binding(self) -> ProviderSessionBinding:
        """Return the provider-neutral binding this assignment must invoke with."""

        return ProviderSessionBinding(
            self.provider_identifier, self.role, self.mode, self.session_id
        )

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _LEASE_FIELDS}

    @classmethod
    def from_dict(cls, value: Any) -> "AssignmentLease":
        _expect_fields(value, set(_LEASE_FIELDS), where="assignment lease")
        return cls(**{name: value[name] for name in _LEASE_FIELDS})


_LEASE_FIELDS = tuple(AssignmentLease.__dataclass_fields__)


@dataclass(frozen=True)
class DurableAssignmentResult:
    """An authenticated durable role/crew result for one exact lease.

    The pool requires this instead of an exit code. ``changed_path_validation``
    is ExecutionCrew's deterministic incremental scope decision, which must have
    accepted the work before a conversation may be reused.
    """

    lease_id: str
    task_id: str
    worker_run_id: str
    role: str
    provider_identifier: str
    model: str
    status: str
    changed_path_validation: str
    confirmed_session: ProviderSessionConfirmation

    def __post_init__(self) -> None:
        _session_id(self.lease_id, field="lease_id")
        if self.status not in {"completed", "failed"}:
            raise SessionPoolError("durable result status must be 'completed' or 'failed'")
        if self.changed_path_validation not in {"accepted", "rejected"}:
            raise SessionPoolError(
                "changed_path_validation must be 'accepted' or 'rejected'"
            )
        if type(self.confirmed_session) is not ProviderSessionConfirmation:
            raise SessionPoolError(
                "durable result requires an exact ProviderSessionConfirmation"
            )
        _text(self.task_id, field="task_id")
        _text(self.worker_run_id, field="worker_run_id", pattern=_SLOT)
        _text(self.role, field="role", pattern=_IDENTIFIER)
        _text(self.provider_identifier, field="provider_identifier", pattern=_IDENTIFIER)
        _text(self.model, field="model")

    @property
    def is_reusable(self) -> bool:
        return self.status == "completed" and self.changed_path_validation == "accepted"


@dataclass(frozen=True)
class PooledSession:
    """One conversation the pool knows about, and its current availability."""

    record_id: str
    compatibility: SessionCompatibility
    state: str
    session_id: str | None = None
    completed_assignment_count: int = 0
    idle_since_utc: str | None = None
    active_lease: AssignmentLease | None = None
    quarantine_reason: str | None = None

    def __post_init__(self) -> None:
        _session_id(self.record_id, field="record_id")
        if self.state not in SESSION_STATES:
            raise SessionPoolError(f"unsupported session state: {self.state!r}")
        if self.session_id is not None:
            _session_id(self.session_id)
        _count(self.completed_assignment_count, field="completed_assignment_count")
        if self.state == "active":
            if type(self.active_lease) is not AssignmentLease:
                raise SessionPoolError("an active session requires its exact lease")
            if self.active_lease.record_id != self.record_id:
                raise SessionPoolError("active lease names a different session record")
            if self.idle_since_utc is not None:
                raise SessionPoolError("an active session cannot also be idle")
        elif self.active_lease is not None:
            raise SessionPoolError(f"a {self.state} session must not hold a lease")
        if self.state == "idle":
            if self.idle_since_utc is None:
                raise SessionPoolError("an idle session requires its idle-since timestamp")
            if self.session_id is None:
                raise SessionPoolError("an idle session requires a confirmed session identity")
            _parse_utc(self.idle_since_utc, field="idle_since_utc")
        elif self.state != "active" and self.idle_since_utc is not None:
            raise SessionPoolError(f"a {self.state} session must not be idle-timed")
        if (self.quarantine_reason is None) != (self.state != "quarantined"):
            raise SessionPoolError("quarantine_reason is required exactly when quarantined")

    def is_reusable_at(self, now: dt.datetime) -> bool:
        if self.state != "idle" or self.session_id is None:
            return False
        idle_for = (now - _parse_utc(self.idle_since_utc, field="idle_since_utc")).total_seconds()
        return 0 <= idle_for < IDLE_SESSION_LIFETIME_SECONDS

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "compatibility": self.compatibility.to_dict(),
            "state": self.state,
            "session_id": self.session_id,
            "completed_assignment_count": self.completed_assignment_count,
            "idle_since_utc": self.idle_since_utc,
            "active_lease": None if self.active_lease is None else self.active_lease.to_dict(),
            "quarantine_reason": self.quarantine_reason,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PooledSession":
        fields = {
            "record_id", "compatibility", "state", "session_id",
            "completed_assignment_count", "idle_since_utc", "active_lease",
            "quarantine_reason",
        }
        _expect_fields(value, fields, where="pooled session")
        lease = value["active_lease"]
        return cls(
            record_id=value["record_id"],
            compatibility=SessionCompatibility.from_dict(value["compatibility"]),
            state=value["state"],
            session_id=value["session_id"],
            completed_assignment_count=value["completed_assignment_count"],
            idle_since_utc=value["idle_since_utc"],
            active_lease=None if lease is None else AssignmentLease.from_dict(lease),
            quarantine_reason=value["quarantine_reason"],
        )


class SessionPool:
    """Role-scoped pool of resumable provider conversations.

    Sessions are created lazily: nothing is launched until an assignment asks
    for one and no compatible idle conversation exists.
    """

    def __init__(
        self,
        *,
        sessions: Iterable[PooledSession] = (),
        max_concurrent_assignments: int = DEFAULT_MAX_CONCURRENT_ASSIGNMENTS,
        clock: Callable[[], dt.datetime] = utc_now,
        identity_factory: Callable[[], str] | None = None,
    ) -> None:
        if (
            isinstance(max_concurrent_assignments, bool)
            or type(max_concurrent_assignments) is not int
            or max_concurrent_assignments < DEFAULT_MAX_CONCURRENT_ASSIGNMENTS
        ):
            raise SessionPoolError(
                "the pool must support at least "
                f"{DEFAULT_MAX_CONCURRENT_ASSIGNMENTS} concurrent assignments"
            )
        self.max_concurrent_assignments = max_concurrent_assignments
        self.clock = clock
        self.identity_factory = identity_factory or (lambda: str(uuid.uuid4()))
        self._sessions: dict[str, PooledSession] = {}
        for session in sessions:
            self._insert(session)
        self._validate_pool_state()

    # ------------------------------------------------------------- inspection

    @property
    def sessions(self) -> tuple[PooledSession, ...]:
        return tuple(self._sessions[key] for key in sorted(self._sessions))

    def sessions_for(self, state: str) -> tuple[PooledSession, ...]:
        return tuple(item for item in self.sessions if item.state == state)

    @property
    def active_assignment_count(self) -> int:
        return len(self.sessions_for("active"))

    def _insert(self, session: PooledSession) -> None:
        if type(session) is not PooledSession:
            raise SessionPoolError("pool accepts only exact PooledSession values")
        if session.record_id in self._sessions:
            raise SessionPoolError(f"duplicate session record {session.record_id}")
        self._sessions[session.record_id] = session

    def _validate_pool_state(self) -> None:
        """Reject impossible combinations before the pool is used at all."""

        session_ids: set[str] = set()
        lease_ids: set[str] = set()
        for session in self.sessions:
            if session.session_id is not None:
                if session.session_id in session_ids:
                    raise SessionPoolError(
                        f"duplicate provider session identity {session.session_id}"
                    )
                session_ids.add(session.session_id)
            lease = session.active_lease
            if lease is None:
                continue
            if lease.lease_id in lease_ids:
                raise SessionPoolError(f"duplicate active lease {lease.lease_id}")
            lease_ids.add(lease.lease_id)
            if lease.compatibility() != session.compatibility:
                raise SessionPoolError(
                    "active lease compatibility differs from its session"
                )
            if lease.session_id != session.session_id:
                raise SessionPoolError("active lease names a different session identity")
        if self.active_assignment_count > self.max_concurrent_assignments:
            raise SessionPoolError("pool holds more active leases than its capacity")

    # --------------------------------------------------------------- checkout

    def checkout(
        self,
        *,
        compatibility: SessionCompatibility,
        worker_slot_id: str,
        task_id: str,
        worker_run_id: str,
        source_commit: str,
        checkout_identity: str,
        now: dt.datetime | None = None,
    ) -> AssignmentLease:
        """Reserve one conversation for one assignment, creating one if needed.

        A compatible idle session is resumed; otherwise a fresh session is
        requested. An active or quarantined conversation is never taken, and a
        checked-out session becomes invisible to every other assignment.
        """

        if type(compatibility) is not SessionCompatibility:
            raise SessionPoolError("checkout requires an exact SessionCompatibility")
        moment = self.clock() if now is None else now
        _utc_text(moment)
        if self.active_assignment_count >= self.max_concurrent_assignments:
            raise SessionPoolError(
                "pool capacity is fully committed to active assignments"
            )
        self.expire_idle(now=moment)
        reusable = [
            session
            for session in self.sessions
            if session.compatibility == compatibility and session.is_reusable_at(moment)
        ]
        # Warmest first, with a deterministic tie-break so a restored pool always
        # selects the same conversation.
        reusable.sort(key=lambda item: (item.idle_since_utc or "", item.record_id))
        session = reusable[-1] if reusable else None
        if session is None:
            # Lazily request a brand-new conversation. Claude accepts a
            # pool-chosen `--session-id`, so the record identity is also the
            # session identity; Codex names its own thread, so the identity
            # stays unknown until the transcript confirms it at check-in.
            record_id = self._new_identity("record")
            if record_id in self._sessions:
                raise SessionPoolError(f"duplicate session record {record_id}")
            assigns_own = compatibility.provider_identifier in _PROVIDER_ASSIGNS_SESSION_ID
            mode, session_id = "start", (None if assigns_own else record_id)
            prior, session_compatibility = 0, compatibility
        else:
            record_id = session.record_id
            mode, session_id = "resume", session.session_id
            prior, session_compatibility = (
                session.completed_assignment_count,
                session.compatibility,
            )
        lease = AssignmentLease(
            pool_schema_version=POOL_SCHEMA_VERSION,
            lease_id=self._new_identity("lease"),
            record_id=record_id,
            session_id=session_id,
            mode=mode,
            provider_identifier=compatibility.provider_identifier,
            model=compatibility.model,
            reasoning_effort=compatibility.reasoning_effort,
            role=compatibility.role,
            capability_class=compatibility.capability_class,
            repository_identity=compatibility.repository_identity,
            protocol_version=compatibility.protocol_version,
            worker_slot_id=worker_slot_id,
            task_id=task_id,
            worker_run_id=worker_run_id,
            source_commit=source_commit,
            checkout_identity=checkout_identity,
            checked_out_at_utc=_utc_text(moment),
            prior_completed_assignment_count=prior,
        )
        self._sessions[record_id] = PooledSession(
            record_id=record_id,
            compatibility=session_compatibility,
            state="active",
            session_id=session_id,
            completed_assignment_count=prior,
            active_lease=lease,
        )
        self._validate_pool_state()
        return lease

    def _new_identity(self, what: str) -> str:
        value = self.identity_factory()
        try:
            return _session_id(value, field=f"{what} identity")
        except ProviderSessionError as exc:
            raise SessionPoolError(str(exc)) from exc

    # --------------------------------------------------------------- check-in

    def check_in(
        self,
        *,
        lease: AssignmentLease,
        result: DurableAssignmentResult,
        now: dt.datetime | None = None,
    ) -> PooledSession:
        """Return a conversation to the idle pool, or quarantine it.

        Every identity on the durable result must equal the lease. Anything
        stale, mismatched, unconfirmed, or rejected by the deterministic
        changed-path check quarantines instead of recycling.
        """

        session = self._leased_session(lease)
        if type(result) is not DurableAssignmentResult:
            return self._quarantine(session, "check-in supplied no durable assignment result")
        mismatches = [
            name
            for name, expected, actual in (
                ("lease_id", lease.lease_id, result.lease_id),
                ("task_id", lease.task_id, result.task_id),
                ("worker_run_id", lease.worker_run_id, result.worker_run_id),
                ("role", lease.role, result.role),
                ("provider_identifier", lease.provider_identifier, result.provider_identifier),
                ("model", lease.model, result.model),
            )
            if expected != actual
        ]
        confirmed = result.confirmed_session
        if confirmed.role != lease.role:
            mismatches.append("confirmed_session.role")
        if confirmed.provider_identifier != lease.provider_identifier:
            mismatches.append("confirmed_session.provider_identifier")
        if lease.session_id is not None and confirmed.session_id != lease.session_id:
            mismatches.append("confirmed_session.session_id")
        if confirmed.mode != lease.mode:
            mismatches.append("confirmed_session.mode")
        if mismatches:
            return self._quarantine(
                session, f"check-in did not match its lease: {sorted(set(mismatches))}"
            )
        if not result.is_reusable:
            return self._quarantine(
                session,
                f"assignment finished {result.status} with changed paths "
                f"{result.changed_path_validation}",
            )
        moment = self.clock() if now is None else now
        returned = PooledSession(
            record_id=session.record_id,
            compatibility=session.compatibility,
            state="idle",
            session_id=confirmed.session_id,
            completed_assignment_count=session.completed_assignment_count + 1,
            idle_since_utc=_utc_text(moment),
        )
        self._sessions[session.record_id] = returned
        self._validate_pool_state()
        return returned

    def quarantine(self, lease: AssignmentLease, reason: str) -> PooledSession:
        """Withdraw a conversation from reuse without touching its worker.

        Quarantine stops selection only. No process is signalled, no provider
        history is deleted, and no credential is revoked.
        """

        return self._quarantine(self._leased_session(lease), _text(reason, field="reason"))

    def _quarantine(self, session: PooledSession, reason: str) -> PooledSession:
        quarantined = PooledSession(
            record_id=session.record_id,
            compatibility=session.compatibility,
            state="quarantined",
            session_id=session.session_id,
            completed_assignment_count=session.completed_assignment_count,
            quarantine_reason=reason,
        )
        self._sessions[session.record_id] = quarantined
        self._validate_pool_state()
        return quarantined

    def _leased_session(self, lease: AssignmentLease) -> PooledSession:
        if type(lease) is not AssignmentLease:
            raise SessionPoolError("an exact AssignmentLease is required")
        session = self._sessions.get(lease.record_id)
        if session is None:
            raise SessionPoolError("lease names a session this pool does not hold")
        if session.state != "active" or session.active_lease is None:
            raise SessionPoolError("lease names a session that is not checked out")
        if session.active_lease != lease:
            raise SessionPoolError("lease is stale: the session holds a different lease")
        return session

    # -------------------------------------------------------------- lifetime

    def expire_idle(self, *, now: dt.datetime | None = None) -> tuple[PooledSession, ...]:
        """Expire idle conversations older than the idle lifetime.

        Only ``idle`` sessions are considered. An active session is never
        expired or stolen however long its worker has been running, and expiry
        never deletes provider history or credentials.
        """

        moment = self.clock() if now is None else now
        expired: list[PooledSession] = []
        for session in self.sessions:
            if session.state != "idle" or session.is_reusable_at(moment):
                continue
            replacement = PooledSession(
                record_id=session.record_id,
                compatibility=session.compatibility,
                state="expired",
                session_id=session.session_id,
                completed_assignment_count=session.completed_assignment_count,
            )
            self._sessions[session.record_id] = replacement
            expired.append(replacement)
        return tuple(expired)

    # ------------------------------------------------------------ durability

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": POOL_SCHEMA_VERSION,
            "protocol_version": CREW_SESSION_PROTOCOL_VERSION,
            "max_concurrent_assignments": self.max_concurrent_assignments,
            "sessions": [session.to_dict() for session in self.sessions],
        }

    @classmethod
    def from_dict(
        cls,
        value: Any,
        *,
        clock: Callable[[], dt.datetime] = utc_now,
        identity_factory: Callable[[], str] | None = None,
    ) -> "SessionPool":
        fields = {"schema_version", "protocol_version", "max_concurrent_assignments", "sessions"}
        _expect_fields(value, fields, where="session pool state")
        if value["schema_version"] != POOL_SCHEMA_VERSION:
            raise SessionPoolError("unsupported pool schema version")
        if value["protocol_version"] != CREW_SESSION_PROTOCOL_VERSION:
            raise SessionPoolError("unsupported crew/session protocol version")
        if not isinstance(value["sessions"], list):
            raise SessionPoolError("pool sessions must be an array")
        return cls(
            sessions=[PooledSession.from_dict(item) for item in value["sessions"]],
            max_concurrent_assignments=value["max_concurrent_assignments"],
            clock=clock,
            identity_factory=identity_factory,
        )


def _strict_json(text: str) -> Any:
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


class SessionPoolStore:
    """Atomic, caller-located durable pool state.

    The path is supplied by the caller and must live outside this repository:
    mutable scheduler state is not repository content. Writes go to a temporary
    file in the same directory, are flushed and fsynced, and are then replaced
    atomically, so a reader never observes a partial pool.
    """

    def __init__(self, path: Path | str) -> None:
        resolved = Path(path).expanduser().resolve()
        if resolved == _REPOSITORY_ROOT or resolved.is_relative_to(_REPOSITORY_ROOT):
            raise SessionPoolError(
                "pool state must be stored outside the repository working tree"
            )
        self.path = resolved

    def load(
        self,
        *,
        clock: Callable[[], dt.datetime] = utc_now,
        identity_factory: Callable[[], str] | None = None,
    ) -> SessionPool:
        if not self.path.exists():
            return SessionPool(clock=clock, identity_factory=identity_factory)
        if not self.path.is_file():
            raise SessionPoolError("pool state path is not a regular file")
        try:
            payload = _strict_json(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            raise SessionPoolError(
                f"durable pool state is unreadable or malformed: {type(exc).__name__}"
            ) from exc
        return SessionPool.from_dict(payload, clock=clock, identity_factory=identity_factory)

    def save(self, pool: SessionPool) -> Path:
        if type(pool) is not SessionPool:
            raise SessionPoolError("only an exact SessionPool may be persisted")
        text = json.dumps(pool.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        return self.path


def assignment_capsule(
    lease: AssignmentLease,
    *,
    checkout_root: str,
    capabilities: Iterable[str],
    allowed_paths: Iterable[str],
    denied_paths: Iterable[str],
    evidence_obligations: Iterable[str],
) -> str:
    """Return the explicit new-assignment authority capsule for a reused session.

    Remembered context must never widen current authority, so the capsule closes
    the previous assignment, revokes every authorization it carried, and then
    restates the complete current authority this assignment actually has.
    """

    if type(lease) is not AssignmentLease:
        raise SessionPoolError("an exact AssignmentLease is required")
    allowed = tuple(allowed_paths) or ("(none)",)
    denied = tuple(denied_paths) or ("(none)",)
    obligations = tuple(evidence_obligations) or ("(none stated)",)
    granted = tuple(capabilities) or ("(none)",)
    lines = [
        "New assignment capsule.",
        "",
        f"The preceding assignment in this conversation is complete "
        f"({lease.prior_completed_assignment_count} completed before this one).",
        "Every task and every write authorization from every previous assignment "
        "has expired and no longer applies. Earlier instructions are recall only; "
        "they grant no authority now and must not be acted on.",
        "",
        f"Current role: {lease.role}",
        f"Current task: {lease.task_id}",
        f"Current source commit: {lease.source_commit}",
        f"Current repository/checkout root: {checkout_root}",
        f"Current capabilities: {', '.join(granted)}",
        "Current allowed write paths:",
        *(f"- {path}" for path in allowed),
        "Current denied write paths:",
        *(f"- {path}" for path in denied),
        "Denied paths override allowed paths.",
        "Current test and evidence obligations:",
        *(f"- {item}" for item in obligations),
        "",
        "Only this assignment may be acted on. A path that was writable in an "
        "earlier assignment is not writable now unless it is listed above. Your "
        "provider tool restrictions still apply, and ExecutionCrew still validates "
        "the exact changed paths this assignment produces.",
    ]
    return "\n".join(lines)


__all__ = [
    "CAPABILITY_CLASSES",
    "CREW_SESSION_PROTOCOL_VERSION",
    "CREW_SESSION_ROLES",
    "DEFAULT_MAX_CONCURRENT_ASSIGNMENTS",
    "IDLE_SESSION_LIFETIME_SECONDS",
    "POOL_SCHEMA_VERSION",
    "AssignmentLease",
    "DurableAssignmentResult",
    "PooledSession",
    "SessionCompatibility",
    "SessionPool",
    "SessionPoolError",
    "SessionPoolStore",
    "assignment_capsule",
    "utc_now",
]
