#!/usr/bin/env python3
"""Prove a clerical task-contract migration safely fast-forwards a durable checkout."""

from __future__ import annotations

import hashlib
import json
import subprocess
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


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout.strip()


def human_pass_state(state, checkout: Path, handoff_head: str):
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
        now="2026-08-28T12:02:00Z",
    )
    state, _ = transition(
        state,
        event_type=WorkflowEventType.HUMAN_VALIDATION_PASSED,
        actor_type=WorkflowActor.HUMAN,
        actor_id="Vincent",
        to_state=WorkflowState.AGENT_READY,
        to_phase=WorkflowPhase.DELIVERY_EVIDENCE,
        details={"tested_commit": handoff_head, "result": "pass"},
        now="2026-08-28T12:03:00Z",
    )
    return state


def rewrite_contract_on_main(controller: Path) -> tuple[dict, str, str, str]:
    contract_path = controller / "Tasks" / f"{TASK_ID}.yaml"
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    contract["contract_revision"] += 1
    contract["notes"] = "Canonical scene path metadata correction."
    data = (json.dumps(contract, indent=2, sort_keys=True) + "\n").encode("utf-8")
    contract_path.write_bytes(data)
    git(controller, "add", str(contract_path.relative_to(controller)))
    git(controller, "commit", "-m", "Migrate synthetic task contract")
    git(controller, "push", "origin", "main")
    return (
        contract,
        hashlib.sha256(data).hexdigest(),
        git(controller, "rev-parse", "HEAD"),
        git(controller, "rev-parse", "HEAD^{tree}"),
    )


def integrate_main_in_remote_branch(root: Path, remote: Path) -> str:
    integrator = root / "integrator"
    run("git", "clone", str(remote), str(integrator), cwd=root)
    git(integrator, "config", "user.name", "Contract Migration")
    git(integrator, "config", "user.email", "migration@example.invalid")
    git(integrator, "switch", "-c", BRANCH, f"origin/{BRANCH}")
    git(integrator, "merge", "--no-ff", "--no-edit", "-m", "Integrate migrated contract", "origin/main")
    integrated = git(integrator, "rev-parse", "HEAD")
    git(integrator, "push", "origin", BRANCH)
    return integrated


def test_contract_migration_fast_forwards_and_rekeys_manifest() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-contract-migration-resume-") as temporary:
        root = Path(temporary)
        controller, remote, source_head = create_fixture(root)
        contract, old_hash, source_tree = contract_facts(controller)
        checkout_root = root / "operator"
        checkout = checkout_root / TASK_ID

        state = initial_state(
            task_id=TASK_ID,
            task_contract_sha256=old_hash,
            now="2026-08-28T12:00:00Z",
        )
        state = lease(
            state,
            worker=WORKER_A,
            source_head=source_head,
            checkout=checkout,
            now="2026-08-28T12:01:00Z",
        )
        initial_observation = observation(
            controller=controller,
            remote=remote,
            contract=contract,
            contract_hash=old_hash,
            source_head=source_head,
            source_tree=source_tree,
            state=state,
            worker=WORKER_A,
        )
        manager_a = ResumableTaskCheckoutManager(
            source_root=controller,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id=WORKER_A,
            allow_local_remote_for_tests=True,
        )
        require(manager_a.prepare(initial_observation)["status"] == "ready", "initial checkout failed")
        human_head = commit_change(checkout)
        git(checkout, "push", "-u", "origin", BRANCH)
        state = human_pass_state(state, checkout, human_head)

        new_contract, new_hash, new_main, new_tree = rewrite_contract_on_main(controller)
        integrated_head = integrate_main_in_remote_branch(root, remote)
        require(integrated_head != human_head, "integration did not advance task branch")

        state, _ = transition(
            state,
            event_type=WorkflowEventType.TASK_CONTRACT_MIGRATED,
            actor_type=WorkflowActor.AGENT,
            actor_id="canonical-scene-path-migration",
            to_state=WorkflowState.AGENT_READY,
            to_phase=WorkflowPhase.DELIVERY_EVIDENCE,
            details={
                "old_task_contract_sha256": old_hash,
                "new_task_contract_sha256": new_hash,
                "branch": BRANCH,
                "head_commit": integrated_head,
                "checkout_path": str(checkout),
                "human_handoff_commit": human_head,
                "human_result": "pass",
            },
            now="2026-08-28T12:04:00Z",
        )
        state = lease(
            state,
            worker=WORKER_B,
            source_head=new_main,
            checkout=checkout,
            now="2026-08-28T12:05:00Z",
        )
        migrated_observation = observation(
            controller=controller,
            remote=remote,
            contract=new_contract,
            contract_hash=new_hash,
            source_head=new_main,
            source_tree=new_tree,
            state=state,
            worker=WORKER_B,
        )
        manager_b = ResumableTaskCheckoutManager(
            source_root=controller,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id=WORKER_B,
            allow_local_remote_for_tests=True,
        )
        before = manager_b.inspect(migrated_observation)
        require(before["status"] == "conflict", f"stale checkout was not detected: {before}")

        recovered = manager_b.prepare(migrated_observation)
        require(recovered["status"] == "ready", f"contract migration recovery failed: {recovered}")
        require(recovered.get("contract_migration_fast_forwarded") is True, "checkout was not fast-forwarded")
        require(recovered.get("durable_manifest_migrated") is True, "manifest was not migrated")
        require(git(checkout, "rev-parse", "HEAD") == integrated_head, "checkout head is wrong")
        require(git(checkout, "status", "--porcelain=v1") == "", "checkout is dirty")
        require(
            recovered.get("task_contract_sha256") == new_hash,
            "checkout contract identity did not migrate",
        )
        manifest = json.loads(manager_b.manifest_path.read_text(encoding="utf-8"))
        require(manifest["task_contract_sha256"] == new_hash, "manifest retained old contract hash")
        require(manifest["task_contract_revision"] == new_contract["contract_revision"], "manifest revision is stale")


def main() -> int:
    test_contract_migration_fast_forwards_and_rekeys_manifest()
    print("PASS test_contract_migration_fast_forwards_and_rekeys_manifest")
    print("TaskReviewAgent contract-migration checkout smoke tests: PASS (1 test)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
