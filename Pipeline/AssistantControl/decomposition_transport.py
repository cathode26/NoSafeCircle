"""Bounded Docker command construction for AssistantControl decomposition."""
from __future__ import annotations

import re

from Pipeline.TaskReviewAgent.contracts import validate_task_id


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def build_compose_command(
    *, task_id: str, project: str, providers: str, max_calls: int,
    run_id: str,
) -> tuple[str, ...]:
    """Build the only decomposition transport AssistantControl supports.

    AssistantControl always uses two distinct providers and exactly two calls:
    one author followed by one independent reviewer. It does not inherit the
    production launcher's Issue, lease-pool, or workflow-state dependencies.
    """
    provider_order = tuple(item.strip() for item in providers.split(",") if item.strip())
    if (len(provider_order) != 2 or len(set(provider_order)) != 2
            or set(provider_order) != {"claude", "codex"}):
        raise ValueError("Assistant decomposition requires one Claude and one Codex role")
    if type(max_calls) is not int or max_calls != 2:
        raise ValueError("Assistant decomposition requires exactly two provider calls")
    if not _SAFE_ID.fullmatch(project):
        raise ValueError("Compose project name is invalid")
    if not _SAFE_ID.fullmatch(run_id):
        raise ValueError("Decomposition run id is invalid")
    return (
        "docker", "compose", "-p", project, "run", "--rm", "-T",
        "round-robin-decompose", "python3",
        "Pipeline/TaskDecomposition/run_round_robin_decomposition.py",
        "--task-id", validate_task_id(task_id),
        "--providers", ",".join(provider_order),
        "--max-calls", "2",
        "--run-id", run_id,
    )


__all__ = ["build_compose_command"]
