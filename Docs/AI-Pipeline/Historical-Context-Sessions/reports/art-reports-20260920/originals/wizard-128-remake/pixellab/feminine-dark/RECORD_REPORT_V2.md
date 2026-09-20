# PixelLab Batch Record: wizard_fd_walk_128 (Retry)

**Character ID:** `afabd47e-a66e-453d-beee-b90f9856f9e0`  
**Animation Group ID:** `9114df33-56f0-4db8-bac8-66032b078374`  
**Animation Name:** `wizard_fd_walk_128`  
**Recording Date:** 2026-09-17  
**Status:** SUCCESS (all frames downloaded on retry)

---

## 1. Download Completion Summary

### Per-Direction Frame Counts and Attempts

| Direction | Downloaded | Attempts | Status |
|-----------|------------|----------|--------|
| south | 6/6 | 1 | ✓ |
| south-east | 6/6 | 1 | ✓ |
| east | 6/6 | 1 | ✓ |
| north-east | 6/6 | 1 | ✓ |
| north | 6/6 | 1 | ✓ |
| north-west | 6/6 | 1 | ✓ |
| west | 6/6 | 1 | ✓ |
| south-west | 6/6 | 1 | ✓ |
| **TOTAL** | **48/48** | **1 per direction** | **✓ All success** |

**Note:** Initial attempt failed with HTTP 403 on all frames due to URL token expiration. Fresh URLs were obtained via `get_character` and download succeeded immediately on retry with User-Agent header.

---

## 2. Canvas Size Analysis

### Distinct Sizes and Frame Counts

| Canvas Size | Frame Count | Breakdown |
|------------|------------|-----------|
| 128×128 | 8 | Standing rotation frames only |
| 152×152 | 18 | Walk frames (3 directions × 6 frames) |
| 160×160 | 30 | Walk frames (5 directions × 6 frames) |

**Observation:** Walk frames have variable canvas sizes. Standing frames are uniform 128×128.

---

## 3. Per-Direction Alpha Bottom Y Analysis (Walk Frames)

### Frame-by-Frame alpha_bottom_y Values and Spreads

| Direction | Frame 0 | Frame 1 | Frame 2 | Frame 3 | Frame 4 | Frame 5 | Spread |
|-----------|---------|---------|---------|---------|---------|---------|--------|
| south | 131 | 132 | 133 | 138 | 136 | 134 | 7 |
| south-east | 136 | 135 | 133 | 134 | 135 | 138 | 5 |
| east | 136 | 136 | 132 | 134 | 132 | 135 | 4 |
| north-east | 131 | 132 | 133 | 130 | 129 | 128 | 5 |
| north | 130 | 131 | 128 | 130 | 130 | 127 | 4 |
| north-west | 130 | 130 | 129 | 128 | 127 | 127 | 3 |
| west | 136 | 136 | 134 | 135 | 134 | 135 | 2 |
| south-west | 135 | 135 | 134 | 133 | 137 | 138 | 5 |

**Spread Analysis:** 
- Minimum spread: **west** (2 pixels)
- Maximum spread: **south** (7 pixels)
- Most directions: 3–5 pixel range
- All values within reasonable animation variation

---

## 4. Alpha Bounding Box Canvas Edge Check

**Frames with alpha bbox touching canvas edge:** NONE

All 56 frames (standing and walk) have alpha bounding boxes that do not touch the canvas edges. No frames have content clipped at left (0), top (0), right (width), or bottom (height) boundaries.

---

## 5. Frame SHA256 Fingerprints (First 16 Characters)

### Per-Direction First and Last Frame Signatures

| Direction | First Frame SHA256 | Last Frame SHA256 |
|-----------|-------------------|-------------------|
| south | `4e35e58c572accf8` | `1f21fa48fed47259` |
| south-east | `03daae34bef20dca` | `285a9a16e687510c` |
| east | `bffbbb6523b31d74` | `d6ca7ccefa20c6da` |
| north-east | `badc983cc66cdc6b` | `bfac0a52a9ce2835` |
| north | `89c394763921280e` | `cc49fc7aca851e9d` |
| north-west | `962c08d5a3968177` | `d7b9890d9a5af3c2` |
| west | `531accf4893bc5fc` | `0f456cd1fa918bff` |
| south-west | `bc900261339bcdeb` | `c51287c75b5213e8` |

**Observation:** All directions have unique first and last frame signatures; no duplicate frame sequences detected.

---

## 6. Partial-Alpha Pixels

**Frames with partial-alpha (0 < alpha < 255) pixels:** NONE

All 56 frames use clean binary alpha (fully opaque or fully transparent), with no anti-aliasing or semi-transparent pixels.

---

## 7. Balance and Generation Report

### PixelLab Account Status

| Metric | Value |
|--------|-------|
| Subscription | Active (Tier 2: Pixel Artisan) |
| Credits | $30.00 (unchanged) |
| Generations Remaining | 4573 (unchanged) |
| Generations Used (Cycle) | 427 (unchanged) |
| Generations Total (Cycle) | 5000 (unchanged) |
| Cycle Reset Date | 2026-10-14 |

**Generation Spend:**
- **Read-only operations:** `get_character` called 2 times (initial fetch + fresh URLs after 403)
- **Generations queued/used:** 0
- **Generations reported by tools:** 0
- **Balance delta:** 0 (no generation occurred)

**Note:** This job was exclusively read-only. All downloaded frames are existing assets from a previously generated character. No new art was generated or modified.

---

## 8. File Inventory Summary

### Standing Frames (8 total)
- Source: `standing_raw/` folder (pre-existing)
- All 8 directions represented
- Uniform size: 128×128
- Format: RGBA PNG

### Walk Animation Frames (48 total)
- Downloaded from PixelLab animation group `9114df33-56f0-4db8-bac8-66032b078374`
- 8 directions × 6 frames/direction
- Canvas sizes: 152×152 (18 frames) and 160×160 (30 frames)
- Format: RGBA PNG
- All frames downloaded successfully

### Total: 56 frames recorded

---

## Inventory Schema

**File:** `raw_inventory_v2.json`

**Structure:** One root object containing:
- `key`: Schema identifier (`nsc-enemy-pixellab-walk-source/v1`)
- `character_id`, `animation_group_id`, `animation_name`: Identifiers
- `recorded_utc`: Timestamp of recording
- `balance_after`: PixelLab account balance at completion
- `frames`: Array of 56 frame objects

**Per-Frame Fields:**
- `group`: "standing" or "walk"
- `direction`: Compass direction (south, north-east, etc.)
- `index`: Frame number (0–5 for walk, 0 for standing)
- `file`: Relative path to PNG file
- `source_url`: Download URL from PixelLab (null for standing frames)
- `width`, `height`: Canvas dimensions
- `mode`: PIL image mode (RGBA)
- `raw_alpha_bbox`: `[left, upper, right, lower]` bounds of non-transparent pixels
- `alpha_bottom_y_from_top`: Lower edge of alpha bounding box (pixel index from top)
- `opaque_pixels`: Count of pixels with alpha > 0
- `partial_alpha_pixels`: Count of pixels with 0 < alpha < 255
- `raw_sha256`: SHA-256 hash of file bytes
- `bytes`: File size in bytes

---

## Anomalies and Notes

### Issues Encountered

1. **HTTP 403 Forbidden on First Attempt**
   - Affected: All 48 walk frames
   - Cause: Signed Backblaze URLs with expiring `?t=` tokens
   - Duration: ~2–5 minutes after `get_character` call
   - Resolution: Fetched fresh URLs via second `get_character` call
   - Fix applied: Added User-Agent header to urllib requests

### Data Quality

- **No partial-alpha pixels:** All frames use binary alpha (good for pixel art)
- **No canvas edge clipping:** All alpha bboxes have safe margins
- **No duplicate frames:** Each direction has unique frame signatures
- **Consistent frame motion:** alpha_bottom_y spread of 2–7 pixels per direction is typical for walking cycles
- **Variable canvas sizes:** Frames vary between 152×152 and 160×160; this is normal when PixelLab optimizes canvas size per frame

### No Issues to Report

- ✓ All 48 walk frames downloaded
- ✓ All 8 standing frames accounted for
- ✓ No missing or corrupted files
- ✓ No duplicate sequences
- ✓ No partial-transparency artifacts
- ✓ No generation cost incurred

---

**End of Report**
