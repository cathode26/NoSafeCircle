from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from work_graph_transform import ApprovedBootstrapInputs, WorkGraphPlan
from work_graph_validate import WorkGraphValidationError, validate_work_graph_plan

ROOT = Path(__file__).resolve().parents[2]
SERIALIZATION_FORMAT = "yaml_1_2_json_subset"


class WorkGraphPersistenceError(RuntimeError):
    """Raised when the persistent bootstrap graph cannot be safely written."""


@dataclass(frozen=True)
class PersistencePaths:
    root: Path
    tasks_dir: Path
    id_map_path: Path
    project_requirements_path: Path
    resource_groups_path: Path
    persisted_marker_path: Path


def persistence_paths(root: Path = ROOT) -> PersistencePaths:
    taskgraph = root / "Pipeline" / "TaskGraph"
    return PersistencePaths(
        root=root,
        tasks_dir=root / "Tasks",
        id_map_path=taskgraph / "WORK_ID_MAP.json",
        project_requirements_path=taskgraph / "PROJECT_REQUIREMENTS.yaml",
        resource_groups_path=taskgraph / "RESOURCE_GROUPS.yaml",
        persisted_marker_path=taskgraph / "BOOTSTRAP_PERSISTED.json",
    )


def canonical_json_text(value: Any) -> str:
    # JSON is a valid YAML 1.2 subset. Keeping the persistent .yaml files inside this
    # subset gives us a zero-dependency parser and byte-for-byte deterministic output.
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkGraphPersistenceError(f"Unable to read staged graph file {path}: {exc}") from exc


def metadata_payloads(plan: WorkGraphPlan, inputs: ApprovedBootstrapInputs) -> dict[str, dict[str, Any]]:
    provenance = {
        "reconciliation_run_id": inputs.source_reconciliation_run_id,
        "verification_run_id": inputs.verification_run_id,
    }
    return {
        "WORK_ID_MAP.json": {
            "schema_version": "1.0",
            "serialization_format": "json",
            **provenance,
            "id_map": plan.id_map,
        },
        "PROJECT_REQUIREMENTS.yaml": {
            "schema_version": "1.0",
            "serialization_format": SERIALIZATION_FORMAT,
            **provenance,
            "requirements": list(plan.project_requirements),
        },
        "RESOURCE_GROUPS.yaml": {
            "schema_version": "1.0",
            "serialization_format": SERIALIZATION_FORMAT,
            **provenance,
            "resource_groups": list(plan.resource_groups),
        },
    }


def assert_bootstrap_targets_absent(paths: PersistencePaths) -> None:
    if paths.persisted_marker_path.exists():
        raise WorkGraphPersistenceError(
            "Initial work graph bootstrap is already complete; refusing to reseed."
        )

    if paths.tasks_dir.exists():
        existing = list(paths.tasks_dir.iterdir())
        if existing:
            raise WorkGraphPersistenceError(
                f"{paths.tasks_dir} is not empty; bootstrap refuses to overwrite persistent task state."
            )

    for path in (
        paths.id_map_path,
        paths.project_requirements_path,
        paths.resource_groups_path,
    ):
        if path.exists():
            raise WorkGraphPersistenceError(
                f"Bootstrap metadata already exists at {path}; refusing to overwrite it."
            )


def stage_work_graph_bundle(
    plan: WorkGraphPlan,
    inputs: ApprovedBootstrapInputs,
    staging_root: Path,
) -> dict[str, str]:
    tasks_dir = staging_root / "Tasks"
    taskgraph_dir = staging_root / "Pipeline" / "TaskGraph"
    tasks_dir.mkdir(parents=True, exist_ok=False)
    taskgraph_dir.mkdir(parents=True, exist_ok=True)

    output_hashes: dict[str, str] = {}

    for task in sorted(plan.tasks, key=lambda item: item["id"]):
        relative = Path("Tasks") / f"{task['id']}.yaml"
        text = canonical_json_text(task)
        write_text(staging_root / relative, text)
        output_hashes[relative.as_posix()] = sha256_bytes(text.encode("utf-8"))

    payloads = metadata_payloads(plan, inputs)
    for filename, payload in payloads.items():
        relative = Path("Pipeline") / "TaskGraph" / filename
        text = canonical_json_text(payload)
        write_text(staging_root / relative, text)
        output_hashes[relative.as_posix()] = sha256_bytes(text.encode("utf-8"))

    marker = {
        "schema_version": "1.0",
        "bootstrap_status": "complete",
        "serialization_format": SERIALIZATION_FORMAT,
        "approved_by": inputs.approved_by,
        "reconciliation_run_id": inputs.source_reconciliation_run_id,
        "verification_run_id": inputs.verification_run_id,
        "task_count": len(plan.tasks),
        "output_sha256": output_hashes,
        "policy": (
            "This marker is published last. Persistent task state is considered bootstrapped only "
            "when this marker exists and taskcontrol revalidates the serialized graph."
        ),
    }
    write_text(taskgraph_dir / "BOOTSTRAP_PERSISTED.json", canonical_json_text(marker))
    return output_hashes


def validate_staged_bundle(
    plan: WorkGraphPlan,
    inputs: ApprovedBootstrapInputs,
    staging_root: Path,
    expected_hashes: dict[str, str],
) -> None:
    task_files = sorted((staging_root / "Tasks").glob("NSC-*.yaml"))
    if len(task_files) != len(plan.tasks):
        raise WorkGraphPersistenceError(
            f"Staged task count mismatch: expected {len(plan.tasks)}, found {len(task_files)}."
        )

    original_by_id = {task["id"]: task for task in plan.tasks}
    loaded_tasks: list[dict[str, Any]] = []
    for path in task_files:
        value = read_json(path)
        if not isinstance(value, dict):
            raise WorkGraphPersistenceError(f"Staged task is not an object: {path}")
        task_id = value.get("id")
        if path.name != f"{task_id}.yaml":
            raise WorkGraphPersistenceError(
                f"Staged task filename/id mismatch: {path.name} vs {task_id!r}."
            )
        if original_by_id.get(task_id) != value:
            raise WorkGraphPersistenceError(f"Staged task changed during serialization: {task_id}")
        loaded_tasks.append(value)

    taskgraph_dir = staging_root / "Pipeline" / "TaskGraph"
    id_map_payload = read_json(taskgraph_dir / "WORK_ID_MAP.json")
    requirements_payload = read_json(taskgraph_dir / "PROJECT_REQUIREMENTS.yaml")
    groups_payload = read_json(taskgraph_dir / "RESOURCE_GROUPS.yaml")

    if id_map_payload.get("id_map") != plan.id_map:
        raise WorkGraphPersistenceError("Staged WORK_ID_MAP.json does not match the validated plan.")
    if requirements_payload.get("requirements") != list(plan.project_requirements):
        raise WorkGraphPersistenceError("Staged PROJECT_REQUIREMENTS.yaml does not match the validated plan.")
    if groups_payload.get("resource_groups") != list(plan.resource_groups):
        raise WorkGraphPersistenceError("Staged RESOURCE_GROUPS.yaml does not match the validated plan.")

    loaded_plan = WorkGraphPlan(
        id_map=id_map_payload["id_map"],
        tasks=tuple(loaded_tasks),
        resource_groups=tuple(groups_payload["resource_groups"]),
        project_requirements=tuple(requirements_payload["requirements"]),
    )
    try:
        validate_work_graph_plan(loaded_plan)
    except WorkGraphValidationError as exc:
        raise WorkGraphPersistenceError(
            f"Serialized staged graph failed graph validation: {exc}"
        ) from exc

    for relative, expected in expected_hashes.items():
        path = staging_root / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise WorkGraphPersistenceError(
                f"Staged output hash mismatch for {relative}: expected {expected}, got {actual}."
            )

    marker = read_json(taskgraph_dir / "BOOTSTRAP_PERSISTED.json")
    if marker.get("bootstrap_status") != "complete":
        raise WorkGraphPersistenceError("Staged bootstrap marker is not complete.")
    if marker.get("output_sha256") != expected_hashes:
        raise WorkGraphPersistenceError("Staged bootstrap marker does not bind the exact staged outputs.")
    if marker.get("reconciliation_run_id") != inputs.source_reconciliation_run_id:
        raise WorkGraphPersistenceError("Staged bootstrap marker reconciliation identity mismatch.")
    if marker.get("verification_run_id") != inputs.verification_run_id:
        raise WorkGraphPersistenceError("Staged bootstrap marker verification identity mismatch.")


def persist_work_graph(
    plan: WorkGraphPlan,
    inputs: ApprovedBootstrapInputs,
    root: Path = ROOT,
) -> PersistencePaths:
    paths = persistence_paths(root)
    validate_work_graph_plan(plan)
    assert_bootstrap_targets_absent(paths)

    # If an empty Tasks directory exists, remove it so the staged directory can be renamed into place.
    if paths.tasks_dir.exists():
        paths.tasks_dir.rmdir()

    published: list[Path] = []
    staging_dir: Path | None = None
    try:
        staging_dir = Path(tempfile.mkdtemp(prefix=".taskgraph-bootstrap-", dir=root))
        expected_hashes = stage_work_graph_bundle(plan, inputs, staging_dir)
        validate_staged_bundle(plan, inputs, staging_dir, expected_hashes)

        staged_tasks = staging_dir / "Tasks"
        os.replace(staged_tasks, paths.tasks_dir)
        published.append(paths.tasks_dir)

        staged_taskgraph = staging_dir / "Pipeline" / "TaskGraph"
        for filename, target in (
            ("WORK_ID_MAP.json", paths.id_map_path),
            ("PROJECT_REQUIREMENTS.yaml", paths.project_requirements_path),
            ("RESOURCE_GROUPS.yaml", paths.resource_groups_path),
        ):
            os.replace(staged_taskgraph / filename, target)
            published.append(target)

        # Commit marker is intentionally last: readers never accept a half-published bootstrap.
        os.replace(staged_taskgraph / "BOOTSTRAP_PERSISTED.json", paths.persisted_marker_path)
        published.append(paths.persisted_marker_path)
    except Exception as exc:
        # Best-effort rollback for ordinary process/file errors. A hard process/OS interruption is
        # still detectable because BOOTSTRAP_PERSISTED.json is the last file published.
        for path in reversed(published):
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.exists():
                    path.unlink()
            except OSError:
                pass
        if isinstance(exc, (WorkGraphPersistenceError, WorkGraphValidationError)):
            raise
        raise WorkGraphPersistenceError(f"Failed to publish persistent work graph: {exc}") from exc
    finally:
        if staging_dir is not None and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    return paths
