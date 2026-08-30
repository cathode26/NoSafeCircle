"""Stage 3: cross exactly one mutation boundary for generic no-TaskId dispatch.

Stage 2 (:mod:`dispatch_plan`) is a read-only planner: it decides whether the
generic command should resume existing durable work or which fresh task a
generic agent could safely begin, but it never creates or edits a GitHub
Issue and never creates a Stage 1 claim ref. Stage 3 is the narrow bridge
that turns a ``fresh_candidate`` plan into ONE real, safely-ordered mutation:

    Stage 2 plan (read-only)
        -> re-verify committed HEAD has not moved since the plan was built
        -> construct the SAME production :class:`RealTaskReviewWorkflow` used
           by the explicit-task path for the selected candidate
        -> observe_goal_state() (re-derives eligibility from CURRENT
           committed/Issue state -- never trusts the stale plan snapshot)
        -> require assess_goal_state() to agree the task is ready for an
           agent lease (fail closed on any disagreement)
        -> acquire_agent_lease() -- this is the ONE mutation boundary; it
           internally performs the Stage 1 atomic claim BEFORE any Issue
           mutation, initializes/acquires the durable Issue, re-reads and
           verifies exact authority, then releases the ephemeral claim (see
           claim_refs.acquire_issue_lease_with_claims, which this function
           does not reimplement)
        -> return a typed outcome; the caller (run_pipeline_agent.py) then
           continues through the EXISTING implementation pipeline for the
           resolved task_id exactly as it would for an explicit -TaskId.

Deliberately NOT built here (see the Stage 3 task brief for the exact
boundary):

- Stage 4 retry: losing the Stage 1 claim race for the selected candidate is
  reported as a normal typed ``claim_conflict``/other terminal outcome. This
  module never recomputes the plan and tries a second candidate.
- Stage 5 decomposition: a ``no_safe_work`` plan is reported as-is; this
  module never routes into the Progressive Decomposer.
- Autonomous/background dispatch: this module is called synchronously by the
  human-invoked generic command; it starts no scheduler of its own.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .claim_policy import ClaimPolicy, ClaimPolicyError
from .claim_refs import ClaimRefsError
from .contracts import TaskReviewContractError, validate_task_id
from .dispatch_plan import DispatchPlan, build_dispatch_plan
from .dispatch_policy import DispatchPolicy
from .goal_loop import GoalAction, assess_goal_state
from .issue_queue import repo_root
from .issue_workflow_store import IssueWorkflowStoreError
from .real_workflow import RealTaskReviewWorkflow

GENERIC_FRESH_DISPATCH_PLANNED_APPROACH = (
    "Stage 3 generic dispatch selected this task from the Stage 2 read-only "
    "fresh-candidate pool because no existing durable agent-ready Issue was "
    "actionable. Inspect the task-owned Unity components, scenes, and tests "
    "next, then continue through the normal implementation pipeline phase."
)
GENERIC_FRESH_DISPATCH_EXPECTED_VALIDATION = (
    "Preserve TaskGraph validity and a clean checkout. The bounded "
    "implementation/test scope, ExecutionCrew run, and human Unity/runtime "
    "validation determine the actual pass/fail result; this lease only "
    "begins the task."
)

# Every outcome this module can return. Kept as a frozenset so callers and
# tests can assert the exact closed set instead of trusting a comment.
GENERIC_DISPATCH_DECISIONS = frozenset(
    {
        "resume_existing",
        "fresh_started",
        "claim_conflict",
        "no_safe_work",
        "blocked_invalid_state",
        "claim_operational_error",
        "issue_initialization_blocked",
        "lease_acquired_claim_cleanup_required",
    }
)


class FreshDispatchError(TaskReviewContractError):
    """Raised only for a programmer/contract violation in Stage 3 wiring.

    Every ordinary scheduling/contention/blocked outcome is returned as a
    typed :class:`GenericDispatchResult`, never raised.
    """


@dataclass(frozen=True)
class GenericDispatchResult:
    """One typed outcome of resolving the generic no-TaskId command.

    ``decision`` is always one of :data:`GENERIC_DISPATCH_DECISIONS`.
    """

    decision: str
    task_id: str | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)
    resume: dict[str, Any] | None = None
    lease_result: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.decision not in GENERIC_DISPATCH_DECISIONS:
            raise FreshDispatchError(
                f"unsupported generic dispatch decision: {self.decision!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "task_id": self.task_id,
            "reasons": list(self.reasons),
            "resume": self.resume,
            "lease_result": self.lease_result,
            "plan": self.plan,
        }


def _git_head(root: Path) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), "rev-parse", "--verify", "HEAD"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60.0,
    )
    if result.returncode != 0:
        raise FreshDispatchError("could not resolve committed HEAD before fresh dispatch")
    return result.stdout.decode("utf-8").strip()


def _lease_outcome_decision(lease_result: Mapping[str, Any]) -> str:
    status = lease_result.get("status")
    if status in ("acquired", "resumed"):
        return "fresh_started"
    if status == "lease_acquired_claim_cleanup_required":
        return "lease_acquired_claim_cleanup_required"
    if status == "blocked":
        ephemeral = lease_result.get("ephemeral_claim")
        if isinstance(ephemeral, dict) and ephemeral.get("status") == "claim_conflict":
            return "claim_conflict"
        return "issue_initialization_blocked"
    # Fail closed: any status this module does not recognize is reported as
    # blocked rather than silently treated as a successful start.
    return "issue_initialization_blocked"


def resolve_generic_dispatch(
    *,
    source: Path | str,
    worker_id: str,
    checkout_root: Path | str | None = None,
    remote: str = "origin",
    policy: DispatchPolicy | None = None,
    claim_policy: ClaimPolicy | None = None,
) -> GenericDispatchResult:
    """Resolve what the human-invoked generic no-TaskId command should do.

    Preserves resume-first ordering (an existing actionable durable Issue
    always wins), and crosses exactly one mutation boundary for a fresh
    candidate: the Stage 1 atomic claim, durable Issue creation/acquisition,
    exact authority verification, and ephemeral claim release all happen
    inside one call to ``RealTaskReviewWorkflow.acquire_agent_lease`` (see
    module docstring). Never retries a different candidate after a lost
    claim race (Stage 4) and never routes into decomposition (Stage 5).
    """

    plan: DispatchPlan = build_dispatch_plan(
        source=source,
        worker_id=worker_id,
        remote=remote,
        policy=policy,
        claim_policy=claim_policy,
    )

    if plan.decision == "resume_existing":
        resume = plan.resume or {}
        return GenericDispatchResult(
            decision="resume_existing",
            task_id=resume.get("task_id"),
            resume=resume,
            plan=plan.to_dict(),
        )
    if plan.decision == "blocked_invalid_state":
        return GenericDispatchResult(
            decision="blocked_invalid_state",
            reasons=plan.reasons,
            plan=plan.to_dict(),
        )
    if plan.decision == "no_safe_work":
        return GenericDispatchResult(decision="no_safe_work", plan=plan.to_dict())
    if plan.decision != "fresh_candidate":
        raise FreshDispatchError(f"unsupported Stage 2 plan decision: {plan.decision!r}")

    candidate = plan.selected_fresh_candidate
    if not isinstance(candidate, dict) or not isinstance(candidate.get("task_id"), str):
        raise FreshDispatchError(
            "Stage 2 plan reported fresh_candidate without a selected_fresh_candidate"
        )
    task_id = validate_task_id(candidate["task_id"])

    root = repo_root(Path(source).resolve())
    current_head = _git_head(root)
    if current_head != plan.source_commit:
        return GenericDispatchResult(
            decision="blocked_invalid_state",
            task_id=task_id,
            reasons=(
                f"Git HEAD moved from {plan.source_commit} to {current_head} between "
                "Stage 2 planning and Stage 3 fresh-dispatch mutation; refusing to "
                "mutate against a stale plan",
            ),
            plan=plan.to_dict(),
        )

    # Do NOT ask a model to reconsider, and do NOT substitute another
    # candidate: task_id is exactly what Stage 2 selected. Constructing the
    # SAME RealTaskReviewWorkflow the explicit-task path uses re-derives
    # eligibility from CURRENT committed/Issue state (never the stale plan)
    # through observe_goal_state()/assess_goal_state(), so this is the same
    # safety kernel applied at mutation time rather than a second one.
    workflow = RealTaskReviewWorkflow(
        source=root,
        task_id=task_id,
        checkout_root=checkout_root,
        worker_id=worker_id,
    )
    observation = workflow.observe_goal_state()
    assessment = assess_goal_state(observation)
    if assessment.action is not GoalAction.ACQUIRE_AGENT_LEASE:
        coordination_status = (observation.get("coordination") or {}).get("status")
        decision = (
            "claim_conflict"
            if coordination_status in ("claimed_by_worker", "claimed_by_other")
            else "blocked_invalid_state"
        )
        return GenericDispatchResult(
            decision=decision,
            task_id=task_id,
            reasons=assessment.reasons,
            plan=plan.to_dict(),
        )

    try:
        lease_result = workflow.acquire_agent_lease(
            planned_approach=GENERIC_FRESH_DISPATCH_PLANNED_APPROACH,
            expected_validation=GENERIC_FRESH_DISPATCH_EXPECTED_VALIDATION,
        )
    except (ClaimRefsError, ClaimPolicyError) as exc:
        # ClaimPolicyError/ClaimCoordinationNotActivatedError (raised by
        # build_activated_claim_client when the committed claim policy is
        # missing, invalid, or not yet activated) is a typed claim-layer
        # failure, not a programmer/contract violation in this module's own
        # wiring: it must map to the same claim_operational_error outcome as
        # ClaimRefsError rather than escaping as a generic unhandled STOP.
        return GenericDispatchResult(
            decision="claim_operational_error",
            task_id=task_id,
            reasons=(str(exc),),
            plan=plan.to_dict(),
        )
    except IssueWorkflowStoreError as exc:
        return GenericDispatchResult(
            decision="issue_initialization_blocked",
            task_id=task_id,
            reasons=(str(exc),),
            plan=plan.to_dict(),
        )

    return GenericDispatchResult(
        decision=_lease_outcome_decision(lease_result),
        task_id=task_id,
        reasons=tuple(lease_result.get("reasons") or ()),
        lease_result=lease_result,
        plan=plan.to_dict(),
    )


__all__ = [
    "GENERIC_DISPATCH_DECISIONS",
    "GENERIC_FRESH_DISPATCH_EXPECTED_VALIDATION",
    "GENERIC_FRESH_DISPATCH_PLANNED_APPROACH",
    "FreshDispatchError",
    "GenericDispatchResult",
    "resolve_generic_dispatch",
]
