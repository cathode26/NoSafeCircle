"""Deterministic bookkeeping for the designer/bookkeeper split.

Everything in a decomposition result that follows from the ownership sheet is
built here, not by a model: the children and their copied fields, every entry
ID and requirement, the parent coverage table with its dispositions, and the
inbound dependency rewrites. The bookkeeper model only writes prose: entry
references, GDD evidence, notes, reasons and the child classification fields.

`impose_skeleton` then overwrites every structural field of the model's answer
with the skeleton, so a dropped entry or a mis-pointed coverage row cannot
reach the candidate. What survives from the model is exactly its prose.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .ownership_sheet import ENTRY_TYPES, conformance_problems

_ID_FIELDS = {
    "acceptance_criteria": ("criterion_id", "AC"),
    "completion_gates": ("gate_id", "VAL"),
    "downstream_integration_obligations": ("obligation_id", "INT"),
}
# Child fields the sheet decides; everything else on a child is the model's prose.
_STRUCTURAL_CHILD_FIELDS = (
    "local_key", "title", "kind", "type", "execution_scope", "execution_reason",
    "exclusive_resources", "existing_task_dependencies", "local_dependencies", *ENTRY_TYPES,
)
_PROSE_CHILD_FIELDS = {
    "basis": "", "confidence": "", "decomposition_reason": "", "decomposition_state": "",
    "source_scope": "", "notes": "", "gdd_evidence": [],
}


def _parent_ref(ref: str) -> tuple[str, str]:
    entry_type, _, entry_id = ref.partition(":")
    return entry_type, entry_id


def result_skeleton(sheet: Mapping[str, Any]) -> dict[str, Any]:
    """The result's structure, fully determined by the sheet; prose fields are empty."""

    children: list[dict[str, Any]] = []
    targets: dict[tuple[str, str], list[dict[str, str]]] = {}
    for plan in sheet["children"]:
        child: dict[str, Any] = {
            "local_key": plan["local_key"],
            "title": plan["title"],
            "kind": plan["kind"],
            "type": plan["type"],
            "execution_scope": plan["execution_scope"],
            "execution_reason": plan["purpose"],
            "exclusive_resources": list(plan["exclusive_resources"]),
            "existing_task_dependencies": list(plan["existing_task_dependencies"]),
            "local_dependencies": list(plan["local_dependencies"]),
            **deepcopy(_PROSE_CHILD_FIELDS),
            "notes": plan["design_notes"],
        }
        for entry_type in ENTRY_TYPES:
            id_field, prefix = _ID_FIELDS[entry_type]
            entries = [entry for entry in plan["entries"] if entry["entry_type"] == entry_type]
            child[entry_type] = []
            for number, entry in enumerate(entries, start=1):
                entry_id = f"{prefix}-{number:03d}"
                child[entry_type].append({id_field: entry_id, "reference": "", "requirement": entry["requirement"]})
                for ref in entry["covers"]:
                    targets.setdefault(_parent_ref(ref), []).append({
                        "local_key": plan["local_key"], "child_entry_type": entry_type,
                        "child_entry_id": entry_id,
                    })
        children.append(child)
    coverage = []
    for (entry_type, entry_id), child_targets in sorted(targets.items()):
        shared = len({target["local_key"] for target in child_targets}) > 1
        coverage.append({
            "parent_entry_type": entry_type,
            "parent_entry_id": entry_id,
            "disposition": "shared_integration" if shared else "assigned_to_child",
            "child_targets": child_targets,
            "reason": "",
            "integration_rationale": "",
        })
    return {
        "decision": "decomposed",
        "reason": "",
        "children": children,
        "parent_requirement_coverage": coverage,
        "inbound_dependency_rewrites": [
            {"dependent_task_id": rewrite["dependent_task_id"],
             "replacement_local_keys": list(rewrite["replacement_local_keys"]), "reason": ""}
            for rewrite in sheet["inbound_dependency_rewrites"]
        ],
    }


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _preserved_notes(design_notes: str, model_notes: Any) -> str:
    """The model's notes, always carrying the designer's notes word for word."""

    written = model_notes.strip() if isinstance(model_notes, str) else ""
    if design_notes in written:
        return written
    return f"{design_notes}\n\n{written}" if written else design_notes


def impose_skeleton(skeleton: Mapping[str, Any], output: Any) -> dict[str, Any]:
    """The model's answer with every structural field replaced by the skeleton's.

    Prose is matched to the skeleton by stable keys (child local_key, entry
    ID, parent entry, dependent task) and anything the model did not write
    stays empty, for the validators to refuse.
    """

    answer = _as_map(output)
    result = {key: deepcopy(value) for key, value in answer.items()
              if key not in ("decision", "children", "parent_requirement_coverage", "inbound_dependency_rewrites")}
    result["decision"] = skeleton["decision"]
    result.setdefault("reason", "")
    written = {child.get("local_key"): child for child in _as_list(answer.get("children"))
               if isinstance(child, Mapping)}
    children = []
    for planned in skeleton["children"]:
        model_child = _as_map(written.get(planned["local_key"]))
        child = {key: deepcopy(value) for key, value in model_child.items() if key not in _STRUCTURAL_CHILD_FIELDS}
        for field, empty in _PROSE_CHILD_FIELDS.items():
            child.setdefault(field, deepcopy(empty))
        for field in _STRUCTURAL_CHILD_FIELDS:
            if field not in ENTRY_TYPES:
                child[field] = deepcopy(planned[field])
        child["notes"] = _preserved_notes(planned["notes"], model_child.get("notes"))
        for entry_type in ENTRY_TYPES:
            id_field = _ID_FIELDS[entry_type][0]
            model_entries = {entry.get(id_field): entry for entry in _as_list(model_child.get(entry_type))
                             if isinstance(entry, Mapping)}
            child[entry_type] = [
                {**entry, "reference": _as_map(model_entries.get(entry[id_field])).get("reference", "")}
                for entry in planned[entry_type]
            ]
        children.append(child)
    result["children"] = children
    model_coverage = {(record.get("parent_entry_type"), record.get("parent_entry_id")): record
                      for record in _as_list(answer.get("parent_requirement_coverage"))
                      if isinstance(record, Mapping)}
    result["parent_requirement_coverage"] = []
    for planned in skeleton["parent_requirement_coverage"]:
        model_record = _as_map(model_coverage.get((planned["parent_entry_type"], planned["parent_entry_id"])))
        record = deepcopy(planned)
        record["reason"] = model_record.get("reason", "")
        if planned["disposition"] == "shared_integration":
            record["integration_rationale"] = model_record.get("integration_rationale", "")
        result["parent_requirement_coverage"].append(record)
    model_rewrites = {rewrite.get("dependent_task_id"): rewrite
                      for rewrite in _as_list(answer.get("inbound_dependency_rewrites"))
                      if isinstance(rewrite, Mapping)}
    result["inbound_dependency_rewrites"] = [
        {**deepcopy(planned), "reason": _as_map(model_rewrites.get(planned["dependent_task_id"])).get("reason", "")}
        for planned in skeleton["inbound_dependency_rewrites"]
    ]
    return result


def structural_slips(sheet: Mapping[str, Any], output: Any) -> list[str]:
    """What the model got wrong structurally, before the skeleton corrected it (diagnostic only)."""

    if not isinstance(output, Mapping):
        return ["the bookkeeper output is not an object"]
    return conformance_problems(sheet, output)
