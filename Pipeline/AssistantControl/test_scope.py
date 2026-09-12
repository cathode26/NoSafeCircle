"""Real repository-scope adapter tests using disposable Git repositories."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.scope import AssistantScopePlanner, ScopePlanningError
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


class ScopePlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        self.git("init")
        name, email = validated_agent_git_identity()
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)
        (self.source / "Tasks").mkdir()
        (self.source / "Assets/NoSafeCircle/Feature/Tests").mkdir(parents=True)
        (self.source / "Assets/NoSafeCircle/Feature/Feature.cs").write_text("class Feature {}\n")
        (self.source / "Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs").write_text("class FeatureTests {}\n")
        contract = {
            "id": "NSC-042", "title": "Fixture", "contract_disposition": "active",
            "depends_on": [], "exclusive_resources": ["repo-file:Assets/NoSafeCircle/Feature/Feature.cs"],
        }
        (self.source / "Tasks/NSC-042.yaml").write_text(json.dumps(contract))
        self.git("add", ".")
        self.git("commit", "-m", "fixture")
        self.checkouts = Checkouts(self.source, Path(self.temp.name) / "checkouts")
        self.checkout = Path(self.checkouts.prepare("NSC-042")["checkout"])

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.source), *args], capture_output=True, check=True).stdout

    def valid(self):
        return ExecutionScopePlan(
            ("Assets/NoSafeCircle/Feature/Feature.cs",), (),
            ("Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs",), (),
        )

    def test_accepts_real_scope_and_persists_exact_identity(self):
        result = AssistantScopePlanner(self.checkouts).plan(
            "NSC-042", self.valid(), lease_id="assistant-lease-1"
        )
        self.assertTrue(result["accepted"])
        self.assertTrue(result["plan_id"].startswith("scope-"))
        self.assertEqual(result["source_commit"], self.git("rev-parse", "HEAD").decode().strip())
        self.assertEqual("assistant-lease-1", result["lease_id"])
        record = json.loads((self.checkouts.records / "NSC-042.json").read_text())
        self.assertEqual(result["plan_id"], record["scope"]["plan_id"])
        self.assertFalse(result["execution_authorized"])

    def test_invalid_plan_preserves_previous_scope(self):
        planner = AssistantScopePlanner(self.checkouts)
        first = planner.plan("NSC-042", self.valid(), lease_id="assistant-lease-1")
        invalid = ExecutionScopePlan(
            ("Assets/NoSafeCircle/Feature/Feature.cs",), (), (),
            ("Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs",),
        )
        with self.assertRaises(ScopePlanningError):
            planner.plan("NSC-042", invalid, lease_id="assistant-lease-2")
        record = json.loads((self.checkouts.records / "NSC-042.json").read_text())
        self.assertEqual(first["plan_id"], record["scope"]["plan_id"])
        self.assertEqual("assistant-lease-1", record["scope"]["lease_id"])

    def test_worker_or_candidate_underway_preserves_scope(self):
        planner = AssistantScopePlanner(self.checkouts)
        first = planner.plan("NSC-042", self.valid(), lease_id="assistant-lease-1")
        path = self.checkouts.records / "NSC-042.json"
        record = json.loads(path.read_text())
        record["worker"] = {"lease_id": "worker-1"}
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ScopePlanningError, "underway"):
            planner.plan("NSC-042", self.valid(), lease_id="assistant-lease-2")
        record = json.loads(path.read_text())
        self.assertEqual(first["plan_id"], record["scope"]["plan_id"])


if __name__ == "__main__":
    unittest.main()
