import json
import subprocess
import sys
from pathlib import Path

REPO = r"C:\NSC\NSC\NoSafeCircle"
CHECKOUT_ROOT = Path(r"C:\NSC\NoSafeCircle-AssistantCheckouts")
NO_WINDOW = 0x08000000

def git(*args):
    r = subprocess.run(["git", "-C", REPO] + list(args), capture_output=True, text=True,
                        creationflags=NO_WINDOW, encoding="utf-8", errors="replace")
    return r

def get_head():
    return git("rev-parse", "HEAD").stdout.strip()

def list_task_ids():
    r = git("ls-tree", "-r", "--name-only", "HEAD", "--", "Tasks/")
    ids = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("Tasks/NSC-") and line.endswith(".yaml"):
            ids.append(line[len("Tasks/"):-len(".yaml")])
    return sorted(ids)

def load_contract(task_id):
    r = git("show", f"HEAD:Tasks/{task_id}.yaml")
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception as e:
        return {"__parse_error__": str(e)}

def file_exists_at_head(path):
    r = git("cat-file", "-e", f"HEAD:{path}")
    return r.returncode == 0

def load_states():
    r = subprocess.run(
        ["python", "-B", "Pipeline/TaskGraph/taskcontrol.py", "states"],
        cwd=REPO, capture_output=True, text=True, creationflags=NO_WINDOW,
        encoding="utf-8", errors="replace",
    )
    states = {}
    for line in r.stdout.splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 2 and parts[0].startswith("NSC-"):
            states[parts[0]] = parts[1]
    return states

def load_record(task_id):
    p = CHECKOUT_ROOT / ".assistant-control" / f"{task_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"__parse_error__": str(e)}

def load_validation_policy():
    p = Path(REPO) / "Pipeline" / "TaskReviewAgent" / "authoritative_validation_policy.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # try common shapes
        if isinstance(data, dict):
            for key in ("tasks", "entries", "policies"):
                if key in data and isinstance(data[key], dict):
                    return data[key]
            return data
        return {}
    except Exception:
        return {}

def main():
    head = get_head()
    states = load_states()
    task_ids = list_task_ids()
    contracts = {}
    for tid in task_ids:
        c = load_contract(tid)
        if c:
            contracts[tid] = c

    conformant_set = {tid for tid, st in states.items() if st == "conformant"}
    not_delivered_ids = [tid for tid, st in states.items() if st == "not_delivered"]

    # build reverse depends_on map across ALL tasks
    dependents_of = {}  # task_id -> list of task_ids that depend on it
    for tid, c in contracts.items():
        for dep in (c.get("depends_on") or []):
            dependents_of.setdefault(dep, []).append(tid)

    val_policy = load_validation_policy()

    results = []
    for tid in not_delivered_ids:
        c = contracts.get(tid)
        if not c:
            results.append({"id": tid, "error": "no contract found at HEAD"})
            continue
        excl = c.get("exclusive_resources") or []
        repo_files = []
        scene_files = []
        for e in excl:
            if e.startswith("repo-file:"):
                repo_files.append(e[len("repo-file:"):])
            elif e.startswith("unity-scene:"):
                scene_files.append(e[len("unity-scene:"):])
        checked = repo_files + scene_files
        existing = [p for p in checked if file_exists_at_head(p)]
        missing = [p for p in checked if p not in existing]

        if len(checked) == 0:
            bucket = "no_file_claims"
        elif len(missing) == 0:
            bucket = "evidence_debt"
        elif len(existing) == 0:
            bucket = "not_built"
        else:
            bucket = "partially_built"

        deps = c.get("depends_on") or []
        deps_conformant = [d for d in deps if d in conformant_set]
        deps_not_conformant = [d for d in deps if d not in conformant_set]

        dependents = dependents_of.get(tid, [])
        dependents_blocked = [d for d in dependents if states.get(d) not in ("conformant",)]

        record = load_record(tid)
        record_status = None
        record_approval = None
        if record:
            record_status = record.get("status") or record.get("state")
            record_approval = record.get("approval") or record.get("approved")

        has_val_policy = tid in val_policy if isinstance(val_policy, dict) else False

        results.append({
            "id": tid,
            "title": c.get("title"),
            "bucket": bucket,
            "checked_files": len(checked),
            "existing_files": len(existing),
            "missing_files": missing,
            "depends_on": deps,
            "deps_conformant": deps_conformant,
            "deps_not_conformant": deps_not_conformant,
            "dependents_total": len(dependents),
            "dependents_blocked": dependents_blocked,
            "record_exists": record is not None,
            "record_status": record_status,
            "record_approval": record_approval,
            "has_validation_policy_entry": has_val_policy,
        })

    out = {
        "head": head,
        "state_counts": {},
        "results": results,
    }
    from collections import Counter
    out["state_counts"] = dict(Counter(states.values()))

    out_path = Path(r"C:\nscrev\viewer-tools\audit_raw.json")
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("wrote:", out_path)
    print("HEAD:", head)
    print("state_counts:", out["state_counts"])
    print("not_delivered count:", len(not_delivered_ids))
    buckets = Counter(r["bucket"] for r in results if "bucket" in r)
    print("buckets:", dict(buckets))

if __name__ == "__main__":
    main()
