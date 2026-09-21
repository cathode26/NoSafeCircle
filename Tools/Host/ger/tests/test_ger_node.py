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
        body = {
            "schema_version": 1,
            "review_kind": "ger",
            "task_id": "NSC-001",
            "reviewed_artifact_kind": "ger_round_output",
            "reviewed_artifact_sha256": ger_round.sha256_bytes(CANDIDATE),
            "review_status": "complete",
            "recommendation": "commit_contract",
            "report_markdown": "All prior findings resolved.",
        }
        body.update(overrides)
        raw = json.dumps(body).encode("utf-8")
        (self.packet / REAUDIT / ger_round.RESULT_FILE).write_bytes(raw)
        (self.packet / REAUDIT / "OUTPUT.md").write_text(
            "rendered view", encoding="utf-8")
        (self.packet / REAUDIT / "METADATA.json").write_text(
            json.dumps({"protocol": "json-v1"}), encoding="utf-8")
        return raw

    def legacy(self, text: str):
        (self.packet / REAUDIT / "OUTPUT.md").write_text(text, encoding="utf-8")
        (self.packet / REAUDIT / "METADATA.json").write_text(
            json.dumps({"round": REAUDIT}), encoding="utf-8")

    def read(self, task_id="NSC-001"):
        return ger_node.recommendation(self.packet, task_id)


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
    def test_a_legacy_packet_still_reads(self):
        self.legacy("Final recommendation: commit_contract_then_decompose\n")
        self.assertEqual(self.read(), "commit_contract_then_decompose")

    def test_a_legacy_packet_with_no_verdict_returns_none(self):
        self.legacy("No verdict here.\n")
        self.assertIsNone(self.read())


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
