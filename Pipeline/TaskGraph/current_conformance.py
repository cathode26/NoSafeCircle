from __future__ import annotations

"""Deterministic current-conformance evaluation against committed HEAD."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from conformance_records import (
    CANON_PATH,
    CommittedRecord,
    ConformanceRecordError,
    GitRepository,
    canonical_text_sha256,
    load_committed_records,
    semantic_json_sha256,
)
from decomposition_graph_semantics import aggregate_child_state_summary

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    record_id: str | None = None


@dataclass(frozen=True)
class ConformanceState:
    task_id: str
    title: str
    state: str
    head_commit: str
    head_tree: str
    selected_record_id: str | None
    findings: tuple[Finding, ...]
    dirty_worktree: bool

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["findings"] = [asdict(item) for item in self.findings]
        return value


def _json(repo: GitRepository, commit: str, path: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(repo.read(commit, path).decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError, ConformanceRecordError) as exc:
        raise ConformanceRecordError(f"Unable to load {label} {path} at {commit}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConformanceRecordError(f"{label} {path} must contain a JSON object.")
    return value


def resolve_committed_task(repo: GitRepository, head: str, selector: str) -> tuple[str, dict[str, Any]]:
    raw = selector.strip()
    if not raw:
        raise ValueError("Task selector may not be blank.")
    direct = f"Tasks/{raw.upper()}.yaml"
    if repo.exists(head, direct):
        task = _json(repo, head, direct, "task contract")
        return direct, task
    matches: list[tuple[str, dict[str, Any]]] = []
    for path in repo.files(head, "Tasks"):
        if not path.endswith(".yaml"):
            continue
        task = _json(repo, head, path, "task contract")
        if task.get("reconciliation_key") == raw:
            matches.append((path, task))
    if len(matches) != 1:
        raise ValueError(f"Unknown task: {selector!r}. Use an NSC-* ID or reconciliation_key.")
    return matches[0]


def _finding(code: str, message: str, record: CommittedRecord | None = None) -> Finding:
    return Finding(code, message, record.record_id if record else None)


def _validate_basis_graph(repo: GitRepository, records: list[CommittedRecord]) -> list[Finding]:
    by_id = {record.record_id: record for record in records}
    findings: list[Finding] = []
    for record in records:
        if record.data["record_type"] != "revalidation":
            continue
        basis_id = record.data["revalidation"]["basis_record_id"]
        basis = by_id.get(basis_id)
        if basis is None:
            findings.append(_finding("basis_missing", f"Basis record {basis_id} does not exist.", record))
            continue
        if basis.data["task_id"] != record.data["task_id"]:
            findings.append(_finding("basis_task_mismatch", "Revalidation basis belongs to another task.", record))
        if not repo.is_ancestor(basis.validated_commit, record.validated_commit):
            findings.append(_finding("basis_not_ancestor", "Basis validated commit is not an ancestor of revalidation commit.", record))
        seen = {record.record_id}
        cursor = basis
        while cursor.data["record_type"] == "revalidation":
            if cursor.record_id in seen:
                findings.append(_finding("basis_cycle", "Revalidation basis chain contains a cycle.", record))
                break
            seen.add(cursor.record_id)
            next_id = cursor.data["revalidation"]["basis_record_id"]
            if next_id not in by_id:
                break
            cursor = by_id[next_id]
    return findings


def _current_gate_ids(task: dict[str, Any]) -> list[str]:
    gates = task.get("completion_gates")
    if not isinstance(gates, list):
        raise ConformanceRecordError("Current task contract completion_gates must be a list.")
    result = [gate.get("gate_id") if isinstance(gate, dict) else None for gate in gates]
    if any(not isinstance(item, str) or not item for item in result) or len(set(result)) != len(result):
        raise ConformanceRecordError("Current task contract has invalid or duplicate completion gate IDs.")
    return result  # type: ignore[return-value]


def _maximal(repo: GitRepository, records: list[CommittedRecord]) -> list[CommittedRecord]:
    maximal: list[CommittedRecord] = []
    for candidate in records:
        if any(
            other.record_id != candidate.record_id
            and other.validated_commit != candidate.validated_commit
            and repo.is_ancestor(candidate.validated_commit, other.validated_commit)
            for other in records
        ):
            continue
        maximal.append(candidate)
    return sorted(maximal, key=lambda item: item.record_id)


def _explicit_aggregate_conformance(
    *,
    root: Path | str,
    task: dict[str, Any],
    head: str,
    head_tree: str,
    dirty: bool,
) -> ConformanceState | None:
    child_ids = task.get("decomposition_children")
    if not (
        task.get("kind") == "feature"
        and task.get("decomposition_state") == "decomposed"
        and isinstance(child_ids, list)
        and child_ids
    ):
        return None

    child_states: dict[str, str] = {}
    for child_id in child_ids:
        child_result = evaluate_current_conformance(root=root, selector=child_id)
        child_states[child_id] = child_result.state
    complete, summary = aggregate_child_state_summary(child_states)
    task_id = str(task.get("id") or "")
    title = str(task.get("title") or "")
    if complete:
        return ConformanceState(
            task_id,
            title,
            "conformant",
            head,
            head_tree,
            None,
            (
                _finding(
                    "aggregate_children_conformant",
                    "All explicitly delegated decomposition children are conformant; "
                    f"aggregate completion is derived without a separate parent implementation pass ({summary}).",
                ),
            ),
            dirty,
        )
    return ConformanceState(
        task_id,
        title,
        "aggregate",
        head,
        head_tree,
        None,
        (
            _finding(
                "aggregate_children_incomplete",
                "Decomposed feature remains aggregate until every explicitly delegated child is conformant "
                f"({summary}).",
            ),
        ),
        dirty,
    )


def evaluate_current_conformance(root: Path | str = ROOT, selector: str = "") -> ConformanceState:
    repo = GitRepository(root)
    head = repo.head()
    head_tree = repo.tree(head)
    dirty = repo.dirty()
    task_path, task = resolve_committed_task(repo, head, selector)
    task_id = str(task.get("id") or "")
    title = str(task.get("title") or "")

    if task.get("schema_version") != "2.0":
        raise ValueError(f"{task_id or task_path}: state requires a schema-v2 task contract at committed HEAD.")

    disposition = task.get("contract_disposition")
    if disposition in {"cancelled", "superseded"}:
        return ConformanceState(task_id, title, disposition, head, head_tree, None,
            (_finding(f"contract_{disposition}", f"Contract disposition is {disposition}."),), dirty)

    aggregate_result = _explicit_aggregate_conformance(
        root=root,
        task=task,
        head=head,
        head_tree=head_tree,
        dirty=dirty,
    )
    if aggregate_result is not None:
        return aggregate_result

    if task.get("kind") == "feature" or task.get("execution_scope") != "single_agent":
        return ConformanceState(task_id, title, "aggregate", head, head_tree, None,
            (_finding("non_executable_contract", "Feature or non-executable contract is aggregate."),), dirty)

    try:
        records = load_committed_records(repo, head, task_id)
    except ConformanceRecordError as exc:
        return ConformanceState(task_id, title, "invalid_evidence", head, head_tree, None,
            (_finding("record_structure_invalid", str(exc)),), dirty)
    if not records:
        return ConformanceState(task_id, title, "not_delivered", head, head_tree, None,
            (_finding("no_committed_evidence", "No committed delivery, baseline, or revalidation record exists."),), dirty)

    invalid = _validate_basis_graph(repo, records)
    current_contract_hash = semantic_json_sha256(repo.read(head, task_path))
    current_revision = task.get("contract_revision")
    current_gate_ids = _current_gate_ids(task)
    conformant: list[CommittedRecord] = []
    replan: list[CommittedRecord] = []
    human: list[CommittedRecord] = []
    stale: list[CommittedRecord] = []

    for record in records:
        data = record.data
        state = data["validated_state"]
        try:
            if repo.tree(state["commit"]) != state["tree"]:
                invalid.append(_finding("validated_tree_mismatch", "Recorded tree does not match validated commit.", record))
                continue
            contract = data["task_contract"]
            historical_task_raw = repo.read(state["commit"], contract["path"])
            historical_task = json.loads(historical_task_raw.decode("utf-8-sig"))
            if semantic_json_sha256(historical_task) != contract["sha256"] or historical_task.get("contract_revision") != contract["revision"] or historical_task.get("id") != task_id:
                invalid.append(_finding("recorded_contract_mismatch", "Recorded contract identity/hash is false at validated commit.", record))
                continue
            canon = data["canon"]
            if canonical_text_sha256(repo.read(state["commit"], canon["path"])) != canon["sha256"]:
                invalid.append(_finding("recorded_canon_mismatch", "Recorded canon hash is false at validated commit.", record))
                continue
            bad_surface = False
            changed_surface = False
            for surface in data["conformance_surfaces"]:
                if repo.blob(state["commit"], surface["path"]) != surface["blob_sha"]:
                    invalid.append(_finding("surface_validated_blob_mismatch", f"Surface {surface['path']} blob is false at validated commit.", record))
                    bad_surface = True
                    break
                if not repo.exists(head, surface["path"]) or repo.blob(head, surface["path"]) != surface["blob_sha"]:
                    changed_surface = True
            if bad_surface:
                continue
            artifact_bad = False
            for gate in data["gate_results"]:
                for evidence in gate["evidence"]:
                    artifact_prefix = f"Pipeline/TaskGraph/evidence/{task_id}/artifacts/"
                    if not evidence["path"].startswith(artifact_prefix):
                        invalid.append(_finding("artifact_location_invalid", f"Gate artifact is outside {artifact_prefix}.", record))
                        artifact_bad = True
                    elif not repo.exists(head, evidence["path"]) or repo.blob(head, evidence["path"]) != evidence["blob_sha"]:
                        invalid.append(_finding("artifact_blob_mismatch", f"Evidence artifact {evidence['path']} is absent or altered at HEAD.", record))
                        artifact_bad = True
            if artifact_bad:
                continue
        except (ConformanceRecordError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            invalid.append(_finding("record_object_unavailable", str(exc), record))
            continue

        if not repo.is_ancestor(state["commit"], head):
            stale.append(record)
            continue

        record_gate_ids = [gate["gate_id"] for gate in data["gate_results"]]
        if record_gate_ids != current_gate_ids and set(record_gate_ids) != set(current_gate_ids):
            invalid.append(_finding("completion_gate_set_mismatch", "Record does not contain exactly the current completion-gate set.", record))
            continue
        contract_changed = contract["path"] != task_path or contract["revision"] != current_revision or contract["sha256"] != current_contract_hash
        if contract_changed:
            replan.append(record)
            continue
        approval = data["human_approval"]
        if approval["required"] and (approval["decision"] != "approved" or not approval["approved_by"].strip()):
            human.append(record)
            continue
        if (not approval["required"] and approval["decision"] != "not_required"):
            invalid.append(_finding("human_approval_contradictory", "Non-required approval must use not_required.", record))
            continue
        if changed_surface or canon["path"] != CANON_PATH:
            stale.append(record)
            continue
        conformant.append(record)

    if invalid:
        return ConformanceState(task_id, title, "invalid_evidence", head, head_tree, None, tuple(invalid), dirty)
    if conformant:
        maximal = _maximal(repo, conformant)
        if len(maximal) != 1:
            ids = ", ".join(item.record_id for item in maximal)
            return ConformanceState(task_id, title, "ambiguous_evidence", head, head_tree, None,
                (_finding("multiple_maximal_current_records", f"Multiple maximal current-valid records: {ids}."),), dirty)
        selected = maximal[0]
        return ConformanceState(task_id, title, "conformant", head, head_tree, selected.record_id,
            (_finding("current_record_selected", "Record is valid for the current task contract, conformance surfaces, gates, artifacts, and its recorded canon provenance.", selected),), dirty)
    for state_name, candidates, code, message in (
        ("needs_replan", replan, "contract_changed", "Current contract revision or semantic hash differs from prior evidence."),
        ("needs_human", human, "human_approval_missing", "Required human approval is missing."),
        ("needs_testing", stale, "evidence_stale", "Prior evidence exists, but current HEAD changed a tracked surface or lineage; the previously completed task may need testing again."),
    ):
        if candidates:
            maximal = _maximal(repo, candidates)
            selected = maximal[0] if len(maximal) == 1 else None
            return ConformanceState(task_id, title, state_name, head, head_tree,
                selected.record_id if selected else None, (_finding(code, message, selected),), dirty)
    return ConformanceState(task_id, title, "not_delivered", head, head_tree, None,
        (_finding("no_usable_evidence", "No usable committed evidence exists."),), dirty)
