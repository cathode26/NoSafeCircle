"""Committed authorization policy for GitHub Issue and comment authors.

The repository is public, so any GitHub account can open Issues and post
comments. Workflow authority must therefore never be derived from Issue or
comment *content* alone. This module owns the committed allow-list of logins
that may carry workflow authority and the deterministic extraction of an
author login from the payload shapes the backends actually return:

- ``gh issue list``/``gh issue view`` (GraphQL-backed) return
  ``{"author": {"login": ...}}`` and report GitHub App bots without the
  ``[bot]`` suffix (``github-actions``);
- the GitHub REST API returns ``{"user": {"login": ...}}`` and reports the
  same bot as ``github-actions[bot]``.

Login comparison is case-insensitive and otherwise EXACT. A ``[bot]`` suffix
is never stripped: ``cathode26[bot]`` and ``cathode26`` are different GitHub
accounts, and human authorization must never be obtainable by removing a bot
suffix. When one automation appears under both payload spellings, the
committed policy lists both spellings as explicit automation aliases.
A missing author is never treated as authorized.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from .contracts import TaskReviewContractError

ACTOR_POLICY_SCHEMA_VERSION = "1.0"
DEFAULT_ACTOR_POLICY_PATH = Path(__file__).resolve().parent / "actor_policy.json"


class ActorPolicyError(TaskReviewContractError):
    """Raised when the committed actor policy is missing or invalid."""


def normalize_login(login: str) -> str:
    """Fold case only. The login is otherwise compared exactly.

    ``cathode26[bot]`` must never normalize to ``cathode26``: they are
    different GitHub identities, and deriving a human identity from a bot
    identity would let an attacker-controllable bot name obtain human
    authority. Automation spellings that differ between payloads (for
    example ``github-actions`` vs ``github-actions[bot]``) are handled by
    listing both as explicit aliases in the committed policy.
    """

    return login.strip().casefold()


def actor_login(payload: Any) -> str | None:
    """Extract the author login from an Issue or comment payload.

    Supports the gh CLI shape (``author.login``) and the GitHub REST shape
    (``user.login``). Returns ``None`` when no author identity is present;
    callers must fail closed on ``None``.
    """

    if not isinstance(payload, Mapping):
        return None
    for key in ("author", "user"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            login = value.get("login")
            if isinstance(login, str) and login.strip():
                return login.strip()
    return None


@dataclass(frozen=True)
class ActorPolicy:
    schema_version: str
    authorized_human_logins: frozenset[str]
    authorized_automation_logins: frozenset[str]

    def is_authorized_human(self, login: Any) -> bool:
        return (
            isinstance(login, str)
            and normalize_login(login) in self.authorized_human_logins
        )

    def is_authorized_automation(self, login: Any) -> bool:
        return (
            isinstance(login, str)
            and normalize_login(login) in self.authorized_automation_logins
        )

    def is_authorized_actor(self, login: Any) -> bool:
        return self.is_authorized_human(login) or self.is_authorized_automation(login)


def _login_set(value: Any, *, field: str) -> frozenset[str]:
    if not isinstance(value, list) or not value:
        raise ActorPolicyError(f"actor policy {field} must be a non-empty array")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ActorPolicyError(f"actor policy {field} entries must be strings")
        identity = normalize_login(item)
        if not identity:
            raise ActorPolicyError(
                f"actor policy {field} contains an empty identity: {item!r}"
            )
        if identity in normalized:
            raise ActorPolicyError(
                f"actor policy {field} contains duplicate identity {identity!r}"
            )
        normalized.append(identity)
    return frozenset(normalized)


def parse_actor_policy(value: Any) -> ActorPolicy:
    if not isinstance(value, Mapping):
        raise ActorPolicyError("actor policy must be a JSON object")
    expected = {
        "schema_version",
        "authorized_human_logins",
        "authorized_automation_logins",
    }
    if set(value) != expected:
        raise ActorPolicyError(
            f"actor policy keys mismatch; missing={sorted(expected - set(value))}, "
            f"extras={sorted(set(value) - expected)}"
        )
    if value.get("schema_version") != ACTOR_POLICY_SCHEMA_VERSION:
        raise ActorPolicyError("unsupported actor policy schema_version")
    humans = _login_set(value.get("authorized_human_logins"), field="authorized_human_logins")
    automation = _login_set(
        value.get("authorized_automation_logins"),
        field="authorized_automation_logins",
    )
    overlap = humans & automation
    if overlap:
        raise ActorPolicyError(
            f"actor policy logins cannot be both human and automation: {sorted(overlap)}"
        )
    return ActorPolicy(
        schema_version=ACTOR_POLICY_SCHEMA_VERSION,
        authorized_human_logins=humans,
        authorized_automation_logins=automation,
    )


def load_actor_policy(path: Path | str = DEFAULT_ACTOR_POLICY_PATH) -> ActorPolicy:
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ActorPolicyError(f"actor policy file is unreadable: {path}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ActorPolicyError(f"actor policy file is not valid JSON: {path}") from exc
    return parse_actor_policy(value)


@lru_cache(maxsize=1)
def default_actor_policy() -> ActorPolicy:
    return load_actor_policy(DEFAULT_ACTOR_POLICY_PATH)


__all__ = [
    "ACTOR_POLICY_SCHEMA_VERSION",
    "ActorPolicy",
    "ActorPolicyError",
    "DEFAULT_ACTOR_POLICY_PATH",
    "actor_login",
    "default_actor_policy",
    "load_actor_policy",
    "normalize_login",
    "parse_actor_policy",
]
