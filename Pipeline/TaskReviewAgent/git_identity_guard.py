"""Prevent automated commits from being attributed to unrelated GitHub users.

GitHub associates command-line commits with accounts by commit email. An invented
``<name>@users.noreply.github.com`` address can therefore impersonate a real
GitHub username. Automated No Safe Circle commits use a reserved ``.invalid``
address instead, and the guard rejects GitHub user noreply addresses supplied by
environment configuration.
"""

from __future__ import annotations

import os
from typing import Any


DEFAULT_AGENT_GIT_NAME = "No Safe Circle TaskReviewAgent"
DEFAULT_AGENT_GIT_EMAIL = "task-review-agent@nosafecircle.invalid"
_GITHUB_USER_NOREPLY_DOMAIN = "users." + "noreply.github.com"
_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}


class GitIdentityGuardError(RuntimeError):
    """Raised when an automated commit identity could map to a GitHub user."""


def validated_agent_git_identity() -> tuple[str, str]:
    """Return the deterministic automation identity or fail closed.

    The ``users.noreply.github.com`` namespace belongs to GitHub accounts. It is
    never a safe namespace for invented automation identities, even when a
    friendly display name is used.
    """

    name = os.getenv("NSC_AGENT_GIT_NAME", DEFAULT_AGENT_GIT_NAME).strip()
    email = os.getenv("NSC_AGENT_GIT_EMAIL", DEFAULT_AGENT_GIT_EMAIL).strip()

    if not name:
        raise GitIdentityGuardError("NSC_AGENT_GIT_NAME must be non-empty")
    if (
        not email
        or email.count("@") != 1
        or any(character.isspace() for character in email)
    ):
        raise GitIdentityGuardError("NSC_AGENT_GIT_EMAIL must be one valid-looking address")

    local, domain = email.rsplit("@", 1)
    if not local or not domain:
        raise GitIdentityGuardError("NSC_AGENT_GIT_EMAIL must include local and domain parts")
    if domain.casefold() == _GITHUB_USER_NOREPLY_DOMAIN.casefold():
        raise GitIdentityGuardError(
            "automated commits must not use the GitHub user noreply namespace; "
            "use a reserved .invalid automation address instead"
        )

    return name, email


def _configure_candidate_identity(self: Any) -> None:
    from .candidate_integration import _git

    name, email = validated_agent_git_identity()
    # Always replace checkout-local identity. An inherited/stale Git config may
    # itself contain an account-attributable address from an older automation.
    _git(self.checkout, "config", "user.name", name)
    _git(self.checkout, "config", "user.email", email)


def _configure_downstream_identity(self: Any) -> None:
    from .downstream_pipeline import _git

    name, email = validated_agent_git_identity()
    _git(self.command_runner, self.checkout, "config", "user.name", name)
    _git(self.command_runner, self.checkout, "config", "user.email", email)


def install_git_identity_guard() -> None:
    """Install the identity guard on every TaskReviewAgent commit path."""

    global _INSTALLED
    if _INSTALLED:
        return

    from .candidate_integration import CandidateIntegrator
    from .downstream_pipeline import DownstreamTaskController

    _ORIGINALS["candidate_ensure_git_identity"] = CandidateIntegrator._ensure_git_identity
    _ORIGINALS["downstream_ensure_git_identity"] = DownstreamTaskController._ensure_git_identity

    CandidateIntegrator._ensure_git_identity = _configure_candidate_identity
    DownstreamTaskController._ensure_git_identity = _configure_downstream_identity
    _INSTALLED = True


__all__ = [
    "DEFAULT_AGENT_GIT_EMAIL",
    "DEFAULT_AGENT_GIT_NAME",
    "GitIdentityGuardError",
    "install_git_identity_guard",
    "validated_agent_git_identity",
]
