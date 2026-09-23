"""Repairing a worktree file that does not match its filtered representation.

The refusal tests matter more than the repair test. A bare `git checkout --`
would pass every "it got clean" assertion here while silently discarding a real
edit, so what distinguishes this from that command is exactly what it REFUSES.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from Pipeline.AssistantControl import test_materialization_reopen as fixture
from Pipeline.AssistantControl.checkout_representation import (
    CheckoutRepresentationError,
    repair_checkout_representation,
)
from Pipeline.AssistantControl.inspect_project import git

TASK = "NSC-046"
TRACKED = "Pipeline/Testing/run_unity_tests_clean.ps1"


class CheckoutRepresentationTests(unittest.TestCase):
    setUp = fixture.ReopenMaterializationTests.setUp
    git = staticmethod(fixture.ReopenMaterializationTests.git)

    def make_unfiltered_copy(self) -> tuple[Path, bytes]:
        """The NSC-048 shape: the RAW blob written straight into the worktree.

        Produced by writing the committed bytes rather than by checking them
        out, which is how the real one arrived.
        """
        checkout = self.checkout
        self.git(checkout, "config", "core.autocrlf", "true")
        target = checkout / TRACKED
        raw = git(checkout, "cat-file", "blob", f"HEAD:{TRACKED}")
        target.write_bytes(raw)
        self.assertTrue(
            git(checkout, "status", "--porcelain=v1", "--", TRACKED).strip(),
            "fixture did not reproduce the modified-but-identical state")
        return checkout, raw

    def test_an_unfiltered_copy_is_repaired_and_the_path_goes_clean(self):
        checkout, raw = self.make_unfiltered_copy()
        plan = repair_checkout_representation(
            self.manager, TASK, path=TRACKED, apply=True)
        self.assertTrue(plan["applied"])
        self.assertEqual("true", plan["autocrlf"])
        self.assertGreater(plan["expected_bytes"], plan["observed_bytes"])
        self.assertEqual(b"", git(checkout, "status", "--porcelain=v1", "--", TRACKED))
        self.assertNotEqual(raw, (checkout / TRACKED).read_bytes())

    def test_a_real_edit_is_REFUSED_rather_than_discarded(self):
        """The one that distinguishes this from `git checkout --`.

        That command would silently destroy this content and report success.
        """
        checkout = self.checkout
        self.git(checkout, "config", "core.autocrlf", "true")
        target = checkout / TRACKED
        target.write_bytes(b"# somebody's unsaved work\n")
        with self.assertRaisesRegex(CheckoutRepresentationError, "holds an edit"):
            repair_checkout_representation(self.manager, TASK, path=TRACKED, apply=True)
        self.assertEqual(b"# somebody's unsaved work\n", target.read_bytes())

    def test_a_staged_change_is_refused(self):
        checkout = self.checkout
        self.git(checkout, "config", "core.autocrlf", "true")
        (checkout / TRACKED).write_bytes(b"# staged\n")
        self.git(checkout, "add", "--", TRACKED)
        with self.assertRaisesRegex(CheckoutRepresentationError, "staged changes"):
            repair_checkout_representation(self.manager, TASK, path=TRACKED, apply=True)

    def test_an_already_correct_path_reports_nothing_to_do(self):
        repair = repair_checkout_representation(self.manager, TASK, path=TRACKED)
        self.assertTrue(repair.get("nothing_to_do"))
        self.assertFalse(repair["applied"])

    def test_a_plan_repairs_nothing(self):
        checkout, raw = self.make_unfiltered_copy()
        plan = repair_checkout_representation(self.manager, TASK, path=TRACKED)
        self.assertFalse(plan["applied"])
        self.assertEqual(raw, (checkout / TRACKED).read_bytes())
        self.assertTrue(git(checkout, "status", "--porcelain=v1", "--", TRACKED).strip())

    def test_an_untracked_path_is_refused(self):
        checkout = self.checkout
        (checkout / "loose.txt").write_bytes(b"x\n")
        with self.assertRaisesRegex(CheckoutRepresentationError, "not a single tracked path"):
            repair_checkout_representation(self.manager, TASK, path="loose.txt", apply=True)


if __name__ == "__main__":
    unittest.main()
