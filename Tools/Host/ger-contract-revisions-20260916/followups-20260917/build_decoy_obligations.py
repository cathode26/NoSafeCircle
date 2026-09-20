"""NSC-088 revision 4 R-07 follow-ups: NSC-006 rev 3 (notes), NSC-087 rev 2 and NSC-086 rev 2 (Spectral Decoy suspension)."""
import json
import pathlib
import subprocess

REPO = r"C:\NSC\NSC\NoSafeCircle"
OUT = pathlib.Path(__file__).resolve().parent / "decoy-obligations"
OUT.mkdir(exist_ok=True)


def load(task: str) -> dict:
    return json.loads(subprocess.run(["git", "-C", REPO, "show", f"HEAD:Tasks/{task}.yaml"], capture_output=True, creationflags=0x08000000, check=True).stdout)


def rep(entry: dict, field: str, old: str, new: str) -> None:
    assert entry[field].count(old) == 1, (field, entry[field].count(old), old[:90])
    entry[field] = entry[field].replace(old, new)


def by_id(items: list, key: str, ident: str) -> dict:
    found = [x for x in items if x[key] == ident]
    assert len(found) == 1, ident
    return found[0]


# NSC-006 revision 3 (mechanical wording)
nsc006 = load("NSC-006")
assert nsc006["contract_revision"] == 2
rep(nsc006, "notes", "The three required spell children are Fireball, Frost Field, and Force Wave. NSC-088 records a separate design-pending Spectral Decoy stretch goal; it is not a fourth required spell or authorized implementation work.",
    "The spell children are Fireball (NSC-007), Frost Field (NSC-008), Force Wave (NSC-009), and the Spectral Decoy (NSC-088). Vincent approved the Spectral Decoy on 2026-09-15, made all former stretch goals goals on 2026-09-17 (GDD 294e5d3fa), and delegated its spell design; NSC-088 revision 4 is decided and awaits its own execution decomposition.")
rep(nsc006, "decomposition_reason", "The three required spells remain independently concrete. This organizational node also groups the design-pending Spectral Decoy stretch task; the grouping itself is not executable and does not need decomposition.",
    "The four spells remain independently owned: Fireball, Frost Field, and Force Wave are concrete, and the Spectral Decoy (NSC-088) carries its own execution decomposition. This organizational node only groups them; the grouping itself is not executable and does not need decomposition.")
nsc006["contract_revision"] = 3
(OUT / "NSC-006.rev3.json").write_text(json.dumps(nsc006, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# NSC-087 revision 2
nsc087 = load("NSC-087")
assert nsc087["contract_revision"] == 1
ac1 = by_id(nsc087["acceptance_criteria"], "criterion_id", "AC-001")
rep(ac1, "requirement", "Frost Field from NSC-008, and Force Wave from NSC-009.",
    "Frost Field from NSC-008, Force Wave from NSC-009, and Spectral Decoy from NSC-088 (SpectralDecoy.SuspendGameplayInput(), which also ends an active phantom through the enemy-owned return API).")
ac2 = by_id(nsc087["acceptance_criteria"], "criterion_id", "AC-002")
rep(ac2, "requirement", "The coordinator calls only the five gameplay owners' public suspend and re-enable methods.",
    "The coordinator calls only the six gameplay owners' public suspend and re-enable methods.")
rep(ac2, "requirement", "spell charge or cast state, cooldown state,", "spell charge or cast state, phantom or redirect state, cooldown state,")
ac3 = by_id(nsc087["acceptance_criteria"], "criterion_id", "AC-003")
rep(ac3, "requirement", "That method calls each gameplay owner's public re-enable method,",
    "That method calls each gameplay owner's public re-enable method, including SpectralDecoy.EnableGameplayInput(),")
val1 = by_id(nsc087["completion_gates"], "gate_id", "VAL-001")
rep(val1, "requirement", "Fireball, Frost Field, and Force Wave each stop that behavior immediately.",
    "Fireball, Frost Field, Force Wave, and Spectral Decoy each stop that behavior immediately; for Spectral Decoy an active phantom ends and every redirected enemy leaves its decoy redirect through EnemyTargetKnowledge's owner API.")
val2 = by_id(nsc087["completion_gates"], "gate_id", "VAL-002")
rep(val2, "requirement", "movement, door-interaction, and spell input has no gameplay effect",
    "movement, door-interaction, and spell input, including the Spectral Decoy action, has no gameplay effect")
nsc087["depends_on"] = nsc087["depends_on"] + ["NSC-088"]
nsc087["notes"] += (" Revision 2 (2026-09-17): adds the Spectral Decoy as the sixth suspended owner and NSC-088 to depends_on, "
                    "recording NSC-088 revision 4 INT-002.")
nsc087["contract_revision"] = 2
(OUT / "NSC-087.rev2.json").write_text(json.dumps(nsc087, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# NSC-086 revision 2
nsc086 = load("NSC-086")
assert nsc086["contract_revision"] == 1
ac3 = by_id(nsc086["acceptance_criteria"], "criterion_id", "AC-003")
rep(ac3, "requirement", "Fireball, Frost Field, or Force Wave suspend methods itself.",
    "Fireball, Frost Field, Force Wave, or Spectral Decoy suspend methods itself.")
ac5 = by_id(nsc086["acceptance_criteria"], "criterion_id", "AC-005")
rep(ac5, "requirement", "Fireball, Frost Field, and Force Wave components",
    "Fireball, Frost Field, Force Wave, and SpectralDecoy components")
val1 = by_id(nsc086["completion_gates"], "gate_id", "VAL-001")
rep(val1, "requirement", "active input-driven behavior on Fireball, Frost Field, and Force Wave.",
    "active input-driven behavior on Fireball, Frost Field, and Force Wave, and ends an active Spectral Decoy phantom so every redirected enemy leaves its decoy redirect through EnemyTargetKnowledge's owner API.")
val2 = by_id(nsc086["completion_gates"], "gate_id", "VAL-002")
rep(val2, "requirement", "movement, door-interaction, and spell input has no gameplay effect",
    "movement, door-interaction, and spell input, including the Spectral Decoy action, has no gameplay effect")
rep(nsc086, "notes", "calls one coordinator method instead of duplicating five gameplay-owner calls.",
    "calls one coordinator method instead of duplicating six gameplay-owner calls. Revision 2 (2026-09-17) adds the Spectral Decoy, recording NSC-088 revision 4 INT-002.")
nsc086["contract_revision"] = 2
(OUT / "NSC-086.rev2.json").write_text(json.dumps(nsc086, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("wrote NSC-006.rev3, NSC-087.rev2, NSC-086.rev2")
