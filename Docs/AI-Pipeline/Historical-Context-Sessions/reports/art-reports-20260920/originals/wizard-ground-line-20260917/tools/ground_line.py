"""
ground_line.py — wizard ground-line normalizer (NSC-095 tooling).

Measures the feet/head rows of a set of standing-facing stills and (optionally)
walk-cycle frame sequences for one wizard "key", picks a single ground-line row
shared by every direction and both groups (standing + walk), shifts every frame
by a whole-pixel vertical offset so its group's reference row lands on that
ground line, and writes the normalized frames plus a ground_line.json record
that a Unity importer (or a later audit) can consume.

No PixelLab calls. No network. Stdlib + Pillow only.

Row convention: rows are 0-based from the TOP of the canvas (row 0 = topmost).
"feet_row" is therefore the LARGEST row index with an opaque pixel (visually
lowest), and "head_row" is the SMALLEST row index with an opaque pixel
(visually highest) — matching the spec's "lowest"/"highest" wording.

CLI:
    python ground_line.py plan  --key <name> --stills <dir>
                                 [--walk <direction>=<dir> ...]
                                 --out <dir> [--canvas 128] [--top-margin 0]
                                 [--bottom-margin 2] [--max-dip 6] [--no-max-dip]
    python ground_line.py check --json <out>\\ground_line.json

Round 2 (2026-09-17): added --bottom-margin (keeps the ground line off the
canvas' bottom edge) and per-group dip measurement/--max-dip capping (a walk
frame's forward foot is drawn lower on screen by design; the dip below the
shared ground line is measured per direction+group and capped rather than
silently accepted). See TOOL_REPORT.md, "Round 2".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

DIRECTIONS = [
    "south", "south-east", "east", "north-east",
    "north", "north-west", "west", "south-west",
]
DIRECTION_SET = frozenset(DIRECTIONS)


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class GroundLineError(Exception):
    """Base class for all errors this tool raises deliberately."""


class UnknownDirectionError(GroundLineError):
    pass


class CanvasMismatchError(GroundLineError):
    pass


class EmptyFrameError(GroundLineError):
    pass


class BoundsError(GroundLineError):
    pass


class ClipError(GroundLineError):
    pass


class ShiftIntegrityError(GroundLineError):
    pass


class MaxDipExceededError(GroundLineError):
    pass


class CheckError(GroundLineError):
    pass


def _group_label(direction: str, group: str) -> str:
    return f"{direction}:{group}"


# --------------------------------------------------------------------------
# Hashing
# --------------------------------------------------------------------------

def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: Path) -> str:
    return sha256_of_bytes(Path(path).read_bytes())


# --------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------

def load_rgba(path: Path) -> Image.Image:
    with Image.open(path) as img:
        # .convert() forces a full load, so the returned image no longer
        # depends on the underlying file handle once we exit this block.
        return img.convert("RGBA")


def measure(img: Image.Image, label: str = "<image>") -> dict:
    """Measure one RGBA frame.

    Returns a dict with w, h, feet_row, head_row, opaque_pixels, bbox
    (left, upper, right, lower — PIL convention: upper/left inclusive,
    right/lower exclusive).
    """
    w, h = img.size
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if bbox is None:
        raise EmptyFrameError(f"{label}: frame has no opaque pixels (alpha bbox is empty)")
    left, upper, right, lower = bbox
    feet_row = lower - 1
    head_row = upper
    hist = alpha.histogram()
    opaque_pixels = sum(hist[1:256])
    return {
        "w": w, "h": h,
        "feet_row": feet_row, "head_row": head_row,
        "opaque_pixels": opaque_pixels,
        "bbox": (left, upper, right, lower),
    }


def lower_median(values):
    """The lower median: sorted(values)[(n - 1) // 2]."""
    if not values:
        raise ValueError("lower_median() of an empty sequence")
    s = sorted(values)
    n = len(s)
    return s[(n - 1) // 2]


def compute_pivot(h: int, g: int) -> dict:
    """pivot for ground line row `g` (inclusive) on a canvas of height `h`.

    g_excl = g + 1 (the NSC-077 alpha_bottom_y_from_top convention).
    pivot = (0.5, (h - g_excl) / h).
    Sanity case: h=176, g=131 -> g_excl=132 -> pivot y = 44/176 = 0.25.
    """
    g_excl = g + 1
    return {"x": 0.5, "y": (h - g_excl) / h}


# --------------------------------------------------------------------------
# Shifting
# --------------------------------------------------------------------------

def shift_image(img: Image.Image, dy: int, label: str = "<image>") -> Image.Image:
    """Shift `img` vertically by `dy` whole pixels (positive = down), with a
    fully transparent fill, and verify the shift was lossless:
      - refuses (raises ClipError) if any opaque pixel would leave the canvas;
      - asserts (raises ShiftIntegrityError) that the opaque pixel count is
        unchanged and the alpha bbox moved by exactly dy afterwards.
    """
    w, h = img.size
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if bbox is None:
        raise EmptyFrameError(f"{label}: frame has no opaque pixels (alpha bbox is empty)")
    left, upper, right, lower = bbox

    new_upper = upper + dy
    new_lower = lower + dy  # exclusive
    if new_upper < 0 or new_lower > h:
        raise ClipError(
            f"{label}: shift dy={dy} would move opaque pixels outside the canvas "
            f"(rows {upper}-{lower - 1} -> {new_upper}-{new_lower - 1}, canvas height {h})"
        )

    opaque_before = sum(alpha.histogram()[1:256])

    new_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    new_img.paste(img, (0, dy))

    new_alpha = new_img.split()[-1]
    opaque_after = sum(new_alpha.histogram()[1:256])
    if opaque_after != opaque_before:
        raise ShiftIntegrityError(
            f"{label}: opaque pixel count changed during shift dy={dy} "
            f"({opaque_before} -> {opaque_after})"
        )

    new_bbox = new_alpha.getbbox()
    expected_bbox = (left, upper + dy, right, lower + dy)
    if new_bbox != expected_bbox:
        raise ShiftIntegrityError(
            f"{label}: bbox after shift dy={dy} is {new_bbox}, expected {expected_bbox}"
        )

    return new_img


# --------------------------------------------------------------------------
# Frame collection
# --------------------------------------------------------------------------

class Frame:
    """One measured input frame, still un-shifted."""

    def __init__(self, group, direction, name, path):
        self.group = group          # "standing" | "walk"
        self.direction = direction
        self.name = name            # file basename, e.g. "south.png" / "frame_00.png"
        self.path = Path(path)
        self.measure = None         # filled in by measure_all()
        self.reference_row = None   # filled in after grouping
        self.dy = None
        self.new_img = None

    @property
    def frame_id(self):
        if self.group == "standing":
            return f"standing:{self.direction}"
        return f"walk:{self.direction}:{self.name}"


def collect_stills(stills_dir: Path) -> list:
    frames = []
    for path in sorted(Path(stills_dir).glob("*.png")):
        direction = path.stem
        if direction not in DIRECTION_SET:
            raise UnknownDirectionError(
                f"unknown direction '{direction}' in stills file {path}"
            )
        frames.append(Frame("standing", direction, path.name, path))
    return frames


def collect_walk(walk_specs: dict) -> list:
    frames = []
    for direction, folder in walk_specs.items():
        if direction not in DIRECTION_SET:
            raise UnknownDirectionError(
                f"unknown direction '{direction}' in --walk {direction}={folder}"
            )
        folder_path = Path(folder)
        frame_paths = sorted(folder_path.glob("frame_*.png"), key=lambda p: p.name)
        if not frame_paths:
            raise GroundLineError(f"--walk {direction}={folder}: no frame_*.png files found")
        for p in frame_paths:
            frames.append(Frame("walk", direction, p.name, p))
    return frames


def measure_all(frames: list, canvas: int) -> None:
    expected = (canvas, canvas)
    for f in frames:
        img = load_rgba(f.path)
        if img.size != expected:
            raise CanvasMismatchError(
                f"{f.path}: size {img.size} != expected canvas {expected}"
            )
        f.measure = measure(img, label=str(f.path))
        f._img = img


# --------------------------------------------------------------------------
# Reference rows / bounds
# --------------------------------------------------------------------------

def compute_references(frames: list) -> dict:
    """Returns {(direction, group): reference_row}."""
    references = {}
    by_group_dir = {}
    for f in frames:
        by_group_dir.setdefault((f.direction, f.group), []).append(f)

    for (direction, group), group_frames in by_group_dir.items():
        if group == "standing":
            assert len(group_frames) == 1
            references[(direction, group)] = group_frames[0].measure["feet_row"]
        else:
            feet_rows = [gf.measure["feet_row"] for gf in group_frames]
            references[(direction, group)] = lower_median(feet_rows)

    for f in frames:
        f.reference_row = references[(f.direction, f.group)]

    return references


def compute_bounds(frames: list, canvas: int, top_margin: int, bottom_margin: int):
    """Returns (g_max, g_min, low_binding_ids, high_binding_ids, max_low, max_high).

    g_max keeps every frame's feet at least `bottom_margin` px above the
    bottom edge of the canvas (row h-1); g_min keeps every frame's head at
    least `top_margin` px below the top edge.
    """
    h = canvas
    deltas_low = [(f.measure["feet_row"] - f.reference_row, f) for f in frames]
    deltas_high = [(f.reference_row - f.measure["head_row"], f) for f in frames]

    max_low = max(d for d, _ in deltas_low)
    low_binding = [f.frame_id for d, f in deltas_low if d == max_low]

    max_high = max(d for d, _ in deltas_high)
    high_binding = [f.frame_id for d, f in deltas_high if d == max_high]

    g_max = (h - 1 - bottom_margin) - max_low
    g_min = top_margin + max_high

    return g_max, g_min, low_binding, high_binding, max_low, max_high


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------

def run_plan(key, stills_dir, walk_specs, out_dir, canvas=128, top_margin=0,
             bottom_margin=2, max_dip=6, no_max_dip=False):
    """Runs the full plan pipeline. Writes files only if everything validates.
    Returns the result dict that is also written to ground_line.json.
    Raises a GroundLineError subclass on any failure, with nothing written.

    `bottom_margin` keeps the chosen ground line off the bottom canvas edge
    (default 2). `max_dip` caps how far any direction+group's deepest frame
    may sit below the shared ground line (default 6); pass `no_max_dip=True`
    to disable that cap entirely (an explicit `max_dip=0` is instead a real
    cap of zero — no group may dip at all).
    """
    stills_frames = collect_stills(stills_dir) if stills_dir else []
    walk_frames = collect_walk(walk_specs) if walk_specs else []
    all_frames = stills_frames + walk_frames

    if not all_frames:
        raise GroundLineError("no input frames given (need --stills and/or --walk)")

    measure_all(all_frames, canvas)
    compute_references(all_frames)

    g_max, g_min, low_binding, high_binding, max_low, max_high = compute_bounds(
        all_frames, canvas, top_margin, bottom_margin
    )

    if g_max < g_min:
        raise BoundsError(
            f"no valid ground line: g_max={g_max} < g_min={g_min}. "
            f"g_max bound by {low_binding} (feet_row - reference = {max_low}, "
            f"bottom_margin={bottom_margin}); "
            f"g_min bound by {high_binding} (reference - head_row = {max_high}, "
            f"top_margin={top_margin})"
        )

    g = g_max

    # Shift every frame in memory first. Nothing is written to disk until
    # every check below — including the max-dip cap — has passed.
    for f in all_frames:
        dy = g - f.reference_row
        f.dy = dy
        f.new_img = shift_image(f._img, dy, label=str(f.path))
        f.feet_after = f.measure["feet_row"] + dy
        f.head_after = f.measure["head_row"] + dy

    groups = {}
    for f in all_frames:
        groups.setdefault((f.direction, f.group), []).append(f)

    # Per-group dip below the shared ground line. A walk frame's forward foot
    # is drawn lower on screen by design (a step toward the camera); this
    # measures that dip per direction+group rather than ignoring it. For a
    # "standing" group (one frame, reference_row == that frame's own
    # feet_row) the dip is always exactly 0.
    group_dip = {}
    for (direction, group), group_frames in groups.items():
        deepest_before = max(gf.measure["feet_row"] for gf in group_frames)
        deepest_after = max(gf.feet_after for gf in group_frames)
        deepest_frames = sorted(
            gf.name for gf in group_frames if gf.measure["feet_row"] == deepest_before
        )
        group_dip[(direction, group)] = {
            "deepest_row_before": deepest_before,
            "deepest_row_after": deepest_after,
            "dip_below_ground_line": deepest_after - g,
            "deepest_frames": deepest_frames,
        }

    max_dip_observed = max(v["dip_below_ground_line"] for v in group_dip.values())
    max_dip_binding = sorted(
        _group_label(direction, group)
        for (direction, group), v in group_dip.items()
        if v["dip_below_ground_line"] == max_dip_observed
    )

    if not no_max_dip and max_dip_observed > max_dip:
        offenders = [
            f"{_group_label(direction, group)} (dip={v['dip_below_ground_line']}, "
            f"frames={v['deepest_frames']})"
            for (direction, group), v in sorted(group_dip.items())
            if v["dip_below_ground_line"] > max_dip
        ]
        raise MaxDipExceededError(
            f"max-dip exceeded: cap={max_dip}, offending group(s): " + "; ".join(offenders)
        )

    # Everything validated — now write output.
    out_dir = Path(out_dir)
    standing_dir = out_dir / "standing"
    walk_dir_root = out_dir / "walk"

    have_standing = any(f.group == "standing" for f in all_frames)
    have_walk = any(f.group == "walk" for f in all_frames)
    if have_standing:
        standing_dir.mkdir(parents=True, exist_ok=True)
    if have_walk:
        walk_dir_root.mkdir(parents=True, exist_ok=True)

    frame_records = []
    directions_out = {}
    walk_frame_counts = {}

    for f in all_frames:
        if f.group == "standing":
            dst_path = standing_dir / f"{f.direction}.png"
        else:
            dst_dir = walk_dir_root / f.direction
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst_path = dst_dir / f.name

        f.new_img.save(dst_path)

        frame_records.append({
            "group": f.group,
            "direction": f.direction,
            "name": f.name,
            "src": str(Path(f.path).resolve()),
            "src_sha256": sha256_of_file(f.path),
            "dst": str(dst_path.resolve()),
            "dst_sha256": sha256_of_file(dst_path),
            "feet_row_before": f.measure["feet_row"],
            "feet_row_after": f.feet_after,
            "alpha_bottom_y_from_top_after": f.feet_after + 1,
            "head_row_before": f.measure["head_row"],
            "head_row_after": f.head_after,
            "dy": f.dy,
            "opaque_pixels": f.measure["opaque_pixels"],
        })

        if f.group == "walk":
            walk_frame_counts[f.direction] = walk_frame_counts.get(f.direction, 0) + 1

    # directions summary
    ref_by_group_dir = {}
    dy_by_group_dir = {}
    for f in all_frames:
        ref_by_group_dir[(f.direction, f.group)] = f.reference_row
        dy_by_group_dir[(f.direction, f.group)] = f.dy

    present_directions = sorted({f.direction for f in all_frames}, key=DIRECTIONS.index)
    for direction in present_directions:
        entry = {}
        if (direction, "standing") in ref_by_group_dir:
            dip = group_dip[(direction, "standing")]
            entry["still"] = {
                "reference_row": ref_by_group_dir[(direction, "standing")],
                "dy": dy_by_group_dir[(direction, "standing")],
                "deepest_row_before": dip["deepest_row_before"],
                "deepest_row_after": dip["deepest_row_after"],
                "dip_below_ground_line": dip["dip_below_ground_line"],
                "deepest_frames": dip["deepest_frames"],
            }
        if (direction, "walk") in ref_by_group_dir:
            dip = group_dip[(direction, "walk")]
            entry["walk"] = {
                "reference_row": ref_by_group_dir[(direction, "walk")],
                "dy": dy_by_group_dir[(direction, "walk")],
                "frames": walk_frame_counts[direction],
                "deepest_row_before": dip["deepest_row_before"],
                "deepest_row_after": dip["deepest_row_after"],
                "dip_below_ground_line": dip["dip_below_ground_line"],
                "deepest_frames": dip["deepest_frames"],
            }
        directions_out[direction] = entry

    standing_present = {f.direction for f in all_frames if f.group == "standing"}
    walk_present = {f.direction for f in all_frames if f.group == "walk"}
    missing_directions = {
        "standing": [d for d in DIRECTIONS if d not in standing_present],
        "walk": [d for d in DIRECTIONS if d not in walk_present],
    }

    pivot = compute_pivot(canvas, g)

    result = {
        "key": key,
        "canvas": [canvas, canvas],
        "ground_line_row_inclusive": g,
        "ground_line_y_from_top": g + 1,
        "pivot": pivot,
        "top_margin": top_margin,
        "bottom_margin": bottom_margin,
        "max_dip": None if no_max_dip else max_dip,
        "max_dip_observed": max_dip_observed,
        "max_dip_binding": max_dip_binding,
        "bounds": {
            "g_min": g_min,
            "g_max": g_max,
            "g_min_binding": high_binding,
            "g_max_binding": low_binding,
        },
        "directions": directions_out,
        "missing_directions": missing_directions,
        "frames": frame_records,
    }

    json_path = out_dir / "ground_line.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    return result


def print_plan_summary(result: dict, out=sys.stdout) -> None:
    g = result["ground_line_row_inclusive"]
    g_excl = result["ground_line_y_from_top"]
    pivot_y = result["pivot"]["y"]
    print(f"key: {result['key']}", file=out)
    print(f"canvas: {result['canvas'][0]}x{result['canvas'][1]}", file=out)
    print(f"chosen ground line G (inclusive row): {g}", file=out)
    print(f"G_excl (alpha_bottom_y_from_top convention): {g_excl}", file=out)
    print(f"pivot: (0.5, {pivot_y})", file=out)
    print(
        f"max_dip_observed: {result['max_dip_observed']} "
        f"(cap={result['max_dip']}, set by: {result['max_dip_binding']})",
        file=out,
    )
    print(
        f"bounds: g_min={result['bounds']['g_min']} "
        f"(binding: {result['bounds']['g_min_binding']}), "
        f"g_max={result['bounds']['g_max']} "
        f"(binding: {result['bounds']['g_max_binding']})",
        file=out,
    )
    for direction in DIRECTIONS:
        entry = result["directions"].get(direction)
        if not entry:
            continue
        parts = []
        if "still" in entry:
            parts.append(f"still dy={entry['still']['dy']}")
        if "walk" in entry:
            parts.append(f"walk dy={entry['walk']['dy']} ({entry['walk']['frames']} frames)")
        print(f"  {direction}: {', '.join(parts)}", file=out)
    if result["missing_directions"]["standing"] or result["missing_directions"]["walk"]:
        print(f"missing standing: {result['missing_directions']['standing']}", file=out)
        print(f"missing walk: {result['missing_directions']['walk']}", file=out)


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------

def run_check(json_path) -> tuple:
    """Re-measures the files named in an existing ground_line.json.
    Returns (ok: bool, problems: list[str]).

    Besides the per-frame checks (round 1), this re-derives each direction+
    group's `deepest_row_after` / `dip_below_ground_line` from the re-measured
    dst frames and the recorded `ground_line_row_inclusive`, and the top-level
    `max_dip_observed`, failing (naming the group) on any mismatch against
    what is recorded in the JSON.
    """
    json_path = Path(json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    problems = []

    # (direction, group) -> list of (frame name, re-measured feet_row_after)
    measured_feet_after = {}

    for rec in data.get("frames", []):
        frame_label = f"{rec['group']}:{rec['direction']}:{rec['name']}"

        dst = Path(rec["dst"])
        if not dst.exists():
            problems.append(f"{frame_label}: dst file missing: {dst}")
            continue
        dst_bytes = dst.read_bytes()
        dst_hash = sha256_of_bytes(dst_bytes)
        if dst_hash != rec["dst_sha256"]:
            problems.append(
                f"{frame_label}: dst sha256 mismatch (recorded {rec['dst_sha256']}, now {dst_hash})"
            )
        try:
            img = load_rgba(dst)
            m = measure(img, label=str(dst))
        except EmptyFrameError as e:
            problems.append(f"{frame_label}: {e}")
            continue
        if m["feet_row"] != rec["feet_row_after"]:
            problems.append(
                f"{frame_label}: feet_row_after mismatch (recorded {rec['feet_row_after']}, now {m['feet_row']})"
            )
        if m["head_row"] != rec["head_row_after"]:
            problems.append(
                f"{frame_label}: head_row_after mismatch (recorded {rec['head_row_after']}, now {m['head_row']})"
            )
        if m["opaque_pixels"] != rec["opaque_pixels"]:
            problems.append(
                f"{frame_label}: opaque_pixels mismatch (recorded {rec['opaque_pixels']}, now {m['opaque_pixels']})"
            )
        if m["feet_row"] + 1 != rec["alpha_bottom_y_from_top_after"]:
            problems.append(
                f"{frame_label}: alpha_bottom_y_from_top_after mismatch "
                f"(recorded {rec['alpha_bottom_y_from_top_after']}, now {m['feet_row'] + 1})"
            )

        src = Path(rec["src"])
        if src.exists():
            src_hash = sha256_of_file(src)
            if src_hash != rec["src_sha256"]:
                problems.append(
                    f"{frame_label}: src sha256 mismatch (recorded {rec['src_sha256']}, now {src_hash}) "
                    f"— the original input frame changed"
                )

        measured_feet_after.setdefault((rec["direction"], rec["group"]), []).append(
            (rec["name"], m["feet_row"])
        )

    # Per-group dip re-check. Only run for a group whose frames all re-measured
    # cleanly above (a missing/unreadable frame was already reported per-frame).
    g = data.get("ground_line_row_inclusive")
    all_dips_now = []
    if g is not None:
        for direction, entry in data.get("directions", {}).items():
            for json_key, group_name in (("still", "standing"), ("walk", "walk")):
                group_entry = entry.get(json_key)
                if not group_entry:
                    continue
                frames_now = measured_feet_after.get((direction, group_name))
                if not frames_now:
                    continue
                label = _group_label(direction, group_name)
                deepest_after_now = max(v for _, v in frames_now)
                dip_now = deepest_after_now - g
                deepest_frames_now = sorted(n for n, v in frames_now if v == deepest_after_now)
                all_dips_now.append(dip_now)

                if "deepest_row_after" in group_entry and group_entry["deepest_row_after"] != deepest_after_now:
                    problems.append(
                        f"{label}: deepest_row_after mismatch "
                        f"(recorded {group_entry['deepest_row_after']}, now {deepest_after_now})"
                    )
                if "dip_below_ground_line" in group_entry and group_entry["dip_below_ground_line"] != dip_now:
                    problems.append(
                        f"{label}: dip_below_ground_line mismatch "
                        f"(recorded {group_entry['dip_below_ground_line']}, now {dip_now})"
                    )
                if "deepest_frames" in group_entry and sorted(group_entry["deepest_frames"]) != deepest_frames_now:
                    problems.append(
                        f"{label}: deepest_frames mismatch "
                        f"(recorded {sorted(group_entry['deepest_frames'])}, now {deepest_frames_now})"
                    )

    if "max_dip_observed" in data and all_dips_now:
        max_dip_observed_now = max(all_dips_now)
        if data["max_dip_observed"] != max_dip_observed_now:
            problems.append(
                f"max_dip_observed mismatch (recorded {data['max_dip_observed']}, now {max_dip_observed_now})"
            )

    return (len(problems) == 0, problems)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _parse_walk_arg(value: str) -> tuple:
    if "=" not in value:
        raise argparse.ArgumentTypeError(f"--walk must be DIRECTION=DIR, got '{value}'")
    direction, _, folder = value.partition("=")
    return direction, folder


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ground_line.py")
    sub = parser.add_subparsers(dest="command", required=True)

    plan_p = sub.add_parser("plan")
    plan_p.add_argument("--key", required=True)
    plan_p.add_argument("--stills", required=False, default=None)
    plan_p.add_argument("--walk", action="append", default=[], metavar="DIRECTION=DIR")
    plan_p.add_argument("--out", required=True)
    plan_p.add_argument("--canvas", type=int, default=128)
    plan_p.add_argument("--top-margin", type=int, default=0, dest="top_margin")
    plan_p.add_argument("--bottom-margin", type=int, default=2, dest="bottom_margin")
    plan_p.add_argument("--max-dip", type=int, default=6, dest="max_dip")
    plan_p.add_argument("--no-max-dip", action="store_true", dest="no_max_dip")

    check_p = sub.add_parser("check")
    check_p.add_argument("--json", required=True)

    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "plan":
        walk_specs = {}
        for raw in args.walk:
            direction, folder = _parse_walk_arg(raw)
            walk_specs[direction] = folder
        try:
            result = run_plan(
                key=args.key,
                stills_dir=args.stills,
                walk_specs=walk_specs,
                out_dir=args.out,
                canvas=args.canvas,
                top_margin=args.top_margin,
                bottom_margin=args.bottom_margin,
                max_dip=args.max_dip,
                no_max_dip=args.no_max_dip,
            )
        except GroundLineError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print_plan_summary(result)
        return 0

    if args.command == "check":
        ok, problems = run_check(args.json)
        if ok:
            print(f"OK: all frames in {args.json} match their recorded measurements")
            return 0
        print(f"FAILED: {len(problems)} problem(s) found in {args.json}", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
