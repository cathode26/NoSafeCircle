"""Deterministic retirement policy for reusable provider sessions.

This module owns accounting and retirement decisions only.  It does not start,
resume, stop, or contact a provider session.  A scheduler applies the returned
decision after the current assignment has ended.

Context-window retirement is intentionally evidence-driven.  ``None`` means
the utilization is unknown and never triggers a threshold decision.  Callers
must not estimate or synthesize a percentage that the provider did not expose.
Latency retirement likewise requires three consecutive, explicitly comparable
samples with the same comparison key and baseline.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any

from .provider_sessions import validate_session_id


SESSION_LIFECYCLE_SCHEMA_VERSION = "1.0"
WORKER_WEIGHTED_UNIT_LIMIT = 48
ARCHITECT_COMPLETED_CYCLE_LIMIT = 100
CONTEXT_WINDOW_RETIRE_PERCENT = 70
LATENCY_RETIRE_MULTIPLIER = 2
LATENCY_RETIRE_SAMPLE_COUNT = 3

SESSION_CLASSES = frozenset({"worker", "architect"})
SESSION_PHASES = frozenset({"between_assignments", "assigned", "retired"})
WORKLOAD_CLASSES = frozenset({"fast", "standard", "deep", "admission_cycle"})
WORKER_WEIGHTS = {"fast": 1, "standard": 3, "deep": 6}
ASSIGNMENT_OUTCOMES = frozenset(
    {
        "completed",
        "provider_failure",
        "output_failure",
        "other_failure",
        "session_incompatibility",
        "identity_failure",
        "waiting",
        "idle",
    }
)
BETWEEN_ASSIGNMENT_OBSERVATIONS = frozenset(
    {"idle", "waiting", "session_incompatibility", "identity_failure"}
)
RETIREMENT_REASONS = frozenset(
    {
        "worker_weighted_unit_limit",
        "worker_weighted_unit_limit_would_be_exceeded",
        "architect_completed_cycle_limit",
        "session_incompatibility",
        "identity_failure",
        "consecutive_provider_output_failures",
        "known_context_window_threshold",
        "sustained_comparable_latency",
    }
)

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*(?:-[a-z0-9_]+)*$")
_ASSIGNMENT_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$")


class SessionLifecycleError(ValueError):
    """Raised when lifecycle state or a requested transition is invalid."""


def _exact_object(value: Any, fields: set[str], *, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise SessionLifecycleError(f"{label} must be a built-in JSON object")
    if set(value) != fields:
        raise SessionLifecycleError(
            f"{label} fields differ from schema; "
            f"missing={sorted(fields - set(value))}, extras={sorted(set(value) - fields)}"
        )
    return value


def _text(value: Any, *, field: str) -> str:
    if type(value) is not str or not value:
        raise SessionLifecycleError(f"{field} must be non-empty built-in text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SessionLifecycleError(f"{field} must be valid UTF-8") from exc
    return value


def _identifier(value: Any, *, field: str) -> str:
    text = _text(value, field=field)
    if _IDENTIFIER.fullmatch(text) is None:
        raise SessionLifecycleError(
            f"{field} must be one conservative lowercase identifier"
        )
    return text


def _assignment_id(value: Any) -> str:
    text = _text(value, field="assignment_id")
    if _ASSIGNMENT_ID.fullmatch(text) is None:
        raise SessionLifecycleError(
            "assignment_id must be a lowercase ASCII slug of 1..128 characters"
        )
    return text


def _integer(
    value: Any,
    *,
    field: str,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if type(value) is not int or value < minimum or (
        maximum is not None and value > maximum
    ):
        bounds = f">={minimum}" if maximum is None else f"{minimum}..{maximum}"
        raise SessionLifecycleError(f"{field} must be an integer in {bounds}")
    return value


def _optional_percent(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    return _integer(value, field=field, minimum=0, maximum=100)


@dataclass(frozen=True)
class LatencySample:
    """One caller-proven latency comparison, expressed with exact integers."""

    comparison_key: str
    duration_milliseconds: int
    baseline_milliseconds: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "comparison_key",
            _identifier(self.comparison_key, field="comparison_key"),
        )
        _integer(
            self.duration_milliseconds,
            field="duration_milliseconds",
            minimum=1,
        )
        _integer(
            self.baseline_milliseconds,
            field="baseline_milliseconds",
            minimum=1,
        )

    @property
    def is_degraded(self) -> bool:
        return (
            self.duration_milliseconds
            >= LATENCY_RETIRE_MULTIPLIER * self.baseline_milliseconds
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparison_key": self.comparison_key,
            "duration_milliseconds": self.duration_milliseconds,
            "baseline_milliseconds": self.baseline_milliseconds,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "LatencySample":
        item = _exact_object(
            value,
            {
                "comparison_key",
                "duration_milliseconds",
                "baseline_milliseconds",
            },
            label="latency sample",
        )
        return cls(
            item["comparison_key"],
            item["duration_milliseconds"],
            item["baseline_milliseconds"],
        )


@dataclass(frozen=True)
class SessionLifecycleState:
    """Serializable state for one exact provider conversation."""

    schema_version: str
    provider_identifier: str
    role: str
    session_id: str
    session_class: str
    phase: str = "between_assignments"
    sequence: int = 0
    completed_assignments: int = 0
    worker_weighted_units: int = 0
    architect_completed_admission_cycles: int = 0
    consecutive_provider_output_failures: int = 0
    latency_comparison_key: str | None = None
    latency_baseline_milliseconds: int | None = None
    latency_degraded_sample_count: int = 0
    known_context_window_percent: int | None = None
    active_assignment_id: str | None = None
    active_workload_class: str | None = None
    active_weighted_units: int = 0
    retirement_reason: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != SESSION_LIFECYCLE_SCHEMA_VERSION:
            raise SessionLifecycleError("unsupported session lifecycle schema version")
        object.__setattr__(
            self,
            "provider_identifier",
            _identifier(self.provider_identifier, field="provider_identifier"),
        )
        object.__setattr__(self, "role", _identifier(self.role, field="role"))
        try:
            validated_session_id = validate_session_id(self.session_id)
        except ValueError as exc:
            raise SessionLifecycleError(str(exc)) from exc
        object.__setattr__(self, "session_id", validated_session_id)
        if type(self.session_class) is not str or self.session_class not in SESSION_CLASSES:
            raise SessionLifecycleError("session_class must be worker or architect")
        if type(self.phase) is not str or self.phase not in SESSION_PHASES:
            raise SessionLifecycleError("phase is unsupported")
        _integer(self.sequence, field="sequence")
        _integer(self.completed_assignments, field="completed_assignments")
        _integer(
            self.worker_weighted_units,
            field="worker_weighted_units",
            maximum=WORKER_WEIGHTED_UNIT_LIMIT,
        )
        _integer(
            self.architect_completed_admission_cycles,
            field="architect_completed_admission_cycles",
            maximum=ARCHITECT_COMPLETED_CYCLE_LIMIT,
        )
        _integer(
            self.consecutive_provider_output_failures,
            field="consecutive_provider_output_failures",
            maximum=2,
        )
        _integer(
            self.latency_degraded_sample_count,
            field="latency_degraded_sample_count",
            maximum=LATENCY_RETIRE_SAMPLE_COUNT,
        )
        _optional_percent(
            self.known_context_window_percent,
            field="known_context_window_percent",
        )
        if self.session_class == "worker" and self.architect_completed_admission_cycles:
            raise SessionLifecycleError(
                "worker session cannot contain architect admission-cycle accounting"
            )
        if self.session_class == "architect" and self.worker_weighted_units:
            raise SessionLifecycleError(
                "architect session cannot contain worker weighted-unit accounting"
            )
        if self.session_class == "worker" and (
            self.worker_weighted_units
            > self.completed_assignments * max(WORKER_WEIGHTS.values())
        ):
            raise SessionLifecycleError(
                "worker completed-assignment and weighted-unit accounting disagree"
            )
        if (
            self.session_class == "architect"
            and self.architect_completed_admission_cycles > self.completed_assignments
        ):
            raise SessionLifecycleError(
                "architect completed cycles exceed completed assignments"
            )
        latency_fields_present = (
            self.latency_comparison_key is not None
            or self.latency_baseline_milliseconds is not None
            or self.latency_degraded_sample_count != 0
        )
        if latency_fields_present:
            if (
                self.latency_comparison_key is None
                or self.latency_baseline_milliseconds is None
                or self.latency_degraded_sample_count < 1
            ):
                raise SessionLifecycleError(
                    "latency comparison key, baseline, and positive streak must appear together"
                )
            _identifier(self.latency_comparison_key, field="latency_comparison_key")
            _integer(
                self.latency_baseline_milliseconds,
                field="latency_baseline_milliseconds",
                minimum=1,
            )
        if self.phase == "assigned":
            if self.retirement_reason is not None:
                raise SessionLifecycleError("an assigned session cannot already be retired")
            if self.active_assignment_id is None or self.active_workload_class is None:
                raise SessionLifecycleError(
                    "assigned phase requires assignment identity and workload class"
                )
            _assignment_id(self.active_assignment_id)
            if self.active_workload_class not in WORKLOAD_CLASSES:
                raise SessionLifecycleError("active_workload_class is unsupported")
            if self.session_class == "worker" and self.active_workload_class == "admission_cycle":
                raise SessionLifecycleError("worker session cannot run an admission cycle")
            if self.session_class == "architect" and self.active_workload_class != "admission_cycle":
                raise SessionLifecycleError("architect session requires admission_cycle work")
            expected_weight = (
                WORKER_WEIGHTS[self.active_workload_class]
                if self.session_class == "worker"
                else 0
            )
            if self.active_weighted_units != expected_weight:
                raise SessionLifecycleError(
                    "active weighted units disagree with the session/workload class"
                )
        else:
            if (
                self.active_assignment_id is not None
                or self.active_workload_class is not None
                or self.active_weighted_units != 0
            ):
                raise SessionLifecycleError(
                    "only an assigned session may retain active assignment state"
                )
        if self.phase == "retired":
            if self.retirement_reason not in RETIREMENT_REASONS:
                raise SessionLifecycleError("retired session requires a supported reason")
        elif self.retirement_reason is not None:
            raise SessionLifecycleError("only retired phase may name a retirement reason")
        threshold_reason: str | None = None
        if self.consecutive_provider_output_failures >= 2:
            threshold_reason = "consecutive_provider_output_failures"
        elif (
            self.known_context_window_percent is not None
            and self.known_context_window_percent >= CONTEXT_WINDOW_RETIRE_PERCENT
        ):
            threshold_reason = "known_context_window_threshold"
        elif self.latency_degraded_sample_count >= LATENCY_RETIRE_SAMPLE_COUNT:
            threshold_reason = "sustained_comparable_latency"
        elif (
            self.session_class == "worker"
            and self.worker_weighted_units >= WORKER_WEIGHTED_UNIT_LIMIT
        ):
            threshold_reason = "worker_weighted_unit_limit"
        elif (
            self.session_class == "architect"
            and self.architect_completed_admission_cycles
            >= ARCHITECT_COMPLETED_CYCLE_LIMIT
        ):
            threshold_reason = "architect_completed_cycle_limit"
        if threshold_reason is not None and self.phase != "retired":
            raise SessionLifecycleError(
                "threshold state must carry its deterministic retirement decision"
            )
        if self.retirement_reason == "worker_weighted_unit_limit" and (
            self.session_class != "worker"
            or self.worker_weighted_units != WORKER_WEIGHTED_UNIT_LIMIT
        ):
            raise SessionLifecycleError("worker limit retirement facts disagree")
        if self.retirement_reason == "worker_weighted_unit_limit_would_be_exceeded" and (
            self.session_class != "worker"
            or self.worker_weighted_units
            <= WORKER_WEIGHTED_UNIT_LIMIT - max(WORKER_WEIGHTS.values())
            or self.worker_weighted_units >= WORKER_WEIGHTED_UNIT_LIMIT
        ):
            raise SessionLifecycleError("worker overflow retirement facts disagree")
        if self.retirement_reason == "architect_completed_cycle_limit" and (
            self.session_class != "architect"
            or self.architect_completed_admission_cycles
            != ARCHITECT_COMPLETED_CYCLE_LIMIT
        ):
            raise SessionLifecycleError("architect limit retirement facts disagree")
        if (
            self.retirement_reason == "consecutive_provider_output_failures"
            and self.consecutive_provider_output_failures != 2
        ):
            raise SessionLifecycleError("failure-streak retirement facts disagree")
        if self.retirement_reason == "known_context_window_threshold" and (
            self.known_context_window_percent is None
            or self.known_context_window_percent < CONTEXT_WINDOW_RETIRE_PERCENT
        ):
            raise SessionLifecycleError("context retirement facts disagree")
        if (
            self.retirement_reason == "sustained_comparable_latency"
            and self.latency_degraded_sample_count != LATENCY_RETIRE_SAMPLE_COUNT
        ):
            raise SessionLifecycleError("latency retirement facts disagree")

    @classmethod
    def create(
        cls,
        *,
        provider_identifier: str,
        role: str,
        session_id: str,
        session_class: str,
    ) -> "SessionLifecycleState":
        return cls(
            SESSION_LIFECYCLE_SCHEMA_VERSION,
            provider_identifier,
            role,
            session_id,
            session_class,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider_identifier": self.provider_identifier,
            "role": self.role,
            "session_id": self.session_id,
            "session_class": self.session_class,
            "phase": self.phase,
            "sequence": self.sequence,
            "completed_assignments": self.completed_assignments,
            "worker_weighted_units": self.worker_weighted_units,
            "architect_completed_admission_cycles": self.architect_completed_admission_cycles,
            "consecutive_provider_output_failures": self.consecutive_provider_output_failures,
            "latency_comparison_key": self.latency_comparison_key,
            "latency_baseline_milliseconds": self.latency_baseline_milliseconds,
            "latency_degraded_sample_count": self.latency_degraded_sample_count,
            "known_context_window_percent": self.known_context_window_percent,
            "active_assignment_id": self.active_assignment_id,
            "active_workload_class": self.active_workload_class,
            "active_weighted_units": self.active_weighted_units,
            "retirement_reason": self.retirement_reason,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SessionLifecycleState":
        fields = {
            "schema_version",
            "provider_identifier",
            "role",
            "session_id",
            "session_class",
            "phase",
            "sequence",
            "completed_assignments",
            "worker_weighted_units",
            "architect_completed_admission_cycles",
            "consecutive_provider_output_failures",
            "latency_comparison_key",
            "latency_baseline_milliseconds",
            "latency_degraded_sample_count",
            "known_context_window_percent",
            "active_assignment_id",
            "active_workload_class",
            "active_weighted_units",
            "retirement_reason",
        }
        return cls(**_exact_object(value, fields, label="session lifecycle state"))


@dataclass(frozen=True)
class SessionLifecycleTelemetry:
    """One deterministic transition record suitable for an append-only journal."""

    schema_version: str
    sequence: int
    event: str
    provider_identifier: str
    role: str
    session_id: str
    session_class: str
    phase_before: str
    phase_after: str
    assignment_id: str | None
    workload_class: str | None
    outcome: str | None
    budget_kind: str
    budget_delta: int
    budget_used: int
    budget_limit: int
    consecutive_provider_output_failures: int
    context_window_known: bool
    known_context_window_percent: int | None
    latency_sample: LatencySample | None
    latency_degraded_sample_count: int
    retirement_decision: bool
    retirement_reason: str | None

    def __post_init__(self) -> None:
        if self.schema_version != SESSION_LIFECYCLE_SCHEMA_VERSION:
            raise SessionLifecycleError("unsupported lifecycle telemetry schema version")
        _integer(self.sequence, field="telemetry sequence", minimum=1)
        if self.event not in {
            "assignment_started",
            "assignment_completed",
            "assignment_refused",
            "idle_observed",
            "waiting_observed",
            "session_incompatibility_observed",
            "identity_failure_observed",
        }:
            raise SessionLifecycleError("telemetry event is unsupported")
        _identifier(self.provider_identifier, field="provider_identifier")
        _identifier(self.role, field="role")
        try:
            validate_session_id(self.session_id)
        except ValueError as exc:
            raise SessionLifecycleError(str(exc)) from exc
        if self.session_class not in SESSION_CLASSES:
            raise SessionLifecycleError("telemetry session_class is unsupported")
        if self.phase_before not in SESSION_PHASES or self.phase_after not in SESSION_PHASES:
            raise SessionLifecycleError("telemetry phase is unsupported")
        if self.assignment_id is not None:
            _assignment_id(self.assignment_id)
        if self.workload_class is not None and self.workload_class not in WORKLOAD_CLASSES:
            raise SessionLifecycleError("telemetry workload_class is unsupported")
        if self.outcome is not None and self.outcome not in ASSIGNMENT_OUTCOMES:
            raise SessionLifecycleError("telemetry outcome is unsupported")
        if self.budget_kind not in {"worker_weighted_units", "architect_completed_admission_cycles"}:
            raise SessionLifecycleError("telemetry budget_kind is unsupported")
        _integer(self.budget_delta, field="budget_delta")
        _integer(self.budget_used, field="budget_used")
        _integer(self.budget_limit, field="budget_limit", minimum=1)
        if self.budget_used > self.budget_limit:
            raise SessionLifecycleError("telemetry budget exceeds its limit")
        _integer(
            self.consecutive_provider_output_failures,
            field="telemetry failure streak",
            maximum=2,
        )
        if type(self.context_window_known) is not bool:
            raise SessionLifecycleError("context_window_known must be boolean")
        _optional_percent(
            self.known_context_window_percent,
            field="known_context_window_percent",
        )
        if self.context_window_known != (self.known_context_window_percent is not None):
            raise SessionLifecycleError(
                "context known flag and percentage must agree"
            )
        if self.latency_sample is not None and type(self.latency_sample) is not LatencySample:
            raise SessionLifecycleError("latency_sample must be an exact LatencySample")
        _integer(
            self.latency_degraded_sample_count,
            field="telemetry latency streak",
            maximum=LATENCY_RETIRE_SAMPLE_COUNT,
        )
        if type(self.retirement_decision) is not bool:
            raise SessionLifecycleError("retirement_decision must be boolean")
        if self.retirement_decision:
            if self.phase_after != "retired" or self.retirement_reason not in RETIREMENT_REASONS:
                raise SessionLifecycleError("retirement telemetry is inconsistent")
        elif self.retirement_reason is not None or self.phase_after == "retired":
            raise SessionLifecycleError("non-retirement telemetry cannot claim retirement")
        if self.event == "assignment_started":
            if (
                self.phase_before != "between_assignments"
                or self.phase_after != "assigned"
                or self.assignment_id is None
                or self.workload_class is None
                or self.outcome is not None
                or self.budget_delta != 0
            ):
                raise SessionLifecycleError("assignment-start telemetry is inconsistent")
        elif self.event == "assignment_completed":
            if (
                self.phase_before != "assigned"
                or self.phase_after not in {"between_assignments", "retired"}
                or self.assignment_id is None
                or self.workload_class is None
                or self.outcome is None
            ):
                raise SessionLifecycleError("assignment-completion telemetry is inconsistent")
        elif self.event == "assignment_refused":
            if (
                self.phase_before != "between_assignments"
                or self.phase_after != "retired"
                or self.assignment_id is None
                or self.workload_class is None
                or self.outcome is not None
                or self.budget_delta != 0
            ):
                raise SessionLifecycleError("assignment-refusal telemetry is inconsistent")
        elif (
            self.phase_before != "between_assignments"
            or self.phase_after not in {"between_assignments", "retired"}
            or self.assignment_id is not None
            or self.workload_class is not None
            or self.outcome is not None
            or self.budget_delta != 0
        ):
            raise SessionLifecycleError("between-assignment telemetry is inconsistent")
        if self.event == "session_incompatibility_observed" and (
            self.phase_after != "retired"
            or self.retirement_reason != "session_incompatibility"
        ):
            raise SessionLifecycleError("incompatibility telemetry must retire the session")
        if self.event == "identity_failure_observed" and (
            self.phase_after != "retired"
            or self.retirement_reason != "identity_failure"
        ):
            raise SessionLifecycleError("identity-failure telemetry must retire the session")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "event": self.event,
            "provider_identifier": self.provider_identifier,
            "role": self.role,
            "session_id": self.session_id,
            "session_class": self.session_class,
            "phase_before": self.phase_before,
            "phase_after": self.phase_after,
            "assignment_id": self.assignment_id,
            "workload_class": self.workload_class,
            "outcome": self.outcome,
            "budget_kind": self.budget_kind,
            "budget_delta": self.budget_delta,
            "budget_used": self.budget_used,
            "budget_limit": self.budget_limit,
            "consecutive_provider_output_failures": self.consecutive_provider_output_failures,
            "context_window_known": self.context_window_known,
            "known_context_window_percent": self.known_context_window_percent,
            "latency_sample": (
                None if self.latency_sample is None else self.latency_sample.to_dict()
            ),
            "latency_degraded_sample_count": self.latency_degraded_sample_count,
            "retirement_decision": self.retirement_decision,
            "retirement_reason": self.retirement_reason,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SessionLifecycleTelemetry":
        fields = {
            "schema_version",
            "sequence",
            "event",
            "provider_identifier",
            "role",
            "session_id",
            "session_class",
            "phase_before",
            "phase_after",
            "assignment_id",
            "workload_class",
            "outcome",
            "budget_kind",
            "budget_delta",
            "budget_used",
            "budget_limit",
            "consecutive_provider_output_failures",
            "context_window_known",
            "known_context_window_percent",
            "latency_sample",
            "latency_degraded_sample_count",
            "retirement_decision",
            "retirement_reason",
        }
        item = dict(_exact_object(value, fields, label="session lifecycle telemetry"))
        if item["latency_sample"] is not None:
            item["latency_sample"] = LatencySample.from_dict(item["latency_sample"])
        return cls(**item)


@dataclass(frozen=True)
class SessionLifecycleTransition:
    """The next immutable state and the telemetry that proves the decision."""

    state: SessionLifecycleState
    telemetry: SessionLifecycleTelemetry

    def __post_init__(self) -> None:
        if type(self.state) is not SessionLifecycleState:
            raise SessionLifecycleError("transition state must be exact lifecycle state")
        if type(self.telemetry) is not SessionLifecycleTelemetry:
            raise SessionLifecycleError("transition telemetry must be exact lifecycle telemetry")
        if self.state.sequence != self.telemetry.sequence:
            raise SessionLifecycleError("transition state and telemetry sequence disagree")
        for field in ("provider_identifier", "role", "session_id", "session_class"):
            if getattr(self.state, field) != getattr(self.telemetry, field):
                raise SessionLifecycleError(
                    f"transition state and telemetry {field} disagree"
                )
        if self.state.phase != self.telemetry.phase_after:
            raise SessionLifecycleError("transition state and telemetry phase disagree")
        budget_kind, budget_used, budget_limit = _budget(self.state)
        if (
            self.telemetry.budget_kind != budget_kind
            or self.telemetry.budget_used != budget_used
            or self.telemetry.budget_limit != budget_limit
        ):
            raise SessionLifecycleError("transition state and telemetry budget disagree")
        if (
            self.state.consecutive_provider_output_failures
            != self.telemetry.consecutive_provider_output_failures
            or self.state.latency_degraded_sample_count
            != self.telemetry.latency_degraded_sample_count
            or self.state.known_context_window_percent
            != self.telemetry.known_context_window_percent
            or self.state.retirement_reason != self.telemetry.retirement_reason
        ):
            raise SessionLifecycleError("transition state and telemetry decision facts disagree")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SESSION_LIFECYCLE_SCHEMA_VERSION,
            "state": self.state.to_dict(),
            "telemetry": self.telemetry.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SessionLifecycleTransition":
        item = _exact_object(
            value,
            {"schema_version", "state", "telemetry"},
            label="session lifecycle transition",
        )
        if item["schema_version"] != SESSION_LIFECYCLE_SCHEMA_VERSION:
            raise SessionLifecycleError("unsupported lifecycle transition schema version")
        return cls(
            SessionLifecycleState.from_dict(item["state"]),
            SessionLifecycleTelemetry.from_dict(item["telemetry"]),
        )


def _require_state(value: Any) -> SessionLifecycleState:
    if type(value) is not SessionLifecycleState:
        raise SessionLifecycleError("state must be an exact SessionLifecycleState")
    return value


def _budget(state: SessionLifecycleState) -> tuple[str, int, int]:
    if state.session_class == "worker":
        return (
            "worker_weighted_units",
            state.worker_weighted_units,
            WORKER_WEIGHTED_UNIT_LIMIT,
        )
    return (
        "architect_completed_admission_cycles",
        state.architect_completed_admission_cycles,
        ARCHITECT_COMPLETED_CYCLE_LIMIT,
    )


def _telemetry(
    before: SessionLifecycleState,
    after: SessionLifecycleState,
    *,
    event: str,
    assignment_id: str | None,
    workload_class: str | None,
    outcome: str | None,
    budget_delta: int,
    context_percent: int | None,
    latency_sample: LatencySample | None,
) -> SessionLifecycleTelemetry:
    budget_kind, used, limit = _budget(after)
    return SessionLifecycleTelemetry(
        SESSION_LIFECYCLE_SCHEMA_VERSION,
        after.sequence,
        event,
        after.provider_identifier,
        after.role,
        after.session_id,
        after.session_class,
        before.phase,
        after.phase,
        assignment_id,
        workload_class,
        outcome,
        budget_kind,
        budget_delta,
        used,
        limit,
        after.consecutive_provider_output_failures,
        context_percent is not None,
        context_percent,
        latency_sample,
        after.latency_degraded_sample_count,
        after.phase == "retired",
        after.retirement_reason,
    )


def _retire(
    state: SessionLifecycleState,
    reason: str,
    *,
    sequence: int,
    known_context_window_percent: int | None = None,
) -> SessionLifecycleState:
    if state.phase == "assigned":
        raise SessionLifecycleError("session retirement is allowed only between assignments")
    if reason not in RETIREMENT_REASONS:
        raise SessionLifecycleError("retirement reason is unsupported")
    return replace(
        state,
        phase="retired",
        sequence=sequence,
        known_context_window_percent=known_context_window_percent,
        active_assignment_id=None,
        active_workload_class=None,
        active_weighted_units=0,
        retirement_reason=reason,
    )


def start_assignment(
    state: SessionLifecycleState,
    *,
    assignment_id: str,
    workload_class: str,
) -> SessionLifecycleTransition:
    """Begin one assignment, or retire before it if its budget would overflow."""

    state = _require_state(state)
    assignment_id = _assignment_id(assignment_id)
    if type(workload_class) is not str or workload_class not in WORKLOAD_CLASSES:
        raise SessionLifecycleError("workload_class is unsupported")
    if state.phase != "between_assignments":
        raise SessionLifecycleError("only an available between-assignment session may start work")
    if state.session_class == "worker":
        if workload_class == "admission_cycle":
            raise SessionLifecycleError("worker session cannot start an admission cycle")
        weight = WORKER_WEIGHTS[workload_class]
        if state.worker_weighted_units + weight > WORKER_WEIGHTED_UNIT_LIMIT:
            after = _retire(
                state,
                "worker_weighted_unit_limit_would_be_exceeded",
                sequence=state.sequence + 1,
            )
            telemetry = _telemetry(
                state,
                after,
                event="assignment_refused",
                assignment_id=assignment_id,
                workload_class=workload_class,
                outcome=None,
                budget_delta=0,
                context_percent=after.known_context_window_percent,
                latency_sample=None,
            )
            return SessionLifecycleTransition(after, telemetry)
    else:
        if workload_class != "admission_cycle":
            raise SessionLifecycleError("architect session requires admission_cycle work")
        weight = 0
        if state.architect_completed_admission_cycles >= ARCHITECT_COMPLETED_CYCLE_LIMIT:
            after = _retire(
                state,
                "architect_completed_cycle_limit",
                sequence=state.sequence + 1,
            )
            telemetry = _telemetry(
                state,
                after,
                event="assignment_refused",
                assignment_id=assignment_id,
                workload_class=workload_class,
                outcome=None,
                budget_delta=0,
                context_percent=after.known_context_window_percent,
                latency_sample=None,
            )
            return SessionLifecycleTransition(after, telemetry)
    after = replace(
        state,
        phase="assigned",
        sequence=state.sequence + 1,
        active_assignment_id=assignment_id,
        active_workload_class=workload_class,
        active_weighted_units=weight,
    )
    return SessionLifecycleTransition(
        after,
        _telemetry(
            state,
            after,
            event="assignment_started",
            assignment_id=assignment_id,
            workload_class=workload_class,
            outcome=None,
            budget_delta=0,
            context_percent=after.known_context_window_percent,
            latency_sample=None,
        ),
    )


def _latency_state(
    state: SessionLifecycleState,
    sample: LatencySample | None,
) -> tuple[str | None, int | None, int]:
    if sample is None or not sample.is_degraded:
        return None, None, 0
    same_comparison = (
        state.latency_comparison_key == sample.comparison_key
        and state.latency_baseline_milliseconds == sample.baseline_milliseconds
    )
    return (
        sample.comparison_key,
        sample.baseline_milliseconds,
        state.latency_degraded_sample_count + 1 if same_comparison else 1,
    )


def finish_assignment(
    state: SessionLifecycleState,
    *,
    assignment_id: str,
    outcome: str,
    known_context_window_percent: int | None = None,
    latency_sample: LatencySample | None = None,
) -> SessionLifecycleTransition:
    """End the active assignment and decide retirement at that safe boundary."""

    state = _require_state(state)
    assignment_id = _assignment_id(assignment_id)
    if state.phase != "assigned":
        raise SessionLifecycleError("finishing requires an assigned session")
    if assignment_id != state.active_assignment_id:
        raise SessionLifecycleError("assignment_id differs from the active assignment")
    if type(outcome) is not str or outcome not in ASSIGNMENT_OUTCOMES:
        raise SessionLifecycleError("assignment outcome is unsupported")
    context_percent = _optional_percent(
        known_context_window_percent,
        field="known_context_window_percent",
    )
    if latency_sample is not None and type(latency_sample) is not LatencySample:
        raise SessionLifecycleError("latency_sample must be an exact LatencySample")

    failure_streak = (
        min(2, state.consecutive_provider_output_failures + 1)
        if outcome in {"provider_failure", "output_failure"}
        else 0
    )
    latency_key, latency_baseline, latency_streak = _latency_state(
        state, latency_sample
    )
    consumes_work_budget = outcome not in {"waiting", "idle"}
    worker_delta = (
        state.active_weighted_units
        if state.session_class == "worker" and consumes_work_budget
        else 0
    )
    architect_delta = (
        1
        if state.session_class == "architect" and outcome == "completed"
        else 0
    )
    worker_units = state.worker_weighted_units + worker_delta
    architect_cycles = state.architect_completed_admission_cycles + architect_delta

    reason: str | None = None
    if outcome == "session_incompatibility":
        reason = "session_incompatibility"
    elif outcome == "identity_failure":
        reason = "identity_failure"
    elif failure_streak >= 2:
        reason = "consecutive_provider_output_failures"
    elif context_percent is not None and context_percent >= CONTEXT_WINDOW_RETIRE_PERCENT:
        reason = "known_context_window_threshold"
    elif latency_streak >= LATENCY_RETIRE_SAMPLE_COUNT:
        reason = "sustained_comparable_latency"
    elif (
        state.session_class == "worker"
        and worker_units >= WORKER_WEIGHTED_UNIT_LIMIT
    ):
        reason = "worker_weighted_unit_limit"
    elif (
        state.session_class == "architect"
        and architect_cycles >= ARCHITECT_COMPLETED_CYCLE_LIMIT
    ):
        reason = "architect_completed_cycle_limit"

    # This single immutable transition is the assignment boundary. Constructing
    # an intermediate available state at a reached threshold would briefly make
    # an already-exhausted session appear reusable.
    after = replace(
        state,
        phase="retired" if reason is not None else "between_assignments",
        sequence=state.sequence + 1,
        completed_assignments=state.completed_assignments + 1,
        worker_weighted_units=worker_units,
        architect_completed_admission_cycles=architect_cycles,
        consecutive_provider_output_failures=failure_streak,
        latency_comparison_key=latency_key,
        latency_baseline_milliseconds=latency_baseline,
        latency_degraded_sample_count=latency_streak,
        known_context_window_percent=context_percent,
        active_assignment_id=None,
        active_workload_class=None,
        active_weighted_units=0,
        retirement_reason=reason,
    )
    budget_delta = worker_delta if state.session_class == "worker" else architect_delta
    return SessionLifecycleTransition(
        after,
        _telemetry(
            state,
            after,
            event="assignment_completed",
            assignment_id=assignment_id,
            workload_class=state.active_workload_class,
            outcome=outcome,
            budget_delta=budget_delta,
            context_percent=context_percent,
            latency_sample=latency_sample,
        ),
    )


def observe_between_assignments(
    state: SessionLifecycleState,
    *,
    observation: str,
    known_context_window_percent: int | None = None,
) -> SessionLifecycleTransition:
    """Record a zero-budget idle/wait observation or an explicit retirement signal."""

    state = _require_state(state)
    if state.phase != "between_assignments":
        raise SessionLifecycleError(
            "between-assignment observations cannot interrupt an assignment"
        )
    if type(observation) is not str or observation not in BETWEEN_ASSIGNMENT_OBSERVATIONS:
        raise SessionLifecycleError("between-assignment observation is unsupported")
    context_percent = _optional_percent(
        known_context_window_percent,
        field="known_context_window_percent",
    )
    next_sequence = state.sequence + 1
    reason: str | None = None
    if observation == "session_incompatibility":
        reason = "session_incompatibility"
    elif observation == "identity_failure":
        reason = "identity_failure"
    elif context_percent is not None and context_percent >= CONTEXT_WINDOW_RETIRE_PERCENT:
        reason = "known_context_window_threshold"
    if reason is None:
        after = replace(
            state,
            sequence=next_sequence,
            known_context_window_percent=context_percent,
        )
    else:
        after = _retire(
            state,
            reason,
            sequence=next_sequence,
            known_context_window_percent=context_percent,
        )
    event = {
        "idle": "idle_observed",
        "waiting": "waiting_observed",
        "session_incompatibility": "session_incompatibility_observed",
        "identity_failure": "identity_failure_observed",
    }[observation]
    return SessionLifecycleTransition(
        after,
        _telemetry(
            state,
            after,
            event=event,
            assignment_id=None,
            workload_class=None,
            outcome=None,
            budget_delta=0,
            context_percent=context_percent,
            latency_sample=None,
        ),
    )


__all__ = [
    "ARCHITECT_COMPLETED_CYCLE_LIMIT",
    "ASSIGNMENT_OUTCOMES",
    "BETWEEN_ASSIGNMENT_OBSERVATIONS",
    "CONTEXT_WINDOW_RETIRE_PERCENT",
    "LATENCY_RETIRE_MULTIPLIER",
    "LATENCY_RETIRE_SAMPLE_COUNT",
    "RETIREMENT_REASONS",
    "SESSION_CLASSES",
    "SESSION_LIFECYCLE_SCHEMA_VERSION",
    "SESSION_PHASES",
    "WORKER_WEIGHTS",
    "WORKER_WEIGHTED_UNIT_LIMIT",
    "WORKLOAD_CLASSES",
    "LatencySample",
    "SessionLifecycleError",
    "SessionLifecycleState",
    "SessionLifecycleTelemetry",
    "SessionLifecycleTransition",
    "finish_assignment",
    "observe_between_assignments",
    "start_assignment",
]
