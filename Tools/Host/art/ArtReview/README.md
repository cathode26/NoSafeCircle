# No Safe Circle art-review toolkit

This Python 3.10+ package creates review-only PNG sheets, GIFs, measurements, inpaint proofs, normalized frame copies, and a manual PixelLab spend ledger. It never calls PixelLab and never modifies an input image. The reference implementation uses only the Python standard library.

Run commands from `Pipeline/ArtReview`:

```text
python3 -m art_review --help
python3 -m art_review <subcommand> --help
```

All output paths are explicit. Before writing, every file-producing command reads and hashes all of its inputs. A command refuses with exit code 2 and writes nothing when an output resolves to an input or when two outputs resolve to the same file. Comparison uses normalized real paths and existing-file identity, so symlink, hard-link, Windows case, and Windows 8.3 aliases are covered. The ledger file is the intentional read/append exception for `init`, `add`, and `balance`; `ledger summary` still refuses to replace its ledger. Manifests are UTF-8 JSON. A command reports malformed input with exit code 2 unless its section documents another result.

## `gamescale`

Render one or more sprites into side-by-side panels at the fixed isometric camera's true screen scale:

```text
python3 -m art_review gamescale --manifest density.json --output density.png --json density-report.json
```

The manifest has optional sheet fields `resolution` (`1080p`, `1440p`, or a vertical pixel count), `panel_width`, `panel_height`, `gap`, `background`, `grid`, `grid_color`, and `footer`, plus a required `sprites` array. `--resolution` overrides the manifest. Every sprite provides `path`, `label`, `mode`, and `sampling`. Camera-facing sprites select exactly one of `box_units`, direct `scale`, or `ppu`. World-plane sprites provide `ppu` and optional `local_scale`. `pivot` is `bottom-center` (default), `center`, or `[x,y]`; `position` is a panel screen point and `phase` adds a sub-pixel `[dx,dy]`. The report records each rendered alpha bbox and alpha-positive pixel count.

When enabled, each grid position is computed independently as `round(k * (vertical_resolution / 16))`. This is Python's half-even rounding, so the first 1080p positions are 0, 68, 135, 202, and 270 rather than a repeatedly added rounded spacing. Labels and footer use the built-in 5x7 font with a defined glyph for every printable ASCII character from 32 through 126. Lowercase letters may share their uppercase shapes; punctuation has dedicated shapes.

## `contact-sheet`

Use either a manifest or a glob:

```text
python3 -m art_review contact-sheet --manifest sheet.json --output sheet.png --zoom 4 --gap 8 --header "Wisp candidates"
python3 -m art_review contact-sheet --glob "C:\Art\Wisp\*.png" --columns 5 --output wisp-sheet.png --json wisp-sheet.json
```

A manifest is `{"rows":[[{"path":"...","caption":"..."}]]}` (the outer object may be omitted). Column width is the largest zoomed image width in that column. Row height is the largest zoomed image height in that row plus 10 label pixels. Smaller images are centered. `--background` and `--cell-background` accept `#RRGGBB` or `#RRGGBBAA`.

## `gif`

Encode positional frames, a glob, or a manifest:

```text
python3 -m art_review gif frame-01.png frame-02.png --duration 50 --zoom 4 --output preview.gif --json preview.json
python3 -m art_review gif --manifest timeline.json --background "#1d1631" --output timeline.gif --json timeline-report.json
```

A timeline manifest is `{"frames":[{"path":"frame.png","duration_ms":50}]}`. `--duration` is the default duration, `--no-loop` omits the NETSCAPE loop extension, and durations are rounded to GIF centiseconds. Frames with at most 256 representable colors use an exact palette without dithering; larger sets use deterministic median-cut reduction and set `palette_reduced` in the JSON report. GIF has binary transparency: partially transparent input is rejected unless `--background` first composites it to opaque pixels. Opaque animations use disposal method 1. Animations with a transparency index use disposal method 2 (restore to background) on every full-canvas frame, so transparent pixels in a later supplied frame cannot retain pixels from an earlier frame.

`--motion-scene scene.json` treats the ordered inputs as a cycling sprite animation. The scene selects a PNG `background` or a `[width,height]` `size` plus `background_color`; `start`, `end`, `fps`, `sampling`, and camera-facing/world-plane fields use the same meanings as `gamescale`. Its `pivot` uses the same shared parser: `bottom-center` (default), `center`, or custom `[x,y]`. Motion speed is either `screen_speed` in pixels/second or `world_speed` with a ground-plane `direction` and `resolution`. The special direction string `down-right` means world `(0.94868,-0.31623)` in X/Z.

## `mask-diff`

```text
python3 -m art_review mask-diff --source source.png --result result.png --mask mask.png --output proof.png --zoom 4 --json proof.json
```

The mask must contain only opaque black (keep) and opaque white (regenerate). The proof is `source | result | changed pixels in magenta`, composited over gray. Fully transparent pixels compare equal regardless of their stored RGB. JSON contains inside/outside counts, introduced result colors, and all three input SHA-256 hashes. Exit code 0 means no outside change, 1 means at least one outside pixel changed, and 2 means invalid input.

## `frame-metrics`

```text
python3 -m art_review frame-metrics --glob "C:\Art\Walk\*.png" --loop --json walk-metrics.json --markdown walk-metrics.md
```

Per-frame output includes size, exclusive alpha bbox, alpha-positive pixel count, distinct RGBA count, and input SHA-256. Neighbor deltas include opaque-count percentage, bbox width, and bbox bottom (feet baseline). `--loop` adds the last-to-first seam. Default flags are absolute opaque change over 15%, absolute width change over 8 pixels, and absolute baseline jump at least 3 pixels; change them with `--opaque-threshold`, `--width-threshold`, and `--baseline-threshold`. Findings never change the exit code.

## `hue-scan`

```text
python3 -m art_review hue-scan --glob "C:\Art\Wisp\*.png" --json warm.json --fail-on-match
python3 -m art_review hue-scan frame.png --range 180:240 --minimum-saturation 0.4 --minimum-value 0.25 --json blue.json
```

Custom `--range` values use inclusive HSV degrees as `LOW:HIGH`; a wrapped range has `LOW > HIGH`. With no custom range, the default warm scan is intentionally strict: hue below 70 or above 330 degrees, with saturation and value strictly above 0.3. Hues exactly 70 and 330 do not match the default. Transparent pixels are ignored. The report includes counts, range semantics, and example colors. `--fail-on-match` exits 1 when any pixel matches.

## `normalize`

```text
python3 -m art_review normalize --glob "C:\Art\Walk\*.png" --size 128 --output-dir "C:\Art\Walk\Normalized" --json normalize.json
python3 -m art_review normalize frame.png --canvas 128 160 --output-dir normalized --json normalize.json
```

Each source origin is placed at `floor((target-raw)/2)` on each axis. Pixels are copied exactly and never resampled. A frame whose alpha-positive content would be cropped is refused before its output is written; the command continues other frames and exits 1 if any frame was refused. The report includes raw size/bbox/hash, canvas origin, selected bbox/hash, and output path. Path collisions, including duplicate output basenames from different source folders, refuse the whole command with exit code 2 before the output directory or report is written.

## `ledger`

The ledger is append-only JSON Lines. Values are copied from PixelLab tool results; this package performs no generation.

```text
python3 -m art_review ledger init --ledger spend.jsonl --job "Wisp animation" --cap 15 --remaining 4683 --used 317
python3 -m art_review ledger add --ledger spend.jsonl --tool animate --id 42ad9f --reported-cost 6 --note "wind-up"
python3 -m art_review ledger add --ledger spend.jsonl --tool inpaint --id c91be2 --reported-cost 2 --provisional
python3 -m art_review ledger balance --ledger spend.jsonl --remaining 4668 --used 332 --label "after review"
python3 -m art_review ledger summary --ledger spend.jsonl --json spend-summary.json --markdown spend-summary.md
```

`init` refuses an existing file. Every ledger line must be a JSON object with the complete, correctly typed fields for `init`, `entry`, or `balance`. `reported_cost` must be finite and between 0 and 1,000,000 inclusive. `remaining` and `used` must be integers between 0 and 1,000,000,000,000 inclusive; `cap` must be null or an integer in the same range. Exactly one `init` is allowed and it must be line 1. `summary`, `add`, and `balance` validate the entire ledger, report the bad line number, and refuse malformed data without silently skipping it or appending. New `init`, `add`, and `balance` arguments receive the same validation before a write.

Summary shows per-tool totals, reported total, first-to-last changes by both generations-used and remaining balance, and `unattributed_difference = used change - reported total`. Spend is the reported total plus positive unattributed spend. Status is `no_cap`, `over_cap`, `near_cap` (spend at least cap minus 2), or `ok`. Every summary warns that the shared PixelLab account can include other sessions.

## Worked example 1: density check and moving walk preview

Save this as `C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Density\20260917-120000\density.json`:

```json
{
  "resolution": "1080p",
  "panel_width": 320,
  "panel_height": 320,
  "grid": true,
  "footer": "Fixed camera: Euler (30,-45,0), orthographic size 8",
  "sprites": [
    {"path":"C:\\Users\\VincentLiguori\\Downloads\\NoSafeCircleOutput\\ArtReview-Inputs\\walk-180.png","label":"In game today","mode":"world-plane","ppu":180,"local_scale":[1,2],"sampling":"point"},
    {"path":"C:\\Users\\VincentLiguori\\Downloads\\NoSafeCircleOutput\\ArtReview-Inputs\\walk-180.png","label":"Now: 180 px, Point","mode":"camera-facing","box_units":2,"sampling":"point"},
    {"path":"C:\\Users\\VincentLiguori\\Downloads\\NoSafeCircleOutput\\ArtReview-Inputs\\walk-180.png","label":"A: smoothed","mode":"camera-facing","box_units":2,"sampling":"smooth"},
    {"path":"C:\\Users\\VincentLiguori\\Downloads\\NoSafeCircleOutput\\ArtReview-Inputs\\walk-128.png","label":"B: remade at 128","mode":"camera-facing","box_units":2,"sampling":"point"}
  ]
}
```

Save this beside it as `walk-motion.json`:

```json
{
  "background_color":"#1d1631",
  "size":[640,640],
  "start":[80,80],
  "end":[485,485],
  "world_speed":4,
  "direction":"down-right",
  "resolution":"1080p",
  "fps":60,
  "mode":"camera-facing",
  "box_units":2,
  "sampling":"point"
}
```

From the package directory on the Windows host, run:

```text
python -m art_review gamescale --manifest "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Density\20260917-120000\density.json" --output "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Density\20260917-120000\density.png" --json "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Density\20260917-120000\density-report.json"
python -m art_review gif --glob "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Inputs\walk-*.png" --motion-scene "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Density\20260917-120000\walk-motion.json" --output "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Density\20260917-120000\walk-motion.gif" --json "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Density\20260917-120000\walk-motion-report.json"
```

At 4 world units/second and 60 fps, this fixed camera produces about 170.76 screen pixels/second, or 2.0125 pixels right and down per frame.

## Worked example 2: inpaint proof and wisp GIF

The first command proves a 128×128 inpaint stayed inside its binary mask:

```text
python -m art_review mask-diff --source "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Inputs\enemy-128-source.png" --result "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Inputs\enemy-128-inpaint.png" --mask "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Inputs\enemy-128-mask.png" --output "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Wisp\20260917-123000\inpaint-proof.png" --zoom 4 --json "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Wisp\20260917-123000\inpaint-proof.json"
```

Build `wisp-timeline.json` with these ordered entries (filenames use two-digit numbering):

- `idle-01.png` through `idle-10.png`: 50 ms each.
- `windup-01.png` through `windup-08.png`: 50 ms each.
- `travel-01.png` through `travel-40.png`: 50 ms each, authored across 405 screen pixels.
- `hit-01.png` through `hit-04.png`: 80 ms each.
- `empty.png` repeated 10 times: 50 ms each.

The JSON shape is the same timeline manifest documented above; then run:

```text
python -m art_review gif --manifest "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Wisp\20260917-123000\wisp-timeline.json" --zoom 4 --background "#1d1631" --output "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Wisp\20260917-123000\wisp.gif" --json "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\ArtReview-Wisp\20260917-123000\wisp-report.json"
```

## Tests and limits

From the repository root:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Pipeline/ArtReview/tests -t Pipeline/ArtReview
```

Large smooth game-scale sheets are intentionally CPU-bound: rendering loops over the transformed sprite bounds plus the full bilinear half-texel support, and 4× supersampling performs 16 bilinear samples per output pixel. PNG decoding rejects interlaced and 16-bit files as well as any data after `IEND`. GIF quantization is deterministic and does not dither. No Pillow acceleration path is present, so there is no optional-path pixel-parity concern.
