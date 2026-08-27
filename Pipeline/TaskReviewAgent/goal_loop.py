"""Deterministic goal loop used to prove the bounded TaskReviewAgent slices."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Protocol

from .contracts import (
    CrewStatus,
    ExecutionScopePlan,
    OutcomeStatus,
    TaskReviewContractError,
    TaskReviewOutcome,
    TaskReviewRequest,
)


class GoalAction(str, Enum):
    PREPARE_CHECKOUT = "prepare_checkout"
    VALIDATE_SCOPE = "validate_scope"
    RUN_EXECUTION_CREW = "run_execution_crew"
    VERIFY_HUMAN_REVIEW_READY = "verify_human_review_ready"
    COMPLETE = "complete"
    NEEDS_HUMAN = "needs_human"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class GoalAssessment:
    action: GoalAction
    reasons: tuple[str, ...] = ()


class TaskReviewToolSurface(Protocol):
    action_log: list[str]

    def observe_goal_state(self) -> dict[str, Any]: ...

    def prepare_task_checkout(self) -> dict[str, Any]: ...

    def validate_execution_scope(self, plan: ExecutionScopePlan): ...

    def run_execution_crew(self, plan_id: str): ...

    def verify_human_review_ready(self, run_id: str): ...

    def require_known_proof(self, proof): ...


class ScopePlanner(Protocol):
    def candidate_plans(
        self,
        request: TaskReviewRequest,
        observation: dict[str, Any],
    ) -> Iterable[ExecutionScopePlan]: ...


class ScriptedScopePlanner:
    """Provides one wrong classification followed by the corrected scope."""

    def candidate_plans(
        self,
        request: TaskReviewRequest,
        observation: dict[str, Any],
    ) -> Iterable[ExecutionScopePlan]:
        facts = observation["repository_scope_facts"]
        implementations = tuple(facts["existing_implementation_paths"])
        absent_test = tuple(facts["absent_test_paths"])
        yield ExecutionScopePlan(
            existing_implementation_paths=implementations,
            new_implementation_paths=(),
            existing_test_paths=absent_test,
            new_test_paths=(),
        )
        yield ExecutionScopePlan(
            existing_implementation_paths=implementations,
            new_implementation_paths=(),
            existing_test_paths=(),
            new_test_paths=absent_test,
        )


def assess_goal_state(observation: dict[str, Any]) -> GoalAssessment:
    environment = observation.get("environment") or {}
    if not environment.get("ready"):
        reasons = tuple(environment.get("errors") or ())
        return GoalAssessment(
            GoalAction.BLOCKED,
            reasons or ("task-review environment is not ready",),
        )
    if not environment.get("controller_clean"):
        return GoalAssessment(GoalAction.BLOCKED, ("controller checkout is not clean",))
    if not environment.get("taskgraph_valid"):
        return GoalAssessment(GoalAction.BLOCKED, ("TaskGraph validation failed",))

    provider_auth_required = environment.get("provider_auth_required", True)
    if provider_auth_required is not False and not environment.get(
        "provider_auth_available"
    ):
        return GoalAssessment(
            GoalAction.BLOCKED,
            ("ExecutionCrew provider authentication is unavailable",),
        )

    task = observation.get("task") or {}
    eligibility = {
        "contract_disposition": "active",
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "derived_state": "not_delivered",
    }
    failures = [
        f"{field}={task.get(field)!r}; expected {expected!r}"
        for field, expected in eligibility.items()
        if task.get(field) != expected
    ]
    if task.get("dependencies_conformant") is not True:
        dependency_states = task.get("dependency_states") or []
        nonconformant = [
            f"{item.get('task_id')}={item.get('state')}"
            for item in dependency_states
            if item.get("state") != "conformant"
        ]
        failures.append(
            "one or more declared dependencies are not conformant"
            + (f": {', '.join(nonconformant)}" if nonconformant else "")
        )
    if failures:
        return GoalAssessment(GoalAction.NEEDS_HUMAN, tuple(failures))

    checkout = observation.get("checkout") or {}
    if checkout.get("status") != "ready":
        return GoalAssessment(GoalAction.PREPARE_CHECKOUT)

    run = observation.get("execution_run")
    if run is None:
        if observation.get("accepted_plan_id") is None:
            return GoalAssessment(GoalAction.VALIDATE_SCOPE)
        return GoalAssessment(GoalAction.RUN_EXECUTION_CREW)

    status = run.get("crew_status")
    if status == CrewStatus.REVIEW_READY.value:
        return GoalAssessment(GoalAction.VERIFY_HUMAN_REVIEW_READY)
    if status in (
        CrewStatus.CONTRACT_REVIEW_REQUIRED.value,
        CrewStatus.NEEDS_HUMAN.value,
    ):
        return GoalAssessment(
            GoalAction.NEEDS_HUMAN,
            tuple(run.get("reasons") or ("ExecutionCrew reached a human authority boundary",)),
        )
    return GoalAssessment(
        GoalAction.BLOCKED,
        tuple(run.get("reasons") or (f"ExecutionCrew ended with {status}",)),
    )


def verify_agent_outcome(
    tools: TaskReviewToolSurface,
    outcome: TaskReviewOutcome,
) -> TaskReviewOutcome:
    if outcome.status is OutcomeStatus.HUMAN_REVIEW_READY:
        assert outcome.proof is not None
        tools.require_known_proof(outcome.proof)
    return outcome


def run_scripted_vertical_slice(
    request: TaskReviewRequest,
    tools: TaskReviewToolSurface,
    planner: ScopePlanner,
    *,
    max_steps: int = 12,
) -> TaskReviewOutcome:
    """Drive the fake pipeline to the human review boundary without an API call."""

    if type(max_steps) is not int or not 1 <= max_steps <= 100:
        raise TaskReviewContractError("max_steps must be an integer from 1 through 100")

    scope_candidates: list[ExecutionScopePlan] | None = None
    scope_index = 0

    for _ in range(max_steps):
        observation = tools.observe_goal_state()
        assessment = assess_goal_state(observation)

        if assessment.action is GoalAction.PREPARE_CHECKOUT:
            tools.prepare_task_checkout()
            continue

        if assessment.action is GoalAction.VALIDATE_SCOPE:
            if scope_candidates is None:
                scope_candidates = list(planner.candidate_plans(request, observation))
                if not scope_candidates:
                    return TaskReviewOutcome(
                        OutcomeStatus.NEEDS_HUMAN,
                        request.task_id,
                        "No bounded implementation/test path plan could be proposed.",
                        None,
                        ("scope planner returned no candidate plans",),
                    )
            if scope_index >= len(scope_candidates):
                return TaskReviewOutcome(
                    OutcomeStatus.NEEDS_HUMAN,
                    request.task_id,
                    "Every bounded implementation/test path plan was rejected.",
                    None,
                    ("scope validation budget exhausted",),
                )
            result = tools.validate_execution_scope(scope_candidates[scope_index])
            scope_index += 1
            if not result.accepted:
                continue
            continue

        if assessment.action is GoalAction.RUN_EXECUTION_CREW:
            plan_id = observation.get("accepted_plan_id")
            if type(plan_id) is not str:
                raise TaskReviewContractError("accepted plan observation is missing plan_id")
            tools.run_execution_crew(plan_id)
            continue

        if assessment.action is GoalAction.VERIFY_HUMAN_REVIEW_READY:
            run = observation["execution_run"]
            proof = tools.verify_human_review_ready(run["run_id"])
            outcome = TaskReviewOutcome(
                OutcomeStatus.HUMAN_REVIEW_READY,
                request.task_id,
                (
                    "ExecutionCrew produced a review-ready candidate patch. The patch remains "
                    "review-only and has not been applied."
                ),
                proof,
                (),
            )
            return verify_agent_outcome(tools, outcome)

        if assessment.action is GoalAction.NEEDS_HUMAN:
            return TaskReviewOutcome(
                OutcomeStatus.NEEDS_HUMAN,
                request.task_id,
                "The task reached a human authority boundary before candidate review.",
                None,
                assessment.reasons,
            )

        if assessment.action is GoalAction.BLOCKED:
            return TaskReviewOutcome(
                OutcomeStatus.BLOCKED,
                request.task_id,
                "The task-review workflow is blocked by an operational failure.",
                None,
                assessment.reasons,
            )

    return TaskReviewOutcome(
        OutcomeStatus.BLOCKED,
        request.task_id,
        "The task-review workflow exhausted its bounded goal-loop budget.",
        None,
        (f"max_steps exhausted: {max_steps}",),
    )
