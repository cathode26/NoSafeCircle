from __future__ import annotations

import json
import sys
import tempfile
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent
for path in (str(HERE), str(PIPELINE)):
    if path not in sys.path:
        sys.path.insert(0, path)

import graph_apply_materialize
from decomposition_graph_semantics import (
    DecompositionGraphSemanticsError,
    validate_decomposition_graph_semantics,
)
from graph_apply_materialize import (
    STAGING_PREFIX,
    GraphApplyMaterializationError,
    GraphApplyPublicationBoundary,
    materialize_graph_apply,
)
from graph_apply_plan import GraphApplyPlanResult, plan_graph_apply
from graph_delta import GraphDeltaPlan, plan_graph_delta
from graph_delta_smoke_test import make_plan, validated_result
from persistent_work_graph import (
    PersistentWorkGraph,
    PersistentWorkGraphError,
    load_persistent_work_graph,
)
from work_graph_persist import persist_work_graph, sha256_bytes
from work_graph_transform import WorkGraphPlan
from work_graph_validate import validate_work_graph_plan


EXPECTED_PUBLICATION_ORDER = (
    "Tasks/NSC-043.yaml",
    "Tasks/NSC-044.yaml",
    "Tasks/NSC-030.yaml",
    "Tasks/NSC-042.yaml",
    "Pipeline/TaskGraph/WORK_ID_MAP.json",
    "Pipeline/TaskGraph/RESOURCE_GROUPS.yaml",
)


@dataclass(frozen=True)
class Fixture:
    root: Path
    source: PersistentWorkGraph
    stored_plan: GraphDeltaPlan
    fresh: GraphApplyPlanResult


def create_fixture(root: Path) -> Fixture:
    source_plan = make_plan()
    inputs = SimpleNamespace(
        approved_by="Synthetic Slice 2 fixture",
        source_reconciliation_run_id="synthetic-reconciliation",
        verification_run_id="synthetic-verification",
    )
    (root / "Pipeline" / "TaskGraph").mkdir(parents=True)
    persist_work_graph(source_plan, inputs, root=root)
    source = load_persistent_work_graph(root)
    result = validated_result(source.plan)
    stored_plan = plan_graph_delta(source, result.parent_task, result)
    fresh = plan_graph_apply(source, result.parent_task, result, stored_plan)
    assert fresh.status == "fresh"
    assert fresh.recomputed_plan is not None
    return Fixture(
        root=root,
        source=source,
        stored_plan=stored_plan,
        fresh=fresh,
    )


def read_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    assert isinstance(value, dict), path
    return value


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def plan_snapshot(plan: WorkGraphPlan) -> str:
    return json.dumps(
        {
            "id_map": plan.id_map,
            "tasks": list(plan.tasks),
            "resource_groups": list(plan.resource_groups),
            "project_requirements": list(plan.project_requirements),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def staging_directories(root: Path) -> list[Path]:
    return sorted(root.glob(f"{STAGING_PREFIX}*"))


def expect_materialization_error(
    callable_,
    fragment: str,
) -> GraphApplyMaterializationError:
    try:
        callable_()
    except GraphApplyMaterializationError as exc:
        assert fragment.lower() in str(exc).lower(), str(exc)
        return exc
    raise AssertionError(
        f"Expected GraphApplyMaterializationError containing {fragment!r}"
    )


def changed_paths(
    before: dict[str, bytes],
    after: dict[str, bytes],
) -> set[str]:
    return {
        relative
        for relative in set(before) | set(after)
        if before.get(relative) != after.get(relative)
    }


def task_map(tasks) -> dict[str, dict]:
    return {task["id"]: task for task in tasks}


def raw_plan_from_repository(root: Path) -> WorkGraphPlan:
    tasks = tuple(
        read_object(path) for path in sorted((root / "Tasks").glob("NSC-*.yaml"))
    )
    taskgraph = root / "Pipeline" / "TaskGraph"
    return WorkGraphPlan(
        id_map=read_object(taskgraph / "WORK_ID_MAP.json")["id_map"],
        tasks=tasks,
        resource_groups=tuple(
            read_object(taskgraph / "RESOURCE_GROUPS.yaml")["resource_groups"]
        ),
        project_requirements=tuple(
            read_object(taskgraph / "PROJECT_REQUIREMENTS.yaml")["requirements"]
        ),
    )


def verify_d1c_child_orphan_semantics() -> None:
    with tempfile.TemporaryDirectory() as temp:
        fixture = create_fixture(Path(temp))
        overlay = deepcopy(fixture.fresh.recomputed_plan.proposed_graph_overlay)
        modern_plan = WorkGraphPlan(
            id_map=overlay["id_map"],
            tasks=tuple(overlay["tasks"]),
            resource_groups=tuple(overlay["resource_groups"]),
            project_requirements=tuple(overlay["project_requirements"]),
        )
        parent_id = fixture.fresh.parent_task_id
        plan_id = fixture.stored_plan.plan_id
        modern_tasks = task_map(modern_plan.tasks)
        modern_parent = modern_tasks[parent_id]
        child_ids = modern_parent["decomposition_children"]
        assert len(child_ids) == 2
        assert modern_parent["decomposition_state"] == "decomposed"
        for child_id in child_ids:
            child = modern_tasks[child_id]
            assert child["contract_disposition"] == "active"
            assert child["parent"] == parent_id
            assert child["provenance"]["parent_task_id"] == parent_id
            assert child["provenance"]["graph_delta_plan_id"] == plan_id

        validate_decomposition_graph_semantics(modern_plan)

        for legacy_children in ("absent", None):
            legacy_tasks = deepcopy(modern_plan.tasks)
            legacy_parent = task_map(legacy_tasks)[parent_id]
            if legacy_children == "absent":
                legacy_parent.pop("decomposition_children")
            else:
                legacy_parent["decomposition_children"] = None
            validate_decomposition_graph_semantics(
                replace(modern_plan, tasks=tuple(legacy_tasks))
            )

        omitted_child_id = child_ids[0]
        invalid_tasks = deepcopy(modern_plan.tasks)
        invalid_parent = task_map(invalid_tasks)[parent_id]
        invalid_parent["decomposition_children"] = child_ids[1:]
        try:
            validate_decomposition_graph_semantics(
                replace(modern_plan, tasks=tuple(invalid_tasks))
            )
        except DecompositionGraphSemanticsError as exc:
            detail = str(exc)
            assert "orphaned" in detail.lower(), detail
            assert omitted_child_id in detail, detail
            assert plan_id in detail, detail
            assert parent_id in detail, detail
        else:
            raise AssertionError("Expected modern omitted-child rejection.")

        torn_child = deepcopy(modern_tasks[omitted_child_id])
        torn_plan = replace(
            fixture.source.plan,
            tasks=tuple((*deepcopy(fixture.source.plan.tasks), torn_child)),
        )
        try:
            validate_decomposition_graph_semantics(torn_plan)
        except DecompositionGraphSemanticsError as exc:
            detail = str(exc)
            assert "orphaned" in detail.lower(), detail
            assert omitted_child_id in detail, detail
            assert plan_id in detail, detail
            assert parent_id in detail, detail
        else:
            raise AssertionError("Expected torn-publication child rejection.")


def verify_non_fresh_refusal() -> None:
    with tempfile.TemporaryDirectory() as temp:
        fixture = create_fixture(Path(temp))
        before = file_snapshot(fixture.root)
        refused_results = (
            replace(
                fixture.fresh,
                status="stale_proposal",
                reason="synthetic stale result",
                failed_authorities=("source_graph_semantic_hash",),
                recomputed_canonical_json_sha256=None,
                recomputed_plan_id=None,
                recomputed_plan=None,
            ),
            replace(
                fixture.fresh,
                status="recompute_mismatch",
                reason="synthetic mismatch result",
                failed_authorities=("graph_delta_canonical_json",),
                recomputed_plan=None,
            ),
            replace(fixture.fresh, recomputed_plan=None),
        )
        for refused in refused_results:
            expect_materialization_error(
                lambda refused=refused: materialize_graph_apply(
                    refused,
                    fixture.root,
                ),
                "requires Slice 1 status 'fresh'"
                if refused.status != "fresh"
                else "non-null exact recomputed_plan",
            )
            assert file_snapshot(fixture.root) == before
            assert staging_directories(fixture.root) == []


def verify_prepublication_failures() -> None:
    with tempfile.TemporaryDirectory() as temp:
        fixture = create_fixture(Path(temp))
        before = file_snapshot(fixture.root)
        boundary_events: list[GraphApplyPublicationBoundary] = []

        def fail_before_publication(boundary: GraphApplyPublicationBoundary) -> None:
            boundary_events.append(boundary)
            if boundary.phase == "before_publication":
                raise RuntimeError("injected pre-publication failure")

        error = expect_materialization_error(
            lambda: materialize_graph_apply(
                fixture.fresh,
                fixture.root,
                publication_boundary_hook=fail_before_publication,
            ),
            "before the first target replacement",
        )
        assert error.published_paths == ()
        assert [event.phase for event in boundary_events] == ["before_publication"]
        assert file_snapshot(fixture.root) == before
        assert staging_directories(fixture.root) == []

    with tempfile.TemporaryDirectory() as temp:
        fixture = create_fixture(Path(temp))
        before = file_snapshot(fixture.root)
        boundary_events = []
        with patch.object(
            graph_apply_materialize,
            "validate_decomposition_graph_semantics",
            side_effect=DecompositionGraphSemanticsError(
                "injected full staged graph validation failure"
            ),
        ):
            expect_materialization_error(
                lambda: materialize_graph_apply(
                    fixture.fresh,
                    fixture.root,
                    publication_boundary_hook=boundary_events.append,
                ),
                "staged graph validation failure",
            )
        assert boundary_events == []
        assert file_snapshot(fixture.root) == before
        assert staging_directories(fixture.root) == []


def verify_partial_publication_rejection() -> None:
    with tempfile.TemporaryDirectory() as temp:
        fixture = create_fixture(Path(temp))
        before = file_snapshot(fixture.root)
        first_child = fixture.fresh.recomputed_plan.proposed_child_contracts[0]
        child_id = first_child["id"]
        plan_id = fixture.stored_plan.plan_id

        def fail_after_first_child(boundary: GraphApplyPublicationBoundary) -> None:
            if (
                boundary.phase == "after_replacement"
                and boundary.replacements_completed == 1
            ):
                raise RuntimeError("injected interruption after first replacement")

        error = expect_materialization_error(
            lambda: materialize_graph_apply(
                fixture.fresh,
                fixture.root,
                publication_boundary_hook=fail_after_first_child,
            ),
            plan_id,
        )
        assert error.published_paths == (f"Tasks/{child_id}.yaml",)
        assert child_id in str(error)
        assert changed_paths(before, file_snapshot(fixture.root)) == {
            f"Tasks/{child_id}.yaml"
        }
        assert (fixture.root / "Tasks" / f"{child_id}.yaml").is_file()
        assert staging_directories(fixture.root) == []

        try:
            load_persistent_work_graph(fixture.root)
        except PersistentWorkGraphError as exc:
            assert "validation failed" in str(exc).lower(), str(exc)
        else:
            raise AssertionError("Expected partial persistent graph rejection.")

        partial_plan = raw_plan_from_repository(fixture.root)
        try:
            validate_decomposition_graph_semantics(partial_plan)
        except DecompositionGraphSemanticsError as exc:
            detail = str(exc)
            assert "orphaned" in detail.lower(), detail
            assert child_id in detail, detail
            assert plan_id in detail, detail
            assert fixture.fresh.parent_task_id in detail, detail
        else:
            raise AssertionError("Expected orphaned D1C child rejection.")


def clean_apply_once() -> tuple[
    tuple[str, ...],
    tuple[tuple[str, str], ...],
    dict[str, bytes],
]:
    with tempfile.TemporaryDirectory() as temp:
        fixture = create_fixture(Path(temp))
        validate_work_graph_plan(fixture.source.plan)
        validate_decomposition_graph_semantics(fixture.source.plan)
        before = file_snapshot(fixture.root)
        initial_id_map = read_object(
            fixture.root / "Pipeline" / "TaskGraph" / "WORK_ID_MAP.json"
        )
        initial_resource_groups = read_object(
            fixture.root / "Pipeline" / "TaskGraph" / "RESOURCE_GROUPS.yaml"
        )
        unchanged_task_ids = {"NSC-001", "NSC-010", "NSC-020"}
        unchanged_state = {
            task_id: (
                (fixture.root / "Tasks" / f"{task_id}.yaml").read_bytes(),
                (fixture.root / "Tasks" / f"{task_id}.yaml").stat().st_mtime_ns,
            )
            for task_id in unchanged_task_ids
        }
        source_before = plan_snapshot(fixture.source.plan)
        stored_before = fixture.stored_plan.canonical_json()
        recomputed_before = fixture.fresh.recomputed_plan.canonical_json()
        fresh_before = fixture.fresh
        events: list[tuple[str, str | None]] = []
        real_work_validation = graph_apply_materialize.validate_work_graph_plan
        real_semantics_validation = (
            graph_apply_materialize.validate_decomposition_graph_semantics
        )

        def record_work_validation(plan: WorkGraphPlan):
            events.append(("validate_work_graph_plan", None))
            return real_work_validation(plan)

        def record_semantics_validation(plan: WorkGraphPlan) -> None:
            events.append(("validate_decomposition_graph_semantics", None))
            real_semantics_validation(plan)

        def record_boundary(boundary: GraphApplyPublicationBoundary) -> None:
            events.append((boundary.phase, boundary.relative_path))

        with (
            patch.object(
                graph_apply_materialize,
                "validate_work_graph_plan",
                side_effect=record_work_validation,
            ),
            patch.object(
                graph_apply_materialize,
                "validate_decomposition_graph_semantics",
                side_effect=record_semantics_validation,
            ),
        ):
            result = materialize_graph_apply(
                fixture.fresh,
                fixture.root,
                publication_boundary_hook=record_boundary,
            )

        assert result.status == "materialized"
        assert result.plan_id == fixture.stored_plan.plan_id
        assert result.parent_task_id == "NSC-042"
        assert result.changed_paths == EXPECTED_PUBLICATION_ORDER
        assert result.publication_order == EXPECTED_PUBLICATION_ORDER
        assert events[:3] == [
            ("validate_work_graph_plan", None),
            ("validate_decomposition_graph_semantics", None),
            ("before_publication", None),
        ]
        assert tuple(
            relative
            for phase, relative in events
            if phase == "after_replacement"
        ) == EXPECTED_PUBLICATION_ORDER

        after = file_snapshot(fixture.root)
        assert changed_paths(before, after) == set(EXPECTED_PUBLICATION_ORDER)
        assert staging_directories(fixture.root) == []
        for task_id, (expected_bytes, expected_mtime) in unchanged_state.items():
            path = fixture.root / "Tasks" / f"{task_id}.yaml"
            assert path.read_bytes() == expected_bytes
            assert path.stat().st_mtime_ns == expected_mtime

        overlay = fixture.fresh.recomputed_plan.proposed_graph_overlay
        overlay_tasks = task_map(overlay["tasks"])
        for task_id in ("NSC-043", "NSC-044", "NSC-030", "NSC-042"):
            assert read_object(
                fixture.root / "Tasks" / f"{task_id}.yaml"
            ) == overlay_tasks[task_id]

        expected_id_map = deepcopy(initial_id_map)
        expected_id_map["id_map"] = overlay["id_map"]
        assert read_object(
            fixture.root / "Pipeline" / "TaskGraph" / "WORK_ID_MAP.json"
        ) == expected_id_map
        expected_resource_groups = deepcopy(initial_resource_groups)
        expected_resource_groups["resource_groups"] = overlay["resource_groups"]
        assert read_object(
            fixture.root / "Pipeline" / "TaskGraph" / "RESOURCE_GROUPS.yaml"
        ) == expected_resource_groups

        output_hashes = dict(result.output_sha256)
        assert tuple(output_hashes) == EXPECTED_PUBLICATION_ORDER
        for relative, expected_hash in output_hashes.items():
            assert sha256_bytes((fixture.root / relative).read_bytes()) == expected_hash

        round_trip = load_persistent_work_graph(fixture.root)
        validate_decomposition_graph_semantics(round_trip.plan)
        assert task_map(round_trip.plan.tasks) == overlay_tasks
        assert round_trip.plan.id_map == overlay["id_map"]
        assert list(round_trip.plan.resource_groups) == overlay["resource_groups"]
        assert list(round_trip.plan.project_requirements) == overlay[
            "project_requirements"
        ]

        assert plan_snapshot(fixture.source.plan) == source_before
        assert fixture.stored_plan.canonical_json() == stored_before
        assert fixture.fresh.recomputed_plan.canonical_json() == recomputed_before
        assert fixture.fresh == fresh_before
        return result.publication_order, result.output_sha256, after


def main() -> int:
    verify_d1c_child_orphan_semantics()
    verify_non_fresh_refusal()
    verify_prepublication_failures()
    verify_partial_publication_rejection()

    first_order, first_hashes, first_files = clean_apply_once()
    second_order, second_hashes, second_files = clean_apply_once()
    assert first_order == second_order == EXPECTED_PUBLICATION_ORDER
    assert first_hashes == second_hashes
    assert first_files == second_files

    print("graph_apply_materialize_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
