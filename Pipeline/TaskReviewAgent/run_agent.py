#!/usr/bin/env python3
"""Run the explicit-task TaskReviewAgent development slices."""

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
    assess_goal_state,
    run_scripted_vertical_slice,
)
from Pipeline.TaskReviewAgent.openai_agent import (  # noqa: E402
    OpenAIAgentsUnavailable,
    describe_runtime,
    run_openai_fake_agent,
    run_openai_real_observation,
)
from Pipeline.TaskReviewAgent.real_observation import (  # noqa: E402
    RealObservationError,
    RealTaskObserver,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument(
        "--mode",
        choices=(
            "scripted",
            "openai-fake",
            "observe-real",
            "openai-observe-real",
        ),
        default="scripted",
        help=(
            "scripted and openai-fake retain the fake end-to-end vertical slice; "
            "observe-real reads actual committed Git/TaskGraph facts without an API call; "
            "openai-observe-real lets OpenAI classify the next action from those real "
            "read-only facts"
        ),
    )
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--model")
    parser.add_argument("--max-turns", type=int, default=24)
    return parser


def fake_report(
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
        "observation_authority": "simulated",
        "downstream_authority": "simulated",
        "authority": "review_only_not_applied",
    }


def real_observation_report(
    *,
    mode: str,
    observer: RealTaskObserver,
    observation: dict[str, Any],
    agent_assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assessment = assess_goal_state(observation)
    return {
        "schema_version": "1.0",
        "mode": mode,
        "runtime": describe_runtime(),
        "observation": observation,
        "deterministic_assessment": {
            "next_action": assessment.action.value,
            "reasons": list(assessment.reasons),
        },
        "agent_assessment": agent_assessment,
        "action_log": list(observer.action_log),
        "observation_authority": "real_read_only",
        "downstream_authority": "not_exposed",
        "authority": "observation_only",
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = TaskReviewRequest(args.task_id)

        if args.mode in ("scripted", "openai-fake"):
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
            payload = fake_report(mode=args.mode, outcome=outcome, tools=tools)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0 if outcome.status is OutcomeStatus.HUMAN_REVIEW_READY else 1

        observer = RealTaskObserver(args.source, request.task_id)
        if args.mode == "observe-real":
            observation = observer.observe_goal_state()
            payload = real_observation_report(
                mode=args.mode,
                observer=observer,
                observation=observation,
            )
        else:
            agent_assessment = run_openai_real_observation(
                request,
                observer,
                model=args.model,
                max_turns=args.max_turns,
            )
            assert observer.last_observation is not None
            payload = real_observation_report(
                mode=args.mode,
                observer=observer,
                observation=observer.last_observation,
                agent_assessment=agent_assessment,
            )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (
        TaskReviewContractError,
        RealObservationError,
        OpenAIAgentsUnavailable,
        OSError,
    ) as exc:
        print(f"TASK REVIEW AGENT: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
