"""Real-Git fixture checks for the chained candidate/materialization workflow.

No real Unity process or paid provider is launched. Bridge, committer, Unity
command runner and validation runner are fixture seams, following the same
pattern as test_candidate.py and test_unity_materialization.py.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl import background_jobs
from Pipeline.AssistantControl import candidate
from Pipeline.AssistantControl import post_crew_workflow
from Pipeline.AssistantControl.automation_policy import authenticate_passing_validations
from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.post_crew_workflow import (
    PostCrewWorkflowError,
    run_post_crew_workflow,
)
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.AssistantControl.source_update import synchronize_candidate
from Pipeline.AssistantControl.unity_materialization import MaterializationError
from Pipeline.AssistantControl.viewer import AssistantSnapshot
from Pipeline.TaskReviewAgent.authoritative_candidate_validation import (
    AuthoritativeCandidateValidationError,
)
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.contracts import TaskReviewContractError
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewReceipt
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity
from Pipeline.TaskReviewAgent.local_candidate_commit import LocalCandidateCommitReceipt


BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs"
TEST = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPrototypeSceneBuilderTests.cs"
WALL = "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/WallTile.asset"
SCENE = "Assets/Scenes/DoorPrototype.unity"
FEATURE = "Assets/NoSafeCircle/Feature/Feature.cs"
FEATURE_TEST = "Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(("git", "-C", str(root), *args), capture_output=True, check=False)
    if result.returncode:
        raise AssertionError(result.stderr.decode(errors="replace"))
    return result.stdout.decode().strip()


class _RealCommitFixtureCommitter:
    """Performs one real Git commit and returns its matching receipt."""

    def __init__(self, checkout: Path, receipt_template: dict, paths: tuple[str, ...], **_kwargs):
        self.checkout = checkout
        self.receipt_template = receipt_template
        self.paths = paths

    def commit(self, run_id: str) -> LocalCandidateCommitReceipt:
        _git(self.checkout, "add", "--", *self.paths)
        _git(self.checkout, "commit", "-q", "-m", "crew code candidate")
        commit = _git(self.checkout, "rev-parse", "HEAD")
        tree = _git(self.checkout, "rev-parse", "HEAD^{tree}")
        return LocalCandidateCommitReceipt(
            **{
                **self.receipt_template,
                "run_id": run_id, "candidate_commit": commit, "candidate_tree": tree,
                "changed_paths": tuple(sorted(self.paths, key=str.casefold)),
            }
        )


class _FixtureBridge:
    def __init__(self, receipt: ExecutionCrewReceipt, **_kwargs):
        self.receipt = receipt

    def require(self, run_id: str) -> ExecutionCrewReceipt:
        if run_id != self.receipt.run_id:
            raise ValueError("foreign run")
        return self.receipt


class PostCrewWorkflowDoorPrototypeTests(unittest.TestCase):
    """A task whose scope registers the DoorPrototype Unity builder."""

    def setUp(self):
        test_root = Path.cwd() / ".test-work"
        test_root.mkdir(exist_ok=True)
        self.root = test_root / f"post-crew-workflow-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.source = self.root / "source"
        self.source.mkdir()
        _git(self.source, "init", "-q")
        name, email = validated_agent_git_identity()
        _git(self.source, "config", "user.name", name)
        _git(self.source, "config", "user.email", email)
        for relative, content in (
            (BUILDER, "class DoorPrototypeSceneBuilder {}\n"),
            (TEST, "class DoorPrototypeSceneBuilderTests {}\n"),
            (WALL, "old wall\n"),
            (SCENE, "old scene\n"),
            ("ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 6000.1.8f1\n"),
            ("Pipeline/Testing/run_unity_tests_clean.ps1", "# fixture\n"),
            ("Pipeline/TaskGraph/taskcontrol.py", "print('taskcontrol validate: PASS')\n"),
        ):
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        task = {
            "schema_version": "2.0", "id": "NSC-042", "contract_revision": 1,
            "contract_disposition": "active", "title": "Fixture wall",
            "reconciliation_key": "fixture-wall", "kind": "implementation",
            "type": "world-foundation", "execution_scope": "single_agent",
            "execution_reason": "fixture", "decomposition_state": "concrete",
            "decomposition_reason": "fixture", "parent": None, "depends_on": [],
            "exclusive_resources": [
                f"repo-file:{BUILDER}", f"repo-file:{TEST}", f"repo-file:{WALL}",
                f"unity-scene:{SCENE}",
            ],
            "acceptance_criteria": [], "completion_gates": [],
            "downstream_integration_obligations": [], "gdd_evidence": [],
            "basis": "direct_gdd", "source_scope": "required", "confidence": "high",
        }
        task_path = self.source / "Tasks/NSC-042.yaml"
        task_path.parent.mkdir()
        task_path.write_text(json.dumps(task), encoding="utf-8", newline="\n")
        _git(self.source, "add", ".")
        _git(self.source, "commit", "-q", "-m", "fixture")
        self.manager = Checkouts(self.source, self.root / "checkouts")
        prepared = self.manager.prepare("NSC-042")
        self.checkout = Path(prepared["checkout"])
        self.unity = self.root / "Unity.exe"
        self.unity.write_bytes(b"fixture")
        self.scope = AssistantScopePlanner(self.manager).plan(
            "NSC-042",
            ExecutionScopePlan((BUILDER, WALL, SCENE), (), (TEST,), ()),
            lease_id="fixture-lease",
        )
        record = json.loads((self.manager.records / "NSC-042.json").read_text())
        self.receipt_template = dict(
            task_id="NSC-042", lease_id="fixture-lease", plan_id=self.scope["plan_id"],
            source_base=record["source_commit"], candidate_parent=record["source_commit"],
            task_contract_sha256=record["task_contract_sha256"],
            execution_result_sha256="a" * 64, candidate_patch_sha256="b" * 64,
            validation_sha256="c" * 64,
        )

    def bridge(self, **_kwargs):
        receipt = ExecutionCrewReceipt(
            run_id="fixture-crew", task_id="NSC-042", lease_id="fixture-lease",
            plan_id=self.scope["plan_id"], provider="claude", execution_model=None,
            execution_reasoning_effort=None, crew_profile="full", validation_profile="full_relevant",
            source_head=self.receipt_template["source_base"],
            task_contract_sha256=self.receipt_template["task_contract_sha256"],
            crew_status="review_ready", result_path="fixture-result", result_sha256="a" * 64,
            candidate_path="fixture-patch", candidate_sha256="b" * 64,
            final_actual_changed_paths=(BUILDER, TEST), returncode=0, rejection_reasons=(),
        )
        return _FixtureBridge(receipt)

    def committer(self, **_kwargs):
        (self.checkout / BUILDER).write_text("class FixedBuilder {}\n", newline="\n")
        (self.checkout / TEST).write_text("class FixedTests {}\n", newline="\n")
        return _RealCommitFixtureCommitter(
            self.checkout, self.receipt_template, (BUILDER, TEST))

    def builder_runner(self, args, cwd, timeout):
        self.assertEqual(self.checkout.resolve(), cwd.resolve())
        (cwd / WALL).write_text("generated wall\n", newline="\n")
        (cwd / SCENE).write_text("generated scene\n", newline="\n")
        return subprocess.CompletedProcess(args, 0, b"builder complete\n", b"")

    def passing_validation(self, **kwargs):
        commit = _git(kwargs["checkout"], "rev-parse", "HEAD")
        return ({
            "test_platform": "EditMode", "test_filter": "DoorPrototypeSceneBuilderTests",
            "commit": commit, "tree": _git(kwargs["checkout"], "rev-parse", "HEAD^{tree}"),
            "total": 3, "passed": 3,
        },)

    def run_workflow(self, **overrides):
        kwargs = dict(
            unity_executable=self.unity, bridge_factory=self.bridge,
            committer_factory=self.committer, unity_command_runner=self.builder_runner,
            validation_runner=self.passing_validation,
        )
        kwargs.update(overrides)
        return run_post_crew_workflow(self.manager, "NSC-042", "fixture-crew", {}, **kwargs)

    def test_registers_materializes_and_validates_in_one_call(self):
        result = self.run_workflow()
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual("NSC-042", result["task_id"])
        self.assertEqual(str(self.checkout), result["checkout"])
        self.assertIsNotNone(result["crew_candidate_commit"])
        self.assertNotEqual(result["crew_candidate_commit"], result["materialized_candidate_commit"])
        self.assertEqual([WALL, SCENE], result["generated_paths"])
        self.assertTrue(result["unity_log_path"])
        self.assertEqual(3, result["focused_test_results"][0]["passed"])
        self.assertIn("Unity Editor", result["visual_reproduction_instructions"])
        self.assertEqual(
            result["materialized_candidate_commit"], _git(self.checkout, "rev-parse", "HEAD"))

    def test_rerun_after_success_is_idempotent_and_does_not_recommit(self):
        first = self.run_workflow()
        calls = {"builder": 0}

        def counting_builder(args, cwd, timeout):
            calls["builder"] += 1
            return self.builder_runner(args, cwd, timeout)

        second = self.run_workflow(unity_command_runner=counting_builder)
        self.assertEqual(first, second)
        self.assertEqual(0, calls["builder"])

    def test_unity_unavailable_reports_needs_materialization(self):
        missing = self.root / "does-not-exist" / "Unity.exe"
        result = self.run_workflow(unity_executable=missing)
        self.assertEqual("NEEDS_MATERIALIZATION", result["status"])
        self.assertIsNone(result["materialized_candidate_commit"])
        self.assertEqual([WALL, SCENE], result["generated_paths"])
        self.assertIn(str(missing), result["materialization_error"])
        self.assertIn("materialize-candidate", result["next_action_command"])
        self.assertIn("NSC-042", result["next_action_command"])
        self.assertTrue(Path(result["materialization_record_path"]).is_file())
        # The candidate is retained as a plain crew-reviewed commit, not a
        # source-code failure; no materialized commit exists on top of it.
        record = json.loads((self.manager.records / "NSC-042.json").read_text())
        self.assertEqual("needs_materialization", record["status"])
        self.assertEqual("crew_reviewed", record["candidate"].get("kind", "crew_reviewed"))
        row = next(
            item for item in AssistantSnapshot(self.source, self.manager.root).build()["tasks"]
            if item["id"] == "NSC-042"
        )
        self.assertEqual("blocked", row["state"])
        self.assertEqual("needs_materialization", row["progress"]["phase"])
        with self.assertRaisesRegex(ValueError, "has not completed required Unity"):
            ReviewGate(self.manager).decide(
                "NSC-042", tested_commit=result["crew_candidate_commit"],
                decision="approve", message="looks good",
            )

        retried = self.run_workflow()
        self.assertEqual("awaiting_human", retried["status"])
        self.assertNotEqual(
            retried["crew_candidate_commit"], retried["materialized_candidate_commit"])
        record = json.loads((self.manager.records / "NSC-042.json").read_text())
        self.assertEqual("awaiting_human", record["status"])
        self.assertNotIn("materialization_failure", record)

    def test_malformed_registered_scope_cannot_skip_required_materialization(self):
        missing = self.root / "does-not-exist" / "Unity.exe"
        self.run_workflow(unity_executable=missing)
        record_path = self.manager.records / "NSC-042.json"
        record = json.loads(record_path.read_text())
        record["scope"]["plan"] = "malformed"
        record_path.write_text(json.dumps(record, indent=2) + "\n")

        with self.assertRaisesRegex(PostCrewWorkflowError, "scope is malformed"):
            self.run_workflow()

    def test_focused_test_failure_reports_validation_failed_with_revise_command(self):
        def failing_validation(**_kwargs):
            raise AuthoritativeCandidateValidationError(
                "candidate EditMode test failed: pattern phase reset")

        result = self.run_workflow(validation_runner=failing_validation)
        self.assertEqual("validation_failed", result["status"])
        self.assertIsNotNone(result["materialized_candidate_commit"])
        self.assertIn("pattern phase reset", result["validation_error"])
        self.assertIn("revise", result["next_action_command"])
        self.assertIn(result["materialized_candidate_commit"], result["next_action_command"])
        row = next(
            item for item in AssistantSnapshot(self.source, self.manager.root).build()["tasks"]
            if item["id"] == "NSC-042"
        )
        self.assertEqual("blocked", row["state"])
        self.assertEqual("unity_validation_failed", row["progress"]["phase"])
        self.assertIn("pattern phase reset", row["progress"]["blocked_reason"])

    def test_rerun_after_validation_failure_does_not_relaunch_unity(self):
        def failing_validation(**_kwargs):
            raise AuthoritativeCandidateValidationError("pattern phase reset")

        first = self.run_workflow(validation_runner=failing_validation)

        def exploding_builder(*_args, **_kwargs):
            raise AssertionError("Unity must not be relaunched for a retained failure")

        second = self.run_workflow(
            unity_command_runner=exploding_builder, validation_runner=exploding_builder)
        self.assertEqual(first, second)


CHAPEL_BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/ChapelOfAshSceneBuilder.cs"
CHAPEL_TEST = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms/ChapelOfAshSceneTests.cs"
CHAPEL_SCENE = "Assets/Scenes/Rooms/ChapelOfAsh.unity"
CHAPEL_BUILD_METHOD = "NoSafeCircle.DoorPrototype.Editor.Rooms.ChapelOfAshSceneBuilder.Build"


class PostCrewWorkflowRoomSceneTests(unittest.TestCase):
    """Reproduces the proven NSC-046 failure and proves the registry fix.

    Before this fix, ``is_door_prototype_builder_output`` did not recognize
    ``Assets/Scenes/Rooms/ChapelOfAsh.unity`` as a Unity-builder output, so
    ``_registered_generated_paths`` returned an empty tuple. The workflow then
    treated the task as having no Unity builder and ran focused validation
    directly against the crew commit, which failed with
    ``FileNotFoundException`` because the room scene did not exist yet. This
    fixture proves the workflow now recognizes the exact registered room
    scene and reaches deterministic materialization instead.
    """

    def setUp(self):
        test_root = Path.cwd() / ".test-work"
        test_root.mkdir(exist_ok=True)
        self.root = test_root / f"post-crew-workflow-room-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.source = self.root / "source"
        self.source.mkdir()
        _git(self.source, "init", "-q")
        name, email = validated_agent_git_identity()
        _git(self.source, "config", "user.name", name)
        _git(self.source, "config", "user.email", email)
        for relative, content in (
            (CHAPEL_BUILDER, "class ChapelOfAshSceneBuilder {}\n"),
            (CHAPEL_TEST, "class ChapelOfAshSceneTests {}\n"),
            (CHAPEL_SCENE, "old chapel scene\n"),
            ("ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 6000.1.8f1\n"),
            ("Pipeline/Testing/run_unity_tests_clean.ps1", "# fixture\n"),
            ("Pipeline/TaskGraph/taskcontrol.py", "print('taskcontrol validate: PASS')\n"),
        ):
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        task = {
            "schema_version": "2.0", "id": "NSC-046", "contract_revision": 1,
            "contract_disposition": "active", "title": "Fixture Chapel of Ash room",
            "reconciliation_key": "fixture-chapel", "kind": "implementation",
            "type": "world-foundation", "execution_scope": "single_agent",
            "execution_reason": "fixture", "decomposition_state": "concrete",
            "decomposition_reason": "fixture", "parent": None, "depends_on": [],
            "exclusive_resources": [
                f"repo-file:{CHAPEL_BUILDER}", f"repo-file:{CHAPEL_TEST}",
                f"unity-scene:{CHAPEL_SCENE}",
            ],
            "acceptance_criteria": [], "completion_gates": [],
            "downstream_integration_obligations": [], "gdd_evidence": [],
            "basis": "direct_gdd", "source_scope": "required", "confidence": "high",
        }
        task_path = self.source / "Tasks/NSC-046.yaml"
        task_path.parent.mkdir()
        task_path.write_text(json.dumps(task), encoding="utf-8", newline="\n")
        _git(self.source, "add", ".")
        _git(self.source, "commit", "-q", "-m", "fixture")
        self.manager = Checkouts(self.source, self.root / "checkouts")
        prepared = self.manager.prepare("NSC-046")
        self.checkout = Path(prepared["checkout"])
        self.unity = self.root / "Unity.exe"
        self.unity.write_bytes(b"fixture")
        self.scope = AssistantScopePlanner(self.manager).plan(
            "NSC-046",
            ExecutionScopePlan((CHAPEL_BUILDER, CHAPEL_SCENE), (), (CHAPEL_TEST,), ()),
            lease_id="fixture-lease",
        )
        record = json.loads((self.manager.records / "NSC-046.json").read_text())
        self.receipt_template = dict(
            task_id="NSC-046", lease_id="fixture-lease", plan_id=self.scope["plan_id"],
            source_base=record["source_commit"], candidate_parent=record["source_commit"],
            task_contract_sha256=record["task_contract_sha256"],
            execution_result_sha256="a" * 64, candidate_patch_sha256="b" * 64,
            validation_sha256="c" * 64,
        )

    def bridge(self, **_kwargs):
        receipt = ExecutionCrewReceipt(
            run_id="fixture-crew", task_id="NSC-046", lease_id="fixture-lease",
            plan_id=self.scope["plan_id"], provider="claude", execution_model=None,
            execution_reasoning_effort=None, crew_profile="full", validation_profile="full_relevant",
            source_head=self.receipt_template["source_base"],
            task_contract_sha256=self.receipt_template["task_contract_sha256"],
            crew_status="review_ready", result_path="fixture-result", result_sha256="a" * 64,
            candidate_path="fixture-patch", candidate_sha256="b" * 64,
            final_actual_changed_paths=(CHAPEL_BUILDER, CHAPEL_TEST),
            returncode=0, rejection_reasons=(),
        )
        return _FixtureBridge(receipt)

    def committer(self, **_kwargs):
        (self.checkout / CHAPEL_BUILDER).write_text(
            "class FixedChapelBuilder {}\n", newline="\n")
        (self.checkout / CHAPEL_TEST).write_text("class FixedChapelTests {}\n", newline="\n")
        return _RealCommitFixtureCommitter(
            self.checkout, self.receipt_template, (CHAPEL_BUILDER, CHAPEL_TEST))

    def chapel_builder_runner(self, args, cwd, timeout):
        self.assertEqual(self.checkout.resolve(), cwd.resolve())
        self.assertIn(CHAPEL_BUILD_METHOD, args)
        (cwd / CHAPEL_SCENE).write_text("generated chapel scene\n", newline="\n")
        return subprocess.CompletedProcess(args, 0, b"builder complete\n", b"")

    def passing_validation(self, **kwargs):
        commit = _git(kwargs["checkout"], "rev-parse", "HEAD")
        return ({
            "test_platform": "EditMode", "test_filter": "ChapelOfAshSceneTests",
            "commit": commit, "tree": _git(kwargs["checkout"], "rev-parse", "HEAD^{tree}"),
            "total": 2, "passed": 2,
        },)

    def test_registered_room_scene_reaches_materialization_not_absent_scene_validation(self):
        result = run_post_crew_workflow(
            self.manager, "NSC-046", "fixture-crew", {},
            unity_executable=self.unity, bridge_factory=self.bridge,
            committer_factory=self.committer, unity_command_runner=self.chapel_builder_runner,
            validation_runner=self.passing_validation,
        )
        self.assertEqual([CHAPEL_SCENE], result["generated_paths"])
        self.assertIsNotNone(result["materialized_candidate_commit"])
        self.assertNotEqual(
            result["crew_candidate_commit"], result["materialized_candidate_commit"])
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual(2, result["focused_test_results"][0]["passed"])


class PostCrewWorkflowNoUnityBuilderTests(unittest.TestCase):
    """A task whose scope registers no Unity-serialized generated asset."""

    def setUp(self):
        test_root = Path.cwd() / ".test-work"
        test_root.mkdir(exist_ok=True)
        self.root = test_root / f"post-crew-workflow-nobuilder-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.source = self.root / "source"
        self.source.mkdir()
        _git(self.source, "init", "-q")
        name, email = validated_agent_git_identity()
        _git(self.source, "config", "user.name", name)
        _git(self.source, "config", "user.email", email)
        (self.source / "Tasks").mkdir()
        (self.source / "Pipeline/TaskGraph").mkdir(parents=True)
        (self.source / "Pipeline/TaskGraph/taskcontrol.py").write_text(
            "print('taskcontrol validate: PASS')\n")
        (self.source / "Assets/NoSafeCircle/Feature/Tests").mkdir(parents=True)
        (self.source / FEATURE).write_text("class Feature {}\n")
        (self.source / FEATURE_TEST).write_text("class FeatureTests {}\n")
        (self.source / "Tasks/NSC-100.yaml").write_text(json.dumps({
            "schema_version": "2.0", "id": "NSC-100", "title": "Fixture feature",
            "contract_disposition": "active",
            "depends_on": [], "exclusive_resources": [
                f"repo-file:{FEATURE}", f"repo-file:{FEATURE_TEST}",
            ],
        }))
        _git(self.source, "add", ".")
        _git(self.source, "commit", "-q", "-m", "fixture")
        self.manager = Checkouts(self.source, self.root / "checkouts")
        self.checkout = Path(self.manager.prepare("NSC-100")["checkout"])
        self.scope = AssistantScopePlanner(self.manager).plan(
            "NSC-100", ExecutionScopePlan((FEATURE,), (), (FEATURE_TEST,), ()),
            lease_id="fixture-lease",
        )
        record = json.loads((self.manager.records / "NSC-100.json").read_text())
        self.receipt_template = dict(
            task_id="NSC-100", lease_id="fixture-lease", plan_id=self.scope["plan_id"],
            source_base=record["source_commit"], candidate_parent=record["source_commit"],
            task_contract_sha256=record["task_contract_sha256"],
            execution_result_sha256="a" * 64, candidate_patch_sha256="b" * 64,
            validation_sha256="c" * 64,
        )

    def bridge(self, **_kwargs):
        receipt = ExecutionCrewReceipt(
            run_id="fixture-crew", task_id="NSC-100", lease_id="fixture-lease",
            plan_id=self.scope["plan_id"], provider="claude", execution_model=None,
            execution_reasoning_effort=None, crew_profile="full", validation_profile="full_relevant",
            source_head=self.receipt_template["source_base"],
            task_contract_sha256=self.receipt_template["task_contract_sha256"],
            crew_status="review_ready", result_path="fixture-result", result_sha256="a" * 64,
            candidate_path="fixture-patch", candidate_sha256="b" * 64,
            final_actual_changed_paths=(FEATURE, FEATURE_TEST), returncode=0, rejection_reasons=(),
        )
        return _FixtureBridge(receipt)

    def committer(self, **_kwargs):
        (self.checkout / FEATURE).write_text("class FixedFeature {}\n", newline="\n")
        (self.checkout / FEATURE_TEST).write_text("class FixedFeatureTests {}\n", newline="\n")
        return _RealCommitFixtureCommitter(
            self.checkout, self.receipt_template, (FEATURE, FEATURE_TEST))

    def test_no_unity_builder_skips_materialization_entirely(self):
        def exploding_builder(*_args, **_kwargs):
            raise AssertionError("materialization must not run for a non-Unity task")

        calls = {"validation": 0}

        def passing_validation(**kwargs):
            calls["validation"] += 1
            return ({
                "test_platform": "EditMode", "test_filter": "FixedFeatureTests",
                "commit": kwargs["commit"], "total": 1, "passed": 1,
            },)

        result = run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
            unity_command_runner=exploding_builder, validation_runner=passing_validation,
        )
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual("not_applicable", result["unity_materialization"])
        self.assertIsNone(result["materialized_candidate_commit"])
        self.assertEqual([], result["generated_paths"])
        self.assertIsNotNone(result["crew_candidate_commit"])
        self.assertEqual(1, calls["validation"])
        self.assertEqual(1, result["focused_test_results"][0]["passed"])

        repeated = run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
            unity_command_runner=exploding_builder, validation_runner=passing_validation,
        )
        self.assertEqual(result, repeated)
        self.assertEqual(1, calls["validation"])

    def test_missing_policy_reaches_human_with_no_unity_pass_claim(self):
        result = run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
            unity_command_runner=lambda *_: self.fail("Unity must not run without a policy"),
        )
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual("not_run", result["automated_unity_validation"])
        self.assertEqual([], result["focused_test_results"])
        self.assertIn("no committed authoritative validation policy", result["validation_note"])
        record = json.loads((self.manager.records / "NSC-100.json").read_text())
        self.assertIsNone(record["approval"])
        self.assertIsNone(record["human_review"])
        self.assertNotIn("authoritative_validations", record["candidate"])
        self.assertEqual("not_run", record["candidate_validation_unavailable"]["automated_unity_validation"])
        with self.assertRaisesRegex(ValueError, "requires authoritative validation"):
            authenticate_passing_validations(
                self.manager.records, record, result["crew_candidate_commit"]
            )
        repeated = run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
            unity_command_runner=lambda *_: self.fail("Unity must not run on replay"),
        )
        self.assertEqual(result, repeated)
        self.assertEqual(record, json.loads((self.manager.records / "NSC-100.json").read_text()))

    def test_exact_hash_stale_policy_reaches_human_without_running_unity(self):
        with patch(
            "Pipeline.TaskReviewAgent.downstream_resilience.validation_plan_for",
            side_effect=TaskReviewContractError(
                "authoritative validation policy for NSC-100 is stale"
            ),
        ):
            result = run_post_crew_workflow(
                self.manager, "NSC-100", "fixture-crew", {},
                bridge_factory=self.bridge, committer_factory=self.committer,
                unity_command_runner=lambda *_: self.fail("Unity must not run on stale policy"),
            )
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual("not_run", result["automated_unity_validation"])
        self.assertEqual([], result["focused_test_results"])
        self.assertIn("is stale", result["validation_note"])

    def test_retained_missing_policy_failure_replays_exact_clean_candidate(self):
        error = "NSC-100 has no committed authoritative validation policy"

        def former_validation(**_kwargs):
            raise AuthoritativeCandidateValidationError(error)

        failed = run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
            validation_runner=former_validation,
        )
        self.assertEqual("validation_failed", failed["status"])
        candidate_commit = failed["crew_candidate_commit"]
        recovered = run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
        )
        self.assertEqual("awaiting_human", recovered["status"])
        self.assertEqual(candidate_commit, recovered["crew_candidate_commit"])
        self.assertEqual("not_run", recovered["automated_unity_validation"])
        record = json.loads((self.manager.records / "NSC-100.json").read_text())
        self.assertEqual(candidate_commit, record["candidate"]["commit"])
        self.assertEqual(error, record["candidate_validation_failure_history"][0]["validation_error"])
        self.assertNotIn("candidate_validation_failure", record)
        self.assertNotIn("authoritative_validations", record["candidate"])
        self.assertEqual(recovered, run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
        ))

    def test_retained_policy_failure_rejects_dirty_candidate_replay(self):
        def former_validation(**_kwargs):
            raise AuthoritativeCandidateValidationError(
                "authoritative validation policy for NSC-100 is stale"
            )

        run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
            validation_runner=former_validation,
        )
        (self.checkout / "untracked.txt").write_text("changed\n")
        with self.assertRaisesRegex(ValueError, "uncommitted changes"):
            run_post_crew_workflow(
                self.manager, "NSC-100", "fixture-crew", {},
                bridge_factory=self.bridge, committer_factory=self.committer,
            )
        record = json.loads((self.manager.records / "NSC-100.json").read_text())
        self.assertEqual("validation_failed", record["status"])

    def test_no_builder_validation_failure_is_retained_and_not_human_ready(self):
        def exploding_builder(*_args, **_kwargs):
            raise AssertionError("materialization must not run for a non-Unity task")

        def failing_validation(**_kwargs):
            raise AuthoritativeCandidateValidationError("feature invariant failed")

        result = run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
            unity_command_runner=exploding_builder, validation_runner=failing_validation,
        )
        self.assertEqual("validation_failed", result["status"])
        self.assertIn("feature invariant failed", result["validation_error"])
        record = json.loads((self.manager.records / "NSC-100.json").read_text())
        self.assertEqual("validation_failed", record["status"])
        with self.assertRaisesRegex(ValueError, "failed authoritative Unity validation"):
            ReviewGate(self.manager).decide(
                "NSC-100", tested_commit=result["crew_candidate_commit"],
                decision="approve", message="approve despite failure",
            )
        snapshot = AssistantSnapshot(self.source, self.manager.root).build()
        self.assertNotIn("inspection_error", snapshot, snapshot.get("inspection_error"))
        row = next(
            item for item in snapshot["tasks"]
            if item["id"] == "NSC-100"
        )
        self.assertEqual("blocked", row["state"])
        self.assertEqual("candidate_validation_failed", row["progress"]["phase"])

    def test_late_validation_preserves_newer_integration_receipt(self):
        preserved = {
            "source_before": "1" * 40,
            "candidate": "2" * 40,
            "completed_at": "2026-09-11T08:33:11+00:00",
        }

        def validation_that_finishes_after_integration(**kwargs):
            record_path = self.manager.records / "NSC-100.json"
            record = json.loads(record_path.read_text())
            preserved["candidate"] = kwargs["commit"]
            record["status"] = "integrated"
            record["approval"] = {
                "decision": "approve", "tested_commit": kwargs["commit"],
            }
            record["human_review"] = {"message": "automatic gauntlet approval"}
            record["integration"] = dict(preserved)
            record_path.write_text(json.dumps(record, indent=2) + "\n")
            return ({
                "test_platform": "EditMode", "test_filter": "FixedFeatureTests",
                "commit": kwargs["commit"], "total": 1, "passed": 1,
            },)

        result = run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
            validation_runner=validation_that_finishes_after_integration,
        )
        self.assertEqual("integrated", result["status"])
        record = json.loads((self.manager.records / "NSC-100.json").read_text())
        self.assertEqual("integrated", record["status"])
        self.assertEqual(preserved, record["integration"])
        self.assertEqual("approve", record["approval"]["decision"])
        self.assertEqual(1, record["candidate"]["authoritative_validations"][0]["passed"])

    # -- the other side of the `checkouts.lock` race --------------------------

    def hold_checkouts_lock(self) -> tuple[threading.Event, threading.Thread]:
        """Hold this root's real `checkouts.lock` from another thread until released."""
        lock_path = self.manager.records / "checkouts.lock"
        holding, release = threading.Event(), threading.Event()

        def hold() -> None:
            with _exclusive_file_lock(lock_path, timeout_seconds=30.0):
                holding.set()
                release.wait(60.0)

        holder = threading.Thread(target=hold, name="checkouts-lock-holder", daemon=True)
        self.addCleanup(holder.join, 60.0)
        self.addCleanup(release.set)
        holder.start()
        self.assertTrue(holding.wait(30.0), "the fixture never took checkouts.lock")
        return release, holder

    def passing_validation(self, **kwargs):
        return ({
            "test_platform": "EditMode", "test_filter": "FixedFeatureTests",
            "commit": kwargs["commit"], "total": 1, "passed": 1,
        },)

    def recorded_lock_waits(self, module):
        """Record the exact budget each `checkouts.lock` acquisition in `module` asks for."""
        waits: list[tuple[str, float]] = []
        real = module._exclusive_file_lock

        def spy(path, *, timeout_seconds):
            waits.append((str(path), timeout_seconds))
            return real(path, timeout_seconds=timeout_seconds)

        patcher = patch.object(module, "_exclusive_file_lock", spy)
        patcher.start()
        self.addCleanup(patcher.stop)
        return waits

    def test_a_child_whose_first_registration_lock_attempt_times_out_still_completes(self):
        """A detached child must not become a failed job because the lock was busy.

        A post-crew child takes `checkouts.lock` at candidate registration, and a
        child that loses that wait is recorded `failed`, blocks its task with
        `background_job_failed` and needs an operator `clear-background-job`
        before the planner will issue another ticket. Registration has mutated
        nothing at that point, so it waits far longer than the controller's 10 s
        instead (20260913 run: children 8b97d834... and 4ac95f738c... died exactly
        this way).
        """
        self.assertGreaterEqual(candidate.REGISTRATION_LOCK_TIMEOUT_SECONDS, 120.0)
        self.assertGreater(
            candidate.REGISTRATION_LOCK_TIMEOUT_SECONDS,
            10 * background_jobs.LAUNCH_LOCK_TIMEOUT_SECONDS,
        )
        waits = self.recorded_lock_waits(candidate)
        release, _holder = self.hold_checkouts_lock()
        threading.Timer(1.0, release.set).start()

        result = run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
            validation_runner=self.passing_validation,
        )

        # The registration transaction asked for the long budget, and survived a
        # holder it would have lost to with the graph controller's 10 s.
        self.assertEqual(
            [(str(self.manager.records / "checkouts.lock"),
              candidate.REGISTRATION_LOCK_TIMEOUT_SECONDS)],
            waits,
        )
        self.assertEqual("awaiting_human", result["status"])
        self.assertIsNotNone(result["crew_candidate_commit"])
        record = json.loads((self.manager.records / "NSC-100.json").read_text())
        self.assertEqual(1, record["candidate"]["authoritative_validations"][0]["passed"])

    def test_a_registration_lock_held_past_the_bound_fails_with_the_original_error(self):
        """The registration wait is bounded: a wedged lock is still loud."""
        lock_path = self.manager.records / "checkouts.lock"
        self.hold_checkouts_lock()

        with patch.object(candidate, "REGISTRATION_LOCK_TIMEOUT_SECONDS", 0.2):
            with self.assertRaises(TimeoutError) as raised:
                run_post_crew_workflow(
                    self.manager, "NSC-100", "fixture-crew", {},
                    bridge_factory=self.bridge, committer_factory=self.committer,
                    validation_runner=self.passing_validation,
                )
        self.assertEqual(str(lock_path), raised.exception.filename)
        self.assertIn("timed out after 0.2s waiting for exclusive file lock",
                      str(raised.exception))
        record = json.loads((self.manager.records / "NSC-100.json").read_text())
        self.assertIsNone(record.get("candidate"))

    def test_validation_runs_with_the_checkout_lock_free_and_the_persist_outwaits_it(self):
        """A finished validation is never discarded because the lock was busy.

        `checkouts.lock` is free for the whole validation, so a graph run's other
        record transactions never wait minutes behind one, and the transaction
        that persists the finished facts waits far longer than a launch's budget:
        in the 20260913 Gauntlet run a 10 s wait threw away a completed 75 s Unity
        validation (post-crew job 8b97d834..., 02:56:21Z) while a foreground
        `sync_candidate` held the lock for 16 s.
        """
        self.assertGreaterEqual(
            post_crew_workflow.VALIDATION_PERSIST_LOCK_TIMEOUT_SECONDS, 120.0)
        self.assertGreater(
            post_crew_workflow.VALIDATION_PERSIST_LOCK_TIMEOUT_SECONDS,
            10 * background_jobs.LAUNCH_LOCK_TIMEOUT_SECONDS,
        )
        lock_path = self.manager.records / "checkouts.lock"
        free_during_validation: list[float] = []
        waits = self.recorded_lock_waits(post_crew_workflow)

        def validation_while_another_writer_holds_the_lock(**kwargs):
            # Nothing holds the lock while the validation runs.
            with _exclusive_file_lock(lock_path, timeout_seconds=0.1):
                free_during_validation.append(1.0)
            release, _holder = self.hold_checkouts_lock()
            # The persist then waits out that holder instead of failing.
            threading.Timer(1.0, release.set).start()
            return self.passing_validation(**kwargs)

        result = run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
            validation_runner=validation_while_another_writer_holds_the_lock,
        )

        # The persist transaction asked for the long budget, and survived a holder
        # it would have lost to with the graph controller's 10 s.
        self.assertEqual(
            [(str(lock_path), post_crew_workflow.VALIDATION_PERSIST_LOCK_TIMEOUT_SECONDS)],
            waits,
        )
        self.assertEqual([1.0], free_during_validation)
        self.assertEqual("awaiting_human", result["status"])
        record = json.loads((self.manager.records / "NSC-100.json").read_text())
        self.assertEqual(1, record["candidate"]["authoritative_validations"][0]["passed"])

    def test_a_lock_held_past_the_persist_budget_fails_loudly_and_retains_state(self):
        """The persist is bounded: a wedged lock is still an error, never a silent loss."""
        lock_path = self.manager.records / "checkouts.lock"

        def validation_then_a_wedged_lock(**kwargs):
            self.hold_checkouts_lock()
            return self.passing_validation(**kwargs)

        with patch.object(post_crew_workflow,
                          "VALIDATION_PERSIST_LOCK_TIMEOUT_SECONDS", 0.2):
            with self.assertRaises(TimeoutError) as raised:
                run_post_crew_workflow(
                    self.manager, "NSC-100", "fixture-crew", {},
                    bridge_factory=self.bridge, committer_factory=self.committer,
                    validation_runner=validation_then_a_wedged_lock,
                )
        self.assertEqual(str(lock_path), raised.exception.filename)
        record = json.loads((self.manager.records / "NSC-100.json").read_text())
        self.assertEqual([], list(record["candidate"].get("authoritative_validations") or ()))
        self.assertNotIn("candidate_validation_failure", record)

    def test_the_persist_refuses_when_the_candidate_changed_underneath(self):
        """The lock is free during validation, so re-acquiring it reverifies the candidate."""
        record_path = self.manager.records / "NSC-100.json"

        def validation_while_the_candidate_is_replaced(**kwargs):
            record = json.loads(record_path.read_text())
            record["candidate"] = {**record["candidate"], "commit": "9" * 40}
            record_path.write_text(json.dumps(record, indent=2) + "\n")
            return self.passing_validation(**kwargs)

        with self.assertRaises(PostCrewWorkflowError) as raised:
            run_post_crew_workflow(
                self.manager, "NSC-100", "fixture-crew", {},
                bridge_factory=self.bridge, committer_factory=self.committer,
                validation_runner=validation_while_the_candidate_is_replaced,
            )
        self.assertIn("candidate changed while authoritative validation was running",
                      str(raised.exception))
        record = json.loads(record_path.read_text())
        self.assertEqual("9" * 40, record["candidate"]["commit"])
        self.assertIsNone(record["candidate"].get("authoritative_validations"))

    def test_source_synchronized_candidate_is_revalidated_without_reregistering_crew(self):
        def passing_validation(**kwargs):
            return ({
                "test_platform": "EditMode", "test_filter": "FixedFeatureTests",
                "commit": kwargs["commit"], "total": 1, "passed": 1,
            },)

        first = run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=self.bridge, committer_factory=self.committer,
            validation_runner=passing_validation,
        )
        old_candidate = first["crew_candidate_commit"]
        (self.source / "unrelated.txt").write_text("later source\n", newline="\n")
        _git(self.source, "add", "unrelated.txt")
        _git(self.source, "commit", "-q", "-m", "advance source")
        source_head = _git(self.source, "rev-parse", "HEAD")
        synchronized = synchronize_candidate(
            self.manager, "NSC-100", old_candidate, source_head,
        )
        sync_commit = synchronized["candidate"]["commit"]

        def must_not_register(*_args, **_kwargs):
            raise AssertionError("the retained crew candidate must not be registered again")

        result = run_post_crew_workflow(
            self.manager, "NSC-100", "fixture-crew", {},
            bridge_factory=must_not_register, committer_factory=must_not_register,
            validation_runner=passing_validation,
        )
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual(sync_commit, result["crew_candidate_commit"])
        self.assertEqual(sync_commit, result["focused_test_results"][0]["commit"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
