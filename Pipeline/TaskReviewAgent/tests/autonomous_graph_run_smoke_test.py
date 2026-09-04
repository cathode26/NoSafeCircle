#!/usr/bin/env python3
"""Pure deterministic tests for the autonomous graph-completion wrapper.

Classification: pure/component tests. These are regression-only orchestration
checks. They use injected snapshots, schedulers, wake results, in-memory progress,
and one disposable receipt directory; no Git, GitHub, provider, worker, TaskGraph,
Unity asset, or canonical checkout is read or mutated.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.autonomous_graph_run as graph_run  # noqa: E402
import Pipeline.TaskReviewAgent.polling_orchestrator as polling_module  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import WorkflowPhase, WorkflowState  # noqa: E402
from Pipeline.TaskReviewAgent.autonomous_graph_run import (  # noqa: E402
    AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
    DEFAULT_FALLBACK_SECONDS,
    AutonomousGraphController,
    AutonomousGraphRunError,
    AutonomousRunManifest,
    AutonomousRuntimeConfiguration,
    CoherentGraphSnapshot,
    GraphCompleteReceipt,
    JsonManifestStore,
    JsonReceiptStore,
    ManagedIssueObservation,
    MemoryProgressStore,
    MemoryReceiptStore,
    SyntheticEvidencePumpResult,
    TaskObservation,
    autonomous_run_paths,
    evaluate_graph_state,
)


HEAD = "1" * 40
TREE = "2" * 40
TASK = "NSC-901"
CHILD = "NSC-902"
EXCLUDED = "NSC-042"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action: Any, expected: type[BaseException] = AutonomousGraphRunError) -> BaseException:
    try:
        action()
    except expected as exc:
        return exc
    raise AssertionError(f"expected {expected.__name__}")


def manifest(
    *,
    targets: tuple[str, ...] = (TASK,),
    excluded: tuple[str, ...] = (),
    capacity: int = 10,
) -> AutonomousRunManifest:
    return AutonomousRunManifest(
        schema_version=AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
        run_id="gauntlet-run-1",
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
            synthetic_evidence_enabled=False,
        ),
        initial_source_commit=HEAD,
        initial_source_tree=TREE,
        target_task_ids=targets,
        excluded_task_ids=excluded,
        max_capacity=capacity,
    )


def managed_issue(
    task_id: str,
    state: str,
    phase: str,
    *,
    event_id: str = "a" * 64,
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
    branch: str = "main",
    attached: bool = True,
    clean: bool = True,
    source_head: str = HEAD,
    source_tree: str = TREE,
    origin_head: str = HEAD,
    initial_ancestor: bool = True,
    initial_tree: str = TREE,
    origin_ancestor: bool = True,
    recovery_task_id: str | None = None,
    recovery_commit: str | None = None,
    active: tuple[str, ...] = (),
    transitions: tuple[str, ...] = (),
    reservations: tuple[str, ...] = (),
) -> CoherentGraphSnapshot:
    return CoherentGraphSnapshot(
        observation_revision=revision,
        source_branch=branch,
        source_attached=attached,
        source_clean=clean,
        source_head=source_head,
        source_tree=source_tree,
        origin_main_head=origin_head,
        initial_source_commit_is_ancestor=initial_ancestor,
        initial_source_tree=initial_tree,
        tasks=tasks
        if tasks is not None
        else (TaskObservation(TASK, "conformant"),),
        managed_issues=issues
        if issues is not None
        else (managed_issue(TASK, "complete", "merge_closeout"),),
        active_assignment_task_ids=active,
        pending_transition_task_ids=transitions,
        reservation_task_ids=reservations,
        origin_main_is_ancestor_of_source=origin_ancestor,
        authorized_local_ahead_recovery_task_id=recovery_task_id,
        authorized_local_ahead_recovery_commit=recovery_commit,
    )


class FakeScheduler:
    def __init__(
        self,
        *,
        capacity: int = 10,
        statuses: tuple[tuple[str, bool], ...] = (("idle", False),),
        wait_reasons: tuple[str, ...] = ("fallback_elapsed",),
        architect_calls: tuple[int, ...] = (0,),
        launch_counts: tuple[int, ...] | None = None,
        launch_task: str | None = None,
        source: Path = ROOT,
        excluded: tuple[str, ...] = (),
        drain_result: bool = True,
    ) -> None:
        self.source = source
        self.max_workers = capacity
        self.excluded_task_ids = frozenset(excluded)
        self.drain_result = drain_result
        self.statuses = list(statuses)
        self.wait_reasons = list(wait_reasons)
        self.architect_calls = list(architect_calls)
        self.launch_counts = list(
            launch_counts if launch_counts is not None else ((1,) if launch_task else (0,))
        )
        self.launch_task = launch_task
        self.active_assignments: dict[str, object] = {}
        self.architect_invocations_this_poll = 0
        self.worker_launches_this_poll = 0
        self.poll_calls = 0
        self.wait_calls: list[float] = []
        self.lifecycle_events: list[str] = []
        self.listener_active = False
        self.require_listener_for_wait = False
        self.allowlists: list[tuple[str, ...]] = []
        self.drain_calls: list[float] = []

    def set_admission_allowlist(self, task_ids: Any) -> None:
        self.allowlists.append(tuple(sorted(task_ids)))

    def drain_active_workers(self, *, poll_seconds: float) -> bool:
        self.lifecycle_events.append("drain")
        self.drain_calls.append(poll_seconds)
        if self.drain_result:
            self.active_assignments.clear()
        return self.drain_result

    def start_activity_listener(self) -> bool:
        if not self.listener_active:
            self.lifecycle_events.append("start")
            self.listener_active = True
        return True

    def close_activity_listener(self) -> None:
        if self.listener_active:
            self.lifecycle_events.append("close")
            self.listener_active = False

    def poll_capacity_batch(self) -> SimpleNamespace:
        self.lifecycle_events.append("poll")
        self.poll_calls += 1
        status, fatal = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        self.architect_invocations_this_poll = (
            self.architect_calls.pop(0)
            if len(self.architect_calls) > 1
            else self.architect_calls[0]
        )
        self.worker_launches_this_poll = (
            self.launch_counts.pop(0)
            if len(self.launch_counts) > 1
            else self.launch_counts[0]
        )
        if self.launch_task is not None:
            self.active_assignments[self.launch_task] = object()
        return SimpleNamespace(status=status, fatal=fatal)

    def _wait_for_architect_activity(self, poll_seconds: float) -> str:
        if self.require_listener_for_wait and not self.listener_active:
            raise AssertionError("activity wait began before its listener")
        self.lifecycle_events.append("wait")
        self.wait_calls.append(poll_seconds)
        return self.wait_reasons.pop(0) if len(self.wait_reasons) > 1 else self.wait_reasons[0]


class SnapshotSequence:
    def __init__(self, *values: CoherentGraphSnapshot) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self) -> CoherentGraphSnapshot:
        self.calls += 1
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]


class FakeLock:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.held = False

    def acquire(self) -> None:
        if self.held:
            raise AssertionError("fixture lock acquired twice")
        self.events.append("acquire")
        self.held = True

    def release(self) -> None:
        if not self.held:
            raise AssertionError("fixture lock released while unheld")
        self.events.append("release")
        self.held = False


def controller(
    *,
    state: CoherentGraphSnapshot | SnapshotSequence,
    scheduler: FakeScheduler | None = None,
    run_manifest: AutonomousRunManifest | None = None,
    store: MemoryProgressStore | None = None,
    lock: FakeLock | None = None,
    receipt_store: MemoryReceiptStore | None = None,
    pump: Any = None,
    fallback: float = DEFAULT_FALLBACK_SECONDS,
) -> AutonomousGraphController:
    exact_manifest = run_manifest or manifest()
    exact_scheduler = scheduler or FakeScheduler(
        capacity=exact_manifest.max_capacity,
        excluded=exact_manifest.excluded_task_ids,
    )
    snapshotter = state if isinstance(state, SnapshotSequence) else SnapshotSequence(state)
    return AutonomousGraphController(
        manifest=exact_manifest,
        scheduler=exact_scheduler,
        scheduler_lock=lock or FakeLock(),
        snapshotter=snapshotter,
        progress_store=store or MemoryProgressStore(),
        receipt_store=receipt_store or MemoryReceiptStore(),
        synthetic_evidence_pump=pump,
        fallback_seconds=fallback,
    )


def test_manifest_is_exact_and_capacity_is_capped_at_ten() -> None:
    value = manifest()
    require(AutonomousRunManifest.from_dict(value.to_dict()) == value, "manifest did not round-trip")
    require(
        value.sha256 == hashlib.sha256(value.canonical_json.encode("utf-8")).hexdigest(),
        "manifest identity is not exact canonical JSON",
    )
    rejects(lambda: manifest(capacity=11))
    rejects(lambda: manifest(targets=(TASK, TASK)))
    rejects(lambda: manifest(targets=(TASK,), excluded=(TASK,)))
    rejects(lambda: replace(value, github_repository="not-a-repository"))
    malformed = value.to_dict()
    malformed["extra"] = True
    rejects(lambda: AutonomousRunManifest.from_dict(malformed))
    rejects(
        lambda: controller(
            state=snapshot(),
            scheduler=FakeScheduler(capacity=9),
            run_manifest=value,
        )
    )
    excludes_42 = manifest(excluded=(EXCLUDED,))
    rejects(
        lambda: controller(
            state=snapshot(),
            scheduler=FakeScheduler(capacity=10, excluded=()),
            run_manifest=excludes_42,
        )
    )
    rejects(
        lambda: controller(
            state=snapshot(),
            scheduler=FakeScheduler(capacity=10, source=ROOT.parent),
            run_manifest=value,
        )
    )


def test_wrapper_delegates_exactly_one_capacity_pass_without_duplicate_scheduling() -> None:
    fake = FakeScheduler(statuses=(("worker_launched", False),))
    pending = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_ready", "implementation"),),
    )
    result = controller(state=pending, scheduler=fake).run(max_steps=1)
    require(result.evaluation.classification == "actionable", "pending fixture changed state")
    require(fake.poll_calls == 1, "wrapper did not delegate exactly one capacity pass")
    require(fake.allowlists == [(TASK,)], "exact run allowlist was not installed pre-poll")
    source = inspect.getsource(graph_run)
    require("plan_dispatch" not in source, "wrapper imported Stage 2 scheduling logic")
    require("process_factory" not in source, "wrapper grew a second worker launcher")
    require("poll_capacity_batch()" in source, "wrapper does not use canonical scheduler pass")


def test_completion_refuses_every_missing_authority_condition() -> None:
    base = snapshot()
    cases = {
        "task_conformance": replace(
            base, tasks=(TaskObservation(TASK, "not_delivered"),)
        ),
        "managed_issue": replace(base, managed_issues=()),
        "terminal_issue": replace(
            base,
            managed_issues=(managed_issue(TASK, "agent_ready", "delivery_evidence"),),
        ),
        "assignment": replace(base, active_assignment_task_ids=(TASK,)),
        "transition": replace(base, pending_transition_task_ids=(TASK,)),
        "reservation": replace(base, reservation_task_ids=(TASK,)),
        "clean_source": replace(base, source_clean=False),
        "attached_source": replace(base, source_attached=False),
        "main_branch": replace(base, source_branch="review/test"),
        "origin_sync": replace(base, origin_main_head="3" * 40),
    }
    for name, observed in cases.items():
        evaluation = evaluate_graph_state(manifest(), observed)
        require(evaluation.classification != "complete", f"{name} incorrectly completed")
        rejects(
            lambda evaluation=evaluation, observed=observed: graph_run.GraphCompleteReceipt.create(
                manifest=manifest(),
                snapshot=observed,
                evaluation=evaluation,
                progress=graph_run.AutonomousRunProgress.create(manifest()),
            )
        )


def test_authorized_descendants_are_required_and_excluded_task_is_not_counted() -> None:
    run_manifest = manifest(excluded=(EXCLUDED,))
    tasks = (
        TaskObservation(TASK, "conformant", (CHILD,)),
        TaskObservation(CHILD, "not_delivered"),
        TaskObservation(EXCLUDED, "invalid_evidence"),
    )
    issues = (
        managed_issue(TASK, "complete", "merge_closeout"),
        managed_issue(CHILD, "agent_ready", "implementation"),
        managed_issue(EXCLUDED, "blocked", "unity_runtime_validation"),
    )
    observed = snapshot(
        tasks=tasks,
        issues=issues,
        transitions=(EXCLUDED,),
        reservations=(EXCLUDED,),
    )
    pending = evaluate_graph_state(run_manifest, observed)
    require(pending.classification == "actionable", "unfinished child was not required")
    require(pending.relevant_task_ids == (TASK, CHILD), "descendant closure is wrong")
    complete = evaluate_graph_state(
        run_manifest,
        replace(
            observed,
            tasks=(
                TaskObservation(TASK, "conformant", (CHILD,)),
                TaskObservation(CHILD, "conformant"),
                TaskObservation(EXCLUDED, "invalid_evidence"),
            ),
            managed_issues=(
                managed_issue(TASK, "complete", "merge_closeout"),
                managed_issue(CHILD, "complete", "merge_closeout"),
                managed_issue(EXCLUDED, "blocked", "unity_runtime_validation"),
            ),
        ),
    )
    require(complete.classification == "complete", "excluded NSC-042 blocked completion")
    require(EXCLUDED not in complete.relevant_task_ids, "excluded NSC-042 was falsely counted")
    escaped = evaluate_graph_state(
        run_manifest,
        replace(observed, active_assignment_task_ids=(EXCLUDED,)),
    )
    require(escaped.classification == "blocked", "live out-of-scope assignment was ignored")


def test_fingerprint_is_exact_deterministic_and_ignores_observer_revision() -> None:
    first = evaluate_graph_state(manifest(), snapshot(revision=1))
    second = evaluate_graph_state(manifest(), snapshot(revision=999))
    require(first.fingerprint == second.fingerprint, "observer revision polluted durable fingerprint")
    expected_payload = {
        "manifest_sha256": manifest().sha256,
        "source": {
            "branch": "main",
            "attached": True,
            "clean": True,
            "head": HEAD,
            "tree": TREE,
            "origin_main_head": HEAD,
            "initial_source_commit_is_ancestor": True,
            "initial_source_tree": TREE,
            "origin_main_is_ancestor_of_source": True,
            "authorized_local_ahead_recovery_task_id": None,
            "authorized_local_ahead_recovery_commit": None,
        },
        "tasks": [TaskObservation(TASK, "conformant").to_dict()],
        "managed_issues": [managed_issue(TASK, "complete", "merge_closeout").to_dict()],
        "active_assignment_task_ids": [],
        "pending_transition_task_ids": [],
        "reservation_task_ids": [],
        "missing_task_ids": [],
        "out_of_scope_active_assignment_task_ids": [],
    }
    expected = hashlib.sha256(
        json.dumps(
            expected_payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    require(first.fingerprint == expected, "fingerprint differs from exact canonical evidence")
    changed = evaluate_graph_state(
        manifest(), replace(snapshot(), source_tree="4" * 40)
    )
    require(changed.fingerprint != first.fingerprint, "durable state change did not change fingerprint")
    issue_identity_changed = evaluate_graph_state(
        manifest(),
        replace(
            snapshot(),
            managed_issues=(
                managed_issue(
                    TASK,
                    "complete",
                    "merge_closeout",
                    event_id="c" * 64,
                    evidence_sha256="d" * 64,
                ),
            ),
        ),
    )
    require(
        issue_identity_changed.fingerprint != first.fingerprint,
        "Issue event/evidence identities were omitted from fingerprint",
    )
    base_issue = managed_issue(TASK, "complete", "merge_closeout")
    working_issue = managed_issue(TASK, "agent_working", "implementation")
    identity_pairs = {
        "state_version": (base_issue, replace(base_issue, state_version=2)),
        "head_commit": (base_issue, replace(base_issue, head_commit="3" * 40)),
        "handoff_commit": (
            base_issue,
            replace(base_issue, human_handoff_commit="4" * 40),
        ),
        "worker_id": (
            working_issue,
            replace(working_issue, worker_id="different-worker"),
        ),
        "lease_id": (working_issue, replace(working_issue, lease_id="e" * 64)),
        "decomposition_run_id": (
            base_issue,
            replace(base_issue, decomposition_run_id="decomposition-run-2"),
        ),
        "graph_delta_plan_id": (
            base_issue,
            replace(base_issue, graph_delta_plan_id="GDP-" + "f" * 64),
        ),
    }
    for name, (before, after) in identity_pairs.items():
        before_fingerprint = evaluate_graph_state(
            manifest(), replace(snapshot(), managed_issues=(before,))
        ).fingerprint
        after_fingerprint = evaluate_graph_state(
            manifest(), replace(snapshot(), managed_issues=(after,))
        ).fingerprint
        require(
            before_fingerprint != after_fingerprint,
            f"Issue {name} was omitted from fingerprint",
        )


def test_complete_receipt_is_deterministic_and_only_emitted_after_strict_proof() -> None:
    first = controller(state=snapshot()).run(max_steps=1)
    second = controller(state=snapshot(revision=88)).run(max_steps=1)
    require(first.receipt is not None and second.receipt is not None, "completion receipt missing")
    require(first.receipt.to_dict() == second.receipt.to_dict(), "receipt is not deterministic")
    payload = first.receipt.to_dict()
    receipt_sha = payload.pop("receipt_sha256")
    expected = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    require(receipt_sha == expected, "receipt SHA does not bind its exact body")
    rejects(
        lambda: first.receipt.lifetime_counters.__setitem__(0, ("poll_cycles_total", 99)),
        (AttributeError, TypeError),
    )


def test_first_baseline_requires_exact_tree_or_a_proven_main_fast_forward() -> None:
    wrong_tree = snapshot(source_tree="4" * 40)
    fake = FakeScheduler()
    rejected = controller(state=wrong_tree, scheduler=fake).run(max_steps=1)
    require(rejected.evaluation.classification == "blocked", "wrong initial tree was accepted")
    require(fake.poll_calls == 0, "wrong initial tree reached the scheduler")
    require(not rejected.progress.baseline_verified, "failed baseline was persisted as verified")

    no_ancestor = snapshot(
        source_head="3" * 40,
        source_tree="4" * 40,
        origin_head="3" * 40,
        initial_ancestor=False,
    )
    rejected = controller(state=no_ancestor, scheduler=FakeScheduler()).run(max_steps=1)
    require(rejected.evaluation.classification == "blocked", "unrelated main history was accepted")

    fast_forward = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_ready", "implementation"),),
        source_head="3" * 40,
        source_tree="4" * 40,
        origin_head="3" * 40,
        initial_ancestor=True,
    )
    accepted = controller(
        state=fast_forward,
        scheduler=FakeScheduler(statuses=(("worker_launched", False),)),
    ).run(max_steps=1)
    require(accepted.progress.baseline_verified, "proven main fast-forward was rejected")

    wrong_ancestor_tree = controller(
        state=fast_forward,
        run_manifest=replace(manifest(), initial_source_tree="9" * 40),
        scheduler=FakeScheduler(statuses=(("worker_launched", False),)),
    ).run(max_steps=1)
    require(
        wrong_ancestor_tree.evaluation.classification == "blocked",
        "fast-forward accepted a false initial tree identity",
    )


def test_only_one_relevant_proven_d1c_local_ahead_recovery_may_poll() -> None:
    local_head = "3" * 40
    run_manifest = manifest(targets=(TASK, CHILD))
    local_ahead = snapshot(
        tasks=(
            TaskObservation(TASK, "not_delivered"),
            TaskObservation(CHILD, "not_delivered"),
        ),
        issues=(
            managed_issue(TASK, "agent_ready", "decomposition_apply"),
            managed_issue(CHILD, "agent_ready", "implementation"),
        ),
        source_head=local_head,
        source_tree="4" * 40,
        origin_head=HEAD,
        recovery_task_id=TASK,
        recovery_commit=local_head,
        reservations=(TASK,),
    )
    fake = FakeScheduler()
    result = controller(
        state=local_ahead,
        scheduler=fake,
        run_manifest=run_manifest,
    ).run(max_steps=1)
    require(result.evaluation.classification == "temporary_wait", str(result.evaluation))
    require(fake.poll_calls == 1, "authorized D1C recovery did not poll")
    require(fake.allowlists == [(TASK,)], f"D1C recovery scope leaked: {fake.allowlists}")

    arbitrary = replace(
        local_ahead,
        authorized_local_ahead_recovery_task_id=None,
        authorized_local_ahead_recovery_commit=None,
    )
    arbitrary_fake = FakeScheduler()
    blocked = controller(
        state=arbitrary,
        scheduler=arbitrary_fake,
        run_manifest=run_manifest,
    ).run(max_steps=1)
    require(blocked.evaluation.classification == "blocked", "arbitrary local-ahead ran")
    require(arbitrary_fake.poll_calls == 0, "arbitrary local-ahead reached scheduler")

    outside = replace(
        local_ahead,
        authorized_local_ahead_recovery_task_id=EXCLUDED,
    )
    outside_fake = FakeScheduler()
    blocked = controller(
        state=outside,
        scheduler=outside_fake,
        run_manifest=run_manifest,
    ).run(max_steps=1)
    require(blocked.evaluation.classification == "blocked", "out-of-scope D1C ran")
    require(outside_fake.poll_calls == 0, "out-of-scope D1C reached scheduler")


def test_task_and_issue_enums_and_state_phase_pairs_are_exact() -> None:
    rejects(lambda: TaskObservation(TASK, "looks_good"))
    rejects(lambda: managed_issue(TASK, "complete", "implementation"))
    rejects(lambda: managed_issue(TASK, "human_action_required", "merge_closeout"))
    rejects(
        lambda: ManagedIssueObservation(
            task_id=TASK,
            state="complete",
            phase="merge_closeout",
            state_version=1,
            last_event_id="a" * 64,
            head_commit=None,
            human_handoff_commit=None,
            worker_id=None,
            lease_id=None,
            decomposition_run_id=None,
            graph_delta_plan_id=None,
            last_event_evidence_sha256=None,
        )
    )
    rejects(
        lambda: ManagedIssueObservation(
            task_id=TASK,
            state=WorkflowState.AGENT_WORKING,
            phase=WorkflowPhase.IMPLEMENTATION,
            state_version=1,
            last_event_id="a" * 64,
            head_commit=None,
            human_handoff_commit=None,
            worker_id=None,
            lease_id=None,
            decomposition_run_id=None,
            graph_delta_plan_id=None,
            last_event_evidence_sha256=None,
        )
    )


def test_terminal_conformance_dispositions_fail_closed_before_admission() -> None:
    for disposition in (
        "needs_replan",
        "needs_human",
        "invalid_evidence",
        "ambiguous_evidence",
        "superseded",
        "cancelled",
    ):
        fake = FakeScheduler()
        result = controller(
            state=snapshot(tasks=(TaskObservation(TASK, disposition),)),
            scheduler=fake,
        ).run(max_steps=1)
        require(result.evaluation.classification == "blocked", disposition)
        require(
            f"{TASK}={disposition}" in ",".join(result.evaluation.reasons),
            f"{disposition} lacked an exact terminal reason",
        )
        require(fake.poll_calls == 0, f"{disposition} reached admission")


def test_dynamic_scope_contains_only_roots_and_authorized_descendants() -> None:
    observed = snapshot(
        tasks=(
            TaskObservation(TASK, "aggregate", (CHILD,)),
            TaskObservation(CHILD, "not_delivered"),
            TaskObservation(EXCLUDED, "not_delivered"),
        ),
        issues=(
            managed_issue(TASK, "complete", "decomposition_apply"),
            managed_issue(CHILD, "agent_ready", "implementation"),
            managed_issue(EXCLUDED, "agent_ready", "implementation"),
        ),
    )
    fake = FakeScheduler(statuses=(("worker_launched", False),))
    controller(state=observed, scheduler=fake).run(max_steps=1)
    require(fake.allowlists == [(TASK, CHILD)], f"wrong dynamic allowlist: {fake.allowlists}")

    escaped_scheduler = FakeScheduler()
    escaped_scheduler.active_assignments[EXCLUDED] = object()
    escaped = controller(
        state=replace(observed, active_assignment_task_ids=(EXCLUDED,)),
        scheduler=escaped_scheduler,
    ).run(max_steps=1)
    require(escaped.evaluation.classification == "blocked", "escaped assignment was ignored")
    require(escaped_scheduler.poll_calls == 0, "escaped assignment reached admission")


def test_worker_and_issue_wakes_reloop_immediately_with_bounded_fallback() -> None:
    waiting = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "human_action_required", "unity_runtime_validation"),),
        reservations=(TASK,),
    )
    for wake in ("worker_returned", "issue_state_changed"):
        fake = FakeScheduler(wait_reasons=(wake,))
        result = controller(state=waiting, scheduler=fake).run(max_steps=1)
        require(result.wait_reason == wake, f"{wake}: wake was not surfaced")
        require(fake.wait_calls == [DEFAULT_FALLBACK_SECONDS], f"{wake}: wrong fallback bound")
        require(result.progress.wakeups_total == 1, f"{wake}: wake counter missing")
        require(result.progress.fallback_waits_total == 0, f"{wake}: wake counted as fallback")
    rejects(lambda: controller(state=waiting, fallback=DEFAULT_FALLBACK_SECONDS + 0.1))


def test_run_owns_listener_before_issue_wait_and_closes_after_completion() -> None:
    waiting = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "human_action_required", "unity_runtime_validation"),),
        reservations=(TASK,),
    )
    fake = FakeScheduler(
        statuses=(("idle", False), ("idle", False)),
        wait_reasons=("issue_state_changed",),
    )
    fake.require_listener_for_wait = True
    running = controller(
        state=SnapshotSequence(waiting, waiting, snapshot(revision=2)),
        scheduler=fake,
    )
    result = running.run()
    require(result.evaluation.classification == "complete", "wake did not re-loop to completion")
    require(
        fake.lifecycle_events == ["start", "poll", "wait", "close"],
        f"wrong listener lifecycle order: {fake.lifecycle_events}",
    )
    require(fake.wait_calls == [DEFAULT_FALLBACK_SECONDS], "Issue wake missed bounded fallback seam")
    require(result.progress.wakeups_total == 1, "Issue wake was not counted")


def test_run_closes_listener_when_observation_raises_and_step_owns_no_lifecycle() -> None:
    complete_scheduler = FakeScheduler()
    outside = controller(state=snapshot(), scheduler=complete_scheduler)
    require(not hasattr(outside, "step"), "controller exposed an unlocked public step")
    rejects(outside._step)
    rejects(outside._poll)
    require(
        complete_scheduler.lifecycle_events == [],
        "private capacity pass ran without lifecycle ownership",
    )

    failing_scheduler = FakeScheduler()

    def fail_snapshot() -> CoherentGraphSnapshot:
        raise RuntimeError("fixture observation failure")

    failing_lock = FakeLock()
    running = AutonomousGraphController(
        manifest=manifest(),
        scheduler=failing_scheduler,
        scheduler_lock=failing_lock,
        snapshotter=fail_snapshot,
        progress_store=MemoryProgressStore(),
        receipt_store=MemoryReceiptStore(),
    )
    rejects(running.run, RuntimeError)
    require(
        failing_scheduler.lifecycle_events == ["start", "close"],
        f"exception leaked listener: {failing_scheduler.lifecycle_events}",
    )
    require(failing_lock.events == ["acquire", "release"], "exception leaked scheduler lock")


def test_fatal_cycle_drains_children_before_listener_and_lock_release() -> None:
    waiting = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_working", "implementation"),),
        active=(TASK,),
        reservations=(TASK,),
    )
    fake = FakeScheduler(statuses=(("worker_failed", True),))
    fake.active_assignments[TASK] = object()
    lock = FakeLock()
    result = controller(
        state=waiting,
        scheduler=fake,
        lock=lock,
    ).run()
    require(result.scheduler_fatal, "fatal cycle identity was lost")
    require(fake.drain_calls == [DEFAULT_FALLBACK_SECONDS], "fatal children were not drained")
    require(fake.lifecycle_events == ["start", "poll", "drain", "close"], "wrong fatal order")
    require(lock.events == ["acquire", "release"] and not lock.held, "fatal run leaked lock")


def test_receipt_is_persisted_atomically_while_run_lock_is_held() -> None:
    lock = FakeLock()

    class LockBoundReceiptStore(MemoryReceiptStore):
        def save(self, receipt: Any) -> None:
            require(lock.held, "receipt was persisted outside scheduler lock")
            super().save(receipt)

    receipts = LockBoundReceiptStore()
    result = controller(
        state=snapshot(),
        lock=lock,
        receipt_store=receipts,
    ).run()
    require(receipts.value == result.receipt, "exact receipt was not persisted")
    require(lock.events == ["acquire", "release"], "receipt run leaked lock")
    require(GraphCompleteReceipt.from_dict(result.receipt.to_dict()) == result.receipt, "receipt did not round-trip")
    malformed = result.receipt.to_dict()
    malformed["manifest_sha256"] = "not-a-sha"
    malformed["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in malformed.items() if key != "receipt_sha256"},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    rejects(lambda: GraphCompleteReceipt.from_dict(malformed))


def test_json_receipt_final_creation_is_exclusive_and_never_overwrites() -> None:
    first_result = controller(state=snapshot()).run(max_steps=1)
    advanced = snapshot(
        revision=2,
        source_head="3" * 40,
        source_tree="4" * 40,
        origin_head="3" * 40,
    )
    second_result = controller(state=advanced).run(max_steps=1)
    require(first_result.receipt is not None, "first receipt missing")
    require(second_result.receipt is not None, "second receipt missing")
    with tempfile.TemporaryDirectory(
        prefix=".autonomous-receipt-test-", dir=ROOT
    ) as text:
        path = Path(text) / "graph-complete.json"
        store = JsonReceiptStore(path)
        store.save(first_result.receipt)
        original = path.read_bytes()
        store.save(first_result.receipt)
        rejects(lambda: store.save(second_result.receipt))
        require(path.read_bytes() == original, "conflicting receipt overwrote final path")
        require(
            [item.name for item in path.parent.iterdir()] == [path.name],
            "exclusive receipt creation leaked a temporary file",
        )


def test_repository_bound_run_paths_and_immutable_manifest_resume() -> None:
    expected = manifest()
    with tempfile.TemporaryDirectory(
        prefix=".autonomous-manifest-test-", dir=ROOT
    ) as text:
        paths = autonomous_run_paths(
            checkout_root=Path(text),
            github_repository=expected.github_repository,
            run_id=expected.run_id,
        )
        repository_hash = hashlib.sha256(
            expected.github_repository.casefold().encode("utf-8")
        ).hexdigest()
        require(paths.root.parent.name == repository_hash, "run path was not repository-bound")
        require(paths.manifest.parent == paths.root, "manifest escaped run root")
        require(paths.progress.name == "progress.json", "wrong progress path")
        require(paths.receipt.name == "graph-complete.json", "wrong receipt path")
        require(paths.events.name == "events.jsonl", "wrong event journal path")

        store = JsonManifestStore(paths.manifest)
        require(store.load() is None, "new run unexpectedly had a manifest")
        require(store.create_or_load(expected) == expected, "manifest creation changed identity")
        original = paths.manifest.read_bytes()
        require(store.create_or_load(expected) == expected, "exact resume was rejected")
        require(paths.manifest.read_bytes() == original, "exact resume rewrote manifest")
        for changed in (
            replace(expected, github_repository="cathode26/another-rehearsal"),
            replace(expected, target_task_ids=(CHILD,)),
            replace(expected, max_capacity=9),
            replace(expected, initial_source_commit="3" * 40),
            replace(expected, initial_source_tree="4" * 40),
        ):
            rejects(lambda changed=changed: store.create_or_load(changed))
            require(paths.manifest.read_bytes() == original, "mismatch changed manifest")

        receipt = controller(state=snapshot()).run(max_steps=1).receipt
        require(receipt is not None, "complete fixture did not create receipt")
        receipt_store = JsonReceiptStore(paths.receipt)
        require(receipt_store.load() is None, "new run unexpectedly had a receipt")
        receipt_store.save(receipt)
        require(receipt_store.load() == receipt, "receipt did not load exactly")


def test_existing_receipt_short_circuits_before_scheduler_or_observation() -> None:
    completed = controller(state=snapshot()).run(max_steps=1)
    require(completed.receipt is not None, "complete fixture did not create receipt")
    receipts = MemoryReceiptStore()
    receipts.save(completed.receipt)
    fake = FakeScheduler()
    lock = FakeLock()
    snapshots = SnapshotSequence(snapshot())
    resumed = AutonomousGraphController(
        manifest=manifest(),
        scheduler=fake,
        scheduler_lock=lock,
        snapshotter=snapshots,
        progress_store=MemoryProgressStore(),
        receipt_store=receipts,
    ).run()
    require(resumed.cycle_status == "already_complete", "receipt did not short-circuit")
    require(resumed.receipt == completed.receipt, "resume returned a different receipt")
    require(snapshots.calls == 0, "completed resume observed Git or GitHub state")
    require(fake.lifecycle_events == [], "completed resume started the scheduler")
    require(lock.events == [], "completed resume acquired the scheduler lock")

    wrong = MemoryReceiptStore()
    wrong.save(completed.receipt)
    rejects(
        lambda: AutonomousGraphController(
            manifest=replace(manifest(), run_id="different-run"),
            scheduler=FakeScheduler(),
            scheduler_lock=FakeLock(),
            snapshotter=SnapshotSequence(snapshot()),
            progress_store=MemoryProgressStore(),
            receipt_store=wrong,
        ).run()
    )


def test_run_drains_live_out_of_scope_assignment_before_terminating() -> None:
    run_manifest = manifest(excluded=(EXCLUDED,))
    observed = snapshot(active=(EXCLUDED,))
    fake = FakeScheduler(excluded=(EXCLUDED,))
    fake.active_assignments[EXCLUDED] = object()
    result = controller(
        state=observed,
        scheduler=fake,
        run_manifest=run_manifest,
    ).run()
    require(result.evaluation.classification == "blocked", "escaped worker did not block")
    require(fake.poll_calls == 0, "escaped worker reached scheduler admission")
    require(fake.drain_calls == [DEFAULT_FALLBACK_SECONDS], "escaped worker was orphaned")
    require(fake.lifecycle_events == ["start", "drain", "close"], "wrong stop lifecycle")

    timeout = FakeScheduler(excluded=(EXCLUDED,), drain_result=False)
    timeout.active_assignments[EXCLUDED] = object()
    timeout_lock = FakeLock()
    rejects(
        lambda: controller(
            state=observed,
            scheduler=timeout,
            run_manifest=run_manifest,
            lock=timeout_lock,
        ).run()
    )
    require(timeout.drain_calls == [DEFAULT_FALLBACK_SECONDS], "timed-out drain was retried")
    require(
        timeout.lifecycle_events == ["start", "drain", "close"],
        "drain timeout leaked lifecycle",
    )
    require(timeout_lock.events == ["acquire", "release"], "drain timeout leaked lock")


def test_real_scheduler_listener_methods_are_idempotent_and_restartable() -> None:
    events: list[str] = []

    class SpyListener:
        def __init__(self, source: Path, *, scheduler_id: str, wake_event: Any) -> None:
            require(source == ROOT.resolve(), "listener received wrong source")
            require(scheduler_id == "autonomous-listener-test", "listener received wrong scheduler")
            require(wake_event is orchestrator.worker_completion_event, "listener received wrong wake event")

        def start(self) -> None:
            events.append("start")

        def close(self) -> None:
            events.append("close")

    orchestrator = polling_module.PollingOrchestrator(
        source=ROOT,
        checkout_root=ROOT / ".unused-autonomous-checkouts",
        scheduler_id="autonomous-listener-test",
        execution_provider=None,
        model=None,
        max_turns=None,
        max_workers=1,
        architect_min_confidence=0.5,
        architect_runner=lambda **_values: None,
        excluded_task_ids=(),
    )
    with patch.object(polling_module, "LocalArchitectWakeListener", SpyListener):
        require(orchestrator.start_activity_listener(), "real scheduler listener did not start")
        require(orchestrator.start_activity_listener(), "idempotent start changed result")
        orchestrator.close_activity_listener()
        orchestrator.close_activity_listener()
        require(orchestrator.start_activity_listener(), "new run could not restart listener")
        orchestrator.close_activity_listener()
    require(events == ["start", "close", "start", "close"], f"wrong real lifecycle: {events}")


def test_progress_change_reloops_without_sleeping() -> None:
    pending = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_ready", "implementation"),),
    )
    progressed = replace(
        pending,
        observation_revision=2,
        managed_issues=(managed_issue(TASK, "agent_ready", "delivery_evidence"),),
    )
    fake = FakeScheduler(wait_reasons=("fallback_elapsed", "fallback_elapsed"))
    sequence = SnapshotSequence(pending, pending, progressed, progressed)
    running = controller(state=sequence, scheduler=fake)
    first = running.run(max_steps=1)
    require(first.wait_reason == "fallback_elapsed", "first stalled view did not use fallback")
    second = running.run(max_steps=1)
    require(second.wait_reason is None, "durable progress slept instead of re-looping")
    require(len(fake.wait_calls) == 1, "progress caused an extra wait")

    first_cycle_fake = FakeScheduler()
    first_cycle = controller(
        state=SnapshotSequence(
            pending,
            replace(
                pending,
                observation_revision=3,
                tasks=(TaskObservation(TASK, "needs_testing"),),
            ),
        ),
        scheduler=first_cycle_fake,
    ).run(max_steps=1)
    require(first_cycle.wait_reason is None, "first-cycle durable progress slept")
    require(first_cycle_fake.wait_calls == [], "first-cycle progress used fallback")


def test_deadlock_requires_same_internal_fingerprint_after_fallback() -> None:
    stalled = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_ready", "implementation"),),
    )
    fake = FakeScheduler(wait_reasons=("fallback_elapsed",))
    running = controller(state=stalled, scheduler=fake)
    first = running.run(max_steps=1)
    require(first.evaluation.classification == "actionable", "first observation was not actionable")
    require(first.wait_reason == "fallback_elapsed", "first observation did not cross fallback")
    second = running.run(max_steps=1)
    require(second.evaluation.classification == "deadlock", "second exact observation did not deadlock")
    require(len(fake.wait_calls) == 1, "deadlock used more than one separating fallback")


def test_a_launch_prevents_deadlock_even_before_the_snapshot_changes() -> None:
    stalled = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_ready", "implementation"),),
    )
    fake = FakeScheduler(
        statuses=(("idle", False), ("worker_launched", False)),
        wait_reasons=("fallback_elapsed",),
        launch_counts=(0, 1),
        launch_task=None,
    )
    running = controller(state=stalled, scheduler=fake)
    running.run(max_steps=1)
    result = running.run(max_steps=1)
    require(result.evaluation.classification == "actionable", "launch was misclassified as deadlock")
    require(result.wait_reason is None, "launch did not cause an immediate re-loop")


def test_external_wait_never_becomes_deadlock_from_unchanged_state() -> None:
    waiting = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "human_action_required", "unity_runtime_validation"),),
        reservations=(TASK,),
    )
    fake = FakeScheduler(wait_reasons=("fallback_elapsed",))
    running = controller(state=waiting, scheduler=fake)
    for _ in range(3):
        result = running.run(max_steps=1)
        require(result.evaluation.classification == "temporary_wait", "human wait became deadlock")


def test_synthetic_pump_requires_exact_post_observation_proof() -> None:
    calls: list[str] = []
    event_id = "c" * 64
    evidence_sha256 = "d" * 64

    def pump(observed: CoherentGraphSnapshot) -> SyntheticEvidencePumpResult:
        require(observed.managed_issues[0].last_event_id == "a" * 64, "pump got wrong pre-state")
        calls.append("machine-evidence")
        return SyntheticEvidencePumpResult(TASK, event_id, evidence_sha256)

    fake = FakeScheduler()
    pending = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_ready", "delivery_evidence"),),
    )
    progressed = replace(
        pending,
        observation_revision=2,
        managed_issues=(
            managed_issue(
                TASK,
                "agent_ready",
                "delivery_evidence",
                event_id=event_id,
                evidence_sha256=evidence_sha256,
                state_version=2,
            ),
        ),
    )
    result = controller(
        state=SnapshotSequence(pending, progressed), scheduler=fake, pump=pump
    ).run(max_steps=1)
    require(calls == ["machine-evidence"], "evidence pump was not called once")
    require(not fake.wait_calls, "successful evidence pump did not re-loop immediately")
    require(result.progress.synthetic_pump_calls_total == 1, "pump lifetime count is wrong")
    source = inspect.getsource(graph_run.AutonomousGraphController)
    require("apply_human_result" not in source, "wrapper can fabricate human authority")
    require("pass_and_resume_task" not in source, "wrapper invokes the human PASS helper")
    unproven = controller(
        state=pending, scheduler=FakeScheduler(), pump=pump
    ).run(max_steps=1)
    require(unproven.evaluation.classification == "blocked", "unproven pump result hot-looped")

    escaped_scheduler = FakeScheduler()
    escaped_pump = lambda _state: SyntheticEvidencePumpResult(
        EXCLUDED, event_id, evidence_sha256
    )
    rejects(
        lambda: controller(
            state=pending,
            scheduler=escaped_scheduler,
            pump=escaped_pump,
        ).run(max_steps=1)
    )
    require(escaped_scheduler.poll_calls == 0, "out-of-scope pump reached scheduler")


def test_pump_evidence_is_proven_before_a_poll_appends_a_lease_event() -> None:
    event_id = "c" * 64
    evidence_sha256 = "d" * 64
    pending = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_ready", "delivery_evidence"),),
    )
    pumped = replace(
        pending,
        observation_revision=2,
        managed_issues=(
            managed_issue(
                TASK,
                "agent_ready",
                "delivery_evidence",
                event_id=event_id,
                evidence_sha256=evidence_sha256,
                state_version=2,
            ),
        ),
    )
    leased = replace(
        pumped,
        observation_revision=3,
        managed_issues=(
            managed_issue(
                TASK,
                "agent_working",
                "delivery_evidence",
                event_id="e" * 64,
                state_version=3,
            ),
        ),
        active_assignment_task_ids=(TASK,),
    )
    fake = FakeScheduler(
        statuses=(("worker_launched", False),),
        launch_task=TASK,
    )
    result = controller(
        state=SnapshotSequence(pending, pumped, leased),
        scheduler=fake,
        pump=lambda _state: SyntheticEvidencePumpResult(
            TASK, event_id, evidence_sha256
        ),
    ).run(max_steps=1)
    require(result.evaluation.classification == "temporary_wait", str(result.evaluation))
    require(fake.poll_calls == 1, "verified pump did not continue to the scheduler")
    require(result.progress.worker_launches_total == 1, "lease launch was not counted")
    require(
        result.evaluation.fingerprint
        == evaluate_graph_state(manifest(), leased).fingerprint,
        "post-lease evidence was not the final cycle observation",
    )


def test_scheduler_fatal_remains_blocked_without_fake_lifecycle_rotation() -> None:
    fake = FakeScheduler(
        statuses=(("worker_failed", True),),
        architect_calls=(12,),
    )
    pending = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_ready", "implementation"),),
    )

    result = controller(state=pending, scheduler=fake).run(max_steps=1)
    require(result.evaluation.classification == "blocked", "scheduler fatal did not fail closed")
    require(result.scheduler_fatal, "scheduler fatal was presented as lifecycle retirement")
    require(result.progress.architect_invocations_total == 12, "architect total was lost")


def test_malformed_scheduler_accounting_fails_closed() -> None:
    fake = FakeScheduler()
    fake.architect_calls = [True]
    pending = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_ready", "implementation"),),
    )
    rejects(lambda: controller(state=pending, scheduler=fake).run(max_steps=1))


def test_launch_count_and_memory_resume_are_monotonic_without_live_mutation() -> None:
    store = MemoryProgressStore()
    pending = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_ready", "implementation"),),
    )
    launched = replace(pending, active_assignment_task_ids=(TASK,))
    first_scheduler = FakeScheduler(
        statuses=(("worker_launched", False),),
        launch_task=TASK,
    )
    first = controller(
        state=SnapshotSequence(pending, launched),
        scheduler=first_scheduler,
        store=store,
    ).run(max_steps=1)
    require(first.progress.worker_launches_total == 1, "worker launch was not counted")
    second_scheduler = FakeScheduler(wait_reasons=("worker_returned",))
    second_scheduler.active_assignments[TASK] = object()
    resumed = controller(
        state=launched, scheduler=second_scheduler, store=store
    ).run(max_steps=1)
    require(resumed.progress.worker_launches_total == 1, "resume reset launch total")
    require(resumed.progress.poll_cycles_total == 2, "resume reset poll total")
    require(store.value is resumed.progress, "in-memory store did not persist exact progress")


def test_same_task_relaunch_uses_scheduler_emitted_launch_count() -> None:
    active = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_working", "implementation"),),
        active=(TASK,),
        reservations=(TASK,),
    )
    fake = FakeScheduler(
        statuses=(("worker_launched", False),),
        launch_counts=(1,),
        launch_task=TASK,
    )
    fake.active_assignments[TASK] = object()
    result = controller(state=active, scheduler=fake).run(max_steps=1)
    require(
        result.progress.worker_launches_total == 1,
        "same-key worker return/relaunch was lost from lifetime accounting",
    )
    source = inspect.getsource(graph_run.AutonomousGraphController._poll)
    require("active_before" not in source, "controller still uses active-key set diff")


def test_failed_poll_checkpoints_accounting_once_across_resume() -> None:
    class SpawnThenRaiseScheduler(FakeScheduler):
        def poll_capacity_batch(self) -> SimpleNamespace:
            self.lifecycle_events.append("poll")
            self.poll_calls += 1
            self.architect_invocations_this_poll = 1
            self.worker_launches_this_poll = 1
            self.active_assignments[TASK] = object()
            raise RuntimeError("fixture failure after worker launch")

    pending = snapshot(
        tasks=(TaskObservation(TASK, "not_delivered"),),
        issues=(managed_issue(TASK, "agent_ready", "implementation"),),
    )
    store = MemoryProgressStore()
    failed_scheduler = SpawnThenRaiseScheduler()
    failed_lock = FakeLock()
    error = rejects(
        lambda: controller(
            state=pending,
            scheduler=failed_scheduler,
            store=store,
            lock=failed_lock,
        ).run(max_steps=1),
        RuntimeError,
    )
    require(
        str(error) == "fixture failure after worker launch",
        "poll accounting masked the scheduler failure",
    )
    require(store.value is not None, "failed poll did not persist run progress")
    require(store.value.poll_cycles_total == 1, "failed poll cycle was not counted")
    require(
        store.value.architect_invocations_total == 1,
        "failed poll architect invocation was not counted",
    )
    require(
        store.value.worker_launches_total == 1,
        "worker launched before the failed poll was not counted",
    )
    require(
        failed_scheduler.lifecycle_events == ["start", "poll", "drain", "close"],
        "failed poll did not drain and close under the owned lifecycle",
    )
    require(
        failed_scheduler.drain_calls == [DEFAULT_FALLBACK_SECONDS],
        "failed poll did not use the bounded worker drain",
    )
    require(
        failed_lock.events == ["acquire", "release"],
        "failed poll did not release the singleton scheduler lock",
    )

    receipts = MemoryReceiptStore()
    resumed_scheduler = FakeScheduler()
    resumed = controller(
        state=snapshot(revision=2),
        scheduler=resumed_scheduler,
        store=store,
        receipt_store=receipts,
    ).run(max_steps=1)
    require(resumed.receipt is not None, "resumed completed run did not emit a receipt")
    require(resumed_scheduler.poll_calls == 0, "completed resume ran another scheduler pass")
    counters = dict(resumed.receipt.lifetime_counters)
    require(counters["poll_cycles_total"] == 1, "resume double-counted failed poll")
    require(
        counters["architect_invocations_total"] == 1,
        "resume lost or double-counted failed-poll architect work",
    )
    require(
        counters["worker_launches_total"] == 1,
        "resume lost or double-counted the pre-failure worker launch",
    )


def main() -> int:
    tests = [
        test_manifest_is_exact_and_capacity_is_capped_at_ten,
        test_wrapper_delegates_exactly_one_capacity_pass_without_duplicate_scheduling,
        test_completion_refuses_every_missing_authority_condition,
        test_authorized_descendants_are_required_and_excluded_task_is_not_counted,
        test_fingerprint_is_exact_deterministic_and_ignores_observer_revision,
        test_complete_receipt_is_deterministic_and_only_emitted_after_strict_proof,
        test_first_baseline_requires_exact_tree_or_a_proven_main_fast_forward,
        test_only_one_relevant_proven_d1c_local_ahead_recovery_may_poll,
        test_task_and_issue_enums_and_state_phase_pairs_are_exact,
        test_terminal_conformance_dispositions_fail_closed_before_admission,
        test_dynamic_scope_contains_only_roots_and_authorized_descendants,
        test_worker_and_issue_wakes_reloop_immediately_with_bounded_fallback,
        test_run_owns_listener_before_issue_wait_and_closes_after_completion,
        test_run_closes_listener_when_observation_raises_and_step_owns_no_lifecycle,
        test_fatal_cycle_drains_children_before_listener_and_lock_release,
        test_receipt_is_persisted_atomically_while_run_lock_is_held,
        test_json_receipt_final_creation_is_exclusive_and_never_overwrites,
        test_repository_bound_run_paths_and_immutable_manifest_resume,
        test_existing_receipt_short_circuits_before_scheduler_or_observation,
        test_run_drains_live_out_of_scope_assignment_before_terminating,
        test_real_scheduler_listener_methods_are_idempotent_and_restartable,
        test_progress_change_reloops_without_sleeping,
        test_deadlock_requires_same_internal_fingerprint_after_fallback,
        test_a_launch_prevents_deadlock_even_before_the_snapshot_changes,
        test_external_wait_never_becomes_deadlock_from_unchanged_state,
        test_synthetic_pump_requires_exact_post_observation_proof,
        test_pump_evidence_is_proven_before_a_poll_appends_a_lease_event,
        test_scheduler_fatal_remains_blocked_without_fake_lifecycle_rotation,
        test_malformed_scheduler_accounting_fails_closed,
        test_launch_count_and_memory_resume_are_monotonic_without_live_mutation,
        test_same_task_relaunch_uses_scheduler_emitted_launch_count,
        test_failed_poll_checkpoints_accounting_once_across_resume,
    ]
    for test in tests:
        test()
    print(f"autonomous graph run smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
