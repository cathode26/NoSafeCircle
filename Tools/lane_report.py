#!/usr/bin/env python3
"""Report what a lane branch contributes, and whether it integrates.

WHY THIS EXISTS. Seven family lanes land tonight, each from its own worktree, each written by a
worker that could not compile or run Unity. The integrator does the same five checks on every one
of them, and doing those five by hand seven times is how one gets skipped on the sixth.

WHAT IT ANSWERS, in order, stopping at the first that fails:
    1. Does the branch exist and what is its tip?
    2. What does it CONTRIBUTE - files added, changed, deleted - against the merge base, not
       against main. Those are different questions and the second one calls newer base work a
       deletion.
    3. Does it merge cleanly? Asked with merge-tree, which answers without touching any checkout.
    4. On the MERGED tree, do both linters pass? Not on the branch alone - a lane can be internally
       consistent and still collide with another lane's guids or push a shared file over a limit.
    5. What does the integrator still have to do by hand? Compile and run Unity. This tool does
       neither and says so, because a report that implies it checked compilation is worse than one
       that admits it did not.

Exit 0 when the lane merges clean and both linters pass on the merged tree; 1 when anything fails;
2 when the branch or the repository is not what was named, which is deliberately distinguishable
from a lane that is simply bad.
"""

import argparse
import pathlib
import subprocess
import sys


def git(repo, *args, check=False):
    """Run git and return (exit code, stdout). Bytes decoded explicitly, never text mode.

    Python text mode on Windows decodes with cp1252 and silently mangles every non-ASCII byte,
    which has corrupted a contract read in this repository before.
    """
    finished = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    out = finished.stdout.decode("utf-8", errors="replace").strip()
    if check and finished.returncode != 0:
        err = finished.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError("git {0} failed: {1}".format(" ".join(args), err))
    return finished.returncode, out


def run_lint(repo, script, extra):
    finished = subprocess.run([sys.executable, "-B", script, *extra], cwd=repo, capture_output=True)
    return finished.returncode, finished.stdout.decode("utf-8", errors="replace").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch", help="The lane branch, e.g. lane/walls-from-ascii")
    parser.add_argument("--repo", default="C:/nscrev/doormeta")
    parser.add_argument("--into", default="", help="Branch to integrate into. Default: current HEAD.")
    arguments = parser.parse_args()

    repo = arguments.repo
    if not pathlib.Path(repo, ".git").exists():
        print("FAIL: '{0}' is not a git repository.".format(repo))
        return 2

    code, tip = git(repo, "rev-parse", "--verify", arguments.branch)
    if code != 0:
        print("FAIL: branch '{0}' does not exist in {1}. Nothing to report.".format(
            arguments.branch, repo))
        return 2

    target = arguments.into or git(repo, "rev-parse", "HEAD")[1]
    _, target_name = git(repo, "rev-parse", "--abbrev-ref", "HEAD") if not arguments.into \
        else (0, arguments.into)

    _, base = git(repo, "merge-base", target, tip)

    print("LANE      {0}".format(arguments.branch))
    print("tip       {0}".format(tip))
    print("into      {0}  ({1})".format(target, target_name))
    print("base      {0}".format(base))

    if base == tip:
        print("FAIL: the lane tip IS the merge base, so it contributes nothing. The worker either "
              "did not commit, or committed to a different branch.")
        return 1

    # WHAT IT CONTRIBUTES, from the merge base. Diffing against the target instead would report
    # every commit the target gained since the lane forked as a DELETION by the lane.
    _, names = git(repo, "diff", "--name-status", base, tip)
    added = [n for n in names.split("\n") if n.startswith("A")]
    modified = [n for n in names.split("\n") if n.startswith("M")]
    deleted = [n for n in names.split("\n") if n.startswith("D")]
    print("\nCONTRIBUTES  {0} added, {1} modified, {2} deleted".format(
        len(added), len(modified), len(deleted)))
    for entry in added + modified + deleted:
        print("   " + entry)

    if deleted:
        print("\nNOTE: this lane DELETES files. A lane is supposed to add its own; check each one.")

    # MERGE CLEANLY? Asked without touching any working tree.
    code, tree = git(repo, "merge-tree", "--write-tree", target, tip)
    if code != 0:
        print("\nFAIL: the lane does NOT merge cleanly into {0}.".format(target_name))
        print(tree)
        return 1
    merged_tree = tree.split("\n")[0]
    print("\nMERGES CLEAN, resulting tree {0}".format(merged_tree))

    # LINT THE MERGED RESULT, not the branch. A lane can be internally consistent and still collide
    # with a sibling lane's guids, which is exactly the failure two parallel workers can produce
    # and neither can see.
    # merge-tree hands back a TREE and `git worktree add` needs a COMMIT-ISH, so wrap the tree in
    # a dangling commit with both sides as parents. Nothing references it, so gc collects it; the
    # point is only to have something a worktree can check out.
    code, trial = git(repo, "commit-tree", merged_tree, "-p", target, "-p", tip,
                      "-m", "lane_report trial merge of " + arguments.branch)
    if code != 0:
        print("")
        print("FAIL: could not build a trial-merge commit: " + trial)
        return 1

    worktree = str(pathlib.Path(repo).parent / ("lane-verify-" + arguments.branch.replace("/", "-")))
    git(repo, "worktree", "remove", "--force", worktree)
    code, out = git(repo, "worktree", "add", "--detach", worktree, trial)
    if code != 0:
        print("")
        print("FAIL: could not materialize the merged tree for linting: " + out)
        return 1

    print("trial merge commit " + trial + " (dangling, not a ref)")

    try:
        failures = 0
        for script, extra in (("Tools/prefab_lint.py",
                               ["--assets", "Assets", "--subtree", "NoSafeCircle/DoorPrototype"]),
                              ("Tools/component_size_lint.py", [])):
            lint_code, lint_out = run_lint(worktree, script, extra)
            marker = "PASS" if lint_code == 0 else "FAIL"
            print("\n{0} {1} (exit {2})".format(marker, script, lint_code))
            for line in lint_out.split("\n")[-6:]:
                print("   " + line)
            if lint_code != 0:
                failures += 1
    finally:
        git(repo, "worktree", "remove", "--force", worktree)

    print("\nSTILL UNVERIFIED AND ONLY THE INTEGRATOR CAN DO IT:")
    print("   compilation   - nothing here compiles C#")
    print("   Unity         - no test has run; the lane's own fixture is unproven")
    print("   visual        - no capture has been taken")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
