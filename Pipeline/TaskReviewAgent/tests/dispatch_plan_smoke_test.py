#!/usr/bin/env python3
"""Stage 2 generic get-work: deterministic, read-only dispatch planning.

Proves the safety kernel (:func:`evaluate_fresh_candidate`) and the composed
planner (:func:`plan_dispatch`) without touching Git, GitHub, or Stage 1
claim refs: every dependency is an in-memory fake, matching the existing
``resource_reservation_smoke_test.py`` style.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from contextlib import contextmanager
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.dispatch_plan as dispatch_plan  # noqa: E402
import Pipeline.TaskReviewAgent.generic_selection as generic_selection  # noqa: E402
from Pipeline.TaskReviewAgent.claim_policy import ClaimPolicyError  # noqa: E402
from Pipeline.TaskReviewAgent.claim_refs import (  # noqa: E402
    MAX_RESOURCE_TOKEN_LENGTH,
    resource_claim_ref,
    task_claim_ref,
)
from Pipeline.TaskReviewAgent.committed_tasks import CommittedTaskError  # noqa: E402
from Pipeline.TaskReviewAgent.dispatch_plan import (  # noqa: E402
    DispatchPlan,
    build_dispatch_plan,
    evaluate_fresh_candidate,
    plan_dispatch,
)
from Pipeline.TaskReviewAgent.dispatch_policy import (  # noqa: E402
    DispatchPolicy,
    DispatchPolicyError,
    load_dispatch_policy,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    labels_for_state,
    render_event_comment,
    transition,
    update_issue_body,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)

NAMESPACE = "refs/nsc/claims"
SOURCE_HEAD = "1" * 40


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_task(task_id: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "id": task_id,
        "schema_version": "2.0",
        "title": f"Fixture {task_id}",
        "contract_revision": 1,
        "contract_disposition": "active",
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "parent": "NSC-001",
        "depends_on": [],
        "exclusive_resources": [],
        "task_contract_sha256": hashlib.sha256(task_id.encode("utf-8")).hexdigest(),
    }
    base.update(overrides)
    return base


def build_task_loader(tasks: dict[str, dict[str, Any]]):
    def loader(task_id: str) -> dict[str, Any]:
        if task_id not in tasks:
            raise CommittedTaskError(f"no fixture task contract for {task_id}")
        return tasks[task_id]

    return loader


def build_state_provider(states: dict[str, str]):
    def provider(task_id: str) -> dict[str, Any]:
        if task_id not in states:
            return {"task_id": task_id, "state": None, "error": f"no fixture state for {task_id}"}
        return {"task_id": task_id, "state": states[task_id], "error": None}

    return provider


def fresh_issue_workflow(tasks: dict[str, dict[str, Any]]) -> tuple[MemoryIssueBackend, IssueWorkflowService]:
    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=build_task_loader(tasks),
        worker_id="dispatch-plan-fixture-worker",
    )
    return backend, service


def evaluate(
    task_id: str,
    tasks: dict[str, dict[str, Any]],
    states: dict[str, str],
    *,
    issue_workflow: IssueWorkflowService | None = None,
    claimed_refs: dict[str, str] | None = None,
    claim_namespace: str | None = None,
):
    if issue_workflow is None:
        _, issue_workflow = fresh_issue_workflow(tasks)
    return evaluate_fresh_candidate(
        task_id,
        task_loader=build_task_loader(tasks),
        state_provider=build_state_provider(states),
        issue_workflow=issue_workflow,
        claimed_refs=claimed_refs or {},
        claim_namespace=claim_namespace,
    )


# --------------------------------------------------------------------------
# 1. Resume-first
# --------------------------------------------------------------------------


def test_resume_beats_every_fresh_candidate() -> None:
    tasks = {
        "NSC-700": make_task("NSC-700"),
        "NSC-701": make_task("NSC-701"),
    }
    states = {"NSC-700": "not_delivered", "NSC-701": "not_delivered"}
    backend, issue_workflow = fresh_issue_workflow(tasks)
    issue_workflow.acquire_agent_lease(
        task=tasks["NSC-700"],
        source_head=SOURCE_HEAD,
        branch="nsc-700-task",
        checkout_path=r"C:\NSC\NSC\NSC-700",
        planned_approach="Implement.",
        expected_validation="Vincent validates.",
        now="2026-08-30T10:00:00Z",
    )
    issue_workflow.publish_human_handoff(
        task_id="NSC-700",
        branch="nsc-700-task",
        head_commit="2" * 40,
        checkout_path=r"C:\NSC\NSC\NSC-700",
        implementation_summary="Implemented.",
        completed_checks=("Pushed.",),
        human_steps=("Test in Unity.",),
        expected_result="Passes.",
        now="2026-08-30T10:01:00Z",
    )
    issue_workflow.apply_human_result(
        task_id="NSC-700",
        result_body=(
            "## Human validation result\n\nResult: PASS\n"
            f"Tested commit: `{'2' * 40}`\n\nCompleted steps:\n- Verified.\n"
        ),
        actor_id="cathode26",
        now="2026-08-30T10:02:00Z",
    )
    plan = plan_dispatch(
        source_commit=SOURCE_HEAD,
        task_ids=list(tasks),
        task_loader=build_task_loader(tasks),
        state_provider=build_state_provider(states),
        issue_workflow=issue_workflow,
    )
    require(plan.decision == "resume_existing", f"resume did not win: {plan.decision}")
    require(plan.resume["task_id"] == "NSC-700", f"wrong resume target: {plan.resume}")
    require(plan.selected_fresh_candidate is None, "fresh candidate selected despite resume")
    require(plan.ranked_eligible_candidates == (), "fresh pool was ranked despite resume")
    require(plan.autonomous_dispatch is False, "autonomous dispatch flag drifted")


# --------------------------------------------------------------------------
# 2/3/11. Fresh-candidate derived-state gating
# --------------------------------------------------------------------------


def test_not_delivered_candidate_selected_when_no_actionable_issue() -> None:
    tasks = {"NSC-702": make_task("NSC-702")}
    states = {"NSC-702": "not_delivered"}
    _, issue_workflow = fresh_issue_workflow(tasks)
    plan = plan_dispatch(
        source_commit=SOURCE_HEAD,
        task_ids=list(tasks),
        task_loader=build_task_loader(tasks),
        state_provider=build_state_provider(states),
        issue_workflow=issue_workflow,
    )
    require(plan.decision == "fresh_candidate", f"unexpected decision: {plan.decision}")
    require(plan.selected_fresh_candidate["task_id"] == "NSC-702", str(plan.selected_fresh_candidate))
    require(plan.autonomous_dispatch is False, "autonomous dispatch flag drifted")


def test_needs_testing_is_not_a_fresh_candidate() -> None:
    tasks = {"NSC-703": make_task("NSC-703")}
    states = {"NSC-703": "needs_testing"}
    result = evaluate("NSC-703", tasks, states)
    require(not result.eligible, "needs_testing task was accepted as fresh implementation")
    require(
        "derived_state_not_fresh:needs_testing" in result.reason_codes,
        f"missing expected reason: {result.reason_codes}",
    )


def test_already_conformant_task_rejected_as_fresh() -> None:
    tasks = {"NSC-704": make_task("NSC-704")}
    states = {"NSC-704": "conformant"}
    result = evaluate("NSC-704", tasks, states)
    require(not result.eligible, "a conformant task was offered as fresh implementation")
    require("derived_state_not_fresh:conformant" in result.reason_codes, str(result.reason_codes))


# --------------------------------------------------------------------------
# 4/5/6/7. Dependency dispatch-satisfied semantics
# --------------------------------------------------------------------------


def test_conformant_dependency_is_dispatch_satisfied() -> None:
    tasks = {
        "NSC-710": make_task("NSC-710"),
        "NSC-780": make_task("NSC-780", depends_on=["NSC-710"]),
    }
    states = {"NSC-710": "conformant", "NSC-780": "not_delivered"}
    result = evaluate("NSC-780", tasks, states)
    require(result.eligible, f"conformant dependency wrongly blocked candidate: {result.reason_codes}")
    require(len(result.dependency_observations) == 1, "expected exactly one dependency observation")
    observation = result.dependency_observations[0]
    require(observation.dispatch_satisfied, "conformant dependency not marked dispatch-satisfied")
    require(observation.note == "conformant", f"unexpected note: {observation.note}")


def test_needs_testing_dependency_is_dispatch_satisfied_but_flagged() -> None:
    tasks = {
        "NSC-711": make_task("NSC-711"),
        "NSC-781": make_task("NSC-781", depends_on=["NSC-711"]),
    }
    states = {"NSC-711": "needs_testing", "NSC-781": "not_delivered"}
    result = evaluate("NSC-781", tasks, states)
    require(
        result.eligible,
        f"needs_testing dependency wrongly blocked candidate: {result.reason_codes}",
    )
    observation = result.dependency_observations[0]
    require(observation.dispatch_satisfied, "needs_testing dependency not dispatch-satisfied")
    require(
        observation.note == "revalidation_debt",
        f"needs_testing dependency was not distinguished from conformant: {observation.note}",
    )
    require(observation.state == "needs_testing", str(observation))


def test_not_delivered_dependency_blocks() -> None:
    tasks = {
        "NSC-712": make_task("NSC-712"),
        "NSC-782": make_task("NSC-782", depends_on=["NSC-712"]),
    }
    states = {"NSC-712": "not_delivered", "NSC-782": "not_delivered"}
    result = evaluate("NSC-782", tasks, states)
    require(not result.eligible, "not_delivered dependency did not block its dependent")
    require(
        "dependency_blocked:NSC-712:not_delivered" in result.reason_codes,
        str(result.reason_codes),
    )


def test_unrecognized_dependency_states_fail_closed() -> None:
    blocking_states = ("needs_replan", "needs_human", "invalid_evidence", "ambiguous_evidence", "aggregate")
    for index, dependency_state in enumerate(blocking_states):
        dep_id = f"NSC-72{index}"
        candidate_id = f"NSC-79{index}"
        tasks = {
            dep_id: make_task(dep_id),
            candidate_id: make_task(candidate_id, depends_on=[dep_id]),
        }
        states = {dep_id: dependency_state, candidate_id: "not_delivered"}
        result = evaluate(candidate_id, tasks, states)
        require(
            not result.eligible,
            f"dependency state {dependency_state!r} did not block dispatch",
        )
        require(
            any(dep_id in reason and dependency_state in reason for reason in result.reason_codes),
            f"missing reason for {dependency_state!r}: {result.reason_codes}",
        )

    # A genuinely unknown/novel state string must also fail closed, never be
    # silently treated as satisfied.
    tasks = {
        "NSC-730": make_task("NSC-730"),
        "NSC-799": make_task("NSC-799", depends_on=["NSC-730"]),
    }
    states = {"NSC-730": "some_future_state_never_seen_before", "NSC-799": "not_delivered"}
    result = evaluate("NSC-799", tasks, states)
    require(not result.eligible, "unknown dependency state was not rejected")
    require(
        "dependency_blocked:NSC-730:unknown_state" in result.reason_codes,
        str(result.reason_codes),
    )
    observation = result.dependency_observations[0]
    require(observation.note == "unknown_state_fails_closed", str(observation))


# --------------------------------------------------------------------------
# 8/9/10. Task-shape eligibility
# --------------------------------------------------------------------------


def test_non_single_agent_candidate_rejected() -> None:
    tasks = {"NSC-740": make_task("NSC-740", execution_scope="needs_execution_decomposition")}
    states = {"NSC-740": "not_delivered"}
    result = evaluate("NSC-740", tasks, states)
    require(not result.eligible, "non-single_agent task was accepted")
    require("execution_scope_not_single_agent" in result.reason_codes, str(result.reason_codes))


def test_non_concrete_decomposition_state_rejected() -> None:
    tasks = {"NSC-741": make_task("NSC-741", decomposition_state="decomposed", kind="feature")}
    states = {"NSC-741": "not_delivered"}
    result = evaluate("NSC-741", tasks, states)
    require(not result.eligible, "non-concrete decomposition task was accepted")
    require("decomposition_state_not_concrete" in result.reason_codes, str(result.reason_codes))
    require("unsupported_kind" in result.reason_codes, str(result.reason_codes))


def test_inactive_disposition_candidate_rejected() -> None:
    for offset, disposition in enumerate(("superseded", "cancelled")):
        task_id = f"NSC-74{5 + offset}"
        tasks = {task_id: make_task(task_id, contract_disposition=disposition)}
        states = {task_id: "not_delivered"}
        result = evaluate(task_id, tasks, states)
        require(not result.eligible, f"{disposition} contract was accepted as fresh work")
        require("contract_not_active" in result.reason_codes, str(result.reason_codes))


# --------------------------------------------------------------------------
# 12/13. Durable Issue ownership and exclusive-resource reservation
# --------------------------------------------------------------------------


def test_existing_issue_ownership_rejects_duplicate_fresh_selection() -> None:
    tasks = {"NSC-750": make_task("NSC-750")}
    states = {"NSC-750": "not_delivered"}
    _, issue_workflow = fresh_issue_workflow(tasks)
    acquired = issue_workflow.acquire_agent_lease(
        task=tasks["NSC-750"],
        source_head=SOURCE_HEAD,
        branch="nsc-750-task",
        checkout_path=r"C:\NSC\NSC\NSC-750",
        planned_approach="Already being worked by another worker.",
        expected_validation="N/A.",
        now="2026-08-30T11:00:00Z",
    )
    require(acquired["status"] == "acquired", f"fixture setup failed: {acquired}")
    result = evaluate(
        "NSC-750",
        tasks,
        states,
        issue_workflow=IssueWorkflowService(
            backend=issue_workflow.backend,
            task_loader=build_task_loader(tasks),
            worker_id="a-different-generic-worker",
        ),
    )
    require(not result.eligible, "an agent_working task was reselected as fresh work")
    require("operationally_owned_by_managed_issue" in result.reason_codes, str(result.reason_codes))


def test_durable_exclusive_resource_overlap_rejects_candidate() -> None:
    shared_resource = "unity-scene:Assets/Scenes/Shared.unity"
    tasks = {
        "NSC-751": make_task("NSC-751", exclusive_resources=[shared_resource]),
        "NSC-752": make_task("NSC-752", exclusive_resources=[shared_resource]),
    }
    states = {"NSC-751": "not_delivered", "NSC-752": "not_delivered"}
    _, issue_workflow = fresh_issue_workflow(tasks)
    acquired = issue_workflow.acquire_agent_lease(
        task=tasks["NSC-751"],
        source_head=SOURCE_HEAD,
        branch="nsc-751-task",
        checkout_path=r"C:\NSC\NSC\NSC-751",
        planned_approach="Holds the shared resource.",
        expected_validation="N/A.",
        now="2026-08-30T11:05:00Z",
    )
    require(acquired["status"] == "acquired", f"fixture setup failed: {acquired}")
    other_worker = IssueWorkflowService(
        backend=issue_workflow.backend,
        task_loader=build_task_loader(tasks),
        worker_id="resource-conflict-checker",
    )
    result = evaluate("NSC-752", tasks, states, issue_workflow=other_worker)
    require(not result.eligible, "overlapping exclusive resource did not reject the candidate")
    require(
        any(reason.startswith("resource_reservation_conflict:") for reason in result.reason_codes),
        str(result.reason_codes),
    )


def test_invalid_managed_issue_state_fails_closed() -> None:
    shared_resource = "unity-scene:Assets/Scenes/Other.unity"
    tasks = {
        "NSC-753": make_task("NSC-753", exclusive_resources=[shared_resource]),
        "NSC-754": make_task("NSC-754"),
    }
    states = {"NSC-753": "not_delivered", "NSC-754": "not_delivered"}
    _, issue_workflow = fresh_issue_workflow(tasks)
    issue_workflow.acquire_agent_lease(
        task=tasks["NSC-753"],
        source_head=SOURCE_HEAD,
        branch="nsc-753-task",
        checkout_path=r"C:\NSC\NSC\NSC-753",
        planned_approach="Will be corrupted.",
        expected_validation="N/A.",
        now="2026-08-30T11:10:00Z",
    )
    issue_number = next(iter(issue_workflow.backend.issues))
    issue_workflow.backend.comments[issue_number][0]["body"] = issue_workflow.backend.comments[
        issue_number
    ][0]["body"].replace(
        '"worker_id": "dispatch-plan-fixture-worker"', '"worker_id": "tampered"'
    )
    checker = IssueWorkflowService(
        backend=issue_workflow.backend,
        task_loader=build_task_loader(tasks),
        worker_id="invalid-issue-checker",
    )
    result = evaluate("NSC-754", tasks, states, issue_workflow=checker)
    require(not result.eligible, "an invalid managed Issue did not block coordination")
    require(
        any(
            reason.startswith("resource_reservation_conflict:") and "invalid" in reason
            for reason in result.reason_codes
        ),
        str(result.reason_codes),
    )


# --------------------------------------------------------------------------
# 14/15/16. Stage 1 claim-ref read-only observation
# --------------------------------------------------------------------------


def test_active_stage1_task_claim_rejects_candidate() -> None:
    tasks = {"NSC-760": make_task("NSC-760")}
    states = {"NSC-760": "not_delivered"}
    claimed_refs = {task_claim_ref(NAMESPACE, "NSC-760"): "a" * 40}
    result = evaluate("NSC-760", tasks, states, claimed_refs=claimed_refs, claim_namespace=NAMESPACE)
    require(not result.eligible, "an active Stage 1 task claim did not reject the candidate")
    require("active_stage1_task_claim" in result.reason_codes, str(result.reason_codes))


def test_active_stage1_resource_claim_rejects_candidate() -> None:
    resource = "unity-prefab:Assets/Prefabs/Door.prefab"
    tasks = {"NSC-761": make_task("NSC-761", exclusive_resources=[resource])}
    states = {"NSC-761": "not_delivered"}
    claimed_refs = {resource_claim_ref(NAMESPACE, resource): "b" * 40}
    result = evaluate("NSC-761", tasks, states, claimed_refs=claimed_refs, claim_namespace=NAMESPACE)
    require(not result.eligible, "an active Stage 1 resource claim did not reject the candidate")
    require("active_stage1_resource_claim" in result.reason_codes, str(result.reason_codes))


def test_disjoint_active_claim_does_not_reject_candidate() -> None:
    tasks = {"NSC-762": make_task("NSC-762", exclusive_resources=["unity-scene:Assets/Scenes/A.unity"])}
    states = {"NSC-762": "not_delivered"}
    claimed_refs = {
        task_claim_ref(NAMESPACE, "NSC-999"): "c" * 40,
        resource_claim_ref(NAMESPACE, "unity-scene:Assets/Scenes/Unrelated.unity"): "d" * 40,
    }
    result = evaluate("NSC-762", tasks, states, claimed_refs=claimed_refs, claim_namespace=NAMESPACE)
    require(result.eligible, f"a disjoint claim wrongly rejected the candidate: {result.reason_codes}")


# --------------------------------------------------------------------------
# 18/19. Ranking determinism and shared safety kernel
# --------------------------------------------------------------------------


def test_ranking_is_deterministic_independent_of_enumeration_order() -> None:
    tasks = {
        "NSC-777": make_task("NSC-777"),
        "NSC-050": make_task("NSC-050"),
        "NSC-100": make_task("NSC-100"),
    }
    states = {task_id: "not_delivered" for task_id in tasks}
    expected = ["NSC-050", "NSC-100", "NSC-777"]
    orderings = [
        ["NSC-777", "NSC-050", "NSC-100"],
        ["NSC-100", "NSC-050", "NSC-777", "NSC-100", "NSC-050"],
        list(reversed(sorted(tasks))),
    ]
    for ordering in orderings:
        _, issue_workflow = fresh_issue_workflow(tasks)
        plan = plan_dispatch(
            source_commit=SOURCE_HEAD,
            task_ids=ordering,
            task_loader=build_task_loader(tasks),
            state_provider=build_state_provider(states),
            issue_workflow=issue_workflow,
        )
        actual = [item["task_id"] for item in plan.ranked_eligible_candidates]
        require(actual == expected, f"non-deterministic ranking for {ordering}: {actual}")


def test_explicit_and_generic_evaluation_share_one_safety_kernel() -> None:
    tasks = {
        "NSC-763": make_task("NSC-763"),
        "NSC-764": make_task("NSC-764", execution_scope="needs_execution_decomposition"),
    }
    states = {"NSC-763": "not_delivered", "NSC-764": "not_delivered"}
    _, issue_workflow = fresh_issue_workflow(tasks)
    plan = plan_dispatch(
        source_commit=SOURCE_HEAD,
        task_ids=list(tasks),
        task_loader=build_task_loader(tasks),
        state_provider=build_state_provider(states),
        issue_workflow=issue_workflow,
    )
    explicit_eligible = evaluate("NSC-763", tasks, states, issue_workflow=issue_workflow)
    explicit_rejected = evaluate("NSC-764", tasks, states, issue_workflow=issue_workflow)
    require(
        plan.selected_fresh_candidate == explicit_eligible.to_dict(),
        "generic pool result diverged from explicit evaluation for an eligible task",
    )
    require(
        plan.skipped_candidates[0] == explicit_rejected.to_dict(),
        "generic pool result diverged from explicit evaluation for a rejected task",
    )
    require(
        explicit_rejected.reason_codes == ("execution_scope_not_single_agent",),
        str(explicit_rejected.reason_codes),
    )


# --------------------------------------------------------------------------
# 20/21/22. Non-mutation, typed no-safe-work, disabled autonomous dispatch
# --------------------------------------------------------------------------


def test_planner_performs_no_mutations() -> None:
    tasks = {
        "NSC-770": make_task("NSC-770"),
        "NSC-771": make_task("NSC-771", depends_on=["NSC-770"]),
    }
    states = {"NSC-770": "conformant", "NSC-771": "not_delivered"}
    backend, issue_workflow = fresh_issue_workflow(tasks)
    before_issues = json.loads(json.dumps(backend.issues))
    before_comments = json.loads(json.dumps(backend.comments))
    before_next_issue = backend.next_issue
    before_next_comment = backend.next_comment

    real_run = subprocess.run

    def _forbidden_run(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(f"unexpected subprocess call during read-only planning: {args!r}")

    subprocess.run = _forbidden_run  # type: ignore[assignment]
    try:
        plan = plan_dispatch(
            source_commit=SOURCE_HEAD,
            task_ids=list(tasks),
            task_loader=build_task_loader(tasks),
            state_provider=build_state_provider(states),
            issue_workflow=issue_workflow,
        )
        evaluate("NSC-771", tasks, states, issue_workflow=issue_workflow)
    finally:
        subprocess.run = real_run  # type: ignore[assignment]

    require(plan.decision == "fresh_candidate", f"unexpected decision: {plan.decision}")
    require(backend.issues == before_issues, "Issue backend issues mutated by read-only planning")
    require(backend.comments == before_comments, "Issue backend comments mutated by read-only planning")
    require(backend.next_issue == before_next_issue, "Issue counter mutated by read-only planning")
    require(backend.next_comment == before_next_comment, "Comment counter mutated by read-only planning")


def test_no_safe_work_is_a_typed_outcome_not_an_exception() -> None:
    tasks = {"NSC-772": make_task("NSC-772")}
    states = {"NSC-772": "conformant"}
    _, issue_workflow = fresh_issue_workflow(tasks)
    plan = plan_dispatch(
        source_commit=SOURCE_HEAD,
        task_ids=list(tasks),
        task_loader=build_task_loader(tasks),
        state_provider=build_state_provider(states),
        issue_workflow=issue_workflow,
    )
    require(plan.decision == "no_safe_work", f"unexpected decision: {plan.decision}")
    require(plan.selected_fresh_candidate is None, "no_safe_work still selected a candidate")
    require(len(plan.skipped_candidates) == 1, str(plan.skipped_candidates))
    require(isinstance(plan, DispatchPlan), "no_safe_work must remain a typed result")


def test_autonomous_dispatch_remains_disabled() -> None:
    policy = load_dispatch_policy()
    require(policy.autonomous_dispatch is False, "committed dispatch policy enabled autonomous dispatch")
    require(policy.mode == "read_only_plan", f"unexpected mode: {policy.mode}")

    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-policy-") as tmp:
        weakened_path = Path(tmp) / "dispatch_policy.json"
        weakened = json.loads(
            (ROOT / "Pipeline" / "TaskReviewAgent" / "dispatch_policy.json").read_text("utf-8")
        )
        weakened["autonomous_dispatch"] = True
        weakened_path.write_text(json.dumps(weakened), encoding="utf-8")
        try:
            load_dispatch_policy(weakened_path)
            raise AssertionError("a weakened autonomous_dispatch=true policy was accepted")
        except DispatchPolicyError:
            pass

    tasks = {"NSC-773": make_task("NSC-773")}
    states = {"NSC-773": "not_delivered"}
    _, issue_workflow = fresh_issue_workflow(tasks)
    fresh_plan = plan_dispatch(
        source_commit=SOURCE_HEAD,
        task_ids=list(tasks),
        task_loader=build_task_loader(tasks),
        state_provider=build_state_provider(states),
        issue_workflow=issue_workflow,
    )
    require(fresh_plan.autonomous_dispatch is False, "fresh_candidate plan enabled autonomous dispatch")


def test_select_agent_ready_task_compatibility_preserved() -> None:
    class _EmptyGhIssueBackend:
        def __init__(self, *, source_root: Path) -> None:
            self.source_root = source_root

        def list_issues(self) -> list[dict[str, Any]]:
            return []

        def get_comments(self, issue_number: int) -> list[dict[str, Any]]:
            return []

    original_backend = generic_selection.GhIssueBackend
    generic_selection.GhIssueBackend = _EmptyGhIssueBackend  # type: ignore[assignment]
    try:
        try:
            generic_selection.select_agent_ready_task(source=ROOT, worker_id="stage2-compat-check")
            raise AssertionError("select_agent_ready_task no longer raises when nothing is agent-ready")
        except generic_selection.GenericSelectionError:
            pass
    finally:
        generic_selection.GhIssueBackend = original_backend  # type: ignore[assignment]


# --------------------------------------------------------------------------
# 23-27. Repair-pass regressions: malformed resources, one-bulk-snapshot,
# provisional/invalid claim observation, HEAD drift, historical COMPLETE.
# --------------------------------------------------------------------------


def test_malformed_resource_token_rejects_only_that_candidate() -> None:
    boundary_resource = "unity-scene:" + ("A" * (MAX_RESOURCE_TOKEN_LENGTH - len("unity-scene:")))
    require(len(boundary_resource) == MAX_RESOURCE_TOKEN_LENGTH, "fixture boundary resource has the wrong length")
    oversized_resource = boundary_resource + "X"

    tasks = {
        "NSC-810": make_task("NSC-810", exclusive_resources=[boundary_resource]),
        "NSC-811": make_task("NSC-811", exclusive_resources=[oversized_resource]),
        "NSC-812": make_task("NSC-812"),
    }
    states = {task_id: "not_delivered" for task_id in tasks}
    _, issue_workflow = fresh_issue_workflow(tasks)

    boundary_result = evaluate(
        "NSC-810", tasks, states, issue_workflow=issue_workflow, claim_namespace=NAMESPACE
    )
    require(
        boundary_result.eligible,
        f"a maximum-length resource token was wrongly rejected: {boundary_result.reason_codes}",
    )

    oversized_result = evaluate(
        "NSC-811", tasks, states, issue_workflow=issue_workflow, claim_namespace=NAMESPACE
    )
    require(not oversized_result.eligible, "an oversized resource token did not reject its candidate")
    require(
        any(
            reason.startswith("malformed_exclusive_resource_token:")
            for reason in oversized_result.reason_codes
        ),
        str(oversized_result.reason_codes),
    )

    unaffected_result = evaluate(
        "NSC-812", tasks, states, issue_workflow=issue_workflow, claim_namespace=NAMESPACE
    )
    require(
        unaffected_result.eligible,
        f"a malformed candidate crashed/blocked an unrelated candidate: {unaffected_result.reason_codes}",
    )

    plan = plan_dispatch(
        source_commit=SOURCE_HEAD,
        task_ids=list(tasks),
        task_loader=build_task_loader(tasks),
        state_provider=build_state_provider(states),
        issue_workflow=issue_workflow,
        claim_namespace=NAMESPACE,
    )
    require(plan.decision == "fresh_candidate", f"one malformed candidate crashed the whole plan: {plan.decision}")
    ranked_ids = {item["task_id"] for item in plan.ranked_eligible_candidates}
    require({"NSC-810", "NSC-812"} <= ranked_ids, str(ranked_ids))
    skipped_ids = {item["task_id"] for item in plan.skipped_candidates}
    require("NSC-811" in skipped_ids, str(skipped_ids))


def test_complete_historical_issue_does_not_block_fresh_candidate() -> None:
    shared_resource = "unity-scene:Assets/Scenes/Historical.unity"
    tasks = {
        "NSC-790": make_task("NSC-790", exclusive_resources=[shared_resource]),
        "NSC-791": make_task("NSC-791", exclusive_resources=[shared_resource]),
    }
    states = {"NSC-790": "conformant", "NSC-791": "not_delivered"}
    backend, issue_workflow = fresh_issue_workflow(tasks)
    acquired = issue_workflow.acquire_agent_lease(
        task=tasks["NSC-790"],
        source_head=SOURCE_HEAD,
        branch="nsc-790-task",
        checkout_path=r"C:\NSC\NSC\NSC-790",
        planned_approach="Complete this historical task.",
        expected_validation="N/A.",
        now="2026-08-30T12:00:00Z",
    )
    issue_number = acquired["issue_number"]
    snapshot = issue_workflow.find("NSC-790")
    require(snapshot is not None and snapshot.state is not None, "fixture Issue was not created")
    next_state, event = transition(
        snapshot.state,
        event_type=WorkflowEventType.COMPLETED,
        actor_type=WorkflowActor.AGENT,
        actor_id=issue_workflow.worker_id,
        to_state=WorkflowState.COMPLETE,
        to_phase=WorkflowPhase.MERGE_CLOSEOUT,
        details={
            "pull_request_url": "https://example.invalid/pull/790",
            "pull_request_number": 790,
            "merged_commit": "9" * 40,
            "conformant_record_id": "DEL-NSC-790-fixture",
        },
        now="2026-08-30T12:01:00Z",
    )
    backend.add_comment(issue_number, render_event_comment(event, "Historical task closeout completed."))
    backend.update_issue(
        issue_number,
        body=update_issue_body(snapshot.body, next_state, next_action="No further workflow action is required."),
        labels=labels_for_state(next_state.state, snapshot.labels),
        assignees=[issue_workflow.assignee],
    )
    backend.issues[issue_number]["state"] = "CLOSED"

    other_worker = IssueWorkflowService(
        backend=backend,
        task_loader=build_task_loader(tasks),
        worker_id="historical-completion-checker",
    )
    result = evaluate("NSC-791", tasks, states, issue_workflow=other_worker)
    require(
        result.eligible,
        f"a COMPLETE historical Issue wrongly blocked an otherwise fresh candidate: {result.reason_codes}",
    )


# --------------------------------------------------------------------------
# Production-wiring fixture: a real Git remote/checkout with committed
# Tasks/*.yaml contracts and a stub taskcontrol.py, so build_dispatch_plan's
# real production wiring (bulk state snapshot, HEAD-drift detection,
# committed claim-policy validation) can be exercised deterministically
# without a live Unity/evidence graph or a real `gh` CLI.
# --------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def _taskcontrol_stub_source() -> str:
    return r'''from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

log_path = os.environ.get("NSC_DISPATCH_TEST_TASKCONTROL_LOG")
if log_path:
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(sys.argv[1:]) + "\n")

if sys.argv[1:] == ["validate"]:
    print("taskcontrol validate: PASS")
    raise SystemExit(0)
if sys.argv[1:] == ["states", "--json"]:
    if os.environ.get("NSC_DISPATCH_TEST_MUTATE_HEAD_DURING_STATES") == "1":
        # Simulate a concurrent push landing on this exact checkout while
        # the bulk states snapshot is being taken, so the plan's final
        # HEAD re-check must catch it.
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "test-induced HEAD drift"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    fixture_path = os.environ["NSC_DISPATCH_TEST_STATES_FIXTURE"]
    print(Path(fixture_path).read_text(encoding="utf-8"))
    raise SystemExit(0)
raise SystemExit(2)
'''


def create_production_fixture(root: Path, *, tasks: dict[str, dict[str, Any]]) -> tuple[Path, Path]:
    remote = root / "remote.git"
    seed = root / "seed"
    _git(root, "init", "--bare", str(remote))
    _git(root, "init", "-b", "main", str(seed))
    _git(seed, "config", "user.name", "Dispatch Plan Smoke")
    _git(seed, "config", "user.email", "dispatch-plan@example.invalid")
    (seed / "Tasks").mkdir()
    (seed / "Pipeline" / "TaskGraph").mkdir(parents=True)
    for task_id, contract in tasks.items():
        (seed / f"Tasks/{task_id}.yaml").write_text(
            json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    (seed / "Pipeline/TaskGraph/taskcontrol.py").write_text(
        _taskcontrol_stub_source(), encoding="utf-8", newline="\n"
    )
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "Fixture commit")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-u", "origin", "main")
    subprocess.run(
        ("git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"),
        cwd=str(root),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    checkout = root / "checkout"
    _git(root, "clone", str(remote), str(checkout))
    _git(checkout, "config", "user.name", "Dispatch Plan Smoke")
    _git(checkout, "config", "user.email", "dispatch-plan@example.invalid")
    return checkout, remote


def _states_fixture(
    tasks: dict[str, dict[str, Any]],
    head_commit: str,
    *,
    states: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    states = states or {}
    return [
        {
            "task_id": task_id,
            "state": states.get(task_id, "not_delivered"),
            "head_commit": head_commit,
            "head_tree": "0" * 40,
            "selected_record_id": None,
            "findings": [],
            "dirty_worktree": False,
        }
        for task_id in tasks
    ]


class _FakeGhIssueBackend:
    """No-network stand-in so production-wiring tests never require a real,
    authenticated `gh` CLI."""

    def __init__(self, *, source_root: Path) -> None:
        self.source_root = source_root

    def list_issues(self) -> list[dict[str, Any]]:
        return []

    def get_comments(self, issue_number: int) -> list[dict[str, Any]]:
        return []


def _run_build_dispatch_plan(
    checkout: Path,
    *,
    states_fixture: Path,
    taskcontrol_log: Path | None = None,
    remote: str = "origin",
    policy: Any = None,
    claim_policy: Any = None,
    gh_backend: Any = _FakeGhIssueBackend,
) -> DispatchPlan:
    original_gh_backend = dispatch_plan.GhIssueBackend
    dispatch_plan.GhIssueBackend = gh_backend  # type: ignore[assignment]
    env_overrides = {"NSC_DISPATCH_TEST_STATES_FIXTURE": str(states_fixture)}
    if taskcontrol_log is not None:
        env_overrides["NSC_DISPATCH_TEST_TASKCONTROL_LOG"] = str(taskcontrol_log)
    previous_env = {key: os.environ.get(key) for key in env_overrides}
    os.environ.update(env_overrides)
    try:
        return build_dispatch_plan(
            source=checkout,
            worker_id="dispatch-plan-fixture-worker",
            remote=remote,
            policy=policy,
            claim_policy=claim_policy,
        )
    finally:
        dispatch_plan.GhIssueBackend = original_gh_backend  # type: ignore[assignment]
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _is_bulk_taskcontrol_call(command: Any) -> bool:
    return (
        isinstance(command, (tuple, list))
        and len(command) == 4
        and Path(str(command[1])).name == "taskcontrol.py"
        and list(command[2:]) == ["states", "--json"]
    )


def _run_with_taskcontrol_override(
    checkout: Path,
    *,
    states_fixture: Path,
    override: Any,
    gh_backend: Any = _FakeGhIssueBackend,
) -> tuple[DispatchPlan, int]:
    original_run = subprocess.run
    calls = 0

    def patched_run(command: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        if _is_bulk_taskcontrol_call(command):
            calls += 1
            return override(command, kwargs)
        return original_run(command, *args, **kwargs)

    subprocess.run = patched_run  # type: ignore[assignment]
    try:
        plan = _run_build_dispatch_plan(
            checkout,
            states_fixture=states_fixture,
            gh_backend=gh_backend,
        )
    finally:
        subprocess.run = original_run  # type: ignore[assignment]
    return plan, calls


def _observation_failure_fixture(
    *,
    payload: Any = None,
    raw_payload: bytes | None = None,
    tasks: dict[str, dict[str, Any]] | None = None,
    override: Any = None,
) -> DispatchPlan:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-observation-") as tmp:
        root = Path(tmp)
        tasks = tasks or {"NSC-860": make_task("NSC-860")}
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        head_commit = _git(checkout, "rev-parse", "HEAD")
        fixture_states = root / "states.json"
        if raw_payload is not None:
            fixture_states.write_bytes(raw_payload)
        else:
            selected_payload = payload
            if callable(selected_payload):
                selected_payload = selected_payload(tasks, head_commit)
            if selected_payload is None:
                selected_payload = _states_fixture(tasks, head_commit)
            fixture_states.write_text(json.dumps(selected_payload), encoding="utf-8")

        before_status = _git(checkout, "status", "--short")
        if override is None:
            plan = _run_build_dispatch_plan(checkout, states_fixture=fixture_states)
        else:
            plan, calls = _run_with_taskcontrol_override(
                checkout,
                states_fixture=fixture_states,
                override=override,
            )
            require(calls == 1, f"expected one failed bulk observation call, saw {calls}")
        after_status = _git(checkout, "status", "--short")
        require(before_status == after_status == "", "blocked observation path mutated the checkout")
        require(plan.decision == "blocked_invalid_state", f"unexpected decision: {plan.decision}")
        require(plan.resume is None, "blocked observation path returned resume work")
        require(plan.selected_fresh_candidate is None, "blocked observation path selected fresh work")
        return plan


def test_production_state_lookup_uses_one_bulk_snapshot_per_plan() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-fixture-") as tmp:
        root = Path(tmp)
        tasks = {
            "NSC-820": make_task("NSC-820", depends_on=["NSC-821", "NSC-822"]),
            "NSC-821": make_task("NSC-821"),
            "NSC-822": make_task("NSC-822"),
        }
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        head_commit = _git(checkout, "rev-parse", "HEAD")
        fixture_states = root / "states.json"
        fixture_states.write_text(json.dumps(_states_fixture(tasks, head_commit)), encoding="utf-8")
        log_path = root / "taskcontrol_calls.log"

        plan = _run_build_dispatch_plan(checkout, states_fixture=fixture_states, taskcontrol_log=log_path)

        require(plan.decision == "fresh_candidate", f"unexpected decision: {plan.decision}")
        calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        states_calls = [call for call in calls if call == ["states", "--json"]]
        per_task_calls = [call for call in calls if call and call[0] == "state"]
        require(len(states_calls) == 1, f"expected exactly one bulk 'states --json' call, saw: {calls}")
        require(not per_task_calls, f"per-task 'state <id> --json' subprocess calls must not happen: {calls}")


def test_production_resume_does_not_invoke_bulk_state_observation() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-resume-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-823": make_task("NSC-823")}
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        committed_task = dispatch_plan.load_committed_task(checkout, "NSC-823")
        memory_backend = MemoryIssueBackend()
        memory_service = IssueWorkflowService(
            backend=memory_backend,
            task_loader=lambda _task_id: committed_task,
            worker_id="resume-fixture-worker",
        )
        memory_service.acquire_agent_lease(
            task=committed_task,
            source_head=_git(checkout, "rev-parse", "HEAD"),
            branch="nsc-823-task",
            checkout_path=r"C:\NSC\NSC\NSC-823",
            planned_approach="Implement the fixture task.",
            expected_validation="Review the fixture result.",
            now="2026-08-31T10:00:00Z",
        )
        memory_service.publish_human_handoff(
            task_id="NSC-823",
            branch="nsc-823-task",
            head_commit="2" * 40,
            checkout_path=r"C:\NSC\NSC\NSC-823",
            implementation_summary="Fixture implementation complete.",
            completed_checks=("Fixture checks passed.",),
            human_steps=("Review the fixture.",),
            expected_result="Fixture is accepted.",
            now="2026-08-31T10:01:00Z",
        )
        memory_service.apply_human_result(
            task_id="NSC-823",
            result_body=(
                "## Human validation result\n\nResult: PASS\n"
                f"Tested commit: `{'2' * 40}`\n\nCompleted steps:\n- Reviewed.\n"
            ),
            actor_id="cathode26",
            now="2026-08-31T10:02:00Z",
        )

        class ResumeGhBackend:
            def __init__(self, *, source_root: Path) -> None:
                self.source_root = source_root

            def list_issues(self) -> list[dict[str, Any]]:
                return memory_backend.list_issues()

            def get_comments(self, issue_number: int) -> list[dict[str, Any]]:
                return memory_backend.get_comments(issue_number)

        fixture_states = root / "states-must-not-run.json"
        fixture_states.write_text("this would fail if read", encoding="utf-8")
        before_issues = json.dumps(memory_backend.issues, sort_keys=True)
        before_comments = json.dumps(memory_backend.comments, sort_keys=True)

        def forbidden_state_observation(_command: Any, _kwargs: Any) -> Any:
            raise AssertionError("resume_existing invoked the bulk TaskGraph state subprocess")

        plan, calls = _run_with_taskcontrol_override(
            checkout,
            states_fixture=fixture_states,
            override=forbidden_state_observation,
            gh_backend=ResumeGhBackend,
        )

        require(calls == 0, f"resume_existing invoked bulk state {calls} time(s)")
        require(plan.decision == "resume_existing", f"unexpected decision: {plan.decision}")
        require(plan.resume is not None and plan.resume["task_id"] == "NSC-823", str(plan.resume))
        require(json.dumps(memory_backend.issues, sort_keys=True) == before_issues, "resume planning mutated Issues")
        require(json.dumps(memory_backend.comments, sort_keys=True) == before_comments, "resume planning mutated comments")


def test_bulk_state_timeout_returns_blocked_invalid_state() -> None:
    def timeout(command: Any, kwargs: dict[str, Any]) -> Any:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    plan = _observation_failure_fixture(override=timeout)
    require(any("timed out" in reason for reason in plan.reasons), str(plan.reasons))


def test_bulk_state_launch_failure_returns_blocked_invalid_state() -> None:
    def launch_failure(_command: Any, _kwargs: dict[str, Any]) -> Any:
        raise OSError("synthetic launch failure")

    plan = _observation_failure_fixture(override=launch_failure)
    require(any("launch failed" in reason for reason in plan.reasons), str(plan.reasons))


def test_bulk_state_nonzero_exit_returns_blocked_with_bounded_stderr() -> None:
    def nonzero(command: Any, _kwargs: dict[str, Any]) -> Any:
        return subprocess.CompletedProcess(
            command,
            17,
            stdout=b"",
            stderr=b"synthetic nonzero detail " + (b"x" * 5000),
        )

    plan = _observation_failure_fixture(override=nonzero)
    require(any("exited nonzero (17)" in reason for reason in plan.reasons), str(plan.reasons))
    require(any("synthetic nonzero detail" in reason for reason in plan.reasons), str(plan.reasons))
    require(max(len(reason) for reason in plan.reasons) < 1200, "nonzero stderr was not bounded")


def test_bulk_state_invalid_json_returns_blocked_invalid_state() -> None:
    plan = _observation_failure_fixture(raw_payload=b"{not-json")
    require(any("invalid UTF-8/JSON" in reason for reason in plan.reasons), str(plan.reasons))


def test_bulk_state_invalid_utf8_returns_blocked_invalid_state() -> None:
    def invalid_utf8(command: Any, _kwargs: dict[str, Any]) -> Any:
        return subprocess.CompletedProcess(command, 0, stdout=b"\xff", stderr=b"")

    plan = _observation_failure_fixture(override=invalid_utf8)
    require(any("invalid UTF-8/JSON" in reason for reason in plan.reasons), str(plan.reasons))


def test_bulk_state_non_list_payload_returns_blocked_invalid_state() -> None:
    plan = _observation_failure_fixture(payload={"task_id": "NSC-860"})
    require(any("expected a JSON list" in reason for reason in plan.reasons), str(plan.reasons))


def test_bulk_state_malformed_entry_returns_blocked_invalid_state() -> None:
    plan = _observation_failure_fixture(payload=[{"task_id": "NSC-860", "state": 7}])
    require(any("malformed state entry" in reason for reason in plan.reasons), str(plan.reasons))


def test_bulk_state_duplicate_task_id_returns_blocked_invalid_state() -> None:
    def duplicate(tasks: dict[str, dict[str, Any]], head_commit: str) -> list[dict[str, Any]]:
        payload = _states_fixture(tasks, head_commit)
        return payload + [dict(payload[0])]

    plan = _observation_failure_fixture(payload=duplicate)
    require(any("duplicate task ID" in reason for reason in plan.reasons), str(plan.reasons))


def test_bulk_state_missing_expected_task_returns_blocked_invalid_state() -> None:
    tasks = {
        "NSC-861": make_task("NSC-861"),
        "NSC-862": make_task("NSC-862"),
    }

    def missing(tasks: dict[str, dict[str, Any]], head_commit: str) -> list[dict[str, Any]]:
        return _states_fixture(tasks, head_commit)[:1]

    plan = _observation_failure_fixture(tasks=tasks, payload=missing)
    require(any("missing=['NSC-862']" in reason for reason in plan.reasons), str(plan.reasons))


def test_bulk_state_unexpected_extra_task_returns_blocked_invalid_state() -> None:
    def extra(tasks: dict[str, dict[str, Any]], head_commit: str) -> list[dict[str, Any]]:
        payload = _states_fixture(tasks, head_commit)
        payload.append(
            {
                "task_id": "NSC-999",
                "state": "not_delivered",
                "head_commit": head_commit,
            }
        )
        return payload

    plan = _observation_failure_fixture(payload=extra)
    require(any("unexpected=['NSC-999']" in reason for reason in plan.reasons), str(plan.reasons))


def test_bulk_state_missing_head_returns_blocked_invalid_state() -> None:
    def missing_head(tasks: dict[str, dict[str, Any]], head_commit: str) -> list[dict[str, Any]]:
        payload = _states_fixture(tasks, head_commit)
        payload[0].pop("head_commit")
        return payload

    plan = _observation_failure_fixture(payload=missing_head)
    require(any("missing/invalid head_commit" in reason for reason in plan.reasons), str(plan.reasons))


def test_bulk_state_unrecognized_state_value_returns_blocked_invalid_state() -> None:
    # Full coverage, correct task ID, correct source HEAD, valid JSON -- the
    # ONLY defect is a state string the committed dispatch policy does not
    # recognize. That is a producer regression and must fail the whole
    # observation as blocked_invalid_state, never degrade into per-task
    # rejections that end in an ordinary no_safe_work.
    def unrecognized_state(tasks: dict[str, dict[str, Any]], head_commit: str) -> list[dict[str, Any]]:
        return _states_fixture(tasks, head_commit, states={"NSC-860": "banana"})

    plan = _observation_failure_fixture(payload=unrecognized_state)
    require(plan.selected_fresh_candidate is None, "unrecognized snapshot state still selected fresh work")
    require(
        any(
            "unrecognized state" in reason and "'banana'" in reason and "NSC-860" in reason
            for reason in plan.reasons
        ),
        f"missing unrecognized-state observation reason: {plan.reasons}",
    )


def test_complete_bulk_snapshot_with_no_eligible_work_returns_no_safe_work() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-no-safe-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-870": make_task("NSC-870")}
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        head_commit = _git(checkout, "rev-parse", "HEAD")
        fixture_states = root / "states.json"
        fixture_states.write_text(
            json.dumps(_states_fixture(tasks, head_commit, states={"NSC-870": "conformant"})),
            encoding="utf-8",
        )
        plan = _run_build_dispatch_plan(checkout, states_fixture=fixture_states)
        require(plan.decision == "no_safe_work", f"unexpected decision: {plan.decision}")


def test_complete_bulk_snapshot_preserves_deterministic_fresh_ranking() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-ranking-") as tmp:
        root = Path(tmp)
        tasks = {
            "NSC-899": make_task("NSC-899"),
            "NSC-871": make_task("NSC-871"),
            "NSC-880": make_task("NSC-880"),
        }
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        head_commit = _git(checkout, "rev-parse", "HEAD")
        fixture_states = root / "states.json"
        fixture_states.write_text(json.dumps(_states_fixture(tasks, head_commit)), encoding="utf-8")
        plan = _run_build_dispatch_plan(checkout, states_fixture=fixture_states)
        require(plan.decision == "fresh_candidate", f"unexpected decision: {plan.decision}")
        require(
            [item["task_id"] for item in plan.ranked_eligible_candidates]
            == ["NSC-871", "NSC-880", "NSC-899"],
            str(plan.ranked_eligible_candidates),
        )
        require(plan.selected_fresh_candidate is not None, "fresh ranking selected nothing")
        require(plan.selected_fresh_candidate["task_id"] == "NSC-871", str(plan.selected_fresh_candidate))


def test_transient_claim_read_failure_yields_provisional_plan_not_pretend_observed() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-fixture-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-830": make_task("NSC-830")}
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        head_commit = _git(checkout, "rev-parse", "HEAD")
        fixture_states = root / "states.json"
        fixture_states.write_text(json.dumps(_states_fixture(tasks, head_commit)), encoding="utf-8")

        plan = _run_build_dispatch_plan(
            checkout, states_fixture=fixture_states, remote="nonexistent-claim-remote-xyz"
        )

        require(plan.decision == "fresh_candidate", f"unexpected decision: {plan.decision}")
        require(plan.claim_observation.get("status") == "unavailable", str(plan.claim_observation))
        require(
            any("Stage 3 atomic claim remains authoritative" in reason for reason in plan.reasons),
            f"missing provisional claim-unavailable reason: {plan.reasons}",
        )
        require(
            plan.selected_fresh_candidate is not None
            and plan.selected_fresh_candidate["task_id"] == "NSC-830",
            str(plan.selected_fresh_candidate),
        )


def test_invalid_committed_claim_policy_returns_blocked_invalid_state() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-fixture-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-840": make_task("NSC-840")}
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        head_commit = _git(checkout, "rev-parse", "HEAD")
        fixture_states = root / "states.json"
        fixture_states.write_text(json.dumps(_states_fixture(tasks, head_commit)), encoding="utf-8")

        original_load_claim_policy = dispatch_plan.load_claim_policy

        def _broken_claim_policy(*_args: Any, **_kwargs: Any) -> Any:
            raise ClaimPolicyError("synthetic corrupted committed claim policy for this test")

        dispatch_plan.load_claim_policy = _broken_claim_policy  # type: ignore[assignment]
        try:
            plan = _run_build_dispatch_plan(checkout, states_fixture=fixture_states)
        finally:
            dispatch_plan.load_claim_policy = original_load_claim_policy  # type: ignore[assignment]

        require(plan.decision == "blocked_invalid_state", f"unexpected decision: {plan.decision}")
        require(
            any("claim policy is invalid" in reason for reason in plan.reasons),
            f"missing invalid-committed-claim-policy reason: {plan.reasons}",
        )


def test_states_snapshot_head_commit_mismatch_returns_blocked_invalid_state() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-fixture-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-851": make_task("NSC-851")}
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        fixture_states = root / "states.json"
        fixture_states.write_text(
            json.dumps(_states_fixture(tasks, "f" * 40)), encoding="utf-8"
        )

        plan = _run_build_dispatch_plan(checkout, states_fixture=fixture_states)

        require(plan.decision == "blocked_invalid_state", f"unexpected decision: {plan.decision}")
        require(
            any("different from the captured source_commit" in reason for reason in plan.reasons),
            f"missing states-snapshot HEAD-mismatch reason: {plan.reasons}",
        )


def test_head_drift_during_planning_returns_blocked_invalid_state() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-fixture-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-852": make_task("NSC-852")}
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        head_commit = _git(checkout, "rev-parse", "HEAD")
        fixture_states = root / "states.json"
        fixture_states.write_text(json.dumps(_states_fixture(tasks, head_commit)), encoding="utf-8")

        previous_mutate_env = os.environ.get("NSC_DISPATCH_TEST_MUTATE_HEAD_DURING_STATES")
        os.environ["NSC_DISPATCH_TEST_MUTATE_HEAD_DURING_STATES"] = "1"
        try:
            plan = _run_build_dispatch_plan(checkout, states_fixture=fixture_states)
        finally:
            if previous_mutate_env is None:
                os.environ.pop("NSC_DISPATCH_TEST_MUTATE_HEAD_DURING_STATES", None)
            else:
                os.environ["NSC_DISPATCH_TEST_MUTATE_HEAD_DURING_STATES"] = previous_mutate_env

        require(plan.decision == "blocked_invalid_state", f"unexpected decision: {plan.decision}")
        require(
            any("HEAD moved" in reason for reason in plan.reasons),
            f"missing HEAD-drift-during-planning reason: {plan.reasons}",
        )


# --------------------------------------------------------------------------
# Consensus-repair regressions: policy self-consistency (fresh subset of
# known, on JSON loading AND direct construction), one effective policy for
# both snapshot recognition and candidate evaluation, and the guarantee that
# a normal fresh/no-safe plan actually observed one validated bulk snapshot.
# --------------------------------------------------------------------------


def test_policy_fresh_state_outside_known_set_is_rejected_on_load() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-policy-fresh-") as tmp:
        inconsistent_path = Path(tmp) / "dispatch_policy.json"
        raw = json.loads(
            (ROOT / "Pipeline" / "TaskReviewAgent" / "dispatch_policy.json").read_text("utf-8")
        )
        raw["fresh_implementation_derived_states"] = list(
            raw["fresh_implementation_derived_states"]
        ) + ["phantom_fresh_state"]
        inconsistent_path.write_text(json.dumps(raw), encoding="utf-8")
        try:
            load_dispatch_policy(inconsistent_path)
            raise AssertionError(
                "a policy whose fresh state is unrecognized by known_dependency_states was accepted"
            )
        except DispatchPolicyError as exc:
            require("fresh_implementation_derived_states" in str(exc), str(exc))
            require("known_dependency_states" in str(exc), str(exc))


def test_directly_constructed_policy_enforces_both_subset_invariants() -> None:
    committed = load_dispatch_policy()

    # Fresh state absent from known: rejected even without the JSON loader.
    try:
        dataclasses.replace(
            committed,
            fresh_implementation_derived_states=committed.fresh_implementation_derived_states
            + ("phantom_fresh_state",),
        )
        raise AssertionError("a directly constructed fresh-not-known policy was accepted")
    except DispatchPolicyError as exc:
        require("fresh_implementation_derived_states" in str(exc), str(exc))

    # The pre-existing dependency-satisfied subset invariant must also hold
    # for direct construction, not only load_dispatch_policy().
    try:
        dataclasses.replace(
            committed,
            dependency_dispatch_satisfied_states=committed.dependency_dispatch_satisfied_states
            + ("phantom_satisfied_state",),
        )
        raise AssertionError("a directly constructed satisfied-not-known policy was accepted")
    except DispatchPolicyError as exc:
        require("dependency_dispatch_satisfied_states" in str(exc), str(exc))


def test_consistent_extended_policy_remains_valid_for_load_and_construction() -> None:
    committed = load_dispatch_policy()

    # Direct construction: the same new state added to BOTH sets is valid.
    extended = dataclasses.replace(
        committed,
        fresh_implementation_derived_states=committed.fresh_implementation_derived_states
        + ("fixture_pilot_state",),
        known_dependency_states=committed.known_dependency_states + ("fixture_pilot_state",),
    )
    require(
        "fixture_pilot_state" in extended.fresh_implementation_derived_states
        and "fixture_pilot_state" in extended.known_dependency_states,
        "consistent extended policy construction failed",
    )

    # JSON loading: the same deliberate extension is also valid.
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-policy-extended-") as tmp:
        extended_path = Path(tmp) / "dispatch_policy.json"
        raw = json.loads(
            (ROOT / "Pipeline" / "TaskReviewAgent" / "dispatch_policy.json").read_text("utf-8")
        )
        raw["fresh_implementation_derived_states"] = list(
            raw["fresh_implementation_derived_states"]
        ) + ["fixture_pilot_state"]
        raw["known_dependency_states"] = list(raw["known_dependency_states"]) + [
            "fixture_pilot_state"
        ]
        extended_path.write_text(json.dumps(raw), encoding="utf-8")
        loaded = load_dispatch_policy(extended_path)
        require(
            "fixture_pilot_state" in loaded.fresh_implementation_derived_states,
            str(loaded.fresh_implementation_derived_states),
        )


def test_one_effective_policy_controls_snapshot_recognition_and_candidate_evaluation() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-one-policy-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-881": make_task("NSC-881")}
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        head_commit = _git(checkout, "rev-parse", "HEAD")
        fixture_states = root / "states.json"
        fixture_states.write_text(
            json.dumps(_states_fixture(tasks, head_commit, states={"NSC-881": "fixture_pilot_state"})),
            encoding="utf-8",
        )

        # Under the committed policy the snapshot state is unrecognized, so
        # snapshot recognition (not per-candidate evaluation) fails the plan.
        committed_plan = _run_build_dispatch_plan(checkout, states_fixture=fixture_states)
        require(
            committed_plan.decision == "blocked_invalid_state",
            f"unexpected decision under committed policy: {committed_plan.decision}",
        )
        require(
            any("unrecognized state" in reason for reason in committed_plan.reasons),
            str(committed_plan.reasons),
        )

        # The SAME injected extended policy instance must then govern both
        # authorities at once: the snapshot recognizes the state AND the
        # candidate kernel admits it as fresh, with no second policy source.
        extended = dataclasses.replace(
            load_dispatch_policy(),
            fresh_implementation_derived_states=load_dispatch_policy().fresh_implementation_derived_states
            + ("fixture_pilot_state",),
            known_dependency_states=load_dispatch_policy().known_dependency_states
            + ("fixture_pilot_state",),
        )
        extended_plan = _run_build_dispatch_plan(
            checkout, states_fixture=fixture_states, policy=extended
        )
        require(
            extended_plan.decision == "fresh_candidate",
            f"unexpected decision under extended policy: {extended_plan.decision}; "
            f"reasons={extended_plan.reasons}",
        )
        require(
            extended_plan.selected_fresh_candidate is not None
            and extended_plan.selected_fresh_candidate["derived_state"] == "fixture_pilot_state",
            str(extended_plan.selected_fresh_candidate),
        )


def test_invalid_committed_dispatch_policy_returns_blocked_invalid_state() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-bad-policy-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-882": make_task("NSC-882")}
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        head_commit = _git(checkout, "rev-parse", "HEAD")
        fixture_states = root / "states.json"
        fixture_states.write_text(json.dumps(_states_fixture(tasks, head_commit)), encoding="utf-8")

        original_load_dispatch_policy = dispatch_plan.load_dispatch_policy

        def _broken_dispatch_policy(*_args: Any, **_kwargs: Any) -> Any:
            raise DispatchPolicyError("synthetic inconsistent committed dispatch policy for this test")

        dispatch_plan.load_dispatch_policy = _broken_dispatch_policy  # type: ignore[assignment]
        try:
            plan = _run_build_dispatch_plan(checkout, states_fixture=fixture_states)
        finally:
            dispatch_plan.load_dispatch_policy = original_load_dispatch_policy  # type: ignore[assignment]

        require(plan.decision == "blocked_invalid_state", f"unexpected decision: {plan.decision}")
        require(
            any("dispatch policy is invalid" in reason for reason in plan.reasons),
            f"missing invalid-committed-dispatch-policy reason: {plan.reasons}",
        )


def test_no_safe_work_requires_one_validated_bulk_snapshot() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-no-safe-snapshot-") as tmp:
        root = Path(tmp)
        tasks = {"NSC-883": make_task("NSC-883")}
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        head_commit = _git(checkout, "rev-parse", "HEAD")
        fixture_states = root / "states.json"
        fixture_states.write_text(
            json.dumps(_states_fixture(tasks, head_commit, states={"NSC-883": "conformant"})),
            encoding="utf-8",
        )
        log_path = root / "taskcontrol_calls.log"

        plan = _run_build_dispatch_plan(checkout, states_fixture=fixture_states, taskcontrol_log=log_path)

        require(plan.decision == "no_safe_work", f"unexpected decision: {plan.decision}")
        calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        states_calls = [call for call in calls if call == ["states", "--json"]]
        require(
            len(states_calls) == 1,
            f"a normal no_safe_work plan must observe exactly one validated bulk snapshot: {calls}",
        )


def test_all_task_loads_failing_with_failing_snapshot_is_blocked_not_no_safe_work() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-loads-fail-") as tmp:
        root = Path(tmp)
        # A committed contract that is not a JSON object fails
        # load_committed_task BEFORE the candidate's own-state lookup, so
        # lazy evaluation alone would never touch the state provider.
        tasks: dict[str, Any] = {"NSC-884": ["deliberately", "not", "a", "contract", "object"]}
        checkout, _remote = create_production_fixture(root, tasks=tasks)
        fixture_states = root / "states.json"
        fixture_states.write_text("[]", encoding="utf-8")

        def timeout(command: Any, kwargs: dict[str, Any]) -> Any:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        plan, calls = _run_with_taskcontrol_override(
            checkout, states_fixture=fixture_states, override=timeout
        )

        require(calls == 1, f"expected exactly one required-observation attempt, saw {calls}")
        require(
            plan.decision == "blocked_invalid_state",
            "a failed required bulk observation degraded into an ordinary decision: "
            f"{plan.decision}",
        )
        require(any("timed out" in reason for reason in plan.reasons), str(plan.reasons))


def test_empty_committed_task_enumeration_without_resume_is_blocked() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dispatch-empty-tasks-") as tmp:
        root = Path(tmp)
        checkout, _remote = create_production_fixture(root, tasks={})
        fixture_states = root / "states.json"
        fixture_states.write_text("[]", encoding="utf-8")

        def forbidden(_command: Any, _kwargs: dict[str, Any]) -> Any:
            raise AssertionError("an empty task universe still forced the bulk state observation")

        plan, calls = _run_with_taskcontrol_override(
            checkout, states_fixture=fixture_states, override=forbidden
        )

        require(calls == 0, f"empty enumeration invoked bulk state {calls} time(s)")
        require(
            plan.decision == "blocked_invalid_state",
            f"empty committed task enumeration returned an ordinary decision: {plan.decision}",
        )
        require(
            any("no committed Tasks/NSC-*.yaml contracts" in reason for reason in plan.reasons),
            str(plan.reasons),
        )


# --------------------------------------------------------------------------
# Pending transition must not reject disjoint fresh work (review B3 / A7(d)).
#
# These drive the REAL plan_dispatch kernel, the REAL IssueWorkflowService and
# the REAL _resource_conflicts_classified path. No planner is injected.
# --------------------------------------------------------------------------

import datetime as _pending_dt  # noqa: E402

import Pipeline.TaskReviewAgent.issue_workflow_store as pending_store  # noqa: E402

PENDING_HOLDER = "NSC-780"
PENDING_RESOURCE = "unity-scene:Assets/Scenes/PendingHolder.unity"
AGENT_READY_LABEL = "nsc-state:agent-ready"
_PENDING_BASE = _pending_dt.datetime(2026, 9, 4, tzinfo=_pending_dt.timezone.utc)


def _pending_stamp(offset_seconds: float) -> str:
    moment = _PENDING_BASE + _pending_dt.timedelta(seconds=offset_seconds)
    return moment.isoformat().replace("+00:00", "Z")


@contextmanager
def _frozen_pending_clock(offset_seconds: float):
    original = pending_store.pending_transition_now
    pending_store.pending_transition_now = (
        lambda: _PENDING_BASE + _pending_dt.timedelta(seconds=offset_seconds)
    )
    try:
        yield
    finally:
        pending_store.pending_transition_now = original


def _workflow_with_pending_holder(tasks: dict[str, dict[str, Any]]):
    """Real service whose holder Issue sits in the additive-label UI window."""

    backend, service = fresh_issue_workflow(tasks)
    # Managed label writes record GitHub-shaped label events at the backend
    # clock; pin it before the human's later UI label event so event order is
    # deterministic instead of depending on the machine clock.
    backend.now = lambda: _pending_stamp(0)
    service.acquire_agent_lease(
        task=tasks[PENDING_HOLDER],
        source_head=SOURCE_HEAD,
        branch="nsc-780-pending-holder",
        checkout_path=r"C:\NSC\NSC\NSC-780",
        planned_approach="Hold the shared scene.",
        expected_validation="Vincent completes the Unity checklist.",
        now=_pending_stamp(0),
    )
    service.publish_human_handoff(
        task_id=PENDING_HOLDER,
        branch="nsc-780-pending-holder",
        head_commit="2" * 40,
        checkout_path=r"C:\NSC\NSC\NSC-780",
        implementation_summary="Fixture handoff.",
        completed_checks=["deterministic checks"],
        human_steps=["Open the canonical checkout."],
        expected_result="The doorway publishes once.",
        now=_pending_stamp(60),
    )
    issue = backend.issues[next(iter(backend.issues))]
    # The GitHub UI ADDS agent-ready beside the authoritative state label.
    names = sorted({item["name"] for item in issue["labels"]} | {AGENT_READY_LABEL})
    issue["labels"] = [{"name": name} for name in names]
    # The window is dated by GitHub's `labeled` event for the target label,
    # never by the Issue's general updated_at.
    backend.record_label_event(
        issue["number"], label=AGENT_READY_LABEL, created_at=_pending_stamp(120)
    )
    return backend, service


def test_pending_issue_does_not_reject_disjoint_fresh_candidate() -> None:
    tasks = {
        PENDING_HOLDER: make_task(
            PENDING_HOLDER, exclusive_resources=[PENDING_RESOURCE]
        ),
        "NSC-781": make_task("NSC-781"),
    }
    states = {PENDING_HOLDER: "not_delivered", "NSC-781": "not_delivered"}
    _backend, issue_workflow = _workflow_with_pending_holder(tasks)
    with _frozen_pending_clock(180):
        plan = plan_dispatch(
            source_commit=SOURCE_HEAD,
            task_ids=list(tasks),
            task_loader=build_task_loader(tasks),
            state_provider=build_state_provider(states),
            issue_workflow=issue_workflow,
        )
    require(
        plan.decision == "fresh_candidate",
        f"a pending Issue rejected all fresh work: {plan.decision} {plan.reasons}",
    )
    require(
        plan.selected_fresh_candidate["task_id"] == "NSC-781",
        f"disjoint candidate was not selected: {plan.selected_fresh_candidate}",
    )


def test_pending_issue_still_reserves_its_exclusive_resource() -> None:
    tasks = {
        PENDING_HOLDER: make_task(
            PENDING_HOLDER, exclusive_resources=[PENDING_RESOURCE]
        ),
        "NSC-782": make_task("NSC-782", exclusive_resources=[PENDING_RESOURCE]),
    }
    states = {PENDING_HOLDER: "not_delivered", "NSC-782": "not_delivered"}
    _backend, issue_workflow = _workflow_with_pending_holder(tasks)
    with _frozen_pending_clock(180):
        conflicts, _diagnostics = issue_workflow.resource_conflicts(tasks["NSC-782"])
        decision = evaluate(
            "NSC-782", tasks, states, issue_workflow=issue_workflow
        )
    require(
        any(PENDING_HOLDER in item and PENDING_RESOURCE in item for item in conflicts),
        f"pending Issue stopped reserving its scene: {conflicts}",
    )
    require(
        not any("must be repaired" in item for item in conflicts),
        f"pending Issue was reported as corrupt state: {conflicts}",
    )
    require(
        not decision.eligible,
        "a candidate sharing the pending task's scene was ruled eligible",
    )
    require(
        any(
            "resource" in code or "conflict" in code
            for code in decision.reason_codes
        ),
        f"overlap was not the stated rejection reason: {decision.reason_codes}",
    )


def main() -> int:
    tests = (
        test_pending_issue_does_not_reject_disjoint_fresh_candidate,
        test_pending_issue_still_reserves_its_exclusive_resource,
        test_resume_beats_every_fresh_candidate,
        test_not_delivered_candidate_selected_when_no_actionable_issue,
        test_needs_testing_is_not_a_fresh_candidate,
        test_already_conformant_task_rejected_as_fresh,
        test_conformant_dependency_is_dispatch_satisfied,
        test_needs_testing_dependency_is_dispatch_satisfied_but_flagged,
        test_not_delivered_dependency_blocks,
        test_unrecognized_dependency_states_fail_closed,
        test_non_single_agent_candidate_rejected,
        test_non_concrete_decomposition_state_rejected,
        test_inactive_disposition_candidate_rejected,
        test_existing_issue_ownership_rejects_duplicate_fresh_selection,
        test_durable_exclusive_resource_overlap_rejects_candidate,
        test_invalid_managed_issue_state_fails_closed,
        test_active_stage1_task_claim_rejects_candidate,
        test_active_stage1_resource_claim_rejects_candidate,
        test_disjoint_active_claim_does_not_reject_candidate,
        test_ranking_is_deterministic_independent_of_enumeration_order,
        test_explicit_and_generic_evaluation_share_one_safety_kernel,
        test_planner_performs_no_mutations,
        test_no_safe_work_is_a_typed_outcome_not_an_exception,
        test_autonomous_dispatch_remains_disabled,
        test_select_agent_ready_task_compatibility_preserved,
        test_malformed_resource_token_rejects_only_that_candidate,
        test_complete_historical_issue_does_not_block_fresh_candidate,
        test_production_state_lookup_uses_one_bulk_snapshot_per_plan,
        test_production_resume_does_not_invoke_bulk_state_observation,
        test_bulk_state_timeout_returns_blocked_invalid_state,
        test_bulk_state_launch_failure_returns_blocked_invalid_state,
        test_bulk_state_nonzero_exit_returns_blocked_with_bounded_stderr,
        test_bulk_state_invalid_json_returns_blocked_invalid_state,
        test_bulk_state_invalid_utf8_returns_blocked_invalid_state,
        test_bulk_state_non_list_payload_returns_blocked_invalid_state,
        test_bulk_state_malformed_entry_returns_blocked_invalid_state,
        test_bulk_state_duplicate_task_id_returns_blocked_invalid_state,
        test_bulk_state_missing_expected_task_returns_blocked_invalid_state,
        test_bulk_state_unexpected_extra_task_returns_blocked_invalid_state,
        test_bulk_state_missing_head_returns_blocked_invalid_state,
        test_bulk_state_unrecognized_state_value_returns_blocked_invalid_state,
        test_complete_bulk_snapshot_with_no_eligible_work_returns_no_safe_work,
        test_complete_bulk_snapshot_preserves_deterministic_fresh_ranking,
        test_transient_claim_read_failure_yields_provisional_plan_not_pretend_observed,
        test_invalid_committed_claim_policy_returns_blocked_invalid_state,
        test_states_snapshot_head_commit_mismatch_returns_blocked_invalid_state,
        test_head_drift_during_planning_returns_blocked_invalid_state,
        test_policy_fresh_state_outside_known_set_is_rejected_on_load,
        test_directly_constructed_policy_enforces_both_subset_invariants,
        test_consistent_extended_policy_remains_valid_for_load_and_construction,
        test_one_effective_policy_controls_snapshot_recognition_and_candidate_evaluation,
        test_invalid_committed_dispatch_policy_returns_blocked_invalid_state,
        test_no_safe_work_requires_one_validated_bulk_snapshot,
        test_all_task_loads_failing_with_failing_snapshot_is_blocked_not_no_safe_work,
        test_empty_committed_task_enumeration_without_resume_is_blocked,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Stage 2 dispatch-plan tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
