# Decisions applied — NSC-015 rev 8 / NSC-017 rev 5

## Why

Codex contract check of NSC-015 revision 7 (commit `50753aa52`) returned
"revise" (`C:\nscrev\codex-jobs\codex-contract-check-NSC-015-rev7-20260917.report.md`).
Blocking finding: NSC-017 INT-001 required the prefab-assembly split to depend
on NSC-017 and attach the existing `EnemyLockedDoorAttack`, and assumed a
third prefab owner; NSC-015 omitted that dependency/component and prescribed
two splits. Both contracts had to agree before NSC-015's D1B.2 decomposition
rerun.

## Decisions (quoted exactly as given, applied in full)

### 1. NSC-015 revision 8

> Add "NSC-017" to depends_on. Check that this creates no cycle.
> In AC-007, add EnemyLockedDoorAttack to the components the generated MeleeEnemyGameplay prefab contains and wires (it already exists at Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/EnemyLockedDoorAttack.cs).
> In VAL-003's prefab conformance, add exactly one EnemyLockedDoorAttack, with its required collaborators resolved on the same prefab.
> In notes:
> - split 2 owns EnemyLockedDoorAttack wiring and conformance and additionally depends on NSC-017;
> - D1B.2 still produces exactly two ordered splits;
> - NSC-017's behavior code is not edited, so EnemyLockedDoorAttack.cs stays NSC-017's file and NSC-015 only attaches and wires the component.
> Change no other requirement.

Applied in full — see `NSC-015.change-log.md` for the exact before/after text
of `depends_on`, `AC-007`, `VAL-003`, and `notes`.

### 2. NSC-017 revision +1 (revision 5)

> Reword INT-001 so the Melee Enemy prefab ownership matches NSC-015's two splits: NSC-015's prefab-assembly split (split 2) attaches EnemyLockedDoorAttack to the generated Melee Enemy gameplay prefab and proves the wiring; there is no third prefab owner.
> Keep, word for word, every part of INT-001 about the Ranged Enemy (its locked-door approach, keep-distance yielding and door-attack form stay unresolved until Vincent decides, and NSC-055 must not assume that wiring).
> Change nothing else.

Applied in full — see `NSC-017.change-log.md`. Verified the Ranged Enemy
sentence is byte-identical between revision 4 and revision 5.

### 3. NSC-015 INT-002 (mid-task addition, relayed by the coordinator)

> One additional settled change for NSC-015 revision 8, from the NSC-030 Codex check (C:\nscrev\codex-jobs\codex-contract-check-NSC-030-rev4-20260917.report.md, minor finding):
> NSC-015 INT-002 currently tells NSC-030 to call ActiveEnemyRegistry.Register directly. Reword it: NSC-030's encounter work submits the prefab instance through EncounterAdmissionController.RequestAdmission, and the controller registers the enemy only after admission. Keep everything else in INT-002 unchanged, and list this change in the change log.

Applied in full — see `NSC-015.change-log.md`. Confirmed
`EncounterAdmissionController.RequestAdmission` is a real production method
(`Assets/NoSafeCircle/DoorPrototype/Scripts/EncounterAdmissionController.cs`)
already referenced by `Tasks/NSC-030.yaml`, so no API was invented.

## Open questions for the GER Agent

None — all three decisions were fully specified and applied without needing
a design call from me. One item surfaced by the required cascade grep is
worth the GER Agent's attention even though it is out of scope for this
draft (see final report: NSC-053 already assumes NSC-017 defines Ranged
Enemy locked-door behavior, which Decision 2 explicitly keeps unresolved).
