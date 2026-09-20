"""Before quarantining directories: which ones hold commits canonical cannot reach?

Moving a directory is only reversible for work that survives elsewhere. Two very different cases
hide behind "it's just a scratch folder":

  WORKTREE of canonical  - its .git is a FILE. Branches and objects live in canonical, so moving
                           the directory destroys no commits. BUT canonical keeps an administrative
                           entry in .git/worktrees/<name> pointing at the dead path, and git still
                           treats that worktree's checked-out branch as checked out - so the branch
                           cannot be checked out anywhere else until `git worktree prune` runs.
                           Move with `git worktree move`, or remove with `git worktree remove`.

  INDEPENDENT CLONE      - its .git is a directory with its own object store. A commit that
                           canonical has never seen exists ONLY here. Moving the directory is
                           reversible; losing or pruning it is not.

Output names every clone-only commit, so each can be fetched into canonical before anything moves.
Read-only: this script never writes, moves or deletes.
"""
import os
import subprocess
import sys

CANON = r"C:\NSC\NSC\NoSafeCircle"
ROOTS = sys.argv[1:] or [r"C:\nscrev", r"C:\NSC"]


def run(repo, *args):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return p.returncode, p.stdout


def canonical_knows(shas):
    """One batch call instead of one process per commit."""
    if not shas:
        return set()
    p = subprocess.run(["git", "-C", CANON, "cat-file", "--batch-check"],
                       input="\n".join(shas), capture_output=True, text=True)
    known = set()
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "commit":
            known.add(parts[0])
    return known


worktrees, clones, plain = [], [], []
for root in ROOTS:
    if not os.path.isdir(root):
        continue
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        dot = os.path.join(path, ".git")
        if os.path.isfile(dot):
            worktrees.append(path)
        elif os.path.isdir(dot):
            clones.append(path)
        else:
            plain.append(path)

print("scanned roots: %s" % ", ".join(ROOTS))
print("  worktrees of canonical : %d  (moving these destroys no commits - but prune afterwards)"
      % len(worktrees))
print("  independent clones     : %d  (these can hold the only copy of something)" % len(clones))
print("  plain directories      : %d" % len(plain))
print()

at_risk = {}
for path in clones:
    rc, raw = run(path, "for-each-ref", "--format=%(objectname) %(refname:short)", "refs/heads/")
    if rc != 0:
        print("  !! could not read refs: %s" % path)
        continue
    rows = [line.split(None, 1) for line in raw.splitlines() if line.strip()]
    if not rows:
        continue
    known = canonical_knows([sha for sha, _ in rows])
    missing = [(sha, ref) for sha, ref in rows if sha not in known]
    if missing:
        at_risk[path] = missing

if not at_risk:
    print("=== NOTHING AT RISK: every clone branch is already an object canonical holds. ===")
else:
    total = sum(len(v) for v in at_risk.values())
    print("=== %d branches in %d clones exist ONLY there. Fetch before moving. ==="
          % (total, len(at_risk)))
    for path in sorted(at_risk):
        print("\n  %s" % path)
        for sha, ref in at_risk[path]:
            print("      %s  %s" % (sha[:12], ref))
    print("\n  Rescue command shape (run in canonical, creates refs only, touches no branch):")
    print('      git -C "%s" fetch "<clone>" "<ref>:archive/<clone-name>-<ref>"' % CANON)
