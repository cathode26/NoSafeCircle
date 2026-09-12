"""Owned isolated task checkouts, independent of scheduler runs and Issues.

Preparing a checkout does not authorize a worker or approve its changes.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from Pipeline.AssistantControl.inspect_project import git
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


def write_record(path: Path, record: dict) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class Checkouts:
    def __init__(self, source: Path, root: Path):
        self.source = Path(git(source, "rev-parse", "--show-toplevel").decode().strip()).resolve()
        self.root = root.resolve()
        if self.root.is_relative_to(self.source) or self.source.is_relative_to(self.root):
            raise ValueError("Task checkouts must be outside the source project in a separate directory")
        self.records = self.root / ".assistant-control"

    def prepare(self, task_id: str, *, expected_commit: str | None = None) -> dict:
        task_id = validate_task_id(task_id)
        self.records.mkdir(parents=True, exist_ok=True)
        with _exclusive_file_lock(self.records / "checkouts.lock", timeout_seconds=10):
            owner = self.records / "project.json"
            identity = {"source": str(self.source), "checkout_root": str(self.root)}
            if owner.exists():
                if json.loads(owner.read_text(encoding="utf-8")) != identity:
                    raise ValueError("Checkout directory belongs to another source project")
            else:
                write_record(owner, identity)
            path = self.records / f"{task_id}.json"
            checkout = self.root / task_id
            if path.exists():
                record = json.loads(path.read_text(encoding="utf-8"))
                if record.get("source") != str(self.source) or record.get("task_id") != task_id:
                    raise ValueError("Task checkout record identity differs")
                if record.get("checkout") != str(checkout):
                    raise ValueError("Task checkout path differs")
                if (expected_commit is not None
                        and record["source_commit"] != expected_commit
                        and (record.get("status") != "preparing" or checkout.exists())):
                    raise ValueError("Existing checkout uses a different starting commit; it was preserved")
                if record["status"] == "preparing" and checkout.exists():
                    # A crash after rename but before receipt can be recovered
                    # only when the complete checkout still proves the receipt.
                    self._verify_initial(record)
                    record["status"] = "prepared"
                    write_record(path, record)
                    return self.observe(task_id)
                elif record["status"] == "preparing":
                    retained = record.get("staging")
                    if not isinstance(retained, str) or not retained:
                        raise ValueError("Incomplete checkout preparation has an invalid staging path")
                    retained_path = Path(retained)
                    if (retained_path.parent.resolve() != self.root
                            or not retained_path.name.startswith(f".{task_id}-")):
                        raise ValueError("Incomplete checkout preparation staging path differs")
                    if retained_path.exists() or retained_path.is_symlink():
                        raise ValueError(f"Incomplete checkout preparation; retained at {retained}")
                    commit = git(self.source, "rev-parse", "HEAD").decode().strip()
                    if expected_commit is not None and commit != expected_commit:
                        raise ValueError("Source commit changed since inspection; inspect before preparing")
                    if expected_commit is None and commit != record["source_commit"]:
                        raise ValueError(
                            "Source commit changed after failed preparation; inspect before preparing"
                        )
                    expected_contract = (
                        record["task_contract_sha256"]
                        if commit == record["source_commit"] else None
                    )
                    contract = load_committed_task(
                        self.source, task_id, commit=commit,
                        expected_sha256=expected_contract,
                    )
                    if contract.get("contract_disposition") != "active":
                        raise ValueError("Only active task contracts can receive a checkout")
                    staging = self.root / f".{task_id}-{uuid.uuid4().hex}"
                    record["source_commit"] = commit
                    record["task_contract_sha256"] = contract["task_contract_sha256"]
                    record["staging"] = str(staging)
                    write_record(path, record)
                else:
                    return self.observe(task_id)
            else:
                if checkout.exists():
                    raise ValueError(f"Existing directory is not owned by this tool: {checkout}")
                commit = git(self.source, "rev-parse", "HEAD").decode().strip()
                if expected_commit is not None and commit != expected_commit:
                    raise ValueError("Source commit changed since inspection; inspect before preparing")
                contract = load_committed_task(self.source, task_id, commit=commit)
                if contract.get("contract_disposition") != "active":
                    raise ValueError("Only active task contracts can receive a new checkout")
                staging = self.root / f".{task_id}-{uuid.uuid4().hex}"
                record = {
                    "schema_version": "assistant-checkout/v1", "task_id": task_id,
                    "source": str(self.source), "checkout": str(checkout),
                    "staging": str(staging), "source_commit": commit,
                    "task_contract_sha256": contract["task_contract_sha256"],
                    "branch": f"assistant/{task_id}", "status": "preparing",
                    "approval": None, "worker": None,
                }
                write_record(path, record)
            # Local transport only; no working files or ignored Unity Library
            # copied. Independent objects keep this a standalone Unity project.
            git(self.source, "clone", "--no-local", "--no-checkout",
                str(self.source), str(staging), timeout_seconds=180)
            git(staging, "config", "core.longpaths", "true")
            git(staging, "remote", "remove", "origin")
            git(staging, "checkout", "-b", record["branch"], commit)
            # Never replace an unrelated destination. Under this root's lock,
            # rename publishes only the newly created staging directory.
            if checkout.exists():
                raise ValueError(f"Checkout appeared during preparation: {checkout}")
            staging.rename(checkout)
            self._verify_initial(record)
            record["status"] = "prepared"
            write_record(path, record)
            return self.observe(task_id)

    def _verify_initial(self, record: dict) -> None:
        checkout = Path(record["checkout"])
        if checkout.resolve() != checkout or checkout.is_symlink():
            raise ValueError("Checkout path was redirected")
        if Path(git(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve() != checkout:
            raise ValueError("Checkout is not an independent Git root")
        if git(checkout, "rev-parse", "HEAD").decode().strip() != record["source_commit"]:
            raise ValueError("Prepared checkout commit changed")
        if git(checkout, "branch", "--show-current").decode().strip() != record["branch"]:
            raise ValueError("Prepared checkout branch changed")
        if git(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
            raise ValueError("Incomplete preparation contains local changes; preserved for inspection")
        load_committed_task(checkout, record["task_id"], commit=record["source_commit"],
                            expected_sha256=record["task_contract_sha256"])

    def observe(self, task_id: str) -> dict:
        from Pipeline.AssistantControl.inspect_project import changes
        task_id = validate_task_id(task_id)
        record = json.loads((self.records / f"{task_id}.json").read_text(encoding="utf-8"))
        checkout = self.root / task_id
        if record.get("source") != str(self.source) or record.get("checkout") != str(checkout):
            raise ValueError("Task checkout record identity differs")
        if record.get("task_id") != task_id:
            raise ValueError("Task checkout record has a different task ID")
        if checkout.resolve() != checkout:
            raise ValueError("Task checkout was redirected")
        if Path(git(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve() != checkout:
            raise ValueError("Task checkout is not an independent Git root")
        return {**record, "current_commit": git(checkout, "rev-parse", "HEAD").decode().strip(),
                "current_branch": git(checkout, "branch", "--show-current").decode().strip(),
                "local_changes": changes(checkout),
                "execution_authorized": False}
