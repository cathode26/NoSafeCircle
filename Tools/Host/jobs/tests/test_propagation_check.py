"""What propagation_check DETECTS: removed symbols, renames, import forms,
and which tests it therefore selects.\n
Split out of the original 1664-line suite, which took 112 seconds - 45% of
the whole host run, and a floor that suite-level concurrency cannot get under
because one file is one process. Its siblings are
test_propagation_check_run.py (running the selected tests safely) and
test_propagation_check_state.py (what the repository looks like going in).
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

if __name__ == "__main__":
    unittest.main(verbosity=2)
