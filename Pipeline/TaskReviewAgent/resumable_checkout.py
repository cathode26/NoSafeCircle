"""Resume policy layered over the strict durable checkout identity checks."""

from __future__ import annotations

from typing import Any

from .durable_checkout import DurableTaskCheckoutManager


_STALE_MAIN_REASON = "checkout origin/main does not match current controller main"


class ResumableTaskCheckoutManager(DurableTaskCheckoutManager):
    """Treat a stale local origin/main ref as nonblocking for a recorded handoff branch.

    A human-tested task branch remains bound to its exact remote branch commit and current
    task-contract hash. Unrelated mainline progress must not force manual checkout repair.
    Fresh task creation still requires exact current main.
    """

    def inspect(self, observation: dict[str, Any]) -> dict[str, Any]:
        result = super().inspect(observation)
        if not self.is_resume(observation) or result.get("status") != "conflict":
            return result
        reasons = list(result.get("reasons") or [])
        filtered = [reason for reason in reasons if reason != _STALE_MAIN_REASON]
        if filtered:
            return result

        remote_url = str(result.get("remote_url") or "")
        managed = bool(remote_url) and self._manifest_matches(observation, remote_url)
        result = {
            **result,
            "reasons": [],
            "managed": managed,
            "origin_main_refresh_required": True,
        }
        result["status"] = "ready" if managed else "unmanaged_exact"
        return result
