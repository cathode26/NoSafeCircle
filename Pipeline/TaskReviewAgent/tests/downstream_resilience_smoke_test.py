#!/usr/bin/env python3
"""Regression tests for downstream PASS carry-forward and failure resilience."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent import downstream_pipeline as downstream_base  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
    _default_runner,
)
from Pipeline.TaskReviewAgent.downstream_resilience import (  # noqa: E402
    _abort_guarded_run,
    _policy_for_task,
    _receipt_payload,
    _record_guard_rejection,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    IssueWorkflowEvent,
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)


POLICY_HASH = "f8c9e326646e16e2c4bcf5eba4a6505494a5044491bc70127d5b0a1603150a3b"
TASK_ID = "NSC-777"
BRANCH = "nsc-777-contract-migration"
WORKER = "task-review-agent-resilience-test"


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


def git(root: Path, *args: str) -> str:
    return run("git", "-C", str(root), *args, cwd=root)


def commit_all(root: Path, message: str) -> str:
    git(root, "add", ".")
    git(root, "commit", "-m", message)
    return git(root, "rev-parse", "HEAD")


def canonical_contract(*, revision: int, canonical: bool, mutate_gate: bool) -> dict:
    gate = "PlayMode crossing validation"
    if mutate_gate:
        gate = "Changed behavioral obligation"
    scene = (
        "Assets/Scenes/DoorPrototype.unity"
        if canonical
        else "Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity"
    )
    return {
        "schema_version": "2.0",
        "id": TASK_ID,
        "contract_revision": revision,
        "contract_disposition": "active",
        "title": "Synthetic contract migration",
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "depends_on": [],
        "exclusive_resources": [
            "repo-file:Assets/Feature.cs",
            f"unity-scene:{scene}",
        ],
        "acceptance_criteria": [
            {
                "criterion_id": "AC-001",
                "requirement": "Preserve synthetic behavior.",
            }
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "requirement": gate}
        ],
    }


def write_json(path: Path, value: dict) -> bytes:
    data = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


class FakeIssueService:
    def __init__(self, snapshot: object) -> None:
        self.snapshot = snapshot

    def find(self, _task_id: str):
        return self.snapshot


class ReceiptController:
    def __init__(
        self,
        *,
        checkout: Path,
        snapshot: object,
        human_commit: str,
    ) -> None:
        self.checkout = checkout
        self.command_runner = _default_runner
        self.task_id = TASK_ID
        self.workflow = SimpleNamespace(
            issue_workflow=FakeIssueService(snapshot),
        )
        self._human_commit = human_commit

    def _latest_human_validation(self):
        return {
            "result": "pass",
            "tested_commit": self._human_commit,
            "body": (
                "## Human validation result\n\n"
                "Result: PASS\n"
                f"Tested commit: `{self._human_commit}`\n"
            ),
        }


def migration_fixture(
    root: Path,
    *,
    mutate_gate: bool = False,
    mutate_protected: bool = False,
    ledger_hash_mismatch: bool = False,
):
    repo = root / "repo"
    run("git", "init", "-b", "main", str(repo), cwd=root)
    git(repo, "config", "user.name", "Downstream Resilience Test")
    git(repo, "config", "user.email", "resilience@example.invalid")

    old_contract = canonical_contract(
        revision=1,
        canonical=False,
        mutate_gate=False,
    )
    old_bytes = write_json(repo / f"Tasks/{TASK_ID}.yaml", old_contract)
    (repo / "Assets").mkdir(exist_ok=True)
    (repo / "Assets/Feature.cs").write_text("task behavior\n", encoding="utf-8")
    (repo / "Assets/TaskTests.cs").write_text("task tests\n", encoding="utf-8")
    (repo / "Assets/Scenes").mkdir(parents=True, exist_ok=True)
    (repo / "Assets/Scenes/DoorPrototype.unity").write_text(
        "scene identity\n",
        encoding="utf-8",
    )
    human_commit = commit_all(repo, "Human-tested task")

    new_contract = canonical_contract(
        revision=2,
        canonical=True,
        mutate_gate=mutate_gate,
    )
    new_bytes = write_json(repo / f"Tasks/{TASK_ID}.yaml", new_contract)
    if mutate_protected:
        (repo / "Assets/Feature.cs").write_text(
            "changed task behavior\n",
            encoding="utf-8",
        )

    old_hash = hashlib.sha256(old_bytes).hexdigest()
    new_hash = hashlib.sha256(new_bytes).hexdigest()
    ledger_old_hash = "0" * 64 if ledger_hash_mismatch else old_hash
    ledger = {
        "schema_version": "1.0",
        "migration_id": "synthetic-scene-path-migration",
        "canonical_scene_root": "Assets/Scenes/",
        "changed_files": [f"Tasks/{TASK_ID}.yaml"],
        "task_contracts": [
            {
                "task_id": TASK_ID,
                "path": f"Tasks/{TASK_ID}.yaml",
                "old_contract_revision": 1,
                "new_contract_revision": 2,
                "old_sha256": ledger_old_hash,
                "new_sha256": new_hash,
                "replacements": [
                    {
                        "from": "Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity",
                        "to": "Assets/Scenes/DoorPrototype.unity",
                    }
                ],
            }
        ],
    }
    write_json(
        repo
        / "Pipeline/TaskGraph/migrations/canonical-unity-scene-paths-20260828.json",
        ledger,
    )
    operational_head = commit_all(repo, "Apply clerical contract migration")

    event = IssueWorkflowEvent.create(
        task_id=TASK_ID,
        sequence=3,
        previous_event_id="a" * 64,
        event_type=WorkflowEventType.TASK_CONTRACT_MIGRATED,
        from_state=WorkflowState.HUMAN_ACTION_REQUIRED,
        to_state=WorkflowState.AGENT_READY,
        from_phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
        to_phase=WorkflowPhase.DELIVERY_EVIDENCE,
        actor_type=WorkflowActor.AGENT,
        actor_id="synthetic-migration",
        task_contract_sha256=old_hash,
        occurred_at_utc="2026-08-28T12:00:00Z",
        details={
            "old_task_contract_sha256": old_hash,
            "new_task_contract_sha256": new_hash,
            "branch": BRANCH,
            "head_commit": operational_head,
            "checkout_path": str(repo),
            "human_handoff_commit": human_commit,
            "human_result": "pass",
            "migration_id": "synthetic-scene-path-migration",
        },
    )
    snapshot = SimpleNamespace(
        valid=True,
        state=SimpleNamespace(),
        events=[event],
        issue_number=777,
        issue_url="https://github.invalid/issues/777",
    )
    controller = ReceiptController(
        checkout=repo,
        snapshot=snapshot,
        human_commit=human_commit,
    )
    state = {
        "branch": BRANCH,
        "head_commit": operational_head,
        "human_handoff_commit": human_commit,
        "human_result": "pass",
        "task_contract_sha256": new_hash,
    }
    task = {
        "id": TASK_ID,
        "task_id": TASK_ID,
        "contract_path": f"Tasks/{TASK_ID}.yaml",
        "task_contract_sha256": new_hash,
    }
    policy = {
        "task_contract_sha256": new_hash,
        "required_test_platforms": ["PlayMode"],
        "test_filters": {"PlayMode": "Synthetic.PlayMode.Tests"},
        "migration_id": "synthetic-scene-path-migration",
        "protected_paths": [
            "Assets/Feature.cs",
            "Assets/TaskTests.cs",
            "Assets/Scenes/DoorPrototype.unity",
        ],
    }
    return controller, state, task, policy


def test_hash_bound_nsc020_policy_selects_only_playmode() -> None:
    task = {
        "id": "NSC-020",
        "task_contract_sha256": POLICY_HASH,
        "completion_gates": [
            {"gate_id": "VAL-001", "requirement": "Validate crossing behavior."}
        ],
    }
    policy = _policy_for_task(task)
    require(policy is not None, "NSC-020 validation policy was not found")
    require(
        policy["required_test_platforms"] == ["PlayMode"],
        "NSC-020 policy invented another platform",
    )
    require(
        downstream_base._required_platforms(task) == ("PlayMode",),
        "installed required-platform resolver ignored the policy",
    )
    require(
        policy["test_filters"]["PlayMode"]
        == "NoSafeCircle.DoorPrototype.Tests.DoorInteractionPlayModeTests",
        "NSC-020 PlayMode filter is wrong",
    )


def test_verified_clerical_migration_carries_forward_original_pass() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-carry-forward-pass-") as temporary:
        controller, state, task, policy = migration_fixture(Path(temporary))
        payload = _receipt_payload(
            controller,
            state=state,
            task=task,
            policy=policy,
        )
        require(
            payload["receipt_type"]
            == "verified_clerical_task_contract_migration",
            "wrong carry-forward receipt type",
        )
        require(
            payload["human_tested_commit"] != payload["operational_commit"],
            "fixture did not exercise carry-forward across commits",
        )
        require(
            payload["required_test_platforms"] == ["PlayMode"],
            "receipt did not bind authoritative platform",
        )


def test_behavioral_contract_change_rejects_carry_forward() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-carry-forward-gate-") as temporary:
        controller, state, task, policy = migration_fixture(
            Path(temporary),
            mutate_gate=True,
        )
        try:
            _receipt_payload(
                controller,
                state=state,
                task=task,
                policy=policy,
            )
        except DownstreamPipelineError as exc:
            require(
                "changed more than revision and declared paths" in str(exc),
                f"unexpected rejection: {exc}",
            )
        else:
            raise AssertionError("behavioral contract change preserved human PASS")


def test_protected_task_blob_change_rejects_carry_forward() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-carry-forward-blob-") as temporary:
        controller, state, task, policy = migration_fixture(
            Path(temporary),
            mutate_protected=True,
        )
        try:
            _receipt_payload(
                controller,
                state=state,
                task=task,
                policy=policy,
            )
        except DownstreamPipelineError as exc:
            require(
                "changed protected task blobs" in str(exc),
                f"unexpected rejection: {exc}",
            )
        else:
            raise AssertionError("changed protected blob preserved human PASS")


def test_ledger_mismatch_rejects_carry_forward() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-carry-forward-ledger-") as temporary:
        controller, state, task, policy = migration_fixture(
            Path(temporary),
            ledger_hash_mismatch=True,
        )
        try:
            _receipt_payload(
                controller,
                state=state,
                task=task,
                policy=policy,
            )
        except DownstreamPipelineError as exc:
            require(
                "event and committed ledger disagree" in str(exc)
                or "bytes do not match" in str(exc),
                f"unexpected rejection: {exc}",
            )
        else:
            raise AssertionError("mismatched ledger preserved human PASS")


def agent_task() -> dict:
    return {
        "id": "NSC-020",
        "title": "Rejection guard fixture",
        "contract_revision": 2,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Exercise generic downstream rejection handling.",
        "depends_on": [],
        "acceptance_criteria": [],
        "completion_gates": [],
        "exclusive_resources": [],
        "task_contract_sha256": POLICY_HASH,
    }


class RejectionController:
    def __init__(self, service: IssueWorkflowService) -> None:
        self.workflow = SimpleNamespace(
            issue_workflow=service,
            worker_id=WORKER,
        )
        self.task_id = "NSC-020"

    def observe(self) -> dict:
        snapshot = self.workflow.issue_workflow.find(self.task_id)
        assert snapshot is not None and snapshot.state is not None
        return {
            "coordination": {
                "workflow_state": snapshot.state.to_dict(),
                "issue_number": snapshot.issue_number,
            },
            "checkout": {
                "status": "ready",
                "head_commit": "1" * 40,
            },
            "downstream": {
                "next_action": "run_authoritative_unity_tests",
            },
        }


class GuardShell:
    def __init__(self, controller: RejectionController) -> None:
        self._controller = controller


def rejection_fixture() -> tuple[IssueWorkflowService, GuardShell]:
    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda _task_id: agent_task(),
        worker_id=WORKER,
    )
    acquired = service.acquire_agent_lease(
        task=agent_task(),
        source_head="2" * 40,
        branch="nsc-020-rejection-guard",
        checkout_path="C:/Tasks/NSC-020",
        planned_approach="Exercise rejection guard.",
        expected_validation="Lease is released after repeated rejection.",
        now="2026-08-28T13:00:00Z",
    )
    require(acquired["status"] == "acquired", "guard fixture lease failed")
    return service, GuardShell(RejectionController(service))


def test_second_identical_rejection_releases_active_lease() -> None:
    service, guard = rejection_fixture()
    error = DownstreamPipelineError("exact human PASS for checkout HEAD is missing")
    _record_guard_rejection(
        guard,
        action="run_authoritative_unity_test",
        error=error,
    )
    first = service.find("NSC-020")
    assert first is not None and first.state is not None
    require(
        first.state.state is WorkflowState.AGENT_WORKING,
        "first rejection released lease too early",
    )
    _record_guard_rejection(
        guard,
        action="run_authoritative_unity_test",
        error=error,
    )
    final = service.find("NSC-020")
    assert final is not None and final.state is not None
    require(
        final.state.state is WorkflowState.AGENT_READY,
        "second identical rejection did not release lease",
    )
    require(
        final.events[-1].event_type is WorkflowEventType.AGENT_LEASE_RELEASED,
        "rejection guard wrote the wrong final event",
    )
    require(
        final.events[-1].details.get("reason")
        == "repeated_downstream_action_rejection",
        "rejection guard omitted its durable reason",
    )


def test_interrupted_downstream_run_releases_active_lease() -> None:
    service, guard = rejection_fixture()
    _abort_guarded_run(
        guard,
        reason="downstream_run_interrupted",
        error=KeyboardInterrupt(),
    )
    final = service.find("NSC-020")
    assert final is not None and final.state is not None
    require(
        final.state.state is WorkflowState.AGENT_READY,
        "interruption left a stale agent lease",
    )
    require(
        final.events[-1].details.get("reason")
        == "downstream_run_interrupted",
        "interruption release reason is wrong",
    )


def main() -> int:
    tests = (
        test_hash_bound_nsc020_policy_selects_only_playmode,
        test_verified_clerical_migration_carries_forward_original_pass,
        test_behavioral_contract_change_rejects_carry_forward,
        test_protected_task_blob_change_rejects_carry_forward,
        test_ledger_mismatch_rejects_carry_forward,
        test_second_identical_rejection_releases_active_lease,
        test_interrupted_downstream_run_releases_active_lease,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(
        "TaskReviewAgent downstream resilience smoke tests: "
        f"PASS ({len(tests)} tests)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
