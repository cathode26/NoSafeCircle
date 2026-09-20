"""Build the NSC-055 rev 3, NSC-015 rev 7 and NSC-094 rev 2 contracts from committed HEAD (no repository writes).

Every text edit must match its anchor exactly once. Output goes to C:\\nscrev\\ger-contract-revisions-20260916\\<ID>\\.
"""
from __future__ import annotations

import json
import pathlib
import subprocess

REPO = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")
OUT = pathlib.Path(r"C:\nscrev\ger-contract-revisions-20260916")


def head_task(task_id: str) -> dict:
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:Tasks/{task_id}.yaml"],
                          capture_output=True, creationflags=0x08000000, check=True).stdout
    return json.loads(blob)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}: {old[:80]!r}")
    return text.replace(old, new)


def write(task: dict) -> pathlib.Path:
    folder = OUT / task["id"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{task['id']}.rev{task['contract_revision']}.json"
    path.write_text(json.dumps(task, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def nsc055() -> pathlib.Path:
    task = head_task("NSC-055")
    assert task["contract_revision"] == 2, task["contract_revision"]
    task["contract_revision"] = 3
    deps = task["depends_on"]
    assert deps.count("NSC-094") == 1 and "NSC-077" not in deps, deps
    deps[deps.index("NSC-094")] = "NSC-077"
    task["notes"] = task["notes"].rstrip() + (
        " Revision 3 (2026-09-16): NSC-094 is superseded by NSC-077 revision 3, which supplies the Ranged Enemy idle"
        " and walk animation as LanternWraithAnimator.controller driven by EnemyAnimationController; this prefab reuses"
        " them read-only. Vincent decided on 2026-09-16 that the Ranged Enemy is the Lantern Wraith and that its"
        " projectile is a teal lantern wisp with unchanged gameplay, so this prefab presents the Lantern Wraith.")
    return write(task)


def nsc015() -> pathlib.Path:
    task = head_task("NSC-015")
    assert task["contract_revision"] == 6, task["contract_revision"]
    task["contract_revision"] = 7
    assert task["depends_on"].count("NSC-094") == 1, task["depends_on"]
    task["depends_on"] = [dep for dep in task["depends_on"] if dep != "NSC-094"]
    walk = [r for r in task["exclusive_resources"] if "MeleeEnemyWalkDirection" in r]
    assert len(walk) == 2, walk
    task["exclusive_resources"] = [r for r in task["exclusive_resources"] if "MeleeEnemyWalkDirection" not in r]

    ac4 = task["acceptance_criteria"][3]
    assert ac4["criterion_id"] == "AC-004"
    ac4["reference"] = replace_once(ac4["reference"], "NSC-039, NSC-077, NSC-089, and NSC-094 handoffs",
                                    "NSC-039, NSC-077, and NSC-089 handoffs", "AC-004 reference")

    ac7 = task["acceptance_criteria"][6]
    assert ac7["criterion_id"] == "AC-007"
    text = ac7["requirement"]
    text = replace_once(
        text,
        "MeleeEnemyDefeatResponse, the read-only NSC-077 Melee presentation output, and the read-only NSC-094 walk component/output.",
        "MeleeEnemyDefeatResponse, and the read-only NSC-077 enemy animation output (EnemyAnimationController with the generated MeleeEnemyAnimator.controller).",
        "AC-007 components")
    text = replace_once(
        text,
        "Do not edit NSC-077 or NSC-094 source, generated assets, stationary review prefab, builder, component, or review placement."
        " If the delivered NSC-094 EnemyWalkAnimation does not itself follow this enemy's movement, create"
        " Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/MeleeEnemyWalkDirection.cs and"
        " Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/MeleeEnemyWalkDirection.cs.meta; MeleeEnemyWalkDirection passes this"
        " enemy's NavMeshAgent.velocity each frame to the public direction input that NSC-094 delivers and edits no NSC-094 file."
        " If NSC-094 delivers no public direction input, stop for a resource decision instead of editing EnemyWalkAnimation.cs.",
        "Do not edit NSC-077's EnemyAnimationController, EnemyAnimationAssetBuilder or generated enemy animation assets."
        " EnemyAnimationController already follows this enemy's own movement and current target, so no separate walk-direction"
        " script is created.",
        "AC-007 walk direction")
    ac7["requirement"] = text

    val3 = task["completion_gates"][2]
    assert val3["gate_id"] == "VAL-003"
    text = val3["requirement"]
    text = replace_once(text, "world-space SpriteRenderer pivot/scale/sorting inherited from NSC-077, NSC-094 walk binding,",
                        "world-space SpriteRenderer pivot/scale/sorting and the MeleeEnemyAnimator binding inherited from NSC-077,",
                        "VAL-003 binding")
    text = replace_once(text,
                        ", no enemy-body Collider added without Vincent's approval, and no gameplay component added to NSC-077's stationary review prefab.",
                        ", and no enemy-body Collider added without Vincent's approval.",
                        "VAL-003 review prefab")
    val3["requirement"] = text

    notes = task["notes"]
    notes = replace_once(notes, "it owns MeleeEnemyDefeatResponse, the conditional MeleeEnemyWalkDirection, Melee-specific movement serialization,",
                         "it owns MeleeEnemyDefeatResponse, Melee-specific movement serialization,", "notes split 2")
    notes = replace_once(notes, "It additionally depends on NSC-003, NSC-011, NSC-013, NSC-039, NSC-077, and NSC-094.",
                         "It additionally depends on NSC-003, NSC-011, NSC-013, NSC-039, and NSC-077.", "notes dependencies")
    notes = replace_once(notes, "ProjectSettings, NSC-077 outputs, NSC-094 outputs, room/scene assets,",
                         "ProjectSettings, NSC-077 outputs, room/scene assets,", "notes outputs")
    task["notes"] = notes.rstrip() + (
        " Revision 7 (2026-09-16): NSC-094 is superseded by NSC-077 revision 3, which delivers EnemyAnimationController and the"
        " generated MeleeEnemyAnimator.controller for the existing scene MeleeEnemy. This prefab reuses them, so the conditional"
        " MeleeEnemyWalkDirection script and its resource claims are removed.")

    serialized = json.dumps(task, ensure_ascii=False)
    for leftover in ("NSC-094", "MeleeEnemyWalkDirection", "stationary review prefab", "EnemyWalkAnimation"):
        if leftover in serialized.replace("Revision 7 (2026-09-16): NSC-094 is superseded", "").replace(
                "so the conditional MeleeEnemyWalkDirection script", ""):
            raise SystemExit(f"NSC-015 still mentions {leftover!r}")
    return write(task)


def nsc094() -> pathlib.Path:
    task = head_task("NSC-094")
    assert task["contract_revision"] == 1 and task["contract_disposition"] == "active"
    rebuilt = {}
    for key, value in task.items():
        rebuilt[key] = value
        if key == "contract_disposition":
            rebuilt[key] = "superseded"
            rebuilt["superseded_by"] = "NSC-077"
    rebuilt["contract_revision"] = 2
    rebuilt["exclusive_resources"] = []
    rebuilt["notes"] = (
        "Superseded by NSC-077 contract revision 3 on 2026-09-16 at Vincent's direction: NSC-077 now puts the approved enemy"
        " idle and walk art, including this task's walk animation scope, on the existing scene enemies. Do not implement this"
        " task; its resource claims are released. " + task["notes"])
    return write(rebuilt)


if __name__ == "__main__":
    for build in (nsc055, nsc015, nsc094):
        print(build())
