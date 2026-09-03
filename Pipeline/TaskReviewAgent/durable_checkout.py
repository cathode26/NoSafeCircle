"""Canonical checkout manager that survives agent/human workflow handoffs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

from .contracts import (
    TASK_REVIEW_SCHEMA_VERSION,
    TaskReviewContractError,
    semantic_sha256,
    validate_task_id,
)
from .issue_workflow_store import _parse_github_repository, _redact_origin
from .real_checkout import (
    _git,
    _git_text,
    _normalized_remote,
    _run,
    branch_name,
    default_checkout_root,
)


class DurableCheckoutError(TaskReviewContractError):
    """Raised when a workflow-owned checkout cannot be created or resumed safely."""


def _workflow_state(observation: dict[str, Any]) -> dict[str, Any] | None:
    coordination = observation.get("coordination")
    if not isinstance(coordination, dict):
        return None
    value = coordination.get("workflow_state")
    return value if isinstance(value, dict) else None


def _require_observation(observation: dict[str, Any], task_id: str) -> None:
    if not isinstance(observation, dict):
        raise DurableCheckoutError("checkout preparation requires one observation object")
    if observation.get("schema_version") != TASK_REVIEW_SCHEMA_VERSION:
        raise DurableCheckoutError("checkout observation has an unsupported schema_version")
    if observation.get("observation_authority") != "real_read_only":
        raise DurableCheckoutError("checkout preparation requires real_read_only observation")
    task = observation.get("task")
    environment = observation.get("environment")
    coordination = observation.get("coordination")
    if not isinstance(task, dict) or not isinstance(environment, dict):
        raise DurableCheckoutError("checkout observation is missing task/environment facts")
    if task.get("task_id") != task_id:
        raise DurableCheckoutError("checkout observation task identity changed")
    if not isinstance(coordination, dict):
        raise DurableCheckoutError("checkout observation is missing Issue workflow facts")


class DurableTaskCheckoutManager:
    """Create fresh task clones and resume pushed handoff branches for later agents."""

    def __init__(
        self,
        *,
        source_root: Path | str,
        task_id: str,
        checkout_root: Path | str | None = None,
        worker_id: str,
        work_type: str = "implementation",
        allow_local_remote_for_tests: bool = False,
    ) -> None:
        self.task_id = validate_task_id(task_id)
        self.source_root = Path(source_root).resolve()
        self.checkout_root = Path(checkout_root or default_checkout_root())
        self.worker_id = str(worker_id).strip()
        if not self.worker_id:
            raise DurableCheckoutError("worker_id must be non-empty")
        self.work_type = str(work_type).strip().casefold()
        if self.work_type not in {"implementation", "decomposition"}:
            raise DurableCheckoutError(
                "work_type must be implementation or decomposition"
            )
        self.allow_local_remote_for_tests = bool(allow_local_remote_for_tests)
        self.checkout_path = self.checkout_root / self.task_id
        self.state_root = self.checkout_root / ".task-review-agent"
        self.manifest_path = self.state_root / f"{self.task_id}.json"

    def expected_branch(self, observation: dict[str, Any]) -> str:
        workflow = _workflow_state(observation)
        recorded = workflow.get("branch") if workflow else None
        if type(recorded) is str and recorded:
            return recorded
        task = observation.get("task") or {}
        return branch_name(self.task_id, task.get("title"))

    def expected_head(self, observation: dict[str, Any]) -> str:
        workflow = _workflow_state(observation)
        recorded = workflow.get("head_commit") if workflow else None
        if type(recorded) is str and recorded:
            return recorded
        return str((observation.get("environment") or {}).get("source_head") or "")

    def is_resume(self, observation: dict[str, Any]) -> bool:
        workflow = _workflow_state(observation)
        return bool(workflow and workflow.get("head_commit"))

    def _remote_allowed(self, remote_url: str) -> bool:
        # Same repository-authority design as RealTaskCheckoutManager: the
        # approved repository is whichever one this controller checkout's own
        # Git origin represents, not a single global hardcode. Separate
        # observed-origin equality checks bind the durable checkout to THIS
        # controller's specific origin.
        if _parse_github_repository(remote_url) is not None:
            return True
        return self.allow_local_remote_for_tests

    def _manifest_payload(
        self,
        observation: dict[str, Any],
        remote_url: str,
    ) -> dict[str, Any]:
        task = observation["task"]
        environment = observation["environment"]
        payload = {
            "schema_version": "2.0",
            "task_id": self.task_id,
            "checkout_path": str(self.checkout_path),
            "branch": self.expected_branch(observation),
            "remote_url": remote_url,
            "initial_source_head": environment["source_head"],
            "initial_source_tree": environment["source_tree"],
            "task_contract_path": task["contract_path"],
            "task_contract_revision": task["contract_revision"],
            "task_contract_sha256": task["task_contract_sha256"],
            "authority": "durable_checkout_identity",
        }
        if self.work_type != "implementation":
            payload["checkout_purpose"] = self.work_type
        return {"manifest_sha256": semantic_sha256(payload), **payload}

    def _read_manifest(self) -> dict[str, Any] | None:
        if not self.manifest_path.is_file():
            return None
        try:
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict):
            return None
        manifest_hash = value.get("manifest_sha256")
        payload = {key: item for key, item in value.items() if key != "manifest_sha256"}
        if manifest_hash != semantic_sha256(payload):
            return None
        return value

    def _manifest_matches(
        self,
        observation: dict[str, Any],
        remote_url: str,
    ) -> bool:
        current = self._read_manifest()
        if current is None:
            return False
        task = observation["task"]
        stable = {
            "schema_version": "2.0",
            "task_id": self.task_id,
            "checkout_path": str(self.checkout_path),
            "branch": self.expected_branch(observation),
            "task_contract_path": task["contract_path"],
            "task_contract_revision": task["contract_revision"],
            "task_contract_sha256": task["task_contract_sha256"],
            "authority": "durable_checkout_identity",
        }
        if self.work_type != "implementation":
            stable["checkout_purpose"] = self.work_type
        if any(current.get(key) != value for key, value in stable.items()):
            return False
        return _normalized_remote(str(current.get("remote_url") or "")) == _normalized_remote(
            remote_url
        )

    def _write_manifest(self, observation: dict[str, Any], remote_url: str) -> None:
        payload = self._manifest_payload(observation, remote_url)
        self.state_root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.task_id}.",
            suffix=".json.tmp",
            dir=str(self.state_root),
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    payload,
                    stream,
                    ensure_ascii=False,
                    allow_nan=False,
                    indent=2,
                    sort_keys=True,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.manifest_path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def inspect(self, observation: dict[str, Any]) -> dict[str, Any]:
        _require_observation(observation, self.task_id)
        environment = observation["environment"]
        task = observation["task"]
        expected_head = self.expected_head(observation)
        expected_branch = self.expected_branch(observation)
        expected_remote = environment.get("remote_url")
        reasons: list[str] = []
        base = {
            "path": str(self.checkout_path),
            "expected_branch": expected_branch,
            "expected_head": expected_head,
            "branch": None,
            "clean": None,
            "head_commit": None,
            "head_tree": None,
            "task_contract_sha256": None,
            "remote_url": None,
            "managed_manifest_path": str(self.manifest_path),
            "managed": False,
            "resume_mode": self.is_resume(observation),
            "reasons": reasons,
        }
        if not self.checkout_path.exists():
            return {"status": "missing", **base}
        if not self.checkout_path.is_dir():
            reasons.append("canonical checkout path exists but is not a directory")
            return {"status": "conflict", **base}
        top = _git_text(self.checkout_path, "rev-parse", "--show-toplevel", check=False)
        if not top:
            reasons.append("canonical checkout path is not a Git repository")
            return {"status": "conflict", **base}
        if Path(top).resolve() != self.checkout_path.resolve():
            reasons.append("canonical checkout path is nested inside another Git repository")
            return {"status": "conflict", **base}

        head = _git_text(self.checkout_path, "rev-parse", "--verify", "HEAD", check=False)
        tree = _git_text(self.checkout_path, "rev-parse", "HEAD^{tree}", check=False)
        branch = _git_text(self.checkout_path, "branch", "--show-current", check=False)
        status = _git_text(
            self.checkout_path,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            check=False,
        )
        remote_url = _git_text(
            self.checkout_path,
            "remote",
            "get-url",
            "origin",
            check=False,
        )
        origin_main = _git_text(
            self.checkout_path,
            "rev-parse",
            "--verify",
            "refs/remotes/origin/main",
            check=False,
        )
        remote_branch = _git_text(
            self.checkout_path,
            "rev-parse",
            "--verify",
            f"refs/remotes/origin/{expected_branch}",
            check=False,
        )
        contract_result = _git(
            self.checkout_path,
            "show",
            f"HEAD:{task['contract_path']}",
            check=False,
        )
        contract_hash = (
            hashlib.sha256(contract_result.stdout).hexdigest()
            if contract_result.returncode == 0
            else None
        )
        base.update(
            branch=branch or None,
            clean=status == "",
            head_commit=head or None,
            head_tree=tree or None,
            task_contract_sha256=contract_hash,
            remote_url=remote_url or None,
        )
        if head != expected_head:
            reasons.append(
                f"checkout HEAD {head!r} does not match workflow head {expected_head!r}"
            )
        if branch != expected_branch:
            reasons.append(
                f"checkout branch {branch!r} does not match workflow branch {expected_branch!r}"
            )
        if status:
            reasons.append("checkout working tree is not clean")
        if not remote_url or not self._remote_allowed(remote_url):
            reasons.append(
                f"checkout origin is not an approved remote: {_redact_origin(remote_url)!r}"
            )
        if not expected_remote:
            # The controller/source origin was never actually observed (for
            # example after an OSError/TimeoutExpired while reading it). The
            # repository-equality invariant below must never be silently
            # skipped just because there is nothing to compare against.
            reasons.append("controller origin remote URL was not observed")
        elif _normalized_remote(remote_url) != _normalized_remote(str(expected_remote)):
            reasons.append("checkout origin differs from the observed controller origin")
        if origin_main != environment.get("source_head"):
            reasons.append("checkout origin/main does not match current controller main")
        if self.is_resume(observation) and remote_branch != expected_head:
            reasons.append("recorded handoff commit is not the pushed remote task branch")
        if not self.is_resume(observation) and tree != environment.get("source_tree"):
            reasons.append("fresh checkout tree does not match observed source tree")
        if contract_hash != task.get("task_contract_sha256"):
            reasons.append("checkout task contract hash does not match current task authority")
        if reasons:
            return {"status": "conflict", **base}

        managed = self._manifest_matches(observation, remote_url)
        base["managed"] = managed
        if self.manifest_path.exists() and not managed:
            reasons.append("external durable checkout manifest conflicts with task identity")
            return {"status": "conflict", **base}
        return {"status": "ready" if managed else "unmanaged_exact", **base}

    def _preparation_reasons(self, observation: dict[str, Any]) -> list[str]:
        _require_observation(observation, self.task_id)
        environment = observation["environment"]
        task = observation["task"]
        coordination = observation["coordination"]
        reasons: list[str] = []
        if environment.get("ready") is not True:
            reasons.append("task-review environment is not ready")
        if environment.get("controller_clean") is not True:
            reasons.append("controller checkout is not clean")
        if environment.get("taskgraph_valid") is not True:
            reasons.append("TaskGraph validation failed")
        if environment.get("source_head") != environment.get("origin_main"):
            reasons.append("controller HEAD must exactly match current origin/main")
        if task.get("contract_disposition") != "active":
            reasons.append("task contract is not active")
        if task.get("kind") != "implementation":
            reasons.append("task is not an implementation contract")
        if self.work_type == "implementation":
            if task.get("execution_scope") != "single_agent":
                reasons.append("task is not single_agent")
            if task.get("decomposition_state") != "concrete":
                reasons.append("task is not concrete")
        else:
            if task.get("execution_scope") != "needs_execution_decomposition":
                reasons.append("task does not require execution decomposition")
        expected_derived_state = (
            "not_delivered" if self.work_type == "implementation" else "aggregate"
        )
        if task.get("derived_state") != expected_derived_state:
            reasons.append(
                f"task is not in {expected_derived_state} state for {self.work_type} work"
            )
        if (
            self.work_type == "implementation"
            and task.get("dependencies_conformant") is not True
        ):
            reasons.append("one or more declared dependencies are not conformant")
        workflow_status = coordination.get("workflow_status")
        if workflow_status != "agent_working_by_worker":
            reasons.append("Issue workflow does not grant this worker an agent lease")
        workflow = coordination.get("workflow_state")
        if not isinstance(workflow, dict) or workflow.get("worker_id") != self.worker_id:
            reasons.append("Issue workflow worker does not match checkout worker_id")
        remote_url = environment.get("remote_url")
        if type(remote_url) is not str or not remote_url:
            reasons.append("controller origin remote URL was not observed")
        elif not self._remote_allowed(remote_url):
            reasons.append(
                f"controller origin is not an approved remote: {_redact_origin(remote_url)!r}"
            )
        return reasons

    def _validate_clone(
        self,
        checkout: Path,
        observation: dict[str, Any],
        remote_url: str,
    ) -> None:
        environment = observation["environment"]
        task = observation["task"]
        expected_head = self.expected_head(observation)
        expected_branch = self.expected_branch(observation)
        head = _git_text(checkout, "rev-parse", "--verify", "HEAD")
        branch = _git_text(checkout, "branch", "--show-current")
        status = _git_text(
            checkout,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        origin_main = _git_text(
            checkout,
            "rev-parse",
            "--verify",
            "refs/remotes/origin/main",
        )
        actual_remote = _git_text(checkout, "remote", "get-url", "origin")
        if head != expected_head:
            raise DurableCheckoutError("new checkout does not match workflow head commit")
        if branch != expected_branch:
            raise DurableCheckoutError("new checkout branch identity is wrong")
        if status:
            raise DurableCheckoutError("new checkout is unexpectedly dirty")
        if origin_main != environment["source_head"]:
            raise DurableCheckoutError("new checkout origin/main differs from controller main")
        if _normalized_remote(actual_remote) != _normalized_remote(remote_url):
            raise DurableCheckoutError("new checkout origin differs from requested remote")
        contract_result = _git(checkout, "show", f"HEAD:{task['contract_path']}")
        if hashlib.sha256(contract_result.stdout).hexdigest() != task[
            "task_contract_sha256"
        ]:
            raise DurableCheckoutError("new checkout task contract hash differs from observation")
        taskcontrol = checkout / "Pipeline" / "TaskGraph" / "taskcontrol.py"
        if not taskcontrol.is_file():
            raise DurableCheckoutError("new checkout is missing TaskGraph taskcontrol.py")
        validation = _run(
            (sys.executable, str(taskcontrol), "validate"),
            cwd=checkout,
            check=False,
            timeout_seconds=300.0,
        )
        if validation.returncode != 0 or b"taskcontrol validate: PASS" not in validation.stdout:
            raise DurableCheckoutError("TaskGraph validation did not pass in new checkout")

    def prepare(self, observation: dict[str, Any]) -> dict[str, Any]:
        reasons = self._preparation_reasons(observation)
        if reasons:
            return {
                "status": "blocked",
                "path": str(self.checkout_path),
                "branch": self.expected_branch(observation),
                "reasons": reasons,
            }
        inspected = self.inspect(observation)
        if inspected["status"] == "ready":
            return {"status": "resumed", **inspected}
        if inspected["status"] == "unmanaged_exact":
            remote_url = str(inspected["remote_url"])
            self._write_manifest(observation, remote_url)
            adopted = self.inspect(observation)
            if adopted["status"] != "ready":
                raise DurableCheckoutError("exact checkout adoption could not be verified")
            return {"status": "adopted", **adopted}
        if inspected["status"] == "conflict":
            return {"status": "blocked", **inspected}

        environment = observation["environment"]
        remote_url = str(environment["remote_url"])
        expected_branch = self.expected_branch(observation)
        expected_head = self.expected_head(observation)
        self.checkout_root.mkdir(parents=True, exist_ok=True)
        temporary = Path(
            tempfile.mkdtemp(
                prefix=f".{self.task_id}.clone-",
                dir=str(self.checkout_root),
            )
        )
        try:
            shutil.rmtree(temporary)
            _run(("git", "clone", remote_url, str(temporary)), cwd=self.checkout_root)
            _git(temporary, "config", "core.longpaths", "true")
            _git(temporary, "fetch", "origin", "main")
            if self.is_resume(observation):
                _git(
                    temporary,
                    "fetch",
                    "origin",
                    f"+refs/heads/{expected_branch}:refs/remotes/origin/{expected_branch}",
                )
                remote_head = _git_text(
                    temporary,
                    "rev-parse",
                    "--verify",
                    f"refs/remotes/origin/{expected_branch}",
                )
                if remote_head != expected_head:
                    raise DurableCheckoutError(
                        "pushed task branch does not match recorded human handoff commit"
                    )
                _git(
                    temporary,
                    "switch",
                    "-c",
                    expected_branch,
                    "--track",
                    f"origin/{expected_branch}",
                )
            else:
                if _git_text(temporary, "rev-parse", "HEAD") != expected_head:
                    raise DurableCheckoutError("remote main moved during checkout creation")
                existing_remote = _git_text(
                    temporary,
                    "rev-parse",
                    "--verify",
                    f"refs/remotes/origin/{expected_branch}",
                    check=False,
                )
                if existing_remote:
                    raise DurableCheckoutError(
                        "fresh workflow found an existing remote task branch without a "
                        "recorded handoff commit"
                    )
                _git(temporary, "switch", "-c", expected_branch)
            self._validate_clone(temporary, observation, remote_url)
            if self.checkout_path.exists():
                raise DurableCheckoutError(
                    "canonical checkout path appeared during preparation; refusing overwrite"
                )
            os.replace(temporary, self.checkout_path)
            self._write_manifest(observation, remote_url)
            verified = self.inspect(observation)
            if verified["status"] != "ready":
                raise DurableCheckoutError("published canonical checkout could not be verified")
            return {"status": "created", **verified}
        finally:
            if temporary.exists():
                def onerror(function, path, _exc):
                    os.chmod(path, stat.S_IWRITE)
                    function(path)

                shutil.rmtree(temporary, onerror=onerror)
