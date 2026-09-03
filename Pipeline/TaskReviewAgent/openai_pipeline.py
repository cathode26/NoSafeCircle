"""Authenticated Codex CLI supervisor for the real task-to-human-Unity pipeline."""

from __future__ import annotations

from typing import Any, Mapping

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
    provider = decision_provider or CodexDockerDecisionProvider(
        source=controller.workflow.base_observer.root,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    history: list[dict[str, Any]] = []

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
            if observed.get("next_action") == "prepare_task_checkout":
                action = "prepare_task_checkout"
                rationale = (
                    "Deterministic host selection followed production_pipeline.next_action "
                    "for the exact no-argument checkout preparation."
                )
                try:
                    with active_progress.heartbeat(
                        "pipeline_action",
                        f"Turn {turn}: executing deterministic {action}",
                        turn=turn,
                        action=action,
                        selection="deterministic_host",
                    ):
                        result = controller.prepare_task_checkout()
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
