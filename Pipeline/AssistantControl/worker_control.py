"""Inspect or cooperatively stop one exact assistant worker; never pick newest."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.process_identity import matches, terminate
from Pipeline.AssistantControl.docker_workers import stop_containers
from Pipeline.AssistantControl.windows_job import active_count, terminate_job
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


_POST_EXIT_IDENTITY_FIELDS = (
    "task_id",
    "run_id",
    "process_identity",
    "lease_id",
    "plan_id",
    "source_head",
    "task_contract_sha256",
    "stop_request_path",
    "job_name",
)


def _worker(checkouts: Checkouts, task_id: str) -> dict:
    validate_task_id(task_id)
    record = checkouts.observe(task_id)
    worker = record.get("worker") or record.get("launch")
    if not isinstance(worker, dict) or worker.get("task_id") != task_id:
        raise ValueError("Task has no identified assistant worker")
    run_id = worker.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Worker run identity is missing")
    expected = (checkouts.records / "worker-runs" / task_id /
                hashlib.sha256(run_id.encode()).hexdigest() / "stop.request")
    if Path(worker.get("stop_request_path", "")).resolve() != expected.resolve():
        raise ValueError("Worker stop path differs from its owned run")
    # Resolve junctions as well as lexical components before any write.
    if not expected.resolve().is_relative_to(checkouts.records.resolve()):
        raise ValueError("Worker stop path escapes its record directory")
    if worker.get("job_name") and worker["job_name"] != "assistant-job-" + hashlib.sha256(str(expected.parent).encode()).hexdigest():
        raise ValueError("Worker job identity differs from its owned run")
    if not record.get("worker") and not worker.get("process_identity"):
        handshake = expected.parent / "child.identity.json"
        if handshake.is_file():
            proof = json.loads(handshake.read_text(encoding="utf-8"))
            request_bytes = (expected.parent / "launch.request.json").read_bytes()
            request = json.loads(request_bytes)
            fields = {"task_id": task_id, "run_id": run_id, "lease_id": worker.get("lease_id")}
            if (any(proof.get(key) != value or request.get(key) != value for key, value in fields.items())
                    or proof.get("request_sha256") != hashlib.sha256(request_bytes).hexdigest()
                    or request.get("source") != str(checkouts.source)
                    or request.get("checkout_root") != str(checkouts.root)
                    or request.get("checkout") != record["checkout"]
                    or not isinstance(proof.get("process_identity"), dict)):
                raise ValueError("Child identity handshake differs from owned launch")
            worker = {**worker, "process_identity": proof["process_identity"]}
    return worker


def _require_same_post_exit_attempt(original: dict, refreshed: dict) -> None:
    if any(field not in original or original.get(field) is None or original.get(field) == ""
           for field in _POST_EXIT_IDENTITY_FIELDS):
        raise ValueError("Running worker identity is incomplete; exact run retained for inspection")
    if any(refreshed.get(field) != original.get(field)
           for field in _POST_EXIT_IDENTITY_FIELDS):
        raise ValueError("Worker identity changed after host exit; exact run retained for inspection")


def status(checkouts: Checkouts, task_id: str) -> dict:
    worker = _worker(checkouts, task_id)
    identity = worker.get("process_identity")
    try:
        alive = matches(identity) if identity else None
        error = None
    except (OSError, ValueError, NotImplementedError) as exc:
        alive, error = None, str(exc)
    if alive is False and worker.get("status") == "running":
        # The child writes its terminal record before exiting.  The first
        # observation can read ``running`` immediately before that atomic
        # replacement, then observe the process after it exits.  Re-read once
        # behind the confirmed exit and accept only the same owned attempt.
        refreshed = _worker(checkouts, task_id)
        _require_same_post_exit_attempt(worker, refreshed)
        worker = refreshed
        if worker.get("status") == "succeeded":
            from Pipeline.AssistantControl.result_inspection import inspect_result
            inspect_result(checkouts, task_id, assistant_run_id=worker["run_id"])
    return {"task_id": task_id, "worker": worker,
            "host_identity_alive": alive, "identity_error": error,
            "stop_requested": Path(worker["stop_request_path"]).is_file(),
            "capacity_released": worker.get("capacity_released") is True,
            "limitation": "Host process identity does not prove Docker children have exited."}


def request_stop(checkouts: Checkouts, task_id: str, *, run_id: str) -> dict:
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        worker = _worker(checkouts, task_id)
        if run_id != worker["run_id"]:
            raise ValueError("Requested run differs from task worker; no stop sent")
        if worker.get("status") in {"succeeded", "failed", "stopped"}:
            return {"task_id": task_id, "run_id": run_id, "stop_requested": False,
                    "host_worker_terminal": True, "capacity_released": False}
        path = Path(worker["stop_request_path"])
        identity = {"task_id": task_id, "run_id": run_id, "lease_id": worker.get("lease_id")}
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8"))
            if any(previous.get(key) != value for key, value in identity.items()):
                raise ValueError("Existing stop request has a different identity")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_record(path, {**identity, "requested_at": datetime.now(timezone.utc).isoformat()})
        return {**identity, "stop_requested": True, "stop_request_path": str(path),
                "capacity_released": False, "host_worker_terminal": False}


def force_stop(checkouts: Checkouts, task_id: str, *, run_id: str) -> dict:
    request_stop(checkouts, task_id, run_id=run_id)
    worker = _worker(checkouts, task_id)
    if worker.get("run_id") != run_id or not worker.get("process_identity"):
        raise ValueError("Exact host identity unavailable; stop request retained")
    # An exited/recycled host needs no termination. Its owned containers may
    # still need cleanup even when the host already wrote a terminal record.
    job_name = worker.get("job_name")
    if job_name:
        terminate_job(job_name)
    if matches(worker["process_identity"]):
        terminate(worker["process_identity"])
    tree_exited = bool(job_name) and active_count(job_name) == 0
    project = "assistant-crew-" + hashlib.sha256(run_id.encode()).hexdigest()[:20]
    docker_worker = {"compose_project": project, **worker}
    cleanup = stop_containers(checkouts.root / task_id, docker_worker)
    if cleanup.get("containers_stopped") is not True:
        raise RuntimeError("Host exited but run containers are still active; stop is not complete")
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        path = checkouts.records / f"{task_id}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        field = "worker" if record.get("worker") else "launch"
        current = record.get(field) or {}
        if current.get("run_id") != run_id or _worker(checkouts, task_id).get("process_identity") != worker["process_identity"]:
            raise ValueError("Task worker changed during stop; retained state requires inspection")
        current["process_identity"] = worker["process_identity"]
        current.update({"status": "stopped", "finished_at": datetime.now(timezone.utc).isoformat(),
                        "host_exit_confirmed": True, "host_tree_exit_confirmed": tree_exited,
                        "docker_cleanup": cleanup})
        write_record(path, record)
    return {"task_id": task_id, "run_id": run_id, **cleanup, "host_exit_confirmed": True,
            "host_tree_exit_confirmed": tree_exited,
            "capacity_released": False}
