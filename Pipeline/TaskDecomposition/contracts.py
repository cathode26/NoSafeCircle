"""Immutable, exact decomposition-result contract snapshots."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

TASK_ID_RE = re.compile(r"^NSC-\d{3,}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LOCAL_KEY_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ENTRY_PATTERNS = {
    "acceptance_criteria": ("criterion_id", re.compile(r"^AC-\d{3,}$")),
    "completion_gates": ("gate_id", re.compile(r"^VAL-\d{3,}$")),
    "downstream_integration_obligations": ("obligation_id", re.compile(r"^INT-\d{3,}$")),
}
DECISIONS = {"already_concrete", "decomposed", "needs_artifact", "needs_human"}
GAP_TYPES = {"none", "execution", "design", "uncertain"}
DISPOSITIONS = {
    "retained_by_parent", "assigned_to_child", "shared_integration",
    "blocked_by_artifact", "blocked_by_human",
}


class DecompositionContractError(ValueError):
    """Raised when untrusted decomposition data is structurally invalid."""


def _snapshot(value: Any, path: str = "$") -> Any:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise DecompositionContractError(f"{path} must contain only finite JSON numbers.")
        return value
    if type(value) is list:
        return [_snapshot(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if type(value) is dict:
        result = {}
        for key, item in value.items():
            if type(key) is not str:
                raise DecompositionContractError(f"{path} object keys must be strings.")
            result[key] = _snapshot(item, f"{path}.{key}")
        return result
    raise DecompositionContractError(
        f"{path} must contain exact JSON-compatible built-in values; got {type(value).__name__}."
    )


def _object(value: Any, label: str, required: set[str], optional: set[str] = frozenset()) -> dict[str, Any]:
    if type(value) is not dict:
        raise DecompositionContractError(f"{label} must be an object.")
    missing = required - set(value)
    extra = set(value) - required - optional
    if missing or extra:
        raise DecompositionContractError(
            f"{label} fields differ from contract (missing={sorted(missing)}, extra={sorted(extra)})."
        )
    return value


def _text(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or (not allow_empty and not value.strip()):
        qualifier = "string" if allow_empty else "non-blank string"
        raise DecompositionContractError(f"{label} must be a {qualifier}.")
    return value if allow_empty else value.strip()


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        raise DecompositionContractError(f"{label} must be a positive integer (booleans are invalid).")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise DecompositionContractError(f"{label} must be an array.")
    return value


def _string_tuple(value: Any, label: str, *, allow_empty_items: bool = False) -> tuple[str, ...]:
    items = tuple(
        _text(item, f"{label}[{index}]", allow_empty=allow_empty_items)
        for index, item in enumerate(_list(value, label))
    )
    if len(items) != len(set(items)):
        raise DecompositionContractError(f"{label} contains duplicate values.")
    return items


@dataclass(frozen=True)
class ParentTaskIdentity:
    task_id: str
    contract_revision: int
    contract_sha256: str

    @classmethod
    def from_dict(cls, raw: Any, label: str = "parent_task") -> "ParentTaskIdentity":
        value = _object(raw, label, {"task_id", "contract_revision", "contract_sha256"})
        task_id = _text(value["task_id"], f"{label}.task_id")
        if not TASK_ID_RE.fullmatch(task_id):
            raise DecompositionContractError(f"{label}.task_id has invalid NSC identity: {task_id!r}.")
        revision = _positive_int(value["contract_revision"], f"{label}.contract_revision")
        sha256 = _text(value["contract_sha256"], f"{label}.contract_sha256")
        if not SHA256_RE.fullmatch(sha256):
            raise DecompositionContractError(f"{label}.contract_sha256 must be lowercase SHA-256.")
        return cls(task_id, revision, sha256)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "contract_revision": self.contract_revision,
            "contract_sha256": self.contract_sha256,
        }


@dataclass(frozen=True)
class ChildRequirementEntry:
    entry_id: str
    reference: str
    requirement: str

    @classmethod
    def from_dict(cls, raw: Any, entry_type: str, label: str) -> "ChildRequirementEntry":
        id_field, pattern = ENTRY_PATTERNS[entry_type]
        value = _object(raw, label, {id_field, "reference", "requirement"})
        entry_id = _text(value[id_field], f"{label}.{id_field}")
        if not pattern.fullmatch(entry_id):
            raise DecompositionContractError(f"{label}.{id_field} has invalid format: {entry_id!r}.")
        return cls(
            entry_id,
            _text(value["reference"], f"{label}.reference"),
            _text(value["requirement"], f"{label}.requirement"),
        )

    def to_dict(self, entry_type: str) -> dict[str, str]:
        id_field = ENTRY_PATTERNS[entry_type][0]
        return {id_field: self.entry_id, "reference": self.reference, "requirement": self.requirement}


def _entries(raw: Any, entry_type: str, label: str) -> tuple[ChildRequirementEntry, ...]:
    values = tuple(
        ChildRequirementEntry.from_dict(item, entry_type, f"{label}[{index}]")
        for index, item in enumerate(_list(raw, label))
    )
    ids = [entry.entry_id for entry in values]
    if len(ids) != len(set(ids)):
        raise DecompositionContractError(f"{label} contains duplicate entry IDs.")
    return values


@dataclass(frozen=True)
class EvidenceEntry:
    reference: str
    requirement: str

    @classmethod
    def from_dict(cls, raw: Any, label: str) -> "EvidenceEntry":
        value = _object(raw, label, {"reference", "requirement"})
        return cls(
            _text(value["reference"], f"{label}.reference"),
            _text(value["requirement"], f"{label}.requirement"),
        )

    def to_dict(self) -> dict[str, str]:
        return {"reference": self.reference, "requirement": self.requirement}


@dataclass(frozen=True)
class ChildProposal:
    local_key: str
    title: str
    kind: str
    type: str
    execution_scope: str
    execution_reason: str
    decomposition_state: str
    decomposition_reason: str
    existing_task_dependencies: tuple[str, ...]
    local_dependencies: tuple[str, ...]
    exclusive_resources: tuple[str, ...]
    acceptance_criteria: tuple[ChildRequirementEntry, ...]
    completion_gates: tuple[ChildRequirementEntry, ...]
    downstream_integration_obligations: tuple[ChildRequirementEntry, ...]
    gdd_evidence: tuple[EvidenceEntry, ...]
    basis: str
    source_scope: str
    confidence: str
    notes: str

    @classmethod
    def from_dict(cls, raw: Any, label: str) -> "ChildProposal":
        fields = {
            "local_key", "title", "kind", "type", "execution_scope", "execution_reason",
            "decomposition_state", "decomposition_reason", "existing_task_dependencies",
            "local_dependencies", "exclusive_resources", "acceptance_criteria",
            "completion_gates", "downstream_integration_obligations", "gdd_evidence",
            "basis", "source_scope", "confidence", "notes",
        }
        value = _object(raw, label, fields)
        local_key = _text(value["local_key"], f"{label}.local_key")
        if not LOCAL_KEY_RE.fullmatch(local_key):
            raise DecompositionContractError(f"{label}.local_key must be a conservative lowercase ASCII slug.")
        existing = _string_tuple(value["existing_task_dependencies"], f"{label}.existing_task_dependencies")
        for task_id in existing:
            if not TASK_ID_RE.fullmatch(task_id):
                raise DecompositionContractError(f"{label}.existing_task_dependencies contains invalid task ID {task_id!r}.")
        local_dependencies = _string_tuple(value["local_dependencies"], f"{label}.local_dependencies")
        for dependency in local_dependencies:
            if not LOCAL_KEY_RE.fullmatch(dependency):
                raise DecompositionContractError(f"{label}.local_dependencies contains invalid local key {dependency!r}.")
        resources = _string_tuple(value["exclusive_resources"], f"{label}.exclusive_resources")
        evidence = tuple(
            EvidenceEntry.from_dict(item, f"{label}.gdd_evidence[{index}]")
            for index, item in enumerate(_list(value["gdd_evidence"], f"{label}.gdd_evidence"))
        )
        return cls(
            local_key=local_key,
            title=_text(value["title"], f"{label}.title"),
            kind=_text(value["kind"], f"{label}.kind"),
            type=_text(value["type"], f"{label}.type"),
            execution_scope=_text(value["execution_scope"], f"{label}.execution_scope"),
            execution_reason=_text(value["execution_reason"], f"{label}.execution_reason"),
            decomposition_state=_text(value["decomposition_state"], f"{label}.decomposition_state"),
            decomposition_reason=_text(value["decomposition_reason"], f"{label}.decomposition_reason"),
            existing_task_dependencies=existing,
            local_dependencies=local_dependencies,
            exclusive_resources=resources,
            acceptance_criteria=_entries(value["acceptance_criteria"], "acceptance_criteria", f"{label}.acceptance_criteria"),
            completion_gates=_entries(value["completion_gates"], "completion_gates", f"{label}.completion_gates"),
            downstream_integration_obligations=_entries(value["downstream_integration_obligations"], "downstream_integration_obligations", f"{label}.downstream_integration_obligations"),
            gdd_evidence=evidence,
            basis=_text(value["basis"], f"{label}.basis"),
            source_scope=_text(value["source_scope"], f"{label}.source_scope"),
            confidence=_text(value["confidence"], f"{label}.confidence"),
            notes=_text(value["notes"], f"{label}.notes", allow_empty=True),
        )

    def entry_ids(self, entry_type: str) -> set[str]:
        return {entry.entry_id for entry in getattr(self, entry_type)}

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_key": self.local_key,
            "title": self.title,
            "kind": self.kind,
            "type": self.type,
            "execution_scope": self.execution_scope,
            "execution_reason": self.execution_reason,
            "decomposition_state": self.decomposition_state,
            "decomposition_reason": self.decomposition_reason,
            "existing_task_dependencies": list(self.existing_task_dependencies),
            "local_dependencies": list(self.local_dependencies),
            "exclusive_resources": list(self.exclusive_resources),
            "acceptance_criteria": [
                ChildRequirementEntry.to_dict(entry, "acceptance_criteria")
                for entry in self.acceptance_criteria
            ],
            "completion_gates": [
                ChildRequirementEntry.to_dict(entry, "completion_gates")
                for entry in self.completion_gates
            ],
            "downstream_integration_obligations": [
                ChildRequirementEntry.to_dict(entry, "downstream_integration_obligations")
                for entry in self.downstream_integration_obligations
            ],
            "gdd_evidence": [EvidenceEntry.to_dict(entry) for entry in self.gdd_evidence],
            "basis": self.basis,
            "source_scope": self.source_scope,
            "confidence": self.confidence,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ChildCoverageTarget:
    local_key: str
    child_entry_type: str
    child_entry_id: str

    @classmethod
    def from_dict(cls, raw: Any, label: str) -> "ChildCoverageTarget":
        value = _object(raw, label, {"local_key", "child_entry_type", "child_entry_id"})
        local_key = _text(value["local_key"], f"{label}.local_key")
        if not LOCAL_KEY_RE.fullmatch(local_key):
            raise DecompositionContractError(f"{label}.local_key has invalid format.")
        entry_type = _text(value["child_entry_type"], f"{label}.child_entry_type")
        if entry_type not in ENTRY_PATTERNS:
            raise DecompositionContractError(f"{label}.child_entry_type is invalid: {entry_type!r}.")
        entry_id = _text(value["child_entry_id"], f"{label}.child_entry_id")
        if not ENTRY_PATTERNS[entry_type][1].fullmatch(entry_id):
            raise DecompositionContractError(f"{label}.child_entry_id has invalid format for {entry_type}.")
        return cls(local_key, entry_type, entry_id)

    def to_dict(self) -> dict[str, str]:
        return {
            "local_key": self.local_key,
            "child_entry_type": self.child_entry_type,
            "child_entry_id": self.child_entry_id,
        }


@dataclass(frozen=True)
class ParentCoverageRecord:
    parent_entry_type: str
    parent_entry_id: str
    disposition: str
    child_targets: tuple[ChildCoverageTarget, ...]
    reason: str
    integration_rationale: str

    @classmethod
    def from_dict(cls, raw: Any, label: str) -> "ParentCoverageRecord":
        value = _object(
            raw, label,
            {"parent_entry_type", "parent_entry_id", "disposition", "child_targets", "reason", "integration_rationale"},
        )
        entry_type = _text(value["parent_entry_type"], f"{label}.parent_entry_type")
        if entry_type not in ENTRY_PATTERNS:
            raise DecompositionContractError(f"{label}.parent_entry_type is invalid: {entry_type!r}.")
        entry_id = _text(value["parent_entry_id"], f"{label}.parent_entry_id")
        if not ENTRY_PATTERNS[entry_type][1].fullmatch(entry_id):
            raise DecompositionContractError(f"{label}.parent_entry_id has invalid format for {entry_type}.")
        disposition = _text(value["disposition"], f"{label}.disposition")
        if disposition not in DISPOSITIONS:
            raise DecompositionContractError(f"{label}.disposition is invalid: {disposition!r}.")
        targets = tuple(
            ChildCoverageTarget.from_dict(item, f"{label}.child_targets[{index}]")
            for index, item in enumerate(_list(value["child_targets"], f"{label}.child_targets"))
        )
        target_keys = [(target.local_key, target.child_entry_type, target.child_entry_id) for target in targets]
        if len(target_keys) != len(set(target_keys)):
            raise DecompositionContractError(f"{label}.child_targets contains duplicates.")
        return cls(
            entry_type, entry_id, disposition, targets,
            _text(value["reason"], f"{label}.reason"),
            _text(value["integration_rationale"], f"{label}.integration_rationale", allow_empty=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_entry_type": self.parent_entry_type,
            "parent_entry_id": self.parent_entry_id,
            "disposition": self.disposition,
            "child_targets": [ChildCoverageTarget.to_dict(target) for target in self.child_targets],
            "reason": self.reason,
            "integration_rationale": self.integration_rationale,
        }


@dataclass(frozen=True)
class ParentObligationRef:
    parent_entry_type: str
    parent_entry_id: str

    @classmethod
    def from_dict(cls, raw: Any, label: str) -> "ParentObligationRef":
        value = _object(raw, label, {"parent_entry_type", "parent_entry_id"})
        entry_type = _text(value["parent_entry_type"], f"{label}.parent_entry_type")
        if entry_type not in ENTRY_PATTERNS:
            raise DecompositionContractError(f"{label}.parent_entry_type is invalid.")
        entry_id = _text(value["parent_entry_id"], f"{label}.parent_entry_id")
        if not ENTRY_PATTERNS[entry_type][1].fullmatch(entry_id):
            raise DecompositionContractError(f"{label}.parent_entry_id has invalid format.")
        return cls(entry_type, entry_id)

    def to_dict(self) -> dict[str, str]:
        return {"parent_entry_type": self.parent_entry_type, "parent_entry_id": self.parent_entry_id}


@dataclass(frozen=True)
class ArtifactProposal:
    title: str
    purpose: str
    source_parent_obligations: tuple[ParentObligationRef, ...]
    authorized_decisions_needed: tuple[str, ...]
    out_of_scope: tuple[str, ...]

    @classmethod
    def from_dict(cls, raw: Any, label: str = "artifact_proposal") -> "ArtifactProposal":
        value = _object(
            raw, label,
            {"title", "purpose", "source_parent_obligations", "authorized_decisions_needed", "out_of_scope"},
        )
        refs = tuple(
            ParentObligationRef.from_dict(item, f"{label}.source_parent_obligations[{index}]")
            for index, item in enumerate(_list(value["source_parent_obligations"], f"{label}.source_parent_obligations"))
        )
        keys = [(ref.parent_entry_type, ref.parent_entry_id) for ref in refs]
        if not refs or len(keys) != len(set(keys)):
            raise DecompositionContractError(f"{label}.source_parent_obligations must be non-empty and unique.")
        decisions = _string_tuple(value["authorized_decisions_needed"], f"{label}.authorized_decisions_needed")
        out_of_scope = _string_tuple(value["out_of_scope"], f"{label}.out_of_scope")
        if not decisions or not out_of_scope:
            raise DecompositionContractError(f"{label} must identify decisions needed and explicit out-of-scope areas.")
        return cls(
            _text(value["title"], f"{label}.title"),
            _text(value["purpose"], f"{label}.purpose"),
            refs, decisions, out_of_scope,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "purpose": self.purpose,
            "source_parent_obligations": [
                ParentObligationRef.to_dict(ref) for ref in self.source_parent_obligations
            ],
            "authorized_decisions_needed": list(self.authorized_decisions_needed),
            "out_of_scope": list(self.out_of_scope),
        }


@dataclass(frozen=True)
class DecompositionResult:
    schema_version: str
    parent_task: ParentTaskIdentity
    decision: str
    gap_type: str
    reason: str
    children: tuple[ChildProposal, ...]
    parent_requirement_coverage: tuple[ParentCoverageRecord, ...]
    unsupported_assumptions: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    artifact_proposal: ArtifactProposal | None

    @classmethod
    def from_dict(cls, raw: Any) -> "DecompositionResult":
        value = _snapshot(raw)
        required = {
            "schema_version", "parent_task", "decision", "gap_type", "reason", "children",
            "parent_requirement_coverage", "unsupported_assumptions", "unresolved_questions",
        }
        value = _object(value, "decomposition_result", required, {"artifact_proposal"})
        version = _text(value["schema_version"], "decomposition_result.schema_version")
        if version != "1.0":
            raise DecompositionContractError(f"Unsupported decomposition schema_version: {version!r}.")
        decision = _text(value["decision"], "decomposition_result.decision")
        gap_type = _text(value["gap_type"], "decomposition_result.gap_type")
        if decision not in DECISIONS:
            raise DecompositionContractError(f"Unsupported decomposition decision: {decision!r}.")
        if gap_type not in GAP_TYPES:
            raise DecompositionContractError(f"Unsupported gap_type: {gap_type!r}.")
        children = tuple(
            ChildProposal.from_dict(item, f"decomposition_result.children[{index}]")
            for index, item in enumerate(_list(value["children"], "decomposition_result.children"))
        )
        keys = [child.local_key for child in children]
        if len(keys) != len(set(keys)):
            raise DecompositionContractError("decomposition_result.children contains duplicate local_key values.")
        coverage = tuple(
            ParentCoverageRecord.from_dict(item, f"decomposition_result.parent_requirement_coverage[{index}]")
            for index, item in enumerate(_list(value["parent_requirement_coverage"], "decomposition_result.parent_requirement_coverage"))
        )
        artifact = ArtifactProposal.from_dict(value["artifact_proposal"]) if "artifact_proposal" in value else None
        return cls(
            version,
            ParentTaskIdentity.from_dict(value["parent_task"]),
            decision,
            gap_type,
            _text(value["reason"], "decomposition_result.reason"),
            children,
            coverage,
            _string_tuple(value["unsupported_assumptions"], "decomposition_result.unsupported_assumptions"),
            _string_tuple(value["unresolved_questions"], "decomposition_result.unresolved_questions"),
            artifact,
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "parent_task": ParentTaskIdentity.to_dict(self.parent_task),
            "decision": self.decision,
            "gap_type": self.gap_type,
            "reason": self.reason,
            "children": [ChildProposal.to_dict(child) for child in self.children],
            "parent_requirement_coverage": [
                ParentCoverageRecord.to_dict(record)
                for record in self.parent_requirement_coverage
            ],
            "unsupported_assumptions": list(self.unsupported_assumptions),
            "unresolved_questions": list(self.unresolved_questions),
        }
        if self.artifact_proposal is not None:
            result["artifact_proposal"] = ArtifactProposal.to_dict(self.artifact_proposal)
        return result

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
