#!/usr/bin/env python3
"""Production coherent observation adapter for autonomous graph completion.

The adapter is deliberately read-only after the canonical source-main refresh.
It binds one exact Git identity, one authoritative all-task conformance payload,
and one cached managed-Issue batch.  A second Git identity read must match the
first byte-for-byte before the observation can reach graph-completion logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from Pipeline.TaskReviewAgent.autonomous_graph_run import (
    AutonomousGraphRunError,
    AutonomousRunManifest,
    CoherentGraphSnapshot,
    ManagedIssueObservation,
    TaskObservation,
)
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import semantic_sha256
from Pipeline.TaskReviewAgent.dispatch_plan import (
    PlanScopedIssueBackend,
    list_committed_task_ids,
    taskcontrol_states_snapshot,
)
from Pipeline.TaskReviewAgent.dispatch_policy import load_dispatch_policy
from Pipeline.TaskReviewAgent.issue_workflow_store import (
    GhIssueBackend,
    IssueBackend,
    IssueWorkflowSnapshot,
)
from Pipeline.TaskReviewAgent.polling_orchestrator import (
    DurableWorkflowObservation,
    _git_text,
    _run_git,
    authorized_local_ahead_recovery_task,
    observe_durable_workflows,
    refresh_source_main,
)


class ProductionGraphSnapshotError(AutonomousGraphRunError):
    """A production graph snapshot could not be proven coherent."""


class SchedulerAssignments(Protocol):
    active_assignments: Mapping[str, Any]


@dataclass(frozen=True)
class _SourceIdentity:
    branch: str
    attached: bool
    clean: bool
    head: str
    tree: str
    origin_main_head: str


def _git_output(root: Path, *args: str) -> tuple[int, str]:
    result = _run_git(root, *args)
    try:
        output = result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ProductionGraphSnapshotError("Git text output was not UTF-8") from exc
    return result.returncode, output


def _capture_source_identity(root: Path) -> _SourceIdentity:
    branch_code, branch = _git_output(
        root, "symbolic-ref", "--quiet", "--short", "HEAD"
    )
    if branch_code not in {0, 1}:
        raise ProductionGraphSnapshotError(
            "could not determine whether the source checkout is attached"
        )
    attached = branch_code == 0
    return _SourceIdentity(
        branch=branch if attached else "(detached)",
        attached=attached,
        clean=not bool(
            _git_text(root, "status", "--porcelain=v1", "--untracked-files=all")
        ),
        head=_git_text(root, "rev-parse", "--verify", "HEAD^{commit}"),
        tree=_git_text(root, "rev-parse", "--verify", "HEAD^{tree}"),
        origin_main_head=_git_text(
            root, "rev-parse", "--verify", "origin/main^{commit}"
        ),
    )


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    result = _run_git(root, "merge-base", "--is-ancestor", ancestor, descendant)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    detail = result.stderr.decode("utf-8", errors="replace").strip()
    raise ProductionGraphSnapshotError(
        "could not prove source ancestry" + (f": {detail[:500]}" if detail else "")
    )


def _detail_from_latest_event(
    snapshot: IssueWorkflowSnapshot,
    key: str,
) -> str | None:
    for event in reversed(snapshot.events):
        value = event.details.get(key)
        if type(value) is str and value:
            return value
    return None


def _managed_issue_observation(
    snapshot: IssueWorkflowSnapshot,
) -> ManagedIssueObservation:
    state = snapshot.state
    if state is None:
        raise ProductionGraphSnapshotError(
            f"managed Issue #{snapshot.issue_number} has no workflow state"
        )
    last_event = snapshot.events[-1] if snapshot.events else None
    return ManagedIssueObservation(
        task_id=state.task_id,
        state=state.state,
        phase=state.phase,
        state_version=state.state_version,
        last_event_id=state.last_event_id,
        head_commit=state.head_commit,
        human_handoff_commit=state.human_handoff_commit,
        worker_id=state.worker_id,
        lease_id=state.lease_id,
        decomposition_run_id=_detail_from_latest_event(
            snapshot, "decomposition_run_id"
        ),
        graph_delta_plan_id=_detail_from_latest_event(
            snapshot, "graph_delta_plan_id"
        ),
        last_event_evidence_sha256=(
            semantic_sha256(last_event.details) if last_event is not None else None
        ),
    )


class ProductionCoherentSnapshotter:
    """Create completion-capable snapshots from exact production authorities."""

    def __init__(
        self,
        *,
        manifest: AutonomousRunManifest,
        scheduler: SchedulerAssignments,
        checkout_root: Path | str,
        worker_id: str,
        backend_factory: Callable[[Path], IssueBackend] | None = None,
    ) -> None:
        source = Path(manifest.source_repository).resolve()
        if not source.is_absolute():  # pragma: no cover - manifest already enforces this
            raise ProductionGraphSnapshotError("source repository must be absolute")
        if type(worker_id) is not str or not worker_id.strip():
            raise ProductionGraphSnapshotError("worker_id must be non-empty text")
        if not hasattr(scheduler, "active_assignments"):
            raise ProductionGraphSnapshotError(
                "scheduler must expose current active_assignments"
            )
        self.manifest = manifest
        self.scheduler = scheduler
        self.source = source
        self.checkout_root = Path(checkout_root)
        self.worker_id = worker_id
        self.backend_factory = backend_factory or (
            lambda root: GhIssueBackend(source_root=root)
        )
        self._observation_revision = 0

    def _task_observations(
        self,
        *,
        source_identity: _SourceIdentity,
    ) -> tuple[TaskObservation, ...]:
        task_ids = list_committed_task_ids(self.source)
        policy = load_dispatch_policy()
        rows = taskcontrol_states_snapshot(
            self.source,
            expected_task_ids=task_ids,
            source_commit=source_identity.head,
            recognized_states=policy.known_dependency_states,
        )
        observations: list[TaskObservation] = []
        for task_id in task_ids:
            row = rows[task_id]
            children = row.get("decomposition_children")
            if type(children) is not list or any(
                type(child) is not str for child in children
            ):
                raise ProductionGraphSnapshotError(
                    f"TaskGraph state row {task_id} omitted exact decomposition_children"
                )
            observations.append(
                TaskObservation(
                    task_id=task_id,
                    conformance_state=row["state"],
                    decomposition_children=tuple(sorted(children)),
                )
            )
        return tuple(observations)

    def _workflow_observation(
        self,
        *,
        source_identity: _SourceIdentity,
    ) -> DurableWorkflowObservation:
        backend = PlanScopedIssueBackend(self.backend_factory(self.source))
        return observe_durable_workflows(
            source=self.source,
            checkout_root=self.checkout_root,
            worker_id=self.worker_id,
            backend=backend,
            task_loader=lambda task_id: load_committed_task(
                self.source, task_id, commit=source_identity.head
            ),
        )

    def __call__(self) -> CoherentGraphSnapshot:
        try:
            refresh = refresh_source_main(self.source)
            before = _capture_source_identity(self.source)
            tasks = self._task_observations(source_identity=before)
            durable = self._workflow_observation(source_identity=before)
            initial_tree = _git_text(
                self.source,
                "rev-parse",
                "--verify",
                f"{self.manifest.initial_source_commit}^{{tree}}",
            )
            initial_is_ancestor = _is_ancestor(
                self.source, self.manifest.initial_source_commit, before.head
            )
            origin_is_ancestor = _is_ancestor(
                self.source, before.origin_main_head, before.head
            )
            recovery_task_id = authorized_local_ahead_recovery_task(
                refresh, durable.reservations
            )
            active_assignments = self.scheduler.active_assignments
            if not isinstance(active_assignments, Mapping):
                raise ProductionGraphSnapshotError(
                    "scheduler.active_assignments must be a mapping"
                )
            active_task_ids = tuple(sorted(active_assignments))
            after = _capture_source_identity(self.source)
        except Exception as exc:
            if isinstance(exc, ProductionGraphSnapshotError):
                raise
            raise ProductionGraphSnapshotError(
                f"production graph observation failed: {type(exc).__name__}: {exc}"
            ) from exc

        if after != before:
            raise ProductionGraphSnapshotError(
                "source branch, attachment, cleanliness, HEAD, tree, or origin/main "
                "moved during coherent snapshot construction"
            )

        self._observation_revision += 1
        managed = tuple(
            _managed_issue_observation(snapshot) for snapshot in durable.snapshots
        )
        return CoherentGraphSnapshot(
            observation_revision=self._observation_revision,
            source_branch=before.branch,
            source_attached=before.attached,
            source_clean=before.clean,
            source_head=before.head,
            source_tree=before.tree,
            origin_main_head=before.origin_main_head,
            initial_source_commit_is_ancestor=initial_is_ancestor,
            initial_source_tree=initial_tree,
            tasks=tasks,
            managed_issues=managed,
            active_assignment_task_ids=active_task_ids,
            pending_transition_task_ids=tuple(
                sorted(
                    snapshot.state.task_id
                    for snapshot in durable.snapshots
                    if snapshot.pending_transition is not None
                    and snapshot.state is not None
                )
            ),
            reservation_task_ids=tuple(
                sorted({item.task_id for item in durable.reservations})
            ),
            origin_main_is_ancestor_of_source=origin_is_ancestor,
            authorized_local_ahead_recovery_task_id=recovery_task_id,
            authorized_local_ahead_recovery_commit=(
                before.head if recovery_task_id is not None else None
            ),
        )


__all__ = [
    "ProductionCoherentSnapshotter",
    "ProductionGraphSnapshotError",
]
