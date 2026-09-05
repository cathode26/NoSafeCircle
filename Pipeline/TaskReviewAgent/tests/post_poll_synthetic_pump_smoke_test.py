#!/usr/bin/env python3
"""Deterministic regressions for the post-poll synthetic evidence pump.

Classification: pure/component tests. Injected snapshots, an injected scheduler,
in-memory progress, and an injected pump callable; no Git, GitHub, provider,
worker, Unity, Docker, or canonical checkout is read or mutated.

The defect these pin: a scheduler poll can itself expose a newly eligible
`human_action_required` handoff by reaping the worker that owned the task. The
pre-poll pump attempt legitimately saw a live worker and declined. Before this
change the controller then treated that internally observed progress as a reason
to hand control to its event/fallback wait -- waiting for an external event that
nobody was going to send, because the next action was the controller's own
synthetic transition. The observed cost in `nsc-914-fast-probe-20260904a` was one
full ~300 s fallback cycle between reaping the worker and running the exact Unity
test.

Tests marked GUARD are preservation checks that pass both before and after the
fix; they exist so the change cannot buy latency by weakening a safety property.
"""

from __future__ import annotations

from dataclasses import replace
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
    eligible_synthetic_handoff_task_ids,
    evaluate_graph_state,
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
TASK = "NSC-901"
OTHER = "NSC-903"
OUT_OF_SCOPE = "NSC-904"
EVENT_ID = "c" * 64
EVIDENCE = "d" * 64
BASE_EVENT = "a" * 64

FAILURES: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------- fixtures


def manifest(
    *, targets: tuple[str, ...] = (TASK,), excluded: tuple[str, ...] = ()
) -> AutonomousRunManifest:
    return AutonomousRunManifest(
        schema_version=AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
        run_id="nsc-914-fast-probe-fixture",
        source_repository=str(ROOT),
        github_repository="cathode26/NoSafeCircle-Homework-Rehearsal",
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
        excluded_task_ids=excluded,
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


AHEAD = "3" * 40


def snapshot(
    *,
    revision: int = 1,
    source_head: str = HEAD,
    origin_head: str = HEAD,
    tasks: tuple[TaskObservation, ...] | None = None,
    issues: tuple[ManagedIssueObservation, ...] | None = None,
    active: tuple[str, ...] = (),
    transitions: tuple[str, ...] = (),
    reservations: tuple[str, ...] = (),
    recovery_task_id: str | None = None,
    recovery_commit: str | None = None,
) -> CoherentGraphSnapshot:
    return CoherentGraphSnapshot(
        observation_revision=revision,
        source_branch="main",
        source_attached=True,
        source_clean=True,
        source_head=source_head,
        source_tree=TREE,
        origin_main_head=origin_head,
        initial_source_commit_is_ancestor=True,
        initial_source_tree=TREE,
        tasks=tasks if tasks is not None else (TaskObservation(TASK, "not_delivered"),),
        managed_issues=issues
        if issues is not None
        else (managed_issue(TASK, "agent_working", "implementation"),),
        active_assignment_task_ids=active,
        pending_transition_task_ids=transitions,
        reservation_task_ids=reservations,
        authorized_local_ahead_recovery_task_id=recovery_task_id,
        authorized_local_ahead_recovery_commit=recovery_commit,
    )


def working_snapshot(**overrides: Any) -> CoherentGraphSnapshot:
    """The pre-poll observation: the implementation worker still owns the task."""
    return snapshot(
        revision=1,
        issues=(managed_issue(TASK, "agent_working", "implementation"),),
        active=(TASK,),
        **overrides,
    )


def reaped_snapshot(
    *, revision: int = 2, **overrides: Any
) -> CoherentGraphSnapshot:
    """The post-poll observation: the poll reaped the worker and the Issue is waiting."""
    return snapshot(
        revision=revision,
        issues=(
            managed_issue(
                TASK, "human_action_required", "unity_runtime_validation", state_version=2
            ),
        ),
        **overrides,
    )


def pumped_snapshot(*, revision: int = 3, **overrides: Any) -> CoherentGraphSnapshot:
    """The post-pump observation proving the exact event/evidence/version move."""
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


def recovery_snapshot(
    observed: CoherentGraphSnapshot, *, task_id: str = TASK
) -> CoherentGraphSnapshot:
    """A legal authorized local-ahead recovery: source ahead of origin/main."""
    return replace(
        observed,
        source_head=AHEAD,
        origin_main_head=HEAD,
        origin_main_is_ancestor_of_source=True,
        authorized_local_ahead_recovery_task_id=task_id,
        authorized_local_ahead_recovery_commit=AHEAD,
    )


class ReapingScheduler:
    """A scheduler whose poll reaps the live worker, exactly like the live defect.

    `active_assignments` is what the controller cross-checks against the coherent
    snapshot, so clearing it inside `poll_capacity_batch` is what makes the
    post-poll snapshot legitimately expose the waiting handoff.
    """

    def __init__(
        self,
        *,
        active: tuple[str, ...] = (TASK,),
        wait_reasons: tuple[str, ...] = ("fallback_elapsed",),
        launches: int = 0,
        status: str = "worker_returned",
        fatal: bool = False,
        excluded: tuple[str, ...] = (),
    ) -> None:
        self.source = ROOT
        self.max_workers = 1
        self.excluded_task_ids = frozenset(excluded)
        self.active_assignments: dict[str, object] = {
            task_id: object() for task_id in active
        }
        self.architect_invocations_this_poll = 0
        self.worker_launches_this_poll = 0
        self._launches = launches
        self._status = status
        self._fatal = fatal
        self.wait_reasons = list(wait_reasons)
        self.poll_calls = 0
        self.wait_calls: list[float] = []
        self.lifecycle_events: list[str] = []
        self.allowlists: list[tuple[str, ...]] = []
        self.listener_active = False

    def set_admission_allowlist(self, task_ids: Any) -> None:
        self.allowlists.append(tuple(sorted(task_ids)))

    def reconcile_interrupted_architect_session(self, *, lock: Any) -> bool:
        require(lock.held, "architect recovery ran without scheduler ownership")
        return False

    def drain_active_workers(self, *, poll_seconds: float) -> bool:
        self.lifecycle_events.append("drain")
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
        # The reap: the finished worker's assignment is released here, which is
        # what makes its terminal Issue state observable to the next snapshot.
        self.active_assignments.clear()
        self.architect_invocations_this_poll = 0
        self.worker_launches_this_poll = self._launches
        return SimpleNamespace(status=self._status, fatal=self._fatal)

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


class RecordingPump:
    """Records the exact snapshot revision each attempt observed."""

    def __init__(
        self,
        *,
        results: tuple[SyntheticEvidencePumpResult | None, ...] = (None,),
    ) -> None:
        self.results = list(results)
        self.observed_revisions: list[int] = []
        self.observed_states: list[str] = []

    def __call__(
        self, observed: CoherentGraphSnapshot
    ) -> SyntheticEvidencePumpResult | None:
        self.observed_revisions.append(observed.observation_revision)
        self.observed_states.append(observed.managed_issues[0].state.value)
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]

    @property
    def calls(self) -> int:
        return len(self.observed_revisions)


def controller(
    *,
    state: SnapshotSequence,
    scheduler: ReapingScheduler,
    pump: Any = None,
    run_manifest: AutonomousRunManifest | None = None,
    excluded_synthetic: tuple[str, ...] = (PRESERVED_TASK_ID,),
) -> AutonomousGraphController:
    exact = run_manifest or manifest()
    return AutonomousGraphController(
        manifest=exact,
        scheduler=scheduler,
        scheduler_lock=FakeLock(),
        snapshotter=state,
        progress_store=MemoryProgressStore(),
        receipt_store=MemoryReceiptStore(),
        synthetic_evidence_pump=pump,
        synthetic_excluded_task_ids=excluded_synthetic,
        fallback_seconds=DEFAULT_FALLBACK_SECONDS,
    )


def success() -> SyntheticEvidencePumpResult:
    return SyntheticEvidencePumpResult(TASK, EVENT_ID, EVIDENCE)


# --------------------------- 1-5: the reaped-worker handoff runs immediately


def test_a_poll_that_reaps_a_worker_pumps_in_the_same_step() -> None:
    """Covers required proofs 1-5 as one indivisible controller step."""
    pump = RecordingPump(results=(None, success()))
    scheduler = ReapingScheduler()
    state = SnapshotSequence(
        working_snapshot(),  # 1. pre-poll: the worker is still active
        reaped_snapshot(),   # 2. post-poll: the reap exposed human_action_required
        pumped_snapshot(),   # 3. post-pump proof observation
    )
    result = controller(state=state, scheduler=scheduler, pump=pump).run(max_steps=1)

    # 1. The pre-poll attempt saw the live worker and correctly declined.
    require(pump.calls == 2, f"expected exactly two pump attempts, got {pump.calls}")
    require(pump.observed_states[0] == "agent_working",
            f"the pre-poll attempt did not observe the live worker: {pump.observed_states}")
    require(pump.observed_revisions[0] == 1,
            f"the pre-poll attempt used the wrong observation: {pump.observed_revisions}")

    # 3. The second attempt ran against the authoritative post-poll snapshot.
    require(pump.observed_states[1] == "human_action_required",
            f"the post-poll attempt did not observe the handoff: {pump.observed_states}")
    require(pump.observed_revisions[1] == 2,
            f"the post-poll attempt did not use the post-poll observation: "
            f"{pump.observed_revisions}")

    # 4. No wait was entered anywhere in the step, and the durable proof held.
    require(scheduler.wait_calls == [],
            f"the controller waited despite an eligible handoff: {scheduler.wait_calls}")
    require(scheduler.lifecycle_events == ["start", "poll", "close"],
            f"unexpected scheduler lifecycle: {scheduler.lifecycle_events}")
    require(result.wait_reason is None, f"a wait reason was recorded: {result.wait_reason}")
    require(result.evaluation.classification != "blocked",
            f"the proven mutation was reported blocked: {result.evaluation}")
    require(
        result.evaluation.fingerprint
        == evaluate_graph_state(manifest(), pumped_snapshot()).fingerprint,
        "the step did not continue from the proven post-pump state",
    )

    # 5. Exactly one synthetic mutation was performed in the step.
    require(result.progress.synthetic_pump_calls_total == 2,
            f"pump attempt accounting is wrong: {result.progress.synthetic_pump_calls_total}")
    require(scheduler.poll_calls == 1, f"more than one poll ran: {scheduler.poll_calls}")


def test_no_wait_occurs_between_reaping_and_the_eligible_pump() -> None:
    """The ordering proof: the pump attempt follows the poll with nothing between."""
    order: list[str] = []
    scheduler = ReapingScheduler()
    real_poll = scheduler.poll_capacity_batch
    real_wait = scheduler._wait_for_architect_activity

    def poll() -> SimpleNamespace:
        order.append("poll")
        return real_poll()

    def wait(poll_seconds: float) -> str:
        order.append("wait")
        return real_wait(poll_seconds)

    scheduler.poll_capacity_batch = poll
    scheduler._wait_for_architect_activity = wait

    def pump(observed: CoherentGraphSnapshot) -> SyntheticEvidencePumpResult | None:
        order.append(f"pump:{observed.managed_issues[0].state.value}")
        if observed.managed_issues[0].state is WorkflowState.HUMAN_ACTION_REQUIRED:
            return success()
        return None

    state = SnapshotSequence(working_snapshot(), reaped_snapshot(), pumped_snapshot())
    controller(state=state, scheduler=scheduler, pump=pump).run(max_steps=1)
    require(
        order == ["pump:agent_working", "poll", "pump:human_action_required"],
        f"a wait or extra step separated reaping from the pump: {order}",
    )


# ------------------------------------ 6: one mutation per step, pre-poll wins


def test_guard_a_successful_pre_poll_pump_is_not_repeated_after_polling() -> None:
    """GUARD covering required proof 6: at most one mutation per step."""
    pump = RecordingPump(results=(success(),))
    scheduler = ReapingScheduler(active=())
    # Pre-poll already shows the waiting handoff, so the first attempt mutates.
    state = SnapshotSequence(
        reaped_snapshot(revision=1),
        pumped_snapshot(revision=2),
        pumped_snapshot(revision=3),
    )
    result = controller(state=state, scheduler=scheduler, pump=pump).run(max_steps=1)
    require(pump.calls == 1,
            f"a second mutation was attempted after the poll: {pump.observed_states}")
    require(result.progress.synthetic_pump_calls_total == 1,
            f"pump accounting is wrong: {result.progress.synthetic_pump_calls_total}")
    require(scheduler.wait_calls == [], "a proven pre-poll pump still waited")


# ------------------------------- 7: a post-poll no-op is quiet and honest


def test_a_post_poll_no_op_neither_loops_nor_claims_progress() -> None:
    """An eligible-looking handoff the pump declines must fall back to the
    ordinary wait rather than spinning or reporting a mutation."""
    pump = RecordingPump(results=(None,))
    scheduler = ReapingScheduler(active=())
    waiting = reaped_snapshot(revision=1)
    state = SnapshotSequence(waiting, waiting, waiting)
    result = controller(state=state, scheduler=scheduler, pump=pump).run(max_steps=1)
    require(pump.calls == 2, f"expected one declined attempt per phase: {pump.calls}")
    require(scheduler.wait_calls == [DEFAULT_FALLBACK_SECONDS],
            f"a declined pump did not fall back to the ordinary wait: {scheduler.wait_calls}")
    require(result.wait_reason == "fallback_elapsed",
            f"unexpected wait reason: {result.wait_reason}")
    require(result.evaluation.classification != "blocked",
            f"a declined pump was treated as a failure: {result.evaluation}")
    require(scheduler.poll_calls == 1, "a declined pump re-polled inside one step")


# --------------------------- 8: an unproven post-poll mutation fails closed


def test_an_unproven_post_poll_mutation_blocks_exactly_like_a_pre_poll_one() -> None:
    pump = RecordingPump(results=(None, success()))
    scheduler = ReapingScheduler()
    # The third observation does NOT carry the claimed event/evidence/version.
    state = SnapshotSequence(
        working_snapshot(), reaped_snapshot(), reaped_snapshot(revision=3)
    )
    result = controller(state=state, scheduler=scheduler, pump=pump).run(max_steps=1)
    require(result.evaluation.classification == "blocked",
            f"an unproven post-poll mutation was accepted: {result.evaluation}")
    require(
        "synthetic_evidence_progress_was_not_proven_post_pump"
        in result.evaluation.reasons,
        f"the fail-closed reason was lost: {result.evaluation.reasons}",
    )
    require(result.cycle_status == "synthetic_evidence_unproven",
            f"unexpected cycle status: {result.cycle_status}")
    require(scheduler.wait_calls == [], "an unproven mutation still waited")

    # Each individual proof component is load-bearing after the poll.
    for label, broken in (
        (
            "event id",
            replace(
                pumped_snapshot(),
                managed_issues=(
                    managed_issue(TASK, "agent_ready", "delivery_evidence",
                                  event_id="e" * 64, evidence_sha256=EVIDENCE,
                                  state_version=3),
                ),
            ),
        ),
        (
            "evidence hash",
            replace(
                pumped_snapshot(),
                managed_issues=(
                    managed_issue(TASK, "agent_ready", "delivery_evidence",
                                  event_id=EVENT_ID, evidence_sha256="f" * 64,
                                  state_version=3),
                ),
            ),
        ),
        (
            "state version",
            replace(
                pumped_snapshot(),
                managed_issues=(
                    managed_issue(TASK, "agent_ready", "delivery_evidence",
                                  event_id=EVENT_ID, evidence_sha256=EVIDENCE,
                                  state_version=2),
                ),
            ),
        ),
    ):
        attempt = controller(
            state=SnapshotSequence(working_snapshot(), reaped_snapshot(), broken),
            scheduler=ReapingScheduler(),
            pump=RecordingPump(results=(None, success())),
        ).run(max_steps=1)
        require(attempt.evaluation.classification == "blocked",
                f"a broken {label} proof was accepted after the poll: {attempt.evaluation}")


# ------------------- 9, 11: GUARD - scope and ownership exclusions hold


def test_guard_active_and_pending_transition_tasks_are_never_eligible() -> None:
    relevant = (TASK,)
    waiting = reaped_snapshot()
    require(
        eligible_synthetic_handoff_task_ids(waiting, relevant_task_ids=relevant)
        == (TASK,),
        "a plain waiting handoff was not recognized as eligible",
    )
    require(
        eligible_synthetic_handoff_task_ids(
            replace(waiting, active_assignment_task_ids=(TASK,)),
            relevant_task_ids=relevant,
        )
        == (),
        "an active assignment was offered to the pump",
    )
    require(
        eligible_synthetic_handoff_task_ids(
            replace(waiting, pending_transition_task_ids=(TASK,)),
            relevant_task_ids=relevant,
        )
        == (),
        "a pending transition was offered to the pump",
    )
    require(
        eligible_synthetic_handoff_task_ids(
            recovery_snapshot(waiting), relevant_task_ids=relevant
        )
        == (),
        "an authorized local-ahead recovery did not suppress the pump",
    )


def test_guard_preserved_and_out_of_scope_tasks_are_never_eligible() -> None:
    waiting_preserved = snapshot(
        revision=2,
        tasks=(TaskObservation(PRESERVED_TASK_ID, "not_delivered"),),
        issues=(
            managed_issue(
                PRESERVED_TASK_ID,
                "human_action_required",
                "unity_runtime_validation",
                state_version=2,
            ),
        ),
    )
    require(
        eligible_synthetic_handoff_task_ids(
            waiting_preserved,
            relevant_task_ids=(PRESERVED_TASK_ID,),
            excluded_task_ids=(PRESERVED_TASK_ID,),
        )
        == (),
        "NSC-042 was offered to the synthetic pump",
    )
    out_of_scope = snapshot(
        revision=2,
        tasks=(TaskObservation(OUT_OF_SCOPE, "not_delivered"),),
        issues=(
            managed_issue(
                OUT_OF_SCOPE, "human_action_required", "unity_runtime_validation",
                state_version=2,
            ),
        ),
    )
    require(
        eligible_synthetic_handoff_task_ids(out_of_scope, relevant_task_ids=(TASK,))
        == (),
        "a task outside the manifest scope was offered to the pump",
    )

def test_an_out_of_scope_post_poll_mutation_is_refused() -> None:
    """The post-poll attempt inherits the pre-poll scope check verbatim."""
    escaped = controller(
        state=SnapshotSequence(working_snapshot(), reaped_snapshot(), pumped_snapshot()),
        scheduler=ReapingScheduler(),
        pump=RecordingPump(
            results=(None, SyntheticEvidencePumpResult(OUT_OF_SCOPE, EVENT_ID, EVIDENCE))
        ),
    )
    try:
        escaped.run(max_steps=1)
    except AutonomousGraphRunError as exc:
        require("outside the pre-pump run scope" in str(exc),
                f"unexpected out-of-scope refusal: {exc}")
    else:
        raise AssertionError("an out-of-scope post-poll mutation was accepted")


def test_guard_the_controller_gate_agrees_with_the_real_pump_selection() -> None:
    """The gate is a pre-check, not a second selection algorithm.

    It must never call the pump eligible where the committed
    `_SyntheticEvidencePump` would find no candidate, so the two cannot drift.
    """
    from Pipeline.TaskReviewAgent.run_autonomous_graph import _SyntheticEvidencePump

    run_manifest = manifest(targets=tuple(sorted((TASK, OTHER, PRESERVED_TASK_ID))))
    waiting = managed_issue(
        TASK, "human_action_required", "unity_runtime_validation", state_version=2
    )
    other_waiting = managed_issue(
        OTHER, "human_action_required", "unity_runtime_validation", state_version=2
    )
    preserved_waiting = managed_issue(
        PRESERVED_TASK_ID, "human_action_required", "unity_runtime_validation", state_version=2
    )
    tasks = (
        TaskObservation(TASK, "not_delivered"),
        TaskObservation(OTHER, "not_delivered"),
        TaskObservation(PRESERVED_TASK_ID, "not_delivered"),
    )
    cases = (
        ("plain waiting handoff", snapshot(revision=2, tasks=tasks, issues=(waiting,))),
        ("nothing waiting", snapshot(revision=2, tasks=tasks,
                                     issues=(managed_issue(TASK, "agent_ready",
                                                           "delivery_evidence"),))),
        ("active assignment", snapshot(revision=2, tasks=tasks, issues=(waiting,),
                                       active=(TASK,))),
        ("pending transition", snapshot(revision=2, tasks=tasks, issues=(waiting,),
                                        transitions=(TASK,))),
        ("preserved only", snapshot(revision=2, tasks=tasks, issues=(preserved_waiting,))),
        ("preserved plus eligible",
         snapshot(revision=2, tasks=tasks, issues=(preserved_waiting, other_waiting))),
        ("local-ahead recovery",
         recovery_snapshot(snapshot(revision=2, tasks=tasks, issues=(waiting,)))),
    )
    processor = _SyntheticEvidencePump(
        manifest=run_manifest,
        source=ROOT,
        checkout_root=ROOT,
        repository="cathode26/NoSafeCircle-Homework-Rehearsal",
    )
    for label, observed in cases:
        gate = eligible_synthetic_handoff_task_ids(
            observed,
            relevant_task_ids=evaluate_graph_state(
                run_manifest, observed
            ).relevant_task_ids,
            excluded_task_ids=(PRESERVED_TASK_ID,),
        )
        # Reproduce the committed pump's own candidate selection without letting
        # it open a live session: it only builds a processor once a candidate
        # exists, so an empty gate must coincide with an empty candidate list.
        selected: list[str] = []
        original = processor.processor
        try:
            processor.processor = SimpleNamespace(
                process_one=lambda task_id, expected_source_head: selected.append(task_id)
            )
            processor(observed)
        finally:
            processor.processor = original
        require(bool(gate) == bool(selected),
                f"{label}: gate {gate} disagrees with pump candidates {selected}")
        if gate and selected:
            require(selected[0] == gate[0],
                    f"{label}: the pump selected {selected[0]}, the gate offered {gate[0]}")


# --------------------- 10, 12: GUARD - disabled synthetic evidence unchanged


def test_guard_a_synthetic_disabled_run_still_waits_normally() -> None:
    scheduler = ReapingScheduler(active=())
    waiting = reaped_snapshot(revision=1)
    state = SnapshotSequence(waiting, waiting, waiting)
    result = controller(state=state, scheduler=scheduler, pump=None).run(max_steps=1)
    require(scheduler.wait_calls == [DEFAULT_FALLBACK_SECONDS],
            f"a pumpless run changed its waiting behavior: {scheduler.wait_calls}")
    require(result.wait_reason == "fallback_elapsed",
            f"unexpected wait reason without a pump: {result.wait_reason}")
    require(result.progress.synthetic_pump_calls_total == 0,
            "a pumpless run counted a synthetic attempt")


def test_guard_a_worker_wake_still_reloops_without_a_pump() -> None:
    scheduler = ReapingScheduler(active=(), wait_reasons=("worker_returned",))
    waiting = reaped_snapshot(revision=1)
    result = controller(
        state=SnapshotSequence(waiting, waiting, waiting), scheduler=scheduler, pump=None
    ).run(max_steps=1)
    require(result.wait_reason == "worker_returned", str(result.wait_reason))
    require(result.progress.wakeups_total == 1,
            f"the external wake was not counted: {result.progress.wakeups_total}")


def test_guard_the_configured_fallback_is_not_shortened() -> None:
    scheduler = ReapingScheduler(active=())
    waiting = reaped_snapshot(revision=1)
    controller(
        state=SnapshotSequence(waiting, waiting, waiting),
        scheduler=scheduler,
        pump=RecordingPump(results=(None,)),
    ).run(max_steps=1)
    require(scheduler.wait_calls == [DEFAULT_FALLBACK_SECONDS],
            f"the configured fallback was changed: {scheduler.wait_calls}")


def test_guard_no_fabricated_human_authority_reaches_the_controller() -> None:
    import inspect

    from Pipeline.TaskReviewAgent import autonomous_graph_run as graph_run

    source = inspect.getsource(graph_run.AutonomousGraphController)
    for forbidden in ("apply_human_result", "pass_and_resume_task", "human_result"):
        require(forbidden not in source,
                f"the controller can now fabricate human authority: {forbidden}")
    gate = inspect.getsource(graph_run.eligible_synthetic_handoff_task_ids)
    require("HUMAN_ACTION_REQUIRED" in gate,
            "the eligibility gate no longer requires a waiting human action")


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
        print(f"post_poll_synthetic_pump_smoke_test: FAIL ({len(FAILURES)})")
        return 1
    print(f"post_poll_synthetic_pump_smoke_test: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
