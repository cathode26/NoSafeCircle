"""Load and validate the committed Stage 2 read-only dispatch-planning policy.

``dispatch_policy.json`` is the committed policy authority for
:mod:`dispatch_plan`. The loader fails closed on any weakening: Stage 2 only
permits ``mode: read_only_plan`` with ``autonomous_dispatch: false``. Widening
either of those requires a reviewed policy *and* code change together, mirror-
ing how :mod:`claim_policy` guards the Stage 1 claim layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import TaskReviewContractError

DISPATCH_POLICY_PATH = Path(__file__).resolve().parent / "dispatch_policy.json"
DISPATCH_POLICY_SCHEMA_VERSION = "1.0"
REQUIRED_MODE = "read_only_plan"
REQUIRED_PREFERENCE = "resume_existing_before_fresh"


class DispatchPolicyError(TaskReviewContractError):
    """Raised when the committed dispatch policy is missing, invalid, or weakened."""


@dataclass(frozen=True)
class DispatchPolicy:
    schema_version: str
    mode: str
    autonomous_dispatch: bool
    preference: str
    fresh_implementation_derived_states: tuple[str, ...]
    dependency_dispatch_satisfied_states: tuple[str, ...]
    known_dependency_states: tuple[str, ...]


def _non_empty_string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise DispatchPolicyError(f"dispatch policy {field} must be a non-empty list")
    items = tuple(value)
    if any(type(item) is not str or not item.strip() for item in items):
        raise DispatchPolicyError(f"dispatch policy {field} must contain non-empty strings")
    if len(set(items)) != len(items):
        raise DispatchPolicyError(f"dispatch policy {field} contains duplicates")
    return items


def load_dispatch_policy(path: Path | str | None = None) -> DispatchPolicy:
    policy_path = Path(path) if path is not None else DISPATCH_POLICY_PATH
    try:
        raw = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DispatchPolicyError(f"dispatch policy could not be read: {policy_path}") from exc
    if not isinstance(raw, dict):
        raise DispatchPolicyError("dispatch policy must be one JSON object")
    expected_keys = {
        "schema_version",
        "mode",
        "autonomous_dispatch",
        "preference",
        "fresh_implementation_derived_states",
        "dependency_dispatch_satisfied_states",
        "known_dependency_states",
    }
    if set(raw) != expected_keys:
        raise DispatchPolicyError(f"dispatch policy keys do not match contract: {sorted(raw)}")
    if raw["schema_version"] != DISPATCH_POLICY_SCHEMA_VERSION:
        raise DispatchPolicyError("dispatch policy has an unsupported schema_version")
    if raw["mode"] != REQUIRED_MODE:
        raise DispatchPolicyError(
            f"dispatch policy mode must remain {REQUIRED_MODE!r} in Stage 2: {raw['mode']!r}"
        )
    if raw["autonomous_dispatch"] is not False:
        raise DispatchPolicyError(
            "dispatch policy autonomous_dispatch must remain false in Stage 2"
        )
    if raw["preference"] != REQUIRED_PREFERENCE:
        raise DispatchPolicyError(
            f"dispatch policy preference must remain {REQUIRED_PREFERENCE!r}: "
            f"{raw['preference']!r}"
        )
    fresh_states = _non_empty_string_tuple(
        raw["fresh_implementation_derived_states"],
        field="fresh_implementation_derived_states",
    )
    satisfied_states = _non_empty_string_tuple(
        raw["dependency_dispatch_satisfied_states"],
        field="dependency_dispatch_satisfied_states",
    )
    known_states = _non_empty_string_tuple(
        raw["known_dependency_states"], field="known_dependency_states"
    )
    if not set(satisfied_states) <= set(known_states):
        raise DispatchPolicyError(
            "dispatch policy dependency_dispatch_satisfied_states must be a subset of "
            "known_dependency_states"
        )
    return DispatchPolicy(
        schema_version=raw["schema_version"],
        mode=raw["mode"],
        autonomous_dispatch=False,
        preference=raw["preference"],
        fresh_implementation_derived_states=fresh_states,
        dependency_dispatch_satisfied_states=satisfied_states,
        known_dependency_states=known_states,
    )


def dependencies_dispatch_satisfied(
    dependency_states: Iterable[Mapping[str, Any]] | None,
    policy: DispatchPolicy | None = None,
) -> bool:
    """True when every dependency observation is dispatch-satisfied.

    This is the ONE dependency-admission predicate: current strict
    conformance (``state == "conformant"``) and ``needs_testing`` (carrying
    revalidation debt) both count as dispatch-satisfied per the committed
    policy, matching :func:`dispatch_plan.evaluate_fresh_candidate`. Callers
    gating dispatch/coordination admission (:mod:`goal_loop`,
    :mod:`real_workflow`) reuse this instead of each hardcoding their own
    dependency predicate.
    """

    policy = policy or load_dispatch_policy()
    return all(
        isinstance(item, Mapping)
        and item.get("error") is None
        and item.get("state") in policy.dependency_dispatch_satisfied_states
        for item in (dependency_states or ())
    )


__all__ = [
    "DISPATCH_POLICY_PATH",
    "DISPATCH_POLICY_SCHEMA_VERSION",
    "DispatchPolicy",
    "DispatchPolicyError",
    "dependencies_dispatch_satisfied",
    "load_dispatch_policy",
]
