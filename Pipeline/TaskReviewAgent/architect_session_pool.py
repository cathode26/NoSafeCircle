"""Adopt-on-confirm Codex architect ownership under the repository scheduler lock.

The durable lease exists before the first paid call, although Codex does not
name its conversation until its transcript confirms thread.started. Unknown
outcomes are never resumed. This uses the shared pool's identity, quarantine,
retirement and assignment accounting instead of inventing a conversation UUID.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping

from Pipeline.AgentRuntime.durable_session_pool import (
    DURABLE_SESSION_POOL_SCHEMA_VERSION,
    AssignmentSettlement,
    DurableSessionPoolStore,
    SessionLifetimePolicy,
    SessionScope,
)
from .architect_session_owner import (
    ARCHITECT_SESSION_ROLE,
    ArchitectSessionCompatibility,
    ArchitectSessionCompatibilityError,
    ArchitectSessionIdentityError,
    ArchitectSessionInvocationError,
    ArchitectSessionOwner,
    ArchitectSessionOwnerError,
    provider_session_confirmation_from_dict,
)
from .supervisor_session_pool import CodexResumeActivation, conversation_store_binding


ARCHITECT_POOL_LIFETIME = SessionLifetimePolicy(
    max_age_seconds=24 * 3600, idle_lifetime_seconds=4 * 3600,
)


@dataclass(frozen=True)
class ArchitectPoolRecovery:
    provider_identifier: str
    role: str
    session_id: str | None
    assignment_id: str
    retirement_reason: str


class CodexArchitectSessionOwner:
    """One durable architect assignment, owned by the exact scheduler lock.

    Loading and compatibility retirement happen only after acquiring that
    lock. Constructing a second owner cannot mutate the first owner's state.
    The checkpoint is authoritative; failed writes poison this object and an
    interrupted assigned checkpoint requires explicit locked reconciliation.
    """

    def __init__(
        self, *, architect_runner: Callable[..., Any],
        compatibility: ArchitectSessionCompatibility,
        source: Path | str, checkout_root: Path | str,
        repository_identity: str, compose_project: str,
        resume_activation: CodexResumeActivation,
        scheduler_lock_type: type, scheduler_lock_path: Path | str,
    ) -> None:
        if not callable(architect_runner):
            raise ArchitectSessionOwnerError("architect runner must be callable")
        if (
            type(compatibility) is not ArchitectSessionCompatibility
            or compatibility.provider_identifier != "openai-codex"
            or compatibility.role != ARCHITECT_SESSION_ROLE
        ):
            raise ArchitectSessionOwnerError("Codex architect compatibility is invalid")
        if type(resume_activation) is not CodexResumeActivation:
            raise ArchitectSessionOwnerError(
                "Codex architect pooling requires an explicit verified resume sandbox control"
            )
        self.architect_runner = architect_runner
        self.compatibility = compatibility
        self.source = Path(source).resolve()
        self.checkout_root = Path(checkout_root).resolve()
        self.resume_activation = resume_activation
        self.scheduler_lock_type = scheduler_lock_type
        self.scheduler_lock_path = Path(scheduler_lock_path).resolve()
        self.scope = SessionScope(
            protocol_version=compatibility.protocol,
            provider_identifier=compatibility.provider_identifier,
            role=compatibility.role, session_class="architect", workload_class="admission_cycle",
            model=compatibility.model, reasoning_effort=compatibility.reasoning_effort,
            repository_identity=repository_identity, resume_contract=resume_activation.fingerprint,
            bindings=(
                ("source_checkout", str(self.source)),
                ("capabilities", ",".join(compatibility.capabilities)),
                conversation_store_binding(compose_project, "codex"),
            ),
        )
        identity = hashlib.sha256(str(self.source).encode("utf-8")).hexdigest()
        self.store = DurableSessionPoolStore(
            self.checkout_root / ".task-review-agent" / "architect-sessions" / identity / "pool.json",
            lifetime=ARCHITECT_POOL_LIFETIME,
        )
        if self.store.path.is_relative_to(self.source):
            raise ArchitectSessionOwnerError("architect pool state must be outside its source checkout")
        self.pool = None
        self.lock = None
        self.poisoned = False

    def _require_lock(self) -> None:
        if (
            type(self.lock) is not self.scheduler_lock_type or not self.lock.is_held
            or self.lock.path.resolve() != self.scheduler_lock_path
        ):
            raise ArchitectSessionOwnerError("Codex architect requires its exact acquired scheduler lock")
        if self.poisoned:
            raise ArchitectSessionOwnerError("Codex architect owner is poisoned after a persistence failure")

    def _save(self) -> None:
        try:
            self.store.save(self.pool)
        except BaseException as exc:
            self.poisoned = True
            if not isinstance(exc, Exception):
                raise
            raise ArchitectSessionOwnerError("Codex architect checkpoint could not be persisted") from exc

    def reconcile_interrupted_assignment(self, *, lock: Any) -> ArchitectPoolRecovery | None:
        self.lock = lock
        self._require_lock()
        # A live owner may not call recovery to steal its own in-flight call.
        if self.pool is not None:
            raise ArchitectSessionOwnerError("Codex architect takeover may only initialize an owner once")
        self.pool = self.store.load()
        active = [item for item in self.pool.sessions if item.state == "active"]
        if len(active) > 1:
            raise ArchitectSessionOwnerError("architect checkpoint holds multiple active assignments")
        recovered = None
        for record in active:
            lease = record.active_lease
            settled = self.pool.retire_interrupted(
                lease, detail="exclusive repository scheduler lock acquired by replacement owner",
            )
            recovered = ArchitectPoolRecovery(
                record.scope.provider_identifier, record.scope.role, record.session_id,
                lease.assignment_id, settled.retirement_reason or "interrupted_assignment_quarantined",
            )
        for record in self.pool.sessions:
            if record.scope != self.scope and record.state in {"idle", "probation"}:
                self.pool.observe(record.record_id, observation="session_incompatibility")
        if active or any(record.scope != self.scope for record in self.pool.sessions):
            self._save()
        return recovered

    def __call__(self, **values: Any) -> Any:
        self._require_lock()
        if self.pool is None:
            raise ArchitectSessionOwnerError("Codex architect requires locked startup reconciliation")
        if self.pool.active_assignment_count:
            raise ArchitectSessionOwnerError("Codex architect assignment is already active")
        lease = self.pool.checkout(
            scope=self.scope,
            assignment={"source_head": values["source_head"], "scheduler_id": values["scheduler_id"]},
            exclusive=True,
            # A subsequent scheduler request may use the one probation turn
            # allowed by the shared lifecycle policy. This call never retries.
            allow_probation_retry=True,
        )
        self._save()  # No provider work may precede the durable exact lease.
        confirmation = None
        failure = None
        context = None
        outcome = "uncertain"
        try:
            result = self.architect_runner(session_binding=lease.binding(), **values)
            metadata = getattr(result, "invocation_metadata", None)
            if not isinstance(metadata, Mapping):
                raise ArchitectSessionIdentityError("architect result omitted invocation metadata")
            confirmation = provider_session_confirmation_from_dict(
                metadata.get("provider_session_confirmation")
            )
            # ProviderSessionBinding enforces exact provider/role/mode and
            # adopts a UUID only for a fresh provider-named conversation.
            expected = lease.binding().confirm(confirmation.session_id)
            if confirmation != expected:
                raise ArchitectSessionIdentityError("architect confirmation differs from its lease")
            if (
                ArchitectSessionCompatibility.from_dict(metadata.get("provider_session_compatibility"))
                != self.compatibility
                or metadata.get("provider_session_resume_contract") != self.scope.resume_contract
            ):
                raise ArchitectSessionCompatibilityError("architect invocation compatibility differs from its lease")
            context = ArchitectSessionOwner._context_percent(metadata)
            outcome = "completed"
        except ArchitectSessionCompatibilityError as exc:
            outcome, failure = "session_incompatibility", exc
        except (ArchitectSessionOwnerError, ValueError) as exc:
            outcome, failure = "identity_failure", exc
        except ArchitectSessionInvocationError as exc:
            failure = exc
            # Timeout/transport uncertainty cannot prove the assignment ended.
            # Other typed failures include the transcript-confirmed identity
            # from the same pinned host transport. Count those through the
            # shared two-failure budget, with no retry inside this call.
            if exc.confirmed_session_id is None or exc.failure_classification in {"timeout", "transport_error"}:
                outcome = "uncertain"
            else:
                try:
                    confirmation = lease.binding().confirm(exc.confirmed_session_id)
                    outcome = exc.lifecycle_outcome
                except ValueError:
                    outcome = "identity_failure"
        except Exception as exc:
            outcome, failure = "uncertain", exc
        settled = self.pool.check_in(
            lease=lease,
            settlement=AssignmentSettlement(
                pool_schema_version=DURABLE_SESSION_POOL_SCHEMA_VERSION,
                lease_id=lease.lease_id, record_id=lease.record_id,
                outcome=outcome, confirmed_session=confirmation,
                known_context_window_percent=context,
                evidence=(), detail="" if failure is None else str(failure),
            ),
        )
        self._save()
        if failure is not None:
            raise failure
        if settled.state not in {"idle", "retired"} or settled.session_id != confirmation.session_id:
            raise ArchitectSessionIdentityError("architect conversation was quarantined at settlement")
        return result
