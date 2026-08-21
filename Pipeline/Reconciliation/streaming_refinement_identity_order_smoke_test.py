from __future__ import annotations

import json

import streaming_refinement_v2 as stream


def operation(*, target_id: str, field: str, value: object) -> dict[str, str]:
    return {
        "target_type": "unresolved_question",
        "target_id": target_id,
        "field": field,
        "op": "set",
        "value_json": json.dumps(value),
        "reason": "identity ordering regression test",
    }


def main() -> int:
    original_question = (
        "What concrete Unity mechanism should door click-selection use, and does it "
        "require a dedicated new Input Action?"
    )
    narrowed_question = "Does door click-selection require a dedicated new Input Action?"

    source = {
        "summary": {},
        "seed_assessment": {},
        "sources": {},
        "work_items": [],
        "non_code_requirements": [],
        "deferred_or_excluded": [],
        "unresolved_questions": [
            {
                "question": original_question,
                "affects_keys": ["door-open-interaction"],
                "why_unresolved": "Original explanation.",
                "recommended_resolution": "repository_inspection",
            }
        ],
    }

    # Deliberately emit the identity rename FIRST, matching the failed clean run.
    # All operations are nevertheless addressed against the immutable source identity.
    operations = [
        operation(
            target_id=original_question,
            field="question",
            value=narrowed_question,
        ),
        operation(
            target_id=original_question,
            field="why_unresolved",
            value="Narrowed explanation after repository inspection.",
        ),
    ]

    refined = stream.apply_stream_operations(source, operations)
    questions = refined["unresolved_questions"]
    assert len(questions) == 1
    assert questions[0]["question"] == narrowed_question
    assert questions[0]["why_unresolved"] == "Narrowed explanation after repository inspection."

    # The immutable source payload must remain unchanged.
    assert source["unresolved_questions"][0]["question"] == original_question
    assert source["unresolved_questions"][0]["why_unresolved"] == "Original explanation."

    print("streaming_refinement_identity_order_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
