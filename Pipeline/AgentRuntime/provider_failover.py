"""Explicit account-quota handoff policy; no transport retries or text heuristics."""

from __future__ import annotations

from typing import Any, Mapping


QUOTA_ERROR_CODES = frozenset({"quota_exhausted", "insufficient_quota", "usage_limit_exceeded"})
ACCOUNT_USAGE_WINDOWS = frozenset({"five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet", "extra_usage"})


def claude_quota_evidence(events: tuple[Mapping[str, Any], ...]) -> str | None:
    """Inspect an already strictly parsed, completed Claude event stream.

    A warning, HTTP 429, free-form error message, local max-turn limit, or
    malformed/contradictory terminal result cannot authorize another provider.
    Unknown transcript layouts fail closed and remain ordinary provider errors.
    """
    if not events:
        return None
    terminal = events[-1]
    if (terminal.get("type") != "result" or terminal.get("is_error") is not True
            or terminal.get("subtype") != "error_during_execution"
            or ("terminal_reason" in terminal and terminal["terminal_reason"] != "error")
            or terminal.get("permission_denials", []) != []
            or "structured_output" in terminal):
        return None
    error = terminal.get("error")
    if isinstance(error, Mapping):
        codes = [error[key] for key in ("type", "code") if key in error]
        if codes and all(type(code) is str and code in QUOTA_ERROR_CODES for code in codes):
            return "terminal_error:" + codes[0]
    if "error" in terminal:
        return None
    # Only the latest rate-limit event can establish the terminal window state.
    for event in reversed(events[:-1]):
        if event.get("type") != "rate_limit_event":
            continue
        # Accept only these explicit machine-field spellings; never message text.
        records = [event[key] for key in ("rate_limit_info", "rateLimitInfo") if key in event]
        if len(records) != 1 or not isinstance(records[0], Mapping):
            return None
        info = records[0]
        if (info.get("status") == "rejected" and type(info.get("rateLimitType")) is str
                and info["rateLimitType"] in ACCOUNT_USAGE_WINDOWS
                and type(info.get("resetsAt")) in (int, float) and info["resetsAt"] > 0):
            return "rejected_account_window:" + info["rateLimitType"]
        return None
    return None


def validate_quota_route(primary: str, provider_allowlist: tuple[str, ...] | None,
                         fallback: str | None) -> None:
    if provider_allowlist is not None:
        if (type(provider_allowlist) is not tuple or not provider_allowlist
                or any(item not in ("claude", "codex") for item in provider_allowlist)
                or tuple(sorted(set(provider_allowlist))) != provider_allowlist):
            raise ValueError("provider_allowlist must be a sorted unique tuple of claude/codex")
        if primary not in provider_allowlist:
            raise ValueError(f"primary provider {primary!r} is not permitted")
    if fallback is not None and (fallback != "codex" or provider_allowlist is None
                                 or "codex" not in provider_allowlist):
        raise ValueError("quota handoff requires explicitly permitted Codex")


def may_handoff_to_codex(result: Any, *, primary: str,
                         provider_allowlist: tuple[str, ...] | None,
                         fallback: str | None, already_handed_off: bool) -> bool:
    validate_quota_route(primary, provider_allowlist, fallback)
    return (not already_handed_off and primary == "claude" and fallback == "codex"
            and result.provider == "claude-code" and result.status == "failed"
            and result.failure_classification == "quota_exhausted")
