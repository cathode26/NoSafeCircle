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
PLAN_ID = "GDP-" + ("a" * 64)


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
        require(created["status"] == "created", f"fresh checkout failed: {created}")

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
        require(recloned["status"] == "created", f"remote branch resume failed: {recloned}")
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
        require(created["status"] == "created", str(created))
        require(Path(created["path"]).resolve() == checkout.resolve(), str(created))
        require(git(checkout, "branch", "--show-current") == BRANCH, "wrong branch")
        require(git(checkout, "rev-parse", "HEAD") == source_head, "wrong source commit")
        require(git(checkout, "status", "--porcelain") == "", "checkout is dirty")
        manifest = json.loads(decomposition.manifest_path.read_text(encoding="utf-8"))
        require(manifest.get("checkout_purpose") == "decomposition", str(manifest))


def advance_main(controller: Path) -> tuple[str, str]:
    (controller / "main-progress.txt").write_text("unrelated\n", encoding="utf-8")
    git(controller, "add", "main-progress.txt")
    git(controller, "commit", "-m", "Advance unrelated mainline")
    git(controller, "push", "origin", "main")
    return git(controller, "rev-parse", "HEAD"), git(controller, "rev-parse", "HEAD^{tree}")


def review_only_decomposition_retry_fixture(root: Path) -> dict:
    controller, remote, initial_main = create_fixture(root)
    contract, contract_hash, initial_tree = contract_facts(controller)
    checkout_root = root / "operator"
    checkout = checkout_root / TASK_ID
    state = initial_state(
        task_id=TASK_ID,
        task_contract_sha256=contract_hash,
        phase=WorkflowPhase.DECOMPOSITION,
        now="2026-09-05T13:00:00Z",
    )
    state = lease(
        state,
        worker=WORKER_A,
        source_head=initial_main,
        checkout=checkout,
        now="2026-09-05T13:01:00Z",
    )
    initial_observation = observation(
        controller=controller,
        remote=remote,
        contract=contract,
        contract_hash=contract_hash,
        source_head=initial_main,
        source_tree=initial_tree,
        state=state,
        worker=WORKER_A,
    )
    initial_observation["task"].update(
        execution_scope="needs_execution_decomposition",
        decomposition_state="concrete",
        derived_state="aggregate",
        dependencies_conformant=False,
    )
    manager = DurableTaskCheckoutManager(
        source_root=controller,
        task_id=TASK_ID,
        checkout_root=checkout_root,
        worker_id=WORKER_A,
        work_type="decomposition",
        allow_local_remote_for_tests=True,
    )
    created = manager.prepare(initial_observation)
    require(created["status"] == "created", f"decomposition checkout create failed: {created}")
    state, _ = transition(
        state,
        event_type=WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED,
        actor_type=WorkflowActor.AGENT,
        actor_id=WORKER_A,
        to_state=WorkflowState.HUMAN_ACTION_REQUIRED,
        to_phase=WorkflowPhase.DECOMPOSITION_APPLY_AUTHORIZATION,
        details={
            "branch": BRANCH,
            "head_commit": initial_main,
            "checkout_path": str(checkout),
            "decomposition_run_id": "fixture-decomposition-run",
            "artifact_root": str(root / "output"),
            "graph_delta_plan_id": PLAN_ID,
        },
        now="2026-09-05T13:02:00Z",
    )
    state, _ = transition(
        state,
        event_type=WorkflowEventType.DECOMPOSITION_APPLICATION_APPROVED,
        actor_type=WorkflowActor.HUMAN,
        actor_id="Vincent",
        to_state=WorkflowState.AGENT_READY,
        to_phase=WorkflowPhase.DECOMPOSITION_APPLY,
        details={"reviewed_plan_id": PLAN_ID},
        now="2026-09-05T13:03:00Z",
    )
    return {
        "root": root,
        "controller": controller,
        "remote": remote,
        "initial_main": initial_main,
        "initial_tree": initial_tree,
        "contract": contract,
        "contract_hash": contract_hash,
        "checkout_root": checkout_root,
        "checkout": checkout,
        "state": state,
        "manager": manager,
    }


def decomposition_retry_observation(
    fixture: dict,
    *,
    source_head: str,
    source_tree: str,
) -> tuple[DurableTaskCheckoutManager, dict]:
    state = lease(
        fixture["state"],
        worker=WORKER_B,
        source_head=source_head,
        checkout=fixture["checkout"],
        now="2026-09-05T13:04:00Z",
    )
    state, _ = transition(
        state,
        event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
        actor_type=WorkflowActor.AGENT,
        actor_id=WORKER_B,
        to_state=WorkflowState.AGENT_READY,
        to_phase=WorkflowPhase.DECOMPOSITION,
        details={
            "reason": "main moved; a fresh D1B.2 proposal is required",
            "work_type": "decomposition",
        },
        now="2026-09-05T13:05:00Z",
    )
    state = lease(
        state,
        worker=WORKER_B,
        source_head=source_head,
        checkout=fixture["checkout"],
        now="2026-09-05T13:06:00Z",
    )
    observed = observation(
        controller=fixture["controller"],
        remote=fixture["remote"],
        contract=fixture["contract"],
        contract_hash=fixture["contract_hash"],
        source_head=source_head,
        source_tree=source_tree,
        state=state,
        worker=WORKER_B,
    )
    observed["task"].update(
        execution_scope="needs_execution_decomposition",
        decomposition_state="concrete",
        derived_state="aggregate",
        dependencies_conformant=False,
    )
    return (
        DurableTaskCheckoutManager(
            source_root=fixture["controller"],
            task_id=TASK_ID,
            checkout_root=fixture["checkout_root"],
            worker_id=WORKER_B,
            work_type="decomposition",
            allow_local_remote_for_tests=True,
        ),
        observed,
    )


def test_review_only_decomposition_retry_fast_forwards_clean_old_main() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-decomposition-main-advance-") as temporary:
        fixture = review_only_decomposition_retry_fixture(Path(temporary))
        current_main, current_tree = advance_main(fixture["controller"])
        manager, observed = decomposition_retry_observation(
            fixture,
            source_head=current_main,
            source_tree=current_tree,
        )
        recovered = manager.prepare(observed)
        require(recovered["status"] == "resumed", f"clean retry was not recovered: {recovered}")
        require(recovered.get("review_only_decomposition_rebased") is True, str(recovered))
        require(recovered.get("prior_checkout_head") == fixture["initial_main"], str(recovered))
        require(recovered.get("recovered_checkout_head") == current_main, str(recovered))
        require(git(fixture["checkout"], "rev-parse", "HEAD") == current_main, "checkout did not fast-forward")
        require(git(fixture["checkout"], "rev-parse", "origin/main") == current_main, "origin/main stayed stale")
        require(git(fixture["checkout"], "status", "--porcelain=v1") == "", "checkout became dirty")
        manifest = json.loads(manager.manifest_path.read_text(encoding="utf-8"))
        require(manifest.get("initial_source_head") == current_main, str(manifest))
        require(manifest.get("initial_source_tree") == current_tree, str(manifest))
        repeated = manager.prepare(observed)
        require(repeated["status"] == "resumed", f"recovery was not idempotent: {repeated}")
        require(git(fixture["checkout"], "rev-parse", "HEAD") == current_main, "retry moved HEAD")


def test_review_only_decomposition_retry_accepts_exact_old_remote_branch() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-decomposition-old-remote-") as temporary:
        fixture = review_only_decomposition_retry_fixture(Path(temporary))
        current_main, current_tree = advance_main(fixture["controller"])
        git(fixture["checkout"], "push", "origin", BRANCH)
        manager, observed = decomposition_retry_observation(
            fixture,
            source_head=current_main,
            source_tree=current_tree,
        )
        recovered = manager.prepare(observed)
        require(recovered["status"] == "resumed", str(recovered))
        require(recovered.get("checkout_fast_forwarded") is True, str(recovered))
        require(git(fixture["checkout"], "rev-parse", "HEAD") == current_main, str(recovered))
        require(
            git(fixture["checkout"], "rev-parse", f"origin/{BRANCH}")
            == fixture["initial_main"],
            "the historical remote task branch was rewritten",
        )


def test_review_only_decomposition_retry_preserves_dirty_checkout() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-decomposition-dirty-") as temporary:
        fixture = review_only_decomposition_retry_fixture(Path(temporary))
        current_main, current_tree = advance_main(fixture["controller"])
        dirty = fixture["checkout"] / "uncommitted.txt"
        dirty.write_text("preserve me\n", encoding="utf-8")
        manager, observed = decomposition_retry_observation(
            fixture,
            source_head=current_main,
            source_tree=current_tree,
        )
        blocked = manager.prepare(observed)
        require(blocked["status"] == "blocked", str(blocked))
        require("checkout working tree is not clean" in blocked.get("reasons", []), str(blocked))
        require(
            "dirty review-only decomposition checkout cannot be advanced or cleaned automatically"
            in blocked.get("reasons", []),
            str(blocked),
        )
        require(dirty.read_text(encoding="utf-8") == "preserve me\n", "dirty evidence changed")
        require(git(fixture["checkout"], "rev-parse", "HEAD") == fixture["initial_main"], "dirty checkout moved")


def test_review_only_decomposition_retry_rejects_diverged_checkout() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-decomposition-diverged-") as temporary:
        fixture = review_only_decomposition_retry_fixture(Path(temporary))
        current_main, current_tree = advance_main(fixture["controller"])
        diverged_head = commit_change(fixture["checkout"])
        manager, observed = decomposition_retry_observation(
            fixture,
            source_head=current_main,
            source_tree=current_tree,
        )
        blocked = manager.prepare(observed)
        require(blocked["status"] == "blocked", str(blocked))
        require(
            any("not an ancestor of current controller main" in reason for reason in blocked.get("reasons", [])),
            str(blocked),
        )
        require(git(fixture["checkout"], "rev-parse", "HEAD") == diverged_head, "diverged checkout moved")


def test_review_only_decomposition_retry_rejects_non_ancestor_main() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-decomposition-non-ancestor-") as temporary:
        fixture = review_only_decomposition_retry_fixture(Path(temporary))
        replacement_main = git(
            fixture["controller"],
            "commit-tree",
            fixture["initial_tree"],
            "-m",
            "Replace main history",
        )
        git(
            fixture["controller"],
            "update-ref",
            "refs/heads/main",
            replacement_main,
            fixture["initial_main"],
        )
        git(fixture["remote"], "fetch", str(fixture["controller"]), replacement_main)
        git(
            fixture["remote"],
            "update-ref",
            "refs/heads/main",
            replacement_main,
            fixture["initial_main"],
        )
        git(
            fixture["controller"],
            "fetch",
            "origin",
            "+refs/heads/main:refs/remotes/origin/main",
        )
        replacement_tree = git(fixture["controller"], "rev-parse", "HEAD^{tree}")
        manager, observed = decomposition_retry_observation(
            fixture,
            source_head=replacement_main,
            source_tree=replacement_tree,
        )
        blocked = manager.prepare(observed)
        require(blocked["status"] == "blocked", str(blocked))
        require(
            any("prior decomposition handoff is not an ancestor" in reason for reason in blocked.get("reasons", [])),
            str(blocked),
        )
        require(git(fixture["checkout"], "rev-parse", "HEAD") == fixture["initial_main"], "non-ancestor checkout moved")


def test_review_only_decomposition_retry_rejects_moved_remote_task_branch() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-decomposition-remote-moved-") as temporary:
        fixture = review_only_decomposition_retry_fixture(Path(temporary))
        current_main, current_tree = advance_main(fixture["controller"])
        moved = git(
            fixture["controller"],
            "commit-tree",
            current_tree,
            "-p",
            current_main,
            "-m",
            "Unexpected remote task branch",
        )
        git(fixture["controller"], "push", "origin", f"{moved}:refs/heads/{BRANCH}")
        manager, observed = decomposition_retry_observation(
            fixture,
            source_head=current_main,
            source_tree=current_tree,
        )
        blocked = manager.prepare(observed)
        require(blocked["status"] == "blocked", str(blocked))
        require(
            any("remote decomposition task branch moved" in reason for reason in blocked.get("reasons", [])),
            str(blocked),
        )
        require(git(fixture["checkout"], "rev-parse", "HEAD") == fixture["initial_main"], "remote conflict moved checkout")


def main() -> int:
    tests = (
        test_checkout_survives_human_and_new_agent,
        test_real_workflow_rejects_unpushed_handoff,
        test_decomposition_uses_exact_canonical_durable_checkout,
        test_review_only_decomposition_retry_fast_forwards_clean_old_main,
        test_review_only_decomposition_retry_accepts_exact_old_remote_branch,
        test_review_only_decomposition_retry_preserves_dirty_checkout,
        test_review_only_decomposition_retry_rejects_diverged_checkout,
        test_review_only_decomposition_retry_rejects_non_ancestor_main,
        test_review_only_decomposition_retry_rejects_moved_remote_task_branch,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent durable checkout smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
