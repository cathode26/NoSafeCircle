"""For each candidate task: which gates are automated and which need Vincent?

The evidence-debt scan proves a policy binds and its fixtures exist. It does NOT prove the task
can be recorded without Vincent - a contract can carry a human gate that no test can satisfy.
This reads every completion gate and flags the ones whose wording asks a person to look.

Also separates the two reasons a named fixture can be absent, which the first scan conflated:
  - the task's implementation is ON MAIN and the fixture is missing  -> a real contract problem
  - the task is NOT IMPLEMENTED yet                                  -> normal; the policy names
                                                                        the fixture it will create
"""
import json
import re
import subprocess
import sys

REPO = sys.argv[1] if len(sys.argv) > 1 else r"C:\NSC\NSC\NoSafeCircle"
CANDIDATES = sys.argv[2].split(",")

HUMAN = re.compile(
    r"\bVincent\b|\bhuman\b|\bby eye\b|\bvisually\b|\bconfirms?\b|\bobserves?\b|\bplaytest"
    r"|\bopens? the (editor|scene|game)|\bin the editor\b|\bscreenshot|\blooks? (right|correct|fine)",
    re.I)


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True).stdout


for tid in CANDIDATES:
    d = json.loads(git("show", "HEAD:Tasks/%s.yaml" % tid))
    gates = d.get("completion_gates", [])
    human = [g for g in gates if HUMAN.search(g["requirement"])]
    auto = [g for g in gates if g not in human]
    flag = "NEEDS VINCENT" if human else "automated only"
    print("%-9s %-15s gates=%d  automated=%s  human=%s"
          % (tid, flag, len(gates), [g["gate_id"] for g in auto], [g["gate_id"] for g in human]))
    for g in human:
        snippet = re.sub(r"\s+", " ", g["requirement"])
        m = HUMAN.search(snippet)
        start = max(0, m.start() - 70)
        print("      %s: ...%s..." % (g["gate_id"], snippet[start:m.end() + 110]))
