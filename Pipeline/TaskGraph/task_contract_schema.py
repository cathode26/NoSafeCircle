from __future__ import annotations

from copy import deepcopy
from typing import Any

TASK_CONTRACT_SCHEMA_VERSION = "2.0"
ALLOWED_CONTRACT_DISPOSITIONS = {"active", "superseded", "cancelled"}
LEGACY_BOOTSTRAP_STATUSES = {"open", "complete"}
FORBIDDEN_V2_OPERATIONAL_FIELDS = {
    "status",
    "validation_requirements",
    "bootstrap_source",
}


class TaskContractSchemaError(RuntimeError):
    """Raised when a task contract cannot be normalized or validated."""


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskContractSchemaError(f"{label} must be a non-empty string.")
    return value.strip()


def require_positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TaskContractSchemaError(f"{label} must be a positive integer.")
    return value


def normalize_contract_entries(
    entries: Any,
    *,
    id_field: str,
    id_prefix: str,
    label: str,
) -> list[dict[str, Any]]:
    """Copy requirement-like entries and give them deterministic local IDs."""

    if not isinstance(entries, list):
        raise TaskContractSchemaError(f"{label} must be a list.")

    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(entries, start=1):
        entry_id = f"{id_prefix}-{index:03d}"
        if isinstance(raw, str):
            requirement = require_text(raw, f"{label}[{index - 1}]")
            entry: dict[str, Any] = {
                id_field: entry_id,
                "reference": "",
                "requirement": requirement,
            }
        elif isinstance(raw, dict):
            entry = deepcopy(raw)
            existing_id = entry.get(id_field)
            if existing_id is None:
                entry[id_field] = entry_id
            else:
                entry[id_field] = require_text(existing_id, f"{label}[{index - 1}].{id_field}")
            entry["reference"] = str(entry.get("reference") or "").strip()
            entry["requirement"] = require_text(
                entry.get("requirement"),
                f"{label}[{index - 1}].requirement",
            )
        else:
            raise TaskContractSchemaError(
                f"{label}[{index - 1}] must be a string or object."
            )
        normalized.append(entry)
    return normalized
