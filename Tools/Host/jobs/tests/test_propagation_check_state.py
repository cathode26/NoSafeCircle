"""What the REPOSITORY looks like going in: working tree versus HEAD, dirty
trees, stale workflow ids, and telling a regression from a pre-existing
failure.\n
Split from test_propagation_check.py; the fixture is shared in
propcheck_fixtures.py.
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import propagation_check as pc  # noqa: E402
from propcheck_fixtures import GIT_IDENTITY, RepoCase, commit, run_git, write  # noqa: E402,F401


class WorkingTreeIsNotTheHead(RepoCase):
    """The clone is left checked out somewhere that is neither base nor head."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", """
            def removed_later(x):
                return x

            def kept(x):
                return x
        """)
        write(self.repo, "tests/test_api.py", """
            from pkg.api import kept

            print(kept("ok"))
        """)
        write(self.repo, ".github/workflows/ci.yml", """
            jobs:
              t:
                steps:
                  - run: python tests/test_api.py
        """)
        self.base = commit(self.repo, "base")

        write(self.repo, "pkg/api.py", """
            def kept(x):
                return x
        """)
        write(self.repo, "Docs/stale.md", "still calls removed_later\n")
        self.head = commit(self.repo, "head")

        # A third commit on main that knows nothing about any of it. The clone
        # is parked here, which is what a steward's clone looks like when they
        # are about to merge a branch into main.
        #
        # It deliberately DIFFERS from head everywhere the tool reads: the
        # stale doc is gone, and the workflow no longer names the test. A
        # fixture where the two revisions happened to agree would let a
        # working-tree read produce the right answer anyway - which is how the
        # defect survived a suite for as long as it did, and what the mutation
        # harness caught when these tests first went green for the wrong
        # reason.
        write(self.repo, "unrelated.py", "VALUE = 1\n")
        (self.repo / "Docs" / "stale.md").unlink()
        # The workflow is RENAMED, not just rewritten, so the set of workflow
        # files differs too. Listing them from the index instead of the
        # revision then finds a filename that does not exist at head, and the
        # CI marking silently comes back empty.
        (self.repo / ".github" / "workflows" / "ci.yml").unlink()
        write(self.repo, ".github/workflows/main-ci.yml", """
            jobs:
              t:
                steps:
                  - run: echo "this branch does not run the test"
        """)
        self.elsewhere = commit(self.repo, "unrelated work on main")

    def test_the_stale_reference_is_found_from_the_wrong_tree(self):
        """Docs/stale.md exists at head and NOT in the checked-out tree, so
        finding it proves the grep read the revision rather than the tree."""
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertIn("removed_later", self.symbol_names(data))
        hit_files = [h["file"] for s in data["removed_symbols"] for h in s["hits"]]
        self.assertIn("Docs/stale.md", hit_files)

    def test_the_selection_comes_from_head_not_from_the_tree(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertIn("tests/test_api.py", self.selected_paths(data))
        self.assertTrue(
            all(t["in_ci"] for t in data["importing_tests"]),
            "CI marking must read the workflows at head",
        )

    def test_a_file_that_exists_only_in_the_tree_is_never_selected(self):
        """The sharpest form of the defect: the working tree has files that
        exist at neither end of the range, and they were being scanned."""
        write(self.repo, "tests/test_only_on_main.py", """
            from pkg.api import kept

            print(kept("later"))
        """)
        commit(self.repo, "a test that exists at neither base nor head")
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertNotIn("tests/test_only_on_main.py", self.selected_paths(data))

    def test_the_report_says_the_tree_is_not_the_head(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertFalse(data["worktree_at_head"])

    def test_run_refuses_rather_than_measuring_the_wrong_revision(self):
        with self.assertRaises(pc.CheckError) as caught:
            self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        message = str(caught.exception)
        self.assertIn("checked out at", message)
        self.assertIn("checkout --detach", message)
        self.assertIn("--run-on-current-tree", message)

    def test_run_on_current_tree_is_the_explicit_escape_hatch(self):
        data = pc.analyse(
            str(self.repo), "%s..%s" % (self.base, self.head), 10, True,
            allow_tree_mismatch=True,
        )
        self.assertIn("run_results", data)
        self.assertFalse(data["run_tree_was_head"])

    def test_run_is_allowed_when_the_tree_really_is_the_head(self):
        run_git(self.repo, "checkout", "-q", "--detach", self.head)
        data = self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        self.assertTrue(data["worktree_at_head"])
        self.assertTrue(data["run_tree_was_head"])

class DirtyTreeIsNotTheHead(RepoCase):
    """Comparing commits alone let an edited tree count as the head."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/api.py", "VALUE = 2\n")
        write(self.repo, "tests/test_api.py", """
            from pkg.api import VALUE
            assert VALUE == 2, VALUE
        """)
        self.head = commit(self.repo, "head")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)
        # At the head commit, but not what the head says.
        write(self.repo, "pkg/api.py", "VALUE = 999\n")

    def test_a_dirty_tree_is_reported_dirty(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertTrue(data["worktree_dirty"])
        self.assertFalse(data["worktree_at_head"])

    def test_run_refuses_a_dirty_tree_even_at_the_right_commit(self):
        with self.assertRaises(pc.CheckError) as caught:
            self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        message = str(caught.exception)
        self.assertIn("uncommitted changes", message)
        self.assertIn("pkg/api.py", message)

    def test_the_escape_hatch_still_records_the_tree_was_not_the_head(self):
        data = pc.analyse(
            str(self.repo), "%s..%s" % (self.base, self.head), 10, True,
            allow_tree_mismatch=True,
        )
        self.assertFalse(data["run_tree_was_head"])
        self.assertTrue(data["run_dirty_worktree"])

    def test_a_clean_tree_at_the_head_is_accepted(self):
        run_git(self.repo, "checkout", "-q", "--", "pkg/api.py")
        data = self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        self.assertTrue(data["worktree_at_head"])
        self.assertFalse(data["worktree_dirty"])

class StaleWorkflowTestIds(RepoCase):
    """CI runs named method ids; renaming one left --run reporting success."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/tests/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        write(self.repo, "pkg/tests/test_viewer.py", """
            import unittest
            from pkg.api import VALUE


            class ViewerTests(unittest.TestCase):
                def test_review_alarm_fires(self):
                    self.assertEqual(1, VALUE)


            if __name__ == "__main__":
                unittest.main()
        """)
        write(self.repo, ".github/workflows/ci.yml", """
            jobs:
              t:
                steps:
                  - run: python -m unittest pkg.tests.test_viewer.ViewerTests.test_review_alarm_fires
        """)
        self.base = commit(self.repo, "base")

        write(self.repo, "pkg/api.py", "VALUE = 2\n")
        write(self.repo, "pkg/tests/test_viewer.py", """
            import unittest
            from pkg.api import VALUE


            class ViewerTests(unittest.TestCase):
                def test_review_alarm_triggers(self):
                    self.assertEqual(2, VALUE)


            if __name__ == "__main__":
                unittest.main()
        """)
        self.head = commit(self.repo, "rename the test method")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)

    def test_the_stale_method_id_is_reported(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        ids = [entry["id"] for entry in data["stale_workflow_test_ids"]]
        self.assertIn("pkg.tests.test_viewer.ViewerTests.test_review_alarm_fires", ids)

    def test_the_report_names_it(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        report = pc.build_report(data, 10)
        self.assertIn("STALE WORKFLOW TEST IDS", report)
        self.assertIn("no longer exist at head", report)
        self.assertIn("test_review_alarm_fires", report)

    def test_the_stale_id_now_fails_the_check(self):
        """RESTORED 2026-09-18. Round 5 found ten live ids flagged on one
        fixture from setattr loops, post-class-body assignment and
        method-adding class decorators, and the check was demoted to advisory
        until those three shapes were handled. `ViewerTests` here has plain
        TestCase bases and none of those shapes, so the renamed method is a
        genuinely stale id and the check fails on it again."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pc.main([str(self.repo), "%s..%s" % (self.base, self.head)])
        self.assertEqual(1, code)
        self.assertIn("test_review_alarm_fires", out.getvalue())

    # test_an_unrenamed_method_is_not_reported was REMOVED here: it analysed
    # base..base, so nothing was selected and the comparison never ran. Four
    # mutations survived behind it. StaleIdGuardsAreNotVacuous replaces it and
    # asserts first that the range really selects the tests.

class StaleIdsHaveNoFalsePositives(RepoCase):
    """Six shapes of a method that exists but is not a plain FunctionDef in
    the class's own body."""

    WORKFLOW_IDS = [
        "pkg.tests.test_viewer.ViewerTests.test_direct",
        "pkg.tests.test_viewer.ViewerTests.test_shared_contract",   # from a mixin
        "pkg.tests.test_viewer.ViewerTests.test_alias",             # name = other
        "pkg.tests.test_viewer.ViewerTests.test_generated",         # from a factory
        "pkg.tests.test_viewer.ViewerTests.test_windows_only",      # def inside an if
        "pkg.tests.test_viewer.GuardedTests.test_guarded",          # class inside an if
        "pkg.tests.test_viewer.ViewerTests",                        # module.Class form
        "pkg.tests.test_viewer.GuardedTests",                       # module.Class, plain bases
        "pkg.tests.test_viewer.SetattrTests.test_case_alpha",       # setattr loop after class
        "pkg.tests.test_viewer.AttributeAssignTests.test_from_attribute",  # Cls.x = fn
        "pkg.tests.test_viewer.DecoratedTests.test_from_decorator",  # class decorator
    ]

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/tests/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        write(self.repo, "pkg/tests/test_viewer.py", """
            import sys
            import unittest

            from pkg.api import VALUE


            def _make_case():
                def body(self):
                    self.assertTrue(True)
                return body


            class SharedContract:
                def test_shared_contract(self):
                    self.assertTrue(True)


            class ViewerTests(SharedContract, unittest.TestCase):
                def test_direct(self):
                    self.assertTrue(VALUE)

                test_alias = test_direct
                test_generated = _make_case()

                if sys.platform == "win32":
                    def test_windows_only(self):
                        self.assertTrue(True)


            if True:
                class GuardedTests(unittest.TestCase):
                    def test_guarded(self):
                        self.assertTrue(True)


            class SetattrTests(unittest.TestCase):
                pass


            def _make_setattr_case(n):
                def body(self):
                    self.assertTrue(True)
                return body


            for _n in ("alpha", "beta"):
                setattr(SetattrTests, "test_case_" + _n, _make_setattr_case(_n))


            class AttributeAssignTests(unittest.TestCase):
                pass


            def _attribute_case(self):
                self.assertTrue(True)


            AttributeAssignTests.test_from_attribute = _attribute_case


            def add_cases(cls):
                def _decorator_case(self):
                    self.assertTrue(True)
                cls.test_from_decorator = _decorator_case
                return cls


            @add_cases
            class DecoratedTests(unittest.TestCase):
                pass
        """)
        steps = "\n".join(
            "                  - run: python -m unittest %s" % i for i in self.WORKFLOW_IDS
        )
        write(self.repo, ".github/workflows/ci.yml",
              "jobs:\n  t:\n    steps:\n" + steps + "\n")
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/api.py", "VALUE = 2\n")
        self.head = commit(self.repo, "change the module the tests import")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)

    def test_every_workflow_id_really_runs_green(self):
        """If any of these did not run, the fixture would prove nothing."""
        env = dict(os.environ)
        env["PYTHONPATH"] = str(self.repo)
        for test_id in self.WORKFLOW_IDS:
            with self.subTest(test_id=test_id):
                proc = subprocess.run(
                    [sys.executable, "-B", "-m", "unittest", test_id],
                    cwd=str(self.repo), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    creationflags=pc.CREATE_NO_WINDOW,
                )
                self.assertEqual(
                    0, proc.returncode, proc.stdout.decode("utf-8", "replace")[-400:]
                )

    def test_none_of_them_is_reported_stale(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertEqual([], data["stale_workflow_test_ids"])

    def test_the_check_exits_zero(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = pc.main([str(self.repo), "%s..%s" % (self.base, self.head)])
        self.assertEqual(0, code)

    def test_a_commented_out_workflow_line_is_ignored(self):
        write(self.repo, ".github/workflows/retired.yml", """
            jobs:
              t:
                steps:
                  # retired: python -m unittest pkg.tests.test_viewer.GuardedTests.test_long_gone
                  - run: echo nothing
        """)
        head2 = commit(self.repo, "a retired, commented-out target")
        run_git(self.repo, "checkout", "-q", "--detach", head2)
        data = self.analyse("%s..%s" % (self.base, head2))
        self.assertEqual([], data["stale_workflow_test_ids"])

    def test_a_genuinely_removed_method_is_still_caught(self):
        """Tightening must not blind the check where it CAN still see.

        `GuardedTests(unittest.TestCase)` has plain bases, so a removed method
        there is provably absent and is reported - and, with the exit code
        restored, the check fails on it.
        """
        source = (self.repo / "pkg" / "tests" / "test_viewer.py").read_text(encoding="utf-8")
        source = source.replace("def test_guarded(self):", "def test_guarded_renamed(self):")
        (self.repo / "pkg" / "tests" / "test_viewer.py").write_text(source, encoding="utf-8")
        head2 = commit(self.repo, "rename a method on a plainly-based class")
        run_git(self.repo, "checkout", "-q", "--detach", head2)
        data = self.analyse("%s..%s" % (self.base, head2))
        ids = [entry["id"] for entry in data["stale_workflow_test_ids"]]
        self.assertIn("pkg.tests.test_viewer.GuardedTests.test_guarded", ids)
        with contextlib.redirect_stdout(io.StringIO()):
            code = pc.main([str(self.repo), "%s..%s" % (self.base, head2)])
        self.assertEqual(1, code)

    def test_a_class_with_a_mixin_is_deliberately_unverifiable(self):
        """The cost of no false positives, stated rather than hidden.

        `ViewerTests(SharedContract, unittest.TestCase)` can inherit methods
        from a base this file does not show, so renaming one of its own
        methods is NOT reported. That is a real miss, accepted on purpose: a
        false stale id exits 1 over green CI, and six of those is what the
        permissive version produced.
        """
        source = (self.repo / "pkg" / "tests" / "test_viewer.py").read_text(encoding="utf-8")
        source = source.replace("def test_direct(self):", "def test_renamed(self):")
        source = source.replace("    test_alias = test_direct\n", "")
        (self.repo / "pkg" / "tests" / "test_viewer.py").write_text(source, encoding="utf-8")
        head2 = commit(self.repo, "rename a method on a mixin-based class")
        run_git(self.repo, "checkout", "-q", "--detach", head2)
        data = self.analyse("%s..%s" % (self.base, head2))
        ids = [entry["id"] for entry in data["stale_workflow_test_ids"]]
        self.assertNotIn("pkg.tests.test_viewer.ViewerTests.test_direct", ids)

class StaleIdGuardsAreNotVacuous(RepoCase):
    """The round-3 guard analysed base..base, so nothing was selected and the
    comparison never ran: four mutations survived behind it."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/tests/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        write(self.repo, "pkg/tests/test_viewer.py", """
            import unittest
            from pkg.api import VALUE


            class ViewerTests(unittest.TestCase):
                def test_present(self):
                    self.assertTrue(VALUE)
        """)
        write(self.repo, "pkg/tests/test_view.py", """
            import unittest
            from pkg.api import VALUE


            class OtherTests(unittest.TestCase):
                def test_other(self):
                    self.assertTrue(VALUE)
        """)
        write(self.repo, ".github/workflows/ci.yml", """
            jobs:
              t:
                steps:
                  - run: python -m unittest pkg.tests.test_viewer.ViewerTests.test_present
                  - run: python -m unittest pkg.tests.test_view.OtherTests.test_other
        """)
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/api.py", "VALUE = 2\n")
        self.head = commit(self.repo, "change what they import")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)

    def test_the_range_really_selects_those_tests(self):
        """Without this the class below could pass by selecting nothing."""
        data = self.analyse("%s..%s" % (self.base, self.head))
        paths = self.selected_paths(data)
        self.assertIn("pkg/tests/test_viewer.py", paths)
        self.assertIn("pkg/tests/test_view.py", paths)

    def test_present_methods_are_not_reported(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertEqual([], data["stale_workflow_test_ids"])

    def test_a_module_name_that_prefixes_another_is_not_confused(self):
        """`pkg.tests.test_view` is a prefix of `pkg.tests.test_viewer`."""
        source = (self.repo / "pkg" / "tests" / "test_view.py").read_text(encoding="utf-8")
        (self.repo / "pkg" / "tests" / "test_view.py").write_text(
            source.replace("def test_other(self):", "def test_other_renamed(self):"),
            encoding="utf-8",
        )
        head2 = commit(self.repo, "rename only the shorter module's method")
        run_git(self.repo, "checkout", "-q", "--detach", head2)
        data = self.analyse("%s..%s" % (self.base, head2))
        ids = [entry["id"] for entry in data["stale_workflow_test_ids"]]
        self.assertEqual(["pkg.tests.test_view.OtherTests.test_other"], ids)

    def test_the_stale_check_reads_head_not_the_checked_out_tree(self):
        """The round-1 blocking class, which the new code had no test for."""
        source = (self.repo / "pkg" / "tests" / "test_viewer.py").read_text(encoding="utf-8")
        (self.repo / "pkg" / "tests" / "test_viewer.py").write_text(
            source.replace("def test_present(self):", "def test_present_renamed(self):"),
            encoding="utf-8",
        )
        head2 = commit(self.repo, "rename it at head2")
        # Park the clone somewhere the method still exists.
        run_git(self.repo, "checkout", "-q", "--detach", self.head)
        data = self.analyse("%s..%s" % (self.base, head2))
        ids = [entry["id"] for entry in data["stale_workflow_test_ids"]]
        self.assertIn("pkg.tests.test_viewer.ViewerTests.test_present", ids)

class BaselineTellsRegressionFromPreExisting(RepoCase):
    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        # Red at base and still red at head: pre-existing, not this range's fault.
        write(self.repo, "tests/test_always_red.py", """
            import sys
            from pkg.api import VALUE
            sys.exit(1)
        """)
        # Green at base, broken by the range: the only real regression.
        write(self.repo, "tests/test_breaks.py", """
            from pkg.api import VALUE
            assert VALUE == 1, VALUE
        """)
        # Red at base, repaired by the range.
        write(self.repo, "tests/test_gets_fixed.py", """
            from pkg.api import VALUE
            assert VALUE == 2, VALUE
        """)
        self.base = commit(self.repo, "base")

        write(self.repo, "pkg/api.py", "VALUE = 2\n")
        # Added by the range, so there is nothing to compare it against.
        write(self.repo, "tests/test_brand_new.py", """
            import sys
            from pkg.api import VALUE
            sys.exit(1)
        """)
        self.head = commit(self.repo, "head")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)

    def _verdicts(self, with_baseline: bool):
        data = pc.analyse(
            str(self.repo), "%s..%s" % (self.base, self.head), 10, True,
            with_baseline=with_baseline,
        )
        return data, {r["test"]: r.get("verdict") for r in data["run_results"]}

    def test_each_result_is_classified(self):
        data, verdicts = self._verdicts(True)
        self.assertIsNone(data["run_baseline"]["error"], data["run_baseline"])
        self.assertEqual("REGRESSION", verdicts["tests/test_breaks.py"])
        self.assertEqual("pre-existing", verdicts["tests/test_always_red.py"])
        self.assertEqual("fixed", verdicts["tests/test_gets_fixed.py"])
        self.assertEqual("new-at-head", verdicts["tests/test_brand_new.py"])

    def test_a_test_absent_at_base_is_named(self):
        data, _ = self._verdicts(True)
        self.assertIn("tests/test_brand_new.py",
                      data["run_baseline"]["not_present_at_base"])

    def test_the_report_marks_the_regression_and_not_the_others(self):
        data, _ = self._verdicts(True)
        report = pc.build_report(data, 10)
        # Scope to the --run results block. Each selected path also appears in
        # step 5's "RUN THESE" command list, and matching that line first is
        # exactly how this test failed for the wrong reason on its first run.
        self.assertIn("6. --run RESULTS", report)
        results_block = report.split("6. --run RESULTS", 1)[1]

        def result_line(path):
            return next(l for l in results_block.splitlines()
                        if path in l and "s  " in l)

        self.assertIn("REGRESSION", result_line("tests/test_breaks.py"))
        pre_existing = result_line("tests/test_always_red.py")
        self.assertIn("already red at base", pre_existing)
        self.assertNotIn("REGRESSION", pre_existing)

    def test_without_the_flag_every_verdict_is_unknown(self):
        """Honest rather than absent: the tool does not know."""
        data, verdicts = self._verdicts(False)
        self.assertIsNone(data["run_baseline"])
        self.assertEqual({"unknown"}, set(verdicts.values()))
        self.assertIn("--baseline", data["run_caveat"])

    def test_the_exit_code_still_fails_on_a_regression(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = pc.main([str(self.repo), "%s..%s" % (self.base, self.head),
                            "--run", "--baseline"])
        self.assertEqual(1, code)

class BaselineLeavesTheCloneAsItFoundIt(RepoCase):
    """--baseline is the one operation that writes to the clone, so it has to
    put everything back."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        write(self.repo, "tests/test_api.py", """
            from pkg.api import VALUE
            print(VALUE)
        """)
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/api.py", "VALUE = 2\n")
        self.head = commit(self.repo, "head")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)

    def _worktrees(self) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "list", "--porcelain"],
            stdout=subprocess.PIPE, creationflags=pc.CREATE_NO_WINDOW,
        )
        return proc.stdout.decode("utf-8", "replace")

    def test_no_worktree_is_left_registered(self):
        before = self._worktrees()
        pc.analyse(str(self.repo), "%s..%s" % (self.base, self.head), 10, True,
                   with_baseline=True)
        self.assertEqual(before, self._worktrees())

    def test_the_working_tree_is_still_clean_and_at_the_head(self):
        pc.analyse(str(self.repo), "%s..%s" % (self.base, self.head), 10, True,
                   with_baseline=True)
        self.assertFalse(pc.worktree_is_dirty(str(self.repo)))
        matches, _want, _got = pc.head_matches_worktree(str(self.repo), self.head)
        self.assertTrue(matches)

    def test_no_scratch_directory_is_left_behind(self):
        before = set(Path(tempfile.gettempdir()).glob("propcheck-base-*"))
        pc.analyse(str(self.repo), "%s..%s" % (self.base, self.head), 10, True,
                   with_baseline=True)
        after = set(Path(tempfile.gettempdir()).glob("propcheck-base-*"))
        self.assertEqual(before, after)

    def test_a_baseline_failure_degrades_to_unknown_rather_than_crashing(self):
        """A worktree that cannot be created must not lose the head results."""
        data = pc.analyse(
            str(self.repo), "%s..%s" % (self.base, self.head), 10, True,
            with_baseline=True,
        )
        # Force the failure path directly: the base revision does not exist.
        broken = pc.run_at_baseline(str(self.repo), "0" * 40, [], None)
        self.assertIsNotNone(broken["error"])
        pc.classify_against_baseline(data["run_results"], broken)
        self.assertEqual({"unknown"},
                         {r["verdict"] for r in data["run_results"]})

if __name__ == "__main__":
    unittest.main(verbosity=2)
