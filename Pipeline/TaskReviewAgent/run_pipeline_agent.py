#!/usr/bin/env python3
"""Run the goal-oriented task pipeline to a committed human Unity handoff."""

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
from Pipeline.TaskReviewAgent.generic_selection import (  # noqa: E402
    GenericSelectionError,
    select_agent_ready_task,
)
from Pipeline.TaskReviewAgent.openai_agent import (  # noqa: E402
    OpenAIAgentsUnavailable,
    describe_runtime,
)
from Pipeline.TaskReviewAgent.openai_pipeline import (  # noqa: E402
    run_openai_production_pipeline,
)
from Pipeline.TaskReviewAgent.production_pipeline import (  # noqa: E402
    ProductionTaskController,
)
from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow  # noqa: E402


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
    parser.add_argument("--model")
    parser.add_argument("--max-turns", type=int, default=80)
    parser.add_argument(
        "--mode",
        choices=("openai", "observe"),
        default="openai",
        help="openai drives the full pipeline; observe reads state without mutations",
    )
    return parser


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
        controller = ProductionTaskController(
            workflow=workflow,
            execution_provider=args.execution_provider,
        )

        if args.mode == "observe":
            result = {
                "schema_version": "1.0",
                "mode": args.mode,
                "selection": selection,
                "worker_id": args.worker_id,
                "execution_provider": args.execution_provider,
                "runtime": describe_runtime(),
                "observation": controller.observe(),
                "authority": "read_only_production_pipeline_observation",
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
        GenericSelectionError,
        OpenAIAgentsUnavailable,
        OSError,
    ) as exc:
        print(f"GAME TASK AGENT: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
