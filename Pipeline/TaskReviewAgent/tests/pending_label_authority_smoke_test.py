#!/usr/bin/env python3
"""Pure/component regressions for label-first pending workflow authority.

F5 regression-only invariants, not Unity acceptance or delivery evidence. The
real store reads canonical hashed transitions and in-memory GitHub payloads;
no network, provider, Unity, filesystem, or synthetic-approval work is invoked.
NSC_PENDING_AUTHORITY_SOURCE selects an unchanged checkout for paired red/green
runs without modifying that checkout or the preserved independent audit repro.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.environ.get(
    "NSC_PENDING_AUTHORITY_SOURCE", Path(__file__).resolve().parents[3],
)).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(Path(__file__).resolve().parent))

from Pipeline.TaskReviewAgent import issue_workflow_store as store  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    STATE_LABELS,
    WorkflowActor as Actor,
    WorkflowEventType as Event,
    WorkflowPhase as Phase,
    WorkflowState as State,
    initial_state,
    render_event_comment,
    transition,
    update_issue_body,
    validate_event_chain,
)
from workflow_consumer_fixture import HumanFixture  # noqa: E402

BASE = dt.datetime(2026, 9, 7, tzinfo=dt.timezone.utc)
TASK = "NSC-781"
WORKER = "pending-authority-fixture"
READY_LABEL = STATE_LABELS[State.AGENT_READY.value]
HUMAN_LABEL = STATE_LABELS[State.HUMAN_ACTION_REQUIRED.value]


def stamp(seconds: float) -> str:
    return (BASE + dt.timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


class LabelFixture:
    def __init__(self, *, cycles=0, additive=False, lease_actor=WORKER,
                 handoff_actor=WORKER, lease_at=None, handoff_at=None,
                 decomposition=False):
        self.backend = store.MemoryIssueBackend(now=lambda: stamp(0))
        self.events = []
        self.state = initial_state(task_id=TASK, task_contract_sha256="7" * 64,
                                   phase=Phase.DECOMPOSITION if decomposition else Phase.IMPLEMENTATION,
                                   now=stamp(0))
        for cycle in range(cycles + 1):
            offset = cycle * 100
            self.step(Event.AGENT_LEASE_ACQUIRED, State.AGENT_WORKING,
                      at=lease_at or stamp(offset + 10), actor_id=lease_actor,
                      details={"worker_id": WORKER, "lease_id": str(cycle + 1) * 64})
            handoff_details = {"branch": "nsc-781-authority-fixture",
                               "head_commit": "b" * 40,
                               "checkout_path": "C:/offline-fixture/NSC-781"}
            if decomposition:
                handoff_details.update(decomposition_run_id="fixture-decomposition",
                                       artifact_root="C:/offline-fixture/artifacts",
                                       graph_delta_plan_id="GDP-" + "a" * 64,
                                       graph_delta_sha256="8" * 64)
            self.step(Event.DECOMPOSITION_HANDOFF_CREATED if decomposition
                      else Event.HUMAN_HANDOFF_CREATED, State.HUMAN_ACTION_REQUIRED,
                      at=handoff_at or stamp(offset + 60), actor_id=handoff_actor,
                      phase=Phase.DECOMPOSITION_APPLY_AUTHORIZATION if decomposition
                      else Phase.UNITY_RUNTIME_VALIDATION, details=handoff_details)
            if cycle < cycles:
                self.step(Event.HUMAN_VALIDATION_FAILED, State.AGENT_READY,
                          at=stamp(offset + 70), actor=Actor.HUMAN,
                          phase=Phase.REPAIR, details={"tested_commit": "b" * 40})
        validate_event_chain(self.state, self.events)
        self.label_at = cycles * 100 + 80
        created = self.backend.create_issue(
            title=TASK + " - Pending authority fixture",
            body=update_issue_body("", self.state), labels=[], assignees=["cathode26"],
        )
        self.number = created["number"]
        self.issue = self.backend.issues[self.number]
        self.backend.issue_events[self.number] = []
        self.publish_comments()
        names = [READY_LABEL, HUMAN_LABEL] if additive else [READY_LABEL]
        self.issue["labels"] = [{"name": name} for name in names]
        self.record_label()

    @property
    def history(self):
        return self.backend.issue_events[self.number]

    def step(self, kind, target, *, at, actor=Actor.AGENT, actor_id=None,
             phase=None, details=None):
        self.state, event = transition(
            self.state, event_type=kind, to_state=target, to_phase=phase,
            actor_type=actor,
            actor_id=actor_id or ("cathode26" if actor is Actor.HUMAN else WORKER),
            details=details or {}, now=at,
        )
        self.events.append(event)

    def publish_comments(self):
        self.backend.comments[self.number] = []
        for event in self.events:
            self.backend.add_comment(self.number, render_event_comment(event, "Offline fixture."))

    def record_label(self, *, at=None, actor="cathode26", event="labeled"):
        record = {"id": 1000 + len(self.history), "event": event,
                  "label": {"name": READY_LABEL},
                  "created_at": at or stamp(self.label_at),
                  "actor": {"login": actor}}
        self.history.append(record)
        return record

    def change_body(self, **changes):
        self.issue["body"] = update_issue_body("", replace(self.state, **changes))

    def snapshot(self):
        return store._snapshot(self.backend, self.backend.get_issue(self.number))

    def service(self):
        return store.IssueWorkflowService(
            backend=self.backend, worker_id="fixture-reader",
            task_loader=lambda _: {"id": TASK, "task_contract_sha256": "7" * 64,
                                   "exclusive_resources": ["unity-scene:Assets/Scenes/Fixture.unity"]},
        )


class PendingLabelAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(store, "pending_transition_now",
                                      lambda: BASE + dt.timedelta(seconds=580)))

    def assert_invalid(self, fixture):
        snapshot = fixture.snapshot()
        self.assertIsNone(snapshot.pending_transition,
                          "unproven label-first authority received the bounded waiting exception")
        self.assertFalse(snapshot.valid)
        if snapshot.state is None:
            self.assertEqual(fixture.service().list_agent_ready(), [])
        else:
            with self.assertRaises(store.IssueWorkflowStoreError):
                fixture.service().list_agent_ready()

    def assert_pending(self, fixture):
        snapshot = fixture.snapshot()
        self.assertIsNotNone(snapshot.pending_transition, snapshot.reasons)
        self.assertFalse(snapshot.valid, "pending never grants admission")
        self.assertEqual(snapshot.pending_transition.from_state, fixture.state.state)
        self.assertEqual(snapshot.pending_transition.to_state, State.AGENT_READY)
        self.assertEqual(fixture.service().list_agent_ready(), [])
        return snapshot.pending_transition

    def test_current_label_actor_must_be_authorized(self):
        for actor in ("outside-user", "cathode26[bot]", "", None):
            with self.subTest(actor=actor):
                fixture = LabelFixture()
                fixture.history[-1]["actor"] = {"login": actor}
                self.assert_invalid(fixture)

    def test_authorized_human_and_automation_label_actors_are_supported(self):
        for actor in ("cathode26", "CATHODE26", "github-actions", "github-actions[bot]"):
            with self.subTest(actor=actor):
                fixture = LabelFixture()
                fixture.history[-1]["actor"] = {"login": actor}
                self.assert_pending(fixture)

    def test_body_commit_must_match_canonical_handoff(self):
        fixture = LabelFixture()
        fixture.change_body(head_commit="f" * 40, human_handoff_commit="f" * 40)
        self.assert_invalid(fixture)

    def test_body_branch_checkout_and_timestamp_must_match_replay(self):
        for changes in ({"branch": "nsc-781-other"},
                        {"checkout_path": "C:/offline-fixture/Other"},
                        {"updated_at_utc": stamp(79)}):
            with self.subTest(changes=changes):
                fixture = LabelFixture()
                fixture.change_body(**changes)
                self.assert_invalid(fixture)

    def test_body_cannot_inject_worker_lease_or_owner(self):
        for changes in ({"worker_id": "unowned-worker"}, {"lease_id": "9" * 64},
                        {"current_actor": "agent"}):
            with self.subTest(changes=changes):
                fixture = LabelFixture()
                # Change raw body fields so the production parser, not this
                # fixture's dataclass constructor, decides validity.
                state = fixture.state.to_dict()
                state.update(changes)
                fixture.issue["body"] = "<!-- nsc-workflow-state\n" + json.dumps(state) + "\n-->"
                self.assert_invalid(fixture)

    def test_lease_actor_must_match_recorded_worker(self):
        self.assert_invalid(LabelFixture(lease_actor="different-worker"))

    def test_handoff_actor_must_own_the_recorded_lease(self):
        self.assert_invalid(LabelFixture(handoff_actor="different-worker"))

    def test_workflow_timestamps_must_be_aware_and_chronological(self):
        for changes in ({"lease_at": stamp(10).removesuffix("Z")},
                        {"lease_at": "not-a-time"}, {"lease_at": stamp(70)},
                        {"handoff_at": stamp(590)}):
            with self.subTest(changes=changes):
                self.assert_invalid(LabelFixture(**changes))

    def test_label_timestamp_must_be_aware_and_follow_handoff(self):
        for value in (stamp(80).removesuffix("Z"), stamp(59), stamp(581), "invalid"):
            with self.subTest(value=value):
                fixture = LabelFixture()
                fixture.history[-1]["created_at"] = value
                self.assert_invalid(fixture)

    def test_positive_unique_label_identity_is_required(self):
        for value in (None, "1000", 0, -1, True):
            with self.subTest(value=value):
                fixture = LabelFixture()
                fixture.history[-1]["id"] = value
                self.assert_invalid(fixture)
        fixture = LabelFixture()
        fixture.history.append(copy.deepcopy(fixture.history[-1]))
        self.assert_invalid(fixture)

    def test_additive_and_replaced_labels_keep_repeated_human_cycles(self):
        for additive in (False, True):
            for cycles in (0, 1, 3):
                with self.subTest(additive=additive, cycles=cycles):
                    fixture = LabelFixture(additive=additive, cycles=cycles)
                    pending = self.assert_pending(fixture)
                    self.assertEqual(pending.label_applied_at_utc, stamp(fixture.label_at))

    def test_only_current_application_actor_and_age_authorize_waiting(self):
        fixture = LabelFixture()
        fixture.history[-1]["actor"] = {"login": "outside-user"}
        fixture.record_label(at=stamp(90), event="unlabeled")
        fixture.record_label(at=stamp(100))
        self.assert_pending(fixture)
        fixture.record_label(at=stamp(110), event="unlabeled")
        fixture.record_label(at=stamp(120), actor="outside-user")
        self.assert_invalid(fixture)

    def test_previous_cycle_label_cannot_date_a_new_handoff(self):
        fixture = LabelFixture(cycles=1)
        fixture.history[-1]["created_at"] = stamp(80)
        self.assert_invalid(fixture)

    def test_human_owned_delivery_block_can_wait_for_authorized_ready_label(self):
        for additive in (False, True):
            with self.subTest(additive=additive):
                fixture = LabelFixture(additive=additive)
                fixture.step(Event.BLOCKED, State.BLOCKED, at=stamp(65),
                             actor=Actor.HUMAN, phase=Phase.DELIVERY_EVIDENCE)
                fixture.publish_comments()
                fixture.issue["body"] = update_issue_body("", fixture.state)
                fixture.issue["labels"] = [{"name": READY_LABEL}]
                if additive:
                    fixture.issue["labels"].append({"name": STATE_LABELS[State.BLOCKED.value]})
                self.assert_pending(fixture)

    def test_decomposition_handoff_can_wait_for_authorized_ready_label(self):
        for additive in (False, True):
            with self.subTest(additive=additive):
                self.assert_pending(LabelFixture(additive=additive, decomposition=True))

    def test_unrelated_activity_does_not_renew_expired_authority(self):
        fixture = LabelFixture()
        fixture.issue["updated_at"] = stamp(700)
        with patch.object(store, "pending_transition_now", lambda: BASE + dt.timedelta(seconds=681)):
            self.assert_invalid(fixture)

    def test_pending_converges_to_one_exact_ready_workflow(self):
        fixture = LabelFixture(cycles=1, additive=True)
        self.assert_pending(fixture)
        fixture.step(Event.HUMAN_VALIDATION_PASSED, State.AGENT_READY,
                     at=stamp(200), actor=Actor.HUMAN, phase=Phase.DELIVERY_EVIDENCE,
                     details={"tested_commit": "b" * 40})
        fixture.publish_comments()
        fixture.issue["body"] = update_issue_body("", fixture.state)
        fixture.issue["labels"] = [{"name": READY_LABEL}]
        for _ in range(2):
            snapshot = fixture.snapshot()
            self.assertTrue(snapshot.valid, snapshot.reasons)
            self.assertIsNone(snapshot.pending_transition)
            ready = fixture.service().list_agent_ready()
            self.assertEqual(len(ready), 1)
            self.assertEqual(ready[0]["workflow_state"]["last_event_id"], fixture.state.last_event_id)
            self.assertEqual(ready[0]["last_event_id"], fixture.state.last_event_id)


@unittest.skipUnless(
    callable(getattr(store, "_expired_pending_workflow_write", None)),
    "candidate-only expiry diagnostic API; paired parent behavior is covered by consumer regressions",
)
class CandidateExpiryDiagnosticTests(unittest.TestCase):
    """Guard-only unit cohort, distinct from the behaviorally red F5 tests.

    The parent implementation has no diagnostic API, so this cohort is
    explicitly skipped there rather than reporting missing-API setup errors.
    Queue-level expiry regressions exercise the actual parent behavior.
    """

    def check(self, options, mutate=None, now=1000):
        fixture = HumanFixture(**options)
        if mutate:
            mutate(fixture)
        with patch.object(store, "pending_transition_now", lambda: BASE + dt.timedelta(seconds=now)):
            snapshot = fixture.snapshot()
            expired = store._expired_pending_workflow_write(fixture.backend, fixture.issue, snapshot)
        return snapshot, expired

    def test_expired_label_open_write_and_closed_prefix_preserve_fatal(self):
        for options in ({"label_first": True}, {}, {"closed": True}):
            with self.subTest(options=options):
                snapshot, expired = self.check(options)
                self.assertFalse(snapshot.valid)
                self.assertIsNone(snapshot.pending_transition)
                self.assertTrue(expired)

    def test_recent_pending_never_becomes_expired(self):
        for options in ({"label_first": True}, {}, {"closed": True}):
            with self.subTest(options=options):
                snapshot, expired = self.check(options, now=180)
                self.assertIsNotNone(snapshot.pending_transition)
                self.assertFalse(expired)

    def test_invalid_label_actor_cannot_be_proven_expiry(self):
        def corrupt(fixture):
            fixture.backend.issue_events[fixture.number][0]["actor"] = {"login": "outside-user"}
        for options in ({"label_first": True}, {}, {"closed": True}):
            with self.subTest(options=options):
                snapshot, expired = self.check(options, corrupt)
                self.assertIsNone(snapshot.pending_transition)
                self.assertFalse(expired)

    def test_forged_body_cannot_be_proven_expiry(self):
        def corrupt(fixture):
            fixture.issue["body"] = update_issue_body("", replace(
                fixture.body_state, head_commit="f" * 40, human_handoff_commit="f" * 40))
        for options in ({"label_first": True}, {}, {"closed": True}):
            with self.subTest(options=options):
                snapshot, expired = self.check(options, corrupt)
                self.assertIsNone(snapshot.pending_transition)
                self.assertFalse(expired)

    def test_future_label_time_cannot_be_redated_into_proven_expiry(self):
        def corrupt(fixture):
            fixture.backend.issue_events[fixture.number][0]["created_at"] = stamp(1001)
        for options in ({"label_first": True}, {}, {"closed": True}):
            with self.subTest(options=options):
                snapshot, expired = self.check(options, corrupt)
                self.assertIsNone(snapshot.pending_transition)
                self.assertFalse(expired)


if __name__ == "__main__":
    unittest.main(verbosity=2)
