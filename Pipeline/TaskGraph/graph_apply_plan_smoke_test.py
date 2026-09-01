from __future__ import annotations

import builtins
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent
for path in (str(HERE), str(PIPELINE)):
    if path not in sys.path:
        sys.path.insert(0, path)

import graph_apply_plan
from decomposition_graph_semantics import validate_decomposition_graph_semantics
from graph_apply_plan import GraphApplyPlanningError, plan_graph_apply
from graph_delta import (
    GraphDeltaPlan,
    GraphDeltaPlanningError,
    plan_graph_delta,
    semantic_json_sha256,
)
from graph_delta_smoke_test import make_plan, replace_parent, task, validated_result
from persistent_work_graph import PersistentWorkGraph
from work_graph_transform import WorkGraphPlan
from work_graph_validate import validate_work_graph_plan


def snapshot_plan(plan: WorkGraphPlan) -> str:
    return json.dumps(
        {
            "id_map": plan.id_map,
            "tasks": plan.tasks,
            "resource_groups": plan.resource_groups,
            "project_requirements": plan.project_requirements,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def tampered_plan(stored: GraphDeltaPlan, field: str, value: str) -> GraphDeltaPlan:
    payload = stored.to_dict()
    payload[field] = value
    return GraphDeltaPlan.from_payload(payload)


def source_with_higher_task_id(source: WorkGraphPlan) -> WorkGraphPlan:
    added = task(
        "NSC-100",
        "unrelated-future-work",
        "implementation",
        "NSC-001",
        "single_agent",
        "concrete",
    )
    id_map = deepcopy(source.id_map)
    id_map[added["reconciliation_key"]] = added["id"]
    changed = WorkGraphPlan(
        id_map=id_map,
        tasks=(*deepcopy(source.tasks), added),
        resource_groups=deepcopy(source.resource_groups),
        project_requirements=deepcopy(source.project_requirements),
    )
    validate_work_graph_plan(changed)
    validate_decomposition_graph_semantics(changed)
    return changed


def source_without_reviewed_parent(source: WorkGraphPlan) -> WorkGraphPlan:
    removed_ids = {"NSC-030", "NSC-042"}
    tasks = tuple(
        deepcopy(task_payload)
        for task_payload in source.tasks
        if task_payload["id"] not in removed_ids
    )
    changed = WorkGraphPlan(
        id_map={task_payload["reconciliation_key"]: task_payload["id"] for task_payload in tasks},
        tasks=tasks,
        resource_groups=(
            {
                "resource_key": "logical:shared",
                "work_ids": ["NSC-010"],
                "reconciliation_keys": ["existing-runtime"],
            },
        ),
        project_requirements=deepcopy(source.project_requirements),
    )
    validate_work_graph_plan(changed)
    validate_decomposition_graph_semantics(changed)
    return changed


def selector_for_task(source: WorkGraphPlan, task_id: str) -> dict[str, object]:
    selected = next(task_payload for task_payload in source.tasks if task_payload["id"] == task_id)
    return {
        "task_id": selected["id"],
        "contract_revision": selected["contract_revision"],
        "contract_sha256": semantic_json_sha256(selected),
    }


def expect_apply_error(callable_, fragment: str) -> GraphApplyPlanningError:
    try:
        callable_()
    except GraphApplyPlanningError as exc:
        assert fragment.lower() in str(exc).lower(), str(exc)
        return exc
    raise AssertionError(
        f"Expected GraphApplyPlanningError containing {fragment!r}"
    )


def main() -> int:
    source = make_plan()
    result = validated_result(source)
    selector = result.parent_task
    stored = plan_graph_delta(source, selector, result)

    source_before = snapshot_plan(source)
    result_before = result.canonical_json()
    selector_before = selector.to_dict()
    stored_before = stored.canonical_json()

    # Slice 1 acceptance: a matching reviewed plan is fresh and supplies only
    # the exact recomputed immutable plan for later materialization.
    fresh = plan_graph_apply(source, selector, result, stored)
    assert fresh.status == "fresh"
    assert fresh.failed_authorities == ()
    assert fresh.recomputed_plan is not None
    assert fresh.recomputed_plan is not stored
    assert fresh.recomputed_plan_id == stored.plan_id
    assert fresh.recomputed_plan.canonical_json() == stored.canonical_json()
    assert fresh.actual_parent_semantic_hash == fresh.expected_parent_semantic_hash
    assert (
        fresh.actual_source_graph_semantic_hash
        == fresh.expected_source_graph_semantic_hash
    )
    assert (
        fresh.stored_canonical_json_sha256
        == fresh.recomputed_canonical_json_sha256
    )
    assert fresh.stored_canonical_json_sha256 == hashlib.sha256(
        stored.canonical_json().encode("utf-8")
    ).hexdigest()

    # PersistentWorkGraph is only a validated wrapper for the same in-memory
    # plan at this boundary and must produce identical fresh semantics.
    persistent_source = PersistentWorkGraph(
        plan=source,
        marker={"bootstrap_status": "synthetic"},
        validation=validate_work_graph_plan(source),
    )
    persistent_fresh = plan_graph_apply(
        persistent_source, selector, result, stored
    )
    assert persistent_fresh == fresh

    # The selector is caller authority for choosing the stored reviewed plan.
    # Pairing another valid task selector with this plan is an API-contract
    # failure before source hashes, stale recovery, or recomputation are used.
    other_parent_selector = selector_for_task(source, "NSC-010")
    with (
        patch.object(
            graph_apply_plan,
            "semantic_json_sha256",
            side_effect=AssertionError("mismatched selector reached source hashing"),
        ) as source_hashing,
        patch.object(
            graph_apply_plan,
            "_stale_reason",
            side_effect=AssertionError("mismatched selector reached stale recovery"),
        ) as stale_recovery,
        patch.object(
            graph_apply_plan,
            "plan_graph_delta",
            side_effect=AssertionError("mismatched selector reached recomputation"),
        ) as recompute,
    ):
        selector_pairing_error = expect_apply_error(
            lambda: plan_graph_apply(
                source, other_parent_selector, result, stored
            ),
            "does not match the stored reviewed GraphDeltaPlan parent identity",
    )
    assert "task ID" in str(selector_pairing_error)
    assert "contract revision" in str(selector_pairing_error)
    source_hashing.assert_not_called()
    stale_recovery.assert_not_called()
    recompute.assert_not_called()

    # All public input guards use GraphApplyPlanningError. Malformed stored
    # review snapshots fail closed without leaking JSONDecodeError/AttributeError.
    expect_apply_error(
        lambda: plan_graph_apply(object(), selector, result, stored),
        "source_graph",
    )
    expect_apply_error(
        lambda: plan_graph_apply(source, selector, result, object()),
        "stored_graph_delta",
    )
    expect_apply_error(
        lambda: plan_graph_apply(
            source, {"task_id": "NSC-042"}, result, stored
        ),
        "task_id/revision/hash identity",
    )
    non_object_stored = GraphDeltaPlan.from_payload(["not", "an", "object"])
    expect_apply_error(
        lambda: plan_graph_apply(
            source, selector, result, non_object_stored
        ),
        "payload must be a JSON object",
    )
    corrupt_stored = GraphDeltaPlan("{truncated-json")
    expect_apply_error(
        lambda: plan_graph_apply(source, selector, result, corrupt_stored),
        "corrupt or truncated",
    )
    missing_identity_payload = stored.to_dict()
    del missing_identity_payload["parent_before_summary"]["task_id"]
    missing_identity_stored = GraphDeltaPlan.from_payload(
        missing_identity_payload
    )
    expect_apply_error(
        lambda: plan_graph_apply(
            source, selector, result, missing_identity_stored
        ),
        "parent_before_summary.task_id",
    )

    # The parent and whole-graph bindings are independent gates. Neither stale
    # outcome may enter deterministic recomputation.
    changed_parent_source = replace_parent(
        source,
        lambda parent: parent.__setitem__("title", "Changed after review"),
    )
    validate_work_graph_plan(changed_parent_source)
    validate_decomposition_graph_semantics(changed_parent_source)
    with patch.object(
        graph_apply_plan,
        "plan_graph_delta",
        side_effect=AssertionError("stale parent source was recomputed"),
    ):
        changed_parent = plan_graph_apply(
            changed_parent_source, selector, result, stored
        )
    assert changed_parent.status == "stale_proposal"
    assert changed_parent.failed_authorities == (
        "parent_semantic_hash",
        "source_graph_semantic_hash",
    )
    assert changed_parent.reason == (
        "Stored reviewed GraphDeltaPlan is stale because the current parent "
        "semantic hash does not match the stored reviewed plan and the current "
        "whole-graph semantic hash does not match the stored reviewed plan."
    )
    assert changed_parent.recomputed_plan is None

    stale_graph_delta = tampered_plan(
        stored, "source_graph_semantic_hash", "0" * 64
    )
    with patch.object(
        graph_apply_plan,
        "plan_graph_delta",
        side_effect=AssertionError("stale graph was recomputed"),
    ):
        stale_graph = plan_graph_apply(source, selector, result, stale_graph_delta)
    assert stale_graph.status == "stale_proposal"
    assert stale_graph.failed_authorities == ("source_graph_semantic_hash",)
    assert stale_graph.recomputed_plan is None
    assert stale_graph.recomputed_plan_id is None
    assert (
        stale_graph.actual_parent_semantic_hash
        == stale_graph.expected_parent_semantic_hash
    )

    missing_parent_source = source_without_reviewed_parent(source)
    with patch.object(
        graph_apply_plan,
        "plan_graph_delta",
        side_effect=AssertionError("missing parent source was recomputed"),
    ):
        missing_parent = plan_graph_apply(
            missing_parent_source, selector, result, stored
        )
    assert missing_parent.status == "stale_proposal"
    assert missing_parent.failed_authorities == (
        "parent_semantic_hash",
        "source_graph_semantic_hash",
    )
    assert missing_parent.reason == (
        "Stored reviewed GraphDeltaPlan is stale because reviewed parent task "
        "NSC-042 is missing from the current source graph and the current "
        "whole-graph semantic hash does not match the stored reviewed plan."
    )
    assert missing_parent.actual_parent_semantic_hash is None
    assert missing_parent.recomputed_plan is None

    # Once source identity is proven fresh, deterministic-planning failure is
    # a recompute mismatch with bounded diagnostics and no mutation payload.
    recompute_failure_text = "synthetic recomputation failure " + ("x" * 1000)
    with patch.object(
        graph_apply_plan,
        "plan_graph_delta",
        side_effect=GraphDeltaPlanningError(recompute_failure_text),
    ):
        recompute_failure = plan_graph_apply(
            source, selector, result, stored
        )
    assert recompute_failure.status == "recompute_mismatch"
    assert recompute_failure.failed_authorities == (
        "plan_graph_delta_recompute",
    )
    assert "plan_graph_delta recomputation failed" in recompute_failure.reason
    assert "synthetic recomputation failure" in recompute_failure.reason
    assert len(recompute_failure.reason) < 400
    assert recompute_failure.recomputed_plan is None
    assert recompute_failure.recomputed_plan_id is None
    assert recompute_failure.recomputed_canonical_json_sha256 is None

    # A stored-plan change outside the source-identity fields reaches the
    # independent exact canonical comparison and is not misreported as stale.
    mismatched_delta = tampered_plan(stored, "parent_after_hash", "f" * 64)
    mismatch = plan_graph_apply(source, selector, result, mismatched_delta)
    assert mismatch.status == "recompute_mismatch"
    assert mismatch.failed_authorities == ("graph_delta_canonical_json",)
    assert mismatch.recomputed_plan is None
    assert mismatch.recomputed_plan_id == stored.plan_id
    assert mismatch.stored_plan_id == stored.plan_id
    assert (
        mismatch.actual_parent_semantic_hash
        == mismatch.expected_parent_semantic_hash
    )
    assert (
        mismatch.actual_source_graph_semantic_hash
        == mismatch.expected_source_graph_semantic_hash
    )
    assert (
        mismatch.stored_canonical_json_sha256
        != mismatch.recomputed_canonical_json_sha256
    )

    # Advancing unrelated graph state would shift allocation if D1B were run
    # again. D1C must instead reject the old reviewed allocation before calling
    # plan_graph_delta and must never accept the shifted candidate silently.
    advanced_source = source_with_higher_task_id(source)
    shifted = plan_graph_delta(advanced_source, selector, result)
    assert shifted.allocated_local_key_to_task_id == {
        "runtime-core": "NSC-101",
        "runtime-integration": "NSC-102",
    }
    assert (
        shifted.allocated_local_key_to_task_id
        != stored.allocated_local_key_to_task_id
    )
    with patch.object(
        graph_apply_plan,
        "plan_graph_delta",
        side_effect=AssertionError("stale proposal was silently reallocated"),
    ) as recompute:
        stale_allocation = plan_graph_apply(
            advanced_source, selector, result, stored
        )
    recompute.assert_not_called()
    assert stale_allocation.status == "stale_proposal"
    assert stale_allocation.failed_authorities == (
        "source_graph_semantic_hash",
    )
    assert stale_allocation.recomputed_plan is None
    assert stored.allocated_local_key_to_task_id == {
        "runtime-core": "NSC-043",
        "runtime-integration": "NSC-044",
    }

    # Repeated calls are deterministic, perform no filesystem I/O, and leave
    # every caller-owned source/review object unchanged.
    repeat = plan_graph_apply(source, selector, result, stored)
    assert repeat == fresh
    with patch.object(
        builtins,
        "open",
        side_effect=AssertionError("graph apply preflight attempted filesystem I/O"),
    ):
        no_io = plan_graph_apply(source, selector, result, stored)
    assert no_io == fresh
    assert snapshot_plan(source) == source_before
    assert result.canonical_json() == result_before
    assert selector.to_dict() == selector_before
    assert stored.canonical_json() == stored_before

    print("graph_apply_plan_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
