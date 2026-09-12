"""Synchronous host entry point for one explicitly authorized ExecutionCrew run."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from Pipeline.TaskReviewAgent.execution_bridge import (
    ExecutionBridgeAbortedError,
    ExecutionCrewBridge,
    ExecutionCrewReceipt,
)
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
from Pipeline.AssistantControl.process_identity import identify
from Pipeline.AssistantControl.runtime_config import compose_environment

from .candidate import CandidateRegistrationError, _scope
from .checkouts import Checkouts, write_record
from .admission import _read_registry, _source_registry_paths
from Pipeline.TaskReviewAgent.contracts import validate_task_id


class CrewWorkerError(ValueError):
    """Worker admission, execution, or durable-state failure."""


BridgeFactory = Callable[..., Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_config(config: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(json.dumps(dict(config), ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise CrewWorkerError("worker config must be JSON-serializable") from exc
    if not isinstance(value, dict):
        raise CrewWorkerError("worker config must be an object")
    return value


def _reservation_identity(checkouts: Checkouts, record: Mapping[str, Any],
                          reservation: Mapping[str, Any], task_id: str) -> None:
    scope = record.get("scope")
    expected = {
        "source": record.get("source"),
        "task_id": task_id,
        "checkout_root": str(checkouts.root),
        "checkout": str(checkouts.root / task_id),
        "source_head": record.get("source_commit"),
        "task_contract_sha256": record.get("task_contract_sha256"),
        "lease_id": scope.get("lease_id") if isinstance(scope, Mapping) else None,
        "plan_id": scope.get("plan_id") if isinstance(scope, Mapping) else None,
    }
    for key, value in expected.items():
        if reservation.get(key) != value:
            raise CrewWorkerError(f"reservation {key} differs from owned task record")
    for key in ("run_id", "lease_id", "plan_id", "source_head", "task_contract_sha256"):
        if type(reservation.get(key)) is not str or not reservation[key].strip():
            raise CrewWorkerError(f"reservation {key} must be a non-empty exact identity")


def _verify_source_reservation(checkouts: Checkouts, reservation: Mapping[str, Any]) -> None:
    lock_path, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(lock_path, timeout_seconds=10):
        registry = _read_registry(registry_path, checkouts.source)
        keys = ("source", "task_id", "checkout_root", "checkout", "run_id",
                "lease_id", "source_head", "task_contract_sha256", "plan_id", "plan")
        if not any(all(item.get(key) == reservation.get(key) for key in keys)
                   for item in registry["reservations"]):
            raise CrewWorkerError("active source admission reservation was not verified")


def _bridge_options(config: Mapping[str, Any]) -> dict[str, Any]:
    source = config.get("bridge", config)
    if not isinstance(source, Mapping):
        raise CrewWorkerError("worker bridge config must be an object")
    allowed = {
        "execution_reasoning_effort", "crew_profile", "validation_profile",
        "command_runner", "timeout_seconds", "worker_slot_id",
        "session_pool_owner", "enable_session_pool", "provider_allowlist",
        "quota_fallback_provider", "provider_profile", "local_rehearsal_context",
        "allow_materialization_bridge",
    }
    options = {key: value for key, value in source.items() if key in allowed}
    if isinstance(options.get("provider_allowlist"), list):
        options["provider_allowlist"] = tuple(options["provider_allowlist"])
    return options


def _compose_project(run_id: str) -> str:
    return "assistant-crew-" + hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:20]


def _write_terminal(path: Path, record: dict[str, Any], *, status: str,
                    error: str | None = None, receipt: ExecutionCrewReceipt | None = None) -> dict[str, Any]:
    worker = dict(record.get("worker") or {})
    worker["status"] = status
    worker["finished_at"] = _now()
    worker["docker_cleanup"] = "not_confirmed_by_host_worker"
    if error is not None:
        worker["error"] = error
    if receipt is not None:
        worker["receipt"] = receipt.to_dict()
    record["worker"] = worker
    write_record(path, record)
    return record


def run_worker(
    checkouts: Checkouts,
    task_id: str,
    reservation: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    bridge_factory: BridgeFactory = ExecutionCrewBridge,
) -> dict[str, Any]:
    """Run exactly one admitted plan synchronously; no scheduler or retry is involved."""
    task_id = validate_task_id(task_id)
    if not isinstance(reservation, Mapping):
        raise CrewWorkerError("worker requires an admission reservation object")
    if not isinstance(config, Mapping):
        raise CrewWorkerError("worker requires a config object")
    saved_config = _json_config(config)
    if saved_config.get("execution_authorized") is not True:
        raise CrewWorkerError("worker requires explicit execution_authorized=true")
    provider = saved_config.get("provider")
    execution_model = saved_config.get("execution_model")
    if type(provider) is not str or not provider.strip():
        raise CrewWorkerError("worker config requires an explicit provider")
    if type(execution_model) is not str or not execution_model.strip():
        raise CrewWorkerError("worker config requires an explicit execution_model")
    run_id = reservation.get("run_id")
    if type(run_id) is not str or not run_id.strip():
        raise CrewWorkerError("reservation requires an exact run_id")
    run_id = run_id.strip()
    record_path = checkouts.records / f"{task_id}.json"
    run_root = checkouts.records / "worker-runs" / task_id / hashlib.sha256(run_id.encode()).hexdigest()
    stop_path = run_root / "stop.request"
    compose_project = _compose_project(run_id)

    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        if not record_path.is_file():
            raise CrewWorkerError("owned task checkout record does not exist")
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CrewWorkerError("owned task checkout record is unreadable") from exc
        try:
            checkouts.observe(task_id)
            _reservation_identity(checkouts, record, reservation, task_id)
            _verify_source_reservation(checkouts, reservation)
            scope = _scope(checkouts, record)
        except (CandidateRegistrationError, ValueError, OSError) as exc:
            raise CrewWorkerError(f"worker admission identity or scope is invalid: {exc}") from exc
        existing = record.get("worker")
        if isinstance(existing, Mapping) and existing.get("status") in {"running", "succeeded", "stopped", "failed"}:
            raise CrewWorkerError("task already has a terminal or running worker state")
        run_root.mkdir(parents=True, exist_ok=True)
        worker = {
            "status": "running", "pid": os.getpid(), "run_id": run_id,
            "process_identity": identify(os.getpid()),
            "task_id": task_id, "lease_id": reservation["lease_id"],
            "plan_id": reservation["plan_id"], "source_head": reservation["source_head"],
            "task_contract_sha256": reservation["task_contract_sha256"],
            "started_at": _now(), "config": saved_config,
            "compose_project": compose_project, "stop_request_path": str(stop_path),
        }
        record["worker"] = worker
        launch = record.get("launch") or {}
        if launch.get("run_id") == run_id and launch.get("process_identity") == worker["process_identity"]:
            worker["job_name"] = launch.get("job_name")
        if bridge_factory is ExecutionCrewBridge:
            from Pipeline.AssistantControl.windows_job import is_assigned
            expected_job = "assistant-job-" + hashlib.sha256(str(run_root).encode()).hexdigest()
            if worker.get("job_name") != expected_job or not is_assigned(expected_job, worker["process_identity"]):
                raise CrewWorkerError("Real provider execution requires the contained worker launcher")
        write_record(record_path, record)

    if stop_path.is_file():
        with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            return _write_terminal(record_path, record, status="stopped", error="stop requested before provider start")

    bridge_config = dict(_bridge_options(saved_config))
    bridge_config.update(execution_model=execution_model.strip(), compose_project=compose_project)
    if bridge_factory is ExecutionCrewBridge:
        # AssistantControl owns the Windows post-crew materializer. The bridge
        # is still narrow: it can emit materialization_required only for exact
        # registered deterministic outputs.
        bridge_config.setdefault("allow_materialization_bridge", True)
    previous_stop_env = os.environ.get("NSC_RUN_STOP_REQUEST_PATH")
    previous_compose_env = {key: os.environ.get(key) for key in ("COMPOSE_FILE", "COMPOSE_PATH_SEPARATOR")}
    os.environ["NSC_RUN_STOP_REQUEST_PATH"] = str(stop_path)
    interrupted: KeyboardInterrupt | None = None
    try:
        from Pipeline.AssistantControl.revision_feedback import prepare_revision_feedback
        retry_arguments = prepare_revision_feedback(checkouts, record, reservation, saved_config)
        if stop_path.is_file():
            raise ExecutionBridgeAbortedError("stop requested while preparing worker inputs")
        os.environ.update(compose_environment(Path(record["checkout"]), run_root,
                                              provider=provider.strip().casefold(),
                                              credential_volume=saved_config.get("credential_volume")))
        bridge = bridge_factory(checkout=Path(record["checkout"]), scope=scope, **bridge_config)
        receipt = bridge.run(plan_id=reservation["plan_id"], provider=provider.strip().casefold(), **retry_arguments)
        if not isinstance(receipt, ExecutionCrewReceipt):
            raise CrewWorkerError("bridge did not return a real ExecutionCrew receipt")
        crew_run_id = receipt.run_id
        verified = bridge.require(crew_run_id)
        if not isinstance(verified, ExecutionCrewReceipt):
            raise CrewWorkerError("bridge.require did not return a real ExecutionCrew receipt")
        expected = (task_id, reservation["lease_id"], reservation["plan_id"],
                    reservation["source_head"], reservation["task_contract_sha256"])
        actual = (verified.task_id, verified.lease_id, verified.plan_id,
                  verified.source_head, verified.task_contract_sha256)
        if actual != expected:
            raise CrewWorkerError("ExecutionCrew receipt identity differs from reservation")
        receipt = verified
        if stop_path.is_file():
            status = "stopped"
            error = "stop requested during provider run"
        elif receipt.crew_status not in {"review_ready", "materialization_required"}:
            status = "failed"
            error = (f"ExecutionCrew returned {receipt.crew_status}: "
                     + "; ".join(receipt.rejection_reasons))
        else:
            status, error = "succeeded", None
    except ExecutionBridgeAbortedError as exc:
        receipt = None
        status, error = "stopped", str(exc)
    except KeyboardInterrupt as exc:
        receipt = None
        interrupted = exc
        status, error = "stopped", "host worker interrupted; Docker cleanup was not confirmed"
    except Exception as exc:
        receipt = None
        status, error = "failed", f"{type(exc).__name__}: {exc}"
    finally:
        for key, value in previous_compose_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if previous_stop_env is None:
            os.environ.pop("NSC_RUN_STOP_REQUEST_PATH", None)
        else:
            os.environ["NSC_RUN_STOP_REQUEST_PATH"] = previous_stop_env

    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        latest = json.loads(record_path.read_text(encoding="utf-8"))
        if receipt is not None:
            latest.setdefault("worker", {})["crew_run_id"] = receipt.run_id
        result = _write_terminal(record_path, latest, status=status, error=error, receipt=receipt)
    if interrupted is not None:
        raise interrupted
    return result


__all__ = ["CrewWorkerError", "run_worker"]
