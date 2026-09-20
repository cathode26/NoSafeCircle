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

No network, no provider, no Docker, no Unity, no paid calls. Every suite writes
its fixtures to a temporary directory.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

HOST = Path(__file__).resolve().parent      # <repo>/Tools/Host
REPO = HOST.parent.parent                   # <repo>

# family -> (suite path relative to repo, cwd relative to repo, extra sys.path)
ART = HOST / "art" / "ArtReview"
SUITES: list[tuple[str, Path, Path, Path | None]] = [
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
    ("jobs", HOST / "jobs" / "tests" / "test_propagation_check.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_resolve_codex.py",
     HOST / "jobs" / "tests", None),
    ("jobs", HOST / "jobs" / "tests" / "test_run_job.py",
     HOST / "jobs" / "tests", None),
]

RAN = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)


def run_one(suite: Path, cwd: Path, extra_path: Path | None, timeout: int):
    """(ok, tests, detail). ok requires exit 0 AND a positive Ran count."""
    if not suite.exists():
        return False, 0, "suite file is missing"
    env = dict(os.environ)
    if extra_path is not None:
        env["PYTHONPATH"] = os.pathsep.join(
            [str(extra_path)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    try:
        proc = subprocess.run(
            [sys.executable, "-B", str(suite)], cwd=str(cwd), env=env,
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, 0, f"timed out after {timeout}s"

    text = (proc.stdout or "") + (proc.stderr or "")
    match = RAN.search(text)
    tests = int(match.group(1)) if match else 0

    if match is None:
        tail = "\n      ".join(text.strip().split("\n")[-3:]) or "(no output)"
        return False, 0, f"ran no tests (exit {proc.returncode})\n      {tail}"
    if tests == 0:
        return False, 0, f"collected 0 tests (exit {proc.returncode})"
    if proc.returncode != 0:
        fails = "; ".join(re.findall(r"^(?:FAIL|ERROR): (\S+)", text, re.MULTILINE)[:5])
        return False, tests, f"exit {proc.returncode}: {fails or 'see output'}"
    return True, tests, ""


def main() -> int:
    wanted = {a.lower() for a in sys.argv[1:]}
    selected = [s for s in SUITES if not wanted or s[0] in wanted]
    if wanted and not selected:
        print(f"no suites match {sorted(wanted)}; known families: "
              f"{sorted({s[0] for s in SUITES})}")
        return 2

    print(f"{len(selected)} suites, interpreter {sys.executable}")
    print(f"repo {REPO}\n")

    failures, total, started = [], 0, time.time()
    for family, suite, cwd, extra in selected:
        rel = suite.relative_to(REPO).as_posix()
        print(f"  {rel} ... ", end="", flush=True)
        ok, tests, detail = run_one(suite, cwd, extra, timeout=900)
        total += tests
        if ok:
            print(f"OK ({tests})")
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
    print("all suites passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
