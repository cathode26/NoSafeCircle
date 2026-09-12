"""Resumable outer loop for the conversation-operated task tools.

The controller chooses one deterministic next transition at a time.  Existing
AssistantControl components continue to own checkouts, provider execution,
candidate validation, Unity materialization, review and local integration.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Mapping, Sequence

from Pipeline.AssistantControl.automation_policy import (
    HUMAN_ONLY_TASKS,
    committed_json,
    is_synthetic_gauntlet,
)
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.dependencies import approved_integration, inspect_dependencies
from Pipeline.AssistantControl.inspect_project import changes, git
from Pipeline.AssistantControl.process_identity import identify
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan, validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import (
    _acquire_liveness_lock,
    _release_liveness_lock,
)


SCHEMA_VERSION = "assistant-graph-controller/v1"
OWNER_SCHEMA_VERSION = "assistant-graph-controller-owner/v1"
_TERMINAL_FAILURES = {
    "changes_requested", "validation_failed", "materialization_failed",
    "needs_materialization",
}
_WORKER_TERMINAL = {"succeeded", "failed", "stopped", "spawn_failed"}
_GRAPH_PATH_PREFIXES = (
    "tasks/", "pipeline/taskgraph/",
    "pipeline/taskreviewagent/authoritative_validation_policy.json",
)
_FILTER_RE = re.compile(r"\bfilter\s+([A-Za-z_][A-Za-z0-9_.+`]*)")
DELEGATE_SAFE_ACTIONS = frozenset({
    "prepare", "refresh_prepared", "scope",
})


class ControllerOwnerActiveError(RuntimeError):
    """Another process holds the graph controller lock."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _task_key(task_id: str) -> tuple[int, str]:
    try:
        return int(task_id.removeprefix("NSC-")), task_id
    except ValueError:
        return 2**31, task_id


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"AssistantControl record is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"AssistantControl record is not an object: {path}")
    return value


def _blob_exists(source: Path, commit: str, path: str) -> bool:
    try:
        return git(source, "cat-file", "-e", f"{commit}:{path}") == b""
    except RuntimeError:
        return False


def _test_filters(source: Path, task: Mapping[str, Any], commit: str) -> list[str]:
    policy = committed_json(
        source, commit,
        "Pipeline/TaskReviewAgent/authoritative_validation_policy.json",
    ) or {}
    entry = (policy.get("tasks") or {}).get(task.get("id"))
    filters: list[str] = []
    if (isinstance(entry, Mapping)
            and entry.get("task_contract_sha256") == task.get("task_contract_sha256")):
        values = entry.get("test_filters") or {}
        if isinstance(values, Mapping):
            filters.extend(value for value in values.values()
                           if isinstance(value, str) and value)
    if not filters:
        for gate in task.get("completion_gates") or []:
            if not isinstance(gate, Mapping):
                continue
            match = _FILTER_RE.search(str(gate.get("requirement") or ""))
            if match:
                filters.append(match.group(1))
    return list(dict.fromkeys(filters))


def _test_sources(source: Path, commit: str) -> list[str]:
    raw = git(source, "ls-tree", "-r", "--name-only", "-z", commit, "--", "Assets", "Packages")
    return sorted(
        path for path in raw.decode("utf-8", "surrogateescape").split("\0")
        if path.casefold().endswith(".cs") and "/tests/" in f"/{path.casefold()}"
    )


def _resolve_test_paths(source: Path, task: Mapping[str, Any], commit: str) -> list[str]:
    sources = _test_sources(source, commit)
    by_stem: dict[str, list[str]] = {}
    for path in sources:
        by_stem.setdefault(PurePosixPath(path).stem, []).append(path)
    resolved: list[str] = []
    for test_filter in _test_filters(source, task, commit):
        matches: list[str] = []
        for name in reversed(test_filter.split(".")):
            if name in by_stem:
                matches = by_stem[name]
                break
        if len(matches) != 1:
            raise ValueError(
                f"{task.get('id')} validation filter {test_filter!r} does not resolve "
                "to exactly one committed C# test file; provide a scope override"
            )
        resolved.append(matches[0])
    return list(dict.fromkeys(resolved))


def automatic_scope_plan(
    source: Path, task: Mapping[str, Any], commit: str,
) -> ExecutionScopePlan:
    """Build a conservative exact-file plan from committed task authority."""
    implementation: list[str] = []
    tests: list[str] = []
    for resource in task.get("exclusive_resources") or []:
        if not isinstance(resource, str):
            continue
        kind, separator, raw_path = resource.partition(":")
        if not separator or kind not in {"repo-file", "unity-scene"}:
            continue
        path = raw_path.replace("\\", "/").strip("/")
        if not path or path.endswith("/"):
            raise ValueError(f"{task.get('id')} has a non-file resource; provide a scope override")
        # Unity .meta companions are generated and authenticated by the existing
        # candidate path.  ExecutionScopePlan deliberately never grants a model
        # direct write authority to them.
        if PurePosixPath(path).suffix.casefold() == ".meta":
            continue
        (tests if "/tests/" in f"/{path.casefold()}" else implementation).append(path)
    for path in _resolve_test_paths(source, task, commit):
        if path not in tests:
            tests.append(path)
    if not implementation:
        raise ValueError(f"{task.get('id')} has no exact implementation files for automatic scope")
    if not tests:
        raise ValueError(f"{task.get('id')} has no resolvable committed C# test for automatic scope")
    existing_impl = tuple(path for path in implementation if _blob_exists(source, commit, path))
    new_impl = tuple(path for path in implementation if path not in existing_impl)
    existing_tests = tuple(path for path in tests if _blob_exists(source, commit, path))
    new_tests = tuple(path for path in tests if path not in existing_tests)
    return ExecutionScopePlan(existing_impl, new_impl, existing_tests, new_tests)


def scope_plan(
    source: Path, task: Mapping[str, Any], commit: str, override_dir: Path | None,
) -> ExecutionScopePlan:
    if override_dir is not None:
        path = override_dir / f"{task['id']}.json"
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            return ExecutionScopePlan.from_dict(value)
    return automatic_scope_plan(source, task, commit)


@dataclass(frozen=True)
class GraphPolicy:
    targets: tuple[str, ...]
    human_review_tasks: frozenset[str] = HUMAN_ONLY_TASKS
    auto_approve_gauntlet: bool = False
    capacity: int = 1
    target_branch: str | None = None
    scope_dir: Path | None = None
    decomposition_providers: str = "claude,codex"
    compose_project: str = "nosafecircle"

    def __post_init__(self) -> None:
        if not self.targets:
            raise ValueError("Graph controller requires at least one explicit target task")
        for task_id in (*self.targets, *self.human_review_tasks):
            validate_task_id(task_id)
        if type(self.capacity) is not int or isinstance(self.capacity, bool) or self.capacity < 1:
            raise ValueError("Graph controller capacity must be positive")
        if "NSC-042" not in self.human_review_tasks:
            raise ValueError("NSC-042 is permanently reserved for human review")


class GraphController:
    def __init__(
        self, manager: Checkouts, policy: GraphPolicy,
        worker_config: Mapping[str, Any], *,
        execution_authorized: bool = False,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.manager = manager
        self.policy = policy
        self.worker_config = json.loads(json.dumps(dict(worker_config)))
        self._worker_config_bytes = _json_bytes(self.worker_config)
        self.execution_authorized = execution_authorized is True
        self.sleep = sleep
        self.state_path = manager.records / "graph-controller.json"
        self.event_path = manager.records / "graph-controller-events.jsonl"
        self.owner_path = manager.records / "graph-controller-owner.json"
        self.lock_path = manager.records / "graph-controller.lock"
        self._active_invocation_id: str | None = None

    def _policy_fields(self) -> dict[str, Any]:
        return {
            **vars(self.policy),
            "targets": list(self.policy.targets),
            "human_review_tasks": sorted(self.policy.human_review_tasks, key=_task_key),
            "scope_dir": (
                str(self.policy.scope_dir.resolve())
                if self.policy.scope_dir is not None else None
            ),
            "provider_spend_authorized": self.execution_authorized,
        }

    def _append_event(self, payload: Mapping[str, Any]) -> None:
        self.event_path.parent.mkdir(parents=True, exist_ok=True)
        with self.event_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(
                dict(payload), sort_keys=True, separators=(",", ":"),
            ) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _acquire_controller_lock(self):
        try:
            return _acquire_liveness_lock(self.lock_path)
        except (BlockingIOError, PermissionError) as exc:
            raise ControllerOwnerActiveError(
                f"Graph controller lock is already held: {self.lock_path}"
            ) from exc

    @contextmanager
    def _controller_owner(
        self, invocation_id: str, *, max_actions: int,
        allowed_actions: frozenset[str] | None,
    ) -> Iterator[None]:
        held_lock = self._acquire_controller_lock()
        owner: dict[str, Any] = {
            "invocation_id": invocation_id,
            "pid": os.getpid(),
        }
        self._active_invocation_id = invocation_id
        started = False
        outcome = "startup_failed"
        error_type = None
        try:
            policy = self._policy_fields()
            policy_sha256 = _sha256(_json_bytes(policy))
            config_sha256 = _sha256(self._worker_config_bytes)
            source_commit, source_branch = self._source_snapshot()
            preflight = None
            state = _read_json(self.state_path)
            if state and state.get("status") == "preflight":
                plan = state.get("preflight_plan")
                preflight = {
                    "source_commit": source_commit,
                    "source_branch": source_branch,
                    "plan_sha256": _sha256(_json_bytes(plan)),
                    "policy_sha256": policy_sha256,
                    "worker_config_sha256": config_sha256,
                } if isinstance(plan, Mapping) else None
                if (
                    not isinstance(plan, Mapping)
                    or plan.get("source") != str(self.manager.source)
                    or plan.get("source_commit") != source_commit
                    or plan.get("target_branch") != source_branch
                    or plan.get("targets") != list(self.policy.targets)
                    or state.get("preflight_binding") != preflight
                ):
                    raise ValueError(
                        "Graph preflight no longer matches Source or controller policy/config bytes"
                    )
            process_identity = identify(os.getpid()) if os.name == "nt" else None
            if os.name == "nt" and process_identity is None:
                raise RuntimeError("Graph controller could not identify its current process")
            owner.update({
                "schema_version": OWNER_SCHEMA_VERSION,
                "status": "controller_started",
                "process_identity": process_identity,
                "started_at_utc": _now(),
                "source": str(self.manager.source),
                "source_commit": source_commit,
                "source_branch": source_branch,
                "targets": list(self.policy.targets),
                "checkout_root": str(self.manager.root),
                "capacity": self.policy.capacity,
                "lock_path": str(self.lock_path),
                "policy": policy,
                "policy_sha256": policy_sha256,
                "worker_config_sha256": config_sha256,
                "max_actions": max_actions,
                "allowed_actions": (
                    sorted(allowed_actions) if allowed_actions is not None else None
                ),
                "preflight_binding": preflight,
            })
            write_record(self.owner_path, owner)
            self._append_event({
                **owner, "event": "controller_started",
                "at_utc": owner["started_at_utc"],
            })
            started = True
            yield
            outcome = "returned"
        except KeyboardInterrupt:
            outcome = "interrupted" if started else "startup_interrupted"
            error_type = "KeyboardInterrupt"
            raise
        except BaseException as exc:
            outcome = "exception" if started else "startup_failed"
            error_type = type(exc).__name__
            raise
        finally:
            released = {
                "schema_version": OWNER_SCHEMA_VERSION,
                "status": "controller_released",
                "invocation_id": invocation_id,
                "pid": owner["pid"],
                "process_identity": owner.get("process_identity"),
                "lock_path": str(self.lock_path),
                "released_at_utc": _now(),
                "outcome": outcome,
                "error_type": error_type,
            }
            # Release diagnostics are independent and never mask the outcome.
            try:
                self._append_event({
                    **released, "event": "controller_released",
                    "at_utc": released["released_at_utc"],
                })
            except BaseException:
                pass
            try:
                write_record(self.owner_path, released)
            except BaseException:
                pass
            self._active_invocation_id = None
            _release_liveness_lock(held_lock)

    def _source_snapshot(self) -> tuple[str, str]:
        head = git(self.manager.source, "rev-parse", "HEAD").decode().strip()
        branch = git(self.manager.source, "branch", "--show-current").decode().strip()
        if not branch:
            raise ValueError("Graph controller requires Source on an attached branch")
        target = self.policy.target_branch or branch
        if branch != target:
            raise ValueError(f"Source is on {branch!r}, expected target branch {target!r}")
        dirty_graph = sorted({
            str(item.get(key)).replace("\\", "/")
            for item in changes(self.manager.source)
            for key in ("path", "original_path")
            if isinstance(item.get(key), str)
            and str(item[key]).replace("\\", "/").casefold().startswith(_GRAPH_PATH_PREFIXES)
        })
        if dirty_graph:
            raise ValueError("Committed task graph has local edits: " + ", ".join(dirty_graph))
        return head, target

    def _contracts(self, head: str) -> dict[str, dict[str, Any]]:
        raw = git(self.manager.source, "ls-tree", "-r", "--name-only", "-z", head, "--", "Tasks")
        ids = sorted({
            PurePosixPath(path).stem
            for path in raw.decode("utf-8", "surrogateescape").split("\0")
            if path.startswith("Tasks/NSC-") and path.endswith(".yaml")
        }, key=_task_key)
        result = {task_id: load_committed_task(self.manager.source, task_id, commit=head)
                  for task_id in ids}
        missing = sorted(set(self.policy.targets) - set(result), key=_task_key)
        if missing:
            raise ValueError("Target tasks do not exist at Source HEAD: " + ", ".join(missing))
        return result

    def _in_scope(self, tasks: Mapping[str, Mapping[str, Any]]) -> list[str]:
        selected = set(self.policy.targets)
        changed = True
        while changed:
            changed = False
            for task_id in tuple(selected):
                task = tasks.get(task_id)
                if task is None:
                    raise ValueError(f"Selected task is missing from committed graph: {task_id}")
                for dependency in task.get("depends_on") or []:
                    if not isinstance(dependency, str) or dependency not in tasks:
                        raise ValueError(
                            f"{task_id} references missing committed dependency {dependency!r}"
                        )
                    if dependency not in selected:
                        selected.add(dependency)
                        changed = True
            for task_id, task in tasks.items():
                if task_id not in selected and task.get("parent") in selected:
                    selected.add(task_id)
                    changed = True
        return sorted(selected, key=_task_key)

    def _record(self, task_id: str) -> dict[str, Any] | None:
        return _read_json(self.manager.records / f"{task_id}.json")

    def _decomposition(self, task_id: str) -> dict[str, Any] | None:
        return _read_json(self.manager.records / f"{task_id}.decomposition.json")

    def _applied_decomposition(
        self, task_id: str, task: Mapping[str, Any], head: str,
    ) -> bool:
        """Prove that the current decomposed parent came from our retained D1C receipt."""
        record = self._decomposition(task_id)
        if not isinstance(record, Mapping):
            return False
        applied_commit = record.get("applied_commit")
        child_ids = record.get("child_ids")
        application = record.get("application")
        if (
            record.get("status") != "applied"
            or record.get("task_id") != task_id
            or record.get("source") != str(self.manager.source)
            or not isinstance(applied_commit, str)
            or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", applied_commit)
            or not isinstance(child_ids, list)
            or not child_ids
            or not all(isinstance(child, str) for child in child_ids)
            or not isinstance(application, Mapping)
            or application.get("new_commit_sha") != applied_commit
        ):
            return False
        try:
            git(self.manager.source, "merge-base", "--is-ancestor", applied_commit, head)
            applied_parent = load_committed_task(
                self.manager.source, task_id, commit=applied_commit,
            )
        except (OSError, RuntimeError, ValueError, TypeError):
            return False
        expected_children = sorted(child_ids, key=_task_key)
        return (
            task.get("decomposition_state") == "decomposed"
            and applied_parent.get("decomposition_state") == "decomposed"
            and sorted(task.get("decomposition_children") or [], key=_task_key)
            == expected_children
            and sorted(applied_parent.get("decomposition_children") or [], key=_task_key)
            == expected_children
        )

    def _task_complete(
        self, task_id: str, tasks: Mapping[str, Mapping[str, Any]], head: str,
        memo: dict[str, bool], visiting: set[str],
    ) -> bool:
        if task_id in memo:
            return memo[task_id]
        if task_id in visiting or task_id not in tasks:
            return False
        visiting.add(task_id)
        task = tasks[task_id]
        complete = False
        if task.get("decomposition_state") == "decomposed":
            children = task.get("decomposition_children") or []
            complete = self._applied_decomposition(task_id, task, head) and bool(children) and all(
                self._task_complete(child, tasks, head, memo, visiting)
                for child in children if isinstance(child, str)
            ) and len(children) == len([child for child in children if isinstance(child, str)])
        if not complete:
            complete = approved_integration(
                self.manager.source, self.manager.records, task_id, head,
            ) is not None
        if not complete and self._record(task_id) is None and self._decomposition(task_id) is None:
            try:
                state = inspect_dependencies(
                    self.manager.source, task_id, self.manager.root,
                ).get("task_state", {}).get("state")
                # Committed delivery evidence may satisfy work completed before
                # this AssistantControl run. Merely finding output files in
                # Source (needs_testing) cannot replace an integration receipt.
                complete = state == "conformant"
            except (OSError, RuntimeError, ValueError, TypeError):
                complete = False
        visiting.remove(task_id)
        memo[task_id] = complete
        return complete

    def _dependencies_ready(
        self, task: Mapping[str, Any], tasks: Mapping[str, Mapping[str, Any]],
        head: str, memo: dict[str, bool],
    ) -> tuple[bool, list[str]]:
        blocked = [dependency for dependency in task.get("depends_on") or []
                   if not self._task_complete(dependency, tasks, head, memo, set())]
        return not blocked, blocked

    def _reservations(self) -> dict[str, dict[str, Any]]:
        from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
        _, path = _source_registry_paths(self.manager.source)
        return {item["task_id"]: item for item in _read_registry(path, self.manager.source)["reservations"]
                if isinstance(item, dict) and isinstance(item.get("task_id"), str)}

    def plan(self) -> dict[str, Any]:
        head, branch = self._source_snapshot()
        tasks = self._contracts(head)
        selected = self._in_scope(tasks)
        reservations = self._reservations()
        memo: dict[str, bool] = {}
        actions: list[dict[str, Any]] = []
        complete: list[str] = []
        waiting_human: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []

        for task_id in selected:
            task = tasks[task_id]
            if task.get("contract_disposition") != "active":
                continue
            if self._task_complete(task_id, tasks, head, memo, set()):
                complete.append(task_id)
                continue
            dependencies_ready, blocked_dependencies = self._dependencies_ready(
                task, tasks, head, memo,
            )
            if not dependencies_ready:
                blocked.append({"task_id": task_id, "reason": "dependencies", "dependencies": blocked_dependencies})
                continue
            execution_scope = task.get("execution_scope")
            if execution_scope == "needs_execution_decomposition":
                receipt = self._decomposition(task_id)
                status = (receipt or {}).get("status")
                if receipt is None:
                    actions.append({"kind": "decompose", "task_id": task_id})
                elif status == "review_ready":
                    actions.append({"kind": "apply_decomposition", "task_id": task_id,
                                    "run_id": receipt.get("run_id"),
                                    "source_commit": head})
                elif status == "running":
                    blocked.append({"task_id": task_id, "reason": "decomposition_already_running"})
                elif status == "failed":
                    blocked.append({"task_id": task_id, "reason": "decomposition_failed",
                                    "error": receipt.get("error")})
                else:
                    blocked.append({"task_id": task_id, "reason": f"decomposition_{status or 'invalid'}"})
                continue
            if execution_scope == "not_applicable":
                blocked.append({"task_id": task_id, "reason": "aggregate_children_incomplete"})
                continue
            if execution_scope != "single_agent":
                blocked.append({"task_id": task_id, "reason": f"unsupported_execution_scope:{execution_scope}"})
                continue

            record = self._record(task_id)
            if record is None:
                actions.append({"kind": "prepare", "task_id": task_id, "source_commit": head})
                continue
            status = record.get("status")
            if status == "preparing":
                actions.append({"kind": "prepare", "task_id": task_id,
                                "source_commit": head})
                continue
            if status == "integrated":
                blocked.append({"task_id": task_id, "reason": "integration_receipt_not_current"})
                continue
            candidate = record.get("candidate") or {}
            validation_failure = record.get("candidate_validation_failure") or {}
            if (status == "validation_failed" and candidate
                    and validation_failure.get("candidate_commit") == candidate.get("commit")
                    and validation_failure.get("validation_error")
                    == f"authoritative validation policy for {task_id} is stale"
                    and record.get("approval") is None
                    and record.get("human_review") is None
                    and record.get("source_commit") != head):
                actions.append({"kind": "sync_candidate", "task_id": task_id,
                                "candidate_commit": candidate.get("commit"),
                                "source_commit": head})
                continue
            if status in _TERMINAL_FAILURES:
                blocked.append({"task_id": task_id, "reason": str(status)})
                continue
            if candidate:
                commit = candidate.get("commit")
                if status == "awaiting_human":
                    if task_id in self.policy.human_review_tasks:
                        waiting_human.append({"task_id": task_id, "candidate_commit": commit,
                                              "checkout": record.get("checkout")})
                    elif self.policy.auto_approve_gauntlet and is_synthetic_gauntlet(
                            self.manager.source, task_id, head):
                        if record.get("source_commit") != head:
                            actions.append({"kind": "sync_candidate", "task_id": task_id,
                                            "candidate_commit": commit, "source_commit": head})
                        else:
                            actions.append({"kind": "auto_approve", "task_id": task_id,
                                            "candidate_commit": commit})
                    else:
                        waiting_human.append({"task_id": task_id, "candidate_commit": commit,
                                              "checkout": record.get("checkout")})
                    continue
                if status == "approved":
                    if record.get("source_commit") != head:
                        actions.append({"kind": "sync_candidate", "task_id": task_id,
                                        "candidate_commit": commit, "source_commit": head})
                    else:
                        actions.append({"kind": "integrate", "task_id": task_id,
                                        "source_commit": head, "target_branch": branch})
                    continue
                if status == "integrating":
                    actions.append({"kind": "integrate", "task_id": task_id,
                                    "source_commit": head, "target_branch": branch})
                    continue
                blocked.append({"task_id": task_id, "reason": f"candidate_state:{status}"})
                continue

            worker = record.get("worker") or record.get("launch")
            if isinstance(worker, Mapping):
                worker_status = worker.get("status")
                if worker.get("capacity_released") is not True:
                    if worker_status in _WORKER_TERMINAL:
                        actions.append({"kind": "settle_worker", "task_id": task_id,
                                        "run_id": worker.get("run_id")})
                    else:
                        actions.append({"kind": "wait_worker", "task_id": task_id,
                                        "run_id": worker.get("run_id")})
                    continue
                if worker_status == "succeeded":
                    actions.append({"kind": "post_crew", "task_id": task_id,
                                    "crew_run_id": worker.get("crew_run_id")})
                else:
                    blocked.append({"task_id": task_id, "reason": f"worker_{worker_status}"})
                continue

            if record.get("source_commit") != head:
                actions.append({"kind": "refresh_prepared", "task_id": task_id,
                                "source_commit": head})
                continue
            scope = record.get("scope")
            if not isinstance(scope, Mapping):
                actions.append({"kind": "scope", "task_id": task_id, "source_commit": head})
                continue
            reservation = reservations.get(task_id)
            if reservation is None:
                run_id = f"assistant-{task_id.casefold()}-{str(scope.get('plan_id', 'scope'))[-12:]}"
                actions.append({"kind": "reserve", "task_id": task_id, "run_id": run_id})
            else:
                actions.append({"kind": "start_worker", "task_id": task_id,
                                "run_id": reservation.get("run_id"),
                                "lease_id": reservation.get("lease_id")})

        status = ("actionable" if actions else "awaiting_human" if waiting_human
                  else "complete" if len(complete) == len(selected)
                  else "blocked")
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "source": str(self.manager.source),
            "source_commit": head,
            "target_branch": branch,
            "targets": list(self.policy.targets),
            "in_scope": selected,
            "next_actions": actions,
            "complete": complete,
            "waiting_human": waiting_human,
            "blocked": blocked,
            "provider_spend_authorized": self.execution_authorized,
            "mutations_performed": False,
        }

    def _save_state(self, status: str, *, action: Mapping[str, Any] | None = None,
                    result: Mapping[str, Any] | None = None,
                    error: str | None = None) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        previous = _read_json(self.state_path) or {}
        history = list(previous.get("history") or [])[-99:]
        if action is not None:
            history.append({"at": _now(), "action": dict(action),
                            "invocation_id": self._active_invocation_id,
                            "result_status": (result or {}).get("status")})
        state = {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "invocation_id": self._active_invocation_id,
            "targets": list(self.policy.targets),
            "human_review_tasks": sorted(self.policy.human_review_tasks, key=_task_key),
            "auto_approve_gauntlet": self.policy.auto_approve_gauntlet,
            "current_action": dict(action) if action is not None else None,
            "last_error": error,
            "history": history,
            "updated_at": _now(),
        }
        if status == "preflight":
            if result is None:
                raise ValueError("Preflight state requires an exact graph plan")
            state["preflight_plan"] = dict(result)
            state["preflight_binding"] = {
                "source_commit": result.get("source_commit"),
                "source_branch": result.get("target_branch"),
                "plan_sha256": _sha256(_json_bytes(result)),
                "policy_sha256": _sha256(_json_bytes(self._policy_fields())),
                "worker_config_sha256": _sha256(self._worker_config_bytes),
            }
        write_record(self.state_path, state)

    def persist_preflight(self) -> dict[str, Any]:
        """Persist one read-only plan for viewer scope without executing an action."""

        held_lock = self._acquire_controller_lock()
        try:
            plan = self.plan()
            head, branch = self._source_snapshot()
            if (
                plan.get("schema_version") != SCHEMA_VERSION
                or plan.get("source") != str(self.manager.source)
                or plan.get("source_commit") != head
                or plan.get("target_branch") != branch
                or plan.get("targets") != list(self.policy.targets)
                or plan.get("mutations_performed") is not False
            ):
                raise ValueError(
                    "Graph preflight plan no longer matches the exact controller identity"
                )
            self._save_state("preflight", result=plan)
            return plan
        finally:
            _release_liveness_lock(held_lock)

    def _append_action_event(
        self, event: str, action: Mapping[str, Any], action_id: str,
        *, duration_seconds: float | None = None, result: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if self._active_invocation_id is None:
            raise RuntimeError("Graph action event requires an active controller invocation")
        payload = {
            "at_utc": _now(),
            "event": event,
            "invocation_id": self._active_invocation_id,
            "action_id": action_id,
            "kind": action.get("kind"),
            "task_id": action.get("task_id"),
            "run_id": action.get("run_id"),
            "provider": self.worker_config.get("provider"),
            "model": self.worker_config.get("execution_model"),
            "result_status": (result or {}).get("status"),
            "duration_seconds": duration_seconds,
            "error": error,
        }
        self._append_event(payload)

    def _execute_timed(self, action: Mapping[str, Any]) -> dict[str, Any]:
        action_id = uuid.uuid4().hex
        started = time.monotonic()
        self._append_action_event("action_started", action, action_id)
        try:
            result = self.execute(action)
        except BaseException as exc:
            self._append_action_event(
                "action_failed", action, action_id,
                duration_seconds=time.monotonic() - started,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        self._append_action_event(
            "action_completed", action, action_id,
            duration_seconds=time.monotonic() - started, result=result,
        )
        return result

    def _require_provider_authority(self) -> None:
        if not self.execution_authorized:
            raise ValueError("Graph provider work requires --authorize-provider-spend")

    def execute(self, action: Mapping[str, Any]) -> dict[str, Any]:
        if self._active_invocation_id is None:
            raise RuntimeError("Graph action requires an active controller invocation")
        kind, task_id = str(action["kind"]), str(action["task_id"])
        if kind == "prepare":
            return self.manager.prepare(task_id, expected_commit=str(action["source_commit"]))
        if kind == "refresh_prepared":
            from Pipeline.AssistantControl.prepared_refresh import refresh_prepared
            return refresh_prepared(self.manager, task_id, str(action["source_commit"]))
        if kind == "scope":
            from Pipeline.AssistantControl.scope import AssistantScopePlanner
            task = load_committed_task(self.manager.source, task_id, commit=str(action["source_commit"]))
            plan = scope_plan(self.manager.source, task, str(action["source_commit"]), self.policy.scope_dir)
            lease = f"assistant-{task_id.casefold()}-{uuid.uuid4().hex[:16]}-lease"
            return AssistantScopePlanner(self.manager).validate_and_persist(
                task_id, plan, lease_id=lease,
            )
        if kind == "reserve":
            from Pipeline.AssistantControl.admission import reserve
            return reserve(self.manager, task_id, str(action["run_id"]), capacity=self.policy.capacity)
        if kind == "start_worker":
            self._require_provider_authority()
            from Pipeline.AssistantControl.worker_launcher import start
            config = {**self.worker_config, "execution_authorized": True}
            return start(self.manager, task_id, str(action["run_id"]), str(action["lease_id"]),
                         config, execution_authorized=True)
        if kind == "wait_worker":
            from Pipeline.AssistantControl import worker_control
            timeout = float(self.worker_config.get("timeout_seconds", 900)) + 180
            deadline = time.monotonic() + timeout
            while True:
                observed = worker_control.status(self.manager, task_id)
                worker = observed.get("worker") or {}
                if worker.get("run_id") != action.get("run_id"):
                    raise ValueError("Worker identity changed while graph controller was waiting")
                if observed.get("host_identity_alive") is False:
                    return observed
                if observed.get("host_identity_alive") is None:
                    raise ValueError("Worker process identity cannot be verified")
                if time.monotonic() >= deadline:
                    return {**observed, "status": "worker_still_running"}
                self.sleep(1.0)
        if kind == "settle_worker":
            from Pipeline.AssistantControl.worker_settlement import settle_completed
            return settle_completed(self.manager, task_id, run_id=str(action["run_id"]))
        if kind == "post_crew":
            from Pipeline.AssistantControl.post_crew_workflow import run_post_crew_workflow
            record = self._record(task_id) or {}
            worker = record.get("worker") or record.get("launch") or {}
            config = worker.get("config") if isinstance(worker.get("config"), Mapping) else self.worker_config
            return run_post_crew_workflow(
                self.manager, task_id, str(action["crew_run_id"]), config,
            )
        if kind == "sync_candidate":
            from Pipeline.AssistantControl.source_update import synchronize_candidate
            return synchronize_candidate(
                self.manager, task_id, str(action["candidate_commit"]),
                str(action["source_commit"]),
            )
        if kind == "auto_approve":
            from Pipeline.AssistantControl.post_crew_workflow import run_post_crew_workflow
            from Pipeline.AssistantControl.review import ReviewGate
            record = self._record(task_id) or {}
            worker = record.get("worker") or record.get("launch") or {}
            crew_run = worker.get("crew_run_id")
            if not isinstance(crew_run, str) or not crew_run:
                candidate = record.get("candidate") or {}
                original = candidate.get("original_candidate") or {}
                crew_run = original.get("run_id") or candidate.get("run_id")
            if not isinstance(crew_run, str) or not crew_run:
                raise ValueError("Gauntlet candidate has no originating crew run")
            config = worker.get("config") if isinstance(worker.get("config"), Mapping) else self.worker_config
            post = run_post_crew_workflow(self.manager, task_id, crew_run, config)
            if post.get("status") != "awaiting_human":
                raise ValueError(f"Gauntlet candidate validation returned {post.get('status')}")
            candidate_commit = post.get("materialized_candidate_commit") or post.get("crew_candidate_commit")
            if candidate_commit != action.get("candidate_commit"):
                raise ValueError("Gauntlet candidate changed during automated validation")
            return ReviewGate(self.manager).approve_validated_gauntlet(
                task_id, tested_commit=candidate_commit,
            )
        if kind == "integrate":
            from Pipeline.AssistantControl.review import ReviewGate
            return ReviewGate(self.manager).integrate(
                task_id, expected_source_commit=str(action["source_commit"]),
                target_branch=str(action["target_branch"]),
            )
        if kind == "decompose":
            self._require_provider_authority()
            from Pipeline.AssistantControl import decomposition
            head = git(self.manager.source, "rev-parse", "HEAD").decode().strip()
            run_id = f"assistant-{task_id.casefold()}-decompose-{head[:12]}"
            return decomposition.run(
                self.manager, task_id, run_id,
                providers=self.policy.decomposition_providers,
                compose_project=self.policy.compose_project,
                execution_authorized=True,
            )
        if kind == "apply_decomposition":
            from Pipeline.AssistantControl import decomposition
            return decomposition.apply(
                self.manager, task_id, run_id=str(action["run_id"]),
                expected_source_commit=str(action["source_commit"]),
                target_branch=self.policy.target_branch or git(
                    self.manager.source, "branch", "--show-current",
                ).decode().strip(),
            )
        raise ValueError(f"Unknown graph action: {kind}")

    def _next_run_action(self, plan: Mapping[str, Any]) -> dict[str, Any] | None:
        """Choose one stable action without letting blocking work starve starts."""
        actions = [dict(item) for item in plan.get("next_actions", [])]
        reservations = self._reservations()
        capacity_full = len(reservations) >= self.policy.capacity
        resource_owner_actions: list[dict[str, Any]] = []
        admission_kinds = {
            "prepare", "refresh_prepared", "scope", "reserve", "start_worker",
        }

        # Drain portable setup first. This lets a guarded low-cost helper prepare
        # and scope every currently eligible task before handing authority back
        # at the first reservation boundary.
        setup_kinds = {"prepare", "refresh_prepared", "scope"}
        for action in actions:
            if action.get("kind") in setup_kinds:
                return action

        # Fill every available worker slot before validating or integrating an
        # earlier fast result. Otherwise a short first task can finish while a
        # later independent task is still purple, and source advancement then
        # forces that prepared checkout through an avoidable refresh.
        for action in actions:
            kind = action.get("kind")
            if kind not in {"reserve", "start_worker"}:
                continue
            if kind == "reserve":
                owner_action = self._resource_overlap_action(
                    action, reservations=reservations,
                )
                if owner_action is not None:
                    resource_owner_actions.append(owner_action)
                    continue
                if capacity_full:
                    continue
            return action

        # With no runnable admission transition, preserve planner/task order
        # for candidate settlement, validation, approval and integration.
        for action in actions:
            if action.get("kind") in admission_kinds | {"decompose", "wait_worker"}:
                continue
            return action

        # A terminal owner must release its exact reservation before an
        # overlapping reserve can be retried. This remains local settlement;
        # it does not admit the blocked task or weaken resource checks.
        for owner_action in resource_owner_actions:
            if owner_action["kind"] == "settle_worker":
                return owner_action

        # Decomposition is synchronous provider work. Run it only after all
        # currently executable single-agent setup/admission/start work.
        for action in actions:
            if action.get("kind") == "decompose":
                return action

        # Waiting blocks the controller, so it is always the last planned
        # action class. This also avoids attempting a reserve at full capacity.
        for action in actions:
            if action.get("kind") == "wait_worker":
                return action
        for owner_action in resource_owner_actions:
            if owner_action["kind"] == "wait_worker":
                return owner_action

        # Capacity can be owned by a worker outside this bounded target set.
        # Wait on the exact active reservation instead of throwing from reserve.
        if capacity_full:
            for task_id in sorted(reservations, key=_task_key):
                owner_action = self._reservation_owner_action(reservations[task_id])
                if owner_action is not None:
                    return owner_action
        return None

    def _reservation_owner_action(
        self, reservation: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Return work for one reservation only when every owner binding matches."""
        owner = reservation.get("task_id")
        if not isinstance(owner, str):
            return None
        record = self._record(owner) or {}
        worker = record.get("worker") or record.get("launch") or {}
        scope = record.get("scope") or {}
        if (record.get("task_id") != owner
                or record.get("source") != str(self.manager.source)
                or record.get("checkout") != str(self.manager.root / owner)
                or record.get("source_commit") != reservation.get("source_head")
                or record.get("task_contract_sha256") != reservation.get("task_contract_sha256")
                or not isinstance(scope, Mapping)
                or scope.get("lease_id") != reservation.get("lease_id")
                or scope.get("plan_id") != reservation.get("plan_id")
                or reservation.get("checkout_root") != str(self.manager.root)
                or reservation.get("checkout") != str(self.manager.root / owner)
                or reservation.get("source") != str(self.manager.source)
                or worker.get("task_id") != owner
                or worker.get("run_id") != reservation.get("run_id")
                or worker.get("lease_id") != reservation.get("lease_id")
                or worker.get("capacity_released") is True):
            return None
        kind = ("settle_worker" if worker.get("status") in _WORKER_TERMINAL
                else "wait_worker")
        return {"kind": kind, "task_id": owner, "run_id": worker.get("run_id")}

    def _resource_overlap_action(
        self, action: Mapping[str, Any], *,
        reservations: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Return wait/settle work only for an exact conflicting reservation."""
        if action.get("kind") != "reserve":
            return None
        from Pipeline.AssistantControl.admission import _overlap, _reservation_resources

        task_id = str(action["task_id"])
        record = self._record(task_id) or {}
        scope = record.get("scope")
        checkout = record.get("checkout")
        source_commit = record.get("source_commit")
        contract_hash = record.get("task_contract_sha256")
        if not isinstance(scope, Mapping) or not all(
                isinstance(value, str) and value
                for value in (checkout, source_commit, contract_hash)):
            return None
        task = load_committed_task(
            Path(checkout), task_id, commit=source_commit,
            expected_sha256=contract_hash,
        )
        requested = _reservation_resources(task, scope)
        reservations = reservations if reservations is not None else self._reservations()
        conflicts = [item for item in reservations.values()
                     if any(_overlap(left, right) for left in requested
                            for right in item.get("resources", []))]
        for reservation in sorted(conflicts, key=lambda item: _task_key(str(item.get("task_id", "")))):
            owner_action = self._reservation_owner_action(reservation)
            if owner_action is not None:
                return owner_action
        return None

    def _run_owned(
        self, *, max_actions: int = 100,
        allowed_actions: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        completed_actions: list[dict[str, Any]] = []
        self._save_state("running")
        try:
            while len(completed_actions) < max_actions:
                plan = self.plan()
                if not plan["next_actions"]:
                    final = {**plan, "mutations_performed": bool(completed_actions),
                             "completed_actions": completed_actions}
                    self._save_state(str(plan["status"]), result=final)
                    return final
                action = self._next_run_action(plan)
                if action is None:
                    final = {**plan, "status": "capacity_full",
                             "mutations_performed": bool(completed_actions),
                             "completed_actions": completed_actions}
                    self._save_state("capacity_full", result=final)
                    return final
                if allowed_actions is not None and action["kind"] not in allowed_actions:
                    final = {
                        **plan,
                        "status": "handoff_required",
                        "handoff_action": action,
                        "allowed_actions": sorted(allowed_actions),
                        "mutations_performed": bool(completed_actions),
                        "completed_actions": completed_actions,
                    }
                    self._save_state("handoff_required", result=final)
                    return final
                self._save_state("running", action=action)
                try:
                    result = self._execute_timed(action)
                except ValueError as exc:
                    if (action.get("kind") != "reserve"
                            or str(exc) != "requested execution resources overlap an active admission"):
                        raise
                    owner_action = self._resource_overlap_action(action)
                    if owner_action is None:
                        raise
                    action = owner_action
                    self._save_state("running", action=action)
                    result = self._execute_timed(action)
                completed_actions.append({"action": dict(action), "result": result})
                self._save_state("running", action=action, result=result)
                if action["kind"] == "wait_worker" and result.get("status") == "worker_still_running":
                    final = {**self.plan(), "status": "worker_still_running",
                             "mutations_performed": bool(completed_actions),
                             "completed_actions": completed_actions}
                    self._save_state("worker_still_running", result=final)
                    return final
            final = {**self.plan(), "status": "action_limit_reached",
                     "mutations_performed": bool(completed_actions),
                     "completed_actions": completed_actions}
            self._save_state("action_limit_reached", result=final)
            return final
        except KeyboardInterrupt:
            try:
                self._save_state("interrupted", error="operator interrupted graph controller")
            except BaseException:
                pass
            raise
        except Exception as exc:
            try:
                self._save_state("blocked", error=f"{type(exc).__name__}: {exc}")
            except BaseException:
                pass
            raise

    def run(
        self, *, max_actions: int = 100,
        allowed_actions: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        if type(max_actions) is not int or isinstance(max_actions, bool) or max_actions < 1:
            raise ValueError("max_actions must be positive")
        invocation_id = uuid.uuid4().hex
        with self._controller_owner(
            invocation_id,
            max_actions=max_actions,
            allowed_actions=allowed_actions,
        ):
            return self._run_owned(
                max_actions=max_actions,
                allowed_actions=allowed_actions,
            )


__all__ = [
    "ControllerOwnerActiveError", "DELEGATE_SAFE_ACTIONS", "GraphController", "GraphPolicy",
    "automatic_scope_plan", "scope_plan",
]
