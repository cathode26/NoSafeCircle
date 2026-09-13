"""Real disposable-Git tests for mechanical candidate synchronization."""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.admission import _source_registry_paths
from Pipeline.AssistantControl.admission import reserve
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.AssistantControl.revisions import begin_revision
from Pipeline.AssistantControl.revision_feedback import prepare_revision_feedback
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.AssistantControl.source_update import (
    CandidateSynchronizationError,
    _require_settled_worker,
    synchronize_candidate,
    validate_synchronized_candidate,
)
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan


class SourceUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source"
        self.source.mkdir()
        self._git("init", "-q")
        name, email = validated_agent_git_identity()
        self._git("config", "user.name", name)
        self._git("config", "user.email", email)
        (self.source / "Tasks").mkdir()
        (self.source / "Tasks/NSC-042.yaml").write_text(json.dumps({
            "id": "NSC-042", "title": "sync", "contract_disposition": "active",
            "kind": "implementation", "execution_scope": "single_agent",
            "decomposition_state": "concrete", "depends_on": [],
            "exclusive_resources": [
                "repo-file:Assets/Feature/Feature.cs",
                "repo-file:Assets/Feature/Tests/FeatureTests.cs",
            ],
        }))
        (self.source / "shared.txt").write_text("base\n")
        (self.source / "test.txt").write_text("test\n")
        (self.source / "Assets/Feature/Tests").mkdir(parents=True)
        (self.source / "Assets/Feature/Feature.cs").write_text("class Feature {}\n")
        (self.source / "Assets/Feature/Tests/FeatureTests.cs").write_text("class FeatureTests {}\n")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "base")
        self.checkouts = Checkouts(self.source, root / "checkouts")
        self.checkouts.prepare("NSC-042")
        self.record_path = self.checkouts.records / "NSC-042.json"

    def _git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.source), *args],
                              capture_output=True, check=True).stdout

    def _approved_candidate(self, filename="candidate.txt", content="candidate\n"):
        checkout = self.checkouts.root / "NSC-042"
        (checkout / filename).write_text(content)
        self._git("add", filename, cwd=checkout)
        self._git("commit", "-q", "-m", "candidate", cwd=checkout)
        candidate = self._git("rev-parse", "HEAD", cwd=checkout).decode().strip()
        record = json.loads(self.record_path.read_text())
        record.update({
            "candidate": {"kind": "crew_reviewed", "commit": candidate,
                          "tree": self._git("rev-parse", "HEAD^{tree}", cwd=checkout).decode().strip(),
                          "receipt": {"run_id": "crew-old"}},
            "approval": {"commit": candidate, "decision": "approve", "message": "ok"},
            "status": "approved",
        })
        write_record(self.record_path, record)
        return record, candidate

    def _advance_source(self, filename="source-change.txt", content="source\n"):
        (self.source / filename).write_text(content)
        self._git("add", filename)
        self._git("commit", "-q", "-m", "other task integrated")

    def test_sync_merges_source_into_candidate_and_clears_approval(self):
        record, old = self._approved_candidate()
        old_source = record["source_commit"]
        self._advance_source()
        source_before = self._git("rev-parse", "HEAD").decode().strip()
        result = synchronize_candidate(self.checkouts, "NSC-042", old, source_before)
        new = result["candidate"]
        self.assertEqual("source_synchronized", new["kind"])
        self.assertFalse(new["crew_review"])
        self.assertTrue(new["source_candidate_crew_review"])
        self.assertIsNone(result["approval"])
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual(old, new["parent"])
        self.assertEqual(source_before, result["source_commit"])
        self.assertEqual(new["commit"], self._git("rev-parse", "HEAD", cwd=self.checkouts.root / "NSC-042").decode().strip())
        self.assertEqual(source_before, self._git("rev-parse", "HEAD").decode().strip())
        self.assertEqual(old, result["candidate_lineage"][0]["candidate"]["commit"])
        validate_synchronized_candidate(self.checkouts, result, new["commit"])

    def test_unreviewed_candidate_syncs_before_first_test_without_granting_approval(self):
        record, old = self._approved_candidate()
        record["approval"] = None
        record["status"] = "awaiting_human"
        write_record(self.record_path, record)
        self._advance_source()
        source_head = self._git("rev-parse", "HEAD").decode().strip()
        result = synchronize_candidate(self.checkouts, "NSC-042", old, source_head)
        self.assertEqual("source_synchronized", result["candidate"]["kind"])
        self.assertEqual("unreviewed",
                         result["candidate"]["mechanical_merge"]["prior_review_state"])
        self.assertIsNone(result["approval"])
        self.assertEqual("awaiting_human", result["status"])
        validate_synchronized_candidate(self.checkouts, result, result["candidate"]["commit"])

    def test_stale_policy_validation_failure_syncs_for_a_fresh_validation(self):
        record, old = self._approved_candidate()
        record["approval"] = None
        record["human_review"] = None
        record["status"] = "validation_failed"
        record["candidate_validation_failure"] = {
            "candidate_commit": old,
            "validation_error": "authoritative validation policy for NSC-042 is stale",
        }
        write_record(self.record_path, record)
        self._advance_source("policy-fix.txt", "corrected policy\n")
        source_head = self._git("rev-parse", "HEAD").decode().strip()
        result = synchronize_candidate(self.checkouts, "NSC-042", old, source_head)
        self.assertEqual("source_synchronized", result["candidate"]["kind"])
        self.assertEqual(
            "stale_policy_validation_retry",
            result["candidate"]["mechanical_merge"]["prior_review_state"],
        )
        self.assertEqual("awaiting_human", result["status"])
        self.assertIsNone(result["approval"])

    def test_other_validation_failure_cannot_sync(self):
        record, old = self._approved_candidate()
        record["approval"] = None
        record["human_review"] = None
        record["status"] = "validation_failed"
        record["candidate_validation_failure"] = {
            "candidate_commit": old,
            "validation_error": "focused test failed",
        }
        write_record(self.record_path, record)
        self._advance_source()
        with self.assertRaisesRegex(ValueError, "failed authoritative Unity validation"):
            synchronize_candidate(
                self.checkouts, "NSC-042", old,
                self._git("rev-parse", "HEAD").decode().strip(),
            )

    def test_rejected_candidate_cannot_use_unreviewed_sync_path(self):
        record, old = self._approved_candidate()
        record["approval"] = {"commit": old, "decision": "reject", "message": "fix it"}
        record["status"] = "changes_requested"
        write_record(self.record_path, record)
        self._advance_source()
        with self.assertRaisesRegex(CandidateSynchronizationError, "approved or unreviewed"):
            synchronize_candidate(
                self.checkouts, "NSC-042", old,
                self._git("rev-parse", "HEAD").decode().strip(),
            )

    def test_review_gate_requires_new_sha_then_integrates_synchronized_candidate(self):
        _, old = self._approved_candidate()
        self._advance_source()
        source_head = self._git("rev-parse", "HEAD").decode().strip()
        result = synchronize_candidate(self.checkouts, "NSC-042", old, source_head)
        new = result["candidate"]["commit"]
        gate = ReviewGate(self.checkouts)
        with self.assertRaisesRegex(ValueError, "registered reviewed candidate"):
            gate.decide("NSC-042", tested_commit=old, decision="approve", message="TESTONLY stale")
        gate.decide("NSC-042", tested_commit=new, decision="approve", message="TESTONLY approve")
        integrated = gate.integrate(
            "NSC-042", expected_source_commit=source_head,
            target_branch=self._git("branch", "--show-current").decode().strip())
        self.assertEqual("integrated", integrated["status"])
        self.assertEqual(new, self._git("rev-parse", "HEAD").decode().strip())

    def test_repeated_sync_preserves_lineage_rejects_stale_approval_and_replays_old_command(self):
        _, original = self._approved_candidate()
        self._advance_source("source-one.txt", "one\n")
        source_one = self._git("rev-parse", "HEAD").decode().strip()
        first = synchronize_candidate(self.checkouts, "NSC-042", original, source_one)
        first_commit = first["candidate"]["commit"]
        self.assertTrue(first["candidate"]["source_candidate_crew_review"])
        # Recover authority from the retained original receipt even if an older
        # controller persisted the derived display flag incorrectly.
        first["candidate"]["source_candidate_crew_review"] = False
        write_record(self.record_path, first)
        gate = ReviewGate(self.checkouts)
        gate.decide("NSC-042", tested_commit=first_commit,
                    decision="approve", message="TESTONLY source one")
        self._advance_source("source-two.txt", "two\n")
        source_two = self._git("rev-parse", "HEAD").decode().strip()
        second = synchronize_candidate(self.checkouts, "NSC-042", first_commit, source_two)
        second_commit = second["candidate"]["commit"]
        self.assertTrue(second["candidate"]["source_candidate_crew_review"])
        checkout = self.checkouts.root / "NSC-042"
        self.assertNotEqual(first_commit, second_commit)
        self.assertTrue((checkout / "source-one.txt").is_file())
        self.assertTrue((checkout / "source-two.txt").is_file())
        self.assertEqual(original, second["candidate"]["original_candidate"]["commit"])
        with self.assertRaisesRegex(ValueError, "registered reviewed candidate"):
            gate.decide("NSC-042", tested_commit=first_commit,
                        decision="approve", message="TESTONLY stale")
        gate.decide("NSC-042", tested_commit=second_commit,
                    decision="approve", message="TESTONLY source two")
        integrated = gate.integrate(
            "NSC-042", expected_source_commit=source_two,
            target_branch=self._git("branch", "--show-current").decode().strip())
        self.assertEqual("integrated", integrated["status"])
        replay = synchronize_candidate(self.checkouts, "NSC-042", original, source_one)
        self.assertEqual(second_commit, replay["candidate"]["commit"])
        self.assertEqual(second_commit, self._git("rev-parse", "HEAD", cwd=checkout).decode().strip())

    def test_second_sync_recovers_after_finalize_failure(self):
        _, original = self._approved_candidate()
        self._advance_source("source-one.txt", "one\n")
        source_one = self._git("rev-parse", "HEAD").decode().strip()
        first = synchronize_candidate(self.checkouts, "NSC-042", original, source_one)
        first_commit = first["candidate"]["commit"]
        ReviewGate(self.checkouts).decide(
            "NSC-042", tested_commit=first_commit, decision="approve", message="TESTONLY one")
        self._advance_source("source-two.txt", "two\n")
        source_two = self._git("rev-parse", "HEAD").decode().strip()
        with patch("Pipeline.AssistantControl.source_update._finalize",
                   side_effect=RuntimeError("injected finalize failure")):
            with self.assertRaises(CandidateSynchronizationError):
                synchronize_candidate(self.checkouts, "NSC-042", first_commit, source_two)
        recovered = synchronize_candidate(self.checkouts, "NSC-042", first_commit, source_two)
        self.assertEqual("source_synchronized", recovered["candidate"]["kind"])
        self.assertIsNone(recovered["approval"])
        self.assertEqual(self._git("rev-parse", "HEAD", cwd=self.checkouts.root / "NSC-042").decode().strip(),
                         recovered["candidate"]["commit"])
        validate_synchronized_candidate(self.checkouts, recovered, recovered["candidate"]["commit"])

    def test_rejected_synchronized_candidate_enters_fresh_feedback_revision(self):
        _, old = self._approved_candidate()
        self._advance_source()
        source_head = self._git("rev-parse", "HEAD").decode().strip()
        result = synchronize_candidate(self.checkouts, "NSC-042", old, source_head)
        new = result["candidate"]["commit"]
        gate = ReviewGate(self.checkouts)
        gate.decide("NSC-042", tested_commit=new, decision="reject", message="TESTONLY revise")
        before = self.record_path.read_bytes()
        revised = begin_revision(self.checkouts, "NSC-042", new)
        self.assertNotEqual(before, self.record_path.read_bytes())
        self.assertEqual("prepared", revised["status"])
        self.assertEqual("fresh", revised["revision"]["feedback_mode"])
        self.assertEqual(new, revised["revision_history"][-1]["candidate"]["commit"])
        self.assertEqual("source_synchronized", revised["revision_history"][-1]["candidate"]["kind"])

    def test_fresh_revision_feedback_uses_new_admission_without_old_retry_args(self):
        _, old = self._approved_candidate()
        self._advance_source()
        source_head = self._git("rev-parse", "HEAD").decode().strip()
        synced = synchronize_candidate(self.checkouts, "NSC-042", old, source_head)
        sync_commit = synced["candidate"]["commit"]
        ReviewGate(self.checkouts).decide(
            "NSC-042", tested_commit=sync_commit, decision="reject", message="TESTONLY fresh notes")
        revised = begin_revision(self.checkouts, "NSC-042", sync_commit)
        AssistantScopePlanner(self.checkouts).plan(
            "NSC-042", ExecutionScopePlan(("Assets/Feature/Feature.cs",), (),
                                           ("Assets/Feature/Tests/FeatureTests.cs",), ()),
            lease_id="fresh-lease")
        reservation = reserve(
            self.checkouts, "NSC-042", "fresh-run",
            dependency_reader=lambda source, task_id, root: {
                "task_id": task_id, "source_commit": source_head,
                "source_unchanged_during_read": True, "dependencies_satisfied": True,
            })
        feedback = prepare_revision_feedback(
            self.checkouts, revised, reservation,
            {"provider": "claude", "execution_model": "fresh-model"})
        self.assertEqual({"revision_feedback_file"}, set(feedback))
        self.assertEqual("TESTONLY fresh notes",
                         feedback["revision_feedback_file"].read_text(encoding="utf-8"))

    def test_source_working_edit_is_preserved(self):
        record, old = self._approved_candidate()
        self._advance_source()
        edit = self.source / "uncommitted-user-edit.txt"
        edit.write_text("preserve me")
        source_head = self._git("rev-parse", "HEAD").decode().strip()
        synchronize_candidate(self.checkouts, "NSC-042", old, source_head)
        self.assertEqual("preserve me", edit.read_text())

    def test_conflict_retains_staging_and_does_not_change_source_or_checkout(self):
        record, old = self._approved_candidate("shared.txt", "candidate\n")
        checkout = self.checkouts.root / "NSC-042"
        self._advance_source("shared.txt", "source\n")
        before = self._git("rev-parse", "HEAD", cwd=checkout).decode().strip()
        with self.assertRaisesRegex(CandidateSynchronizationError, "retained staging") as error:
            synchronize_candidate(self.checkouts, "NSC-042", old,
                                  self._git("rev-parse", "HEAD").decode().strip())
        staging = Path(re.search(r"retained staging at (.+)$", str(error.exception)).group(1))
        self.assertTrue(staging.exists())
        self.assertEqual(before, self._git("rev-parse", "HEAD", cwd=checkout).decode().strip())
        self.assertEqual("crew_reviewed", json.loads(self.record_path.read_text())["candidate"]["kind"])

    def test_post_ff_journal_recovers_if_record_write_raced(self):
        record, old = self._approved_candidate()
        self._advance_source()
        source_head = self._git("rev-parse", "HEAD").decode().strip()
        first = synchronize_candidate(self.checkouts, "NSC-042", old, source_head)
        with self.assertRaisesRegex(CandidateSynchronizationError, "has not advanced"):
            synchronize_candidate(self.checkouts, "NSC-042", first["candidate"]["commit"], source_head)
        # Simulate the narrow crash window after checkout FF and journal post,
        # before the task record write.
        write_record(self.record_path, record)
        recovered = synchronize_candidate(self.checkouts, "NSC-042", old, source_head)
        self.assertEqual(first["candidate"]["commit"], recovered["candidate"]["commit"])

    def test_matching_settled_worker_pair_needs_only_worker_capacity_proof(self):
        _require_settled_worker({
            "worker": {"run_id": "run", "status": "failed", "capacity_released": True},
            "launch": {"run_id": "run", "status": "failed"},
        })
        with self.assertRaisesRegex(CandidateSynchronizationError, "launch"):
            _require_settled_worker({
                "worker": {"run_id": "run", "status": "failed", "capacity_released": True},
                "launch": {"run_id": "other", "status": "failed"},
            })

    def test_active_reservation_blocks_journal_recovery(self):
        record, old = self._approved_candidate()
        self._advance_source()
        source_head = self._git("rev-parse", "HEAD").decode().strip()
        first = synchronize_candidate(self.checkouts, "NSC-042", old, source_head)
        write_record(self.record_path, record)
        _, registry_path = _source_registry_paths(self.source)
        write_record(registry_path, {"schema_version": "assistant-admission/v1",
                                     "source": str(self.checkouts.source),
                                     "reservations": [{"status": "active", "task_id": "NSC-042"}]})
        with self.assertRaisesRegex(CandidateSynchronizationError, "active reservation"):
            synchronize_candidate(self.checkouts, "NSC-042", old, source_head)

    def test_validator_rejects_tampered_merge_proof(self):
        record, old = self._approved_candidate()
        self._advance_source()
        source_head = self._git("rev-parse", "HEAD").decode().strip()
        result = synchronize_candidate(self.checkouts, "NSC-042", old, source_head)
        result["candidate"]["mechanical_merge"]["merge_tree"] = "0" * 40
        with self.assertRaisesRegex(CandidateSynchronizationError, "merge-tree"):
            validate_synchronized_candidate(self.checkouts, result, result["candidate"]["commit"])


if __name__ == "__main__":
    unittest.main()
