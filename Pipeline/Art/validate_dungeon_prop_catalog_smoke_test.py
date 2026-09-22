#!/usr/bin/env python3
"""Smoke test for validate_dungeon_prop_catalog.py.

Standard library only, and every fixture is written inside a tempfile.TemporaryDirectory
OUTSIDE the repository: the completion gate rechecks tracked and untracked state after this
runs, and any repository mutation fails validation.

The important half is not that a good catalog passes. It is that each guard FAILS, and fails
for its OWN reason. A guard nobody has tried to break is a claim, not evidence -- and a
negative test that asserts only "it failed" will happily pass on an earlier, unrelated
refusal.
"""

from __future__ import annotations

import copy
import json
import pathlib
import struct
import sys
import tempfile
import zlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import validate_dungeon_prop_catalog as V  # noqa: E402

SELECTED = "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/Source/selected/furnishings"
RAW = "Docs/Art/Environment/Props/Raw/furnishings"


def write_png(path: pathlib.Path, width: int, height: int, opaque_box) -> None:
    """Write an 8-bit RGBA PNG; opaque_box is (x0, y0, x1, y1) inclusive, rest transparent."""
    x0, y0, x1, y1 = opaque_box
    raw = bytearray()
    for y in range(height):
        raw.append(0)                                        # filter type 0
        for x in range(width):
            inside = x0 <= x <= x1 and y0 <= y <= y1
            raw += bytes((200, 60, 90, 255) if inside else (0, 0, 0, 0))

    def chunk(tag: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw)))
        + chunk(b"IEND", b""))


def build(root: pathlib.Path):
    """A repo-shaped fixture with one prop whose catalog entry is correct."""
    w = h = 16
    box = (4, 2, 11, 12)                                     # 8x11 opaque, 3 clear rows below
    sel = root / SELECTED / "fx_prop.png"
    raw = root / RAW / "fx_prop.png"
    write_png(sel, w, h, box)
    write_png(raw, w, h, box)

    import hashlib
    entry = {
        "id": "fx_prop",
        "source_path": f"{RAW}/fx_prop.png",
        "source_owner_task_id": "NSC-078",
        "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "selected_sha256": hashlib.sha256(sel.read_bytes()).hexdigest(),
        "crop_pad_offset_px": None,
        "repair_mask": None,
        "pixel_width": w,
        "pixel_height": h,
        "alpha_bounds_px": {"x": 4, "y": 2, "width": 8, "height": 11},
        "has_transparent_pixels": True,
        "pixels_per_unit": 64,
        "footprint_world_size": {"x": 1.0, "z": 1.0, "h": 1.0},
        "intended_rooms": ["BoneArchive"],
        "renderer_use": "SpriteRenderer",
        "pivot_normalized": {"x": 0.5, "y": round((h - (2 + 11)) / h, 6)},
        "sorting_anchor_normalized": {"x": 0.5, "y": round((h - (2 + 11)) / h, 6)},
        "identity_category": "books_or_scrolls",
        "variant_group": "fx",
        "facing": "either",
        "segment_role": "single",
        "footprint_reference": "fixture",
        "placement_role": "supporting_cluster",
        "collision_intent": "decorative_none",
        "provenance_document": "Docs/Art/Environment/PROPS_PIXELLAB_GENERATION.md",
    }
    return {"schema_version": 1, "owner_task_id": "NSC-078", "pixels_per_unit": 64,
            "entries": [entry]}


def run_case(root: pathlib.Path, catalog: dict):
    path = root / "Assets/NoSafeCircle/DoorPrototype/Art/Environment/Props/PropCatalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return V.validate(path, root)


def main() -> int:
    failures = []

    with tempfile.TemporaryDirectory(prefix="nsc078-catalog-smoke-") as tmp:
        root = pathlib.Path(tmp)
        good = build(root)

        errors = run_case(root, good)
        if errors:
            failures.append(f"a correct catalog was rejected: {errors}")

        # Each case below MUST fail, and the assertion names the substring that proves it
        # failed for its own reason rather than on some earlier refusal.
        cases = [
            ("selected_sha256 drift", "selected_sha256",
             lambda c: c["entries"][0].__setitem__("selected_sha256", "0" * 64)),
            ("raw_sha256 drift", "raw_sha256",
             lambda c: c["entries"][0].__setitem__("raw_sha256", "0" * 64)),
            ("wrong pixel size", "file is",
             lambda c: c["entries"][0].__setitem__("pixel_width", 99)),
            ("wrong alpha bounds", "alpha_bounds_px",
             lambda c: c["entries"][0].__setitem__(
                 "alpha_bounds_px", {"x": 0, "y": 0, "width": 1, "height": 1})),
            ("pivot pinned to the canvas bottom", "ground line",
             lambda c: c["entries"][0].__setitem__("pivot_normalized", {"x": 0.5, "y": 0.0})),
            ("wrong pixels_per_unit", "pixels_per_unit must be",
             lambda c: c["entries"][0].__setitem__("pixels_per_unit", 180)),
            ("disallowed room", "not allowed",
             lambda c: c["entries"][0].__setitem__("intended_rooms", ["Nowhere"])),
            ("disallowed facing", "facing", lambda c: c["entries"][0].__setitem__("facing", "sideways")),
            ("missing required field", "missing field",
             lambda c: c["entries"][0].pop("collision_intent")),
            ("repair_mask outside the image", "falls outside",
             lambda c: c["entries"][0].__setitem__(
                 "repair_mask", [{"x": 0, "y": 0, "width": 999, "height": 2}])),
            ("duplicate entry", "duplicate",
             lambda c: c["entries"].append(copy.deepcopy(c["entries"][0]))),
            ("png on disk with no entry", "no catalog entry",
             lambda c: c["entries"].clear() or c["entries"].append(
                 dict(good["entries"][0], id="fx_other"))),
        ]

        for label, expect, mutate in cases:
            bad = copy.deepcopy(good)
            mutate(bad)
            errors = run_case(root, bad)
            if not errors:
                failures.append(f"{label}: validator PASSED a catalog it should reject")
            elif not any(expect in e for e in errors):
                failures.append(
                    f"{label}: rejected, but for the wrong reason -- expected {expect!r}, got {errors}")

        # the validator must not write inside the tree it validates
        before = {p.relative_to(root).as_posix(): p.stat().st_mtime_ns
                  for p in root.rglob("*") if p.is_file() and p.suffix == ".png"}
        run_case(root, good)
        after = {p.relative_to(root).as_posix(): p.stat().st_mtime_ns
                 for p in root.rglob("*") if p.is_file() and p.suffix == ".png"}
        if before != after:
            failures.append("the validator mutated PNG files while validating")

    if failures:
        for f in failures:
            print(f"FAIL {f}")
        print(f"\n{len(failures)} smoke-test failure(s)")
        return 1

    print("OK smoke test: 1 accepted catalog, 12 guards each refused for its own reason, "
          "no fixture written outside the temporary directory")
    return 0


if __name__ == "__main__":
    sys.exit(main())
