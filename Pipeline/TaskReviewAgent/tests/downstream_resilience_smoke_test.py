#!/usr/bin/env python3
"""Regression tests for verified downstream PASS carry-forward and loop recovery."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
    _default_runner,
)
from Pipeline.TaskReviewAgent.downstream_resilience import (  # noqa: E402
    _build_contract_migration_receipt,
    validation_plan_for,
)
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    ResumableDownstreamTaskController,
)
from Pipeline.TaskReviewAgent.goal_loop_guard import GuardedTaskController  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    IssueWorkflowEvent,
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
)
from Pipeline.TaskReviewAgent.tests.goal_loop_guard_smoke_test import (  # noqa: E402
    fixture as guard_fixture,
)


TASK_ID = "NSC-777"
BRANCH = "nsc-777-contract-migration"
CONTRACT_PATH = f"Tasks/{TASK_ID}.yaml"
OLD_SCENE = "Assets/Feature/Scenes/Feature.unity"
NEW_SCENE = "Assets/Scenes/Feature.unity"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout.decode('utf-8', 'replace')}\n"
            f"{result.stderr.decode('utf-8', 'replace')}"
        )
    return result


def git(root: Path, *args: str, check: bool = True) -> str:
    return run("git", "-C", str(root), *args, cwd=root, check=check).stdout.decode().strip()


def write_contract(path: Path, *, revision: int, scene: str, behavior: str) -> tuple[dict[str, Any], str]:
    contract = {
        "schema_version": "2.0",
        "id": TASK_ID,
        "contract_revision": revision,
        "contract_disposition": "active",
        "title": "Synthetic contract migration",
        "reconciliation_key": "synthetic-contract-migration",
        "kind": "implementation",
        "type": "gameplay_system",
        "execution_scope": "single_agent",
        "execution_reason": "Exercise clerical migration validation.",
        "decomposition_state": "concrete",
        "decomposition_reason": "Synthetic focused task.",
        "parent": "NSC-001",
        "depends_on": [],
        "exclusive_resources": [
            "repo-file:Assets/Feature.cs",
            f"unity-scene:{scene}",
        ],
        "acceptance_criteria": [
            {
                "criterion_id": "AC-001",
                "reference": "Synthetic",
                "requirement": behavior,
            }
        ],
        "completion_gates": [
            {
                "gate_id": "VAL-001",
                "reference": "Synthetic",
                "requirement": "Validate the behavior in Play Mode.",
            }
        ],
        "downstream_integration_obligations": [],
        "gdd_evidence": [],
        "basis": "direct_gdd",
        "source_scope": "required",
        "confidence": "high",
        "notes": "Synthetic test contract.",
        "repository_state_at_bootstrap": "missing",
        "repository_evidence_at_bootstrap": [],
        "provenance": {
            "origin": "synthetic",
            "source_schema_version": "1.0",
            "reconciliation_run_id": "synthetic",
            "verification_run_id": "synthetic",
            "bootstrap_status_observation": "open",
            "migration_id": "synthetic",
        },
    }
    data = (json.dumps(contract, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return contract, hashlib.sha256(data).hexdigest()


class FakeService:
    def __init__(self, event: IssueWorkflowEvent) -> None:
        self.snapshot = SimpleNamespace(
            valid=True,
            state=SimpleNamespace(),
            events=[event],
            issue_url="https://example.invalid/issues/777",
        )

    def find(self, task_id: str):
        return self.snapshot if task_id == TASK_ID else None


class FakeWorkflow:
    def __init__(self, service: FakeService) -> None:
        self.issue_workflow = service
        self.worker_id = "worker"


def migration_event(
    *,
    old_hash: str,
    new_hash: str,
    human_commit: str,
    operational_commit: str,
) -> IssueWorkflowEvent:
    return IssueWorkflowEvent.create(
        task_id=TASK_ID,
        sequence=3,
        previous_event_id="1" * 64,
        event_type=WorkflowEventType.TASK_CONTRACT_MIGRATED,
        from_state=WorkflowState.HUMAN_ACTION_REQUIRED,
        to_state=WorkflowState.AGENT_READY,
        from_phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
        to_phase=WorkflowPhase.DELIVERY_EVIDENCE,
        actor_type=WorkflowActor.AGENT,
        actor_id="synthetic-migration",
        task_contract_sha256=old_hash,
        occurred_at_utc="2026-08-28T20:00:00Z",
        details={
            "old_task_contract_sha256": old_hash,
            "new_task_contract_sha256": new_hash,
            "branch": BRANCH,
            "head_commit": operational_commit,
            "checkout_path": "C:/Tasks/NSC-777",
            "human_handoff_commit": human_commit,
            "human_result": "pass",
            "migration_id": "synthetic-clerical-migration",
        },
    )


def create_migration_fixture(
    root: Path,
    *,
    behavior_change: bool = False,
    task_blob_change: bool = False,
) -> tuple[Path, dict[str, Any], dict[str, Any], str, str]:
    remote = root / "remote.git"
    repo = root / "repo"
    run("git", "init", "--bare", str(remote), cwd=root)
    run("git", "init", "-b", "main", str(repo), cwd=root)
    git(repo, "config", "user.name", "Downstream Resilience Test")
    git(repo, "config", "user.email", "resilience@example.invalid")

    old_contract, old_hash = write_contract(
        repo / CONTRACT_PATH,
        revision=1,
        scene=OLD_SCENE,
        behavior="Preserve the synthetic gameplay behavior.",
    )
    (repo / "Assets").mkdir(exist_ok=True)
    (repo / "Assets/Feature.cs").write_text("base\n", encoding="utf-8")
    (repo / "Assets/FeatureTests.cs").write_text("base tests\n", encoding="utf-8")
    (repo / NEW_SCENE).parent.mkdir(parents=True, exist_ok=True)
    (repo / NEW_SCENE).write_text("scene\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Create base")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-u", "origin", "main")
    run("git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main", cwd=root)

    git(repo, "switch", "-c", BRANCH)
    (repo / "Assets/Feature.cs").write_text("task implementation\n", encoding="utf-8")
    (repo / "Assets/FeatureTests.cs").write_text("task tests\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Implement task")
    human_commit = git(repo, "rev-parse", "HEAD")
    git(repo, "push", "-u", "origin", BRANCH)

    git(repo, "switch", "main")
    behavior = (
        "Change the synthetic gameplay behavior."
        if behavior_change
        else "Preserve the synthetic gameplay behavior."
    )
    new_contract, new_hash = write_contract(
        repo / CONTRACT_PATH,
        revision=2,
        scene=NEW_SCENE,
        behavior=behavior,
    )
    ledger = {
        "schema_version": "1.0",
        "migration_id": "synthetic-clerical-migration",
        "task_contracts": [
            {
                "task_id": TASK_ID,
                "path": CONTRACT_PATH,
                "old_contract_revision": 1,
                "new_contract_revision": 2,
                "old_sha256": old_hash,
                "new_sha256": new_hash,
                "replacements": [{"from": OLD_SCENE, "to": NEW_SCENE}],
            }
        ],
    }
    ledger_path = repo / "Pipeline/TaskGraph/migrations/synthetic-clerical-migration.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    runtime = repo / "Pipeline/TaskReviewAgent/runtime.py"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text("# clerical pipeline change\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Apply clerical contract migration")
    main_commit = git(repo, "rev-parse", "HEAD")
    git(repo, "push", "origin", "main")

    git(repo, "switch", BRANCH)
    git(repo, "merge", "--no-ff", "--no-edit", "-m", "Integrate clerical migration", main_commit)
    if task_blob_change:
        (repo / "Assets/Feature.cs").write_text("changed after human test\n", encoding="utf-8")
        git(repo, "commit", "-am", "Mutate task blob")
    operational_commit = git(repo, "rev-parse", "HEAD")
    git(repo, "push", "origin", BRANCH)
    git(repo, "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main")

    event = migration_event(
        old_hash=old_hash,
        new_hash=new_hash,
        human_commit=human_commit,
        operational_commit=operational_commit,
    )
    service = FakeService(event)
    workflow = FakeWorkflow(service)
    controller = object.__new__(ResumableDownstreamTaskController)
    controller.task_id = TASK_ID
    controller.checkout = repo
    controller.command_runner = _default_runner
    controller.workflow = workflow
    controller.state = {}
    controller.last_observation = {
        "task": {
            "task_id": TASK_ID,
            "contract_path": CONTRACT_PATH,
            "task_contract_sha256": new_hash,
        }
    }
    controller._assert_checkout = lambda: None
    controller._persist = lambda: None
    human = {
        "result": "pass",
        "tested_commit": human_commit,
        "body": "Result: PASS",
    }
    controller._latest_human_validation = lambda: human
    state = {
        "state": "agent_working",
        "phase": "delivery_evidence",
        "branch": BRANCH,
        "head_commit": operational_commit,
        "task_contract_sha256": new_hash,
    }
    return repo, state, human, human_commit, operational_commit


def test_verified_contract_migration_carries_original_pass() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-carry-forward-") as temporary:
        repo, state, human, human_commit, operational_commit = create_migration_fixture(Path(temporary))
        controller = SimpleNamespace()
        # Rebuild the controller used by the fixture from closure-visible Git facts.
        # The real patched class is used below to exercise the installed guard.
        event_data = None
        del controller, event_data

        # create_migration_fixture leaves the real controller identities in Git; construct it once.
        old_hash = hashlib.sha256(
            subprocess.check_output(["git", "-C", str(repo), "show", f"{human_commit}:{CONTRACT_PATH}"])
        ).hexdigest()
        new_hash = state["task_contract_sha256"]
        event = migration_event(
            old_hash=old_hash,
            new_hash=new_hash,
            human_commit=human_commit,
            operational_commit=operational_commit,
        )
        service = FakeService(event)
        tested = object.__new__(ResumableDownstreamTaskController)
        tested.task_id = TASK_ID
        tested.checkout = repo
        tested.command_runner = _default_runner
        tested.workflow = FakeWorkflow(service)
        tested.state = {}
        tested.last_observation = {
            "task": {
                "task_id": TASK_ID,
                "contract_path": CONTRACT_PATH,
                "task_contract_sha256": new_hash,
            }
        }
        tested._assert_checkout = lambda: None
        tested._persist = lambda: None
        tested._latest_human_validation = lambda: human

        tested._assert_human_tested_head(state)
        receipt = tested.state.get("human_pass_carry_forward")
        require(isinstance(receipt, dict), "carry-forward receipt was not persisted")
        require(receipt["human_tested_commit"] == human_commit, "human commit changed")
        require(receipt["operational_commit"] == operational_commit, "operational commit changed")
        require(receipt["verified_unchanged_task_paths"], "task paths were not verified")
        require(tested.state["delivery_base_commit"] == receipt["integrated_main_commit"], "base not stabilized")


def test_behavioral_contract_change_is_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-carry-forward-behavior-") as temporary:
        repo, state, human, human_commit, operational_commit = create_migration_fixture(
            Path(temporary), behavior_change=True
        )
        old_hash = hashlib.sha256(
            subprocess.check_output(["git", "-C", str(repo), "show", f"{human_commit}:{CONTRACT_PATH}"])
        ).hexdigest()
        event = migration_event(
            old_hash=old_hash,
            new_hash=state["task_contract_sha256"],
            human_commit=human_commit,
            operational_commit=operational_commit,
        )
        controller = SimpleNamespace(
            task_id=TASK_ID,
            checkout=repo,
            command_runner=_default_runner,
            workflow=FakeWorkflow(FakeService(event)),
            state={},
            last_observation={
                "task": {
                    "task_id": TASK_ID,
                    "contract_path": CONTRACT_PATH,
                    "task_contract_sha256": state["task_contract_sha256"],
                }
            },
        )
        try:
            _build_contract_migration_receipt(controller, state, human, operational_commit)
        except DownstreamPipelineError as exc:
            require("changed behavior" in str(exc), f"unexpected rejection: {exc}")
        else:
            raise AssertionError("behavioral contract change carried the PASS")


def test_task_owned_blob_change_is_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-carry-forward-blob-") as temporary:
        repo, state, human, human_commit, operational_commit = create_migration_fixture(
            Path(temporary), task_blob_change=True
        )
        old_hash = hashlib.sha256(
            subprocess.check_output(["git", "-C", str(repo), "show", f"{human_commit}:{CONTRACT_PATH}"])
        ).hexdigest()
        event = migration_event(
            old_hash=old_hash,
            new_hash=state["task_contract_sha256"],
            human_commit=human_commit,
            operational_commit=operational_commit,
        )
        controller = SimpleNamespace(
            task_id=TASK_ID,
            checkout=repo,
            command_runner=_default_runner,
            workflow=FakeWorkflow(FakeService(event)),
            state={},
            last_observation={
                "task": {
                    "task_id": TASK_ID,
                    "contract_path": CONTRACT_PATH,
                    "task_contract_sha256": state["task_contract_sha256"],
                }
            },
        )
        try:
            _build_contract_migration_receipt(controller, state, human, operational_commit)
        except DownstreamPipelineError as exc:
            require("task-owned blob" in str(exc), f"unexpected rejection: {exc}")
        else:
            raise AssertionError("changed task blob carried the PASS")


def test_nsc020_validation_policy_is_playmode_only() -> None:
    task = {
        "task_id": "NSC-020",
        "task_contract_sha256": "f8c9e326646e16e2c4bcf5eba4a6505494a5044491bc70127d5b0a1603150a3b",
    }
    plan = validation_plan_for(ROOT, task)
    require(plan is not None, "NSC-020 validation policy is missing")
    require(plan["required_test_platforms"] == ["PlayMode"], "NSC-020 platform is not explicit")
    require(
        plan["test_filters"]["PlayMode"]
        == "NoSafeCircle.DoorPrototype.Tests.DoorInteractionPlayModeTests",
        "NSC-020 PlayMode filter is wrong",
    )


def test_second_identical_rejection_releases_lease() -> None:
    service, controller = guard_fixture("progress")
    error = DownstreamPipelineError("deterministic synthetic rejection")
    require(
        controller.record_action_rejection(action="run_authoritative_unity_test", error=error)
        is False,
        "first rejection released the lease",
    )
    require(
        controller.record_action_rejection(action="run_authoritative_unity_test", error=error)
        is True,
        "second rejection did not release the lease",
    )
    snapshot = service.find("NSC-020")
    assert snapshot is not None and snapshot.state is not None
    require(snapshot.state.state is WorkflowState.AGENT_READY, "lease remains active")
    require(
        snapshot.events[-1].details.get("reason") == "repeated_action_rejection",
        "release event has the wrong reason",
    )
    observation = controller.observe()
    require(observation["environment"]["ready"] is False, "run did not become terminal")
    require(
        observation["goal_loop_guard"]["status"] == "repeated_action_rejection",
        "terminal guard status is misleading",
    )


def main() -> int:
    tests = (
        test_verified_contract_migration_carries_original_pass,
        test_behavioral_contract_change_is_rejected,
        test_task_owned_blob_change_is_rejected,
        test_nsc020_validation_policy_is_playmode_only,
        test_second_identical_rejection_releases_lease,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent downstream resilience smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
