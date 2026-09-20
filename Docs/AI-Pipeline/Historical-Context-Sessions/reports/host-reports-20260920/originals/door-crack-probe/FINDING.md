# The door jamb seam: measured in the live scene, 2026-09-17

Game Agent. Probe run in `C:\nscrev\branch-verify` at main `b7e46c320`, using the **same query the
enemy uses** — `Physics.Raycast` from `position + Vector3.up`, `DefaultRaycastLayers`,
`QueryTriggerInteraction.Ignore`, matching `EnemyTargetKnowledge.HasUnobstructedViewOfWizard` and
`EnemyLanternWispCaster`. Raw output: `result.txt`. Probe source: `DoorCrackProbe.cs` (scratch,
never committed; the checkout was left clean).

## The defect, in numbers

Every one of the **5 doors** in the committed scene:

```
blocker enabled : True                     (sealed state; the probe also forces it enabled)
blocker size    : (2, 2.5, 0.3)
blocker x span  : 2 units, centred on the door
wall collision  : begins at ±1.5 from the door centre
sightline OPEN  : x offset -1.25 and +1.25
```

So the doorway opening is **3 units wide** (`DoorOpeningWidth = 3f`) and the blocker is **2 units
wide**, leaving a **0.5-unit vertical slot on each side** — between the blocker's edge at ±1.0 and
the wall's edge at ±1.5. Ten slots across five doors.

**The sightline passes beside the blocker, not through it.** At every offset from -1.0 to +1.0 the
ray hits `DoorVisual`; at ±1.25 it hits nothing at all; at ±1.5 and beyond it hits the wall
collision. That is the seam Vincent photographed: *"The projectile went between the wall and the
door."*

**Both sides, not only the hinge side.** The screenshot shows one; the measurement shows two.

## Cause

`DoorPrototypeSceneBuilder.cs:1088` sets `doorwayBlocker.size = new Vector3(2f, 2.5f, 0.3f)`, and
the comment above it says the collider is *"sized to the door's footprint"*. That is the defect
stated in the source: **collision was sized to the door leaf's art, not to the hole in the wall.**
A 2-unit leaf cannot seal a 3-unit opening.

Not the art: the door in the scene is the builder's procedurally generated `DoorSprite`, a filled
rectangle with a border. There is no crack in the texture. What reads as a crack is the slot
itself, showing background between door and wall.

Not the LOS code: both `HasUnobstructedViewOfWizard` implementations are correct. They report a
clear path because the path *is* clear.

## Three symptoms, one hole

1. An enemy sees the wizard walking past a closed door (chest-height ray through the slot).
2. The enemy's projectile passes through the slot.
3. The wizard's fireball does too.

**Consequence for NSC-007:** its new collider-blocked projectile can pass every acceptance test and
the fireball will still go through doors, because the ray genuinely has a clear path. NSC-007 is not
a fix for this and must not be credited with one.

## The fix, and the test that must come with it

Seal the **opening**, not the leaf: either widen the blocker to the full 3-unit opening, or author
a separate doorway occluder spanning jamb to jamb while the leaf keeps its own art-sized collider
for click targeting.

A regression test must **sweep** the doorway — several lateral offsets *and* several heights, from
both sides, with the blocker enabled, requiring every ray to be blocked. A single centre-line ray
passes today and proves nothing: the probe shows the centre ray correctly hitting `DoorVisual`
while ±1.25 is wide open. `DoorCrackProbe.cs` is a usable starting point for that test.

## Ownership note

The blocker geometry belongs to **NSC-020**, which is `needs_replan`, so this likely wants its own
narrow task rather than riding NSC-020. That call is the GER Agent's.

Separately: PixelLab door art exists in the repo and is unwired —
`Assets/NoSafeCircle/DoorPrototype/Art/Doors/Source/door_bonestone_{locked,sealed,damaged,broken,open,opening}_S_000.png`
— while the scene uses the generated placeholder. Not part of this defect; possibly a cheap visual win.
