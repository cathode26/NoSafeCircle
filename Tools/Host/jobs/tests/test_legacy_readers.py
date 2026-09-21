#!/usr/bin/env python
"""Every legacy Markdown reader must refuse a derived view. All of them.

Run:
    python -B test_legacy_readers.py

This exists because the same rule has now been missed twice in different places:

  - MJ-P2-01 found that `check_closure_report`'s rendered view satisfied
    `legacy_closure_markdown.inspect` as a fresh approval of a `revise` verdict.
    Two readers were guarded.
  - MJ-P2-06 found the THIRD, `apply_contract.parse_post_commit_verdict`, wired
    up a commit later, doing exactly the same thing through
    `resolve_post_commit_check(legacy=True)`.

Fixing each one as it is found is what produced the second finding. So the rule
is one function, `review_result.is_derived_view`, and this module enumerates the
readers and checks each of them against the same fixtures - including a positive
control asserting each reader DOES accept the equivalent genuine legacy text,
because a reader that refuses everything would pass the refusal tests while
having quietly stopped working.

**Adding a legacy reader means adding it to READERS.** There is no way to detect
one automatically; what this buys is a single place that fails loudly when the
list and the code disagree, instead of three places that each look fine alone.
"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

HOST = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HOST))
sys.path.insert(0, str(HOST / "jobs"))
sys.path.insert(0, str(HOST / "ger"))

import apply_contract  # noqa: E402
import ger_round  # noqa: E402
import legacy_closure_markdown  # noqa: E402
import review_result  # noqa: E402

CONTRACT = b'{"task": "NSC-001", "revision": 7}\n'
SHA16 = hashlib.sha256(CONTRACT).hexdigest()[:16]

# Genuine pre-cutover text each reader accepts, and the verdict it should give.
CLOSURE_PROSE = (
    "Revised contract sha256 (first 16 hex): " + SHA16 + "\n"
    "Ledger:\n"
    "- L1: RESOLVED.\n"
    "New findings (task-local, most severe first):\n"
    "- none\n"
    "Final recommendation: commit_contract"
)
ROUND_PROSE = "Final recommendation: commit_contract_then_decompose\n"
POST_COMMIT_PROSE = "Ledger:\n- L1: RESOLVED.\n\nFinal recommendation: revise\n"


def closure_reader(text):
    verdict = legacy_closure_markdown.inspect(text, SHA16)
    return verdict["recommendation"] if verdict["complete"] else None


# (name, callable taking text and returning a verdict or None, genuine text,
#  the verdict that genuine text must produce)
READERS = [
    ("legacy_closure_markdown.inspect", closure_reader,
     CLOSURE_PROSE, "commit_contract"),
    ("ger_round.legacy_round_recommendation", ger_round.legacy_round_recommendation,
     ROUND_PROSE, "commit_contract_then_decompose"),
    ("apply_contract.parse_post_commit_verdict", apply_contract.parse_post_commit_verdict,
     POST_COMMIT_PROSE, "revise"),
]


class EveryReader(unittest.TestCase):
    def test_each_reader_accepts_its_genuine_legacy_text(self):
        # The positive control. Without it, a reader that refuses everything
        # passes every refusal test below while being broken.
        for name, reader, genuine, expected in READERS:
            with self.subTest(reader=name):
                self.assertEqual(reader(genuine), expected,
                                 f"{name} no longer reads genuine legacy text")

    def test_each_reader_refuses_the_same_text_marked_as_derived(self):
        # One byte of difference: the marker. Everything the reader would key on
        # is still present, so a refusal can only come from the guard.
        for name, reader, genuine, _expected in READERS:
            with self.subTest(reader=name):
                derived = review_result.DERIVED_VIEW_HEADER + "\n\n" + genuine
                self.assertIsNone(reader(derived),
                                  f"{name} read a verdict out of a derived view")

    def test_each_reader_refuses_a_marker_anywhere_in_the_text(self):
        # Not only as a header: a view embedded further down is still derived.
        for name, reader, genuine, _expected in READERS:
            with self.subTest(reader=name):
                derived = genuine + "\n\n" + review_result.DERIVED_VIEW_HEADER + "\n"
                self.assertIsNone(reader(derived), name)

    def test_every_reader_named_in_the_shared_docstring_is_on_this_list(self):
        # The docstring of is_derived_view names the readers. If it names one
        # this module does not cover, the list has drifted from the intent.
        named = review_result.is_derived_view.__doc__ or ""
        for name, _reader, _genuine, _expected in READERS:
            with self.subTest(reader=name):
                self.assertIn(name.split(".")[-1], named,
                              f"{name} is tested here but not named in "
                              f"is_derived_view's docstring")


class TheSharedTest(unittest.TestCase):
    def test_it_is_the_marker_that_decides(self):
        self.assertTrue(review_result.is_derived_view(
            review_result.DERIVED_VIEW_HEADER))
        self.assertTrue(review_result.is_derived_view(
            "prose\n" + review_result.DERIVED_VIEW_MARKER + "\nmore"))
        self.assertFalse(review_result.is_derived_view("an ordinary report"))

    def test_empty_and_none_are_not_derived_views(self):
        self.assertFalse(review_result.is_derived_view(""))
        self.assertFalse(review_result.is_derived_view(None))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main(verbosity=2)
