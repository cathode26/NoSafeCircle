#!/usr/bin/env python3
"""Deterministic tests for the role-scoped ExecutionCrew session pool.

Classification: pure/component tests over the pool state machine, its durable
store, and ExecutionCrew's lease wiring. Clocks and session identities are
injected, no provider is contacted, no process is started, and no repository
file is touched. Every test proves an explicit regression-only invariant.

The load-bearing claims are: a conversation is reusable only for the same role
with the same stable provider/model/reasoning/capability/repository identity; a
checked-out session is invisible to everyone else; only an exact matching
durable result returns one; anything unproven quarantines; idle reuse ends at
exactly one hour while active leases are never touched; and nothing in the pool
ever terminates a worker.
"""

from __future__ import annotations

import datetime as dt
import inspect
import itertools
import json
from pathlib import Path
import re
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.provider_sessions import (  # noqa: E402
    RESUMED_AUTHORITY_NOTICE,
    ProviderSessionBinding,
    ProviderSessionConfirmation,
)
from Pipeline.ExecutionCrew import run_crew as crew_module  # noqa: E402
from Pipeline.ExecutionCrew.run_crew import (  # noqa: E402
    CrewBlocked,
    repair_attempt_session,
    validate_role_session_leases,
)
from Pipeline.ExecutionCrew.session_pool import (  # noqa: E402
    CREW_SESSION_PROTOCOL_VERSION,
    CREW_SESSION_ROLES,
    DEFAULT_MAX_CONCURRENT_ASSIGNMENTS,
    IDLE_SESSION_LIFETIME_SECONDS,
    POOL_SCHEMA_VERSION,
    AssignmentLease,
    DurableAssignmentResult,
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


def identity_factory():
    counter = itertools.count(1)

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
) -> SessionCompatibility:
    return SessionCompatibility(
        provider, model, reasoning, role, capability_class, repository, protocol
    )


def checkout(
    session_pool: SessionPool,
    *,
    compat: SessionCompatibility | None = None,
    slot: str = "worker-slot-1",
    task_id: str = "NSC-050",
    run_id: str = "nsc-050-run-1",
    commit: str = COMMIT,
    checkout_identity: str = r"C:\NSC\NSC\NSC-050",
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


def durable(
    lease: AssignmentLease,
    *,
    session_id: str | None = None,
    status: str = "completed",
    changed_paths: str = "accepted",
    **overrides,
) -> DurableAssignmentResult:
    confirmed = ProviderSessionConfirmation(
        overrides.pop("confirmed_provider", lease.provider_identifier),
        overrides.pop("confirmed_role", lease.role),
        overrides.pop("confirmed_mode", lease.mode),
        session_id or lease.session_id or "cafe0000-1111-4111-8111-000000000001",
    )
    values = {
        "lease_id": lease.lease_id,
        "task_id": lease.task_id,
        "worker_run_id": lease.worker_run_id,
        "role": lease.role,
        "provider_identifier": lease.provider_identifier,
        "model": lease.model,
    }
    values.update(overrides)
    return DurableAssignmentResult(
        status=status, changed_path_validation=changed_paths,
        confirmed_session=confirmed, **values,
    )


def complete(session_pool: SessionPool, lease: AssignmentLease, *, now=None, **values):
    return session_pool.check_in(lease=lease, result=durable(lease, **values), now=now or BASE)


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
    keys = {role: compatibility(role=role).key() for role in CREW_SESSION_ROLES}
    require(len(set(keys.values())) == len(CREW_SESSION_ROLES), f"roles collide: {keys}")
    session_pool = pool()
    warmed = compatibility(role="implementer")
    complete(session_pool, checkout(session_pool, compat=warmed))
    for role in CREW_SESSION_ROLES:
        if role == "implementer":
            continue
        lease = checkout(session_pool, compat=compatibility(role=role), now=at(60))
        require(lease.mode == "start", f"{role} was offered the implementer conversation")
        require(lease.role == role, str(lease.role))


def test_model_or_reasoning_change_creates_a_fresh_session() -> None:
    for changed in (
        compatibility(model="claude-opus-4-1-20260101"),
        compatibility(reasoning="xhigh"),
        compatibility(capability_class="high_reasoning"),
        compatibility(repository="https://github.com/cathode26/Other.git"),
        compatibility(protocol="9.9"),
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


def test_stale_or_mismatched_check_in_fails_closed() -> None:
    for field, value in (
        ("lease_id", "dead0000-1111-4111-8111-000000000001"),
        ("task_id", "NSC-999"),
        ("worker_run_id", "nsc-999-run-9"),
        ("role", "validator"),
        ("provider_identifier", "openai-codex"),
        ("model", "claude-other-1"),
        ("confirmed_role", "validator"),
        ("confirmed_provider", "openai-codex"),
        ("confirmed_mode", "resume"),
    ):
        session_pool = pool()
        lease = checkout(session_pool)
        session = session_pool.check_in(
            lease=lease, result=durable(lease, **{field: value}), now=at(30)
        )
        require(session.state == "quarantined", f"{field} mismatch was accepted")
        require("did not match its lease" in (session.quarantine_reason or ""),
                str(session.quarantine_reason))
        require(not session.is_reusable_at(at(31)), "a quarantined session stayed reusable")
    # A confirmation naming a different conversation is equally fatal.
    session_pool = pool()
    lease = checkout(session_pool)
    complete(session_pool, lease)
    warm = checkout(session_pool, run_id="nsc-050-run-2", now=at(60))
    session = session_pool.check_in(
        lease=warm,
        result=durable(warm, session_id="dead0000-1111-4111-8111-000000000002"),
        now=at(90),
    )
    require(session.state == "quarantined", "a different confirmed session was accepted")
    # A lease that is no longer the session's active lease is stale.
    session_pool = pool()
    lease = checkout(session_pool)
    complete(session_pool, lease)
    rejects(lambda: complete(session_pool, lease), SessionPoolError)


def test_provider_failure_quarantines_the_session() -> None:
    for reason in (
        "provider transport failure",
        "timeout with uncertain provider state",
        "missing or malformed provider-session identity",
    ):
        session_pool = pool()
        lease = checkout(session_pool)
        session = session_pool.quarantine(lease, reason)
        require(session.state == "quarantined" and session.quarantine_reason == reason, str(session))
        require(session_pool.active_assignment_count == 0, "quarantine kept the lease active")
        fresh = checkout(session_pool, run_id="nsc-050-run-2", now=at(60))
        require(fresh.mode == "start", "a quarantined conversation was reused")
    # A rejected deterministic changed-path check must not recycle either.
    session_pool = pool()
    lease = checkout(session_pool)
    session = session_pool.check_in(
        lease=lease, result=durable(lease, changed_paths="rejected"), now=at(30)
    )
    require(session.state == "quarantined", "rejected changed paths were recycled")
    require("changed paths rejected" in (session.quarantine_reason or ""), str(session.quarantine_reason))


def test_missing_durable_result_prevents_reuse() -> None:
    session_pool = pool()
    lease = checkout(session_pool)
    session = session_pool.check_in(lease=lease, result=None, now=at(30))
    require(session.state == "quarantined", "a missing durable result was accepted")
    require("no durable assignment result" in (session.quarantine_reason or ""),
            str(session.quarantine_reason))
    # A failed status is not reusable even when the identity all matches.
    session_pool = pool()
    lease = checkout(session_pool)
    session = session_pool.check_in(lease=lease, result=durable(lease, status="failed"), now=at(30))
    require(session.state == "quarantined", "a failed assignment recycled its session")
    rejects(lambda: durable(lease, status="unknown"), SessionPoolError)
    rejects(lambda: durable(lease, changed_paths="maybe"), SessionPoolError)


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
        first, checkout_root=r"C:\NSC\NSC\NSC-050", capabilities=("repository_write",),
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
    require(validate_role_session_leases(None, task_id="NSC-050", run_id="r", provider_identifier="claude-code",
                                         model=CLAUDE_MODEL, reasoning_effort=None) == {},
            "absent leases produced bindings")
    require(validate_role_session_leases({}, task_id="NSC-050", run_id="r", provider_identifier="claude-code",
                                         model=CLAUDE_MODEL, reasoning_effort=None) == {},
            "empty leases produced bindings")
    signature = inspect.signature(crew_module.run_crew)
    for name in ("role_session_leases", "role_session_bindings", "codex_resume_sandbox_argument"):
        require(signature.parameters[name].default is None, f"{name} is not optional")
    source = inspect.getsource(crew_module.run_crew)
    require("supply role session bindings or pooled leases, not both" in source,
            "the crew accepts both session mechanisms at once")
    require("pooled role session leases require the exact worker run ID" in source,
            "pooled leases do not pin the worker run ID")


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


def test_a_retry_cannot_inherit_an_unrelated_tasks_session() -> None:
    session_pool = pool()
    lease = checkout(session_pool, task_id="NSC-050", run_id="nsc-050-run-1")
    common = {"provider_identifier": "claude-code", "model": CLAUDE_MODEL, "reasoning_effort": None}
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
    rejects(lambda: validate_role_session_leases({"validator": lease}, task_id="NSC-050",
                                                 run_id="nsc-050-run-1", **common), CrewBlocked)
    rejects(lambda: validate_role_session_leases({"implementer": lease}, task_id="NSC-050",
                                                 run_id="nsc-050-run-1",
                                                 provider_identifier="openai-codex",
                                                 model=CLAUDE_MODEL, reasoning_effort=None), CrewBlocked)
    rejects(lambda: validate_role_session_leases({"implementer": lease}, task_id="NSC-050",
                                                 run_id="nsc-050-run-1",
                                                 provider_identifier="claude-code",
                                                 model="claude-other-1", reasoning_effort=None), CrewBlocked)
    rejects(lambda: validate_role_session_leases({"implementer": lease}, task_id="NSC-050",
                                                 run_id="nsc-050-run-1",
                                                 provider_identifier="claude-code",
                                                 model=CLAUDE_MODEL, reasoning_effort="high"), CrewBlocked)
    rejects(lambda: validate_role_session_leases({"implementer": "lease"}, task_id="NSC-050",
                                                 run_id="nsc-050-run-1", **common), CrewBlocked)


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
        rejects(lambda: store.save("not-a-pool"), SessionPoolError)
    # Mutable pool state must never be stored inside the repository.
    rejects(lambda: SessionPoolStore(ROOT / "Pipeline" / "pool.json"), SessionPoolError)


# ------------------------------------------------------- 20: no termination


def test_no_pool_code_path_terminates_a_worker() -> None:
    source = Path(ROOT / "Pipeline/ExecutionCrew/session_pool.py").read_text(encoding="utf-8")
    banned = (
        "kill", "terminate", "SIGKILL", "SIGTERM", "taskkill", "Popen",
        "subprocess", "os.system", "signal", "docker", "psutil",
    )
    for word in banned:
        require(
            re.search(rf"\b{re.escape(word)}\b", source) is None,
            f"the pool references process control: {word}",
        )
    # Returning and expiring are pure state transitions on the pool's own record.
    for name in ("check_in", "quarantine", "expire_idle", "_quarantine"):
        body = inspect.getsource(getattr(SessionPool, name))
        for word in banned:
            require(
                re.search(rf"{re.escape(word)}", body) is None,
                f"SessionPool.{name} references {word}",
            )
    require(
        "never touch a running worker" in source and "terminates nothing" in source,
        "the pool does not state its no-termination contract",
    )


def test_pool_schema_identity_is_pinned() -> None:
    require(POOL_SCHEMA_VERSION == "1.0", POOL_SCHEMA_VERSION)
    require(CREW_SESSION_PROTOCOL_VERSION == "1.0", CREW_SESSION_PROTOCOL_VERSION)
    expected = (
        "pool_schema_version", "lease_id", "record_id", "session_id", "mode",
        "provider_identifier", "model", "reasoning_effort", "role",
        "capability_class", "repository_identity", "protocol_version",
        "worker_slot_id", "task_id", "worker_run_id", "source_commit",
        "checkout_identity", "checked_out_at_utc", "prior_completed_assignment_count",
    )
    require(tuple(AssignmentLease.__dataclass_fields__) == expected,
            str(tuple(AssignmentLease.__dataclass_fields__)))
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
    test_idle_sessions_expire_after_exactly_one_hour,
    test_active_sessions_are_never_expired_or_stolen,
    test_a_reused_session_receives_the_authority_revocation_capsule,
    test_prior_allowed_paths_are_not_current_allowed_paths,
    test_existing_ephemeral_crew_behavior_is_unchanged_without_pool_arguments,
    test_repair_attempts_retain_the_roles_leased_session,
    test_a_retry_cannot_inherit_an_unrelated_tasks_session,
    test_pool_persistence_is_atomic_and_malformed_state_fails_closed,
    test_no_pool_code_path_terminates_a_worker,
    test_pool_schema_identity_is_pinned,
)


def main(argv: list[str] | None = None) -> int:
    selected = set(argv or [])
    for test in TESTS:
        if selected and test.__name__ not in selected:
            continue
        test()
        print(f"PASS {test.__name__}")
    print("session_pool_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
