from __future__ import annotations

import random

import reconciliation_agent as reconciliation
import verification_crew as crew


def main() -> int:
    assignments = crew.choose_audit_models(random.Random(12345))

    assert reconciliation._is_allowed_review_path("Packages/manifest.json")
    assert not reconciliation._is_allowed_review_path("Packages/packages-lock.json")

    valid_history = {
        "sources": {
            "files_reviewed": ["Packages/manifest.json"],
            "historical_sources_reviewed": [
                "Assignment6GER/README_Assignment6.md"
            ],
        }
    }
    reconciliation.validate_reviewed_paths(valid_history)

    invalid_history = {
        "sources": {
            "files_reviewed": ["Packages/manifest.json"],
            "historical_sources_reviewed": ["Packages/manifest.json"],
        }
    }
    try:
        reconciliation.validate_reviewed_paths(invalid_history)
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "Packages/manifest.json must not be accepted as historical evidence."
        )

    if len(crew.MODEL_POOL) > 1:
        assert assignments["coverage_a"] != assignments["coverage_b"]
        assert assignments["structure"] != assignments["evidence"]
        assert "execution" in assignments

    audits = [
        {
            "agent": "GDD Coverage Auditor A",
            "requested_model": crew.MODEL_POOL[0],
            "result": {
                "verdict": "fail",
                "findings": [],
                "notes": [],
                "requirements": [
                    {
                        "requirement_id": "REQ-TEST-001",
                        "reference": "Section Test",
                        "requirement": "Required test behavior",
                        "classification": "required_gameplay",
                        "representation": "unrepresented",
                        "mapped_keys": [],
                        "explanation": "Deliberately uncovered for smoke test.",
                    }
                ],
            },
        },
        {
            "agent": "Repository Evidence Auditor",
            "requested_model": crew.MODEL_POOL[-1],
            "result": {
                "verdict": "pass",
                "findings": [],
                "notes": [],
            },
        },
    ]

    merged = crew.merge_findings(audits)
    assert merged["material_finding_count"] == 1
    assert merged["findings"][0]["source_agent"] == "Deterministic Coverage Check"


    # Representation taxonomy: required statements do not all imply work items.
    taxonomy_ok = [
        {
            "agent": "GDD Coverage Auditor A",
            "requested_model": crew.MODEL_POOL[0],
            "result": {
                "requirements": [
                    {
                        "requirement_id": "REQ-ACCEPT",
                        "reference": "Section Test",
                        "requirement": "Behavior owned by an existing task",
                        "classification": "required_gameplay",
                        "representation": "acceptance_criterion",
                        "mapped_keys": ["existing-task"],
                        "explanation": "Acceptance criterion.",
                    },
                    {
                        "requirement_id": "REQ-VALIDATE",
                        "reference": "Section Test",
                        "requirement": "Explicit validation check",
                        "classification": "required_gameplay",
                        "representation": "validation_requirement",
                        "mapped_keys": ["existing-task"],
                        "explanation": "Validation requirement.",
                    },
                    {
                        "requirement_id": "REQ-PIPELINE",
                        "reference": "Section Test",
                        "requirement": "Do not concurrently modify one Unity asset",
                        "classification": "required_process",
                        "representation": "pipeline_constraint",
                        "mapped_keys": [],
                        "explanation": "Pipeline invariant.",
                    },
                    {
                        "requirement_id": "REQ-DELIVERY",
                        "reference": "Section Test",
                        "requirement": "Produce the Windows build",
                        "classification": "required_non_code",
                        "representation": "delivery_requirement",
                        "mapped_keys": [],
                        "explanation": "Delivery requirement.",
                    },
                ]
            },
        }
    ]
    assert crew.deterministic_audit_checks(taxonomy_ok) == []

    taxonomy_bad = [
        {
            "agent": "GDD Coverage Auditor A",
            "requested_model": crew.MODEL_POOL[0],
            "result": {
                "requirements": [
                    {
                        "requirement_id": "REQ-AMBIG",
                        "reference": "Section Test",
                        "requirement": "Required but mapping is unclear",
                        "classification": "required_gameplay",
                        "representation": "ambiguous",
                        "mapped_keys": [],
                        "explanation": "Ambiguous on purpose.",
                    },
                    {
                        "requirement_id": "REQ-WRONG-TYPE",
                        "reference": "Section Test",
                        "requirement": "Gameplay incorrectly called process",
                        "classification": "required_gameplay",
                        "representation": "pipeline_constraint",
                        "mapped_keys": [],
                        "explanation": "Wrong representation on purpose.",
                    },
                    {
                        "requirement_id": "REQ-NO-OWNER",
                        "reference": "Section Test",
                        "requirement": "Acceptance criterion without owner",
                        "classification": "required_gameplay",
                        "representation": "acceptance_criterion",
                        "mapped_keys": [],
                        "explanation": "Missing owner on purpose.",
                    },
                    {
                        "requirement_id": "REQ-STRETCH-LEAK",
                        "reference": "Section Test",
                        "requirement": "Stretch item incorrectly seeded",
                        "classification": "stretch",
                        "representation": "work_item",
                        "mapped_keys": ["bad-stretch-task"],
                        "explanation": "Scope leak on purpose.",
                    },
                ]
            },
        }
    ]
    taxonomy_findings = crew.deterministic_audit_checks(taxonomy_bad)
    assert len(taxonomy_findings) == 4
    categories = {
        item["finding"]["category"] for item in taxonomy_findings
    }
    assert "requirement_representation_problem" in categories
    assert "scope_leak" in categories
    ambiguous = next(
        item
        for item in taxonomy_findings
        if item["finding"]["finding_id"].endswith("REQ-AMBIG")
    )
    assert ambiguous["finding"]["requires_human_review"] is True
    assert "new work item" in ambiguous["finding"]["recommended_change"]

    refiner_findings = crew.build_refiner_findings(
        {
            "finding_count": 3,
            "findings": [
                {"finding": {"severity": "error", "title": "must fix"}},
                {"finding": {"severity": "warning", "title": "recheck later"}},
                {"finding": {"severity": "suggestion", "title": "optional"}},
            ],
        }
    )
    assert refiner_findings["source_finding_count"] == 3
    assert refiner_findings["material_finding_count"] == 1
    assert len(refiner_findings["findings"]) == 1
    assert refiner_findings["findings"][0]["finding"]["title"] == "must fix"
    assert crew.choose_refiner_model(random.Random(1), assignments) == crew.REFINER_MODEL

    payload = {
        "sources": {
            "files_reviewed": [
                "Docs/GDD/No_Safe_Circle_GDD.md",
                "Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMana.cs",
                "Pipeline/Reconciliation/outputs/runs/example/reconciliation.json",
                "Pipeline/Reconciliation/outputs/runs/example/verifications/v1/MERGED_FINDINGS_PASS1.json",
            ]
        }
    }
    removed = crew.sanitize_refiner_input_tracking(payload)
    assert len(removed) == 2
    assert payload["sources"]["files_reviewed"] == [
        "Docs/GDD/No_Safe_Circle_GDD.md",
        "Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMana.cs",
    ]


    legacy = {
        "work_items": [
            {"key": "root", "kind": "feature", "graph_status": "open"},
            {"key": "todo", "kind": "implementation", "graph_status": "open"},
            {"key": "done", "kind": "implementation", "graph_status": "complete"},
        ]
    }
    upgraded = crew.ensure_execution_scope_defaults(legacy)
    assert set(upgraded) == {"root", "todo", "done"}
    assert legacy["work_items"][0]["execution_scope"] == "not_applicable"
    assert legacy["work_items"][1]["execution_scope"] == "unknown"
    assert legacy["work_items"][2]["execution_scope"] == "not_applicable"


    resource_legacy = {
        "work_items": [
            {"key": "feature", "kind": "feature", "graph_status": "open"},
            {"key": "task-a", "kind": "implementation", "graph_status": "open"},
            {"key": "task-b", "kind": "implementation", "graph_status": "open"},
        ]
    }
    resource_upgraded = reconciliation.ensure_exclusive_resource_defaults(
        resource_legacy
    )
    assert set(resource_upgraded) == {"feature", "task-a", "task-b"}

    shared = {
        "key": (
            "repo-file:"
            "Assets/NoSafeCircle/DoorPrototype/Editor/"
            "DoorPrototypeSceneBuilder.cs"
        ),
        "reason": "Both tasks modify the same scene builder.",
        "evidence": "Current repository uses one builder for the prototype scene.",
    }
    resource_legacy["work_items"][1]["exclusive_resources"] = [dict(shared)]
    resource_legacy["work_items"][2]["exclusive_resources"] = [dict(shared)]

    by_key = reconciliation._validate_unique_keys(
        resource_legacy["work_items"]
    )
    reconciliation._validate_exclusive_resources(by_key)
    groups = reconciliation.build_exclusive_resource_groups(
        resource_legacy["work_items"]
    )
    assert groups == [
        {
            "resource_key": shared["key"],
            "work_keys": ["task-a", "task-b"],
        }
    ]

    invalid_resource = {
        "feature": {
            "key": "feature",
            "kind": "feature",
            "graph_status": "open",
            "exclusive_resources": [
                {
                    "key": "logical:should-not-lock-feature",
                    "reason": "invalid",
                    "evidence": "invalid",
                }
            ],
        }
    }
    try:
        reconciliation._validate_exclusive_resources(invalid_resource)
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "Feature nodes must not carry exclusive resource locks."
        )

    requirement_legacy = {
        "work_items": [
            {"key": "legacy-requirement-task"},
        ]
    }
    requirement_upgraded = reconciliation.ensure_requirement_detail_defaults(
        requirement_legacy
    )
    assert requirement_upgraded == ["legacy-requirement-task"]
    assert requirement_legacy["work_items"][0]["acceptance_criteria"] == []
    assert requirement_legacy["work_items"][0]["validation_requirements"] == []

    print("verification smoke test passed")
    print(f"model pool: {', '.join(crew.MODEL_POOL)}")
    print(f"sample assignments: {assignments}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
