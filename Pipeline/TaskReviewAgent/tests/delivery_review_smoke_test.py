#!/usr/bin/env python3
"""Deterministic tests for hash-bound TaskDelivery approval proposals."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.delivery_review import (  # noqa: E402
    DeliveryReviewError,
    DeliveryReviewProposal,
    create_delivery_review_proposal,
    file_sha256,
    materialize_approved_review,
    materialize_automated_review,
)

TASK_ID = "NSC-777"
COMMIT = "1" * 40


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_error(action, text: str) -> None:
    try:
        action()
    except DeliveryReviewError as exc:
        require(text in str(exc), f"unexpected error: {exc}")
    else:
        raise AssertionError(f"expected DeliveryReviewError containing {text!r}")


def draft() -> dict:
    return {
        "schema_version": "1.0",
        "review_kind": "delivery_spec_review",
        "review_status": "needs_human",
        "task": {
            "id": TASK_ID,
            "title": "Synthetic delivery task",
            "contract_revision": 1,
            "contract_sha256": "a" * 64,
        },
        "validated_commit": COMMIT,
        "validated_tree": "2" * 40,
        "base_commit": "3" * 40,
        "candidate_commit": COMMIT,
        "base_source": "explicit_base_commit",
        "validation_manifests": [],
        "artifacts": [
            {
                "id": "unity_01_results",
                "type": "unity_test_results",
                "source_path": r"C:\Temp\results.xml",
                "name": "Unity-PlayMode-01",
                "sha256": "b" * 64,
                "size_bytes": 100,
                "validation_manifest": r"C:\Temp\validation-manifest.json",
            },
            {
                "id": "human_validation_01",
                "type": "human_validation",
                "source_path": r"C:\Temp\human.txt",
                "name": "HumanValidation-01",
                "sha256": "c" * 64,
                "size_bytes": 50,
                "validation_manifest": None,
            },
        ],
        "committed_diff_paths": [
            "Assets/NoSafeCircle/Synthetic/Feature.cs",
            "Assets/NoSafeCircle/Synthetic/Tests/FeatureTests.cs",
        ],
        "surface_candidates": [
            {
                "path": "Assets/NoSafeCircle/Synthetic/Feature.cs",
                "sources": ["committed_diff"],
                "suggested_role": "implementation",
                "selected": True,
                "role": "",
            },
            {
                "path": "Assets/NoSafeCircle/Synthetic/Tests/FeatureTests.cs",
                "sources": ["committed_diff"],
                "suggested_role": "implementation",
                "selected": True,
                "role": "",
            },
        ],
        "gates": [
            {
                "gate_id": "VAL-001",
                "reference": "synthetic-gate",
                "requirement": "Play Mode behavior passes.",
                "evidence": [],
                "notes": "",
            }
        ],
        "human_approval": {
            "required": True,
            "decision": "",
            "approved_by": "",
            "notes": "",
        },
        "review_instructions": ["Review every truth-bearing field."],
    }


def test_proposal_and_approved_review() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-delivery-review-") as temporary:
        root = Path(temporary)
        draft_path = root / "delivery-draft.json"
        proposal_path = root / "delivery-proposal.json"
        approved_path = root / "delivery-approved.json"
        draft_path.write_text(
            json.dumps(draft(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        proposal = create_delivery_review_proposal(
            draft_path=draft_path,
            output_path=proposal_path,
            task_id=TASK_ID,
            branch="nsc-777-synthetic",
            selected_surfaces=[
                {
                    "path": "Assets/NoSafeCircle/Synthetic/Feature.cs",
                    "role": "runtime behavior owner",
                },
                {
                    "path": "Assets/NoSafeCircle/Synthetic/Tests/FeatureTests.cs",
                    "role": "Play Mode regression coverage",
                },
            ],
            gate_mappings=[
                {
                    "gate_id": "VAL-001",
                    "evidence": ["unity_01_results", "human_validation_01"],
                    "notes": (
                        "The Play Mode XML proves the automated behavior and Vincent's "
                        "validation records the required runtime observation."
                    ),
                }
            ],
            approval_notes="Approve the exact surfaces and evidence mapping shown here.",
            created_by="task-review-agent-smoke",
        )
        require(proposal_path.is_file(), "proposal was not published")
        require(
            proposal["proposal_sha256"] == file_sha256(proposal_path),
            "proposal SHA changed",
        )
        loaded = DeliveryReviewProposal.from_dict(
            json.loads(proposal_path.read_text(encoding="utf-8"))
        )
        require(loaded.validated_commit == COMMIT, "proposal commit changed")
        approved = materialize_approved_review(
            proposal_path=proposal_path,
            expected_proposal_sha256=proposal["proposal_sha256"],
            approved_by="Vincent",
            output_path=approved_path,
        )
        value = json.loads(
            Path(approved["approved_review_path"]).read_text(encoding="utf-8")
        )
        require(value["review_status"] == "approved", "review was not approved")
        require(
            value["human_approval"]["approved_by"] == "Vincent",
            "human identity was not recorded",
        )
        roles = {
            item["path"]: item["role"]
            for item in value["surface_candidates"]
            if item["selected"]
        }
        require(
            roles["Assets/NoSafeCircle/Synthetic/Feature.cs"]
            == "runtime behavior owner",
            "surface role changed",
        )
        require(
            value["gates"][0]["evidence"]
            == ["unity_01_results", "human_validation_01"],
            "gate evidence changed",
        )


def test_invalid_proposals_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-delivery-review-invalid-") as temporary:
        root = Path(temporary)
        draft_path = root / "delivery-draft.json"
        draft_path.write_text(
            json.dumps(draft(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        expect_error(
            lambda: create_delivery_review_proposal(
                draft_path=draft_path,
                output_path=root / "bad-evidence.json",
                task_id=TASK_ID,
                branch="nsc-777-synthetic",
                selected_surfaces=[
                    {
                        "path": "Assets/NoSafeCircle/Synthetic/Feature.cs",
                        "role": "runtime behavior owner",
                    }
                ],
                gate_mappings=[
                    {
                        "gate_id": "VAL-001",
                        "evidence": ["unknown_artifact"],
                        "notes": "This note is meaningful but the artifact is unknown.",
                    }
                ],
                approval_notes="Review this proposal.",
                created_by="agent",
            ),
            "unknown artifact",
        )
        expect_error(
            lambda: create_delivery_review_proposal(
                draft_path=draft_path,
                output_path=root / "missing-gate.json",
                task_id=TASK_ID,
                branch="nsc-777-synthetic",
                selected_surfaces=[
                    {
                        "path": "Assets/NoSafeCircle/Synthetic/Feature.cs",
                        "role": "runtime behavior owner",
                    }
                ],
                gate_mappings=[],
                approval_notes="Review this proposal.",
                created_by="agent",
            ),
            "gate_mappings must be non-empty",
        )


def test_automated_review_records_no_human_approval() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-delivery-review-auto-") as temporary:
        root = Path(temporary)
        draft_path = root / "delivery-draft.json"
        proposal_path = root / "delivery-proposal.json"
        approved_path = root / "delivery-approved.json"
        value = draft()
        value["artifacts"] = [value["artifacts"][0]]
        draft_path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        proposal = create_delivery_review_proposal(
            draft_path=draft_path,
            output_path=proposal_path,
            task_id=TASK_ID,
            branch="nsc-777-synthetic",
            selected_surfaces=[
                {
                    "path": "Assets/NoSafeCircle/Synthetic/Feature.cs",
                    "role": "runtime behavior owner",
                }
            ],
            gate_mappings=[
                {
                    "gate_id": "VAL-001",
                    "evidence": ["unity_01_results"],
                    "notes": "The exact committed Unity test validates this gate.",
                }
            ],
            approval_notes="Machine validation may package this synthetic task.",
            created_by="task-review-agent-smoke",
        )
        result = materialize_automated_review(
            proposal_path=proposal_path,
            expected_proposal_sha256=proposal["proposal_sha256"],
            output_path=approved_path,
            validation_event_id="e" * 64,
            validation_policy_sha256="d" * 64,
        )
        approved = json.loads(
            Path(result["approved_review_path"]).read_text(encoding="utf-8")
        )
        require(
            approved["human_approval"]
            == {
                "required": False,
                "decision": "not_required",
                "approved_by": "",
                "notes": (
                    f"Automated validation event {'e' * 64}; committed "
                    f"validation policy {'d' * 64}."
                ),
            },
            "automated review fabricated or omitted approval authority",
        )


def main() -> int:
    tests = (
        test_proposal_and_approved_review,
        test_invalid_proposals_fail_closed,
        test_automated_review_records_no_human_approval,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent delivery review tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
