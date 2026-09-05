"""Durable host owner for one task-scoped, resumable Codex supervisor conversation.

Every judgment turn of the goal supervisor used to be an ephemeral Codex CLI
process: `codex_supervisor_turn.py` built a fresh conversation, paid for the
complete prompt, and threw the conversation away. This owner keeps that
conversation's *identity* durable so separate `codex_supervisor_turn`
subprocesses -- across turns of one worker, across the worker returning at
`human_action_required`, and across the later delivery/merge-closeout worker
for the same task -- resume the exact same provider thread. Pooling means a
resumable conversation, never a live process or container.

The owner is deliberately narrow.

Task-bound compatibility. The :class:`SessionScope` binds the crew/session
protocol, the ``task_supervisor`` role, the ``openai-codex`` provider, the
exact model, the reasoning effort, the repository identity, the fingerprint of
the exact operator-verified Codex resume control, *and the task ID*. A
different task, model, effort, repository, protocol, or resume control can
never inherit the conversation: the scope key differs, so the owner cold-starts
and retires the incompatible record explicitly.

Adopt on confirm. Codex assigns its thread UUID only after the first call, so
a cold lease carries no identity. The conversation becomes poolable only when
the container's `provider_session_confirmation` -- the exact `thread.started`
identity the AgentRuntime adapter proved from the transcript -- reaches
:meth:`SupervisorSessionOwner.finish_turn`. A missing, malformed, or
mismatched confirmation quarantines the conversation; exit code 0 proves
nothing.

Explicit activation. Codex `exec resume` does not accept `--sandbox`, so the
adapter refuses to resume unless an operator supplies a verified argument that
reproduces the pinned `--sandbox danger-full-access` policy through an option
resume does accept. Warm pooling is therefore *off* unless that exact argument
is supplied (``NSC_CODEX_RESUME_SANDBOX_ARGUMENT`` or the worker's explicit
flag). With the gate off the worker constructs no owner and every turn stays
the historical ephemeral turn; an owner constructed without an activation
never binds a session, retires any conversation an earlier activation left
behind, and reports ``warm_pooling_active: false`` on every turn. Nothing here
claims warm pooling that is not happening.

One exact active lease. The owner holds one operating-system liveness lock per
task for the whole worker process. A second live owner for the same task fails
closed at construction. A stranded active lease -- an earlier owner that died
mid-turn -- is reconciled only by the owner that now holds that exact lock, on
the same host and platform, and only by retiring the conversation as
interrupted. It is never resumed.

Bounded lifetime. One paid judgment turn is one completed lifecycle cycle of
the committed AgentRuntime policy (architect class: 100 completed cycles, two
consecutive provider/output failures, or a known context-window utilization at
the committed threshold retire the conversation). Context utilization is known
only when the operator states the model's context window explicitly
(``NSC_TASK_SUPERVISOR_CONTEXT_WINDOW_TOKENS``); it is computed from the exact
input token count Codex reported for the turn and is otherwise unknown. Age and
idle bounds are stated below and never apply to an active assignment.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
from typing import Any, BinaryIO, Callable, Iterable, Mapping, Sequence

from Pipeline.AgentRuntime.durable_session_pool import (
    DURABLE_SESSION_POOL_SCHEMA_VERSION,
    AssignmentSettlement,
    DurableSessionPool,
    DurableSessionPoolError,
    DurableSessionPoolStore,
    SessionLease,
    SessionLifetimePolicy,
    SessionRecord,
    SessionScope,
    append_journal_line,
    authority_capsule,
    confirmation_from_dict,
    resume_contract_fingerprint,
    utc_now,
    utc_text,
)
from Pipeline.AgentRuntime.provider_sessions import ProviderSessionConfirmation

from .contracts import TaskReviewContractError, validate_task_id
from .execution_session_pool import (
    _acquire_liveness_lock,
    _exclusive_file_lock,
    _file_identity,
    _release_liveness_lock,
)


SUPERVISOR_SESSION_PROTOCOL_VERSION = "1.0"
SUPERVISOR_SESSION_ROLE = "task_supervisor"
SUPERVISOR_SESSION_PROVIDER = "openai-codex"
# A human validation cycle can span days, so a returned supervisor conversation
# waits a week for its next turn; nothing survives two weeks from creation.
SUPERVISOR_SESSION_MAX_AGE_SECONDS = 14 * 24 * 3600
SUPERVISOR_SESSION_IDLE_LIFETIME_SECONDS = 7 * 24 * 3600
SUPERVISOR_SESSION_LIFETIME = SessionLifetimePolicy(
    max_age_seconds=SUPERVISOR_SESSION_MAX_AGE_SECONDS,
    idle_lifetime_seconds=SUPERVISOR_SESSION_IDLE_LIFETIME_SECONDS,
)
CODEX_RESUME_SANDBOX_ARGUMENT_ENVIRONMENT = "NSC_CODEX_RESUME_SANDBOX_ARGUMENT"
SUPERVISOR_CONTEXT_WINDOW_ENVIRONMENT = "NSC_TASK_SUPERVISOR_CONTEXT_WINDOW_TOKENS"
# A provider conversation lives in the container's configuration volume,
# which Docker Compose names from the project it runs under. A session
# started under one project cannot be resumed under another, so the store
# is part of a pooled conversation's identity, never an ambient default.
COMPOSE_PROJECT_ENVIRONMENT = "NSC_TASK_AGENT_COMPOSE_PROJECT"
DEFAULT_COMPOSE_PROJECT = "nosafecircle"
CONVERSATION_STORE_BINDING = "conversation_store"
CONVERSATION_STORE_VOLUMES = {"claude": "claude-config", "codex": "codex-config"}
CODEX_RESUME_GATE_OFF_REASON = (
    "codex exec resume cannot reproduce the pinned '--sandbox danger-full-access' "
    "policy without an operator-verified argument; no verified "
    f"{CODEX_RESUME_SANDBOX_ARGUMENT_ENVIRONMENT} was supplied, so supervisor "
    "turns stay ephemeral and no conversation is pooled"
)
# The resume control reproduces the pinned sandbox policy through the one
# channel `codex exec resume` accepts for it: `-c`/`--config` overrides of
# sandbox configuration keys. Nothing else is a sandbox control: `--sandbox`
# is not accepted by resume at all, `--last` selects a session by recency,
# `--all` widens session lookup beyond the current working directory,
# `--ephemeral` discards the session files a resume needs, the bypass flag is
# a wider policy, and working-directory, approval, profile, or feature flags
# would widen what the resumed turn may do beyond what the start had.
_RESUME_CONFIG_FLAGS = frozenset({"-c", "--config"})
_RESUME_CONFIG_KEY = re.compile(r"^sandbox[a-z0-9_.]*=.+$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_SLOT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
# Docker Compose project names: lowercase letters, digits, dashes, and
# underscores, starting with a letter or digit.
_COMPOSE_PROJECT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_FAILURE_OUTCOMES = {
    "ProviderFailure": "provider_failure",
    "ProviderOutputInvalid": "output_failure",
    "ProviderRequestRejected": "other_failure",
    "ProviderPermissionDenied": "provider_failure",
    "ProviderBudgetExhausted": "provider_failure",
    "ProviderTimeout": "uncertain",
    "ProviderTransportError": "uncertain",
}


class SupervisorSessionPoolError(TaskReviewContractError):
    """The supervisor session contract or persisted identity was invalid."""


@dataclass(frozen=True)
class CodexResumeActivation:
    """The exact operator-verified argv fragment that makes Codex resume safe.

    The value is never inferred. It arrives only from the operator, is
    validated for shape, and is fingerprinted into every session's scope so a
    conversation started under one control is never resumed under another.
    """

    argument: tuple[str, ...]

    def __post_init__(self) -> None:
        parts = self.argument
        if (
            type(parts) is not tuple
            or not parts
            or any(type(part) is not str or not part or part != part.strip() for part in parts)
        ):
            raise SupervisorSessionPoolError(
                "the Codex resume control must be a non-empty tuple of non-empty unpadded strings"
            )
        if len(parts) % 2 != 0:
            raise SupervisorSessionPoolError(
                "the Codex resume control must be `-c`/`--config` flag and "
                "`sandbox...=value` pairs, for example "
                '("-c", \'sandbox_mode="danger-full-access"\')'
            )
        for flag, value in zip(parts[0::2], parts[1::2]):
            if flag not in _RESUME_CONFIG_FLAGS:
                raise SupervisorSessionPoolError(
                    f"the Codex resume control may not contain {flag!r}: only `-c`/"
                    "`--config` sandbox overrides reproduce the pinned sandbox policy "
                    "through an option `codex exec resume` accepts"
                )
            if _RESUME_CONFIG_KEY.fullmatch(value) is None or _UUID.fullmatch(value):
                raise SupervisorSessionPoolError(
                    f"the Codex resume control value {value!r} must be one "
                    "`sandbox...=value` configuration override"
                )

    @classmethod
    def parse(cls, text: str) -> "CodexResumeActivation":
        """Parse the operator's JSON array of argv fragments."""

        try:
            value = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise SupervisorSessionPoolError(
                "the Codex resume control must be a JSON array of argv strings, for example "
                '["-c", "sandbox_mode=\\"danger-full-access\\""]'
            ) from exc
        if not isinstance(value, list):
            raise SupervisorSessionPoolError("the Codex resume control must be a JSON array of argv strings")
        return cls(tuple(value))

    @property
    def fingerprint(self) -> str:
        digest = resume_contract_fingerprint(self.argument)
        assert digest is not None
        return digest

    def to_dict(self) -> dict[str, Any]:
        return {"argument": list(self.argument), "fingerprint": self.fingerprint}


def codex_resume_activation_from_environment(
    environ: Mapping[str, str] | None = None,
) -> CodexResumeActivation | None:
    """Return the operator's resume control, or ``None`` when the gate is off."""

    source = os.environ if environ is None else environ
    raw = source.get(CODEX_RESUME_SANDBOX_ARGUMENT_ENVIRONMENT)
    if raw is None or not raw.strip():
        return None
    return CodexResumeActivation.parse(raw)


def context_window_tokens_from_environment(
    environ: Mapping[str, str] | None = None,
) -> int | None:
    """Return the operator-stated model context window, or ``None`` (unknown)."""

    source = os.environ if environ is None else environ
    raw = source.get(SUPERVISOR_CONTEXT_WINDOW_ENVIRONMENT)
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise SupervisorSessionPoolError(
            f"{SUPERVISOR_CONTEXT_WINDOW_ENVIRONMENT} must be a positive integer token count"
        ) from exc
    return validate_context_window_tokens(value)


def validate_context_window_tokens(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or type(value) is not int or value < 1000:
        raise SupervisorSessionPoolError(
            "the supervisor context window must be an explicit integer of at least 1000 tokens"
        )
    return value


def known_context_window_percent(usage: Any, window_tokens: int | None) -> int | None:
    """Derive utilization only from the exact reported input tokens and an explicit window."""

    if window_tokens is None or not isinstance(usage, Mapping):
        return None
    tokens = usage.get("input_tokens")
    if isinstance(tokens, bool) or type(tokens) is not int or tokens < 0:
        return None
    return min(100, (tokens * 100) // window_tokens)


def classify_turn_failure(classification: Any) -> str:
    """Map the container's provider exception name onto a settlement outcome."""

    if type(classification) is str and classification in _FAILURE_OUTCOMES:
        return _FAILURE_OUTCOMES[classification]
    return "uncertain"


def resolve_compose_project(compose_project: Any = None) -> str:
    """Return the exact Docker Compose project a provider container runs under.

    The explicit value wins, then ``NSC_TASK_AGENT_COMPOSE_PROJECT``, then the
    repository default. The same resolution builds the provider and the pool
    owner, so the two can never disagree silently about where a conversation
    lives.
    """

    value = (
        str(compose_project).strip()
        if compose_project
        else os.getenv(COMPOSE_PROJECT_ENVIRONMENT, "").strip() or DEFAULT_COMPOSE_PROJECT
    )
    if _COMPOSE_PROJECT.fullmatch(value) is None:
        raise SupervisorSessionPoolError(
            f"compose project {value!r} is not a valid Docker Compose project name"
        )
    return value


def conversation_store_binding(compose_project: str, provider_name: str) -> tuple[str, str]:
    """The scope binding naming the exact volume a provider's sessions live in."""

    project = resolve_compose_project(compose_project)
    try:
        volume = CONVERSATION_STORE_VOLUMES[provider_name]
    except KeyError:
        raise SupervisorSessionPoolError(
            f"no conversation store volume is known for provider {provider_name!r}"
        ) from None
    return (CONVERSATION_STORE_BINDING, f"compose:{project}/{volume}")


def gate_off_activation_state(task_id: str) -> dict[str, Any]:
    """The truthful pool report for a worker that never activated the gate."""

    return {
        "schema_version": DURABLE_SESSION_POOL_SCHEMA_VERSION,
        "role": SUPERVISOR_SESSION_ROLE,
        "provider": SUPERVISOR_SESSION_PROVIDER,
        "task_id": validate_task_id(task_id),
        "warm_pooling_active": False,
        "reason": CODEX_RESUME_GATE_OFF_REASON,
        "resume_contract": None,
        "conversation_store": None,
        "state_path": None,
        "context_window_tokens": None,
        "reconciliation": [],
    }


@dataclass(frozen=True)
class SupervisorTurn:
    """One checked-out supervisor turn: its lease, capsule, and request block."""

    lease: SessionLease
    capsule: str
    provider_session: dict[str, Any]

    @property
    def mode(self) -> str:
        return self.lease.mode

    @property
    def session_id(self) -> str | None:
        return self.lease.session_id


def _repository_identity(source: Path) -> str:
    try:
        completed = subprocess.run(
            ("git", "remote", "get-url", "origin"),
            cwd=str(source), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=30.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SupervisorSessionPoolError("source repository identity could not be read") from exc
    if completed.returncode != 0:
        raise SupervisorSessionPoolError("source checkout has no readable origin repository identity")
    try:
        value = completed.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise SupervisorSessionPoolError("source checkout origin is not valid UTF-8") from exc
    if not value:
        raise SupervisorSessionPoolError("source checkout origin is empty")
    return value


def supervisor_pool_root(checkout_root: Path | str, repository_identity: str) -> Path:
    repository_hash = hashlib.sha256(repository_identity.encode("utf-8")).hexdigest()
    return (
        Path(checkout_root).resolve()
        / ".task-review-agent"
        / "session-pools"
        / repository_hash
        / "task-supervisor"
    )


class SupervisorSessionOwner:
    """Own the durable supervisor conversation for exactly one task."""

    def __init__(
        self,
        *,
        source: Path | str,
        checkout_root: Path | str,
        task_id: str,
        worker_id: str,
        run_id: str,
        model: str,
        reasoning_effort: str,
        resume_activation: CodexResumeActivation | None,
        context_window_tokens: int | None = None,
        repository_identity: str | None = None,
        compose_project: str | None = None,
        clock: Callable[[], dt.datetime] = utc_now,
        identity_factory: Callable[[], str] | None = None,
        host_identity: str | None = None,
    ) -> None:
        self.source = Path(source).resolve()
        self.task_id = validate_task_id(task_id)
        self.worker_id = _slot(worker_id, field="worker_id")
        self.run_id = _slot(run_id, field="run_id")
        self.model = _exact(model, field="model")
        self.reasoning_effort = _exact(reasoning_effort, field="reasoning_effort")
        self.compose_project = resolve_compose_project(compose_project)
        self.conversation_store = conversation_store_binding(self.compose_project, "codex")[1]
        if resume_activation is not None and type(resume_activation) is not CodexResumeActivation:
            raise SupervisorSessionPoolError("resume_activation must be an exact CodexResumeActivation")
        self.resume_activation = resume_activation
        self.context_window_tokens = validate_context_window_tokens(context_window_tokens)
        self.clock = clock
        self.identity_factory = identity_factory
        self.host_identity = host_identity or socket.gethostname()
        self.platform = os.name
        self.repository_identity = (
            _repository_identity(self.source) if repository_identity is None else _exact(
                repository_identity, field="repository_identity"
            )
        )
        self.root = supervisor_pool_root(checkout_root, self.repository_identity)
        self.state_path = self.root / "state.json"
        self.lock_path = self.root / "state.lock"
        self.journal_path = self.root / "events.jsonl"
        self.liveness_path = self.root / "liveness" / f"{self.task_id}.alive"
        self.store = DurableSessionPoolStore(self.state_path, lifetime=SUPERVISOR_SESSION_LIFETIME)
        self.scope: SessionScope | None = None
        if resume_activation is not None:
            self.scope = SessionScope(
                protocol_version=SUPERVISOR_SESSION_PROTOCOL_VERSION,
                provider_identifier=SUPERVISOR_SESSION_PROVIDER,
                role=SUPERVISOR_SESSION_ROLE,
                session_class="architect",
                workload_class="admission_cycle",
                model=self.model,
                reasoning_effort=self.reasoning_effort,
                repository_identity=self.repository_identity,
                resume_contract=resume_activation.fingerprint,
                bindings=(
                    conversation_store_binding(self.compose_project, "codex"),
                    ("task_id", self.task_id),
                ),
            )
        self._liveness: BinaryIO | None = None
        self.liveness_identity: str | None = None
        self._closed = False
        self.reconciliation: list[dict[str, Any]] = []
        self._acquire_liveness()
        try:
            self._reconcile()
        except BaseException:
            self.close()
            raise

    # ------------------------------------------------------------------ state

    @property
    def warm_pooling_active(self) -> bool:
        return self.scope is not None and not self._closed

    def activation_state(self) -> dict[str, Any]:
        """Describe, truthfully, whether warm pooling is happening."""

        base = {
            "schema_version": DURABLE_SESSION_POOL_SCHEMA_VERSION,
            "role": SUPERVISOR_SESSION_ROLE,
            "provider": SUPERVISOR_SESSION_PROVIDER,
            "task_id": self.task_id,
            "warm_pooling_active": self.warm_pooling_active,
            "conversation_store": self.conversation_store,
            "state_path": str(self.state_path),
            "context_window_tokens": self.context_window_tokens,
            "reconciliation": list(self.reconciliation),
        }
        if self.scope is None:
            base["reason"] = CODEX_RESUME_GATE_OFF_REASON
            base["resume_contract"] = None
        else:
            base["reason"] = "operator-verified Codex resume control supplied"
            base["resume_contract"] = self.scope.resume_contract
            base["scope_sha256"] = self.scope.key_sha256()
        return base

    def _acquire_liveness(self) -> None:
        try:
            self._liveness = _acquire_liveness_lock(self.liveness_path)
            identity = _file_identity(self._liveness)
            if identity is None:
                raise SupervisorSessionPoolError(
                    "supervisor liveness file identity is unavailable, so a later owner "
                    f"could never prove ownership of {self.liveness_path}"
                )
            self.liveness_identity = f"{identity[0]}:{identity[1]}"
        except (BlockingIOError, PermissionError) as exc:
            raise SupervisorSessionPoolError(
                f"another live worker owns the supervisor session for {self.task_id}: "
                f"{self.liveness_path}"
            ) from exc
        except OSError as exc:
            raise SupervisorSessionPoolError(
                f"supervisor liveness lock could not be taken: {self.liveness_path}: {exc}"
            ) from exc

    def close(self) -> None:
        if self._liveness is not None:
            _release_liveness_lock(self._liveness)
            self._liveness = None
        self._closed = True

    def __enter__(self) -> "SupervisorSessionOwner":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ---------------------------------------------------------- transactions

    def _transaction(self, mutate: Callable[[DurableSessionPool], Any]) -> Any:
        """Load, mutate, save, and journal under the short cross-process lock."""

        events: list[dict[str, Any]] = []
        with _exclusive_file_lock(self.lock_path):
            try:
                pool = self.store.load(
                    clock=self.clock, identity_factory=self.identity_factory,
                    event_sink=events.append,
                )
                result = mutate(pool)
                # Every mutation announces itself; a transaction that changed
                # nothing (an ephemeral-only owner with no stale state) writes
                # nothing, so the gate-off path leaves no pool file behind.
                if events:
                    self.store.save(pool)
            except DurableSessionPoolError as exc:
                raise SupervisorSessionPoolError(str(exc)) from exc
            stamp = utc_text(self.clock())
            for event in events:
                event.update({"task_id": self.task_id, "worker_id": self.worker_id, "run_id": self.run_id, "at": stamp})
                try:
                    append_journal_line(self.journal_path, event)
                except OSError as exc:
                    raise SupervisorSessionPoolError(
                        f"supervisor session journal could not be appended: {self.journal_path}: {exc}"
                    ) from exc
        return result

    def _task_records(self, pool: DurableSessionPool) -> tuple[SessionRecord, ...]:
        return tuple(
            record for record in pool.sessions
            if record.scope.role == SUPERVISOR_SESSION_ROLE
            and record.scope.binding("task_id") == self.task_id
        )

    def _reconcile(self) -> None:
        """Retire stranded or incompatible conversations for this exact task.

        Runs once, at construction, while this owner holds the task's liveness
        lock. An active lease whose recorded owner ran on this host and
        platform is provably stranded -- its owner would otherwise hold the lock
        this owner just took -- and is retired as interrupted. One recorded on
        another host or platform cannot be proven dead and fails closed. Idle
        conversations whose scope differs from the current one (model, effort,
        repository, protocol, or resume control changed, or the gate is now
        off) are retired as incompatible so they are never resumed by mistake.
        """

        def mutate(pool: DurableSessionPool) -> None:
            for record in self._task_records(pool):
                if record.state == "active":
                    lease = record.active_lease
                    assert lease is not None
                    host = lease.assignment_value("host")
                    platform = lease.assignment_value("platform")
                    if host != self.host_identity or platform != self.platform:
                        raise SupervisorSessionPoolError(
                            f"supervisor session for {self.task_id} holds an active lease owned on "
                            f"host {host!r}/{platform!r}; it cannot be proven stranded from "
                            f"{self.host_identity!r}/{self.platform!r}"
                        )
                    # The lock this owner holds must be the very file the
                    # stranded owner held; a replaced lock file proves nothing.
                    if lease.assignment_value("liveness_identity") != self.liveness_identity:
                        raise SupervisorSessionPoolError(
                            f"supervisor session for {self.task_id} holds an active lease whose "
                            "liveness lock file is not the one this owner holds; it cannot be "
                            "proven stranded"
                        )
                    settled = pool.retire_interrupted(
                        lease,
                        detail=(
                            f"owner {lease.assignment_value('worker_id')} run "
                            f"{lease.assignment_value('run_id')} no longer holds the task liveness lock"
                        ),
                    )
                    self.reconciliation.append(
                        {"record_id": settled.record_id, "action": "retired_interrupted", "state": settled.state}
                    )
                elif record.state in {"idle", "probation"} and record.scope != self.scope:
                    observed = pool.observe(record.record_id, observation="session_incompatibility")
                    self.reconciliation.append(
                        {"record_id": observed.record_id, "action": "retired_incompatible", "state": observed.state}
                    )

        self._transaction(mutate)

    # ------------------------------------------------------------------ turns

    def begin_turn(
        self,
        *,
        turn: int,
        allowed_actions: Sequence[str],
        phase: str | None = None,
        issue_state: str | None = None,
        issue_state_version: int | None = None,
        source_head: str | None = None,
        source_tree: str | None = None,
        checkout_status: str | None = None,
    ) -> SupervisorTurn | None:
        """Check out the task's conversation for one judgment turn.

        Returns ``None`` when warm pooling is inactive, in which case the caller
        runs the historical ephemeral turn unchanged. Otherwise the returned
        turn carries the exact lease, the fresh authority capsule that must lead
        the prompt, and the ``provider_session`` block for the container.
        """

        if self.scope is None or self._closed:
            return None
        if isinstance(turn, bool) or type(turn) is not int or turn < 1:
            raise SupervisorSessionPoolError("supervisor turn must be a positive integer")
        actions = tuple(dict.fromkeys(str(item) for item in allowed_actions if str(item)))
        if not actions:
            raise SupervisorSessionPoolError("a supervisor turn requires allowed actions")
        assignment = {
            "run_id": self.run_id,
            "worker_id": self.worker_id,
            "turn": str(turn),
            "host": self.host_identity,
            "platform": self.platform,
            "liveness_identity": self.liveness_identity or "",
        }
        current = {
            "task": self.task_id,
            "run": self.run_id,
            "worker": self.worker_id,
            "turn": str(turn),
            "phase": phase or "(not observed)",
            "issue_state": issue_state or "(not observed)",
            "issue_state_version": "(not observed)" if issue_state_version is None else str(issue_state_version),
            "source_head": source_head or "(not observed)",
            "source_tree": source_tree or "(not observed)",
            "checkout_status": checkout_status or "(not observed)",
        }
        for name in ("phase", "issue_state", "source_head", "source_tree", "checkout_status"):
            value = current[name]
            if value != "(not observed)":
                assignment[name] = value
        if issue_state_version is not None:
            assignment["issue_state_version"] = str(issue_state_version)
        scope = self.scope

        def mutate(pool: DurableSessionPool) -> SessionLease:
            return pool.checkout(
                scope=scope, assignment=assignment, exclusive=True, allow_probation_retry=True,
            )

        lease = self._transaction(mutate)
        capsule = authority_capsule(
            role=SUPERVISOR_SESSION_ROLE,
            mode=lease.mode,
            prior_completed_assignment_count=lease.prior_completed_assignment_count,
            current=current,
            allowed_actions=actions,
            capabilities=(),
            obligations=(
                "Return exactly one structured decision from the allowed actions above.",
                "You hold zero capabilities: no shell, repository write, GitHub, Unity, or tool authority.",
            ),
        )
        provider_session = {
            "mode": lease.mode,
            "session_id": lease.session_id,
            "resume_sandbox_argument": list(self.resume_activation.argument) if self.resume_activation else None,
        }
        return SupervisorTurn(lease=lease, capsule=capsule, provider_session=provider_session)

    def finish_turn(
        self,
        turn: SupervisorTurn,
        *,
        outcome: str,
        confirmation: Any,
        usage: Any = None,
        detail: str = "",
    ) -> SessionRecord:
        """Settle one turn from durable proof; idempotent for identical replays."""

        if type(turn) is not SupervisorTurn:
            raise SupervisorSessionPoolError("finish_turn requires the exact SupervisorTurn")
        confirmed: ProviderSessionConfirmation | None = None
        reason = detail
        if confirmation is not None:
            try:
                confirmed = confirmation_from_dict(confirmation)
            except DurableSessionPoolError as exc:
                confirmed = None
                reason = f"malformed provider session confirmation: {exc}; {detail}"
        settlement = AssignmentSettlement(
            pool_schema_version=DURABLE_SESSION_POOL_SCHEMA_VERSION,
            lease_id=turn.lease.lease_id,
            record_id=turn.lease.record_id,
            outcome=outcome,
            confirmed_session=confirmed,
            known_context_window_percent=known_context_window_percent(usage, self.context_window_tokens),
            evidence=self._usage_evidence(usage),
            detail=reason,
        )
        return self._transaction(lambda pool: pool.check_in(lease=turn.lease, settlement=settlement))

    def cancel_turn(self, turn: SupervisorTurn) -> SessionRecord | None:
        """Return a checked-out turn that never reached the provider, uncharged."""

        if type(turn) is not SupervisorTurn:
            raise SupervisorSessionPoolError("cancel_turn requires the exact SupervisorTurn")
        return self._transaction(lambda pool: pool.cancel(turn.lease))

    @staticmethod
    def _usage_evidence(usage: Any) -> dict[str, str]:
        if not isinstance(usage, Mapping):
            return {}
        evidence: dict[str, str] = {}
        for name in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(name)
            if type(value) is int and not isinstance(value, bool) and value >= 0:
                evidence[name] = str(value)
        return evidence

    def records(self) -> tuple[SessionRecord, ...]:
        """Read this task's records without mutating anything."""

        with _exclusive_file_lock(self.lock_path):
            try:
                pool = self.store.load(clock=self.clock, identity_factory=self.identity_factory)
            except DurableSessionPoolError as exc:
                raise SupervisorSessionPoolError(str(exc)) from exc
        return self._task_records(pool)


def _slot(value: Any, *, field: str) -> str:
    if type(value) is not str or _SLOT.fullmatch(value) is None:
        raise SupervisorSessionPoolError(f"{field} must be a conservative identifier")
    return value


def _exact(value: Any, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise SupervisorSessionPoolError(f"{field} must be exact non-empty text")
    return value


__all__ = [
    "CODEX_RESUME_GATE_OFF_REASON",
    "CODEX_RESUME_SANDBOX_ARGUMENT_ENVIRONMENT",
    "SUPERVISOR_CONTEXT_WINDOW_ENVIRONMENT",
    "SUPERVISOR_SESSION_IDLE_LIFETIME_SECONDS",
    "SUPERVISOR_SESSION_LIFETIME",
    "SUPERVISOR_SESSION_MAX_AGE_SECONDS",
    "SUPERVISOR_SESSION_PROTOCOL_VERSION",
    "SUPERVISOR_SESSION_PROVIDER",
    "SUPERVISOR_SESSION_ROLE",
    "CodexResumeActivation",
    "SupervisorSessionOwner",
    "SupervisorSessionPoolError",
    "SupervisorTurn",
    "classify_turn_failure",
    "codex_resume_activation_from_environment",
    "context_window_tokens_from_environment",
    "gate_off_activation_state",
    "known_context_window_percent",
    "supervisor_pool_root",
    "validate_context_window_tokens",
]
