#!/usr/bin/env python
"""Tests for the standalone closure job record.

Run:
    python -B test_closure_record.py

A closure review run outside a GER packet had no completion record, so a consumer
could not tell a review whose job succeeded from one whose job failed - and
`resolve_post_commit_check` accepted a result that `check_job_result` rejects
with a non-zero process status, giving it `imported` provenance it had not
earned (Astra MJ-P3-03, reproduced at the boundary).

The record is the host's evidence that a review was PRODUCED. It is not a second
verdict: the reviewer's result still owns the decision and `recommendation` is
deliberately absent from the record.

Exact types are the recurring theme. A truthiness test accepts `exit_code: false`
and a missing `is_error`, which is why each is asserted as itself.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import closure_record  # noqa: E402
import review_result  # noqa: E402

TASK = "NSC-001"
CONTRACT = b'{"task": "NSC-001", "revision": 7}\n'
DIGEST = hashlib.sha256(CONTRACT).hexdigest()
VIEW = b"rendered human view\n"


def result_bytes(**overrides) -> bytes:
    body = {
        "schema_version": 1, "review_kind": "closure", "task_id": TASK,
        "reviewed_artifact_kind": "contract", "reviewed_artifact_sha256": DIGEST,
        "review_status": "complete", "recommendation": "commit_contract",
        "report_markdown": "Ledger:\n- L1: RESOLVED.",
    }
    body.update(overrides)
    return json.dumps(body).encode("utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.result = self.tmp / "JOB.result.json"

    def finish(self, raw: bytes | None = None, *, view: bytes = VIEW,
               provider: str = "codex", **overrides) -> dict:
        """A finished job: result, view, record - as a launcher writes them."""
        raw = result_bytes() if raw is None else raw
        self.result.write_bytes(raw)
        closure_record.view_path(self.result).write_bytes(view)
        record = closure_record.build(
            task_id=TASK, provider=provider, reviewed_artifact_sha256=DIGEST,
            result_bytes=raw, view_bytes=view, exit_code=0,
            is_error=None if provider == "codex" else False,
            started_at=1_700_000_000.0, completed_at=1_700_000_042.0,
            review_status="complete")
        record.update(overrides)
        closure_record.publish(self.result, record)
        return record

    def read(self, **kwargs):
        return closure_record.read_job(
            self.result, task_id=kwargs.pop("task_id", TASK),
            reviewed_artifact_sha256=kwargs.pop("reviewed_artifact_sha256", DIGEST))

    def refuses(self, code: str, **finish):
        self.finish(**finish)
        with self.assertRaises(closure_record.RecordError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, code, caught.exception.message)


class TheNamingRule(unittest.TestCase):
    """Derived once, never supplied - so relocating a job's files keeps working."""

    def test_the_record_sits_beside_the_raw_result(self):
        self.assertEqual(
            closure_record.metadata_path(Path("/x/JOB.result.json")).name,
            "JOB.result.json.metadata.json")

    def test_the_view_is_the_jobs_report(self):
        self.assertEqual(closure_record.view_path(Path("/x/JOB.result.json")).name,
                         "JOB.report.md")

    def test_both_stay_in_the_jobs_directory(self):
        result = Path("/somewhere/else/JOB.result.json")
        self.assertEqual(closure_record.metadata_path(result).parent, result.parent)
        self.assertEqual(closure_record.view_path(result).parent, result.parent)


class AFinishedJob(Base):
    def test_it_reads_back_the_validated_result(self):
        self.finish()
        self.assertEqual(self.read().recommendation, "commit_contract")

    def test_a_completed_revise_is_a_finished_job(self):
        # The point Astra made explicitly: a negative verdict is a finished
        # review and gets a record and a zero exit, like an approval.
        self.finish(result_bytes(recommendation="revise"))
        self.assertEqual(self.read().recommendation, "revise")

    def test_a_claude_record_carries_is_error_false(self):
        self.finish(provider="claude-host")
        self.assertEqual(self.read().recommendation, "commit_contract")

    def test_the_record_carries_no_verdict(self):
        record = self.finish()
        self.assertNotIn("recommendation", record)

    def test_a_real_session_id_is_kept_and_a_missing_one_is_not_invented(self):
        with_id = closure_record.build(
            task_id=TASK, provider="claude-host", reviewed_artifact_sha256=DIGEST,
            result_bytes=b"{}", view_bytes=VIEW, exit_code=0, is_error=False,
            started_at=1.0, completed_at=2.0, review_status="complete",
            session_id="session-real")
        self.assertEqual(with_id["session_id"], "session-real")
        without = closure_record.build(
            task_id=TASK, provider="codex", reviewed_artifact_sha256=DIGEST,
            result_bytes=b"{}", view_bytes=VIEW, exit_code=0, is_error=None,
            started_at=1.0, completed_at=2.0, review_status="complete")
        self.assertNotIn("session_id", without)


class AnUnfinishedJob(Base):
    def test_no_record_means_unfinished(self):
        self.result.write_bytes(result_bytes())
        closure_record.view_path(self.result).write_bytes(VIEW)
        with self.assertRaises(closure_record.RecordError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "no_record")

    def test_a_missing_view_means_unfinished(self):
        self.finish()
        closure_record.view_path(self.result).unlink()
        with self.assertRaises(closure_record.RecordError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "no_record")

    def test_an_unreadable_record_refuses(self):
        self.finish()
        closure_record.metadata_path(self.result).write_text("{ not json",
                                                             encoding="utf-8")
        with self.assertRaises(closure_record.RecordError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "unreadable_record")

    def test_a_duplicated_key_refuses(self):
        self.finish()
        closure_record.metadata_path(self.result).write_text(
            '{"protocol": "json-v1", "protocol": "json-v1"}', encoding="utf-8")
        with self.assertRaises(closure_record.RecordError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "duplicate_key")


class ExactTypes(Base):
    """A truthiness test accepts most of these. Each is asserted as itself."""

    def test_a_false_exit_code_is_not_a_zero_one(self):
        self.refuses("not_ready", exit_code=False)

    def test_a_nonzero_exit_code_refuses(self):
        self.refuses("not_ready", exit_code=9)

    def test_a_claude_record_missing_is_error_refuses(self):
        self.finish(provider="claude-host")
        record = json.loads(closure_record.metadata_path(self.result).read_text(
            encoding="utf-8"))
        del record["is_error"]
        closure_record.metadata_path(self.result).write_text(json.dumps(record),
                                                             encoding="utf-8")
        with self.assertRaises(closure_record.RecordError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "not_ready")

    def test_a_codex_record_claiming_is_error_false_refuses(self):
        # That transport reports no such field, so claiming one is invented
        # evidence even when the value looks harmless.
        self.refuses("bad_field", provider="codex", is_error=False)

    def test_a_boolean_timestamp_refuses(self):
        self.refuses("bad_field", started_at=True)

    def test_a_non_finite_timestamp_refuses(self):
        self.refuses("bad_field", completed_at=float("inf"))

    def test_completion_before_start_refuses(self):
        self.refuses("bad_field", started_at=10.0, completed_at=9.0)

    def test_a_hash_that_is_not_64_lowercase_hex_refuses(self):
        for bad in ("A" * 64, "a" * 63, "zz"):
            with self.subTest(bad=bad):
                self.setUp()
                self.refuses("bad_field", reviewed_artifact_sha256=bad)

    def test_an_unknown_protocol_refuses(self):
        self.refuses("unknown_protocol", protocol="json-v9")

    def test_an_unknown_provider_refuses(self):
        # `provider` names the fixture's provider AND is the field being broken,
        # so the override goes in after the build rather than through it.
        self.finish()
        record = json.loads(closure_record.metadata_path(self.result).read_text(
            encoding="utf-8"))
        record["provider"] = "mystery"
        closure_record.metadata_path(self.result).write_text(json.dumps(record),
                                                             encoding="utf-8")
        with self.assertRaises(closure_record.RecordError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "unknown_provider")

    def test_an_incomplete_review_status_refuses(self):
        self.refuses("not_ready", review_status="incomplete")


class TamperingAndSubject(Base):
    def test_an_edited_result_refuses(self):
        self.finish()
        self.result.write_bytes(result_bytes(recommendation="revise"))
        with self.assertRaises(closure_record.RecordError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "tampered")

    def test_an_edited_view_refuses(self):
        self.finish()
        closure_record.view_path(self.result).write_bytes(b"a different account\n")
        with self.assertRaises(closure_record.RecordError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "tampered")

    def test_a_record_about_another_task_refuses(self):
        # Catches Exception, then asserts the TYPE and code. Catching RecordError
        # directly looked tighter but was weaker: without the subject check the
        # reader reaches review_result.load, which raises a DIFFERENT exception
        # type, so the test errored instead of failing and the mutation harness
        # correctly refused to count it. The record must refuse this itself,
        # before the reviewer's own binding is consulted.
        self.finish()
        with self.assertRaises(Exception) as caught:
            closure_record.read_job(self.result, task_id="NSC-999",
                                    reviewed_artifact_sha256=DIGEST)
        self.assertIsInstance(caught.exception, closure_record.RecordError,
                              f"the record did not refuse it; "
                              f"{type(caught.exception).__name__} did")
        self.assertEqual(caught.exception.code, "subject_mismatch")

    def test_a_record_about_other_contract_bytes_refuses(self):
        self.finish()
        with self.assertRaises(Exception) as caught:
            closure_record.read_job(self.result, task_id=TASK,
                                    reviewed_artifact_sha256="b" * 64)
        self.assertIsInstance(caught.exception, closure_record.RecordError,
                              f"the record did not refuse it; "
                              f"{type(caught.exception).__name__} did")
        self.assertEqual(caught.exception.code, "subject_mismatch")

    def test_the_reviewers_own_binding_is_still_checked(self):
        # The record agreeing is not enough; review_result.load runs too.
        other = hashlib.sha256(b"different contract").hexdigest()
        raw = result_bytes(reviewed_artifact_sha256=other)
        self.finish(raw)
        with self.assertRaises(review_result.ReviewResultError):
            self.read()


class Publication(Base):
    def test_it_leaves_no_temporary_file(self):
        self.finish()
        strays = [p.name for p in self.tmp.iterdir() if p.name.startswith(".")]
        self.assertEqual(strays, [])

    def test_a_crash_before_the_rename_leaves_no_record(self):
        # Simulated by never calling publish: absence is the whole signal.
        self.result.write_bytes(result_bytes())
        closure_record.view_path(self.result).write_bytes(VIEW)
        self.assertFalse(closure_record.metadata_path(self.result).exists())
        with self.assertRaises(closure_record.RecordError) as caught:
            self.read()
        self.assertEqual(caught.exception.code, "no_record")


if __name__ == "__main__":
    unittest.main(verbosity=2)
