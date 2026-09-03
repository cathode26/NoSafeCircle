#!/usr/bin/env python3
"""Polling scheduler, integration occupancy, and exact-launch smoke tests.

Classification: pure/component tests plus temporary Git repository fixtures.
In-memory Issue transitions create durable-state fixtures only; no GitHub,
claim ref, provider, worker, canonical Unity asset, or TaskGraph is mutated.
"""

from __future__ import annotations

import io
import inspect
import json
import subprocess
import sys
import tempfile
from contextlib import ExitStack, redirect_stdout
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.polling_orchestrator as scheduler_module  # noqa: E402
from Pipeline.TaskReviewAgent.architect_preflight import (  # noqa: E402
    ArchitectAdvisory,
    ArchitectAnalysis,
    PredictedChangeSurface,
    evaluate_architect_policy,
)
from Pipeline.TaskReviewAgent.contracts import TaskReviewContractError  # noqa: E402
from Pipeline.TaskReviewAgent.dispatch_plan import (  # noqa: E402
    DispatchPlan,
    TaskcontrolStateObservationError,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowSnapshot,
    IssueWorkflowService,
    MemoryIssueBackend,
    _snapshot,
)
from Pipeline.TaskReviewAgent.execution_routing import (  # noqa: E402
    ExecutionRoutingError,
    load_execution_routing_policy,
)
from Pipeline.TaskReviewAgent.polling_orchestrator import (  # noqa: E402
    ActiveAssignment,
    DEFAULT_POLL_SECONDS,
    DEFAULT_MAX_WORKERS,
    IntegrationObservationError,
    IntegrationReservation,
    JsonEventEmitter,
    PollingOrchestrator,
    SchedulerAlreadyActive,
    SchedulerLock,
    build_decomposition_worker_command,
    build_worker_command,
    observe_durable_integration_reservations,
    read_branch_changed_paths,
    read_working_tree_changed_paths,
    refresh_source_main,
    scheduler_lock_path,
)


TASK_A = "NSC-101"
TASK_B = "NSC-102"
TASK_C = "NSC-103"
CONTRACTS = {
    TASK_A: "a" * 64,
    TASK_B: "b" * 64,
    TASK_C: "c" * 64,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120.0,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def git(root: Path, *args: str, check: bool = True) -> str:
    return run("git", "-C", str(root), *args, cwd=root, check=check).stdout.strip()


def create_source(root: Path) -> tuple[Path, str]:
    source = root / "source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.name", "Polling Fixture")
    git(source, "config", "user.email", "polling-fixture@nosafecircle.invalid")
    (source / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    git(source, "add", "compose.yaml")
    git(source, "commit", "-m", "fixture base")
    return source, git(source, "rev-parse", "HEAD")


def task(task_id: str, *, resources: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "id": task_id,
        "title": f"Polling fixture {task_id}",
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "contract_disposition": "active",
        "exclusive_resources": list(resources),
        "depends_on": [],
        "acceptance_criteria": [],
        "completion_gates": [],
        "task_contract_sha256": CONTRACTS[task_id],
    }


def decomposition_task(task_id: str) -> dict[str, Any]:
    value = task(task_id)
    value.update(
        {
            "parent": "NSC-001",
            "execution_scope": "needs_execution_decomposition",
            "decomposition_state": "atomicity_unknown",
        }
    )
    return value


def _candidate(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "task_contract_sha256": CONTRACTS[task_id],
        "exclusive_resources": [],
    }


def candidate_plan(head: str, task_id: str, *other_task_ids: str) -> DispatchPlan:
    candidates = tuple(_candidate(item) for item in (task_id, *other_task_ids))
    return DispatchPlan(
        schema_version="1.0",
        source_commit=head,
        mode="read_only_plan",
        autonomous_dispatch=False,
        decision="fresh_candidate",
        resume=None,
        selected_fresh_candidate=candidates[0],
        ranked_eligible_candidates=candidates,
        skipped_candidates=(),
        agent_ready_count=0,
        claim_observation={"status": "fixture"},
    )


def mixed_work_plan(
    head: str,
    implementation_task_id: str,
    decomposition_task_id: str,
) -> DispatchPlan:
    implementation = _candidate(implementation_task_id)
    decomposition = {
        **_candidate(decomposition_task_id),
        "eligible": False,
        "reason_codes": [
            "execution_scope_not_single_agent",
            "decomposition_state_not_concrete",
            "derived_state_not_fresh:aggregate",
        ],
    }
    return DispatchPlan(
        schema_version="1.0",
        source_commit=head,
        mode="read_only_plan",
        autonomous_dispatch=False,
        decision="fresh_candidate",
        resume=None,
        selected_fresh_candidate=implementation,
        ranked_eligible_candidates=(implementation,),
        skipped_candidates=(decomposition,),
        agent_ready_count=0,
        claim_observation={"status": "fixture"},
    )


def resume_plan(
    head: str,
    task_id: str,
    *fresh_task_ids: str,
    phase: str = "repair",
) -> DispatchPlan:
    fresh_candidates = tuple(_candidate(item) for item in fresh_task_ids)
    return DispatchPlan(
        schema_version="1.0",
        source_commit=head,
        mode="read_only_plan",
        autonomous_dispatch=False,
        decision="resume_existing",
        resume={
            "task_id": task_id,
            "phase": phase,
            "issue_number": 1,
            "branch": f"{task_id.casefold()}-fixture",
            "commit": head,
        },
        selected_fresh_candidate=(fresh_candidates[0] if fresh_candidates else None),
        ranked_eligible_candidates=fresh_candidates,
        skipped_candidates=(),
        agent_ready_count=1,
        claim_observation={"status": "fixture"},
    )


def terminal_plan(head: str, decision: str) -> DispatchPlan:
    return DispatchPlan(
        schema_version="1.0",
        source_commit=head,
        mode="read_only_plan",
        autonomous_dispatch=False,
        decision=decision,
        resume=None,
        selected_fresh_candidate=None,
        ranked_eligible_candidates=(),
        skipped_candidates=(),
        agent_ready_count=0,
        claim_observation={"status": "fixture"},
        reasons=("fixture blocked",) if decision == "blocked_invalid_state" else (),
    )


class SequencePlanner:
    def __init__(self, plans: list[DispatchPlan]) -> None:
        self.plans = plans
        self.calls: list[set[str]] = []

    def __call__(self, **values: Any) -> DispatchPlan:
        self.calls.append(set(values.get("excluded_task_ids") or ()))
        index = min(len(self.calls) - 1, len(self.plans) - 1)
        return self.plans[index]


class SemanticStage2Planner:
    """One-snapshot fake matching production resume/fresh exclusion semantics."""

    def __init__(self, *, head: str, resume_task_id: str, fresh_rank: tuple[str, ...]) -> None:
        self.head = head
        self.resume_task_id = resume_task_id
        self.fresh_rank = fresh_rank
        self.calls: list[set[str]] = []

    def __call__(self, **values: Any) -> DispatchPlan:
        excluded = set(values.get("excluded_task_ids") or ())
        self.calls.append(excluded)
        # Production Stage 2 ignores exclusions for resume-first selection,
        # while its fresh pool evaluates/ranks normally and then honors them.
        fresh = tuple(item for item in self.fresh_rank if item not in excluded)
        return resume_plan(self.head, self.resume_task_id, *fresh)


class RecordingProductionPlanner:
    def __init__(self) -> None:
        self.calls: list[set[str]] = []
        self.plans: list[DispatchPlan] = []

    def __call__(self, **values: Any) -> DispatchPlan:
        self.calls.append(set(values.get("excluded_task_ids") or ()))
        plan = scheduler_module.build_poll_dispatch_plan(**values)
        self.plans.append(plan)
        return plan


class Stage2WorkflowFixture:
    """Minimal read-only workflow surface consumed by production Stage 2."""

    def __init__(self, *, head: str, resume_task_id: str | None) -> None:
        self.list_agent_ready_calls = 0
        self.agent_ready: list[dict[str, Any]] = []
        if resume_task_id is not None:
            self.agent_ready.append(
                {
                    "issue_number": 101,
                    "issue_url": "https://example.invalid/issues/101",
                    "workflow_state": {
                        "task_id": resume_task_id,
                        "phase": "repair",
                        "branch": f"{resume_task_id.casefold()}-fixture",
                        "head_commit": head,
                        "human_result": None,
                    },
                }
            )

    def list_agent_ready(self) -> list[dict[str, Any]]:
        self.list_agent_ready_calls += 1
        return list(self.agent_ready)

    def find(self, _task_id: str) -> None:
        return None

    def resource_conflicts(
        self, _task: Mapping[str, Any]
    ) -> tuple[list[str], list[str]]:
        return [], []


def patch_taskgraph_observation_failure(
    stack: ExitStack,
    *,
    tasks: Mapping[str, dict[str, Any]],
    workflow: Stage2WorkflowFixture,
) -> dict[str, int]:
    observations = {"count": 0}

    def fail_state_observation(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        observations["count"] += 1
        raise TaskcontrolStateObservationError(
            "temporary fixture TaskGraph observation failure"
        )

    stack.enter_context(
        patch.object(
            scheduler_module,
            "IssueWorkflowService",
            return_value=workflow,
        )
    )
    stack.enter_context(
        patch.object(
            scheduler_module,
            "repo_root",
            side_effect=lambda source: Path(source).resolve(),
        )
    )
    stack.enter_context(
        patch.object(scheduler_module, "GhIssueBackend", return_value=object())
    )
    stack.enter_context(
        patch.object(
            scheduler_module,
            "load_committed_task",
            side_effect=lambda _root, task_id: tasks[task_id],
        )
    )
    stack.enter_context(
        patch.object(
            scheduler_module.dispatch_plan_module,
            "list_committed_task_ids",
            return_value=sorted(tasks),
        )
    )
    stack.enter_context(
        patch.object(
            scheduler_module.dispatch_plan_module,
            "_read_only_claim_observation",
            return_value=({}, None, {"status": "fixture"}, ()),
        )
    )
    stack.enter_context(
        patch.object(
            scheduler_module.dispatch_plan_module,
            "_taskcontrol_states_snapshot",
            side_effect=fail_state_observation,
        )
    )
    return observations


class FakeProcess:
    next_pid = 4100

    def __init__(self, returncode: int | None = None) -> None:
        FakeProcess.next_pid += 1
        self.pid = FakeProcess.next_pid
        self.returncode = returncode
        self.kill_calls = 0
        self.terminate_calls = 0

    def poll(self) -> int | None:
        return self.returncode

    def kill(self) -> None:
        self.kill_calls += 1

    def terminate(self) -> None:
        self.terminate_calls += 1


class ProcessFactory:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []
        self.processes: list[FakeProcess] = []

    def __call__(self, command: Any, **kwargs: Any) -> FakeProcess:
        self.calls.append((tuple(command), dict(kwargs)))
        process = FakeProcess()
        self.processes.append(process)
        return process


class MutableClock:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def advisory(
    task_id: str,
    head: str,
    *,
    risk: str = "low",
    recommendation: str = "start",
    confidence: float = 0.9,
    exact_paths: tuple[str, ...] = ("Assets/NoSafeCircle/UI/PlayerHud.cs",),
    unity_assets: tuple[str, ...] = (),
    escalation_category: str = "none",
    escalation_question: str = "",
    disjointness: tuple[tuple[str, str], ...] = (),
    capability_tier: str = "standard",
    provider_preference: str = "no_preference",
    work_type: str = "implementation",
) -> ArchitectAdvisory:
    return ArchitectAdvisory.from_dict(
        {
            "task_id": task_id,
            "source_head": head,
            "task_contract_sha256": CONTRACTS[task_id],
            "predicted_change_surface": {
                "exact_paths": list(exact_paths),
                "path_patterns": [],
                "unity_serialized_assets": list(unity_assets),
                "symbols_or_components": ["PlayerHud"],
                "shared_systems": ["player HUD"],
            },
            "integration_risk": risk,
            "parallel_recommendation": recommendation,
            "work_type_recommendation": work_type,
            "execution_recommendation": {
                "capability_tier": capability_tier,
                "provider_preference": provider_preference,
                "rationale": "Ordinary gameplay implementation with established patterns.",
            },
            "conflicting_task_ids": [],
            "conflict_reasons": [],
            "escalation": {
                "category": escalation_category,
                "question": escalation_question,
            },
            "unknown_surface_disjointness": [
                {"task_id": other_id, "justification": justification}
                for other_id, justification in disjointness
            ],
            "design_advice": {
                "implementation_summary": "Use the existing health API.",
                "recommended_interfaces": ["Avoid editing the central manager."],
                "sequencing_notes": [],
                "suggested_exclusive_resources": ["logical:player-hud"],
                "suggested_taskgraph_changes": [],
                "suggested_decomposition": [],
            },
            "evidence": [],
            "confidence": confidence,
            "assumptions": [],
        }
    )


class FakeArchitect:
    """Advisory source; a mapped ``Exception`` simulates an unusable answer."""

    def __init__(self, values: Mapping[str, Any]) -> None:
        self.values = dict(values)
        self.calls: list[str] = []

    def __call__(self, **values: Any) -> ArchitectAnalysis:
        if "candidates" in values:
            ids = [item["task"]["id"] for item in values["candidates"]]
            work_types = {
                item["task"]["id"]: set(item["eligible_work_types"])
                for item in values["candidates"]
            }
            usable = [
                task_id
                for task_id in ids
                if task_id in self.values
                and not isinstance(self.values[task_id], Exception)
                and self.values[task_id].work_type_recommendation
                in work_types[task_id]
            ]
            starts = [
                task_id
                for task_id in usable
                if evaluate_architect_policy(self.values[task_id]).decision == "start"
            ]
            if starts:
                task_id = starts[0]
            elif usable:
                task_id = usable[0]
            else:
                task_id = ids[0]
        else:
            task_id = values["task"]["id"]
        self.calls.append(task_id)
        selected = self.values[task_id]
        if isinstance(selected, Exception):
            raise selected
        return ArchitectAnalysis(
            analysis_id=f"analysis-{task_id.casefold()}-{len(self.calls)}",
            advisory=selected,
            artifact_path=Path(f"/fixture/{task_id}.json"),
            active_surface_fingerprint="f" * 64,
            invocation_metadata={"provider": "fake", "model": "fake-model"},
        )


def make_orchestrator(
    *,
    source: Path,
    planner: Any,
    architect: FakeArchitect,
    processes: ProcessFactory,
    tasks: Mapping[str, dict[str, Any]],
    reservations: tuple[IntegrationReservation, ...] = (),
    max_workers: int = 4,
    dry_run: bool = False,
    max_architect_invocations_per_poll: int = 8,
    max_architect_invocations_per_session: int = 20,
    architect_min_reanalysis_seconds: float = 300.0,
    max_consecutive_observation_failures: int = 3,
    fatal_drain_seconds: float = scheduler_module.DEFAULT_FATAL_DRAIN_SECONDS,
    monotonic_clock: Any = None,
    routing_policy: Any = None,
    routing_policy_loader: Any = None,
    excluded_task_ids: tuple[str, ...] = (),
) -> tuple[PollingOrchestrator, io.StringIO]:
    stream = io.StringIO()
    orchestrator = PollingOrchestrator(
        source=source,
        checkout_root=source.parent / "checkouts",
        scheduler_id="polling-smoke-scheduler",
        execution_provider="claude",
        model=None,
        max_turns=120,
        max_workers=max_workers,
        architect_min_confidence=0.65,
        architect_runner=architect,
        routing_policy=routing_policy,
        routing_policy_loader=routing_policy_loader,
        max_architect_invocations_per_poll=max_architect_invocations_per_poll,
        max_architect_invocations_per_session=max_architect_invocations_per_session,
        architect_min_reanalysis_seconds=architect_min_reanalysis_seconds,
        max_consecutive_observation_failures=max_consecutive_observation_failures,
        fatal_drain_seconds=fatal_drain_seconds,
        plan_builder=planner,
        task_loader=lambda task_id: tasks[task_id],
        reservation_observer=lambda: reservations,
        source_refresher=lambda _source: {
            "before": git(source, "rev-parse", "HEAD"),
            "after": git(source, "rev-parse", "HEAD"),
            "changed": False,
        },
        process_factory=processes,
        event_emitter=JsonEventEmitter(stream),
        excluded_task_ids=excluded_task_ids,
        dry_run=dry_run,
        monotonic_clock=monotonic_clock or scheduler_module.time.monotonic,
    )
    return orchestrator, stream


def add_active(
    orchestrator: PollingOrchestrator,
    *,
    task_id: str,
    process: FakeProcess,
    predicted: tuple[str, ...] = ("Assets/Active.cs",),
) -> None:
    orchestrator.active_assignments[task_id] = ActiveAssignment(
        task_id=task_id,
        worker_id=f"active-{task_id.casefold()}",
        process=process,
        checkout_path=orchestrator.checkout_root / task_id,
        exclusive_resources=(),
        architect_surface=PredictedChangeSurface(predicted, (), (), (), ()),
        architect_confidence=0.9,
        advisory_artifact_path=Path(f"/fixture/{task_id}.json"),
        start_time_utc="2026-09-01T00:00:00+00:00",
    )


def test_singleton_second_scheduler_fails_immediately() -> None:
    with tempfile.TemporaryDirectory() as text:
        path = Path(text) / "scheduler.lock"
        first = SchedulerLock(path)
        second = SchedulerLock(path)
        first.acquire()
        try:
            try:
                second.acquire()
            except SchedulerAlreadyActive as exc:
                require(str(exc) == "scheduler_already_active", str(exc))
            else:
                raise AssertionError("second scheduler acquired the OS lock")
        finally:
            first.release()


def test_event_emitter_persists_exact_stdout_journal() -> None:
    with tempfile.TemporaryDirectory() as text:
        journal = Path(text) / "scheduler" / "events.jsonl"
        stream = io.StringIO()
        emitter = JsonEventEmitter(stream, journal_path=journal)
        emitter.emit("fixture_event", task_id=TASK_A, detail="persist me")
        require(journal.is_file(), "scheduler journal was not created")
        require(
            journal.read_text(encoding="utf-8") == stream.getvalue(),
            "scheduler journal differs from emitted stdout event",
        )
        payload = json.loads(stream.getvalue())
        require(payload["event"] == "fixture_event", str(payload))
        require(payload["task_id"] == TASK_A, str(payload))


def test_shared_checkout_root_lock_collides_across_source_clones() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source_a = root / "source-a"
        source_b = root / "source-b"
        checkout_root = root / "shared-checkouts"
        source_a.mkdir()
        source_b.mkdir()
        path_a = scheduler_lock_path(
            source=source_a, checkout_root=checkout_root
        )
        path_b = scheduler_lock_path(
            source=source_b, checkout_root=checkout_root
        )
        require(path_a == path_b, f"lock paths differ: {path_a} != {path_b}")
        require(
            path_a.parent == checkout_root.resolve() / ".task-review-agent/locks",
            str(path_a),
        )
        first = SchedulerLock(path_a)
        second = SchedulerLock(path_b)
        first.acquire()
        try:
            try:
                second.acquire()
            except SchedulerAlreadyActive:
                pass
            else:
                raise AssertionError("different source clones both acquired one root")
        finally:
            first.release()


def test_no_safe_work_launches_nothing() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([terminal_plan(head, "no_safe_work")])
        architect = FakeArchitect({})
        processes = ProcessFactory()
        orchestrator, _stream = make_orchestrator(
            source=source, planner=planner, architect=architect, processes=processes, tasks={}
        )
        result = orchestrator.poll_once()
        require(result.status == "idle", str(result))
        require(not processes.calls and not architect.calls, "idle plan invoked work")


def test_blocked_invalid_state_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([terminal_plan(head, "blocked_invalid_state")])
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=FakeArchitect({}),
            processes=ProcessFactory(),
            tasks={},
        )
        result = orchestrator.poll_once()
        require(result.fatal and result.status == "blocked_invalid_state", str(result))


def test_resume_existing_remains_stage2_priority() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([resume_plan(head, TASK_A)])
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head)})
        processes = ProcessFactory()
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
            architect_min_reanalysis_seconds=0.0,
        )
        result = orchestrator.poll_once()
        require(result.status == "worker_launched" and result.task_id == TASK_A, str(result))
        require(architect.calls == [TASK_A], str(architect.calls))


def test_every_worker_command_has_exact_task_and_unique_worker_id() -> None:
    first = build_worker_command(
        task_id=TASK_A,
        worker_id="worker-one",
        source=Path("/tmp/polling-source"),
        checkout_root=Path("/tmp/polling-checkouts"),
        execution_provider="claude",
        model=None,
        max_turns=120,
    )
    second = build_worker_command(
        task_id=TASK_B,
        worker_id="worker-two",
        source=Path("/tmp/polling-source"),
        checkout_root=Path("/tmp/polling-checkouts"),
        execution_provider="codex",
        model="fixture-model",
        max_turns=80,
    )
    for command, expected_task, expected_worker in (
        (first, TASK_A, "worker-one"),
        (second, TASK_B, "worker-two"),
    ):
        require(command.count("--task-id") == 1, str(command))
        require(command[command.index("--task-id") + 1] == expected_task, str(command))
        require(command.count("--worker-id") == 1, str(command))
        require(command[command.index("--worker-id") + 1] == expected_worker, str(command))
    require("worker-one" != "worker-two", "worker IDs were not unique")


def test_scheduler_has_no_generic_contention_retry_or_taskless_launch() -> None:
    source = Path(scheduler_module.__file__).read_text(encoding="utf-8")
    forbidden_name = "resolve_generic_dispatch" + "_with_contention_retry"
    require(forbidden_name not in source, "scheduler calls the mutating generic dispatcher")
    require('"--task-id"' in source, "scheduler has no explicit task-id launch token")
    require("build_worker_command(" in source, "scheduler bypasses its exact worker builder")


def test_max_workers_blocks_launch() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A)])
        processes = ProcessFactory()
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=FakeArchitect({TASK_A: advisory(TASK_A, head)}),
            processes=processes,
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B)},
            max_workers=1,
        )
        add_active(orchestrator, task_id=TASK_B, process=FakeProcess())
        result = orchestrator.poll_once()
        require(result.status == "capacity_full", str(result))
        require(not processes.calls, "capacity-full poll launched a worker")


def test_at_most_one_new_worker_per_poll() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A, TASK_B)])
        processes = ProcessFactory()
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=FakeArchitect(
                {TASK_A: advisory(TASK_A, head), TASK_B: advisory(TASK_B, head)}
            ),
            processes=processes,
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B)},
        )
        orchestrator.poll_once()
        require(len(processes.calls) == 1, f"poll launched {len(processes.calls)} workers")
        require(len(planner.calls) == 1, f"planner was rebuilt after successful launch")


def test_active_task_ids_feed_stage2_exclusions() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([terminal_plan(head, "no_safe_work")])
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=FakeArchitect({}),
            processes=ProcessFactory(),
            tasks={TASK_A: task(TASK_A)},
            max_workers=2,
        )
        add_active(orchestrator, task_id=TASK_A, process=FakeProcess())
        orchestrator.poll_once()
        require(planner.calls == [{TASK_A}], str(planner.calls))


def test_session_exclusions_feed_every_stage2_poll() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner(
            [
                terminal_plan(head, "no_safe_work"),
                terminal_plan(head, "no_safe_work"),
            ]
        )
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=FakeArchitect({}),
            processes=ProcessFactory(),
            tasks={},
            excluded_task_ids=(TASK_A,),
        )
        require(orchestrator.poll_once().status == "idle", "first poll was not idle")
        require(orchestrator.poll_once().status == "idle", "second poll was not idle")
        require(planner.calls == [{TASK_A}, {TASK_A}], str(planner.calls))
        require(
            f'"excluded_task_ids": ["{TASK_A}"]' in stream.getvalue(),
            stream.getvalue(),
        )


def test_exclude_task_id_cli_is_repeatable_and_validated() -> None:
    args = scheduler_module.build_parser().parse_args(
        ["--exclude-task-id", TASK_A, "--exclude-task-id", TASK_B]
    )
    require(args.exclude_task_id == [TASK_A, TASK_B], str(args.exclude_task_id))
    try:
        PollingOrchestrator(
            source=ROOT,
            checkout_root=ROOT.parent / "checkouts",
            scheduler_id="invalid-exclusion-fixture",
            execution_provider="claude",
            model=None,
            max_turns=1,
            max_workers=1,
            architect_min_confidence=0.65,
            architect_runner=FakeArchitect({}),
            excluded_task_ids=("not-a-task",),
        )
    except TaskReviewContractError:
        pass
    else:
        raise AssertionError("invalid permanent scheduler exclusion was accepted")


def test_architect_portfolio_selects_disjoint_candidate_in_one_call() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A, TASK_B)])
        architect = FakeArchitect(
            {
                TASK_A: advisory(TASK_A, head, risk="medium"),
                TASK_B: advisory(
                    TASK_B,
                    head,
                    exact_paths=("Assets/NoSafeCircle/Gameplay/Disjoint.cs",),
                ),
            }
        )
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B)},
        )
        result = orchestrator.poll_once()
        require(result.status == "worker_launched" and result.task_id == TASK_B, str(result))
        require(planner.calls == [set()], str(planner.calls))
        require(architect.calls == [TASK_B], str(architect.calls))
        require('"portfolio_size": 2' in stream.getvalue(), stream.getvalue())


def test_ineligible_decomposition_pair_is_not_selected_or_launched() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A, TASK_B)])
        architect = FakeArchitect(
            {
                TASK_A: advisory(TASK_A, head, work_type="decomposition"),
                TASK_B: advisory(
                    TASK_B,
                    head,
                    exact_paths=("Assets/NoSafeCircle/Gameplay/Disjoint.cs",),
                ),
            }
        )
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B)},
        )
        result = orchestrator.poll_once()
        require(result.status == "worker_launched" and result.task_id == TASK_B, str(result))
        require(len(processes.calls) == 1, str(processes.calls))
        require(architect.calls == [TASK_B], str(architect.calls))
        require('"work_types": ["implementation"]' in stream.getvalue(), stream.getvalue())


def test_architect_can_choose_decomposition_while_implementation_exists() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([mixed_work_plan(head, TASK_A, TASK_B)])
        architect = FakeArchitect(
            {
                TASK_A: advisory(TASK_A, head, risk="high"),
                TASK_B: advisory(TASK_B, head, work_type="decomposition"),
            }
        )
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A), TASK_B: decomposition_task(TASK_B)},
        )
        result = orchestrator.poll_once()
        require(
            result.status == "worker_launched" and result.task_id == TASK_B,
            str(result),
        )
        require(architect.calls == [TASK_B], str(architect.calls))
        command = processes.calls[0][0]
        require("host_decomposition_launcher.py" in " ".join(command), str(command))
        require("host_worker_launcher.py" not in " ".join(command), str(command))
        require('"work_type": "decomposition"' in stream.getvalue(), stream.getvalue())


def test_excluded_skipped_decomposition_never_enters_architect_portfolio() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        plan = replace(
            mixed_work_plan(head, TASK_A, TASK_B),
            excluded_task_ids=(TASK_B,),
        )
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head)})
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([plan]),
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A), TASK_B: decomposition_task(TASK_B)},
        )
        result = orchestrator.poll_once()
        require(result.status == "worker_launched" and result.task_id == TASK_A, str(result))
        require(architect.calls == [TASK_A], str(architect.calls))
        require(f'"task_id": "{TASK_B}"' not in stream.getvalue(), stream.getvalue())


def test_decomposition_worker_command_binds_exact_task_and_output_policy() -> None:
    command = build_decomposition_worker_command(
        task_id=TASK_B,
        worker_id="decomposition-fixture-worker",
        source=Path("C:/fixture/source"),
        checkout_root=Path("C:/fixture/checkouts"),
        output_root=Path("C:/fixture/outputs/NSC-102"),
    )
    require(command[command.index("--task-id") + 1] == TASK_B, str(command))
    require(
        command[command.index("--worker-id") + 1]
        == "decomposition-fixture-worker",
        str(command),
    )
    require(
        command[command.index("--output-root") + 1].replace("\\", "/")
        == "C:/fixture/outputs/NSC-102",
        str(command),
    )
    require(
        command[command.index("--checkout-root") + 1].replace("\\", "/")
        == "C:/fixture/checkouts",
        str(command),
    )


def test_approved_decomposition_resume_cannot_route_to_implementation() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner(
            [resume_plan(head, TASK_B, phase="decomposition_apply")]
        )
        architect = FakeArchitect(
            {TASK_B: advisory(TASK_B, head, work_type="decomposition")}
        )
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_B: decomposition_task(TASK_B)},
        )
        result = orchestrator.poll_once()
        require(
            result.status == "worker_launched" and result.task_id == TASK_B,
            str(result),
        )
        command = processes.calls[0][0]
        require("host_decomposition_launcher.py" in " ".join(command), str(command))
        require('"work_types": ["decomposition"]' in stream.getvalue(), stream.getvalue())


def test_resume_wait_does_not_starve_stage2_ranked_fresh_work() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SemanticStage2Planner(
            head=head,
            resume_task_id=TASK_A,
            fresh_rank=(TASK_B,),
        )
        architect = FakeArchitect(
            {
                TASK_A: advisory(TASK_A, head, risk="medium"),
                TASK_B: advisory(
                    TASK_B,
                    head,
                    exact_paths=("Assets/NoSafeCircle/Gameplay/Disjoint.cs",),
                ),
            }
        )
        processes = ProcessFactory()
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B)},
        )
        result = orchestrator.poll_once()
        require(
            result.status == "worker_launched" and result.task_id == TASK_B,
            str(result),
        )
        require(planner.calls == [set()], f"Stage 2 ran more than once: {planner.calls}")
        require(architect.calls == [TASK_B], str(architect.calls))


def test_resume_survives_typed_taskgraph_observation_failure() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        tasks = {TASK_A: task(TASK_A), TASK_B: task(TASK_B)}
        workflow = Stage2WorkflowFixture(head=head, resume_task_id=TASK_A)
        planner = RecordingProductionPlanner()
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head)})
        processes = ProcessFactory()
        with ExitStack() as stack:
            observations = patch_taskgraph_observation_failure(
                stack, tasks=tasks, workflow=workflow
            )
            orchestrator, stream = make_orchestrator(
                source=source,
                planner=planner,
                architect=architect,
                processes=processes,
                tasks=tasks,
            )
            result = orchestrator.poll_once()

        require(
            result.status == "worker_launched"
            and result.task_id == TASK_A
            and not result.fatal,
            str(result),
        )
        require(len(planner.plans) == 1, str(planner.plans))
        plan = planner.plans[0]
        require(
            plan.resume
            == {
                "task_id": TASK_A,
                "issue_number": 101,
                "issue_url": "https://example.invalid/issues/101",
                "phase": "repair",
                "branch": f"{TASK_A.casefold()}-fixture",
                "commit": head,
                "human_result": None,
            },
            str(plan.resume),
        )
        require(plan.ranked_eligible_candidates == (), str(plan))
        require(plan.selected_fresh_candidate is None, str(plan))
        require(
            any(
                reason.startswith(scheduler_module.FRESH_POOL_UNAVAILABLE_REASON)
                for reason in plan.reasons
            ),
            str(plan.reasons),
        )
        require(planner.calls == [set()], f"Stage 2 ran more than once: {planner.calls}")
        require(workflow.list_agent_ready_calls == 1, str(workflow.list_agent_ready_calls))
        require(observations["count"] == 1, str(observations))
        require(architect.calls == [TASK_A], str(architect.calls))
        require(len(processes.calls) == 1, str(processes.calls))
        require(
            f'"event": "{scheduler_module.FRESH_POOL_UNAVAILABLE_REASON}"'
            in stream.getvalue(),
            stream.getvalue(),
        )


def test_fresh_only_typed_taskgraph_observation_failure_remains_blocked() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        tasks = {TASK_A: task(TASK_A)}
        workflow = Stage2WorkflowFixture(head=head, resume_task_id=None)
        planner = RecordingProductionPlanner()
        architect = FakeArchitect({})
        processes = ProcessFactory()
        with ExitStack() as stack:
            observations = patch_taskgraph_observation_failure(
                stack, tasks=tasks, workflow=workflow
            )
            orchestrator, stream = make_orchestrator(
                source=source,
                planner=planner,
                architect=architect,
                processes=processes,
                tasks=tasks,
            )
            result = orchestrator.poll_once()

        require(
            result.status == "blocked_invalid_state" and result.fatal,
            str(result),
        )
        require(len(planner.plans) == 1, str(planner.plans))
        require(
            "authoritative TaskGraph state observation failed"
            in " ".join(planner.plans[0].reasons),
            str(planner.plans[0].reasons),
        )
        require(workflow.list_agent_ready_calls == 1, str(workflow.list_agent_ready_calls))
        require(observations["count"] == 1, str(observations))
        require(not architect.calls and not processes.calls, "fresh failure admitted work")
        require('"event": "scheduler_blocked"' in stream.getvalue(), stream.getvalue())


def test_resume_waits_safely_when_fresh_pool_observation_is_unavailable() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        tasks = {TASK_A: task(TASK_A), TASK_B: task(TASK_B)}
        workflow = Stage2WorkflowFixture(head=head, resume_task_id=TASK_A)
        planner = RecordingProductionPlanner()
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head, risk="medium")})
        processes = ProcessFactory()
        with ExitStack() as stack:
            observations = patch_taskgraph_observation_failure(
                stack, tasks=tasks, workflow=workflow
            )
            orchestrator, stream = make_orchestrator(
                source=source,
                planner=planner,
                architect=architect,
                processes=processes,
                tasks=tasks,
            )
            result = orchestrator.poll_once()

        require(result.status == "idle" and not result.fatal, str(result))
        require(len(planner.plans) == 1, str(planner.plans))
        plan = planner.plans[0]
        require(plan.resume is not None and plan.resume["task_id"] == TASK_A, str(plan))
        require(plan.ranked_eligible_candidates == (), str(plan))
        require(plan.selected_fresh_candidate is None, str(plan))
        require(planner.calls == [set()], f"Stage 2 ran more than once: {planner.calls}")
        require(workflow.list_agent_ready_calls == 1, str(workflow.list_agent_ready_calls))
        require(observations["count"] == 1, str(observations))
        require(architect.calls == [TASK_A], str(architect.calls))
        require(not processes.calls, "resume WAIT fabricated or launched fresh work")
        require('"event": "architect_wait"' in stream.getvalue(), stream.getvalue())
        require(TASK_B not in stream.getvalue(), stream.getvalue())


def test_design_escalation_reaches_human_review_and_launches_nothing() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A)])
        architect = FakeArchitect(
            {
                TASK_A: advisory(
                    TASK_A,
                    head,
                    recommendation="human_review",
                    escalation_category="decomposition_required",
                    escalation_question=(
                        "Should the HUD prefab assembly be split from the health "
                        "binding before implementation?"
                    ),
                )
            }
        )
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
        )
        result = orchestrator.poll_once()
        require(result.status == "idle", str(result))
        require(not processes.calls, "human-review candidate launched")
        require('"event": "architect_human_review"' in stream.getvalue(), stream.getvalue())


def test_merge_uncertainty_waits_and_never_asks_a_human() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A)])
        architect = FakeArchitect(
            {
                TASK_A: advisory(
                    TASK_A,
                    head,
                    risk="unknown",
                    recommendation="human_review",
                    confidence=0.2,
                )
            }
        )
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
        )
        result = orchestrator.poll_once()
        events = stream.getvalue()
        require(result.status == "idle", str(result))
        require(not processes.calls, "uncertain candidate launched")
        require('"event": "architect_wait"' in events, events)
        require('"event": "architect_human_review"' not in events, events)


def test_portfolio_architect_can_select_usable_candidate() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A, TASK_B)])
        architect = FakeArchitect(
            {
                TASK_A: RuntimeError("architect container exited 2"),
                TASK_B: advisory(
                    TASK_B,
                    head,
                    exact_paths=("Assets/NoSafeCircle/Gameplay/Disjoint.cs",),
                ),
            }
        )
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B)},
        )
        result = orchestrator.poll_once()
        events = stream.getvalue()
        require(
            result.status == "worker_launched" and result.task_id == TASK_B, str(result)
        )
        require(not result.fatal, "portfolio selection was treated as fatal")
        require(architect.calls == [TASK_B], str(architect.calls))
        require('"portfolio_size": 2' in events, events)
        require(planner.calls == [set()], str(planner.calls))
        require(
            [command[command.index("--task-id") + 1] for command, _ in processes.calls]
            == [TASK_B],
            str(processes.calls),
        )


def unknown_surface_reservation(task_id: str, *, resources: tuple[str, ...]) -> IntegrationReservation:
    return IntegrationReservation(
        task_id=task_id,
        workflow_state="human_action_required",
        phase="unity_runtime_validation",
        branch=f"{task_id.casefold()}-manual",
        head=None,
        checkout_path=None,
        exclusive_resources=resources,
        predicted_paths=(),
        actual_paths=(),
        unity_serialized_assets=(),
        shared_systems=(),
        confidence=0.0,
        evidence_type="durable_incomplete_surface_unknown",
        surface_unknown=True,
    )


def test_unknown_in_flight_surface_waits_before_paying_for_the_architect() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A)])
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head)})
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
            reservations=(unknown_surface_reservation(TASK_B, resources=()),),
        )
        result = orchestrator.poll_once()
        events = stream.getvalue()
        require(result.status == "idle", str(result))
        require(not processes.calls, "unknown in-flight surface allowed a launch")
        require(not architect.calls, "unknown-surface wait still paid for the architect")
        require('"event": "candidate_wait_unknown_surface"' in events, events)


def test_unknown_surface_does_not_deadlock_provably_disjoint_work() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A)])
        architect = FakeArchitect(
            {
                TASK_A: advisory(
                    TASK_A,
                    head,
                    disjointness=(
                        (
                            TASK_B,
                            "NSC-102 owns the Chapel blockout; the HUD binding "
                            "touches no scene geometry.",
                        ),
                    ),
                )
            }
        )
        processes = ProcessFactory()
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A, resources=("logical:player-hud",))},
            reservations=(
                unknown_surface_reservation(
                    TASK_B, resources=("logical:chapel-blockout",)
                ),
            ),
        )
        result = orchestrator.poll_once()
        require(
            result.status == "worker_launched" and result.task_id == TASK_A, str(result)
        )


def test_unjustified_unknown_surface_waits_after_the_architect_answers() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A)])
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head)})
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A, resources=("logical:player-hud",))},
            reservations=(
                unknown_surface_reservation(
                    TASK_B, resources=("logical:chapel-blockout",)
                ),
            ),
        )
        result = orchestrator.poll_once()
        events = stream.getvalue()
        require(result.status == "idle", str(result))
        require(architect.calls == [TASK_A], str(architect.calls))
        require(not processes.calls, "unjustified unknown surface launched a worker")
        require("unobservable integration surface" in events, events)


def test_cached_wait_is_reused_while_every_input_is_unchanged() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner(
            [candidate_plan(head, TASK_A), candidate_plan(head, TASK_A)]
        )
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head, risk="medium")})
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
        )
        require(orchestrator.poll_once().status == "idle", "first poll launched work")
        require(orchestrator.poll_once().status == "idle", "second poll launched work")
        require(architect.calls == [TASK_A], f"cache repaid the architect: {architect.calls}")
        require('"cached": true' in stream.getvalue(), stream.getvalue())
        require(not processes.calls, "cached wait launched a worker")


def test_actual_path_growth_does_not_repurchase_wait_and_new_overlap_blocks() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        first = source / "Synthetic/Active/First.cs"
        first.parent.mkdir(parents=True, exist_ok=True)
        first.write_text("first\n", encoding="utf-8")
        own = IntegrationReservation(
            task_id=TASK_A,
            workflow_state="agent_ready",
            phase="repair",
            branch="nsc-101-scene",
            head="1" * 40,
            checkout_path=None,
            exclusive_resources=(),
            predicted_paths=(),
            actual_paths=("Synthetic/Scenes/X.unity",),
            unity_serialized_assets=("Synthetic/Scenes/X.unity",),
            shared_systems=(),
            confidence=1.0,
            evidence_type="durable_branch_or_checkout_actual_paths",
        )
        planner = SemanticStage2Planner(
            head=head, resume_task_id=TASK_A, fresh_rank=()
        )
        architect = FakeArchitect(
            {
                TASK_A: advisory(
                    TASK_A,
                    head,
                    risk="medium",
                    exact_paths=("Assets/NoSafeCircle/Unrelated.cs",),
                )
            }
        )
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B)},
            reservations=(own,),
            max_workers=2,
        )
        add_active(
            orchestrator,
            task_id=TASK_B,
            process=FakeProcess(),
            predicted=("Synthetic/Active/Predicted.cs",),
        )
        orchestrator.active_assignments[TASK_B].checkout_path = source

        require(orchestrator.poll_once().status == "idle", "first WAIT launched")
        require(architect.calls == [TASK_A], str(architect.calls))

        second = source / "Synthetic/Active/Second.cs"
        second.write_text("second\n", encoding="utf-8")
        require(orchestrator.poll_once().status == "idle", "cached WAIT launched")
        require(
            architect.calls == [TASK_A],
            f"irrelevant actual-path growth repurchased WAIT: {architect.calls}",
        )
        require('"cached": true' in stream.getvalue(), stream.getvalue())

        overlap = source / "Synthetic/Scenes/X.unity"
        overlap.parent.mkdir(parents=True, exist_ok=True)
        overlap.write_text("conflict\n", encoding="utf-8")
        require(orchestrator.poll_once().status == "idle", "overlap launched")
        require(architect.calls == [TASK_A], str(architect.calls))
        require(
            '"conflict_kind": "exact_path_actual"' in stream.getvalue(),
            stream.getvalue(),
        )
        require(not processes.calls, "deterministic overlap launched a worker")


def test_wait_reanalysis_cooldown_survives_unrelated_membership_change() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        clock = MutableClock()
        planner = SequencePlanner(
            [
                candidate_plan(head, TASK_A),
                candidate_plan(head, TASK_A),
                candidate_plan(head, TASK_A),
            ]
        )
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head, risk="medium")})
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=ProcessFactory(),
            tasks={TASK_A: task(TASK_A)},
            monotonic_clock=clock,
        )
        require(orchestrator.poll_once().status == "idle", "first WAIT launched")
        orchestrator.reservation_observer = lambda: (
            IntegrationReservation(
                task_id=TASK_C,
                workflow_state="agent_in_progress",
                phase="implementation",
                branch="nsc-103-unrelated",
                head="3" * 40,
                checkout_path=None,
                exclusive_resources=(),
                predicted_paths=(),
                actual_paths=("Synthetic/Unrelated.cs",),
                unity_serialized_assets=(),
                shared_systems=(),
                confidence=1.0,
                evidence_type="durable_branch_or_checkout_actual_paths",
            ),
        )
        require(orchestrator.poll_once().status == "idle", "cooldown launched")
        require(architect.calls == [TASK_A], str(architect.calls))
        require('"cooldown": true' in stream.getvalue(), stream.getvalue())
        clock.advance(301.0)
        require(orchestrator.poll_once().status == "idle", "reanalyzed WAIT launched")
        require(architect.calls == [TASK_A, TASK_A], str(architect.calls))


def test_wait_is_reconsidered_when_head_or_in_flight_state_changes() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, first_head = create_source(Path(text))
        (source / "README.md").write_text("second commit\n", encoding="utf-8")
        git(source, "add", "README.md")
        git(source, "commit", "-m", "advance head")
        second_head = git(source, "rev-parse", "HEAD")
        require(first_head != second_head, "fixture HEAD did not move")
        planner = SequencePlanner(
            [
                candidate_plan(second_head, TASK_A),
                candidate_plan(second_head, TASK_A),
            ]
        )
        architect = FakeArchitect({TASK_A: advisory(TASK_A, second_head, risk="medium")})
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=ProcessFactory(),
            tasks={TASK_A: task(TASK_A)},
            architect_min_reanalysis_seconds=0.0,
        )
        orchestrator.poll_once()
        require(architect.calls == [TASK_A], str(architect.calls))

        # Same HEAD and same task contract, but a new in-flight reservation
        # changes the integration fingerprint, so the wait is reconsidered.
        orchestrator.reservation_observer = lambda: (
            IntegrationReservation(
                task_id=TASK_C,
                workflow_state="agent_in_progress",
                phase="implementation",
                branch="nsc-103-fixture",
                head=None,
                checkout_path=None,
                exclusive_resources=(),
                predicted_paths=(),
                actual_paths=("Assets/NoSafeCircle/Gameplay/Unrelated.cs",),
                unity_serialized_assets=(),
                shared_systems=(),
                confidence=1.0,
                evidence_type="durable_branch_or_checkout_actual_paths",
            ),
        )
        orchestrator.poll_once()
        require(architect.calls == [TASK_A, TASK_A], str(architect.calls))


def test_mixed_portfolio_uses_one_paid_call_per_poll() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A, TASK_B, TASK_C)])
        architect = FakeArchitect(
            {
                TASK_A: advisory(TASK_A, head, risk="high"),
                TASK_B: advisory(TASK_B, head, risk="high"),
                TASK_C: advisory(TASK_C, head, risk="high"),
            }
        )
        processes = ProcessFactory()
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={
                TASK_A: task(TASK_A),
                TASK_B: task(TASK_B),
                TASK_C: task(TASK_C),
            },
            max_architect_invocations_per_poll=1,
        )
        result = orchestrator.poll_once()
        require(result.status == "idle", str(result))
        require(not result.fatal, "a portfolio WAIT was treated as fatal")
        require(architect.calls == [TASK_A], str(architect.calls))
        require(not processes.calls, "portfolio WAIT launched a worker")


def test_cumulative_architect_session_cap_stops_new_admissions() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner(
            [candidate_plan(head, TASK_A), candidate_plan(head, TASK_B)]
        )
        architect = FakeArchitect(
            {
                TASK_A: advisory(TASK_A, head, risk="high"),
                TASK_B: advisory(TASK_B, head),
            }
        )
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B)},
            max_architect_invocations_per_session=1,
        )
        require(orchestrator.poll_once().status == "idle", "first WAIT launched")
        result = orchestrator.poll_once()
        require(
            result.fatal
            and result.status == "architect_session_budget_exhausted",
            str(result),
        )
        require(architect.calls == [TASK_A], str(architect.calls))
        require(not processes.calls, "session-budget exhaustion launched a worker")
        require(
            "cumulative architect session invocation cap is exhausted"
            in stream.getvalue(),
            stream.getvalue(),
        )


def test_resume_is_not_blocked_by_its_own_durable_reservation() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([resume_plan(head, TASK_A)])
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head)})
        processes = ProcessFactory()
        own = IntegrationReservation(
            task_id=TASK_A,
            workflow_state="agent_in_progress",
            phase="implementation",
            branch="nsc-101-hud",
            head=None,
            checkout_path=None,
            exclusive_resources=("logical:player-hud",),
            predicted_paths=(),
            actual_paths=("Assets/NoSafeCircle/UI/PlayerHud.cs",),
            unity_serialized_assets=(),
            shared_systems=(),
            confidence=1.0,
            evidence_type="durable_branch_or_checkout_actual_paths",
        )
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A, resources=("logical:player-hud",))},
            reservations=(own,),
        )
        result = orchestrator.poll_once()
        require(
            result.status == "worker_launched" and result.task_id == TASK_A, str(result)
        )


def test_resume_waits_when_other_active_work_overlaps() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([resume_plan(head, TASK_A)])
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head)})
        processes = ProcessFactory()
        other = IntegrationReservation(
            task_id=TASK_B,
            workflow_state="agent_in_progress",
            phase="implementation",
            branch="nsc-102-hud",
            head=None,
            checkout_path=None,
            exclusive_resources=(),
            predicted_paths=(),
            actual_paths=("Assets/NoSafeCircle/UI/PlayerHud.cs",),
            unity_serialized_assets=(),
            shared_systems=(),
            confidence=1.0,
            evidence_type="durable_branch_or_checkout_actual_paths",
        )
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
            reservations=(other,),
        )
        result = orchestrator.poll_once()
        require(result.status == "idle", str(result))
        require(not processes.calls, "overlapping resume launched a worker")
        require('"conflict_kind": "exact_path_actual"' in stream.getvalue(), stream.getvalue())


def test_resume_own_actual_unity_path_conflicts_with_other_branch() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source, head = create_source(root)
        checkouts: list[Path] = []
        for task_id in (TASK_A, TASK_B):
            checkout = root / f"checkout-{task_id}"
            run("git", "clone", str(source), str(checkout), cwd=root)
            git(checkout, "config", "user.name", "Polling Fixture")
            git(
                checkout,
                "config",
                "user.email",
                "polling-fixture@nosafecircle.invalid",
            )
            git(checkout, "switch", "-c", f"{task_id.casefold()}-scene")
            scene = checkout / "Synthetic/Scenes/X.unity"
            scene.parent.mkdir(parents=True, exist_ok=True)
            scene.write_text(f"fixture {task_id}\n", encoding="utf-8")
            git(checkout, "add", "Synthetic/Scenes/X.unity")
            git(checkout, "commit", "-m", f"{task_id} scene")
            checkouts.append(checkout)

        own_actual = read_branch_changed_paths(checkouts[0])
        other_actual = read_branch_changed_paths(checkouts[1])
        require(own_actual == ("Synthetic/Scenes/X.unity",), str(own_actual))
        require(other_actual == own_actual, str(other_actual))
        reservations = tuple(
            IntegrationReservation(
                task_id=task_id,
                workflow_state="agent_in_progress",
                phase="implementation",
                branch=f"{task_id.casefold()}-scene",
                head=git(checkout, "rev-parse", "HEAD"),
                checkout_path=str(checkout),
                exclusive_resources=(),
                predicted_paths=(),
                actual_paths=actual,
                unity_serialized_assets=actual,
                shared_systems=(),
                confidence=1.0,
                evidence_type="durable_branch_or_checkout_actual_paths",
            )
            for task_id, checkout, actual in (
                (TASK_A, checkouts[0], own_actual),
                (TASK_B, checkouts[1], other_actual),
            )
        )
        architect = FakeArchitect(
            {
                TASK_A: advisory(
                    TASK_A,
                    head,
                    exact_paths=("Assets/NoSafeCircle/Unrelated.cs",),
                )
            }
        )
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=SemanticStage2Planner(
                head=head, resume_task_id=TASK_A, fresh_rank=()
            ),
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
            reservations=reservations,
        )
        result = orchestrator.poll_once()
        require(result.status == "idle", str(result))
        require(not architect.calls, "actual Git evidence still purchased a model call")
        require(not processes.calls, "conflicting Unity branches launched a worker")
        require("Synthetic/Scenes/X.unity" in stream.getvalue(), stream.getvalue())


def test_wait_mutates_no_durable_taskgraph_issue_or_git_state() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, backend, fixture_task = create_durable_human_fixture(Path(text))
        head_before = git(source, "rev-parse", "HEAD")
        status_before = git(source, "status", "--porcelain")
        issues_before = repr(backend.list_issues())
        plan_head = head_before
        planner = SequencePlanner([candidate_plan(plan_head, TASK_B)])
        architect = FakeArchitect({TASK_B: advisory(TASK_B, plan_head, risk="high")})
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_B: task(TASK_B)},
        )
        result = orchestrator.poll_once()
        require(result.status == "idle", str(result))
        require('"event": "architect_wait"' in stream.getvalue(), stream.getvalue())
        require(not processes.calls, "a wait launched a worker")
        require(git(source, "rev-parse", "HEAD") == head_before, "wait moved HEAD")
        require(git(source, "status", "--porcelain") == status_before, "wait dirtied the tree")
        require(repr(backend.list_issues()) == issues_before, "wait mutated Issue state")
        require(not (source / "Tasks").exists(), "wait created a TaskGraph path")


def test_actual_working_tree_paths_become_reservation_evidence() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        for relative in ("Assets/Tracked.cs", "Assets/Staged.cs"):
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("base\n", encoding="utf-8")
        git(source, "add", "Assets")
        git(source, "commit", "-m", "tracked files")
        (source / "Assets/Tracked.cs").write_text("changed\n", encoding="utf-8")
        (source / "Assets/Staged.cs").write_text("staged\n", encoding="utf-8")
        git(source, "add", "Assets/Staged.cs")
        (source / "Assets/Untracked.cs").write_text("new\n", encoding="utf-8")
        observed = set(read_working_tree_changed_paths(source))
        require(
            observed
            == {"Assets/Tracked.cs", "Assets/Staged.cs", "Assets/Untracked.cs"},
            str(observed),
        )
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([terminal_plan(head, "no_safe_work")]),
            architect=FakeArchitect({}),
            processes=ProcessFactory(),
            tasks={TASK_A: task(TASK_A)},
        )
        assignment = ActiveAssignment(
            task_id=TASK_A,
            worker_id="active-working-tree-fixture",
            process=FakeProcess(),
            checkout_path=source,
            exclusive_resources=(),
            architect_surface=PredictedChangeSurface((), (), (), (), ()),
            architect_confidence=0.9,
            advisory_artifact_path=Path("/fixture/working-tree.json"),
            start_time_utc="2026-09-01T00:00:00+00:00",
        )
        orchestrator.active_assignments[TASK_A] = assignment
        reservations = orchestrator._refresh_active_reservations()
        require(len(reservations) == 1, str(reservations))
        require(set(reservations[0].actual_paths) == observed, str(reservations[0]))
        require(
            reservations[0].evidence_type == "scheduler_prediction_and_actual_git",
            str(reservations[0]),
        )


def test_new_worker_checkout_is_explicitly_pending_with_prediction_preserved() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([terminal_plan(head, "no_safe_work")]),
            architect=FakeArchitect({}),
            processes=ProcessFactory(),
            tasks={TASK_A: task(TASK_A)},
        )
        add_active(
            orchestrator,
            task_id=TASK_A,
            process=FakeProcess(),
            predicted=("Synthetic/Expected.cs",),
        )
        reservation = orchestrator._refresh_active_reservations()[0]
        require(not reservation.surface_unknown, str(reservation))
        require(reservation.actual_paths == (), str(reservation))
        require(
            reservation.predicted_paths == ("Synthetic/Expected.cs",),
            str(reservation),
        )
        require(
            reservation.evidence_type == "scheduler_prediction_checkout_pending",
            str(reservation),
        )
        require(
            '"event": "active_checkout_observation_pending"' in stream.getvalue(),
            stream.getvalue(),
        )


def test_previously_observed_checkout_disappearing_becomes_unknown() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source, head = create_source(root)
        changed = source / "Synthetic/Observed.cs"
        changed.parent.mkdir(parents=True, exist_ok=True)
        changed.write_text("observed\n", encoding="utf-8")
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([terminal_plan(head, "no_safe_work")]),
            architect=FakeArchitect({}),
            processes=ProcessFactory(),
            tasks={TASK_A: task(TASK_A)},
        )
        add_active(orchestrator, task_id=TASK_A, process=FakeProcess())
        assignment = orchestrator.active_assignments[TASK_A]
        assignment.checkout_path = source
        observed = orchestrator._refresh_active_reservations()[0]
        require(assignment.checkout_observed_once, str(assignment))
        require(not observed.surface_unknown, str(observed))
        moved = root / "source-moved"
        source.rename(moved)
        missing = orchestrator._refresh_active_reservations()[0]
        require(missing.surface_unknown, str(missing))
        require("Synthetic/Observed.cs" in missing.actual_paths, str(missing))
        require(
            '"event": "active_checkout_surface_unknown"' in stream.getvalue(),
            stream.getvalue(),
        )


def create_durable_human_fixture(root: Path) -> tuple[Path, MemoryIssueBackend, dict[str, Any]]:
    source, main_head = create_source(root)
    game = source / "Assets/Scenes/Game.unity"
    game.parent.mkdir(parents=True, exist_ok=True)
    git(source, "switch", "-c", "nsc-101-game-scene")
    game.write_text("fixture scene\n", encoding="utf-8")
    git(source, "add", "Assets/Scenes/Game.unity")
    git(source, "commit", "-m", "task branch scene")
    task_head = git(source, "rev-parse", "HEAD")
    fixture_task = task(TASK_A)
    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda _task_id: fixture_task,
        worker_id="durable-fixture-worker",
    )
    service.acquire_agent_lease(
        task=fixture_task,
        source_head=main_head,
        branch="nsc-101-game-scene",
        checkout_path=str(source),
        planned_approach="Change the fixture scene.",
        expected_validation="Inspect the fixture scene.",
        now="2026-09-01T00:00:00Z",
    )
    service.publish_human_handoff(
        task_id=TASK_A,
        branch="nsc-101-game-scene",
        head_commit=task_head,
        checkout_path=str(source),
        implementation_summary="Changed the fixture scene.",
        completed_checks=("Temporary Git fixture committed.",),
        human_steps=("Inspect the fixture.",),
        expected_result="The fixture is visible.",
        now="2026-09-01T00:01:00Z",
    )
    return source, backend, fixture_task


def test_durable_human_action_branch_becomes_reservation() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, backend, fixture_task = create_durable_human_fixture(Path(text))
        reservations = observe_durable_integration_reservations(
            source=source,
            checkout_root=source.parent,
            worker_id="read-only-observer",
            backend=backend,
            task_loader=lambda _task_id: fixture_task,
        )
        require(len(reservations) == 1, str(reservations))
        reservation = reservations[0]
        require(reservation.workflow_state == "human_action_required", str(reservation))
        require("Assets/Scenes/Game.unity" in reservation.actual_paths, str(reservation))
        require(not reservation.surface_unknown, str(reservation))


def test_actual_branch_path_overlap_prevents_launch() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        reservation = IntegrationReservation(
            task_id=TASK_B,
            workflow_state="human_action_required",
            phase="unity_runtime_validation",
            branch="nsc-102-hud",
            head="2" * 40,
            checkout_path=str(source.parent / TASK_B),
            exclusive_resources=(),
            predicted_paths=(),
            actual_paths=("Assets/NoSafeCircle/UI/PlayerHud.cs",),
            unity_serialized_assets=(),
            shared_systems=(),
            confidence=1.0,
            evidence_type="durable_branch_actual",
        )
        planner = SequencePlanner([candidate_plan(head, TASK_A)])
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=FakeArchitect({TASK_A: advisory(TASK_A, head)}),
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
            reservations=(reservation,),
        )
        result = orchestrator.poll_once()
        require(result.status == "idle", str(result))
        require(not processes.calls, "actual branch overlap launched a worker")
        require('"conflict_kind": "exact_path_actual"' in stream.getvalue(), stream.getvalue())


def test_successful_child_exit_frees_local_capacity() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([terminal_plan(head, "no_safe_work")]),
            architect=FakeArchitect({}),
            processes=ProcessFactory(),
            tasks={TASK_A: task(TASK_A)},
        )
        add_active(orchestrator, task_id=TASK_A, process=FakeProcess(returncode=0))
        result = orchestrator.poll_once()
        require(result.status == "idle", str(result))
        require(not orchestrator.active_assignments, "successful child kept capacity")
        require('"event": "worker_finished"' in stream.getvalue(), stream.getvalue())


def test_nonzero_child_exit_stops_new_admissions() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_B)])
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=FakeArchitect({TASK_B: advisory(TASK_B, head)}),
            processes=processes,
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B)},
        )
        add_active(orchestrator, task_id=TASK_A, process=FakeProcess(returncode=7))
        result = orchestrator.poll_once()
        require(result.fatal and result.status == "worker_failed", str(result))
        require(not planner.calls and not processes.calls, "failed child allowed admission")
        require('"event": "worker_failed"' in stream.getvalue(), stream.getvalue())


def test_fatal_child_exit_drains_other_workers_before_scheduler_stops() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source, head = create_source(root)
        planner = SequencePlanner([candidate_plan(head, TASK_C)])
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=FakeArchitect({TASK_C: advisory(TASK_C, head)}),
            processes=ProcessFactory(),
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B), TASK_C: task(TASK_C)},
        )
        failed = FakeProcess(returncode=7)

        class FinishesDuringDrain(FakeProcess):
            def __init__(self) -> None:
                super().__init__()
                self.polls = 0

            def poll(self) -> int | None:
                self.polls += 1
                return None if self.polls == 1 else 0

        survivor = FinishesDuringDrain()
        add_active(orchestrator, task_id=TASK_A, process=failed)
        add_active(orchestrator, task_id=TASK_B, process=survivor)

        with patch.object(scheduler_module.time, "sleep", return_value=None):
            exit_code = orchestrator.run(
                lock=SchedulerLock(root / "drain.lock"),
                poll_seconds=0.01,
                once=False,
            )

        require(exit_code == 2, f"failed child returned {exit_code}")
        require(not planner.calls, "fatal child exit allowed a new admission")
        require(not orchestrator.active_assignments, "surviving worker was not drained")
        require(
            survivor.kill_calls == 0 and survivor.terminate_calls == 0,
            "drain killed the surviving worker",
        )
        events = stream.getvalue()
        require('"event": "scheduler_draining"' in events, events)
        require('"event": "worker_finished"' in events, events)
        require('"active_children": []' in events, events)
        draining = next(
            item
            for item in map(json.loads, events.splitlines())
            if item["event"] == "scheduler_draining"
        )
        require(
            [item["task_id"] for item in draining["active_children"]] == [TASK_B],
            str(draining),
        )


def test_ctrl_c_during_fatal_drain_preserves_failure_exit() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source, head = create_source(root)
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([candidate_plan(head, TASK_C)]),
            architect=FakeArchitect({TASK_C: advisory(TASK_C, head)}),
            processes=ProcessFactory(),
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B), TASK_C: task(TASK_C)},
        )
        add_active(orchestrator, task_id=TASK_A, process=FakeProcess(returncode=7))
        survivor = FakeProcess()
        add_active(orchestrator, task_id=TASK_B, process=survivor)

        with patch.object(
            scheduler_module.time,
            "sleep",
            side_effect=KeyboardInterrupt(),
        ):
            exit_code = orchestrator.run(
                lock=SchedulerLock(root / "drain-interrupt.lock"),
                poll_seconds=0.01,
                once=False,
            )

        require(exit_code == 2, f"Ctrl+C masked fatal exit as {exit_code}")
        require(TASK_B in orchestrator.active_assignments, "interrupt lost live child")
        stopped = [
            item
            for item in map(json.loads, stream.getvalue().splitlines())
            if item["event"] == "scheduler_stopped"
        ][-1]
        require(stopped["reason"] == "worker_failed_drain_interrupted", str(stopped))


def test_fatal_drain_timeout_is_bounded_and_preserves_child() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source, head = create_source(root)
        clock = MutableClock()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([candidate_plan(head, TASK_C)]),
            architect=FakeArchitect({TASK_C: advisory(TASK_C, head)}),
            processes=ProcessFactory(),
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B), TASK_C: task(TASK_C)},
            fatal_drain_seconds=0.05,
            monotonic_clock=clock,
        )
        add_active(orchestrator, task_id=TASK_A, process=FakeProcess(returncode=7))
        survivor = FakeProcess()
        add_active(orchestrator, task_id=TASK_B, process=survivor)

        def advance(seconds: float) -> None:
            clock.advance(seconds)

        with patch.object(scheduler_module.time, "sleep", side_effect=advance):
            exit_code = orchestrator.run(
                lock=SchedulerLock(root / "drain-timeout.lock"),
                poll_seconds=0.05,
                once=False,
            )

        require(exit_code == 2, f"drain timeout returned {exit_code}")
        require(TASK_B in orchestrator.active_assignments, "timeout lost live child")
        require('"event": "scheduler_drain_timeout"' in stream.getvalue(), stream.getvalue())
        require("worker_failed_drain_timeout" in stream.getvalue(), stream.getvalue())


def test_poll_exception_keeps_worker_supervised_until_observable() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source, head = create_source(root)
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([candidate_plan(head, TASK_B)]),
            architect=FakeArchitect({TASK_B: advisory(TASK_B, head)}),
            processes=ProcessFactory(),
            tasks={TASK_A: task(TASK_A), TASK_B: task(TASK_B)},
        )

        class PollRaisesOnce(FakeProcess):
            def __init__(self) -> None:
                super().__init__()
                self.polls = 0

            def poll(self) -> int | None:
                self.polls += 1
                if self.polls == 1:
                    raise OSError("temporary process observation failure")
                return 0

        child = PollRaisesOnce()
        add_active(orchestrator, task_id=TASK_A, process=child)
        with patch.object(scheduler_module.time, "sleep", return_value=None):
            exit_code = orchestrator.run(
                lock=SchedulerLock(root / "poll-error.lock"),
                poll_seconds=0.01,
                once=False,
            )
        require(exit_code == 2, f"poll failure returned {exit_code}")
        require(not orchestrator.active_assignments, "recovered child was not reaped")
        require('"event": "worker_poll_failed"' in stream.getvalue(), stream.getvalue())
        require('"event": "worker_finished"' in stream.getvalue(), stream.getvalue())


def test_one_transient_reservation_observation_failure_then_recovers() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A)])
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head)})
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
        )
        observations = 0

        def observe() -> tuple[IntegrationReservation, ...]:
            nonlocal observations
            observations += 1
            if observations == 1:
                raise IntegrationObservationError("temporary fixture read failure")
            return ()

        orchestrator.reservation_observer = observe
        first = orchestrator.poll_once()
        require(
            first.status == "reservation_observation_wait" and not first.fatal,
            str(first),
        )
        require(not planner.calls and not architect.calls and not processes.calls, "failed observation admitted work")
        second = orchestrator.poll_once()
        require(
            second.status == "worker_launched" and second.task_id == TASK_A,
            str(second),
        )
        require('"event": "scheduler_wait_observation_failure"' in stream.getvalue(), stream.getvalue())
        require('"event": "scheduler_observation_recovered"' in stream.getvalue(), stream.getvalue())


def test_reservation_observation_failure_threshold_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        planner = SequencePlanner([candidate_plan(head, TASK_A)])
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head)})
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=planner,
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
        )

        def observe() -> tuple[IntegrationReservation, ...]:
            raise IntegrationObservationError("persistent fixture read failure")

        orchestrator.reservation_observer = observe
        results = [
            orchestrator.poll_once()
            for _ in range(scheduler_module.DEFAULT_MAX_CONSECUTIVE_OBSERVATION_FAILURES)
        ]
        require(
            all(
                result.status == "reservation_observation_wait" and not result.fatal
                for result in results[:-1]
            ),
            str(results),
        )
        require(
            results[-1].status == "reservation_observation_failed"
            and results[-1].fatal,
            str(results[-1]),
        )
        require(not planner.calls and not architect.calls and not processes.calls, "failed observation admitted work")
        events = stream.getvalue()
        require(
            "integration reservation observation failed at the bounded consecutive-failure limit"
            in events,
            events,
        )
        require(
            f'"consecutive_observation_failures": {scheduler_module.DEFAULT_MAX_CONSECUTIVE_OBSERVATION_FAILURES}'
            in events,
            events,
        )


def test_dry_run_never_invokes_models_or_workers() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        architect = FakeArchitect({TASK_A: advisory(TASK_A, head)})
        processes = ProcessFactory()
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([candidate_plan(head, TASK_A)]),
            architect=architect,
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
            dry_run=True,
        )
        result = orchestrator.poll_once()
        require(result.status == "dry_run_candidate", str(result))
        require(not architect.calls and not processes.calls, "dry-run invoked model/worker")


def test_worker_popen_uses_host_controller_boundary_and_shell_false() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        processes = ProcessFactory()
        orchestrator, _stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([candidate_plan(head, TASK_A)]),
            architect=FakeArchitect({TASK_A: advisory(TASK_A, head)}),
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
        )
        orchestrator.poll_once()
        command, kwargs = processes.calls[0]
        require(isinstance(command, tuple), f"worker command was not argv: {command!r}")
        require(kwargs.get("shell") is False, str(kwargs))
        if scheduler_module.os.name == "nt":
            require(
                kwargs.get("creationflags") == subprocess.CREATE_NEW_PROCESS_GROUP,
                str(kwargs),
            )
        else:
            require(kwargs.get("start_new_session") is True, str(kwargs))
        require(command[0] == sys.executable, str(command))
        require(command[1] == "-u", str(command))
        require(Path(command[2]).name == "host_worker_launcher.py", str(command))
        require("docker" not in command, str(command))
        require("claude-exec" not in command and "codex-exec" not in command, str(command))
        require(command[command.index("--task-id") + 1] == TASK_A, str(command))
        require(
            command[command.index("--source") + 1] == str(source.resolve()),
            str(command),
        )
        require(
            command[command.index("--checkout-root") + 1]
            == str(orchestrator.checkout_root.resolve()),
            str(command),
        )


def test_worker_launch_records_and_carries_exact_resolved_route() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        environment = {
            "NSC_ROUTE_DEEP_DEFAULT_PROVIDER": "claude",
            "NSC_ROUTE_DEEP_ALLOWED_PROVIDERS": "openai,claude",
            "NSC_ROUTE_DEEP_CLAUDE_MODEL": "claude-deep-route",
            "NSC_ROUTE_DEEP_OPENAI_MODEL": "openai-deep-route",
            "NSC_ROUTE_DEEP_OPENAI_REASONING_EFFORT": "xhigh",
            "NSC_ROUTE_DEEP_SUPERVISOR_MODEL": "supervisor-deep-route",
            "NSC_ROUTE_DEEP_SUPERVISOR_REASONING_EFFORT": "xhigh",
            "NSC_ROUTE_DEEP_MAX_TURNS": "120",
        }
        processes = ProcessFactory()
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([candidate_plan(head, TASK_A)]),
            architect=FakeArchitect(
                {
                    TASK_A: advisory(
                        TASK_A,
                        head,
                        capability_tier="deep",
                        provider_preference="openai",
                    )
                }
            ),
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
            routing_policy=load_execution_routing_policy(environment),
        )
        result = orchestrator.poll_once()
        require(result.status == "worker_launched", str(result))
        command = processes.calls[0][0]
        exact_argv = {
            "--execution-provider": "codex",
            "--execution-model": "openai-deep-route",
            "--execution-reasoning-effort": "xhigh",
            "--model": "supervisor-deep-route",
            "--supervisor-reasoning-effort": "xhigh",
            "--max-turns": "120",
        }
        for option, expected in exact_argv.items():
            require(command[command.index(option) + 1] == expected, str(command))
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        launched = next(item for item in events if item["event"] == "worker_launched")
        expected_event = {
            "task_id": TASK_A,
            "capability_tier": "deep",
            "provider_preference": "openai",
            "preference_honored": True,
            "execution_provider": "codex",
            "execution_model": "openai-deep-route",
            "execution_reasoning_effort": "xhigh",
            "supervisor_model": "supervisor-deep-route",
            "supervisor_reasoning_effort": "xhigh",
            "max_turns": 120,
        }
        for field, expected in expected_event.items():
            require(launched.get(field) == expected, str(launched))


def test_malformed_routing_policy_launches_nothing() -> None:
    with tempfile.TemporaryDirectory() as text:
        source, head = create_source(Path(text))
        processes = ProcessFactory()

        def malformed_policy() -> Any:
            raise ExecutionRoutingError("fixture malformed routing configuration")

        orchestrator, stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([candidate_plan(head, TASK_A)]),
            architect=FakeArchitect({TASK_A: advisory(TASK_A, head)}),
            processes=processes,
            tasks={TASK_A: task(TASK_A)},
            routing_policy_loader=malformed_policy,
        )
        result = orchestrator.poll_once()
        require(result.status == "idle", str(result))
        require(not processes.calls, "malformed routing policy launched a worker")
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        blocked = [item for item in events if item["event"] == "execution_route_wait"]
        require(len(blocked) == 1 and blocked[0]["task_id"] == TASK_A, str(events))
        require("fixture malformed" in blocked[0]["error"], str(blocked[0]))


def test_ctrl_c_does_not_kill_children_or_release_leases() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source, head = create_source(root)
        orchestrator, stream = make_orchestrator(
            source=source,
            planner=SequencePlanner([terminal_plan(head, "no_safe_work")]),
            architect=FakeArchitect({}),
            processes=ProcessFactory(),
            tasks={TASK_A: task(TASK_A)},
            max_workers=1,
        )
        child = FakeProcess()
        add_active(orchestrator, task_id=TASK_A, process=child)
        original_sleep = scheduler_module.time.sleep

        def interrupt(_seconds: float) -> None:
            raise KeyboardInterrupt()

        scheduler_module.time.sleep = interrupt
        try:
            exit_code = orchestrator.run(
                lock=SchedulerLock(root / "ctrl-c.lock"),
                poll_seconds=0.01,
                once=False,
            )
        finally:
            scheduler_module.time.sleep = original_sleep
        require(exit_code == 0, f"Ctrl+C returned {exit_code}")
        require(child.kill_calls == 0 and child.terminate_calls == 0, "child was killed")
        require(TASK_A in orchestrator.active_assignments, "local child record was mutated")
        require("released no durable lease" in stream.getvalue(), stream.getvalue())
        require("operating-system child survival is not guaranteed" in stream.getvalue(), stream.getvalue())


def test_scheduler_source_has_no_issue_or_claim_mutation_calls() -> None:
    source = Path(scheduler_module.__file__).read_text(encoding="utf-8")
    forbidden = (
        ".acquire_agent_lease(",
        ".create_issue(",
        ".update_issue(",
        ".add_comment(",
        "GitRefClaimClient(",
    )
    for token in forbidden:
        require(token not in source, f"scheduler contains mutation call {token}")
    require("_snapshot" in source, "durable enumeration did not reuse workflow parsing")


def test_main_handles_bare_task_review_contract_error() -> None:
    stream = io.StringIO()
    with patch.object(
        scheduler_module,
        "repo_root",
        side_effect=TaskReviewContractError("fixture bare contract failure"),
    ):
        with redirect_stdout(stream):
            exit_code = scheduler_module.main(["--once", "--source", "."])
    events = stream.getvalue()
    require(exit_code == 2, f"bare contract error returned {exit_code}")
    require('"event": "scheduler_blocked"' in events, events)
    require('"error_type": "TaskReviewContractError"' in events, events)
    require("scheduler initialization failed" in events, events)


def test_private_snapshot_coupling_signature_and_fields_are_pinned() -> None:
    signature = inspect.signature(_snapshot)
    require(tuple(signature.parameters) == ("backend", "issue"), str(signature))
    require(callable(_snapshot), "issue_workflow_store._snapshot is not callable")
    fields = set(IssueWorkflowSnapshot.__dataclass_fields__)
    required_fields = {
        "issue_number",
        "state",
        "managed",
        "valid",
        "reasons",
    }
    require(required_fields <= fields, f"snapshot fields changed: {sorted(fields)}")


def test_default_max_workers_is_one_until_live_acceptance() -> None:
    require(DEFAULT_MAX_WORKERS == 1, f"default max workers is {DEFAULT_MAX_WORKERS}")
    require(DEFAULT_POLL_SECONDS == 60.0, f"default poll is {DEFAULT_POLL_SECONDS}")


def test_source_refresh_fast_forwards_exact_remote_main_without_rewrite() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source, before = create_source(root)
        remote = root / "remote.git"
        git(root, "init", "--bare", str(remote))
        git(source, "remote", "add", "origin", str(remote))
        git(source, "push", "-u", "origin", "main")

        updater = root / "updater"
        git(root, "clone", "--branch", "main", str(remote), str(updater))
        git(updater, "config", "user.name", "Polling Fixture")
        git(updater, "config", "user.email", "polling-fixture@nosafecircle.invalid")
        (updater / "remote.txt").write_text("remote advance\n", encoding="utf-8")
        git(updater, "add", "remote.txt")
        git(updater, "commit", "-m", "remote advance")
        git(updater, "push", "origin", "main")
        remote_head = git(updater, "rev-parse", "HEAD")

        result = refresh_source_main(source)
        require(result == {"before": before, "after": remote_head, "changed": True}, str(result))
        require(git(source, "rev-parse", "HEAD") == remote_head, "source did not fast-forward")
        require(git(source, "status", "--porcelain") == "", "refresh dirtied source")


def test_source_refresh_refuses_dirty_controller_without_overwrite() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source, head = create_source(root)
        remote = root / "remote.git"
        git(root, "init", "--bare", str(remote))
        git(source, "remote", "add", "origin", str(remote))
        git(source, "push", "-u", "origin", "main")
        (source / "local.txt").write_text("preserve me\n", encoding="utf-8")
        try:
            refresh_source_main(source)
        except IntegrationObservationError as exc:
            require("not completely clean" in str(exc), str(exc))
        else:
            raise AssertionError("dirty controller was refreshed")
        require(git(source, "rev-parse", "HEAD") == head, "dirty source HEAD changed")
        require((source / "local.txt").read_text(encoding="utf-8") == "preserve me\n", "dirty file changed")


def main() -> int:
    tests = (
        test_singleton_second_scheduler_fails_immediately,
        test_event_emitter_persists_exact_stdout_journal,
        test_shared_checkout_root_lock_collides_across_source_clones,
        test_no_safe_work_launches_nothing,
        test_blocked_invalid_state_fails_closed,
        test_resume_existing_remains_stage2_priority,
        test_every_worker_command_has_exact_task_and_unique_worker_id,
        test_scheduler_has_no_generic_contention_retry_or_taskless_launch,
        test_max_workers_blocks_launch,
        test_at_most_one_new_worker_per_poll,
        test_active_task_ids_feed_stage2_exclusions,
        test_session_exclusions_feed_every_stage2_poll,
        test_exclude_task_id_cli_is_repeatable_and_validated,
        test_architect_portfolio_selects_disjoint_candidate_in_one_call,
        test_ineligible_decomposition_pair_is_not_selected_or_launched,
        test_architect_can_choose_decomposition_while_implementation_exists,
        test_excluded_skipped_decomposition_never_enters_architect_portfolio,
        test_decomposition_worker_command_binds_exact_task_and_output_policy,
        test_approved_decomposition_resume_cannot_route_to_implementation,
        test_resume_wait_does_not_starve_stage2_ranked_fresh_work,
        test_resume_survives_typed_taskgraph_observation_failure,
        test_fresh_only_typed_taskgraph_observation_failure_remains_blocked,
        test_resume_waits_safely_when_fresh_pool_observation_is_unavailable,
        test_design_escalation_reaches_human_review_and_launches_nothing,
        test_merge_uncertainty_waits_and_never_asks_a_human,
        test_portfolio_architect_can_select_usable_candidate,
        test_unknown_in_flight_surface_waits_before_paying_for_the_architect,
        test_unknown_surface_does_not_deadlock_provably_disjoint_work,
        test_unjustified_unknown_surface_waits_after_the_architect_answers,
        test_cached_wait_is_reused_while_every_input_is_unchanged,
        test_actual_path_growth_does_not_repurchase_wait_and_new_overlap_blocks,
        test_wait_reanalysis_cooldown_survives_unrelated_membership_change,
        test_wait_is_reconsidered_when_head_or_in_flight_state_changes,
        test_mixed_portfolio_uses_one_paid_call_per_poll,
        test_cumulative_architect_session_cap_stops_new_admissions,
        test_resume_is_not_blocked_by_its_own_durable_reservation,
        test_resume_waits_when_other_active_work_overlaps,
        test_resume_own_actual_unity_path_conflicts_with_other_branch,
        test_wait_mutates_no_durable_taskgraph_issue_or_git_state,
        test_actual_working_tree_paths_become_reservation_evidence,
        test_new_worker_checkout_is_explicitly_pending_with_prediction_preserved,
        test_previously_observed_checkout_disappearing_becomes_unknown,
        test_durable_human_action_branch_becomes_reservation,
        test_actual_branch_path_overlap_prevents_launch,
        test_successful_child_exit_frees_local_capacity,
        test_nonzero_child_exit_stops_new_admissions,
        test_fatal_child_exit_drains_other_workers_before_scheduler_stops,
        test_ctrl_c_during_fatal_drain_preserves_failure_exit,
        test_fatal_drain_timeout_is_bounded_and_preserves_child,
        test_poll_exception_keeps_worker_supervised_until_observable,
        test_one_transient_reservation_observation_failure_then_recovers,
        test_reservation_observation_failure_threshold_fails_closed,
        test_dry_run_never_invokes_models_or_workers,
        test_worker_popen_uses_host_controller_boundary_and_shell_false,
        test_worker_launch_records_and_carries_exact_resolved_route,
        test_malformed_routing_policy_launches_nothing,
        test_ctrl_c_does_not_kill_children_or_release_leases,
        test_scheduler_source_has_no_issue_or_claim_mutation_calls,
        test_main_handles_bare_task_review_contract_error,
        test_private_snapshot_coupling_signature_and_fields_are_pinned,
        test_default_max_workers_is_one_until_live_acceptance,
        test_source_refresh_fast_forwards_exact_remote_main_without_rewrite,
        test_source_refresh_refuses_dirty_controller_without_overwrite,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Polling orchestrator tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
