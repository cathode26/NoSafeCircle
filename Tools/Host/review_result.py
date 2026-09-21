#!/usr/bin/env python
"""One reviewer result, declared rather than inferred.

Eight rounds of review on `jobs/check_closure_report.py` all had one shape: the
checker read free-form Markdown and tried to work out which line the reviewer
*intended* as the verdict. Markdown's ways of displaying text without asserting
it are not a closed set - fenced blocks, block quotes, lazy continuation,
indented code, inline spans across lines, escaped delimiters, raw HTML - so each
round closed one shape and the next round found another. That is not a sequence
of bugs. It is what building a recognizer against an open set looks like from
the inside.

So this module does not recognize anything. The reviewer emits one JSON object
with eight required fields, and the only machine decision is `recommendation`.
Narrative lives inside `report_markdown`, where it is a string and nothing else:
a fence in there, an HTML block, an escaped backtick, the literal text
``Final recommendation: revise``, or a whole JSON object, are all just bytes in
a string field. There is no second place a verdict can come from, so there is
nothing to contradict and no contradiction scan to write.

**What a successful `load` proves, exactly:** the reviewer emitted one complete,
structurally valid result for the task, family, artifact kind and artifact bytes
the HOST selected. `decode` alone proves only the first half - that the object is
well formed. The subject is established by `bind`, and `load` is the pairing of
the two; saying "decode" where this means "load" is the confusion that makes a
schema-only bypass look safe. None of them prove the review was competent,
honest, or that its quotations are real. Those remain review defects, and no amount of parsing
finds them. Saying so here is not modesty - a checker that claims more is how a
caller ends up trusting a verdict it should have read.

Two separations that the eight rounds argue for:

1. **Structure and binding are different questions, asked by different calls.**
   `decode()` answers "is this a well-formed result at all", `bind()` answers "is
   it about the thing I asked for". Fusing them is what made every tightening of
   one a loosening of the other. Callers that need both call both; the failures
   are distinguishable because they carry different codes.

2. **Every refusal names its reason.** `ReviewResultError.code` is a fixed
   vocabulary, not prose. Tests assert the code, because a test that only
   asserts "it raised" passes when the fixture is refused by the wrong rule -
   which happened twice in round 2 of the Markdown checker and hid two live
   mutations.

Standard library only, by policy: `run_tool_tests.py` documents pytest as
deliberately absent and the F: rehearsal measured "no pip packages" as a property
of the install. These tools must run from a fresh checkout on another drive with
nothing installed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

__all__ = [
    "DERIVED_VIEW_HEADER",
    "DERIVED_VIEW_MARKER",
    "is_derived_view",
    "ReviewResult",
    "ReviewResultError",
    "load",
    "decode",
    "bind",
    "FAMILIES",
    "ARTIFACT_KINDS",
    "REVIEW_STATUSES",
    "FIELDS",
    "MAX_BYTES",
    "SCHEMA_VERSION",
]

SCHEMA_VERSION = 1

# The marker every rendered human view carries, and the one string the legacy
# Markdown reader refuses on sight.
#
# It lives HERE, in the module both sides already import, because the first
# version of this had the header written out separately in check_closure_report
# and in ger_round - two copies of one rule, which is the exact shape that has
# produced five findings in this codebase already. A guard and the thing it
# guards against must not be able to drift apart.
#
# Why it is needed at all (Astra MJ-P2-01, reproduced): a reviewer can declare
# `revise` in JSON while writing prose that looks like a finished LEGACY report
# recommending commit_contract. The renderer copies that prose verbatim, as it
# should - narrative is opaque. But the generated view then satisfied the legacy
# checker, which read it as a fresh approval of what the reviewer had refused.
# The answer is not to scan the prose; it is to make derived Markdown
# structurally unusable as a legacy decision source.
DERIVED_VIEW_MARKER = "NSC-DERIVED-VIEW-V1"
DERIVED_VIEW_HEADER = (
    f"<!-- {DERIVED_VIEW_MARKER}: rendered from a validated JSON result. This "
    "file is a human view and is NOT a decision source; no tool may read a "
    "verdict out of it. -->"
)


def is_derived_view(text: str) -> bool:
    """Was this text rendered from a validated result rather than written as one?

    **Every legacy reader calls this before interpreting Markdown.** There are
    three - `legacy_closure_markdown.inspect`,
    `ger_round.legacy_round_recommendation` and
    `apply_contract.parse_post_commit_verdict` - and the guard has now been
    missing from one of them twice: MJ-P2-01 found two and fixed both, then
    MJ-P2-06 found the third, connected later, accepting a derived `revise` view
    as `commit_contract`.

    One rule living in several places is this codebase's recurring failure, so
    the membership test is a function rather than a constant each reader spells
    out, and `jobs/tests/test_legacy_readers.py` asserts every reader on that
    list actually refuses - a test that checks the readers rather than my memory
    of them.
    """
    return DERIVED_VIEW_MARKER in (text or "")


def looks_like_result(raw: bytes | str) -> bool:
    """Is this SHAPED like a new-format result, whether or not it parses?

    The one test every legacy reader uses to refuse something it should not be
    reading. It is deliberately structural rather than a parse, because Astra
    MJ-P2-06 found the parse-based version had three holes: a result carrying the
    allowed single BOM failed `json.loads` and fell through to the grep, so did a
    valid object followed by trailing text, and so did anything JSON-shaped but
    malformed. In each case a JSON result had its verdict read out by a Markdown
    grep - `"recommendation": "commit_contract"` contains the word - which is the
    cross-format confusion this protocol exists to remove.

    "Starts with a brace, after at most one BOM and any whitespace" covers all
    three and cannot be satisfied by a genuine legacy report, which begins with
    prose or a heading. It only ever causes a REFUSAL: the forbidden direction is
    retrying a failed JSON parse as Markdown, and this does the opposite.
    """
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
    else:
        text = raw or ""
    if text.startswith(_BOM):
        text = text[1:]
    return text.lstrip().startswith("{")


# One megabyte. A review that needs more than this is not being truncated by a
# limit - it is being generated by something that has stopped following the
# contract, and reading gigabytes to discover that helps nobody.
MAX_BYTES = 1 << 20

# The two vocabularies stay separate, deliberately. `revise` is a closure verdict
# and `needs_design` is a GER verdict; they are not translations of each other,
# and a reader that maps one onto the other invents a decision the reviewer did
# not make. Both sets are copied from the live declarations, not from prose:
# jobs/check_closure_report.py RECOMMENDATIONS, and ger/ger_node.py
# RECOMMENDATIONS with ger/apply_contract.py COMMITTABLE.
FAMILIES: dict[str, tuple[str, ...]] = {
    "closure": ("commit_contract", "commit_contract_then_decompose", "revise"),
    "ger": ("commit_contract", "commit_contract_then_decompose", "needs_design",
            "blocked_not_design", "release_without_change"),
}

ARTIFACT_KINDS = ("contract", "ger_round_output")
REVIEW_STATUSES = ("complete", "incomplete")

FIELDS = ("schema_version", "review_kind", "task_id", "reviewed_artifact_kind",
          "reviewed_artifact_sha256", "review_status", "recommendation",
          "report_markdown")

_HEX = frozenset("0123456789abcdef")
_BOM = chr(0xFEFF)   # named, not embedded: a literal BOM is invisible in every editor


class ReviewResultError(Exception):
    """A refusal with a machine-readable reason.

    `code` is what tests and callers branch on. `message` is for a human reading
    a log. A caller that wants to tell "malformed" from "about the wrong thing"
    reads the code; it must never pattern-match the message.
    """

    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ReviewResult:
    """A decoded, structurally valid result. Not yet known to be about anything."""

    schema_version: int
    review_kind: str
    task_id: str
    reviewed_artifact_kind: str
    reviewed_artifact_sha256: str
    review_status: str
    recommendation: str | None
    report_markdown: str

    @property
    def is_complete(self) -> bool:
        return self.review_status == "complete"

    @property
    def is_committable(self) -> bool:
        """A completed review recommending that the contract be committed.

        Deliberately narrow: `revise`, `needs_design` and `blocked_not_design` are
        completed reviews too. "The review finished" and "the review approved" are
        different facts and a caller that conflates them approves on a refusal.
        """
        return self.is_complete and self.recommendation in (
            "commit_contract", "commit_contract_then_decompose")


def _reject(code: str, message: str) -> None:
    raise ReviewResultError(code, message)


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """json's default keeps the last of a duplicate pair, silently.

    Two `recommendation` keys would then decode as whichever came last, which is
    the JSON spelling of the exact defect round 1 found in the Markdown checker:
    a document asserting two things, read as asserting one.
    """
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            _reject("duplicate_key", f"the key {key!r} appears more than once")
        seen.add(key)
    return dict(pairs)


def _no_constants(token: str) -> object:
    """NaN, Infinity and -Infinity are JavaScript, not JSON. Python accepts them."""
    _reject("nonstandard_number",
            f"{token} is not valid JSON; the decoder accepts it only by extension")
    return None  # unreachable; keeps the callable's contract honest


def _require_str(obj: dict[str, object], field: str) -> str:
    value = obj[field]
    if not isinstance(value, str):
        _reject("wrong_type",
                f"{field} must be a string, got {type(value).__name__}")
    # `"\ud800"` is well-formed JSON and decodes to a lone surrogate, which is a
    # str Python is happy to hold and cannot encode back to UTF-8. Before this
    # check a result carrying one validated, bound, and reported
    # is_committable=True - and then crashed check_closure_report with an
    # unhandled UnicodeEncodeError the moment it wrote the rendered view. A
    # value that cannot be written back out is not a value we accept. Valid
    # surrogate PAIRS decode to a real codepoint and are unaffected.
    try:
        value.encode("utf-8")                    # type: ignore[union-attr]
    except UnicodeEncodeError as exc:
        _reject("lone_surrogate",
                f"{field} contains an escaped unpaired surrogate, which cannot "
                f"be encoded as UTF-8: {exc}")
    return value  # type: ignore[return-value]


def load(raw: bytes, *, task_id: str, review_kind: str, reviewed_artifact_kind: str,
         reviewed_artifact_sha256: str) -> ReviewResult:
    """**The only entry point a consumer should call.** Decode, then bind.

    `decode` and `bind` are separate so their failures are distinguishable and so
    the unit tests can exercise each rule in isolation. That separation must not
    become a bypass: a caller that decodes and acts without binding has checked
    that the reviewer wrote a well-formed object and NOT that the object is about
    the task it launched, which is the more dangerous of the two mistakes and the
    one hash binding exists to stop.

    So every actionable path goes through here. If you find a consumer calling
    `decode` on its own to reach a `recommendation`, that is the defect.
    """
    return bind(decode(raw),
                task_id=task_id,
                review_kind=review_kind,
                reviewed_artifact_kind=reviewed_artifact_kind,
                reviewed_artifact_sha256=reviewed_artifact_sha256)


def decode(raw: bytes) -> ReviewResult:
    """Strictly decode one reviewer result. Structure only - see `bind` for subject.

    Refuses, with these codes: oversize, not_utf8, not_json, parser_limit,
    not_object, duplicate_key, nonstandard_number, missing_field, unknown_field,
    wrong_type, lone_surrogate, unknown_enum, bad_hash_format, empty_report,
    recommendation_on_incomplete, missing_recommendation,
    wrong_family_recommendation.

    It never searches for JSON inside prose and never repairs anything. A fenced
    block around the object, a preamble sentence, or a trailing sign-off are all
    `not_json`, because the contract is one object and nothing else.
    """
    if not isinstance(raw, (bytes, bytearray)):
        _reject("wrong_type", "decode takes the exact bytes the reviewer produced")

    if len(raw) > MAX_BYTES:
        _reject("oversize", f"{len(raw)} bytes exceeds the {MAX_BYTES} byte limit")

    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError as exc:
        _reject("not_utf8", f"not valid UTF-8: {exc}")

    # Exactly one leading BOM is tolerated, because some providers and editors
    # emit it and the alternative is refusing correct results over an invisible
    # byte. A second one is not a BOM, it is content, and json will say so.
    if text.startswith(_BOM):
        text = text[1:]

    try:
        obj = json.loads(text,
                         object_pairs_hook=_no_duplicate_keys,
                         parse_constant=_no_constants)
    except ReviewResultError:
        raise
    except json.JSONDecodeError as exc:
        _reject("not_json", f"not one JSON document: {exc}")
    except ValueError as exc:
        # json.loads raises a bare ValueError for a value the parser can decode
        # syntactically but refuses to build - an integer past CPython's 4300
        # digit conversion limit is the reachable one. It already failed closed,
        # by crashing; a refusal with a code is the same answer, said properly.
        # Deliberately narrow: ValueError only, so a genuine programming error
        # still surfaces as itself instead of being reported as a bad result.
        _reject("parser_limit", f"the decoder refused to build this value: {exc}")

    if not isinstance(obj, dict):
        _reject("not_object",
                f"the result must be one JSON object, got {type(obj).__name__}")

    missing = [f for f in FIELDS if f not in obj]
    if missing:
        _reject("missing_field", "missing required field(s): " + ", ".join(missing))

    unknown = sorted(set(obj) - set(FIELDS))
    if unknown:
        _reject("unknown_field", "unknown field(s): " + ", ".join(unknown))

    version = obj["schema_version"]
    # bool is a subclass of int, so `isinstance(True, int)` is True and a result
    # claiming `"schema_version": true` would otherwise pass as version 1.
    if isinstance(version, bool) or not isinstance(version, int):
        _reject("wrong_type",
                f"schema_version must be an integer, got {type(version).__name__}")
    if version != SCHEMA_VERSION:
        _reject("unknown_enum",
                f"schema_version {version} is not the supported version {SCHEMA_VERSION}")

    review_kind = _require_str(obj, "review_kind")
    if review_kind not in FAMILIES:
        _reject("unknown_enum",
                f"review_kind {review_kind!r} is not one of {sorted(FAMILIES)}")

    task_id = _require_str(obj, "task_id")
    if not task_id:
        _reject("wrong_type", "task_id must not be empty")

    artifact_kind = _require_str(obj, "reviewed_artifact_kind")
    if artifact_kind not in ARTIFACT_KINDS:
        _reject("unknown_enum",
                f"reviewed_artifact_kind {artifact_kind!r} is not one of "
                f"{list(ARTIFACT_KINDS)}")

    digest = _require_str(obj, "reviewed_artifact_sha256")
    if len(digest) != 64 or not set(digest) <= _HEX:
        _reject("bad_hash_format",
                "reviewed_artifact_sha256 must be 64 lowercase hex characters; "
                f"got {len(digest)} character(s)")

    review_status = _require_str(obj, "review_status")
    if review_status not in REVIEW_STATUSES:
        _reject("unknown_enum",
                f"review_status {review_status!r} is not one of {list(REVIEW_STATUSES)}")

    report_markdown = _require_str(obj, "report_markdown")
    if not report_markdown.strip():
        _reject("empty_report",
                "report_markdown must carry the human review, or the reason the "
                "review did not finish")

    recommendation = obj["recommendation"]
    if review_status == "incomplete":
        # An unfinished review has no actionable answer. Letting it carry one is
        # how "the provider died" became indistinguishable from "revise", which
        # is the defect commit b4dedabfb exists to fix.
        if recommendation is not None:
            _reject("recommendation_on_incomplete",
                    "an incomplete review must have recommendation null; it did "
                    f"not finish, so {recommendation!r} is not its conclusion")
    else:
        if recommendation is None:
            _reject("missing_recommendation",
                    "a complete review must name a recommendation")
        if not isinstance(recommendation, str):
            _reject("wrong_type",
                    "recommendation must be a string or null, got "
                    f"{type(recommendation).__name__}")
        allowed = FAMILIES[review_kind]
        if recommendation not in allowed:
            _reject("wrong_family_recommendation",
                    f"{recommendation!r} is not a {review_kind} recommendation; "
                    f"the {review_kind} family is {list(allowed)}")

    return ReviewResult(
        schema_version=version,
        review_kind=review_kind,
        task_id=task_id,
        reviewed_artifact_kind=artifact_kind,
        reviewed_artifact_sha256=digest,
        review_status=review_status,
        recommendation=recommendation,
        report_markdown=report_markdown,
    )


def bind(result: ReviewResult, *, task_id: str, review_kind: str,
         reviewed_artifact_kind: str, reviewed_artifact_sha256: str) -> ReviewResult:
    """Check the result is about what the HOST selected, not what the reviewer chose.

    The four expectations come from the caller, which knows the task it launched
    and hashed the artifact itself. A reviewer that reviewed a different revision,
    a different task, or the wrong kind of artifact produces a structurally
    perfect result about the wrong thing - and before hash binding existed, that
    read as a clean pass.

    Refuses with: task_mismatch, family_mismatch, artifact_kind_mismatch,
    artifact_hash_mismatch. Returns the same result, so callers can chain.
    """
    expected_digest = reviewed_artifact_sha256.lower()
    if len(expected_digest) != 64 or not set(expected_digest) <= _HEX:
        # The caller's own expectation is malformed. Refusing here rather than
        # comparing is deliberate: a comparison against a bad expectation fails
        # as though the REVIEWER were wrong, and sends the reader hunting in the
        # wrong place.
        _reject("bad_hash_format",
                "the expected reviewed_artifact_sha256 must itself be 64 "
                "lowercase hex characters")

    if result.task_id != task_id:
        _reject("task_mismatch",
                f"the result is about task {result.task_id!r}, the host asked "
                f"about {task_id!r}")

    if result.review_kind != review_kind:
        _reject("family_mismatch",
                f"the result declares the {result.review_kind!r} family, the "
                f"host asked for {review_kind!r}")

    if result.reviewed_artifact_kind != reviewed_artifact_kind:
        _reject("artifact_kind_mismatch",
                f"the result reviewed a {result.reviewed_artifact_kind!r}, the "
                f"host supplied a {reviewed_artifact_kind!r}")

    if result.reviewed_artifact_sha256 != expected_digest:
        _reject("artifact_hash_mismatch",
                "the result is about different bytes than the host supplied: "
                f"{result.reviewed_artifact_sha256[:16]}... reviewed, "
                f"{expected_digest[:16]}... supplied")

    return result
