"""Open a draft pull request for every recent local branch that still has work missing from main.

    python branch_prs.py prepare   # read-only: collect per-branch changes, write PR bodies and plan.json
    python branch_prs.py open      # push each planned branch to origin (no force) and open draft PRs

The PR body describes what the branch changes relative to main, so Vincent can review each one.
Nothing is merged, and auto-merge is never enabled.
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import subprocess
import sys
import time

REPO = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")
OUT = pathlib.Path(r"C:\nscrev\branch-prs-20260914")
GH_REPO = "cathode26/NoSafeCircle"
SINCE = "2026-09-12"
OWN_EMAIL = "Vincent.J.Liguori@outlook.com"
FOOTER = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"


def run(*args: str, check: bool = True) -> str:
    result = subprocess.run(list(args), cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed ({result.returncode}): {result.stderr.strip()[-600:]}")
    return result.stdout


def git(*args: str, check: bool = True) -> str:
    return run("git", *args, check=check)


def prepare() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    main_sha = git("rev-parse", "main").strip()
    remote_heads = {line.split("\t")[1][len("refs/heads/"):] for line in git("ls-remote", "--heads", "origin").splitlines() if "\t" in line}
    rows = git("for-each-ref", "refs/heads", "--no-merged=main", "--format=%(refname:short)|%(committerdate:iso-strict)|%(objectname)").splitlines()
    plan = []
    for row in rows:
        name, date, tip = row.split("|")
        if date[:10] < SINCE:
            continue
        cherry = git("cherry", "-v", "main", name).splitlines()
        unique = [(line[2:42], line[43:]) for line in cherry if line.startswith("+ ")]
        on_main = [line for line in cherry if line.startswith("- ")]
        if not unique:
            continue
        base = git("merge-base", "main", name).strip()
        shortstat = git("diff", "--shortstat", base, name).strip() or "no file changes"
        dirstat = [line.strip() for line in git("diff", "--dirstat=files,10", base, name).splitlines()][:5]
        name_status = git("diff", "--name-status", base, name).splitlines()
        emails = set(git("log", "--format=%ae%n%ce", f"main..{name}").split())
        unexpected = sorted(e for e in emails if not e.endswith(".invalid") and e != OWN_EMAIL)
        subjects = [subject for _, subject in unique]
        tasks = sorted(set(re.findall(r"NSC-?\d{3}", name.upper() + " " + " ".join(subjects))))
        tasks = sorted({t if "-" in t else f"NSC-{t[3:]}" for t in tasks})
        plan.append({
            "branch": name, "tip": tip, "tip_date": date, "tip_subject": git("log", "-1", "--format=%s", name).strip(),
            "merge_base": base, "unique": unique, "already_on_main": len(on_main), "shortstat": shortstat,
            "dirstat": dirstat, "files": name_status, "tasks": tasks, "unexpected_emails": unexpected,
            "exists_on_origin": name in remote_heads, "old": date[:10] < "2026-09-13",
            "diagnostic_or_revert": any(re.match(r"(Diagnose|Revert)\b", s) for s in subjects),
        })
    by_tip = collections.defaultdict(list)
    by_subjects = collections.defaultdict(list)
    for item in plan:
        by_tip[item["tip"]].append(item["branch"])
        by_subjects[tuple(sorted(s for _, s in item["unique"]))].append(item["branch"])
    for item in plan:
        same_tip = [b for b in by_tip[item["tip"]] if b != item["branch"]]
        same_subjects = [b for b in by_subjects[tuple(sorted(s for _, s in item["unique"]))] if b != item["branch"] and b not in same_tip]
        item["duplicates"] = {"same_tip_commit": same_tip, "same_commit_subjects": same_subjects}
        item["title"] = (f"{', '.join(item['tasks'][:3]) or 'Pipeline'}: {item['tip_subject']}")[:110]
        item["body_file"] = str(OUT / (re.sub(r"[^A-Za-z0-9._-]+", "_", item["branch"]) + ".md"))
        pathlib.Path(item["body_file"]).write_text(body(item, main_sha), encoding="utf-8")
    plan.sort(key=lambda item: item["tip_date"])
    (OUT / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    for item in plan:
        flags = []
        if item["duplicates"]["same_tip_commit"]:
            flags.append("duplicate tip")
        if item["duplicates"]["same_commit_subjects"]:
            flags.append("same commits rebased")
        if item["diagnostic_or_revert"]:
            flags.append("diagnose/revert")
        if item["old"]:
            flags.append("09-12 branch")
        if item["unexpected_emails"]:
            flags.append("UNEXPECTED EMAIL " + ",".join(item["unexpected_emails"]))
        if item["exists_on_origin"]:
            flags.append("already on origin")
        print(f"{item['branch']} | +{len(item['unique'])} | {item['shortstat']} | {'; '.join(flags)}")
    print(f"\n{len(plan)} branches planned; bodies and plan.json in {OUT}")
    return 0


def body(item: dict, main_sha: str) -> str:
    lines = [
        f"**Branch:** `{item['branch']}` (tip `{item['tip'][:9]}`, {item['tip_date'][:16].replace('T', ' ')})",
        f"**Opened as a draft for Vincent's review. Not merged.** Base is `main` (`{main_sha[:9]}`).",
        "",
        f"**Commits not on main ({len(item['unique'])}):**",
    ]
    lines += [f"- `{sha[:9]}` {subject}" for sha, subject in item["unique"]]
    if item["already_on_main"]:
        lines += ["", f"**Also contains {item['already_on_main']} commit(s) already on main** under other SHAs (cherry-picked), so the file list below can include changes main already has."]
    lines += ["", f"**Change against its merge base `{item['merge_base'][:9]}`:** {item['shortstat']}"]
    if item["dirstat"]:
        lines += ["", "**Main areas:** " + "; ".join(item["dirstat"])]
    shown = item["files"][:40]
    lines += ["", "**Files:**", "```", *shown, "```"]
    if len(item["files"]) > len(shown):
        lines.append(f"...and {len(item['files']) - len(shown)} more.")
    notes = []
    if item["duplicates"]["same_tip_commit"]:
        notes.append("Exact duplicate: the same tip commit is also on " + ", ".join(f"`{b}`" for b in item["duplicates"]["same_tip_commit"]) + ".")
    if item["duplicates"]["same_commit_subjects"]:
        notes.append("Likely the same work rebased: identical commit subjects on " + ", ".join(f"`{b}`" for b in item["duplicates"]["same_commit_subjects"]) + ".")
    if item["diagnostic_or_revert"]:
        notes.append("Contains diagnostic and/or revert commits.")
    if item["old"]:
        notes.append("Branch last changed on 2026-09-12; main may already hold a later version of this work.")
    if notes:
        lines += ["", "**Review notes:**", *[f"- {note}" for note in notes]]
    lines += ["", FOOTER]
    return "\n".join(lines) + "\n"


def open_prs() -> int:
    plan = json.loads((OUT / "plan.json").read_text(encoding="utf-8"))
    blocked = [item["branch"] for item in plan if item["unexpected_emails"]]
    todo = [item for item in plan if not item["unexpected_emails"]]
    refspecs = [f"refs/heads/{item['branch']}:refs/heads/{item['branch']}" for item in todo if not item["exists_on_origin"]]
    for chunk_start in range(0, len(refspecs), 20):
        chunk = refspecs[chunk_start:chunk_start + 20]
        push = subprocess.run(["git", "push", "origin", *chunk], cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(push.stderr.strip()[-1500:], flush=True)
        if push.returncode != 0:
            print(f"push chunk failed ({push.returncode}); stopping before creating PRs", flush=True)
            return 1
    results = []
    for item in todo:
        remote_tip = git("ls-remote", "--heads", "origin", item["branch"]).split("\t")[0].strip()
        if remote_tip != item["tip"]:
            results.append({"branch": item["branch"], "result": f"skipped: origin tip {remote_tip[:9] or 'missing'} != local {item['tip'][:9]}"})
            continue
        existing = run("gh", "pr", "list", "--repo", GH_REPO, "--head", item["branch"], "--state", "open", "--json", "url", "-q", ".[].url", check=False).strip()
        if existing:
            results.append({"branch": item["branch"], "result": "already open", "url": existing})
            continue
        created = subprocess.run(["gh", "pr", "create", "--repo", GH_REPO, "--draft", "--base", "main", "--head", item["branch"],
                                  "--title", item["title"], "--body-file", item["body_file"]],
                                 cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace")
        url = created.stdout.strip().splitlines()[-1] if created.returncode == 0 and created.stdout.strip() else ""
        results.append({"branch": item["branch"], "result": "opened" if url else f"failed: {created.stderr.strip()[-300:]}", "url": url,
                        "title": item["title"], "unique_commits": len(item["unique"]), "shortstat": item["shortstat"]})
        print(f"{results[-1]['result']:>8}  {item['branch']}  {url}", flush=True)
        time.sleep(2)
    (OUT / "opened.json").write_text(json.dumps({"blocked_unexpected_email": blocked, "results": results}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"opened": sum(1 for r in results if r["result"] == "opened"), "blocked": blocked,
                      "other": [r for r in results if r["result"] not in ("opened",)]}, indent=2))
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    raise SystemExit(prepare() if mode == "prepare" else open_prs() if mode == "open" else print(__doc__) or 2)
