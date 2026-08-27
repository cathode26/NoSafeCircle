#!/usr/bin/env python3
"""Run the goal-oriented task pipeline through human validation and closeout."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    TaskReviewContractError,
    TaskReviewRequest,
)
from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
)
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    ResumableDownstreamTaskController,
)
from Pipeline.TaskReviewAgent.generic_selection import (  # noqa: E402
    GenericSelectionError,
    select_agent_ready_task,
)
from Pipeline.TaskReviewAgent.openai_agent import (  # noqa: E402
    OpenAIAgentsUnavailable,
    describe_runtime,
)
from Pipeline.TaskReviewAgent.openai_downstream import (  # noqa: E402
    OpenAIDownstreamPipelineError,
    run_openai_downstream_pipeline,
)
from Pipeline.TaskReviewAgent.openai_pipeline import (  # noqa: E402
    run_openai_production_pipeline,
)
from Pipeline.TaskReviewAgent.production_pipeline import (  # noqa: E402
    ProductionTaskController,
)
from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow  # noqa: E402


_DOWNSTREAM_PHASES = {"delivery_evidence", "merge_closeout"}


def default_worker_id() -> str:
    host = "".join(
        character if character.isalnum() else "-"
        for character in socket.gethostname().casefold()
    ).strip("-") or "host"
    return f"task-review-agent-{host}-{uuid.uuid4().hex[:10]}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task-id",
        help=(
            "Explicit NSC-### task. Omit to resume the first fully validated "
            "nsc-state:agent-ready Issue."
        ),
    )
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--checkout-root", type=Path)
    parser.add_argument(
        "--worker-id",
        default=os.getenv("TASK_REVIEW_AGENT_WORKER_ID") or default_worker_id(),
    )
    parser.add_argument(
        "--execution-provider",
        choices=("claude", "codex"),
        default=os.getenv("TASK_REVIEW_EXECUTION_PROVIDER", "claude"),
    )
    parser.add_argument("--unity-executable")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--max-turns", type=int, default=120)
    parser.add_argument(
        "--mode",
        choices=("openai", "observe"),
        default="openai",
        help="openai drives the current Issue phase; observe reads without mutations",
    )
    return parser


def _workflow_state(observation: dict) -> dict:
    coordination = observation.get("coordination") or {}
    state = coordination.get("workflow_state")
    return state if isinstance(state, dict) else {}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        selection = None
        if args.task_id:
            request = TaskReviewRequest(args.task_id)
        else:
            selection = select_agent_ready_task(
                source=args.source,
                worker_id=args.worker_id,
            )
            request = TaskReviewRequest(selection["task_id"])

        workflow = RealTaskReviewWorkflow(
            source=args.source,
            task_id=request.task_id,
            checkout_root=args.checkout_root,
            worker_id=args.worker_id,
        )
        routing_observation = workflow.observe_goal_state()
        state = _workflow_state(routing_observation)
        downstream = state.get("phase") in _DOWNSTREAM_PHASES

        if downstream:
            controller = ResumableDownstreamTaskController(
                workflow=workflow,
                unity_executable=args.unity_executable,
                output_root=args.output_root,
            )
            authority = "read_only_downstream_pipeline_observation"
        else:
            controller = ProductionTaskController(
                workflow=workflow,
                execution_provider=args.execution_provider,
            )
            authority = "read_only_production_pipeline_observation"

        if args.mode == "observe":
            result = {
                "schema_version": "1.0",
                "mode": args.mode,
                "selected_pipeline": "downstream" if downstream else "implementation",
                "selection": selection,
                "worker_id": args.worker_id,
                "execution_provider": args.execution_provider,
                "runtime": describe_runtime(),
                "observation": controller.observe(),
                "authority": authority,
            }
        elif downstream:
            outcome = run_openai_downstream_pipeline(
                request,
                controller,
                model=args.model,
                max_turns=args.max_turns,
            )
            result = {
                "schema_version": "1.0",
                "mode": args.mode,
                "selected_pipeline": "downstream",
                "selection": selection,
                "worker_id": args.worker_id,
                "runtime": describe_runtime(),
                "outcome": outcome,
            }
        else:
            outcome = run_openai_production_pipeline(
                request,
                controller,
                model=args.model,
                max_turns=args.max_turns,
            )
            result = {
                "schema_version": "1.0",
                "mode": args.mode,
                "selected_pipeline": "implementation",
                "selection": selection,
                "worker_id": args.worker_id,
                "execution_provider": args.execution_provider,
                "runtime": describe_runtime(),
                "outcome": outcome,
            }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (
        TaskReviewContractError,
        DownstreamPipelineError,
        GenericSelectionError,
        OpenAIAgentsUnavailable,
        OpenAIDownstreamPipelineError,
        OSError,
    ) as exc:
        print(f"GAME TASK AGENT: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
