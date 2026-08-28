"""Authenticated Codex CLI supervisor for delivery evidence and verified closeout."""

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
from .downstream_runtime import ResumableDownstreamTaskController
from .progress import NullProgress, ProgressLog, ProgressSink, summarize_result


class OpenAIDownstreamPipelineError(TaskReviewContractError):
    """Raised when the goal loop cannot safely reach a downstream terminal state."""


_ACTIONS = {
    "acquire_agent_lease": (
        "Acquire the current delivery/closeout phase. Arguments: planned_approach, "
        "expected_validation."
    ),
    "prepare_task_checkout": "Resume/recreate the canonical checkout at the recorded head. No arguments.",
    "read_issue_log": "Read validated workflow events and human comments. No arguments.",
    "list_repository_files": "List committed files. Optional arguments: prefix, limit.",
    "search_repository": "Search committed text. Arguments: query, prefixes; optional limit.",
    "read_repository_file": "Read one committed file range. Arguments: path; optional start_line, end_line.",
    "run_authoritative_unity_test": (
        "Run one clean Unity validation filter. Arguments: test_platform, test_filter."
    ),
    "create_delivery_review_draft": "Create TaskDelivery's immutable clerical draft. No arguments.",
    "delivery_review_facts": "Read exact candidate surfaces, evidence IDs, and gates. No arguments.",
    "create_delivery_review_proposal": (
        "Create a hash-bound proposal without approving it. Arguments: selected_surfaces, "
        "gate_mappings, approval_notes."
    ),
    "publish_delivery_review": "Publish the proposal and transfer the Issue to Vincent. No arguments.",
    "finalize_delivery_evidence_and_open_pr": (
        "After exact human approval, package evidence, prove conformance, push, and open PR. No arguments."
    ),
    "inspect_or_merge_pull_request": (
        "Inspect checks; release if pending, block on failure, or merge exact passing head. No arguments."
    ),
    "verify_post_merge_and_complete": (
        "Verify fresh main remains conformant, complete the journal, and close the Issue. No arguments."
    ),
}

_GOAL_AND_RULES = """
GOAL
Resume the durable Issue after Vincent's Unity PASS and move it through authoritative Unity
validation, hash-bound human delivery review, TaskDelivery evidence, TaskGraph conformance, pull
request checks, exact merge, fresh-main verification, and Issue completion.

AUTHORITY
You choose only one next bounded action. Host Python executes and validates it. You have no direct
shell, repository-write, GitHub, Unity, evidence, approval, commit, push, or merge authority.

OPERATING RULES
- Follow downstream.next_action and never skip a prerequisite.
- Acquire a lease before any downstream side effect.
- Read the Issue log, task contract, Unity testing policy, and programmer-language policy.
- Select exact Unity test filters from committed tests and run every required platform.
- Human PASS is not authoritative automated evidence; only passed validation manifests are.
- After drafting, inspect every surface candidate, evidence artifact, and completion gate.
- Select only truthful committed conformance surfaces, give each a concrete semantic role, and map
  each gate to specific evidence with a gate-specific explanation.
- You may propose delivery mappings but never approve them. Publish the proposal and stop at the
  human review boundary. A rejected proposal cannot be reused.
- After exact approval, finalization must establish TaskGraph conformant before PR creation.
- Pending checks release the lease for a later generic run. Merge only the exact recorded head with
  history preserved. If main advanced beyond the validated integration, stop rather than merge.
- Complete only after fresh origin/main validates and still derives the task as conformant.
- Never edit game code, task contracts, the GDD, approved mappings, validation manifests, or
  immutable evidence bytes. Never force-push, squash, or rebase.
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
    downstream = observation.get("downstream") or {}
    receipt = downstream.get("receipt") or {}
    environment = observation.get("environment") or {}
    next_action = downstream.get("next_action")
    fixed = {
        "schema_version": TASK_REVIEW_SCHEMA_VERSION,
        "task_id": request.task_id,
        "issue_url": coordination.get("issue_url"),
        "branch": state.get("branch"),
        "commit": state.get("head_commit"),
        "pull_request_url": receipt.get("pull_request_url"),
        "authority": "delivery_evidence_to_verified_merge_closeout",
        "deterministic_final_state": observation,
    }

    if state.get("state") == "complete":
        return {
            **fixed,
            "status": "complete",
            "next_action": "No further action; fresh main is conformant and the Issue is closed.",
            "blockers": [],
        }

    if (
        state.get("state") == "blocked"
        and state.get("phase") == "delivery_evidence"
        and state.get("current_actor") == "human"
        and next_action == "vincent_reviews_delivery_proposal"
    ):
        return {
            **fixed,
            "status": "human_delivery_review",
            "next_action": "Vincent reviews the exact proposal recorded in the Issue.",
            "blockers": [],
        }

    if (
        state.get("state") == "agent_ready"
        and state.get("phase") == "merge_closeout"
        and isinstance(receipt.get("evidence_commit"), str)
        and isinstance(receipt.get("pull_request_url"), str)
        and not receipt.get("merged_commit")
    ):
        return {
            **fixed,
            "status": "checks_pending",
            "next_action": "Run the generic agent again after pull-request checks finish.",
            "blockers": [],
        }

    if state.get("state") == "blocked":
        return {
            **fixed,
            "status": "blocked",
            "next_action": next_action or "Resolve the latest durable Issue blocker.",
            "blockers": _strings(coordination.get("reasons"))
            or ["The managed downstream Issue is blocked; inspect its latest event."],
        }

    if environment.get("ready") is not True:
        return {
            **fixed,
            "status": "blocked",
            "next_action": "Repair the deterministic environment before retrying.",
            "blockers": _strings(environment.get("errors"))
            or ["The deterministic environment is not ready."],
        }

    if coordination.get("status") in {"claimed_by_other", "conflict", "unavailable"}:
        return {
            **fixed,
            "status": "blocked",
            "next_action": "Resolve the Issue coordination conflict.",
            "blockers": _strings(coordination.get("reasons"))
            or [f"Issue coordination status is {coordination.get('status')!r}."],
        }
    return None


def _execute(
    decision: SupervisorDecision,
    controller: ResumableDownstreamTaskController,
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
    if action == "read_issue_log":
        decision.validate_arguments()
        return controller.read_issue_log()
    if action == "list_repository_files":
        values = decision.validate_arguments(optional=("prefix", "limit"))
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
    if action == "run_authoritative_unity_test":
        values = decision.validate_arguments(required=("test_platform", "test_filter"))
        return controller.run_authoritative_unity_test(**values)
    if action == "create_delivery_review_draft":
        decision.validate_arguments()
        return controller.create_delivery_review_draft()
    if action == "delivery_review_facts":
        decision.validate_arguments()
        return controller.delivery_review_facts()
    if action == "create_delivery_review_proposal":
        values = decision.validate_arguments(
            required=("selected_surfaces", "gate_mappings", "approval_notes")
        )
        return controller.create_delivery_review_proposal(**values)
    if action == "publish_delivery_review":
        decision.validate_arguments()
        return controller.publish_delivery_review()
    if action == "finalize_delivery_evidence_and_open_pr":
        decision.validate_arguments()
        return controller.finalize_delivery_evidence_and_open_pr()
    if action == "inspect_or_merge_pull_request":
        decision.validate_arguments()
        return controller.inspect_or_merge_pull_request()
    if action == "verify_post_merge_and_complete":
        decision.validate_arguments()
        return controller.verify_post_merge_and_complete()
    raise CodexSupervisorError(f"unhandled downstream action: {action}")


def _observation_fields(observation: Mapping[str, Any]) -> dict[str, Any]:
    state = _workflow_state(observation)
    downstream = observation.get("downstream") or {}
    coordination = observation.get("coordination") or {}
    checkout = observation.get("checkout") or {}
    return {
        "issue_state": state.get("state"),
        "phase": state.get("phase"),
        "downstream_status": downstream.get("status"),
        "next_action": downstream.get("next_action"),
        "checkout_status": checkout.get("status"),
        "issue_number": coordination.get("issue_number"),
    }


def _progress_for(
    request: TaskReviewRequest,
    controller: ResumableDownstreamTaskController,
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
            pipeline="downstream",
        ),
        True,
    )


def run_openai_downstream_pipeline(
    request: TaskReviewRequest,
    controller: ResumableDownstreamTaskController,
    *,
    model: str | None = None,
    max_turns: int = 100,
    decision_provider: DecisionProvider | None = None,
    progress: ProgressSink | None = None,
) -> dict[str, Any]:
    """Drive downstream work with Codex CLI while host tools retain authority."""

    if isinstance(max_turns, bool) or not isinstance(max_turns, int) or not 4 <= max_turns <= 160:
        raise OpenAIDownstreamPipelineError("max_turns must be an integer from 4 through 160")
    active_progress, owns_progress = _progress_for(
        request,
        controller,
        decision_provider=decision_provider,
        progress=progress,
    )
    provider = decision_provider or CodexDockerDecisionProvider(
        source=controller.workflow.base_observer.root,
        model=model,
    )
    history: list[dict[str, Any]] = []

    try:
        for turn in range(1, max_turns + 1):
            with active_progress.heartbeat(
                "state_observation",
                f"Turn {turn}: reading deterministic downstream state",
                turn=turn,
            ):
                observation = controller.observe()
            observed = _observation_fields(observation)
            active_progress.emit(
                "state_observed",
                f"Turn {turn}: deterministic downstream state read",
                turn=turn,
                **observed,
            )
            terminal = _terminal_outcome(request, observation)
            if terminal is not None:
                active_progress.emit(
                    "terminal_state",
                    f"Reached terminal downstream state {terminal.get('status')}",
                    turn=turn,
                    **summarize_result(terminal),
                )
                if owns_progress:
                    active_progress.finish(str(terminal.get("status") or "complete"))
                return terminal
            prompt = render_supervisor_prompt(
                task_id=request.task_id,
                goal_and_rules=_GOAL_AND_RULES,
                observation=observation,
                history=history,
                actions=_ACTIONS,
            )
            with active_progress.heartbeat(
                "codex_supervisor",
                f"Turn {turn}: Codex is choosing the next downstream action",
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

        raise OpenAIDownstreamPipelineError(
            f"Codex supervisor exhausted {max_turns} decisions without a deterministic terminal state"
        )
    except BaseException:
        if owns_progress:
            active_progress.finish("failed")
        raise
