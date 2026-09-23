"""Admitting a record that `revise-on-source` reconciled with Source.

The decisive pair is `test_a_reconciliation_survives_source_moving_on` and
`test_a_reconciliation_beside_the_main_line_is_refused`. A reconciliation is a
MERGE of the rejected candidate and Source, so it can never equal Source HEAD;
the question is not whether it lags but whether it lags ON the main line. Getting
that pair wrong in the strict direction makes every reconciliation unrecoverable,
because `revise-on-source` archives the candidate and cannot be run twice.

Every case builds throwaway repositories through the reopen fixture. Nothing
here reads or writes live pipeline state.
"""
from __future__ import annotations

import json
import types
import unittest
from pathlib import Path

from Pipeline.AssistantControl import test_materialization_reopen as fixture
from Pipeline.AssistantControl.admission import (
    _reconciled_source_commit,
    _revise_on_source_baseline,
)
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.revise_on_source import revise_on_source
from Pipeline.AssistantControl.test_revise_on_source import ReviseOnSourceTests

TASK = "NSC-046"


class AdmissionReviseOnSourceTests(ReviseOnSourceTests):
    """Reuses the reconciliation fixture so every record here is a real merge."""

    def source_head(self) -> str:
        return self.git(self.source, "rev-parse", "HEAD")

    def checkouts(self):
        # Only `source` is read by the baseline helper; the record carries its
        # own checkout path.
        return types.SimpleNamespace(source=self.source)

    def reconcile(self) -> dict:
        """Apply a real reconciliation and return the resulting record."""
        candidate, head, contract = self.frozen_pair()
        revise_on_source(
            self.manager, TASK, expected_candidate=candidate,
            expected_source_commit=head, accept_contract_sha256=contract,
            reason="a crew pass is needed against the current contract", apply=True)
        return self.record()

    def baseline(self, record=None, head=None):
        return _revise_on_source_baseline(
            self.checkouts(), record or self.record(), head or self.source_head())

    def test_a_reconciled_record_yields_its_reconciled_commit(self):
        record = self.reconcile()
        self.assertEqual(record["source_commit"], self.baseline(record))

    def test_the_reconciled_commit_is_what_the_scope_pin_must_match(self):
        """Admission's second guard compares the scope pin to this baseline, so a
        baseline the pin cannot match would refuse just as hard as no baseline."""
        record = self.reconcile()
        self.assertEqual(record["source_commit"], self.baseline(record),
                         "the pin and the baseline must be the same commit")

    def test_a_record_with_no_reconciliation_yields_no_baseline(self):
        """The ordinary admission path must be left exactly as it was."""
        self.make_failed_record()
        self.assertIsNone(self.baseline())

    def test_a_reconciliation_survives_source_moving_on(self):
        """The property the whole design turns on.

        `revise-on-source` archives the rejected candidate and pops it, so it
        cannot be run again. If a reconciliation expired when Source moved, it
        would be UNRECOVERABLE -- and Source moves constantly.
        """
        record = self.reconcile()
        for _ in range(3):
            self.advance_source(revise_contract=False)

        moved = self.source_head()
        self.assertNotEqual(moved, record["source_commit"])
        self.assertEqual(record["source_commit"], self.baseline(record, moved),
                         "a reconciliation that lags Source is still admissible")

    def test_a_reconciliation_beside_the_main_line_is_refused(self):
        """Lagging is fine; sitting on a commit Source never had is not."""
        record = self.reconcile()
        # A real commit that exists in the repository but is not an ancestor of
        # HEAD, which is exactly the shape a rewritten or foreign base would have.
        self.git(self.source, "branch", "sideline")
        head_before = self.source_head()
        self.git(self.source, "checkout", "-q", "sideline")
        self.advance_source(revise_contract=False)
        sideline = self.source_head()
        self.git(self.source, "checkout", "-q", "-")
        self.assertEqual(head_before, self.source_head(), "HEAD must be back where it was")

        record["revise_on_source_history"][-1]["inspected_source_commit"] = sideline
        with self.assertRaisesRegex(ValueError, "not an\\s+ancestor of current Source HEAD"):
            self.baseline(record)

    def test_a_recorded_source_commit_is_used_instead_of_deriving_one(self):
        record = self.reconcile()
        entry = record["revise_on_source_history"][-1]
        self.assertTrue(entry.get("inspected_source_commit"),
                        "new entries must record the Source they merged")
        self.assertEqual(
            entry["inspected_source_commit"],
            _reconciled_source_commit(self.checkouts(), record, entry,
                                      record["source_commit"]))

    def test_an_entry_without_a_recorded_source_falls_back_to_the_merge(self):
        """The first reconciliations predate the field and must still admit."""
        record = self.reconcile()
        entry = record["revise_on_source_history"][-1]
        recorded = entry.pop("inspected_source_commit")

        self.assertEqual(
            recorded,
            _reconciled_source_commit(self.checkouts(), record, entry,
                                      record["source_commit"]),
            "deriving from the merge must agree with what was recorded")
        self.assertEqual(record["source_commit"], self.baseline(record))

    def test_a_merge_whose_first_parent_is_not_the_candidate_is_refused(self):
        """Parent order is only trustworthy for merges this command made, so the
        assumption is verified rather than assumed."""
        record = self.reconcile()
        entry = record["revise_on_source_history"][-1]
        entry.pop("inspected_source_commit")
        entry["rejected_candidate"] = "0" * 40

        with self.assertRaisesRegex(ValueError, "first parent is not the rejected candidate"):
            self.baseline(record)

    def test_a_contract_that_is_not_the_record_pin_is_refused(self):
        record = self.reconcile()
        record["task_contract_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "not the record's pinned contract"):
            self.baseline(record)

    def test_a_reconciled_record_still_carrying_a_candidate_is_refused(self):
        """`revise-on-source` publishes with no candidate. One that reappeared
        means something else touched the record, and admitting it would start a
        worker over work already in the review path."""
        record = self.reconcile()
        record["candidate"] = {"commit": "c" * 40}
        with self.assertRaisesRegex(ValueError, "must carry no candidate"):
            self.baseline(record)

    def test_a_reconciliation_the_record_has_moved_past_yields_no_baseline(self):
        record = self.reconcile()
        record["source_commit"] = "d" * 40
        self.assertIsNone(self.baseline(record),
                          "guessing which entry is current would be worse than refusing")

    def test_malformed_history_is_refused_rather_than_ignored(self):
        record = self.reconcile()
        record["revise_on_source_history"] = ["not a mapping"]
        with self.assertRaisesRegex(ValueError, "history is malformed"):
            self.baseline(record)

    def test_an_empty_history_yields_no_baseline(self):
        record = self.reconcile()
        record["revise_on_source_history"] = []
        self.assertIsNone(self.baseline(record))


def load_tests(loader, tests, pattern):
    """Run only this module's cases, not the reconciliation suite it inherits."""
    suite = unittest.TestSuite()
    for name in loader.getTestCaseNames(AdmissionReviseOnSourceTests):
        if name in dir(ReviseOnSourceTests) and name.startswith("test_"):
            continue
        suite.addTest(AdmissionReviseOnSourceTests(name))
    return suite


if __name__ == "__main__":
    unittest.main()
