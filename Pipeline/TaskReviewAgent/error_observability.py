"""Bounded controller exception telemetry; never execution authority."""
from __future__ import annotations

import re
from typing import Any


def safe_error_message(exc: BaseException) -> str:
    message = " ".join(str(exc).split())
    # Common credential-bearing forms can occur in subprocess/transport errors.
    message = re.sub(r"(?i)\b(bearer\s+)\S+", r"\1[redacted]", message)
    message = re.sub(r"(?i)\b(token|password|secret|api[_-]?key)(\s*[:=]\s*)\S+", r"\1\2[redacted]", message)
    message = re.sub(r"(?i)(https?://)[^\s/@]+:[^\s/@]+@", r"\1[redacted]@", message)
    message = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+)\b", "[redacted]", message)
    return message[:900] or type(exc).__name__


def record_autonomous_run_error(controller: Any, exc: BaseException, *, stage: str) -> None:
    fields = dict(exception_type=type(exc).__name__, message=safe_error_message(exc), stage=stage)
    timeline = controller.run_timeline
    if timeline is not None:
        timeline.record("autonomous_run_error", **fields)
    emitter = getattr(controller.scheduler, "events", None)
    if emitter is not None:
        try:
            emitter.emit("autonomous_run_error", run_id=controller.manifest.run_id, **fields)
        except (OSError, UnicodeError, ValueError):
            # Only telemetry write failures are tolerated here. The enclosing
            # controller still drains and re-raises the original run exception.
            pass
