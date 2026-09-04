#!/usr/bin/env python3
"""Pure component tests for deterministic provider-session retirement.

Classification: pure/component tests. These checks are regression-only policy
coverage for AgentRuntime; they make no provider, network, command, Unity, or
repository mutation calls.
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.session_lifecycle import (  # noqa: E402
    ARCHITECT_COMPLETED_CYCLE_LIMIT,
    CONTEXT_WINDOW_RETIRE_PERCENT,
    SESSION_LIFECYCLE_SCHEMA_VERSION,
    WORKER_WEIGHTED_UNIT_LIMIT,
    LatencySample,
    SessionLifecycleError,
    SessionLifecycleState,
    SessionLifecycleTelemetry,
    SessionLifecycleTransition,
    finish_assignment,
    observe_between_assignments,
    start_assignment,
)


SESSION_A = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
SESSION_B = "9c858901-8a57-4791-81fe-4c455b099bc9"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action: Any, expected: type[BaseException] = SessionLifecycleError) -> BaseException:
    try:
        action()
    except expected as exc:
        return exc
    raise AssertionError(f"expected {expected.__name__}")


def session(
    session_class: str = "worker",
    *,
    provider: str = "provider-alpha",
    role: str = "implementer",
    session_id: str = SESSION_A,
) -> SessionLifecycleState:
    return SessionLifecycleState.create(
        provider_identifier=provider,
        role=role,
        session_id=session_id,
        session_class=session_class,
    )


def complete(
    state: SessionLifecycleState,
    number: int,
    *,
    workload: str = "fast",
    outcome: str = "completed",
    context: int | None = None,
    latency: LatencySample | None = None,
) -> SessionLifecycleTransition:
    assignment_id = f"assignment-{number}"
    started = start_assignment(
        state,
        assignment_id=assignment_id,
        workload_class=workload,
    )
    require(started.state.phase == "assigned", "assignment did not start")
    return finish_assignment(
        started.state,
        assignment_id=assignment_id,
        outcome=outcome,
        known_context_window_percent=context,
        latency_sample=latency,
    )


def test_worker_weighted_limits_are_exact() -> None:
    for workload, count in (("fast", 48), ("standard", 16), ("deep", 8)):
        state = session(role=f"{workload}_worker")
        for number in range(1, count + 1):
            result = complete(state, number, workload=workload)
            state = result.state
            if number < count:
                require(state.phase == "between_assignments", f"{workload} retired early")
            else:
                require(state.phase == "retired", f"{workload} did not retire at cap")
                require(
                    state.retirement_reason == "worker_weighted_unit_limit",
                    f"{workload}: wrong retirement reason",
                )
        require(
            state.worker_weighted_units == WORKER_WEIGHTED_UNIT_LIMIT,
            f"{workload}: wrong weighted total",
        )
        require(state.completed_assignments == count, f"{workload}: wrong run count")


def test_mixed_worker_assignment_that_would_exceed_limit_is_never_started() -> None:
    state = session()
    for number in range(1, 8):
        state = complete(state, number, workload="deep").state
    state = complete(state, 8, workload="standard").state
    require(state.worker_weighted_units == 45, "fixture did not reach 45 units")
    refused = start_assignment(
        state,
        assignment_id="assignment-9",
        workload_class="deep",
    )
    require(refused.state.phase == "retired", "overflowing work was not refused")
    require(refused.telemetry.event == "assignment_refused", "refusal was not explicit")
    require(refused.telemetry.budget_delta == 0, "refusal consumed budget")
    require(refused.state.worker_weighted_units == 45, "refusal changed accounting")
    require(
        refused.state.retirement_reason == "worker_weighted_unit_limit_would_be_exceeded",
        "wrong overflow retirement reason",
    )


def test_architect_retires_after_one_hundred_completed_admission_cycles() -> None:
    state = session("architect", provider="provider-beta", role="portfolio_architect")
    for number in range(1, ARCHITECT_COMPLETED_CYCLE_LIMIT + 1):
        result = complete(state, number, workload="admission_cycle")
        state = result.state
    require(state.phase == "retired", "architect remained available after cycle cap")
    require(
        state.architect_completed_admission_cycles == 100,
        "architect cycle accounting is wrong",
    )
    require(
        state.retirement_reason == "architect_completed_cycle_limit",
        "architect cap reason is wrong",
    )


def test_waiting_and_idle_consume_no_budget() -> None:
    for session_class, workload in (("worker", "fast"), ("architect", "admission_cycle")):
        state = session(session_class, role=f"{session_class}_role")
        before = state.to_dict()
        for number in range(20):
            observation = "waiting" if number % 2 else "idle"
            transition = observe_between_assignments(state, observation=observation)
            require(transition.telemetry.budget_delta == 0, "idle/wait consumed budget")
            state = transition.state
        require(state.phase == "between_assignments", "idle/wait retired the session")
        require(state.completed_assignments == 0, "idle/wait counted an assignment")
        require(state.worker_weighted_units == before["worker_weighted_units"], "worker budget changed")
        require(
            state.architect_completed_admission_cycles
            == before["architect_completed_admission_cycles"],
            "architect budget changed",
        )
        # A caller can also report that a started attempt ended waiting or idle;
        # those explicit outcomes remain zero-cost.
        for number, outcome in enumerate(("waiting", "idle"), 1):
            transition = complete(
                state,
                number,
                workload=workload,
                outcome=outcome,
            )
            require(transition.telemetry.budget_delta == 0, "wait outcome consumed budget")
            state = transition.state
        require(state.worker_weighted_units == 0, "worker wait outcome changed budget")
        require(
            state.architect_completed_admission_cycles == 0,
            "architect wait outcome changed budget",
        )


def test_retirement_never_interrupts_an_assignment() -> None:
    active = start_assignment(
        session(), assignment_id="assignment-active", workload_class="deep"
    ).state
    rejects(
        lambda: observe_between_assignments(
            active,
            observation="identity_failure",
            known_context_window_percent=100,
        )
    )
    require(active.phase == "assigned", "failed observation mutated immutable state")
    finished = finish_assignment(
        active,
        assignment_id="assignment-active",
        outcome="identity_failure",
        known_context_window_percent=100,
    )
    require(finished.state.phase == "retired", "boundary retirement did not occur")
    require(finished.telemetry.phase_before == "assigned", "wrong telemetry boundary")
    require(finished.telemetry.phase_after == "retired", "wrong telemetry result")


def test_explicit_identity_and_compatibility_failures_retire_immediately() -> None:
    for observation in ("session_incompatibility", "identity_failure"):
        result = observe_between_assignments(session(), observation=observation)
        require(result.state.phase == "retired", f"{observation} did not retire")
        require(result.state.retirement_reason == observation, f"{observation}: wrong reason")
        require(result.telemetry.budget_delta == 0, f"{observation}: budget changed")
    for number, outcome in enumerate(("session_incompatibility", "identity_failure"), 1):
        result = complete(session(), number, outcome=outcome)
        require(result.state.phase == "retired", f"active {outcome} did not retire at boundary")
        require(result.state.retirement_reason == outcome, f"active {outcome}: wrong reason")


def test_two_consecutive_provider_or_output_failures_retire() -> None:
    state = session()
    first = complete(state, 1, outcome="provider_failure")
    require(first.state.phase == "between_assignments", "one failure retired early")
    require(first.state.consecutive_provider_output_failures == 1, "failure not counted")
    reset = complete(first.state, 2, outcome="completed")
    require(reset.state.consecutive_provider_output_failures == 0, "success did not reset streak")
    one = complete(reset.state, 3, outcome="output_failure")
    two = complete(one.state, 4, outcome="provider_failure")
    require(two.state.phase == "retired", "two consecutive failures did not retire")
    require(
        two.state.retirement_reason == "consecutive_provider_output_failures",
        "failure streak reason is wrong",
    )
    require(two.state.worker_weighted_units == 4, "active worker attempts were not charged")

    architect = session("architect", role="admission_architect")
    failed = complete(
        architect, 1, workload="admission_cycle", outcome="provider_failure"
    )
    require(
        failed.state.architect_completed_admission_cycles == 0,
        "failed architect invocation counted as a completed admission cycle",
    )


def test_context_threshold_requires_explicit_known_percentage() -> None:
    unknown = complete(session(), 1)
    require(unknown.state.phase == "between_assignments", "unknown context retired")
    require(not unknown.telemetry.context_window_known, "unknown context was claimed known")
    require(
        unknown.telemetry.known_context_window_percent is None,
        "unknown context invented a percentage",
    )
    below = complete(session(), 1, context=CONTEXT_WINDOW_RETIRE_PERCENT - 1)
    require(below.state.phase == "between_assignments", "sub-threshold context retired")
    resumed = start_assignment(
        below.state,
        assignment_id="known-context-resume",
        workload_class="fast",
    )
    require(
        resumed.telemetry.known_context_window_percent
        == CONTEXT_WINDOW_RETIRE_PERCENT - 1,
        "assignment-start telemetry lost the last explicit known context",
    )
    exact = complete(session(), 1, context=CONTEXT_WINDOW_RETIRE_PERCENT)
    require(exact.state.phase == "retired", "70 percent did not retire")
    require(
        exact.state.retirement_reason == "known_context_window_threshold",
        "context reason is wrong",
    )
    rejects(lambda: complete(session(), 1, context=101))
    rejects(lambda: complete(session(), 1, context=True))


def test_latency_requires_three_consecutive_comparable_degraded_samples() -> None:
    key = "fast-read"
    baseline = 100
    state = session()
    state = complete(
        state, 1, latency=LatencySample(key, 200, baseline)
    ).state
    state = complete(
        state, 2, latency=LatencySample(key, 199, baseline)
    ).state
    require(state.latency_degraded_sample_count == 0, "healthy sample did not reset streak")
    state = complete(
        state, 3, latency=LatencySample(key, 250, baseline)
    ).state
    state = complete(
        state, 4, latency=LatencySample("deep-read", 500, 200)
    ).state
    require(state.latency_degraded_sample_count == 1, "new comparison did not reset streak")
    state = complete(
        state, 5, latency=LatencySample(key, 200, baseline)
    ).state
    state = complete(state, 6).state
    require(state.latency_degraded_sample_count == 0, "missing comparison did not break streak")
    for number, duration in ((7, 200), (8, 201), (9, 300)):
        result = complete(
            state,
            number,
            latency=LatencySample(key, duration, baseline),
        )
        state = result.state
    require(state.phase == "retired", "three degraded samples did not retire")
    require(
        state.retirement_reason == "sustained_comparable_latency",
        "latency reason is wrong",
    )


def test_serialization_is_strict_and_round_trips_deterministically() -> None:
    started = start_assignment(
        session(provider="openai-codex", role="validator", session_id=SESSION_B),
        assignment_id="round-trip-1",
        workload_class="standard",
    )
    finished = finish_assignment(
        started.state,
        assignment_id="round-trip-1",
        outcome="provider_failure",
        known_context_window_percent=42,
        latency_sample=LatencySample("standard-validation", 500, 400),
    )
    encoded = json.dumps(
        finished.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    decoded = SessionLifecycleTransition.from_dict(json.loads(encoded))
    require(decoded == finished, "transition round trip changed values")
    require(
        json.dumps(decoded.to_dict(), sort_keys=True, separators=(",", ":")) == encoded,
        "transition serialization is not deterministic",
    )

    class DictSubclass(dict):
        pass

    rejects(lambda: SessionLifecycleState.from_dict(DictSubclass(finished.state.to_dict())))
    extra = finished.state.to_dict()
    extra["unexpected"] = 1
    rejects(lambda: SessionLifecycleState.from_dict(extra))
    missing = finished.telemetry.to_dict()
    del missing["budget_delta"]
    rejects(lambda: SessionLifecycleTelemetry.from_dict(missing))
    malformed = finished.state.to_dict()
    malformed["worker_weighted_units"] = True
    rejects(lambda: SessionLifecycleState.from_dict(malformed))
    rejects(
        lambda: SessionLifecycleState.create(
            provider_identifier="provider-alpha",
            role="implementer",
            session_id="last",
            session_class="worker",
        )
    )
    inconsistent = finished.to_dict()
    inconsistent["telemetry"]["budget_used"] += 1
    rejects(lambda: SessionLifecycleTransition.from_dict(inconsistent))


def test_role_and_provider_names_are_data_not_policy() -> None:
    pairs = (
        ("claude-code", "implementation_worker", "worker", SESSION_A),
        ("openai-codex", "portfolio_architect", "architect", SESSION_B),
        ("future-provider", "custom_review_role", "worker", SESSION_A),
    )
    for provider, role, session_class, identity in pairs:
        state = session(
            session_class,
            provider=provider,
            role=role,
            session_id=identity,
        )
        require(state.provider_identifier == provider, "provider identity changed")
        require(state.role == role, "role identity changed")


def test_invalid_or_contradictory_state_fails_closed() -> None:
    base = session()
    rejects(lambda: start_assignment(base, assignment_id="UPPER", workload_class="fast"))
    rejects(lambda: start_assignment(base, assignment_id="ok", workload_class="admission_cycle"))
    rejects(
        lambda: start_assignment(
            session("architect"), assignment_id="ok", workload_class="deep"
        )
    )
    active = start_assignment(base, assignment_id="exact-id", workload_class="fast").state
    rejects(
        lambda: finish_assignment(
            active, assignment_id="different-id", outcome="completed"
        )
    )
    rejects(lambda: finish_assignment(base, assignment_id="exact-id", outcome="completed"))
    rejects(lambda: replace(active, phase="retired", retirement_reason="identity_failure"))
    rejects(
        lambda: replace(
            base,
            latency_comparison_key="fast-read",
            latency_baseline_milliseconds=100,
            latency_degraded_sample_count=0,
        )
    )
    rejects(lambda: LatencySample("fast-read", True, 100))


TESTS = (
    test_worker_weighted_limits_are_exact,
    test_mixed_worker_assignment_that_would_exceed_limit_is_never_started,
    test_architect_retires_after_one_hundred_completed_admission_cycles,
    test_waiting_and_idle_consume_no_budget,
    test_retirement_never_interrupts_an_assignment,
    test_explicit_identity_and_compatibility_failures_retire_immediately,
    test_two_consecutive_provider_or_output_failures_retire,
    test_context_threshold_requires_explicit_known_percentage,
    test_latency_requires_three_consecutive_comparable_degraded_samples,
    test_serialization_is_strict_and_round_trips_deterministically,
    test_role_and_provider_names_are_data_not_policy,
    test_invalid_or_contradictory_state_fails_closed,
)


def main(argv: list[str] | None = None) -> int:
    selected = set(argv or [])
    for test in TESTS:
        if selected and test.__name__ not in selected:
            continue
        test()
        print(f"PASS {test.__name__}")
    print("session_lifecycle_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
