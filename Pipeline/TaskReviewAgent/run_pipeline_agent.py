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
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.codex_supervisor import (  # noqa: E402
    describe_codex_runtime,
)
from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    TaskReviewContractError,
    TaskReviewRequest,
)
from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
)
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    DownstreamTaskReviewWorkflow,
    ResumableDownstreamTaskController,
)
from Pipeline.TaskReviewAgent.generic_selection import (  # noqa: E402
    GenericSelectionError,
    select_agent_ready_task,
)
from Pipeline.TaskReviewAgent.goal_loop_guard import (  # noqa: E402
    GuardedTaskController,
)
from Pipeline.TaskReviewAgent.issue_queue import repo_root  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowStoreError,
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
from Pipeline.TaskReviewAgent.progress import ProgressLog  # noqa: E402
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
        help=(
            "openai uses authenticated Codex CLI to drive the current Issue phase; "
            "observe reads without mutations"
        ),
    )
    return parser


def _workflow_state(observation: dict) -> dict:
    coordination = observation.get("coordination") or {}
    state = coordination.get("workflow_state")
    return state if isinstance(state, dict) else {}


def _managed_issue_phase(
    *,
    source: Path,
    task_id: str,
    worker_id: str,
) -> str | None:
    """Read the durable Issue before choosing the workflow eligibility policy."""

    root = repo_root(source.resolve())
    service = IssueWorkflowService(
        backend=GhIssueBackend(source_root=root),
        task_loader=lambda selected: {
            "id": selected,
            "exclusive_resources": [],
        },
        worker_id=worker_id,
    )
    snapshot = service.find(task_id)
    if snapshot is None:
        return None
    if not snapshot.valid:
        raise GenericSelectionError(
            "Managed Issue is invalid and cannot be routed: "
            + "; ".join(snapshot.reasons)
        )
    if not snapshot.managed or snapshot.state is None:
        return None
    return snapshot.state.phase.value


def _outcome_status(result: dict[str, Any]) -> str:
    outcome = result.get("outcome")
    if isinstance(outcome, dict) and isinstance(outcome.get("status"), str):
        return outcome["status"]
    return "succeeded"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    progress: ProgressLog | None = None
    try:
        selection = None
        if args.task_id:
            request = TaskReviewRequest(args.task_id)
            selected_phase = _managed_issue_phase(
                source=args.source,
                task_id=request.task_id,
                worker_id=args.worker_id,
            )
        else:
            print(
                "[task-agent] Reading the durable agent-ready Issue queue...",
                file=sys.stderr,
                flush=True,
            )
            selection = select_agent_ready_task(
                source=args.source,
                worker_id=args.worker_id,
            )
            request = TaskReviewRequest(selection["task_id"])
            selected_phase = selection.get("phase")

        downstream_selected = selected_phase in _DOWNSTREAM_PHASES
        workflow_type = (
            DownstreamTaskReviewWorkflow
            if downstream_selected
            else RealTaskReviewWorkflow
        )
        workflow = workflow_type(
            source=args.source,
            task_id=request.task_id,
            checkout_root=args.checkout_root,
            worker_id=args.worker_id,
        )
        pipeline_name = "downstream" if downstream_selected else "implementation"
        if args.mode == "openai":
            output_root = (
                args.output_root.resolve()
                if args.output_root is not None
                else workflow.base_observer.root.parent
                / ".task-review-agent"
                / "outputs"
            )
            progress = ProgressLog(
                output_root=output_root,
                task_id=request.task_id,
                worker_id=args.worker_id,
                pipeline=pipeline_name,
            )
            progress.emit(
                "routing_started",
                "Selecting the deterministic pipeline route from the durable Issue state",
                selected_phase=selected_phase,
                issue_number=(selection or {}).get("issue_number"),
            )
            with progress.heartbeat(
                "routing_observation",
                "Reading the durable Issue, TaskGraph, Git, and checkout state",
            ):
                routing_observation = workflow.observe_goal_state()
        else:
            routing_observation = workflow.observe_goal_state()

        state = _workflow_state(routing_observation)
        observed_phase = state.get("phase")
        downstream = observed_phase in _DOWNSTREAM_PHASES
        if progress is not None:
            progress.emit(
                "routing_completed",
                f"Selected {'downstream' if downstream else 'implementation'} pipeline",
                observed_phase=observed_phase,
                issue_state=state.get("state"),
            )

        if downstream_selected and not downstream:
            raise GenericSelectionError(
                "Managed Issue changed after selection and no longer has a "
                "downstream phase; rerun selection."
            )
        if downstream and not downstream_selected:
            raise GenericSelectionError(
                "Managed Issue entered a downstream phase during routing; rerun so "
                "the downstream eligibility policy is selected explicitly."
            )

        if downstream:
            controller: Any = ResumableDownstreamTaskController(
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

        if args.mode == "openai":
            controller = GuardedTaskController(controller, progress=progress)

        if args.mode == "observe":
            result = {
                "schema_version": "1.0",
                "mode": args.mode,
                "selected_pipeline": "downstream" if downstream else "implementation",
                "selection": selection,
                "worker_id": args.worker_id,
                "execution_provider": args.execution_provider,
                "runtime": describe_codex_runtime(),
                "observation": controller.observe(),
                "authority": authority,
            }
        elif downstream:
            outcome = run_openai_downstream_pipeline(
                request,
                controller,
                model=args.model,
                max_turns=args.max_turns,
                progress=progress,
            )
            result = {
                "schema_version": "1.0",
                "mode": args.mode,
                "selected_pipeline": "downstream",
                "selection": selection,
                "worker_id": args.worker_id,
                "runtime": describe_codex_runtime(),
                "outcome": outcome,
            }
        else:
            outcome = run_openai_production_pipeline(
                request,
                controller,
                model=args.model,
                max_turns=args.max_turns,
                progress=progress,
            )
            result = {
                "schema_version": "1.0",
                "mode": args.mode,
                "selected_pipeline": "implementation",
                "selection": selection,
                "worker_id": args.worker_id,
                "execution_provider": args.execution_provider,
                "runtime": describe_codex_runtime(),
                "outcome": outcome,
            }
        if progress is not None:
            progress.finish(_outcome_status(result))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (
        TaskReviewContractError,
        DownstreamPipelineError,
        GenericSelectionError,
        IssueWorkflowStoreError,
        OpenAIDownstreamPipelineError,
        OSError,
        ValueError,
    ) as exc:
        if progress is not None:
            progress.finish(
                "failed",
                error_type=type(exc).__name__,
                error=" ".join(str(exc).split())[:900],
            )
        print(f"GAME TASK AGENT: STOP\n{exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
