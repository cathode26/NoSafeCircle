"""OpenAI Agents SDK adapter for durable Issue lease and checkout preparation."""

from __future__ import annotations

import os
from typing import Any

from .contracts import TASK_REVIEW_SCHEMA_VERSION, TaskReviewContractError, TaskReviewRequest
from .goal_loop import GoalAction, assess_goal_state
from .openai_agent import DEFAULT_MODEL, _json, _require_runtime
from .real_workflow import RealTaskReviewWorkflow


def run_openai_real_checkout(
    request: TaskReviewRequest,
    workflow: RealTaskReviewWorkflow,
    *,
    model: str | None = None,
    max_turns: int = 20,
) -> dict[str, Any]:
    """Let OpenAI acquire the durable Issue lease and prepare the canonical checkout."""

    Agent, ModelSettings, Runner, function_tool, pydantic_types = _require_runtime(max_turns)
    BaseModel, ConfigDict = pydantic_types

    class CheckoutAssessmentModel(BaseModel):
        model_config = ConfigDict(extra="forbid")

        schema_version: str
        task_id: str
        observation_sha256: str
        checkout_sha256: str
        next_action: str
        reasons: list[str]
        authority: str

    @function_tool
    def observe_goal_state() -> str:
        """Read real Git, TaskGraph, durable Issue state, and canonical checkout facts."""

        return _json(workflow.observe_goal_state())

    @function_tool
    def acquire_agent_lease(
        planned_approach: str,
        expected_validation: str,
    ) -> str:
        """Create/resume the managed Issue and acquire its agent-working lease."""

        return _json(
            workflow.acquire_agent_lease(
                planned_approach=planned_approach,
                expected_validation=expected_validation,
            )
        )

    @function_tool
    def prepare_task_checkout() -> str:
        """Create or resume the canonical checkout only after the Issue lease is valid."""

        return _json(workflow.prepare_task_checkout())

    instructions = f"""
You are the Issue-lease and checkout stage of the No Safe Circle Task Review Supervisor.

TASK
Advance exact explicit task {request.task_id} through the durable GitHub Issue workflow and
canonical checkout boundary. Start by calling observe_goal_state.

AVAILABLE AUTHORITY
- observe real committed Git and TaskGraph facts;
- create or initialize the task Issue, check resource conflicts, and acquire one agent lease;
- create or resume only the canonical checkout after that lease is verified.

LOOP
1. Call observe_goal_state.
2. If next action is acquire_agent_lease, call acquire_agent_lease with a concrete Unity
   implementation approach and expected validation. Re-observe.
3. If next action is prepare_checkout, call prepare_task_checkout once. Re-observe.
4. Stop when the exact next action is validate_scope, needs_human, blocked, or complete.
5. Never invent task IDs, paths, branches, hashes, Issue state, or statuses.

BOUNDARY
You may not plan write paths, run ExecutionCrew, edit gameplay/tests, apply a patch, run Unity,
commit, push, merge, package evidence, or claim conformance.

OUTPUT
- schema_version exactly {TASK_REVIEW_SCHEMA_VERSION};
- task_id exactly {request.task_id};
- observation_sha256 and checkout_sha256 copied from the final observation;
- next_action matching deterministic state;
- concrete reasons;
- authority exactly issue_lease_and_checkout_only.
""".strip()

    calls_before = len(workflow.action_log)
    agent = Agent(
        name="No Safe Circle Issue and Checkout Supervisor",
        model=model or os.getenv("TASK_REVIEW_AGENT_MODEL", DEFAULT_MODEL),
        instructions=instructions,
        tools=[observe_goal_state, acquire_agent_lease, prepare_task_checkout],
        output_type=CheckoutAssessmentModel,
        model_settings=ModelSettings(tool_choice="required"),
    )
    result = Runner.run_sync(
        agent,
        f"Advance {request.task_id} through the bounded Issue and checkout stage.",
        max_turns=max_turns,
    )
    final_output = result.final_output
    if not isinstance(final_output, CheckoutAssessmentModel):
        raise TaskReviewContractError(
            "OpenAI checkout agent did not return the required structured output"
        )
    if len(workflow.action_log) <= calls_before or workflow.last_observation is None:
        raise TaskReviewContractError(
            "OpenAI checkout agent returned without calling observe_goal_state"
        )

    observation = workflow.last_observation
    expected = assess_goal_state(observation)
    payload = final_output.model_dump(mode="json")
    fixed_checks = {
        "schema_version": TASK_REVIEW_SCHEMA_VERSION,
        "task_id": request.task_id,
        "observation_sha256": observation["observation_sha256"],
        "checkout_sha256": observation["checkout_sha256"],
        "next_action": expected.action.value,
        "authority": "issue_lease_and_checkout_only",
    }
    for field, expected_value in fixed_checks.items():
        if payload.get(field) != expected_value:
            raise TaskReviewContractError(
                "OpenAI checkout assessment did not match deterministic "
                f"{field}: {payload.get(field)!r} != {expected_value!r}"
            )

    actions = workflow.action_log[calls_before:]
    if expected.action is GoalAction.VALIDATE_SCOPE:
        coordination = observation.get("coordination") or {}
        if coordination.get("workflow_status") != "agent_working_by_worker":
            raise TaskReviewContractError(
                "OpenAI checkout agent reached validate_scope without its Issue lease"
            )
        if observation["checkout"].get("status") != "ready":
            raise TaskReviewContractError(
                "OpenAI checkout agent reached validate_scope without a ready checkout"
            )
        if workflow.last_lease_result is None and "acquire_agent_lease" in actions:
            raise TaskReviewContractError("agent lease call did not retain its result")

    return {
        **fixed_checks,
        "reasons": list(expected.reasons),
        "model_reasons": list(payload.get("reasons") or []),
        "agent_lease": workflow.last_lease_result,
        "checkout_preparation": workflow.last_checkout_result,
    }
