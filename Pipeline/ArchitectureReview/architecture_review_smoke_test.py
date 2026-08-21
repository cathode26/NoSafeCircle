from __future__ import annotations

import architecture_review as review


def main() -> int:
    assert len(review.ROLE_SPECS) == 8

    keys = [role["key"] for role in review.ROLE_SPECS]
    names = [role["name"] for role in review.ROLE_SPECS]
    assert len(keys) == len(set(keys))
    assert len(names) == len(set(names))

    required_roles = {
        "game_technical_director",
        "workflow_systems_architect",
        "llm_reliability_engineer",
        "unity_production_engineer",
        "yagni_complexity_critic",
        "autonomous_agent_architect",
        "adversarial_qa",
        "game_producer",
    }
    assert set(keys) == required_roles

    assert "Docs/AI-Pipeline/CURRENT_STATE.md" in review.ARCHITECTURE_DOCS
    assert "Docs/AI-Pipeline/DECISIONS.md" in review.ARCHITECTURE_DOCS
    assert "Docs/AI-Pipeline/01_MILESTONE_TASK_GRAPH.md" in review.ARCHITECTURE_DOCS

    sample = review.common_review_prompt(
        role_name="Smoke Test Reviewer",
        role_focus="Test the review contract.",
        frozen_head="deadbeef",
    )

    assert "You may reject them" in sample
    assert "Do NOT assume `Tasks/*.yaml`" in sample
    assert "GDD is iterative" in sample
    assert "fundamentally sound" in sample
    assert "days instead of weeks" in sample
    assert "materially different architecture" in sample

    assignments = review.assign_models(12345)
    assert set(assignments) == required_roles
    assert all(model in review.MODEL_POOL for model in assignments.values())

    verdict_enum = review.REVIEW_SCHEMA["properties"]["overall_verdict"]["enum"]
    assert "fundamentally_wrong_approach" in verdict_enum
    assert "sound_high_leverage" in verdict_enum

    print("architecture_review_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
