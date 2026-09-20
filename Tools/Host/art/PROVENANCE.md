# Art-review toolkit: provenance

`C:\nscrev\art-tools\ArtReview\` is a byte-exact export (`git archive`) of `Pipeline/ArtReview/`. The source is:
- commit `50b98276d902e4000535da27eb654b3899aaf405`;
- branch `codex/codex-art-review-toolkit-20260917-0021`;
- clone `C:\nscrev\codex-jobs\codex-art-review-toolkit-20260917-0021`, based on local main `17fbcdfcdc9e591270245e12f6d34bb914f157e5`.

It is accepted by the Art Director Agent on 2026-09-17 and stays here until the Game Agent brings it into the repository. Don't edit this copy; change the branch and re-export instead.

## What it is

A Python standard-library CLI for review material only; it never calls PixelLab and never modifies inputs. Subcommands:
- `gamescale`: true-screen-scale panels through the fixed camera (Euler 30,-45,0, orthographic size 8), for camera-facing or world-plane sprites, with point or smooth sampling;
- `contact-sheet`
- `gif` (timelines and motion scenes)
- `mask-diff`: proves an inpaint changed only masked pixels;
- `frame-metrics`: opaque counts, bounding boxes, and baseline or loop-seam jumps;
- `hue-scan`: for example the "no fire colors" check;
- `normalize`: lossless center crop/pad;
- `ledger`: per-job PixelLab spend with unattributed-difference and cap status.

Usage: `ArtReview\README.md`. Run from `C:\nscrev\art-tools\ArtReview`: `python -B -m art_review <subcommand> --help`.

## Approval and history

- Approved by Vincent on 2026-09-17 ("give all the agents everything they want"; board row H-20260917-05). Built by one Codex "do" job in Docker, with fix rounds on the same branch.
- Spec: `C:\nscrev\codex-jobs\codex-art-review-toolkit-20260917-0021.prompt.md`; fix specs `...-fix1.prompt.md`, `...-fix2.prompt.md`; logs alongside.

| Round | Head | Codex review | Result |
|---|---|---|---|
| Build | `3b0d2d1a0` | `C:\nscrev\codex-jobs\codex-review-art-review-toolkit-20260917-0043\CODEX_VERDICT.json` | FIX_FIRST: 9 findings, including a blocking one (an output could overwrite an input) |
| Fix 1 | `f6b810601` | `...\codex-review-art-review-toolkit-r2-20260917-0113\CODEX_VERDICT.json` | FIX_FIRST: all 9 fixed; 1 new minor (ledger aggregate overflow to Infinity) |
| Fix 2 | `50b98276d` | `...\codex-review-art-review-toolkit-r3-20260917-0131\CODEX_VERDICT.json` | FIX_FIRST: overflow fixed; 1 new minor (see known issue) |

**Astra advice** (third send-back; Vincent's rule "When things go back, Ask Codex, use a Astra for advice"; gpt-6-astra, xhigh, read-only), report `C:\nscrev\codex-jobs\codex-advice-art-review-toolkit-20260917-0140.report.md`:
- ROOT CAUSE: later reviews found distinct pre-existing numeric edge cases, not regressions.
- NEXT STEP: accept `50b98276d` with the known issue documented.
- NEEDS VINCENT: no.

## Checks at the accepted head

- 38/38 unit tests pass in Docker (Linux), on the Windows host, and from this exported copy.
- Windows-only probes: output paths that alias an input through case, forward slashes, 8.3 short names or dot segments are refused with the input unchanged (`C:\nscrev\reports\art-director\toolkit-verify-20260917\windows_collision_probe.py`).
- Real-art acceptance, 10/10 against known answers from the 2026-09-16 art jobs (`...\toolkit-verify-20260917\verify_toolkit.py`, `verify_results.json`):
  - mask-diff 1312 inside / 0 outside with 84 introduced colors;
  - normalize 152 to 128 pixel-identical to an independent crop;
  - world-plane wizard 16x97 px;
  - ledger 19 reported / 20 used / 1 unattributed;
  - GIF 500/400 ms;
  - 5 and 6 px baseline flags;
  - hue-scan 0 warm pixels on the wisps;
  - contact sheet.

## Known issue (accepted)

An externally edited ledger containing an enormous integer cost (for example 10**400) can exit 1 with a Python traceback instead of exit 2 naming the line. Validation still fails before any summary output or append, so no wrong number is reported. The toolkit's own `ledger` commands can't store such a value (costs are bounded to 0..1000000), and real PixelLab costs are 1-40.
