from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from work_graph_transform import WorkGraphPlan
from work_graph_validate import WorkGraphValidationSummary, validate_work_graph_plan

ROOT = Path(__file__).resolve().parents[2]
SERIALIZATION_FORMAT = "yaml_1_2_json_subset"


class PersistentWorkGraphError(RuntimeError):
    """Raised when the live persistent work graph cannot be loaded or trusted."""


@dataclass(frozen=True)
class PersistentWorkGraph:
    plan: WorkGraphPlan
    marker: dict[str, Any]
    validation: WorkGraphValidationSummary

    @property
    def tasks_by_id(self) -> dict[str, dict[str, Any]]:
        return {task["id"]: task for task in self.plan.tasks}

    @property
    def tasks_by_key(self) -> dict[str, dict[str, Any]]:
        return {task["reconciliation_key"]: task for task in self.plan.tasks}


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise PersistentWorkGraphError(f"Missing {label}: {_display_path(path)}")
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise PersistentWorkGraphError(f"Unable to read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PersistentWorkGraphError(f"Expected {label} to contain a JSON object: {path}")
    return value


def _require_text(payload: dict[str, Any], field: str, label: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PersistentWorkGraphError(f"{label}.{field} must be a non-empty string.")
    return value.strip()


def _validate_bootstrap_marker(marker: dict[str, Any], root: Path) -> None:
    if marker.get("schema_version") != "1.0":
        raise PersistentWorkGraphError(
            f"Unsupported bootstrap marker schema: {marker.get('schema_version')!r}"
        )
    if marker.get("bootstrap_status") != "complete":
        raise PersistentWorkGraphError(
            f"Persistent graph bootstrap is not complete: {marker.get('bootstrap_status')!r}"
        )
    if marker.get("serialization_format") != SERIALIZATION_FORMAT:
        raise PersistentWorkGraphError(
            "Unsupported persistent graph serialization format: "
            f"{marker.get('serialization_format')!r}"
        )

    baseline_hashes = marker.get("output_sha256")
    if not isinstance(baseline_hashes, dict) or not baseline_hashes:
        raise PersistentWorkGraphError("Bootstrap marker is missing output_sha256 baseline entries.")

    # These hashes preserve historical bootstrap identity. Live contract bytes
    # legitimately change during approved schema migrations and later contract
    # revisions, so the loader requires the original paths to remain present but
    # does not compare current bytes with the old bootstrap hashes.
    root_resolved = root.resolve()
    for relative_path in baseline_hashes:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise PersistentWorkGraphError("Bootstrap marker contains an invalid baseline path.")
        candidate = (root_resolved / relative_path).resolve()
        try:
            candidate.relative_to(root_resolved)
        except ValueError as exc:
            raise PersistentWorkGraphError(
                f"Bootstrap baseline path escapes repository root: {relative_path!r}"
            ) from exc
        if not candidate.is_file():
            raise PersistentWorkGraphError(
                f"Bootstrap baseline output is missing from the live graph: {relative_path}"
            )


def _load_tasks(tasks_dir: Path) -> tuple[dict[str, Any], ...]:
    if not tasks_dir.is_dir():
        raise PersistentWorkGraphError(f"Persistent Tasks directory does not exist: {tasks_dir}")
    paths = sorted(tasks_dir.glob("NSC-*.yaml"))
    if not paths:
        raise PersistentWorkGraphError("Persistent Tasks directory contains no NSC-*.yaml files.")

    tasks: list[dict[str, Any]] = []
    versions: set[str] = set()
    for path in paths:
        task = _load_json_object(path, "task")
        task_id = _require_text(task, "id", f"task {path.name}")
        if task_id != path.stem:
            raise PersistentWorkGraphError(
                f"Task filename/id mismatch: {path.name} contains id {task_id!r}."
            )
        version = task.get("schema_version")
        if not isinstance(version, str):
            raise PersistentWorkGraphError(f"{task_id}.schema_version must be a string.")
        versions.add(version)
        tasks.append(task)

    if len(versions) != 1:
        raise PersistentWorkGraphError(
            f"Live task graph is partially migrated; found schema versions {sorted(versions)}. "
            "Re-run the idempotent v2 migrator to complete or recover the migration."
        )
    return tuple(tasks)


def load_persistent_work_graph(root: Path = ROOT) -> PersistentWorkGraph:
    taskgraph_dir = root / "Pipeline" / "TaskGraph"
    marker = _load_json_object(
        taskgraph_dir / "BOOTSTRAP_PERSISTED.json",
        "bootstrap completion marker",
    )
    _validate_bootstrap_marker(marker, root)

    id_map_payload = _load_json_object(taskgraph_dir / "WORK_ID_MAP.json", "work ID map")
    requirements_payload = _load_json_object(
        taskgraph_dir / "PROJECT_REQUIREMENTS.yaml", "project requirements"
    )
    resources_payload = _load_json_object(
        taskgraph_dir / "RESOURCE_GROUPS.yaml", "resource groups"
    )

    id_map = id_map_payload.get("id_map")
    if not isinstance(id_map, dict) or not id_map:
        raise PersistentWorkGraphError("WORK_ID_MAP.json contains no id_map object.")
    normalized_id_map: dict[str, str] = {}
    for key, work_id in id_map.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(work_id, str) or not work_id.strip():
            raise PersistentWorkGraphError("WORK_ID_MAP.json contains a blank or non-string mapping.")
        normalized_id_map[key.strip()] = work_id.strip()

    requirements = requirements_payload.get("requirements")
    if not isinstance(requirements, list):
        raise PersistentWorkGraphError("PROJECT_REQUIREMENTS.yaml is missing requirements list.")
    resource_groups = resources_payload.get("resource_groups")
    if not isinstance(resource_groups, list):
        raise PersistentWorkGraphError("RESOURCE_GROUPS.yaml is missing resource_groups list.")

    tasks = _load_tasks(root / "Tasks")
    plan = WorkGraphPlan(
        id_map=normalized_id_map,
        tasks=tasks,
        resource_groups=tuple(resource_groups),
        project_requirements=tuple(requirements),
    )
    try:
        validation = validate_work_graph_plan(plan)
    except Exception as exc:
        raise PersistentWorkGraphError(f"Persistent work graph validation failed: {exc}") from exc
    return PersistentWorkGraph(plan=plan, marker=marker, validation=validation)
