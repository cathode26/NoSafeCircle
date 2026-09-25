"""Durable, detached background actions owned by the graph controller.

The graph controller stays one owner with one planner. Expensive management
actions that never move Source or the target branch (a decomposition proposal,
post-crew candidate validation) run in an exact ticketed child process instead
of blocking the scheduling loop. The ticket binds the task, the Source commit,
the contract hash, the provider configuration and the child's process identity;
the child retains its result as a receipt bound to the ticket bytes and to that
exact process identity. A restarted controller either observes the same live
child or harvests its retained receipt. It never launches the same ticket twice.

Every Windows child is assigned to a run-derived named Job Object before the
controller permits it to work, using the same handoff as the worker launcher:
the parent keeps its Job Object handle until the exact child has opened the
named job and acknowledged it. An operator stop writes an authenticated
``stop.request.json`` bound to the ticket, the child's PID and process identity
and the Job Object name, gives the child a bounded cooperative grace period,
then terminates only that recorded Job Object tree. A stopped job is retained as
``cancelled``: never a provider failure, never relaunched automatically.

A decomposition ticket also records, before Docker can start, the exact name of
the provider container the child will create and the compose project it
belongs to. After the child's tree has ended, that exact container (and nothing
else) is inspected, removed on every sighting, and watched for the whole
bounded window, verified only when its final stability interval was absent;
because one Docker operation may take up to a minute, the ticket also keeps a
tombstone until that bound has passed and is rechecked once after it; until
that final recheck the cleanup stays pending, so every stop and every startup
retries the exact look. Every retry reauthenticates the immutable ticket
(request bytes, task, job, container identity, owned run directory) before
anything destructive and fails closed on a mismatch; a cleanup already in
progress under a live owner is waited for, never superseded, and a superseded
result rereads durable state instead of failing the controller. The verified
outcome is retained on the ticket; Docker work never runs while the checkout
lock is held. A controller that
starts while tickets are still active reconciles every one of them under its
lock before planning: a ticket it can authenticate and observe alive is
adopted; one it cannot is stopped, its tree and exact container ended, and its
task blocked with the retained reason; an ambiguous state refuses startup.

The child never plans, never takes the controller lock, never mutates Source,
and starts a provider only when the ticket carries the controller's explicit
spend authorization.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.process_identity import identify, matches
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


SCHEMA = "assistant-background-job/v1"
RECEIPT_SCHEMA = "assistant-background-job-receipt/v1"
STOP_SCHEMA = "assistant-background-job-stop/v1"
JOB_KINDS = frozenset({"decompose", "post_crew", "fixture"})
ACTIVE_STATUSES = frozenset({"launched", "running"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "died", "cancelled", "spawn_failed"})
STOP_GRACE_SECONDS = 15.0
# How long one launch transaction waits for `checkouts.lock`. A launch that
# loses this wait has written nothing durable (see :func:`launch`), so the graph
# controller defers it to its next planning cycle instead of failing the whole
# invocation. Tests shorten this to exercise contention without waiting.
LAUNCH_LOCK_TIMEOUT_SECONDS = 10.0
# Attribute stamped on a `checkouts.lock` timeout that was raised *before* its
# transaction wrote anything durable. Only a raise site that can prove that
# property may stamp it; the graph controller refuses to defer an action
# without it. The value is the exact lock path, so a marked timeout from
# another checkout root is still not deferred here.
PRE_MUTATION_LOCK_ATTRIBUTE = "assistant_pre_mutation_lock_path"
CONTAINER_SETTLE_SECONDS = 3.0
CONTAINER_WINDOW_SECONDS = 15.0
CONTAINER_TOMBSTONE_SECONDS = 60.0
_RETRY_BACKOFF_SECONDS = 30.0
_ACTIVE_CLEANUPS: set[tuple[str, str, Any]] = set()  # (task, job, generation) in flight here
_RECEIPT_OUTCOMES = {"succeeded": "completed", "failed": "failed", "stopped": "cancelled"}
_READY_TIMEOUT_SECONDS = 30.0
_STOP_POLL_SECONDS = 0.5
_DOCKER_TIMEOUT_SECONDS = 60
_STOP_IDENTITY_FIELDS = (
    "schema_version", "task_id", "kind", "job_id", "request_sha256", "pid",
    "process_identity", "job_name",
)
CONTAINER_JOB_LABEL = "com.nosafecircle.assistant.job"
CONTAINER_CHECKOUT_LABEL = "com.nosafecircle.assistant.checkout"
_CONTAINER_INSPECT_FORMAT = (
    '{"id":{{json .Id}},"name":{{json .Name}},"running":{{json .State.Running}},'
    '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
    '"job":{{json (index .Config.Labels "' + CONTAINER_JOB_LABEL + '")}},'
    '"checkout":{{json (index .Config.Labels "' + CONTAINER_CHECKOUT_LABEL + '")}}}'
)


class BackgroundJobError(ValueError):
    """A background job could not be safely launched, observed, stopped or harvested."""


class StartupRefused(BackgroundJobError):
    """Retained job state is too ambiguous to plan beside without risking an unrelated process.

    ``outcomes`` lists the reconciliation outcomes already persisted before the
    refusal (they are durable and must still be journaled); ``index`` is the
    ticket that caused it.
    """

    def __init__(self, message: str, *, outcomes: list[dict[str, Any]] | None = None,
                 index: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.outcomes = list(outcomes or [])
        self.index = dict(index) if index is not None else None


class ContainerReconcileError(BackgroundJobError):
    """A Docker operation failed part-way through one exact container cleanup.

    ``partial`` carries every sighting and every removal made before the
    failure, so the caller can keep them durable and renew the cleanup bound
    instead of losing what already happened.
    """

    def __init__(self, message: str, *, partial: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.partial = dict(partial or {})


def _now() -> str:
    return _utc_now().isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _json_copy(value: Any, label: str) -> Any:
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError) as exc:
        raise BackgroundJobError(f"{label} must be JSON-serializable") from exc


def _read_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BackgroundJobError(f"background job record is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise BackgroundJobError(f"background job record is not an object: {path}")
    return value


def _task_order(task_id: str) -> tuple[int, str]:
    try:
        return int(task_id.removeprefix("NSC-")), task_id
    except ValueError:
        return 2**31, task_id


def index_path(manager: Checkouts, task_id: str) -> Path:
    return manager.records / f"{validate_task_id(task_id)}.background-job.json"


def jobs_root(manager: Checkouts) -> Path:
    return manager.records / "background-jobs"


def job_id_for(kind: str, task_id: str, identity: Mapping[str, Any], attempt: int,
               *, source: Any, checkout_root: Any) -> str:
    """The exact ticket id, derived from the owning checkout as well as the work.

    ``source`` and ``checkout_root`` are required: without them two checkouts
    (or two clones) of the same Source commit running the same task with the
    same identity would derive the same id and therefore the same provider
    container name, and a stop in one could remove the other's container.
    """
    return hashlib.sha256(_canonical({
        "kind": kind, "task_id": task_id, "identity": dict(identity), "attempt": attempt,
        "source": str(source), "checkout_root": str(checkout_root),
    })).hexdigest()


def checkout_digest_for(source: Any, checkout_root: Any) -> str:
    """The exact checkout a ticket belongs to, as a container label value."""
    return hashlib.sha256(
        _canonical({"source": str(source), "checkout_root": str(checkout_root)})
    ).hexdigest()


def container_labels_for(job_id: Any, source: Any, checkout_root: Any) -> dict[str, str]:
    """The labels the ticket's own container must carry, and nothing else may."""
    return {
        CONTAINER_JOB_LABEL: str(job_id),
        CONTAINER_CHECKOUT_LABEL: checkout_digest_for(source, checkout_root),
    }


def job_name_for(run_root: Path) -> str:
    """The run-derived named Job Object that contains one ticket's child tree."""
    return "assistant-job-" + hashlib.sha256(str(run_root.resolve()).encode("utf-8")).hexdigest()


def container_name_for(job_id: str) -> str:
    """The exact provider container name one decomposition ticket may create."""
    return "nsc-decompose-" + str(job_id)[:24]


def read_index(manager: Checkouts, task_id: str) -> dict[str, Any] | None:
    """Return the controller-owned index of the task's latest background job."""
    value = _read_object(index_path(manager, task_id))
    if value is None:
        return None
    if (value.get("schema_version") != SCHEMA or value.get("task_id") != task_id
            or value.get("source") != str(manager.source)
            or value.get("checkout_root") != str(manager.root)):
        raise BackgroundJobError(f"background job index identity differs for {task_id}")
    return value


def scan_indexes(
    manager: Checkouts,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Every readable index keyed by task id, and one diagnostic per unreadable one.

    An index file that is missing, empty, truncated, malformed or whose recorded
    identity differs from this Source and checkout root is never "nothing
    remains": it is reported with its path and the exact error so a caller can
    fail closed instead of concluding the graph is finished. Nothing is
    deleted, rewritten or repaired here. Every diagnostic is JSON-safe, so it
    can be reported to an operator verbatim.
    """
    readable: dict[str, dict[str, Any]] = {}
    unreadable: list[dict[str, Any]] = []
    if not manager.records.is_dir():
        return readable, unreadable
    for path in sorted(manager.records.glob("NSC-*.background-job.json")):
        task_id = path.name[: -len(".background-job.json")]
        try:
            # ValueError covers both an unreadable record and a file name that
            # is not a valid task id: neither may pass as an absent job.
            index = read_index(manager, task_id)
        except ValueError as exc:
            unreadable.append({"task_id": task_id, "path": str(path), "error": str(exc)})
            continue
        if index is not None:
            readable[task_id] = index
    return readable, unreadable


def unreadable_indexes(manager: Checkouts) -> list[dict[str, Any]]:
    """Diagnostics for every background-job index that cannot be authenticated."""
    return scan_indexes(manager)[1]


def list_indexes(manager: Checkouts) -> dict[str, dict[str, Any]]:
    """Return every task's latest background job index keyed by task id.

    Raises on the first index that cannot be authenticated: a caller that must
    survive one uses :func:`scan_indexes` and reports it instead.
    """
    readable, unreadable = scan_indexes(manager)
    if unreadable:
        raise BackgroundJobError(unreadable[0]["error"])
    return readable


def summary(index: Mapping[str, Any]) -> dict[str, Any]:
    """Compact viewer/diagnosis view of one job index."""
    return {key: index.get(key) for key in (
        "task_id", "kind", "job_id", "attempt", "status", "identity", "invocation_id",
        "launched_at_utc", "pid", "process_identity", "job_name", "provider_container",
        "provider_container_cleanup", "authentication", "reconciliation", "stop",
        "result_status", "error",
        "completed_at_utc", "harvested_at_utc", "harvest_invocation_id", "run_root",
    )}


class JobHost(Protocol):
    """Process seam: production spawns a contained detached child; tests use a fixture."""

    def identify_self(self) -> dict[str, Any]: ...

    def spawn(self, run_root: Path, request: Mapping[str, Any]) -> dict[str, Any]:
        """Start the child and contain it in ``request['job_name']`` before returning."""

    def handoff(self, run_root: Path, process_identity: Mapping[str, Any], job_name: str) -> None:
        """Hold the Job Object until the exact child acknowledges it opened the named job."""

    def alive(self, process_identity: Mapping[str, Any]) -> bool | None: ...

    def stop(self, process_identity: Mapping[str, Any], job_name: str) -> dict[str, Any]:
        """Terminate only the recorded Job Object tree; prove the exact host is gone."""

    def adopt(self, process_identity: Mapping[str, Any], job_name: str) -> None:
        """Retain the named Job Object of one live, contained child after a controller restart."""

    def docker(self, arguments: list[str]) -> tuple[int, str, str]:
        """Run one docker CLI command; returns (exit code, stdout, stderr)."""


def _identity(pid: int) -> dict[str, Any]:
    try:
        value = identify(pid)
    except (NotImplementedError, OSError, ValueError) as exc:
        raise BackgroundJobError("detached background jobs require exact process identity") from exc
    if not isinstance(value, dict):
        raise BackgroundJobError("background job process identity is unavailable")
    return value


DockerRunner = Callable[[list[str]], tuple[int, str, str]]


def _run_docker(arguments: list[str]) -> tuple[int, str, str]:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        result = subprocess.run(
            ["docker", *arguments], capture_output=True, text=True,
            timeout=_DOCKER_TIMEOUT_SECONDS, creationflags=creationflags, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 125, "", f"{type(exc).__name__}: {exc}"
    return result.returncode, result.stdout, result.stderr


class DetachedHost:
    """Launch the child as a hidden, Job-Object-contained process; observe it by exact identity."""

    def __init__(self, docker_runner: DockerRunner | None = None) -> None:
        self._job_handles: dict[str, Any] = {}
        self._adopted: dict[str, Any] = {}
        self._docker_runner = docker_runner or _run_docker

    def identify_self(self) -> dict[str, Any]:
        return _identity(os.getpid())

    def spawn(self, run_root: Path, request: Mapping[str, Any]) -> dict[str, Any]:
        job_name = str(request.get("job_name") or "")
        if not job_name:
            raise BackgroundJobError("background job ticket carries no Job Object name")
        control_source = Path(__file__).resolve().parents[2]
        args = [
            sys.executable, "-m", "Pipeline.AssistantControl.background_jobs", "--child",
            "--request", str(run_root / "launch.request.json"),
            "--source", str(request["source"]), "--checkout-root", str(request["checkout_root"]),
            "--task", str(request["task_id"]), "--job", str(request["job_id"]),
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        try:
            with (run_root / "stdout.log").open("ab") as stdout, \
                    (run_root / "stderr.log").open("ab") as stderr:
                child = subprocess.Popen(
                    args, cwd=str(control_source), stdin=subprocess.DEVNULL,
                    stdout=stdout, stderr=stderr, shell=False,
                    creationflags=creationflags, startupinfo=startupinfo,
                )
        except (OSError, ValueError) as exc:
            raise BackgroundJobError(f"background job child could not be spawned: {exc}") from exc
        threading.Thread(target=child.wait, name="assistant-job-reaper", daemon=True).start()
        try:
            child_identity = _identity(child.pid)
            from Pipeline.AssistantControl.windows_job import create_and_assign
            # The child is still waiting for its ready receipt: contain every
            # future descendant before publishing permission to work.
            self._job_handles[job_name] = create_and_assign(job_name, child_identity)
        except Exception as exc:
            # The retained Popen handle names exactly this child, never a bare PID.
            try:
                child.terminate()
                child.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired, ValueError):
                try:
                    child.kill()
                    child.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired, ValueError):
                    pass
            if isinstance(exc, BackgroundJobError):
                raise
            raise BackgroundJobError(f"background job child could not be contained: {exc}") from exc
        return {"pid": child.pid, "process_identity": child_identity}

    def handoff(self, run_root: Path, process_identity: Mapping[str, Any], job_name: str) -> None:
        """Keep the parent handle open until the exact child opened the named job."""
        job = self._job_handles.get(job_name)
        if job is None:
            raise BackgroundJobError("background Job Object handle is unavailable for handoff")
        opened_path = run_root / "job.opened.json"
        deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
        try:
            while not opened_path.is_file():
                if self.alive(process_identity) is False:
                    raise BackgroundJobError("contained background child exited before Job Object handoff")
                if time.monotonic() >= deadline:
                    raise BackgroundJobError("contained background child did not acknowledge Job Object handoff")
                time.sleep(0.05)
            opened = _read_object(opened_path) or {}
            if (opened.get("job_name") != job_name
                    or opened.get("pid") != process_identity.get("pid")
                    or opened.get("process_identity") != dict(process_identity)):
                raise BackgroundJobError("background Job Object handoff is not bound to the exact child")
        except BaseException:
            from Pipeline.AssistantControl.windows_job import terminate_job
            try:
                terminate_job(job_name)
            except Exception:
                pass
            job.close()
            self._job_handles.pop(job_name, None)
            raise
        job.close()
        self._job_handles.pop(job_name, None)

    def alive(self, process_identity: Mapping[str, Any]) -> bool | None:
        try:
            return matches(dict(process_identity))
        except (OSError, ValueError, NotImplementedError):
            return None

    def tree_active(self, job_name: str) -> int:
        from Pipeline.AssistantControl.windows_job import active_count
        return active_count(job_name)

    def adopt(self, process_identity: Mapping[str, Any], job_name: str) -> None:
        """Reopen and retain the live child's named Job Object; refuse an uncontained child."""
        from Pipeline.AssistantControl.windows_job import WindowsJobError, is_assigned, open_named
        if job_name in self._adopted:
            return
        try:
            contained = is_assigned(job_name, dict(process_identity))
        except (WindowsJobError, ValueError) as exc:
            raise BackgroundJobError(f"background job containment cannot be verified: {exc}") from exc
        if not contained:
            raise BackgroundJobError("live background child is not in its recorded Job Object")
        self._adopted[job_name] = open_named(job_name)

    def docker(self, arguments: list[str]) -> tuple[int, str, str]:
        return self._docker_runner(list(arguments))

    def stop(self, process_identity: Mapping[str, Any], job_name: str) -> dict[str, Any]:
        """Terminate only the recorded Job Object tree; the exact host must be gone after."""
        from Pipeline.AssistantControl.windows_job import (
            WindowsJobError, active_count, is_assigned, terminate_job,
        )
        identity = dict(process_identity)
        try:
            host_alive = matches(identity)
        except (OSError, ValueError, NotImplementedError) as exc:
            raise BackgroundJobError(f"background job host identity cannot be verified: {exc}") from exc
        if host_alive:
            try:
                contained = is_assigned(job_name, identity)
            except (WindowsJobError, ValueError):
                contained = None  # The host exited between the two checks.
            if contained is False:
                raise BackgroundJobError(
                    "background job child is not in its recorded Job Object; nothing was terminated"
                )
        # The run-derived name is the authority: it reaches every contained
        # descendant even after the exact host already exited.
        terminate_job(job_name)
        deadline = time.monotonic() + 10.0
        while matches(identity) and time.monotonic() < deadline:
            time.sleep(0.05)
        if matches(identity):
            raise BackgroundJobError("background job host remained alive after Job Object termination")
        adopted = self._adopted.pop(job_name, None)
        if adopted is not None:
            adopted.close()
        return {"host_exited": True, "tree_active": active_count(job_name), "job_name": job_name}


def _attempt_number(manager: Checkouts, kind: str, task_id: str,
                    identity: Mapping[str, Any]) -> int:
    """Attempts are counted from retained run roots, never from a deletable index."""
    root = jobs_root(manager) / task_id
    if not root.is_dir():
        return 1
    wanted = _canonical(dict(identity))
    count = 0
    for request_path in root.glob("*/launch.request.json"):
        request = _read_object(request_path) or {}
        if request.get("kind") == kind and _canonical(request.get("identity")) == wanted:
            count += 1
    return count + 1


def _mark_spawn_failed(manager: Checkouts, task_id: str, job_id: str, error: str) -> None:
    with _exclusive_file_lock(manager.records / "checkouts.lock", timeout_seconds=10):
        current = read_index(manager, task_id)
        if current is not None and current.get("job_id") == job_id:
            current.update(status="spawn_failed", error=error, completed_at_utc=_now())
            write_record(index_path(manager, task_id), current)


def _provider_container(kind: str, job_id: str, identity: Mapping[str, Any], *,
                        source: Any, checkout_root: Any) -> dict[str, Any] | None:
    """The exact container a ticket may create, fixed before Docker can start.

    The name is checkout-exact through the job id, and the container must also
    carry this ticket's job and checkout labels: a container under the name
    that does not is another checkout's and is never removed.
    """
    project = None
    if kind == "decompose":
        project = str(identity["compose_project"])
    elif kind == "fixture" and identity.get("simulate_container") is True:
        project = "fixture"
    if project is None:
        return None
    return {"name": container_name_for(job_id), "compose_project": project,
            "labels": container_labels_for(job_id, source, checkout_root)}


def mark_pre_mutation_lock_contention(exc: BaseException, lock_path: Path) -> None:
    """Stamp a lock timeout raised before its transaction wrote anything durable.

    The exception object, its type and its message are left exactly as
    ``_exclusive_file_lock`` produced them: a caller that does not know about
    the stamp still sees today's ``TimeoutError``.
    """
    setattr(exc, PRE_MUTATION_LOCK_ATTRIBUTE, str(lock_path))


def pre_mutation_lock_contention(exc: BaseException) -> str | None:
    """The lock path a stamped timeout names, or ``None`` when it is not stamped."""
    marked = getattr(exc, PRE_MUTATION_LOCK_ATTRIBUTE, None)
    return marked if type(marked) is str else None


def _require_decompose_options(identity: Mapping[str, Any]) -> None:
    """Refuse a malformed opt-in decomposition option before any ticket exists.

    decomposition.run makes the full checks (checklist version, two distinct
    providers for a bookkeeper); these only keep a wrong type out of the ticket.
    """
    if "max_calls" in identity and (type(identity["max_calls"]) is not int
                                    or identity["max_calls"] not in (2, 3)):
        raise BackgroundJobError("background decomposition max_calls must be 2 or 3")
    for key in ("author_checklist", "bookkeeper_model"):
        if key in identity and (type(identity[key]) is not str or not identity[key].strip()):
            raise BackgroundJobError(f"background decomposition {key} must be a non-blank string")
    if "continue_from" in identity:
        raise BackgroundJobError("background decomposition does not support continue_from")


def launch(
    manager: Checkouts, *, kind: str, task_id: str, identity: Mapping[str, Any],
    config: Mapping[str, Any] | None, invocation_id: str,
    provider_spend_authorized: bool, host: JobHost, binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one exact ticket and start its contained child; refuse a second live job per task."""
    task_id = validate_task_id(task_id)
    if kind not in JOB_KINDS:
        raise BackgroundJobError(f"unsupported background job kind: {kind}")
    if type(invocation_id) is not str or not invocation_id:
        raise BackgroundJobError("background job launch requires the owning invocation id")
    identity = _json_copy(dict(identity), "background job identity")
    saved_config = _json_copy(dict(config), "background job config") if config is not None else None
    if kind == "decompose" and provider_spend_authorized is not True:
        raise BackgroundJobError("decomposition background job requires provider-spend authorization")
    if kind == "decompose" and not isinstance(identity.get("compose_project"), str):
        raise BackgroundJobError("decomposition background job requires a compose project")
    if kind == "decompose":
        _require_decompose_options(identity)
    manager.records.mkdir(parents=True, exist_ok=True)
    lock_path = manager.records / "checkouts.lock"
    with contextlib.ExitStack() as transaction:
        try:
            transaction.enter_context(
                _exclusive_file_lock(lock_path, timeout_seconds=LAUNCH_LOCK_TIMEOUT_SECONDS)
            )
        except TimeoutError as exc:
            # Everything above is validation of the caller's arguments plus one
            # idempotent `records.mkdir(exist_ok=True)` that `_open_lock_region`
            # performs anyway: no run root, no launch request, no index and no
            # child exist yet, so this launch can be deferred and re-emitted.
            # `_mark_spawn_failed` takes the same lock *after* a child was
            # spawned and is deliberately left unstamped.
            mark_pre_mutation_lock_contention(exc, lock_path)
            raise
        existing = read_index(manager, task_id)
        if existing is not None and existing.get("status") in ACTIVE_STATUSES:
            raise BackgroundJobError(
                f"{task_id} already has an active background job {existing.get('job_id')}"
            )
        if existing is not None and not cleanup_final(existing):
            raise BackgroundJobError(
                f"{task_id} background job {existing.get('job_id')} left a provider container that "
                "is not finally verified absent; clear it first"
            )
        attempt = _attempt_number(manager, kind, task_id, identity)
        job_id = job_id_for(kind, task_id, identity, attempt,
                            source=manager.source, checkout_root=manager.root)
        run_root = jobs_root(manager) / task_id / job_id
        if run_root.exists():
            raise BackgroundJobError(f"duplicate background job launch refused: {run_root}")
        run_root.mkdir(parents=True)
        parent_identity = host.identify_self()
        job_name = job_name_for(run_root)
        provider_container = _provider_container(kind, job_id, identity,
                                                 source=manager.source, checkout_root=manager.root)
        request_path = run_root / "launch.request.json"
        request = {
            "schema_version": SCHEMA, "job_id": job_id, "kind": kind, "task_id": task_id,
            "attempt": attempt, "source": str(manager.source),
            "checkout_root": str(manager.root), "identity": identity,
            "config": saved_config,
            "provider_spend_authorized": provider_spend_authorized is True,
            "provider_container": provider_container,
            "invocation_id": invocation_id, "created_at_utc": _now(),
            "created_by_pid": os.getpid(), "parent_identity": parent_identity,
            "run_root": str(run_root), "ready": str(run_root / "ready.receipt.json"),
            "receipt": str(run_root / "receipt.json"),
            "stop_request": str(run_root / "stop.request.json"),
            "job_opened": str(run_root / "job.opened.json"),
            "job_name": job_name,
            "stdout_log": str(run_root / "stdout.log"),
            "stderr_log": str(run_root / "stderr.log"),
            "ready_timeout_seconds": _READY_TIMEOUT_SECONDS,
            "binding": dict(binding or {}),
        }
        write_record(request_path, request)
        request_sha256 = hashlib.sha256(request_path.read_bytes()).hexdigest()
        history = list((existing or {}).get("history") or [])
        if existing is not None:
            history.append(summary(existing))
        index = {
            "schema_version": SCHEMA, "task_id": task_id, "source": str(manager.source),
            "checkout_root": str(manager.root), "job_id": job_id, "kind": kind,
            "attempt": attempt, "identity": identity, "run_root": str(run_root),
            "request": str(request_path), "request_sha256": request_sha256,
            "job_name": job_name, "stop_request": str(run_root / "stop.request.json"),
            "provider_container": provider_container, "provider_container_cleanup": None,
            "reconciliation": None,
            "invocation_id": invocation_id, "status": "launched",
            "launched_at_utc": request["created_at_utc"], "pid": None,
            "process_identity": None, "parent_identity": parent_identity,
            "stop": None, "result_status": None, "error": None, "completed_at_utc": None,
            "harvested_at_utc": None, "harvest_invocation_id": None,
            "receipt_sha256": None, "history": history[-20:],
        }
        write_record(index_path(manager, task_id), index)
        try:
            spawned = host.spawn(run_root, request)
        except Exception as exc:
            index.update(status="spawn_failed", error=f"{type(exc).__name__}: {exc}",
                         completed_at_utc=_now())
            write_record(index_path(manager, task_id), index)
            if isinstance(exc, BackgroundJobError):
                raise
            raise BackgroundJobError(f"background job child could not be spawned: {exc}") from exc
        write_record(run_root / "launcher.identity.json", {
            "job_id": job_id, "pid": spawned["pid"], "job_name": job_name,
            "process_identity": spawned["process_identity"],
            "parent_identity": parent_identity,
        })
        index.update(status="running", pid=spawned["pid"],
                     process_identity=spawned["process_identity"])
        write_record(index_path(manager, task_id), index)
        # The child may run its operation only after its identity is durable here
        # and it has acknowledged its Job Object below.
        write_record(run_root / "ready.receipt.json", {
            "schema_version": SCHEMA, "job_id": job_id, "task_id": task_id, "kind": kind,
            "request": str(request_path), "request_sha256": request_sha256,
            "parent_identity": parent_identity, "job_name": job_name,
            "child_identity": spawned["process_identity"], "pid": spawned["pid"],
        })
    # The bounded handoff wait runs outside the checkout transaction so other
    # record writers (a post-crew child persisting its validation) never time
    # out behind a slow child start.
    try:
        host.handoff(run_root, spawned["process_identity"], job_name)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        _mark_spawn_failed(manager, task_id, job_id, error)
        if isinstance(exc, BackgroundJobError):
            raise
        raise BackgroundJobError(f"background job handoff failed: {exc}") from exc
    return index


def _read_receipt(index: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the child's receipt only when bound to this exact ticket and child."""
    receipt = _read_object(Path(str(index["run_root"])) / "receipt.json")
    if receipt is None:
        return None
    if (receipt.get("schema_version") != RECEIPT_SCHEMA
            or receipt.get("job_id") != index.get("job_id")
            or receipt.get("task_id") != index.get("task_id")
            or receipt.get("kind") != index.get("kind")
            or receipt.get("request_sha256") != index.get("request_sha256")
            or receipt.get("pid") != index.get("pid")
            or not isinstance(index.get("process_identity"), Mapping)
            or receipt.get("process_identity") != dict(index["process_identity"])
            or receipt.get("status") not in _RECEIPT_OUTCOMES):
        raise BackgroundJobError(
            f"background job receipt is not bound to ticket {index.get('job_id')} "
            "and its exact child process identity"
        )
    return receipt


def observe(index: Mapping[str, Any], host: JobHost) -> dict[str, Any]:
    """Read-only liveness/receipt view: running, completed, failed, cancelled, died or unverifiable."""
    status = index.get("status")
    if status in TERMINAL_STATUSES:
        return {"status": status, "harvested": True}
    try:
        receipt = _read_receipt(index)
    except BackgroundJobError as exc:
        return {"status": "unverifiable", "detail": str(exc)}
    if receipt is not None:
        return {"status": _RECEIPT_OUTCOMES[str(receipt.get("status"))], "receipt": receipt}
    identity = index.get("process_identity")
    if status != "running" or not isinstance(identity, Mapping):
        return {"status": "died", "detail": "child was never bound to a durable identity"}
    alive = host.alive(identity)
    if alive is True:
        return {"status": "running"}
    if alive is False:
        return {"status": "died", "detail": "child process identity is gone without a receipt"}
    return {"status": "unverifiable", "detail": "child process identity cannot be verified"}


# ---------------------------------------------------------------------------
# Exact provider-container reconciliation


def _inspect_container(docker: DockerRunner, name: str) -> dict[str, Any] | None:
    """Inspect exactly one container by name; None when absent; raises when Docker cannot answer."""
    code, out, err = docker(["container", "inspect", "--format", _CONTAINER_INSPECT_FORMAT, name])
    if code == 0:
        line = out.strip().splitlines()[0] if out.strip() else ""
        try:
            found = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BackgroundJobError(f"docker inspect returned an unreadable record for {name}") from exc
        if not isinstance(found, dict):
            raise BackgroundJobError(f"docker inspect returned no object for {name}")
        return found
    text = (err or out or "").strip()
    if "No such" in text or "no such" in text:
        return None
    raise BackgroundJobError(f"docker inspect failed for {name} (exit {code}): {text[:300]}")


def _progress_result(progress: Mapping[str, Any]) -> dict[str, Any]:
    """The partial outcome of a reconciliation that did not reach its verdict.

    Only what was actually observed: a reconciliation that never started
    reports nothing at all, so recording it can never blank the container name
    or the observations a previous generation recorded.
    """
    if not progress:
        return {"removed": [], "container_sighted": False}
    return {
        "container_name": progress.get("container_name"),
        "compose_project": progress.get("compose_project"),
        "removed": list(progress.get("removed") or []),
        "observations": list(progress.get("observations") or []),
        "container_sighted": bool(progress.get("sighted")),
        "settle_seconds": progress.get("settle_seconds"),
        "window_seconds": progress.get("window_seconds"),
        "watched_seconds": progress.get("watched_seconds"),
    }


def reconcile_provider_container(
    index: Mapping[str, Any], host: JobHost, *,
    clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
    settle_seconds: float | None = None, window_seconds: float | None = None,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Remove exactly the ticket's container whenever it is present; prove the name ends absent.

    Only the recorded name is ever inspected. A container under that name whose
    compose project or service labels do not match the ticket is never removed:
    the mismatch is raised so the caller records it and touches nothing. The
    name is watched for the whole ``window_seconds`` (every 0.5 s), removing on
    every sighting, and the result is ``verified_absent`` only when the final
    ``settle_seconds`` of the window were continuously absent; a sighting late
    in the window extends the watch until that final interval is absent, up to
    a bounded cap, after which the result is ``unverified``. Idempotent. This
    function never holds ``checkouts.lock``.

    ``progress`` is updated in place with every sighting and every removal as
    they happen, and the same partial record is attached to
    :class:`ContainerReconcileError` when a Docker operation fails, so no
    caller can lose a removal — or the renewed cleanup bound it implies —
    because a later Docker call failed or was interrupted.
    """
    settle = float(CONTAINER_SETTLE_SECONDS if settle_seconds is None else settle_seconds)
    window = float(CONTAINER_WINDOW_SECONDS if window_seconds is None else window_seconds)
    container = index.get("provider_container")
    if not isinstance(container, Mapping):
        return {"status": "not_applicable", "container_name": None}
    name = str(container.get("name") or "")
    project = str(container.get("compose_project") or "")
    if not name or not project or name != container_name_for(str(index.get("job_id"))):
        raise BackgroundJobError("provider container identity differs from its ticket; nothing removed")
    # Without the ticket's own job and checkout labels nothing may be removed:
    # the name alone cannot distinguish two checkouts' containers.
    expected_labels = container_labels_for(
        str(index.get("job_id")), index.get("source"), index.get("checkout_root"))
    if not isinstance(container.get("labels"), Mapping) or dict(container["labels"]) != expected_labels:
        raise BackgroundJobError(
            "provider container labels differ from its ticket and checkout; nothing removed")
    started = clock()
    window_end = started + window
    hard_cap = window_end + max(3.0 * settle, 1.0)
    observations: list[dict[str, Any]] = []
    removed: list[str] = []
    progress = {} if progress is None else progress
    # The same list objects: every sighting and removal below is durable to the
    # caller the moment it happens, even if the next Docker call never answers.
    progress.update({"container_name": name, "compose_project": project, "removed": removed,
                     "observations": observations, "sighted": False, "settle_seconds": settle,
                     "window_seconds": window, "watched_seconds": 0.0})
    absent_since: float | None = None
    verified = False
    try:
        while True:
            found = _inspect_container(host.docker, name)
            now = clock()
            progress["watched_seconds"] = round(now - started, 3)
            if found is not None:
                found_name = str(found.get("name") or "").lstrip("/")
                found_project = found.get("project")
                found_service = str(found.get("service") or "")
                found_job = found.get("job") or None
                found_checkout = found.get("checkout") or None
                observations.append({"at": round(now - started, 3), "present": True, "id": found.get("id"),
                                     "job_label": found_job, "checkout_label": found_checkout})
                if found_name != name or found_project != project or (
                        index.get("kind") == "decompose" and not found_service.endswith("-decompose")):
                    raise BackgroundJobError(
                        f"container {name!r} carries other identity (project {found_project!r}, "
                        f"service {found_service!r}); not removed"
                    )
                if (found_job != expected_labels[CONTAINER_JOB_LABEL]
                        or found_checkout != expected_labels[CONTAINER_CHECKOUT_LABEL]):
                    # Another checkout's run, or an unlabelled container that
                    # this ticket cannot prove is its own.
                    raise BackgroundJobError(
                        f"container {name!r} carries other identity (job label {found_job!r}, "
                        f"checkout label {found_checkout!r}); not removed"
                    )
                container_id = str(found.get("id") or "")
                if not container_id:
                    raise BackgroundJobError(f"container {name!r} has no id; not removed")
                # Only now is the sighting this ticket's own container: an
                # unrelated container under the name is never counted or removed.
                progress["sighted"] = True
                code, _out, err = host.docker(["rm", "-f", container_id])
                if code != 0 and "No such" not in (err or ""):
                    raise BackgroundJobError(f"docker rm failed for {container_id[:12]}: {err.strip()[:300]}")
                removed.append(container_id)
                absent_since = None
            else:
                observations.append({"at": round(now - started, 3), "present": False})
                if absent_since is None:
                    absent_since = now
            settled = absent_since is not None and now - absent_since >= settle
            if now >= window_end and settled:
                verified = True
                break
            if now >= hard_cap:
                break
            sleep(0.5)
    except Exception as exc:
        progress["watched_seconds"] = round(clock() - started, 3)
        raise ContainerReconcileError(
            str(exc) if isinstance(exc, BackgroundJobError) else f"{type(exc).__name__}: {exc}",
            partial=_progress_result(progress),
        ) from exc
    progress["watched_seconds"] = round(clock() - started, 3)
    return {
        "status": "verified_absent" if verified else "unverified",
        "container_name": name, "compose_project": project, "removed": removed,
        "observations": observations, "settle_seconds": settle, "window_seconds": window,
        "watched_seconds": progress["watched_seconds"],
        "container_sighted": bool(progress["sighted"]),
        "verified_at_utc": _now() if verified else None,
    }


# ---------------------------------------------------------------------------
# Ticket authentication shared by stops, cleanups and restart reconciliation


def _ticket_problems(manager: Checkouts, index: Mapping[str, Any]) -> list[str]:
    """Mismatches between an index and its immutable ticket (read-only, no process checks).

    The recorded request hash is checked against the ticket bytes on every
    path, including the bytes of a request file that is missing or empty: an
    unreadable ticket authenticates nothing, it never skips the comparison.
    """
    problems: list[str] = []
    task_id = str(index.get("task_id") or "")
    job_id = str(index.get("job_id") or "")
    try:
        validate_task_id(task_id)
    except ValueError:
        problems.append("index task id is not a valid task id")
    expected_root = jobs_root(manager) / task_id / job_id
    if index.get("source") != str(manager.source) or index.get("checkout_root") != str(manager.root):
        problems.append("index names another Source or checkout root")
    request_path = expected_root / "launch.request.json"
    try:
        request_bytes = request_path.read_bytes()
    except OSError:
        problems.append("launch request is missing")
        request_bytes = b""
    else:
        if not request_bytes:
            problems.append("launch request is empty")
    recorded_hash = index.get("request_sha256")
    if not isinstance(recorded_hash, str) or len(recorded_hash) != 64:
        problems.append("index records no ticket hash")
    if hashlib.sha256(request_bytes).hexdigest() != recorded_hash:
        problems.append("launch request bytes differ from the recorded ticket hash")
    request: dict[str, Any] = {}
    if request_bytes:
        try:
            parsed = json.loads(request_bytes)
            if isinstance(parsed, dict):
                request = parsed
            else:
                problems.append("launch request is not an object")
        except (UnicodeError, json.JSONDecodeError):
            problems.append("launch request is unreadable")
    if request:
        if request.get("schema_version") != SCHEMA:
            problems.append("ticket schema differs from the index")
        for field in ("job_id", "task_id", "kind", "identity", "job_name", "source",
                      "checkout_root", "provider_container"):
            if request.get(field) != index.get(field):
                problems.append(f"ticket {field} differs from the index")
    return problems


def _handshake_ticket_problems(manager: Checkouts, index: Mapping[str, Any]) -> list[str]:
    """The child's own handshake must name the same ticket bytes the index records.

    Deliberately not part of :func:`_authentication_problems`: the recorded
    child is still provably itself and its container name is still derived from
    an authenticating ticket, so a restart may stop and quarantine exactly that
    tree and remove exactly that container. It is what makes such a ticket
    unauthenticated for planning, never a reason to leave a container behind.
    """
    expected_root = jobs_root(manager) / str(index.get("task_id") or "") / str(index.get("job_id") or "")
    child = _read_object_quietly(expected_root / "child.identity.json")
    if (child is not None and not child.get("unreadable")
            and child.get("request_sha256") != index.get("request_sha256")):
        return ["child identity handshake names other ticket bytes"]
    return []


def _identity_problems(manager: Checkouts, index: Mapping[str, Any]) -> list[str]:
    """Mismatches between an index's recorded identity and its own run's artifacts.

    Proves, before anything destructive may happen in this ticket's name: the
    owned run directory, the Job Object name derived from it, the job kind, the
    derived provider container name and its compose project, the recorded PID
    and the complete process identity dict, checked against
    ``launcher.identity.json``, the child's ``child.identity.json`` handshake
    and its ``job.opened.json`` acknowledgement. A ticket whose child was never
    spawned records no identity and none is invented for it, but an identity
    artifact that does exist must still match exactly.
    """
    problems: list[str] = []
    task_id = str(index.get("task_id") or "")
    job_id = str(index.get("job_id") or "")
    expected_root = jobs_root(manager) / task_id / job_id
    try:
        if Path(str(index.get("run_root") or "")).resolve() != expected_root.resolve():
            problems.append("run root differs from the owned job path")
    except OSError:
        problems.append("run root cannot be resolved")
    if index.get("job_name") != job_name_for(expected_root):
        problems.append("Job Object name is not derived from the owned run root")
    if index.get("kind") not in JOB_KINDS:
        problems.append("job kind is not a known background job kind")
    try:
        derived_job_id = job_id_for(
            str(index.get("kind") or ""), task_id, index.get("identity") or {},
            index.get("attempt"), source=manager.source, checkout_root=manager.root)
    except (TypeError, ValueError, AttributeError):
        derived_job_id = None
    if derived_job_id != job_id:
        problems.append(
            "job id is not derived from this checkout, Source, task, identity and attempt")
    container = index.get("provider_container")
    if container is not None:
        if (not isinstance(container, Mapping)
                or container.get("name") != container_name_for(job_id)
                or not container.get("compose_project")):
            problems.append("provider container identity is not derived from the ticket")
        elif dict(container.get("labels") or {}) != container_labels_for(
                job_id, manager.source, manager.root):
            problems.append("provider container labels are not derived from this checkout and ticket")
    identity = index.get("process_identity")
    pid = index.get("pid")
    spawned = pid is not None or isinstance(identity, Mapping)
    if index.get("status") == "running" and not spawned:
        problems.append("running index has no exact process identity")
    launcher = _read_object_quietly(expected_root / "launcher.identity.json")
    child = _read_object_quietly(expected_root / "child.identity.json")
    opened = _read_object_quietly(expected_root / "job.opened.json")
    if spawned:
        if (not isinstance(identity, Mapping) or type(identity.get("pid")) is not int
                or identity.get("pid") != pid):
            problems.append("recorded process identity does not name the recorded pid")
        if launcher is None:
            problems.append("launcher identity is missing")
    identity = dict(identity) if isinstance(identity, Mapping) else identity
    if launcher is not None:
        if launcher.get("unreadable"):
            problems.append("launcher identity is unreadable")
        elif (launcher.get("job_id") != job_id or launcher.get("pid") != pid
              or launcher.get("process_identity") != identity
              or launcher.get("job_name") != index.get("job_name")):
            problems.append("launcher identity differs from the index")
    if child is not None:
        if child.get("unreadable"):
            problems.append("child identity handshake is unreadable")
        else:
            if child.get("pid") != pid or child.get("process_identity") != identity:
                problems.append("child identity handshake differs from the index")
            if child.get("job_id") not in (None, job_id):
                problems.append("child identity handshake names another job")
    if opened is not None:
        if opened.get("unreadable"):
            problems.append("Job Object acknowledgement is unreadable")
        elif (opened.get("job_name") != index.get("job_name") or opened.get("pid") != pid
              or opened.get("process_identity") != identity):
            problems.append("Job Object acknowledgement differs from the index")
    return problems


def _authentication_problems(manager: Checkouts, index: Mapping[str, Any]) -> list[str]:
    """Everything that must match before anything destructive happens for a ticket.

    The immutable ticket (request bytes and their recorded hash, schema, task
    id, job id, kind, identity, Job Object name, Source, checkout root) plus the
    owned run directory, the derived container name and compose project, the
    recorded PID and the complete process identity.
    """
    return _identity_problems(manager, index) + _ticket_problems(manager, index)


def _refuse_authentication(manager: Checkouts, index: dict[str, Any],
                           problems: Sequence[str]) -> dict[str, Any]:
    """Record ``authentication_failed`` durably; nothing destructive happens.

    Must be called with ``checkouts.lock`` held and ``index`` freshly read
    under it. The index itself is never deleted or repaired here.
    """
    error = "ticket does not authenticate: " + "; ".join(problems)
    if isinstance(index.get("provider_container"), Mapping):
        _record_refusal(index, error, authentication_failed=True)
    index["authentication"] = {
        "status": "authentication_failed", "problems": list(problems), "at_utc": _now(),
    }
    write_record(index_path(manager, str(index.get("task_id"))), index)
    return index


# ---------------------------------------------------------------------------
# Cleanup records: begun under the lock, run without it, finished under it


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def tombstone_active(index: Mapping[str, Any]) -> bool:
    """True while a late daemon-side create of the ticket's container could still land."""
    cleanup = index.get("provider_container_cleanup")
    until = _parse_utc(cleanup.get("tombstone_until_utc")) if isinstance(cleanup, Mapping) else None
    return until is not None and _utc_now() < until


def cleanup_final(index: Mapping[str, Any]) -> bool:
    """True when the container is verified absent and, if a tombstone was set, rechecked after it."""
    if not isinstance(index.get("provider_container"), Mapping):
        return True
    cleanup = index.get("provider_container_cleanup")
    if not isinstance(cleanup, Mapping) or cleanup.get("status") != "verified_absent":
        return False
    if cleanup.get("tombstone_until_utc") is None:
        return True
    return not tombstone_active(index) and bool(cleanup.get("final_recheck_at_utc"))


def cleanup_pending(index: Mapping[str, Any]) -> bool:
    """True while a ticket names a provider container whose cleanup is not final.

    Verified absence inside the window is not final while its tombstone is
    unfinished: a stop or a startup still owes the exact recheck.
    """
    return isinstance(index.get("provider_container"), Mapping) and not cleanup_final(index)


def _later_utc(*values: Any) -> str | None:
    """The latest of several recorded deadlines: a cleanup bound never moves back."""
    best: datetime | None = None
    latest: str | None = None
    for value in values:
        parsed = _parse_utc(value)
        if parsed is not None and (best is None or parsed > best):
            best, latest = parsed, str(value)
    return latest


def _concurrency_outcome(index: Mapping[str, Any], concurrency: str, detail: str) -> dict[str, Any]:
    """An expected concurrency result: this ticket's cleanup is no longer ours to finish.

    The index was cleared, or a newer ticket replaced it, while the exact Docker
    work ran without the lock. Whatever replaced it is the authority and owes
    its own cleanup; this stale view carries no container and nothing pending,
    so a controller loop continues instead of taking an exception.
    """
    return {
        "task_id": index.get("task_id"), "kind": index.get("kind"),
        "job_id": index.get("job_id"), "status": index.get("status"),
        "provider_container": None, "provider_container_cleanup": None,
        "cleanup_concurrency": concurrency, "detail": detail,
    }


def _cleanup_owner() -> dict[str, Any]:
    try:
        identity = identify(os.getpid())
    except (NotImplementedError, OSError, ValueError):
        identity = None
    return {"pid": os.getpid(), "process_identity": identity if isinstance(identity, dict) else None,
            "since_utc": _now()}


def cleanup_owner_alive(index: Mapping[str, Any]) -> bool:
    """True when the ticket's in-progress cleanup belongs to a process that is still running it."""
    cleanup = index.get("provider_container_cleanup")
    if not isinstance(cleanup, Mapping) or cleanup.get("status") != "in_progress":
        return False
    owner = cleanup.get("owner") if isinstance(cleanup.get("owner"), Mapping) else {}
    key = (str(index.get("task_id")), str(index.get("job_id")), cleanup.get("generation"))
    if owner.get("pid") == os.getpid():
        return key in _ACTIVE_CLEANUPS
    identity = owner.get("process_identity")
    if not isinstance(identity, Mapping):
        return False
    try:
        return bool(matches(dict(identity)))
    except (ValueError, OSError, NotImplementedError):
        return False


def cleanup_retry_due(index: Mapping[str, Any]) -> bool:
    """Whether a controller loop should retry this ticket's pending cleanup now."""
    if not cleanup_pending(index):
        return False
    cleanup = index.get("provider_container_cleanup")
    cleanup = cleanup if isinstance(cleanup, Mapping) else {}
    if cleanup.get("authentication_failed"):
        return False  # a ticket that does not authenticate is never retried automatically
    if cleanup.get("status") == "in_progress" and cleanup_owner_alive(index):
        return False
    if cleanup.get("status") == "verified_absent" and tombstone_active(index):
        return False  # the exact recheck comes after the Docker operation bound
    if cleanup.get("status") in {"refused", "unverified"}:
        last = _parse_utc(cleanup.get("finished_at_utc") or cleanup.get("refused_at_utc"))
        if last is not None and (_utc_now() - last).total_seconds() < _RETRY_BACKOFF_SECONDS:
            return False
    return True


def _begin_cleanup(current: dict[str, Any], *, tombstone_seconds: float,
                   took_over_from: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Mutate an index (held under the lock) into cleanup-in-progress with a new generation."""
    container = current["provider_container"]
    previous = current.get("provider_container_cleanup")
    previous = dict(previous) if isinstance(previous, Mapping) else {}
    bound = max(float(previous.get("tombstone_seconds") or 0.0), float(tombstone_seconds))
    tombstone = previous.get("tombstone_until_utc")
    if tombstone is None and bound > 0:
        tombstone = (_utc_now() + timedelta(seconds=bound)).isoformat()
    current["provider_container_cleanup"] = {
        "status": "in_progress", "generation": int(previous.get("generation") or 0) + 1,
        "attempt": int(previous.get("attempt") or 0) + 1,
        "container_name": container.get("name"), "compose_project": container.get("compose_project"),
        "started_at_utc": _now(), "tombstone_until_utc": tombstone, "tombstone_seconds": bound,
        "final_recheck_at_utc": previous.get("final_recheck_at_utc"),
        "container_sighted": bool(previous.get("container_sighted")),
        "previous_status": previous.get("status"), "previous_error": previous.get("error"),
        "removed": list(previous.get("removed") or []),
        "owner": _cleanup_owner(),
        "took_over_from": ({"generation": took_over_from.get("generation"),
                            "owner": took_over_from.get("owner")} if took_over_from else None),
    }
    return current


def _record_refusal(current: dict[str, Any], error: str, *, authentication_failed: bool = False) -> dict[str, Any]:
    """Mutate an index (held under the lock) into a refused cleanup without a new generation.

    A generation that is in progress is never overwritten. Its ``status``,
    ``generation``, ``owner`` and every progress field (``removed``,
    ``observations``, ``container_sighted``, ``tombstone_until_utc``,
    ``final_recheck_at_utc``) stand exactly as they are, and the refusal is
    recorded beside them as ``refusal_error``/``refused_at_utc`` with
    ``authentication_failed``: its owner still records what it removed and saw
    and still renews the bound, and :func:`_finish_cleanup` then lands the
    generation as ``refused``, never verified. No path here shortens a deadline
    or drops a removal.
    """
    previous = current.get("provider_container_cleanup")
    previous = dict(previous) if isinstance(previous, Mapping) else {}
    container = current.get("provider_container") or {}
    record = {
        **previous, "refused_at_utc": _now(),
        "container_name": previous.get("container_name") or container.get("name"),
        "removed": list(previous.get("removed") or []),
        "authentication_failed": bool(authentication_failed or previous.get("authentication_failed")),
    }
    if previous.get("status") == "in_progress" and cleanup_owner_alive(current):
        # A live owner is mid-generation: it still owes the durable record of
        # what it removed and saw, so only the refusal is added beside it.
        record["refusal_error"] = error
    else:
        # Nothing is in flight (or its owner is gone): the refusal is the
        # status, and every progress field above is carried unchanged.
        record["status"] = "refused"
        record["error"] = error
    # Belt and braces: a refusal may only ever keep or extend the recorded bound.
    record["tombstone_until_utc"] = _later_utc(
        previous.get("tombstone_until_utc"), record.get("tombstone_until_utc"))
    record["final_recheck_at_utc"] = previous.get("final_recheck_at_utc")
    record["container_sighted"] = bool(previous.get("container_sighted"))
    current["provider_container_cleanup"] = record
    return current


def _finish_cleanup(manager: Checkouts, begun: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    """Under the lock: record the unlocked reconciliation only for the exact generation begun.

    A generation that was taken over meanwhile is not an error: the durable
    state written by the newer owner stands and is returned as it is.
    """
    cleanup_begun = begun["provider_container_cleanup"]
    generation = cleanup_begun["generation"]
    key = (str(begun["task_id"]), str(begun["job_id"]), generation)
    try:
        with _exclusive_file_lock(manager.records / "checkouts.lock", timeout_seconds=10):
            current = read_index(manager, str(begun["task_id"]))
            if current is None:
                return _concurrency_outcome(
                    begun, "cleared", "the background job index was cleared during the cleanup")
            if current.get("job_id") != begun.get("job_id"):
                return current
            cleanup = current.get("provider_container_cleanup")
            # A refusal that landed on this exact generation before it finished
            # is not a takeover: this owner still owes the durable record of
            # what it removed and saw, and of the bound that restarts from it.
            refused_in_flight = (isinstance(cleanup, Mapping) and cleanup.get("status") == "refused"
                                 and cleanup.get("generation") == generation
                                 and not cleanup.get("finished_at_utc"))
            if (not isinstance(cleanup, Mapping) or cleanup.get("generation") != generation
                    or (cleanup.get("status") != "in_progress" and not refused_in_flight)):
                return current
            previously_removed = list(cleanup.get("removed") or [])
            new_removals = [item for item in result.get("removed") or [] if item not in previously_removed]
            merged = {**cleanup, **dict(result), "generation": generation, "finished_at_utc": _now(),
                      "removed": previously_removed + new_removals}
            # A removal, or any sighting of the exact container (including one a
            # failed or interrupted Docker operation left unremoved), restarts
            # the operation bound and owes the final recheck again. The bound
            # only ever moves forward: an exception can never restore an older
            # deadline, and a cleanup that saw its container is never complete.
            sighted = bool(new_removals or result.get("container_sighted")
                           or any(item.get("present") for item in result.get("observations") or []))
            bound = float(cleanup.get("tombstone_seconds") or 0.0)
            renewed = ((_utc_now() + timedelta(seconds=bound)).isoformat()
                       if sighted and bound > 0 else None)
            # This generation's own verdict, never sticky: a later generation
            # that looks again and sees nothing is what earns the final recheck.
            # The value carried into an in-flight record only keeps that record
            # honest until its own generation reports.
            merged["container_sighted"] = sighted
            merged["tombstone_until_utc"] = _later_utc(
                cleanup.get("tombstone_until_utc"), merged.get("tombstone_until_utc"), renewed)
            merged["final_recheck_at_utc"] = (
                None if sighted else cleanup.get("final_recheck_at_utc"))
            if cleanup.get("authentication_failed") or cleanup.get("refusal_error") or refused_in_flight:
                # A refusal landed while this generation ran without the lock.
                # Its removals, sightings and renewed bound are durable, but a
                # ticket that does not authenticate can never read as verified.
                if merged.get("error"):
                    merged["reconcile_error"] = merged["error"]
                merged["status"] = "refused"
                merged["error"] = (cleanup.get("refusal_error") or cleanup.get("error")
                                   or merged.get("error"))
                merged["authentication_failed"] = True
                merged["verified_at_utc"] = None
                merged["final_recheck_at_utc"] = None
            current["provider_container_cleanup"] = merged
            write_record(index_path(manager, str(begun["task_id"])), current)
            return current
    finally:
        _ACTIVE_CLEANUPS.discard(key)


def _finish_interrupted(manager: Checkouts, begun: Mapping[str, Any],
                        progress: Mapping[str, Any], exc: BaseException) -> None:
    """Keep an interrupted cleanup's partial progress durable without masking the interrupt."""
    try:
        _finish_cleanup(manager, begun, {
            **_progress_result(progress), "status": "refused",
            "error": f"container reconciliation was interrupted: {type(exc).__name__}: {exc}",
        })
    except BaseException:
        _ACTIVE_CLEANUPS.discard((
            str(begun.get("task_id")), str(begun.get("job_id")),
            (begun.get("provider_container_cleanup") or {}).get("generation"),
        ))


def _reconcile_unlocked(begun: Mapping[str, Any], host: JobHost, *, clock, sleep,
                        settle_seconds: float | None, window_seconds: float | None,
                        progress: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the exact reconciliation; a failure is a refused result that still
    carries every sighting and removal made before it."""
    progress = {} if progress is None else progress
    try:
        return reconcile_provider_container(
            begun, host, clock=clock, sleep=sleep,
            settle_seconds=settle_seconds, window_seconds=window_seconds, progress=progress,
        )
    except ContainerReconcileError as exc:
        return {**exc.partial, "status": "refused", "error": str(exc)}
    except BackgroundJobError as exc:
        return {**_progress_result(progress), "status": "refused", "error": str(exc)}
    except Exception as exc:
        return {**_progress_result(progress), "status": "refused",
                "error": f"{type(exc).__name__}: {exc}"}


def _coalesce_wait_seconds() -> float:
    return float(CONTAINER_WINDOW_SECONDS) + 3.0 * float(CONTAINER_SETTLE_SECONDS) + 10.0


def _run_cleanup(manager: Checkouts, index: Mapping[str, Any], host: JobHost, *,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 settle_seconds: float | None = None, window_seconds: float | None = None,
                 tombstone_seconds: float | None = None) -> dict[str, Any]:
    """Reconcile one ticket's exact container: authenticate and begin under the lock, run
    without it, finish under it.

    The immutable ticket is reauthenticated before anything destructive: a
    tampered index is recorded as refused and nothing is inspected or removed.
    A cleanup already in progress under a live owner is waited for (bounded)
    instead of superseded; one whose owner is gone is taken over.
    """
    tombstone = float(CONTAINER_TOMBSTONE_SECONDS if tombstone_seconds is None else tombstone_seconds)
    task_id = str(index["task_id"])
    job_id = str(index.get("job_id"))
    deadline = clock() + _coalesce_wait_seconds()
    while True:
        with _exclusive_file_lock(manager.records / "checkouts.lock", timeout_seconds=10):
            current = read_index(manager, task_id)
            if current is None:
                return _concurrency_outcome(
                    index, "cleared", "the background job index was cleared before this cleanup")
            if current.get("job_id") != job_id:
                return _concurrency_outcome(
                    index, "superseded", "a newer background job ticket replaced this one")
            if not isinstance(current.get("provider_container"), Mapping):
                return current
            problems = _authentication_problems(manager, current)
            if problems:
                return _refuse_authentication(manager, current, problems)
            cleanup = current.get("provider_container_cleanup")
            waiting = False
            if isinstance(cleanup, Mapping) and cleanup.get("status") == "in_progress":
                if cleanup_owner_alive(current):
                    waiting = True
                else:
                    begun = _begin_cleanup(current, tombstone_seconds=tombstone, took_over_from=cleanup)
            else:
                begun = _begin_cleanup(current, tombstone_seconds=tombstone)
            if not waiting:
                write_record(index_path(manager, task_id), begun)
        if not waiting:
            break
        if clock() >= deadline:
            return current  # still owned by a live process: its durable state stands
        sleep(0.5)
    key = (task_id, job_id, begun["provider_container_cleanup"]["generation"])
    _ACTIVE_CLEANUPS.add(key)
    progress: dict[str, Any] = {}
    try:
        result = _reconcile_unlocked(begun, host, clock=clock, sleep=sleep,
                                     settle_seconds=settle_seconds, window_seconds=window_seconds,
                                     progress=progress)
    except BaseException as exc:
        # An interrupt must not lose a removal or leave the bound where it was.
        _finish_interrupted(manager, begun, progress, exc)
        raise
    return _finish_cleanup(manager, begun, result)


def _exact_look(manager: Checkouts, index: Mapping[str, Any], host: JobHost, *,
                clock: Callable[[], float], sleep: Callable[[float], None]) -> dict[str, Any]:
    """One more exact look at the name; a sighting removes it and reruns the whole window."""
    before = list((index.get("provider_container_cleanup") or {}).get("removed") or [])
    current = _run_cleanup(manager, index, host, clock=clock, sleep=sleep,
                           settle_seconds=0.0, window_seconds=0.0)
    if current.get("cleanup_concurrency"):
        return current
    cleanup = current.get("provider_container_cleanup") or {}
    if cleanup.get("status") == "verified_absent" and list(cleanup.get("removed") or []) != before:
        current = _run_cleanup(manager, current, host, clock=clock, sleep=sleep)
    return current


def _record_final_recheck(manager: Checkouts, index: Mapping[str, Any]) -> dict[str, Any]:
    """Record the exact absence check owed after the Docker operation bound.

    A ticket cleared or superseded meanwhile is an expected concurrency
    outcome, not a failure: the durable state that replaced it is the
    authority and nothing is raised into the controller.
    """
    with _exclusive_file_lock(manager.records / "checkouts.lock", timeout_seconds=10):
        current = read_index(manager, str(index["task_id"]))
        if current is None:
            return _concurrency_outcome(
                index, "cleared", "the background job index was cleared during the final recheck")
        if current.get("job_id") != index.get("job_id"):
            return _concurrency_outcome(
                index, "superseded", "a newer background job ticket replaced this one")
        cleanup = dict(current.get("provider_container_cleanup") or {})
        expected = (index.get("provider_container_cleanup") or {}).get("generation")
        if (cleanup.get("status") != "verified_absent" or cleanup.get("generation") != expected
                or cleanup.get("container_sighted") or tombstone_active(current)):
            return current
        cleanup["final_recheck_at_utc"] = _now()
        current["provider_container_cleanup"] = cleanup
        write_record(index_path(manager, str(index["task_id"])), current)
        return current


def _wait_for_tombstone(index: Mapping[str, Any], *, clock: Callable[[], float],
                        sleep: Callable[[float], None]) -> None:
    """Sleep until the ticket's Docker operation bound has passed (bounded)."""
    cleanup = index.get("provider_container_cleanup") or {}
    until = _parse_utc(cleanup.get("tombstone_until_utc"))
    if until is None:
        return
    deadline = clock() + float(cleanup.get("tombstone_seconds") or CONTAINER_TOMBSTONE_SECONDS) + 5.0
    while True:
        remaining = (until - _utc_now()).total_seconds()
        if remaining <= 0 or clock() >= deadline:
            return
        sleep(min(0.5, remaining))


def settle_cleanup(manager: Checkouts, index: Mapping[str, Any], host: JobHost, *,
                   clock: Callable[[], float] = time.monotonic,
                   sleep: Callable[[float], None] = time.sleep,
                   wait_for_tombstone: bool = False) -> dict[str, Any]:
    """Drive one ticket's container cleanup as far as it can go right now.

    Not yet verified: run (or rerun) the exact window. Verified with an active
    tombstone: take one exact look now (a sighting is removed and reruns the
    window), then either wait the bound out (``wait_for_tombstone``) or return
    still pending. Bound passed: record the final recheck. Every step
    reauthenticates the ticket; a refusal is retained, never hidden.
    """
    current = read_index(manager, str(index["task_id"]))
    if current is None:
        return _concurrency_outcome(index, "cleared", "the background job index was cleared")
    if current.get("job_id") != index.get("job_id"):
        return current
    if not isinstance(current.get("provider_container"), Mapping) or cleanup_final(current):
        return current
    cleanup = current.get("provider_container_cleanup") or {}
    looked = False
    if cleanup.get("status") != "verified_absent":
        current = _run_cleanup(manager, current, host, clock=clock, sleep=sleep)
        cleanup = current.get("provider_container_cleanup") or {}
        if current.get("cleanup_concurrency") or cleanup.get("status") != "verified_absent":
            return current
        looked = True  # the window just ended absent; nothing new to look at yet
    if tombstone_active(current):
        if not looked:
            current = _exact_look(manager, current, host, clock=clock, sleep=sleep)
        if current.get("cleanup_concurrency") or not wait_for_tombstone or (
                current.get("provider_container_cleanup") or {}).get("status") != "verified_absent":
            return current
        _wait_for_tombstone(current, clock=clock, sleep=sleep)
        reread = read_index(manager, str(index["task_id"]))
        if reread is None:
            return _concurrency_outcome(
                index, "cleared", "the background job index was cleared while its bound passed")
        if reread.get("job_id") != current.get("job_id"):
            return reread
        current = reread
        if tombstone_active(current):
            return current
    if cleanup_final(current):
        return current
    current = _exact_look(manager, current, host, clock=clock, sleep=sleep)
    if current.get("cleanup_concurrency"):
        return current
    if (current.get("provider_container_cleanup") or {}).get("status") != "verified_absent" \
            or tombstone_active(current):
        return current
    return _record_final_recheck(manager, current)


def harvest(manager: Checkouts, index: Mapping[str, Any], observed: Mapping[str, Any],
            *, invocation_id: str, host: JobHost | None = None,
            clock: Callable[[], float] = time.monotonic,
            sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Persist one terminal observation onto the controller-owned index.

    With a ``host``, a ticket that names a provider container is then
    reconciled exactly (see :func:`reconcile_provider_container`) outside the
    lock: the harvest reauthenticates the ticket and records the cleanup as in
    progress under the lock, releases it for the Docker work, and records the
    outcome under the lock again only for that generation. A refusal or an
    unverifiable Docker is retained too, never hidden; a repeated stop retries
    it.
    """
    outcome = observed.get("status")
    if outcome not in {"completed", "failed", "died", "cancelled"}:
        raise BackgroundJobError(f"background job outcome {outcome!r} is not harvestable")
    begun: dict[str, Any] | None = None
    with _exclusive_file_lock(manager.records / "checkouts.lock", timeout_seconds=10):
        current = read_index(manager, str(index["task_id"]))
        if current is None or current.get("job_id") != index.get("job_id"):
            raise BackgroundJobError("background job index changed before harvest")
        if current.get("status") in TERMINAL_STATUSES:
            return current
        receipt = observed.get("receipt") or {}
        result = receipt.get("result") if isinstance(receipt.get("result"), Mapping) else {}
        if outcome == "completed":
            error = None
        elif outcome == "failed":
            error = receipt.get("error")
        else:
            error = receipt.get("error") or observed.get("detail")
        current.update({
            "status": outcome,
            "result_status": result.get("status") if outcome == "completed" else None,
            "error": error,
            "completed_at_utc": receipt.get("completed_at_utc") or _now(),
            "harvested_at_utc": _now(),
            "harvest_invocation_id": invocation_id,
            "receipt_sha256": (
                hashlib.sha256((Path(str(current["run_root"])) / "receipt.json").read_bytes()).hexdigest()
                if receipt else None
            ),
        })
        if host is not None and isinstance(current.get("provider_container"), Mapping):
            problems = _authentication_problems(manager, current)
            if problems:
                _record_refusal(current, "ticket does not authenticate: " + "; ".join(problems),
                                authentication_failed=True)
                current["authentication"] = {
                    "status": "authentication_failed", "problems": list(problems), "at_utc": _now(),
                }
            else:
                # A completed child removed its own container before exiting:
                # one look suffices and no tombstone applies. Every other
                # outcome ends a tree that may still have a create in flight.
                begun = _begin_cleanup(current, tombstone_seconds=0.0 if outcome == "completed"
                                       else float(CONTAINER_TOMBSTONE_SECONDS))
        write_record(index_path(manager, str(index["task_id"])), current)
    if begun is None:
        return current
    key = (str(begun["task_id"]), str(begun["job_id"]), begun["provider_container_cleanup"]["generation"])
    _ACTIVE_CLEANUPS.add(key)
    progress: dict[str, Any] = {}
    try:
        if outcome == "completed":
            result = _reconcile_unlocked(begun, host, clock=clock, sleep=sleep,
                                         settle_seconds=0.0, window_seconds=0.0, progress=progress)
        else:
            result = _reconcile_unlocked(begun, host, clock=clock, sleep=sleep,
                                         settle_seconds=None, window_seconds=None, progress=progress)
    except BaseException as exc:
        _finish_interrupted(manager, begun, progress, exc)
        raise
    return _finish_cleanup(manager, begun, result)


# ---------------------------------------------------------------------------
# Operator stop


def stop_payload(index: Mapping[str, Any], reason: str) -> dict[str, Any]:
    """The authenticated stop request: bound to ticket, child identity and Job Object."""
    return {
        "schema_version": STOP_SCHEMA,
        "task_id": index.get("task_id"), "kind": index.get("kind"),
        "job_id": index.get("job_id"), "request_sha256": index.get("request_sha256"),
        "pid": index.get("pid"), "process_identity": index.get("process_identity"),
        "job_name": index.get("job_name"), "reason": reason,
        "requested_at_utc": _now(),
    }


def _owned_run_root(manager: Checkouts, index: Mapping[str, Any]) -> Path:
    task_id = validate_task_id(str(index.get("task_id")))
    expected_root = (jobs_root(manager) / task_id / str(index.get("job_id"))).resolve()
    if Path(str(index.get("run_root"))).resolve() != expected_root:
        raise BackgroundJobError("background job run root differs from its owned path")
    return expected_root


def _owned_job_name(manager: Checkouts, index: Mapping[str, Any]) -> str:
    """The only Job Object a stop may reach: the one derived from this ticket's own run root."""
    expected_root = _owned_run_root(manager, index)
    job_name = index.get("job_name")
    if not isinstance(job_name, str) or job_name != job_name_for(expected_root):
        raise BackgroundJobError(
            "background job Job Object name is not derived from its owned run; nothing was terminated"
        )
    return job_name


def _owned_stop_path(manager: Checkouts, index: Mapping[str, Any]) -> Path:
    expected_root = _owned_run_root(manager, index)
    stop_path = Path(str(index.get("stop_request") or "")).resolve()
    if stop_path != expected_root / "stop.request.json":
        raise BackgroundJobError("background job stop path differs from its owned run")
    _owned_job_name(manager, index)
    return stop_path


def request_stop(manager: Checkouts, index: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    """Write, or re-verify, the bound stop request of one exact job. Terminates nothing."""
    task_id = validate_task_id(str(index.get("task_id")))
    with _exclusive_file_lock(manager.records / "checkouts.lock", timeout_seconds=10):
        current = read_index(manager, task_id)
        if current is None or current.get("job_id") != index.get("job_id"):
            raise BackgroundJobError("background job index changed before stop")
        if current.get("status") in TERMINAL_STATUSES:
            return current
        if current.get("status") != "running" or not isinstance(current.get("process_identity"), Mapping):
            # A child that was never bound never received permission to work;
            # it exits by itself when its ready receipt does not arrive.
            return current
        # Nothing may be bound, signalled or terminated in this ticket's name
        # until its own run's artifacts prove the recorded PID, the complete
        # process identity, the Job Object name and the owned run directory.
        problems = _identity_problems(manager, current)
        if problems:
            current = _refuse_authentication(manager, current, problems)
            # The ownership checks raise their own exact message when the run
            # root, Job Object name or stop path is the mismatch.
            _owned_stop_path(manager, current)
            raise BackgroundJobError(
                "background job stop refused: the ticket does not authenticate: "
                + "; ".join(problems) + "; nothing was stopped"
            )
        stop_path = _owned_stop_path(manager, current)
        payload = stop_payload(current, reason)
        previous = _read_object(stop_path)
        if previous is not None:
            if any(previous.get(field) != payload.get(field) for field in _STOP_IDENTITY_FIELDS):
                raise BackgroundJobError("existing background job stop request has a different identity")
            payload = previous
        else:
            write_record(stop_path, payload)
        current["stop"] = {
            "requested_at_utc": payload.get("requested_at_utc"), "reason": payload.get("reason"),
            "path": str(stop_path),
        }
        write_record(index_path(manager, task_id), current)
        return current


def _retry_pending_cleanup(manager: Checkouts, index: Mapping[str, Any], host: JobHost, *,
                           clock: Callable[[], float], sleep: Callable[[float], None],
                           finalize: bool) -> dict[str, Any]:
    """A terminal ticket whose container cleanup is not final is still stop work."""
    current = read_index(manager, str(index["task_id"])) or dict(index)
    if current.get("job_id") == index.get("job_id") and cleanup_pending(current):
        return settle_cleanup(manager, current, host, clock=clock, sleep=sleep,
                              wait_for_tombstone=finalize)
    return current


def _enforce_stop(manager: Checkouts, index: Mapping[str, Any], *, host: JobHost,
                  reason: str, invocation_id: str,
                  clock: Callable[[], float] = time.monotonic,
                  sleep: Callable[[float], None] = time.sleep,
                  finalize: bool = False) -> dict[str, Any]:
    """After the grace period: harvest a receipt, or terminate the exact tree and retain it.

    The harvest reconciles the ticket's exact provider container once the tree
    has ended, so the retained stop result states whether it is verified
    absent; a ticket already terminal with a pending cleanup is retried.
    """
    observed = observe(index, host)
    if observed.get("status") == "unverifiable":
        raise BackgroundJobError(f"background job cannot be verified for stop: {observed.get('detail')}")
    if observed.get("status") == "running":
        identity = index.get("process_identity")
        job_name = _owned_job_name(manager, index)
        if not isinstance(identity, Mapping) or identity.get("pid") != index.get("pid"):
            raise BackgroundJobError("background job stop requires exact child and Job Object identity")
        # Re-proven immediately before the only destructive call: an index that
        # does not name its own run's recorded child terminates nothing.
        problems = _identity_problems(manager, index)
        if problems:
            with _exclusive_file_lock(manager.records / "checkouts.lock", timeout_seconds=10):
                current = read_index(manager, str(index.get("task_id")))
                if current is not None and current.get("job_id") == index.get("job_id"):
                    _refuse_authentication(manager, current, problems)
            raise BackgroundJobError(
                "background job stop refused: the ticket does not authenticate: "
                + "; ".join(problems) + "; nothing was terminated"
            )
        host.stop(identity, job_name)
        observed = observe(index, host)
        if observed.get("status") == "unverifiable":
            raise BackgroundJobError(f"background job exit cannot be verified after stop: {observed.get('detail')}")
        if observed.get("status") == "running":
            raise BackgroundJobError("background job is still running after Job Object termination")
    if observed.get("status") == "died":
        observed = {"status": "cancelled",
                    "detail": f"operator stopped background job without a receipt: {reason}"}
    if observed.get("status") in TERMINAL_STATUSES and observed.get("harvested"):
        return _retry_pending_cleanup(manager, index, host, clock=clock, sleep=sleep, finalize=finalize)
    current = harvest(manager, index, observed, invocation_id=invocation_id, host=host,
                      clock=clock, sleep=sleep)
    if finalize and cleanup_pending(current):
        current = settle_cleanup(manager, current, host, clock=clock, sleep=sleep, wait_for_tombstone=True)
    return current


def cancel(manager: Checkouts, index: Mapping[str, Any], *, host: JobHost, reason: str,
           grace_seconds: float = STOP_GRACE_SECONDS,
           invocation_id: str = "operator-stop",
           clock: Callable[[], float] = time.monotonic,
           sleep: Callable[[float], None] = time.sleep,
           finalize: bool = False) -> dict[str, Any]:
    """Stop one exact job: bound request, bounded cooperative grace, then tree termination.

    Repeating it on a terminal job retries the pending container cleanup
    (one exact look while the tombstone is active; the final recheck after
    it) and is otherwise a no-op. With ``finalize`` the call also waits the
    tombstone out. The result is complete only when :func:`cleanup_pending`
    is false for it.
    """
    if not isinstance(grace_seconds, (int, float)) or grace_seconds < 0:
        raise BackgroundJobError("background job stop grace must be a non-negative number")
    current = request_stop(manager, index, reason=reason)
    if current.get("status") in TERMINAL_STATUSES:
        return _retry_pending_cleanup(manager, current, host, clock=clock, sleep=sleep, finalize=finalize)
    deadline = clock() + float(grace_seconds)
    while observe(current, host).get("status") == "running" and clock() < deadline:
        sleep(min(0.05, max(0.0, deadline - clock())))
    return _enforce_stop(manager, current, host=host, reason=reason, invocation_id=invocation_id,
                         clock=clock, sleep=sleep, finalize=finalize)


def cancel_all(manager: Checkouts, *, host: JobHost, reason: str,
               grace_seconds: float = STOP_GRACE_SECONDS,
               invocation_id: str = "operator-stop",
               clock: Callable[[], float] = time.monotonic,
               sleep: Callable[[float], None] = time.sleep,
               finalize: bool = False) -> list[dict[str, Any]]:
    """Stop every active job and drive every pending container cleanup.

    Active jobs are requested together, share one grace period, then are
    enforced one by one; terminal jobs whose exact container cleanup is not
    final are retried. With ``finalize`` each tombstone is waited out and the
    final recheck recorded, so the result can be complete. Per-job failures
    are retained in the result instead of aborting the others. Each result
    carries ``cleanup_pending`` and, while a tombstone is active,
    ``retry_after_utc``.
    """
    if not isinstance(grace_seconds, (int, float)) or grace_seconds < 0:
        raise BackgroundJobError("background job stop grace must be a non-negative number")
    results: list[dict[str, Any]] = []
    requested: list[dict[str, Any]] = []
    retries: list[dict[str, Any]] = []
    readable, unreadable = scan_indexes(manager)
    for item in unreadable:
        # Unreadable is never "nothing remains": the stop stays incomplete and
        # the operator is handed the exact path and error. Nothing is repaired.
        results.append({
            "task_id": item["task_id"], "job_id": None, "status": "unreadable_index",
            "cleanup_pending": True, "retry_after_utc": None,
            "path": item["path"], "error": item["error"],
        })
    for task_id in sorted(readable, key=_task_order):
        index = readable[task_id]
        if index is None:
            continue
        if index.get("status") not in ACTIVE_STATUSES:
            if cleanup_pending(index):
                retries.append(index)
            continue
        try:
            requested.append(request_stop(manager, index, reason=reason))
        except Exception as exc:
            results.append({"task_id": task_id, "job_id": index.get("job_id"),
                            "status": "stop_failed", "error": f"{type(exc).__name__}: {exc}"})
    deadline = clock() + float(grace_seconds)
    pending = [index for index in requested if index.get("status") in ACTIVE_STATUSES]
    while pending and clock() < deadline:
        pending = [index for index in pending if observe(index, host).get("status") == "running"]
        if pending:
            sleep(min(0.05, max(0.0, deadline - clock())))
    for index in requested:
        try:
            results.append(_stop_result(_enforce_stop(
                manager, index, host=host, reason=reason, invocation_id=invocation_id,
                clock=clock, sleep=sleep, finalize=finalize,
            )))
        except Exception as exc:
            results.append({"task_id": index.get("task_id"), "job_id": index.get("job_id"),
                            "status": "stop_failed", "error": f"{type(exc).__name__}: {exc}"})
    for index in retries:
        try:
            results.append(_stop_result(settle_cleanup(
                manager, index, host, clock=clock, sleep=sleep, wait_for_tombstone=finalize)))
        except Exception as exc:
            results.append({"task_id": index.get("task_id"), "job_id": index.get("job_id"),
                            "status": "stop_failed", "error": f"{type(exc).__name__}: {exc}"})
    return results


def _stop_result(index: Mapping[str, Any]) -> dict[str, Any]:
    cleanup = index.get("provider_container_cleanup") or {}
    return {**summary(index), "cleanup_pending": cleanup_pending(index),
            "retry_after_utc": cleanup.get("tombstone_until_utc") if tombstone_active(index) else None}


def stop_complete(results: Sequence[Mapping[str, Any]]) -> bool:
    """True when every stop result is terminal with no container cleanup pending."""
    return all(
        item.get("status") in TERMINAL_STATUSES and not item.get("cleanup_pending")
        for item in results
    )


# ---------------------------------------------------------------------------
# Restart reconciliation


def authenticate_index(manager: Checkouts, index: Mapping[str, Any]) -> dict[str, Any]:
    """Prove one ticket before acting on it (read-only).

    ``identity_bound`` states whether the recorded PID, process identity and
    Job Object name are tied to this ticket's own run root by the artifacts
    written at launch and by the child's own handshake; without that, nothing
    may be stopped in the ticket's name. ``problems`` lists every mismatch,
    binding problems first, then the immutable-ticket problems shared with
    every cleanup retry.
    """
    binding = _identity_problems(manager, index)
    problems = _ticket_problems(manager, index) + _handshake_ticket_problems(manager, index)
    return {"authenticated": not binding and not problems, "identity_bound": not binding,
            "problems": binding + problems}


def _read_object_quietly(path: Path) -> dict[str, Any] | None:
    try:
        return _read_object(path)
    except BackgroundJobError:
        return {"unreadable": True}


def reconcile_startup(
    manager: Checkouts, host: JobHost, *, invocation_id: str,
    grace_seconds: float = STOP_GRACE_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Under the controller lock, settle every ticket before anything is planned or launched.

    Outcomes per ticket: ``adopted`` (authenticated, alive, contained; its Job
    Object handle is retained), ``harvested`` (its receipt or death recorded
    and its exact container reconciled to a final verdict), ``quarantined``
    (alive with a bound identity but a ticket that no longer authenticates:
    bound stop, exact tree and container ended, task blocked with the retained
    reason), and ``container_verified`` (a terminal ticket whose container
    cleanup was still pending, including an unfinished tombstone). Each
    pending cleanup is retried exactly, its tombstone waited out (bounded) and
    its final recheck recorded before the controller plans. A live child whose
    identity cannot be bound to its ticket, an unverifiable child, a stop that
    cannot be proven, or a container that is not finally verified absent
    raises :class:`StartupRefused`: nothing is killed or removed on a guess,
    and the controller does not plan beside it. Docker work never runs while
    ``checkouts.lock`` is held.
    """
    outcomes: list[dict[str, Any]] = []
    readable, unreadable = scan_indexes(manager)
    if unreadable:
        # A record that cannot be read is not an absent job: nothing is
        # repaired or deleted here and the controller does not plan beside it.
        raise StartupRefused(
            "background job state cannot be authenticated: "
            + "; ".join(f"{item['path']}: {item['error']}" for item in unreadable)
            + "; repair or archive it by hand before the controller plans",
            outcomes=outcomes, index={"unreadable_indexes": unreadable},
        )
    for task_id in sorted(readable, key=_task_order):
        index = read_index(manager, task_id)
        if index is None:
            continue
        label = f"{task_id} background job {index.get('job_id')}"
        if index.get("status") not in ACTIVE_STATUSES:
            if cleanup_pending(index):
                try:
                    current = settle_cleanup(manager, index, host, clock=clock, sleep=sleep,
                                             wait_for_tombstone=True)
                except BackgroundJobError as exc:
                    raise StartupRefused(
                        f"{label} container cleanup could not be settled: {exc}",
                        outcomes=outcomes, index=summary(index),
                    ) from exc
                if current.get("cleanup_concurrency"):
                    # Cleared or replaced by another owner: whatever replaced it
                    # owes its own cleanup and is settled on its own turn.
                    outcomes.append({"outcome": "cleanup_superseded", **summary(current),
                                     "detail": current.get("detail")})
                    continue
                _require_verified(label, current, outcomes)
                outcomes.append({"outcome": "container_verified", **summary(current)})
            continue
        auth = authenticate_index(manager, index)
        observed = observe(index, host)
        status = observed.get("status")
        if status == "unverifiable":
            raise StartupRefused(
                f"{label} cannot be verified: {observed.get('detail')}; refusing to plan beside it",
                outcomes=outcomes, index=summary(index),
            )
        if status == "running":
            if not auth["identity_bound"]:
                raise StartupRefused(
                    f"{label} is alive but its process identity is not bound to its ticket "
                    f"({'; '.join(auth['problems'])}); nothing was stopped",
                    outcomes=outcomes, index=summary(index),
                )
            if auth["authenticated"]:
                try:
                    host.adopt(dict(index["process_identity"]), str(index.get("job_name")))
                except Exception as exc:
                    raise StartupRefused(
                        f"{label} is alive but its Job Object cannot be adopted: {exc}",
                        outcomes=outcomes, index=summary(index),
                    ) from exc
                outcomes.append({"outcome": "adopted", **summary(index)})
                continue
            reason = "restart reconciliation: " + "; ".join(auth["problems"])
            try:
                current = request_stop(manager, index, reason=reason)
                deadline = clock() + float(grace_seconds)
                while observe(current, host).get("status") == "running" and clock() < deadline:
                    sleep(min(0.05, max(0.0, deadline - clock())))
                current = _enforce_stop(manager, current, host=host, reason=reason,
                                        invocation_id=invocation_id, clock=clock, sleep=sleep,
                                        finalize=True)
            except BackgroundJobError as exc:
                raise StartupRefused(f"{label} could not be stopped safely: {exc}",
                                     outcomes=outcomes, index=summary(index)) from exc
            current = _record_reconciliation(manager, current, {
                "outcome": "quarantined", "problems": auth["problems"],
                "invocation_id": invocation_id, "at_utc": _now(),
            })
            # The quarantine is durable whether or not its container verified.
            outcomes.append({"outcome": "quarantined", **summary(current)})
            _require_verified(label, current, outcomes)
            continue
        # completed, failed or died: retain the durable outcome; never relaunch.
        try:
            current = harvest(manager, index, observed, invocation_id=invocation_id, host=host,
                              clock=clock, sleep=sleep)
            if cleanup_pending(current):
                current = settle_cleanup(manager, current, host, clock=clock, sleep=sleep,
                                         wait_for_tombstone=True)
        except BackgroundJobError as exc:
            raise StartupRefused(f"{label} could not be harvested: {exc}",
                                 outcomes=outcomes, index=summary(index)) from exc
        if not auth["authenticated"]:
            current = _record_reconciliation(manager, current, {
                "outcome": "harvested_unauthenticated", "problems": auth["problems"],
                "invocation_id": invocation_id, "at_utc": _now(),
            })
        outcomes.append({"outcome": "harvested", **summary(current)})
        _require_verified(label, current, outcomes)
    return outcomes


def _require_verified(label: str, index: Mapping[str, Any], outcomes: list[dict[str, Any]]) -> None:
    """Refuse startup when a ticket's container is not finally verified absent; outcomes stay journaled."""
    if cleanup_pending(index):
        cleanup = index.get("provider_container_cleanup") or {}
        raise StartupRefused(
            f"{label}: provider container {cleanup.get('container_name')!r} is not verified "
            f"absent ({cleanup.get('status')}: {cleanup.get('error')}); refusing to plan beside it",
            outcomes=outcomes, index=summary(index),
        )


def _record_reconciliation(manager: Checkouts, index: Mapping[str, Any],
                           reconciliation: Mapping[str, Any]) -> dict[str, Any]:
    with _exclusive_file_lock(manager.records / "checkouts.lock", timeout_seconds=10):
        current = read_index(manager, str(index["task_id"]))
        if current is None or current.get("job_id") != index.get("job_id"):
            raise BackgroundJobError("background job index changed during reconciliation")
        current["reconciliation"] = dict(reconciliation)
        write_record(index_path(manager, str(index["task_id"])), current)
        return current


def clear(manager: Checkouts, task_id: str, *, job_id: str, host: JobHost,
          clock: Callable[[], float] = time.monotonic,
          sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Archive one terminal index so the planner may launch a fresh ticket.

    Run roots and receipts are never deleted; only the index moves aside, and
    only once the ticket's exact provider container is finally verified
    absent: a pending cleanup is retried, an active tombstone (a late create
    could still land) refuses with the time to retry, and after the tombstone
    one exact look is recorded as the final recheck. Docker work never runs
    while ``checkouts.lock`` is held.
    """
    task_id = validate_task_id(task_id)
    with _exclusive_file_lock(manager.records / "checkouts.lock", timeout_seconds=10):
        index = read_index(manager, task_id)
        if index is None or index.get("job_id") != job_id:
            raise BackgroundJobError("exact background job index was not found")
        if index.get("status") in ACTIVE_STATUSES and observe(index, host).get("status") == "running":
            raise BackgroundJobError("background job is still running; it was not cleared")
    if index.get("status") in ACTIVE_STATUSES:
        raise BackgroundJobError("background job has not been harvested; it was not cleared")
    problems = _authentication_problems(manager, index)
    if problems:
        with _exclusive_file_lock(manager.records / "checkouts.lock", timeout_seconds=10):
            current = read_index(manager, task_id)
            if current is not None and current.get("job_id") == job_id:
                _refuse_authentication(manager, current, problems)
        raise BackgroundJobError(
            "background job clear refused: the ticket does not authenticate: "
            + "; ".join(problems) + "; the job was not cleared"
        )
    if cleanup_pending(index):
        index = settle_cleanup(manager, index, host, clock=clock, sleep=sleep, wait_for_tombstone=False)
        if cleanup_pending(index):
            cleanup = index.get("provider_container_cleanup") or {}
            name = (index.get("provider_container") or {}).get("name")
            if cleanup.get("authentication_failed"):
                raise BackgroundJobError(
                    f"provider container {name!r}: {cleanup.get('error')}; the job was not cleared"
                )
            if cleanup.get("status") == "verified_absent" and tombstone_active(index):
                raise BackgroundJobError(
                    f"provider container {name!r} is verified absent but a late create could still land "
                    f"until {cleanup.get('tombstone_until_utc')}; retry clear after that time"
                )
            raise BackgroundJobError(
                f"provider container {name!r} is not verified absent "
                f"({cleanup.get('status')}: {cleanup.get('error')}); the job was not cleared"
            )
    with _exclusive_file_lock(manager.records / "checkouts.lock", timeout_seconds=10):
        current = read_index(manager, task_id)
        if current is None or current.get("job_id") != job_id:
            raise BackgroundJobError("exact background job index was not found")
        if current.get("status") in ACTIVE_STATUSES or not cleanup_final(current):
            raise BackgroundJobError("background job index changed while it was being cleared")
        archived = index_path(manager, task_id).with_name(
            f"{task_id}.background-job.{job_id}.cleared.json"
        )
        write_record(archived, {**current, "cleared_at_utc": _now()})
        index_path(manager, task_id).unlink()
        return {"task_id": task_id, "job_id": job_id, "cleared": True, "archived": str(archived)}


# ---------------------------------------------------------------------------
# Child process


def _write_receipt(request: Mapping[str, Any], request_sha256: str, identity: Mapping[str, Any],
                   started_at: str, *, status: str, result: Any = None,
                   error: str | None = None) -> None:
    write_record(Path(str(request["receipt"])), {
        "schema_version": RECEIPT_SCHEMA, "job_id": request["job_id"],
        "kind": request["kind"], "task_id": request["task_id"],
        "request_sha256": request_sha256, "pid": os.getpid(),
        "process_identity": dict(identity), "started_at_utc": started_at,
        "completed_at_utc": _now(), "status": status, "result": result, "error": error,
    })


def _stop_requested(request: Mapping[str, Any], request_sha256: str,
                    identity: Mapping[str, Any]) -> bool:
    """True when an authenticated stop request names exactly this child; raises on a forgery."""
    path = Path(str(request.get("stop_request") or ""))
    payload = _read_object(path) if path.is_file() else None
    if payload is None:
        return False
    expected = {
        "schema_version": STOP_SCHEMA,
        "task_id": request.get("task_id"), "kind": request.get("kind"),
        "job_id": request.get("job_id"), "request_sha256": request_sha256,
        "pid": os.getpid(), "process_identity": dict(identity),
        "job_name": request.get("job_name"),
    }
    if any(payload.get(field) != value for field, value in expected.items()):
        raise BackgroundJobError("background job stop request is not bound to this child")
    return True


class _StopWatch:
    """Poll the bound stop request during work and run the kind's cooperative interrupt once."""

    def __init__(self, request: Mapping[str, Any], request_sha256: str,
                 identity: Mapping[str, Any], interrupt: Callable[[], None] | None):
        self._request = request
        self._request_sha256 = request_sha256
        self._identity = dict(identity)
        self._interrupt = interrupt
        self.requested = threading.Event()
        self.error: BaseException | None = None
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._run, name="assistant-job-stop-watch", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._closed.set()

    def _run(self) -> None:
        while not self._closed.wait(_STOP_POLL_SECONDS):
            try:
                requested = _stop_requested(self._request, self._request_sha256, self._identity)
            except BackgroundJobError as exc:
                # A stop request that does not bind to this child means the run
                # root can no longer be trusted: stop working, fail closed.
                self.error = exc
                requested = True
            if not requested:
                continue
            self.requested.set()
            if self._interrupt is not None:
                try:
                    self._interrupt()
                except Exception as exc:  # pragma: no cover - best effort
                    if self.error is None:
                        self.error = exc
            return


def _container_ownership_problem(request: Mapping[str, Any], observed: Mapping[str, Any],
                                 name: str, expected_labels: Mapping[str, str]) -> str | None:
    """Why a container found under the ticket's name is not this ticket's own."""
    project = str((request.get("provider_container") or {}).get("compose_project") or "")
    if observed.get("name") != name or observed.get("project") != project or (
            request.get("kind") == "decompose"
            and not str(observed.get("service") or "").endswith("-decompose")):
        return (f"container {name!r} carries other identity (project {observed.get('project')!r}, "
                f"service {observed.get('service')!r})")
    if (observed.get("job_label") != expected_labels[CONTAINER_JOB_LABEL]
            or observed.get("checkout_label") != expected_labels[CONTAINER_CHECKOUT_LABEL]):
        return (f"container {name!r} carries other identity (job label {observed.get('job_label')!r}, "
                f"checkout label {observed.get('checkout_label')!r})")
    if not str(observed.get("id") or ""):
        return f"container {name!r} has no id"
    return None


def _decide_cooperative_stop(request: Mapping[str, Any], docker: DockerRunner) -> dict[str, Any]:
    """Inspect the ticket's exact container name and decide whether it may be stopped."""
    decision: dict[str, Any] = {
        "schema_version": SCHEMA, "job_id": request.get("job_id"),
        "task_id": request.get("task_id"), "kind": request.get("kind"),
        "at_utc": _now(), "container_name": None, "expected_labels": None,
        "inspected": None, "decision": "refused", "reason": None,
        "stopped_id": None, "error": None,
    }
    try:
        name = _ticket_container_name(request)
        expected = _ticket_container_labels(request)
    except BackgroundJobError as exc:
        return {**decision, "reason": "ticket_does_not_authenticate", "error": str(exc)}
    decision.update(container_name=name, expected_labels=dict(expected))
    try:
        found = _inspect_container(docker, name)
    except BackgroundJobError as exc:
        return {**decision, "reason": "docker_cannot_answer", "error": str(exc)}
    if found is None:
        return {**decision, "decision": "absent", "reason": "no_such_container"}
    observed = {
        "id": found.get("id"), "name": str(found.get("name") or "").lstrip("/"),
        "project": found.get("project"), "service": str(found.get("service") or ""),
        "job_label": found.get("job") or None, "checkout_label": found.get("checkout") or None,
    }
    decision["inspected"] = observed
    problem = _container_ownership_problem(request, observed, name, expected)
    if problem is not None:
        return {**decision, "reason": "other_identity", "error": f"{problem}; not stopped"}
    container_id = str(observed["id"])
    # Only ever the exact id, never the name: the name alone proves nothing.
    code, _out, err = docker(["stop", "--time", "10", container_id])
    if code != 0:
        if "No such" in (err or "") or "no such" in (err or ""):
            # It went away between the inspect and the stop: nothing was stopped.
            return {**decision, "decision": "absent", "reason": "gone_before_stop"}
        return {**decision, "reason": "docker_stop_failed",
                "error": f"docker stop failed for {container_id[:12]}: {(err or '').strip()[:300]}"}
    return {**decision, "decision": "stopped", "reason": None, "stopped_id": container_id}


def cooperative_stop(request: Mapping[str, Any], *,
                     docker: DockerRunner | None = None) -> dict[str, Any]:
    """Cooperatively stop this ticket's own provider container, and only ever that one.

    A stop by name is destructive, so it is held to the same standard as a
    removal. The ticket is the source of truth (:func:`_ticket_container_name`
    and :func:`_ticket_container_labels`); its exact recorded name is inspected
    once with the reconciliation's own format; the container must be this
    ticket's own (exact name, compose project, a ``-decompose`` service for a
    decomposition, and both ownership labels equal to the ones the ticket
    records); and only then is it stopped **by its exact container id**, never
    by name, with the same ``docker stop --time 10`` semantics as before. A
    mismatch, a missing or unreadable label, an absent container, a Docker
    failure or a ticket that does not authenticate stops nothing.

    The decision is recorded durably as ``cooperative-stop.json`` in the run
    root and returned; it is never raised. A refused cooperative stop must not
    surface as the stop watch's error, which would turn the child's own
    ``stopped`` receipt into a failure.
    """
    runner = _run_docker if docker is None else docker
    try:
        decision = _decide_cooperative_stop(request, runner)
    except Exception as exc:  # the child's own stop path is never failed by this
        decision = {
            "schema_version": SCHEMA, "job_id": request.get("job_id"),
            "task_id": request.get("task_id"), "kind": request.get("kind"),
            "at_utc": _now(), "container_name": None, "expected_labels": None,
            "inspected": None, "decision": "refused", "reason": "unexpected_error",
            "stopped_id": None, "error": f"{type(exc).__name__}: {exc}",
        }
    try:
        write_record(Path(str(request.get("run_root"))) / "cooperative-stop.json", decision)
    except Exception as exc:  # a record that cannot be written never fails the stop
        decision["record_error"] = f"{type(exc).__name__}: {exc}"
    return decision


def _spawn_fixture_sleeper(run_root: Path) -> dict[str, Any]:
    """Test-only grandchild proving that a stop terminates the whole contained tree."""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    sleeper = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(300)"],
        cwd=str(run_root), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=creationflags,
    )
    return {"pid": sleeper.pid, "process_identity": _identity(sleeper.pid)}


def _ticket_container_name(request: Mapping[str, Any]) -> str:
    """The container name fixed in the ticket; fails closed if it is not the derived one."""
    container = request.get("provider_container")
    expected = container_name_for(str(request.get("job_id")))
    if not isinstance(container, Mapping) or container.get("name") != expected:
        raise BackgroundJobError("ticket provider container name is not derived from the ticket")
    identity = request.get("identity") or {}
    if request.get("kind") == "decompose" and container.get("compose_project") != identity.get("compose_project"):
        raise BackgroundJobError("ticket provider container compose project differs from the identity")
    _ticket_container_labels(request)
    return expected


def _ticket_container_labels(request: Mapping[str, Any]) -> dict[str, str]:
    """The job and checkout labels the child must put on its container."""
    container = request.get("provider_container")
    expected = container_labels_for(
        str(request.get("job_id")), request.get("source"), request.get("checkout_root"))
    if not isinstance(container, Mapping) or dict(container.get("labels") or {}) != expected:
        raise BackgroundJobError(
            "ticket provider container labels are not derived from the ticket and checkout")
    return expected


def _run_kind(manager: Checkouts, request: Mapping[str, Any], watch: _StopWatch) -> Any:
    kind = request["kind"]
    task_id = str(request["task_id"])
    identity = request.get("identity") or {}
    if kind == "fixture":
        run_root = Path(str(request["run_root"]))
        marker = run_root / "fixture.marker.json"
        sleeper = _spawn_fixture_sleeper(run_root) if identity.get("spawn_sleeper") is True else None
        write_record(marker, {"status": "fixture_started", "job_id": request["job_id"],
                              "pid": os.getpid(), "sleeper": sleeper})
        delay = float(identity.get("delay_seconds", 0.0))
        if delay < 0 or delay > 300:
            raise BackgroundJobError("fixture delay is outside the test-only bound")
        deadline = time.monotonic() + delay
        cooperative = identity.get("ignore_stop") is not True
        while time.monotonic() < deadline:
            if cooperative and watch.requested.is_set():
                return {"status": "fixture_stopped", "marker": str(marker), "sleeper": sleeper}
            time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
        return {"status": "fixture_completed", "marker": str(marker), "sleeper": sleeper}
    if kind == "decompose":
        if request.get("provider_spend_authorized") is not True:
            raise BackgroundJobError("decomposition ticket carries no provider-spend authorization")
        container_name = _ticket_container_name(request)
        head = git(manager.source, "rev-parse", "HEAD").decode().strip()
        if head != identity.get("source_commit"):
            raise BackgroundJobError("Source HEAD moved before the decomposition proposal started")
        _require_decompose_options(identity)
        from Pipeline.AssistantControl import decomposition
        return decomposition.run(
            manager, task_id, str(identity["run_id"]),
            providers=",".join(identity["providers"]),
            compose_project=str(identity["compose_project"]),
            execution_authorized=True,
            container_name=container_name,
            container_labels=_ticket_container_labels(request),
            max_calls=identity.get("max_calls", 2),
            author_checklist=identity.get("author_checklist"),
            bookkeeper_model=identity.get("bookkeeper_model"),
        )
    if kind == "post_crew":
        from Pipeline.AssistantControl.post_crew_workflow import run_post_crew_workflow
        record = json.loads((manager.records / f"{task_id}.json").read_text(encoding="utf-8"))
        candidate = record.get("candidate") or {}
        worker = record.get("worker") or record.get("launch") or {}
        expected_candidate = identity.get("candidate_commit")
        if expected_candidate is None:
            if candidate or worker.get("crew_run_id") != identity.get("crew_run_id"):
                raise BackgroundJobError("owned task record no longer matches the post-crew ticket")
        elif candidate.get("commit") != expected_candidate:
            raise BackgroundJobError("candidate changed before the post-crew ticket started")
        config = request.get("config")
        if not isinstance(config, Mapping):
            raise BackgroundJobError("post-crew ticket carries no bridge configuration")
        return run_post_crew_workflow(manager, task_id, str(identity["crew_run_id"]), config)
    raise BackgroundJobError(f"unsupported background job kind: {kind}")


def _interrupt_for(request: Mapping[str, Any]) -> Callable[[], None] | None:
    """The child's cooperative interrupt: verify ownership, then stop only its own container."""
    if request.get("kind") == "decompose":
        _ticket_container_name(request)  # fail closed before the child starts working
        return lambda: cooperative_stop(request)
    return None


def _child_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--job", required=True)
    args = parser.parse_args(argv)
    if not args.child:
        raise BackgroundJobError("child mode is internal")
    started_at = _now()
    request_bytes = args.request.read_bytes()
    request = json.loads(request_bytes)
    request_sha256 = hashlib.sha256(request_bytes).hexdigest()
    identity = _identity(os.getpid())
    job = None
    watch: _StopWatch | None = None
    try:
        expected_root = (args.checkout_root.resolve() / ".assistant-control" / "background-jobs"
                         / args.task / args.job)
        job_name = str(request.get("job_name") or "")
        if (request.get("schema_version") != SCHEMA or request.get("job_id") != args.job
                or request.get("task_id") != args.task
                or request.get("source") != str(args.source.resolve())
                or request.get("checkout_root") != str(args.checkout_root.resolve())
                or args.request.resolve() != expected_root / "launch.request.json"
                or Path(str(request.get("run_root"))).resolve() != expected_root
                or Path(str(request.get("receipt"))).resolve() != expected_root / "receipt.json"
                or Path(str(request.get("stop_request"))).resolve() != expected_root / "stop.request.json"
                or Path(str(request.get("job_opened"))).resolve() != expected_root / "job.opened.json"
                or job_name != job_name_for(expected_root)):
            raise BackgroundJobError("ticket identity differs from child arguments")
        write_record(expected_root / "child.identity.json", {
            "schema_version": SCHEMA, "job_id": args.job, "task_id": args.task,
            "request_sha256": request_sha256, "pid": os.getpid(), "process_identity": identity,
        })
        ready_path = expected_root / "ready.receipt.json"
        deadline = time.monotonic() + float(request.get("ready_timeout_seconds", _READY_TIMEOUT_SECONDS))
        ready = None
        while time.monotonic() < deadline:
            if ready_path.is_file():
                ready = json.loads(ready_path.read_text(encoding="utf-8"))
                break
            time.sleep(0.05)
        if ready is None:
            # Never run an operation the controller has not durably bound.
            return 2
        if (ready.get("job_id") != args.job or ready.get("request_sha256") != request_sha256
                or ready.get("child_identity") != identity
                or ready.get("parent_identity") != request.get("parent_identity")
                or ready.get("job_name") != job_name):
            raise BackgroundJobError("ready receipt is not bound to this child")
        from Pipeline.AssistantControl.windows_job import is_assigned, open_named
        if not is_assigned(job_name, identity):
            raise BackgroundJobError("background child is not contained by its recorded Job Object")
        # Hold the named job for the child's whole life so an operator can
        # reach the exact tree by name after the parent released its handle.
        job = open_named(job_name)
        write_record(expected_root / "job.opened.json", {
            "schema_version": SCHEMA, "job_id": args.job, "task_id": args.task,
            "job_name": job_name, "pid": os.getpid(), "process_identity": identity,
        })
        if _stop_requested(request, request_sha256, identity):
            _write_receipt(request, request_sha256, identity, started_at,
                           status="stopped", error="operator stopped background job before work")
            return 130
        manager = Checkouts(args.source, args.checkout_root)
        watch = _StopWatch(request, request_sha256, identity, _interrupt_for(request))
        watch.start()
        try:
            result = _run_kind(manager, request, watch)
        except Exception as exc:
            if watch.requested.is_set() and watch.error is None:
                _write_receipt(request, request_sha256, identity, started_at, status="stopped",
                               error=f"operator stopped background job during work: {type(exc).__name__}: {exc}")
                return 130
            raise
        finally:
            watch.close()
        if watch.error is not None:
            raise watch.error
        if watch.requested.is_set() or _stop_requested(request, request_sha256, identity):
            _write_receipt(request, request_sha256, identity, started_at, status="stopped",
                           error="operator stopped background job",
                           result=_json_copy(result, "background job result"))
            return 130
        _write_receipt(request, request_sha256, identity, started_at,
                       status="succeeded", result=_json_copy(result, "background job result"))
        return 0
    except Exception as exc:
        try:
            _write_receipt(request, request_sha256, identity, started_at,
                           status="failed", error=f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
        return 1
    finally:
        if watch is not None:
            watch.close()
        if job is not None:
            job.close()


def main() -> int:
    return _child_main(sys.argv[1:]) if "--child" in sys.argv[1:] else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ACTIVE_STATUSES", "BackgroundJobError", "CONTAINER_CHECKOUT_LABEL", "CONTAINER_JOB_LABEL",
    "CONTAINER_SETTLE_SECONDS",
    "CONTAINER_TOMBSTONE_SECONDS", "CONTAINER_WINDOW_SECONDS", "ContainerReconcileError",
    "DetachedHost", "JOB_KINDS",
    "JobHost", "SCHEMA", "STOP_GRACE_SECONDS", "STOP_SCHEMA", "StartupRefused",
    "TERMINAL_STATUSES", "authenticate_index", "cancel", "cancel_all", "checkout_digest_for",
    "cleanup_final",
    "cleanup_owner_alive", "cleanup_pending", "cleanup_retry_due", "clear", "container_labels_for",
    "container_name_for", "cooperative_stop",
    "harvest", "index_path", "job_id_for", "job_name_for", "launch", "list_indexes", "observe",
    "read_index", "reconcile_provider_container", "reconcile_startup", "request_stop",
    "scan_indexes", "settle_cleanup", "stop_complete", "stop_payload", "summary",
    "tombstone_active", "unreadable_indexes",
]
