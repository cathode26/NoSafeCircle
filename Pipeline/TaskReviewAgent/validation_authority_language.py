"""Authority-aware wording for downstream operator, provider, and Issue text.

Downstream delivery can be authorized two different ways:

* an exact-commit human Unity PASS recorded as a validated workflow event; or
* a policy-bound automated validation event for a private synthetic gauntlet
  task, which deliberately leaves ``human_result`` null.

The authority checks already distinguish those cases. Only the human-facing
prose lagged behind, so a fully automated run still printed operator and Issue
text such as "Carry the unchanged human PASS into merge closeout" and
"already-approved delivery". That text claims a human decision that never
happened.

This module owns the wording rules so every downstream message resolves the
same way:

* automated authority is never described as a human PASS, human approval, or an
  already human-approved delivery;
* a genuine exact-commit human PASS keeps its existing honest wording;
* an unresolved authority falls back to neutral wording rather than assuming a
  human decided anything.

It contains presentation only. It never decides whether delivery is authorized.
"""

from __future__ import annotations

from typing import Any, Mapping


AUTOMATED = "automated"
HUMAN = "human"


def normalized_authority_kind(value: Any) -> str | None:
    """Return ``automated``/``human`` for an exact known kind, else ``None``."""

    text = str(value).strip().casefold() if isinstance(value, str) else ""
    return text if text in {AUTOMATED, HUMAN} else None


def authority_kind_from_observation(observation: Any) -> str | None:
    """Resolve the wording authority from durable observation state only.

    A recorded exact human result of ``pass`` is human authority. Automated
    wording requires both a persisted automated validation authority in the
    downstream receipt and no human result at all, which matches the condition
    ``_authoritative_automated_validation`` enforces. Anything else is unknown,
    so the caller uses neutral wording instead of claiming an approval.
    """

    if not isinstance(observation, Mapping):
        return None
    coordination = observation.get("coordination")
    state = (
        coordination.get("workflow_state")
        if isinstance(coordination, Mapping)
        else None
    )
    human_result = state.get("human_result") if isinstance(state, Mapping) else None
    if isinstance(human_result, str) and human_result.strip().casefold() == "pass":
        return HUMAN
    if human_result is not None:
        return None
    downstream = observation.get("downstream")
    receipt = downstream.get("receipt") if isinstance(downstream, Mapping) else None
    authority = (
        receipt.get("validation_authority") if isinstance(receipt, Mapping) else None
    )
    if not isinstance(authority, Mapping):
        return None
    kind = normalized_authority_kind(authority.get("kind"))
    return kind if kind == AUTOMATED else None


def publish_delivery_review_label(kind: Any) -> str:
    """Operator-facing name of the delivery-review publication step."""

    resolved = normalized_authority_kind(kind)
    if resolved == HUMAN:
        return "Carry the unchanged human PASS into merge closeout"
    if resolved == AUTOMATED:
        return "Carry the unchanged automated validation evidence into merge closeout"
    return "Carry the unchanged recorded validation authority into merge closeout"


def merge_closeout_expected_validation(kind: Any) -> str:
    """Lease prose recorded in the Issue when merge closeout resumes."""

    resolved = normalized_authority_kind(kind)
    if resolved == HUMAN:
        return (
            "Merge closeout verification of the already-approved delivery "
            "evidence: approval, evidence commit, pull request, merge, and "
            "post-merge conformance."
        )
    if resolved == AUTOMATED:
        return (
            "Merge closeout verification of the delivery evidence accepted by "
            "the recorded automated validation authority: machine acceptance, "
            "evidence commit, pull request, merge, and post-merge conformance."
        )
    return (
        "Merge closeout verification of the recorded delivery-evidence "
        "authorization: recorded acceptance, evidence commit, pull request, "
        "merge, and post-merge conformance."
    )


def delivery_review_proposal_phrase(kind: Any) -> str:
    """Tail of the delivery-evidence lease prose that names the review target."""

    resolved = normalized_authority_kind(kind)
    if resolved == HUMAN:
        return "then a delivery review proposal for Vincent."
    if resolved == AUTOMATED:
        return (
            "then a hash-bound delivery review proposal accepted by the "
            "recorded automated validation authority."
        )
    return (
        "then a hash-bound delivery review proposal for the recorded "
        "validation authority."
    )


def original_validated_commit_label(kind: Any) -> str:
    """Issue-comment label for the commit the original authority validated."""

    resolved = normalized_authority_kind(kind)
    if resolved == HUMAN:
        return "Original human-tested commit"
    if resolved == AUTOMATED:
        return "Original machine-validated commit"
    return "Original validated commit"


def carried_authority_sentence(kind: Any) -> str:
    """Issue-comment sentence explaining that authority stays commit-bound."""

    resolved = normalized_authority_kind(kind)
    if resolved == HUMAN:
        return "The original human PASS remains attached only to its original commit."
    if resolved == AUTOMATED:
        return (
            "The original automated validation evidence remains attached only "
            "to its original commit."
        )
    return (
        "The original validation authority remains attached only to its "
        "original commit."
    )


__all__ = [
    "AUTOMATED",
    "HUMAN",
    "authority_kind_from_observation",
    "carried_authority_sentence",
    "delivery_review_proposal_phrase",
    "merge_closeout_expected_validation",
    "normalized_authority_kind",
    "original_validated_commit_label",
    "publish_delivery_review_label",
]
