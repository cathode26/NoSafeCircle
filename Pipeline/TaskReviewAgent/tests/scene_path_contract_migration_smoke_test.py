#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskGraph.scene_path_policy import (
    inspect_scene_path_policy,
    validate_scene_path_policy,
)
from Pipeline.TaskReviewAgent.downstream_pipeline import _default_runner
from Pipeline.TaskReviewAgent.issue_workflow import (
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    initial_state,
    transition,
    validate_event_chain,
)
from Pipeline.TaskReviewAgent.mainline_reintegration import _object_id_at


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_repository_scene_policy() -> None:
    result = validate_scene_path_policy(ROOT)
    require(result["status"] == "pass", "scene path policy did not pass")


def test_historical_raw_context_is_not_live_scene_authority() -> None:
    stale_reference = (
        "Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity"
    )

    with tempfile.TemporaryDirectory(prefix="nsc-scene-history-") as temporary:
        repo = Path(temporary)

        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=repo,
            check=True,
            stdout=subprocess.PIPE,
        )

        raw_path = (
            repo
            / "Docs"
            / "AI-Pipeline"
            / "Historical-Context-Sessions"
            / "raw"
            / "session.txt"
        )

        raw_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        raw_path.write_text(
            f"Historical record: {stale_reference}\n",
            encoding="utf-8",
        )

        subprocess.run(
            ["git", "add", "."],
            cwd=repo,
            check=True,
        )

        raw_result = inspect_scene_path_policy(repo)

        require(
            raw_result["status"] == "pass",
            "immutable raw historical context was treated as live authority",
        )

        require(
            "Docs/AI-Pipeline/Historical-Context-Sessions/raw/"
            in raw_result["excluded_historical_prefixes"],
            "raw historical context prefix was not reported as excluded",
        )

        live_path = (
            repo
            / "Docs"
            / "AI-Pipeline"
            / "Historical-Context-Sessions"
            / "CURRENT_CONTEXT.md"
        )

        live_path.write_text(
            f"Current operational reference: {stale_reference}\n",
            encoding="utf-8",
        )

        subprocess.run(
            ["git", "add", "."],
            cwd=repo,
            check=True,
        )

        live_result = inspect_scene_path_policy(repo)

        require(
            live_result["status"] == "fail",
            "CURRENT_CONTEXT.md escaped live scene-path validation",
        )

        require(
            any(
                "CURRENT_CONTEXT.md" in finding
                for finding in live_result["findings"]
            ),
            "live-context failure did not identify CURRENT_CONTEXT.md",
        )


def test_missing_scene_resource_is_not_a_changed_blob() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-scene-object-") as temporary:
        repo = Path(temporary)
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "config", "user.name", "Scene Test"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "scene@example.invalid"], cwd=repo, check=True)
        (repo / "file.txt").write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "one"], cwd=repo, check=True, stdout=subprocess.PIPE)
        first = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        (repo / "file.txt").write_text("two\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-am", "two"], cwd=repo, check=True, stdout=subprocess.PIPE)
        second = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        controller = SimpleNamespace(command_runner=_default_runner, checkout=repo)
        path = "Assets/Scenes/Missing.unity"
        require(_object_id_at(controller, first, path) is None, "missing old path resolved")
        require(_object_id_at(controller, second, path) is None, "missing new path resolved")


def test_contract_hash_rollover_is_append_only() -> None:
    old_hash = "1" * 64
    new_hash = "2" * 64
    state = initial_state(task_id="NSC-777", task_contract_sha256=old_hash)
    state, lease = transition(
        state,
        event_type=WorkflowEventType.AGENT_LEASE_ACQUIRED,
        actor_type=WorkflowActor.AGENT,
        actor_id="worker",
        to_state=WorkflowState.AGENT_WORKING,
        details={"worker_id": "worker", "lease_id": "3" * 64},
    )
    state, handoff = transition(
        state,
        event_type=WorkflowEventType.HUMAN_HANDOFF_CREATED,
        actor_type=WorkflowActor.AGENT,
        actor_id="worker",
        to_state=WorkflowState.HUMAN_ACTION_REQUIRED,
        to_phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
        details={
            "branch": "nsc-777-test",
            "head_commit": "4" * 40,
            "checkout_path": "C:/Tasks/NSC-777",
        },
    )
    state, migrated = transition(
        state,
        event_type=WorkflowEventType.TASK_CONTRACT_MIGRATED,
        actor_type=WorkflowActor.AGENT,
        actor_id="scene-path-migration",
        to_state=WorkflowState.AGENT_READY,
        to_phase=WorkflowPhase.DELIVERY_EVIDENCE,
        details={
            "old_task_contract_sha256": old_hash,
            "new_task_contract_sha256": new_hash,
            "branch": "nsc-777-test",
            "head_commit": "5" * 40,
            "checkout_path": "C:/Tasks/NSC-777",
            "human_handoff_commit": "4" * 40,
            "human_result": "pass",
        },
    )
    validated = validate_event_chain(state, [lease, handoff, migrated])
    require(len(validated) == 3, "migration event chain was not retained")
    require(state.task_contract_sha256 == new_hash, "state did not adopt new hash")
    require(state.head_commit == "5" * 40, "operational head did not advance")
    require(state.human_handoff_commit == "4" * 40, "original human identity changed")


def main() -> int:
    tests = (
        test_repository_scene_policy,
        test_historical_raw_context_is_not_live_scene_authority,
        test_missing_scene_resource_is_not_a_changed_blob,
        test_contract_hash_rollover_is_append_only,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Scene path and contract migration smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
