"""Build NSC-077 rev 6, NSC-015 rev 9 and NSC-093 rev +1 from committed HEAD (exact-once edits; no repository writes)."""
from __future__ import annotations

import json
import pathlib
import subprocess

REPO = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")
OUT = pathlib.Path(r"C:\nscrev\ger-contract-revisions-20260916\followups-20260917")


def head_task(task_id: str) -> dict:
    return json.loads(subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:Tasks/{task_id}.yaml"],
                                     capture_output=True, creationflags=0x08000000, check=True).stdout)


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}: {old[:100]!r}")
    return text.replace(old, new)


def entry(task: dict, section: str, id_field: str, entry_id: str) -> dict:
    hits = [item for item in task[section] if item.get(id_field) == entry_id]
    if len(hits) != 1:
        raise SystemExit(f"expected one {entry_id} in {section}, found {len(hits)}")
    return hits[0]


def write(task: dict) -> None:
    path = OUT / f"{task['id']}.rev{task['contract_revision']}.json"
    path.write_text(json.dumps(task, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(path)


# NSC-077 revision 6: GUID-flexible rename, VAL-007 check, VAL-008 settled density wording.
t = head_task("NSC-077")
assert t["contract_revision"] == 5, t["contract_revision"]
ac7 = entry(t, "acceptance_criteria", "criterion_id", "AC-007")
ac7["requirement"] = once(
    ac7["requirement"],
    "move EnemyFireballCaster.cs and its .meta to EnemyLanternWispCaster.cs and EnemyLanternWispCaster.cs.meta so the script GUID survives,",
    "move EnemyFireballCaster.cs to EnemyLanternWispCaster.cs, moving its .meta with it so the script GUID survives when the executor can move .meta files (an execution pipeline that generates its own deterministic .meta instead is acceptable, because the rebuilt scene is the only reference and VAL-003 proves it has no missing scripts),",
    "077 AC-007")
val7 = entry(t, "completion_gates", "gate_id", "VAL-007")
val7["requirement"] = once(
    val7["requirement"],
    "and that EnemyLanternWispCaster.cs.meta keeps EnemyFireballCaster's GUID;",
    "and that the saved scene has no missing-script references after the rename, recording whether EnemyLanternWispCaster.cs.meta kept EnemyFireballCaster's GUID;",
    "077 VAL-007")
val8 = entry(t, "completion_gates", "gate_id", "VAL-008")
val8["requirement"] = once(
    val8["requirement"],
    "Sprite shimmer while moving belongs to the open pixel-density decision and is recorded there.",
    "Pixel density is settled at 64 pixels per unit (decision B); any remaining sprite shimmer is recorded for the Art Director rather than blocking approval.",
    "077 VAL-008")
t["contract_revision"] = 6
write(t)

# NSC-015 revision 9: defeat also suspends and resets EnemyLockedDoorAttack.
t = head_task("NSC-015")
assert t["contract_revision"] == 8, t["contract_revision"]
ac6 = entry(t, "acceptance_criteria", "criterion_id", "AC-006")
ac6["requirement"] = once(
    ac6["requirement"],
    "On EnemyHealth.Defeated, MeleeEnemyDefeatResponse calls MeleeEnemyAttack.ResetAttack(), stops EnemyPursuitMovement participation,",
    "On EnemyHealth.Defeated, MeleeEnemyDefeatResponse calls MeleeEnemyAttack.ResetAttack(), calls EnemyLockedDoorAttack.ResetAttack() and disables that component so no pending locked-door attack can damage a door after defeat, stops EnemyPursuitMovement participation,",
    "015 AC-006 defeat")
ac6["requirement"] = once(
    ac6["requirement"],
    "which restores only the movement-disable state it owns.",
    "which restores only the movement-disable state it owns and re-enables EnemyLockedDoorAttack.",
    "015 AC-006 reset")
val6 = entry(t, "completion_gates", "gate_id", "VAL-006")
val6["requirement"] = val6["requirement"].rstrip() + (
    " Also defeat an enemy while its EnemyLockedDoorAttack has a pending attack on a locked door and verify the door takes"
    " no further damage before ResetDefeatResponse(), and that after ResetDefeatResponse() the component is enabled again.")
t["contract_revision"] = 9
write(t)

# NSC-093 revision +1: INT-001 names NSC-077 (obligation text only; delivered scope unchanged).
t = head_task("NSC-093")
int1 = entry(t, "downstream_integration_obligations", "obligation_id", "INT-001")
int1["reference"] = once(int1["reference"], "NSC-094 runtime animation integration",
                         "NSC-077 runtime animation integration (NSC-094 superseded 2026-09-16)", "093 INT-001 reference")
int1["requirement"] = once(int1["requirement"], "NSC-094 imports only the approved 96 walk frames",
                           "NSC-077 imports only the approved 96 walk frames", "093 INT-001 requirement")
t["contract_revision"] = t["contract_revision"] + 1
write(t)
