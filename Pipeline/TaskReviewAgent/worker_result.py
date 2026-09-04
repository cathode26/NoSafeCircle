"""Identity-bound terminal result contract for scheduler child processes."""

from __future__ import annotations

import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


WORKER_RESULT_SCHEMA_VERSION = "1.0"
WORKER_SUCCESS_STATUSES = frozenset({"human_action_required", "completed"})
WORKER_TERMINAL_STATUSES = frozenset(
    {*WORKER_SUCCESS_STATUSES, "blocked", "no_safe_work", "error"}
)
WORKER_STATUS_EXIT_CODES = {
    "human_action_required": 0,
    "completed": 0,
    "blocked": 3,
    "no_safe_work": 4,
    "error": 2,
}
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,95}$")


class WorkerResultError(RuntimeError):
    """Raised when a scheduler child result is missing, stale, or incoherent."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise WorkerResultError(f"worker result {field} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WorkerResultError(f"worker result {field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise WorkerResultError(f"worker result {field} must be a UTC timestamp")
    return parsed.astimezone(timezone.utc)


def _load_run_metadata(run_dir: Path) -> dict[str, Any]:
    try:
        value = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkerResultError("worker run metadata is missing or unreadable") from exc
    if not isinstance(value, dict):
        raise WorkerResultError("worker run metadata must be a JSON object")
    return value


def _validate_run_identity(
    metadata: Mapping[str, Any],
    *,
    run_id: str,
    worker_id: str,
    task_id: str,
) -> None:
    schema_version = metadata.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version:
        raise WorkerResultError("run metadata schema_version is missing")
    expected = {
        "run_id": run_id,
        "worker_id": worker_id,
        "task_id": task_id,
    }
    mismatched = [key for key, item in expected.items() if metadata.get(key) != item]
    if mismatched:
        raise WorkerResultError(
            "run metadata identity mismatch: " + ", ".join(sorted(mismatched))
        )
    _parse_utc(metadata.get("started_at_utc"), field="run started_at_utc")


def initialize_worker_run(
    *,
    output_root: Path | str,
    task_id: str,
    run_id: str,
    worker_id: str,
    started_at_utc: str,
) -> Path:
    """Create the exact scheduler-owned run directory and immutable identity file."""

    if re.fullmatch(r"NSC-[0-9]{3}", task_id) is None:
        raise WorkerResultError("worker run task_id is invalid")
    if _RUN_ID_RE.fullmatch(run_id) is None:
        raise WorkerResultError("worker run run_id is invalid")
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise WorkerResultError("worker run worker_id is invalid")
    _parse_utc(started_at_utc, field="started_at_utc")
    root = Path(output_root).resolve()
    run_dir = root / task_id / run_id
    if not run_dir.is_relative_to(root):
        raise WorkerResultError("worker run path escaped its output root")
    run_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema_version": WORKER_RESULT_SCHEMA_VERSION,
        "run_id": run_id,
        "task_id": task_id,
        "worker_id": worker_id,
        "started_at_utc": started_at_utc,
    }
    (run_dir / "run.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return run_dir


def _write_result(
    *,
    filename: str,
    run_dir: Path | str,
    run_id: str,
    worker_id: str,
    task_id: str,
    source_head: str,
    task_contract_sha256: str,
    terminal_status: str,
    outcome_authority: str,
    issue_number: int | None,
    exit_code: int,
    pid: int,
) -> Path:
    if terminal_status not in WORKER_TERMINAL_STATUSES:
        raise WorkerResultError(f"unsupported terminal status {terminal_status!r}")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise WorkerResultError("worker result exit_code must be an integer")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
        raise WorkerResultError("worker result pid must be a positive integer")
    if not isinstance(outcome_authority, str) or not outcome_authority.strip():
        raise WorkerResultError("worker result outcome_authority is invalid")
    if not _GIT_SHA_RE.fullmatch(source_head):
        raise WorkerResultError("worker result source_head is invalid")
    if not _SHA256_RE.fullmatch(task_contract_sha256):
        raise WorkerResultError("worker result task_contract_sha256 is invalid")
    if issue_number is not None and (
        not isinstance(issue_number, int)
        or isinstance(issue_number, bool)
        or issue_number < 1
    ):
        raise WorkerResultError("worker result issue_number is invalid")
    if terminal_status in WORKER_SUCCESS_STATUSES and issue_number is None:
        raise WorkerResultError("successful worker result requires an Issue number")
    if terminal_status == "no_safe_work" and issue_number is not None:
        raise WorkerResultError("no-safe-work result cannot carry an Issue number")
    if WORKER_STATUS_EXIT_CODES[terminal_status] != exit_code:
        raise WorkerResultError("worker result status and exit code disagree")
    resolved_run_dir = Path(run_dir).resolve()
    _validate_run_identity(
        _load_run_metadata(resolved_run_dir),
        run_id=run_id,
        worker_id=worker_id,
        task_id=task_id,
    )
    target = resolved_run_dir / filename
    if target.exists():
        raise WorkerResultError(f"worker result already exists: {target}")
    payload = {
        "schema_version": WORKER_RESULT_SCHEMA_VERSION,
        "run_id": run_id,
        "worker_id": worker_id,
        "task_id": task_id,
        "source_head": source_head,
        "task_contract_sha256": task_contract_sha256,
        "terminal_status": terminal_status,
        "outcome_authority": outcome_authority,
        "issue_number": issue_number,
        "exit_code": exit_code,
        "pid": pid,
        "finished_at_utc": _utc_now(),
    }
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, target)
    return target


def write_pipeline_result(**values: Any) -> Path:
    """Publish the inner pipeline's result for the tracked host wrapper to relay."""

    return _write_result(filename="pipeline_result.json", **values)


def write_worker_result(**values: Any) -> Path:
    """Publish the scheduler-tracked process's final authoritative artifact."""

    return _write_result(filename="run_result.json", **values)


def validate_worker_result(
    path: Path | str,
    *,
    expected_run_id: str,
    expected_worker_id: str,
    expected_task_id: str,
    expected_source_head: str,
    expected_task_contract_sha256: str,
    expected_pid: int | None,
    observed_exit_code: int,
    started_at_utc: str,
    observed_at_utc: str,
    expected_issue_number: int | None = None,
) -> dict[str, Any]:
    """Validate the scheduler-derived result path against one exact assignment."""

    if type(observed_exit_code) is not int:
        raise WorkerResultError("observed worker exit code must be an integer")
    if expected_pid is not None and (
        type(expected_pid) is not int or expected_pid < 1
    ):
        raise WorkerResultError("expected worker pid must be a positive integer")
    if expected_issue_number is not None and (
        type(expected_issue_number) is not int or expected_issue_number < 1
    ):
        raise WorkerResultError("expected Issue number must be a positive integer")
    target = Path(path).resolve()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
        metadata = _load_run_metadata(target.parent)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkerResultError(f"worker result is missing or unreadable: {target}") from exc
    if not isinstance(value, dict) or not isinstance(metadata, dict):
        raise WorkerResultError("worker result and run metadata must be JSON objects")
    expected_result = {
        "schema_version": WORKER_RESULT_SCHEMA_VERSION,
        "run_id": expected_run_id,
        "worker_id": expected_worker_id,
        "task_id": expected_task_id,
        "source_head": expected_source_head,
        "task_contract_sha256": expected_task_contract_sha256,
        "exit_code": observed_exit_code,
    }
    if expected_pid is not None:
        expected_result["pid"] = expected_pid
    mismatched = [
        key for key, item in expected_result.items() if value.get(key) != item
    ]
    if mismatched:
        raise WorkerResultError(
            "worker result identity mismatch: " + ", ".join(sorted(mismatched))
        )
    if type(value.get("exit_code")) is not int:
        raise WorkerResultError("worker result exit_code must be an integer")
    if type(value.get("pid")) is not int or value["pid"] < 1:
        raise WorkerResultError("worker result pid is invalid")
    _validate_run_identity(
        metadata,
        run_id=expected_run_id,
        worker_id=expected_worker_id,
        task_id=expected_task_id,
    )
    status = value.get("terminal_status")
    if not isinstance(status, str) or status not in WORKER_TERMINAL_STATUSES:
        raise WorkerResultError("worker result terminal_status is invalid")
    expected_code = WORKER_STATUS_EXIT_CODES[status]
    if observed_exit_code != expected_code:
        raise WorkerResultError("worker result status and exit code disagree")
    if (
        not isinstance(value.get("outcome_authority"), str)
        or not value["outcome_authority"].strip()
    ):
        raise WorkerResultError("worker result outcome_authority is missing")
    issue_number = value.get("issue_number")
    if issue_number is not None and (
        not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number < 1
    ):
        raise WorkerResultError("worker result issue_number is invalid")
    if status in WORKER_SUCCESS_STATUSES and issue_number is None:
        raise WorkerResultError("successful worker result requires an Issue number")
    if status == "no_safe_work" and issue_number is not None:
        raise WorkerResultError("no-safe-work result cannot carry an Issue number")
    if expected_issue_number is not None and issue_number != expected_issue_number:
        raise WorkerResultError("worker result issue_number does not match admission")
    started = _parse_utc(started_at_utc, field="assignment started_at_utc")
    finished = _parse_utc(value.get("finished_at_utc"), field="finished_at_utc")
    observed = _parse_utc(observed_at_utc, field="observed_at_utc")
    if finished < started or finished > observed:
        raise WorkerResultError("worker result finished_at_utc is outside the observed lifetime")
    try:
        modified = datetime.fromtimestamp(target.stat().st_mtime, timezone.utc)
    except (OSError, OverflowError, ValueError) as exc:
        raise WorkerResultError("worker result mtime is unreadable") from exc
    if not math.isfinite(modified.timestamp()) or modified <= started or modified > observed:
        raise WorkerResultError("worker result mtime is outside the observed lifetime")
    return dict(value)


__all__ = [
    "WORKER_RESULT_SCHEMA_VERSION",
    "WORKER_SUCCESS_STATUSES",
    "WORKER_STATUS_EXIT_CODES",
    "WORKER_TERMINAL_STATUSES",
    "WorkerResultError",
    "initialize_worker_run",
    "validate_worker_result",
    "write_pipeline_result",
    "write_worker_result",
]
