"""Validate revised task contracts in memory against current main (no repository writes).

    python -B validate_in_memory.py <revised.json> [<revised.json> ...]

Substitutes each revised contract for its task, reconciles RESOURCE_GROUPS exactly as
apply_contract.py does, and runs the TaskGraph validator on the result.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys

REPO = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")
sys.path.insert(0, str(REPO / "Pipeline" / "TaskGraph"))
sys.path.insert(0, r"C:\nscrev\ger-tools")

import apply_contract as ac  # noqa: E402
from persistent_work_graph import load_persistent_work_graph  # noqa: E402
from work_graph_validate import validate_work_graph_plan  # noqa: E402


def main() -> int:
    revised = {}
    for arg in sys.argv[1:]:
        task = json.loads(pathlib.Path(arg).read_bytes())
        revised[task["id"]] = task
    graph = load_persistent_work_graph(REPO)
    plan = graph.plan
    tasks = [revised.get(task["id"], task) for task in plan.tasks]
    groups = copy.deepcopy(list(plan.resource_groups))
    changes = ac.reconcile_resource_groups(groups, tasks)
    for change in changes:
        after = change["after"]
        entry = {"reconciliation_keys": after["reconciliation_keys"], "resource_key": after["resource_key"],
                 "work_ids": after["work_ids"]}
        if change["change_type"] == "updated":
            index = next(i for i, group in enumerate(groups) if group["resource_key"] == after["resource_key"])
            groups[index] = entry
        else:
            groups.append(entry)
        print(f"[GROUPS] {change['change_type']}: {after['resource_key']} -> {after['work_ids']}")
    new_plan = type(plan)(plan.id_map, tuple(tasks), tuple(groups), plan.project_requirements)
    summary = validate_work_graph_plan(new_plan)
    print("[VALIDATE] PASS", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
