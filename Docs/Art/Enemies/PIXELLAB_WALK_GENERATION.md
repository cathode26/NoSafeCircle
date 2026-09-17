# NSC-093 — PixelLab enemy walk source

Status: **provisional source candidate for Vincent's visual review**. The 96 selected walk PNGs are in `Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/Walk/`. This task does not import them into Unity, change the stationary NSC-063 images, create clips or prefabs, or add movement or combat. NSC-077 may integrate the frames into Unity only after Vincent approves this exact candidate. (NSC-094, the earlier integration task, was superseded by NSC-077 on 2026-09-17.)

## Source identities and generation

The inputs are the revised NSC-063 PixelLab characters, with the same costumes, palette and lighting documented in `PIXELLAB_GENERATION.md`. PixelLab MCP `animate_character` was used in `v3` mode, once per character for eight directions, then once for a north-only Melee correction. PixelLab did not expose a model version, seed, frame rate or negative-prompt field. The tool's `directions` argument explicitly listed north, north-east, east, south-east, south, south-west, west and north-west. `frame_count` was 6. PixelLab returned seven frames per direction: index 0 is the reference frame; **indices 1–6 are the six selected animated frames**, renamed `walk_00`–`walk_05`. No idle still was duplicated as an animation frame.

| Enemy | Character ID | PixelLab animation group ID | Result |
| --- | --- | --- | --- |
| Melee, visible cleaver | `070592db-d334-4e7d-b5c9-5dad404d7f98` | `1829930f-b534-42f5-ac45-3ca2d0acd9dc` | Eight directions produced; the original north cycle was rejected because the cleaver disappeared in its middle frame. Its north-east cycle was later found to show a duplicate second cleaver (see NSC-093 correction below) and was replaced. |
| Melee, north correction | same character | `eac8eec0-5c0c-48e1-8ba0-7f1c978285c0` | Selected for north only; its cleaver remains visible in every animated frame. |
| Melee, north-east single-cleaver correction (2026-09-16) | same character | `be98e54d-77d2-421b-9f00-524052e967cd` | Selected for north-east only, replacing the duplicate-cleaver original; started from the approved single-cleaver idle candidate rather than the character's own (two-cleaver) north-east rotation. See "North-east single-cleaver correction" below. |
| Ranged, bright lantern wraith | `adf018b5-b4c9-4533-8ea2-9d9d28537dcb` | `03b945cb-b2ed-431e-86de-0f5a58b73440` | All eight directions selected. |

The exact per-direction animation IDs, source frame indices, raw PNG SHA-256 hashes, selected PNG SHA-256 hashes, original canvas dimensions and padding offsets are recorded for every file in `Source/Walk/inventory.json`. The PixelLab character IDs link back to the selected NSC-063 source images; neither character was regenerated for this task. The source tree contains exactly one six-frame sequence for each enemy and each direction.

Melee eight-direction action description sent to PixelLab:

> Clean looping walking cycle: squat dungeon brute advances in small grounded steps with planted boot contacts. Oversized hood and patched charcoal cloak stay fixed to the body throughout the stride. Large bright chipped iron cleaver remains clearly visible, held diagonally outward in a stable high guard in every frame and every facing, no attack swing, no duplicate weapon, no gore. Preserve the exact revised idle character's proportions, ember eyes, palette, soft light, feet baseline, and transparent background.

North-only Melee correction action description:

> rear-view north-facing loop of six grounded walking steps; the brute grips ONE large bright chipped iron cleaver in its right hand and holds that blade diagonally outward to screen left, beyond the cloak silhouette, high and fully visible in EVERY frame including the middle steps; never hide, lower, crop, duplicate, or swap the cleaver; patched charcoal cloak, oversized hood, ember eyes and boots remain the exact revised character identity; transparent background, consistent size, soft lighting, no attack swing or gore

Ranged eight-direction action description:

> Clean looping walking cycle: small hunched lantern wraith caster advances in short grounded steps; tall cracked lantern-staff stays held forward and outward with the bright round teal ghost-light visible in EVERY frame and facing; pale bone-white glowing hood interior and eyes remain readable, violet scarf and charcoal cloak retain the revised silhouette; no attack, projectile, duplicate staff, gore, or new props; preserve exact revised idle character identity, palette, scale, feet baseline, soft lighting, and transparent background.

PixelLab reported 16 generations for each eight-direction request and 2 for the north-only correction, 34 for this task's three accepted requests. A simultaneous Ranged request was rejected by PixelLab's 10-job concurrency limit before it queued; it returned no animation ID or charge, and the Ranged request was submitted successfully after the Melee jobs completed. The account is shared; its balance was 4,777 generations before these requests and 4,734 afterward, so the full 43-generation account delta must not be attributed to this task without separate evidence.

## Canvas normalization and selected files

PixelLab's v3 walk PNGs are RGBA but vary in canvas dimensions by direction, from 132×132 to 172×172. The raw exports are preserved outside the selected subtree in the NSC-093 task evidence checkout; their SHA-256 hashes and PixelLab animation IDs remain in the committed inventory. Each selected PNG is **losslessly padded** to 176×176 with transparent pixels. The complete raw RGBA bitmap is pasted unchanged, without resizing or cropping, centered horizontally and shifted vertically so every frame's lowest nontransparent pixel ends at image y=132. `inventory.json` records the raw size, alpha bounding box and exact `[x,y]` paste offset for every frame. It is sufficient to reconstruct and check every selected pixel from the original PixelLab URL. The actual character pixels retain their original scale; a future Unity importer must set a matching ground pivot and pixels-per-unit rather than assuming the idle 128×128 canvas settings.

Selected naming is `enemy_<melee|ranged>_<n|ne|e|se|s|sw|w|nw>_walk_<00..05>.png`. Direction identity comes from PixelLab's explicit direction key, never from response order. The generated image size and transparent ground line are consistent across all 96 selected PNGs. NSC-063's 16 stationary source PNGs are unchanged.

## Visual review and validation

The full-resolution [Melee contact sheet](Walk/melee_contact_sheet.png) and [Ranged contact sheet](Walk/ranged_contact_sheet.png) show each NSC-063 idle still above its six walk frames, across all eight facings. [Melee at half scale](Walk/melee_gameplay_scale.png) and [Ranged at half scale](Walk/ranged_gameplay_scale.png) provide a closer indication of gameplay readability. The Melee north correction was selected after comparing the raw first-pass and replacement cycles; the selected north blade remains visible in all frames. The Ranged lantern and glowing hood remain legible across the selected facings. **Vincent must still decide** whether these loops preserve the intended identities, weapon reads, foot motion and acceptable frame-to-frame consistency. In particular, the north-east Melee still and its walk frames appear to show an extra blade; this is visible in the NSC-063 source identity and should be checked explicitly before approval.

A deterministic source audit passed: 96 unique files, two enemies × eight directions × six ordered frames, 176×176 RGBA with transparent and opaque pixels, shared y=132 alpha ground line, matching inventory SHA-256 values, and pixel-for-pixel equivalence between every raw PixelLab image and its recorded padded region. This is source validation only; no Unity Animator, movement, scene or human visual gate has passed in NSC-093.

## North-east single-cleaver correction (2026-09-16)

This section documents task NSC-093's correction, paired with NSC-063's idle
correction (see "North-east single-cleaver correction (2026-09-16)" in
`PIXELLAB_GENERATION.md`). It replaces exactly the six melee north-east walk
frames; no other direction, archetype, or NSC-063 idle file changed here.

**Defect.** The prior melee north-east walk cycle (`animation_group_id`
`1829930f-b534-42f5-ac45-3ca2d0acd9dc`, `animation_id`
`9c9d4789-2c3e-433b-8db1-45fe2b38714e`) showed the same duplicate second
cleaver above the screen-left shoulder as the NSC-063 north-east idle, in all
six frames — exactly the defect this document's "Visual review and
validation" section above flagged as needing to be checked before approval.

**Starting frame.** Per the NSC-063 candidate's own README (see
`Docs/Art/Enemies/Candidates/melee_ne_single_cleaver/README.md`), a walk
correction must start from the approved single-cleaver identity rather than
re-animating the character's own (two-cleaver) north-east rotation. This
correction used `custom_start_frame_url` pointing at Vincent's approved
candidate, byte-verified before use:
`https://raw.githubusercontent.com/cathode26/NoSafeCircle/01e3b8ffd3e47b2f712733ac4ba4f891cc9dd395/Docs/Art/Enemies/Candidates/melee_ne_single_cleaver/idle_single_cleaver.png`
(128x128 RGBA, 3014 bytes, SHA-256
`e714d5e5d4222982f79597099261f7a20e19c7b7986e55a6588dd056e2537e57`).

**Tool call.** PixelLab MCP `animate_character`, `mode="v3"` (not `pro`),
`character_id` `070592db-d334-4e7d-b5c9-5dad404d7f98`, `directions`
`["north-east"]`, `frame_count` 6, `keep_first_frame` true, `animation_name`
"NSC-093 melee walk north-east single cleaver". Action description sent
verbatim:

> north-east-facing three-quarter rear view loop of six grounded walking
> steps; the squat dungeon brute grips ONE large bright chipped iron cleaver
> in its right hand on the screen-right side and holds it diagonally outward
> in a stable high guard, fully visible in EVERY frame; the left hand stays
> empty; never add a second cleaver, never hide, lower, crop or swap the
> blade; oversized hood, patched charcoal cloak, ember eyes and boots remain
> the exact start-frame identity; planted boot contacts, transparent
> background, consistent size, soft lighting, no attack swing or gore

**Attempts.** 1 of 3 allowed attempts was needed. Attempt 1 —
`animation_group_id` `be98e54d-77d2-421b-9f00-524052e967cd`, `animation_id`
`96bfd2b5-e7e5-4ebc-9329-05cd18e738fa` — passed visual review on all six
frames (see quality notes below) and was selected; no second or third
attempt was generated. Cost: 2 generations (v3 mode, 1 job, 2 generations
per direction at this canvas/frame-count combination). PixelLab account
balance was 4,691 generations remaining before this task's calls and 4,689
after (used 311 of the 5,000-generation cycle allowance; the account is
shared, so this delta should not be attributed to this task alone without
separate evidence, consistent with the caveat in the original generation
record above).

**Frame mapping.** PixelLab returned 7 frames (index 0 reference + 1-6
animated), matching the original convention. Frame 1 -> `walk_00`, frame 2 ->
`walk_01`, ... frame 6 -> `walk_05`. Raw canvas for every frame was 152x132
(vs. the original cycle's 152x152); each was renormalized independently onto
the project's 176x176 transparent canvas using the same rule as the rest of
this document: pasted unscaled, horizontally centered
(`padding_offset_x = (176 - raw_w) // 2`), and shifted vertically so the
alpha bounding box's lower edge lands at y=132
(`padding_offset_y = 132 - raw_alpha_bbox[3]`). Exact per-frame `raw_size`,
`raw_alpha_bbox`, `padding_offset`, `raw_sha256` and `selected_sha256` are in
the six updated `inventory.json` entries for
`enemy_melee_ne_walk_00.png`-`enemy_melee_ne_walk_05.png`.

**Quality review.** All six frames were viewed individually at 8x
nearest-neighbor zoom plus a combined comparison sheet
(idle / new frames / old defective frames) and passed every check: exactly
one cleaver, held in the right hand on the screen-right side, in all six
frames; empty left hand; same hood/cloak/boot/palette identity as the
approved idle; alpha bounding box does not touch the raw canvas edge in any
frame (nothing cropped); legs show a varied, readable walking stride across
the six frames. See the comparison sheet and GIF referenced in the NSC-063
fix report for this correction.

**Approval.** Vincent reviewed the comparison sheet
(`C:\nscrev\reports\nsc063-cleaver\ne_walk_candidate_sheet.png`) and the loop
(`ne_walk_attempt1.gif`) and **approved these six north-east walk frames on
2026-09-16**.

**Replaced files and hashes.**

| File | Old `selected_sha256` | New `selected_sha256` |
|---|---|---|
| `enemy_melee_ne_walk_00.png` | `b3754550fa73287769421135a765a44f0dc51f7bae576a7c606498cf3415c014` | `b86249393de4b09aaee9c7181ea890ce1efba6bb801a6a78a2f8e00ebbceed75` |
| `enemy_melee_ne_walk_01.png` | `b3caf40c5aa54b29767caeafe8b6fbdab37429871446fd4a0fcb028934bfb695` | `4afe85029c7475b574601d47dd6734894003a5c1fefe1d21f7f17ed78747b391` |
| `enemy_melee_ne_walk_02.png` | `34bc3fa86298de3df656e8fceca874620789a1e0da5bd6f404cb6a21fd873ee4` | `c19e551fbddb28f502e66fcd25eff912c0c63ae92a70a5409dd59f2c42f1f8ba` |
| `enemy_melee_ne_walk_03.png` | `d618d2da0451dcf52a065de813ea7b59ea22631cbf48b6d86ef770ed7709de85` | `2ee34f241f64f0d52dbfa0ce31b310f88b231c70b3a2a3c212ecd45e6ce3a926` |
| `enemy_melee_ne_walk_04.png` | `82e282c478a145c854fae49a6e59af552d2eb62ccb3db441c3cf405bb7227e61` | `fc1ea368e9aebb9ffbee8c1229d76fa9a50d69882a34db78ebbf786e5e7cab75` |
| `enemy_melee_ne_walk_05.png` | `3cfac1dff75d2e2c8d72bffd90f590e5c8f99053bc7c88a0043e21dfe063f24c` | `5896d2e1e8fa7c32d121e9b75dea6c299701de95a05c9790bb613b83f65ff5b3` |

All six replaced files remain 176x176 RGBA, `.meta` files (and GUIDs)
unchanged. `Docs/Art/Enemies/Walk/melee_contact_sheet.png` and
`melee_gameplay_scale.png` were **not** regenerated: no build script for
either exists anywhere in this repository (same search as the NSC-063 idle
correction). Both sheets still show the two-cleaver north-east cycle and are
stale for that one direction until rebuilt.
