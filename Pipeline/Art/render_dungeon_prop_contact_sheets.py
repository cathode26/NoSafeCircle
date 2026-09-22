#!/usr/bin/env python3
"""Render NSC-078 review contact sheets: native pixels, world scale, gameplay density.

Three panels per sheet, because a prop can be right in one and wrong in another:

  1. NATIVE  - every sprite at 1:1 and at 3x. Defects in a 64 px prop are invisible at 1x,
               and 3x is where a stray lantern or a wrong material shows.
  2. WORLD    - each sprite beside the approved 2x2-world-unit wizard box (about 135 px at
               1080p) and the 3.0-unit door-opening proxy, so "is it the right SIZE" is
               answered against something approved rather than against taste.
  3. DENSITY  - the gameplay camera: orthographic size 8 at the recorded Game view
               resolution, which is the only panel that answers "can a player read it".

This is a review tool, not a gate tool: it uses Pillow. The two validators are standard
library only because they run in a container that has no third-party packages; this one
does not run there. It says so clearly rather than failing obscurely if Pillow is absent.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

try:
    from PIL import Image, ImageDraw
except ImportError:                                           # pragma: no cover
    sys.exit("render_dungeon_prop_contact_sheets.py needs Pillow. It is a review tool and is "
             "not part of the completion gate; the two validate_* scripts are stdlib-only.")

PIXELS_PER_UNIT = 64
WIZARD_BOX_UNITS = 2.0
DOOR_OPENING_UNITS = 3.0
ORTHO_SIZE = 8.0
BG = (26, 22, 32, 255)
INK = (226, 218, 236, 255)
DIM = (150, 142, 168, 255)


def load(entry, repo_root: pathlib.Path):
    root = repo_root / "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected"
    for p in root.rglob(f"{entry['id']}.png"):
        return Image.open(p).convert("RGBA")
    raise SystemExit(f"{entry['id']}: no selected PNG under {root}")


def _checker(draw, x, y, w, h):
    for cy in range(y, y + h, 8):
        for cx in range(x, x + w, 8):
            if ((cx - x) // 8 + (cy - y) // 8) % 2 == 0:
                draw.rectangle([cx, cy, min(cx + 7, x + w - 1), min(cy + 7, y + h - 1)],
                               fill=(44, 38, 52, 255))


def panel_native(images, scale=3, pad=24, label=26):
    w = sum(i.width * scale for _, i in images) + pad * (len(images) + 1)
    h = max(i.height * scale for _, i in images) + pad * 2 + label * 2
    sheet = Image.new("RGBA", (w, h), BG)
    d = ImageDraw.Draw(sheet)
    d.text((pad, 6), f"1. NATIVE PIXELS at {scale}x", fill=INK)
    x = pad
    for name, im in images:
        big = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        y = pad + label
        _checker(d, x, y, big.width, big.height)
        sheet.alpha_composite(big, (x, y))
        d.text((x, y + big.height + 4), f"{name}  {im.width}x{im.height}", fill=DIM)
        x += big.width + pad
    return sheet


def panel_world(images, pad=24, label=26, screen_h=1080):
    """Each prop beside the approved wizard box and the door-opening proxy."""
    px_per_unit_on_screen = screen_h / (ORTHO_SIZE * 2.0)
    wizard_px = int(WIZARD_BOX_UNITS * px_per_unit_on_screen)
    door_px = int(DOOR_OPENING_UNITS * px_per_unit_on_screen)
    scale = px_per_unit_on_screen / PIXELS_PER_UNIT

    shots = [(n, im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                           Image.NEAREST)) for n, im in images]
    h = max([wizard_px] + [i.height for _, i in shots]) + pad * 2 + label * 2
    w = door_px + wizard_px + sum(i.width for _, i in shots) + pad * (len(shots) + 3)

    sheet = Image.new("RGBA", (w, h), BG)
    d = ImageDraw.Draw(sheet)
    d.text((pad, 6), f"2. WORLD SCALE at {screen_h}p, ortho size {ORTHO_SIZE} "
                     f"({px_per_unit_on_screen:.1f} screen px per world unit)", fill=INK)
    base = h - pad

    d.rectangle([pad, base - door_px, pad + int(door_px * 0.25), base], outline=(120, 90, 150, 255))
    d.text((pad, base + 2), f"door opening {DOOR_OPENING_UNITS}u", fill=DIM)
    x = pad + int(door_px * 0.25) + pad

    d.rectangle([x, base - wizard_px, x + wizard_px, base], outline=(150, 120, 90, 255))
    d.text((x, base + 2), f"wizard box {WIZARD_BOX_UNITS}x{WIZARD_BOX_UNITS}u", fill=DIM)
    x += wizard_px + pad

    for name, im in shots:
        sheet.alpha_composite(im, (x, base - im.height))
        d.text((x, base + 2), name, fill=DIM)
        x += im.width + pad
    return sheet


def panel_density(images, pad=24, label=26, screen_h=1080):
    """1:1 gameplay pixels -- what the player actually resolves."""
    scale = (screen_h / (ORTHO_SIZE * 2.0)) / PIXELS_PER_UNIT
    shots = [(n, im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                           Image.NEAREST)) for n, im in images]
    w = sum(i.width for _, i in shots) + pad * (len(shots) + 1)
    h = max(i.height for _, i in shots) + pad * 2 + label * 2
    sheet = Image.new("RGBA", (w, h), BG)
    d = ImageDraw.Draw(sheet)
    d.text((pad, 6), f"3. GAMEPLAY DENSITY -- as drawn on a {screen_h}p screen", fill=INK)
    x = pad
    for name, im in shots:
        sheet.alpha_composite(im, (x, pad + label))
        d.text((x, pad + label + im.height + 4), name, fill=DIM)
        x += im.width + pad
    return sheet


def stack(panels, pad=18):
    w = max(p.width for p in panels) + pad * 2
    h = sum(p.height for p in panels) + pad * (len(panels) + 1)
    out = Image.new("RGBA", (w, h), BG)
    y = pad
    for p in panels:
        out.alpha_composite(p, (pad, y))
        y += p.height + pad
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--ids", nargs="*", default=None, help="explicit ids (the style pilot)")
    ap.add_argument("--family", default=None, help="render one family instead")
    ap.add_argument("--screen-height", type=int, default=1080)
    args = ap.parse_args(argv)

    repo_root = args.catalog.resolve()
    for parent in args.catalog.resolve().parents:
        if (parent / "Assets").is_dir():
            repo_root = parent
            break

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    entries = catalog["entries"]
    if args.ids:
        wanted = {i: None for i in args.ids}
        entries = [e for e in entries if e["id"] in wanted]
        missing = set(args.ids) - {e["id"] for e in entries}
        if missing:
            return int(bool(print(f"not in the catalog: {sorted(missing)}"))) or 1
    elif args.family:
        entries = [e for e in entries
                   if pathlib.PurePosixPath(e["source_path"]).parent.name == args.family]

    if not entries:
        print("no entries selected; refusing to render an empty sheet")
        return 1

    images = [(e["id"], load(e, repo_root)) for e in entries]
    sheet = stack([panel_native(images),
                   panel_world(images, screen_h=args.screen_height),
                   panel_density(images, screen_h=args.screen_height)])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)
    print(f"wrote {args.out} ({sheet.width}x{sheet.height}) from {len(images)} sprites")
    return 0


if __name__ == "__main__":
    sys.exit(main())
