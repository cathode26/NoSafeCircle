# Viewer Agent: graph evidence-debt audit

Requested by: GER Agent, relaying Vincent's direct ask ("Can we do an audit, the viewer agent was asked to be an auditor and fix everything"). Brief: `C:\nscrev\reports\handoffs\viewer-agent-evidence-debt-audit-20260918.md`.

Read-only. This report is a list, not a fix. HEAD at audit time: `91a415ab9f51e82b6ef5464061dc54ef40413dc7` (local main).

Method: for each `not_delivered` task, loaded its committed contract (`git show HEAD:Tasks/NSC-###.yaml`), took every `repo-file:` and `unity-scene:` entry from `exclusive_resources` (`logical:` claims are not files and were excluded), and checked each path's existence at `HEAD` with `git cat-file -e` — never a filename search, so the partial-class trap from 2026-09-18 doesn't apply here. Dependency conformance and "unblocks" counts come from a full `depends_on` graph built from every committed contract (not just the 51), cross-referenced against `taskcontrol.py states`. Record status/approval read from `.assistant-control\NSC-###.json` where present. Validation-policy presence checked against `Pipeline\TaskReviewAgent\authoritative_validation_policy.json`.

## Summary

`taskcontrol.py states` (95 tasks): 17 conformant, 24 aggregate, 1 needs_replan, 2 needs_testing, 1 superseded, **50 not_delivered** (brief said 51; one — NSC-078's contract — moved since the brief was written, see below, and is counted in this run's `not_delivered` set as partially_built).

Of the 50 not_delivered:

| Bucket | Count | Meaning |
|---|---|---|
| **Evidence debt** | 25 | every claimed file exists at HEAD, no approved delivery record — recoverable with an evidence pass, no new code |
| **Partially built** | 10 | some claimed files exist, some don't — named below |
| **Not built** | 12 | none of the claimed files exist |
| **No file claims** | 3 | contract has only `logical:` resource claims — this method can't check them; need a different kind of look |

---

## Ready queue (evidence-debt tasks whose dependencies are already conformant — recoverable right now)

Ranked by how many other blocked tasks each one unblocks:

| Task | Unblocks | Blocked tasks it frees | Record status | Validation policy |
|---|---|---|---|---|
| **NSC-089** | 9 | NSC-013, 014, 015, 030, 053, 071, 088, 090, 092 | `materialization_failed` (stale — see note) | **resolved by GER, 497f0d662** |
| **NSC-091** | 8 | NSC-015, 016, 017, 053, 054, 077, 088, 092 | no record at all | **resolved by GER, 8b0f82933** |
| **NSC-045** | 3 | NSC-049, 071, 080 | no record | present |
| **NSC-061** | 3 | NSC-062, 073, 095 | `integrated` | missing |
| **NSC-044** | 2 | NSC-049, 079 | no record | present |
| **NSC-048** | 2 | NSC-049, 083 | no record | present |
| **NSC-032** | 1 | NSC-033 | `awaiting_human` — see caveat | missing |
| **NSC-040** | 0 | — | `prepared` — see caveat | missing |

**NSC-089 is the single highest-value item in this audit.** It unblocks 9 other tasks, all 15 of its claimed files exist at HEAD, and its dependency is conformant. Its record says `materialization_failed`, but that record is from a **superseded worker run** (`2026-09-14T10:15`, source_head `4f787f94a`, the run genuinely failed to materialize). The human-complete display overlay I'm carrying separately says the work was later integrated directly on local main at `4047a4335` with EditMode 2/2 and a 57/57 builder regression pass — and every file the contract claims does exist at the current HEAD. **This isn't a case of "check the record" — the record itself is wrong/stale and should probably be retired or superseded, not trusted.**

**Correction (GER Agent, caught by the Game Agent):** an earlier version of this report recommended writing NSC-089's delivery record "against `4047a4335`." That's wrong — `record_delivery` requires `HEAD == validated_commit`, and the manifest binds whatever commit Unity actually executed at, so the record must bind **current main**, not the historical integration commit. `4047a4335` belongs in the record's notes as provenance only. Precedent: NSC-069 bound `01620a96d`, not its original implementation commit.

**Update, same day:** GER Agent independently confirmed NSC-089 and NSC-091 both lacked a validation-policy entry, wrote both, and committed them to local main (`497f0d662`, `8b0f82933`), no contract revision needed. That clears the paperwork blocker on the top two ready-queue items within the hour of this report landing — the Game Agent can run both gates now.

**NSC-091** has zero `depends_on` entries in its own contract — worth Game Agent confirming that's intentional (a foundational enemy-AI task with no listed dependency looks like it could be an omission, not a design fact), but it doesn't block the recovery.

**Caveat on NSC-032:** its record status `awaiting_human` matches what the viewer already shows (pink "Task Needs You") — it's a real candidate waiting on Vincent's own Unity test, not a paperwork gap. Listing it here for completeness since it technically fits the bucket definition, but it isn't "recoverable with an evidence pass" the way the others are — it's recoverable by Vincent playing it.

**Caveat on NSC-040:** all 2 dependencies conformant, all claimed files present, record status `prepared` (drafted but not committed) — by this method it reads as recoverable. But the live viewer currently shows NSC-040 as **blocked**, not ready, which this audit's dependency check alone doesn't explain (exclusive-resource claims and reservation state aren't something I checked for conflicts with other in-flight tasks). Worth the Game Agent's own look before assuming it's a pure paperwork case.

---

## Evidence debt — full list (25), ranked by unblock count

| Task | Unblocks | Deps conformant | Record | Val. policy | Title |
|---|---|---|---|---|---|
| NSC-089 | 9 | 1/1 | materialization_failed (stale) | **resolved, 497f0d662** | DoorPrototype NavMesh Surface and Enemy Agent Config |
| NSC-091 | 8 | 0/0 | none | **resolved, 8b0f82933** | Enemy Target Detection, Last-Known Position, Search State |
| NSC-092 | 8 | 0/3 | none | **resolved, 21a4cf5e5** | Enemy NavMesh Pursuit, Search Movement, Door Traversal, Reset |
| NSC-050 | 6 | 1/2 | awaiting_human | missing | DoorInteractable Auto-Lock, Durability, Breaking, Floor Reset |
| NSC-017 | 4 | 0/6 | none | **resolved, c95b72daa** | Enemy Locked-Door Attack, Breach, and Pursuit Resume |
| NSC-062 | 4 | 1/2 | prepared | present | Animated Wizard Unity Integration |
| NSC-090 | 4 | 0/1 | none | **resolved, 293253965** | Door State to Enemy NavMesh Passability Component |
| NSC-045 | 3 | 1/1 | none | present | Bone Archive Widened-Lane Blockout and Tilemap Walls |
| NSC-061 | 3 | 0/0 | integrated | missing | PixelLab Wizard Art Direction and Selection |
| NSC-073 | 3 | 0/2 | none | present | White Female Wizard Hat Frame Correction |
| NSC-044 | 2 | 1/1 | none | present | Ruined Entry Spatial Blockout |
| NSC-048 | 2 | 1/1 | none | present | Final Room Layout, Floor and Wall Tilemaps, Catalog Update |
| NSC-049 | 2 | 3/13 | none | present | Five-Room Continuity and Door Sequence Integration |
| NSC-051 | 2 | 0/2 | none | missing | DoorInteractable State Connection to Enemy Door Passability |
| NSC-053 | 2 | 0/4 | none | **resolved, 009d5d5c3** | Ranged Enemy Keep-Distance Movement and Frost Speed Response |
| NSC-068 | 2 | 0/2 | none | **present, f06ed3815 (predates this audit)** | Selected Wizard World Placement and Gameplay Entry |
| NSC-070 | 2 | 0/2 | none | present | Four-Wizard Directional Animation State Repair |
| NSC-074 | 2 | 0/1 | none | present | PixelLab Cardinal Wizard Walk Source Art |
| NSC-075 | 2 | 0/5 | none | present | Unity Eight-Direction Wizard Locomotion Integration |
| NSC-032 | 1 | 4/4 | awaiting_human (real, see caveat above) | missing | Floor Run/Restart Bootstrap |
| NSC-052 | 1 | 0/1 | none | **resolved, ca9060cda** | Door Breach Feedback: Banging, Shaking, Cracks, Durability |
| NSC-067 | 1 | 0/2 | none | missing | Four-Wizard Selection Screen |
| NSC-040 | 0 | 2/2 | prepared (see caveat above) | missing | Visual/Simulation Separation and Continuous-Scene Integration |
| NSC-060 | 0 | 2/3 | none | missing | Player Resource Feedback Modernization |
| NSC-096 | 0 | 0/2 | none | present | Wizard 128 px Source Integration Switch |

**Correction: this originally said "23 of 25 evidence-debt tasks have no validation-policy entry." That was a counting error on my part — the raw data says 15 of 25.** Of those 15, GER Agent has already cleared NSC-089 and NSC-091 (see above), leaving 13. Per the brief, a missing entry parks the candidate even after a delivery record exists.

**GER Agent's follow-up correction, which is the more useful fix:** not all 15/13 are the same kind of work. Some tasks' completion gates name a real, existing Unity test-fixture class — those are a cheap policy-entry write, minutes each. Others describe behavior to verify without naming any fixture at all (including two that are explicitly non-Unity human/assistant checks) — those need a **contract revision to give them an auditable gate** before any policy entry can bind to anything. I read every one of the 13 remaining contracts' `completion_gates` text directly (not a filename search) to split them:

| Names a real fixture — cheap policy entry | No fixture named — needs a contract revision first |
|---|---|
| **NSC-017** — `EnemyLockedDoorAttackPlayModeTests.cs` | **NSC-032** — "Play Mode check: ..." (Floor Run/Restart) — no class named in either gate |
| **NSC-052** — `DoorBreachFeedbackPlayModeTests` | **NSC-040** — "Integrated Unity validation checks..." — describes a check, names no class |
| **NSC-053** — `RangedEnemyKeepDistanceMovementPlayModeTests.cs` | **NSC-050** — "In a Play Mode test, verify..." — no class named |
| **NSC-090** — `DoorEnemyPassabilityPlayModeTests.cs` | **NSC-051** — "Using a test-owned door..." — no class named |
| **NSC-092** — `EnemyPursuitPlayModeTests.cs` | **NSC-060** — 3 automated gates with no class named, plus one explicit `Developer verifies ... in Play Mode` gate |
| *(NSC-089, NSC-091 — already resolved by GER today)* | **NSC-061** — `A deterministic inventory confirms...` / `The assistant verifies...` — explicitly not a Unity fixture, GER's own example |
| *(NSC-068 — already had a policy entry, `f06ed3815`, predating this audit; my original data was stale)* | **NSC-067** — Automated Editor/Play Mode coverage described, no class named |

5 cheap, 8 need contract work first. That's the actual work queue this bucket converts into.

**Update, same night:** GER Agent committed all 5 "cheap" policy entries to local main (nothing pushed): NSC-017 `c95b72daa`, NSC-052 `ca9060cda`, NSC-053 `009d5d5c3`, NSC-090 `293253965`, NSC-092 `21a4cf5e5`. That's 7 of the 15 cleared in one session (with NSC-089/091 above). Remaining 7 in the "needs a contract revision" column: NSC-032, 040, 050, 051, 060, 061, 067. **NSC-068 is removed from that column** — GER had already committed its policy entry at `f06ed3815` (PlayMode `WizardGameEntryPlayMode...`) before this audit ran; verified directly against that commit. My data predated it.

One methodology note from GER worth keeping for future audits: a name ending in "Tests" inside gate prose can be a *method* (e.g. `BuildInMemoryForTests` in NSC-052), not a class — worth a closer look before assuming a gate names a fixture, not just a grep match on the word.

---

## Partially built (10) — named missing files

Sorted by unblock count. Full missing-file lists are in the raw data (`C:\Users\VINCEN~1\AppData\Local\Temp\claude\C--NSC\99beff7b-cdbc-4cbd-bbf7-06662e97534b\scratchpad\audit_raw.json`, kept until this report is reviewed); representative/short ones shown in full below.

| Task | Present/claimed | Unblocks | Missing (short lists in full; long ones summarized) |
|---|---|---|---|
| NSC-009 | 6/14 | 5 | `ForceWave.cs`(+.meta), `ForceWaveCooldownUI.cs`(+.meta), `ForceWavePlayModeTests.cs`(+.meta), `ForceWaveSceneBuilderTests.cs`(+.meta) — the whole Force Wave spell is unbuilt |
| NSC-078 | **1/167** | 5 | Effectively nothing is on disk — the PropCatalog, all source PNGs, docs, review sheets, and the import postprocessor are all missing. This is a "partially built" only in the technical sense that 1 shared path exists; treat it as **not built** |
| NSC-007 | 7/15 | 4 | `Fireball.cs`(+.meta), `FireballProjectile.cs`(+.meta), `FireballPlayModeTests.cs`(+.meta), `FireballCommittedSceneConformanceTests.cs`(+.meta) — the Fireball spell scripts themselves are unbuilt, though shared scaffolding (scene builder, input actions) exists |
| NSC-008 | 6/12 | 4 | `FrostField.cs`(+.meta), `FrostFieldPlayModeTests.cs`(+.meta), `FrostFieldSceneBuilderTests.cs`(+.meta) — same pattern as NSC-007/009, spell script itself missing |
| NSC-077 | 17/21 | 4 | `FireCasterEnemySprite.asset`(+.meta), `EnemyFireballCaster.cs`(+.meta) — close to done, one enemy's fireball-caster art/script wiring is what's left |
| NSC-046 | 6/10 | 3 | `ChapelOfAshFarWallTile.asset`(+.meta), `ChapelOfAshCutawayWallTile.asset`(+.meta) — two generated tile assets |
| NSC-047 | 6/10 | 2 | `LowerVaultNearWallStubTile.asset`(+.meta), `LowerVaultBlockoutProxySprite.asset`(+.meta) — two generated tile assets |
| NSC-055 | 1/15 | 2 | Lantern Wraith gameplay prefab, builder, projectile prefab, flare sprite, defeat-response script, and their tests — essentially all unbuilt |
| NSC-086 | 3/9 | 1 | `FinalDoorVictoryTrigger.cs`(+.meta) and its two test files |
| NSC-095 | 3/5 | 1 | `WizardPixelLab128SourceAuditTests.cs`(+.meta) only — very close, one test file short |

---

## Not built (12) — nothing to recover, needs real work

| Task | Unblocks | Claimed files | Title |
|---|---|---|---|
| NSC-064 | 1 | 2 | PixelLab Dungeon Architecture Art Direction and Selection |
| NSC-071 | 1 | 1 | Bone Archive Navigation Lane Validation |
| NSC-072 | 1 | 1 | Chapel of Ash Projectile Cover Validation |
| NSC-079 | 1 | 4 | Ruined Entry Visual Dressing |
| NSC-080 | 1 | 4 | Bone Archive Visual Dressing |
| NSC-081 | 1 | 4 | Chapel of Ash Visual Dressing |
| NSC-082 | 1 | 4 | Lower Vault Visual Dressing |
| NSC-083 | 1 | 4 | Final Room Visual Dressing |
| NSC-087 | 1 | 4 | Victory Gameplay Suspension Coordinator |
| NSC-059 | 0 | 1 | Completed Gameplay Reuse Audit |
| NSC-084 | 0 | 4 | First-Wing Content Integration Package and Preservation Pass |
| NSC-085 | 0 | 1 | Expanded Dungeon Wing Route Plan and Room/Corridor Task Split (currently GER-active — expected to be unbuilt, it's still a proposal) |

---

## Doesn't fit a bucket — own lines

- **NSC-013, NSC-058** — contracts claim only `logical:` resources (`enemy-locomotion-behavior-surface`, `shared-hierarchy-fader`), no `repo-file`/`unity-scene` entries at all. This audit's file-existence method can't say anything about these two; someone will need to check their actual implementation state a different way (e.g. against the logical surface's real owner file). NSC-013 depends on NSC-092 and NSC-089 (both evidence debt above), so it can't be assessed as ready either way until those land.
- **NSC-043 (Desktop WebGL Build Artifact)** — has **no file claims at all** (`exclusive_resources: []`) and its record status is `approved`, not `awaiting_human` or absent. This is the viewer's known V1 display bug: a genuinely approved candidate that hasn't been integrated yet, showing as dark-green "Awaiting Instruction" instead of its real state. Not evidence debt — it's mid-pipeline, waiting on integration, already flagged to the Pipeline Maintainer separately.

---

## What I did not check

Per the brief's boundaries: no records written, no contracts edited, nothing merged, no Unity run. I did not verify that existing files' *contents* actually satisfy each task's acceptance criteria — only that the specific paths the contract names exist at HEAD. A file being present is necessary but not sufficient for the task to actually be correct; that judgment belongs to whoever writes the evidence pass.

## Handoff

- **GER Agent:** the validation-policy gaps (23 of 25 evidence-debt tasks missing an entry) is a bucket you can work independent of the Game Agent's evidence passes.
- **Game Agent:** the ready queue above, especially NSC-089 (highest unblock value, stale failed record to retire) and NSC-091/045/061/044/048.
- **Pipeline Maintainer / already flagged:** NSC-043's V1 display bug.
