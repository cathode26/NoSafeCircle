"""OpenAI Agents SDK adapter for the real claim-inspection/checkout boundary."""

from __future__ import annotations

import os
from typing import Any

from .contracts import TASK_REVIEW_SCHEMA_VERSION, TaskReviewContractError, TaskReviewRequest
from .goal_loop import assess_goal_state
from .openai_agent import DEFAULT_MODEL, _json, _require_runtime
from .real_workflow import RealTaskReviewWorkflow


def run_openai_real_checkout(
    request: TaskReviewRequest,
    workflow: RealTaskReviewWorkflow,
    *,
    model: str | None = None,
    max_turns: int = 16,
) -> dict[str, Any]:
    """Let OpenAI prepare a checkout only after deterministic claim and eligibility gates."""

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
        """Read real Git, TaskGraph, GitHub claim, and canonical checkout facts."""

        return _json(workflow.observe_goal_state())

    @function_tool
    def prepare_task_checkout() -> str:
        """Create or resume the canonical checkout only when all deterministic gates pass."""

        return _json(workflow.prepare_task_checkout())

    instructions = f"""
You are the checkout-preparation stage of the No Safe Circle Task Review Supervisor.

TASK
Advance exact explicit task {request.task_id} through the existing GitHub-claim and canonical
checkout boundary. Start by calling observe_goal_state.

AVAILABLE AUTHORITY
- observe real committed Git and TaskGraph facts;
- inspect the real GitHub Issue claim read-only;
- call prepare_task_checkout only when deterministic next_action is prepare_checkout.

prepare_task_checkout may create or resume only:
C:\\UnityProjects\\NoSafeCircleAgentCrew\\{request.task_id}
(or the explicitly configured test/operator checkout root).

It may not create or alter a GitHub Issue or claim. If next_action is claim_task, stop and
report claim_task. It may not plan paths, run ExecutionCrew, edit files, apply a patch, run
Unity, commit, push, merge, package evidence, or claim conformance.

LOOP
1. Call observe_goal_state.
2. If the deterministic facts require prepare_checkout, call prepare_task_checkout once.
3. After any preparation call, call observe_goal_state again.
4. Stop when the exact next action is claim_task, validate_scope, needs_human, or blocked.
5. Never invent task IDs, paths, branches, hashes, Issue state, or statuses.

OUTPUT
- schema_version exactly {TASK_REVIEW_SCHEMA_VERSION};
- task_id exactly {request.task_id};
- observation_sha256 and checkout_sha256 copied from the final observation;
- next_action matching the final deterministic state;
- concrete reasons;
- authority exactly checkout_preparation_only.
""".strip()

    calls_before = len(workflow.action_log)
    agent = Agent(
        name="No Safe Circle Checkout Supervisor",
        model=model or os.getenv("TASK_REVIEW_AGENT_MODEL", DEFAULT_MODEL),
        instructions=instructions,
        tools=[observe_goal_state, prepare_task_checkout],
        output_type=CheckoutAssessmentModel,
        model_settings=ModelSettings(tool_choice="required"),
    )
    result = Runner.run_sync(
        agent,
        f"Advance {request.task_id} through the bounded claim/checkout stage.",
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
        "authority": "checkout_preparation_only",
    }
    for field, expected_value in fixed_checks.items():
        if payload.get(field) != expected_value:
            raise TaskReviewContractError(
                "OpenAI checkout assessment did not match deterministic "
                f"{field}: {payload.get(field)!r} != {expected_value!r}"
            )

    if expected.action.value == "validate_scope":
        if "prepare_task_checkout" not in workflow.action_log[calls_before:]:
            raise TaskReviewContractError(
                "OpenAI checkout agent claimed validate_scope without "
                "preparing/resuming checkout"
            )
        if observation["checkout"].get("status") != "ready":
            raise TaskReviewContractError(
                "OpenAI checkout agent reached validate_scope without a ready checkout"
            )

    return {
        **fixed_checks,
        "reasons": list(expected.reasons),
        "model_reasons": list(payload.get("reasons") or []),
        "checkout_preparation": workflow.last_checkout_result,
    }
