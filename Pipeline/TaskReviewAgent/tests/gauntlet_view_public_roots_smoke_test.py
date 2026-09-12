"""Component regression: public viewer never discovers sibling private runs."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from Pipeline.TaskReviewAgent.GauntletView.server import discover_roots


class PublicRootsTests(unittest.TestCase):
    def test_default_roots_are_this_checkout_without_filesystem_discovery(self):
        with patch.object(Path, "glob", side_effect=AssertionError("unexpected discovery")):
            self.assertEqual(discover_roots(None, None), (ROOT / "Tasks", ROOT))

    def test_explicit_external_state_does_not_select_another_task_checkout(self):
        external = ROOT.parent / "explicit-test-state"
        self.assertEqual(discover_roots(None, str(external)), (ROOT / "Tasks", external))

    def test_explicit_task_and_state_roots_are_preserved(self):
        tasks = ROOT.parent / "explicit-test-checkout" / "Tasks"
        state = ROOT.parent / "explicit-test-state"
        self.assertEqual(discover_roots(str(tasks), str(state)), (tasks, state))


if __name__ == "__main__":
    unittest.main()
