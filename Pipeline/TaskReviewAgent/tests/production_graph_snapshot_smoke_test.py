#!/usr/bin/env python3
"""Deterministic production coherent-snapshot adapter regressions.

Classification: pure/component tests. These are regression-only orchestration
checks. Git, TaskGraph, Issue, and scheduler boundaries are injected except for
one in-memory IssueWorkflowStore scan; no GitHub, provider, Docker, Unity asset,
canonical checkout, or repository state is mutated.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.production_graph_snapshot as snapshot_module  # noqa: E402
from Pipeline.TaskReviewAgent.autonomous_graph_run import (  # noqa: E402
    AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
    AutonomousRunManifest,
    AutonomousRuntimeConfiguration,
)
from Pipeline.TaskReviewAgent.dispatch_plan import PlanScopedIssueBackend  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)
from Pipeline.TaskReviewAgent.polling_orchestrator import (  # noqa: E402
    DurableWorkflowObservation,
    IntegrationReservation,
    observe_durable_workflows,
)
from Pipeline.TaskReviewAgent.production_graph_snapshot import (  # noqa: E402
    ProductionCoherentSnapshotter,
    ProductionGraphSnapshotError,
)


HEAD = "1" * 40
TREE = "2" * 40
NEW_HEAD = "3" * 40
NEW_TREE = "4" * 40
PARENT = "NSC-901"
CHILD = "NSC-902"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action: Any, text: str) -> None:
    try:
        action()
    except ProductionGraphSnapshotError as exc:
        require(text in str(exc), f"unexpected error: {exc}")
    else:
        raise AssertionError(f"expected ProductionGraphSnapshotError containing {text!r}")


def manifest() -> AutonomousRunManifest:
    return AutonomousRunManifest(
        schema_version=AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
        run_id="coherent-snapshot-test",
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
        target_task_ids=(PARENT,),
        excluded_task_ids=(),
        max_capacity=10,
    )


def identity(
    *,
    head: str = HEAD,
    tree: str = TREE,
    origin: str = HEAD,
) -> snapshot_module._SourceIdentity:
    return snapshot_module._SourceIdentity(
        branch="main",
        attached=True,
        clean=True,
        head=head,
        tree=tree,
        origin_main_head=origin,
    )


def test_source_identity_is_captured_with_two_coherent_git_processes() -> None:
    calls: list[tuple[str, ...]] = []
    results = iter(
        (
            subprocess.CompletedProcess(
                args=(),
                returncode=0,
                stdout=f"{HEAD}\n{TREE}\n{HEAD}\n".encode("utf-8"),
                stderr=b"",
            ),
            subprocess.CompletedProcess(
                args=(),
                returncode=0,
                stdout=b"## main...origin/main\n",
                stderr=b"",
            ),
        )
    )

    def run_git(_root: Path, *args: str):
        calls.append(args)
        return next(results)

    with patch.object(snapshot_module, "_run_git", side_effect=run_git):
        observed = snapshot_module._capture_source_identity(ROOT)

    require(observed == identity(), f"coherent source identity changed: {observed}")
    require(
        calls
        == [
            ("rev-parse", "HEAD^{commit}", "HEAD^{tree}", "origin/main^{commit}"),
            ("status", "--porcelain=v1", "--branch", "--untracked-files=all"),
        ],
        f"source identity was not captured in two Git calls: {calls}",
    )


def reservation(task_id: str) -> IntegrationReservation:
    return IntegrationReservation(
        task_id=task_id,
        workflow_state="agent_working",
        phase="implementation",
        branch=f"{task_id.lower()}-fixture",
        head=None,
        checkout_path=str(ROOT.parent / task_id),
        exclusive_resources=(f"synthetic:{task_id}",),
        predicted_paths=(),
        actual_paths=(),
        unity_serialized_assets=(),
        shared_systems=(),
        confidence=0.0,
        evidence_type="durable_incomplete_surface_unknown",
        surface_unknown=True,
    )


class Scheduler:
    def __init__(self, active: tuple[str, ...] = ()) -> None:
        self.active_assignments = {task_id: object() for task_id in active}


def invoke(
    *,
    rows: dict[str, dict[str, Any]] | None = None,
    durable: DurableWorkflowObservation | None = None,
    active: tuple[str, ...] = (),
    identities: tuple[snapshot_module._SourceIdentity, ...] | None = None,
    refresh: dict[str, Any] | None = None,
):
    selected_rows = rows or {
        PARENT: {
            "task_id": PARENT,
            "state": "not_delivered",
            "decomposition_children": [],
            "head_commit": HEAD,
        }
    }
    selected_durable = durable or DurableWorkflowObservation((), ())
    identity_values = identities or (identity(), identity())
    backend = MemoryIssueBackend()
    scheduler = Scheduler(active)
    producer = ProductionCoherentSnapshotter(
        manifest=manifest(),
        scheduler=scheduler,
        checkout_root=ROOT.parent,
        worker_id="coherent-snapshot-test-worker",
        backend_factory=lambda _root: backend,
    )
    with (
        patch.object(
            snapshot_module,
            "refresh_source_main",
            return_value=refresh
            or {"before": HEAD, "after": HEAD, "changed": False},
        ),
        patch.object(
            snapshot_module,
            "_capture_source_identity",
            side_effect=identity_values,
        ),
        patch.object(
            snapshot_module,
            "list_committed_task_ids",
            return_value=sorted(selected_rows),
        ),
        patch.object(
            snapshot_module,
            "taskcontrol_states_snapshot",
            return_value=selected_rows,
        ),
        patch.object(
            snapshot_module,
            "load_dispatch_policy",
            return_value=SimpleNamespace(known_dependency_states={"not_delivered", "aggregate"}),
        ),
        patch.object(
            snapshot_module,
            "observe_durable_workflows",
            return_value=selected_durable,
        ),
        patch.object(snapshot_module, "_git_text", return_value=TREE),
        patch.object(snapshot_module, "_is_ancestor", return_value=True),
    ):
        return producer()


def test_refresh_happens_before_a_completion_capable_identity_is_captured() -> None:
    calls: list[str] = []
    refreshed = identity(head=NEW_HEAD, tree=NEW_TREE, origin=NEW_HEAD)

    def refresh(_source: Path) -> dict[str, Any]:
        calls.append("refresh")
        return {"before": HEAD, "after": NEW_HEAD, "changed": True}

    def capture(_source: Path) -> snapshot_module._SourceIdentity:
        calls.append("capture")
        return refreshed

    producer = ProductionCoherentSnapshotter(
        manifest=manifest(),
        scheduler=Scheduler(),
        checkout_root=ROOT.parent,
        worker_id="refresh-order-worker",
        backend_factory=lambda _root: MemoryIssueBackend(),
    )
    with (
        patch.object(snapshot_module, "refresh_source_main", side_effect=refresh),
        patch.object(snapshot_module, "_capture_source_identity", side_effect=capture),
        patch.object(snapshot_module, "list_committed_task_ids", return_value=(PARENT,)),
        patch.object(
            snapshot_module,
            "taskcontrol_states_snapshot",
            return_value={
                PARENT: {
                    "task_id": PARENT,
                    "state": "not_delivered",
                    "head_commit": NEW_HEAD,
                    "decomposition_children": [],
                }
            },
        ),
        patch.object(
            snapshot_module,
            "load_dispatch_policy",
            return_value=SimpleNamespace(known_dependency_states={"not_delivered"}),
        ),
        patch.object(
            snapshot_module,
            "observe_durable_workflows",
            return_value=DurableWorkflowObservation((), ()),
        ),
        patch.object(snapshot_module, "_git_text", return_value=TREE),
        patch.object(snapshot_module, "_is_ancestor", return_value=True),
    ):
        observed = producer()
    require(calls == ["refresh", "capture", "capture"], str(calls))
    require(observed.source_head == NEW_HEAD, str(observed))
    require(observed.origin_main_head == NEW_HEAD, str(observed))


def test_one_cached_issue_batch_produces_workflow_and_reservation_views() -> None:
    task = {
        "id": PARENT,
        "title": "Synthetic coherent observation",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Prove one Issue batch.",
        "depends_on": [],
        "exclusive_resources": ["synthetic:coherent-observation"],
        "acceptance_criteria": [],
        "completion_gates": [],
        "task_contract_sha256": "a" * 64,
    }
    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda _task_id: task,
        worker_id="prior-process-worker",
    )
    service.acquire_agent_lease(
        task=task,
        source_head=HEAD,
        branch="nsc-901-fixture",
        checkout_path=str(ROOT.parent / PARENT),
        planned_approach="Create a synthetic fixture.",
        expected_validation="Observe its durable reservation.",
        now="2026-09-04T00:00:00Z",
    )
    list_calls = 0
    original = backend.list_issues

    def counted_list() -> list[dict[str, Any]]:
        nonlocal list_calls
        list_calls += 1
        return original()

    backend.list_issues = counted_list  # type: ignore[method-assign]
    observed = observe_durable_workflows(
        source=ROOT,
        checkout_root=ROOT.parent,
        worker_id="snapshot-observer",
        backend=PlanScopedIssueBackend(backend),
        task_loader=lambda _task_id: task,
    )
    require(list_calls == 1, f"expected one Issue list, saw {list_calls}")
    require(len(observed.snapshots) == 1, str(observed.snapshots))
    require(len(observed.reservations) == 1, str(observed.reservations))
    require(observed.snapshots[0].state.task_id == PARENT, str(observed.snapshots))
    require(observed.reservations[0].task_id == PARENT, str(observed.reservations))


def test_d1c_children_expand_from_the_same_bulk_taskgraph_payload() -> None:
    observed = invoke(
        rows={
            PARENT: {
                "task_id": PARENT,
                "state": "aggregate",
                "decomposition_children": [CHILD],
                "head_commit": HEAD,
            },
            CHILD: {
                "task_id": CHILD,
                "state": "not_delivered",
                "decomposition_children": [],
                "head_commit": HEAD,
            },
        }
    )
    by_id = {item.task_id: item for item in observed.tasks}
    require(by_id[PARENT].decomposition_children == (CHILD,), str(by_id[PARENT]))
    require(CHILD in by_id, str(by_id))


def test_prior_process_reservation_is_not_adopted_as_an_active_assignment() -> None:
    observed = invoke(
        durable=DurableWorkflowObservation((), (reservation(PARENT),)),
        active=(CHILD,),
    )
    require(observed.reservation_task_ids == (PARENT,), str(observed))
    require(observed.active_assignment_task_ids == (CHILD,), str(observed))


def test_source_movement_during_construction_fails_closed() -> None:
    before = identity()
    after = identity(head=NEW_HEAD, tree=NEW_TREE, origin=NEW_HEAD)
    rejects(
        lambda: invoke(identities=(before, after)),
        "moved during coherent snapshot construction",
    )


def main() -> int:
    tests = (
        test_refresh_happens_before_a_completion_capable_identity_is_captured,
        test_one_cached_issue_batch_produces_workflow_and_reservation_views,
        test_d1c_children_expand_from_the_same_bulk_taskgraph_payload,
        test_prior_process_reservation_is_not_adopted_as_an_active_assignment,
        test_source_movement_during_construction_fails_closed,
    )
    for test in tests:
        test()
    print(f"production_graph_snapshot_smoke_test: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
