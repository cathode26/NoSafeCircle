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

THAT EXEMPTION HAS TO FOLLOW THREE EDGES, NOT ONE, AND IT ONLY FOLLOWED TWO UNTIL 2026-09-26. A task may
declare the fixture itself; a DEPENDENCY may author it (NSC-096 binds NSC-095's audit fixture); or the
task may be a DECOMPOSED PARENT whose CHILDREN author everything while the parent declares nothing. The
third edge runs the wrong way - children name their `parent`, so no depends_on walk reaches them - and
without it every aggregate parent false-FAILs on its own decomposition. NSC-007 is the case: it declares
no resources at all, and its three "TYPE NOT FOUND" clauses are declared by NSC-118
(FireballCastAndChargePlayModeTests, FireballLifecyclePlayModeTests) and NSC-119
(FireballCommittedSceneConformanceTests). Those filters were CORRECT the whole time - they name exactly
what the decomposition will produce. The tool reported them as defects for as long as it has existed.

What it checks, per semicolon-separated name in the filter:
  - the type is DECLARED in committed file CONTENT (never a filename match - fixtures are often partial
    classes living in differently named files);
  - its namespace-qualified name matches the filter exactly;
  - it contains at least one [Test]/[UnityTest]/[TestCase] - a real type with an empty body passes
    vacuously at the graph level and is the same failure wearing a better disguise;
  - the platform implied by its location (Tests/Editor -> EditMode, else PlayMode) matches the platform
    the filter is bound under;
  - the clause RESOLVES under graph_controller._resolve_test_paths, which is a two-stage lookup, not a
    stem-only one. THIS CHECK USED TO DEMAND EXACTLY ONE MATCHING FILE STEM AND THAT WAS WRONG: it
    produced a false FAIL on every PARTIAL fixture, which is a whole class of real ones. The resolver
    tries the file stem FIRST (graph_controller.py:425) and, only when no stem matches, falls back to a
    type index (:430) that sets spans_files = all_partial (:439). The rejection at :444 is
    `not matches or (len(matches) > 1 and not spans_files)` - so several files are FINE when they are all
    partial, because Unity runs a filter naming a partial type against every file contributing to it.
    Measured 2026-09-26 at main 5def87bc: NSC-069 and NSC-100 were reported FAIL here for years and both
    resolve correctly in the live automatic_scope_plan (2 and 5 test paths, including BOTH halves of the
    partial class RoomSceneCompositionFoundationTests). The 2026-09-18 GER handoff's advice that NSC-069
    'needs a scope override' came from this false FAIL and is withdrawn.
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
        before = len(problems)
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
        # Mirror graph_controller._resolve_test_paths exactly: stem branch first (:425), then the type
        # index (:430) whose spans_files = all_partial (:439); rejection at :444 is
        # `not matches or (len(matches) > 1 and not spans_files)`. A partial fixture spanning several
        # files RESOLVES - demanding one stem here is stricter than the code and false-FAILs it.
        n_stems = len(stems.get(short, []))
        if n_stems > 1:
            problems.append(
                f"{platform}: STEM AMBIGUITY - {short} matches {n_stems} committed test file stems. The"
                " resolver takes the stem branch first, where spans_files is False, so >1 is rejected"
                " at graph_controller.py:444.")
        elif n_stems == 0 and len(hits) > 1 and not all(h[2] for h in hits):
            problems.append(
                f"{platform}: TYPE AMBIGUITY - no file stem matches {short}, so the type index at"
                f" graph_controller.py:430 decides, and {len(hits)} committed files declare that name"
                " without all being `partial`. Those are distinct types sharing a name and are rejected"
                " at :444. (All-partial would resolve to every contributing file, which is correct.)")
        if len(problems) == before:
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
        # A DECOMPOSED PARENT DECLARES NOTHING AND ITS CHILDREN AUTHOR EVERYTHING, and the
        # children point UP via `parent`, so no depends_on edge leads to them. Without this
        # index an aggregate parent false-FAILs on every fixture its own decomposition will
        # write. NSC-007 did: all three of its "TYPE NOT FOUND" clauses are declared by
        # NSC-118 and NSC-119. Built once; the walk is transitive so a child that is itself
        # decomposed still reaches its grandchildren.
        kids: dict[str, list[str]] = {}
        contracts: dict[str, dict] = {}
        for line in git("ls-tree", "-r", "--name-only", args.commit, "--", "Tasks").decode(
                "utf-8", "replace").split("\n"):
            if not line.endswith(".yaml"):
                continue
            tid = line.rsplit("/", 1)[-1][:-5]
            try:
                contracts[tid] = json.loads(git("show", f"{args.commit}:{line}"))
            except Exception:
                continue
            parent = contracts[tid].get("parent")
            if parent:
                kids.setdefault(parent, []).append(tid)

        def declared_cs(tid: str) -> set:
            contract = contracts.get(tid) or {}
            return {r.partition(":")[2] for r in (contract.get("exclusive_resources") or [])
                    if r.startswith("repo-file:") and r.endswith(".cs")}

        def descendants(tid: str, seen: set | None = None) -> set:
            seen = seen if seen is not None else set()
            out: set = set()
            for kid in kids.get(tid, []):
                if kid in seen:
                    continue
                seen.add(kid)
                out |= declared_cs(kid) | descendants(kid, seen)
            return out
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
                    # ...and everything this task DECOMPOSES INTO. See the kids index above.
                    claimed |= descendants(task_id)
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
