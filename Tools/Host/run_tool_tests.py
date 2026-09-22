#!/usr/bin/env python
"""Run every host tool suite. The one documented command, and what CI calls.

    python -B Tools/Host/run_tool_tests.py            # everything
    python -B Tools/Host/run_tool_tests.py jobs art   # only those families

Why this exists rather than a glob plus `python <file>`:

1. **A suite that runs nothing must fail.** On 2026-09-20 the six ArtReview
   suites exited non-zero on `ModuleNotFoundError: No module named 'art_review'`
   and a first pass recorded them as passing, because it read the exit status of
   a grep through a pipe instead of the interpreter's. Thirty-eight tests were
   invisible. So every suite here must print a `Ran N tests` line AND exit 0;
   either one alone is not a pass, and N == 0 is a failure.

2. **Suites do not agree on how to be invoked.** ArtReview needs its package
   root importable; `python tests/test_gif.py` puts `tests/` on sys.path, not
   the parent, so running it from the right directory is not enough. That is a
   property of each suite, recorded here once instead of rediscovered.

3. **The list is explicit, not globbed.** A suite that is deleted or renamed
   should break this file loudly rather than quietly stop being run.

4. **The verdict is unittest's closing summary, not text found in the stream.**
   Astra round 2 found strict skip mode bypassable: a suite printing
   `skipped=0` anywhere above its real `OK (skipped=2)` passed, because the
   first match won. Counts are now read only from the last `Ran N tests` block
   and the verdict line under it. This file had no tests of its own until that
   finding - the runner every other suite's result passes through was the one
   unguarded thing here - so `tests/test_run_tool_tests.py` exists now too.

No network, no provider, no Docker, no Unity, no paid calls. Every suite writes
its fixtures to a temporary directory.
"""
from __future__ import annotations

import os
import re
import concurrent.futures
import shutil
import subprocess
import tempfile
import sys
import time
from pathlib import Path

HOST = Path(__file__).resolve().parent      # <repo>/Tools/Host
REPO = HOST.parent.parent                   # <repo>

# family -> (suite path relative to repo, cwd relative to repo, extra sys.path)
ART = HOST / "art" / "ArtReview"
SUITES: list[tuple[str, Path, Path, Path | None]] = [
    ("paths", HOST / "tests" / "test_nsc_paths.py", HOST / "tests", None),
    ("runner", HOST / "tests" / "test_run_tool_tests.py", HOST / "tests", None),
    ("result", HOST / "tests" / "test_review_result.py", HOST / "tests", None),
    ("deploy", HOST / "tests" / "test_deploy_tools.py", HOST / "tests", None),
    ("cleanup", HOST / "cleanup" / "tests" / "test_safe_delete.py",
     HOST / "cleanup" / "tests", None),
    ("art", ART / "tests" / "test_analysis_ledger_sheets.py", ART, ART),
    ("art", ART / "tests" / "test_cli.py", ART, ART),
    ("art", ART / "tests" / "test_fix2.py", ART, ART),
    ("art", ART / "tests" / "test_gif.py", ART, ART),
    ("art", ART / "tests" / "test_png_camera.py", ART, ART),
    ("art", ART / "tests" / "test_review_fixes.py", ART, ART),
    ("astra", HOST / "astra" / "tests" / "test_ask_astra.py",
     HOST / "astra" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_check_job_result.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_check_closure_report.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_mutation_check.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_legacy_readers.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_claude_closure_review.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_closure_record.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_legacy_closure_markdown.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_propagation_check.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_propagation_check_run.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_propagation_check_state.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_resolve_codex.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_run_job.py",
     HOST / "jobs" / "tests", None),
    ("codex-jobs", HOST / "codex-jobs" / "tests" / "test_run_closure_review.py",
     HOST / "codex-jobs" / "tests", None),
    ("session", HOST / "session" / "tests" / "test_compaction_bootstrap.py",
     HOST / "session" / "tests", None),
    ("ger", HOST / "ger" / "tests" / "test_main_write.py",
     HOST / "ger" / "tests", None),
    ("ger", HOST / "ger" / "tests" / "test_ger_round.py",
     HOST / "ger" / "tests", None),
    ("ger", HOST / "ger" / "tests" / "test_ger_node.py",
     HOST / "ger" / "tests", None),
    ("ger", HOST / "ger" / "tests" / "test_apply_contract.py",
     HOST / "ger" / "tests", None),
    ("ger", HOST / "ger" / "tests" / "test_ger_decision_revision.py",
     HOST / "ger" / "tests", None),
]

# unittest reports a skip inside OK, so a suite that has quietly stopped covering
# something looks identical to one that still does - the false green this runner
# exists to catch, one layer down. NSC_TOOL_TESTS_NO_SKIPS=1 makes any skip a
# failure, which is what CI sets, because the cases that skip are the guard cases.
#
# Astra round 2, finding 2: that enforcement was bypassable. It searched the
# whole stream for "skipped=" and took the FIRST hit, so a suite printing
# "fixture baseline: skipped=0" anywhere above its real summary satisfied strict
# mode while unittest had said OK (skipped=2). Same root cause as the closure
# checker - recognising a fragment rather than reading the result.
#
# unittest closes every run with these lines, in this order:
#
#     Ran 42 tests in 0.040s
#
#     OK (skipped=2)
#
# so the verdict is found from the LAST "Ran" line, never from the stream.
RAN = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)
VERDICT = re.compile(r"^(OK|FAILED)(?:\s*\((?P<counts>[^)]*)\))?\s*$", re.MULTILINE)
COUNT = re.compile(r"([a-z]+(?:\s+[a-z]+)*)\s*=\s*(\d+)")
NO_SKIPS = os.environ.get("NSC_TOOL_TESTS_NO_SKIPS") == "1"


def terminal_summary(text: str) -> tuple[int | None, str | None, dict[str, int]]:
    """unittest's own closing summary: (tests run, OK or FAILED, its counts).

    The LAST one in the stream. A suite that shells out to another suite prints
    more than one, and only the outermost - the last to finish - is this
    suite's verdict. Counts come from the verdict line's parenthetical and from
    nowhere else, which is what makes the masking case above impossible rather
    than merely unlikely.
    """
    runs = list(RAN.finditer(text))
    if not runs:
        return None, None, {}

    last = runs[-1]
    tests = int(last.group(1))
    verdict = VERDICT.search(text, last.end())
    if verdict is None:
        return tests, None, {}

    counts = {name.strip(): int(number)
              for name, number in COUNT.findall(verdict.group("counts") or "")}
    return tests, verdict.group(1), counts


def run_one(suite: Path, cwd: Path, extra_path: Path | None, timeout: int,
            temp_root: Path | None = None):
    """(ok, tests, detail). ok requires exit 0 AND a positive Ran count."""
    if not suite.exists():
        return False, 0, "suite file is missing"
    env = dict(os.environ)
    if temp_root is not None:
        # A private temp root per suite. Suites run concurrently now, and at
        # least three of them write temp under a fixed path - two sharing a root
        # would collide and read as flakiness rather than as the collision it is.
        temp_root.mkdir(parents=True, exist_ok=True)
        env["TEMP"] = env["TMP"] = str(temp_root)
        env["PYTHONPYCACHEPREFIX"] = str(temp_root / "pycache")
    if extra_path is not None:
        env["PYTHONPATH"] = os.pathsep.join(
            [str(extra_path)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    try:
        # Merged at the pipe, not reassembled afterwards. Astra round 3: both
        # concatenating and joining the two captured streams put ALL stdout
        # before ALL stderr, which destroys execution order - so a nested
        # suite's inner summary could appear after the outer one and win the
        # "last summary" rule below. Ordering has to be real, not inferred.
        # -u as well as merging: Python block-buffers stdout when it is a pipe
        # but keeps stderr line-buffered, so a suite that prints a captured
        # child result during a test has that text flushed at EXIT - after its
        # own summary. Merging the streams made the order real only for stderr.
        # Astra round 4 reproduced the outer suite's skip vanishing behind an
        # inner "OK". Unbuffered, arrival order is execution order.
        proc = subprocess.run(
            [sys.executable, "-B", "-u", str(suite)], cwd=str(cwd), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, 0, f"timed out after {timeout}s"

    text = proc.stdout or ""
    tests, verdict, counts = terminal_summary(text)
    skipped = counts.get("skipped", 0)

    if tests is None:
        tail = "\n      ".join(text.strip().split("\n")[-3:]) or "(no output)"
        return False, 0, f"ran no tests (exit {proc.returncode})\n      {tail}"
    if tests == 0:
        return False, 0, f"collected 0 tests (exit {proc.returncode})"
    if proc.returncode != 0:
        fails = "; ".join(re.findall(r"^(?:FAIL|ERROR): (\S+)", text, re.MULTILINE)[:5])
        also = f", {skipped} also skipped" if skipped else ""
        return False, tests, f"exit {proc.returncode}{also}: {fails or 'see output'}"
    if verdict is None:
        return False, tests, ("the suite printed a test count but no OK or FAILED "
                              "line, so there is no verdict to trust")
    if verdict != "OK":
        return False, tests, f"unittest said {verdict} but the process exited 0"
    if skipped and NO_SKIPS:
        return False, tests, (f"{skipped} test(s) skipped, and skips are not "
                              "allowed here; the cases that skip are the guard cases")
    return True, tests, f"{skipped} skipped" if skipped else ""


def workers() -> int:
    """How many suites to run at once.

    Each one is a subprocess that spends most of its life waiting on git,
    another subprocess, or a deliberate timeout, so this can exceed the core
    count. Capped anyway, and NSC_TOOL_TESTS_WORKERS=1 restores the old
    one-at-a-time behaviour for anyone bisecting a suite interaction.
    """
    from_env = os.environ.get("NSC_TOOL_TESTS_WORKERS")
    if from_env and from_env.isdigit() and int(from_env) > 0:
        return int(from_env)
    return max(1, min(8, (os.cpu_count() or 2)))


def main() -> int:
    wanted = {a.lower() for a in sys.argv[1:]}
    selected = [s for s in SUITES if not wanted or s[0] in wanted]
    if wanted and not selected:
        print(f"no suites match {sorted(wanted)}; known families: "
              f"{sorted({s[0] for s in SUITES})}")
        return 2

    print(f"{len(selected)} suites, interpreter {sys.executable}")
    print(f"repo {REPO}\n")

    failures, skipped_in, total, started = [], [], 0, time.time()
    width = workers()
    print(f"running {width} at a time\n" if width > 1 else "")

    with tempfile.TemporaryDirectory(prefix="tool-tests-") as scratch:
        pending = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=width) as pool:
            for index, (family, suite, cwd, extra) in enumerate(selected):
                root = Path(scratch) / f"suite{index:02d}"
                pending[suite] = pool.submit(run_one, suite, cwd, extra, 900, root)

            # Reported in TABLE order, not completion order: a run stays
            # diffable against the last one, and nobody reads scheduling as
            # significance. `.result()` blocks on each in turn, which is
            # exactly the order we want to print.
            for family, suite, cwd, extra in selected:
                rel = suite.relative_to(REPO).as_posix()
                print(f"  {rel} ... ", end="", flush=True)
                ok, tests, detail = pending[suite].result()
                total += tests
                if ok:
                    print(f"OK ({tests})" + (f" - {detail}" if detail else ""))
                    if detail:
                        skipped_in.append((rel, detail))
                else:
                    print(f"FAILED - {detail}")
                    failures.append((family, rel, detail))

    elapsed = time.time() - started
    print(f"\n{total} tests across {len(selected)} suites in {elapsed:.0f}s")
    if failures:
        print(f"\n{len(failures)} suite(s) FAILED:")
        for family, rel, detail in failures:
            print(f"  [{family}] {rel}: {detail}")
        return 1
    if skipped_in:
        print("")
        print("suites with skipped tests - coverage is quietly reduced:")
        for rel, detail in skipped_in:
            print(f"  {rel}: {detail}")
        print("  set NSC_TOOL_TESTS_NO_SKIPS=1 to make these a failure")
    print("all suites passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
