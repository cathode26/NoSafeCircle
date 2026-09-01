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
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    TaskReviewContractError,
    TaskReviewRequest,
)
from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
)
from Pipeline.TaskReviewAgent.dispatch_plan import (  # noqa: E402
    TaskcontrolStateObservationError,
    build_dispatch_plan,
    evaluate_committed_fresh_candidate,
)
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    DownstreamTaskReviewWorkflow,
    ResumableDownstreamTaskController,
)
from Pipeline.TaskReviewAgent.fresh_dispatch import (  # noqa: E402
    resolve_generic_dispatch_with_contention_retry,
)
from Pipeline.TaskReviewAgent.generic_selection import (  # noqa: E402
    GenericSelectionError,
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
            "Explicit NSC-### task. Omit to resume existing actionable work "
            "first; otherwise select and safely start one fresh Stage 2 "
            "implementation candidate."
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
        task_loader=lambda selected: load_committed_task(root, selected),
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


def _require_explicit_fresh_admission(
    *,
    source: Path,
    task_id: str,
    worker_id: str,
    selected_phase: str | None,
) -> None:
    """Gate an explicit fresh ``-TaskId`` through the same Stage 2 safety
    kernel generic dispatch uses, so an explicit ask cannot bypass
    eligibility/dependency/resource checks generic dispatch enforces.

    A ``selected_phase`` that is not ``None`` means a managed Issue already
    exists for this task: that is a legitimate RESUME and must never be
    routed through fresh evaluation as though it were new work, so this
    function returns immediately without consulting the Stage 2 kernel. A
    blocked explicit task is reported for THIS exact task_id; it is never
    silently substituted for another candidate.
    """

    if selected_phase is not None:
        return
    try:
        evaluation = evaluate_committed_fresh_candidate(
            source=source,
            task_id=task_id,
            worker_id=worker_id,
        )
    except TaskcontrolStateObservationError as exc:
        # A failed bulk snapshot is a global operational failure, not an
        # eligibility fact about this task. Surface the bounded concrete
        # reason instead of a bare per-task state_lookup_failed rejection.
        raise GenericSelectionError(
            f"authoritative TaskGraph state observation failed: {exc}"
        ) from exc
    if not evaluation.eligible:
        raise GenericSelectionError(
            f"{task_id} is not safe fresh implementation work: "
            + "; ".join(evaluation.reason_codes)
        )


def _outcome_status(result: dict[str, Any]) -> str:
    """Report the pipeline outcome literally; never default to success.

    A run whose outcome is missing or malformed did not prove successful work.
    Observation-only runs report that they observed, nothing more.
    """

    outcome = result.get("outcome")
    if isinstance(outcome, dict) and isinstance(outcome.get("status"), str):
        return outcome["status"]
    if result.get("mode") == "observe":
        return "observed"
    return "unknown_outcome"


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
            if args.mode != "observe":
                # Observe mode is a read-only diagnostic: an operator must be
                # able to inspect an explicit task's current state even when
                # it would not be safe/eligible fresh mutation admission.
                # Only a mutating mode enforces the Stage 2 safety kernel
                # before continuing.
                _require_explicit_fresh_admission(
                    source=args.source,
                    task_id=request.task_id,
                    worker_id=args.worker_id,
                    selected_phase=selected_phase,
                )
        elif args.mode == "observe":
            # observe mode must never mutate or retry. Stage 4's
            # resolve_generic_dispatch_with_contention_retry crosses a real
            # mutation boundary (Stage 1 claim + durable Issue
            # creation/acquisition) on every attempt it makes, so a
            # no-TaskId observe run stops at the read-only Stage 2 plan
            # instead of calling it at all.
            plan = build_dispatch_plan(source=args.source, worker_id=args.worker_id)
            result = {
                "schema_version": "1.0",
                "mode": args.mode,
                "selected_pipeline": None,
                "dispatch_plan": plan.to_dict(),
                "worker_id": args.worker_id,
                "runtime": describe_codex_runtime(),
                "authority": "read_only_dispatch_plan_observation",
            }
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        else:
            print(
                "[task-agent] Resolving generic dispatch: resume existing durable "
                "work, otherwise select one currently safe Stage 2 fresh candidate "
                "(retrying another candidate after ordinary claim contention)...",
                file=sys.stderr,
                flush=True,
            )
            dispatch_result = resolve_generic_dispatch_with_contention_retry(
                source=args.source,
                worker_id=args.worker_id,
                checkout_root=args.checkout_root,
            )
            if dispatch_result.decision == "resume_existing":
                selection = dict(dispatch_result.resume or {})
                selection.setdefault(
                    "selection_priority", "resume_agent_ready_before_new_task"
                )
                request = TaskReviewRequest(dispatch_result.task_id)
                selected_phase = (dispatch_result.resume or {}).get("phase")
            elif dispatch_result.decision == "fresh_started":
                selection = {
                    "selection_priority": "stage3_fresh_dispatch",
                    "task_id": dispatch_result.task_id,
                    "contention_attempt_count": dispatch_result.contention_attempt_count,
                }
                request = TaskReviewRequest(dispatch_result.task_id)
                # A task that was just leased for the first time always
                # starts at the initial implementation phase.
                selected_phase = None
            else:
                # no_safe_work / blocked_invalid_state / claim_operational_error /
                # issue_initialization_blocked / lease_acquired_claim_cleanup_required:
                # report the typed Stage 4 outcome directly. Never invent or
                # substitute a task, and never treat no_safe_work as an error
                # requiring the human to pass an explicit -TaskId. Ordinary
                # claim_conflict never reaches here: Stage 4 already retried
                # it against another currently-safe candidate, or exhausted
                # the untried pool into no_safe_work.
                result = {
                    "schema_version": "1.0",
                    "mode": args.mode,
                    "selected_pipeline": None,
                    "generic_dispatch": dispatch_result.to_dict(),
                    "worker_id": args.worker_id,
                    "runtime": describe_codex_runtime(),
                    "authority": "generic_dispatch_resolution_only",
                }
                print(json.dumps(result, indent=2, sort_keys=True))
                return 0 if dispatch_result.decision == "no_safe_work" else 2

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
        status = _outcome_status(result)
        if progress is not None:
            progress.finish(status)
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.mode == "openai" and status == "unknown_outcome":
            # A run whose outcome is missing or malformed proved nothing.
            # It must terminate as a failure, never as successful work.
            print(
                "GAME TASK AGENT: STOP\n"
                "The pipeline finished without a usable outcome status; the run "
                "result is recorded above but cannot be treated as successful "
                "work.",
                file=sys.stderr,
                flush=True,
            )
            return 2
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
