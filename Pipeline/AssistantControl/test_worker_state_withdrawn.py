"""A settled run whose output `revise-on-source` withdrew is over.

The decisive test is `test_a_run_dispatched_after_the_reconciliation_is_still_live`.
Widening "finished" in the wrong direction lets a gate scope or re-dispatch over a
succeeded crew whose candidate is merely waiting to be harvested, which is exactly
what the exclusion of "succeeded" exists to prevent and is not being softened.

Shaped from the live NSC-048 record, which reached `prepared` with its worker
archived and could still not be dispatched: the stale launch kept `ready_pending`
and the archived run read `succeeded`, so no gate would call it finished.
"""
from __future__ import annotations

import unittest

from Pipeline.AssistantControl.worker_state import (
    finished_run_ids,
    is_finished_launch,
    is_finished_worker,
    is_settled_worker,
    output_was_withdrawn,
)

RECONCILED = "39fdae4529cd84233741eb6877e7e5ca812fb0e4"
OLD_SOURCE = "04d37a7c55edd200870b0f93bc15e8953479aef2"
RUN = "game-agent-nsc048-042825"


def settled(**overrides) -> dict:
    entry = {
        "run_id": RUN,
        "status": "succeeded",
        "capacity_released": True,
        "settled_at": "2026-09-23T04:28:00+00:00",
        "source_head": OLD_SOURCE,
    }
    entry.update(overrides)
    return entry


def reconciled_record(*, worker_history=None, reconciled=RECONCILED,
                      source_commit=RECONCILED, **overrides) -> dict:
    record = {
        "task_id": "NSC-048",
        "status": "prepared",
        "source_commit": source_commit,
        "revise_on_source_history": [{"reconciled_commit": reconciled}],
        "worker_history": [settled()] if worker_history is None else worker_history,
        "launch": {"run_id": RUN, "status": "ready_pending"},
    }
    record.update(overrides)
    return record


class WithdrawnOutputTests(unittest.TestCase):
    def test_a_settled_run_whose_output_was_withdrawn_counts_as_finished(self):
        record = reconciled_record()
        self.assertEqual({RUN}, finished_run_ids(record))

    def test_the_stale_launch_is_recognised_as_finished(self):
        """The live NSC-048 shape. A launch keeps whatever status it had when the
        launcher wrote it, so a finished run leaves `ready_pending` behind."""
        record = reconciled_record()
        self.assertTrue(is_finished_launch(record, record["launch"]))

    def test_a_run_dispatched_after_the_reconciliation_is_still_live(self):
        """The case this must never swallow.

        Its `source_head` IS the reconciled commit, because it was dispatched from
        the reconciled baseline. Nothing else on the record distinguishes it from
        the withdrawn run.
        """
        record = reconciled_record(worker_history=[settled(source_head=RECONCILED)])
        self.assertEqual(set(), finished_run_ids(record))
        self.assertFalse(is_finished_launch(record, record["launch"]))

    def test_settlement_is_never_waived(self):
        """Only the status test is widened. A withdrawn run that has not been
        settled has not proven its process and containers are gone."""
        for missing in ({"capacity_released": False}, {"settled_at": ""}):
            with self.subTest(missing=missing):
                record = reconciled_record(worker_history=[settled(**missing)])
                self.assertEqual(set(), finished_run_ids(record))

    def test_a_record_with_no_reconciliation_is_unchanged(self):
        record = reconciled_record()
        record.pop("revise_on_source_history")
        self.assertEqual(set(), finished_run_ids(record),
                         "a succeeded run is still not finished on an ordinary record")

    def test_a_withdrawal_that_did_not_produce_the_current_baseline_is_ignored(self):
        record = reconciled_record(source_commit="f" * 40)
        self.assertEqual(set(), finished_run_ids(record))

    def test_a_run_with_no_recorded_source_head_is_still_live(self):
        """Absent evidence stays live; the permissive direction would let a gate
        re-dispatch over work that may still be real."""
        entry = settled()
        entry.pop("source_head")
        self.assertEqual(set(), finished_run_ids(reconciled_record(worker_history=[entry])))

    def test_both_archive_shapes_are_read(self):
        """`retire-worker` copies fields to the top level; `worker_launcher` nests
        them under "worker". A run archived by one must count for the other."""
        nested = {"run_id": RUN, "worker": settled()}
        self.assertEqual({RUN}, finished_run_ids(reconciled_record(worker_history=[nested])))

    def test_a_failed_run_still_finishes_without_any_withdrawal(self):
        record = reconciled_record(worker_history=[settled(status="failed")])
        record.pop("revise_on_source_history")
        self.assertEqual({RUN}, finished_run_ids(record))

    def test_is_finished_worker_itself_is_not_widened(self):
        """The status-only predicate has other callers and must not change; the
        withdrawn case is handled where the RECORD is available, not here."""
        self.assertFalse(is_finished_worker(settled()))
        self.assertTrue(is_finished_worker(settled(status="failed")))
        self.assertTrue(is_finished_worker(settled(status="stopped")))

    def test_settlement_and_withdrawal_are_separable(self):
        record = reconciled_record()
        entry = settled()
        self.assertTrue(is_settled_worker(entry))
        self.assertTrue(output_was_withdrawn(record, entry))
        self.assertFalse(output_was_withdrawn(record, settled(source_head=RECONCILED)))
        self.assertFalse(output_was_withdrawn(record, "not a mapping"))


if __name__ == "__main__":
    unittest.main()
