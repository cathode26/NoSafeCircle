"""Container-side support for durable, role-scoped decomposition sessions.

The host owner (`Pipeline/TaskReviewAgent/decomposition_session_pool.py`)
reserves one resumable provider conversation per semantic role and provider
before a D1B run starts and settles them from the run's durable artifacts after
Docker returns. This module is the part that runs inside the round-robin or
one-provider container: it loads the host's lease bundle, binds every lease to
the exact run it is about to serve, hands each round the exact session binding
its role/provider lease names, and writes the evidence block the host needs to
prove the assignment from the round artifact's own bytes.

Two roles, two pools, no sharing. `task_decomposer` (the candidate author) and
`decomposition_reviewer` (the independent reviewer) are distinct semantic roles
with distinct scope keys and therefore distinct conversations, even when the
same provider and model serve both. An author conversation is never handed to
a reviewer round and a reviewer conversation is never handed to an author
round: the lease key is `<provider>:<role>`, the scope carries the role, and
the AgentRuntime adapters independently refuse a binding whose role differs
from the invocation's role. Reviewer prompts are built only from the candidate
artifacts and deterministic context the circuit authorizes; the author's
conversation history is not available to a reviewer round at all.

Identity is proven, never assumed. A round confirms the conversation it used
only through the adapter's transcript-proven `ProviderSessionConfirmation`. A
round that asked for a session but proved none stops the run: its output can
not be attributed to the conversation it was supposed to come from. Every
pooled round records the exact artifact it produced (candidate or review) and
its SHA-256, the round and invocation identity, the role, provider, model,
source identity, lease, and the confirmed session, so the host can refuse any
check-in whose artifact, round, run, task, or identity does not match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from Pipeline.AgentRuntime.durable_session_pool import (
    DURABLE_SESSION_POOL_SCHEMA_VERSION,
    DurableSessionPoolError,
    SessionLease,
    authority_capsule,
    resume_contract_fingerprint,
    strict_json,
)
from Pipeline.AgentRuntime.provider_sessions import (
    ProviderSessionBinding,
    ProviderSessionConfirmation,
)


DECOMPOSITION_SESSION_PROTOCOL_VERSION = "1.0"
DECOMPOSITION_LEASE_BUNDLE_SCHEMA_VERSION = "1.0"
POOLED_ROUND_EVIDENCE_SCHEMA_VERSION = "1.0"
DECOMPOSITION_SESSION_ROLES = ("task_decomposer", "decomposition_reviewer")
DECOMPOSITION_MODES = frozenset({"d1b1", "round_robin_d1b2"})
PROVIDER_IDENTIFIERS = {"claude": "claude-code", "codex": "openai-codex"}
PROVIDER_NAMES = {identifier: name for name, identifier in PROVIDER_IDENTIFIERS.items()}
# Every field a pooled round's evidence block carries, in order. The host
# rebuilds the same block from the lease and the run request and compares
# field by field, so an artifact borrowed from another round, run, task, lease,
# or source can never prove this assignment.
POOLED_ROUND_EVIDENCE_FIELDS = (
    "schema_version",
    "pool_schema_version",
    "protocol_version",
    "lease_key",
    "lease_id",
    "record_id",
    "task_id",
    "run_id",
    "decomposition_mode",
    "round_number",
    "invocation_id",
    "role",
    "provider_name",
    "provider_identifier",
    "model",
    "reasoning_effort",
    "repository_identity",
    "conversation_store",
    "source_head",
    "source_tree",
    "checkout_identity",
    "requested_mode",
    "requested_session_id",
    "confirmed_session",
    "artifact_path",
    "artifact_sha256",
    "agent_status",
    "round_status",
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LEASE_KEY = re.compile(r"^(claude|codex):(task_decomposer|decomposition_reviewer)$")
# The one extra scope fact a decomposition lease binds: the Docker Compose
# volume the provider's conversation lives in, ``compose:<project>/<volume>``.
# The container cannot observe the project it runs under, so it carries the
# host's binding into every round's evidence and the host verifies it.
CONVERSATION_STORE_BINDING = "conversation_store"
_CONVERSATION_STORE = re.compile(r"^compose:[a-z0-9][a-z0-9_-]{0,127}/(claude-config|codex-config)$")


class DecompositionSessionError(RuntimeError):
    """A pooled decomposition session contract failed closed."""


def lease_key(provider_name: str, role: str) -> str:
    key = f"{provider_name}:{role}"
    if _LEASE_KEY.fullmatch(key) is None:
        raise DecompositionSessionError(f"unsupported decomposition lease key: {key}")
    return key


def repository_identity_of(source_root: Path) -> str:
    """Read the source checkout's configured origin exactly as the host does."""

    try:
        completed = subprocess.run(
            ("git", "remote", "get-url", "origin"),
            cwd=str(source_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=30.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DecompositionSessionError("source repository identity could not be read") from exc
    if completed.returncode != 0:
        raise DecompositionSessionError("source checkout has no readable origin repository identity")
    value = completed.stdout.decode("utf-8", errors="strict").strip()
    if not value:
        raise DecompositionSessionError("source checkout origin is empty")
    return value


@dataclass(frozen=True)
class DecompositionLeaseBundle:
    """The host's exact reservation for one decomposition run."""

    run_id: str
    task_id: str
    decomposition_mode: str
    source_commit: str
    repository_identity: str
    checkout_identity: str
    leases: dict[str, SessionLease]
    codex_resume_sandbox_argument: tuple[str, ...] | None

    def lease_for(self, provider_name: str, role: str) -> SessionLease | None:
        return self.leases.get(lease_key(provider_name, role))


def load_lease_bundle(path: Path | str, *, run_id: str) -> DecompositionLeaseBundle:
    """Load and strictly validate the host's lease bundle for this exact run."""

    try:
        payload = strict_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise DecompositionSessionError(
            f"decomposition lease bundle is unreadable or malformed: {type(exc).__name__}"
        ) from exc
    return lease_bundle_from_dict(payload, run_id=run_id)


def lease_bundle_from_dict(payload: Any, *, run_id: str) -> DecompositionLeaseBundle:
    expected = {
        "schema_version", "run_id", "task_id", "decomposition_mode", "source_commit",
        "repository_identity", "checkout_identity", "leases", "codex_resume_sandbox_argument",
    }
    if not isinstance(payload, Mapping) or set(payload) != expected:
        raise DecompositionSessionError("decomposition lease bundle fields differ from schema")
    if payload["schema_version"] != DECOMPOSITION_LEASE_BUNDLE_SCHEMA_VERSION:
        raise DecompositionSessionError("unsupported decomposition lease bundle schema version")
    if payload["run_id"] != run_id:
        raise DecompositionSessionError(
            f"decomposition lease bundle is bound to run {payload['run_id']!r}, not {run_id!r}"
        )
    task_id = payload["task_id"]
    if type(task_id) is not str or re.fullmatch(r"NSC-[0-9]{3}", task_id) is None:
        raise DecompositionSessionError("decomposition lease bundle task id is invalid")
    mode = payload["decomposition_mode"]
    if mode not in DECOMPOSITION_MODES:
        raise DecompositionSessionError("decomposition lease bundle mode is unsupported")
    source_commit = payload["source_commit"]
    if type(source_commit) is not str or _COMMIT.fullmatch(source_commit) is None:
        raise DecompositionSessionError("decomposition lease bundle source commit is invalid")
    for name in ("repository_identity", "checkout_identity"):
        if type(payload[name]) is not str or not payload[name].strip():
            raise DecompositionSessionError(f"decomposition lease bundle {name} is invalid")
    argument = payload["codex_resume_sandbox_argument"]
    if argument is not None and (
        not isinstance(argument, list) or not argument
        or any(type(item) is not str or not item for item in argument)
    ):
        raise DecompositionSessionError("decomposition lease bundle resume control is invalid")
    resume_argument = None if argument is None else tuple(argument)
    resume_fingerprint = resume_contract_fingerprint(resume_argument)
    if not isinstance(payload["leases"], Mapping) or not payload["leases"]:
        raise DecompositionSessionError("decomposition lease bundle carries no leases")
    leases: dict[str, SessionLease] = {}
    for key, value in payload["leases"].items():
        if type(key) is not str or _LEASE_KEY.fullmatch(key) is None:
            raise DecompositionSessionError(f"unsupported decomposition lease key: {key!r}")
        try:
            lease = SessionLease.from_dict(value)
        except DurableSessionPoolError as exc:
            raise DecompositionSessionError(f"lease {key} is invalid: {exc}") from exc
        provider_name, role = key.split(":", 1)
        scope = lease.scope
        if scope.protocol_version != DECOMPOSITION_SESSION_PROTOCOL_VERSION:
            raise DecompositionSessionError(
                f"lease {key} speaks protocol {scope.protocol_version!r}; this build speaks "
                f"{DECOMPOSITION_SESSION_PROTOCOL_VERSION!r}"
            )
        if scope.role != role or scope.provider_identifier != PROVIDER_IDENTIFIERS[provider_name]:
            raise DecompositionSessionError(f"lease {key} names a different role or provider than its key")
        if scope.session_class != "worker" or scope.workload_class != "deep":
            raise DecompositionSessionError(f"lease {key} is not a deep worker assignment")
        if scope.repository_identity != payload["repository_identity"]:
            raise DecompositionSessionError(f"lease {key} names a different repository than the bundle")
        if [name for name, _ in scope.bindings] != [CONVERSATION_STORE_BINDING]:
            raise DecompositionSessionError(
                f"lease {key} must bind exactly its provider conversation store and nothing else"
            )
        store = scope.bindings[0][1]
        if _CONVERSATION_STORE.fullmatch(store) is None or not store.endswith(f"/{provider_name}-config"):
            raise DecompositionSessionError(
                f"lease {key} names a conversation store its provider does not use: {store!r}"
            )
        if lease.assignment_value("run_id") != run_id or lease.assignment_value("task_id") != task_id:
            raise DecompositionSessionError(f"lease {key} is assigned to another run or task")
        if lease.assignment_value("source_commit") != source_commit:
            raise DecompositionSessionError(f"lease {key} is assigned to another source commit")
        if provider_name == "codex":
            if resume_fingerprint is None or scope.resume_contract != resume_fingerprint:
                raise DecompositionSessionError(
                    f"lease {key} requires the exact verified Codex resume control the bundle carries"
                )
        elif scope.resume_contract is not None:
            raise DecompositionSessionError(f"lease {key} carries a resume control its provider does not use")
        leases[key] = lease
    return DecompositionLeaseBundle(
        run_id=run_id, task_id=task_id, decomposition_mode=mode, source_commit=source_commit,
        repository_identity=payload["repository_identity"], checkout_identity=payload["checkout_identity"],
        leases=leases, codex_resume_sandbox_argument=resume_argument,
    )


def bind_lease_bundle_to_run(
    bundle: DecompositionLeaseBundle,
    *,
    task_id: str,
    source_head: str,
    source_root: Path,
    decomposition_mode: str,
    scheduler_repository_identity: str,
    provider_order: tuple[str, ...],
) -> None:
    """Fail closed unless every lease matches the run this container is about to perform."""

    if bundle.task_id != task_id:
        raise DecompositionSessionError(
            f"lease bundle is bound to task {bundle.task_id}, not {task_id}"
        )
    if bundle.source_commit != source_head:
        raise DecompositionSessionError(
            f"lease bundle is bound to source commit {bundle.source_commit}, not {source_head}"
        )
    if bundle.decomposition_mode != decomposition_mode:
        raise DecompositionSessionError(
            f"lease bundle is bound to mode {bundle.decomposition_mode}, not {decomposition_mode}"
        )
    observed = repository_identity_of(source_root)
    if bundle.repository_identity != scheduler_repository_identity or observed != scheduler_repository_identity:
        raise DecompositionSessionError(
            "lease bundle repository identity, the scheduler-proven identity, and the "
            "checkout's configured origin must all agree"
        )
    for key in bundle.leases:
        provider_name = key.split(":", 1)[0]
        if provider_name not in provider_order:
            raise DecompositionSessionError(
                f"lease {key} names a provider this run does not rotate through"
            )


def assert_lease_matches_route(
    lease: SessionLease,
    *,
    provider_identifier: str,
    model: str,
    reasoning_effort: str | None,
) -> None:
    """The route this round will actually use must equal what the lease authorized."""

    scope = lease.scope
    if scope.provider_identifier != provider_identifier:
        raise DecompositionSessionError(
            f"lease is bound to provider {scope.provider_identifier!r}; this round routes through {provider_identifier!r}"
        )
    if scope.model != model:
        raise DecompositionSessionError(
            f"lease is bound to model {scope.model!r}; this round resolved {model!r}"
        )
    if scope.reasoning_effort != reasoning_effort:
        raise DecompositionSessionError(
            f"lease is bound to reasoning effort {scope.reasoning_effort!r}; this round resolved {reasoning_effort!r}"
        )


@dataclass
class PooledRoundSessions:
    """Per-run memory of which conversation each lease key has proven so far."""

    bundle: DecompositionLeaseBundle
    confirmations: dict[str, ProviderSessionConfirmation] = field(default_factory=dict)
    rounds: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    unproven: dict[str, str] = field(default_factory=dict)

    def binding_for(self, key: str) -> ProviderSessionBinding:
        lease = self.bundle.leases[key]
        confirmed = self.confirmations.get(key)
        if confirmed is None:
            return lease.binding()
        # A later round of the same run continues the exact conversation the
        # earlier round proved; it never opens a second one for the same lease.
        return confirmed.resume_binding()

    def capsule_for(self, key: str, *, current: Mapping[str, str], allowed_actions: tuple[str, ...]) -> str:
        lease = self.bundle.leases[key]
        confirmed = self.confirmations.get(key)
        prior = lease.prior_completed_assignment_count + len(self.rounds.get(key, ()))
        return authority_capsule(
            role=lease.scope.role,
            mode="resume" if (lease.is_resume or confirmed is not None) else "start",
            prior_completed_assignment_count=prior,
            current=current,
            allowed_actions=allowed_actions,
            capabilities=("repository_read", "repository_search"),
            obligations=(
                "Return exactly one structured result for this round; it is review-only.",
                "No repository write, command execution, GitHub, Unity, or graph-application authority exists.",
            ),
        )

    def record_unproven(self, key: str, detail: str) -> None:
        """A round asked for this lease and proved nothing: invoked, never reusable."""

        self.unproven[key] = detail

    def record(self, key: str, confirmed: ProviderSessionConfirmation, evidence: dict[str, Any]) -> None:
        existing = self.confirmations.get(key)
        if existing is not None and existing.session_id != confirmed.session_id:
            raise DecompositionSessionError(
                f"lease {key} proved conversation {confirmed.session_id} after proving {existing.session_id}"
            )
        self.confirmations.setdefault(key, confirmed)
        self.rounds.setdefault(key, []).append(evidence)

    def summary(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, lease in sorted(self.bundle.leases.items()):
            confirmed = self.confirmations.get(key)
            result[key] = {
                "lease_id": lease.lease_id,
                "record_id": lease.record_id,
                "role": lease.scope.role,
                "provider_identifier": lease.scope.provider_identifier,
                "requested_mode": lease.mode,
                "requested_session_id": lease.session_id,
                "invoked": key in self.rounds or key in self.unproven,
                "identity_unproven": self.unproven.get(key),
                "confirmed_session": None if confirmed is None else confirmed.to_dict(),
                "rounds": list(self.rounds.get(key, ())),
            }
        return result


def pooled_round_evidence(
    *,
    lease_key_value: str,
    lease: SessionLease,
    task_id: str,
    run_id: str,
    decomposition_mode: str,
    round_number: int,
    invocation_id: str,
    role: str,
    provider_name: str,
    model: str,
    reasoning_effort: str | None,
    source_head: str,
    source_tree: str,
    checkout_identity: str,
    requested: ProviderSessionBinding,
    confirmed: ProviderSessionConfirmation,
    artifact_path: str | None,
    artifact_sha256: str | None,
    agent_status: str,
    round_status: str,
) -> dict[str, Any]:
    """Return the exact assignment binding a pooled round writes into its own artifact."""

    if role != lease.scope.role:
        raise DecompositionSessionError(f"round role {role!r} differs from lease role {lease.scope.role!r}")
    if artifact_sha256 is not None and _SHA256.fullmatch(artifact_sha256) is None:
        raise DecompositionSessionError("artifact sha256 must be exact")
    value = {
        "schema_version": POOLED_ROUND_EVIDENCE_SCHEMA_VERSION,
        "pool_schema_version": DURABLE_SESSION_POOL_SCHEMA_VERSION,
        "protocol_version": lease.scope.protocol_version,
        "lease_key": lease_key_value,
        "lease_id": lease.lease_id,
        "record_id": lease.record_id,
        "task_id": task_id,
        "run_id": run_id,
        "decomposition_mode": decomposition_mode,
        "round_number": round_number,
        "invocation_id": invocation_id,
        "role": role,
        "provider_name": provider_name,
        "provider_identifier": lease.scope.provider_identifier,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "repository_identity": lease.scope.repository_identity,
        "conversation_store": lease.scope.binding(CONVERSATION_STORE_BINDING),
        "source_head": source_head,
        "source_tree": source_tree,
        "checkout_identity": checkout_identity,
        "requested_mode": requested.mode,
        "requested_session_id": requested.session_id,
        "confirmed_session": confirmed.to_dict(),
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
        "agent_status": agent_status,
        "round_status": round_status,
    }
    if tuple(value) != POOLED_ROUND_EVIDENCE_FIELDS:
        raise DecompositionSessionError("pooled round evidence fields drifted from the schema")
    return value


def sha256_of_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_artifact_sha256(value: Any) -> str:
    """Hash the exact bytes `publish_json_no_overwrite` writes for ``value``."""

    text = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "DECOMPOSITION_LEASE_BUNDLE_SCHEMA_VERSION",
    "DECOMPOSITION_MODES",
    "DECOMPOSITION_SESSION_PROTOCOL_VERSION",
    "DECOMPOSITION_SESSION_ROLES",
    "POOLED_ROUND_EVIDENCE_FIELDS",
    "POOLED_ROUND_EVIDENCE_SCHEMA_VERSION",
    "PROVIDER_IDENTIFIERS",
    "PROVIDER_NAMES",
    "DecompositionLeaseBundle",
    "DecompositionSessionError",
    "PooledRoundSessions",
    "assert_lease_matches_route",
    "bind_lease_bundle_to_run",
    "canonical_artifact_sha256",
    "lease_bundle_from_dict",
    "lease_key",
    "load_lease_bundle",
    "pooled_round_evidence",
    "repository_identity_of",
    "sha256_of_file",
]
