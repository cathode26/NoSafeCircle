#!/usr/bin/env python3
"""Prove unrelated mainline progress does not invalidate a human handoff branch."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    initial_state,
    transition,
)
from Pipeline.TaskReviewAgent.resumable_checkout import (  # noqa: E402
    ResumableTaskCheckoutManager,
)
from Pipeline.TaskReviewAgent.tests.durable_checkout_smoke_test import (  # noqa: E402
    BRANCH,
    TASK_ID,
    WORKER_A,
    WORKER_B,
    commit_change,
    contract_facts,
    git,
    lease,
    observation,
)
from Pipeline.TaskReviewAgent.tests.real_checkout_smoke_test import (  # noqa: E402
    create_fixture,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_resume_ignores_only_stale_origin_main() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-resume-main-progress-") as temporary:
        root = Path(temporary)
        controller, remote, initial_main = create_fixture(root)
        contract, contract_hash, initial_tree = contract_facts(controller)
        checkout_root = root / "operator"
        checkout = checkout_root / TASK_ID
        state = initial_state(
            task_id=TASK_ID,
            task_contract_sha256=contract_hash,
            now="2026-08-27T14:00:00Z",
        )
        state = lease(
            state,
            worker=WORKER_A,
            source_head=initial_main,
            checkout=checkout,
            now="2026-08-27T14:01:00Z",
        )
        first_observation = observation(
            controller=controller,
            remote=remote,
            contract=contract,
            contract_hash=contract_hash,
            source_head=initial_main,
            source_tree=initial_tree,
            state=state,
            worker=WORKER_A,
        )
        first_manager = ResumableTaskCheckoutManager(
            source_root=controller,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id=WORKER_A,
            allow_local_remote_for_tests=True,
        )
        require(first_manager.prepare(first_observation)["status"] == "ready", "create failed")
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
            now="2026-08-27T14:02:00Z",
        )
        state, _ = transition(
            state,
            event_type=WorkflowEventType.HUMAN_VALIDATION_PASSED,
            actor_type=WorkflowActor.HUMAN,
            actor_id="Vincent",
            to_state=WorkflowState.AGENT_READY,
            to_phase=WorkflowPhase.DELIVERY_EVIDENCE,
            details={"tested_commit": handoff_head, "result": "pass"},
            now="2026-08-27T14:03:00Z",
        )

        git(controller, "config", "user.name", "Mainline Progress")
        git(controller, "config", "user.email", "main@example.invalid")
        (controller / "main-progress.txt").write_text("unrelated\n", encoding="utf-8")
        git(controller, "add", "main-progress.txt")
        git(controller, "commit", "-m", "Advance unrelated mainline")
        git(controller, "push", "origin", "main")
        current_main = git(controller, "rev-parse", "HEAD")
        current_tree = git(controller, "rev-parse", "HEAD^{tree}")
        require(current_main != initial_main, "mainline did not advance")

        state = lease(
            state,
            worker=WORKER_B,
            source_head=current_main,
            checkout=checkout,
            now="2026-08-27T14:04:00Z",
        )
        resume_observation = observation(
            controller=controller,
            remote=remote,
            contract=contract,
            contract_hash=contract_hash,
            source_head=current_main,
            source_tree=current_tree,
            state=state,
            worker=WORKER_B,
        )
        manager = ResumableTaskCheckoutManager(
            source_root=controller,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id=WORKER_B,
            allow_local_remote_for_tests=True,
        )
        inspected = manager.inspect(resume_observation)
        require(
            inspected["status"] in ("ready", "unmanaged_exact"),
            f"stale origin/main blocked resume: {inspected}",
        )
        require(
            inspected.get("origin_main_refresh_required") is True,
            "stale origin/main was not reported",
        )
        if inspected["status"] == "unmanaged_exact":
            inspected = manager.prepare(resume_observation)
            require(
                inspected["status"] == "ready",
                f"exact checkout could not be safely adopted: {inspected}",
            )
        require(inspected["head_commit"] == handoff_head, "human-tested commit changed")
        require(git(checkout, "rev-parse", "HEAD") == handoff_head, "checkout was rewritten")
        require(git(controller, "rev-parse", "HEAD") == current_main, "controller changed")


def main() -> int:
    test_resume_ignores_only_stale_origin_main()
    print("PASS test_resume_ignores_only_stale_origin_main")
    print("TaskReviewAgent resumable checkout smoke tests: PASS (1 test)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
