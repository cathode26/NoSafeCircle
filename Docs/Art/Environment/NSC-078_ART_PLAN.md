# NSC-078 art plan: first-wing props

**Status:** the authoritative art plan for NSC-078 (Art Director Agent, 2026-09-17). NSC-078 revision 4 cites this file by its commit and SHA-256. It carries everything an isolated task checkout needs:
- the 45 catalog rows, with per-entry footprints and canvases;
- the subject prompts and the global prompt clause;
- the wizard-proxy scaling rule;
- the five-source style-lock pilot;
- the tool settings and the spend estimate.

It follows `NSC-078_DECISIONS.md` (2026-09-17): D-2 gives NSC-078 every independently sorted SpriteRenderer prop, raw exports live under `Docs/`, and style inputs come only from Vincent-approved pilot sources.

**Planning only:** this file authorizes no PixelLab spend. Vincent's spend go is separate.

**Precedence:** where this plan and the committed `Tasks/NSC-078.yaml` differ, the contract wins. Follow the contract's acceptance criteria and gates, and treat the difference as a defect in this plan: report it to the Art Director Agent, which amends the plan.

Sources:
- `Docs/Art/Environment/DUNGEON_ART_DIRECTION.md` (canon);
- the Art Director bible (`art-director.md` in Vincent's Claude agent folder);
- the committed room layouts `Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms/*Layout.cs`;
- the NSC-064 candidate kit documentation on `codex/nsc064-connections-20260914`;
- the GER packet for NSC-078 (rounds 01-04).

Density: Vincent picked option B on 2026-09-16. Characters are re-made at 128x128 at about 64 px per world unit in a 2x2-unit camera-facing box, so characters, props and architecture all target about 64 px per world unit (D-1).

---

## 1. First-wing prop list

### Conventions used below

- **Density:** 64 px per world unit.
- **Display:** sprites face the camera. PixelLab `low top-down` art already contains its projection. On a world-aligned plane it is squeezed to 0.71x and sheared; today's wizard shows exactly that (about 15x96 px at 1080p). `facing` picks which drawing to use; it never rotates the sprite.
- **Canvas** (camera Euler 30, -45, 0; footprint x, z; height h):
  - width = (x + z) x 0.7071 x 64 + 8 px;
  - height = (h x 0.866 + (x + z) x 0.3536) x 64 + 8 px;
  - rounded up to a multiple of 4 and at most 256 (`create_object_pro_flash` custom sizes).
- **`footprint_world_size`:** x, z, h in world units. It records the drawn object, not the gameplay collider. Big layout areas (the 6x7 rubble field, the 5x5 final obstacle, the storage piles) are filled by clusters of these pieces, placed by the dressing tasks.
- **Facing on screen:** a `world_x` long side runs from upper-left to lower-right; a `world_z` long side runs from lower-left to upper-right.
- **Committed layouts fix the facings:**
  - Chapel pews run along world X (`ChapelOfAshLayout.PewFootprints`, 5.5 x 1.5, 1.25 high);
  - Bone Archive shelves run along world Z (`BoneArchiveLayout.ShelfA/B/C`, 1.5 x 11-12, 2.5 high);
  - Final Room benches run along world X (`FinalRoomLayout.WestBenchBounds/EastBenchBounds`, 2.5 x 0.55, 0.7 high).
  - The first wing therefore needs only one facing for each long-footprint family. AC-005 records the other facing as not required.
- **Long runs, no seamless tiling:** shelf, pew and rail segments use a post-and-panel design. Every segment carries an upright at its joint edge, so pieces butt together without pixel-exact seams (see section 5).
  - Pew run 5.5 = start 1.75 + 2 middles of 1.0 + end 1.75.
  - Shelf runs 11 and 12 = start 1.5 + 8 or 9 middles of 1.0 + end 1.5.
- **`identity_category` enum (proposed):** `broken_masonry`, `web`, `vegetation_or_slime`, `debris_rubble`, `introductory_landmark`, `shelf_bank_segment`, `bone_pile`, `collapsed_furniture`, `books_or_scrolls`, `archival_clutter`, `archive_landmark`, `pew_segment`, `altar_or_ritual_focus`, `candle_cluster`, `ash_accent`, `sigil`, `gothic_vertical_shape`, `chapel_landmark`, `barrel`, `crate`, `rail`, `water_or_slime_edge`, `cliff_or_platform`, `vault_landmark`, `bench`, `recognizable_furniture`, `ritual_detail`, `bounded_hazard_framing`, `dramatic_landmark`, `pillar_column`, `spooky_comedy_detail`.
  - "Debris" and "rubble" share `debris_rubble`, so the high-frequency two-variant rule applies to both.
- **Variants:** each row is one variant. The number after `variant_group` is how many entries that group has.

### 1a. Props, clutter, landmarks and route dressing (35 of 45)

| id | family | identity_category | variant_group (entries) | facing | segment_role | footprint_world_size x, z, h | canvas px | intended_rooms | footprint_reference |
|---|---|---|---|---|---|---|---|---|---|
| `shared_bone_pile_a` | furnishings | bone_pile | bone_pile (2) | either | single | 1, 1, 0.5 | 100x84 | BoneArchive, ChapelOfAsh, FinalRoom | art direction |
| `shared_bone_pile_b` | furnishings | bone_pile | bone_pile (2) | either | single | 1.2, 0.8, 0.3 | 100x72 | BoneArchive, FinalRoom, RuinedEntry | art direction |
| `shared_web_corner_a` | furnishings | web | web (2) | either | single | 1, 1, 1.5 | 100x140 | RuinedEntry, BoneArchive, ChapelOfAsh, FinalRoom | art direction (far corners only; near corners are cutaway) |
| `shared_web_drape_b` | furnishings | web | web (2) | either | single | 1.5, 0.2, 1 | 88x104 | RuinedEntry, BoneArchive, FinalRoom | art direction |
| `shared_rubble_scatter_b` | architecture | debris_rubble | debris_rubble (3) | either | single | 1.5, 1.5, 0.5 | 144x104 | RuinedEntry, LowerVault, FinalRoom | RuinedEntryLayout.RubbleABounds/RubbleBBounds (cluster piece) |
| `shared_candle_cluster_a` | furnishings | candle_cluster | candle_cluster (1) | either | single | 0.8, 0.8, 0.6 | 84x80 | ChapelOfAsh, FinalRoom | art direction |
| `re_landmark_guardian_statue_standing` | architecture | introductory_landmark | d1_guardian (2) | world_x | single | 1.5, 0.5, 2.2 | 100x176 | RuinedEntry | RuinedEntryLayout.D1LandmarkWestDressingBounds |
| `re_landmark_guardian_statue_broken` | architecture | introductory_landmark | d1_guardian (2) | world_x | single | 1.5, 0.5, 1.4 | 100x132 | RuinedEntry | RuinedEntryLayout.D1LandmarkEastDressingBounds |
| `re_broken_masonry_blocks` | architecture | broken_masonry | broken_masonry (1) | either | single | 1.5, 1, 0.8 | 124x112 | RuinedEntry | RuinedEntryLayout.NorthWestClusterDressingBounds |
| `re_roots_and_mushrooms` | furnishings | vegetation_or_slime | vegetation (1) | either | single | 1, 1, 0.6 | 100x88 | RuinedEntry | RuinedEntryLayout.WestWallClusterDressingBounds |
| `re_debris_broken_handcart` | furnishings | debris_rubble | debris_rubble (3) | either | single | 1.5, 1, 0.8 | 124x112 | RuinedEntry | RuinedEntryLayout.RubbleABounds (cluster piece) |
| `re_comedy_thumbs_up_skeleton_hand` | furnishings | spooky_comedy_detail | comedy_re (1) | either | single | 0.5, 0.5, 0.4 | 56x56 | RuinedEntry | art direction |
| `ba_collapsed_reading_table_z` | furnishings | collapsed_furniture | collapsed_furniture (1) | world_z | single | 1, 2, 1.25 | 144x148 | BoneArchive | BoneArchiveLayout.CollapsedFurnitureBA1 |
| `ba_book_and_scroll_stack` | furnishings | books_or_scrolls | books_or_scrolls (1) | either | single | 0.6, 0.6, 0.9 | 64x88 | BoneArchive | art direction |
| `ba_spilled_scroll_basket` | furnishings | archival_clutter | archival_clutter (1) | either | single | 0.8, 0.8, 0.6 | 84x80 | BoneArchive | art direction |
| `ba_landmark_chained_grimoire_lectern` | architecture | archive_landmark | archive_landmark (1) | either | single | 1.5, 1.5, 2 | 144x188 | BoneArchive | art direction |
| `ba_comedy_skull_with_spectacles` | furnishings | spooky_comedy_detail | comedy_ba (1) | either | single | 0.6, 0.6, 0.4 | 64x60 | BoneArchive | art direction |
| `ca_altar_ash_bowl_x` | furnishings | altar_or_ritual_focus | altar (1) | world_x | single | 2, 1, 1.2 | 144x144 | ChapelOfAsh | art direction |
| `ca_ash_heap` | furnishings | ash_accent | ash_accent (1) | either | single | 1, 1, 0.4 | 100x76 | ChapelOfAsh | art direction |
| `ca_sigil_floor_mark` | architecture | sigil | sigil (1) | either | single | 2, 2, 0 | 192x100 | ChapelOfAsh | ChapelOfAshLayout.CentralAisleWidth (4.0) |
| `ca_candelabra_tall` | furnishings | gothic_vertical_shape | gothic_vertical (1) | either | single | 0.6, 0.6, 2 | 64x148 | ChapelOfAsh | art direction |
| `ca_landmark_cracked_bell_frame_x` | architecture | chapel_landmark | chapel_landmark (1) | world_x | single | 2, 1, 2.5 | 144x216 | ChapelOfAsh | art direction |
| `ca_comedy_offering_plate_sock` | furnishings | spooky_comedy_detail | comedy_ca (1) | either | single | 0.5, 0.5, 0.2 | 56x44 | ChapelOfAsh | art direction |
| `lv_iron_rail_x` | hazard_route | rail | rail (2) | world_x | single | 2, 0.2, 1 | 108x116 | LowerVault | NSC-047 rev 4 crossing edge; collision_intent downstream_existing_geometry |
| `lv_iron_rail_z` | hazard_route | rail | rail (2) | world_z | single | 0.2, 2, 1 | 108x116 | LowerVault | NSC-047 rev 4 crossing edge; collision_intent downstream_existing_geometry |
| `lv_sluice_slime_spill` | hazard_route | water_or_slime_edge | slime_edge (1) | either | single | 1.5, 1, 0.8 | 124x112 | LowerVault | NSC-047 rev 4 LV-H1 edge, decorative only |
| `lv_broken_ledge_chunk` | hazard_route | cliff_or_platform | ledge (1) | either | single | 1.5, 1, 0.8 | 124x112 | LowerVault | NSC-047 rev 4 LV-H1 edge, decorative only |
| `lv_landmark_sluice_wheel_gate_x` | architecture | vault_landmark | vault_landmark (1) | world_x | single | 2, 1, 2.5 | 144x216 | LowerVault | art direction |
| `lv_comedy_barrel_striped_socks` | furnishings | spooky_comedy_detail | comedy_lv (1) | either | single | 0.8, 0.8, 1.1 | 84x108 | LowerVault | LowerVaultLayout.WestStoragePile (cluster piece) |
| `fr_bench_x` | furnishings | bench | bench (1) | world_x | single | 2.5, 0.55, 0.7 | 148x116 | FinalRoom | FinalRoomLayout.WestBenchBounds/EastBenchBounds |
| `fr_round_table_with_stools` | furnishings | recognizable_furniture | furniture (1) | either | single | 1.5, 1.5, 0.9 | 144x128 | FinalRoom | art direction |
| `fr_ritual_bone_candle_ring` | furnishings | ritual_detail | ritual_detail (1) | either | single | 1.5, 1.5, 0.3 | 144x96 | FinalRoom | art direction |
| `fr_bone_chain_post` | hazard_route | bounded_hazard_framing | hazard_frame (1) | either | single | 0.4, 0.4, 1.2 | 48x96 | FinalRoom | art direction (placed in rows around the bounded area) |
| `fr_landmark_bone_throne` | architecture | dramatic_landmark | dramatic_landmark (1) | either | single | 2.25, 2.25, 2.4 | 212x244 | FinalRoom | FinalRoomLayout.FinalObstacleBounds (centre piece of the 5x5 obstacle) |
| `fr_comedy_party_hat_skull_cake` | furnishings | spooky_comedy_detail | comedy_fr (1) | either | single | 0.6, 0.6, 0.5 | 64x64 | FinalRoom | art direction |

`placement_role` and `collision_intent` recommendations:
- landmarks: `focal_landmark` / `downstream_review_required`;
- rails, slime spill, ledge and chain post: `route_edge` or `hazard_boundary` / `downstream_existing_geometry`;
- sigil: `background` / `decorative_none`;
- small clutter and comedy: `supporting_cluster` / `decorative_none`;
- bench, altar, table and handcart: `supporting_cluster` / `downstream_review_required`.

### 1b. Furniture runs, storage, rubble and columns moved from NSC-064 by D-2 (10 of 45)

`NSC-078_DECISIONS.md` D-2 (2026-09-17) moved these independently sorted SpriteRenderer props from NSC-064 to NSC-078. They follow the same rules as 1a.

| id | family | identity_category | variant_group (entries) | facing | segment_role | footprint_world_size x, z, h | canvas px | intended_rooms | footprint_reference |
|---|---|---|---|---|---|---|---|---|---|
| `ba_shelf_bank_z_start` | furnishings | shelf_bank_segment | shelf_bank (3) | world_z | start | 1.5, 1.5, 2.5 | 144x216 | BoneArchive | BoneArchiveLayout.ShelfA/B/C |
| `ba_shelf_bank_z_middle` | furnishings | shelf_bank_segment | shelf_bank (3) | world_z | middle | 1.5, 1, 2.5 | 124x204 | BoneArchive | BoneArchiveLayout.ShelfA/B/C |
| `ba_shelf_bank_z_end` | furnishings | shelf_bank_segment | shelf_bank (3) | world_z | end | 1.5, 1.5, 2.5 | 144x216 | BoneArchive | BoneArchiveLayout.ShelfA/B/C |
| `ca_pew_x_start` | furnishings | pew_segment | pew (3) | world_x | start | 1.75, 1.5, 1.25 | 156x152 | ChapelOfAsh | ChapelOfAshLayout.PewFootprints |
| `ca_pew_x_middle` | furnishings | pew_segment | pew (3) | world_x | middle | 1, 1.5, 1.25 | 124x136 | ChapelOfAsh | ChapelOfAshLayout.PewFootprints |
| `ca_pew_x_end` | furnishings | pew_segment | pew (3) | world_x | end | 1.75, 1.5, 1.25 | 156x152 | ChapelOfAsh | ChapelOfAshLayout.PewFootprints |
| `shared_stone_column` | architecture | pillar_column | column (1) | either | single | 1.5, 1.5, 2.5 | 144x216 | ChapelOfAsh, LowerVault | ChapelOfAshLayout.ColumnBounds; LowerVaultLayout.CentralColumnCluster |
| `lv_barrel` | furnishings | barrel | storage (2) | either | single | 0.8, 0.8, 1 | 84x100 | LowerVault | LowerVaultLayout.WestStoragePile/EastStoragePile/NorthWestStorageBar |
| `lv_crate` | furnishings | crate | storage (2) | either | single | 1, 1, 1 | 100x112 | LowerVault | LowerVaultLayout storage piles |
| `shared_rubble_pile_a` | architecture | debris_rubble | debris_rubble (3) | either | single | 2, 2, 1.25 | 192x168 | RuinedEntry | RuinedEntryLayout.RubbleABounds/RubbleBBounds (cluster piece) |

Walls, floors, corners, end caps, wall pilasters, door-jamb transitions and the near-wall cutaway-stub family stay NSC-064 Tilemap sources and aren't listed.

**One header for both blocks, from revision 9.** Until then 1a and 1b carried *different* column sets - 1b inserted `owner` and dropped `intended_rooms` - so `facing` sat at index 4 in one block and index 5 in the other. **A script binding every row to one header misreads the other block as plausible data and never as an error**, which is why three separate counts of the `world_x` entries disagreed (3 and 7 from one script run under each header, 5 then 9 and 8 from two readers matching ids instead of the column). The correct count, binding each row to the header above it, is **ten**. `owner` is dropped because it read `NSC-078` in all ten rows and the sentence above this table already says so; `intended_rooms` is added because it is per-row and load-bearing, and was absent for these ten. **Those ten values are derived from `footprint_reference`** - the rooms whose committed layout names the prop. For a `shared_` entry that is the set with a committed reference, not a bar on reuse elsewhere; widening it is an art-direction change, not a transcription.

### 1c. AC-002 coverage check

| Room | Noun | Entries |
|---|---|---|
| Ruined Entry | broken masonry | `re_broken_masonry_blocks` |
| | webs | `shared_web_corner_a`, `shared_web_drape_b` |
| | vegetation or slime | `re_roots_and_mushrooms` |
| | debris | `re_debris_broken_handcart`, `shared_rubble_scatter_b`, `shared_rubble_pile_a` |
| | introductory landmark | `re_landmark_guardian_statue_standing`, `re_landmark_guardian_statue_broken` (flanking D1) |
| | comedy | `re_comedy_thumbs_up_skeleton_hand` |
| Bone Archive | shelf-bank segments | `ba_shelf_bank_z_start`, `ba_shelf_bank_z_middle`, `ba_shelf_bank_z_end` |
| | bone piles | `shared_bone_pile_a`, `shared_bone_pile_b` |
| | collapsed furniture | `ba_collapsed_reading_table_z` |
| | books or scrolls | `ba_book_and_scroll_stack` |
| | archival clutter | `ba_spilled_scroll_basket` |
| | archive landmark | `ba_landmark_chained_grimoire_lectern` |
| | comedy | `ba_comedy_skull_with_spectacles` |
| Chapel of Ash | pews | `ca_pew_x_start`, `ca_pew_x_middle`, `ca_pew_x_end` |
| | altar or ritual focus | `ca_altar_ash_bowl_x` |
| | candle cluster | `shared_candle_cluster_a` |
| | ash accent | `ca_ash_heap` |
| | sigil | `ca_sigil_floor_mark` |
| | gothic vertical shape | `ca_candelabra_tall` |
| | chapel landmark | `ca_landmark_cracked_bell_frame_x` |
| | comedy | `ca_comedy_offering_plate_sock` |
| Lower Vault | barrels, crates | `lv_barrel`, `lv_crate` |
| | rails | `lv_iron_rail_x`, `lv_iron_rail_z` |
| | water or slime edge | `lv_sluice_slime_spill` |
| | cliff or platform | `lv_broken_ledge_chunk` |
| | vault landmark | `lv_landmark_sluice_wheel_gate_x` |
| | comedy | `lv_comedy_barrel_striped_socks` |
| Final Room | benches | `fr_bench_x` |
| | recognizable furniture | `fr_round_table_with_stools` |
| | ritual detail | `fr_ritual_bone_candle_ring` |
| | candle cluster | `shared_candle_cluster_a` |
| | bounded-hazard framing | `fr_bone_chain_post` |
| | dramatic landmark | `fr_landmark_bone_throne` |
| | comedy | `fr_comedy_party_hat_skull_cake` |

High-frequency rules:
- rubble: 3 entries;
- bone pile: 2;
- web: 2.

Every room has one comedy detail. Nothing uses lava, chasm or horn trim (D-3). The final throne uses violet ritual light and **no gold**, so the final door's gold rim stays the one escape accent.

---

## 2. File names and folder layout

Names:
- lowercase ASCII, no provider IDs or timestamps;
- the catalog `id` equals the file stem;
- the room prefix is `shared_`, `re_`, `ba_`, `ca_`, `lv_` or `fr_`;
- a `_x`/`_z` suffix only when facing isn't `either`;
- a `_start`/`_middle`/`_end` suffix only for segments.

```text
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props.meta
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/PropCatalog.json            (+ .json.meta)
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source.meta
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/furnishings_inventory.json   (+ .json.meta)
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/architecture_inventory.json  (+ .json.meta)
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/hazard_route_inventory.json  (+ .json.meta)
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected.meta
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings.meta
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/<id>.png   (+ <id>.png.meta)
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture.meta
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/<id>.png  (+ <id>.png.meta)
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/hazard_route.meta
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/hazard_route/<id>.png  (+ <id>.png.meta)
Docs/Art/Environment/Props/Raw/<family>/<id>.png                                    (raw selected export, no .meta)
```

- **Raw exports go under `Docs/`, not `Assets/`** (a change from the wizard precedent, which keeps `raw/` under `Assets`). Under `Assets` every raw PNG becomes a second imported texture, and with a GUID-only stub `.meta` it imports as a cubemap in Unity 6000.1.8f1. Under `Docs` they need no `.meta` at all.
- **Commit a raw file for every selected PNG,** even when it is byte-identical (`create_object_pro_flash` renders the exact canvas, so crop/pad should be rare). That keeps the file list exact for the scope validator. The inventory records `raw_sha256`, `selected_sha256` and any lossless crop/pad offset.
- **Masked repairs:** when a selected PNG was repaired with a PixelLab masked inpaint, record the repaired area as `repair_mask` in the family inventory: a list of axis-aligned rectangles (x, y, width, height) in selected-image pixels whose union covers every repaired pixel (AC-001, AC-004). No mask PNG is committed, because the contract claims no such resource. The validator decodes both PNGs and proves that every selected pixel outside the recorded rectangles equals the raw pixel at the recorded `crop_pad_offset_px`. Keep each rectangle tight: an oversized rectangle weakens the proof.
- **Rejected candidates live on a separate local branch**, never in the task's candidate commit.
  - Commit them from a clone of `main`, with an `.invalid` identity, on the branch `art-rejects/NSC-078`, as `Docs/Art/Environment/Candidates/NSC-078/<id>__rNN.png` (attempt number, no provider IDs).
  - The Game Agent fetches that branch into the canonical repository.
  - Never merge it into `main`, never push it without Vincent, and never delete it.
  - The family inventory records each reject's SHA-256, its prompt and the rejects-branch commit.
- **Pilot sources** are ordinary family entries (section 3); they get no separate file names.

The exact per-entry list for `exclusive_resources` (45 entries x 3 files) is in the appendix.

---

## 3. Style-lock pilot for Vincent's first pick (5 sources)

AC-003 needs a freestanding prop, a repeatable or connected source, and a hazard or route-edge source. This set also locks the palette for bone, wood, stone and iron and the rule that candle light is the brightest value.

| # | id | Why it is in the pilot |
|---|---|---|
| 1 | `shared_bone_pile_a` | High-frequency freestanding clutter; bone palette; small-prop readability at 64 PPU |
| 2 | `ba_collapsed_reading_table_z` | Wood furniture; world_z facing test on a committed footprint (BA1); medium size |
| 3 | `ca_candelabra_tall` | Tall gothic vertical; warm candle flames as the brightest pixels; thin-shape readability |
| 4 | `re_broken_masonry_blocks` | Violet-slate stone that must sit beside NSC-064 walls; architecture palette lock |
| 5 | `lv_iron_rail_x` | Connected route-edge source: two copies butted in the sheet prove the post-and-panel joint; no walkable claim |

Pilot sheet panels (AC-003):
- native pixels;
- world scale beside the wizard;
- gameplay-camera density.

**Wizard-proxy scaling rule.** Density option B puts the wizard in a 2x2-world-unit camera-facing box: 135 px at 1080p, 180 px at 1440p.
- In the world-scale and gameplay-camera panels, draw the four committed south-east standing wizard sprites (`Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/<key>/selected/standing/south-east.png`, 180x180) scaled into that box with nearest-neighbour sampling: 0.75x at 1080p, 1.0x at 1440p.
- Use the committed 128x128 remake instead, at 1.0546875x at 1080p, once it exists on `main`.
- Props draw at 64 px per world unit in the same panels (1.0546875x at 1080p), beside the 3.0-world-unit door-opening proxy.
- Never draw the wizard at 180 PPU (0.375x).

---

## 4. Prompts, tool settings and PixelLab estimate

### 4a. Global clause (append to every description; Pro Flash has no outline or shading parameters)

```text
dark-but-cute horror-comedy dungeon prop, chunky readable proportions, low top-down isometric view, single color black outline, basic shading, medium detail, crisp pixel art with no anti-aliasing and no gradients, dark spooky dungeon color palette of deep plum and teal-black shadows with warm lantern-glow highlights, soft key light from the upper left, transparent background, no text, no letters, no runes, no floor shadow, no other objects
```

- **Light direction:** "upper left" is a proposal. Confirm it against the door family B and wizard highlights in the pilot, then record it in `NSC-078_STYLE_LOCK.md`.
- **Materials:**
  - stone: "violet slate and mauve stone with lilac edge highlights and mossy green-grey accents; cold violet and mauve purple, no tan, no beige, no warm brown stone";
  - wood: "dark red-brown wood with iron studs";
  - iron: "cold blue-grey wrought iron with dull orange-brown rust patches, hard metal not timber, no wood, no wood grain, no warm brown planks". Added in revision 9 and tested on `lv_iron_rail_z` against a baseline already on disk, one variable changed: pixels desaturated enough to read as bare metal went 3.3% to 58.2%, and the warm orange-brown band 7.1% to 27.1% - the warm share rising is the rust in the clause working, not the palette drifting. One prop, one call: strong on a rail, untested on every other iron entry;
  - bone: "cream bone, not pure white";
  - candles: "warm amber flames as the brightest pixels";
  - webs: "chunky 2-pixel pale grey-lilac strands" (1 px strands vanish at game scale).
- **Facing clauses:** world_x = "long side runs diagonally from upper-left to lower-right"; world_z = "long side runs diagonally from lower-left to upper-right".

### 4b. Subject clauses

| id | Subject clause | Production note |
|---|---|---|
| `shared_bone_pile_a` | small heap of cream bones with one cracked skull on top |  |
| `shared_bone_pile_b` | low scatter of cream ribs and long bones, no skull |  |
| `shared_web_corner_a` | thick chunky spider web spanning a right-angled corner, the web alone and nothing behind it, no wall, no bricks, no stone, no floor, no architecture | Revision 9, finding 4. The committed clause said "filling a stone wall corner" and the generation drew a whole stone wall and floor; this tail is the repair that then worked. |
| `shared_web_drape_b` | sagging chunky spider web drape, its top edge stretched wide and its middle sagging low, the web alone and nothing behind it, no wall, no bricks, no stone, no floor, no architecture, no posts, no anchors | Revision 9, finding 4. Generated from this text: keeper, no invented anchors. |
| `shared_rubble_scatter_b` | low scatter of broken violet-slate stones with one snapped wooden plank |  |
| `shared_candle_cluster_a` | five melted cream candles of different heights on a small wax puddle, warm amber flames |  |
| `re_landmark_guardian_statue_standing` | weathered stone guardian statue on a square plinth, chunky rounded helmet, cracked shield held forward, moss on its shoulders, long side runs diagonally from upper-left to lower-right | Batch 1 keeper, accepted on its merits as a landmark - **never judged on its facing**, and the tilt/mirror-IoU test cannot judge it, because that test only works on long thin props. It and the broken statue are a coupled pair and must agree. |
| `re_landmark_guardian_statue_broken` | weathered stone guardian statue toppled and broken on its square plinth, chunky rounded helmet, cracked shield, moss on the fallen pieces, its helmeted head rolled beside it, moss in the cracks, long side runs diagonally from upper-left to lower-right | Make it from the approved standing statue with `edit_image_pro_flash` (reference method) or `create_object_state` so the pair matches. **Moved here from the subject clause in revision 9**, which is the only reason this column exists: as clause text those two tool names, the backticks and the bold markers were assembled verbatim into the prompt, mid-sentence between the subject and the material clause. The clause also gained the `world_x` facing phrase it never had and a full restatement of the statue, so it can be sent standalone. |
| `re_broken_masonry_blocks` | tumbled carved violet-slate masonry blocks lying flat and scattered; nothing standing, nothing upright, no curved shapes | Clause unchanged and now **tested** - see D-5. Dropping the arch noun and adding "no curved shapes" produced rubble with no arch and no surviving curve on the first attempt. |
| `re_roots_and_mushrooms` | tangle of dark roots with small pale glowing mushrooms and mossy green-grey tufts |  |
| `re_debris_broken_handcart` | broken wooden handcart tipped on its side with a snapped wheel and spilled planks |  |
| `re_comedy_thumbs_up_skeleton_hand` | tiny cute skeleton hand poking out of a pile of pebbles giving a cheerful thumbs-up |  |
| `ba_collapsed_reading_table_z` | collapsed dark wooden reading table with one snapped leg, open books sliding off, long side runs diagonally from lower-left to upper-right |  |
| `ba_book_and_scroll_stack` | tall wobbly stack of old leather books topped with rolled scrolls |  |
| `ba_spilled_scroll_basket` | tipped wicker basket spilling rolled parchment scrolls |  |
| `ba_landmark_chained_grimoire_lectern` | giant chained grimoire lying open on a carved bone lectern, faint violet glow between its pages, chains hanging down and pooling loosely at its base | Revision 9, finding 4. Generated from this text: keeper, chains pool at the base, no floor drawn. |
| `ba_comedy_skull_with_spectacles` | small cute skull wearing round reading spectacles, resting on an open book |  |
| `ca_altar_ash_bowl_x` | low violet-slate stone altar holding a wide bowl of pale grey ash and two small candles, abstract carved geometric pattern, long side runs diagonally from upper-left to lower-right | **Carries the same "pale grey ash" phrasing that made `ca_ash_heap` read as a snow pile** (finding 3). The Art Director re-cast `ca_ash_heap` and did not extend that to this entry, and what an altar bowl should read as is their call, not this plan's - so the clause is left as written and flagged here. Check the ash value on the first generation rather than discovering it in a contact sheet. Two clauses in the 45 carry the phrase; these are both. |
| `ca_ash_heap` | soft heap of dark charcoal-grey ash with black burnt chunks, no fire, no embers | Revision 9, finding 3. "Pale grey" against the deep-plum palette read as a snow pile - the brightest value in the run, and the model drew what the plan asked for. Re-cast dark it works: mean luminance 133.2 to 71.6, peak 222.5 to 154.0, saturation flat at 0.07 to 0.08, so it stayed neutral grey and only moved down in value. |
| `ca_sigil_floor_mark` | ritual circle of abstract geometric lines and dots in faded chalk-lilac, drawn as a flat foreshortened ellipse seen from directly above, the painted marks alone with nothing beneath them, no stone slab, no flagstones, no floor tiles, no ground plane | Revision 9, finding 4, and the one that could not simply have the noun deleted: this prop genuinely **is** a floor marking, so stripping the setting carelessly makes the model draw an upright ring instead of a flat one. The wording keeps the flatness and refuses the slab. **Not yet generated** - send it alone, so a failure is attributable to it. |
| `ca_candelabra_tall` | tall thin wrought-iron gothic candelabra with pointed finials holding five cream candles with warm amber flames |  |
| `ca_landmark_cracked_bell_frame_x` | tall dark wooden gothic bell frame with a pointed-arch top holding a large cracked bell, long side runs diagonally from upper-left to lower-right |  |
| `ca_comedy_offering_plate_sock` | small offering plate holding one lonely striped sock and a button |  |
| `lv_iron_rail_x` | short rusty iron railing section, two square posts joined by two bars with a post at each end, long side runs diagonally from upper-left to lower-right |  |
| `lv_iron_rail_z` | short rusty iron railing section, two square posts joined by two bars with a post at each end, long side runs diagonally from lower-left to upper-right | Revision 9, finding 5. The committed clause was "the same railing section" with no restatement, so sent standalone it described nothing; this is `lv_iron_rail_x`'s subject in full with the `world_z` facing. |
| `lv_sluice_slime_spill` | broken stone sluice pipe mouth spilling murky green-grey slime into a small puddle |  |
| `lv_broken_ledge_chunk` | cracked violet-slate stone ledge fragment with a chipped edge and dripping moss |  |
| `lv_landmark_sluice_wheel_gate_x` | large rusty sluice gate, a big iron valve wheel on a stone frame beside a jammed wooden gate with trickles of water, long side runs diagonally from upper-left to lower-right |  |
| `lv_comedy_barrel_striped_socks` | wooden barrel with two skeleton legs in striped socks sticking out of the top |  |
| `fr_bench_x` | sturdy dark wooden bench with carved bone-shaped legs, long side runs diagonally from upper-left to lower-right |  |
| `fr_round_table_with_stools` | round dark wooden table with a candle stub and two small stools |  |
| `fr_ritual_bone_candle_ring` | flat ring of small cream bones and tiny violet candles arranged in a foreshortened ellipse seen from above, the ring alone with nothing beneath it, no floor, no slab, no tiles, no ground | Revision 9, finding 4. The geometry it was reaching for - seen from above, lying flat - is kept; only the setting noun invited the slab. Generated from this text: keeper, no floor slab. |
| `fr_bone_chain_post` | short bone-and-iron post topped with a small skull, a sagging chain end hanging from it |  |
| `fr_landmark_bone_throne` | huge ominous throne of stacked violet-slate stone and cream bones with a tall pointed back, violet ritual candles on its steps, empty seat, no gold |  |
| `fr_comedy_party_hat_skull_cake` | cute skull wearing a tiny striped party hat beside a small cake with one candle |  |

| id | Subject clause | Production note |
|---|---|---|
| `ba_shelf_bank_z_start` | first section of a tall dark wooden archive shelf packed with old books and bone bookends, a thick upright post at each end, long side runs diagonally from lower-left to upper-right | Three-segment run: see D-7. `world_z`, the reliable diagonal. |
| `ba_shelf_bank_z_middle` | middle section of the same tall dark wooden archive shelf packed with old books and bone bookends, a single upright post at its upper-right end only, long side runs diagonally from lower-left to upper-right | Three-segment run: see D-7. |
| `ba_shelf_bank_z_end` | last section of the same tall dark wooden archive shelf packed with old books and bone bookends, a thick capped upright post at its upper-right end only, long side runs diagonally from lower-left to upper-right | Three-segment run: see D-7. |
| `ca_pew_x_start` | first section of a dark wooden chapel pew with a carved backrest, carved end posts at both ends, long side runs diagonally from upper-left to lower-right | Three-segment run on the unreliable `world_x` diagonal: **the worst facing exposure in the plan**, and none of the three has been attempted. See D-7 and the re-roll budget in D-5. |
| `ca_pew_x_middle` | middle section of the same dark wooden chapel pew with a carved backrest, a single upright post at its lower-right end only, long side runs diagonally from upper-left to lower-right | Three-segment run on `world_x`: see D-7. |
| `ca_pew_x_end` | last section of the same dark wooden chapel pew with a carved backrest, a carved end post at its lower-right end only, long side runs diagonally from upper-left to lower-right | Three-segment run on `world_x`: see D-7. |
| `shared_stone_column` | thick violet-slate gothic column with a cracked base and a bone-carved capital |  |
| `lv_barrel` | banded dark wooden barrel with iron hoops |  |
| `lv_crate` | iron-cornered dark wooden crate |  |
| `shared_rubble_pile_a` | large heap of broken violet-slate blocks and dust |  |

**Segment joints** (post-and-panel):
- A run is laid from its world -Z end (shelves) or -X end (pews) toward +Z or +X: start, then middles, then end.
- Every joint carries exactly one post, from the segment on the lower-coordinate side. The start carries posts at both ends; the middle and end carry a post at their +Z or +X end.
- No seam needs pixel-exact matching.
- On screen, +Z runs toward the upper right and +X toward the lower right.

### 4c. Tool settings (`create_object_pro_flash`)

- `description`: subject clause + global clause.
- `n_directions: 1`, `view: "low top-down"`.
- `width`/`height`: the canvas from section 1 (multiples of 4, at most 256).
- `seed`: fixed per entry and recorded; `name`: the catalog id.
- **Pilot:** no `style_image`.
- **Families after Vincent approves the pilot:**
  - `style_image: {source_image_id: <approved pilot image id>, usage_description: "match this prop's outline weight, shading, palette and pixel density; do not copy its shape"}`;
  - `style_options: {color_palette: true, outline: true, detail: true, shading: true}`.
- **Style image size:** it must fit the target canvas without resizing (an oversized one fails validation before spending). For smaller canvases, pass a lossless crop of the pilot source that fits, and record the crop box and SHA-256.
- **Style image source:** from the same family where possible (stone from the masonry, wood from the table, bone from the bone pile, iron from the rail).
- **After each result:** download with `get_object` immediately; results expire after about 8 hours.
- **Repairs:** see section 5.

### 4d. Generation estimate for Vincent's spend go

- **Read every number in this section as a printed estimate, not a spend.** Printed per-call costs can run well under the meter, and the gap is not a fixed rate: the NSC-095 wizard run settled at **132 generations on the meter against 97 printed, about 36% more**, with no other PixelLab work on the account to explain it, while a later batch the same day measured **70 against 70.5 printed**. So multiply the table below by roughly 1.4 when asking for a cap, to buy headroom, but treat the difference as something each run measures rather than a rate to rely on: the pilot is about 95 rather than 68, and all 45 entries about 800 rather than 581. Count a task's own recorded calls against its cap and read `get_balance` with an empty queue as the cross-check, and derive both totals from the recorded readings rather than by hand; a printed-versus-meter gap is expected and is not a defect.
- **Unit costs:** provisional Pro Flash quotes from 2026-09-16 were 5 at up to 64 px and 6 at up to 128 px. Canvases above 128 px are assumed 8 (unquoted). Get a free `get_pro_flash_capabilities` quote per size before asking.
- **Attempts:** 1.5 per ordinary entry, 2 per segment, 3 per landmark.

| Step | Entries | `create_object_pro_flash` | `create_image_pixflux` (1 per attempt) |
|---|---|---|---|
| Style-lock pilot (5 sources, 2 attempts each) | 5 | about 68 | about 10 |
| Furnishings family (after pilot) | 26 | about 285 | about 42 |
| Architecture family (after pilot) | 10 | about 192 | about 24 |
| Hazard/route family (after pilot) | 4 | about 36 | about 6 |
| **Total** | **45** | **about 581** | **about 82** |

- **Contract tool:** the contract's tool is `create_object_pro_flash`.
- **Cheaper tool:** `create_image_pixflux` (1 generation; forced palette through `color_image`, outline, shading and view options) made the approved Lantern Wraith wisp A. Where the contract and Vincent allow it, a 5-generation Pixflux run of the same 5 pilot sources, with the pilot palette as `color_image`, would show whether the whole pack could cost about 82 instead of about 581.
- `create_1_direction_object` batches 16 small objects per call, but only offers `top-down`/`sidescroller` views; not recommended for the low top-down look.
- **Spend gate:** none of this is authorized. Vincent's spend go is separate from the contract.

---

## 5. Rules this plan depends on

- **Density (D-1).** Props draw at about 64 px per world unit, the same as the option-B characters.
  - Props are displayed camera-facing: PixelLab low top-down art already contains its projection, and on world-aligned planes it is squeezed and sheared.
  - `facing` picks which drawing to use; it never rotates the sprite.
  - NSC-064 states its own real texel density (its candidate kit is `tile_size 32` with 52x58 pieces and a 26 px stride), so walls and props can be checked against each other.
- **Ownership (D-2).** NSC-078 owns every independently sorted SpriteRenderer prop, all 45 rows. NSC-064 keeps the Tilemap pieces: floors, walls, corners, end caps, wall pilasters, door-jamb transitions, cutaway stubs.
- **Lower Vault (D-3).** Hazard and route art is decorative. It never implies walkable ground, safe islands, crossings or elevation beyond the committed NSC-047 revision 4 geometry. Lava, chasm and horn trim stay FutureExpansion vocabulary.
- **Processing (D-4).**
  - Only lossless crop/pad, recorded against the committed raw export.
  - Repairs go through PixelLab only: masked inpaint, preferably `inpaint_image_pro_flash` (byte-exact outside the mask, about 6 generations), with the repaired area recorded as `repair_mask` rectangles in the family inventory; PixelLab's own `reduce_colors`; or regeneration.
  - No local pixel edits, scripted palette reduction or seam repair. Post-and-panel segments need no seams.
- **Re-rolls (D-5).** *Re-rolls pin both halves, not the half that failed.* When a generation is right in one respect and wrong in another, the re-roll prompt must re-state what was already correct as well as what is being fixed. The masonry re-roll pinned the silhouette alone and the palette drifted from violet slate to warm tan; the next pinned silhouette and palette together and produced Vincent's pick. A re-roll prompt that names only the defect is how a fix trades one reject for another.
  - **`re_broken_masonry_blocks` is TESTED as written, and the UNTESTED mark added in revision 7 is withdrawn.** Dropping the arch noun and adding "no curved shapes" produced rubble with no arch and no surviving curve, first attempt, keeper. Round 3's proven prompt kept the noun and still produced a voussoir curve, so the noun was the cause and removing it was the fix.
  - **`world_x` facings are seed-sensitive, not unreachable - budget re-rolls and measure the tilt.** A strict single-variable test, seed 500 on both sides and one phrase differing, gives tilt -0.949 px/row for `world_z` and +0.850 for `world_x`: near-perfect opposite tilts, so **the committed facing clauses are the ones that work and neither needs rewriting.** But `_z` rendered diagonal at both seeds tried and `_x` at one of three, so every `world_x` entry needs two or three attempts budgeted and the tilt of each result measured rather than assumed. A report that the `_x` diagonal was unreachable by prompt was **withdrawn**: its controlled pair had run at two different seeds, so two variables moved and were reported as one. Do not re-derive it.
- **Clause text is what the asset depicts; method goes in the production-note column (D-6).**
  The subject-clause column is assembled into the generator prompt **verbatim, with no sanitising
  whatever**, so everything in it is drawn: markdown emphasis, backticks and tool names are prompt
  text. **Only column 2 of section 4b is assembled**; column 3 is for readers and is never sent.
  - Until revision 9 the clause table had two columns and therefore **nowhere to record a per-entry
    method note**, so the one entry that needed one put it in the clause -
    `re_landmark_guardian_statue_broken` carried about 110 characters of operator instruction. The
    third column exists so the next author has somewhere to put it. **Counted before it was called a
    class: 1 of the 45 clause rows and 1 of the 35 assembled prompts in that run's `call_table.json`;
    the global clause and all material clauses were clean.**
  - **A clause must name its subject completely enough to be drawn with no other clause in hand.**
    "The same X" is not the defect - **a missing restatement is**. Six of the 45 clauses say "the
    same"; four of them (`ba_shelf_bank_z_middle`/`_end`, `ca_pew_x_middle`/`_end`) then restate the
    subject in full and are healthy. The two that did not are repaired in revision 9.
  - **Name what the prop is, including its own parts; never name a surface, room feature or anchor
    that the prop is not.** A prop told its setting draws its setting: `shared_web_corner_a` was told
    it filled a stone wall corner and drew a whole stone wall and floor. **Five of the 45 clauses did
    this and all five are repaired in revision 9**; a further six name another part of the same prop
    (the statue's own head, the skull's book, the sluice's puddle) and are correct - that is the
    distinction, not a list of forbidden words. When a value instruction needs a comparison, write a
    bare value: "darker than the ground it sits on" walks straight back into this.
- **A multi-segment run is one lineage, not three lucky generations (D-7).**
  `ba_shelf_bank_z_start`/`_middle`/`_end` and `ca_pew_x_start`/`_middle`/`_end` must read as **one
  piece of furniture**: the same tilt direction, the same post geometry at the joint, the same
  palette and the same drawn height. **Three segments each re-rolled independently until it happens
  to render will not match each other**, so the run is produced from **one approved source segment**
  with the other two derived from it, and is **judged as a run** rather than segment by segment.
  - This is not the seam rule. AC-005's "no pixel-exact seam" is about how joints meet, and
    post-and-panel construction already settles that; it does **not** say the segments may be
    generated independently.
  - **The pew run is the exposure.** All three segments are `world_x`, the diagonal that rendered at
    one of three seeds tried, and none of the three has ever been attempted - so it needs the re-roll
    budget of D-5 *and* the single lineage of this rule. Rotating one segment is a candidate
    mechanism and is **untested on a tiling run**: the Art Director picks the mechanism, this rule
    sets the bar it has to meet.
- **Style inputs (AC-001).** The pilot uses text prompts only. Family acquisition may pass `style_image`/`color_image` only from Vincent-approved pilot sources, recorded by SHA-256. R01-R17 and any franchise art are never PixelLab inputs.
- **Wizard proxy (AC-003).** See section 3.
- **Who executes:** the Art Director Agent session, under the art bible and `nsc-art-director-guide.md` section 1. Unity import steps (the importer postprocessor and the `.meta` files after import) are run by the Game Agent's `unity-runner`; the Art Director can't run Unity.

---

---

## Appendix: exact per-entry files (45 entries x 3 files)

Folder `.meta` files, inventories, the catalog, docs, contact sheets and scripts are listed in section 2 and the contract. Masks for masked repairs are named in the contract when used.

### furnishings (29 entries)

```text
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_book_and_scroll_stack.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_book_and_scroll_stack.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ba_book_and_scroll_stack.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_collapsed_reading_table_z.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_collapsed_reading_table_z.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ba_collapsed_reading_table_z.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_comedy_skull_with_spectacles.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_comedy_skull_with_spectacles.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ba_comedy_skull_with_spectacles.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_shelf_bank_z_end.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_shelf_bank_z_end.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ba_shelf_bank_z_end.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_shelf_bank_z_middle.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_shelf_bank_z_middle.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ba_shelf_bank_z_middle.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_shelf_bank_z_start.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_shelf_bank_z_start.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ba_shelf_bank_z_start.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_spilled_scroll_basket.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ba_spilled_scroll_basket.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ba_spilled_scroll_basket.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_altar_ash_bowl_x.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_altar_ash_bowl_x.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ca_altar_ash_bowl_x.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_ash_heap.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_ash_heap.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ca_ash_heap.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_candelabra_tall.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_candelabra_tall.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ca_candelabra_tall.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_comedy_offering_plate_sock.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_comedy_offering_plate_sock.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ca_comedy_offering_plate_sock.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_pew_x_end.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_pew_x_end.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ca_pew_x_end.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_pew_x_middle.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_pew_x_middle.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ca_pew_x_middle.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_pew_x_start.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/ca_pew_x_start.png.meta
Docs/Art/Environment/Props/Raw/furnishings/ca_pew_x_start.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/fr_bench_x.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/fr_bench_x.png.meta
Docs/Art/Environment/Props/Raw/furnishings/fr_bench_x.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/fr_comedy_party_hat_skull_cake.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/fr_comedy_party_hat_skull_cake.png.meta
Docs/Art/Environment/Props/Raw/furnishings/fr_comedy_party_hat_skull_cake.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/fr_ritual_bone_candle_ring.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/fr_ritual_bone_candle_ring.png.meta
Docs/Art/Environment/Props/Raw/furnishings/fr_ritual_bone_candle_ring.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/fr_round_table_with_stools.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/fr_round_table_with_stools.png.meta
Docs/Art/Environment/Props/Raw/furnishings/fr_round_table_with_stools.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/lv_barrel.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/lv_barrel.png.meta
Docs/Art/Environment/Props/Raw/furnishings/lv_barrel.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/lv_comedy_barrel_striped_socks.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/lv_comedy_barrel_striped_socks.png.meta
Docs/Art/Environment/Props/Raw/furnishings/lv_comedy_barrel_striped_socks.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/lv_crate.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/lv_crate.png.meta
Docs/Art/Environment/Props/Raw/furnishings/lv_crate.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/re_comedy_thumbs_up_skeleton_hand.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/re_comedy_thumbs_up_skeleton_hand.png.meta
Docs/Art/Environment/Props/Raw/furnishings/re_comedy_thumbs_up_skeleton_hand.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/re_debris_broken_handcart.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/re_debris_broken_handcart.png.meta
Docs/Art/Environment/Props/Raw/furnishings/re_debris_broken_handcart.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/re_roots_and_mushrooms.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/re_roots_and_mushrooms.png.meta
Docs/Art/Environment/Props/Raw/furnishings/re_roots_and_mushrooms.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/shared_bone_pile_a.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/shared_bone_pile_a.png.meta
Docs/Art/Environment/Props/Raw/furnishings/shared_bone_pile_a.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/shared_bone_pile_b.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/shared_bone_pile_b.png.meta
Docs/Art/Environment/Props/Raw/furnishings/shared_bone_pile_b.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/shared_candle_cluster_a.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/shared_candle_cluster_a.png.meta
Docs/Art/Environment/Props/Raw/furnishings/shared_candle_cluster_a.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/shared_web_corner_a.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/shared_web_corner_a.png.meta
Docs/Art/Environment/Props/Raw/furnishings/shared_web_corner_a.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/shared_web_drape_b.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings/shared_web_drape_b.png.meta
Docs/Art/Environment/Props/Raw/furnishings/shared_web_drape_b.png
```

### architecture (11 entries)

```text
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/ba_landmark_chained_grimoire_lectern.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/ba_landmark_chained_grimoire_lectern.png.meta
Docs/Art/Environment/Props/Raw/architecture/ba_landmark_chained_grimoire_lectern.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/ca_landmark_cracked_bell_frame_x.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/ca_landmark_cracked_bell_frame_x.png.meta
Docs/Art/Environment/Props/Raw/architecture/ca_landmark_cracked_bell_frame_x.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/ca_sigil_floor_mark.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/ca_sigil_floor_mark.png.meta
Docs/Art/Environment/Props/Raw/architecture/ca_sigil_floor_mark.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/fr_landmark_bone_throne.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/fr_landmark_bone_throne.png.meta
Docs/Art/Environment/Props/Raw/architecture/fr_landmark_bone_throne.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/lv_landmark_sluice_wheel_gate_x.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/lv_landmark_sluice_wheel_gate_x.png.meta
Docs/Art/Environment/Props/Raw/architecture/lv_landmark_sluice_wheel_gate_x.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/re_broken_masonry_blocks.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/re_broken_masonry_blocks.png.meta
Docs/Art/Environment/Props/Raw/architecture/re_broken_masonry_blocks.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/re_landmark_guardian_statue_broken.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/re_landmark_guardian_statue_broken.png.meta
Docs/Art/Environment/Props/Raw/architecture/re_landmark_guardian_statue_broken.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/re_landmark_guardian_statue_standing.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/re_landmark_guardian_statue_standing.png.meta
Docs/Art/Environment/Props/Raw/architecture/re_landmark_guardian_statue_standing.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/shared_rubble_pile_a.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/shared_rubble_pile_a.png.meta
Docs/Art/Environment/Props/Raw/architecture/shared_rubble_pile_a.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/shared_rubble_scatter_b.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/shared_rubble_scatter_b.png.meta
Docs/Art/Environment/Props/Raw/architecture/shared_rubble_scatter_b.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/shared_stone_column.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/architecture/shared_stone_column.png.meta
Docs/Art/Environment/Props/Raw/architecture/shared_stone_column.png
```

### hazard_route (5 entries)

```text
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/hazard_route/fr_bone_chain_post.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/hazard_route/fr_bone_chain_post.png.meta
Docs/Art/Environment/Props/Raw/hazard_route/fr_bone_chain_post.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/hazard_route/lv_broken_ledge_chunk.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/hazard_route/lv_broken_ledge_chunk.png.meta
Docs/Art/Environment/Props/Raw/hazard_route/lv_broken_ledge_chunk.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/hazard_route/lv_iron_rail_x.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/hazard_route/lv_iron_rail_x.png.meta
Docs/Art/Environment/Props/Raw/hazard_route/lv_iron_rail_x.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/hazard_route/lv_iron_rail_z.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/hazard_route/lv_iron_rail_z.png.meta
Docs/Art/Environment/Props/Raw/hazard_route/lv_iron_rail_z.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/hazard_route/lv_sluice_slime_spill.png
Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/hazard_route/lv_sluice_slime_spill.png.meta
Docs/Art/Environment/Props/Raw/hazard_route/lv_sluice_slime_spill.png
```
