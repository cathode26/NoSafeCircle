from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streaming_refinement_v2 as stream


def op(
    *,
    target_type: str = "work_item",
    target_id: str = "example",
    field: str = "acceptance_criteria",
    operation: str = "append_unique",
    value: object = None,
) -> dict[str, str]:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "field": field,
        "op": operation,
        "value_json": "" if operation == "remove_record" else json.dumps(value),
        "reason": "smoke test",
    }


def main() -> int:
    source = {
        "summary": {"desired_state_summary": "x", "current_state_summary": "y", "major_findings": []},
        "seed_assessment": {"status": "ready_with_warnings", "blockers": [], "warnings": []},
        "sources": {"files_reviewed": [], "historical_sources_reviewed": []},
        "work_items": [
            {
                "key": "example",
                "acceptance_criteria": [],
                "exclusive_resources": [],
                "confidence": "medium",
            }
        ],
        "non_code_requirements": [],
        "deferred_or_excluded": [],
        "unresolved_questions": [{"question": "obsolete?", "why_unresolved": "old"}],
    }

    operations = [
        op(value={"reference": "GDD", "requirement": "A"}),
        op(field="confidence", operation="set", value="high"),
        op(
            target_type="unresolved_question",
            target_id="obsolete?",
            field="",
            operation="remove_record",
        ),
    ]
    refined = stream.apply_stream_operations(source, operations)
    assert refined["work_items"][0]["confidence"] == "high"
    assert len(refined["work_items"][0]["acceptance_criteria"]) == 1
    assert refined["unresolved_questions"] == []
    assert source["work_items"][0]["confidence"] == "medium"

    append_a = op(value={"reference": "A", "requirement": "one"})
    append_b = op(value={"reference": "B", "requirement": "two"})
    assert stream._field_operations_compatible([append_a, append_b])

    set_a = op(field="confidence", operation="set", value="high")
    set_b = op(field="confidence", operation="set", value="low")
    assert not stream._field_operations_compatible([set_a, set_b])

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        candidate = root / "candidate.json"
        candidate.write_text(json.dumps(source), encoding="utf-8")
        coordinator = stream.StreamingRepairCoordinator(
            source_candidate=candidate,
            source_run_id="smoke",
            run_dir=root / "run",
        )
        coordinator.repairs = {
            "remove_audit": {
                "result": {
                    "operations": [
                        op(field="", operation="remove_record")
                    ]
                }
            },
            "field_audit": {
                "result": {
                    "operations": [
                        op(field="confidence", operation="set", value="high")
                    ]
                }
            },
        }
        coordinator._build_conflict_report()
        assert coordinator.conflict_report is not None
        assert coordinator.conflict_report["conflict_field_count"] == 1
        assert coordinator.conflict_report["conflict_component_count"] == 1
        coordinator.executor.shutdown(wait=True)

    print("streaming_refinement_v2_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
