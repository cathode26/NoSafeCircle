"""Command-line interface for the art review toolkit."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from .camera import camera_facing_affine, camera_facing_scale, down_right_direction, motion_step, parse_pivot, render, world_plane_affine
from .gifio import write_gif
from .ledger import add as ledger_add
from .ledger import balance as ledger_balance
from .ledger import initialize as ledger_initialize
from .ledger import markdown as ledger_markdown
from .ledger import summarize as ledger_summarize
from .maskdiff import compare
from .metrics import frame_metrics, hue_scan
from .normalize import normalize_frame
from .pngio import read_png, write_png
from .raster import RGBAImage, blit, nearest_zoom, parse_color
from .sheets import contact_sheet, game_scale_sheet


def _json_read(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _json_write(value: Any, path: str | Path | None) -> None:
    if path is not None:
        Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _same_path(left: str | Path, right: str | Path) -> bool:
    left_path, right_path = Path(left), Path(right)
    left_name = os.path.normcase(os.path.realpath(left_path))
    right_name = os.path.normcase(os.path.realpath(right_path))
    if left_name == right_name:
        return True
    if left_path.exists() and right_path.exists():
        try:
            return os.path.samefile(left_path, right_path)
        except OSError:
            pass
    return False


def _validate_io_paths(inputs: Sequence[str | Path], outputs: Sequence[str | Path | None]) -> None:
    """Reject aliases, then read and hash every input before any output is written."""
    input_paths = [Path(path) for path in inputs]
    output_paths = [Path(path) for path in outputs if path is not None]
    for index, output in enumerate(output_paths):
        for other in output_paths[index + 1:]:
            if _same_path(output, other):
                raise ValueError(f"output path {output} resolves to another output path {other}")
        for input_path in input_paths:
            if _same_path(output, input_path):
                raise ValueError(f"output path {output} resolves to input path {input_path}")
    for input_path in input_paths:
        hashlib.sha256(input_path.read_bytes()).digest()


def _paths(positional: list[str], pattern: str | None) -> list[str]:
    result = list(positional)
    if pattern:
        result.extend(sorted(glob.glob(pattern)))
    if not result:
        raise ValueError("provide frame paths or --glob")
    return result


def _opaque_background(image: RGBAImage, color_text: str) -> RGBAImage:
    result = RGBAImage.new(image.width, image.height, parse_color(color_text))
    blit(result, image, 0, 0)
    return result


def _motion_scene(sprite_paths: list[str], scene: dict[str, Any]) -> tuple[list[RGBAImage], list[int]]:
    sprites = [read_png(path) for path in sprite_paths]
    if "background" in scene:
        background = read_png(scene["background"])
    else:
        width, height = scene.get("size", [640, 360])
        background = RGBAImage.new(int(width), int(height), parse_color(scene.get("background_color", "#1d1631")))
    start = tuple(float(value) for value in scene.get("start", [0, 0]))
    end = tuple(float(value) for value in scene["end"])
    fps = float(scene.get("fps", 60))
    delta_x, delta_y = end[0] - start[0], end[1] - start[1]
    distance = math.hypot(delta_x, delta_y)
    if "world_speed" in scene:
        direction_value = scene.get("direction", "down-right")
        direction = down_right_direction() if direction_value == "down-right" else tuple(direction_value)
        movement = motion_step(float(scene["world_speed"]), direction, fps, scene.get("resolution", "1080p"))
        speed = math.hypot(movement["pixels_per_second_x"], movement["pixels_per_second_y"])
    else:
        speed = float(scene["screen_speed"])
    frame_count = max(1, math.ceil(distance / speed * fps) + 1) if distance else 1
    duration = round(1000 / fps)
    output = []
    for index in range(frame_count):
        progress = min(1.0, index / max(1, frame_count - 1))
        position = (start[0] + delta_x * progress, start[1] + delta_y * progress)
        sprite = sprites[index % len(sprites)]
        pivot = parse_pivot(scene.get("pivot", "bottom-center"), sprite.width, sprite.height)
        if scene.get("mode", "camera-facing") == "world-plane":
            transform = world_plane_affine(float(scene["ppu"]), tuple(scene.get("local_scale", [1, 1])),
                                           scene.get("resolution", "1080p"), pivot, position)
        else:
            scale_options = {name: scene[name] for name in ("box_units", "scale", "ppu") if name in scene}
            if not scale_options:
                scale_options["scale"] = 1.0
            scale = camera_facing_scale(sprite.height, scene.get("resolution", "1080p"), **scale_options)
            transform = camera_facing_affine(scale, pivot, position)
        layer = render(sprite, background.width, background.height, transform, scene.get("sampling", "point"))
        frame = background.copy()
        blit(frame, layer, 0, 0)
        output.append(frame)
    return output, [duration] * frame_count


def command_gamescale(arguments: argparse.Namespace) -> int:
    manifest = _json_read(arguments.manifest)
    if arguments.resolution is not None:
        manifest["resolution"] = arguments.resolution
    _validate_io_paths([arguments.manifest, *(sprite["path"] for sprite in manifest["sprites"])],
                       [arguments.output, arguments.json])
    sheet, sprites = game_scale_sheet(manifest)
    write_png(sheet, arguments.output)
    _json_write({"output": arguments.output, "size": [sheet.width, sheet.height], "sprites": sprites}, arguments.json)
    return 0


def command_contact_sheet(arguments: argparse.Namespace) -> int:
    inputs: list[str | Path] = []
    if arguments.manifest:
        value = _json_read(arguments.manifest)
        rows = value["rows"] if isinstance(value, dict) else value
        inputs.append(arguments.manifest)
    else:
        paths = sorted(glob.glob(arguments.glob))
        if not paths:
            raise ValueError("glob matched no images")
        columns = max(1, arguments.columns)
        cells = [{"path": path, "caption": Path(path).stem} for path in paths]
        rows = [cells[index:index + columns] for index in range(0, len(cells), columns)]
    inputs.extend(cell["path"] for row in rows for cell in row)
    _validate_io_paths(inputs, [arguments.output, arguments.json])
    sheet = contact_sheet(rows, arguments.zoom, arguments.gap, arguments.background, arguments.cell_background, arguments.header)
    write_png(sheet, arguments.output)
    _json_write({"output": arguments.output, "size": [sheet.width, sheet.height]}, arguments.json)
    return 0


def command_gif(arguments: argparse.Namespace) -> int:
    inputs: list[str | Path] = []
    if arguments.manifest:
        manifest = _json_read(arguments.manifest)
        inputs.append(arguments.manifest)
        entries = manifest["frames"] if isinstance(manifest, dict) else manifest
        paths = [entry["path"] for entry in entries]
        durations = [int(entry.get("duration_ms", arguments.duration)) for entry in entries]
    else:
        paths = _paths(arguments.frames, arguments.glob)
        durations = [arguments.duration] * len(paths)
    inputs.extend(paths)
    if arguments.motion_scene:
        scene = _json_read(arguments.motion_scene)
        inputs.append(arguments.motion_scene)
        if "background" in scene:
            inputs.append(scene["background"])
        _validate_io_paths(inputs, [arguments.output, arguments.json])
        frames, durations = _motion_scene(paths, scene)
    else:
        _validate_io_paths(inputs, [arguments.output, arguments.json])
        frames = [read_png(path) for path in paths]
        if arguments.zoom != 1:
            frames = [nearest_zoom(frame, arguments.zoom) for frame in frames]
        if arguments.background:
            frames = [_opaque_background(frame, arguments.background) for frame in frames]
    report = write_gif(frames, durations, arguments.output, not arguments.no_loop)
    _json_write(report, arguments.json)
    return 0


def command_mask_diff(arguments: argparse.Namespace) -> int:
    _validate_io_paths([arguments.source, arguments.result, arguments.mask], [arguments.output, arguments.json])
    report = compare(arguments.source, arguments.result, arguments.mask, arguments.output, arguments.zoom)
    _json_write(report, arguments.json)
    return 1 if report["changed_outside"] else 0


def _metrics_markdown(report: dict[str, Any]) -> str:
    lines = ["| # | File | Size | Alpha bbox | Opaque | Colors |", "| ---: | --- | --- | --- | ---: | ---: |"]
    for index, frame in enumerate(report["frames"]):
        lines.append(f"| {index} | {frame['path']} | {frame['size'][0]}x{frame['size'][1]} | {frame['alpha_bbox']} | {frame['opaque_pixel_count']} | {frame['distinct_color_count']} |")
    lines.extend(["", "| From→to | Opaque % | Width Δ | Baseline Δ | Flags |", "| --- | ---: | ---: | ---: | --- |"])
    for delta in report["deltas"]:
        label = f"{delta['from']}→{delta['to']}" + (" (loop)" if delta["loop_seam"] else "")
        lines.append(f"| {label} | {delta['opaque_change_percent']:.2f} | {delta['bbox_width_change']} | {delta['bbox_bottom_change']} | {', '.join(delta['flags'])} |")
    return "\n".join(lines) + "\n"


def command_frame_metrics(arguments: argparse.Namespace) -> int:
    paths = _paths(arguments.frames, arguments.glob)
    _validate_io_paths(paths, [arguments.json, arguments.markdown])
    report = frame_metrics(paths, loop=arguments.loop,
                           opaque_threshold=arguments.opaque_threshold, width_threshold=arguments.width_threshold,
                           baseline_threshold=arguments.baseline_threshold)
    _json_write(report, arguments.json)
    if arguments.markdown:
        Path(arguments.markdown).write_text(_metrics_markdown(report), encoding="utf-8")
    return 0


def command_hue_scan(arguments: argparse.Namespace) -> int:
    ranges = None
    if arguments.ranges:
        ranges = []
        for value in arguments.ranges:
            low, high = value.split(":", 1)
            ranges.append((float(low), float(high)))
    paths = _paths(arguments.files, arguments.glob)
    _validate_io_paths(paths, [arguments.json])
    report = hue_scan(paths, ranges, arguments.minimum_saturation, arguments.minimum_value)
    _json_write(report, arguments.json)
    return 1 if arguments.fail_on_match and report["matching_pixel_count"] else 0


def command_normalize(arguments: argparse.Namespace) -> int:
    paths = _paths(arguments.frames, arguments.glob)
    width = height = arguments.size if arguments.size else None
    if arguments.canvas:
        width, height = arguments.canvas
    if width is None or height is None:
        raise ValueError("provide --size or --canvas WIDTH HEIGHT")
    output_directory = Path(arguments.output_dir)
    outputs = [output_directory / Path(value).name for value in paths]
    _validate_io_paths(paths, [*outputs, arguments.json])
    output_directory.mkdir(parents=True, exist_ok=True)
    reports, errors = [], []
    for value in paths:
        source = Path(value)
        output = output_directory / source.name
        if output.resolve() == source.resolve():
            errors.append({"path": str(source), "error": "output would overwrite source"})
            continue
        try:
            reports.append(normalize_frame(source, output, width, height))
        except ValueError as exc:
            errors.append({"path": str(source), "error": str(exc)})
    _json_write({"frames": reports, "errors": errors}, arguments.json)
    return 1 if errors else 0


def command_ledger(arguments: argparse.Namespace) -> int:
    if arguments.action == "init":
        ledger_initialize(arguments.ledger, arguments.job, arguments.remaining, arguments.used, arguments.cap)
    elif arguments.action == "add":
        ledger_add(arguments.ledger, arguments.tool, arguments.id, arguments.reported_cost, arguments.provisional, arguments.note)
    elif arguments.action == "balance":
        ledger_balance(arguments.ledger, arguments.remaining, arguments.used, arguments.label)
    else:
        _validate_io_paths([arguments.ledger], [arguments.json, arguments.markdown])
        report = ledger_summarize(arguments.ledger)
        _json_write(report, arguments.json)
        if arguments.markdown:
            Path(arguments.markdown).write_text(ledger_markdown(report), encoding="utf-8")
        if not arguments.json and not arguments.markdown:
            print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m art_review", description="No Safe Circle pixel-art review tools")
    commands = parser.add_subparsers(dest="command", required=True)
    gamescale = commands.add_parser("gamescale", help="render a true-screen-scale comparison sheet")
    gamescale.add_argument("--manifest", required=True); gamescale.add_argument("--output", required=True)
    gamescale.add_argument("--resolution"); gamescale.add_argument("--json"); gamescale.set_defaults(function=command_gamescale)
    contact = commands.add_parser("contact-sheet", help="build a labeled image grid")
    contact_source = contact.add_mutually_exclusive_group(required=True)
    contact_source.add_argument("--manifest"); contact_source.add_argument("--glob")
    contact.add_argument("--output", required=True); contact.add_argument("--columns", type=int, default=4)
    contact.add_argument("--zoom", type=int, default=1); contact.add_argument("--gap", type=int, default=8)
    contact.add_argument("--background", default="#1d1631"); contact.add_argument("--cell-background", default="#2a2342")
    contact.add_argument("--header", default=""); contact.add_argument("--json"); contact.set_defaults(function=command_contact_sheet)
    gif = commands.add_parser("gif", help="encode ordered PNG frames as GIF89a")
    gif.add_argument("frames", nargs="*"); gif.add_argument("--glob"); gif.add_argument("--manifest")
    gif.add_argument("--output", required=True); gif.add_argument("--duration", type=int, default=100)
    gif.add_argument("--zoom", type=int, default=1); gif.add_argument("--background"); gif.add_argument("--no-loop", action="store_true")
    gif.add_argument("--motion-scene"); gif.add_argument("--json"); gif.set_defaults(function=command_gif)
    mask = commands.add_parser("mask-diff", help="prove changes are confined to a binary mask")
    mask.add_argument("--source", required=True); mask.add_argument("--result", required=True); mask.add_argument("--mask", required=True)
    mask.add_argument("--output", required=True); mask.add_argument("--zoom", type=int, default=1); mask.add_argument("--json")
    mask.set_defaults(function=command_mask_diff)
    metrics = commands.add_parser("frame-metrics", help="measure frame continuity and outliers")
    metrics.add_argument("frames", nargs="*"); metrics.add_argument("--glob"); metrics.add_argument("--loop", action="store_true")
    metrics.add_argument("--opaque-threshold", type=float, default=15.0); metrics.add_argument("--width-threshold", type=int, default=8)
    metrics.add_argument("--baseline-threshold", type=int, default=3); metrics.add_argument("--json", required=True); metrics.add_argument("--markdown")
    metrics.set_defaults(function=command_frame_metrics)
    hue = commands.add_parser("hue-scan", help="count pixels in HSV hue ranges")
    hue.add_argument("files", nargs="*"); hue.add_argument("--glob"); hue.add_argument("--range", dest="ranges", action="append")
    hue.add_argument("--minimum-saturation", type=float, default=0.3); hue.add_argument("--minimum-value", type=float, default=0.3)
    hue.add_argument("--fail-on-match", action="store_true"); hue.add_argument("--json"); hue.set_defaults(function=command_hue_scan)
    normalize = commands.add_parser("normalize", help="losslessly center crop/pad frames")
    normalize.add_argument("frames", nargs="*"); normalize.add_argument("--glob"); normalize.add_argument("--output-dir", required=True)
    size = normalize.add_mutually_exclusive_group(required=True); size.add_argument("--size", type=int); size.add_argument("--canvas", type=int, nargs=2)
    normalize.add_argument("--json", required=True); normalize.set_defaults(function=command_normalize)
    ledger = commands.add_parser("ledger", help="record manually reported PixelLab spend")
    actions = ledger.add_subparsers(dest="action", required=True)
    init = actions.add_parser("init"); init.add_argument("--ledger", required=True); init.add_argument("--job", required=True)
    init.add_argument("--cap", type=int); init.add_argument("--remaining", type=int, required=True); init.add_argument("--used", type=int, required=True)
    add_command = actions.add_parser("add"); add_command.add_argument("--ledger", required=True); add_command.add_argument("--tool", required=True)
    add_command.add_argument("--id", required=True); add_command.add_argument("--reported-cost", type=float, required=True)
    add_command.add_argument("--provisional", action="store_true"); add_command.add_argument("--note")
    balance_command = actions.add_parser("balance"); balance_command.add_argument("--ledger", required=True)
    balance_command.add_argument("--remaining", type=int, required=True); balance_command.add_argument("--used", type=int, required=True)
    balance_command.add_argument("--label")
    summary = actions.add_parser("summary"); summary.add_argument("--ledger", required=True); summary.add_argument("--markdown"); summary.add_argument("--json")
    ledger.set_defaults(function=command_ledger)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        arguments = parser.parse_args(argv)
        return int(arguments.function(arguments))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
