#!/usr/bin/env python3
"""Deterministic tests for the provider-neutral durable session pool.

No provider, process, network, or repository access occurs. Every test drives
the pool with explicit clocks, identities, and settlements.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.durable_session_pool import (  # noqa: E402
    DURABLE_SESSION_POOL_SCHEMA_VERSION,
    AssignmentSettlement,
    DurableSessionPool,
    DurableSessionPoolError,
    DurableSessionPoolStore,
    SessionLifetimePolicy,
    SessionRecord,
    SessionScope,
    authority_capsule,
    resume_contract_fingerprint,
)
from Pipeline.AgentRuntime.provider_sessions import ProviderSessionConfirmation  # noqa: E402
from Pipeline.AgentRuntime.session_lifecycle import (  # noqa: E402
    ARCHITECT_COMPLETED_CYCLE_LIMIT,
    SessionLifecycleState,
)


SESSION_A = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
SESSION_B = "9c858901-8a57-4791-81fe-4c455b099bc9"
RESUME = resume_contract_fingerprint(("-c", 'sandbox_mode="danger-full-access"'))
T0 = dt.datetime(2026, 9, 4, 12, 0, tzinfo=dt.timezone.utc)
LIFETIME = SessionLifetimePolicy(max_age_seconds=14 * 86400, idle_lifetime_seconds=7 * 86400)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action: Any, expected: type[BaseException], fragment: str = "") -> BaseException:
    try:
        action()
    except expected as exc:
        require(fragment in str(exc), f"expected {fragment!r} in {exc}")
        return exc
    raise AssertionError(f"expected {expected.__name__}")


def identities(*values: str):
    queue = list(values)

    def factory() -> str:
        if not queue:
            raise AssertionError("identity factory exhausted")
        return queue.pop(0)

    return factory


def scope(**overrides: Any) -> SessionScope:
    values: dict[str, Any] = dict(
        protocol_version="1.0", provider_identifier="openai-codex", role="task_supervisor",
        session_class="architect", workload_class="admission_cycle", model="gpt-5.6-sol",
        reasoning_effort="high", repository_identity="https://github.com/x/y.git",
        resume_contract=RESUME, bindings=(("task_id", "NSC-914"),),
    )
    values.update(overrides)
    return SessionScope(**values)


def worker_scope(**overrides: Any) -> SessionScope:
    values: dict[str, Any] = dict(
        protocol_version="1.0", provider_identifier="claude-code", role="task_decomposer",
        session_class="worker", workload_class="deep", model="claude-sonnet-5",
        reasoning_effort=None, repository_identity="https://github.com/x/y.git",
    )
    values.update(overrides)
    return SessionScope(**values)


def confirmation(session_id: str, *, mode: str, scope_value: SessionScope | None = None) -> ProviderSessionConfirmation:
    value = scope_value or scope()
    return ProviderSessionConfirmation(value.provider_identifier, value.role, mode, session_id)


def settle(lease, outcome="completed", *, confirmed=None, percent=None, detail="ok", evidence=()):
    return AssignmentSettlement(
        pool_schema_version=DURABLE_SESSION_POOL_SCHEMA_VERSION, lease_id=lease.lease_id,
        record_id=lease.record_id, outcome=outcome, confirmed_session=confirmed,
        known_context_window_percent=percent, evidence=evidence, detail=detail,
    )


def pool(*ids: str, events: list | None = None, **kwargs: Any) -> DurableSessionPool:
    return DurableSessionPool(
        lifetime=LIFETIME, clock=lambda: T0, identity_factory=identities(*ids) if ids else None,
        event_sink=None if events is None else events.append, **kwargs,
    )


def test_scope_key_binds_every_identity_fact() -> None:
    base = scope()
    for name, value in (
        ("protocol_version", "2.0"), ("model", "gpt-other"), ("reasoning_effort", "low"),
        ("repository_identity", "https://github.com/x/z.git"), ("bindings", (("task_id", "NSC-915"),)),
        ("resume_contract", resume_contract_fingerprint(("-c", "sandbox_mode=\"read-only\""))),
    ):
        other = scope(**{name: value})
        require(other.key() != base.key() and other != base, f"{name} was not part of the scope key")
    require(base.binding("task_id") == "NSC-914" and base.binding("nope") is None, "binding lookup")
    rejects(lambda: scope(resume_contract=None), DurableSessionPoolError, "verified resume control")
    rejects(lambda: scope(session_class="worker"), DurableSessionPoolError, "admission cycles")
    rejects(lambda: scope(provider_identifier="fake"), DurableSessionPoolError, "unsupported pool provider")
    require(worker_scope().resume_contract is None, "claude needs no resume control")
    require(SessionScope.from_dict(base.to_dict()) == base, "scope round trip")
    rejects(lambda: resume_contract_fingerprint(("",)), DurableSessionPoolError, "non-empty")
    require(
        resume_contract_fingerprint(("-c", "a=b")) != resume_contract_fingerprint(("-c a=b",)),
        "element boundaries must be part of the fingerprint",
    )


def test_cold_start_adopts_confirmed_identity_and_resumes_exactly() -> None:
    events: list[dict[str, Any]] = []
    p = pool("1ea5e111-1111-4111-8111-111111111111", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
             "1ea5e222-2222-4222-8222-222222222222", events=events)
    lease = p.checkout(scope=scope(), assignment={"run_id": "r1", "turn": "1"}, exclusive=True)
    require(lease.mode == "start" and lease.session_id is None, "codex cold lease must carry no identity")
    require(lease.binding().mode == "start" and lease.binding().session_id is None, "binding")
    require(p.session(lease.record_id).lifecycle is None, "no lifecycle before proof")
    record = p.check_in(lease=lease, settlement=settle(lease, confirmed=confirmation(SESSION_A, mode="start")))
    require(record.state == "idle" and record.session_id == SESSION_A, f"adopt on confirm: {record}")
    require(record.completed_assignment_count == 1 and record.lifecycle.architect_completed_admission_cycles == 1, "accounted")
    warm = p.checkout(scope=scope(), assignment={"run_id": "r1", "turn": "2"}, exclusive=True, now=T0 + dt.timedelta(minutes=5))
    require(warm.mode == "resume" and warm.session_id == SESSION_A and warm.record_id == lease.record_id, "exact resume")
    require(warm.prior_completed_assignment_count == 1, "history travels on the lease")
    require([e["event"] for e in events] == ["cold_start", "check_in", "resume"], [e["event"] for e in events])
    require(all("prompt" not in json.dumps(e) for e in events), "journal never carries prompts")


def test_missing_or_mismatched_confirmation_never_becomes_identity() -> None:
    p = pool()
    cold = p.checkout(scope=scope(), assignment={"run_id": "r1"})
    record = p.check_in(lease=cold, settlement=settle(cold, confirmed=None))
    require(record.state == "quarantined" and record.session_id is None and record.lifecycle is None, str(record))
    require("no confirmed session identity" in record.quarantine_reason, record.quarantine_reason)
    require(not p.sessions_in_scope(scope())[0].state == "idle", "quarantined is never offered")
    # A warm conversation whose transcript names another thread retires for identity failure.
    p2 = pool()
    first = p2.checkout(scope=scope(), assignment={"run_id": "r1"})
    p2.check_in(lease=first, settlement=settle(first, confirmed=confirmation(SESSION_A, mode="start")))
    warm = p2.checkout(scope=scope(), assignment={"run_id": "r2"})
    record = p2.check_in(lease=warm, settlement=settle(warm, confirmed=confirmation(SESSION_B, mode="resume")))
    require(record.state == "retired" and record.retirement_reason == "identity_failure", str(record))
    # Mode, role, and provider disagreements are contradictions too.
    for bad in (
        confirmation(SESSION_A, mode="start"),
        ProviderSessionConfirmation("openai-codex", "implementer", "resume", SESSION_A),
    ):
        p3 = pool()
        first = p3.checkout(scope=scope(), assignment={"run_id": "r1"})
        p3.check_in(lease=first, settlement=settle(first, confirmed=confirmation(SESSION_A, mode="start")))
        warm = p3.checkout(scope=scope(), assignment={"run_id": "r2"})
        settled = p3.check_in(lease=warm, settlement=settle(warm, confirmed=bad))
        require(settled.state == "retired" and settled.retirement_reason == "identity_failure", str(settled))
    fresh = p2.checkout(scope=scope(), assignment={"run_id": "r3"})
    require(fresh.mode == "start" and fresh.record_id != warm.record_id, "identity failure is never resumed")


def test_uncertain_outcomes_retire_and_are_never_resumed() -> None:
    p = pool()
    first = p.checkout(scope=scope(), assignment={"run_id": "r1"})
    p.check_in(lease=first, settlement=settle(first, confirmed=confirmation(SESSION_A, mode="start")))
    warm = p.checkout(scope=scope(), assignment={"run_id": "r2"})
    record = p.check_in(lease=warm, settlement=settle(warm, "uncertain", confirmed=None, detail="timeout"))
    require(record.state == "retired" and record.retirement_reason == "interrupted_assignment", str(record))
    require(p.checkout(scope=scope(), assignment={"run_id": "r3"}).mode == "start", "cold after uncertainty")
    cold = pool()
    lease = cold.checkout(scope=scope(), assignment={"run_id": "r1"})
    record = cold.check_in(lease=lease, settlement=settle(lease, "uncertain", detail="transport"))
    require(record.state == "quarantined" and record.session_id is None, "cold uncertainty quarantines without identity")


def test_interrupted_active_lease_is_retired_only_as_interruption() -> None:
    p = pool()
    first = p.checkout(scope=scope(), assignment={"run_id": "r1"})
    p.check_in(lease=first, settlement=settle(first, confirmed=confirmation(SESSION_A, mode="start")))
    stranded = p.checkout(scope=scope(), assignment={"run_id": "r2"}, exclusive=True)
    rejects(lambda: p.checkout(scope=scope(), assignment={"run_id": "r3"}, exclusive=True),
            DurableSessionPoolError, "already holds an active lease")
    record = p.retire_interrupted(stranded, detail="owner died")
    require(record.state == "retired" and record.retirement_reason == "interrupted_assignment", str(record))
    require(p.is_settled(stranded.lease_id), "interruption settles the lease")
    rejects(lambda: p.check_in(lease=stranded, settlement=settle(stranded, confirmed=confirmation(SESSION_A, mode="resume"))),
            DurableSessionPoolError, "different content")
    cold = p.checkout(scope=scope(), assignment={"run_id": "r3"}, exclusive=True)
    require(cold.mode == "start", "an interrupted conversation is never resumed")


def test_counted_failures_go_to_probation_then_retire() -> None:
    p = pool()
    first = p.checkout(scope=scope(), assignment={"run_id": "r1"})
    p.check_in(lease=first, settlement=settle(first, confirmed=confirmation(SESSION_A, mode="start")))
    warm = p.checkout(scope=scope(), assignment={"run_id": "r2"})
    record = p.check_in(lease=warm, settlement=settle(warm, "provider_failure", confirmed=confirmation(SESSION_A, mode="resume"), detail="exit 1"))
    require(record.state == "probation" and record.lifecycle.consecutive_provider_output_failures == 1, str(record))
    require(p.checkout(scope=scope(), assignment={"run_id": "r3"}).mode == "start", "probation is invisible to a plain checkout")
    p2 = pool()
    first = p2.checkout(scope=scope(), assignment={"run_id": "r1"})
    p2.check_in(lease=first, settlement=settle(first, confirmed=confirmation(SESSION_A, mode="start")))
    warm = p2.checkout(scope=scope(), assignment={"run_id": "r2"})
    p2.check_in(lease=warm, settlement=settle(warm, "output_failure", confirmed=confirmation(SESSION_A, mode="resume")))
    retry = p2.checkout(scope=scope(), assignment={"run_id": "r3"}, allow_probation_retry=True)
    require(retry.mode == "resume" and retry.probation_retry and retry.session_id == SESSION_A, "one deliberate retry")
    record = p2.check_in(lease=retry, settlement=settle(retry, "provider_failure", confirmed=confirmation(SESSION_A, mode="resume")))
    require(record.state == "retired" and record.retirement_reason == "consecutive_provider_output_failures", str(record))
    p3 = pool()
    first = p3.checkout(scope=scope(), assignment={"run_id": "r1"})
    p3.check_in(lease=first, settlement=settle(first, confirmed=confirmation(SESSION_A, mode="start")))
    warm = p3.checkout(scope=scope(), assignment={"run_id": "r2"})
    p3.check_in(lease=warm, settlement=settle(warm, "output_failure", confirmed=confirmation(SESSION_A, mode="resume")))
    retry = p3.checkout(scope=scope(), assignment={"run_id": "r3"}, allow_probation_retry=True)
    record = p3.check_in(lease=retry, settlement=settle(retry, confirmed=confirmation(SESSION_A, mode="resume")))
    require(record.state == "idle" and record.lifecycle.consecutive_provider_output_failures == 0, "success resets the streak")


def test_assignment_and_context_caps_rotate_explicitly() -> None:
    lifecycle = SessionLifecycleState(
        "1.0", "openai-codex", "task_supervisor", SESSION_A, "architect",
        completed_assignments=ARCHITECT_COMPLETED_CYCLE_LIMIT - 1,
        architect_completed_admission_cycles=ARCHITECT_COMPLETED_CYCLE_LIMIT - 1,
    )
    seeded = SessionRecord(
        record_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", scope=scope(), state="idle",
        created_at_utc="2026-09-04T11:00:00Z", session_id=SESSION_A,
        completed_assignment_count=ARCHITECT_COMPLETED_CYCLE_LIMIT - 1,
        idle_since_utc="2026-09-04T11:30:00Z", lifecycle=lifecycle,
    )
    p = DurableSessionPool(lifetime=LIFETIME, sessions=[seeded], clock=lambda: T0)
    warm = p.checkout(scope=scope(), assignment={"run_id": "r1"})
    require(warm.mode == "resume", "the last budgeted cycle is still offered")
    record = p.check_in(lease=warm, settlement=settle(warm, confirmed=confirmation(SESSION_A, mode="resume")))
    require(record.state == "retired" and record.retirement_reason == "architect_completed_cycle_limit", str(record))
    require(p.checkout(scope=scope(), assignment={"run_id": "r2"}).mode == "start", "cap rotates to a cold start")
    p2 = pool()
    first = p2.checkout(scope=scope(), assignment={"run_id": "r1"})
    record = p2.check_in(lease=first, settlement=settle(first, confirmed=confirmation(SESSION_A, mode="start"), percent=70))
    require(record.state == "retired" and record.retirement_reason == "known_context_window_threshold", str(record))
    p3 = pool()
    first = p3.checkout(scope=scope(), assignment={"run_id": "r1"})
    record = p3.check_in(lease=first, settlement=settle(first, confirmed=confirmation(SESSION_A, mode="start"), percent=None))
    require(record.state == "idle", "unknown context never retires")
    deep = pool()
    ws = worker_scope()
    session_ids = iter([SESSION_A])
    lease = deep.checkout(scope=ws, assignment={"run_id": "r1"})
    require(lease.session_id == lease.record_id, "claude leases carry the pool-chosen identity")
    record = deep.check_in(lease=lease, settlement=settle(lease, confirmed=ProviderSessionConfirmation("claude-code", "task_decomposer", "start", lease.record_id)))
    for n in range(2, 9):
        warm = deep.checkout(scope=ws, assignment={"run_id": f"r{n}"})
        record = deep.check_in(lease=warm, settlement=settle(warm, confirmed=ProviderSessionConfirmation("claude-code", "task_decomposer", "resume", lease.record_id)))
    require(record.state == "retired" and record.retirement_reason == "worker_weighted_unit_limit", f"8 deep assignments retire: {record}")
    del session_ids


def test_age_and_idle_bounds_expire_only_returned_conversations() -> None:
    p = pool()
    first = p.checkout(scope=scope(), assignment={"run_id": "r1"})
    p.check_in(lease=first, settlement=settle(first, confirmed=confirmation(SESSION_A, mode="start")))
    late = T0 + dt.timedelta(days=7)
    expired = p.expire(now=late)
    require(len(expired) == 1 and expired[0].state == "expired" and expired[0].expiry_reason == "idle_lifetime", str(expired))
    require(p.checkout(scope=scope(), assignment={"run_id": "r2"}, now=late).mode == "start", "expired is never resumed")
    aged = pool()
    lease = aged.checkout(scope=scope(), assignment={"run_id": "r1"})
    aged.check_in(lease=lease, settlement=settle(lease, confirmed=confirmation(SESSION_A, mode="start")))
    for day in range(1, 16):
        moment = T0 + dt.timedelta(days=day)
        warm = aged.checkout(scope=scope(), assignment={"run_id": f"r{day}"}, now=moment)
        if warm.mode == "start":
            break
        aged.check_in(lease=warm, settlement=settle(warm, confirmed=confirmation(SESSION_A, mode="resume")), now=moment)
    require(warm.mode == "start", "a busy conversation still ages out at max_session_age")
    require(any(r.expiry_reason == "max_session_age" for r in aged.sessions), [r.expiry_reason for r in aged.sessions])
    active = pool()
    lease = active.checkout(scope=scope(), assignment={"run_id": "r1"})
    active.check_in(lease=lease, settlement=settle(lease, confirmed=confirmation(SESSION_A, mode="start")))
    held = active.checkout(scope=scope(), assignment={"run_id": "r2"})
    require(active.expire(now=T0 + dt.timedelta(days=400)) == (), "an active assignment is never expired")
    require(active.session(held.record_id).state == "active", "still active")
    rejects(lambda: SessionLifetimePolicy(None, None), DurableSessionPoolError, "at least one bound")


def test_settlement_replay_is_idempotent_and_different_replay_fails() -> None:
    p = pool()
    lease = p.checkout(scope=scope(), assignment={"run_id": "r1"})
    ok = settle(lease, confirmed=confirmation(SESSION_A, mode="start"))
    first = p.check_in(lease=lease, settlement=ok)
    again = p.check_in(lease=lease, settlement=ok)
    require(first == again and first.completed_assignment_count == 1, "identical replay is a no-op")
    rejects(lambda: p.check_in(lease=lease, settlement=settle(lease, "provider_failure", confirmed=confirmation(SESSION_A, mode="start"))),
            DurableSessionPoolError, "different content")
    other = p.checkout(scope=scope(bindings=(("task_id", "NSC-915"),)), assignment={"run_id": "r9"})
    rejects(lambda: p.check_in(lease=other, settlement=ok), DurableSessionPoolError, "different lease")
    rejects(lambda: settle(lease, "waiting"), DurableSessionPoolError, "outcome")


def test_cancel_returns_uninvoked_leases_without_charging() -> None:
    p = pool()
    cold = p.checkout(scope=scope(), assignment={"run_id": "r1"})
    require(p.cancel(cold) is None and p.sessions == (), "a never-contacted cold record is discarded")
    lease = p.checkout(scope=scope(), assignment={"run_id": "r1"})
    p.check_in(lease=lease, settlement=settle(lease, confirmed=confirmation(SESSION_A, mode="start")))
    warm = p.checkout(scope=scope(), assignment={"run_id": "r2"})
    returned = p.cancel(warm)
    require(returned.state == "idle" and returned.completed_assignment_count == 1, "cancel preserves counts")
    require(returned.lifecycle.architect_completed_admission_cycles == 1, "no budget charged")


def test_store_round_trips_atomically_and_refuses_foreign_policy() -> None:
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "pool.json"
        store = DurableSessionPoolStore(path, lifetime=LIFETIME)
        p = store.load(clock=lambda: T0)
        lease = p.checkout(scope=scope(), assignment={"run_id": "r1", "host": "h"})
        p.check_in(lease=lease, settlement=settle(lease, confirmed=confirmation(SESSION_A, mode="start"), evidence={"input_tokens": "12"}))
        store.save(p)
        require(not list(Path(temp).glob(".pool.json.*")), "no temporary file remains")
        loaded = store.load(clock=lambda: T0 + dt.timedelta(minutes=1))
        require(loaded.sessions[0].session_id == SESSION_A and loaded.is_settled(lease.lease_id), "round trip")
        require(loaded.checkout(scope=scope(), assignment={"run_id": "r2"}).mode == "resume", "restored pool resumes")
        other = DurableSessionPoolStore(path, lifetime=SessionLifetimePolicy(1.0, None))
        rejects(lambda: other.load(), DurableSessionPoolError, "lifetime policy differs")
        path.write_text('{"schema_version": "1.0", "schema_version": "1.0"}', encoding="utf-8")
        rejects(lambda: store.load(), DurableSessionPoolError, "malformed")
        rejects(lambda: DurableSessionPoolStore(ROOT / "Pipeline" / "x.json", lifetime=LIFETIME),
                DurableSessionPoolError, "outside the repository")


def test_record_invariants_reject_impossible_state() -> None:
    lifecycle = SessionLifecycleState("1.0", "openai-codex", "task_supervisor", SESSION_A, "architect",
                                      completed_assignments=1, architect_completed_admission_cycles=1)
    good = SessionRecord(record_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", scope=scope(), state="idle",
                         created_at_utc="2026-09-04T11:00:00Z", session_id=SESSION_A,
                         completed_assignment_count=1, idle_since_utc="2026-09-04T11:30:00Z", lifecycle=lifecycle)
    require(SessionRecord.from_dict(good.to_dict()) == good, "record round trip")
    rejects(lambda: SessionRecord(record_id=good.record_id, scope=scope(), state="idle", created_at_utc=good.created_at_utc,
                                  session_id=None, completed_assignment_count=1, idle_since_utc=good.idle_since_utc, lifecycle=None),
            DurableSessionPoolError, "confirmed session identity")
    rejects(lambda: SessionRecord(record_id=good.record_id, scope=scope(), state="retired", created_at_utc=good.created_at_utc,
                                  session_id=SESSION_A, completed_assignment_count=1, lifecycle=lifecycle),
            DurableSessionPoolError, "retirement decision")
    rejects(lambda: SessionRecord(record_id=good.record_id, scope=scope(), state="idle", created_at_utc=good.created_at_utc,
                                  session_id=SESSION_B, completed_assignment_count=1, idle_since_utc=good.idle_since_utc, lifecycle=lifecycle),
            DurableSessionPoolError, "different conversation")
    rejects(lambda: SessionRecord(record_id=good.record_id, scope=scope(), state="quarantined", created_at_utc=good.created_at_utc),
            DurableSessionPoolError, "quarantine_reason")
    rejects(lambda: DurableSessionPool(lifetime=LIFETIME, sessions=[good, good]), DurableSessionPoolError, "duplicate")


def test_authority_capsule_revokes_and_restates() -> None:
    resumed = authority_capsule(
        role="task_supervisor", mode="resume", prior_completed_assignment_count=3,
        current={"task": "NSC-914", "phase": "delivery_evidence", "source_head": "abc"},
        allowed_actions=("run_authoritative_unity_test",), capabilities=(), obligations=("one decision",),
    )
    for fragment in ("closed", "revoked", "context only", "Current task: NSC-914", "Current phase: delivery_evidence",
                     "Current source head: abc", "- run_authoritative_unity_test", "Current capabilities: (none)", "3 completed"):
        require(fragment in resumed, f"capsule lacks {fragment!r}")
    started = authority_capsule(role="task_supervisor", mode="start", prior_completed_assignment_count=0,
                                current={"task": "NSC-914"}, allowed_actions=("a",), capabilities=())
    require("no prior assignment" in started and "revoked" not in started, started)
    rejects(lambda: authority_capsule(role="x", mode="other", prior_completed_assignment_count=0, current={}, allowed_actions=(), capabilities=()),
            DurableSessionPoolError, "mode")


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"durable session pool tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
