"""Receipt regressions with real Git, bridge verification and local committer.

Crew artifacts and bridge persistence are explicit fixture inputs, not provider
review evidence. All files/commits and test-only human decisions are confined
to disposable repositories. No provider, Docker or Unity is invoked.
"""
import hashlib
import json
import unittest
from dataclasses import replace

from Pipeline.AssistantControl import test_candidate as fixture
from Pipeline.AssistantControl.candidate import _scope, register_candidate
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.AssistantControl.revisions import begin_revision
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge


class CandidateReceiptRevisionTests(unittest.TestCase):
    git = fixture.CandidateRecoveryTests.git
    git_bytes = fixture.CandidateRecoveryTests.git_bytes
    valid = fixture.CandidateRecoveryTests.valid

    config = {"execution_model": "recovery-model", "crew_profile": "full",
              "validation_profile": "full_relevant"}

    def setUp(self):
        fixture.CandidateRecoveryTests.setUp(self)

    def receipt_path(self, run_id):
        return (self.checkouts.records / "candidate-receipts" / "NSC-042" /
                (hashlib.sha256(run_id.encode("utf-8")).hexdigest() + ".json"))

    def register(self, run_id):
        return register_candidate(self.checkouts, "NSC-042", run_id, self.config)

    def test_distinct_revision_runs_preserve_both_real_committer_receipts(self):
        # First registration really writes a committer receipt; seeding only
        # candidate metadata would miss a task-wide receipt-path collision.
        first = self.register(self.run_id)
        first_path = self.receipt_path(self.run_id)
        first_bytes = first_path.read_bytes()
        first_commit = first["candidate"]["commit"]
        old_artifacts = {path: path.read_bytes()
                         for path in (self.result_path, self.patch_path)}
        ReviewGate(self.checkouts).decide(
            "NSC-042", tested_commit=first_commit, decision="reject",
            message="TEST ONLY: revise this disposable candidate")
        begin_revision(self.checkouts, "NSC-042", first_commit)
        accepted = AssistantScopePlanner(self.checkouts).plan(
            "NSC-042", self.valid(), lease_id="receipt-revision-lease")
        record = json.loads(self.record_path.read_text())
        second_run = "crew-receipt-revision-run"
        second_result = self.result_path.with_name("second-crew-result.json")
        second_result.write_text('{"pipeline_generated_paths": []}\n', encoding="utf-8")
        second_patch = self.patch_path.with_name("second-candidate.patch")
        for relative in self.receipt.final_actual_changed_paths:
            target = self.checkout / relative
            target.write_bytes(target.read_bytes().replace(b"Recovered", b"Revised"))
        second_patch.write_bytes(self.git_bytes("diff", "--binary"))
        self.git_bytes("restore", "--", *self.receipt.final_actual_changed_paths)
        receipt = replace(
            self.receipt, run_id=second_run, lease_id=accepted["lease_id"],
            plan_id=accepted["plan_id"], source_head=first_commit,
            result_path=str(second_result),
            result_sha256=hashlib.sha256(second_result.read_bytes()).hexdigest(),
            candidate_path=str(second_patch),
            candidate_sha256=hashlib.sha256(second_patch.read_bytes()).hexdigest())
        bridge = ExecutionCrewBridge(
            checkout=self.checkout, scope=_scope(self.checkouts, record), **self.config)
        bridge._persist(receipt)  # Fixture-generated result; never execute bridge.run.
        second = self.register(second_run)  # Real patch validation/application/commit.
        second_path = self.receipt_path(second_run)
        self.assertNotEqual(first_path, second_path)
        self.assertEqual(first_bytes, first_path.read_bytes())
        self.assertEqual(second_run, json.loads(second_path.read_text())["run_id"])
        self.assertEqual(first_commit, second["candidate"]["parent"])
        self.assertNotEqual(first_commit, second["candidate"]["commit"])
        self.assertEqual(first["candidate"], second["revision_history"][0]["candidate"])
        for path, contents in old_artifacts.items():
            self.assertEqual(contents, path.read_bytes())
        second_bytes = second_path.read_bytes()
        self.assertEqual(second, self.register(second_run))
        self.assertEqual(second_bytes, second_path.read_bytes())
        self.assertEqual(first_bytes, first_path.read_bytes())
        self.assertEqual(b"", self.git_bytes("status", "--porcelain=v1", "--untracked-files=all"))

    def test_reregistration_preserves_exact_approved_record_and_receipt_bytes(self):
        registered = self.register(self.run_id)
        commit = registered["candidate"]["commit"]
        approved = ReviewGate(self.checkouts).decide(
            "NSC-042", tested_commit=commit, decision="approve",
            message="TEST ONLY: approve this disposable candidate")
        record_bytes = self.record_path.read_bytes()
        receipt_bytes = self.receipt_path(self.run_id).read_bytes()
        repeated = self.register(self.run_id)
        self.assertEqual(approved, repeated)
        self.assertEqual("approved", repeated["status"])
        self.assertEqual(approved["approval"], repeated["approval"])
        self.assertEqual(record_bytes, self.record_path.read_bytes())
        self.assertEqual(receipt_bytes, self.receipt_path(self.run_id).read_bytes())
        self.assertEqual(commit, self.git_bytes("rev-parse", "HEAD").decode().strip())
        self.assertEqual(b"", self.git_bytes("status", "--porcelain=v1", "--untracked-files=all"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
