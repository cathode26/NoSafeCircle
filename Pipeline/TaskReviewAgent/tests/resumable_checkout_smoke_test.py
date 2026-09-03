#!/usr/bin/env python3
"""Prove human-tested task checkouts resume after safe local/editor churn."""

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


UNITY_CHURN = (
    "ProjectSettings/EditorBuildSettings.asset",
    "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json",
    "ProjectSettings/ProjectSettings.asset",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def add_tracked_unity_settings(controller: Path) -> tuple[str, str]:
    for relative in UNITY_CHURN:
        path = controller / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"baseline:{relative}\n", encoding="utf-8")
    git(controller, "add", *UNITY_CHURN)
    git(controller, "commit", "-m", "Add tracked Unity settings fixture")
    git(controller, "push", "origin", "main")
    return git(controller, "rev-parse", "HEAD"), git(controller, "rev-parse", "HEAD^{tree}")


def human_handoff_state(
    *,
    state,
    checkout: Path,
    handoff_head: str,
    worker: str,
):
    state, _ = transition(
        state,
        event_type=WorkflowEventType.HUMAN_HANDOFF_CREATED,
        actor_type=WorkflowActor.AGENT,
        actor_id=worker,
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
    return state


def advance_main(controller: Path) -> tuple[str, str]:
    git(controller, "config", "user.name", "Mainline Progress")
    git(controller, "config", "user.email", "main@example.invalid")
    (controller / "main-progress.txt").write_text("unrelated\n", encoding="utf-8")
    git(controller, "add", "main-progress.txt")
    git(controller, "commit", "-m", "Advance unrelated mainline")
    git(controller, "push", "origin", "main")
    return git(controller, "rev-parse", "HEAD"), git(controller, "rev-parse", "HEAD^{tree}")


def test_active_implementation_defers_main_advance_to_candidate_integration() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-active-main-progress-") as temporary:
        root = Path(temporary)
        controller, remote, initial_main = create_fixture(root)
        contract, contract_hash, initial_tree = contract_facts(controller)
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
            source_head=initial_main,
            checkout=checkout,
            now="2026-08-27T13:01:00Z",
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
        manager = ResumableTaskCheckoutManager(
            source_root=controller,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id=WORKER_A,
            allow_local_remote_for_tests=True,
        )
        require(manager.prepare(initial_observation)["status"] == "ready", "create failed")
        current_main, current_tree = advance_main(controller)
        advanced_observation = observation(
            controller=controller,
            remote=remote,
            contract=contract,
            contract_hash=contract_hash,
            source_head=current_main,
            source_tree=current_tree,
            state=state,
            worker=WORKER_A,
        )
        inspected = manager.inspect(advanced_observation)
        require(inspected["status"] == "ready", f"active checkout was stranded: {inspected}")
        require(inspected.get("base_main_advanced") is True, "main advance was not reported")
        require(
            inspected.get("current_main_integration_deferred_to") == "candidate_integration",
            "main integration was deferred to the wrong boundary",
        )
        require(git(checkout, "rev-parse", "HEAD") == initial_main, "stable base was rewritten")


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
        state = human_handoff_state(
            state=state,
            checkout=checkout,
            handoff_head=handoff_head,
            worker=WORKER_A,
        )

        current_main, current_tree = advance_main(controller)
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


def test_resume_recovers_exact_unity_churn_and_refreshes_main() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-resume-unity-churn-") as temporary:
        root = Path(temporary)
        controller, remote, _ = create_fixture(root)
        initial_main, initial_tree = add_tracked_unity_settings(controller)
        contract, contract_hash, _ = contract_facts(controller)
        checkout_root = root / "operator"
        checkout = checkout_root / TASK_ID
        state = initial_state(
            task_id=TASK_ID,
            task_contract_sha256=contract_hash,
            now="2026-08-27T15:00:00Z",
        )
        state = lease(
            state,
            worker=WORKER_A,
            source_head=initial_main,
            checkout=checkout,
            now="2026-08-27T15:01:00Z",
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
        state = human_handoff_state(
            state=state,
            checkout=checkout,
            handoff_head=handoff_head,
            worker=WORKER_A,
        )

        current_main, current_tree = advance_main(controller)
        for relative in UNITY_CHURN:
            (checkout / relative).write_text(f"unity-churn:{relative}\n", encoding="utf-8")
        require(git(checkout, "status", "--porcelain=v1"), "Unity churn fixture stayed clean")

        state = lease(
            state,
            worker=WORKER_B,
            source_head=current_main,
            checkout=checkout,
            now="2026-08-27T15:04:00Z",
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
        before = manager.inspect(resume_observation)
        require(before["status"] == "conflict", f"dirty checkout was not rejected: {before}")
        recovered = manager.prepare(resume_observation)
        require(recovered["status"] == "ready", f"safe churn recovery failed: {recovered}")
        require(
            set(recovered.get("recovered_unity_churn") or []) == set(UNITY_CHURN),
            f"wrong paths were recovered: {recovered}",
        )
        require(recovered.get("origin_main_refreshed") is True, "origin/main was not refreshed")
        require(git(checkout, "status", "--porcelain=v1") == "", "checkout remained dirty")
        require(git(checkout, "rev-parse", "HEAD") == handoff_head, "tested HEAD changed")
        require(git(checkout, "rev-parse", "origin/main") == current_main, "origin/main stayed stale")
        for relative in UNITY_CHURN:
            require(
                (checkout / relative).read_text(encoding="utf-8") == f"baseline:{relative}\n",
                f"{relative} was not restored from the tested commit",
            )


def main() -> int:
    tests = (
        test_active_implementation_defers_main_advance_to_candidate_integration,
        test_resume_ignores_only_stale_origin_main,
        test_resume_recovers_exact_unity_churn_and_refreshes_main,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent resumable checkout smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
