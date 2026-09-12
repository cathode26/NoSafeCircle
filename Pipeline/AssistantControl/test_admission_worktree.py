"""Real-Git tests for the admission registry's identity across worktrees.

A Git worktree of an already-admitted repository shares its admission
registry file with the repository's other worktrees, because the file lives
under --git-common-dir, not under the caller's own --show-toplevel. Before
this fix, the registry's self-described identity field was keyed on the
caller's own toplevel, so whichever worktree wrote the shared file first
"won" that path string permanently and every other worktree of the same
repo failed the identity check deterministically -- not a timing-dependent
race. These tests reproduce that with a real ``git worktree add`` and prove
the fix, while also proving a genuinely different repository, and a
corrupted registry at the same identity, still fail closed.
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.admission import (
    _read_registry,
    _registry_identity,
    _source_registry_paths,
    release,
    reserve,
)
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


def _write_task(root, task_id, resource):
    (root / f"Tasks/{task_id}.yaml").write_text(json.dumps({
        "id": task_id, "title": task_id, "contract_disposition": "active",
        "kind": "implementation", "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "depends_on": [], "exclusive_resources": [resource],
    }))


class AdmissionWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.main = Path(self.temp.name) / "main-repo"
        self.main.mkdir()
        self.git(self.main, "init")
        name, email = validated_agent_git_identity()
        self.git(self.main, "config", "user.name", name)
        self.git(self.main, "config", "user.email", email)
        (self.main / "Tasks").mkdir()
        (self.main / "Assets/Feature/Tests").mkdir(parents=True)
        (self.main / "Assets/Feature/Feature.cs").write_text("class Feature {}\n")
        (self.main / "Assets/Feature/Tests/FeatureTests.cs").write_text("class FeatureTests {}\n")
        _write_task(self.main, "NSC-042", "repo-file:Assets/Feature")
        _write_task(self.main, "NSC-043", "repo-file:Assets/Feature/Other.cs")
        self.git(self.main, "add", ".")
        self.git(self.main, "commit", "-m", "admission worktree fixture")
        self.worktree = Path(self.temp.name) / "worktree"
        self.git(self.main, "worktree", "add", str(self.worktree), "-b", "assistant/worktree-fixture")
        self.manager_main = Checkouts(self.main, Path(self.temp.name) / "checkouts-main")
        self.manager_wt = Checkouts(self.worktree, Path(self.temp.name) / "checkouts-wt")

    def git(self, cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args],
                              capture_output=True, check=True).stdout

    def plan(self, manager, task_id, lease_id):
        manager.prepare(task_id)
        return AssistantScopePlanner(manager).plan(
            task_id,
            ExecutionScopePlan(
                ("Assets/Feature/Feature.cs",), (),
                ("Assets/Feature/Tests/FeatureTests.cs",), (),
            ),
            lease_id=lease_id,
        )

    @staticmethod
    def dependencies(source, task_id, _checkout_root):
        head = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                              capture_output=True, check=True).stdout.decode().strip()
        return {"task_id": task_id, "source_commit": head,
                "source_unchanged_during_read": True, "dependencies_satisfied": True}

    def test_worktree_and_main_checkout_share_one_registry_file(self):
        _, main_registry_path = _source_registry_paths(self.main)
        _, wt_registry_path = _source_registry_paths(self.worktree)
        self.assertEqual(main_registry_path, wt_registry_path)

    def test_identity_is_the_shared_repo_root_not_the_calling_worktree(self):
        _, main_registry_path = _source_registry_paths(self.main)
        _, wt_registry_path = _source_registry_paths(self.worktree)
        # Both worktrees compute the SAME identity: the main repo's own
        # toplevel -- never the worktree's own, distinct toplevel path.
        self.assertEqual(str(self.main.resolve()), _registry_identity(main_registry_path))
        self.assertEqual(str(self.main.resolve()), _registry_identity(wt_registry_path))
        self.assertNotEqual(str(self.worktree.resolve()), _registry_identity(wt_registry_path))

    def test_first_initialization_from_a_worktree_creates_a_valid_shared_registry(self):
        self.plan(self.manager_wt, "NSC-042", "lease-042")
        reserved = reserve(self.manager_wt, "NSC-042", "run-042", dependency_reader=self.dependencies)
        self.assertTrue(reserved["admitted"])
        _, registry_path = _source_registry_paths(self.worktree)
        from_worktree = _read_registry(registry_path, self.worktree)
        self.assertEqual(1, len(from_worktree["reservations"]))
        # Reading the identical on-disk file through the MAIN checkout's own
        # identity must not raise "identity or schema differs" -- this is
        # exactly the bug: a worktree's first write must stay readable by
        # every other worktree of the same repo, including the main one.
        from_main = _read_registry(registry_path, self.main)
        self.assertEqual(from_worktree, from_main)

    def test_repeated_initialization_from_the_same_source_is_idempotent(self):
        self.plan(self.manager_main, "NSC-042", "lease-042")
        first = reserve(self.manager_main, "NSC-042", "run-042", dependency_reader=self.dependencies)
        second = reserve(self.manager_main, "NSC-042", "run-042", dependency_reader=self.dependencies)
        self.assertEqual(first, second)
        _, registry_path = _source_registry_paths(self.main)
        self.assertEqual(_read_registry(registry_path, self.main),
                         _read_registry(registry_path, self.main))

    def test_reservation_from_one_worktree_is_visible_and_enforced_from_the_other(self):
        self.plan(self.manager_wt, "NSC-042", "lease-042")
        reserve(self.manager_wt, "NSC-042", "run-042", dependency_reader=self.dependencies)
        # Read through the MAIN checkout's own identity: it must see the
        # exact reservation the worktree just made in the one shared file.
        _, main_registry_path = _source_registry_paths(self.main)
        seen_from_main = _read_registry(main_registry_path, self.main)
        self.assertEqual(["NSC-042"], [item["task_id"] for item in seen_from_main["reservations"]])
        # A second task, admitted through the MAIN checkout, is correctly
        # blocked by capacity because the shared registry already carries
        # the worktree's reservation -- proving real coordination, not just
        # visibility.
        self.plan(self.manager_main, "NSC-043", "lease-043")
        with self.assertRaisesRegex(ValueError, "capacity"):
            reserve(self.manager_main, "NSC-043", "run-043", dependency_reader=self.dependencies)
        released = release(self.manager_wt, "NSC-042", "run-042", "lease-042")
        self.assertTrue(released["released"])
        reserved_from_main = reserve(
            self.manager_main, "NSC-043", "run-043", dependency_reader=self.dependencies)
        self.assertTrue(reserved_from_main["admitted"])
        # And the worktree now observes the main checkout's reservation.
        _, wt_registry_path = _source_registry_paths(self.worktree)
        seen_from_wt = _read_registry(wt_registry_path, self.worktree)
        self.assertEqual(["NSC-043"], [item["task_id"] for item in seen_from_wt["reservations"]])

    def test_corrupted_registry_at_the_same_identity_still_fails_closed(self):
        _, registry_path = _source_registry_paths(self.main)
        identity = _registry_identity(registry_path)
        corrupt_variants = (
            {"schema_version": "wrong/v0", "source": identity, "reservations": []},
            {"schema_version": "assistant-admission/v1", "source": identity, "reservations": "not-a-list"},
            ["not", "a", "dict"],
        )
        for corrupt in corrupt_variants:
            write_record(registry_path, corrupt)
            with self.assertRaisesRegex(ValueError, "identity or schema differs"):
                _read_registry(registry_path, self.main)

    def test_unrelated_repository_gets_an_independent_registry_and_cross_reading_is_refused(self):
        other = Path(self.temp.name) / "unrelated-repo"
        other.mkdir()
        self.git(other, "init")
        name, email = validated_agent_git_identity()
        self.git(other, "config", "user.name", name)
        self.git(other, "config", "user.email", email)
        (other / "readme.txt").write_text("unrelated\n")
        self.git(other, "add", ".")
        self.git(other, "commit", "-m", "unrelated")
        _, main_registry_path = _source_registry_paths(self.main)
        _, other_registry_path = _source_registry_paths(other)
        self.assertNotEqual(main_registry_path, other_registry_path)

        self.plan(self.manager_main, "NSC-042", "lease-042")
        reserve(self.manager_main, "NSC-042", "run-042", dependency_reader=self.dependencies)
        main_registry = json.loads(main_registry_path.read_text(encoding="utf-8"))
        # Manually drop the main repo's own registry content at the
        # unrelated repo's own registry path. Its stored identity is the
        # main repo's root, which does not match the unrelated repo's own
        # identity, so reading it there must still fail closed.
        write_record(other_registry_path, main_registry)
        with self.assertRaisesRegex(ValueError, "identity or schema differs"):
            _read_registry(other_registry_path, other)


if __name__ == "__main__":
    unittest.main()
