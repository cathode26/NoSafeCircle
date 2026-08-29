#!/usr/bin/env python3
"""Deterministic tests for operator progress, heartbeats, and durable debug logs."""

from __future__ import annotations

import io
import json
import os
import sys
import time
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.codex_supervisor import SupervisorDecision  # noqa: E402
from Pipeline.TaskReviewAgent.operator_logging import (  # noqa: E402
    remember_supervisor_decision_for_logging,
)
from Pipeline.TaskReviewAgent.progress import ProgressLog, summarize_result  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_operator_log_is_unity_friendly_and_diagnostic() -> None:
    prior = os.environ.get("NSC_TASK_AGENT_LOG_VERBOSITY")
    os.environ["NSC_TASK_AGENT_LOG_VERBOSITY"] = "operator"
    try:
        with TemporaryDirectory(prefix="task-agent-progress-") as text:
            terminal = io.StringIO()
            with redirect_stderr(terminal):
                progress = ProgressLog(
                    output_root=Path(text),
                    task_id="NSC-020",
                    worker_id="task-review-agent-test",
                    pipeline="downstream",
                    heartbeat_seconds=0.03,
                    run_id="progress-smoke",
                )
                with progress.heartbeat(
                    "state_observation",
                    "Reading deterministic downstream state",
                    turn=2,
                ):
                    time.sleep(0.01)
                progress.emit(
                    "state_observed",
                    "Deterministic downstream state read",
                    turn=2,
                    issue_state="agent_working",
                    phase="delivery_evidence",
                    next_action="run_authoritative_unity_test",
                    checkout_status="ready",
                    issue_number=64,
                )

                search = SupervisorDecision(
                    "NSC-020",
                    "search_repository",
                    {
                        "query": "Unity testing policy",
                        "prefixes": ["", "Docs/Engineering/"],
                        "limit": 100,
                    },
                    "Find the relevant policy.",
                )
                remember_supervisor_decision_for_logging(
                    search,
                    usage={
                        "input_tokens": 123,
                        "output_tokens": 45,
                        "cache_read_input_tokens": 67,
                    },
                )
                progress.emit(
                    "supervisor_decision",
                    "Codex selected search_repository",
                    turn=2,
                    action="search_repository",
                    rationale=search.rationale,
                )
                try:
                    with progress.heartbeat(
                        "pipeline_action",
                        "Executing search_repository",
                        turn=2,
                        action="search_repository",
                    ):
                        raise RuntimeError("repository prefix must be non-empty")
                except RuntimeError:
                    pass
                progress.emit(
                    "action_rejected",
                    "search_repository was rejected by deterministic validation",
                    turn=2,
                    action="search_repository",
                    error_type="DownstreamPipelineError",
                    error="repository prefix must be non-empty",
                )

                unity = SupervisorDecision(
                    "NSC-020",
                    "run_authoritative_unity_test",
                    {
                        "test_platform": "PlayMode",
                        "test_filter": (
                            "NoSafeCircle.DoorPrototype.Tests."
                            "DoorInteractionPlayModeTests"
                        ),
                    },
                    "Run the committed focused tests.",
                )
                remember_supervisor_decision_for_logging(
                    unity,
                    usage={"input_tokens": 200, "output_tokens": 30},
                )
                progress.emit(
                    "supervisor_decision",
                    "Codex selected run_authoritative_unity_test",
                    turn=3,
                    action="run_authoritative_unity_test",
                    rationale=unity.rationale,
                )
                with progress.heartbeat(
                    "pipeline_action",
                    "Executing run_authoritative_unity_test",
                    turn=3,
                    action="run_authoritative_unity_test",
                ):
                    time.sleep(0.07)
                progress.emit(
                    "action_completed",
                    "run_authoritative_unity_test completed",
                    turn=3,
                    action="run_authoritative_unity_test",
                    result_summary=summarize_result(
                        {
                            "status": "passed",
                            "test_platform": "PlayMode",
                            "test_filter": unity.arguments["test_filter"],
                            "commit": "a" * 40,
                            "secret_prompt": "must-not-be-logged",
                        }
                    ),
                )
                progress.finish("human_delivery_review")

            rendered = terminal.getvalue()
            require("[STATE]" in rendered, "terminal omitted operator state label")
            require("Delivery evidence" in rendered, "terminal omitted friendly phase")
            require("Unity checkout: ready" in rendered, "terminal omitted checkout meaning")
            require("[PLAN]" in rendered, "terminal omitted plan label")
            require(
                "Search project code and documentation" in rendered,
                "terminal omitted friendly search action",
            )
            require("arg_query=Unity testing policy" in rendered, "search query was not logged")
            require("<blank>, Docs/Engineering/" in rendered, "malformed prefixes were hidden")
            require("usage_input_tokens=123" in rendered, "provider usage was not logged")
            require("[BLOCKED]" in rendered, "terminal omitted blocked label")
            require(
                "The agent sent a blank search folder" in rendered,
                "terminal omitted actionable error hint",
            )
            require("Run Unity PlayMode tests" in rendered, "Unity action is not readable")
            require(
                "DoorInteractionPlayModeTests" in rendered,
                "Unity test filter was not logged",
            )
            require("result_status=passed" in rendered, "result status stayed hidden")
            require("result_test_platform=PlayMode" in rendered, "test platform stayed hidden")
            require(
                "state_observation_started" not in rendered,
                "technical state event cluttered the operator terminal",
            )
            require("must-not-be-logged" not in rendered, "terminal leaked unselected result data")

            run_dir = Path(text) / "NSC-020" / "progress-smoke"
            text_log = (run_dir / "progress.log").read_text(encoding="utf-8")
            debug_log = (run_dir / "debug.log").read_text(encoding="utf-8")
            require("[WORK]" in text_log, "operator log omitted working state")
            require("still working" in text_log.casefold(), "operator log omitted heartbeat")
            require(
                "state_observation_started" not in text_log,
                "operator log contains technical-only events",
            )
            require(
                "state_observation_started" in debug_log,
                "debug log omitted technical event",
            )
            require(
                "pipeline_action_failed" in debug_log,
                "debug log omitted the original failing stage",
            )

            metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            require(metadata["log_verbosity"] == "operator", "run metadata omitted verbosity")
            require(metadata["debug_log"].endswith("debug.log"), "run metadata omitted debug log")

            events = [
                json.loads(line)
                for line in (run_dir / "progress.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            require(len(events) >= 15, "too few durable progress events")
            require(
                [event["sequence"] for event in events] == list(range(1, len(events) + 1)),
                "progress event sequence is not contiguous",
            )
            decision_events = [
                event for event in events if event["event"] == "supervisor_decision"
            ]
            require(decision_events, "JSONL omitted supervisor decisions")
            require(
                decision_events[0]["fields"]["action_arguments"]["prefixes"][0] == "<blank>",
                "structured log did not preserve the sanitized blank argument",
            )
            require(
                events[-1]["fields"].get("status") == "human_delivery_review",
                "final status was not persisted",
            )
    finally:
        if prior is None:
            os.environ.pop("NSC_TASK_AGENT_LOG_VERBOSITY", None)
        else:
            os.environ["NSC_TASK_AGENT_LOG_VERBOSITY"] = prior


def test_result_summary_is_bounded() -> None:
    summary = summarize_result(
        {
            "status": "review_ready",
            "run_id": "run-123",
            "candidate_sha256": "a" * 64,
            "paths": ["one", "two"],
            "prompt": "do not persist this",
            "file_contents": "do not persist this either",
        }
    )
    require(summary["status"] == "review_ready", "status missing from summary")
    require(summary["run_id"] == "run-123", "run identity missing from summary")
    require(summary["paths_count"] == 2, "safe collection count missing")
    require("prompt" not in summary, "prompt leaked into summary")
    require("file_contents" not in summary, "file contents leaked into summary")


def main() -> int:
    tests = (
        test_operator_log_is_unity_friendly_and_diagnostic,
        test_result_summary_is_bounded,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent progress logging tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
