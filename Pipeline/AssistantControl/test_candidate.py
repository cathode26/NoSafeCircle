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


class ReceiptDeclineDiagnosisTests(unittest.TestCase):
    """`require` used to answer ONE sentence for eight different causes.

    "candidate integration requires the current run_id" named the caller's
    argument for every decline in `_load_current`, including the ones where the
    argument was perfectly correct -- eight distinct conditions, one sentence.

    THE CASE THAT MOTIVATED THIS WAS WITHDRAWN BY ITS REPORTER, AND THE FIX STANDS
    ANYWAY. The report said two crew results were stranded paid work; NSC-082's
    deliverables were already on main and its patch duplicated them. Worse for the
    original framing, that report's own call had passed the ASSISTANT run id rather
    than the crew's, so the sentence may have been literally correct in the only
    case anyone raised. What survives is measured independently and is why these
    tests exist: eight silent declines cannot share one message. And the run_id
    branch now prints BOTH ids, which is exactly what would have ended that
    investigation in one line instead of an hour.

    These drive the bridge directly with a SimpleNamespace scope, the shape
    `quota_failover_smoke_test.py` already uses, because `_load_current` and
    `require` read only `scope.task_id` and `scope.accepted` -- and because
    reconstructing a real scope is a separate mechanism that refuses for its own
    reasons and hid these messages on my first attempt.
    """

    TASK = "NSC-042"
    RUN = "nsc-042-20260923t094010z"

    def setUp(self):
        import tempfile
        from types import SimpleNamespace
        temporary = tempfile.TemporaryDirectory(prefix="receipt-decline-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        outputs = self.root / "outputs"
        outputs.mkdir()
        self.result_path = outputs / "crew_result.json"
        self.candidate_path = outputs / "candidate.patch"
        self.result_path.write_bytes(b'{"status": "review_ready"}\n')
        self.candidate_path.write_bytes(b"diff --git a/x b/x\n")
        self.accepted = SimpleNamespace(
            task_id=self.TASK, lease_id="lease-1", plan_id="plan-1",
            source_head="0" * 40, task_contract_sha256="a" * 64)
        self.scope = SimpleNamespace(task_id=self.TASK, accepted=self.accepted)

    def receipt(self, **overrides):
        import hashlib
        fields = dict(
            run_id=self.RUN, task_id=self.TASK, lease_id="lease-1", plan_id="plan-1",
            provider="claude", execution_model="claude-sonnet-5",
            execution_reasoning_effort=None, crew_profile="full",
            validation_profile="full_relevant", source_head="0" * 40,
            task_contract_sha256="a" * 64, crew_status="review_ready",
            result_path=str(self.result_path),
            result_sha256=hashlib.sha256(self.result_path.read_bytes()).hexdigest(),
            candidate_path=str(self.candidate_path),
            candidate_sha256=hashlib.sha256(self.candidate_path.read_bytes()).hexdigest(),
            final_actual_changed_paths=(), returncode=0, rejection_reasons=(),
        )
        fields.update(overrides)
        return ExecutionCrewReceipt(**fields)

    def bridge(self, **overrides):
        options = dict(checkout=self.checkout, scope=self.scope,
                       execution_model="claude-sonnet-5", crew_profile="full",
                       validation_profile="full_relevant")
        options.update(overrides)
        return ExecutionCrewBridge(**options)

    def test_no_persisted_receipt_says_so_instead_of_blaming_the_run_id(self):
        with self.assertRaises(Exception) as caught:
            self.bridge().require(self.RUN)
        message = str(caught.exception)
        self.assertIn("no authenticated ExecutionCrew receipt is loaded", message)
        self.assertIn("has ever been persisted", message)
        self.assertIn("NSC-042.execution.json", message)
        self.assertNotIn("requires the current run_id", message)

    def test_a_receipt_that_does_not_match_this_bridge_names_the_field_and_both_values(self):
        """A later session rebuilds the bridge from the crew's own config, and one
        wrong field used to decline in silence. Name it, and name what each side holds."""

        self.bridge()._persist(self.receipt())
        with self.assertRaises(Exception) as caught:
            self.bridge(execution_model="a-different-model").require(self.RUN)
        message = str(caught.exception)
        self.assertIn("does not belong to this bridge", message)
        self.assertIn("execution_model", message)
        self.assertIn("a-different-model", message)
        self.assertIn("claude-sonnet-5", message)

    def test_a_loaded_receipt_for_another_run_names_both_runs(self):
        """The OTHER fault the single sentence conflated. It must stay separable:
        this one really IS about the run_id, and only this one."""

        self.bridge()._persist(self.receipt())
        with self.assertRaises(Exception) as caught:
            self.bridge().require("a-run-this-bridge-never-saw")
        message = str(caught.exception)
        self.assertIn(self.RUN, message)
        self.assertIn("a-run-this-bridge-never-saw", message)
        self.assertNotIn("no authenticated ExecutionCrew receipt is loaded", message)

    def test_a_receipt_this_bridge_accepts_is_loaded_by_a_SECOND_bridge(self):
        """The control, and it is the claim the whole investigation turned on.

        The report that routed this to me concluded a crew whose session ended can
        never be harvested, because `self._receipt` is None at construction. It is
        -- and then `_load_current()` runs on the next line. A second, freshly
        built bridge adopts the persisted receipt, which is what makes an
        after-the-fact harvest possible at all.
        """

        self.bridge()._persist(self.receipt())
        adopted = self.bridge().require(self.RUN)
        self.assertEqual(self.RUN, adopted.run_id)
        self.assertEqual(str(self.candidate_path), adopted.candidate_path)
