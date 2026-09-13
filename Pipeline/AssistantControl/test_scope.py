"""Real repository-scope adapter tests using disposable Git repositories."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.scope import AssistantScopePlanner, ScopePlanningError
from Pipeline.ExecutionCrew.run_crew import preflight_role_paths
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity
from Pipeline.TaskReviewAgent.pipeline_scope import (
    RepositoryScopeAuthority,
    RepositoryScopeError,
)


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
            "depends_on": [], "exclusive_resources": [
                "repo-file:Assets/NoSafeCircle/Feature/Feature.cs",
                "repo-file:Assets/NoSafeCircle/Feature/Tests/FeatureTests.cs",
            ],
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


class ExactWorkerScopeTests(unittest.TestCase):
    RUINED_BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/RuinedEntrySceneBuilder.cs"
    RUINED_LAYOUT = "Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms/RuinedEntryLayout.cs"
    RUINED_TEST = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms/RuinedEntrySceneTests.cs"
    RUINED_SCENE = "Assets/Scenes/Rooms/RuinedEntry.unity"
    BONE_BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/BoneArchiveSceneBuilder.cs"
    BONE_LAYOUT = "Assets/NoSafeCircle/DoorPrototype/Scripts/World/Rooms/BoneArchiveLayout.cs"
    BONE_TEST = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms/BoneArchiveSceneTests.cs"
    BONE_SCENE = "Assets/Scenes/Rooms/BoneArchive.unity"
    COMMON_BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs"
    COMMON_CATALOG = "Assets/NoSafeCircle/DoorPrototype/Scripts/World/RoomCatalog.cs"
    CANONICAL_SCENE = "Assets/Scenes/DoorPrototype.unity"
    UNRELATED_TEST = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPrototypeSceneBuilderTests.cs"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        self.git("init", "-b", "main")
        name, email = validated_agent_git_identity()
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)

        resource_parents = {
            str(Path(path).parent).replace("\\", "/")
            for path in (
                self.RUINED_BUILDER,
                self.RUINED_LAYOUT,
                self.RUINED_TEST,
                self.RUINED_SCENE,
                self.BONE_BUILDER,
                self.BONE_LAYOUT,
                self.BONE_TEST,
                self.BONE_SCENE,
            )
        }
        for parent in resource_parents:
            directory = self.source / parent
            directory.mkdir(parents=True, exist_ok=True)
            (directory / ".keep").write_text("tracked parent\n", encoding="utf-8")

        for path in (
            self.COMMON_BUILDER,
            self.COMMON_CATALOG,
            self.CANONICAL_SCENE,
            self.UNRELATED_TEST,
        ):
            target = self.source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"fixture for {path}\n", encoding="utf-8")

        owned_directory = self.source / "Assets/NoSafeCircle/OwnedFeature"
        (owned_directory / "Tests").mkdir(parents=True)
        (owned_directory / "OwnedFeature.cs").write_text("class OwnedFeature {}\n")
        (owned_directory / "Tests/OwnedFeatureTests.cs").write_text(
            "class OwnedFeatureTests {}\n"
        )

        shared = self.source / "Assets/NoSafeCircle/Shared"
        (shared / "Tests").mkdir(parents=True)
        (shared / "Owned.cs").write_text("class Owned {}\n")
        (shared / "Sibling.cs").write_text("class Sibling {}\n")
        (shared / "Tests/OwnedTests.cs").write_text("class OwnedTests {}\n")
        (shared / "Tests/SiblingTests.cs").write_text("class SiblingTests {}\n")

        self.write_contract(
            "NSC-044",
            [
                f"repo-file:{self.RUINED_BUILDER}",
                f"repo-file:{self.RUINED_LAYOUT}",
                f"repo-file:{self.RUINED_TEST}",
                f"unity-scene:{self.RUINED_SCENE}",
                "logical:room-walkability:ruined-entry",
            ],
        )
        self.write_contract(
            "NSC-045",
            [
                f"repo-file:{self.BONE_BUILDER}",
                f"repo-file:{self.BONE_LAYOUT}",
                f"repo-file:{self.BONE_TEST}",
                f"unity-scene:{self.BONE_SCENE}",
                "logical:room-walkability:bone-archive",
            ],
        )
        self.write_contract(
            "NSC-046",
            ["repo-file:Assets/NoSafeCircle/OwnedFeature"],
        )
        self.write_contract(
            "NSC-047",
            [
                "repo-file:Assets/NoSafeCircle/Shared/Owned.cs",
                "repo-file:Assets/NoSafeCircle/Shared/Tests/OwnedTests.cs",
            ],
        )
        self.write_contract(
            "NSC-048",
            ["repo-file:Assets/NoSafeCircle//Shared/Owned.cs"],
        )
        self.git("add", ".")
        self.git("commit", "-m", "Create exact worker scope fixture")
        self.head = self.git("rev-parse", "HEAD").decode().strip()

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.source), *args],
            capture_output=True,
            check=True,
        ).stdout

    def write_contract(self, task_id, resources):
        tasks = self.source / "Tasks"
        tasks.mkdir(exist_ok=True)
        contract = {
            "id": task_id,
            "title": "Exact scope fixture",
            "contract_disposition": "active",
            "depends_on": [],
            "exclusive_resources": resources,
        }
        (tasks / f"{task_id}.yaml").write_text(
            json.dumps(contract, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def authority(self, task_id, *, task=None, state_name=None):
        committed = load_committed_task(self.source, task_id, commit=self.head)
        return RepositoryScopeAuthority(
            checkout=self.source,
            task=committed if task is None else task,
            lease_id=f"lease-{task_id.casefold()}",
            expected_branch="main",
            state_root=Path(self.temp.name) / (state_name or f"state-{task_id}"),
        )

    def room_plan(
        self,
        room,
        *,
        extra_existing_implementation=(),
        extra_new_implementation=(),
        extra_existing_tests=(),
        extra_new_tests=(),
    ):
        if room == "ruined":
            implementation = (self.RUINED_BUILDER, self.RUINED_LAYOUT, self.RUINED_SCENE)
            tests = (self.RUINED_TEST,)
        else:
            implementation = (self.BONE_BUILDER, self.BONE_LAYOUT, self.BONE_SCENE)
            tests = (self.BONE_TEST,)
        return ExecutionScopePlan(
            tuple(extra_existing_implementation),
            (*implementation, *extra_new_implementation),
            tuple(extra_existing_tests),
            (*tests, *extra_new_tests),
        )

    def test_nsc_044_accepts_only_its_exact_room_files(self):
        authority = self.authority("NSC-044")
        accepted = authority.validate(self.room_plan("ruined"))
        self.assertTrue(accepted.accepted, accepted.reasons)
        self.assertEqual([], authority.facts()["ownership_roots"])

        forbidden_implementation = (
            self.COMMON_BUILDER,
            self.COMMON_CATALOG,
            self.CANONICAL_SCENE,
        )
        for path in forbidden_implementation:
            with self.subTest(path=path):
                result = authority.validate(
                    self.room_plan(
                        "ruined", extra_existing_implementation=(path,)
                    )
                )
                self.assertFalse(result.accepted, path)
        for path in (self.BONE_BUILDER, self.BONE_LAYOUT, self.BONE_SCENE):
            with self.subTest(path=path):
                result = authority.validate(
                    self.room_plan("ruined", extra_new_implementation=(path,))
                )
                self.assertFalse(result.accepted, path)
        result = authority.validate(
            self.room_plan(
                "ruined", extra_existing_tests=(self.UNRELATED_TEST,)
            )
        )
        self.assertFalse(result.accepted, self.UNRELATED_TEST)

    def test_nsc_044_new_paths_receive_only_deterministic_meta_companions(self):
        plan = self.room_plan("ruined")
        implementation, tests = preflight_role_paths(
            self.source,
            self.head,
            plan.existing_implementation_paths,
            plan.new_implementation_paths,
            plan.existing_test_paths,
            plan.new_test_paths,
        )
        self.assertEqual(
            tuple(f"{path}.meta" for path in plan.new_implementation_paths),
            implementation.pipeline_generated_sidecars,
        )
        self.assertEqual(
            (f"{self.RUINED_TEST}.meta",),
            tests.pipeline_generated_sidecars,
        )

    def test_room_contracts_cannot_write_each_others_resources(self):
        ruined = self.authority("NSC-044")
        bone = self.authority("NSC-045")
        self.assertFalse(
            ruined.validate(
                self.room_plan(
                    "ruined", extra_new_implementation=(self.BONE_BUILDER,)
                )
            ).accepted
        )
        self.assertFalse(
            bone.validate(
                self.room_plan(
                    "bone", extra_new_implementation=(self.RUINED_BUILDER,)
                )
            ).accepted
        )

    def test_multiple_exact_resources_do_not_grant_their_common_directory(self):
        authority = self.authority("NSC-047")
        plan = ExecutionScopePlan(
            ("Assets/NoSafeCircle/Shared/Owned.cs",),
            (),
            ("Assets/NoSafeCircle/Shared/Tests/OwnedTests.cs",),
            (),
        )
        self.assertTrue(authority.validate(plan).accepted)
        sibling = ExecutionScopePlan(
            ("Assets/NoSafeCircle/Shared/Sibling.cs",),
            (),
            ("Assets/NoSafeCircle/Shared/Tests/SiblingTests.cs",),
            (),
        )
        self.assertFalse(authority.validate(sibling).accepted)

    def test_explicitly_owned_committed_directory_allows_descendants(self):
        authority = self.authority("NSC-046")
        plan = ExecutionScopePlan(
            ("Assets/NoSafeCircle/OwnedFeature/OwnedFeature.cs",),
            (),
            ("Assets/NoSafeCircle/OwnedFeature/Tests/OwnedFeatureTests.cs",),
            (),
        )
        self.assertTrue(authority.validate(plan).accepted)
        self.assertEqual(
            ["Assets/NoSafeCircle/OwnedFeature/"],
            authority.facts()["ownership_roots"],
        )

    def test_committed_contract_resources_override_claimed_broad_root(self):
        task = load_committed_task(self.source, "NSC-044", commit=self.head)
        task["exclusive_resources"] = [
            "repo-file:Assets/NoSafeCircle/DoorPrototype"
        ]
        authority = self.authority("NSC-044", task=task, state_name="claimed-root")
        result = authority.validate(
            self.room_plan(
                "ruined", extra_existing_implementation=(self.COMMON_BUILDER,)
            )
        )
        self.assertFalse(result.accepted)

    def test_malformed_noncanonical_resource_path_fails_closed(self):
        with self.assertRaises(RepositoryScopeError):
            self.authority("NSC-048")

    def test_rejected_plan_does_not_mutate_checkout_or_scope_state(self):
        state_root = Path(self.temp.name) / "rejected-state"
        authority = self.authority(
            "NSC-044", state_name=state_root.name
        )
        before_tree = self.git("rev-parse", "HEAD^{tree}")
        before_status = self.git("status", "--porcelain=v1", "--untracked-files=all")
        result = authority.validate(
            self.room_plan(
                "ruined", extra_existing_tests=(self.UNRELATED_TEST,)
            )
        )
        self.assertFalse(result.accepted)
        self.assertEqual(before_tree, self.git("rev-parse", "HEAD^{tree}"))
        self.assertEqual(
            before_status,
            self.git("status", "--porcelain=v1", "--untracked-files=all"),
        )
        self.assertFalse(state_root.exists())


if __name__ == "__main__":
    unittest.main()
