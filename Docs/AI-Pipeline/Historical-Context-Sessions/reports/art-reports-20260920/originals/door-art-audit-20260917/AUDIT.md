# The seven committed door states: are they still the art we want?

Art Director Agent, 2026-09-17, at the Documentation Agent's request ("are those seven door states the ones
you'd want bound, or has your direction moved"). **No generations spent.** Everything below is measured from the
committed blobs on local `main` (`b7e46c320`), extracted with `git show`, and from
`Docs/Art/Doors/inventory.json`.

## Verdict

**The style has not moved - bind them. But not yet, and not silently, for three reasons that are not about
style.** Two of the three are cheap; the first is Vincent's to answer and costs him thirty seconds.

## What is there, measured

`Assets/NoSafeCircle/DoorPrototype/Art/Doors/Source/door_bonestone_<state>_S_000.png`, seven states - sealed,
locked, opening, open, damaged, broken, final. Sheet: `door_states_2x.png`, numbers: `audit.json`.

| Check | Result |
|---|---|
| Canvas | **128 x 128** for all seven - a 2-unit camera-facing box at 64 PPU, which is exactly the convention NSC-095/NSC-096 landed for the wizard. Nothing to re-author |
| Cross-state alignment | **bbox identical in all seven** (6,4 - 122,121) and the lowest opaque row is **120 in every state**. Spread **0**. The door will not hop or shift when its state changes - this is the defect class that cost NSC-095 a revision, and this family does not have it |
| Palette | violet hue **41.5% to 55.6%**, warm hue **0.5% to 4.3%** (only `final` reaches 11.7%, from its gold glow). The approved wizard measures violet 43.7%. **The same cold violet slate Vincent just picked for the NSC-078 masonry** |
| Colour count | **22 to 57** per state, already inside the approved register (wizard 63). No `reduce_colors` pass needed |
| Facings | **direction S only.** Mirroring would serve E and W geometrically but flips the light, which the whole family lights from the upper left |

## The three things binding needs first

**1. Vincent has never seen these.** `inventory.json` says `"human_visual_approval": false` with
`"assistant_selection_authority": "operator-authorized unattended continuation"` - an assistant picked family B
over family A and committed it. Every other art family in this game carries Vincent's own pick. **Binding art he
has never approved would make the pick permanent by default**, which is the one thing my role exists to prevent.
`door_states_2x.png` is the whole family on one sheet; his answer is a yes, a no, or "re-roll the glow".

**2. Every state paints the floor.** Each sprite carries a lavender ground disc with mossy stones under the
threshold. That is the Tilemap's job, and it will sit as a lighter patch on top of the committed floor art. It is
also the exact pattern the new canon line names: **painted ground implies walkable ground.** Either the disc is
masked out of the sprites (an `inpaint_image_pro_flash` pass, about 10.5 metered per state, so roughly 74 for
seven), or it is accepted deliberately as a threshold decal and the floor tile under a door is left bare. **That
is a design decision, not a defect - but someone has to take it before these are bound**, because it is far
cheaper now than after a room is dressed around them.

**3. The art draws the arch and the jamb, not just the leaf** - the stone surround is part of every sprite. So
the wall opening, the painted jamb and the blocker collider all describe the same opening three times. That is worth
handing to the Game Agent with the jamb-seam fix: **the collider should match the painted jamb**, and the
`opening`/`open`/`broken` states each expose a different amount of passage, so whatever the fix does about the
seam has to be checked against the state the door is actually in. `broken` shows a hole through a closed leaf -
if that hole is not a sightline, it is the mirror case of the bug Vincent just found.

## What I would add later, not now

Non-south facings. A north, east or west door has no art today, and mirroring flips the upper-left light. That is
a generation request with its own cap when a room needs it - not a blocker for binding the south doors that
already exist.
