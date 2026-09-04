"""Durable host owner for pooled ExecutionCrew provider conversations.

The owner is deliberately narrower than the task scheduler.  It reserves four
role-scoped Claude conversations immediately before one Docker ExecutionCrew
run, persists the exact leases under an operating-system lock, and settles them
from the hash-exact ``crew_result.json`` after Docker returns.  The lock is
never held while Docker or a provider is running.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Iterator, Mapping

from Pipeline.AgentRuntime.session_lifecycle import SessionLifecycleTelemetry
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


OWNER_SCHEMA_VERSION = "1.0"
LEASE_BUNDLE_SCHEMA_VERSION = "1.0"
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
}


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
            if run_id in state["assignments"]:
                raise ExecutionCrewSessionPoolError(
                    f"pooled run identity already exists: {run_id}"
                )
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
                probation = [
                    item
                    for item in pool.sessions_for("probation")
                    if item.compatibility == compatibility
                ]
                try:
                    if probation:
                        probation.sort(key=lambda item: item.record_id)
                        lease = pool.offer_probation_retry(
                            compatibility=compatibility,
                            record_id=probation[0].record_id,
                            worker_slot_id=worker_slot_id,
                            task_id=task_id,
                            worker_run_id=run_id,
                            source_commit=source_commit,
                            checkout_identity=checkout_identity,
                        )
                    else:
                        lease = pool.checkout(
                            compatibility=compatibility,
                            worker_slot_id=worker_slot_id,
                            task_id=task_id,
                            worker_run_id=run_id,
                            source_commit=source_commit,
                            checkout_identity=checkout_identity,
                        )
                except SessionPoolError as exc:
                    raise ExecutionCrewSessionPoolError(
                        f"ExecutionCrew role sessions could not be reserved: {exc}"
                    ) from exc
                leases[role] = lease
            bundle_path = self.assignment_root / f"{run_id}.leases.json"
            bundle = {
                "schema_version": LEASE_BUNDLE_SCHEMA_VERSION,
                "run_id": run_id,
                "leases": {role: leases[role].to_dict() for role in CREW_SESSION_ROLES},
            }
            _write_verified(bundle_path, _json_bytes(bundle))
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
            }
            self._save(state, pool, telemetry)
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
            for role in CREW_SESSION_ROLES:
                pool.quarantine(
                    AssignmentLease.from_dict(assignment["leases"][role]),
                    f"terminal crew run produced no authoritative result: {reason}",
                    outcome="output_failure",
                )
            assignment["status"] = "failed"
            assignment["settled_generation"] = state["generation"] + 1
            self._save(state, pool, telemetry)

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
            role for role in CREW_SESSION_ROLES if records[role]["invoked"]
        }:
            raise ExecutionCrewSessionPoolError(
                "pooled crew result durable role set is inconsistent"
            )
        for role in CREW_SESSION_ROLES:
            lease, durable = decisions[role]
            if durable is None:
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
        if state["schema_version"] != OWNER_SCHEMA_VERSION:
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
            if set(assignment) != _ASSIGNMENT_FIELDS or assignment["run_id"] != run_id:
                raise ExecutionCrewSessionPoolError(
                    "pool assignment fields differ from schema"
                )
            if assignment["status"] not in {"active", "settled", "failed", "cancelled"}:
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
    "OWNER_SCHEMA_VERSION",
    "POOL_CAPACITY",
]
