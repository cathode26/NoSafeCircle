"""Provider-free repository/branch commit gate, backed by a remote Git CAS journal.

Every update is a child of the last journal commit. Queue, owner, receipts and
wake intent change in ONE exact-OID ref transaction. No expiration grants
ownership. The ordinary task/resource claims and Issue leases are independent.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
import re
import socket
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from .claim_policy import activated_claim_namespace, load_claim_policy
from .claim_refs import _classify_failed_claim_push, _run_git
from .contracts import TaskReviewContractError, canonical_json, validate_task_id
from .git_identity_guard import validated_agent_git_identity
from .issue_workflow_store import _parse_github_repository

SCHEMA = "1.0"
MARKER = "nsc-durable-integration-gate"
SHA = re.compile(r"[0-9a-f]{40}\Z")
TOKEN = re.compile(r"[0-9a-f]{32}\Z")


class IntegrationGateError(TaskReviewContractError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def timestamp(value: str) -> dt.datetime:
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.utcoffset() is None:
            raise ValueError("timezone missing")
        return result.astimezone(dt.timezone.utc)
    except (AttributeError, TypeError, ValueError) as exc:
        raise IntegrationGateError("gate timestamp must include a timezone") from exc


def repository_identity(origin: str) -> str:
    github = _parse_github_repository(origin)
    if github:
        return "github.com/" + "/".join(github).casefold()
    # Local bare remotes are supported for offline integration tests. Remote
    # aliases and credentials are never accepted as canonical identities.
    path = Path(origin)
    if path.is_absolute() and path.exists():
        return path.resolve().as_uri()
    raise IntegrationGateError("gate requires an exact GitHub origin or local bare repository")


def owner_identity(task_id: str, run_id: str, worker_id: str, lease_id: str | None = None) -> dict:
    result = dict(task_id=validate_task_id(task_id), run_id=run_id,
                  worker_id=worker_id, lease_id=lease_id or uuid.uuid4().hex)
    if any(not isinstance(result[k], str) or not result[k].strip() for k in ("run_id", "worker_id")):
        raise IntegrationGateError("gate requires exact run and worker identities")
    if not TOKEN.fullmatch(result["lease_id"]):
        raise IntegrationGateError("gate lease must be an unguessable UUID hex identity")
    return result


def same_owner(owner: Mapping | None, identity: Mapping) -> bool:
    return owner is not None and all(owner.get(k) == identity.get(k)
                                     for k in ("task_id", "run_id", "worker_id", "lease_id"))


def ordered_waiters(state: Mapping) -> list[dict]:
    return sorted(state["queue"], key=lambda w: (timestamp(w["ready_at"]), w["task_id"]))


def eligible_waiters(state: Mapping) -> list[dict]:
    """Quarantine retains the queue entry without making it eligible to own."""
    return [waiter for waiter in ordered_waiters(state) if not waiter.get("quarantine")]


def admissible_waiters(state: Mapping) -> list[dict]:
    """Order proven-disjoint waiters without deleting blocked predecessors."""
    quarantines = [waiter for waiter in state["queue"] if waiter.get("quarantine")]
    result = []
    for waiter in eligible_waiters(state):
        candidate = waiter.get("reservation")
        for quarantined in quarantines:
            reserved = quarantined.get("reservation")
            if (not candidate or not reserved or not candidate["exclusive_resources"]
                    or not reserved["exclusive_resources"]
                    or {item.casefold() for item in candidate["exclusive_resources"]}
                    & {item.casefold() for item in reserved["exclusive_resources"]}):
                break
        else:
            result.append(waiter)
    return result


def validate_waiter_reservation(value: Mapping) -> None:
    if (not isinstance(value, Mapping)
            or set(value) != {"issue_number", "task_contract_sha256", "exclusive_resources"}
            or type(value["issue_number"]) is not int or value["issue_number"] < 1
            or not re.fullmatch(r"[0-9a-f]{64}", str(value["task_contract_sha256"]))
            or not isinstance(value["exclusive_resources"], list)
            or any(not isinstance(item, str) or not item.strip() for item in value["exclusive_resources"])
            or value["exclusive_resources"] != sorted(set(value["exclusive_resources"]))):
        raise IntegrationGateError("malformed durable waiter resource reservation")


class GitIntegrationGate:
    def __init__(self, repository: Path, *, remote: str = "origin", target_branch: str = "main",
                 namespace: str | None = None, clock: Callable[[], str] = utc_now,
                 wake: Callable[[Mapping], Any] | None = None):
        self.repository = Path(repository)
        self.remote = remote
        origin = _run_git(self.repository, "remote", "get-url", remote).stdout.decode().strip()
        self.repository_id = repository_identity(origin)
        if _run_git(self.repository, "check-ref-format", f"refs/heads/{target_branch}", check=False).returncode:
            raise IntegrationGateError("invalid integration target branch")
        self.target_branch = target_branch
        namespace = namespace or activated_claim_namespace(load_claim_policy())
        domain = canonical_json([self.repository_id, target_branch])
        self.domain = hashlib.sha256(domain.encode()).hexdigest()
        self.ref = f"{namespace}/integration-gates/{self.domain}"
        self.clock = clock
        self.wake = wake or send_wake

    def empty(self) -> dict:
        return dict(schema_version=SCHEMA, repository=self.repository_id,
                    target_branch=self.target_branch, revision=0, owner=None,
                    queue=[], event=None)

    def read(self) -> tuple[str, dict]:
        lines = _run_git(self.repository, "ls-remote", self.remote, self.ref).stdout.decode().splitlines()
        if not lines:
            return "", self.empty()
        if len(lines) != 1 or lines[0].split()[1:] != [self.ref]:
            raise IntegrationGateError("ambiguous integration gate ref")
        oid = lines[0].split()[0]
        if not SHA.fullmatch(oid):
            raise IntegrationGateError("invalid integration gate OID")
        _run_git(self.repository, "fetch", "--quiet", "--no-write-fetch-head", self.remote, oid)
        raw = _run_git(self.repository, "show", "-s", "--format=%B", oid).stdout.decode()
        try:
            marker, payload = raw.split("\n", 1)
            state = json.loads(payload)
            if marker != MARKER:
                raise ValueError("marker")
            self.validate(state)
            parents = _run_git(self.repository, "show", "-s", "--format=%P", oid).stdout.decode().split()
            previous = state["event"]["previous_oid"]
            if parents != ([previous] if previous else []) or (state["revision"] == 1) != (not parents):
                raise ValueError("journal parent/revision")
        except (ValueError, KeyError, TypeError) as exc:
            raise IntegrationGateError(f"corrupt or unsupported integration gate {self.ref} at {oid}") from exc
        return oid, state

    def validate(self, state: Mapping) -> None:
        if (set(state) != set(self.empty()) or state["schema_version"] != SCHEMA
                or state["repository"] != self.repository_id or state["target_branch"] != self.target_branch
                or type(state["revision"]) is not int or state["revision"] < 1
                or not isinstance(state["event"], dict) or not isinstance(state["queue"], list)):
            raise IntegrationGateError("gate schema/domain/revision mismatch; reconcile exact ref")
        event = state["event"]
        if (not isinstance(event.get("kind"), str) or not event["kind"].startswith("gate_")
                or (event.get("previous_oid") != "" and not SHA.fullmatch(str(event.get("previous_oid", ""))))):
            raise IntegrationGateError("gate event identity is malformed")
        timestamp(event["occurred_at"])
        tasks = []
        for waiter in state["queue"]:
            tasks.append(validate_task_id(waiter["task_id"]))
            timestamp(waiter["ready_at"])
            if not re.fullmatch(r"[0-9a-f]{64}", waiter["ready_event"]):
                raise IntegrationGateError("queue eligibility event is malformed")
            if not isinstance(waiter["wake_endpoints"], list):
                raise IntegrationGateError("queue wake endpoints malformed")
            for endpoint in waiter["wake_endpoints"]:
                validate_endpoint(endpoint)
            if waiter.get("reservation") is not None:
                validate_waiter_reservation(waiter["reservation"])
            quarantine = waiter.get("quarantine")
            if quarantine is not None:
                if (not isinstance(quarantine, dict)
                        or set(quarantine) != {"reason", "observed_issue_numbers"}
                        or not isinstance(quarantine["reason"], str) or not quarantine["reason"]
                        or not isinstance(quarantine["observed_issue_numbers"], list)
                        or any(type(number) is not int or number < 1 for number in quarantine["observed_issue_numbers"])
                        or quarantine["observed_issue_numbers"] != sorted(set(quarantine["observed_issue_numbers"]))):
                    raise IntegrationGateError("malformed waiter quarantine disposition")
        if len(tasks) != len(set(tasks)):
            raise IntegrationGateError("duplicate gate waiters")
        owner = state["owner"]
        if owner is not None:
            if set(owner) != {"task_id", "run_id", "worker_id", "lease_id", "repository", "target_branch",
                              "acquired_at", "heartbeat_at", "progress", "status", "operation", "unity_seconds", "ci_seconds"}:
                raise IntegrationGateError("gate owner schema mismatch")
            owner_identity(*(owner[k] for k in ("task_id", "run_id", "worker_id", "lease_id")))
            if owner["repository"] != self.repository_id or owner["target_branch"] != self.target_branch:
                raise IntegrationGateError("owner domain mismatch")
            if owner["status"] not in {"held", "quarantined"} or owner["task_id"] in tasks:
                raise IntegrationGateError("invalid gate owner state")
            timestamp(owner["acquired_at"])
            timestamp(owner["heartbeat_at"])
            for key in ("unity_seconds", "ci_seconds"):
                if type(owner[key]) not in (int, float) or not math.isfinite(owner[key]) or owner[key] < 0:
                    raise IntegrationGateError("gate duration is malformed")
            if not isinstance(owner["progress"], str) or not owner["progress"]:
                raise IntegrationGateError("gate progress is missing")
            operation = owner["operation"]
            if operation is not None:
                if (not isinstance(operation, dict) or set(operation) != {"kind", "started_at"}
                        or not isinstance(operation["kind"], str) or not operation["kind"]):
                    raise IntegrationGateError("gate operation is malformed")
                timestamp(operation["started_at"])

    def compare_and_swap(self, expected: str, state: dict, event: dict) -> bool:
        value = copy.deepcopy(state)
        value["revision"] += 1
        value["event"] = {**event, "occurred_at": self.clock(), "previous_oid": expected}
        self.validate(value)
        name, email = validated_agent_git_identity()
        environment = {f"GIT_{role}_{field}": data for role in ("AUTHOR", "COMMITTER")
                       for field, data in (("NAME", name), ("EMAIL", email))}
        tree = _run_git(self.repository, "mktree", input_bytes=b"").stdout.decode().strip()
        oid = _run_git(self.repository, "commit-tree", tree, *(("-p", expected) if expected else ()),
                       input_bytes=(MARKER + "\n" + canonical_json(value) + "\n").encode(),
                       environment=environment).stdout.decode().strip()
        result = _run_git(self.repository, "push", "--porcelain", "--atomic",
                          f"--force-with-lease={self.ref}:{expected}", self.remote,
                          f"{oid}:{self.ref}", check=False)
        if result.returncode:
            classification, _ = _classify_failed_claim_push((self.ref,), result)
            if classification in {"contention", "transient"}:
                return False
            # No blind replay after a transport failure. This action may have
            # reached the remote; an operator/same owner must inspect the journal.
            raise IntegrationGateError(f"gate CAS outcome uncertain; inspect {self.ref} expected {expected or 'absent'} proposed {oid}")
        return True

    def enqueue(self, task_id: str, *, ready_at: str, ready_event: str, endpoint: Mapping | None = None,
                reservation: Mapping | None = None) -> dict:
        task_id = validate_task_id(task_id)
        ready_at = timestamp(ready_at).isoformat()
        if not re.fullmatch(r"[0-9a-f]{64}", ready_event):
            raise IntegrationGateError("eligible gate task requires its durable ready event")
        if endpoint is not None:
            validate_endpoint(endpoint)
        if reservation is not None:
            validate_waiter_reservation(reservation)
        oid, state = self.read()
        if state["owner"] and state["owner"]["task_id"] == task_id:
            return {"status": "owned", "owner": state["owner"]}
        existing = next((w for w in state["queue"] if w["task_id"] == task_id), None)
        if existing:
            if existing.get("quarantine"):
                return {"status": "deferred", "reason": "waiter requires exact workflow reconciliation"}
            if reservation is not None and existing.get("reservation") not in (None, reservation):
                raise IntegrationGateError("queued waiter resource identity changed; reconcile before admission")
            if reservation is not None and existing.get("reservation") is None:
                existing["reservation"] = dict(reservation)
            elif endpoint is None or dict(endpoint) in existing["wake_endpoints"]:
                return {"status": "queued", "waiter": existing}
            if endpoint is not None and dict(endpoint) not in existing["wake_endpoints"]:
                existing["wake_endpoints"].append(dict(endpoint))
        else:
            existing = dict(task_id=task_id, ready_at=ready_at, ready_event=ready_event,
                            wake_endpoints=[dict(endpoint)] if endpoint else [])
            if reservation is not None:
                existing["reservation"] = dict(reservation)
            state["queue"].append(existing)
        state["queue"] = ordered_waiters(state)
        changed = self.compare_and_swap(oid, state, dict(kind="gate_eligible_queued", task_id=task_id,
                                                        ready_at=existing["ready_at"], ready_event=existing["ready_event"]))
        return {"status": "queued" if changed else "deferred", "waiter": existing}

    def acquire(self, identity: Mapping) -> dict:
        identity = owner_identity(*(identity[k] for k in ("task_id", "run_id", "worker_id", "lease_id")))
        oid, state = self.read()
        if state["owner"]:
            if same_owner(state["owner"], identity):
                self.require_owner(state, identity)
                return {"status": "acquired", "owner": state["owner"], "resumed": True}
            return {"status": "deferred", "owner": state["owner"], "reason": "gate occupied; no TTL recovery"}
        queue = admissible_waiters(state)
        if not queue or queue[0]["task_id"] != identity["task_id"]:
            return {"status": "deferred", "reason": "older durable waiter has priority"}
        now = self.clock()
        wait_seconds = max(0.0, (timestamp(now) - timestamp(queue[0]["ready_at"])).total_seconds())
        owner = dict(identity, repository=self.repository_id, target_branch=self.target_branch,
                     acquired_at=now, heartbeat_at=now, progress="acquired", status="held",
                     operation=None, unity_seconds=0.0, ci_seconds=0.0)
        state["owner"] = owner
        state["queue"] = [waiter for waiter in state["queue"] if waiter["task_id"] != identity["task_id"]]
        if not self.compare_and_swap(oid, state, dict(kind="gate_acquired", owner=owner, wait_seconds=wait_seconds)):
            return {"status": "deferred", "reason": "bounded CAS contention"}
        return {"status": "acquired", "owner": owner, "resumed": False}

    def quarantine_waiter(self, task_id: str, *, reason: str, observed_issue_numbers: list[int]) -> bool:
        """Persist unresolved ownership; never withdraw, complete or steal it."""
        task_id = validate_task_id(task_id)
        oid, state = self.read()
        waiter = next((item for item in state["queue"] if item["task_id"] == task_id), None)
        if waiter is None:
            return False
        disposition = dict(reason=reason, observed_issue_numbers=sorted(set(observed_issue_numbers)))
        if waiter.get("quarantine") == disposition:
            return True
        waiter["quarantine"] = disposition
        return self.compare_and_swap(oid, state, dict(kind="gate_waiter_quarantined", task_id=task_id,
                                                     quarantine=disposition))

    def reconcile_waiter(self, task_id: str, *, reservation: Mapping, history_event_ids: list[str],
                         issue_event_id: str) -> bool:
        """Clear quarantine only after the reader proves the original Issue chain."""
        validate_waiter_reservation(reservation)
        oid, state = self.read()
        waiter = next((item for item in state["queue"] if item["task_id"] == task_id), None)
        if waiter is None:
            return False
        if not waiter.get("quarantine"):
            return True
        if (waiter.get("reservation") != reservation or waiter["ready_event"] not in history_event_ids
                or not re.fullmatch(r"[0-9a-f]{64}", issue_event_id)):
            return False
        waiter.pop("quarantine")
        return self.compare_and_swap(oid, state, dict(kind="gate_waiter_reconciled", task_id=task_id,
                                                     issue_event_id=issue_event_id,
                                                     ready_event=waiter["ready_event"]))

    def withdraw(self, task_id: str, *, issue_state: str, issue_event_id: str) -> bool:
        """Remove only a waiter whose durable workflow is no longer eligible."""
        task_id = validate_task_id(task_id)
        if (issue_state not in {"human_action_required", "blocked", "complete"}
                or not re.fullmatch(r"[0-9a-f]{64}", issue_event_id)):
            raise IntegrationGateError("withdrawing a waiter requires a verified noneligible Issue event")
        oid, state = self.read()
        if not any(w["task_id"] == task_id for w in state["queue"]):
            return True
        state["queue"] = [w for w in state["queue"] if w["task_id"] != task_id]
        return self.compare_and_swap(oid, state, dict(kind="gate_waiter_withdrawn", task_id=task_id,
                                                     issue_state=issue_state, issue_event_id=issue_event_id))

    def require_owner(self, state: Mapping, identity: Mapping) -> dict:
        owner = state["owner"]
        if not same_owner(owner, identity) or owner["status"] != "held":
            raise IntegrationGateError(f"exact gate owner unavailable; inspect {self.ref}; never steal by age")
        return owner

    def progress(self, identity: Mapping, stage: str, *, operation: str | None = None, _attempt: int = 0) -> None:
        oid, state = self.read()
        owner = self.require_owner(state, identity)
        now = self.clock()
        prior = owner["operation"]
        if prior and operation is None:
            duration = max(0.0, (timestamp(now) - timestamp(prior["started_at"])).total_seconds())
            if prior["kind"] in {"unity", "ci"}:
                owner[prior["kind"] + "_seconds"] += duration
        if prior and operation:
            raise IntegrationGateError("cannot start a second operation or resume an uncertain operation")
        owner.update(heartbeat_at=now, progress=stage,
                     operation=dict(kind=operation, started_at=now) if operation else None)
        if not self.compare_and_swap(oid, state, dict(kind="gate_progress_confirmed", owner=owner)):
            if _attempt < 3:
                # Queue registrations may race with owner progress. Retry only
                # a proven CAS rejection, never an uncertain transport result.
                return self.progress(identity, stage, operation=operation, _attempt=_attempt + 1)
            raise IntegrationGateError("gate progress CAS raced; stop before another side effect")

    def release(self, identity: Mapping, *, reason: str, receipt: Mapping, _attempt: int = 0) -> dict:
        if not isinstance(reason, str) or not reason.strip():
            raise IntegrationGateError("gate release needs a reason")
        oid, state = self.read()
        owner = self.require_owner(state, identity)
        if owner["operation"] is not None:
            raise IntegrationGateError("gate has an unfinished operation; quarantine and reconcile")
        self._require_receipt(identity, receipt)
        if receipt["status"] == "completed" and not SHA.fullmatch(str(receipt.get("verified_main", ""))):
            raise IntegrationGateError("completion requires the verified main commit")
        now = self.clock()
        queue = admissible_waiters(state)
        next_waiter = queue[0] if queue else None
        state["owner"] = None
        event = dict(kind="gate_released", owner=owner, reason=reason, receipt=dict(receipt),
                     unity_seconds=owner["unity_seconds"], ci_seconds=owner["ci_seconds"],
                     integration_seconds=max(0.0, (timestamp(now) - timestamp(owner["acquired_at"])).total_seconds()),
                     next_waiter=next_waiter["task_id"] if next_waiter else None)
        if not self.compare_and_swap(oid, state, event):
            if _attempt < 3:
                return self.release(identity, reason=reason, receipt=receipt, _attempt=_attempt + 1)
            raise IntegrationGateError("release CAS raced; no successor authorized by this call")
        # Wake intent and completion receipt are already durable atomically.
        # Datagram loss cannot grant ownership; one scheduler fallback read recovers it.
        if next_waiter:
            self.wake(dict(next_waiter, domain=self.domain))
        return dict(status="released", next_waiter=event["next_waiter"])

    @staticmethod
    def _require_receipt(identity: Mapping, receipt: Mapping) -> None:
        if (not isinstance(receipt, Mapping) or not same_owner(receipt, identity)
                or receipt.get("schema_version") != SCHEMA
                or receipt.get("status") not in {"completed", "quiescent", "recovered"}
                or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("issue_event_id", "")))):
            raise IntegrationGateError("release requires an exact owner-bound durable settlement receipt")

    def quarantine(self, identity: Mapping, reason: str, _attempt: int = 0) -> None:
        oid, state = self.read()
        owner = self.require_owner(state, identity)
        owner["status"] = "quarantined"
        if not self.compare_and_swap(oid, state, dict(kind="gate_crash_or_uncertain_operation", owner=owner, reason=reason)):
            if _attempt < 3:
                return self.quarantine(identity, reason, _attempt + 1)
            raise IntegrationGateError("quarantine CAS raced; preserve owner and inspect exact ref")

    def recover(self, *, expected_oid: str, receipt: Mapping) -> dict:
        """Explicit operator repair AFTER fencing all old processes and reconciling remote side effects.

        A receipt is an operator attestation, never a PID/age/exit-zero inference.
        No scheduler or worker calls this method automatically.
        """
        oid, state = self.read()
        owner = state["owner"]
        if oid != expected_oid or owner is None:
            raise IntegrationGateError("recovery ref/owner moved; repeat read-only investigation")
        self._require_receipt(owner, receipt)
        if (receipt["status"] != "recovered" or receipt.get("processes_fenced") is not True
                or receipt.get("remote_operations_reconciled") is not True
                or not SHA.fullmatch(str(receipt.get("verified_main", "")))
                or not str(receipt.get("operator_evidence", "")).strip()):
            raise IntegrationGateError("recovery needs explicit fencing, main/PR/Issue reconciliation and preserved evidence")
        state["owner"] = None
        queue = admissible_waiters(state)
        next_waiter = queue[0] if queue else None
        if not self.compare_and_swap(oid, state, dict(kind="gate_recovery_decision", owner=owner,
                                                     receipt=dict(receipt), next_waiter=next_waiter)):
            raise IntegrationGateError("recovery CAS raced; nothing may assume success")
        if next_waiter:
            self.wake(dict(next_waiter, domain=self.domain))
        return {"status": "recovered"}


def validate_endpoint(endpoint: Mapping) -> None:
    if (set(endpoint) != {"host", "port", "nonce"} or not isinstance(endpoint["host"], str)
            or not endpoint["host"] or type(endpoint["port"]) is not int
            or not 1 <= endpoint["port"] <= 65535 or not TOKEN.fullmatch(str(endpoint["nonce"]))):
        raise IntegrationGateError("malformed advisory gate wake endpoint")


def send_wake(waiter: Mapping) -> None:
    for endpoint in waiter["wake_endpoints"]:
        validate_endpoint(endpoint)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.settimeout(1.0)
                sender.sendto(json.dumps(dict(nonce=endpoint["nonce"], domain=waiter["domain"],
                                             task_id=waiter["task_id"])).encode(),
                              (endpoint["host"], endpoint["port"]))
        except OSError:
            # The immutable release retains the wake intent. Notification has
            # no authority and must never undo a committed release.
            continue


class GateWakeListener:
    """One event-driven wait endpoint per controller, shared by its pending set."""
    def __init__(self, event: threading.Event, domain: str, *, host: str = "127.0.0.1", on_wake=None):
        self.event, self.domain = event, domain
        self.pending = threading.Event()
        self.on_wake = on_wake
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, 0))
        self.socket.settimeout(0.2)
        self.endpoint = dict(host=host, port=self.socket.getsockname()[1], nonce=uuid.uuid4().hex)
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()

    def _listen(self) -> None:
        while not self.closed.is_set():
            try:
                raw, _ = self.socket.recvfrom(4096)
                value = json.loads(raw)
                if value.get("nonce") == self.endpoint["nonce"] and value.get("domain") == self.domain:
                    validate_task_id(value.get("task_id"))
                    self.pending.set()
                    self.event.set()
                    if self.on_wake:
                        self.on_wake(value["task_id"])
            except (OSError, ValueError, TaskReviewContractError):
                continue

    def close(self) -> None:
        self.closed.set()
        self.socket.close()
        self.thread.join(timeout=1)
