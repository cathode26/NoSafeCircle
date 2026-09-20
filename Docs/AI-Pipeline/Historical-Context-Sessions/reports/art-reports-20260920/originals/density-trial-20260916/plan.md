# Pixel-density trial: masculine-light wizard, south-east (2026-09-16)

Art Director job. Trial only: no task ID, checkout, branch, commit or viewer marker. Nothing is written under `C:\NSC\NSC\NoSafeCircle`; it is read only.

## Approval and Vincent's words

- Vincent approved a one-facing pixel-density trial, at most 15 PixelLab generations (2026-09-16, launch prompt `C:\nscrev\reports\art-director\launch-prompt-density-and-wisp-20260916.md`).
- The launch prompt asked for a 64x64 option-B canvas. After step 1 showed the wizard's box is 2 world units tall, Vincent answered (2026-09-16): **"The wizard should be 128x128"**. Option B therefore uses a 128x128 canvas, about 64 pixels per world unit in a 2x2-unit box.

## Vincent's decision (2026-09-16)

- Question, after the review images were opened in the session side panel (`inspect/sheet_1x_cell1_now_a_b_4x.png`, `density_motion_3x.gif`, `density_sheet_1x.png`): "Wizard density: does B (the 128 px remake) still look like the same wizard? A or B?"
- Vincent: **"yes"**. With his earlier **"The wizard should be 128x128"**, this is recorded as **B: re-make characters at game size, a 128x128 canvas at about 64 px per world unit** (a 2x2-unit camera-facing box). If "yes" answered only the likeness question, his 128x128 instruction still specifies B; he can correct this record.
- Not approved by this decision: the production remake spend, the builder change, or the NSC-075 test changes. The trial art is review material and is not committed.

## Step 1: on-screen scale (read from code on local `main` `bdf618744`; sprites identical on `origin/main` `96a6293c4`)

| Fact | Source |
|---|---|
| Camera: orthographic size 8, Euler (30, -45, 0), offset (10, 10, -10) | `DoorPrototypeGlobalSceneBuilder.cs` `IsometricOrthographicSize`, `BuildCamera` |
| Screen px per world unit (perpendicular to view): 1080/16 = 67.5 at 1080p; 1440/16 = 90 at 1440p | derived |
| Player "Visual" SpriteRenderer: `CreateWorldSpriteVisual("Visual", "WizardSprite", player, Vector3.zero, Quaternion.identity, new Vector2(1f, 2f), ...)` so `localScale = (1, 2, 1)`, rotation identity (sprite lies in the world XY plane; it does not face the camera) | `DoorPrototypeGlobalSceneBuilder.BuildPlayer` line 277; `DoorPrototypeSceneBuilder.CreateWorldSpriteVisual` line 975 |
| Wizard import: Sprite, 180 PPU, pivot (0.5, 0), Point filter, no mipmaps, uncompressed | `ImportWizardSprite` lines 550-572 |
| Walk clips: 6 sprites, `EnsureWizardClip(walkName, walk, 12)` so 12 fps, keys at i/12 s, loopTime on; idle clips 1 fps | `BuildWizardAnimationAssets` line 533, `EnsureWizardClip` lines 589-612 |
| Player move speed: `PlayerMovement.moveSpeed = 4` world units/s on the ground plane | `Scripts/PlayerMovement.cs` line 21 |

**The trial's premise did not add up.** The launch prompt assumed the 180 px art shows at 67.5/180 = 0.375x. With the real transform:
- camera right = (0.7071, 0, 0.7071), camera up = (-0.3536, 0.8660, 0.3536);
- sprite X (world X, scale 1): 0.2652 screen px right and 0.1326 px down per source px (squeezed and sheared 26.6 degrees);
- sprite Y (world Y, scale 2): 0.6495 screen px up per source px;
- the south-east standing figure (58x146 source px) shows about **15 px wide x 96 px tall** at 1080p, leaning.

Confirmed against a real Unity render: `C:\NSC\AssistantControlEvidence\nsc044-gameplay-camera-tint-20260914\d1-staging.png` (NSC-044 camera review test, 800x600, ortho 8, wizard at `localScale (1, 2, 1)`, identity rotation) shows the same thin, leaning wizard, about 53 px tall at 37.5 px/unit, which scales to 95 px at 1080p. Evidence sheet: `scale_check_current_visual.png` (left: Unity render crop; middle: computed projection; right: the same art camera-facing at the same height). Tool: `tools/scale_check.py`.

Asked Vincent for one 1920x1080 Game-view screenshot beside a wall, to be saved as `gameview_1080p.png` in this folder. Status recorded in the results section.

**Consequence for both options:** the integration must give the wizard Visual a uniform scale and a camera-facing orientation. Without that, A and B are both squeezed to about 0.41 of their drawn aspect and sheared. Integration work, owned by a Task Orchestrator job.

**Simulation assumption (stated on every sheet):** the fixed Visual is a camera-facing 2x2-world-unit box. At 1080p that box is 135 px: the 180 px art shows at 0.75x and the 128 px art at 1.0547x. At 1440p the box is 180 px: the 180 px art shows at exactly 1.0x and the 128 px art at 1.406x.

## Step 2: sources (read only)

Root: `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/`. Measurements in `source_measurements.json` (`tools/measure_sources.py`).

| File | Size | Alpha bbox | Opaque px | SHA-256 |
|---|---|---|---|---|
| `standing/south.png` | 180x180 | (60,12)-(120,155) | 5126 | `38c4f378898a0ae57bb495a4d8d5ca68482c1deda911f38f8181bd0896405116` |
| `standing/south-east.png` | 180x180 | (60,13)-(118,159) | 4600 | `89258c88260bfa1a62ac3d393a3c98ba61067c08b2bf7d805b0cf2d76d6df301` |
| `walk/south-east/frame_000.png` | 180x180 | (61,12)-(119,159) | 4556 | `7e69bb86f003bceff5f6dfd3e885fee2ed2630d4ccb80e577ab4bff876e1015c` |
| `walk/south-east/frame_001.png` | 180x180 | (61,11)-(121,153) | 4676 | `8d17eaa8b070cf605a723b79f46776a8f4801acee8e51f9928f9602d686773d6` |
| `walk/south-east/frame_002.png` | 180x180 | (60,11)-(118,152) | 4530 | `377fb9f357a62bada541a9dad3c735f843b55e04f253a80dbf1faed9a7722930` |
| `walk/south-east/frame_003.png` | 180x180 | (59,12)-(117,159) | 4657 | `64fc316233178008aaedc55583512f012fd045e5c83202e5d3953a361a1240b7` |
| `walk/south-east/frame_004.png` | 180x180 | (60,11)-(121,159) | 5067 | `2c5942a62c2ddb6ebd8d3aed3101578dad69279a5e2274954f42007c704ce94a` |
| `walk/south-east/frame_005.png` | 180x180 | (61,11)-(118,159) | 4820 | `bec335bbf2c557cceb90ed8967be12da539bea2913e5f502dc66525b3f8d38f5` |

Source URL for PixelLab (verified 2026-09-16: HTTP 200, bytes match the local file; `tools/verify_urls.py`):
`https://raw.githubusercontent.com/cathode26/NoSafeCircle/96a6293c47cf2346b5c98f968e8790ce561674d3/Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south.png`

## Step 3: planned PixelLab calls (option B at 128x128)

Pre-flight 2026-09-16: `list_jobs(include_recent=true)` showed no active jobs and none finished in the last 30 minutes. Balance before: generations remaining 4689, used 311 of 5000; credits $30.00 (shared account).

| # | Tool | Parameters | Expected generations |
|---|---|---|---|
| 3a | `image_to_pixelart` | `image_url` = south.png raw URL above; `faithful=true`; `init_image_strength=150` (adjust within 100-300 only if needed); `output_width=128`; `output_height=128`; `seed=20260916`; `text_guidance_scale` default 8 | 1 |
| 3b | `create_character` | `mode="v3"`; `reference_image_url` = https URL PixelLab returns for 3a; `description="stocky pale-skinned wizard with brown hair and a full brown beard, purple pointed hat with a tan band, open dark-purple coat over a light-blue shirt, brown belt with a book at the hip, brown boots, dark-but-cute horror-comedy pixel art, low top-down"`; `view="low top-down"`; `body_type="humanoid"`; `name="masculine-light density trial 128"`; `size` omitted (defaults to the 128 reference) | 2-9 (v3 scales with size; about 4-5 expected at 128) |
| 3c | `animate_character` | `character_id` from 3b; `mode="v3"`; `directions=["south-east"]`; `frame_count=6`; `animation_name="density_trial_walk_se"`; `action_description="walking, classic even-paced six-frame walk loop, feet stepping on one steady ground line, arms swinging gently, hat, hair, beard, long coat and belt book kept exactly as in the standard pose"`; `keep_first_frame` default true (frame 0 = start pose, 1-6 = loop) | ceil(w x h x 6 / 65536): 2 at a 128-148 px canvas, 3-4 up to 185 px |

Expected total 7-14, cap 15. Anything more stops for Vincent's go.

Every result is downloaded at once into `pixellab/` and kept. Frames are cropped or padded losslessly, centered, to 128x128 only after checking that no opaque pixel falls outside the crop; raw size, alpha bbox, offset and SHA-256 are recorded per frame.

## Step 4: game-scale simulation (local Pillow, no Unity, no AI; review material only)

Tool: `tools/density_sim.py`. Outputs are review renders, never source art.

- Background `#1d1631`, faint 1-world-unit grid.
- Panels:
  - "In game today": the 180 px art through today's builder transform (1x2 box, not camera-facing), nearest sampling. Reference only.
  - "Now: 180 px, Point": the 180 px walk frames in the camera-facing 2-unit box (0.75x at 1080p, 1.0x at 1440p), nearest sampling at pixel centers.
  - "A: smoothed": the same frames and size, rendered at 4x with bilinear sampling (premultiplied alpha), then box-downscaled 4x, to mimic mipmaps + bilinear.
  - "B: remade at 128": the 128 px walk frames (animation frames 1-6) in the same 2-unit box (1.0547x at 1080p, 1.406x at 1440p), nearest sampling.
- Motion: world move speed 4 units/s along the direction that points exactly screen down-right (world direction (0.949, 0, -0.316)). That is 0.632 screen units per world unit, 170.8 px/s at 1080p (2.012 px right and 2.012 px down per 1/60 s) and 227.7 px/s at 1440p. Positions are sampled in sub-pixel steps at 60 fps; walk frames advance at the clip's 12 fps (each frame held 5 steps, 0.5 s loop).
- GIF timing: GIF cannot play 60 fps, so the GIFs show every second 60 fps step at 30 fps (delays 30/30/40 ms).
- Outputs: `density_sheet_1x.png` (1080p scale), `density_sheet_1440p.png`, `density_sheet_4x.png` (4x nearest zoom of the 1080p sheet), `density_motion_1x.gif`, `density_motion_3x.gif`.

Unverified note for the Unity check: the walk clip's keys sit at i/12 s with no hold key after the sixth sprite, so the clip may be 5/12 s long and show frame 5 only briefly. Only Unity can confirm.

## Results

Download log with URL, SHA-256, size, alpha bbox and opaque count for every file: `downloads.json` (`C:\nscrev\reports\art-director\tools\fetch_result.py`).

### 3a `image_to_pixelart`: done, 1 generation

- Job `d7ff0f49-bc75-4a5c-81b1-bf0764ac0c91`; parameters exactly as planned (strength 150 on the first try; no adjustment needed).
- Result URL: `https://api.pixellab.ai/mcp/images/d7ff0f49-bc75-4a5c-81b1-bf0764ac0c91/download`, saved as `pixellab/3a_image_to_pixelart_south_128.png`: 128x128, SHA-256 `be1a7a4ab2c9d27601dd013627c09da8a5f2705902276c89fc71d2413782581f`, 80 colors.
- **Opaque**: PixelLab flattened the transparent source onto a gray (129,130,130) background; the tool has no background option. Passed to 3b unchanged, as the launch prompt specified.
- Look: faithful to `standing/south.png` (hat and tan band, beard and grin, blue shirt, coat, belt book, boots). Check sheet: `inspect/3a_vs_source.png`.

### 3b `create_character` v3 with reference: done, 2 generations

- Character `1d1cd21e-dd13-4bcc-9e0d-4c56f84e5e80` ("masculine-light density trial 128"), group `b3586e63-9d1c-41d5-a0ff-6123d231ff85`; PixelLab-reported cost 2 (below the 4-5 estimate).
- The v3 rotation removed the gray background: all 8 rotations are transparent 128x128 PNGs in `pixellab/3b_rotations/`. After the job's final pass the URLs changed (`?t=1789619035` to `?t=1789619071`); a re-download to `pixellab/3b_rotations_final/` is byte-identical.

| Rotation | Alpha bbox | Opaque px | SHA-256 |
|---|---|---|---|
| south | (43,8)-(85,110) | 2609 | `dffbac8f175126f1...` |
| south-east | (42,11)-(87,114) | 2395 | `2ec4872fddd7df23...` |
| east | (45,13)-(87,117) | 1993 | `7e8ec80b881c9cb4...` |
| north | (43,10)-(84,109) | 2644 | `62f9fa18327bd887...` |
| west | (40,12)-(83,117) | 2018 | `f46df36a182bb8c0...` |
| north-east | (43,11)-(85,113) | 2451 | `850d84bf618d4ec3...` |
| north-west | (43,12)-(84,113) | 2523 | `7e05c313520fae9d...` |
| south-west | (41,9)-(85,114) | 2345 | `8e6fe2fe08ad8044...` |

(Full hashes in `downloads.json`.) Identity check against the 180 px south and south-east standing sprites: `inspect/3b_rotation_vs_source.png`. On-model: hat and band, beard, grin, shirt, coat, buckle, belt book and boots all carried over.

### 3c `animate_character` v3, south-east, 6 frames: done, 2 generations

- Animation group `2e1ec5da-1e38-4e70-a2c3-8a192a1b96ee`, animation `517b8825-1ecc-4e3a-ac45-f7bcf4622f3e`; PixelLab-reported cost 2.
- 7 raw frames at 152x152 (index 0 = start pose, 1-6 = loop) in `pixellab/3c_walk_se_raw/`.
- Normalized losslessly to 128x128: raw canvas origin (-12, -12), a 12 px crop per side containing no opaque pixels; opaque counts unchanged. Output in `pixellab/3c_walk_se_128/`; per-frame raw size, bboxes, offsets and both SHA-256 values in `pixellab/3c_walk_se_128/normalize_report.json` (`tools/normalize_frames.py`).

| Frame | 128 px alpha bbox | Opaque px |
|---|---|---|
| 00 (start pose) | (42,11)-(87,114) | 2395 |
| 01 | (42,12)-(87,112) | 2289 |
| 02 | (43,14)-(88,113) | 2274 |
| 03 | (43,12)-(88,111) | 2351 |
| 04 | (43,11)-(88,113) | 2442 |
| 05 | (43,11)-(88,113) | 2541 |
| 06 | (43,14)-(88,118) | 2528 |

Continuity findings:
- The feet (bbox bottom) sit at 112-113 on frames 1-5 but 118 on frame 6. The loop seam (6 to 1) jumps the feet about 6 px, the known PixelLab drift toward the camera.
- Opaque pixels rise 2274 to 2541 (+12%) across the loop; width is steady at 45 px, so no silhouette loss.
- Strip: `inspect/walk_180_vs_128.png`.

Job 1 generations used by me: 5, tool-reported (3a 1, 3b 2, 3c 2). Shared balance:
- 4689 remaining before 3a;
- 4686 after 3a and 3b were charged;
- 4669 after both jobs (Job 2 started while 3c ran). The change of 20 is 1 more than the 19 generations reported across both jobs, and `list_jobs` showed only this session's jobs. The extra generation is unattributed, most likely Job 2's provisional Pro Flash inpaint price, but it could be 3c.

### Real-game evidence (2026-09-17, relayed by the Game Agent)

- Vincent played the NSC-077 candidate: Dungeon Brute and Lantern Wraith at 64 PPU in a camera-facing 2x2-unit box.
- He said:
  - "The enemies look great."
  - "the wizards dont look nearly as good sadly".
  - "Whatever you have done to make the enemy look great and in perspective, the wizards need that treatment."
- His screenshots show the thin, leaning wizard this trial predicted, with the door sprite drawn over the wizard's upper body (a sorting issue).
- This confirms step 1's finding in the real game. The exact 1080p/1440p captures (H-20260917-07) still come once the Game Agent's capture tool lands.
- **Follow-ups:**
  - the Game Agent asked the GER Agent to contract the wizard Visual integration (uniform camera-facing box plus sorting check);
  - the 128x128 wizard remake under decision B is the Art Director's to schedule, and still needs its own contract and Vincent's PixelLab spend go.

### Step 1 screenshot

As of the PixelLab work, `gameview_1080p.png` had not been saved. Vincent answered the canvas question ("The wizard should be 128x128") but not the screenshot request. The scale finding rests on the builder code plus the real Unity render from the NSC-044 camera review test; the in-game Game-view check is still owed.

### Step 4 simulation

Built by an `art-director` subagent on Sonnet (Vincent, 2026-09-16: "send it to subagent if it is easy so a lower cost subagent can do it") to the spec above. Values and metrics: `sim_notes.md`, `sim_metrics.json`.

In game, `IsometricCameraFollow.LateUpdate` sets the camera to target + a fixed offset, so the wizard holds one sub-pixel screen phase while walking and the world scrolls behind him. The moving-sprite GIF is therefore the worst case: it shows how enemies (not camera-locked) will look. For the wizard the relevant view is the per-frame detail on the static sheets.

Outputs (subagent-built; checked by me with Read and Pillow):

| File | Size | Check |
|---|---|---|
| `density_sheet_1x.png` | 2498x1304 | 4 labeled rows x 9 cells plus footer. A 4x crop of cell 1 (`inspect/sheet_1x_cell1_now_a_b_4x.png`) shows: Now crisp with a few dropped outline pixels; A visibly soft; B crisp and chunkier, same wizard |
| `density_sheet_1440p.png` | 3330x1708 | same layout at 1440p |
| `density_sheet_4x.png` | 9992x5216 | 4x nearest of the 1x sheet |
| `density_motion_1x.gif` | 1740x408 | 45 frames, 30/30/40 ms, 1500 ms, loops |
| `density_motion_3x.gif` | 1720x534 | 45 frames, same timing; frame 22 (`inspect/motion3x_frame22.png`) shows all 4 panels correctly |
| `sim_notes.md`, `sim_metrics.json` | | constants, sampling definitions, metrics |

- The "In game today" projection in the script reproduces the step-1 size: 16x97 px measured against about 15x96 expected.
- Metric caveat: the step-to-step opaque-pixel swing in `sim_metrics.json` mixes real walk-frame changes with sampling changes, and for A it counts semi-transparent edge pixels, so it is a weak shimmer proxy. Judge from the sheets and GIFs, not the numbers.
