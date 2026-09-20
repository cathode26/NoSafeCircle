# PixelLab Batch Record: feminine-dark wizard 128px walk animation

**Date:** 2026-09-17  
**Recorded by:** PixelLab batch recorder  
**Character:** afabd47e-a66e-453d-beee-b90f9856f9e0 (wizard_feminine_dark_128)  
**Animation Group:** 9114df33-56f0-4db8-bac8-66032b078374 (wizard_fd_walk_128)

## Commands executed

1. `get_character(character_id="afabd47e-a66e-453d-beee-b90f9856f9e0")` → Status: completed, all 8 walk directions generated
2. `get_balance()` (before) → 4573 generations remaining, 427 used
3. Downloaded standing PNG files from disk (already present)
4. Attempted to download 48 walk animation frames via HTTP from PixelLab Backblaze URLs
5. Measured all PNG files with Pillow (size, SHA-256, alpha bbox, opaque pixel count, distinct colors)
6. `get_balance()` (after) → 4573 generations remaining, 427 used

## File inventory

### Standing files
✓ All 8 standing rotation PNGs present and measured  
- south.png (5053 bytes)
- east.png (4089 bytes)
- north.png (4103 bytes)
- west.png (3906 bytes)
- south-east.png (5443 bytes)
- north-east.png (4401 bytes)
- north-west.png (4306 bytes)
- south-west.png (5443 bytes)

**Total standing:** 8 files ✓

### Walk animation frames
✗ **All 48 walk animation frames EXPIRED** (HTTP 403 Forbidden)

The character API response showed all frames as "completed" with valid-looking Backblaze URLs, but all URLs return HTTP 403 when accessed. This is consistent with PixelLab's documented 8-hour retention for file URLs. The animation group `9114df33-56f0-4db8-bac8-66032b078374` was queued recently but the download links have since expired.

**Missing directions (48 frames total):**
- south (6 frames)
- south-east (6 frames)
- east (6 frames)
- north-east (6 frames)
- north (6 frames)
- north-west (6 frames)
- west (6 frames)
- south-west (6 frames)

## File format verification

All standing files are PNG with RGBA mode (alpha channel present).

### Standing file sizes
| File | Size | Mode |
|------|------|------|
| south | 128×128 | RGBA |
| east | 128×128 | RGBA |
| north | 128×128 | RGBA |
| west | 128×128 | RGBA |
| south-east | 128×128 | RGBA |
| north-east | 128×128 | RGBA |
| north-west | 128×128 | RGBA |
| south-west | 128×128 | RGBA |

**All dimensions:** 128×128 (consistent) ✓

## Check 3: Vertical drift (walk animation alpha bottom Y, by frame)

**CANNOT VERIFY:** All walk frames expired. No data available for per-frame alpha_bottom_y analysis.

## Check 4: Alpha bbox clipping detection

### Standing files alpha bounding boxes
| Direction | Left | Top | Right | Bottom | Width | Height | Clipped? |
|-----------|------|-----|-------|--------|-------|--------|----------|
| south | 40 | 7 | 88 | 116 | 48 | 109 | No |
| east | 40 | 10 | 87 | 120 | 47 | 110 | No |
| north | 43 | 11 | 85 | 117 | 42 | 106 | No |
| west | 42 | 10 | 89 | 120 | 47 | 110 | No |
| south-east | 42 | 9 | 87 | 120 | 45 | 111 | No |
| north-east | 45 | 10 | 84 | 118 | 39 | 108 | No |
| north-west | 45 | 10 | 84 | 118 | 39 | 108 | No |
| south-west | 40 | 8 | 87 | 120 | 47 | 112 | No |

**No standing frames touch canvas edges** ✓

Walk frame clipping cannot be verified (frames expired).

## Check 5: First and last frame SHA-256 comparison

**CANNOT VERIFY:** Walk frames expired. No data available.

Standing file hashes (for reference):

| Direction | SHA-256 |
|-----------|---------|
| south | d97e8d4e2841e9e0193837f6448ad0ae1c450e19356ba2a3417e2d22396859c6 |
| east | 6865594fb128447167ed062ad93f5cbd1ed5df72944fbf3b84af73afc6978860 |
| north | 4e529ff39dc143a1858d53a020cc87b085a40dc821aefe5a6e4d95fbc711641e |
| west | 3c5928c006adedda31378123995c8ad36c500ecc76f101d94511f81c46408d04 |
| south-east | 9c9e7489de788ef3bf9b2447019e5639ed53e6cf1c327a3875416e5f516ba27f |
| north-east | 3c130ed49ef4937d046a8536c2a8792ede91c2c2735005705b98903986605947 |
| north-west | e6a6970cf3e19ff9b65054f0f0b54774c1492f2cc93544663270883074f5019e |
| south-west | 822c0af654bab319bc8a12fb4ee3ecb7bd716cf4cfe9709b33e0b0c6911060cd |

## Anomalies

1. **CRITICAL:** All 48 walk animation frames have expired (HTTP 403 Forbidden)
   - Animation group was completed per API
   - Download URLs were valid in the API response
   - Backblaze retention limit (8 hours) likely passed
   - **Action needed:** Request regeneration of walk animation frames

2. Standing files show consistent opaque pixel counts across all 8 directions:
   - South: 3077
   - East: 2384
   - North: 3090
   - West: 2376
   - South-east: 2916
   - North-east: 2844
   - North-west: 2792
   - South-west: 2937
   - Range: 2376–3090 pixels (reasonable variation for 8 rotations)

3. No clipping issues detected in standing frames (alpha boxes within 128×128 bounds)

## Balance report

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Generations remaining | 4573 | 4573 | 0 |
| Generations used | 427 | 427 | 0 |

**No generation cost incurred** — the walk animation group was already completed when recording began. Only standing files were recorded from disk; walk frame downloads were not retrieved due to URL expiration.

## Summary

- **Standing files recorded:** 8/8 ✓
- **Walk animation frames:** 0/48 (expired)
- **Inventory file:** `raw_inventory.json` (8 entries, standing only)
- **Total bytes recorded:** 36,744 (standing frames only)
- **Generation cost:** 0 (no new generation)

The feminine-dark wizard standing poses are complete and verified. The walk animation frames require regeneration and re-download to complete the batch recording.
