#!/usr/bin/env python
"""The one-writer guard, which had no test and had never fired.

Run:
    python -B test_main_write.py

`main_write.start()` promised, in its own docstring, to refuse "when another role
has a MAIN-WRITE START without an END in the last 30 minutes". It could not: the
role was a module constant, every START was written with it, and the filter
`not item.startswith(ROLE)` therefore discarded every open write. `others` was
always empty. Two roles could hold open writes with no warning, and one role's
END closed another's START.

The GER Agent found it on 2026-09-20 (board H-20260920-10) by reproducing it
against a throwaway journal. Nothing here touches the live journal: every case
writes to a temp file, which is the property the module was built for -
`journal` is a required keyword argument on every function precisely so a test
cannot reach the real one.
"""
from __future__ import annotations

import ast
import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main_write as mw  # noqa: E402

HEAD_A = "a" * 40
HEAD_B = "b" * 40


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.journal = Path(self._tmp.name) / "journal.md"
        # NSC_ROLE must not leak in from the machine running the suite.
        self._role = os.environ.pop("NSC_ROLE", None)
        if self._role is not None:
            self.addCleanup(os.environ.__setitem__, "NSC_ROLE", self._role)

    def text(self) -> str:
        return self.journal.read_text(encoding="utf-8") if self.journal.is_file() else ""


class TheGuardActuallyRefuses(Base):
    """The behaviour the docstring promised and the code never delivered."""

    def test_a_second_role_is_refused_while_the_first_is_open(self):
        mw.start("first", HEAD_A, role="Game Agent", journal=self.journal)
        with self.assertRaises(SystemExit) as caught:
            mw.start("second", HEAD_B, role="Release Agent", journal=self.journal)
        self.assertIn("another main write is open", str(caught.exception))
        self.assertIn("Game Agent", str(caught.exception))

    def test_the_same_role_may_continue(self):
        """Its own open write is not a collision.

        The refusal is asserted ABSENT rather than merely not happening: when the
        filter compares against anything other than the caller, a role is refused
        its own write, and an uncaught SystemExit here reads as an ERROR - which
        a mutation harness scores as breakage rather than as detection. A
        positive case has to name the refusal it expects not to get.
        """
        mw.start("first", HEAD_A, role="Game Agent", journal=self.journal)
        try:
            mw.start("second", HEAD_B, role="Game Agent", journal=self.journal)
        except SystemExit as refused:
            self.fail(f"a role was refused its own open write: {refused}")
        self.assertEqual(self.text().count("MAIN-WRITE START Game Agent"), 2)

    def test_a_second_role_is_allowed_once_the_first_ends(self):
        """And the END has to be stamped with the role that ended.

        If every END carries one fixed role, this hand-off silently stops
        working: Game Agent's END clears nothing, and Release Agent is refused a
        write nobody holds. Asserted as an absent refusal for the same reason as
        above - otherwise the SystemExit is an ERROR, not a failure.
        """
        mw.start("first", HEAD_A, role="Game Agent", journal=self.journal)
        mw.end(HEAD_A, "done", role="Game Agent", journal=self.journal)
        self.assertIn("MAIN-WRITE END Game Agent", self.text())
        try:
            mw.start("second", HEAD_B, role="Release Agent", journal=self.journal)
        except SystemExit as refused:
            self.fail(f"the hand-off was refused after a clean end: {refused}")
        self.assertIn("MAIN-WRITE START Release Agent", self.text())

    def test_one_roles_end_does_not_close_anothers_start(self):
        """The second half of the defect, and the more dangerous half.

        `end()` popped the pending map by the same module constant, so any
        role's END cleared whatever was open. A role could believe it held the
        write while another had already taken it.
        """
        mw.start("first", HEAD_A, role="Game Agent", journal=self.journal)
        mw.end(HEAD_B, "unrelated", role="Release Agent", journal=self.journal)
        with self.assertRaises(SystemExit) as caught:
            mw.start("third", HEAD_B, role="Documentation Agent", journal=self.journal)
        self.assertIn("Game Agent", str(caught.exception),
                      "Release Agent's END closed Game Agent's START")

    def test_the_start_is_written_under_the_callers_own_heading(self):
        mw.start("first", HEAD_A, role="Pipeline Maintainer Agent", journal=self.journal)
        self.assertIn("Pipeline Maintainer Agent", self.text().splitlines()[1])
        self.assertNotIn("GER Agent", self.text())


class TheRoleMustBeSupplied(Base):
    def test_no_role_and_no_environment_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            mw.start("first", HEAD_A, role=None, journal=self.journal)
        self.assertIn("needs the role", str(caught.exception))
        self.assertEqual(self.text(), "", "a refused start still wrote to the journal")

    def test_the_environment_supplies_it_when_the_flag_does_not(self):
        os.environ["NSC_ROLE"] = "Cleanup Agent"
        self.addCleanup(os.environ.pop, "NSC_ROLE", None)
        mw.start("first", HEAD_A, role=None, journal=self.journal)
        self.assertIn("MAIN-WRITE START Cleanup Agent", self.text())

    def test_an_explicit_role_beats_the_environment(self):
        os.environ["NSC_ROLE"] = "Cleanup Agent"
        self.addCleanup(os.environ.pop, "NSC_ROLE", None)
        mw.start("first", HEAD_A, role="Viewer Agent", journal=self.journal)
        self.assertIn("MAIN-WRITE START Viewer Agent", self.text())

    def test_a_role_the_journal_cannot_be_parsed_for_is_refused(self):
        """The same defect one layer down, found while fixing the first.

        `open_writes` reads roles back with a pattern ending in Agent, Steward or
        Orchestrator. A role outside that writes a START the guard can never see
        again - invisible, so the collision check is dead for that role exactly
        as it was dead for everyone. Refused at write time instead.
        """
        for bad in ("Vincent", "pipeline-maintainer", "Agent 7", ""):
            with self.subTest(role=bad):
                with self.assertRaises(SystemExit):
                    mw.start("first", HEAD_A, role=bad, journal=self.journal)
        self.assertEqual(self.text(), "")

    def test_every_role_actually_in_use_is_accepted(self):
        for role in ("GER Agent", "Game Agent", "Release Agent", "Cleanup Agent",
                     "Documentation Agent", "Pipeline Maintainer Agent",
                     "Art Director Agent", "Viewer Agent", "Decomposition Agent",
                     "Integration Steward"):
            with self.subTest(role=role):
                self.assertEqual(mw.resolve_role(role), role)

    def test_end_needs_a_role_too(self):
        with self.assertRaises(SystemExit):
            mw.end(HEAD_A, "done", role=None, journal=self.journal)


class TheJournalIsStillReadBack(Base):
    """open_writes must see what start wrote - the two halves have to agree."""

    def test_a_start_is_visible_to_open_writes(self):
        mw.start("first", HEAD_A, role="Game Agent", journal=self.journal)
        self.assertEqual(len(mw.open_writes(journal=self.journal)), 1)
        self.assertTrue(mw.open_writes(journal=self.journal)[0].startswith("Game Agent since"))

    def test_an_end_clears_only_its_own_role(self):
        mw.start("a", HEAD_A, role="Game Agent", journal=self.journal)
        mw.end(HEAD_A, "done", role="Game Agent", journal=self.journal)
        self.assertEqual(mw.open_writes(journal=self.journal), [])

    def test_an_old_start_falls_out_of_the_window(self):
        mw.start("first", HEAD_A, role="Game Agent", journal=self.journal)
        self.assertEqual(mw.open_writes(minutes=0, journal=self.journal), [])


class EveryCallerPassesTheRole(unittest.TestCase):
    """The signature change broke two callers, and nothing here was looking.

    `role` became a required keyword-only argument on 2026-09-22. The three
    callers under `ger/` were updated. `new_task_commit.py` and
    `policy_entry_commit.py` under `ger-contract-revisions-20260916/` were not,
    even though the agreed plan named them, and both raise
    `TypeError: start() missing 1 required keyword-only argument: 'role'` at
    their first journal write. The GER Agent found them by running the scripts.

    A line grep cannot answer this: these calls wrap, `role=` lands on a
    continuation line, and grepping for its absence reports six callers that are
    in fact correct. Parse instead.

    Worth stating plainly: this sees only the tracked tree. The same two files
    also live at `C:/nscrev/ger-contract-revisions-20260916/`, outside any
    checkout, and nothing in CI can reach them. Landing a signature change means
    copying there too.
    """

    HOST = Path(__file__).resolve().parents[2]

    def test_no_tracked_caller_omits_the_role(self):
        offenders = []
        for path in sorted(self.HOST.rglob("*.py")):
            parts = set(path.parts)
            if "__pycache__" in parts or "tests" in parts:
                continue
            if "retired-" in path.name:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "main_write"
                        and func.attr in ("start", "end")):
                    continue
                if not any(kw.arg == "role" for kw in node.keywords):
                    offenders.append(f"{path.relative_to(self.HOST)}:"
                                     f"{node.lineno} main_write.{func.attr}()")
        self.assertEqual([], offenders,
                         "these callers omit role= and raise TypeError at the "
                         "first journal write: " + "; ".join(offenders))

    def test_the_rule_this_enforces_is_still_real(self):
        """Guard the guard: if role stops being required, the test above passes
        on every file whatever it says, which is the vacuous shape this module
        exists to punish."""
        for name in ("start", "end"):
            parameter = inspect.signature(getattr(mw, name)).parameters.get("role")
            self.assertIsNotNone(parameter, f"{name}() no longer takes a role")
            self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY,
                          f"{name}()'s role is no longer keyword-only")
            self.assertIs(parameter.default, inspect.Parameter.empty,
                          f"{name}()'s role has acquired a default - which is "
                          "exactly what made the guard compare every role "
                          "against itself until 2026-09-22")


if __name__ == "__main__":
    unittest.main(verbosity=2)
