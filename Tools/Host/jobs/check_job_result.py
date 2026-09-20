"""Decide whether a provider job actually succeeded. One tested implementation.

Why this exists (audit 20260920-143913): `run_closure_review.sh` stored the provider exit status
in `rc` and never rejected a nonzero value, and its last line was a `grep`, so the SCRIPT's exit
status was grep's. Reproduced with synthetic artifacts:

    provider status 7, report present containing "Final recommendation: ready"  ->  exit 0
    provider status 7, report missing                                           ->  exit 3

So a failed provider run plus a leftover report from an earlier job read as success. That is the
same false-green family as runbook rule 25 (exit 0 is not evidence) and its converse (absence is
not a verdict).

Three things kept separate, because collapsing them is what caused the bug:

  * did the provider process succeed?            (rc)
  * is there a fresh artifact from THIS run?     (mtime/size against a marker)
  * what does the artifact say?                  (the verdict - reported, never the exit status)

Exit codes: 0 success with a fresh report; 4 provider failed; 3 no report; 5 report is stale;
6 report is empty. A verdict of "reject" is NOT a failure here - that is the review's answer,
not the run's.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


class Outcome:
    OK = 0
    NO_REPORT = 3
    PROVIDER_FAILED = 4
    STALE_REPORT = 5
    EMPTY_REPORT = 6


def judge(rc: int, report: Path, started_at: float | None = None) -> tuple[int, str]:
    """Return (exit_code, human message). Pure: no printing, no side effects."""
    if rc != 0:
        extra = ""
        if report.is_file() and report.stat().st_size > 0:
            extra = (" A report file is present, but it cannot be trusted: it may be left over "
                     "from an earlier run. Provider failure wins.")
        return Outcome.PROVIDER_FAILED, f"provider exited {rc}.{extra}"

    if not report.is_file():
        return Outcome.NO_REPORT, (f"provider exited 0 but wrote no report at {report}. "
                                   "Exit 0 means the wrapper ran, not that the work happened.")

    size = report.stat().st_size
    if size == 0:
        return Outcome.EMPTY_REPORT, f"report {report} exists but is empty."

    if started_at is not None and report.stat().st_mtime < started_at:
        return Outcome.STALE_REPORT, (
            f"report {report} was last written before this run started - it is a leftover from "
            "an earlier job, not this one's output.")

    return Outcome.OK, f"provider exited 0 and wrote a fresh {size}-byte report."


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Judge a provider job's real outcome; keep the verdict out of the exit code.")
    ap.add_argument("--rc", type=int, required=True, help="the provider process's exit status")
    ap.add_argument("--report", required=True, help="path the job was told to write")
    ap.add_argument("--started-at", type=float, default=None,
                    help="epoch seconds captured before launching; enables the staleness check")
    ap.add_argument("--verdict-grep", default=None,
                    help="if the run succeeded, print matching lines from the report (FYI only, "
                         "never changes the exit status)")
    args = ap.parse_args(argv)

    code, message = judge(args.rc, Path(args.report), args.started_at)
    stream = sys.stdout if code == Outcome.OK else sys.stderr
    print(("[OK] " if code == Outcome.OK else "[FAILED] ") + message, file=stream)

    if code == Outcome.OK and args.verdict_grep:
        try:
            for line in Path(args.report).read_text(encoding="utf-8", errors="replace").splitlines():
                if args.verdict_grep.lower() in line.lower():
                    print(line.strip())
        except OSError:
            pass  # reporting the verdict must never change the outcome
    return code


if __name__ == "__main__":
    raise SystemExit(main())
