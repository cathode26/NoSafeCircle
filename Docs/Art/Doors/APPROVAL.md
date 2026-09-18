# Door art: Vincent's approval, and the state-to-code bind list

**Target path in the repo: `Docs/Art/Doors/APPROVAL.md`** (a new file - see "Why not inventory.json" below).
Prepared by the Art Director Agent, 2026-09-17. Lands through the Documentation Agent; I do not commit to main.

## The approval

**Vincent, 2026-09-17: "door art approved."**

- **What was approved:** the seven committed NSC-065 bonestone door sprites, family B
  (`selected_family: "family_b_bone_and_stone"`), at
  `Assets/NoSafeCircle/DoorPrototype/Art/Doors/Source/door_bonestone_<state>_S_000.png`.
- **What he saw:** the Art Director's audit sheet `door_states_2x.png` - all seven states at 2x native pixels
  with each sprite's measured ground line drawn on it, plus the measurements in
  `C:\nscrev\reports\art-director\door-art-audit-20260917\AUDIT.md`.
- **What this closes:** `Docs/Art/Doors/inventory.json` records `"human_visual_approval": false` with
  `"assistant_selection_authority": "operator-authorized unattended continuation"` - an assistant picked family B
  over family A unattended. **That pick is now Vincent's own.** The NSC-065 delivery record
  (`DEL-NSC-065-03affab6b822`) always intended this: its `human_approval` block says `"decision":
  "not_required"` because "Vincent in-game readability decision is deferred to downstream Unity integration".
  This file is that deferred decision.

## Why not edited into inventory.json

**Because NSC-065's delivery record pins that file's blob.** `DEL-NSC-065-03affab6b822.json` lists
`Docs/Art/Doors/inventory.json` as a conformance surface at blob `9120473efc69113990002ab4cae8f8222fd48ca3`,
which is exactly the file's current blob on `main`. Editing it in place would silently invalidate the recorded
evidence of a closed task - the same failure class as a stale contract-hash pin. `inventory.md` is pinned too
(`8444cc83...`). **Both stay untouched;** the approval lives here, where nothing pins it, and points back at them.

## Bind list: which sprites the code can actually express today

`DoorPassabilityState` (in `Scripts/World/DoorEnemyPassability.cs`) is **Sealed, Open, Locked, Broken**, and
`DoorInteractable` carries `isFinalDoor` as a *flag*, not a state. Against that:

| Sprite | Bind now? | Maps to |
|---|---|---|
| `sealed` | **yes** | `DoorPassabilityState.Sealed` - the name already matches |
| `locked` | **yes** | `DoorPassabilityState.Locked` |
| `open` | **yes** | `DoorPassabilityState.Open` |
| `final` | **yes, conditional** | not a state: use it for a **closed** door (sealed or locked) when `isFinalDoor` is true. An *open* final door uses the `open` sprite - the `final` art is a closed leaf with a gold glow, so it cannot stand in for an open passage |
| `broken` | **ready, not shown in this pass** | it maps cleanly to the existing `DoorPassabilityState.Broken`, so no art work is needed when breaking is enabled. Vincent: "A broken door occurs later, dont use it now. YEs an enemy can come through a broken door, they broke it." **When it does arrive, the painted hole is a genuine opening that collision must honour rather than seal** |
| `opening` | **optional, no new state needed** | a single transition frame held for about 0.1 s between `Sealed` and `Open`. It is one frame, not a loop, so it buys a two-step swing instead of a hard cut. Bind it only if the Game Agent wants that; nothing breaks without it |
| `damaged` | **waits for code** | it is the look of a **locked door that has taken damage but is not broken yet**. `DoorInteractable` already accumulates damage against a locked door on the way to `Broken`, so this needs only a threshold to switch the sprite - it is not orphan art, and it gives the player feedback that hitting the door is working |

**So: three states bind unconditionally, `final` binds as a flag-conditional look, and three sprites wait -
`broken` on gameplay, `opening` on a design choice, `damaged` on a damage threshold.**

## Two decisions already taken, recorded here so nobody re-opens them

- **The painted lavender floor disc stays for now.** Every state paints a ground patch under the threshold, which
  is the Tilemap's job and is what "art must not out-promise the geometry" names. The Game Agent's point stands:
  NSC-064 is about to replace the floor with the isometric kit at `orthographicSize` 7.9551, so a masking pass
  (about 74 metered for seven states) would be paid against art that is being replaced and re-judged anyway.
  **Decide once, after the new floor lands.**
- **The doorway is small for the characters.** Measured by differencing the `sealed` and `open` sprites, the
  opening is **1.00 x 1.30 world units**, and the merged wizard stands **1.64 units** tall. Either bind the door
  sprite at about **x1.54** (opening 2.0 units, arch about 3 units - plausible for a vault gate, zero generations)
  or re-author with more passage and less arch. **Vincent's call; put to him 2026-09-17.**

## Still not generated

**Non-south facings.** Only direction S exists. Mirroring would serve E and W geometrically but flips the
upper-left key light the whole family shares, so other facings are a generation request with their own cap when a
room needs one.
