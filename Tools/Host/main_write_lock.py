#!/usr/bin/env python
"""One admission protocol for every writer of canonical `main`.

Designed by Astra (gpt-6-astra, xhigh) on 2026-09-22 at the Pipeline
Maintainer's request; implemented here. The design report is
`codex-design-report.md` in that day's MainWriteLock shared folder. Where this
file departs from that design it says so.

WHAT BINDS, AND WHAT DOES NOT

`git update-ref <ref> <new> <old>` is a compare-and-swap that git enforces:

    update-ref refs/locks/main-write <A> ""   -> succeeds only when absent
    update-ref refs/locks/main-write <B> ""   -> fatal: reference already exists
    update-ref -d refs/locks/main-write <B>   -> error: is at <A> but expected <B>

**The lock binds every writer that ADDRESSES THE SAME REPOSITORY. It does not
bind "any tool from any clone", and an earlier version of this claim said it
did.** Measured 2026-09-22: an independent clone has no `refs/locks/*` at all,
its `--git-common-dir` is its own `.git`, and the default refspec
`+refs/heads/*:refs/remotes/origin/*` never fetches them. Linked worktrees share
refs through a common Git directory; independent clones do not. So `repo` is
required everywhere here, must name the canonical repository being modified
rather than the clone the script happens to live in, and **is never resolved
against the current directory**. A clone-local absence of the ref does not mean
`main` is free.

NO AUTOMATIC AGE-ONLY RECLAMATION. THIS IS THE POINT OF THE REDESIGN.

The predecessor deleted any lock older than 1800 seconds and took it. That is
unsafe for a reason no threshold fixes: **an expired timestamp does not revoke a
running process's ability to write.** The displaced holder is not notified, not
stopped, and not checked; it carries on writing while a second writer believes
it holds exclusive access. Making two tools agree on one threshold does not help
-- a single shared threshold still steals from a sufficiently long-running live
operation.

So: a held lock is never broken automatically, at any age. `acquire` waits, then
refuses and names the holder. Reclaiming a crashed writer's lock is an explicit
operator action, `recover()`, which the caller may only perform after
establishing that the writer and its descendants have stopped.

`OVERDUE_SECONDS` is a *warning* threshold and carries no authority to delete.
It is 60 seconds, not 1800, and that number is measured rather than guessed:
across four real merges on 2026-09-22 the whole START-to-END bracket was 1, 1, 2
and 1 seconds, and a local re-timing put `taskcontrol validate` at ~780ms with
~186ms of git precondition checks. A legitimate holder is three orders of
magnitude below the old threshold, so a lock older than a minute is a crash with
near-certainty and should say so in the same minute rather than half an hour
later. The old 1800s was chosen with no measurement behind it.

WHAT THIS MODULE DELIBERATELY DOES NOT DO

It makes no liveness determination. Checking whether the holder's pid died is
not sufficient -- its git subprocess may still be writing, and pids are reused --
so rather than implement a check that could be wrong, `recover()` requires the
caller to have established termination and records that it claimed to. A guard
that cannot be trusted is worse than an absent one that forces a human to look.
"""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

LOCK_REF = "refs/locks/main-write"
BLOB_SCHEMA = "nsc-main-write-lock/v2"
DEFAULT_TIMEOUT = 120.0
OVERDUE_SECONDS = 60.0
POLL_SECONDS = 0.05
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class MainWriteLockError(RuntimeError):
    """The lock could not be operated on."""


class MainWriteLockBusy(MainWriteLockError):
    """Another writer holds the lock. Carries the holder so callers can name it."""

    def __init__(self, owner: dict, owner_oid: str, overdue_by: float | None):
        self.owner = owner
        self.owner_oid = owner_oid
        self.overdue_by = overdue_by
        super().__init__(self.describe())

    def describe(self) -> str:
        who = self.owner.get("role") or "an unidentified writer"
        what = self.owner.get("operation") or "an unnamed operation"
        where = self.owner.get("host") or "?"
        pid = self.owner.get("pid")
        text = (f"{who} holds {LOCK_REF} for {what} "
                f"(host {where}, pid {pid}, owner {self.owner_oid[:12]})")
        if self.overdue_by is not None and self.overdue_by > 0:
            text += (f"; it is OVERDUE by {self.overdue_by:.0f}s. A legitimate "
                     f"hold is 1-2s, so this is very likely a crashed writer. "
                     f"It will NOT be taken automatically -- establish that the "
                     f"writer and its children have stopped, then run recovery "
                     f"against owner {self.owner_oid}.")
        return text


@dataclass(frozen=True)
class WriteHandle:
    """Proof of ownership. Required to release; never reconstructible by a peer."""

    repo: pathlib.Path
    owner_oid: str
    operation_id: str
    role: str
    operation: str
    expected_head: str
    acquired_at: float
    released: list = field(default_factory=list, compare=False, repr=False)

    @property
    def is_released(self) -> bool:
        return bool(self.released)


def _git(repo: pathlib.Path, *args: str,
         stdin: bytes | None = None) -> tuple[int, str, str]:
    result = subprocess.run(["git", "-C", str(repo), *args], input=stdin,
                            capture_output=True, creationflags=NO_WINDOW)
    return (result.returncode,
            result.stdout.decode("utf-8", "replace").strip(),
            result.stderr.decode("utf-8", "replace").strip())


def _require_repo(repo) -> pathlib.Path:
    """No default, no cwd fallback. The repository is the lock's authority."""
    if repo is None or (isinstance(repo, str) and not repo.strip()):
        raise MainWriteLockError(
            "the main-write lock requires an explicit repo: it binds every "
            "writer that addresses one repository, so resolving it against the "
            "current directory would lock the wrong thing and read as free")
    path = pathlib.Path(repo)
    code, top, error = _git(path, "rev-parse", "--git-dir")
    if code != 0:
        raise MainWriteLockError(f"{path} is not a git repository: {error}")
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def inspect(*, repo) -> tuple[str, dict] | None:
    """(owner_oid, owner) for the current holder, or None. Never writes."""
    repo = _require_repo(repo)
    code, current, _ = _git(repo, "rev-parse", "--verify", "-q", LOCK_REF)
    if code != 0 or not current:
        return None
    code, blob, _ = _git(repo, "cat-file", "blob", current)
    if code != 0:
        return current, {"malformed": "the lock blob could not be read"}
    try:
        owner = json.loads(blob)
    except (ValueError, TypeError):
        return current, {"malformed": blob[:200]}
    return current, owner if isinstance(owner, dict) else {"malformed": blob[:200]}


def overdue_by(owner: dict) -> float | None:
    """Seconds past OVERDUE_SECONDS, or None when it cannot be told."""
    try:
        age = time.time() - float(owner["acquired_epoch"])
    except (KeyError, TypeError, ValueError):
        return None
    return age - OVERDUE_SECONDS


def _write_owner_blob(repo: pathlib.Path, body: dict) -> str:
    payload = json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    code, oid, error = _git(repo, "hash-object", "-w", "--stdin", stdin=payload)
    if code != 0:
        raise MainWriteLockError(f"could not write the lock object: {error}")
    return oid


def acquire(*, repo, role: str, operation: str, expected_head: str = "",
            timeout: float = DEFAULT_TIMEOUT) -> WriteHandle:
    """Take the lock, or raise MainWriteLockBusy. Never breaks a held lock."""
    repo = _require_repo(repo)
    if not isinstance(role, str) or not role.strip():
        raise MainWriteLockError("the main-write lock requires a role")
    if not isinstance(operation, str) or not operation.strip():
        raise MainWriteLockError(
            "the main-write lock requires an operation: a refusal that cannot "
            "say what the holder is doing sends the reader to the journal")

    operation_id = str(uuid.uuid4())
    body = {
        "schema_version": BLOB_SCHEMA,
        "operation_id": operation_id,          # identity; pid+time is not one
        "role": role.strip(),
        "operation": operation.strip(),
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "acquired_epoch": time.time(),
        "acquired_at": _now(),
        "expected_head": expected_head,
    }
    owner_oid = _write_owner_blob(repo, body)

    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if _git(repo, "update-ref", LOCK_REF, owner_oid, "")[0] == 0:
            return WriteHandle(repo=repo, owner_oid=owner_oid,
                               operation_id=operation_id, role=body["role"],
                               operation=body["operation"],
                               expected_head=expected_head,
                               acquired_at=body["acquired_epoch"])
        found = inspect(repo=repo)
        if found is None:
            continue                  # released between our attempt and our look
        current_oid, owner = found
        if time.monotonic() >= deadline:
            raise MainWriteLockBusy(owner, current_oid, overdue_by(owner))
        time.sleep(POLL_SECONDS)


def release(handle: WriteHandle, *, repo=None) -> None:
    """Release only this handle's lock. A duplicate release is a no-op.

    Compare-and-swap against the handle's own owner object, so a stale handle
    can never delete a LATER acquisition -- the failure a module-level "who
    holds it" variable would have allowed, and the one a duplicate `end()` in
    the GER callers would otherwise have caused.
    """
    if not isinstance(handle, WriteHandle):
        raise MainWriteLockError(
            "release requires the WriteHandle that acquire returned; a role or "
            "a re-read of the current holder is not proof of ownership")
    if repo is not None and pathlib.Path(repo).resolve() != handle.repo.resolve():
        raise MainWriteLockError(
            f"handle belongs to {handle.repo}, not {repo}")
    if handle.is_released:
        return
    code, _, error = _git(handle.repo, "update-ref", "-d", LOCK_REF,
                          handle.owner_oid)
    handle.released.append(_now())
    if code != 0:
        found = inspect(repo=handle.repo)
        raise MainWriteLockError(
            f"could not release {LOCK_REF}: {error}. This lock is no longer "
            f"ours -- current holder: "
            f"{'none' if found is None else found[1]}. Do not assume the write "
            f"was exclusive; inspect the repository before trusting it.")


@contextlib.contextmanager
def held(*, repo, role: str, operation: str, expected_head: str = "",
         timeout: float = DEFAULT_TIMEOUT):
    """Hold the lock for the duration. Releases even when the body raises."""
    handle = acquire(repo=repo, role=role, operation=operation,
                     expected_head=expected_head, timeout=timeout)
    try:
        yield handle
    finally:
        with contextlib.suppress(MainWriteLockError):
            release(handle)


def recover(*, repo, expected_owner_oid: str, role: str, reason: str,
            termination_established: bool) -> WriteHandle:
    """Reclaim a crashed writer's lock, after the CALLER proved it stopped.

    This is the only path that displaces another owner, and it is deliberately
    not automatic. `termination_established` is the caller asserting it checked;
    this module cannot check for it, because a dead pid does not prove a dead
    git subprocess and pids are reused. Recording the assertion at least makes
    a wrong one attributable.

    The swap is a compare-and-swap against the exact owner the caller inspected,
    so a recovery that races a legitimate release-and-reacquire refuses instead
    of stealing from the new owner.
    """
    repo = _require_repo(repo)
    if not termination_established:
        raise MainWriteLockError(
            "recovery refuses: establish that the holding writer AND its child "
            "processes have stopped before reclaiming. An expired timestamp is "
            "not evidence of that, which is why this is not automatic.")
    if not isinstance(reason, str) or not reason.strip():
        raise MainWriteLockError("recovery requires a reason; it is recorded")

    found = inspect(repo=repo)
    if found is None:
        raise MainWriteLockError(
            f"{LOCK_REF} is not held; there is nothing to recover")
    current_oid, owner = found
    if current_oid != expected_owner_oid:
        raise MainWriteLockError(
            f"refusing to recover: the lock is held by {current_oid[:12]}, not "
            f"the {expected_owner_oid[:12]} you inspected. It changed hands "
            f"while you were looking -- inspect again.")

    operation_id = str(uuid.uuid4())
    body = {
        "schema_version": BLOB_SCHEMA,
        "operation_id": operation_id,
        "role": role.strip(),
        "operation": f"recovery: {reason.strip()}",
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "acquired_epoch": time.time(),
        "acquired_at": _now(),
        "expected_head": "",
        "recovered_from": {"owner_oid": current_oid, "owner": owner},
        "termination_established_by_caller": True,
    }
    owner_oid = _write_owner_blob(repo, body)
    code, _, error = _git(repo, "update-ref", LOCK_REF, owner_oid, current_oid)
    if code != 0:
        raise MainWriteLockError(
            f"recovery lost the compare-and-swap, nothing changed: {error}")
    return WriteHandle(repo=repo, owner_oid=owner_oid,
                       operation_id=operation_id, role=body["role"],
                       operation=body["operation"], expected_head="",
                       acquired_at=body["acquired_epoch"])
