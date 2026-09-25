"""Explain why one retained AssistantControl decomposition run stopped.

`diagnose-decomposition` is read-only: it locates the task's current or
archived decomposition receipt for an exact run ID, confirms the receipt's
artifact root is that run's directory under this checkout root's records,
reads the run only through link-free components beneath the records root,
and routes it through `TaskDecomposition.run_diagnosis`, passing the receipt
so a run the host refused is not reported as a success. It writes nothing,
never retries, and every result says `retry_authorized: false`.
"""
from __future__ import annotations

import hashlib
import os
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

from TaskDecomposition.run_diagnosis import (  # noqa: E402
    DiagnosisEvidenceError,
    confined,
    diagnose_run,
    parse_json_object,
)

RECEIPT_SCHEMA = "assistant-decomposition/v1"
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))


def _receipt(manager: Checkouts, task_id: str, run_id: str) -> tuple[str, dict[str, Any], bytes]:
    names = [f"{task_id}.decomposition.json"] + sorted(
        path.name for path in manager.records.glob(f"{task_id}.decomposition.{run_id}.*.archived.json")
    )
    matches = []
    for name in names:
        path = confined(manager.records, name)
        if not path.is_file():
            continue
        data = path.read_bytes()
        value = parse_json_object(data, f"decomposition receipt {name}")
        if value.get("run_id") == run_id:
            matches.append((name, value, data))
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one decomposition receipt for {task_id} run {run_id}, found {len(matches)}"
        )
    return matches[0]


def diagnose(manager: Checkouts, task_id: str, *, run_id: str) -> dict[str, Any]:
    validate_task_id(task_id)
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run id must be a plain identifier")
    name, receipt, data = _receipt(manager, task_id, run_id)
    if receipt.get("schema_version") != RECEIPT_SCHEMA or receipt.get("task_id") != task_id:
        raise ValueError("decomposition receipt identity differs")
    run_dir = confined(manager.records, f"decomposition-runs/{run_id}")
    artifact_root = receipt.get("artifact_root")
    if not isinstance(artifact_root, str) or not _same_path(artifact_root, run_dir):
        raise ValueError("decomposition receipt artifact root is not this run's retained directory")
    try:
        diagnosis = diagnose_run(run_dir, receipt=receipt)
    except DiagnosisEvidenceError as exc:
        raise ValueError(f"retained run evidence refused: {exc}") from exc
    if diagnosis.get("task_id") != task_id or diagnosis.get("run_id") != run_id:
        raise ValueError("retained run result identity differs from its receipt")
    diagnosis["receipt"] = {
        "path": name,
        "status": receipt.get("status"),
        "source": receipt.get("source"),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    return diagnosis
