# Handoff — GER Agent, 2026-09-18

Written by the GER Agent at 63% context. **Self-contained: a successor should need only this file, `CLAUDE.md`, the memory index and `nsc-agent-directory.md`.** Longer history is in `C:\NSC\agent-state\ger-agent.md` (read it bottom-up; later sections supersede earlier ones). Full job corpus: `C:\nscrev\reports\ger-agent-job-corpus.md`.

> **READ `C:\NSC\agent-state\ger-agent-todo.md` FIRST — it is the authority for what is next.**
> This file is frozen as of 2026-09-18 and its queue (sections 2, 3 and 10) is already out of date.
> Known stale here, corrected in the todo file and verified at main `255951482`:
> "Nothing pushed" (`origin/main` equals main, pushed via PR #134); the 35 line-ending churn files
> (gone, working tree clean); and section 3 item 1, the sorting-layer task — **`WorldSprites`
> already exists** as an orphan layer, so do not contract it as written. See
> `C:\nscrev\reports\ger-orchestrator\sorting-layer-task-rescope-20260918.md`.
> The role, the hard rules, and sections 4-9 and 11-13 (scar tissue, counted groups, what a handoff
> cannot carry) are still good — those are why this file exists.

---

## 1. The role

Task contracts. Design revisions, new task contracts, validation-policy entries, GER holds and releases, committing contract revisions to **local main**, handing oversized tasks to the Decomposition Agent, reporting concisely to Vincent.

**Hard rules, no exceptions:**
- **Never push.** Never run crews, never apply a decomposition, never delete an `NSC-###` branch.
- **Re-check HEAD and a clean tree for your paths before each commit**, via the main-write protocol.
- Artifacts stay outside the repo. GER is full-cycle, not review-only.
- Vincent's canonical checkout carries 35 line-ending churn files — **never stage, revert or commit them**.
- Art goes to the Art Director Agent. Out-of-lane work goes to its owner by session title.
- **A relayed go is not Vincent's go** for merges or pushes, and a go given in your chat does not authorise another agent acting in theirs.

## 2. State at handoff

- **Local main `255951482`. Nothing pushed.**
- **NSC-007 decomposition plan approved by Vincent** ("approve 007"): `decomp-nsc007-20260918e`, GDP-737cfe15b2, children **NSC-100/101/102**, authored against rev 8. The Decomposition Agent applies it.
- **NSC-097 rev 3 is ready to re-dispatch** — the Game Agent has it, it holds no reservation.
- **NSC-015's old plan `decomp-nsc015-20260917d` MUST NOT be applied** — pinned at `ca9060cda`, invalidated by my own revisions 12/13/14. Needs a fresh run.
- My queue is empty. Nothing drafted-and-unlanded.

**Landed 2026-09-18, all local main:** NSC-097 rev 1 `c41f35bbb` / 2 `62a2897cd` / 3 `cb91d32a7`; NSC-098 rev 1 `2c509103a` / 2 `878c835e2` / 3 `d047525ce`; NSC-099 rev 1 `3cbea24bd` / 2 `e595cc162`; NSC-015 rev 12 `3474291ac` / 13 `9f580c58c` / 14 `448b74927`; NSC-007 rev 6 `7fb260eb8` / 7 `ff291624f` / 8 `255951482`; NSC-078 rev 6 `6eb84d822`; NSC-082 rev 4 `6c1c07217`; **11 validation-policy entries** (089 `497f0d662`, 091 `8b0f82933`, 017 `c95b72daa`, 053 `009d5d5c3`, 090 `293253965`, 092 `21a4cf5e5`, 052 `ca9060cda`, 032 `636c860f5`, 050 `4c79f8695`, 051 `47bf4e358`, 067 `40e489b98`).

## 3. Approved by Vincent, never contracted — do these first

1. **Sorting-layer task.** He said "Yes". The project defines exactly one sorting layer (`Default`), so the room composer's check that every renderer uses the shared layer **can never fail**, and nothing validates draw **order** at all — a sprite authored at order 50 draws over everything and passes every gate. **NSC-069's INT-002 hands its sorting proof to this task, which does not exist.** Needs a `WorldSprites` layer, `WorldSpriteSortingLayerName` repointed, order validated; touches ProjectSettings and every builder-authored renderer, so its own contract and a Unity pass.
2. **Room-catalog parallelism split.** He said "yes fix it so they can run in paralell". NSC-044..048 all contend on `RoomSceneCatalog.cs` and its generated `.asset`, and three edit their own bounds literal inside the shared `CreateCanonicalRooms`, so they run one at a time. Design settled, never written: per-room bounds data, the catalog asset rebuilt by one owner, then five mechanical revisions dropping the shared claims.

**Also open:** NSC-097 VAL-002 is ambiguous — it says "in the same Edit Mode fixture" then pivots to Play-Mode assertions without naming a file, and says "a projectile crosses" when **no `Fireball` class exists at HEAD** and NSC-097 `depends_on` is `[]`. Name `DoorwayTraversalPlayModeTests.cs` and state that "projectile" means the raycast query AC-001 uses.

## 4. Scar tissue — clauses that look arbitrary and must NOT be removed

A stranger can reconstruct a rule but never the incident behind it. Each of these was written to stop a future reader "fixing" something:

- **NSC-099 AC-004:** `death_brute_decapitated_a` keeps a wound spiral at the collar. **Vincent chose it with the sprite in front of him**, so that read is inside the approved family. Nobody may remove or repaint it citing the stylised-not-gore direction.
- **NSC-097 AC-002:** `DoorInteractable.cs` is not writable by that task. Seven tasks claim it; a blocked crew run proved the new-component route works instead because `Complete()` deactivates the visual *before* raising `Opened`.
- **NSC-097 AC-002:** the binder may change GameObject activity and the sprite **only, never collider state** — `doorVisual` and `doorwayBlocker` are the **same GameObject**, so re-enabling the visual re-activates the collider's object. This one is *preventive*, not scar tissue: reasoned forward from verified Unity semantics, no incident yet. Both must stay; only one has a scar.
- **NSC-015 AC-006:** the no-repeat rule is at **variant** level deliberately. At look level it would break "one shot means decapitated" for the second of two consecutive one-shot kills — while passing every reachability gate.
- **NSC-098:** `reconciliation_key` reads `fireball-second-mint` and **cannot be changed** (invariant across revisions). It describes the id's history, not the contract. Do not "correct" it; do not mint a replacement to get a nicer key.

## 5. Deliberately unfixed — do not pin these to make a gate crisp

- **NSC-098's heavy-blow threshold** and **NSC-099's rarity weights** are Vincent's to tune at the VAL gate. Pinning a number inverts his rule: a low threshold makes `blasted` the normal one-shot death instead of `decapitated`.
- Thresholds are expressed **relative to max health**, never as absolute damage — an absolute value goes stale *silently* on a rebalance.

## 6. Threads a successor would re-decide differently

- **Walkable elevation** ("it would be great if you could get on the ledge!") = a new cross-room mechanic task **plus** an NSC-047 revision committing real geometry, sequenced **with** NSC-064, not after — the collision-versus-camera-plane guard is the same guard, so doing them apart builds it twice.
- **Corpse persistence** = stay for the level, his call, taken with the clutter consequence stated. Not an oversight; don't propose a fade.
- **Spell VFX** = one task per spell. NSC-098 INT-001 tells Frost Field and Force Wave to reuse the pattern rather than merging into one task.
- **Death looks are enemies only.** The wizard has **no death art at all**, not one frame. A future batch if he ever wants it.
- **NSC-007 AC-007 bundles five obligations.** Not what broke the four decompositions (rev 8 was). May still trip a child. Don't chase, don't forget.

## 7. Rules that cost real runs

- **Verify every handed-over diagnosis with `git show` before revising.** Three times on 2026-09-18 a confident cross-session diagnosis would have had me revise a correct contract.
- **A machine-readable field and the prose describing it must change in the same revision.** NSC-007 rev 6 changed the prose and left `execution_scope` at `single_agent`; `decomposition.py:571-574` gates on `active` **and** `needs_execution_decomposition` **and** `concrete` together — **`concrete` is REQUIRED, not stale.**
- **A decomposable contract needs roughly one test file per anticipated child.** Four NSC-007 rejections across two models, one constant: the resource list.
- **A `review_ready` plan goes stale the moment its task is revised**, silently. Check `apply_source_commit` before applying; check for a waiting plan before revising.
- **The house defect shape is "a gate that passes while the rule is wrong."** Five of today's contract defects were that. Ask of every criterion: *could this pass while being wrong?*
- **Never write an optional criterion, and never a gate the code cannot reach.**
- Pin/hold: "main is free" and "main is free as you launch" are different claims; a run in flight **cannot** be re-pinned.

## 8. Tools

- `C:\nscrev\ger-contract-revisions-20260916\verify_filter.py` — **run before binding any policy filter.** Proves the type exists by content grep, counts its tests, checks platform, checks file-stem resolution, and knows a fixture authored by the task or a dependency legitimately does not exist yet. Clean across the graph except NSC-069 (partial class, no matching file stem, needs a scope override).
- **Committers:** `C:\nscrev\ger-tools\contract_commit.py` for revisions (`--policy-filters-file` is flat `{platform: filter}`); `new_task_commit.py` for new tasks (`{task: {platform: filter}}`); `policy_entry_commit.py` for a policy entry with no contract change. Any note saying "use runbook_contract_commit.py until parity lands" is superseded — contract_commit.py landed every revision today.
- **MAIN-WRITE is code, not convention:** `C:\nscrev\ger-tools\main_write.py` — `default_journal`, `start`, `end`. The committers call it; you never hand-write markers.

## 9. What no handoff can carry

**A large share of this role's work arrives as fragments in other people's threads.** Sampled systematically from the corpus: *"Or in the GER agent documentation?"*, *"Did I agree to that?"*, *"So I need to look at branches for Evidence passes for the five?"*, *"I thought some agents wanted a, can you ask them why?"* — none of which mean anything without the turn before them.

Several of Vincent's decisions today reached me **via the Art Director or the Documentation Agent**, not directly. So: **check with the owning agent before re-asking him**, and expect that some threads are resumable rather than transferable.

## 10. Open for Vincent

- Sequencing for walkable elevation against NSC-064.
- Whether the melee walk-toward-and-away is accepted until NSC-015's child runs.
- The doorway-size remedy if the ×1.54 sprite binding proves wrong in play.

**Settled today, do not re-ask:** all twelve death sprites, the kill-history rule, enemies-only, corpses persist for the level, stylised-violent, door art approved, projection (b), NSC-064 before the rooms, and **two Codex Pro accounts — one resets 09-19, the other 09-22 18:55**.

---

## 11. Key paths — full, because bare filenames stalled a successor

```
C:\NSC\agent-state\ger-agent.md                                   long history, read bottom-up
C:\nscrev\reports\ger-orchestrator\vincent-decisions-20260917.md  THE decisions ledger: numbered items 1-14
                                                                  with APPROVED/CONFIRMED annotations + item 7's
                                                                  four melee answers. Cited by bare filename
                                                                  everywhere else; this is where it lives.
C:\nscrev\reports\ger-agent-job-corpus.md                         every request this role received, numbered
C:\nscrev\reports\agent-recovery\ger-agent-20260918-0358-76312bfd.md   session digest (Vincent's side + peers')
C:\nscrev\ger-contract-revisions-20260916\                        all revision patch scripts + verify_filter.py
C:\nscrev\ger-tools\                                              contract_commit.py, main_write.py
C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md   MAIN-WRITE journal
C:\NSC\NSC\NoSafeCircle                                           the canonical checkout (read via git show)
```

## 12. Counted groups — the literal membership, because the count does not survive

Vincent's shorthand is operationally load-bearing and the number alone is useless later. A successor testing this handoff was blocked on exactly this.

- **"the five"** (evidence passes / NSC-075's blocked dependencies) = **NSC-062, NSC-068, NSC-070, NSC-073, NSC-074**. All were `not_delivered` while the wizard work was merged and visibly in the game.
- **"all twelve"** (death looks) = `death_brute_{blasted,burned,decapitated_a,decapitated_b,dismembered_a,dismembered_b}` + `death_wraith_{dissipated,draining,hollowed,shattered,snuffed,unravelled}`.
- **"the eight"** (Art Director's recommended death looks, superseded by "all twelve") = the four brute and four wraith looks, one per kind.
- **"the seven"** (tasks claiming `DoorInteractable.cs`) = NSC-019, NSC-020, NSC-041, NSC-049, NSC-050, NSC-051, NSC-052.
- **"the eleven"** (tasks claiming `DoorPrototypeGlobalSceneBuilder.cs`) = NSC-007, 008, 009, 039, 049, 066, 069, 075, 077, 088, 096.
- **"the three children"** (NSC-007 decomposition, approved) = **NSC-100, NSC-101, NSC-102**.

**Rule for the successor: the moment Vincent agrees a counted group, write the explicit list beside the count.**

## 13. What this handoff structurally cannot carry

A read-only successor was given this file and eight real requests sampled mechanically from the corpus. Result: **1 actionable, 5 actionable-only-with-an-assumption, 2 impossible.** It counted **24 of 78 (31%)** of Vincent's messages as unintelligible in isolation — replies like *"Yes 64 and b"*, *"or death looks I mean."*, *"I want them both"*.

**The unfixable part:** the session digest records Vincent's messages and other agents' messages but **never this agent's own turns**, so any message that replies to something *I* said is unrecoverable. Vincent's very first message of the session (*"Or in the GER agent documentation?"*) is permanently unanswerable for that reason.

**Two mitigations a successor should adopt from the start:**
1. Keep a rolling verbatim tail of the last few exchanges — **both sides** — in the state file, refreshed at each checkpoint. Vincent's side alone is not enough.
2. When Vincent polls several agents on one decision, keep an **agent → stance → reason → quote** table. "Some agents wanted (a)" was unanswerable because no such table existed, and the reasoning lived only in cross-session messages the digest discarded.

**And log live yes/no answers where the thing they answer lives.** The decisions ledger does this well inside its own table and nowhere else: Vincent's answer to "wait for the fix, or merge anyway?" on the GER-hold bug was never recorded anywhere, so the bug's status is known and his instruction about it is lost.
