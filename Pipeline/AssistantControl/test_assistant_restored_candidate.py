"""Disposable real-Git tests for assistant-restored candidate registration."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.assistant_restored_candidate import (
    AssistantRestoredCandidateError,
    register_assistant_restored_candidate,
)
from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


class RestoredCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        self.git("init", "-q")
        name, email = validated_agent_git_identity()
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)
        (self.source / "Tasks").mkdir()
        (self.source / "Assets/NoSafeCircle/Feature/Tests").mkdir(parents=True)
        (self.source / "Assets/NoSafeCircle/Feature/Feature.cs").write_text("class Feature {}\n")
        (self.source / "Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs").write_text("class FeatureTests {}\n")
        (self.source / "Tasks/NSC-042.yaml").write_text(json.dumps({
            "id": "NSC-042", "title": "Fixture", "contract_disposition": "active",
            "depends_on": [], "exclusive_resources": ["repo-file:Assets/NoSafeCircle/Feature/Feature.cs"],
        }))
        self.git("add", ".")
        self.git("commit", "-q", "-m", "base")
        self.checkouts = Checkouts(self.source, Path(self.temp.name) / "checkouts")
        self.record = self.checkouts.prepare("NSC-042")
        self.checkout = Path(self.record["checkout"])
        from Pipeline.AssistantControl.scope import AssistantScopePlanner
        self.scope = AssistantScopePlanner(self.checkouts).plan(
            "NSC-042", ExecutionScopePlan(
                ("Assets/NoSafeCircle/Feature/Feature.cs",), (),
                ("Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs",), (),
            ), lease_id="assistant-lease-1")
        (self.checkout / "Assets/NoSafeCircle/Feature/Feature.cs").write_text("class Feature { }")
        self.git_checkout("add", ".")
        self.git_checkout("commit", "-q", "-m", "restored candidate")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.source), *args], capture_output=True, check=True).stdout

    def git_checkout(self, *args):
        return subprocess.run(["git", "-C", str(self.checkout), *args], capture_output=True, check=True).stdout

    def register(self):
        base = self.record["source_commit"]
        candidate = self.git_checkout("rev-parse", "HEAD").decode().strip()
        tree = self.git_checkout("rev-parse", "HEAD^{tree}").decode().strip()
        return register_assistant_restored_candidate(
            self.checkouts, "NSC-042", base_commit=base, candidate_commit=candidate,
            candidate_tree=tree, task_contract_sha256=self.record["task_contract_sha256"],
            changed_paths=["Assets/NoSafeCircle/Feature/Feature.cs"],
            evidence={"source": "assistant-restored fixture", "unity_tests": 3},
            reference_provenance={"reference": "SuccessfullTasks/NSC-042", "restored": True},
        )

    def test_registers_honest_review_only_candidate(self):
        result = self.register()
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual("assistant_restored", result["candidate"]["kind"])
        self.assertFalse(result["candidate"]["crew_review"])
        self.assertIsNone(result["approval"])
        self.assertIsNone(result["worker"])

    def test_rejects_diff_outside_scope_and_preserves_record(self):
        before = json.loads((self.checkouts.records / "NSC-042.json").read_text())
        with self.assertRaisesRegex(AssistantRestoredCandidateError, "outside"):
            base = self.record["source_commit"]
            commit = self.git_checkout("rev-parse", "HEAD").decode().strip()
            tree = self.git_checkout("rev-parse", "HEAD^{tree}").decode().strip()
            register_assistant_restored_candidate(
                self.checkouts, "NSC-042", base_commit=base, candidate_commit=commit,
                candidate_tree=tree, task_contract_sha256=self.record["task_contract_sha256"],
                changed_paths=["Assets/NoSafeCircle/Feature/Feature.cs", "Tasks/NSC-042.yaml"],
                evidence={"e": 1}, reference_provenance={"r": 1})
        self.assertEqual(before, json.loads((self.checkouts.records / "NSC-042.json").read_text()))

    def test_rejects_unsettled_worker_without_erasing_it(self):
        path = self.checkouts.records / "NSC-042.json"
        record = json.loads(path.read_text())
        record["worker"] = {"status": "failed", "capacity_released": False}
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(AssistantRestoredCandidateError, "settled"):
            self.register()
        self.assertEqual(record, json.loads(path.read_text()))

    def test_rejects_dirty_checkout(self):
        untracked = self.checkout / "untracked.txt"
        untracked.write_text("not reviewed\n")
        with self.assertRaisesRegex(AssistantRestoredCandidateError, "uncommitted"):
            self.register()
        self.assertIsNone(json.loads(
            (self.checkouts.records / "NSC-042.json").read_text()
        ).get("candidate"))

    def test_retains_settled_worker_receipt(self):
        path = self.checkouts.records / "NSC-042.json"
        record = json.loads(path.read_text())
        record["worker"] = {"status": "failed", "capacity_released": True,
                            "run_id": "failed-run", "settlement_reason": "crew rejected"}
        path.write_text(json.dumps(record))
        result = self.register()
        self.assertEqual(record["worker"], result["worker"])
        self.assertFalse(result["candidate"]["crew_review"])

    def test_settled_worker_supersedes_retained_launch_handoff(self):
        path = self.checkouts.records / "NSC-042.json"
        record = json.loads(path.read_text())
        record["launch"] = {"status": "ready_pending", "capacity_released": False}
        record["worker"] = {"status": "failed", "capacity_released": True,
                            "run_id": "failed-run", "settlement_reason": "crew rejected"}
        path.write_text(json.dumps(record))
        result = self.register()
        self.assertEqual("ready_pending", result["launch"]["status"])
        self.assertEqual("failed", result["worker"]["status"])
        self.assertEqual("awaiting_human", result["status"])


if __name__ == "__main__":
    unittest.main()
