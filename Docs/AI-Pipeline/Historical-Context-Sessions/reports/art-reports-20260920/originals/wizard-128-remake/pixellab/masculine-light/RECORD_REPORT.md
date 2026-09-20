# PixelLab Batch Recording Report

## Batch Information

- **Character**: masculine-light wizard, 128 px
- **Character ID**: 1d1cd21e-dd13-4bcc-9e0d-4c56f84e5e80
- **Animation Group**: wizard_ml_walk_128
- **Animation Group ID**: f925b6a1-b6e1-419a-a474-bf2128114db4
- **Recorded UTC**: 2026-09-17T21:15:45.232064Z

## Download Summary

- **Standing images**: 8 files (8 directions)
- **Walk animation frames**: 48 frames (8 directions x 6 frames)
- **Total files**: 56

## Image Sizes

| Size | Count |
|------|-------|
| 128x128 | 8 |
| 148x148 | 6 |
| 152x152 | 30 |
| 156x156 | 6 |
| 160x160 | 6 |

## Standing Images Analysis

All 8 standing images (128x128) were successfully downloaded with RGBA color mode.

## Walk Animation Analysis by Direction

### south

- **Frame count**: 6
- **Frames size**: Not uniform across directions (see size table)
- **Alpha bbox bottom (alpha_bottom_y_from_top)**:
  - Frame 0-5: [126, 131, 133, 133, 132, 136]
  - Min: 126, Max: 136
  - **Vertical drift**: 10 pixels
- **Frame hash (first 16 chars)**:
  - First frame (f00): `225a5e28243d2a20...`
  - Last frame (f05): `bb9c1893ed212fbc...`
  - Identical: No

### east

- **Frame count**: 6
- **Frames size**: Not uniform across directions (see size table)
- **Alpha bbox bottom (alpha_bottom_y_from_top)**:
  - Frame 0-5: [129, 129, 127, 127, 127, 128]
  - Min: 127, Max: 129
  - **Vertical drift**: 2 pixels
- **Frame hash (first 16 chars)**:
  - First frame (f00): `c4cfecc5d07cdc9a...`
  - Last frame (f05): `956aafcaf772166e...`
  - Identical: No

### north

- **Frame count**: 6
- **Frames size**: Not uniform across directions (see size table)
- **Alpha bbox bottom (alpha_bottom_y_from_top)**:
  - Frame 0-5: [128, 126, 129, 127, 125, 128]
  - Min: 125, Max: 129
  - **Vertical drift**: 4 pixels
- **Frame hash (first 16 chars)**:
  - First frame (f00): `3447207c6b10951e...`
  - Last frame (f05): `c26f16f22292ae01...`
  - Identical: No

### west

- **Frame count**: 6
- **Frames size**: Not uniform across directions (see size table)
- **Alpha bbox bottom (alpha_bottom_y_from_top)**:
  - Frame 0-5: [129, 129, 128, 128, 129, 129]
  - Min: 128, Max: 129
  - **Vertical drift**: 1 pixels
- **Frame hash (first 16 chars)**:
  - First frame (f00): `13c015e9cd131edb...`
  - Last frame (f05): `9e92bac9d4c845c6...`
  - Identical: No

### south-east

- **Frame count**: 6
- **Frames size**: Not uniform across directions (see size table)
- **Alpha bbox bottom (alpha_bottom_y_from_top)**:
  - Frame 0-5: [126, 125, 124, 124, 125, 128]
  - Min: 124, Max: 128
  - **Vertical drift**: 4 pixels
- **Frame hash (first 16 chars)**:
  - First frame (f00): `bf8c0f5492864332...`
  - Last frame (f05): `a26c5d34b91bf875...`
  - Identical: No

### north-east

- **Frame count**: 6
- **Frames size**: Not uniform across directions (see size table)
- **Alpha bbox bottom (alpha_bottom_y_from_top)**:
  - Frame 0-5: [127, 129, 129, 126, 124, 125]
  - Min: 124, Max: 129
  - **Vertical drift**: 5 pixels
- **Frame hash (first 16 chars)**:
  - First frame (f00): `45acb90571ab5d19...`
  - Last frame (f05): `928bddaa12e0d135...`
  - Identical: No

### north-west

- **Frame count**: 6
- **Frames size**: Not uniform across directions (see size table)
- **Alpha bbox bottom (alpha_bottom_y_from_top)**:
  - Frame 0-5: [123, 127, 126, 123, 122, 123]
  - Min: 122, Max: 127
  - **Vertical drift**: 5 pixels
- **Frame hash (first 16 chars)**:
  - First frame (f00): `601c727564d2803d...`
  - Last frame (f05): `ec8fac2eb7623efb...`
  - Identical: No

### south-west

- **Frame count**: 6
- **Frames size**: Not uniform across directions (see size table)
- **Alpha bbox bottom (alpha_bottom_y_from_top)**:
  - Frame 0-5: [127, 126, 126, 125, 126, 129]
  - Min: 125, Max: 129
  - **Vertical drift**: 4 pixels
- **Frame hash (first 16 chars)**:
  - First frame (f00): `fe46ef11e1c3aa92...`
  - Last frame (f05): `19ad058a9f679927...`
  - Identical: No

## Clipping Detection (Alpha Bbox vs Canvas)

No files have alpha bbox touching canvas edges.

## Balance Report

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Generations Remaining | 4642 | 4638 | -4 |
| Generations Used | 358 | 362 | +4 |

## Anomalies & Issues

No anomalies detected.

## Files Generated

- **Inventory**: `raw_inventory.json` (56 frame entries)
- **Report**: `RECORD_REPORT.md` (this file)
- **Standing images**: `standing_raw/*.png` (8 files, 128x128)
- **Walk frames**: `walk/<direction>/frame_XX.png` (48 files, various sizes)

