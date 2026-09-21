#!/usr/bin/env python
"""Did the closure review reach ONE verdict, about the RIGHT contract?

check_job_result.py answers three narrower questions - did the process succeed,
is the artifact fresh, what does it say - and answers them correctly. It does
not know what a *closure review* must contain, and should not.

The first version of this file asked only "are the markers present". Astra's
2026-09-20 release review showed that is a different and much weaker question:

  * `.search` returns the FIRST match, so a report recommending
    `commit_contract` and later `revise` passed as `commit_contract`. The
    checker picked a side in a contradiction instead of refusing it.
  * "I could not review this task" appearing AFTER a well-formed footer still
    passed, because nothing required the footer to be the end of the report.
  * ANY 16 hex characters satisfied the identity line, and there was no way to
    say which contract was under review, so a report about a DIFFERENT revision
    passed. That is the one that matters: a stale or misdirected review reading
    as a clean pass on the wrong bytes.

So this now requires all of:

  1. exactly one contract-identity line and exactly one final recommendation -
     more than one of either is a contradiction, not a verdict;
  2. the recommendation sitting in the report's closing lines, so trailing
     text that walks it back cannot hide behind a correct-looking footer;
  3. with --contract, the identity equal to sha256 of those exact bytes.

`revise` is still a SUCCESS. The review ran and reached a negative conclusion.
Treating a rejection as a failed run is how a verdict gets retried like a
timeout, which is the confusion this whole checker family exists to prevent.

Exit: 0 complete; 7 incomplete, contradictory or about the wrong contract;
      2 a file could not be read.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

RECOMMENDATIONS = ("commit_contract", "commit_contract_then_decompose", "revise")

# Tolerant of markdown emphasis and list markers, strict about the value.
SHA16 = re.compile(r"sha256\s*\(first\s*16\s*hex\)\s*:?\s*\**\s*([0-9a-fA-F]{16})\b",
                   re.IGNORECASE)
FINAL = re.compile(r"Final\s+recommendation\s*:?\s*\**\s*([a-z_]+)", re.IGNORECASE)

# How many closing non-empty lines count as "the footer". The prompt puts the
# identity and the recommendation in the last two or three lines; anything after
# them is the report arguing with its own verdict.
FOOTER_LINES = 3


def contract_sha16(data: bytes) -> str:
    """The first 16 hex characters of the contract's SHA-256, as the prompt asks."""
    return hashlib.sha256(data).hexdigest()[:16]


def inspect(text: str, expected_sha16: str | None = None) -> dict:
    """What the report contains, and whether that is one verdict worth acting on."""
    text = text or ""
    shas = SHA16.findall(text)
    recs = [r.lower() for r in FINAL.findall(text)]

    lines = [line for line in text.splitlines() if line.strip()]
    footer = "\n".join(lines[-FOOTER_LINES:])
    in_footer = bool(FINAL.search(footer))

    missing: list[str] = []

    if not shas:
        missing.append("no contract identity (sha256 first 16 hex)")
    elif len(set(s.lower() for s in shas)) > 1:
        missing.append(f"{len(shas)} different contract identities reported: "
                       + ", ".join(sorted(set(s.lower() for s in shas))))

    if not recs:
        missing.append("no final recommendation")
    else:
        distinct = sorted(set(recs))
        if len(distinct) > 1:
            missing.append("contradictory final recommendations: " + ", ".join(distinct))
        elif len(recs) > 1:
            missing.append(f"the final recommendation appears {len(recs)} times; "
                           "a verdict is stated once")
        elif distinct[0] not in RECOMMENDATIONS:
            missing.append(f"final recommendation {distinct[0]!r} is not one of "
                           + ", ".join(RECOMMENDATIONS))
        elif not in_footer:
            missing.append("the final recommendation is not in the closing lines; "
                           "text after it walks the verdict back")

    sha16 = shas[0].lower() if shas else None
    if expected_sha16 and sha16 and sha16 != expected_sha16.lower():
        missing.append(f"the report reviewed contract {sha16}, but the contract under "
                       f"review is {expected_sha16.lower()} - this review is about "
                       "different bytes")

    return {
        "complete": not missing,
        "sha16": sha16,
        "recommendation": recs[0] if len(set(recs)) == 1 else None,
        "expected_sha16": expected_sha16.lower() if expected_sha16 else None,
        "missing": missing,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Check that a closure review reached one verdict about the right contract.")
    ap.add_argument("--report", required=True, help="the report file to inspect")
    ap.add_argument("--contract", default=None,
                    help="the exact REVISED_CONTRACT.json the review was given; its "
                         "sha256 must match the identity the report states")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        text = Path(args.report).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"cannot read {args.report}: {exc}", file=sys.stderr)
        return 2

    expected = None
    if args.contract:
        try:
            expected = contract_sha16(Path(args.contract).read_bytes())
        except OSError as exc:
            print(f"cannot read {args.contract}: {exc}", file=sys.stderr)
            return 2

    result = inspect(text, expected)
    if result["complete"]:
        if not args.quiet:
            bound = f", contract {result['sha16']}" + (" (verified)" if expected else "")
            print(f"closure review complete: {result['recommendation']}{bound}")
        return 0

    print(f"closure review NOT ACTIONABLE - {args.report}", file=sys.stderr)
    for reason in result["missing"]:
        print(f"  - {reason}", file=sys.stderr)
    head = "\n      ".join(text.strip().splitlines()[:5])
    print(f"  report begins:\n      {head}", file=sys.stderr)
    return 7


if __name__ == "__main__":
    raise SystemExit(main())
