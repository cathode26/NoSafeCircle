"""Authenticated Codex CLI supervisor for the real task-to-human-Unity pipeline."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Mapping

from .codex_supervisor import (
    CodexDockerDecisionProvider,
    CodexSupervisorError,
    DecisionProvider,
    SupervisorDecision,
    render_supervisor_prompt,
)
from .contracts import TASK_REVIEW_SCHEMA_VERSION, TaskReviewContractError, TaskReviewRequest
from .production_pipeline import ProductionTaskController
from .progress import NullProgress, ProgressLog, ProgressSink, summarize_result


class OpenAIProductionPipelineError(TaskReviewContractError):
    """Raised when the goal loop cannot safely reach a deterministic terminal state."""


_ACTIONS = {
    "acquire_agent_lease": (
        "Reserve the managed Issue for this worker. Arguments: planned_approach, "
        "expected_validation."
    ),
    "repository_facts": "Read task-owned resource hints and suggested implementation/test files. No arguments.",
    "list_repository_files": (
        "List committed files. Arguments: prefix; optional limit. Use '.' for all approved "
        "read roots, or a repository-relative approved prefix such as 'Assets/' or "
        "'Docs/Engineering/'."
    ),
    "search_repository": (
        "Search committed text. Arguments: query, prefixes; optional limit. Use ['.'] for "
        "all approved read roots; never use an empty prefix list."
    ),
    "read_repository_file": "Read one committed file range. Arguments: path; optional start_line, end_line.",
    "latest_human_feedback": "Read the latest validated human PASS/FAIL feedback. No arguments.",
    "validate_execution_scope": (
        "Validate exact file authority. Arguments: existing_implementation_paths, "
        "new_implementation_paths, existing_test_paths, new_test_paths."
    ),
    "run_execution_crew": (
        "Run ExecutionCrew using a validated plan. Arguments: plan_id; optional "
        "retry_run_id and feedback_file."
    ),
    "integrate_commit_push_and_handoff": (
        "Verify/apply a review_ready candidate, commit and push it, then publish Vincent's "
        "Unity checklist. Arguments: run_id, implementation_summary, human_steps, expected_result."
    ),
    "record_pipeline_blocker": (
        "Persist a genuine bounded blocker in the Issue. Arguments: summary, details."
    ),
}

_GOAL_AND_RULES = """
GOAL
Advance the exact task from current deterministic state until its implementation and tests are
committed and pushed on the canonical task branch and the managed Issue is
human_action_required/unity_runtime_validation.

AUTHORITY
You choose only the next bounded action. ExecutionCrew is the only game-code author. Host Python
validates and executes every action. You have no direct shell, repository-write, GitHub, Unity,
commit, push, merge, delivery, or conformance authority.

OPERATING RULES
- Follow production_pipeline.next_action and never skip a prerequisite.
- Do not select a different task.
- Acquire a lease only with a concrete implementation approach and expected validation.
- Before proposing scope, inspect repository_facts and read the Unity testing/programmer-language
  policies plus enough current scripts and tests to identify the smallest exact file set.
- repository_scope_facts already supplies exact required_policy_paths, existing/absent resource
  paths, and suggested tests. Use those paths directly; do not search or list merely to rediscover
  a path already present there.
- Correct existing/new classifications from deterministic validation findings. Never include .meta.
- Keep implementation and test scopes disjoint and include at least one C# test file.
- Run ExecutionCrew only with a returned plan_id.
- If ExecutionCrew returns a non-review-ready terminal status, record its exact blocker and artifact
  identity rather than inventing a candidate.
- Integrate only a returned review_ready run_id. Human steps must identify the checkout/scene,
  numbered Play Mode actions, and observable PASS behavior derived from completion gates.
- Stop at the human Issue boundary. Do not run downstream delivery or merge work.
"""


def _workflow_state(observation: Mapping[str, Any]) -> dict[str, Any]:
    coordination = observation.get("coordination")
    if not isinstance(coordination, Mapping):
        return {}
    state = coordination.get("workflow_state")
    return dict(state) if isinstance(state, Mapping) else {}


def _strings(values: Any) -> list[str]:
    if isinstance(values, (list, tuple)):
        return [str(item) for item in values if str(item).strip()]
    return []


def _terminal_outcome(
    request: TaskReviewRequest,
    observation: Mapping[str, Any],
) -> dict[str, Any] | None:
    coordination = observation.get("coordination") or {}
    state = _workflow_state(observation)
    pipeline = observation.get("production_pipeline") or {}
    environment = observation.get("environment") or {}
    task = observation.get("task") or {}

    if (
        pipeline.get("status") == "human_action_required"
        and state.get("state") == "human_action_required"
    ):
        return {
            "schema_version": TASK_REVIEW_SCHEMA_VERSION,
            "task_id": request.task_id,
            "status": "human_action_required",
            "issue_url": coordination.get("issue_url"),
            "branch": state.get("branch"),
            "commit": state.get("head_commit"),
            "next_action": "Vincent completes the exact Unity checklist in the managed Issue.",
            "blockers": [],
            "authority": "committed_branch_to_human_unity_handoff",
            "deterministic_final_state": observation,
        }

    if state.get("state") == "blocked":
        return {
            "schema_version": TASK_REVIEW_SCHEMA_VERSION,
            "task_id": request.task_id,
            "status": "blocked",
            "issue_url": coordination.get("issue_url"),
            "branch": state.get("branch"),
            "commit": state.get("head_commit"),
            "next_action": pipeline.get("next_action") or "Resolve the recorded Issue blocker.",
            "blockers": _strings(coordination.get("reasons"))
            or ["The managed Issue is in blocked state; inspect its latest event."],
            "authority": "committed_branch_to_human_unity_handoff",
            "deterministic_final_state": observation,
        }

    if environment.get("ready") is not True:
        return {
            "schema_version": TASK_REVIEW_SCHEMA_VERSION,
            "task_id": request.task_id,
            "status": "blocked",
            "issue_url": coordination.get("issue_url"),
            "branch": state.get("branch"),
            "commit": state.get("head_commit"),
            "next_action": "Repair the deterministic environment before retrying.",
            "blockers": _strings(environment.get("errors"))
            or ["The deterministic environment is not ready."],
            "authority": "committed_branch_to_human_unity_handoff",
            "deterministic_final_state": observation,
        }

    eligibility = {
        "contract_disposition": task.get("contract_disposition") == "active",
        "kind": task.get("kind") == "implementation",
        "execution_scope": task.get("execution_scope") == "single_agent",
        "decomposition_state": task.get("decomposition_state") == "concrete",
        "derived_state": task.get("derived_state") == "not_delivered",
        "dependencies_conformant": task.get("dependencies_conformant") is True,
    }
    if not all(eligibility.values()):
        blockers = [name for name, passed in eligibility.items() if not passed]
        return {
            "schema_version": TASK_REVIEW_SCHEMA_VERSION,
            "task_id": request.task_id,
            "status": "needs_human",
            "issue_url": coordination.get("issue_url"),
            "branch": state.get("branch"),
            "commit": state.get("head_commit"),
            "next_action": "Resolve task-contract or dependency readiness before implementation.",
            "blockers": [f"Eligibility condition failed: {name}" for name in blockers],
            "authority": "committed_branch_to_human_unity_handoff",
            "deterministic_final_state": observation,
        }

    if coordination.get("status") in {
        "claimed_by_other",
        "conflict",
        "closed",
        "unavailable",
    }:
        return {
            "schema_version": TASK_REVIEW_SCHEMA_VERSION,
            "task_id": request.task_id,
            "status": "blocked",
            "issue_url": coordination.get("issue_url"),
            "branch": state.get("branch"),
            "commit": state.get("head_commit"),
            "next_action": "Resolve the GitHub Issue coordination conflict.",
            "blockers": _strings(coordination.get("reasons"))
            or [f"Issue coordination status is {coordination.get('status')!r}."],
            "authority": "committed_branch_to_human_unity_handoff",
            "deterministic_final_state": observation,
        }
    return None


def _execute(
    decision: SupervisorDecision,
    controller: ProductionTaskController,
) -> Any:
    action = decision.action
    if action == "acquire_agent_lease":
        values = decision.validate_arguments(
            required=("planned_approach", "expected_validation")
        )
        return controller.acquire_agent_lease(**values)
    if action == "prepare_task_checkout":
        decision.validate_arguments()
        return controller.prepare_task_checkout()
    if action == "repository_facts":
        decision.validate_arguments()
        return controller.repository_facts()
    if action == "list_repository_files":
        values = decision.validate_arguments(required=("prefix",), optional=("limit",))
        return controller.list_repository_files(**values)
    if action == "search_repository":
        values = decision.validate_arguments(
            required=("query", "prefixes"), optional=("limit",)
        )
        return controller.search_repository(**values)
    if action == "read_repository_file":
        values = decision.validate_arguments(
            required=("path",), optional=("start_line", "end_line")
        )
        return controller.read_repository_file(**values)
    if action == "latest_human_feedback":
        decision.validate_arguments()
        return controller.latest_human_feedback()
    if action == "validate_execution_scope":
        values = decision.validate_arguments(
            required=(
                "existing_implementation_paths",
                "new_implementation_paths",
                "existing_test_paths",
                "new_test_paths",
            )
        )
        return controller.validate_execution_scope(**values)
    if action == "run_execution_crew":
        values = decision.validate_arguments(
            required=("plan_id",), optional=("retry_run_id", "feedback_file")
        )
        return controller.run_execution_crew(**values)
    if action == "integrate_commit_push_and_handoff":
        values = decision.validate_arguments(
            required=(
                "run_id",
                "implementation_summary",
                "human_steps",
                "expected_result",
            )
        )
        return controller.integrate_commit_push_and_handoff(**values)
    if action == "record_pipeline_blocker":
        values = decision.validate_arguments(required=("summary", "details"))
        return controller.record_pipeline_blocker(**values)
    raise CodexSupervisorError(f"unhandled production action: {action}")


def _observation_fields(observation: Mapping[str, Any]) -> dict[str, Any]:
    state = _workflow_state(observation)
    pipeline = observation.get("production_pipeline") or {}
    checkout = observation.get("checkout") or {}
    coordination = observation.get("coordination") or {}
    return {
        "issue_state": state.get("state"),
        "phase": state.get("phase"),
        "pipeline_status": pipeline.get("status"),
        "next_action": pipeline.get("next_action"),
        "checkout_status": checkout.get("status"),
        "issue_number": coordination.get("issue_number"),
    }


# A deterministically forced action may bypass the supervisor provider ONLY when
# the host already owns every required argument. The provider still decides
# whenever any argument needs judgment, so this never removes a real decision.
#
# prepare_task_checkout: no arguments at all.
# run_execution_crew:    plan_id is the accepted scope plan the host validated;
#                        production_pipeline emits this next_action exactly when
#                        `scope.accepted is not None` and no execution receipt
#                        exists, so the first run is fully determined. A retry
#                        needs retry_run_id/feedback_file judgment and is
#                        therefore deliberately excluded below.
_HOST_FORCED_INVOKERS: dict[str, Callable[[Any, Mapping[str, Any]], Any]] = {
    "prepare_task_checkout": lambda controller, _arguments: (
        controller.prepare_task_checkout()
    ),
    "run_execution_crew": lambda controller, arguments: (
        controller.run_execution_crew(**dict(arguments))
    ),
}

# Consecutive supervisor turns that may pass without any durable workflow change
# before the loop fails closed. Ordinary exploration (repository_facts, searches,
# file reads) legitimately makes no durable change, so this bound is deliberately
# generous; it exists to stop unbounded churn, not to second-guess a few reads.
_MAX_TURNS_WITHOUT_DURABLE_PROGRESS = 12


def _host_forced_action(
    observation: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    """Return the exact (action, arguments) deterministic host state forces.

    Returns ``None`` whenever more than one safe action remains, or whenever any
    required argument would need supervisor judgment. Callers must consult the
    provider in that case.
    """

    next_action = observed.get("next_action")
    if next_action == "prepare_task_checkout":
        return ("prepare_task_checkout", {})
    if next_action == "run_execution_crew":
        plan_id = observation.get("accepted_plan_id")
        if not isinstance(plan_id, str) or not plan_id.strip():
            return None
        if observation.get("execution_run") is not None:
            # A prior receipt exists, so this is a repair/retry whose
            # retry_run_id and feedback_file require supervisor judgment.
            return None
        return ("run_execution_crew", {"plan_id": plan_id})
    return None


def _progress_fingerprint(observation: Mapping[str, Any]) -> str:
    """Hash the durable workflow state that proves real progress.

    Deliberately excludes provider responses, history, prompts, and turn counters:
    another provider answer is not progress. Only committed/durable workflow,
    checkout, scope, execution and integration identity count.
    """

    state = _workflow_state(observation)
    pipeline = observation.get("production_pipeline") or {}
    checkout = observation.get("checkout") or {}
    coordination = observation.get("coordination") or {}
    execution = observation.get("execution_run")
    execution = execution if isinstance(execution, Mapping) else {}
    integration = observation.get("candidate_integration")
    integration = integration if isinstance(integration, Mapping) else {}
    material = {
        "issue_state": state.get("state"),
        "phase": state.get("phase"),
        "lease_id": state.get("lease_id"),
        "head_commit": state.get("head_commit"),
        "pipeline_status": pipeline.get("status"),
        "next_action": pipeline.get("next_action"),
        "checkout_status": checkout.get("status"),
        "coordination_status": coordination.get("status"),
        "accepted_plan_id": observation.get("accepted_plan_id"),
        "execution_run_id": execution.get("run_id"),
        "execution_crew_status": execution.get("crew_status"),
        "integration_commit": integration.get("commit"),
        "integration_status": integration.get("status"),
    }
    payload = json.dumps(material, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _progress_for(
    request: TaskReviewRequest,
    controller: ProductionTaskController,
    *,
    decision_provider: DecisionProvider | None,
    progress: ProgressSink | None,
) -> tuple[ProgressSink, bool]:
    if progress is not None:
        return progress, False
    if decision_provider is not None:
        return NullProgress(), False
    root = controller.workflow.base_observer.root.parent / ".task-review-agent" / "outputs"
    return (
        ProgressLog(
            output_root=root,
            task_id=request.task_id,
            worker_id=controller.workflow.worker_id,
            pipeline="implementation",
        ),
        True,
    )


def run_openai_production_pipeline(
    request: TaskReviewRequest,
    controller: ProductionTaskController,
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
    max_turns: int = 80,
    decision_provider: DecisionProvider | None = None,
    progress: ProgressSink | None = None,
    session_owner: Any = None,
) -> dict[str, Any]:
    """Drive a task with Codex CLI while host tools retain all authority."""

    if isinstance(max_turns, bool) or not isinstance(max_turns, int) or not 4 <= max_turns <= 160:
        raise OpenAIProductionPipelineError("max_turns must be an integer from 4 through 160")
    active_progress, owns_progress = _progress_for(
        request,
        controller,
        decision_provider=decision_provider,
        progress=progress,
    )
    if decision_provider is not None and session_owner is not None:
        raise OpenAIProductionPipelineError(
            "an injected decision provider cannot also receive a supervisor session owner"
        )
    provider = decision_provider or CodexDockerDecisionProvider(
        source=controller.workflow.base_observer.root,
        model=model,
        reasoning_effort=reasoning_effort,
        session_owner=session_owner,
    )
    history: list[dict[str, Any]] = []
    last_progress_fingerprint: str | None = None
    turns_without_durable_progress = 0

    try:
        for turn in range(1, max_turns + 1):
            with active_progress.heartbeat(
                "state_observation",
                f"Turn {turn}: reading deterministic workflow state",
                turn=turn,
            ):
                observation = controller.observe()
            observed = _observation_fields(observation)
            active_progress.emit(
                "state_observed",
                f"Turn {turn}: deterministic state read",
                turn=turn,
                **observed,
            )
            fingerprint = _progress_fingerprint(observation)
            if last_progress_fingerprint is None or fingerprint != last_progress_fingerprint:
                turns_without_durable_progress = 0
            else:
                turns_without_durable_progress += 1
            last_progress_fingerprint = fingerprint
            terminal = _terminal_outcome(request, observation)
            if terminal is not None:
                active_progress.emit(
                    "terminal_state",
                    f"Reached terminal workflow state {terminal.get('status')}",
                    turn=turn,
                    **summarize_result(terminal),
                )
                if owns_progress:
                    active_progress.finish(str(terminal.get("status") or "complete"))
                return terminal
            if turns_without_durable_progress >= _MAX_TURNS_WITHOUT_DURABLE_PROGRESS:
                active_progress.emit(
                    "no_durable_progress_bound_reached",
                    (
                        f"{turns_without_durable_progress} consecutive turns changed no "
                        "durable workflow state; stopping without choosing an action"
                    ),
                    turn=turn,
                    turns_without_durable_progress=turns_without_durable_progress,
                    max_turns_without_durable_progress=(
                        _MAX_TURNS_WITHOUT_DURABLE_PROGRESS
                    ),
                    progress_fingerprint=fingerprint,
                    next_action=observed.get("next_action"),
                )
                try:
                    controller.record_pipeline_blocker(
                        summary="Goal supervisor made no durable workflow progress",
                        details=[
                            f"{turns_without_durable_progress} consecutive supervisor turns "
                            "left every durable workflow, checkout, scope, execution and "
                            "integration field unchanged.",
                            "The bounded limit is "
                            f"{_MAX_TURNS_WITHOUT_DURABLE_PROGRESS} consecutive turns.",
                            "No terminal state was proven and no action was synthesized.",
                        ],
                    )
                    observation = controller.observe()
                    terminal = _terminal_outcome(request, observation)
                    if terminal is not None:
                        if owns_progress:
                            active_progress.finish(
                                str(terminal.get("status") or "blocked")
                            )
                        return terminal
                except TaskReviewContractError:
                    pass
                raise OpenAIProductionPipelineError(
                    "Goal supervisor made no durable workflow progress for "
                    f"{turns_without_durable_progress} consecutive turns"
                )
            forced = _host_forced_action(observation, observed)
            if forced is not None:
                action, forced_arguments = forced
                rationale = (
                    "Deterministic host selection followed production_pipeline.next_action "
                    f"for the exact host-argued action {action}."
                )
                try:
                    with active_progress.heartbeat(
                        "pipeline_action",
                        f"Turn {turn}: executing deterministic {action}",
                        turn=turn,
                        action=action,
                        selection="deterministic_host",
                    ):
                        result = _HOST_FORCED_INVOKERS[action](
                            controller, forced_arguments
                        )
                    active_progress.emit(
                        "action_completed",
                        f"Turn {turn}: {action} completed",
                        turn=turn,
                        action=action,
                        selection="deterministic_host",
                        result_summary=summarize_result(result),
                    )
                    history.append(
                        {
                            "turn": turn,
                            "action": action,
                            "selection": "deterministic_host",
                            "rationale": rationale,
                            "result": summarize_result(result),
                        }
                    )
                except TaskReviewContractError as exc:
                    active_progress.emit(
                        "action_rejected",
                        f"Turn {turn}: {action} was rejected by deterministic validation",
                        turn=turn,
                        action=action,
                        selection="deterministic_host",
                        error_type=type(exc).__name__,
                        error=" ".join(str(exc).split())[:700],
                    )
                    history.append(
                        {
                            "turn": turn,
                            "action": action,
                            "selection": "deterministic_host",
                            "rationale": rationale,
                            "tool_error": " ".join(str(exc).split())[:700],
                        }
                    )
                continue
            prompt = render_supervisor_prompt(
                task_id=request.task_id,
                goal_and_rules=_GOAL_AND_RULES,
                observation=observation,
                history=history,
                actions=_ACTIONS,
            )
            bind_observation = getattr(provider, "bind_turn_observation", None)
            if callable(bind_observation):
                # The authority capsule of a pooled turn names the same phase,
                # Issue state, and source identity the prompt was rendered from.
                bind_observation(observation)
            with active_progress.heartbeat(
                "codex_supervisor",
                f"Turn {turn}: Codex is choosing the next bounded action",
                turn=turn,
                expected_next_action=observed.get("next_action"),
            ):
                decision = provider.decide(
                    task_id=request.task_id,
                    turn=turn,
                    prompt=prompt,
                    allowed_actions=tuple(_ACTIONS),
                )
            active_progress.emit(
                "supervisor_decision",
                f"Turn {turn}: Codex selected {decision.action}",
                turn=turn,
                action=decision.action,
                rationale=" ".join(decision.rationale.split())[:500],
            )
            try:
                with active_progress.heartbeat(
                    "pipeline_action",
                    f"Turn {turn}: executing {decision.action}",
                    turn=turn,
                    action=decision.action,
                ):
                    result = _execute(decision, controller)
                active_progress.emit(
                    "action_completed",
                    f"Turn {turn}: {decision.action} completed",
                    turn=turn,
                    action=decision.action,
                    result_summary=summarize_result(result),
                )
                history.append(
                    {
                        "turn": turn,
                        "action": decision.action,
                        "rationale": decision.rationale,
                        "result": result,
                    }
                )
            except TaskReviewContractError as exc:
                active_progress.emit(
                    "action_rejected",
                    f"Turn {turn}: {decision.action} was rejected by deterministic validation",
                    turn=turn,
                    action=decision.action,
                    error_type=type(exc).__name__,
                    error=" ".join(str(exc).split())[:700],
                )
                history.append(
                    {
                        "turn": turn,
                        "action": decision.action,
                        "rationale": decision.rationale,
                        "tool_error": str(exc),
                    }
                )

        observation = controller.observe()
        state = _workflow_state(observation)
        if state.get("state") == "agent_working" and state.get("worker_id") == controller.workflow.worker_id:
            try:
                active_progress.emit(
                    "turn_budget_exhausted",
                    f"Codex used all {max_turns} bounded decisions; recording a durable blocker",
                    max_turns=max_turns,
                )
                controller.record_pipeline_blocker(
                    summary="Goal supervisor turn budget exhausted",
                    details=[
                        f"The authenticated Codex supervisor used all {max_turns} bounded decisions.",
                        "No human-ready terminal state was proven.",
                    ],
                )
                observation = controller.observe()
                terminal = _terminal_outcome(request, observation)
                if terminal is not None:
                    if owns_progress:
                        active_progress.finish(str(terminal.get("status") or "blocked"))
                    return terminal
            except TaskReviewContractError:
                pass
        raise OpenAIProductionPipelineError(
            f"Codex supervisor exhausted {max_turns} decisions without a deterministic terminal state"
        )
    except BaseException:
        if owns_progress:
            active_progress.finish("failed")
        raise
