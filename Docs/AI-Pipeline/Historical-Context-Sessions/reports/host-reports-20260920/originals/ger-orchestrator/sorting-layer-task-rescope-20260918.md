# Sorting-layer task — re-scope from measured HEAD, 2026-09-18

GER Agent. All claims below verified at main `255951482` with `git show` / `git grep`, not carried
from the handoff. **Three of the handoff's premises for this task are stale.** Do not contract the
task as the handoff describes it.

## What the handoff said, and what is actually true

| Handoff claim | Verified at HEAD | Verdict |
|---|---|---|
| "The project defines exactly one sorting layer (`Default`)" | `ProjectSettings/TagManager.asset` defines **two**: `Default` (id 0) and **`WorldSprites` (id 1043912875)** | **FALSE** |
| Task "needs a `WorldSprites` layer" | Already added by the Game Agent in `d688f8b12`, 2026-09-17 19:12:25 | **ALREADY DONE** |
| "nothing validates draw **order** at all" | `DoorPrototypeSceneBuilderTests.cs:792-798` compares floor/wall/architectural `sortingOrder`; `:1269`, `:1409` assert exact values | **TOO STRONG** |
| "NSC-069 INT-002 hands its sorting proof to this task, which does not exist" | Confirmed verbatim in `downstream_integration_obligations` | **TRUE** |

## The `WorldSprites` layer is an orphan

Defined in ProjectSettings and **referenced by nothing**. `WorldSpriteSortingLayerName` is still
`"Default"` (`DoorPrototypeSceneBuilder.cs:56`), and the only `.cs` hits for the string
`WorldSprites` are `WorldSpritePrefabAssetFolderName` — a **prefab asset folder name**, an unrelated
string coincidence, not the sorting layer.

Half-done is worse than either end state: a reader checking TagManager concludes the sorting work
landed. It has not. The composer check at `RoomSceneComposer.cs:344,353` still compares against
`"Default"`, so every renderer still passes.

## A committed justification silently expired

NSC-069 **revision 8** dropped VAL-001's negative sorting case, citing a Game Agent Unity probe at
`7a1bae97a`: with only `Default` defined, "a renderer stays on Default however the layer name or id
is assigned, so `RoomSceneComposer.ValidateSortingConvention` is unreachable and any test claiming
to prove it could not fail."

**That premise is false at HEAD.** A second layer now exists, so a renderer *can* be moved off
`Default`, `ValidateSortingConvention` *is* reachable, and the negative test rev 8 removed as
impossible **is now writable**.

Timing, which matters and is not what it looks like:

- `d688f8b12` (layer) — 2026-09-17 **19:12:25**
- `70645a036` (NSC-069 rev 9) — 2026-09-17 **19:13:02**
- `git merge-base --is-ancestor d688f8b12 70645a036` → **NO**

So by wall clock the layer landed first, but it was **not in rev 9's history** — the two were
authored on divergent lines and only met on main. Rev 9's reasoning was true for the commit it was
written against and became false when the lines joined. Nothing warned either author. This is the
`trust-the-source-not-the-name` failure mode in its timing form: *true at the source commit, false
at HEAD.*

**Consequence:** NSC-069 needs a revision 10 recording that the unreachability argument has expired
and either restoring the negative case or stating why it still stays out. Queued behind the freeze.

## Resource reality — the task is contractable, but contends widely

- `ProjectSettings/TagManager.asset` is claimed by exactly one task: **NSC-069**.
- `DoorPrototypeSceneBuilder.cs` (home of the constant to repoint) is claimed by **29 tasks**,
  including NSC-039 *World-Space SpriteRenderer Prefab and Sorting Foundation* (rev 2, active).
  Contention is the norm here, not a blocker — canonical `exclusive_resources` are shared and
  serialize runs rather than forbidding the claim (see `exclusive-resources-semantics-differ-upstream`).

## The finding that changes sequencing

Repointing `WorldSpriteSortingLayerName` off `"Default"` **invalidates six committed contracts that
name the `Default` sorting layer literally**:

    NSC-044, NSC-045, NSC-046, NSC-047, NSC-048, NSC-069

NSC-047's AC is explicit: proxies "on the Default sorting layer with sortingOrder 0".

**NSC-044..048 are exactly the five room tasks in the other queued item, the room-catalog
parallelism split.** The two approved-but-uncontracted tasks therefore land on the same five
contracts. Revising them once, carrying both the per-room bounds data *and* the sorting repoint,
costs five revisions; doing them separately costs ten and leaves a window where a room contract
names a layer the constant no longer points at.

**Recommendation: sequence the sorting-layer task and the room-catalog split together, one revision
per room task.** This is the same argument already recorded for walkable elevation vs NSC-064 —
"the collision-versus-camera-plane guard is the same guard, so doing them apart builds it twice."

## Revised task shape (draft scope, not yet a contract)

1. **Not** "add a `WorldSprites` layer" — it exists. Instead: adopt it, or delete it and add the
   real one, so the graph stops carrying an orphan.
2. Repoint `DoorPrototypeSceneBuilder.WorldSpriteSortingLayerName` to `WorldSprites`.
3. Move every builder-authored renderer onto it.
4. Validate draw **order**, which today is asserted only at a few specific call sites — a sprite
   authored at order 50 still draws over everything and passes every gate.
5. Restore NSC-069's negative sorting case, now that it is writable (discharges INT-002).
6. Carry the six-contract cascade, folded into the room-catalog split revisions.

Needs its own contract and a Unity pass (ProjectSettings + every builder-authored renderer).
