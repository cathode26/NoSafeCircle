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


PROGRESS_SCHEMA_VERSION = "1.0"
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]+")
_SCALAR = (str, int, float, bool, type(None))


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
    )
    summary: dict[str, Any] = {}
    for key in preferred:
        value_for_key = value.get(key)
        if isinstance(value_for_key, _SCALAR) and value_for_key not in (None, ""):
            summary[key] = value_for_key
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
    """Append-only progress journal that also prints concise live status to stderr."""

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
            "progress_log": str(self.text_path),
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
        self.emit("log_ready", f"Live progress log: {self.text_path}")
        self.emit(
            "log_watch",
            "Watch from another PowerShell window with: "
            f"Get-Content -Wait -LiteralPath '{self.text_path}'",
        )

    def emit(self, event: str, message: str, **fields: Any) -> None:
        event_name = _component(event, fallback="event").casefold()
        clean_message = _short_text(message, limit=1200)
        with self._lock:
            self._sequence += 1
            record = {
                "schema_version": PROGRESS_SCHEMA_VERSION,
                "sequence": self._sequence,
                "timestamp_utc": utc_now(),
                "elapsed_seconds": round(time.monotonic() - self._started_monotonic, 3),
                "run_id": self.run_id,
                "task_id": self.task_id,
                "worker_id": self.worker_id,
                "pipeline": self.pipeline,
                "event": event_name,
                "message": clean_message,
                "fields": _safe_json(fields),
            }
            terminal_fields = " ".join(
                f"{key}={_short_text(value, limit=140)}"
                for key, value in fields.items()
                if isinstance(value, _SCALAR) and value not in (None, "")
            )
            line = (
                f"[{record['timestamp_utc']}] [{self.task_id}] "
                f"[{event_name}] {clean_message}"
                + (f" | {terminal_fields}" if terminal_fields else "")
            )
            with self.text_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
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
