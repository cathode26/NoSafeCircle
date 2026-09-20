# Density simulation notes (2026-09-16)

Tool: `tools/density_sim.py` (local Pillow 12.3.0 / Python 3.13.1, no numpy, no subprocesses, no PixelLab calls). Outputs are review renders, never source art; nothing under `C:\NSC\NSC\NoSafeCircle` was written.

Inputs read (read-only):
- 180 px walk, masculine-light south-east, 6 frames: `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_000.png` .. `frame_005.png` (180x180 RGBA).
- Option B 128 px walk: `pixellab/3c_walk_se_128/frame_01.png` .. `frame_06.png` (128x128 RGBA; `frame_00.png` is the start pose and was not used).

## Values used

| Value | 1080p | 1440p |
|---|---|---|
| Screen px per world unit | 67.5 | 90 |
| Fixed Visual box | camera-facing 2x2 world units, pivot bottom-center | same |
| Box in screen px | 135 px | 180 px |
| 180 px art scale in the box | 0.75 | 1.0 |
| 128 px art scale in the box | 1.0546875 | 1.40625 |
| "In game today" projection, screen px per source px along sprite X (right, down) | (0.2652, 0.1326) | (0.3536, 0.1768) |
| "In game today" projection, screen px per source px along sprite Y-up (pure up) | 0.6495 | 0.8660 |
| 1440p factor applied to the "today" coefficients | - | x 90/67.5 = 4/3 |

Motion (world direction (0.949, 0, -0.316), 0.632 screen units per world unit, `PlayerMovement.moveSpeed = 4` world units/s):
- 1080p: 170.8 px/s along the screen down-right direction; per 1/60 s step, 2.012 px right and 2.012 px down (both axes equal at 45 degrees screen).
- 1440p: 227.7 px/s; per step, 2.683 px on each axis.
- 60 fps simulation, 1.5 s, 90 steps.
- Walk frame index = `floor(step / 5) mod 6` (12 fps clip, 5 sim-steps held per walk frame).
- Start pivot per panel: a fixed integer anchor near the panel's upper-left plus a fractional phase of (0.37, 0.21) px, then `+ step * step_px` on both axes. Anchors used: 1080p panel `(110, 150)`; 1440p virtual panel (metrics only, no GIF) `(147, 200)`.
- Panel canvas sizes: 1080p motion panel 420x380 px (`PANEL_MOTION_SIZE_1080`); 1440p metrics-only virtual canvas 560x507 px, scaled proportionally, used only to bound "on-screen" for the 1440p opaque-pixel-count metrics (no 1440p GIF is produced, per spec).
- GIF timing: every second 60 fps step is written (45 of the 90 steps), durations cycle 30/30/40 ms, loop forever, palette quantized 256 colors with `Image.Dither.NONE` from a shared palette built across that GIF's own frames.
- 3x window: 140x170 px, the (floor-tracked) pivot held at local (70, 150) inside the window, i.e. `window_origin = (floor(px) - 70, floor(py) - 150)`; the sprite keeps its true sub-pixel offset inside the window. Enlarged 3x nearest-neighbour for display.

Static sheets: 9 columns per row (walk frames 0-5 at pixel phase (0.0, 0.0), then walk frame 0 again at pixel phases (0.25, 0.25), (0.5, 0.5), (0.75, 0.75)); 4 rows, one per panel, labeled above the row; cell 3x3 world units with a >= 1 world unit gap between cells; grid lines every 1 world unit (67.5 px at 1080p, 90 px at 1440p), color `#2a2342`, background `#1d1631`.

## Sampling definitions (exact, as specified; no PIL `AFFINE`, explicit per-pixel loops restricted to each sprite's screen bounding rectangle)

**Nearest** ("Now: 180 px, Point" and "B: remade at 128"), pivot `(px, py)`, scale `s`, canvas `w x h`:
- `left = px - w*s/2`, `top = py - h*s`.
- For screen pixel `(X, Y)` with center `(X+0.5, Y+0.5)`: `u = (X+0.5-left)/s`, `v = (Y+0.5-top)/s`.
- If `0 <= u < w` and `0 <= v < h`: color = `texel(floor(u), floor(v))`; else transparent.

**"In game today"**: the same pixel-center rule through the affine projection. Pivot corresponds to source point `(u0, v0) = (w/2, h)` (canvas bottom-center). For screen pixel center `(X+0.5, Y+0.5)`:
- `dx = (X+0.5) - px`, `dy = (Y+0.5) - py`.
- `Du = dx / ax0`; `Dvd = (dy - Du*ax1) / ay1` (`Dvd` = downward source-pixel offset from the pivot).
- `u = Du + w/2`, `v = Dvd + h`; nearest-sample as above.
- Verified against `plan.md`'s reported on-screen size for the standing south-east figure (58x146 source bbox -> "about 15 px wide x 96 px tall" at 1080p): the walk frame 0 standing pose through this code measured 16x97 px, matching within rounding.

**Bilinear + box-average** ("A: smoothed"): on a 4x grid, `s4 = 4*s`, `left4 = 4*left`, `top4 = 4*top`. For each of the 16 fine sub-pixels `(kx, ky)` in `0..3` making up one final pixel `(X, Y)`: fine index `Xf = 4*X+kx`, `Yf = 4*Y+ky`; `u = (Xf+0.5-left4)/s4`, `v = (Yf+0.5-top4)/s4`; sample bilinearly at texel coordinate `(u-0.5, v-0.5)` from the 4 neighbouring texels (each converted to premultiplied alpha first: `(r*a/255, g*a/255, b*a/255, a)`; out-of-canvas texels are `(0,0,0,0)`), weighted by the standard bilinear fractional weights. Average the 16 premultiplied sub-pixel results (box filter), then unpremultiply (`straight_rgb = premult_rgb / (a/255)` where `a > 0`, else `0`) to get the final pixel's straight-alpha color.

Compositing: straight-alpha "over" onto the opaque background/grid (`out_rgb = src_rgb*a/255 + dst_rgb*(1-a/255)`).

"Opaque" in every metric = alpha > 0 (same convention as `source_measurements.json` / `normalize_frames.py`).

## Statement

This is a simulation, not Unity. In game the camera follows the wizard with a fixed offset (`IsometricCameraFollow.LateUpdate`), so the wizard holds one sub-pixel phase while walking and the world scrolls behind him; the moving-sprite GIF is the worst case and matches how enemies will look.

## Result summary (see `sim_metrics.json` for full per-frame and per-step data)

Mean / max absolute step-to-step change in on-screen opaque pixel count over the 90-step, 1.5 s walk:

| Panel | Mean @1080p | Max @1080p | Mean @1440p | Max @1440p |
|---|---|---|---|---|
| In game today (1x2 box) | 9.27 | 80 | 19.58 | 133 |
| Now: 180 px, Point | 24.00 | 229 | 41.33 | 410 |
| A: smoothed | 26.78 | 279 | 140.79 | 480 |
| B: remade at 128 | 19.63 | 268 | 41.17 | 461 |

At 1080p, B (128 px remake) has both a lower mean and a lower max frame-to-frame opaque-pixel swing than the current 180 px point-filtered art ("Now"), consistent with 128 px showing closer to native resolution in the 2x2-unit box (1.05x vs 0.75x) and therefore sampling more stably. At 1440p, B and "Now" are close on the mean (41.17 vs 41.33) while "A: smoothed" swings far more (140.79 mean, 480 max) - the bilinear+box-average filtering does not remove the instability the way real Unity mipmapping would at this small a sprite size; it mainly blurs single frames rather than stabilizing the sequence.
