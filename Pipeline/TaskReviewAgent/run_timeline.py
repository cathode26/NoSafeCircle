"""The controller's own durable, timestamped run-lifecycle journal.

The scheduler already keeps an append-only journal with a UTC timestamp on
every record, so worker and architect timing survive the process. Two facts
sit above the scheduler and were therefore not durable anywhere: when the
autonomous controller began this run, and when it reached graph completion.
The graph-complete receipt proves completion happened but carries no time,
and a file modification time is not evidence.

This module adds the smallest durable record that closes that gap: an
append-only ``run_timeline.jsonl`` beside the run's other artifacts, one JSON
object per line, each carrying ``timestamp_utc`` and the exact ``run_id``.

It is deliberately a separate file rather than a new field on the manifest,
progress, or receipt. Those three are strictly validated as exact objects and
the receipt is hash-bound, so widening any of them would invalidate every
artifact an earlier run already wrote. A new append-only file changes no
existing schema, so an old run stays readable and a new run simply carries
more evidence. A reader that finds no timeline reports the timestamps as
unavailable rather than inferring them.

Appending is best effort by design. A run must not fail because its own
bookkeeping could not be written, so a write failure is swallowed and the
missing record is later reported as unavailable, which is the truthful
outcome.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

RUN_TIMELINE_SCHEMA_VERSION = "1.0"

#: The controller reached its first step for this run.
RUN_STARTED_EVENT = "autonomous_run_started"
#: The controller durably saved a graph-complete receipt.
GRAPH_COMPLETE_EVENT = "graph_complete_receipt_written"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class RunTimelineJournal:
    """Append-only run-lifecycle records for exactly one run."""

    def __init__(self, path: Path | str, *, run_id: str) -> None:
        if type(run_id) is not str or not run_id.strip():
            raise ValueError("run timeline requires an exact run_id")
        self.path = Path(path)
        self.run_id = run_id

    def record(self, event: str, **fields: Any) -> bool:
        """Append one timestamped record. Returns whether it was written.

        Never raises: the run's own progress must not depend on the success of
        its bookkeeping. An unwritten record becomes an explicit
        ``unavailable`` in the evidence report instead of a silent guess.
        """

        payload = {
            "schema_version": RUN_TIMELINE_SCHEMA_VERSION,
            "timestamp_utc": utc_now(),
            "run_id": self.run_id,
            "event": str(event),
            "pid": os.getpid(),
        }
        for key, value in fields.items():
            if key in payload:
                continue
            try:
                json.dumps(value, allow_nan=False)
            except (TypeError, ValueError):
                value = str(value)
            payload[key] = value
        try:
            line = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n"
        except (TypeError, ValueError):
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()
        except (OSError, UnicodeError):
            return False
        return True

    def record_run_started(self, **fields: Any) -> bool:
        return self.record(RUN_STARTED_EVENT, **fields)

    def record_graph_complete(self, **fields: Any) -> bool:
        return self.record(GRAPH_COMPLETE_EVENT, **fields)


__all__ = [
    "GRAPH_COMPLETE_EVENT",
    "RUN_STARTED_EVENT",
    "RUN_TIMELINE_SCHEMA_VERSION",
    "RunTimelineJournal",
    "utc_now",
]
