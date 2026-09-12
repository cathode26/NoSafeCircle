"""Release completed crew capacity only after host and container exit checks."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.docker_workers import inventory, remove_unused_project_resources
from Pipeline.AssistantControl.process_identity import matches
from Pipeline.AssistantControl.worker_control import _worker
from Pipeline.AssistantControl.windows_job import active_count
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


def settle_completed(checkouts: Checkouts, task_id: str, *, run_id: str) -> dict:
    """Release only after completed receipt proof or an exited contained tree."""
    validate_task_id(task_id)
    lock, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        record = checkouts.observe(task_id)
        worker = _worker(checkouts, task_id)
        if worker.get("run_id") != run_id:
            raise ValueError("Only the exact crew run can use this settlement")
        no_child = (not record.get("worker") and worker.get("status") == "spawn_failed"
                    and worker.get("no_child_created") is True
                    and not worker.get("process_identity")
                    and not (Path(worker["stop_request_path"]).parent / "ready.receipt.json").exists())
        pre_ready_exit = (not record.get("worker") and worker.get("status") == "spawn_failed"
                          and worker.get("no_child_created") is False
                          and worker.get("child_exit_confirmed") is True
                          and worker.get("before_ready") is True
                          and not worker.get("process_identity")
                          and not (Path(worker["stop_request_path"]).parent / "ready.receipt.json").exists())
        if not (no_child or pre_ready_exit) and (not worker.get("process_identity") or matches(worker["process_identity"])):
            raise ValueError("Worker host exit is not confirmed")
        completed = worker.get("status") == "succeeded"
        if worker.get("job_name"):
            if active_count(worker["job_name"]) != 0:
                raise ValueError("Worker tree exit is not confirmed")
        elif not completed and not (no_child or pre_ready_exit):
            raise ValueError("Failed or stopped worker tree exit is not confirmed")
        receipt = worker.get("receipt") or {}
        if (worker.get("status") == "succeeded"
                and receipt.get("crew_status") is not None
                and receipt.get("crew_status") not in {"review_ready", "materialization_required"}):
            # Older workers recorded the host invocation as succeeded even
            # when the verified crew result was rejected. Preserve that real
            # receipt, but settle the host result as failed.
            worker["status"] = "failed"
            worker["settlement_reason"] = "ExecutionCrew receipt was rejected"
            record["worker"] = worker
        scope = record.get("scope") or {}
        expected = {"task_id": task_id, "lease_id": scope.get("lease_id"),
                    "plan_id": scope.get("plan_id"), "source_head": record["source_commit"],
                    "task_contract_sha256": record["task_contract_sha256"]}
        binding = worker if record.get("worker") else {**expected, **worker}
        if any(not value or binding.get(key) != value for key, value in expected.items()):
            raise ValueError("Completed receipt identity differs from the owned task")
        if completed:
            if any(receipt.get(key) != value for key, value in expected.items()):
                raise ValueError("Completed receipt identity differs from the owned task")
            if not worker.get("crew_run_id") or receipt.get("run_id") != worker["crew_run_id"]:
                raise ValueError("Crew result identity is missing or changed")
            output_root = (Path(record["checkout"]) / "Pipeline/ExecutionCrew/outputs").resolve()
            for file_key, hash_key in (("result_path", "result_sha256"), ("candidate_path", "candidate_sha256")):
                if file_key == "result_path" and (receipt.get(file_key) is None or receipt.get(hash_key) is None):
                    raise ValueError("Crew result artifact is required")
                if (file_key == "candidate_path" and receipt.get(file_key) is None
                        and receipt.get(hash_key) is None
                        and receipt.get("crew_status") not in {"review_ready", "materialization_required"}):
                    continue
                if (receipt.get(file_key) is None) != (receipt.get(hash_key) is None):
                    raise ValueError("Crew artifact path and hash must be provided together")
                artifact = Path(receipt.get(file_key) or "").resolve()
                if not artifact.is_relative_to(output_root):
                    raise ValueError("Crew artifact is outside its owned output directory")
                if hashlib.sha256(artifact.read_bytes()).hexdigest() != receipt.get(hash_key):
                    raise ValueError("Crew artifact changed after worker completion")
        docker_worker = {"compose_project": "assistant-crew-" + hashlib.sha256(run_id.encode()).hexdigest()[:20], **worker}
        try:
            if any(item["running"] for item in inventory(Path(record["checkout"]), docker_worker)):
                raise ValueError("Run containers have not exited")
        except RuntimeError:
            # The host/tree proof above is authoritative; Docker cleanup is
            # retried later if the daemon is unavailable at this point.
            pass
        try:
            remove_unused_project_resources(Path(record["checkout"]), docker_worker)
        except RuntimeError:
            # Do not turn a completed worker into a failed result because
            # cleanup raced with Docker or the daemon temporarily disappeared.
            pass
        with _exclusive_file_lock(lock, timeout_seconds=10):
            registry = _read_registry(registry_path, checkouts.source)
            owned = [item for item in registry["reservations"] if item.get("task_id") == task_id]
            if owned:
                if len(owned) != 1 or any(owned[0].get(key) != value for key, value in {
                    "run_id": run_id, "lease_id": worker["lease_id"],
                    "checkout_root": str(checkouts.root), "checkout": record["checkout"],
                }.items()):
                    raise ValueError("A different admission owns this task; no release")
                registry["reservations"].remove(owned[0])
                write_record(registry_path, registry)
            # A crash after registry settlement is recoverable without removing
            # another task or requiring a second provider invocation.
            path = checkouts.records / f"{task_id}.json"
            persisted = json.loads(path.read_text(encoding="utf-8"))
            field = "worker" if persisted.get("worker") else "launch"
            persisted_crew_status = (persisted[field].get("receipt") or {}).get("crew_status")
            if (field == "worker" and persisted[field].get("status") == "succeeded"
                    and persisted_crew_status is not None
                    and persisted_crew_status not in {"review_ready", "materialization_required"}):
                persisted[field]["status"] = "failed"
                persisted[field]["settlement_reason"] = "ExecutionCrew receipt was rejected"
            if persisted[field].get("status") not in {"succeeded", "failed", "stopped", "spawn_failed"}:
                persisted[field]["status"] = "stopped" if Path(worker["stop_request_path"]).is_file() else "failed"
                persisted[field]["settlement_reason"] = "Exited without a completed worker result"
            persisted[field]["capacity_released"] = True
            persisted[field].setdefault("settled_at", datetime.now(timezone.utc).isoformat())
            write_record(path, persisted)
        return {"task_id": task_id, "run_id": run_id, "capacity_released": True,
                "approval_granted": False, "integration_performed": False}
