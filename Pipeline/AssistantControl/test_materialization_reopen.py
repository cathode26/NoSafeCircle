"""Real-Git fixture checks for reopen-materialization; no Unity, no provider.

The failed record is produced by RUNNING materialize_candidate with a failing
validation runner, never by hand-writing a record. A test that authors the
state it then accepts proves only that two pieces of my own writing agree.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.candidate_validation_retry import (
    validation_failure_sha256,
)
from Pipeline.AssistantControl.materialization_reopen import (
    MaterializationReopenError,
    reopen_materialization,
)
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.AssistantControl.unity_materialization import (
    MaterializationError,
    materialize_candidate,
)
from Pipeline.TaskReviewAgent.authoritative_candidate_validation import (
    AuthoritativeCandidateValidationError,
)
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity
from Pipeline.TaskReviewAgent.local_candidate_commit import LocalCandidateCommitReceipt


BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/ChapelOfAshSceneBuilder.cs"
TESTS = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/Rooms/ChapelOfAshSceneTests.cs"
SCENE = "Assets/Scenes/Rooms/ChapelOfAsh.unity"
BUILD_METHOD = (
    "NoSafeCircle.DoorPrototype.Editor.Rooms.ChapelOfAshSceneBuilder.BuildAndSave")
LEASE = "fixture-lease"


class ReopenMaterializationTests(unittest.TestCase):
    """A materialized candidate whose validation failed on a HOST defect."""

    def setUp(self):
        test_root = Path.cwd() / ".test-work"
        test_root.mkdir(exist_ok=True)
        self.root = test_root / f"assistant-reopen-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git(self.source, "init", "-q")
        name, email = validated_agent_git_identity()
        self.git(self.source, "config", "user.name", name)
        self.git(self.source, "config", "user.email", email)
        for relative, content in (
            (BUILDER, "class ChapelOfAshSceneBuilder {}\n"),
            (TESTS, "class ChapelOfAshSceneTests {}\n"),
            (SCENE, "old chapel scene\n"),
            ("ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 6000.1.8f1\n"),
            ("Pipeline/Testing/run_unity_tests_clean.ps1", "# fixture\n"),
            ("Pipeline/TaskGraph/taskcontrol.py", "print('taskcontrol validate: PASS')\n"),
        ):
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        task = {
            "schema_version": "2.0", "id": "NSC-046", "contract_revision": 1,
            "contract_disposition": "active", "title": "Fixture Chapel of Ash room",
            "reconciliation_key": "fixture-chapel", "kind": "implementation",
            "type": "world-foundation", "execution_scope": "single_agent",
            "execution_reason": "fixture", "decomposition_state": "concrete",
            "decomposition_reason": "fixture", "parent": None, "depends_on": [],
            "exclusive_resources": [
                f"repo-file:{BUILDER}", f"repo-file:{TESTS}",
                f"unity-scene:{SCENE}",
            ],
            "acceptance_criteria": [], "completion_gates": [],
            "downstream_integration_obligations": [], "gdd_evidence": [],
            "basis": "direct_gdd", "source_scope": "required", "confidence": "high",
        }
        task_path = self.source / "Tasks/NSC-046.yaml"
        task_path.parent.mkdir()
        task_path.write_text(json.dumps(task), encoding="utf-8", newline="\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-q", "-m", "fixture")
        self.manager = Checkouts(self.source, self.root / "checkouts")
        prepared = self.manager.prepare("NSC-046")
        self.checkout = Path(prepared["checkout"])
        self.unity = self.root / "Unity.exe"
        self.unity.write_bytes(b"fixture")
        self.scope = AssistantScopePlanner(self.manager).plan(
            "NSC-046",
            ExecutionScopePlan((BUILDER, SCENE), (), (TESTS,), ()),
            lease_id=LEASE,
        )

    @staticmethod
    def git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ("git", "-C", str(root), *args), capture_output=True, check=False)
        if result.returncode:
            raise AssertionError(result.stderr.decode(errors="replace"))
        return result.stdout.decode().strip()

    def register_candidate(self) -> str:
        (self.checkout / BUILDER).write_text("class Fixed {}\n", newline="\n")
        (self.checkout / TESTS).write_text("class FixedTests {}\n", newline="\n")
        paths = [BUILDER, TESTS]
        self.git(self.checkout, "add", "--", *paths)
        self.git(self.checkout, "commit", "-q", "-m", "crew candidate")
        commit = self.git(self.checkout, "rev-parse", "HEAD")
        tree = self.git(self.checkout, "rev-parse", "HEAD^{tree}")
        record_path = self.manager.records / "NSC-046.json"
        record = json.loads(record_path.read_text())
        receipt = LocalCandidateCommitReceipt(
            task_id="NSC-046", lease_id=LEASE, plan_id=self.scope["plan_id"],
            run_id="fixture-crew", source_base=record["source_commit"],
            candidate_commit=commit, candidate_tree=tree,
            candidate_parent=record["source_commit"],
            task_contract_sha256=record["task_contract_sha256"],
            execution_result_sha256="a" * 64, candidate_patch_sha256="b" * 64,
            changed_paths=tuple(sorted(paths, key=str.casefold)),
            validation_sha256="c" * 64,
        )
        record["candidate"] = {
            "commit": commit, "tree": tree, "parent": record["source_commit"],
            "run_id": "fixture-crew", "lease_id": LEASE,
            "plan_id": self.scope["plan_id"], "receipt": receipt.to_dict(),
        }
        record["status"] = "awaiting_human"
        record["approval"] = None
        write_record(record_path, record)
        return commit

    def builder(self, args, cwd, timeout):
        (cwd / SCENE).write_text("generated chapel scene\n", newline="\n")
        return subprocess.CompletedProcess(args, 0, b"ok\n", b"")

    def passing_validation(self, **kwargs):
        commit = self.git(kwargs["checkout"], "rev-parse", "HEAD")
        self.assertEqual(
            "", self.git(kwargs["checkout"], "status", "--porcelain=v1"))
        return ({
            "test_platform": "EditMode", "test_filter": "ChapelOfAshSceneTests",
            "commit": commit,
            "tree": self.git(kwargs["checkout"], "rev-parse", "HEAD^{tree}"),
            "total": 2, "passed": 2,
        },)

    def failing_validation(self, **kwargs):
        raise AuthoritativeCandidateValidationError(
            "authoritative validation requires a clean task checkout")

    def make_failed_record(self) -> tuple[str, str, str]:
        """Produce the failure by RUNNING the real path, not by writing it."""
        original = self.register_candidate()
        with self.assertRaises(MaterializationError):
            materialize_candidate(
                self.manager, "NSC-046", original, unity_executable=self.unity,
                unity_command_runner=self.builder,
                validation_runner=self.failing_validation,
            )
        record = json.loads((self.manager.records / "NSC-046.json").read_text())
        self.assertEqual("validation_failed", record["status"])
        self.assertEqual("unity_materialization_failed", record["candidate"]["kind"])
        materialized = record["candidate"]["commit"]
        digest = validation_failure_sha256(record["materialization_failure"])
        return original, materialized, digest

    def land_host_fix(self) -> str:
        (self.source / "Pipeline/Testing/run_unity_tests_clean.ps1").write_text(
            "# fixture, repaired\n", encoding="utf-8", newline="\n")
        self.git(self.source, "add", "--", "Pipeline/Testing/run_unity_tests_clean.ps1")
        self.git(self.source, "commit", "-q", "-m", "host fix")
        return self.git(self.source, "rev-parse", "HEAD")

    def test_dry_run_reports_without_touching_the_record(self):
        _original, materialized, digest = self.make_failed_record()
        fix = self.land_host_fix()
        plan = reopen_materialization(
            self.manager, "NSC-046", expected_candidate=materialized,
            expected_failure_sha256=digest, host_fix_commit=fix)
        self.assertFalse(plan["applied"])
        record = json.loads((self.manager.records / "NSC-046.json").read_text())
        self.assertEqual("validation_failed", record["status"])

    def test_apply_restores_the_original_candidate_and_needs_materialization(self):
        original, materialized, digest = self.make_failed_record()
        fix = self.land_host_fix()
        plan = reopen_materialization(
            self.manager, "NSC-046", expected_candidate=materialized,
            expected_failure_sha256=digest, host_fix_commit=fix, apply=True)
        self.assertTrue(plan["applied"])
        record = json.loads((self.manager.records / "NSC-046.json").read_text())
        self.assertEqual("needs_materialization", record["status"])
        self.assertEqual(original, record["candidate"]["commit"])
        self.assertNotIn("materialization_failure", record)
        self.assertEqual(original, self.git(self.checkout, "rev-parse", "HEAD"))
        self.assertEqual(
            "", self.git(self.checkout, "status", "--porcelain=v1", "--untracked-files=all"))

    def test_the_materialized_commit_is_preserved_not_orphaned(self):
        """A reopen must never be why a commit becomes unreachable."""
        _original, materialized, digest = self.make_failed_record()
        fix = self.land_host_fix()
        plan = reopen_materialization(
            self.manager, "NSC-046", expected_candidate=materialized,
            expected_failure_sha256=digest, host_fix_commit=fix, apply=True)
        self.assertEqual(
            materialized,
            self.git(self.checkout, "rev-parse", plan["preserved_ref"]))

    def test_no_host_fix_is_refused(self):
        """The guard that correctly refuses NSC-045, whose failure is its own."""
        _original, materialized, digest = self.make_failed_record()
        head = self.git(self.source, "rev-parse", "HEAD")
        with self.assertRaisesRegex(
                MaterializationReopenError, "no host fix after the failed run"):
            reopen_materialization(
                self.manager, "NSC-046", expected_candidate=materialized,
                expected_failure_sha256=digest, host_fix_commit=head, apply=True)

    def test_a_wrong_failure_digest_is_refused(self):
        _original, materialized, _digest = self.make_failed_record()
        fix = self.land_host_fix()
        with self.assertRaisesRegex(
                MaterializationReopenError, "differs from the exact request"):
            reopen_materialization(
                self.manager, "NSC-046", expected_candidate=materialized,
                expected_failure_sha256="d" * 64, host_fix_commit=fix, apply=True)

    def test_a_reviewed_record_is_refused(self):
        """Reopening a reviewed candidate would be an approval decision."""
        _original, materialized, digest = self.make_failed_record()
        fix = self.land_host_fix()
        record_path = self.manager.records / "NSC-046.json"
        record = json.loads(record_path.read_text())
        record["human_review"] = {"decision": "rejected"}
        write_record(record_path, record)
        with self.assertRaisesRegex(
                MaterializationReopenError, "approval decision"):
            reopen_materialization(
                self.manager, "NSC-046", expected_candidate=materialized,
                expected_failure_sha256=digest, host_fix_commit=fix, apply=True)

    def test_an_unrelated_contract_revision_on_main_does_not_block_reopen(self):
        """GER propagating a contract fix must not strand a parked candidate.

        Materialization binds the contract in the CHECKOUT at the candidate
        commit against the record pin, never at Source HEAD -- so contract
        churn on main provably cannot reach a parked candidate.
        """
        _original, materialized, digest = self.make_failed_record()
        task_path = self.source / "Tasks/NSC-046.yaml"
        task = json.loads(task_path.read_text())
        task["contract_revision"] = 2
        task["title"] = "Fixture Chapel of Ash room, revised"
        task_path.write_text(json.dumps(task), encoding="utf-8", newline="\n")
        self.git(self.source, "add", "--", "Tasks/NSC-046.yaml")
        self.git(self.source, "commit", "-q", "-m", "GER: contract revision 2")
        fix = self.git(self.source, "rev-parse", "HEAD")
        plan = reopen_materialization(
            self.manager, "NSC-046", expected_candidate=materialized,
            expected_failure_sha256=digest, host_fix_commit=fix, apply=True)
        self.assertTrue(plan["applied"])
        record = json.loads((self.manager.records / "NSC-046.json").read_text())
        self.assertEqual("needs_materialization", record["status"])

    def test_the_retained_journal_is_archived_not_left_to_short_circuit(self):
        """The defect the record-level tests could not see.

        The journal is keyed by the CANDIDATE commit, which is exactly what the
        reopen restores to, so it survived and unity_materialization refused
        with "unfinished Unity materialization was retained". Archived, not
        deleted: a reopen must never be why something becomes unreachable.
        """
        original, materialized, digest = self.make_failed_record()
        journal = (self.manager.records
                   / f"NSC-046.unity-materialization.{original}.json")
        self.assertTrue(journal.is_file(), "fixture did not retain a journal")
        fix = self.land_host_fix()
        plan = reopen_materialization(
            self.manager, "NSC-046", expected_candidate=materialized,
            expected_failure_sha256=digest, host_fix_commit=fix, apply=True)
        self.assertFalse(journal.exists(), "journal still short-circuits materialization")
        archived = pathlib.Path(plan["archived_journal"])
        self.assertTrue(archived.is_file(), "journal was deleted rather than archived")

    def test_materialization_actually_runs_again_after_a_reopen(self):
        """END TO END: the thing the command exists for.

        Every other reopen test asserts the RECORD. This asserts that Unity is
        invoked and a NEW materialized commit appears -- which is what failed on
        NSC-046 while every record-level assertion passed.
        """
        original, materialized, digest = self.make_failed_record()
        fix = self.land_host_fix()
        reopen_materialization(
            self.manager, "NSC-046", expected_candidate=materialized,
            expected_failure_sha256=digest, host_fix_commit=fix, apply=True)
        launched = []

        def counting_builder(args, cwd, timeout):
            launched.append(args)
            return self.builder(args, cwd, timeout)

        result = materialize_candidate(
            self.manager, "NSC-046", original, unity_executable=self.unity,
            unity_command_runner=counting_builder,
            validation_runner=self.passing_validation,
        )
        self.assertTrue(launched, "Unity was never invoked after the reopen")
        self.assertEqual("awaiting_human", result["status"])
        self.assertNotEqual(
            original, result["candidate"]["commit"],
            "materialization produced no new commit")

    def _reopen_leaving_the_journal(self):
        """The state both rooms are in: record reopened, journal still there.

        Produced by running the real reopen and restoring the journal, rather
        than by hand-writing a record -- the state has to be one the command
        can actually produce.
        """
        original, materialized, digest = self.make_failed_record()
        journal = (self.manager.records
                   / f"NSC-046.unity-materialization.{original}.json")
        retained = journal.read_bytes()
        fix = self.land_host_fix()
        reopen_materialization(
            self.manager, "NSC-046", expected_candidate=materialized,
            expected_failure_sha256=digest, host_fix_commit=fix, apply=True)
        archived = pathlib.Path(
            json.loads((self.manager.records / "NSC-046.json").read_text())
            ["materialization_reopen"]["archived_journal"])
        archived.unlink()
        journal.write_bytes(retained)
        return original, materialized, digest, fix, journal

    def test_a_reopen_can_be_resumed_to_retire_a_surviving_journal(self):
        """Both rooms are in this state; without this they need a hand-moved file."""
        _original, materialized, digest, fix, journal = self._reopen_leaving_the_journal()
        self.assertTrue(journal.is_file())
        plan = reopen_materialization(
            self.manager, "NSC-046", expected_candidate=materialized,
            expected_failure_sha256=digest, host_fix_commit=fix, apply=True)
        self.assertTrue(plan["applied"])
        self.assertTrue(plan["resumed"])
        self.assertFalse(journal.exists())
        self.assertTrue(pathlib.Path(plan["archived_journal"]).is_file())

    def test_resume_dry_run_reports_without_moving_the_journal(self):
        _original, materialized, digest, fix, journal = self._reopen_leaving_the_journal()
        plan = reopen_materialization(
            self.manager, "NSC-046", expected_candidate=materialized,
            expected_failure_sha256=digest, host_fix_commit=fix)
        self.assertFalse(plan["applied"])
        self.assertTrue(journal.is_file())

    def test_resume_with_nothing_left_says_so_rather_than_claiming_success(self):
        """A command that reports success for work it did not do is worse
        than one that refuses."""
        _original, materialized, digest = self.make_failed_record()
        fix = self.land_host_fix()
        reopen_materialization(
            self.manager, "NSC-046", expected_candidate=materialized,
            expected_failure_sha256=digest, host_fix_commit=fix, apply=True)
        plan = reopen_materialization(
            self.manager, "NSC-046", expected_candidate=materialized,
            expected_failure_sha256=digest, host_fix_commit=fix, apply=True)
        self.assertTrue(plan.get("nothing_to_do"))
        self.assertFalse(plan["applied"])

    def test_resume_refuses_a_digest_that_is_not_the_recorded_one(self):
        """Resume is bound to the record's OWN reopen marker."""
        _original, materialized, _digest, fix, _journal = self._reopen_leaving_the_journal()
        with self.assertRaisesRegex(
                MaterializationReopenError, "not 'needs_materialization'"):
            reopen_materialization(
                self.manager, "NSC-046", expected_candidate=materialized,
                expected_failure_sha256="f" * 64, host_fix_commit=fix, apply=True)

    def test_a_crew_candidate_is_refused(self):
        """This command is for a failed MATERIALIZED candidate only."""
        original = self.register_candidate()
        fix = self.land_host_fix()
        with self.assertRaisesRegex(MaterializationReopenError, "failed materialized"):
            reopen_materialization(
                self.manager, "NSC-046", expected_candidate=original,
                expected_failure_sha256="d" * 64, host_fix_commit=fix, apply=True)


    # ------------------------------------------------------------------
    # REOPEN NEVER DESTROYS AN OPERATOR'S UNCOMMITTED WORK.
    #
    # `--apply` ends in `git reset --hard`, and HEAD was checked while the
    # WORKING TREE was not. Whoever runs this is by definition investigating a
    # FAILED materialization, so whatever is uncommitted in that checkout is
    # their diagnosis. Found by Astra's main audit, 2026-09-23, in a module I
    # wrote.
    #
    # These live in this class rather than a subclass on purpose: subclassing
    # it re-runs all fourteen of its tests for the fixture alone.
    # ------------------------------------------------------------------

    NOTES = "investigation-notes.txt"

    def dirty_tracked_edit(self) -> str:
        """An edit to a TRACKED file -- the shape `reset --hard` destroys."""
        text = "class ChapelOfAshSceneBuilder { /* mid-investigation */ }\n"
        (self.checkout / BUILDER).write_text(text, encoding="utf-8", newline="\n")
        return text

    def record_status(self) -> str:
        return json.loads(
            (self.manager.records / "NSC-046.json").read_text()
        )["status"]

    def test_apply_refuses_and_the_edit_is_still_there_afterwards(self):
        _original, materialized, digest = self.make_failed_record()
        fix = self.land_host_fix()
        text = self.dirty_tracked_edit()
        with self.assertRaises(MaterializationReopenError) as caught:
            reopen_materialization(
                self.manager, "NSC-046", expected_candidate=materialized,
                expected_failure_sha256=digest, host_fix_commit=fix, apply=True)
        message = str(caught.exception)
        self.assertIn("uncommitted changes", message)
        self.assertIn(BUILDER, message)
        self.assertIn("reset --hard", message)
        # The assertion that actually matters: the work survived.
        self.assertEqual(
            text, (self.checkout / BUILDER).read_text(encoding="utf-8"))
        self.assertEqual("validation_failed", self.record_status())

    def test_the_dry_run_refuses_too_so_it_is_learned_before_applying(self):
        _original, materialized, digest = self.make_failed_record()
        fix = self.land_host_fix()
        self.dirty_tracked_edit()
        with self.assertRaises(MaterializationReopenError) as caught:
            reopen_materialization(
                self.manager, "NSC-046", expected_candidate=materialized,
                expected_failure_sha256=digest, host_fix_commit=fix)
        self.assertIn("uncommitted changes", str(caught.exception))

    def test_an_untracked_file_is_refused_before_the_record_moves(self):
        """`reset --hard` spares untracked files, then the post-reset check
        refuses -- after the journal was archived and the ref written. Refusing
        up front turns a half-done reopen into a clean one."""
        _original, materialized, digest = self.make_failed_record()
        fix = self.land_host_fix()
        (self.checkout / self.NOTES).write_text(
            "why it failed\n", encoding="utf-8", newline="\n")
        with self.assertRaises(MaterializationReopenError) as caught:
            reopen_materialization(
                self.manager, "NSC-046", expected_candidate=materialized,
                expected_failure_sha256=digest, host_fix_commit=fix, apply=True)
        self.assertIn(self.NOTES, str(caught.exception))
        self.assertTrue((self.checkout / self.NOTES).is_file())
        self.assertEqual("validation_failed", self.record_status())

    def test_an_edit_arriving_after_verification_is_still_not_destroyed(self):
        """The first check runs OUTSIDE the lock, so it can go stale.

        Simulated by making the first observation report clean while the tree is
        really dirty -- which is exactly what a write landing between the two
        looks like from in here. Without the second check this reaches the reset.
        """
        from unittest import mock

        import Pipeline.AssistantControl.materialization_reopen as reopen

        _original, materialized, digest = self.make_failed_record()
        fix = self.land_host_fix()
        text = self.dirty_tracked_edit()
        real = reopen._working_tree_dirt
        calls = []

        def clean_once(checkout):
            calls.append(checkout)
            return () if len(calls) == 1 else real(checkout)

        with mock.patch.object(reopen, "_working_tree_dirt", clean_once):
            with self.assertRaises(MaterializationReopenError) as caught:
                reopen_materialization(
                    self.manager, "NSC-046", expected_candidate=materialized,
                    expected_failure_sha256=digest, host_fix_commit=fix,
                    apply=True)
        self.assertIn("became dirty after verification", str(caught.exception))
        self.assertIn("nothing was discarded", str(caught.exception))
        self.assertEqual(
            text, (self.checkout / BUILDER).read_text(encoding="utf-8"))
        self.assertGreater(len(calls), 1, "the second observation never happened")

    def test_an_ignored_file_does_not_block_a_reopen(self):
        """A guard this strict would block every reopen in a real checkout.

        Unity litters ignored paths constantly and none of it is at risk from a
        reset. Excluded via .git/info/exclude specifically because that is not a
        tracked file, so the fixture stays clean while proving the case.
        """
        _original, materialized, digest = self.make_failed_record()
        fix = self.land_host_fix()
        exclude = self.checkout / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("\nunity-scratch.tmp\n")
        (self.checkout / "unity-scratch.tmp").write_text(
            "ignored\n", encoding="utf-8", newline="\n")
        plan = reopen_materialization(
            self.manager, "NSC-046", expected_candidate=materialized,
            expected_failure_sha256=digest, host_fix_commit=fix, apply=True)
        self.assertTrue(plan["applied"])
        self.assertEqual("needs_materialization", self.record_status())


if __name__ == "__main__":
    unittest.main()
