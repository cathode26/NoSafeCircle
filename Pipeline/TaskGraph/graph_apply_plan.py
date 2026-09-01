"""Pure deterministic Stage D1C graph-application preflight planning."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from graph_delta import (
    GraphDeltaPlan,
    GraphDeltaPlanningError,
    _identity_dict,
    _plan_payload,
    plan_graph_delta,
    semantic_json_sha256,
)
from persistent_work_graph import PersistentWorkGraph
from work_graph_transform import WorkGraphPlan


GraphApplyPlanStatus = Literal["fresh", "stale_proposal", "recompute_mismatch"]
GraphApplyPlanAuthority = Literal[
    "parent_semantic_hash",
    "source_graph_semantic_hash",
    "plan_graph_delta_recompute",
    "graph_delta_canonical_json",
]


class GraphApplyPlanningError(RuntimeError):
    """Raised when graph-application preflight inputs violate their API contract."""


@dataclass(frozen=True)
class GraphApplyPlanResult:
    """Immutable outcome of source binding and deterministic delta recomputation.

    ``recomputed_plan`` is present only for ``fresh``. Callers must never use a
    recomputed plan from a stale or mismatched reviewed proposal.
    """

    status: GraphApplyPlanStatus
    reason: str
    failed_authorities: tuple[GraphApplyPlanAuthority, ...]
    parent_task_id: str
    stored_plan_id: str
    expected_parent_semantic_hash: str
    actual_parent_semantic_hash: str | None
    expected_source_graph_semantic_hash: str
    actual_source_graph_semantic_hash: str
    stored_canonical_json_sha256: str
    recomputed_canonical_json_sha256: str | None
    recomputed_plan_id: str | None
    recomputed_plan: GraphDeltaPlan | None


def _source_plan(source_graph: Any) -> WorkGraphPlan:
    if type(source_graph) is WorkGraphPlan:
        return source_graph
    if type(source_graph) is PersistentWorkGraph:
        return source_graph.plan
    raise GraphApplyPlanningError(
        "source_graph must be a validated WorkGraphPlan or PersistentWorkGraph."
    )


def _stored_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if type(value) is not str or not value:
        raise GraphApplyPlanningError(
            f"stored_graph_delta.{field} must be a non-empty string."
        )
    return value


def _bounded_detail(error: BaseException, limit: int = 240) -> str:
    detail = " ".join(str(error).split()) or type(error).__name__
    if len(detail) <= limit:
        return detail
    return detail[: limit - 3] + "..."


def _stored_snapshot(
    stored_graph_delta: GraphDeltaPlan,
) -> tuple[dict[str, Any], str]:
    try:
        canonical_json = stored_graph_delta.canonical_json()
        payload = stored_graph_delta.to_dict()
    except (AttributeError, TypeError, ValueError) as exc:
        raise GraphApplyPlanningError(
            "Stored reviewed GraphDeltaPlan serialization is corrupt or truncated: "
            f"{_bounded_detail(exc)}"
        ) from exc
    if type(canonical_json) is not str or not canonical_json:
        raise GraphApplyPlanningError(
            "Stored reviewed GraphDeltaPlan canonical JSON must be a non-empty string."
        )
    if type(payload) is not dict:
        raise GraphApplyPlanningError(
            "Stored reviewed GraphDeltaPlan payload must be a JSON object."
        )
    try:
        normalized_json = GraphDeltaPlan.from_payload(payload).canonical_json()
    except GraphDeltaPlanningError as exc:
        raise GraphApplyPlanningError(
            "Stored reviewed GraphDeltaPlan payload is not canonical JSON: "
            f"{_bounded_detail(exc)}"
        ) from exc
    if canonical_json != normalized_json:
        raise GraphApplyPlanningError(
            "Stored reviewed GraphDeltaPlan serialization is not canonical JSON."
        )
    return payload, canonical_json


def _stored_sha256(payload: dict[str, Any], field: str) -> str:
    value = _stored_text(payload, field)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise GraphApplyPlanningError(
            f"stored_graph_delta.{field} must be lowercase SHA-256."
        )
    return value


def _stored_parent_identity(
    payload: dict[str, Any], parent_before_hash: str
) -> dict[str, Any]:
    summary = payload.get("parent_before_summary")
    if type(summary) is not dict:
        raise GraphApplyPlanningError(
            "stored_graph_delta.parent_before_summary must be a JSON object."
        )
    raw_identity = {
        "task_id": summary.get("task_id"),
        "contract_revision": summary.get("contract_revision"),
        "contract_sha256": parent_before_hash,
    }
    try:
        return _identity_dict(raw_identity, "stored_graph_delta.parent_before_summary")
    except GraphDeltaPlanningError as exc:
        raise GraphApplyPlanningError(str(exc)) from exc


def _require_selector_matches_stored_parent(
    selector: dict[str, Any], stored_parent_identity: dict[str, Any]
) -> None:
    if selector == stored_parent_identity:
        return
    labels = {
        "task_id": "task ID",
        "contract_revision": "contract revision",
        "contract_sha256": "contract SHA-256",
    }
    differences = [
        labels[field]
        for field in ("task_id", "contract_revision", "contract_sha256")
        if selector[field] != stored_parent_identity[field]
    ]
    raise GraphApplyPlanningError(
        "parent_selector does not match the stored reviewed GraphDeltaPlan parent "
        f"identity ({', '.join(differences)} differ)."
    )


def _canonical_json_sha256(canonical_json: str) -> str:
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _stale_reason(
    failed_authorities: tuple[GraphApplyPlanAuthority, ...],
    *,
    parent_task_id: str,
    parent_missing: bool,
) -> str:
    clauses: list[str] = []
    for authority in failed_authorities:
        if authority == "parent_semantic_hash":
            if parent_missing:
                clauses.append(
                    f"reviewed parent task {parent_task_id} is missing from the "
                    "current source graph"
                )
            else:
                clauses.append(
                    "the current parent semantic hash does not match the stored reviewed plan"
                )
        elif authority == "source_graph_semantic_hash":
            clauses.append(
                "the current whole-graph semantic hash does not match the stored reviewed plan"
            )
    return "Stored reviewed GraphDeltaPlan is stale because " + " and ".join(clauses) + "."


def plan_graph_apply(
    source_graph: Any,
    parent_selector: Any,
    decomposition_result: Any,
    stored_graph_delta: GraphDeltaPlan,
) -> GraphApplyPlanResult:
    """Run the fresh-source preflight for a reviewed graph delta.

    Source identity is checked before ``plan_graph_delta`` is called. A stale
    proposal is therefore rejected without reallocating children or substituting
    a newly computed plan for the reviewed authority.

    Slice 3 callers must perform the already-applied/idempotency check before
    calling this function. A legitimately applied plan changes graph identity and
    will otherwise appear stale to this fresh-source-only preflight.
    """

    if type(stored_graph_delta) is not GraphDeltaPlan:
        raise GraphApplyPlanningError(
            "stored_graph_delta must be an exact GraphDeltaPlan review snapshot."
        )

    source = _source_plan(source_graph)
    try:
        selector = _identity_dict(parent_selector, "parent_selector")
    except GraphDeltaPlanningError as exc:
        raise GraphApplyPlanningError(str(exc)) from exc

    stored_payload, stored_canonical_json = _stored_snapshot(stored_graph_delta)
    stored_plan_id = _stored_text(stored_payload, "plan_id")
    expected_parent_hash = _stored_sha256(stored_payload, "parent_before_hash")
    expected_graph_hash = _stored_sha256(
        stored_payload, "source_graph_semantic_hash"
    )
    stored_parent_identity = _stored_parent_identity(
        stored_payload, expected_parent_hash
    )
    _require_selector_matches_stored_parent(selector, stored_parent_identity)
    stored_canonical_hash = _canonical_json_sha256(stored_canonical_json)

    parent_task_id = selector["task_id"]
    current_parent = next(
        (task for task in source.tasks if task.get("id") == parent_task_id),
        None,
    )
    actual_parent_hash = (
        semantic_json_sha256(current_parent) if current_parent is not None else None
    )
    actual_graph_hash = semantic_json_sha256(_plan_payload(source))

    failed_source_authorities: list[GraphApplyPlanAuthority] = []
    if actual_parent_hash != expected_parent_hash:
        failed_source_authorities.append("parent_semantic_hash")
    if actual_graph_hash != expected_graph_hash:
        failed_source_authorities.append("source_graph_semantic_hash")
    if failed_source_authorities:
        failures = tuple(failed_source_authorities)
        return GraphApplyPlanResult(
            status="stale_proposal",
            reason=_stale_reason(
                failures,
                parent_task_id=parent_task_id,
                parent_missing=current_parent is None,
            ),
            failed_authorities=failures,
            parent_task_id=parent_task_id,
            stored_plan_id=stored_plan_id,
            expected_parent_semantic_hash=expected_parent_hash,
            actual_parent_semantic_hash=actual_parent_hash,
            expected_source_graph_semantic_hash=expected_graph_hash,
            actual_source_graph_semantic_hash=actual_graph_hash,
            stored_canonical_json_sha256=stored_canonical_hash,
            recomputed_canonical_json_sha256=None,
            recomputed_plan_id=None,
            recomputed_plan=None,
        )

    try:
        recomputed = plan_graph_delta(source, parent_selector, decomposition_result)
    except GraphDeltaPlanningError as exc:
        return GraphApplyPlanResult(
            status="recompute_mismatch",
            reason=(
                "Source identity is fresh, but plan_graph_delta recomputation failed: "
                f"{_bounded_detail(exc)}"
            ),
            failed_authorities=("plan_graph_delta_recompute",),
            parent_task_id=parent_task_id,
            stored_plan_id=stored_plan_id,
            expected_parent_semantic_hash=expected_parent_hash,
            actual_parent_semantic_hash=actual_parent_hash,
            expected_source_graph_semantic_hash=expected_graph_hash,
            actual_source_graph_semantic_hash=actual_graph_hash,
            stored_canonical_json_sha256=stored_canonical_hash,
            recomputed_canonical_json_sha256=None,
            recomputed_plan_id=None,
            recomputed_plan=None,
        )

    recomputed_canonical_json = recomputed.canonical_json()
    recomputed_canonical_hash = _canonical_json_sha256(recomputed_canonical_json)
    if recomputed_canonical_json != stored_canonical_json:
        return GraphApplyPlanResult(
            status="recompute_mismatch",
            reason=(
                "Source identity is fresh, but the recomputed "
                "GraphDeltaPlan.canonical_json() differs from the stored reviewed plan "
                f"(stored SHA-256 {stored_canonical_hash}, recomputed SHA-256 "
                f"{recomputed_canonical_hash})."
            ),
            failed_authorities=("graph_delta_canonical_json",),
            parent_task_id=parent_task_id,
            stored_plan_id=stored_plan_id,
            expected_parent_semantic_hash=expected_parent_hash,
            actual_parent_semantic_hash=actual_parent_hash,
            expected_source_graph_semantic_hash=expected_graph_hash,
            actual_source_graph_semantic_hash=actual_graph_hash,
            stored_canonical_json_sha256=stored_canonical_hash,
            recomputed_canonical_json_sha256=recomputed_canonical_hash,
            recomputed_plan_id=recomputed.plan_id,
            recomputed_plan=None,
        )

    return GraphApplyPlanResult(
        status="fresh",
        reason=(
            "Current source identity matches and deterministic recomputation exactly "
            "matches the stored reviewed GraphDeltaPlan."
        ),
        failed_authorities=(),
        parent_task_id=parent_task_id,
        stored_plan_id=stored_plan_id,
        expected_parent_semantic_hash=expected_parent_hash,
        actual_parent_semantic_hash=actual_parent_hash,
        expected_source_graph_semantic_hash=expected_graph_hash,
        actual_source_graph_semantic_hash=actual_graph_hash,
        stored_canonical_json_sha256=stored_canonical_hash,
        recomputed_canonical_json_sha256=recomputed_canonical_hash,
        recomputed_plan_id=recomputed.plan_id,
        recomputed_plan=recomputed,
    )
