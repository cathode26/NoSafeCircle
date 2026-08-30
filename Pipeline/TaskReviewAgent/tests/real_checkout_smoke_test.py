#!/usr/bin/env python3
"""Deterministic standalone-clone tests for the real TaskReviewAgent checkout boundary."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.coordination import StaticCoordinationObserver  # noqa: E402
from Pipeline.TaskReviewAgent.goal_loop import GoalAction, assess_goal_state  # noqa: E402
from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow  # noqa: E402


TASK_ID = "NSC-777"
WORKER_ID = "task-review-agent-smoke"


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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


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
    print("Task contract schema: 2.0")
    raise SystemExit(0)

if len(sys.argv) == 4 and sys.argv[1] == "state" and sys.argv[3] == "--json":
    task_id = sys.argv[2]
    print(json.dumps({
        "task_id": task_id,
        "title": "Synthetic Checkout Task",
        "state": "not_delivered",
        "head_commit": git("rev-parse", "HEAD"),
        "head_tree": git("rev-parse", "HEAD^{tree}"),
        "selected_record_id": None,
        "findings": [],
        "dirty_worktree": False,
    }, sort_keys=True))
    raise SystemExit(0)

raise SystemExit(2)
"""


def create_fixture(root: Path) -> tuple[Path, Path, str]:
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
        "title": "Synthetic Checkout Task",
        "contract_revision": 1,
        "contract_disposition": "active",
        "kind": "implementation",
        "type": "gameplay_system",
        "execution_scope": "single_agent",
        "execution_reason": "Synthetic checkout boundary test.",
        "decomposition_state": "concrete",
        "decomposition_reason": "Already bounded.",
        "depends_on": [],
        "exclusive_resources": [],
        "acceptance_criteria": [],
        "completion_gates": [],
        "downstream_integration_obligations": [],
    }
    (seed / "Tasks" / f"{TASK_ID}.yaml").write_text(
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
    git(seed, "commit", "-m", "Create synthetic checkout fixture")
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
    git(controller, "config", "user.name", "TaskReviewAgent Smoke")
    git(controller, "config", "user.email", "task-review-agent@example.invalid")
    return controller, remote, git(controller, "rev-parse", "HEAD")


def workflow(
    *,
    controller: Path,
    checkout_root: Path,
    coordination_status: str,
) -> RealTaskReviewWorkflow:
    return RealTaskReviewWorkflow(
        source=controller,
        task_id=TASK_ID,
        checkout_root=checkout_root,
        worker_id=WORKER_ID,
        coordination_observer=StaticCoordinationObserver(
            worker_id=WORKER_ID,
            status=coordination_status,
        ),
        allow_local_remote_for_tests=True,
    )


def test_real_checkout_create_resume_and_conflict() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-task-review-checkout-") as temporary:
        root = Path(temporary)
        controller, _, source_head = create_fixture(root)
        checkout_root = root / "operator"
        subject = workflow(
            controller=controller,
            checkout_root=checkout_root,
            coordination_status="claimed_by_worker",
        )

        before_tree = git(controller, "rev-parse", "HEAD^{tree}")
        before_status = git(
            controller,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )

        first = subject.observe_goal_state()
        require(
            assess_goal_state(first).action is GoalAction.PREPARE_CHECKOUT,
            "eligible claimed task did not advance to checkout preparation",
        )
        require(first["checkout"]["status"] == "missing", "missing checkout was not observed")

        created = subject.prepare_task_checkout()
        require(created["status"] == "created", f"checkout was not created: {created}")
        second = subject.observe_goal_state()
        require(second["checkout"]["status"] == "ready", "created checkout was not ready")
        require(
            assess_goal_state(second).action is GoalAction.VALIDATE_SCOPE,
            "ready checkout did not advance to path planning",
        )

        checkout = checkout_root / TASK_ID
        require(checkout.is_dir(), "canonical task directory was not created")
        require(checkout.parent == checkout_root, "checkout is not the exact canonical child path")
        require(git(checkout, "rev-parse", "HEAD") == source_head, "checkout HEAD changed")
        require(
            git(checkout, "branch", "--show-current")
            == "nsc-777-synthetic-checkout-task",
            "checkout branch is not deterministic",
        )
        require(
            git(checkout, "status", "--porcelain=v1", "--untracked-files=all") == "",
            "created checkout is dirty",
        )
        manifest = checkout_root / ".task-review-agent" / f"{TASK_ID}.json"
        require(manifest.is_file(), "external checkout identity manifest is missing")
        require(
            not (checkout / ".task-review-agent").exists(),
            "manifest dirtied task checkout",
        )

        resumed = subject.prepare_task_checkout()
        require(resumed["status"] == "resumed", "exact managed checkout was not resumed")

        (checkout / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
        conflict = subject.observe_goal_state()
        require(conflict["checkout"]["status"] == "conflict", "dirty checkout was accepted")
        require(
            assess_goal_state(conflict).action is GoalAction.NEEDS_HUMAN,
            "checkout conflict did not stop at human reconciliation",
        )

        require(git(controller, "rev-parse", "HEAD") == source_head, "controller HEAD changed")
        require(
            git(controller, "rev-parse", "HEAD^{tree}") == before_tree,
            "controller tree changed",
        )
        require(
            git(controller, "status", "--porcelain=v1", "--untracked-files=all")
            == before_status,
            "checkout preparation dirtied the controller",
        )


def test_real_checkout_requires_github_claim() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-task-review-claim-") as temporary:
        root = Path(temporary)
        controller, _, _ = create_fixture(root)
        checkout_root = root / "operator"
        subject = workflow(
            controller=controller,
            checkout_root=checkout_root,
            coordination_status="available_unassigned",
        )
        observation = subject.observe_goal_state()
        assessment = assess_goal_state(observation)
        require(assessment.action is GoalAction.CLAIM_TASK, "unclaimed task bypassed claim gate")
        result = subject.prepare_task_checkout()
        require(result["status"] == "blocked", "checkout manager ignored missing claim")
        require(not (checkout_root / TASK_ID).exists(), "unclaimed task checkout was created")


def main() -> int:
    tests = (
        test_real_checkout_create_resume_and_conflict,
        test_real_checkout_requires_github_claim,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent real checkout smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
