from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from task_contract_migration import MIGRATION_ID, TaskContractMigrationError, migrate_task_contract
from task_contract_schema import TASK_CONTRACT_SCHEMA_VERSION
from work_graph_transform import WorkGraphPlan
from work_graph_validate import WorkGraphValidationError, validate_work_graph_plan

ROOT = Path(__file__).resolve().parents[2]
REPORT_RELATIVE = Path("Pipeline/TaskGraph/TASK_CONTRACT_V2_MIGRATION.json")


class TaskContractMigrationApplyError(RuntimeError):
    """Raised when the repository migration cannot be planned or applied safely."""


@dataclass(frozen=True)
class TaskFileMigration:
    path: Path
    source_sha256: str
    target_sha256: str
    source_schema_version: str
    target: dict[str, Any]


@dataclass(frozen=True)
class MigrationPlan:
    root: Path
    files: tuple[TaskFileMigration, ...]
    report: dict[str, Any]


def canonical_json_text(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise TaskContractMigrationApplyError(f"Missing {label}: {path}")
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskContractMigrationApplyError(f"Unable to read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TaskContractMigrationApplyError(f"{label} must contain an object: {path}")
    return value


def _metadata_plan(root: Path, tasks: tuple[dict[str, Any], ...]) -> WorkGraphPlan:
    taskgraph = root / "Pipeline" / "TaskGraph"
    id_map_payload = load_json_object(taskgraph / "WORK_ID_MAP.json", "work ID map")
    requirements_payload = load_json_object(
        taskgraph / "PROJECT_REQUIREMENTS.yaml", "project requirements"
    )
    resources_payload = load_json_object(taskgraph / "RESOURCE_GROUPS.yaml", "resource groups")
    id_map = id_map_payload.get("id_map")
    requirements = requirements_payload.get("requirements")
    resource_groups = resources_payload.get("resource_groups")
    if not isinstance(id_map, dict):
        raise TaskContractMigrationApplyError("WORK_ID_MAP.json is missing id_map.")
    if not isinstance(requirements, list):
        raise TaskContractMigrationApplyError(
            "PROJECT_REQUIREMENTS.yaml is missing requirements."
        )
    if not isinstance(resource_groups, list):
        raise TaskContractMigrationApplyError(
            "RESOURCE_GROUPS.yaml is missing resource_groups."
        )
    return WorkGraphPlan(
        id_map={str(key): str(value) for key, value in id_map.items()},
        tasks=tasks,
        resource_groups=tuple(resource_groups),
        project_requirements=tuple(requirements),
    )


def plan_migration(root: Path = ROOT) -> MigrationPlan:
    task_paths = sorted((root / "Tasks").glob("NSC-*.yaml"))
    if not task_paths:
        raise TaskContractMigrationApplyError("No Tasks/NSC-*.yaml contracts found.")

    migrations: list[TaskFileMigration] = []
    target_tasks: list[dict[str, Any]] = []
    bootstrap_observations: dict[str, int] = {"open": 0, "complete": 0}
    total_gates = 0
    total_obligations = 0

    for path in task_paths:
        source_bytes = path.read_bytes()
        source = load_json_object(path, "task contract")
        source_version = str(source.get("schema_version") or "")
        try:
            target = migrate_task_contract(source)
        except TaskContractMigrationError as exc:
            raise TaskContractMigrationApplyError(f"{path.name}: {exc}") from exc
        if target.get("schema_version") != TASK_CONTRACT_SCHEMA_VERSION:
            raise TaskContractMigrationApplyError(
                f"{path.name}: migration did not produce schema {TASK_CONTRACT_SCHEMA_VERSION}."
            )
        if target.get("id") != path.stem:
            raise TaskContractMigrationApplyError(
                f"{path.name}: filename/id mismatch after migration."
            )
        observation = target.get("provenance", {}).get("bootstrap_status_observation")
        if observation in bootstrap_observations:
            bootstrap_observations[observation] += 1
        total_gates += len(target.get("completion_gates", []))
        total_obligations += len(target.get("downstream_integration_obligations", []))
        target_text = canonical_json_text(target)
        migrations.append(
            TaskFileMigration(
                path=path,
                source_sha256=sha256_bytes(source_bytes),
                target_sha256=sha256_bytes(target_text.encode("utf-8")),
                source_schema_version=source_version,
                target=target,
            )
        )
        target_tasks.append(target)

    plan = _metadata_plan(root, tuple(target_tasks))
    try:
        summary = validate_work_graph_plan(plan)
    except WorkGraphValidationError as exc:
        raise TaskContractMigrationApplyError(
            f"Migrated graph failed schema-v2 validation: {exc}"
        ) from exc

    report = {
        "schema_version": "1.0",
        "migration_id": MIGRATION_ID,
        "target_task_contract_schema_version": TASK_CONTRACT_SCHEMA_VERSION,
        "task_count": len(migrations),
        "source_schema_versions": sorted(
            {migration.source_schema_version for migration in migrations}
        ),
        "bootstrap_status_observations": bootstrap_observations,
        "completion_gate_count": total_gates,
        "downstream_integration_obligation_count": total_obligations,
        "validation": {
            "root_id": summary.root_id,
            "parent_edge_count": summary.parent_edge_count,
            "dependency_edge_count": summary.dependency_edge_count,
            "resource_group_count": summary.resource_group_count,
        },
        "files": [
            {
                "path": migration.path.relative_to(root).as_posix(),
                "source_schema_version": migration.source_schema_version,
                "source_sha256": migration.source_sha256,
                "target_sha256": migration.target_sha256,
            }
            for migration in migrations
        ],
        "policy": (
            "This migration converts task definitions to schema 2.0. It removes mutable "
            "operational completion status, preserves bootstrap status only as historical "
            "provenance, and does not authorize execution or claim current conformance."
        ),
    }
    return MigrationPlan(root=root, files=tuple(migrations), report=report)


def verify_existing_report(root: Path) -> dict[str, Any] | None:
    report_path = root / REPORT_RELATIVE
    if not report_path.exists():
        return None
    report = load_json_object(report_path, "migration report")
    if report.get("migration_id") != MIGRATION_ID:
        raise TaskContractMigrationApplyError(
            f"Unexpected migration report identity: {report.get('migration_id')!r}"
        )
    if report.get("target_task_contract_schema_version") != TASK_CONTRACT_SCHEMA_VERSION:
        raise TaskContractMigrationApplyError(
            "Migration report target schema does not match this migrator."
        )
    files = report.get("files")
    if not isinstance(files, list) or not files:
        raise TaskContractMigrationApplyError("Migration report contains no file bindings.")
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise TaskContractMigrationApplyError(
                f"Migration report files[{index}] is not an object."
            )
        relative = entry.get("path")
        expected = entry.get("target_sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise TaskContractMigrationApplyError(
                f"Migration report files[{index}] is missing path/target_sha256."
            )
        path = root / relative
        if not path.is_file():
            raise TaskContractMigrationApplyError(
                f"Migrated task bound by the report is missing: {relative}"
            )
        actual = sha256_bytes(path.read_bytes())
        if actual != expected:
            raise TaskContractMigrationApplyError(
                f"Migrated task no longer matches report: {relative}"
            )
    return report


def apply_migration(plan: MigrationPlan) -> None:
    existing_report = verify_existing_report(plan.root)
    if existing_report is not None:
        print("Task contract schema-v2 migration is already applied and verified.")
        return

    report_path = plan.root / REPORT_RELATIVE

    staging = Path(tempfile.mkdtemp(prefix=".task-contract-v2-", dir=plan.root))
    try:
        for migration in plan.files:
            relative = migration.path.relative_to(plan.root)
            target_path = staging / relative
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(
                canonical_json_text(migration.target), encoding="utf-8", newline="\n"
            )
        staged_report = staging / REPORT_RELATIVE
        staged_report.parent.mkdir(parents=True, exist_ok=True)
        staged_report.write_text(
            canonical_json_text(plan.report), encoding="utf-8", newline="\n"
        )

        # Recheck source bytes immediately before publication. A concurrently
        # edited contract invalidates the migration plan rather than being lost.
        for migration in plan.files:
            current_sha = sha256_bytes(migration.path.read_bytes())
            if current_sha != migration.source_sha256:
                raise TaskContractMigrationApplyError(
                    f"Task changed after migration planning: {migration.path}"
                )

        # Individual replacements are atomic. The report is published last, so
        # an interrupted apply is detectable and safely recoverable by rerunning
        # this idempotent migrator over the mixed v1/v2 files.
        for migration in plan.files:
            relative = migration.path.relative_to(plan.root)
            os.replace(staging / relative, migration.path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged_report, report_path)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def print_summary(plan: MigrationPlan, *, applied: bool) -> None:
    action = "APPLIED" if applied else "CHECK PASS"
    print(f"Task contract schema-v2 migration: {action}")
    print(f"Migration ID:           {plan.report['migration_id']}")
    print(f"Task contracts:         {plan.report['task_count']}")
    print(f"Source schemas:         {', '.join(plan.report['source_schema_versions'])}")
    print(f"Target schema:          {plan.report['target_task_contract_schema_version']}")
    observations = plan.report["bootstrap_status_observations"]
    print(
        "Historical observations: "
        f"open={observations['open']}, complete={observations['complete']}"
    )
    print(f"Completion gates:       {plan.report['completion_gate_count']}")
    print(
        "Integration obligations: "
        f"{plan.report['downstream_integration_obligation_count']}"
    )
    if not applied:
        print("No files were written. Run again with --apply after reviewing this check.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check or atomically apply the Tasks/*.yaml schema-v2 migration."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Validate migration without writing.")
    mode.add_argument("--apply", action="store_true", help="Apply the validated migration.")
    args = parser.parse_args(argv)
    try:
        plan = plan_migration()
        if args.apply:
            apply_migration(plan)
            report = verify_existing_report(ROOT)
            if report is None:
                raise TaskContractMigrationApplyError(
                    "Post-apply migration report verification failed."
                )
            print_summary(plan, applied=True)
        else:
            existing = verify_existing_report(ROOT)
            if existing is not None:
                print("Task contract schema-v2 migration: CHECK PASS (already applied)")
                print(f"Migration ID:           {existing['migration_id']}")
                print(f"Task contracts:         {existing['task_count']}")
                print(f"Target schema:          {existing['target_task_contract_schema_version']}")
            else:
                print_summary(plan, applied=False)
    except TaskContractMigrationApplyError as exc:
        print(f"Task contract schema-v2 migration: FAIL\n{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
