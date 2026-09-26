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
from difflib import SequenceMatcher
import re
from typing import Any, Mapping

from .ownership_sheet import ENTRY_TYPES, conformance_problems

NOTES_RULE_ADDITIONS = "additions-1"


def validate_notes_rule(notes_rule: str | None) -> None:
    """Refuse unknown rules rather than changing the meaning of recorded evidence."""

    if notes_rule is not None and notes_rule != NOTES_RULE_ADDITIONS:
        raise ValueError(f"unsupported bookkeeper notes rule: {notes_rule!r}")


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


def _preserved_notes(design_notes: str, model_notes: Any, *, legacy: bool = False,
                     notes_rule: str | None = None) -> str:
    """The model's notes, always carrying the designer's notes word for word.

    ``legacy`` reproduces the pre-v2 behaviour exactly, so evidence recorded
    before the whitespace fix still replays to the candidate it recorded.
    """

    validate_notes_rule(notes_rule)
    written = model_notes.strip() if isinstance(model_notes, str) else ""
    if design_notes in written:
        return written
    # Design notes that begin or end with whitespace are lost by the strip;
    # recognise them in the unstripped text rather than duplicating them.
    if not legacy and isinstance(model_notes, str) and design_notes in model_notes:
        return model_notes
    if notes_rule == NOTES_RULE_ADDITIONS:
        normalized_design = " ".join(design_notes.split()).casefold()
        kept = []
        for paragraph in re.split(r"\n\s*\n", written):
            paragraph = paragraph.strip()
            normalized = " ".join(paragraph.split()).casefold()
            if not normalized:
                continue
            # Repeated characters in long prose must not be discarded as junk.
            near_copy = (normalized in normalized_design
                         or SequenceMatcher(None, normalized, normalized_design, autojunk=False).ratio() >= 0.9)
            if not near_copy and len(normalized) > len(normalized_design):
                # A longer paragraph can start with a drifted copy, then append prose.
                # Compare that paragraph's design-note-length prefix to the design notes.
                near_copy = SequenceMatcher(
                    None, normalized[:len(normalized_design)], normalized_design, autojunk=False,
                ).ratio() >= 0.9
            if not near_copy:
                kept.append(paragraph)
        written = "\n\n".join(kept)
    return f"{design_notes}\n\n{written}" if written else design_notes


def impose_skeleton(skeleton: Mapping[str, Any], output: Any, *, legacy_notes: bool = False,
                    legacy_entry_ids: bool = False,
                    notes_rule: str | None = None) -> dict[str, Any]:
    """The model's answer with every structural field replaced by the skeleton's.

    Prose is matched to the skeleton by stable keys (child local_key, entry
    requirement, parent entry, dependent task) and anything the model did not
    write stays empty, for the validators to refuse. Entry IDs are the model's
    free text and it mis-numbers them, so they are only a fallback key;
    ``legacy_entry_ids`` restores the pre-fix ID join for replaying evidence
    recorded before that change.
    """

    validate_notes_rule(notes_rule)
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
        child["notes"] = _preserved_notes(
            planned["notes"], model_child.get("notes"), legacy=legacy_notes, notes_rule=notes_rule,
        )
        for entry_type in ENTRY_TYPES:
            id_field = _ID_FIELDS[entry_type][0]
            model_entries = [entry for entry in _as_list(model_child.get(entry_type))
                             if isinstance(entry, Mapping)]
            by_id = {entry.get(id_field): entry for entry in model_entries}
            # The entry ID is the model's own free text and it mis-numbers it;
            # the requirement is the sheet's, and conformance_problems compares
            # requirements exactly, so match on the requirement and keep the ID
            # only as a fallback. A requirement stated twice pairs up in order.
            by_requirement: dict[Any, list[Mapping[str, Any]]] = {}
            if not legacy_entry_ids:
                for entry in model_entries:
                    by_requirement.setdefault(entry.get("requirement"), []).append(entry)
            imposed = []
            for entry in planned[entry_type]:
                matched = by_requirement.get(entry["requirement"])
                model_entry = matched.pop(0) if matched else by_id.get(entry[id_field])
                imposed.append({**entry, "reference": _as_map(model_entry).get("reference", "")})
            child[entry_type] = imposed
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
