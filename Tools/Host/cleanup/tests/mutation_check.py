"""Break safe_delete.py on purpose; every break must turn some test red.

A guard with green tests proves nothing until you show the tests can fail. This
harness works on a COPY in a temp dir - never the live tool - so killing it
mid-run cannot leave C:\\NSC\\tools\\cleanup\\safe_delete.py with a guard disabled.

Run:  python -B tests/mutation_check.py     (from C:\\NSC\\tools\\cleanup)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent / "safe_delete.py"
TESTS = HERE / "test_safe_delete.py"

# (label, find, replace) - each must make at least one test fail.
MUTATIONS = [
    ("depth floor lowered to 0 (guard off)",
     "MIN_ALLOWED_DEPTH = 3",
     "MIN_ALLOWED_DEPTH = 0"),

    ("depth floor lowered to 2 (off by one)",
     "MIN_ALLOWED_DEPTH = 3",
     "MIN_ALLOWED_DEPTH = 2"),

    ("real_path stops resolving junctions",
     "    return Path(os.path.realpath(os.fspath(p)))",
     "    return Path(os.path.abspath(os.fspath(p)))"),

    ("depth test skips the resolved target",
     '    for label, candidate in (("the path given", given), ("its real target", resolved)):',
     '    for label, candidate in (("the path given", given),):'),

    ("depth test skips the path as given",
     '    for label, candidate in (("the path given", given), ("its real target", resolved)):',
     '    for label, candidate in (("its real target", resolved),):'),

    ("is_reparse forgets junctions (the islink trap)",
     "    return bool(junction or q.is_symlink() or os.path.islink(q))",
     "    return bool(q.is_symlink() or os.path.islink(q))"),

    ("reparse points get recursively deleted instead of unlinked",
     '    if report["is_reparse_point"]:',
     "    if False:"),

    ("dry run deletes anyway",
     "        getattr(shutil.rmtree, \"avoids_symlink_attacks\", False))\n    if apply:",
     "        getattr(shutil.rmtree, \"avoids_symlink_attacks\", False))\n    if True:"),

    ("a rootless path is given a depth instead of refused",
     '        raise Refused(f"{q} has no drive or share root, so its depth cannot be "\n'
     '                      "determined. Pass an absolute path.")',
     "        return 99"),

    ("absence reads as permission",
     '    resolved = check_recursive_delete(given)',
     '    resolved = check_recursive_delete(given) if Path(given).exists() else Path(given)'),
]


def run_tests(workdir: Path) -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover",
         "-s", "tests", "-p", "test_safe_delete.py"],
        cwd=str(workdir), capture_output=True, text=True, timeout=300,
    )
    return r.returncode == 0, (r.stdout + r.stderr)


def main() -> int:
    original = TOOL.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="safedel-mut-") as td:
        work = Path(td) / "cleanup"
        (work / "tests").mkdir(parents=True)
        shutil.copy2(TOOL, work / TOOL.name)
        shutil.copy2(TESTS, work / "tests" / TESTS.name)

        ok, out = run_tests(work)
        if not ok:
            print("baseline is RED before any mutation - fix the suite first")
            print(out[-1500:])
            return 1
        print("baseline: green\n")

        caught = 0
        for label, find, replace in MUTATIONS:
            if find not in original:
                print(f"MISSING   {label}\n          anchor not found - mutation is stale")
                continue
            (work / TOOL.name).write_text(original.replace(find, replace, 1), encoding="utf-8")
            ok, out = run_tests(work)
            if ok:
                print(f"SURVIVED  {label}")
                print("          *** no test failed - this guard is not pinned ***")
            else:
                first = next((ln for ln in out.splitlines()
                              if ln.startswith(("FAIL:", "ERROR:"))), "(a test failed)")
                caught += 1
                print(f"caught    {label}")
                print(f"          {first.strip()}")
            (work / TOOL.name).write_text(original, encoding="utf-8")

        print()
        total = len(MUTATIONS)
        print(f"{caught}/{total} mutations caught")
        if caught == total:
            print("every guard in safe_delete.py is pinned by a test")
            return 0
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
