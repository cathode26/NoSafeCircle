"""Real read-only repository and TaskGraph observation for TaskReviewAgent."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from .contracts import (
    TASK_REVIEW_SCHEMA_VERSION,
    TaskReviewContractError,
    semantic_sha256,
    validate_task_id,
)


class RealObservationError(TaskReviewContractError):
    """Raised when committed repository facts cannot be observed safely."""


def _decode(data: bytes, *, label: str, allow_bom: bool = False) -> str:
    encoding = "utf-8-sig" if allow_bom else "utf-8"
    try:
        return data.decode(encoding)
    except UnicodeDecodeError as exc:
        raise RealObservationError(f"{label} was not valid {encoding}") from exc


def _command_detail(result: subprocess.CompletedProcess[bytes]) -> str:
    parts: list[str] = []
    for label, data in (("stdout", result.stdout), ("stderr", result.stderr)):
        text = _decode(data or b"", label=label).strip()
        if text:
            parts.append(f"{label}: {text}")
    return "\n".join(parts)


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout_seconds: float = 300.0,
) -> subprocess.CompletedProcess[bytes]:
    if not args or any(type(item) is not str or not item for item in args):
        raise RealObservationError("subprocess arguments must be non-empty exact strings")
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
        raise RealObservationError(
            f"command could not be executed safely: {' '.join(args)}"
        ) from exc
    if check and result.returncode != 0:
        detail = _command_detail(result)
        raise RealObservationError(
            f"command failed ({result.returncode}): {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def _git(
    root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    return _run(("git", "-C", str(root), *args), cwd=root, check=check)


def _git_text(root: Path, *args: str, check: bool = True) -> str:
    return _decode(_git(root, *args, check=check).stdout, label="git stdout").strip()


def _json_object(data: bytes, *, label: str, allow_bom: bool = False) -> dict[str, Any]:
    try:
        value = json.loads(_decode(data, label=label, allow_bom=allow_bom))
    except json.JSONDecodeError as exc:
        raise RealObservationError(f"{label} was not valid JSON") from exc
    if not isinstance(value, dict):
        raise RealObservationError(f"{label} must contain one JSON object")
    return value


def _stable_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


class RealTaskObserver:
    """Read committed facts without changing Git, TaskGraph, task, or checkout state."""

    def __init__(self, source: Path | str, task_id: str) -> None:
        self.task_id = validate_task_id(task_id)
        candidate = Path(source)
        if not candidate.exists() or not candidate.is_dir():
            raise RealObservationError(f"source repository directory does not exist: {candidate}")
        resolved = candidate.resolve()
        top_level = _run(
            ("git", "-C", str(resolved), "rev-parse", "--show-toplevel"),
            cwd=resolved,
        )
        root_text = _decode(top_level.stdout, label="git repository root").strip()
        if not root_text:
            raise RealObservationError("git rev-parse returned an empty repository root")
        self.root = Path(root_text).resolve()
        self.taskcontrol_path = self.root / "Pipeline" / "TaskGraph" / "taskcontrol.py"
        if not self.taskcontrol_path.is_file():
            raise RealObservationError(
                f"TaskGraph taskcontrol entry point is missing: {self.taskcontrol_path}"
            )
        self.action_log: list[str] = []
        self.last_observation: dict[str, Any] | None = None
        self._clean_observation_cache_key: tuple[str, str, str, str | None] | None = None
        self._clean_observation_cache: dict[str, Any] | None = None

    def _taskcontrol(
        self,
        *args: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        return _run(
            (sys.executable, str(self.taskcontrol_path), *args),
            cwd=self.root,
            check=check,
        )

    def _committed_task(self) -> tuple[str, bytes, dict[str, Any]]:
        path = f"Tasks/{self.task_id}.yaml"
        result = _git(self.root, "show", f"HEAD:{path}", check=False)
        if result.returncode != 0:
            detail = _command_detail(result)
            raise RealObservationError(
                f"committed task contract is missing for {self.task_id}: {path}"
                + (f"\n{detail}" if detail else "")
            )
        task = _json_object(result.stdout, label=path, allow_bom=True)
        if task.get("id") != self.task_id:
            raise RealObservationError(
                f"committed task identity mismatch: expected {self.task_id}, "
                f"found {task.get('id')!r}"
            )
        return path, result.stdout, task

    def _state(self, task_id: str) -> tuple[dict[str, Any] | None, str | None]:
        result = self._taskcontrol("state", task_id, "--json", check=False)
        if result.returncode != 0:
            detail = _command_detail(result)
            return None, (
                f"taskcontrol state failed for {task_id} ({result.returncode})"
                + (f": {detail}" if detail else "")
            )
        try:
            state = _json_object(result.stdout, label=f"taskcontrol state {task_id}")
        except RealObservationError as exc:
            return None, str(exc)
        if state.get("task_id") != task_id:
            return None, (
                f"taskcontrol state identity mismatch for {task_id}: "
                f"{state.get('task_id')!r}"
            )
        return state, None

    def observe_goal_state(self) -> dict[str, Any]:
        self.action_log.append("observe_goal_state")

        head = _git_text(self.root, "rev-parse", "--verify", "HEAD")
        tree = _git_text(self.root, "rev-parse", "HEAD^{tree}")
        branch_result = _git(
            self.root,
            "symbolic-ref",
            "--quiet",
            "--short",
            "HEAD",
            check=False,
        )
        branch = (
            _decode(branch_result.stdout, label="git branch").strip()
            if branch_result.returncode == 0
            else "(detached)"
        )
        origin_main_result = _git(
            self.root,
            "rev-parse",
            "--verify",
            "refs/remotes/origin/main",
            check=False,
        )
        origin_main = (
            _decode(origin_main_result.stdout, label="origin/main").strip()
            if origin_main_result.returncode == 0
            else None
        )
        status_text = _git_text(
            self.root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        status_lines = _stable_lines(status_text)
        controller_clean = not status_lines

        cache_key = (head, tree, branch, origin_main)
        if (
            controller_clean
            and self._clean_observation_cache_key == cache_key
            and self._clean_observation_cache is not None
        ):
            self.last_observation = json.loads(
                json.dumps(
                    self._clean_observation_cache,
                    ensure_ascii=False,
                    allow_nan=False,
                )
            )
            return json.loads(
                json.dumps(self.last_observation, ensure_ascii=False, allow_nan=False)
            )
        if not controller_clean:
            self._clean_observation_cache_key = None
            self._clean_observation_cache = None

        validation_result = self._taskcontrol("validate", check=False)
        validation_stdout = _decode(
            validation_result.stdout,
            label="taskcontrol validate stdout",
        ).strip()
        validation_stderr = _decode(
            validation_result.stderr,
            label="taskcontrol validate stderr",
        ).strip()
        taskgraph_valid = (
            validation_result.returncode == 0
            and "taskcontrol validate: PASS" in validation_stdout
        )

        task_path, task_bytes, task = self._committed_task()
        task_contract_sha256 = hashlib.sha256(task_bytes).hexdigest()

        errors: list[str] = []
        if not taskgraph_valid:
            errors.append(
                "TaskGraph validation failed"
                + (
                    f": {validation_stderr or validation_stdout}"
                    if validation_stderr or validation_stdout
                    else ""
                )
            )

        task_state, task_state_error = self._state(self.task_id)
        if task_state_error is not None:
            errors.append(task_state_error)

        raw_dependencies = task.get("depends_on", [])
        if not isinstance(raw_dependencies, list) or any(
            type(item) is not str or not item for item in raw_dependencies
        ):
            raise RealObservationError(
                f"{task_path} depends_on must be an array of non-empty task IDs"
            )

        dependency_states: list[dict[str, Any]] = []
        for dependency_id in raw_dependencies:
            validate_task_id(dependency_id)
            dependency_state, dependency_error = self._state(dependency_id)
            if dependency_error is not None:
                errors.append(dependency_error)
                dependency_states.append(
                    {
                        "task_id": dependency_id,
                        "title": None,
                        "state": "unknown",
                        "head_commit": None,
                        "head_tree": None,
                        "selected_record_id": None,
                        "dirty_worktree": None,
                        "findings": [],
                        "error": dependency_error,
                    }
                )
                continue
            assert dependency_state is not None
            dependency_states.append(
                {
                    "task_id": dependency_id,
                    "title": dependency_state.get("title"),
                    "state": dependency_state.get("state"),
                    "head_commit": dependency_state.get("head_commit"),
                    "head_tree": dependency_state.get("head_tree"),
                    "selected_record_id": dependency_state.get("selected_record_id"),
                    "dirty_worktree": dependency_state.get("dirty_worktree"),
                    "findings": dependency_state.get("findings") or [],
                    "error": None,
                }
            )

        dependencies_conformant = all(
            item.get("state") == "conformant" and item.get("error") is None
            for item in dependency_states
        )
        if not raw_dependencies:
            dependencies_conformant = True

        if task_state is not None and task_state.get("head_commit") != head:
            errors.append(
                "taskcontrol state was evaluated against a different HEAD: "
                f"{task_state.get('head_commit')!r} != {head!r}"
            )
        for item in dependency_states:
            dependency_head = item.get("head_commit")
            if dependency_head is not None and dependency_head != head:
                errors.append(
                    f"dependency {item['task_id']} state used a different HEAD: "
                    f"{dependency_head!r} != {head!r}"
                )

        task_payload = {
            "task_id": self.task_id,
            "title": task.get("title"),
            "contract_path": task_path,
            "contract_revision": task.get("contract_revision"),
            "contract_disposition": task.get("contract_disposition"),
            "kind": task.get("kind"),
            "type": task.get("type"),
            "execution_scope": task.get("execution_scope"),
            "execution_reason": task.get("execution_reason"),
            "decomposition_state": task.get("decomposition_state"),
            "decomposition_reason": task.get("decomposition_reason"),
            "derived_state": (
                task_state.get("state") if task_state is not None else "unknown"
            ),
            "dependencies_conformant": dependencies_conformant,
            "depends_on": list(raw_dependencies),
            "dependency_states": dependency_states,
            "exclusive_resources": task.get("exclusive_resources") or [],
            "acceptance_criteria": task.get("acceptance_criteria") or [],
            "completion_gates": task.get("completion_gates") or [],
            "downstream_integration_obligations": (
                task.get("downstream_integration_obligations") or []
            ),
            "source_head": head,
            "source_tree": tree,
            "task_contract_sha256": task_contract_sha256,
            "state_findings": (
                task_state.get("findings") if task_state is not None else []
            ),
            "state_dirty_worktree": (
                task_state.get("dirty_worktree") if task_state is not None else None
            ),
        }

        environment_payload = {
            "ready": taskgraph_valid and task_state is not None and not errors,
            "controller_clean": controller_clean,
            "taskgraph_valid": taskgraph_valid,
            "provider_auth_required": False,
            "provider_auth_available": None,
            "execution_crew_mode": "not_observed",
            "repository_root": str(self.root),
            "branch": branch,
            "source_head": head,
            "source_tree": tree,
            "origin_main": origin_main,
            "git_status": status_lines,
            "taskgraph_validation": {
                "returncode": validation_result.returncode,
                "stdout": validation_stdout,
                "stderr": validation_stderr,
            },
            "errors": errors,
        }

        identity = {
            "environment": environment_payload,
            "task": task_payload,
        }
        observation = {
            "schema_version": TASK_REVIEW_SCHEMA_VERSION,
            "observation_authority": "real_read_only",
            "observation_sha256": semantic_sha256(identity),
            **identity,
            "checkout": {
                "status": "not_observed",
                "path": None,
                "branch": None,
                "clean": None,
            },
            "repository_scope_facts": {
                "status": "not_observed",
                "authority": "not_yet_implemented",
            },
            "accepted_plan_id": None,
            "execution_run": None,
        }
        self.last_observation = json.loads(
            json.dumps(observation, ensure_ascii=False, allow_nan=False)
        )
        if (
            controller_clean
            and taskgraph_valid
            and task_state is not None
            and not errors
        ):
            self._clean_observation_cache_key = cache_key
            self._clean_observation_cache = json.loads(
                json.dumps(self.last_observation, ensure_ascii=False, allow_nan=False)
            )
        return json.loads(
            json.dumps(self.last_observation, ensure_ascii=False, allow_nan=False)
        )
