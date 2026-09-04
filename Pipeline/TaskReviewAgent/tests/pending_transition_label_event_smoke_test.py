#!/usr/bin/env python3
"""Regression tests: the bounded PENDING_TRANSITION window is dated by GitHub's
`labeled` event for the target state label, never by the Issue's general
``updated_at``.

Classification: pure/component tests over the in-memory Issue backend and the
plan-scoped read cache; no repository file, GitHub Issue, or container is
touched. Every test proves an explicit regression-only invariant of the
scheduler's durable-reservation read path.
"""

from __future__ import annotations

import datetime
import io
import json
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.issue_workflow_store as store_module  # noqa: E402
import Pipeline.TaskReviewAgent.tests.issue_workflow_smoke_test as workflow_fixture  # noqa: E402
from Pipeline.TaskReviewAgent.dispatch_plan import (  # noqa: E402
    DispatchPlan,
    _PlanScopedIssueBackend,
)
from Pipeline.TaskReviewAgent.polling_orchestrator import (  # noqa: E402
    JsonEventEmitter,
    PollingOrchestrator,
    observe_durable_integration_reservations,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    ALL_STATE_LABELS,
    STATE_LABELS,
    WorkflowState,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    PENDING_TRANSITION_MAX_AGE_SECONDS,
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowSnapshot,
    IssueWorkflowStoreError,
    MemoryIssueBackend,
    _snapshot,
)

TASK = workflow_fixture.TASK_ID
OTHER = workflow_fixture.OTHER_TASK_ID
SHARED_RESOURCE = "unity-scene:Assets/Scenes/Test.unity"
AGENT_READY_LABEL = STATE_LABELS[WorkflowState.AGENT_READY.value]
AGENT_WORKING_LABEL = STATE_LABELS[WorkflowState.AGENT_WORKING.value]
_BASE = datetime.datetime(2026, 9, 4, 0, 0, 0, tzinfo=datetime.timezone.utc)
LABEL_AT = 120.0
MAX_AGE = PENDING_TRANSITION_MAX_AGE_SECONDS


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def stamp(offset_seconds: float) -> str:
    moment = _BASE + datetime.timedelta(seconds=offset_seconds)
    return moment.isoformat().replace("+00:00", "Z")


def github_label_event(
    backend: MemoryIssueBackend,
    issue_number: int,
    *,
    label: str,
    created_at: str,
    event: str = "labeled",
) -> None:
    """Record one GitHub-shaped label event on the in-memory backend.

    Production backends record these through ``record_label_event``. When that
    method is absent (the pre-fix backend under regression comparison) the same
    GitHub-shaped record is written directly, so a failing assertion below
    reports the behavioural defect rather than a missing fixture method.
    """

    recorder = getattr(backend, "record_label_event", None)
    if callable(recorder):
        recorder(issue_number, label=label, created_at=created_at, event=event)
        return
    history = backend.__dict__.setdefault("issue_events", {}).setdefault(issue_number, [])
    history.append(
        {
            "id": 1000 + sum(len(items) for items in backend.__dict__["issue_events"].values()),
            "event": event,
            "label": {"name": label, "color": "ededed"},
            "created_at": created_at,
            "actor": {"login": "cathode26"},
        }
    )


def label_event_history(backend: MemoryIssueBackend, issue_number: int) -> list[dict[str, Any]]:
    return json.loads(json.dumps(backend.__dict__.get("issue_events", {}).get(issue_number, [])))


@contextmanager
def frozen_clock(offset_seconds: float):
    original = store_module.pending_transition_now
    store_module.pending_transition_now = lambda: _BASE + datetime.timedelta(
        seconds=offset_seconds
    )
    try:
        yield
    finally:
        store_module.pending_transition_now = original


class Fixture:
    """One managed Issue that really reached human_action_required.

    The backend clock is deterministic and advanced explicitly, so every
    managed label write records a GitHub-shaped event at a known time.
    """

    def __init__(
        self, *, backend: MemoryIssueBackend | None = None, handoff: bool = True
    ) -> None:
        self.clock = {"offset": 0.0}
        self.backend = backend or MemoryIssueBackend(
            now=lambda: stamp(self.clock["offset"])
        )
        self.tasks = {
            TASK: workflow_fixture.task(TASK, SHARED_RESOURCE),
            OTHER: workflow_fixture.task(OTHER, SHARED_RESOURCE),
        }
        self.service = IssueWorkflowService(
            backend=self.backend,
            task_loader=lambda task_id: self.tasks[task_id],
            worker_id="pending-label-event-worker",
        )
        self.service.acquire_agent_lease(
            task=self.tasks[TASK],
            source_head=workflow_fixture.SOURCE_HEAD,
            branch=workflow_fixture.BRANCH,
            checkout_path=workflow_fixture.CHECKOUT,
            planned_approach="Prove the label-event window.",
            expected_validation="Vincent completes the Unity checklist.",
            now=stamp(0),
        )
        self.issue_number = next(iter(self.backend.issues))
        if not handoff:
            return
        self.clock["offset"] = 60.0
        self.service.publish_human_handoff(
            task_id=TASK,
            branch=workflow_fixture.BRANCH,
            head_commit=workflow_fixture.HANDOFF_HEAD,
            checkout_path=workflow_fixture.CHECKOUT,
            implementation_summary="Fixture handoff.",
            completed_checks=["deterministic checks"],
            human_steps=["Open the canonical checkout."],
            expected_result="The doorway publishes once.",
            now=stamp(60),
        )

    @property
    def issue(self) -> dict[str, Any]:
        return self.backend.issues[self.issue_number]

    def apply_ui_label(
        self,
        label: str = AGENT_READY_LABEL,
        *,
        at_offset: float = LABEL_AT,
        replace: bool = False,
        record_event: bool = True,
    ) -> None:
        """Model a GitHub UI label write: the label list changes and GitHub
        records one `labeled` event. ``record_event=False`` models a listing
        whose event history cannot prove the write."""

        names = {item["name"] for item in self.issue["labels"]}
        if replace:
            names -= set(ALL_STATE_LABELS)
        names.add(label)
        self.issue["labels"] = [{"name": name} for name in sorted(names)]
        self.issue["updated_at"] = stamp(at_offset)
        if record_event:
            github_label_event(
                self.backend, self.issue_number, label=label, created_at=stamp(at_offset)
            )

    def unrelated_activity(self, *, at_offset: float) -> None:
        """A comment plus body edit: GitHub refreshes updated_at, no label event."""

        self.issue["updated_at"] = stamp(at_offset)
        self.backend.comments.setdefault(self.issue_number, []).append(
            {
                "id": 9000,
                "author": {"login": "cathode26"},
                "body": "Unrelated follow-up comment.",
            }
        )

    def snapshot(self) -> IssueWorkflowSnapshot:
        return _snapshot(self.backend, self.backend.get_issue(self.issue_number))


def _assert_pending(snapshot: IssueWorkflowSnapshot, *, age: float) -> None:
    require(snapshot.pending_transition is not None, f"not pending: {snapshot.reasons}")
    pending = snapshot.pending_transition
    require(pending.from_state is WorkflowState.HUMAN_ACTION_REQUIRED, str(pending))
    require(pending.to_state is WorkflowState.AGENT_READY, str(pending))
    require(pending.target_label == AGENT_READY_LABEL, str(pending))
    require(abs(pending.age_seconds - age) < 1e-6, f"age {pending.age_seconds} != {age}")
    require(pending.label_applied_at_utc == stamp(LABEL_AT), str(pending))
    require(type(pending.label_event_id) is int and pending.label_event_id > 0, str(pending))
    require(not snapshot.valid, "a pending snapshot is never valid")
    payload = pending.to_dict()
    require(
        payload["label_event_id"] == pending.label_event_id
        and payload["label_applied_at_utc"] == stamp(LABEL_AT)
        and "updated_at" not in json.dumps(payload),
        str(payload),
    )


def _assert_invalid_not_pending(snapshot: IssueWorkflowSnapshot) -> None:
    require(snapshot.pending_transition is None, f"unexpected pending: {snapshot}")
    require(not snapshot.valid and snapshot.managed, str(snapshot))
    require(
        any("state label mismatch" in reason for reason in snapshot.reasons),
        str(snapshot.reasons),
    )


# --- behavior-changing tests (fail against the updated_at-based code) --------


def test_unrelated_issue_activity_does_not_renew_the_pending_window() -> None:
    fixture = Fixture()
    fixture.apply_ui_label(at_offset=LABEL_AT)
    # A comment/body edit 30 seconds before expiry refreshes updated_at.
    fixture.unrelated_activity(at_offset=LABEL_AT + MAX_AGE - 30)
    with frozen_clock(LABEL_AT + MAX_AGE - 1):
        _assert_pending(fixture.snapshot(), age=MAX_AGE - 1)
    with frozen_clock(LABEL_AT + MAX_AGE + 1):
        # updated_at is only 31 seconds old here; the label event is expired.
        _assert_invalid_not_pending(fixture.snapshot())


def test_window_is_measured_from_the_label_event_not_updated_at() -> None:
    fixture = Fixture()
    fixture.apply_ui_label(at_offset=LABEL_AT)
    # Stale listing metadata: updated_at far older than the label event.
    fixture.issue["updated_at"] = stamp(0)
    with frozen_clock(LABEL_AT + 60):
        _assert_pending(fixture.snapshot(), age=60)
    # And metadata far newer than the event does not shrink the age either.
    fixture.issue["updated_at"] = stamp(LABEL_AT + 59)
    with frozen_clock(LABEL_AT + 60):
        _assert_pending(fixture.snapshot(), age=60)


def test_missing_label_event_evidence_fails_closed() -> None:
    fixture = Fixture()
    fixture.apply_ui_label(at_offset=LABEL_AT, record_event=False)
    with frozen_clock(LABEL_AT + 60):
        snapshot = fixture.snapshot()
    _assert_invalid_not_pending(snapshot)
    require(
        any("cannot be dated" in reason for reason in snapshot.reasons),
        str(snapshot.reasons),
    )


def test_backend_without_label_event_support_fails_closed() -> None:
    class NoEventsBackend(MemoryIssueBackend):
        get_issue_events = None  # type: ignore[assignment]

    fixture = Fixture(backend=NoEventsBackend(now=lambda: stamp(0)))
    fixture.apply_ui_label(at_offset=LABEL_AT)
    with frozen_clock(LABEL_AT + 60):
        snapshot = fixture.snapshot()
    _assert_invalid_not_pending(snapshot)
    require(
        any("cannot be dated" in reason for reason in snapshot.reasons),
        str(snapshot.reasons),
    )


def test_malformed_label_event_identity_or_timestamp_fails_closed() -> None:
    for corruption in (
        {"id": None},
        {"id": "17"},
        {"id": 0},
        {"created_at": None},
        {"created_at": "yesterday"},
        {"label": {"color": "ededed"}},
        {"label": "nsc-state:agent-ready"},
    ):
        fixture = Fixture()
        fixture.apply_ui_label(at_offset=LABEL_AT)
        record = fixture.backend.__dict__["issue_events"][fixture.issue_number][-1]
        require(record["label"]["name"] == AGENT_READY_LABEL, str(record))
        record.update(corruption)
        with frozen_clock(LABEL_AT + 60):
            snapshot = fixture.snapshot()
        _assert_invalid_not_pending(snapshot)
        require(
            any("cannot be dated" in reason for reason in snapshot.reasons),
            f"{corruption}: {snapshot.reasons}",
        )
    # A corrupt payload shape (not a list of objects) is equally unprovable.
    fixture = Fixture()
    fixture.apply_ui_label(at_offset=LABEL_AT)
    fixture.backend.__dict__["issue_events"][fixture.issue_number].append("labeled")
    with frozen_clock(LABEL_AT + 60):
        _assert_invalid_not_pending(fixture.snapshot())


def test_later_unlabeled_event_is_not_an_open_transition() -> None:
    fixture = Fixture()
    fixture.apply_ui_label(at_offset=LABEL_AT)
    # GitHub says the label was removed again, but the listing still shows it.
    github_label_event(
        fixture.backend,
        fixture.issue_number,
        label=AGENT_READY_LABEL,
        event="unlabeled",
        created_at=stamp(LABEL_AT + 10),
    )
    fixture.issue["updated_at"] = stamp(LABEL_AT + 10)
    with frozen_clock(LABEL_AT + 60):
        _assert_invalid_not_pending(fixture.snapshot())
    # Re-applying the label is a new datable transition.
    github_label_event(
        fixture.backend,
        fixture.issue_number,
        label=AGENT_READY_LABEL,
        created_at=stamp(LABEL_AT + 20),
    )
    with frozen_clock(LABEL_AT + 60):
        snapshot = fixture.snapshot()
    require(snapshot.pending_transition is not None, str(snapshot.reasons))
    require(abs(snapshot.pending_transition.age_seconds - 40) < 1e-6, str(snapshot))


def test_additive_and_replacement_ui_shapes_both_date_from_the_label_event() -> None:
    for replace in (False, True):
        fixture = Fixture()
        fixture.apply_ui_label(at_offset=LABEL_AT, replace=replace)
        state_labels = {
            item["name"] for item in fixture.issue["labels"]
        } & ALL_STATE_LABELS
        expected = (
            {AGENT_READY_LABEL}
            if replace
            else {AGENT_READY_LABEL, STATE_LABELS[WorkflowState.HUMAN_ACTION_REQUIRED.value]}
        )
        require(state_labels == expected, f"replace={replace}: {state_labels}")
        # updated_at is stale in both shapes; only the event can date the window.
        fixture.issue["updated_at"] = stamp(0)
        with frozen_clock(LABEL_AT + MAX_AGE - 1):
            _assert_pending(fixture.snapshot(), age=MAX_AGE - 1)
        with frozen_clock(LABEL_AT + MAX_AGE + 1):
            _assert_invalid_not_pending(fixture.snapshot())


def test_pending_holder_reserves_resources_and_is_not_selectable_until_expiry() -> None:
    fixture = Fixture()
    fixture.apply_ui_label(at_offset=LABEL_AT)
    fixture.unrelated_activity(at_offset=LABEL_AT + MAX_AGE - 30)
    with frozen_clock(LABEL_AT + MAX_AGE - 1):
        ready = fixture.service.list_agent_ready()
        require(ready == [], f"pending Issue was selectable: {ready}")
        blocked = fixture.service.acquire_agent_lease(
            task=fixture.tasks[OTHER],
            source_head=workflow_fixture.SOURCE_HEAD,
            branch="nsc-778-other",
            checkout_path=r"C:\NSC\NSC\NSC-778",
            planned_approach="Take the shared scene.",
            expected_validation="Never granted.",
            now=stamp(LABEL_AT + MAX_AGE - 1),
        )
    require(blocked.get("status") == "blocked", str(blocked))
    reasons = " ".join(blocked.get("reasons") or ())
    require(TASK in reasons and SHARED_RESOURCE in reasons, reasons)
    require("must be repaired" not in reasons, f"pending holder reported corrupt: {reasons}")
    with frozen_clock(LABEL_AT + MAX_AGE + 1):
        expired = fixture.service.acquire_agent_lease(
            task=fixture.tasks[OTHER],
            source_head=workflow_fixture.SOURCE_HEAD,
            branch="nsc-778-other",
            checkout_path=r"C:\NSC\NSC\NSC-778",
            planned_approach="Take the shared scene.",
            expected_validation="Never granted.",
            now=stamp(LABEL_AT + MAX_AGE + 1),
        )
    require(expired.get("status") == "blocked", str(expired))
    expired_reasons = " ".join(expired.get("reasons") or ())
    require(
        "must be repaired before resource coordination" in expired_reasons,
        f"expired transition was not ordinary invalid state: {expired_reasons}",
    )
    with frozen_clock(LABEL_AT + MAX_AGE + 1):
        try:
            fixture.service.list_agent_ready()
        except IssueWorkflowStoreError as exc:
            require("is invalid" in str(exc), str(exc))
        else:
            raise AssertionError("expired transition did not fail closed in discovery")


def test_plan_scoped_backend_reads_label_events_once_per_snapshot() -> None:
    class CountingBackend(MemoryIssueBackend):
        def __init__(self, **values: Any) -> None:
            super().__init__(**values)
            self.event_reads: list[int] = []

        def get_issue_events(self, issue_number: int) -> list[dict[str, Any]]:
            self.event_reads.append(issue_number)
            return label_event_history(self, issue_number)

    fixture = Fixture(backend=CountingBackend(now=lambda: stamp(0)))
    fixture.apply_ui_label(at_offset=LABEL_AT)
    scoped = _PlanScopedIssueBackend(fixture.backend)
    with frozen_clock(LABEL_AT + 60):
        listed = scoped.list_issues()
        first = _snapshot(scoped, listed[0])
        second = _snapshot(scoped, listed[0])
        require(first.pending_transition is not None and second.pending_transition is not None, "not pending")
        require(fixture.backend.event_reads == [fixture.issue_number], str(fixture.backend.event_reads))
        # An exact re-read invalidates the cached events exactly like comments.
        scoped.get_issue(fixture.issue_number)
        _snapshot(scoped, scoped.get_issue(fixture.issue_number))
        require(fixture.backend.event_reads == [fixture.issue_number] * 2, str(fixture.backend.event_reads))
    for name in ("create_issue", "update_issue", "add_comment", "ensure_labels"):
        try:
            getattr(scoped, name)(*([1, "x"] if name == "add_comment" else [1] if name == "update_issue" else []))
        except IssueWorkflowStoreError:
            continue
        raise AssertionError(f"plan-scoped backend permitted {name}")


def test_coherent_issue_never_reads_label_events() -> None:
    class CountingBackend(MemoryIssueBackend):
        def __init__(self, **values: Any) -> None:
            super().__init__(**values)
            self.event_reads: list[int] = []

        def get_issue_events(self, issue_number: int) -> list[dict[str, Any]]:
            self.event_reads.append(issue_number)
            return label_event_history(self, issue_number)

    fixture = Fixture(backend=CountingBackend(now=lambda: stamp(0)))
    coherent = fixture.snapshot()
    require(coherent.valid and coherent.pending_transition is None, str(coherent.reasons))
    # An illegal pair is invalid before any event read as well.
    fixture.apply_ui_label(AGENT_WORKING_LABEL, at_offset=LABEL_AT)
    with frozen_clock(LABEL_AT + 60):
        illegal = fixture.snapshot()
    _assert_invalid_not_pending(illegal)
    require(fixture.backend.event_reads == [], str(fixture.backend.event_reads))


def test_gh_backend_lists_issue_events_with_paginated_rest_call() -> None:
    backend = object.__new__(GhIssueBackend)
    backend.source_root = ROOT
    backend.repository = "cathode26/NoSafeCircle"
    calls: list[tuple[str, ...]] = []
    pages = (
        '[{"id": 11, "event": "labeled", "label": {"name": "nsc-state:agent-ready"}, '
        '"created_at": "2026-09-04T00:02:00Z", "actor": {"login": "cathode26"}}]'
        '[{"id": 12, "event": "commented", "created_at": "2026-09-04T00:03:00Z"}]'
    )

    def fake_run(args: tuple[str, ...], *, check: bool = True):
        calls.append(tuple(args))
        return subprocess.CompletedProcess(args=tuple(args), returncode=0, stdout=pages, stderr="")

    with patch.object(GhIssueBackend, "_run", staticmethod(fake_run)):
        events = backend.get_issue_events(7)
    require(
        calls
        == [
            (
                "gh",
                "api",
                "--paginate",
                "repos/cathode26/NoSafeCircle/issues/7/events?per_page=100",
            )
        ],
        str(calls),
    )
    require([item["id"] for item in events] == [11, 12], str(events))
    with patch.object(
        GhIssueBackend,
        "_run",
        staticmethod(lambda args, check=True: subprocess.CompletedProcess(args, 0, "{}", "")),
    ):
        try:
            backend.get_issue_events(7)
        except IssueWorkflowStoreError as exc:
            require("GitHub issue events" in str(exc), str(exc))
        else:
            raise AssertionError("non-array events page was accepted")
    for bad in (0, -1, "7"):
        try:
            backend.get_issue_events(bad)  # type: ignore[arg-type]
        except IssueWorkflowStoreError:
            continue
        raise AssertionError(f"invalid Issue number {bad!r} was accepted")


def test_memory_backend_records_label_events_for_managed_label_writes() -> None:
    fixture = Fixture()
    history = fixture.backend.get_issue_events(fixture.issue_number)
    require(all(item["event"] in {"labeled", "unlabeled"} for item in history), str(history))
    ids = [item["id"] for item in history]
    require(ids == sorted(ids) and len(set(ids)) == len(ids), str(ids))
    human_label = STATE_LABELS[WorkflowState.HUMAN_ACTION_REQUIRED.value]
    latest_human = [item for item in history if item["label"]["name"] == human_label][-1]
    require(latest_human["event"] == "labeled" and latest_human["created_at"] == stamp(60), str(latest_human))
    latest_working = [item for item in history if item["label"]["name"] == AGENT_WORKING_LABEL][-1]
    require(latest_working["event"] == "unlabeled" and latest_working["created_at"] == stamp(60), str(latest_working))
    # Direct label mutation records nothing: evidence must be explicit.
    fixture.apply_ui_label(at_offset=LABEL_AT, record_event=False)
    require(fixture.backend.get_issue_events(fixture.issue_number) == history, "implicit event recorded")
    try:
        fixture.backend.record_label_event(fixture.issue_number, label=AGENT_READY_LABEL, created_at=stamp(1), event="renamed")
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported event type accepted")


def test_plan_scoped_wrapper_over_eventless_backend_fails_closed() -> None:
    class NoEventsBackend(MemoryIssueBackend):
        get_issue_events = None  # type: ignore[assignment]

    fixture = Fixture(backend=NoEventsBackend(now=lambda: stamp(0)))
    fixture.apply_ui_label(at_offset=LABEL_AT)
    scoped = _PlanScopedIssueBackend(fixture.backend)
    with frozen_clock(LABEL_AT + 60):
        snapshot = _snapshot(scoped, scoped.list_issues()[0])
    _assert_invalid_not_pending(snapshot)
    require(
        any("cannot be dated" in reason for reason in snapshot.reasons),
        str(snapshot.reasons),
    )


def test_labeled_event_for_an_unrelated_label_does_not_renew_the_window() -> None:
    fixture = Fixture()
    fixture.apply_ui_label(at_offset=LABEL_AT)
    # A human adds an unrelated label 30 seconds before expiry: GitHub records
    # a `labeled` event for THAT label and refreshes updated_at.
    fixture.issue["labels"].append({"name": "priority:high"})
    fixture.issue["updated_at"] = stamp(LABEL_AT + MAX_AGE - 30)
    github_label_event(
        fixture.backend,
        fixture.issue_number,
        label="priority:high",
        created_at=stamp(LABEL_AT + MAX_AGE - 30),
    )
    with frozen_clock(LABEL_AT + MAX_AGE - 1):
        _assert_pending(fixture.snapshot(), age=MAX_AGE - 1)
    with frozen_clock(LABEL_AT + MAX_AGE + 1):
        _assert_invalid_not_pending(fixture.snapshot())


def test_label_event_transport_failure_propagates_like_comment_reads() -> None:
    class FailingEventsBackend(MemoryIssueBackend):
        def get_issue_events(self, issue_number: int) -> list[dict[str, Any]]:
            raise IssueWorkflowStoreError("gh api issues/events failed (502)")

    fixture = Fixture(backend=FailingEventsBackend(now=lambda: stamp(0)))
    coherent = fixture.snapshot()
    require(coherent.valid, f"coherent Issue must not read events: {coherent.reasons}")
    fixture.apply_ui_label(at_offset=LABEL_AT)
    with frozen_clock(LABEL_AT + 60):
        for read in (fixture.snapshot, fixture.service.list_agent_ready):
            try:
                read()
            except IssueWorkflowStoreError as exc:
                require("502" in str(exc), str(exc))
            else:
                raise AssertionError(f"{read.__name__} swallowed the transport failure")


def test_non_convergible_agent_ready_shape_reads_no_events() -> None:
    class CountingBackend(MemoryIssueBackend):
        def __init__(self, **values: Any) -> None:
            super().__init__(**values)
            self.event_reads: list[int] = []

        def get_issue_events(self, issue_number: int) -> list[dict[str, Any]]:
            self.event_reads.append(issue_number)
            return label_event_history(self, issue_number)

    # Still agent_working (no human handoff): the additive agent-ready shape is
    # legal but the agent-ready Action never converges it, so it is neither
    # pending nor worth a GitHub event read.
    fixture = Fixture(backend=CountingBackend(now=lambda: stamp(0)), handoff=False)
    require(fixture.snapshot().valid, "fixture Issue must start coherent")
    fixture.apply_ui_label(at_offset=LABEL_AT)
    with frozen_clock(LABEL_AT + 60):
        snapshot = fixture.snapshot()
    _assert_invalid_not_pending(snapshot)
    require(
        not any("cannot be dated" in reason for reason in snapshot.reasons),
        f"non-convergible shape must not be reported as undatable: {snapshot.reasons}",
    )
    require(fixture.backend.event_reads == [], str(fixture.backend.event_reads))


def test_scheduler_counts_no_observation_failure_until_the_label_event_expires() -> None:
    """Requirement 5/6 at the scheduler boundary: the real poll loop treats a
    recent label transition as PENDING (reservation kept, counter untouched) and
    the same Issue as an observation failure once the original label event is
    older than the window, even though unrelated activity kept updated_at fresh."""

    fixture = Fixture()
    fixture.apply_ui_label(at_offset=LABEL_AT)
    fixture.unrelated_activity(at_offset=LABEL_AT + MAX_AGE - 30)
    with tempfile.TemporaryDirectory() as text:
        source = Path(text) / "source"
        source.mkdir()
        head = "3" * 40
        stream = io.StringIO()

        def observer():
            return observe_durable_integration_reservations(
                source=source,
                checkout_root=source.parent / "checkouts",
                worker_id="pending-label-event-scheduler",
                backend=fixture.backend,
                task_loader=lambda task_id: fixture.tasks[task_id],
            )

        def idle_plan(**_values: Any) -> DispatchPlan:
            return DispatchPlan(
                schema_version="1.0",
                source_commit=head,
                mode="read_only_plan",
                autonomous_dispatch=False,
                decision="no_safe_work",
                resume=None,
                selected_fresh_candidate=None,
                ranked_eligible_candidates=(),
                skipped_candidates=(),
                agent_ready_count=0,
                claim_observation={"status": "fixture"},
            )

        orchestrator = PollingOrchestrator(
            source=source,
            checkout_root=source.parent / "checkouts",
            scheduler_id="pending-label-event-scheduler",
            execution_provider="claude",
            model=None,
            max_turns=1,
            max_workers=1,
            architect_min_confidence=0.65,
            architect_runner=lambda **_values: (_ for _ in ()).throw(
                AssertionError("the architect must not be consulted")
            ),
            plan_builder=idle_plan,
            task_loader=lambda task_id: fixture.tasks[task_id],
            reservation_observer=observer,
            source_refresher=lambda _source: {"before": head, "after": head, "changed": False},
            process_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("no worker may launch")
            ),
            event_emitter=JsonEventEmitter(stream),
        )

        with frozen_clock(LABEL_AT + MAX_AGE - 1):
            recent = orchestrator.poll_once()
        events = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
        names = [item["event"] for item in events]
        require(recent.status == "idle" and not recent.fatal, str(recent))
        require("issue_pending_transition" in names, str(names))
        pending_event = next(item for item in events if item["event"] == "issue_pending_transition")
        transition = pending_event["pending_transitions"][0]
        require(transition["task_id"] == TASK, str(transition))
        reservations = next(
            item for item in events if item["event"] == "integration_reservations_observed"
        )
        require(
            any(
                item["task_id"] == TASK and SHARED_RESOURCE in item["exclusive_resources"]
                for item in reservations["reservations"]
            ),
            str(reservations),
        )
        require(
            orchestrator.consecutive_observation_failures == 0,
            f"recent transition counted as failure: {orchestrator.consecutive_observation_failures}",
        )
        require("scheduler_wait_observation_failure" not in names, str(names))

        stream.seek(0)
        stream.truncate()
        with frozen_clock(LABEL_AT + MAX_AGE + 1):
            expired = orchestrator.poll_once()
        names = [
            json.loads(line)["event"] for line in stream.getvalue().splitlines() if line.strip()
        ]
        require(expired.status == "reservation_observation_wait" and not expired.fatal, str(expired))
        require("scheduler_wait_observation_failure" in names, str(names))
        require("issue_pending_transition" not in names, str(names))
        require(
            orchestrator.consecutive_observation_failures == 1,
            f"expired label event was not counted: {orchestrator.consecutive_observation_failures}",
        )
        # The scheduler event carries the label-event authority, not updated_at.
        require(transition["label_applied_at_utc"] == stamp(LABEL_AT), str(transition))
        require("updated_at" not in json.dumps(transition), str(transition))


# --- guards: semantics that must stay identical to the pre-fix code -------------
# (the expiry guard also pins the renamed PendingStateTransition fields, so it
# fails on the pre-fix code with AttributeError rather than passing there)


def test_expired_label_event_is_ordinary_invalid_state() -> None:
    fixture = Fixture()
    fixture.apply_ui_label(at_offset=LABEL_AT)
    with frozen_clock(LABEL_AT + MAX_AGE):
        _assert_pending(fixture.snapshot(), age=MAX_AGE)
    with frozen_clock(LABEL_AT + MAX_AGE + 1):
        snapshot = fixture.snapshot()
    _assert_invalid_not_pending(snapshot)
    require(
        not any("cannot be dated" in reason for reason in snapshot.reasons),
        f"expiry must not be reported as missing evidence: {snapshot.reasons}",
    )
    with frozen_clock(LABEL_AT - 1):
        _assert_invalid_not_pending(fixture.snapshot())


def test_convergence_restrictions_are_unchanged() -> None:
    fixture = Fixture()
    fixture.apply_ui_label(AGENT_WORKING_LABEL, at_offset=LABEL_AT)
    with frozen_clock(LABEL_AT + 60):
        _assert_invalid_not_pending(fixture.snapshot())
    fixture = Fixture()
    fixture.apply_ui_label("nsc-state:blocked", at_offset=LABEL_AT)
    with frozen_clock(LABEL_AT + 60):
        _assert_invalid_not_pending(fixture.snapshot())


TESTS = (
    test_unrelated_issue_activity_does_not_renew_the_pending_window,
    test_window_is_measured_from_the_label_event_not_updated_at,
    test_missing_label_event_evidence_fails_closed,
    test_backend_without_label_event_support_fails_closed,
    test_malformed_label_event_identity_or_timestamp_fails_closed,
    test_later_unlabeled_event_is_not_an_open_transition,
    test_additive_and_replacement_ui_shapes_both_date_from_the_label_event,
    test_pending_holder_reserves_resources_and_is_not_selectable_until_expiry,
    test_plan_scoped_backend_reads_label_events_once_per_snapshot,
    test_coherent_issue_never_reads_label_events,
    test_gh_backend_lists_issue_events_with_paginated_rest_call,
    test_memory_backend_records_label_events_for_managed_label_writes,
    test_plan_scoped_wrapper_over_eventless_backend_fails_closed,
    test_labeled_event_for_an_unrelated_label_does_not_renew_the_window,
    test_label_event_transport_failure_propagates_like_comment_reads,
    test_non_convergible_agent_ready_shape_reads_no_events,
    test_scheduler_counts_no_observation_failure_until_the_label_event_expires,
    test_expired_label_event_is_ordinary_invalid_state,
    test_convergence_restrictions_are_unchanged,
)


def main(argv: list[str] | None = None) -> int:
    selected = set(argv or [])
    for test in TESTS:
        if selected and test.__name__ not in selected:
            continue
        test()
        print(f"PASS {test.__name__}")
    print("pending_transition_label_event_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
