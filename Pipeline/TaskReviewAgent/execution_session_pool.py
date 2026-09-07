"""Durable host owner for pooled ExecutionCrew provider conversations.

The owner is deliberately narrower than the task scheduler.  It reserves four
role-scoped Claude conversations immediately before one Docker ExecutionCrew
run, persists the exact leases under an operating-system lock, and settles them
from the hash-exact ``crew_result.json`` after Docker returns.  The pool-state
lock is never held while Docker or a provider is running.

One separate per-run lock is deliberately held for exactly that long.  It is
the durable evidence that a run still has an owning controller: the operating
system releases it when that process exits, however it exits, so a run stranded
by a crash becomes provably reclaimable while an owned one never does.  Age is
never used for that decision, because a legitimate assignment may run for hours.
The lock proves the controller is gone, not that the crew container stopped; it
is the right evidence because only a host controller can settle an assignment,
so an unowned run can never be settled at all.  Reclaiming only quarantines: it
signals no process, touches no container, and deletes no provider history.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
from typing import Any, BinaryIO, Iterable, Iterator, Mapping

from Pipeline.AgentRuntime.session_lifecycle import SessionLifecycleTelemetry
from Pipeline.AgentRuntime.contracts import AgentResult
from Pipeline.TaskExecution.contracts import TaskExecutionRequest
from Pipeline.ExecutionCrew.run_crew import ROLE_CAPABILITY_CLASSES
from Pipeline.ExecutionCrew.session_pool import (
    CREW_SESSION_ROLES,
    AssignmentLease,
    DurableAssignmentResult,
    SessionCompatibility,
    SessionPool,
    SessionPoolError,
)

from .contracts import semantic_sha256, validate_task_id
from .real_checkout import _normalized_remote


OWNER_SCHEMA_VERSION = "1.1"
# 1.0 assignments predate durable liveness evidence and load unchanged.
# The version is bumped so an older build rejects a newer state file with
# "unsupported schema" rather than a misleading field-set mismatch.
_SUPPORTED_OWNER_SCHEMA_VERSIONS = frozenset({"1.0", "1.1"})
LEASE_BUNDLE_SCHEMA_VERSION = "1.0"
LIVENESS_SCHEMA_VERSION = "1.0"
LIVENESS_KIND = "exclusive-file-lock"
POOL_CAPACITY = 40
CHECKOUT_IDENTITY_PREFIX = "manifest-sha256:"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_ASSIGNMENT_FIELDS = {
    "run_id",
    "task_id",
    "worker_slot_id",
    "source_commit",
    "task_contract_sha256",
    "checkout_identity",
    "repository_identity",
    "provider_identifier",
    "model",
    "reasoning_effort",
    "leases",
    "lease_bundle_path",
    "result_path",
    "status",
    "result_sha256",
    "settled_generation",
    "liveness",
}
# Assignments written before durable liveness evidence existed. They load
# unchanged and are normalized to "no evidence", which keeps them active and
# never reclaimable: absence of evidence is not evidence that a run is unowned.
_LEGACY_ASSIGNMENT_FIELDS = _ASSIGNMENT_FIELDS - {"liveness"}
_ASSIGNMENT_STATUSES = {"active", "settled", "failed", "cancelled", "stranded"}


class ExecutionCrewSessionPoolError(RuntimeError):
    """The production pool contract or persisted identity was invalid."""


class ExecutionCrewSessionPoolPersistenceError(ExecutionCrewSessionPoolError):
    """The pool could not durably commit and verify one transition."""


def _strict_json(payload: bytes, *, label: str) -> Any:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExecutionCrewSessionPoolError(f"{label} is not valid UTF-8") from exc

    def duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=duplicate_guard,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant {value}")
            ),
        )
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ExecutionCrewSessionPoolError(f"{label} is not strict JSON: {exc}") from exc


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_verified(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if path.read_bytes() != payload:
            raise ExecutionCrewSessionPoolPersistenceError(
                f"durable pool write could not be verified: {path}"
            )
    except ExecutionCrewSessionPoolPersistenceError:
        raise
    except OSError as exc:
        raise ExecutionCrewSessionPoolPersistenceError(
            f"durable pool write failed: {path}: {exc}"
        ) from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    """Hold one cross-process file lock for a short pool transaction."""

    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    try:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()


def _open_lock_region(path: Path) -> BinaryIO:
    """Open one single-byte lock region without truncating an existing file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    try:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
    except OSError:
        stream.close()
        raise
    return stream


def _acquire_liveness_lock(path: Path) -> BinaryIO:
    """Take the exclusive liveness lock for one run, or raise.

    This lock is deliberately *held for the whole worker invocation*, unlike
    ``_exclusive_file_lock``, which guards only a short pool transaction and is
    never held while Docker or a provider runs. Holding it is what makes owner
    death observable: the operating system releases the lock when the owning
    process exits, however it exits.
    """

    stream = _open_lock_region(path)
    try:
        _lock_region_exclusive_nonblocking(stream)
    except BaseException:
        stream.close()
        raise
    return stream


def _file_identity(stream: BinaryIO) -> tuple[int, int] | None:
    """Return the open file's (device, inode) identity, or None if unavailable."""

    try:
        status = os.fstat(stream.fileno())
    except OSError:
        return None
    if not status.st_ino:
        return None
    return (int(status.st_dev), int(status.st_ino))


def _lock_region_exclusive_nonblocking(stream: BinaryIO) -> None:
    """Take the region exclusively without waiting, or raise.

    A refusal is reported as ``PermissionError`` by ``msvcrt`` and as
    ``BlockingIOError`` by ``fcntl``; both mean another open handle -- in this
    process or any other -- already holds the region.
    """

    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_liveness_lock(stream: BinaryIO) -> None:
    """Release one held liveness lock, tolerating an already-closed stream."""

    try:
        if not stream.closed:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except OSError:
        # Process exit releases the region regardless; a failed explicit
        # unlock must never mask the transition that requested it.
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _probe_liveness(descriptor: Any, *, host: str) -> tuple[str, str]:
    """Decide whether the process that owns one run is provably gone.

    Returns ``(verdict, detail)`` where ``verdict`` is exactly one of:

    ``"unowned"``
        The exclusive lock was acquired, so the operating system released it,
        so no process on this host owns this run.
    ``"live"``
        The lock is held. A controller owns this run and must not be disturbed.
    ``"unknown"``
        Ownership is not decidable from durable evidence here. The caller must
        keep the lease active and report ``detail`` as the precise blocker.

    Elapsed time is deliberately not an input: a legitimate assignment may run
    for hours, and age is not evidence of anything.

    What the lock proves, precisely: the *controller* that reserved the leases
    is gone. It does not prove that the Docker crew container is gone, because
    the container is not a descendant of the controller and never holds this
    lock. That distinction is deliberate and sufficient here, because settling
    an assignment is something only a host controller can do: once no process
    owns the run, nothing will ever settle it, so its leases can never be
    released by the normal path. Reclaiming is therefore about a run that
    *cannot resume*, not about a process proven to have stopped computing.

    Reclaiming stays conservative in every direction: it quarantines, which
    only withdraws conversations from reuse. No process is signalled, no
    container is touched, no provider history is deleted, and the run's
    artifacts stay on disk. A container that outlives its controller and later
    writes ``crew_result.json`` is not lost -- it is simply no longer settled
    automatically, and the operator can inspect it. Ordering protects the
    common case: ``_recover_persisted_results`` settles any run whose exact
    result already exists before reclamation is considered at all.
    """

    if not isinstance(descriptor, Mapping):
        return "unknown", "assignment predates durable liveness evidence"
    if descriptor.get("schema_version") != LIVENESS_SCHEMA_VERSION:
        return "unknown", "liveness evidence uses an unsupported schema"
    if descriptor.get("kind") != LIVENESS_KIND:
        return "unknown", f"unsupported liveness evidence kind: {descriptor.get('kind')!r}"
    recorded_platform = descriptor.get("platform")
    if recorded_platform != os.name:
        # Windows byte-range locks and POSIX flock locks do not interoperate,
        # so a foreign-platform record can never be evaluated here.
        return (
            "unknown",
            f"run was recorded on platform {recorded_platform!r}, not {os.name!r}",
        )
    recorded_host = descriptor.get("host")
    if recorded_host != host:
        # A lock observed across a shared filesystem from another machine is
        # not proof of anything about the owning host's processes.
        return (
            "unknown",
            f"run is owned by host {recorded_host!r} and cannot be proven dead from {host!r}",
        )
    raw_path = descriptor.get("path")
    if type(raw_path) is not str or not raw_path:
        return "unknown", "liveness evidence records no lock path"
    path = Path(raw_path)
    if not path.is_file():
        return "unknown", f"liveness lock file is missing: {path}"
    try:
        stream = _open_lock_region(path)
    except OSError as exc:
        # Not being able to open the file says nothing about the worker.
        return "unknown", f"liveness lock file could not be opened: {exc}"
    identity = _file_identity(stream)
    recorded_identity = descriptor.get("file_identity")
    if identity is None or recorded_identity != list(identity):
        # The path was replaced, so an owner may still hold the original file
        # while this name resolves to a different one. Locking this file would
        # succeed and would say nothing about that owner.
        stream.close()
        return (
            "unknown",
            f"liveness lock file identity at {path} differs from the recorded run",
        )
    try:
        _lock_region_exclusive_nonblocking(stream)
    except (BlockingIOError, PermissionError):
        # The ordinary "a worker holds this" answer on both platforms:
        # PermissionError from msvcrt, BlockingIOError from flock.
        stream.close()
        return "live", f"the owning process still holds {path}"
    except OSError as exc:
        stream.close()
        return "unknown", f"liveness lock could not be evaluated: {exc}"
    except Exception as exc:  # pragma: no cover - platform lock API absent
        stream.close()
        return "unknown", f"liveness lock API is unavailable: {exc}"
    _release_liveness_lock(stream)
    return "unowned", f"no process holds {path}; the run has no owner and cannot resume"


class ExecutionCrewSessionPoolOwner:
    """Own one repository-scoped, process-safe pool of ExecutionCrew sessions."""

    def __init__(
        self,
        *,
        checkout: Path | str,
        output_root: Path | str | None = None,
        manifest_path: Path | str | None = None,
    ) -> None:
        self.checkout = Path(checkout).resolve()
        self.output_root = Path(
            output_root
            or self.checkout / "Pipeline" / "ExecutionCrew" / "outputs"
        ).resolve()
        self.manifest_path = Path(
            manifest_path
            or self.checkout.parent / ".task-review-agent" / f"{self.checkout.name}.json"
        ).resolve()
        self.repository_identity = self._repository_identity()
        repository_hash = hashlib.sha256(
            self.repository_identity.encode("utf-8")
        ).hexdigest()
        self.root = (
            self.checkout.parent
            / ".task-review-agent"
            / "session-pools"
            / repository_hash
        )
        self.state_path = self.root / "execution-crew.json"
        self.lock_path = self.root / "execution-crew.lock"
        self.assignment_root = self.root / "assignments"
        self.host_identity = socket.gethostname()
        # Liveness locks this process currently holds, keyed by run identity.
        # A held entry proves this owner is alive for that run without asking
        # the operating system, so a run is never mistaken for dead in-process.
        self._liveness_holds: dict[str, BinaryIO] = {}

    def liveness_path(self, run_id: str) -> Path:
        return self.assignment_root / f"{run_id}.alive"

    def _repository_identity(self) -> str:
        try:
            completed = subprocess.run(
                ("git", "remote", "get-url", "origin"),
                cwd=str(self.checkout),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30.0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExecutionCrewSessionPoolError(
                "task checkout repository identity could not be read"
            ) from exc
        if completed.returncode != 0:
            raise ExecutionCrewSessionPoolError(
                "task checkout has no readable origin repository identity"
            )
        try:
            value = completed.stdout.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise ExecutionCrewSessionPoolError(
                "task checkout origin is not valid UTF-8"
            ) from exc
        if not value:
            raise ExecutionCrewSessionPoolError("task checkout origin is empty")
        return value

    def checkout_manifest_identity(
        self,
        *,
        task_id: str,
        worker_slot_id: str,
        source_commit: str,
        task_contract_sha256: str | None = None,
    ) -> str:
        task_id = validate_task_id(task_id)
        try:
            payload = self.manifest_path.read_bytes()
        except OSError as exc:
            raise ExecutionCrewSessionPoolError(
                f"external checkout identity manifest is unreadable: {self.manifest_path}"
            ) from exc
        value = _strict_json(payload, label="external checkout identity manifest")
        if type(value) is not dict:
            raise ExecutionCrewSessionPoolError(
                "external checkout identity manifest must be an object"
            )
        manifest_hash = value.get("manifest_sha256")
        body = {key: item for key, item in value.items() if key != "manifest_sha256"}
        if manifest_hash != semantic_sha256(body):
            raise ExecutionCrewSessionPoolError(
                "external checkout identity manifest hash is invalid"
            )
        manifest_contract = (value.get("schema_version"), value.get("authority"))
        if manifest_contract not in {
            ("1.0", "checkout_preparation_only"),
            ("2.0", "durable_checkout_identity"),
        }:
            raise ExecutionCrewSessionPoolError(
                "external checkout identity manifest has an unsupported contract"
            )
        if value.get("task_id") != task_id:
            raise ExecutionCrewSessionPoolError(
                "external checkout identity manifest names a different task"
            )
        if task_contract_sha256 is not None and (
            value.get("task_contract_path") != f"Tasks/{task_id}.yaml"
            or value.get("task_contract_sha256") != task_contract_sha256
        ):
            raise ExecutionCrewSessionPoolError(
                "external checkout identity manifest names a different task contract"
            )
        try:
            manifest_checkout = Path(str(value.get("checkout_path") or "")).resolve()
        except (OSError, ValueError) as exc:
            raise ExecutionCrewSessionPoolError(
                "external checkout identity manifest path is invalid"
            ) from exc
        if manifest_checkout != self.checkout:
            raise ExecutionCrewSessionPoolError(
                "external checkout identity manifest names a different checkout"
            )
        if _normalized_remote(str(value.get("remote_url") or "")) != _normalized_remote(
            self.repository_identity
        ):
            raise ExecutionCrewSessionPoolError(
                "external checkout identity manifest names a different repository"
            )
        try:
            current_head = subprocess.run(
                ("git", "rev-parse", "HEAD"),
                cwd=str(self.checkout),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=30.0,
            ).stdout.decode("utf-8").strip()
            current_branch = subprocess.run(
                ("git", "branch", "--show-current"),
                cwd=str(self.checkout),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=30.0,
            ).stdout.decode("utf-8").strip()
        except (OSError, UnicodeDecodeError, subprocess.SubprocessError) as exc:
            raise ExecutionCrewSessionPoolError(
                "task checkout branch and commit identity could not be read"
            ) from exc
        if current_head != source_commit or value.get("branch") != current_branch:
            raise ExecutionCrewSessionPoolError(
                "external checkout identity manifest differs from the current branch or commit"
            )
        if manifest_contract == ("1.0", "checkout_preparation_only") and (
            value.get("worker_id") != worker_slot_id
            or value.get("source_head") != source_commit
        ):
            raise ExecutionCrewSessionPoolError(
                "prepared checkout manifest differs from the scheduler worker or source commit"
            )
        return CHECKOUT_IDENTITY_PREFIX + hashlib.sha256(payload).hexdigest()

    def prepare(
        self,
        *,
        run_id: str,
        task_id: str,
        worker_slot_id: str,
        source_commit: str,
        task_contract_sha256: str,
        model: str,
        reasoning_effort: str | None = None,
    ) -> dict[str, Any]:
        """Durably reserve the four Claude role sessions for one exact run."""

        task_id = validate_task_id(task_id)
        if _RUN_ID.fullmatch(run_id) is None:
            raise ExecutionCrewSessionPoolError("pooled run_id has an invalid form")
        if _COMMIT.fullmatch(source_commit) is None:
            raise ExecutionCrewSessionPoolError("pooled source_commit must be exact")
        if type(task_contract_sha256) is not str or re.fullmatch(
            r"[0-9a-f]{64}", task_contract_sha256
        ) is None:
            raise ExecutionCrewSessionPoolError(
                "pooled task_contract_sha256 must be exact"
            )
        if type(worker_slot_id) is not str or not worker_slot_id.strip():
            raise ExecutionCrewSessionPoolError("worker_slot_id must be non-empty")
        if type(model) is not str or not model.strip():
            raise ExecutionCrewSessionPoolError("pooled Claude model must be exact")
        if reasoning_effort is not None:
            raise ExecutionCrewSessionPoolError(
                "pooled Claude execution does not accept a reasoning effort"
            )
        checkout_identity = self.checkout_manifest_identity(
            task_id=task_id,
            worker_slot_id=worker_slot_id,
            source_commit=source_commit,
            task_contract_sha256=task_contract_sha256,
        )
        with _exclusive_file_lock(self.lock_path):
            state, pool, telemetry = self._load()
            self._recover_persisted_results(state, pool)
            self._reclaim_stranded(state, pool)
            if run_id in state["assignments"]:
                raise ExecutionCrewSessionPoolError(
                    f"pooled run identity already exists: {run_id}"
                )
            # One instant decides both eligibility and admission for every role,
            # so a record can never be judged offerable against one clock and
            # then refused against another inside the same reservation.
            moment = pool.clock()
            # Retire records that left the idle window before any candidate is
            # inspected. Expiry happens inside this saved transaction, so a
            # stale record is durably retired instead of being re-discovered by
            # the next reservation.
            pool.expire_idle(now=moment)
            leases: dict[str, AssignmentLease] = {}
            for role in CREW_SESSION_ROLES:
                compatibility = SessionCompatibility(
                    "claude-code",
                    model.strip(),
                    None,
                    role,
                    ROLE_CAPABILITY_CLASSES[role],
                    self.repository_identity,
                )
                offerable = sorted(
                    (
                        item
                        for item in pool.sessions_for("probation")
                        if item.compatibility == compatibility
                        and item.is_retry_offerable_at(moment)
                    ),
                    key=lambda item: item.record_id,
                )
                lease: AssignmentLease | None = None
                refusals: list[str] = []
                for candidate in offerable:
                    try:
                        lease = pool.offer_probation_retry(
                            compatibility=compatibility,
                            record_id=candidate.record_id,
                            worker_slot_id=worker_slot_id,
                            task_id=task_id,
                            worker_run_id=run_id,
                            source_commit=source_commit,
                            checkout_identity=checkout_identity,
                            now=moment,
                        )
                    except SessionPoolError as exc:
                        # One refused probation record must never deny the role.
                        # Try the next offerable record, then a fresh session.
                        refusals.append(f"{candidate.record_id}: {exc}")
                        continue
                    break
                if lease is None:
                    try:
                        lease = pool.checkout(
                            compatibility=compatibility,
                            worker_slot_id=worker_slot_id,
                            task_id=task_id,
                            worker_run_id=run_id,
                            source_commit=source_commit,
                            checkout_identity=checkout_identity,
                            now=moment,
                        )
                    except SessionPoolError as exc:
                        detail = f"ExecutionCrew role sessions could not be reserved: {exc}"
                        if refusals:
                            detail += f" (refused probation retries: {'; '.join(refusals)})"
                        raise ExecutionCrewSessionPoolError(detail) from exc
                leases[role] = lease
            bundle_path = self.assignment_root / f"{run_id}.leases.json"
            bundle = {
                "schema_version": LEASE_BUNDLE_SCHEMA_VERSION,
                "run_id": run_id,
                "leases": {role: leases[role].to_dict() for role in CREW_SESSION_ROLES},
            }
            _write_verified(bundle_path, _json_bytes(bundle))
            # Take the liveness lock before the assignment becomes durable, so
            # no window exists in which an active run is recorded with an
            # unheld lock and another host could read it as dead.
            liveness_path = self.liveness_path(run_id)
            try:
                held = _acquire_liveness_lock(liveness_path)
            except OSError as exc:
                raise ExecutionCrewSessionPoolError(
                    f"pooled run liveness could not be established: {exc}"
                ) from exc
            liveness_identity = _file_identity(held)
            if liveness_identity is None:
                _release_liveness_lock(held)
                raise ExecutionCrewSessionPoolError(
                    "pooled run liveness file identity is unavailable, so a later "
                    f"owner could never prove ownership of {liveness_path}"
                )
            self._liveness_holds[run_id] = held
            state["assignments"][run_id] = {
                "run_id": run_id,
                "task_id": task_id,
                "worker_slot_id": worker_slot_id,
                "source_commit": source_commit,
                "task_contract_sha256": task_contract_sha256,
                "checkout_identity": checkout_identity,
                "repository_identity": self.repository_identity,
                "provider_identifier": "claude-code",
                "model": model.strip(),
                "reasoning_effort": None,
                "leases": {role: leases[role].to_dict() for role in CREW_SESSION_ROLES},
                "lease_bundle_path": str(bundle_path),
                "result_path": str(self.output_root / run_id / "crew_result.json"),
                "status": "active",
                "result_sha256": None,
                "settled_generation": None,
                "liveness": {
                    "schema_version": LIVENESS_SCHEMA_VERSION,
                    "kind": LIVENESS_KIND,
                    "path": str(liveness_path),
                    "file_identity": [liveness_identity[0], liveness_identity[1]],
                    "platform": os.name,
                    "host": self.host_identity,
                    "pid": os.getpid(),
                },
            }
            try:
                self._save(state, pool, telemetry)
            except BaseException:
                # The reservation never became durable, so this process must not
                # keep claiming to own it.
                self.release_liveness(run_id=run_id)
                raise
        return {
            "run_id": run_id,
            "repository_identity": self.repository_identity,
            "checkout_identity": checkout_identity,
            "manifest_path": str(self.manifest_path),
            "lease_bundle_path": str(bundle_path),
            "leases": {role: leases[role].to_dict() for role in CREW_SESSION_ROLES},
        }

    def settle(self, *, run_id: str, result_path: Path | str) -> str:
        """Settle one exact result once; replay of the same bytes is a no-op."""

        path = Path(result_path).resolve()
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise ExecutionCrewSessionPoolError(
                "pooled crew result is missing or unreadable"
            ) from exc
        result = _strict_json(payload, label="pooled crew result")
        if type(result) is not dict:
            raise ExecutionCrewSessionPoolError("pooled crew result must be an object")
        digest = hashlib.sha256(payload).hexdigest()
        with _exclusive_file_lock(self.lock_path):
            state, pool, telemetry = self._load()
            assignment = state["assignments"].get(run_id)
            if assignment is None:
                raise ExecutionCrewSessionPoolError(
                    "pooled crew result names no durable assignment"
                )
            if path != Path(assignment["result_path"]).resolve():
                raise ExecutionCrewSessionPoolError(
                    "pooled crew result path differs from the durable assignment"
                )
            if assignment["status"] != "active":
                if assignment["result_sha256"] is None:
                    raise ExecutionCrewSessionPoolError(
                        f"{assignment['status']} pooled assignment cannot accept a later result"
                    )
                if assignment["result_sha256"] != digest:
                    raise ExecutionCrewSessionPoolError(
                        f"{assignment['status']} pooled result replay has different bytes"
                    )
                return f"already_{assignment['status']}"
            try:
                self._settle_payload(pool, assignment, result, path.parent)
            except (ExecutionCrewSessionPoolError, SessionPoolError) as exc:
                for role in CREW_SESSION_ROLES:
                    lease = AssignmentLease.from_dict(assignment["leases"][role])
                    try:
                        pool.quarantine(
                            lease,
                            f"terminal pooled result failed exact validation: {exc}",
                            outcome="identity_failure",
                        )
                    except SessionPoolError:
                        pass
                assignment["status"] = "failed"
                assignment["result_sha256"] = digest
                assignment["settled_generation"] = state["generation"] + 1
                self._save(state, pool, telemetry)
                raise ExecutionCrewSessionPoolError(str(exc)) from exc
            assignment["status"] = "settled"
            assignment["result_sha256"] = digest
            assignment["settled_generation"] = state["generation"] + 1
            self._save(state, pool, telemetry)
        return "settled"

    def terminal_without_result(self, *, run_id: str, reason: str) -> None:
        """Quarantine every lease when a known-ended process produced no result."""

        with _exclusive_file_lock(self.lock_path):
            state, pool, telemetry = self._load()
            assignment = state["assignments"].get(run_id)
            if assignment is None or assignment["status"] != "active":
                return
            refused: list[str] = []
            for role in CREW_SESSION_ROLES:
                try:
                    pool.quarantine(
                        AssignmentLease.from_dict(assignment["leases"][role]),
                        f"terminal crew run produced no authoritative result: {reason}",
                        outcome="output_failure",
                    )
                except SessionPoolError as exc:
                    # One role the pool can no longer transition must not keep
                    # the other three active. Every role that can leave active
                    # state does so and is committed below; the rest are named.
                    refused.append(f"{role}: {exc}")
            assignment["status"] = "failed"
            assignment["settled_generation"] = state["generation"] + 1
            self._save(state, pool, telemetry)
        self.release_liveness(run_id=run_id)
        if refused:
            raise ExecutionCrewSessionPoolError(
                "pooled roles could not be withdrawn from reuse: " + "; ".join(refused)
            )

    def cancel_unstarted(self, *, run_id: str) -> None:
        """Return every lease after a proven process-start failure."""

        with _exclusive_file_lock(self.lock_path):
            state, pool, telemetry = self._load()
            assignment = state["assignments"].get(run_id)
            if assignment is None or assignment["status"] != "active":
                return
            for role in CREW_SESSION_ROLES:
                pool.cancel(AssignmentLease.from_dict(assignment["leases"][role]))
            assignment["status"] = "cancelled"
            assignment["settled_generation"] = state["generation"] + 1
            self._save(state, pool, telemetry)
        self.release_liveness(run_id=run_id)

    def release_liveness(self, *, run_id: str) -> None:
        """Stop asserting that this process owns one run. Idempotent.

        Releasing is not a pool transition: it changes no lease and no
        assignment status. It only stops this process from proving liveness, so
        a run that never reached a terminal transition becomes reclaimable by a
        later owner instead of being stranded forever.
        """

        stream = self._liveness_holds.pop(run_id, None)
        if stream is not None:
            _release_liveness_lock(stream)

    def release_all_liveness(self) -> None:
        """Release every liveness lock this owner holds. Idempotent.

        Equivalent to the process exiting: the assignments keep whatever status
        they already have, and any that are still active become reclaimable by
        a later owner.
        """

        for run_id in tuple(self._liveness_holds):
            self.release_liveness(run_id=run_id)

    def __enter__(self) -> "ExecutionCrewSessionPoolOwner":
        return self

    def __exit__(self, *_exception: object) -> None:
        self.release_all_liveness()

    def __del__(self) -> None:  # pragma: no cover - finalizer backstop
        try:
            self.release_all_liveness()
        except Exception:
            pass

    def recover_stranded(self, *, run_ids: Iterable[str] | None = None) -> dict[str, Any]:
        """Reclaim leases whose owning worker run is provably gone.

        Fail-closed by construction: a lease is quarantined only when durable
        evidence proves that no process owns its exact run, which is exactly
        when nothing can ever settle it. A live run is left untouched, and an
        undecidable one is left active with its precise blocker reported
        rather than guessed at. Reclaiming quarantines and nothing more: no
        worker is signalled, no container is touched, and no provider
        conversation history is deleted.
        """

        with _exclusive_file_lock(self.lock_path):
            state, pool, telemetry = self._load()
            self._recover_persisted_results(state, pool)
            report = self._reclaim_stranded(state, pool, run_ids=run_ids)
            self._save(state, pool, telemetry)
        return report

    def _reclaim_stranded(
        self,
        state: dict[str, Any],
        pool: SessionPool,
        *,
        run_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Quarantine every lease of every provably unowned run.

        The caller already holds the pool-state lock and is responsible for
        saving. ``_recover_persisted_results`` must run first, so a run whose
        exact result already exists settles normally and is never reclaimed.
        """

        selected = None if run_ids is None else {str(item) for item in run_ids}
        reclaimed: list[dict[str, Any]] = []
        live: list[str] = []
        uncertain: list[dict[str, str]] = []
        for run_id, assignment in sorted(state["assignments"].items()):
            if assignment["status"] != "active":
                continue
            if selected is not None and run_id not in selected:
                continue
            if run_id in self._liveness_holds:
                # This process owns the run right now. No probe can be more
                # authoritative than that, and none is performed.
                live.append(run_id)
                continue
            verdict, detail = _probe_liveness(
                assignment.get("liveness"), host=self.host_identity
            )
            if verdict == "live":
                live.append(run_id)
                continue
            if verdict != "unowned":
                uncertain.append({"run_id": run_id, "blocker": detail})
                continue
            quarantined: list[str] = []
            for role in CREW_SESSION_ROLES:
                lease = AssignmentLease.from_dict(assignment["leases"][role])
                try:
                    pool.quarantine(
                        lease,
                        "stranded run reclaimed because it has no owning "
                        f"controller and can never be settled: {detail}",
                        outcome="other_failure",
                    )
                except SessionPoolError as exc:
                    # A lease the pool no longer holds cannot be reclaimed
                    # twice; the run is still recorded as stranded below.
                    uncertain.append(
                        {"run_id": run_id, "blocker": f"{role} lease was not reclaimable: {exc}"}
                    )
                else:
                    quarantined.append(role)
            assignment["status"] = "stranded"
            assignment["settled_generation"] = state["generation"] + 1
            reclaimed.append(
                {"run_id": run_id, "reason": detail, "quarantined_roles": tuple(quarantined)}
            )
        return {
            "reclaimed": tuple(reclaimed),
            "live": tuple(live),
            "uncertain": tuple(uncertain),
        }

    def _recover_persisted_results(
        self, state: dict[str, Any], pool: SessionPool
    ) -> None:
        for run_id, assignment in sorted(state["assignments"].items()):
            if assignment["status"] != "active":
                continue
            result_path = Path(assignment["result_path"])
            if not result_path.is_file():
                # No process-liveness fact is available here. Active sessions
                # remain exclusively leased and are never stolen.
                continue
            payload = result_path.read_bytes()
            try:
                result = _strict_json(payload, label="recoverable pooled crew result")
                if type(result) is not dict:
                    raise ExecutionCrewSessionPoolError(
                        "recoverable pooled crew result must be an object"
                    )
                self._settle_payload(pool, assignment, result, result_path.parent)
            except (ExecutionCrewSessionPoolError, SessionPoolError) as exc:
                for role in CREW_SESSION_ROLES:
                    lease = AssignmentLease.from_dict(assignment["leases"][role])
                    try:
                        pool.quarantine(
                            lease,
                            f"recoverable terminal result failed exact validation: {exc}",
                            outcome="identity_failure",
                        )
                    except SessionPoolError:
                        pass
                assignment["status"] = "failed"
            else:
                assignment["status"] = "settled"
            assignment["result_sha256"] = hashlib.sha256(payload).hexdigest()
            assignment["settled_generation"] = state["generation"] + 1

    def _settle_payload(
        self,
        pool: SessionPool,
        assignment: dict[str, Any],
        result: Mapping[str, Any],
        evidence_root: Path,
    ) -> None:
        fixed = {
            "run_id": assignment["run_id"],
            "task_id": assignment["task_id"],
            "source_head": assignment["source_commit"],
            "provider": "claude",
            "execution_model": assignment["model"],
            "execution_reasoning_effort": None,
        }
        for field, expected in fixed.items():
            if result.get(field) != expected:
                raise ExecutionCrewSessionPoolError(
                    f"pooled crew result changed {field}"
                )
        task_contract = result.get("task_contract_identity")
        if not isinstance(task_contract, Mapping) or (
            task_contract.get("path") != f"Tasks/{assignment['task_id']}.yaml"
            or task_contract.get("sha256") != assignment["task_contract_sha256"]
        ):
            raise ExecutionCrewSessionPoolError(
                "pooled crew result changed the task contract identity"
            )
        records = result.get("pooled_role_leases")
        durable_records = result.get("durable_assignment_results")
        if type(records) is not dict or set(records) != set(CREW_SESSION_ROLES):
            raise ExecutionCrewSessionPoolError(
                "pooled crew result did not echo all four exact leases"
            )
        if type(durable_records) is not dict:
            raise ExecutionCrewSessionPoolError(
                "pooled crew result omitted durable assignment results"
            )
        decisions: dict[str, tuple[AssignmentLease, DurableAssignmentResult | None]] = {}
        quota_failures = result.get("provider_quota_failures", {})
        if type(quota_failures) is not dict or not set(quota_failures).issubset(CREW_SESSION_ROLES):
            raise ExecutionCrewSessionPoolError("invalid provider quota failure role set")
        for role in CREW_SESSION_ROLES:
            lease = AssignmentLease.from_dict(assignment["leases"][role])
            record = records[role]
            if type(record) is not dict:
                raise ExecutionCrewSessionPoolError(
                    f"pooled lease echo for {role} is not an object"
                )
            expected_lease = lease.to_dict()
            echoed_lease = {key: record.get(key) for key in expected_lease}
            if echoed_lease != expected_lease or set(record) != set(expected_lease) | {
                "invoked",
                "durable_assignment_result",
            }:
                raise ExecutionCrewSessionPoolError(
                    f"pooled crew result changed the {role} lease"
                )
            invoked = record.get("invoked")
            embedded = record.get("durable_assignment_result")
            if type(invoked) is not bool:
                raise ExecutionCrewSessionPoolError(
                    f"pooled crew result has invalid {role} invocation state"
                )
            if role in quota_failures:
                if not invoked or embedded is not None or role in durable_records:
                    raise ExecutionCrewSessionPoolError("quota-exhausted lease must not expose reusable evidence")
                failure = quota_failures[role]
                if (type(failure) is not dict or failure.get("role") != role
                        or failure.get("lease_id") != lease.lease_id
                        or failure.get("session_disposition") != "quarantined"):
                    raise ExecutionCrewSessionPoolError("quota failure differs from its exact lease")
                invocation_id = failure.get("run_id")
                if type(invocation_id) is not str or not re.fullmatch(r"[a-z0-9-]{1,64}", invocation_id):
                    raise ExecutionCrewSessionPoolError("quota failure has invalid invocation identity")
                evidence = failure.get("evidence")
                if type(evidence) is not dict or set(evidence) != {"request.json", "result.json", "provider.log", "task_request.json"}:
                    raise ExecutionCrewSessionPoolError("quota failure omitted exact runtime evidence")
                payloads = {}
                for name, metadata in evidence.items():
                    prefix = "task_execution" if name == "task_request.json" else "agent_runtime"
                    relative = f"{prefix}/{invocation_id}/{name}"
                    path = evidence_root / relative
                    if (type(metadata) is not dict or metadata.get("path") != relative
                            or not path.resolve().is_relative_to(evidence_root.resolve())):
                        raise ExecutionCrewSessionPoolError("quota evidence escaped its crew run")
                    try:
                        payload = path.read_bytes()
                    except OSError as exc:
                        raise ExecutionCrewSessionPoolError("quota evidence is missing or unreadable") from exc
                    if hashlib.sha256(payload).hexdigest() != metadata.get("sha256"):
                        raise ExecutionCrewSessionPoolError("quota evidence hash differs from persisted bytes")
                    payloads[name] = payload
                try:
                    agent_result = AgentResult.from_dict(_strict_json(payloads["result.json"], label="quota AgentResult"))
                    task_request = TaskExecutionRequest.from_dict(_strict_json(payloads["task_request.json"], label="quota task request"))
                    agent_request = _strict_json(payloads["request.json"], label="quota agent request")
                except ValueError as exc:
                    raise ExecutionCrewSessionPoolError("quota evidence has malformed runtime contracts") from exc
                if (agent_result.run_id != invocation_id or agent_result.role != role
                        or agent_result.provider != "claude-code" or agent_result.model != lease.model
                        or agent_result.status != "failed" or agent_result.failure_classification != "quota_exhausted"
                        or agent_result.raw_log_reference != "provider.log"
                        or task_request.task_id != lease.task_id
                        or task_request.task_contract_identity.to_dict() != task_contract
                        or task_request.invocation.run_id != invocation_id or task_request.invocation.role != role
                        or task_request.invocation.provider_configuration_key != "claude-crew"
                        or task_request.invocation.model_capability_class != lease.capability_class
                        or task_request.invocation.to_dict() != agent_request):
                    raise ExecutionCrewSessionPoolError("quota failure is not bound to this assignment")
                decisions[role] = (lease, None)
                continue
            if not invoked:
                if embedded is not None or role in durable_records:
                    raise ExecutionCrewSessionPoolError(
                        f"unused pooled role {role} exposed assignment evidence"
                    )
                decisions[role] = (lease, None)
                continue
            if type(embedded) is not dict or durable_records.get(role) != embedded:
                raise ExecutionCrewSessionPoolError(
                    f"pooled role {role} has inconsistent durable evidence"
                )
            durable = DurableAssignmentResult.from_dict(embedded)
            decisions[role] = (lease, durable)
        if set(durable_records) != {
            role for role in CREW_SESSION_ROLES if records[role]["invoked"] and role not in quota_failures
        }:
            raise ExecutionCrewSessionPoolError(
                "pooled crew result durable role set is inconsistent"
            )
        for role in CREW_SESSION_ROLES:
            lease, durable = decisions[role]
            if role in quota_failures:
                pool.quarantine(lease, "confirmed Claude account quota exhaustion; provider handoff never reuses this lease")
            elif durable is None:
                pool.cancel(lease)
            else:
                pool.check_in(lease=lease, result=durable, evidence_root=evidence_root)

    def _new_state(self) -> dict[str, Any]:
        body = {
            "schema_version": OWNER_SCHEMA_VERSION,
            "generation": 0,
            "pool": SessionPool(max_concurrent_assignments=POOL_CAPACITY).to_dict(),
            "assignments": {},
            "lifecycle_telemetry": [],
        }
        return {"state_sha256": semantic_sha256(body), **body}

    def _load(self) -> tuple[dict[str, Any], SessionPool, list[dict[str, Any]]]:
        state = self._new_state() if not self.state_path.is_file() else _strict_json(
            self.state_path.read_bytes(), label="ExecutionCrew session pool state"
        )
        if type(state) is not dict or set(state) != {
            "schema_version",
            "state_sha256",
            "generation",
            "pool",
            "assignments",
            "lifecycle_telemetry",
        }:
            raise ExecutionCrewSessionPoolError(
                "ExecutionCrew session pool state fields differ from schema"
            )
        if state["schema_version"] not in _SUPPORTED_OWNER_SCHEMA_VERSIONS:
            raise ExecutionCrewSessionPoolError(
                "ExecutionCrew session pool state has an unsupported schema"
            )
        state_body = {key: value for key, value in state.items() if key != "state_sha256"}
        if state["state_sha256"] != semantic_sha256(state_body):
            raise ExecutionCrewSessionPoolError(
                "ExecutionCrew session pool state hash is invalid"
            )
        if type(state["generation"]) is not int or state["generation"] < 0:
            raise ExecutionCrewSessionPoolError("pool generation is invalid")
        if type(state["assignments"]) is not dict:
            raise ExecutionCrewSessionPoolError("pool assignments must be an object")
        for run_id, assignment in state["assignments"].items():
            if _RUN_ID.fullmatch(run_id) is None or type(assignment) is not dict:
                raise ExecutionCrewSessionPoolError("pool assignment identity is invalid")
            fields = set(assignment)
            if fields == _LEGACY_ASSIGNMENT_FIELDS:
                # Pre-liveness assignment: no evidence, never reclaimable.
                assignment["liveness"] = None
                fields = set(assignment)
            if fields != _ASSIGNMENT_FIELDS or assignment["run_id"] != run_id:
                raise ExecutionCrewSessionPoolError(
                    "pool assignment fields differ from schema"
                )
            if assignment["status"] not in _ASSIGNMENT_STATUSES:
                raise ExecutionCrewSessionPoolError("pool assignment status is invalid")
            if type(assignment["leases"]) is not dict or set(
                assignment["leases"]
            ) != set(CREW_SESSION_ROLES):
                raise ExecutionCrewSessionPoolError(
                    "pool assignment must carry four exact leases"
                )
        if type(state["lifecycle_telemetry"]) is not list:
            raise ExecutionCrewSessionPoolError("pool telemetry must be an array")
        for value in state["lifecycle_telemetry"]:
            SessionLifecycleTelemetry.from_dict(value)
        telemetry: list[dict[str, Any]] = []
        try:
            pool = SessionPool.from_dict(
                state["pool"], telemetry_sink=lambda value: telemetry.append(value.to_dict())
            )
        except SessionPoolError as exc:
            raise ExecutionCrewSessionPoolError(
                f"ExecutionCrew session pool state is invalid: {exc}"
            ) from exc
        active_assignment_leases: set[str] = set()
        for run_id, assignment in state["assignments"].items():
            if _COMMIT.fullmatch(assignment["source_commit"]) is None or re.fullmatch(
                r"[0-9a-f]{64}", assignment["task_contract_sha256"]
            ) is None:
                raise ExecutionCrewSessionPoolError(
                    "pool assignment commit or task-contract identity is invalid"
                )
            expected_bundle = self.assignment_root / f"{run_id}.leases.json"
            if Path(assignment["lease_bundle_path"]).resolve() != expected_bundle.resolve():
                raise ExecutionCrewSessionPoolError(
                    "pool assignment lease-bundle path is invalid"
                )
            result_path = Path(assignment["result_path"])
            if not result_path.is_absolute() or result_path.name != "crew_result.json":
                raise ExecutionCrewSessionPoolError(
                    "pool assignment result path is invalid"
                )
            for role in CREW_SESSION_ROLES:
                try:
                    lease = AssignmentLease.from_dict(assignment["leases"][role])
                except SessionPoolError as exc:
                    raise ExecutionCrewSessionPoolError(
                        f"pool assignment lease is invalid: {exc}"
                    ) from exc
                expected = {
                    "role": role,
                    "task_id": assignment["task_id"],
                    "worker_run_id": run_id,
                    "worker_slot_id": assignment["worker_slot_id"],
                    "source_commit": assignment["source_commit"],
                    "checkout_identity": assignment["checkout_identity"],
                    "repository_identity": assignment["repository_identity"],
                    "provider_identifier": assignment["provider_identifier"],
                    "model": assignment["model"],
                    "reasoning_effort": assignment["reasoning_effort"],
                }
                if any(getattr(lease, field) != value for field, value in expected.items()):
                    raise ExecutionCrewSessionPoolError(
                        "pool assignment metadata disagrees with its exact lease"
                    )
                if assignment["status"] == "active":
                    if lease.lease_id in active_assignment_leases:
                        raise ExecutionCrewSessionPoolError(
                            "active pool assignments share a lease identity"
                        )
                    active_assignment_leases.add(lease.lease_id)
            if assignment["status"] == "active":
                if assignment["result_sha256"] is not None or assignment[
                    "settled_generation"
                ] is not None:
                    raise ExecutionCrewSessionPoolError(
                        "active pool assignment carries settlement metadata"
                    )
            else:
                settled_generation = assignment["settled_generation"]
                if (
                    type(settled_generation) is not int
                    or settled_generation < 1
                    or settled_generation > state["generation"]
                ):
                    raise ExecutionCrewSessionPoolError(
                        "terminal pool assignment has invalid settlement generation"
                    )
                result_sha = assignment["result_sha256"]
                if result_sha is not None and re.fullmatch(r"[0-9a-f]{64}", result_sha) is None:
                    raise ExecutionCrewSessionPoolError(
                        "terminal pool assignment result hash is invalid"
                    )
        pool_active = {
            item.active_lease.lease_id
            for item in pool.sessions_for("active")
            if item.active_lease is not None
        }
        if pool_active != active_assignment_leases:
            raise ExecutionCrewSessionPoolError(
                "pool active leases disagree with the assignment journal"
            )
        return state, pool, telemetry

    def _save(
        self,
        state: dict[str, Any],
        pool: SessionPool,
        telemetry: list[dict[str, Any]],
    ) -> None:
        state["generation"] += 1
        state["schema_version"] = OWNER_SCHEMA_VERSION
        state["pool"] = pool.to_dict()
        state["lifecycle_telemetry"].extend(telemetry)
        state_body = {key: value for key, value in state.items() if key != "state_sha256"}
        state["state_sha256"] = semantic_sha256(state_body)
        _write_verified(self.state_path, _json_bytes(state))


__all__ = [
    "CHECKOUT_IDENTITY_PREFIX",
    "ExecutionCrewSessionPoolError",
    "ExecutionCrewSessionPoolOwner",
    "ExecutionCrewSessionPoolPersistenceError",
    "LEASE_BUNDLE_SCHEMA_VERSION",
    "LIVENESS_KIND",
    "LIVENESS_SCHEMA_VERSION",
    "OWNER_SCHEMA_VERSION",
    "POOL_CAPACITY",
]
