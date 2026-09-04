"""Provider-neutral, opt-in persistent-session substrate for pooled workers.

A pooled worker may return to the scheduler pool while its authenticated
provider conversation stays resumable. This module models only the identity and
compatibility of such a conversation. It is deliberately not a running
subprocess, a session store, a scheduler, or a pooling policy.

Three rules shape every value here.

Opt-in. A caller that supplies no binding keeps the historical ephemeral
behavior exactly. Nothing in this module changes an invocation that does not
name a session.

Whole-value identity. A session is named by one exact lowercase canonical
RFC 4122 UUID and nothing else. "Last session", a display name, a search term,
a thread name, a partial or uppercase ID, the nil UUID, and every other
ambiguous selector are rejected before a subprocess can be launched. The
provider CLIs accept such selectors; AgentRuntime must not.

Expiring authority. Resuming a conversation restores remembered context, never
remembered permission. Every invocation, including a resume, carries its own
repository root, model, output schema, capabilities, write boundaries, prompt,
and budgets, and :data:`RESUMED_AUTHORITY_NOTICE` states that inside the prompt
so the model cannot mistake recall for authorization.

Compatibility identity is provider plus role. A Claude conversation can never be
resumed through Codex, and an Implementer conversation can never be resumed as a
Validator, because both facts are bound into the key a future scheduler compares.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping


PROVIDER_SESSION_SCHEMA_VERSION = "1.0"
SESSION_MODES = frozenset({"start", "resume"})

# Conservative lowercase ASCII identifier, matching the shape AgentRuntime
# already requires of roles and provider configuration keys.
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*(?:-[a-z0-9_]+)*$")
# Exact lowercase canonical RFC 4122 textual form. Braced, URN, uppercase, and
# unhyphenated hexadecimal spellings are all refused rather than normalized:
# normalizing would silently accept a selector the caller did not verify.
_SESSION_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
# The nil UUID parses but names no conversation. It is a sentinel, so it is
# exactly the kind of ambiguous selector this module exists to reject.
_NIL_SESSION_ID = "00000000-0000-0000-0000-000000000000"

RESUMED_AUTHORITY_NOTICE = (
    "Resumed session authority notice: this is a new assignment in an existing "
    "conversation. Every task, file, path, and write permission granted by any "
    "previous assignment in this conversation has expired and no longer applies. "
    "Earlier instructions are recall only and grant no authority now. Only the "
    "repository root, model, output schema, capabilities, allowed and denied "
    "write paths, task instructions, and budgets stated in this invocation apply. "
    "Do not act on a remembered task, reuse a remembered write path, or continue "
    "unfinished earlier work unless this invocation asks for it."
)


class ProviderSessionError(ValueError):
    """Raised when provider-session identity or compatibility fails closed."""


def validate_session_id(value: Any, *, field: str = "session_id") -> str:
    """Return one exact lowercase canonical UUID or fail closed.

    Whole-value only. The input must already be the exact canonical text; this
    never trims, lowercases, unwraps, or otherwise repairs an ambiguous value.
    """

    if type(value) is not str:
        raise ProviderSessionError(f"{field} must be a string")
    if not value:
        raise ProviderSessionError(f"{field} must not be empty")
    if _SESSION_ID.fullmatch(value) is None:
        raise ProviderSessionError(
            f"{field} must be one exact lowercase canonical UUID; "
            "'last', a display name, a thread name, a search term, a braced or "
            "URN form, and a partial ID are never accepted"
        )
    if value == _NIL_SESSION_ID:
        raise ProviderSessionError(f"{field} must not be the nil UUID sentinel")
    return value


def validate_session_mode(value: Any, *, field: str = "mode") -> str:
    if type(value) is not str or value not in SESSION_MODES:
        raise ProviderSessionError(
            f"{field} must be exactly 'start' or 'resume'"
        )
    return value


def _identifier(value: Any, *, field: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise ProviderSessionError(
            f"{field} must be one conservative lowercase identifier"
        )
    return value


@dataclass(frozen=True)
class ProviderSessionBinding:
    """One opt-in request to start or resume an exact provider conversation.

    ``session_id`` is required to resume. Starting is provider-shaped: an
    adapter whose CLI accepts a caller-chosen ID requires one, and an adapter
    whose CLI assigns the ID itself requires ``None`` and reports the assigned
    value through :class:`ProviderSessionLedger`. The adapter enforces its own
    rule; this container only refuses a resume with no exact identity.
    """

    provider_identifier: str
    role: str
    mode: str
    session_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_identifier",
            _identifier(self.provider_identifier, field="provider_identifier"),
        )
        object.__setattr__(self, "role", _identifier(self.role, field="role"))
        object.__setattr__(self, "mode", validate_session_mode(self.mode))
        if self.session_id is not None:
            object.__setattr__(
                self, "session_id", validate_session_id(self.session_id)
            )
        elif self.mode == "resume":
            raise ProviderSessionError(
                "resuming requires an exact session_id; a provider-selected "
                "'most recent' session is never an acceptable resume target"
            )

    @property
    def is_resume(self) -> bool:
        return self.mode == "resume"

    def compatibility_key(self) -> str:
        """Return the exact provider/role identity a scheduler must match.

        A future pooling scheduler compares this before offering a live
        conversation to an assignment. Provider prevents a Claude session from
        being handed to Codex; role prevents an Implementer conversation from
        silently resuming as a Validator.
        """

        return f"{PROVIDER_SESSION_SCHEMA_VERSION}\n{self.provider_identifier}\n{self.role}"

    def confirm(self, observed_session_id: Any) -> "ProviderSessionConfirmation":
        """Bind the identity the provider transcript actually reported.

        A resume must observe exactly the requested ID. A start with a
        caller-chosen ID must observe that ID. A start with a provider-assigned
        ID adopts whatever exact UUID the transcript proved.
        """

        observed = validate_session_id(
            observed_session_id, field="observed session_id"
        )
        if self.session_id is not None and observed != self.session_id:
            raise ProviderSessionError(
                "provider transcript reported a different session identity than "
                "the invocation bound"
            )
        return ProviderSessionConfirmation(
            self.provider_identifier, self.role, self.mode, observed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROVIDER_SESSION_SCHEMA_VERSION,
            "provider_identifier": self.provider_identifier,
            "role": self.role,
            "mode": self.mode,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProviderSessionBinding":
        if not isinstance(value, Mapping):
            raise ProviderSessionError("provider session binding must be an object")
        expected = {"provider_identifier", "role", "mode", "session_id"}
        unknown = set(value) - (expected | {"schema_version"})
        missing = expected - set(value)
        if unknown:
            raise ProviderSessionError(
                f"unsupported provider session binding fields: {sorted(unknown)}"
            )
        if missing:
            raise ProviderSessionError(
                f"missing provider session binding fields: {sorted(missing)}"
            )
        version = value.get("schema_version", PROVIDER_SESSION_SCHEMA_VERSION)
        if version != PROVIDER_SESSION_SCHEMA_VERSION:
            raise ProviderSessionError(
                "unsupported provider session binding schema version"
            )
        return cls(
            value["provider_identifier"],
            value["role"],
            value["mode"],
            value["session_id"],
        )


@dataclass(frozen=True)
class ProviderSessionConfirmation:
    """The exact conversation identity a provider transcript actually proved."""

    provider_identifier: str
    role: str
    mode: str
    session_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_identifier",
            _identifier(self.provider_identifier, field="provider_identifier"),
        )
        object.__setattr__(self, "role", _identifier(self.role, field="role"))
        object.__setattr__(self, "mode", validate_session_mode(self.mode))
        object.__setattr__(
            self, "session_id", validate_session_id(self.session_id)
        )

    def compatibility_key(self) -> str:
        return f"{PROVIDER_SESSION_SCHEMA_VERSION}\n{self.provider_identifier}\n{self.role}"

    def resume_binding(self) -> ProviderSessionBinding:
        """Return the binding a later compatible assignment would resume with."""

        return ProviderSessionBinding(
            self.provider_identifier, self.role, "resume", self.session_id
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROVIDER_SESSION_SCHEMA_VERSION,
            "provider_identifier": self.provider_identifier,
            "role": self.role,
            "mode": self.mode,
            "session_id": self.session_id,
        }


class ProviderSessionLedger:
    """Write-once sink for the identity one invocation actually confirmed.

    The adapter records here instead of widening ``AgentProvider.invoke`` or the
    validated ``AgentResult`` contract, so an opt-in session leaves every
    existing request/result artifact byte-identical. One invocation confirms at
    most one identity; a second record is a contradiction and fails closed.
    """

    __slots__ = ("_confirmation",)

    def __init__(self) -> None:
        self._confirmation: ProviderSessionConfirmation | None = None

    @property
    def confirmed(self) -> ProviderSessionConfirmation | None:
        return self._confirmation

    def record(self, confirmation: ProviderSessionConfirmation) -> None:
        if type(confirmation) is not ProviderSessionConfirmation:
            raise ProviderSessionError(
                "ledger accepts only an exact ProviderSessionConfirmation"
            )
        if self._confirmation is not None:
            raise ProviderSessionError(
                "provider session ledger already recorded a confirmed identity"
            )
        self._confirmation = confirmation

    def to_dict(self) -> dict[str, Any] | None:
        return None if self._confirmation is None else self._confirmation.to_dict()


def require_compatible_binding(
    binding: Any,
    *,
    provider_identifier: str,
    role: str,
) -> ProviderSessionBinding:
    """Fail closed unless the binding matches this exact provider and role."""

    if type(binding) is not ProviderSessionBinding:
        raise ProviderSessionError(
            "provider session must be an exact ProviderSessionBinding"
        )
    if binding.provider_identifier != provider_identifier:
        raise ProviderSessionError(
            f"session was bound to provider {binding.provider_identifier!r} and "
            f"cannot be resumed through {provider_identifier!r}"
        )
    if binding.role != role:
        raise ProviderSessionError(
            f"session was bound to role {binding.role!r} and cannot be resumed "
            f"as role {role!r}"
        )
    return binding


def prompt_with_resumed_authority(prompt: str, binding: Any) -> str:
    """Prepend the expiring-authority notice to a resumed assignment prompt.

    The notice leads because a resumed conversation already holds remembered
    instructions; the revocation must be read before the new task.
    """

    if binding is None or not getattr(binding, "is_resume", False):
        return prompt
    return f"{RESUMED_AUTHORITY_NOTICE}\n\n{prompt}"


__all__ = [
    "PROVIDER_SESSION_SCHEMA_VERSION",
    "RESUMED_AUTHORITY_NOTICE",
    "SESSION_MODES",
    "ProviderSessionBinding",
    "ProviderSessionConfirmation",
    "ProviderSessionError",
    "ProviderSessionLedger",
    "prompt_with_resumed_authority",
    "require_compatible_binding",
    "validate_session_id",
    "validate_session_mode",
]
