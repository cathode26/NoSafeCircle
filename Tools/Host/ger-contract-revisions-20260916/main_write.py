"""Main-write protocol journal markers for the GER Agent (nsc-main-orchestrator-guide.md section 5).

start() refuses when another role has a MAIN-WRITE START without an END in the last 30 minutes, then appends
"MAIN-WRITE START <role> <operation> expected HEAD <sha>". end() appends "MAIN-WRITE END <role> new HEAD <sha>; <checks>".
Lines go under a "## <date> GER Agent" section, which is added when the journal's last section belongs to another role.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re

JOURNAL = pathlib.Path(r"C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md")
ROLE = "GER Agent"


def _append(line: str) -> None:
    text = JOURNAL.read_text(encoding="utf-8")
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    header = f"## {today} {ROLE}"
    headers = [h for h in text.splitlines() if h.startswith("## ")]
    prefix = "" if text.endswith("\n") else "\n"
    if not headers or headers[-1].strip() != header:
        prefix += f"\n{header}\n"
    with JOURNAL.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix + line + "\n")


def open_writes(minutes: int = 30) -> list[str]:
    """START lines from the last `minutes` without a later END from the same role."""
    now = dt.datetime.now(dt.timezone.utc)
    pending: dict[str, str] = {}
    for line in JOURNAL.read_text(encoding="utf-8").splitlines():
        start = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC MAIN-WRITE START ([A-Za-z ]+?(?:Agent|Steward|Orchestrator))", line)
        if start:
            pending[start.group(2).strip()] = start.group(1)
            continue
        end = re.search(r"MAIN-WRITE END ([A-Za-z ]+?(?:Agent|Steward|Orchestrator))", line)
        if end:
            pending.pop(end.group(1).strip(), None)
    recent = []
    for role, stamp in pending.items():
        when = dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
        if now - when <= dt.timedelta(minutes=minutes):
            recent.append(f"{role} since {stamp} UTC")
    return recent


def start(operation: str, expected_head: str) -> None:
    others = [item for item in open_writes() if not item.startswith(ROLE)]
    if others:
        raise SystemExit(f"another main write is open: {others}; wait or ask")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    _append(f"- {stamp} UTC MAIN-WRITE START {ROLE}: {operation}, expected HEAD {expected_head[:9]}")


def end(new_head: str, checks: str) -> None:
    _append(f"- MAIN-WRITE END {ROLE}: new HEAD {new_head[:9]}; {checks}")
