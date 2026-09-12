#!/usr/bin/env python3
"""Pure/component F3 regressions through the real closed-workflow consumers.

Regression-only invariants, not Unity acceptance or delivery evidence. Git and
TaskGraph read boundaries are injected; the store, completed-Issue guard, bulk
observer, resource scanner and default production workflow snapshot path run.
All Issue data is invented in memory. No network or persistent mutation occurs.
NSC_WORKFLOW_CONSUMER_SOURCE selects an unchanged baseline application checkout.
"""

from __future__ import annotations

import os
import sys
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.environ.get(
    "NSC_WORKFLOW_CONSUMER_SOURCE", Path(__file__).resolve().parents[3],
)).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(Path(__file__).resolve().parent))

from Pipeline.TaskReviewAgent import issue_workflow_store as store  # noqa: E402
from Pipeline.TaskReviewAgent import polling_orchestrator as polling  # noqa: E402
from Pipeline.TaskReviewAgent import production_graph_snapshot as producer  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import STATE_LABELS, update_issue_body  # noqa: E402
from Pipeline.TaskReviewAgent.tests import autonomous_graph_run_smoke_test as graph  # noqa: E402
from Pipeline.TaskReviewAgent.tests import production_graph_snapshot_smoke_test as production_fixture  # noqa: E402
from workflow_consumer_fixture import HumanFixture, BASE, stamp, dt  # noqa: E402


class CountingBackend(store.MemoryIssueBackend):
    def __init__(self):
        super().__init__(now=lambda: stamp(0))
        self.comment_reads = []
        self.exact_reads = []

    def get_comments(self, issue_number):
        self.comment_reads.append(issue_number)
        return super().get_comments(issue_number)

    def get_issue(self, issue_number):
        self.exact_reads.append(issue_number)
        return super().get_issue(issue_number)


class ClosedWorkflowConsumerTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(store, "pending_transition_now",
                                      lambda: BASE + dt.timedelta(seconds=180)))
        # Keep the real immediate exact-read path, but no wall-clock backoff.
        # Expiry evidence is dated by the independent frozen workflow clock.
        self.enterContext(patch.object(store, "RESERVATION_CONSISTENCY_DELAYS_SECONDS", (0.0,)))

    def service(self, fixture):
        return store.IssueWorkflowService(backend=fixture.backend,
                                         task_loader=lambda _: fixture.task_data(),
                                         worker_id="closed-consumer-reader")

    @contextmanager
    def read_boundaries(self):
        with patch.object(polling, "is_git_checkout", return_value=False), \
             patch.object(polling, "read_branch_changed_paths", return_value=()):
            yield

    def bulk(self, fixture):
        with self.read_boundaries():
            return polling.observe_durable_workflows(
                source=ROOT, checkout_root=ROOT.parent, worker_id="closed-consumer-reader",
                backend=fixture.backend, task_loader=lambda _: fixture.task_data(),
            )

    def coherent_snapshot(self, fixture):
        manifest = replace(graph.manifest(targets=(fixture.task,)), source_repository=str(ROOT))
        snapshotter = producer.ProductionCoherentSnapshotter(
            manifest=manifest, scheduler=graph.FakeScheduler(), checkout_root=ROOT.parent,
            worker_id="closed-consumer-reader", backend_factory=lambda _: fixture.backend,
            source_refresher=lambda _: {"before": graph.HEAD, "after": graph.HEAD, "changed": False},
        )
        with self.read_boundaries(), \
             patch.object(producer, "_capture_source_identity", return_value=production_fixture.identity()), \
             patch.object(snapshotter, "_task_observations",
                          return_value=(graph.TaskObservation(fixture.task, "conformant"),)), \
             patch.object(producer, "load_committed_task", return_value=fixture.task_data()), \
             patch.object(producer, "_git_text", return_value=graph.TREE), \
             patch.object(producer, "_is_ancestor", return_value=True):
            snapshot = snapshotter()
        return snapshot, graph.evaluate_graph_state(manifest, snapshot)

    def conflicts(self, fixture, *, same_resource=True):
        selected = {"id": "NSC-702", "exclusive_resources": (
            fixture.task_data()["exclusive_resources"] if same_resource
            else ["unity-scene:Assets/Scenes/DisjointFixture.unity"]
        )}
        return self.service(fixture)._resource_conflicts_classified(selected)[0]

    def test_closed_one_and_two_event_prefixes_reach_per_task_history(self):
        for length in (1, 2):
            with self.subTest(prefix_length=length):
                fixture = HumanFixture(backend=CountingBackend(), closed=True,
                                       closed_prefix_length=length)
                self.assertIsNotNone(fixture.snapshot().pending_transition, "fixture must prove a canonical suffix")
                fixture.backend.comment_reads.clear()
                found = self.service(fixture).find(fixture.task)
                self.assertIsNotNone(found, "closed pending body was discarded before history classification")
                self.assertIsNotNone(found.pending_transition)
                self.assertEqual(found.state, fixture.body_state)
                self.assertIn(fixture.number, fixture.backend.comment_reads)
                observed = self.service(fixture).observe(fixture.task)
                self.assertEqual(observed["status"], "conflict")
                self.assertIsNotNone(observed["pending_transition"])
                self.assertEqual(self.service(fixture).list_agent_ready(), [])

    def test_closed_prefixes_remain_bulk_reservations(self):
        for length in (1, 2):
            with self.subTest(prefix_length=length):
                fixture = HumanFixture(closed=True, closed_prefix_length=length)
                observed = self.bulk(fixture)
                self.assertEqual([item.state.task_id for item in observed.snapshots], [fixture.task])
                self.assertEqual([item.task_id for item in observed.reservations], [fixture.task])
                self.assertEqual(observed.reservations[0].exclusive_resources,
                                 tuple(fixture.task_data()["exclusive_resources"]))
                self.assertIsNotNone(observed.reservations[0].pending_transition)

    def test_closed_prefixes_block_only_known_overlapping_resources(self):
        for length in (1, 2):
            with self.subTest(prefix_length=length):
                fixture = HumanFixture(closed=True, closed_prefix_length=length)
                self.assertTrue(self.conflicts(fixture), "pending closed workflow released its scene")
                self.assertEqual(self.conflicts(fixture, same_resource=False), [])

    def test_default_production_snapshot_waits_for_closed_prefixes(self):
        for length in (1, 2):
            with self.subTest(prefix_length=length):
                fixture = HumanFixture(closed=True, closed_prefix_length=length)
                snapshot, evaluation = self.coherent_snapshot(fixture)
                self.assertEqual(snapshot.pending_transition_task_ids, (fixture.task,))
                self.assertEqual(snapshot.reservation_task_ids, (fixture.task,))
                self.assertEqual(evaluation.classification, "temporary_wait")

    def test_coherent_completion_releases_reservation_without_losing_terminal_issue(self):
        fixture = HumanFixture(closed=True, coherent=True)
        found = self.service(fixture).find(fixture.task)
        self.assertIsNotNone(found)
        self.assertTrue(found.valid)
        self.assertEqual(found.state, fixture.state)
        observed = self.bulk(fixture)
        self.assertEqual(len(observed.snapshots), 1)
        self.assertEqual(observed.reservations, ())
        self.assertEqual(self.conflicts(fixture), [])
        snapshot, evaluation = self.coherent_snapshot(fixture)
        self.assertEqual(snapshot.pending_transition_task_ids, ())
        self.assertEqual(snapshot.reservation_task_ids, ())
        self.assertEqual(evaluation.classification, "complete")

    def test_complete_body_with_pending_label_write_still_reserves_resources(self):
        fixture = HumanFixture(closed=True)
        fixture.issue["body"] = update_issue_body("", fixture.state)
        self.assertIsNotNone(fixture.snapshot().pending_transition)
        observed = self.bulk(fixture)
        self.assertEqual([item.task_id for item in observed.reservations], [fixture.task])
        self.assertTrue(self.conflicts(fixture))
        snapshot, evaluation = self.coherent_snapshot(fixture)
        self.assertEqual(snapshot.pending_transition_task_ids, (fixture.task,))
        self.assertEqual(snapshot.reservation_task_ids, (fixture.task,))
        self.assertEqual(evaluation.classification, "temporary_wait")

    def test_expired_completion_prefix_is_fatal_not_absent_or_complete(self):
        for length in (1, 2):
            with self.subTest(prefix_length=length):
                fixture = HumanFixture(closed=True, closed_prefix_length=length)
                with patch.object(store, "pending_transition_now",
                                  lambda: BASE + dt.timedelta(seconds=741)):
                    self.assertIsNone(fixture.snapshot().pending_transition)
                    found = self.service(fixture).find(fixture.task)
                    self.assertIsNotNone(found, "expired completion disappeared from per-task authority")
                    self.assertFalse(found.valid)
                    self.assertEqual(self.service(fixture).observe(fixture.task)["status"], "conflict")
                    self.assertTrue(self.conflicts(fixture, same_resource=False))
                    with self.assertRaises(polling.IntegrationObservationError):
                        self.bulk(fixture)
                    with self.assertRaises(producer.ProductionGraphSnapshotError):
                        self.coherent_snapshot(fixture)

    def test_expired_closed_prefix_survives_the_real_exact_retry(self):
        fixture = HumanFixture(backend=CountingBackend(), closed=True)
        with patch.object(store, "pending_transition_now", lambda: BASE + dt.timedelta(seconds=741)):
            entries = store._consistent_snapshots(fixture.backend, [fixture.issue])
        self.assertEqual(fixture.backend.exact_reads, [fixture.number])
        self.assertEqual(len(entries), 1)
        self.assertIsNotNone(entries[0].snapshot, "exact CLOSED read erased supported completion authority")
        self.assertFalse(entries[0].snapshot.valid)
        self.assertIsNone(entries[0].snapshot.pending_transition)

    def test_unauthorized_early_or_reopened_close_cannot_hide_completion_corruption(self):
        for mutation in ("unauthorized", "early", "reopened", "duplicate_id"):
            with self.subTest(mutation=mutation):
                fixture = HumanFixture(closed=True)
                history = fixture.backend.issue_events[fixture.number]
                if mutation == "unauthorized":
                    history[-1]["actor"] = {"login": "outside-user"}
                elif mutation == "early":
                    history[-1]["created_at"] = stamp(139)
                elif mutation == "duplicate_id":
                    history[-1]["id"] = history[0]["id"]
                else:
                    fixture.record("reopened", 144)
                self.assertIsNone(fixture.snapshot().pending_transition)
                self.assertIsNotNone(self.service(fixture).find(fixture.task))
                self.assertTrue(self.conflicts(fixture))
                with self.assertRaises(polling.IntegrationObservationError):
                    self.bulk(fixture)

    def test_malformed_trusted_completion_suffix_is_fatal(self):
        fixture = HumanFixture(closed=True)
        fixture.backend.comments[fixture.number][-1]["body"] = "<!-- nsc-workflow-event\n{broken}\n-->"
        found = self.service(fixture).find(fixture.task)
        self.assertIsNotNone(found)
        self.assertFalse(found.valid)
        self.assertIsNone(found.pending_transition)
        self.assertTrue(self.conflicts(fixture, same_resource=False))
        with self.assertRaises(polling.IntegrationObservationError):
            self.bulk(fixture)
        with self.assertRaises(producer.ProductionGraphSnapshotError):
            self.coherent_snapshot(fixture)

    def test_historical_closed_implementation_duplicate_is_excluded(self):
        fixture = HumanFixture(backend=CountingBackend(), coherent=True)
        fixture.issue["state"] = "CLOSED"
        fixture.issue["body"] = update_issue_body("", fixture.implementation_state)
        fixture.issue["labels"] = [{"name": STATE_LABELS["agent_working"]}]
        fixture.backend.comments[fixture.number] = fixture.backend.comments[fixture.number][:1]
        self.assertIsNone(self.service(fixture).find(fixture.task))
        self.assertEqual(self.bulk(fixture).snapshots, ())
        self.assertEqual(self.conflicts(fixture), [])
        self.assertEqual(fixture.backend.comment_reads, [])

    def test_coherent_closed_incomplete_duplicate_is_not_completion(self):
        fixture = HumanFixture(coherent=True)
        fixture.issue["state"] = "CLOSED"
        self.assertTrue(fixture.snapshot().valid)
        self.assertIsNone(self.service(fixture).find(fixture.task))
        self.assertEqual(self.bulk(fixture).snapshots, ())
        self.assertEqual(self.conflicts(fixture), [])

    def test_unauthorized_closed_imitations_never_gain_ownership(self):
        fixture = HumanFixture(backend=CountingBackend(), closed=True)
        fixture.issue["author"] = {"login": "outside-user"}
        self.assertIsNone(self.service(fixture).find(fixture.task))
        self.assertEqual(self.bulk(fixture).snapshots, ())
        self.assertEqual(self.conflicts(fixture), [])
        self.assertEqual(fixture.backend.comment_reads, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
