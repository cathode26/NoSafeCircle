"""Reconciling a rejected candidate with current Source for fresh crew work.

The decisive test is the tree one. Every other test asserts the RECORD, and a
record that says `prepared` while the checkout still lacks Source's commits
would be a confident lie -- the worker would start from the wrong tree and
nothing in the record would say so.
"""
from __future__ import annotations

import hashlib
import json
import unittest
import uuid
from pathlib import Path

from Pipeline.AssistantControl import test_materialization_reopen as fixture
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.revise_on_source import (
    ReviseOnSourceError,
    revise_on_source,
)

TASK = "NSC-046"


class ReviseOnSourceTests(unittest.TestCase):
    setUp = fixture.ReopenMaterializationTests.setUp
    git = staticmethod(fixture.ReopenMaterializationTests.git)
    register_candidate = fixture.ReopenMaterializationTests.register_candidate
    builder = fixture.ReopenMaterializationTests.builder
    failing_validation = fixture.ReopenMaterializationTests.failing_validation
    make_failed_record = fixture.ReopenMaterializationTests.make_failed_record

    def record(self) -> dict:
        return json.loads((self.manager.records / f"{TASK}.json").read_text())

    def advance_source(self, revise_contract: bool) -> tuple[str, str]:
        """Move Source on, optionally revising this task's contract too.

        Returns (source head, contract sha256 at that head). The contract sha is
        the committed LF blob, which is what the loader hashes.
        """
        marker = self.source / "Pipeline/Testing/source-moved.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        # Unique per call: a second identical write leaves nothing to commit.
        marker.write_text(f"main moved on {uuid.uuid4().hex}\n",
                          encoding="utf-8", newline="\n")
        self.git(self.source, "add", "--", "Pipeline/Testing/source-moved.txt")
        if revise_contract:
            path = self.source / f"Tasks/{TASK}.yaml"
            task = json.loads(path.read_text(encoding="utf-8"))
            task["title"] = "revised while the candidate sat frozen"
            path.write_text(json.dumps(task), encoding="utf-8", newline="\n")
            self.git(self.source, "add", "--", f"Tasks/{TASK}.yaml")
        self.git(self.source, "commit", "-q", "-m", "source advances")
        head = self.git(self.source, "rev-parse", "HEAD")
        blob = git(self.source, "cat-file", "blob", f"{head}:Tasks/{TASK}.yaml")
        return head, hashlib.sha256(blob).hexdigest()

    def frozen_pair(self, revise_contract: bool = True) -> tuple[str, str, str]:
        _original, materialized, _digest = self.make_failed_record()
        head, contract = self.advance_source(revise_contract)
        return materialized, head, contract

    def test_a_plan_changes_nothing(self):
        candidate, head, contract = self.frozen_pair()
        before = (self.manager.records / f"{TASK}.json").read_bytes()
        plan = revise_on_source(
            self.manager, TASK, expected_candidate=candidate,
            expected_source_commit=head, accept_contract_sha256=contract,
            reason="two real test failures need a crew pass")
        self.assertFalse(plan["applied"])
        self.assertEqual("prepared", plan["next_status"])
        self.assertTrue(plan["carries_no_candidate"])
        self.assertEqual(before, (self.manager.records / f"{TASK}.json").read_bytes())

    def test_apply_publishes_prepared_with_no_candidate_and_the_accepted_contract(self):
        candidate, head, contract = self.frozen_pair()
        old_pin = self.record()["task_contract_sha256"]
        plan = revise_on_source(
            self.manager, TASK, expected_candidate=candidate,
            expected_source_commit=head, accept_contract_sha256=contract,
            reason="two real test failures need a crew pass", apply=True)
        self.assertTrue(plan["applied"])
        record = self.record()
        self.assertEqual("prepared", record["status"])
        self.assertNotIn("candidate", record)
        self.assertNotIn("materialization_failure", record)
        self.assertEqual(contract, record["task_contract_sha256"])
        self.assertNotEqual(old_pin, contract)
        self.assertEqual(plan["reconciled_commit"], record["source_commit"])

    def test_the_reconciled_tree_holds_BOTH_the_crew_work_and_source(self):
        """The decisive one. A record saying `prepared` over a tree that lacks
        Source would start the worker from the wrong place and say nothing."""
        candidate, head, contract = self.frozen_pair()
        plan = revise_on_source(
            self.manager, TASK, expected_candidate=candidate,
            expected_source_commit=head, accept_contract_sha256=contract,
            reason="two real test failures need a crew pass", apply=True)
        checkout = Path(plan["checkout"])
        merged = plan["reconciled_commit"]
        self.assertEqual(merged, self.git(checkout, "rev-parse", "HEAD"))
        # Source's new commit is an ancestor...
        git(checkout, "merge-base", "--is-ancestor", head, merged)
        # ...and so is the rejected candidate: the crew's work is carried, not discarded.
        git(checkout, "merge-base", "--is-ancestor", candidate, merged)
        self.assertTrue((checkout / "Pipeline/Testing/source-moved.txt").is_file())

    def test_the_rejected_candidate_and_its_failure_are_archived(self):
        candidate, head, contract = self.frozen_pair()
        plan = revise_on_source(
            self.manager, TASK, expected_candidate=candidate,
            expected_source_commit=head, accept_contract_sha256=contract,
            reason="two real test failures need a crew pass", apply=True)
        archived = json.loads(Path(plan["archived_record"]).read_text(encoding="utf-8"))
        self.assertEqual(candidate, archived["rejected_candidate"]["commit"])
        self.assertTrue(archived["materialization_failure"])
        self.assertEqual(plan["old_contract_sha256"], archived["old_contract_sha256"])

    def test_a_contract_that_is_not_the_one_at_source_head_is_refused(self):
        """Adopting 'whatever is at HEAD' is the decision this refuses to make."""
        candidate, head, _contract = self.frozen_pair()
        with self.assertRaises(Exception) as caught:
            revise_on_source(
                self.manager, TASK, expected_candidate=candidate,
                expected_source_commit=head, accept_contract_sha256="a" * 64,
                reason="wrong contract", apply=True)
        self.assertNotIsInstance(caught.exception, SystemExit)

    def test_a_source_that_has_not_advanced_is_refused(self):
        _original, materialized, _digest = self.make_failed_record()
        head = self.git(self.source, "rev-parse", "HEAD")
        blob = git(self.source, "cat-file", "blob", f"{head}:Tasks/{TASK}.yaml")
        with self.assertRaisesRegex(ReviseOnSourceError, "ordinary revise applies"):
            revise_on_source(
                self.manager, TASK, expected_candidate=materialized,
                expected_source_commit=head,
                accept_contract_sha256=hashlib.sha256(blob).hexdigest(),
                reason="nothing moved", apply=True)

    def test_a_healthy_candidate_is_refused(self):
        """An intact crew candidate has not been rejected; nothing to reconcile."""
        candidate = self.register_candidate()
        head, contract = self.advance_source(revise_contract=True)
        with self.assertRaisesRegex(ReviseOnSourceError, "FAILED authoritative validation"):
            revise_on_source(
                self.manager, TASK, expected_candidate=candidate,
                expected_source_commit=head, accept_contract_sha256=contract,
                reason="wrong command", apply=True)

    def test_a_stale_inspected_source_is_refused(self):
        candidate, head, contract = self.frozen_pair()
        self.advance_source(revise_contract=False)
        with self.assertRaisesRegex(ReviseOnSourceError, "re-inspect"):
            revise_on_source(
                self.manager, TASK, expected_candidate=candidate,
                expected_source_commit=head, accept_contract_sha256=contract,
                reason="stale inspection", apply=True)


if __name__ == "__main__":
    unittest.main()
