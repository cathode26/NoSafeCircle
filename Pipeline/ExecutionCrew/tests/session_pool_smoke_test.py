#!/usr/bin/env python3
"""Deterministic tests for the role-scoped ExecutionCrew session pool.

Classification: pure/component tests over the pool state machine, its durable
store, its use of the committed AgentRuntime session-lifetime policy, and
ExecutionCrew's lease wiring. Clocks and session identities are injected, no
provider is contacted, no process is started, and no tracked repository file is
touched; durable role evidence is written to throwaway temporary directories.
Every test proves an explicit regression-only invariant.

The load-bearing claims are: a conversation is reusable only for the same role
with the same stable provider/model/reasoning/class/capability/repository/
protocol identity; a checked-out session is invisible to everyone else; only an
exact matching durable result whose persisted artifact is present, hash-exact,
self-consistent, and bound in its own bytes to this exact assignment returns one;
anything unproven quarantines and never adopts an unproven confirmation's
identity; a proven provider/output failure is counted by the committed policy and
held on non-advertised probation for at most one deliberate retry, so two
consecutive counted failures retire a conversation and an evidenced success
between them resets the streak; idle reuse ends at exactly one hour while active
leases are never touched; the committed worker/architect budgets and
early-retirement rules are applied only between assignments; and nothing in the
pool ever ends a worker.

Full-run behavior for pooled leases lives in `pooled_run_crew_smoke_test.py`.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import inspect
import itertools
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Mapping

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.provider_sessions import (  # noqa: E402
    RESUMED_AUTHORITY_NOTICE,
    ProviderSessionBinding,
    ProviderSessionConfirmation,
)
from Pipeline.AgentRuntime.session_lifecycle import (  # noqa: E402
    ARCHITECT_COMPLETED_CYCLE_LIMIT,
    CONTEXT_WINDOW_RETIRE_PERCENT,
    LATENCY_RETIRE_MULTIPLIER,
    LATENCY_RETIRE_SAMPLE_COUNT,
    SESSION_LIFECYCLE_SCHEMA_VERSION,
    WORKER_WEIGHTED_UNIT_LIMIT,
    WORKER_WEIGHTS,
    LatencySample,
    SessionLifecycleState,
)
from Pipeline.ExecutionCrew import run_crew as crew_module  # noqa: E402
from Pipeline.ExecutionCrew.run_crew import (  # noqa: E402
    ROLE_CAPABILITY_CLASSES,
    CrewBlocked,
    repair_attempt_session,
    validate_role_session_leases,
)
from Pipeline.ExecutionCrew.session_pool import (  # noqa: E402
    CAPABILITY_WORKLOAD_CLASSES,
    CREW_SESSION_PROTOCOL_VERSION,
    CREW_SESSION_ROLES,
    DEFAULT_MAX_CONCURRENT_ASSIGNMENTS,
    DURABLE_ASSIGNMENT_RESULT_SCHEMA_VERSION,
    IDLE_SESSION_LIFETIME_SECONDS,
    POOL_SCHEMA_VERSION,
    SESSION_STATES,
    ROLE_EVIDENCE_FIELDS,
    ROLE_EVIDENCE_SCHEMA_VERSION,
    AssignmentLease,
    DurableAssignmentResult,
    PooledSession,
    SessionCompatibility,
    SessionPool,
    SessionPoolError,
    SessionPoolStore,
    assignment_capsule,
)

BASE = dt.datetime(2026, 9, 4, 12, 0, 0, tzinfo=dt.timezone.utc)
COMMIT = "a" * 40
OTHER_COMMIT = "b" * 40
REPOSITORY = "https://github.com/cathode26/NoSafeCircle.git"
CLAUDE_MODEL = "claude-sonnet-4-5-20260101"
CODEX_MODEL = "gpt-concrete-1"
CHECKOUT = r"C:\NSC\NSC\NSC-050"
BANNED_PROCESS_CONTROL = (
    "kill", "terminate", "SIGKILL", "SIGTERM", "taskkill", "Popen",
    "subprocess", "os.system", "signal", "docker", "psutil",
)

_EVIDENCE = contextlib.ExitStack()
_EVIDENCE_ROOT: Path | None = None
_EVIDENCE_RUNS = itertools.count(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action, expected: type[BaseException]) -> BaseException:
    try:
        action()
    except expected as exc:
        return exc
    raise AssertionError(f"expected {expected.__name__}")


def at(seconds: float) -> dt.datetime:
    return BASE + dt.timedelta(seconds=seconds)


def identity_factory(start: int = 1):
    counter = itertools.count(start)

    def make() -> str:
        value = next(counter)
        return f"{value:08x}-1111-4111-8111-{value:012x}"

    return make


def pool(**values) -> SessionPool:
    values.setdefault("identity_factory", identity_factory())
    values.setdefault("clock", lambda: BASE)
    return SessionPool(**values)


def compatibility(
    *,
    provider: str = "claude-code",
    model: str = CLAUDE_MODEL,
    reasoning: str | None = None,
    role: str = "implementer",
    capability_class: str = "standard",
    repository: str = REPOSITORY,
    protocol: str = CREW_SESSION_PROTOCOL_VERSION,
    session_class: str = "worker",
) -> SessionCompatibility:
    return SessionCompatibility(
        provider, model, reasoning, role, capability_class, repository, protocol, session_class
    )


def checkout(
    session_pool: SessionPool,
    *,
    compat: SessionCompatibility | None = None,
    slot: str = "worker-slot-1",
    task_id: str = "NSC-050",
    run_id: str = "nsc-050-run-1",
    commit: str = COMMIT,
    checkout_identity: str = CHECKOUT,
    now: dt.datetime | None = None,
) -> AssignmentLease:
    return session_pool.checkout(
        compatibility=compat or compatibility(),
        worker_slot_id=slot,
        task_id=task_id,
        worker_run_id=run_id,
        source_commit=commit,
        checkout_identity=checkout_identity,
        now=now,
    )


def evidence_root() -> Path:
    global _EVIDENCE_ROOT
    if _EVIDENCE_ROOT is None:
        _EVIDENCE_ROOT = Path(
            _EVIDENCE.enter_context(tempfile.TemporaryDirectory(prefix="session-pool-evidence-"))
        )
    return _EVIDENCE_ROOT


def role_artifact(role: str, *, status: str, changed: str, semantic: str,
                  binding: Mapping[str, object] | None = None) -> tuple[Path, str, str]:
    """Write one persisted role result exactly as ExecutionCrew would.

    The bytes are written without newline translation and hashed exactly as
    written, so the digest a Windows reader recomputes is the digest a Linux
    writer recorded.
    """

    run_dir = evidence_root() / f"run-{next(_EVIDENCE_RUNS)}"
    (run_dir / "role_results").mkdir(parents=True)
    relative = f"role_results/{role}_1.json"
    record: dict[str, object] = {
        "role": role,
        "attempt": 1,
        "agent_status": "succeeded" if status == "completed" else "failed",
        "scope_check_reasons": (
            [] if changed == "accepted" and semantic == "accepted" else ["fixture reason"]
        ),
        "deterministic_changed_path_validation": changed,
        "semantic_validation": semantic,
    }
    if binding is not None:
        record["pooled_assignment_evidence"] = dict(binding)
    payload = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (run_dir / relative).write_bytes(payload)
    on_disk = (run_dir / relative).read_bytes()
    require(on_disk == payload, "the fixture artifact was not written as exact bytes")
    return run_dir, relative, hashlib.sha256(on_disk).hexdigest()


def durable(
    lease: AssignmentLease,
    *,
    session_id: str | None = None,
    status: str = "completed",
    changed_paths: str = "accepted",
    semantic: str = "accepted",
    outcome: str | None = None,
    context_percent: int | None = None,
    latency: LatencySample | None = None,
    binding_overrides: Mapping[str, object] | None = None,
    omit_binding: bool = False,
    **overrides,
) -> tuple[DurableAssignmentResult, Path]:
    """Return one durable result plus the crew run directory that proves it.

    The persisted artifact carries the exact assignment binding the production
    accessor derives from the result itself, so the fixture can never drift into
    hand-maintained agreement with the schema it is meant to test.
    """

    confirmed = ProviderSessionConfirmation(
        overrides.pop("confirmed_provider", lease.provider_identifier),
        overrides.pop("confirmed_role", lease.role),
        overrides.pop("confirmed_mode", lease.mode),
        session_id or lease.session_id or "cafe0000-1111-4111-8111-000000000001",
    )
    proved = status == "completed" and changed_paths == "accepted" and semantic == "accepted"
    values = {
        "schema_version": DURABLE_ASSIGNMENT_RESULT_SCHEMA_VERSION,
        "pool_schema_version": lease.pool_schema_version,
        "protocol_version": lease.protocol_version,
        "lease_id": lease.lease_id,
        "record_id": lease.record_id,
        "crew_run_id": lease.worker_run_id,
        "task_id": lease.task_id,
        "worker_run_id": lease.worker_run_id,
        "worker_slot_id": lease.worker_slot_id,
        "session_class": lease.session_class,
        "role": lease.role,
        "capability_class": lease.capability_class,
        "provider_identifier": lease.provider_identifier,
        "model": lease.model,
        "reasoning_effort": lease.reasoning_effort,
        "repository_identity": lease.repository_identity,
        "source_commit": lease.source_commit,
        "checkout_identity": lease.checkout_identity,
    }
    values.update(overrides)
    decided = {
        "status": status,
        "assignment_outcome": outcome or ("completed" if proved else "output_failure"),
        "semantic_validation": semantic,
        "changed_path_validation": changed_paths,
        "known_context_window_percent": context_percent,
        "latency_sample": latency,
        "confirmed_session": confirmed,
    }
    # The artifact path is deterministic, so the binding is built before the
    # bytes exist and the recorded digest is taken from the bytes as written.
    provisional = DurableAssignmentResult(
        role_result_artifact=f"role_results/{values['role']}_1.json",
        role_result_sha256="0" * 64,
        **decided, **values,
    )
    binding = dict(provisional.role_evidence_binding())
    binding.update(binding_overrides or {})
    run_dir, artifact, digest = role_artifact(
        values["role"], status=status, changed=changed_paths, semantic=semantic,
        binding=None if omit_binding else binding,
    )
    return (
        DurableAssignmentResult(
            role_result_artifact=artifact,
            role_result_sha256=digest,
            **decided, **values,
        ),
        run_dir,
    )


def complete(session_pool: SessionPool, lease: AssignmentLease, *, now=None, **values):
    result, run_dir = durable(lease, **values)
    return session_pool.check_in(
        lease=lease, result=result, evidence_root=run_dir, now=now or BASE
    )


def seeded(lifecycle: SessionLifecycleState, *, compat: SessionCompatibility,
           record_id: str, idle_at: dt.datetime = BASE) -> PooledSession:
    """Return one idle pooled session carrying an exact seeded lifecycle."""

    return PooledSession(
        record_id=record_id,
        compatibility=compat,
        state="idle",
        session_id=lifecycle.session_id,
        completed_assignment_count=lifecycle.completed_assignments,
        idle_since_utc=idle_at.isoformat().replace("+00:00", "Z"),
        lifecycle=lifecycle,
    )


def lifecycle_state(**values) -> SessionLifecycleState:
    base = {
        "schema_version": SESSION_LIFECYCLE_SCHEMA_VERSION,
        "provider_identifier": "claude-code",
        "role": "implementer",
        "session_id": "aaaa0000-1111-4111-8111-000000000001",
        "session_class": "worker",
    }
    base.update(values)
    return SessionLifecycleState(**base)


def process_control_hits(text: str) -> list[str]:
    """Return every banned process-control word this source text mentions."""

    return sorted(
        word for word in BANNED_PROCESS_CONTROL
        if re.search(rf"\b{re.escape(word)}\b", text) is not None
    )


# ------------------------------------------------- 1/2: reuse and resume


def test_a_returned_implementer_session_is_reused_as_an_implementer() -> None:
    session_pool = pool()
    first = checkout(session_pool)
    require(first.mode == "start", f"a cold pool must start a session: {first.mode}")
    returned = complete(session_pool, first)
    require(returned.state == "idle" and returned.completed_assignment_count == 1, str(returned))

    second = checkout(session_pool, task_id="NSC-051", run_id="nsc-051-run-1", commit=OTHER_COMMIT,
                      now=at(60))
    require(second.mode == "resume", "a warm compatible session was not reused")
    require(second.session_id == first.session_id, "a different conversation was offered")
    require(second.role == "implementer", str(second.role))
    require(second.lease_id != first.lease_id, "a lease was reused")
    require(second.prior_completed_assignment_count == 1, str(second.prior_completed_assignment_count))
    # The refreshed assignment facts are exactly the new ones.
    require(second.task_id == "NSC-051" and second.source_commit == OTHER_COMMIT, str(second))
    require(len(session_pool.sessions) == 1, "reuse created a second session record")


def test_reuse_resumes_rather_than_creating_a_second_provider_session() -> None:
    session_pool = pool()
    first = checkout(session_pool)
    complete(session_pool, first)
    second = checkout(session_pool, task_id="NSC-051", run_id="nsc-051-run-1", now=at(60))
    binding = second.session_binding()
    require(type(binding) is ProviderSessionBinding, str(binding))
    require(binding.mode == "resume" and binding.session_id == first.session_id, str(binding))
    require(len(session_pool.sessions) == 1, "a second provider session record appeared")
    # Codex names its own thread, so a cold Codex start carries no identity and
    # adopts the one its transcript confirms.
    codex_pool = pool()
    codex_compat = compatibility(provider="openai-codex", model=CODEX_MODEL, reasoning="high")
    cold = checkout(codex_pool, compat=codex_compat)
    require(cold.mode == "start" and cold.session_id is None, str(cold))
    assigned = "beef0000-1111-4111-8111-000000000009"
    complete(codex_pool, cold, session_id=assigned)
    warm = checkout(codex_pool, compat=codex_compat, task_id="NSC-051",
                    run_id="nsc-051-run-1", now=at(60))
    require(warm.mode == "resume" and warm.session_id == assigned, str(warm))


# ------------------------------------------------------- 3/4/5: isolation


def test_claude_and_codex_pools_remain_separate() -> None:
    session_pool = pool()
    claude = compatibility()
    codex = compatibility(provider="openai-codex", model=CODEX_MODEL, reasoning="high")
    require(claude.key() != codex.key(), "providers share a compatibility key")
    complete(session_pool, checkout(session_pool, compat=claude))
    lease = checkout(session_pool, compat=codex, now=at(60))
    require(lease.mode == "start", "a Claude conversation was offered to Codex")
    require(len(session_pool.sessions) == 2, str(len(session_pool.sessions)))


def test_every_crew_role_keeps_its_own_pool() -> None:
    require(
        set(CREW_SESSION_ROLES)
        == {"contract_locality_auditor", "implementer", "test_author", "validator"},
        str(CREW_SESSION_ROLES),
    )
    keys = {
        role: compatibility(role=role, capability_class=ROLE_CAPABILITY_CLASSES[role]).key()
        for role in CREW_SESSION_ROLES
    }
    require(len(set(keys.values())) == len(CREW_SESSION_ROLES), f"roles collide: {keys}")
    session_pool = pool()
    warmed = compatibility(role="implementer")
    complete(session_pool, checkout(session_pool, compat=warmed))
    for role in CREW_SESSION_ROLES:
        if role == "implementer":
            continue
        lease = checkout(
            session_pool,
            compat=compatibility(role=role, capability_class=ROLE_CAPABILITY_CLASSES[role]),
            now=at(60),
        )
        require(lease.mode == "start", f"{role} was offered the implementer conversation")
        require(lease.role == role, str(lease.role))


def test_model_or_reasoning_change_creates_a_fresh_session() -> None:
    for changed in (
        compatibility(model="claude-opus-4-1-20260101"),
        compatibility(reasoning="xhigh"),
        compatibility(capability_class="high_reasoning"),
        compatibility(repository="https://github.com/cathode26/Other.git"),
    ):
        session_pool = pool()
        complete(session_pool, checkout(session_pool))
        lease = checkout(session_pool, compat=changed, now=at(60))
        require(lease.mode == "start", f"a stale conversation was reused for {changed}")
        require(len(session_pool.sessions) == 2, str(len(session_pool.sessions)))


# --------------------------------------------- 6/7: exclusivity and capacity


def test_an_active_session_is_never_checked_out_twice() -> None:
    session_pool = pool()
    first = checkout(session_pool)
    complete(session_pool, first)
    second = checkout(session_pool, slot="worker-slot-2", run_id="nsc-050-run-2", now=at(60))
    require(second.mode == "resume", "setup did not warm the session")
    third = checkout(session_pool, slot="worker-slot-3", run_id="nsc-050-run-3", now=at(120))
    require(third.mode == "start", "an active conversation was handed to a second assignment")
    require(third.session_id != second.session_id, "two assignments share one conversation")
    require(session_pool.active_assignment_count == 2, str(session_pool.active_assignment_count))


def test_ten_concurrent_assignments_receive_ten_unique_leases() -> None:
    session_pool = pool()
    require(
        DEFAULT_MAX_CONCURRENT_ASSIGNMENTS == 10,
        str(DEFAULT_MAX_CONCURRENT_ASSIGNMENTS),
    )
    leases = [
        checkout(session_pool, slot=f"worker-slot-{index}", run_id=f"nsc-050-run-{index}",
                 now=at(index))
        for index in range(10)
    ]
    require(len({lease.lease_id for lease in leases}) == 10, "lease IDs collided")
    require(len({lease.record_id for lease in leases}) == 10, "session records collided")
    require(len({lease.session_id for lease in leases}) == 10, "session identities collided")
    require(session_pool.active_assignment_count == 10, str(session_pool.active_assignment_count))
    # Sessions are created lazily: exactly as many as were actually asked for.
    require(len(session_pool.sessions) == 10, str(len(session_pool.sessions)))
    rejects(lambda: checkout(session_pool, slot="worker-slot-11", run_id="nsc-050-run-11"),
            SessionPoolError)
    rejects(lambda: pool(max_concurrent_assignments=9), SessionPoolError)


# ------------------------------------------------- 8/9/10/11: check-in rules


def test_exact_matching_check_in_returns_the_session() -> None:
    session_pool = pool()
    lease = checkout(session_pool)
    returned = complete(session_pool, lease, now=at(30))
    require(returned.state == "idle", str(returned.state))
    require(returned.idle_since_utc == "2026-09-04T12:00:30Z", str(returned.idle_since_utc))
    require(returned.session_id == lease.session_id, "identity changed on check-in")
    require(session_pool.active_assignment_count == 0, "the lease was not released")
    require(returned.lifecycle is not None and returned.lifecycle.worker_weighted_units
            == WORKER_WEIGHTS[CAPABILITY_WORKLOAD_CLASSES["standard"]], str(returned.lifecycle))


def test_stale_or_mismatched_check_in_fails_closed() -> None:
    for field, value in (
        ("lease_id", "dead0000-1111-4111-8111-000000000001"),
        ("record_id", "dead0000-1111-4111-8111-000000000002"),
        ("crew_run_id", "nsc-999-run-9"),
        ("task_id", "NSC-999"),
        ("worker_run_id", "nsc-999-run-9"),
        ("worker_slot_id", "worker-slot-9"),
        ("role", "validator"),
        ("capability_class", "high_reasoning"),
        ("provider_identifier", "openai-codex"),
        ("model", "claude-other-1"),
        ("reasoning_effort", "high"),
        ("repository_identity", "https://github.com/cathode26/Other.git"),
        ("source_commit", OTHER_COMMIT),
        ("checkout_identity", r"C:\NSC\NSC\NSC-999"),
        ("confirmed_role", "validator"),
        ("confirmed_provider", "openai-codex"),
        ("confirmed_mode", "resume"),
    ):
        session_pool = pool()
        lease = checkout(session_pool)
        result, run_dir = durable(lease, **{field: value})
        session = session_pool.check_in(
            lease=lease, result=result, evidence_root=run_dir, now=at(30)
        )
        require(session.state == "quarantined", f"{field} mismatch was accepted")
        require(
            "did not match its lease" in (session.quarantine_reason or "")
            or "compatibility differs" in (session.quarantine_reason or ""),
            f"{field}: {session.quarantine_reason}",
        )
        require(session.retirement_reason in {"identity_failure", "session_incompatibility"},
                f"{field}: {session.retirement_reason}")
        require(not session.is_reusable_at(at(31)), "a quarantined session stayed reusable")
    # A confirmation naming a different conversation is equally fatal.
    session_pool = pool()
    lease = checkout(session_pool)
    complete(session_pool, lease)
    warm = checkout(session_pool, run_id="nsc-050-run-2", now=at(60))
    result, run_dir = durable(warm, session_id="dead0000-1111-4111-8111-000000000002")
    session = session_pool.check_in(lease=warm, result=result, evidence_root=run_dir, now=at(90))
    require(session.state == "quarantined", "a different confirmed session was accepted")
    # A lease that is no longer the session's active lease is stale.
    session_pool = pool()
    lease = checkout(session_pool)
    complete(session_pool, lease)
    rejects(lambda: complete(session_pool, lease), SessionPoolError)


def test_provider_failure_quarantines_the_session() -> None:
    for reason, outcome in (
        ("provider transport failure", "provider_failure"),
        ("timeout with uncertain provider state", "provider_failure"),
        ("missing or malformed provider-session identity", "identity_failure"),
    ):
        session_pool = pool()
        lease = checkout(session_pool)
        session = session_pool.quarantine(lease, reason, outcome=outcome)
        require(session.state == "quarantined" and session.quarantine_reason == reason, str(session))
        require(session_pool.active_assignment_count == 0, "quarantine kept the lease active")
        fresh = checkout(session_pool, run_id="nsc-050-run-2", now=at(60))
        require(fresh.mode == "start", "a quarantined conversation was reused")
    # A rejected deterministic changed-path check must not recycle either, and
    # neither may a rejected semantic review. Both are proven output failures, so
    # the committed policy counts them and the conversation waits on probation --
    # never advertised, never reusable, and never offered by `checkout`.
    for label, values in (
        ("changed paths", {"changed_paths": "rejected"}),
        ("semantics", {"semantic": "rejected"}),
    ):
        session_pool = pool()
        lease = checkout(session_pool)
        result, run_dir = durable(lease, **values)
        session = session_pool.check_in(
            lease=lease, result=result, evidence_root=run_dir, now=at(30)
        )
        require(session.state == "probation", f"{label} rejection was recycled")
        require("rejected" in (session.probation_reason or ""), str(session.probation_reason))
        require(not session.is_reusable_at(at(31)), f"{label}: a failed session stayed reusable")
        fresh = checkout(session_pool, run_id="nsc-050-run-2", now=at(31))
        require(fresh.mode == "start", f"{label}: probation was advertised to checkout")
    rejects(lambda: session_pool.quarantine(lease, "reason", outcome="completed"), SessionPoolError)


def test_missing_durable_result_prevents_reuse() -> None:
    session_pool = pool()
    lease = checkout(session_pool)
    session = session_pool.check_in(lease=lease, result=None, evidence_root=None, now=at(30))
    require(session.state == "quarantined", "a missing durable result was accepted")
    require("no durable assignment result" in (session.quarantine_reason or ""),
            str(session.quarantine_reason))
    # A failed status is not reusable even when the identity all matches: a
    # proven provider failure is counted and held on probation, never returned as
    # a successful reusable result.
    session_pool = pool()
    lease = checkout(session_pool)
    result, run_dir = durable(lease, status="failed", outcome="provider_failure")
    session = session_pool.check_in(lease=lease, result=result, evidence_root=run_dir, now=at(30))
    require(session.state == "probation", "a failed assignment recycled its session")
    require(not session.is_reusable_at(at(31)), "a failed assignment stayed reusable")
    rejects(lambda: durable(lease, status="unknown"), SessionPoolError)
    rejects(lambda: durable(lease, changed_paths="maybe"), SessionPoolError)
    # A durable result may never claim success while reporting a rejection.
    rejects(lambda: durable(lease, changed_paths="rejected", outcome="completed"), SessionPoolError)
    rejects(lambda: durable(lease, status="failed", outcome="completed"), SessionPoolError)


def test_missing_or_tampered_role_evidence_prevents_reuse() -> None:
    # An exit code, a caller assertion, or a session ID is not evidence: the
    # exact persisted role artifact must be present and hash-exact.
    session_pool = pool()
    lease = checkout(session_pool)
    result, run_dir = durable(lease)
    session = session_pool.check_in(lease=lease, result=result, evidence_root=None, now=at(30))
    require(session.state == "quarantined", "a check-in with no run directory was accepted")

    session_pool = pool()
    lease = checkout(session_pool)
    result, run_dir = durable(lease)
    (run_dir / result.role_result_artifact).unlink()
    session = session_pool.check_in(lease=lease, result=result, evidence_root=run_dir, now=at(30))
    require(session.state == "quarantined", "a missing role artifact was accepted")
    require("missing or unreadable" in (session.quarantine_reason or ""),
            str(session.quarantine_reason))

    session_pool = pool()
    lease = checkout(session_pool)
    result, run_dir = durable(lease)
    (run_dir / result.role_result_artifact).write_text("{}\n", encoding="utf-8")
    session = session_pool.check_in(lease=lease, result=result, evidence_root=run_dir, now=at(30))
    require(session.state == "quarantined", "a tampered role artifact was accepted")
    require("SHA-256" in (session.quarantine_reason or ""), str(session.quarantine_reason))

    # An artifact that hashes correctly but records a different decision is a
    # contradiction, not evidence.
    session_pool = pool()
    lease = checkout(session_pool)
    run_dir, _, _ = role_artifact("implementer", status="completed", changed="rejected",
                                  semantic="accepted")
    honest, honest_dir = durable(lease)
    forged = DurableAssignmentResult.from_dict({
        **honest.to_dict(),
        "role_result_sha256": hashlib.sha256(
            (run_dir / "role_results/implementer_1.json").read_bytes()
        ).hexdigest(),
    })
    session = session_pool.check_in(lease=lease, result=forged, evidence_root=run_dir, now=at(30))
    require(session.state == "quarantined", "a contradictory role artifact was accepted")
    require("disagrees with the durable claim" in (session.quarantine_reason or ""),
            str(session.quarantine_reason))
    require(honest_dir != run_dir, "evidence directories must not collide")


def rewritten_binding(run_dir: Path, artifact: str, mutate) -> str:
    """Rewrite one artifact's assignment binding and return its new digest."""

    path = run_dir / artifact
    record = json.loads(path.read_text(encoding="utf-8"))
    mutate(record["pooled_assignment_evidence"])
    payload = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_role_evidence_is_inseparable_from_its_exact_assignment() -> None:
    # A well-formed artifact proves its own assignment.
    session_pool = pool()
    lease = checkout(session_pool)
    result, run_dir = durable(lease)
    require(result.evidence_reason(run_dir) is None, str(result.evidence_reason(run_dir)))
    binding = result.role_evidence_binding()
    require(tuple(binding) == ROLE_EVIDENCE_FIELDS, str(tuple(binding)))
    require(binding["schema_version"] == ROLE_EVIDENCE_SCHEMA_VERSION, str(binding))

    # An artifact with no binding at all is not this assignment's evidence.
    session_pool = pool()
    lease = checkout(session_pool)
    result, run_dir = durable(lease, omit_binding=True)
    session = session_pool.check_in(lease=lease, result=result, evidence_root=run_dir, now=at(30))
    require(session.state == "quarantined", str(session.state))
    require("no pooled assignment binding" in (session.quarantine_reason or ""),
            str(session.quarantine_reason))

    # Every bound field is compared against the trusted lease/result.
    for field, value in (
        ("schema_version", "9.9"),
        ("pool_schema_version", "9.9"),
        ("protocol_version", "9.9"),
        ("crew_run_id", "nsc-999-run-9"),
        ("lease_id", "dead0000-1111-4111-8111-000000000001"),
        ("record_id", "dead0000-1111-4111-8111-000000000002"),
        ("task_id", "NSC-999"),
        ("worker_run_id", "nsc-999-run-9"),
        ("worker_slot_id", "worker-slot-9"),
        ("session_class", "architect"),
        ("role", "validator"),
        ("capability_class", "high_reasoning"),
        ("repository_identity", "https://github.com/cathode26/Other.git"),
        ("source_commit", OTHER_COMMIT),
        ("checkout_identity", r"C:\NSC\NSC\NSC-999"),
        ("provider_identifier", "openai-codex"),
        ("model", "claude-other-1"),
        ("reasoning_effort", "high"),
        ("confirmed_session", {"schema_version": "1.0", "provider_identifier": "claude-code",
                               "role": "implementer", "mode": "start",
                               "session_id": "dead0000-1111-4111-8111-000000000003"}),
        ("status", "failed"),
        ("assignment_outcome", "output_failure"),
        ("semantic_validation", "rejected"),
        ("changed_path_validation", "rejected"),
        ("role_result_artifact", "role_results/validator_1.json"),
    ):
        require(field in ROLE_EVIDENCE_FIELDS, f"{field} is not a bound field")
        session_pool = pool()
        lease = checkout(session_pool)
        result, run_dir = durable(lease, binding_overrides={field: value})
        session = session_pool.check_in(
            lease=lease, result=result, evidence_root=run_dir, now=at(30)
        )
        require(session.state == "quarantined", f"{field}: {session.state}")
        require(f"binding disagrees with the durable claim: ['{field}']"
                in (session.quarantine_reason or ""), f"{field}: {session.quarantine_reason}")

    # An extra field and a missing field are both refused, even when the artifact
    # is rehashed so its digest still matches.
    for label, mutate, expected in (
        ("extra", lambda item: item.update({"surprise": 1}),
         "binding has unsupported fields: ['surprise']"),
        ("missing", lambda item: item.pop("lease_id"),
         "binding is missing fields: ['lease_id']"),
    ):
        session_pool = pool()
        lease = checkout(session_pool)
        result, run_dir = durable(lease)
        digest = rewritten_binding(run_dir, result.role_result_artifact, mutate)
        rehashed = DurableAssignmentResult.from_dict(
            {**result.to_dict(), "role_result_sha256": digest}
        )
        session = session_pool.check_in(
            lease=lease, result=rehashed, evidence_root=run_dir, now=at(30)
        )
        require(session.state == "quarantined", f"{label}: {session.state}")
        require(expected in (session.quarantine_reason or ""),
                f"{label}: {session.quarantine_reason}")

    # A successful same-role artifact copied from another run, lease, task, and
    # source cannot prove this assignment, even byte-for-byte with a rehashed
    # digest and the same run-relative path.
    donor_pool = pool(identity_factory=identity_factory(start=200))
    donor = checkout(donor_pool, task_id="NSC-060", run_id="nsc-060-run-1",
                     commit=OTHER_COMMIT, checkout_identity=r"C:\NSC\NSC\NSC-060")
    donor_result, donor_dir = durable(donor)
    require(donor_result.evidence_reason(donor_dir) is None, "the donor artifact is invalid")
    donor_bytes = (donor_dir / donor_result.role_result_artifact).read_bytes()

    session_pool = pool()
    lease = checkout(session_pool)
    result, run_dir = durable(lease)
    require(result.role_result_artifact == donor_result.role_result_artifact,
            "the copy must reuse the same run-relative path")
    (run_dir / result.role_result_artifact).write_bytes(donor_bytes)
    borrowed = DurableAssignmentResult.from_dict({
        **result.to_dict(),
        "role_result_sha256": hashlib.sha256(donor_bytes).hexdigest(),
    })
    session = session_pool.check_in(
        lease=lease, result=borrowed, evidence_root=run_dir, now=at(30)
    )
    require(session.state == "quarantined", str(session.state))
    reason = session.quarantine_reason or ""
    require("binding disagrees with the durable claim" in reason, reason)
    for field in ("checkout_identity", "crew_run_id", "lease_id", "record_id",
                  "source_commit", "task_id", "worker_run_id"):
        require(f"'{field}'" in reason, f"{field} was not compared: {reason}")
    require(not session.is_reusable_at(at(31)), "a borrowed artifact recycled a session")


def test_an_unproven_confirmation_never_replaces_a_trusted_identity() -> None:
    # A pre-bound conversation keeps the identity the pool chose, whatever a
    # mismatched confirmation asserts.
    forged_id = "dead0000-1111-4111-8111-000000000009"
    session_pool = pool()
    lease = checkout(session_pool)
    require(lease.session_id is not None and lease.mode == "start", str(lease))
    result, run_dir = durable(lease, session_id=forged_id)
    session = session_pool.check_in(lease=lease, result=result, evidence_root=run_dir, now=at(30))
    require(session.state == "quarantined", str(session.state))
    require(session.session_id == lease.session_id,
            f"an unproven confirmation replaced the trusted identity: {session.session_id}")
    require(session.lifecycle is not None and session.lifecycle.session_id == lease.session_id,
            str(None if session.lifecycle is None else session.lifecycle.session_id))
    require(forged_id not in json.dumps(session.to_dict()),
            "the forged identity survived somewhere in the quarantined record")

    # A provider-named cold conversation has no trusted identity yet, so an
    # unproven confirmation gives it none.
    codex = compatibility(provider="openai-codex", model=CODEX_MODEL, reasoning="high")
    for label, values in (
        ("wrong provider", {"confirmed_provider": "claude-code"}),
        ("wrong role", {"confirmed_role": "validator"}),
        ("wrong mode", {"confirmed_mode": "resume"}),
        ("mismatched lease", {"task_id": "NSC-999"}),
    ):
        session_pool = pool()
        lease = checkout(session_pool, compat=codex)
        require(lease.session_id is None, f"{label}: a cold Codex lease claimed an identity")
        result, run_dir = durable(lease, **values)
        session = session_pool.check_in(
            lease=lease, result=result, evidence_root=run_dir, now=at(30)
        )
        require(session.state == "quarantined", f"{label}: {session.state}")
        require(session.session_id is None,
                f"{label}: an unproven confirmation was adopted: {session.session_id}")
        require(session.lifecycle is None,
                f"{label}: an unproven identity was accounted: {session.lifecycle}")
        fresh = checkout(session_pool, compat=codex, run_id="nsc-050-run-2", now=at(31))
        require(fresh.mode == "start", f"{label}: an unproven conversation was reused")

    # An exact confirmation whose durable evidence cannot be proven is equally
    # untrusted: nothing is adopted.
    session_pool = pool()
    lease = checkout(session_pool, compat=codex)
    result, run_dir = durable(lease)
    (run_dir / result.role_result_artifact).unlink()
    session = session_pool.check_in(lease=lease, result=result, evidence_root=run_dir, now=at(30))
    require(session.state == "quarantined", str(session.state))
    require(session.session_id is None and session.lifecycle is None, str(session))

    # Only an exact confirmation with provable evidence adopts the identity the
    # provider named.
    session_pool = pool()
    lease = checkout(session_pool, compat=codex)
    result, run_dir = durable(lease)
    session = session_pool.check_in(lease=lease, result=result, evidence_root=run_dir, now=at(30))
    require(session.state == "idle", str(session.state))
    require(session.session_id == result.confirmed_session.session_id, str(session.session_id))
    require(session.lifecycle.session_id == result.confirmed_session.session_id,
            str(session.lifecycle.session_id))
    warm = checkout(session_pool, compat=codex, run_id="nsc-050-run-2", now=at(31))
    require(warm.mode == "resume" and warm.session_id == result.confirmed_session.session_id,
            str(warm))


# ------------------------------------------------------- 12/13: idle lifetime


def test_idle_sessions_expire_after_exactly_one_hour() -> None:
    require(IDLE_SESSION_LIFETIME_SECONDS == 3600.0, str(IDLE_SESSION_LIFETIME_SECONDS))
    session_pool = pool()
    lease = checkout(session_pool)
    returned = complete(session_pool, lease, now=at(0))
    require(returned.is_reusable_at(at(3599.999)), "expired early")
    require(not returned.is_reusable_at(at(3600.0)), "reusable at exactly one hour")
    warm = checkout(session_pool, run_id="nsc-050-run-2", now=at(3599))
    require(warm.mode == "resume", "a still-fresh session was not reused")
    complete(session_pool, warm, now=at(3599))

    stale = pool()
    stale_lease = checkout(stale)
    complete(stale, stale_lease, now=at(0))
    expired = stale.expire_idle(now=at(3600.0))
    require(len(expired) == 1 and expired[0].state == "expired", str(expired))
    # Expiry stops selection only; the identity is retained, not deleted.
    require(expired[0].session_id == stale_lease.session_id, "expiry discarded the identity")
    require(expired[0].completed_assignment_count == 1, "expiry discarded the history")
    cold = checkout(stale, run_id="nsc-050-run-3", now=at(3601))
    require(cold.mode == "start", "an expired conversation was reused")


def test_active_sessions_are_never_expired_or_stolen() -> None:
    session_pool = pool()
    lease = checkout(session_pool, now=at(0))
    # A very slow worker still owns its lease a full day later.
    require(session_pool.expire_idle(now=at(86_400)) == (), "an active lease was expired")
    held = session_pool.sessions[0]
    require(held.state == "active" and held.active_lease == lease, str(held))
    other = checkout(session_pool, slot="worker-slot-2", run_id="nsc-050-run-2", now=at(86_400))
    require(other.record_id != lease.record_id, "an active session was stolen")
    # The original lease still checks in normally afterwards.
    returned = complete(session_pool, lease, now=at(86_401))
    require(returned.state == "idle", str(returned.state))


# ------------------------------------------------- 14/15: authority on reuse


def test_a_reused_session_receives_the_authority_revocation_capsule() -> None:
    session_pool = pool()
    complete(session_pool, checkout(session_pool))
    reused = checkout(session_pool, task_id="NSC-051", run_id="nsc-051-run-1",
                      commit=OTHER_COMMIT, checkout_identity=r"C:\NSC\NSC\NSC-051", now=at(60))
    capsule = assignment_capsule(
        reused, checkout_root=r"C:\NSC\NSC\NSC-051",
        capabilities=("repository_read", "repository_search", "repository_write"),
        allowed_paths=("Assets/Current.cs",), denied_paths=("Assets/Forbidden.cs",),
        evidence_obligations=("Deterministic changed-path validation applies.",),
    )
    for phrase in (
        "preceding assignment in this conversation is complete",
        "has expired and no longer applies",
        "recall only",
        "NSC-051",
        OTHER_COMMIT,
        r"C:\NSC\NSC\NSC-051",
        "repository_write",
        "Assets/Current.cs",
        "Assets/Forbidden.cs",
        "Denied paths override allowed paths",
        "implementer",
        "Deterministic changed-path validation applies.",
        "Only this assignment may be acted on",
    ):
        require(phrase in capsule, f"capsule is missing: {phrase}")
    rejects(lambda: assignment_capsule(None, checkout_root="x", capabilities=(),
                                       allowed_paths=(), denied_paths=(),
                                       evidence_obligations=()), SessionPoolError)


def test_prior_allowed_paths_are_not_current_allowed_paths() -> None:
    session_pool = pool()
    first = checkout(session_pool)
    first_capsule = assignment_capsule(
        first, checkout_root=CHECKOUT, capabilities=("repository_write",),
        allowed_paths=("Assets/Old.cs",), denied_paths=(), evidence_obligations=(),
    )
    require("Assets/Old.cs" in first_capsule, "setup capsule is wrong")
    complete(session_pool, first)
    reused = checkout(session_pool, task_id="NSC-051", run_id="nsc-051-run-1", now=at(60))
    second_capsule = assignment_capsule(
        reused, checkout_root=r"C:\NSC\NSC\NSC-051", capabilities=("repository_write",),
        allowed_paths=("Assets/New.cs",), denied_paths=("Assets/Old.cs",),
        evidence_obligations=(),
    )
    allowed_block = second_capsule.split("Current allowed write paths:")[1].split(
        "Current denied write paths:"
    )[0]
    require("Assets/New.cs" in allowed_block, "current allowed path missing")
    require("Assets/Old.cs" not in allowed_block, "a prior allowed path stayed allowed")
    require("Assets/Old.cs" in second_capsule.split("Current denied write paths:")[1],
            "the prior path was not explicitly denied")
    # The lease itself never carries write paths, so they cannot leak forward.
    require(not any("path" in name for name in AssignmentLease.__dataclass_fields__),
            str(tuple(AssignmentLease.__dataclass_fields__)))


# ------------------------------------- 16/17/18: ExecutionCrew lease wiring


def test_existing_ephemeral_crew_behavior_is_unchanged_without_pool_arguments() -> None:
    identity = {"task_id": "NSC-050", "run_id": "r", "provider_identifier": "claude-code",
                "model": CLAUDE_MODEL, "reasoning_effort": None, "source_commit": COMMIT,
                "checkout_identity": CHECKOUT, "repository_identity": REPOSITORY}
    require(validate_role_session_leases(None, **identity) == {}, "absent leases produced bindings")
    require(validate_role_session_leases({}, **identity) == {}, "empty leases produced bindings")
    signature = inspect.signature(crew_module.run_crew)
    for name in ("role_session_leases", "role_session_bindings", "codex_resume_sandbox_argument",
                 "scheduler_repository_identity"):
        require(signature.parameters[name].default is None, f"{name} is not optional")
    source = inspect.getsource(crew_module.run_crew)
    require("supply role session bindings or pooled leases, not both" in source,
            "the crew accepts both session mechanisms at once")
    require("pooled role session leases require the exact worker run ID" in source,
            "pooled leases do not pin the worker run ID")
    require("pooled role session leases require the scheduler-proven repository identity" in source,
            "pooled leases do not require a proven repository identity")


def test_repair_attempts_retain_the_roles_leased_session() -> None:
    session_pool = pool()
    lease = checkout(session_pool)
    confirmed = ProviderSessionConfirmation("claude-code", "implementer", "start", lease.session_id)
    resumed = repair_attempt_session(confirmed)
    require(resumed.is_resume, "a repair attempt started a second conversation")
    require(resumed.session_id == lease.session_id, "a repair attempt changed conversation")
    require(resumed.role == "implementer", str(resumed.role))
    rejects(lambda: repair_attempt_session("not-a-confirmation"), CrewBlocked)
    source = inspect.getsource(crew_module.run_crew)
    require("role_sessions[role] = repair_attempt_session(confirmed)" in source,
            "the crew does not carry a role's session into its repair attempt")
    require("role_sessions.get(role) or resolve_role_session(" in source,
            "the crew does not prefer the live per-role session")


def test_a_retry_cannot_inherit_an_unrelated_execution() -> None:
    session_pool = pool()
    lease = checkout(session_pool, task_id="NSC-050", run_id="nsc-050-run-1")
    common = {"provider_identifier": "claude-code", "model": CLAUDE_MODEL,
              "reasoning_effort": None, "source_commit": COMMIT,
              "checkout_identity": CHECKOUT, "repository_identity": REPOSITORY}
    require(
        validate_role_session_leases({"implementer": lease}, task_id="NSC-050",
                                     run_id="nsc-050-run-1", **common) == {"implementer": lease},
        "the matching lease was refused",
    )
    for label, values in (
        ("another task", {"task_id": "NSC-051", "run_id": "nsc-050-run-1"}),
        ("another run", {"task_id": "NSC-050", "run_id": "nsc-050-run-2"}),
    ):
        blocked = rejects(
            lambda values=values: validate_role_session_leases(
                {"implementer": lease}, **values, **common
            ),
            CrewBlocked,
        )
        require("cannot be used" in str(blocked), f"{label}: {blocked}")
    matched = {"task_id": "NSC-050", "run_id": "nsc-050-run-1"}
    for label, override, expected in (
        ("role", {}, "cannot be used for role"),
        ("provider", {"provider_identifier": "openai-codex"}, "cannot be used through"),
        ("model", {"model": "claude-other-1"}, "routed model"),
        ("reasoning", {"reasoning_effort": "high"}, "reasoning effort"),
        ("commit", {"source_commit": OTHER_COMMIT}, "bound to source commit"),
        ("checkout", {"checkout_identity": r"C:\NSC\NSC\NSC-999"}, "bound to source checkout"),
        ("repository", {"repository_identity": "https://github.com/cathode26/Other.git"},
         "bound to repository"),
    ):
        leases = {"validator": lease} if label == "role" else {"implementer": lease}
        blocked = rejects(
            lambda leases=leases, override=override: validate_role_session_leases(
                leases, **matched, **{**common, **override}
            ),
            CrewBlocked,
        )
        require(expected in str(blocked), f"{label}: {blocked}")
    # The routed capability class for this exact role is part of the identity.
    blocked = rejects(
        lambda: validate_role_session_leases(
            {"implementer": lease}, **matched, **common,
            role_capability_classes={"implementer": "high_reasoning"},
        ),
        CrewBlocked,
    )
    require("capability class" in str(blocked), str(blocked))
    rejects(lambda: validate_role_session_leases({"implementer": "lease"}, **matched, **common),
            CrewBlocked)


# ------------------------------------------------------------ 19: durability


def test_pool_persistence_is_atomic_and_malformed_state_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="session-pool-test-") as text:
        path = Path(text) / "state" / "pool.json"
        store = SessionPoolStore(path)
        require(store.load().sessions == (), "a missing store did not start empty")
        session_pool = pool()
        lease = checkout(session_pool)
        complete(session_pool, lease)
        store.save(session_pool)
        require(path.is_file(), "pool state was not written")
        leftovers = [item.name for item in path.parent.iterdir() if item.name != path.name]
        require(not leftovers, f"atomic write left temporary files: {leftovers}")

        restored = SessionPoolStore(path).load(clock=lambda: at(60), identity_factory=identity_factory())
        require(len(restored.sessions) == 1, str(restored.sessions))
        warm = checkout(restored, run_id="nsc-050-run-2", now=at(60))
        require(warm.mode == "resume" and warm.session_id == lease.session_id, str(warm))

        payload = json.loads(path.read_text(encoding="utf-8"))
        for label, corrupt in (
            ("duplicate JSON keys", '{"schema_version":"1.0","schema_version":"1.0"}'),
            ("unknown schema", json.dumps({**payload, "schema_version": "9.9"})),
            ("unknown protocol", json.dumps({**payload, "protocol_version": "9.9"})),
            ("unknown field", json.dumps({**payload, "surprise": 1})),
            ("not an object", "[]"),
            ("truncated", "{"),
        ):
            path.write_text(corrupt, encoding="utf-8")
            rejects(lambda: SessionPoolStore(path).load(), SessionPoolError)
        # Duplicate session identities and duplicate active leases are impossible.
        doubled = json.loads(json.dumps(payload))
        doubled["sessions"] = [payload["sessions"][0], dict(payload["sessions"][0], record_id="cccc0000-1111-4111-8111-000000000003")]
        path.write_text(json.dumps(doubled), encoding="utf-8")
        rejects(lambda: SessionPoolStore(path).load(), SessionPoolError)
        # Malformed UUIDs never load.
        broken = json.loads(json.dumps(payload))
        broken["sessions"][0]["session_id"] = "last"
        path.write_text(json.dumps(broken), encoding="utf-8")
        rejects(lambda: SessionPoolStore(path).load(), SessionPoolError)
        # Durable lifecycle accounting must agree with the pool's own count.
        disagreeing = json.loads(json.dumps(payload))
        disagreeing["sessions"][0]["completed_assignment_count"] = 7
        path.write_text(json.dumps(disagreeing), encoding="utf-8")
        rejects(lambda: SessionPoolStore(path).load(), SessionPoolError)
        rejects(lambda: store.save("not-a-pool"), SessionPoolError)
    # Mutable pool state must never be stored inside the repository.
    rejects(lambda: SessionPoolStore(ROOT / "Pipeline" / "pool.json"), SessionPoolError)


def test_a_nested_session_protocol_must_match_the_crew_protocol() -> None:
    # Construction refuses another protocol outright.
    rejects(lambda: compatibility(protocol="9.9"), SessionPoolError)
    session_pool = pool()
    lease = checkout(session_pool)
    complete(session_pool, lease)
    payload = session_pool.to_dict()
    require(payload["protocol_version"] == CREW_SESSION_PROTOCOL_VERSION, str(payload))
    # A payload that claims the supported protocol at the top level while
    # carrying a conversation that learned another one is refused on restore.
    nested = json.loads(json.dumps(payload))
    nested["sessions"][0]["compatibility"]["protocol_version"] = "9.9"
    blocked = rejects(lambda: SessionPool.from_dict(nested), SessionPoolError)
    require("protocol" in str(blocked), str(blocked))
    require(nested["protocol_version"] == "1.0", "the top-level protocol was not left supported")
    # The same rule applies to a restored lease and a restored durable result.
    rejects(lambda: AssignmentLease.from_dict({**lease.to_dict(), "protocol_version": "9.9"}),
            SessionPoolError)
    result, _ = durable(lease)
    rejects(lambda: DurableAssignmentResult.from_dict({**result.to_dict(),
                                                       "protocol_version": "9.9"}),
            SessionPoolError)


def test_durable_assignment_results_round_trip_and_fail_closed() -> None:
    session_pool = pool()
    lease = checkout(session_pool)
    result, run_dir = durable(lease)
    require(DurableAssignmentResult.from_dict(result.to_dict()) == result, "round trip failed")
    require(result.evidence_reason(run_dir) is None, str(result.evidence_reason(run_dir)))
    for label, mutation in (
        ("unknown field", {"surprise": 1}),
        ("bad schema", {"schema_version": "9.9"}),
        ("bad pool schema", {"pool_schema_version": "9.9"}),
        ("bad status", {"status": "maybe"}),
        ("bad outcome", {"assignment_outcome": "idle"}),
        ("bad digest", {"role_result_sha256": "not-a-digest"}),
        ("absolute artifact", {"role_result_artifact": "/etc/passwd"}),
        ("traversal artifact", {"role_result_artifact": "role_results/../../secret.json"}),
        ("bad percent", {"known_context_window_percent": 101}),
        ("bad session", {"confirmed_session": {"schema_version": "1.0",
                                               "provider_identifier": "claude-code",
                                               "role": "implementer", "mode": "start",
                                               "session_id": "last"}}),
    ):
        rejects(lambda mutation=mutation: DurableAssignmentResult.from_dict(
            {**result.to_dict(), **mutation}), SessionPoolError)
        require(label, "each mutation is labeled")
    missing = {key: value for key, value in result.to_dict().items() if key != "lease_id"}
    rejects(lambda: DurableAssignmentResult.from_dict(missing), SessionPoolError)


# ------------------------------------ 20/21/22/23: committed lifetime policy


def budget_run(capability_class: str, expected_assignments: int) -> None:
    """Complete assignments until the committed worker budget retires the session."""

    compat = compatibility(capability_class=capability_class)
    session_pool = pool()
    first = checkout(session_pool, compat=compat)
    session_id = first.session_id
    lease = first
    for index in range(expected_assignments):
        returned = complete(session_pool, lease, now=at(index))
        if index < expected_assignments - 1:
            require(returned.state == "idle", f"retired early at {index + 1}: {returned.state}")
            lease = checkout(session_pool, compat=compat, run_id=f"nsc-050-run-{index + 2}",
                             now=at(index))
            require(lease.mode == "resume" and lease.session_id == session_id,
                    f"assignment {index + 2} did not continue the conversation")
        else:
            require(returned.state == "retired",
                    f"still reusable after {expected_assignments}: {returned.state}")
            require(returned.retirement_reason == "worker_weighted_unit_limit",
                    str(returned.retirement_reason))
            require(returned.completed_assignment_count == expected_assignments,
                    str(returned.completed_assignment_count))
    replacement = checkout(session_pool, compat=compat, run_id="nsc-050-run-final",
                           now=at(expected_assignments))
    require(replacement.mode == "start", "a retired conversation was offered again")
    require(replacement.session_id != session_id, "a retired conversation was reused")


def test_worker_budget_is_exactly_forty_eight_weighted_units() -> None:
    require(WORKER_WEIGHTED_UNIT_LIMIT == 48, str(WORKER_WEIGHTED_UNIT_LIMIT))
    require(WORKER_WEIGHTS == {"fast": 1, "standard": 3, "deep": 6}, str(WORKER_WEIGHTS))
    require(CAPABILITY_WORKLOAD_CLASSES
            == {"low_cost": "fast", "standard": "standard", "high_reasoning": "deep"},
            str(CAPABILITY_WORKLOAD_CLASSES))
    budget_run("low_cost", 48)
    budget_run("standard", 16)
    budget_run("high_reasoning", 8)


def test_architect_retires_after_exactly_one_hundred_cycles() -> None:
    require(ARCHITECT_COMPLETED_CYCLE_LIMIT == 100, str(ARCHITECT_COMPLETED_CYCLE_LIMIT))
    compat = compatibility(role="architect", capability_class="high_reasoning",
                           session_class="architect")
    require(compat.workload_class == "admission_cycle", compat.workload_class)
    session_pool = pool()
    lease = checkout(session_pool, compat=compat)
    for index in range(ARCHITECT_COMPLETED_CYCLE_LIMIT):
        returned = complete(session_pool, lease, now=at(index))
        if index < ARCHITECT_COMPLETED_CYCLE_LIMIT - 1:
            require(returned.state == "idle", f"retired early at cycle {index + 1}")
            lease = checkout(session_pool, compat=compat, run_id=f"nsc-050-run-{index + 2}",
                             now=at(index))
        else:
            require(returned.state == "retired", f"still reusable after 100: {returned.state}")
            require(returned.retirement_reason == "architect_completed_cycle_limit",
                    str(returned.retirement_reason))
            require(returned.lifecycle.architect_completed_admission_cycles == 100,
                    str(returned.lifecycle))
    # An architect session is never confused with a worker session.
    rejects(lambda: compatibility(role="implementer", session_class="architect"), SessionPoolError)
    rejects(lambda: compatibility(role="architect"), SessionPoolError)
    rejects(lambda: compatibility(role="architect", capability_class="standard",
                                  session_class="architect"), SessionPoolError)


def test_idle_and_waiting_cost_nothing() -> None:
    session_pool = pool()
    lease = checkout(session_pool)
    returned = complete(session_pool, lease, now=at(0))
    spent = returned.lifecycle.worker_weighted_units
    for observation in ("idle", "waiting", "idle", "waiting"):
        observed = session_pool.observe(returned.record_id, observation=observation)
        require(observed.state == "idle", f"{observation} changed availability: {observed.state}")
        require(observed.lifecycle.worker_weighted_units == spent,
                f"{observation} consumed budget: {observed.lifecycle.worker_weighted_units}")
        require(observed.completed_assignment_count == 1, str(observed.completed_assignment_count))
    # Waiting does not extend reusability either: the idle clock is unchanged.
    require(session_pool.sessions[0].idle_since_utc == returned.idle_since_utc,
            "waiting reset the idle clock")
    warm = checkout(session_pool, run_id="nsc-050-run-2", now=at(60))
    require(warm.mode == "resume", "a waiting session stopped being reusable")


def test_every_early_retirement_condition_is_enforced() -> None:
    # Incompatibility and identity failure retire immediately.
    session_pool = pool()
    lease = checkout(session_pool)
    result, run_dir = durable(lease, task_id="NSC-999")
    session = session_pool.check_in(lease=lease, result=result, evidence_root=run_dir)
    require(session.retirement_reason == "identity_failure", str(session.retirement_reason))

    session_pool = pool()
    lease = checkout(session_pool)
    result, run_dir = durable(lease, model="claude-other-1", capability_class="high_reasoning")
    session = session_pool.check_in(lease=lease, result=result, evidence_root=run_dir)
    require(session.state == "quarantined", str(session.state))

    idle_session = pool(sessions=[seeded(lifecycle_state(), compat=compatibility(),
                                         record_id="aaaa0000-1111-4111-8111-000000000002")])
    retired = idle_session.observe("aaaa0000-1111-4111-8111-000000000002",
                                   observation="session_incompatibility")
    require(retired.state == "retired" and retired.retirement_reason == "session_incompatibility",
            str(retired))
    identity_pool = pool(sessions=[seeded(lifecycle_state(), compat=compatibility(),
                                          record_id="aaaa0000-1111-4111-8111-000000000002")])
    retired = identity_pool.observe("aaaa0000-1111-4111-8111-000000000002",
                                    observation="identity_failure")
    require(retired.state == "retired" and retired.retirement_reason == "identity_failure",
            str(retired))

    # The consecutive provider/output failure streak is proven behaviorally
    # through the real pool in
    # `test_two_counted_failures_retire_a_conversation_through_the_real_pool`; a
    # hand-seeded streak would assert a state the pool can never actually reach.

    # Known context-window utilization at the committed threshold retires it.
    require(CONTEXT_WINDOW_RETIRE_PERCENT == 70, str(CONTEXT_WINDOW_RETIRE_PERCENT))
    below = pool()
    lease = checkout(below)
    returned = complete(below, lease, context_percent=CONTEXT_WINDOW_RETIRE_PERCENT - 1)
    require(returned.state == "idle", str(returned.state))
    above = pool()
    lease = checkout(above)
    returned = complete(above, lease, context_percent=CONTEXT_WINDOW_RETIRE_PERCENT)
    require(returned.state == "retired", str(returned.state))
    require(returned.retirement_reason == "known_context_window_threshold",
            str(returned.retirement_reason))
    require(returned.completed_assignment_count == 1,
            "the finished assignment still counted")

    # Three comparable latency samples at or above the multiplier retire it.
    require(LATENCY_RETIRE_SAMPLE_COUNT == 3 and LATENCY_RETIRE_MULTIPLIER == 2,
            f"{LATENCY_RETIRE_SAMPLE_COUNT}/{LATENCY_RETIRE_MULTIPLIER}")
    slow = LatencySample("crew_role_turnaround", 4000, 2000)
    latency_pool = pool()
    lease = checkout(latency_pool)
    for index in range(LATENCY_RETIRE_SAMPLE_COUNT):
        returned = complete(latency_pool, lease, now=at(index), latency=slow)
        if index < LATENCY_RETIRE_SAMPLE_COUNT - 1:
            require(returned.state == "idle", f"retired at sample {index + 1}")
            lease = checkout(latency_pool, run_id=f"nsc-050-run-{index + 2}", now=at(index))
    require(returned.state == "retired", str(returned.state))
    require(returned.retirement_reason == "sustained_comparable_latency",
            str(returned.retirement_reason))

    # A conversation whose next assignment would overflow the budget retires at
    # checkout instead of starting work it cannot finish within the budget.
    nearly = lifecycle_state(completed_assignments=8, worker_weighted_units=46)
    overflow_pool = pool(sessions=[seeded(nearly, compat=compatibility(capability_class="high_reasoning"),
                                          record_id="aaaa0000-1111-4111-8111-000000000002")])
    lease = checkout(overflow_pool, compat=compatibility(capability_class="high_reasoning"),
                     run_id="nsc-050-run-2", now=at(1))
    require(lease.mode == "start", "an overflowing conversation was offered")
    retired = overflow_pool.sessions_for("retired")
    require(len(retired) == 1, str(overflow_pool.sessions))
    require(retired[0].retirement_reason == "worker_weighted_unit_limit_would_be_exceeded",
            str(retired[0].retirement_reason))


def failed(session_pool: SessionPool, lease: AssignmentLease, *, outcome: str, now):
    """Check one exactly proven provider/output failure in through the real pool."""

    result, run_dir = durable(lease, status="failed", outcome=outcome)
    return session_pool.check_in(lease=lease, result=result, evidence_root=run_dir, now=now)


def test_two_counted_failures_retire_a_conversation_through_the_real_pool() -> None:
    # First failure: counted by the committed policy, never advertised, and held
    # for exactly one deliberate retry.
    session_pool = pool()
    lease = checkout(session_pool)
    session = failed(session_pool, lease, outcome="provider_failure", now=at(30))
    require(session.state == "probation", str(session.state))
    require(session.lifecycle.consecutive_provider_output_failures == 1,
            str(session.lifecycle.consecutive_provider_output_failures))
    require(session.retirement_reason is None, str(session.retirement_reason))
    require(session.quarantine_reason is None, "a probation session claimed a quarantine reason")
    require("failed" in (session.probation_reason or ""), str(session.probation_reason))
    require(not session.is_reusable_at(at(31)), "a failed conversation was advertised as reusable")
    require(session.is_retry_offerable_at(at(31)), "the pool cannot offer its own probation")

    # Nothing else can reach it: normal checkout starts a fresh conversation, and
    # a probation conversation is not an idle one to observe between assignments.
    other = checkout(session_pool, run_id="nsc-050-run-2", now=at(31))
    require(other.mode == "start", "probation was offered to an ordinary checkout")
    require(other.record_id != lease.record_id, "probation was handed out as a warm session")
    rejects(lambda: session_pool.observe(lease.record_id, observation="idle"), SessionPoolError)
    session_pool.quarantine(other, "fixture cleanup", outcome="other_failure")

    # Only a deliberate, exactly compatible retry may offer it, and only while it
    # is still on the idle clock.
    rejects(
        lambda: session_pool.offer_probation_retry(
            compatibility=compatibility(role="validator", capability_class="high_reasoning"),
            record_id=lease.record_id, worker_slot_id="worker-slot-1", task_id="NSC-050",
            worker_run_id="nsc-050-run-3", source_commit=COMMIT, checkout_identity=CHECKOUT,
            now=at(32),
        ),
        SessionPoolError,
    )
    rejects(
        lambda: session_pool.offer_probation_retry(
            compatibility=compatibility(), record_id=other.record_id,
            worker_slot_id="worker-slot-1", task_id="NSC-050", worker_run_id="nsc-050-run-3",
            source_commit=COMMIT, checkout_identity=CHECKOUT, now=at(32),
        ),
        SessionPoolError,
    )
    retry = session_pool.offer_probation_retry(
        compatibility=compatibility(), record_id=lease.record_id,
        worker_slot_id="worker-slot-1", task_id="NSC-050", worker_run_id="nsc-050-run-3",
        source_commit=COMMIT, checkout_identity=CHECKOUT, now=at(33),
    )
    require(retry.mode == "resume", "the controlled retry started a new conversation")
    require(retry.session_id == lease.session_id, "the controlled retry changed conversation")
    require(retry.record_id == lease.record_id, str(retry.record_id))
    # The retry is an ordinary active assignment: it cannot be offered twice and
    # cannot be interrupted.
    rejects(
        lambda: session_pool.offer_probation_retry(
            compatibility=compatibility(), record_id=lease.record_id,
            worker_slot_id="worker-slot-1", task_id="NSC-050", worker_run_id="nsc-050-run-4",
            source_commit=COMMIT, checkout_identity=CHECKOUT, now=at(34),
        ),
        SessionPoolError,
    )
    require(session_pool.expire_idle(now=at(100_000)) == (), "an active retry was expired")

    # Second consecutive counted failure: the committed policy retires it.
    retired = failed(session_pool, retry, outcome="output_failure", now=at(40))
    require(retired.state == "quarantined", str(retired.state))
    require(retired.retirement_reason == "consecutive_provider_output_failures",
            str(retired.retirement_reason))
    require(retired.lifecycle.consecutive_provider_output_failures == 2,
            str(retired.lifecycle.consecutive_provider_output_failures))
    require(not retired.is_reusable_at(at(41)) and not retired.is_retry_offerable_at(at(41)),
            "a retired conversation was still offerable")
    rejects(
        lambda: session_pool.offer_probation_retry(
            compatibility=compatibility(), record_id=lease.record_id,
            worker_slot_id="worker-slot-1", task_id="NSC-050", worker_run_id="nsc-050-run-5",
            source_commit=COMMIT, checkout_identity=CHECKOUT, now=at(41),
        ),
        SessionPoolError,
    )
    replacement = checkout(session_pool, run_id="nsc-050-run-6", now=at(42))
    require(replacement.mode == "start" and replacement.session_id != lease.session_id,
            "a retired conversation was reused")

    # A probation conversation expires on the same idle clock rather than being
    # offered a retry an hour later.
    stale = pool()
    stale_lease = checkout(stale)
    failed(stale, stale_lease, outcome="output_failure", now=at(0))
    require(stale.sessions[0].state == "probation", str(stale.sessions[0].state))
    rejects(
        lambda: stale.offer_probation_retry(
            compatibility=compatibility(), record_id=stale_lease.record_id,
            worker_slot_id="worker-slot-1", task_id="NSC-050", worker_run_id="nsc-050-run-2",
            source_commit=COMMIT, checkout_identity=CHECKOUT,
            now=at(IDLE_SESSION_LIFETIME_SECONDS),
        ),
        SessionPoolError,
    )
    require(stale.sessions[0].state == "expired", str(stale.sessions[0].state))


def test_an_evidenced_success_between_failures_resets_the_streak() -> None:
    session_pool = pool()
    lease = checkout(session_pool)
    session = failed(session_pool, lease, outcome="output_failure", now=at(10))
    require(session.state == "probation", str(session.state))

    retry = session_pool.offer_probation_retry(
        compatibility=compatibility(), record_id=lease.record_id,
        worker_slot_id="worker-slot-1", task_id="NSC-050", worker_run_id="nsc-050-run-2",
        source_commit=COMMIT, checkout_identity=CHECKOUT, now=at(11),
    )
    recovered = complete(session_pool, retry, now=at(12))
    require(recovered.state == "idle", str(recovered.state))
    require(recovered.lifecycle.consecutive_provider_output_failures == 0,
            "a fully evidenced assignment did not reset the streak")
    require(recovered.is_reusable_at(at(13)), "a recovered conversation was not reusable")

    # The next failure therefore starts the streak again instead of retiring.
    warm = checkout(session_pool, run_id="nsc-050-run-3", now=at(13))
    require(warm.mode == "resume" and warm.session_id == lease.session_id, str(warm))
    again = failed(session_pool, warm, outcome="provider_failure", now=at(14))
    require(again.state == "probation", str(again.state))
    require(again.retirement_reason is None,
            "an intervening success did not clear the earlier failure")
    require(again.lifecycle.consecutive_provider_output_failures == 1,
            str(again.lifecycle.consecutive_provider_output_failures))
    require(again.completed_assignment_count == 3, str(again.completed_assignment_count))


def restored(payload: dict) -> SessionPool:
    """Restore durable pool state exactly as a scheduler would."""

    return SessionPool.from_dict(json.loads(json.dumps(payload)),
                                 identity_factory=identity_factory(start=500),
                                 clock=lambda: BASE)


def probation_payload() -> tuple[dict, str]:
    """Return durable state holding one genuine probation, plus its record ID."""

    session_pool = pool()
    lease = checkout(session_pool)
    placed = failed(session_pool, lease, outcome="output_failure", now=at(30))
    require(placed.state == "probation", str(placed.state))
    payload = json.loads(json.dumps(session_pool.to_dict()))
    require(payload["sessions"][0]["lifecycle"]["consecutive_provider_output_failures"] == 1,
            str(payload["sessions"][0]["lifecycle"]))
    return payload, placed.record_id


def test_pool_state_and_lifecycle_state_cannot_disagree() -> None:
    # A genuine probation survives durable state as a probation, and is still
    # invisible to ordinary checkout after restoration.
    payload, record_id = probation_payload()
    session_pool = restored(payload)
    session = session_pool.sessions[0]
    require(session.state == "probation", str(session.state))
    require(not session.is_reusable_at(at(31)), "a restored probation was advertised")
    ordinary = checkout(session_pool, run_id="nsc-050-run-2", now=at(31))
    require(ordinary.mode == "start" and ordinary.record_id != record_id,
            "a restored probation was handed out by ordinary checkout")
    session_pool.quarantine(ordinary, "fixture cleanup", outcome="other_failure")
    retry = session_pool.offer_probation_retry(
        compatibility=compatibility(), record_id=record_id, worker_slot_id="worker-slot-1",
        task_id="NSC-050", worker_run_id="nsc-050-run-3", source_commit=COMMIT,
        checkout_identity=CHECKOUT, now=at(32),
    )
    require(retry.mode == "resume", "the restored probation refused its one deliberate retry")
    rejects(
        lambda: session_pool.offer_probation_retry(
            compatibility=compatibility(), record_id=record_id, worker_slot_id="worker-slot-1",
            task_id="NSC-050", worker_run_id="nsc-050-run-4", source_commit=COMMIT,
            checkout_identity=CHECKOUT, now=at(33),
        ),
        SessionPoolError,
    )

    # Re-labelling that exact conversation as ordinary idle is refused at the
    # restoration boundary, before any checkout can advertise it.
    forged, _ = probation_payload()
    forged["sessions"][0]["state"] = "idle"
    forged["sessions"][0]["probation_reason"] = None
    blocked = rejects(lambda: restored(forged), SessionPoolError)
    require("state 'idle' requires a counted failure streak of 0" in str(blocked),
            str(blocked))
    rejects(lambda: PooledSession.from_dict(forged["sessions"][0]), SessionPoolError)
    # The same contradiction is refused in memory, so nothing can construct it.
    genuine = restored(probation_payload()[0]).sessions[0]
    rejects(lambda: PooledSession(
        record_id=genuine.record_id, compatibility=genuine.compatibility, state="idle",
        session_id=genuine.session_id,
        completed_assignment_count=genuine.completed_assignment_count,
        idle_since_utc=genuine.idle_since_utc, lifecycle=genuine.lifecycle,
    ), SessionPoolError)
    # And a clean conversation may not claim probation either.
    clean = pool()
    clean_lease = checkout(clean)
    idle_session = complete(clean, clean_lease, now=at(30))
    blocked = rejects(lambda: PooledSession(
        record_id=idle_session.record_id, compatibility=idle_session.compatibility,
        state="probation", session_id=idle_session.session_id,
        completed_assignment_count=idle_session.completed_assignment_count,
        idle_since_utc=idle_session.idle_since_utc, probation_reason="claimed without a failure",
        lifecycle=idle_session.lifecycle,
    ), SessionPoolError)
    require("state 'probation' requires a counted failure streak of 1" in str(blocked),
            str(blocked))


def active_payload(*, resumed: bool = True) -> dict:
    """Return durable state holding one active assignment."""

    session_pool = pool()
    lease = checkout(session_pool)
    if not resumed:
        return json.loads(json.dumps(session_pool.to_dict()))
    complete(session_pool, lease, now=at(30))
    warm = checkout(session_pool, run_id="nsc-050-run-2", now=at(31))
    require(warm.mode == "resume", "the fixture did not resume a warm conversation")
    payload = json.loads(json.dumps(session_pool.to_dict()))
    require(payload["sessions"][0]["state"] == "active", str(payload["sessions"][0]["state"]))
    return payload


def test_an_active_assignment_cannot_contradict_its_own_history() -> None:
    # A genuinely fresh provider-named conversation legitimately has no
    # lifecycle yet, so the invariant must not refuse a real cold start.
    codex = compatibility(provider="openai-codex", model=CODEX_MODEL, reasoning="high")
    cold = pool()
    cold_lease = cold.checkout(compatibility=codex, worker_slot_id="worker-slot-1",
                               task_id="NSC-050", worker_run_id="nsc-050-run-1",
                               source_commit=COMMIT, checkout_identity=CHECKOUT, now=BASE)
    require(cold_lease.mode == "start" and cold_lease.session_id is None, str(cold_lease))
    require(restored(cold.to_dict()).sessions[0].lifecycle is None, "a cold start was refused")

    # A warm resume may not drop its accounted history and restart at zero.
    payload = active_payload()
    require(payload["sessions"][0]["active_lease"]["mode"] == "resume",
            str(payload["sessions"][0]["active_lease"]["mode"]))
    require(payload["sessions"][0]["completed_assignment_count"] == 1,
            str(payload["sessions"][0]["completed_assignment_count"]))
    forged = json.loads(json.dumps(payload))
    forged["sessions"][0]["lifecycle"] = None
    blocked = rejects(lambda: restored(forged), SessionPoolError)
    require("only a fresh start lease may hold no lifecycle state" in str(blocked), str(blocked))

    # The lease's prior count must equal the conversation's accounted history.
    forged = json.loads(json.dumps(payload))
    forged["sessions"][0]["active_lease"]["prior_completed_assignment_count"] = 0
    blocked = rejects(lambda: restored(forged), SessionPoolError)
    require("prior assignment count differs" in str(blocked), str(blocked))

    # The assigned workload must be the workload this session's capability class
    # actually costs, so a standard session cannot be accounted as fast work.
    forged = json.loads(json.dumps(payload))
    lifecycle = forged["sessions"][0]["lifecycle"]
    require(lifecycle["active_workload_class"] == "standard", str(lifecycle))
    lifecycle["active_workload_class"] = "fast"
    lifecycle["active_weighted_units"] = WORKER_WEIGHTS["fast"]
    blocked = rejects(lambda: restored(forged), SessionPoolError)
    require("workload class differs from its session compatibility" in str(blocked), str(blocked))

    # Retired and quarantined records stay internally consistent too.
    genuine_probation, _ = probation_payload()
    between = genuine_probation["sessions"][0]["lifecycle"]
    for label, mutation in (
        ("retired without a retirement decision",
         {"state": "retired", "probation_reason": None, "idle_since_utc": None}),
        ("retired but still idle-timed",
         {"state": "retired", "probation_reason": None}),
        ("quarantined but still idle-timed",
         {"state": "quarantined", "probation_reason": None,
          "quarantine_reason": "fixture"}),
    ):
        forged = json.loads(json.dumps(genuine_probation))
        forged["sessions"][0].update(mutation)
        require(forged["sessions"][0]["lifecycle"] == between, f"{label}: fixture drifted")
        rejects(lambda forged=forged: restored(forged), SessionPoolError)
    # A quarantined record may not hold an assigned lifecycle either.
    forged = active_payload()
    forged["sessions"][0].update({"state": "quarantined", "quarantine_reason": "fixture",
                                  "active_lease": None})
    rejects(lambda: restored(forged), SessionPoolError)


def test_retirement_never_interrupts_an_active_assignment() -> None:
    session_pool = pool()
    lease = checkout(session_pool, now=at(0))
    # Nothing between-assignments may be applied while the worker holds its lease.
    blocked = rejects(
        lambda: session_pool.observe(lease.record_id, observation="identity_failure"),
        SessionPoolError,
    )
    require("never interrupted" in str(blocked), str(blocked))
    rejects(lambda: session_pool.observe(lease.record_id, observation="idle"), SessionPoolError)
    require(session_pool.expire_idle(now=at(86_400)) == (), "an active assignment was expired")
    require(session_pool.sessions[0].state == "active", str(session_pool.sessions[0].state))
    # A conversation already at its budget still finishes the assignment it holds.
    exhausted = lifecycle_state(completed_assignments=15, worker_weighted_units=45)
    ready = pool(sessions=[seeded(exhausted, compat=compatibility(),
                                  record_id="aaaa0000-1111-4111-8111-000000000002")])
    last = checkout(ready, run_id="nsc-050-run-2", now=at(1))
    require(last.mode == "resume", "the seeded conversation was not offered")
    require(ready.sessions[0].state == "active", str(ready.sessions[0].state))
    require(ready.expire_idle(now=at(100_000)) == (), "an exhausted active assignment was expired")
    returned = complete(ready, last, now=at(2))
    require(returned.state == "retired", str(returned.state))
    require(returned.completed_assignment_count == 16, str(returned.completed_assignment_count))


# ------------------------------------------------------- 24: no termination


def test_no_pool_code_path_terminates_a_worker() -> None:
    source = Path(ROOT / "Pipeline/ExecutionCrew/session_pool.py").read_text(encoding="utf-8")
    require(process_control_hits(source) == [],
            f"the pool references process control: {process_control_hits(source)}")
    targets = ("checkout", "check_in", "quarantine", "observe", "expire_idle", "_quarantine",
               "_finish")
    for name in targets:
        body = inspect.getsource(getattr(SessionPool, name))
        require(process_control_hits(body) == [],
                f"SessionPool.{name} references {process_control_hits(body)}")
    # The scan must actually catch a forbidden operation injected into one of
    # those exact methods, or this regression would be vacuous.
    clean = inspect.getsource(SessionPool.check_in)
    anchor = "        session = self._leased_session(lease)"
    require(clean.count(anchor) == 1, "the injection anchor is no longer unique")
    injected = clean.replace(
        anchor,
        anchor + "\n        subprocess.run(('kill', '-9', str(worker_pid)), check=False)",
    )
    require(injected != clean, "the injection did not change the method source")
    require(process_control_hits(injected) == ["kill", "subprocess"],
            f"the scan missed an injected operation: {process_control_hits(injected)}")
    require(
        "never touch a running worker" in source and "terminates nothing" in source,
        "the pool does not state its no-termination contract",
    )


def test_pool_schema_identity_is_pinned() -> None:
    require(POOL_SCHEMA_VERSION == "1.0", POOL_SCHEMA_VERSION)
    require(CREW_SESSION_PROTOCOL_VERSION == "1.0", CREW_SESSION_PROTOCOL_VERSION)
    require(DURABLE_ASSIGNMENT_RESULT_SCHEMA_VERSION == "1.0",
            DURABLE_ASSIGNMENT_RESULT_SCHEMA_VERSION)
    expected = (
        "pool_schema_version", "lease_id", "record_id", "session_id", "mode",
        "provider_identifier", "model", "reasoning_effort", "session_class", "role",
        "capability_class", "repository_identity", "protocol_version",
        "worker_slot_id", "task_id", "worker_run_id", "source_commit",
        "checkout_identity", "checked_out_at_utc", "prior_completed_assignment_count",
    )
    require(tuple(AssignmentLease.__dataclass_fields__) == expected,
            str(tuple(AssignmentLease.__dataclass_fields__)))
    require(ROLE_EVIDENCE_SCHEMA_VERSION == "1.0", ROLE_EVIDENCE_SCHEMA_VERSION)
    require(ROLE_EVIDENCE_FIELDS == (
        "schema_version", "pool_schema_version", "protocol_version", "crew_run_id",
        "lease_id", "record_id", "task_id", "worker_run_id", "worker_slot_id",
        "session_class", "role", "capability_class", "repository_identity",
        "source_commit", "checkout_identity", "provider_identifier", "model",
        "reasoning_effort", "confirmed_session", "status", "assignment_outcome",
        "semantic_validation", "changed_path_validation", "role_result_artifact",
    ), str(ROLE_EVIDENCE_FIELDS))
    require("probation" in SESSION_STATES, str(sorted(SESSION_STATES)))
    require(tuple(PooledSession.__dataclass_fields__) == (
        "record_id", "compatibility", "state", "session_id",
        "completed_assignment_count", "idle_since_utc", "active_lease",
        "quarantine_reason", "probation_reason", "lifecycle",
    ), str(tuple(PooledSession.__dataclass_fields__)))
    # A probation conversation survives durable state exactly as it was placed.
    probation_pool = pool()
    probation_lease = checkout(probation_pool)
    placed = failed(probation_pool, probation_lease, outcome="output_failure", now=at(5))
    restored = SessionPool.from_dict(json.loads(json.dumps(probation_pool.to_dict())))
    require(restored.sessions[0] == placed, str(restored.sessions[0]))
    session_pool = pool()
    lease = checkout(session_pool)
    require(AssignmentLease.from_dict(lease.to_dict()) == lease, "lease round trip failed")
    rejects(lambda: AssignmentLease.from_dict({**lease.to_dict(), "extra": 1}), SessionPoolError)
    rejects(lambda: AssignmentLease.from_dict({**lease.to_dict(), "mode": "continue"}), SessionPoolError)
    rejects(lambda: AssignmentLease.from_dict({**lease.to_dict(), "source_commit": "abc"}), SessionPoolError)
    require(RESUMED_AUTHORITY_NOTICE, "the provider-neutral revocation notice is missing")


TESTS = (
    test_a_returned_implementer_session_is_reused_as_an_implementer,
    test_reuse_resumes_rather_than_creating_a_second_provider_session,
    test_claude_and_codex_pools_remain_separate,
    test_every_crew_role_keeps_its_own_pool,
    test_model_or_reasoning_change_creates_a_fresh_session,
    test_an_active_session_is_never_checked_out_twice,
    test_ten_concurrent_assignments_receive_ten_unique_leases,
    test_exact_matching_check_in_returns_the_session,
    test_stale_or_mismatched_check_in_fails_closed,
    test_provider_failure_quarantines_the_session,
    test_missing_durable_result_prevents_reuse,
    test_missing_or_tampered_role_evidence_prevents_reuse,
    test_role_evidence_is_inseparable_from_its_exact_assignment,
    test_an_unproven_confirmation_never_replaces_a_trusted_identity,
    test_idle_sessions_expire_after_exactly_one_hour,
    test_active_sessions_are_never_expired_or_stolen,
    test_a_reused_session_receives_the_authority_revocation_capsule,
    test_prior_allowed_paths_are_not_current_allowed_paths,
    test_existing_ephemeral_crew_behavior_is_unchanged_without_pool_arguments,
    test_repair_attempts_retain_the_roles_leased_session,
    test_a_retry_cannot_inherit_an_unrelated_execution,
    test_pool_persistence_is_atomic_and_malformed_state_fails_closed,
    test_a_nested_session_protocol_must_match_the_crew_protocol,
    test_durable_assignment_results_round_trip_and_fail_closed,
    test_worker_budget_is_exactly_forty_eight_weighted_units,
    test_architect_retires_after_exactly_one_hundred_cycles,
    test_idle_and_waiting_cost_nothing,
    test_every_early_retirement_condition_is_enforced,
    test_two_counted_failures_retire_a_conversation_through_the_real_pool,
    test_an_evidenced_success_between_failures_resets_the_streak,
    test_pool_state_and_lifecycle_state_cannot_disagree,
    test_an_active_assignment_cannot_contradict_its_own_history,
    test_retirement_never_interrupts_an_active_assignment,
    test_no_pool_code_path_terminates_a_worker,
    test_pool_schema_identity_is_pinned,
)


def main(argv: list[str] | None = None) -> int:
    selected = set(argv or [])
    with _EVIDENCE:
        for test in TESTS:
            if selected and test.__name__ not in selected:
                continue
            test()
            print(f"PASS {test.__name__}")
    print("session_pool_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
