from __future__ import annotations

import argparse
from pathlib import Path

from bootstrap_inputs import BootstrapInputError, load_approved_bootstrap_inputs
from work_graph_persist import WorkGraphPersistenceError, persist_work_graph
from work_graph_transform import WorkGraphTransformError, build_work_graph_plan
from work_graph_validate import WorkGraphValidationError, validate_work_graph_plan

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "Tasks"
ID_MAP_PATH = ROOT / "Pipeline" / "TaskGraph" / "WORK_ID_MAP.json"
PROJECT_REQUIREMENTS_PATH = ROOT / "Pipeline" / "TaskGraph" / "PROJECT_REQUIREMENTS.yaml"
RESOURCE_GROUPS_PATH = ROOT / "Pipeline" / "TaskGraph" / "RESOURCE_GROUPS.yaml"
PERSISTED_MARKER_PATH = ROOT / "Pipeline" / "TaskGraph" / "BOOTSTRAP_PERSISTED.json"


def planned_task_paths(task_ids: list[str]) -> list[Path]:
    return [TASKS_DIR / f"{task_id}.yaml" for task_id in sorted(task_ids)]


def load_plan():
    inputs = load_approved_bootstrap_inputs()
    plan = build_work_graph_plan(inputs)
    summary = validate_work_graph_plan(plan)
    return inputs, plan, summary


def print_dry_run() -> int:
    inputs, plan, summary = load_plan()
    task_paths = planned_task_paths([task["id"] for task in plan.tasks])

    print("Work Graph Seeder dry run: PASS")
    print(f"Approved by:          {inputs.approved_by}")
    print(f"Reconciliation run:   {inputs.source_reconciliation_run_id}")
    print(f"Verification run:     {inputs.verification_run_id}")
    print(f"Tasks validated:      {summary.task_count}")
    print(f"Root:                 {summary.root_id} ({summary.root_key})")
    print(f"Parent edges:         {summary.parent_edge_count}")
    print(f"Dependency edges:     {summary.dependency_edge_count}")
    print("Parent hierarchy:     connected + acyclic")
    print("Dependency graph:     acyclic")
    print(f"Resource groups:      {summary.resource_group_count}")
    print(f"Project requirements: {summary.project_requirement_count}")
    print("Shared resource claims: exact group match")
    print("Bootstrap provenance: one approved source/verification pair")
    print("\nWould create on --apply:")
    print(f"  Tasks/NSC-001.yaml ... Tasks/NSC-{summary.task_count:03d}.yaml ({len(task_paths)} task files)")
    print(f"  {ID_MAP_PATH.relative_to(ROOT).as_posix()}")
    print(f"  {PROJECT_REQUIREMENTS_PATH.relative_to(ROOT).as_posix()}")
    print(f"  {RESOURCE_GROUPS_PATH.relative_to(ROOT).as_posix()}")
    print(f"  {PERSISTED_MARKER_PATH.relative_to(ROOT).as_posix()} (published last)")
    print("\nSerialization: YAML 1.2 JSON-compatible subset (stdlib only).")
    print("No files were written.")
    return 0


def apply_seed() -> int:
    inputs, plan, summary = load_plan()
    paths = persist_work_graph(plan, inputs, root=ROOT)

    print("Work Graph Seeder apply: PASS")
    print(f"Approved by:          {inputs.approved_by}")
    print(f"Reconciliation run:   {inputs.source_reconciliation_run_id}")
    print(f"Verification run:     {inputs.verification_run_id}")
    print(f"Tasks written:        {summary.task_count}")
    print(f"Root:                 {summary.root_id} ({summary.root_key})")
    print(f"Dependency edges:     {summary.dependency_edge_count}")
    print(f"Resource groups:      {summary.resource_group_count}")
    print(f"Project requirements: {summary.project_requirement_count}")
    print("Serialized graph was reloaded and revalidated before publication.")
    print(f"Commit marker:        {paths.persisted_marker_path.relative_to(ROOT).as_posix()}")
    print("Initial persistent work graph bootstrap is complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically seed the initial persistent No Safe Circle work graph from the "
            "human-approved verified reconciliation."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report the exact bootstrap write plan without writing files.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Stage, reload, revalidate, and publish the one-time persistent work graph bootstrap.",
    )
    args = parser.parse_args()

    try:
        if args.apply:
            return apply_seed()
        return print_dry_run()
    except (
        BootstrapInputError,
        WorkGraphTransformError,
        WorkGraphValidationError,
        WorkGraphPersistenceError,
    ) as exc:
        mode_name = "apply" if args.apply else "dry run"
        print(f"Work Graph Seeder {mode_name}: FAIL\n{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
