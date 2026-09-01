"""Local changed-file materialization for a fresh Stage D1C apply plan."""

from __future__ import annotations

import os
import shutil
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from decomposition_graph_semantics import validate_decomposition_graph_semantics
from graph_apply_plan import GraphApplyPlanResult
from graph_delta import (
    GraphDeltaPlan,
    NSC_ID_RE,
    _plan_payload,
    semantic_json_sha256,
)
from persistent_work_graph import load_persistent_work_graph
from work_graph_persist import (
    canonical_json_text,
    read_json,
    sha256_bytes,
    write_text,
)
from work_graph_transform import WorkGraphPlan
from work_graph_validate import validate_work_graph_plan


STAGING_PREFIX = ".taskgraph-apply-"
PublicationBoundaryPhase = Literal["before_publication", "after_replacement"]


class GraphApplyMaterializationError(RuntimeError):
    """Raised when local graph materialization cannot complete safely."""

    def __init__(self, message: str, *, published_paths: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.published_paths = published_paths


@dataclass(frozen=True)
class GraphApplyPublicationBoundary:
    """Deterministic observation/fault-injection point around ordered publication."""

    phase: PublicationBoundaryPhase
    replacements_completed: int
    relative_path: str | None


PublicationBoundaryHook = Callable[[GraphApplyPublicationBoundary], None]


@dataclass(frozen=True)
class GraphApplyMaterializationResult:
    """Immutable summary of one complete local changed-file publication."""

    status: Literal["materialized"]
    plan_id: str
    parent_task_id: str
    changed_paths: tuple[str, ...]
    publication_order: tuple[str, ...]
    output_sha256: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _Artifact:
    relative_path: Path
    text: str


def _bounded_detail(error: BaseException, limit: int = 500) -> str:
    detail = " ".join(str(error).split()) or type(error).__name__
    if len(detail) <= limit:
        return detail
    return detail[: limit - 3] + "..."


def _require_fresh_result(result: GraphApplyPlanResult) -> GraphDeltaPlan:
    if type(result) is not GraphApplyPlanResult:
        raise GraphApplyMaterializationError(
            "slice1_result must be an exact GraphApplyPlanResult."
        )
    if result.status != "fresh":
        raise GraphApplyMaterializationError(
            "Local materialization requires Slice 1 status 'fresh'; "
            f"received {result.status!r}."
        )
    plan = result.recomputed_plan
    if type(plan) is not GraphDeltaPlan:
        raise GraphApplyMaterializationError(
            "A fresh Slice 1 result must carry a non-null exact recomputed_plan."
        )
    if result.failed_authorities:
        raise GraphApplyMaterializationError(
            "A fresh Slice 1 result may not carry failed authorities."
        )
    if (
        result.recomputed_plan_id != plan.plan_id
        or result.stored_plan_id != plan.plan_id
    ):
        raise GraphApplyMaterializationError(
            "Fresh Slice 1 plan identities do not match its recomputed_plan."
        )
    canonical_hash = sha256_bytes(plan.canonical_json().encode("utf-8"))
    if (
        result.recomputed_canonical_json_sha256 != canonical_hash
        or result.stored_canonical_json_sha256 != canonical_hash
    ):
        raise GraphApplyMaterializationError(
            "Fresh Slice 1 canonical plan hashes do not match its recomputed_plan."
        )
    if (
        result.actual_parent_semantic_hash
        != result.expected_parent_semantic_hash
        or result.actual_source_graph_semantic_hash
        != result.expected_source_graph_semantic_hash
        or result.actual_source_graph_semantic_hash
        != plan.source_graph_semantic_hash
    ):
        raise GraphApplyMaterializationError(
            "Fresh Slice 1 source identities are internally inconsistent."
        )
    return plan


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise GraphApplyMaterializationError(f"{label} must be a JSON object.")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise GraphApplyMaterializationError(f"{label} must be a JSON list.")
    return value


def _task_number(task_id: Any, label: str) -> int:
    if type(task_id) is not str:
        raise GraphApplyMaterializationError(f"{label} must be an NSC task ID.")
    match = NSC_ID_RE.fullmatch(task_id)
    if match is None:
        raise GraphApplyMaterializationError(f"{label} must be an NSC task ID.")
    return int(match.group(1))


def _plan_components(
    plan: GraphDeltaPlan,
    expected_parent_id: str,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    tuple[str, ...],
    tuple[str, ...],
]:
    payload = _require_object(plan.to_dict(), "recomputed_plan")
    overlay = _require_object(
        payload.get("proposed_graph_overlay"),
        "recomputed_plan.proposed_graph_overlay",
    )
    for field in ("id_map", "tasks"):
        expected_type = dict if field == "id_map" else list
        if type(overlay.get(field)) is not expected_type:
            raise GraphApplyMaterializationError(
                f"recomputed_plan.proposed_graph_overlay.{field} has the wrong type."
            )
    _require_list(
        overlay.get("resource_groups"),
        "recomputed_plan.proposed_graph_overlay.resource_groups",
    )
    _require_list(
        overlay.get("project_requirements"),
        "recomputed_plan.proposed_graph_overlay.project_requirements",
    )

    children = _require_list(
        payload.get("proposed_child_contracts"),
        "recomputed_plan.proposed_child_contracts",
    )
    child_ids: list[str] = []
    for index, child_value in enumerate(children):
        child = _require_object(
            child_value,
            f"recomputed_plan.proposed_child_contracts[{index}]",
        )
        child_id = child.get("id")
        _task_number(child_id, f"proposed_child_contracts[{index}].id")
        child_ids.append(child_id)
    if not child_ids or len(child_ids) != len(set(child_ids)):
        raise GraphApplyMaterializationError(
            "recomputed_plan.proposed_child_contracts must name unique children."
        )

    inbound_changes = _require_list(
        payload.get("inbound_dependency_changes"),
        "recomputed_plan.inbound_dependency_changes",
    )
    dependent_ids: list[str] = []
    for index, change_value in enumerate(inbound_changes):
        change = _require_object(
            change_value,
            f"recomputed_plan.inbound_dependency_changes[{index}]",
        )
        dependent_id = change.get("dependent_task_id")
        _task_number(
            dependent_id,
            f"inbound_dependency_changes[{index}].dependent_task_id",
        )
        dependent_ids.append(dependent_id)
    if len(dependent_ids) != len(set(dependent_ids)):
        raise GraphApplyMaterializationError(
            "recomputed_plan.inbound_dependency_changes names duplicate dependents."
        )

    parent_summary = _require_object(
        payload.get("parent_after_summary"),
        "recomputed_plan.parent_after_summary",
    )
    parent_id = parent_summary.get("task_id")
    _task_number(parent_id, "recomputed_plan.parent_after_summary.task_id")
    if parent_id != expected_parent_id:
        raise GraphApplyMaterializationError(
            "Fresh Slice 1 parent identity differs from the recomputed plan parent."
        )

    return (
        payload,
        overlay,
        tuple(sorted(child_ids, key=lambda value: _task_number(value, "child ID"))),
        tuple(
            sorted(dependent_ids, key=lambda value: _task_number(value, "dependent ID"))
        ),
    )


def _task_by_id(tasks: Any, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, task_value in enumerate(tasks):
        task = _require_object(task_value, f"{label}[{index}]")
        task_id = task.get("id")
        _task_number(task_id, f"{label}[{index}].id")
        if task_id in result:
            raise GraphApplyMaterializationError(
                f"{label} contains duplicate task {task_id}."
            )
        result[task_id] = task
    return result


def _validate_exact_task_change_set(
    current: WorkGraphPlan,
    overlay: dict[str, Any],
    *,
    parent_id: str,
    child_ids: tuple[str, ...],
    dependent_ids: tuple[str, ...],
    proposed_children: list[Any],
) -> dict[str, dict[str, Any]]:
    current_by_id = _task_by_id(current.tasks, "current tasks")
    proposed_by_id = _task_by_id(overlay["tasks"], "proposed overlay tasks")
    current_ids = set(current_by_id)
    proposed_ids = set(proposed_by_id)
    added_ids = proposed_ids - current_ids
    removed_ids = current_ids - proposed_ids
    changed_existing_ids = {
        task_id
        for task_id in current_ids & proposed_ids
        if current_by_id[task_id] != proposed_by_id[task_id]
    }
    expected_changed_existing = {parent_id, *dependent_ids}
    if added_ids != set(child_ids):
        raise GraphApplyMaterializationError(
            "The recomputed plan's added task set differs from its proposed children "
            f"(added={sorted(added_ids)}, children={list(child_ids)})."
        )
    if removed_ids:
        raise GraphApplyMaterializationError(
            f"The recomputed plan unexpectedly removes tasks: {sorted(removed_ids)}."
        )
    if changed_existing_ids != expected_changed_existing:
        raise GraphApplyMaterializationError(
            "The recomputed plan's changed existing task set is not exactly parent plus "
            f"rewritten dependents (changed={sorted(changed_existing_ids)}, "
            f"expected={sorted(expected_changed_existing)})."
        )
    proposed_children_by_id = _task_by_id(
        proposed_children,
        "proposed child contracts",
    )
    if set(proposed_children_by_id) != set(child_ids):
        raise GraphApplyMaterializationError(
            "The recomputed plan's proposed child identities are inconsistent."
        )
    for child_id in child_ids:
        if proposed_by_id[child_id] != proposed_children_by_id[child_id]:
            raise GraphApplyMaterializationError(
                f"Proposed child {child_id} differs between the plan and graph overlay."
            )
    return proposed_by_id


def _metadata_payload(
    current_payload: dict[str, Any],
    field: str,
    value: Any,
) -> dict[str, Any]:
    result = deepcopy(current_payload)
    result[field] = deepcopy(value)
    return result


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        return _require_object(read_json(path), label)
    except GraphApplyMaterializationError:
        raise
    except Exception as exc:
        raise GraphApplyMaterializationError(
            f"Unable to read {label} {path}: {_bounded_detail(exc)}"
        ) from exc


def _artifact_if_changed(
    artifacts: list[_Artifact],
    root: Path,
    relative_path: Path,
    payload: Any,
) -> None:
    text = canonical_json_text(payload)
    target = root / relative_path
    try:
        current_bytes = target.read_bytes()
    except FileNotFoundError:
        current_bytes = None
    except OSError as exc:
        raise GraphApplyMaterializationError(
            f"Unable to inspect target file {target}: {_bounded_detail(exc)}"
        ) from exc
    if current_bytes != text.encode("utf-8"):
        artifacts.append(_Artifact(relative_path=relative_path, text=text))


def _stage_artifacts(
    artifacts: tuple[_Artifact, ...],
    staging_root: Path,
) -> tuple[tuple[str, str], ...]:
    hashes: list[tuple[str, str]] = []
    for artifact in artifacts:
        staged_path = staging_root / artifact.relative_path
        write_text(staged_path, artifact.text)
        expected = sha256_bytes(artifact.text.encode("utf-8"))
        actual = sha256_bytes(staged_path.read_bytes())
        if actual != expected:
            raise GraphApplyMaterializationError(
                f"Staged output hash mismatch for {artifact.relative_path.as_posix()}: "
                f"expected {expected}, got {actual}."
            )
        hashes.append((artifact.relative_path.as_posix(), actual))
    return tuple(hashes)


def _staged_or_target_path(
    root: Path,
    staging_root: Path,
    staged_paths: set[str],
    relative_path: Path,
) -> Path:
    if relative_path.as_posix() in staged_paths:
        return staging_root / relative_path
    return root / relative_path


def _overlay_differences(
    plan: WorkGraphPlan,
    expected_overlay: dict[str, Any],
) -> list[str]:
    differences: list[str] = []
    if plan.id_map != expected_overlay.get("id_map"):
        differences.append("id_map")
    expected_tasks = expected_overlay.get("tasks")
    if type(expected_tasks) is not list or _task_by_id(
        plan.tasks,
        "materialized tasks",
    ) != _task_by_id(expected_tasks, "expected overlay tasks"):
        differences.append("tasks")
    if list(plan.resource_groups) != expected_overlay.get("resource_groups"):
        differences.append("resource_groups")
    if list(plan.project_requirements) != expected_overlay.get("project_requirements"):
        differences.append("project_requirements")
    return differences


def _load_and_validate_staged_graph(
    root: Path,
    staging_root: Path,
    artifacts: tuple[_Artifact, ...],
    expected_overlay: dict[str, Any],
) -> WorkGraphPlan:
    staged_paths = {artifact.relative_path.as_posix() for artifact in artifacts}
    task_paths: dict[str, Path] = {
        path.name: path for path in (root / "Tasks").glob("NSC-*.yaml")
    }
    for artifact in artifacts:
        if artifact.relative_path.parts[:1] != ("Tasks",):
            continue
        task_paths[artifact.relative_path.name] = staging_root / artifact.relative_path

    loaded_tasks: list[dict[str, Any]] = []
    for filename in sorted(task_paths):
        task = _read_object(task_paths[filename], f"staged resulting task {filename}")
        task_id = task.get("id")
        if filename != f"{task_id}.yaml":
            raise GraphApplyMaterializationError(
                f"Staged resulting task filename/id mismatch: {filename} vs {task_id!r}."
            )
        loaded_tasks.append(task)

    taskgraph = Path("Pipeline") / "TaskGraph"
    id_map_payload = _read_object(
        _staged_or_target_path(
            root,
            staging_root,
            staged_paths,
            taskgraph / "WORK_ID_MAP.json",
        ),
        "staged resulting work ID map",
    )
    resource_payload = _read_object(
        _staged_or_target_path(
            root,
            staging_root,
            staged_paths,
            taskgraph / "RESOURCE_GROUPS.yaml",
        ),
        "staged resulting resource groups",
    )
    requirements_payload = _read_object(
        root / taskgraph / "PROJECT_REQUIREMENTS.yaml",
        "current project requirements",
    )
    id_map = _require_object(id_map_payload.get("id_map"), "WORK_ID_MAP.json.id_map")
    resource_groups = _require_list(
        resource_payload.get("resource_groups"),
        "RESOURCE_GROUPS.yaml.resource_groups",
    )
    requirements = _require_list(
        requirements_payload.get("requirements"),
        "PROJECT_REQUIREMENTS.yaml.requirements",
    )
    staged_plan = WorkGraphPlan(
        id_map=deepcopy(id_map),
        tasks=tuple(loaded_tasks),
        resource_groups=tuple(deepcopy(resource_groups)),
        project_requirements=tuple(deepcopy(requirements)),
    )

    validate_work_graph_plan(staged_plan)
    validate_decomposition_graph_semantics(staged_plan)

    differing_sections = _overlay_differences(staged_plan, expected_overlay)
    if differing_sections:
        raise GraphApplyMaterializationError(
            "The fully validated staged graph differs from the recomputed plan overlay "
            f"in sections: {differing_sections}."
        )
    return staged_plan


def _notify_boundary(
    hook: PublicationBoundaryHook | None,
    phase: PublicationBoundaryPhase,
    replacements_completed: int,
    relative_path: str | None,
) -> None:
    if hook is None:
        return
    hook(
        GraphApplyPublicationBoundary(
            phase=phase,
            replacements_completed=replacements_completed,
            relative_path=relative_path,
        )
    )


def materialize_graph_apply(
    slice1_result: GraphApplyPlanResult,
    target_root: Path,
    *,
    publication_boundary_hook: PublicationBoundaryHook | None = None,
) -> GraphApplyMaterializationResult:
    """Stage, fully validate, and locally publish one fresh recomputed plan.

    The function never recomputes planning authority and accepts no parent selector.
    It verifies that ``target_root`` is still the exact whole-graph context already
    proven by Slice 1, then publishes changed files only. Individual ``os.replace``
    calls are atomic; the ordered multi-file publication is deliberately not.
    """

    recomputed_plan = _require_fresh_result(slice1_result)
    root = Path(target_root).resolve()
    if not root.is_dir():
        raise GraphApplyMaterializationError(
            f"target_root must be an existing disposable repository directory: {root}"
        )

    staging_root: Path | None = None
    published_paths: list[str] = []
    try:
        current_graph = load_persistent_work_graph(root)
        current_hash = semantic_json_sha256(_plan_payload(current_graph.plan))
        if current_hash != slice1_result.actual_source_graph_semantic_hash:
            raise GraphApplyMaterializationError(
                "The disposable target graph no longer matches the whole-graph context "
                "already proven fresh by Slice 1."
            )

        payload, overlay, child_ids, dependent_ids = _plan_components(
            recomputed_plan,
            slice1_result.parent_task_id,
        )
        proposed_children = _require_list(
            payload.get("proposed_child_contracts"),
            "recomputed_plan.proposed_child_contracts",
        )
        proposed_by_id = _validate_exact_task_change_set(
            current_graph.plan,
            overlay,
            parent_id=slice1_result.parent_task_id,
            child_ids=child_ids,
            dependent_ids=dependent_ids,
            proposed_children=proposed_children,
        )
        if list(current_graph.plan.project_requirements) != overlay["project_requirements"]:
            raise GraphApplyMaterializationError(
                "The recomputed plan unexpectedly changes project requirements, which are "
                "outside Slice 2 publication authority."
            )

        taskgraph = Path("Pipeline") / "TaskGraph"
        current_id_map_payload = _read_object(
            root / taskgraph / "WORK_ID_MAP.json",
            "current work ID map",
        )
        current_resource_payload = _read_object(
            root / taskgraph / "RESOURCE_GROUPS.yaml",
            "current resource groups",
        )
        if current_id_map_payload.get("id_map") != current_graph.plan.id_map:
            raise GraphApplyMaterializationError(
                "Current WORK_ID_MAP.json differs from the validated source graph."
            )
        if current_resource_payload.get("resource_groups") != list(
            current_graph.plan.resource_groups
        ):
            raise GraphApplyMaterializationError(
                "Current RESOURCE_GROUPS.yaml differs from the validated source graph."
            )

        artifacts: list[_Artifact] = []
        for child_id in child_ids:
            _artifact_if_changed(
                artifacts,
                root,
                Path("Tasks") / f"{child_id}.yaml",
                proposed_by_id[child_id],
            )
        for dependent_id in dependent_ids:
            _artifact_if_changed(
                artifacts,
                root,
                Path("Tasks") / f"{dependent_id}.yaml",
                proposed_by_id[dependent_id],
            )
        parent_id = slice1_result.parent_task_id
        _artifact_if_changed(
            artifacts,
            root,
            Path("Tasks") / f"{parent_id}.yaml",
            proposed_by_id[parent_id],
        )
        _artifact_if_changed(
            artifacts,
            root,
            taskgraph / "WORK_ID_MAP.json",
            _metadata_payload(
                current_id_map_payload,
                "id_map",
                overlay["id_map"],
            ),
        )
        _artifact_if_changed(
            artifacts,
            root,
            taskgraph / "RESOURCE_GROUPS.yaml",
            _metadata_payload(
                current_resource_payload,
                "resource_groups",
                overlay["resource_groups"],
            ),
        )
        artifact_tuple = tuple(artifacts)
        staged_task_ids = {
            artifact.relative_path.stem
            for artifact in artifact_tuple
            if artifact.relative_path.parts[:1] == ("Tasks",)
        }
        if staged_task_ids != {parent_id, *child_ids, *dependent_ids}:
            raise GraphApplyMaterializationError(
                "Changed task staging is not exactly children, rewritten dependents, and parent."
            )
        if (taskgraph / "WORK_ID_MAP.json") not in {
            artifact.relative_path for artifact in artifact_tuple
        }:
            raise GraphApplyMaterializationError(
                "Fresh graph application must change WORK_ID_MAP.json."
            )

        staging_root = Path(
            tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=root)
        )
        output_hashes = _stage_artifacts(artifact_tuple, staging_root)
        _load_and_validate_staged_graph(
            root,
            staging_root,
            artifact_tuple,
            overlay,
        )

        _notify_boundary(
            publication_boundary_hook,
            "before_publication",
            0,
            None,
        )
        for artifact in artifact_tuple:
            relative = artifact.relative_path.as_posix()
            os.replace(staging_root / artifact.relative_path, root / artifact.relative_path)
            published_paths.append(relative)
            _notify_boundary(
                publication_boundary_hook,
                "after_replacement",
                len(published_paths),
                relative,
            )

        materialized_graph = load_persistent_work_graph(root)
        if _overlay_differences(materialized_graph.plan, overlay):
            raise GraphApplyMaterializationError(
                "The fully published graph differs from the recomputed plan overlay."
            )
    except Exception as exc:
        published = tuple(published_paths)
        if published:
            raise GraphApplyMaterializationError(
                "Local graph publication stopped after "
                f"{len(published)} replacement(s) for plan {recomputed_plan.plan_id}; "
                "the disposable target contains a published prefix and was not rolled "
                f"back (published={list(published)}): {_bounded_detail(exc)}",
                published_paths=published,
            ) from exc
        if isinstance(exc, GraphApplyMaterializationError):
            detail = str(exc)
        else:
            detail = _bounded_detail(exc)
        raise GraphApplyMaterializationError(
            "Local graph materialization failed before the first target replacement; "
            f"no target file was published: {detail}"
        ) from exc
    finally:
        if staging_root is not None and staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)

    order = tuple(published_paths)
    return GraphApplyMaterializationResult(
        status="materialized",
        plan_id=recomputed_plan.plan_id,
        parent_task_id=slice1_result.parent_task_id,
        changed_paths=order,
        publication_order=order,
        output_sha256=output_hashes,
    )
