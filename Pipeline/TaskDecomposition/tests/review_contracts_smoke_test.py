from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = ROOT / "Pipeline" / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.schema_validation import validate_schema
from TaskDecomposition.review_contracts import (
    DecompositionReviewContractError,
    DecompositionReviewResult,
)
from TaskDecomposition.review_policy import (
    DecompositionReviewPolicyError,
    validate_decomposition_review,
)
from TaskDecomposition.review_schemas import DECOMPOSITION_REVIEW_SCHEMA
from TaskDecomposition.tests.test_support import decomposed_result, task


CANDIDATE_SHA = "a" * 64
FINDING_ID = "round-02-duplicate-ownership"


def parent() -> dict:
    return task(
        "NSC-010",
        "selected-parent",
        "implementation",
        "NSC-001",
        "needs_execution_decomposition",
        "concrete",
    )


def finding(finding_id: str = FINDING_ID) -> dict:
    return {
        "finding_id": finding_id,
        "severity": "blocking",
        "category": "duplicate_responsibility",
        "affected_contracts": ["NSC-010", "proposed:bounded-child"],
        "problem": "The reviewed candidate duplicates an owned responsibility.",
        "required_resolution": "Remove the duplicate or establish distinct ownership.",
    }


def review(
    verdict: str,
    *,
    findings=(),
    resolutions=(),
    revised=None,
    candidate_sha: str = CANDIDATE_SHA,
) -> dict:
    return {
        "schema_version": "1.0",
        "reviewed_candidate_sha256": candidate_sha,
        "verdict": verdict,
        "summary": "Synthetic independent review.",
        "findings": list(findings),
        "prior_finding_resolutions": list(resolutions),
        "revised_decomposition": revised,
    }


def resolution(status: str) -> dict:
    return {
        "finding_id": FINDING_ID,
        "status": status,
        "explanation": f"Synthetic {status} determination against the current candidate.",
    }


def expect_contract_failure(raw: dict, fragment: str) -> None:
    try:
        DecompositionReviewResult.from_dict(raw)
    except DecompositionReviewContractError as exc:
        assert fragment.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError(f"expected contract failure containing {fragment!r}")


def expect_policy_failure(raw: dict, *, prior, all_ids, round_number: int, fragment: str) -> None:
    try:
        validate_decomposition_review(
            raw,
            expected_candidate_sha256=CANDIDATE_SHA,
            round_number=round_number,
            prior_unresolved_findings=prior,
            all_prior_finding_ids=all_ids,
        )
    except DecompositionReviewPolicyError as exc:
        assert fragment.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError(f"expected policy failure containing {fragment!r}")


def main() -> int:
    validate_schema(DECOMPOSITION_REVIEW_SCHEMA)
    revised = decomposed_result(parent())

    first, unresolved = validate_decomposition_review(
        review("revise", findings=[finding()], revised=revised),
        expected_candidate_sha256=CANDIDATE_SHA,
        round_number=2,
        prior_unresolved_findings={},
        all_prior_finding_ids=set(),
    )
    assert first.verdict == "revise"
    assert set(unresolved) == {FINDING_ID}

    # A later reviewer may revise the candidate because the same prior defect remains
    # blocking; it must not manufacture a duplicate new finding just to continue.
    revised_again = deepcopy(revised)
    revised_again["children"][0]["notes"] = "Second attempted resolution."
    second, unresolved = validate_decomposition_review(
        review(
            "revise",
            resolutions=[resolution("still_blocking")],
            revised=revised_again,
        ),
        expected_candidate_sha256=CANDIDATE_SHA,
        round_number=3,
        prior_unresolved_findings=unresolved,
        all_prior_finding_ids={FINDING_ID},
    )
    assert second.verdict == "revise"
    assert set(unresolved) == {FINDING_ID}

    passed, unresolved = validate_decomposition_review(
        review("pass", resolutions=[resolution("resolved")]),
        expected_candidate_sha256=CANDIDATE_SHA,
        round_number=4,
        prior_unresolved_findings=unresolved,
        all_prior_finding_ids={FINDING_ID},
    )
    assert passed.verdict == "pass"
    assert unresolved == {}

    # Human escalation may preserve the unresolved defect without inventing a revision.
    human, unresolved = validate_decomposition_review(
        review("needs_human", resolutions=[resolution("still_blocking")]),
        expected_candidate_sha256=CANDIDATE_SHA,
        round_number=3,
        prior_unresolved_findings={FINDING_ID: first.findings[0]},
        all_prior_finding_ids={FINDING_ID},
    )
    assert human.verdict == "needs_human"
    assert set(unresolved) == {FINDING_ID}

    duplicate = review(
        "revise",
        findings=[finding(), finding()],
        revised=revised,
    )
    expect_contract_failure(duplicate, "duplicate finding_id")

    expect_policy_failure(
        review("pass", resolutions=[resolution("still_blocking")]),
        prior={FINDING_ID: first.findings[0]},
        all_ids={FINDING_ID},
        round_number=3,
        fragment="requires every prior blocking finding",
    )
    expect_policy_failure(
        review("revise", revised=revised),
        prior={},
        all_ids=set(),
        round_number=2,
        fragment="requires at least one blocking finding",
    )
    expect_policy_failure(
        review(
            "revise",
            findings=[finding("round-01-stale-prefix")],
            revised=revised,
        ),
        prior={},
        all_ids=set(),
        round_number=2,
        fragment="round-02",
    )
    expect_policy_failure(
        review("pass", candidate_sha="b" * 64),
        prior={},
        all_ids=set(),
        round_number=2,
        fragment="different candidate",
    )

    canonical = DecompositionReviewResult.from_dict(
        review("pass")
    ).canonical_json()
    assert canonical == DecompositionReviewResult.from_dict(
        review("pass")
    ).canonical_json()
    assert "NaN" not in canonical and "Infinity" not in canonical

    print("review_contracts_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
