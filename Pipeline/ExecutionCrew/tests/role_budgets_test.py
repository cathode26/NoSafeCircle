"""Crew role budgets: the full-profile writers get room; everything else keeps the default."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.ExecutionCrew.run_crew import role_budgets  # noqa: E402


class RoleBudgetTests(unittest.TestCase):
    def test_full_profile_writers_get_the_large_budget(self):
        """Both writing roles, pinned together.

        The implementer was raised after NSC-042 died on max_turns twice; the test author
        after NSC-007 died on the 1200s wall writing two full suites; the validator after
        NSC-047 died at 531.3s on error_max_turns with both writing roles already
        succeeded. The environment override cannot substitute for any of them: compose's
        crew services declare a fixed environment block, so a host value never reaches
        the container.
        """

        for role in ("implementer", "test_author", "validator"):
            with self.subTest(role=role):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop(f"NSC_{role.upper()}_TURN_LIMIT", None)
                    os.environ.pop(f"NSC_{role.upper()}_TIMEOUT_SECONDS", None)
                    budget = role_budgets(role, "full")
                self.assertEqual((budget.turn_limit, budget.timeout_seconds), (96, 3600.0))
                self.assertEqual(role_budgets(role, None).turn_limit, 96, "no profile means full")

    def test_other_roles_and_profiles_keep_the_default(self):
        # The standard-profile test author is deliberately not raised; only the full profile is.
        for role, profile in (("implementer", "lean"), ("test_author", "standard"),
                              ("validator", "standard")):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop(f"NSC_{role.upper()}_TURN_LIMIT", None)
                budget = role_budgets(role, profile)
            self.assertEqual((budget.turn_limit, budget.timeout_seconds), (32, 1200.0), (role, profile))

    def test_operator_override_wins(self):
        with patch.dict(os.environ, {"NSC_VALIDATOR_TURN_LIMIT": "48", "NSC_VALIDATOR_TIMEOUT_SECONDS": "900"}):
            budget = role_budgets("validator", "full")
        self.assertEqual((budget.turn_limit, budget.timeout_seconds), (48, 900.0))


if __name__ == "__main__":
    unittest.main()
