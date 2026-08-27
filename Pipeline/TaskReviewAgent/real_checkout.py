"""Safe canonical task checkout inspection and preparation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

from .contracts import (
    TASK_REVIEW_SCHEMA_VERSION,
    TaskReviewContractError,
    semantic_sha256,
    validate_task_id,
)


CANONICAL_REMOTE = "https://github.com/cathode26/NoSafeCircle.git"
_WINDOWS_DEFAULT_ROOT = Path(r"C:\UnityProjects\NoSafeCircleAgentCrew")
_BRANCH_TOKEN_RE = re.compile(r"[^a-z0-9]+")


class RealCheckoutError(TaskReviewContractError):
    """Raised when a canonical checkout cannot be inspected or prepared safely."""


def default_checkout_root() -> Path:
    configured = os.getenv("NSC_TASK_CHECKOUT_ROOT")
    if configured:
        return Path(configured)
    return _WINDOWS_DEFAULT_ROOT


def _decode(data: bytes, *, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RealCheckoutError(f"{label} was not valid UTF-8") from exc


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout_seconds: float = 600.0,
) -> subprocess.CompletedProcess[bytes]:
    if not args or any(type(item) is not str or not item for item in args):
        raise RealCheckoutError("subprocess arguments must be non-empty exact strings")
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    try:
        result = subprocess.run(
            tuple(args),
            cwd=str(cwd),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RealCheckoutError(
            f"command could not be executed safely: {' '.join(args)}"
        ) from exc
    if check and result.returncode != 0:
        stdout = _decode(result.stdout or b"", label="stdout").strip()
        stderr = _decode(result.stderr or b"", label="stderr").strip()
        detail = "\n".join(item for item in (stdout, stderr) if item)
        raise RealCheckoutError(
            f"command failed ({result.returncode}): {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return _run(("git", "-C", str(root), *args), cwd=root, check=check)


def _git_text(root: Path, *args: str, check: bool = True) -> str:
    return _decode(_git(root, *args, check=check).stdout, label="git stdout").strip()


def _normalized_remote(value: str) -> str:
    text = value.strip().replace("\\", "/")
    if text.endswith(".git"):
        text = text[:-4]
    return text.rstrip("/").casefold()


def _slug(value: Any) -> str:
    raw = str(value or "task").casefold()
    slug = _BRANCH_TOKEN_RE.sub("-", raw).strip("-")
    return slug[:72].strip("-") or "task"


def branch_name(task_id: str, title: Any) -> str:
    return f"{validate_task_id(task_id).casefold()}-{_slug(title)}"


def _observation_identity(observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "environment": observation.get("environment"),
        "task": observation.get("task"),
        "coordination": observation.get("coordination"),
    }


def _require_observation(observation: dict[str, Any], task_id: str) -> None:
    if not isinstance(observation, dict):
        raise RealCheckoutError("checkout preparation requires one observation object")
    if observation.get("schema_version") != TASK_REVIEW_SCHEMA_VERSION:
        raise RealCheckoutError("checkout observation has an unsupported schema_version")
    if observation.get("observation_authority") != "real_read_only":
        raise RealCheckoutError("checkout preparation requires real_read_only observation")
    task = observation.get("task")
    environment = observation.get("environment")
    coordination = observation.get("coordination")
    if not isinstance(task, dict) or not isinstance(environment, dict):
        raise RealCheckoutError("checkout observation is missing task/environment facts")
    if task.get("task_id") != task_id:
        raise RealCheckoutError("checkout observation task identity changed")
    if not isinstance(coordination, dict):
        raise RealCheckoutError("checkout observation is missing GitHub coordination facts")
    expected_hash = semantic_sha256(_observation_identity(observation))
    if observation.get("observation_sha256") != expected_hash:
        raise RealCheckoutError("checkout observation identity hash does not match its facts")


class RealTaskCheckoutManager:
    """Inspect or create the canonical standalone clone for one explicit task."""

    def __init__(
        self,
        *,
        source_root: Path | str,
        task_id: str,
        checkout_root: Path | str | None = None,
        worker_id: str,
        allow_local_remote_for_tests: bool = False,
    ) -> None:
        self.task_id = validate_task_id(task_id)
        self.source_root = Path(source_root).resolve()
        self.checkout_root = Path(checkout_root or default_checkout_root())
        self.worker_id = str(worker_id).strip()
        if not self.worker_id:
            raise RealCheckoutError("worker_id must be non-empty")
        self.allow_local_remote_for_tests = bool(allow_local_remote_for_tests)
        self.checkout_path = self.checkout_root / self.task_id
        self.state_root = self.checkout_root / ".task-review-agent"
        self.manifest_path = self.state_root / f"{self.task_id}.json"

    def expected_branch(self, observation: dict[str, Any]) -> str:
        task = observation.get("task") or {}
        return branch_name(self.task_id, task.get("title"))

    def _manifest_payload(self, observation: dict[str, Any], remote_url: str) -> dict[str, Any]:
        task = observation["task"]
        environment = observation["environment"]
        payload = {
            "schema_version": "1.0",
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "checkout_path": str(self.checkout_path),
            "branch": self.expected_branch(observation),
            "remote_url": remote_url,
            "source_head": environment["source_head"],
            "source_tree": environment["source_tree"],
            "task_contract_path": task["contract_path"],
            "task_contract_revision": task["contract_revision"],
            "task_contract_sha256": task["task_contract_sha256"],
            "authority": "checkout_preparation_only",
        }
        return {"manifest_sha256": semantic_sha256(payload), **payload}

    def _write_manifest(self, observation: dict[str, Any], remote_url: str) -> None:
        payload = self._manifest_payload(observation, remote_url)
        self.state_root.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.task_id}.",
            suffix=".json.tmp",
            dir=str(self.state_root),
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
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

    def _manifest_matches(self, observation: dict[str, Any], remote_url: str) -> bool:
        if not self.manifest_path.is_file():
            return False
        try:
            current = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        return current == self._manifest_payload(observation, remote_url)

    def _remote_allowed(self, remote_url: str) -> bool:
        if _normalized_remote(remote_url) == _normalized_remote(CANONICAL_REMOTE):
            return True
        return self.allow_local_remote_for_tests

    def inspect(self, observation: dict[str, Any]) -> dict[str, Any]:
        _require_observation(observation, self.task_id)
        environment = observation["environment"]
        task = observation["task"]
        expected_head = environment.get("source_head")
        expected_tree = environment.get("source_tree")
        expected_remote = environment.get("remote_url")
        expected_branch = self.expected_branch(observation)
        reasons: list[str] = []

        base = {
            "path": str(self.checkout_path),
            "expected_branch": expected_branch,
            "branch": None,
            "clean": None,
            "source_head": None,
            "source_tree": None,
            "task_contract_sha256": None,
            "remote_url": None,
            "managed_manifest_path": str(self.manifest_path),
            "managed": False,
            "reasons": reasons,
        }

        if not self.checkout_path.exists():
            return {"status": "missing", **base}
        if not self.checkout_path.is_dir():
            reasons.append("canonical checkout path exists but is not a directory")
            return {"status": "conflict", **base}

        top = _git_text(
            self.checkout_path,
            "rev-parse",
            "--show-toplevel",
            check=False,
        )
        if not top:
            reasons.append("canonical checkout path is not a Git repository")
            return {"status": "conflict", **base}
        try:
            actual_root = Path(top).resolve()
        except OSError:
            reasons.append("canonical checkout Git root could not be resolved")
            return {"status": "conflict", **base}
        if actual_root != self.checkout_path.resolve():
            reasons.append("canonical checkout path is nested inside another Git repository")
            return {"status": "conflict", **base}

        head = _git_text(self.checkout_path, "rev-parse", "--verify", "HEAD", check=False)
        tree = _git_text(self.checkout_path, "rev-parse", "HEAD^{tree}", check=False)
        branch = _git_text(
            self.checkout_path,
            "symbolic-ref",
            "--quiet",
            "--short",
            "HEAD",
            check=False,
        )
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
        contract_path = str(task.get("contract_path") or "")
        contract_result = _git(
            self.checkout_path,
            "show",
            f"HEAD:{contract_path}",
            check=False,
        )
        contract_sha = (
            hashlib.sha256(contract_result.stdout).hexdigest()
            if contract_result.returncode == 0
            else None
        )

        base.update(
            {
                "branch": branch or None,
                "clean": status == "",
                "source_head": head or None,
                "source_tree": tree or None,
                "task_contract_sha256": contract_sha,
                "remote_url": remote_url or None,
            }
        )

        if head != expected_head:
            reasons.append(
                f"checkout HEAD {head!r} does not match observed source {expected_head!r}"
            )
        if tree != expected_tree:
            reasons.append(
                f"checkout tree {tree!r} does not match observed source tree {expected_tree!r}"
            )
        if branch != expected_branch:
            reasons.append(
                f"checkout branch {branch!r} does not match expected {expected_branch!r}"
            )
        if status:
            reasons.append("checkout working tree is not clean")
        if not remote_url or not self._remote_allowed(remote_url):
            reasons.append(f"checkout origin is not an approved remote: {remote_url!r}")
        if expected_remote and _normalized_remote(remote_url) != _normalized_remote(
            str(expected_remote)
        ):
            reasons.append("checkout origin differs from the observed controller origin")
        if origin_main != expected_head:
            reasons.append("checkout origin/main does not match the observed source HEAD")
        if contract_sha != task.get("task_contract_sha256"):
            reasons.append("checkout committed task contract hash does not match the observation")
        if reasons:
            return {"status": "conflict", **base}

        managed = self._manifest_matches(observation, remote_url)
        base["managed"] = managed
        if self.manifest_path.exists() and not managed:
            reasons.append(
                "external TaskReviewAgent checkout manifest conflicts with this "
                "task/worker/source"
            )
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
        if task.get("execution_scope") != "single_agent":
            reasons.append("task is not single_agent")
        if task.get("decomposition_state") != "concrete":
            reasons.append("task is not concrete")
        if task.get("derived_state") != "not_delivered":
            reasons.append("task is not in not_delivered state")
        if task.get("dependencies_conformant") is not True:
            reasons.append("one or more declared dependencies are not conformant")
        if coordination.get("status") != "claimed_by_worker":
            reasons.append("GitHub Issue is not claimed by this worker")
        if coordination.get("worker_id") != self.worker_id:
            reasons.append("GitHub claim worker does not match checkout worker_id")
        remote_url = environment.get("remote_url")
        if type(remote_url) is not str or not remote_url:
            reasons.append("controller origin remote URL was not observed")
        elif not self._remote_allowed(remote_url):
            reasons.append(f"controller origin is not an approved remote: {remote_url!r}")
        return reasons

    def _validate_new_clone(
        self,
        checkout: Path,
        observation: dict[str, Any],
        remote_url: str,
    ) -> None:
        environment = observation["environment"]
        task = observation["task"]
        head = _git_text(checkout, "rev-parse", "--verify", "HEAD")
        tree = _git_text(checkout, "rev-parse", "HEAD^{tree}")
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
        if head != environment["source_head"] or tree != environment["source_tree"]:
            raise RealCheckoutError("new checkout does not match the observed source commit/tree")
        if origin_main != environment["source_head"]:
            raise RealCheckoutError("new checkout origin/main moved away from observed source HEAD")
        if branch != self.expected_branch(observation):
            raise RealCheckoutError("new checkout branch identity is wrong")
        if status:
            raise RealCheckoutError("new checkout is unexpectedly dirty")
        if _normalized_remote(actual_remote) != _normalized_remote(remote_url):
            raise RealCheckoutError("new checkout origin differs from requested remote")

        contract_result = _git(
            checkout,
            "show",
            f"HEAD:{task['contract_path']}",
        )
        if hashlib.sha256(contract_result.stdout).hexdigest() != task[
            "task_contract_sha256"
        ]:
            raise RealCheckoutError("new checkout task contract hash differs from observation")

        taskcontrol = checkout / "Pipeline" / "TaskGraph" / "taskcontrol.py"
        if not taskcontrol.is_file():
            raise RealCheckoutError("new checkout is missing TaskGraph taskcontrol.py")
        validation = _run(
            (sys.executable, str(taskcontrol), "validate"),
            cwd=checkout,
            check=False,
            timeout_seconds=300.0,
        )
        stdout = _decode(validation.stdout, label="taskcontrol validate stdout")
        if validation.returncode != 0 or "taskcontrol validate: PASS" not in stdout:
            raise RealCheckoutError("TaskGraph validation did not pass in the new checkout")

    def prepare(self, observation: dict[str, Any]) -> dict[str, Any]:
        reasons = self._preparation_reasons(observation)
        if reasons:
            return {
                "status": "blocked",
                "path": str(self.checkout_path),
                "branch": self.expected_branch(observation),
                "reasons": reasons,
            }

        environment = observation["environment"]
        remote_url = str(environment["remote_url"])
        current = self.inspect(observation)
        if current["status"] == "ready":
            return {
                "status": "resumed",
                "path": str(self.checkout_path),
                "branch": self.expected_branch(observation),
                "source_head": environment["source_head"],
                "task_contract_sha256": observation["task"]["task_contract_sha256"],
                "reasons": [],
            }
        if current["status"] == "unmanaged_exact":
            self._write_manifest(observation, remote_url)
            verified = self.inspect(observation)
            if verified["status"] != "ready":
                raise RealCheckoutError("exact existing checkout could not be adopted safely")
            return {
                "status": "resumed",
                "path": str(self.checkout_path),
                "branch": self.expected_branch(observation),
                "source_head": environment["source_head"],
                "task_contract_sha256": observation["task"]["task_contract_sha256"],
                "reasons": [],
            }
        if current["status"] == "conflict":
            return {
                "status": "conflict_requires_human",
                "path": str(self.checkout_path),
                "branch": self.expected_branch(observation),
                "reasons": list(current["reasons"]),
            }

        self.checkout_root.mkdir(parents=True, exist_ok=True)
        staging_parent = Path(
            tempfile.mkdtemp(
                prefix=f".{self.task_id}.checkout-",
                dir=str(self.checkout_root),
            )
        )
        staging_checkout = staging_parent / self.task_id
        try:
            _run(
                (
                    "git",
                    "clone",
                    "--no-local",
                    "--no-checkout",
                    "--origin",
                    "origin",
                    remote_url,
                    str(staging_checkout),
                ),
                cwd=self.checkout_root,
                timeout_seconds=900.0,
            )
            _git(staging_checkout, "config", "core.longpaths", "true")
            observed_head = str(environment["source_head"])
            remote_main = _git_text(
                staging_checkout,
                "rev-parse",
                "--verify",
                "refs/remotes/origin/main",
            )
            if remote_main != observed_head:
                raise RealCheckoutError(
                    "remote main moved during checkout preparation; rerun observation"
                )
            _git(
                staging_checkout,
                "switch",
                "-c",
                self.expected_branch(observation),
                observed_head,
            )
            self._validate_new_clone(staging_checkout, observation, remote_url)
            if self.checkout_path.exists():
                return {
                    "status": "conflict_requires_human",
                    "path": str(self.checkout_path),
                    "branch": self.expected_branch(observation),
                    "reasons": [
                        "canonical checkout path appeared during preparation; "
                        "no overwrite occurred"
                    ],
                }
            staging_checkout.rename(self.checkout_path)
            self._write_manifest(observation, remote_url)
            verified = self.inspect(observation)
            if verified["status"] != "ready":
                raise RealCheckoutError(
                    "published checkout failed final identity verification"
                )
            return {
                "status": "created",
                "path": str(self.checkout_path),
                "branch": self.expected_branch(observation),
                "source_head": environment["source_head"],
                "task_contract_sha256": observation["task"]["task_contract_sha256"],
                "reasons": [],
            }
        finally:
            if staging_parent.exists():
                shutil.rmtree(staging_parent, ignore_errors=True)
