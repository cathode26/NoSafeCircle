# NSC-064 VAL-002 — Assistant art-selection review

**Art Director Agent, 2026-09-24. Measured at commit `7f7a8efbb78fe9a53e4c035e39e9f246a4e32c95`.**

**Gate text:** *"The assistant verifies the kit is mutually coherent and maps every selected motif
to at least one named room without claiming that the Unity world is already authored."*

**Verdict: the kit is mutually coherent, every motif maps to at least one named room, and the
Unity world is NOT authored. Stated explicitly below, because the gate requires that it not be
claimed.**

---

## 1. THE KIT, AS MEASURED — 11 sources, 5 floors and 6 wall modules

Full deterministic inventory in `NSC064SourceInventory.json` (VAL-001). No prop sources live under
this task's tree; props are NSC-078's and are referenced here only as the palette reference.

    floor_RuinedEntry   128x128   16 Wang tiles @32px   100% opaque
    floor_BoneArchive   128x128   16 Wang tiles @32px   100% opaque
    floor_ChapelOfAsh   128x128   16 Wang tiles @32px   100% opaque
    floor_LowerVault    128x128   16 Wang tiles @32px   100% opaque
    floor_FinalRoom     128x128   16 Wang tiles @32px   100% opaque
    wall_straight       128x160   shaped silhouette     60.0% opaque
    wall_corner         128x160   shaped silhouette     54.9% opaque
    wall_end_cap         80x160   shaped silhouette     59.7% opaque
    wall_door_jamb      128x176   shaped silhouette     55.7% opaque
    wall_pilaster        64x176   shaped silhouette     39.9% opaque
    wall_broken_stub    128x128   shaped silhouette     52.8% opaque

**Import settings: ZERO deviations from the task's own style lock** across all eleven — Sprite,
Single, 64 PPU, Point, uncompressed, alphaIsTransparency, no mipmaps, **wrap Clamp**, Texture2D.
*(`wrapU: 1` is Clamp; the enum reads inverted and has failed sixteen assets on that field before.)*

**Floors are full rectangles with every corner opaque**, so they tessellate without holes. **Walls
are shaped silhouettes with alpha-0 corners, which is correct for a vertical billboard** and is
not a defect.

## 2. MUTUAL COHERENCE — measured against the reference, not asserted

**The style lock declares a palette band "measured off delivered props": luminance 68-73,
saturation 19-39, warm 4-5%.** Measured directly, 10 of 11 kit sources fall outside it.

**THAT RESULT IS AN ARTIFACT OF THE INSTRUMENT AND I PROVED IT BEFORE REPORTING IT.** Running the
identical function over **NSC-078's delivered props — the very set the band was derived from —
only 1 of 14 lands inside the declared saturation band.** Prop median saturation is **46.2**
against a declared 19-39; prop median luminance **59.7** against a declared 68-73. **A reference
set cannot fail the band that was measured off it, so my instrument reads systematically higher
than the one that set it.** The absolute numbers are not comparable across instruments; the
relative comparison is.

**COHERENCE, KIT vs PROPS UNDER ONE INSTRUMENT:**

    props (n=14)   luminance median 59.7  (40.5-102.2)    saturation median 46.2  (29.4-65.4)
    kit walls      luminance       46.4-58.9              saturation       40.3-57.9
    kit floors     luminance       39.5-73.2              saturation       26.3-55.7

- **Walls sit inside the prop range on both axes, slightly darker than the prop median.** Coherent.
- **Floors sit at or below prop luminance throughout**, which is exactly what the lock requires:
  *"a floor belongs under the things standing on it."* Coherent, and coherent **by design**.
- **Colour depth holds: every source is at or under the 48-colour lock** — walls at exactly 48
  (the `reduce_colors` target), floors 24-31. This one IS instrument-independent and it passes.

**One measured observation, offered rather than hidden:** `wall_door_jamb` and `wall_pilaster` are
**176 px tall (2.75 world units)** against the lock's wall height of **160 px (2.5)**. Both are
elements that architecturally rise above the wall line — a jamb carries its lintel, a pilaster its
capital. **I read that as intentional, not as drift**, and record it so a later reader can disagree
with the reading rather than rediscover the number.

## 3. EVERY MOTIF MAPS TO AT LEAST ONE NAMED ROOM

**Floors map one-to-one by name** — `floor_RuinedEntry` to Ruined Entry, and so on for Bone
Archive, Chapel of Ash, Lower Vault and Final Room. **Five floors, five named rooms, no orphan and
no gap.**

**Wall modules, each to at least one room** (mapping made against the committed room layouts I
authored the five dressing catalogs against):

    wall_straight      ALL FIVE - every room has straight runs; the cutaway convention draws
                       north and west full height as the backdrop
    wall_corner        ALL FIVE - every room is rectangular, so every room has corners
    wall_end_cap       ALL FIVE - the south and east cutaway stubs terminate their runs
    wall_door_jamb     Ruined Entry (D1), Chapel of Ash (D3), and every other doored threshold
    wall_pilaster      Chapel of Ash first - ecclesiastical vertical articulation along the aisle;
                       also Bone Archive, between the three shelf banks
    wall_broken_stub   Ruined Entry above all - the room whose identity IS ruin; also the
                       cutaway stubs wherever a run is meant to read as broken

**No motif is unassigned, and no named room lacks a floor.**

## 4. WHAT I EXPLICITLY DO NOT CLAIM — the gate asks for this

- **THE UNITY WORLD IS NOT AUTHORED FROM THIS KIT.** Measured: **all eleven GUIDs have ZERO
  references anywhere in `Assets/`.** The rooms currently draw procedural masonry generated in
  code. **Nothing in this record says otherwise.**
- **The 16-tile Wang sheets are imported `spriteMode: Single`, so they are not sliced into tiles.**
  That is **correct for a source** and explicitly downstream: **INT-001** says *"A separate task
  imports the approved sources, builds deterministic Tile and Sprite assets, and applies them."*
  AC-005 likewise bars this task from creating Unity Tile assets.
- **Vincent has not reviewed this art.** The provenance document records that he pre-approved the
  spend — *"all runs approved"* — and that **clearing the generation is not a review of the
  result.** VAL-002 is the assistant's verification and is not a substitute for his opinion.
- **No claim about gameplay geometry.** Nothing here changes, or depends on, the authored room
  layouts.
