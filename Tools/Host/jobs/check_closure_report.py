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
    2   an input could not be read, or an argument combination was refused.
    4   the provider process itself failed; nothing it wrote is actionable.
    7   the result is not an actionable review - malformed, incomplete, or about
        something other than what the host supplied.
    8   the contract file changed after the host selected it. New, and the one
        code a caller must not treat as a review outcome: it says the run's
        SUBJECT moved underneath it, so the verdict is about bytes nobody chose.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import review_result  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import closure_record  # noqa: E402


def render(result: review_result.ReviewResult) -> str:
    """The human view, derived from validated fields only.

    It carries `review_result.DERIVED_VIEW_HEADER`, and that marker is load
    bearing rather than decorative: the legacy Markdown reader refuses any text
    containing it. Without that, a reviewer could declare `revise` in JSON while
    writing prose shaped like a finished legacy report approving the contract,
    and the file rendered here would satisfy the legacy checker as a fresh
    approval of what the reviewer had just refused (Astra MJ-P2-01, reproduced
    through both CLIs). The marker is defined once, beside the guard that reads
    it, so the two cannot drift.
    """
    verdict = result.recommendation if result.is_complete else "INCOMPLETE - no recommendation"
    return "\n".join([
        review_result.DERIVED_VIEW_HEADER,
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
    # Astra MJ-P3-03-B, reproduced on the Codex shell path after I fixed the
    # Claude one: the contract was read only AFTER the provider returned, so a
    # provider that edited the fixture got an approval of the bytes it had just
    # written - self-consistent and worthless. The host hashes what it selected
    # BEFORE launching and passes it here. Required with --provider, so the
    # publishing boundary cannot be reached without a pre-launch expectation.
    ap.add_argument("--contract-sha256", default=None,
                    help="the sha256 the host computed BEFORE launching the "
                         "provider; the contract file must still match it")
    ap.add_argument("--task", required=True,
                    help="the task the host asked about, e.g. NSC-001")
    ap.add_argument("--report-out", default=None,
                    help="write the human view of report_markdown here; only "
                         "written when the result validates")
    ap.add_argument("--quiet", action="store_true")
    # The job record. Given these, this publishes it LAST, after every check and
    # after the view is written - so a caller that finds a record knows the whole
    # run succeeded. The shell runner passes its own `$rc` and start time rather
    # than repeating any of these checks in Bash.
    # Codex only. Astra MJ-P3-03-A: this CLI sees a raw result and a process
    # exit status, never a Claude wrapper, so it cannot observe is_error and
    # would have to supply False itself - which is the invented evidence the
    # record exists to prevent. The Claude launchers publish their own record
    # from the wrapper they actually received.
    ap.add_argument("--provider", choices=("codex",),
                    help="publish a job record for a Codex run; requires "
                         "--exit-code and --started-at. Claude runs publish "
                         "through claude_closure_review, which sees the wrapper.")
    ap.add_argument("--exit-code", type=int,
                    help="the provider process's own exit status")
    ap.add_argument("--started-at", type=float,
                    help="Unix seconds captured by the host BEFORE launching")
    ap.add_argument("--session-id", default=None,
                    help="a real session id if the transport reported one; never invented")
    args = ap.parse_args(argv)

    if args.provider and (args.exit_code is None or args.started_at is None):
        ap.error("--provider requires --exit-code and --started-at")
    if args.provider and not args.contract_sha256:
        ap.error("--provider requires --contract-sha256: a record must not be "
                 "published without the host's pre-launch expectation")
    if args.contract_sha256 is not None and (
            len(args.contract_sha256) != 64
            or set(args.contract_sha256) - set("0123456789abcdef")):
        ap.error("--contract-sha256 must be 64 lowercase hex characters")

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

    if args.contract_sha256 is not None and args.contract_sha256 != expected:
        # Refused, not substituted. Binding the verdict to the saved hash would
        # make the result fail its own check and read as a bad review; the truth
        # is that the run is untrustworthy, not that the reviewer was wrong.
        print(f"closure review NOT ACTIONABLE - the contract changed under the run",
              file=sys.stderr)
        print(f"  - the host selected {args.contract_sha256[:16]} before launching",
              file=sys.stderr)
        print(f"  - {args.contract} now hashes to {expected[:16]}", file=sys.stderr)
        return 8

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

    if args.provider and args.exit_code != 0:
        # Checked here as well as by the runner: this is the boundary that
        # publishes, and it must not publish for a run the process said failed.
        print(f"closure review NOT ACTIONABLE - the provider exited "
              f"{args.exit_code}", file=sys.stderr)
        return 4

    view_bytes = b""
    if args.report_out:
        view = render(result)
        Path(args.report_out).write_text(view, encoding="utf-8")
        view_bytes = Path(args.report_out).read_bytes()

    if args.provider:
        if not args.report_out:
            print("--provider needs --report-out: the record hashes the view",
                  file=sys.stderr)
            return 2
        # Same backstop, same reasoning as the Claude launcher: a refusal to
        # overwrite a finished record is correct, and dying with a traceback on
        # an undocumented exit 1 is not how to report it (Fable).
        try:
            closure_record.publish(Path(args.result), closure_record.build(
                task_id=args.task,
                provider=args.provider,
                reviewed_artifact_sha256=expected,
                result_bytes=raw,
                view_bytes=view_bytes,
                exit_code=args.exit_code,
                # Codex's transport reports no is_error; saying null is the honest
                # record, and the reader requires exactly that for this provider.
                is_error=None if args.provider == "codex" else False,
                started_at=args.started_at,
                completed_at=time.time(),
                review_status=result.review_status,
                session_id=args.session_id))
        except closure_record.RecordError as refusal:
            print(f"cannot publish the job record: {refusal}", file=sys.stderr)
            return 2

    if not args.quiet:
        print(f"closure review complete: {result.recommendation}, "
              f"contract {result.reviewed_artifact_sha256[:16]} (verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
