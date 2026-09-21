#!/usr/bin/env python
"""Tests for review_result, the declared-result reader.

Run:
    python -B test_review_result.py

Every refusal test asserts the exception's CODE, never merely that it raised.
In round 2 of the Markdown checker two tests passed for the wrong reason - their
fixtures were refused by a second rule before reaching the rule under test - and
that hid two live mutations. `refuses()` exists so that cannot recur here.

The MJ-04 class is the point of the whole exercise. Each of those fixtures is a
counterexample that cost a review round against the Markdown checker: a verdict
in a fence, in a block quote, behind an escaped backtick, inside raw HTML, an
options list echoed back. Here they are all just characters inside a string
field, and the assertions are boring. That is the property being bought.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import review_result  # noqa: E402
from review_result import ReviewResultError, bind, decode  # noqa: E402

DIGEST = "a" * 64
OTHER_DIGEST = "b" * 64

GOOD = {
    "schema_version": 1,
    "review_kind": "closure",
    "task_id": "NSC-001",
    "reviewed_artifact_kind": "contract",
    "reviewed_artifact_sha256": DIGEST,
    "review_status": "complete",
    "recommendation": "commit_contract",
    "report_markdown": "The ledger item is resolved.",
}

EXPECT = {
    "task_id": "NSC-001",
    "review_kind": "closure",
    "reviewed_artifact_kind": "contract",
    "reviewed_artifact_sha256": DIGEST,
}


def raw(**overrides) -> bytes:
    """The valid object with fields replaced; a value of `...` deletes the field."""
    body = dict(GOOD)
    for key, value in overrides.items():
        if value is ...:
            body.pop(key, None)
        else:
            body[key] = value
    return json.dumps(body).encode("utf-8")


class Base(unittest.TestCase):
    def refuses(self, code: str, data: bytes, note: str = ""):
        """Assert the exact refusal reason, and report the real one when it differs."""
        with self.assertRaises(ReviewResultError) as caught:
            decode(data)
        self.assertEqual(
            caught.exception.code, code,
            f"expected {code!r}{' (' + note + ')' if note else ''}, "
            f"got {caught.exception.code!r}: {caught.exception.message}")
        return caught.exception


class StrictDecoding(Base):
    """MJ-01: strict decoding, closed types and fields; invalid and oversized refuse."""

    def test_the_valid_object_decodes(self):
        result = decode(raw())
        self.assertEqual(result.recommendation, "commit_contract")
        self.assertTrue(result.is_complete)
        self.assertTrue(result.is_committable)

    def test_a_deeply_nested_value_refuses_rather_than_crashing(self):
        """Fable: 200k nested lists, ~400 KB, well under MAX_BYTES.

        RecursionError is a RuntimeError, so the ValueError branch never saw it
        and the decoder crashed. ger_round's caller catches (ValueError, OSError)
        only, so the round wrote neither FAILED.json nor METADATA.json and looked
        to the node like it was still running - a crash that presents as a hang.

        The size limit cannot stand in for this one: depth is not length.
        """
        deep = '{"schema_version": ' + "[" * 200_000 + "]" * 200_000 + "}"
        self.assertLess(len(deep), review_result.MAX_BYTES * 1,
                        "the fixture must be under the size limit or it proves "
                        "nothing about depth")
        with self.assertRaises(Exception) as caught:
            review_result.decode(deep.encode("utf-8"))
        self.assertIsInstance(caught.exception, review_result.ReviewResultError)
        self.assertEqual(caught.exception.code, "parser_limit")

    def test_oversize_refuses_before_parsing(self):
        big = raw(report_markdown="x" * (review_result.MAX_BYTES + 1))
        self.assertGreater(len(big), review_result.MAX_BYTES)
        self.refuses("oversize", big)

    def test_at_the_limit_is_accepted(self):
        # The boundary belongs to the accepted side; a mutation flipping > to >=
        # must fail something.
        body = json.dumps(dict(GOOD, report_markdown="x")).encode("utf-8")
        pad = review_result.MAX_BYTES - len(body)
        exact = raw(report_markdown="x" * (1 + pad))
        self.assertEqual(len(exact), review_result.MAX_BYTES)
        self.assertEqual(decode(exact).recommendation, "commit_contract")

    def test_invalid_utf8_refuses(self):
        self.refuses("not_utf8", b'{"schema_version": 1, "x": "\xff\xfe"}')

    def test_a_fenced_object_is_not_json(self):
        self.refuses("not_json", b"```json\n" + raw() + b"\n```")

    def test_a_preamble_sentence_is_not_json(self):
        self.refuses("not_json", b"Here is my result:\n" + raw())

    def test_trailing_data_refuses(self):
        self.refuses("not_json", raw() + b"\nReviewed by Astra.")

    def test_two_objects_refuse(self):
        self.refuses("not_json", raw() + raw())

    def test_empty_input_refuses(self):
        self.refuses("not_json", b"")

    def test_a_top_level_array_refuses(self):
        self.refuses("not_object", json.dumps([GOOD]).encode("utf-8"))

    def test_a_top_level_string_refuses(self):
        self.refuses("not_object", b'"commit_contract"')

    def test_duplicate_keys_refuse(self):
        # json's default keeps the last pair silently, which is the JSON spelling
        # of a document asserting two verdicts and being read as asserting one.
        text = ('{"schema_version": 1, "review_kind": "closure", "task_id": "NSC-001",'
                ' "reviewed_artifact_kind": "contract",'
                f' "reviewed_artifact_sha256": "{DIGEST}",'
                ' "review_status": "complete",'
                ' "recommendation": "revise",'
                ' "recommendation": "commit_contract",'
                ' "report_markdown": "text"}')
        self.refuses("duplicate_key", text.encode("utf-8"))

    def test_nan_and_infinity_refuse(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                text = json.dumps(GOOD)[:-1] + f', "extra": {token}}}'
                self.refuses("nonstandard_number", text.encode("utf-8"))

    def test_every_missing_field_refuses(self):
        for field in review_result.FIELDS:
            with self.subTest(field=field):
                self.refuses("missing_field", raw(**{field: ...}))

    def test_an_unknown_field_refuses(self):
        self.refuses("unknown_field", raw(confidence="high"))

    def test_schema_version_true_is_not_one(self):
        # bool subclasses int, so isinstance(True, int) is True and a naive check
        # reads `"schema_version": true` as version 1.
        self.refuses("wrong_type", raw(schema_version=True))

    def test_schema_version_as_string_refuses(self):
        self.refuses("wrong_type", raw(schema_version="1"))

    def test_an_unsupported_schema_version_refuses(self):
        self.refuses("unknown_enum", raw(schema_version=2))

    def test_unknown_enums_refuse(self):
        for field, value in (("review_kind", "audit"),
                             ("reviewed_artifact_kind", "diff"),
                             ("review_status", "partial")):
            with self.subTest(field=field):
                self.refuses("unknown_enum", raw(**{field: value}))

    def test_non_string_scalars_refuse(self):
        for field in ("review_kind", "task_id", "reviewed_artifact_kind",
                      "reviewed_artifact_sha256", "review_status", "report_markdown"):
            with self.subTest(field=field):
                self.refuses("wrong_type", raw(**{field: 7}))

    def test_bad_hash_shapes_refuse(self):
        for bad, note in (("a" * 63, "too short"),
                          ("a" * 65, "too long"),
                          ("A" * 64, "uppercase"),
                          ("g" * 64, "not hex"),
                          ("", "empty")):
            with self.subTest(note=note):
                self.refuses("bad_hash_format", raw(reviewed_artifact_sha256=bad), note)

    def test_empty_task_id_refuses(self):
        self.refuses("wrong_type", raw(task_id=""))

    def test_an_empty_report_refuses(self):
        for value in ("", "   ", "\n\t "):
            with self.subTest(value=repr(value)):
                self.refuses("empty_report", raw(report_markdown=value))

    def test_one_leading_bom_is_tolerated(self):
        self.assertEqual(decode(chr(0xFEFF).encode("utf-8") + raw()).task_id, "NSC-001")

    def test_a_second_bom_is_content_and_refuses(self):
        self.refuses("not_json", (chr(0xFEFF) * 2).encode("utf-8") + raw())

    def test_decode_takes_bytes_not_text(self):
        # Passing str would skip the UTF-8 and size checks entirely.
        with self.assertRaises(ReviewResultError) as caught:
            decode(json.dumps(GOOD))
        self.assertEqual(caught.exception.code, "wrong_type")


class UnicodeThatCannotBeWrittenBack(Base):
    """Astra MJ-P1-01: an escaped unpaired surrogate is valid JSON and unencodable.

    `"\\ud800"` is well-formed JSON. It decodes to a lone surrogate, which is a
    str Python holds happily and cannot encode back to UTF-8. Before this was
    closed, such a result decoded, bound, and reported is_committable=True - and
    then crashed `check_closure_report` with an unhandled UnicodeEncodeError the
    moment it wrote the rendered view. Reproduced independently by Astra and here
    before the fix.
    """

    # Assembled from hex digits rather than written as literals. A source file
    # containing an astral escape is liable to be normalised into the single
    # real character it denotes by any tool that round-trips it through JSON -
    # which
    # happened while writing these tests, and would have quietly turned the
    # regression guard below into a test of something else.
    HIGH = "\\u" + "d800"
    LOW = "\\u" + "dc00"
    LAST_LOW = "\\u" + "dfff"
    PAIR = "\\u" + "d83d" + "\\u" + "de00"      # U+1F600, as JSON must escape it

    def escaped(self, field: str, escape: str) -> bytes:
        """JSON text carrying a literal \\uXXXX escape, never a real codepoint.

        Built by substitution rather than json.dumps, because dumps would encode
        a real surrogate and the point is the ESCAPE. The ascii encode is the
        assertion: if `escape` were ever a real character rather than its escape
        text, this raises instead of silently testing the wrong thing.
        """
        text = json.dumps(dict(GOOD, **{field: "PLACEHOLDER"}))
        return text.replace('"PLACEHOLDER"', '"' + escape + '"').encode("ascii")

    def test_a_lone_high_surrogate_is_refused(self):
        self.refuses("lone_surrogate", self.escaped("report_markdown", self.HIGH))

    def test_a_lone_low_surrogate_is_refused(self):
        self.refuses("lone_surrogate", self.escaped("report_markdown", self.LOW))

    def test_a_lone_surrogate_in_any_string_field_is_refused(self):
        for field in ("task_id", "report_markdown"):
            with self.subTest(field=field):
                self.refuses("lone_surrogate", self.escaped(field, self.LAST_LOW))

    def test_a_valid_surrogate_pair_is_still_accepted(self):
        # The fix must reject unpaired surrogates without rejecting astral
        # characters, which JSON necessarily escapes AS a surrogate pair.
        result = decode(self.escaped("report_markdown", self.PAIR))
        self.assertEqual(len(result.report_markdown), 1)
        self.assertEqual(len(result.report_markdown.encode("utf-8")), 4)

    def test_an_accepted_result_can_always_be_written_back_out(self):
        # The property underneath the rule, stated once.
        result = decode(self.escaped("report_markdown", self.PAIR))
        for value in (result.report_markdown, result.task_id,
                      result.reviewed_artifact_sha256):
            value.encode("utf-8")


class DecoderLimits(Base):
    """Astra MJ-P1-01, second half: json.loads can raise a bare ValueError."""

    def test_an_enormous_integer_is_refused_not_leaked(self):
        # CPython refuses integer string conversion past 4300 digits, with a
        # ValueError that is NOT a JSONDecodeError. It failed closed before, by
        # crashing; this is the same answer said properly.
        raw = ('{"schema_version": ' + "9" * 6000 + "}").encode("ascii")
        self.refuses("parser_limit", raw)

    def test_a_real_programming_error_is_not_reported_as_a_bad_result(self):
        # The ValueError catch is narrow on purpose. If it swallowed everything,
        # a bug in this module would be reported as the reviewer's fault.
        broken = object()
        with self.assertRaises(ReviewResultError) as caught:
            decode(broken)  # type: ignore[arg-type]
        self.assertEqual(caught.exception.code, "wrong_type")


class CompletionAndRecommendation(Base):
    """MJ-02: a complete negative succeeds; incomplete cannot approve or retry."""

    def test_a_complete_revise_is_a_finished_review(self):
        result = decode(raw(recommendation="revise"))
        self.assertTrue(result.is_complete)
        self.assertFalse(result.is_committable)
        self.assertEqual(result.recommendation, "revise")

    def test_a_complete_ger_refusal_is_a_finished_review(self):
        for verdict in ("needs_design", "blocked_not_design", "release_without_change"):
            with self.subTest(verdict=verdict):
                result = decode(raw(review_kind="ger",
                                    reviewed_artifact_kind="ger_round_output",
                                    recommendation=verdict))
                self.assertTrue(result.is_complete)
                self.assertFalse(result.is_committable)

    def test_both_committable_values_are_committable(self):
        for verdict in ("commit_contract", "commit_contract_then_decompose"):
            with self.subTest(verdict=verdict):
                self.assertTrue(decode(raw(recommendation=verdict)).is_committable)

    def test_incomplete_with_null_is_valid_and_not_actionable(self):
        result = decode(raw(review_status="incomplete", recommendation=None,
                            report_markdown="The provider timed out."))
        self.assertFalse(result.is_complete)
        self.assertFalse(result.is_committable)
        self.assertIsNone(result.recommendation)

    def test_incomplete_may_not_carry_a_recommendation(self):
        # "The provider died" must not be expressible as "revise", which is the
        # confusion commit b4dedabfb exists to fix.
        for verdict in ("revise", "commit_contract"):
            with self.subTest(verdict=verdict):
                self.refuses("recommendation_on_incomplete",
                             raw(review_status="incomplete", recommendation=verdict))

    def test_complete_must_name_a_recommendation(self):
        self.refuses("missing_recommendation", raw(recommendation=None))

    def test_a_non_string_recommendation_refuses(self):
        self.refuses("wrong_type", raw(recommendation=3))

    def test_the_two_vocabularies_do_not_cross(self):
        # "Do not translate revise into needs_design" - they are different
        # families, and a reader that maps one onto the other invents a decision.
        self.refuses("wrong_family_recommendation", raw(recommendation="needs_design"),
                     "needs_design is not a closure verdict")
        self.refuses("wrong_family_recommendation",
                     raw(review_kind="ger",
                         reviewed_artifact_kind="ger_round_output",
                         recommendation="revise"),
                     "revise is not a GER verdict")

    def test_a_near_miss_verdict_refuses(self):
        # `commit_contract2` passed the Markdown checker in round 2.
        for bad in ("commit_contract2", "Commit_Contract", "commit contract", " revise"):
            with self.subTest(bad=bad):
                self.refuses("wrong_family_recommendation", raw(recommendation=bad))


class HostBinding(Base):
    """MJ-03: the result must be about what the host selected."""

    def test_a_matching_result_binds(self):
        result = decode(raw())
        self.assertIs(bind(result, **EXPECT), result)

    def test_a_different_task_refuses(self):
        with self.assertRaises(ReviewResultError) as caught:
            bind(decode(raw(task_id="NSC-999")), **EXPECT)
        self.assertEqual(caught.exception.code, "task_mismatch")

    def test_a_different_family_refuses(self):
        with self.assertRaises(ReviewResultError) as caught:
            bind(decode(raw(review_kind="ger",
                            reviewed_artifact_kind="ger_round_output",
                            recommendation="needs_design")),
                 **dict(EXPECT, reviewed_artifact_kind="ger_round_output"))
        self.assertEqual(caught.exception.code, "family_mismatch")

    def test_a_different_artifact_kind_refuses(self):
        with self.assertRaises(ReviewResultError) as caught:
            bind(decode(raw(reviewed_artifact_kind="ger_round_output")), **EXPECT)
        self.assertEqual(caught.exception.code, "artifact_kind_mismatch")

    def test_changed_reviewed_bytes_refuse(self):
        # A structurally perfect review of a DIFFERENT revision.
        with self.assertRaises(ReviewResultError) as caught:
            bind(decode(raw(reviewed_artifact_sha256=OTHER_DIGEST)), **EXPECT)
        self.assertEqual(caught.exception.code, "artifact_hash_mismatch")

    def test_a_malformed_expectation_blames_the_caller(self):
        # Refusing here rather than comparing keeps a bad host expectation from
        # reading as a bad reviewer result.
        with self.assertRaises(ReviewResultError) as caught:
            bind(decode(raw()), **dict(EXPECT, reviewed_artifact_sha256="nope"))
        self.assertEqual(caught.exception.code, "bad_hash_format")


class TheOneEntryPoint(Base):
    """`load` is what consumers call: schema and binding, never one without the other."""

    def test_load_returns_the_bound_result(self):
        result = review_result.load(raw(), **EXPECT)
        self.assertEqual(result.recommendation, "commit_contract")

    def test_load_enforces_the_schema(self):
        with self.assertRaises(ReviewResultError) as caught:
            review_result.load(raw(confidence="high"), **EXPECT)
        self.assertEqual(caught.exception.code, "unknown_field")

    def test_load_enforces_the_binding(self):
        # The bypass this entry point exists to close: a structurally perfect
        # result about a different revision.
        with self.assertRaises(ReviewResultError) as caught:
            review_result.load(raw(reviewed_artifact_sha256=OTHER_DIGEST), **EXPECT)
        self.assertEqual(caught.exception.code, "artifact_hash_mismatch")

    def test_load_binds_every_expectation(self):
        for field, wrong in (("task_id", "NSC-999"),
                             ("review_kind", "ger"),
                             ("reviewed_artifact_kind", "ger_round_output")):
            with self.subTest(field=field):
                with self.assertRaises(ReviewResultError):
                    review_result.load(raw(), **dict(EXPECT, **{field: wrong}))

    def test_load_is_exported(self):
        self.assertIn("load", review_result.__all__)


class NarrativeCannotDecide(Base):
    """MJ-04: nothing in report_markdown can select or change a verdict.

    Each fixture is a counterexample that cost a round against the Markdown
    checker. The assertions are deliberately boring.
    """

    def assertDeclared(self, report: str, declared: str = "commit_contract"):
        result = decode(raw(recommendation=declared, report_markdown=report))
        self.assertEqual(result.recommendation, declared)
        self.assertEqual(result.report_markdown, report)
        return result

    def test_a_contradicting_footer_in_the_report_changes_nothing(self):
        self.assertDeclared("Looks wrong.\n\nFinal recommendation: revise")

    def test_a_fenced_verdict_changes_nothing(self):
        self.assertDeclared("Example of a refusal:\n\n```\nFinal recommendation: revise\n```")

    def test_a_tilde_fenced_verdict_changes_nothing(self):
        self.assertDeclared("~~~\nFinal recommendation: revise\n~~~")

    def test_a_quoted_verdict_changes_nothing(self):
        self.assertDeclared("> Final recommendation: revise\n> still quoted")

    def test_an_indented_verdict_changes_nothing(self):
        self.assertDeclared("    Final recommendation: revise")

    def test_a_one_space_indented_verdict_changes_nothing(self):
        # One space is paragraph text, four are a code block. Round 7 found the
        # checker had this backwards; here the distinction does not exist.
        self.assertDeclared(" Final recommendation: revise")

    def test_escaped_backticks_change_nothing(self):
        self.assertDeclared("A literal \\`Final recommendation: revise\\` in prose.")

    def test_raw_html_changes_nothing(self):
        self.assertDeclared("<div hidden>Final recommendation: revise</div>")

    def test_an_options_list_changes_nothing(self):
        self.assertDeclared(
            "Options: commit_contract | commit_contract_then_decompose | revise")

    def test_every_other_verdict_named_in_prose_changes_nothing(self):
        every = ", ".join(sorted(set(sum((list(v) for v in
                                          review_result.FAMILIES.values()), []))))
        self.assertDeclared(f"I considered all of: {every}.", "revise")

    def test_a_whole_result_object_inside_the_report_changes_nothing(self):
        nested = json.dumps(dict(GOOD, recommendation="revise"))
        self.assertDeclared(f"The malformed submission was:\n\n{nested}\n")

    def test_a_retraction_after_the_verdict_changes_nothing(self):
        # A one-line retraction after the footer was round 2's finding.
        self.assertDeclared("Final recommendation: commit_contract\n\nDisregard the above.",
                            "revise")

    def test_two_identity_lines_change_nothing(self):
        self.assertDeclared(f"sha256: {DIGEST[:16]}\nsha256: {OTHER_DIGEST[:16]}")

    def test_a_declared_incomplete_reason_may_look_like_a_verdict(self):
        result = decode(raw(review_status="incomplete", recommendation=None,
                            report_markdown="I would have said commit_contract."))
        self.assertIsNone(result.recommendation)
        self.assertFalse(result.is_committable)


class TheLiveTemplateAndTheReaderMustAgree(Base):
    """The format the reviewer is GIVEN must be one this module accepts.

    Round 2 of the Markdown checker had two halves, and the second was that the
    template handed reviewers a shape the checker refused - a verdict line that
    listed all three options, and a parenthetical after it. Nothing in the
    repository connected the two files, so both were "correct" alone.

    This is that connection, on the JSON side. Its ancestor guarded the Markdown
    pair and now guards the frozen legacy format at
    `Tools/Host/jobs/tests/test_check_closure_report.py::TheTemplateAndTheCheckerMustAgree`.
    """

    TEMPLATE = (Path(__file__).resolve().parent.parent
                / "codex-jobs" / "templates" / "contract-closure-review-prompt.md")

    # What a compliant reviewer substitutes for each placeholder. A placeholder
    # field missing from here raises KeyError and fails the test, which is the
    # point: a new field in the template must be considered here too.
    SUBSTITUTIONS = {
        "task_id": "NSC-001",
        "reviewed_artifact_sha256": DIGEST,
        "recommendation": "revise",
        "report_markdown": "Ledger:\n- L1: UNRESOLVED — the gate is still unprovable.",
    }

    def example(self) -> bytes:
        text = self.TEMPLATE.read_text(encoding="utf-8")
        _, found, block = text.partition("FINAL MESSAGE")
        self.assertTrue(found, f"no FINAL MESSAGE section in {self.TEMPLATE}")
        start = block.index("{")
        end = block.index("\n}", start) + 2
        obj = block[start:end]

        def fill(match):
            key = match.group(1)
            return f'"{key}": {json.dumps(self.SUBSTITUTIONS[key])}'

        filled = re.sub(r'"(\w+)": "<[^"]*>"', fill, obj)
        self.assertNotIn("<", filled,
                         f"a placeholder was not substituted: {filled}")
        return filled.encode("utf-8")

    def test_the_template_is_where_this_test_looks_for_it(self):
        self.assertTrue(self.TEMPLATE.is_file(), self.TEMPLATE)

    def test_the_documented_object_decodes_and_binds(self):
        result = review_result.load(self.example(), **dict(EXPECT))
        self.assertEqual(result.recommendation, "revise")
        self.assertTrue(result.is_complete)
        self.assertFalse(result.is_committable)

    def test_the_template_declares_the_closure_family_and_kind(self):
        # If the template said "ger", every real review would fail binding.
        result = decode(self.example())
        self.assertEqual(result.review_kind, "closure")
        self.assertEqual(result.reviewed_artifact_kind, "contract")

    def test_the_template_tells_the_reviewer_to_emit_nothing_else(self):
        # The JSON reader refuses a preamble or a sign-off, so the instruction
        # that prevents them is load-bearing, not decoration.
        text = self.TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("nothing before or after", text)
        self.assertIn("no code fence", text)

    def test_the_template_asks_for_the_full_hash_not_a_prefix(self):
        text = self.TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("64", text,
                      "the template must ask for all 64 hex characters; the "
                      "legacy format asked for the first 16 and binding needs all")


if __name__ == "__main__":
    unittest.main(verbosity=2)
