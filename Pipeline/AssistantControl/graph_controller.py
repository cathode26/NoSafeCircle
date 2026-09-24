"""Resumable outer loop for the conversation-operated task tools.

The controller chooses one deterministic next transition at a time.  Existing
AssistantControl components continue to own checkouts, provider execution,
candidate validation, Unity materialization, review and local integration.
"""
from __future__ import annotations

import errno
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

from Pipeline.AssistantControl import background_jobs
from Pipeline.AssistantControl import worker_state
from Pipeline.AssistantControl.automation_policy import (
    HUMAN_ONLY_TASKS,
    committed_json,
    is_synthetic_gauntlet,
)
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.dependencies import (
    approved_integration,
    conformance_context,
    inspect_dependencies,
)
from Pipeline.AssistantControl.inspect_project import changes, git
from Pipeline.AssistantControl.process_identity import identify
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task, load_committed_tasks
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
_DECOMPOSITION_SCHEMA = "assistant-decomposition/v1"
# Receipt states that describe finished decomposition history. "running" and
# anything unrecognised are deliberately absent: they still veto.
_SETTLED_DECOMPOSITION_STATUSES = frozenset({"failed", "review_ready", "applied"})
_TASK_ID_RE = re.compile(r"NSC-\d+")
_GRAPH_PATH_PREFIXES = (
    "tasks/", "pipeline/taskgraph/",
    "pipeline/taskreviewagent/authoritative_validation_policy.json",
)
_FILTER_RE = re.compile(r"\bfilter\s+([A-Za-z_][A-Za-z0-9_.+`]*)")
DELEGATE_SAFE_ACTIONS = frozenset({
    "prepare", "refresh_prepared", "scope",
})
# Expensive management work that never moves Source runs as an owned detached
# background job so the loop keeps settling workers and admitting crews.
BACKGROUND_ACTION_KINDS = frozenset({"decompose", "post_crew"})
# Every action that moves Source or the target branch stays in the single
# owner thread, one at a time, in planner order.
SOURCE_LANE_ACTION_KINDS = frozenset({
    "apply_decomposition", "sync_candidate", "auto_approve", "integrate",
})
# The Source lane actions that actually advance the Source commit. A
# decomposition proposal reads Source for minutes and binds every round to the
# exact head and tree it started from, so these two wait while one is in
# flight. `sync_candidate` and `auto_approve` stay in the Source lane but move
# neither Source nor the target branch, so a proposal never holds them.
DECOMPOSITION_HELD_ACTION_KINDS = frozenset({"apply_decomposition", "integrate"})
_SETUP_KINDS = frozenset({"prepare", "refresh_prepared", "scope"})
_ADMISSION_KINDS = frozenset({"reserve", "start_worker"})
_WAIT_KINDS = frozenset({"wait_worker", "wait_job"})
_WAIT_TIMEOUT_STATUSES = frozenset({"worker_still_running", "background_jobs_running"})
_DECOMPOSITION_JOB_WAIT_SECONDS = 3600.0 + 180.0
_POST_CREW_JOB_WAIT_SECONDS = 1800.0
# `checkouts.lock` serializes every record transaction in one checkout root, and
# its legitimate holders are slow: in the 20260913 Gauntlet run a post-crew
# child's candidate registration held it about 9 s and a foreground
# `sync_candidate` 13-16 s, while every waiter budgets 10 s. Losing that wait is
# contention, never proof that anything is wrong, so an action that cannot take
# the lock *before* it has written anything durable is deferred to the next
# planning cycle, which re-emits it, instead of failing the invocation.
#
# Only kinds whose `checkouts.lock` acquisition provably precedes every durable
# write of that action are listed. Proof per kind, read at 1dae47b:
#   decompose, post_crew  `_job_identity` only reads (git rev-parse, the
#       committed task, the task record), then `background_jobs.launch` takes the
#       lock before it creates the run root, the launch request, the index or the
#       child. `launch` stamps exactly that acquisition (its later
#       `_mark_spawn_failed` acquisition, which follows a spawned child, is
#       unstamped) and a launch is deferred only when the stamp is present.
#   prepare               `Checkouts.prepare` (checkouts.py): `validate_task_id`
#       and `records.mkdir(exist_ok=True)`, then the lock.
#   refresh_prepared      `refresh_prepared` (prepared_refresh.py): argument
#       checks and two path computations, then the lock; the Source registry lock
#       is taken inside it and is a different path.
#   scope                 `_execute_foreground` reads the committed task and
#       computes the plan (`scope_plan` only reads), then
#       `AssistantScopePlanner.validate_and_persist` takes the lock first.
#   reserve               `admission.reserve`: argument checks and path
#       computations, then the lock; the registry lock is inside it.
#   start_worker          `worker_launcher.start`: `_json_config`,
#       `require_reservation` (read-only, and its own `checkouts.lock`
#       acquisition is also pre-mutation) and `_run_root`, which only computes a
#       path, then the lock before the launch request exists.
#   settle_worker         `worker_settlement.settle_completed`: `validate_task_id`
#       and one path computation, then the lock.
#   sync_candidate        `source_update.synchronize_candidate`: argument checks
#       and three path computations, then the lock; `_source_integration_lock`
#       and the registry lock are taken inside it.
#   auto_approve          `ReviewGate.approve_validated_gauntlet`: one import and
#       a message check, then the lock. `_execute_foreground` only reads the
#       record before it.
#   integrate             `ReviewGate.integrate`: the lock is its first statement.
# Deliberately excluded, keeping today's failure path:
#   apply_decomposition   never acquires `checkouts.lock` at all; it takes the
#       Source integration lock first and `_apply_locked` writes under it.
#   wait_worker, wait_job the acquisitions reachable from `_wait_for_progress`
#       are inside `background_jobs.harvest` and the cleanup recorders, which
#       persist an observation or a Docker removal that has already happened.
#   anything else         unproven, so unchanged.
LOCK_DEFERRABLE_ACTION_KINDS = frozenset({
    "decompose", "post_crew", "prepare", "refresh_prepared", "scope", "reserve",
    "start_worker", "settle_worker", "sync_candidate", "auto_approve", "integrate",
})
# The bound: after this many consecutive deferrals of the same action the
# original error is raised exactly as it is today, so a wedged lock stays loud.
# With a 10 s lock budget and the wait below that is roughly 80 s of contention.
LOCK_DEFERRAL_LIMIT = 6
# A bounded pause between a deferral and the next planning cycle so the loop
# does not spin. Short enough that a lock which frees immediately delays the
# action by seconds, not minutes.
LOCK_DEFERRAL_WAIT_SECONDS = 3.0
# An operator stop for a controller that has no console: `stop-graph` writes
# this request bound to the running invocation, PID and process identity; the
# controller honors it between actions and on every wait poll exactly like
# Ctrl+C, then returns status "stopped". Unbound or stale requests are archived.
STOP_REQUEST_SCHEMA = "assistant-graph-controller-stop/v1"


class ControllerOwnerActiveError(RuntimeError):
    """Another process holds the graph controller lock."""


class _ActionDeferred(Exception):
    """One action lost a pre-mutation lock wait and is re-planned, not failed.

    Private control flow inside :meth:`GraphController._run_owned`: it never
    reaches a caller, is never journaled as a failure, and carries the exact
    deferral facts that were journaled as `action_deferred`.
    """

    def __init__(self, record: Mapping[str, Any]) -> None:
        super().__init__(str(record.get("reason")))
        self.record = dict(record)


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
    background_job_limit: int = 4

    def __post_init__(self) -> None:
        if not self.targets:
            raise ValueError("Graph controller requires at least one explicit target task")
        for task_id in (*self.targets, *self.human_review_tasks):
            validate_task_id(task_id)
        if type(self.capacity) is not int or isinstance(self.capacity, bool) or self.capacity < 1:
            raise ValueError("Graph controller capacity must be positive")
        if (type(self.background_job_limit) is not int
                or isinstance(self.background_job_limit, bool)
                or self.background_job_limit < 1):
            raise ValueError("Graph controller background job limit must be positive")
        if "NSC-042" not in self.human_review_tasks:
            raise ValueError("NSC-042 is permanently reserved for human review")


class GraphController:
    def __init__(
        self, manager: Checkouts, policy: GraphPolicy,
        worker_config: Mapping[str, Any], *,
        execution_authorized: bool = False,
        require_preflight: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        job_host: background_jobs.JobHost | None = None,
        stop_grace_seconds: float = background_jobs.STOP_GRACE_SECONDS,
    ):
        self.manager = manager
        self.policy = policy
        self.worker_config = json.loads(json.dumps(dict(worker_config)))
        self._worker_config_bytes = _json_bytes(self.worker_config)
        self.execution_authorized = execution_authorized is True
        self.require_preflight = require_preflight is True
        self.sleep = sleep
        self.clock = clock
        self.job_host = job_host if job_host is not None else background_jobs.DetachedHost()
        self.stop_grace_seconds = float(stop_grace_seconds)
        self.state_path = manager.records / "graph-controller.json"
        self.event_path = manager.records / "graph-controller-events.jsonl"
        self.owner_path = manager.records / "graph-controller-owner.json"
        self.lock_path = manager.records / "graph-controller.lock"
        self.stop_path = manager.records / "graph-controller.stop.json"
        self._process_identity: dict[str, Any] | None = None
        self._active_invocation_id: str | None = None
        self._last_plan: dict[str, Any] | None = None
        self._source_lane_busy = False
        # Which held action has already been journaled, and with which exact
        # blocking identity, so one hold is one event instead of one per cycle.
        self._journaled_holds: dict[tuple[str, str], str] = {}
        # Consecutive `checkouts.lock` deferrals per exact action, bounded by
        # LOCK_DEFERRAL_LIMIT. Reset when this invocation starts and when the
        # action finally runs, so a restarted controller carries no deferral
        # state and the bound is per invocation.
        self._lock_deferrals: dict[str, int] = {}
        # Everything below is bound to one exact Source HEAD and discarded the
        # moment HEAD differs: committed contracts, the conformance view, and
        # proofs keyed by the bytes of the record they were derived from.
        self._head_cache: dict[str, Any] = {"head": None}
        self._snapshot_dirty = False

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
        self._lock_deferrals = {}
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
            if self.require_preflight and not (
                isinstance(state, Mapping)
                and isinstance(state.get("preflight_binding"), Mapping)
                and isinstance(state.get("preflight_plan"), Mapping)
            ):
                raise ValueError(
                    "Graph execution requires graph-preflight for this exact Source, policy and worker config"
                )
            if state and (state.get("status") == "preflight" or self.require_preflight):
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
            self._process_identity = process_identity
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
        local_edits = changes(self.manager.source)
        self._snapshot_dirty = bool(local_edits)
        dirty_graph = sorted({
            str(item.get(key)).replace("\\", "/")
            for item in local_edits
            for key in ("path", "original_path")
            if isinstance(item.get(key), str)
            and str(item[key]).replace("\\", "/").casefold().startswith(_GRAPH_PATH_PREFIXES)
        })
        if dirty_graph:
            raise ValueError("Committed task graph has local edits: " + ", ".join(dirty_graph))
        return head, target

    def _cache_for(self, head: str) -> dict[str, Any]:
        """Return the per-HEAD cache, emptied whenever Source HEAD has moved."""
        if self._head_cache.get("head") != head:
            self._head_cache = {
                "head": head, "contracts": None, "context": None,
                "context_dirty": None, "proofs": {},
            }
        return self._head_cache

    @staticmethod
    def _file_sha256(path: Path) -> str | None:
        try:
            return _sha256(path.read_bytes())
        except OSError:
            return None

    def _proof(self, head: str, key: tuple[Any, ...], compute: Callable[[], Any]) -> Any:
        """Memoize one proof derived only from immutable objects at ``head`` and ``key``."""
        proofs = self._cache_for(head)["proofs"]
        if key not in proofs:
            proofs[key] = compute()
        return proofs[key]

    def _conformance_context(self, head: str):
        """One committed-HEAD conformance view, reused while HEAD and dirtiness hold."""
        cache = self._cache_for(head)
        context = cache["context"]
        if context is None or cache["context_dirty"] != self._snapshot_dirty:
            context = conformance_context(self.manager.source)
            if context.head != head:
                raise ValueError("Source HEAD moved while the graph was being planned")
            cache["context"] = context
            cache["context_dirty"] = self._snapshot_dirty
        return context

    def _contracts(self, head: str) -> dict[str, dict[str, Any]]:
        cache = self._cache_for(head)
        if cache["contracts"] is None:
            raw = git(self.manager.source, "ls-tree", "-r", "--name-only", "-z", head, "--", "Tasks")
            ids = sorted({
                PurePosixPath(path).stem
                for path in raw.decode("utf-8", "surrogateescape").split("\0")
                if path.startswith("Tasks/NSC-") and path.endswith(".yaml")
            }, key=_task_key)
            # One git process reads every contract's exact bytes at this commit.
            cache["contracts"] = load_committed_tasks(self.manager.source, ids, commit=head)
        result = dict(cache["contracts"])
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

    def _record_describes_live_work(self, task_id: str) -> bool:
        """True when this controller's own record still has work in flight.

        The committed-conformance route in `_task_complete` exists for work
        completed OUTSIDE this controller -- `_committed_conformant` says so --
        so gating it on a record merely EXISTING used the presence of a file as
        a proxy for "the controller is managing this". One leftover record from
        a failed run then vetoed that route forever, and the task could never be
        recognised as already delivered however good the committed evidence was.

        What the gate protects is the narrower case where this controller has
        something in flight that its own state machine should drive instead: a
        candidate awaiting review or integration, or a run the record does not
        prove is over. `worker_state` owns "is this run over", and asking it
        here rather than re-deriving keeps this answer and `_actions`' answer
        from drifting apart -- they disagreeing is what produced the pair of
        defects this replaces.
        """
        record = self._record(task_id)
        if not isinstance(record, Mapping):
            return False
        if record.get("candidate"):
            return True
        for entry in (record.get("worker"), record.get("launch")):
            if isinstance(entry, Mapping) and not worker_state.is_finished_launch(
                    record, entry):
                return True
        return False

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
            # The proof depends only on this HEAD, the retained receipt bytes
            # and immutable Git history, so it is computed once per receipt.
            applied = self._proof(head, (
                "applied_decomposition", task_id, task.get("task_contract_sha256"),
                self._file_sha256(self.manager.records / f"{task_id}.decomposition.json"),
            ), lambda: self._applied_decomposition(task_id, task, head))
            complete = applied and bool(children) and all(
                self._task_complete(child, tasks, head, memo, visiting)
                for child in children if isinstance(child, str)
            ) and len(children) == len([child for child in children if isinstance(child, str)])
        if not complete:
            complete = self._proof(head, (
                "approved_integration", task_id,
                self._file_sha256(self.manager.records / f"{task_id}.json"),
            ), lambda: approved_integration(
                self.manager.source, self.manager.records, task_id, head,
            ) is not None)
        if (not complete and not self._record_describes_live_work(task_id)
                and self._decomposition_permits_committed_conformance(task_id, task)):
            # The task's own committed conformance state is a pure function of
            # this HEAD (and worktree dirtiness), so its outcome is kept per HEAD.
            complete = self._proof(
                head, ("committed_conformance", task_id, self._snapshot_dirty),
                lambda: self._committed_conformant(task_id, head),
            )
        visiting.remove(task_id)
        memo[task_id] = complete
        return complete

    def _decomposition_permits_committed_conformance(
        self, task_id: str, task: Mapping[str, Any],
    ) -> bool:
        """True when no decomposition receipt should veto committed conformance.

        An absent receipt never vetoes. A settled receipt for an already
        decomposed parent is history, not proof of application: a decomposition
        proposed and applied in an isolated clone leaves its receipt bound to
        that clone, so canonical sees a foreign `source`. Requiring the receipt
        to be absent let that history veto independently committed completion
        forever. Source equality is deliberately not checked here -- this is
        not `_applied_decomposition`, which still authenticates the receipt.
        """
        record = self._decomposition(task_id)
        if record is None:
            return True
        children = task.get("decomposition_children")
        return (
            isinstance(record, Mapping)
            and record.get("schema_version") == _DECOMPOSITION_SCHEMA
            and record.get("task_id") == task_id
            and record.get("status") in _SETTLED_DECOMPOSITION_STATUSES
            and task.get("contract_disposition", "active") == "active"
            and task.get("kind") == "feature"
            and task.get("execution_scope") == "not_applicable"
            and task.get("decomposition_state") == "decomposed"
            and isinstance(children, list)
            and bool(children)
            and all(isinstance(child, str) and _TASK_ID_RE.fullmatch(child)
                    for child in children)
            and len(set(children)) == len(children)
        )

    def _committed_conformant(self, task_id: str, head: str) -> bool:
        try:
            state = inspect_dependencies(
                self.manager.source, task_id, self.manager.root,
                context=self._conformance_context(head),
            ).get("task_state", {}).get("state")
            # Committed delivery evidence may satisfy work completed before
            # this AssistantControl run. Merely finding output files in
            # Source (needs_testing) cannot replace an integration receipt.
            return state == "conformant"
        except (OSError, RuntimeError, ValueError, TypeError):
            return False

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

    def _jobs(self) -> dict[str, dict[str, Any]]:
        return background_jobs.list_indexes(self.manager)

    def _job_gate(self, task_id: str, job: Mapping[str, Any] | None) -> dict[str, Any] | None:
        """Read-only: return the wait action or blocked item that a job imposes on its task.

        A live job owns its task until it ends. A job that ended without a
        receipt, or whose child failed, blocks only its task until an operator
        clears the exact index; it is never relaunched automatically. A
        completed job imposes nothing: the records it wrote decide the next step.
        """
        if job is None:
            return None
        status = job.get("status")
        if status in background_jobs.ACTIVE_STATUSES:
            observed = background_jobs.observe(job, self.job_host)
            status = observed.get("status")
            if status == "running":
                return {"kind": "wait_job", "task_id": task_id,
                        "job_id": job.get("job_id"), "job_kind": job.get("kind")}
            if status == "completed":
                return None
            error = (observed.get("receipt") or {}).get("error") or observed.get("detail")
        elif status == "completed":
            return None
        else:
            error = job.get("error")
        blocked = {"task_id": task_id, "reason": f"background_job_{status}",
                   "job_kind": job.get("kind"), "job_id": job.get("job_id"), "error": error}
        if isinstance(job.get("reconciliation"), Mapping):
            blocked["reconciliation"] = dict(job["reconciliation"])
        return blocked

    @staticmethod
    def _crew_run_for_validation(record: Mapping[str, Any]) -> str | None:
        worker = record.get("worker") or record.get("launch") or {}
        crew_run = worker.get("crew_run_id") if isinstance(worker, Mapping) else None
        if not isinstance(crew_run, str) or not crew_run:
            candidate = record.get("candidate") or {}
            original = candidate.get("original_candidate") or {}
            crew_run = original.get("run_id") or candidate.get("run_id")
        return crew_run if isinstance(crew_run, str) and crew_run else None

    def _source_lane_holds(
        self, actions: list[dict[str, Any]], jobs: Mapping[str, Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Mark the planned actions that must wait for a decomposition proposal.

        A decomposition proposal reads Source for minutes while its provider
        runs, and every round of it is bound to the exact Source head and tree it
        started from, so a Source move during the call throws the whole round
        away: NSC-1145 returned a correct two-child proposal that was rejected
        with `source HEAD changed during provider invocation` because an
        unrelated integration landed 81 seconds into an 87-second call.

        Three rules, all derived from this plan and the durable job indexes:

        1. While any `decompose` job is active, `integrate` and
           `apply_decomposition` wait. Nothing else waits: settlement, post-crew
           launches, setup, admission, `sync_candidate` and `auto_approve` never
           advance the Source commit, so the loop keeps working through them.
        2. At most one decomposition proposal is in flight. A second
           decompose-ready parent waits until the first job has ended and its
           `apply_decomposition` has landed or been recorded as failed, because
           an apply moves Source exactly like an integration.
        3. A Source-moving action ready in the same cycle as a new `decompose`
           launch goes first and the launch waits one cycle, so an integration
           is never delayed by minutes for a proposal that could have started a
           few seconds later.

        The held action keeps its place in `next_actions` carrying a `held`
        record, so the plan reports what is waiting and why, and it runs
        unchanged on the first cycle that no longer holds it. Every input is
        durable, so a restarted controller reconstructs the same holds.
        """
        holds: list[dict[str, Any]] = []

        def hold(action: dict[str, Any], reason: str, blocker: Mapping[str, Any] | None) -> None:
            record = {
                "task_id": action.get("task_id"),
                "kind": action.get("kind"),
                "reason": reason,
                "blocking_task_id": None if blocker is None else blocker.get("task_id"),
                "blocking_job_id": None if blocker is None else blocker.get("job_id"),
            }
            action["held"] = dict(record)
            holds.append(record)

        active = [
            jobs[task_id] for task_id in sorted(jobs, key=_task_key)
            if jobs[task_id].get("kind") == "decompose"
            and jobs[task_id].get("status") in background_jobs.ACTIVE_STATUSES
        ]
        in_flight = active[0] if active else None
        source_moving = [item for item in actions
                         if item.get("kind") in DECOMPOSITION_HELD_ACTION_KINDS]
        if in_flight is not None:
            for action in source_moving:
                hold(action, "decomposition_proposal_in_flight", in_flight)
        apply_pending = [item for item in actions
                         if item.get("kind") == "apply_decomposition"]
        for action in actions:
            if action.get("kind") != "decompose":
                continue
            if in_flight is not None:
                hold(action, "decomposition_proposal_in_flight", in_flight)
            elif apply_pending:
                hold(action, "decomposition_apply_pending", apply_pending[0])
            elif source_moving:
                hold(action, "source_lane_action_ready", source_moving[0])
        return holds

    def plan(self) -> dict[str, Any]:
        head, branch = self._source_snapshot()
        tasks = self._contracts(head)
        selected = self._in_scope(tasks)
        reservations = self._reservations()
        jobs = self._jobs()
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
            gate = self._job_gate(task_id, jobs.get(task_id))
            if gate is not None:
                (actions if gate.get("kind") == "wait_job" else blocked).append(gate)
                continue
            execution_scope = task.get("execution_scope")
            if execution_scope == "needs_execution_decomposition":
                receipt = self._decomposition(task_id)
                status = (receipt or {}).get("status")
                if receipt is None:
                    if jobs.get(task_id) is not None:
                        # The ticket ran to completion without a proposal record;
                        # its receipt is the authority and relaunch needs an operator.
                        blocked.append({"task_id": task_id, "reason": "decomposition_receipt_missing",
                                        "job_id": jobs[task_id].get("job_id")})
                    else:
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
                            self.manager.source, task_id, head, tasks=tasks):
                        crew_run = self._crew_run_for_validation(record)
                        if record.get("source_commit") != head:
                            actions.append({"kind": "sync_candidate", "task_id": task_id,
                                            "candidate_commit": commit, "source_commit": head})
                        elif not candidate.get("authoritative_validations") and crew_run:
                            # Focused Unity validation of a synchronized candidate
                            # is the expensive half of auto-approval; run it as a
                            # background job and approve from its retained facts.
                            actions.append({"kind": "post_crew", "task_id": task_id,
                                            "crew_run_id": crew_run,
                                            "candidate_commit": commit})
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
                # A launch entry keeps whatever status the launcher wrote, so a
                # run that ended and was settled can leave `ready_pending` with a
                # null `capacity_released` behind. Read at face value that is
                # "not settled, not terminal", which emits `wait_worker` for a
                # run that ended days ago -- on every pass, with nothing that can
                # ever change it. `worker_state` answers from the record's own
                # proof instead: the settled copy in `worker_history`.
                #
                # Such a record then falls through to `blocked`, deliberately.
                # Retiring the stale entry so the task can be dispatched again
                # is a separate decision with its own command; surfacing it is
                # this function's job, and silently retrying would hide it.
                if (not worker_state.is_finished_launch(record, worker)
                        and worker.get("capacity_released") is not True):
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

        held = self._source_lane_holds(actions, jobs)
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
            "held": held,
            "complete": complete,
            "waiting_human": waiting_human,
            "blocked": blocked,
            "background_jobs": [background_jobs.summary(jobs[task_id])
                                for task_id in sorted(jobs, key=_task_key)],
            "provider_spend_authorized": self.execution_authorized,
            "mutations_performed": False,
        }

    def _save_state(self, status: str, *, action: Mapping[str, Any] | None = None,
                    result: Mapping[str, Any] | None = None,
                    error: str | None = None,
                    background_stops: Sequence[Mapping[str, Any]] | None = None) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        previous = _read_json(self.state_path) or {}
        history = list(previous.get("history") or [])[-99:]
        if action is not None:
            history.append({"at": _now(), "action": dict(action),
                            "invocation_id": self._active_invocation_id,
                            "result_status": (result or {}).get("status")})
        try:
            jobs = self._jobs()
        except (OSError, ValueError):
            jobs = {}
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
            "background_jobs": [background_jobs.summary(jobs[task_id])
                                for task_id in sorted(jobs, key=_task_key)],
            "updated_at": _now(),
        }
        if background_stops is not None:
            state["background_stops"] = [dict(item) for item in background_stops]
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
        elif isinstance(previous.get("preflight_binding"), Mapping):
            # The next bounded invocation must still prove its original
            # preparation, even after this invocation wrote progress or stopped.
            state["preflight_binding"] = previous["preflight_binding"]
            state["preflight_plan"] = previous.get("preflight_plan")
            if result is not None:
                state["last_result"] = dict(result)
        elif result is not None:
            state["last_result"] = dict(result)
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

    def _checkouts_lock_contention(self, action: Mapping[str, Any], exc: BaseException) -> bool:
        """Is this exactly a lost pre-mutation wait for this root's `checkouts.lock`?

        Typed, not text-matched: `_exclusive_file_lock` raises
        ``TimeoutError(errno.ETIMEDOUT, ..., str(path))``, so the class, the
        errno and the filename are all checked, and the producer's wording is
        required on top of them. The lock path must be this checkout root's
        `checkouts.lock`: a timeout on the Source integration lock, the Source
        registry lock, `decomposition.lock` or another root's records is not this
        contention and keeps its own failure path.
        """
        if not isinstance(exc, TimeoutError) or exc.errno != errno.ETIMEDOUT:
            return False
        wanted = str(self.manager.records / "checkouts.lock")
        if exc.filename != wanted:
            return False
        message = str(exc.strerror or "")
        if not (message.startswith("timed out after ")
                and message.endswith(" waiting for exclusive file lock")):
            return False
        if str(action.get("kind")) not in BACKGROUND_ACTION_KINDS:
            return True
        # A launch is the one deferrable path with a second `checkouts.lock`
        # acquisition after a durable write, so only the stamped pre-mutation
        # acquisition counts (see `background_jobs.launch`).
        return background_jobs.pre_mutation_lock_contention(exc) == wanted

    def _lock_deferral(
        self, action: Mapping[str, Any], exc: BaseException, action_id: str, *,
        seconds_waited: float,
    ) -> dict[str, Any] | None:
        """Journal and count one deferral, or return None to keep the failure path."""
        kind = str(action.get("kind"))
        if kind not in LOCK_DEFERRABLE_ACTION_KINDS:
            return None
        if not self._checkouts_lock_contention(action, exc):
            return None
        key = _json_bytes(dict(action)).decode("utf-8")
        count = self._lock_deferrals.get(key, 0) + 1
        if count > LOCK_DEFERRAL_LIMIT:
            # A lock held this long is wedged, not busy: fail exactly as before.
            return None
        self._lock_deferrals[key] = count
        record = {
            "at_utc": _now(), "task_id": action.get("task_id"), "kind": kind,
            "reason": "lock_contention",
            "lock_path": str(self.manager.records / "checkouts.lock"),
            "seconds_waited": round(float(seconds_waited), 3),
            "deferrals": count, "limit": LOCK_DEFERRAL_LIMIT,
            "error": f"{type(exc).__name__}: {exc}",
        }
        self._append_event({
            "event": "action_deferred", "invocation_id": self._active_invocation_id,
            "action_id": action_id, "run_id": action.get("run_id"), **record,
        })
        return record

    def _execute_timed(self, action: Mapping[str, Any]) -> dict[str, Any]:
        action_id = uuid.uuid4().hex
        started = time.monotonic()
        self._append_action_event("action_started", action, action_id)
        try:
            result = self.execute(action)
        except BaseException as exc:
            deferral = self._lock_deferral(
                action, exc, action_id, seconds_waited=time.monotonic() - started,
            )
            if deferral is not None:
                raise _ActionDeferred(deferral) from exc
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
        kind = str(action["kind"])
        if kind in BACKGROUND_ACTION_KINDS:
            return self._launch_job(action)
        if kind in _WAIT_KINDS:
            return self._wait_for_progress(action)
        if kind in SOURCE_LANE_ACTION_KINDS:
            if self._source_lane_busy:
                raise RuntimeError("Source-moving graph actions must not overlap")
            self._source_lane_busy = True
            try:
                return self._execute_foreground(action)
            finally:
                self._source_lane_busy = False
        return self._execute_foreground(action)

    def _job_identity(self, action: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
        """Bind one background ticket to the exact task, Source commit, contract and config."""
        kind, task_id = str(action["kind"]), str(action["task_id"])
        if kind == "decompose":
            self._require_provider_authority()
            head = git(self.manager.source, "rev-parse", "HEAD").decode().strip()
            branch = git(self.manager.source, "branch", "--show-current").decode().strip()
            task = load_committed_task(self.manager.source, task_id, commit=head)
            providers = [item.strip() for item in self.policy.decomposition_providers.split(",")
                         if item.strip()]
            identity = {
                "run_id": f"assistant-{task_id.casefold()}-decompose-{head[:12]}",
                "source_commit": head, "source_branch": branch,
                "task_contract_sha256": task.get("task_contract_sha256"),
                "providers": providers, "compose_project": self.policy.compose_project,
            }
            return identity, None, True
        if kind == "post_crew":
            record = self._record(task_id) or {}
            worker = record.get("worker") or record.get("launch") or {}
            config = worker.get("config") if isinstance(worker.get("config"), Mapping) else self.worker_config
            identity = {
                "crew_run_id": str(action["crew_run_id"]),
                "candidate_commit": action.get("candidate_commit"),
                "source_commit": record.get("source_commit"),
                "task_contract_sha256": record.get("task_contract_sha256"),
            }
            return identity, dict(config), False
        raise ValueError(f"Unknown background graph action: {kind}")

    def _launch_job(self, action: Mapping[str, Any]) -> dict[str, Any]:
        kind, task_id = str(action["kind"]), str(action["task_id"])
        identity, config, spend = self._job_identity(action)
        try:
            index = background_jobs.launch(
                self.manager, kind=kind, task_id=task_id, identity=identity, config=config,
                invocation_id=str(self._active_invocation_id),
                provider_spend_authorized=spend, host=self.job_host,
                binding={
                    "policy_sha256": _sha256(_json_bytes(self._policy_fields())),
                    "worker_config_sha256": _sha256(self._worker_config_bytes),
                },
            )
        except background_jobs.BackgroundJobError as exc:
            # A ticket whose child never started blocks only its own task; the
            # planner reads the retained spawn_failed index on the next cycle.
            failed = background_jobs.read_index(self.manager, task_id)
            if (failed is None or failed.get("status") != "spawn_failed"
                    or failed.get("invocation_id") != self._active_invocation_id):
                raise
            self._append_job_event("job_spawn_failed", failed)
            return {"status": "spawn_failed", "task_id": task_id, "kind": kind,
                    "job_id": failed.get("job_id"), "error": str(exc)}
        self._append_job_event("job_launched", index)
        return {"status": "launched", "task_id": task_id, "kind": kind,
                "job_id": index.get("job_id"), "attempt": index.get("attempt"),
                "identity": index.get("identity"), "pid": index.get("pid"),
                "process_identity": index.get("process_identity"),
                "run_root": index.get("run_root")}

    def _append_job_event(self, event: str, index: Mapping[str, Any], **extra: Any) -> None:
        payload = {
            "at_utc": _now(), "event": event,
            "invocation_id": self._active_invocation_id,
            **{key: index.get(key) for key in (
                "task_id", "kind", "job_id", "attempt", "identity", "status", "pid",
                "process_identity", "launched_at_utc", "result_status", "error",
                "completed_at_utc", "run_root", "provider_container",
                "provider_container_cleanup",
            )},
            "launch_invocation_id": index.get("invocation_id"),
            "provider": self.worker_config.get("provider"),
            "model": self.worker_config.get("execution_model"),
            **extra,
        }
        self._append_event(payload)

    def _journal_source_lane_holds(self, plan: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Record each new hold once, not once per cycle it stays held.

        A hold is journaled when it first appears and again only if the exact
        blocking job or the reason changes. Releasing it forgets it, so the same
        action held again later is journaled again. A restarted controller
        rebuilds the same holds from the durable job indexes and journals them
        once more, under its own invocation id.
        """
        journaled: list[dict[str, Any]] = []
        current: dict[tuple[str, str], str] = {}
        for record in plan.get("held") or ():
            if not isinstance(record, Mapping):
                continue
            key = (str(record.get("task_id")), str(record.get("kind")))
            signature = f"{record.get('reason')}:{record.get('blocking_job_id')}"
            current[key] = signature
            if self._journaled_holds.get(key) == signature:
                continue
            payload = {
                "at_utc": _now(), "event": "source_lane_held",
                "invocation_id": self._active_invocation_id,
                **{name: record.get(name) for name in (
                    "task_id", "kind", "reason", "blocking_task_id", "blocking_job_id",
                )},
            }
            self._append_event(payload)
            journaled.append(payload)
        self._journaled_holds = current
        return journaled

    def _reconcile_startup(self) -> list[dict[str, Any]]:
        """Settle every retained ticket under the controller lock before the first plan.

        A live, authenticated job is adopted (its Job Object handle retained;
        it is never relaunched); an ended job is harvested and its exact
        provider container reconciled; a live job whose ticket no longer
        authenticates is stopped and quarantined; anything ambiguous refuses
        startup before a plan or a launch can happen.
        """
        try:
            outcomes = background_jobs.reconcile_startup(
                self.manager, self.job_host, invocation_id=str(self._active_invocation_id),
                grace_seconds=self.stop_grace_seconds, clock=self.clock, sleep=self.sleep,
            )
        except background_jobs.StartupRefused as exc:
            # Outcomes persisted before the refusal are durable; journal them
            # before the refusal itself so the journal matches the indexes.
            self._journal_reconciliation(exc.outcomes)
            self._append_event({
                "at_utc": _now(), "event": "startup_refused",
                "invocation_id": self._active_invocation_id, "error": str(exc),
                **{key: (exc.index or {}).get(key) for key in ("task_id", "kind", "job_id", "status")},
                "provider_container": (exc.index or {}).get("provider_container"),
                "provider_container_cleanup": (exc.index or {}).get("provider_container_cleanup"),
            })
            raise
        return self._journal_reconciliation(outcomes)

    def _journal_reconciliation(self, outcomes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        harvested: list[dict[str, Any]] = []
        for outcome in outcomes:
            index = {key: value for key, value in outcome.items() if key != "outcome"}
            kind = outcome["outcome"]
            if kind == "adopted":
                event = "job_adopted"
            elif kind == "quarantined":
                event = "job_quarantined"
            elif kind == "container_verified":
                event = "job_container_verified"
            elif kind == "cleanup_superseded":
                event = "job_cleanup_superseded"
            else:
                event = {"completed": "job_completed", "failed": "job_failed"}.get(
                    str(index.get("status")), "job_died")
                harvested.append(index)
            self._append_job_event(event, index, reconciliation=index.get("reconciliation"))
        return harvested

    def _harvest_jobs(self) -> list[dict[str, Any]]:
        """Persist every ended job's exact receipt and reconcile its exact container.

        A terminal job whose container cleanup is not final (refused earlier,
        unverified, abandoned by a process that died, or verified with its
        tombstone now passed) is retried here, exactly and without the lock,
        so the final recheck happens a minute after the kill without an
        operator; a retry that cannot finish is retained and retried later.

        Concurrency is expected, never fatal: a ticket cleared or superseded
        while its Docker work ran unlocked is journaled and skipped, and a
        cleanup or harvest that raises is journaled against its own task while
        every other task keeps moving. Nothing from this method reaches the
        controller loop as an exception.
        """
        harvested: list[dict[str, Any]] = []
        for task_id in sorted(self._jobs(), key=_task_key):
            index = background_jobs.read_index(self.manager, task_id)
            if index is None:
                continue
            if index.get("status") not in background_jobs.ACTIVE_STATUSES:
                if background_jobs.cleanup_retry_due(index):
                    try:
                        settled = background_jobs.settle_cleanup(
                            self.manager, index, self.job_host, clock=self.clock, sleep=self.sleep,
                            wait_for_tombstone=False,
                        )
                    except background_jobs.BackgroundJobError as exc:
                        self._append_job_event("job_cleanup_pending", index,
                                               detail=f"{type(exc).__name__}: {exc}")
                        continue
                    if settled.get("cleanup_concurrency"):
                        self._append_job_event("job_cleanup_superseded", settled,
                                               detail=settled.get("detail"))
                        continue
                    self._append_job_event(
                        "job_cleanup_pending" if background_jobs.cleanup_pending(settled)
                        else "job_container_verified", settled,
                    )
                continue
            observed = background_jobs.observe(index, self.job_host)
            status = observed.get("status")
            if status == "running":
                continue
            if status == "unverifiable":
                self._append_job_event("job_unverifiable", index, detail=observed.get("detail"))
                continue
            try:
                updated = background_jobs.harvest(
                    self.manager, index, observed, invocation_id=str(self._active_invocation_id),
                    host=self.job_host, clock=self.clock, sleep=self.sleep,
                )
            except background_jobs.BackgroundJobError as exc:
                self._append_job_event("job_harvest_deferred", index,
                                       detail=f"{type(exc).__name__}: {exc}")
                continue
            self._append_job_event(
                {"completed": "job_completed", "failed": "job_failed"}.get(status, "job_died"),
                updated,
            )
            harvested.append(background_jobs.summary(updated))
        return harvested

    def _watched_workers(self, action: Mapping[str, Any]) -> list[dict[str, Any]]:
        watched = [dict(item) for item in (self._last_plan or {}).get("next_actions", [])
                   if item.get("kind") == "wait_worker"]
        if action.get("kind") == "wait_worker" and not any(
                item.get("task_id") == action.get("task_id") for item in watched):
            watched.append(dict(action))
        return watched

    def _wait_for_progress(self, action: Mapping[str, Any]) -> dict[str, Any]:
        """Block only until any watched worker exits or any background job ends."""
        from Pipeline.AssistantControl import worker_control
        workers = self._watched_workers(action)
        jobs = [index for index in self._jobs().values()
                if index.get("status") in background_jobs.ACTIVE_STATUSES]
        if action.get("kind") == "wait_job" and not any(
                index.get("job_id") == action.get("job_id") for index in jobs):
            raise ValueError("Background job identity changed while graph controller was waiting")
        budget = 0.0
        if workers:
            budget = float(self.worker_config.get("timeout_seconds", 900)) + 180
        for index in jobs:
            budget = max(budget, _DECOMPOSITION_JOB_WAIT_SECONDS if index.get("kind") == "decompose"
                         else _POST_CREW_JOB_WAIT_SECONDS)
        deadline = self.clock() + budget
        while True:
            for watched in workers:
                task_id = str(watched["task_id"])
                observed = worker_control.status(self.manager, task_id)
                worker = observed.get("worker") or {}
                if worker.get("run_id") != watched.get("run_id"):
                    raise ValueError("Worker identity changed while graph controller was waiting")
                if observed.get("host_identity_alive") is False:
                    return {**observed, "status": "progress", "progress": "worker_exited"}
                if observed.get("host_identity_alive") is None:
                    raise ValueError("Worker process identity cannot be verified")
            for index in jobs:
                observed = background_jobs.observe(index, self.job_host)
                if observed.get("status") != "running":
                    return {"status": "progress", "progress": "job_ended",
                            "task_id": index.get("task_id"), "job_id": index.get("job_id"),
                            "job_kind": index.get("kind"), "job_status": observed.get("status")}
            if self._bound_stop_request() is not None:
                return {"status": "stop_requested",
                        "watched_workers": [item.get("task_id") for item in workers],
                        "watched_jobs": [index.get("job_id") for index in jobs]}
            if self.clock() >= deadline:
                return {"status": "worker_still_running" if workers else "background_jobs_running",
                        "watched_workers": [item.get("task_id") for item in workers],
                        "watched_jobs": [index.get("job_id") for index in jobs]}
            self.sleep(1.0)

    # -- operator stop request -------------------------------------------

    def _read_stop_request(self) -> dict[str, Any] | None:
        try:
            return _read_json(self.stop_path)
        except ValueError:
            return {"schema_version": None, "unreadable": True}

    def _bound_stop_request(self) -> dict[str, Any] | None:
        """Return the stop request only when it names this exact running invocation."""
        request = self._read_stop_request()
        if request is None or self._active_invocation_id is None:
            return None
        if (request.get("schema_version") == STOP_REQUEST_SCHEMA
                and request.get("invocation_id") == self._active_invocation_id
                and request.get("pid") == os.getpid()
                and request.get("process_identity") == self._process_identity):
            return request
        return None

    def _archive_stop_request(self, label: str) -> str | None:
        if not self.stop_path.is_file():
            return None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.stop_path.with_name(f"graph-controller.stop.{label}-{stamp}.json")
        os.replace(self.stop_path, target)
        return str(target)

    def _archive_stale_stop_request(self) -> None:
        request = self._read_stop_request()
        if request is None or self._bound_stop_request() is not None:
            return
        archived = self._archive_stop_request("stale")
        self._append_event({
            "at_utc": _now(), "event": "stop_request_ignored",
            "invocation_id": self._active_invocation_id,
            "request_invocation_id": request.get("invocation_id"),
            "request_pid": request.get("pid"), "archived": archived,
        })

    def _cancel_active_jobs(self, reason: str, grace_seconds: float) -> list[dict[str, Any]]:
        """Stop every active background job; a second interrupt or a failure is retained, never hidden."""
        stops: list[dict[str, Any]] = []
        try:
            stops = background_jobs.cancel_all(
                self.manager, host=self.job_host, reason=reason,
                grace_seconds=grace_seconds, invocation_id=str(self._active_invocation_id),
                clock=self.clock, sleep=self.sleep,
            )
        except KeyboardInterrupt:
            stops = [{"status": "stop_interrupted",
                      "error": "second interrupt abandoned background job enforcement"}]
        except Exception as exc:
            stops = [{"status": "stop_failed", "error": f"{type(exc).__name__}: {exc}"}]
        for item in stops:
            try:
                self._append_event({
                    "at_utc": _now(), "event": "job_stopped",
                    "invocation_id": self._active_invocation_id, **dict(item),
                })
            except BaseException:
                pass
        return stops

    def _stop_grace(self, request: Mapping[str, Any]) -> float:
        grace = request.get("grace_seconds")
        if isinstance(grace, (int, float)) and not isinstance(grace, bool) and grace >= 0:
            return float(grace)
        return self.stop_grace_seconds

    def _execute_foreground(self, action: Mapping[str, Any]) -> dict[str, Any]:
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
        if kind == "settle_worker":
            from Pipeline.AssistantControl.worker_settlement import settle_completed
            return settle_completed(self.manager, task_id, run_id=str(action["run_id"]))
        if kind == "sync_candidate":
            from Pipeline.AssistantControl.source_update import synchronize_candidate
            return synchronize_candidate(
                self.manager, task_id, str(action["candidate_commit"]),
                str(action["source_commit"]),
            )
        if kind == "auto_approve":
            # Approval only. Focused Unity validation is background `post_crew`
            # work; this foreground step never runs it and fails closed when
            # the exact candidate carries no retained validation facts.
            from Pipeline.AssistantControl.review import ReviewGate
            record = self._record(task_id) or {}
            candidate = record.get("candidate") or {}
            candidate_commit = candidate.get("commit")
            if not isinstance(candidate_commit, str) or candidate_commit != action.get("candidate_commit"):
                raise ValueError("Gauntlet candidate changed before automated approval")
            if record.get("status") != "awaiting_human":
                raise ValueError(f"Gauntlet candidate is {record.get('status')!r}, not awaiting approval")
            if not candidate.get("authoritative_validations"):
                raise ValueError(
                    "Gauntlet candidate has no retained focused validation; "
                    "a post_crew job must validate it first"
                )
            return ReviewGate(self.manager).approve_validated_gauntlet(
                task_id, tested_commit=candidate_commit,
            )
        if kind == "integrate":
            from Pipeline.AssistantControl.review import ReviewGate
            return ReviewGate(self.manager).integrate(
                task_id, expected_source_commit=str(action["source_commit"]),
                target_branch=str(action["target_branch"]),
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

    def _next_run_action(
        self, plan: Mapping[str, Any], *, allowed_actions: frozenset[str] | None = None,
    ) -> dict[str, Any] | None:
        """Choose one stable action without letting blocking work starve starts."""
        actions = [dict(item) for item in plan.get("next_actions", [])]
        if allowed_actions is not None:
            # A delegate drains every transition it may perform before handing
            # authority back at the first one it may not.
            permitted = [item for item in actions if item.get("kind") in allowed_actions]
            choice = self._choose_run_action(permitted) if permitted else None
            if choice is not None:
                return choice
        return self._choose_run_action(actions)

    def _choose_run_action(self, actions: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
        actions = [dict(item) for item in actions]
        # An action the planner held waits for a decomposition proposal; it is
        # never chosen, and the loop falls through to everything else.
        held_any = any(item.get("held") for item in actions)
        actions = [item for item in actions if not item.get("held")]
        reservations = self._reservations()
        capacity_full = len(reservations) >= self.policy.capacity
        resource_owner_actions: list[dict[str, Any]] = []

        # Observe and settle terminal workers on every cycle. Settlement takes
        # seconds, releases the worker's reservation and never moves Source.
        for action in actions:
            if action.get("kind") == "settle_worker":
                return action

        # Start expensive non-Source work (decomposition proposals, post-crew
        # validation) as owned background jobs before anything else so the
        # minutes they take overlap with admission instead of preceding it.
        running_jobs = sum(
            1 for index in self._jobs().values()
            if index.get("status") in background_jobs.ACTIVE_STATUSES
        )
        deferred_launch = False
        for action in actions:
            if action.get("kind") in BACKGROUND_ACTION_KINDS:
                if running_jobs < self.policy.background_job_limit:
                    return action
                deferred_launch = True

        # Drain portable setup next. This lets a guarded low-cost helper prepare
        # and scope every currently eligible task before handing authority back
        # at the first reservation boundary.
        for action in actions:
            if action.get("kind") in _SETUP_KINDS:
                return action

        # Fill every available worker slot before integrating an earlier fast
        # result. Otherwise a short first task can finish while a later
        # independent task is still purple, and source advancement then forces
        # that prepared checkout through an avoidable refresh.
        for action in actions:
            kind = action.get("kind")
            if kind not in _ADMISSION_KINDS:
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

        # A terminal owner must release its exact reservation before an
        # overlapping reserve can be retried. This remains local settlement;
        # it does not admit the blocked task or weaken resource checks.
        for owner_action in resource_owner_actions:
            if owner_action["kind"] == "settle_worker":
                return owner_action

        # Source-moving work runs here, one action at a time, in planner order.
        for action in actions:
            if action.get("kind") in SOURCE_LANE_ACTION_KINDS:
                return action

        # Waiting blocks the controller, so it is always the last planned
        # action class. This also avoids attempting a reserve at full capacity.
        for action in actions:
            if action.get("kind") in _WAIT_KINDS:
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

        # A launch deferred by the background job limit, or an action held for a
        # decomposition proposal, waits on a running job rather than ending the
        # run: the hold is released by that job, not by an operator.
        if deferred_launch or held_any:
            for task_id in sorted(self._jobs(), key=_task_key):
                index = background_jobs.read_index(self.manager, task_id)
                if index is not None and index.get("status") in background_jobs.ACTIVE_STATUSES:
                    return {"kind": "wait_job", "task_id": task_id,
                            "job_id": index.get("job_id"), "job_kind": index.get("kind")}
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
        harvested_jobs: list[dict[str, Any]] = []
        lock_deferrals: list[dict[str, Any]] = []

        def final_result(
            plan: Mapping[str, Any], status: str, *,
            background_stops: Sequence[Mapping[str, Any]] | None = None, **extra: Any,
        ) -> dict[str, Any]:
            final = {
                **plan, "status": status,
                "mutations_performed": bool(completed_actions) or bool(harvested_jobs),
                "completed_actions": completed_actions,
                "harvested_jobs": harvested_jobs,
                "lock_deferrals": lock_deferrals,
                **extra,
            }
            if background_stops is not None:
                final["background_stops"] = [dict(item) for item in background_stops]
            self._save_state(status, result=final, background_stops=background_stops)
            return final

        def stopped(request: Mapping[str, Any]) -> dict[str, Any]:
            reason = str(request.get("reason") or "operator requested graph stop")
            stops = self._cancel_active_jobs(reason, self._stop_grace(request))
            # A job whose exact container could not be verified absent is
            # stopped but not finished: `stop-background-jobs` retries it.
            cleanup_pending = sorted(
                {str(item.get("task_id")) for item in stops if item.get("cleanup_pending")},
                key=_task_key,
            )
            self._append_event({
                "at_utc": _now(), "event": "controller_stopped",
                "invocation_id": self._active_invocation_id, "reason": reason,
                "requested_at_utc": request.get("requested_at_utc"),
                "stopped_jobs": len(stops), "cleanup_pending": cleanup_pending,
            })
            archived = self._archive_stop_request("handled")
            return final_result(
                self.plan(), "stopped", background_stops=stops,
                stop_request={**dict(request), "archived": archived},
                cleanup_pending=cleanup_pending,
            )

        self._archive_stale_stop_request()
        self._save_state("running")
        try:
            # Every retained ticket is adopted, harvested or quarantined under
            # this lock before the first plan: no launch can duplicate a live
            # child and no dead child's container outlives its ticket.
            harvested_jobs.extend(self._reconcile_startup())
            while len(completed_actions) < max_actions:
                stop_request = self._bound_stop_request()
                if stop_request is not None:
                    return stopped(stop_request)
                # Harvest exact receipts of ended jobs before planning so the
                # planner sees their durable outcome, never a stale ticket.
                harvested_jobs.extend(self._harvest_jobs())
                plan = self.plan()
                self._last_plan = plan
                self._journal_source_lane_holds(plan)
                if not plan["next_actions"]:
                    return final_result(plan, str(plan["status"]))
                action = self._next_run_action(plan, allowed_actions=allowed_actions)
                if action is None:
                    return final_result(plan, "capacity_full")
                if allowed_actions is not None and action["kind"] not in allowed_actions:
                    return final_result(
                        plan, "handoff_required", handoff_action=action,
                        allowed_actions=sorted(allowed_actions),
                    )
                self._save_state("running", action=action)
                try:
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
                except _ActionDeferred as deferred:
                    # Nothing durable was written and nothing is blocked: the
                    # invocation stays running with no `last_error`, and the next
                    # plan re-emits this action. The bounded wait keeps the loop
                    # from spinning on a lock that is merely busy.
                    lock_deferrals.append(deferred.record)
                    self._save_state("running")
                    self.sleep(LOCK_DEFERRAL_WAIT_SECONDS)
                    continue
                self._lock_deferrals.pop(_json_bytes(dict(action)).decode("utf-8"), None)
                completed_actions.append({"action": dict(action), "result": result})
                self._save_state("running", action=action, result=result)
                if action["kind"] in _WAIT_KINDS and result.get("status") == "stop_requested":
                    stop_request = self._bound_stop_request()
                    if stop_request is not None:
                        return stopped(stop_request)
                if action["kind"] in _WAIT_KINDS and result.get("status") in _WAIT_TIMEOUT_STATUSES:
                    return final_result(self.plan(), str(result["status"]))
            return final_result(self.plan(), "action_limit_reached")
        except KeyboardInterrupt:
            # An operator stop must not leave provider or Unity work running in
            # detached children: request, wait the bounded grace, then terminate
            # each exact recorded Job Object tree. A second interrupt abandons
            # the enforcement; `stop-background-jobs` finishes it afterwards.
            stops = self._cancel_active_jobs(
                "operator interrupted graph controller", self.stop_grace_seconds,
            )
            try:
                self._save_state(
                    "interrupted", error="operator interrupted graph controller",
                    background_stops=stops,
                )
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


def _release_note(pending: Sequence[str], unreadable: Sequence[Mapping[str, Any]]) -> str:
    """What the operator must still do before this graph can be called finished."""
    parts: list[str] = []
    if unreadable:
        parts.append(
            "a background-job index cannot be read or authenticated ("
            + "; ".join(f"{item.get('path')}: {item.get('error')}" for item in unreadable)
            + "); nothing may be reported as finished until it is repaired or archived by hand"
        )
    if pending:
        parts.append(
            "a provider container of " + ", ".join(pending)
            + " is not finally verified absent; run stop-background-jobs, which retries the "
            "exact cleanup under the controller lock"
        )
    if not parts:
        return ("no graph controller owns this graph; nothing left to stop "
                "(stop-background-jobs stops jobs orphaned by a lost controller and "
                "retries a pending container cleanup)")
    return "the controller has released but " + "; also ".join(parts)


def request_stop(
    manager: Checkouts, *, reason: str = "operator requested graph stop",
    grace_seconds: float = background_jobs.STOP_GRACE_SECONDS, wait_seconds: float = 120.0,
) -> dict[str, Any]:
    """Ask the controller that owns this graph to stop; wait a bounded time for its release.

    Idempotent: a request already bound to the running invocation is reused,
    never rewritten, and a released owner reports `already_released` with its
    retained outcome. Refuses when no controller ever owned the graph, and when
    a started owner's lock is free (a dead process, which
    `stop-background-jobs` handles). Never terminates anything itself.
    """
    if not isinstance(grace_seconds, (int, float)) or grace_seconds < 0:
        raise ValueError("stop grace must be a non-negative number of seconds")
    if not isinstance(wait_seconds, (int, float)) or wait_seconds < 0:
        raise ValueError("stop wait must be a non-negative number of seconds")
    owner_path = manager.records / "graph-controller-owner.json"
    state_path = manager.records / "graph-controller.json"
    owner = _read_json(owner_path)
    if owner is None:
        raise ValueError(
            "no graph controller has owned this graph; nothing to stop "
            "(stop-background-jobs stops jobs orphaned by a lost controller)"
        )
    if owner.get("status") == "controller_released":
        state = _read_json(state_path) or {}
        pending, unreadable = _cleanup_pending_tasks(manager, state)
        return {
            "status": ("already_released_cleanup_pending" if pending or unreadable
                       else "already_released"),
            "invocation_id": owner.get("invocation_id"),
            "controller_status": state.get("status"), "outcome": owner.get("outcome"),
            "background_stops": state.get("background_stops"),
            "cleanup_pending": pending,
            "unreadable_indexes": unreadable,
            "note": _release_note(pending, unreadable),
        }
    if owner.get("status") != "controller_started":
        raise ValueError("the graph controller owner record is unreadable; nothing to stop")
    try:
        held = _acquire_liveness_lock(manager.records / "graph-controller.lock")
    except (BlockingIOError, PermissionError):
        held = None
    if held is not None:
        _release_liveness_lock(held)
        raise ValueError(
            "the graph controller owner record is stale: its lock is free, so the controller "
            "process is gone; run stop-background-jobs to stop its orphaned jobs"
        )
    request = {
        "schema_version": STOP_REQUEST_SCHEMA,
        "invocation_id": owner.get("invocation_id"), "pid": owner.get("pid"),
        "process_identity": owner.get("process_identity"),
        "reason": str(reason), "grace_seconds": float(grace_seconds),
        "requested_at_utc": _now(), "requested_by_pid": os.getpid(),
    }
    stop_path = manager.records / "graph-controller.stop.json"
    try:
        existing = _read_json(stop_path)
    except ValueError:
        existing = None
    repeated = existing is not None and all(
        existing.get(field) == request[field]
        for field in ("schema_version", "invocation_id", "pid", "process_identity"))
    if repeated:
        request = dict(existing)
    else:
        write_record(stop_path, request)
    deadline = time.monotonic() + float(wait_seconds)
    while True:
        current = _read_json(owner_path) or {}
        if (current.get("invocation_id") == request["invocation_id"]
                and current.get("status") == "controller_released"):
            state = _read_json(state_path) or {}
            pending, unreadable = _cleanup_pending_tasks(manager, state)
            if state.get("status") != "stopped":
                status = "released"
            elif pending or unreadable:
                status = "stopped_cleanup_pending"
            else:
                status = "stopped"
            return {
                "status": status, "controller_status": state.get("status"),
                "outcome": current.get("outcome"),
                "background_stops": state.get("background_stops"), "request": request,
                "repeated": repeated, "cleanup_pending": pending,
                "unreadable_indexes": unreadable,
                **({"note": _release_note(pending, unreadable)} if pending or unreadable else {}),
            }
        if time.monotonic() >= deadline:
            return {"status": "stop_requested", "request": request, "repeated": repeated,
                    "note": "the controller has not released yet; its runner reports the final status"}
        time.sleep(0.5)


def _cleanup_pending_tasks(
    manager: Checkouts, state: Mapping[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Unfinished background-job work left behind a released controller.

    Returns the task ids whose stopped job still has a provider container
    cleanup that is not final, and one diagnostic (task id, path, error) per
    background-job index that cannot be read or authenticated at all. An index
    that cannot be read is never "nothing remains": the caller must fail closed
    on it. The durable job indexes are the authority; the stop result recorded
    in the state is only consulted for a job whose index has since been
    cleared. Nothing here deletes or repairs a record.
    """
    readable, unreadable = background_jobs.scan_indexes(manager)
    pending: set[str] = set()
    for item in state.get("background_stops") or []:
        if not isinstance(item, Mapping) or not isinstance(item.get("task_id"), str):
            continue
        index = readable.get(item["task_id"])
        if index is None:
            continue  # cleared, or unreadable and already reported below
        if index.get("job_id") == item.get("job_id") and background_jobs.cleanup_pending(index):
            pending.add(item["task_id"])
    for task_id, index in readable.items():
        if index.get("status") in background_jobs.TERMINAL_STATUSES and background_jobs.cleanup_pending(index):
            pending.add(task_id)
    return (
        sorted(pending, key=_task_key),
        sorted(unreadable, key=lambda item: _task_key(str(item.get("task_id")))),
    )


__all__ = [
    "BACKGROUND_ACTION_KINDS", "ControllerOwnerActiveError", "DELEGATE_SAFE_ACTIONS",
    "GraphController", "GraphPolicy", "SOURCE_LANE_ACTION_KINDS", "STOP_REQUEST_SCHEMA",
    "automatic_scope_plan", "request_stop", "scope_plan",
]
