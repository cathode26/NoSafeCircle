from __future__ import annotations

from copy import deepcopy
from typing import Any

from task_contract_schema import (
    LEGACY_BOOTSTRAP_STATUSES,
    TASK_CONTRACT_SCHEMA_VERSION,
    TaskContractSchemaError,
    normalize_contract_entries,
    require_text,
)

MIGRATION_ID = "task-contract-schema-v2-20260822"

# The camera's only v1 `validation_requirements` entry explicitly described a
# later Tilemap/SpriteRenderer compatibility check. It is not a gate that must
# remain open on the already-delivered camera contract. Preserve it as a
# downstream obligation and derive the actual historical completion gates from
# the repository/test evidence recorded in the same v1 task.
CAMERA_COMPLETION_GATES = [
    {
        "reference": "Bootstrap repository evidence — DoorPrototypeSceneBuilderTests",
        "requirement": (
            "Unity validation confirms the canonical camera is orthographic and "
            "uses the fixed approved isometric rotation without a runtime rotation controller."
        ),
    },
    {
        "reference": "Bootstrap repository evidence — IsometricCameraFollow validation",
        "requirement": (
            "Unity validation confirms target-follow translation does not change "
            "the camera's fixed rotation."
        ),
    },
]

DOWNSTREAM_VALIDATION_INDEXES: dict[str, set[int]] = {
    "NSC-023": {0},
}
COMPLETION_GATE_OVERRIDES: dict[str, list[dict[str, str]]] = {
    "NSC-023": CAMERA_COMPLETION_GATES,
}

EXECUTION_CONTRACT_OVERRIDES: dict[str, dict[str, str]] = {
    "NSC-023": {
        "execution_scope": "single_agent",
        "execution_reason": (
            "The fixed-camera behavior is a bounded implementation contract. Historical delivery "
            "does not make its execution scope not-applicable; current completion is derived elsewhere."
        ),
        "decomposition_state": "concrete",
        "decomposition_reason": (
            "The fixed projection/no-free-rotation behavior is a concrete bounded contract. "
            "Delivery state is intentionally separate from decomposition state."
        ),
    }
}


class TaskContractMigrationError(RuntimeError):
    """Raised when a v1 task cannot be migrated deterministically."""


def _legacy_provenance(task: dict[str, Any], status: str) -> dict[str, Any]:
    source = task.get("bootstrap_source")
    if not isinstance(source, dict):
        raise TaskContractMigrationError(
            f"{task.get('id', '<unknown>')}.bootstrap_source must be an object."
        )
    try:
        reconciliation_run_id = require_text(
            source.get("reconciliation_run_id"),
            f"{task.get('id', '<unknown>')}.bootstrap_source.reconciliation_run_id",
        )
        verification_run_id = require_text(
            source.get("verification_run_id"),
            f"{task.get('id', '<unknown>')}.bootstrap_source.verification_run_id",
        )
    except TaskContractSchemaError as exc:
        raise TaskContractMigrationError(str(exc)) from exc

    return {
        "origin": "verified_reconciliation_bootstrap",
        "source_schema_version": "1.0",
        "reconciliation_run_id": reconciliation_run_id,
        "verification_run_id": verification_run_id,
        "bootstrap_status_observation": status,
        "migration_id": MIGRATION_ID,
    }


def migrate_v1_task(task: dict[str, Any]) -> dict[str, Any]:
    """Convert one v1 bootstrap task into a v2 task contract.

    The migration removes operational completion state, preserves the old
    status only as an explicitly historical provenance observation, numbers
    criteria/gates deterministically, and separates future integration work
    from completion gates.
    """

    if not isinstance(task, dict):
        raise TaskContractMigrationError("Task must be an object.")
    if task.get("schema_version") != "1.0":
        raise TaskContractMigrationError(
            f"Expected task schema_version '1.0', got {task.get('schema_version')!r}."
        )

    try:
        task_id = require_text(task.get("id"), "task.id")
        status = require_text(task.get("status"), f"{task_id}.status")
    except TaskContractSchemaError as exc:
        raise TaskContractMigrationError(str(exc)) from exc
    if status not in LEGACY_BOOTSTRAP_STATUSES:
        raise TaskContractMigrationError(
            f"{task_id}.status must be one of {sorted(LEGACY_BOOTSTRAP_STATUSES)}."
        )

    raw_validation = task.get("validation_requirements", [])
    if not isinstance(raw_validation, list):
        raise TaskContractMigrationError(
            f"{task_id}.validation_requirements must be a list."
        )

    downstream_indexes = DOWNSTREAM_VALIDATION_INDEXES.get(task_id, set())
    invalid_indexes = sorted(index for index in downstream_indexes if index < 0 or index >= len(raw_validation))
    if invalid_indexes:
        raise TaskContractMigrationError(
            f"{task_id} migration rules reference missing validation indexes: {invalid_indexes}."
        )

    completion_source = [
        entry for index, entry in enumerate(raw_validation) if index not in downstream_indexes
    ]
    downstream_source = [
        entry for index, entry in enumerate(raw_validation) if index in downstream_indexes
    ]
    if task_id in COMPLETION_GATE_OVERRIDES:
        completion_source = COMPLETION_GATE_OVERRIDES[task_id]

    try:
        acceptance_criteria = normalize_contract_entries(
            task.get("acceptance_criteria", []),
            id_field="criterion_id",
            id_prefix="AC",
            label=f"{task_id}.acceptance_criteria",
        )
        completion_gates = normalize_contract_entries(
            completion_source,
            id_field="gate_id",
            id_prefix="VAL",
            label=f"{task_id}.completion_gates",
        )
        downstream_obligations = normalize_contract_entries(
            downstream_source,
            id_field="obligation_id",
            id_prefix="INT",
            label=f"{task_id}.downstream_integration_obligations",
        )
    except TaskContractSchemaError as exc:
        raise TaskContractMigrationError(str(exc)) from exc

    contract_override = EXECUTION_CONTRACT_OVERRIDES.get(task_id, {})

    # Build the object in canonical field order instead of mutating the legacy
    # dictionary. Optional legacy fields are copied afterward.
    migrated: dict[str, Any] = {
        "schema_version": TASK_CONTRACT_SCHEMA_VERSION,
        "id": task_id,
        "contract_revision": 1,
        "contract_disposition": "active",
        "title": task.get("title", ""),
        "reconciliation_key": task.get("reconciliation_key", ""),
        "kind": task.get("kind", ""),
        "type": task.get("type", ""),
        "execution_scope": contract_override.get(
            "execution_scope", str(task.get("execution_scope") or "")
        ),
        "execution_reason": contract_override.get(
            "execution_reason", str(task.get("execution_reason") or "")
        ),
        "decomposition_state": contract_override.get(
            "decomposition_state", str(task.get("decomposition_state") or "")
        ),
        "decomposition_reason": contract_override.get(
            "decomposition_reason", str(task.get("decomposition_reason") or "")
        ),
        "parent": task.get("parent", ""),
        "depends_on": deepcopy(task.get("depends_on", [])),
        "exclusive_resources": deepcopy(task.get("exclusive_resources", [])),
        "acceptance_criteria": acceptance_criteria,
        "completion_gates": completion_gates,
        "downstream_integration_obligations": downstream_obligations,
        "gdd_evidence": deepcopy(task.get("gdd_evidence", [])),
        "basis": task.get("basis", ""),
        "source_scope": task.get("source_scope", ""),
        "confidence": task.get("confidence", ""),
        "notes": task.get("notes", ""),
        "repository_state_at_bootstrap": task.get("repository_state_at_bootstrap", ""),
        "repository_evidence_at_bootstrap": deepcopy(
            task.get("repository_evidence_at_bootstrap", [])
        ),
        "provenance": _legacy_provenance(task, status),
    }

    handled = {
        "schema_version",
        "id",
        "status",
        "validation_requirements",
        "bootstrap_source",
        *migrated.keys(),
    }
    for field, value in task.items():
        if field not in handled:
            migrated[field] = deepcopy(value)

    return migrated


def migrate_task_contract(task: dict[str, Any]) -> dict[str, Any]:
    """Idempotently return a v2 contract or migrate a v1 task."""

    version = task.get("schema_version") if isinstance(task, dict) else None
    if version == TASK_CONTRACT_SCHEMA_VERSION:
        return deepcopy(task)
    if version == "1.0":
        return migrate_v1_task(task)
    raise TaskContractMigrationError(
        f"Unsupported task schema_version: {version!r}."
    )
