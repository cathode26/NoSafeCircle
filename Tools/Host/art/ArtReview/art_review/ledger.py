"""Append-only JSON Lines ledger for manually reported PixelLab spend."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_REPORTED_COST = 1_000_000
MAX_COUNTER = 1_000_000_000_000


def _append(path: Path, event: dict[str, Any]) -> None:
    event = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), **event}
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")


def _is_nonnegative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_counter(value: object, name: str) -> None:
    if not _is_nonnegative_integer(value) or value > MAX_COUNTER:
        raise ValueError(f"{name} must be an integer from 0 through {MAX_COUNTER}")


def _validate_cost(value: object) -> None:
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(value) or value < 0 or value > MAX_REPORTED_COST):
        raise ValueError(f"reported cost must be a finite number from 0 through {MAX_REPORTED_COST}")


def _validate_finite_aggregate(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} is not finite")


def _require_fields(event: dict[str, Any], fields: tuple[str, ...], line_number: int) -> None:
    missing = [field for field in fields if field not in event]
    if missing:
        raise ValueError(f"ledger line {line_number}: missing required field {missing[0]!r}")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard numeric constant {value}")


def _validate_event(event: object, line_number: int) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError(f"ledger line {line_number}: event must be a JSON object")
    event_type = event.get("type")
    if event_type not in ("init", "entry", "balance"):
        raise ValueError(f"ledger line {line_number}: unknown event type {event_type!r}")
    required = {
        "init": ("type", "timestamp_utc", "job", "cap", "remaining", "used"),
        "entry": ("type", "timestamp_utc", "tool", "pixellab_id", "reported_cost", "provisional", "note"),
        "balance": ("type", "timestamp_utc", "remaining", "used", "label"),
    }[event_type]
    _require_fields(event, required, line_number)
    if not isinstance(event["timestamp_utc"], str):
        raise ValueError(f"ledger line {line_number}: timestamp_utc must be a string")
    if event_type == "init":
        if not isinstance(event["job"], str):
            raise ValueError(f"ledger line {line_number}: job must be a string")
        if event["cap"] is not None:
            try:
                _validate_counter(event["cap"], "cap")
            except ValueError as exc:
                raise ValueError(f"ledger line {line_number}: {exc}") from exc
    elif event_type == "entry":
        if not isinstance(event["tool"], str) or not isinstance(event["pixellab_id"], str):
            raise ValueError(f"ledger line {line_number}: tool and pixellab_id must be strings")
        try:
            _validate_cost(event["reported_cost"])
        except ValueError as exc:
            raise ValueError(f"ledger line {line_number}: {exc}") from exc
        if not isinstance(event["provisional"], bool):
            raise ValueError(f"ledger line {line_number}: provisional must be a boolean")
        if event["note"] is not None and not isinstance(event["note"], str):
            raise ValueError(f"ledger line {line_number}: note must be null or a string")
    else:
        if event["label"] is not None and not isinstance(event["label"], str):
            raise ValueError(f"ledger line {line_number}: label must be null or a string")
    if event_type in ("init", "balance"):
        for field in ("remaining", "used"):
            try:
                _validate_counter(event[field], field)
            except ValueError as exc:
                raise ValueError(f"ledger line {line_number}: {exc}") from exc
    return event


def initialize(path: str | Path, job: str, remaining: int, used: int, cap: int | None = None) -> None:
    if not isinstance(job, str):
        raise ValueError("job must be a string")
    _validate_counter(remaining, "remaining")
    _validate_counter(used, "used")
    if cap is not None:
        _validate_counter(cap, "cap")
    ledger_path = Path(path)
    if ledger_path.exists():
        raise FileExistsError(f"ledger already exists: {ledger_path}")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    _append(ledger_path, {"type": "init", "job": job, "cap": cap, "remaining": remaining, "used": used})


def add(path: str | Path, tool: str, pixellab_id: str, reported_cost: float, provisional: bool = False,
        note: str | None = None) -> None:
    if not isinstance(tool, str) or not isinstance(pixellab_id, str):
        raise ValueError("tool and PixelLab id must be strings")
    _validate_cost(reported_cost)
    if not isinstance(provisional, bool):
        raise ValueError("provisional must be a boolean")
    if note is not None and not isinstance(note, str):
        raise ValueError("note must be null or a string")
    ledger_path = Path(path)
    if not ledger_path.is_file():
        raise FileNotFoundError(f"ledger does not exist: {ledger_path}")
    read_events(ledger_path)
    _append(ledger_path, {"type": "entry", "tool": tool, "pixellab_id": pixellab_id,
                          "reported_cost": reported_cost, "provisional": provisional, "note": note})


def balance(path: str | Path, remaining: int, used: int, label: str | None = None) -> None:
    _validate_counter(remaining, "remaining")
    _validate_counter(used, "used")
    if label is not None and not isinstance(label, str):
        raise ValueError("label must be null or a string")
    ledger_path = Path(path)
    if not ledger_path.is_file():
        raise FileNotFoundError(f"ledger does not exist: {ledger_path}")
    read_events(ledger_path)
    _append(ledger_path, {"type": "balance", "remaining": remaining, "used": used, "label": label})


def read_events(path: str | Path) -> list[dict[str, Any]]:
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read ledger: {exc}") from exc
    hashlib.sha256(data).digest()
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        line_number = data[:exc.start].count(b"\n") + 1
        raise ValueError(f"ledger line {line_number}: invalid UTF-8") from exc
    events = []
    for line_number, line in enumerate(lines, 1):
        try:
            raw_event = json.loads(line, parse_constant=_reject_json_constant)
        except json.JSONDecodeError as exc:
            raise ValueError(f"ledger line {line_number}: invalid JSON: {exc.msg}") from exc
        except ValueError as exc:
            raise ValueError(f"ledger line {line_number}: invalid JSON: {exc}") from exc
        events.append(_validate_event(raw_event, line_number))
    if not events:
        raise ValueError("ledger line 1: ledger must begin with exactly one init event")
    init_lines = [index for index, event in enumerate(events, 1) if event["type"] == "init"]
    if init_lines != [1]:
        bad_line = init_lines[0] if init_lines and init_lines[0] != 1 else (init_lines[1] if len(init_lines) > 1 else 1)
        raise ValueError(f"ledger line {bad_line}: init must appear exactly once as the first event")
    return events


def summarize(path: str | Path) -> dict[str, Any]:
    events = read_events(path)
    first = events[0]
    snapshots = [event for event in events if event.get("type") in ("init", "balance")]
    last = snapshots[-1]
    per_tool: dict[str, float] = defaultdict(float)
    provisional = 0.0
    for event in events:
        if event.get("type") == "entry":
            cost = float(event["reported_cost"])
            per_tool[event["tool"]] += cost
            _validate_finite_aggregate(per_tool[event["tool"]], f"per-tool total for {event['tool']!r}")
            if event.get("provisional"):
                provisional += cost
                _validate_finite_aggregate(provisional, "provisional total")
    reported = sum(per_tool.values())
    _validate_finite_aggregate(reported, "reported total")
    used_change = int(last["used"]) - int(first["used"])
    remaining_change = int(first["remaining"]) - int(last["remaining"])
    unattributed = used_change - reported
    _validate_finite_aggregate(unattributed, "unattributed difference")
    spend = reported + max(0.0, unattributed)
    _validate_finite_aggregate(spend, "spend")
    cap = first.get("cap")
    if cap is None:
        status = "no_cap"
    elif spend > cap:
        status = "over_cap"
    elif spend >= cap - 2:
        status = "near_cap"
    else:
        status = "ok"
    return {"job": first["job"], "cap": cap, "per_tool": dict(sorted(per_tool.items())),
            "tool_reported_total": reported, "provisional_total": provisional,
            "balance_change": {"by_generations_used": used_change, "by_remaining": remaining_change},
            "unattributed_difference": unattributed, "spend": spend, "cap_status": status,
            "warning": "PixelLab account balances are shared; balance changes can include other sessions."}


def markdown(summary: dict[str, Any]) -> str:
    rows = ["| Tool | Reported cost |", "| --- | ---: |"]
    rows.extend(f"| {tool} | {cost:g} |" for tool, cost in summary["per_tool"].items())
    rows.extend(["", f"Reported total: {summary['tool_reported_total']:g}",
                 f"Balance change (used / remaining): {summary['balance_change']['by_generations_used']} / {summary['balance_change']['by_remaining']}",
                 f"Unattributed: {summary['unattributed_difference']:g}", f"Spend: {summary['spend']:g}",
                 f"Cap status: {summary['cap_status']}", "", f"Warning: {summary['warning']}"])
    return "\n".join(rows) + "\n"
