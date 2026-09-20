# GER overnight report (2026-09-14)

This is Claude's running report as GER owner while Vincent sleeps, from about 11:05 UTC for about 5 hours. It is updated as work progresses.

## Morning summary (updated 16:30 UTC)

**GER is stopped (Vincent, about 16:30 UTC).** Codex is out of usage until Sep 19. Everything GER produced is salvaged in `C:/nscrev/ger-salvage-20260914/`. Its `INDEX.md` lists each task's outcome, commit, follow-ups and resume steps, and the folder also holds a verified git bundle of local main.

**Committed on local main (not pushed):**
- **NSC-044 Ruined Entry**, revision 4 (`1795df8f`). Released. Codex received it, and its implementation candidate is in focused Unity tests.
- **NSC-017 Enemy Locked-Door Attack, Breach, and Pursuit Resume**, revision 4 (`52ffed00`). Released and handed off to Codex.
- **NSC-015 Melee Enemy Pursuit, Close-Range Attack, and Gameplay Prefab**, revision 6 (`6fb702b5`). Decomposition queued, so it is still held. Its second split waits on questions 40–42. Codex asked for a review-only D1B.2 run on local main. It is prepared and its zero-cost preflight passed, but my permission guard refused the paid launch, so it **needs your go (question 66)**.
- **NSC-052 Door Breach Feedback**, revision 2 (`8d485ebd`). Released and handed off to Codex. Its code was already integrated; your visible and audible check is still open.
- **NSC-053 Ranged Enemy Keep-Distance Movement and Frost Speed Response**, revision 3 (`b25aa5d3`). Released and handed off to Codex. Its graph follow-ups (dependency edges to NSC-017 and NSC-033) need you or Primary Sol.
- **NSC-054 Ranged Enemy Projectile Attack, Cover Collision, and Reset**, revision 3 (`7bd75a9b`). Released and handed off. Codex has since implemented it and recorded delivery evidence.
- **NSC-020 DoorInteractable Forward-Crossing Geometry, State, and Reset**, revision 3 (`d69ad5f7`). Released and handed off. It fixes a cited early-crossing defect, so NSC-020 now needs a fresh delivery record.
- **NSC-003 player movement**, revision 4 (`96a6293c`). Released and handed off. Only INT-001 changed, so its delivery stays usable; VAL-001 and VAL-002 need a fresh revalidation.

**Released without a contract change:**
- **NSC-012 Enemy Health/Defeat:** the quality-pass re-audit found revision 2 correct, so its delivery stays `conformant`. Questions 52–54 don't block anything.
- **NSC-041 Door Interaction Feedback:** Codex answered its one ownership question (73) with option 1. Revision 1 stays, and NSC-049's GER takes the committed-scene door feedback proof.
- **NSC-005 player mana:** released without a contract change. At HEAD `96a6293c` it is already `conformant` (record `REV-NSC-005-ca9fc2d7262e`), so question 80 looks moot. Only an optional recheck remains.

**Waiting on your design decisions:** 11 tasks, all still held, with 88 numbered questions below.
- **Non-blocking:** questions 36–39, 43–54, 67–72 and 74–88.
- **Question 73** was answered by Codex (option 1). You can still override it.
- **Question 30** (decomposition authority) applies to any contract too large for one worker.
- **Question 66** is an authorization rather than a design question: the paid, review-only decomposition run for NSC-015.

Several questions overlap, so a few answers unblock a lot:
- **Door feedback ownership (73):** Codex answered with option 1, and NSC-041 is released. Override it only if you disagree.
- **Spectral Decoy (55–65):** whether to build it (55) is settled, because the contract records it as your request. Five decisions block a first version: cast and route, which enemies switch to the phantom and when they revert, lifetime, cost, and doors. The details are in the NSC-088 section.
- **Spell controls (10 and 32):** one answer covers NSC-007, NSC-008 and NSC-009.
- **Room walls (1–3):** the shared-boundary wall visual, the door frame on a cutaway wall, and tall obstacle visuals. These affect every room and NSC-049.
- **Room landing order (4):** Codex already chose batched landing for rooms whose shared boundary moves. Confirm or override.
- **Melee Enemy bodies (40–42):** body blocking, movement during wind-up, and the defeated enemy's look. Answering these unblocks NSC-015's second split.
- **The rest:** Fireball (11), Frost Field (12), Force Wave (31, 33–35), encounters (13–19), prop art (6–9), and the expansion wing (20–29). The wing questions mostly come down to whether the GDD should allow a multi-room wing at all.

**GER is stopped: the Codex usage limit is used up.** At 14:51 UTC, the Codex refine rounds for NSC-004 and NSC-066 failed immediately. The provider reported the limit and said to try again on Sep 19, 2026 at 4:00 PM, unless more credits are added; that's your call. I'm not launching any new Codex rounds.
- **NSC-004 and NSC-066 (title screen):** still held and paused. Their first two rounds are complete and kept. Each needs only its Codex refine and Claude re-audit.
- **NSC-015:** the review-only decomposition run also needs a Codex call, so this limit blocks it even with your go (question 66).
- **NSC-003 (player movement):** revision 4 committed at `96a6293c`, released and handed off. It changes INT-001 only, so VAL-001 and VAL-002 need a fresh revalidation.

**#127 watch:** the checks at 14:57, 15:18, 15:38 and 15:58 UTC found no new comments. The 20-minute watch ended at about 16:00 UTC with a closeout post. 22 tasks are still held: 11 need your design decisions, NSC-015 is decomposition queued, NSC-004 and NSC-066 wait on Codex usage, and NSC-049, 071, 072 and 079–083 wait on the room decisions.

**Tooling fixes tonight:**
- the verdict parser;
- the snapshot scope (reviewers couldn't see root-level `Assets/`);
- the #127 watcher;
- resource-group edits, which no longer reformat other tasks' entries.

None of them changed a committed contract's content.

## Operating limits

- **Never:** push; decide game design for Vincent; apply a D1B.2 plan that needs his exact-plan authorization; claim a test or approval that did not happen.
- **Held tasks:** a task that needs a design decision is paused (gray, still held), and its exact questions are listed below.
- **Concurrency:** about 5 tasks at a time. Contract commits happen one at a time, each after a fresh check that local main is clean.
- **Quota:** if a provider quota error appears, no new runs are launched.

## Commits on local main (not pushed)

| Commit | Parent | What |
|---|---|---|
| `07579c44` | `56e86c80` | Runbook and README switched to the full-cycle GER rule |
| `4f787f94` | `9cb03bc1` | GDD room size authority (maximum 3x each side; clearances stay minimums), plus the GDDRAG index rebuild |
| `82c96a9d` | `a24d4c8e` | Vincent's room decisions: NSC-069 revision 5 (room tasks own their catalog rows), NSC-049 revision 4 (catalog bounds and player start), resource group, art direction |
| `22322654` | `3eb21657` | `Pipeline/TaskDesignGER/GER_AUTOMATION.md`: how the GER owner runs GER |
| `cf015386` | `38904af15` | `GER_AUTOMATION.md` section 9: context presets, owner patch and re-check, parser lesson, #127 handoffs, cross-room coordinates |
| `1795df8f` | `68eb0d0ca` | **NSC-044 contract revision 4** (Ruined Entry 28 x 26, player start, wall Tilemaps, stronger route tests), plus two created `RESOURCE_GROUPS.yaml` groups for the room catalog files. `taskcontrol validate` PASS. Hold released and handed off on #127 |
| `52ffed00` | `b5c45c2d` | **NSC-017 contract revision 4**, now titled "Enemy Locked-Door Attack, Breach, and Pursuit Resume". It adds the `EnemyLockedDoorAttack` component and a door approach point, and updates the `EnemyPursuitMovement.cs` group in place to NSC-092 and NSC-017. Reached through an owner patch and a fresh re-check. `taskcontrol validate` PASS. Hold released and handed off on #127 |
| `6fb702b5` | `52ffed00` | **NSC-015 contract revision 6**, now titled "Melee Enemy Pursuit, Close-Range Attack, and Gameplay Prefab" (`needs_execution_decomposition`). Reached through an owner patch and a fresh re-check. `taskcontrol validate` PASS. **Decomposition queued:** still held, with two proposed splits; split 2 waits for your decisions |
| `b25aa5d3` | `8d485ebd` | **NSC-053 contract revision 3**, Ranged Enemy Keep-Distance Movement and Frost Speed Response. The disable handoff no longer touches NSC-092's pursuit component, and the test checks are observable at frame end. Reached through an owner patch after a `blocked_not_design` re-audit with exact replacement text, then a fresh `commit_contract` re-check. `taskcontrol validate` PASS. Hold released and handed off on #127 |
| `8d485ebd` | `6fb702b5` | **NSC-052 contract revision 2**, Door Breach Feedback. Tightens the contract around the already-integrated feedback code and adds NSC-052 in place to the `DoorPrototypeSceneBuilderTests.cs` group. Reached through an owner patch and a fresh re-check. `taskcontrol validate` PASS. Hold released and handed off on #127 |
| `7bd75a9b` | `5b3d0b3a` | **NSC-054 contract revision 3**, Ranged Enemy Projectile Attack, Cover Collision, and Reset. It adds swept per-`Tick` contact, a non-null launch owner, a serialized target-knowledge reference with a `GetComponent` fallback, and a restored GDD cover-evidence entry. Reached through an owner patch and a fresh re-check. The re-audit's six single-owner resource groups were not added: validation requires groups only for resources claimed by two or more tasks. `taskcontrol validate` PASS. Hold released and handed off on #127. Codex reports it has since implemented the task and recorded delivery evidence |
| `d69ad5f7` | `4ef9aac8` | **NSC-020 contract revision 3**, now titled "DoorInteractable Forward-Crossing Geometry, State, and Reset". It fixes the cited early-crossing defect: `CrossedForward` fires only once the wizard's capsule is clear of the doorway blocker. It adds builder materialization and a committed-scene D1–D5 geometry check. Reached through an owner patch and a fresh re-check. `taskcontrol validate` PASS. Hold released and handed off on #127 |
| `96a6293c` | `d69ad5f7` | **NSC-003 contract revision 4** (player movement). Only INT-001 changed. It records the door pointer path, the pointer validity rule, Charged Fireball's single movement-restriction request, and the reset calls. Acceptance criteria, gates and resources are unchanged. Reached through an owner patch and a fresh re-check. `taskcontrol validate` PASS. Hold released and handed off on #127 |

## Task status (room wave, GER v3 on base commit `82c96a9d`, all finished 11:30–11:35 UTC)

| Task | Re-audit result | GER proposal | Marker | Next |
|---|---|---|---|---|
| NSC-044 Ruined Entry | `blocked_not_design` with exact replacement text. Owner patch (16 replacements), then a fresh re-check: `commit_contract` | 28 x 26, X [-14,+14], Z [-26,0]; D1 unchanged; player start (-4,0,-22) | released (purple) | **Committed `1795df8f`; hold released; handed off on #127 about 12:02 UTC.** Minor follow-ups C-01 to C-06 go to the next revision |
| NSC-045 Bone Archive | `needs_design` | 24 x 20, X [-12,+12], Z [0,20]; D1 and D2 unchanged | paused | Decisions 1 and 3; then apply R-01 to R-10 and re-check |
| NSC-046 Chapel of Ash | `needs_design`. The driver log said `commit_contract`; that was a parser bug, see below | 36 x 34, X [-18,+18], Z [20,54]; D3 moves to (-8,54) | paused | Decisions 1, 2 and 4; then apply R-02 to R-12 and re-check |
| NSC-047 Lower Vault | `blocked_not_design`: 4 mechanical blockers, exact text | 40 x 22, X [-20,+20], Z [42,64]; D3 and D4 unchanged | paused | Rebase onto NSC-046's D3 once decisions 1, 2 and 4 settle NSC-046 (cascade note below) |
| NSC-048 Final Room | `blocked_not_design`: 1 blocker, exact text | 30 x 28, X [-15,+15], Z [64,92]; D5 moves to (0,92) | paused | Rebase after NSC-046 and NSC-047 |

Run IDs: `20260914-055357-NSC-044`, `-055406-NSC-045`, `-055414-NSC-046`, `-055422-NSC-047`, `-055432-NSC-048`, under `Downloads\NoSafeCircleOutput\RoomContentGER`.

**NSC-044 path to commit.** The round-04 re-audit gave exact replacement text for every finding, and none needed a design decision. So:
1. The GER owner applied only that quoted text, in `05-owner-patch`: 16 replacements, and only the nine expected fields changed.
2. A fresh Claude `06-claude-recheck` must approve the patched contract.
3. After approval, `apply_contract.py` commits it.

## Task status (non-room tasks)

| Task | Result | Run ID | Marker |
|---|---|---|---|
| NSC-030 Encounter Placement and Composition Authoring | `needs_design`: decisions 13–19 below. The next revision also gets non-design fixes R-03 to R-10, then D1B.2 decomposition | `20260914-065035-NSC-030` | paused |
| NSC-052 Door Breach Feedback | **Committed `8d485ebd`, released, handed off.** Re-audit and fresh re-check both returned `commit_contract`. Questions 46–48 are non-blocking. Known follow-up: its INT-001 cites NSC-017 revision 3 gate IDs | `20260914-073309-NSC-052` | released (purple) |
| NSC-085 Expanded Dungeon Route Graph and Side Chambers | `needs_design`, decisions 20–29 below (GDD scope for a multi-room wing). Non-design fixes for the next revision: restore revision 2's approved topology, and require real JSON parse evidence. The first attempt, `20260914-065043`, hit a transient capacity error | `20260914-070454-NSC-085` | paused |
| NSC-053 Ranged Enemy Keep-Distance Movement and Frost Speed Response | **Committed `b25aa5d3`, released, handed off.** The re-audit was `blocked_not_design` with exact replacement text; owner patch, then a fresh re-check returned `commit_contract`. Questions 49–51 are non-blocking. Graph follow-up: NSC-017 and NSC-033 dependency edges | `20260914-073917-NSC-053` | released (purple) |
| NSC-078 Reusable Dark-Cute Dungeon Prop Art Pack | `needs_design`, decisions 6–9 below; non-design fixes R-01 to R-10 for the next revision | `20260914-065051-NSC-078` | paused |
| NSC-007 Charged Fireball | `needs_design`, decisions 10–11 below; non-design fixes R-01 to R-08 for the next revision | `20260914-065058-NSC-007` | paused |
| NSC-008 Frost Field | `needs_design`, decisions 10 and 12 below; non-design contract work on NSC-013 first | `20260914-065104-NSC-008` | paused |
| NSC-009 Force Wave | `needs_design`: decisions 31–35 below, where 31 and 32 block. The non-design fix is the spell handoff on the title screen and at game entry. The first attempt (`20260914-072248`) was stopped because its snapshot was too narrow | `20260914-072739-NSC-009` | paused |
| NSC-054 Ranged Enemy Projectile Attack, Cover Collision, and Reset | **Committed `7bd75a9b`, released, handed off.** Owner patch (12 replacements), then a fresh re-check returned `commit_contract`. The re-audit's six single-owner resource groups (E-6) were not added, because validation needs groups only for shared resources. Questions 67–72 are non-blocking | `20260914-075919-NSC-054` | released (purple) |
| NSC-015 Melee Enemy (now Melee Enemy Pursuit, Close-Range Attack, and Gameplay Prefab) | **Committed `6fb702b5`, decomposition queued.** Re-audit and fresh re-check: `commit_contract_then_decompose`. There are two proposed splits; split 2 waits for decisions 40–42. The review-only D1B.2 run is prepared at `5b3d0b3a` but needs your go (question 66) | `20260914-072839-NSC-015` | paused (held) |
| NSC-017 Enemy Locked-Door Attack, Breach, and Pursuit Resume | **Committed `52ffed00`, released, handed off.** Owner patch (9 replacements), then a fresh re-check returned `commit_contract`. Questions 36–39 are non-blocking | `20260914-073054-NSC-017` | released (purple) |
| NSC-088 Spectral Decoy Spell and Enemy Redirection | `needs_design`: decisions 55–65 below; 55 and 56 block. It is a GDD stretch goal. Non-design fixes R-01 to R-05 are ready for the next revision | `20260914-080507-NSC-088` | paused |
| NSC-012 Enemy Health/Defeat (quality pass) | **Released without a contract change.** The re-audit returned `release_without_change`; revision 2 stays byte-identical and conformant. Questions 52–54 are non-blocking | `20260914-080828-NSC-012` | released (purple) |
| NSC-041 Door Interaction Feedback (quality pass) | **Released without a contract change.** Its one blocking question (73, who owns preserving D1–D5 door feedback) was answered by Codex with option 1: revision 1 stays, and NSC-049's GER takes the committed-scene proof. Questions 74–75 are non-blocking | `20260914-081321-NSC-041` | released (purple) |
| NSC-020 DoorInteractable Forward-Crossing Geometry, State, and Reset (quality pass) | **Committed `d69ad5f7`, released, handed off.** The re-audit cited an early-crossing defect and returned `commit_contract` with two whole-field edits. Owner patch, then a fresh re-check returned `commit_contract`. NSC-020 now needs a fresh delivery record. Questions 76–79 are non-blocking | `20260914-081837-NSC-020` | released (purple) |
| NSC-005 player mana (quality pass) | **Released without a contract change** (`release_without_change`). Revalidation is due, but no new evidence record until the packaging route is chosen (question 80). Questions 80–83 are non-blocking | `20260914-083819-NSC-005` | released (purple) |
| NSC-003 player movement (quality pass) | **Committed `96a6293c`, released, handed off.** The re-audit returned `commit_contract` with one whole-field INT-001 edit. Owner patch, then a fresh re-check returned `commit_contract`. VAL-001 and VAL-002 need a fresh revalidation. Questions 84–88 are non-blocking | `20260914-083223-NSC-003` | released (purple) |
| NSC-004 (quality pass) | **Blocked by the Codex usage limit.** Codex generate and Claude evaluate are complete. The Codex refine round failed at 14:51 UTC on the provider's usage limit. Resume after the limit resets or credits are added | `20260914-084042-NSC-004` | paused |
| NSC-066 Title Screen | **Blocked by the Codex usage limit.** Codex generate and Claude evaluate are complete. The Codex refine round failed at 14:52 UTC on the provider's usage limit. It is the last task in the GER queue | `20260914-085155-NSC-066` | paused |

## Issue #127 room handoffs

At about 11:15 UTC, Vincent asked that issue #127 be the handoff thread with Codex. Claude checks it about every 20 minutes and posts blockers immediately. Codex replied at 11:31 UTC with three points:
- release each hold after its approved commit;
- recheck the clean local main HEAD before each commit;
- the issue covers all GER tasks, not only rooms.

| Time (UTC) | Who | Comment |
|---|---|---|
| 11:10–11:13 | Codex | Watching the issue on a 20-minute cadence. Relayed Vincent's scope correction: the thread covers every GER task |
| 11:15 | Claude | Status hello, plus how rooms become ready |
| 11:30 | Codex | Release each hold after its approved commit; recheck clean main before each commit |
| 11:36 | Codex | Keep live viewer markers truthful for every GER task (start / pause / finish). Already consistent: NSC-045, 046 and 048 had finished their rounds and been paused for design |
| 11:41 | Claude | Room results, five blockers, landing-order question |
| 11:43 | Codex | Landing order (b); NSC-044 stays independent; continue non-room GER |
| 11:52 | Claude | NSC-044 owner patch under re-check; batch A started |
| 12:02 | Claude | **Ready for Codex — NSC-044** |
| 12:05 | Codex | **Received — NSC-044**; routing it as an independent room candidate |
| 12:26 | Codex | Check-in: the NSC-044 candidate reached Unity scene materialization and focused tests are running. Asks for each non-room result to be handed off individually |
| 12:27 | Claude | **Blocked — NSC-008** Frost Field (4 decisions); correction for the input-asset snapshot mistake |
| 12:29 | Claude | **Blocked — NSC-007** Charged Fireball (6 decisions) |
| 12:31 | Claude | **Blocked — NSC-078** prop art pack (4 decisions) |
| 12:33 | Claude | **Blocked — NSC-030** encounter authoring (7 decisions) |
| 12:39 | Codex | Relayed Vincent's clarification: every GER task gets its own Ready or Blocked post; Codex routes still-large tasks through decomposition |
| 12:39 | Claude | **Blocked — NSC-085** expansion wing (10 decisions) |
| 12:41 | Claude | Full-queue check-in, plus the handoff plan for contracts that need decomposition |
| 12:44 | Codex | Decomposition belongs to the GER owner: run D1B.2 and keep the parent and children held until the split applies |
| 12:48 | Claude | Decomposition constraints: D1C needs your exact-plan approval and ends with a push |
| 13:00 | Codex | A contract that still needs D1B.2 is "decomposition queued", not a design blocker. The earlier "don't run yet" applied only to specific research runs |
| 13:00 | Claude | **Blocked — NSC-009** Force Wave |
| 13:13 | Claude | **Ready for Codex — NSC-017** |
| 13:17 | Claude | **Decomposition queued — NSC-015** |
| 13:17 | Codex | NSC-017 checked and accepted (only its contract and one resource group changed; the graph validates) |
| 13:19 | Codex | **Received — NSC-015**. Keep the parent held; run a review-only D1B.2 on local main when capacity permits, and post the reviewed plan and SHA; nothing is applied before exact-plan approval |
| 13:24 | Claude | **Ready for Codex — NSC-052** |
| 13:28 | Claude | **Ready for Codex — NSC-053** |
| 13:29 | Claude | Queue check-in. Committed and released so far: NSC-044, NSC-017, NSC-052 and NSC-053. NSC-015 is decomposition queued, and D1B.2 preparation is under way. Also posted the snapshot deadlock fix and the NSC-053 graph follow-ups |
| 13:29 | Codex | **Received — NSC-052**. Its implementation is already on main; Codex is checking the focused evidence, and your visible and audible gameplay decision stays open |
| 13:31 | Codex | **Received — NSC-053**. Only its contract changed, and the graph validates. An isolated implementation check is queued after the active room visual pass. Continue GER on every queued task |
| 13:36 | Claude | **Ready for Codex — NSC-012**, released without a contract change |
| 13:40 | Claude | **Blocked — NSC-088** Spectral Decoy (10 decisions) |
| 13:40 | Codex | **Received — NSC-012**. Accepts the release with no new run and no graph edit; the prefab and restart follow-ups belong to their owners |
| 13:50 | Claude | **Blocked — NSC-015 review-only D1B.2 launch.** Prepared and preflighted at `5b3d0b3a`. My permission guard refused the paid launch, so it needs your go |
| 13:53 | Claude | **Blocked — NSC-041**, door feedback ownership: one blocking decision, with option 1 recommended |
| 14:00 | Codex | Check-in with three points:<br>• **Received — NSC-041.** Chooses option 1: revision 1 stays unchanged, NSC-049 takes the committed-scene D1–D5 proof, and the hold is released.<br>• **Received — NSC-015 blocker.** Keep the paid call held.<br>• **NSC-088.** Relays that you asked for the phantom spell, so including it is approved. Asks for the blocking questions to be reduced |
| 14:03 | Codex | Correction on NSC-015. Codex states a standing authorization for a bounded review-only proposal and review call. If a local permission guard still refuses, report it and continue |
| 14:20 | Codex | Check-in: main is at `4ef9aac8`. NSC-042 and NSC-054 are complete; NSC-017 and NSC-053 workers continue. Recheck HEAD before the next commit |
| 14:34 | Claude | **Ready for Codex — NSC-054** (`7bd75a9b`) |
| 14:37 | Claude | Three posts:<br>• **Ready for Codex — NSC-041**, released without a contract change (option 1).<br>• A queue check-in covering the session-limit failures and how they resume, plus the NSC-015 guard.<br>• The reduced NSC-088 blocking decisions |
| 14:47 | Claude | **Ready for Codex — NSC-020** (`d69ad5f7`) |
| 14:48 | Claude | **Ready for Codex — NSC-005**, released without a contract change |
| 14:54 | Claude | **Ready for Codex — NSC-003** (`96a6293c`) |
| 14:55 | Claude | **Blocked — Codex usage limit.** NSC-004 and NSC-066 are paused at their Codex refine round, the NSC-015 decomposition call is blocked too, and no new Codex rounds will launch |

## Decisions needed from Vincent

**Room decisions 1–5: decided by Claude (GER owner) at Vincent's direction, 2026-09-14 about 16:50 UTC.** Vincent: "I wanted you to make the decisions."
- **1:** option (a).
- **2:** option (b).
- **3:** option (b). Visuals about 1.25 units, tuned in camera review; colliders stay at 2.5.
- **4:** option (b). `CommittedRoomSourceSceneConformanceTests.cs` moves to NSC-049.
- **5:** confirmed.

These decisions are not yet written into any contract.

1. **Shared-boundary wall visuals.** Affects all rooms and NSC-049.
   - **The conflict:** where two rooms meet (the D1 to D4 lines), one wall is both the southern room's far wall (full height) and the northern room's near wall (0.5-unit cutaway). RoomSceneComposer clones both rooms' walls, so the composed scene gets both.
   - **Options:**
     - (a) Keep the northern room's low stub. It never hides the wizard just north of the door, but the southern room loses its tall far wall on that line.
     - (b) Keep the southern room's full-height wall. It hides the wizard in the northern room's southern strip.
     - (c) A runtime wall fade while the wizard is behind the wall. This is new presentation behaviour and would need its own task.
   - **Recommendation:** (a). Each room keeps authoring its walls per the art direction in its own scene, and NSC-049 drops the southern copy during composition, a narrow change to NSC-069 AC-004's clone rule. The NSC-044, NSC-045 and NSC-047 re-audits lean the same way.
2. **Door frame on a cutaway wall.**
   - **Options:**
     - (a) The cutaway stops at the opening, and the door instance NSC-049 places gives the readable frame. NSC-046's re-audit recommends this.
     - (b) One full-height jamb cell on each side of the opening. NSC-047 and NSC-048 propose this.
   - **Recommendation:** (b). The art direction says door frames stay readable, and no door art is on main yet.
   - **Scope:** one rule for all five rooms.
3. **Tall obstacle visuals (Bone Archive shelves and archive bays).**
   - **The rule:** the GDD blockout says shelf height "should be at least 2.5 units", so they read as lane-forming architecture and can support later visual replacement.
   - **The problem:** at the 30-degree camera, a 2.5-unit visual hides about 3 units of floor to its north and west, which is most of each lane.
   - **Options:**
     - (a) Keep 2.5-unit visuals.
     - (b) Lower the visuals to a stated height, for example about 1.25 units tuned in camera review, with colliders kept at 2.5.
     - (c) A runtime fade.
   - **Recommendation:** (b).
4. **Catalog landing order, and test ownership.**
   - **The problem:** a room catalog edit that moves a shared boundary turns sibling tests red until the neighbouring rooms land and NSC-049 recomposes. The affected tests are LowerVaultSceneTests, CommittedRoomSourceSceneConformanceTests and FiveRoomDoorSequencePlayModeTests.
   - **Options:**
     - (a) Serialized turns, south to north, with main red in between.
     - (b) The rooms that move a boundary land together, with a narrow NSC-049 refresh.
   - **Recommendation:** (b), and assign `CommittedRoomSourceSceneConformanceTests.cs` to NSC-049. This is NSC-046's re-audit recommendation.
   - **Codex chose (b) for integration** at 11:43 UTC on #127: the rooms whose shared boundary moves land together with the narrow NSC-049 refresh, and NSC-044 stays independent. Confirm or override.
5. **Wall Tilemap structure (confirmation, not blocking).** "Each room uses an Isometric Tilemap for its walls" is being implemented as one room-owned Grid with separate straight-run wall Tilemaps per side, because one Tilemap cannot hold walls on both axes. I treat this as meeting your decision; say if you meant otherwise.

**No decision needed (for your awareness):**
- **Accepted proposals:** committing a room contract accepts GER's size and layout proposal under the GDD section 13 authority you gave. The proposals are in the task table.
- **Cutaway technique varies by room:**
  - NSC-044, 046 and 047 use room-owned stub tiles;
  - NSC-045 and 048 scale the shared WallTile to 0.2 height.

  Your camera review decides whether the squashed look is acceptable.

### Non-room decisions (GER runs finished 12:22–12:28 UTC)

6. **NSC-078 D-2: source-art ownership between NSC-064 and NSC-078.**
   - For base walls, corners, end caps, floors, pillars, pews, shelves, rubble and storage: does NSC-064 own them, with NSC-078 adding only variants?
   - Who owns the near-wall cutaway stub family?
   - Should NSC-064 get its own GER? That GER would publish an exact inventory path and schema, own `Art/Environment.meta`, and replace NSC-064's assistant art review with your review gate.
7. **NSC-078 D-1: texel density.** Should props and architecture use the architecture's 64 pixels per cell, match the wizard's 180 PPU, or use documented mixed densities? This can wait for the style-lock pilot review, but must be settled before any art family is acquired.
8. **NSC-078 D-4: PixelLab post-processing.** Are deterministic crop, trim, alpha cleanup, palette reduction and seam repair allowed? Are the raw exports committed next to the processed files?
9. **Lower Vault hazards (NSC-047 and NSC-082).**
   - Does NSC-047 get water or crossing geometry through a GER, or is NSC-082 AC-005 revised to fit the current blockout?
   - Are lava, chasm and horn trim first-wing content, or only vocabulary for the NSC-085 expansion?
10. **Spell bindings (NSC-007, NSC-008, NSC-009).** Which physical inputs cast Fireball (tap and hold), Frost Field and Force Wave? The left mouse button already moves the wizard and selects doors. One answer covers all three spells.
11. **Charged Fireball behaviour (NSC-007).**
    - **D2 Collision:** against walls, shelves, rubble, pews, columns and sealed, locked, open or broken doors, does the Fireball stop, detonate or pass through? Can it hurt an enemy behind a door? This decides whether a door buys time or safety.
    - **D3 Aim and range:** is the cursor a direction or an exact destination? What happens at maximum range with no hit?
    - **D4 Mana:** is mana spent on press, on release or gradually? What if the charge outgrows the available mana?
    - **D5 Interruption:** do damage, a move click or a door click cancel a charge? Is there a way to abort without casting?
    - **D6 Feedback:** is placeholder charge, projectile and blast feedback acceptable for the first playable Fireball?
12. **Frost Field behaviour (NSC-008).**
    - Does a Frost cast during the five-second door-opening timer cancel the door interaction? The GDD's Frost wording suggests it does not.
    - **Recast:** is a new cast rejected, or does it replace the field? Or can several fields exist at once, and do they stack?
    - **Victory:** does an active field run until it expires, or clear immediately?

### Encounter decisions (NSC-030, GER run finished 12:32 UTC)

Items 13, 14 and 17 block the NSC-030 contract. Items 15, 16, 18 and 19 are values for its child tasks.

13. **Pending enemies from rooms the wizard has left.**
    - `EncounterAdmissionController` admits queued batches in request order. A Chapel batch still pending after D3 locks would block the Lower Vault and Final Room admissions. It would then activate behind a locked door and keep its registry slots.
    - Should admission keep delaying in request order, or reduce/cancel a room's pending enemies when the wizard crosses that room's exit door?
    - When does `ProcessPendingAdmissions` retry, for example after an enemy is defeated?
14. **Ranged support under the 15-enemy cap.** Is it enough to list a Melee Enemy before any Ranged Enemy in each request? Or must every Ranged Enemy wait until a Melee Enemy from its own encounter is active?
15. **Rosters.**
    - For each room, including Lower Vault: the enemy count (3–8) and the Melee/Ranged split.
    - For the rear-breach test, earlier survivors plus the Lower Vault request must be able to exceed 15.
    - Do three Melee Enemies still teach circling in Ruined Entry?
16. **Triggers and regions.**
    - How many activation triggers each room has, and where they go.
    - Each room's spawn/reset region.
    - Whether a region may sit in a door staging area.
17. **Chapel spawn-to-cover rule.** Approve or reject: from every Ranged spawn position, a real pew or column collider must block the line to cover pocket CA-W or CA-E.
18. **Door durability.** The values for D1–D4, and whether D5 gets a value or is exempt (crossing D5 ends gameplay).
19. **Final Room pressure.** What it means as authored content, without waves or reinforcements.

### Expansion decisions (NSC-085, GER retry finished 12:38 UTC)

The core blocker is GDD scope. Current canon allows only "one additional room" as a stretch goal and excludes multiple floors, loot and persistent progression. NSC-085 plans a multi-room wing.

20. **Structure.** Should NSC-085 stay a two-file planning task (`Docs/World/ExpandedDungeonRouteGraph.md` and its `.svg` map), with room and corridor implementation in a separate aggregate decomposed later?
21. **GDD section.**
    - Will you add an Expanded Dungeon Wing section that goes beyond the one-additional-room stretch goal?
    - Where does the wing sit relative to D5 and **You Escaped**: before D5, replacing D5 as the final door, or optional?
    - Do the exclusions of multiple floors, loot and persistent progression change?
22. **Connection.**
    - Which first-wing room and wall side does the wing attach to, through an existing or a new door role?
    - Do you accept that opening a first-wing wall, adding a room or door ID, or changing D5 needs its own GDD and first-wing contract revision?
23. **Content.**
    - How many mandatory and optional rooms and corridors, and what is the destination?
    - Which enemies and encounters, if any?
    - Do persistence, restart and the 15-enemy cap cover the wing?
24. **Traversal rules.**
    - Are complete doorless loops allowed inside encounter regions?
    - How do gates, shortcuts and return routes work with forward-only doors?
    - What does a reward room or dead-end chamber give, without loot?
    - Are elevation changes walkable NavMesh stairs or ramps, or visual only?
    - Are lava, chasms, slime and corrupted ground damaging, non-walkable, or background?
25. **Scale.** Which room, corridor, passage and door widths apply to the new wing? GDD section 13 covers only the first wing.
26. **Biome.** Is the natural-cavern branch from your 2026-09-13 direction still required? Is an infernal or corrupted destination part of this wing?
27. **References.**
    - Are R13 (constructed) and R15 (cavern) the "macro layouts", and R16 and R17 the "reference map"?
    - Should R11 and R12 join the originality comparison?
    - Is a cavern reference missing from the references folder?
28. **Dependency.** Should topology-only planning still wait for NSC-084?
29. **Later implementation.** Which parent should the later aggregate sit under (not NSC-022)? Should it use new parallel expansion ID, catalog and composer files, or sequenced revisions of NSC-069's and NSC-049's files?

### Decomposition authority (standing question)

30. **How GER-committed contracts get decomposed.** Some contracts are right but too large for one worker. For those, D1B.2 decomposition and D1C graph application can't finish overnight:
    - **Checkout source:** the canonical D1B.2 checkout clones the GitHub remote. The remote lacks the unpushed local GER commits.
    - **Research tree:** the local research-tree route is under your "Don't run yet" hold for NSC-014, 015 and 033.
    - **Application:** D1C needs your exact-plan APPROVE, and it ends with an exact push to main.

    For each such task, you need to give:
    - either a push of local main or a go for the research tree;
    - then approval of each exact plan.

    Until then, those tasks keep their committed contracts and stay held. Codex confirmed at 12:44 UTC that decomposition belongs to the GER owner.

    At 13:00 UTC Codex added that such a task is **decomposition queued**, not a design blocker:
    - its reviewed contract is committed and stays held;
    - it is posted on #127 with the exact commit SHA and the proposed split;
    - Codex routes the canonical decomposition and apply boundary separately, without requiring a push.

    No child becomes executable until its exact plan is applied.

### Force Wave decisions (NSC-009, GER run finished 12:59 UTC)

Items 31 and 32 block the contract.

31. **Force Wave through solid geometry.** Can the wave push an enemy on the other side of a wall collider, a sealed door, or a locked door? Pushing through a locked door knocks back the enemies breaching it and weakens door pressure.
32. **Three-spell controls (the same question as 10).**
    - A dedicated Force Wave Input Action with an approved keyboard/mouse binding, or a select-spell-then-attack scheme for all three spells?
    - Is a gamepad binding needed now?
    - It can't be left click, which moves the wizard and selects doors.
33. **Balance-test owner.** Which task owns the playtest of surround escape, door blockers, distant ranged pressure, and roughly one use per encounter?
34. **Feedback (doesn't block).**
    - The knockback is an instant NavMeshAgent warp, which may read as a teleport at gameplay-camera scale.
    - Pressing during cooldown gives no feedback.
    - Are the cooldown indicator and the displacement enough for the prototype?
35. **Confirm (the default fits the GDD).** Casting Force Wave during the five-second door timer doesn't reset the door attempt.

**Cross-spell note (GER owner, not a question for you):**
- **The gap.** NSC-007 and NSC-009 both found that the title screen and game entry have no spell suspend/re-enable handoff. As things stand, a Fireball added to the title screen's input-suspension list would stay disabled all game, and a Force Wave press on the title screen would spend mana.
- **The fix.** The next revisions of NSC-007, NSC-008 and NSC-009 handle it the same way, with resource groups shared with NSC-066 and NSC-068.

### Locked-door enemy attack questions (NSC-017, GER run finished 13:04 UTC)

These don't block NSC-017, whose contract is being committed after a fresh re-check.

36. **Searching enemy behind a locked door.** An enemy is searching for a last known position that lies behind a locked door. Should it:
    - (a) attack the door;
    - (b) clear its target under a new rule for unreachable positions;
    - (c) stay stalled, which is the current NSC-092 behaviour?

    The contract follows the GDD literally: only a pursuing enemy attacks a door.
37. **Ranged Enemy at a locked door.**
    - Does a blocked Ranged Enemy walk up and strike the door, damage it another way, or follow some other rule?
    - Does its keep-distance movement pause meanwhile?

    This blocks the Ranged prefab wiring in NSC-055, not NSC-017.
38. **Frost Field slowing a breach.** Should this GDD stretch goal become required scope? It is optional today, and the contract leaves it out.
39. **Force Wave through a locked door.** This is the same question as 31.

**Graph follow-ups from NSC-017 (GER owner or Primary Sol):**
- Assign a receiving validation contract for its gameplay-camera obligation, INT-004.
- Record INT-003, the check that a broken door's NavMesh path is complete in the built scene, in NSC-049.
- When NSC-015 is decomposed, its prefab-assembly child must depend on NSC-017.
- Correct NSC-092's stale note saying it alone owns the enemy locomotion surface.

### Melee Enemy decisions (NSC-015: contract committed, decomposition queued)

Items 40, 41 and 42 block dispatch of NSC-015's second split (movement, defeat response and prefab). The first split, attack and reset, does not wait.

40. **Body blocking.** Should Melee Enemy bodies physically block the wizard, as in "surround" or "block access to a door"? If yes:
    - Which task owns the Collider?
    - How does NSC-089's NavMesh bake keep active enemy colliders out of the walkable surface?
41. **Movement during wind-up.** Should a Melee Enemy keep pursuing during its attack wind-up (the current behaviour), pause, or slow down?
42. **Defeated enemy.** Should it be hidden, left as a corpse sprite, faded, or something else? If body blocking is approved, when does its physical obstruction end?
43. **Attack feedback.** Must NSC-015 deliver a readable wind-up, swing and hit (animation, VFX or audio) now? Or is this a recorded presentation gap? No approved melee attack assets exist. This blocks only NSC-015's human review gate.
44. **Fireball targeting.** How does Charged Fireball find Melee Enemies for area damage? No collider, layer or registry query is approved. Not an NSC-015 blocker.
45. **Cross-task validation.** Should NSC-007, NSC-008, NSC-009 or NSC-071 gain dependencies so they validate against the assembled Melee prefab? Not an NSC-015 blocker.

### Door breach feedback questions (NSC-052, contract being committed after a fresh re-check)

None of these blocks NSC-052.

46. **Broken door look and owner.**
    - After a door breaks, should its sprite look open or broken? The GDD says the door "remains open".
    - Does that belong to NSC-050, NSC-052, or a new reviewed task?
    - Until then, is "all cracks, indicator disappears, final bang" enough for you to recognise the break at gameplay-camera scale? The player-blocking collider stays enabled either way.
47. **Attacked door out of frame.** Suppose you are holding the next door's five-second opening while the attacked rear door is off-screen. Is the localized bang enough, or do you want an off-screen or HUD cue? That cue would be new design.
48. **Always-visible bars.** This matters only if you reject the default of hiding the durability bar while a door is sealed or open.

### Ranged Enemy movement questions (NSC-053, committed and released)

None of these blocks NSC-053.

49. **Pre-fire line of sight.**
    - **The conflict:** the GDD asks for a Ranged Enemy line-of-sight check before it fires. NSC-016, NSC-054 and NSC-072 instead let it fire and rely on the projectile hitting cover.
    - **The question:** which rule governs?
    - **If pre-fire line of sight wins:** NSC-053's hold behaviour needs another review for a lone survivor stuck behind cover. No cover-seeking movement is authorized.
50. **Ranged Enemy at a locked door.** This is the same question as 37: does it damage the door with its projectile, or with another attack?
51. **Facing while backing away.** Should a retreating Ranged Enemy face the wizard or its movement direction? This is presentation work for NSC-055 and NSC-094.

**Graph follow-ups from NSC-053, for you or Primary Sol:**
- **NSC-017** should depend on NSC-053. It disables and re-enables the keep-distance component around a locked-door attack.
- **NSC-033's enemy-reset work** should depend on NSC-053 and NSC-055.
- **Floor restart:** decide which task restores the keep-distance component's enabled state.

### Enemy Health quality pass (NSC-012, released without a contract change)

The re-audit recommended `release_without_change`. `Tasks/NSC-012.yaml` stays at revision 2, byte-for-byte, so its approved delivery stays `conformant`. None of these questions block anything.

52. **Stale bootstrap note.** The contract's notes still say this capability "does not exist in any form". Keep the note as history (recommended), or approve a separate notes-only edit? A notes-only edit keeps the task `conformant` and only adds a recheck note.
53. **Fresh validation.** Re-run VAL-001 to VAL-003, or keep the approved evidence from 2026-08-25? The code is expected to be unchanged, so a re-run is optional.
54. **Enemy damage feedback.** Should enemies get health bars, hit-only feedback, or only a defeat cue at gameplay-camera scale? The GDD requires a continuous health display only for the wizard, so any choice here is new design for the enemy prefab tasks.

**Downstream follow-ups from NSC-012 (no NSC-012 edit):**
- When NSC-015 is decomposed, its prefab work needs a Play Mode gate for exactly-once registration and unregistration on lethal damage, like NSC-055 VAL-001.
- NSC-033's enemy-restart child must call `EnemyHealth.ResetHealth` from a real zero-health restart.

### Spectral Decoy decisions (NSC-088, GER run finished 13:37 UTC)

The re-audit returned `needs_design`. Nothing was committed; the task is still held and its marker is paused.
- **Stretch goal only:** Spectral Decoy appears in the GDD only as a stretch goal (GDD:560), and accepting a stretch feature is your call (GDD:644).
- **Rule conflict:** its "draw enemies down another corridor" idea breaks the current rule that enemies lose the wizard only through distance and search (GDD:526–537).
- **Code today:** `EnemyTargetKnowledge` only knows about the wizard.

**Update 14:37 UTC: now five blocking decisions.**
- **Question 55 is settled.** The committed NSC-088 contract records the feature as your own request (basis `human_requested_stretch_goal_task`), and Codex relayed the same on #127.
- **Still unapproved.** The contract's own execution reason names what's left, and only these five block a first implementable version:
  - **Cast and route** (from 58): which input casts it, and whether the route is a clicked point or a direction.
  - **Enemy switching and reversion** (from 56 and 57; this is the GDD pursuit-rule change): which enemies may follow the phantom and how many, and what they do when it ends.
  - **Lifetime and destruction** (from 62): how long it lasts, and whether enemy attacks can destroy it.
  - **Cost** (from 62): mana cost, cooldown, and how many phantoms can exist at once.
  - **Doors** (from 61): whether the phantom may pass open or broken doors and lead pursuers ahead, and whether an enemy following the phantom may attack a locked door.
- **Proposed to wait:** questions 59, 60, 63 and 64 (room balance, attacks and spells, the guardrail, feedback), until playtest or a later revision.
- **Still yours:** question 65.

The original list follows for reference.

55. **Accept it?** Build Spectral Decoy as a stretch feature, or decline it.
56. **Pursuit rule.**
    - Amend GDD 526–537 so an enemy can be pulled off the wizard, or reshape the idea. One reshaped option is a lure that affects only enemies already searching; that still changes GDD:528.
    - Either way, decide which distance governs gaining and losing a target: the wizard's, the phantom's, or both.
57. **Which enemies.**
    - Melee, Ranged or both.
    - One, some or all per cast, and in what priority.
    - What an enemy still remembers about the wizard.
    - What happens after expiry, destruction, a failed route, or reacquiring the wizard.
58. **Cast and route.**
    - Which input casts it. The Input Actions asset has only `PointerPosition` and `MoveToCursor`, and NSC-003, 007, 008 and 009 hold its lock.
    - How the route is chosen: a clicked point read from `PointerWorldTarget`, or a direction or branch.
    - What happens with an invalid route.
59. **Rooms.**
    - **Bone Archive:** how many pursuers one cast may pull away before the BA-1 pinch stops working as a trap and a Frost Field lane.
    - **Chapel:** must the wizard still use pews and columns against Ranged shots? Does the fast central aisle lose its risk if Ranged Enemies are redirected (GDD:322, 383–385)?
    - **Lower Vault:** may the Decoy create the safe repeatable loop the room forbids, or neutralize pursuers breaking in through D3 (GDD:391, 424)?
    - **Ruined Entry and Final Room:** is casting refused, reduced, or allowed with no side corridor? The Final Room says the last door window must come from movement and the existing spell kit (GDD:436).
60. **Attacks and spells.**
    - Do Ranged Enemies aim at the phantom, and do their projectiles hit it?
    - Can Melee attacks destroy it?
    - After Frost Field or Force Wave hits a redirected enemy, does the enemy return to the phantom, the wizard, or searching?
    - Can the phantom itself be slowed or knocked back?
61. **Doors.**
    - Behavior at sealed, open, locked and broken doors.
    - Whether the phantom may lead pursuers ahead of the wizard through an open door.
    - Backward travel through a broken doorway: the NavMesh allows both directions by default.
    - Whether the phantom persists across rooms.
    - Whether a phantom-following enemy may attack a locked door (GDD:541; NSC-017 AC-001).
62. **Limits and cost.** Lifetime, destruction, concurrent limit, mana cost, cooldown, and whether mana is spent before or after the route is checked.
63. **Balance guardrail.** Adopt or revise: "the Decoy alone does not guarantee the five uninterrupted door seconds (GDD:50, 572) and does not reliably answer both enemy types (GDD:79)".
64. **Feedback.** What feedback is required at gameplay-camera scale? Does showing each enemy's target switch pull in the awareness-indicator stretch goal (GDD:560)?
65. **Design-hold record.** The re-audit says the round-03 contract, with its quoted fixes R-01 to R-05, authorizes no files, gates or APIs, so it is safe to commit as a record of the hold. Commit it now, or wait for an executable revision? I left it uncommitted.

**After your decisions:**
1. Revise GDD 98–104 and the success criteria (609), NSC-033 or its restart child, NSC-087 (a sixth suspend participant), and NSC-086 (the final-door-to-suspension scene path).
2. Write a new executable NSC-088 revision.
3. Run D1B.2. The likely splits are:
   - the Decoy's cast, route, lifetime, mana and feedback;
   - enemy target redirection in `EnemyTargetKnowledge` and `EnemyPursuitMovement`, reviewed with NSC-013, 015, 017, 053, 054 and 055;
   - input, builder, scene, restart and suspension wiring.

**Non-design fixes ready for the next revision (R-01 to R-05, quoted in the re-audit):**
- redirecting a searching enemy also counts as a GDD change;
- the phantom uses only NavMesh door passability, never a second door-state check;
- cursor routes read `PlayerMovement.PointerWorldTarget`;
- quote GDD:79 exactly;
- restart proof goes to NSC-033 or its restart child, and victory suspension goes to NSC-087 and NSC-086.

### Ranged Enemy projectile questions (NSC-054, commit pending a fresh re-check)

None of these blocks committing NSC-054. Questions 70 and 71 must be settled before NSC-055 is dispatched.

67. **Hold fire behind cover?** Today an enemy fires into cover. Should that ever be replaced by a line-of-sight check before release? If so, choose what the wind-up does while the path is blocked:
    - never starts;
    - cancels at release;
    - holds the shot until the wizard is exposed.

    Any of these needs coordinated revisions to NSC-016, NSC-072 and NSC-054.
68. **Enemy bodies.** Should enemy bodies block Ranged Enemy shots, or take friendly fire? Revision 3 lets shots pass through any enemy that has `EnemyTargetKnowledge`.
69. **Firing while searching.** May a searching Ranged Enemy fire at the wizard's last known position? Revision 3 attacks only while pursuing.
70. **Aim timing.** Does the shot aim where the wizard is when the wind-up starts, or where the wizard is when the shot is released? This changes how easily sideways movement dodges a telegraphed shot. Settle it in playtesting before NSC-055's presentation review.
71. **Production asset ownership.** Which approved task owns each of these? NSC-055 names none of them.
    - the production projectile prefab or template;
    - the `projectileOrigin` placement;
    - the `windUpFeedback` object;
    - the exact Ranged Enemy prefab path.
72. **Attack art and audio.** Should art and audio be commissioned for the projectile, wind-up, impact or attack pose? The current Ranged Enemy source art covers only idle poses, and explicitly leaves out attacks and projectiles.

### Door feedback ownership (NSC-041 quality pass, GER run finished 13:50 UTC)

The re-audit returned `needs_design`. Nothing was committed; the task is still held with its marker paused, and delivered revision 1 is unchanged. It cited no runtime defect: what's missing is proof in the committed scene that doors D2 to D5 keep their feedback.

73. **Blocking: who owns preserving D1–D5 door feedback?**
    - **Option 1 (the re-audit recommends it):** NSC-041 stays at revision 1 with no contract change and is revalidated now. That means your Play Mode review of the textured door tints in the composed scene, plus the Edit Mode hover-alignment suite and the Play Mode feedback suite. NSC-049 then takes a committed-scene D1–D5 feedback gate through its own GER.
      - *Before revalidating:* read NSC-041's conformance finding at HEAD. Use a revalidation record only if the delivery basis is an ancestor; otherwise record a new revision-1 delivery.
    - **Option 2:** NSC-041 moves to revision 2 with the committed-scene D1–D5 gate. It then depends on NSC-049 and shows `needs_replan` until NSC-049 is delivered, so NSC-033's restart work also waits.
      - *Text ready:* the re-audit's exact replacement text for this path. VAL-002 compares against the door's selection distance, VAL-001 covers each of D2 to D5, VAL-003 starts each selection outside arm's reach, plus a notes line on NSC-033 and the resource-group update.
74. **Non-blocking, NSC-019's call:** should a click on a door's top band or corners select the door? Today those points fall outside the 1.5-radius selection circle and become plain move commands. Hover still shows the clickable area.
75. **Non-blocking, NSC-065's call:** may locked doors keep the sealed door's look until NSC-065's door-state art is in the game, as long as the human check finds the next sealed door unambiguous?

### Door crossing questions (NSC-020, committed `d69ad5f7`)

None of these blocked the commit.

76. **The state change.** Revision 3 moves NSC-020 to `needs_replan` until a new delivery record proves the merged VAL-001. Editing `DoorInteractable.cs` will also add a recheck suggestion to other conformant records that track that file. Committing contracts is authority you delegated to GER; revert `d69ad5f7` if you disagree.
77. **Extra forward margin.** The contract only requires the wizard's capsule to be clear of the doorway blocker before the door locks. Should the door wait for more distance? This is a playtest feel call.
78. **Consumer tests that use reflection.** NSC-050, NSC-051 and NSC-052 prove crossing by calling the private handler directly. Should they get holds or revalidation? NSC-050 matters most, because the fix moves when its automatic lock and health restore happen.
79. **Space beyond D5.** The corrected D5 trigger sits past the Final Room's authored edge at z = 86, so the wizard walks about 0.65 units or more past it to escape. Is that acceptable, or does the escape side need walkable space? NSC-086's scene gate covers whether D5 can be reached.

### Player mana questions (NSC-005, released without a contract change)

80. **Evidence packaging (likely moot).** At HEAD `96a6293c`, NSC-005 is already `conformant` (record `REV-NSC-005-ca9fc2d7262e`), and so are NSC-003 and NSC-004. Only optional rechecks remain. The original question, kept for reference: This is not a design decision. If `taskcontrol.py state NSC-005 --json` confirms `evidence_stale` from broken ancestry, choose how to record the revalidation.
    - First check whether NSC-005's three validated commits were left out of the 2026-08-29 history-identity migration map.
    - Don't delete or rewrite existing records.
81. **Readability while moving.** Is the 0.25 s colour-only flash on a denied cast noticed while the wizard moves? If not, the follow-up belongs to NSC-060.
82. **Real-spell denial proof.** This is graph routing, not design. Give NSC-007, NSC-008 and NSC-009 each a Play Mode gate: a cast with too little mana calls `PlayerMana.Spend`, gets false and `CastDenied`, and starts no spell-local cast state.
83. **Fireball denial timing.** A real design decision for NSC-007's GER: is Charged Fireball denied when charging starts, or when release tries to cast?

### Player movement questions (NSC-003, committed `96a6293c`)

None of these blocks the commit, because revision 4 decides none of them.

84. **Charging restriction.** Should charging stop movement completely, as delivered, or only slow it ("restricts movement further", GDD:65)? Slowing would replan NSC-003 later.
85. **Destination during a charge.** Should starting a charge cancel the active click destination and held-cursor steering? Or should movement resume toward it afterward, as it does today?
86. **Spell bindings for NSC-007, NSC-008 and NSC-009.** `MoveToCursor` is on the left mouse button, and the unused stock `Attack` action is bound there too.
87. **Held button across restart.** After a Play Mode observation, should holding or releasing the move button across a restart resume movement immediately, or require a fresh press?
88. **More restriction requesters (only if ever wanted).** Individually releasable restriction requests would replan NSC-003 and need a resource group shared with NSC-019.

### NSC-015 review-only decomposition run (needs your go)

66. **Authorize the paid review-only D1B.2 run for NSC-015?** It is fully prepared and the zero-cost checks passed:
    - a clean clone of local main at `5b3d0b3a`, where NSC-015 is revision 6;
    - the offline preflight: context build, run gate and decomposition preflight all ok;
    - the no-spend CLI smoke refused cleanly and wrote nothing;
    - Docker, the decomposition image and the provider volumes are present.

    **What was refused.** When I launched `AssistantControl decompose NSC-015 --providers codex,claude --authorize-provider-spend`, my permission guard refused it. That command makes one Codex proposal call and one Claude review call, with no GitHub writes and no graph apply. I did not work around the refusal.

    **If you say go:** I run it and post the reviewed plan and hashes on #127. Applying the plan still needs your separate exact-plan approval.

    **Known risk:** local main lacks the research pipeline's extra revision review. A reviewer REVISE on call 2 ends as `needs_human`.

## Stopped, failed or unusual

- **GER snapshot scope defect, fixed about 12:30 UTC.**
  - **Cause:** snapshots held only `Assets/NoSafeCircle` and `Assets/Scenes`. So the NSC-008 re-audit wrongly called `Assets/InputSystem_Actions.inputactions` missing; it is on main.
  - **Fix:** new snapshots include all of `Assets/`, and prompts say "outside the snapshot" instead of "missing".
  - **Running cycles:** they keep byte-identical prompts.
  - **NSC-009:** its first round was stopped, preserved with `ABORTED_BY_OWNER.json`, and restarted.
- **#127 watcher gaps, fixed.**
  - **Missed comments:** the count-based watcher missed two Codex comments posted between my own posts (11:13 and 11:36). Both asked for things already being done. The replacement remembers every comment URL, and my posts carry a hidden marker.
  - **Emoji crash:** one later Codex comment contained an emoji that crashed console output before the comment was shown. Output is now UTF-8, and a comment is recorded as seen only after it prints.
- **Recommendation parser bug, fixed.**
  - **The bug:** the node driver and `apply_contract.py` returned the first option, in list order, found anywhere after the "Final recommendation" heading. So NSC-046's "needs_design ... a short re-audit should then be able to recommend commit_contract" parsed as `commit_contract`.
  - **Impact:** I read every re-audit before acting, and no commit was attempted on the wrong reading.
  - **The fix:** both parsers now return the earliest option named after the heading. A regression test over the real re-audits passes.
- **Depth cascade across rooms.**
  - NSC-046's deeper Chapel moves D3 north by 12, while the NSC-047 and NSC-048 proposals assume Lower Vault stays at Z [42,64].
  - Room contracts use absolute coordinates, and the composer cannot translate rooms.
  - Once NSC-046 settles, NSC-047 moves to Z [54,76] with its entry at X -8, and NSC-048 moves to Z [76,104]. Each needs a rebased, independently re-checked revision.
- **Earlier runs.** The v1 and v2 runs were superseded when Vincent changed design authority. They are preserved with `ABORTED_BY_OWNER.json`.
- **Canonical checkout.** Earlier it had uncommitted changes that were not GER's, most likely Unity's DOTween upgrade: six deleted `DOTweenUpgradeManager` files and a modified `ProjectSettings.asset`. I left them untouched. By 13:54 UTC the tracked tree was clean.
- **Hash-preparer fix.** Stopped on Vincent's instruction; the prompt workaround stays.
- **GER tooling upgraded between cycles.** At 11:40 UTC:
  - per-category prompt context (`--context`, `--addendum-file`);
  - the parser fix;
  - a `release_without_change` outcome for the quality pass.

  With the room preset, all 20 recorded v3 prompts rebuild byte-for-byte.
- **Snapshot deadlock, fixed about 13:27 UTC.**
  - **Symptom:** the NSC-020 driver hung while building its snapshot. Python stopped reading the `git archive` stream before its end padding, so git blocked on a full pipe while Python waited for git.
  - **Fix:** the driver now drains the stream before waiting.
  - **Recovery:** I stopped the stuck git process and set the partial snapshot aside. NSC-020 resumed on its existing packet.
- **NSC-015 decomposition launch refused, 13:46 UTC.**
  - My permission guard refused the paid, review-only D1B.2 launch.
  - I did not retry it or work around it. The run is fully prepared and preflighted, and it waits for your go (question 66).
- **Owner-patch tool extended, 13:48 UTC.** For NSC-054's quoted edits, `ger_patch.py` gained two things:
  - object items for `insert_list_after`, needed to add a `gdd_evidence` entry;
  - `insert_after_tight`, for quoted insertions that begin with punctuation.

  The guards are unchanged:
  - every inserted text must be quoted in the re-audit;
  - every anchor must match exactly once;
  - a fresh Claude re-check must approve the patched contract before `apply_contract.py` will commit it.
- **Claude session limit, about 13:59–14:10 UTC.**
  - Four GER rounds failed with a provider 429 "session limit" error: NSC-004 and NSC-066 in their evaluation round, and NSC-003 and NSC-005 in their re-audit round. The GER `claude -p` rounds share your Claude usage.
  - After the 14:30 reset, `ger_node.py` gained `--retry-transient-failure`. It keeps a round that failed on a provider limit as `<round>.failed-<UTC>` and reruns only that round, so finished Codex rounds were not repeated. Any other failure still needs a fresh packet.
  - The four cycles resumed about two at a time, to spread usage.
- **Re-check wrapper bug, 14:37 UTC.** My shell wrapper read the snapshot name from Windows Python output with a trailing carriage return. The first NSC-020 re-check therefore failed its precondition before any provider call. It is kept as a `.failed-` record, and the retry passed.
- **Six single-owner resource groups not added (NSC-054).** The re-audit and re-check said they were required. They are not:
  - validation (`work_graph_validate.py`) requires groups only for resources claimed by two or more tasks;
  - canonical graph-delta reconciliation never creates single-owner groups;
  - 277 existing single-owner claims have none.

  `taskcontrol validate` passed on the commit.
- **Codex usage limit, 14:51–14:52 UTC.**
  - The Codex refine rounds for NSC-004 and NSC-066 failed within seconds. The provider reported that the Codex usage limit is used up, with a retry time of Sep 19, 2026, 4:00 PM, unless more credits are added.
  - Following the quota rule, no new Codex rounds were launched.
  - NSC-004 and NSC-066 keep their completed first two rounds. Before resuming either one, rename its failed refine round to a `.failed-` record.
  - The transient-retry option deliberately does not cover a multi-day quota like this one.
