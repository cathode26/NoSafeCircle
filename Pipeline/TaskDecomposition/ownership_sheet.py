"""The designer's ownership sheet for a decomposition, and the check that a
filled-in proposal still says what the sheet says.

The sheet holds the design: which children exist, what each owns, what each
depends on, the requirement text of every child entry, and which parent
entries each child entry covers. Everything else in a decomposition result
(entry IDs, references, coverage records, reasons, GDD evidence, notes) is
bookkeeping that another call can fill in without changing the design.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SHEET_SCHEMA_VERSION = "1"
ENTRY_TYPES = ("acceptance_criteria", "completion_gates", "downstream_integration_obligations")
_ENTRY_ID_FIELD = {
    "acceptance_criteria": "criterion_id",
    "completion_gates": "gate_id",
    "downstream_integration_obligations": "obligation_id",
}
_COPIED_CHILD_FIELDS = ("title", "kind", "type", "execution_scope")


class OwnershipSheetError(ValueError):
    """The sheet itself is malformed."""


OWNERSHIP_SHEET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "rationale", "children", "inbound_dependency_rewrites"],
    "properties": {
        "schema_version": {"type": "string", "enum": [SHEET_SCHEMA_VERSION]},
        "rationale": {"type": "string"},
        "children": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["local_key", "title", "purpose", "kind", "type", "execution_scope",
                             "exclusive_resources", "existing_task_dependencies", "local_dependencies",
                             "design_notes", "entries"],
                "properties": {
                    "local_key": {"type": "string"},
                    "title": {"type": "string"},
                    "purpose": {"type": "string"},
                    "kind": {"type": "string"},
                    "type": {"type": "string"},
                    "execution_scope": {"type": "string"},
                    "exclusive_resources": {"type": "array", "items": {"type": "string"}},
                    "existing_task_dependencies": {"type": "array", "items": {"type": "string"}},
                    "local_dependencies": {"type": "array", "items": {"type": "string"}},
                    "design_notes": {"type": "string"},
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["entry_type", "requirement", "covers"],
                            "properties": {
                                "entry_type": {"type": "string", "enum": list(ENTRY_TYPES)},
                                "requirement": {"type": "string"},
                                "covers": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
            },
        },
        "inbound_dependency_rewrites": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dependent_task_id", "replacement_local_keys"],
                "properties": {
                    "dependent_task_id": {"type": "string"},
                    "replacement_local_keys": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


def sheet_sha256(sheet: Mapping[str, Any]) -> str:
    text = json.dumps(sheet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parent_ref(entry_type: str, entry_id: str) -> str:
    return f"{entry_type}:{entry_id}"


def validate_sheet(sheet: Any, parent_contract: Mapping[str, Any]) -> None:
    """Refuse a sheet that cannot describe a complete split of the parent."""

    try:
        _validate_sheet(sheet, parent_contract)
    except OwnershipSheetError:
        raise
    except (AttributeError, KeyError, TypeError) as exc:
        raise OwnershipSheetError(f"the sheet is malformed: {type(exc).__name__}: {exc}") from exc


def _validate_sheet(sheet: Mapping[str, Any], parent_contract: Mapping[str, Any]) -> None:
    if sheet.get("schema_version") != SHEET_SCHEMA_VERSION:
        raise OwnershipSheetError(f"schema_version must be {SHEET_SCHEMA_VERSION!r}")
    keys = [child["local_key"] for child in sheet["children"]]
    if not keys:
        raise OwnershipSheetError("the sheet proposes no children")
    if len(set(keys)) != len(keys):
        raise OwnershipSheetError("child local_key values repeat")
    parent_refs = {
        _parent_ref(entry_type, entry[_ENTRY_ID_FIELD[entry_type]])
        for entry_type in ENTRY_TYPES
        for entry in parent_contract.get(entry_type) or []
    }
    covered: set[str] = set()
    owners: dict[str, str] = {}
    for child in sheet["children"]:
        for dependency in child["local_dependencies"]:
            if dependency not in keys or dependency == child["local_key"]:
                raise OwnershipSheetError(f"{child['local_key']}: unknown local dependency {dependency!r}")
        present = {entry["entry_type"] for entry in child["entries"]}
        for required in ("acceptance_criteria", "completion_gates"):
            if required not in present:
                raise OwnershipSheetError(f"{child['local_key']}: needs at least one {required} entry")
        for entry in child["entries"]:
            if not entry["requirement"].strip():
                raise OwnershipSheetError(f"{child['local_key']}: an entry has no requirement text")
            for ref in entry["covers"]:
                if ref not in parent_refs:
                    raise OwnershipSheetError(f"{child['local_key']}: covers unknown parent entry {ref!r}")
                covered.add(ref)
        for resource in child["exclusive_resources"]:
            if resource in owners:
                raise OwnershipSheetError(f"{resource} is owned by both {owners[resource]} and {child['local_key']}")
            owners[resource] = child["local_key"]
    missing = sorted(parent_refs - covered)
    if missing:
        raise OwnershipSheetError(f"no child entry covers {', '.join(missing)}")
    for rewrite in sheet["inbound_dependency_rewrites"]:
        unknown = set(rewrite["replacement_local_keys"]) - set(keys)
        if unknown or not rewrite["replacement_local_keys"]:
            raise OwnershipSheetError(f"rewrite for {rewrite['dependent_task_id']} names unknown children")


def sheet_from_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """The sheet a designer would have written for an existing result."""

    covers: dict[tuple[str, str, str], list[str]] = {}
    for record in result["parent_requirement_coverage"]:
        for target in record["child_targets"]:
            key = (target["local_key"], target["child_entry_type"], target["child_entry_id"])
            covers.setdefault(key, []).append(_parent_ref(record["parent_entry_type"], record["parent_entry_id"]))
    children = []
    for child in result["children"]:
        entries = []
        for entry_type in ENTRY_TYPES:
            for entry in child.get(entry_type) or []:
                entry_id = entry[_ENTRY_ID_FIELD[entry_type]]
                entries.append({
                    "entry_type": entry_type,
                    "requirement": entry["requirement"],
                    "covers": sorted(covers.get((child["local_key"], entry_type, entry_id), [])),
                })
        children.append({
            "local_key": child["local_key"],
            "title": child["title"],
            "purpose": child["execution_reason"],
            **{field: child[field] for field in ("kind", "type", "execution_scope")},
            "exclusive_resources": list(child["exclusive_resources"]),
            "existing_task_dependencies": list(child["existing_task_dependencies"]),
            "local_dependencies": list(child["local_dependencies"]),
            "design_notes": child.get("notes", ""),
            "entries": entries,
        })
    return {
        "schema_version": SHEET_SCHEMA_VERSION,
        "rationale": result.get("reason", ""),
        "children": children,
        "inbound_dependency_rewrites": [
            {"dependent_task_id": r["dependent_task_id"], "replacement_local_keys": list(r["replacement_local_keys"])}
            for r in result["inbound_dependency_rewrites"]
        ],
    }


def conformance_problems(sheet: Mapping[str, Any], result: Mapping[str, Any]) -> list[str]:
    """Every way `result` departs from the design in `sheet`; empty when it conforms.

    Entry IDs, references, reasons and evidence are free; everything the sheet
    states is compared exactly.
    """

    problems: list[str] = []
    if result.get("decision") != "decomposed":
        return [f"decision is {result.get('decision')!r}, not 'decomposed'"]
    planned = {child["local_key"]: child for child in sheet["children"]}
    written = {child.get("local_key"): child for child in result.get("children") or []}
    for key in sorted(set(planned) - set(written)):
        problems.append(f"child {key} is missing")
    for key in sorted(set(written) - set(planned)):
        problems.append(f"child {key} is not in the sheet")
    entry_index: dict[tuple[str, str, str], str] = {}
    for key in sorted(set(planned) & set(written)):
        plan, child = planned[key], written[key]
        for field in _COPIED_CHILD_FIELDS:
            if child.get(field) != plan[field]:
                problems.append(f"{key}: {field} changed")
        if child.get("execution_reason") != plan["purpose"]:
            problems.append(f"{key}: execution_reason is not the sheet's purpose")
        for field in ("exclusive_resources", "existing_task_dependencies", "local_dependencies"):
            if sorted(child.get(field) or []) != sorted(plan[field]):
                problems.append(f"{key}: {field} changed")
        planned_entries = sorted((e["entry_type"], e["requirement"]) for e in plan["entries"])
        written_entries = []
        for entry_type in ENTRY_TYPES:
            for entry in child.get(entry_type) or []:
                written_entries.append((entry_type, entry.get("requirement")))
                entry_index[(key, entry_type, entry.get(_ENTRY_ID_FIELD[entry_type]))] = entry.get("requirement")
        if sorted(written_entries) != planned_entries:
            problems.append(f"{key}: child entries differ from the sheet")
    expected: set[tuple[str, str, str, str]] = set()
    for key, plan in planned.items():
        for entry in plan["entries"]:
            for ref in entry["covers"]:
                expected.add((ref, key, entry["entry_type"], entry["requirement"]))
    actual: set[tuple[str, str, str, str]] = set()
    for record in result.get("parent_requirement_coverage") or []:
        ref = _parent_ref(record.get("parent_entry_type"), record.get("parent_entry_id"))
        for target in record.get("child_targets") or []:
            located = (target.get("local_key"), target.get("child_entry_type"), target.get("child_entry_id"))
            if located not in entry_index:
                problems.append(f"coverage for {ref} points at missing entry {located}")
                continue
            actual.add((ref, located[0], located[1], entry_index[located]))
    for ref, key, entry_type, _ in sorted(expected - actual):
        problems.append(f"coverage for {ref} -> {key} {entry_type} is missing")
    for ref, key, entry_type, _ in sorted(actual - expected):
        problems.append(f"coverage for {ref} -> {key} {entry_type} is not in the sheet")
    planned_rewrites = {r["dependent_task_id"]: sorted(r["replacement_local_keys"])
                        for r in sheet["inbound_dependency_rewrites"]}
    written_rewrites = {r.get("dependent_task_id"): sorted(r.get("replacement_local_keys") or [])
                        for r in result.get("inbound_dependency_rewrites") or []}
    if planned_rewrites != written_rewrites:
        problems.append("inbound dependency rewrites differ from the sheet")
    return problems
