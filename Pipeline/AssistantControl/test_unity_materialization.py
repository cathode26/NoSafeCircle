"""Real-Git fixture checks; no real Unity process or provider is launched."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.revisions import begin_revision
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.AssistantControl.unity_materialization import (
    MaterializationError,
    materialize_candidate,
)
from Pipeline.TaskReviewAgent.authoritative_candidate_validation import (
    AuthoritativeCandidateValidationError,
)
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.door_prototype_materialization import (
    DOOR_PROTOTYPE_BUILD_METHOD,
    ROOM_SCENE_BUILDERS,
    DoorPrototypeMaterializationError,
    changed_paths,
    run_door_prototype_builder,
)
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity
from Pipeline.TaskReviewAgent.local_candidate_commit import LocalCandidateCommitReceipt


BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs"
TEST = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPrototypeSceneBuilderTests.cs"
WALL = "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/WallTile.asset"
SCENE = "Assets/Scenes/DoorPrototype.unity"
WIZARD_ROOT = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard"
WIZARD_SOURCE = WIZARD_ROOT + "/Source/approved.png"
WIZARD_CONTROLLER = WIZARD_ROOT + "/Generated/WizardAnimator.controller"


class MaterializationTests(unittest.TestCase):
    def setUp(self):
        # tempfile.TemporaryDirectory applies an ACL that some Windows test
        # sandboxes cannot traverse. Use an ordinary disposable directory.
        test_root = Path.cwd() / ".test-work"
        test_root.mkdir(exist_ok=True)
        self.root = test_root / f"assistant-unity-materialization-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git(self.source, "init", "-q")
        name, email = validated_agent_git_identity()
        self.git(self.source, "config", "user.name", name)
        self.git(self.source, "config", "user.email", email)
        for relative, content in (
            (BUILDER, "class DoorPrototypeSceneBuilder {}\n"),
            (TEST, "class DoorPrototypeSceneBuilderTests {}\n"),
            (WALL, "old wall\n"),
            (SCENE, "old scene\n"),
            (WIZARD_SOURCE, "approved pixels\n"),
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
                f"repo-file:{WIZARD_ROOT}",
                f"unity-scene:{SCENE}",
            ],
            "acceptance_criteria": [], "completion_gates": [],
            "downstream_integration_obligations": [], "gdd_evidence": [],
            "basis": "direct_gdd", "source_scope": "required", "confidence": "high",
        }
        task_path = self.source / "Tasks/NSC-042.yaml"
        task_path.parent.mkdir()
        task_path.write_text(json.dumps(task), encoding="utf-8", newline="\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-q", "-m", "fixture")
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

    @staticmethod
    def git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ("git", "-C", str(root), *args), capture_output=True, check=False,
        )
        if result.returncode:
            raise AssertionError(result.stderr.decode(errors="replace"))
        return result.stdout.decode().strip()

    def register_code_candidate(self, *, include_generated: bool = False) -> str:
        (self.checkout / BUILDER).write_text("class FixedBuilder {}\n", newline="\n")
        (self.checkout / TEST).write_text("class FixedTests {}\n", newline="\n")
        paths = [BUILDER, TEST]
        if include_generated:
            (self.checkout / WALL).write_text("hand-authored wall\n", newline="\n")
            paths.append(WALL)
        self.git(self.checkout, "add", "--", *paths)
        self.git(self.checkout, "commit", "-q", "-m", "crew code candidate")
        commit = self.git(self.checkout, "rev-parse", "HEAD")
        tree = self.git(self.checkout, "rev-parse", "HEAD^{tree}")
        record_path = self.manager.records / "NSC-042.json"
        record = json.loads(record_path.read_text())
        receipt = LocalCandidateCommitReceipt(
            task_id="NSC-042", lease_id="fixture-lease", plan_id=self.scope["plan_id"],
            run_id="fixture-crew", source_base=record["source_commit"],
            candidate_commit=commit, candidate_tree=tree,
            candidate_parent=record["source_commit"],
            task_contract_sha256=record["task_contract_sha256"],
            execution_result_sha256="a" * 64, candidate_patch_sha256="b" * 64,
            changed_paths=tuple(sorted(paths, key=str.casefold)), validation_sha256="c" * 64,
        )
        record["candidate"] = {
            "commit": commit, "tree": tree, "parent": record["source_commit"],
            "run_id": "fixture-crew", "lease_id": "fixture-lease",
            "plan_id": self.scope["plan_id"], "receipt": receipt.to_dict(),
        }
        record["status"] = "awaiting_human"
        record["approval"] = None
        write_record(record_path, record)
        return commit

    def builder_runner(self, args, cwd, timeout):
        self.assertEqual(self.checkout.resolve(), cwd.resolve())
        self.assertIn("NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build", args)
        self.assertGreater(timeout, 0)
        (cwd / WALL).write_text("generated wall  \n", newline="\n")
        (cwd / SCENE).write_text("generated scene  \n", newline="\n")
        return subprocess.CompletedProcess(args, 0, b"builder complete\n", b"")

    def passing_validation(self, **kwargs):
        commit = self.git(kwargs["checkout"], "rev-parse", "HEAD")
        self.assertEqual(kwargs["commit"], commit)
        self.assertEqual("", self.git(kwargs["checkout"], "status", "--porcelain=v1"))
        return ({
            "test_platform": "EditMode",
            "test_filter": "DoorPrototypeSceneBuilderTests",
            "commit": commit,
            "tree": self.git(kwargs["checkout"], "rev-parse", "HEAD^{tree}"),
            "total": 3,
            "passed": 3,
        },)

    def test_shared_builder_materializes_only_registered_outputs(self):
        result = run_door_prototype_builder(
            checkout=self.checkout, task_id="NSC-042",
            state_root=self.manager.records, initial_changed_paths=(),
            unity_executable=self.unity, unity_command_runner=self.builder_runner,
            allowed_generated_paths=tuple(sorted((WALL, SCENE), key=str.casefold)),
        )
        self.assertEqual(tuple(sorted((WALL, SCENE), key=str.casefold)), result.builder_paths)
        self.assertNotIn("  \n", (self.checkout / WALL).read_text())

    def test_nsc_042_policy_runs_the_real_door_prototype_tests(self):
        policy = json.loads((
            Path(__file__).parents[1] / "TaskReviewAgent"
            / "authoritative_validation_policy.json"
        ).read_text(encoding="utf-8"))
        entry = policy["tasks"]["NSC-042"]
        self.assertEqual(
            "NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests",
            entry["test_filters"]["EditMode"],
        )
        self.assertNotIn("GauntletTests", entry["test_filters"]["EditMode"])

    def test_shared_builder_rejects_and_retains_unregistered_output(self):
        def bad_runner(args, cwd, timeout):
            (cwd / "unexpected.asset").write_text("unexpected\n")
            return subprocess.CompletedProcess(args, 0, b"", b"")
        with self.assertRaisesRegex(DoorPrototypeMaterializationError, "untracked paths outside"):
            run_door_prototype_builder(
                checkout=self.checkout, task_id="NSC-042",
                state_root=self.manager.records, initial_changed_paths=(),
                unity_executable=self.unity, unity_command_runner=bad_runner,
                allowed_generated_paths=(WALL,),
            )
        self.assertTrue((self.checkout / "unexpected.asset").is_file())

    def test_nsc032_incidental_enemy_folder_meta_is_authenticated_and_materialized(self):
        folder = "Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies"
        keep = self.checkout / folder / ".gitkeep"
        keep.parent.mkdir(parents=True)
        keep.write_text("\n", encoding="utf-8")
        self.git(self.checkout, "add", "--", f"{folder}/.gitkeep")
        self.git(self.checkout, "commit", "-q", "-m", "tracked enemy folder")
        meta_path = f"{folder}.meta"
        def unity_runner(args, cwd, timeout):
            (cwd / SCENE).write_text("generated scene\n", newline="\n")
            (cwd / meta_path).write_text(
                "fileFormatVersion: 2\nguid: 81075e5cba4420b499b12a31d486b2e6\n"
                "folderAsset: yes\nDefaultImporter:\n  externalObjects: {}\n",
                newline="\n",
            )
            return subprocess.CompletedProcess(args, 0, b"", b"")
        result = run_door_prototype_builder(
            checkout=self.checkout, task_id="NSC-032",
            state_root=self.manager.records, initial_changed_paths=(),
            unity_executable=self.unity, unity_command_runner=unity_runner,
            allowed_generated_paths=(SCENE,),
            incidental_folder_meta_path=meta_path,
        )
        self.assertEqual((meta_path, SCENE), result.builder_paths)
        self.assertEqual((meta_path,), result.authenticated_incidental_meta_paths)
        self.assertTrue((self.checkout / meta_path).exists())
        self.assertTrue(Path(result.incidental_evidence_path).is_file())
        self.assertEqual((meta_path, SCENE), changed_paths(self.checkout))

    def test_nsc032_folder_meta_exception_does_not_hide_other_untracked_paths(self):
        folder = "Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies"
        keep = self.checkout / folder / ".gitkeep"
        keep.parent.mkdir(parents=True)
        keep.write_text("\n", encoding="utf-8")
        self.git(self.checkout, "add", "--", f"{folder}/.gitkeep")
        self.git(self.checkout, "commit", "-q", "-m", "tracked enemy folder")
        meta_path = f"{folder}.meta"
        def unity_runner(args, cwd, timeout):
            (cwd / SCENE).write_text("generated scene\n", newline="\n")
            (cwd / meta_path).write_text(
                "fileFormatVersion: 2\nguid: 81075e5cba4420b499b12a31d486b2e6\n"
                "folderAsset: yes\nDefaultImporter:\n",
                newline="\n",
            )
            (cwd / "unexpected.asset").write_text("not task owned\n")
            return subprocess.CompletedProcess(args, 0, b"", b"")
        with self.assertRaisesRegex(DoorPrototypeMaterializationError, "untracked paths outside"):
            run_door_prototype_builder(
                checkout=self.checkout, task_id="NSC-032",
                state_root=self.manager.records, initial_changed_paths=(),
                unity_executable=self.unity, unity_command_runner=unity_runner,
                allowed_generated_paths=(SCENE,),
                incidental_folder_meta_path=meta_path,
            )
        self.assertTrue((self.checkout / "unexpected.asset").is_file())

    def test_shared_builder_allows_only_serialized_output_under_registered_root(self):
        def art_runner(args, cwd, timeout):
            target = cwd / WIZARD_CONTROLLER
            target.parent.mkdir(parents=True)
            target.write_text("generated controller  \n", newline="\n")
            return subprocess.CompletedProcess(args, 0, b"", b"")
        result = run_door_prototype_builder(
            checkout=self.checkout, task_id="NSC-042",
            state_root=self.manager.records, initial_changed_paths=(),
            unity_executable=self.unity, unity_command_runner=art_runner,
            allowed_generated_paths=(WALL,),
            allowed_generated_roots=(WIZARD_ROOT,),
        )
        self.assertEqual((WIZARD_CONTROLLER,), result.builder_paths)
        self.assertNotIn("  \n", (self.checkout / WIZARD_CONTROLLER).read_text())

    def test_shared_builder_rejects_nonserialized_output_under_registered_root(self):
        unexpected = WIZARD_ROOT + "/Generated/HandAuthored.cs"
        def bad_art_runner(args, cwd, timeout):
            target = cwd / unexpected
            target.parent.mkdir(parents=True)
            target.write_text("class HandAuthored {}\n", newline="\n")
            return subprocess.CompletedProcess(args, 0, b"", b"")
        with self.assertRaisesRegex(DoorPrototypeMaterializationError, "untracked paths outside"):
            run_door_prototype_builder(
                checkout=self.checkout, task_id="NSC-042",
                state_root=self.manager.records, initial_changed_paths=(),
                unity_executable=self.unity, unity_command_runner=bad_art_runner,
                allowed_generated_paths=(WALL,),
                allowed_generated_roots=(WIZARD_ROOT,),
            )
        self.assertTrue((self.checkout / unexpected).is_file())

    def test_materialization_derives_task_owned_generated_art_root(self):
        original = self.register_code_candidate()
        def art_runner(args, cwd, timeout):
            target = cwd / WIZARD_CONTROLLER
            target.parent.mkdir(parents=True)
            target.write_text("generated controller\n", newline="\n")
            return subprocess.CompletedProcess(args, 0, b"", b"")
        result = materialize_candidate(
            self.manager, "NSC-042", original, unity_executable=self.unity,
            unity_command_runner=art_runner,
            validation_runner=self.passing_validation,
        )
        self.assertEqual([WIZARD_CONTROLLER], result["candidate"]["changed_paths"])
        journal = json.loads((
            self.manager.records / f"NSC-042.unity-materialization.{original}.json"
        ).read_text())
        self.assertEqual([WIZARD_ROOT], journal["registered_generated_roots"])

    def test_materializes_then_validates_exact_commit_for_human_review(self):
        original = self.register_code_candidate()
        result = materialize_candidate(
            self.manager, "NSC-042", original, unity_executable=self.unity,
            unity_command_runner=self.builder_runner,
            validation_runner=self.passing_validation,
        )
        candidate = result["candidate"]
        self.assertEqual("unity_materialized", candidate["kind"])
        self.assertFalse(candidate["crew_review"])
        self.assertTrue(candidate["source_candidate_crew_review"])
        self.assertEqual(original, candidate["parent"])
        self.assertEqual("awaiting_human", result["status"])
        self.assertIsNone(result["approval"])
        self.assertEqual(candidate["commit"], self.git(self.checkout, "rev-parse", "HEAD"))
        self.assertEqual(3, candidate["authoritative_validations"][0]["passed"])

    def test_refuses_crew_hand_authored_generated_payload(self):
        original = self.register_code_candidate(include_generated=True)
        with self.assertRaisesRegex(MaterializationError, "already edited Unity-generated"):
            materialize_candidate(
                self.manager, "NSC-042", original, unity_executable=self.unity,
                unity_command_runner=self.builder_runner,
                validation_runner=self.passing_validation,
            )

    def test_validation_failure_is_recorded_for_next_crew(self):
        original = self.register_code_candidate()
        def failing_validation(**_kwargs):
            raise AuthoritativeCandidateValidationError(
                "candidate EditMode test failed: pattern phase reset"
            )
        with self.assertRaisesRegex(MaterializationError, "give this evidence"):
            materialize_candidate(
                self.manager, "NSC-042", original, unity_executable=self.unity,
                unity_command_runner=self.builder_runner,
                validation_runner=failing_validation,
            )
        record = json.loads((self.manager.records / "NSC-042.json").read_text())
        self.assertEqual("validation_failed", record["status"])
        self.assertIn("pattern phase reset", record["materialization_failure"]["validation_error"])
        failed_commit = self.git(self.checkout, "rev-parse", "HEAD")
        self.assertNotEqual(original, failed_commit)
        self.assertEqual("unity_materialization_failed", record["candidate"]["kind"])
        self.assertEqual(failed_commit, record["candidate"]["commit"])
        with self.assertRaisesRegex(ValueError, "cannot be approved"):
            ReviewGate(self.manager).decide(
                "NSC-042", tested_commit=failed_commit,
                decision="approve", message="fixture must remain rejected",
            )
        with self.assertRaisesRegex(MaterializationError, "unfinished Unity materialization"):
            materialize_candidate(
                self.manager, "NSC-042", original, unity_executable=self.unity,
                unity_command_runner=self.builder_runner,
                validation_runner=failing_validation,
            )
        revised = begin_revision(self.manager, "NSC-042", failed_commit)
        self.assertEqual("prepared", revised["status"])
        self.assertEqual("fresh", revised["revision"]["feedback_mode"])
        self.assertIn("pattern phase reset", revised["revision"]["rejected_review"]["message"])
        self.assertEqual(failed_commit, revised["source_commit"])
        self.assertNotIn("candidate", revised)


CHAPEL_BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/ChapelOfAshSceneBuilder.cs"
CHAPEL_TEST = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms/ChapelOfAshSceneTests.cs"
CHAPEL_SCENE = "Assets/Scenes/Rooms/ChapelOfAsh.unity"
CHAPEL_BUILD_METHOD = "NoSafeCircle.DoorPrototype.Editor.Rooms.ChapelOfAshSceneBuilder.Build"
LOWER_VAULT_SCENE = "Assets/Scenes/Rooms/LowerVault.unity"
UNKNOWN_ROOM_SCENE = "Assets/Scenes/Rooms/UnknownRoom.unity"


class RoomSceneMaterializationTests(unittest.TestCase):
    """The exact room-scene registry drives which builder method runs.

    Reproduces the proven NSC-046 failure: a crew candidate that only changes
    a room's own SceneBuilder.cs (never the shared DoorPrototypeSceneBuilder.cs)
    must still be recognized and materialized through its exact registered
    scene, with no wildcard authority over ``Assets/Scenes/Rooms/``.
    """

    def setUp(self):
        test_root = Path.cwd() / ".test-work"
        test_root.mkdir(exist_ok=True)
        self.root = test_root / f"assistant-room-materialization-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git(self.source, "init", "-q")
        name, email = validated_agent_git_identity()
        self.git(self.source, "config", "user.name", name)
        self.git(self.source, "config", "user.email", email)
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
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-q", "-m", "fixture")
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

    @staticmethod
    def git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ("git", "-C", str(root), *args), capture_output=True, check=False,
        )
        if result.returncode:
            raise AssertionError(result.stderr.decode(errors="replace"))
        return result.stdout.decode().strip()

    def register_code_candidate(self) -> str:
        (self.checkout / CHAPEL_BUILDER).write_text(
            "class FixedChapelBuilder {}\n", newline="\n")
        (self.checkout / CHAPEL_TEST).write_text("class FixedChapelTests {}\n", newline="\n")
        paths = [CHAPEL_BUILDER, CHAPEL_TEST]
        self.git(self.checkout, "add", "--", *paths)
        self.git(self.checkout, "commit", "-q", "-m", "crew Chapel room candidate")
        commit = self.git(self.checkout, "rev-parse", "HEAD")
        tree = self.git(self.checkout, "rev-parse", "HEAD^{tree}")
        record_path = self.manager.records / "NSC-046.json"
        record = json.loads(record_path.read_text())
        receipt = LocalCandidateCommitReceipt(
            task_id="NSC-046", lease_id="fixture-lease", plan_id=self.scope["plan_id"],
            run_id="fixture-crew", source_base=record["source_commit"],
            candidate_commit=commit, candidate_tree=tree,
            candidate_parent=record["source_commit"],
            task_contract_sha256=record["task_contract_sha256"],
            execution_result_sha256="a" * 64, candidate_patch_sha256="b" * 64,
            changed_paths=tuple(sorted(paths, key=str.casefold)), validation_sha256="c" * 64,
        )
        record["candidate"] = {
            "commit": commit, "tree": tree, "parent": record["source_commit"],
            "run_id": "fixture-crew", "lease_id": "fixture-lease",
            "plan_id": self.scope["plan_id"], "receipt": receipt.to_dict(),
        }
        record["status"] = "awaiting_human"
        record["approval"] = None
        write_record(record_path, record)
        return commit

    def chapel_builder_runner(self, args, cwd, timeout):
        self.assertEqual(self.checkout.resolve(), cwd.resolve())
        self.assertIn(CHAPEL_BUILD_METHOD, args)
        self.assertNotIn(DOOR_PROTOTYPE_BUILD_METHOD, args)
        (cwd / CHAPEL_SCENE).write_text("generated chapel scene  \n", newline="\n")
        return subprocess.CompletedProcess(args, 0, b"builder complete\n", b"")

    def passing_validation(self, **kwargs):
        commit = self.git(kwargs["checkout"], "rev-parse", "HEAD")
        self.assertEqual(kwargs["commit"], commit)
        self.assertEqual("", self.git(kwargs["checkout"], "status", "--porcelain=v1"))
        return ({
            "test_platform": "EditMode",
            "test_filter": "ChapelOfAshSceneTests",
            "commit": commit,
            "tree": self.git(kwargs["checkout"], "rev-parse", "HEAD^{tree}"),
            "total": 2,
            "passed": 2,
        },)

    def test_room_registry_matches_the_five_approved_scenes(self):
        self.assertEqual(
            {
                "Assets/Scenes/Rooms/RuinedEntry.unity",
                "Assets/Scenes/Rooms/BoneArchive.unity",
                CHAPEL_SCENE,
                LOWER_VAULT_SCENE,
                "Assets/Scenes/Rooms/FinalRoom.unity",
            },
            set(ROOM_SCENE_BUILDERS),
        )
        self.assertEqual(CHAPEL_BUILD_METHOD, ROOM_SCENE_BUILDERS[CHAPEL_SCENE].build_method)
        self.assertEqual(CHAPEL_BUILDER, ROOM_SCENE_BUILDERS[CHAPEL_SCENE].builder_source_path)

    def test_run_door_prototype_builder_invokes_the_registered_room_build_method(self):
        result = run_door_prototype_builder(
            checkout=self.checkout, task_id="NSC-046",
            state_root=self.manager.records, initial_changed_paths=(),
            unity_executable=self.unity, unity_command_runner=self.chapel_builder_runner,
            allowed_generated_paths=(CHAPEL_SCENE,),
        )
        self.assertEqual((CHAPEL_SCENE,), result.builder_paths)
        self.assertNotIn("  \n", (self.checkout / CHAPEL_SCENE).read_text())

    def test_unregistered_room_scene_is_refused_not_wildcard_matched(self):
        def exploding_runner(*_args, **_kwargs):
            raise AssertionError("Unity must not launch for an unregistered room scene")
        with self.assertRaisesRegex(
            DoorPrototypeMaterializationError, "outside the DoorPrototype builder boundary",
        ):
            run_door_prototype_builder(
                checkout=self.checkout, task_id="NSC-046",
                state_root=self.manager.records, initial_changed_paths=(),
                unity_executable=self.unity, unity_command_runner=exploding_runner,
                allowed_generated_paths=(UNKNOWN_ROOM_SCENE,),
            )

    def test_mixed_room_scenes_are_refused_as_ambiguous(self):
        def exploding_runner(*_args, **_kwargs):
            raise AssertionError("Unity must not launch for an ambiguous builder request")
        with self.assertRaisesRegex(
            DoorPrototypeMaterializationError,
            "require more than one builder method",
        ):
            run_door_prototype_builder(
                checkout=self.checkout, task_id="NSC-046",
                state_root=self.manager.records, initial_changed_paths=(),
                unity_executable=self.unity, unity_command_runner=exploding_runner,
                allowed_generated_paths=tuple(sorted(
                    (CHAPEL_SCENE, LOWER_VAULT_SCENE), key=str.casefold,
                )),
            )

    def test_materializes_the_exact_registered_room_scene_for_human_review(self):
        original = self.register_code_candidate()
        result = materialize_candidate(
            self.manager, "NSC-046", original, unity_executable=self.unity,
            unity_command_runner=self.chapel_builder_runner,
            validation_runner=self.passing_validation,
        )
        candidate = result["candidate"]
        self.assertEqual("unity_materialized", candidate["kind"])
        self.assertEqual([CHAPEL_SCENE], candidate["changed_paths"])
        self.assertEqual(CHAPEL_BUILD_METHOD, candidate["materialization"]["builder"])
        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual(candidate["commit"], self.git(self.checkout, "rev-parse", "HEAD"))
        journal_path = (
            self.manager.records / f"NSC-046.unity-materialization.{original}.json"
        )
        journal = json.loads(journal_path.read_text())
        self.assertEqual(CHAPEL_BUILD_METHOD, journal["builder"])


if __name__ == "__main__":
    unittest.main()
