"""Retry authorizes another attempt for an INTACT candidate.

The failure is produced by RUNNING the real materializer with a builder that
fails, not by hand-writing a record: the state has to be one the pipeline can
actually reach. That is what proved, on NSC-048, that a candidate with no `kind`
key at all is the normal crew-reviewed shape rather than a damaged one.

The decisive test is the end-to-end one. Every other test here asserts the
RECORD, and the record was already correct on the night `reopen` did nothing at
all -- the journal survived and short-circuited the next materialization. The
only assertion that can catch a no-op is one about an EFFECT the command does
not itself report.
"""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from Pipeline.AssistantControl import test_materialization_reopen as fixture
from Pipeline.AssistantControl.candidate_validation_retry import validation_failure_sha256
from Pipeline.AssistantControl.materialization_retry import (
    MaterializationRetryError,
    retry_materialization,
)
from Pipeline.AssistantControl.unity_materialization import (
    MaterializationError,
    materialize_candidate,
)

TASK = "NSC-046"  # the fixture's task id; the shape under test is NSC-048's


class MaterializationRetryTests(unittest.TestCase):
    setUp = fixture.ReopenMaterializationTests.setUp
    # `git` is a staticmethod there; copying the plain function would rebind it
    # as an instance method and pass `self` as the repository path.
    git = staticmethod(fixture.ReopenMaterializationTests.git)
    register_candidate = fixture.ReopenMaterializationTests.register_candidate
    builder = fixture.ReopenMaterializationTests.builder
    passing_validation = fixture.ReopenMaterializationTests.passing_validation

    def failing_validation(self, **kwargs):
        """Reopen's shape, defined here so it is bound when passed as a runner."""
        return fixture.ReopenMaterializationTests.failing_validation(self, **kwargs)

    def failing_builder(self, args, cwd, timeout):
        """The NSC-048 shape: Unity refuses the entry point, nothing is written."""
        return subprocess.CompletedProcess(
            args, 1, b"",
            b"executeMethod method 'Build' could not be found.\n")

    def make_attempt_failure(self) -> tuple[str, str]:
        """Produce a BUILDER failure by running the real path.

        Distinct from the reopen fixture's validation failure: no materialized
        commit is created, so the candidate is never replaced.
        """
        candidate = self.register_candidate()
        with self.assertRaises(MaterializationError):
            materialize_candidate(
                self.manager, TASK, candidate, unity_executable=self.unity,
                unity_command_runner=self.failing_builder,
                validation_runner=self.passing_validation,
            )
        record = json.loads((self.manager.records / f"{TASK}.json").read_text())
        self.assertEqual("materialization_failed", record["status"])
        # The candidate is INTACT: not replaced, and carrying no kind key.
        self.assertEqual(candidate, record["candidate"]["commit"])
        self.assertNotIn("kind", record["candidate"])
        failure = record["materialization_failure"]
        self.assertIsNone(failure.get("materialized_commit"))
        return candidate, validation_failure_sha256(failure)

    def record(self) -> dict:
        return json.loads((self.manager.records / f"{TASK}.json").read_text())

    def test_a_plan_changes_nothing_and_names_the_retained_journal(self):
        candidate, digest = self.make_attempt_failure()
        before = (self.manager.records / f"{TASK}.json").read_bytes()
        plan = retry_materialization(
            self.manager, TASK, expected_candidate=candidate,
            expected_failure_sha256=digest, reason="registry fixed host-side")
        self.assertFalse(plan["applied"])
        self.assertEqual(before, (self.manager.records / f"{TASK}.json").read_bytes())
        self.assertTrue(Path(plan["retained_journal"]).is_file())

    def test_apply_preserves_the_failure_and_returns_the_record_to_needs_materialization(self):
        candidate, digest = self.make_attempt_failure()
        pin = self.record()["task_contract_sha256"]
        receipt = self.record()["candidate"].get("receipt")
        plan = retry_materialization(
            self.manager, TASK, expected_candidate=candidate,
            expected_failure_sha256=digest, reason="registry fixed host-side", apply=True)
        self.assertTrue(plan["applied"])
        record = self.record()
        self.assertEqual("needs_materialization", record["status"])
        self.assertNotIn("materialization_failure", record)
        # Untouched by design: candidate, its receipt, and the contract pin.
        self.assertEqual(candidate, record["candidate"]["commit"])
        self.assertEqual(receipt, record["candidate"].get("receipt"))
        self.assertEqual(pin, record["task_contract_sha256"])
        # The failure is preserved, not discarded, and keeps its own verdict.
        archived = json.loads(Path(plan["archived_failure"]).read_text(encoding="utf-8"))
        self.assertEqual(digest, validation_failure_sha256(
            archived["materialization_failure"]))
        self.assertIs(False, archived["materialization_failure"]["retryable"])

    def test_the_retained_journal_is_archived_not_left_to_short_circuit(self):
        """The defect a record-level assertion cannot see.

        The materializer inspects an existing journal BEFORE it checks candidate
        eligibility, so a status change alone yields "unfinished Unity
        materialization was retained".
        """
        candidate, digest = self.make_attempt_failure()
        journal = Path(self.manager.records
                       / f"{TASK}.unity-materialization.{candidate}.json")
        self.assertTrue(journal.is_file(), "fixture produced no journal")
        plan = retry_materialization(
            self.manager, TASK, expected_candidate=candidate,
            expected_failure_sha256=digest, reason="registry fixed host-side", apply=True)
        self.assertFalse(journal.exists())
        self.assertTrue(Path(plan["archived_journal"]).is_file())

    def test_materialization_actually_runs_again_after_a_retry(self):
        """END TO END: the thing the command exists for.

        Asserts an effect the command does not report -- that Unity is invoked
        and a materialized commit appears -- rather than the record it writes.
        """
        candidate, digest = self.make_attempt_failure()
        retry_materialization(
            self.manager, TASK, expected_candidate=candidate,
            expected_failure_sha256=digest, reason="registry fixed host-side", apply=True)
        launched = []

        def counting_builder(args, cwd, timeout):
            launched.append(args)
            return fixture.ReopenMaterializationTests.builder(self, args, cwd, timeout)

        result = materialize_candidate(
            self.manager, TASK, candidate, unity_executable=self.unity,
            unity_command_runner=counting_builder,
            validation_runner=self.passing_validation,
        )
        self.assertTrue(launched, "Unity was never invoked after the retry")
        self.assertEqual("awaiting_human", result["status"])
        self.assertNotEqual(candidate, result["candidate"]["commit"])

    def test_a_validation_failure_belongs_to_reopen_and_is_refused(self):
        """The boundary. A failure that produced a materialized commit replaced
        its candidate, and restoring that is reopen's transition, not this one."""
        candidate = self.register_candidate()
        with self.assertRaises(MaterializationError):
            materialize_candidate(
                self.manager, TASK, candidate, unity_executable=self.unity,
                unity_command_runner=self.builder,
                validation_runner=self.failing_validation,
            )
        record = self.record()
        self.assertEqual("validation_failed", record["status"])
        digest = validation_failure_sha256(record["materialization_failure"])
        with self.assertRaisesRegex(MaterializationRetryError, "not 'validation_failed'"):
            retry_materialization(
                self.manager, TASK, expected_candidate=record["candidate"]["commit"],
                expected_failure_sha256=digest, reason="wrong command", apply=True)

    def test_a_retry_requires_a_stated_reason(self):
        """The mechanical checks cannot establish the blocker is gone, so the
        operator's rationale is the only evidence there is."""
        candidate, digest = self.make_attempt_failure()
        with self.assertRaisesRegex(MaterializationRetryError, "stated reason"):
            retry_materialization(
                self.manager, TASK, expected_candidate=candidate,
                expected_failure_sha256=digest, reason="   ", apply=True)

    def test_a_digest_that_is_not_the_recorded_failure_is_refused(self):
        candidate, _digest = self.make_attempt_failure()
        with self.assertRaisesRegex(MaterializationRetryError, "differs from the exact request"):
            retry_materialization(
                self.manager, TASK, expected_candidate=candidate,
                expected_failure_sha256="f" * 64, reason="registry fixed", apply=True)

    def test_a_second_apply_refuses_rather_than_overwriting_the_first_evidence(self):
        candidate, digest = self.make_attempt_failure()
        retry_materialization(
            self.manager, TASK, expected_candidate=candidate,
            expected_failure_sha256=digest, reason="registry fixed", apply=True)
        # Put the record back into the failed shape to re-reach the archive step.
        record = self.record()
        record["status"] = "materialization_failed"
        record["materialization_failure"] = json.loads(
            Path(record["materialization_retry"]["archived_failure"]).read_text(
                encoding="utf-8"))["materialization_failure"]
        (self.manager.records / f"{TASK}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(MaterializationRetryError, "archive already exists"):
            retry_materialization(
                self.manager, TASK, expected_candidate=candidate,
                expected_failure_sha256=digest, reason="registry fixed", apply=True)


if __name__ == "__main__":
    unittest.main()
