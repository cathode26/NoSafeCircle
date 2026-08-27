#!/usr/bin/env python3
"""Prove that a pushed task branch survives human and later-agent handoffs."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.contracts import TaskReviewContractError  # noqa: E402
from Pipeline.TaskReviewAgent.durable_checkout import (  # noqa: E402
    DurableTaskCheckoutManager,
)
from Pipeline.TaskReviewAgent.goal_loop import (  # noqa: E402
    GoalAction,
    assess_goal_state,
)
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

TASK_ID = "NSC-777"
BRANCH = "nsc-777-durable-checkout-task"


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def git(root: Path, *args: str, check: bool = True) -> str:
    return run("git", "-C", str(root), *args, cwd=root, check=check).stdout.strip()


def git_bytes(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git bytes command failed ({result.returncode}): {args!r}\n"
            f"{result.stderr.decode(errors='replace')}"
        )
    return result.stdout


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


def taskcontrol_source() -> str:
    return """from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
def git(*args: str) -> str:
    return subprocess.check_output(("git", "-C", str(ROOT), *args), text=True).strip()
if sys.argv[1:] == ["validate"]:
    print("taskcontrol validate: PASS")
    raise SystemExit(0)
if len(sys.argv) == 4 and sys.argv[1] == "state" and sys.argv[3] == "--json":
    print(json.dumps({
        "task_id": sys.argv[2],
        "title": "Durable Checkout Task",
        "state": "not_delivered",
        "head_commit": git("rev-parse", "HEAD"),
        "head_tree": git("rev-parse", "HEAD^{tree}"),
        "selected_record_id": None,
        "findings": [],
        "dirty_worktree": False,
    }))
    raise SystemExit(0)
raise SystemExit(2)
"""


def create_fixture(root: Path) -> tuple[Path, Path, dict, str, str, str]:
    remote = root / "remote.git"
    seed = root / "seed"
    controller = root / "controller"
    run("git", "init", "--bare", str(remote), cwd=root)
    run("git", "init", "-b", "main", str(seed), cwd=root)
    git(seed, "config", "user.name", "TaskReviewAgent Smoke")
    git(seed, "config", "user.email", "task-review-agent@example.invalid")
    (seed / "Tasks").mkdir(parents=True)
    (seed / "Pipeline" / "TaskGraph").mkdir(parents=True)
    contract = {
        "schema_version": "2.0",
        "id": TASK_ID,
        "title": "Durable Checkout Task",
        "contract_revision": 1,
        "contract_disposition": "active",
        "kind": "implementation",
        "type": "gameplay_system",
        "execution_scope": "single_agent",
        "execution_reason": "Prove resume across a human handoff.",
        "decomposition_state": "concrete",
        "decomposition_reason": "Already bounded.",
        "depends_on": [],
        "exclusive_resources": [],
        "acceptance_criteria": [],
        "completion_gates": [],
        "downstream_integration_obligations": [],
    }
    contract_path = seed / "Tasks" / f"{TASK_ID}.yaml"
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (seed / "Pipeline" / "TaskGraph" / "taskcontrol.py").write_text(
        taskcontrol_source(),
        encoding="utf-8",
        newline="\n",
    )
    git(seed, "add", ".")
    git(seed, "commit", "-m", "Create durable checkout fixture")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "main")
    run(
        "git",
        "--git-dir",
        str(remote),
        "symbolic-ref",
        "HEAD",
        "refs/heads/main",
        cwd=root,
    )
    run("git", "clone", str(remote), str(controller), cwd=root)
    return (
        controller,
        remote,
        contract,
        git(controller, "rev-parse", "HEAD"),
        git(controller, "rev-parse", "HEAD^{tree}"),
        hashlib.sha256(git_bytes(controller, "show", f"HEAD:Tasks/{TASK_ID}.yaml")).hexdigest(),
    )


def observation(
    *,
    controller: Path,
    remote: Path,
    contract: dict,
    source_head: str,
    source_tree: str,
    contract_hash: str,
    state,
    worker_id: str,
) -> dict:
    task = {
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
    }
    environment = {
        "ready": True,
        "controller_clean": True,
        "taskgraph_valid": True,
        "source_head": source_head,
        "source_tree": source_tree,
        "origin_main": source_head,
        "remote_url": str(remote),
        "repository_root": str(controller),
    }
    coordination = {
        "status": "claimed_by_worker",
        "workflow_status": "agent_working_by_worker",
        "worker_id": worker_id,
        "workflow_state": state.to_dict(),
        "reasons": [],
    }
    return {
        "schema_version": "1.0",
        "observation_authority": "real_read_only",
        "environment": environment,
        "task": task,
        "coordination": coordination,
    }


def acquire(state, worker_id: str, source_head: str, checkout: Path, now: str):
    return transition(
        state,
        event_type=WorkflowEventType.AGENT_LEASE_ACQUIRED,
        actor_type=WorkflowActor.AGENT,
        actor_id=worker_id,
        to_state=WorkflowState.AGENT_WORKING,
        details={
            "worker_id": worker_id,
            "lease_id": ("a" if worker_id == "agent-a" else "b") * 64,
            "source_head": source_head,
            "branch": BRANCH,
            "checkout_path": str(checkout),
        },
        now=now,
    )[0]


def commit_implementation(checkout: Path) -> str:
    git(checkout, "config", "user.name", "Agent A")
    git(checkout, "config", "user.email", "agent-a@example.invalid")
    (checkout / "implementation.txt").write_text("implemented\n", encoding="utf-8")
    git(checkout, "add", "implementation.txt")
    git(checkout, "commit", "-m", "Implement synthetic task")
    return git(checkout, "rev-parse", "HEAD")


def test_checkout_survives_human_and_new_agent() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-durable-checkout-") as temporary:
        root = Path(temporary)
        controller, remote, contract, source_head, source_tree, contract_hash = create_fixture(root)
        checkout_root = root / "operator"
        checkout = checkout_root / TASK_ID
        state = initial_state(
            task_id=TASK_ID,
            task_contract_sha256=contract_hash,
            now="2026-08-27T13:00:00Z",
        )
        state = acquire(state, "agent-a", source_head, checkout, "2026-08-27T13:01:00Z")
        first_observation = observation(
            controller=controller,
            remote=remote,
            contract=contract,
            source_head=source_head,
            source_tree=source_tree,
            contract_hash=contract_hash,
            state=state,
            worker_id="agent-a",
        )
        first_manager = DurableTaskCheckoutManager(
            source_root=controller,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id="agent-a",
            allow_local_remote_for_tests=True,
        )
        created = first_manager.prepare(first_observation)
        require(created["status"] == "created", f"fresh checkout failed: {created}")

        implementation_head = commit_implementation(checkout)
        git(checkout, "push", "-u", "origin", BRANCH)
        state, _ = transition(
            state,
            event_type=WorkflowEventType.HUMAN_HANDOFF_CREATED,
            actor_type=WorkflowActor.AGENT,
            actor_id="agent-a",
            to_state=WorkflowState.HUMAN_ACTION_REQUIRED,
            to_phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
            details={
                "branch": BRANCH,
                "head_commit": implementation_head,
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
            details={"tested_commit": implementation_head, "result": "fail"},
            now="2026-08-27T13:03:00Z",
        )
        state = acquire(state, "agent-b", source_head, checkout, "2026-08-27T13:04:00Z")
        resume_observation = observation(
            controller=controller,
            remote=remote,
            contract=contract,
            source_head=source_head,
            source_tree=source_tree,
            contract_hash=contract_hash,
            state=state,
            worker_id="agent-b",
        )
        second_manager = DurableTaskCheckoutManager(
            source_root=controller,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id="agent-b",
            allow_local_remote_for_tests=True,
        )
        inspected = second_manager.inspect(resume_observation)
        require(inspected["status"] == "ready", f"new worker could not resume: {inspected}")
        require(inspected["head_commit"] == implementation_head, "handoff commit changed")

        shutil.rmtree(checkout)
        require(not checkout.exists(), "temporary checkout removal failed")
        recloned = second_manager.prepare(resume_observation)
        require(recloned["status"] == "created", f"remote branch resume failed: {recloned}")
        require(git(checkout, "rev-parse", "HEAD") == implementation_head, "reclone used wrong commit")
        require(git(checkout, "branch", "--show-current") == BRANCH, "reclone used wrong branch")
        require(
            git(checkout, "status", "--porcelain=v1", "--untracked-files=all") == "",
            "resumed checkout is dirty",
        )
        require(git(controller, "rev-parse", "HEAD") == source_head, "controller HEAD changed")
        require(
            git(controller, "status", "--porcelain=v1", "--untracked-files=all") == "",
            "controller was dirtied",
        )


def test_real_workflow_rejects_unpushed_handoff() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-pushed-handoff-") as temporary:
        root = Path(temporary)
        controller, remote, contract, _, _, contract_hash = create_fixture(root)
        checkout_root = root / "operator"
        backend = MemoryIssueBackend()
        task_record = {**contract, "task_contract_sha256": contract_hash}
        service = IssueWorkflowService(
            backend=backend,
            task_loader=lambda task_id: task_record,
            worker_id="agent-a",
        )
        workflow = RealTaskReviewWorkflow(
            source=controller,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id="agent-a",
            issue_workflow_service=service,
            allow_local_remote_for_tests=True,
        )
        first = workflow.observe_goal_state()
        require(
            assess_goal_state(first).action is GoalAction.ACQUIRE_AGENT_LEASE,
            "fresh managed task did not request an Issue lease",
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
        checkout = checkout_root / TASK_ID
        head = commit_implementation(checkout)

        handoff = lambda: workflow.publish_human_handoff(
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
        require(
            result["status"] == "human_action_required",
            f"pushed handoff was rejected: {result}",
        )
        require(
            service.observe(TASK_ID)["status"] == "human_action_required",
            "Issue did not become human-owned",
        )
        require(str(remote), "remote fixture disappeared")


def main() -> int:
    tests = (
        test_checkout_survives_human_and_new_agent,
        test_real_workflow_rejects_unpushed_handoff,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent durable checkout smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
