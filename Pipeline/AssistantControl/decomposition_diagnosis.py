"""Explain why one retained AssistantControl decomposition run stopped.

`diagnose-decomposition` is read-only: it locates the task's current or
archived decomposition receipt for an exact run ID, confirms the receipt's
artifact root is that run's directory under this checkout root's records,
and routes the run through `TaskDecomposition.run_diagnosis`. It writes
nothing, never retries, and every result says `retry_authorized: false`.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.TaskReviewAgent.contracts import validate_task_id

ROOT = Path(__file__).resolve().parents[2]
for module_root in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline" / "TaskGraph"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from TaskDecomposition.run_diagnosis import diagnose_run  # noqa: E402

RECEIPT_SCHEMA = "assistant-decomposition/v1"
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _receipt(manager: Checkouts, task_id: str, run_id: str) -> tuple[Path, dict[str, Any], bytes]:
    current = manager.records / f"{task_id}.decomposition.json"
    candidates = [current] if current.is_file() else []
    candidates += sorted(manager.records.glob(f"{task_id}.decomposition.{run_id}.*.archived.json"))
    matches = []
    for path in candidates:
        if path.is_symlink():
            continue
        data = path.read_bytes()
        value = json.loads(data.decode("utf-8"))
        if isinstance(value, dict) and value.get("run_id") == run_id:
            matches.append((path, value, data))
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one decomposition receipt for {task_id} run {run_id}, found {len(matches)}"
        )
    return matches[0]


def diagnose(manager: Checkouts, task_id: str, *, run_id: str) -> dict[str, Any]:
    validate_task_id(task_id)
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run id must be a plain identifier")
    path, receipt, data = _receipt(manager, task_id, run_id)
    if receipt.get("schema_version") != RECEIPT_SCHEMA or receipt.get("task_id") != task_id:
        raise ValueError("decomposition receipt identity differs")
    expected_root = (manager.records / "decomposition-runs" / run_id).resolve()
    artifact_root = receipt.get("artifact_root")
    if not isinstance(artifact_root, str) or Path(artifact_root).resolve() != expected_root:
        raise ValueError("decomposition receipt artifact root is not this run's retained directory")
    diagnosis = diagnose_run(expected_root)
    if diagnosis.get("task_id") != task_id or diagnosis.get("run_id") != run_id:
        raise ValueError("retained run result identity differs from its receipt")
    diagnosis["receipt"] = {
        "path": path.name,
        "status": receipt.get("status"),
        "source": receipt.get("source"),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    return diagnosis
