# NSC-030 encounter design decisions

GER Orchestrator (Claude), 2026-09-16, deciding questions 13-19 that Vincent delegated on 2026-09-15, plus one sequencing question surfaced by research. Sources:
- GER packet `20260914-065035-NSC-030`;
- `C:\nscrev\reports\ger-overnight-20260914.md`, questions 13-19;
- the brief `C:\nscrev\ger-contract-revisions-20260916\briefs\encounters-030.md`;
- local main `95492e43d`;
- the room contracts committed 2026-09-15 (NSC-044 rev 5, NSC-045 rev 4, NSC-046 rev 6, NSC-047 rev 4, NSC-048 rev 4).

Guiding rules:
- **The GDD.** Enemies left alive are a persistent consequence. Doors buy time, not safety. Ruined Entry teaches circling a Melee Enemy, and Chapel of Ash introduces the Ranged Enemy with Melee support. The Final Room is a pressured five-second escape window with no waves.
- **Keep it small.** Add no new mechanics.

## 13. Pending enemies from rooms the wizard has left
- **Cancel on exit.** When a room's exit door locks behind the wizard, meaning the forward crossing that locks D1-D4, every enemy from that room's admission request that is still pending is cancelled: it never activates during the rest of the floor run. Enemies already active from that room are unaffected; they persist and pursue as the GDD requires.
- **Retry when a slot frees.** Pending admissions are retried in request order whenever registry capacity frees, for example when an enemy is defeated, and on every new request.
- **Why.** Under strict FIFO, a Chapel batch still pending after D3 locks would activate behind a locked door in an empty room and hold registry slots the Final Room's required mixed pressure needs. Nothing was ever on screen, so cancelling it removes no visible consequence.
- **In the contract.** VAL-003 and VAL-004 assert this single result.

## 14. Ranged support under the 15-enemy cap
- **Listed order is enough.** Every mixed request lists its Melee Enemies before its Ranged Enemies. `ProcessPendingAdmissions` admits in list order and stops at capacity, so a Melee Enemy from the same batch always activates first.
- **No extra gate.** There is no "wait for an active ally" rule.

## 15. Rosters (starting values for the per-room children, sized to the approved room table)
Vincent's VAL-007 play review tunes these; they are starting values, not canon.

| Room | Approved bounds | Roster |
|---|---|---|
| Ruined Entry | 28x26 | 3 Melee |
| Bone Archive | 24x20 | 4 Melee |
| Chapel of Ash | 36x34 | 3 Melee + 2 Ranged, Melee listed first |
| Lower Vault | 40x22 | 2 Melee + 1 Ranged |
| Final Room | 30x28 | 2 Melee + 2 Ranged |

- **Ruined Entry.** The minimum AC-002 allows. Whether three still teach circling is VAL-007's human check.
- **Lower Vault.** Deliberately lean: with earlier survivors (3+4+5) the registry reaches exactly 15, so a D3 rear breach exercises the decision 13 behavior.
- **Final Room.** Both enemy types, plus whatever pursuers survived.
- **Ranged means the Lantern Wraith.** Vincent, 2026-09-16: the Ranged Enemy is the Lantern Wraith. NSC-030 text stays generic ("Ranged Enemy") and names no concrete caster class.

## 16. Triggers and spawn/reset regions
- **Triggers.**
  - One activation trigger per room, on that room's own entry-side landing: Bone Archive's D1 entry area (NSC-045 AC-002), Chapel's D2 landing (NSC-046 AC-001) and Lower Vault's D3 apron (NSC-047 AC-002).
  - Final Room: the per-room child defines a landing of about 4x4 units on the Final Room side of D4, inside walkable floor, clear of FR-1 and of D5's staging rectangle.
  - Ruined Entry has no entry door, so its trigger sits inside its own loop geometry, away from PlayerStart, and fires once the wizard commits toward the rubble.
- **Spawn/reset regions.** A room's spawn/reset region is its walkable interior, minus authored obstacle footprints, minus every door opening, minus every exit-side door staging rectangle.
- **Spawn distance.** Every spawn position is at least 6 horizontal units from the room's entry door center, or from PlayerStart in Ruined Entry, so enemies never appear on top of the wizard.
- **Triggers vs. exit rectangles.** A trigger never overlaps an exit-side staging rectangle.

## 17. Chapel Ranged spawn cover rule
- **The rule.** From every Chapel of Ash Ranged Enemy spawn position, at least one of cover pockets CA-W or CA-E is occluded by a real pew or column collider. This is the GDD:379 wording that NSC-046 rev 6 VAL-001 already proves for the room.
- **What goes.** The round-03 dual-pocket rule, where both must be occluded, is replaced by this.

## 18. Door durability (first-pass tuning)
- **D1-D4.** D1 = 60, D2 = 80, D3 = 100, D4 = 120: a rising curve, so later doors buy more time as surviving pursuers accumulate.
- **D5.** Exempt, no value: crossing D5 ends gameplay.
- **Where the values live.** `DoorSequenceBuilder` becomes the source of truth for these values. Encounter work never edits `DoorInteractable`'s durability, damage or break logic.

## 19. Final Room pressure
- **No waves.** The fixed mixed roster from decision 15, plus the persistent pursuers still alive or pending from earlier rooms, while the wizard holds the D5 five-second attempt.
- **Nothing extra.** No waves, reinforcements or staged spawns, since the GDD excludes them.

## 20 (new). Sequencing against rooms not yet built, and the playable build's fixed squad
- **What can start now.** The shared encounter data and committed-content validator child (split item 1) needs no room geometry.
- **What must wait.** Each per-room child (split items 2-6) waits until that room's rebuilt scene and `RoomSceneCatalog` actually hold its 2026-09-15 approved bounds, not merely until the room contract is committed. Its gates open the committed scene through the production catalog.
- **The fixed squad.**
  - Today `DoorPrototypeGlobalSceneBuilder.BuildChaseEnemies` places 5 MeleeEnemy and 4 FireCasterEnemy (becoming LanternWraith under NSC-077 rev 3) at fixed positions, with no registry, admission or trigger.
  - NSC-030's canonical-scene materialization child (split item 7) replaces that squad with encounter-admitted enemies, whose prefabs reuse NSC-077's enemy animation (NSC-077 INT-001).
  - Until then the squad stays. Its positions were computed against the old room table, so the room rebuild must keep each of those enemies inside its intended room. This is recorded as a follow-up for NSC-049's composed-scene reconciliation.

## Non-design fixes applied
- **Verbatim fixes.** R-03 (reset handoff through NSC-033, not NSC-092), R-04, R-05, R-06, R-07, R-08, R-09 and R-10 (NSC-089 in INT-005), as quoted in round 04.
- **Replaced by decisions.** R-02's AC-006 either/or is replaced by decision 13. R-01's VAL-005 becomes decision 17's rule.
- **Decomposition.** This task remains a feature node needing D1B.2 decomposition, so after commit it stays held and goes to the Decomposition Orchestrator.
