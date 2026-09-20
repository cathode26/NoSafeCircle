# PixelLab Batch Recording Report
## wizard_fl_walk_128_north_r2 (North Walk Re-roll)

**Date:** 2026-09-17  
**Character ID:** 53aebb62-452d-4228-bda3-3a873a42f9eb  
**Animation Group ID:** 660311ba-196b-4dd6-b709-8217e0cf2b0c  
**Animation Name:** wizard_fl_walk_128_north_r2  
**Direction:** North  
**Frames Requested:** 6  

---

## Commands Executed

1. **`get_character(character_id="53aebb62-452d-4228-bda3-3a873a42f9eb")`**
   - Status: Completed
   - Retrieved character details and animation group frame URLs
   - Animation group `wizard_fl_walk_128_north_r2` confirmed with 6 frames

2. **`get_balance()`** (before download)
   - Credits: $30.00
   - Generations remaining: 4609
   - Generations used: 391
   - Subscription: active (Tier 2: Pixel Artisan)

3. **Frame downloads** (6 frames via HTTPS)
   - All frames downloaded successfully from PixelLab CDN
   - Saved as: `frame_00.png` through `frame_05.png`

4. **Frame analysis** (Python PIL measurements)
   - Canvas sizes verified
   - Alpha channels analyzed
   - Bounding boxes extracted
   - SHA-256 hashes computed
   - White-boot pixels counted

---

## Check 1: Canvas Sizes

All frames must be the same size.

| Frame | Width | Height | Status |
|-------|-------|--------|--------|
| 0 | 152 | 152 | ✓ |
| 1 | 152 | 152 | ✓ |
| 2 | 152 | 152 | ✓ |
| 3 | 152 | 152 | ✓ |
| 4 | 152 | 152 | ✓ |
| 5 | 152 | 152 | ✓ |

**Result:** All 6 frames are **152×152 pixels** (uniform canvas).

---

## Check 2: Alpha Bottom Y Values

Vertical position of the alpha bounding box lower edge per frame.

| Frame | Bottom Y | |
|-------|----------|---|
| 0 | 126 | |
| 1 | 129 | |
| 2 | 128 | |
| 3 | 123 | |
| 4 | 127 | |
| 5 | 130 | |

**Min:** 123  
**Max:** 130  
**Range:** 7 pixels (difference from min to max)

---

## Check 3: White-Boot Check

Count of pixels with alpha > 0 where red, green, and blue are all > 190, listed by color.

| Frame | Total | #fddaca | #fbe4d5 | Other | Colors |
|-------|-------|---------|---------|-------|--------|
| 0 | 10 | 10 | — | — | 1 |
| 1 | 10 | 2 | 8 | — | 2 |
| 2 | 4 | 4 | — | — | 1 |
| 3 | 4 | 2 | 2 | — | 2 |
| 4 | 7 | 7 | — | — | 1 |
| 5 | 11 | 4 | 7 | — | 2 |

**Total across animation:** 46 white-boot pixels  
**Primary color:** #fddaca (warm beige, 27 pixels)  
**Secondary color:** #fbe4d5 (lighter beige, 19 pixels)  

This boot-top edge remains consistent with expected light boot coloring.

---

## Check 4: Alpha Bounding Box Edge Contact

Detection of alpha bounding box edges touching canvas boundaries (0 or 152).

| Frame | Left (0?) | Top (0?) | Right (152?) | Bottom (152?) | Status |
|-------|-----------|----------|--------------|---------------|--------|
| 0 | No | No | No | No | Interior ✓ |
| 1 | No | No | No | No | Interior ✓ |
| 2 | No | No | No | No | Interior ✓ |
| 3 | No | No | No | No | Interior ✓ |
| 4 | No | No | No | No | Interior ✓ |
| 5 | No | No | No | No | Interior ✓ |

**Result:** No frames touch canvas edges. All bounding boxes are interior (good padding).

---

## Check 5: SHA-256 Hash Prefixes (First 16 Characters)

For duplicate frame detection.

| Frame | Filename | SHA-256 (first 16 chars) |
|-------|----------|-------------------------|
| 0 | frame_00.png | 636709e169e414b7 |
| 1 | frame_01.png | 8b6c1b62591f516d |
| 2 | frame_02.png | f8fc0f90646ef22c |
| 3 | frame_03.png | a821dd09090f481f |
| 4 | frame_04.png | c3e91903dd32faf8 |
| 5 | frame_05.png | faac657c63d8029c |

**Result:** All 6 SHA-256 prefixes are unique. No duplicate frames detected.

---

## Summary

✓ **6 frames downloaded:** All present, 152×152px canvas  
✓ **Consistent sizing:** No variation in dimensions  
✓ **Vertical coherence:** 7-pixel range in bottom-y alignment (frames 123–130)  
✓ **Boot coloring:** Expected beige tones (#fddaca, #fbe4d5) at boot top  
✓ **Padding:** No content touching canvas edges  
✓ **Uniqueness:** No duplicate frames; all SHA-256 prefixes distinct  

**Status:** PASS — Animation batch is complete and valid.

---

## Files Generated

- `record.json` — Full measurements and metadata per frame
- `frame_00.png` through `frame_05.png` — Raw PNG exports
- `REPORT.md` — This report
