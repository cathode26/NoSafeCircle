"""Explicit host-owned provider restrictions, independent of model defaults."""

from __future__ import annotations


class ProviderPolicyError(ValueError):
    """A requested provider would escape the operator's permitted providers."""


def provider_allowlist(value: object) -> tuple[str, ...] | None:
    """Validate a canonical restriction; None preserves unrestricted legacy runs."""
    if value is None:
        return None
    if type(value) not in {list, tuple}:
        raise ProviderPolicyError("provider_allowlist must be a list or tuple")
    values = tuple(value)
    if not values or any(type(item) is not str or item not in {"claude", "codex"} for item in values):
        raise ProviderPolicyError("provider_allowlist must contain claude and/or codex")
    if values != tuple(sorted(set(values))):
        raise ProviderPolicyError("provider_allowlist must be sorted and duplicate-free")
    return values


def parse_provider_allowlist(value: str) -> tuple[str, ...]:
    result = provider_allowlist(value.split(","))
    assert result is not None
    return result


def require_permitted_provider(provider: str, permitted: tuple[str, ...] | None, *, role: str) -> None:
    permitted = provider_allowlist(permitted)
    if permitted is not None and provider not in permitted:
        raise ProviderPolicyError(f"{role} provider {provider!r} is not in provider_allowlist")
