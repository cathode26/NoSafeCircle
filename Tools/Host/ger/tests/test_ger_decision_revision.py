#!/usr/bin/env python
"""Tests for the imported round-08 re-check.

Run:
    python -B test_ger_decision_revision.py

Round 08 is the one decision round no provider runs here: the GER owner hands
over a fresh reviewer's result. That makes it the place where fabricated evidence
would be easiest and least visible, so the record says `provider_evidence:
imported` and names its source, and ger_round.check_record refuses an import that
does not.

The old recheck accepted any report containing the revised contract's first 16
hex characters somewhere in its prose, then grepped it for a verdict. Both halves
are gone: the result declares what it reviewed and the host binds it to the exact
REVISED_CONTRACT.json bytes.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import ger_decision_revision as gdr  # noqa: E402
import ger_round  # noqa: E402
import review_result  # noqa: E402

TASK = "NSC-001"
BUILD = gdr.BUILD
RECHECK = gdr.RECHECK
REVISED = b'{"id": "NSC-001", "contract_revision": 2}\n'


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.packet = self.tmp / "packet"
        build = self.packet / BUILD
        build.mkdir(parents=True)

        output = b"# NSC-001 owner decision revision\n"
        (build / "OUTPUT.md").write_bytes(output)
        (build / "REVISED_CONTRACT.json").write_bytes(REVISED)
        (build / "METADATA.json").write_text(json.dumps({
            "round": BUILD, "task_id": TASK,
            "output_sha256": gdr.sha256(output),
            "revised_contract_sha256": gdr.sha256(REVISED),
        }), encoding="utf-8")

        # repository_head shells out to git in apply_contract.REPO; the round
        # records it but nothing here depends on its value.
        self._real_head = gdr.repository_head
        gdr.repository_head = lambda: "0" * 40
        self.addCleanup(lambda: setattr(gdr, "repository_head", self._real_head))

    def result(self, **overrides) -> bytes:
        body = {
            "schema_version": 1,
            "review_kind": "ger",
            "task_id": TASK,
            "reviewed_artifact_kind": "ger_round_output",
            "reviewed_artifact_sha256": gdr.sha256(REVISED),
            "review_status": "complete",
            "recommendation": "commit_contract",
            "report_markdown": "The recorded decisions are applied.",
        }
        body.update(overrides)
        return json.dumps(body).encode("utf-8")

    def recheck(self, raw: bytes, *, legacy=False) -> int:
        path = self.tmp / "reviewer.report"
        path.write_bytes(raw)
        return gdr.recheck(argparse.Namespace(
            packet=self.packet, report=path, reviewer="fresh Claude", legacy=legacy))

    @property
    def round_dir(self) -> Path:
        return self.packet / RECHECK

    def metadata(self) -> dict:
        return json.loads((self.round_dir / "METADATA.json").read_text(encoding="utf-8"))


class TheImportedResult(Base):
    def test_a_bound_result_is_recorded_as_an_import(self):
        self.assertEqual(self.recheck(self.result()), 0)
        meta = self.metadata()
        self.assertEqual(meta["protocol"], "json-v1")
        self.assertEqual(meta["provider_evidence"], "imported")
        self.assertTrue(meta["imported_from"].endswith("reviewer.report"))
        self.assertEqual(meta["recommendation"], "commit_contract")
        self.assertEqual(meta["reviewed"], f"{BUILD}/REVISED_CONTRACT.json")
        self.assertEqual(meta["result_sha256"], gdr.sha256(self.result()))

    def test_the_result_is_kept_verbatim_and_the_view_is_derived(self):
        raw = self.result(report_markdown="Ledger:\n- L1: RESOLVED, line 40.")
        self.recheck(raw)
        self.assertEqual((self.round_dir / ger_round.RESULT_FILE).read_bytes(), raw)
        view = (self.round_dir / "OUTPUT.md").read_text(encoding="utf-8")
        self.assertIn(review_result.DERIVED_VIEW_MARKER, view)
        self.assertIn("L1: RESOLVED, line 40.", view)

    def test_the_recorded_import_is_readable_by_the_shared_reader(self):
        # The contract this producer must meet: check_record accepts an import
        # that names its source, without provider exit or session evidence.
        self.recheck(self.result(recommendation="commit_contract_then_decompose"))
        decision = ger_round.read_decision(self.packet, RECHECK, TASK)
        self.assertEqual(decision.recommendation, "commit_contract_then_decompose")

    def test_a_review_of_different_contract_bytes_is_refused(self):
        with self.assertRaises(SystemExit):
            self.recheck(self.result(reviewed_artifact_sha256="c" * 64))
        self.assertTrue((self.round_dir / "FAILED.json").is_file())
        self.assertFalse((self.round_dir / "METADATA.json").exists())

    def test_a_declared_incomplete_is_refused(self):
        with self.assertRaises(SystemExit):
            self.recheck(self.result(review_status="incomplete", recommendation=None,
                                     report_markdown="Could not finish."))
        self.assertFalse((self.round_dir / "METADATA.json").exists())

    def test_a_closure_verdict_is_not_a_ger_verdict(self):
        with self.assertRaises(SystemExit):
            self.recheck(self.result(recommendation="revise"))

    def test_prose_is_refused_without_the_legacy_flag(self):
        prose = ("Reviewed " + gdr.sha256(REVISED)[:16] +
                 "\n\nFinal recommendation: commit_contract\n").encode("utf-8")
        with self.assertRaises(SystemExit):
            self.recheck(prose)
        self.assertFalse((self.round_dir / "METADATA.json").exists())

    def test_the_round_is_reserved(self):
        self.recheck(self.result())
        with self.assertRaises(Exception):
            self.recheck(self.result())


class TheLegacyFlag(Base):
    def test_an_old_report_reads_when_declared(self):
        prose = ("Reviewed " + gdr.sha256(REVISED)[:16] +
                 "\n\nFinal recommendation: commit_contract\n").encode("utf-8")
        self.assertEqual(self.recheck(prose, legacy=True), 0)
        meta = self.metadata()
        self.assertEqual(meta["protocol"], "legacy-markdown")
        self.assertEqual(meta["recommendation"], "commit_contract")
        self.assertIsNone(meta["result_sha256"])
        # Still labelled an import: it was handed over, not produced here.
        self.assertEqual(meta["provider_evidence"], "imported")

    def test_an_old_report_without_the_identity_is_refused(self):
        with self.assertRaises(SystemExit):
            self.recheck(b"Final recommendation: commit_contract\n", legacy=True)

    def test_the_legacy_flag_does_not_accept_a_json_result(self):
        # It selects the old READER; it is not a bypass that accepts anything.
        with self.assertRaises(SystemExit):
            self.recheck(self.result(), legacy=True)

    def test_a_bom_prefixed_result_does_not_become_a_legacy_verdict(self):
        # Astra MJ-P2-06 at the importer. The refusal used to depend on
        # json.loads SUCCEEDING, so a result carrying the allowed single BOM
        # failed the parse and fell through to the grep - which found
        # `commit_contract` inside `"recommendation": "commit_contract"` and
        # published an incomplete review as a complete legacy one.
        bom = chr(0xFEFF).encode("utf-8") + self.result(
            review_status="incomplete", recommendation=None,
            report_markdown="Final recommendation: commit_contract")
        with self.assertRaises(SystemExit):
            self.recheck(bom, legacy=True)
        self.assertFalse((self.round_dir / "METADATA.json").exists())

    def test_json_with_trailing_text_does_not_become_a_legacy_verdict(self):
        trailing = self.result() + b"\n\nFinal recommendation: commit_contract\n"
        with self.assertRaises(SystemExit):
            self.recheck(trailing, legacy=True)
        self.assertFalse((self.round_dir / "METADATA.json").exists())

    def test_malformed_json_shaped_text_does_not_become_a_legacy_verdict(self):
        broken = (b'{"schema_version": 1, "recommendation": "commit_contract"'
                  + gdr.sha256(REVISED)[:16].encode("ascii"))
        with self.assertRaises(SystemExit):
            self.recheck(broken, legacy=True)

    def test_a_legacy_import_can_be_read_back(self):
        # Astra MJ-P2-08: the importer writes protocol=legacy-markdown, and
        # read_decision accepted historical mode only for an ABSENT protocol, so
        # a genuine old report imported with --legacy was then refused even when
        # the reader was explicitly told to allow legacy. Writer and reader must
        # agree about what historical means.
        prose = ("Reviewed " + gdr.sha256(REVISED)[:16] +
                 "\n\nFinal recommendation: commit_contract\n").encode("utf-8")
        self.assertEqual(self.recheck(prose, legacy=True), 0)
        with self.assertRaises(ger_round.LegacyPacket):
            ger_round.read_decision(self.packet, RECHECK, TASK, allow_legacy=True)

    def test_a_legacy_import_is_still_refused_without_the_readers_permission(self):
        prose = ("Reviewed " + gdr.sha256(REVISED)[:16] +
                 "\n\nFinal recommendation: commit_contract\n").encode("utf-8")
        self.recheck(prose, legacy=True)
        with self.assertRaises(ValueError) as caught:
            ger_round.read_decision(self.packet, RECHECK, TASK)
        self.assertNotIsInstance(caught.exception, ger_round.LegacyPacket)


if __name__ == "__main__":
    unittest.main(verbosity=2)
