"""Component regression tests using only temporary Git projects."""
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl import test_review as fixture
from Pipeline.AssistantControl.successful_tasks import preserve_success


class SuccessfulProjectTests(unittest.TestCase):
    setUp = fixture.ReviewTests.setUp
    run_git = fixture.ReviewTests.run_git
    manager = fixture.ReviewTests.manager
    candidate = fixture.ReviewTests.candidate
    approve = fixture.ReviewTests.approve

    def success_root(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return (Path(temp.name) / "SuccessfullTasks").resolve()

    def test_only_approved_integrated_candidate_is_preserved_and_repeat_is_safe(self):
        gate, record, commit, branch = self.candidate()
        root = self.success_root()
        with self.assertRaisesRegex(ValueError, "approved and integrated"):
            preserve_success(gate.checkouts, "NSC-042", root)
        self.approve(gate, commit)
        with self.assertRaisesRegex(ValueError, "approved and integrated"):
            preserve_success(gate.checkouts, "NSC-042", root)
        gate.integrate("NSC-042", expected_source_commit=record["source_commit"], target_branch=branch)
        first = preserve_success(gate.checkouts, "NSC-042", root)
        second = preserve_success(gate.checkouts, "NSC-042", root)
        self.assertEqual(first["successful_project"], second["successful_project"])
        self.assertEqual(str(root / "NSC-042"), first["successful_project"]["path"])
        self.assertEqual(commit, first["successful_project"]["commit"])
        self.assertEqual("candidate\n", (root / "NSC-042/wall file.txt").read_text())
        self.assertTrue(Path(record["checkout"]).is_dir())

    def test_existing_successful_project_is_never_overwritten(self):
        gate, record, commit, branch = self.candidate()
        self.approve(gate, commit)
        gate.integrate("NSC-042", expected_source_commit=record["source_commit"], target_branch=branch)
        root = self.success_root()
        existing = root / "NSC-042"
        existing.mkdir(parents=True)
        (existing / "working-game.txt").write_text("Keep this working version")
        with self.assertRaisesRegex(ValueError, "no overwrite"):
            preserve_success(gate.checkouts, "NSC-042", root)
        self.assertEqual("Keep this working version", (existing / "working-game.txt").read_text())


if __name__ == "__main__":
    unittest.main()
