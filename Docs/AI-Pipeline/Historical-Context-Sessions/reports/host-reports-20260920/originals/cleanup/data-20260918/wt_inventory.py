"""Read-only worktree inventory for the Cleanup Agent. Never writes into any repo, never moves or deletes.

Output: JSON of every registered worktree (from canonical `git worktree list --porcelain`) plus every child of
C:\\NSC\\_worktrees, with: exists, .git kind, branch/detached, HEAD, merged-into-main, task-named, and status split
into Unity noise vs real edits.
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

CANON = r"C:\NSC\NSC\NoSafeCircle"
WT_ROOT = r"C:\NSC\_worktrees"
OUT = sys.argv[1]
NOWIN = 0x08000000  # CREATE_NO_WINDOW


def git(repo, *args, timeout=300):
    try:
        p = subprocess.run(["git", "--no-optional-locks", "-C", repo, *args], capture_output=True, text=True,
                           timeout=timeout, creationflags=NOWIN, encoding="utf-8", errors="replace")
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # noqa
        return 99, "", repr(e)


rc, out, err = git(CANON, "worktree", "list", "--porcelain")
if rc != 0:
    raise SystemExit("worktree list failed: " + err)

entries, cur = [], None
for line in out.splitlines():
    if line.startswith("worktree "):
        cur = {"path": line[9:].replace("/", "\\"), "branch": None, "detached": False, "locked": False,
               "prunable": False, "bare": False, "head": None}
        entries.append(cur)
    elif cur is None:
        continue
    elif line.startswith("HEAD "):
        cur["head"] = line[5:]
    elif line.startswith("branch "):
        cur["branch"] = line[7:].replace("refs/heads/", "")
    elif line == "detached":
        cur["detached"] = True
    elif line.startswith("locked"):
        cur["locked"] = True
    elif line.startswith("prunable"):
        cur["prunable"] = True
    elif line == "bare":
        cur["bare"] = True

NOISE = re.compile(r"^(Library|Temp|Logs|obj|Build|UserSettings|Builds)/", re.I)
TASK = re.compile(r"NSC[-_]?\d{2,4}", re.I)


def classify(e):
    p = e["path"]
    e["exists"] = os.path.isdir(p)
    dot = os.path.join(p, ".git")
    e["git_kind"] = "file" if os.path.isfile(dot) else ("dir" if os.path.isdir(dot) else "none")
    e["under_wt_root"] = p.lower().startswith(WT_ROOT.lower() + "\\")
    e["is_canonical"] = os.path.normcase(p) == os.path.normcase(CANON)
    e["task_named"] = bool(TASK.search(os.path.basename(p))) or bool(e["branch"] and TASK.search(e["branch"]))
    if e["head"]:
        rc, _, _ = git(CANON, "merge-base", "--is-ancestor", e["head"], "main")
        e["head_in_main"] = (rc == 0)
    else:
        e["head_in_main"] = None
    e["branch_merged"] = None
    if e["branch"]:
        rc, _, _ = git(CANON, "merge-base", "--is-ancestor", "refs/heads/" + e["branch"], "main")
        e["branch_merged"] = (rc == 0)
    e["real_lines"], e["noise_lines"], e["status_err"] = None, None, None
    if e["exists"] and e["git_kind"] != "none":
        rc, so, se = git(p, "status", "--porcelain")
        if rc == 0:
            real, noise = [], 0
            for ln in so.splitlines():
                path = ln[3:].strip().strip('"')
                if NOISE.match(path):
                    noise += 1
                else:
                    real.append(ln)
            e["real_lines"] = real[:40]
            e["real_count"] = len(real)
            e["noise_lines"] = noise
        else:
            e["status_err"] = se.strip()[:200]
    return e


with ThreadPoolExecutor(8) as ex:
    entries = list(ex.map(classify, entries))

registered = {os.path.normcase(e["path"]) for e in entries}
wt_children = []
if os.path.isdir(WT_ROOT):
    for name in sorted(os.listdir(WT_ROOT)):
        path = os.path.join(WT_ROOT, name)
        dot = os.path.join(path, ".git")
        wt_children.append({
            "path": path, "is_dir": os.path.isdir(path),
            "git_kind": "file" if os.path.isfile(dot) else ("dir" if os.path.isdir(dot) else "none"),
            "registered": os.path.normcase(path) in registered,
            "mtime": os.path.getmtime(path) if os.path.exists(path) else None,
        })

with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"registered": entries, "wt_root_children": wt_children}, f, indent=1)

print("registered", len(entries), "children of _worktrees", len(wt_children))
