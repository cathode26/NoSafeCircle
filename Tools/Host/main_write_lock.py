#!/usr/bin/env python
"""Shared admission for cooperating writers of one actual Git repository.

Git conditional ref creation/removal binds ownership to a fresh UUID-bearing
blob. Linked worktrees share the ordinary ref through their common Git directory;
independent clones do not. Every caller must pass the repository it will mutate.
The handle binds that absolute target and common Git identity once.

No age, PID, role, journal entry or process metadata grants takeover permission.
Sixty seconds means overdue for inspection only; there is no upper bound on a
legitimate hold. Explicit recovery requires the full observed token, a reason,
and the operator's confirmation that the original writer AND its children cannot
continue. It replaces the token atomically, records actual repository state and
releases without resetting or retrying business operations.

Optional process identity is diagnostic. The tracked Pipeline implementation is
used when available; standalone deployments record an explicit unavailable reason.
Neither outcome is automatic liveness proof or recovery authority.
"""
from __future__ import annotations

import contextlib
import argparse
import importlib.util
import json
import os
import re
import pathlib
import socket
import sys
import subprocess
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone

LOCK_REF = "refs/locks/main-write"
BLOB_SCHEMA = "nsc-main-write-lock/v2"
DEFAULT_TIMEOUT = 120.0
OVERDUE_SECONDS = 60.0
POLL_SECONDS = 0.05
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _identity_provider():
    """Load the maintained identity API from this tool's resolved repository."""
    from nsc_paths import canonical, containing_repo
    located = containing_repo() or canonical()
    source = located.path / "Pipeline" / "AssistantControl" / "process_identity.py"
    spec = importlib.util.spec_from_file_location("_main_write_process_identity", source)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load process identity from {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _process_identity() -> dict | str:
    """This process as pid + creation ticks + image, or why not.

    Reuses `Pipeline.AssistantControl.process_identity`, which already
    implements this correctly, rather than writing a second identity
    function -- two implementations of one identity is the same trap as two
    implementations of one lock. Returns a STRING reason on failure, never
    None and never a missing key, so a caller cannot read absence as a pass.
    """
    try:
        identify = _identity_provider().identify
    except (ImportError, OSError) as error:
        return f"unavailable: process_identity could not be imported ({error})"
    with suppress(OSError, ValueError, NotImplementedError):
        found = identify(os.getpid())
        if found is not None:
            return found
        return "unavailable: this process reported no identity"
    return "unavailable: the host identity check refused"


def warn_legacy_writers(journal, *, now=None, stream=None):
    """Expose recent legacy writers during cutover; the journal is never a gate."""
    stream = sys.stderr if stream is None else stream
    try:
        text = pathlib.Path(journal).read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    except (OSError, UnicodeError) as error:
        print(f"WARNING: legacy writer journal could not be read: {journal}: {error}", file=stream)
        return
    now = datetime.now(timezone.utc) if now is None else now
    records = re.compile(r"^- (\d{4}-\d\d-\d\d \d\d:\d\d(?::\d\d)?) UTC MAIN-WRITE (START|END) ([A-Za-z ]+(?:Agent|Steward|Orchestrator)):")
    operation = re.compile(r"; operation [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:\b)", re.I)
    ended = re.compile(r"MAIN-WRITE END ([A-Za-z ]+(?:Agent|Steward|Orchestrator)):")
    pending = {}
    for line in text.splitlines():
        end = ended.search(line)
        if end:
            pending.pop(end.group(1), None)
            continue
        match = records.match(line)
        if not match:
            continue
        stamp, event, role = match.groups()
        if event == "END":
            pending.pop(role, None)
        elif operation.search(line):
            pending.pop(role, None)
        else:
            try:
                when = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            pending[role] = (when, line)
    for role, (when, line) in pending.items():
        if 0 <= (now - when).total_seconds() < 30 * 60:
            print(f"WARNING: recent legacy writer may bypass {LOCK_REF}: {line}. "
                  "Pipeline Maintainer must reconcile this invocation during cutover.", file=stream)


class MainWriteLockError(RuntimeError):
    """The lock could not be operated on."""


class MutationChildUncertain(MainWriteLockError):
    """A started child may still write. Retain ownership for explicit recovery."""


def run_process(*args, **kwargs):
    """subprocess.run equivalent which never hides an unsettled child.

    An interrupted/expired wait does not prove that Git hooks or validator
    descendants stopped. Keep the lock and report the process for recovery.
    Failure to create the process is an ordinary error: no child was started.
    """
    input_data = kwargs.pop("input", None)
    mutation_capable = kwargs.pop("mutation_capable", True)
    timeout = kwargs.pop("timeout", None)
    check = kwargs.pop("check", False)
    if kwargs.pop("capture_output", False):
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    if input_data is not None:
        kwargs["stdin"] = subprocess.PIPE
    child = subprocess.Popen(*args, **kwargs)
    try:
        stdout, stderr = child.communicate(input_data, timeout=timeout)
    except BaseException as error:
        if not mutation_capable:
            # A failed observation cannot modify repository state. Settle the
            # direct reader where possible, but never turn it into ownership.
            with contextlib.suppress(BaseException):
                child.kill()
                child.communicate(timeout=5)
            raise
        raise MutationChildUncertain(
            f"child {child.pid} wait failed; its descendants may still write. "
            "Ownership must be retained until the operation and children are "
            f"confirmed stopped: {type(error).__name__}: {error}") from error
    result = subprocess.CompletedProcess(child.args, child.returncode, stdout, stderr)
    if check:
        result.check_returncode()
    return result


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
            text += (f"; it is OVERDUE by {self.overdue_by:.0f}s and should be "
                     f"INSPECTED. Overdue is not dead: a paused, blocked or "
                     f"overloaded writer is still writing. It will NOT be taken "
                     f"automatically -- establish that the writer and its "
                     f"children cannot continue, then run recovery against "
                     f"owner {self.owner_oid}.")
        return text


@dataclass(frozen=True)
class WriteHandle:
    """Proof of ownership. Required to release; never reconstructible by a peer."""

    repo: pathlib.Path
    common_git_dir: pathlib.Path
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
    result = run_process(["git", "-C", str(repo), *args], input=stdin,
                            capture_output=True, creationflags=NO_WINDOW,
                            mutation_capable=bool(args and args[0] in ("update-ref", "hash-object", "reset")))
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
    path = pathlib.Path(repo).resolve()
    code, top, error = _git(path, "rev-parse", "--git-dir")
    if code != 0:
        raise MainWriteLockError(f"{path} is not a git repository: {error}")
    return path


def _common_dir(repo: pathlib.Path) -> pathlib.Path:
    code, common, error = _git(repo, "rev-parse", "--git-common-dir")
    if code != 0 or not common:
        raise MainWriteLockError(f"cannot resolve repository identity: {error}")
    path = pathlib.Path(common)
    return (path if path.is_absolute() else repo / path).resolve()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def inspect(*, repo) -> tuple[str, dict] | None:
    """(owner_oid, owner) for the current holder, or None. Never writes."""
    repo = _require_repo(repo)
    code, current, error = _git(repo, "rev-parse", "--verify", "--quiet", LOCK_REF)
    # Git emits a warning for a broken ref even with --quiet. Only a clean
    # missing-ref result is absence; never discard diagnostics as "free".
    if code == 1 and not error:
        return None
    if code != 0 or not current:
        raise MainWriteLockError(f"cannot inspect {LOCK_REF}: {error}")
    code, blob, error = _git(repo, "cat-file", "blob", current)
    if code != 0:
        raise MainWriteLockError(f"cannot read lock object {current}: {error}")
    try:
        owner = json.loads(blob)
    except (ValueError, TypeError):
        # Old merger owners remain held; preserve their diagnostic identity.
        parts = blob.split("|")
        if len(parts) >= 3:
            return current, {"role": parts[0], "pid": parts[1],
                             "acquired_epoch": parts[2], "legacy": True}
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
    common = _common_dir(repo)
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
        # A bare pid is not an identity: see the module docstring.
        "process_identity": _process_identity(),
    }
    owner_oid = _write_owner_blob(repo, body)

    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            code, _, error = _git(repo, "update-ref", LOCK_REF, owner_oid, "")
        except MutationChildUncertain as error:
            raise MutationChildUncertain(
                f"{error}; acquisition may hold owner {owner_oid} in {repo}; "
                "inspect after the child is settled") from error
        if code == 0:
            return WriteHandle(repo=repo, common_git_dir=common, owner_oid=owner_oid,
                               operation_id=operation_id, role=body["role"],
                               operation=body["operation"],
                               expected_head=expected_head,
                               acquired_at=body["acquired_epoch"])
        found = inspect(repo=repo)
        if found is None and not ("reference already exists" in error or
                                  "but expected" in error):
            raise MainWriteLockError(f"could not acquire {LOCK_REF}: {error}")
        current_oid, owner = found if found is not None else ("", {})
        # EVERY retry path checks the deadline. The branch where the ref
        # vanished between our attempt and our look used to `continue`
        # without checking it and without sleeping, so a lock that kept
        # appearing and disappearing spun this loop forever with no
        # timeout at all. Found by Codex reading the source, not by a
        # test here -- a contender that never stops is not a refusal a
        # caller can observe.
        if time.monotonic() >= deadline:
            if found is None:
                raise MainWriteLockError(
                    f"timed out acquiring {LOCK_REF}; ownership changed during "
                    f"inspection: {error}")
            raise MainWriteLockBusy(owner, current_oid,
                                    overdue_by(owner) if owner else None)
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
    if _common_dir(_require_repo(handle.repo)) != handle.common_git_dir:
        raise MainWriteLockError("the handle's repository identity changed")
    if repo is not None and _common_dir(_require_repo(repo)) != handle.common_git_dir:
        raise MainWriteLockError(
            f"handle belongs to {handle.repo}, not {repo}")
    if handle.is_released:
        return
    try:
        code, _, error = _git(handle.repo, "update-ref", "-d", LOCK_REF,
                              handle.owner_oid)
    except MutationChildUncertain as error:
        raise MutationChildUncertain(
            f"{error}; release of owner {handle.owner_oid} in {handle.repo} "
            "is uncertain; inspect after the child is settled") from error
    if code != 0:
        found = inspect(repo=handle.repo)
        state = ("still ours" if found and found[0] == handle.owner_oid
                 else "no longer ours")
        raise MainWriteLockError(
            f"could not release {LOCK_REF}: {error}. This lock is {state} "
            f"-- current holder: "
            f"{'none' if found is None else found[1]}. Do not assume the write "
            f"was exclusive; inspect the repository before trusting it.")
    handle.released.append(_now())


@contextlib.contextmanager
def held(*, repo, role: str, operation: str, expected_head: str = "",
         timeout: float = DEFAULT_TIMEOUT):
    """Hold the lock for the duration. Releases even when the body raises."""
    handle = acquire(repo=repo, role=role, operation=operation,
                     expected_head=expected_head, timeout=timeout)
    try:
        yield handle
    except MutationChildUncertain as error:
        raise MutationChildUncertain(
            f"{error}; retained {LOCK_REF} owner {handle.owner_oid} "
            f"in {handle.repo}") from error
    except BaseException:
        release(handle)  # a release failure chains the original body failure
        raise
    else:
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
    if not isinstance(role, str) or not role.strip():
        raise MainWriteLockError("recovery requires a role")
    if not isinstance(expected_owner_oid, str) or not re.fullmatch(
            r"(?:[0-9a-f]{40}|[0-9a-f]{64})", expected_owner_oid):
        raise MainWriteLockError("recovery requires the full observed owner OID")
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
        "process_identity": _process_identity(),
        "recovered_from": {"owner_oid": current_oid, "owner": owner},
        "termination_established_by_caller": True,
    }
    owner_oid = _write_owner_blob(repo, body)
    try:
        code, _, error = _git(repo, "update-ref", LOCK_REF, owner_oid, current_oid)
    except MutationChildUncertain as error:
        raise MutationChildUncertain(
            f"{error}; recovery replacement may hold owner {owner_oid} in {repo}; "
            "inspect after the child is settled") from error
    if code != 0:
        raise MainWriteLockError(
            f"recovery lost the compare-and-swap, nothing changed: {error}")
    return WriteHandle(repo=repo, common_git_dir=_common_dir(repo), owner_oid=owner_oid,
                       operation_id=operation_id, role=body["role"],
                       operation=body["operation"], expected_head="",
                       acquired_at=body["acquired_epoch"])


def recover_and_report(*, report, **kwargs) -> dict:
    """Take recovery ownership, record actual Git state, then release.

    No business operation or rollback runs here. Any failure retains the fresh
    recovery token so another writer cannot hide the state before inspection.
    """
    owner = recover(**kwargs)
    try:
        state = {"repo": str(owner.repo), "common_git_dir": str(owner.common_git_dir),
                 "recovery_owner_oid": owner.owner_oid,
                 "recovered_from": kwargs["expected_owner_oid"], "reason": kwargs["reason"]}
        for name, args in (("head", ("rev-parse", "HEAD")),
                           ("status", ("status", "--porcelain=v1")),
                           ("index", ("diff", "--cached", "--name-status"))):
            code, out, error = _git(owner.repo, *args)
            if code:
                raise MainWriteLockError(f"recovery cannot observe {name}: {error}")
            state[name] = out
        state["in_progress"] = []
        for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
            code, path, error = _git(owner.repo, "rev-parse", "--git-path", marker)
            if code:
                raise MainWriteLockError(f"cannot inspect {marker}: {error}")
            resolved = pathlib.Path(path)
            if not resolved.is_absolute():
                resolved = owner.repo / resolved
            if resolved.exists():
                state["in_progress"].append(marker)
        with pathlib.Path(report).open("x", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        release(owner)
        return state
    except BaseException as error:
        raise MainWriteLockError(
            f"recovery did not complete: {error}; retained recovery owner "
            f"{owner.owner_oid} in {owner.repo}. Inspect before retrying.") from error


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or explicitly recover a main-write lock.")
    commands = parser.add_subparsers(dest="command", required=True)
    view = commands.add_parser("inspect")
    view.add_argument("--repo", required=True, type=pathlib.Path)
    repair = commands.add_parser("recover")
    repair.add_argument("--repo", required=True, type=pathlib.Path)
    repair.add_argument("--owner-oid", required=True)
    repair.add_argument("--role", required=True)
    repair.add_argument("--reason", required=True)
    repair.add_argument("--termination-established", action="store_true", required=True,
                        help="assert the original writer AND its children cannot continue")
    repair.add_argument("--report", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            print(json.dumps(inspect(repo=args.repo), indent=2))
        else:
            result = recover_and_report(repo=args.repo, expected_owner_oid=args.owner_oid,
                                        role=args.role, reason=args.reason,
                                        termination_established=args.termination_established,
                                        report=args.report)
            print(f"Lock cleared; repository state recorded in {args.report}. "
                  "No reset, repair, merge or commit was performed.")
            print(json.dumps(result, indent=2))
    except MainWriteLockError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
