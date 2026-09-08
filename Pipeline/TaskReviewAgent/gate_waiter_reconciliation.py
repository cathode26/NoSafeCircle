"""Host-owned queue reconciliation before read-only workflow consumers.

Only an entry already in the repository's Git CAS journal can be quarantined.
The wrapper omits its unusable Issue from active workflow discovery, but exposes
the durable unresolved reservation to every resource consumer. Unknown ownership
blocks all work. No Issue is edited and no missing workflow becomes completed.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .integration_gate import IntegrationGateError, validate_waiter_reservation
from .issue_workflow_store import (IssueWorkflowService, IssueWorkflowStoreError, issue_author_authorized,
                                   _task_marker, _expired_pending_workflow_write)


def waiter_reservation(snapshot: Any, task: Mapping) -> dict:
    state = snapshot.state
    resources = task.get("exclusive_resources")
    if (not snapshot.valid or state is None or task.get("id") != state.task_id
            or task.get("task_contract_sha256") != state.task_contract_sha256
            or not isinstance(resources, (list, tuple))):
        raise IntegrationGateError("waiter resources require exact committed task and coherent Issue authority")
    value = dict(issue_number=snapshot.issue_number, task_contract_sha256=state.task_contract_sha256,
                 exclusive_resources=sorted(set(resources)))
    validate_waiter_reservation(value)
    return value


class ReconciledIssueBackend:
    """One pass's journal-proven quarantine plus the existing Issue read port."""
    def __init__(self, backend: Any, quarantines: list[dict], pending_issue_numbers: set[int]):
        self._backend = backend
        self._quarantines = deepcopy(quarantines)
        self._pending_issue_numbers = set(pending_issue_numbers)
        self.repository = getattr(backend, "repository", None)

    @property
    def quarantined_waiters(self) -> list[dict]:
        return deepcopy(self._quarantines)

    def list_issues(self):
        omitted = {number for waiter in self._quarantines
                   for number in waiter["quarantine"]["observed_issue_numbers"]}
        return [issue for issue in self._backend.list_issues()
                if issue.get("number") not in omitted or issue.get("number") in self._pending_issue_numbers]

    def __getattr__(self, name):
        return getattr(self._backend, name)


def quarantined_waiters(backend: Any) -> list[dict]:
    # Accept only the host-created wrapper, not arbitrary Issue JSON or a flag.
    from .dispatch_plan import PlanScopedIssueBackend
    while isinstance(backend, PlanScopedIssueBackend):
        backend = backend._backend
    return backend.quarantined_waiters if isinstance(backend, ReconciledIssueBackend) else []


def reconcile_backend(backend: Any, *, gate: Any, task_loader: Any, worker_id: str) -> ReconciledIssueBackend:
    """Bounded, idempotent journal updates before the pass's pure readers run."""
    if isinstance(backend, ReconciledIssueBackend):
        return backend
    service = IssueWorkflowService(backend=backend, task_loader=task_loader, worker_id=worker_id)
    issues = backend.list_issues()
    pending_issue_numbers: set[int] = set()
    _, initial = gate.read()
    for waiter in initial["queue"]:
        task_id = waiter["task_id"]
        numbers = []
        marker = _task_marker(task_id)
        for issue in issues:
            title = str(issue.get("title") or "")
            if issue_author_authorized(issue) and (title == task_id or title.startswith(task_id + " —")
                    or marker in str(issue.get("body") or "")):
                number = issue.get("number")
                if type(number) is int and number > 0:
                    numbers.append(number)
        try:
            snapshot = service.find(task_id)
        except IssueWorkflowStoreError:
            snapshot = None
        if snapshot is not None and snapshot.pending_transition is not None:
            # A proven pending write is not quarantined or removed from scans.
            pending_issue_numbers.add(snapshot.issue_number)
            continue
        if snapshot is None or not snapshot.valid or snapshot.state is None:
            issue = next((item for item in issues if snapshot is not None
                          and item.get("number") == snapshot.issue_number), None)
            if issue is not None and _expired_pending_workflow_write(backend, issue, snapshot):
                # Expiration is corruption under the existing bounded policy,
                # not a route into quarantine's disjoint-work exception.
                raise IssueWorkflowStoreError("proven pending workflow write expired; repair managed Issue authority")
            if not gate.quarantine_waiter(task_id, reason="workflow_missing_or_invalid",
                                          observed_issue_numbers=numbers):
                raise IntegrationGateError("waiter quarantine CAS raced; re-observe before admission")
            continue
        if waiter.get("quarantine"):
            try:
                reservation = waiter_reservation(snapshot, task_loader(task_id))
            except (IntegrationGateError, KeyError, OSError):
                reservation = None
            if reservation is None or not gate.reconcile_waiter(task_id, reservation=reservation,
                                         history_event_ids=[event.event_id for event in snapshot.events],
                                         issue_event_id=snapshot.state.last_event_id):
                if not gate.quarantine_waiter(task_id, reason="workflow_reappearance_not_bound",
                                              observed_issue_numbers=numbers):
                    raise IntegrationGateError("waiter reconciliation raced; re-observe before admission")
    _, final = gate.read()
    quarantines = [item for item in final["queue"] if item.get("quarantine")]
    return ReconciledIssueBackend(backend, quarantines, pending_issue_numbers)
