"""Merge every recent local branch that still has work missing from main, in an isolated clone.

Nothing here touches the canonical checkout: it clones local main into WORK, merges each qualifying
branch there with --no-ff (oldest tip first), aborts and records any conflicting merge, undoes any
merge that would re-add files main has deleted, runs taskcontrol validate, and writes a JSON report.
The canonical main is fast-forwarded to the result as a separate, explicit step.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import sys

CANON = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")
WORK = pathlib.Path(r"C:\nscrev\merge-all-20260914")
SINCE = "2026-09-12"
IDENTITY = ["-c", "user.name=No Safe Circle Branch Integration",
            "-c", "user.email=branch-integration@nosafecircle.invalid"]
TRAILER = "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"


def git(*args: str, cwd: pathlib.Path = WORK, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()[-800:]}")
    return result


def candidate_branches() -> list[dict]:
    rows = git("for-each-ref", "refs/heads", "--no-merged=main",
               "--format=%(refname:short)|%(committerdate:iso-strict)", cwd=CANON).stdout.splitlines()
    branches = []
    for row in rows:
        name, date = row.split("|", 1)
        if date[:10] < SINCE:
            continue
        cherry = git("cherry", "main", name, cwd=CANON).stdout.splitlines()
        missing = [line[2:] for line in cherry if line.startswith("+ ")]
        if missing:
            branches.append({"branch": name, "tip_date": date, "commits_not_on_main": len(missing)})
    return sorted(branches, key=lambda item: item["tip_date"])


def main() -> int:
    if WORK.exists():
        raise SystemExit(f"work directory already exists: {WORK}")
    canon_main = git("rev-parse", "refs/heads/main", cwd=CANON).stdout.strip()
    branches = candidate_branches()
    print(f"canonical main {canon_main[:9]}; {len(branches)} branches with work not on main", flush=True)

    subprocess.run(["git", "-c", "core.longpaths=true", "clone", "--no-local", "--branch", "main", str(CANON), str(WORK)],
                   check=True, capture_output=True)
    git("config", "core.longpaths", "true")
    if git("rev-parse", "HEAD").stdout.strip() != canon_main:
        raise SystemExit("clone HEAD differs from canonical main")
    deleted_on_main = set(git("log", "--diff-filter=D", "--name-only", "--format=", "--since=2026-08-01", "main").stdout.split())

    results = []
    for item in branches:
        name = item["branch"]
        before = git("rev-parse", "HEAD").stdout.strip()
        merge = git(*IDENTITY, "merge", "--no-ff", "-m", f"Merge branch '{name}' into main", "-m", TRAILER,
                    f"origin/{name}", check=False)
        if merge.returncode != 0:
            conflicts = git("diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
            git("merge", "--abort", check=False)
            if git("rev-parse", "HEAD").stdout.strip() != before or git("status", "--porcelain=v1", "--untracked-files=no").stdout.strip():
                raise SystemExit(f"could not restore a clean state after aborting {name}")
            results.append({**item, "result": "conflict_skipped", "conflicts": conflicts[:20],
                            "detail": (merge.stdout + merge.stderr).strip()[-300:]})
            print(f"CONFLICT  {name}: {len(conflicts)} files", flush=True)
            continue
        added = git("diff", "--name-only", "--diff-filter=A", "HEAD^1", "HEAD").stdout.split()
        resurrected = sorted(path for path in added if path in deleted_on_main)
        if resurrected:
            git("reset", "--hard", before)
            results.append({**item, "result": "skipped_resurrects_deleted_files", "files": resurrected[:20]})
            print(f"SKIPPED   {name}: would re-add {len(resurrected)} files deleted on main", flush=True)
            continue
        changed = git("diff", "--name-only", "HEAD^1", "HEAD").stdout.split()
        results.append({**item, "result": "merged", "merge_commit": git("rev-parse", "HEAD").stdout.strip(),
                        "files_changed": len(changed)})
        print(f"MERGED    {name}: {len(changed)} files", flush=True)

    validate = subprocess.run([sys.executable, "-B", "Pipeline/TaskGraph/taskcontrol.py", "validate"], cwd=str(WORK),
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
    final_head = git("rev-parse", "HEAD").stdout.strip()
    stat = git("diff", "--shortstat", canon_main, final_head).stdout.strip()
    report = {
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "canonical_main_before": canon_main, "result_head": final_head, "work": str(WORK),
        "merged": sum(1 for r in results if r["result"] == "merged"),
        "conflict_skipped": sum(1 for r in results if r["result"] == "conflict_skipped"),
        "skipped_resurrects_deleted_files": sum(1 for r in results if r["result"] == "skipped_resurrects_deleted_files"),
        "diff_vs_main_before": stat,
        "taskcontrol_validate_exit": validate.returncode,
        "taskcontrol_validate_tail": (validate.stdout + validate.stderr).strip()[-600:],
        "branches": results,
    }
    (WORK.parent / "merge-all-20260914-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in report if key != "branches"}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
