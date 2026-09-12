"""Narrow bridge from semantic review to deterministic Unity materialization.

This module does not approve a candidate. It recognizes only the one case in
which a validator's remaining blockers are registered Unity outputs that the
Windows materializer owns. Every other ``needs_changes`` result remains a
normal failed review.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .contracts import ExecutionScopePlan
from .door_prototype_materialization import (
    is_door_prototype_builder_output,
    is_unity_serialized,
)


MATERIALIZATION_REQUIRED_STATUS = "materialization_required"
_ALLOWED_NOT_PROVEN_REASONS = frozenset({
    "runtime_not_executed",
    "missing_required_artifact",
})


def registered_materialization_paths(plan: Any) -> tuple[str, ...]:
    """Return the exact Unity-serialized outputs registered in one scope."""

    if hasattr(plan, "existing_implementation_paths") and hasattr(
            plan, "new_implementation_paths"):
        existing = plan.existing_implementation_paths
        new = plan.new_implementation_paths
    elif hasattr(plan, "existing_paths") and hasattr(plan, "new_paths"):
        # ExecutionCrew's already-validated per-role plan deliberately uses
        # shorter field names. It carries the same exact implementation path
        # partition and reaches this bridge only after semantic review asks
        # whether a registered Unity output can be materialized.
        existing = plan.existing_paths
        new = plan.new_paths
    else:
        raise TypeError("materialization path plan has no implementation paths")
    implementation = (*existing, *new)
    return tuple(sorted(
        (
            path for path in implementation
            if is_door_prototype_builder_output(path) and is_unity_serialized(path)
        ),
        key=str.casefold,
    ))


def materialization_blockers_only(
    validator_output: Mapping[str, Any],
    registered_paths: Iterable[str],
) -> tuple[str, ...] | None:
    """Authenticate the narrow ``needs_changes`` materialization condition."""

    if not isinstance(validator_output, Mapping):
        return None
    if validator_output.get("status") != "needs_changes":
        return None
    registered = tuple(sorted(set(registered_paths), key=str.casefold))
    if not registered:
        return None

    issues = validator_output.get("blocking_issues")
    if not isinstance(issues, list) or not issues:
        return None
    issue_paths: list[str] = []
    for issue in issues:
        if not isinstance(issue, Mapping):
            return None
        path = issue.get("path")
        if type(path) is not str or not path or path not in registered:
            return None
        issue_paths.append(path)
    if len(set(issue_paths)) != len(issue_paths):
        return None

    criteria = validator_output.get("criteria_results")
    if not isinstance(criteria, list):
        return None
    for item in criteria:
        if not isinstance(item, Mapping):
            return None
        status = item.get("status")
        reason = item.get("reason_code")
        if status == "pass":
            if reason != "proved":
                return None
        elif status == "not_proven":
            if reason not in _ALLOWED_NOT_PROVEN_REASONS:
                return None
        else:
            # A failed criterion or malformed status is a source/review
            # problem. The materializer cannot cure it.
            return None
    return registered


def scope_materialization_paths(scope: Mapping[str, Any]) -> tuple[str, ...]:
    """Read materialization authority from one registered scope receipt."""

    if not isinstance(scope, Mapping):
        raise ValueError("registered execution scope is missing")
    plan = ExecutionScopePlan.from_dict(scope["plan"])
    return registered_materialization_paths(plan)


__all__ = [
    "MATERIALIZATION_REQUIRED_STATUS",
    "materialization_blockers_only",
    "registered_materialization_paths",
    "scope_materialization_paths",
]
