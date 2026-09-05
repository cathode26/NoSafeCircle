#!/usr/bin/env python3
"""Run the goal-oriented task pipeline through human validation and closeout."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.codex_supervisor import (  # noqa: E402
    describe_codex_runtime,
    resolve_supervisor_model,
    resolve_supervisor_reasoning_effort,
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
from Pipeline.TaskReviewAgent.execution_routing import (  # noqa: E402
    OPENAI_REASONING_EFFORTS,
)
from Pipeline.TaskReviewAgent.progress import ProgressLog  # noqa: E402
from Pipeline.TaskReviewAgent.real_checkout import default_checkout_root  # noqa: E402
from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow  # noqa: E402
from Pipeline.TaskReviewAgent.supervisor_session_pool import (  # noqa: E402
    CODEX_RESUME_SANDBOX_ARGUMENT_ENVIRONMENT,
    SUPERVISOR_CONTEXT_WINDOW_ENVIRONMENT,
    CodexResumeActivation,
    SupervisorSessionOwner,
    SupervisorSessionPoolError,
    codex_resume_activation_from_environment,
    context_window_tokens_from_environment,
    gate_off_activation_state,
    validate_context_window_tokens,
)
from Pipeline.TaskReviewAgent.taskgraph_review_issues import (  # noqa: E402
    ReviewIssueMaterializationResult,
    materialize_taskgraph_review_issues,
    observe_taskgraph_review_snapshot,
)
from Pipeline.TaskReviewAgent.worker_result import (  # noqa: E402
    WorkerResultError,
    write_pipeline_result,
)


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
    parser.add_argument("--run-id")
    parser.add_argument("--admission-source-head")
    parser.add_argument("--task-contract-sha256")
    parser.add_argument("--admission-issue-number", type=int)
    parser.add_argument("--model")
    parser.add_argument(
        "--supervisor-reasoning-effort",
        choices=OPENAI_REASONING_EFFORTS,
    )
    parser.add_argument(
        "--execution-model",
        help="Explicit ExecutionCrew provider model; independent from --model.",
    )
    parser.add_argument(
        "--execution-reasoning-effort",
        choices=OPENAI_REASONING_EFFORTS,
        help="Explicit OpenAI/Codex ExecutionCrew reasoning effort.",
    )
    parser.add_argument("--crew-profile", choices=("lean", "standard", "full"))
    parser.add_argument(
        "--validation-profile",
        choices=("targeted", "task_specific", "full_relevant"),
    )
    parser.add_argument(
        "--enable-execution-session-pool",
        action="store_true",
        help="Scheduler-owned opt-in for production Claude ExecutionCrew pooling.",
    )
    parser.add_argument("--max-turns", type=int, default=120)
    parser.add_argument(
        "--supervisor-codex-resume-sandbox-argument",
        help=(
            "JSON array of the exact operator-verified argv fragment that "
            "reproduces the supervisor's pinned Codex sandbox policy on "
            "`codex exec resume`. Supplying it activates durable supervisor "
            "session pooling. Defaults to "
            f"{CODEX_RESUME_SANDBOX_ARGUMENT_ENVIRONMENT}; absent means the "
            "resume gate is off and every supervisor turn stays ephemeral."
        ),
    )
    parser.add_argument(
        "--supervisor-context-window-tokens",
        type=int,
        help=(
            "Explicit context window of the supervisor model, used only to "
            "derive known context utilization from the exact input token count "
            "Codex reports. Defaults to "
            f"{SUPERVISOR_CONTEXT_WINDOW_ENVIRONMENT}; absent means unknown."
        ),
    )
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


def _supervisor_resume_activation(
    args: argparse.Namespace,
) -> CodexResumeActivation | None:
    """Return the operator's exact Codex resume control, or None (gate off)."""

    if args.supervisor_codex_resume_sandbox_argument is not None:
        return CodexResumeActivation.parse(args.supervisor_codex_resume_sandbox_argument)
    return codex_resume_activation_from_environment()


def _supervisor_context_window(args: argparse.Namespace) -> int | None:
    if args.supervisor_context_window_tokens is not None:
        return validate_context_window_tokens(args.supervisor_context_window_tokens)
    return context_window_tokens_from_environment()


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


def _materialize_generic_review_work(
    *,
    source: Path,
) -> ReviewIssueMaterializationResult:
    """Materialize current review debt before generic mutating dispatch.

    Keeping backend construction in this entrypoint preserves the same
    repository binding and in-memory test seam used by fresh dispatch.
    """

    root = repo_root(source.resolve())
    snapshot = observe_taskgraph_review_snapshot(root)
    return materialize_taskgraph_review_issues(
        source_commit=snapshot.source_commit,
        states=snapshot.states,
        tasks=snapshot.tasks,
        backend=GhIssueBackend(source_root=root),
    )


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


def _worker_terminal_contract(status: str) -> tuple[str, int]:
    if status in {
        "human_action_required",
        "human_revalidation_required",
        "human_delivery_review",
    }:
        return "human_action_required", 0
    if status == "complete":
        return "completed", 0
    if status in {"blocked", "needs_human", "checks_pending"}:
        return "blocked", 3
    if status == "no_safe_work":
        return "no_safe_work", 4
    return "error", 2


def _scheduler_result_enabled(args: argparse.Namespace) -> bool:
    values = (
        args.run_id,
        args.admission_source_head,
        args.task_contract_sha256,
    )
    if all(value is None for value in values):
        if args.admission_issue_number is not None:
            raise ValueError("admission Issue number requires scheduler result identity")
        return False
    if any(value is None for value in values):
        raise ValueError(
            "scheduler result identity requires run-id, admission source HEAD, "
            "and task-contract SHA-256 together"
        )
    if args.task_id is None or args.output_root is None:
        raise ValueError("scheduler result identity requires task-id and output-root")
    if args.admission_issue_number is not None and args.admission_issue_number < 1:
        raise ValueError("admission Issue number must be a positive integer")
    observed_head = subprocess.run(
        ("git", "-C", str(args.source.resolve()), "rev-parse", "HEAD"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=60.0,
    )
    if (
        observed_head.returncode != 0
        or observed_head.stdout.strip() != args.admission_source_head
    ):
        raise ValueError("scheduler admission source HEAD no longer matches the controller")
    load_committed_task(
        args.source.resolve(),
        args.task_id,
        expected_sha256=args.task_contract_sha256,
    )
    return True


def _result_issue_number(result: dict[str, Any]) -> int | None:
    selection = result.get("selection")
    if isinstance(selection, dict) and type(selection.get("issue_number")) is int:
        return selection["issue_number"]
    outcome = result.get("outcome")
    if isinstance(outcome, dict):
        final = outcome.get("deterministic_final_state")
        coordination = final.get("coordination") if isinstance(final, dict) else None
        if (
            isinstance(coordination, dict)
            and type(coordination.get("issue_number")) is int
        ):
            return coordination["issue_number"]
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    progress: ProgressLog | None = None
    supervisor_owner: SupervisorSessionOwner | None = None
    scheduler_result = False
    try:
        scheduler_result = _scheduler_result_enabled(args)
        if args.enable_execution_session_pool and not scheduler_result:
            raise GenericSelectionError(
                "ExecutionCrew session pooling requires scheduler-owned run identity"
            )
        if args.enable_execution_session_pool and (
            args.execution_provider != "claude" or args.execution_model is None
        ):
            raise GenericSelectionError(
                "ExecutionCrew session pooling requires a routed Claude model"
            )
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
            review_result = _materialize_generic_review_work(source=args.source)
            print(
                "[task-agent] TaskGraph review work materialized from "
                f"{review_result.source_commit}: "
                f"created={len(review_result.created_task_ids)}, "
                f"updated={len(review_result.updated_task_ids)}, "
                f"already_current={len(review_result.already_current_task_ids)}.",
                file=sys.stderr,
                flush=True,
            )
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
                run_id=args.run_id,
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
            controller_options: dict[str, Any] = {
                "workflow": workflow,
                "execution_provider": args.execution_provider,
                "enable_execution_session_pool": args.enable_execution_session_pool,
            }
            # Keep the historical manual/default constructor call shape when
            # no routed values were supplied. Scheduler-launched workers carry
            # both values explicitly.
            if args.execution_model is not None:
                controller_options["execution_model"] = args.execution_model
            if args.execution_reasoning_effort is not None:
                controller_options["execution_reasoning_effort"] = (
                    args.execution_reasoning_effort
                )
            if args.crew_profile is not None:
                controller_options["crew_profile"] = args.crew_profile
            if args.validation_profile is not None:
                controller_options["validation_profile"] = args.validation_profile
            controller = ProductionTaskController(**controller_options)
            authority = "read_only_production_pipeline_observation"

        if args.mode == "openai":
            controller = GuardedTaskController(controller, progress=progress)
            assert progress is not None
            resume_activation = _supervisor_resume_activation(args)
            if resume_activation is not None:
                # The durable supervisor conversation is task-scoped and owned
                # by this worker for its lifetime. It exists only when the
                # operator activated the Codex resume gate; with the gate off
                # every turn stays exactly the historical ephemeral turn and
                # the worker says so instead of implying warm pooling.
                supervisor_owner = SupervisorSessionOwner(
                    source=workflow.base_observer.root,
                    checkout_root=args.checkout_root or default_checkout_root(),
                    task_id=request.task_id,
                    worker_id=args.worker_id,
                    run_id=progress.run_id,
                    model=resolve_supervisor_model(args.model),
                    reasoning_effort=resolve_supervisor_reasoning_effort(
                        None if downstream else args.supervisor_reasoning_effort
                    ),
                    resume_activation=resume_activation,
                    context_window_tokens=_supervisor_context_window(args),
                )
                activation = supervisor_owner.activation_state()
            else:
                activation = gate_off_activation_state(request.task_id)
            progress.emit(
                "supervisor_session_pool",
                (
                    "Supervisor session pooling: warm resume ACTIVE"
                    if activation["warm_pooling_active"]
                    else "Supervisor session pooling: warm resume OFF (ephemeral turns)"
                ),
                warm_pooling_active=activation["warm_pooling_active"],
                reason=activation["reason"],
                resume_contract=activation["resume_contract"],
                reconciliation=activation["reconciliation"],
            )

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
                session_owner=supervisor_owner,
            )
            result = {
                "schema_version": "1.0",
                "mode": args.mode,
                "selected_pipeline": "downstream",
                "selection": selection,
                "worker_id": args.worker_id,
                "runtime": describe_codex_runtime(),
                "supervisor_session_pool": (
                    gate_off_activation_state(request.task_id)
                    if supervisor_owner is None
                    else supervisor_owner.activation_state()
                ),
                "outcome": outcome,
            }
        else:
            supervisor_options: dict[str, Any] = {
                "model": args.model,
                "max_turns": args.max_turns,
                "progress": progress,
                "session_owner": supervisor_owner,
            }
            if args.supervisor_reasoning_effort is not None:
                supervisor_options["reasoning_effort"] = (
                    args.supervisor_reasoning_effort
                )
            outcome = run_openai_production_pipeline(
                request,
                controller,
                **supervisor_options,
            )
            result = {
                "schema_version": "1.0",
                "mode": args.mode,
                "selected_pipeline": "implementation",
                "selection": selection,
                "worker_id": args.worker_id,
                "execution_provider": args.execution_provider,
                "execution_model": args.execution_model,
                "execution_reasoning_effort": args.execution_reasoning_effort,
                "supervisor_model": args.model,
                "supervisor_reasoning_effort": args.supervisor_reasoning_effort,
                "runtime": describe_codex_runtime(),
                "supervisor_session_pool": (
                    gate_off_activation_state(request.task_id)
                    if supervisor_owner is None
                    else supervisor_owner.activation_state()
                ),
                "outcome": outcome,
            }
        status = _outcome_status(result)
        terminal_status, exit_code = _worker_terminal_contract(status)
        if progress is not None:
            progress.finish(status)
        if scheduler_result:
            if progress is None:
                raise WorkerResultError("scheduler run completed without a progress directory")
            outcome = result.get("outcome")
            authority = (
                outcome.get("authority")
                if isinstance(outcome, dict)
                else "task_review_pipeline_terminal_result"
            )
            issue_number = _result_issue_number(result)
            if (
                args.admission_issue_number is not None
                and issue_number is not None
                and issue_number != args.admission_issue_number
            ):
                raise WorkerResultError(
                    "pipeline result Issue number does not match scheduler admission"
                )
            if issue_number is None:
                issue_number = args.admission_issue_number
            write_pipeline_result(
                run_dir=progress.run_dir,
                run_id=args.run_id,
                worker_id=args.worker_id,
                task_id=args.task_id,
                source_head=args.admission_source_head,
                task_contract_sha256=args.task_contract_sha256,
                terminal_status=terminal_status,
                outcome_authority=str(authority or "task_review_pipeline_terminal_result"),
                issue_number=issue_number,
                exit_code=exit_code,
                pid=os.getpid(),
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.mode == "openai" and exit_code != 0:
            # The entry point is also the worker-process contract used by the
            # polling scheduler. Only known successful handoff/closeout states
            # may exit zero; blocked, needs-human, malformed, and future unknown
            # outcomes must stop new admissions in the parent process.
            print(
                "GAME TASK AGENT: STOP\n"
                f"The pipeline finished with non-success outcome {status!r}. "
                "The run result is recorded above and cannot be treated as a "
                "successful worker process.",
                file=sys.stderr,
                flush=True,
            )
            return exit_code
        return exit_code if args.mode == "openai" else 0
    except (
        TaskReviewContractError,
        TaskcontrolStateObservationError,
        DownstreamPipelineError,
        GenericSelectionError,
        IssueWorkflowStoreError,
        OpenAIDownstreamPipelineError,
        SupervisorSessionPoolError,
        WorkerResultError,
        OSError,
        ValueError,
    ) as exc:
        if progress is not None:
            progress.finish(
                "failed",
                error_type=type(exc).__name__,
                error=" ".join(str(exc).split())[:900],
            )
            if scheduler_result and not isinstance(exc, WorkerResultError):
                write_pipeline_result(
                    run_dir=progress.run_dir,
                    run_id=args.run_id,
                    worker_id=args.worker_id,
                    task_id=args.task_id,
                    source_head=args.admission_source_head,
                    task_contract_sha256=args.task_contract_sha256,
                    terminal_status="error",
                    outcome_authority="task_review_pipeline_exception",
                    issue_number=args.admission_issue_number,
                    exit_code=2,
                    pid=os.getpid(),
                )
        print(f"GAME TASK AGENT: STOP\n{exc}", file=sys.stderr, flush=True)
        return 2
    finally:
        if supervisor_owner is not None:
            supervisor_owner.close()


if __name__ == "__main__":
    raise SystemExit(main())
