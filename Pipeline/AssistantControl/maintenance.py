"""Small, authenticated maintenance tickets for already-created workers."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.process_identity import matches
from Pipeline.AssistantControl.worker_control import _worker, status
from Pipeline.AssistantControl.worker_settlement import settle_completed
from Pipeline.AssistantControl.result_inspection import inspect_result
from Pipeline.AssistantControl.docker_workers import remove_unused_project_resources
from Pipeline.AssistantControl.windows_job import active_count
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id

_ACTIONS = {"inspect-worker", "verify-candidate", "settle-worker", "cleanup-worker-docker"}
_SCHEMA = "assistant-maintenance-ticket/v1"
_RECEIPT_SCHEMA = "assistant-maintenance-receipt/v1"
_TICKET_KEYS = {
    "schema_version", "action", "task_id", "source", "source_head", "checkout_root", "checkout",
    "branch", "checkout_commit", "task_contract_sha256", "assistant_run_id", "worker",
    "issued_at_utc", "semantic_sha256",
}
_RECEIPT_KEYS = {"schema_version", "ticket_sha256", "action", "task_id", "assistant_run_id",
                 "completed_at_utc", "result", "semantic_sha256"}
_WORKER_KEYS = ("task_id", "run_id", "lease_id", "plan_id", "source_head",
                "task_contract_sha256", "process_identity", "stop_request_path",
                "job_name", "status")


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _ticket_sha(body: dict[str, Any]) -> str:
    return _sha({key: value for key, value in body.items() if key != "semantic_sha256"})


def _receipt_sha(body: dict[str, Any]) -> str:
    return _sha({key: value for key, value in body.items() if key != "semantic_sha256"})


def _owned(path: Path, root: Path) -> Path:
    root = root.resolve()
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError("Maintenance ticket must be a regular file inside the owned ticket directory")
    return path.resolve()


@dataclass(frozen=True)
class MaintenanceTicket:
    body: dict[str, Any]

    @property
    def action(self) -> str: return str(self.body["action"])

    @property
    def task_id(self) -> str: return str(self.body["task_id"])

    @classmethod
    def read(cls, path: Path, tickets_root: Path) -> "MaintenanceTicket":
        path = _owned(path, tickets_root)
        body = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(body, dict) or body.get("schema_version") != _SCHEMA:
            raise ValueError("Maintenance ticket schema is invalid")
        if (body.get("action") not in _ACTIONS
                or set(body) != _TICKET_KEYS
                or body.get("semantic_sha256") != _ticket_sha(body)):
            raise ValueError("Maintenance ticket authentication failed")
        return cls(body)


class MaintenanceExecutor:
    def __init__(self, checkouts: Checkouts):
        self.checkouts = checkouts
        self.tickets = checkouts.records / "maintenance-tickets"
        self.receipts = checkouts.records / "maintenance-receipts"

    def plan(self, task_id: str, action: str, *, run_id: str) -> dict[str, Any]:
        task_id = validate_task_id(task_id)
        if action not in _ACTIONS:
            raise ValueError("Unknown maintenance action")
        record = self.checkouts.observe(task_id)
        worker = _worker(self.checkouts, task_id)
        if worker.get("run_id") != run_id or worker.get("task_id") != task_id:
            raise ValueError("Worker run identity differs from the requested ticket")
        required = ("task_id", "run_id", "lease_id", "plan_id", "source_head",
                    "task_contract_sha256", "process_identity", "stop_request_path", "status")
        if any(worker.get(key) in (None, "") for key in required) or not isinstance(worker.get("process_identity"), dict):
            raise ValueError("Worker identity is incomplete")
        if (worker.get("source_head") != record.get("source_commit")
                or worker.get("task_contract_sha256") != record.get("task_contract_sha256")):
            raise ValueError("Worker source or task contract differs from the owned task")
        checkout = Path(record["checkout"]).resolve()
        if checkout != (self.checkouts.root / task_id).resolve():
            raise ValueError("Worker checkout is not owned by this checkout root")
        contract = load_committed_task(checkout, task_id, commit=record["source_commit"],
                                       expected_sha256=record["task_contract_sha256"])
        current_commit = git(checkout, "rev-parse", "HEAD").decode().strip()
        body: dict[str, Any] = {
            "schema_version": _SCHEMA, "action": action, "task_id": task_id,
            "source": str(self.checkouts.source), "source_head": git(self.checkouts.source, "rev-parse", "HEAD").decode().strip(),
            "checkout_root": str(self.checkouts.root), "checkout": str(checkout),
            "branch": git(checkout, "branch", "--show-current").decode().strip(), "checkout_commit": current_commit,
            "task_contract_sha256": contract["task_contract_sha256"], "assistant_run_id": run_id,
            "worker": {key: worker.get(key) for key in
                       _WORKER_KEYS},
            "issued_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        body["semantic_sha256"] = _ticket_sha(body)
        self.tickets.mkdir(parents=True, exist_ok=True)
        path = self.tickets / f"{task_id}-{body['semantic_sha256']}.json"
        if path.exists():
            existing = MaintenanceTicket.read(path, self.tickets).body
            if _ticket_sha(existing) != _ticket_sha(body):
                raise ValueError("A different ticket already owns this task and run")
            return {"ticket_path": str(path), "semantic_sha256": existing["semantic_sha256"]}
        write_record(path, body)
        return {"ticket_path": str(path), "semantic_sha256": body["semantic_sha256"]}

    def run(self, path: Path) -> dict[str, Any]:
        ticket = MaintenanceTicket.read(path, self.tickets)
        with _exclusive_file_lock(self.checkouts.records / "maintenance.lock", timeout_seconds=10):
            body = ticket.body
            if body["source"] != str(self.checkouts.source) or body["checkout_root"] != str(self.checkouts.root):
                raise ValueError("Maintenance ticket belongs to another project")
            expected_checkout = (self.checkouts.root / ticket.task_id).resolve()
            ticket_checkout = Path(body["checkout"]).resolve()
            if ticket_checkout != expected_checkout:
                raise ValueError("Maintenance ticket checkout is not task-owned")
            receipt_path = self.receipts / (body["semantic_sha256"] + ".json")
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if (not isinstance(receipt, dict) or set(receipt) != _RECEIPT_KEYS
                        or receipt.get("ticket_sha256") != body["semantic_sha256"]
                        or receipt.get("schema_version") != _RECEIPT_SCHEMA
                        or receipt.get("semantic_sha256") != _receipt_sha(receipt)):
                    raise ValueError("Maintenance receipt authentication failed")
                return receipt
            record = self.checkouts.observe(ticket.task_id)
            if (Path(record.get("checkout", "")).resolve() != ticket_checkout
                    or record.get("source") not in (None, str(self.checkouts.source))):
                raise ValueError("Observed checkout binding differs from the maintenance ticket")
            if (record.get("source_commit") != body["worker"]["source_head"]
                    or record.get("task_contract_sha256") != body["task_contract_sha256"]):
                raise ValueError("Observed task binding differs from the maintenance ticket")
            worker = _worker(self.checkouts, ticket.task_id)
            expected = body["worker"]
            if any(worker.get(key) != expected.get(key) for key in _WORKER_KEYS):
                raise ValueError("Current worker identity differs from the maintenance ticket")
            if git(self.checkouts.source, "rev-parse", "HEAD").decode().strip() != body["source_head"]:
                raise ValueError("Source changed since the maintenance ticket was issued")
            if git(ticket_checkout, "branch", "--show-current").decode().strip() != body["branch"]:
                raise ValueError("Checkout branch changed since the maintenance ticket was issued")
            if git(ticket_checkout, "rev-parse", "HEAD").decode().strip() != body["checkout_commit"]:
                raise ValueError("Checkout commit changed since the maintenance ticket was issued")
            result = self._dispatch(ticket, record, worker)
            receipt = {"schema_version": _RECEIPT_SCHEMA, "ticket_sha256": body["semantic_sha256"],
                       "action": ticket.action, "task_id": ticket.task_id,
                       "assistant_run_id": body["assistant_run_id"], "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                       "result": result}
            receipt["semantic_sha256"] = _receipt_sha(receipt)
            self.receipts.mkdir(parents=True, exist_ok=True)
            write_record(receipt_path, receipt)
            return receipt

    def _dispatch(self, ticket: MaintenanceTicket, record: dict[str, Any], worker: dict[str, Any]) -> dict[str, Any]:
        if ticket.action == "inspect-worker":
            return status(self.checkouts, ticket.task_id)
        if ticket.action == "verify-candidate":
            return inspect_result(self.checkouts, ticket.task_id, assistant_run_id=ticket.body["assistant_run_id"])
        if ticket.action == "settle-worker":
            return settle_completed(self.checkouts, ticket.task_id, run_id=ticket.body["assistant_run_id"])
        if worker.get("status") not in {"succeeded", "failed", "stopped"} or worker.get("capacity_released") is not True:
            raise ValueError("Docker cleanup requires a terminal, capacity-released worker")
        identity = worker.get("process_identity")
        if not isinstance(identity, dict) or matches(identity) is not False:
            raise ValueError("Docker cleanup requires a confirmed dead host identity")
        if worker.get("job_name") and active_count(worker["job_name"]) != 0:
            raise ValueError("Docker cleanup requires an empty worker job")
        project = "assistant-crew-" + hashlib.sha256(ticket.body["assistant_run_id"].encode()).hexdigest()[:20]
        return remove_unused_project_resources(Path(record["checkout"]), {**worker, "run_id": ticket.body["assistant_run_id"], "compose_project": project})
