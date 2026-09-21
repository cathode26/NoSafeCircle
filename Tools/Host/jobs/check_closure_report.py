#!/usr/bin/env python
"""Did the closure review reach ONE verdict, about the RIGHT contract?

check_job_result.py answers three narrower questions - did the process succeed,
is the artifact fresh, what does it say - and answers them correctly. It does
not know what a *closure review* must contain, and should not.

Three rounds of findings shaped this file, and the third one is the reason it
looks the way it does.

Round 0 asked only "are the markers present".

Round 1 (Astra, on `17cf1f4c5`) showed that is a much weaker question: `.search`
returned the FIRST match, so a report recommending `commit_contract` and later
`revise` passed as `commit_contract`; a refusal placed after a well-formed
footer still passed; and ANY 16 hex characters satisfied the identity, so a
review of a DIFFERENT revision read as a clean pass. The fix added a pattern for
contradiction, a three-line window for trailing text, and a hash binding.

Round 2 (Astra, on `08c3ff8ea`) found five more shapes that still passed *with
the correct contract hash*: a one- or two-line retraction after the footer; a
verdict inside a fenced block or a block quote; the template's own options line
`commit_contract | commit_contract_then_decompose | revise` echoed back without
choosing; `commit_contract2`; and two identical identity lines.

**Its root cause is worth more than its list:** the checker "recognised matching
text fragments rather than establishing an unambiguous result". A pattern per
counterexample is how round 1 produced round 2. So this file no longer searches
a string - it reads a document:

  1. lines inside fenced blocks or block quotes are EXAMPLES, and a verdict
     written in an example is not a verdict;
  2. a field label is counted by OCCURRENCE, not by distinct value - two lines
     claiming the same contract are two claims, and one of them may be stale;
  3. whatever follows the colon IS the value, entire. Scooping the first word
     out of it is what let an options list read as a choice and
     `commit_contract2` read as `commit_contract`;
  4. the recommendation must be the LAST non-blank line of the report. Round 1
     allowed a three-line window so a short sign-off would pass, and that
     window is exactly what a one-line retraction fitted inside. Nothing in the
     text distinguishes "Reviewed by Astra." from "Disregard the above." - so
     nothing may follow the verdict.

Every round-2 counterexample falls out of those four, rather than each having
its own rule. The prompt template was corrected in the same commit to end at
the recommendation, because a checker cannot demand a terminal verdict while
the format it is given shows a line after it.

What round 2 confirmed CORRECT, and must not be re-litigated: the hash binding
to the contract bytes, CRLF/BOM/case/terminal-punctuation tolerance, and
putting the identity before the recommendation.

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

# The field labels. Tolerant of markdown emphasis, strict about the colon: a
# label without one is prose ("I would normally give a Final recommendation
# here").
#
# These are deliberately NOT anchored to the start of the line. "On reflection,
# Final recommendation: revise" is a second verdict, and a checker that cannot
# see it picks a side in a contradiction - which is round 1's finding 1a.
IDENTITY = re.compile(
    r"(?:revised\s+contract\s+)?sha256\s*\(\s*first\s*16\s*hex\s*\)\s*\**\s*:",
    re.IGNORECASE)
RECOMMENDATION = re.compile(r"final\s+recommendation\s*\**\s*:", re.IGNORECASE)

# Block-level structure. An opening fence is closed only by the same character,
# at least as long, alone on its line; an unclosed fence therefore swallows the
# rest of the report, and the review is refused for having no verdict. That is
# the safe direction.
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*(.*)$")
QUOTE = re.compile(r"^\s{0,3}>")

HEX16 = re.compile(r"^[0-9a-fA-F]{16}$")


def contract_sha16(data: bytes) -> str:
    """The first 16 hex characters of the contract's SHA-256, as the prompt asks."""
    return hashlib.sha256(data).hexdigest()[:16]


def report_lines(text: str) -> dict[int, str]:
    """Line number -> content, for the lines that are the report SPEAKING.

    Fenced blocks and block quotes are where a report shows you something -
    the template it was given, a bad example, the format it was asked for.
    Excluding them is the difference between reading a document and searching
    a string, and it is what makes "a verdict inside an example" stop being a
    special case that needs its own rule.
    """
    speaking: dict[int, str] = {}
    fence: tuple[str, int] | None = None

    for number, line in enumerate(text.splitlines()):
        opener = FENCE.match(line)
        if fence is not None:
            if (opener and opener.group(1)[0] == fence[0]
                    and len(opener.group(1)) >= fence[1]
                    and not opener.group(2).strip()):
                fence = None
            continue
        if opener:
            fence = (opener.group(1)[0], len(opener.group(1)))
            continue
        if QUOTE.match(line):
            continue
        speaking[number] = line

    return speaking


def field_occurrences(speaking: dict[int, str],
                      label: re.Pattern[str]) -> list[tuple[int, str]]:
    """Every place the report states this field: (line number, rest of line)."""
    return [(number, line[m.end():])
            for number, line in sorted(speaking.items())
            for m in label.finditer(line)]


def stated_value(rest: str) -> str:
    """The value a field line states: everything after the colon, undecorated.

    Markdown emphasis and one terminal punctuation mark come off, because
    round 2 confirmed that tolerance is correct. Nothing else does. In
    particular this does NOT pull the first word out of the remainder, which is
    what let `commit_contract | commit_contract_then_decompose | revise` read as
    a choice and `commit_contract2` read as `commit_contract`. A value with a
    space in it is not one value, and saying so is the whole point.
    """
    value = rest.strip().strip("*_`").strip()
    return value.rstrip(".;,").strip()


def last_content_line(lines: list[str]) -> int:
    """The last line with anything on it, or -1."""
    for number in range(len(lines) - 1, -1, -1):
        if lines[number].strip():
            return number
    return -1


def inspect(text: str, expected_sha16: str | None = None) -> dict:
    """What the report contains, and whether that is one verdict worth acting on."""
    text = (text or "").lstrip("﻿")
    lines = text.splitlines()
    speaking = report_lines(text)

    identities = field_occurrences(speaking, IDENTITY)
    recommendations = field_occurrences(speaking, RECOMMENDATION)

    missing: list[str] = []

    sha16: str | None = None
    if not identities:
        missing.append("no contract identity (sha256 first 16 hex)")
    elif len(identities) > 1:
        values = sorted({stated_value(rest).lower() for _, rest in identities})
        if len(values) > 1:
            missing.append(f"{len(identities)} different contract identities reported: "
                           + ", ".join(values))
        else:
            missing.append(f"the contract identity appears {len(identities)} times; "
                           "a review states which contract it read once")
    else:
        value = stated_value(identities[0][1])
        if HEX16.match(value):
            sha16 = value.lower()
        else:
            missing.append(f"the contract identity reads {value!r}, which is not "
                           "sixteen hex characters")

    recommendation: str | None = None
    if not recommendations:
        missing.append("no final recommendation")
    elif len(recommendations) > 1:
        values = sorted({stated_value(rest) for _, rest in recommendations})
        if len(values) > 1:
            missing.append("contradictory final recommendations: " + ", ".join(values))
        else:
            missing.append(f"the final recommendation appears {len(recommendations)} "
                           "times; a verdict is stated once")
    else:
        number, rest = recommendations[0]
        value = stated_value(rest)
        if value not in RECOMMENDATIONS:
            missing.append(f"final recommendation {value!r} is not one of "
                           + ", ".join(RECOMMENDATIONS))
        else:
            recommendation = value
            last = last_content_line(lines)
            if number != last:
                missing.append("the final recommendation is not the last line of the "
                               f"report; it is followed by {lines[last].strip()!r}")

    if expected_sha16 and sha16 and sha16 != expected_sha16.lower():
        missing.append(f"the report reviewed contract {sha16}, but the contract under "
                       f"review is {expected_sha16.lower()} - this review is about "
                       "different bytes")

    return {
        "complete": not missing,
        "sha16": sha16,
        "recommendation": recommendation,
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
