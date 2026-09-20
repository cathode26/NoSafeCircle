#!/usr/bin/env python
"""Prove the tests are not theatre: break one guard at a time, confirm a test fails.

Every mutation below removes a real protection. If the suite still passes, that
protection is pinned by nothing and the test that claims to cover it is a lie.

    C:/Python313/python.exe -B tests/mutation_check.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent / "ask_astra.py"
SUITE = HERE / "test_ask_astra.py"

# (name, what it breaks, old, new, the test class that must go red)
MUTATIONS = [
    (
        "pid probe always says alive",
        "stale locks would never be broken, so one crashed agent blocks Astra forever",
        "def _pid_alive(pid) -> bool:\n    fake =",
        "def _pid_alive(pid) -> bool:\n    return True\n    fake =",
        "Locking",
    ),
    (
        "classify before reading the answer",
        "Astra quoting 'unknown model' in a good answer would exit 4",
        "    if result.answer:\n        _record(asker, question, result, \"answered\", thread_id)",
        "    if _looks_model_unavailable(result):\n        _record(asker, question, result, \"model-unavailable\", thread_id)\n        _err(f\"astra: this Codex CLI cannot reach {MODEL}. {FALLBACK_MESSAGE}\")\n        return EXIT_MODEL_UNAVAILABLE\n    if result.answer:\n        _record(asker, question, result, \"answered\", thread_id)",
        "ExitCodes",
    ),
    (
        "safety guard is a no-op",
        "a --dangerously flag or an unpinned model would reach Codex",
        "def _assert_safe(argv) -> None:\n    joined =",
        "def _assert_safe(argv) -> None:\n    return\n    joined =",
        "Safety",
    ),
    (
        "scan accepts a folder with no binary",
        "'newest by mtime' picks the hash folder that has no codex.exe",
        "        if not exe.is_file():\n            continue",
        "        if False:\n            continue",
        "FindCodex",
    ),
    (
        "argparse keeps its own exit 2",
        "a usage error would be indistinguishable from 'Astra is busy'",
        "        raise SystemExit(EXIT_USAGE)",
        "        raise SystemExit(2)",
        "ExitCodes",
    ),
    (
        "console window not hidden",
        "every question would flash a console on Vincent's screen",
        "            timeout=timeout_seconds,\n            creationflags=CREATE_NO_WINDOW,",
        "            timeout=timeout_seconds,",
        "Safety",
    ),
    (
        "lock acquired without O_EXCL",
        "two agents could hold the thread at once",
        "os.O_CREAT | os.O_EXCL | os.O_WRONLY",
        "os.O_CREAT | os.O_WRONLY",
        "Locking",
    ),
    (
        "stale needs only age, not a dead pid",
        "a live, slow agent's lock would be stolen out from under it",
        "    return _lock_age_seconds(payload) > STALE_LOCK_SECONDS and not _pid_alive(payload.get(\"pid\"))",
        "    return _lock_age_seconds(payload) > STALE_LOCK_SECONDS",
        "Locking",
    ),
    (
        "lock never released",
        "one question would wedge the thread for 30 minutes",
        "    finally:\n        release_lock()",
        "    finally:\n        pass",
        "Locking",
    ),
    (
        "scratch guard runs after mkdir",
        "the folder under C:/NSC is created and only then refused - the original bug",
        "def _out_file(kind: str) -> Path:\n    if _under_forbidden_root(TMP_DIR):",
        "def _out_file(kind: str) -> Path:\n    TMP_DIR.mkdir(parents=True, exist_ok=True)\n    if _under_forbidden_root(TMP_DIR):",
        "Safety",
    ),
    (
        "home is never checked",
        "a forbidden NSC_ASTRA_HOME would write logs and answers under C:/NSC",
        "        _assert_home_safe()\n        return args.func(args)",
        "        return args.func(args)",
        "Safety",
    ),
    (
        "forbidden-root check is case sensitive",
        "c:/nsc/... would slip past a guard written for C:/NSC",
        "    return any(str(p).lower() == forbidden for p in (resolved, *resolved.parents))",
        "    return any(str(p) == str(FORBIDDEN_TEMP_ROOT) for p in (resolved, *resolved.parents))",
        "Safety",
    ),
    (
        "init overwrites an existing thread",
        "a second init would silently discard the shared conversation",
        "        if not args.new:",
        "        if False:",
        "Init",
    ),
]


def run_class(name: str):
    env = dict(os.environ)
    env["TEMP"] = env["TMP"] = r"C:\nscrev\tmp\astra"
    proc = subprocess.run(
        [sys.executable, "-B", str(SUITE), name],
        cwd=str(HERE.parent),
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    return proc.returncode == 0, proc.stdout + proc.stderr


def main() -> int:
    original = TOOL.read_text(encoding="utf-8")
    survivors = []
    try:
        for label, why, old, new, klass in MUTATIONS:
            if old not in original:
                print(f"SKIP  {label}: anchor not found - the mutation itself is stale")
                survivors.append((label, "anchor not found"))
                continue
            TOOL.write_text(original.replace(old, new, 1), encoding="utf-8", newline="")
            passed, output = run_class(klass)
            if passed:
                print(f"SURVIVED  {label}  ({klass} still green)")
                print(f"          would mean: {why}")
                survivors.append((label, klass))
            else:
                failing = [
                    line for line in output.splitlines() if line.startswith(("FAIL:", "ERROR:"))
                ]
                print(f"caught    {label}  -> {klass}: {len(failing)} red")
                for line in failing[:3]:
                    print(f"              {line}")
    finally:
        TOOL.write_text(original, encoding="utf-8", newline="")
        # A mutated run deliberately defeats the scratch guard, so it really does
        # create the folder the guard exists to prevent. Clean up after ourselves:
        # this harness must not be the thing that leaves debris under C:\NSC.
        debris = Path(r"C:\NSC\astra-should-not-happen")
        if debris.exists():
            import shutil

            shutil.rmtree(debris, ignore_errors=True)
            print(f"cleaned up {debris} (created by a mutated run)")

    print()
    if survivors:
        print(f"{len(survivors)} mutation(s) SURVIVED - those guards are pinned by no test:")
        for label, klass in survivors:
            print(f"  - {label} ({klass})")
        return 1
    print(f"all {len(MUTATIONS)} mutations caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
