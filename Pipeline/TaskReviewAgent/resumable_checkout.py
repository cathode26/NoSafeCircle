"""Resume policy layered over the strict durable checkout identity checks."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .durable_checkout import DurableTaskCheckoutManager
from .real_checkout import _decode, _git, _git_text, _normalized_remote
from .safe_unity_churn import classify_safe_post_unity_churn


_STALE_MAIN_REASON = "checkout origin/main does not match current controller main"
_DIRTY_WORKTREE_REASON = "checkout working tree is not clean"
_CONTRACT_HASH_REASON = "checkout task contract hash does not match current task authority"
_MANIFEST_REASON = "external durable checkout manifest conflicts with task identity"
_REMOTE_HEAD_REASON = "recorded handoff commit is not the pushed remote task branch"
class ResumableTaskCheckoutManager(DurableTaskCheckoutManager):
    """Resume exact durable task branches across safe editor and contract migrations.

    Normal human-tested resumes remain bound to their exact remote branch commit and
    task-contract hash. The manager may restore only a tiny allowlist of unstaged
    ProjectSettings churn and refresh local tracking refs.

    A repository-wide clerical task-contract migration may also advance the durable
    Issue head. In that case this manager may fast-forward the existing clean task
    checkout only when all of these identities agree:

    - the checked-out branch is the exact Issue branch;
    - the local head is an ancestor of the exact Issue head;
    - the remote task branch equals that Issue head;
    - the task contract at that remote head hashes to current TaskGraph authority;
    - the origin remote still equals the controller origin.

    The recovery never resets, rebases, force-pushes, or accepts an unexpected dirty
    path. After the fast-forward it rewrites the external durable manifest to the new
    contract identity and verifies the strict base-manager inspection passes.
    """

    def inspect(self, observation: dict[str, Any]) -> dict[str, Any]:
        result = super().inspect(observation)
        if not self.is_resume(observation) and result.get("status") == "conflict":
            deferred = self._defer_active_implementation_main_advance(
                observation, result
            )
            if deferred:
                return deferred
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

    def _defer_active_implementation_main_advance(
        self,
        observation: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Keep a proven implementation base stable until candidate integration.

        Current main is intentionally integrated by CandidateIntegrator after the
        execution crew returns and immediately before the initial handoff commit.
        Refreshing a clean in-progress checkout sooner discards its stable input
        identity and used to strand concurrent runs whenever another task advanced
        main.
        """

        workflow = (observation.get("coordination") or {}).get("workflow_state") or {}
        if (
            workflow.get("state") != "agent_working"
            or workflow.get("phase") != "implementation"
        ):
            return {}
        reasons = set(result.get("reasons") or [])
        head_reason = next(
            (
                reason
                for reason in reasons
                if reason.startswith("checkout HEAD ")
                and " does not match workflow head " in reason
            ),
            None,
        )
        tree_reason = next(
            (
                reason
                for reason in reasons
                if reason == "fresh checkout tree does not match observed source tree"
            ),
            None,
        )
        permitted = {_STALE_MAIN_REASON}
        if head_reason:
            permitted.add(head_reason)
        if tree_reason:
            permitted.add(tree_reason)
        if not reasons or not reasons.issubset(permitted):
            return {}

        manifest = self._read_manifest()
        remote_url = str(result.get("remote_url") or "")
        current_main = str((observation.get("environment") or {}).get("source_head") or "")
        base_head = str((manifest or {}).get("initial_source_head") or "")
        base_tree = str((manifest or {}).get("initial_source_tree") or "")
        if (
            manifest is None
            or not self._manifest_matches(observation, remote_url)
            or result.get("head_commit") != base_head
            or result.get("head_tree") != base_tree
            or result.get("clean") is not True
            or not base_head
            or not current_main
            or _git(
                self.source_root,
                "merge-base",
                "--is-ancestor",
                base_head,
                current_main,
                check=False,
            ).returncode
            != 0
        ):
            return {}
        return {
            **result,
            "status": "ready",
            "reasons": [],
            "managed": True,
            "base_main_advanced": True,
            "implementation_base_head": base_head,
            "deferred_current_main_head": current_main,
            "current_main_integration_deferred_to": "candidate_integration",
        }

    def prepare(self, observation: dict[str, Any]) -> dict[str, Any]:
        recovery = self._recover_stale_unleased_checkout(observation)
        if recovery:
            if (observation.get("coordination") or {}).get("status") == "available_unassigned":
                return {"status": "archived_stale", "path": str(self.checkout_path), **recovery, "recovery_authority": "archived_stale_unleased_checkout"}
            prepared = super().prepare(observation)
            return {
                **prepared,
                **recovery,
                "recovery_authority": "archived_stale_unleased_checkout",
            }
        recovery = self._recover_safe_resume_state(observation)
        result = super().prepare(observation)
        if recovery:
            return {
                **result,
                **recovery,
                "recovery_authority": "exact_durable_resume_identity",
            }
        return result

    def _recover_stale_unleased_checkout(
        self, observation: dict[str, Any]
    ) -> dict[str, Any]:
        """Archive a clean stale checkout before preparing the current one.

        A checkout left by an interrupted preparation can be clean and still
        carry an older contract/mainline identity.  With no Issue lease or
        handoff head there is no work identity to resume, so preserving it as
        an exact archive is the safe recovery boundary.  Dirty or active
        checkouts deliberately remain conflicts.
        """
        if not self.checkout_path.is_dir():
            return {}
        coordination = observation.get("coordination") or {}
        workflow = coordination.get("workflow_state")
        if coordination.get("status") == "available_unassigned":
            if workflow is not None and (
                not isinstance(workflow, dict)
                or workflow.get("state") != "agent_ready"
            ):
                return {}
        elif coordination.get("status") == "claimed_by_worker":
            if not isinstance(workflow, dict):
                return {}
            if (
                workflow.get("state") != "agent_working"
                or workflow.get("phase") != "implementation"
                or workflow.get("worker_id") != self.worker_id
                or not workflow.get("lease_id")
                or workflow.get("human_handoff_commit") is not None
                or workflow.get("human_result") is not None
            ):
                return {}
        else:
            return {}
        if workflow is not None and coordination.get("status") == "available_unassigned":
            if not isinstance(workflow, dict):
                return {}
            if workflow.get("state") != "agent_ready":
                return {}
            if any(workflow.get(key) is not None for key in (
                "worker_id", "lease_id", "branch", "head_commit", "checkout_path",
            )):
                return {}
        if observation.get("accepted_plan_id") is not None or observation.get("execution_run") is not None:
            return {}

        current = super().inspect(observation)
        reasons = set(current.get("reasons") or [])
        permitted = {
            "checkout origin/main does not match current controller main",
            "fresh checkout tree does not match observed source tree",
            "checkout task contract hash does not match current task authority",
            "external durable checkout manifest conflicts with task identity",
            "recorded handoff commit is not the pushed remote task branch",
        }
        permitted.update(
            reason for reason in reasons
            if reason.startswith("checkout HEAD ")
            and " does not match workflow head " in reason
        )
        if current.get("status") != "conflict" or not reasons or not reasons.issubset(permitted):
            return {}
        if current.get("clean") is not True or current.get("branch") != current.get("expected_branch"):
            return {}
        if coordination.get("status") == "claimed_by_worker":
            manifest = self._read_manifest()
            if not manifest:
                return {}
            if (
                current.get("head_commit") != manifest.get("initial_source_head")
                or current.get("head_tree") != manifest.get("initial_source_tree")
                or manifest.get("branch") != current.get("expected_branch")
                or manifest.get("task_id") != self.task_id
            ):
                return {}
        remote_url = str(current.get("remote_url") or "")
        expected_remote = str((observation.get("environment") or {}).get("remote_url") or "")
        if not remote_url or not expected_remote or _normalized_remote(remote_url) != _normalized_remote(expected_remote):
            return {}

        archive_root = self.checkout_root / ".stale-checkouts" / self.task_id
        archive_root.mkdir(parents=True, exist_ok=True)
        descriptor = Path(tempfile.mkdtemp(prefix="archive-", dir=str(archive_root)))
        archive_path = descriptor.with_name(descriptor.name + "-checkout")
        descriptor.rmdir()
        # The resolved target is explicitly below this manager's checkout root.
        if self.checkout_path.resolve() == self.checkout_root.resolve() or self.checkout_root.resolve() not in self.checkout_path.resolve().parents:
            return {}
        shutil.move(str(self.checkout_path), str(archive_path))
        archived_manifest = None
        if self.manifest_path.is_file():
            manifest_dir = archive_path / ".task-review-agent"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            archived_manifest = manifest_dir / self.manifest_path.name
            shutil.move(str(self.manifest_path), str(archived_manifest))
        return {
            "stale_checkout_archived": str(archive_path),
            "stale_manifest_archived": str(archived_manifest) if archived_manifest else None,
            "stale_checkout_head": current.get("head_commit"),
            "stale_checkout_tree": current.get("head_tree"),
        }

    def _recover_safe_resume_state(
        self,
        observation: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.is_resume(observation) or not self.checkout_path.is_dir():
            return {}
        raw = super().inspect(observation)
        if raw.get("status") != "conflict":
            return {}

        reasons = list(raw.get("reasons") or [])
        if not reasons:
            return {}
        reason_set = set(reasons)
        head_reasons = [
            reason
            for reason in reasons
            if reason.startswith("checkout HEAD ")
            and " does not match workflow head " in reason
        ]
        permitted = {
            _STALE_MAIN_REASON,
            _DIRTY_WORKTREE_REASON,
            _CONTRACT_HASH_REASON,
            _MANIFEST_REASON,
            _REMOTE_HEAD_REASON,
            *head_reasons,
        }
        if not reason_set.issubset(permitted):
            return {}

        environment = observation.get("environment") or {}
        task = observation.get("task") or {}
        expected_branch = self.expected_branch(observation)
        expected_head = self.expected_head(observation)
        remote_url = str(raw.get("remote_url") or "")
        expected_remote = str(environment.get("remote_url") or "")
        if (
            raw.get("branch") != expected_branch
            or not remote_url
            or not self._remote_allowed(remote_url)
            or not expected_remote
            or _normalized_remote(remote_url) != _normalized_remote(expected_remote)
        ):
            return {}

        restored: list[str] = []
        if _DIRTY_WORKTREE_REASON in reason_set:
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

        _git(
            self.checkout_path,
            "fetch",
            "origin",
            "+refs/heads/main:refs/remotes/origin/main",
            f"+refs/heads/{expected_branch}:refs/remotes/origin/{expected_branch}",
        )
        remote_head = _git_text(
            self.checkout_path,
            "rev-parse",
            "--verify",
            f"refs/remotes/origin/{expected_branch}",
            check=False,
        )
        local_head = _git_text(
            self.checkout_path,
            "rev-parse",
            "--verify",
            "HEAD",
            check=False,
        )
        if remote_head != expected_head or not local_head:
            return {}
        if (
            _git(
                self.checkout_path,
                "merge-base",
                "--is-ancestor",
                local_head,
                expected_head,
                check=False,
            ).returncode
            != 0
        ):
            return {}

        contract_path = task.get("contract_path")
        expected_contract_hash = task.get("task_contract_sha256")
        if not isinstance(contract_path, str) or not isinstance(expected_contract_hash, str):
            return {}
        contract = _git(
            self.checkout_path,
            "show",
            f"{expected_head}:{contract_path}",
            check=False,
        )
        if (
            contract.returncode != 0
            or hashlib.sha256(contract.stdout).hexdigest() != expected_contract_hash
        ):
            return {}

        fast_forwarded = local_head != expected_head
        if fast_forwarded:
            _git(
                self.checkout_path,
                "merge",
                "--ff-only",
                expected_head,
            )

        self._write_manifest(observation, remote_url)
        verified = super().inspect(observation)
        if verified.get("status") != "ready":
            return {}
        return {
            "recovered_unity_churn": restored,
            "origin_main_refreshed": True,
            "contract_migration_fast_forwarded": fast_forwarded,
            "prior_checkout_head": local_head,
            "recovered_checkout_head": expected_head,
            "durable_manifest_migrated": True,
        }

    def _safe_dirty_paths(self) -> list[str] | None:
        # Do not use _git_text here: its trailing/leading strip is correct for
        # hashes and branch names but would remove the first porcelain status
        # column when the first entry is an unstaged modification (" M").
        result = _git(
            self.checkout_path,
            "-c",
            "core.quotepath=false",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        raw = _decode(result.stdout, label="git status stdout")
        classified = classify_safe_post_unity_churn(raw, self.checkout_path)
        return list(classified) if classified is not None else None
