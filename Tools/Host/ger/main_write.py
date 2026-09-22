"""GER adapter for the shared main-write Git lock and operation journal.

start requires the actual mutation repository, expected HEAD, role and journal;
end accepts only its returned handle. transaction keeps ownership through checks,
file writes, Git/hooks, validation, restoration and final outcome recording.
Journal history is diagnostic and never decides admission. default_journal uses
the live journal only for the canonical checkout; fixtures get their own Git-dir
journal. A role is attribution, never permission for nested ownership.
"""
from __future__ import annotations

import datetime as dt
import contextlib
from dataclasses import dataclass
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import main_write_lock as lock
from main_write_lock import MutationChildUncertain, run_process

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
            f"cannot be represented by the journal's diagnostic parser.")
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
        start = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?::\d{2})? UTC MAIN-WRITE START ([A-Za-z ]+?(?:Agent|Steward|Orchestrator))", line)
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


@dataclass
class WriteHandle:
    lock: lock.WriteHandle
    journal: pathlib.Path
    ended: bool = False


def _git(repo, *args):
    code, out, error = lock._git(repo, *args)
    if code:
        raise lock.MainWriteLockError(f"git {' '.join(args)} failed: {error}")
    return out


def start(operation: str, expected_head: str, *, repo, role: str,
          journal: pathlib.Path, timeout: float = lock.DEFAULT_TIMEOUT) -> WriteHandle:
    """Acquire first; the journal records ownership and never grants it."""
    role = resolve_role(role)
    if journal is None:
        raise SystemExit("main_write needs an explicit journal path")
    journal = pathlib.Path(journal).resolve()
    owner = lock.acquire(repo=repo, role=role, operation=operation,
                         expected_head=expected_head, timeout=timeout)
    try:
        if _git(owner.repo, "rev-parse", "HEAD") != expected_head:
            raise SystemExit("HEAD moved since planning; rerun")
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        _append(f"- {stamp} UTC MAIN-WRITE START {role}: {operation}, "
                f"expected HEAD {expected_head}; operation {owner.operation_id}",
                role=role, journal=journal)
    except MutationChildUncertain as error:
        raise MutationChildUncertain(f"{error}; retained owner {owner.owner_oid}") from error
    except BaseException:
        lock.release(owner)
        raise
    return WriteHandle(owner, journal)


def end(write: WriteHandle, new_head: str, checks: str) -> None:
    """End exactly the returned operation. Recording failure still releases."""
    if not isinstance(write, WriteHandle):
        raise lock.MainWriteLockError("end requires the exact start WriteHandle")
    if write.ended:
        lock.release(write.lock)  # retry a previous failed release, never append twice
        return
    write.ended = True
    try:
        _append(f"- MAIN-WRITE END {write.lock.role}: new HEAD {new_head}; "
                f"{checks}; operation {write.lock.operation_id}",
                role=write.lock.role, journal=write.journal)
    finally:
        lock.release(write.lock)


@contextlib.contextmanager
def transaction(operation: str, expected_head: str, *, repo, role: str,
                journal: pathlib.Path, touched, expected_files=None,
                timeout=lock.DEFAULT_TIMEOUT):
    """Hold through checks, writes, restoration and observed outcome.

    Planning can happen without ownership. Admission verifies the plan's HEAD
    and inputs, then captures actual restoration bytes while the lock is held.
    A successful commit is never restored because a later report failed.
    """
    write = start(operation, expected_head, repo=repo, role=role,
                  journal=journal, timeout=timeout)
    target = write.lock.repo
    snapshots = None
    outcome = "completed; not pushed"
    observed = "unknown"
    uncertain = False
    try:
        if _git(target, "symbolic-ref", "--short", "HEAD") != "main":
            raise SystemExit("the target is not checked out on main")
        if _git(target, "status", "--porcelain=v1", "--", *touched):
            raise SystemExit("target paths already have uncommitted changes")
        if _git(target, "diff", "--cached", "--name-only"):
            raise SystemExit("the index already has staged paths; refusing to commit")
        for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
            path = pathlib.Path(_git(target, "rev-parse", "--git-path", marker))
            if not path.is_absolute():
                path = target / path
            if path.exists():
                raise SystemExit(f"unfinished Git operation: {marker}")
        for relative, planned in (expected_files or {}).items():
            path = target / relative
            actual = path.read_bytes() if path.exists() else None
            if actual != planned:
                raise SystemExit(f"{relative} changed since planning; rerun")
        snapshots = {relative: ((target / relative).read_bytes()
                                if (target / relative).exists() else None)
                     for relative in touched}
        yield write
    except MutationChildUncertain:
        uncertain = True
        raise
    except BaseException as error:
        outcome = f"failed: {type(error).__name__}: {error}; inspect recorded HEAD"
        try:
            observed = _git(target, "rev-parse", "HEAD")
            if snapshots is not None and observed == expected_head:
                _git(target, "reset", "-q")
                failures = []
                for relative, data in snapshots.items():
                    try:
                        path = target / relative
                        if data is None:
                            path.unlink(missing_ok=True)
                        else:
                            path.write_bytes(data)
                    except OSError as failure:
                        failures.append(f"{relative}: {failure}")
                if failures:
                    raise lock.MainWriteLockError("restoration incomplete: " + "; ".join(failures))
                outcome += "; original touched bytes and empty index restored"
            elif observed != expected_head:
                outcome += "; HEAD changed, committed result retained without restoration"
        except MutationChildUncertain:
            uncertain = True
            raise
        except BaseException as observation_error:
            outcome += f"; restoration/observation failed: {observation_error}"
            raise
        raise
    finally:
        if uncertain:
            print(f"MAIN-WRITE retained owner {write.lock.owner_oid} in {target}; "
                  "confirm writer and children stopped before explicit recovery", file=sys.stderr)
        else:
            observation_failure = None
            try:
                observed = _git(target, "rev-parse", "HEAD")
            except BaseException as observation_error:
                outcome += f"; HEAD observation failed: {observation_error}"
                observation_failure = observation_error
            end(write, observed, outcome)
            if observation_failure is not None:
                raise observation_failure
