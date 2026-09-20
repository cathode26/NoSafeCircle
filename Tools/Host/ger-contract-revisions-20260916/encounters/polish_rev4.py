"""Owner review edits to the drafted NSC-030 revision 4 (exact-once replacements; writes the draft file in place)."""
from __future__ import annotations

import json
import pathlib

PATH = pathlib.Path(r"C:\nscrev\ger-contract-revisions-20260916\encounters\NSC-030.rev4.json")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}: {old[:90]!r}")
    return text.replace(old, new)


def entry(entries: list, id_field: str, entry_id: str) -> dict:
    found = [item for item in entries if item.get(id_field) == entry_id]
    if len(found) != 1:
        raise SystemExit(f"expected one {entry_id}, found {len(found)}")
    return found[0]


task = json.loads(PATH.read_text(encoding="utf-8"))

ac1 = entry(task["acceptance_criteria"], "criterion_id", "AC-001")
ac1["requirement"] = replace_once(
    ac1["requirement"], "and any Vincent-approved Lower Vault mixed roster", "and the Lower Vault mixed roster", "AC-001")

ac4 = entry(task["acceptance_criteria"], "criterion_id", "AC-004")
ac4["requirement"] = replace_once(
    ac4["requirement"], "records its Vincent-approved activation trigger or triggers and authored spawn/reset region",
    "records its approved activation trigger or triggers and authored spawn/reset region (starting values in this contract's notes)",
    "AC-004")

ac8 = entry(task["acceptance_criteria"], "criterion_id", "AC-008")
ac8["requirement"] = replace_once(
    ac8["requirement"],
    "After Vincent approves the door-durability applicability and value table, store that table as the authoring source of truth in",
    "Store the door-durability value table (D1 through D4 values, D5 exempt; starting values in this contract's notes) as the authoring source of truth in",
    "AC-008 table")
ac8["requirement"] = replace_once(
    ac8["requirement"], "applies each approved value to the existing serialized maxDurability field while creating D1 through D5,",
    "applies each D1-D4 value to the existing serialized maxDurability field while creating the doors and leaves D5 without an encounter-authored value,",
    "AC-008 apply")

val1 = entry(task["completion_gates"], "gate_id", "VAL-001")
text = val1["requirement"]
text = replace_once(text, "valid delivered gameplay-prefab references; and the Vincent-approved Lower Vault roster.",
                    "valid delivered gameplay-prefab references; and the approved Lower Vault roster.", "VAL-001 roster")
text = replace_once(text, "lie inside the Vincent-approved region boundaries recorded for that room.",
                    "lie inside the approved region boundaries recorded for that room, at least 6 units from that room's entry door center (from PlayerStart in Ruined Entry).",
                    "VAL-001 region")
text = replace_once(
    text,
    "Compare every applicable D1-D5 DoorInteractable.MaxDurability value in the committed scene with the literal Vincent-approved values recorded in the durability child's contract, including the approved D5 inclusion or exemption.",
    "Compare every D1-D4 DoorInteractable.MaxDurability value in the committed scene with the literal values recorded in the durability child's contract (starting values D1 60, D2 80, D3 100, D4 120) and verify the table has no D5 entry.",
    "VAL-001 durability")
val1["requirement"] = text

notes = task["notes"]
notes = replace_once(
    notes,
    "it does not edit Assets/NoSafeCircle/DoorPrototype/Scripts/EncounterAdmissionController.cs unless Vincent's approved policy requires a reviewed NSC-028-owned interface change.",
    "AC-006's cancel-on-exit and retry-when-capacity-frees policy needs a reviewed change to Assets/NoSafeCircle/DoorPrototype/Scripts/EncounterAdmissionController.cs, which NSC-028 owns; D1B.2 routes that interface change as NSC-028-owned work ahead of the materialization child, and no encounter child edits that file directly.",
    "notes admission")
notes = notes.rstrip() + (
    " Until child 7 lands, DoorPrototypeGlobalSceneBuilder.BuildChaseEnemies' fixed enemy positions assume the pre-2026-09-15 room"
    " table, so the rebuild of Bone Archive through Final Room must keep each of those enemies inside its intended room (NSC-049"
    " composed-scene follow-up). Rosters, triggers, regions and durability values are GER owner decisions made under Vincent's"
    " 2026-09-15 delegation (C:\\nscrev\\ger-contract-revisions-20260916\\encounters\\NSC-030_DECISIONS.md); VAL-007 tunes them.")
task["notes"] = notes

serialized = json.dumps(task, ensure_ascii=False)
for stale in ("Vincent-approved", "After Vincent approves", "Vincent's approved policy"):
    if stale in serialized:
        raise SystemExit(f"stale wording remains: {stale!r}")
PATH.write_text(json.dumps(task, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("polished", PATH)
