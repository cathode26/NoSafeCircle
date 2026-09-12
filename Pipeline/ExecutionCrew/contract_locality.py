"""Deterministic context assembly and structured-output validation for the mandatory,
read-only Contract Locality Auditor that runs before the Implementer.

This module never edits a task contract, the GDD, or the graph. It only shapes committed
task-contract data into auditor prompt context and deterministically checks the auditor's
structured output for internal consistency. Dispatch readiness / dependency-completion
authority is out of scope; see Pipeline/TaskGraph/work_graph_validate.py for that concern.
"""

from __future__ import annotations

from typing import Any, Mapping

CONTRACT_LOCALITY_AUDIT_SCHEMA_VERSION = "1.0"

# Every nonlocal classification requires one specific recommended_action; local_to_task is
# the only classification that is not, itself, a blocking finding.
CLASSIFICATION_ACTIONS: dict[str, str] = {
    "local_to_task": "keep",
    "requires_declared_dependency": "add_dependency",
    "downstream_integration": "move_to_downstream_integration",
    "missing_design": "clarify_design",
    "ambiguous": "human_review",
}
NONLOCAL_CLASSIFICATIONS = frozenset(CLASSIFICATION_ACTIONS) - {"local_to_task"}


class ContractLocalityError(RuntimeError):
    """Raised when committed task-catalog data cannot be safely shaped for the audit."""


def _text_field(task: Mapping[str, Any], field: str, task_id: str) -> str:
    value = task.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ContractLocalityError(f"{task_id}.{field} must be a non-empty string.")
    return value.strip()


def task_catalog_entry(task: Mapping[str, Any]) -> dict[str, Any]:
    task_id = _text_field(task, "id", str(task.get("id")))
    reconciliation_key = _text_field(task, "reconciliation_key", task_id)
    title = _text_field(task, "title", task_id)
    kind = _text_field(task, "kind", task_id)
    execution_scope = _text_field(task, "execution_scope", task_id)
    decomposition_state = _text_field(task, "decomposition_state", task_id)
    parent = task.get("parent") or ""
    if not isinstance(parent, str):
        raise ContractLocalityError(f"{task_id}.parent must be a string.")
    depends_on = task.get("depends_on")
    if not isinstance(depends_on, list) or any(not isinstance(item, str) for item in depends_on):
        raise ContractLocalityError(f"{task_id}.depends_on must be a list of strings.")
    return {
        "id": task_id,
        "reconciliation_key": reconciliation_key,
        "title": title,
        "kind": kind,
        "type": task.get("type") if isinstance(task.get("type"), str) else kind,
        "execution_scope": execution_scope,
        "decomposition_state": decomposition_state,
        "parent": parent,
        "depends_on": list(depends_on),
    }


def build_task_catalog(tasks_by_id: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic, id-sorted catalog covering every committed task contract."""
    return [task_catalog_entry(tasks_by_id[task_id]) for task_id in sorted(tasks_by_id)]


def direct_dependency_contracts(
    task: Mapping[str, Any], tasks_by_id: Mapping[str, Mapping[str, Any]]
) -> dict[str, Mapping[str, Any]]:
    depends_on = task.get("depends_on") or ()
    return {dependency_id: tasks_by_id[dependency_id] for dependency_id in sorted(depends_on) if dependency_id in tasks_by_id}


def direct_dependent_contracts(
    task_id: str, tasks_by_id: Mapping[str, Mapping[str, Any]]
) -> dict[str, Mapping[str, Any]]:
    return {
        other_id: other
        for other_id, other in sorted(tasks_by_id.items())
        if task_id in (other.get("depends_on") or ())
    }


def expected_entry_ids(task: Mapping[str, Any]) -> dict[str, str]:
    """Map every current AC/VAL ID on the task to its expected entry_type."""
    expected: dict[str, str] = {}
    for item in task.get("acceptance_criteria", []):
        expected[item["criterion_id"]] = "acceptance_criterion"
    for item in task.get("completion_gates", []):
        expected[item["gate_id"]] = "completion_gate"
    return expected


def validate_locality_audit_output(
    output: Mapping[str, Any], *, task: Mapping[str, Any], valid_task_ids: frozenset[str]
) -> list[str]:
    """Deterministically check auditor output for internal consistency.

    Assumes `output` already satisfies the JSON-schema-level contract (AgentRunner validates
    structured_output against the request's output_schema before a role can succeed), so this
    only checks cross-field semantic consistency the schema itself cannot express.
    """
    reasons: list[str] = []
    expected = expected_entry_ids(task)

    entries = output.get("entry_results", [])
    entries_by_id: dict[str, Mapping[str, Any]] = {}
    seen_ids: list[Any] = []
    for entry in entries:
        entry_id = entry.get("id")
        seen_ids.append(entry_id)
        if isinstance(entry_id, str) and entry_id not in entries_by_id:
            entries_by_id[entry_id] = entry
    if len(seen_ids) != len(set(seen_ids)):
        reasons.append("contract locality auditor entry_results contains duplicate IDs")
    missing = sorted(set(expected) - set(seen_ids))
    unknown = sorted(set(seen_ids) - set(expected))
    if missing:
        reasons.append(f"contract locality auditor entry_results missing IDs: {', '.join(missing)}")
    if unknown:
        reasons.append(f"contract locality auditor entry_results contains unknown IDs: {', '.join(unknown)}")

    for entry_id, expected_type in expected.items():
        entry = entries_by_id.get(entry_id)
        if entry is None:
            continue
        if entry.get("entry_type") != expected_type:
            reasons.append(f"{entry_id} entry_type must be {expected_type}")
        classification = entry.get("classification")
        expected_action = CLASSIFICATION_ACTIONS.get(classification)
        if expected_action is None:
            reasons.append(f"{entry_id} has an unknown classification: {classification!r}")
        elif entry.get("recommended_action") != expected_action:
            reasons.append(
                f"{entry_id} classification {classification!r} requires recommended_action={expected_action!r}"
            )
        for related in entry.get("related_task_ids", []):
            if related not in valid_task_ids:
                reasons.append(f"{entry_id} references unknown related task ID: {related!r}")

    blocking = output.get("blocking_findings", [])
    blocking_by_entry: dict[str, Mapping[str, Any]] = {}
    for finding in blocking:
        entry_id = finding.get("entry_id")
        if isinstance(entry_id, str):
            if entry_id in blocking_by_entry:
                reasons.append(f"contract locality auditor blocking_findings contains duplicate entry_id {entry_id!r}")
            blocking_by_entry[entry_id] = finding
        for related in finding.get("related_task_ids", []):
            if related not in valid_task_ids:
                reasons.append(f"blocking finding {entry_id!r} references unknown related task ID: {related!r}")

    unknown_finding_ids = sorted(set(blocking_by_entry) - set(entries_by_id))
    if unknown_finding_ids:
        reasons.append(
            "contract locality auditor blocking_findings references unknown entry IDs: "
            + ", ".join(unknown_finding_ids)
        )

    nonlocal_ids = {
        entry_id
        for entry_id, entry in entries_by_id.items()
        if entry.get("classification") in NONLOCAL_CLASSIFICATIONS
    }
    local_ids = set(entries_by_id) - nonlocal_ids

    for entry_id in sorted(nonlocal_ids):
        entry = entries_by_id[entry_id]
        classification = entry.get("classification")
        finding = blocking_by_entry.get(entry_id)
        if finding is None:
            reasons.append(f"{entry_id} is classified {classification!r} but has no matching blocking_findings entry")
            continue
        if finding.get("reason_code") != classification:
            reasons.append(f"blocking finding {entry_id!r} reason_code must match entry classification {classification!r}")
        expected_action = CLASSIFICATION_ACTIONS.get(classification)
        if finding.get("recommended_action") != expected_action:
            reasons.append(f"blocking finding {entry_id!r} recommended_action must be {expected_action!r}")
        if classification == "requires_declared_dependency":
            entry_related = entry.get("related_task_ids", [])
            finding_related = finding.get("related_task_ids", [])
            if not entry_related:
                reasons.append(f"{entry_id} classification requires_declared_dependency requires a nonempty related_task_ids")
            if set(entry_related) != set(finding_related):
                reasons.append(f"blocking finding {entry_id!r} related_task_ids must match entry related_task_ids for requires_declared_dependency")

    for entry_id in sorted(local_ids):
        if entry_id in blocking_by_entry:
            reasons.append(f"{entry_id} is local_to_task and must not have a blocking_findings entry")

    status = output.get("status")
    if status == "pass" and (nonlocal_ids or blocking_by_entry):
        reasons.append("contract locality auditor status=pass requires every entry local_to_task and zero blocking findings")
    if status == "contract_review_required" and not nonlocal_ids:
        reasons.append("contract locality auditor status=contract_review_required requires at least one nonlocal entry")

    return reasons


# The auditor decides locality from what a related task *requires* or *owns*.
# These dependent-contract fields state neither: each one either repeats a value
# the deterministic task catalog in the same prompt already carries for every
# committed task, or records how that contract was derived. Requirement text --
# acceptance criteria, completion gates, downstream integration obligations,
# notes, exclusive resources, the execution/decomposition reasoning that says
# what a task keeps versus defers, and the depends_on edge itself -- is never
# omitted, so no locality decision loses an input it can turn on.
#
# This is a denylist on purpose. A field this module has not classified is
# retained, so a future task-contract schema addition cannot leave the audit
# silently.
DEPENDENT_CONTRACT_OMITTED_FIELDS: frozenset[str] = frozenset({
    # Already carried verbatim, for every committed task, by the task catalog.
    "decomposition_state",
    "execution_scope",
    "kind",
    "parent",
    "reconciliation_key",
    "type",
    # Derivation metadata. `gdd_evidence` is an excerpt of the canonical GDD the
    # auditor already holds in full, and the bootstrap repository observations
    # are a stale snapshot of a tree the auditor can read directly at the
    # audited head through its repository_read capability.
    "contract_revision",
    "gdd_evidence",
    "provenance",
    "repository_evidence_at_bootstrap",
    "repository_state_at_bootstrap",
    "schema_version",
})

# Synthesized by the payload below. A committed contract must not already carry
# them, or the audit would read a contract value as pipeline metadata.
_DEPENDENT_PAYLOAD_SYNTHETIC_FIELDS = ("committed_contract_path", "omitted_fields")


def auditor_dependent_contract_payload(
    dependent_contracts: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Project each direct dependent contract onto its locality-bearing fields.

    Every retained field keeps its exact committed value: nothing is summarized,
    truncated, reordered, or replaced by a title. Each entry additionally names
    the exact committed file holding the whole contract, so the omitted fields
    stay deterministically reachable through the repository read capability the
    auditor already has, at the same commit the audit is bound to.
    """
    payload: dict[str, dict[str, Any]] = {}
    for task_id in sorted(dependent_contracts):
        contract = dependent_contracts[task_id]
        reserved = [field for field in _DEPENDENT_PAYLOAD_SYNTHETIC_FIELDS if field in contract]
        if reserved:
            raise ContractLocalityError(
                f"{task_id} already defines reserved auditor payload field(s): {', '.join(reserved)}"
            )
        retained = {
            field: value
            for field, value in contract.items()
            if field not in DEPENDENT_CONTRACT_OMITTED_FIELDS
        }
        payload[task_id] = {
            **retained,
            "committed_contract_path": f"Tasks/{task_id}.yaml",
            "omitted_fields": sorted(set(contract) & DEPENDENT_CONTRACT_OMITTED_FIELDS),
        }
    return payload
