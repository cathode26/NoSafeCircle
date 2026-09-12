"""Candidate adapter tests using a temporary real Git checkout and explicit fixture seams.

The fake bridge and committer below are test seams. They prove adapter identity,
durability, locking, and dirty-checkout behavior; they are not independent
ExecutionCrew review evidence and do not authorize a real task.
"""
import json
import unittest
from pathlib import Path

from Pipeline.AssistantControl import test_scope as scope_fixture
from Pipeline.AssistantControl.candidate import (
    CandidateRegistrationError,
    register_candidate,
)
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewReceipt
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge
from Pipeline.TaskReviewAgent.local_candidate_commit import (
    LocalCandidateCommitReceipt,
)
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan


class FixtureBridge:
    def __init__(self, receipt, **_kwargs):
        self.receipt = receipt

    def require(self, run_id):
        if run_id != self.receipt.run_id:
            raise ValueError("foreign run")
        return self.receipt


class FixtureCommitter:
    def __init__(self, receipt, **_kwargs):
        self.receipt = receipt

    def commit(self, run_id):
        if run_id != self.receipt.run_id:
            raise ValueError("foreign run")
        return self.receipt


class CandidateAdapterTests(scope_fixture.ScopePlannerTests):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        self.git("init", "-q")
        name, email = validated_agent_git_identity()
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)
        (self.source / "Tasks").mkdir()
        (self.source / "Pipeline/TaskGraph").mkdir(parents=True)
        (self.source / "Pipeline/TaskGraph/taskcontrol.py").write_text(
            "print('taskcontrol validate: PASS')\n")
        (self.source / "Assets/NoSafeCircle/Feature/Tests").mkdir(parents=True)
        (self.source / "Assets/NoSafeCircle/Feature/Feature.cs").write_text("class Feature {}\n")
        (self.source / "Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs").write_text("class FeatureTests {}\n")
        (self.source / "Tasks/NSC-042.yaml").write_text(json.dumps({
            "id": "NSC-042", "title": "Fixture", "contract_disposition": "active",
            "depends_on": [], "exclusive_resources": [
                "repo-file:Assets/NoSafeCircle/Feature/Feature.cs"],
        }))
        self.git("add", ".")
        self.git("commit", "-q", "-m", "fixture")
        from Pipeline.AssistantControl.checkouts import Checkouts
        import tempfile as _tempfile
        self.checkouts = Checkouts(self.source, Path(self.temp.name) / "checkouts")
        self.checkout = Path(self.checkouts.prepare("NSC-042")["checkout"])
        self.accepted = self.planner_scope()
        record = json.loads((self.checkouts.records / "NSC-042.json").read_text())
        self.base = record["source_commit"]
        self.receipt = LocalCandidateCommitReceipt(
            task_id="NSC-042", lease_id="assistant-lease-1", plan_id=self.accepted["plan_id"],
            run_id="crew-run", source_base=self.base, candidate_commit="1" * 40,
            candidate_tree="2" * 40, candidate_parent=self.base,
            task_contract_sha256=record["task_contract_sha256"],
            execution_result_sha256="3" * 64, candidate_patch_sha256="4" * 64,
            changed_paths=("Assets/NoSafeCircle/Feature/Feature.cs",),
            validation_sha256="5" * 64,
        )

    def planner_scope(self):
        return self._plan_result

    @property
    def _plan_result(self):
        from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
        return __import__("Pipeline.AssistantControl.scope", fromlist=["AssistantScopePlanner"]).AssistantScopePlanner(self.checkouts).plan(
            "NSC-042", ExecutionScopePlan(
                ("Assets/NoSafeCircle/Feature/Feature.cs",), (),
                ("Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs",), (),
            ), lease_id="assistant-lease-1")

    def bridge(self, **kwargs):
        return FixtureBridge(ExecutionCrewReceipt(
            run_id="crew-run", task_id="NSC-042", lease_id="assistant-lease-1",
            plan_id=self.accepted["plan_id"], provider="claude", execution_model=None,
            execution_reasoning_effort=None, crew_profile="full", validation_profile="full_relevant",
            source_head=self.base, task_contract_sha256=self.receipt.task_contract_sha256,
            crew_status="review_ready", result_path="fixture-result", result_sha256="3" * 64,
            candidate_path="fixture-patch", candidate_sha256="4" * 64,
            final_actual_changed_paths=self.receipt.changed_paths, returncode=0, rejection_reasons=(),
        ))

    def committer(self, **kwargs):
        return FixtureCommitter(self.receipt)

    def test_registers_verified_fixture_receipt_as_awaiting_human(self):
        result = register_candidate(
            self.checkouts, "NSC-042", "crew-run", bridge_factory=self.bridge,
            committer_factory=self.committer,
        )
        self.assertEqual("awaiting_human", result["status"])
        self.assertIsNone(result["approval"])
        self.assertEqual("1" * 40, result["candidate"]["commit"])
        persisted = json.loads((self.checkouts.records / "NSC-042.json").read_text())
        self.assertEqual(result["candidate"], persisted["candidate"])

    def test_rejects_foreign_bridge_identity_and_preserves_record(self):
        original = json.loads((self.checkouts.records / "NSC-042.json").read_text())

        def foreign(**kwargs):
            bridge = self.bridge(**kwargs)
            bridge.receipt = ExecutionCrewReceipt(**{
                **bridge.receipt.__dict__, "lease_id": "foreign-lease",
            })
            return bridge

        with self.assertRaisesRegex(CandidateRegistrationError, "identity differs"):
            register_candidate(self.checkouts, "NSC-042", "crew-run", bridge_factory=foreign,
                               committer_factory=self.committer)
        self.assertEqual(original, json.loads((self.checkouts.records / "NSC-042.json").read_text()))

    def test_changed_checkout_fails_closed_without_reset(self):
        checkout = Path(self.checkouts.root / "NSC-042")
        target = checkout / "Assets/NoSafeCircle/Feature/Feature.cs"
        target.write_text("Vincent's dirty file\n")
        with self.assertRaisesRegex(CandidateRegistrationError, "retained state"):
            register_candidate(self.checkouts, "NSC-042", "crew-run", bridge_factory=self.bridge,
                               committer_factory=self.committer)
        self.assertEqual("Vincent's dirty file\n", target.read_text())

    def test_edited_scope_source_or_contract_fails_closed(self):
        path = self.checkouts.records / "NSC-042.json"
        original = json.loads(path.read_text())
        edited = dict(original)
        edited_scope = dict(edited["scope"])
        edited_scope["source_head"] = "0" * 40
        edited["scope"] = edited_scope
        path.write_text(json.dumps(edited))
        with self.assertRaisesRegex(CandidateRegistrationError, "retained state"):
            register_candidate(self.checkouts, "NSC-042", "crew-run", bridge_factory=self.bridge,
                               committer_factory=self.committer)
        edited_scope["source_head"] = original["scope"]["source_head"]
        edited_scope["task_contract_sha256"] = "f" * 64
        path.write_text(json.dumps({**original, "scope": edited_scope}))
        with self.assertRaisesRegex(CandidateRegistrationError, "retained state"):
            register_candidate(self.checkouts, "NSC-042", "crew-run", bridge_factory=self.bridge,
                               committer_factory=self.committer)

    def test_integrating_status_rejects_registration(self):
        path = self.checkouts.records / "NSC-042.json"
        record = json.loads(path.read_text())
        record["status"] = "integrating"
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(CandidateRegistrationError, "not accepting"):
            register_candidate(self.checkouts, "NSC-042", "crew-run", bridge_factory=self.bridge,
                               committer_factory=self.committer)


class CandidateRecoveryTests(unittest.TestCase):
    """Real bridge/committer recovery test; artifacts are fixture evidence only."""

    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        self.git("init", "-q")
        name, email = validated_agent_git_identity()
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)
        (self.source / "Tasks").mkdir()
        (self.source / "Pipeline/TaskGraph").mkdir(parents=True)
        (self.source / "Pipeline/TaskGraph/taskcontrol.py").write_text(
            "print('taskcontrol validate: PASS')\n")
        (self.source / "Assets/NoSafeCircle/Feature/Tests").mkdir(parents=True)
        (self.source / "Assets/NoSafeCircle/Feature/Feature.cs").write_text("class Feature {}\n")
        (self.source / "Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs").write_text("class FeatureTests {}\n")
        (self.source / "Tasks/NSC-042.yaml").write_text(json.dumps({
            "id": "NSC-042", "title": "Fixture", "contract_disposition": "active",
            "depends_on": [], "exclusive_resources": [
                "repo-file:Assets/NoSafeCircle/Feature/Feature.cs"],
        }))
        self.git("add", ".")
        self.git("commit", "-q", "-m", "fixture")
        from Pipeline.AssistantControl.checkouts import Checkouts
        self.checkouts = Checkouts(self.source, Path(self.temp.name) / "checkouts")
        self.checkout = Path(self.checkouts.prepare("NSC-042")["checkout"])
        from Pipeline.AssistantControl.scope import AssistantScopePlanner
        AssistantScopePlanner(self.checkouts).plan(
            "NSC-042", self.valid(), lease_id="recovery-lease")
        self.record_path = self.checkouts.records / "NSC-042.json"
        self.record = json.loads(self.record_path.read_text())
        self.checkout = Path(self.record["checkout"])
        self.run_id = "crew-recovery-run"
        self.result_path = Path(self.temp.name) / "crew-result.json"
        self.patch_path = Path(self.temp.name) / "candidate.patch"
        self.result_path.write_text('{"pipeline_generated_paths": []}\n', encoding="utf-8")
        # Keep candidate patch content LF-normalized even when the Windows
        # machine has core.autocrlf enabled. A CR embedded in a binary patch is
        # real trailing whitespace and production correctly rejects it.
        (self.checkout / "Assets/NoSafeCircle/Feature/Feature.cs").write_bytes(
            b"class RecoveredFeature {}\n")
        (self.checkout / "Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs").write_bytes(
            b"class RecoveredFeatureTests {}\n")
        self.patch_path.write_bytes(self.git_bytes("diff", "--binary"))
        self.git_bytes("restore", "--", ".")
        self.receipt = ExecutionCrewReceipt(
            run_id=self.run_id, task_id="NSC-042", lease_id="recovery-lease",
            plan_id=self.record["scope"]["plan_id"], provider="claude",
            execution_model="recovery-model", execution_reasoning_effort=None,
            crew_profile="full", validation_profile="full_relevant",
            source_head=self.record["source_commit"],
            task_contract_sha256=self.record["task_contract_sha256"],
            crew_status="review_ready", result_path=str(self.result_path),
            result_sha256=__import__("hashlib").sha256(self.result_path.read_bytes()).hexdigest(),
            candidate_path=str(self.patch_path),
            candidate_sha256=__import__("hashlib").sha256(self.patch_path.read_bytes()).hexdigest(),
            final_actual_changed_paths=(
                "Assets/NoSafeCircle/Feature/Feature.cs",
                "Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs",
            ), returncode=0, rejection_reasons=(),
        )
        scope = __import__("Pipeline.AssistantControl.candidate", fromlist=["_scope"])._scope(
            self.checkouts, self.record)
        bridge = ExecutionCrewBridge(
            checkout=self.checkout, scope=scope, execution_model="recovery-model",
            crew_profile="full", validation_profile="full_relevant")
        bridge._persist(self.receipt)  # fixture setup of the real bridge receipt store
        bridge = ExecutionCrewBridge(
            checkout=self.checkout, scope=scope, execution_model="recovery-model",
            crew_profile="full", validation_profile="full_relevant")
        self.git_bytes("apply", "--binary", str(self.patch_path))
        name, email = validated_agent_git_identity()
        self.git_bytes("config", "user.name", name)
        self.git_bytes("config", "user.email", email)
        self.git_bytes("add", "--", *self.receipt.final_actual_changed_paths)
        self.git_bytes("commit", "-m", "Fixture candidate", "-m",
                       f"ExecutionCrew-Run: {self.receipt.run_id}\n"
                       f"ExecutionCrew-Result-SHA256: {self.receipt.result_sha256}\n"
                       f"ExecutionCrew-Candidate-SHA256: {self.receipt.candidate_sha256}\n"
                       f"Task-Contract-SHA256: {self.receipt.task_contract_sha256}\n"
                       "Local-Candidate-Only: true\n")
        self.assertNotEqual(self.record["source_commit"],
                            self.git_bytes("rev-parse", "HEAD").decode().strip())

    def git_bytes(self, *args):
        import subprocess
        return subprocess.run(["git", "-C", str(self.checkout), *args],
                              capture_output=True, check=True).stdout

    def valid(self):
        return ExecutionScopePlan(
            ("Assets/NoSafeCircle/Feature/Feature.cs",), (),
            ("Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs",), (),
        )

    def git(self, *args):
        import subprocess
        return subprocess.run(["git", "-C", str(self.source), *args],
                              capture_output=True, check=True).stdout

    def test_recovery_uses_real_constructor_and_committer(self):
        result = register_candidate(
            self.checkouts, "NSC-042", self.run_id,
            {"execution_model": "recovery-model", "crew_profile": "full",
             "validation_profile": "full_relevant"})
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual(self.run_id, result["candidate"]["run_id"])
        self.assertEqual(self.git_bytes("rev-parse", "HEAD").decode().strip(),
                         result["candidate"]["commit"])
        self.assertFalse(any(self.checkouts.records.glob(".candidate-recovery-*")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
