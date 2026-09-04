"""Durable lifecycle owner for one reusable polling-architect conversation.

The owner decorates the existing architect-runner callable.  It owns no task
selection, worker process, scheduler state, or provider implementation.  One
paid architect call is one ``admission_cycle`` assignment; scheduler waits that
never invoke this object therefore consume no lifecycle budget.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping
import uuid

from Pipeline.AgentRuntime.provider_sessions import (
    PROVIDER_SESSION_SCHEMA_VERSION,
    ProviderSessionBinding,
    ProviderSessionConfirmation,
    validate_session_id,
)
from Pipeline.AgentRuntime.session_lifecycle import (
    ASSIGNMENT_OUTCOMES,
    SessionLifecycleError,
    SessionLifecycleState,
    SessionLifecycleTelemetry,
    SessionLifecycleTransition,
    finish_assignment,
    observe_between_assignments,
    start_assignment,
)


ARCHITECT_SESSION_JOURNAL_SCHEMA_VERSION = "1.0"
ARCHITECT_SESSION_COMPATIBILITY_SCHEMA_VERSION = "1.0"
ARCHITECT_SESSION_ROLE = "polling_architect"


class ArchitectSessionOwnerError(RuntimeError):
    """The architect conversation cannot be started, resumed, or accounted safely."""


class ArchitectSessionIdentityError(ArchitectSessionOwnerError):
    """A paid call did not prove the exact provider conversation it was given."""


class ArchitectSessionCompatibilityError(ArchitectSessionOwnerError):
    """A session's provider execution contract is not exactly reusable."""


@dataclass(frozen=True)
class ArchitectSessionCompatibility:
    """Exact provider/model/protocol identity required to resume a session."""

    provider_identifier: str
    role: str
    model: str
    reasoning_effort: str | None
    protocol: str
    capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in ("provider_identifier", "role", "model", "protocol"):
            value = getattr(self, field_name)
            if type(value) is not str or not value or value != value.strip():
                raise ArchitectSessionOwnerError(
                    f"architect compatibility {field_name} must be exact non-empty text"
                )
        if self.reasoning_effort is not None and (
            type(self.reasoning_effort) is not str
            or not self.reasoning_effort
            or self.reasoning_effort != self.reasoning_effort.strip()
        ):
            raise ArchitectSessionOwnerError(
                "architect compatibility reasoning_effort must be null or exact text"
            )
        if (
            type(self.capabilities) is not tuple
            or not self.capabilities
            or any(type(item) is not str or not item for item in self.capabilities)
            or tuple(sorted(set(self.capabilities))) != self.capabilities
        ):
            raise ArchitectSessionOwnerError(
                "architect compatibility capabilities must be a sorted unique tuple"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ARCHITECT_SESSION_COMPATIBILITY_SCHEMA_VERSION,
            "provider_identifier": self.provider_identifier,
            "role": self.role,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "protocol": self.protocol,
            "capabilities": list(self.capabilities),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ArchitectSessionCompatibility":
        expected = {
            "schema_version",
            "provider_identifier",
            "role",
            "model",
            "reasoning_effort",
            "protocol",
            "capabilities",
        }
        if type(value) is not dict or set(value) != expected:
            raise ArchitectSessionOwnerError(
                "architect session compatibility fields differ from schema"
            )
        if value["schema_version"] != ARCHITECT_SESSION_COMPATIBILITY_SCHEMA_VERSION:
            raise ArchitectSessionOwnerError(
                "architect session compatibility schema is unsupported"
            )
        capabilities = value["capabilities"]
        if type(capabilities) is not list:
            raise ArchitectSessionOwnerError(
                "architect compatibility capabilities must be an array"
            )
        return cls(
            value["provider_identifier"],
            value["role"],
            value["model"],
            value["reasoning_effort"],
            value["protocol"],
            tuple(capabilities),
        )


@dataclass(frozen=True)
class ArchitectSessionInvocationError(RuntimeError):
    """Typed provider failure transported across the Docker architect boundary."""

    lifecycle_outcome: str
    failure_classification: str
    confirmed_session_id: str | None
    detail: str

    def __post_init__(self) -> None:
        if self.lifecycle_outcome not in ASSIGNMENT_OUTCOMES - {"completed", "waiting", "idle"}:
            raise ArchitectSessionOwnerError("architect failure lifecycle outcome is unsupported")
        if type(self.failure_classification) is not str or not self.failure_classification:
            raise ArchitectSessionOwnerError("architect failure classification must be non-empty")
        if self.confirmed_session_id is not None:
            object.__setattr__(
                self,
                "confirmed_session_id",
                validate_session_id(self.confirmed_session_id),
            )
        if type(self.detail) is not str or not self.detail.strip():
            raise ArchitectSessionOwnerError("architect failure detail must be non-empty")
        RuntimeError.__init__(self, self.detail)


def provider_session_confirmation_from_dict(value: Any) -> ProviderSessionConfirmation:
    """Decode one exact provider-session confirmation without accepting extras."""

    if type(value) is not dict:
        raise ArchitectSessionOwnerError("provider session confirmation must be an exact object")
    expected = {
        "schema_version",
        "provider_identifier",
        "role",
        "mode",
        "session_id",
    }
    if set(value) != expected:
        raise ArchitectSessionOwnerError("provider session confirmation fields differ from schema")
    if value["schema_version"] != PROVIDER_SESSION_SCHEMA_VERSION:
        raise ArchitectSessionOwnerError("provider session confirmation schema is unsupported")
    try:
        return ProviderSessionConfirmation(
            value["provider_identifier"],
            value["role"],
            value["mode"],
            value["session_id"],
        )
    except ValueError as exc:
        raise ArchitectSessionOwnerError(str(exc)) from exc


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(_canonical_json(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class JsonArchitectSessionStore:
    """Exact current state plus an append-only, fsynced transition journal."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.state_path = self.root / "state.json"
        self.compatibility_path = self.root / "compatibility.json"
        self.telemetry_path = self.root / "telemetry.jsonl"

    def load_compatibility(self) -> ArchitectSessionCompatibility | None:
        if not self.compatibility_path.exists():
            return None
        try:
            return ArchitectSessionCompatibility.from_dict(
                json.loads(self.compatibility_path.read_text(encoding="utf-8"))
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ArchitectSessionOwnerError(
                "architect session compatibility is unreadable or invalid: "
                f"{self.compatibility_path}"
            ) from exc

    def load(self) -> SessionLifecycleState | None:
        if not self.state_path.exists():
            if self.telemetry_path.exists():
                raise ArchitectSessionOwnerError(
                    "architect lifecycle telemetry exists without current state: "
                    f"{self.telemetry_path}"
                )
            return None
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            state = SessionLifecycleState.from_dict(value)
            if not self.telemetry_path.exists():
                return state
            lines = self.telemetry_path.read_text(encoding="utf-8").splitlines()
            if not lines:
                raise ArchitectSessionOwnerError(
                    "architect lifecycle telemetry is unexpectedly empty"
                )
            last_state: SessionLifecycleState | None = None
            for line in lines:
                record = json.loads(line)
                if type(record) is not dict or set(record) != {
                    "schema_version",
                    "state",
                    "telemetry",
                }:
                    raise ArchitectSessionOwnerError(
                        "architect lifecycle telemetry record differs from schema"
                    )
                if record["schema_version"] != ARCHITECT_SESSION_JOURNAL_SCHEMA_VERSION:
                    raise ArchitectSessionOwnerError(
                        "architect lifecycle telemetry schema is unsupported"
                    )
                recorded_state = SessionLifecycleState.from_dict(record["state"])
                telemetry = SessionLifecycleTelemetry.from_dict(record["telemetry"])
                if (
                    recorded_state.provider_identifier != telemetry.provider_identifier
                    or recorded_state.role != telemetry.role
                    or recorded_state.session_id != telemetry.session_id
                    or recorded_state.session_class != telemetry.session_class
                    or recorded_state.sequence != telemetry.sequence
                    or recorded_state.phase != telemetry.phase_after
                ):
                    raise ArchitectSessionOwnerError(
                        "architect lifecycle telemetry does not bind its resulting state"
                    )
                if last_state is not None:
                    same_session = (
                        last_state.provider_identifier == recorded_state.provider_identifier
                        and last_state.role == recorded_state.role
                        and last_state.session_id == recorded_state.session_id
                    )
                    if same_session and (
                        recorded_state.sequence != last_state.sequence + 1
                        or telemetry.phase_before != last_state.phase
                    ):
                        raise ArchitectSessionOwnerError(
                            "architect lifecycle telemetry sequence or phase continuity is broken"
                        )
                    if not same_session and (
                        last_state.phase != "retired"
                        or recorded_state.sequence != 1
                        or telemetry.phase_before != "between_assignments"
                    ):
                        raise ArchitectSessionOwnerError(
                            "architect lifecycle telemetry changed sessions without retirement"
                        )
                last_state = recorded_state
            if last_state != state and state.sequence != 0:
                raise ArchitectSessionOwnerError(
                    "architect lifecycle current state is not the journal tail"
                )
            return state
        except (OSError, UnicodeError, json.JSONDecodeError, SessionLifecycleError) as exc:
            raise ArchitectSessionOwnerError(
                f"architect lifecycle state is unreadable or invalid: {self.state_path}"
            ) from exc

    def save_initial(
        self,
        state: SessionLifecycleState,
        compatibility: ArchitectSessionCompatibility,
    ) -> None:
        if type(state) is not SessionLifecycleState:
            raise ArchitectSessionOwnerError("initial lifecycle state must be exact")
        if type(compatibility) is not ArchitectSessionCompatibility:
            raise ArchitectSessionOwnerError("initial compatibility must be exact")
        _atomic_write_json(self.compatibility_path, compatibility.to_dict())
        _atomic_write_json(self.state_path, state.to_dict())

    def record(self, transition: SessionLifecycleTransition) -> None:
        if type(transition) is not SessionLifecycleTransition:
            raise ArchitectSessionOwnerError("lifecycle transition must be exact")
        self.root.mkdir(parents=True, exist_ok=True)
        record = {
            "schema_version": ARCHITECT_SESSION_JOURNAL_SCHEMA_VERSION,
            "state": transition.state.to_dict(),
            "telemetry": transition.telemetry.to_dict(),
        }
        line = _canonical_json(record) + "\n"
        try:
            # State is the recovery authority. Persist it first so interruption
            # can only strand an exact ``assigned`` state (which the owner
            # blocks), never leave a journaled assignment with reusable stale
            # between-assignment state.
            _atomic_write_json(self.state_path, transition.state.to_dict())
            with self.telemetry_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise ArchitectSessionOwnerError(
                f"architect lifecycle transition could not be persisted: {self.root}"
            ) from exc


class ArchitectSessionOwner:
    """Lifecycle-aware callable that preserves the surrounding scheduler object."""

    def __init__(
        self,
        *,
        architect_runner: Callable[..., Any],
        provider_identifier: str,
        role: str,
        store: JsonArchitectSessionStore,
        compatibility: ArchitectSessionCompatibility,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if not callable(architect_runner):
            raise ArchitectSessionOwnerError("architect_runner must be callable")
        if type(store) is not JsonArchitectSessionStore:
            raise ArchitectSessionOwnerError("store must be an exact JsonArchitectSessionStore")
        if type(compatibility) is not ArchitectSessionCompatibility:
            raise ArchitectSessionOwnerError("compatibility must be exact")
        self.architect_runner = architect_runner
        self.provider_identifier = provider_identifier
        self.role = role
        self.store = store
        self.compatibility = compatibility
        if (
            compatibility.provider_identifier != provider_identifier
            or compatibility.role != role
        ):
            raise ArchitectSessionOwnerError(
                "architect compatibility provider/role differs from owner identity"
            )
        self.session_id_factory = session_id_factory or (lambda: str(uuid.uuid4()))
        self.poisoned = False
        if not callable(self.session_id_factory):
            raise ArchitectSessionOwnerError("session_id_factory must be callable")
        self.state = self.store.load()
        stored_compatibility = self.store.load_compatibility()
        if self.state is not None:
            if (
                self.state.provider_identifier != self.provider_identifier
                or self.state.role != self.role
                or self.state.session_class != "architect"
            ):
                raise ArchitectSessionOwnerError(
                    "persisted architect lifecycle identity differs from this owner"
                )
            if self.state.phase == "assigned":
                raise ArchitectSessionOwnerError(
                    "persisted architect session is assigned; explicit reconciliation is required"
                )
            if stored_compatibility is None:
                raise ArchitectSessionOwnerError(
                    "persisted architect lifecycle state has no compatibility identity"
                )
            if stored_compatibility != self.compatibility and self.state.phase != "retired":
                try:
                    retired = observe_between_assignments(
                        self.state,
                        observation="session_incompatibility",
                    )
                    self.store.record(retired)
                    self.state = retired.state
                except (ArchitectSessionOwnerError, SessionLifecycleError, OSError) as exc:
                    self.poisoned = True
                    raise ArchitectSessionOwnerError(
                        "architect compatibility mismatch could not be retired durably"
                    ) from exc
        elif stored_compatibility is not None:
            raise ArchitectSessionOwnerError(
                "architect compatibility exists without lifecycle state"
            )

    def _create_state(self) -> SessionLifecycleState:
        if self.provider_identifier == "openai-codex":
            raise ArchitectSessionOwnerError(
                "fresh Codex pooling cannot call start_assignment before the paid call: "
                "Codex assigns its exact session UUID only after start; resuming also remains "
                "subject to the provider adapter's verified sandbox-policy guard"
            )
        if self.provider_identifier != "claude-code":
            raise ArchitectSessionOwnerError("architect session provider is unsupported")
        try:
            session_id = validate_session_id(self.session_id_factory())
            state = SessionLifecycleState.create(
                provider_identifier=self.provider_identifier,
                role=self.role,
                session_id=session_id,
                session_class="architect",
            )
        except (ValueError, SessionLifecycleError) as exc:
            raise ArchitectSessionOwnerError(str(exc)) from exc
        self.store.save_initial(state, self.compatibility)
        self.state = state
        return state

    def _available_state(self) -> SessionLifecycleState:
        if self.poisoned:
            raise ArchitectSessionOwnerError(
                "architect session owner is poisoned after a persistence failure"
            )
        state = self.state
        if state is None or state.phase == "retired":
            state = self._create_state()
        if state.phase == "assigned":
            raise ArchitectSessionOwnerError(
                "architect session is assigned; explicit reconciliation is required"
            )
        if state.phase != "between_assignments":
            raise ArchitectSessionOwnerError("architect lifecycle phase is unsupported")
        return state

    @staticmethod
    def _context_percent(metadata: Mapping[str, Any]) -> int | None:
        if "known_context_window_percent" not in metadata:
            return None
        value = metadata["known_context_window_percent"]
        if type(value) is not int or not 0 <= value <= 100:
            raise ArchitectSessionOwnerError(
                "known_context_window_percent must be an explicit integer in 0..100"
            )
        return value

    def _confirm(
        self,
        metadata: Mapping[str, Any],
        binding: ProviderSessionBinding,
    ) -> ProviderSessionConfirmation:
        if "provider_session_confirmation" not in metadata:
            raise ArchitectSessionIdentityError(
                "successful architect call omitted exact provider session confirmation"
            )
        try:
            confirmation = provider_session_confirmation_from_dict(
                metadata["provider_session_confirmation"]
            )
        except ArchitectSessionOwnerError as exc:
            raise ArchitectSessionIdentityError(str(exc)) from exc
        if (
            confirmation.provider_identifier != self.provider_identifier
            or confirmation.role != self.role
            or confirmation.mode != binding.mode
            or confirmation.session_id != binding.session_id
        ):
            raise ArchitectSessionIdentityError(
                "successful architect call returned a mismatched provider session confirmation"
            )
        try:
            observed_compatibility = ArchitectSessionCompatibility.from_dict(
                metadata.get("provider_session_compatibility")
            )
        except ArchitectSessionOwnerError as exc:
            raise ArchitectSessionCompatibilityError(str(exc)) from exc
        if observed_compatibility != self.compatibility:
            raise ArchitectSessionCompatibilityError(
                "architect call returned mismatched provider session compatibility"
            )
        return confirmation

    def __call__(self, **values: Any) -> Any:
        state = self._available_state()
        mode = "start" if state.sequence == 0 and state.completed_assignments == 0 else "resume"
        binding = ProviderSessionBinding(
            self.provider_identifier,
            self.role,
            mode,
            state.session_id,
        )
        assignment_id = f"architect-cycle-{state.sequence + 1}"
        try:
            started = start_assignment(
                state,
                assignment_id=assignment_id,
                workload_class="admission_cycle",
            )
            self.store.record(started)
            self.state = started.state
        except ArchitectSessionOwnerError:
            self.poisoned = True
            raise
        except (SessionLifecycleError, OSError) as exc:
            self.poisoned = True
            raise ArchitectSessionOwnerError(str(exc)) from exc

        try:
            result = self.architect_runner(session_binding=binding, **values)
            metadata = getattr(result, "invocation_metadata", None)
            if not isinstance(metadata, Mapping):
                raise ArchitectSessionIdentityError(
                    "architect result omitted invocation metadata"
                )
            self._confirm(metadata, binding)
            outcome = "completed"
            context_percent = self._context_percent(metadata)
        except ArchitectSessionIdentityError as exc:
            outcome = "identity_failure"
            context_percent = None
            failure = exc
            result = None
        except ArchitectSessionCompatibilityError as exc:
            outcome = "session_incompatibility"
            context_percent = None
            failure = exc
            result = None
        except ArchitectSessionInvocationError as exc:
            if exc.confirmed_session_id is not None and exc.confirmed_session_id != state.session_id:
                outcome = "identity_failure"
            else:
                outcome = exc.lifecycle_outcome
            context_percent = None
            failure: Exception | None = exc
            result = None
        except Exception as exc:
            outcome = "other_failure"
            context_percent = None
            failure = exc
            result = None
        else:
            failure = None

        try:
            finished = finish_assignment(
                self.state,
                assignment_id=assignment_id,
                outcome=outcome,
                known_context_window_percent=context_percent,
                # Comparable latency is deliberately disabled until an exact
                # caller-owned key and baseline are available.
                latency_sample=None,
            )
            self.store.record(finished)
            self.state = finished.state
        except ArchitectSessionOwnerError:
            self.poisoned = True
            raise
        except (SessionLifecycleError, OSError) as exc:
            self.poisoned = True
            raise ArchitectSessionOwnerError(str(exc)) from exc
        if failure is not None:
            raise failure
        return result


__all__ = [
    "ARCHITECT_SESSION_JOURNAL_SCHEMA_VERSION",
    "ARCHITECT_SESSION_COMPATIBILITY_SCHEMA_VERSION",
    "ARCHITECT_SESSION_ROLE",
    "ArchitectSessionCompatibility",
    "ArchitectSessionCompatibilityError",
    "ArchitectSessionIdentityError",
    "ArchitectSessionInvocationError",
    "ArchitectSessionOwner",
    "ArchitectSessionOwnerError",
    "JsonArchitectSessionStore",
    "provider_session_confirmation_from_dict",
]
