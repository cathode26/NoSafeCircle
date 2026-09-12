"""Detached, readiness-gated launcher for one assistant worker run.

The parent owns the launch request and readiness receipt. The child cannot
invoke the real worker until both are durable and bound to its exact process
identity. The test-only fixture mode is deliberately explicit and never calls
the provider worker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from collections.abc import Mapping
from typing import Any

from Pipeline.AssistantControl.admission import (
    _read_registry,
    _source_registry_paths,
    require_reservation,
)
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.process_identity import identify
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
from Pipeline.TaskReviewAgent.contracts import validate_task_id


class WorkerLauncherError(ValueError):
    """A detached worker launch could not be safely established."""


def _run_root(checkouts: Checkouts, task_id: str, run_id: str) -> Path:
    return (checkouts.records / "worker-runs" / task_id /
            hashlib.sha256(run_id.encode("utf-8")).hexdigest())


def _json_config(config: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(json.dumps(dict(config), ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise WorkerLauncherError("launcher config must be JSON-serializable") from exc
    if not isinstance(value, dict):
        raise WorkerLauncherError("launcher config must be an object")
    return value


def _identity(pid: int) -> dict[str, Any]:
    try:
        value = identify(pid)
    except (NotImplementedError, OSError, ValueError) as exc:
        raise WorkerLauncherError("detached launcher requires supported exact process identity") from exc
    if not isinstance(value, dict):
        raise WorkerLauncherError("detached launcher could not establish process identity")
    return value


def _write_status(run_root: Path, status: str, **fields: Any) -> None:
    write_record(run_root / "launcher.status.json", {"status": status, **fields})


def _owned_path(value: str, expected: Path, label: str) -> Path:
    path = Path(value).resolve()
    if path != expected.resolve():
        raise WorkerLauncherError(f"{label} is outside its owned hashed run path")
    return path


def _verify_reservation_under_checkout_lock(
    checkouts: Checkouts, task_id: str, run_id: str, lease_id: str,
    reservation: Mapping[str, Any],
) -> None:
    """Recheck the exact admission while the checkout transaction is held."""
    lock_path, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(lock_path, timeout_seconds=10):
        registry = _read_registry(registry_path, checkouts.source)
        matches = [item for item in registry["reservations"]
                   if item.get("task_id") == task_id
                   and item.get("run_id") == run_id
                   and item.get("lease_id") == lease_id
                   and item.get("checkout_root") == str(checkouts.root)]
        if (len(matches) != 1
                or any(matches[0].get(key) != value
                       for key, value in reservation.items()
                       if key not in {"admitted", "execution_authorized"})):
            raise WorkerLauncherError("launch reservation changed before spawn")


def _archive_previous_attempt(record: dict[str, Any], *, task_id: str,
                              run_id: str) -> None:
    worker = record.get("worker")
    launch = record.get("launch")
    active = worker if isinstance(worker, dict) else launch
    if not isinstance(active, dict):
        return
    old_run = active.get("run_id")
    if old_run == run_id:
        raise WorkerLauncherError("same-run worker replacement refused")
    settled_spawn_failure = (
        active.get("status") == "spawn_failed"
        and (
            active.get("no_child_created") is True
            or (active.get("no_child_created") is False
                and active.get("child_exit_confirmed") is True
                and active.get("before_ready") is True)
        )
    )
    if active.get("status") not in {"failed", "stopped"} and not settled_spawn_failure:
        raise WorkerLauncherError("live, unsettled, or succeeded worker replacement refused")
    if active.get("capacity_released") is not True:
        raise WorkerLauncherError("worker replacement requires released capacity")
    history = record.get("worker_history", [])
    if not isinstance(history, list):
        raise WorkerLauncherError("owned worker history is malformed")
    # Entries are copies of the prior fields. Existing entries are never
    # rewritten, so control tools retain an immutable audit trail of attempts.
    history.append({
        "schema_version": "assistant-worker-history/v1",
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "run_id": old_run,
        "worker": json.loads(json.dumps(worker)) if isinstance(worker, dict) else None,
        "launch": json.loads(json.dumps(launch)) if isinstance(launch, dict) else None,
    })
    record["worker_history"] = history
    record.pop("worker", None)
    record.pop("launch", None)


def start(
    checkouts: Checkouts,
    task_id: str,
    run_id: str,
    lease_id: str,
    config: Mapping[str, Any],
    execution_authorized: bool = False,
) -> dict[str, Any]:
    """Start one readiness-gated detached worker; never launch without explicit authorization."""
    task_id = validate_task_id(task_id)
    if type(run_id) is not str or not run_id.strip() or type(lease_id) is not str or not lease_id.strip():
        raise WorkerLauncherError("launcher requires exact run_id and lease_id")
    if execution_authorized is not True:
        raise WorkerLauncherError("detached worker launch requires execution_authorized=true")
    saved = _json_config(config)
    saved["execution_authorized"] = True
    reservation = require_reservation(checkouts, task_id, run_id, lease_id)
    run_root = _run_root(checkouts, task_id, run_id)
    request_path = run_root / "launch.request.json"
    ready_path = run_root / "ready.receipt.json"
    stdout_path = run_root / "stdout.log"
    stderr_path = run_root / "stderr.log"
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        if request_path.exists():
            raise WorkerLauncherError("duplicate worker launch refused for this run")
        record_path = checkouts.records / f"{task_id}.json"
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise WorkerLauncherError("owned task checkout record is unreadable") from exc
        if (record.get("checkout") != reservation.get("checkout")
                or record.get("source") != reservation.get("source")):
            raise WorkerLauncherError("launch reservation differs from owned task record")
        _verify_reservation_under_checkout_lock(
            checkouts, task_id, run_id, lease_id, reservation)
        _archive_previous_attempt(record, task_id=task_id, run_id=run_id)
        run_root.mkdir(parents=True, exist_ok=True)
        if saved.get("_test_fixture") is not None:
            raise WorkerLauncherError("fixture config is not accepted by the production launcher")
        parent_identity = _identity(os.getpid())
        config_path = run_root / "launch.config.json"
        write_record(config_path, saved)
        config_sha256 = hashlib.sha256(config_path.read_bytes()).hexdigest()
        stop_path = run_root / "stop.request"
        job_name = "assistant-job-" + hashlib.sha256(str(run_root).encode()).hexdigest()
        request = {
            "schema_version": "assistant-worker-launch/v1", "task_id": task_id,
            "run_id": run_id, "lease_id": lease_id, "checkout_root": str(checkouts.root),
            "checkout": reservation["checkout"], "source": reservation["source"],
            "reservation_plan_id": reservation["plan_id"], "config_sha256": config_sha256,
            "job_name": job_name,
            "parent_identity": parent_identity, "config": str(config_path),
            "ready": str(ready_path), "stop_request": str(stop_path), "created_by_pid": os.getpid(),
            "job_opened": str(run_root / "job.opened.json"),
            "ready_timeout_seconds": float(saved.get("ready_timeout_seconds", 10)),
            "test_fixture": saved.get("_test_fixture"),
        }
        if request["ready_timeout_seconds"] <= 0 or request["ready_timeout_seconds"] > 300:
            raise WorkerLauncherError("ready_timeout_seconds must be between 0 and 300")
        write_record(request_path, request)
        record["launch"] = {
            "status": "starting", "task_id": task_id, "run_id": run_id,
            "lease_id": lease_id, "stop_request_path": str(stop_path), "job_name": job_name,
        }
        write_record(record_path, record)
        control_source = Path(__file__).resolve().parents[2]
        args = [sys.executable, "-m", "Pipeline.AssistantControl.worker_launcher", "--child",
                "--request", str(request_path), "--source", str(checkouts.source),
                "--checkout-root", str(checkouts.root), "--task", task_id,
                "--run", run_id, "--lease", lease_id]
        if saved.get("_test_fixture") is not None:
            args.append("--fixture")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        try:
            with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
                child = subprocess.Popen(
                    args, cwd=str(control_source), stdin=subprocess.DEVNULL,
                    stdout=stdout, stderr=stderr, shell=False,
                    creationflags=creationflags, startupinfo=startupinfo,
                )
        except (OSError, ValueError) as exc:
            record["launch"].update({
                "status": "spawn_failed", "no_child_created": True,
                "error": str(exc),
            })
            write_record(record_path, record)
            _write_status(run_root, "spawn_failed", error=str(exc),
                          no_child_created=True, run_id=run_id)
            raise WorkerLauncherError("detached worker process could not be spawned") from exc
        threading.Thread(target=child.wait, name="assistant-worker-reaper", daemon=True).start()
        try:
            child_identity = _identity(child.pid)
        except WorkerLauncherError as exc:
            # Popen succeeded, so this is never a no-child outcome. Cleanup
            # uses the retained handle and records proof only after wait().
            child_exit_confirmed = False
            try:
                child.terminate()
                child.wait(timeout=10)
                child_exit_confirmed = True
            except (OSError, subprocess.TimeoutExpired, ValueError):
                try:
                    child.kill()
                    child.wait(timeout=10)
                    child_exit_confirmed = True
                except (OSError, subprocess.TimeoutExpired, ValueError):
                    pass
            record["launch"].update({
                "status": "spawn_failed", "no_child_created": False,
                "child_exit_confirmed": child_exit_confirmed, "before_ready": True,
                "error": str(exc),
            })
            write_record(record_path, record)
            _write_status(run_root, "spawn_failed", error=str(exc),
                          no_child_created=False,
                          child_exit_confirmed=child_exit_confirmed,
                          run_id=run_id)
            raise
        write_record(run_root / "launcher.identity.json", {
            "pid": child.pid, "process_identity": child_identity,
            "parent_identity": parent_identity, "run_id": run_id,
        })
        record["launch"].update({"pid": child.pid, "process_identity": child_identity,
                                 "status": "ready_pending"})
        write_record(record_path, record)
        ready = {
            "schema_version": "assistant-worker-ready/v1", "task_id": task_id,
            "run_id": run_id, "lease_id": lease_id, "request": str(request_path),
            "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
            "parent_identity": parent_identity, "child_identity": child_identity,
            "pid": child.pid,
        }
        from Pipeline.AssistantControl.windows_job import create_and_assign
        # The child is still waiting: contain all future host descendants before
        # publishing permission to enter the provider bridge.
        with create_and_assign(job_name, child_identity):
            write_record(ready_path, ready)
            deadline = time.monotonic() + float(request["ready_timeout_seconds"])
            opened_path = run_root / "job.opened.json"
            while not opened_path.is_file() and time.monotonic() < deadline:
                if child.poll() is not None:
                    raise WorkerLauncherError("contained child exited before Job Object handoff")
                time.sleep(0.05)
            if not opened_path.is_file():
                raise WorkerLauncherError("contained child did not acknowledge Job Object handoff")
            try:
                opened = json.loads(opened_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise WorkerLauncherError("Job Object handoff receipt is unreadable") from exc
            if opened.get("run_id") != run_id or opened.get("child_identity") != child_identity:
                raise WorkerLauncherError("Job Object handoff receipt is not bound to the child")
        return {
            "started": True, "task_id": task_id, "run_id": run_id,
            "lease_id": lease_id, "pid": child.pid, "process_identity": child_identity,
            "run_root": str(run_root), "request": str(request_path),
            "ready_receipt": str(ready_path), "stdout": str(stdout_path),
            "stderr": str(stderr_path), "execution_authorized": True,
        }


def _child_fixture(request: Mapping[str, Any], run_root: Path) -> None:
    fixture = request.get("test_fixture")
    if not isinstance(fixture, Mapping) or type(fixture.get("marker")) is not str:
        raise WorkerLauncherError("fixture child requires a labeled marker path")
    marker = Path(fixture["marker"]).resolve()
    if not marker.is_relative_to(run_root.resolve()):
        raise WorkerLauncherError("fixture marker must remain inside the owned run root")
    write_record(marker, {"status": "fixture_started", "run_id": request["run_id"],
                          "pid": os.getpid(), "run_root": str(run_root)})
    _write_status(run_root, "fixture_completed", pid=os.getpid(), run_id=request["run_id"])


def _child_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--lease", required=True)
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args(argv)
    if not args.child:
        raise WorkerLauncherError("child mode is internal")
    job = None
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        if (request.get("task_id") != args.task or request.get("run_id") != args.run
                or request.get("lease_id") != args.lease):
            raise WorkerLauncherError("launch request identity differs from child arguments")
        expected_root = (args.checkout_root.resolve() / ".assistant-control" / "worker-runs"
                         / args.task / hashlib.sha256(args.run.encode("utf-8")).hexdigest())
        _owned_path(str(args.request), expected_root / "launch.request.json", "launch request")
        config_path = _owned_path(str(request["config"]), expected_root / "launch.config.json", "launch config")
        ready_path = _owned_path(str(request["ready"]), expected_root / "ready.receipt.json", "ready receipt")
        _owned_path(str(request["stop_request"]), expected_root / "stop.request", "stop request")
        if (request.get("source") != str(args.source.resolve())
                or request.get("checkout_root") != str(args.checkout_root.resolve())):
            raise WorkerLauncherError("launch request repository arguments differ")
        if request.get("checkout") != str(args.checkout_root.resolve() / args.task):
            raise WorkerLauncherError("launch request checkout differs from child arguments")
        child_identity = _identity(os.getpid())
        request_sha256 = hashlib.sha256(args.request.read_bytes()).hexdigest()
        write_record(expected_root / "child.identity.json", {
            "schema_version": "assistant-worker-child-identity/v1",
            "task_id": args.task, "run_id": args.run, "lease_id": args.lease,
            "request": str(args.request), "request_sha256": request_sha256,
            "pid": os.getpid(), "process_identity": child_identity,
        })
        deadline = time.monotonic() + float(request["ready_timeout_seconds"])
        ready = None
        while time.monotonic() < deadline:
            run_root = args.request.parent
            stop_path = run_root / "stop.request"
            if stop_path.is_file():
                _write_status(run_root, "stopped_before_worker", pid=os.getpid(), run_id=args.run)
                return 0
            if ready_path.is_file():
                ready = json.loads(ready_path.read_text(encoding="utf-8"))
                break
            time.sleep(0.05)
        if ready is None:
            _write_status(args.request.parent, "ready_timeout", pid=os.getpid(), run_id=args.run)
            return 2
        expected_hash = request_sha256
        config_bytes = config_path.read_bytes()
        if hashlib.sha256(config_bytes).hexdigest() != request.get("config_sha256"):
            raise WorkerLauncherError("launch config bytes do not match the request hash")
        if (ready.get("request") != str(args.request)
                or ready.get("request_sha256") != expected_hash
                or ready.get("child_identity") != child_identity
                or ready.get("run_id") != args.run or ready.get("task_id") != args.task
                or ready.get("lease_id") != args.lease
                or ready.get("parent_identity") != request.get("parent_identity")):
            raise WorkerLauncherError("ready receipt is not bound to this launch process")
        if request.get("job_name"):
            from Pipeline.AssistantControl.windows_job import open_named
            job = open_named(request["job_name"])
            write_record(args.request.parent / "job.opened.json", {
                "schema_version": "assistant-worker-job-opened/v1",
                "run_id": args.run, "task_id": args.task, "child_identity": child_identity,
            })
        checkouts = Checkouts(args.source, args.checkout_root)
        reservation = require_reservation(checkouts, args.task, args.run, args.lease)
        config = json.loads(config_bytes.decode("utf-8"))
        if args.fixture:
            _child_fixture(request, args.request.parent)
            return 0
        from Pipeline.AssistantControl.crew_worker import run_worker
        result = run_worker(checkouts, args.task, reservation, config)
        status = ((result.get("worker") or {}).get("status")
                  if isinstance(result, Mapping) else None)
        return 0 if status == "succeeded" else 2 if status == "stopped" else 1
    except Exception as exc:
        _write_status(args.request.parent, "child_failed", pid=os.getpid(), error=str(exc))
        return 1
    finally:
        if job is not None:
            job.close()


def main() -> int:
    return _child_main(sys.argv[1:]) if "--child" in sys.argv[1:] else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["WorkerLauncherError", "start"]
