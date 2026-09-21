#!/usr/bin/env python
"""Tests for check_closure_report.py.

Three rounds of findings are pinned here, and each round found the previous
round's fix too narrow. That pattern is the reason AstraRound2Counterexamples
exists as a class rather than as seven scattered cases.

Main-Commit-Review 20260920-180652, finding 2: a fresh, non-empty report saying
"I could not review this task. Please retry later." passed every generic check
and the closure workflow called it a success.

Astra's release review of 17cf1f4c5, finding 1 (BLOCKING): the first fix asked
only whether the markers were present, which is a much weaker question. It
picked the first of two contradictory recommendations, accepted a refusal placed
after a well-formed footer, and accepted ANY 16 hex characters as the contract
identity - so a review of a different revision read as a clean pass.

Run:  python -B test_check_closure_report.py
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_closure_report import (  # noqa: E402
    RECOMMENDATION, contract_sha16, inspect, main,
)

SHA = "0123456789abcdef"
GOOD_TAIL = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
             "\n"
             "Final recommendation: commit_contract\n")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def report(self, text: str) -> Path:
        path = self.tmp / "job.report.md"
        path.write_text(text, encoding="utf-8")
        return path

    def contract(self, data: bytes = b'{"task": "NSC-001"}') -> Path:
        path = self.tmp / "REVISED_CONTRACT.json"
        path.write_bytes(data)
        return path


class TheDeclinedReview(Base):
    """Main-Commit-Review 20260920-180652, finding 2."""

    def test_a_polite_refusal_is_not_a_completed_review(self):
        result = inspect("I could not review this task. Please retry later.\n")
        self.assertFalse(result["complete"])
        self.assertIn("no contract identity (sha256 first 16 hex)", result["missing"])
        self.assertIn("no final recommendation", result["missing"])

    def test_it_exits_7_rather_than_0(self):
        path = self.report("I could not review this task. Please retry later.\n")
        self.assertEqual(main(["--report", str(path)]), 7)

    def test_prose_about_a_recommendation_is_not_a_recommendation(self):
        result = inspect("I would normally give a Final recommendation here, but "
                         "the clone was empty.\n")
        self.assertFalse(result["complete"])


class OneVerdictOrNone(Base):
    """Astra finding 1a: .search took the first of two contradictory verdicts."""

    def test_two_different_recommendations_are_a_contradiction_not_a_verdict(self):
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: commit_contract\n"
                "On reflection, Final recommendation: revise\n")
        result = inspect(text)
        self.assertFalse(result["complete"], "a contradiction must not resolve to one side")
        self.assertIn("contradictory", " ".join(result["missing"]))
        self.assertIsNone(result["recommendation"])

    def test_the_first_one_is_not_silently_chosen(self):
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: commit_contract\n"
                "Final recommendation: revise\n")
        self.assertNotEqual(inspect(text)["recommendation"], "commit_contract")

    def test_the_same_verdict_stated_twice_is_still_refused(self):
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: revise\n"
                "Final recommendation: revise\n")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("once", " ".join(result["missing"]))

    def test_two_different_contract_identities_are_refused(self):
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Revised contract sha256 (first 16 hex): fedcba9876543210\n"
                "Final recommendation: revise\n")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("different contract identities", " ".join(result["missing"]))


class TheVerdictMustBeTheEnd(Base):
    """Astra round 1, finding 1b: a refusal after a well-formed footer passed.

    The round-1 fix allowed the verdict anywhere in the last three non-empty
    lines, so that a short sign-off would still pass. Round 2 found a one-line
    retraction sitting in that same window. The window is gone: the verdict is
    the last line or it is not the verdict.
    """

    def test_a_refusal_after_the_footer_is_not_a_completed_review(self):
        text = (GOOD_TAIL
                + "\nActually, I could not review this task. Please retry later.\n"
                + "There was no usable clone, so none of the above was checked.\n"
                + "Disregard the recommendation above.\n"
                + "This report should not be acted on.\n"
                + "Please re-run the job.\n")
        result = inspect(text)
        self.assertFalse(result["complete"], "trailing text walked the verdict back")
        self.assertIn("last line", " ".join(result["missing"]))

    def test_an_ordinary_report_ending_in_its_footer_is_fine(self):
        self.assertTrue(inspect("...the review...\n\n" + GOOD_TAIL)["complete"])

    def test_even_a_harmless_sign_off_after_the_footer_is_refused(self):
        """Round 1 tolerated this, and that tolerance was the defect.

        A checker reading text cannot tell a courtesy from a retraction - both
        are one short line after a well-formed footer. Round 2 walked in
        through exactly this allowance, so the allowance goes. The cost is
        real and accepted: a report signed off politely is refused, and the
        reviewer is told to end at the verdict.
        """
        result = inspect("...\n" + GOOD_TAIL + "\nReviewed by Astra.\n")
        self.assertFalse(result["complete"])
        self.assertIn("Reviewed by Astra.", " ".join(result["missing"]),
                      "the refusal must quote what it found after the verdict")


class TheIdentityMustBeTheContractUnderReview(Base):
    """Astra finding 1c: any 16 hex characters passed, so a review of the wrong
    revision read as a clean pass. This is the one that matters."""

    def test_a_report_about_different_bytes_is_refused(self):
        data = b'{"task": "NSC-001", "revision": 7}'
        real = contract_sha16(data)
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: commit_contract\n")
        result = inspect(text, expected_sha16=real)
        self.assertFalse(result["complete"])
        self.assertIn("different bytes", " ".join(result["missing"]))

    def test_the_matching_identity_passes_and_is_marked_verified(self):
        data = b'{"task": "NSC-001", "revision": 7}'
        real = contract_sha16(data)
        text = (f"Revised contract sha256 (first 16 hex): {real}\n"
                "Final recommendation: commit_contract\n")
        self.assertTrue(inspect(text, expected_sha16=real)["complete"])

    def test_the_comparison_is_case_insensitive(self):
        data = b"x"
        real = contract_sha16(data)
        text = (f"Revised contract sha256 (first 16 hex): {real.upper()}\n"
                "Final recommendation: revise\n")
        self.assertTrue(inspect(text, expected_sha16=real)["complete"])

    def test_end_to_end_through_the_contract_flag(self):
        data = b'{"task": "NSC-042"}'
        contract = self.contract(data)
        good = self.report(f"Revised contract sha256 (first 16 hex): {contract_sha16(data)}\n"
                           "Final recommendation: revise\n")
        self.assertEqual(main(["--report", str(good), "--contract", str(contract),
                               "--quiet"]), 0)
        wrong = self.report(f"Revised contract sha256 (first 16 hex): {SHA}\n"
                            "Final recommendation: revise\n")
        self.assertEqual(main(["--report", str(wrong), "--contract", str(contract)]), 7)

    def test_contract_sha16_is_the_documented_computation(self):
        data = b"some exact bytes"
        self.assertEqual(contract_sha16(data), hashlib.sha256(data).hexdigest()[:16])

    def test_an_unreadable_contract_exits_2_not_7(self):
        report = self.report(GOOD_TAIL)
        self.assertEqual(main(["--report", str(report),
                               "--contract", str(self.tmp / "absent.json")]), 2)


class ARealVerdictIsASuccess(Base):
    def test_commit_contract(self):
        self.assertTrue(inspect("...review...\n" + GOOD_TAIL)["complete"])

    def test_revise_is_a_completed_review_not_a_failed_run(self):
        text = GOOD_TAIL.replace("commit_contract", "revise")
        result = inspect(text)
        self.assertTrue(result["complete"], result["missing"])
        self.assertEqual(result["recommendation"], "revise")

    def test_revise_exits_zero(self):
        path = self.report(GOOD_TAIL.replace("commit_contract", "revise"))
        self.assertEqual(main(["--report", str(path), "--quiet"]), 0)

    def test_commit_contract_then_decompose(self):
        text = GOOD_TAIL.replace("commit_contract\n", "commit_contract_then_decompose\n")
        self.assertEqual(inspect(text)["recommendation"],
                         "commit_contract_then_decompose")

    def test_the_contract_identity_is_returned_for_binding(self):
        self.assertEqual(inspect(GOOD_TAIL)["sha16"], SHA)


class HalfFinishedReports(Base):
    def test_a_recommendation_without_a_contract_identity_is_incomplete(self):
        result = inspect("Final recommendation: commit_contract\n")
        self.assertFalse(result["complete"])

    def test_a_contract_identity_without_a_recommendation_is_incomplete(self):
        self.assertFalse(inspect(f"Revised contract sha256 (first 16 hex): {SHA}\n")["complete"])

    def test_an_invented_recommendation_is_refused_by_name(self):
        text = GOOD_TAIL.replace("commit_contract", "looks_fine_to_me")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("looks_fine_to_me", " ".join(result["missing"]))

    def test_a_short_hash_is_not_a_contract_identity(self):
        self.assertFalse(inspect(GOOD_TAIL.replace(SHA, "0123abc"))["complete"])

    def test_an_overlong_hash_is_not_a_contract_identity(self):
        """Not on Astra's list; found while making the identity exact.

        A 16-of-N match anywhere in the line succeeds on a 17-character hex
        string - the scan starts one character later and the word boundary
        lands at the end - so a mistyped identity silently bound to a contract
        nobody named.
        """
        result = inspect(GOOD_TAIL.replace(SHA, SHA + "0"))
        self.assertFalse(result["complete"])
        self.assertIn("sixteen hex characters", " ".join(result["missing"]))

    def test_an_empty_report_is_incomplete(self):
        self.assertFalse(inspect("")["complete"])


class Tolerance(Base):
    def test_markdown_emphasis_does_not_hide_the_verdict(self):
        text = (f"**Revised contract sha256 (first 16 hex):** {SHA.upper()}\n"
                "**Final recommendation:** revise\n")
        result = inspect(text)
        self.assertTrue(result["complete"], result["missing"])
        self.assertEqual(result["sha16"], SHA)
        self.assertEqual(result["recommendation"], "revise")

    def test_an_unreadable_report_exits_2_not_7(self):
        self.assertEqual(main(["--report", str(self.tmp / "absent.md")]), 2)


class AstraRound2Counterexamples(Base):
    """Astra's re-review of `08c3ff8ea`, finding 1 (BLOCKING).

    Every one of these returned complete=True, and each carries the CORRECT
    contract hash, so none of them is caught by the --contract binding.

    The root cause Astra named is the useful part: both checkers "recognise
    matching text fragments rather than establishing an unambiguous result".
    These are therefore not seven new patterns to special-case. They are seven
    shapes that a structural parse refuses without being told about any of
    them, and adding a rule per shape here would be the round-1 mistake again.
    """

    def test_a_one_line_retraction_after_the_footer_is_refused(self):
        """The case the round-1 regression missed, so it is written first.

        TheVerdictMustBeTheEnd appends FIVE lines, which pushes the verdict out
        of a three-line window - so it proves the window, not the retraction.
        One line stays inside the window and passed. A verdict that is not the
        last word is not the verdict.
        """
        text = GOOD_TAIL + "Disregard the recommendation above.\n"
        result = inspect(text)
        self.assertFalse(result["complete"], "a one-line retraction walked it back")

    def test_a_two_line_retraction_after_the_footer_is_refused(self):
        text = GOOD_TAIL + "Disregard the above.\nPlease re-run this job.\n"
        self.assertFalse(inspect(text)["complete"])

    def test_a_verdict_inside_a_fenced_block_is_an_example_not_a_verdict(self):
        """Assert the REASON, not just the refusal.

        Asserting complete is False would pass with the fence rule removed:
        the trailing line makes the verdict non-terminal, so the report is
        refused either way and the mutation survives. The claim being made
        here is that the fenced verdict was never SEEN - so the refusal must
        be "there is no verdict", never "your verdict is misplaced".
        """
        text = ("Here is the shape I was asked to produce:\n"
                "\n"
                "```\n"
                f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: commit_contract\n"
                "```\n"
                "\n"
                "I could not review this task.\n")
        result = inspect(text)
        self.assertFalse(result["complete"], "a fenced example is not a verdict")
        self.assertIn("no final recommendation", result["missing"])
        self.assertIn("no contract identity (sha256 first 16 hex)", result["missing"])

    def test_a_verdict_inside_a_block_quote_is_an_example_not_a_verdict(self):
        """Same claim, same reason: quoted lines are shown, not stated."""
        text = ("The template asks for:\n"
                f"> Revised contract sha256 (first 16 hex): {SHA}\n"
                "> Final recommendation: commit_contract\n"
                "\n"
                "I could not review this task.\n")
        result = inspect(text)
        self.assertFalse(result["complete"], "a quoted example is not a verdict")
        self.assertIn("no final recommendation", result["missing"])
        self.assertIn("no contract identity (sha256 first 16 hex)", result["missing"])

    def test_an_unclosed_fence_swallows_the_rest_and_the_review_is_refused(self):
        """A truncated report must not be completed by accident.

        Nothing closes the fence, so every later line is inside an example -
        including the footer. Refusing is the safe direction, and pinning it
        means a future tolerance for unterminated fences has to argue with a
        test.
        """
        text = ("Here is the shape I was asked to produce:\n"
                "\n"
                "```\n"
                f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: commit_contract\n")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("no final recommendation", result["missing"])

    def test_the_echoed_options_line_is_not_a_choice(self):
        """The template's own line, handed back without choosing from it."""
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: commit_contract | "
                "commit_contract_then_decompose | revise\n")
        self.assertFalse(inspect(text)["complete"], "listing options is not choosing")

    def test_a_recommendation_name_must_end_where_the_name_ends(self):
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: commit_contract2\n")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("commit_contract2", " ".join(result["missing"]),
                      "the refusal must name the value it read")

    def test_the_same_identity_stated_twice_is_refused(self):
        """Counted by occurrence, not by distinct value.

        Two lines claiming the same contract are two claims. The round-1 check
        compared a set, so it only noticed disagreement.
        """
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: revise\n")
        self.assertFalse(inspect(text)["complete"], "two identity lines are two claims")

    def test_none_of_these_are_caught_by_the_hash_binding(self):
        """Astra reproduced every counterexample with the RIGHT hash.

        Pinned so a successor does not "fix" these by tightening the binding,
        which Astra confirmed is already correct.
        """
        data = b'{"task": "NSC-001", "revision": 7}'
        real = contract_sha16(data)
        text = (f"Revised contract sha256 (first 16 hex): {real}\n"
                "Final recommendation: commit_contract\n"
                "Disregard the recommendation above.\n")
        result = inspect(text, expected_sha16=real)
        self.assertFalse(result["complete"])
        self.assertNotIn("different bytes", " ".join(result["missing"]),
                         "this must fail on structure, not on the hash")


class TheTemplateAndTheCheckerMustAgree(Base):
    """The round-2 defect had a second half: the format the reviewer is GIVEN.

    contract-closure-review-prompt.md ended with a parenthetical AFTER the
    recommendation and showed all three options ON the recommendation line, so
    a reviewer echoing it faithfully produced two of Astra's counterexamples.
    A checker cannot demand a terminal, single-valued verdict while the
    template it hands out shows neither, and nothing in the repository
    connected the two files.

    This class is that connection.
    """

    TEMPLATE = (Path(__file__).resolve().parent.parent.parent
                / "codex-jobs" / "templates" / "contract-closure-review-prompt.md")

    def final_message(self) -> str:
        text = self.TEMPLATE.read_text(encoding="utf-8")
        _, found, block = text.partition("FINAL MESSAGE")
        self.assertTrue(found, f"no FINAL MESSAGE section in {self.TEMPLATE}")
        _, _, block = block.partition("\n")
        self.assertIn("sha256", block, "the FINAL MESSAGE section lost its identity line")
        return block

    def filled(self) -> str:
        """The block a compliant reviewer would produce from it."""
        out = []
        for line in self.final_message().splitlines():
            if RECOMMENDATION.search(line):
                line = "Final recommendation: revise"
            out.append(line.replace("<16 hex characters>", SHA))
        return "\n".join(out)

    def test_the_template_is_where_this_test_looks_for_it(self):
        self.assertTrue(self.TEMPLATE.is_file(), self.TEMPLATE)

    def test_the_documented_final_message_passes_the_checker(self):
        result = inspect(self.filled())
        self.assertTrue(result["complete"],
                        "the template asks reviewers for a report this checker "
                        f"refuses: {result['missing']}")
        self.assertEqual(result["recommendation"], "revise")
        self.assertEqual(result["sha16"], SHA)

    def test_nothing_in_the_template_follows_the_recommendation(self):
        """The parenthetical that used to sit here is how round 2 got in."""
        lines = [ln for ln in self.final_message().splitlines() if ln.strip()]
        self.assertTrue(lines, "empty FINAL MESSAGE section")
        self.assertTrue(RECOMMENDATION.search(lines[-1]),
                        f"the template's last line is {lines[-1]!r}, not the verdict")

    def test_the_template_does_not_show_the_options_as_the_value(self):
        """Echoed verbatim, that line was Astra counterexample 3."""
        for line in self.final_message().splitlines():
            if RECOMMENDATION.search(line):
                self.assertNotIn("|", line,
                                 "the verdict line must not be a menu; a reviewer "
                                 "echoing it has not chosen anything")


class AstraRound3Counterexamples(Base):
    """Astra's review of `76ce3aec2`. Round 2's fix was still too narrow.

    Its root cause, for the third time running: the checker "recognizes
    selected Markdown patterns, rather than establishing whether a field
    belongs to the actual report". Round 2 excluded fenced blocks and block
    quotes - two example containers out of at least four.

    The fix does not add the missing two. It inverts the question to one with a
    closed answer: a field line is where the TEMPLATE puts one - column 0,
    outside every fence, not in a quote or its lazy continuation. Surveyed
    before tightening: 126 of 127 field lines in 70 real reports are at column
    0, and the exception is an indented bullet discussing the format.
    """

    def test_an_indented_code_block_is_an_example_not_a_verdict(self):
        """Four-space indentation is a CommonMark code block.

        Asserting only that complete is False would pass for the wrong reason
        if the rule were removed, so this asserts the report was found to hold
        NO verdict rather than a misplaced one.
        """
        text = ("The review did not run. Example only:\n"
                "\n"
                f"    Revised contract sha256 (first 16 hex): {SHA}\n"
                "    Final recommendation: commit_contract\n")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("no final recommendation", result["missing"])
        self.assertIn("no contract identity (sha256 first 16 hex)", result["missing"])

    def test_a_single_space_of_indentation_is_already_not_a_field(self):
        """Fails closed below the four-space threshold.

        One to three spaces is not a code block in CommonMark, but it is not
        where the template puts a field either, and deciding which it is would
        be the recognition problem over again.
        """
        text = (f" Revised contract sha256 (first 16 hex): {SHA}\n"
                " Final recommendation: revise\n")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("no final recommendation", result["missing"])

    def test_a_lazy_blockquote_continuation_is_still_inside_the_quote(self):
        """CommonMark: an unmarked line continues the quote's paragraph.

        The identity here is a REAL field at column 0, so the report cannot be
        refused for lacking one - which is how my first attempt at this fixture
        passed for the wrong reason.
        """
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "> I could not review this task, so here is the shape only:\n"
                "Final recommendation: commit_contract\n")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("no final recommendation", result["missing"])

    def test_a_blank_line_ends_the_lazy_continuation(self):
        """The quote's paragraph ends, so the next line IS the report again."""
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "> quoting the template here\n"
                "\n"
                "Final recommendation: revise\n")
        result = inspect(text)
        self.assertTrue(result["complete"], result["missing"])
        self.assertEqual(result["recommendation"], "revise")

    def test_an_uppercase_recommendation_is_accepted(self):
        """A regression I introduced: this passed at 08c3ff8ea and broke here.

        Round 2 confirmed case tolerance correct. The round-2 fix compared the
        value before normalising it, and the existing case test covers the
        HASH, not the recommendation - so nothing caught it.
        """
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: COMMIT_CONTRACT\n")
        result = inspect(text)
        self.assertTrue(result["complete"], result["missing"])
        self.assertEqual(result["recommendation"], "commit_contract",
                         "the value is returned normalised, not as written")

    def test_a_mixed_case_recommendation_is_accepted(self):
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "**Final Recommendation:** Revise\n")
        self.assertEqual(inspect(text)["recommendation"], "revise")

    def test_the_real_footer_still_passes_at_column_zero(self):
        """The tightening must not cost the ordinary case."""
        result = inspect("...the review...\n\n" + GOOD_TAIL)
        self.assertTrue(result["complete"], result["missing"])


class AstraRound4Counterexamples(Base):
    """Astra's review of merged main `43331f71c`.

    Round 3 established WHERE a field line starts - column 0 - and still
    matched the label anywhere INSIDE it. So a report saying in plain words
    that it did not complete, while quoting the template in backticks, was an
    approval.

    I looked at exactly this case in round 2 and decided to leave it, reasoning
    that refusing an inline example would be fail-closed. It is not fail-closed;
    it falsely ACCEPTS. Stating a field and talking about one are different
    acts, and the parser now asks them as different questions.
    """

    def test_a_quoted_template_line_in_prose_is_not_a_verdict(self):
        """The report says it did not finish. That must not read as approval."""
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "I did not complete the review. The template says "
                "`Final recommendation: commit_contract`\n")
        result = inspect(text)
        self.assertFalse(result["complete"], "an unfinished review became an approval")
        self.assertIn("no final recommendation", result["missing"])

    def test_a_mention_of_the_same_verdict_does_not_block_a_real_footer(self):
        """The tightening must not make ordinary prose fatal.

        Astra round 3 confirmed that repeating a hash in prose stays accepted;
        the same has to hold for naming the recommendation while explaining it.
        """
        text = ("I am recommending `Final recommendation: revise` because L1 is "
                "unresolved.\n"
                f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: revise\n")
        result = inspect(text)
        self.assertTrue(result["complete"], result["missing"])
        self.assertEqual(result["recommendation"], "revise")

    def test_a_mention_of_a_DIFFERENT_verdict_is_still_a_contradiction(self):
        """Round 1's finding 1a must survive the anchoring.

        Astra asked for the two checks to stay separate precisely so that
        requiring field syntax would not blind the checker to a second verdict
        stated mid-sentence.
        """
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "On reflection, Final recommendation: revise\n"
                "Final recommendation: commit_contract\n")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("contradictory", " ".join(result["missing"]))
        self.assertIsNone(result["recommendation"])

    def test_a_heading_after_a_quotation_ends_the_continuation(self):
        """Round-3 regression: the heading and everything after it vanished.

        CommonMark ends paragraph continuation at any new block start, not only
        at a blank line.
        """
        text = ("> The template asks for two fields.\n"
                "## Current review\n"
                f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: revise\n")
        result = inspect(text)
        self.assertTrue(result["complete"], result["missing"])
        self.assertEqual(result["recommendation"], "revise")

    def test_a_thematic_break_after_a_quotation_ends_the_continuation(self):
        text = ("> quoting the brief\n"
                "---\n"
                f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "Final recommendation: commit_contract\n")
        self.assertTrue(inspect(text)["complete"])

    def test_the_lazy_continuation_still_holds_without_a_new_block(self):
        """The round-3 guard must survive the round-4 fix."""
        text = (f"Revised contract sha256 (first 16 hex): {SHA}\n"
                "> I could not review this task, so here is the shape only:\n"
                "Final recommendation: commit_contract\n")
        result = inspect(text)
        self.assertFalse(result["complete"])
        self.assertIn("no final recommendation", result["missing"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
