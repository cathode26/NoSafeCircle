"""Pure/component regression tests; all mutations are in disposable Git repos.

Proves inventory preserves operator edits and reads committed task identity.
Does not prove Unity conformance, admission, provider behavior or delivery.
"""
import ast
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from Pipeline.AssistantControl.inspect_project import changes, git, inspect, resource_conflicts, unresolvable_commit
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_git("init")
        name, email = validated_agent_git_identity()
        self.run_git("config", "user.name", name)
        self.run_git("config", "user.email", email)
        self.run_git("config", "core.autocrlf", "false")
        (self.root / "Tasks").mkdir()
        self.contract = self.root / "Tasks/NSC-042.yaml"
        self.contract.write_text(json.dumps({
            # schema_version is REQUIRED of a committed contract by
            # current_conformance.py:357 since 692adcb9c (2026-09-12).
            # Without it AssistantSnapshot.build() yields no task rows at
            # all, and every fixture that chains to this one goes red.
            "schema_version": "2.0",
            "id": "NSC-042", "title": "Committed wall task", "depends_on": [],
            "exclusive_resources": ["repo-file:wall file.txt"],
        }), encoding="utf-8")
        (self.root / "wall file.txt").write_text("old\n", encoding="utf-8")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "Fixture")

    def run_git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args],
                              capture_output=True, check=True).stdout

    def test_dirty_inventory_preserves_index_and_files_and_uses_committed_contract(self):
        self.contract.write_text('{"id":"NSC-042","title":"Uncommitted"}')
        asset = self.root / "wall file.txt"
        asset.write_bytes(b"operator edits\n")
        (self.root / "untracked.txt").write_bytes(b"keep me")
        before_index = (self.root / ".git/index").read_bytes()
        before_head = self.run_git("rev-parse", "HEAD")
        result = inspect(self.root, "NSC-042")
        self.assertEqual("Committed wall task", result["tasks"][0]["title"])
        self.assertEqual(["wall file.txt"], result["tasks"][0]["local_edit_conflicts"])
        self.assertTrue(result["head_unchanged_during_read"])
        self.assertIn({"status": "??", "path": "untracked.txt"}, result["local_changes"])
        self.assertEqual(before_index, (self.root / ".git/index").read_bytes())
        self.assertEqual(before_head, self.run_git("rev-parse", "HEAD"))
        self.assertEqual(b"operator edits\n", asset.read_bytes())
        self.assertEqual(b"keep me", (self.root / "untracked.txt").read_bytes())

    def test_staged_rename_reports_original_and_destination(self):
        self.run_git("mv", "wall file.txt", "renamed wall.txt")
        edits = changes(self.root)
        self.assertEqual("renamed wall.txt", edits[0]["path"])
        self.assertEqual("wall file.txt", edits[0]["original_path"])
        self.assertEqual(["wall file.txt"], resource_conflicts(
            {"exclusive_resources": ["repo-file:wall file.txt"]}, edits))

    def test_missing_contract_does_not_fabricate_task(self):
        with self.assertRaisesRegex(ValueError, "No committed task"):
            inspect(self.root, "NSC-999")

    def test_clean_inventory_reports_no_edits(self):
        result = inspect(self.root)
        self.assertEqual([], result["local_changes"])
        self.assertEqual(["NSC-042"], [task["id"] for task in result["tasks"]])


class GitProcessTests(unittest.TestCase):
    def test_git_child_uses_no_window_on_windows(self):
        completed = mock.Mock(returncode=0, stdout=b"ok", stderr=b"")
        with mock.patch("Pipeline.AssistantControl.inspect_project.subprocess.run",
                        return_value=completed) as run:
            self.assertEqual(b"ok", git(Path("C:/fixture"), "status"))
        expected = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        self.assertEqual(expected, run.call_args.kwargs["creationflags"])

    def test_git_retries_local_clone_through_bundle_after_exact_msys_failure(self):
        if os.name != "nt":
            self.skipTest("Windows-only process creation recovery")
        failed = mock.Mock(
            returncode=1, stdout=b"",
            stderr=b"sh.exe: *** fatal error - couldn't create signal pipe, Win32 error 5",
        )
        succeeded = mock.Mock(returncode=0, stdout=b"ok", stderr=b"")
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            destination = root / "checkout"
            with mock.patch(
                "Pipeline.AssistantControl.inspect_project.subprocess.run",
                side_effect=(failed, succeeded, succeeded, succeeded),
            ) as run:
                self.assertEqual(b"ok", git(
                    source, "clone", "--no-local", "--no-checkout",
                    str(source), str(destination),
                ))
        self.assertEqual(4, run.call_count)
        self.assertIn("bundle", run.call_args_list[1].args[0])
        self.assertNotIn("--no-local", run.call_args_list[2].args[0])
        self.assertEqual("set-url", run.call_args_list[3].args[0][-3])

    def test_git_does_not_retry_real_git_failure(self):
        failed = mock.Mock(
            returncode=128, stdout=b"", stderr=b"fatal: repository does not exist",
        )
        with mock.patch(
            "Pipeline.AssistantControl.inspect_project.subprocess.run",
            return_value=failed,
        ) as run:
            with self.assertRaisesRegex(RuntimeError, "repository does not exist"):
                git(Path("C:/fixture"), "fetch")
        self.assertEqual(1, run.call_count)


if __name__ == "__main__":
    unittest.main()


class ResolvableCommitTests(unittest.TestCase):
    """A commit absent from a checkout is not a proven non-ancestor."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.run_git("init")
        name, email = validated_agent_git_identity()
        self.run_git("config", "user.name", name)
        self.run_git("config", "user.email", email)
        (self.root / "a.txt").write_text("a\n")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "base")
        self.head = self.run_git("rev-parse", "HEAD").decode().strip()

    def run_git(self, *args):
        return git(self.root, *args)

    def test_a_present_commit_resolves_and_reports_nothing(self):
        self.assertIsNone(
            unresolvable_commit(self.root, ("current source HEAD", self.head)))

    def test_an_absent_commit_is_named_with_its_label(self):
        absent = "0" * 40
        missing = unresolvable_commit(self.root, ("current source HEAD", absent))
        self.assertIsNotNone(missing)
        self.assertIn("current source HEAD", missing)
        self.assertIn(absent, missing)
        self.assertIn("not present in the task checkout", missing)

    def test_the_first_absent_commit_wins_so_the_cause_is_the_one_reported(self):
        """Order is caller-declared; reporting the second would misname the cause."""
        absent_a, absent_b = "0" * 40, "1" * 40
        missing = unresolvable_commit(
            self.root, ("first label", absent_a), ("second label", absent_b))
        self.assertIn("first label", missing)
        self.assertNotIn("second label", missing)

    def test_a_tree_or_blob_id_is_not_accepted_as_a_commit(self):
        """`cat-file -e <sha>` alone passes for any object; the helper pins ^{commit}."""
        tree = self.run_git("rev-parse", "HEAD^{tree}").decode().strip()
        missing = unresolvable_commit(self.root, ("the rejected candidate", tree))
        self.assertIsNotNone(missing, "a tree id was accepted as a commit")


class TaskCheckoutAncestryCallersTests(unittest.TestCase):
    """Every `--is-ancestor` on a TASK CHECKOUT resolves its objects first.

    Same shape as EveryCallerPassesTheRole. Without this the helper is an
    honour system: a new site can add a bare `--is-ancestor` on a task checkout
    and silently reintroduce "not an ancestor" for a commit that is merely
    absent. Sites that run against `checkouts.source` are NOT covered here -
    canonical holds both objects by construction.
    """

    @staticmethod
    def _task_checkout_ancestry_calls(function):
        """Ancestry calls in this function that run against a TASK CHECKOUT.

        A canonical call reads `checkouts.source`, which holds both objects by
        construction; only the per-task root can be missing one.
        """
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Name) and node.func.id == "git"):
                continue
            literals = [a.value for a in node.args
                        if isinstance(a, ast.Constant) and type(a.value) is str]
            if "--is-ancestor" not in literals or not node.args:
                continue
            if "source" in ast.unparse(node.args[0]):
                continue
            yield node

    def test_both_task_checkout_sites_resolve_before_comparing(self):
        """Binds per FUNCTION, not per file.

        A file-level substring check would pass while a SECOND bare
        `--is-ancestor` sat in the same module reintroducing the defect.
        """
        root = Path(__file__).resolve().parent
        checked = 0
        for name in ("revisions.py", "admission.py"):
            tree = ast.parse((root / name).read_text(encoding="utf-8"))
            for function in ast.walk(tree):
                if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                calls = list(self._task_checkout_ancestry_calls(function))
                if not calls:
                    continue
                checked += len(calls)
                resolves = any(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "unresolvable_commit"
                    for node in ast.walk(function)
                )
                self.assertTrue(
                    resolves,
                    f"{name}:{function.name} compares ancestry on a task checkout "
                    f"without resolving its objects first",
                )
        self.assertEqual(
            2, checked,
            "expected exactly two task-checkout ancestry sites; the set changed",
        )

