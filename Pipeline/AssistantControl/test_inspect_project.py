"""Pure/component regression tests; all mutations are in disposable Git repos.

Proves inventory preserves operator edits and reads committed task identity.
Does not prove Unity conformance, admission, provider behavior or delivery.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.inspect_project import changes, git, inspect, resource_conflicts
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
        completed = unittest.mock.Mock(returncode=0, stdout=b"ok", stderr=b"")
        with unittest.mock.patch("Pipeline.AssistantControl.inspect_project.subprocess.run",
                                 return_value=completed) as run:
            self.assertEqual(b"ok", git(Path("C:/fixture"), "status"))
        expected = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        self.assertEqual(expected, run.call_args.kwargs["creationflags"])


if __name__ == "__main__":
    unittest.main()
