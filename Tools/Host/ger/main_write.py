"""Main-write protocol journal markers for GER contract commits (nsc-main-orchestrator-guide.md section 5).

start() refuses when another role has a MAIN-WRITE START without an END in the last 30 minutes, then appends
"MAIN-WRITE START <role> <operation> expected HEAD <sha>". end() appends "MAIN-WRITE END <role> new HEAD
<sha>; <checks>". Lines go under a "## <date> GER Agent" section, which is added when the journal's last
section belongs to another role.

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
import pathlib
import re

JOURNAL = pathlib.Path(r"C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md")
CANONICAL_REPO = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")
ROLE = "GER Agent"


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


def _append(line: str, *, journal: pathlib.Path) -> None:
    text = _read(journal)
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    header = f"## {today} {ROLE}"
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


def start(operation: str, expected_head: str, *, journal: pathlib.Path) -> None:
    others = [item for item in open_writes(journal=journal) if not item.startswith(ROLE)]
    if others:
        raise SystemExit(f"another main write is open: {others}; wait or ask")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    _append(f"- {stamp} UTC MAIN-WRITE START {ROLE}: {operation}, expected HEAD {expected_head[:9]}", journal=journal)


def end(new_head: str, checks: str, *, journal: pathlib.Path) -> None:
    _append(f"- MAIN-WRITE END {ROLE}: new HEAD {new_head[:9]}; {checks}", journal=journal)
