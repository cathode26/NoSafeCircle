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

# A FIELD begins its line. A MENTION is anywhere in one. Astra round 4: the
# column-0 rule said where a field line starts, but the label was still matched
# anywhere inside it, so "The template says `Final recommendation:
# commit_contract`" turned an explicit "I did not complete the review" into an
# approval. Requiring the syntax and detecting contradictions are two different
# questions; conflating them is what produced that hole.
# No leading caret: these patterns are used only through
# field_occurrences, which calls .match(), and .match() anchors at
# position 0 already. Having both meant neither could be mutation-tested,
# because each one covered for the other.
DECORATION = r"[*_#+\-]*\s*\**\s*"
IDENTITY_FIELD = re.compile(DECORATION + IDENTITY.pattern, re.IGNORECASE)
RECOMMENDATION_FIELD = re.compile(DECORATION + RECOMMENDATION.pattern, re.IGNORECASE)

# CommonMark ends a paragraph - and so a block quote's lazy continuation - at
# any new block start, not only at a blank line. Round 3 missed headings and
# thematic breaks, so a heading straight after a quotation swallowed the footer.
BLOCK_START = re.compile(r"^\s{0,3}(?:#{1,6}(?:\s|$)"
                         r"|(?:\*\s*){3,}$|(?:-\s*){3,}$|(?:_\s*){3,}$)")

# Block-level structure. An opening fence is closed only by the same character,
# at least as long, alone on its line; an unclosed fence therefore swallows the
# rest of the report, and the review is refused for having no verdict. That is
# the safe direction.
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*(.*)$")
QUOTE = re.compile(r"^\s{0,3}>")
INDENTED = re.compile(r"^[ \t]")

HEX16 = re.compile(r"^[0-9a-fA-F]{16}$")


# The leading token of a mention: the first word after the label, undecorated.
# Round 5: requiring a mention's ENTIRE remainder to be a valid value meant
# "revise - L1 is unresolved" was thrown away, so attaching a reason to a
# contradiction made the contradiction disappear. A field must be exact; a
# mention only has to be legible.
LEADING_TOKEN = re.compile(r"\s*\**\s*`*\s*([A-Za-z0-9_]+)")


def contract_sha16(data: bytes) -> str:
    """The first 16 hex characters of the contract's SHA-256, as the prompt asks."""
    return hashlib.sha256(data).hexdigest()[:16]


def inline_segments(text: str) -> list[tuple[int, int]]:
    """Offset ranges where inline parsing applies at all.

    A segment is a run of consecutive non-blank lines outside every fenced
    block. Two CommonMark facts make this the right unit: a code span cannot
    contain a blank line, and the contents of a fenced block are not
    inline-parsed. Astra round 6 paired a literal backtick inside a `~~~`
    example with one eight lines below, and the recommendation between them
    disappeared into the resulting "span".
    """
    segments: list[tuple[int, int]] = []
    fence: tuple[str, int] | None = None
    start: int | None = None
    position = 0

    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        opener = FENCE.match(stripped)
        eligible = True

        if fence is not None:
            if (opener and opener.group(1)[0] == fence[0]
                    and len(opener.group(1)) >= fence[1]
                    and not opener.group(2).strip()):
                fence = None
            eligible = False
        elif opener:
            fence = (opener.group(1)[0], len(opener.group(1)))
            eligible = False
        elif not stripped.strip():
            eligible = False

        if eligible:
            if start is None:
                start = position
        elif start is not None:
            segments.append((start, position))
            start = None
        position += len(line)

    if start is not None:
        segments.append((start, position))
    return segments


def code_span_ranges(text: str) -> list[tuple[int, int]]:
    """Character ranges inside inline code spans, over the WHOLE text.

    A span opens on a run of N backticks and closes on the next run of exactly
    N. Unclosed backticks are literal.

    This is not line-based, and that is the point. Astra round 5 showed a span
    opening on one line and closing on the next, with the label between them -
    so the label sat inside a quotation that every line-by-line rule in rounds
    1 to 4 was structurally unable to see.
    """
    spans: list[tuple[int, int]] = []
    for segment_start, segment_end in inline_segments(text):
        spans.extend(_spans_within(text, segment_start, segment_end))
    return spans


def _spans_within(text: str, begin: int, length: int) -> list[tuple[int, int]]:
    """Backtick pairing inside one segment, never across its edges."""
    spans: list[tuple[int, int]] = []
    index = begin

    while index < length:
        if text[index] != "`":
            index += 1
            continue

        run = 1
        while index + run < length and text[index + run] == "`":
            run += 1

        cursor, closed = index + run, False
        while cursor < length:
            if text[cursor] == "`":
                closing = 1
                while cursor + closing < length and text[cursor + closing] == "`":
                    closing += 1
                if closing == run:
                    spans.append((index, cursor + closing))
                    index, closed = cursor + closing, True
                    break
                cursor += closing
            else:
                cursor += 1

        if not closed:
            index += run

    return spans


def line_starts(text: str) -> list[int]:
    """Absolute offset of each line, so a match can be placed in the document."""
    offsets, position = [], 0
    for line in text.splitlines(keepends=True):
        offsets.append(position)
        position += len(line)
    return offsets


def inside_span(offset: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= offset < end for start, end in spans)


def normalise(value: str) -> str:
    """Undecorate a stated value. ONE implementation, called by BOTH paths.

    Astra round 6's root cause was that there were two: the field path stripped
    emphasis and the mention path did not, so `_revise_` was `revise` in the
    footer and `_revise_` in prose, and a contradiction between them could not
    be seen. Any future tolerance belongs here and nowhere else.
    """
    value = value.strip().strip("*_`").strip()
    return value.rstrip(".;,").strip().lower()


def leading_token(rest: str) -> str:
    """The first word a mention names, normalised, or ''."""
    found = LEADING_TOKEN.match(rest)
    return normalise(found.group(1)) if found else ""


def report_lines(text: str) -> dict[int, str]:
    """Line number -> content, for the lines that are the report SPEAKING.

    Astra round 3 rejected the earlier version of this for enumerating example
    containers: it excluded fenced blocks and block quotes, and an INDENTED
    code block and a LAZY BLOCKQUOTE CONTINUATION both still delivered
    actionable verdicts. Adding two more patterns would have been the round-1
    mistake for the third time, because the set of things that look like an
    example is open-ended.

    So the question is inverted. Not "is this inside something example-shaped?"
    but "is this where the template puts a field?" - column 0, outside every
    fence, not in a block quote or its lazy continuation. That set is closed
    and it is defined by the format we hand out, not by Markdown trivia.

    Surveyed before tightening: of 127 field lines across 70 real reports, 126
    are at column 0. The one exception is an indented bullet discussing the
    format, which this must exclude anyway.
    """
    speaking: dict[int, str] = {}
    fence: tuple[str, int] | None = None
    quoting = False

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
            quoting = False
            continue

        if QUOTE.match(line):
            quoting = True
            continue
        if not line.strip():
            quoting = False          # a blank line ends the quote's paragraph
            continue
        if BLOCK_START.match(line):
            quoting = False          # so does a heading or a thematic break
        if quoting:
            continue                 # lazy continuation: still inside the quote
        if INDENTED.match(line):
            continue                 # an example, or continuation text - not a field

        speaking[number] = line

    return speaking


def field_occurrences(speaking: dict[int, str], label: re.Pattern[str],
                      starts: list[int],
                      spans: list[tuple[int, int]]) -> list[tuple[int, str]]:
    """Lines that STATE this field: (line number, rest of line).

    Anchored: the label has to begin the line, allowing only markdown
    decoration before it. A label further in is the report talking ABOUT the
    field, which is `mentions` below, not a statement of it. And a label inside
    a code span is quoted text wherever it sits, including when the span was
    opened on an earlier line.
    """
    out = []
    for number, line in sorted(speaking.items()):
        match = label.match(line)
        if match and not inside_span(starts[number] + match.start(), spans):
            out.append((number, line[match.end():]))
    return out


def mentions(speaking: dict[int, str], label: re.Pattern[str],
             starts: list[int],
             spans: list[tuple[int, int]]) -> list[tuple[int, str]]:
    """Every place the label appears at all, wherever it sits in the line.

    Used only to catch a contradiction. Round 1's finding 1a was a report
    recommending one thing and later, mid-sentence, another; anchored matching
    alone would stop seeing that, which is why Astra asked for the two checks
    to be kept separate rather than merged.
    """
    return [(number, line[m.end():])
            for number, line in sorted(speaking.items())
            for m in label.finditer(line)
            if not inside_span(starts[number] + m.start(), spans)]


def contradicted_by(speaking: dict[int, str], label: re.Pattern[str],
                    starts: list[int], spans: list[tuple[int, int]],
                    field_line: int, field_value: str, allowed) -> list[str]:
    """Values named elsewhere that differ from the one the field states.

    Applied to BOTH fields. Round 5: running it on the recommendation alone
    let a report claim two different contracts and pass, because the losing
    identity was only ever in prose.
    """
    found = set()
    for number, rest in mentions(speaking, label, starts, spans):
        if number == field_line:
            continue
        token = leading_token(rest)
        if token and token != field_value and allowed(token):
            found.add(token)
    return sorted(found)


def stated_value(rest: str) -> str:
    """The value a field line states: everything after the colon, undecorated.

    Markdown emphasis and one terminal punctuation mark come off, because
    round 2 confirmed that tolerance is correct. Nothing else does. In
    particular this does NOT pull the first word out of the remainder, which is
    what let `commit_contract | commit_contract_then_decompose | revise` read as
    a choice and `commit_contract2` read as `commit_contract`. A value with a
    space in it is not one value, and saying so is the whole point.
    """
    return normalise(rest)


def last_content_line(lines: list[str]) -> int:
    """The last line with anything on it, or -1."""
    for number in range(len(lines) - 1, -1, -1):
        if lines[number].strip():
            return number
    return -1


def inspect(text: str, expected_sha16: str | None = None) -> dict:
    """What the report contains, and whether that is one verdict worth acting on."""
    text = (text or "").lstrip("\ufeff")
    lines = text.splitlines()
    speaking = report_lines(text)
    starts = line_starts(text)
    spans = code_span_ranges(text)

    identities = field_occurrences(speaking, IDENTITY_FIELD, starts, spans)
    recommendations = field_occurrences(speaking, RECOMMENDATION_FIELD, starts, spans)

    missing: list[str] = []

    sha16: str | None = None
    if not identities:
        missing.append("no contract identity (sha256 first 16 hex)")
    elif len(identities) > 1:
        values = sorted({stated_value(rest) for _, rest in identities})
        if len(values) > 1:
            missing.append(f"{len(identities)} different contract identities reported: "
                           + ", ".join(values))
        else:
            missing.append(f"the contract identity appears {len(identities)} times; "
                           "a review states which contract it read once")
    else:
        value = stated_value(identities[0][1])
        if HEX16.match(value):
            sha16 = value
            others = contradicted_by(speaking, IDENTITY, starts, spans,
                                     identities[0][0], sha16,
                                     lambda token: bool(HEX16.match(token)))
            if others:
                missing.append(f"{len(others) + 1} different contract identities "
                               "reported: " + ", ".join(sorted([sha16] + others)))
                sha16 = None
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
        # Lower-cased before the comparison. Astra round 2 confirmed case
        # tolerance correct; round 3 caught that this branch had lost it, so
        # COMMIT_CONTRACT passed at 08c3ff8ea and failed here. A regression
        # introduced by the fix, which is what a reviewer is for.
        value = stated_value(rest)          # normalise() lower-cases
        if value not in RECOMMENDATIONS:
            missing.append(f"final recommendation {value!r} is not one of "
                           + ", ".join(RECOMMENDATIONS))
        else:
            stated_elsewhere = contradicted_by(
                speaking, RECOMMENDATION, starts, spans, number, value,
                lambda token: token in RECOMMENDATIONS)
            if stated_elsewhere:
                missing.append("contradictory final recommendations: "
                               f"{value} is stated as the verdict, but "
                               + ", ".join(stated_elsewhere)
                               + " appears elsewhere in the report")
            else:
                recommendation = value
                last = last_content_line(lines)
                if number != last:
                    missing.append("the final recommendation is not the last line "
                                   f"of the report; it is followed by "
                                   f"{lines[last].strip()!r}")

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
