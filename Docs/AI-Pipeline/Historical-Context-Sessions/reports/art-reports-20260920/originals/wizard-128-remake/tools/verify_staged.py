"""Run NSC-095 VAL-001's assertions against the staged tree, before handing it to the Game Agent.

Usage: python verify_staged.py <stage_dir>
Exit code 0 means every assertion passed.
"""
import hashlib
import json
import os
import sys

from PIL import Image

DIRS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
KEYS = ["masculine-light", "masculine-dark", "feminine-light", "feminine-dark"]
SEL = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab128"
RAW = "Docs/Art/Wizard/Raw128"


def lower_median(v):
    s = sorted(v)
    return s[(len(s) - 1) // 2]


def main():
    stage = sys.argv[1]
    inv = json.load(open(os.path.join(stage, SEL, "source-inventory.json"), encoding="utf-8"))
    rows = {r["selected_path"]: r for r in inv["frames"]}
    fails = []

    # 1. exactly the 224 expected paths
    expected = set()
    for k in KEYS:
        for d in DIRS:
            expected.add(f"{SEL}/{k}/selected/standing/{d}.png")
            for i in range(6):
                expected.add(f"{SEL}/{k}/selected/walk/{d}/frame_{i:03d}.png")
    on_disk = set()
    for root, _dirs, files in os.walk(os.path.join(stage, SEL)):
        for f in files:
            if f.endswith(".png"):
                rel = os.path.relpath(os.path.join(root, f), stage).replace("\\", "/")
                on_disk.add(rel)
    if on_disk != expected:
        fails.append(f"path set mismatch: {len(on_disk)} on disk vs {len(expected)} expected; "
                     f"missing {sorted(expected - on_disk)[:3]}, extra {sorted(on_disk - expected)[:3]}")
    if len(expected) != 224:
        fails.append(f"expected-path count is {len(expected)}, not 224")

    # 2. geometry, transparency, corner alpha, inventory hash, recorded alpha bottom
    for rel in sorted(on_disk):
        p = os.path.join(stage, rel)
        im = Image.open(p).convert("RGBA")
        if im.size != (128, 128):
            fails.append(f"{rel}: size {im.size}")
        a = im.getchannel("A")
        w, h = im.size
        corners = [a.getpixel((0, 0)), a.getpixel((w - 1, 0)), a.getpixel((0, h - 1)), a.getpixel((w - 1, h - 1))]
        if any(c != 0 for c in corners):
            fails.append(f"{rel}: corner alpha {corners}")
        row = rows.get(rel)
        if row is None:
            fails.append(f"{rel}: absent from source-inventory.json")
            continue
        digest = hashlib.sha256(open(p, "rb").read()).hexdigest()
        if digest != row["selected_sha256"]:
            fails.append(f"{rel}: selected_sha256 mismatch")
        bottom = a.getbbox()[3]
        if row.get("alpha_bottom_y_from_top") != bottom:
            fails.append(f"{rel}: alpha_bottom_y_from_top {row.get('alpha_bottom_y_from_top')} vs pixels {bottom}")
        if not row.get("character_id") or not row.get("prompt"):
            fails.append(f"{rel}: empty character id or prompt")

    # 3. the ground-line rules, per wizard and per group
    for k in KEYS:
        gl = inv["wizards"][k]["ground_line_y_from_top"]
        cap = inv["wizards"][k]["dip_cap"]
        if inv["wizards"][k]["max_dip_below_ground_line"] > min(cap, 6):
            fails.append(f"{k}: max dip {inv['wizards'][k]['max_dip_below_ground_line']} over cap")
        pivot_y = inv["wizards"][k]["pivot"]["y"]
        if abs(pivot_y - (128 - gl) / 128) > 1e-9:
            fails.append(f"{k}: pivot y {pivot_y} does not equal (128 - {gl}) / 128")
        for d in DIRS:
            still = rows[f"{SEL}/{k}/selected/standing/{d}.png"]["alpha_bottom_y_from_top"]
            if still != gl:
                fails.append(f"{k}/{d}: standing alpha bottom {still} != ground line {gl}")
            walk = [rows[f"{SEL}/{k}/selected/walk/{d}/frame_{i:03d}.png"]["alpha_bottom_y_from_top"] for i in range(6)]
            if lower_median(walk) != gl:
                fails.append(f"{k}/{d}: walk lower median {lower_median(walk)} != ground line {gl}")
            dip = max(walk) - gl
            recorded = inv["wizards"][k]["groups"][d]["walk"]["dip_below_ground_line"]
            if dip != recorded:
                fails.append(f"{k}/{d}: dip {dip} != recorded {recorded}")
            if dip > 6:
                fails.append(f"{k}/{d}: dip {dip} over the 6 px cap")

    # 4. raw exports present, and no .meta anywhere in the staged tree
    no_raw = [f"{r['key']}/{r['group']}/{r['direction']}/{r['frame_index']}" for r in inv["frames"] if not r["raw_path"]]
    if no_raw:
        fails.append(f"{len(no_raw)} inventory rows carry no raw_path, e.g. {no_raw[:3]}")
    raw_missing = [r["raw_path"] for r in inv["frames"] if r["raw_path"] and not os.path.exists(os.path.join(stage, r["raw_path"]))]
    if raw_missing:
        fails.append(f"{len(raw_missing)} raw exports missing on disk, e.g. {raw_missing[:2]}")
    metas = []
    for root, _dirs, files in os.walk(stage):
        metas += [f for f in files if f.endswith(".meta")]
    if metas:
        fails.append(f"{len(metas)} .meta files in the staged tree")

    print(f"checked {len(on_disk)} selected PNGs, {len(inv['frames'])} inventory rows, 4 wizards")
    print("raw exports:", sum(1 for r in inv["frames"] if r["raw_path"]))
    print("identity exceptions:", len(inv["identity_exceptions"]))
    if fails:
        print(f"\nFAILURES ({len(fails)}):")
        for f in fails[:25]:
            print(" -", f)
        sys.exit(1)
    print("\nALL ASSERTIONS PASSED")


main()
