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
        for stem in ("Third", "Fourth"):
            (self.source / f"Assets/Feature/{stem}.cs").write_text(f"class {stem} {{}}\n")
            (self.source / f"Assets/Feature/Tests/{stem}Tests.cs").write_text(f"class {stem}Tests {{}}\n")
        for task_id, resources in (
            ("NSC-042", ["repo-file:Assets/Feature"]),
            ("NSC-043", [
                "repo-file:Assets/Feature/Other.cs",
                "repo-file:Assets/Feature/Tests/OtherTests.cs",
            ]),
            ("NSC-044", ["repo-file:Assets/Feature/Third.cs", "logical:scene-lock"]),
            ("NSC-045", ["repo-file:Assets/Feature/Fourth.cs", "logical:scene-lock"]),
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
        stem = {"NSC-042": "Feature", "NSC-043": "Other",
                "NSC-044": "Third", "NSC-045": "Fourth"}[task_id]
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

    def test_readiness_names_the_checkout_cause_not_just_its_category(self):
        """`checkout_or_scope_not_ready` alone names the CATEGORY, not the cause.

        Reported from the floor by the Pipeline Runner, which lost a detour to
        it: NSC-118 was prepared, dependency-clear and resource-free, and
        readiness said only `checkout_or_scope_not_ready` while the string that
        actually explained it -- "task checkout is not at current source HEAD"
        -- sat in the separate `checkout_error` field. Both are in the same
        returned dict; what was missing was any pointer from one to the other.

        The stable code stays a PREFIX so a machine match still works.
        """
        self.plan(self.manager_one, "NSC-042", "lease-042")
        (self.source / "Assets/Feature/Unrelated.cs").write_text("class Unrelated {}\n")
        self.git("add", ".")
        self.git("commit", "-m", "source moves on after the checkout was prepared")

        stale = inspect_readiness(
            self.manager_one, "NSC-042", dependency_reader=self.dependencies,
        )
        self.assertFalse(stale["ready_to_reserve"])
        named = [problem for problem in stale["problems"]
                 if problem.startswith("checkout_or_scope_not_ready")]
        self.assertEqual(1, len(named), stale["problems"])

        # The whole point: the entry must not be the bare category.
        self.assertNotEqual("checkout_or_scope_not_ready", named[0])
        self.assertTrue(stale["checkout_error"], "no cause was captured at all")
        self.assertIn(stale["checkout_error"], named[0])

    def test_capacity_held_by_an_unsettled_run_is_named_not_counted_as_work(self):
        """A run that ENDED but was never settled still holds its reservation.

        A bare count cannot tell it from work in flight, and unlike a running
        crew it never clears itself, so nothing dispatches again until someone
        settles it. Readiness names the holder instead of only saying the
        pipeline is full.
        """
        self.plan(self.manager_one, "NSC-042", "lease-042")
        self.plan(self.manager_one, "NSC-044", "lease-044")
        reserve(
            self.manager_one, "NSC-042", "run-042",
            dependency_reader=self.dependencies,
        )
        # Control: a reservation held by work in flight must NOT be flagged, so
        # a pass cannot come from flagging every reservation.
        busy = inspect_readiness(
            self.manager_one, "NSC-044", dependency_reader=self.dependencies,
        )
        self.assertIn("worker_capacity_exhausted", busy["problems"])
        self.assertEqual([], busy["reservations_awaiting_settle"])
        self.assertNotIn("worker_capacity_held_by_unsettled_runs", busy["problems"])

        path = self.manager_one.records / "NSC-042.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["worker"] = {"run_id": "run-042", "status": "succeeded"}
        path.write_text(json.dumps(record), encoding="utf-8")

        debt = inspect_readiness(
            self.manager_one, "NSC-044", dependency_reader=self.dependencies,
        )
        self.assertIn("worker_capacity_exhausted", debt["problems"])
        self.assertIn("worker_capacity_held_by_unsettled_runs", debt["problems"])
        self.assertEqual(["NSC-042"], debt["reservations_awaiting_settle"])

        # `settled_at` plus `capacity_released` is the record's own proof that
        # the process and containers are gone: no longer debt.
        record["worker"]["capacity_released"] = True
        record["worker"]["settled_at"] = "2026-09-25T00:00:00Z"
        path.write_text(json.dumps(record), encoding="utf-8")
        settled = inspect_readiness(
            self.manager_one, "NSC-044", dependency_reader=self.dependencies,
        )
        self.assertEqual([], settled["reservations_awaiting_settle"])
        self.assertNotIn("worker_capacity_held_by_unsettled_runs", settled["problems"])

    def test_a_reservation_from_another_checkout_root_is_unknown_not_clean(self):
        """Control records are per checkout root; the registry is on the source.

        A reservation taken from another root cannot be read here, and saying
        nothing would report it as settled. It is listed as unreadable instead.
        """
        self.plan(self.manager_one, "NSC-042", "lease-042")
        self.plan(self.manager_two, "NSC-043", "lease-043")
        reserve(
            self.manager_one, "NSC-042", "run-042",
            dependency_reader=self.dependencies,
        )
        other = inspect_readiness(
            self.manager_two, "NSC-043", dependency_reader=self.dependencies,
        )
        self.assertIn("worker_capacity_exhausted", other["problems"])
        self.assertEqual([], other["reservations_awaiting_settle"])
        self.assertEqual(["NSC-042"], other["reservations_not_readable_here"])

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

    def test_parallel_file_work_requires_opt_in_and_same_live_checkout_root(self):
        self.plan(self.manager_one, "NSC-042", "lease-042")
        self.plan(self.manager_one, "NSC-043", "lease-043")
        self.plan(self.manager_two, "NSC-044", "lease-044")
        reserve(self.manager_one, "NSC-042", "run-042", capacity=3,
                dependency_reader=self.dependencies)
        default = inspect_readiness(self.manager_one, "NSC-043", capacity=3,
                                    dependency_reader=self.dependencies)
        self.assertIn("resources_reserved_by_other_tasks", default["problems"])
        opted = inspect_readiness(self.manager_one, "NSC-043", capacity=3,
                                  allow_resource_overlap=True,
                                  dependency_reader=self.dependencies)
        self.assertTrue(opted["ready_to_reserve"])
        self.assertEqual(["NSC-042"], opted["resource_owners"])
        self.assertEqual([], opted["blocking_resource_owners"])
        with self.assertRaisesRegex(ValueError, "overlap"):
            reserve(self.manager_one, "NSC-043", "run-043", capacity=3,
                    dependency_reader=self.dependencies)
        with self.assertRaisesRegex(ValueError, "overlap"):
            reserve(self.manager_two, "NSC-044", "run-044", capacity=3,
                    allow_resource_overlap=True, dependency_reader=self.dependencies)
        admitted = reserve(self.manager_one, "NSC-043", "run-043", capacity=3,
                           allow_resource_overlap=True, dependency_reader=self.dependencies)
        self.assertEqual(str(self.manager_one.root / "NSC-043"), admitted["checkout"])
        self.assertTrue(admitted["resource_overlap_authorized"])
        self.assertEqual(["NSC-042"], [item["task_id"] for item in admitted["overlap_with"]])
        self.assertEqual(["assets/feature/other.cs", "assets/feature/tests/othertests.cs"],
                         admitted["overlap_with"][0]["requested_resources"])
        self.assertEqual(admitted, require_reservation(
            self.manager_one, "NSC-043", "run-043", "lease-043"))

    def test_opt_in_retains_capacity_three_and_exclusive_logical_locks(self):
        for task_id in ("NSC-042", "NSC-043", "NSC-044", "NSC-045"):
            self.plan(self.manager_one, task_id, f"lease-{task_id}")
        for task_id in ("NSC-042", "NSC-043", "NSC-044"):
            reserve(self.manager_one, task_id, f"run-{task_id}", capacity=3,
                    allow_resource_overlap=True, dependency_reader=self.dependencies)
        with self.assertRaisesRegex(ValueError, "capacity"):
            reserve(self.manager_one, "NSC-045", "run-NSC-045", capacity=3,
                    allow_resource_overlap=True, dependency_reader=self.dependencies)
        release(self.manager_one, "NSC-042", "run-NSC-042", "lease-NSC-042")
        blocked = inspect_readiness(self.manager_one, "NSC-045", capacity=3,
                                    allow_resource_overlap=True,
                                    dependency_reader=self.dependencies)
        self.assertIn("resources_reserved_by_other_tasks", blocked["problems"])
        self.assertEqual(["NSC-044"], blocked["blocking_resource_owners"])
        with self.assertRaisesRegex(ValueError, "overlap"):
            reserve(self.manager_one, "NSC-045", "run-NSC-045", capacity=3,
                    allow_resource_overlap=True, dependency_reader=self.dependencies)

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
