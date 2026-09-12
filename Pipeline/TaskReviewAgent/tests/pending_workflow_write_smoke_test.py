#!/usr/bin/env python3
"""Pure/component regressions for bounded GitHub workflow-write visibility.

Regression-only invariants; no Unity acceptance or delivery evidence is produced.
Fixtures use canonical hashed transitions and in-memory GitHub payloads only.
NSC_WORKFLOW_WRITE_SOURCE selects an unchanged application checkout for paired
base/candidate runs. Both the OPEN/no-label and CLOSED/body-prefix cases use
invented canonical events; no historical Issue or delivery artifacts are read.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
import sys
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.environ.get("NSC_WORKFLOW_WRITE_SOURCE", Path(__file__).resolve().parents[3])).resolve()
sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent import issue_workflow_store as store  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    AUTOMATED_VALIDATION_EVIDENCE_AUTHORITY,
    AUTOMATED_VALIDATION_GAUNTLET_ID,
    AUTOMATED_VALIDATION_REPOSITORY,
    STATE_LABELS,
    IssueWorkflowEvent,
    IssueWorkflowState,
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    initial_state,
    labels_for_state,
    parse_events,
    render_event_comment,
    transition,
    update_issue_body,
    validate_event_chain,
)

TASK = "NSC-701"
CONTRACT_HASH = "7" * 64
HEAD = "b" * 40
WORKER = "workflow-write-fixture"
_BASE = dt.datetime(2026, 9, 7, 2, 15, tzinfo=dt.timezone.utc)


def stamp(seconds: float) -> str:
    return (_BASE + dt.timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


@contextmanager
def frozen_clock(seconds: float = 180):
    with patch.object(store, "pending_transition_now", lambda: _BASE + dt.timedelta(seconds=seconds)):
        yield


class WorkflowWriteFixture:
    """An authenticated workflow write whose label list has not converged."""

    def __init__(self, *, closed: bool = False, target_labeled: bool = False,
                 handoff_at: float = 60):
        self.backend = store.MemoryIssueBackend(now=lambda: stamp(0))
        self.backend.repository = AUTOMATED_VALIDATION_REPOSITORY
        self.backend.next_issue = 7
        self.events = []
        state = initial_state(task_id=TASK, task_contract_sha256=CONTRACT_HASH, now=stamp(0))
        self.initial_state = state
        state = self.advance(state, WorkflowEventType.AGENT_LEASE_ACQUIRED,
                             WorkflowState.AGENT_WORKING, at=10,
                             details={"worker_id": WORKER, "lease_id": "1" * 64})
        state = self.advance(state, WorkflowEventType.HUMAN_HANDOFF_CREATED,
                             WorkflowState.HUMAN_ACTION_REQUIRED, at=handoff_at,
                             phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
                             details={"branch": "nsc-701-workflow-write-fixture",
                                      "head_commit": HEAD,
                                      "checkout_path": "C:/offline-fixture/NSC-701"})
        self.handoff_state = state
        evidence = {
            "schema_version": "1.0",
            "authority": AUTOMATED_VALIDATION_EVIDENCE_AUTHORITY,
            "repository": AUTOMATED_VALIDATION_REPOSITORY,
            "repository_private": True,
            "gauntlet_id": AUTOMATED_VALIDATION_GAUNTLET_ID,
            "task_id": TASK,
            "handoff_event_id": state.last_event_id,
            "branch": state.branch,
            "commit": HEAD,
            "tree": "c" * 40,
            "task_contract_sha256": CONTRACT_HASH,
            "validation_policy_authority": "committed_private_synthetic_gauntlet_validation_policy",
            "validation_policy_sha256": "4" * 64,
            "required_validations": [{"test_platform": "EditMode", "test_filter": "Fixture.ExactTest"}],
            "unity_validations": [{
                "test_platform": "EditMode", "test_filter": "Fixture.ExactTest",
                "manifest_sha256": "5" * 64, "xml_sha256": "6" * 64, "log_sha256": "7" * 64,
                "commit": HEAD, "tree": "c" * 40, "post_commit": HEAD, "post_tree": "c" * 40,
                "repository_clean_before": True, "repository_clean_after": True,
                "total": 1, "passed": 1, "failed": 0, "skipped": 0,
            }],
        }
        state = self.advance(state, WorkflowEventType.AUTOMATED_VALIDATION_PASSED,
                             WorkflowState.AGENT_READY, at=120,
                             phase=WorkflowPhase.DELIVERY_EVIDENCE, details=evidence)
        self.state = state
        self.final_state = state
        self.removed_label = STATE_LABELS[WorkflowState.HUMAN_ACTION_REQUIRED.value]
        self.removed_at = 121
        if closed:
            state = self.advance(state, WorkflowEventType.AGENT_LEASE_ACQUIRED,
                                 WorkflowState.AGENT_WORKING, at=130,
                                 phase=WorkflowPhase.MERGE_CLOSEOUT,
                                 details={"worker_id": WORKER, "lease_id": "2" * 64})
            self.working_state = state
            self.final_state = self.advance(
                state, WorkflowEventType.COMPLETED, WorkflowState.COMPLETE, at=140,
                phase=WorkflowPhase.MERGE_CLOSEOUT,
                details={"pull_request_url": "https://example.invalid/pull/8",
                         "pull_request_number": 8, "merged_commit": "d" * 40,
                         "conformant_record_id": "DEL-NSC-701-fixture"})
            self.removed_label = STATE_LABELS[WorkflowState.AGENT_WORKING.value]
            self.removed_at = 141
        validate_event_chain(self.state, self.events[:self.state.state_version])
        validate_event_chain(self.final_state, self.events)
        created = self.backend.create_issue(
            title=f"{TASK} — Verify a bounded workflow write",
            body=update_issue_body(f"<!-- nsc-task:{TASK} -->", self.state),
            labels=[], assignees=["cathode26"])
        self.issue_number = created["number"]
        self.issue["state"] = "CLOSED" if closed else "OPEN"
        self.issue["updated_at"] = stamp(179)
        for event in self.events:
            self.backend.add_comment(self.issue_number, render_event_comment(event, "Offline fixture transition."))
        self.record("unlabeled", self.removed_at, label=self.removed_label)
        if target_labeled:
            self.record("labeled", self.removed_at + 1,
                        label=STATE_LABELS[self.final_state.state.value])
        if closed:
            self.record("closed", 143)

    @property
    def issue(self):
        return self.backend.issues[self.issue_number]

    @property
    def history(self):
        return self.backend.issue_events[self.issue_number]

    def advance(self, state, kind, target, *, at, phase=None, details=None):
        result, event = transition(state, event_type=kind, actor_type=WorkflowActor.AGENT,
                                   actor_id=WORKER, to_state=target, to_phase=phase,
                                   details=details or {}, now=stamp(at))
        self.events.append(event)
        return result

    def record(self, kind, at, *, label=None, actor="cathode26"):
        event = {"id": 1000 + len(self.history), "event": kind,
                 "created_at": stamp(at), "actor": {"login": actor}}
        if label is not None:
            event["label"] = {"name": label}
        self.history.append(event)
        return event

    def snapshot(self):
        return store._snapshot(self.backend, self.backend.get_issue(self.issue_number))

    def replace_event(self, index, event):
        self.events[index] = event
        self.backend.comments[self.issue_number][index]["body"] = render_event_comment(event, "Offline fixture transition.")


class SixEventWorkflowWriteFixture(WorkflowWriteFixture):
    """Two exact validation rounds, entirely invented and canonically hashed.

    Retain the six-event replay and stale no-label observation regression without
    shipping private Issue comments, run paths, commit hashes, or live evidence.
    """

    def __init__(self):
        super().__init__(target_labeled=True)
        state = self.advance(self.state, WorkflowEventType.AGENT_LEASE_ACQUIRED,
                             WorkflowState.AGENT_WORKING, at=130,
                             phase=WorkflowPhase.DELIVERY_EVIDENCE,
                             details={"worker_id": WORKER, "lease_id": "2" * 64})
        state = self.advance(state, WorkflowEventType.HUMAN_HANDOFF_CREATED,
                             WorkflowState.HUMAN_ACTION_REQUIRED, at=160,
                             phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
                             details={"branch": "nsc-701-workflow-write-fixture",
                                      "head_commit": "e" * 40,
                                      "checkout_path": "C:/offline-fixture/NSC-701"})
        evidence = copy.deepcopy(self.events[2].details)
        evidence.update(handoff_event_id=state.last_event_id, commit="e" * 40, tree="f" * 40)
        evidence["unity_validations"][0].update(
            commit="e" * 40, post_commit="e" * 40, tree="f" * 40, post_tree="f" * 40)
        self.state = self.final_state = self.advance(
            state, WorkflowEventType.AUTOMATED_VALIDATION_PASSED,
            WorkflowState.AGENT_READY, at=170,
            phase=WorkflowPhase.DELIVERY_EVIDENCE, details=evidence)
        validate_event_chain(self.state, self.events)
        self.issue["body"] = update_issue_body("", self.state)
        self.backend.comments[self.issue_number] = [
            {"author": {"login": "cathode26"},
             "body": render_event_comment(event, "Invented six-event fixture.")}
            for event in self.events
        ]
        for kind, at, label in (
            ("unlabeled", 131, "agent_ready"),
            ("labeled", 132, "agent_working"),
            ("unlabeled", 161, "agent_working"),
            ("labeled", 162, "human_action_required"),
            ("unlabeled", 171, "human_action_required"),
            ("labeled", 172, "agent_ready"),
        ):
            self.record(kind, at, label=STATE_LABELS[label])
        self.observed_at = _BASE + dt.timedelta(seconds=188.25)

    @contextmanager
    def frozen_clock(self):
        with patch.object(store, "pending_transition_now", lambda: self.observed_at):
            yield

    def snapshot(self):
        return store._snapshot(self.backend, self.backend.get_issue(self.issue_number))


class PendingWorkflowWriteTests(unittest.TestCase):
    def assert_pending(self, fixture, *, now=180):
        original = copy.deepcopy(fixture.issue)
        with frozen_clock(now):
            snapshot = fixture.snapshot()
        self.assertIsNotNone(snapshot.pending_transition, snapshot.reasons)
        self.assertFalse(snapshot.valid)
        self.assertEqual(snapshot.state, fixture.state, "pending recognition rewrote body authority")
        self.assertEqual(snapshot.body, original["body"])
        self.assertEqual(fixture.issue, original, "read-only classification mutated Issue")
        self.assertEqual(snapshot.pending_transition.to_state, fixture.final_state.state)
        self.assertEqual(snapshot.pending_transition.target_label, STATE_LABELS[fixture.final_state.state.value])
        self.assertLessEqual(snapshot.pending_transition.age_seconds, 600)
        return snapshot

    def assert_rejected(self, fixture, *, now=180):
        with frozen_clock(now):
            snapshot = fixture.snapshot()
        self.assertIsNone(snapshot.pending_transition, snapshot.to_dict())
        self.assertFalse(snapshot.valid)
        return snapshot

    def test_recent_exact_automated_ready_write_is_pending(self):
        snapshot = self.assert_pending(WorkflowWriteFixture())
        self.assertIsNone(snapshot.state.human_result, "machine evidence invented human PASS")
        self.assertEqual(snapshot.state.phase, WorkflowPhase.DELIVERY_EVIDENCE)

    def test_label_already_applied_with_stale_no_label_listing_is_pending(self):
        self.assert_pending(WorkflowWriteFixture(target_labeled=True))

    def test_six_event_revalidation_is_pending_at_no_label_observation(self):
        fixture = SixEventWorkflowWriteFixture()
        expected_event = "6badd63093a3061f5b6359b781bb1c1932f43189fe8c597dfe9d48611e875d0e"
        self.assertEqual(len(fixture.events), 6)
        self.assertEqual(fixture.events[-1].event_id, expected_event)
        self.assertEqual(fixture.events[-1].occurred_at_utc, stamp(170))
        self.assertEqual(fixture.state.last_event_id, expected_event)
        self.assertEqual(fixture.state.state_version, 6)
        self.assertIsNone(fixture.state.human_result)
        original = copy.deepcopy(fixture.issue)
        with fixture.frozen_clock():
            snapshot = fixture.snapshot()
        self.assertIsNotNone(snapshot.pending_transition, snapshot.reasons)
        self.assertFalse(snapshot.valid)
        self.assertEqual(snapshot.state, fixture.state)
        self.assertEqual(snapshot.body, original["body"])
        self.assertEqual(fixture.issue, original)
        pending = snapshot.pending_transition
        self.assertEqual(pending.workflow_event_id, expected_event)
        self.assertEqual(pending.label_event_type, "unlabeled")
        self.assertEqual(pending.label_event_id, 1006)
        self.assertEqual(pending.label_applied_at_utc, stamp(171))
        self.assertEqual(pending.to_state, WorkflowState.AGENT_READY)
        self.assertEqual(pending.age_seconds, 18.25)

    def test_closed_body_prefix_and_verified_completion_suffix_is_pending(self):
        self.assert_pending(WorkflowWriteFixture(closed=True))

    def test_closed_body_prefix_with_complete_label_event_is_pending(self):
        self.assert_pending(WorkflowWriteFixture(closed=True, target_labeled=True))

    def test_closed_body_one_event_behind_is_pending(self):
        fixture = WorkflowWriteFixture(closed=True)
        fixture.state = fixture.working_state
        fixture.issue["body"] = update_issue_body(fixture.issue["body"], fixture.state)
        self.assert_pending(fixture)

    def test_pending_window_includes_exact_boundary(self):
        self.assert_pending(WorkflowWriteFixture(), now=720)

    def test_pending_ready_is_not_admitted_and_spends_no_consistency_sleep(self):
        fixture = WorkflowWriteFixture()
        service = store.IssueWorkflowService(backend=fixture.backend,
                                             task_loader=lambda _: {}, worker_id=WORKER)
        before = copy.deepcopy((fixture.backend.issues, fixture.backend.comments, fixture.history))
        with frozen_clock(), patch.object(store.time, "sleep") as sleep:
            self.assertEqual(service.list_agent_ready(), [])
        sleep.assert_not_called()
        self.assertEqual((fixture.backend.issues, fixture.backend.comments, fixture.history), before)

    def test_expired_workflow_event_cannot_be_renewed_by_new_label_activity(self):
        fixture = WorkflowWriteFixture()
        fixture.history[0]["created_at"] = stamp(721)
        fixture.issue["updated_at"] = stamp(721)
        self.assert_rejected(fixture, now=721)

    def test_expired_label_removal_cannot_be_renewed_by_unrelated_activity(self):
        fixture = WorkflowWriteFixture()
        fixture.issue["updated_at"] = stamp(900)
        self.assert_rejected(fixture, now=900)

    def test_missing_removal_evidence_fails_closed(self):
        fixture = WorkflowWriteFixture()
        fixture.history.clear()
        self.assert_rejected(fixture)

    def test_target_application_without_source_removal_is_unprovable(self):
        fixture = WorkflowWriteFixture(target_labeled=True)
        fixture.history.pop(0)
        self.assert_rejected(fixture)

    def test_future_or_pretransition_removal_fails_closed(self):
        for at in (181, 119):
            with self.subTest(at=at):
                fixture = WorkflowWriteFixture()
                fixture.history[0]["created_at"] = stamp(at)
                self.assert_rejected(fixture)

    def test_missing_malformed_or_unauthorized_label_identity_fails_closed(self):
        for field, value in (("id", True), ("id", 0), ("created_at", "bad-time"),
                             ("actor", {}), ("actor", {"login": "outside-user"})):
            with self.subTest(field=field, value=value):
                fixture = WorkflowWriteFixture()
                fixture.history[0][field] = value
                self.assert_rejected(fixture)

    def test_later_contradictory_label_event_fails_closed(self):
        for kind, label in (("unlabeled", STATE_LABELS["agent_ready"]),
                            ("labeled", STATE_LABELS["blocked"]),
                            ("labeled", STATE_LABELS["human_action_required"])):
            with self.subTest(kind=kind, label=label):
                fixture = WorkflowWriteFixture(target_labeled=True)
                fixture.record(kind, 123, label=label)
                self.assert_rejected(fixture)

    def test_earlier_contradictory_label_cannot_hide_behind_expected_removal(self):
        fixture = WorkflowWriteFixture(target_labeled=True)
        fixture.record("labeled", 119, label=STATE_LABELS["blocked"])
        self.assert_rejected(fixture)

    def test_nonempty_wrong_labels_do_not_use_missing_label_exception(self):
        fixture = WorkflowWriteFixture()
        fixture.issue["labels"] = [{"name": STATE_LABELS["blocked"]}]
        self.assert_rejected(fixture)

    def test_malformed_authorized_comment_fails_closed(self):
        fixture = WorkflowWriteFixture()
        fixture.backend.add_comment(fixture.issue_number, "<!-- nsc-workflow-event\n{bad-json}\n-->")
        self.assert_rejected(fixture)

    def test_forged_authorized_event_hash_fails_closed(self):
        fixture = WorkflowWriteFixture()
        comment = fixture.backend.comments[fixture.issue_number][-1]
        comment["body"] = comment["body"].replace(fixture.events[-1].event_id, "0" * 64)
        self.assert_rejected(fixture)

    def test_malformed_authorized_body_fails_closed(self):
        fixture = WorkflowWriteFixture()
        fixture.issue["body"] += "\n<!-- nsc-workflow-state\n{}\n-->"
        self.assert_rejected(fixture)

    def test_future_hashed_workflow_event_fails_closed(self):
        fixture = WorkflowWriteFixture()
        payload = fixture.events[-1].identity_payload()
        payload["occurred_at_utc"] = stamp(181)
        event = IssueWorkflowEvent.create(**payload)
        fixture.replace_event(-1, event)
        fixture.state = replace(fixture.state, last_event_id=event.event_id, updated_at_utc=stamp(181))
        fixture.issue["body"] = update_issue_body(fixture.issue["body"], fixture.state)
        self.assert_rejected(fixture)

    def test_contradictory_body_commit_is_not_pending(self):
        fixture = WorkflowWriteFixture()
        fixture.state = replace(fixture.state, head_commit="e" * 40)
        fixture.issue["body"] = update_issue_body(fixture.issue["body"], fixture.state)
        self.assert_rejected(fixture)

    def test_version_zero_body_cannot_skip_exact_body_comparison(self):
        fixture = WorkflowWriteFixture()
        fixture.state = replace(fixture.initial_state, branch="forged-branch", head_commit="e" * 40)
        fixture.events = fixture.events[:2]
        fixture.backend.comments[fixture.issue_number] = fixture.backend.comments[fixture.issue_number][:2]
        fixture.issue["body"] = update_issue_body(fixture.issue["body"], fixture.state)
        fixture.history.clear()
        fixture.record("unlabeled", 61, label=STATE_LABELS["agent_working"])
        self.assert_rejected(fixture)

    def test_future_or_nonmonotonic_hashed_predecessor_fails_closed(self):
        for at in (130, 181):
            with self.subTest(at=at):
                self.assert_rejected(WorkflowWriteFixture(handoff_at=at))

    def test_timezone_missing_label_timestamp_is_unprovable(self):
        fixture = WorkflowWriteFixture()
        fixture.history[0]["created_at"] = stamp(121).removesuffix("Z")
        self.assert_rejected(fixture)

    def test_timezone_missing_workflow_timestamp_is_unprovable(self):
        fixture = WorkflowWriteFixture()
        payload = fixture.events[-1].identity_payload()
        payload["occurred_at_utc"] = stamp(120).removesuffix("Z")
        event = IssueWorkflowEvent.create(**payload)
        fixture.replace_event(-1, event)
        fixture.state = replace(fixture.state, last_event_id=event.event_id,
                                updated_at_utc=event.occurred_at_utc)
        fixture.issue["body"] = update_issue_body(fixture.issue["body"], fixture.state)
        self.assert_rejected(fixture)

    def test_unauthorized_issue_never_becomes_pending(self):
        fixture = WorkflowWriteFixture()
        fixture.issue["author"] = {"login": "outside-user"}
        self.assert_rejected(fixture)

    def test_closed_without_completed_suffix_fails_closed(self):
        fixture = WorkflowWriteFixture()
        fixture.issue["state"] = "CLOSED"
        fixture.record("closed", 143)
        self.assert_rejected(fixture)

    def test_closed_requires_recent_trusted_close_event(self):
        for value in (None, {"actor": {"login": "outside-user"}},
                      {"created_at": stamp(139)}, {"created_at": stamp(181)}):
            with self.subTest(value=value):
                fixture = WorkflowWriteFixture(closed=True)
                if value is None:
                    fixture.history.pop()
                else:
                    fixture.history[-1].update(value)
                self.assert_rejected(fixture)

    def test_closed_forked_suffix_fails_closed(self):
        fixture = WorkflowWriteFixture(closed=True)
        fixture.backend.comments[fixture.issue_number].append(
            copy.deepcopy(fixture.backend.comments[fixture.issue_number][-1]))
        self.assert_rejected(fixture)

    def test_duplicate_contradictory_close_identity_fails_closed(self):
        fixture = WorkflowWriteFixture(closed=True)
        duplicate = copy.deepcopy(fixture.history[-1])
        duplicate["event"] = "reopened"
        fixture.history.append(duplicate)
        self.assert_rejected(fixture)

    def test_more_than_two_unobserved_body_transitions_fail_closed(self):
        fixture = WorkflowWriteFixture(closed=True)
        fixture.state = fixture.handoff_state
        fixture.issue["body"] = update_issue_body(fixture.issue["body"], fixture.state)
        self.assert_rejected(fixture)

    def test_hash_valid_but_illegal_suffix_fails_closed(self):
        fixture = WorkflowWriteFixture(closed=True)
        payload = fixture.events[-1].identity_payload()
        payload["actor_type"] = WorkflowActor.HUMAN.value
        fixture.replace_event(-1, IssueWorkflowEvent.create(**payload))
        self.assert_rejected(fixture)

    def test_completed_suffix_cannot_name_a_worker_without_the_lease(self):
        fixture = WorkflowWriteFixture(closed=True)
        payload = fixture.events[-1].identity_payload()
        payload["actor_id"] = "foreign-worker"
        fixture.replace_event(-1, IssueWorkflowEvent.create(**payload))
        self.assert_rejected(fixture)

    def test_lease_suffix_actor_must_match_named_worker(self):
        fixture = WorkflowWriteFixture(closed=True)
        lease_payload = fixture.events[-2].identity_payload()
        lease_payload["actor_id"] = "foreign-worker"
        lease = IssueWorkflowEvent.create(**lease_payload)
        fixture.replace_event(-2, lease)
        completed_payload = fixture.events[-1].identity_payload()
        completed_payload["previous_event_id"] = lease.event_id
        fixture.replace_event(-1, IssueWorkflowEvent.create(**completed_payload))
        self.assert_rejected(fixture)

    def test_settled_closed_complete_retains_complete_label(self):
        fixture = WorkflowWriteFixture(closed=True)
        fixture.issue["body"] = update_issue_body(fixture.issue["body"], fixture.final_state)
        fixture.issue["labels"] = [{"name": name} for name in labels_for_state(WorkflowState.COMPLETE)]
        with frozen_clock():
            snapshot = fixture.snapshot()
        self.assertTrue(snapshot.valid, snapshot.reasons)
        self.assertIsNone(snapshot.pending_transition)
        self.assertEqual(snapshot.labels, (STATE_LABELS["complete"],))
        validate_event_chain(snapshot.state, parse_events(fixture.backend.get_comments(fixture.issue_number)))


if __name__ == "__main__":
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import synthetic_fixture_authority
    with synthetic_fixture_authority():
        unittest.main(verbosity=2)
