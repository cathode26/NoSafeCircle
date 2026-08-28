#!/usr/bin/env python3
"""Deterministic tests for terminal progress, heartbeats, and durable logs."""

from __future__ import annotations

import io
import json
import sys
import time
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.progress import ProgressLog, summarize_result  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_terminal_and_durable_heartbeat() -> None:
    with TemporaryDirectory(prefix="task-agent-progress-") as text:
        terminal = io.StringIO()
        with redirect_stderr(terminal):
            progress = ProgressLog(
                output_root=Path(text),
                task_id="NSC-020",
                worker_id="task-review-agent-test",
                pipeline="implementation",
                heartbeat_seconds=0.03,
                run_id="progress-smoke",
            )
            with progress.heartbeat(
                "codex_supervisor",
                "Codex is choosing the next bounded action",
                turn=1,
            ):
                time.sleep(0.09)
            progress.emit(
                "action_completed",
                "Completed prepare_task_checkout",
                action="prepare_task_checkout",
                result_summary=summarize_result(
                    {
                        "status": "ready",
                        "path": "C:/UnityProjects/NoSafeCircleAgentCrew/NSC-020",
                        "secret_prompt": "must-not-be-logged",
                    }
                ),
            )
            progress.finish("human_action_required")

        rendered = terminal.getvalue()
        require("codex_supervisor_started" in rendered, "terminal omitted stage start")
        require("codex_supervisor_heartbeat" in rendered, "terminal omitted heartbeat")
        require("codex_supervisor_completed" in rendered, "terminal omitted completion")
        require("Get-Content -Wait" in rendered, "terminal omitted tail command")

        run_dir = Path(text) / "NSC-020" / "progress-smoke"
        text_log = (run_dir / "progress.log").read_text(encoding="utf-8")
        require("still running" in text_log, "durable log omitted heartbeat")
        require("prepare_task_checkout" in text_log, "durable log omitted action")
        require("must-not-be-logged" not in text_log, "terminal log leaked unselected result data")

        events = [
            json.loads(line)
            for line in (run_dir / "progress.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        require(len(events) >= 8, "too few durable progress events")
        require(
            [event["sequence"] for event in events] == list(range(1, len(events) + 1)),
            "progress event sequence is not contiguous",
        )
        require(
            any(event["event"] == "codex_supervisor_heartbeat" for event in events),
            "JSONL omitted heartbeat event",
        )
        require(
            events[-1]["fields"].get("status") == "human_action_required",
            "final status was not persisted",
        )


def test_result_summary_is_bounded() -> None:
    summary = summarize_result(
        {
            "status": "review_ready",
            "run_id": "run-123",
            "candidate_sha256": "a" * 64,
            "prompt": "do not persist this",
            "file_contents": "do not persist this either",
        }
    )
    require(summary["status"] == "review_ready", "status missing from summary")
    require(summary["run_id"] == "run-123", "run identity missing from summary")
    require("prompt" not in summary, "prompt leaked into summary")
    require("file_contents" not in summary, "file contents leaked into summary")


def main() -> int:
    tests = (
        test_terminal_and_durable_heartbeat,
        test_result_summary_is_bounded,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent progress logging tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
