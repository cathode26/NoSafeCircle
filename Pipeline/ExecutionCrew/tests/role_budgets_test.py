"""Crew role budgets: the full-profile implementer gets room to edit authored assets."""
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
    def test_full_profile_implementer_gets_the_large_budget(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NSC_IMPLEMENTER_TURN_LIMIT", None)
            os.environ.pop("NSC_IMPLEMENTER_TIMEOUT_SECONDS", None)
            budget = role_budgets("implementer", "full")
        self.assertEqual((budget.turn_limit, budget.timeout_seconds), (96, 3600.0))
        self.assertEqual((role_budgets("implementer", None).turn_limit), 96, "no profile means full")

    def test_other_roles_and_profiles_keep_the_default(self):
        for role, profile in (("implementer", "lean"), ("validator", "full"), ("test_author", "full")):
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
