from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from work_graph_transform import WorkGraphPlan
from work_graph_validate import WorkGraphValidationSummary, validate_work_graph_plan

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "Tasks"
TASKGRAPH_DIR = ROOT / "Pipeline" / "TaskGraph"
BOOTSTRAP_MARKER_PATH = TASKGRAPH_DIR / "BOOTSTRAP_PERSISTED.json"
ID_MAP_PATH = TASKGRAPH_DIR / "WORK_ID_MAP.json"
PROJECT_REQUIREMENTS_PATH = TASKGRAPH_DIR / "PROJECT_REQUIREMENTS.yaml"
RESOURCE_GROUPS_PATH = TASKGRAPH_DIR / "RESOURCE_GROUPS.yaml"
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


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise PersistentWorkGraphError(f"Missing {label}: {path.relative_to(ROOT) if path.is_absolute() else path}")
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

    # The hashes are a historical bootstrap baseline, not an immutable checksum for live task
    # state. Legitimate task status changes will change task bytes. We do, however, require every
    # baseline output path to continue to exist so bootstrap state cannot silently disappear.
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
    for path in paths:
        task = _load_json_object(path, "task")
        file_id = path.stem
        task_id = _require_text(task, "id", f"task {path.name}")
        if task_id != file_id:
            raise PersistentWorkGraphError(
                f"Task filename/id mismatch: {path.name} contains id {task_id!r}."
            )
        tasks.append(task)
    return tuple(tasks)


def load_persistent_work_graph(root: Path = ROOT) -> PersistentWorkGraph:
    """Load and structurally validate the live persistent work graph.

    BOOTSTRAP_PERSISTED.json proves the one-time bootstrap completed. Its SHA-256 entries are
    intentionally treated as a historical baseline rather than live-file checksums because task
    state is expected to evolve after bootstrap.
    """

    taskgraph_dir = root / "Pipeline" / "TaskGraph"
    marker_path = taskgraph_dir / "BOOTSTRAP_PERSISTED.json"
    id_map_path = taskgraph_dir / "WORK_ID_MAP.json"
    project_requirements_path = taskgraph_dir / "PROJECT_REQUIREMENTS.yaml"
    resource_groups_path = taskgraph_dir / "RESOURCE_GROUPS.yaml"
    tasks_dir = root / "Tasks"

    marker = _load_json_object(marker_path, "bootstrap completion marker")
    _validate_bootstrap_marker(marker, root)

    id_map_payload = _load_json_object(id_map_path, "work ID map")
    requirements_payload = _load_json_object(project_requirements_path, "project requirements")
    resources_payload = _load_json_object(resource_groups_path, "resource groups")

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

    tasks = _load_tasks(tasks_dir)

    baseline_count = marker.get("task_count")
    if not isinstance(baseline_count, int) or baseline_count < 1:
        raise PersistentWorkGraphError("Bootstrap marker contains invalid task_count.")
    if len(tasks) < baseline_count:
        raise PersistentWorkGraphError(
            f"Live graph has fewer tasks ({len(tasks)}) than the bootstrap baseline ({baseline_count})."
        )

    plan = WorkGraphPlan(
        id_map=normalized_id_map,
        tasks=tasks,
        resource_groups=tuple(resource_groups),
        project_requirements=tuple(requirements),
    )
    validation = validate_work_graph_plan(plan)
    return PersistentWorkGraph(plan=plan, marker=marker, validation=validation)
