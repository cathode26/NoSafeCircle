#!/usr/bin/env python
"""Is this closure result a finished review of the RIGHT contract?

The question has not changed since the Markdown checker. What changed is where
the answer comes from: the reviewer now declares it in one JSON object, so this
file reads a field instead of inferring a verdict from prose. The reasoning for
that is in `Tools/Host/review_result.py`; the short version is that eight review
rounds were spent on the inference and the defect space never closed.

This file is deliberately thin. Every rule lives in `review_result`, and the only
things here are argument handling, reading bytes, hashing the contract, exit
codes, and rendering the human view.

**There is no fallback to the legacy reader.** A result that fails to parse is a
failure, full stop. The Markdown recogniser still exists, at
`legacy_closure_markdown.py`, for reading reports written before the cutover -
but nothing in this file can reach it, and that is the point. If a malformed new
result could be retried through the old parser, every guarantee the JSON protocol
buys would be available to bypass by emitting something the new reader rejects.

Exit codes, unchanged from the Markdown checker so callers keep working:

    0   a complete review, whatever it recommends. `revise` exits 0: the review
        ran and reached a negative conclusion, and treating a rejection as a
        failed run is how a verdict gets retried like a timeout.
    2   an input could not be read.
    7   the result is not an actionable review - malformed, incomplete, or about
        something other than what the host supplied.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import review_result  # noqa: E402

RENDERED_HEADER = (
    "<!-- Rendered from the validated JSON result. This file is a human view and "
    "is NOT a decision source; no tool may read a verdict out of it. -->"
)


def render(result: review_result.ReviewResult) -> str:
    """The human view, derived from validated fields only.

    Labelled as derived because the handoff requires that rendered Markdown never
    become usable as a fresh approval through a legacy path. The label is not the
    enforcement - the enforcement is that no reader parses this file - but a
    reader who opens it should not have to guess where it came from.
    """
    verdict = result.recommendation if result.is_complete else "INCOMPLETE - no recommendation"
    return "\n".join([
        RENDERED_HEADER,
        "",
        f"# Closure review - {result.task_id}",
        "",
        f"- Review status: {result.review_status}",
        f"- Recommendation: {verdict}",
        f"- Reviewed contract sha256: {result.reviewed_artifact_sha256}",
        "",
        "---",
        "",
        result.report_markdown.rstrip(),
        "",
    ])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Check that a closure review reached one declared verdict "
                    "about the exact contract the host supplied.")
    ap.add_argument("--result", required=True,
                    help="the reviewer's raw JSON result")
    ap.add_argument("--contract", required=True,
                    help="the exact REVISED_CONTRACT.json the review was given; "
                         "its sha256 must equal the one the result declares")
    ap.add_argument("--task", required=True,
                    help="the task the host asked about, e.g. NSC-001")
    ap.add_argument("--report-out", default=None,
                    help="write the human view of report_markdown here; only "
                         "written when the result validates")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        raw = Path(args.result).read_bytes()
    except OSError as exc:
        print(f"cannot read {args.result}: {exc}", file=sys.stderr)
        return 2

    try:
        contract = Path(args.contract).read_bytes()
    except OSError as exc:
        print(f"cannot read {args.contract}: {exc}", file=sys.stderr)
        return 2

    expected = hashlib.sha256(contract).hexdigest()

    try:
        result = review_result.load(
            raw,
            task_id=args.task,
            review_kind="closure",
            reviewed_artifact_kind="contract",
            reviewed_artifact_sha256=expected,
        )
    except review_result.ReviewResultError as error:
        print(f"closure review NOT ACTIONABLE - {args.result}", file=sys.stderr)
        print(f"  - {error.code}: {error.message}", file=sys.stderr)
        head = raw[:400].decode("utf-8", errors="replace").strip().splitlines()[:5]
        print("  result begins:\n      " + "\n      ".join(head), file=sys.stderr)
        return 7

    if not result.is_complete:
        # A declared non-finish. Distinct from a malformed result above, and
        # distinct from a negative verdict below: the review did not happen, so
        # there is nothing to act on and nothing to retry a verdict over.
        print(f"closure review INCOMPLETE - {args.result}", file=sys.stderr)
        print(f"  - the reviewer declared it did not finish", file=sys.stderr)
        for line in result.report_markdown.strip().splitlines()[:5]:
            print(f"      {line}", file=sys.stderr)
        return 7

    if args.report_out:
        Path(args.report_out).write_text(render(result), encoding="utf-8")

    if not args.quiet:
        print(f"closure review complete: {result.recommendation}, "
              f"contract {result.reviewed_artifact_sha256[:16]} (verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
