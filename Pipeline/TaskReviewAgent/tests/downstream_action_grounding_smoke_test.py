#!/usr/bin/env python3
"""Regression tests for lease-first routing and exact delivery proposal IDs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.schema_validation import (  # noqa: E402
    SchemaValidationError,
    validate_instance,
    validate_schema,
)
from Pipeline.TaskReviewAgent import codex_supervisor  # noqa: E402
from Pipeline.TaskReviewAgent import downstream_action_grounding as grounding  # noqa: E402
from Pipeline.TaskReviewAgent import downstream_determinism  # noqa: E402
from Pipeline.TaskReviewAgent import openai_downstream  # noqa: E402
from Pipeline.TaskReviewAgent import progress  # noqa: E402


grounding.install_downstream_action_grounding()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def delivery_facts() -> dict[str, Any]:
    return {
        "task_id": "NSC-020",
        "draft_path": "C:/private/output/delivery-review-draft.json",
        "draft_sha256": "d" * 64,
        "validated_commit": "c" * 40,
        "surface_candidates": [
            {
                "path": "Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs",
                "sources": ["committed_diff", "task.exclusive_resources"],
                "suggested_role": "implementation",
                "selected": True,
                "role": "",
            },
            {
                "path": "Assets/NoSafeCircle/DoorPrototype/Tests/DoorInteractionPlayModeTests.cs",
                "sources": ["committed_diff"],
                "suggested_role": "implementation",
                "selected": True,
                "role": "",
            },
        ],
        "artifacts": [
            {
                "id": "unity_01_results",
                "type": "unity_test_results",
                "source_path": "C:/private/output/results.xml",
                "name": "Unity-PlayMode-01",
                "sha256": "1" * 64,
                "size_bytes": 123,
                "validation_manifest": "C:/private/output/validation-manifest.json",
            },
            {
                "id": "unity_01_log",
                "type": "unity_log",
                "source_path": "C:/private/output/Editor.log",
                "name": "Unity-PlayMode-01",
                "sha256": "2" * 64,
                "size_bytes": 456,
                "validation_manifest": "C:/private/output/validation-manifest.json",
            },
            {
                "id": "human_validation_01",
                "type": "human_validation",
                "source_path": "C:/private/output/human-validation.txt",
                "name": "HumanValidation-01",
                "sha256": "3" * 64,
                "size_bytes": 789,
                "validation_manifest": None,
            },
        ],
        "gates": [
            {
                "gate_id": "VAL-001",
                "reference": "Door crossing validation",
                "requirement": (
                    "Crossing is detected only after the open door is actually crossed."
                ),
                "evidence": [],
                "notes": "",
            }
        ],
        "proposal_path": None,
        "proposal_sha256": None,
    }


def proposal_observation(*, state: str = "agent_working") -> dict[str, Any]:
    return {
        "coordination": {
            "workflow_state": {
                "state": state,
                "phase": "delivery_evidence",
                "state_version": 24,
            }
        },
        "checkout": {"status": "ready"},
        "downstream": {
            "next_action": (
                "acquire_agent_lease"
                if state == "agent_ready"
                else "create_delivery_review_proposal"
            ),
        },
    }


def proposal_history() -> list[dict[str, Any]]:
    return [
        {
            "turn": 7,
            "action": "delivery_review_facts",
            "rationale": "Read the host-verified proposal inventory.",
            "result": delivery_facts(),
        }
    ]


def test_agent_ready_acquires_lease_before_checkout_repair() -> None:
    observation = proposal_observation(state="agent_ready")
    observation["checkout"]["origin_main_refresh_required"] = True
    observation["downstream"]["mainline_reintegration"] = {
        "status": "main_commit_unavailable"
    }
    actions = {
        "acquire_agent_lease": "acquire",
        "prepare_task_checkout": "prepare",
    }
    actual = downstream_determinism.allowed_actions_for(
        observation,
        [],
        actions,
    )
    require(
        actual == ("acquire_agent_lease",),
        "agent-ready routing attempted checkout mutation before acquiring a lease",
    )


def test_proposal_without_facts_reads_facts_first() -> None:
    actions = {
        "delivery_review_facts": "facts",
        "create_delivery_review_proposal": "proposal",
    }
    actual = downstream_determinism.allowed_actions_for(
        proposal_observation(),
        [],
        actions,
    )
    require(
        actual == ("delivery_review_facts",),
        "proposal routing skipped the exact host facts",
    )


def test_bounded_history_preserves_exact_safe_proposal_ids() -> None:
    compact = downstream_determinism.bounded_history(proposal_history())
    result = compact[0]["result"]
    require(
        result["artifact_ids"]
        == ["unity_01_results", "unity_01_log", "human_validation_01"],
        "history compaction removed the exact artifact IDs needed by the proposal",
    )
    require(result["gate_ids"] == ["VAL-001"], "gate IDs were removed")
    require(
        result["surface_paths"]
        == [
            "Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs",
            "Assets/NoSafeCircle/DoorPrototype/Tests/DoorInteractionPlayModeTests.cs",
        ],
        "surface paths were removed",
    )
    rendered = json.dumps(compact)
    require("C:/private/output" not in rendered, "external artifact paths leaked")
    require("validation-manifest.json" not in rendered, "manifest path leaked")


def test_prompt_and_schema_ground_exact_artifact_ids() -> None:
    prompt = openai_downstream.render_supervisor_prompt(
        task_id="NSC-020",
        goal_and_rules="Create only a truthful proposal.",
        observation=proposal_observation(),
        history=proposal_history(),
        actions={
            "delivery_review_facts": "Read facts.",
            "create_delivery_review_proposal": "Create proposal.",
        },
    )
    require(
        "HOST_VERIFIED_DELIVERY_REVIEW_FACTS=" in prompt,
        "proposal prompt omitted the host-verified inventory",
    )
    for value in (
        "unity_01_results",
        "unity_01_log",
        "human_validation_01",
        "VAL-001",
        "DoorInteractable.cs",
    ):
        require(value in prompt, f"proposal prompt omitted {value}")
    require(
        "A validation-manifest path, SHA, test filter, artifact name, or prose description is not an artifact ID"
        in prompt,
        "proposal prompt did not explain the artifact-ID boundary",
    )
    require("C:/private/output" not in prompt, "external artifact path leaked")

    schema = codex_supervisor.decision_schema(
        ("create_delivery_review_proposal",)
    )
    validate_schema(schema)
    arguments = schema["properties"]["arguments"]["properties"]
    path_enum = arguments["selected_surfaces"]["items"]["properties"][
        "path"
    ]["enum"]
    artifact_enum = arguments["gate_mappings"]["items"]["properties"][
        "evidence"
    ]["items"]["enum"]
    gate_enum = arguments["gate_mappings"]["items"]["properties"][
        "gate_id"
    ]["enum"]
    require(len(path_enum) == 2, "surface path enum is incomplete")
    require(
        artifact_enum
        == ["unity_01_results", "unity_01_log", "human_validation_01"],
        "proposal evidence schema is not constrained to exact artifact IDs",
    )
    require(gate_enum == ["VAL-001"], "proposal gate schema is not exact")

    decision = {
        "schema_version": "1.0",
        "task_id": "NSC-020",
        "action": "create_delivery_review_proposal",
        "arguments": {
            "selected_surfaces": [
                {
                    "path": path_enum[0],
                    "role": "Owns the doorway-crossing state implementation.",
                }
            ],
            "gate_mappings": [
                {
                    "gate_id": "VAL-001",
                    "evidence": ["validation-manifest.json"],
                    "notes": "The exact PlayMode test demonstrates the gate.",
                }
            ],
            "approval_notes": "Proposal only; Vincent still approves it.",
        },
        "rationale": "Map the exact host inventory.",
    }
    try:
        validate_instance(decision, schema)
    except SchemaValidationError:
        pass
    else:
        raise AssertionError("an invented validation-manifest artifact ID passed")

    decision["arguments"]["gate_mappings"][0]["evidence"] = [
        "unity_01_results"
    ]
    validate_instance(decision, schema)


def test_duplicate_artifact_identity_fails_closed() -> None:
    facts = delivery_facts()
    facts["artifacts"][1]["id"] = "unity_01_results"
    try:
        grounding.proposal_facts_from_result(facts)
    except codex_supervisor.CodexSupervisorError as exc:
        require("not unique" in str(exc), "wrong duplicate-artifact failure")
    else:
        raise AssertionError("duplicate artifact IDs entered the proposal context")


def test_operator_summary_exposes_exact_ids_not_external_paths() -> None:
    summary = progress.summarize_result(delivery_facts())
    require(summary["artifacts_count"] == 3, "artifact count missing")
    require(summary["artifact_ids"][0] == "unity_01_results", "IDs missing")
    require(summary["gate_ids"] == ["VAL-001"], "gate IDs missing")
    rendered = json.dumps(summary)
    require("C:/private/output" not in rendered, "operator summary leaked paths")


def main() -> int:
    tests = (
        test_agent_ready_acquires_lease_before_checkout_repair,
        test_proposal_without_facts_reads_facts_first,
        test_bounded_history_preserves_exact_safe_proposal_ids,
        test_prompt_and_schema_ground_exact_artifact_ids,
        test_duplicate_artifact_identity_fails_closed,
        test_operator_summary_exposes_exact_ids_not_external_paths,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(
        "TaskReviewAgent downstream action grounding tests: "
        f"PASS ({len(tests)} tests)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
