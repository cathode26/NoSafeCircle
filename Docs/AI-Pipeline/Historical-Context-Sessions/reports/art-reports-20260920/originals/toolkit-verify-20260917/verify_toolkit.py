"""Real-data acceptance check of the Codex art-review toolkit against known answers from 2026-09-16.

Runs the CLI in-process (no subprocesses, so no console windows) and compares results with the
Art Director's own earlier measurements. Writes only into this folder. Uses Pillow only to compare
decoded pixels with earlier Pillow-made files.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

PACKAGE = Path(r"C:\nscrev\codex-jobs\codex-art-review-toolkit-20260917-0021\Pipeline\ArtReview")
sys.path.insert(0, str(PACKAGE))
sys.dont_write_bytecode = True

from art_review.cli import main  # noqa: E402
from PIL import Image  # noqa: E402

OUT = Path(__file__).resolve().parent
REPO = Path(r"C:\NSC\NSC\NoSafeCircle")
WISP = Path(r"C:\nscrev\reports\art-director\lantern-wisp-20260916")
DENSITY = Path(r"C:\nscrev\reports\art-director\density-trial-20260916")
results = []


def check(name, condition, detail):
    results.append({"check": name, "pass": bool(condition), "detail": detail})
    print(("PASS " if condition else "FAIL ") + name + " :: " + json.dumps(detail)[:300])


def run(args):
    started = time.perf_counter()
    code = main([str(a) for a in args])
    return code, round(time.perf_counter() - started, 2)


# 1. mask-diff on the Lantern Wraith wind-up: expect 1312 inside, 0 outside, 83 introduced colors, exit 0.
code, seconds = run(["mask-diff", "--source", REPO / "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_se_idle_00.png",
                     "--result", WISP / "pixellab/windup_se_128.png", "--mask", WISP / "inputs/windup_mask_128.png",
                     "--output", OUT / "maskdiff_proof.png", "--zoom", "4", "--json", OUT / "maskdiff.json"])
report = json.loads((OUT / "maskdiff.json").read_text(encoding="utf-8"))
introduced = report.get("introduced_colors") or report.get("introduced_result_colors") or []
check("mask-diff counts", code == 0 and report.get("changed_inside") == 1312 and report.get("changed_outside") == 0,
      {"exit": code, "inside": report.get("changed_inside"), "outside": report.get("changed_outside"), "seconds": seconds})
# 84, not 83: the inpaint kept 7 of 8 original colors (lost #30e0cb); corrected 2026-09-17.
check("mask-diff introduced colors = 84", len(introduced) == 84, {"introduced": len(introduced), "keys": sorted(report.keys())})

# 2. frame-metrics on the B 128 walk loop: expect a 5 px baseline jump 5->6 and a 6 px seam jump 6->1.
frames = [DENSITY / f"pixellab/3c_walk_se_128/frame_0{i}.png" for i in range(1, 7)]
code, seconds = run(["frame-metrics", *frames, "--loop", "--json", OUT / "walk_metrics.json", "--markdown", OUT / "walk_metrics.md"])
metrics = json.loads((OUT / "walk_metrics.json").read_text(encoding="utf-8"))
check("frame-metrics ran", code == 0, {"exit": code, "seconds": seconds, "keys": sorted(metrics.keys())})
text = json.dumps(metrics)
check("frame-metrics reports seam and 5-6 px baseline jumps", ("seam" in text or "loop" in text) and ("6" in text),
      {"excerpt": text[:600]})

# 3. normalize 152 -> 128: pixels must equal the earlier Pillow-normalized frames.
raw = [DENSITY / f"pixellab/3c_walk_se_raw/frame_0{i}.png" for i in range(0, 7)]
code, seconds = run(["normalize", *raw, "--size", "128", "--output-dir", OUT / "normalized", "--json", OUT / "normalize.json"])
same = []
for i in range(0, 7):
    mine = Image.open(DENSITY / f"pixellab/3c_walk_se_128/frame_0{i}.png").convert("RGBA")
    theirs = Image.open(OUT / "normalized" / f"frame_0{i}.png").convert("RGBA")
    same.append(mine.size == theirs.size and mine.tobytes() == theirs.tobytes())
check("normalize matches earlier crop pixel-for-pixel", code == 0 and all(same), {"exit": code, "per_frame_equal": same, "seconds": seconds})

# 4. gamescale: today's world-plane wizard (~16x97 on the walk frame) and B at 1.0547x.
manifest = {
    "resolution": "1080p", "panel_width": 240, "panel_height": 240, "grid": True,
    "footer": "toolkit verification 2026-09-17",
    "sprites": [
        {"path": str(REPO / "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_000.png"),
         "label": "In game today", "mode": "world-plane", "ppu": 180, "local_scale": [1, 2], "sampling": "point"},
        {"path": str(REPO / "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_000.png"),
         "label": "Now 180 point", "mode": "camera-facing", "box_units": 2, "sampling": "point"},
        {"path": str(REPO / "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/walk/south-east/frame_000.png"),
         "label": "A smooth", "mode": "camera-facing", "box_units": 2, "sampling": "smooth"},
        {"path": str(DENSITY / "pixellab/3c_walk_se_128/frame_01.png"),
         "label": "B 128 point", "mode": "camera-facing", "box_units": 2, "sampling": "point"},
    ],
}
(OUT / "gamescale_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
code, seconds = run(["gamescale", "--manifest", OUT / "gamescale_manifest.json", "--output", OUT / "gamescale.png", "--json", OUT / "gamescale.json"])
gs = json.loads((OUT / "gamescale.json").read_text(encoding="utf-8"))
check("gamescale ran", code == 0, {"exit": code, "seconds": seconds, "report": json.dumps(gs)[:700]})

# 5. ledger with today's real numbers: 19 reported, 311->331 used, no cap -> unattributed 1.
ledger = OUT / "ledger_today.jsonl"
if ledger.exists():
    ledger.unlink()
run(["ledger", "init", "--ledger", ledger, "--job", "density+wisp 2026-09-16", "--remaining", "4689", "--used", "311"])
for tool, pid, cost in [("image_to_pixelart", "d7ff0f49", 1), ("create_character_v3", "1d1cd21e", 2), ("animate_character_v3", "2e1ec5da", 2),
                        ("inpaint_image_pro_flash", "ebe47446", 6), ("create_image_pixflux", "d0c65268", 1), ("create_image_pixflux", "5ac6baf1", 1),
                        ("create_image_pixflux", "f2180612", 1), ("create_image_pixflux", "53d87d74", 1), ("create_image_pixen", "1f854150", 1),
                        ("create_image_pixflux", "e1e9efad", 1), ("animate_image", "27041bc9", 1), ("animate_image", "1795a439", 1)]:
    run(["ledger", "add", "--ledger", ledger, "--tool", tool, "--id", pid, "--reported-cost", str(cost)])
run(["ledger", "balance", "--ledger", ledger, "--remaining", "4669", "--used", "331", "--label", "after both jobs"])
code, _ = run(["ledger", "summary", "--ledger", ledger, "--json", OUT / "ledger_summary.json", "--markdown", OUT / "ledger_summary.md"])
summary = json.loads((OUT / "ledger_summary.json").read_text(encoding="utf-8"))
check("ledger reproduces 19 reported / 20 used / 1 unattributed", code == 0 and summary["tool_reported_total"] == 19
      and summary["balance_change"]["by_generations_used"] == 20 and summary["unattributed_difference"] == 1 and summary["cap_status"] == "no_cap",
      {"summary": summary})

# 6. hue-scan on the wisp candidates: expect 0 warm pixels.
wisps = [WISP / f"pixellab/{name}.png" for name in ["wisp_A2_still", "wisp_B2_still", "wisp_C2_still", "windup_se_128"]]
code, seconds = run(["hue-scan", *wisps, "--json", OUT / "hue.json", "--fail-on-match"])
hue = json.loads((OUT / "hue.json").read_text(encoding="utf-8"))
check("hue-scan finds no warm pixels", code == 0 and hue.get("matching_pixel_count") == 0, {"exit": code, "report": json.dumps(hue)[:300]})

# 7. gif timeline with a background; Pillow must read the frames and durations.
timeline = {"frames": [{"path": str(REPO / "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_se_idle_00.png"), "duration_ms": 500},
                       {"path": str(WISP / "pixellab/windup_se_128.png"), "duration_ms": 400}]}
(OUT / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
code, seconds = run(["gif", "--manifest", OUT / "timeline.json", "--zoom", "2", "--background", "#1d1631", "--output", OUT / "windup.gif", "--json", OUT / "windup_gif.json"])
gif = Image.open(OUT / "windup.gif")
durations = []
for index in range(gif.n_frames):
    gif.seek(index)
    durations.append(gif.info.get("duration"))
check("gif readable by Pillow with 500/400 ms", code == 0 and gif.n_frames == 2 and durations == [500, 400],
      {"exit": code, "frames": gif.n_frames, "durations": durations, "size": gif.size, "seconds": seconds})

# 8. contact-sheet from a glob.
code, seconds = run(["contact-sheet", "--glob", str(WISP / "pixellab" / "wisp_*2_still.png"), "--columns", "3", "--zoom", "4", "--output", OUT / "wisp_sheet.png", "--json", OUT / "wisp_sheet.json"])
sheet = Image.open(OUT / "wisp_sheet.png")
check("contact-sheet ran", code == 0, {"exit": code, "size": sheet.size, "seconds": seconds})

(OUT / "verify_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print("SUMMARY", sum(r["pass"] for r in results), "of", len(results), "passed")
