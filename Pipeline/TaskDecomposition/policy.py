"""Deterministic semantic policy for decomposition-result contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from .contracts import DecompositionContractError, DecompositionResult, ENTRY_PATTERNS


class DecompositionPolicyError(ValueError):
    """Raised when a structurally valid result violates decomposition policy."""


def semantic_json_sha256(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parent_entries(parent_task: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for entry_type, (id_field, _) in ENTRY_PATTERNS.items():
        entries = parent_task.get(entry_type)
        if type(entries) is not list:
            raise DecompositionPolicyError(f"parent_task.{entry_type} must be an array.")
        for index, entry in enumerate(entries):
            if type(entry) is not dict or type(entry.get(id_field)) is not str:
                raise DecompositionPolicyError(f"parent_task.{entry_type}[{index}] is malformed.")
            key = (entry_type, entry[id_field])
            if key in result:
                raise DecompositionPolicyError(f"Parent contains duplicate requirement entry {entry_type}/{entry[id_field]}.")
            result[key] = entry
    return result


def validate_decomposition_result(
    raw: Any,
    *,
    parent_task: dict[str, Any],
    existing_reconciliation_keys: Iterable[str] = (),
) -> DecompositionResult:
    """Validate, detach, and return one immutable decomposition proposal."""

    try:
        if type(raw) is DecompositionResult:
            serialized = json.dumps(
                DecompositionResult.to_dict(raw),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            result = DecompositionResult.from_dict(json.loads(serialized))
        elif isinstance(raw, DecompositionResult):
            raise DecompositionContractError(
                "decomposition_result subclasses are not accepted; an exact DecompositionResult is required."
            )
        else:
            result = DecompositionResult.from_dict(raw)
    except DecompositionContractError:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise DecompositionContractError(
            f"decomposition_result could not be serialized through the base contract: {exc}"
        ) from exc
    if type(parent_task) is not dict:
        raise DecompositionPolicyError("parent_task must be an exact built-in object.")
    identity = result.parent_task
    if parent_task.get("id") != identity.task_id:
        raise DecompositionPolicyError("Decomposition parent task ID does not match the selected contract.")
    revision = parent_task.get("contract_revision")
    if type(revision) is not int or revision != identity.contract_revision:
        raise DecompositionPolicyError("Decomposition parent contract revision does not match the selected contract.")
    actual_hash = semantic_json_sha256(parent_task)
    if actual_hash != identity.contract_sha256:
        raise DecompositionPolicyError("Decomposition parent semantic contract SHA-256 does not match the selected contract.")

    expected_gap = {
        "already_concrete": {"none"},
        "decomposed": {"execution"},
        "needs_artifact": {"design"},
        "needs_human": {"uncertain", "design", "execution"},
    }[result.decision]
    if result.gap_type not in expected_gap:
        raise DecompositionPolicyError(
            f"Decision {result.decision!r} is incompatible with gap_type {result.gap_type!r}."
        )

    if result.decision == "decomposed":
        if not result.children:
            raise DecompositionPolicyError("decomposed requires one or more child proposals.")
    elif result.children:
        raise DecompositionPolicyError(f"{result.decision} may not contain child proposals.")

    if result.decision == "needs_artifact":
        if result.artifact_proposal is None:
            raise DecompositionPolicyError("needs_artifact requires one smallest-necessary artifact proposal.")
    elif result.artifact_proposal is not None:
        raise DecompositionPolicyError(f"{result.decision} may not contain an artifact proposal.")

    if result.decision in {"already_concrete", "decomposed"}:
        if result.unsupported_assumptions or result.unresolved_questions:
            raise DecompositionPolicyError("Accepted decomposition output may not contain unsupported assumptions or unresolved questions.")
    if result.decision == "needs_human" and not result.unresolved_questions:
        raise DecompositionPolicyError("needs_human requires unresolved questions explaining why publication cannot proceed.")

    existing_keys = set(existing_reconciliation_keys)
    for child in result.children:
        if child.local_key in existing_keys:
            raise DecompositionPolicyError(f"Child local_key collides with existing reconciliation_key: {child.local_key!r}.")
        if child.kind != "implementation" or child.execution_scope != "single_agent" or child.decomposition_state != "concrete":
            raise DecompositionPolicyError(
                f"Child {child.local_key!r} must be implementation/single_agent/concrete."
            )
        if not child.acceptance_criteria:
            raise DecompositionPolicyError(
                f"Child {child.local_key!r} requires at least one acceptance criterion."
            )
        if not child.completion_gates:
            raise DecompositionPolicyError(
                f"Child {child.local_key!r} requires at least one completion gate."
            )
        if identity.task_id in child.existing_task_dependencies:
            raise DecompositionPolicyError(
                f"Child {child.local_key!r} may not depend on selected aggregate parent {identity.task_id}."
            )

    parent_entries = _parent_entries(parent_task)
    coverage_by_parent: dict[tuple[str, str], Any] = {}
    traced_child_entries: set[tuple[str, str, str]] = set()
    child_by_key = {child.local_key: child for child in result.children}
    allowed_dispositions = {
        "already_concrete": {"retained_by_parent"},
        "decomposed": {"assigned_to_child", "shared_integration"},
        "needs_artifact": {"retained_by_parent", "blocked_by_artifact"},
        "needs_human": {"retained_by_parent", "blocked_by_human"},
    }[result.decision]

    for record in result.parent_requirement_coverage:
        parent_key = (record.parent_entry_type, record.parent_entry_id)
        if parent_key not in parent_entries:
            raise DecompositionPolicyError(
                f"Coverage invents unknown parent obligation {record.parent_entry_type}/{record.parent_entry_id}."
            )
        if parent_key in coverage_by_parent:
            raise DecompositionPolicyError(
                f"Duplicate parent coverage for {record.parent_entry_type}/{record.parent_entry_id}."
            )
        coverage_by_parent[parent_key] = record
        if record.disposition not in allowed_dispositions:
            raise DecompositionPolicyError(
                f"Coverage disposition {record.disposition!r} is invalid for decision {result.decision!r}."
            )
        if record.disposition in {"retained_by_parent", "blocked_by_artifact", "blocked_by_human"} and record.child_targets:
            raise DecompositionPolicyError(f"Coverage disposition {record.disposition!r} may not have child targets.")
        if record.disposition == "assigned_to_child" and not record.child_targets:
            raise DecompositionPolicyError("assigned_to_child requires at least one exact child target.")
        if record.disposition == "shared_integration" and not record.child_targets:
            raise DecompositionPolicyError("shared_integration requires at least one exact child target.")
        if (
            record.disposition == "shared_integration"
            and len(record.child_targets) == 1
            and not record.integration_rationale.strip()
        ):
            raise DecompositionPolicyError(
                "shared_integration with one child target requires an explicit integration rationale."
            )
        for target in record.child_targets:
            child = child_by_key.get(target.local_key)
            if child is None:
                raise DecompositionPolicyError(f"Coverage target references unknown child {target.local_key!r}.")
            if target.child_entry_id not in child.entry_ids(target.child_entry_type):
                raise DecompositionPolicyError(
                    f"Coverage target references unknown child entry {target.local_key}/{target.child_entry_type}/{target.child_entry_id}."
                )
            traced_child_entries.add((target.local_key, target.child_entry_type, target.child_entry_id))

    missing = set(parent_entries) - set(coverage_by_parent)
    if missing:
        rendered = ", ".join(f"{kind}/{entry_id}" for kind, entry_id in sorted(missing))
        raise DecompositionPolicyError(f"Missing parent requirement coverage: {rendered}.")

    if result.decision == "needs_artifact" and not any(
        record.disposition == "blocked_by_artifact" for record in coverage_by_parent.values()
    ):
        raise DecompositionPolicyError("needs_artifact requires at least one blocked_by_artifact obligation.")
    if result.decision == "needs_human" and not any(
        record.disposition == "blocked_by_human" for record in coverage_by_parent.values()
    ):
        raise DecompositionPolicyError("needs_human requires at least one blocked_by_human obligation.")

    targeted_child_keys = {
        target.local_key
        for record in result.parent_requirement_coverage
        for target in record.child_targets
    }
    for child in result.children:
        if child.local_key not in targeted_child_keys:
            raise DecompositionPolicyError(
                f"Child {child.local_key!r} is not targeted by any parent coverage record."
            )
        for entry_type in ENTRY_PATTERNS:
            for entry_id in child.entry_ids(entry_type):
                target = (child.local_key, entry_type, entry_id)
                if target not in traced_child_entries:
                    raise DecompositionPolicyError(
                        f"Untraced child obligation {child.local_key}/{entry_type}/{entry_id}."
                    )

    if result.artifact_proposal is not None:
        artifact_sources: set[tuple[str, str]] = set()
        for ref in result.artifact_proposal.source_parent_obligations:
            parent_key = (ref.parent_entry_type, ref.parent_entry_id)
            if parent_key not in parent_entries:
                raise DecompositionPolicyError(
                    f"Artifact proposal references unknown parent obligation {ref.parent_entry_type}/{ref.parent_entry_id}."
                )
            if coverage_by_parent[parent_key].disposition != "blocked_by_artifact":
                raise DecompositionPolicyError(
                    "Artifact proposal source obligation "
                    f"{ref.parent_entry_type}/{ref.parent_entry_id} must have blocked_by_artifact coverage."
                )
            artifact_sources.add(parent_key)
        blocked_by_artifact = {
            parent_key
            for parent_key, record in coverage_by_parent.items()
            if record.disposition == "blocked_by_artifact"
        }
        if artifact_sources != blocked_by_artifact:
            missing = sorted(blocked_by_artifact - artifact_sources)
            extra = sorted(artifact_sources - blocked_by_artifact)
            raise DecompositionPolicyError(
                "Artifact proposal source obligations must exactly match blocked_by_artifact "
                f"coverage (missing={missing}, extra={extra})."
            )
    return result
