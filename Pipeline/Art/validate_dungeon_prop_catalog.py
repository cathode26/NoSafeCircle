#!/usr/bin/env python3
"""Validate NSC-078's PropCatalog.json against the PNGs it describes.

Standard library only -- json, hashlib, struct, zlib, argparse, pathlib -- because the
completion gate runs this from a clean candidate checkout inside a container with no
third-party packages. In particular there is NO Pillow, so the PNG is decoded here.

The validator READS. It never writes inside the repository: the gate rechecks tracked and
untracked state afterwards and any mutation fails validation.

Why it decodes the pixels rather than trusting the catalog: a catalog field and the file it
describes are two different artifacts, and the whole point is to catch them disagreeing. A
check that re-read the catalog's own numbers would be self-consistent by construction and
would prove nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import struct
import sys
import zlib

REQUIRED_FIELDS = (
    "id", "source_path", "source_owner_task_id", "raw_sha256", "selected_sha256",
    "crop_pad_offset_px", "repair_mask", "pixel_width", "pixel_height", "alpha_bounds_px",
    "has_transparent_pixels", "pixels_per_unit", "footprint_world_size", "intended_rooms",
    "renderer_use", "pivot_normalized", "sorting_anchor_normalized", "identity_category",
    "variant_group", "facing", "segment_role", "footprint_reference", "placement_role",
    "collision_intent", "provenance_document",
)

ALLOWED_ROOMS = {
    "RuinedEntry", "BoneArchive", "ChapelOfAsh", "LowerVault", "FinalRoom",
    "FirstWingConnector", "FutureExpansion",
}
ALLOWED_FACING = {"world_x", "world_z", "either"}
ALLOWED_SEGMENT_ROLE = {"single", "start", "middle", "end"}
ALLOWED_PLACEMENT_ROLE = {
    "focal_landmark", "supporting_cluster", "route_edge", "wall_rhythm", "threshold",
    "hazard_boundary", "background",
}
SELECTED_ROOT = "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected"
PIXELS_PER_UNIT = 64


# --------------------------------------------------------------------------- PNG


class PngError(Exception):
    pass


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(data: bytes):
    """Return (width, height, rgba_rows) for a non-interlaced 8-bit PNG."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise PngError("not a PNG")

    pos, idat, width, height = 8, [], None, None
    bit_depth = color_type = interlace = None
    palette, trns = b"", None

    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length                                   # 4 len + 4 type + body + 4 crc

        if ctype == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", body)
        elif ctype == b"PLTE":
            palette = body
        elif ctype == b"tRNS":
            trns = body
        elif ctype == b"IDAT":
            idat.append(body)
        elif ctype == b"IEND":
            break

    if width is None:
        raise PngError("no IHDR")
    if bit_depth != 8:
        raise PngError(f"unsupported bit depth {bit_depth}; only 8 is supported")
    if interlace != 0:
        raise PngError("interlaced PNGs are not supported")

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise PngError(f"unsupported colour type {color_type}")

    raw = zlib.decompress(b"".join(idat))
    stride = width * channels
    out, prev = [], bytearray(stride)
    at = 0
    for _ in range(height):
        filt = raw[at]
        line = bytearray(raw[at + 1:at + 1 + stride])
        at += 1 + stride
        if filt == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif filt == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif filt == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif filt == 4:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                upleft = prev[i - channels] if i >= channels else 0
                line[i] = (line[i] + _paeth(left, prev[i], upleft)) & 0xFF
        elif filt != 0:
            raise PngError(f"unknown filter type {filt}")
        out.append(bytes(line))
        prev = line

    rows = []
    for line in out:
        row = []
        for x in range(width):
            if color_type == 6:
                o = x * 4
                row.append((line[o], line[o + 1], line[o + 2], line[o + 3]))
            elif color_type == 2:
                o = x * 3
                row.append((line[o], line[o + 1], line[o + 2], 255))
            elif color_type == 0:
                v = line[x]
                row.append((v, v, v, 255))
            elif color_type == 4:
                o = x * 2
                row.append((line[o], line[o], line[o], line[o + 1]))
            else:                                            # palette
                idx = line[x]
                r, g, b = palette[idx * 3:idx * 3 + 3]
                a = trns[idx] if trns and idx < len(trns) else 255
                row.append((r, g, b, a))
        rows.append(row)
    return width, height, rows


def alpha_bounds(width: int, height: int, rows):
    """Bounding box of non-transparent pixels, top-left origin, or None if fully clear."""
    min_x, min_y, max_x, max_y = width, height, -1, -1
    for y in range(height):
        row = rows[y]
        for x in range(width):
            if row[x][3] != 0:
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y
    if max_x < 0:
        return None
    return {"x": min_x, "y": min_y, "width": max_x - min_x + 1, "height": max_y - min_y + 1}


# ---------------------------------------------------------------------- validate


def validate(catalog_path: pathlib.Path, repo_root: pathlib.Path):
    errors: list[str] = []

    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception as exc:                                  # noqa: BLE001
        return [f"{catalog_path}: not readable JSON: {exc}"]

    entries = catalog.get("entries")
    if not isinstance(entries, list) or not entries:
        return [f"{catalog_path}: 'entries' must be a non-empty list"]

    seen: dict[str, int] = {}
    for i, e in enumerate(entries):
        eid = e.get("id", f"<entry {i}>")
        for f in REQUIRED_FIELDS:
            if f not in e:
                errors.append(f"{eid}: missing field '{f}'")
        if eid in seen:
            errors.append(f"{eid}: duplicate catalog entry (also at index {seen[eid]})")
        seen[eid] = i

        if e.get("renderer_use") != "SpriteRenderer":
            errors.append(f"{eid}: renderer_use must be SpriteRenderer")
        if e.get("pixels_per_unit") != PIXELS_PER_UNIT:
            errors.append(f"{eid}: pixels_per_unit must be {PIXELS_PER_UNIT}")
        if e.get("facing") not in ALLOWED_FACING:
            errors.append(f"{eid}: facing {e.get('facing')!r} not allowed")
        if e.get("segment_role") not in ALLOWED_SEGMENT_ROLE:
            errors.append(f"{eid}: segment_role {e.get('segment_role')!r} not allowed")
        if e.get("placement_role") not in ALLOWED_PLACEMENT_ROLE:
            errors.append(f"{eid}: placement_role {e.get('placement_role')!r} not allowed")
        for room in e.get("intended_rooms") or []:
            if room not in ALLOWED_ROOMS:
                errors.append(f"{eid}: intended_rooms value {room!r} not allowed")
        if not (e.get("intended_rooms") or []):
            errors.append(f"{eid}: intended_rooms must not be empty")

        selected = None
        for cand in (repo_root / SELECTED_ROOT).rglob(f"{eid}.png"):
            selected = cand
            break
        if selected is None:
            errors.append(f"{eid}: no selected PNG named {eid}.png under {SELECTED_ROOT}")
            continue

        got = hashlib.sha256(selected.read_bytes()).hexdigest()
        if got != e.get("selected_sha256"):
            errors.append(f"{eid}: selected_sha256 {e.get('selected_sha256')} but file is {got}")

        raw = repo_root / str(e.get("source_path", ""))
        if not raw.is_file():
            errors.append(f"{eid}: source_path does not exist: {e.get('source_path')}")
        else:
            got_raw = hashlib.sha256(raw.read_bytes()).hexdigest()
            if got_raw != e.get("raw_sha256"):
                errors.append(f"{eid}: raw_sha256 {e.get('raw_sha256')} but file is {got_raw}")

        try:
            w, h, rows = decode_png(selected.read_bytes())
        except PngError as exc:
            errors.append(f"{eid}: {selected}: {exc}")
            continue

        if e.get("pixel_width") != w or e.get("pixel_height") != h:
            errors.append(f"{eid}: catalog says {e.get('pixel_width')}x{e.get('pixel_height')}, "
                          f"file is {w}x{h}")

        bounds = alpha_bounds(w, h, rows)
        if bounds is None:
            errors.append(f"{eid}: image is fully transparent")
        elif e.get("alpha_bounds_px") != bounds:
            errors.append(f"{eid}: alpha_bounds_px {e.get('alpha_bounds_px')} but measured {bounds}")

        transparent = any(px[3] == 0 for row in rows for px in row)
        if bool(e.get("has_transparent_pixels")) != transparent:
            errors.append(f"{eid}: has_transparent_pixels {e.get('has_transparent_pixels')} "
                          f"but measured {transparent}")

        # The pivot is the drawn ground line, not the canvas bottom. (0.5, 0) floats a prop
        # whose art stops short of the bottom edge, which is every prop in this family.
        pivot = e.get("pivot_normalized") or {}
        if bounds is not None and isinstance(pivot, dict):
            expected_y = (h - (bounds["y"] + bounds["height"])) / h
            if abs(float(pivot.get("y", -1)) - expected_y) > 0.002:
                errors.append(f"{eid}: pivot_normalized.y {pivot.get('y')} but the drawn "
                              f"ground line is {round(expected_y, 6)}")

        mask = e.get("repair_mask")
        if mask is not None:
            if not isinstance(mask, list):
                errors.append(f"{eid}: repair_mask must be null or a list of rectangles")
            else:
                for r in mask:
                    if not all(k in r for k in ("x", "y", "width", "height")):
                        errors.append(f"{eid}: repair_mask rectangle needs x, y, width, height")
                    elif (r["x"] < 0 or r["y"] < 0 or r["width"] <= 0 or r["height"] <= 0
                          or r["x"] + r["width"] > w or r["y"] + r["height"] > h):
                        errors.append(f"{eid}: repair_mask rectangle {r} falls outside {w}x{h}")

        offset = e.get("crop_pad_offset_px")
        if offset is not None and not (isinstance(offset, dict) and {"x", "y"} <= set(offset)):
            errors.append(f"{eid}: crop_pad_offset_px must be null or an object with x and y")

    # every selected PNG must have an entry, not just every entry a PNG
    on_disk = {p.stem for p in (repo_root / SELECTED_ROOT).rglob("*.png")}
    for orphan in sorted(on_disk - set(seen)):
        errors.append(f"{orphan}.png is on disk with no catalog entry")

    return errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", required=True, type=pathlib.Path)
    ap.add_argument("--repo-root", type=pathlib.Path, default=None,
                    help="defaults to the repository the catalog lives in")
    args = ap.parse_args(argv)

    catalog = args.catalog
    repo_root = args.repo_root
    if repo_root is None:
        repo_root = catalog.resolve()
        for parent in catalog.resolve().parents:
            if (parent / "Assets").is_dir():
                repo_root = parent
                break

    errors = validate(catalog, repo_root)
    if errors:
        for e in errors:
            print(f"FAIL {e}")
        print(f"\n{len(errors)} problem(s)")
        return 1

    count = len(json.loads(catalog.read_text(encoding='utf-8'))["entries"])
    print(f"OK {count} catalog entries validated against their PNGs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
