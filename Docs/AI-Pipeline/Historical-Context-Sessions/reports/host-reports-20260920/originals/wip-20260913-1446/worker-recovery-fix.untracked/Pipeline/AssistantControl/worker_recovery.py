"""Record one dead worker's surviving, authenticated ExecutionCrew result.

A worker host can die after its crew succeeded but before the worker's own
terminal write landed. In NSC-1163 (2026-09-13) the crew reached REVIEW_READY,
the bridge persisted its authenticated receipt, and one lost wait for
`checkouts.lock` then ended the host: the record stayed `running` without a
receipt, and dead-worker settlement records such an attempt as failed with
"Exited without a completed worker result". Re-running the crew would overwrite
the persisted receipt, so the result that survived is recovered instead.

`recover_result` writes only the task's own record, and only when every
precondition holds, checked once before and again inside `checkouts.lock`
immediately before the write: the exact worker run; a host confirmed gone; an
empty Job Object tree; no stop request; proof that the worker never persisted a
terminal outcome of its own (still `running` with its capacity held, or settled
by exactly the dead-worker path); the checkout still at the worker's source
commit; and the persisted receipt authenticated through the bridge the worker
itself built, bound to the worker's reservation identity, with a completed crew
status and both artifacts inside the checkout's ExecutionCrew outputs. The
written record must then pass `inspect_result`, or its exact prior bytes are
restored. Nothing here starts a provider, re-runs the crew, approves, integrates,
changes a crew artifact or the persisted execution receipt, or touches another
task.
"""
from __future__ import annotations

import json
import os
import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from Pipeline.AssistantControl.candidate import _scope
from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.crew_worker import (
    _bridge_options,
    _compose_project,
    _now,
    _write_terminal,
    locked_record_write,
)
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.process_identity import matches
from Pipeline.AssistantControl.result_inspection import inspect_result
from Pipeline.AssistantControl.windows_job import active_count
from Pipeline.AssistantControl.worker_control import _POST_EXIT_IDENTITY_FIELDS, _worker
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge, ExecutionCrewReceipt


SCHEMA_VERSION = "assistant-worker-recovery/v1"
# The exact reason `worker_settlement.settle_completed` records for a confirmed
# exit whose worker never wrote a terminal status and had no stop request.
DEAD_WORKER_SETTLEMENT_REASON = "Exited without a completed worker result"
RECOVERY_REASON = (
    "worker host exited before persisting its terminal status; its ExecutionCrew result "
    "survived and was authenticated from the persisted execution receipt"
)
_COMPLETED_CREW_STATUSES = frozenset({"review_ready", "materialization_required"})
# Written only by a worker's own terminal write or by a forced stop. A worker
# carrying any of them persisted an outcome, which recovery never replaces.
_TERMINAL_WRITE_FIELDS = (
    "receipt", "crew_run_id", "finished_at", "error", "docker_cleanup", "host_exit_confirmed",
)
_RECEIPT_IDENTITY_FIELDS = ("task_id", "lease_id", "plan_id", "source_head", "task_contract_sha256")


class WorkerRecoveryError(ValueError):
    """A recovery precondition does not hold; the task record was left unchanged."""


def _read(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        record = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkerRecoveryError("owned task checkout record is missing or unreadable") from exc
    if not isinstance(record, dict):
        raise WorkerRecoveryError("owned task checkout record is not an object")
    return raw, record


def _restore(path: Path, data: bytes) -> None:
    """Put the exact prior record bytes back with an atomic replace."""
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _verify(
    checkouts: Checkouts, task_id: str, record: dict[str, Any], *, run_id: str, crew_run_id: str,
) -> tuple[str, ExecutionCrewReceipt]:
    """Check every precondition against ``record`` without writing anything.

    Returns which recoverable state the worker is in (``running`` or
    ``settled_dead_worker``) and the authenticated receipt.
    """
    if (record.get("task_id") != task_id or record.get("source") != str(checkouts.source)
            or record.get("checkout") != str(checkouts.root / task_id)):
        raise WorkerRecoveryError("task checkout record identity differs")
    worker = record.get("worker")
    if not isinstance(worker, dict):
        raise WorkerRecoveryError("task has no worker attempt to recover")
    if worker.get("run_id") != run_id:
        raise WorkerRecoveryError("requested run differs from the task's worker run")
    if record.get("candidate"):
        raise WorkerRecoveryError("task already has a registered candidate")
    written = [field for field in _TERMINAL_WRITE_FIELDS if field in worker]
    if written:
        raise WorkerRecoveryError(
            "worker already persisted a terminal outcome of its own (" + ", ".join(written) + ")"
        )
    status = worker.get("status")
    if (status == "running" and worker.get("capacity_released") is not True
            and "settled_at" not in worker and "settlement_reason" not in worker):
        state = "running"
    elif (status == "failed" and worker.get("capacity_released") is True
            and worker.get("settlement_reason") == DEAD_WORKER_SETTLEMENT_REASON):
        state = "settled_dead_worker"
    else:
        raise WorkerRecoveryError(
            "worker is neither running with its capacity held nor settled by the dead-worker path"
        )
    # A recovered `succeeded` record is settled without the tree proof that a
    # non-terminal one needs, so recovery demands that proof, and the complete
    # owned identity behind it, itself.
    missing = [field for field in _POST_EXIT_IDENTITY_FIELDS if not worker.get(field)]
    if missing:
        raise WorkerRecoveryError("worker identity is incomplete: " + ", ".join(missing))
    try:
        owned = _worker(checkouts, task_id)
    except (OSError, RuntimeError, ValueError) as exc:
        raise WorkerRecoveryError(f"worker run is not owned by this checkout root: {exc}") from exc
    if owned != worker:
        raise WorkerRecoveryError("task record changed while recovery was verifying it")
    scope = record.get("scope")
    if not isinstance(scope, Mapping):
        raise WorkerRecoveryError("task has no registered execution scope")
    reservation = {
        "task_id": task_id, "lease_id": scope.get("lease_id"), "plan_id": scope.get("plan_id"),
        "source_head": record.get("source_commit"),
        "task_contract_sha256": record.get("task_contract_sha256"),
    }
    if any(not value or worker.get(key) != value for key, value in reservation.items()):
        raise WorkerRecoveryError("worker reservation identity differs from the owned task scope")
    if worker.get("compose_project") != _compose_project(run_id):
        raise WorkerRecoveryError("worker compose project differs from its run")
    if os.path.lexists(worker["stop_request_path"]):
        raise WorkerRecoveryError("a stop was requested for this run")
    try:
        alive = matches(worker["process_identity"])
    except (OSError, RuntimeError, ValueError) as exc:
        raise WorkerRecoveryError(f"worker host identity cannot be verified: {exc}") from exc
    if alive is not False:
        raise WorkerRecoveryError("worker host is still running")
    try:
        active = active_count(worker["job_name"])
    except (OSError, RuntimeError, ValueError) as exc:
        raise WorkerRecoveryError(f"worker job tree cannot be verified: {exc}") from exc
    if active != 0:
        raise WorkerRecoveryError("worker job tree still has active processes")
    checkout = Path(record["checkout"])
    try:
        head = git(checkout, "rev-parse", "HEAD").decode().strip()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        raise WorkerRecoveryError(f"task checkout HEAD cannot be read: {exc}") from exc
    if head != record.get("source_commit"):
        raise WorkerRecoveryError(
            "task checkout HEAD differs from the worker's source commit; recovery never "
            "reconstructs scope from a moved checkout"
        )
    config = worker.get("config")
    if (not isinstance(config, Mapping) or type(config.get("execution_model")) is not str
            or not config["execution_model"].strip()):
        raise WorkerRecoveryError("worker config does not name its execution model")
    try:
        # Exactly the bridge `crew_worker.run_worker` built for this run: the
        # persisted receipt loads only under the same rigor profiles and model.
        options = dict(_bridge_options(config))
        options.update(execution_model=config["execution_model"].strip(),
                       compose_project=worker["compose_project"])
        options.setdefault("allow_materialization_bridge", True)
        bridge = ExecutionCrewBridge(checkout=checkout, scope=_scope(checkouts, record), **options)
        verified = bridge.require(crew_run_id)
    except Exception as exc:
        raise WorkerRecoveryError(
            f"persisted ExecutionCrew receipt was not authenticated for crew run {crew_run_id}: {exc}"
        ) from exc
    if not isinstance(verified, ExecutionCrewReceipt) or verified.run_id != crew_run_id:
        raise WorkerRecoveryError("bridge did not return the requested ExecutionCrew receipt")
    for key in _RECEIPT_IDENTITY_FIELDS:
        if getattr(verified, key) != worker.get(key):
            raise WorkerRecoveryError(f"ExecutionCrew receipt {key} differs from the worker's reservation")
    if verified.crew_status not in _COMPLETED_CREW_STATUSES:
        raise WorkerRecoveryError(
            f"ExecutionCrew receipt status {verified.crew_status!r} is not a completed crew result"
        )
    output_root = (checkout / "Pipeline" / "ExecutionCrew" / "outputs").resolve()
    for label, value in (("result", verified.result_path), ("candidate patch", verified.candidate_path)):
        if not isinstance(value, str) or not value or not Path(value).resolve().is_relative_to(output_root):
            raise WorkerRecoveryError(f"crew {label} is not inside the checkout's ExecutionCrew outputs")
    return state, verified


def recover_result(
    checkouts: Checkouts, task_id: str, *, run_id: str, crew_run_id: str,
) -> dict[str, Any]:
    """Record the surviving crew result of one dead worker (see the module docstring).

    From a ``running`` record the capacity stays held, so the normal
    `settle_worker` re-verifies the receipt and artifacts before releasing it.
    From a dead-worker settlement the released capacity and ``settled_at`` stay,
    the stale failure reason moves into the ``recovery`` block, and the planner's
    normal path emits `post_crew` for the crew run.
    """
    task_id = validate_task_id(task_id)
    for label, value in (("run_id", run_id), ("crew_run_id", crew_run_id)):
        if type(value) is not str or not value or value != value.strip():
            raise WorkerRecoveryError(f"recovery requires an exact {label}")
    record_path = checkouts.records / f"{task_id}.json"
    _verify(checkouts, task_id, _read(record_path)[1], run_id=run_id, crew_run_id=crew_run_id)

    def write() -> dict[str, Any]:
        prior, record = _read(record_path)
        state, verified = _verify(checkouts, task_id, record, run_id=run_id, crew_run_id=crew_run_id)
        worker = dict(record["worker"])
        recovery: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION, "recovered_at": _now(),
            "crew_run_id": verified.run_id, "prior_status": worker.get("status"),
            "reason": RECOVERY_REASON,
        }
        if "settlement_reason" in worker:
            # Settlement recorded that no result existed; the receipt proves otherwise.
            recovery["prior_settlement_reason"] = worker.pop("settlement_reason")
        worker["crew_run_id"] = verified.run_id
        worker["recovery"] = recovery
        record["worker"] = worker
        try:
            _write_terminal(record_path, record, status="succeeded", receipt=verified)
            inspection = inspect_result(checkouts, task_id, assistant_run_id=run_id)
        except BaseException:
            _restore(record_path, prior)
            raise
        released = worker.get("capacity_released") is True
        return {
            "schema_version": SCHEMA_VERSION, "task_id": task_id, "run_id": run_id,
            "crew_run_id": verified.run_id, "recovered": True, "recovered_from": state,
            "prior_status": recovery["prior_status"],
            "prior_settlement_reason": recovery.get("prior_settlement_reason"),
            "worker_status": "succeeded", "crew_status": verified.crew_status,
            "capacity_released": released,
            "next_step": "post_crew" if released else "settle_worker",
            "inspection": inspection,
            "provider_invoked": False, "crew_rerun": False,
            "approval_granted": False, "integration_performed": False,
        }

    return locked_record_write(checkouts, write)


__all__ = ["DEAD_WORKER_SETTLEMENT_REASON", "WorkerRecoveryError", "recover_result"]
