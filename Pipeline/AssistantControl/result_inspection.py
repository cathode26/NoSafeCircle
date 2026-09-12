"""Read and authenticate one retained ExecutionCrew result without changing it."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id


class ResultInspectionError(ValueError):
    """A retained worker result or patch cannot be authenticated."""


def _attempts(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for item in record.get("worker_history", []):
        if isinstance(item, Mapping):
            worker = item.get("worker")
            launch = item.get("launch")
            attempt = worker if isinstance(worker, Mapping) else launch
            if isinstance(attempt, Mapping):
                attempts.append(dict(attempt))
    worker = record.get("worker")
    launch = record.get("launch")
    current = worker if isinstance(worker, Mapping) else launch
    if isinstance(current, Mapping):
        attempts.append(dict(current))
    return attempts


def _regular_artifact(
    value: object, expected_sha256: object, output_root: Path, label: str,
) -> tuple[Path, bytes]:
    if not isinstance(value, str) or not isinstance(expected_sha256, str):
        raise ResultInspectionError(f"{label} path and hash are missing")
    path = Path(value).resolve()
    if not path.is_relative_to(output_root) or path.is_symlink() or not path.is_file():
        raise ResultInspectionError(f"{label} is not a regular file in the owned output root")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ResultInspectionError(f"{label} bytes differ from the durable receipt")
    return path, data


def inspect_result(
    checkouts: Checkouts, task_id: str, *, assistant_run_id: str | None = None,
) -> dict[str, Any]:
    """Return a bounded summary after re-hashing the exact result and patch bytes."""
    task_id = validate_task_id(task_id)
    record = checkouts.observe(task_id)
    attempts = _attempts(record)
    if assistant_run_id is not None:
        attempts = [item for item in attempts if item.get("run_id") == assistant_run_id]
    else:
        attempts = [item for item in attempts if isinstance(item.get("receipt"), Mapping)]
        attempts = attempts[-1:]
    if len(attempts) != 1:
        raise ResultInspectionError(
            "exactly one retained worker attempt must match the requested run"
        )
    worker = attempts[0]
    receipt = worker.get("receipt")
    if not isinstance(receipt, Mapping):
        raise ResultInspectionError("worker attempt has no durable ExecutionCrew receipt")
    receipt = dict(receipt)
    crew_run_id = worker.get("crew_run_id")
    expected = {
        "task_id": task_id,
        "run_id": crew_run_id,
        "source_head": worker.get("source_head"),
        "task_contract_sha256": worker.get("task_contract_sha256"),
    }
    if (worker.get("run_id") is None or not crew_run_id
            or any(not value or receipt.get(key) != value for key, value in expected.items())):
        raise ResultInspectionError("worker and ExecutionCrew receipt identities differ")
    load_committed_task(
        Path(record["checkout"]), task_id, commit=str(receipt["source_head"]),
        expected_sha256=str(receipt["task_contract_sha256"]),
    )
    output_root = (
        Path(record["checkout"]) / "Pipeline" / "ExecutionCrew" / "outputs"
    ).resolve()
    result_path, result_bytes = _regular_artifact(
        receipt.get("result_path"), receipt.get("result_sha256"),
        output_root, "crew result",
    )
    try:
        result = json.loads(result_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ResultInspectionError("crew result is not readable JSON") from exc
    if not isinstance(result, Mapping):
        raise ResultInspectionError("crew result must be an object")
    result_identity = {
        "task_id": task_id,
        "run_id": crew_run_id,
        "source_head": receipt.get("source_head"),
        "crew_status": receipt.get("crew_status"),
        "final_actual_changed_paths": receipt.get("final_actual_changed_paths"),
    }
    if any(result.get(key) != value for key, value in result_identity.items()):
        raise ResultInspectionError("crew result identity differs from its durable receipt")
    contract_identity = result.get("task_contract_identity")
    if (not isinstance(contract_identity, Mapping)
            or contract_identity.get("sha256") != receipt.get("task_contract_sha256")):
        raise ResultInspectionError("crew result task contract identity differs")

    patch_path = None
    patch_bytes = None
    if receipt.get("candidate_path") is not None or receipt.get("candidate_sha256") is not None:
        patch_path, patch_bytes = _regular_artifact(
            receipt.get("candidate_path"), receipt.get("candidate_sha256"),
            output_root, "candidate patch",
        )
    if receipt.get("crew_status") == "review_ready" and patch_bytes is None:
        raise ResultInspectionError("review-ready result has no authenticated candidate patch")
    if result.get("candidate_patch_sha256") not in {None, receipt.get("candidate_sha256")}:
        raise ResultInspectionError("crew result and receipt name different candidate patch bytes")

    return {
        "schema_version": "assistant-result-inspection/v1",
        "task_id": task_id,
        "assistant_run_id": worker["run_id"],
        "crew_run_id": crew_run_id,
        "worker_status": worker.get("status"),
        "capacity_released": worker.get("capacity_released") is True,
        "crew_status": receipt.get("crew_status"),
        "source_head": receipt.get("source_head"),
        "task_contract_sha256": receipt.get("task_contract_sha256"),
        "result": {
            "path": str(result_path),
            "sha256": receipt.get("result_sha256"),
            "size_bytes": len(result_bytes),
        },
        "candidate_patch": (
            None if patch_path is None else {
                "path": str(patch_path),
                "sha256": receipt.get("candidate_sha256"),
                "size_bytes": len(patch_bytes or b""),
            }
        ),
        "final_actual_changed_paths": list(receipt.get("final_actual_changed_paths") or []),
        "attempts_used": result.get("attempts_used"),
        "duration_seconds": result.get("duration_seconds"),
        "validator_status": result.get("validator_status"),
        "rejection_reasons": list(receipt.get("rejection_reasons") or []),
        "human_next_step": result.get("human_next_step"),
        "authenticated": True,
        "mutations_performed": False,
    }


__all__ = ["ResultInspectionError", "inspect_result"]
