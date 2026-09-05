"""Durable host owner for role-scoped decomposition author and reviewer sessions.

Before one D1B run starts, this owner reserves one resumable provider
conversation per semantic role and provider the circuit can reach -- the
`task_decomposer` (candidate author) and the `decomposition_reviewer`
(independent reviewer) -- writes those leases into a read-only bundle the
container mounts, and holds one operating-system liveness lock for the run.
After Docker returns it settles every lease from the run's durable artifacts:
the container's `pooled_sessions` summary, every pooled round's evidence block,
and the exact bytes of the candidate or review artifact that evidence names.
The pool-state lock is never held while Docker or a provider runs.

Independence is structural. Author and reviewer scopes differ in their role,
so they are different records with different conversations even when the same
provider and model serve both; a lease is keyed `<provider>:<role>` and the
container hands each round only the lease for its own role. No decomposition
conversation is ever shared with the architect, supervisor, or ExecutionCrew
pools: the scope protocol, role vocabulary, and state file are all distinct.

Sessions are repository-wide. Task, run, round, source commit, checkout, and
artifact identities are per-assignment facts bound into the lease, the
capsule, and the check-in evidence -- never into the scope -- so a
conversation may serve a later task only through a fresh assignment capsule
that revokes the prior task's authority and binds the new task, source, and
artifact. A check-in whose evidence names another task, run, round, role,
provider, model, source, checkout, lease, artifact, or session identity is
refused: the conversation is withdrawn, never resumed.

Codex conversations are reserved only when the operator has supplied the
verified `codex exec resume` control (`NSC_CODEX_RESUME_SANDBOX_ARGUMENT`);
otherwise Codex rounds stay ephemeral and only Claude rounds pool, exactly as
the ExecutionCrew pool already behaves.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from typing import Any, BinaryIO, Callable, Mapping


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for _module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))

from Pipeline.AgentRuntime.durable_session_pool import (  # noqa: E402
    DURABLE_SESSION_POOL_SCHEMA_VERSION,
    AssignmentSettlement,
    DurableSessionPool,
    DurableSessionPoolError,
    SessionLease,
    SessionLifetimePolicy,
    SessionRecord,
    SessionScope,
    append_journal_line,
    confirmation_from_dict,
    strict_json,
    utc_now,
    utc_text,
)
from Pipeline.AgentRuntime.provider_sessions import ProviderSessionConfirmation
from Pipeline.TaskDecomposition.session_pool_support import (
    DECOMPOSITION_LEASE_BUNDLE_SCHEMA_VERSION,
    DECOMPOSITION_MODES,
    DECOMPOSITION_SESSION_PROTOCOL_VERSION,
    DECOMPOSITION_SESSION_ROLES,
    POOLED_ROUND_EVIDENCE_FIELDS,
    POOLED_ROUND_EVIDENCE_SCHEMA_VERSION,
    PROVIDER_IDENTIFIERS,
    lease_key,
)
from TaskDecomposition.live_decomposition import _invocation_id as d1b1_invocation_id
from TaskDecomposition.round_robin_decomposition import (
    _round_invocation_id as d1b2_invocation_id,
)

from .contracts import TaskReviewContractError, validate_task_id
from .execution_session_pool import (
    LIVENESS_KIND,
    LIVENESS_SCHEMA_VERSION,
    _acquire_liveness_lock,
    _exclusive_file_lock,
    _file_identity,
    _probe_liveness,
    _release_liveness_lock,
    _write_verified,
)
from .supervisor_session_pool import (
    CodexResumeActivation,
    SupervisorSessionPoolError,
    conversation_store_binding,
    resolve_compose_project,
)


DECOMPOSITION_OWNER_SCHEMA_VERSION = "1.0"
DECOMPOSITION_SESSION_MAX_AGE_SECONDS = 14 * 24 * 3600
DECOMPOSITION_SESSION_IDLE_LIFETIME_SECONDS = 7 * 24 * 3600
DECOMPOSITION_SESSION_LIFETIME = SessionLifetimePolicy(
    max_age_seconds=DECOMPOSITION_SESSION_MAX_AGE_SECONDS,
    idle_lifetime_seconds=DECOMPOSITION_SESSION_IDLE_LIFETIME_SECONDS,
)
DECOMPOSITION_CONTEXT_WINDOW_ENVIRONMENT = "NSC_DECOMPOSITION_CONTEXT_WINDOW_TOKENS"
CHECKOUT_IDENTITY_PREFIX = "manifest-sha256:"
_RUN_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ASSIGNMENT_STATUSES = frozenset({"active", "settled", "stranded", "cancelled"})
_REPOSITORY_ROOT = ROOT
_ROUND_STATUS_OUTCOMES = {
    "candidate_valid": "completed",
    "revised_candidate_valid": "completed",
    "independent_pass": "completed",
    "needs_human": "completed",
    "review_ready": "completed",
    "rejected": "output_failure",
    "agent_failed": "provider_failure",
}
_FAILURE_CLASSIFICATION_OUTCOMES = {
    "timeout": "uncertain",
    "internal_error": "uncertain",
    "provider_error": "provider_failure",
    "schema_error": "output_failure",
    "invalid_request": "other_failure",
    "permission_denied": "provider_failure",
    "budget_exhausted": "provider_failure",
}


class DecompositionSessionPoolError(TaskReviewContractError):
    """The decomposition pool contract or persisted identity was invalid."""


def possible_lease_keys(
    *, decomposition_mode: str, provider_order: tuple[str, ...], max_calls: int
) -> tuple[str, ...]:
    """Return every `<provider>:<role>` the circuit can reach, in first-use order.

    D1B.1 invokes one author. D1B.2 authors with the first provider and then
    lets every later position review, so the reachable pairs are exactly the
    first provider as author plus each provider that occupies a review round
    within the call limit. Nothing here infers a role from a round number at
    invocation time: the container receives the exact pair per lease key.
    """

    if decomposition_mode not in DECOMPOSITION_MODES:
        raise DecompositionSessionPoolError("unsupported decomposition mode")
    if not provider_order or any(name not in PROVIDER_IDENTIFIERS for name in provider_order):
        raise DecompositionSessionPoolError("provider order must name claude and/or codex")
    keys = [lease_key(provider_order[0], "task_decomposer")]
    if decomposition_mode == "round_robin_d1b2":
        if type(max_calls) is not int or max_calls < 2:
            raise DecompositionSessionPoolError("round-robin pooling requires max_calls of at least 2")
        for round_number in range(2, max_calls + 1):
            key = lease_key(provider_order[(round_number - 1) % len(provider_order)], "decomposition_reviewer")
            if key not in keys:
                keys.append(key)
    return tuple(keys)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def context_window_percent(usage: Any, window_tokens: int | None) -> int | None:
    if window_tokens is None or not isinstance(usage, Mapping):
        return None
    tokens = usage.get("input_tokens")
    if isinstance(tokens, bool) or type(tokens) is not int or tokens < 0:
        return None
    return min(100, (tokens * 100) // window_tokens)


class DecompositionSessionPoolOwner:
    """Own one repository-scoped, process-safe pool of decomposition sessions."""

    def __init__(
        self,
        *,
        checkout: Path | str,
        repository_identity: str,
        provider_models: Mapping[str, tuple[str, str | None]],
        codex_resume_activation: CodexResumeActivation | None,
        compose_project: str,
        context_window_tokens: int | None = None,
        manifest_path: Path | str | None = None,
        clock: Callable[[], dt.datetime] = utc_now,
        identity_factory: Callable[[], str] | None = None,
        host_identity: str | None = None,
    ) -> None:
        self.checkout = Path(checkout).resolve()
        if type(repository_identity) is not str or not repository_identity.strip():
            raise DecompositionSessionPoolError("repository identity must be exact non-empty text")
        self.repository_identity = repository_identity
        # The compose project is the exact one the launcher runs the
        # round-robin container under; it names the volumes the provider
        # conversations live in, so it is part of every lease's identity.
        try:
            self.compose_project = resolve_compose_project(compose_project)
        except SupervisorSessionPoolError as exc:
            raise DecompositionSessionPoolError(str(exc)) from exc
        models: dict[str, tuple[str, str | None]] = {}
        for name, value in provider_models.items():
            if name not in PROVIDER_IDENTIFIERS or type(value) is not tuple or len(value) != 2:
                raise DecompositionSessionPoolError("provider_models must map claude/codex to (model, effort)")
            model, effort = value
            if type(model) is not str or not model.strip():
                raise DecompositionSessionPoolError(f"{name} model must be exact non-empty text")
            if name == "claude" and effort is not None:
                raise DecompositionSessionPoolError("claude decomposition sessions carry no reasoning effort")
            if name == "codex" and (type(effort) is not str or not effort.strip()):
                raise DecompositionSessionPoolError("codex decomposition sessions require an exact reasoning effort")
            models[name] = (model.strip(), effort)
        self.provider_models = models
        if codex_resume_activation is not None and type(codex_resume_activation) is not CodexResumeActivation:
            raise DecompositionSessionPoolError("codex_resume_activation must be an exact CodexResumeActivation")
        self.codex_resume_activation = codex_resume_activation
        if context_window_tokens is not None and (
            isinstance(context_window_tokens, bool) or type(context_window_tokens) is not int or context_window_tokens < 1000
        ):
            raise DecompositionSessionPoolError("context window must be an explicit integer of at least 1000 tokens")
        self.context_window_tokens = context_window_tokens
        self.manifest_path = Path(
            manifest_path or self.checkout.parent / ".task-review-agent" / f"{self.checkout.name}.json"
        ).resolve()
        repository_hash = hashlib.sha256(self.repository_identity.encode("utf-8")).hexdigest()
        self.root = self.checkout.parent / ".task-review-agent" / "session-pools" / repository_hash / "decomposition"
        # Pool records and the assignment ledger are one document written by
        # one atomic, verified replace, so no crash can leave an active record
        # that no assignment names or an assignment that names no record.
        self.state_path = self.root / "state.json"
        self.lock_path = self.root / "state.lock"
        self.journal_path = self.root / "events.jsonl"
        self.assignment_root = self.root / "assignments"
        if self.state_path == _REPOSITORY_ROOT or self.state_path.is_relative_to(_REPOSITORY_ROOT):
            raise DecompositionSessionPoolError("pool state must be stored outside the repository working tree")
        self.clock = clock
        self.identity_factory = identity_factory
        self.host_identity = host_identity or socket.gethostname()
        self._liveness_holds: dict[str, BinaryIO] = {}

    # ------------------------------------------------------------ persistence

    def liveness_path(self, run_id: str) -> Path:
        return self.assignment_root / f"{run_id}.alive"

    def checkout_identity(self) -> str:
        try:
            payload = self.manifest_path.read_bytes()
        except OSError as exc:
            raise DecompositionSessionPoolError(
                f"external checkout identity manifest is unreadable: {self.manifest_path}"
            ) from exc
        return CHECKOUT_IDENTITY_PREFIX + hashlib.sha256(payload).hexdigest()

    def _load(self, events: list[dict[str, Any]]) -> tuple[DurableSessionPool, dict[str, Any]]:
        """Load the one durable document and refuse any internal disagreement."""

        if not self.state_path.exists():
            pool = DurableSessionPool(
                lifetime=DECOMPOSITION_SESSION_LIFETIME, clock=self.clock,
                identity_factory=self.identity_factory, event_sink=events.append,
            )
            return pool, {"schema_version": DECOMPOSITION_OWNER_SCHEMA_VERSION, "assignments": {}}
        try:
            value = strict_json(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            raise DecompositionSessionPoolError(
                f"decomposition pool state is unreadable or malformed: {type(exc).__name__}"
            ) from exc
        if (
            not isinstance(value, Mapping)
            or set(value) != {"schema_version", "pool", "assignments"}
            or value["schema_version"] != DECOMPOSITION_OWNER_SCHEMA_VERSION
            or not isinstance(value["assignments"], Mapping)
        ):
            raise DecompositionSessionPoolError("decomposition pool state differs from schema")
        pool = DurableSessionPool.from_dict(
            value["pool"], lifetime=DECOMPOSITION_SESSION_LIFETIME, clock=self.clock,
            identity_factory=self.identity_factory, event_sink=events.append,
        )
        assignments = {"schema_version": DECOMPOSITION_OWNER_SCHEMA_VERSION, "assignments": dict(value["assignments"])}
        active_leases: dict[str, str] = {}
        for run_id, assignment in assignments["assignments"].items():
            if not isinstance(assignment, Mapping) or assignment.get("status") not in _ASSIGNMENT_STATUSES:
                raise DecompositionSessionPoolError(f"decomposition assignment {run_id} is malformed")
            if assignment["status"] != "active":
                continue
            for value_lease in assignment["leases"].values():
                lease_id = value_lease.get("lease_id") if isinstance(value_lease, Mapping) else None
                if type(lease_id) is not str or lease_id in active_leases:
                    raise DecompositionSessionPoolError(f"decomposition assignment {run_id} lease ledger is malformed")
                active_leases[lease_id] = run_id
        for record in pool.sessions_for("active"):
            assert record.active_lease is not None
            if record.active_lease.lease_id not in active_leases:
                raise DecompositionSessionPoolError(
                    "decomposition pool holds an active lease no assignment names; the state is corrupt"
                )
        return pool, assignments

    def _transaction(self, mutate: Callable[[DurableSessionPool, dict[str, Any]], Any]) -> Any:
        events: list[dict[str, Any]] = []
        with _exclusive_file_lock(self.lock_path):
            try:
                pool, assignments = self._load(events)
                result = mutate(pool, assignments)
                document = {
                    "schema_version": DECOMPOSITION_OWNER_SCHEMA_VERSION,
                    "pool": pool.to_dict(),
                    "assignments": assignments["assignments"],
                }
                _write_verified(self.state_path, _json_bytes(document))
            except DurableSessionPoolError as exc:
                raise DecompositionSessionPoolError(str(exc)) from exc
            stamp = utc_text(self.clock())
            for event in events:
                event.update({"at": stamp, "owner": "decomposition"})
                try:
                    append_journal_line(self.journal_path, event)
                except OSError as exc:
                    raise DecompositionSessionPoolError(
                        f"decomposition session journal could not be appended: {exc}"
                    ) from exc
        return result

    # --------------------------------------------------------------- scopes

    def scope_for(self, provider_name: str, role: str) -> SessionScope | None:
        """The exact scope for one provider/role pair, or None when it cannot pool."""

        if role not in DECOMPOSITION_SESSION_ROLES or provider_name not in self.provider_models:
            raise DecompositionSessionPoolError(f"unsupported decomposition scope {provider_name}:{role}")
        model, effort = self.provider_models[provider_name]
        resume_contract = None
        if provider_name == "codex":
            if self.codex_resume_activation is None:
                return None
            resume_contract = self.codex_resume_activation.fingerprint
        return SessionScope(
            protocol_version=DECOMPOSITION_SESSION_PROTOCOL_VERSION,
            provider_identifier=PROVIDER_IDENTIFIERS[provider_name],
            role=role,
            session_class="worker",
            workload_class="deep",
            model=model,
            reasoning_effort=effort,
            repository_identity=self.repository_identity,
            resume_contract=resume_contract,
            bindings=(conversation_store_binding(self.compose_project, provider_name),),
        )

    # ---------------------------------------------------------------- prepare

    def prepare(
        self,
        *,
        run_id: str,
        task_id: str,
        decomposition_mode: str,
        provider_order: tuple[str, ...],
        max_calls: int,
        source_commit: str,
        worker_id: str,
    ) -> dict[str, Any]:
        """Durably reserve every reachable role session for one exact run."""

        task_id = validate_task_id(task_id)
        if type(run_id) is not str or _RUN_ID.fullmatch(run_id) is None:
            raise DecompositionSessionPoolError("pooled run_id has an invalid form")
        if type(source_commit) is not str or _COMMIT.fullmatch(source_commit) is None:
            raise DecompositionSessionPoolError("pooled source_commit must be exact")
        if type(worker_id) is not str or not worker_id.strip():
            raise DecompositionSessionPoolError("worker_id must be non-empty")
        keys = possible_lease_keys(
            decomposition_mode=decomposition_mode, provider_order=tuple(provider_order), max_calls=max_calls,
        )
        checkout_identity = self.checkout_identity()
        source_tree = self._source_tree(source_commit)
        skipped: list[str] = []
        acquired_here: list[str] = []

        def mutate(pool: DurableSessionPool, assignments: dict[str, Any]) -> dict[str, Any]:
            self._reclaim_stranded(pool, assignments)
            if run_id in assignments["assignments"]:
                raise DecompositionSessionPoolError(f"pooled decomposition run already exists: {run_id}")
            moment = pool.clock()
            leases: dict[str, SessionLease] = {}
            for key in keys:
                provider_name, role = key.split(":", 1)
                scope = self.scope_for(provider_name, role)
                if scope is None:
                    skipped.append(key)
                    continue
                leases[key] = pool.checkout(
                    scope=scope,
                    assignment={
                        "run_id": run_id, "task_id": task_id, "decomposition_mode": decomposition_mode,
                        "source_commit": source_commit, "source_tree": source_tree,
                        "checkout_identity": checkout_identity,
                        "worker_id": worker_id, "host": self.host_identity, "platform": os.name,
                    },
                    now=moment, allow_probation_retry=True,
                )
            if not leases:
                raise DecompositionSessionPoolError(
                    "no decomposition session could be reserved: every reachable provider "
                    "requires an unavailable resume control"
                )
            bundle_path = self.assignment_root / f"{run_id}.leases.json"
            bundle = {
                "schema_version": DECOMPOSITION_LEASE_BUNDLE_SCHEMA_VERSION,
                "run_id": run_id,
                "task_id": task_id,
                "decomposition_mode": decomposition_mode,
                "source_commit": source_commit,
                "repository_identity": self.repository_identity,
                "checkout_identity": checkout_identity,
                "leases": {key: lease.to_dict() for key, lease in leases.items()},
                "codex_resume_sandbox_argument": (
                    None if self.codex_resume_activation is None
                    else list(self.codex_resume_activation.argument)
                ),
            }
            try:
                _write_verified(bundle_path, _json_bytes(bundle))
            except Exception as exc:
                raise DecompositionSessionPoolError(f"lease bundle could not be written: {exc}") from exc
            liveness_path = self.liveness_path(run_id)
            try:
                held = _acquire_liveness_lock(liveness_path)
            except OSError as exc:
                raise DecompositionSessionPoolError(f"pooled run liveness could not be established: {exc}") from exc
            liveness_identity = _file_identity(held)
            if liveness_identity is None:
                _release_liveness_lock(held)
                raise DecompositionSessionPoolError("pooled run liveness file identity is unavailable")
            self._liveness_holds[run_id] = held
            acquired_here.append(run_id)
            assignments["assignments"][run_id] = {
                "run_id": run_id,
                "task_id": task_id,
                "decomposition_mode": decomposition_mode,
                "provider_order": list(provider_order),
                "max_calls": max_calls,
                "source_commit": source_commit,
                "source_tree": source_tree,
                "checkout_identity": checkout_identity,
                "repository_identity": self.repository_identity,
                "worker_id": worker_id,
                "leases": {key: lease.to_dict() for key, lease in leases.items()},
                "skipped_keys": list(skipped),
                "lease_bundle_path": str(bundle_path),
                "status": "active",
                "settlement": None,
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
            return {
                "run_id": run_id,
                "repository_identity": self.repository_identity,
                "compose_project": self.compose_project,
                "checkout_identity": checkout_identity,
                "lease_bundle_path": str(bundle_path),
                "leases": {key: lease.to_dict() for key, lease in leases.items()},
                "skipped_keys": list(skipped),
                "provider_environment": {
                    "NSC_CLAUDE_MODEL": self.provider_models.get("claude", ("", None))[0],
                    "NSC_OPENAI_CODEX_MODEL": self.provider_models.get("codex", ("", None))[0],
                },
            }

        try:
            return self._transaction(mutate)
        except BaseException:
            # Only a lock this call took is released: a refused duplicate run
            # id must never drop the liveness of the run that already owns it.
            if run_id in acquired_here:
                self.release_liveness(run_id=run_id)
            raise

    def _reclaim_stranded(self, pool: DurableSessionPool, assignments: dict[str, Any]) -> list[dict[str, Any]]:
        """Retire every lease of every provably unowned run as interrupted."""

        reclaimed: list[dict[str, Any]] = []
        for run_id, assignment in sorted(assignments["assignments"].items()):
            if assignment["status"] != "active" or run_id in self._liveness_holds:
                continue
            verdict, detail = _probe_liveness(assignment.get("liveness"), host=self.host_identity)
            if verdict != "unowned":
                continue
            for key, value in sorted(assignment["leases"].items()):
                lease = SessionLease.from_dict(value)
                if pool.is_settled(lease.lease_id):
                    continue
                pool.retire_interrupted(lease, detail=f"stranded run {run_id} has no owning controller: {detail}")
            assignment["status"] = "stranded"
            reclaimed.append({"run_id": run_id, "reason": detail})
        return reclaimed

    def _source_tree(self, source_commit: str) -> str:
        """Bind the checkout's exact tree, refusing a checkout not at the admitted commit."""

        try:
            head = subprocess.run(
                ("git", "rev-parse", "--verify", "HEAD"), cwd=str(self.checkout),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=30.0,
            ).stdout.decode("utf-8").strip()
            tree = subprocess.run(
                ("git", "rev-parse", "HEAD^{tree}"), cwd=str(self.checkout),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=30.0,
            ).stdout.decode("utf-8").strip()
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
            raise DecompositionSessionPoolError("task checkout source identity could not be read") from exc
        if head != source_commit:
            raise DecompositionSessionPoolError(
                f"task checkout HEAD {head} is not the admitted source commit {source_commit}"
            )
        if _COMMIT.fullmatch(tree) is None:
            raise DecompositionSessionPoolError("task checkout tree identity is invalid")
        return tree

    def cancel_unstarted(self, *, run_id: str) -> None:
        """Return every lease of one run after a proven provider-start failure.

        Only the owner still holding the run's liveness lock may say the
        provider never started; the leases are returned uncharged and the run
        is recorded as cancelled instead of being reclaimed later as stranded.
        """

        if run_id not in self._liveness_holds:
            raise DecompositionSessionPoolError(
                f"only the owner holding run {run_id} may cancel it as unstarted"
            )

        def mutate(pool: DurableSessionPool, assignments: dict[str, Any]) -> None:
            assignment = assignments["assignments"].get(run_id)
            if assignment is None or assignment["status"] != "active":
                return
            for value in assignment["leases"].values():
                lease = SessionLease.from_dict(value)
                if not pool.is_settled(lease.lease_id):
                    pool.cancel(lease)
            assignment["status"] = "cancelled"

        try:
            self._transaction(mutate)
        finally:
            self.release_liveness(run_id=run_id)

    def release_liveness(self, *, run_id: str) -> None:
        held = self._liveness_holds.pop(run_id, None)
        if held is not None:
            _release_liveness_lock(held)

    def close(self) -> None:
        for run_id in list(self._liveness_holds):
            self.release_liveness(run_id=run_id)

    # ----------------------------------------------------------------- settle

    def settle(self, *, run_id: str, run_dir: Path | str) -> dict[str, Any]:
        """Settle every lease of one run from its durable artifacts, exactly once."""

        if type(run_id) is not str or _RUN_ID.fullmatch(run_id) is None:
            raise DecompositionSessionPoolError("pooled run_id has an invalid form")
        root = Path(run_dir)

        def mutate(pool: DurableSessionPool, assignments: dict[str, Any]) -> dict[str, Any]:
            assignment = assignments["assignments"].get(run_id)
            if assignment is None:
                raise DecompositionSessionPoolError(f"no pooled decomposition run is recorded: {run_id}")
            if assignment["status"] == "settled":
                return dict(assignment["settlement"])
            if assignment["status"] != "active":
                raise DecompositionSessionPoolError(f"pooled decomposition run {run_id} is {assignment['status']}")
            try:
                result = strict_json((root / "decomposition_run_result.json").read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError, RecursionError) as exc:
                raise DecompositionSessionPoolError(
                    f"decomposition run result is unreadable or malformed: {type(exc).__name__}"
                ) from exc
            if not isinstance(result, Mapping) or result.get("run_id") != run_id or result.get("task_id") != assignment["task_id"]:
                raise DecompositionSessionPoolError("decomposition run result names another run or task")
            summaries = result.get("pooled_sessions")
            if not isinstance(summaries, Mapping):
                raise DecompositionSessionPoolError("decomposition run result carries no pooled_sessions summary")
            outcomes: dict[str, Any] = {}
            for key, value in sorted(assignment["leases"].items()):
                lease = SessionLease.from_dict(value)
                summary = summaries.get(key)
                if pool.is_settled(lease.lease_id):
                    outcomes[key] = {"state": "already_settled"}
                    continue
                if not isinstance(summary, Mapping) or summary.get("lease_id") != lease.lease_id:
                    record = pool.check_in(
                        lease=lease,
                        settlement=self._settlement(lease, "identity_failure", None, None, {}, "run result does not describe this lease"),
                    )
                elif summary.get("invoked") is not True:
                    record = pool.cancel(lease)
                    outcomes[key] = {"state": None if record is None else record.state, "invoked": False}
                    continue
                else:
                    record = pool.check_in(lease=lease, settlement=self._settle_lease(lease, key, assignment, result, summary, root))
                outcomes[key] = {
                    "state": record.state,
                    "invoked": True,
                    "session_id": record.session_id,
                    "completed_assignment_count": record.completed_assignment_count,
                    "retirement_reason": record.retirement_reason,
                    "quarantine_reason": record.quarantine_reason,
                }
            settlement = {"run_id": run_id, "run_status": result.get("run_status"), "leases": outcomes}
            assignment["status"] = "settled"
            assignment["settlement"] = settlement
            return settlement

        try:
            return self._transaction(mutate)
        finally:
            self.release_liveness(run_id=run_id)

    def _settlement(
        self,
        lease: SessionLease,
        outcome: str,
        confirmed: ProviderSessionConfirmation | None,
        percent: int | None,
        evidence: Mapping[str, str],
        detail: str,
    ) -> AssignmentSettlement:
        return AssignmentSettlement(
            pool_schema_version=DURABLE_SESSION_POOL_SCHEMA_VERSION,
            lease_id=lease.lease_id, record_id=lease.record_id, outcome=outcome,
            confirmed_session=confirmed, known_context_window_percent=percent,
            evidence=dict(evidence), detail=detail,
        )

    def _settle_lease(
        self,
        lease: SessionLease,
        key: str,
        assignment: Mapping[str, Any],
        result: Mapping[str, Any],
        summary: Mapping[str, Any],
        root: Path,
    ) -> AssignmentSettlement:
        """Prove one lease's rounds from their artifacts; anything unproven withdraws it."""

        unproven = summary.get("identity_unproven")
        if unproven is not None:
            # An earlier round may have proven this conversation, but a later
            # round asked to resume it and proved nothing: the provider may or
            # may not have received that turn, so the conversation is retired
            # as uncertain rather than returned.
            confirmed_value = summary.get("confirmed_session")
            confirmed: ProviderSessionConfirmation | None = None
            if confirmed_value is not None:
                try:
                    confirmed = confirmation_from_dict(confirmed_value)
                except DurableSessionPoolError:
                    confirmed = None
            return self._settlement(
                lease, "uncertain", confirmed, None, {},
                f"a later round proved no identity: {str(unproven)[:300]}",
            )
        confirmed_value = summary.get("confirmed_session")
        if confirmed_value is None:
            return self._settlement(lease, "identity_failure", None, None, {}, "the run proved no session identity for this lease")
        try:
            confirmed = confirmation_from_dict(confirmed_value)
        except DurableSessionPoolError as exc:
            return self._settlement(lease, "identity_failure", None, None, {}, f"malformed confirmation: {exc}")
        rounds = summary.get("rounds")
        if not isinstance(rounds, list) or not rounds:
            return self._settlement(lease, "identity_failure", None, None, {}, "the run recorded no round evidence for this lease")
        provider_name, role = key.split(":", 1)
        model, effort = self.provider_models[provider_name]
        expected = {
            "schema_version": POOLED_ROUND_EVIDENCE_SCHEMA_VERSION,
            "pool_schema_version": DURABLE_SESSION_POOL_SCHEMA_VERSION,
            "protocol_version": DECOMPOSITION_SESSION_PROTOCOL_VERSION,
            "lease_key": key,
            "lease_id": lease.lease_id,
            "record_id": lease.record_id,
            "task_id": assignment["task_id"],
            "run_id": assignment["run_id"],
            "decomposition_mode": assignment["decomposition_mode"],
            "role": role,
            "provider_name": provider_name,
            "provider_identifier": PROVIDER_IDENTIFIERS[provider_name],
            "model": model,
            "reasoning_effort": effort,
            "repository_identity": self.repository_identity,
            "conversation_store": conversation_store_binding(self.compose_project, provider_name)[1],
            "source_head": assignment["source_commit"],
            "checkout_identity": assignment["checkout_identity"],
        }
        outcome = "completed"
        last_usage: Any = None
        evidence: dict[str, str] = {}
        seen_rounds: set[int] = set()
        for index, round_evidence in enumerate(rounds):
            if not isinstance(round_evidence, Mapping) or set(round_evidence) != set(POOLED_ROUND_EVIDENCE_FIELDS):
                return self._settlement(lease, "identity_failure", None, None, {}, f"round evidence {index} fields drifted from the schema")
            for name, value in expected.items():
                if round_evidence.get(name) != value:
                    return self._settlement(
                        lease, "identity_failure", None, None, {},
                        f"round evidence {index} {name} disagrees with the lease: {round_evidence.get(name)!r}",
                    )
            # Every round of one lease must have proven the same conversation:
            # the first with the mode the lease requested, every later one as
            # a resume of exactly that thread.
            round_confirmed = round_evidence["confirmed_session"]
            if not isinstance(round_confirmed, Mapping) or (
                round_confirmed.get("session_id") != confirmed.session_id
                or round_confirmed.get("provider_identifier") != confirmed.provider_identifier
                or round_confirmed.get("role") != confirmed.role
            ):
                return self._settlement(lease, "identity_failure", None, None, {}, f"round evidence {index} proved a different conversation")
            if index == 0:
                if (
                    round_evidence["requested_mode"] != lease.mode
                    or round_evidence["requested_session_id"] != lease.session_id
                    or round_confirmed.get("mode") != lease.mode
                ):
                    return self._settlement(lease, "identity_failure", None, None, {}, "first round did not request the leased session")
            elif (
                round_evidence["requested_mode"] != "resume"
                or round_evidence["requested_session_id"] != confirmed.session_id
                or round_confirmed.get("mode") != "resume"
            ):
                return self._settlement(lease, "identity_failure", None, None, {}, "a later round did not resume the confirmed session")
            round_number = round_evidence["round_number"]
            if (
                type(round_number) is not int or isinstance(round_number, bool)
                or round_number < 1 or round_number > int(assignment["max_calls"])
                or round_number in seen_rounds
            ):
                return self._settlement(lease, "identity_failure", None, None, {}, "round number is invalid, repeated, or beyond the call limit")
            seen_rounds.add(round_number)
            if round_evidence["source_tree"] != assignment["source_tree"]:
                return self._settlement(lease, "identity_failure", None, None, {}, f"round {round_number} source tree disagrees with the admitted checkout")
            # The invocation identity is deterministic from task, run, round,
            # and role, so the host recomputes it instead of trusting the
            # container's copy; the AgentRuntime artifact it names must then
            # exist and agree on run, role, provider, model, and status.
            mode = assignment["decomposition_mode"]
            expected_invocation = (
                d1b1_invocation_id(assignment["task_id"], assignment["run_id"])
                if mode == "d1b1"
                else d1b2_invocation_id(assignment["task_id"], assignment["run_id"], round_number, role)
            )
            if round_evidence["invocation_id"] != expected_invocation:
                return self._settlement(
                    lease, "identity_failure", None, None, {},
                    f"round {round_number} invocation id is not the one this task, run, round, and role determine",
                )
            runtime_result = self._runtime_result(root, mode, round_number, expected_invocation)
            if runtime_result is None:
                return self._settlement(lease, "identity_failure", None, None, {}, f"round {round_number} has no readable AgentRuntime result")
            for name, value in (
                ("run_id", expected_invocation), ("role", role),
                ("provider", PROVIDER_IDENTIFIERS[provider_name]), ("model", model),
            ):
                if runtime_result.get(name) != value:
                    return self._settlement(
                        lease, "identity_failure", None, None, {},
                        f"round {round_number} AgentRuntime result {name} disagrees with the lease",
                    )
            runtime_status = runtime_result.get("status")
            if (runtime_status == "succeeded") != (round_evidence["agent_status"] == "succeeded"):
                return self._settlement(
                    lease, "identity_failure", None, None, {},
                    f"round {round_number} evidence agent status disagrees with the AgentRuntime result",
                )
            round_result = self._round_result(root, mode, round_number, result)
            if round_result is None or round_result.get("pooled_session") != dict(round_evidence):
                return self._settlement(
                    lease, "identity_failure", None, None, {},
                    f"round {round_number} artifact does not carry this exact evidence block",
                )
            artifact_path = round_evidence["artifact_path"]
            artifact_sha256 = round_evidence["artifact_sha256"]
            if artifact_path is not None:
                if type(artifact_path) is not str or type(artifact_sha256) is not str or _SHA256.fullmatch(artifact_sha256) is None:
                    return self._settlement(lease, "identity_failure", None, None, {}, "artifact binding is malformed")
                candidate = root / artifact_path
                try:
                    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
                except OSError:
                    return self._settlement(lease, "identity_failure", None, None, {}, f"artifact is missing: {artifact_path}")
                if digest != artifact_sha256:
                    return self._settlement(lease, "identity_failure", None, None, {}, f"artifact hash mismatch: {artifact_path}")
                evidence[f"round_{round_number}_artifact_sha256"] = artifact_sha256
            evidence[f"round_{round_number}_invocation_id"] = str(round_evidence["invocation_id"])
            round_outcome = _ROUND_STATUS_OUTCOMES.get(str(round_evidence["round_status"]), "output_failure")
            if runtime_status != "succeeded":
                classification = runtime_result.get("failure_classification")
                round_outcome = _FAILURE_CLASSIFICATION_OUTCOMES.get(str(classification), "uncertain")
            if round_outcome != "completed":
                outcome = round_outcome if outcome == "completed" else outcome
            last_usage = runtime_result.get("usage")
        percent = context_window_percent(last_usage, self.context_window_tokens)
        return self._settlement(lease, outcome, confirmed, percent, evidence, f"{len(rounds)} pooled round(s) settled")

    @staticmethod
    def _round_result(root: Path, mode: str, round_number: int, result: Mapping[str, Any]) -> Mapping[str, Any] | None:
        if mode == "d1b1":
            evidence = result.get("pooled_session_evidence")
            return None if not isinstance(evidence, Mapping) else {"pooled_session": evidence, "agent_failure_classification": result.get("agent_failure_classification")}
        path = root / "rounds" / f"{round_number:02d}" / "round_result.json"
        try:
            value = strict_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, RecursionError):
            return None
        return value if isinstance(value, Mapping) else None

    @staticmethod
    def _runtime_result(root: Path, mode: str, round_number: int, invocation_id: str) -> Mapping[str, Any] | None:
        relative = (
            Path("agent_runtime") / invocation_id / "result.json"
            if mode == "d1b1"
            else Path("rounds") / f"{round_number:02d}" / "agent_runtime" / invocation_id / "result.json"
        )
        try:
            value = strict_json((root / relative).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, RecursionError):
            return None
        return value if isinstance(value, Mapping) else None

    # ------------------------------------------------------------- inspection

    def records(self) -> tuple[SessionRecord, ...]:
        with _exclusive_file_lock(self.lock_path):
            try:
                pool, _assignments = self._load([])
            except DurableSessionPoolError as exc:
                raise DecompositionSessionPoolError(str(exc)) from exc
        return pool.sessions

    def assignments(self) -> dict[str, Any]:
        with _exclusive_file_lock(self.lock_path):
            try:
                _pool, assignments = self._load([])
            except DurableSessionPoolError as exc:
                raise DecompositionSessionPoolError(str(exc)) from exc
        return assignments["assignments"]


__all__ = [
    "CHECKOUT_IDENTITY_PREFIX",
    "DECOMPOSITION_CONTEXT_WINDOW_ENVIRONMENT",
    "DECOMPOSITION_OWNER_SCHEMA_VERSION",
    "DECOMPOSITION_SESSION_IDLE_LIFETIME_SECONDS",
    "DECOMPOSITION_SESSION_LIFETIME",
    "DECOMPOSITION_SESSION_MAX_AGE_SECONDS",
    "DecompositionSessionPoolError",
    "DecompositionSessionPoolOwner",
    "context_window_percent",
    "possible_lease_keys",
]
