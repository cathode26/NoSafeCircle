# NSC-093 — PixelLab enemy walk source

Status: **provisional source candidate for Vincent's visual review**. The 96 selected walk PNGs are in `Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/Walk/`. This task does not import them into Unity, change the stationary NSC-063 images, create clips or prefabs, or add movement or combat. NSC-094 may use the frames only after Vincent approves this exact candidate.

## Source identities and generation

The inputs are the revised NSC-063 PixelLab characters, with the same costumes, palette and lighting documented in `PIXELLAB_GENERATION.md`. PixelLab MCP `animate_character` was used in `v3` mode, once per character for eight directions, then once for a north-only Melee correction. PixelLab did not expose a model version, seed, frame rate or negative-prompt field. The tool's `directions` argument explicitly listed north, north-east, east, south-east, south, south-west, west and north-west. `frame_count` was 6. PixelLab returned seven frames per direction: index 0 is the reference frame; **indices 1–6 are the six selected animated frames**, renamed `walk_00`–`walk_05`. No idle still was duplicated as an animation frame.

| Enemy | Character ID | PixelLab animation group ID | Result |
| --- | --- | --- | --- |
| Melee, visible cleaver | `070592db-d334-4e7d-b5c9-5dad404d7f98` | `1829930f-b534-42f5-ac45-3ca2d0acd9dc` | Eight directions produced; the original north cycle was rejected because the cleaver disappeared in its middle frame. |
| Melee, north correction | same character | `eac8eec0-5c0c-48e1-8ba0-7f1c978285c0` | Selected for north only; its cleaver remains visible in every animated frame. |
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
