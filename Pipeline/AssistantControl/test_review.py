"""Real-Git component tests of decisions and merge recovery.

Candidate registration is a fixture seam, not evidence of crew review. No human
approval or task delivery is claimed outside these temporary repositories.
"""
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl import test_checkouts as fixture
from Pipeline.AssistantControl import review
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


class ReviewTests(unittest.TestCase):
    setUp = fixture.CheckoutTests.setUp
    run_git = fixture.CheckoutTests.run_git
    manager = fixture.CheckoutTests.manager

    def candidate(self, filename="wall file.txt"):
        manager = self.manager()
        record = manager.prepare("NSC-042")
        checkout = Path(record["checkout"])
        name, email = validated_agent_git_identity()
        for args in (("config", "user.name", name), ("config", "user.email", email)):
            review.git(checkout, *args)
        (checkout / filename).write_text("candidate\n")
        review.git(checkout, "add", filename)
        review.git(checkout, "commit", "-m", "Fixture reviewed candidate")
        commit = review.git(checkout, "rev-parse", "HEAD").decode().strip()
        record["candidate"] = {"commit": commit,
                               "tree": review.git(checkout, "rev-parse", "HEAD^{tree}").decode().strip()}
        record["status"] = "awaiting_human"
        review.write_record(manager.records / "NSC-042.json", record)
        gate = review.ReviewGate(manager)
        branch = self.run_git("branch", "--show-current").decode().strip()
        return gate, record, commit, branch

    def approve(self, gate, commit):
        return gate.decide("NSC-042", tested_commit=commit, decision="approve", message="Fixture PASS")

    def test_no_approval_no_merge_then_exact_approved_commit_integrates_once(self):
        gate, record, commit, branch = self.candidate()
        before = record["source_commit"]
        with self.assertRaisesRegex(ValueError, "approve"):
            gate.integrate("NSC-042", expected_source_commit=before, target_branch=branch)
        self.approve(gate, commit)
        first = gate.integrate("NSC-042", expected_source_commit=before, target_branch=branch)
        second = gate.integrate("NSC-042", expected_source_commit=before, target_branch=branch)
        self.assertEqual("integrated", first["status"])
        self.assertEqual(first["integration"], second["integration"])
        self.assertEqual(commit, self.run_git("rev-parse", "HEAD").decode().strip())

    def test_dirty_source_and_changed_tested_commit_are_preserved(self):
        gate, record, commit, branch = self.candidate()
        with self.assertRaisesRegex(ValueError, "not the registered"):
            self.approve(gate, record["source_commit"])
        self.approve(gate, commit)
        (self.root / "wall file.txt").write_text("Vincent's current work")
        with self.assertRaisesRegex(ValueError, "overlap"):
            gate.integrate("NSC-042", expected_source_commit=record["source_commit"], target_branch=branch)
        self.assertEqual("Vincent's current work", (self.root / "wall file.txt").read_text())

    def test_disjoint_tracked_source_edit_survives_integration_byte_for_byte(self):
        user_path = self.root / "vincent-work.txt"
        user_path.write_bytes(b"committed\r\n")
        self.run_git("add", "vincent-work.txt")
        self.run_git("commit", "-m", "Fixture user file")
        gate, record, commit, branch = self.candidate()
        self.approve(gate, commit)
        user_bytes = b"Vincent's uncommitted Unity work\r\n\x00"
        user_path.write_bytes(user_bytes)
        result = gate.integrate(
            "NSC-042", expected_source_commit=record["source_commit"], target_branch=branch,
        )
        self.assertEqual("integrated", result["status"])
        self.assertEqual(commit, self.run_git("rev-parse", "HEAD").decode().strip())
        self.assertEqual(user_bytes, user_path.read_bytes())
        self.assertTrue(result["integration"]["preserved_worktree"]["paths"])

    def test_reject_cancels_approval_and_preserves_candidate(self):
        gate, record, commit, branch = self.candidate()
        self.approve(gate, commit)
        rejected = gate.decide("NSC-042", tested_commit=commit, decision="reject", message="Fixture seams still visible")
        self.assertIsNone(rejected["approval"])
        self.assertEqual(2, len(rejected["review_history"]))
        with self.assertRaisesRegex(ValueError, "approve"):
            gate.integrate("NSC-042", expected_source_commit=record["source_commit"], target_branch=branch)
        self.assertEqual("candidate\n", (Path(record["checkout"]) / "wall file.txt").read_text())

    def test_merge_before_receipt_recovers_without_second_merge(self):
        gate, record, commit, branch = self.candidate()
        self.approve(gate, commit)
        original_write = review.write_record
        def fail_after_merge(path, value):
            if value["status"] == "integrated":
                raise OSError("Fixture interruption after Git merge")
            original_write(path, value)
        with patch.object(review, "write_record", side_effect=fail_after_merge):
            with self.assertRaisesRegex(OSError, "interruption"):
                gate.integrate("NSC-042", expected_source_commit=record["source_commit"], target_branch=branch)
        self.assertEqual(commit, self.run_git("rev-parse", "HEAD").decode().strip())
        result = gate.integrate("NSC-042", expected_source_commit=record["source_commit"], target_branch=branch)
        self.assertEqual("integrated", result["status"])

    def test_changed_candidate_after_approval_cannot_integrate(self):
        gate, record, commit, branch = self.candidate()
        self.approve(gate, commit)
        checkout = Path(record["checkout"])
        (checkout / "wall file.txt").write_text("unreviewed follow-up")
        review.git(checkout, "add", "wall file.txt")
        review.git(checkout, "commit", "-m", "Unreviewed fixture")
        with self.assertRaisesRegex(ValueError, "changed after review"):
            gate.integrate("NSC-042", expected_source_commit=record["source_commit"], target_branch=branch)
        self.assertEqual(record["source_commit"], self.run_git("rev-parse", "HEAD").decode().strip())

    def test_ignored_source_file_collision_is_preserved_and_refused(self):
        gate, record, commit, branch = self.candidate("local-notes.txt")
        exclude = self.root / ".git/info/exclude"
        exclude.write_text(exclude.read_text() + "\nlocal-notes.txt\n")
        notes = self.root / "local-notes.txt"
        notes.write_text("Vincent's ignored notes\n")
        self.approve(gate, commit)
        with self.assertRaisesRegex(RuntimeError, "overwritten"):
            gate.integrate("NSC-042", expected_source_commit=record["source_commit"], target_branch=branch)
        self.assertEqual("Vincent's ignored notes\n", notes.read_text())
        self.assertEqual(record["source_commit"], self.run_git("rev-parse", "HEAD").decode().strip())

    def test_branch_switch_during_fetch_fails_closed_before_merge(self):
        gate, record, commit, branch = self.candidate()
        self.run_git("branch", "other-work")
        self.approve(gate, commit)
        original_git = review.git
        switched = False

        def switch_after_fetch(source, *args, **kwargs):
            nonlocal switched
            result = original_git(source, *args, **kwargs)
            if args and args[0] == "fetch" and not switched:
                switched = True
                original_git(source, "checkout", "other-work")
            return result

        with patch.object(review, "git", side_effect=switch_after_fetch):
            with self.assertRaisesRegex(ValueError, "changed during fetch"):
                gate.integrate("NSC-042", expected_source_commit=record["source_commit"], target_branch=branch)
        self.assertTrue(switched)
        self.assertEqual("other-work", self.run_git("branch", "--show-current").decode().strip())
        self.assertEqual(record["source_commit"], self.run_git("rev-parse", branch).decode().strip())
        self.assertEqual(record["source_commit"], self.run_git("rev-parse", "other-work").decode().strip())


if __name__ == "__main__":
    unittest.main()
