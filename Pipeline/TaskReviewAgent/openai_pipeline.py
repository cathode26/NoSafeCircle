"""OpenAI Agents SDK supervisor for the real task-to-human-Unity pipeline."""

from __future__ import annotations

import os
from typing import Any

from .contracts import TASK_REVIEW_SCHEMA_VERSION, TaskReviewContractError, TaskReviewRequest
from .openai_agent import DEFAULT_MODEL, _json, _require_runtime
from .production_pipeline import ProductionTaskController


class OpenAIProductionPipelineError(TaskReviewContractError):
    """Raised when the model output disagrees with deterministic workflow state."""


def run_openai_production_pipeline(
    request: TaskReviewRequest,
    controller: ProductionTaskController,
    *,
    model: str | None = None,
    max_turns: int = 80,
) -> dict[str, Any]:
    """Drive one explicit or queue-selected task to a committed human Unity handoff."""

    Agent, _, Runner, function_tool, pydantic_types = _require_runtime(max_turns)
    BaseModel, ConfigDict = pydantic_types

    class PipelineOutcomeModel(BaseModel):
        model_config = ConfigDict(extra="forbid")

        schema_version: str
        task_id: str
        status: str
        issue_url: str | None
        branch: str | None
        commit: str | None
        next_action: str
        blockers: list[str]
        authority: str

    observations_before = len(controller.workflow.action_log)

    @function_tool
    def observe_goal_state() -> str:
        """Read current Git, TaskGraph, Issue, checkout, scope, crew, and integration state."""

        return _json(controller.observe())

    @function_tool
    def acquire_agent_lease(planned_approach: str, expected_validation: str) -> str:
        """Reserve the managed Issue for this worker after eligibility/resource checks."""

        return _json(
            controller.acquire_agent_lease(
                planned_approach=planned_approach,
                expected_validation=expected_validation,
            )
        )

    @function_tool
    def prepare_task_checkout() -> str:
        """Create or resume the exact canonical task checkout and deterministic branch."""

        return _json(controller.prepare_task_checkout())

    @function_tool
    def repository_facts() -> str:
        """Read task-owned resource hints and relevant implementation/test file suggestions."""

        return _json(controller.repository_facts())

    @function_tool
    def list_repository_files(prefix: str, limit: int = 200) -> str:
        """List committed files under one approved repository prefix."""

        return _json(controller.list_repository_files(prefix=prefix, limit=limit))

    @function_tool
    def search_repository(
        query: str,
        prefixes: list[str],
        limit: int = 80,
    ) -> str:
        """Search committed text under approved roots without shell or write authority."""

        return _json(
            controller.search_repository(query=query, prefixes=prefixes, limit=limit)
        )

    @function_tool
    def read_repository_file(
        path: str,
        start_line: int = 1,
        end_line: int = 400,
    ) -> str:
        """Read a bounded line range from one committed text file."""

        return _json(
            controller.read_repository_file(
                path=path,
                start_line=start_line,
                end_line=end_line,
            )
        )

    @function_tool
    def latest_human_feedback() -> str:
        """Read the latest validated PASS/FAIL comment when the Issue is in repair/delivery."""

        return _json(controller.latest_human_feedback())

    @function_tool
    def validate_execution_scope(
        existing_implementation_paths: list[str],
        new_implementation_paths: list[str],
        existing_test_paths: list[str],
        new_test_paths: list[str],
    ) -> str:
        """Mint a plan ID only for exact safe implementation/test file authority."""

        try:
            result = controller.validate_execution_scope(
                existing_implementation_paths=existing_implementation_paths,
                new_implementation_paths=new_implementation_paths,
                existing_test_paths=existing_test_paths,
                new_test_paths=new_test_paths,
            )
        except TaskReviewContractError as exc:
            result = {"accepted": False, "reasons": [str(exc)], "plan_id": None}
        return _json(result)

    @function_tool
    def run_execution_crew(
        plan_id: str,
        retry_run_id: str | None = None,
        feedback_file: str | None = None,
    ) -> str:
        """Run the existing Contract Auditor/Implementer/Test Author/Validator pipeline."""

        return _json(
            controller.run_execution_crew(
                plan_id=plan_id,
                retry_run_id=retry_run_id,
                feedback_file=feedback_file,
            )
        )

    @function_tool
    def integrate_commit_push_and_handoff(
        run_id: str,
        implementation_summary: str,
        human_steps: list[str],
        expected_result: str,
    ) -> str:
        """Verify/apply candidate, commit/push branch, and publish Vincent's Issue checklist."""

        return _json(
            controller.integrate_commit_push_and_handoff(
                run_id=run_id,
                implementation_summary=implementation_summary,
                human_steps=human_steps,
                expected_result=expected_result,
            )
        )

    @function_tool
    def record_pipeline_blocker(summary: str, details: list[str]) -> str:
        """Persist a genuine design/contract/operational blocker in the managed Issue."""

        return _json(controller.record_pipeline_blocker(summary=summary, details=details))

    instructions = f"""
You are the No Safe Circle goal-oriented production task supervisor.

GOAL
Take exact task {request.task_id} through the existing repository pipeline until the agent has:
1. acquired the durable Issue lease;
2. created or resumed the canonical task checkout and branch;
3. selected the smallest exact implementation and Unity-test file surface;
4. run the existing ExecutionCrew;
5. received crew_status=review_ready;
6. deterministically applied candidate.patch;
7. committed and pushed the exact task branch; and
8. changed the managed Issue to human_action_required with concrete Unity steps for Vincent.

YOU DO NOT WRITE GAME CODE DIRECTLY
The only code-writing authority belongs to ExecutionCrew. You have bounded repository read/search,
exact scope validation, ExecutionCrew invocation, candidate integration, Git commit/push, and Issue
handoff tools. Never claim a tool action occurred without its returned proof.

OPERATING LOOP
- Always call observe_goal_state first and after lease or checkout changes.
- Follow production_pipeline.next_action. Never skip a prerequisite.
- If the task/dependencies are not eligible, return needs_human without claiming another task.
- Acquire a lease with a concrete Unity implementation approach and expected validation.
- Read Docs/Engineering/UNITY_TESTING_POLICY.md and
  Docs/AI-Pipeline/UNITY_PROGRAMMER_LANGUAGE.md before proposing scope.
- Start scope discovery from exclusive resources and repository_facts. Search/read enough current
  code and tests to identify exact files. Keep scope minimal.
- Correct existing/new classification using deterministic validation findings. Never scaffold a
  file merely to make it existing. Never include .meta; ExecutionCrew owns new Assets sidecars.
- Implementation and test scopes must be disjoint. Tests must include at least one C# test file.
- Run ExecutionCrew only with a returned plan_id.
- crew_status=review_ready is semantic candidate approval, not yet a commit or human validation.
- For contract_review_required, blocked, rejected, or needs_human, record_pipeline_blocker with
  exact result reasons/artifact identity. Do not fabricate a candidate.
- For review_ready, call integrate_commit_push_and_handoff exactly once. Give Vincent numbered,
  executable Unity steps derived from the task completion gates. State the exact expected result.
- Stop after the Issue is human_action_required. Do not run Unity, merge, deliver, or claim
  TaskGraph conformance.

HUMAN HANDOFF QUALITY
The implementation summary must name concrete Unity scripts/components/behavior and tests. The
human steps must say which checkout/scene to open, what to do in Play Mode, and what observable
behavior counts as PASS. Do not ask Vincent to inspect raw patches or finish implementation.

FINAL OUTPUT
Return schema_version={TASK_REVIEW_SCHEMA_VERSION}, task_id={request.task_id}, and authority
exactly committed_branch_to_human_unity_handoff. status must be human_action_required,
needs_human, or blocked. For human_action_required, copy the exact Issue URL, branch, and commit
from final deterministic state and leave blockers empty.
""".strip()

    agent = Agent(
        name="No Safe Circle Production Task Supervisor",
        model=model or os.getenv("TASK_REVIEW_AGENT_MODEL", DEFAULT_MODEL),
        instructions=instructions,
        tools=[
            observe_goal_state,
            acquire_agent_lease,
            prepare_task_checkout,
            repository_facts,
            list_repository_files,
            search_repository,
            read_repository_file,
            latest_human_feedback,
            validate_execution_scope,
            run_execution_crew,
            integrate_commit_push_and_handoff,
            record_pipeline_blocker,
        ],
        output_type=PipelineOutcomeModel,
    )

    result = Runner.run_sync(
        agent,
        f"Advance {request.task_id} to its durable human Unity validation handoff.",
        max_turns=max_turns,
    )
    final_output = result.final_output
    if not isinstance(final_output, PipelineOutcomeModel):
        raise OpenAIProductionPipelineError(
            "OpenAI production supervisor did not return the required structured output"
        )
    if len(controller.workflow.action_log) <= observations_before:
        raise OpenAIProductionPipelineError(
            "OpenAI production supervisor returned without observing workflow state"
        )

    payload = final_output.model_dump(mode="json")
    if payload.get("schema_version") != TASK_REVIEW_SCHEMA_VERSION:
        raise OpenAIProductionPipelineError("model changed schema_version")
    if payload.get("task_id") != request.task_id:
        raise OpenAIProductionPipelineError("model changed explicit task identity")
    if payload.get("authority") != "committed_branch_to_human_unity_handoff":
        raise OpenAIProductionPipelineError("model changed final authority boundary")

    final_observation = controller.observe()
    state = ((final_observation.get("coordination") or {}).get("workflow_state") or {})
    deterministic_status = (final_observation.get("production_pipeline") or {}).get("status")
    if payload.get("status") == "human_action_required":
        if deterministic_status != "human_action_required" or state.get("state") != "human_action_required":
            raise OpenAIProductionPipelineError(
                "model claimed human handoff before deterministic Issue state reached it"
            )
        fixed = {
            "issue_url": (final_observation.get("coordination") or {}).get("issue_url"),
            "branch": state.get("branch"),
            "commit": state.get("head_commit"),
        }
        for field, expected in fixed.items():
            if payload.get(field) != expected:
                raise OpenAIProductionPipelineError(
                    f"model changed final {field}: {payload.get(field)!r} != {expected!r}"
                )
        if payload.get("blockers"):
            raise OpenAIProductionPipelineError("human_action_required cannot contain blockers")
    elif payload.get("status") not in ("needs_human", "blocked"):
        raise OpenAIProductionPipelineError("model returned unsupported final status")
    return {
        **payload,
        "deterministic_final_state": final_observation,
    }
