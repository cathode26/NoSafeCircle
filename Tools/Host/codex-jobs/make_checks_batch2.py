"""Fill the contract-check template for a batch of revisions and write a sequential runner script."""
import pathlib

ROOT = pathlib.Path(r"C:\nscrev\codex-jobs")
TEMPLATE = (ROOT / "templates" / "contract-recheck-prompt.md").read_text(encoding="utf-8")

BATCH = [
    ("NSC-077", "rev6", "3eb886805c9d6e10381afc67b6d6bd4ba2fe0d9a",
     "Enemy art integration for the existing moving enemies (Vincent 2026-09-16), with the Lantern Wraith decision and pixel-density decision B, all settled. "
     "Revision 6 (commit 3eb886805) answers the revision 5 check (report C:/nscrev/codex-jobs/codex-contract-check-NSC-077-rev5-20260917.report.md): "
     "the EnemyFireballCaster.cs to EnemyLanternWispCaster.cs rename keeps the script GUID when the executor can move .meta files and accepts a pipeline-generated .meta otherwise, "
     "because the rebuilt scene is the only reference and VAL-003 proves no missing scripts; VAL-007 records whether the GUID was kept; VAL-008 states pixel density is settled at 64 PPU. "
     "The implementation already exists on branch codex/nsc077-moving-enemy-art-20260917 and waits for this verdict before Vincent tests it.",
     "NSC-015 revision 9 and NSC-093 revision 2 (committed right after this one)"),
    ("NSC-015", "rev9", "512cb1b203175453782e446838c0e1ec9859802b",
     "Melee Enemy pursuit, close-range attack and gameplay prefab; waits for D1B.2 decomposition into two splits. "
     "Revision 9 (commit 512cb1b20) answers the revision 8 check (report C:/nscrev/codex-jobs/codex-contract-check-NSC-015-rev8-20260917.report.md): "
     "MeleeEnemyDefeatResponse also calls EnemyLockedDoorAttack.ResetAttack() and disables that component on defeat, re-enables it in ResetDefeatResponse(), "
     "and VAL-006 proves a locked door takes no damage after the enemy is defeated mid-attack. Revision 8 added the NSC-017 dependency and EnemyLockedDoorAttack wiring.",
     "NSC-077 revision 6 (just before), NSC-093 revision 2 (just after), NSC-017 revision 5 (earlier today)"),
    ("NSC-030", "rev5", "5c81b33c95f04ae8c39b6622988ed3d33bff846c",
     "Room enemy encounters feature node, held for D1B.2 decomposition. The GER owner's settled decisions are in C:/nscrev/ger-contract-revisions-20260916/encounters/NSC-030_DECISIONS.md. "
     "Revision 5 (commit 5c81b33c9) answers the revision 4 check (report C:/nscrev/codex-jobs/codex-contract-check-NSC-030-rev4-20260917.report.md): "
     "an owner-authorized prerequisite child (1B) adds a room-batch admission-cancellation API and capacity-freed retry to EncounterAdmissionController; "
     "reset proof uses the authored initial position EnemyPursuitMovement captures in Awake; every configured enemy position is checked; the Chapel line check has explicit heights and trigger policy; "
     "the Lower Vault trigger fires on entry before the D3 breach; natural traversal must fire each trigger; INT-006 records the fixed-squad recomposition obligation. "
     "The GDD changed at commit 294e5d3fa (stretch goals are goals; enemy counts and the cap are balance levers Vincent may raise).",
     "none directly; NSC-015 revision 9 and NSC-077 revision 6 were committed after it"),
]

lines = ["#!/usr/bin/env bash", "set -u"]
for task, rev, sha, reason, others in BATCH:
    job = f"codex-contract-check-{task}-{rev}-20260917"
    text = (TEMPLATE.replace("<TASK_ID>", task)
            .replace("<ONE_PARAGRAPH_REASON_AND_VINCENTS_WORDS>", reason)
            .replace("<OTHER_TASK_IDS_OR_NONE>", others))
    assert "<TASK_ID>" not in text and "<ONE_PARAGRAPH" not in text
    (ROOT / f"{job}.prompt.md").write_text(text, encoding="utf-8")
    lines.append(f"bash C:/nscrev/codex-jobs/run_contract_check.sh {job} {task} {sha}")
    print("prompt", job)
(ROOT / "run_checks_batch2.sh").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("runner written")
