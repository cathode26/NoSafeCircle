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

:func:`resolve_generic_dispatch` above is a SINGLE attempt: a lost Stage 1
claim race for the selected candidate (``claim_conflict``) is reported as a
normal typed terminal outcome, and this function never recomputes the plan
or tries a second candidate. That single-attempt behavior is preserved
exactly for the explicit ``-TaskId`` path and is still what every existing
Stage 3 test exercises directly.

Stage 4 (:func:`resolve_generic_dispatch_with_contention_retry`) is the
narrow addition on top: for the GENERIC no-TaskId command only, it calls
:func:`resolve_generic_dispatch` in a loop, and when (and only when) one
attempt reports ordinary ``claim_conflict``, it records that task id in a
per-invocation ``excluded_task_ids`` set, rebuilds Stage 2 authority from
scratch (a brand new :func:`resolve_generic_dispatch` call, which itself
rebuilds a brand new :class:`~.dispatch_plan.DispatchPlan`), and tries again.
Every other terminal outcome (``resume_existing``, ``fresh_started``,
``no_safe_work``, ``blocked_invalid_state``, ``claim_operational_error``,
``issue_initialization_blocked``, ``lease_acquired_claim_cleanup_required``)
stops the loop immediately and is returned as-is; none of those are ordinary
contention. The committed task graph is finite and every ``claim_conflict``
strictly grows the exclusion set, so the loop is structurally finite with no
arbitrary retry-count cap and no sleep/backoff of its own.

Deliberately NOT built here:

- Stage 5 decomposition: a ``no_safe_work`` plan is reported as-is; this
  module never routes into the Progressive Decomposer.
- Autonomous/background dispatch: this module is called synchronously by the
  human-invoked generic command; it starts no scheduler, daemon, or queue of
  its own. Ten PowerShell windows remain ten independent synchronous
  invocations of the same algorithm, not one coordinator.
- A second fresh-candidate safety implementation: Stage 4 only ever narrows
  the SAME Stage 2 kernel (:func:`dispatch_plan.evaluate_fresh_candidate`)
  via ``excluded_task_ids``; it never re-ranks, reorders, or re-scores.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .claim_policy import ClaimPolicy, ClaimPolicyError
from .claim_refs import ClaimRefsError
from .contracts import TaskReviewContractError, validate_task_id
from .dispatch_plan import DispatchPlan, build_dispatch_plan
from .dispatch_policy import DispatchPolicy
from .goal_loop import GoalAction, assess_goal_state
from .issue_queue import repo_root
from .issue_workflow_store import (
    BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER,
    BLOCKED_KIND_DURABLE_RESOURCE_RESERVATION_CONFLICT,
    IssueWorkflowStoreError,
)
from .real_workflow import RealTaskReviewWorkflow

# The closed set of acquire_agent_lease() "blocked_kind" values that
# positively prove an ordinary post-claim durable-ownership race against
# another AUTHORIZED worker's already-valid durable authority -- never an
# invalid/tampered Issue, a contract mismatch, or an operational failure (see
# issue_workflow_store.py for the exact structural conditions each requires).
# A blocked result with a missing or unrecognized blocked_kind is never
# retryable.
_BENIGN_DURABLE_CONTENTION_BLOCKED_KINDS = frozenset(
    {
        BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER,
        BLOCKED_KIND_DURABLE_RESOURCE_RESERVATION_CONFLICT,
    }
)

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
    """Classify one acquire_agent_lease() result into a Stage 3 decision.

    A ``blocked`` result is ordinary ``claim_conflict`` in exactly two
    shapes, both proven upstream, never guessed here from text:

    1. the Stage 1 ephemeral Git-ref claim itself lost its race
       (``ephemeral_claim.status == "claim_conflict"``); or
    2. the ephemeral claim was won, but the subsequent durable-Issue reread
       inside the SAME attempt positively proved another authorized worker
       already holds valid durable authority -- either the task's Issue
       (``BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER``) or an overlapping
       exclusive-resource reservation
       (``BLOCKED_KIND_DURABLE_RESOURCE_RESERVATION_CONFLICT``). This second
       shape can only reach this function via ``blocked_kind`` set by
       ``IssueWorkflowService.acquire_agent_lease``, which is reached from
       ``acquire_issue_lease_with_claims`` only after ``claim_client.acquire``
       already succeeded for this attempt (see claim_refs.py), so the "claim
       already won" precondition holds by construction.

    Every other blocked shape -- an invalid/tampered Issue, a contract-hash
    mismatch, an exact-authority reread failure, a claim-cleanup failure, an
    operational Issue/GitHub failure, or an unrecognized/untyped blocked
    result -- has no matching ``blocked_kind`` and stays terminal
    ``issue_initialization_blocked``.
    """

    status = lease_result.get("status")
    if status in ("acquired", "resumed"):
        return "fresh_started"
    if status == "lease_acquired_claim_cleanup_required":
        return "lease_acquired_claim_cleanup_required"
    if status == "blocked":
        ephemeral = lease_result.get("ephemeral_claim")
        if isinstance(ephemeral, dict) and ephemeral.get("status") == "claim_conflict":
            return "claim_conflict"
        if lease_result.get("blocked_kind") in _BENIGN_DURABLE_CONTENTION_BLOCKED_KINDS:
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
    excluded_task_ids: Iterable[str] | None = None,
) -> GenericDispatchResult:
    """Resolve what the human-invoked generic no-TaskId command should do,
    for ONE attempt.

    Preserves resume-first ordering (an existing actionable durable Issue
    always wins), and crosses exactly one mutation boundary for a fresh
    candidate: the Stage 1 atomic claim, durable Issue creation/acquisition,
    exact authority verification, and ephemeral claim release all happen
    inside one call to ``RealTaskReviewWorkflow.acquire_agent_lease`` (see
    module docstring). Never retries a different candidate itself after a
    lost claim race and never routes into decomposition (Stage 5); Stage 4
    retry across multiple attempts is
    :func:`resolve_generic_dispatch_with_contention_retry`, which calls this
    function repeatedly rather than this function looping internally.

    ``excluded_task_ids`` (Stage 4) is forwarded unchanged to
    :func:`dispatch_plan.build_dispatch_plan`; omitting it (every existing
    caller) preserves exact Stage 3 behavior.
    """

    plan: DispatchPlan = build_dispatch_plan(
        source=source,
        worker_id=worker_id,
        remote=remote,
        policy=policy,
        claim_policy=claim_policy,
        excluded_task_ids=excluded_task_ids,
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


# ---------------------------------------------------------------------------
# Stage 4: retry ordinary claim contention with a fresh Stage 2 plan, for the
# GENERIC no-TaskId command only.
# ---------------------------------------------------------------------------

# The ONE outcome a single resolve_generic_dispatch() attempt can report that
# Stage 4 retries. Every other outcome in GENERIC_DISPATCH_DECISIONS remains
# terminal for the whole invocation (see module docstring).
GENERIC_CONTENTION_RETRYABLE_DECISION = "claim_conflict"

# The closed set of decisions resolve_generic_dispatch_with_contention_retry
# can return. "claim_conflict" is deliberately absent: it is retried
# in-loop and never escapes as the wrapper's own terminal decision.
GENERIC_CONTENTION_RETRY_DECISIONS = frozenset(
    GENERIC_DISPATCH_DECISIONS - {GENERIC_CONTENTION_RETRYABLE_DECISION}
)


@dataclass(frozen=True)
class ContentionAttempt:
    """One ordinary claim-contention loss this invocation observed and moved
    past. Bounded, structured history for Gauntlet verification -- never a
    dump of the full plan or any secret."""

    attempt_index: int
    task_id: str
    plan_source_commit: str | None
    classification: str
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_index": self.attempt_index,
            "task_id": self.task_id,
            "plan_source_commit": self.plan_source_commit,
            "classification": self.classification,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class GenericDispatchRetryResult:
    """The typed outcome of resolving the generic no-TaskId command WITH
    Stage 4 per-invocation contention retry.

    ``decision`` is always one of :data:`GENERIC_CONTENTION_RETRY_DECISIONS`
    -- ordinary ``claim_conflict`` is never the final decision: it is either
    retried (another attempt) or, once every currently safe untried
    candidate is exhausted, surfaces as ``no_safe_work`` with
    ``exhausted_after_contention=True``.
    """

    decision: str
    task_id: str | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)
    resume: dict[str, Any] | None = None
    lease_result: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    contention_history: tuple[ContentionAttempt, ...] = field(default_factory=tuple)
    contended_task_ids: tuple[str, ...] = field(default_factory=tuple)
    exhausted_after_contention: bool = False

    def __post_init__(self) -> None:
        if self.decision not in GENERIC_CONTENTION_RETRY_DECISIONS:
            raise FreshDispatchError(
                f"unsupported generic contention-retry decision: {self.decision!r}"
            )

    @property
    def contention_attempt_count(self) -> int:
        return len(self.contention_history)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "task_id": self.task_id,
            "reasons": list(self.reasons),
            "resume": self.resume,
            "lease_result": self.lease_result,
            "plan": self.plan,
            "contention_attempt_count": self.contention_attempt_count,
            "contended_task_ids": list(self.contended_task_ids),
            "contention_history": [item.to_dict() for item in self.contention_history],
            "exhausted_after_contention": self.exhausted_after_contention,
        }


def resolve_generic_dispatch_with_contention_retry(
    *,
    source: Path | str,
    worker_id: str,
    checkout_root: Path | str | None = None,
    remote: str = "origin",
    policy: DispatchPolicy | None = None,
    claim_policy: ClaimPolicy | None = None,
) -> GenericDispatchRetryResult:
    """Stage 4: resolve the generic no-TaskId command, retrying ordinary
    per-task/per-resource claim contention with a currently-safe alternate
    candidate, for as many independent worker processes as are run.

    Algorithm, one attempt at a time:

    1. Call :func:`resolve_generic_dispatch` with this invocation's current
       ``excluded_task_ids`` (initially empty). That call rebuilds Stage 2
       authority from scratch every single time -- current committed HEAD,
       task contracts, taskcontrol state, durable Issue state, durable
       resource reservations, and a fresh Stage 1 claim-ref snapshot -- so
       resume-first preference and every safety check are re-evaluated fresh
       on every attempt, never read from a stale/cached plan.
    2. If the outcome is ``claim_conflict``: this is ordinary same-task or
       shared-exclusive-resource arbitration loss, not an infrastructure
       failure. Record it in the bounded ``contention_history``, add its
       ``task_id`` to this invocation's in-memory ``excluded_task_ids`` (so
       THIS invocation will not attempt it again), and loop -- the next
       attempt's fresh Stage 2 plan will never rank an excluded task as the
       selected fresh candidate (see ``dispatch_plan.plan_dispatch``'s
       ``excluded_task_ids`` handling), and will still prefer an
       agent-ready resume over any fresh candidate if one has since appeared.
    3. Any other outcome (``resume_existing``, ``fresh_started``,
       ``no_safe_work``, ``blocked_invalid_state``,
       ``claim_operational_error``, ``issue_initialization_blocked``,
       ``lease_acquired_claim_cleanup_required``) stops the loop immediately
       and is returned as this invocation's final result. In particular,
       operational/invalid-state/initialization/cleanup failures are never
       retried -- only ordinary claim contention is.

    The committed task graph is finite and ``excluded_task_ids`` strictly
    grows by one on every retried attempt, so this loop is structurally
    finite: there is no arbitrary retry-count cap, no sleep/backoff, and no
    background polling. If a refreshed plan were ever to report
    ``claim_conflict`` for a task_id already in this invocation's exclusion
    set, that is an internal invariant violation (the exclusion should have
    kept it out of the candidate pool) -- this fails closed with
    ``blocked_invalid_state`` rather than looping.

    This function is used ONLY for the generic no-TaskId command. Explicit
    ``-TaskId`` admission continues to call the single-attempt
    :func:`resolve_generic_dispatch`-equivalent gate
    (``evaluate_committed_fresh_candidate`` /
    ``run_pipeline_agent._require_explicit_fresh_admission``) so a blocked
    explicit task is always reported for THAT exact task_id and never
    silently substituted. Observe mode never calls this function at all.
    """

    excluded_task_ids: set[str] = set()
    history: list[ContentionAttempt] = []
    attempt_index = 0

    while True:
        attempt_index += 1
        result = resolve_generic_dispatch(
            source=source,
            worker_id=worker_id,
            checkout_root=checkout_root,
            remote=remote,
            policy=policy,
            claim_policy=claim_policy,
            excluded_task_ids=excluded_task_ids,
        )
        if result.task_id:
            print(f"[SELECT] {result.task_id}", file=sys.stderr, flush=True)

        if result.decision == GENERIC_CONTENTION_RETRYABLE_DECISION:
            contended_task_id = result.task_id
            if not isinstance(contended_task_id, str) or not contended_task_id:
                raise FreshDispatchError(
                    "claim_conflict outcome without a task_id: cannot record contention"
                )
            if contended_task_id in excluded_task_ids:
                # Invariant violation: a refreshed plan must never re-select
                # a task this invocation already excluded after losing its
                # claim race. Fail closed instead of looping forever.
                return GenericDispatchRetryResult(
                    decision="blocked_invalid_state",
                    task_id=contended_task_id,
                    reasons=(
                        "internal invariant violation: refreshed Stage 2 plan "
                        f"re-selected already-excluded candidate {contended_task_id} "
                        "after ordinary claim contention",
                    ),
                    plan=result.plan,
                    contention_history=tuple(history),
                    contended_task_ids=tuple(sorted(excluded_task_ids)),
                )
            print(
                f"[CLAIM] contention on {contended_task_id}",
                file=sys.stderr,
                flush=True,
            )
            history.append(
                ContentionAttempt(
                    attempt_index=attempt_index,
                    task_id=contended_task_id,
                    plan_source_commit=(result.plan or {}).get("source_commit"),
                    classification=result.decision,
                    reasons=result.reasons,
                )
            )
            excluded_task_ids.add(contended_task_id)
            print(
                "[RETRY] refreshing dispatch plan after ordinary claim contention",
                file=sys.stderr,
                flush=True,
            )
            continue

        exhausted_after_contention = (
            result.decision == "no_safe_work" and bool(history)
        )
        if result.decision == "fresh_started":
            print(f"[CLAIM] acquired {result.task_id}", file=sys.stderr, flush=True)
        return GenericDispatchRetryResult(
            decision=result.decision,
            task_id=result.task_id,
            reasons=result.reasons,
            resume=result.resume,
            lease_result=result.lease_result,
            plan=result.plan,
            contention_history=tuple(history),
            contended_task_ids=tuple(sorted(excluded_task_ids)),
            exhausted_after_contention=exhausted_after_contention,
        )


__all__ = [
    "GENERIC_CONTENTION_RETRYABLE_DECISION",
    "GENERIC_CONTENTION_RETRY_DECISIONS",
    "GENERIC_DISPATCH_DECISIONS",
    "GENERIC_FRESH_DISPATCH_EXPECTED_VALIDATION",
    "GENERIC_FRESH_DISPATCH_PLANNED_APPROACH",
    "ContentionAttempt",
    "FreshDispatchError",
    "GenericDispatchResult",
    "GenericDispatchRetryResult",
    "resolve_generic_dispatch",
    "resolve_generic_dispatch_with_contention_retry",
]
