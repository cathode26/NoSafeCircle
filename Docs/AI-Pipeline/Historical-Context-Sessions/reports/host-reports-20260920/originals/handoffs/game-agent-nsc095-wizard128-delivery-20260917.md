# Handoff: commit the NSC-095 wizard 128 px art (staged and verified)

From: Art Director Agent. To: Game Agent. 2026-09-17. Contract: **NSC-095 rev 2 `b806002b7`** on local main.

I never commit to main, so the art needs you (or a crew you run) to land it. Everything is staged, hashed and
checked against VAL-001's assertions.

## What to commit

**Source tree:** `C:\nscrev\reports\art-director\wizard-128-remake\staged\`, 450 files, 3.5 MB, LF-safe (PNG and
JSON only, plus one Markdown file). Copy it over a clone's root; the paths inside already match the contract.

| Path | Count | What |
|---|---|---|
| `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128/<key>/selected/standing/<dir>.png` | 32 | the game frames |
| `.../selected/walk/<dir>/frame_000..005.png` | 192 | 6 ordered frames per facing |
| `.../PixelLab128/source-inventory.json` | 1 | per-frame provenance, per-wizard ground line, identity exceptions |
| `Docs/Art/Wizard/Raw128/<key>/...` | 224 | the raw PixelLab exports, **no `.meta`**, per AC-002 and the NSC-078 precedent |
| `Docs/Art/Wizard/PIXELLAB_128_GENERATION.md` | 1 | tools, prompts, settings, defects, spend, rejects |

**The 180 px sources and `Docs/Art/Wizard/PIXELLAB_GENERATION.md` must stay byte-identical** (AC-003). I did not
touch them; please confirm after the copy.

## The one thing I cannot do: the `.meta` files

AC-002 requires every PNG under `PixelLab128` to have a committed `.meta` importing it as
`TextureImporterShape.Texture2D`, and **never a GUID-only stub**, which imports as a cubemap (the P34 defect,
`e1ce889b0`). There are no `.meta` files in the staged tree, by design. Please mint them the way the contract
allows:

- the pipeline's deterministic default TextureImporter meta (P34), or
- Unity-minted metas from a `unity-runner` import, committed by exact path in their own commit before anything
  binds to them.

Sprite type, pivot and pixels-per-unit belong to **NSC-096**, not here.

## Verification already done, reproducible by you

```
python C:\nscrev\reports\art-director\wizard-128-remake\tools\verify_staged.py "C:\nscrev\reports\art-director\wizard-128-remake\staged"
```

It re-runs VAL-001's assertions and prints `ALL ASSERTIONS PASSED`: exactly the 224 expected paths; every PNG
128x128 with alpha 0 in all four corners; every file present once in the inventory with a matching
`selected_sha256`; every recorded `alpha_bottom_y_from_top` equal to the pixels; per wizard, the standing frames
all on `ground_line_y_from_top` and each walk group's lower median on it too; every dip at most the recorded
value and at most 6; `pivot y == (128 - ground_line_y_from_top) / 128`; a raw export for all 224; no `.meta`.

## What NSC-096 needs from this

| Wizard | `ground_line_y_from_top` | Pivot at 64 PPU |
|---|---|---|
| masculine-light | 122 | (0.5, 6/128 = 0.046875) |
| masculine-dark | 121 | (0.5, 7/128 = 0.0546875) |
| feminine-light | 120 | (0.5, 8/128 = 0.0625) |
| feminine-dark | 121 | (0.5, 7/128 = 0.0546875) |

One constant per wizard, read from the inventory, not one number for all four.

## State of Vincent's gate

**VAL-002 is not signed yet.** He has the review package (four 8-facing walk GIFs and four true-1080p-scale
sheets) and the one open question: the walk toward the camera drifts down across its cycle and snaps back at the
loop, 7 px masculine-light, 8 px masculine-dark, 6 px feminine-light, 3 px feminine-dark. If he asks for that to
be chased further, the affected south walks change and I will send you a replacement commit for those frames.

Committing now is still useful, since VAL-002 approves an exact commit. **Your call on sequencing**; tell me which
you prefer and I will note it in the plan.

## Rejects branch

`art-rejects/NSC-095`, local only, never the task branch: the masculine-dark rebuild
`2a83863a-7286-4f6c-85a5-7d85c82475d8` and its two inpaint results, and the superseded walk frames listed in the
generation record. Say the word if you want them staged for that branch too and I will lay them out the same way.

Reply to: Art Director Agent.
