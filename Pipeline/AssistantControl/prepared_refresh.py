"""Refresh one untouched, prepared checkout to an inspected Source commit."""
from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
from Pipeline.AssistantControl.worker_state import is_finished_launch, is_finished_worker
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


class PreparedRefreshError(ValueError):
    """Refreshing would lose ownership or preparation evidence."""


def _path(checkouts: Checkouts, task_id: str) -> Path:
    return checkouts.records / f"{validate_task_id(task_id)}.json"


def _journal(checkouts: Checkouts, task_id: str) -> Path:
    return checkouts.records / f"{validate_task_id(task_id)}.prepared-refresh.json"


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreparedRefreshError("prepared refresh journal is unreadable") from exc
    if not isinstance(value, dict):
        raise PreparedRefreshError("prepared refresh journal is invalid")
    return value


def _head(path: Path) -> str:
    return git(path, "rev-parse", "HEAD").decode().strip()


def _clean_owned(checkouts: Checkouts, record: dict[str, Any]) -> Path:
    checkout = Path(record.get("checkout", ""))
    if (record.get("source") != str(checkouts.source)
            or checkout != checkouts.root / record.get("task_id", "")
            or checkout.resolve() != checkout or checkout.is_symlink()):
        raise PreparedRefreshError("prepared checkout identity differs")
    if Path(git(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve() != checkout:
        raise PreparedRefreshError("prepared checkout is not an owned Git root")
    if git(checkout, "branch", "--show-current").decode().strip() != record.get("branch"):
        raise PreparedRefreshError("prepared checkout branch changed")
    if git(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
        raise PreparedRefreshError("prepared checkout is dirty; changes were preserved")
    return checkout


def _forbidden(record: dict[str, Any]) -> None:
    # Finished runs leave evidence behind on purpose: settle updates the worker entry and
    # retire archives it into worker_history. Refusing on that evidence made a refresh
    # impossible after any cancelled or failed run, and with refresh unreachable the
    # checkout stays pinned at its old commit and reserve refuses too.
    worker = record.get("worker")
    if worker and not is_finished_worker(worker):
        raise PreparedRefreshError("prepared refresh refuses record with worker")
    launch = record.get("launch")
    if launch and not is_finished_launch(record, launch):
        raise PreparedRefreshError("prepared refresh refuses record with launch")
    for field in ("candidate", "revision", "revision_history",
                  "candidate_lineage", "integration", "human_review"):
        if record.get(field):
            raise PreparedRefreshError(f"prepared refresh refuses record with {field}")
    if record.get("approval") is not None:
        raise PreparedRefreshError("prepared refresh refuses an approved or reviewed record")
    if record.get("status") != "prepared":
        raise PreparedRefreshError("only a prepared checkout can be refreshed")


def _active_admission(checkouts: Checkouts, task_id: str) -> None:
    _, registry_path = _source_registry_paths(checkouts.source)
    registry = _read_registry(registry_path, checkouts.source)
    if any(item.get("task_id") == task_id for item in registry["reservations"]):
        raise PreparedRefreshError("active admission exists; prepared refresh refused")


def _finish(record_path: Path, record: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    history = record.get("preparation_history")
    if not isinstance(history, list):
        history = []
    history.append({"source_commit": record.get("source_commit"),
                    "task_contract_sha256": record.get("task_contract_sha256"),
                    "refreshed_to": journal["source_commit"],
                    "recorded_at": journal["created_at"]})
    record["preparation_history"] = history
    record["source_commit"] = journal["source_commit"]
    record["task_contract_sha256"] = journal["task_contract_sha256"]
    record.pop("scope", None)
    record["status"] = "prepared"
    write_record(record_path, record)
    return record


def refresh_prepared(checkouts: Checkouts, task_id: str, expected_source_commit: str) -> dict[str, Any]:
    """Fast-forward an owned pristine prepared checkout to exact Source HEAD."""
    task_id = validate_task_id(task_id)
    if type(expected_source_commit) is not str or not expected_source_commit:
        raise PreparedRefreshError("refresh requires an exact expected Source commit")
    record_path, journal_path = _path(checkouts, task_id), _journal(checkouts, task_id)
    source_lock, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        with _exclusive_file_lock(source_lock, timeout_seconds=10):
            record = _read(record_path)
            if record.get("task_id") != task_id:
                raise PreparedRefreshError("task record identity differs")
            _active_admission(checkouts, task_id)
            _forbidden(record)
            checkout = _clean_owned(checkouts, record)
            actual_source = _head(checkouts.source)
            if actual_source != expected_source_commit:
                raise PreparedRefreshError("Source HEAD differs from expected_source_commit")
            if _head(checkout) == expected_source_commit and not journal_path.exists():
                if record.get("source_commit") != expected_source_commit:
                    raise PreparedRefreshError("checkout advanced outside recorded preparation; preserved")
                load_committed_task(checkout, task_id, commit=expected_source_commit,
                                    expected_sha256=record.get("task_contract_sha256"))
                return record
            old = record.get("source_commit")
            if not isinstance(old, str):
                raise PreparedRefreshError("prepared record has no source commit")
            try:
                git(checkouts.source, "merge-base", "--is-ancestor", old, expected_source_commit)
            except RuntimeError as exc:
                raise PreparedRefreshError("expected Source is not a descendant of prepared HEAD") from exc
            if journal_path.is_file():
                pending = _read(journal_path)
                if (pending.get("task_id") != task_id
                        or pending.get("source_commit") != expected_source_commit
                        or pending.get("new_commit") != expected_source_commit):
                    raise PreparedRefreshError("retained refresh journal requires inspection")
                if _head(checkout) == pending.get("new_commit"):
                    _clean_owned(checkouts, record)
                    load_committed_task(checkout, task_id, commit=expected_source_commit,
                                        expected_sha256=pending.get("task_contract_sha256"))
                    if record.get("source_commit") == expected_source_commit:
                        journal_path.unlink(missing_ok=True)
                        return record
                    result = _finish(record_path, record, pending)
                    journal_path.unlink(missing_ok=True)
                    return result
                raise PreparedRefreshError("retained refresh journal is not safely recoverable")
            task = load_committed_task(checkouts.source, task_id, commit=expected_source_commit)
            if task.get("contract_disposition") != "active":
                raise PreparedRefreshError("task is no longer active at inspected Source")
            operation = uuid.uuid4().hex
            journal = {"schema_version": "assistant-prepared-refresh/v1", "task_id": task_id,
                       "old_commit": old, "source_commit": expected_source_commit,
                       "new_commit": expected_source_commit,
                       "task_contract_sha256": task["task_contract_sha256"],
                       "created_at": datetime.now(timezone.utc).isoformat(), "operation": operation}
            write_record(journal_path, journal)
            try:
                if _head(checkouts.source) != expected_source_commit:
                    raise PreparedRefreshError("Source changed before checkout fetch")
                git(checkout, "fetch", "--no-tags", str(checkouts.source), expected_source_commit,
                    timeout_seconds=180)
                if _head(checkouts.source) != expected_source_commit or _head(checkout) != old:
                    raise PreparedRefreshError("Source or prepared checkout changed after fetch")
                _clean_owned(checkouts, record)
                load_committed_task(checkouts.source, task_id, commit=expected_source_commit,
                                    expected_sha256=task["task_contract_sha256"])
                git(checkout, "merge", "--ff-only", "--no-overwrite-ignore", "FETCH_HEAD",
                    timeout_seconds=180)
                if _head(checkout) != expected_source_commit:
                    raise PreparedRefreshError("prepared checkout did not fast-forward exactly")
                _clean_owned(checkouts, record)
                journal["phase"] = "post_ff"
                write_record(journal_path, journal)
                result = _finish(record_path, record, journal)
                journal_path.unlink(missing_ok=True)
                return result
            except PreparedRefreshError:
                raise
            except Exception as exc:
                raise PreparedRefreshError("prepared refresh failed; retained journal for recovery") from exc


__all__ = ["PreparedRefreshError", "refresh_prepared"]
