"""Which not_delivered tasks are paperwork, and which are real work?

Cheap pass, in this order so the expensive step runs on few tasks:
  1. derived_state == not_delivered
  2. a committed policy entry exists AND its task_contract_sha256 binds at HEAD
  3. every type its filters name exists by DECLARATION, with its [Test]/[UnityTest] count

A task that clears all three is an evidence pass: run the filter, record, commit. A task that
fails (2) or (3) is a contract question for the GER Agent, not paperwork - and must not be
queued as if it were cheap.
"""
import hashlib
import json
import re
import subprocess
import sys

REPO = sys.argv[1] if len(sys.argv) > 1 else r"C:\NSC\NSC\NoSafeCircle"


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True).stdout


def git_bytes(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True).stdout


states = {}
for line in subprocess.run([sys.executable, "-B", REPO + r"\Pipeline\TaskGraph\taskcontrol.py",
                            "states"], capture_output=True, text=True, cwd=REPO).stdout.splitlines():
    parts = line.split()
    if len(parts) >= 2 and parts[0].startswith("NSC-"):
        states[parts[0]] = parts[1]

not_delivered = sorted(t for t, s in states.items() if s == "not_delivered")
print("not_delivered: %d" % len(not_delivered))

policy = json.loads(git("show", "HEAD:Pipeline/TaskReviewAgent/authoritative_validation_policy.json"))
ptasks = policy.get("tasks", {})

no_entry, stale, bound = [], [], []
for tid in not_delivered:
    entry = ptasks.get(tid)
    if not entry:
        no_entry.append(tid)
        continue
    actual = hashlib.sha256(git_bytes("show", "HEAD:Tasks/%s.yaml" % tid)).hexdigest()
    (bound if actual == entry.get("task_contract_sha256") else stale).append(tid)

print("  no policy entry : %d  %s" % (len(no_entry), " ".join(no_entry)))
print("  policy STALE    : %d  %s" % (len(stale), " ".join(stale)))
print("  policy binds    : %d  %s" % (len(bound), " ".join(bound)))

# Only now read source, and only for the bound ones.
cs_files = [f for f in git("ls-tree", "-r", "--name-only", "HEAD").splitlines() if f.endswith(".cs")]
sources = {f: git("show", "HEAD:" + f) for f in cs_files}

print("\n=== tasks whose policy binds: do the named fixtures exist? ===")
ready, broken = [], []
for tid in bound:
    entry = ptasks[tid]
    rows, missing = [], []
    for platform, joined in (entry.get("test_filters") or {}).items():
        for flt in joined.split(";"):
            flt = flt.strip()
            if not flt:
                continue
            typename = flt.rsplit(".", 1)[-1]
            hits = [f for f, src in sources.items()
                    if re.search(r"\bclass\s+%s\b" % re.escape(typename), src)]
            if not hits:
                missing.append(flt)
                continue
            n = sum(len(re.findall(r"^\s*\[Test\]", sources[f], re.M))
                    + len(re.findall(r"^\s*\[UnityTest\]", sources[f], re.M)) for f in hits)
            partial = any(re.search(r"\bpartial\s+class\s+%s\b" % re.escape(typename), sources[f])
                          for f in hits)
            rows.append((platform, typename, n, len(hits), partial))
    gates = len(json.loads(git("show", "HEAD:Tasks/%s.yaml" % tid)).get("completion_gates", []))
    tag = "READY " if not missing else "BROKEN"
    (ready if not missing else broken).append(tid)
    total = sum(r[2] for r in rows)
    print("%s %s  gates=%d  tests=%d" % (tag, tid, gates, total))
    for platform, typename, n, files, partial in rows:
        print("        %-9s %-52s %3d test(s)%s%s"
              % (platform, typename, n,
                 "  in %d files" % files if files > 1 else "",
                 "  PARTIAL" % () if partial else ""))
    for flt in missing:
        print("        MISSING DECLARATION: %s" % flt)

print("\nREADY  (evidence pass, no Vincent): %d  %s" % (len(ready), " ".join(ready)))
print("BROKEN (contract question for GER): %d  %s" % (len(broken), " ".join(broken)))
