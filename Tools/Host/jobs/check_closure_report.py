#!/usr/bin/env python
"""Did the closure review actually review the contract, or decline to?

check_job_result.py answers three narrower questions - did the process succeed,
is the artifact fresh, what does it say - and answers them correctly. It does not
and should not know what a *closure review* has to contain. The 2026-09-20
main-commit review reproduced the gap that leaves: a fresh, non-empty report
reading

    I could not review this task. Please retry later.

passes every one of those checks and the closure workflow calls it a success.

The closure prompt states exactly what a finished report carries
(templates/contract-closure-review-prompt.md, lines 43 and 50):

    Revised contract sha256 (first 16 hex): <16 hex characters>
    Final recommendation: commit_contract | commit_contract_then_decompose | revise

Both must be present. The sha16 is the contract identity - without it the report
cannot be tied to the bytes that were reviewed, so a report about the wrong
revision is indistinguishable from a report about the right one.

**A `revise` recommendation is a SUCCESS.** The review ran, reached a conclusion
and the conclusion is negative. Conflating "the work was rejected" with "the run
failed" is how a REJECT verdict gets retried as though it were a timeout, which
is the failure this whole checker family exists to prevent.

Exit: 0 complete; 7 incomplete; 2 the report could not be read.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RECOMMENDATIONS = ("commit_contract", "commit_contract_then_decompose", "revise")

# Tolerant of surrounding markdown (bold, list markers) but not of a missing
# value: the point is to catch a report that never reached a conclusion.
SHA16 = re.compile(r"sha256\s*\(first\s*16\s*hex\)\s*:?\s*\**\s*([0-9a-fA-F]{16})\b",
                   re.IGNORECASE)
FINAL = re.compile(r"Final\s+recommendation\s*:?\s*\**\s*([a-z_]+)", re.IGNORECASE)


def inspect(text: str) -> dict:
    """What the report contains, and whether that is enough to act on."""
    sha = SHA16.search(text or "")
    rec = FINAL.search(text or "")
    recommendation = rec.group(1).lower() if rec else None

    missing = []
    if sha is None:
        missing.append("no contract identity (sha256 first 16 hex)")
    if recommendation is None:
        missing.append("no final recommendation")
    elif recommendation not in RECOMMENDATIONS:
        missing.append(f"final recommendation {recommendation!r} is not one of "
                       f"{', '.join(RECOMMENDATIONS)}")

    return {
        "complete": not missing,
        "sha16": sha.group(1).lower() if sha else None,
        "recommendation": recommendation,
        "missing": missing,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Check that a closure review report is a finished review.")
    ap.add_argument("--report", required=True, help="the report file to inspect")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    path = Path(args.report)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return 2

    result = inspect(text)
    if result["complete"]:
        if not args.quiet:
            print(f"closure review complete: {result['recommendation']} "
                  f"(contract {result['sha16']})")
        return 0

    print(f"closure review INCOMPLETE - {path}", file=sys.stderr)
    for reason in result["missing"]:
        print(f"  - {reason}", file=sys.stderr)
    head = "\n".join(text.strip().splitlines()[:5])
    print(f"  report begins:\n      {head}", file=sys.stderr)
    return 7


if __name__ == "__main__":
    raise SystemExit(main())
