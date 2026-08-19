from __future__ import annotations

import random

import verification_crew as crew


def main() -> int:
    assignments = crew.choose_audit_models(random.Random(12345))

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

    print("verification smoke test passed")
    print(f"model pool: {', '.join(crew.MODEL_POOL)}")
    print(f"sample assignments: {assignments}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
