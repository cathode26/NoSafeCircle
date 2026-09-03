#!/usr/bin/env python3
"""Prove pushed handoff and later-agent checkout continuity."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.contracts import TaskReviewContractError  # noqa: E402
from Pipeline.TaskReviewAgent.durable_checkout import DurableTaskCheckoutManager  # noqa: E402
from Pipeline.TaskReviewAgent.goal_loop import GoalAction, assess_goal_state  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    initial_state,
    transition,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)
from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow  # noqa: E402
from Pipeline.TaskReviewAgent.tests.real_checkout_smoke_test import (  # noqa: E402
    TASK_ID,
    create_fixture,
    git,
)

WORKER_A = "agent-a"
WORKER_B = "agent-b"
BRANCH = "nsc-777-synthetic-checkout-task"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_error(action, text: str) -> None:
    try:
        action()
    except TaskReviewContractError as exc:
        require(text in str(exc), f"unexpected error: {exc}")
    else:
        raise AssertionError(f"expected TaskReviewContractError containing {text!r}")


def contract_facts(controller: Path) -> tuple[dict, str, str]:
    raw = __import__("subprocess").check_output(
        ("git", "-C", str(controller), "show", f"HEAD:Tasks/{TASK_ID}.yaml")
    )
    return (
        json.loads(raw.decode("utf-8-sig")),
        hashlib.sha256(raw).hexdigest(),
        git(controller, "rev-parse", "HEAD^{tree}"),
    )


def lease(state, *, worker: str, source_head: str, checkout: Path, now: str):
    return transition(
        state,
        event_type=WorkflowEventType.AGENT_LEASE_ACQUIRED,
        actor_type=WorkflowActor.AGENT,
        actor_id=worker,
        to_state=WorkflowState.AGENT_WORKING,
        details={
            "worker_id": worker,
            "lease_id": ("a" if worker == WORKER_A else "b") * 64,
            "source_head": source_head,
            "branch": BRANCH,
            "checkout_path": str(checkout),
        },
        now=now,
    )[0]


def observation(
    *,
    controller: Path,
    remote: Path,
    contract: dict,
    contract_hash: str,
    source_head: str,
    source_tree: str,
    state,
    worker: str,
) -> dict:
    return {
        "schema_version": "1.0",
        "observation_authority": "real_read_only",
        "environment": {
            "ready": True,
            "controller_clean": True,
            "taskgraph_valid": True,
            "source_head": source_head,
            "source_tree": source_tree,
            "origin_main": source_head,
            "remote_url": str(remote),
        },
        "task": {
            "task_id": TASK_ID,
            "title": contract["title"],
            "contract_path": f"Tasks/{TASK_ID}.yaml",
            "contract_revision": contract["contract_revision"],
            "contract_disposition": "active",
            "kind": "implementation",
            "execution_scope": "single_agent",
            "decomposition_state": "concrete",
            "derived_state": "not_delivered",
            "dependencies_conformant": True,
            "task_contract_sha256": contract_hash,
        },
        "coordination": {
            "status": "claimed_by_worker",
            "workflow_status": "agent_working_by_worker",
            "worker_id": worker,
            "workflow_state": state.to_dict(),
            "reasons": [],
        },
    }


def commit_change(checkout: Path) -> str:
    git(checkout, "config", "user.name", "TaskReviewAgent")
    git(checkout, "config", "user.email", "agent@example.invalid")
    (checkout / "implementation.txt").write_text("implemented\n", encoding="utf-8")
    git(checkout, "add", "implementation.txt")
    git(checkout, "commit", "-m", "Implement synthetic task")
    return git(checkout, "rev-parse", "HEAD")


def test_checkout_survives_human_and_new_agent() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-durable-checkout-") as temporary:
        root = Path(temporary)
        controller, remote, source_head = create_fixture(root)
        contract, contract_hash, source_tree = contract_facts(controller)
        checkout_root = root / "operator"
        checkout = checkout_root / TASK_ID
        state = initial_state(
            task_id=TASK_ID,
            task_contract_sha256=contract_hash,
            now="2026-08-27T13:00:00Z",
        )
        state = lease(
            state,
            worker=WORKER_A,
            source_head=source_head,
            checkout=checkout,
            now="2026-08-27T13:01:00Z",
        )
        first_observation = observation(
            controller=controller,
            remote=remote,
            contract=contract,
            contract_hash=contract_hash,
            source_head=source_head,
            source_tree=source_tree,
            state=state,
            worker=WORKER_A,
        )
        manager_a = DurableTaskCheckoutManager(
            source_root=controller,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id=WORKER_A,
            allow_local_remote_for_tests=True,
        )
        created = manager_a.prepare(first_observation)
        require(created["status"] == "ready", f"fresh checkout failed: {created}")

        handoff_head = commit_change(checkout)
        git(checkout, "push", "-u", "origin", BRANCH)
        state, _ = transition(
            state,
            event_type=WorkflowEventType.HUMAN_HANDOFF_CREATED,
            actor_type=WorkflowActor.AGENT,
            actor_id=WORKER_A,
            to_state=WorkflowState.HUMAN_ACTION_REQUIRED,
            to_phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
            details={
                "branch": BRANCH,
                "head_commit": handoff_head,
                "checkout_path": str(checkout),
            },
            now="2026-08-27T13:02:00Z",
        )
        state, _ = transition(
            state,
            event_type=WorkflowEventType.HUMAN_VALIDATION_FAILED,
            actor_type=WorkflowActor.HUMAN,
            actor_id="Vincent",
            to_state=WorkflowState.AGENT_READY,
            to_phase=WorkflowPhase.REPAIR,
            details={"tested_commit": handoff_head, "result": "fail"},
            now="2026-08-27T13:03:00Z",
        )
        state = lease(
            state,
            worker=WORKER_B,
            source_head=source_head,
            checkout=checkout,
            now="2026-08-27T13:04:00Z",
        )
        resume_observation = observation(
            controller=controller,
            remote=remote,
            contract=contract,
            contract_hash=contract_hash,
            source_head=source_head,
            source_tree=source_tree,
            state=state,
            worker=WORKER_B,
        )
        manager_b = DurableTaskCheckoutManager(
            source_root=controller,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id=WORKER_B,
            allow_local_remote_for_tests=True,
        )
        inspected = manager_b.inspect(resume_observation)
        require(inspected["status"] == "ready", f"new worker could not resume: {inspected}")
        require(inspected["head_commit"] == handoff_head, "handoff commit changed")

        saved_checkout = root / "saved-checkout"
        checkout.rename(saved_checkout)
        require(not checkout.exists(), "canonical checkout path was not released")
        recloned = manager_b.prepare(resume_observation)
        require(recloned["status"] == "ready", f"remote branch resume failed: {recloned}")
        require(git(checkout, "rev-parse", "HEAD") == handoff_head, "wrong resumed commit")
        require(git(checkout, "branch", "--show-current") == BRANCH, "wrong resumed branch")
        require(
            git(checkout, "status", "--porcelain=v1", "--untracked-files=all") == "",
            "resumed checkout is dirty",
        )
        require(git(controller, "rev-parse", "HEAD") == source_head, "controller changed")
        require(
            git(controller, "status", "--porcelain=v1", "--untracked-files=all") == "",
            "controller was dirtied",
        )
        require(saved_checkout.is_dir(), "original checkout evidence was not preserved")


def test_real_workflow_rejects_unpushed_handoff() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-pushed-handoff-") as temporary:
        root = Path(temporary)
        controller, _, _ = create_fixture(root)
        contract, contract_hash, _ = contract_facts(controller)
        task_record = {**contract, "task_contract_sha256": contract_hash}
        backend = MemoryIssueBackend()
        service = IssueWorkflowService(
            backend=backend,
            task_loader=lambda task_id: task_record,
            worker_id=WORKER_A,
        )
        workflow = RealTaskReviewWorkflow(
            source=controller,
            task_id=TASK_ID,
            checkout_root=root / "operator",
            worker_id=WORKER_A,
            issue_workflow_service=service,
            allow_local_remote_for_tests=True,
        )
        first = workflow.observe_goal_state()
        require(
            assess_goal_state(first).action is GoalAction.ACQUIRE_AGENT_LEASE,
            "fresh task did not request a lease",
        )
        workflow.acquire_agent_lease(
            planned_approach="Implement and push the synthetic behavior.",
            expected_validation="Commit, push, and create the Unity handoff.",
        )
        second = workflow.observe_goal_state()
        require(
            assess_goal_state(second).action is GoalAction.PREPARE_CHECKOUT,
            "leased task did not advance to checkout",
        )
        workflow.prepare_task_checkout()
        checkout = root / "operator" / TASK_ID
        head = commit_change(checkout)

        def handoff():
            return workflow.publish_human_handoff(
                branch=BRANCH,
                head_commit=head,
                implementation_summary="Implemented the synthetic task.",
                completed_checks=["TaskGraph validation passed."],
                human_steps=["Open the project.", "Verify the behavior."],
                expected_result="The behavior works.",
            )

        expect_error(handoff, "has not been pushed")
        git(checkout, "push", "-u", "origin", BRANCH)
        result = handoff()
        require(result["status"] == "human_action_required", "pushed handoff failed")
        require(
            service.observe(TASK_ID)["status"] == "human_action_required",
            "Issue did not become human-owned",
        )


def test_decomposition_uses_exact_canonical_durable_checkout() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-decomposition-checkout-") as temporary:
        root = Path(temporary)
        controller, remote, source_head = create_fixture(root)
        contract, contract_hash, source_tree = contract_facts(controller)
        checkout_root = root / "operator"
        checkout = checkout_root / TASK_ID
        state = initial_state(
            task_id=TASK_ID,
            task_contract_sha256=contract_hash,
            now="2026-09-03T13:00:00Z",
        )
        state = lease(
            state,
            worker=WORKER_A,
            source_head=source_head,
            checkout=checkout,
            now="2026-09-03T13:01:00Z",
        )
        observed = observation(
            controller=controller,
            remote=remote,
            contract=contract,
            contract_hash=contract_hash,
            source_head=source_head,
            source_tree=source_tree,
            state=state,
            worker=WORKER_A,
        )
        observed["task"].update(
            execution_scope="needs_execution_decomposition",
            decomposition_state="concrete",
            derived_state="aggregate",
            dependencies_conformant=False,
        )
        implementation = DurableTaskCheckoutManager(
            source_root=controller,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id=WORKER_A,
            allow_local_remote_for_tests=True,
        )
        blocked = implementation.prepare(observed)
        require(blocked["status"] == "blocked", str(blocked))
        require(not checkout.exists(), "implementation mode created a decomposition checkout")

        decomposition = DurableTaskCheckoutManager(
            source_root=controller,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id=WORKER_A,
            work_type="decomposition",
            allow_local_remote_for_tests=True,
        )
        created = decomposition.prepare(observed)
        require(created["status"] == "ready", str(created))
        require(Path(created["path"]).resolve() == checkout.resolve(), str(created))
        require(git(checkout, "branch", "--show-current") == BRANCH, "wrong branch")
        require(git(checkout, "rev-parse", "HEAD") == source_head, "wrong source commit")
        require(git(checkout, "status", "--porcelain") == "", "checkout is dirty")
        manifest = json.loads(decomposition.manifest_path.read_text(encoding="utf-8"))
        require(manifest.get("checkout_purpose") == "decomposition", str(manifest))


def main() -> int:
    tests = (
        test_checkout_survives_human_and_new_agent,
        test_real_workflow_rejects_unpushed_handoff,
        test_decomposition_uses_exact_canonical_durable_checkout,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent durable checkout smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
