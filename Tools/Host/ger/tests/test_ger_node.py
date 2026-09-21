#!/usr/bin/env python
"""Tests for ger_node's reading of the re-audit verdict.

Run:
    python -B test_ger_node.py

`recommendation` used to grep `04-claude-reaudit/OUTPUT.md` for the earliest
verdict word after the last "final recommendation" heading. Under the JSON
protocol that file is the DERIVED human view, which embeds report_markdown
verbatim - so the old reader would have taken a verdict word out of the
reviewer's own reasoning and outranked the declared decision with it.

The three branches that matter, and the line between them:

  - a v2 packet is read through the shared loader;
  - a LEGACY packet may use the old grep, because packets written before the
    cutover still have that shape;
  - a v2 packet that does NOT validate returns None and must not reach the grep.
    That last one is the whole rule: if it fell through, a reviewer could bypass
    the protocol by emitting something the loader rejects.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ger_node  # noqa: E402
import ger_fixtures as fixtures  # noqa: E402
import ger_round  # noqa: E402

REAUDIT = "04-claude-reaudit"
REVIEWED = "03-codex-refine"
CANDIDATE = b"The refined candidate.\n"


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.packet = Path(self._tmp.name) / "packet"
        (self.packet / REVIEWED).mkdir(parents=True)
        (self.packet / REVIEWED / "OUTPUT.md").write_bytes(CANDIDATE)
        (self.packet / REAUDIT).mkdir(parents=True)
        self.logged: list[str] = []
        self._real_log = ger_node.log
        ger_node.log = self.logged.append
        self.addCleanup(lambda: setattr(ger_node, "log", self._real_log))

    def v2(self, **overrides):
        """A realistic record, not a stub: hashes and provider evidence included."""
        return fixtures.decision(self.packet, fixtures.result_bytes(**overrides))

    def legacy(self, text: str):
        fixtures.legacy(self.packet, text)

    def read(self, task_id="NSC-001", allow_legacy=False):
        return ger_node.recommendation(self.packet, task_id, allow_legacy=allow_legacy)


class V2Packets(Base):
    def test_the_declared_verdict_is_returned(self):
        self.v2()
        self.assertEqual(self.read(), "commit_contract")

    def test_reasoning_that_names_other_verdicts_does_not_win(self):
        # The exact shape the old grep got wrong: needs_design appears earlier in
        # the text than the real verdict, and sorted-by-length put it first.
        self.v2(recommendation="commit_contract",
                report_markdown="I weighed needs_design and blocked_not_design "
                                "before settling.")
        self.assertEqual(self.read(), "commit_contract")

    def test_an_incomplete_review_has_no_recommendation(self):
        self.v2(review_status="incomplete", recommendation=None,
                report_markdown="Ran out of context.")
        self.assertIsNone(self.read())


class TheLegacyBranch(Base):
    """Reading an old packet is a caller's DECISION, not an inference."""

    def test_a_legacy_packet_reads_when_the_caller_says_so(self):
        self.legacy("Final recommendation: commit_contract_then_decompose\n")
        self.assertEqual(self.read(allow_legacy=True),
                         "commit_contract_then_decompose")

    def test_a_legacy_packet_with_no_verdict_returns_none(self):
        self.legacy("No verdict here.\n")
        self.assertIsNone(self.read(allow_legacy=True))

    def test_a_legacy_packet_is_refused_by_default(self):
        # Astra MJ-P2-02: historical parsing must be selected explicitly by host
        # context. A packet that simply declares no protocol is not evidence that
        # reading its Markdown is safe.
        self.legacy("Final recommendation: commit_contract\n")
        self.assertIsNone(self.read())
        self.assertTrue(any("no readable decision" in line for line in self.logged))


class NoFallthrough(Base):
    """A v2 packet that does not validate must not reach the legacy grep."""

    def test_unparseable_result_does_not_fall_through(self):
        self.v2()
        (self.packet / REAUDIT / ger_round.RESULT_FILE).write_bytes(b"not json")
        # The view is written to look exactly like a legacy report, so if the
        # grep were reachable it would return a verdict and this would fail.
        (self.packet / REAUDIT / "OUTPUT.md").write_text(
            "Final recommendation: commit_contract\n", encoding="utf-8")
        self.assertIsNone(self.read())
        self.assertTrue(any("no readable decision" in line for line in self.logged))

    def test_a_review_of_edited_bytes_does_not_fall_through(self):
        self.v2()
        (self.packet / REVIEWED / "OUTPUT.md").write_bytes(b"edited since.\n")
        (self.packet / REAUDIT / "OUTPUT.md").write_text(
            "Final recommendation: commit_contract\n", encoding="utf-8")
        self.assertIsNone(self.read())

    def test_the_wrong_task_does_not_fall_through(self):
        self.v2()
        (self.packet / REAUDIT / "OUTPUT.md").write_text(
            "Final recommendation: commit_contract\n", encoding="utf-8")
        self.assertIsNone(self.read(task_id="NSC-999"))

    def test_the_legacy_grep_would_have_accepted_those(self):
        # Without this, the three tests above prove nothing: if the fixture text
        # were not something the grep accepts, they would pass while telling us
        # nothing about fallthrough.
        (self.packet / REAUDIT / "OUTPUT.md").write_text(
            "Final recommendation: commit_contract\n", encoding="utf-8")
        self.assertEqual(ger_node.legacy_recommendation(self.packet),
                         "commit_contract")


class TheRecordMustHoldUp(Base):
    """Astra MJ-P2-03: the reader now revalidates the record, not just the JSON."""

    def test_an_edited_result_with_a_stale_hash_is_refused(self):
        raw = self.v2(recommendation="needs_design")
        tampered = json.loads(raw.decode("utf-8"))
        tampered["recommendation"] = "commit_contract"
        (self.packet / REAUDIT / ger_round.RESULT_FILE).write_bytes(
            json.dumps(tampered).encode("utf-8"))
        self.assertIsNone(self.read())

    def test_a_round_that_recorded_provider_failure_is_refused(self):
        for weakened in ({"exit_code": 9}, {"is_error": True}, {"session_id": None}):
            with self.subTest(weakened=weakened):
                fixtures.decision(self.packet, **weakened)
                self.assertIsNone(self.read())

    def test_an_unknown_protocol_is_refused(self):
        fixtures.decision(self.packet, protocol="json-v9")
        self.assertIsNone(self.read())

    def test_a_json_v1_record_with_no_result_file_is_refused(self):
        self.v2()
        (self.packet / REAUDIT / ger_round.RESULT_FILE).unlink()
        (self.packet / REAUDIT / "OUTPUT.md").write_text(
            "Final recommendation: commit_contract\n", encoding="utf-8")
        # Not legacy - incomplete. Even with allow_legacy, a declared json-v1
        # record missing its result is a broken record, not an old one.
        self.assertIsNone(self.read())
        self.assertIsNone(self.read(allow_legacy=True))

    def test_an_imported_record_must_name_its_source(self):
        fixtures.decision(self.packet, provider_evidence="imported",
                          exit_code=None, session_id=None)
        self.assertIsNone(self.read())
        fixtures.decision(self.packet, provider_evidence="imported",
                          imported_from="round-08 report from the GER owner",
                          exit_code=None, session_id=None)
        self.assertEqual(self.read(), "commit_contract")


class RetryEligibility(Base):
    """Astra MJ-P2-04, path 3: reviewer prose must not buy another provider call."""

    RATE_LIMIT_PROSE = ("The service returned a rate limit error during my "
                        "investigation, which I note as a finding.")

    def failed(self, **record):
        directory = self.packet / REAUDIT
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "FAILED.json").write_text(json.dumps(record), encoding="utf-8")
        return directory

    def test_a_protocol_failure_is_never_transient(self):
        # exit_code 1, deliberately. Fable found this case written with
        # exit_code 0, where the SECOND gate ("the provider call succeeded")
        # refuses it on its own - so the test named for the protocol gate never
        # exercised the protocol gate, and a mutant of it survived. A failed
        # process plus a protocol label isolates the rule under test.
        directory = self.failed(kind="protocol", reason=self.RATE_LIMIT_PROSE,
                                metadata={"exit_code": 1, "is_error": True})
        self.assertFalse(ger_node.transient_failure(directory))

    def test_the_same_failure_without_the_protocol_label_is_transient(self):
        # The control that makes the case above mean something: identical
        # evidence, no `kind`, and the rate-limit prose now qualifies.
        directory = self.failed(reason=self.RATE_LIMIT_PROSE,
                                metadata={"exit_code": 1, "is_error": True})
        self.assertTrue(ger_node.transient_failure(directory))

    def test_a_successful_provider_call_is_never_transient(self):
        # No `kind`, so this is the general rule rather than the label: the
        # process exited 0 and reported no error, so the transport worked and
        # whatever failed afterwards will fail again.
        directory = self.failed(reason=self.RATE_LIMIT_PROSE,
                                metadata={"exit_code": 0, "is_error": None})
        self.assertFalse(ger_node.transient_failure(directory))

    def test_a_real_provider_refusal_is_still_transient(self):
        # The gates must not swallow the case retrying exists for.
        directory = self.failed(reason="exit code 1", metadata={"exit_code": 1})
        (directory / "STDERR.log").write_text("HTTP 429 rate limit exceeded",
                                              encoding="utf-8")
        self.assertTrue(ger_node.transient_failure(directory),
                        "a genuine provider refusal must still be retryable")

    def test_prose_alone_no_longer_qualifies(self):
        # The exact shape: a round that failed with a non-zero exit but whose
        # only rate-limit wording is the reviewer's own narrative. Kept
        # retryable, because the provider call did fail - what changed is that a
        # SUCCESSFUL call can no longer be talked into a retry.
        directory = self.failed(reason="exit code 2", metadata={"exit_code": 2})
        (directory / "RAW_RESPONSE.json").write_text(
            json.dumps({"result": self.RATE_LIMIT_PROSE}), encoding="utf-8")
        self.assertTrue(ger_node.transient_failure(directory))
        # ...and the same prose with a successful call is not.
        directory = self.failed(reason="unreadable decision",
                                metadata={"exit_code": 0})
        self.assertFalse(ger_node.transient_failure(directory))


if __name__ == "__main__":
    unittest.main(verbosity=2)
