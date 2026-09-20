# NSC-030 decision brief — Room Enemy Encounters: Spawn Regions, Activation Triggers, and Door Durability Values

For the GER owner, to write an owner-decision revision. Read-only research, 2026-09-16.

**Sources**
- GER packet (`needs_design`, finished 2026-09-14 12:32 UTC): `C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\RoomContentGER\20260914-065035-NSC-030\` — cited below as `01-codex-generate/OUTPUT.md`, `02-claude-evaluate/OUTPUT.md`, `03-codex-refine/OUTPUT.md`, `04-claude-reaudit/OUTPUT.md`. Frozen source commit `38904af1`, task revision 3. The older `20260914-010000-NSC-030-gameplay` packet has only `GER_PACKET.md` and `SOURCE_IDENTITY.json` — no rounds — and adds nothing beyond it.
- Owner's questions: `C:\nscrev\reports\ger-overnight-20260914.md` (cited `overnight.md:LINE`), questions 13–19 plus the encounter framing at lines 246–265.
- Repo, read-only, `C:\NSC\NSC\NoSafeCircle` (paths relative to this root unless noted), local main `95492e43d7519049c32056b6548c13765cdc157c` (verified directly: `git rev-parse HEAD`).
- `Tasks/NSC-030.yaml` on main is still **revision 3, byte-identical** to what the packet started from (verified by direct read) — the packet's proposed revision 4 was never committed.

---

## 1. Round-04 final recommendation and every blocking design question

**Verdict: `needs_design`, do not commit revision 4** (`04-claude-reaudit/OUTPUT.md:167-174`). Two findings change contract text and must wait on Vincent; a third (R-01, below) also changes contract text but is really a scope correction, not a new design fact.

**Round history** (all three rounds independently reached the same call):
- **Round-01** (`codex-generate`) proposed AC-001 as "a Ranged Enemy may remain alone only after its authored Melee support is defeated" and a Chapel VAL-004 re-running NSC-072's projectile/target-memory proof (`01-codex-generate/OUTPUT.md:271,329`).
- **Round-02** (`claude-evaluate`) found both wrong: FIFO admission can activate a lone Ranged Enemy under partial capacity (F-01, blocking), and nothing wires the registry/controller into the canonical scene (F-02, blocking) (`02-claude-evaluate/OUTPUT.md:18-49`). It first raised the FIFO-vs-reduce policy question as F-03 (`OUTPUT.md:50-63`) and recommended `needs_design` (`OUTPUT.md:245-260`).
- **Round-03** (`codex-refine`) fixed F-01 into AC-001's Melee-before-Ranged ordering and fixed F-02 into AC-005's scene-wiring text, but left F-03 as an **unresolved either/or embedded in AC-006 itself** ("Vincent approves one pending-admission policy: either … or …") and added a **new, unapproved placement rule** in VAL-005 (Chapel linecast-to-cover) that F-05 hadn't asked for (`03-codex-refine/OUTPUT.md:17-21`). Verdict `needs_design` (`OUTPUT.md:381-399`).
- **Round-04** (`claude-reaudit`, independent) confirmed AC-001/AC-005 are now correct (F-01, F-02 **resolved**, `04-claude-reaudit/OUTPUT.md:32-33`), but caught both remaining problems as fresh major findings:

| ID | Severity | What's wrong | Maps to owner question |
|---|---|---|---|
| **R-02** | major | AC-006 is a design hold written into contract text ("either … or …"), and VAL-003/VAL-004 have no single assertable expected result — a Chapel batch left pending after D3 locks can activate behind a locked door in an empty room and silently rob the Final Room of its required mixed pressure (`04-claude-reaudit/OUTPUT.md:58-68`). | **13** |
| **R-01** | major | VAL-005's Chapel linecast rule is `requires_design_approval` content sitting in contract text, against the packet's own instruction that such content "becomes an open question for Vincent, never contract text" (`04-claude-reaudit/OUTPUT.md:48-56`). | **17** |
| (framing only, not a new finding) | — | Whether Melee-before-Ranged *listed order* is enough, or every Ranged Enemy must wait for an *active* Melee Enemy from its own encounter. | **14** |

Round-04's own path to commit (`OUTPUT.md:171-174`): once Vincent answers 13/14/17, (1) rewrite AC-006/VAL-003/VAL-004 to the single chosen result, (2) delete or convert VAL-005 per R-01, then apply R-03–R-10 verbatim (section 2), (3) commit. Decisions 15, 16, 18, 19 are child-level values and don't block the commit.

**Contract-commit checklist** (`04-claude-reaudit/OUTPUT.md:127-165`): (a) JSON/field-set — **pass**; (b) GDD/art-direction consistency — **partial** (fails only on R-01/R-02/R-07/R-08); (c) ownership/`exclusive_resources` — **pass, with R-03/R-10**; (d) dependencies — **pass, with R-03**; (e) gates locally completable — **fails until R-01, R-02, R-06 are fixed**; (f) concrete Unity language — **pass**.

---

## 2. Every required non-design fix (R-03–R-10, `04-claude-reaudit/OUTPUT.md:70-125`)

One line each; exact replacement text quoted where the re-audit gives it verbatim.

- **R-03 (major).** INT-001/AC-009/VAL-006 route the authored spawn/reset-region handoff through **NSC-092**, but NSC-092 has no dependency on NSC-030 and sits *earlier* in the graph (reached only indirectly through NSC-015/017/071) — a D1B.2 edge from NSC-092 to an encounter child would cycle. Fix: replace INT-001, AC-009's 2nd–3rd sentences, and VAL-006's last two sentences with the re-audit's verbatim text routing the reset proof through **NSC-033** instead, with NSC-092 receiving no dependency on NSC-030 work (`OUTPUT.md:70-87`, full replacement text given there).
- **R-04 (minor).** AC-004 says "trigger or triggers" but AC-005/VAL-002 say "the trigger." Fix, AC-005 last sentence → *"The activation trigger or triggers for each room together call EncounterAdmissionController.RequestAdmission exactly once per floor run with that room's configured prefab instances."* VAL-002 → replace "the trigger cannot submit a second request" with *"that room's triggers cannot submit a second request during that run."* (`OUTPUT.md:89-92`)
- **R-05 (minor).** VAL-002 checks `EnemyHealth.activeEnemyRegistry`, a private field with no getter (confirmed: `EnemyHealth.cs:9`, no public accessor). Fix, VAL-002 → *"and defeating each production enemy through EnemyHealth.TakeDamage removes it from that ActiveEnemyRegistry."* AC-005, append → *"Any other registry reference exposed by the delivered NSC-015 and NSC-055 prefabs is wired to the same ActiveEnemyRegistry."* (`OUTPUT.md:94-97`)
- **R-06 (minor).** VAL-001's durability check is circular (comparing the scene against the same table the builder read from it proves nothing) and its "preserve clearance minimums" clause would invent a placement ban. Fix, first clause → *"do not overlap non-floor gameplay colliders or any D1-D5 door opening, and lie inside the Vincent-approved region boundaries recorded for that room. Verify each trigger is inside its own room and, for Bone Archive through Final Room, does not overlap the opening of the door through which the wizard enters that room."* Durability clause → *"Compare every applicable D1-D5 DoorInteractable.MaxDurability value in the committed scene with the literal Vincent-approved values recorded in the durability child's contract, including the approved D5 inclusion or exemption."* (`OUTPUT.md:99-109`)
- **R-07 (minor).** AC-007 misquotes the GDD on Lower Vault — GDD:117/391 say "several incomplete loops," not "both incomplete routes." Fix → *"Lower Vault keeps its several incomplete loops and the D3 doorway, through which surviving pursuers break in, spatially relevant."* (`OUTPUT.md:111-112`)
- **R-08 (minor).** The 5th `gdd_evidence` entry reads as if cover doesn't block Ranged shots; GDD:116 says it does. Fix → *"Movement and Frost Field stretch Melee pursuit, Fireball converts separation into damage, Force Wave creates short-range emergency space, pews and columns block Ranged Enemy projectiles without clearing the enemy's target, and target loss remains distance-based with last-known-position search."* (`OUTPUT.md:114-116`)
- **R-09 (minor).** Notes call NSC-015 and NSC-055 "feature-level"; both are `kind: implementation` (confirmed directly: both files' `"kind": "implementation"`). Fix → *"NSC-015 is not yet decomposed; future children should depend on its delivered Melee Enemy prefab child once that child ID exists, and on NSC-055 for the assembled Ranged Enemy prefab."* (`OUTPUT.md:118-120`)
- **R-10 (minor).** INT-005 lists NSC-049/050/033 exclusive resources but omits **NSC-089**, which also locks `DoorPrototypeSceneBuilder.cs`/`DoorPrototype.unity` (confirmed: `Tasks/NSC-089.yaml` exists, `kind: implementation`, title "DoorPrototype NavMesh Surface and Enemy Agent Configuration"). Fix, INT-005 `reference` → add NSC-089; `requirement` last sentence → *"These children run after NSC-049, NSC-050, and NSC-089 and may not overlap NSC-033's shared builder/scene mutation."* (`OUTPUT.md:122-125`)

---

## 3. Round-03 final contract, in short (`03-codex-refine/OUTPUT.md:169-399`)

**Title:** *Room Enemy Encounters: Spawn Regions, Activation Triggers, and Door Durability Values* (renamed from *Dungeon Encounter Placement and Composition Authoring* per `UNITY_PROGRAMMER_LANGUAGE.md`).

**depends_on:** `NSC-028, NSC-050, NSC-015, NSC-055` (unchanged) **+** `NSC-049, NSC-007, NSC-008, NSC-009, NSC-071, NSC-072, NSC-017, NSC-089` (added). All 12 verified directly: every ID exists in `Tasks/`, every one is `kind: implementation`, `contract_disposition: active` — no feature-to-feature edge risk (`OUTPUT.md:263-276`; independently re-verified in this research, all 12 files present and `active`).

**exclusive_resources:** `[]` — correct for a feature node; no file is claimed at this level. Nine child responsibilities are named instead (below).

**Acceptance criteria** (one line each):
- **AC-001** — Melee-before-Ranged listed order in every mixed request, so FIFO partial admission can't activate an isolated Ranged Enemy.
- **AC-002** — 3–8 requested enemies per room; the separate 15-enemy floor cap stays `ActiveEnemyRegistry`'s job.
- **AC-003** — Ruined Entry/Bone Archive melee-only; Chapel first mixed; Final Room mixed; Lower Vault composition is a Vincent value.
- **AC-004** — each room records its approved trigger(s) and spawn/reset region inside its own accepted walkable geometry; no room-owned bounds/obstacles/routes/catalog edits.
- **AC-005** — the `No Safe Circle/Build Door Prototype Scene` command materializes exactly one `ActiveEnemyRegistry` + one `EncounterAdmissionController` in `DoorPrototype.unity`, wired through `Initialize`; each room's trigger calls `RequestAdmission` once per floor run.
- **AC-006** — **design hold in contract text** (R-02 target): Vincent must pick FIFO-delay vs. reduce/cancel-on-exit before this is assertable.
- **AC-007** — encounter placement must preserve each room's documented tactical purpose (circling in Ruined Entry, lane control in Bone Archive, aisle/cover tradeoff in Chapel, rear-pursuer relevance in Lower Vault, pressured D5 window in Final Room).
- **AC-008** — after Vincent approves a D1–D5 value table, `DoorSequenceBuilder.cs` becomes its source of truth; encounter work never touches `DoorInteractable`'s durability/damage/break logic directly.
- **AC-009** — each encounter activation component exposes its own reset method (fired/requested state only) and hands its enemies' authored regions to `EnemyPursuitMovement.ResetPursuit()`; NSC-030 doesn't edit the shared restart orchestrator (rewritten by R-03).

**Completion gates** (one line each):
- **VAL-001** — committed-scene conformance: 5 rooms, 3–8 count, Melee-before-Ranged, roster rules, valid prefab refs, spawn regions on NSC-089's NavMesh and off gameplay colliders/door openings, D1–D5 durability vs. the approved table (R-06 rewrites the durability/region clauses).
- **VAL-002** — Play Mode: one registry + one initialized controller; each room's real trigger submits its exact configured instances; cap never exceeded; no duplicate request (R-04/R-05 tighten wording).
- **VAL-003** — Play Mode Chapel cap test: fill registry to 14, fire Chapel's trigger, verify the first admission is Melee — **has no expected outcome for the remainder until AC-006 is settled.**
- **VAL-004** — Play Mode Lower Vault rear-breach test: real earlier-encounter survivors + a real D3 break via NSC-017 + the Lower Vault trigger firing together — **same AC-006 gap.**
- **VAL-005** — **R-01 target:** Chapel `Physics.Linecast` from Ranged spawn points to CA-W/CA-E, gated on an approval that doesn't exist; delete or convert to the approved rule.
- **VAL-006** — Play Mode: encounter component's reset method + registry/admission reset restore one-fresh-request-per-floor-run capability (rewritten by R-03).
- **VAL-007** — Vincent's human Play Mode gate: plays all five rooms with the full kit, records multi-shot camera evidence per room, explicitly judges whether 3 Melee Enemies still teach circling in Ruined Entry and whether accepted room sizes make kiting/target-loss too easy.

**Downstream integration obligations:** INT-001 restart handoff (rewritten by R-03 to route through NSC-033, not NSC-092) · INT-002 NSC-049 must re-validate encounter placement whenever a room task changes bounds/obstacles/door center · INT-003 NSC-079–084 visual dressing must not invalidate triggers/regions/cover · INT-004 maps VAL-002/VAL-004 evidence onto NSC-028's own INT-002/INT-003 closure · INT-005 sequences every encounter/durability child's builder-and-scene lock against NSC-049/050/033 (R-10 adds NSC-089).

**Proposed D1B.2 split, 9 responsibilities, no child IDs yet** (`OUTPUT.md:385-399`):
1. Shared production encounter data + committed-content validator — **can start now**, before placement values.
2–6. Per-room encounter authoring (Ruined Entry, Bone Archive, Chapel, Lower Vault, Final Room) — **held on decisions 15/16** (+17 for Chapel, +19 for Final Room) **and on each room's *accepted* geometry** (see section 4 — "accepted" ≠ "built").
7. Canonical-scene registry/admission/trigger/prefab/region materialization — **held on decision 13** (the retry path specifically).
8. `DoorSequenceBuilder` durability table + materialization — **held on decision 18.**
9. Production Play Mode + human validation — **after NSC-015/055/017 are delivered.**

Integrated restart stays **outside** NSC-030 (an NSC-033/NSC-092 obligation, per R-03).

**Facts now stale on main** (see section 4 for full detail): the GDD's own room/door coordinate table (`Docs/GDD/No_Safe_Circle_GDD.md:227-235`) is the pre-2026-09-14 baseline and was never edited by any room task; four of the five room contracts committed 2026-09-15 (NSC-045/046/047/048) have **not** been implemented in Unity yet — `RoomSceneCatalog.cs` and every layout script except Ruined Entry's still hold the old numbers; and `Assets/Scenes/DoorPrototype.unity`'s actual enemy roster (9 fixed enemies from a task-less commit) was never in the packet's scope at all.

---

## 4. Conflicts with main now

### Room geometry — approved but not yet built for 4 of 5 rooms

The packet's snapshot (`38904af1`, 2026-09-14 06:50) predates even Ruined Entry's own widening. Since then:

| Room | `Tasks/NSC-0##.yaml` **approved** (2026-09-15) | `RoomSceneCatalog.cs` / layout script **actually on main** | Built? |
|---|---|---|---|
| Ruined Entry | X[-14,+14] Z[-26,0], D1 (0,0) — `NSC-044.yaml` rev 5 AC-001 | `RoomSceneCatalog.cs:108` **matches**; `RuinedEntryLayout.cs` mtime 09-14 07:27 | **Yes** |
| Bone Archive | X[-12,+12] Z[0,20], D2 (+6,20) — `NSC-045.yaml` rev 4 AC-001 | `RoomSceneCatalog.cs:112` = X[-10,+10]; `BoneArchiveLayout.cs:14` = same old bounds; mtime 09-13 16:46 | **No** |
| Chapel of Ash | X[-18,+18] Z[20,54], D3 (-8,54) — `NSC-046.yaml` rev 6 AC-001 | `RoomSceneCatalog.cs:116` = X[-12,+12] Z[20,42]; `ChapelOfAshLayout.cs:8-9` = ±12; mtime 09-13 16:46 | **No** |
| Lower Vault | X[-20,+20] Z[54,76], D3 (-8,54) D4 (+4,76) — `NSC-047.yaml` rev 4 AC-001 | `RoomSceneCatalog.cs:120` = X[-11,+11] Z[42,64]; `LowerVaultLayout.cs:8-11,20-21` = same, D3(-6,42) D4(4,64); mtime 09-13 16:46 | **No** |
| Final Room | X[-15,+15] Z[76,104], D4 (+4,76) D5 (0,104) — `NSC-048.yaml` rev 4 AC-001 | `RoomSceneCatalog.cs:124` = X[-12,+12] Z[64,86]; `FinalRoomLayout.cs:8-15` = same, D4(4,64) D5(0,86); mtime 09-13 16:46 | **No** |

All five `NSC-04x` contracts show `recheck_recommendation: commit_contract` — the *design* is accepted, sitting one dispatch away from a worker actually rewriting `RoomSceneCatalog.cs`, the four layout scripts, and the four `.unity` scenes (their catalog edits are also contractually batched together per GER room decision 4, so none of the four can land alone). Until that lands, `GDD:227-235`'s own stale table and the current catalog agree with each other and with the *original* NSC-030 packet — the packet's geometry assumptions for Bone Archive, Chapel, Lower Vault and Final Room are **still literally correct against main today**, even though they're already known to be superseded on paper.

**Consequence for NSC-030's own decomposition plan (section 3, split items 2–6):** "held for its accepted room revision" must mean *materialized in `Assets/Scenes/Rooms/*.unity` and `RoomSceneCatalog.asset`*, not merely *contract-committed*, because VAL-001/VAL-004 open the committed scene and load content through the production catalog path — there is nothing yet to place a Chapel or Lower Vault trigger against. Recommend making this explicit rather than leaving "accepted" ambiguous (see decision 20 below).

### Playable-build enemy placement — will conflict once the rooms above are rebuilt

`DoorPrototypeGlobalSceneBuilder.BuildChaseEnemies` (`DoorPrototypeGlobalSceneBuilder.cs:373-386`) unconditionally spawns **5 `MeleeEnemy`** (`EnemySpawnPositions`, `:345-352`) and **4 `FireCasterEnemy`** (`EnemyCasterSpawnPositions`, `:365-371`) into the canonical scene at scene-build time — always active, no trigger, no admission request. `EnemyHealth` is added at `:419` with **no call to `Initialize(registry)`**, and no `ActiveEnemyRegistry`/`EncounterAdmissionController` exists anywhere in the canonical scene (confirmed: only `RoomSceneComposer.cs:37-38`'s *disallow* list mentions those two types). This is a parallel, task-less demo path — `Tasks/NSC-077.yaml` notes call it out explicitly: *"On main the scene enemies come from the playable-build commit 9a3d22c56, which has no task"* (`NSC-077.yaml`, notes). It has nothing to do with NSC-030's Registry/Admission system today.

The spawn coordinates are hand-computed against the **old** room table — the code comment says so literally: *"LowerVault Z[42,64], FinalRoom Z[64,86]; doors D1(0,0) D2(6,20) D3(-6,42) D4(4,64) D5(0,86)"* (`DoorPrototypeGlobalSceneBuilder.cs:343-344`), which is exactly today's still-current catalog. So there is **no placement bug today**. But once Bone Archive/Chapel/Lower Vault/Final Room are rebuilt to the approved 2026-09-15 table, several of these fixed positions land in the *wrong* room, because Lower Vault and Final Room both shift +12 in Z and Chapel grows to absorb it:
- `(-7, 0, 53)` — authored as "LowerVault mid-room" — falls inside the **new Chapel's** D3 staging rectangle, X[-10.5,-5.5] Z[48.75,53.75] (`ChapelOfAshLayout` per `NSC-046.yaml` AC-001), not Lower Vault (which will start at Z 54).
- `(8, 0, 74)` and `(0, 0, 70)` — authored as "FinalRoom" positions — fall inside the **new Lower Vault** (Z[54,76]), not Final Room (which will start at Z 76).

`NSC-077.yaml` rev 3 (**committed, not yet implemented** — confirmed no `LanternWraith`/`EnemyLanternWispCaster` file or reference exists anywhere under `Assets/`) claims exclusive write on this exact file (`NSC-077.yaml` `exclusive_resources`) but its AC-001 explicitly preserves *"spawn positions, counts, components and all gameplay tuning"* — it will not fix this drift. **Whichever task actually re-catalogs the four rooms, or a dedicated NSC-030 child, needs an explicit obligation to reposition or retire these 9 enemies** — otherwise the first real Unity rebuild after the room revisions land silently moves guard enemies into the wrong room. Recommend folding this into NSC-049's INT-001/INT-002 (it already owns reconciling composed-scene content on every room-bound change) or into decision 20 below.

### Lantern Wraith naming — approved rename, unimplemented

`Tasks/NSC-077.yaml` revision 3 (Vincent-approved 2026-09-16) will rename the scene's `FireCasterEnemy` → `LanternWraith` and `EnemyFireballCaster.cs` → `EnemyLanternWispCaster.cs` (keeping the script GUID), with a teal lantern-wisp projectile replacing the orange fireball look — **no gameplay change**. Confirmed **not yet implemented**: no `LanternWraith`/`EnemyLanternWispCaster` file exists; `DoorPrototypeGlobalSceneBuilder.cs:397` still instantiates a GameObject literally named `"FireCasterEnemy"` and adds `EnemyFireballCaster` at `:415`. Today, the GER packet's and current GDD's use of "Ranged Enemy" / "FireCasterEnemy" is accurate. Any NSC-030 child that writes test code against the concrete class name (rather than the `EnemyHealth`/registry-level abstraction) will need either to land after NSC-077, or to be written against `EnemyHealth`/`ActiveEnemyRegistry` only and stay silent on the concrete caster type name — recommend the latter, since none of NSC-030's own AC/VAL text currently names `FireCasterEnemy` or `EnemyFireballCaster` directly (it already only talks about "Ranged Enemy" generically), so no rewrite is actually needed there. Worth a one-line confirmation from the owner rather than a contract change.

---

## 5. Decisions the owner must make

Numbered to match `overnight.md` questions 13–19 (`overnight.md:250-265`), plus one new sequencing decision this research surfaced. Each has at most 3 options, a recommendation, and a one-line reason. For the value questions (15, 16, 18, 19), concrete starting numbers are given, sized to the **approved-but-unbuilt** 2026-09-15 room table (section 4), since that is what will actually exist once these children are dispatched.

**13. Pending enemies from rooms the wizard has left.** *Blocks AC-006/VAL-003/VAL-004.*
- (a) Keep delaying in strict FIFO request order (today's unmodified `EncounterAdmissionController.ProcessPendingAdmissions`, `EncounterAdmissionController.cs:115-166` — no code change).
- (b) Reduce/cancel a room's still-pending enemies when that room's exit door locks.
- (c) Hybrid: keep (a), but also retry `ProcessPendingAdmissions` specifically on every enemy defeat.
- **Recommended: (b), with retries also on defeat.** R-02's own evidence is concrete: under (a), a Chapel batch still pending when D3 locks activates behind a locked door in an *empty* room and permanently occupies registry slots the Final Room needs for its required mixed composition (GDD:118, AC-003) — a silent content-integrity bug, not a style choice. `DoorInteractable.Locked` (`DoorInteractable.cs:95`, fires exactly once) is a ready-made hook for the cancel; `EnemyHealth.Defeat` (`EnemyHealth.cs:43-49`) already unregisters from the registry, so hanging a `ProcessPendingAdmissions()` retry there is a one-line addition, not new architecture.

**14. Ranged support under the cap.** *Blocks AC-001's exact strength (framed inside R-02's discussion, not its own finding).*
- (a) Melee-before-Ranged *listed order* in the request is sufficient (today's committed AC-001 wording).
- (b) Every Ranged Enemy must wait until a Melee Enemy from its *own* encounter is currently active (registered), not merely listed first.
- **Recommended: (a).** `ProcessPendingAdmissions` (`EncounterAdmissionController.cs:124-163`) admits strictly in list order and stops the instant `RemainingCapacity <= 0` (`:140-145`) — under the current, unmodified code, Melee-first ordering *already* guarantees a Melee Enemy activates before any Ranged Enemy from the same batch. (b) needs a new "wait for an active ally" gate with no existing API to express it, for no behavior difference in the common case (3–8 enemies per room, 15-enemy cap) — added complexity without a documented failure mode it fixes.

**15. Rosters** (counts, Melee/Ranged split per room; Lower Vault's cap-pressure roster; does 3 Melee still teach circling in Ruined Entry). *Value question — concrete starting numbers, sized to the approved (not-yet-built) room table.*
- Ruined Entry (28×26, melee-only): **3 Melee.** Recommended over 4+ because the room only grew modestly from its 20×18 baseline (not toward the 3× ceiling), so the original "circle a melee enemy" read (GDD:114) most plausibly still holds at the AC-002 floor of 3 — this is exactly what VAL-007 already asks Vincent to confirm in Play Mode (`03-codex-refine/OUTPUT.md` VAL-007), so start at the minimum and let that human gate be the actual check.
- Bone Archive (24×20, melee-only): **4 Melee.** One more than Ruined Entry to match its lane/pinch teaching purpose (GDD:115), comfortably inside 3–8.
- Chapel of Ash (36×34, first mixed): **3 Melee + 2 Ranged (5 total).** Satisfies AC-001's Melee-before-Ranged ordering trivially; the much larger footprint (up from 24×22) supports a slightly richer roster than Bone Archive's across its two side routes plus the aisle.
- Lower Vault (40×22, mixed, the cap-pressure room): **2 Melee + 1 Ranged (3 total), deliberately lean.** With Ruined Entry + Bone Archive + Chapel worst-case un-defeated (3+4+5 = 12 active) plus Lower Vault's own 3, the registry sits at exactly 15 — so *any* surviving pursuer breaking through D3 immediately forces the pending-admission policy VAL-004 exists to test. A larger Lower Vault roster would blunt that test by leaving no headroom to observe the delay/reduce behavior at all.
- Final Room (30×28, mixed): **2 Melee + 2 Ranged (4 total).** Matches GDD:118's "both enemy types, full spell kit" requirement inside 3–8, while leaving cap room for whatever pursuers are still alive from earlier rooms.
- **Ruined Entry circling — recommend keeping 3, answer yes.** Same reasoning as above; treat it as the VAL-007 human check it already is rather than pre-deciding it in the contract.

**16. Triggers and regions** (how many per room, where; whether a region may sit in a door staging area). *Value question.*
- (a) **One activation trigger per room**, positioned at/inside each room's own already-approved entry-side landing rectangle; the spawn/reset region is that room's walkable interior minus its authored obstacle footprints and minus both staging rectangles.
- (b) Multiple sub-area triggers per room (e.g., separate Melee/Ranged activation zones).
- (c) No separate trigger — treat the spawn/reset region itself as the activation volume.
- **Recommended: (a), 1 trigger per room, reusing already-approved rectangles rather than inventing new geometry:** Bone Archive's D1 entry area X[-4,+4] Z[0.25,3.75] (`NSC-045.yaml` AC-002); Chapel's D2 landing X[3.5,8.5] Z[20.25,25.25] (`NSC-046.yaml` AC-001); Lower Vault's D3 apron X[-10.5,-5.5] Z[54.25,59.25] (`NSC-047.yaml` AC-002); Final Room needs a comparable new ~4×4 D4-side landing (none is published yet — flag for that room's next revision). Ruined Entry has no entry door, so its trigger should sit inside its own already-proven loop geometry, away from `PlayerStart` (`NSC-044.yaml` AC-001), so it fires only once the player commits toward the rubble. **Regions must not sit inside a door's *exit*-side staging rectangle** (R-06's fix already requires this — a trigger overlapping the door the wizard is *about* to five-second-hold would let the encounter fire mid-approach) but **may** sit inside the room's own *entry*-side landing, which is exactly what (a) uses.

**17. Chapel spawn-to-cover rule.** *Blocks VAL-005 (R-01).*
- (a) Round-03's rule as written: every Chapel Ranged spawn position must be blocked from **both** CA-W and CA-E.
- (b) Every Chapel Ranged spawn position must be blocked from **at least one** of CA-W or CA-E.
- (c) Reject the geometric gate entirely; rely only on Vincent's VAL-007 human judgment.
- **Recommended: (b).** This is verbatim what the GDD already requires at the room-geometry level — *"At least one of CA-W or CA-E must be geometrically occluded from a representative straight-line ranged attack"* (`Docs/GDD/No_Safe_Circle_GDD.md:379`) — and `NSC-046.yaml` rev 6 VAL-001 already proves exactly this with real ray casts against committed pew/column colliders. NSC-030 only needs to require that Chapel's Ranged *spawn positions* be chosen from where that already-approved occlusion applies; it isn't inventing a new, stricter dual-pocket rule, which is what made R-01 flag the current wording as unapproved design.

**18. Door durability** (D1–D4 values; D5 exempt or valued). *Value question. No per-hit enemy-door-damage constant is fixed anywhere on main yet (`NSC-017.yaml`'s `EnemyLockedDoorAttack` applies damage only through `DoorInteractable.TakeDamage(float)` with no named amount), so these are first-pass tuning values pending playtesting, consistent with GDD:532's own stance on tuning values.*
- **D1 = 60, D2 = 80, D3 = 100 (the current uniform default — confirmed `DoorInteractable.cs:48`, `maxDurability = 100f`), D4 = 120** — a gentle rising curve so later doors buy more time as the run gets harder, without needing a canonical damage-per-hit number yet.
- **D5 = exempt, no value.** GDD:98/443 make crossing D5 the victory condition that ends gameplay outright — no enemy ever gets to attack a "locked D5" the way it does D1–D4, so a value there is dead data. Both round-02 (F-04) and round-03/04 flagged this identically; treat it as settled rather than reopened.
- Confirmed on main: `DoorSequenceBuilder.ConfigureDoor` (`DoorSequenceBuilder.cs:49-63`) sets only `doorId`, `isFinalDoor`, and `position` — durability is untouched, so all five doors currently share the same default 100. `Tasks/NSC-050.yaml`'s own AC deliberately stops at *"Expose a serialized maximum-durability value... so level authoring can configure each door"* — it hands the values to NSC-030 on purpose.

**19. Final Room pressure** (as authored content, no waves/reinforcements). *Value question.*
- (a) The fixed roster from decision 15 (2 Melee + 2 Ranged) plus whatever persistent pursuers are still active/pending from Lower Vault's rear breach, arriving simultaneously in a comparatively open room (GDD:118) at the same moment the player must hold the D5 five-second attempt — no new mechanic.
- (b) Same as (a), plus tightening the D5 staging rectangle's exposure to FR-1 so the existing obstacle reads as less forgiving.
- (c) Candidate B from round-03's compared candidates — staged/waved reinforcements.
- **Recommended: (a).** GDD's required-scope table (line 556-558) and stretch-goal list (line 560) exclude anything wave-like from the base game, and round-03's own analysis of Candidate B says the GDD *"supplies no wave count, timing, trigger sequencing, or replacement rule"* — inventing one is exactly the "silently add new mechanics" the packet's own instructions forbid. The fixed mixed roster plus FR-1 (X[-3.5,+3.5] Z[87,94], `NSC-048.yaml` rev 4 AC-001) is the only `within_current_GDD` option on the table and is enough to create the "final uninterrupted five-second escape window" GDD:118/436 asks for.

**20 (new). Sequencing against the unbuilt rooms.** *Not one of 13–19 — surfaced by this research (section 4).*
- (a) Dispatch NSC-030's shared-data/validator child (D1B.2 split item 1) now, since it needs no room geometry, but hold every per-room child (items 2–6) until that room's `Assets/Scenes/Rooms/*.unity` and `RoomSceneCatalog.asset` actually reflect its 2026-09-15 numbers — not merely until the *contract* is committed.
- (b) Dispatch per-room children now, against the approved-but-unbuilt numbers, and let them race the room-rebuild work.
- **Recommended: (a).** VAL-001/VAL-004 explicitly open the *committed* scene and load content through the production catalog path (`03-codex-refine/OUTPUT.md` VAL-001/VAL-004) — there is nothing for a Chapel or Lower Vault encounter child to test against until those scenes exist at the new bounds. (b) risks a child writing real region/trigger coordinates against geometry that then shifts out from under it when the room task finally lands. Recommend also assigning someone the small fix in section 4 ("Playable-build enemy placement") — reposition or retire `BuildChaseEnemies`' 9 fixed enemies — as part of whichever task next rebuilds the canonical scene from the new catalog, most naturally NSC-049's own INT-001/INT-002.
