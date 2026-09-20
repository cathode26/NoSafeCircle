#!/usr/bin/env python
"""Revert each 2026-09-18 review fix one at a time; confirm a test goes red.

The review's own closing note was that every finding it raised would pass the
suite as it stood. That is only fixed if each new test really fails without its
fix - a test written after the fix, against the fixed code, proves nothing.

    C:/Python313/python.exe -B tests/review_mutation_check.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITE = HERE / "test_run_job.py"

# The tool is mutated inside a COPY of job-tools, never in place.
#
# The first version rewrote the live run_job.py and restored it in a `finally`.
# A reviewer pointed out what that means: for about twelve seconds at a time,
# the tool other agents run has one guard switched off - and if the harness is
# killed, or hits a tool timeout, `finally` never runs and the disabled guard
# stays on disk silently. A test harness must not be able to leave the live
# tool unsafe.
WORKDIR = Path(os.environ.get("NSC_RUN_JOB_MUTATION_DIR", r"C:\nscrev\tmp\rj-mutation-copy"))
LIVE_TOOL = HERE.parent / "run_job.py"
TOOL = WORKDIR / "run_job.py"


def make_copy() -> None:
    """A throwaway job-tools whose run_job.py is the one we break."""
    import shutil

    if WORKDIR.exists():
        shutil.rmtree(WORKDIR, ignore_errors=True)
    (WORKDIR / "tests").mkdir(parents=True, exist_ok=True)
    shutil.copy2(LIVE_TOOL, TOOL)
    for name in ("test_run_job.py", "fake_claude.py", "fake_docker.py"):
        shutil.copy2(HERE / name, WORKDIR / "tests" / name)

# (label, finding it reverts, old, new, test class that must go red)
MUTATIONS = [
    (
        "is_under back to string comparison",
        "blocking: \\\\?\\ and UNC spellings of the canonical repo passed the clone guard",
        "def is_under(child: Path, parent: Path) -> bool:",
        "def is_under(child: Path, parent: Path) -> bool:\n"
        "    try:\n"
        "        child.resolve().relative_to(parent.resolve())\n"
        "        return True\n"
        "    except (ValueError, OSError):\n"
        "        return False\n"
        "def _unused_is_under(child: Path, parent: Path) -> bool:",
        "ReviewCloneGuardSpellings",
    ),
    (
        "guard_allow_tool is a no-op",
        "blocking: --allow-tool Write/Edit/Bash widened a read-only job type",
        "def guard_allow_tool(rule: str, base_tools: list[str], job_type: str) -> None:",
        "def guard_allow_tool(rule: str, base_tools: list[str], job_type: str) -> None:\n    return",
        "ReviewAllowToolWidening",
    ),
    (
        "guard_tool_list is a no-op",
        "the belt-and-braces pass over the assembled tool list",
        "def guard_tool_list(tools: list[str], base_tools: list[str], job_type: str) -> None:",
        "def guard_tool_list(tools: list[str], base_tools: list[str], job_type: str) -> None:\n    return",
        "ReviewAllowToolWidening",
    ),
    (
        "the Docker login is never really asked",
        "blocking: the account cache failed open, and no test covered the Docker branch",
        "    email = parse_auth_email(proc.stdout or \"\")\n"
        "    return email, f\"the login of the {service} container\"",
        "    return OUTSOURCE_ACCOUNT, f\"the login of the {service} container\"",
        "ReviewAccountCache",
    ),
    (
        "env overrides always apply",
        "major: NSC_RUN_JOB_* could move FORBIDDEN_ROOT and CANONICAL in production",
        "    if not TESTING:\n        _IGNORED_OVERRIDES.append(name)\n        return default",
        "    if False:\n        _IGNORED_OVERRIDES.append(name)\n        return default",
        "ReviewEnvironmentOverrides",
    ),
    (
        "guard_out always mkdirs",
        "major: --dry-run created the jobs directory and the --out folder",
        "    if not dry_run:  # --dry-run changes nothing on disk, folders included\n"
        "        resolved.mkdir(parents=True, exist_ok=True)",
        "    resolved.mkdir(parents=True, exist_ok=True)",
        "ReviewDryRunSideEffects",
    ),
    (
        "traversal names accepted again",
        "minor: --name .. put the job's output in NSCREV itself",
        "    if name.strip(\".\") == \"\":",
        "    if False:",
        "ReviewJobName",
    ),
    (
        "background skips the account guard",
        "major: --background was a way round the guard that decides who pays",
        "        try:\n            who, how = logged_in_account(job)\n"
        "            guard_account(who, how, args.allow_account)\n"
        "        except Refused as exc:\n"
        "            print(f\"REFUSED: {exc}\", file=sys.stderr)\n"
        "            return 2\n        spawn_background(args)",
        "        spawn_background(args)",
        "ReviewBackgroundRefusals",
    ),
    (
        "allow-account and host-reason not forwarded",
        "major: --background --allow-account x silently never ran",
        "                        (\"--allow-account\", args.allow_account),\n"
        "                        (\"--host-reason\", args.host_reason)):",
        "                        ):",
        "ReviewBackgroundRefusals",
    ),
    (
        "child stderr back to DEVNULL",
        "major: a background job that was refused left no trace at all",
        "        child, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,\n"
        "        stderr=handle, creationflags=flags, cwd=str(NSCREV),",
        "        child, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,\n"
        "        stderr=subprocess.DEVNULL, creationflags=flags, cwd=str(NSCREV),",
        "ReviewBackgroundRefusals",
    ),
    (
        "account refusal back to a traceback",
        "minor: the one guard that exited 1 with a traceback instead of REFUSED: and 2",
        "    try:\n        who, how = logged_in_account(job)\n"
        "        spending = guard_account(who, how, args.allow_account)\n"
        "    except Refused as exc:\n"
        "        print(f\"REFUSED: {exc}\", file=sys.stderr)\n"
        "        return 2",
        "    who, how = logged_in_account(job)\n"
        "    spending = guard_account(who, how, args.allow_account)",
        "ReviewAccountRefusalShape",
    ),
    (
        "preflight stdin inherited again",
        "major: auth status blocked until the 300s limit when stdin was a pipe",
        "    if \"input\" not in kwargs:  # subprocess.run rejects stdin and input together\n"
        "        kwargs.setdefault(\"stdin\", subprocess.DEVNULL)",
        "    pass",
        "ReviewSubprocessStdin",
    ),
    (
        "telemetry forgets who paid",
        "major: every --background child recorded account: null",
        "\"account\": (account or {}).get(\"account\") or spending,",
        "\"account\": (account or {}).get(\"account\"),",
        "ReviewTelemetryAttribution",
    ),
    (
        "split_tool_rule_value does not split",
        "blocking (review 2): several rules packed into one --allow-tool value "
        "parsed as a single rule with a greedy specifier",
        "def split_tool_rule_value(value: str) -> list[str]:",
        "def split_tool_rule_value(value: str) -> list[str]:\n    return [value]",
        "ReviewAllowToolWidening",
    ),
    (
        "_bash_specifier_is_unconstrained always says constrained",
        "blocking (review 2): Bash(*), Bash( ), Bash(:*), Bash(**) and bash(*) "
        "reached the argv on advice (Opus, dontAsk, --add-dir C:/NSC)",
        "def _bash_specifier_is_unconstrained(specifier: str | None) -> bool:",
        "def _bash_specifier_is_unconstrained(specifier: str | None) -> bool:\n    return False",
        "ReviewAllowToolWidening",
    ),
    (
        "guard_out only checks one direction",
        "blocking (review 2): --out C:/ (an ancestor of C:\\NSC) passed and "
        "would mount C:\\NSC writable at /out/NSC",
        "    if is_under(resolved, FORBIDDEN_ROOT) or is_under(FORBIDDEN_ROOT, resolved):",
        "    if is_under(resolved, FORBIDDEN_ROOT):",
        "ReviewOutGuard",
    ),
]


def run_class(name: str):
    env = dict(os.environ)
    env["TEMP"] = env["TMP"] = r"C:\nscrev\tmp\rj-mutation"
    env.pop("NSC_RUN_JOB_TESTING", None)
    Path(env["TEMP"]).mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-B", str(WORKDIR / "tests" / "test_run_job.py"), name],
        cwd=str(WORKDIR), capture_output=True, text=True, env=env, timeout=900,
    )
    return proc.returncode == 0, proc.stdout + proc.stderr


def main() -> int:
    make_copy()
    original = TOOL.read_text(encoding="utf-8")
    survivors = []
    try:
        for label, why, old, new, klass in MUTATIONS:
            if old not in original:
                print(f"SKIP      {label}: anchor not found - the mutation is stale")
                survivors.append((label, "anchor not found"))
                continue
            TOOL.write_text(original.replace(old, new, 1), encoding="utf-8", newline="")
            passed, output = run_class(klass)
            if passed:
                print(f"SURVIVED  {label}  ({klass} still green)")
                print(f"          reverts: {why}")
                survivors.append((label, klass))
            else:
                red = [ln for ln in output.splitlines() if ln.startswith(("FAIL:", "ERROR:"))]
                print(f"caught    {label}  -> {klass}: {len(red)} red")
                for line in red[:2]:
                    print(f"              {line}")
    finally:
        # Restoring the copy is tidiness, not safety: the live tool was never
        # touched, so a kill here leaves nothing broken.
        TOOL.write_text(original, encoding="utf-8", newline="")

    print()
    if survivors:
        print(f"{len(survivors)} mutation(s) SURVIVED - pinned by no test:")
        for label, klass in survivors:
            print(f"  - {label} ({klass})")
        return 1
    print(f"all {len(MUTATIONS)} review fixes are pinned by a test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
