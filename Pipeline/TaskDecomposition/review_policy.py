"""Deterministic semantic policy for D1B.2 review/revision output."""

from __future__ import annotations

from typing import Any, Mapping

from TaskDecomposition.review_contracts import (
    DecompositionReviewContractError,
    DecompositionReviewResult,
    ReviewFinding,
)


class DecompositionReviewPolicyError(ValueError):
    """Raised when a structurally valid review violates round-robin policy."""


def validate_decomposition_review(
    raw: Any,
    *,
    expected_candidate_sha256: str,
    round_number: int,
    prior_unresolved_findings: Mapping[str, ReviewFinding],
    all_prior_finding_ids: set[str] | frozenset[str],
) -> tuple[DecompositionReviewResult, dict[str, ReviewFinding]]:
    """Validate one independent review and derive the next unresolved set."""

    try:
        result = (
            raw
            if type(raw) is DecompositionReviewResult
            else DecompositionReviewResult.from_dict(raw)
        )
    except DecompositionReviewContractError:
        raise

    if result.reviewed_candidate_sha256 != expected_candidate_sha256:
        raise DecompositionReviewPolicyError(
            "Reviewer result is bound to a different candidate SHA-256."
        )

    expected_prefix = f"round-{round_number:02d}-"
    new_ids = {finding.finding_id for finding in result.findings}
    for finding_id in new_ids:
        if not finding_id.startswith(expected_prefix):
            raise DecompositionReviewPolicyError(
                f"New finding {finding_id!r} must start with {expected_prefix!r}."
            )
    collisions = new_ids.intersection(all_prior_finding_ids)
    if collisions:
        raise DecompositionReviewPolicyError(
            f"Review reuses prior finding IDs: {sorted(collisions)}."
        )

    expected_resolution_ids = set(prior_unresolved_findings)
    actual_resolution_ids = {
        resolution.finding_id for resolution in result.prior_finding_resolutions
    }
    if expected_resolution_ids != actual_resolution_ids:
        missing = sorted(expected_resolution_ids - actual_resolution_ids)
        extra = sorted(actual_resolution_ids - expected_resolution_ids)
        raise DecompositionReviewPolicyError(
            "prior_finding_resolutions must exactly cover the unresolved blocking "
            f"finding set (missing={missing}, extra={extra})."
        )

    unresolved = dict(prior_unresolved_findings)
    for resolution in result.prior_finding_resolutions:
        if resolution.status in {"resolved", "withdrawn"}:
            unresolved.pop(resolution.finding_id, None)
        elif resolution.status == "still_blocking":
            if resolution.finding_id not in unresolved:
                raise DecompositionReviewPolicyError(
                    f"Resolution references non-unresolved finding {resolution.finding_id!r}."
                )
        else:  # pragma: no cover - structural contract owns the enum.
            raise DecompositionReviewPolicyError(
                f"Unsupported finding resolution status {resolution.status!r}."
            )

    blocking_new = [
        finding for finding in result.findings if finding.severity == "blocking"
    ]
    for finding in blocking_new:
        unresolved[finding.finding_id] = finding

    if result.verdict == "pass":
        if result.revised_decomposition is not None:
            raise DecompositionReviewPolicyError(
                "pass may not contain a revised decomposition candidate."
            )
        if blocking_new:
            raise DecompositionReviewPolicyError(
                "pass may not introduce blocking findings."
            )
        if unresolved:
            raise DecompositionReviewPolicyError(
                "pass requires every prior blocking finding to be resolved or withdrawn."
            )
    elif result.verdict == "revise":
        if result.revised_decomposition is None:
            raise DecompositionReviewPolicyError(
                "revise requires a complete revised decomposition candidate."
            )
        if not blocking_new:
            raise DecompositionReviewPolicyError(
                "revise requires at least one new blocking finding against the reviewed candidate."
            )
    elif result.verdict == "needs_human":
        if result.revised_decomposition is not None:
            raise DecompositionReviewPolicyError(
                "needs_human may not contain a revised decomposition candidate."
            )
        if not unresolved:
            raise DecompositionReviewPolicyError(
                "needs_human requires at least one unresolved blocking finding."
            )
    else:  # pragma: no cover - structural contract owns the enum.
        raise DecompositionReviewPolicyError(
            f"Unsupported review verdict {result.verdict!r}."
        )

    return result, unresolved
