#!/usr/bin/env python3
"""Run the first explicit-task TaskReviewAgent vertical slice."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    OutcomeStatus,
    TaskReviewContractError,
    TaskReviewRequest,
)
from Pipeline.TaskReviewAgent.fake_tools import FakeTaskFixture, FakeTaskReviewTools  # noqa: E402
from Pipeline.TaskReviewAgent.goal_loop import (  # noqa: E402
    ScriptedScopePlanner,
    run_scripted_vertical_slice,
)
from Pipeline.TaskReviewAgent.openai_agent import (  # noqa: E402
    OpenAIAgentsUnavailable,
    describe_runtime,
    run_openai_fake_agent,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument(
        "--mode",
        choices=("scripted", "openai-fake"),
        default="scripted",
        help=(
            "scripted proves the deterministic fake vertical slice without an API call; "
            "openai-fake lets a real OpenAI agent navigate the same fake tools"
        ),
    )
    parser.add_argument("--model")
    parser.add_argument("--max-turns", type=int, default=24)
    return parser


def report(
    *,
    mode: str,
    outcome: Any,
    tools: FakeTaskReviewTools,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "mode": mode,
        "runtime": describe_runtime(),
        "outcome": outcome.to_dict(),
        "action_log": list(tools.action_log),
        "authority": "review_only_not_applied",
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = TaskReviewRequest(args.task_id)
        fixture = FakeTaskFixture(task_id=request.task_id)
        tools = FakeTaskReviewTools(fixture)
        if args.mode == "scripted":
            outcome = run_scripted_vertical_slice(
                request,
                tools,
                ScriptedScopePlanner(),
            )
        else:
            outcome = run_openai_fake_agent(
                request,
                tools,
                model=args.model,
                max_turns=args.max_turns,
            )
        payload = report(mode=args.mode, outcome=outcome, tools=tools)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if outcome.status is OutcomeStatus.HUMAN_REVIEW_READY else 1
    except (TaskReviewContractError, OpenAIAgentsUnavailable, OSError) as exc:
        print(f"TASK REVIEW AGENT: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
