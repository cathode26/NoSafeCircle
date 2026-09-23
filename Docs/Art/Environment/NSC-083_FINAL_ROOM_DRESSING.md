# NSC-083 — Final Room dressing design

**Author: Art Director Agent, 2026-09-23. Authored BEFORE the crew runs.** Fifth of five — the set
is complete.

**This document is the placement intent the Art Director will approve against at VAL-002.** It is
not a contract and adds no criterion. Where it and NSC-083 disagree, the contract wins.

**Room identity: the Final Room.** The end of the dungeon. A bone throne on a raised mass in the
centre, benches near the entrance, and an open north hall where the last encounter happens.

**Every number below was resolved from `FinalRoomLayout.cs` and `PropCatalog.json` on main.**

---

## THE ROOM, AS THE LAYOUT DEFINES IT

    room bounds        X [-12, 12]   Z [64, 86]      walls 0.5 thick, **2.0 tall**
    inner faces        X [-11.75, 11.75]   Z [64.25, 85.75]
    D4  ENTRY          (4, 64)   width 3  -> X [2.5, 5.5]    in the SOUTH wall
    D5  EXIT           (0, 86)   width 3  -> X [-1.5, 1.5]   in the NORTH wall
    final obstacle     X [-2.5, 2.5]   Z [73.5, 78.5]   height 2.0     a 5 x 5 mass, dead centre
    west bench         X [-9.75, -7.25]   Z [68.225, 68.775]   height 0.7
    east bench         X [7.25, 9.75]     Z [68.225, 68.775]   height 0.7
    north staging      X [-9, 9]   Z [80, 84]        18 x 4, the encounter space
    circulation        west 9.25     east 9.25       symmetric

**This room's walls are 2.0, not 2.5.** It is the only one. Every height judgement here is against
a lower wall than the rest of the dungeon.

---

## THE ONE RULE THAT OVERRIDES EVERY PLACEMENT BELOW

**Nothing may read as impassable that is passable — and the chain posts are the trap.**

`fr_bone_chain_post` is catalogued *"placed in rows around the bounded area"*. **A row of chain
posts around the central obstacle reads as a fence, and a fence reads as a closed arena.** The
obstacle is only the 5 x 5 centre; **9.25 units of circulation are open on each side**, and the
north staging area is 18 x 4 of clear floor. **A player who believes the arena is closed will not
enter it — in the room where the game ends.**

This is the inverse of the Lower Vault's rule, and it is the most expensive one in the set to get
wrong, because there is no room after this to recover the read.

### Mechanical tests

1. **No continuous run of chain posts.** Posts go in **broken rows with visible gaps at least 2
   units wide**, and **at least one gap must face each of the west and east circulation routes.**
   A ring the eye can close is a fence.
2. **No chain post inside the west or east circulation**, X [-11.75, -2.5] and X [2.5, 11.75]. They
   belong **against the obstacle's own edge**, not out in the floor.
3. **`NorthStagingBounds` X [-9, 9], Z [80, 84] carries nothing.** That is where the encounter
   happens. Not a candle, not a bone pile, not a flat prop.
4. **Door approaches clear** — D4 X [2.5, 5.5] for 2 units north of the south wall, D5 X [-1.5,
   1.5] for 2 units south of the north wall.
5. **No prop against the south or east wall faces.** See below.

---

## DRESSABLE WALLS: NORTH AND WEST ONLY

**The camera is `Quaternion.Euler(30, -45, 0)`**, asserted at
`CommittedSceneCameraConformanceTests.cs:45`. At yaw -45 it looks toward -X and +Z:

    FAR, drawn, dressable      north wall  Z = 86      west wall  X = -12
    NEAR, cut away, NOT drawn  south wall  Z = 64      east wall  X = +12

`LowerVaultSceneBuilder.cs:188` says the same in the sibling room. **Props against the south or
east faces are never rendered.**

**The ENTRY door D4 is in the cutaway south wall** — do not dress the entry threshold.

**The far corner is north-west (-12, 86)**, the only corner where two drawn walls meet.
**`shared_web_corner_a` goes there and nowhere else.** Note it draws at 2.02 against a 2.0 wall;
see below — that is not a defect.

**The room is symmetric in geometry and will NOT be symmetric on screen.** The west side is far and
drawn; the east side is near and cut away. **Dress the west side more.** Mirroring the dressing
east-for-west wastes half of it and makes the room read lopsided in the direction opposite to the
one intended.

---

## THE TWELVE COMMITTED PROPS

All 64 PPU. **Drawn size is the alpha bounding box.**

| prop | drawn w x h | declared h | pivot | role |
|---|---|---|---|---|
| `fr_landmark_bone_throne` | 2.56 x 3.59 | 2.40 | ground_line | **the landmark** |
| `shared_web_corner_a` | 1.48 x 2.02 | 1.50 | ground_line | far corner only |
| `fr_bone_chain_post` | 0.48 x 1.08 | 1.20 | ground_line | broken rows, see rule |
| `shared_web_drape_b` | 1.28 x 1.30 | 1.00 | ground_line | a drawn wall face |
| `fr_round_table_with_stools` | 1.92 x 1.61 | 0.90 | ground_line | the last camp |
| `fr_bench_x` | 1.69 x 1.59 | 0.70 | ground_line | the two bench bounds |
| `shared_candle_cluster_a` | 0.89 x 1.02 | 0.60 | ground_line | small light |
| `fr_comedy_party_hat_skull_cake` | 0.80 x 0.73 | 0.50 | ground_line | the one joke |
| `shared_bone_pile_a` | 1.19 x 1.02 | 0.50 | ground_line | remains |
| `shared_rubble_scatter_b` | 1.88 x 1.41 | 0.50 | ground_line | **see the rubble note** |
| `fr_ritual_bone_candle_ring` | 2.05 x 1.30 | 0.30 | **lie_within** | floor, at the throne |
| `shared_bone_pile_b` | 1.27 x 0.98 | 0.30 | **lie_within** | floor |

### The throne rises above the wall line, and here that is the point

`fr_landmark_bone_throne` draws at **3.59 against a 2.0 wall**. In every other room I have said
keep a landmark under the wall. **Here, do not.**

This is the final room, the throne is the last thing in the dungeon, and it stands on a 2.0-tall
mass in the dead centre. **Breaking the wall silhouette is what makes it read as the climax rather
than as more furniture.** It is also the only room whose walls are 2.0, so the effect is available
here and nowhere else.

**That is a visual pick and it is mine to make.** Recorded so nobody "fixes" it later.

**Everything else drawing above the wall is the ordinary case and is not a defect either.**
`footprint_world_size.h` is the *occluding* height; the drawn sprite is taller because isometric
art folds depth into vertical extent. Walls are tile-built and axis-aligned; props are not.
**Never fix a height by scaling a prop** — that breaks the pixel grid at 64 PPU.

### Two `lie_within` props — the most of any room

`fr_ritual_bone_candle_ring` and `shared_bone_pile_b` anchor at the **centre of their alpha
bounding box**, not the bottom edge. **Three flat props were anchored wrong by 0.49–0.65 world
units before this was caught** — fix on main at `fd31ce99f`, classifying importer at `7fb5259b5`.
**This room has two of them, so it is the best test of whether the dressing builder handles the
rule at all.**

Both need real floor. Not against the obstacle base, where a flat sprite reads as half-buried.

### The rubble note

`shared_rubble_scatter_b` is catalogued for this room but its `footprint_reference` names
**`RuinedEntryLayout.RubbleABounds/RubbleBBounds`** — another room's geometry. **It has no
footprint here.**

**Use it sparingly, at the foot of the central obstacle only**, as material that fell off the mass.
**Do not scatter it across the circulation.** The Ruined Entry brief establishes that rubble means
*you cannot pass*; this is the last room the player sees and contradicting that read here is the
worst place to do it.

---

## PLACEMENT

### The throne and the central mass

**`fr_landmark_bone_throne` centred on `FinalObstacleBounds`**, facing south toward the D4 entry so
the player meets it face-on.

**`fr_ritual_bone_candle_ring` on the floor at the obstacle's south foot**, flat, between the
throne and the approach. It is 2.05 wide and it frames the throne without adding height.

**`shared_rubble_scatter_b` at the mass's west foot**, on the drawn side, where it reads.

**`fr_bone_chain_post` in broken rows against the obstacle's edge** — see the one rule. **Gaps
facing west and east.**

### The benches — the room's quiet beat

**`fr_bench_x` on `WestBenchBounds` and `EastBenchBounds`.** Both are 2.5 wide and 0.55 deep at Z ≈
68.5, near the entry. The bench prop draws 1.69 wide, so **one bench per bound, centred.**

**These are the last place anyone sat.** Put `shared_candle_cluster_a` beside the **west** bench —
the drawn side — and leave the east one bare. **Asymmetric, deliberately**: the west is what the
camera sees.

### The last camp

**`fr_round_table_with_stools` in the west circulation, around X -7, Z 75-77**, roughly level with
the obstacle, against the drawn side.

**This is the room's story in one prop: people made a camp in the last room and did not leave.**
Keep it out of the north staging area and at least 2 units clear of the obstacle so it does not
merge with the mass.

### Webs and bone

**`shared_web_corner_a` in the north-west corner. `shared_web_drape_b` on the north or west face,
one only.**

**`shared_bone_pile_a` and `shared_bone_pile_b` near the throne and along the west wall** — not in
the staging area, not in the circulation lanes' centres.

### The one joke

**`fr_comedy_party_hat_skull_cake` on the round table.** A skull in a party hat next to a cake, at
the last camp. It is 0.80 units.

**This is the best-placed joke in the project and it earns its place:** the camp is the room's
saddest detail and the cake is the same people refusing to be miserable about it. **One comedy
detail, not three.** Not on the throne — the throne is doing the room's serious work.

---

## PALETTE AND DENSITY

**Judged against this room's own committed sprites, not a fixed number.**

- **Bone is this room's character, and unlike the Bone Archive it is bone WITHOUT paper** — that is
  what keeps the two rooms distinct. The Archive is yellowed and dry; this room is pale and hard.
- **The candles are the only warm note and they should cluster at the camp and the throne**, which
  is also where the player's eye should travel: entry, camp, throne, north hall.
- **Nothing may out-read the throne.**
- **Density: dense at the centre and the west, empty at the north staging area.** The staging
  emptiness is not undressed, it is **cleared** — and after four dressed rooms the player will read
  a deliberately empty 18 x 4 hall as exactly what it is.

---

## WHAT VAL-002 WILL BE JUDGED ON

The gameplay-density panel, not a contact sheet.

**Pass/fail, anyone can check:**

1. Every dressing object is a prop from the committed catalog, at its catalog pivot and PPU —
   including **both** `lie_within` props.
2. `NorthStagingBounds` X [-9, 9], Z [80, 84] is empty.
3. Chain posts form broken rows with gaps of at least 2 units, including one facing each of the
   west and east circulation routes; no chain post stands out in the circulation.
4. Both door approaches are clear.
5. No prop is placed against the south or east wall faces, which are cut away.

**The Art Director's judgement:**

6. The throne reads as the landmark and as the end of the dungeon at gameplay distance.
7. The arena reads as **open** — a player at D4 can see that they may walk around the obstacle.
8. The camp reads as a camp, and the room reads as bone-without-paper, distinct from the Bone
   Archive.
9. The dressing reads as the same material family as this room's own committed sprites.

---

## THE SET IS COMPLETE

All five rooms now have placement intent written before their crews run:

    NSC-079  Ruined Entry    NSC-080  Bone Archive    NSC-081  Chapel of Ash
    NSC-082  Lower Vault     NSC-083  Final Room

**Read across them, the five rooms are meant to be distinguishable by material alone:** stone and
growth, yellowed paper, pale ash, iron and wet, pale bone. **If two rooms read the same in their
panels, that is the defect to fix first** — it costs the dungeon its sense of progression, and no
single room's panel can show it.
