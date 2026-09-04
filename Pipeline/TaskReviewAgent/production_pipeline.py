"""Production controller from durable Issue state through committed human handoff."""

from __future__ import annotations

import json
from typing import Any, Iterable

from .candidate_integration import CandidateIntegrator
from .contracts import ExecutionScopePlan, TaskReviewContractError
from .execution_bridge import ExecutionCrewBridge
from .issue_workflow import (
    WorkflowActor,
    WorkflowEventType,
    WorkflowState,
    labels_for_state,
    parse_human_validation_result,
    render_event_comment,
    transition,
    update_issue_body,
    utc_now,
)
from .real_workflow import RealTaskReviewWorkflow
from .repository_scope import RepositoryScopeAuthority


class ProductionPipelineError(TaskReviewContractError):
    """Raised when the production task controller cannot safely advance."""


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _workflow_state(observation: dict[str, Any]) -> dict[str, Any] | None:
    coordination = observation.get("coordination")
    if not isinstance(coordination, dict):
        return None
    state = coordination.get("workflow_state")
    return state if isinstance(state, dict) else None


class ProductionTaskController:
    """Use existing pipeline authority and stop only at the human Unity boundary."""

    def __init__(
        self,
        *,
        workflow: RealTaskReviewWorkflow,
        execution_provider: str,
        execution_model: str | None = None,
        execution_reasoning_effort: str | None = None,
        execution_command_runner=None,
        execution_session_pool_owner=None,
        enable_execution_session_pool: bool | None = None,
    ) -> None:
        self.workflow = workflow
        self.task_id = workflow.task_id
        self.execution_provider = str(execution_provider).strip().casefold()
        if self.execution_provider not in ("claude", "codex"):
            raise ProductionPipelineError("execution_provider must be claude or codex")
        self.execution_model = (
            str(execution_model).strip() if execution_model else None
        )
        self.execution_reasoning_effort = (
            str(execution_reasoning_effort).strip()
            if execution_reasoning_effort
            else None
        )
        if self.execution_reasoning_effort is not None and self.execution_provider != "codex":
            raise ProductionPipelineError(
                "execution_reasoning_effort is supported only for codex"
            )
        self.execution_command_runner = execution_command_runner
        self.execution_session_pool_owner = execution_session_pool_owner
        self.enable_execution_session_pool = enable_execution_session_pool
        self.scope: RepositoryScopeAuthority | None = None
        self.execution: ExecutionCrewBridge | None = None
        self.integrator: CandidateIntegrator | None = None
        self.last_observation: dict[str, Any] | None = None
        self.last_handoff: dict[str, Any] | None = None

    def observe(self) -> dict[str, Any]:
        observation = self.workflow.observe_goal_state()
        state = _workflow_state(observation)
        checkout = observation.get("checkout") or {}
        coordination = observation.get("coordination") or {}
        self.scope = None
        self.execution = None
        self.integrator = None

        if (
            isinstance(state, dict)
            and state.get("state") == "agent_working"
            and state.get("worker_id") == self.workflow.worker_id
            and type(state.get("lease_id")) is str
            and coordination.get("status") == "claimed_by_worker"
            and checkout.get("status") == "ready"
        ):
            branch = str(checkout.get("branch") or checkout.get("expected_branch") or "")
            self.scope = RepositoryScopeAuthority(
                checkout=checkout["path"],
                task=observation["task"],
                lease_id=state["lease_id"],
                expected_branch=branch,
            )
            self.execution = ExecutionCrewBridge(
                checkout=checkout["path"],
                scope=self.scope,
                execution_model=self.execution_model,
                execution_reasoning_effort=self.execution_reasoning_effort,
                command_runner=self.execution_command_runner,
                worker_slot_id=self.workflow.worker_id,
                session_pool_owner=self.execution_session_pool_owner,
                enable_session_pool=(
                    self.execution_command_runner is None
                    if self.enable_execution_session_pool is None
                    else self.enable_execution_session_pool
                ),
            )
            self.integrator = CandidateIntegrator(
                checkout=checkout["path"],
                branch=branch,
                task_title=str(observation["task"].get("title") or self.task_id),
                scope=self.scope,
                execution=self.execution,
            )
            observation["repository_scope_facts"] = self.scope.facts()
            observation["accepted_plan_id"] = (
                self.scope.accepted.plan_id if self.scope.accepted is not None else None
            )
            observation["execution_run"] = (
                self.execution.receipt.to_dict()
                if self.execution.receipt is not None
                else None
            )
            observation["candidate_integration"] = (
                self.integrator.receipt.to_dict()
                if self.integrator.receipt is not None
                else None
            )
        else:
            observation["candidate_integration"] = None

        observation["production_pipeline"] = self._pipeline_status(observation)
        self.last_observation = _copy(observation)
        return _copy(observation)

    def _pipeline_status(self, observation: dict[str, Any]) -> dict[str, Any]:
        state = _workflow_state(observation)
        if state is not None and state.get("state") == "human_action_required":
            return {
                "status": "human_action_required",
                "next_action": "Vincent completes the Issue checklist.",
            }
        coordination = observation.get("coordination") or {}
        if coordination.get("status") in ("available_unassigned", "available_missing"):
            return {"status": "agent_ready", "next_action": "acquire_agent_lease"}
        checkout = observation.get("checkout") or {}
        if coordination.get("status") == "claimed_by_worker" and checkout.get("status") != "ready":
            return {"status": "agent_working", "next_action": "prepare_task_checkout"}
        if self.scope is None:
            return {"status": "not_ready", "next_action": "inspect blockers"}
        if self.scope.accepted is None:
            return {"status": "agent_working", "next_action": "validate_execution_scope"}
        if self.execution is None or self.execution.receipt is None:
            return {"status": "agent_working", "next_action": "run_execution_crew"}
        if self.execution.receipt.crew_status != "review_ready":
            return {
                "status": "agent_working",
                "next_action": "record_pipeline_blocker",
                "crew_status": self.execution.receipt.crew_status,
                "reasons": list(self.execution.receipt.rejection_reasons),
            }
        if self.integrator is None or self.integrator.receipt is None:
            return {
                "status": "agent_working",
                "next_action": "integrate_commit_push_and_handoff",
            }
        return {
            "status": "agent_working",
            "next_action": "publish_human_handoff",
        }

    def acquire_agent_lease(
        self,
        *,
        planned_approach: str,
        expected_validation: str,
    ) -> dict[str, Any]:
        return self.workflow.acquire_agent_lease(
            planned_approach=planned_approach,
            expected_validation=expected_validation,
        )

    def prepare_task_checkout(self) -> dict[str, Any]:
        return self.workflow.prepare_task_checkout()

    def repository_facts(self) -> dict[str, Any]:
        return self._require_scope().facts()

    def list_repository_files(self, *, prefix: str, limit: int = 200) -> dict[str, Any]:
        return self._require_scope().list_files(prefix=prefix, limit=limit)

    def search_repository(
        self,
        *,
        query: str,
        prefixes: Iterable[str],
        limit: int = 80,
    ) -> dict[str, Any]:
        return self._require_scope().search(query=query, prefixes=prefixes, limit=limit)

    def read_repository_file(
        self,
        *,
        path: str,
        start_line: int = 1,
        end_line: int = 400,
    ) -> dict[str, Any]:
        return self._require_scope().read_file(
            path=path,
            start_line=start_line,
            end_line=end_line,
        )

    def validate_execution_scope(
        self,
        *,
        existing_implementation_paths: Iterable[str],
        new_implementation_paths: Iterable[str],
        existing_test_paths: Iterable[str],
        new_test_paths: Iterable[str],
    ) -> dict[str, Any]:
        plan = ExecutionScopePlan(
            tuple(existing_implementation_paths),
            tuple(new_implementation_paths),
            tuple(existing_test_paths),
            tuple(new_test_paths),
        )
        return self._require_scope().validate(plan).to_dict()

    def run_execution_crew(
        self,
        *,
        plan_id: str,
        retry_run_id: str | None = None,
        feedback_file: str | None = None,
    ) -> dict[str, Any]:
        receipt = self._require_execution().run(
            plan_id=plan_id,
            provider=self.execution_provider,
            retry_run_id=retry_run_id,
            feedback_file=feedback_file,
        )
        return receipt.to_dict()

    def integrate_commit_push_and_handoff(
        self,
        *,
        run_id: str,
        implementation_summary: str,
        human_steps: Iterable[str],
        expected_result: str,
    ) -> dict[str, Any]:
        receipt = self._require_integrator().integrate(run_id)
        summary = "\n".join(
            (
                implementation_summary.strip(),
                "",
                "### Pipeline identity",
                f"- **ExecutionCrew run:** `{receipt.run_id}`",
                f"- **Execution provider:** `{receipt.provider}`",
                f"- **Candidate SHA-256:** `{receipt.candidate_sha256}`",
                f"- **Verified changed paths:** `{len(receipt.changed_paths)}`",
            )
        )
        handoff = self.workflow.publish_human_handoff(
            branch=receipt.branch,
            head_commit=receipt.commit,
            implementation_summary=summary,
            completed_checks=list(receipt.completed_checks),
            human_steps=list(human_steps),
            expected_result=expected_result,
        )
        self.last_handoff = _copy(handoff)
        return {
            "status": "human_action_required",
            "integration": receipt.to_dict(),
            "handoff": handoff,
        }

    def record_pipeline_blocker(
        self,
        *,
        summary: str,
        details: Iterable[str],
    ) -> dict[str, Any]:
        service = self.workflow.issue_workflow
        if service is None:
            raise ProductionPipelineError("Issue workflow is unavailable")
        snapshot = service.find(self.task_id)
        if snapshot is None or not snapshot.valid or snapshot.state is None:
            raise ProductionPipelineError("pipeline blocker requires a valid managed Issue")
        state = snapshot.state
        if state.state is not WorkflowState.AGENT_WORKING or state.worker_id != self.workflow.worker_id:
            raise ProductionPipelineError("pipeline blocker requires this worker's active lease")
        reason_lines = [str(item).strip() for item in details if str(item).strip()]
        next_state, event = transition(
            state,
            event_type=WorkflowEventType.BLOCKED,
            actor_type=WorkflowActor.AGENT,
            actor_id=self.workflow.worker_id,
            to_state=WorkflowState.BLOCKED,
            details={
                "summary": summary.strip(),
                "details": reason_lines,
            },
            now=utc_now(),
        )
        service.backend.add_comment(
            snapshot.issue_number,
            render_event_comment(
                event,
                "\n".join(
                    (
                        "The production pipeline stopped at a bounded blocker.",
                        "",
                        "### Summary",
                        summary.strip(),
                        "",
                        "### Details",
                        *([f"- {item}" for item in reason_lines] or ["- No details recorded."]),
                    )
                ),
            ),
        )
        service.backend.update_issue(
            snapshot.issue_number,
            body=update_issue_body(
                snapshot.body,
                next_state,
                next_action="Review and resolve the recorded blocker, then return the Issue to agent-ready.",
            ),
            labels=labels_for_state(next_state.state, snapshot.labels),
            assignees=[service.assignee],
        )
        verified = service.verify_post_mutation_state(
            self.task_id,
            next_state,
            transition_name="pipeline blocker",
        )
        return {"status": "blocked", **verified.to_dict()}

    def latest_human_feedback(self) -> dict[str, Any] | None:
        service = self.workflow.issue_workflow
        if service is None:
            return None
        snapshot = service.find(self.task_id)
        if snapshot is None:
            return None
        for comment in reversed(service.backend.get_comments(snapshot.issue_number)):
            body = comment.get("body") if isinstance(comment, dict) else None
            if type(body) is not str:
                continue
            result = parse_human_validation_result(body)
            if result is not None:
                return {
                    "result": result.result,
                    "tested_commit": result.tested_commit,
                    "body": result.body,
                }
        return None

    def _require_scope(self) -> RepositoryScopeAuthority:
        if self.scope is None:
            raise ProductionPipelineError(
                "repository tools require an active lease and ready canonical checkout; observe first"
            )
        return self.scope

    def _require_execution(self) -> ExecutionCrewBridge:
        if self.execution is None:
            raise ProductionPipelineError("ExecutionCrew requires a ready repository scope")
        return self.execution

    def _require_integrator(self) -> CandidateIntegrator:
        if self.integrator is None:
            raise ProductionPipelineError("candidate integration requires a verified ExecutionCrew run")
        return self.integrator
