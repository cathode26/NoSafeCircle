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
from .publication_fence import (
    PUBLICATION_PROTOCOL_VERSION,
    DEFINITELY_PUBLISHED,
    REQUIRES_RECONCILIATION,
    PublicationStatus,
)

SCHEMA = "1.0"
MARKER = "nsc-durable-integration-gate"
SHA = re.compile(r"[0-9a-f]{40}\Z")
TOKEN = re.compile(r"[0-9a-f]{32}\Z")

# Owner records written before the versioned publication protocol carry neither
# the approved source head nor the exact expected target-branch commit, so they
# cannot express publication authority. They stay READABLE -- history and audit
# must survive, and operator recovery has to be able to read them -- but every
# authority operation refuses them (see require_owner).
LEGACY_OWNER_KEYS = frozenset({
    "task_id", "run_id", "worker_id", "lease_id", "repository", "target_branch",
    "acquired_at", "heartbeat_at", "progress", "status", "operation", "unity_seconds", "ci_seconds"})
OWNER_KEYS = LEGACY_OWNER_KEYS | {"protocol_version", "publication"}
PUBLICATION_KEYS = frozenset({
    "protocol_version", "repository", "target_branch", "task_id", "run_id", "worker_id",
    "lease_id", "source_head", "validated_commit", "expected_main", "operation_id",
    "base_epoch", "status", "publication_commit", "observed_pre_image", "observed_target",
    "detail"})
#: Receipt fields that bind a settlement to the exact publication operation.
RECEIPT_PUBLICATION_KEYS = (
    "publication_operation_id", "publication_status", "publication_expected_main",
    "publication_source_head", "publication_validated_commit", "publication_commit",
    "publication_observed_main", "publication_base_epoch")
_PUBLICATION_STATUSES = frozenset(item.value for item in PublicationStatus)

ABANDONED_WAITER_RETIREMENT_SCHEMA = "1.0"
ABANDONED_WAITER_RETIREMENT_AUTHORITY = (
    "host_verified_abandoned_gate_waiter_retirement"
)
ABANDONED_WAITER_RETIREMENT_PROOF_KEYS = frozenset({
    "schema_version", "authority", "repository", "target_branch", "gate_ref",
    "expected_gate_oid", "expected_gate_revision", "task_id",
    "task_contract_sha256", "retired_waiter", "issue", "task_branch",
    "candidate_head", "recorded_checkout", "canonical_checkout",
    "absent_checkout_paths", "remote_task_ref", "remote_task_branch_oid",
    "main_head", "candidate_reachable_from_main", "observed_gate_owner",
    "live_assignment",
})
ABANDONED_WAITER_RETIREMENT_ISSUE_KEYS = frozenset({
    "number", "url", "state", "classification", "body_sha256",
    "managed_snapshot", "event_ids",
})
ABANDONED_WAITER_RETIREMENT_ASSIGNMENT_KEYS = frozenset({
    "workflow_state", "worker_id", "lease_id", "claim_refs",
})


class IntegrationGateError(TaskReviewContractError):
    pass


class LegacyGateOwnerError(IntegrationGateError):
    """A pre-versioned owner record may never be treated as publication authority."""


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

    def _state_at_oid(self, oid: str) -> tuple[dict, list[str]]:
        """Read one already-fetched journal commit without consulting a ref."""
        if not SHA.fullmatch(str(oid)):
            raise IntegrationGateError("invalid integration gate history OID")
        raw = _run_git(self.repository, "show", "-s", "--format=%B", oid).stdout.decode()
        try:
            marker, payload = raw.split("\n", 1)
            state = json.loads(payload)
            if marker != MARKER:
                raise ValueError("marker")
            self.validate(state)
            parents = _run_git(
                self.repository, "show", "-s", "--format=%P", oid,
            ).stdout.decode().split()
            previous = state["event"]["previous_oid"]
            if parents != ([previous] if previous else []):
                raise ValueError("journal parent")
        except (ValueError, KeyError, TypeError) as exc:
            raise IntegrationGateError(
                f"corrupt integration gate history at {oid}"
            ) from exc
        return state, parents

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
            keys = set(owner)
            # Both shapes stay readable so durable history, audit and operator
            # recovery survive a protocol change; only AUTHORITY is versioned.
            if keys not in (set(OWNER_KEYS), set(LEGACY_OWNER_KEYS)):
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
            if keys == set(OWNER_KEYS):
                if owner["protocol_version"] != PUBLICATION_PROTOCOL_VERSION:
                    raise IntegrationGateError("unsupported gate owner protocol version; reconcile exact ref")
                self._validate_publication(owner)

    def _validate_publication(self, owner: Mapping) -> None:
        """Validate the owner-bound publication operation, or its absence.

        The record binds publication authority to the approved source head and
        the exact expected target-branch commit. It is never inferred: an absent
        record means NOT_ATTEMPTED, not "any base is acceptable".
        """
        record = owner["publication"]
        if record is None:
            return
        if not isinstance(record, dict) or set(record) != set(PUBLICATION_KEYS):
            raise IntegrationGateError("gate publication operation schema mismatch")
        if record["protocol_version"] != PUBLICATION_PROTOCOL_VERSION:
            raise IntegrationGateError("unsupported gate publication protocol version; reconcile exact ref")
        if record["repository"] != self.repository_id or record["target_branch"] != self.target_branch:
            raise IntegrationGateError("publication operation domain mismatch")
        if any(record[key] != owner[key] for key in ("task_id", "run_id", "worker_id", "lease_id")):
            raise IntegrationGateError("publication operation is not bound to this gate owner")
        for key in ("source_head", "validated_commit", "expected_main"):
            if not SHA.fullmatch(str(record[key])):
                raise IntegrationGateError("publication operation requires exact source and base identities")
        if record["validated_commit"] != record["source_head"]:
            raise IntegrationGateError(
                "publication operation names validation evidence for a commit other than the "
                "approved candidate; an untested topology may never be published")
        if not TOKEN.fullmatch(str(record["operation_id"])):
            raise IntegrationGateError("publication operation identity is malformed")
        if type(record["base_epoch"]) is not int or record["base_epoch"] < 1:
            raise IntegrationGateError("publication operation base epoch is malformed")
        if record["status"] not in _PUBLICATION_STATUSES:
            raise IntegrationGateError("publication operation status is not a known outcome")
        for key in ("publication_commit", "observed_pre_image", "observed_target"):
            value = record[key]
            if value is not None and not SHA.fullmatch(str(value)):
                raise IntegrationGateError("publication operation observation is malformed")
        if not isinstance(record["detail"], str):
            raise IntegrationGateError("publication operation detail is malformed")

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

    def append_only_compare_and_swap(self, expected: str, state: dict, event: dict) -> bool:
        """Append one exact child without any forced ref update.

        A normal fast-forward push is itself the old-tip fence: if another
        writer advances the journal from ``expected``, this child is no longer
        a fast-forward and Git rejects it. This narrower writer exists for
        operator retirement, whose contract explicitly forbids force push.
        """
        if not SHA.fullmatch(str(expected)):
            raise IntegrationGateError("append-only gate CAS requires an exact existing OID")
        value = copy.deepcopy(state)
        value["revision"] += 1
        value["event"] = {**event, "occurred_at": self.clock(), "previous_oid": expected}
        self.validate(value)
        name, email = validated_agent_git_identity()
        environment = {f"GIT_{role}_{field}": data for role in ("AUTHOR", "COMMITTER")
                       for field, data in (("NAME", name), ("EMAIL", email))}
        tree = _run_git(self.repository, "mktree", input_bytes=b"").stdout.decode().strip()
        proposed = _run_git(
            self.repository,
            "commit-tree",
            tree,
            "-p",
            expected,
            input_bytes=(MARKER + "\n" + canonical_json(value) + "\n").encode(),
            environment=environment,
        ).stdout.decode().strip()
        result = _run_git(
            self.repository,
            "push",
            "--porcelain",
            "--atomic",
            self.remote,
            f"{proposed}:{self.ref}",
            check=False,
        )
        if result.returncode == 0:
            return True
        # A failed command may still have reached the remote. Re-read instead
        # of replaying. Exact proposed identity proves success; any other moved
        # tip proves this writer lost its old-tip fence.
        observed, _ = self.read()
        if observed == proposed:
            return True
        if observed != expected:
            return False
        raise IntegrationGateError(
            f"append-only gate CAS failed without moving {self.ref}; inspect expected {expected}"
        )

    def _validate_abandoned_waiter_retirement_proof(
        self, proof: Mapping, *, expected_oid: str, state: Mapping,
    ) -> dict:
        """Validate the host proof against the exact journal pre-image."""
        if not isinstance(proof, Mapping) or set(proof) != set(ABANDONED_WAITER_RETIREMENT_PROOF_KEYS):
            raise IntegrationGateError("abandoned waiter retirement proof keys mismatch")
        task_id = validate_task_id(proof.get("task_id"))
        if (
            proof.get("schema_version") != ABANDONED_WAITER_RETIREMENT_SCHEMA
            or proof.get("authority") != ABANDONED_WAITER_RETIREMENT_AUTHORITY
            or proof.get("repository") != self.repository_id
            or proof.get("target_branch") != self.target_branch
            or proof.get("gate_ref") != self.ref
            or proof.get("expected_gate_oid") != expected_oid
            or proof.get("expected_gate_revision") != state.get("revision")
        ):
            raise IntegrationGateError("abandoned waiter retirement gate identity changed")
        if not re.fullmatch(r"[0-9a-f]{64}", str(proof.get("task_contract_sha256", ""))):
            raise IntegrationGateError("abandoned waiter retirement contract identity is invalid")
        waiter = next(
            (item for item in state["queue"] if item["task_id"] == task_id),
            None,
        )
        if waiter is None or waiter != proof.get("retired_waiter"):
            raise IntegrationGateError("exact quarantined waiter identity changed")
        quarantine = waiter.get("quarantine")
        reservation = waiter.get("reservation")
        if (
            not isinstance(quarantine, Mapping)
            or quarantine.get("reason") != "workflow_missing_or_invalid"
            or not isinstance(reservation, Mapping)
        ):
            raise IntegrationGateError("retirement requires the exact invalid-workflow quarantine")
        validate_waiter_reservation(reservation)
        issue = proof.get("issue")
        if not isinstance(issue, Mapping) or set(issue) != set(ABANDONED_WAITER_RETIREMENT_ISSUE_KEYS):
            raise IntegrationGateError("abandoned waiter Issue proof keys mismatch")
        observed_numbers = quarantine.get("observed_issue_numbers")
        if (
            issue.get("number") != reservation["issue_number"]
            or observed_numbers != [reservation["issue_number"]]
            or issue.get("state") != "CLOSED"
            or issue.get("classification") != "closed_incomplete_invalid_not_complete"
            or not isinstance(issue.get("url"), str)
            or not issue["url"].strip()
            or not re.fullmatch(r"[0-9a-f]{64}", str(issue.get("body_sha256", "")))
        ):
            raise IntegrationGateError("abandoned waiter Issue identity/classification changed")
        snapshot = issue.get("managed_snapshot")
        if not isinstance(snapshot, Mapping):
            raise IntegrationGateError("abandoned waiter managed snapshot is missing")
        workflow = snapshot.get("workflow_state")
        event_ids = issue.get("event_ids")
        if (
            snapshot.get("issue_number") != issue["number"]
            or snapshot.get("issue_url") != issue["url"]
            or snapshot.get("managed") is not True
            or snapshot.get("valid") is not True
            or snapshot.get("reasons") != []
            or snapshot.get("pending_transition") is not None
            or not isinstance(workflow, Mapping)
            or workflow.get("task_id") != task_id
            or workflow.get("task_contract_sha256") != proof["task_contract_sha256"]
            or workflow.get("state") != "agent_ready"
            or workflow.get("phase") not in {"delivery_evidence", "merge_closeout"}
            or workflow.get("worker_id") is not None
            or workflow.get("lease_id") is not None
            or not isinstance(event_ids, list)
            or any(not re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in event_ids)
            or len(set(event_ids)) != len(event_ids)
            or len(event_ids) != snapshot.get("event_count")
            or (event_ids[-1] if event_ids else None) != snapshot.get("last_event_id")
        ):
            raise IntegrationGateError("abandoned waiter managed snapshot is not exact closed incomplete authority")
        if reservation["task_contract_sha256"] != proof["task_contract_sha256"]:
            raise IntegrationGateError("abandoned waiter reservation contract changed")
        task_branch = proof.get("task_branch")
        candidate = proof.get("candidate_head")
        recorded_checkout = proof.get("recorded_checkout")
        canonical_checkout = proof.get("canonical_checkout")
        absent_paths = proof.get("absent_checkout_paths")
        if (
            not isinstance(task_branch, str)
            or not task_branch
            or workflow.get("branch") != task_branch
            or proof.get("remote_task_ref") != f"refs/heads/{task_branch}"
            or proof.get("remote_task_branch_oid") is not None
            or not SHA.fullmatch(str(candidate))
            or workflow.get("head_commit") != candidate
            or workflow.get("human_handoff_commit") != candidate
            or workflow.get("checkout_path") != recorded_checkout
            or not isinstance(recorded_checkout, str)
            or not recorded_checkout
            or not isinstance(canonical_checkout, str)
            or not canonical_checkout
            or not isinstance(absent_paths, list)
            or absent_paths != sorted(set((recorded_checkout, canonical_checkout)), key=str.casefold)
            or proof.get("candidate_reachable_from_main") is not False
            or not SHA.fullmatch(str(proof.get("main_head", "")))
        ):
            raise IntegrationGateError("abandoned waiter branch/head/checkout proof changed")
        owner = proof.get("observed_gate_owner")
        if owner != state.get("owner") or (
            isinstance(owner, Mapping) and owner.get("task_id") == task_id
        ):
            raise IntegrationGateError("abandoned waiter still has gate ownership")
        assignment = proof.get("live_assignment")
        if (
            not isinstance(assignment, Mapping)
            or set(assignment) != set(ABANDONED_WAITER_RETIREMENT_ASSIGNMENT_KEYS)
            or assignment.get("workflow_state") != "agent_ready"
            or assignment.get("worker_id") is not None
            or assignment.get("lease_id") is not None
            or assignment.get("claim_refs") != []
        ):
            raise IntegrationGateError("abandoned waiter still has a live assignment or lease")
        return copy.deepcopy(dict(proof))

    def abandoned_waiter_retirement(
        self, *, expected_oid: str, task_id: str, proof: Mapping | None = None,
    ) -> dict | None:
        """Find one exact prior retirement anchored directly to expected_oid."""
        task_id = validate_task_id(task_id)
        if not SHA.fullmatch(str(expected_oid)):
            raise IntegrationGateError("retirement lookup requires an exact gate OID")
        current_oid, _ = self.read()
        cursor = current_oid
        visited: set[str] = set()
        while cursor and cursor != expected_oid:
            if cursor in visited:
                raise IntegrationGateError("integration gate history contains a cycle")
            visited.add(cursor)
            state, parents = self._state_at_oid(cursor)
            event = state["event"]
            if (
                event.get("kind") == "gate_abandoned_waiter_retired"
                and event.get("task_id") == task_id
                and event.get("previous_oid") == expected_oid
            ):
                recorded = event.get("proof")
                if not isinstance(recorded, Mapping):
                    raise IntegrationGateError("recorded abandoned waiter proof is malformed")
                if proof is not None and canonical_json(recorded) != canonical_json(dict(proof)):
                    raise IntegrationGateError("recorded abandoned waiter proof differs from retry")
                return copy.deepcopy(dict(recorded))
            cursor = parents[0] if parents else ""
        if cursor != expected_oid:
            raise IntegrationGateError("expected retirement OID is not in current gate history")
        return None

    def retire_abandoned_waiter(self, *, expected_oid: str, proof: Mapping) -> dict:
        """Retire one host-proven abandoned quarantine; never infer completion."""
        task_id = validate_task_id(proof.get("task_id") if isinstance(proof, Mapping) else None)
        existing = self.abandoned_waiter_retirement(
            expected_oid=expected_oid,
            task_id=task_id,
            proof=proof,
        )
        if existing is not None:
            return {"status": "already_retired", "task_id": task_id, "proof": existing}
        oid, state = self.read()
        if oid != expected_oid:
            raise IntegrationGateError("abandoned waiter retirement gate OID moved; re-observe")
        exact_proof = self._validate_abandoned_waiter_retirement_proof(
            proof, expected_oid=expected_oid, state=state,
        )
        state["queue"] = [
            waiter for waiter in state["queue"] if waiter["task_id"] != task_id
        ]
        queue = admissible_waiters(state) if state["owner"] is None else []
        next_waiter = queue[0] if queue else None
        if not self.append_only_compare_and_swap(
            expected_oid,
            state,
            {
                "kind": "gate_abandoned_waiter_retired",
                "task_id": task_id,
                "proof": exact_proof,
                "next_waiter": next_waiter["task_id"] if next_waiter else None,
            },
        ):
            raise IntegrationGateError(
                "abandoned waiter retirement CAS raced; queue remains authoritative"
            )
        # The append-only event makes wake intent durable first. A notification
        # failure grants nothing, and a normal scheduler read remains fallback.
        if next_waiter:
            self.wake(dict(next_waiter, domain=self.domain))
        return {
            "status": "retired",
            "task_id": task_id,
            "next_waiter": next_waiter["task_id"] if next_waiter else None,
            "proof": exact_proof,
        }

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
        selected_index = next(
            (index for index, waiter in enumerate(queue) if waiter["task_id"] == identity["task_id"]),
            None,
        )
        if selected_index is None:
            return {"status": "deferred", "reason": "task is not an admissible durable waiter"}
        selected = queue[selected_index]
        now = self.clock()
        wait_seconds = max(0.0, (timestamp(now) - timestamp(selected["ready_at"])).total_seconds())
        owner = dict(identity, repository=self.repository_id, target_branch=self.target_branch,
                     acquired_at=now, heartbeat_at=now, progress="acquired", status="held",
                     operation=None, unity_seconds=0.0, ci_seconds=0.0,
                     protocol_version=PUBLICATION_PROTOCOL_VERSION, publication=None)
        state["owner"] = owner
        state["queue"] = [
            waiter for waiter in state["queue"]
            if waiter["task_id"] != identity["task_id"]
        ]
        if not self.compare_and_swap(
            oid,
            state,
            dict(
                kind="gate_acquired",
                owner=owner,
                wait_seconds=wait_seconds,
                prior_queue_position=selected_index + 1,
                bypassed_waiter_count=selected_index,
            ),
        ):
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

    def require_owner(self, state: Mapping, identity: Mapping, *,
                      source_head: str | None = None, expected_main: str | None = None) -> dict:
        """The one place gate authority and publication identities are validated.

        Acquisition, same-owner resume, renewal, publication, completion and
        release all reach the gate through this check, so a same task/run/worker
        presenting a different approved source head or a different expected base
        never inherits the previous authority.
        """
        owner = state["owner"]
        if not same_owner(owner, identity) or owner["status"] != "held":
            raise IntegrationGateError(f"exact gate owner unavailable; inspect {self.ref}; never steal by age")
        if set(owner) == set(LEGACY_OWNER_KEYS):
            raise LegacyGateOwnerError(
                f"gate owner at {self.ref} predates the versioned publication protocol and carries no "
                "source/base identity; reconcile it explicitly through gate recovery rather than "
                "reinterpreting it as authorized publication authority")
        self.require_publication_identity(owner, source_head=source_head, expected_main=expected_main)
        return owner

    @staticmethod
    def require_publication_identity(owner: Mapping, *, source_head: str | None = None,
                                     expected_main: str | None = None) -> Mapping | None:
        record = owner["publication"]
        if source_head is None and expected_main is None:
            return record
        if record is None:
            raise IntegrationGateError(
                "no owner-bound publication operation exists for this source head and base; "
                "bind publication authority before asserting it")
        if ((source_head is not None and record["source_head"] != source_head)
                or (expected_main is not None and record["expected_main"] != expected_main)):
            raise IntegrationGateError(
                "publication authority is bound to a different approved source head or expected base; "
                "reintegrate current main and bind a new owner-bound operation")
        return record

    def bind_publication(self, identity: Mapping, *, source_head: str, validated_commit: str,
                         expected_main: str, operation_id: str | None = None,
                         _attempt: int = 0) -> dict:
        """Persist the exact candidate, validation and base identities BEFORE any mutation.

        Rebinding after a legitimate reintegration produces a NEW operation with
        a higher base epoch, recorded as its own append-only transition. Nothing
        is edited in place and no prior record is discarded.

        A rejected operation is never re-leased against a freshly observed base:
        rebinding requires a different approved candidate, which only
        reintegration, revalidation and renewed approval can produce.
        """
        for label, value in (("source head", source_head), ("validated commit", validated_commit),
                             ("expected main", expected_main)):
            if not SHA.fullmatch(str(value)):
                raise IntegrationGateError(f"publication binding requires an exact {label} commit OID")
        if validated_commit != source_head:
            raise IntegrationGateError(
                "publication binding requires validation evidence for the exact approved candidate")
        oid, state = self.read()
        owner = self.require_owner(state, identity)
        existing = owner["publication"]
        if existing is not None:
            if (existing["source_head"] == source_head
                    and existing["expected_main"] == expected_main
                    and existing["validated_commit"] == validated_commit):
                # Resuming THIS operation, not starting another. An unreconciled
                # status is resolved by inspecting the remote outcome, which the
                # caller does next; it is never resolved by a second mutation.
                return dict(existing)
            if PublicationStatus(existing["status"]) in REQUIRES_RECONCILIATION:
                raise IntegrationGateError(
                    f"publication operation {existing['operation_id']} is unreconciled "
                    f"({existing['status']}); reconcile the remote outcome before binding another")
            if PublicationStatus(existing["status"]) in DEFINITELY_PUBLISHED:
                raise IntegrationGateError(
                    "this owner already published against a different base; reconcile before rebinding")
            if existing["source_head"] == source_head:
                raise IntegrationGateError(
                    f"publication operation {existing['operation_id']} was refused for candidate "
                    f"{source_head}; that same candidate may not be re-leased against a newly "
                    "observed base. Reintegrate current main, rerun the required validation and "
                    "obtain renewed approval, then bind the new candidate.")
            epoch = existing["base_epoch"] + 1
        else:
            epoch = 1
        record = dict(protocol_version=PUBLICATION_PROTOCOL_VERSION, repository=self.repository_id,
                      target_branch=self.target_branch,
                      **{key: owner[key] for key in ("task_id", "run_id", "worker_id", "lease_id")},
                      source_head=source_head, validated_commit=validated_commit,
                      expected_main=expected_main,
                      operation_id=operation_id or uuid.uuid4().hex, base_epoch=epoch,
                      status=PublicationStatus.PREPARED.value, publication_commit=None,
                      observed_pre_image=None, observed_target=None, detail="")
        owner["publication"], owner["heartbeat_at"] = record, self.clock()
        if not self.compare_and_swap(oid, state, dict(kind="gate_publication_bound", owner=owner,
                                                      publication=record, previous=existing)):
            if _attempt < 3:
                return self.bind_publication(identity, source_head=source_head,
                                             validated_commit=validated_commit,
                                             expected_main=expected_main,
                                             operation_id=record["operation_id"], _attempt=_attempt + 1)
            raise IntegrationGateError("publication binding CAS raced; stop before any mutation")
        return record

    def record_publication(self, identity: Mapping, *, operation_id: str, status: str,
                           publication_commit: str | None = None, observed_pre_image: str | None = None,
                           observed_target: str | None = None, detail: str = "",
                           _attempt: int = 0) -> dict:
        """Record one publication transition. Only the exact operation may settle itself."""
        oid, state = self.read()
        owner = self.require_owner(state, identity)
        record = owner["publication"]
        if record is None or record["operation_id"] != operation_id:
            raise IntegrationGateError(
                "no matching owner-bound publication operation; a stale or foreign operation "
                "may never record a publication outcome")
        if status not in _PUBLICATION_STATUSES:
            raise IntegrationGateError("publication operation status is not a known outcome")
        if (PublicationStatus(record["status"]) in DEFINITELY_PUBLISHED
                and PublicationStatus(status) not in DEFINITELY_PUBLISHED):
            raise IntegrationGateError("a settled publication may not be downgraded; reconcile instead")
        updated = dict(record, status=status, detail=str(detail)[:2000])
        for key, value in (("publication_commit", publication_commit),
                           ("observed_pre_image", observed_pre_image),
                           ("observed_target", observed_target)):
            if value is not None:
                updated[key] = value
        owner["publication"], owner["heartbeat_at"] = updated, self.clock()
        if not self.compare_and_swap(oid, state, dict(kind="gate_publication_recorded", owner=owner,
                                                      publication=updated)):
            if _attempt < 3:
                return self.record_publication(identity, operation_id=operation_id, status=status,
                                               publication_commit=publication_commit,
                                               observed_pre_image=observed_pre_image,
                                               observed_target=observed_target, detail=detail,
                                               _attempt=_attempt + 1)
            raise IntegrationGateError("publication outcome CAS raced; the outcome is recorded nowhere durable")
        return updated

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
        publication = owner["publication"]
        if publication is not None and PublicationStatus(publication["status"]) in REQUIRES_RECONCILIATION:
            raise IntegrationGateError(
                f"publication operation {publication['operation_id']} is {publication['status']}; "
                "quarantine and reconcile the remote outcome instead of releasing the gate")
        self._require_receipt(identity, receipt, publication=publication)
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
    def _require_receipt(identity: Mapping, receipt: Mapping, *, publication: Mapping | None = None) -> None:
        if (not isinstance(receipt, Mapping) or not same_owner(receipt, identity)
                or receipt.get("schema_version") != SCHEMA
                or receipt.get("status") not in {"completed", "quiescent", "recovered"}
                or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("issue_event_id", "")))):
            raise IntegrationGateError("release requires an exact owner-bound durable settlement receipt")
        GitIntegrationGate._require_publication_receipt(receipt, publication)

    @staticmethod
    def _require_publication_receipt(receipt: Mapping, publication: Mapping | None) -> None:
        """A settlement after a real mutation must name every identity it used.

        The receipt binds the original expected base, the approved source head,
        the exact published commit, the observed final target and the prior
        operation/lease identity, so a later reader never has to re-derive them
        from mutable state.
        """
        if publication is None or PublicationStatus(publication["status"]) not in DEFINITELY_PUBLISHED:
            if any(key in receipt for key in RECEIPT_PUBLICATION_KEYS):
                raise IntegrationGateError(
                    "settlement claims a publication this owner never performed; reconcile the exact ref")
            return
        missing = [key for key in RECEIPT_PUBLICATION_KEYS if key not in receipt]
        if missing:
            raise IntegrationGateError(
                "settlement after publication must bind " + ", ".join(sorted(missing)))
        expected = {
            "publication_operation_id": publication["operation_id"],
            "publication_status": publication["status"],
            "publication_expected_main": publication["expected_main"],
            "publication_source_head": publication["source_head"],
            "publication_validated_commit": publication["validated_commit"],
            "publication_commit": publication["publication_commit"],
            "publication_base_epoch": publication["base_epoch"],
        }
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise IntegrationGateError(
                "settlement identities do not match this owner's durable publication operation")
        if not SHA.fullmatch(str(receipt.get("publication_observed_main", ""))):
            raise IntegrationGateError("settlement after publication requires the observed final target commit")
        if receipt.get("status") == "completed" and receipt.get("verified_main") != publication["publication_commit"]:
            raise IntegrationGateError("completion must verify the exact published commit")

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
        # Legacy owners are readable here on purpose: explicit operator recovery
        # is the reconciliation path a pre-versioned record must be able to take.
        publication = owner.get("publication")
        self._require_receipt(owner, receipt, publication=publication)
        if (receipt["status"] != "recovered" or receipt.get("processes_fenced") is not True
                or receipt.get("remote_operations_reconciled") is not True
                or not SHA.fullmatch(str(receipt.get("verified_main", "")))
                or not str(receipt.get("operator_evidence", "")).strip()):
            raise IntegrationGateError("recovery needs explicit fencing, main/PR/Issue reconciliation and preserved evidence")
        if publication is not None and receipt.get("publication_operation_id") != publication["operation_id"]:
            raise IntegrationGateError(
                "recovery receipt must name the exact prior publication operation it reconciled")
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
