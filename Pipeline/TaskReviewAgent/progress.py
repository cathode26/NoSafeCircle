"""Live terminal progress and durable per-run logs for the Game Task Agent."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Protocol


PROGRESS_SCHEMA_VERSION = "1.1"
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]+")
_SCALAR = (str, int, float, bool, type(None))
_OPERATOR_LABELS = {
    "run_started": "START",
    "log_ready": "LOG",
    "log_watch": "LOG",
    "routing_started": "ROUTE",
    "routing_completed": "ROUTE",
    "state_observed": "STATE",
    "codex_supervisor_started": "AGENT",
    "codex_supervisor_heartbeat": "AGENT",
    "codex_supervisor_failed": "AGENT ERROR",
    "supervisor_decision": "PLAN",
    "pipeline_action_started": "WORK",
    "pipeline_action_heartbeat": "WORK",
    "action_completed": "DONE",
    "action_rejected": "BLOCKED",
    "checkout_preparation_blocked": "BLOCKED",
    "repeated_action_rejection": "BLOCKED",
    "terminal_state": "RESULT",
    "turn_budget_exhausted": "BLOCKED",
    "run_finished": "END",
}
_TECHNICAL_ONLY_EVENTS = frozenset(
    {
        "routing_observation_started",
        "routing_observation_completed",
        "state_observation_started",
        "state_observation_completed",
        "codex_supervisor_completed",
        "pipeline_action_completed",
        "pipeline_action_failed",
    }
)
_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "api_key",
        "access_token",
        "credential",
        "credentials",
        "password",
        "prompt",
        "raw_prompt",
        "raw_output",
        "secret",
        "secret_prompt",
        "token",
        "file_contents",
        "content",
        "body",
        "feedback_text",
        "patch",
        "diff",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _component(value: str, *, fallback: str) -> str:
    normalized = _SAFE_COMPONENT.sub("-", str(value).strip()).strip("-._")
    return normalized or fallback


def _safe_json(value: Any) -> Any:
    try:
        return json.loads(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                default=lambda item: str(item),
            )
        )
    except (TypeError, ValueError):
        return str(value)


def _short_text(value: Any, *, limit: int = 480) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _safe_field_name(value: Any) -> str:
    return _component(str(value), fallback="field").replace("-", "_").casefold()


def _field_is_safe(key: str) -> bool:
    normalized = key.casefold()
    return (
        normalized not in _SENSITIVE_FIELD_NAMES
        and not normalized.endswith("_body")
        and not normalized.endswith("_contents")
        and not normalized.startswith("raw_")
    )


def _terminal_value(value: Any, *, limit: int = 180) -> str | None:
    if isinstance(value, _SCALAR):
        if value in (None, ""):
            return None
        return _short_text(value, limit=limit)
    if isinstance(value, (list, tuple)):
        rendered: list[str] = []
        for item in value[:8]:
            if not isinstance(item, _SCALAR):
                continue
            text = "<blank>" if isinstance(item, str) and not item.strip() else _short_text(item, limit=90)
            if text:
                rendered.append(text)
        if not rendered:
            return "(none)" if len(value) == 0 else None
        suffix = f", +{len(value) - len(rendered)} more" if len(value) > len(rendered) else ""
        return ", ".join(rendered) + suffix
    return None


def _flatten_terminal_fields(fields: Mapping[str, Any]) -> dict[str, str]:
    """Flatten selected bounded fields for terminal/debug text without dumping payloads."""

    flattened: dict[str, str] = {}
    for raw_key, value in fields.items():
        key = _safe_field_name(raw_key)
        if not _field_is_safe(key):
            continue
        if isinstance(value, Mapping) and key in {
            "action_arguments",
            "provider_usage",
            "result_summary",
        }:
            prefix = {
                "action_arguments": "arg",
                "provider_usage": "usage",
                "result_summary": "result",
            }[key]
            for nested_key, nested_value in value.items():
                child = _safe_field_name(nested_key)
                combined = f"{prefix}_{child}"
                if not _field_is_safe(child):
                    continue
                rendered = _terminal_value(nested_value)
                if rendered is not None:
                    flattened[combined] = rendered
            continue
        rendered = _terminal_value(value)
        if rendered is not None:
            flattened[key] = rendered
    return flattened


def summarize_result(value: Any) -> dict[str, Any]:
    """Return bounded identity/status fields without logging file contents or prompts."""

    if not isinstance(value, Mapping):
        return {"result_type": type(value).__name__}
    preferred = (
        "status",
        "crew_status",
        "run_id",
        "plan_id",
        "issue_number",
        "issue_url",
        "branch",
        "commit",
        "head_commit",
        "checkout_path",
        "path",
        "next_action",
        "authority",
        "state",
        "phase",
        "candidate_sha256",
        "returncode",
        "clean",
        "count",
        "truncated",
        "classification",
        "human_revalidation_required",
        "test_platform",
        "test_filter",
        "pull_request_url",
        "evidence_commit",
        "merged_commit",
        "main_head",
        "record_id",
        "proposal_sha256",
    )
    summary: dict[str, Any] = {}
    for key in preferred:
        value_for_key = value.get(key)
        if isinstance(value_for_key, _SCALAR) and value_for_key not in (None, ""):
            summary[key] = value_for_key
    for key in (
        "paths",
        "matches",
        "events",
        "comments",
        "created_paths",
        "validation_manifests",
        "recovered_unity_churn",
    ):
        collection = value.get(key)
        if isinstance(collection, (list, tuple)):
            summary[f"{key}_count"] = len(collection)
    if not summary:
        summary["result_keys"] = sorted(str(key) for key in value)[:24]
    return summary


class ProgressSink(Protocol):
    def emit(self, event: str, message: str, **fields: Any) -> None: ...

    @contextmanager
    def heartbeat(
        self,
        event: str,
        message: str,
        *,
        interval_seconds: float | None = None,
        **fields: Any,
    ) -> Iterator[None]: ...

    def finish(self, status: str, **fields: Any) -> None: ...


class NullProgress:
    """No-op progress sink used by deterministic unit tests."""

    def emit(self, event: str, message: str, **fields: Any) -> None:
        return None

    @contextmanager
    def heartbeat(
        self,
        event: str,
        message: str,
        *,
        interval_seconds: float | None = None,
        **fields: Any,
    ) -> Iterator[None]:
        yield

    def finish(self, status: str, **fields: Any) -> None:
        return None


class ProgressLog:
    """Append-only progress journal with operator and technical text views."""

    def __init__(
        self,
        *,
        output_root: Path | str,
        task_id: str,
        worker_id: str,
        pipeline: str,
        heartbeat_seconds: float | None = None,
        run_id: str | None = None,
    ) -> None:
        self.task_id = str(task_id).strip()
        self.worker_id = str(worker_id).strip()
        self.pipeline = str(pipeline).strip()
        if not self.task_id or not self.worker_id or not self.pipeline:
            raise ValueError("task_id, worker_id, and pipeline must be non-empty")
        raw_interval = (
            heartbeat_seconds
            if heartbeat_seconds is not None
            else os.getenv("NSC_TASK_AGENT_HEARTBEAT_SECONDS", "15")
        )
        self.heartbeat_seconds = float(raw_interval)
        if self.heartbeat_seconds <= 0:
            raise ValueError("heartbeat interval must be positive")
        verbosity = os.getenv("NSC_TASK_AGENT_LOG_VERBOSITY", "operator").strip().casefold()
        if verbosity not in {"operator", "debug"}:
            raise ValueError("NSC_TASK_AGENT_LOG_VERBOSITY must be operator or debug")
        self.verbosity = verbosity
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        self.run_id = run_id or (
            f"{timestamp}-{_component(self.worker_id, fallback='worker')[-24:]}-"
            f"{uuid.uuid4().hex[:8]}"
        )
        root = Path(output_root).expanduser().resolve()
        self.run_dir = root / _component(self.task_id, fallback="task") / _component(
            self.run_id,
            fallback="run",
        )
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.text_path = self.run_dir / "progress.log"
        self.debug_path = self.run_dir / "debug.log"
        self.events_path = self.run_dir / "progress.jsonl"
        self.metadata_path = self.run_dir / "run.json"
        self._lock = threading.RLock()
        self._sequence = 0
        self._started_monotonic = time.monotonic()
        metadata = {
            "schema_version": PROGRESS_SCHEMA_VERSION,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "pipeline": self.pipeline,
            "started_at_utc": utc_now(),
            "heartbeat_seconds": self.heartbeat_seconds,
            "log_verbosity": self.verbosity,
            "progress_log": str(self.text_path),
            "debug_log": str(self.debug_path),
            "events_log": str(self.events_path),
        }
        self.metadata_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        self.emit(
            "run_started",
            f"Game Task Agent {self.pipeline} run started",
            run_id=self.run_id,
            worker_id=self.worker_id,
        )
        self.emit("log_ready", f"Operator progress log: {self.text_path}")
        self.emit("debug_log_ready", f"Full technical log: {self.debug_path}")
        self.emit(
            "log_watch",
            "Watch progress from another PowerShell window with: "
            f"Get-Content -Wait -LiteralPath '{self.text_path}'",
        )

    def emit(self, event: str, message: str, **fields: Any) -> None:
        event_name = _component(event, fallback="event").casefold()
        clean_message = _short_text(message, limit=1200)
        with self._lock:
            self._sequence += 1
            timestamp = utc_now()
            record = {
                "schema_version": PROGRESS_SCHEMA_VERSION,
                "sequence": self._sequence,
                "timestamp_utc": timestamp,
                "elapsed_seconds": round(time.monotonic() - self._started_monotonic, 3),
                "run_id": self.run_id,
                "task_id": self.task_id,
                "worker_id": self.worker_id,
                "pipeline": self.pipeline,
                "event": event_name,
                "message": clean_message,
                "fields": _safe_json(fields),
            }
            terminal_fields = _flatten_terminal_fields(fields)
            rendered_fields = " ".join(
                f"{key}={_short_text(value, limit=180)}"
                for key, value in terminal_fields.items()
            )
            debug_line = (
                f"[{timestamp}] [{self.task_id}] [{event_name}] {clean_message}"
                + (f" | {rendered_fields}" if rendered_fields else "")
            )
            operator_label = _OPERATOR_LABELS.get(event_name, event_name.replace("_", " ").upper())
            operator_line = (
                f"[{timestamp}] [{self.task_id}] [{operator_label}] {clean_message}"
                + (f" | {rendered_fields}" if rendered_fields else "")
            )
            with self.debug_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(debug_line + "\n")
                handle.flush()
            with self.events_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\n"
                )
                handle.flush()
            visible = self.verbosity == "debug" or event_name not in _TECHNICAL_ONLY_EVENTS
            if visible:
                line = debug_line if self.verbosity == "debug" else operator_line
                with self.text_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line + "\n")
                    handle.flush()
                print(line, file=sys.stderr, flush=True)

    @contextmanager
    def heartbeat(
        self,
        event: str,
        message: str,
        *,
        interval_seconds: float | None = None,
        **fields: Any,
    ) -> Iterator[None]:
        interval = self.heartbeat_seconds if interval_seconds is None else float(interval_seconds)
        if interval <= 0:
            raise ValueError("heartbeat interval must be positive")
        started = time.monotonic()
        stop = threading.Event()
        self.emit(f"{event}_started", message, **fields)

        def pulse() -> None:
            while not stop.wait(interval):
                try:
                    self.emit(
                        f"{event}_heartbeat",
                        f"{message} — still running",
                        elapsed_seconds=round(time.monotonic() - started, 1),
                        **fields,
                    )
                except Exception:
                    return

        thread = threading.Thread(
            target=pulse,
            name=f"task-agent-heartbeat-{_component(event, fallback='event')}",
            daemon=True,
        )
        thread.start()
        try:
            yield
        except BaseException as exc:
            self.emit(
                f"{event}_failed",
                f"{message} failed: {_short_text(exc, limit=700)}",
                duration_seconds=round(time.monotonic() - started, 3),
                error_type=type(exc).__name__,
                **fields,
            )
            raise
        else:
            self.emit(
                f"{event}_completed",
                f"{message} completed",
                duration_seconds=round(time.monotonic() - started, 3),
                **fields,
            )
        finally:
            stop.set()
            thread.join(timeout=max(1.0, min(interval, 5.0)))

    def finish(self, status: str, **fields: Any) -> None:
        self.emit(
            "run_finished",
            f"Game Task Agent run finished with status {status}",
            status=status,
            **fields,
        )
