#!/usr/bin/env python3
"""Deterministic regressions for the in-flight transition settle wait.

Classification: pure/component tests. Injected snapshots, an injected scheduler,
in-memory progress, and an injected pump callable; no Git, GitHub, provider,
worker, Unity, Docker, or canonical checkout is read or mutated.

The defect these pin: after a worker hands a task to `human_action_required`,
the managed Issue can still be inside its bounded state-Action window -- the
agent-ready label is applied and GitHub has not finished writing the body yet.
That window is deliberately not admissible and deliberately not pump-eligible,
so the step had nothing left to do and fell through to the one generic
`fallback_seconds` wait. Nothing wakes that wait: no worker returns, and the
transition converges remotely without a local notification, so the run idled
until the fallback elapsed or an unrelated poke arrived. The single all-Claude
NSC-920 run showed roughly 93 s between the poll that ended idle and the next
poll that observed `agent_ready / delivery_evidence`.

The fix gives that one evidenced state a short bounded settle budget with
doubling backoff. Tests marked GUARD are preservation checks that pass both
before and after the fix; they exist so the change cannot buy latency by
weakening a safety property or by shortening the generic fallback.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.autonomous_graph_run import (  # noqa: E402
    AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
    DEFAULT_FALLBACK_SECONDS,
    DEFAULT_TRANSITION_SETTLE_SECONDS,
    AutonomousGraphController,
    AutonomousGraphRunError,
    AutonomousRunManifest,
    AutonomousRuntimeConfiguration,
    CoherentGraphSnapshot,
    ManagedIssueObservation,
    MemoryProgressStore,
    MemoryReceiptStore,
    SyntheticEvidencePumpResult,
    TaskObservation,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowPhase,
    WorkflowState,
)
from Pipeline.TaskReviewAgent.prepare_synthetic_gauntlet import (  # noqa: E402
    PRESERVED_TASK_ID,
)

HEAD = "1" * 40
TREE = "2" * 40
TASK = "NSC-920"
OUT_OF_SCOPE = "NSC-904"
EVENT_ID = "c" * 64
EVIDENCE = "d" * 64
BASE_EVENT = "a" * 64

FAILURES: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------- fixtures


def manifest(*, targets: tuple[str, ...] = (TASK,)) -> AutonomousRunManifest:
    return AutonomousRunManifest(
        schema_version=AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
        run_id="nsc-920-settle-fixture",
        source_repository=str(ROOT),
        github_repository="fixture-owner/pipeline-rehearsal",
        runtime_configuration=AutonomousRuntimeConfiguration(
            execution_provider="claude",
            execution_model=None,
            execution_max_turns=120,
            architect_provider="claude",
            architect_model=None,
            architect_max_turns=24,
            architect_min_confidence=0.7,
            architect_max_invocations_per_poll=3,
            architect_min_reanalysis_seconds=300.0,
            max_consecutive_observation_failures=3,
            fatal_drain_seconds=1800.0,
            fallback_seconds=300.0,
            synthetic_evidence_enabled=True,
        ),
        initial_source_commit=HEAD,
        initial_source_tree=TREE,
        target_task_ids=targets,
        excluded_task_ids=(),
        max_capacity=1,
    )


def managed_issue(
    task_id: str,
    state: str,
    phase: str,
    *,
    event_id: str = BASE_EVENT,
    evidence_sha256: str | None = None,
    state_version: int = 1,
) -> ManagedIssueObservation:
    working = state == "agent_working"
    human = state == "human_action_required"
    return ManagedIssueObservation(
        task_id=task_id,
        state=WorkflowState(state),
        phase=WorkflowPhase(phase),
        state_version=state_version,
        last_event_id=event_id,
        head_commit=HEAD if human else None,
        human_handoff_commit=HEAD if human else None,
        worker_id="fixture-worker" if working else None,
        lease_id="b" * 64 if working else None,
        decomposition_run_id=None,
        graph_delta_plan_id=None,
        last_event_evidence_sha256=evidence_sha256,
    )


def snapshot(
    *,
    revision: int = 1,
    tasks: tuple[TaskObservation, ...] | None = None,
    issues: tuple[ManagedIssueObservation, ...] | None = None,
    active: tuple[str, ...] = (),
    transitions: tuple[str, ...] = (),
    reservations: tuple[str, ...] = (),
) -> CoherentGraphSnapshot:
    return CoherentGraphSnapshot(
        observation_revision=revision,
        source_branch="main",
        source_attached=True,
        source_clean=True,
        source_head=HEAD,
        source_tree=TREE,
        origin_main_head=HEAD,
        initial_source_commit_is_ancestor=True,
        initial_source_tree=TREE,
        tasks=tasks if tasks is not None else (TaskObservation(TASK, "not_delivered"),),
        managed_issues=issues
        if issues is not None
        else (managed_issue(TASK, "agent_working", "implementation"),),
        active_assignment_task_ids=active,
        pending_transition_task_ids=transitions,
        reservation_task_ids=reservations,
        authorized_local_ahead_recovery_task_id=None,
        authorized_local_ahead_recovery_commit=None,
    )


def working_snapshot(**overrides: Any) -> CoherentGraphSnapshot:
    """The pre-poll observation: the implementation worker still owns the task."""
    return snapshot(
        revision=1,
        issues=(managed_issue(TASK, "agent_working", "implementation"),),
        active=(TASK,),
        **overrides,
    )


def waiting_snapshot(
    *, revision: int = 2, transitions: tuple[str, ...] = (TASK,), **overrides: Any
) -> CoherentGraphSnapshot:
    """The handoff observation: waiting, with its agent-ready Action in flight.

    `pending_transition_task_ids` is the exact durable shape the scheduler
    already recognizes as "the label is one legal state ahead of its body while
    the state Action runs". It is not admissible and not pump-eligible, and the
    Action that converges it sends no local wake.
    """
    return snapshot(
        revision=revision,
        issues=(
            managed_issue(
                TASK,
                "human_action_required",
                "unity_runtime_validation",
                state_version=2,
            ),
        ),
        transitions=transitions,
        **overrides,
    )


def settled_snapshot(*, revision: int = 3, **overrides: Any) -> CoherentGraphSnapshot:
    """The observation after the state Action converged: eligible delivery work."""
    return snapshot(
        revision=revision,
        issues=(
            managed_issue(
                TASK,
                "agent_ready",
                "delivery_evidence",
                event_id=EVENT_ID,
                evidence_sha256=EVIDENCE,
                state_version=3,
            ),
        ),
        **overrides,
    )


class ReapingScheduler:
    """A scheduler whose poll reaps the live worker, exactly like the live run."""

    def __init__(
        self,
        *,
        active: tuple[str, ...] = (TASK,),
        wait_reasons: tuple[str, ...] = ("fallback_elapsed",),
        launches: int = 0,
        status: str = "worker_returned",
    ) -> None:
        self.source = ROOT
        self.max_workers = 1
        self.excluded_task_ids: frozenset[str] = frozenset()
        self.active_assignments: dict[str, object] = {
            task_id: object() for task_id in active
        }
        self.architect_invocations_this_poll = 0
        self.worker_launches_this_poll = 0
        self._launches = launches
        self._status = status
        self.wait_reasons = list(wait_reasons)
        self.poll_calls = 0
        self.wait_calls: list[float] = []
        self.lifecycle_events: list[str] = []
        self.listener_active = False

    def set_admission_allowlist(self, task_ids: Any) -> None:
        return None

    def reconcile_interrupted_architect_session(self, *, lock: Any) -> bool:
        require(lock.held, "architect recovery ran without scheduler ownership")
        return False

    def drain_active_workers(self, *, poll_seconds: float, stop_reason: str) -> bool:
        self.active_assignments.clear()
        return True

    def start_activity_listener(self) -> bool:
        self.listener_active = True
        self.lifecycle_events.append("start")
        return True

    def close_activity_listener(self) -> None:
        self.listener_active = False
        self.lifecycle_events.append("close")

    def poll_capacity_batch(self) -> SimpleNamespace:
        self.lifecycle_events.append("poll")
        self.poll_calls += 1
        self.active_assignments.clear()
        self.architect_invocations_this_poll = 0
        self.worker_launches_this_poll = self._launches
        return SimpleNamespace(status=self._status, fatal=False)

    def _wait_for_architect_activity(self, poll_seconds: float) -> str:
        self.lifecycle_events.append("wait")
        self.wait_calls.append(poll_seconds)
        return (
            self.wait_reasons.pop(0)
            if len(self.wait_reasons) > 1
            else self.wait_reasons[0]
        )


class SnapshotSequence:
    def __init__(self, *values: CoherentGraphSnapshot) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self) -> CoherentGraphSnapshot:
        self.calls += 1
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]


class FakeLock:
    def __init__(self) -> None:
        self.held = False

    def acquire(self) -> None:
        self.held = True

    def release(self) -> None:
        self.held = False


class DecliningPump:
    """The exact live shape: a pending transition is never pump-eligible."""

    def __init__(self) -> None:
        self.observed_states: list[str] = []

    def __call__(
        self, observed: CoherentGraphSnapshot
    ) -> SyntheticEvidencePumpResult | None:
        self.observed_states.append(observed.managed_issues[0].state.value)
        return None


def controller(
    *,
    state: SnapshotSequence,
    scheduler: ReapingScheduler,
    pump: Any = None,
    run_manifest: AutonomousRunManifest | None = None,
    **overrides: Any,
) -> AutonomousGraphController:
    return AutonomousGraphController(
        manifest=run_manifest or manifest(),
        scheduler=scheduler,
        scheduler_lock=FakeLock(),
        snapshotter=state,
        progress_store=MemoryProgressStore(),
        receipt_store=MemoryReceiptStore(),
        synthetic_evidence_pump=pump,
        synthetic_excluded_task_ids=(PRESERVED_TASK_ID,),
        fallback_seconds=DEFAULT_FALLBACK_SECONDS,
        **overrides,
    )


# ------------- 1: the proven defect -- no long wait between handoff and work


def test_an_in_flight_handoff_transition_is_re_observed_promptly() -> None:
    """The exact live sequence: worker returns waiting, Action in flight, resume.

    Before the fix this step slept the full 300 s generic fallback while GitHub
    finished a transition that sends no wake, so the delivery-evidence work that
    was already authorized could not start until the fallback elapsed.
    """
    pump = DecliningPump()
    scheduler = ReapingScheduler(status="idle")
    state = SnapshotSequence(
        working_snapshot(),               # step 1 pre-poll: the worker owns it
        waiting_snapshot(revision=2),     # step 1 post-poll: the poll reaped it
        waiting_snapshot(revision=3),     # step 2: unchanged, Action still in flight
        waiting_snapshot(revision=4),     # step 2 post-poll: still in flight -> wait
        settled_snapshot(revision=5),     # step 3: the Action converged
    )
    result = controller(state=state, scheduler=scheduler, pump=pump).run(max_steps=3)

    require(
        scheduler.wait_calls == [DEFAULT_TRANSITION_SETTLE_SECONDS],
        f"the in-flight transition did not use the settle budget: {scheduler.wait_calls}",
    )
    require(
        sum(scheduler.wait_calls) < DEFAULT_FALLBACK_SECONDS,
        f"the step still slept a generic fallback: {scheduler.wait_calls}",
    )
    require(
        scheduler.poll_calls == 3,
        f"the controller did not re-observe and poll promptly: {scheduler.poll_calls}",
    )
    require(
        result.evaluation.classification == "actionable",
        f"the settled delivery-evidence handoff was not eligible: {result.evaluation}",
    )
    require(
        pump.observed_states[-1] == "agent_ready",
        f"the run did not reach the settled state: {pump.observed_states}",
    )


def test_the_settle_wait_is_reported_on_the_step_result() -> None:
    """The step must state which budget authorized its wait, not just its reason."""
    scheduler = ReapingScheduler(active=())
    waiting = waiting_snapshot(revision=1)
    result = controller(
        state=SnapshotSequence(waiting, waiting, waiting), scheduler=scheduler
    ).run(max_steps=1)
    require(
        result.wait_scope == "transition_settle",
        f"the wait budget was not reported: {result.wait_scope}",
    )
    require(
        result.wait_seconds == DEFAULT_TRANSITION_SETTLE_SECONDS,
        f"the reported wait length is wrong: {result.wait_seconds}",
    )
    require(
        result.wait_reason == "fallback_elapsed",
        f"the scheduler wait reason was lost: {result.wait_reason}",
    )


# ------------------------------- 2: bounded backoff, never a busy loop


def test_repeated_settle_waits_back_off_toward_the_fallback() -> None:
    """An unchanged in-flight observation must double, not spin."""
    scheduler = ReapingScheduler(active=())
    waiting = waiting_snapshot(revision=1)
    controller(
        state=SnapshotSequence(waiting, waiting, waiting), scheduler=scheduler
    ).run(max_steps=4)
    require(
        scheduler.wait_calls == [5.0, 10.0, 20.0, 40.0],
        f"consecutive settle waits did not back off: {scheduler.wait_calls}",
    )
    require(
        all(item <= DEFAULT_FALLBACK_SECONDS for item in scheduler.wait_calls),
        f"a settle wait exceeded the generic fallback: {scheduler.wait_calls}",
    )


def test_settle_backoff_never_exceeds_the_generic_fallback() -> None:
    """The worst case is exactly today's behavior, never worse."""
    scheduler = ReapingScheduler(active=())
    waiting = waiting_snapshot(revision=1)
    controller(
        state=SnapshotSequence(waiting, waiting, waiting),
        scheduler=scheduler,
        transition_settle_seconds=200.0,
    ).run(max_steps=3)
    require(
        scheduler.wait_calls == [200.0, 300.0, 300.0],
        f"the backoff did not cap at the generic fallback: {scheduler.wait_calls}",
    )


def test_a_wake_resets_the_settle_backoff() -> None:
    """A real wake means the next in-flight window starts short again."""
    scheduler = ReapingScheduler(
        active=(),
        wait_reasons=("fallback_elapsed", "issue_state_changed", "fallback_elapsed"),
    )
    waiting = waiting_snapshot(revision=1)
    result = controller(
        state=SnapshotSequence(waiting, waiting, waiting), scheduler=scheduler
    ).run(max_steps=3)
    require(
        scheduler.wait_calls == [5.0, 10.0, 5.0],
        f"the backoff did not reset after a wake: {scheduler.wait_calls}",
    )
    require(
        result.progress.wakeups_total == 1,
        f"the wake was not counted: {result.progress.wakeups_total}",
    )


# ---------------------------------- 3: GUARDs -- nothing else got faster


def test_guard_a_plain_human_wait_keeps_the_generic_fallback() -> None:
    """A waiting human with no in-flight transition is still a long wait."""
    scheduler = ReapingScheduler(active=())
    waiting = waiting_snapshot(revision=1, transitions=())
    result = controller(
        state=SnapshotSequence(waiting, waiting, waiting), scheduler=scheduler
    ).run(max_steps=1)
    require(
        scheduler.wait_calls == [DEFAULT_FALLBACK_SECONDS],
        f"an ordinary human wait was shortened: {scheduler.wait_calls}",
    )
    require(
        result.wait_reason == "fallback_elapsed",
        f"an ordinary human wait lost its wait reason: {result.wait_reason}",
    )


def test_guard_an_out_of_scope_transition_does_not_shorten_the_wait() -> None:
    """Only a transition inside the exact run scope earns the settle budget."""
    scheduler = ReapingScheduler(active=())
    waiting = waiting_snapshot(revision=1, transitions=(OUT_OF_SCOPE,))
    controller(
        state=SnapshotSequence(waiting, waiting, waiting), scheduler=scheduler
    ).run(max_steps=1)
    require(
        scheduler.wait_calls == [DEFAULT_FALLBACK_SECONDS],
        f"an out-of-scope transition shortened the wait: {scheduler.wait_calls}",
    )


def test_guard_a_declined_pump_still_falls_back_normally() -> None:
    """A pump decline stays authoritative; it is not a fast retry trigger."""
    pump = DecliningPump()
    scheduler = ReapingScheduler(active=())
    waiting = snapshot(
        revision=1,
        issues=(
            managed_issue(
                TASK,
                "human_action_required",
                "unity_runtime_validation",
                state_version=2,
            ),
        ),
    )
    controller(
        state=SnapshotSequence(waiting, waiting, waiting),
        scheduler=scheduler,
        pump=pump,
    ).run(max_steps=1)
    require(
        scheduler.wait_calls == [DEFAULT_FALLBACK_SECONDS],
        f"a declined pump became a fast retry: {scheduler.wait_calls}",
    )


def test_guard_an_in_flight_transition_is_still_never_admitted_or_pumped() -> None:
    """The settle budget must not make a mid-transition Issue selectable."""
    from Pipeline.TaskReviewAgent.autonomous_graph_run import (
        eligible_synthetic_handoff_task_ids,
        evaluate_graph_state,
    )

    observed = waiting_snapshot(revision=1)
    evaluation = evaluate_graph_state(manifest(), observed)
    require(
        eligible_synthetic_handoff_task_ids(
            observed,
            relevant_task_ids=evaluation.relevant_task_ids,
            excluded_task_ids=(PRESERVED_TASK_ID,),
        )
        == (),
        "a task inside its state-Action window became pump-eligible",
    )
    require(
        evaluation.classification == "temporary_wait",
        f"an in-flight transition changed classification: {evaluation}",
    )
    require(
        not evaluation.internally_stalled,
        "an in-flight transition was treated as internally stalled",
    )


def test_guard_the_settle_wait_still_counts_as_a_lifetime_wait() -> None:
    """Latency work must not quietly stop accounting for elapsed waits."""
    scheduler = ReapingScheduler(active=())
    waiting = waiting_snapshot(revision=1)
    result = controller(
        state=SnapshotSequence(waiting, waiting, waiting), scheduler=scheduler
    ).run(max_steps=2)
    require(
        result.progress.fallback_waits_total == 2,
        f"elapsed settle waits were not counted: {result.progress.fallback_waits_total}",
    )
    require(
        result.progress.last_fallback_fingerprint is None,
        "an externally waiting state was armed for deadlock detection",
    )


def test_guard_the_settle_budget_is_validated() -> None:
    scheduler = ReapingScheduler(active=())
    waiting = waiting_snapshot(revision=1)
    for invalid in (0.0, -1.0, float("inf"), 300.1, "5", True, None):
        try:
            controller(
                state=SnapshotSequence(waiting, waiting, waiting),
                scheduler=scheduler,
                transition_settle_seconds=invalid,
            )
        except AutonomousGraphRunError:
            continue
        raise AssertionError(f"an invalid settle budget was accepted: {invalid!r}")


def test_guard_the_settle_budget_cannot_exceed_the_configured_fallback() -> None:
    scheduler = ReapingScheduler(active=())
    waiting = waiting_snapshot(revision=1)
    try:
        AutonomousGraphController(
            manifest=manifest(),
            scheduler=scheduler,
            scheduler_lock=FakeLock(),
            snapshotter=SnapshotSequence(waiting, waiting, waiting),
            progress_store=MemoryProgressStore(),
            receipt_store=MemoryReceiptStore(),
            fallback_seconds=30.0,
            transition_settle_seconds=60.0,
        )
    except AutonomousGraphRunError:
        return
    raise AssertionError("a settle budget longer than the fallback was accepted")


# --------------------------------------------------------------------- main


def main() -> int:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_")
        and callable(value)
        and getattr(value, "__module__", None) == __name__
    ]
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - the runner reports every failure
            FAILURES.append(f"{test.__name__}: {exc}")
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    if FAILURES:
        print(f"transition_settle_wait_smoke_test: FAIL ({len(FAILURES)})")
        return 1
    print(f"transition_settle_wait_smoke_test: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    raise SystemExit(run_with_synthetic_authority(main))
