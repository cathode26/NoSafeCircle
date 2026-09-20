"""Record Vincent's 2026-09-14 room decisions in the NSC-069 and NSC-049 task contracts.

Edits only the named fields, keeps each file's key order and line endings, and refuses when a
file does not round-trip byte-for-byte before editing or an expected old text is not exact.
Does not commit; run taskcontrol validate and commit separately.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")
DECISION = {"date": "2026-09-14", "decided_by": "Vincent",
            "record": "graph-lead-journal GER queue status; GDD blockout section 13 Room size authority"}


def load(task_id: str) -> tuple[pathlib.Path, bytes, dict, bool]:
    path = REPO / "Tasks" / f"{task_id}.yaml"
    raw = path.read_bytes()
    crlf = b"\r\n" in raw
    data = json.loads(raw)
    if dump(data, crlf) != raw:
        raise SystemExit(f"{task_id} does not round-trip byte-for-byte; refusing to edit")
    return path, raw, data, crlf


def dump(data: dict, crlf: bool) -> bytes:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


def entry(entries: list, key: str, ident: str) -> dict:
    matches = [item for item in entries if item.get(key) == ident]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one {ident}, found {len(matches)}")
    return matches[0]


def replace_requirement(item: dict, old_prefix: str, new_text: str) -> None:
    if not item["requirement"].startswith(old_prefix):
        raise SystemExit(f"unexpected current text for {item}: {item['requirement'][:120]!r}")
    item["requirement"] = new_text


def main() -> int:
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain=v1", "--", "Tasks/NSC-069.yaml",
                            "Tasks/NSC-049.yaml"], capture_output=True, text=True).stdout.strip()
    if dirty:
        raise SystemExit(f"target contracts already have uncommitted changes:\n{dirty}")

    path69, _, t69, crlf69 = load("NSC-069")
    if t69["contract_revision"] != 4:
        raise SystemExit(f"NSC-069 revision is {t69['contract_revision']}, expected 4")
    replace_requirement(
        entry(t69["acceptance_criteria"], "criterion_id", "AC-006"),
        "Establish and validate the exact disjoint ownership seams consumed by NSC-044 through NSC-048.",
        "Establish and validate the exact disjoint ownership seams consumed by NSC-044 through NSC-048. Each room "
        "task may create and save only its own scene, builder, layout data, tests, and generated .meta companions; "
        "it may not edit an asmdef, common contract, common composer, DoorPrototypeSceneBuilder, DoorPrototype.unity, "
        "or another room's files. As the one catalog exception (Vincent, 2026-09-14), a room task may edit its own "
        "room's RoomBounds entry and the center of its own exit door in RoomSceneCatalog.cs and regenerate "
        "RoomSceneCatalog.asset, within the GDD room size authority; room tasks take turns on those shared catalog "
        "files, and NSC-049 reconciles shared boundaries and door alignment during composition.")
    t69["contract_revision"] = 5
    t69["notes"] = (t69["notes"].rstrip() + " Vincent approved the room-task catalog exception in AC-006 on "
                    "2026-09-14 so Task Design GER room revisions can resize rooms within the GDD room size authority.")
    t69["provenance"]["design_decisions"] = list(t69["provenance"].get("design_decisions") or []) + [{
        **DECISION, "decision": "Room tasks NSC-044 to NSC-048 may edit their own RoomSceneCatalog bounds entry and "
                                "exit-door center; NSC-049 reconciles shared boundaries and door alignment."}]

    path49, _, t49, crlf49 = load("NSC-049")
    if t49["contract_revision"] != 3:
        raise SystemExit(f"NSC-049 revision is {t49['contract_revision']}, expected 3")
    replace_requirement(
        entry(t49["acceptance_criteria"], "criterion_id", "AC-001"),
        "Integrate the five authored room blockouts into the canonical continuous gameplay scene/floor at their approved global bounds",
        "Integrate the five authored room blockouts into the canonical continuous gameplay scene/floor at the room "
        "bounds and door centers recorded in RoomSceneCatalog, which NSC-044 through NSC-048 may revise within the GDD "
        "room size authority; reconcile shared boundaries, wall jogs, and door alignment here, without room scene loads "
        "or cross-scene state transfer.")
    replace_requirement(
        entry(t49["completion_gates"], "gate_id", "VAL-001"),
        "Committed-scene validation verifies all five room shells and D1 through D5 coexist at their approved coordinates",
        "Committed-scene validation verifies all five room shells and D1 through D5 coexist at the bounds and door "
        "centers recorded in RoomSceneCatalog in the canonical continuous floor, that adjoining rooms share their "
        "boundary with matching door openings, and that visible architecture corresponds to separately authored "
        "gameplay geometry without scene loading.")
    if any(item["criterion_id"] == "AC-003" for item in t49["acceptance_criteria"]) or \
            any(item["gate_id"] == "VAL-003" for item in t49["completion_gates"]):
        raise SystemExit("NSC-049 already has AC-003 or VAL-003")
    t49["acceptance_criteria"].append({
        "criterion_id": "AC-003",
        "reference": "Vincent decision 2026-09-14 (player start ownership); GDD — Approved Five-Room Spatial Layout Blockout §3 START",
        "requirement": "When composing Assets/Scenes/DoorPrototype.unity, move the existing Player root and PlayerSpawn to "
                       "the Ruined Entry start point that NSC-044 records in "
                       "Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms/RuinedEntryLayout.cs, through "
                       "DoorPrototypeGlobalSceneBuilder, without creating a second Player or PlayerSpawn."})
    t49["completion_gates"].append({
        "gate_id": "VAL-003",
        "reference": "AC-003",
        "requirement": "An Edit Mode test in Assets/NoSafeCircle/DoorPrototype/Tests/Editor/World/FiveRoomCompositionTests.cs "
                       "composes the canonical scene and verifies exactly one Player and one PlayerSpawn, both at the "
                       "start point read from RuinedEntryLayout.cs."})
    builder = "repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs"
    if builder not in t49["exclusive_resources"]:
        t49["exclusive_resources"].insert(1, builder)
    t49["contract_revision"] = 4
    t49["provenance"]["design_decisions"] = list(t49["provenance"].get("design_decisions") or []) + [{
        **DECISION, "decision": "Compose at RoomSceneCatalog bounds revised by room tasks; NSC-049 places the Player "
                                "and PlayerSpawn at the start point NSC-044 records in RuinedEntryLayout.cs."}]

    groups_path = REPO / "Pipeline" / "TaskGraph" / "RESOURCE_GROUPS.yaml"
    groups_raw = groups_path.read_bytes()
    groups_crlf = b"\r\n" in groups_raw
    groups = json.loads(groups_raw)
    if dump(groups, groups_crlf) != groups_raw:
        raise SystemExit("RESOURCE_GROUPS.yaml does not round-trip byte-for-byte; refusing to edit")
    found = []
    stack = [groups]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if item.get("resource_key") == builder:
                found.append(item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    if len(found) != 1:
        raise SystemExit(f"expected one resource group for {builder}, found {len(found)}")
    group = found[0]
    if "NSC-049" not in group["work_ids"]:
        group["work_ids"].append("NSC-049")
    if t49["reconciliation_key"] not in group["reconciliation_keys"]:
        group["reconciliation_keys"].append(t49["reconciliation_key"])

    path69.write_bytes(dump(t69, crlf69))
    path49.write_bytes(dump(t49, crlf49))
    groups_path.write_bytes(dump(groups, groups_crlf))
    stat = subprocess.run(["git", "-C", str(REPO), "diff", "--stat", "--", "Tasks/NSC-069.yaml", "Tasks/NSC-049.yaml",
                           "Pipeline/TaskGraph/RESOURCE_GROUPS.yaml"],
                          capture_output=True, text=True).stdout
    print(stat.strip())
    print("[DONE] NSC-069 -> revision 5, NSC-049 -> revision 4 written (not committed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
