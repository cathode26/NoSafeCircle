"""OpenAI Agents SDK adapter over the bounded TaskReviewAgent tool surface."""

from __future__ import annotations

import json
import os
from importlib import metadata
from typing import Any

from .contracts import (
    ExecutionScopePlan,
    OutcomeStatus,
    TASK_REVIEW_SCHEMA_VERSION,
    TaskReviewContractError,
    TaskReviewOutcome,
    TaskReviewRequest,
)
from .goal_loop import TaskReviewToolSurface, verify_agent_outcome


TESTED_OPENAI_AGENTS_VERSION = "0.22.0"
DEFAULT_MODEL = "gpt-5.6"


class OpenAIAgentsUnavailable(RuntimeError):
    """Raised when the optional OpenAI Agents SDK runtime is not installed."""


def installed_agents_version() -> str | None:
    try:
        return metadata.version("openai-agents")
    except metadata.PackageNotFoundError:
        return None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)


def run_openai_fake_agent(
    request: TaskReviewRequest,
    tools: TaskReviewToolSurface,
    *,
    model: str | None = None,
    max_turns: int = 24,
) -> TaskReviewOutcome:
    """Use a real OpenAI agent to navigate only the deterministic fake tool surface."""

    if not os.getenv("OPENAI_API_KEY"):
        raise OpenAIAgentsUnavailable("OPENAI_API_KEY is required for --mode openai-fake")
    if type(max_turns) is not int or not 4 <= max_turns <= 100:
        raise TaskReviewContractError("max_turns must be an integer from 4 through 100")

    try:
        from agents import Agent, Runner, function_tool
        from pydantic import BaseModel, ConfigDict
    except ImportError as exc:
        raise OpenAIAgentsUnavailable(
            "OpenAI Agents SDK is not installed. Run: "
            "python -m pip install -r Pipeline/TaskReviewAgent/requirements.txt"
        ) from exc

    class HumanReviewProofModel(BaseModel):
        model_config = ConfigDict(extra="forbid")

        proof_id: str
        task_id: str
        run_id: str
        source_head: str
        task_contract_sha256: str
        candidate_patch_path: str
        candidate_sha256: str
        apply_check_passed: bool
        source_unchanged: bool
        authority: str

    class TaskReviewOutcomeModel(BaseModel):
        model_config = ConfigDict(extra="forbid")

        schema_version: str
        status: str
        task_id: str
        summary: str
        proof: HumanReviewProofModel | None
        blockers: list[str]

    @function_tool
    def observe_goal_state() -> str:
        """Read the current fake environment, task, checkout, plan, and ExecutionCrew state."""

        return _json(tools.observe_goal_state())

    @function_tool
    def prepare_task_checkout() -> str:
        """Create or resume the canonical isolated task checkout in the fake environment."""

        return _json(tools.prepare_task_checkout())

    @function_tool
    def validate_execution_scope(
        existing_implementation_paths: list[str],
        new_implementation_paths: list[str],
        existing_test_paths: list[str],
        new_test_paths: list[str],
    ) -> str:
        """Validate an exact bounded implementation/test path plan before ExecutionCrew."""

        try:
            plan = ExecutionScopePlan(
                tuple(existing_implementation_paths),
                tuple(new_implementation_paths),
                tuple(existing_test_paths),
                tuple(new_test_paths),
            )
        except TaskReviewContractError as exc:
            return _json({"accepted": False, "reasons": [str(exc)], "plan_id": None})
        return _json(tools.validate_execution_scope(plan).to_dict())

    @function_tool
    def run_execution_crew(plan_id: str) -> str:
        """Run fake ExecutionCrew using only a previously validated plan ID."""

        return _json(tools.run_execution_crew(plan_id).to_dict())

    @function_tool
    def verify_human_review_ready(run_id: str) -> str:
        """Mint deterministic proof only for a verified review_ready ExecutionCrew run."""

        return _json(tools.verify_human_review_ready(run_id).to_dict())

    instructions = f"""
You are the No Safe Circle Task Review Supervisor.

GOAL
Use the supplied tools to move explicit task {request.task_id} from its observed current
state to the existing pipeline's human candidate-review boundary.

SUCCESS MEANS ONLY THIS
- the exact task is eligible;
- its canonical isolated checkout is ready;
- an exact implementation/test path plan was deterministically accepted;
- ExecutionCrew returned crew_status=review_ready;
- verify_human_review_ready returned a proof object;
- the patch remains review_only_not_applied.

OPERATING RULES
1. Call observe_goal_state before taking any action and after every state-changing tool call.
2. Never invent a plan_id, run_id, proof_id, file path, hash, checkout, or status.
3. When scope validation rejects a plan, correct the existing/new path classification using
   the rejection reasons and current observation. Do not bypass validation.
4. Never claim that Unity ran, that a patch was applied, that code was committed, or that the
   task is delivered or conformant.
5. Return human_review_ready only after calling verify_human_review_ready and copying its
   exact proof object into the final result.
6. At a design/contract authority boundary, return needs_human with concrete blockers.
7. At an operational failure, return blocked with concrete blockers.
8. The final task_id must remain exactly {request.task_id}.
9. The final schema_version must be {TASK_REVIEW_SCHEMA_VERSION}.
""".strip()

    agent = Agent(
        name="No Safe Circle Task Review Supervisor",
        model=model or os.getenv("TASK_REVIEW_AGENT_MODEL", DEFAULT_MODEL),
        instructions=instructions,
        tools=[
            observe_goal_state,
            prepare_task_checkout,
            validate_execution_scope,
            run_execution_crew,
            verify_human_review_ready,
        ],
        output_type=TaskReviewOutcomeModel,
    )

    result = Runner.run_sync(
        agent,
        (
            f"Take {request.task_id} to deterministic human candidate review using only the "
            "available fake pipeline tools."
        ),
        max_turns=max_turns,
    )
    final_output = result.final_output
    if not isinstance(final_output, TaskReviewOutcomeModel):
        raise TaskReviewContractError("OpenAI agent did not return the required structured output")

    payload = final_output.model_dump(mode="json")
    outcome = TaskReviewOutcome.from_dict(payload)
    if outcome.task_id != request.task_id:
        raise TaskReviewContractError("OpenAI agent changed the explicit task identity")
    return verify_agent_outcome(tools, outcome)


def describe_runtime() -> dict[str, Any]:
    version = installed_agents_version()
    return {
        "installed": version is not None,
        "installed_version": version,
        "tested_version": TESTED_OPENAI_AGENTS_VERSION,
        "default_model": DEFAULT_MODEL,
    }
