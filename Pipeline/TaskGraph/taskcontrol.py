from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from typing import Any

from execution_authority import (
    UnsafeExecutionAuthorizationError,
    assess_execution_authorization,
)
from persistent_work_graph import PersistentWorkGraphError, load_persistent_work_graph
from work_graph_validate import WorkGraphValidationError


def _numeric_id(task: dict[str, Any]) -> int:
    return int(str(task["id"]).split("-", 1)[1])


def _sorted_tasks(tasks: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    return sorted(tasks, key=_numeric_id)


def _resolve_task(graph, selector: str) -> dict[str, Any]:
    raw = selector.strip()
    if not raw:
        raise ValueError("Task selector may not be blank.")

    by_id = graph.tasks_by_id
    by_key = graph.tasks_by_key

    upper = raw.upper()
    if upper in by_id:
        return by_id[upper]
    if raw in by_key:
        return by_key[raw]

    raise ValueError(f"Unknown task: {selector!r}. Use an NSC-* ID or reconciliation_key.")


def _format_task_row(task: dict[str, Any]) -> str:
    return (
        f"{task['id']:<8} "
        f"{task['status']:<13} "
        f"{task['kind']:<14} "
        f"{task['execution_scope']:<29} "
        f"{task['title']}"
    )


def command_validate(graph) -> int:
    summary = graph.validation
    complete = sum(1 for task in graph.plan.tasks if task["status"] == "complete")
    open_count = len(graph.plan.tasks) - complete
    print("taskcontrol validate: PASS")
    print(f"Tasks:                         {summary.task_count}")
    print(f"Legacy YAML open:              {open_count}")
    print(f"Legacy YAML complete:          {complete}")
    print(f"Root:                          {summary.root_id} ({summary.root_key})")
    print(f"Parent edges:                  {summary.parent_edge_count}")
    print(f"Dependency edges:              {summary.dependency_edge_count}")
    print(f"Resource groups:               {summary.resource_group_count}")
    print(f"Project requirements:          {summary.project_requirement_count}")
    print("Parent hierarchy:              connected + acyclic")
    print("Dependency graph:              acyclic")
    print("Bootstrap marker:              present + complete")
    print("Autonomous dispatch authority: DISABLED (Phase 1 safety guard)")
    return 0


def command_list(graph, status: str | None, kind: str | None) -> int:
    tasks = _sorted_tasks(graph.plan.tasks)
    if status:
        tasks = [task for task in tasks if task["status"] == status]
    if kind:
        tasks = [task for task in tasks if task["kind"] == kind]

    print("ID       LEGACY_STATUS KIND           EXECUTION_SCOPE               TITLE")
    print("-------- ------------- -------------- ----------------------------- -----")
    for task in tasks:
        print(_format_task_row(task))
    print(f"\n{len(tasks)} task(s). Legacy status is advisory only.")
    return 0


def _print_requirement_list(title: str, entries: Any) -> None:
    print(f"\n{title}:")
    if not isinstance(entries, list) or not entries:
        print("  (none)")
        return
    for entry in entries:
        if isinstance(entry, dict):
            reference = str(entry.get("reference") or "").strip()
            requirement = str(entry.get("requirement") or "").strip()
            if reference:
                print(f"  - [{reference}] {requirement}")
            else:
                print(f"  - {requirement}")
        else:
            print(f"  - {entry}")


def command_show(graph, selector: str) -> int:
    task = _resolve_task(graph, selector)
    by_id = graph.tasks_by_id

    print(f"{task['id']} — {task['title']}")
    print(f"reconciliation_key: {task['reconciliation_key']}")
    print(f"kind/type:          {task['kind']} / {task.get('type', '')}")
    print(f"legacy_status:      {task['status']} (advisory only)")
    print(f"execution_scope:    {task['execution_scope']}")
    if task.get("execution_reason"):
        print(f"execution_reason:   {task['execution_reason']}")
    print(f"decomposition:      {task.get('decomposition_state', '')}")
    if task.get("decomposition_reason"):
        print(f"decomposition_reason: {task['decomposition_reason']}")

    parent = str(task.get("parent") or "").strip()
    if parent:
        parent_task = by_id[parent]
        print(f"parent:             {parent} — {parent_task['title']}")
    else:
        print("parent:             (root)")

    print("\nDependencies:")
    dependencies = task.get("depends_on", [])
    if not dependencies:
        print("  (none)")
    else:
        for dependency_id in dependencies:
            dependency = by_id[dependency_id]
            print(
                f"  - {dependency_id} "
                f"[legacy_status={dependency['status']}] {dependency['title']}"
            )

    print("\nExclusive resources:")
    resources = task.get("exclusive_resources", [])
    if not resources:
        print("  (none)")
    else:
        for resource in resources:
            print(f"  - {resource}")

    _print_requirement_list("Acceptance criteria", task.get("acceptance_criteria", []))
    _print_requirement_list("Validation requirements", task.get("validation_requirements", []))

    if task.get("notes"):
        print(f"\nNotes:\n  {task['notes']}")
    print(f"\nRepository state at bootstrap: {task.get('repository_state_at_bootstrap', '')}")
    print("Execution authorization: not derivable from this task file")
    return 0


def advisory_ready_tasks(graph) -> list[dict[str, Any]]:
    """Return the legacy status-derived frontier for human planning only.

    This calculation intentionally preserves the Milestone 1 bootstrap behavior
    so humans can inspect the graph. It is not execution authority and must not
    be consumed by an autonomous dispatcher.
    """

    by_id = graph.tasks_by_id
    ready: list[dict[str, Any]] = []
    for task in graph.plan.tasks:
        if task["status"] != "open":
            continue
        if task["kind"] not in {"implementation", "artifact"}:
            continue
        if task["execution_scope"] != "single_agent":
            continue
        if all(by_id[dependency_id]["status"] == "complete" for dependency_id in task["depends_on"]):
            ready.append(task)
    return _sorted_tasks(ready)


def ready_tasks(graph) -> list[dict[str, Any]]:
    """Reject the old ambiguous API instead of returning dispatch candidates."""

    _ = graph
    raise UnsafeExecutionAuthorizationError(
        "ready_tasks() is disabled because legacy Tasks/*.yaml status cannot "
        "authorize execution. Use advisory_ready_tasks() only for human planning, "
        "and use evidence-derived authorization after Phase 2 is implemented."
    )


def command_ready(graph) -> int:
    tasks = advisory_ready_tasks(graph)
    print("ADVISORY READY WORK — NOT AUTHORIZED FOR AUTONOMOUS DISPATCH")
    print("Derived from mutable legacy Tasks/*.yaml status fields.")
    print("Use this list for human planning only; `taskcontrol authorize` currently denies all tasks.\n")
    if not tasks:
        print("  (none)")
        return 0

    print("ID       KIND           TITLE")
    print("-------- -------------- -----")
    for task in tasks:
        print(f"{task['id']:<8} {task['kind']:<14} {task['title']}")
    print(f"\n{len(tasks)} advisory task(s). Zero autonomously authorized task(s).")
    return 0


def command_authorize(graph, selector: str) -> int:
    task = _resolve_task(graph, selector)
    assessment = assess_execution_authorization(task)

    state = "AUTHORIZED" if assessment.authorized else "DENIED"
    print(f"EXECUTION AUTHORIZATION: {state}")
    print(f"task:          {task['id']} — {task['title']}")
    print(f"legacy_status: {task['status']}")
    print(f"reason_code:   {assessment.reason_code}")
    print(f"reason:        {assessment.message}")
    return 0 if assessment.authorized else 2


def command_graph(graph) -> int:
    by_id = graph.tasks_by_id
    children: dict[str, list[str]] = defaultdict(list)
    root_id = graph.validation.root_id

    for task in graph.plan.tasks:
        parent = str(task.get("parent") or "").strip()
        if parent:
            children[parent].append(task["id"])
    for values in children.values():
        values.sort(key=lambda task_id: int(task_id.split("-", 1)[1]))

    def render(task_id: str, depth: int) -> None:
        task = by_id[task_id]
        legacy_status = "complete" if task["status"] == "complete" else "open"
        scope = task["execution_scope"]
        prefix = "  " * depth
        dep_suffix = ""
        if task["depends_on"]:
            dep_suffix = " deps=" + ",".join(task["depends_on"])
        print(
            f"{prefix}{task_id} [legacy_status={legacy_status}] "
            f"[{task['kind']}] [{scope}] {task['title']}{dep_suffix}"
        )
        for child_id in children.get(task_id, []):
            render(child_id, depth + 1)

    render(root_id, 0)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic local CLI for the persistent No Safe Circle work graph."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="Validate the current persistent work graph.")

    list_parser = subparsers.add_parser("list", help="List persistent work items.")
    list_parser.add_argument(
        "--status",
        choices=("open", "complete"),
        help="Filter by legacy advisory YAML status.",
    )
    list_parser.add_argument("--kind", choices=("feature", "artifact", "implementation"))

    show_parser = subparsers.add_parser("show", help="Show one work item by NSC ID or reconciliation key.")
    show_parser.add_argument("task")

    subparsers.add_parser(
        "ready",
        help="List the legacy status-derived advisory frontier; never authorizes dispatch.",
    )

    authorize_parser = subparsers.add_parser(
        "authorize",
        help="Check autonomous execution authority. Phase 1 intentionally denies all tasks.",
    )
    authorize_parser.add_argument("task")

    subparsers.add_parser("graph", help="Print the parent hierarchy and dependency references.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        graph = load_persistent_work_graph()
        if args.command == "validate":
            return command_validate(graph)
        if args.command == "list":
            return command_list(graph, args.status, args.kind)
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
