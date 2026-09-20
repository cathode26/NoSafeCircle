"""GER Agent: prove every type named in a validation-policy filter actually exists, before binding it.

    python -B verify_filter.py --filter "NoSafeCircle.DoorPrototype.Tests.FireballPlayModeTests"
    python -B verify_filter.py --task NSC-092                 # check what is already bound
    python -B verify_filter.py --all                          # audit every committed policy entry

Why this exists. A policy filter naming a type that does not exist selects zero tests. The pipeline catches
it loudly - run_unity_tests_clean.ps1 fails on `$total -le 0`, record_delivery.py raises on `total == 0` -
so it parks a candidate rather than passing a bad one, but it still costs a full crew run and a revision
round. NSC-007 bound `...Tests.FireballPlayModeTests` while the crew had written five fixtures over an
abstract base; that cost a run. NSC-069 revisions 7-9 cost three more.

IMPORTANT limitation, learned by testing this tool against NSC-007: a task that AUTHORS its own fixtures
has no such type at HEAD before it runs, so a bare "type not found" is expected rather than a defect. The
check reads the task's exclusive_resources and reports those as informational (`--`) instead of failures.
A missing type the task does NOT claim is a real defect.

What it checks, per semicolon-separated name in the filter:
  - the type is DECLARED in committed file CONTENT (never a filename match - fixtures are often partial
    classes living in differently named files);
  - its namespace-qualified name matches the filter exactly;
  - it contains at least one [Test]/[UnityTest]/[TestCase] - a real type with an empty body passes
    vacuously at the graph level and is the same failure wearing a better disguise;
  - the platform implied by its location (Tests/Editor -> EditMode, else PlayMode) matches the platform
    the filter is bound under;
  - graph_controller._resolve_test_paths resolves filters by FILE STEM, so the last name segment must also
    match exactly one committed test file stem, or scoping fails even when the type exists.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

REPO = r"C:\NSC\NSC\NoSafeCircle"
NO_WINDOW = 0x08000000
POLICY = "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
DECL = re.compile(
    r"^\s*(?:public|internal)\s+(?:sealed\s+|static\s+|abstract\s+|partial\s+)*class\s+(\w+)", re.M)
NS = re.compile(r"^\s*namespace\s+([\w.]+)", re.M)
TESTS = re.compile(r"^\s*\[(?:Test|UnityTest|TestCase)", re.M)


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True,
                          creationflags=NO_WINDOW, check=True).stdout


def index(commit: str) -> dict:
    """class name -> list of (path, namespace, is_partial, test_count)."""
    paths = [p for p in git("ls-tree", "-r", "--name-only", commit, "--", "Assets")
             .decode("utf-8", "replace").split("\n") if p.endswith(".cs") and "/Tests/" in p]
    found: dict = {}
    for path in paths:
        src = git("show", f"{commit}:{path}").decode("utf-8", "replace")
        ns = NS.search(src)
        count = len(TESTS.findall(src))
        for match in re.finditer(
                r"^\s*(?:public|internal)\s+((?:sealed\s+|static\s+|abstract\s+|partial\s+)*)class\s+(\w+)",
                src, re.M):
            found.setdefault(match.group(2), []).append(
                (path, ns.group(1) if ns else "?", "partial" in match.group(1), count))
    return found


def check(filter_text: str, platform: str, table: dict, stems: dict, authored: set | None = None) -> list:
    problems = []
    names = [n.strip() for n in filter_text.split(";") if n.strip()]
    if not names:
        return [f"{platform}: filter is empty"]
    for full in names:
        short = full.rsplit(".", 1)[-1]
        hits = table.get(short) or []
        if not hits:
            if authored and any(a.rsplit("/", 1)[-1][:-3] == short for a in authored):
                print(f"    --  {full}  (not at HEAD yet; this task AUTHORS a file named {short}.cs - "
                      "expected before it runs - this task or a dependency authors it - re-check after integration)")
            else:
                problems.append(
                    f"{platform}: TYPE NOT FOUND - {full} (no committed file DECLARES class {short}, "
                    "and this task does not claim a file of that name)")
            continue
        qualified = [h for h in hits if f"{h[1]}.{short}" == full]
        if not qualified:
            actual = ", ".join(sorted({f"{h[1]}.{short}" for h in hits}))
            problems.append(f"{platform}: NAMESPACE MISMATCH - filter says {full}, committed is {actual}")
            continue
        total = sum(h[3] for h in qualified)
        if total == 0:
            problems.append(f"{platform}: ZERO TESTS - {full} exists but declares no [Test]/[UnityTest]")
        for path, _, _, _ in qualified:
            implied = "EditMode" if "/Tests/Editor/" in path else "PlayMode"
            if implied != platform:
                problems.append(f"{platform}: PLATFORM MISMATCH - {full} lives at {path} ({implied})")
        if len(stems.get(short, [])) != 1:
            n = len(stems.get(short, []))
            problems.append(
                f"{platform}: STEM RESOLUTION - {short} matches {n} committed test file stems, needs exactly 1 "
                "(graph_controller resolves scope by file stem)")
        if not problems or problems[-1].startswith(platform) is False:
            pass
        if all(not p.startswith(f"{platform}: ") or full not in p for p in problems):
            print(f"    OK  {full}  ({total} tests, {qualified[0][0]})")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--filter", help="a filter string to check (use with --platform)")
    ap.add_argument("--platform", default="PlayMode", choices=["EditMode", "PlayMode"])
    ap.add_argument("--task", help="check the filters already bound for this task id")
    ap.add_argument("--all", action="store_true", help="audit every committed policy entry")
    args = ap.parse_args()

    table = index(args.commit)
    stems: dict = {}
    for path in [p for p in git("ls-tree", "-r", "--name-only", args.commit, "--", "Assets")
                 .decode("utf-8", "replace").split("\n") if p.endswith(".cs") and "/Tests/" in p]:
        stems.setdefault(path.rsplit("/", 1)[-1][:-3], []).append(path)

    jobs = []
    if args.filter:
        jobs.append(("(given)", {args.platform: args.filter}, set()))
    if args.task or args.all:
        tasks = json.loads(git("show", f"{args.commit}:{POLICY}"))["tasks"]
        for task_id, entry in sorted(tasks.items()):
            if args.all or task_id == args.task:
                try:
                    contract = json.loads(git("show", f"{args.commit}:Tasks/{task_id}.yaml"))
                    claimed = {r.partition(":")[2] for r in (contract.get("exclusive_resources") or [])
                               if r.startswith("repo-file:") and r.endswith(".cs")}
                    # A task may legitimately bind a fixture that one of its DEPENDENCIES authors:
                    # the file will exist by the time this task runs. NSC-096 binds NSC-095's audit
                    # fixture and depends on it, which is correct rather than a defect.
                    for dep in (contract.get("depends_on") or []):
                        try:
                            dep_contract = json.loads(git("show", f"{args.commit}:Tasks/{dep}.yaml"))
                        except Exception:
                            continue
                        claimed |= {r.partition(":")[2] for r in (dep_contract.get("exclusive_resources") or [])
                                    if r.startswith("repo-file:") and r.endswith(".cs")}
                except Exception:
                    claimed = set()
                jobs.append((task_id, entry.get("test_filters") or {}, claimed))
        if args.task and not jobs:
            print(f"{args.task}: no policy entry")
            return 1

    bad = 0
    for label, filters, authored in jobs:
        print(f"\n=== {label}")
        problems = []
        for platform, text in filters.items():
            if platform not in ("EditMode", "PlayMode"):
                print(f"    skip non-Unity platform {platform}")
                continue
            problems += check(text, platform, table, stems, authored)
        for p in problems:
            print(f"    !!  {p}")
        bad += len(problems)
    print(f"\n{'FAIL' if bad else 'PASS'}: {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
