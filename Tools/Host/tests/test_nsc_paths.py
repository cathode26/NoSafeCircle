#!/usr/bin/env python
"""Tests for nsc_paths, the shared root resolver.

Run:
    python -B test_nsc_paths.py

The environment is isolated in setUp, both because NSC_WORK is read from it and
because a developer with a stale NSC_HOME set must not be able to change what
these tests prove.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nsc_paths  # noqa: E402

# NSC_HOME and NSC_CANONICAL are NOT settings. They are listed here so the
# tests can prove they are ignored, which is the security property.
VARS = ("NSC_WORK", "NSC_HOME", "NSC_CANONICAL")


class Base(unittest.TestCase):
    def setUp(self):
        self._saved_env = {k: os.environ.get(k) for k in VARS}
        for k in VARS:
            os.environ.pop(k, None)
        self._saved_here = nsc_paths._HERE
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        nsc_paths._HERE = self._saved_here
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def at(self, *parts: str) -> Path:
        """Pretend nsc_paths lives at this location."""
        where = self.tmp.joinpath(*parts)
        where.mkdir(parents=True, exist_ok=True)
        nsc_paths._HERE = where
        return where


class TheEnvironmentCannotMoveAGuard(Base):
    """The reason this module does not have an NSC_HOME.

    run_job.py derives FORBIDDEN_ROOT from workspace() and refuses --out under
    it, refuses a job clone under it, and refuses to use canonical() as a job
    clone. A review on 2026-09-18 found that a caller who could move those two
    values got a read-write job in the live canonical checkout, with every guard
    passing. These tests are that finding, kept executable.
    """

    def test_nsc_home_does_not_move_the_workspace(self):
        home = self.tmp / "NSC"
        self.at("NSC", "tools")
        os.environ["NSC_HOME"] = r"F:\somewhere-harmless"
        root = nsc_paths.workspace()
        self.assertEqual(root.path, home)
        self.assertNotIn("environment", root.how)

    def test_nsc_canonical_does_not_move_the_checkout(self):
        home = self.tmp / "NSC"
        (home / "NSC" / "NoSafeCircle").mkdir(parents=True)
        self.at("NSC", "tools")
        os.environ["NSC_CANONICAL"] = r"F:\somewhere-harmless"
        root = nsc_paths.canonical()
        self.assertEqual(root.path, home / "NSC" / "NoSafeCircle")
        self.assertNotIn("environment", root.how)

    def test_no_variable_at_all_moves_the_guarded_roots(self):
        # Anything an attacker might try, including the names a future
        # well-meaning change would reach for first.
        home = self.tmp / "NSC"
        self.at("NSC", "tools")
        for name in ("NSC_HOME", "NSC_CANONICAL", "NSC_ROOT", "NSC_WORKSPACE",
                     "NSC_BASE", "NSC_INSTALL"):
            os.environ[name] = r"F:\somewhere-harmless"
        try:
            self.assertEqual(nsc_paths.workspace().path, home)
        finally:
            for name in ("NSC_ROOT", "NSC_WORKSPACE", "NSC_BASE", "NSC_INSTALL"):
                os.environ.pop(name, None)

    def test_moving_the_tools_is_what_moves_the_guard(self):
        # The supported way to relocate: deploy the tools under the new root.
        for home_name in ("NSC", "NSC-on-F"):
            home = self.tmp / home_name
            self.at(home_name, "tools")
            self.assertEqual(nsc_paths.workspace().path, home)


class WorkIsTheOneConfigurableRoot(Base):
    def test_nsc_work_is_honoured(self):
        os.environ["NSC_WORK"] = r"F:\NSC\ValidationRuns"
        root = nsc_paths.work()
        self.assertEqual(root.path, Path(r"F:\NSC\ValidationRuns"))
        self.assertEqual(root.how, "environment NSC_WORK")

    def test_blank_and_whitespace_are_not_a_setting(self):
        for blank in ("", "   ", "\t"):
            os.environ["NSC_WORK"] = blank
            self.assertEqual(nsc_paths.work().path, nsc_paths.DEFAULT_WORK,
                             f"{blank!r} should not count as configured")

    def test_surrounding_whitespace_is_stripped(self):
        os.environ["NSC_WORK"] = "  F:\\scratch  "
        self.assertEqual(nsc_paths.work().path, Path(r"F:\scratch"))

    def test_it_is_never_derived_from_a_deployed_location(self):
        # C:\NSC -> C:\nscrev is not a derivation anyone could compute.
        self.at("NSC", "tools")
        root = nsc_paths.work()
        self.assertEqual(root.path, nsc_paths.DEFAULT_WORK)
        self.assertEqual(root.how, "documented default")

    def test_it_is_never_derived_from_a_tracked_location_either(self):
        self.at("checkout", "Tools", "Host")
        self.assertEqual(nsc_paths.work().path, nsc_paths.DEFAULT_WORK)


class DerivingFromWhereTheFileIs(Base):
    def test_deployed_copy_derives_the_workspace_above_it(self):
        home = self.tmp / "NSC"
        self.at("NSC", "tools")
        root = nsc_paths.workspace()
        self.assertEqual(root.path, home)
        self.assertIn("deployed", root.how)

    def test_an_unrecognised_location_falls_back_to_the_default(self):
        self.at("somewhere", "random")
        self.assertEqual(nsc_paths.workspace().path, nsc_paths.DEFAULT_WORKSPACE)
        self.assertEqual(nsc_paths.workspace().how, "documented default")

    def test_tools_directory_name_is_matched_case_insensitively(self):
        # The tracked tree spells it Tools/Host; a deployment spells it tools.
        home = self.tmp / "NSC"
        self.at("NSC", "TOOLS")
        self.assertEqual(nsc_paths.workspace().path, home)


class CanonicalTriesBothKnownLayouts(Base):
    def test_this_machines_doubled_layout(self):
        home = self.tmp / "NSC"
        (home / "NSC" / "NoSafeCircle").mkdir(parents=True)
        self.at("NSC", "tools")
        root = nsc_paths.canonical()
        self.assertEqual(root.path, home / "NSC" / "NoSafeCircle")
        self.assertEqual(root.how, "found under the workspace")

    def test_the_flat_layout_the_f_validation_checkout_uses(self):
        home = self.tmp / "NSC"
        (home / "NoSafeCircle").mkdir(parents=True)
        self.at("NSC", "tools")
        self.assertEqual(nsc_paths.canonical().path, home / "NoSafeCircle")

    def test_the_doubled_layout_wins_when_both_exist(self):
        home = self.tmp / "NSC"
        (home / "NSC" / "NoSafeCircle").mkdir(parents=True)
        (home / "NoSafeCircle").mkdir(parents=True)
        self.at("NSC", "tools")
        self.assertEqual(nsc_paths.canonical().path, home / "NSC" / "NoSafeCircle")

    def test_neither_existing_says_so_instead_of_pretending(self):
        self.at("NSC", "tools")
        self.assertIn("does not exist", nsc_paths.canonical().how)


class CanonicalIsNotTheRepoYouLiveIn(Base):
    """The footgun the containing_repo split exists to remove."""

    def test_running_from_a_clone_does_not_make_that_clone_canonical(self):
        # run_job.py clones job clones FROM canonical, and refuses to use
        # canonical AS a job clone. If canonical derived from the tracked
        # location, a tool running inside a clone would make that clone both.
        home = self.tmp / "NSC"
        (home / "NSC" / "NoSafeCircle").mkdir(parents=True)
        self.at("some-job-clone", "Tools", "Host")
        # workspace falls back to the default here, so point canonical's search
        # at a real layout by deploying under it instead.
        self.assertIsNotNone(nsc_paths.containing_repo())
        self.assertNotEqual(nsc_paths.canonical().path,
                            nsc_paths.containing_repo().path)

    def test_containing_repo_answers_the_other_question(self):
        clone = self.tmp / "some-job-clone"
        self.at("some-job-clone", "Tools", "Host")
        root = nsc_paths.containing_repo()
        self.assertEqual(root.path, clone)
        self.assertIn("tracked", root.how)

    def test_containing_repo_is_none_for_a_deployed_copy(self):
        self.at("NSC", "tools")
        self.assertIsNone(nsc_paths.containing_repo())


class RequireFailsLoudly(Base):
    def test_it_returns_paths_when_everything_exists(self):
        home = self.tmp / "NSC"
        (home / "tools").mkdir(parents=True)
        self.at("NSC", "tools")
        os.environ["NSC_WORK"] = str(self.tmp)
        got = nsc_paths.require("workspace", "work")
        self.assertEqual(got["workspace"], home)

    def test_a_missing_root_names_itself_its_path_and_how_it_was_decided(self):
        os.environ["NSC_WORK"] = r"F:\definitely-not-here"
        with self.assertRaises(FileNotFoundError) as caught:
            nsc_paths.require("work")
        message = str(caught.exception)
        self.assertIn("work", message)
        self.assertIn("definitely-not-here", message)
        self.assertIn("environment NSC_WORK", message)

    def test_every_missing_root_is_reported_not_just_the_first(self):
        self.at("nowhere", "tools")   # workspace derives to a missing dir's parent
        os.environ["NSC_WORK"] = r"F:\nope-two"
        with self.assertRaises(FileNotFoundError) as caught:
            nsc_paths.require("canonical", "work")
        message = str(caught.exception)
        self.assertIn("canonical", message)
        self.assertIn("nope-two", message)

    def test_an_unknown_root_name_is_a_programming_error(self):
        with self.assertRaises(KeyError):
            nsc_paths.require("nscrev")


class DescribeIsTheAuditTrail(Base):
    def test_it_reports_every_root_with_its_reason(self):
        self.at("NSC", "tools")
        os.environ["NSC_WORK"] = str(self.tmp)
        got = nsc_paths.describe()
        self.assertEqual(sorted(got),
                         ["canonical", "containing_repo", "work", "workspace"])
        self.assertEqual(got["work"]["path"], str(self.tmp))
        self.assertEqual(got["work"]["how"], "environment NSC_WORK")
        self.assertEqual(got["work"]["exists"], "true")
        self.assertIn("deployed", got["workspace"]["how"])

    def test_it_reports_a_root_that_is_not_there(self):
        os.environ["NSC_WORK"] = r"F:\absent"
        self.assertEqual(nsc_paths.describe()["work"]["exists"], "false")

    def test_it_reports_having_no_containing_repository(self):
        self.at("NSC", "tools")
        self.assertEqual(nsc_paths.describe()["containing_repo"]["how"],
                         "not inside a checkout")


class RootBehavesLikeAPath(Base):
    def test_it_can_be_joined(self):
        os.environ["NSC_WORK"] = r"C:\work"
        self.assertEqual(nsc_paths.work() / "jobs" / "x.json",
                         Path(r"C:\work\jobs\x.json"))

    def test_it_works_with_os_fspath_and_open(self):
        os.environ["NSC_WORK"] = str(self.tmp)
        self.assertEqual(os.fspath(nsc_paths.work()), str(self.tmp))
        self.assertTrue(Path(nsc_paths.work()).is_dir())

    def test_it_compares_equal_to_the_path_it_holds(self):
        os.environ["NSC_WORK"] = r"C:\nscrev"
        self.assertEqual(nsc_paths.work(), Path(r"C:\nscrev"))


class TheDefaultsAreThisMachine(Base):
    def test_nothing_changes_until_the_tools_are_deployed_elsewhere(self):
        # The whole point: this module is a no-op on the machine it was written
        # on, so introducing it cannot move anything by itself.
        self.at("somewhere", "unrecognised")
        self.assertEqual(nsc_paths.workspace().path, Path(r"C:\NSC"))
        self.assertEqual(nsc_paths.work().path, Path(r"C:\nscrev"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
