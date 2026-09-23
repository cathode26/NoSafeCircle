#!/usr/bin/env python
"""Can this tell a stale deployment from an edited one? That is the whole point.

Run:
    python -B test_deploy_tools.py

Nothing here touches the real deployment at C:/NSC/tools or the real canonical
checkout. Every case builds a throwaway git repo and a throwaway workspace under
the OS temp directory, so a failure cannot damage the thing the tool exists to
protect.

The three states the tool must separate, and why a test for each is not
decoration:

    stale     the deployment matches what was recorded, and the tracked file has
              moved on. Routine: somebody merged.
    modified  the deployment does NOT match what was recorded. Somebody edited
              the copy that is actually running, and no git history covers it.
    unrecorded a deployment with no record at all, where a matching file could be
              either of the above and the tool must say so rather than guess.

Before this tool, all three looked identical from outside - which is how seven
GER tools went stale on 2026-09-22 with nothing reporting it.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOST = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HOST))
import deploy_tools as dt  # noqa: E402

MANIFEST = {
    "schema_version": 1,
    "families": {
        "ger": {"include": ["*.py"], "exclude": ["tests/**"]},
    },
    "root_files": ["nsc_paths.py"],
}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

        self.repo = self.tmp / "repo"
        self.host = self.repo / "Tools" / "Host"
        (self.host / "ger" / "tests").mkdir(parents=True)
        self.write("nsc_paths.py", "WORKSPACE = 1\n")
        self.write("ger/ger_round.py", "VERSION = 1\n")
        self.write("ger/ger_node.py", "VERSION = 1\n")
        self.write("ger/tests/test_ger_round.py", "# never deploys\n")
        (self.host / dt.MANIFEST_NAME).write_text(
            json.dumps(MANIFEST), encoding="utf-8")

        self.git("init", "-q")
        self.git("config", "user.name", "fixture")
        self.git("config", "user.email", "fixture@nosafecircle.invalid")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "first")

        self.workspace = self.tmp / "workspace"
        self.tools = self.workspace / "tools"

    def git(self, *args: str) -> str:
        done = subprocess.run(["git", "-C", str(self.repo), *args],
                              capture_output=True, text=True)
        if done.returncode != 0:
            raise AssertionError(f"git {' '.join(args)}: {done.stderr}")
        return done.stdout

    def write(self, relative: str, text: str) -> None:
        """LF, explicitly, because that is what git stores.

        `Path.write_text` uses text mode and translates to CRLF on Windows, so
        the first version of this fixture wrote CRLF "source" files - which are
        not what the tool compares against, and which made the CRLF test double
        its own line endings into genuinely different content.
        """
        path = self.host / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        io.open(path, "w", encoding="utf-8", newline="\n").write(text)

    def run_tool(self, *extra: str) -> int:
        return dt.main(["--repo", str(self.repo),
                        "--workspace", str(self.workspace), *extra])

    def deploy(self, *extra: str) -> int:
        return self.run_tool("--apply", *extra)

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").strip()

    def record(self) -> dict:
        return json.loads((self.tools / dt.RECORD_NAME).read_text(encoding="utf-8"))

    def states(self) -> dict[str, str]:
        manifest = dt.load_manifest(self.host)
        found, _record = dt.compare(
            self.host, self.tools, manifest,
            tracked=dt.tracked_paths(self.repo))
        return found


class WhatDeploys(Base):
    def test_only_what_the_manifest_declares(self):
        self.assertEqual(self.deploy(), 0)
        deployed = sorted(p.relative_to(self.tools).as_posix()
                          for p in self.tools.rglob("*.py"))
        self.assertEqual(deployed, ["ger/ger_node.py", "ger/ger_round.py",
                                    "nsc_paths.py"])

    def test_an_excluded_subtree_does_not_deploy(self):
        # ger/tests exists in the source and is excluded. A deployment that
        # carried test suites would also carry their fixtures' assumptions.
        self.assertEqual(self.deploy(), 0)
        self.assertFalse((self.tools / "ger" / "tests").exists())

    def test_the_record_names_the_commit_and_every_file(self):
        self.assertEqual(self.deploy(), 0)
        record = self.record()
        self.assertEqual(record["deployed_from"], self.head())
        self.assertEqual(sorted(record["files"]),
                         ["ger/ger_node.py", "ger/ger_round.py", "nsc_paths.py"])
        self.assertEqual(record["schema_version"], dt.SCHEMA_VERSION)

    def test_a_fresh_deployment_reports_nothing(self):
        self.assertEqual(self.deploy(), 0)
        self.assertEqual(self.run_tool("--check", "--quiet"), 0)
        self.assertEqual(set(self.states().values()), {dt.CURRENT})


class TheThreeStates(Base):
    def test_a_merge_makes_the_deployment_stale(self):
        self.assertEqual(self.deploy(), 0)
        self.write("ger/ger_round.py", "VERSION = 2\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "second")

        states = self.states()
        self.assertEqual(states["ger/ger_round.py"], dt.STALE)
        self.assertEqual(states["ger/ger_node.py"], dt.CURRENT)
        self.assertEqual(self.run_tool("--check", "--quiet"), 1)

    def test_an_edited_deployment_is_MODIFIED_not_stale(self):
        """The state nothing could see before a per-file hash was recorded.

        A commit id alone cannot tell these apart: in both cases the deployed
        bytes differ from the tracked bytes. Only the recorded hash says whether
        the deployment still holds what was put there.
        """
        self.assertEqual(self.deploy(), 0)
        (self.tools / "ger" / "ger_round.py").write_text(
            "VERSION = 1\nHAND_EDITED = True\n", encoding="utf-8")

        states = self.states()
        self.assertEqual(states["ger/ger_round.py"], dt.MODIFIED)
        self.assertNotEqual(states["ger/ger_round.py"], dt.STALE)
        self.assertEqual(self.run_tool("--check", "--quiet"), 1)

    def test_stale_and_modified_are_distinguished_on_the_same_file(self):
        # Both conditions at once: tracked moved AND the copy was edited. The
        # answer must be `modified`, the more serious of the two, because a
        # redeploy would silently discard someone's edit.
        self.assertEqual(self.deploy(), 0)
        self.write("ger/ger_round.py", "VERSION = 2\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "second")
        (self.tools / "ger" / "ger_round.py").write_text(
            "VERSION = 99\n", encoding="utf-8")
        self.assertEqual(self.states()["ger/ger_round.py"], dt.MODIFIED)

    def test_a_deployment_with_no_record_cannot_be_called_current(self):
        self.assertEqual(self.deploy(), 0)
        (self.tools / dt.RECORD_NAME).unlink()
        self.write("ger/ger_round.py", "VERSION = 2\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "second")

        states = self.states()
        # Differs from tracked and there is no record: cannot tell stale from
        # edited, so it is reported as unrecorded rather than guessed at.
        self.assertEqual(states["ger/ger_round.py"], dt.UNRECORDED)
        self.assertEqual(self.run_tool("--check", "--quiet"), 1)

    def test_a_declared_file_that_never_deployed_is_absent(self):
        self.assertEqual(self.deploy(), 0)
        (self.tools / "nsc_paths.py").unlink()
        self.assertEqual(self.states()["nsc_paths.py"], dt.ABSENT)

    def test_absent_alone_does_not_fail_unless_asked(self):
        # True of the whole closure family today. If absence failed by default,
        # the check would be red until the cutover and nobody would run it.
        self.assertEqual(self.deploy(), 0)
        (self.tools / "nsc_paths.py").unlink()
        self.assertEqual(self.run_tool("--check", "--quiet"), 0)
        self.assertEqual(self.run_tool("--check", "--quiet", "--require-complete"), 1)

    def _deploy_a_copy_of_the_excluded_test(self, text: str) -> None:
        """Put a copy of an EXCLUDED host file into the deployment."""
        self.assertEqual(self.deploy(), 0)
        landed = self.tools / "ger" / "tests" / "test_ger_round.py"
        landed.parent.mkdir(parents=True, exist_ok=True)
        io.open(landed, "w", encoding="utf-8", newline="\n").write(text)

    def test_an_undeclared_file_that_differs_from_the_host_tree_is_shadowed(self):
        """The real defect: excluded from the manifest, so no --apply repairs it.

        Measured live 2026-09-22: three jobs/tests files sat in the deployment
        with older content, one of them seven test cases short, filed under
        EXTRA beside twenty-six .bak leftovers.
        """
        self._deploy_a_copy_of_the_excluded_test("# an older copy\n")
        self.assertEqual(self.states()["ger/tests/test_ger_round.py"], dt.SHADOWED)
        self.assertEqual(self.run_tool("--check", "--quiet"), 1)

    def test_an_undeclared_file_identical_to_the_host_tree_stays_extra(self):
        """The control. Undeclared but not misleading: nothing is hidden by it.

        A change that called every undeclared file SHADOWED would pass the test
        above and erase the distinction it exists to draw.
        """
        self._deploy_a_copy_of_the_excluded_test("# never deploys\n")
        self.assertEqual(self.states()["ger/tests/test_ger_round.py"], dt.EXTRA)

    def test_shadowed_is_reported_ahead_of_modified(self):
        """Ordering carries the meaning: a modified declared file is one
        --apply from correct; a shadowed one is reachable by no command."""
        self.assertLess(dt.SEVERITY.index(dt.SHADOWED), dt.SEVERITY.index(dt.MODIFIED))

    def test_an_undeclared_deployed_file_is_extra(self):
        self.assertEqual(self.deploy(), 0)
        (self.tools / "ger" / "hand_placed.py").write_text("x = 1\n", encoding="utf-8")
        self.assertEqual(self.states()["ger/hand_placed.py"], dt.EXTRA)
        self.assertEqual(self.run_tool("--check", "--quiet"), 1)


class LineEndings(Base):
    def test_a_crlf_deployment_of_an_lf_file_is_current(self):
        """The deployment is CRLF in the working tree; the blobs are LF.

        Without normalisation every single file reports as different and the
        tool is noise. This is why the cutover document says "ignoring line
        endings" for its own comparison.
        """
        self.assertEqual(self.deploy(), 0)
        target = self.tools / "ger" / "ger_round.py"
        raw = target.read_bytes()
        self.assertNotIn(b"\r", raw, "the fixture must deploy LF for this to mean anything")
        target.write_bytes(raw.replace(b"\n", b"\r\n"))
        self.assertEqual(self.states()["ger/ger_round.py"], dt.CURRENT)

    def test_a_lone_cr_inside_content_is_still_a_difference(self):
        # `.replace(b"\r", b"")` would make these two files hash the same. A CR
        # inside a string literal is content, not a line ending.
        self.assertNotEqual(dt.digest(b'x = "a\rb"\n'), dt.digest(b'x = "ab"\n'))

    def test_normalise_handles_all_three_conventions(self):
        for raw in (b"a\r\nb\n", b"a\nb\n", b"a\rb\n"):
            with self.subTest(raw=raw):
                self.assertEqual(dt.normalise(raw), b"a\nb\n")


class RefusalsAndScope(Base):
    def test_it_refuses_to_deploy_from_a_dirty_checkout(self):
        """A recorded commit id that does not describe the copied bytes is worse
        than no record: it invites exactly the trust the record should earn."""
        self.write("ger/ger_round.py", "VERSION = 2\n")   # uncommitted
        self.assertEqual(self.deploy(), 2)
        self.assertFalse(self.tools.exists() and (self.tools / dt.RECORD_NAME).is_file())

    def test_a_dirty_file_outside_the_selection_does_not_block(self):
        # Only the files being deployed matter. A dirty README must not stop a
        # deployment of ger/.
        (self.repo / "README.md").write_text("edited\n", encoding="utf-8")
        self.assertEqual(self.deploy(), 0)

    def test_a_dirty_excluded_file_does_not_block(self):
        self.write("ger/tests/test_ger_round.py", "# edited, never deploys\n")
        self.assertEqual(self.deploy(), 0)

    def test_one_family_does_not_erase_another_familys_hashes(self):
        self.assertEqual(self.deploy(), 0)
        before = set(self.record()["files"])
        self.write("ger/ger_round.py", "VERSION = 2\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "second")
        self.assertEqual(self.deploy("--family", "ger"), 0)
        after = self.record()
        self.assertEqual(set(after["files"]), before)
        self.assertEqual(after["partial_family"], "ger")

    def test_check_refuses_when_there_is_no_deployment(self):
        self.assertEqual(self.run_tool("--check"), 2)

    def test_a_manifest_with_the_wrong_schema_is_refused(self):
        (self.host / dt.MANIFEST_NAME).write_text(
            json.dumps({"schema_version": 99}), encoding="utf-8")
        self.assertEqual(self.run_tool("--check"), 2)

    def test_a_missing_manifest_is_refused_not_treated_as_empty(self):
        (self.host / dt.MANIFEST_NAME).unlink()
        self.assertEqual(self.run_tool("--check"), 2)
        self.assertEqual(self.deploy(), 2)

    def test_a_manifest_naming_a_family_that_does_not_exist_is_not_an_error(self):
        # The manifest must be able to declare the supported set before every
        # part of it exists; that is how the closure family is declared today.
        (self.host / dt.MANIFEST_NAME).write_text(json.dumps({
            "schema_version": 1,
            "families": {"ger": {"include": ["*.py"], "exclude": []},
                         "not-yet": {"include": ["*.py"], "exclude": []}},
            "root_files": ["nsc_paths.py", "never_written.py"],
        }), encoding="utf-8")
        self.assertEqual(self.deploy(), 0)
        self.assertEqual(sorted(self.record()["files"]),
                         ["ger/ger_node.py", "ger/ger_round.py", "nsc_paths.py"])


class TheRealDeployment(unittest.TestCase):
    """Read-only assertions about the manifest that ships, not the fixture's."""

    def setUp(self):
        self.manifest = dt.load_manifest(HOST)

    def test_the_shipped_manifest_parses_and_matches_this_schema(self):
        self.assertEqual(self.manifest["schema_version"], dt.SCHEMA_VERSION)

    def test_it_declares_the_seven_families_that_are_deployed_today(self):
        for family in ("art", "astra", "cleanup", "ger", "jobs", "session", "viewer"):
            self.assertIn(family, self.manifest["families"])

    def test_it_declares_the_resolver_the_closure_launcher_requires(self):
        # run_closure_review.sh exits 2 without nsc_paths.py beside its helpers,
        # and make_closure_prompt.py imports it. Deploying codex-jobs without it
        # produces a launcher that refuses every run.
        self.assertIn("nsc_paths.py", self.manifest["root_files"])
        self.assertIn("review_result.py", self.manifest["root_files"])

    def test_it_never_declares_the_host_test_suites(self):
        self.assertNotIn("tests", self.manifest["families"])
        self.assertIn("tests", self.manifest["never_deploy"])

    def test_the_ger_family_excludes_its_tests(self):
        self.assertIn("tests/**", self.manifest["families"]["ger"]["exclude"])

    def test_every_declared_root_file_exists_in_the_tree(self):
        for name in self.manifest["root_files"]:
            self.assertTrue((HOST / name).is_file(), f"{name} is declared and absent")


class SelectionComesFromTheTrackedTree(Base):
    """H1: it globbed the FILESYSTEM while its docstring claimed the tree.

    The dirty check uses ordinary `git status`, which omits IGNORED files, so a
    gitignored local .py inside a declared family was copied into the
    deployment AND recorded in DEPLOYED.json as deployed from a HEAD containing
    no such file. False provenance, and it ships a local helper by accident.
    """

    def ignored_intruder(self) -> str:
        """An ignored, untracked .py inside a declared family."""
        self.write("ger/scratch_helper.py", "print('local only')\n")
        self.write(".gitignore", "scratch_helper.py\n")
        self.git("add", "Tools/Host/.gitignore")
        self.git("commit", "-m", "ignore a local helper", "--no-gpg-sign")
        return "ger/scratch_helper.py"

    def test_an_ignored_local_file_is_never_selected(self):
        intruder = self.ignored_intruder()
        manifest = dt.load_manifest(self.host)
        chosen = dt.selected(self.host, manifest,
                             tracked=dt.tracked_paths(self.repo))
        self.assertNotIn(intruder, chosen)
        self.assertEqual(
            "", self.git("status", "--porcelain").strip(),
            "the intruder must be invisible to the dirty check, which is "
            "exactly what made it shippable")

    def test_an_ignored_local_file_is_never_deployed_or_recorded(self):
        intruder = self.ignored_intruder()
        self.assertEqual(0, self.deploy())
        self.assertFalse((self.tools / intruder).exists(),
                         "an ignored local file reached the deployment")
        self.assertNotIn(intruder, self.record()["files"],
                         "DEPLOYED.json recorded a file its HEAD does not have")

    def test_every_recorded_file_exists_in_the_recorded_commit(self):
        """The provenance claim itself, checked against git rather than trusted."""
        self.ignored_intruder()
        self.assertEqual(0, self.deploy())
        record = self.record()
        listing = self.git("ls-tree", "-r", "--name-only",
                           record["deployed_from"], "--", "Tools/Host")
        prefix = "Tools/Host/"
        in_commit = {line[len(prefix):] for line in listing.splitlines()
                     if line.startswith(prefix)}
        missing = sorted(set(record["files"]) - in_commit)
        self.assertEqual(
            [], missing,
            "DEPLOYED.json names files absent from the commit it cites")


class RequireCompleteCannotPassOnNothing(Base):
    """H2: `any()` over an empty inventory is False, so it returned 0."""

    def test_a_misspelled_family_is_refused_rather_than_passing(self):
        self.assertEqual(0, self.deploy())
        self.assertEqual(
            2, self.run_tool("--check", "--require-complete", "--family", "jobz"),
            "a typo must not report a complete deployment")

    def test_a_misspelled_family_is_refused_without_require_complete_too(self):
        """This is what the family-name check earns on its own.

        With --require-complete, the empty-inventory guard below it would catch
        the typo anyway, so the two overlap and a test using that flag cannot
        tell which one fired. Plain --check has no such backstop: before the
        family check, `--check --family jobz` selected nothing, `any()` over
        nothing was False, and it exited 0.
        """
        self.assertEqual(0, self.deploy())
        self.assertEqual(
            2, self.run_tool("--check", "--family", "jobz"),
            "a typo must not report a clean deployment either")

    def test_a_real_family_still_works(self):
        """The refusal must not swallow the ordinary case."""
        self.assertEqual(0, self.deploy())
        self.assertIn(self.run_tool("--check", "--family", "ger"), (0, 1))

    def test_a_declared_family_that_matches_nothing_is_also_refused(self):
        """The family-name check does not cover this one.

        A family can be spelled correctly, be declared in the manifest, and
        still select zero files because its patterns match nothing tracked.
        "Complete" over an empty inventory is not a pass either way, and
        without this the second guard has no test and is a claim.
        """
        self.assertEqual(0, self.deploy())
        (self.host / dt.MANIFEST_NAME).write_text(json.dumps({
            "schema_version": 1,
            "families": {
                "ger": {"include": ["*.py"], "exclude": ["tests/**"]},
                "empty": {"include": ["*.nothing"], "exclude": []},
            },
            "root_files": ["nsc_paths.py"],
        }), encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "declare a family that matches nothing")
        self.assertEqual(
            2, self.run_tool("--check", "--require-complete", "--family", "empty"),
            "an empty inventory cannot be complete")


if __name__ == "__main__":
    unittest.main(verbosity=2)
