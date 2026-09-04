"""Role-scoped, resumable provider-session pool for reusable ExecutionCrew workers.

Pooling here means a resumable provider conversation, never a live process. This
module starts nothing, waits on nothing, and terminates nothing: it only records
which conversations exist, which assignment currently owns one, and which are no
longer safe to reuse. Every worker process lifetime stays owned by whoever
launched it.

Five ideas carry the design.

Role isolation. `contract_locality_auditor`, `implementer`, `test_author`, and
`validator` keep entirely separate pools. A conversation is offered back only for
the exact role that created it, so an Implementer's memory can never become a
Validator's context.

Stable-only compatibility. A session is reusable only when provider, exact model,
reasoning effort, role, session class, capability class, repository identity, and
protocol version all match. Task ID, source commit, checkout, allowed paths, and
the assignment itself are deliberately excluded: they are refreshed on every
assignment and are never continuing authority. Anything uncertain starts fresh.

Explicit checkout and check-in. Checking out makes a session invisible to every
other assignment. Checking in requires the exact lease, task, worker run, crew
run, role, provider, routed model and reasoning effort, source commit, checkout
identity, repository identity, protocol version, and the provider-confirmed
session identity, plus a durable result whose persisted role artifact is present,
hash-exact, internally consistent with the deterministic changed-path and
semantic decisions it claims, and bound in its own bytes to this exact
assignment. A process exit code proves nothing here, and neither does a caller
assertion, a bare session ID, or another assignment's perfectly valid artifact.

Committed lifetime policy, applied once per boundary. Budgets, failure streaks,
context-window and latency retirement all come from
`Pipeline/AgentRuntime/session_lifecycle.py`; this module owns no second copy of
those numbers. Its transitions are applied only between assignments, so an active
assignment is never interrupted or retired. A proven provider/output failure that
the committed policy counted but did not retire leaves the conversation on
explicit probation: never advertised, never reusable, and offered again only by
one deliberate, exactly compatible retry through `offer_probation_retry`, whose
own result either resets the streak or lets the committed policy retire it.

Fail closed into quarantine. Anything unproven -- missing or malformed session
identity, transport failure, uncertain timeout, mismatched lease fields, missing
durable result, missing or tampered role evidence, evidence bound to another
assignment, rejected changed paths, rejected semantics, corrupt state, or an
unknown protocol -- quarantines the conversation instead of recycling it, and an
unproven provider confirmation never replaces the identity the lease or session
already established. Quarantine, probation, retirement, and expiry only stop the
pool selecting a session; they never delete provider history or credentials, and
they never touch a running worker.
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

from Pipeline.AgentRuntime.provider_sessions import (
    PROVIDER_SESSION_SCHEMA_VERSION,
    ProviderSessionBinding,
    ProviderSessionConfirmation,
    ProviderSessionError,
    validate_session_id,
)
from Pipeline.AgentRuntime.session_lifecycle import (
    ARCHITECT_COMPLETED_CYCLE_LIMIT,
    ASSIGNMENT_OUTCOMES,
    WORKER_WEIGHTED_UNIT_LIMIT,
    WORKER_WEIGHTS,
    LatencySample,
    SessionLifecycleError,
    SessionLifecycleState,
    finish_assignment,
    observe_between_assignments,
    start_assignment,
)


POOL_SCHEMA_VERSION = "1.0"
ROLE_EVIDENCE_SCHEMA_VERSION = "1.0"
# Bumped whenever the crew/session interaction contract changes in a way that
# makes an older live conversation unsafe to continue. It is part of the
# compatibility key, so a version change starts fresh sessions instead of
# resuming conversations that learned an older contract.
CREW_SESSION_PROTOCOL_VERSION = "1.0"
DURABLE_ASSIGNMENT_RESULT_SCHEMA_VERSION = "1.0"

# One hour of idle reusability after a successful check-in. A session at exactly
# this age is already expired; reusability is the half-open window [0, 3600).
IDLE_SESSION_LIFETIME_SECONDS = 3600.0
DEFAULT_MAX_CONCURRENT_ASSIGNMENTS = 10

# Every field the persisted role artifact must itself carry, so durable evidence
# can never be separated from the exact assignment that produced it. A perfectly
# valid artifact from another crew run, lease, task, checkout, or role disagrees
# here and fails closed instead of proving somebody else's work.
ROLE_EVIDENCE_FIELDS = (
    "schema_version",
    "pool_schema_version",
    "protocol_version",
    "crew_run_id",
    "lease_id",
    "record_id",
    "task_id",
    "worker_run_id",
    "worker_slot_id",
    "session_class",
    "role",
    "capability_class",
    "repository_identity",
    "source_commit",
    "checkout_identity",
    "provider_identifier",
    "model",
    "reasoning_effort",
    "confirmed_session",
    "status",
    "assignment_outcome",
    "semantic_validation",
    "changed_path_validation",
    "role_result_artifact",
)

CREW_SESSION_ROLES = (
    "contract_locality_auditor",
    "implementer",
    "test_author",
    "validator",
)
ARCHITECT_SESSION_ROLE = "architect"
CAPABILITY_CLASSES = frozenset({"low_cost", "standard", "high_reasoning"})
# The committed worker budget is expressed in weighted units per workload class,
# so a pooled capability class must map onto exactly one of those classes rather
# than inventing a parallel cost model here.
CAPABILITY_WORKLOAD_CLASSES = {
    "low_cost": "fast",
    "standard": "standard",
    "high_reasoning": "deep",
}
SESSION_STATES = frozenset(
    {"idle", "active", "probation", "quarantined", "expired", "retired"}
)
# States that hold a returned conversation on the idle clock. Only `idle` is ever
# advertised; `probation` is invisible to `checkout` and reachable exclusively
# through one deliberate `offer_probation_retry`.
_TIMED_STATES = frozenset({"idle", "probation"})
# Outcomes a finished assignment may report. `idle` and `waiting` are
# between-assignment observations and never describe a completed assignment.
ASSIGNMENT_RESULT_OUTCOMES = frozenset(ASSIGNMENT_OUTCOMES - {"idle", "waiting"})
FAILED_ASSIGNMENT_OUTCOMES = frozenset(ASSIGNMENT_RESULT_OUTCOMES - {"completed"})

# Codex names its own conversation and reports it in `thread.started`, so the
# pool cannot mint that identity in advance. Claude accepts `--session-id`, so
# the pool chooses it up front. Keeping this explicit means the pool never
# guesses which half of the contract applies.
_PROVIDER_ASSIGNS_SESSION_ID = frozenset({"openai-codex"})
_SUPPORTED_PROVIDERS = frozenset({"claude-code", "openai-codex"})

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*(?:-[a-z0-9_]+)*$")
_SLOT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# One conservative repository-relative artifact path. Absolute paths, Windows
# drive letters, backslashes, and any traversal segment are refused so durable
# evidence can only ever name a file inside the crew run directory.
_ARTIFACT_PATH = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class SessionPoolError(RuntimeError):
    """Raised when pool identity, compatibility, evidence, or lifetime fails closed."""


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


def _percent(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or type(value) is not int or not 0 <= value <= 100:
        raise SessionPoolError(f"{field} must be an integer percentage in 0..100")
    return value


def _member(value: Any, allowed: Iterable[str], *, field: str) -> str:
    permitted = frozenset(allowed)
    if type(value) is not str or value not in permitted:
        raise SessionPoolError(f"{field} must be one of {sorted(permitted)}")
    return value


def _protocol_version(value: Any, *, field: str = "protocol_version") -> str:
    """Refuse any protocol other than the one this crew/session contract states.

    An older or newer conversation protocol is not a compatibility miss to be
    routed around: it is a value this build cannot interpret, so it fails closed
    at construction and again at durable restoration.
    """

    text = _text(value, field=field)
    if text != CREW_SESSION_PROTOCOL_VERSION:
        raise SessionPoolError(
            f"unsupported crew/session protocol version {text!r}; "
            f"this build speaks exactly {CREW_SESSION_PROTOCOL_VERSION!r}"
        )
    return text


def _artifact_path(value: Any, *, field: str) -> str:
    text = _text(value, field=field, pattern=_ARTIFACT_PATH)
    if any(segment in {".", ".."} for segment in text.split("/")):
        raise SessionPoolError(f"{field} must not contain a traversal segment")
    return text


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
    session_class: str = "worker"

    def __post_init__(self) -> None:
        provider = _text(self.provider_identifier, field="provider_identifier", pattern=_IDENTIFIER)
        if provider not in _SUPPORTED_PROVIDERS:
            raise SessionPoolError(f"unsupported pool provider: {provider}")
        session_class = _member(
            self.session_class, {"worker", "architect"}, field="session_class"
        )
        role = _text(self.role, field="role", pattern=_IDENTIFIER)
        capability_class = _member(
            self.capability_class, CAPABILITY_CLASSES, field="capability_class"
        )
        if session_class == "worker":
            if role not in CREW_SESSION_ROLES:
                raise SessionPoolError(f"unsupported ExecutionCrew pool role: {role}")
        else:
            if role != ARCHITECT_SESSION_ROLE:
                raise SessionPoolError(
                    f"an architect session must use the {ARCHITECT_SESSION_ROLE!r} role"
                )
            if capability_class != "high_reasoning":
                raise SessionPoolError("an architect session is high_reasoning work")
        object.__setattr__(self, "provider_identifier", provider)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "session_class", session_class)
        object.__setattr__(self, "capability_class", capability_class)
        object.__setattr__(self, "model", _text(self.model, field="model"))
        object.__setattr__(
            self, "reasoning_effort", _optional_text(self.reasoning_effort, field="reasoning_effort")
        )
        object.__setattr__(
            self, "repository_identity", _text(self.repository_identity, field="repository_identity")
        )
        object.__setattr__(
            self, "protocol_version", _protocol_version(self.protocol_version)
        )

    @property
    def workload_class(self) -> str:
        """Return the committed lifecycle workload class this session consumes."""

        if self.session_class == "architect":
            return "admission_cycle"
        return CAPABILITY_WORKLOAD_CLASSES[self.capability_class]

    def key(self) -> str:
        """Return the exact stable-compatibility key the pool matches on."""

        return "\n".join(
            (
                POOL_SCHEMA_VERSION,
                self.protocol_version,
                self.provider_identifier,
                self.model,
                "" if self.reasoning_effort is None else self.reasoning_effort,
                self.session_class,
                self.role,
                self.capability_class,
                self.repository_identity,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _COMPATIBILITY_FIELDS}

    @classmethod
    def from_dict(cls, value: Any) -> "SessionCompatibility":
        _expect_fields(value, set(_COMPATIBILITY_FIELDS), where="session compatibility")
        return cls(**{name: value[name] for name in _COMPATIBILITY_FIELDS})


_COMPATIBILITY_FIELDS = tuple(SessionCompatibility.__dataclass_fields__)


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
    session_class: str
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
            self.session_class,
        )

    @property
    def assignment_id(self) -> str:
        """Return the lifecycle assignment identity, which is this exact lease."""

        return self.lease_id

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


def pooled_assignment_evidence(
    *,
    lease: AssignmentLease,
    confirmed: Any,
    crew_run_id: str,
    artifact: str,
    status: str,
    assignment_outcome: str,
    semantic_validation: str,
    changed_path_validation: str,
) -> dict[str, Any]:
    """Return the exact assignment binding one role artifact must carry in its bytes.

    The writer builds this block from the lease it actually ran on and persists
    it inside the role artifact, so the artifact and its assignment are one
    object. ``DurableAssignmentResult.evidence_reason`` rebuilds the same block
    from the trusted lease/result at check-in and requires an exact match, which
    is why a successful artifact borrowed from another run, lease, task, or
    source can never be presented as this assignment's evidence.
    """

    if type(lease) is not AssignmentLease:
        raise SessionPoolError("role evidence binding requires an exact AssignmentLease")
    if type(confirmed) is not ProviderSessionConfirmation:
        raise SessionPoolError(
            "role evidence binding requires an exact ProviderSessionConfirmation"
        )
    value = {
        "schema_version": ROLE_EVIDENCE_SCHEMA_VERSION,
        "pool_schema_version": lease.pool_schema_version,
        "protocol_version": lease.protocol_version,
        "crew_run_id": _text(crew_run_id, field="crew_run_id", pattern=_SLOT),
        "lease_id": lease.lease_id,
        "record_id": lease.record_id,
        "task_id": lease.task_id,
        "worker_run_id": lease.worker_run_id,
        "worker_slot_id": lease.worker_slot_id,
        "session_class": lease.session_class,
        "role": lease.role,
        "capability_class": lease.capability_class,
        "repository_identity": lease.repository_identity,
        "source_commit": lease.source_commit,
        "checkout_identity": lease.checkout_identity,
        "provider_identifier": lease.provider_identifier,
        "model": lease.model,
        "reasoning_effort": lease.reasoning_effort,
        "confirmed_session": confirmed.to_dict(),
        "status": _member(status, {"completed", "failed"}, field="status"),
        "assignment_outcome": _member(
            assignment_outcome, ASSIGNMENT_RESULT_OUTCOMES, field="assignment_outcome"
        ),
        "semantic_validation": _member(
            semantic_validation, {"accepted", "rejected"}, field="semantic_validation"
        ),
        "changed_path_validation": _member(
            changed_path_validation, {"accepted", "rejected"}, field="changed_path_validation"
        ),
        "role_result_artifact": _artifact_path(artifact, field="role_result_artifact"),
    }
    if tuple(value) != ROLE_EVIDENCE_FIELDS:
        raise SessionPoolError("role evidence binding fields drifted from the schema")
    return value


def _confirmation_from_dict(value: Any) -> ProviderSessionConfirmation:
    fields = {"provider_identifier", "role", "mode", "session_id"}
    _expect_fields(value, fields | {"schema_version"}, where="provider session confirmation")
    if value["schema_version"] != PROVIDER_SESSION_SCHEMA_VERSION:
        raise SessionPoolError("unsupported provider session confirmation schema version")
    try:
        return ProviderSessionConfirmation(
            value["provider_identifier"], value["role"], value["mode"], value["session_id"]
        )
    except ProviderSessionError as exc:
        raise SessionPoolError(str(exc)) from exc


def _latency_from_dict(value: Any) -> LatencySample | None:
    if value is None:
        return None
    fields = {"comparison_key", "duration_milliseconds", "baseline_milliseconds"}
    _expect_fields(value, fields, where="latency sample")
    try:
        return LatencySample(
            value["comparison_key"],
            value["duration_milliseconds"],
            value["baseline_milliseconds"],
        )
    except SessionLifecycleError as exc:
        raise SessionPoolError(str(exc)) from exc


@dataclass(frozen=True)
class DurableAssignmentResult:
    """Authenticated durable evidence that one exact lease produced one result.

    This is what a scheduler must present instead of a process exit code, a
    caller assertion, or a bare session ID. It repeats every identity the lease
    carried, names the exact persisted role artifact and its SHA-256, and states
    both the deterministic changed-path decision and the semantic decision that
    ExecutionCrew actually reached. ``assignment_outcome`` is the committed
    lifecycle vocabulary, so budget, failure-streak, context, and latency
    retirement are decided by the one policy module rather than re-derived here.
    """

    schema_version: str
    pool_schema_version: str
    protocol_version: str
    lease_id: str
    record_id: str
    crew_run_id: str
    task_id: str
    worker_run_id: str
    worker_slot_id: str
    session_class: str
    role: str
    capability_class: str
    provider_identifier: str
    model: str
    reasoning_effort: str | None
    repository_identity: str
    source_commit: str
    checkout_identity: str
    status: str
    assignment_outcome: str
    semantic_validation: str
    changed_path_validation: str
    role_result_artifact: str
    role_result_sha256: str
    known_context_window_percent: int | None
    latency_sample: LatencySample | None
    confirmed_session: ProviderSessionConfirmation

    def __post_init__(self) -> None:
        if self.schema_version != DURABLE_ASSIGNMENT_RESULT_SCHEMA_VERSION:
            raise SessionPoolError("unsupported durable assignment result schema version")
        if self.pool_schema_version != POOL_SCHEMA_VERSION:
            raise SessionPoolError("unsupported pool schema version")
        _protocol_version(self.protocol_version)
        _session_id(self.lease_id, field="lease_id")
        _session_id(self.record_id, field="record_id")
        _text(self.crew_run_id, field="crew_run_id", pattern=_SLOT)
        _text(self.task_id, field="task_id")
        _text(self.worker_run_id, field="worker_run_id", pattern=_SLOT)
        _text(self.worker_slot_id, field="worker_slot_id", pattern=_SLOT)
        _text(self.source_commit, field="source_commit", pattern=_COMMIT)
        _text(self.checkout_identity, field="checkout_identity")
        _member(self.status, {"completed", "failed"}, field="status")
        _member(
            self.assignment_outcome,
            ASSIGNMENT_RESULT_OUTCOMES,
            field="assignment_outcome",
        )
        _member(self.semantic_validation, {"accepted", "rejected"}, field="semantic_validation")
        _member(
            self.changed_path_validation,
            {"accepted", "rejected"},
            field="changed_path_validation",
        )
        _artifact_path(self.role_result_artifact, field="role_result_artifact")
        _text(self.role_result_sha256, field="role_result_sha256", pattern=_SHA256)
        _percent(self.known_context_window_percent, field="known_context_window_percent")
        if self.latency_sample is not None and type(self.latency_sample) is not LatencySample:
            raise SessionPoolError("latency_sample must be an exact LatencySample")
        if type(self.confirmed_session) is not ProviderSessionConfirmation:
            raise SessionPoolError(
                "durable result requires an exact ProviderSessionConfirmation"
            )
        # The stable identity is validated through the one definition again, so
        # a durable result can never claim a compatibility the pool would refuse.
        self.compatibility()
        proved = (
            self.status == "completed"
            and self.semantic_validation == "accepted"
            and self.changed_path_validation == "accepted"
        )
        if proved != (self.assignment_outcome == "completed"):
            raise SessionPoolError(
                "assignment_outcome must be 'completed' exactly when the role "
                "status and both validation decisions accepted the work"
            )

    def compatibility(self) -> SessionCompatibility:
        return SessionCompatibility(
            self.provider_identifier, self.model, self.reasoning_effort, self.role,
            self.capability_class, self.repository_identity, self.protocol_version,
            self.session_class,
        )

    @property
    def is_reusable(self) -> bool:
        return self.assignment_outcome == "completed"

    def lease_mismatches(self, lease: AssignmentLease) -> tuple[str, ...]:
        """Return every field where this evidence disagrees with its lease."""

        if type(lease) is not AssignmentLease:
            raise SessionPoolError("an exact AssignmentLease is required")
        pairs = (
            ("pool_schema_version", lease.pool_schema_version, self.pool_schema_version),
            ("protocol_version", lease.protocol_version, self.protocol_version),
            ("lease_id", lease.lease_id, self.lease_id),
            ("record_id", lease.record_id, self.record_id),
            ("crew_run_id", lease.worker_run_id, self.crew_run_id),
            ("task_id", lease.task_id, self.task_id),
            ("worker_run_id", lease.worker_run_id, self.worker_run_id),
            ("worker_slot_id", lease.worker_slot_id, self.worker_slot_id),
            ("session_class", lease.session_class, self.session_class),
            ("role", lease.role, self.role),
            ("capability_class", lease.capability_class, self.capability_class),
            ("provider_identifier", lease.provider_identifier, self.provider_identifier),
            ("model", lease.model, self.model),
            ("reasoning_effort", lease.reasoning_effort, self.reasoning_effort),
            ("repository_identity", lease.repository_identity, self.repository_identity),
            ("source_commit", lease.source_commit, self.source_commit),
            ("checkout_identity", lease.checkout_identity, self.checkout_identity),
        )
        mismatches = [name for name, expected, actual in pairs if expected != actual]
        confirmed = self.confirmed_session
        if confirmed.role != lease.role:
            mismatches.append("confirmed_session.role")
        if confirmed.provider_identifier != lease.provider_identifier:
            mismatches.append("confirmed_session.provider_identifier")
        if lease.session_id is not None and confirmed.session_id != lease.session_id:
            mismatches.append("confirmed_session.session_id")
        if confirmed.mode != lease.mode:
            mismatches.append("confirmed_session.mode")
        return tuple(sorted(set(mismatches)))

    def role_evidence_binding(self) -> dict[str, Any]:
        """Return the exact assignment binding this result's role artifact must carry.

        ``check_in`` proves every field of this result against the trusted lease
        before the artifact is read, so this block is the lease's identity in the
        artifact's own bytes rather than a second, weaker copy of it.
        """

        value: dict[str, Any] = {"schema_version": ROLE_EVIDENCE_SCHEMA_VERSION}
        for name in ROLE_EVIDENCE_FIELDS[1:]:
            value[name] = (
                self.confirmed_session.to_dict()
                if name == "confirmed_session"
                else getattr(self, name)
            )
        return value

    def evidence_reason(self, evidence_root: Any) -> str | None:
        """Return why the persisted role artifact fails to prove this result.

        ``None`` means the exact named artifact exists under the crew run
        directory, hashes to the recorded SHA-256, records the role, agent
        status, and deterministic scope decision this evidence claims, and binds
        itself to this exact assignment. A missing, tampered, contradictory, or
        borrowed artifact always produces a reason.
        """

        if evidence_root is None:
            return "no crew run directory was supplied to prove the role artifact"
        try:
            root = Path(evidence_root)
        except TypeError:
            return "crew run directory is not a usable path"
        artifact = root / self.role_result_artifact
        try:
            payload = artifact.read_bytes()
        except OSError:
            return f"role result artifact is missing or unreadable: {self.role_result_artifact}"
        if hashlib.sha256(payload).hexdigest() != self.role_result_sha256:
            return f"role result artifact does not match its recorded SHA-256: {self.role_result_artifact}"
        try:
            record = _strict_json(payload.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError):
            return f"role result artifact is not strict JSON: {self.role_result_artifact}"
        if not isinstance(record, Mapping):
            return f"role result artifact is not an object: {self.role_result_artifact}"
        if record.get("role") != self.role:
            return "role result artifact names a different role"
        agent_status = record.get("agent_status")
        if self.status == "completed" and agent_status != "succeeded":
            return f"role result artifact reports agent status {agent_status!r}"
        if self.status == "failed" and agent_status == "succeeded":
            return "role result artifact reports success for a failed assignment"
        if not isinstance(record.get("scope_check_reasons"), list):
            return "role result artifact has no deterministic scope decision"
        for field, claimed in (
            ("deterministic_changed_path_validation", self.changed_path_validation),
            ("semantic_validation", self.semantic_validation),
        ):
            if record.get(field) != claimed:
                return (
                    f"role result artifact {field}={record.get(field)!r} disagrees with "
                    f"the durable claim {claimed!r}"
                )
        binding = record.get("pooled_assignment_evidence")
        expected = self.role_evidence_binding()
        if not isinstance(binding, Mapping):
            return "role result artifact carries no pooled assignment binding"
        unknown = sorted(set(binding) - set(expected))
        if unknown:
            return f"role result artifact assignment binding has unsupported fields: {unknown}"
        missing = sorted(set(expected) - set(binding))
        if missing:
            return f"role result artifact assignment binding is missing fields: {missing}"
        differing = sorted(name for name in expected if binding[name] != expected[name])
        if differing:
            return (
                "role result artifact assignment binding disagrees with the durable "
                f"claim: {differing}"
            )
        return None

    def to_dict(self) -> dict[str, Any]:
        value = {name: getattr(self, name) for name in _DURABLE_FIELDS}
        value["latency_sample"] = (
            None if self.latency_sample is None else self.latency_sample.to_dict()
        )
        value["confirmed_session"] = self.confirmed_session.to_dict()
        return value

    @classmethod
    def from_dict(cls, value: Any) -> "DurableAssignmentResult":
        _expect_fields(value, set(_DURABLE_FIELDS), where="durable assignment result")
        values = {name: value[name] for name in _DURABLE_FIELDS}
        values["latency_sample"] = _latency_from_dict(value["latency_sample"])
        values["confirmed_session"] = _confirmation_from_dict(value["confirmed_session"])
        return cls(**values)


_DURABLE_FIELDS = tuple(DurableAssignmentResult.__dataclass_fields__)


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
    probation_reason: str | None = None
    lifecycle: SessionLifecycleState | None = None

    def __post_init__(self) -> None:
        _session_id(self.record_id, field="record_id")
        if self.state not in SESSION_STATES:
            raise SessionPoolError(f"unsupported session state: {self.state!r}")
        if self.session_id is not None:
            _session_id(self.session_id)
        _count(self.completed_assignment_count, field="completed_assignment_count")
        if self.lifecycle is not None:
            if type(self.lifecycle) is not SessionLifecycleState:
                raise SessionPoolError("lifecycle must be an exact SessionLifecycleState")
            if self.lifecycle.session_id != self.session_id:
                raise SessionPoolError("lifecycle names a different conversation")
            if (
                self.lifecycle.role != self.compatibility.role
                or self.lifecycle.provider_identifier != self.compatibility.provider_identifier
                or self.lifecycle.session_class != self.compatibility.session_class
            ):
                raise SessionPoolError("lifecycle identity differs from its session")
            if self.lifecycle.completed_assignments != self.completed_assignment_count:
                raise SessionPoolError("lifecycle and pool assignment counts disagree")
        if self.state == "active":
            if type(self.active_lease) is not AssignmentLease:
                raise SessionPoolError("an active session requires its exact lease")
            if self.active_lease.record_id != self.record_id:
                raise SessionPoolError("active lease names a different session record")
            if self.idle_since_utc is not None:
                raise SessionPoolError("an active session cannot also be idle")
            if self.active_lease.prior_completed_assignment_count != self.completed_assignment_count:
                raise SessionPoolError(
                    "active lease prior assignment count differs from the conversation's history"
                )
            if self.lifecycle is None:
                # A conversation has no lifecycle only before its very first
                # assignment is accounted, which is exactly the cold start of a
                # provider-named thread. A warm resume must still carry the
                # assigned lifecycle it was started with, so a restored payload
                # cannot drop that history and have it silently restart at zero.
                if self.active_lease.mode != "start" or self.completed_assignment_count != 0:
                    raise SessionPoolError(
                        "only a fresh start lease may hold no lifecycle state"
                    )
            else:
                if self.lifecycle.phase != "assigned":
                    raise SessionPoolError("an active session requires an assigned lifecycle")
                if self.lifecycle.active_workload_class != self.compatibility.workload_class:
                    raise SessionPoolError(
                        "assigned lifecycle workload class differs from its session compatibility"
                    )
        elif self.active_lease is not None:
            raise SessionPoolError(f"a {self.state} session must not hold a lease")
        elif self.lifecycle is not None and self.lifecycle.phase == "assigned":
            raise SessionPoolError("only an active session may hold an assigned lifecycle")
        if self.state in _TIMED_STATES:
            if self.idle_since_utc is None:
                raise SessionPoolError(f"a {self.state} session requires its idle-since timestamp")
            if self.session_id is None:
                raise SessionPoolError(
                    f"a {self.state} session requires a confirmed session identity"
                )
            if self.lifecycle is None or self.lifecycle.phase != "between_assignments":
                raise SessionPoolError(
                    f"a {self.state} session requires an available lifecycle between assignments"
                )
            # The committed policy already counted this conversation's history, so
            # the pool state must say the same thing as the lifecycle it carries:
            # ordinary idle means no counted provider/output failure, and
            # probation means exactly the one the policy counted. (A second
            # consecutive failure retires the conversation, so a between-
            # assignments streak is only ever 0 or 1.) Without this correlation a
            # restored or forged record could re-advertise a failed conversation
            # as ordinary idle and bypass the deliberate probation-retry gate.
            expected_streak = 0 if self.state == "idle" else 1
            if self.lifecycle.consecutive_provider_output_failures != expected_streak:
                raise SessionPoolError(
                    f"pool state {self.state!r} requires a counted failure streak of "
                    f"{expected_streak}, not "
                    f"{self.lifecycle.consecutive_provider_output_failures}"
                )
            _parse_utc(self.idle_since_utc, field="idle_since_utc")
        elif self.state != "active" and self.idle_since_utc is not None:
            raise SessionPoolError(f"a {self.state} session must not be idle-timed")
        # Retirement is decided by the committed policy, so the public pool state
        # and the lifecycle phase must say the same thing in both directions. A
        # record may not claim retirement the lifecycle never decided, and a
        # conversation the lifecycle retired may not be filed under any other
        # state, where `sessions_for("retired")` would silently omit it.
        retired_lifecycle = self.lifecycle is not None and self.lifecycle.phase == "retired"
        if self.state == "retired" and not retired_lifecycle:
            raise SessionPoolError("a retired session requires its lifecycle retirement decision")
        if retired_lifecycle and self.state != "retired":
            raise SessionPoolError(
                f"a lifecycle retired for {self.lifecycle.retirement_reason!r} must be "
                f"recorded as retired, not as {self.state!r}"
            )
        if (self.quarantine_reason is None) != (self.state != "quarantined"):
            raise SessionPoolError("quarantine_reason is required exactly when quarantined")
        if (self.probation_reason is None) != (self.state != "probation"):
            raise SessionPoolError("probation_reason is required exactly when on probation")

    @property
    def retirement_reason(self) -> str | None:
        return None if self.lifecycle is None else self.lifecycle.retirement_reason

    def _within_idle_window(self, now: dt.datetime) -> bool:
        idle_for = (now - _parse_utc(self.idle_since_utc, field="idle_since_utc")).total_seconds()
        return 0 <= idle_for < IDLE_SESSION_LIFETIME_SECONDS

    def is_reusable_at(self, now: dt.datetime) -> bool:
        if self.state != "idle" or self.session_id is None:
            return False
        return self._within_idle_window(now)

    def is_retry_offerable_at(self, now: dt.datetime) -> bool:
        """Return whether the pool may deliberately offer this probation a retry.

        This is never reusability: a probation conversation is invisible to
        `checkout` and is offered only by an explicit `offer_probation_retry`
        naming this exact record.
        """

        if self.state != "probation" or self.session_id is None:
            return False
        return self._within_idle_window(now)

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
            "probation_reason": self.probation_reason,
            "lifecycle": None if self.lifecycle is None else self.lifecycle.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PooledSession":
        fields = {
            "record_id", "compatibility", "state", "session_id",
            "completed_assignment_count", "idle_since_utc", "active_lease",
            "quarantine_reason", "probation_reason", "lifecycle",
        }
        _expect_fields(value, fields, where="pooled session")
        lease = value["active_lease"]
        lifecycle = value["lifecycle"]
        if lifecycle is not None:
            try:
                lifecycle = SessionLifecycleState.from_dict(lifecycle)
            except SessionLifecycleError as exc:
                raise SessionPoolError(str(exc)) from exc
        return cls(
            record_id=value["record_id"],
            compatibility=SessionCompatibility.from_dict(value["compatibility"]),
            state=value["state"],
            session_id=value["session_id"],
            completed_assignment_count=value["completed_assignment_count"],
            idle_since_utc=value["idle_since_utc"],
            active_lease=None if lease is None else AssignmentLease.from_dict(lease),
            quarantine_reason=value["quarantine_reason"],
            probation_reason=value["probation_reason"],
            lifecycle=lifecycle,
        )


class SessionPool:
    """Role-scoped pool of resumable provider conversations.

    Sessions are created lazily: nothing is launched until an assignment asks
    for one and no compatible idle conversation exists. Every budget and
    retirement decision comes from the committed AgentRuntime lifecycle policy
    and is applied only at an assignment boundary.
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
            if (
                session.lifecycle is not None
                and session.lifecycle.active_assignment_id != lease.assignment_id
            ):
                raise SessionPoolError("lifecycle names a different active assignment")
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

        A compatible idle session is resumed unless the committed lifecycle
        policy refuses the next assignment, in which case that conversation is
        retired between assignments and a fresh one is requested. An active,
        probation, quarantined, expired, or retired conversation is never taken,
        and a checked-out session becomes invisible to every other assignment.
        """

        if type(compatibility) is not SessionCompatibility:
            raise SessionPoolError("checkout requires an exact SessionCompatibility")
        moment = self._admit(now)
        lease_id = self._new_identity("lease")
        reusable = [
            session
            for session in self.sessions
            if session.compatibility == compatibility and session.is_reusable_at(moment)
        ]
        # Warmest first, with a deterministic tie-break so a restored pool always
        # selects the same conversation.
        reusable.sort(key=lambda item: (item.idle_since_utc or "", item.record_id))
        selected: PooledSession | None = None
        lifecycle: SessionLifecycleState | None = None
        while reusable:
            candidate = reusable.pop()
            started = self._start(candidate, lease_id=lease_id)
            if started.phase != "assigned":
                # The budget for the next assignment is already spent, so this
                # conversation retires here rather than being offered.
                self._sessions[candidate.record_id] = PooledSession(
                    record_id=candidate.record_id,
                    compatibility=candidate.compatibility,
                    state="retired",
                    session_id=candidate.session_id,
                    completed_assignment_count=candidate.completed_assignment_count,
                    lifecycle=started,
                )
                continue
            selected, lifecycle = candidate, started
            break
        return self._lease(
            lease_id=lease_id, selected=selected, lifecycle=lifecycle,
            compatibility=compatibility, worker_slot_id=worker_slot_id, task_id=task_id,
            worker_run_id=worker_run_id, source_commit=source_commit,
            checkout_identity=checkout_identity, moment=moment,
        )

    def offer_probation_retry(
        self,
        *,
        compatibility: SessionCompatibility,
        record_id: str,
        worker_slot_id: str,
        task_id: str,
        worker_run_id: str,
        source_commit: str,
        checkout_identity: str,
        now: dt.datetime | None = None,
    ) -> AssignmentLease:
        """Deliberately offer one exact probation conversation a controlled retry.

        A proven provider/output failure is accounted by the committed policy but
        is never advertised, so `checkout` cannot reach it. Only this call, which
        names the exact record and restates the identical stable compatibility,
        may offer it again. The retry is an ordinary assignment: its own durable
        result either resets the committed failure streak or lets a second
        consecutive provider/output failure retire the conversation.
        """

        if type(compatibility) is not SessionCompatibility:
            raise SessionPoolError("a probation retry requires an exact SessionCompatibility")
        moment = self._admit(now)
        session = self._sessions.get(_session_id(record_id, field="record_id"))
        if session is None or session.state != "probation":
            raise SessionPoolError("pool holds no probation conversation with this record")
        if session.compatibility != compatibility:
            raise SessionPoolError(
                "a probation retry must state the identical stable compatibility"
            )
        if not session.is_retry_offerable_at(moment):
            raise SessionPoolError("this probation conversation is no longer offerable")
        lease_id = self._new_identity("lease")
        lifecycle = self._start(session, lease_id=lease_id)
        if lifecycle.phase != "assigned":
            # The committed budget already ended this conversation, so the retry
            # is refused here rather than started as work it cannot finish.
            self._sessions[session.record_id] = PooledSession(
                record_id=session.record_id,
                compatibility=session.compatibility,
                state="retired",
                session_id=session.session_id,
                completed_assignment_count=session.completed_assignment_count,
                lifecycle=lifecycle,
            )
            self._validate_pool_state()
            raise SessionPoolError(
                "the committed lifetime policy retired this conversation instead of retrying it"
            )
        return self._lease(
            lease_id=lease_id, selected=session, lifecycle=lifecycle,
            compatibility=compatibility, worker_slot_id=worker_slot_id, task_id=task_id,
            worker_run_id=worker_run_id, source_commit=source_commit,
            checkout_identity=checkout_identity, moment=moment,
        )

    def _admit(self, now: dt.datetime | None) -> dt.datetime:
        """Return the assignment moment, refusing a pool already at capacity."""

        moment = self.clock() if now is None else now
        _utc_text(moment)
        if self.active_assignment_count >= self.max_concurrent_assignments:
            raise SessionPoolError(
                "pool capacity is fully committed to active assignments"
            )
        self.expire_idle(now=moment)
        return moment

    def _lease(
        self,
        *,
        lease_id: str,
        selected: PooledSession | None,
        lifecycle: SessionLifecycleState | None,
        compatibility: SessionCompatibility,
        worker_slot_id: str,
        task_id: str,
        worker_run_id: str,
        source_commit: str,
        checkout_identity: str,
        moment: dt.datetime,
    ) -> AssignmentLease:
        """Mint one exclusive lease and make its conversation invisible to others."""

        if selected is None:
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
            record_id = selected.record_id
            mode, session_id = "resume", selected.session_id
            prior, session_compatibility = (
                selected.completed_assignment_count,
                selected.compatibility,
            )
        lease = AssignmentLease(
            pool_schema_version=POOL_SCHEMA_VERSION,
            lease_id=lease_id,
            record_id=record_id,
            session_id=session_id,
            mode=mode,
            provider_identifier=compatibility.provider_identifier,
            model=compatibility.model,
            reasoning_effort=compatibility.reasoning_effort,
            session_class=compatibility.session_class,
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
            lifecycle=lifecycle,
        )
        self._validate_pool_state()
        return lease

    def _new_identity(self, what: str) -> str:
        value = self.identity_factory()
        try:
            return _session_id(value, field=f"{what} identity")
        except ProviderSessionError as exc:
            raise SessionPoolError(str(exc)) from exc

    def _start(self, session: PooledSession, *, lease_id: str) -> SessionLifecycleState:
        """Apply the committed start-of-assignment policy to a warm session."""

        if session.lifecycle is None:
            raise SessionPoolError("a reusable session must carry its lifecycle state")
        try:
            return start_assignment(
                session.lifecycle,
                assignment_id=lease_id,
                workload_class=session.compatibility.workload_class,
            ).state
        except SessionLifecycleError as exc:
            raise SessionPoolError(str(exc)) from exc

    # --------------------------------------------------------------- check-in

    def check_in(
        self,
        *,
        lease: AssignmentLease,
        result: Any,
        evidence_root: Any = None,
        now: dt.datetime | None = None,
    ) -> PooledSession:
        """Return a conversation to the idle pool, or quarantine it.

        Every identity on the durable result must equal the lease, and the exact
        persisted role artifact it names must exist under ``evidence_root``, hash
        to the recorded SHA-256, agree with the decisions it claims, and bind
        itself to this exact assignment. Anything stale, mismatched, unconfirmed,
        tampered, borrowed, semantically rejected, or rejected by the
        deterministic changed-path check quarantines instead of recycling, and
        never adopts the identity an unproven confirmation asserted.
        """

        session = self._leased_session(lease)
        moment = self.clock() if now is None else now
        _utc_text(moment)
        # Until the confirmation is proven exactly, the only trustworthy identity
        # is the one the lease/session already established. A pre-bound
        # conversation keeps it; a provider-named cold conversation still has
        # none, and an unproven confirmation must not supply one.
        trusted_id = session.session_id
        if type(result) is not DurableAssignmentResult:
            return self._quarantine(
                session,
                "check-in supplied no durable assignment result",
                outcome="output_failure",
                session_id=trusted_id,
            )
        mismatches = result.lease_mismatches(lease)
        if mismatches:
            return self._quarantine(
                session,
                f"check-in did not match its lease: {list(mismatches)}",
                outcome="identity_failure",
                result=result,
                session_id=trusted_id,
            )
        if result.compatibility() != session.compatibility:
            return self._quarantine(
                session,
                "check-in compatibility differs from the pooled conversation",
                outcome="session_incompatibility",
                result=result,
                session_id=trusted_id,
            )
        evidence = result.evidence_reason(evidence_root)
        if evidence is not None:
            return self._quarantine(
                session,
                f"durable role evidence is not provable: {evidence}",
                outcome="output_failure",
                result=result,
                session_id=trusted_id,
            )
        # The confirmation now matches the lease exactly and the persisted role
        # artifact proves the assignment, so a provider-named cold conversation
        # may finally be accounted under the identity it confirmed.
        proven_id = trusted_id or result.confirmed_session.session_id
        if not result.is_reusable:
            reason = (
                f"assignment finished {result.status} with semantics "
                f"{result.semantic_validation} and changed paths "
                f"{result.changed_path_validation}"
            )
            lifecycle = self._finish(
                session, outcome=result.assignment_outcome, result=result,
                session_id=proven_id,
            )
            if (
                lifecycle is not None
                and lifecycle.phase == "between_assignments"
                and lifecycle.consecutive_provider_output_failures > 0
                and lifecycle.session_id is not None
            ):
                # The committed policy counted this exact failure into its streak
                # without retiring the conversation. It is never advertised and
                # never reusable; it waits on probation for at most one
                # deliberate, exactly compatible retry.
                return self._probation(session, reason, lifecycle=lifecycle, now=moment)
            return self._settle_failed(
                session, reason, lifecycle=lifecycle, session_id=proven_id
            )
        lifecycle = self._finish(
            session, outcome="completed", result=result, session_id=proven_id
        )
        assert lifecycle is not None
        if lifecycle.phase == "retired":
            # The committed budget, context, or latency policy ended this
            # conversation at its assignment boundary; the work still counted.
            returned = PooledSession(
                record_id=session.record_id,
                compatibility=session.compatibility,
                state="retired",
                session_id=lifecycle.session_id,
                completed_assignment_count=lifecycle.completed_assignments,
                lifecycle=lifecycle,
            )
        else:
            returned = PooledSession(
                record_id=session.record_id,
                compatibility=session.compatibility,
                state="idle",
                session_id=lifecycle.session_id,
                completed_assignment_count=lifecycle.completed_assignments,
                idle_since_utc=_utc_text(moment),
                lifecycle=lifecycle,
            )
        self._sessions[session.record_id] = returned
        self._validate_pool_state()
        return returned

    def quarantine(
        self,
        lease: AssignmentLease,
        reason: str,
        *,
        outcome: str = "other_failure",
    ) -> PooledSession:
        """Withdraw a conversation from reuse without touching its worker.

        Quarantine stops selection only. No process is asked to stop, no
        provider history is deleted, and no credential is revoked.
        """

        session = self._leased_session(lease)
        return self._quarantine(
            session,
            _text(reason, field="reason"),
            outcome=_member(
                outcome, FAILED_ASSIGNMENT_OUTCOMES, field="quarantine outcome"
            ),
            session_id=session.session_id,
        )

    def observe(
        self,
        record_id: str,
        *,
        observation: str,
        known_context_window_percent: int | None = None,
    ) -> PooledSession:
        """Record a zero-cost idle/wait, or an explicit between-assignment retirement.

        Waiting for work is free: it consumes no budget. Incompatibility and
        identity failure retire the conversation immediately, and a known
        context-window utilization at or above the committed threshold retires it
        too. An active assignment is never observed this way, because retirement
        must never interrupt work in progress.
        """

        session = self._sessions.get(_session_id(record_id, field="record_id"))
        if session is None:
            raise SessionPoolError("pool does not hold this session record")
        if session.state == "active":
            raise SessionPoolError(
                "an active assignment is never interrupted by a between-assignment observation"
            )
        if session.state != "idle" or session.lifecycle is None:
            raise SessionPoolError("only an idle session can be observed between assignments")
        try:
            lifecycle = observe_between_assignments(
                session.lifecycle,
                observation=observation,
                known_context_window_percent=known_context_window_percent,
            ).state
        except SessionLifecycleError as exc:
            raise SessionPoolError(str(exc)) from exc
        if lifecycle.phase == "retired":
            observed = PooledSession(
                record_id=session.record_id,
                compatibility=session.compatibility,
                state="retired",
                session_id=session.session_id,
                completed_assignment_count=lifecycle.completed_assignments,
                lifecycle=lifecycle,
            )
        else:
            observed = PooledSession(
                record_id=session.record_id,
                compatibility=session.compatibility,
                state="idle",
                session_id=session.session_id,
                completed_assignment_count=lifecycle.completed_assignments,
                idle_since_utc=session.idle_since_utc,
                lifecycle=lifecycle,
            )
        self._sessions[session.record_id] = observed
        self._validate_pool_state()
        return observed

    def _quarantine(
        self,
        session: PooledSession,
        reason: str,
        *,
        outcome: str,
        result: DurableAssignmentResult | None = None,
        session_id: str | None,
    ) -> PooledSession:
        lifecycle = self._finish(
            session, outcome=outcome, result=result, session_id=session_id
        )
        return self._settle_failed(
            session, reason, lifecycle=lifecycle, session_id=session_id
        )

    def _settle_failed(
        self,
        session: PooledSession,
        reason: str,
        *,
        lifecycle: SessionLifecycleState | None,
        session_id: str | None,
    ) -> PooledSession:
        """Record the public outcome the committed lifecycle actually decided.

        A conversation the committed policy retired is `retired`, whatever ended
        it -- a second consecutive provider/output failure, identity failure,
        session incompatibility, the context-window threshold, sustained
        comparable latency, or an exhausted budget. Its retirement decision is
        already on the lifecycle, so the record carries no separate withdrawal
        reason and `sessions_for("retired")` reports it. Anything the policy did
        not authoritatively retire -- unproven evidence, a missing durable
        result, a cold conversation with no lifecycle at all -- is withdrawn as
        `quarantined` with the reason it was withdrawn for. Neither state is ever
        selectable, and this decides only how the pool records what happened.
        """

        if lifecycle is not None and lifecycle.phase == "retired":
            settled = PooledSession(
                record_id=session.record_id,
                compatibility=session.compatibility,
                state="retired",
                session_id=lifecycle.session_id,
                completed_assignment_count=lifecycle.completed_assignments,
                lifecycle=lifecycle,
            )
        else:
            settled = PooledSession(
                record_id=session.record_id,
                compatibility=session.compatibility,
                state="quarantined",
                # Only a proven identity is recorded: a provider-named
                # conversation whose confirmation was never proven stays
                # unidentified rather than adopting whatever the transcript
                # asserted.
                session_id=session_id if lifecycle is None else lifecycle.session_id,
                completed_assignment_count=(
                    session.completed_assignment_count
                    if lifecycle is None
                    else lifecycle.completed_assignments
                ),
                quarantine_reason=reason,
                lifecycle=lifecycle,
            )
        self._sessions[session.record_id] = settled
        self._validate_pool_state()
        return settled

    def _probation(
        self,
        session: PooledSession,
        reason: str,
        *,
        lifecycle: SessionLifecycleState,
        now: dt.datetime,
    ) -> PooledSession:
        """Hold a counted, non-retiring failure for one deliberate retry only."""

        placed = PooledSession(
            record_id=session.record_id,
            compatibility=session.compatibility,
            state="probation",
            session_id=lifecycle.session_id,
            completed_assignment_count=lifecycle.completed_assignments,
            idle_since_utc=_utc_text(now),
            probation_reason=reason,
            lifecycle=lifecycle,
        )
        self._sessions[session.record_id] = placed
        self._validate_pool_state()
        return placed

    def _finish(
        self,
        session: PooledSession,
        *,
        outcome: str,
        result: DurableAssignmentResult | None,
        session_id: str | None,
    ) -> SessionLifecycleState | None:
        """Apply the committed end-of-assignment policy at this exact boundary.

        A conversation whose provider named its own thread has no lifecycle state
        until its identity is confirmed, so the first assignment's start and
        finish are applied together here, under the exact identity the caller
        proved rather than whatever the transcript claimed. Accounting is
        identical either way; a first assignment that never proved an identity
        simply has nothing to account against and is quarantined without one.
        """

        lifecycle = session.lifecycle
        if lifecycle is None:
            if result is None or session.active_lease is None or session_id is None:
                return None
            try:
                created = SessionLifecycleState.create(
                    provider_identifier=session.compatibility.provider_identifier,
                    role=session.compatibility.role,
                    session_id=session_id,
                    session_class=session.compatibility.session_class,
                )
                lifecycle = start_assignment(
                    created,
                    assignment_id=session.active_lease.assignment_id,
                    workload_class=session.compatibility.workload_class,
                ).state
            except SessionLifecycleError as exc:
                raise SessionPoolError(str(exc)) from exc
        if lifecycle.phase != "assigned":
            return lifecycle
        try:
            return finish_assignment(
                lifecycle,
                assignment_id=lifecycle.active_assignment_id or "",
                outcome=outcome,
                known_context_window_percent=(
                    None if result is None else result.known_context_window_percent
                ),
                latency_sample=None if result is None else result.latency_sample,
            ).state
        except SessionLifecycleError as exc:
            raise SessionPoolError(str(exc)) from exc

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
        """Expire returned conversations older than the idle lifetime.

        Only conversations on the idle clock -- ``idle`` and ``probation`` -- are
        considered, so a stale probation is never offered a retry hours later. An
        active session is never expired or stolen however long its worker has
        been running, and expiry never deletes provider history or credentials.
        """

        moment = self.clock() if now is None else now
        expired: list[PooledSession] = []
        for session in self.sessions:
            if session.state not in _TIMED_STATES:
                continue
            if session.is_reusable_at(moment) or session.is_retry_offerable_at(moment):
                continue
            replacement = PooledSession(
                record_id=session.record_id,
                compatibility=session.compatibility,
                state="expired",
                session_id=session.session_id,
                completed_assignment_count=session.completed_assignment_count,
                lifecycle=session.lifecycle,
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
        # The nested per-session compatibility is validated independently, so a
        # payload cannot claim a supported protocol at the top level while
        # carrying a conversation that learned a different one.
        _protocol_version(value["protocol_version"], field="pool protocol_version")
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
    "ARCHITECT_COMPLETED_CYCLE_LIMIT",
    "ARCHITECT_SESSION_ROLE",
    "ASSIGNMENT_RESULT_OUTCOMES",
    "CAPABILITY_CLASSES",
    "CAPABILITY_WORKLOAD_CLASSES",
    "CREW_SESSION_PROTOCOL_VERSION",
    "CREW_SESSION_ROLES",
    "DEFAULT_MAX_CONCURRENT_ASSIGNMENTS",
    "DURABLE_ASSIGNMENT_RESULT_SCHEMA_VERSION",
    "FAILED_ASSIGNMENT_OUTCOMES",
    "IDLE_SESSION_LIFETIME_SECONDS",
    "POOL_SCHEMA_VERSION",
    "SESSION_STATES",
    "ROLE_EVIDENCE_FIELDS",
    "ROLE_EVIDENCE_SCHEMA_VERSION",
    "WORKER_WEIGHTED_UNIT_LIMIT",
    "WORKER_WEIGHTS",
    "AssignmentLease",
    "DurableAssignmentResult",
    "LatencySample",
    "PooledSession",
    "SessionCompatibility",
    "SessionPool",
    "SessionPoolError",
    "SessionPoolStore",
    "assignment_capsule",
    "pooled_assignment_evidence",
    "utc_now",
]
