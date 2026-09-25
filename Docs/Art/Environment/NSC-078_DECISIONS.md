# NSC-078 prop art design decisions (final)

GER Orchestrator (Claude), 2026-09-17, deciding questions 6-9 that Vincent delegated on 2026-09-15, with the Art Director Agent's plan. Sources:
- GER packet `20260914-065051-NSC-078`;
- `C:\nscrev\reports\ger-overnight-20260914.md`, questions 6-9;
- the brief `briefs\props-078.md`;
- the Art Director plan `briefs\props-078-art-director-plan.md` (2026-09-17);
- Vincent's 2026-09-16 pixel-density decision B (art-director guide, section 11 item 1).

## D-1. Texel density
- **64 pixels per world unit** for props and architecture, the same target as characters under decision B.
- **Props display camera-facing.** PixelLab low top-down art already contains its projection; on a world-aligned plane it is squeezed and sheared. The downstream Unity owner sets that up (INT-003).
- **NSC-064's PPU.** NSC-064 must state and verify its real PPU in its own revision. Its candidate is a 32 px kit with 52x58 pieces and a 26 px stride.

## D-2. Ownership between NSC-064 and NSC-078 (changed on the Art Director's advice)
- **NSC-064:** Tilemap architecture only, meaning floors, straight walls, corners, end caps, wall pilasters and the near-wall cutaway-stub family. It also owns `Assets/NoSafeCircle/DoorPrototype/Art/Environment.meta` and publishes its inventory path and schema in its own revision.
- **NSC-078:** every independently sorted SpriteRenderer prop, including shelf-bank segments, pew segments, the stone column, barrels, crates and rubble piles. These are made with `create_object_pro_flash`, which NSC-064's `create_building_kit` can't produce, and the GDD's hybrid architecture puts props on SpriteRenderers. The Art Director plan's section 1b rows move to NSC-078 unchanged, giving 45 entries.
- **Dependency kept.** NSC-078 still depends on NSC-064, so the stone palette and density lock against the approved wall kit, and the shared `Art/Environment.meta` exists first.
- **Follow-up.** NSC-064 needs its own owner revision (Tilemap-only scope, real PPU, inventory path and schema, `Art/Environment.meta`, Vincent's review gate). It joins the GER queue.

## D-3. Lower Vault hazards
- **FutureExpansion only.** Lava, chasm and horn trim stay FutureExpansion vocabulary only. No NSC-078 entry uses them.
- **The Lower Vault stays as committed.** It remains NSC-047 rev 4's Broken Sluice Crossing, and NSC-082 rev 3 already fits it. Delete AC-006 and INT-002's "Vincent must decide NSC-047 vs NSC-082" wording (R-05).

## D-4. PixelLab processing and records
- **Allowed edits.**
  - Lossless crop and pad, recorded.
  - PixelLab-native repairs only: `inpaint_image` and `inpaint_image_pro_flash` with a recorded mask, proven byte-exact outside the mask; PixelLab `reduce_colors`; and `edit_image_pro_flash` or `create_object_state` to make a matching variant from an approved source.
  - No hand-painted, scripted or non-PixelLab pixel edits (art bible hard rule).
- **Raw exports.** Every selected PNG has its raw PixelLab export committed under `Docs/Art/Environment/Props/Raw/<family>/<id>.png`, with no `.meta` (so it never imports as a cubemap stub texture). The inventory records `raw_sha256`, `selected_sha256` and any crop or pad offset.
- **Rejects.** Rejected candidates are kept under `Docs/Art/Environment/Props/Candidates/<id>__rNN.png`, claimed as a directory.
- **No seam repair.** Long runs use post-and-panel segments, so drop VAL-003's repeat-period invariant from NSC-078. Wall repeat checks stay with NSC-064.

## Other contract changes
- **AC-001.** Allow `style_image` and `color_image` only from Vincent-approved NSC-078 pilot sources, recorded by SHA-256. R01-R17 are never generator inputs.
- **AC-002.** Use the Art Director plan's section 1 list (45 entries after D-2), its `identity_category` enum, and its coverage table, including one comedy detail per room.
- **AC-003.** The style-lock pilot is `shared_bone_pile_a`, `ba_collapsed_reading_table_z`, `ca_candelabra_tall`, `re_broken_masonry_blocks` and `lv_iron_rail_x`, with an optional 5-generation `create_image_pixflux` side test of the same five. Contact sheets show native pixels, world scale beside the wizard at the decision-B size (a 2x2-unit camera-facing box), and gameplay-camera density.
- **Prompts and tools.** The plan's section 4 global clause, subject clauses and `create_object_pro_flash` settings are the prompt authority. The light direction is confirmed in the pilot and recorded in `NSC-078_STYLE_LOCK.md`.
- **Spend gates.** Vincent's spend go is required before the pilot (about 68 Pro Flash plus about 10 Pixflux generations), and again before family acquisition (about 581 Pro Flash for 45 entries, or about 82 if Vincent picks Pixflux). Nothing in this contract authorizes spend.
- **Executor.** The Art Director Agent session, under the art bible, per `nsc-art-director-guide.md` section 1.
- **Resources.** `exclusive_resources` names every selected PNG, `.png.meta` and raw PNG for the 45 entries (the plan's appendix generator, extended to the 10 moved rows), plus round 03's catalog, inventory, folder `.meta`, docs and script files, plus the Candidates directory claim.
- **Non-design fixes.**
  - R-01: GUID-only `.meta` companions. INT-003 must also say that the Unity integration builder sets `textureShape = Texture2D`, resets the cookie and gamma fields, and sets 64 PPU, Point filter, no compression, and a camera-facing box.
  - R-02: schema fields, using the plan's enum.
  - R-03: NSC-064 entries are checked only by path and SHA-256 against NSC-064's published inventory, once its revision names it.
  - R-04: the files are enumerated, and `Art/Environment.meta` goes to NSC-064.
  - R-05, R-06, R-07 and R-08: apply as quoted.
  - R-09: door states use NSC-065 AC-002's wording.
  - R-10: check revision 1's AC ids and renumber if needed.
- **Scope.** `execution_scope` returns to `single_agent` and `decomposition_state` to `concrete`. The decisions are now written in, and the pilot and final review are human gates inside one art task.
