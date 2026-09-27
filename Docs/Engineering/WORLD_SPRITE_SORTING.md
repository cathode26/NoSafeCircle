# World sprite sorting: what decides what draws in front

**Measured on canonical `main` at `163d7cca` on 2026-09-27** from `ProjectSettings/TagManager.asset`,
`ProjectSettings/GraphicsSettings.asset`, `Resources/Player/IsometricCamera.prefab` and the source.

**The single definition of the four values lives in code, on purpose, and this document does not
restate it:** `Scripts/World/WorldSpriteConvention.cs`. It is in the *runtime* assembly so runtime
spawners can reach it, it carries its own history in a long comment, and every editor constant
forwards to it. **If a number here and a number there ever disagree, the code is right.** This
document exists for the things the code cannot say from inside one file: the precedence chain, where
the camera settings actually come from, and which tests hold it together.

---

## 1. The precedence chain, in the order Unity applies it

    1.  sorting LAYER index          compared first, and it is the INDEX, not the name
    2.  sortingOrder (int)           compared next, and it beats position unconditionally
    3.  transparency sort            only reached when 1 and 2 tie

Two layers exist, and only two (`TagManager.asset`):

| index | name | uniqueID |
|---|---|---|
| 0 | `Default` | 0 |
| 1 | `WorldSprites` | 1043912875 |

So **anything left on `Default` draws behind everything on `WorldSprites`, whatever number it
carries.** Five baked prefabs sat on `Default` for a night; 222 props were instantiated and not
drawn, and Vincent photographed the result. A test asserting the literal string `"Default"` passed
the whole time.

Every world sprite and every world tilemap is on `WorldSprites` at `sortingOrder = 0` — **one
shared order**, so step 2 always ties and depth always falls through to step 3, which is position.
Authored per-object integers are the failure mode, not the mechanism: 22 Bone Archive shelves were
authored at `-219..-36` against a wizard at `0`, so no shelf could occlude him at *any* position.

The constraint chain that forces one shared order is worth knowing before anyone proposes tidying
it. Walls are Tilemaps, and a `TilemapRenderer` has **one** order for an entire run — Unity has no
per-tile order — so walls cannot carry per-position depth and must sort on the axis. The wizard must
be on the axis to sort against walls. The props must therefore be there too. **walls -> wizard ->
props**, and there is no arrangement that keeps authored integers *and* lets walls occlude.

The two background bands sit below every world sprite:

- floors at `short.MinValue`
- the architectural border at `short.MinValue + 10`

`short.MinValue` rather than a small negative because `Renderer.sortingOrder` is a signed 16-bit
field in Unity's sorting key: out of range **wraps silently to a large positive**, which puts the
floor in front of everything. Both were `-100/-90` until a catalog prop authored at `-1165` went
under the floor.

---

## 2. Where the transparency sort actually comes from — not from ProjectSettings

This is the part that is easy to get wrong by reading one file.

`ProjectSettings/GraphicsSettings.asset` says:

    m_TransparencySortMode: 0            (Default)
    m_TransparencySortAxis: {x: 0, y: 0, z: 1}

**Both of those are effectively inert.** `m_TransparencySortAxis` is only consulted when the mode is
`CustomAxis`, and the mode here is `Default`. The live values are set in code, every time:

`Scripts/IsometricCameraFollow.cs:32-33`, in `OnEnable`:

    camera.transparencySortMode = TransparencySortMode.CustomAxis;
    camera.transparencySortAxis = IsometricTransparencySortAxis;

and the axis itself, at `:21`:

    public static readonly Vector3 IsometricTransparencySortAxis =
        new Vector3(0f, 1f, 0.26f).normalized;

**Why it is reapplied in `OnEnable` rather than serialized:** the file says it outright —
*"Camera.transparencySortMode/Axis are not serialized into the scene by every supported Unity editor
version"*. So a committed scene cannot be trusted to carry them and the component restores them at
load and at Play. The same constant is shared with the editor camera builder so the two can never
drift.

**Why the coefficients are what they are**, also from the file, and both halves matter:

- `x = 0` **deliberately contributes no depth**, so moving along a horizontal wall cannot flip
  occlusion.
- `z` is **positive** because Unity draws the larger dot product first (farther back), and this
  camera sits at `-Z` looking toward `+Z`, so a larger world Z is genuinely farther. *A negative
  coefficient inverted depth and rendered a door in front of a wizard standing south of it.*

The camera is orthographic, size 8, at **pitch 30, yaw -45, roll 0** — decoded here from
`IsometricCamera.prefab`'s serialized quaternion `(0.2391176, -0.3696438, 0.0990458, 0.8923991)`
rather than recalled.

### The camera already supplies the isometric projection

Worth stating because it has been got wrong three times by three different agents reasoning from PNG
dimensions: the orthographic camera over a tilemap laid flat in XZ **already projects to
isometric**. A pre-drawn diamond tile would therefore be projected **twice**. No inspection of a
sprite's pixel dimensions can reach that fact — it is a property of the scene, not of the file.

---

## 3. `spriteSortPoint` must be `Pivot`, not `Center`

`PropPrefabVerifier` checks it and states the reason: *Center sorting reads the sprite's middle
rather than its ground contact point and breaks depth against the wizard.* The prop pivots are
authored near the bottom of the sprite for exactly this reason — the door leaf's, for instance, is
7 px up from the bottom of a 128 px sprite.

---

## 4. What holds this together, and what does not

| check | what it covers |
|---|---|
| `Editor/Environment/PropPrefabVerifier.cs` | per prop prefab: sorting layer name, sorting order, `spriteSortPoint`, and it reads the expected values **from `WorldSpriteConvention`** rather than restating them, so a change to the band cannot pass |
| `Tests/Editor/WorldSpriteSortingLayerDeclarationTests.cs` | the layer is declared in `TagManager.asset` |
| `Tests/Editor/World/BackgroundSortingBandTests.cs` | the two background bands |
| `Tests/IsometricSortingRenderPlayModeTests.cs` | sorting in an assembled world |
| `Tests/Editor/TitleScreenSceneBuilderTests.cs:125-127` | that a built camera gets `CustomAxis` and the shared axis |
| `Tests/Editor/World/SceneStubTests.cs:225` | records that the convention *fails silently* because the camera fields are not serialized |

**The gap: `PropPrefabVerifier` never reads `gameObject.layer`.** It validates the *sorting* layer
and not the *physics* layer, and the physics layer is what decides whether a prop blocks sight and
fireballs. See `PROP_COLLIDERS_AND_NAVMESH.md` §4, where 25 of 31 props disagree with the stated
policy and nothing notices.

---

## The rule that generalises, and it is the one worth carrying

**Every failure in this subsystem was silent, and in each case a test was green while the screen was
wrong.** A literal `"Default"` assertion passed while 222 props were invisible. Authored orders
`-219..-36` were internally consistent and made occlusion impossible. `-1165` was a valid int and
went under the floor. The camera fields are not serialized, so a scene can look correctly authored
and load wrong.

So: **assert the relation, never the value it happens to have today** — read the expected value from
the one definition, the way `PropPrefabVerifier` does, and prefer a rendered frame over arithmetic
when the question is what a player sees.

## What is not proven

- **That nothing on `Default` is currently invisible.** The prop population is checked by the
  verifier; walls, doors, effects and UI were not swept for this document.
- **That `0.26` is the right Z coefficient** for the current camera pitch. It is the value that
  fixed an observed inversion; no one has derived it from the 30-degree pitch or tested the margin.
- **Whether the door leaf's ~0.4 overshoot above the wall top sorts correctly** against the wall
  tilemap it pokes through.

## What would falsify this document

- **The layer indices**: re-read `m_SortingLayers` in `ProjectSettings/TagManager.asset`. A third
  layer inserted before `WorldSprites` changes its index and every claim that depends on it.
- **The single shared order**: if any world sprite carries a `sortingOrder` other than
  `WorldSpriteConvention.SortingOrder`, position no longer decides depth for it.
- **Where the sort comes from**: if `IsometricCameraFollow.OnEnable` stops setting `CustomAxis`,
  the inert `GraphicsSettings` values become live and section 2 is wrong.
- **The axis itself**: `(0, 1, 0.26)` was tuned against a 30-degree pitch. Change the camera
  pitch and the coefficient needs re-deriving; nobody has measured its margin.
