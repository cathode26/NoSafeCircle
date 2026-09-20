"""Which remaining tasks are at or above NSC-007's difficulty profile?

Vincent's benchmark for "too hard for a crew to complete in one run" is NSC-007 **as dispatched at
revision 5** - 11 non-meta resources, 11 acceptance criteria, 5 distinct areas, and a shape that
deletes existing behaviour while building its replacement. Pin a benchmark to a revision, not to a
task id: NSC-007 is now at revision 8 with 13 non-meta resources after four failed decompositions.

FIXED 2026-09-18: this script used to skip every task whose derived state is `aggregate`, which
silently excluded **the tasks already flagged as too hard**. An implementation task reads `aggregate`
when its `execution_scope` is `needs_execution_decomposition` - marked for splitting, not itself
dispatchable. Those are exactly what this triage exists to surface, so they are now included and
labelled FLAGGED. NSC-007 was invisible to its own benchmark until this was fixed.
Found by the Decomposition Agent's handover pass.

Usage:  python -B C:/nscrev/job-tools/too_hard_benchmark.py
"""
import json
import subprocess
from pathlib import Path

REPO = Path(r"C:\NSC\NSC\NoSafeCircle")
NW = 0x08000000

out = subprocess.run(["python", "-B", "Pipeline/TaskGraph/taskcontrol.py", "states"],
                     cwd=REPO, capture_output=True, text=True, creationflags=NW).stdout
state = {}
for line in out.splitlines()[2:]:
    p = line.split()
    if len(p) >= 4 and p[0].startswith("NSC-"):
        state[p[0]] = p[1]

DONE = {"conformant", "delivered"}
SKIP = {"superseded"}          # NOT `aggregate` - see the docstring

rows = []
for f in sorted((REPO / "Tasks").glob("NSC-*.yaml")):
    d = json.loads(f.read_text(encoding="utf-8"))
    i = d["id"]
    if d.get("kind") != "implementation" or d.get("contract_disposition") != "active":
        continue
    if state.get(i) in DONE or state.get(i) in SKIP:
        continue
    res = [r for r in d.get("exclusive_resources", []) if not r.endswith(".meta")]
    areas = {"/".join(r.split(":", 1)[-1].split("/")[:4]) for r in res}
    rows.append({
        "id": i, "res": len(res), "ac": len(d.get("acceptance_criteria", [])),
        "areas": len(areas), "rev": d.get("contract_revision", 0),
        "state": state.get(i, "?"),
        "flagged": d.get("execution_scope") == "needs_execution_decomposition",
        "title": (d.get("title") or "")[:44],
    })

BENCH = {"res": 11, "ac": 11, "areas": 5}


def score(r):
    return sum(1 for k, v in BENCH.items() if r[k] >= v)


rows.sort(key=lambda r: (-score(r), -r["res"] - r["ac"]))

print(f"benchmark = NSC-007 at rev 5: {BENCH['res']} resources, {BENCH['ac']} criteria, {BENCH['areas']} areas")
print("FLAGGED = already marked needs_execution_decomposition, i.e. someone has judged it too hard.\n")
print(f"{'task':9} {'res':>4} {'AC':>4} {'area':>5} {'rev':>4}  {'axes':>5} {'flag':>8}  {'state':14} title")
print("-" * 106)
for r in rows:
    s = score(r)
    mark = "***" if s >= 2 else (" * " if s == 1 else "   ")
    print(f"{r['id']:9} {r['res']:>4} {r['ac']:>4} {r['areas']:>5} {r['rev']:>4}  {mark:>5} "
          f"{'FLAGGED' if r['flagged'] else '':>8}  {r['state']:14} {r['title']}")

hard = [r for r in rows if score(r) >= 2]
flagged = [r for r in rows if r["flagged"]]
print(f"\n{len(hard)} of {len(rows)} meet or exceed the benchmark on 2+ axes: {', '.join(r['id'] for r in hard)}")
print(f"{len(flagged)} already flagged for decomposition: {', '.join(r['id'] for r in flagged) or '(none)'}")
print("\nRead the contract before trusting the count: 100 independent PNGs is easy; 8 files that rewire")
print("a scene and a fixture together is not. Revision count is a fourth signal the axes cannot see.")
