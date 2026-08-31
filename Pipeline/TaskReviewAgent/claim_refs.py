"""Short-lived atomic Git-ref claims for explicit task/lease initialization.

Two workers may race for the same task, or for two tasks sharing an exclusive
resource, in the narrow window before the durable GitHub Issue lease becomes
authoritative. This module closes that window with ephemeral claim refs:

    refs/nsc/claims/tasks/<TASK-ID>
    refs/nsc/claims/resources/<canonical-resource-sha256>

Lifecycle (see ``acquire_issue_lease_with_claims``):

    atomically create task ref + every exclusive-resource ref (one push,
    nonexistence CAS) -> acquire/initialize the GitHub Issue lease while the
    claims are held -> re-read and verify exact Issue authority -> delete the
    claim refs with exact claim-SHA fencing.

The Git-ref claim is never long-lived workflow authority; the GitHub Issue
lease remains the durable controller. Losing a claim race is a NORMAL
scheduling outcome and is returned as a typed ``claim_conflict`` result.

Race contract for one atomic acquisition attempt: AT MOST one worker may win
a set of conflicting claims — never two. Zero winners is also a legal
outcome: two overlapping atomic pushes can abort each other's ref
transaction, which is returned as a typed transient ``claim_conflict``
(``kind="transient_transaction_contention"``) so the scheduler can recompute
and retry later. Only a PROVEN nonexistence/exact-value race (``stale info``
or a remote ``cannot lock ref``/existence rejection for one of this push's
claim refs) counts as ordinary contention; policy/hook rejections,
authentication, permission, transport, and other remote failures stay
operational errors (``ClaimRefsError``).

Crash policy: there is no TTL and no automatic stale-claim garbage
collection. A claim left behind by a crashed process stays visible through
``inspect_claims`` (exact ref, claim OID, receipt, timestamps) and is repaired
manually with exact-SHA fencing only. An active process may release its own
still-exact claims after a normal initialization failure.

The claim target is a parentless empty-tree commit created with plumbing
(``git mktree``/``git commit-tree``), so the current branch, working tree,
and index are never touched. GitHub support for the custom ``refs/nsc``
namespace is unproven; the namespace is an explicit constructor argument and
``probe_remote_claim_namespace`` exists for a deliberate capability smoke test
against a disposable remote.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .claim_policy import (
    ClaimPolicy,
    activated_claim_namespace,
    load_claim_policy,
    validate_claim_namespace,
)
from .contracts import (
    GIT_SHA_RE,
    TaskReviewContractError,
    canonical_json,
    validate_task_id,
)
from .git_identity_guard import validated_agent_git_identity
from .issue_workflow import (
    IssueWorkflowState,
    WorkflowContractError,
    WorkflowState,
    utc_now,
)
from .issue_workflow_store import (
    IssueWorkflowStoreError,
    verify_post_mutation_state,
)
from .real_checkout import CANONICAL_REMOTE, _normalized_remote

CLAIM_RECEIPT_SCHEMA_VERSION = "1.0"
CLAIM_MESSAGE_MARKER = "no-safe-circle-ephemeral-claim"
MAX_CLAIM_RESOURCES = 100
MAX_RESOURCE_TOKEN_LENGTH = 512

# Porcelain rejection reasons that only mean "a sibling ref in the same
# atomic push failed"; they carry no proof of their own and are legal only
# alongside a proven contention/transient line. Real GitHub reports a raced
# sibling ref's own porcelain reason as the bare word "failed" (not one of
# the longer "atomic ... failed" phrasings below), while the ref that
# actually lost the race carries the exact nonexistence-CAS proof inline in
# ITS OWN reason text (see `_ref_proves_contention`/`_classify_failed_claim_push`).
_NEUTRAL_REJECTION_REASONS = frozenset(
    {"atomic push failed", "atomic transaction failed", "failed"}
)
# Client-side --force-with-lease CAS failure against the ref advertisement.
_STALE_INFO_REASON = "stale info"
# Server-side per-ref update failure; ambiguous on its own, so stderr must
# prove which kind of failure it was before it may count as contention.
_SERVER_UPDATE_REASON = "failed to update ref"


class ClaimRefsError(TaskReviewContractError):
    """Raised when the claim primitive fails operationally (not a lost race)."""


def _run_git(
    repository: Path,
    *args: str,
    input_bytes: bytes | None = None,
    check: bool = True,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    merged = os.environ.copy()
    if environment:
        merged.update(environment)
    try:
        result = subprocess.run(
            ("git", "-C", str(repository), *args),
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged,
            check=False,
            timeout=300.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ClaimRefsError(f"git could not be executed safely: git {' '.join(args)}") from exc
    if check and result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise ClaimRefsError(
            f"git command failed ({result.returncode}): git {' '.join(args)}"
            + (f"\n{stderr}" if stderr else "")
        )
    return result


def _parse_porcelain_rejections(stdout_text: str) -> list[tuple[str, str, str]]:
    """(destination ref, summary, parenthesized reason) per rejected ref line.

    ``git push --porcelain`` reports one machine-readable line per refspec on
    stdout; rejected refs start with ``!`` and carry the reason in trailing
    parentheses, e.g. ``[rejected] (stale info)``.
    """

    rejected: list[tuple[str, str, str]] = []
    for line in stdout_text.splitlines():
        if not line.startswith("!"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        refspec, summary = parts[1], parts[2].strip()
        destination = refspec.split(":", 1)[1] if ":" in refspec else refspec
        reason = ""
        if summary.endswith(")") and "(" in summary:
            reason = summary[summary.rindex("(") + 1 : -1].strip()
        rejected.append((destination, summary, reason))
    return rejected


def _contention_proof_pattern(ref: str) -> re.Pattern[str]:
    """Exact nonexistence/exact-value CAS proof text for one exact ref.

    This is the proof GitHub embeds directly in a rejected ref's OWN
    porcelain reason, e.g. ``[remote rejected] (cannot lock ref '<ref>':
    reference already exists)``; the same text can also appear only in free
    combined stderr, which is why callers check both.
    """

    escaped = re.escape(ref)
    return re.compile(
        rf"cannot lock ref '{escaped}': reference already exists"
        rf"|cannot lock ref '{escaped}': is at [0-9a-f]{{40}} but expected"
    )


def _transient_lock_proof_pattern(ref: str) -> re.Pattern[str]:
    """Exact ref-transaction-lock-contention proof text for one exact ref."""

    escaped = re.escape(ref)
    return re.compile(
        rf"cannot lock ref '{escaped}': Unable to create '[^']*\.lock': File exists"
    )


def _existence_race_proofs(
    refs: Sequence[str],
    stderr_text: str,
) -> tuple[set[str], set[str]]:
    """Refs whose combined stderr text proves a race: (contention, transient).

    Contention is proven only by the remote refusing this exact CAS:
    the ref already exists where nonexistence was asserted, or it holds a
    different exact value than expected. A ref-transaction lock file held by
    a concurrent push is a transient race, not held state. Every other
    ``cannot lock ref`` flavor (permissions, corrupt lock, disk) stays
    unproven and therefore operational.
    """

    contention: set[str] = set()
    transient: set[str] = set()
    for ref in refs:
        if _contention_proof_pattern(ref).search(stderr_text):
            contention.add(ref)
        elif _transient_lock_proof_pattern(ref).search(stderr_text):
            transient.add(ref)
    return contention, transient


def _classify_failed_claim_push(
    refs: Sequence[str],
    result: subprocess.CompletedProcess[bytes],
) -> tuple[str, list[str]]:
    """Classify a failed claim push: 'contention', 'transient', or 'operational'.

    Ordinary claim contention requires per-ref proof of a nonexistence/lease
    race; broad markers alone never qualify. Policy rejection, pre-receive
    hook rejection, unsupported namespace/atomic push, authentication,
    permission, ruleset, and transport failures all stay operational.

    Real GitHub places the exact nonexistence-CAS proof inline in the raced
    ref's OWN porcelain reason, e.g. ``[remote rejected] (cannot lock ref
    '<exact ref>': reference already exists)``, while an aborted sibling ref
    in the same ``--atomic`` transaction reports only the bare, unproven
    reason ``failed``. Each per-ref reason is therefore checked directly for
    that ref's own proof text (in addition to the combined stderr search),
    so this exact shape is recognized without ever treating a bare
    ``failed``/``[remote rejected]``/``cannot lock ref`` marker as contention
    on its own.
    """

    stdout_text = (result.stdout or b"").decode("utf-8", errors="replace")
    stderr_text = (result.stderr or b"").decode("utf-8", errors="replace")
    rejected = [
        entry
        for entry in _parse_porcelain_rejections(stdout_text)
        if entry[0] in set(refs)
    ]
    contention_refs, transient_refs = _existence_race_proofs(refs, stderr_text)
    details = [f"{summary} for {ref}" for ref, summary, _ in rejected]
    if stderr_text.strip():
        details.append(stderr_text.strip())
    if not rejected:
        return "operational", details
    kinds: list[str] = []
    for ref, _, reason in rejected:
        if reason == _STALE_INFO_REASON:
            kinds.append("contention")
        elif ref in contention_refs or _contention_proof_pattern(ref).search(reason):
            kinds.append("contention")
        elif ref in transient_refs or _transient_lock_proof_pattern(ref).search(reason):
            kinds.append("transient")
        elif reason in _NEUTRAL_REJECTION_REASONS:
            kinds.append("neutral")
        elif reason == _SERVER_UPDATE_REASON:
            if contention_refs:
                # A sibling ref in this atomic push carries the proof; this
                # ref only failed because the transaction was aborted.
                kinds.append("neutral")
            elif transient_refs:
                kinds.append("transient")
            else:
                kinds.append("operational")
        else:
            kinds.append("operational")
    if "operational" in kinds:
        return "operational", details
    if "contention" in kinds or contention_refs:
        # A server-side atomic race can report EVERY ref as the neutral
        # "atomic transaction failed" while the existence proof for the
        # raced ref appears only in stderr; the stderr proof still names one
        # of this push's exact refs, so the race is proven.
        return "contention", details
    if "transient" in kinds or transient_refs:
        return "transient", details
    # Only neutral sibling-abort lines and no per-ref proof: nothing
    # demonstrated an actual race, so this stays operational.
    return "operational", details


def canonical_resource_hash(resource: str) -> str:
    """Deterministic hash of one canonical exclusive-resource token.

    Resource text is arbitrary (`unity-scene:Assets/...`); it never appears in
    a ref name directly. The exact UTF-8 token is hashed, so equal tokens from
    different tasks always collide on the same claim ref.
    """

    if type(resource) is not str or not resource.strip():
        raise ClaimRefsError("exclusive resource token must be a non-empty string")
    if len(resource) > MAX_RESOURCE_TOKEN_LENGTH:
        raise ClaimRefsError("exclusive resource token exceeds the bounded receipt size")
    return hashlib.sha256(resource.encode("utf-8")).hexdigest()


def task_claim_ref(namespace: str, task_id: str) -> str:
    return f"{validate_claim_namespace(namespace)}/tasks/{validate_task_id(task_id)}"


def resource_claim_ref(namespace: str, resource: str) -> str:
    return f"{validate_claim_namespace(namespace)}/resources/{canonical_resource_hash(resource)}"


@dataclass(frozen=True)
class ClaimReceipt:
    """Bounded, inspectable payload stored in the claim commit message."""

    schema_version: str
    claim_worker_id: str
    task_id: str
    exclusive_resources: tuple[str, ...]
    resource_hashes: tuple[str, ...]
    source_head: str
    created_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "claim_worker_id": self.claim_worker_id,
            "task_id": self.task_id,
            "exclusive_resources": list(self.exclusive_resources),
            "resource_hashes": list(self.resource_hashes),
            "source_head": self.source_head,
            "created_at_utc": self.created_at_utc,
        }


def _parse_receipt(message_body: str) -> ClaimReceipt | None:
    """Parse and identity-validate a claim receipt; None when it cannot be trusted.

    Stale-claim inspection and repair decisions read this receipt, so it is
    validated field by field rather than coerced: the task ID, source head,
    and per-resource hashes must all be internally consistent, otherwise the
    claim is reported as carrying no parseable receipt.
    """

    lines = message_body.strip().splitlines()
    if not lines or lines[0].strip() != CLAIM_MESSAGE_MARKER:
        return None
    try:
        raw = json.loads("\n".join(lines[1:]))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict) or raw.get("schema_version") != CLAIM_RECEIPT_SCHEMA_VERSION:
        return None
    try:
        claim_worker_id = raw["claim_worker_id"]
        task_id = raw["task_id"]
        exclusive_resources = raw["exclusive_resources"]
        resource_hashes = raw["resource_hashes"]
        source_head = raw["source_head"]
        created_at_utc = raw["created_at_utc"]
    except KeyError:
        return None
    if type(claim_worker_id) is not str or not claim_worker_id.strip():
        return None
    if type(source_head) is not str or not GIT_SHA_RE.fullmatch(source_head):
        return None
    if type(created_at_utc) is not str or not created_at_utc.strip():
        return None
    if not isinstance(exclusive_resources, list) or not isinstance(resource_hashes, list):
        return None
    if any(type(item) is not str or not item.strip() for item in exclusive_resources):
        return None
    try:
        validate_task_id(task_id)
        expected_hashes = [canonical_resource_hash(item) for item in exclusive_resources]
    except TaskReviewContractError:
        return None
    if resource_hashes != expected_hashes:
        return None
    return ClaimReceipt(
        schema_version=str(raw["schema_version"]),
        claim_worker_id=claim_worker_id,
        task_id=task_id,
        exclusive_resources=tuple(exclusive_resources),
        resource_hashes=tuple(resource_hashes),
        source_head=source_head,
        created_at_utc=created_at_utc,
    )


@dataclass(frozen=True)
class ClaimAcquisition:
    """A successful atomic claim of one task ref plus its resource refs."""

    claim_oid: str
    refs: tuple[str, ...]
    receipt: ClaimReceipt
    namespace: str
    remote: str
    status: str = "acquired"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "claim_oid": self.claim_oid,
            "refs": list(self.refs),
            "receipt": self.receipt.to_dict(),
            "namespace": self.namespace,
            "remote": self.remote,
        }


@dataclass(frozen=True)
class ClaimConflict:
    """A lost claim race: a normal scheduling result, not an error.

    ``kind`` distinguishes the two legal race outcomes: ``held_by_other``
    (a conflicting claim ref provably exists) and
    ``transient_transaction_contention`` (two overlapping atomic pushes
    aborted each other, so this attempt had zero winners and may be retried
    by the scheduler). Neither kind proves this worker may proceed.
    """

    refs: tuple[str, ...]
    reasons: tuple[str, ...]
    kind: str = "held_by_other"
    status: str = "claim_conflict"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "kind": self.kind,
            "refs": list(self.refs),
            "reasons": list(self.reasons),
        }


class GitRefClaimClient:
    """Atomic create/release/inspect of ephemeral claim refs on one remote.

    ``claim_worker_id`` is the arbitration identity recorded in receipts. It
    must be unique per process/run, never a machine-stable ID, so a crashed
    run's stale claim can never be mistaken for (or released by) a later run
    on the same machine.
    """

    def __init__(
        self,
        *,
        local_repository: Path | str,
        remote: str,
        namespace: str,
        worker_id: str,
        claim_worker_id: str | None = None,
    ) -> None:
        self.local_repository = Path(local_repository)
        self.remote = str(remote).strip()
        self.namespace = validate_claim_namespace(namespace)
        self.worker_id = str(worker_id).strip()
        if not self.remote:
            raise ClaimRefsError("claim remote must be non-empty")
        if not self.worker_id:
            raise ClaimRefsError("worker_id must be non-empty")
        if claim_worker_id is not None and not str(claim_worker_id).strip():
            raise ClaimRefsError("claim_worker_id must be non-empty when provided")
        self.claim_worker_id = (
            str(claim_worker_id).strip()
            if claim_worker_id is not None
            else f"{self.worker_id}.{uuid.uuid4().hex}"
        )

    def _claim_refs(self, task_id: str, exclusive_resources: Sequence[str]) -> tuple[str, ...]:
        refs = [task_claim_ref(self.namespace, task_id)]
        refs.extend(
            sorted(
                {resource_claim_ref(self.namespace, item) for item in exclusive_resources}
            )
        )
        return tuple(refs)

    def _create_claim_commit(self, receipt: ClaimReceipt) -> str:
        # Pure plumbing: mktree from empty stdin plus commit-tree never touch
        # HEAD, the index, or the working tree of the local repository.
        name, email = validated_agent_git_identity()
        identity_environment = {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        }
        tree = (
            _run_git(self.local_repository, "mktree", input_bytes=b"")
            .stdout.decode("utf-8")
            .strip()
        )
        message = f"{CLAIM_MESSAGE_MARKER}\n\n{canonical_json(receipt.to_dict())}\n"
        commit = (
            _run_git(
                self.local_repository,
                "commit-tree",
                tree,
                input_bytes=message.encode("utf-8"),
                environment=identity_environment,
            )
            .stdout.decode("utf-8")
            .strip()
        )
        if not GIT_SHA_RE.fullmatch(commit):
            raise ClaimRefsError(f"claim commit OID is invalid: {commit!r}")
        return commit

    def acquire(
        self,
        *,
        task_id: str,
        exclusive_resources: Iterable[str],
        source_head: str,
        now: str | None = None,
    ) -> ClaimAcquisition | ClaimConflict:
        """Atomically create the task ref and every resource ref, or none.

        One ``git push --atomic`` carries every create refspec together with a
        ``--force-with-lease=<ref>:`` nonexistence CAS per ref. Any existing
        ref fails the whole push; the loser gets ``ClaimConflict`` and the
        remote is left without any of this worker's refs.
        """

        task_id = validate_task_id(task_id)
        if type(source_head) is not str or not GIT_SHA_RE.fullmatch(source_head):
            raise ClaimRefsError("source_head must be one exact 40-hex commit SHA")
        # Fail closed on malformed resource values instead of stringifying
        # arbitrary objects into claim receipts and ref hashes.
        resource_items = list(exclusive_resources)
        for item in resource_items:
            if type(item) is not str:
                raise ClaimRefsError(
                    "exclusive resource tokens must be strings; got "
                    f"{type(item).__name__}"
                )
        resources = sorted(set(resource_items))
        if len(resources) > MAX_CLAIM_RESOURCES:
            raise ClaimRefsError("claim exceeds the bounded exclusive-resource count")
        receipt = ClaimReceipt(
            schema_version=CLAIM_RECEIPT_SCHEMA_VERSION,
            claim_worker_id=self.claim_worker_id,
            task_id=task_id,
            exclusive_resources=tuple(resources),
            resource_hashes=tuple(canonical_resource_hash(item) for item in resources),
            source_head=source_head,
            created_at_utc=now or utc_now(),
        )
        refs = self._claim_refs(task_id, resources)
        claim_oid = self._create_claim_commit(receipt)
        push_args = (
            "push",
            "--atomic",
            "--porcelain",
            *(f"--force-with-lease={ref}:" for ref in refs),
            self.remote,
            *(f"{claim_oid}:{ref}" for ref in refs),
        )
        result = _run_git(self.local_repository, *push_args, check=False)
        if result.returncode == 0:
            return ClaimAcquisition(
                claim_oid=claim_oid,
                refs=refs,
                receipt=receipt,
                namespace=self.namespace,
                remote=self.remote,
            )
        classification, details = _classify_failed_claim_push(refs, result)
        if classification == "contention":
            return ClaimConflict(
                refs=refs,
                reasons=(
                    "another worker already holds one or more of these claim refs",
                    *details,
                ),
                kind="held_by_other",
            )
        if classification == "transient":
            return ClaimConflict(
                refs=refs,
                reasons=(
                    "a concurrent claim push held the remote ref transaction; "
                    "this attempt had no winner and may be retried by the "
                    "scheduler",
                    *details,
                ),
                kind="transient_transaction_contention",
            )
        raise ClaimRefsError(
            f"claim push failed operationally ({result.returncode}); this is not "
            "a claim race:\n" + "\n".join(details)
        )

    def _fenced_atomic_delete(
        self,
        refs: Sequence[str],
        expected_oid: str,
    ) -> dict[str, Any]:
        """Atomically delete refs only while each still holds the exact OID.

        Every delete refspec is fenced with ``--force-with-lease=<ref>:<oid>``,
        so a stale handle whose refs have been superseded cannot delete a
        newer worker's claims; that outcome is the typed
        ``stale_claim_conflict`` result, not an exception.
        """

        push_args = (
            "push",
            "--atomic",
            "--porcelain",
            *(f"--force-with-lease={ref}:{expected_oid}" for ref in refs),
            self.remote,
            *(f":{ref}" for ref in refs),
        )
        result = _run_git(self.local_repository, *push_args, check=False)
        if result.returncode == 0:
            return {
                "status": "released",
                "claim_oid": expected_oid,
                "refs": list(refs),
            }
        classification, details = _classify_failed_claim_push(refs, result)
        if classification in ("contention", "transient"):
            return {
                "status": "stale_claim_conflict",
                "claim_oid": expected_oid,
                "refs": list(refs),
                "reasons": [
                    (
                        "one or more claim refs no longer point at this exact "
                        "claim OID; nothing was deleted"
                        if classification == "contention"
                        else "a concurrent push held the remote ref transaction; "
                        "nothing was deleted and the delete may be retried"
                    ),
                    *details,
                ],
            }
        raise ClaimRefsError(
            f"claim delete push failed operationally ({result.returncode}); this "
            "is not a stale-claim race:\n" + "\n".join(details)
        )

    def _require_namespace_refs(self, refs: Sequence[str]) -> tuple[str, ...]:
        validated: list[str] = []
        for ref in refs:
            if type(ref) is not str or not ref.startswith(f"{self.namespace}/"):
                raise ClaimRefsError(
                    f"claim ref {ref!r} is not under this client's namespace "
                    f"{self.namespace!r}"
                )
            validated.append(ref)
        if not validated:
            raise ClaimRefsError("at least one claim ref is required")
        return tuple(validated)

    def release(self, acquisition: ClaimAcquisition) -> dict[str, Any]:
        """Release this client's own acquisition with exact claim-SHA fencing.

        The acquisition must belong to this client's remote, namespace, and
        claim worker identity; releasing a foreign acquisition (a different
        run's claims, another namespace, or another remote) is refused. Stale
        claims left by a crashed run are repaired only through the manual
        exact-SHA path (``inspect_claims`` + ``repair_stale_claim``).
        """

        if not isinstance(acquisition, ClaimAcquisition):
            raise ClaimRefsError("release requires a ClaimAcquisition")
        if acquisition.namespace != self.namespace:
            raise ClaimRefsError(
                f"acquisition namespace {acquisition.namespace!r} does not match "
                f"this client's namespace {self.namespace!r}"
            )
        if _normalized_remote(acquisition.remote) != _normalized_remote(self.remote):
            raise ClaimRefsError(
                f"acquisition remote {acquisition.remote!r} does not match this "
                f"client's remote {self.remote!r}"
            )
        if acquisition.receipt.claim_worker_id != self.claim_worker_id:
            raise ClaimRefsError(
                "acquisition belongs to claim worker "
                f"{acquisition.receipt.claim_worker_id!r}, not this client "
                f"({self.claim_worker_id!r}); a foreign claim is repaired only "
                "manually with inspect_claims and repair_stale_claim"
            )
        if type(acquisition.claim_oid) is not str or not GIT_SHA_RE.fullmatch(
            acquisition.claim_oid
        ):
            raise ClaimRefsError("acquisition claim OID is not one exact 40-hex SHA")
        refs = self._require_namespace_refs(acquisition.refs)
        return self._fenced_atomic_delete(refs, acquisition.claim_oid)

    def repair_stale_claim(
        self,
        *,
        refs: Sequence[str],
        expected_claim_oid: str,
    ) -> dict[str, Any]:
        """Manual exact-SHA stale-claim repair: delete refs at one exact OID.

        This is the only sanctioned way to remove a claim left by a crashed
        process. The operator reads the exact claim OID from
        ``inspect_claims`` and names it here; a ref that has since moved to a
        newer claim is NOT deleted and comes back as ``stale_claim_conflict``.
        There is no TTL and no automatic garbage collection.
        """

        if type(expected_claim_oid) is not str or not GIT_SHA_RE.fullmatch(
            expected_claim_oid
        ):
            raise ClaimRefsError(
                "stale-claim repair requires the exact 40-hex claim OID from "
                "inspect_claims"
            )
        return self._fenced_atomic_delete(
            self._require_namespace_refs(refs), expected_claim_oid
        )

    def list_remote_claims(self) -> dict[str, str]:
        """Map every remote claim ref under this namespace to its OID."""

        result = _run_git(
            self.local_repository, "ls-remote", self.remote, f"{self.namespace}/*"
        )
        claims: dict[str, str] = {}
        for line in result.stdout.decode("utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) == 2 and GIT_SHA_RE.fullmatch(parts[0]):
                claims[parts[1]] = parts[0]
        return claims

    def inspect_claims(self) -> list[dict[str, Any]]:
        """Report every claim under the namespace without modifying anything.

        Each entry names the exact ref, claim OID, committer timestamp, and
        the parsed receipt (or a reason when the object carries none). This is
        the Stage 1 stale-claim visibility surface; repair stays manual and
        exact-SHA-only.
        """

        claims = self.list_remote_claims()
        if claims:
            # Fetch the claim commits into the object store only; no local
            # refs are created and FETCH_HEAD is scratch state.
            _run_git(self.local_repository, "fetch", "--quiet", self.remote, *sorted(claims))
        report: list[dict[str, Any]] = []
        for ref in sorted(claims):
            oid = claims[ref]
            entry: dict[str, Any] = {
                "ref": ref,
                "claim_oid": oid,
                "receipt": None,
                "committer_timestamp_utc": None,
                "reasons": [],
            }
            show = _run_git(self.local_repository, "cat-file", "commit", oid, check=False)
            if show.returncode != 0:
                entry["reasons"].append("claim commit object could not be read")
                report.append(entry)
                continue
            text = show.stdout.decode("utf-8", errors="replace")
            headers, _, body = text.partition("\n\n")
            for header in headers.splitlines():
                if header.startswith("committer "):
                    entry["committer_timestamp_utc"] = " ".join(header.split()[-2:])
            receipt = _parse_receipt(body)
            if receipt is None:
                entry["reasons"].append(
                    "claim commit does not carry a parseable claim receipt"
                )
            else:
                entry["receipt"] = receipt.to_dict()
            report.append(entry)
        return report


def build_activated_claim_client(
    *,
    local_repository: Path | str,
    remote: str,
    worker_id: str,
    policy: ClaimPolicy | None = None,
) -> GitRefClaimClient:
    """Construct the production claim client from the committed claim policy.

    Fails closed with ``ClaimCoordinationNotActivatedError`` while the policy
    still records ``pending_capability_probe``; the namespace is always the
    explicitly activated one, never the first preference entry by default.
    """

    resolved = policy if policy is not None else load_claim_policy()
    namespace = activated_claim_namespace(resolved)
    return GitRefClaimClient(
        local_repository=local_repository,
        remote=remote,
        namespace=namespace,
        worker_id=worker_id,
    )


def _release_for_report(
    claim_client: GitRefClaimClient,
    claim: ClaimAcquisition,
) -> dict[str, Any]:
    """Release claims for a result payload; an operational failure is reported
    as data instead of masking the more important Issue outcome."""

    try:
        return claim_client.release(claim)
    except ClaimRefsError as exc:
        return {
            "status": "release_error",
            "claim_oid": claim.claim_oid,
            "refs": list(claim.refs),
            "reasons": [f"claim release failed operationally: {exc}"],
        }


def _exact_authority_failures(
    *,
    issue_workflow: Any,
    task_id: str,
    result: Mapping[str, Any],
) -> list[str]:
    """Re-read the Issue and verify the exact durable authority just acquired.

    The acquisition result must name the exact lease: same task, this
    worker's ``agent_working`` state, the exact ``lease_id``, and the exact
    ``state_version``/``last_event_id`` the acquisition reported. A
    same-worker state carrying a DIFFERENT lease fails the handoff.
    """

    reasons: list[str] = []
    expected = result.get("workflow_state")
    if not isinstance(expected, Mapping):
        return ["the acquisition result carries no workflow_state to verify against"]
    expected_lease_id = expected.get("lease_id")
    expected_version = expected.get("state_version")
    expected_event_id = expected.get("last_event_id")
    if type(expected_lease_id) is not str or not expected_lease_id:
        reasons.append("the acquisition result carries no exact lease_id")
    if type(expected_version) is not int:
        reasons.append("the acquisition result carries no exact state_version")
    if type(expected_event_id) is not str or not expected_event_id:
        reasons.append("the acquisition result carries no exact last_event_id")
    if reasons:
        return reasons
    try:
        expected_state = IssueWorkflowState.from_dict(expected)
    except WorkflowContractError as exc:
        return [f"the acquisition result workflow_state is invalid: {exc}"]
    try:
        verified = verify_post_mutation_state(
            issue_workflow,
            task_id,
            expected_state,
            transition_name="exact GitHub Issue lease authority",
        )
    except IssueWorkflowStoreError as exc:
        detail = str(exc)
        if "lease_id" in detail:
            detail = "re-read workflow state carries a different lease_id; " + detail
        return [detail]
    state = verified.state
    assert state is not None
    if state.state is not WorkflowState.AGENT_WORKING:
        reasons.append(
            f"re-read workflow state is {state.state.value}, not agent_working"
        )
    if state.task_id != task_id:
        reasons.append(
            f"re-read workflow task {state.task_id!r} is not the acquired task "
            f"{task_id!r}"
        )
    if state.worker_id != issue_workflow.worker_id:
        reasons.append(
            f"re-read lease worker {state.worker_id!r} is not this worker "
            f"{issue_workflow.worker_id!r}"
        )
    if state.lease_id != expected_lease_id:
        reasons.append(
            "re-read lease_id differs from the acquired lease_id; a same-worker "
            "state under a different lease must fail the handoff"
        )
    if state.state_version != expected_version:
        reasons.append(
            f"re-read state_version {state.state_version} differs from the "
            f"acquired state_version {expected_version}"
        )
    if state.last_event_id != expected_event_id:
        reasons.append(
            "re-read last_event_id differs from the acquired last_event_id"
        )
    return reasons


def _inspect_conflicting_claims(
    claim_client: GitRefClaimClient,
    refs: Sequence[str],
) -> list[dict[str, Any]]:
    wanted = set(refs)
    try:
        return [
            entry
            for entry in claim_client.inspect_claims()
            if entry.get("ref") in wanted
        ]
    except ClaimRefsError as exc:
        return [{"ref": None, "reasons": [f"claim inspection failed: {exc}"]}]


def _resume_durable_lease_despite_claim_conflict(
    *,
    claim_client: GitRefClaimClient,
    issue_workflow: Any,
    conflict: ClaimConflict,
    task: Mapping[str, Any],
    task_id: str,
    source_head: str,
    branch: str,
    checkout_path: str,
    planned_approach: str,
    expected_validation: str,
    now: str | None,
) -> dict[str, Any] | None:
    """Resume this worker's existing durable Issue lease past a stale claim.

    A claim ref left behind by a prior crashed run must not permanently
    invalidate an otherwise authoritative durable Issue lease. When the
    re-read Issue already records THIS worker's valid ``agent_working``
    lease, the resume proceeds through the ordinary Issue workflow (which
    performs no state transition for a same-worker resume), the exact
    authority is re-verified, and the conflicting claim is reported for
    manual exact-SHA repair — it is never deleted automatically, because it
    may belong to a newer active process. Returns None when this is not a
    valid durable resume, so the caller reports the ordinary claim conflict.
    """

    snapshot = issue_workflow.find(task_id)
    if snapshot is None or not getattr(snapshot, "valid", False):
        return None
    state = getattr(snapshot, "state", None)
    if state is None or state.state is not WorkflowState.AGENT_WORKING:
        return None
    if state.task_id != task_id or state.worker_id != issue_workflow.worker_id:
        return None
    result = issue_workflow.acquire_agent_lease(
        task=task,
        source_head=source_head,
        branch=branch,
        checkout_path=checkout_path,
        planned_approach=planned_approach,
        expected_validation=expected_validation,
        now=now,
    )
    if result.get("status") != "resumed":
        return None
    failures = _exact_authority_failures(
        issue_workflow=issue_workflow, task_id=task_id, result=result
    )
    if failures:
        return None
    return {
        **result,
        "ephemeral_claim": conflict.to_dict(),
        "stale_ephemeral_claim": {
            "refs": list(conflict.refs),
            "claims": _inspect_conflicting_claims(claim_client, conflict.refs),
            "repair": (
                "manual exact-SHA repair only: read the exact claim OID with "
                "inspect_claims, confirm the owning process is dead, then "
                "delete with repair_stale_claim; never delete a claim without "
                "its exact current OID"
            ),
        },
        "reasons": [
            "the durable GitHub Issue lease already belongs to this worker and "
            "was resumed; an ephemeral claim ref from a prior run is still "
            "present and requires manual exact-SHA repair",
        ],
    }


def acquire_issue_lease_with_claims(
    *,
    claim_client: GitRefClaimClient,
    issue_workflow: Any,
    task: Mapping[str, Any],
    source_head: str,
    branch: str,
    checkout_path: str,
    planned_approach: str,
    expected_validation: str,
    now: str | None = None,
) -> dict[str, Any]:
    """Guard durable Issue lease acquisition with short-lived claim refs.

    The claims are held across ``issue_workflow.acquire_agent_lease``. After a
    normal ``acquired``/``resumed`` result the Issue is re-read and this
    worker's EXACT authority verified — task, ``agent_working`` state, worker
    identity, ``lease_id``, ``state_version``, and ``last_event_id`` — before
    the claims are released with exact-SHA fencing; a failed verification is
    reported as blocked, never as success. If verified authority was acquired
    but the claims cannot be released cleanly, the typed
    ``lease_acquired_claim_cleanup_required`` result is returned so ordinary
    execution stops while the durable lease fact is preserved. A normal
    non-acquired Issue outcome releases this process's still-exact claims. A
    claim conflict against an already-held durable lease of this same worker
    resumes durably and reports the stale claim for manual repair. An
    unexpected crash leaves the claims in place for ``inspect_claims`` —
    there is no automatic cleanup.
    """

    task_id = validate_task_id(task.get("id"))
    issue_worker = getattr(issue_workflow, "worker_id", None)
    if type(issue_worker) is not str or not issue_worker.strip():
        raise ClaimRefsError(
            "the Issue workflow does not expose a non-empty worker_id; claim "
            "coordination cannot verify lease identity"
        )
    if claim_client.worker_id != issue_worker:
        raise ClaimRefsError(
            f"claim client worker_id {claim_client.worker_id!r} differs from the "
            f"Issue workflow worker_id {issue_worker!r}; refusing before any "
            "remote mutation"
        )
    claim = claim_client.acquire(
        task_id=task_id,
        exclusive_resources=task.get("exclusive_resources") or [],
        source_head=source_head,
        now=now,
    )
    if isinstance(claim, ClaimConflict):
        resumed = _resume_durable_lease_despite_claim_conflict(
            claim_client=claim_client,
            issue_workflow=issue_workflow,
            conflict=claim,
            task=task,
            task_id=task_id,
            source_head=source_head,
            branch=branch,
            checkout_path=checkout_path,
            planned_approach=planned_approach,
            expected_validation=expected_validation,
            now=now,
        )
        if resumed is not None:
            return resumed
        return {
            "status": "blocked",
            "reasons": [
                "ephemeral Git-ref claim conflict: another worker currently holds "
                "the task or an exclusive-resource claim ref, or the atomic claim "
                "transaction was raced; losing this race is a normal scheduling "
                "result and the scheduler may retry later",
                *claim.reasons,
            ],
            "ephemeral_claim": claim.to_dict(),
        }
    result = issue_workflow.acquire_agent_lease(
        task=task,
        source_head=source_head,
        branch=branch,
        checkout_path=checkout_path,
        planned_approach=planned_approach,
        expected_validation=expected_validation,
        now=now,
    )
    if result.get("status") not in ("acquired", "resumed"):
        # Normal initialization failure by this still-active process: release
        # its own still-exact claims and pass the Issue outcome through.
        release = _release_for_report(claim_client, claim)
        return {**result, "ephemeral_claim_release": release}
    failures = _exact_authority_failures(
        issue_workflow=issue_workflow, task_id=task_id, result=result
    )
    if failures:
        release = _release_for_report(claim_client, claim)
        return {
            "status": "blocked",
            "reasons": [
                "GitHub Issue lease authority could not be re-read and verified as "
                "this worker's exact agent_working lease; the handoff did not "
                "succeed",
                *failures,
            ],
            "issue_result": result,
            "ephemeral_claim_release": release,
        }
    release = _release_for_report(claim_client, claim)
    if release.get("status") != "released":
        # The durable Issue lease WAS acquired and verified, but this run's
        # ephemeral claims could not be removed cleanly. Ordinary execution
        # must not continue as though the handoff completed; a newer claim is
        # never deleted silently.
        return {
            "status": "lease_acquired_claim_cleanup_required",
            "reasons": [
                "the durable GitHub Issue lease was acquired and verified, but the "
                "ephemeral claim refs could not be released cleanly; an operator "
                "must inspect the claim refs and repair them with exact-SHA "
                "fencing before ordinary execution continues",
                *(release.get("reasons") or ()),
            ],
            "issue_result": result,
            "ephemeral_claim": claim.to_dict(),
            "ephemeral_claim_release": release,
        }
    return {
        **result,
        "ephemeral_claim": {
            "claim_oid": claim.claim_oid,
            "refs": list(claim.refs),
            "release": release,
        },
    }


def probe_remote_claim_namespace(
    *,
    local_repository: Path | str,
    remote: str,
    namespace: str,
    allow_canonical_remote: bool = False,
) -> dict[str, Any]:
    """Opt-in capability smoke test: can this remote host the claim namespace?

    Creates one probe ref under ``<namespace>/capability-probe/`` with
    nonexistence CAS and deletes it with exact-SHA fencing. Refuses the
    production No Safe Circle remote unless the operator passes
    ``allow_canonical_remote=True`` for the deliberate live capability test.
    """

    if (
        _normalized_remote(str(remote)) == _normalized_remote(CANONICAL_REMOTE)
        and not allow_canonical_remote
    ):
        raise ClaimRefsError(
            "the production GitHub remote is refused by default; run the live "
            "namespace capability smoke test deliberately with "
            "allow_canonical_remote=True"
        )
    client = GitRefClaimClient(
        local_repository=local_repository,
        remote=remote,
        namespace=namespace,
        worker_id="namespace-capability-probe",
    )
    probe_ref = f"{client.namespace}/capability-probe/{uuid.uuid4().hex}"
    receipt = ClaimReceipt(
        schema_version=CLAIM_RECEIPT_SCHEMA_VERSION,
        claim_worker_id=client.claim_worker_id,
        task_id="NSC-000",
        exclusive_resources=(),
        resource_hashes=(),
        source_head="0" * 40,
        created_at_utc=utc_now(),
    )
    oid = client._create_claim_commit(receipt)
    create = _run_git(
        client.local_repository,
        "push",
        "--atomic",
        f"--force-with-lease={probe_ref}:",
        client.remote,
        f"{oid}:{probe_ref}",
        check=False,
    )
    created = create.returncode == 0
    deleted = False
    delete_stderr = ""
    if created:
        delete = _run_git(
            client.local_repository,
            "push",
            "--atomic",
            f"--force-with-lease={probe_ref}:{oid}",
            client.remote,
            f":{probe_ref}",
            check=False,
        )
        deleted = delete.returncode == 0
        delete_stderr = (delete.stderr or b"").decode("utf-8", errors="replace").strip()
    return {
        "namespace": client.namespace,
        "remote": client.remote,
        "probe_ref": probe_ref,
        "probe_oid": oid,
        "create_supported": created,
        "delete_supported": deleted,
        "create_stderr": (create.stderr or b"").decode("utf-8", errors="replace").strip(),
        "delete_stderr": delete_stderr,
        "capability": created and deleted,
    }


__all__ = [
    "CLAIM_MESSAGE_MARKER",
    "CLAIM_RECEIPT_SCHEMA_VERSION",
    "ClaimAcquisition",
    "ClaimConflict",
    "ClaimReceipt",
    "ClaimRefsError",
    "GitRefClaimClient",
    "acquire_issue_lease_with_claims",
    "build_activated_claim_client",
    "canonical_resource_hash",
    "probe_remote_claim_namespace",
    "resource_claim_ref",
    "task_claim_ref",
]
