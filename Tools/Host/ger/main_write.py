"""Main-write protocol journal markers for GER contract commits (nsc-main-orchestrator-guide.md section 5).

start() refuses when another role has a MAIN-WRITE START without an END in the last 30 minutes, then appends
"MAIN-WRITE START <role> <operation> expected HEAD <sha>". end() appends "MAIN-WRITE END <role> new HEAD
<sha>; <checks>". Lines go under a "## <date> <role>" section, which is added when the journal's last
section belongs to another role.

**`role` is a REQUIRED argument, and that is the whole point.** It was a module
constant, `ROLE = "GER Agent"`, until 2026-09-22. Every START was therefore
written as GER whatever role was running, `start()` filtered the open writes with
`not item.startswith(ROLE)`, and so it discarded every one of them: `others` was
always empty and the refusal above was unreachable - it had never fired, for
anyone. `end()` popped by the same constant, so one role's END closed another's
START. Reported by the GER Agent (board H-20260920-10) with a reproduction
against a throwaway journal: role A opened, role B was NOT refused, B's single
END emptied the pending map while A never ended.

A caller that forgets the role is now refused rather than silently mislabelled.
Journal lines already stamped "GER Agent" on another role's behalf are history
and are left as they are; rewriting them would be inventing a record.

Ported from C:\\nscrev\\ger-contract-revisions-20260916\\main_write.py (G15b): every function takes a
`journal` path so a caller, including a test, can point it at a throwaway file without touching the live
journal.

G15b round 2 (reviewer finding: live-journal hazard): a caller that omits `journal` no longer always gets
the live path. `default_journal(repo)` resolves it instead - the live journal only for the canonical
checkout, a per-repo fallback file otherwise - and the two ger-tools commit scripts call it themselves when
`--journal` is not given, so a test running against any other clone can never append to the live journal.

G15b round 3 (re-check findings): `journal` is a required keyword argument on every function, so no caller
can reach the live journal by omitting it (None is refused too), and a repo without `.git` is a clean
SystemExit instead of a traceback.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import re

JOURNAL = pathlib.Path(r"C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md")
CANONICAL_REPO = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")

# The shape `open_writes` can parse back out of the journal. A role that does not
# match it writes a START this module can never see again - invisible, so the
# guard would be dead for that role exactly as it was dead for everyone before.
# Validated at write time rather than trusted, because the failure is silent.
ROLE_PATTERN = re.compile(r"^[A-Za-z ]+(?:Agent|Steward|Orchestrator)$")


def resolve_role(explicit: str | None = None) -> str:
    """The role writing to main: given, or from NSC_ROLE, or refused.

    There is deliberately no default. A default is what made the guard useless -
    every caller inherited "GER Agent" and the collision check compared a role
    against itself.
    """
    role = (explicit or os.environ.get("NSC_ROLE") or "").strip()
    if not role:
        raise SystemExit(
            "main_write needs the role that is writing: pass --role, or set "
            "NSC_ROLE. There is no default on purpose - a default is what made "
            "the one-writer guard compare every role against itself.")
    if not ROLE_PATTERN.match(role):
        raise SystemExit(
            f"role {role!r} cannot be read back out of the journal: it must be "
            f"words ending in Agent, Steward or Orchestrator (for example "
            f"'Pipeline Maintainer Agent'). A role this module cannot parse "
            f"writes a START that the collision check will never see.")
    return role


def _git_dir(repo: pathlib.Path) -> pathlib.Path:
    """The repo's own git directory, resolving a `.git` file (worktree/submodule) to its real gitdir."""
    dot_git = repo / ".git"
    if dot_git.is_dir():
        return dot_git
    try:
        text = dot_git.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise SystemExit(f"{repo} is not a git checkout (no readable .git): {error}") from error
    prefix = "gitdir: "
    if not text.startswith(prefix):
        raise SystemExit(f"{dot_git} is not a recognized git dir pointer")
    target = pathlib.Path(text[len(prefix):])
    return target if target.is_absolute() else (repo / target).resolve()


def default_journal(repo: pathlib.Path) -> pathlib.Path:
    """The journal path a caller gets when it passes no explicit `journal`/`--journal`.

    The live graph-lead journal only when `repo` is (resolved, case-insensitively) the canonical
    checkout; any other repo - including every test clone - gets its own `nsc-main-write-journal.md`
    inside its git dir instead, so it can never append to the live journal. This is the tools' own
    default-resolution rule (defense in depth even if a caller forgets `--journal`); it does not read or
    write anything by itself.
    """
    try:
        is_canonical = str(repo.resolve()).lower() == str(CANONICAL_REPO.resolve()).lower()
    except OSError:
        is_canonical = str(repo).lower() == str(CANONICAL_REPO).lower()
    return JOURNAL if is_canonical else _git_dir(repo) / "nsc-main-write-journal.md"


def _read(journal: pathlib.Path) -> str:
    if journal is None:
        raise SystemExit("main_write needs an explicit journal path; resolve it with default_journal(repo)")
    try:
        return journal.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _append(line: str, *, role: str, journal: pathlib.Path) -> None:
    text = _read(journal)
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    header = f"## {today} {role}"
    headers = [h for h in text.splitlines() if h.startswith("## ")]
    prefix = "" if (not text or text.endswith("\n")) else "\n"
    if not headers or headers[-1].strip() != header:
        prefix += f"\n{header}\n"
    with journal.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix + line + "\n")


def open_writes(minutes: int = 30, *, journal: pathlib.Path) -> list[str]:
    """START lines from the last `minutes` without a later END from the same role."""
    now = dt.datetime.now(dt.timezone.utc)
    pending: dict[str, str] = {}
    for line in _read(journal).splitlines():
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


def start(operation: str, expected_head: str, *, role: str, journal: pathlib.Path) -> None:
    """Refuse if ANOTHER role holds an open write, then record that this one began.

    The filter compares against the CALLER's role, which is the fix: it used to
    compare against a module constant that every START had also been written
    with, so it discarded every open write and refused nothing.
    """
    role = resolve_role(role)
    others = [item for item in open_writes(journal=journal)
              if not item.startswith(f"{role} since")]
    if others:
        raise SystemExit(f"another main write is open: {others}; wait or ask")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    _append(f"- {stamp} UTC MAIN-WRITE START {role}: {operation}, expected HEAD {expected_head[:9]}",
            role=role, journal=journal)


def end(new_head: str, checks: str, *, role: str, journal: pathlib.Path) -> None:
    role = resolve_role(role)
    _append(f"- MAIN-WRITE END {role}: new HEAD {new_head[:9]}; {checks}",
            role=role, journal=journal)
