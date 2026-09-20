#!/usr/bin/env python
"""Tests for nsc_paths, the shared root resolver.

Run:
    python -B test_nsc_paths.py

Every test isolates the environment, because the three variables under test are
read from it and a developer's own NSC_HOME would otherwise decide the results.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nsc_paths  # noqa: E402

VARS = ("NSC_HOME", "NSC_CANONICAL", "NSC_WORK")


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


class TheEnvironmentAlwaysWins(Base):
    def test_each_root_reads_its_own_variable(self):
        self.at("some", "Tools", "Host")
        os.environ["NSC_HOME"] = r"F:\NSC"
        os.environ["NSC_CANONICAL"] = r"F:\NSC\NoSafeCircle"
        os.environ["NSC_WORK"] = r"F:\NSC\ValidationRuns"
        self.assertEqual(nsc_paths.workspace().path, Path(r"F:\NSC"))
        self.assertEqual(nsc_paths.canonical().path, Path(r"F:\NSC\NoSafeCircle"))
        self.assertEqual(nsc_paths.work().path, Path(r"F:\NSC\ValidationRuns"))

    def test_it_beats_a_derivation_that_would_have_worked(self):
        # Without the variable this derives canonical from the tracked layout.
        repo = self.tmp / "repo"
        self.at("repo", "Tools", "Host")
        self.assertEqual(nsc_paths.canonical().path, repo)
        os.environ["NSC_CANONICAL"] = r"F:\elsewhere"
        self.assertEqual(nsc_paths.canonical().path, Path(r"F:\elsewhere"))

    def test_the_reason_travels_with_the_value(self):
        os.environ["NSC_HOME"] = r"F:\NSC"
        self.assertEqual(nsc_paths.workspace().how, "environment NSC_HOME")

    def test_blank_and_whitespace_are_not_a_setting(self):
        for blank in ("", "   ", "\t"):
            os.environ["NSC_WORK"] = blank
            self.assertEqual(nsc_paths.work().path, nsc_paths.DEFAULT_WORK,
                             f"{blank!r} should not count as configured")

    def test_surrounding_whitespace_is_stripped(self):
        os.environ["NSC_HOME"] = "  F:\\NSC  "
        self.assertEqual(nsc_paths.workspace().path, Path(r"F:\NSC"))


class DerivingFromWhereTheFileIs(Base):
    def test_tracked_copy_derives_the_repo_it_lives_in(self):
        repo = self.tmp / "checkout"
        self.at("checkout", "Tools", "Host")
        root = nsc_paths.canonical()
        self.assertEqual(root.path, repo)
        self.assertIn("tracked", root.how)

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
    def _deployed_under(self, home_parts):
        """Put the file at <home>/tools so canonical must search under <home>."""
        self.at(*home_parts, "tools")

    def test_this_machines_doubled_layout(self):
        home = self.tmp / "NSC"
        (home / "NSC" / "NoSafeCircle").mkdir(parents=True)
        self._deployed_under(["NSC"])
        root = nsc_paths.canonical()
        self.assertEqual(root.path, home / "NSC" / "NoSafeCircle")
        self.assertEqual(root.how, "found under the workspace")

    def test_the_flat_layout_the_f_validation_checkout_uses(self):
        home = self.tmp / "NSC"
        (home / "NoSafeCircle").mkdir(parents=True)
        self._deployed_under(["NSC"])
        root = nsc_paths.canonical()
        self.assertEqual(root.path, home / "NoSafeCircle")

    def test_the_doubled_layout_wins_when_both_exist(self):
        home = self.tmp / "NSC"
        (home / "NSC" / "NoSafeCircle").mkdir(parents=True)
        (home / "NoSafeCircle").mkdir(parents=True)
        self._deployed_under(["NSC"])
        self.assertEqual(nsc_paths.canonical().path, home / "NSC" / "NoSafeCircle")

    def test_neither_existing_says_so_instead_of_pretending(self):
        self._deployed_under(["NSC"])
        root = nsc_paths.canonical()
        self.assertIn("does not exist", root.how)


class WorkIsNeverDerived(Base):
    def test_a_deployed_location_does_not_invent_it(self):
        # work is a sibling with an unrelated name: C:\NSC -> C:\nscrev.
        self.at("NSC", "tools")
        root = nsc_paths.work()
        self.assertEqual(root.path, nsc_paths.DEFAULT_WORK)
        self.assertEqual(root.how, "documented default")

    def test_a_tracked_location_does_not_invent_it_either(self):
        self.at("checkout", "Tools", "Host")
        self.assertEqual(nsc_paths.work().path, nsc_paths.DEFAULT_WORK)


class RequireFailsLoudly(Base):
    def test_it_returns_paths_when_everything_exists(self):
        home = self.tmp / "NSC"
        home.mkdir()
        os.environ["NSC_HOME"] = str(home)
        os.environ["NSC_WORK"] = str(self.tmp)
        got = nsc_paths.require("workspace", "work")
        self.assertEqual(got["workspace"], home)

    def test_a_missing_root_names_itself_its_path_and_how_it_was_decided(self):
        os.environ["NSC_HOME"] = r"F:\definitely-not-here"
        with self.assertRaises(FileNotFoundError) as caught:
            nsc_paths.require("workspace")
        message = str(caught.exception)
        self.assertIn("workspace", message)
        self.assertIn("definitely-not-here", message)
        self.assertIn("environment NSC_HOME", message)
        self.assertIn("NSC_HOME", message)

    def test_every_missing_root_is_reported_not_just_the_first(self):
        os.environ["NSC_HOME"] = r"F:\nope-one"
        os.environ["NSC_WORK"] = r"F:\nope-two"
        with self.assertRaises(FileNotFoundError) as caught:
            nsc_paths.require("workspace", "work")
        message = str(caught.exception)
        self.assertIn("nope-one", message)
        self.assertIn("nope-two", message)

    def test_an_unknown_root_name_is_a_programming_error(self):
        with self.assertRaises(KeyError):
            nsc_paths.require("nscrev")


class DescribeIsTheAuditTrail(Base):
    def test_it_reports_every_root_with_its_reason(self):
        os.environ["NSC_HOME"] = str(self.tmp)
        got = nsc_paths.describe()
        self.assertEqual(sorted(got), ["canonical", "work", "workspace"])
        self.assertEqual(got["workspace"]["path"], str(self.tmp))
        self.assertEqual(got["workspace"]["how"], "environment NSC_HOME")
        self.assertEqual(got["workspace"]["exists"], "true")

    def test_it_reports_a_root_that_is_not_there(self):
        os.environ["NSC_WORK"] = r"F:\absent"
        self.assertEqual(nsc_paths.describe()["work"]["exists"], "false")


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
        os.environ["NSC_HOME"] = r"C:\NSC"
        self.assertEqual(nsc_paths.workspace(), Path(r"C:\NSC"))


class TheDefaultsAreThisMachine(Base):
    def test_nothing_changes_until_someone_sets_the_environment(self):
        # The whole point: this module is a no-op on the machine it was written
        # on, so introducing it cannot move anything by itself.
        self.at("somewhere", "unrecognised")
        self.assertEqual(nsc_paths.workspace().path, Path(r"C:\NSC"))
        self.assertEqual(nsc_paths.work().path, Path(r"C:\nscrev"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
