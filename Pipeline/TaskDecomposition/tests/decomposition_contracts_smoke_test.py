from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[2]
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

from AgentRuntime.schema_validation import validate_instance, validate_schema
from TaskDecomposition.contracts import DecompositionContractError, DecompositionResult
from TaskDecomposition.policy import (
    DecompositionPolicyError,
    semantic_json_sha256,
    validate_decomposition_result,
)
from TaskDecomposition.schemas import DECOMPOSITION_RESULT_SCHEMA


def parent_task() -> dict:
    return {
        "schema_version": "2.0",
        "id": "NSC-042",
        "contract_revision": 3,
        "contract_disposition": "active",
        "title": "Synthetic parent",
        "reconciliation_key": "synthetic-parent",
        "kind": "implementation",
        "type": "synthetic",
        "execution_scope": "needs_execution_decomposition",
        "execution_reason": "Too broad.",
        "decomposition_state": "concrete",
        "decomposition_reason": "Design is approved.",
        "parent": "NSC-001",
        "depends_on": [],
        "exclusive_resources": [],
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "reference": "Canon", "requirement": "Parent acceptance."}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "reference": "Policy", "requirement": "Parent validation."}
        ],
        "downstream_integration_obligations": [
            {"obligation_id": "INT-001", "reference": "Integration", "requirement": "Parent integration."}
        ],
        "gdd_evidence": [],
        "basis": "direct_gdd",
        "source_scope": "required",
        "confidence": "high",
        "notes": "",
        "repository_state_at_bootstrap": "missing",
        "repository_evidence_at_bootstrap": [],
        "provenance": {"origin": "synthetic"},
    }


def identity(parent: dict) -> dict:
    return {
        "task_id": parent["id"],
        "contract_revision": parent["contract_revision"],
        "contract_sha256": semantic_json_sha256(parent),
    }


def child(key: str) -> dict:
    return {
        "local_key": key,
        "title": f"Child {key}",
        "kind": "implementation",
        "type": "synthetic_child",
        "execution_scope": "single_agent",
        "execution_reason": "One bounded responsibility.",
        "decomposition_state": "concrete",
        "decomposition_reason": "Approved behavior is fully specified.",
        "existing_task_dependencies": [],
        "local_dependencies": [],
        "exclusive_resources": [],
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "reference": "Parent AC-001", "requirement": f"{key} acceptance."}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "reference": "Parent VAL-001", "requirement": f"Validate {key}."}
        ],
        "downstream_integration_obligations": [],
        "gdd_evidence": [
            {"reference": "Synthetic canon", "requirement": "Approved responsibility only."}
        ],
        "basis": "direct_gdd",
        "source_scope": "required",
        "confidence": "high",
        "notes": "",
    }


def base(parent: dict, decision: str, gap: str) -> dict:
    return {
        "schema_version": "1.1",
        "parent_task": identity(parent),
        "decision": decision,
        "gap_type": gap,
        "reason": "Deterministic synthetic reason.",
        "children": [],
        "parent_requirement_coverage": [],
        "inbound_dependency_rewrites": [],
        "unsupported_assumptions": [],
        "unresolved_questions": [],
        "artifact_proposal": None,
    }


def retained_result(parent: dict) -> dict:
    value = base(parent, "already_concrete", "none")
    value["parent_requirement_coverage"] = [
        {
            "parent_entry_type": kind,
            "parent_entry_id": entry_id,
            "disposition": "retained_by_parent",
            "child_targets": [],
            "reason": "The concrete parent retains this obligation.",
            "integration_rationale": "",
        }
        for kind, entry_id in (
            ("acceptance_criteria", "AC-001"),
            ("completion_gates", "VAL-001"),
            ("downstream_integration_obligations", "INT-001"),
        )
    ]
    return value


def decomposed_result(parent: dict) -> dict:
    value = base(parent, "decomposed", "execution")
    first = child("runtime-core")
    second = child("runtime-integration")
    second["local_dependencies"] = ["runtime-core"]
    second["downstream_integration_obligations"] = [
        {"obligation_id": "INT-001", "reference": "Parent INT-001", "requirement": "Integrate children."}
    ]
    value["children"] = [first, second]
    value["parent_requirement_coverage"] = [
        {
            "parent_entry_type": "acceptance_criteria",
            "parent_entry_id": "AC-001",
            "disposition": "shared_integration",
            "child_targets": [
                {"local_key": "runtime-core", "child_entry_type": "acceptance_criteria", "child_entry_id": "AC-001"},
                {"local_key": "runtime-integration", "child_entry_type": "acceptance_criteria", "child_entry_id": "AC-001"},
            ],
            "reason": "Both bounded behaviors implement the parent criterion.",
            "integration_rationale": "Both exact targets jointly satisfy the parent behavior.",
        },
        {
            "parent_entry_type": "completion_gates",
            "parent_entry_id": "VAL-001",
            "disposition": "shared_integration",
            "child_targets": [
                {"local_key": "runtime-core", "child_entry_type": "completion_gates", "child_entry_id": "VAL-001"},
                {"local_key": "runtime-integration", "child_entry_type": "completion_gates", "child_entry_id": "VAL-001"},
            ],
            "reason": "Each child has a bounded validation gate.",
            "integration_rationale": "Validation is split across two exact child gates.",
        },
        {
            "parent_entry_type": "downstream_integration_obligations",
            "parent_entry_id": "INT-001",
            "disposition": "assigned_to_child",
            "child_targets": [
                {"local_key": "runtime-integration", "child_entry_type": "downstream_integration_obligations", "child_entry_id": "INT-001"}
            ],
            "reason": "The integration child owns the exact obligation.",
            "integration_rationale": "",
        },
    ]
    return value


def blocked_result(parent: dict, decision: str) -> dict:
    gap = "design" if decision == "needs_artifact" else "uncertain"
    disposition = "blocked_by_artifact" if decision == "needs_artifact" else "blocked_by_human"
    value = base(parent, decision, gap)
    value["parent_requirement_coverage"] = [
        {
            "parent_entry_type": kind,
            "parent_entry_id": entry_id,
            "disposition": disposition,
            "child_targets": [],
            "reason": "Publication is blocked without authority.",
            "integration_rationale": "",
        }
        for kind, entry_id in (
            ("acceptance_criteria", "AC-001"),
            ("completion_gates", "VAL-001"),
            ("downstream_integration_obligations", "INT-001"),
        )
    ]
    if decision == "needs_artifact":
        value["artifact_proposal"] = {
            "title": "Smallest missing design",
            "purpose": "Authorize only the decision needed to resume decomposition.",
            "source_parent_obligations": [
                {"parent_entry_type": kind, "parent_entry_id": entry_id}
                for kind, entry_id in (
                    ("acceptance_criteria", "AC-001"),
                    ("completion_gates", "VAL-001"),
                    ("downstream_integration_obligations", "INT-001"),
                )
            ],
            "authorized_decisions_needed": ["Choose the approved boundary."],
            "out_of_scope": ["New mechanics and unrelated content."],
        }
    else:
        value["unresolved_questions"] = ["Which approved interpretation governs the parent?"]
    return value


def expect_failure(payload: dict, parent: dict, fragment: str, existing=()) -> None:
    try:
        validate_decomposition_result(payload, parent_task=parent, existing_reconciliation_keys=existing)
    except (DecompositionContractError, DecompositionPolicyError) as exc:
        assert fragment.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError(f"Expected failure containing {fragment!r}")


def assert_all_object_properties_required(schema: dict, path: str = "$") -> None:
    declared_type = schema["type"]
    types = {declared_type} if type(declared_type) is str else set(declared_type)
    if "object" in types:
        properties = schema.get("properties", {})
        assert set(schema.get("required", [])) == set(properties), (
            f"{path} does not require every declared property"
        )
        for name, child_schema in properties.items():
            assert_all_object_properties_required(child_schema, f"{path}.{name}")
    if "array" in types:
        assert_all_object_properties_required(schema["items"], f"{path}[]")


def main() -> int:
    validate_schema(DECOMPOSITION_RESULT_SCHEMA)
    assert_all_object_properties_required(DECOMPOSITION_RESULT_SCHEMA)
    parent = parent_task()

    concrete = validate_decomposition_result(retained_result(parent), parent_task=parent)
    assert concrete.decision == "already_concrete"
    decomposed = validate_decomposition_result(decomposed_result(parent), parent_task=parent)
    assert len(decomposed.children) == 2
    reparsed = validate_decomposition_result(decomposed, parent_task=parent)
    assert reparsed is not decomposed
    assert reparsed.parent_task is not decomposed.parent_task
    assert reparsed.children[0] is not decomposed.children[0]
    assert reparsed.canonical_json() == decomposed.canonical_json()

    class DecompositionResultSubclass(DecompositionResult):
        def to_dict(self) -> dict:
            return decomposed_result(parent)

    subclass = DecompositionResultSubclass(**decomposed.__dict__)
    expect_failure(subclass, parent, "subclasses are not accepted")
    directly_invalid = DecompositionResult(
        schema_version=decomposed.schema_version,
        parent_task=decomposed.parent_task,
        decision="invalid-decision",
        gap_type=decomposed.gap_type,
        reason=decomposed.reason,
        children=decomposed.children,
        parent_requirement_coverage=decomposed.parent_requirement_coverage,
        inbound_dependency_rewrites=decomposed.inbound_dependency_rewrites,
        unsupported_assumptions=decomposed.unsupported_assumptions,
        unresolved_questions=decomposed.unresolved_questions,
        artifact_proposal=decomposed.artifact_proposal,
    )
    expect_failure(directly_invalid, parent, "unsupported decomposition decision")
    artifact = validate_decomposition_result(blocked_result(parent, "needs_artifact"), parent_task=parent)
    human = validate_decomposition_result(blocked_result(parent, "needs_human"), parent_task=parent)
    assert artifact.artifact_proposal
    assert human.unresolved_questions
    assert concrete.artifact_proposal is None
    assert decomposed.artifact_proposal is None
    assert human.artifact_proposal is None
    for valid in (concrete, decomposed, artifact, human):
        validate_instance(valid.to_dict(), DECOMPOSITION_RESULT_SCHEMA)
        assert "artifact_proposal" in valid.to_dict()
        assert "inbound_dependency_rewrites" in valid.to_dict()
    assert concrete.to_dict()["artifact_proposal"] is None
    assert artifact.to_dict()["artifact_proposal"] == blocked_result(
        parent, "needs_artifact"
    )["artifact_proposal"]
    validate_instance(None, DECOMPOSITION_RESULT_SCHEMA["properties"]["artifact_proposal"])
    validate_instance(
        artifact.to_dict()["artifact_proposal"],
        DECOMPOSITION_RESULT_SCHEMA["properties"]["artifact_proposal"],
    )

    legacy_payload = retained_result(parent)
    legacy_payload["schema_version"] = "1.0"
    legacy_payload.pop("inbound_dependency_rewrites")
    legacy_payload.pop("artifact_proposal")
    compatible = DecompositionResult.from_dict(legacy_payload)
    assert compatible.schema_version == "1.0"
    assert compatible.inbound_dependency_rewrites == ()
    assert compatible.artifact_proposal is None
    assert "inbound_dependency_rewrites" not in compatible.to_dict()
    assert compatible.to_dict()["artifact_proposal"] is None

    bad = retained_result(parent)
    bad["parent_task"]["contract_sha256"] = "x" * 64
    expect_failure(bad, parent, "lowercase SHA-256")
    bad = retained_result(parent)
    bad["parent_task"]["contract_revision"] = True
    expect_failure(bad, parent, "positive integer")
    bad = decomposed_result(parent)
    bad["children"][1]["local_key"] = "runtime-core"
    expect_failure(bad, parent, "duplicate local_key")
    expect_failure(decomposed_result(parent), parent, "collides", existing={"runtime-core"})

    valid_resources = decomposed_result(parent)
    valid_resources["children"][0]["exclusive_resources"] = [
        "repo-file:ProjectSettings/ProjectVersion.txt",
        "unity-scene:Assets/Scenes/Gameplay.unity",
        "unity-prefab:Assets/Prefabs/Player.prefab",
        "logical:gameplay-shared-surface",
    ]
    validate_decomposition_result(valid_resources, parent_task=parent)
    for malformed_resource in (
        "unknown:value",
        "repo-file:",
        "repo-file:/Assets/Absolute.cs",
        "repo-file:Assets/../Escape.cs",
        "repo-file:Assets//DuplicateSeparator.cs",
        "repo-file:Assets\\Backslash.cs",
        " repo-file:Assets/Whitespace.cs ",
        "unity-scene:ProjectSettings/Scene.unity",
        "unity-prefab:Assets",
        "logical:",
        "logical:Uppercase",
        "logical:contains_underscore",
    ):
        bad = decomposed_result(parent)
        bad["children"][0]["exclusive_resources"] = [malformed_resource]
        expect_failure(bad, parent, "exclusive_resources")
    bad = retained_result(parent)
    bad["gap_type"] = "execution"
    expect_failure(bad, parent, "incompatible")
    bad = retained_result(parent)
    bad["children"] = [child("illegal-child")]
    expect_failure(bad, parent, "may not contain child")
    bad = blocked_result(parent, "needs_artifact")
    bad["artifact_proposal"] = None
    expect_failure(bad, parent, "requires one")
    artifact_object = blocked_result(parent, "needs_artifact")["artifact_proposal"]
    for bad in (
        retained_result(parent),
        decomposed_result(parent),
        blocked_result(parent, "needs_human"),
    ):
        bad["artifact_proposal"] = deepcopy(artifact_object)
        expect_failure(bad, parent, "may not contain an artifact")
    for field, id_field, malformed in (
        ("acceptance_criteria", "criterion_id", "A-001"),
        ("completion_gates", "gate_id", "V-001"),
        ("downstream_integration_obligations", "obligation_id", "I-001"),
    ):
        bad = decomposed_result(parent)
        target_child = bad["children"][1] if field == "downstream_integration_obligations" else bad["children"][0]
        target_child[field][0][id_field] = malformed
        expect_failure(bad, parent, "invalid format")
    bad = decomposed_result(parent)
    bad["children"][0]["acceptance_criteria"].append(deepcopy(bad["children"][0]["acceptance_criteria"][0]))
    expect_failure(bad, parent, "duplicate entry IDs")
    bad = decomposed_result(parent)
    bad["parent_requirement_coverage"].pop()
    expect_failure(bad, parent, "missing parent requirement coverage")
    bad = decomposed_result(parent)
    bad["parent_requirement_coverage"].append(deepcopy(bad["parent_requirement_coverage"][0]))
    expect_failure(bad, parent, "duplicate parent coverage")
    bad = decomposed_result(parent)
    bad["parent_requirement_coverage"][0]["child_targets"][0]["local_key"] = "missing-child"
    expect_failure(bad, parent, "unknown child")
    bad = decomposed_result(parent)
    bad["parent_requirement_coverage"][0]["child_targets"][0]["child_entry_id"] = "AC-999"
    expect_failure(bad, parent, "unknown child entry")
    bad = decomposed_result(parent)
    bad["parent_requirement_coverage"][0]["child_targets"].pop()
    expect_failure(bad, parent, "untraced child obligation")
    bad = decomposed_result(parent)
    bad["children"][0]["acceptance_criteria"] = []
    expect_failure(bad, parent, "at least one acceptance criterion")
    bad = decomposed_result(parent)
    bad["children"][0]["completion_gates"] = []
    expect_failure(bad, parent, "at least one completion gate")
    bad = decomposed_result(parent)
    bad["children"][0]["acceptance_criteria"] = []
    bad["children"][0]["completion_gates"] = []
    bad["children"][0]["downstream_integration_obligations"] = []
    expect_failure(bad, parent, "at least one acceptance criterion")
    bad = decomposed_result(parent)
    for record in bad["parent_requirement_coverage"]:
        record["child_targets"] = [
            target for target in record["child_targets"]
            if target["local_key"] != "runtime-core"
        ]
    expect_failure(bad, parent, "not targeted by any parent coverage")

    bad = decomposed_result(parent)
    bad["parent_requirement_coverage"][0]["child_targets"] = []
    expect_failure(bad, parent, "at least one exact child target")
    bad = decomposed_result(parent)
    removed_target = bad["parent_requirement_coverage"][0]["child_targets"].pop()
    bad["parent_requirement_coverage"][0]["integration_rationale"] = ""
    bad["parent_requirement_coverage"][2]["child_targets"].append(removed_target)
    expect_failure(bad, parent, "one child target requires")
    one_target = decomposed_result(parent)
    removed_target = one_target["parent_requirement_coverage"][0]["child_targets"].pop()
    one_target["parent_requirement_coverage"][2]["child_targets"].append(removed_target)
    validate_decomposition_result(one_target, parent_task=parent)
    multiple_targets = decomposed_result(parent)
    multiple_targets["parent_requirement_coverage"][0]["integration_rationale"] = ""
    validate_decomposition_result(multiple_targets, parent_task=parent)
    bad = decomposed_result(parent)
    bad["parent_requirement_coverage"][0]["disposition"] = "retained_by_parent"
    expect_failure(bad, parent, "invalid for decision")
    for field in ("unresolved_questions", "unsupported_assumptions"):
        bad = decomposed_result(parent)
        bad[field] = ["Not acceptable on an accepted result."]
        expect_failure(bad, parent, "may not contain unsupported assumptions")

    rewrite = decomposed_result(parent)
    rewrite["inbound_dependency_rewrites"] = [
        {
            "dependent_task_id": "NSC-050",
            "replacement_local_keys": ["runtime-integration"],
            "reason": "Consumer requires the integrated child capability.",
        }
    ]
    validated_rewrite = validate_decomposition_result(rewrite, parent_task=parent)
    assert validated_rewrite.inbound_dependency_rewrites[0].replacement_local_keys == (
        "runtime-integration",
    )

    bad = decomposed_result(parent)
    bad["inbound_dependency_rewrites"] = [
        {
            "dependent_task_id": "NSC-050",
            "replacement_local_keys": [],
            "reason": "Invalid empty replacement set.",
        }
    ]
    expect_failure(bad, parent, "at least one concrete child key")

    bad = decomposed_result(parent)
    bad["inbound_dependency_rewrites"] = [
        {
            "dependent_task_id": "NSC-050",
            "replacement_local_keys": ["missing-child"],
            "reason": "Invalid unknown child.",
        }
    ]
    expect_failure(bad, parent, "references unknown child")

    bad = decomposed_result(parent)
    bad["inbound_dependency_rewrites"] = [
        {
            "dependent_task_id": "NSC-050",
            "replacement_local_keys": ["runtime-integration"],
            "reason": "first",
        },
        {
            "dependent_task_id": "NSC-050",
            "replacement_local_keys": ["runtime-core"],
            "reason": "duplicate dependent",
        },
    ]
    expect_failure(bad, parent, "duplicate dependent_task_id")

    bad = retained_result(parent)
    bad["inbound_dependency_rewrites"] = [
        {
            "dependent_task_id": "NSC-050",
            "replacement_local_keys": ["runtime-core"],
            "reason": "Non-decomposed results cannot rewrite dependencies.",
        }
    ]
    expect_failure(bad, parent, "may not contain inbound dependency rewrites")

    mixed_artifact = blocked_result(parent, "needs_artifact")
    mixed_artifact["parent_requirement_coverage"][1]["disposition"] = "retained_by_parent"
    mixed_artifact["artifact_proposal"]["source_parent_obligations"] = [
        ref
        for ref in mixed_artifact["artifact_proposal"]["source_parent_obligations"]
        if ref["parent_entry_id"] != "VAL-001"
    ]
    validate_decomposition_result(mixed_artifact, parent_task=parent)

    bad = blocked_result(parent, "needs_artifact")
    bad["artifact_proposal"]["source_parent_obligations"].pop()
    expect_failure(bad, parent, "exactly match blocked_by_artifact")

    bad = blocked_result(parent, "needs_artifact")
    bad["parent_requirement_coverage"][0]["disposition"] = "retained_by_parent"
    expect_failure(bad, parent, "must have blocked_by_artifact coverage")
    bad = blocked_result(parent, "needs_artifact")
    for record in bad["parent_requirement_coverage"]:
        record["disposition"] = "retained_by_parent"
    expect_failure(bad, parent, "at least one blocked_by_artifact")

    mixed_human = blocked_result(parent, "needs_human")
    mixed_human["parent_requirement_coverage"][1]["disposition"] = "retained_by_parent"
    validate_decomposition_result(mixed_human, parent_task=parent)
    bad = blocked_result(parent, "needs_human")
    for record in bad["parent_requirement_coverage"]:
        record["disposition"] = "retained_by_parent"
    expect_failure(bad, parent, "at least one blocked_by_human")

    mutable = decomposed_result(parent)
    validated = validate_decomposition_result(mutable, parent_task=parent)
    before = validated.canonical_json()
    mutable["children"][0]["title"] = "MUTATED"
    mutable["parent_requirement_coverage"][0]["child_targets"][0]["local_key"] = "mutated"
    assert validated.canonical_json() == before
    assert validated.canonical_json() == validate_decomposition_result(
        json.loads(before), parent_task=parent
    ).canonical_json()
    assert hashlib.sha256(before.encode("utf-8")).hexdigest() == hashlib.sha256(validated.canonical_json().encode("utf-8")).hexdigest()

    print("decomposition_contracts_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
