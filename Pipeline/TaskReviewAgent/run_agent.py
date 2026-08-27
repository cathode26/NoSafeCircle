#!/usr/bin/env python3
"""Run the explicit-task TaskReviewAgent development slices."""

from __future__ import annotations

import argparse
import json
import os
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
    GoalAction,
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
from Pipeline.TaskReviewAgent.openai_checkout import (  # noqa: E402
    run_openai_real_checkout,
)
from Pipeline.TaskReviewAgent.real_checkout import RealCheckoutError  # noqa: E402
from Pipeline.TaskReviewAgent.real_observation import (  # noqa: E402
    RealObservationError,
    RealTaskObserver,
)
from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow  # noqa: E402


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
            "checkout-real",
            "openai-checkout-real",
        ),
        default="scripted",
        help=(
            "scripted/openai-fake retain the fake end-to-end regression; "
            "observe-real/openai-observe-real read committed Git/TaskGraph facts only; "
            "checkout-real/openai-checkout-real additionally inspect GitHub claim state "
            "and may create or resume the canonical checkout only when it is already "
            "claimed by the selected worker"
        ),
    )
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--checkout-root", type=Path)
    parser.add_argument(
        "--worker-id",
        default=os.getenv("TASK_REVIEW_AGENT_WORKER_ID", "task-review-agent"),
    )
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


def real_checkout_report(
    *,
    mode: str,
    workflow: RealTaskReviewWorkflow,
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
        "checkout_preparation": workflow.last_checkout_result,
        "action_log": list(workflow.action_log),
        "observation_authority": "real_read_only",
        "github_authority": "read_only_claim_inspection",
        "checkout_authority": "create_or_resume_after_existing_claim",
        "downstream_authority": "not_exposed",
        "authority": "checkout_preparation_only",
    }


def run_deterministic_checkout(
    workflow: RealTaskReviewWorkflow,
) -> dict[str, Any]:
    observation = workflow.observe_goal_state()
    assessment = assess_goal_state(observation)
    if assessment.action is GoalAction.PREPARE_CHECKOUT:
        workflow.prepare_task_checkout()
        observation = workflow.observe_goal_state()
    return observation


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

        if args.mode in ("observe-real", "openai-observe-real"):
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

        workflow = RealTaskReviewWorkflow(
            source=args.source,
            task_id=request.task_id,
            checkout_root=args.checkout_root,
            worker_id=args.worker_id,
        )
        if args.mode == "checkout-real":
            observation = run_deterministic_checkout(workflow)
            payload = real_checkout_report(
                mode=args.mode,
                workflow=workflow,
                observation=observation,
            )
        else:
            agent_assessment = run_openai_real_checkout(
                request,
                workflow,
                model=args.model,
                max_turns=args.max_turns,
            )
            assert workflow.last_observation is not None
            payload = real_checkout_report(
                mode=args.mode,
                workflow=workflow,
                observation=workflow.last_observation,
                agent_assessment=agent_assessment,
            )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (
        TaskReviewContractError,
        RealObservationError,
        RealCheckoutError,
        OpenAIAgentsUnavailable,
        OSError,
    ) as exc:
        print(f"TASK REVIEW AGENT: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
