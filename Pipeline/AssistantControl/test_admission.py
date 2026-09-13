"""Real-Git admission tests using disposable repositories and injected dependency evidence."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.admission import release, require_reservation, reserve
from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.readiness import inspect_readiness
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


class AdmissionTests(unittest.TestCase):
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
        (self.source / "Assets/Feature/Tests").mkdir(parents=True)
        (self.source / "Assets/Feature/Feature.cs").write_text("class Feature {}\n")
        (self.source / "Assets/Feature/Tests/FeatureTests.cs").write_text("class FeatureTests {}\n")
        (self.source / "Assets/Feature/Other.cs").write_text("class Other {}\n")
        (self.source / "Assets/Feature/Tests/OtherTests.cs").write_text("class OtherTests {}\n")
        for task_id, resources in (
            ("NSC-042", ["repo-file:Assets/Feature"]),
            ("NSC-043", [
                "repo-file:Assets/Feature/Other.cs",
                "repo-file:Assets/Feature/Tests/OtherTests.cs",
            ]),
        ):
            (self.source / f"Tasks/{task_id}.yaml").write_text(json.dumps({
                "id": task_id, "title": task_id, "contract_disposition": "active",
                "kind": "implementation", "execution_scope": "single_agent",
                "decomposition_state": "concrete",
                "depends_on": [], "exclusive_resources": resources,
            }))
        self.git("add", ".")
        self.git("commit", "-m", "admission fixture")
        self.root_one = Path(self.temp.name) / "checkouts-one"
        self.root_two = Path(self.temp.name) / "checkouts-two"
        self.manager_one = Checkouts(self.source, self.root_one)
        self.manager_two = Checkouts(self.source, self.root_two)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.source), *args],
                              capture_output=True, check=True).stdout

    def plan(self, manager, task_id, lease_id):
        manager.prepare(task_id)
        stem = "Feature" if task_id == "NSC-042" else "Other"
        return AssistantScopePlanner(manager).plan(
            task_id,
            ExecutionScopePlan(
                (f"Assets/Feature/{stem}.cs",), (),
                (f"Assets/Feature/Tests/{stem}Tests.cs",), (),
            ),
            lease_id=lease_id,
        )

    @staticmethod
    def dependencies(source, task_id, checkout_root):
        return {
            "task_id": task_id,
            "source_commit": subprocess.run(
                ["git", "-C", str(source), "rev-parse", "HEAD"],
                capture_output=True, check=True,
            ).stdout.decode().strip(),
            "source_unchanged_during_read": True,
            "dependencies_satisfied": True,
            "fixture_dependency_reader": True,
        }

    def test_reserve_is_idempotent_only_for_the_same_checkout_identity(self):
        self.plan(self.manager_one, "NSC-042", "lease-042")
        self.plan(self.manager_two, "NSC-042", "lease-042")
        first = reserve(self.manager_one, "NSC-042", "run-042", dependency_reader=self.dependencies)
        second = reserve(self.manager_one, "NSC-042", "run-042", dependency_reader=self.dependencies)
        self.assertEqual(first, second)
        self.assertTrue(first["admitted"])
        self.assertFalse(first["execution_authorized"])
        self.assertEqual("run-042", first["run_id"])
        self.assertEqual("lease-042", first["lease_id"])
        self.assertTrue(first["plan_id"].startswith("scope-"))
        with self.assertRaisesRegex(ValueError, "checkout root"):
            reserve(self.manager_two, "NSC-042", "run-042", dependency_reader=self.dependencies)

    def test_readiness_is_read_only_and_explains_capacity_resources_and_source_edits(self):
        self.plan(self.manager_one, "NSC-042", "lease-042")
        ready = inspect_readiness(
            self.manager_one, "NSC-042", dependency_reader=self.dependencies,
        )
        self.assertTrue(ready["ready_to_reserve"])
        self.assertFalse(ready["mutations_performed"])
        self.assertEqual([], ready["problems"])
        self.plan(self.manager_two, "NSC-043", "lease-043")
        reserve(
            self.manager_one, "NSC-042", "run-042",
            dependency_reader=self.dependencies,
        )
        blocked = inspect_readiness(
            self.manager_two, "NSC-043", dependency_reader=self.dependencies,
        )
        self.assertFalse(blocked["ready_to_reserve"])
        self.assertIn("worker_capacity_exhausted", blocked["problems"])
        self.assertIn("resources_reserved_by_other_tasks", blocked["problems"])
        self.assertEqual(["NSC-042"], blocked["resource_owners"])

        release(self.manager_one, "NSC-042", "run-042", "lease-042")
        (self.source / "Assets/Feature/Feature.cs").write_text("Vincent edit\n")
        edited = inspect_readiness(
            self.manager_one, "NSC-042", dependency_reader=self.dependencies,
        )
        self.assertIn("source_has_conflicting_local_edits", edited["problems"])
        self.assertEqual(["assets/feature/feature.cs"], edited["source_edit_conflicts"])

    def test_require_reservation_returns_exact_owned_current_record(self):
        self.plan(self.manager_one, "NSC-042", "lease-042")
        reserved = reserve(self.manager_one, "NSC-042", "run-042", dependency_reader=self.dependencies)
        required = require_reservation(self.manager_one, "NSC-042", "run-042", "lease-042")
        self.assertEqual(reserved, required)
        with self.assertRaisesRegex(ValueError, "owned by this checkout root"):
            require_reservation(self.manager_two, "NSC-042", "run-042", "lease-042")

    def test_tampered_scope_json_is_rejected_by_persisted_authority(self):
        self.plan(self.manager_one, "NSC-042", "lease-042")
        path = self.manager_one.records / "NSC-042.json"
        record = json.loads(path.read_text())
        record["scope"]["plan_id"] = "scope-forged"
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "persisted execution scope"):
            reserve(self.manager_one, "NSC-042", "run-042", dependency_reader=self.dependencies)

    def test_capacity_and_hierarchical_resource_overlap_are_rejected(self):
        self.plan(self.manager_one, "NSC-042", "lease-042")
        self.plan(self.manager_two, "NSC-043", "lease-043")
        reserve(self.manager_one, "NSC-042", "run-042", dependency_reader=self.dependencies)
        with self.assertRaisesRegex(ValueError, "capacity"):
            reserve(self.manager_two, "NSC-043", "run-043", dependency_reader=self.dependencies)
        with self.assertRaisesRegex(ValueError, "overlap"):
            reserve(self.manager_two, "NSC-043", "run-043", capacity=2,
                    dependency_reader=self.dependencies)

    def test_same_task_different_run_and_same_lease_are_rejected(self):
        self.plan(self.manager_one, "NSC-042", "lease-042")
        reserve(self.manager_one, "NSC-042", "run-042", dependency_reader=self.dependencies)
        with self.assertRaisesRegex(ValueError, "different active admission"):
            reserve(self.manager_one, "NSC-042", "run-043", capacity=2,
                    dependency_reader=self.dependencies)
        self.plan(self.manager_two, "NSC-043", "lease-042")
        with self.assertRaisesRegex(ValueError, "run or lease"):
            reserve(self.manager_two, "NSC-043", "run-043", capacity=2,
                    dependency_reader=self.dependencies)

    def test_release_requires_exact_identity_and_allows_new_reservation(self):
        self.plan(self.manager_one, "NSC-042", "lease-042")
        reserve(self.manager_one, "NSC-042", "run-042", dependency_reader=self.dependencies)
        with self.assertRaisesRegex(ValueError, "exact active"):
            release(self.manager_one, "NSC-042", "run-042", "wrong-lease")
        released = release(self.manager_one, "NSC-042", "run-042", "lease-042")
        self.assertTrue(released["released"])
        replacement = reserve(self.manager_one, "NSC-042", "run-043", dependency_reader=self.dependencies)
        self.assertEqual("run-043", replacement["run_id"])

    def test_source_head_change_or_unsatisfied_dependency_fails_before_reservation(self):
        self.plan(self.manager_one, "NSC-042", "lease-042")
        (self.source / "source-change.txt").write_text("changed\n")
        self.git("add", "source-change.txt")
        self.git("commit", "-m", "advance source")
        with self.assertRaisesRegex(ValueError, "current HEAD"):
            reserve(self.manager_one, "NSC-042", "run-042", dependency_reader=self.dependencies)

        # A separate fresh checkout proves the dependency gate itself.
        manager = Checkouts(self.source, Path(self.temp.name) / "checkouts-three")
        self.plan(manager, "NSC-042", "lease-043")
        def blocked(_source, task_id, _checkout_root):
            return {"task_id": task_id, "source_commit": self.git("rev-parse", "HEAD").decode().strip(),
                    "source_unchanged_during_read": True, "dependencies_satisfied": False,
                    "fixture_dependency_reader": True}
        with self.assertRaisesRegex(ValueError, "dependency inspection"):
            reserve(manager, "NSC-042", "run-043", dependency_reader=blocked)


if __name__ == "__main__":
    unittest.main()
