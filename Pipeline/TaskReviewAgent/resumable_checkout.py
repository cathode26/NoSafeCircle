"""Resume policy layered over the strict durable checkout identity checks."""

from __future__ import annotations

from typing import Any

from .durable_checkout import DurableTaskCheckoutManager
from .real_checkout import _git, _git_text


_STALE_MAIN_REASON = "checkout origin/main does not match current controller main"
_DIRTY_WORKTREE_REASON = "checkout working tree is not clean"
_SAFE_POST_HANDOFF_UNITY_CHURN = frozenset(
    {
        "ProjectSettings/EditorBuildSettings.asset",
        "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json",
        "ProjectSettings/ProjectSettings.asset",
    }
)


class ResumableTaskCheckoutManager(DurableTaskCheckoutManager):
    """Resume an exact human-tested branch without treating Unity churn as task work.

    A human-tested task branch remains bound to its exact remote branch commit and
    task-contract hash. Unrelated mainline progress does not rewrite that branch.
    Before downstream automation resumes, this manager may restore only a tiny exact
    allowlist of unstaged ProjectSettings churn produced by opening/running Unity and
    may refresh the local origin/main tracking ref. Any staged, untracked, task-owned,
    or otherwise unexpected path remains a hard conflict.
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

    def prepare(self, observation: dict[str, Any]) -> dict[str, Any]:
        recovery = self._recover_safe_post_handoff_churn(observation)
        result = super().prepare(observation)
        if recovery:
            return {
                **result,
                **recovery,
                "recovery_authority": "exact_human_handoff_unity_churn_allowlist",
            }
        return result

    def _recover_safe_post_handoff_churn(
        self,
        observation: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.is_resume(observation) or not self.checkout_path.is_dir():
            return {}
        raw = super().inspect(observation)
        if raw.get("status") != "conflict":
            return {}
        reasons = set(raw.get("reasons") or [])
        permitted_reasons = {_STALE_MAIN_REASON, _DIRTY_WORKTREE_REASON}
        if not reasons or not reasons.issubset(permitted_reasons):
            return {}

        restored: list[str] = []
        if _DIRTY_WORKTREE_REASON in reasons:
            dirty = self._safe_dirty_paths()
            if not dirty:
                return {}
            for path in dirty:
                _git(
                    self.checkout_path,
                    "restore",
                    "--source=HEAD",
                    "--worktree",
                    "--",
                    path,
                )
            restored = dirty

        refreshed = False
        if _STALE_MAIN_REASON in reasons:
            _git(
                self.checkout_path,
                "fetch",
                "origin",
                "+refs/heads/main:refs/remotes/origin/main",
            )
            refreshed = True

        verified = super().inspect(observation)
        if verified.get("status") not in {"ready", "unmanaged_exact"}:
            return {}
        return {
            "recovered_unity_churn": restored,
            "origin_main_refreshed": refreshed,
        }

    def _safe_dirty_paths(self) -> list[str] | None:
        raw = _git_text(
            self.checkout_path,
            "-c",
            "core.quotepath=false",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        if not raw:
            return []
        paths: list[str] = []
        for line in raw.splitlines():
            if len(line) < 4:
                return None
            code = line[:2]
            path = line[3:].replace("\\", "/")
            if " -> " in path:
                return None
            if code != " M" or path not in _SAFE_POST_HANDOFF_UNITY_CHURN:
                return None
            paths.append(path)
        return sorted(set(paths), key=str.casefold)
