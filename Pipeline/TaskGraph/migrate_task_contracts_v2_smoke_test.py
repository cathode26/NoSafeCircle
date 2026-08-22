from __future__ import annotations

import json
import tempfile
from pathlib import Path

from migrate_task_contracts_v2 import (
    REPORT_RELATIVE,
    apply_migration,
    plan_migration,
    verify_existing_report,
)
from persistent_work_graph import load_persistent_work_graph
from task_contract_quality_audit import audit_contracts


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def v1_task(
    task_id,
    key,
    title,
    kind,
    parent,
    depends_on,
    scope,
    *,
    status="open",
    acceptance=None,
    validation=None,
):
    return {
        "schema_version": "1.0",
        "id": task_id,
        "title": title,
        "reconciliation_key": key,
        "kind": kind,
        "type": kind,
        "status": status,
        "execution_scope": scope,
        "execution_reason": "fixture",
        "decomposition_state": "coarse" if kind == "feature" else "concrete",
        "decomposition_reason": "fixture",
        "parent": parent,
        "depends_on": depends_on,
        "exclusive_resources": [],
        "acceptance_criteria": acceptance
        or [{"reference": "Fixture", "requirement": f"Accept {title}."}],
        "validation_requirements": validation
        or [{"reference": "Fixture", "requirement": f"Validate {title}."}],
        "gdd_evidence": [],
        "basis": "direct_gdd",
        "source_scope": "required",
        "confidence": "high",
        "notes": "",
        "repository_state_at_bootstrap": "missing",
        "repository_evidence_at_bootstrap": [],
        "bootstrap_source": {
            "reconciliation_run_id": "source-run",
            "verification_run_id": "verify-run",
        },
    }


def build_fixture(root: Path) -> None:
    movement_acceptance = [
        {
            "reference": "Move",
            "requirement": "Mouse-directed movement uses project Input Actions.",
        },
        {
            "reference": "Pointer",
            "requirement": "Player Movement exposes the shared world-space pointer target.",
        },
        {
            "reference": "Restriction",
            "requirement": "Player Movement exposes its owner-controlled restriction interface.",
        },
        {
            "reference": "Reset",
            "requirement": "Player Movement exposes its owner-controlled reset entry point.",
        },
        {
            "reference": "Suspend A",
            "requirement": (
                "Exposes an owner-controlled gameplay-enable/suspend interface that immediately "
                "stops or cancels any in-progress input-driven movement, rejects new movement "
                "commands while suspended, and is re-enabled only through an authorized reset flow."
            ),
        },
        {
            "reference": "Suspend B",
            "requirement": (
                "Exposes an owner-controlled gameplay-enable/suspend interface that immediately "
                "stops already-active input-driven movement, rejects new movement commands while "
                "suspended, and can be re-enabled only through an authorized reset flow."
            ),
        },
    ]
    door_acceptance = [
        {
            "reference": "Door",
            "requirement": "Clicking a door requests approach and interaction.",
        },
        {
            "reference": "Door",
            "requirement": "Arrival starts the automatic opening timer.",
        },
        {
            "reference": "Door",
            "requirement": "Cursor drift after selection does not cancel.",
        },
        {
            "reference": "Door",
            "requirement": "Damage or movement interruption resets progress.",
        },
        {
            "reference": "Input",
            "requirement": "Door input uses project Input Actions.",
        },
        {
            "reference": "Suspend A",
            "requirement": (
                "Exposes an owner-controlled gameplay-enable/suspend interface that immediately "
                "cancels an in-progress door approach/opening timer and rejects new door-selection "
                "commands while suspended."
            ),
        },
        {
            "reference": "Reset A",
            "requirement": (
                "Exposes an owner-controlled reset entry point that returns owned interaction and "
                "opening state to floor-initial values."
            ),
        },
        {
            "reference": "Door",
            "requirement": "Five uninterrupted seconds opens the door.",
        },
        {
            "reference": "Reset B",
            "requirement": (
                "Exposes an owner-controlled reset entry point that returns owned opening state "
                "to floor-initial values rather than external mutation."
            ),
        },
        {
            "reference": "Suspend B",
            "requirement": (
                "Exposes an owner-controlled gameplay-enable/suspend interface that immediately "
                "stops an in-progress door approach/opening timer and rejects new door-interaction "
                "commands while suspended."
            ),
        },
    ]

    tasks = [
        v1_task(
            "NSC-001",
            "no-safe-circle",
            "No Safe Circle",
            "feature",
            "",
            [],
            "not_applicable",
        ),
        v1_task(
            "NSC-002",
            "world",
            "World",
            "feature",
            "NSC-001",
            [],
            "not_applicable",
        ),
        v1_task(
            "NSC-003",
            "player-movement",
            "Player Movement",
            "implementation",
            "NSC-002",
            [],
            "single_agent",
            acceptance=movement_acceptance,
            validation=[
                {
                    "reference": "Move",
                    "requirement": "Validate click and hold movement.",
                },
                {
                    "reference": "Pointer",
                    "requirement": (
                        "Validate pointer consumption by Door Interaction once that system exists."
                    ),
                },
                {
                    "reference": "Suspend",
                    "requirement": "Validate movement suspension.",
                },
            ],
        ),
        v1_task(
            "NSC-019",
            "door-open-interaction",
            "Door Opening",
            "implementation",
            "NSC-002",
            ["NSC-003"],
            "single_agent",
            acceptance=door_acceptance,
        ),
        v1_task(
            "NSC-023",
            "fixed-isometric-camera",
            "Fixed Isometric Camera",
            "implementation",
            "NSC-002",
            [],
            "not_applicable",
            status="complete",
            validation=[
                {
                    "reference": "Future integration",
                    "requirement": (
                        "Once the Tilemap foundation exists, validate compatibility."
                    ),
                }
            ],
        ),
    ]
    for task in tasks:
        write_json(root / "Tasks" / f"{task['id']}.yaml", task)

    taskgraph = root / "Pipeline" / "TaskGraph"
    write_json(
        taskgraph / "WORK_ID_MAP.json",
        {
            "schema_version": "1.0",
            "id_map": {
                "no-safe-circle": "NSC-001",
                "world": "NSC-002",
                "player-movement": "NSC-003",
                "door-open-interaction": "NSC-019",
                "fixed-isometric-camera": "NSC-023",
            },
        },
    )
    write_json(
        taskgraph / "PROJECT_REQUIREMENTS.yaml",
        {
            "schema_version": "1.0",
            "requirements": [
                {
                    "title": "Human authority",
                    "requirement_type": "pipeline_constraint",
                    "status": "confirmed",
                }
            ],
        },
    )
    write_json(
        taskgraph / "RESOURCE_GROUPS.yaml",
        {"schema_version": "1.0", "resource_groups": []},
    )
    baseline_paths = {
        f"Tasks/{task['id']}.yaml": "historical" for task in tasks
    }
    baseline_paths.update(
        {
            "Pipeline/TaskGraph/WORK_ID_MAP.json": "historical",
            "Pipeline/TaskGraph/PROJECT_REQUIREMENTS.yaml": "historical",
            "Pipeline/TaskGraph/RESOURCE_GROUPS.yaml": "historical",
        }
    )
    write_json(
        taskgraph / "BOOTSTRAP_PERSISTED.json",
        {
            "schema_version": "1.0",
            "bootstrap_status": "complete",
            "serialization_format": "yaml_1_2_json_subset",
            "task_count": len(tasks),
            "output_sha256": baseline_paths,
        },
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="task-v2-migration-") as temp:
        root = Path(temp)
        build_fixture(root)
        plan = plan_migration(root)
        assert plan.report["task_count"] == 5
        assert plan.report["bootstrap_status_observations"] == {
            "open": 4,
            "complete": 1,
        }
        assert plan.report["downstream_integration_obligation_count"] == 2

        movement = next(
            item.target for item in plan.files if item.path.stem == "NSC-003"
        )
        assert len(movement["acceptance_criteria"]) == 5
        assert len(movement["completion_gates"]) == 2
        assert len(movement["downstream_integration_obligations"]) == 1
        assert "once that system exists" in movement[
            "downstream_integration_obligations"
        ][0]["requirement"]

        door = next(
            item.target for item in plan.files if item.path.stem == "NSC-019"
        )
        assert len(door["acceptance_criteria"]) == 8
        suspend = [
            entry
            for entry in door["acceptance_criteria"]
            if "gameplay-enable/suspend" in entry["requirement"]
        ]
        resets = [
            entry
            for entry in door["acceptance_criteria"]
            if "reset entry point" in entry["requirement"]
        ]
        assert len(suspend) == 1
        assert len(resets) == 1

        camera = next(
            item.target for item in plan.files if item.path.stem == "NSC-023"
        )
        assert "status" not in camera
        assert camera["provenance"]["bootstrap_status_observation"] == "complete"
        assert camera["execution_scope"] == "single_agent"
        assert camera["decomposition_state"] == "concrete"
        assert len(camera["completion_gates"]) == 2
        assert len(camera["downstream_integration_obligations"]) == 1

        apply_migration(plan)
        assert verify_existing_report(root) is not None
        graph = load_persistent_work_graph(root)
        assert graph.validation.task_schema_version == "2.0"
        assert graph.tasks_by_id["NSC-023"]["contract_disposition"] == "active"
        assert (root / REPORT_RELATIVE).is_file()

        audit = audit_contracts(root / "Tasks")
        assert audit.findings == ()

        # Replanning and reapplying is safe and does not rewrite valid v2 contracts.
        apply_migration(plan_migration(root))
        assert verify_existing_report(root) is not None

    print("migrate_task_contracts_v2_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
