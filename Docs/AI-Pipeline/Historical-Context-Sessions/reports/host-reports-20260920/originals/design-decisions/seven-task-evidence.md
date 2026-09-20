# Seven-Task Design-Decision Evidence Pack

**Prepared:** 2026-09-15 | **Repository:** `C:\NSC\NSC\NoSafeCircle` @ `main` = `9810029590bf2fd4099b36495dad7109c950302d` ("NSC-093: commit Unity metadata for enemy eight-direction walk art") | **Mode:** read-only research, no repository files modified.

## Method and sources

For each task I read:

- `Tasks/<ID>.yaml` (JSON) at current `main` — the live, uncommitted-forward contract.
- The GER packet's `04-claude-reaudit/OUTPUT.md` (the final round-4 recommendation and the numbered "Decisions that need Vincent"), and skimmed `02-claude-evaluate/OUTPUT.md` via round-4's own "status of round-02 findings" tables, which quote and resolve every round-2 finding — round-4 is the authoritative, most current statement of what blocks each task.
- The full text of `Docs/GDD/No_Safe_Circle_GDD.md` (739 lines, read in full).
- The actual game code under `Assets/NoSafeCircle/` (direct file reads/greps, not just the audits' citations).
- `Assets/InputSystem_Actions.inputactions` (direct read of the full JSON).
- `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml` and `Tasks/*.yaml` (grepped for exclusive-resource collisions).
- Git history/ancestry (`git log`, `git merge-base --is-ancestor`, `git show`) to confirm whether anything has changed since each review's frozen snapshot.

Packet directories used (all confirmed via `NODE_STATUS.json`: `"status": "rounds_complete"`, `"reaudit_recommendation": "needs_design"`):

| Task | Packet directory | Snapshot commit | Ancestor of current `main`? |
|---|---|---|---|
| NSC-007 | `RoomContentGER/20260914-065058-NSC-007` | `38904af152b8...` | Yes |
| NSC-008 | `RoomContentGER/20260914-065104-NSC-008` | `38904af152b8...` | Yes |
| NSC-009 | `RoomContentGER/20260914-072739-NSC-009` (a `20260914-072248-NSC-009` attempt exists but only has round 1 — superseded/incomplete, not used) | `22c93fbc93cf...` | Yes |
| NSC-030 | `RoomContentGER/20260914-065035-NSC-030` (two earlier `NSC-030`/`NSC-030-gameplay` dirs from 01:00/02:01 have only `GER_PACKET.md` — not real review runs) | `38904af152b8...` | Yes |
| NSC-078 | `RoomContentGER/20260914-065051-NSC-078` (a `003001-NSC-078` dir has only `GER_PACKET.md` — not used) | `38904af152b8...` | Yes |
| NSC-085 | `RoomContentGER/20260914-070454-NSC-085` (the `065043-NSC-085` attempt only has round 1 — superseded, not used) | `1795df8fde48...` | Yes |
| NSC-088 | `RoomContentGER/20260914-080507-NSC-088` | `b5c45c2d225a...` | Yes |

`TaskDesignGER/20260913-Spectral-Decoy-Question/USER_PROBLEM.md` is Vincent's original framing for Spectral Decoy ("send a phantom or duplicate down a different corridor, draw pursuing enemies after it... Compare tactics already allowed by the current GDD with new decoy/visibility rules that would need a GDD revision") — it predates NSC-088 and is folded into that task's section below. Its subfolders are all labeled `NSC-006` (an old ID) and were not separately reviewed as one of the seven tasks.

All four snapshot commits are ancestors of current `main`, and no `Tasks/NSC-0{07,08,09,30,78,85,88}.yaml` revision number has advanced past what each reaudit reviewed (each live file's `contract_revision` matches the reaudit's stated baseline, not the higher "if-committed" number the round-3 draft would have become) — **nothing has changed for any of the seven since these reviews ran.**

One correction to the record: NSC-008's reaudit states "the snapshot confirms no `*.inputactions*` file exists." I checked directly — `git show 38904af152b8...:Assets/InputSystem_Actions.inputactions` returns the full 1096-line file, and it is unchanged (still exists, same shape) at current `main`. The reviewer's *bounded minimal-context file snapshot* (a filtered subset, per the GDD's own "Minimal-context dispatch" rule, GDD:622) evidently did not include this file — it was not actually absent from the repository at that commit. The "restore `InputSystem_Actions.inputactions`" item in NSC-008's non-design blocker list is therefore **already satisfied** and should not gate anything further.

---

## NSC-007 — Charged Fireball

Contract: revision 2 live, `single_agent`/`concrete`, depends on NSC-003 (delivered), NSC-012 (delivered).

### a) Open design questions (round-04 §6)

All of D1–D5 are explicitly BLOCKING — the recommendation states "D1–D5 decide behavior a worker would otherwise have to invent." D6 and the pause-dispatch item are listed as open questions but are not folded into that blocking sentence.

1. **D1 · Spell bindings [BLOCKING].** "What are the physical tap/hold bindings for Fireball, and the cast bindings for Frost Field and Force Wave? Left mouse is already movement and door selection." (Shared across NSC-007/008/009 — see Cross-cutting Finding 1.)
2. **D2 · Fireball collision [BLOCKING].** "When a Fireball meets a wall, shelf, rubble pile, pew, column, or a sealed, locked, open or broken door collider, does it stop, detonate, or pass through? Can it damage an enemy on the other side?"
3. **D3 · Aim, range and expiry [BLOCKING].** "Does the cursor give only a direction, or an exact destination? At maximum range or lifetime with no enemy hit, does the shot fizzle with no damage, or do something else?"
4. **D4 · Mana timing [BLOCKING].** "Is mana spent on press, on release, or gradually? What happens when a charge grows past the mana available?"
5. **D5 · Interrupting a charge [BLOCKING].** "Does taking damage, a move click, or a door click cancel a charge? Is there a way to abort without casting? What happens to a destination clicked while the wizard is rooted?"
6. **D6 · Placeholder feedback [open, not explicitly tagged blocking].** "Is programmer-placeholder world-space feedback acceptable for the first playable Fireball (charge progress, full charge, projectile, blast area)? Or must an approved presentation task come first?"
7. **Pause dispatch [process question, not a design question].** "Should NSC-007 revision 2 be kept from dispatch while D1–D6 are open?" — addressed to "Vincent and Primary Sol," not Vincent alone. The reaudit separately warns: live revision 2 is already `single_agent`/`concrete` with both dependencies delivered, so under the pipeline's own readiness rule it "may already count as ready for dispatch" and could ship with D1–D5 unanswered unless someone explicitly holds it.

### b) GDD evidence per question

| # | GDD citation | Governing text | Verdict |
|---|---|---|---|
| D1 bindings | — | No line anywhere in the 739-line GDD assigns a physical key/button to Fireball, Frost Field, or Force Wave. GDD:64 only says input is "routed through the shared Unity Input System/Input Actions layer" and spells "consume" the shared pointer target. | **GDD SILENT** on the actual binding. |
| D2 collision w/ doors/cover | GDD:23 "Locked doors provide recovery time, not permanent safety." GDD:40 "Safety is always temporary. Doors delay pursuing enemies but do not remove the threat..." GDD:541–543 (door durability/breaking rules) | These establish a *principle* (a locked door must not become a permanently safe firing position) but never state the literal mechanic for a Fireball hitting a door/wall/cover collider. | **GDD SILENT** on the literal rule; GDD:23/40/541-543 constrain the acceptable answer space without supplying it. |
| D3 aim/range/expiry | GDD:65 "Aim with the cursor. Tap for a quick, mobile shot... Hold to charge..." | Confirms tap/charge exists; says nothing about exact-destination vs. direction-only aiming or expiry-without-a-hit behavior. | **GDD SILENT** on range/expiry mechanics. |
| D4 mana timing | GDD:65, GDD:87 (AC-003 reference) "restricts movement further" / "costs more mana"; GDD:86 "Mana regenerates slowly after a brief post-cast delay" | Establishes charge costs more than tap, but never states the trigger point (press/release/gradual) at which the cost is deducted. Force Wave's mana rule (line 91, "spends 25 mana... through Player Mana") is explicit only for Force Wave. | **GDD SILENT** on Fireball's spend-timing. |
| D5 interruption | GDD:68/94/538 (door-interaction interruption rule: "Taking damage, moving away, or issuing another command that cancels/replaces the door approach resets the attempt") | This is an explicit interruption rule, but only for the **door** interaction. No analogous sentence exists anywhere for a spell charge. | **GDD SILENT** on Fireball-charge interruption; the door rule is a plausible analogy, not a stated one. |
| D6 placeholder feedback | GDD:90 "The exact visual or audio treatment is an implementation choice" (Frost Field targeting/feedback bullet only) | GDD explicitly grants Frost Field this license; Fireball has no equivalent sentence. | **GDD SILENT** for Fireball specifically. |

### c) Code state

- **No `Fireball` (or similarly named) component exists anywhere under `Assets/NoSafeCircle/`.** Directly confirmed by file search (`find` for `*fireball*`/`*frostfield*`/`*forcewave*`/`*decoy*`/`*spectral*` returns zero results across the whole tree). This matches the contract's own `"repository_state_at_bootstrap": "missing"`.
- The interfaces Fireball would need already exist and are directly usable: `PlayerMana.Spend(float)` (confirmed by direct read, `PlayerMana.cs:55-68`; returns `false` and raises `CastDenied` on insufficient mana, no side effect otherwise) and `PlayerMovement.PointerWorldTarget`/`HasPointerWorldTarget` (confirmed by direct read, `PlayerMovement.cs:43-44`, recomputed every `Tick`).
- **R-01/R-03 title-screen gap — independently confirmed by direct read of both files in full:**
  - `TitleScreenController.SuspendGameplayInput()` (`TitleScreenController.cs:59-73`) only ever sets `inputBehaviour.enabled = false` on everything in its `gameplayInputBehaviours` array; the entire 76-line file contains no method that re-enables anything in that array.
  - `WizardGameEntryController.EnterWorld()` (`WizardGameEntryController.cs:58-85`) calls exactly `playerMovement.EnableGameplayInput()` and `playerInteractionController.EnableGameplayInput()` (lines 83-84) — nothing else. If Fireball were added to the title screen's suspension array (as AC-010 currently plans), nothing in the live code would ever turn it back on. This is a real, verified bug-in-waiting, not merely an audit claim.
  - A currently-committed test, `Tests/Editor/TitleScreenSceneBuilderTests.cs:112`, asserts the array's size is exactly 2 — adding Fireball would break that test, and no task (including NSC-007) currently locks that test file.

### d) Dependency / file-ownership conflicts

`exclusive_resources`: `DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`, `unity-scene:Assets/Scenes/DoorPrototype.unity`, `Assets/InputSystem_Actions.inputactions`.

- Independently confirmed via `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`: `Assets/InputSystem_Actions.inputactions` is claimed by **exactly** `NSC-003`, `NSC-007`, `NSC-008`, `NSC-009` — the input-bootstrap task and all three spell tasks, and no one else. This means the D1 binding decision has a literal sequencing consequence: only one of these four tasks can touch the asset at a time.
- `DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` is independently confirmed (via `grep -l` across `Tasks/*.yaml`) to be locked by **29 different tasks**, so Fireball's slot in that queue is heavily contended regardless of the design decisions.
- `DoorPrototypeGlobalSceneBuilder.cs` — where the Player GameObject (and its title-screen/game-entry wiring) is actually built — is locked only by `NSC-039, 049, 069, 075, 077` (confirmed independently by grep). **NSC-007 does not lock it**, yet R-03's recommended fix requires editing it. This is a real gap, not just an audit opinion.
- R-08: undeclared dependency on `NSC-066` (owns `TitleScreenController.cs`) and, under fix-option (a), `NSC-068` (owns `WizardGameEntryController.cs`) — neither is in NSC-007's `depends_on` today.

---

## NSC-008 — Frost Field

Contract: revision 2 live, `single_agent`/`concrete`, depends on NSC-003 (delivered), NSC-013 (not delivered).

### a) Open design questions (round-04 §6)

All four are BLOCKING — recommendation: "`needs_design` — do not commit NSC-008 revision 3... Decisions Vincent must make: 1... 2... 3... 4."

1. **Spell controls [BLOCKING].** "Which physical inputs do Fireball (tap/hold), Frost Field and Force Wave use? Left mouse button already means move and door-select... Decide once for NSC-007, 008 and 009."
2. **Frost during the door timer [BLOCKING].** "If the wizard casts Frost while the five-second opening timer runs, does that count as 'another command that cancels/replaces the door interaction' (GDD:94)? ... If it does not reset, NSC-008 needs only a gate test. If it does reset, also decide which component cancels the door: NSC-008 or NSC-019."
3. **Recasting [BLOCKING].** "While a field is active, is a new cast rejected, does it replace the current field, or can several fields exist at once? If several can exist, do overlapping fields slow an enemy once or stack?"
4. **Active field at victory [BLOCKING].** "When victory suspends gameplay, does an active field run until it expires or get cleared immediately? GDD:100 covers 'input-driven activity'; a field that is already placed arguably isn't."

Separately, two **non-design** blockers (not Vincent's call): R-03 (NSC-013/NSC-092 must be revised to expose a real "find/slow enemies in area" interface — see part (c) below) and the now-resolved `InputSystem_Actions.inputactions` "restore" item (see Method note above).

### b) GDD evidence per question

| # | GDD citation | Governing text | Verdict |
|---|---|---|---|
| Bindings | — | Same as NSC-007 D1. | **GDD SILENT.** |
| Door-timer reset | GDD:68/94/538 "Taking damage, moving away, or issuing another command that cancels/replaces the door interaction resets progress." GDD:66 Frost Field "creates an opening to... begin opening a door." | The door rule names damage, moving away, or a cancelling/replacing command — a Frost cast is none of the first two, and "creates an opening to... begin opening a door" reads as *cooperative* with door-opening, not disruptive to it. | **Leaning-but-not-explicit**: GDD text suggests Frost casting should *not* reset the door timer, but never says so directly — the reaudit itself calls this an inference ("suggests not"), not a quoted rule. |
| Recast rule | — | No sentence anywhere addresses casting Frost Field while a field is already active. | **GDD SILENT.** |
| Active field at victory | GDD:98 "...normal gameplay input... stops..."; GDD:100 "...immediately stop or cancel their current **input-driven activity**, reject new commands..." | "Input-driven activity" plausibly means the *casting* action, not a passive already-placed area effect that is no longer receiving input. The GDD never resolves this ambiguity. | **GDD SILENT / ambiguous** — line 100's own wording is the source of the ambiguity, not a separate silence. |

### c) Code state

- **No `FrostField` component exists anywhere** (confirmed by direct search, zero results).
- Frost Field's real prerequisite interface does not exist yet, independent of Vincent's decisions: `NSC-013` (the enemy slow effect) has no begin/end/refresh request method in its current contract (only "restored when the effect ends" language), and no enemy Collider/layer/enumeration exists in the repository that a `FrostField` component could use to find which enemies are standing inside its placed area (confirmed: `ActiveEnemyRegistry.cs`, read directly, exposes only `Register`, `Unregister`, `ResetRegistry` — no spatial query at all). **Frost Field is blocked on a second team's not-yet-built interface, not only on Vincent's decisions.**
- `PlayerMana.Spend` and `PlayerMovement.PointerWorldTarget` are available exactly as for Fireball (see above).

### d) Dependency / file-ownership conflicts

Same three `exclusive_resources` as NSC-007 (`DoorPrototypeSceneBuilder.cs`, `DoorPrototype.unity`, `InputSystem_Actions.inputactions`) — same four-way (`NSC-003/007/008/009`) contention on the input asset.

- R-08 (independently corroborated): the Player GameObject is actually assembled in `DoorPrototypeGlobalSceneBuilder.cs`, which NSC-008 does **not** lock (that file's lock list is `NSC-039, 049, 069, 075, 077` only) — a real gap if Frost Field needs to be wired there.
- `depends_on`: NSC-003 (delivered), NSC-013 (not delivered, and itself needs a contract revision per R-03 before it can unblock NSC-008 at all).

---

## NSC-009 — Force Wave

Contract: revision 2 live, `single_agent`/`concrete`, depends on NSC-013 only (not delivered).

### a) Open design questions (round-04 §6)

Two are explicitly tagged blocking; one explicitly does not block; one is an accepted default; one (owner assignment) is unlabeled.

1. **Force Wave and solid geometry [BLOCKS DISPATCH — explicit].** "Can the wave push an enemy on the other side of a wall collider, a sealed `DoorInteractable`, or a locked one? If it passes through a locked door, it pushes back enemies attacking that door and weakens breach pressure."
2. **Three-spell controls [BLOCKS DISPATCH — explicit].** "Pick one: a dedicated Force Wave Input Action with an approved keyboard/mouse binding, or a select-spell-then-Attack scheme, which would also need rules for Fireball and Frost Field... Also: is a gamepad binding needed now? The binding can't be left-click, because that would trigger MoveToCursor or replace a door approach."
3. **Balance-test owner [unlabeled — not named as a dispatch blocker in the recommendation].** "Which reviewed task owns INT-004: surround escape, door blockers, distant ranged pressure, and roughly one use per encounter?"
4. **Feedback [explicitly "(doesn't block)"].** "Are the cooldown indicator plus displacement enough for the prototype, or should cast or refusal feedback be added?"
5. **Confirm door-timer non-reset [explicitly "(default fits the current GDD)"].** "Casting Force Wave during the five-second door timer doesn't reset the attempt (AC-007)" — presented as already-correct, needing only Vincent's sign-off.

Separately, R-01 (major, non-design): the round-03 refinement adds INT-003 (a title-screen suspension handoff) that, as worded, **cannot be carried out** by any existing task and would actively **break** NSC-066's already-shipped requirement (AC-002: "Before Start Game is activated, normal player movement, spell, and door-interaction input cannot affect gameplay") the moment Force Wave lands, because nothing currently suspends it at the title screen.

### b) GDD evidence per question

| # | GDD citation | Governing text | Verdict |
|---|---|---|---|
| Solid-geometry knockback | GDD:23, 40, 541-543 (same as NSC-007 D2) | Same "doors ≠ permanent safety" principle. | **GDD SILENT** on the literal mechanic. |
| Bindings | GDD:64 "Force Wave is the player-centered exception" (to cursor-aim) | Confirms *no cursor* is used, assigns no button. | **GDD SILENT** on the physical key. |
| Balance-owner | — | Organizational/pipeline question. | Not a GDD matter. |
| Feedback | GDD:576 "Failure is readable: poor positioning, low mana, using Force Wave without an immediate threat..." | General readability principle only; no specific feedback requirement for a refused cooldown press. | **GDD SILENT** on the specific case. |
| Door-timer confirm | GDD:68/94/538 (only damage, moving away, or a cancelling/replacing command reset the door attempt) | Force Wave is none of those three by the letter of the rule. | **GDD actually answers this by omission** — the reaudit calls it "the default direction the current GDD already supports," which is why it's tagged "Confirm" rather than an open question. |

### c) Code state

- **No `ForceWave` component exists anywhere** (confirmed, zero results).
- Unlike Frost Field, Force Wave's downstream interface **already exists**: `EnemyStatusEffectMovement.RequestDisplacement(Vector3, float)` is cited at `EnemyStatusEffectMovement.cs:100` (file confirmed present at `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies/EnemyStatusEffectMovement.cs`). Force Wave is materially less blocked on other teams' code than Frost Field is.
- `PlayerMana.Spend` is available (confirmed, see NSC-007/008 above).

### d) Dependency / file-ownership conflicts

Same three `exclusive_resources` as NSC-007/008. `depends_on`: NSC-013 only (not delivered).

- R-01's fix would require adding `TitleScreenController.cs` and `WizardGameEntryController.cs` to NSC-009's locks — independently confirmed **neither file is currently locked by NSC-009**, and confirmed by direct read (see NSC-007 §c above) that `WizardGameEntryController.EnterWorld` re-enables only `playerMovement` and `playerInteractionController` today, exactly as the audit states.

---

## NSC-030 — Dungeon Encounter Placement and Composition Authoring

Contract: revision 3 live. This is a `kind: feature` / `execution_scope: not_applicable` / `decomposition_state: needs_future_decomposition` parent node with **empty** `exclusive_resources` — it does not itself get implemented; it gates the not-yet-created per-room encounter children.

### a) Open design questions (round-04 §6)

Recommendation explicitly splits these: "Decisions 1, 2 and 5 below change contract text... Decisions 3, 4, 6 and 7 are child-level values and do not block the commit."

1. **Pending-enemy policy [BLOCKING].** "Keep delaying them in request order? If so, a Chapel batch still pending after D3 locks blocks Lower Vault and Final Room admission, then activates behind a locked door where it keeps registry slots. Or reduce/cancel a room's still-pending enemies when the wizard crosses that room's exit door? Also: at which events does `ProcessPendingAdmissions` retry?"
2. **Ranged support under the cap [BLOCKING].** "Is listing a Melee Enemy before any Ranged Enemy in each request enough? Or must every Ranged Enemy wait until a Melee Enemy from its own encounter is active?"
5. **Chapel spawn-to-cover rule [BLOCKING].** "Approve or reject: from each Ranged spawn position, a real pew or column collider must block the line to CA-W or CA-E."
3. **Rosters [non-blocking, child-level].** "The count (3–8) and Melee/Ranged split for each room, including Lower Vault... Also confirm that three Melee Enemies still teach circling in Ruined Entry."
4. **Triggers and regions [non-blocking, child-level].** "How many activation triggers each room has, where they go, and each room's spawn/reset region boundaries. This includes whether regions may sit in door staging areas."
6. **Door durability [non-blocking, child-level].** "Values for D1–D4, and whether D5 gets a value or is exempt."
7. **Final Room pressure [non-blocking, child-level].** "What it means as authored content, without adding waves or reinforcements (Candidate B stays unapproved)."

### b) GDD evidence per question

| # | GDD citation | Governing text | Verdict |
|---|---|---|---|
| 1 pending-enemy policy | GDD:550 "If activating the requested enemies would exceed fifteen active enemies, new encounter enemies are **delayed or reduced** first; existing persistent pursuers are never removed to make room." | Explicitly authorizes *either* delay *or* reduction as the menu of options, but never says which trigger/event should retry a delayed batch, nor what happens once the wizard has already left that room. | **Partially GDD-governed** (the two allowed options are named); **GDD SILENT** on the retry trigger and cross-room edge case. |
| 2 ranged-under-cap ordering | GDD:518 "Ranged Enemies never appear as an isolated encounter: every encounter that introduces one also includes at least one Melee Enemy." | Governs *authoring/composition* — every encounter must include a melee enemy. Says nothing about admission-time ordering once the registry forces a partial/delayed admission. | **GDD SILENT** on the admission-sequencing question specifically. |
| 3 rosters | GDD:575 "Encounters use three to eight enemies and never exceed fifteen active enemies." | A range only; exact numbers are explicitly deferred by the GDD itself to authoring/playtesting. | Explicitly deferred, not silent. |
| 4 triggers/regions | — | No GDD text addresses exact trigger-volume placement (expected — GDD:509 "Room size authority" delegates this precision to Task Design GER). | **GDD SILENT** by design. |
| 5 Chapel spawn-to-cover | GDD:373-379, specifically line 379: "**At least one of CA-W or CA-E must be geometrically occluded** from a representative straight-line ranged attack crossing from the opposite half of the chapel by a real pew or column collider." | This occludes the **cover pockets** (CA-W/CA-E) from attacks. It does **not** say Ranged Enemy **spawn positions** must themselves be pre-occluded from a cover pocket — that is a materially different, stronger rule that VAL-005 tried to add unapproved (confirmed as the reaudit's own R-01 finding). | **GDD explicitly covers the cover-pocket rule; GDD SILENT on / does not require the stronger spawn-position rule.** |
| 6 door durability | GDD:93 "Door feedback: Banging, shaking, cracks, and a durability indicator..." (concept only); GDD:594/607 assign durability-value authoring to the Dungeon Encounter Agent. | No numeric values anywhere. | **GDD SILENT** on values, explicitly delegated to this task. |
| 7 Final Room pressure | GDD:118 "...populated by both Melee and Ranged Enemies. The player must combine movement, Frost Field, Force Wave, and Fireball to create the final uninterrupted five-second escape window." | Qualitative tactical intent only. | **GDD SILENT** on exact composition. |

### c) Code state

The shared runtime *foundation* already exists and is more built-out than the other tasks in this pack: `EncounterAdmissionController.cs` and `ActiveEnemyRegistry.cs` both exist under `Assets/NoSafeCircle/DoorPrototype/Scripts/`, each with a dedicated PlayMode test file (`EncounterAdmissionControllerPlayModeTests.cs`, `ActiveEnemyRegistryPlayModeTests.cs`) — all four confirmed directly present. Per the reaudit's line-level citations (not independently re-verified line-by-line by me, but consistent with the file's confirmed existence): `ProcessPendingAdmissions` already admits enemies in list order (`:128-150`), and `RequestAdmission`/`RequestedBatchCount` already exist (`:60,100-101`). **What is missing is exclusively per-room content** — no roster, trigger, or durability data exists yet, because NSC-030 has never been decomposed into children (its own `exclusive_resources` is `[]`).

### d) Dependency / file-ownership conflicts

`depends_on`: NSC-028, NSC-050, NSC-015, NSC-055. Its own `exclusive_resources` is empty (feature-level placeholder). Its eventual children will need `DoorPrototypeSceneBuilder.cs`, `DoorSequenceBuilder.cs`, and the `DoorPrototype.unity` scene — the same 29-task contention queue on `DoorPrototypeSceneBuilder.cs` documented under NSC-007 above, plus R-10's finding that `NSC-089` also locks that builder/scene and is missing from NSC-030's current sequencing note (INT-005).

---

## NSC-078 — Reusable Dark-Cute Dungeon Prop Art Pack

Contract: revision 2 live, `single_agent`/`concrete`, depends on NSC-064 (not delivered — "Pipeline/TaskGraph has no NSC-064 evidence").

### a) Open design questions (round-04 §6)

1. **D-2, file ownership [BLOCKING — "blocks the file list"].** "For base straight walls, corners, end caps, floors, pillars or columns, pews, shelves, rubble and storage: does NSC-064 own them, with NSC-078 adding only variants? Who owns the near-wall cutaway stub family? Does NSC-064 get its own GER now, to publish an exact inventory path and schema, own `Art/Environment.meta`, and replace its 'Assistant art-selection review' with a Vincent gate?"
2. **D-1, texel density [soft-blocking — "can be answered now or at the style-lock pilot review, but must be settled before any family acquisition"].** "Should props and architecture share the 64-px-per-cell architecture density, match the wizard's 180 PPU, or use documented mixed densities?"
3. **D-4, PixelLab post-processing [conditionally blocking — "If seam repair is forbidden, a failing wall repeat check stops the task as blocked"].** "Are deterministic crop, trim, alpha cleanup, palette reduction or seam repair allowed? Are the raw selected exports committed next to the processed files...?"
4. **D-3, Lower Vault [explicitly NOT a precondition for NSC-078].** "Should NSC-047 get reviewed water or crossing geometry through a GER, or should NSC-082 AC-005 be revised to fit the current blockout? Are lava, chasm and horn trim first-wing content, or only vocabulary for the future expansion (NSC-085)?"

### b) GDD evidence per question

All four of these are **task-graph/ownership and production-pipeline questions, not GDD questions** — the GDD does not assign file ownership between sibling tasks, does not specify pixels-per-unit for any asset, and does not discuss image post-processing tooling.

| # | GDD citation | Verdict |
|---|---|---|
| D-2 ownership split | — | **GDD SILENT** (correctly so — this is pipeline/task-graph territory). |
| D-1 texel density | — | **GDD SILENT.** GDD:670/681 mandate Tilemap-for-architecture / SpriteRenderer-for-props as a rendering split but state no pixel density anywhere. |
| D-4 post-processing | GDD:642 "Development-time generative tools may be used to create isometric tiles, props, and directional sprites, but once imported they behave as ordinary Unity assets." | Permits generative-tool use generally; **GDD SILENT** on whether deterministic post-processing of the generated output is permitted. |
| D-3 Lower Vault hazard art | — | **GDD SILENT** — this is an NSC-047-vs-NSC-082 authoring conflict the GDD never anticipates, and per the reaudit's own R-05 it should not gate NSC-078 regardless. |

### c) Code state

Confirmed directly: no `PropCatalog.json` exists anywhere under `Assets/` (zero search results), and `Assets/NoSafeCircle/DoorPrototype/Art/` contains only `Wizard.meta` — no `Environment.meta` folder file exists yet for any of NSC-064/078–084 to claim. This is a pure art-acquisition task with nothing built, consistent with `"repository_state_at_bootstrap": "missing"`.

### d) Dependency / file-ownership conflicts

`exclusive_resources`: `logical:pixellab-dungeon-prop-art`, `Art/Environment/Props/Source`, `Art/Environment/Props/PropCatalog.json`, `Docs/Art/Environment/PROPS_PIXELLAB_GENERATION.md`.

- **Direct conflict:** NSC-064's contract (`NSC-064.yaml:30`, per the reaudit) claims the same base-architecture noun set (floor, wall, rubble, shelf, pew, column, storage) that NSC-078's own revision-2 `visual_direction_addendum` also lists. Two tasks currently describe ownership of overlapping content with no resolved boundary — this is exactly D-2.
- **Shared unowned file:** `Assets/NoSafeCircle/DoorPrototype/Art/Environment.meta` (the parent folder's Unity meta file) is claimed by **none** of NSC-064 or NSC-078–084 today, yet all of them would create it on first write — a live collision risk across up to seven tasks if any two run concurrently.
- `depends_on` NSC-064, which has no delivery evidence yet.

---

## NSC-085 — Expanded Dungeon Route Graph and Side Chambers

Contract: revision 2 live, `single_agent`/`proposed` (planning-parent shape), depends on NSC-084 (not delivered), parent NSC-022.

### a) Open design questions (round-04 §6)

The recommendation names three reasons the contract can't commit, tied to decisions 1, 2, and part of 8; decisions 3–7, 9–10 are also needed to finalize the plan but are not individually cited as commit-blockers in section 5.

1. **Structure (D-1) [BLOCKING — "the structure isn't approved... needs Vincent's approval before it is executable"].** "Should NSC-085 be a two-file planning task (`ExpandedDungeonRouteGraph.md` and `.svg`), with room and corridor implementation in a separate aggregate decomposed later?"
2. **GDD scope [BLOCKING — headline conflict, see Cross-cutting Finding 2].** "Will you add an 'Expanded Dungeon Wing' section to the GDD that goes beyond the 'one additional room' stretch goal (GDD:560)? Where does the wing sit relative to D5 and You Escaped: before D5, replacing D5, or optional? Do the exclusions of multiple floors, loot and persistent progression (GDD:558) change?"
3. **Connection.** "Which first-wing room and wall side does the wing attach to, and through an existing or a new door role? Do you accept that opening a first-wing wall... needs its own GDD and first-wing contract revision?"
4. **Content.** "How many mandatory and optional rooms and corridors, and what is the destination? Which enemies and encounters, if any? Do persistence, restart and the 15-enemy cap cover the wing?"
5. **Traversal rules.** Loops inside encounter regions; how gates/shortcuts/return routes work "given that doors are forward-only"; what a "reward room" gives "given that loot is excluded"; whether elevation changes are walkable or visual only; whether hazards are damaging, non-walkable, or background.
6. **Scale.** "What room, corridor, passage and door widths apply to the new wing? GDD §13 doesn't govern it."
7. **Biome.** "Is the natural-cavern branch from your 2026-09-13 direction still required? Is an infernal or corrupted destination part of this wing?"
8. **References [BLOCKING in part — "the reference mapping is unconfirmed"].** "Are R13 (constructed) and R15 (cavern) the 'macro layouts' your rev-2 criteria refer to? Are R16 and R17 the 'reference map'? Should R11 and R12 be in the originality comparison?"
9. **Dependency.** "Should topology-only planning still wait for NSC-084?"
10. **Later implementation.** "Which parent should the later aggregate sit under (not NSC-022)? ... new parallel files, or a sequenced revision of NSC-069's and NSC-049's files?"

### b) GDD evidence — see Cross-cutting Finding 2 for the full quote-and-line-count answer. Summary per question:

| # | GDD citation | Verdict |
|---|---|---|
| 1 structure | — | Task-graph/process question. **GDD SILENT** (not a GDD matter). |
| 2 GDD scope | **GDD:560** "one additional room" (exact quote and analysis in Cross-cutting Finding 2); GDD:558 excludes "multiple floors" and "persistent progression"; GDD:143-149 (blockout) excludes "new... rooms, doors, enemies, spells, progression, lore, or rewards." | **GDD directly conflicts** with NSC-085's planned scope — see below. |
| 3 connection | GDD's five-room topology (lines 192-241) is fixed; D5 is fixed as "the final door" (line 443). | **GDD SILENT** on where/how a wing would attach — the current topology has no stated extension point. |
| 4 content | GDD:104 "adding later rooms or stateful systems must extend the reset participants without redesigning the orchestration contract" — the *only* place the GDD contemplates "later rooms" as a technical possibility, but only as a restart-orchestrator footnote. | **GDD SILENT** on content/count; line 104 is a plumbing constraint, not scope authorization. |
| 5 traversal | GDD:541-543 "the floor is a forward-only escape sequence... The player cannot travel backward through an earlier doorway." | Any wing "gate/shortcut/return route" must respect the existing forward-only rule — a real, explicit constraint the plan must honor. |
| 6 scale | GDD §13 (line 509) explicitly: "The room sizes and coordinates in this blockout are baselines... Each room may grow up to three times its listed width and depth" — but this is scoped to the five *named* rooms. | **GDD SILENT** for a new wing ("GDD §13 doesn't govern it," confirmed by direct reading of §13's own room-by-room scope). |
| 7 biome | — | **GDD SILENT** — the cavern-biome direction lives only in Vincent's 2026-09-13 art-direction note and NSC-085 revision 2, never in the GDD itself. |
| 8 references | — | Not a GDD question (image-mapping / production question). |
| 9 dependency | GDD:610 "Shared-write conflicts are sequencing/locking concerns, not proof of a dependency unless one task actually requires behavior another task must create first." | Directly relevant general principle; doesn't resolve whether NSC-085 specifically needs NSC-084 first. |
| 10 later-parent | NSC-022.yaml:33 (task-graph fact, not GDD). | Not a GDD matter. |

### c) Code state

Confirmed directly: **no `Docs/World/` directory exists at all** ("No such file or directory"), and no `ExpandedDungeonRouteGraph.md` or `.svg` exists anywhere in `Docs/` (zero search results). Nothing has been authored — expected, since this is a planning-only task and even its own deliverable files don't exist yet.

### d) Dependency / file-ownership conflicts

`exclusive_resources`: `Docs/World/ExpandedDungeonRouteGraph.md`, `logical:expanded-dungeon-route-graph` — nothing else in the repository currently claims these paths (no active conflict). `depends_on` NSC-084 (undelivered; decision 9 asks whether to even keep this). Parent is NSC-022, but `INT-001` explicitly forbids placing the later room/corridor implementation children under NSC-022 by default. `AC-004` requires NSC-085 to leave NSC-078 through NSC-084 (the first-wing content tasks) untouched and un-blocked — i.e., this task must not become a bottleneck for the required five-room content work.

---

## NSC-088 — Spectral Decoy Spell and Enemy Redirection

Contract: revision 3 live, `source_scope: stretch`, `execution_scope: unknown`, `decomposition_state: coarse`, **empty** `exclusive_resources` and **empty** `completion_gates` (a deliberate design-hold record, not an executable contract — `record_delivery.py` would reject an empty gate list outright, confirmed by the reaudit's own commit-check table).

### a) Open design questions (round-04 §6)

None of the 11 items carry an explicit blocking/non-blocking tag the way NSC-009/030 do, but the contract's own empty `exclusive_resources`/`completion_gates` show that **nothing is executable until these are answered** — item 1 is the threshold gate, item 2 is the "core conflict" the recommendation names explicitly, and item 11 is explicitly sequenced last.

1. **Accept it? [threshold].** "Implement Spectral Decoy as a stretch feature (GDD:644), or decline it."
2. **Pursuit rule [core conflict — see Cross-cutting Finding 3].** "Amend GDD:526-537 so an enemy can be redirected off the wizard, or reshape the concept... decide which distance governs acquisition and loss: to the wizard, to the phantom, or both."
3. **Which enemies.** Melee/Ranged/both; how many per cast and priority; what wizard knowledge is retained; state after expiry/destruction/route failure/reacquisition.
4. **Cast and route.** "Cast input: the Input Actions asset has only `PointerPosition` and `MoveToCursor`, and NSC-003/007/008/009 hold its lock" (ties directly to Cross-cutting Finding 1). Route choice (clicked point vs. direction/branch); behavior on an invalid route.
5. **Rooms.** Per-room caveats for Bone Archive (pull limits vs. the BA-1 pinch), Chapel (does the phantom remove the central-aisle risk?), Lower Vault (could it create the forbidden safe loop, or neutralize the D3 rear-breach?), Ruined Entry/Final Room (refused/reduced/allowed with no corridor?).
6. **Attacks and spells.** Do Ranged Enemies/projectiles target the phantom? Can Melee destroy it? What happens after Frost Field/Force Wave hits a redirected enemy? Can the phantom itself be slowed/knocked back?
7. **Doors.** Behavior at sealed/open/locked/broken doors; whether it may lead pursuers ahead of the wizard through an open door; backward travel through broken doorways (flagged explicitly against R-02's finding, see part (c)); persistence across rooms; whether a phantom-following enemy can attack a locked door.
8. **Limits and cost.** Lifetime, destruction, concurrent limit, mana cost, cooldown, and whether mana is spent before or after route validation.
9. **Balance guardrail.** Adopt or revise: "the Decoy alone does not guarantee the five uninterrupted door seconds... and does not reliably answer both enemy types."
10. **Feedback.** Required gameplay-camera feedback; whether per-enemy target-switch display overlaps the separate awareness-indicator stretch goal (GDD:560).
11. **Other contracts [sequenced last].** Revise GDD §2/§3 and the success criteria (609); revise NSC-033 (restart) and NSC-087/NSC-086 (victory suspension); then run D1B.2 decomposition.

### b) GDD evidence — see Cross-cutting Finding 3 for the full quote-and-verdict. Summary:

| # | GDD citation | Verdict |
|---|---|---|
| 1 accept? | **GDD:560** "Spectral Decoy" listed as a stretch goal; **GDD:644** "...and decides which stretch features are accepted." | GDD explicitly makes acceptance the developer's call — this is the one question the GDD directly assigns to Vincent. |
| 2 pursuit rule | **GDD:526-537** (full quote in Cross-cutting Finding 3) | **Does not authorize redirection** — see below. Directly conflicts with Vincent's "draw pursuing enemies after it" direction as recorded in `USER_PROBLEM.md`. |
| 3 which enemies | GDD:513-518 (Required Enemy Roster) describes Melee/Ranged behavior only relative to the wizard. | **GDD SILENT** on any decoy-eligibility distinction. |
| 4 cast/route input | GDD:64/89 (shared pointer-target rule) | If cursor-based, must reuse `PlayerMovement.PointerWorldTarget` like the other cursor-aimed abilities — a real constraint, not silence. |
| 5 rooms | GDD:117 (Lower Vault "several incomplete loops," not one safe circuit); GDD:322-385 (Chapel cover/aisle tradeoff); GDD:436 (Final Room: "movement and the existing spell kit") | These sections describe the *current*, non-decoy tactical intent for each room; the GDD is **silent** on how a decoy would interact with any of them — that interaction is exactly what would need authoring once accepted. |
| 6 attacks/spells | GDD:685/688 (ownership: Frost slow "applied and restored by Enemy Pursuit"); no decoy-interaction text. | **GDD SILENT.** |
| 7 doors | GDD:541-543 (door passability / forward-only rule); confirmed in code (`DoorEnemyPassability.cs`) that open/broken doorways carry no directionality (see part (c)). | GDD is explicit about forward-only *for the player*; **SILENT** on a phantom's direction of travel, and the code has no directional gate to enforce whatever is decided. |
| 8 limits/cost | GDD:83-92 (general mana/spell-state ownership pattern) | Pattern exists for the other three spells; **GDD SILENT** on Decoy's specific numbers (expected — same as the other spells' D3/D4-style gaps). |
| 9 guardrail | GDD:40-41 (design pillars), GDD:79 ("No single spell reliably answers both enemy types by itself") | Directly-quotable governing text the guardrail already paraphrases correctly (R-04 only flags a narrowing paraphrase to fix). |
| 10 feedback | GDD:560 (awareness-indicator is a *separate* stretch goal) | GDD explicitly treats these as two different stretch features — useful boundary, but **silent** on whether Decoy may borrow that presentation. |

### c) Code state

- **No Decoy/phantom component exists anywhere** (confirmed, zero search results for `*decoy*`/`*spectral*`).
- **The enemy-target system is structurally single-target today** — confirmed by full direct read of `EnemyTargetKnowledge.cs`: `wizardTransform` is the only target field (line 23), `AcquireTarget()` unconditionally does `CurrentTarget = wizardTransform;` (line 119), and both acquisition (`UpdateTargetKnowledge`, lines 85-115) and loss are pure functions of `Vector3.Distance(transform.position, wizardTransform.position)`. There is no branch point anywhere in this 151-line file for a second candidate target. Adding Spectral Decoy requires a real structural change to this class, not just a new component bolted alongside it.
- **R-02's door-directionality finding is independently confirmed** by full direct read of `DoorEnemyPassability.cs`: `SetDoorState` (lines 50-60) only toggles one `NavMeshObstacle`'s `carving`/`enabled` flags on/off — there is no concept of direction anywhere in the 82-line file. An open or broken doorway is genuinely walkable both ways today; nothing would stop a NavMesh-driven phantom from walking backward through one unless new code is written.

### d) Dependency / file-ownership conflicts

`exclusive_resources` is `[]` (pure design hold — nothing owned yet). `depends_on`: NSC-003, NSC-091, NSC-092, NSC-089 (none delivered, per the reaudit's evidence-folder check).

- Once this moves forward, any cast-input action would need `Assets/InputSystem_Actions.inputactions`, already locked by exactly `NSC-003/007/008/009` (independently confirmed via `RESOURCE_GROUPS.yaml`, see NSC-007 §d) — Decoy would be a **fifth** claimant on that same file.
- Victory-suspension proof needs a revision to `NSC-087` (to add a sixth suspend participant beyond its current five) and `NSC-086`; restart proof needs a revision to `NSC-033`, which is itself already flagged `needs_execution_decomposition` in its own contract.

---

## Cross-cutting findings

### 1. Are the three spell bindings (NSC-007/008/009) constrained or free?

**`Assets/InputSystem_Actions.inputactions`** (read in full) is Unity's stock "InputSystem_Actions" template asset with two custom actions added on top. Its `Player` action map defines **11 actions total**:

| Action | Bound to | Consumed by any script under `Assets/NoSafeCircle/`? |
|---|---|---|
| `PointerPosition` | `<Mouse>/position` | **Yes** — `PlayerMovement.cs:72`, `FindAction("PointerPosition")` |
| `MoveToCursor` | `<Mouse>/leftButton` | **Yes** — `PlayerMovement.cs:73`, `FindAction("MoveToCursor")` |
| `Move` | WASD/arrows/gamepad stick/joystick/XR | No |
| `Look` | gamepad right stick/mouse delta/joystick hat | No |
| `Attack` | **`<Mouse>/leftButton`**, Gamepad West, Touchscreen tap, Joystick trigger, XR primary, `<Keyboard>/enter` | No |
| `Interact` | `<Keyboard>/e` (Hold interaction), Gamepad North | No |
| `Crouch` | `<Keyboard>/c`, Gamepad East | No |
| `Jump` | `<Keyboard>/space`, Gamepad South, XR secondary | No |
| `Sprint` | `<Keyboard>/leftShift`, Gamepad left-stick-press, XR trigger | No |
| `Previous` | `<Keyboard>/1`, Gamepad dpad-left | No |
| `Next` | `<Keyboard>/2`, Gamepad dpad-right | No |

I independently grepped every `.cs` file under `Assets/NoSafeCircle/` for `Attack`, `Interact`, `Crouch`, `Jump`, `Sprint`, `Previous`, `Next`, `Move`, `Look`, `FindAction`, `InputAction`, `PlayerInput`: the only real hits are `PlayerMovement.cs`'s two `FindAction` calls quoted above, plus incidental substring matches (`PlayerInteractionController`, `DoorInteractionFeedback`, `InteractPrompt` — not the `Interact` action) in two test files. **`PlayerMovement.cs` is the sole consumer of this asset in the entire codebase, and it reads exactly two actions.**

**Conclusion: the decision is not literally forced by anything wired today (nothing but left-click drives real gameplay), but it is not a blank slate either.** Six keyboard keys (E, C, Space, Shift, 1, 2) plus Enter and several gamepad/XR/touch bindings are *already named and defined* as unused Input Actions sitting in the checked-in asset. A designer can either repurpose those existing dead actions for Fireball/Frost Field/Force Wave (and later Decoy) with zero new asset entries, or add 3-4 cleanly-named new actions — both paths are open. One thing is **not** open, and predates the spell work entirely: `<Mouse>/leftButton` is **already double-bound** today, to both the vestigial `Attack` action and the load-bearing `MoveToCursor` action — a latent collision worth flagging to Vincent regardless of what gets decided for the spells. What *is* constrained is the **file itself**: `RESOURCE_GROUPS.yaml` confirms `Assets/InputSystem_Actions.inputactions` is locked by exactly `NSC-003, NSC-007, NSC-008, NSC-009` — only one of those four tasks can edit it at a time, and NSC-088 would need a fifth claim later.

### 2. NSC-085's multi-room wing vs. the GDD's one-room stretch goal

Exact quote, **GDD line 560** (the last line of the "Required Scope, Exclusions, and Stretch Goals" subsection):

> "**Stretch goals:** Spectral Decoy, a third enemy, Fireball-charge reactions, an awareness indicator, Frost Field slowing a breach, advanced door damage, and **one additional room**."

Supporting exclusions, **GDD line 558**:

> "**Excluded:** multiplayer, classes, equipment, loot, skill trees, quests, vendors, procedural generation, persistent progression, **multiple floors**, bespoke 3D character models or rigs, free-rotation 3D camera presentation, and generative AI during play."

And the blockout's own non-authorization list, **GDD lines 143-149**:

> "This blockout does **not** add or authorize: ... new mechanics, **rooms**, doors, enemies, spells, progression, lore, or rewards..."

**The GDD permits exactly one (1) additional room as a stretch goal — not a wing.** NSC-085's own acceptance criteria describe something categorically larger: "branching paths, at least one navigable loop, optional dead-end reward rooms, short connector corridors" (AC-001) plus "an original natural-cavern branch with irregular chamber outlines... one hub-like junction, at least one loop... connections back into constructed masonry rooms" (AC-002) — i.e., multiple rooms, corridors, a hub, and at least one loop, which is several rooms beyond one by any reading. This is a direct, numeric conflict with current canon, not a matter of interpretation, and it is exactly why the reaudit's decision 2 requires Vincent to actually amend the GDD before this contract can be anything but a design hold.

### 3. NSC-088 Spectral Decoy — does GDD:526-537 authorize luring enemies off the wizard?

Exact quote, **GDD lines 526-532 and 537** (the full "Enemy Detection, Pursuit, and Target Loss" section plus the first "Door and Pursuit Rules" bullet; lines 533-534 are blank in the source file):

> "526: Each enemy uses a **Detection Distance** for acquiring the player and a larger **Lose Target Distance** for breaking active pursuit. Detection Distance must be smaller than Lose Target Distance so an enemy does not rapidly alternate between acquiring and losing the player at one boundary.
> 527: When the player enters Detection Distance, the enemy acquires the wizard as its target and pursues according to its archetype. Crossing an open doorway does not by itself clear that target.
> 528: When the player moves beyond Lose Target Distance, the enemy stops tracking the player's exact current position and enters a search state using the player's last known position. The distance threshold determines this transition; randomness does not decide whether the enemy forgets the player.
> 529: The enemy continues toward the last known position. If it reaches that position without reacquiring the player, it performs a short, bounded search/wander using controlled randomness to choose a nearby navigable direction or point, periodically checking for the player again.
> 530: If the player re-enters Detection Distance during search/wander, the enemy reacquires the wizard and returns to normal pursuit.
> 531: If the bounded search completes without reacquisition, the enemy clears the target and returns to its local idle/wander behavior. Losing the target does not despawn, replace, or reset the enemy; it remains the same persistent enemy object and can be encountered again later.
> 532: Exact Detection Distance, Lose Target Distance, search duration, and search/wander weighting are tuning values to be established during playtesting.
>
> 537: Enemies move between rooms through open doors; crossing a doorway does not clear pursuit. Active pursuit is lost only through the distance-and-search behavior defined in **Enemy Detection, Pursuit, and Target Loss**."

**No — this passage does not authorize luring enemies away from the wizard.** It states the opposite as the current, unconditional rule: an enemy's target is always the wizard (there is no other target type in the model at all), acquisition and loss are governed **purely by distance and a bounded random search**, and pursuit is explicitly *not* cleared by crossing a doorway (line 527, restated at line 537). Nothing in this section — or anywhere else in the 739-line GDD — describes a mechanism by which an enemy's tracked target could be switched from the wizard to a second object such as a phantom/decoy. This is precisely the "core conflict" the reaudit names: Vincent's recorded direction ("draw pursuing enemies after it... slip past while they chase the phantom," per `USER_PROBLEM.md`) requires an actual amendment to GDD:526-537, which is why NSC-088 AC-002 makes a GDD amendment an explicit prerequisite and why the live contract's `exclusive_resources` and `completion_gates` are both empty — there is nothing yet approved to build or test. This is corroborated by the code: `EnemyTargetKnowledge.cs` (read in full) has no second-target concept anywhere in its 151 lines; today's implementation is structurally incapable of representing "chasing the phantom instead of the wizard" without new design and new code.
