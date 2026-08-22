from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from typing import Any

from execution_authority import (
    UnsafeExecutionAuthorizationError,
    assess_execution_authorization,
)
from persistent_work_graph import PersistentWorkGraphError, load_persistent_work_graph
from task_contract_schema import TASK_CONTRACT_SCHEMA_VERSION
from work_graph_validate import WorkGraphValidationError
from current_conformance import evaluate_current_conformance


def _numeric_id(task: dict[str, Any]) -> int:
    return int(str(task["id"]).split("-", 1)[1])


def _sorted_tasks(tasks):
    return sorted(tasks, key=_numeric_id)


def _resolve_task(graph, selector: str) -> dict[str, Any]:
    raw = selector.strip()
    if not raw:
        raise ValueError("Task selector may not be blank.")
    upper = raw.upper()
    if upper in graph.tasks_by_id:
        return graph.tasks_by_id[upper]
    if raw in graph.tasks_by_key:
        return graph.tasks_by_key[raw]
    raise ValueError(f"Unknown task: {selector!r}. Use an NSC-* ID or reconciliation_key.")


def _is_v2(graph) -> bool:
    return graph.validation.task_schema_version == TASK_CONTRACT_SCHEMA_VERSION


def command_validate(graph) -> int:
    summary = graph.validation
    print("taskcontrol validate: PASS")
    print(f"Task contract schema:           {summary.task_schema_version}")
    print(f"Tasks:                          {summary.task_count}")
    if _is_v2(graph):
        counts = {name: 0 for name in ("active", "superseded", "cancelled")}
        for task in graph.plan.tasks:
            counts[task["contract_disposition"]] += 1
        print(f"Active contracts:               {counts['active']}")
        print(f"Superseded contracts:           {counts['superseded']}")
        print(f"Cancelled contracts:            {counts['cancelled']}")
    else:
        complete = sum(1 for task in graph.plan.tasks if task["status"] == "complete")
        print(f"Legacy YAML open:               {len(graph.plan.tasks) - complete}")
        print(f"Legacy YAML complete:           {complete}")
        print("Migration state:                schema v2 not yet applied")
    print(f"Root:                           {summary.root_id} ({summary.root_key})")
    print(f"Parent edges:                   {summary.parent_edge_count}")
    print(f"Dependency edges:               {summary.dependency_edge_count}")
    print(f"Resource groups:                {summary.resource_group_count}")
    print(f"Project requirements:           {summary.project_requirement_count}")
    print("Parent hierarchy:               connected + acyclic")
    print("Dependency graph:               acyclic")
    print("Autonomous dispatch authority:  DISABLED")
    return 0


def _format_task_row_v1(task):
    return (
        f"{task['id']:<8} {task['status']:<13} {task['kind']:<14} "
        f"{task['execution_scope']:<29} {task['title']}"
    )


def _format_task_row_v2(task):
    return (
        f"{task['id']:<8} {task['contract_disposition']:<13} {task['kind']:<14} "
        f"{task['execution_scope']:<29} r{task['contract_revision']:<3} {task['title']}"
    )


def command_list(graph, status: str | None, disposition: str | None, kind: str | None) -> int:
    tasks = _sorted_tasks(graph.plan.tasks)
    if kind:
        tasks = [task for task in tasks if task["kind"] == kind]
    if _is_v2(graph):
        if status:
            raise ValueError("--status is only valid before the schema-v2 migration.")
        if disposition:
            tasks = [task for task in tasks if task["contract_disposition"] == disposition]
        print("ID       DISPOSITION   KIND           EXECUTION_SCOPE               REV  TITLE")
        print("-------- ------------- -------------- ----------------------------- ---- -----")
        for task in tasks:
            print(_format_task_row_v2(task))
    else:
        if disposition:
            raise ValueError("--disposition requires schema-v2 task contracts.")
        if status:
            tasks = [task for task in tasks if task["status"] == status]
        print("ID       LEGACY_STATUS KIND           EXECUTION_SCOPE               TITLE")
        print("-------- ------------- -------------- ----------------------------- -----")
        for task in tasks:
            print(_format_task_row_v1(task))
    print(f"\n{len(tasks)} task contract(s). No row authorizes autonomous execution.")
    return 0


def _print_requirement_list(title: str, entries: Any, id_field: str | None = None) -> None:
    print(f"\n{title}:")
    if not isinstance(entries, list) or not entries:
        print("  (none)")
        return
    for entry in entries:
        if isinstance(entry, dict):
            entry_id = str(entry.get(id_field) or "").strip() if id_field else ""
            reference = str(entry.get("reference") or "").strip()
            requirement = str(entry.get("requirement") or "").strip()
            label = f"{entry_id} " if entry_id else ""
            if reference:
                print(f"  - {label}[{reference}] {requirement}")
            else:
                print(f"  - {label}{requirement}")
        else:
            print(f"  - {entry}")


def command_show(graph, selector: str) -> int:
    task = _resolve_task(graph, selector)
    print(f"{task['id']} — {task['title']}")
    print(f"schema_version:     {task['schema_version']}")
    print(f"reconciliation_key: {task['reconciliation_key']}")
    print(f"kind/type:          {task['kind']} / {task.get('type', '')}")
    if task["schema_version"] == TASK_CONTRACT_SCHEMA_VERSION:
        print(f"contract_revision:  {task['contract_revision']}")
        print(f"disposition:        {task['contract_disposition']}")
    else:
        print(f"legacy_status:      {task['status']} (historical/advisory only)")
    print(f"execution_scope:    {task['execution_scope']}")
    if task.get("execution_reason"):
        print(f"execution_reason:   {task['execution_reason']}")
    print(f"decomposition:      {task.get('decomposition_state', '')}")

    parent = str(task.get("parent") or "").strip()
    print(f"parent:             {parent or '(root)'}")
    print("\nDependencies:")
    for dependency_id in task.get("depends_on", []):
        dependency = graph.tasks_by_id[dependency_id]
        if dependency["schema_version"] == TASK_CONTRACT_SCHEMA_VERSION:
            state = f"disposition={dependency['contract_disposition']}"
        else:
            state = f"legacy_status={dependency['status']}"
        print(f"  - {dependency_id} [{state}] {dependency['title']}")
    if not task.get("depends_on"):
        print("  (none)")

    _print_requirement_list(
        "Acceptance criteria",
        task.get("acceptance_criteria", []),
        "criterion_id" if _is_v2(graph) else None,
    )
    if _is_v2(graph):
        _print_requirement_list("Completion gates", task.get("completion_gates", []), "gate_id")
        _print_requirement_list(
            "Downstream integration obligations",
            task.get("downstream_integration_obligations", []),
            "obligation_id",
        )
        print(f"\nProvenance:\n  {task.get('provenance', {})}")
    else:
        _print_requirement_list("Legacy validation requirements", task.get("validation_requirements", []))
    print("\nEvidence-derived current-state inspection: available via taskcontrol state")
    print("Execution authorization: denied — dispatch authorization policy is not enabled")
    print("State inspection alone never authorizes execution.")
    return 0


def advisory_ready_tasks(graph) -> list[dict[str, Any]]:
    """Return the old v1 planning frontier only while v1 files still exist.

    Schema v2 deliberately has no completion status. Dependency readiness is not
    derived because the dispatch policy that would define it is not enabled.
    """
    if _is_v2(graph):
        return []
    by_id = graph.tasks_by_id
    ready = []
    for task in graph.plan.tasks:
        if task["status"] != "open":
            continue
        if task["kind"] not in {"implementation", "artifact"}:
            continue
        if task["execution_scope"] != "single_agent":
            continue
        if all(by_id[dep]["status"] == "complete" for dep in task["depends_on"]):
            ready.append(task)
    return _sorted_tasks(ready)


def ready_tasks(graph):
    _ = graph
    raise UnsafeExecutionAuthorizationError(
        "ready_tasks() is disabled. Evidence-derived current-state inspection does not "
        "provide execution authority, and dependency-readiness and dispatch policy are "
        "not enabled."
    )


def command_ready(graph) -> int:
    if _is_v2(graph):
        print("TASK READINESS: UNAVAILABLE — DISPATCH POLICY NOT ENABLED")
        print("Evidence-derived current-state inspection exists via taskcontrol state.")
        print("Evidence-derived current conformance has been proven on at least one real task.")
        print("A conformant result does not establish dependency readiness.")
        print("Dependency-readiness policy has not been implemented or approved.")
        print("Dispatch authorization policy has not been implemented or approved.")
        print("State inspection and a conformant result never authorize autonomous execution.")
        print("Zero tasks are authorized for autonomous dispatch.")
        return 0

    tasks = advisory_ready_tasks(graph)
    print("ADVISORY LEGACY READY WORK — NOT AUTHORIZED FOR AUTONOMOUS DISPATCH")
    print("This view exists only until schema-v2 migration removes legacy status.\n")
    for task in tasks:
        print(f"{task['id']:<8} {task['kind']:<14} {task['title']}")
    print(f"\n{len(tasks)} advisory task(s). Zero authorized task(s).")
    return 0


def command_authorize(graph, selector: str) -> int:
    task = _resolve_task(graph, selector)
    assessment = assess_execution_authorization(task)
    print("EXECUTION AUTHORIZATION: DENIED")
    print(f"task:        {task['id']} — {task['title']}")
    print(f"reason_code: {assessment.reason_code}")
    print(f"reason:      {assessment.message}")
    return 2


def command_state(selector: str, as_json: bool = False) -> int:
    result = evaluate_current_conformance(selector=selector)
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"{result.task_id} — {result.title}")
    print(f"derived_state:    {result.state}")
    print(f"HEAD commit:      {result.head_commit}")
    print(f"HEAD tree:        {result.head_tree}")
    print(f"selected_record:  {result.selected_record_id or '(none)'}")
    print("findings:")
    for finding in result.findings:
        suffix = f" [{finding.record_id}]" if finding.record_id else ""
        print(f"  - {finding.code}{suffix}: {finding.message}")
    if result.dirty_worktree:
        print("WARNING: working tree is dirty; state above describes committed HEAD only.")
    return 0


def command_graph(graph) -> int:
    children: dict[str, list[str]] = defaultdict(list)
    for task in graph.plan.tasks:
        parent = str(task.get("parent") or "").strip()
        if parent:
            children[parent].append(task["id"])
    for values in children.values():
        values.sort(key=lambda value: int(value.split("-", 1)[1]))

    def render(task_id: str, depth: int) -> None:
        task = graph.tasks_by_id[task_id]
        if _is_v2(graph):
            state = f"disposition={task['contract_disposition']}"
        else:
            state = f"legacy_status={task['status']}"
        deps = ""
        if task["depends_on"]:
            deps = " deps=" + ",".join(task["depends_on"])
        print(
            f"{'  ' * depth}{task_id} [{state}] [{task['kind']}] "
            f"[{task['execution_scope']}] {task['title']}{deps}"
        )
        for child_id in children.get(task_id, []):
            render(child_id, depth + 1)

    render(graph.validation.root_id, 0)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic task-contract inspection CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--status", choices=("open", "complete"))
    list_parser.add_argument("--disposition", choices=("active", "superseded", "cancelled"))
    list_parser.add_argument("--kind", choices=("feature", "artifact", "implementation"))
    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("task")
    subparsers.add_parser("ready")
    authorize_parser = subparsers.add_parser("authorize")
    authorize_parser.add_argument("task")
    state_parser = subparsers.add_parser("state")
    state_parser.add_argument("task")
    state_parser.add_argument("--json", action="store_true")
    subparsers.add_parser("graph")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "state":
            return command_state(args.task, args.json)
        graph = load_persistent_work_graph()
        if args.command == "validate":
            return command_validate(graph)
        if args.command == "list":
            return command_list(graph, args.status, args.disposition, args.kind)
        if args.command == "show":
            return command_show(graph, args.task)
        if args.command == "ready":
            return command_ready(graph)
        if args.command == "authorize":
            return command_authorize(graph, args.task)
        if args.command == "graph":
            return command_graph(graph)
        parser.error(f"Unknown command: {args.command}")
    except (
        PersistentWorkGraphError,
        UnsafeExecutionAuthorizationError,
        WorkGraphValidationError,
        ValueError,
        KeyError,
    ) as exc:
        print(f"taskcontrol {args.command}: FAIL\n{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
