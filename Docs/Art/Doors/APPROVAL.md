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
  **!!! SETTLED 2026-09-27 AND THE x1.54 IS SUPERSEDED. HE TOOK THE SECOND OPTION - RE-AUTHORED, NOT
  SCALED. THE APPROVED SCALE IS NOW x1.0. See "Flat-elevation redraw" at the end of this file; two
  test constants read this line, so do not cite the x1.54 from here. !!!**

## Still not generated

**Non-south facings.** Only direction S exists. Mirroring would serve E and W geometrically but flips the
upper-left key light the whole family shares, so other facings are a generation request with their own cap when a
room needs one.

## South-west facing, 2026-09-26 — a NEW generation, not the approved sprite rotated

**Why it exists.** Vincent, from a play screenshot: *"Door is pointing south and it should point
south west."* That is a defect he can see, and it is entirely an art problem.
`CreateDoorSpriteVisual` sets `localRotation = Quaternion.identity`, so the builder never rotates
the sprite; and `BuildWalls` places the flanking walls at `doorPosition ± (2.5, 1.25, 0)` with
`localScale (3, 2.5, 0.3)`, so the wall runs along X and is thin in Z. Its face normal is ±Z and
is seen obliquely under the scene's −45° yaw camera. **A front-facing sprite is wrong for this
wall by construction, and no builder change can fix it.**

**What it is, stated plainly so nobody mistakes it for a rotation of the approved art.** The
`_SW_` set is a NEW PixelLab generation in the family's style. It is **not** Vincent's approved
door re-angled, and that route is now permanently closed: the approved base's PixelLab job
(`99f204e7-c2e6-4b79-96bf-91f1aab741b9`) has **expired** — its hosted image returns HTTP 404 — so
those pixels can no longer be fed into any reference or edit tool. *Expired*, not merely *blocked*.

**Provenance.** 8-direction object `3795f8df-3527-4a5f-b2b6-b947ea0d2455` ("Bonestone Arch Door",
view `low top-down`, 40 generations; it returns 136×136 even when 128 is requested). The
south-west rotation was then finished with `edit_image_pixen`, **one edit at a time from a single
base and never chained** — the method that produced the approved family. Chaining was tried first
and failed measurably: each call repaints the whole sprite, so a later edit silently undid an
earlier one.

| file | source | seed | edit |
|---|---|---|---|
| `door_bonestone_sealed_SW_000.png` | the SW rotation | 20151 | remove an invented lantern; add a small pale-lavender threshold puddle and mossy rocks |
| `door_bonestone_locked_SW_000.png` | sealed base | 20403 | *"add a stylized bone crossbar latch…"* — the approved family's own prompt |
| `door_bonestone_open_SW_000.png` | sealed base | 20406 | *"door fully swung open…"* |
| `door_bonestone_final_SW_000.png` | sealed base | 20405 | *"add a warm golden rim light…"* |

**Canvas and registration.** Delivered at the builder's **128×128**, padded with transparent
pixels from 136×136 — **never rescaled**; opaque pixel counts are identical before and after
padding for all four. All four were cropped on **one union box** `(16,8,115,133)` and
bottom-aligned, so the door cannot jump between states. `spritePivot` is `{x: 0.492188, y: 0}`:
the puddle spreads left, so centring on the bounding box would put the door slab off its world
position; this places the slab where the approved `_S_` sprite places it. Importer settings are
otherwise cloned from the approved sprite — `textureType: 8`, PPU 64, `filterMode: 0`,
`alphaIsTransparency: 1` — with a fresh GUID per file.

**Acceptance.** The four states were gated as a set against the approved family: no neon
saturation in any state (0 px at S>0.85 ∧ V>0.60), the puddle **coherent across states**
(465 / 463 / 476 / 349, max/min 1.36) so it does not change when the door locks, and the maroon
door slab present in all four. **An absolute pixel-count target taken from the approved sprite
was tried first and discarded: that door is front-facing, so its threshold pool spreads toward the
camera, and a 3/4 facing foreshortens the same puddle into far fewer pixels. Coherence transfers
between facings; a raw count does not.**

**Honest differences from the approved art**, shown to Vincent with the images: the stone reads
greyer than the approved blue-violet slate, the puddle is smaller, and there are fewer moss rocks.

**What this does NOT change.** Nothing on screen. The builder's four filename constants at
`DoorPrototypeSceneBuilder.cs:1040-1043` still name the `_S_` files, and the `_S_` files are
untouched. Switching facings is a one-line change to those constants — **and it is Vincent's call,
because this is a new design rather than his approved sprite turned.** Note that those constants
sit under the `AC-002` comment binding them to this document's bind list, so the builder edit is
not cosmetic and may need an AC-002 revision alongside it.

**`Docs/Art/Doors/inventory.json` and `inventory.md` are pinned by NSC-065's delivery record**
(`9120473efc69113990002ab4cae8f8222fd48ca3` and `8444cc83e983cd8b025ba4105646bd9b24a73f84`,
both re-resolved on main and current) **and are deliberately not edited here.** This file is the
one that is not pinned, which is why the record goes in it.

## Flat-elevation redraw, 2026-09-27 - THE APPROVED ART SCALE IS x1.0, NOT x1.54

**This supersedes the `x1.54` in "Two decisions already taken" above.** That was a 2026-09-17 choice
between scaling the 128x128 sprite up or re-authoring it. **Vincent effectively took the second
option by rejecting the result of the first**, from a play render: *"The angle on that door is not
the same as the wall"*, *"it is looking south west, but not geometrically perfect south west"*,
*"its looking more west than south!"*

**WHY SCALING WAS NEVER GOING TO WORK, and it is the part worth keeping: `x1.54` IS AN UPSCALE OF
PIXEL ART.** The sprites import at 64 PPU, so 1.54x renders every pixel at 1.54 screen pixels
against the masonry's 1.0 - the door read as a chunkier material than the wall it sits in. Scaling
was chosen when the alternative was a generation request; re-authoring at the wall's own PPU costs
the same and removes the defect instead of enlarging it.

**THE APPROVED ART, all four states the prefab binds:**

    door_bonestone_{sealed,locked,open,final}_SW_000.png
    192 x 160 px at 64 PPU  =  3.000 x 2.500 world units, scale x1.0
    spritePivot {x: 0.5, y: 0.0875}   = 14 px bottom pad / 160, the art-base pivot convention
                                        wall_door_jamb already ships as 26/176 = 0.147727
    GUIDs UNCHANGED - the PNGs were replaced in place, so Door.prefab needs no rewiring.

**EVIDENCE - measured live off the spawned prefab by the Game Agent, not computed:**

    leaf edges          -1.50000 and 1.50000
    jamb inner edges    -1.50000 and 1.50000
    residual gap         0.00000 per side
    leaf bottom          0.00000  on the floor line
    leaf top             2.50000  exactly matching WallHeight

**Unity 6000.1.8f1 import check, all four:** rect 192x160, pivot (96,14) px, PPU 64, bounds
y -0.21875..2.28125 x -1.5..1.5, Point filter, **failures=0**.

**THE PREDICTION THIS REPLACED, stated before the render and confirmed by it:** the old door was
`128/64 x 1.54 = 3.080` units against `WallHeight 2.5` and **rode 0.58 above the wall top**; the new
one matches course for course. That was offered as falsifiable and it held.

**THE TWO PREFAB FIELDS ARE A PAIR - CHANGING ONLY THE SCALE SINKS THE DOOR 0.219 INTO THE FLOOR**,
because the new art's 14-row bottom pad arrives as a negative `bounds.min.y` that a transform offset
cannot see:

    Door.prefab  m_LocalScale     {x: 1.54, y: 1.54, z: 1.54}  ->  {x: 1, y: 1, z: 1}
    Door.prefab  m_LocalPosition  {x: 0, y: -1.25, z: 0}       ->  {x: 0, y: -1.03125, z: 0}

**`DoorArtScale` in `DoorPrototypeSceneBuilder.cs` IS NOT THIS LEVER.** That constant scales the
builder's isolated scene, which loads the `_S_` sprites by name and still shows the old art. The
shipped path is `Door.prefab` via `DoorSpawner.cs:134`.

**WHAT THIS DOES NOT SETTLE.** Vincent has rejected the art-only remedy for the doorway as a whole -
*"it doesnt work right, you will need to extend the wall get rid of the collide and use a mask"* and
*"The gap is still there"* - and the continuous-wall-plus-mask work is proceeding separately. **That
changes the WALL, not the leaf.** This record approves the leaf's geometry and material; it makes no
claim that the doorway is finished.
