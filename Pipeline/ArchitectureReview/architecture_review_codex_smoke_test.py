from __future__ import annotations

import architecture_review as shared
import architecture_review_codex as codex_review


def main() -> int:
    # Importing the Codex runner must preserve the shared eight-role review
    # contract while replacing only provider/model execution details.
    assert len(shared.ROLE_SPECS) == 8
    assert shared.invoke_read_only_agent is codex_review.invoke_codex_agent
    assert shared.MODEL_POOL == codex_review.MODEL_POOL
    assert shared.SYNTHESIS_MODEL == codex_review.SYNTHESIS_MODEL
    assert shared.ADVERSARY_MODEL == codex_review.ADVERSARY_MODEL

    assert codex_review.MODEL_POOL
    assert all(model.startswith("gpt-") for model in codex_review.MODEL_POOL)
    assert codex_review.SYNTHESIS_MODEL.startswith("gpt-")
    assert codex_review.ADVERSARY_MODEL.startswith("gpt-")

    assert codex_review.REVIEW_REASONING_EFFORT == "high"
    assert codex_review.SYNTHESIS_REASONING_EFFORT == "xhigh"
    assert codex_review.ADVERSARY_REASONING_EFFORT == "xhigh"

    assert codex_review.reasoning_effort_for("Independent Reviewer") == "high"
    assert codex_review.reasoning_effort_for("Architecture Synthesis") == "xhigh"
    assert codex_review.reasoning_effort_for("Adversarial Synthesis Critic") == "xhigh"

    sample = shared.common_review_prompt(
        role_name="Smoke Test Reviewer",
        role_focus="Test the review contract.",
        frozen_head="deadbeef",
    )
    assert "You may reject them" in sample
    assert "GDD is iterative" in sample
    assert "days instead of weeks" in sample
    assert "materially different architecture" in sample

    print("architecture_review_codex_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
