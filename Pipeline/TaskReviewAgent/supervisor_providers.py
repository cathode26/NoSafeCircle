"""One registry of what each TaskReviewAgent goal-supervisor provider needs.

The supervisor was structurally pinned to Codex: the launcher demanded Codex in
every allowlist, the worker asserted Codex before any provider existed, and the
session scope named ``openai-codex`` unconditionally. That made a Claude-only
autonomous task impossible even when the architect and ExecutionCrew were both
Claude.

This module owns only the provider-shaped facts -- adapter identity, Compose
service, credential volume, turn entrypoint, and resume capability -- so every
boundary that must honour an explicit supervisor selection reads them from one
place instead of repeating a literal. It performs no provider, Docker, process,
repository, or network action.

The supervisor provider is deliberately independent of the software architect
provider, the ExecutionCrew route, and per-role validation or repair routes.
Choosing one here never chooses any of the others.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .provider_policy import (
    DEFAULT_SUPERVISOR_PROVIDER,
    SUPERVISOR_PROVIDERS,
    ProviderPolicyError,
    resolve_supervisor_provider,
)


class SupervisorProviderError(ProviderPolicyError):
    """The requested supervisor provider is unknown or unusable as configured."""


@dataclass(frozen=True)
class SupervisorProviderProfile:
    """Exactly what one supervisor provider needs, and nothing about the others."""

    #: The operator/runtime selector: ``claude`` or ``codex``.
    supervisor_provider: str
    #: The AgentRuntime adapter identity that binds session compatibility.
    provider_identifier: str
    #: The Docker Compose service that holds this provider's authenticated CLI.
    compose_service: str
    #: The repository-default credential volume this provider authenticates from.
    default_conversation_store_volume: str
    #: The environment variable an operator may use to name a different volume.
    conversation_store_environment: str
    #: The in-container entrypoint that runs one bounded supervisor turn.
    turn_entrypoint: str
    #: The key ``conversation_store_binding`` uses for this provider.
    conversation_store_key: str
    #: True when a resume needs an operator-verified argument before pooling may
    #: activate at all. Codex cannot reproduce its pinned sandbox policy on
    #: ``codex exec resume``; Claude resumes natively with ``--resume <uuid>``.
    resume_requires_verified_argument: bool
    #: The exact capability a resume relies on, recorded in durable evidence so
    #: a reader can tell which contract a pooled conversation was started under.
    resume_capability: str
    #: The committed repository default model for this provider. Both values are
    #: the ones ``execution_routing`` already commits to (``_DEFAULT_CLAUDE_MODEL``
    #: and ``_DEFAULT_OPENAI_MODEL``); neither is invented here.
    default_model: str
    #: That provider's own model environment variable, matching the pairing
    #: ``execution_routing.load_execution_routing_policy`` already uses.
    model_environment: str
    #: The prefix every model identifier for this provider must carry. Claude's
    #: adapter enforces the same prefix itself; naming it here lets a mismatch
    #: fail on the host instead of inside the container.
    model_prefix: str


_PROFILES: Mapping[str, SupervisorProviderProfile] = {
    "codex": SupervisorProviderProfile(
        supervisor_provider="codex",
        provider_identifier="openai-codex",
        compose_service="codex-supervisor",
        default_conversation_store_volume="nosafecircle_codex-config",
        conversation_store_environment="NSC_TASK_SUPERVISOR_CODEX_VOLUME",
        turn_entrypoint="Pipeline/TaskReviewAgent/codex_supervisor_turn.py",
        conversation_store_key="codex",
        resume_requires_verified_argument=True,
        resume_capability="codex-exec-resume-with-verified-sandbox-config",
        default_model="gpt-5.6-sol",
        model_environment="NSC_OPENAI_CODEX_MODEL",
        model_prefix="gpt-",
    ),
    "claude": SupervisorProviderProfile(
        supervisor_provider="claude",
        provider_identifier="claude-code",
        compose_service="claude-supervisor",
        default_conversation_store_volume="nosafecircle_claude-config",
        conversation_store_environment="NSC_TASK_SUPERVISOR_CLAUDE_VOLUME",
        turn_entrypoint="Pipeline/TaskReviewAgent/claude_supervisor_turn.py",
        conversation_store_key="claude",
        resume_requires_verified_argument=False,
        resume_capability="claude-native-resume-session-id",
        default_model="claude-sonnet-5",
        model_environment="NSC_CLAUDE_MODEL",
        model_prefix="claude-",
    ),
}

assert set(_PROFILES) == set(SUPERVISOR_PROVIDERS)


def supervisor_provider_profile(value: object = None) -> SupervisorProviderProfile:
    """Return the exact profile for one supervisor selection.

    ``None`` resolves to the historical Codex supervisor, so a caller or a
    persisted artifact that predates this selection is unchanged.
    """

    return _PROFILES[resolve_supervisor_provider(value)]


def supervisor_provider_identifier(value: object = None) -> str:
    """Return the AgentRuntime adapter identity a supervisor selection binds."""

    return supervisor_provider_profile(value).provider_identifier


def supervisor_provider_for_identifier(identifier: object) -> str:
    """Invert the adapter identity back to its operator-facing selector.

    A persisted session records the adapter identity, so reconciliation needs
    the exact inverse rather than a guess.
    """

    for profile in _PROFILES.values():
        if profile.provider_identifier == identifier:
            return profile.supervisor_provider
    raise SupervisorProviderError(
        f"no supervisor provider is known for adapter identity {identifier!r}"
    )


__all__ = [
    "DEFAULT_SUPERVISOR_PROVIDER",
    "SUPERVISOR_PROVIDERS",
    "SupervisorProviderError",
    "SupervisorProviderProfile",
    "supervisor_provider_for_identifier",
    "supervisor_provider_identifier",
    "supervisor_provider_profile",
]
