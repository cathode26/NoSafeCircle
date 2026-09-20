#!/usr/bin/env python
"""Revert each 2026-09-18 review fix in propagation_check.py; confirm a test goes red.

Two independent reviews found the same blocking defect, and both closed by
noting that every finding they raised passed the suite as it stood. A test
written afterwards, against the fixed code, proves nothing on its own.

Works on a COPY of job-tools. The live tool is never modified, so being killed
here cannot leave the tool other agents run with a guard switched off.

    C:/Python313/python.exe -B tests/propagation_mutation_check.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE = HERE.parent

# (label, what it reverts, old, new, test class that must go red)
MUTATIONS = [
    (
        "grep_symbols searches the working tree",
        "BLOCKING, found twice independently: stale references looked for in "
        "whatever the clone had checked out",
        'args += [rev, "--", "."]',
        'args += ["--", "."]',
        "WorkingTreeIsNotTheHead",
    ),
    (
        "importing_tests searches the working tree",
        "BLOCKING: test selection from the wrong revision - the false green",
        'rev, "--", "*_test.py", "*test_*.py", "*/tests/*.py", "tests/*.py"]',
        '"--", "*_test.py", "*test_*.py", "*/tests/*.py", "tests/*.py"]',
        "WorkingTreeIsNotTheHead",
    ),
    (
        "workflow_references reads the checked-out workflows",
        "CI marking judged against the clone's current branch, not the range",
        'blobs = cat_file_batch(clone, ["%s:%s" % (rev, wf) for wf in workflows])',
        'blobs = cat_file_batch(clone, ["HEAD:%s" % wf for wf in workflows])',
        "WorkingTreeIsNotTheHead",
    ),
    (
        "workflow listing comes from the index",
        "the set of workflow files taken from the tree rather than the revision",
        '["ls-tree", "-r", "--name-only", rev, "--", WORKFLOW_DIR]',
        '["ls-files", "--", WORKFLOW_DIR]',
        "WorkingTreeIsNotTheHead",
    ),
    (
        "--run runs against whatever is on disk",
        "BLOCKING: --run measured a revision nobody asked about, silently",
        "        if not matches and not allow_tree_mismatch:",
        "        if False:",
        "WorkingTreeIsNotTheHead",
    ),
    (
        "a changed test file is not selected for itself",
        "PR #134 round 4: a range editing a test file selected nothing",
        "        tests.append(SelectedTest(path=entry.path, modules=[\"(changed test file)\"]))",
        "        pass",
        "ChangedTestFileSelectsItself",
    ),
    (
        "a deleted test is selected anyway",
        "selecting a file that no longer exists at head can only error",
        "        if entry.path not in head_paths:\n            continue",
        "        if False:\n            continue",
        "ChangedTestFileSelectsItself",
    ),
    (
        "--run has no timeout again",
        "one hung test blocked the whole run forever",
        "                    returncode = proc.wait(timeout=timeout)",
        "                    returncode = proc.wait()",
        "RunSafety",
    ),
    (
        "the verdict comes from the last line again",
        "a failing suite whose last line said PASS read as passing",
        'status = "timeout" if timed_out else ("pass" if returncode == 0 else "fail")',
        'status = "timeout" if timed_out else '
        '("pass" if "PASS" in last_meaningful_line(output) else "fail")',
        "RunSafety",
    ),
    (
        "the scratch directory leaks again",
        "every --run left a propcheck-* directory behind",
        "        shutil.rmtree(scratch, ignore_errors=True)",
        "        pass",
        "RunSafety",
    ),
    # Round 2 of the review. Every one of these passed the 44 tests that were
    # green when that review started.
    (
        "the report formats a None exit code again",
        "BLOCKING: a timed-out test crashed the whole text report with a TypeError",
        '            shown = "exit %-3d" % code if isinstance(code, int) else "%-8s" % "TIMEOUT"',
        '            shown = "exit %-3d" % code',
        "TimeoutReachesTheReport",
    ),
    (
        "a timeout is not counted as a failure",
        "the header said '0 failed' with a timed-out test in the list",
        'failed = sum(1 for r in runs if r.get("status") != "pass")',
        'failed = sum(1 for r in runs if r.get("exit_code") not in (0, None))',
        "TimeoutReachesTheReport",
    ),
    (
        "a dirty tree counts as the head",
        "a clone at the head commit with edits ran something that is not the head",
        "    dirty = worktree_is_dirty(clone)",
        "    dirty = False",
        "DirtyTreeIsNotTheHead",
    ),
    (
        "the report never mentions the tree mismatch",
        "a reader could take --run-on-current-tree output for the range's result",
        '            add("   !! THESE RESULTS ARE NOT THIS RANGE\'S. The clone was checked out at")',
        '            pass',
        "TheTextReportCarriesTheWarnings",
    ),
    (
        "the report never mentions the missing baseline",
        "a failure read as a regression with nothing saying it might be pre-existing",
        '            add("   !! NO BASELINE: %s" % data["run_caveat"])',
        "            pass",
        "TheTextReportCarriesTheWarnings",
    ),
    (
        "step 5 never warns the files are not on disk",
        "commands offered for files that do not exist in this checkout",
        # Anchored on the guard, not on a format string: a mutation that breaks
        # syntax "catches" for the wrong reason and proves nothing.
        '    if not data.get("worktree_at_head", True):\n        # Without this',
        '    if False:\n        # Without this',
        "TheTextReportCarriesTheWarnings",
    ),
    (
        "only the direct child is killed",
        # The round-2 label said "the timeout waited for it", which stopped
        # being true once output went to a file instead of a pipe: the timeout
        # is prompt either way, and the only red was a tearDown PermissionError
        # from the surviving grandchild holding the fixture open. It is now
        # pointed at the class that actually asserts the grandchild is dead.
        "the grandchild outlives the run - an orphan per timed-out test",
        "                    kill_process_tree(proc)",
        "                    proc.kill()",
        "TheGrandchildIsActuallyDead",
    ),
    # Round 3.
    (
        "renames hide a deleted module",
        "BLOCKING: git reports only the new path, so every name in the old "
        "module looked untouched and --run said 0 run, 0 failed, exit 0",
        '["diff", "--no-renames", "--name-only", "%s..%s" % (base, head)]',
        '["diff", "--name-only", "%s..%s" % (base, head)]',
        "RenamedModuleIsNotInvisible",
    ),
    (
        "untracked python files are not reported",
        "a forgotten git add passes here and fails in a fresh clone",
        '    data["untracked_python_files"] = untracked_python_files(clone)',
        '    data["untracked_python_files"] = []',
        "UntrackedFilesAreReported",
    ),
    (
        "stale workflow test ids are not looked for",
        "a renamed test method left --run reporting success over a red CI command",
        "    stale_ids = stale_workflow_test_ids(clone, head, workflow_text, tests)",
        "    stale_ids = []",
        "StaleWorkflowTestIds",
    ),
    (
        "a stale test id does not fail the check",
        "reporting a known-red CI command while exiting 0",
        '    if data.get("stale_workflow_test_ids"):\n        return 1',
        "    if False:\n        return 1",
        "StaleWorkflowTestIds",
    ),
    (
        "git status refreshes the index again",
        "a tool that calls the clone read-only writing to .git/index",
        '        clone, ["--no-optional-locks", "status", "--porcelain", mode], allowed=(0, 128)',
        '        clone, ["status", "--porcelain", mode], allowed=(0, 128)',
        "TheCloneIsNotWrittenTo",
    ),
    # Round 4. The first four are mutations a reviewer showed SURVIVING the
    # round-3 suite, because its only false-positive guard analysed an empty
    # range and never reached the comparison at all.
    (
        "class bindings are always empty",
        "every workflow test id reported stale - exit 1 over green CI",
        "        bindings[node.name] = None if node.name in bindings else names",
        "        bindings[node.name] = set()",
        "StaleIdsHaveNoFalsePositives",
    ),
    (
        "the Class.method shape filter is dropped",
        "`module.Class` alone read as a method id",
        '            if suffix.count(".") != 1:\n                continue',
        "            if False:\n                continue",
        "StaleIdsHaveNoFalsePositives",
    ),
    (
        "module prefix matched without the dot",
        "pkg.tests.test_view claiming ids that belong to pkg.tests.test_viewer",
        '            if not candidate.startswith(module + "."):',
        "            if not candidate.startswith(module):",
        "StaleIdGuardsAreNotVacuous",
    ),
    (
        "the stale check reads HEAD instead of the revision",
        "the round-1 blocking class, in code written after round 1",
        '    stale_ids = stale_workflow_test_ids(clone, head, workflow_text, tests)',
        '    stale_ids = stale_workflow_test_ids(clone, "HEAD", workflow_text, tests)',
        "StaleIdGuardsAreNotVacuous",
    ),
    (
        "mixin and computed bases are trusted anyway",
        "six LIVE ids reported stale: mixin methods, aliases, factory-built "
        "methods, defs inside an if. Re-anchored after round 6 folded the "
        "decorator check into the same guard - the old anchor went stale and "
        "the mutation SKIPped, leaving this guard pinned by nothing.",
        "        if node.decorator_list or not _plain_test_case_bases(node):\n"
        "            names: Optional[Set[str]] = None",
        "        if False:\n"
        "            names: Optional[Set[str]] = None",
        "StaleIdsHaveNoFalsePositives",
    ),
    (
        "only the class's own body is scanned",
        "a class nested under a module-level if is never found",
        "    for node in ast.walk(tree):\n        if not isinstance(node, ast.ClassDef):",
        "    for node in tree.body:\n        if not isinstance(node, ast.ClassDef):",
        "StaleIdsHaveNoFalsePositives",
    ),
    (
        "workflow comments are not stripped",
        "a retired, commented-out CI line reported as a stale id",
        "    for candidate in DOTTED_TEST_ID.findall(strip_yaml_comments(workflow_text)):",
        '    for candidate in DOTTED_TEST_ID.findall(workflow_text or ""):',
        "StaleIdsHaveNoFalsePositives",
    ),
    (
        "an __init__.py package owns Class.method ids",
        "pkg.tests claiming pkg.tests.test_viewer.ViewerTests",
        '        if test.path.endswith("__init__.py"):\n            continue',
        "        if False:\n            continue",
        "StaleIdsHaveNoFalsePositives",
    ),
    (
        "untracked listing collapses directories again",
        "a new untracked PACKAGE invisible - the commonest forgotten git add",
        '    mode = "--untracked-files=all" if untracked else "--untracked-files=no"',
        '    mode = "--untracked-files=normal" if untracked else "--untracked-files=no"',
        "UntrackedPackageIsSeen",
    ),
    # Round 6. Three more false-positive shapes review5 found: methods added
    # to a class from OUTSIDE its body, which the per-class scan cannot see.
    (
        "a class decorator is trusted anyway",
        "a method-adding decorator (e.g. @add_cases) left unverifiable, so "
        "the method it adds is reported as a stale id",
        "        if node.decorator_list or not _plain_test_case_bases(node):",
        "        if not _plain_test_case_bases(node):",
        "StaleIdsHaveNoFalsePositives",
    ),
    (
        "a setattr loop after the class is trusted anyway",
        "the usual parametrise idiom - setattr(Cls, \"test_\" + n, fn) - left "
        "unverifiable, so a live parametrised test is reported as a stale id",
        '            if isinstance(func, ast.Name) and func.id == "setattr" and node.args:',
        "            if False:",
        "StaleIdsHaveNoFalsePositives",
    ),
    (
        "an attribute assigned after the class body is dropped",
        "`Cls.name = fn` after the class body found but never recorded, so "
        "the live method it names is reported as a stale id",
        "                bindings[class_name].add(target.attr)",
        "                pass",
        "StaleIdsHaveNoFalsePositives",
    ),
]


# Mutations expected to SURVIVE, because a different guard already covers the
# case and no honest input can reach them. Listing them is the point: an
# unexplained survivor is a hole, and a survivor with a reason is defence in
# depth. Each entry must say which guard covers it, and a NEW survivor not
# named here still fails this harness.
EXPECTED_REDUNDANT = {
    "module prefix matched without the dot":
        "`suffix.count('.') != 1` drops the mis-split id first, and any class "
        "name it could invent is not in the module, so the not-found guard "
        "skips it. Kept because it is one character and states the intent.",
    "an __init__.py package owns Class.method ids":
        "an __init__.py defines no classes, so the not-found guard skips the "
        "id. Firing would need a class in __init__.py named after a sibling "
        "module, with plain TestCase bases. Kept because the package is never "
        "the owner of a Class.method id and saying so is cheaper than relying "
        "on that.",
}


def run_class(workdir: Path, name: str, temp: Path):
    env = dict(os.environ)
    env["TEMP"] = env["TMP"] = str(temp)
    proc = subprocess.run(
        [sys.executable, "-B", str(workdir / "tests" / "test_propagation_check.py"), name],
        cwd=str(workdir), capture_output=True, text=True, env=env, timeout=900,
    )
    return proc.returncode == 0, proc.stdout + proc.stderr


def main() -> int:
    # ignore_cleanup_errors: a mutation that deliberately fails to kill the
    # process tree leaves a grandchild holding a log file open, and Windows
    # then refuses to delete it. That is the mutation working, not a failure
    # of the harness - but it must not become the harness's own traceback.
    scratch = tempfile.TemporaryDirectory(
        prefix="propcheck-mutation-", ignore_cleanup_errors=True
    )
    # ignore_cleanup_errors leaves a directory behind when a mutated run left a
    # process holding a file. Sweep any survivors from earlier runs, which by
    # now have no live holder, so this harness does not accumulate them.
    for stale in Path(tempfile.gettempdir()).glob("propcheck-mutation-*"):
        if stale.name != Path(scratch.name).name:
            shutil.rmtree(stale, ignore_errors=True)
    workdir = Path(scratch.name) / "job-tools"
    temp = Path(scratch.name) / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        LIVE, workdir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.bak.py"),
    )
    tool = workdir / "propagation_check.py"
    original = tool.read_text(encoding="utf-8")
    print(f"copied job-tools to {workdir} (the live tool is never modified)")

    classes = sorted({klass for *_rest, klass in MUTATIONS})
    print("baseline: the unmutated copy must be green before anything is broken")
    for klass in classes:
        passed, output = run_class(workdir, klass, temp)
        if not passed:
            print(f"  BASELINE RED  {klass}")
            print("\n".join(output.splitlines()[-15:]))
            scratch.cleanup()
            return 1
        print(f"  baseline green  {klass}")

    survivors = []
    redundant = []
    try:
        for label, why, old, new, klass in MUTATIONS:
            if old not in original:
                print(f"SKIP      {label}: anchor not found - the mutation is stale")
                survivors.append((label, "anchor not found"))
                continue
            tool.write_text(original.replace(old, new, 1), encoding="utf-8", newline="")
            passed, output = run_class(workdir, klass, temp)
            tool.write_text(original, encoding="utf-8", newline="")
            if passed and label in EXPECTED_REDUNDANT:
                print(f"redundant {label}  ({klass} still green, as expected)")
                print(f"          covered by: {EXPECTED_REDUNDANT[label]}")
                redundant.append(label)
            elif passed:
                print(f"SURVIVED  {label}  ({klass} still green)")
                print(f"          reverts: {why}")
                survivors.append((label, klass))
            else:
                red = [ln for ln in output.splitlines() if ln.startswith(("FAIL:", "ERROR:"))]
                print(f"caught    {label}  -> {klass}: {len(red)} red")
                for line in red[:2]:
                    print(f"              {line}")
    finally:
        scratch.cleanup()

    print()
    if survivors:
        print(f"{len(survivors)} mutation(s) SURVIVED - pinned by no test:")
        for label, klass in survivors:
            print(f"  - {label} ({klass})")
        return 1
    stale_expectations = set(EXPECTED_REDUNDANT) - set(redundant)
    if stale_expectations:
        # An entry that no longer survives means the guard became reachable,
        # or the mutation went stale. Either way the note is now a lie.
        print(f"{len(stale_expectations)} EXPECTED_REDUNDANT entr(y/ies) no longer survive - "
              f"remove them: {sorted(stale_expectations)}")
        return 1
    pinned = len(MUTATIONS) - len(redundant)
    print(f"all {pinned} review fixes are pinned by a test"
          f" ({len(redundant)} redundant guard(s) covered by another, listed above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
