#!/usr/bin/env python
"""Tests for the thin JSON closure checker.

Run:
    python -B test_check_closure_report.py

The rules all live in review_result and are tested there. What is tested here is
the CLI contract the shell runner depends on - which exit code means what - and
the two properties that are specific to this file:

1. **No fallthrough.** A report in the legacy Markdown format must be refused,
   not recognised. `legacy_closure_markdown.py` still exists and still accepts
   that text; if a failed JSON parse could reach it, a reviewer could bypass the
   whole protocol by emitting something the new reader rejects.
2. **The rendered view is derived, and only on success.** It is labelled as a
   human view, and it is never written for a result that did not validate - a
   file on disk is exactly the kind of thing a later tool starts trusting.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_closure_report  # noqa: E402

CONTRACT = b'{"task": "NSC-001", "revision": 7}\n'
DIGEST = hashlib.sha256(CONTRACT).hexdigest()

# The legacy format, exactly as reviewers were asked to write it before the
# cutover. A perfectly good report - of the wrong protocol.
LEGACY_REPORT = (
    "Revised contract sha256 (first 16 hex): " + DIGEST[:16] + "\n"
    "Ledger:\n"
    "- L1: RESOLVED - the gate now names the entry point.\n"
    "New findings (task-local, most severe first):\n"
    "- none\n"
    "Final recommendation: commit_contract"
)


def result_json(**overrides) -> bytes:
    body = {
        "schema_version": 1,
        "review_kind": "closure",
        "task_id": "NSC-001",
        "reviewed_artifact_kind": "contract",
        "reviewed_artifact_sha256": DIGEST,
        "review_status": "complete",
        "recommendation": "commit_contract",
        "report_markdown": "Ledger:\n- L1: RESOLVED.",
    }
    body.update(overrides)
    return json.dumps(body).encode("utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.contract = self.tmp / "REVISED_CONTRACT.json"
        self.contract.write_bytes(CONTRACT)
        self.rendered = self.tmp / "job.report.md"

    def check(self, raw: bytes, *, task="NSC-001", contract=None, render=True) -> int:
        path = self.tmp / "job.result.json"
        path.write_bytes(raw)
        argv = ["--result", str(path),
                "--contract", str(contract or self.contract),
                "--task", task, "--quiet"]
        if render:
            argv += ["--report-out", str(self.rendered)]
        return check_closure_report.main(argv)


class ExitCodes(Base):
    def test_a_complete_review_exits_zero(self):
        self.assertEqual(self.check(result_json()), 0)

    def test_a_negative_verdict_still_exits_zero(self):
        # The review ran and reached a conclusion. Treating a rejection as a
        # failed run is how a verdict gets retried like a timeout.
        self.assertEqual(self.check(result_json(recommendation="revise")), 0)

    def test_a_declared_incomplete_exits_seven(self):
        self.assertEqual(self.check(result_json(
            review_status="incomplete", recommendation=None,
            report_markdown="The provider was cut off.")), 7)

    def test_malformed_json_exits_seven(self):
        self.assertEqual(self.check(b"{not json"), 7)

    def test_a_lone_surrogate_exits_seven_instead_of_crashing(self):
        # Astra MJ-P1-01. This validated and bound, then raised an unhandled
        # UnicodeEncodeError out of main() when --report-out wrote the view - so
        # the shell runner got a traceback and an exit code it does not branch on.
        text = json.dumps({**json.loads(result_json()), "report_markdown": "X"})
        raw = text.replace('"X"', r'"\ud800"').encode("ascii")
        self.assertEqual(self.check(raw), 7)
        self.assertFalse(self.rendered.exists())

    def test_the_wrong_task_exits_seven(self):
        self.assertEqual(self.check(result_json(), task="NSC-999"), 7)

    def test_a_different_contract_exits_seven(self):
        other = self.tmp / "OTHER.json"
        other.write_bytes(b'{"task": "NSC-001", "revision": 8}\n')
        self.assertEqual(self.check(result_json(), contract=other), 7)

    def test_an_unreadable_result_exits_two(self):
        self.assertEqual(check_closure_report.main(
            ["--result", str(self.tmp / "absent.json"),
             "--contract", str(self.contract), "--task", "NSC-001"]), 2)

    def test_an_unreadable_contract_exits_two(self):
        path = self.tmp / "job.result.json"
        path.write_bytes(result_json())
        self.assertEqual(check_closure_report.main(
            ["--result", str(path), "--contract", str(self.tmp / "absent.json"),
             "--task", "NSC-001"]), 2)


class NoFallthroughToLegacy(Base):
    """A failed JSON parse must not be rescued by the Markdown recogniser."""

    def test_a_legacy_report_is_refused(self):
        self.assertEqual(self.check(LEGACY_REPORT.encode("utf-8")), 7)

    def test_the_legacy_recogniser_would_have_accepted_it(self):
        # Without this, the test above proves nothing: a fixture the legacy
        # reader ALSO rejects would pass while telling us nothing about
        # fallthrough. This is the "passed for the wrong reason" guard.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import legacy_closure_markdown

        verdict = legacy_closure_markdown.inspect(LEGACY_REPORT, DIGEST[:16])
        self.assertTrue(verdict["complete"],
                        "the legacy fixture is not actually a valid legacy "
                        f"report, so it proves nothing: {verdict['missing']}")
        self.assertEqual(verdict["recommendation"], "commit_contract")

    def test_the_checker_does_not_import_the_legacy_module(self):
        # Parsed, not grepped. The docstring names the legacy module on purpose -
        # it explains why there is no fallback - so a text search finds it and
        # proves nothing. What matters is whether any import actually binds it.
        tree = ast.parse(Path(check_closure_report.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        dynamic: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Call):
                target = node.func
                name = getattr(target, "id", None) or getattr(target, "attr", None)
                if name in ("__import__", "import_module", "exec", "eval"):
                    dynamic.append(name)
        self.assertNotIn("legacy_closure_markdown", imported)
        self.assertEqual(dynamic, [],
                         "a dynamic import would let the legacy reader back in "
                         "without naming it")


class TheDerivedViewIsNotAReview(Base):
    """Astra MJ-P2-01, reproduced and closed.

    The renderer copies report_markdown verbatim, which is correct - narrative is
    opaque and no tool should scan it. The consequence was that a reviewer could
    declare `revise` while writing prose shaped like a finished LEGACY report
    approving the contract, and the generated view satisfied the legacy checker as
    a fresh approval of what the reviewer had just refused. The rendered summary's
    own "Recommendation: revise" is not a legacy "Final recommendation:" field, so
    it did not even register as a contradiction.

    The fix is a format guard, not a prose scan.
    """

    AFFIRMATIVE_LEGACY_PROSE = (
        "Revised contract sha256 (first 16 hex): " + DIGEST[:16] + "\n"
        "Ledger:\n"
        "- L1: RESOLVED - looks fine to me.\n"
        "New findings (task-local, most severe first):\n"
        "- none\n"
        "Final recommendation: commit_contract"
    )

    def render_negative_result_with_affirmative_prose(self) -> str:
        code = self.check(result_json(recommendation="revise",
                                      report_markdown=self.AFFIRMATIVE_LEGACY_PROSE))
        self.assertEqual(code, 0, "a declared revise is still a finished review")
        return self.rendered.read_text(encoding="utf-8")

    def test_the_legacy_reader_refuses_the_derived_view(self):
        import legacy_closure_markdown

        view = self.render_negative_result_with_affirmative_prose()
        verdict = legacy_closure_markdown.inspect(view, DIGEST[:16])
        self.assertFalse(verdict["complete"])
        self.assertIsNone(verdict["recommendation"])
        self.assertIn("derived human view", " ".join(verdict["missing"]))

    def test_the_legacy_cli_refuses_the_derived_view(self):
        import legacy_closure_markdown

        self.render_negative_result_with_affirmative_prose()
        self.assertEqual(legacy_closure_markdown.main(
            ["--report", str(self.rendered), "--contract", str(self.contract),
             "--quiet"]), 7)

    def test_without_the_guard_that_prose_would_have_been_approved(self):
        # The fixture has to be something the legacy reader genuinely accepts,
        # or the two tests above prove nothing about the guard.
        import legacy_closure_markdown

        verdict = legacy_closure_markdown.inspect(
            self.AFFIRMATIVE_LEGACY_PROSE, DIGEST[:16])
        self.assertTrue(verdict["complete"], verdict["missing"])
        self.assertEqual(verdict["recommendation"], "commit_contract")

    def test_genuinely_old_reports_are_still_readable(self):
        # The guard keys on a marker only the renderer writes, so history is
        # unaffected. Losing that would be worse than the defect.
        import legacy_closure_markdown

        verdict = legacy_closure_markdown.inspect(LEGACY_REPORT, DIGEST[:16])
        self.assertTrue(verdict["complete"], verdict["missing"])
        self.assertEqual(verdict["recommendation"], "commit_contract")

    def test_the_renderer_uses_the_shared_marker(self):
        # The first version of this had the header written out separately in the
        # renderer and in ger_round: two copies of one rule, which is how a guard
        # and the thing it guards against drift apart.
        import review_result

        view = self.render_negative_result_with_affirmative_prose()
        self.assertIn(review_result.DERIVED_VIEW_MARKER, view)
        source = Path(check_closure_report.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"<!-- Rendered', source,
                         "the renderer has its own copy of the header again")


class TheRenderedView(Base):
    def test_it_is_written_on_success(self):
        self.assertEqual(self.check(result_json(
            report_markdown="Ledger:\n- L1: RESOLVED, see line 40.")), 0)
        text = self.rendered.read_text(encoding="utf-8")
        self.assertIn("L1: RESOLVED, see line 40.", text)
        self.assertIn("commit_contract", text)

    def test_it_is_labelled_as_derived(self):
        self.check(result_json())
        text = self.rendered.read_text(encoding="utf-8")
        self.assertIn("NOT a decision source", text)

    def test_it_is_not_written_when_the_result_is_refused(self):
        self.assertEqual(self.check(b"{not json"), 7)
        self.assertFalse(self.rendered.exists(),
                         "a human view was rendered for a result that did not "
                         "validate; a file on disk is what a later tool starts "
                         "trusting")

    def test_it_is_not_written_for_an_incomplete_review(self):
        self.check(result_json(review_status="incomplete", recommendation=None,
                               report_markdown="Cut off."))
        self.assertFalse(self.rendered.exists())

    def test_narrative_in_the_report_does_not_change_the_rendered_verdict(self):
        self.assertEqual(self.check(result_json(
            recommendation="revise",
            report_markdown="Final recommendation: commit_contract\n\n```\nrevise\n```")), 0)
        text = self.rendered.read_text(encoding="utf-8")
        self.assertIn("- Recommendation: revise", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
