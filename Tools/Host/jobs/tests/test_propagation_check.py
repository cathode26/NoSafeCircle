#!/usr/bin/env python3
"""Tests for propagation_check.py.

Each test builds a throwaway git repository under TMPDIR with a known base
and head commit, then asserts what the tool reports. Nothing here touches
the real repository, and no test spawns a console window.

    python -B tests/test_propagation_check.py
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import time
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import propagation_check as pc  # noqa: E402

GIT_IDENTITY = [
    "-c", "user.name=Propagation Check Test",
    "-c", "user.email=propagation-check@nosafecircle.invalid",
    "-c", "commit.gpgsign=false",
]


def run_git(repo: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo)] + GIT_IDENTITY + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=pc.CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "git %s failed:\n%s" % (" ".join(args), proc.stdout.decode("utf-8", "replace"))
        )


def write(repo: Path, relative: str, text: str) -> None:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


def commit(repo: Path, message: str) -> str:
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", message)
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=pc.CREATE_NO_WINDOW,
    )
    return proc.stdout.decode().strip()


class RepoCase(unittest.TestCase):
    """Base class owning one disposable repository per test."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="propcheck-test-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "clone"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "symbolic-ref", "HEAD", "refs/heads/main")

    def analyse(self, rev_range: str, limit: int = 10, do_run: bool = False):
        return pc.analyse(str(self.repo), rev_range, limit, do_run)

    def symbol_names(self, data) -> list:
        return [s["name"] for s in data["removed_symbols"]]

    def selected_paths(self, data) -> list:
        return [t["path"] for t in data["importing_tests"]]


class RemovedFunctionWithWorkflowReference(RepoCase):
    """A removed function still named in .github/workflows must be reported."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/audit.py", """
            def run_contract_audit(path):
                return path

            def keep_me(path):
                return path
        """)
        write(self.repo, "tests/test_audit.py", """
            from pkg.audit import keep_me

            print(keep_me("ok"))
        """)
        write(self.repo, ".github/workflows/ci.yml", """
            jobs:
              audit:
                steps:
                  - run: python -c "from pkg.audit import run_contract_audit"
                  - run: python tests/test_audit.py
        """)
        write(self.repo, "Docs/notes.md", "We call run_contract_audit at merge time.\n")
        self.base = commit(self.repo, "base")

        write(self.repo, "pkg/audit.py", """
            def keep_me(path):
                return path
        """)
        self.head = commit(self.repo, "drop the audit")

    def test_reports_the_removed_function(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertEqual(self.symbol_names(data), ["run_contract_audit"])

    def test_finds_the_workflow_and_markdown_references(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        hits = data["removed_symbols"][0]["hits"]
        files = {hit["file"] for hit in hits}
        self.assertIn(".github/workflows/ci.yml", files)
        self.assertIn("Docs/notes.md", files)
        workflow_hits = [h for h in hits if h["in_workflow"]]
        self.assertEqual(len(workflow_hits), 1)
        self.assertFalse(any(hit["in_changed_file"] for hit in hits))

    def test_report_marks_the_ci_workflow_hit(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        report = pc.build_report(data, 10)
        self.assertIn("[CI WORKFLOW]", report)
        self.assertIn("run_contract_audit", report)

    def test_limit_caps_printed_hits(self):
        data = self.analyse("%s..%s" % (self.base, self.head), limit=1)
        symbol = data["removed_symbols"][0]
        self.assertEqual(len(symbol["hits"]), 1)
        self.assertGreater(symbol["reference_count"], 1)
        self.assertIn("more hit(s) not shown", pc.build_report(data, 1))


class RenamedClass(RepoCase):
    """A rename shows the old name gone, with the in-file hits marked as such."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/pool.py", """
            class SessionLease:
                def __init__(self, name):
                    self.name = name


            def make(name):
                return SessionLease(name)
        """)
        write(self.repo, "tests/test_pool.py", """
            from pkg.pool import make

            print(make("x"))
        """)
        write(self.repo, "Docs/pool.md", "SessionLease is the unit of ownership.\n")
        self.base = commit(self.repo, "base")

        write(self.repo, "pkg/pool.py", """
            class ProviderLease:
                def __init__(self, name):
                    self.name = name


            def make(name):
                return ProviderLease(name)
        """)
        self.head = commit(self.repo, "rename the lease class")

    def test_old_class_name_is_reported_removed(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertEqual(self.symbol_names(data), ["SessionLease"])

    def test_stale_doc_reference_is_external(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        symbol = data["removed_symbols"][0]
        self.assertEqual(symbol["external_reference_count"], 1)
        self.assertEqual(symbol["hits"][0]["file"], "Docs/pool.md")

    def test_importing_test_is_still_selected(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertEqual(self.selected_paths(data), ["tests/test_pool.py"])


class RenameConfinedToOneFile(RepoCase):
    """Hits inside the changed file itself are flagged, not treated as stale."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/local.py", """
            OLD_NAME = 1


            def use():
                return OLD_NAME
        """)
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/local.py", """
            NEW_NAME = 1


            def use():
                # OLD_NAME was renamed here
                return NEW_NAME
        """)
        self.head = commit(self.repo, "rename inside one file")

    def test_in_file_hit_is_marked_and_not_counted_external(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        symbol = data["removed_symbols"][0]
        self.assertEqual(symbol["name"], "OLD_NAME")
        self.assertEqual(symbol["external_reference_count"], 0)
        self.assertTrue(all(hit["in_changed_file"] for hit in symbol["hits"]))
        self.assertIn("likely the rename itself", pc.build_report(data, 10))


class ValueRemovedFromTuple(RepoCase):
    """The PR #134 shape: no symbol changes, so only step 4 catches it."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/session_pool.py", """
            CREW_SESSION_ROLES = (
                "implementer",
                "tester",
                "reviewer",
                "contract_locality_auditor",
            )


            def role_count():
                return len(CREW_SESSION_ROLES)
        """)
        write(self.repo, "tests/test_session_pool.py", """
            from pkg.session_pool import role_count

            assert role_count() == 4, "expected four roles not idle"
        """)
        write(self.repo, ".github/workflows/ci.yml", """
            jobs:
              core:
                steps:
                  - run: python tests/test_session_pool.py
        """)
        self.base = commit(self.repo, "base")

        write(self.repo, "pkg/session_pool.py", """
            CREW_SESSION_ROLES = (
                "implementer",
                "tester",
                "reviewer",
            )


            def role_count():
                return len(CREW_SESSION_ROLES)
        """)
        self.head = commit(self.repo, "drop a role from the tuple value")

    def test_step_two_finds_no_removed_symbol(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertEqual(data["removed_symbols"], [])

    def test_step_four_still_selects_the_importing_test(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertEqual(self.selected_paths(data), ["tests/test_session_pool.py"])
        self.assertTrue(data["importing_tests"][0]["in_ci"])

    def test_report_says_the_clean_symbol_result_proves_nothing(self):
        report = pc.build_report(self.analyse("%s..%s" % (self.base, self.head)), 10)
        self.assertIn("This does NOT mean nothing broke", report)
        self.assertIn("VALUE of a constant", report)

    def test_run_catches_the_failure_the_grep_missed(self):
        data = self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        results = data["run_results"]
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0]["exit_code"], 0)
        self.assertIn("four roles not idle", results[0]["last_line"])


class ChangedModuleWithNoImportingTests(RepoCase):
    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/lonely.py", "VALUE = 1\n")
        write(self.repo, "tests/test_other.py", "print('unrelated')\n")
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/lonely.py", "VALUE = 2\n")
        self.head = commit(self.repo, "change the lonely module")

    def test_no_tests_are_selected(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertEqual(data["changed_modules"], ["pkg.lonely"])
        self.assertEqual(data["importing_tests"], [])
        self.assertEqual(data["commands"], [])

    def test_report_says_so_plainly(self):
        report = pc.build_report(self.analyse("%s..%s" % (self.base, self.head)), 10)
        self.assertIn("no tracked test file imports any changed module", report)
        self.assertIn("nothing selected", report)

    def test_run_with_no_selection_succeeds(self):
        data = self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        self.assertEqual(data["run_results"], [])


class NonPythonChange(RepoCase):
    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/thing.py", "VALUE = 1\n")
        write(self.repo, "Docs/readme.md", "before\n")
        write(self.repo, "Pipeline/run.ps1", "Write-Host 'before'\n")
        self.base = commit(self.repo, "base")
        write(self.repo, "Docs/readme.md", "after\n")
        write(self.repo, "Pipeline/run.ps1", "Write-Host 'after'\n")
        self.head = commit(self.repo, "docs and powershell only")

    def test_nothing_python_is_analysed(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertEqual(data["changed_python_files"], [])
        self.assertEqual(data["changed_modules"], [])
        self.assertEqual(data["removed_symbols"], [])
        self.assertEqual(data["importing_tests"], [])

    def test_non_python_files_are_still_counted_in_the_report(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertEqual(sorted(data["changed_other_files"]),
                         ["Docs/readme.md", "Pipeline/run.ps1"])
        self.assertIn("2 non-Python file(s) changed", pc.build_report(data, 10))


class RunReportsFailingTest(RepoCase):
    """--run must report one line per file with its exit code and last line."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/calc.py", "def total():\n    return 1\n")
        write(self.repo, "tests/test_good.py", """
            from pkg.calc import total

            assert isinstance(total(), int)
            print("good: ok")
        """)
        write(self.repo, "tests/test_bad.py", """
            from pkg.calc import total

            raise SystemExit("bad: deliberate failure")
        """)
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/calc.py", "def total():\n    return 2\n")
        self.head = commit(self.repo, "change the total")

    def test_both_tests_run_with_their_exit_codes(self):
        data = self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        results = {r["test"]: r for r in data["run_results"]}
        self.assertEqual(sorted(results), ["tests/test_bad.py", "tests/test_good.py"])
        self.assertNotEqual(results["tests/test_bad.py"]["exit_code"], 0)
        self.assertIn("deliberate failure", results["tests/test_bad.py"]["last_line"])

    def test_passing_test_reports_zero_and_its_last_line(self):
        data = self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        good = [r for r in data["run_results"] if r["test"] == "tests/test_good.py"][0]
        self.assertEqual(good["exit_code"], 0)
        self.assertEqual(good["last_line"], "good: ok")

    def test_main_exits_nonzero_when_a_selected_test_fails(self):
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            code = pc.main([str(self.repo), "%s..%s" % (self.base, self.head),
                            "--run", "--json"])
        self.assertEqual(code, 1)
        self.assertIn("run_results", captured.getvalue())


class ImportFormsAndMapping(unittest.TestCase):
    """Unit coverage for the parts the repository's own import style exercises."""

    def test_module_path_mapping(self):
        self.assertEqual(
            pc.module_path_for("Pipeline/ExecutionCrew/session_pool.py"),
            "Pipeline.ExecutionCrew.session_pool",
        )
        self.assertEqual(pc.module_path_for("Pipeline/__init__.py"), "Pipeline")
        self.assertIsNone(pc.module_path_for("Docs/notes.md"))
        self.assertIsNone(pc.module_path_for("some dir/mod.py"))

    def test_import_parsing_covers_the_repository_forms(self):
        module = "Pipeline.ExecutionCrew.session_pool"
        owner = "Pipeline.ExecutionCrew.tests.session_pool_smoke_test"

        def names(line):
            return pc.modules_named_by_import_line(line, owner)

        self.assertIn(module, names("import Pipeline.ExecutionCrew.session_pool"))
        self.assertIn(module, names("from Pipeline.ExecutionCrew.session_pool import ("))
        self.assertIn(
            module,
            names("        from Pipeline.ExecutionCrew.session_pool import A,B"),
        )
        # The parent-package form the repository also uses.
        self.assertIn(module, names("from Pipeline.ExecutionCrew import session_pool as sp"))
        self.assertIn(module, names("from Pipeline.ExecutionCrew import run_crew, session_pool"))
        self.assertNotIn(module, names("from Pipeline.ExecutionCrew.session_pool_extra import X"))
        self.assertNotIn(module, names("# session_pool is mentioned in prose"))
        self.assertNotIn(module, names("value = 'Pipeline.ExecutionCrew.session_pool'"))

    def test_relative_imports_resolve_against_the_importing_file(self):
        owner = "Pipeline.CodexJobs.tests.test_codex_jobs"
        self.assertIn(
            "Pipeline.CodexJobs.tests.fake_docker",
            pc.modules_named_by_import_line("from . import fake_docker", owner),
        )
        self.assertIn(
            "Pipeline.CodexJobs.jobs",
            pc.modules_named_by_import_line("from ..jobs import run", owner),
        )
        self.assertEqual(
            pc.modules_named_by_import_line("from . import x", None), set()
        )

    def test_import_aliases_and_multiple_targets(self):
        got = pc.modules_named_by_import_line("import a.b as ab, c.d", None)
        self.assertEqual(got, {"a.b", "c.d"})
        got = pc.modules_named_by_import_line("from a.b import c as d, e  # note", None)
        self.assertEqual(got, {"a.b", "a.b.c", "a.b.e"})

    def test_module_level_names_include_all_entries(self):
        names = pc.module_level_names(textwrap.dedent("""
            __all__ = ["exported", "also"]

            CONST = 1
            A, B = 2, 3


            class Thing:
                def method(self):
                    pass


            def func():
                inner = 1
                return inner
        """))
        self.assertIn("CONST", names)
        self.assertIn("A", names)
        self.assertIn("B", names)
        self.assertIn("Thing", names)
        self.assertIn("func", names)
        self.assertIn("exported", names)
        self.assertIn("also", names)
        self.assertNotIn("method", names)
        self.assertNotIn("inner", names)

    def test_is_test_path(self):
        self.assertTrue(pc.is_test_path("Pipeline/ExecutionCrew/tests/x_smoke_test.py"))
        self.assertTrue(pc.is_test_path("Pipeline/AssistantControl/test_scope.py"))
        self.assertFalse(pc.is_test_path("Pipeline/ExecutionCrew/session_pool.py"))
        self.assertFalse(pc.is_test_path("Docs/tests/notes.md"))

    def test_range_parsing(self):
        self.assertEqual(pc.parse_range("a..b"), ("a", "b"))
        self.assertEqual(pc.parse_range("a...b"), ("a", "b"))
        with self.assertRaises(pc.CheckError):
            pc.parse_range("nope")
        with self.assertRaises(pc.CheckError):
            pc.parse_range("a..")

    def test_no_window_flag_is_the_allowed_one(self):
        expected = 0x08000000 if sys.platform == "win32" else 0
        self.assertEqual(pc.CREATE_NO_WINDOW, expected)


class BadInput(unittest.TestCase):
    def test_missing_clone_reports_a_message(self):
        tmp = tempfile.mkdtemp(prefix="propcheck-nope-")
        with contextlib.redirect_stderr(io.StringIO()) as captured:
            code = pc.main([os.path.join(tmp, "absent"), "a..b"])
        self.assertEqual(code, 2)
        self.assertIn("propagation_check:", captured.getvalue())



# ---------------------------------------------------------------------------
# Regressions from the two independent reviews of 2026-09-18.
#
# Both a Fable review and a pipeline-reviewer commissioned separately by the
# Release Agent arrived at the same blocking defect from different directions:
# every step except the symbol diff read the clone's CHECKED-OUT WORKING TREE
# rather than <head>. Run from a clone sitting on main - the posture the
# runbook would put it in, just before a merge - it reported a confident
# false green.
# ---------------------------------------------------------------------------


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


class ChangedTestFileSelectsItself(RepoCase):
    """PR #134 round 4: a range that edits a test file selected nothing."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/view.py", "VALUE = 1\n")
        write(self.repo, "tests/view_smoke_test.py", """
            print("checking the view")
        """)
        write(self.repo, "index.html", "<p>one</p>\n")
        write(self.repo, ".github/workflows/ci.yml", """
            jobs:
              t:
                steps:
                  - run: python tests/view_smoke_test.py
        """)
        self.base = commit(self.repo, "base")

        # Exactly PR #134 round 4's shape: a non-Python file and a test file,
        # and no change to any module the test imports.
        write(self.repo, "index.html", "<p>two</p>\n")
        write(self.repo, "tests/view_smoke_test.py", """
            print("checking the view differently")
        """)
        self.head = commit(self.repo, "head")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)

    def test_the_changed_test_is_selected(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertIn("tests/view_smoke_test.py", self.selected_paths(data))

    def test_it_is_marked_as_run_by_ci(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        entry = next(t for t in data["importing_tests"]
                     if t["path"] == "tests/view_smoke_test.py")
        self.assertTrue(entry["in_ci"])

    def test_a_deleted_test_is_not_selected(self):
        """There is nothing left to run, so selecting it would only error."""
        (self.repo / "tests" / "view_smoke_test.py").unlink()
        head2 = commit(self.repo, "delete the test")
        run_git(self.repo, "checkout", "-q", "--detach", head2)
        data = self.analyse("%s..%s" % (self.base, head2))
        self.assertNotIn("tests/view_smoke_test.py", self.selected_paths(data))

    def test_it_is_not_selected_twice(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        paths = self.selected_paths(data)
        self.assertEqual(len(paths), len(set(paths)))


class RunSafety(RepoCase):
    """--run had no timeout, and read its verdict out of the last line."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        self.base = commit(self.repo, "base")

    def test_a_hung_test_times_out_instead_of_blocking_forever(self):
        write(self.repo, "tests/test_hang.py", """
            import time
            time.sleep(45)
        """)
        commit(self.repo, "a test that hangs")
        run_git(self.repo, "checkout", "-q", "--detach", "HEAD")
        results = pc.run_tests(
            str(self.repo), [pc.SelectedTest(path="tests/test_hang.py")], timeout=2.0
        )
        self.assertEqual("timeout", results[0]["status"])
        self.assertIsNone(results[0]["exit_code"])

    def test_a_failing_test_that_prints_PASS_last_still_reads_as_failed(self):
        """`production_end_to_end_smoke_test.py` did exactly this: a per-case
        "PASS ..." as its final line while exiting 1. The verdict comes from
        the exit code and nothing else."""
        write(self.repo, "tests/test_liar.py", """
            import sys
            print("PASS test_everything_is_fine")
            sys.exit(1)
        """)
        commit(self.repo, "a test that lies in its last line")
        results = pc.run_tests(
            str(self.repo), [pc.SelectedTest(path="tests/test_liar.py")]
        )
        self.assertEqual("fail", results[0]["status"])
        self.assertEqual(1, results[0]["exit_code"])
        self.assertIn("PASS test_everything_is_fine", results[0]["last_line"])

    def test_the_scratch_directory_is_removed(self):
        write(self.repo, "tests/test_ok.py", "print('fine')\n")
        commit(self.repo, "ok")
        before = set(Path(tempfile.gettempdir()).glob("propcheck-*"))
        pc.run_tests(str(self.repo), [pc.SelectedTest(path="tests/test_ok.py")])
        after = set(Path(tempfile.gettempdir()).glob("propcheck-*"))
        self.assertEqual(before, after, "run_tests leaked a scratch directory")

    def test_the_run_carries_its_no_baseline_caveat(self):
        write(self.repo, "tests/test_ok.py", "print('fine')\n")
        head = commit(self.repo, "ok")
        run_git(self.repo, "checkout", "-q", "--detach", head)
        data = self.analyse("%s..%s" % (self.base, head), do_run=True)
        self.assertIsNone(data["run_baseline"])
        self.assertIn("already fail", data["run_caveat"])



# ---------------------------------------------------------------------------
# Round 2 of the review. Each of these is a defect the round-1 fixes either
# introduced or left, and none of them was covered by the 44 tests that were
# green when the round-2 review started.
# ---------------------------------------------------------------------------


class TimeoutReachesTheReport(RepoCase):
    """A timed-out test crashed the default text report with a TypeError.

    `"exit %-3d" % None`. The whole report was lost, after --run had already
    spent up to the timeout on every test.
    """

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/api.py", "VALUE = 2\n")
        write(self.repo, "tests/test_hang.py", """
            import time
            from pkg.api import VALUE
            time.sleep(45)
        """)
        self.head = commit(self.repo, "head")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)

    def _timed_out_data(self):
        return pc.analyse(
            str(self.repo), "%s..%s" % (self.base, self.head), 10, True,
            run_timeout=2.0,
        )

    def test_the_text_report_survives_a_timeout(self):
        data = self._timed_out_data()
        self.assertTrue(any(r["status"] == "timeout" for r in data["run_results"]))
        report = pc.build_report(data, 10)          # used to raise TypeError
        self.assertIn("TIMEOUT", report)
        self.assertIn("tests/test_hang.py", report)

    def test_a_timeout_counts_as_a_failure_in_the_report_header(self):
        data = self._timed_out_data()
        report = pc.build_report(data, 10)
        self.assertNotIn("0 failed", report)

    def test_main_exits_nonzero_on_a_timeout(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = pc.main([str(self.repo), "%s..%s" % (self.base, self.head),
                            "--run", "--run-timeout", "2"])
        self.assertEqual(1, code, out.getvalue()[-400:])


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


class TheTextReportCarriesTheWarnings(RepoCase):
    """The warnings existed only in the JSON, so a reader of the text report
    could mistake the escape hatch's output for the range's."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        write(self.repo, "tests/test_api.py", "print('ok')\n")
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/api.py", "VALUE = 2\n")
        self.head = commit(self.repo, "head")
        write(self.repo, "unrelated.py", "X = 1\n")
        commit(self.repo, "parked elsewhere")

    def test_the_report_warns_that_the_clone_is_not_at_the_head(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        report = pc.build_report(data, 10)
        self.assertIn("not at the head", report)
        self.assertIn("checkout --detach", report)

    def test_the_report_says_run_results_are_not_the_ranges(self):
        data = pc.analyse(
            str(self.repo), "%s..%s" % (self.base, self.head), 10, True,
            allow_tree_mismatch=True,
        )
        report = pc.build_report(data, 10)
        self.assertIn("NOT THIS RANGE", report)

    def test_the_report_carries_the_no_baseline_caveat(self):
        run_git(self.repo, "checkout", "-q", "--detach", self.head)
        data = self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        report = pc.build_report(data, 10)
        self.assertIn("NO BASELINE", report)

    def test_a_clean_run_at_the_head_has_no_tree_warning(self):
        run_git(self.repo, "checkout", "-q", "--detach", self.head)
        data = self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        report = pc.build_report(data, 10)
        self.assertNotIn("NOT THIS RANGE", report)
        self.assertNotIn("not at the head", report)


class TimeoutKillsTheWholeTree(RepoCase):
    """The timeout killed only the direct child, and then blocked on a pipe a
    surviving grandchild still held - the hang it exists to stop."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        self.base = commit(self.repo, "base")

    def test_a_test_that_spawns_a_child_still_times_out_promptly(self):
        write(self.repo, "tests/test_spawner.py", """
            import subprocess
            import sys
            import time
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(45)"])
            print("spawned", child.pid, flush=True)
            time.sleep(45)
        """)
        commit(self.repo, "a test that starts a grandchild")
        started = time.time()
        results = pc.run_tests(
            str(self.repo), [pc.SelectedTest(path="tests/test_spawner.py")], timeout=3.0
        )
        elapsed = time.time() - started
        self.assertEqual("timeout", results[0]["status"])
        # It used to come back only when the grandchild exited, at ~60s here.
        self.assertLess(elapsed, 40, "the timeout waited for the grandchild")

    def test_the_output_written_before_the_hang_is_still_captured(self):
        write(self.repo, "tests/test_noisy_hang.py", """
            import time
            print("MARKER before the hang", flush=True)
            time.sleep(45)
        """)
        commit(self.repo, "a noisy hang")
        results = pc.run_tests(
            str(self.repo), [pc.SelectedTest(path="tests/test_noisy_hang.py")], timeout=3.0
        )
        self.assertEqual("timeout", results[0]["status"])
        self.assertIn("MARKER before the hang", results[0]["last_line"])



# ---------------------------------------------------------------------------
# Round 3 of the review. The first of these was filed by me as "what the tool
# does not catch"; the reviewer proved it is a false green, which is the
# category this tool exists to prevent.
# ---------------------------------------------------------------------------


class RenamedModuleIsNotInvisible(RepoCase):
    """git scored a rename+edit as R090 and reported only the new path, so the
    old module's names looked untouched and nothing was selected."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/old_name.py", """
            ALPHA = 1
            BETA = 2


            def helper(value):
                return value


            class Thing:
                pass
        """)
        write(self.repo, "tests/test_uses_old.py", """
            from pkg.old_name import helper

            print(helper("ok"))
        """)
        write(self.repo, ".github/workflows/ci.yml", """
            jobs:
              t:
                steps:
                  - run: python tests/test_uses_old.py
        """)
        self.base = commit(self.repo, "base")

        # A rename plus a small edit, which git scores as a similar rename.
        run_git(self.repo, "mv", "pkg/old_name.py", "pkg/new_name.py")
        write(self.repo, "pkg/new_name.py", """
            ALPHA = 1
            BETA = 2
            GAMMA = 3


            def helper(value):
                return value


            class Thing:
                pass
        """)
        self.head = commit(self.repo, "rename the module")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)

    def test_git_really_scores_this_as_a_rename(self):
        """If git stopped detecting it, this fixture would pass for free."""
        proc = subprocess.run(
            ["git", "-C", str(self.repo), "diff", "--name-status", "-M",
             "%s..%s" % (self.base, self.head)],
            stdout=subprocess.PIPE, creationflags=pc.CREATE_NO_WINDOW,
        )
        self.assertIn("R", proc.stdout.decode().split("\t")[0])

    def test_the_old_module_counts_as_changed(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertIn("pkg/old_name.py", [e["path"] for e in data["changed_python_files"]])

    def test_its_names_are_reported_removed(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertIn("helper", self.symbol_names(data))
        self.assertIn("Thing", self.symbol_names(data))

    def test_the_importing_test_is_selected(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertIn("tests/test_uses_old.py", self.selected_paths(data))

    def test_run_fails_instead_of_reporting_a_confident_green(self):
        data = self.analyse("%s..%s" % (self.base, self.head), do_run=True)
        self.assertTrue(any(r["status"] == "fail" for r in data["run_results"]))
        with contextlib.redirect_stdout(io.StringIO()):
            code = pc.main([str(self.repo), "%s..%s" % (self.base, self.head), "--run"])
        self.assertEqual(1, code)

    def test_a_plain_delete_still_works(self):
        """The delete path was always right; it must stay right."""
        (self.repo / "pkg" / "new_name.py").unlink()
        head2 = commit(self.repo, "delete it outright")
        run_git(self.repo, "checkout", "-q", "--detach", head2)
        data = self.analyse("%s..%s" % (self.base, head2))
        self.assertIn("helper", self.symbol_names(data))


class UntrackedFilesAreReported(RepoCase):
    """--untracked-files=no was blind to a forgotten `git add`."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/api.py", """
            from pkg.helper import HELP
            VALUE = HELP
        """)
        self.head = commit(self.repo, "head imports a helper")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)
        # On disk, never committed: a fresh clone of head would not have it.
        write(self.repo, "pkg/helper.py", "HELP = 2\n")

    def test_the_untracked_python_file_is_listed(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertIn("pkg/helper.py", data["untracked_python_files"])

    def test_the_report_warns_about_it(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        report = pc.build_report(data, 10)
        self.assertIn("UNTRACKED", report)
        self.assertIn("pkg/helper.py", report)

    def test_a_clean_checkout_lists_none(self):
        (self.repo / "pkg" / "helper.py").unlink()
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertEqual([], data["untracked_python_files"])
        self.assertNotIn("UNTRACKED", pc.build_report(data, 10))


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


class TheCloneIsNotWrittenTo(RepoCase):
    """The always-on git status refreshed .git/index, in a tool whose own CLI
    help calls the clone read-only."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/api.py", "VALUE = 2\n")
        self.head = commit(self.repo, "head")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)

    def _make_the_stat_cache_stale(self) -> None:
        """Rewrite a tracked file with identical bytes.

        The stat cache has to be STALE for the index test to mean anything:
        straight after a checkout git has nothing to refresh, so even a plain
        `git status` leaves the index alone and the test passes either way.
        Changing only the mtime is exactly what makes git rewrite it.

        Measured, not assumed: with a 0.02 s gap git does not notice and does
        not rewrite the index, so the test passed even with the guard removed.
        Git's stat cache has one-second granularity, so the sleep has to cross
        a whole second for the entry to look stale.
        """
        target = self.repo / "pkg" / "api.py"
        time.sleep(1.1)
        target.write_bytes(target.read_bytes())

    def test_an_analysis_run_leaves_the_index_byte_identical(self):
        import hashlib

        self._make_the_stat_cache_stale()
        index = self.repo / ".git" / "index"
        before = hashlib.sha256(index.read_bytes()).hexdigest()
        self.analyse("%s..%s" % (self.base, self.head))
        after = hashlib.sha256(index.read_bytes()).hexdigest()
        self.assertEqual(before, after, "the analysis wrote to .git/index")

    def test_the_stale_cache_trick_does_not_change_the_content(self):
        """Guards the trick: if it dirtied the tree, the test above would be
        measuring something else entirely."""
        self._make_the_stat_cache_stale()
        self.assertFalse(pc.worktree_is_dirty(str(self.repo)))


class TheGrandchildIsActuallyDead(RepoCase):
    """The round-2 mutation for this was caught only by a tearDown error: no
    test asserted the grandchild had been killed, just that we stopped waiting."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        self.base = commit(self.repo, "base")

    def test_the_spawned_child_is_killed_by_the_timeout(self):
        marker = Path(self.tmp.name) / "grandchild.pid"
        write(self.repo, "tests/test_spawner.py", """
            import subprocess
            import sys
            import time
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(45)"])
            open(r"%s", "w").write(str(child.pid))
            time.sleep(45)
        """ % marker)
        commit(self.repo, "spawner")
        results = pc.run_tests(
            str(self.repo), [pc.SelectedTest(path="tests/test_spawner.py")], timeout=3.0
        )
        self.assertEqual("timeout", results[0]["status"])
        pid = int(marker.read_text().strip())
        deadline = time.time() + 15
        while time.time() < deadline and _pid_running(pid):
            time.sleep(0.2)
        self.assertFalse(_pid_running(pid), "the grandchild (pid %d) outlived the kill" % pid)


def _pid_running(pid: int) -> bool:
    proc = subprocess.run(
        ["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=pc.CREATE_NO_WINDOW,
    )
    return str(pid) in proc.stdout.decode("utf-8", "replace")



# ---------------------------------------------------------------------------
# Round 4. Every one of these is a LIVE test id that the first version of
# stale_workflow_test_ids reported as missing - and a false stale id exits 1,
# so it is as harmful as a miss. The guard test that should have caught them
# analysed an empty range and proved nothing.
# ---------------------------------------------------------------------------


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


class UntrackedPackageIsSeen(RepoCase):
    """--untracked-files=normal collapsed a new directory to `?? pkg/helpers/`,
    which does not end in .py - and a new package is the commonest forgotten
    `git add`."""

    def setUp(self) -> None:
        super().setUp()
        write(self.repo, "pkg/__init__.py", "")
        write(self.repo, "pkg/api.py", "VALUE = 1\n")
        self.base = commit(self.repo, "base")
        write(self.repo, "pkg/api.py", """
            from pkg.helpers.util import HELP
            VALUE = HELP
        """)
        self.head = commit(self.repo, "head imports a new package")
        run_git(self.repo, "checkout", "-q", "--detach", self.head)
        write(self.repo, "pkg/helpers/__init__.py", "")
        write(self.repo, "pkg/helpers/util.py", "HELP = 2\n")

    def test_the_whole_untracked_package_is_listed(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        listed = data["untracked_python_files"]
        self.assertIn("pkg/helpers/util.py", listed)
        self.assertIn("pkg/helpers/__init__.py", listed)

    def test_the_report_warns(self):
        data = self.analyse("%s..%s" % (self.base, self.head))
        self.assertIn("UNTRACKED", pc.build_report(data, 10))



# ---------------------------------------------------------------------------
# --baseline. Every review round said the same thing: without running the same
# tests at <base>, a red test is not evidence of a regression. A real run had
# 10 failures of which 2 were pre-existing, and the tool could state the
# caveat but not resolve it.
# ---------------------------------------------------------------------------


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
