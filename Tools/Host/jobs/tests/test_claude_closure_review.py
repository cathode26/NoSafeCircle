#!/usr/bin/env python
"""Tests for the tracked Claude closure-review adapter.

Run:
    python -B test_claude_closure_review.py

The two live adapters this replaces both returned 0 after a provider failure:
their only non-zero exits were an unreadable wrapper JSON and a usage-limit
phrase found in the review text. A run with `is_error: true`, or one whose
review was empty, reported success - so a caller branching on the exit status
was told a review had happened when it had not.

`interpret` is where every one of those decisions lives, and its ORDER is the
property under test: process status, then emptiness, then the protocol. A
well-formed result must never excuse a failed run, and a failed run must never be
read for content. Each test names which of those it pins.

No provider is called. The fixtures are captured wrapper JSON of the shape the
CLI emits with --output-format json.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import claude_closure_review as ccr  # noqa: E402
import review_result  # noqa: E402

TASK = "NSC-001"
CONTRACT = b'{"task": "NSC-001", "revision": 7}\n'
DIGEST = hashlib.sha256(CONTRACT).hexdigest()


def result_json(**overrides) -> str:
    body = {
        "schema_version": 1,
        "review_kind": "closure",
        "task_id": TASK,
        "reviewed_artifact_kind": "contract",
        "reviewed_artifact_sha256": DIGEST,
        "review_status": "complete",
        "recommendation": "commit_contract",
        "report_markdown": "Ledger:\n- L1: RESOLVED.",
    }
    body.update(overrides)
    return json.dumps(body)


def wrapper(result: str | None = None, **overrides) -> bytes:
    """What the CLI writes with --output-format json."""
    body = {"subtype": "success", "is_error": False, "num_turns": 12,
            "result": result_json() if result is None else result}
    body.update(overrides)
    return json.dumps(body).encode("utf-8")


class Base(unittest.TestCase):
    def interpret(self, raw: bytes, task_id: str = TASK, contract: bytes = CONTRACT):
        return ccr.interpret(raw, task_id=task_id, contract=contract)


class ProviderStatusComesFirst(Base):
    """A well-formed result must never excuse a failed run."""

    def test_is_error_fails_even_with_a_perfect_result(self):
        # The exact defect: the live adapters returned 0 here.
        status, message, result = self.interpret(
            wrapper(is_error=True, subtype="error_during_execution"))
        self.assertEqual(status, ccr.PROVIDER_FAILED)
        self.assertIn("is_error", message)
        self.assertIsNone(result)

    def test_an_empty_result_fails_even_when_the_run_reported_success(self):
        for empty in (None, "", "   \n\t"):
            with self.subTest(empty=repr(empty)):
                status, _message, _result = self.interpret(wrapper(result=empty or ""))
                self.assertEqual(status, ccr.EMPTY_RESULT)

    def test_a_missing_result_key_is_empty_not_a_crash(self):
        status, _message, _result = self.interpret(
            json.dumps({"is_error": False}).encode("utf-8"))
        self.assertEqual(status, ccr.EMPTY_RESULT)

    def test_unreadable_wrapper_output_is_a_setup_failure(self):
        self.assertEqual(self.interpret(b"not json at all")[0], ccr.SETUP_REFUSED)
        self.assertEqual(self.interpret(b'["a list"]')[0], ccr.SETUP_REFUSED)


class TheProtocolDecides(Base):
    def test_a_bound_result_succeeds(self):
        status, message, result = self.interpret(wrapper())
        self.assertEqual(status, ccr.OK)
        self.assertIn("commit_contract", message)
        self.assertEqual(result.recommendation, "commit_contract")

    def test_a_negative_verdict_still_succeeds(self):
        status, _message, result = self.interpret(
            wrapper(result=result_json(recommendation="revise")))
        self.assertEqual(status, ccr.OK)
        self.assertEqual(result.recommendation, "revise")

    def test_a_declared_incomplete_is_not_actionable(self):
        status, message, _result = self.interpret(wrapper(result=result_json(
            review_status="incomplete", recommendation=None,
            report_markdown="I could not finish.")))
        self.assertEqual(status, ccr.NOT_ACTIONABLE)
        self.assertIn("incomplete", message)

    def test_prose_instead_of_a_result_is_not_actionable(self):
        # What the old adapters accepted and grepped.
        status, message, _result = self.interpret(wrapper(
            result="Ledger:\n- L1 RESOLVED\n\nFinal recommendation: commit_contract"))
        self.assertEqual(status, ccr.NOT_ACTIONABLE)
        self.assertIn("not_json", message)

    def test_a_review_of_a_different_contract_is_not_actionable(self):
        status, message, _result = self.interpret(
            wrapper(), contract=b'{"task": "NSC-001", "revision": 8}\n')
        self.assertEqual(status, ccr.NOT_ACTIONABLE)
        self.assertIn("artifact_hash_mismatch", message)

    def test_a_review_of_a_different_task_is_not_actionable(self):
        status, message, _result = self.interpret(wrapper(), task_id="NSC-999")
        self.assertEqual(status, ccr.NOT_ACTIONABLE)
        self.assertIn("task_mismatch", message)


class UsageLimits(Base):
    def test_a_usage_limit_in_prose_is_reported_as_one(self):
        status, message, _result = self.interpret(wrapper(
            result="I hit a usage limit and stopped."))
        self.assertEqual(status, ccr.USAGE_LIMIT)
        self.assertIn("tell Vincent", message)

    def test_a_review_that_merely_discusses_rate_limits_still_validates(self):
        # The old check searched the whole result text, so a review whose
        # narrative mentioned rate limits was reported as a usage limit. A
        # well-formed JSON result is a review, whatever it talks about.
        status, _message, result = self.interpret(wrapper(result=result_json(
            report_markdown="The task must handle a rate limit from the service.")))
        self.assertEqual(status, ccr.OK)
        self.assertEqual(result.recommendation, "commit_contract")


class TheRenderedView(Base):
    def test_it_is_labelled_and_carries_the_narrative(self):
        _status, _message, result = self.interpret(wrapper(result=result_json(
            report_markdown="Ledger:\n- L1: RESOLVED at line 40.")))
        view = ccr.render(result)
        self.assertIn(review_result.DERIVED_VIEW_MARKER, view)
        self.assertIn("L1: RESOLVED at line 40.", view)
        self.assertIn("- Recommendation: commit_contract", view)

    def test_narrative_does_not_change_the_rendered_verdict(self):
        _status, _message, result = self.interpret(wrapper(result=result_json(
            recommendation="revise",
            report_markdown="Final recommendation: commit_contract")))
        self.assertIn("- Recommendation: revise", ccr.render(result))


class TheTwoRunners(unittest.TestCase):
    """They differ by one command, and by nothing else."""

    def test_docker_runs_in_the_clone_and_host_does_not(self):
        clone = Path("C:/nscrev/cj-example")
        docker_cmd, docker_cwd = ccr.command("docker", "claude-sonnet-5", "60", clone)
        self.assertEqual(docker_cwd, clone)
        self.assertEqual(docker_cmd[0], "docker")
        self.assertIn("--output-format", docker_cmd)

    def test_both_request_json_output_and_read_only_tools(self):
        docker_cmd, _ = ccr.command("docker", "m", "60", Path("C:/tmp"))
        for forbidden in ("Edit", "Write", "NotebookEdit"):
            self.assertNotIn(forbidden, docker_cmd)
        self.assertIn("json", docker_cmd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
