from __future__ import annotations

"""Deterministic delivery-evidence packager for one TaskGraph task.

This tool is clerical automation only. It reads one explicit JSON
delivery-spec file, verifies every precondition against the committed
repository, copies and validates the declared artifacts, computes every
hash and Git object identity itself, generates the immutable delivery
record, and validates that record with the existing authoritative schema
in conformance_records.py. It never stages, commits, pushes, merges, edits
a task contract, invokes Unity, invokes an LLM, or claims conformance.
TaskGraph's evidence-derived evaluator remains the sole authority for
derived state, and only after the generated files are committed.
"""

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from conformance_records import (
    CANON_PATH,
    EVIDENCE_ROOT,
    SCHEMA_VERSION,
    TASK_ID_RE,
    ConformanceRecordError,
    GitRepository,
    canonical_text_sha256,
    safe_repository_path,
    semantic_json_sha256,
    validate_record_shape,
)

ROOT = Path(__file__).resolve().parents[2]

DELIVERY_SPEC_SCHEMA_VERSION = "1.0"
ARTIFACT_TYPES = {"unity_test_results", "unity_log", "human_validation", "other"}
EXTENSION_BY_ARTIFACT_TYPE = {
    "unity_test_results": ".xml",
    "unity_log": ".log",
    "human_validation": ".txt",
}
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
SAFE_REV_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/~^:-]{0,199}")


class RecordDeliveryError(RuntimeError):
    """Raised when a delivery package cannot be safely produced."""


class PublicationFailure(RuntimeError):
    """Raised when an unexpected failure occurs after publication started."""

    def __init__(self, published: list[str], cause: BaseException) -> None:
        super().__init__(str(cause))
        self.published = published
        self.cause = cause


# --------------------------------------------------------------------------
# Delivery-spec schema (distinct from, and not a replacement for, the
# authoritative conformance-record schema in conformance_records.py).
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SurfaceSpec:
    path: str
    role: str


@dataclass(frozen=True)
class ArtifactSpec:
    id: str
    type: str
    source_path: str
    name: str


@dataclass(frozen=True)
class GateSpec:
    gate_id: str
    evidence: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class ApprovalSpec:
    required: bool
    decision: str
    approved_by: str
    notes: str


@dataclass(frozen=True)
class DeliverySpec:
    task_id: str
    validated_commit: str
    base_commit: str
    candidate_commit: str
    surfaces: tuple[SurfaceSpec, ...]
    artifacts: tuple[ArtifactSpec, ...]
    gates: tuple[GateSpec, ...]
    human_approval: ApprovalSpec


def _fields(value: Any, label: str, required: set[str], optional: set[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RecordDeliveryError(f"{label} must be an object.")
    allowed = required | optional
    extra = set(value) - allowed
    missing = required - set(value)
    if extra or missing:
        raise RecordDeliveryError(
            f"{label} fields differ from the delivery-spec schema (missing={sorted(missing)}, extra={sorted(extra)})."
        )
    return value


def _text(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise RecordDeliveryError(f"{label} must be a {'string' if allow_empty else 'non-empty string'}.")
    return value


def _rev(value: Any, label: str) -> str:
    text = _text(value, label)
    if not SAFE_REV_RE.fullmatch(text):
        raise RecordDeliveryError(f"{label} is not a safe Git revision expression: {text!r}.")
    return text


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise RecordDeliveryError(f"{label} must be a boolean.")
    return value


def parse_delivery_spec(raw: Any) -> DeliverySpec:
    spec = _fields(
        raw,
        "delivery spec",
        {
            "schema_version", "task_id", "validated_commit", "base_commit",
            "candidate_commit", "surfaces", "artifacts", "gates", "human_approval",
        },
    )
    if spec["schema_version"] != DELIVERY_SPEC_SCHEMA_VERSION:
        raise RecordDeliveryError(f"Unsupported delivery-spec schema_version {spec['schema_version']!r}.")

    task_id = _text(spec["task_id"], "task_id")
    if not TASK_ID_RE.fullmatch(task_id):
        raise RecordDeliveryError(f"Invalid task_id {task_id!r}.")

    validated_commit = _rev(spec["validated_commit"], "validated_commit")
    base_commit = _rev(spec["base_commit"], "base_commit")
    candidate_commit = _rev(spec["candidate_commit"], "candidate_commit")

    raw_surfaces = spec["surfaces"]
    if not isinstance(raw_surfaces, list):
        raise RecordDeliveryError("surfaces must be a list.")
    surfaces: list[SurfaceSpec] = []
    seen_surface_paths: set[str] = set()
    for index, raw_surface in enumerate(raw_surfaces):
        item = _fields(raw_surface, f"surfaces[{index}]", {"path", "role"})
        path = safe_repository_path(item["path"], f"surfaces[{index}].path")
        role = _text(item["role"], f"surfaces[{index}].role")
        if path in seen_surface_paths:
            raise RecordDeliveryError(f"Duplicate conformance surface path: {path!r}.")
        seen_surface_paths.add(path)
        surfaces.append(SurfaceSpec(path=path, role=role))

    raw_artifacts = spec["artifacts"]
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise RecordDeliveryError("artifacts must be a non-empty list.")
    artifacts: list[ArtifactSpec] = []
    seen_artifact_ids: set[str] = set()
    for index, raw_artifact in enumerate(raw_artifacts):
        item = _fields(raw_artifact, f"artifacts[{index}]", {"id", "type", "source_path", "name"})
        artifact_id = _text(item["id"], f"artifacts[{index}].id")
        if artifact_id in seen_artifact_ids:
            raise RecordDeliveryError(f"Duplicate artifact id: {artifact_id!r}.")
        seen_artifact_ids.add(artifact_id)
        artifact_type = _text(item["type"], f"artifacts[{index}].type")
        if artifact_type not in ARTIFACT_TYPES:
            raise RecordDeliveryError(f"artifacts[{index}].type must be one of {sorted(ARTIFACT_TYPES)}, got {artifact_type!r}.")
        source_path = _text(item["source_path"], f"artifacts[{index}].source_path")
        name = _text(item["name"], f"artifacts[{index}].name")
        if not NAME_RE.fullmatch(name):
            raise RecordDeliveryError(f"artifacts[{index}].name {name!r} must contain only [A-Za-z0-9_.-] and not start with a separator.")
        artifacts.append(ArtifactSpec(id=artifact_id, type=artifact_type, source_path=source_path, name=name))

    raw_gates = spec["gates"]
    if not isinstance(raw_gates, list) or not raw_gates:
        raise RecordDeliveryError("gates must be a non-empty list.")
    gates: list[GateSpec] = []
    seen_gate_ids: set[str] = set()
    artifact_ids = seen_artifact_ids
    for index, raw_gate in enumerate(raw_gates):
        item = _fields(raw_gate, f"gates[{index}]", {"gate_id", "evidence"}, {"notes"})
        gate_id = _text(item["gate_id"], f"gates[{index}].gate_id")
        if gate_id in seen_gate_ids:
            raise RecordDeliveryError(f"Duplicate gate_id in delivery spec: {gate_id!r}.")
        seen_gate_ids.add(gate_id)
        raw_evidence = item["evidence"]
        if not isinstance(raw_evidence, list) or not raw_evidence:
            raise RecordDeliveryError(f"gates[{index}].evidence must be a non-empty list of artifact IDs.")
        evidence_ids: list[str] = []
        for evidence_index, raw_evidence_id in enumerate(raw_evidence):
            evidence_id = _text(raw_evidence_id, f"gates[{index}].evidence[{evidence_index}]")
            if evidence_id not in artifact_ids:
                raise RecordDeliveryError(f"gates[{index}].evidence references unknown artifact id {evidence_id!r}.")
            evidence_ids.append(evidence_id)
        notes = _text(item.get("notes", ""), f"gates[{index}].notes", allow_empty=True)
        gates.append(GateSpec(gate_id=gate_id, evidence=tuple(evidence_ids), notes=notes))

    raw_approval = spec["human_approval"]
    approval_item = _fields(raw_approval, "human_approval", {"required", "decision"}, {"approved_by", "notes"})
    required = _bool(approval_item["required"], "human_approval.required")
    decision = _text(approval_item["decision"], "human_approval.decision")
    if decision not in {"approved", "not_required"}:
        raise RecordDeliveryError(f"human_approval.decision must be 'approved' or 'not_required', got {decision!r}.")
    approved_by = _text(approval_item.get("approved_by", ""), "human_approval.approved_by", allow_empty=True)
    approval_notes = _text(approval_item.get("notes", ""), "human_approval.notes", allow_empty=True)

    return DeliverySpec(
        task_id=task_id,
        validated_commit=validated_commit,
        base_commit=base_commit,
        candidate_commit=candidate_commit,
        surfaces=tuple(surfaces),
        artifacts=tuple(artifacts),
        gates=tuple(gates),
        human_approval=ApprovalSpec(required=required, decision=decision, approved_by=approved_by, notes=approval_notes),
    )


def load_delivery_spec(path: Path) -> DeliverySpec:
    if not path.is_file():
        raise RecordDeliveryError(f"Delivery-spec file does not exist: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecordDeliveryError(f"Unable to parse delivery-spec JSON at {path}: {exc}") from exc
    return parse_delivery_spec(raw)


# --------------------------------------------------------------------------
# Additional deterministic Git object helpers (conformance_records.py is
# reused unmodified; these operate only on commit resolution and content
# hashing, never on the index or refs).
# --------------------------------------------------------------------------


def _run_git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RecordDeliveryError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def resolve_commit(root: Path, expression: str) -> str:
    return _run_git(root, "rev-parse", "--verify", f"{expression}^{{commit}}").decode().strip()


def hash_object_raw(root: Path, data: bytes) -> str:
    """Hash raw bytes exactly as given, with no clean filters applied.

    This is NOT what `git add` will store whenever a clean filter or
    text/eol normalization applies to the destination path (see
    hash_object_as_committed below). Only use this for content that is
    read directly from a committed Git object (which Git has already
    normalized once, at commit time) or in tests that specifically need
    the unfiltered value for comparison.
    """
    result = subprocess.run(
        ["git", "hash-object", "--stdin"], cwd=root, input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise RecordDeliveryError(f"git hash-object failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout.decode().strip()


def hash_object_as_committed(root: Path, repo_path: str, data: bytes) -> str:
    """Hash bytes the way Git will actually store them once staged.

    Uses --path=<repo_path> --filters so any clean filter or text/eol
    normalization that `git add -f -- <repo_path>` would apply (driven by
    .gitattributes at that path) is applied before hashing. This never
    touches the index, working tree, or object database (-w is never
    passed).
    """
    safe_repository_path(repo_path, "hash_object_as_committed repo_path")
    result = subprocess.run(
        ["git", "hash-object", "--stdin", f"--path={repo_path}", "--filters"], cwd=root, input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise RecordDeliveryError(f"git hash-object --filters failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout.decode().strip()


def require_committed_blob(root: Path, sha: str, path: str) -> None:
    """Reject a conformance surface whose resolved object is not a blob.

    GitRepository.blob() (conformance_records.py) only checks that
    `rev-parse <commit>:<path>` produced a syntactically valid 40-character
    SHA; a directory/tree resolves to such a SHA too. This checks the
    actual Git object type via plumbing, without touching the index.
    """
    result = subprocess.run(
        ["git", "cat-file", "-t", sha], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise RecordDeliveryError(f"git cat-file -t {sha} failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    object_type = result.stdout.decode().strip()
    if object_type != "blob":
        raise RecordDeliveryError(
            f"Conformance surface {path!r} resolves to a Git {object_type}, not a blob."
        )


def git_user_name(root: Path) -> str:
    result = subprocess.run(
        ["git", "config", "user.name"], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        return ""
    return result.stdout.decode("utf-8", "replace").strip()


def _task_gate_ids(task: dict[str, Any]) -> list[str]:
    gates = task.get("completion_gates")
    if not isinstance(gates, list) or not gates:
        raise RecordDeliveryError("Task contract completion_gates must be a non-empty list.")
    ids = [gate.get("gate_id") if isinstance(gate, dict) else None for gate in gates]
    if any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids):
        raise RecordDeliveryError("Task contract has invalid or duplicate completion gate IDs.")
    return ids  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Unity/human artifact validation.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UnityReport:
    result: str
    total: int
    passed: int
    failed: int
    skipped: int


def _xml_int_attribute(element: ElementTree.Element, name: str, source_label: str, *, default: int | None = None) -> int:
    raw = element.get(name)
    if raw is None:
        if default is not None:
            return default
        raise RecordDeliveryError(f"Unity test-results XML at {source_label} is missing the {name!r} attribute.")
    if not re.fullmatch(r"-?\d+", raw.strip()):
        raise RecordDeliveryError(f"Unity test-results XML at {source_label} has a non-integer {name!r} attribute: {raw!r}.")
    return int(raw.strip())


def validate_unity_test_results(data: bytes, source_label: str) -> UnityReport:
    try:
        root_element = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise RecordDeliveryError(f"Malformed Unity test-results XML at {source_label}: {exc}") from exc
    if root_element.tag != "test-run":
        raise RecordDeliveryError(
            f"Unity test-results XML at {source_label} must have a <test-run> root element, found <{root_element.tag}>."
        )
    result = root_element.get("result")
    if not isinstance(result, str) or not result:
        raise RecordDeliveryError(f"Unity test-results XML at {source_label} is missing the 'result' attribute.")
    total = _xml_int_attribute(root_element, "total", source_label)
    passed = _xml_int_attribute(root_element, "passed", source_label)
    failed = _xml_int_attribute(root_element, "failed", source_label)
    skipped = _xml_int_attribute(root_element, "skipped", source_label)
    inconclusive = _xml_int_attribute(root_element, "inconclusive", source_label, default=0)
    if total < 0 or passed < 0 or failed < 0 or skipped < 0 or inconclusive < 0:
        raise RecordDeliveryError(f"Unity test-results XML at {source_label} has a negative count attribute.")
    if total != passed + failed + skipped + inconclusive:
        raise RecordDeliveryError(
            f"Unity test-results XML at {source_label} counts are inconsistent: "
            f"total={total} != passed+failed+skipped+inconclusive={passed + failed + skipped + inconclusive}."
        )
    if result != "Passed":
        raise RecordDeliveryError(f"Unity test-results XML at {source_label} result is {result!r}, not 'Passed'.")
    if failed != 0:
        raise RecordDeliveryError(f"Unity test-results XML at {source_label} reports {failed} failed test(s).")
    return UnityReport(result=result, total=total, passed=passed, failed=failed, skipped=skipped)


def validate_human_validation_text(data: bytes, source_label: str) -> None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RecordDeliveryError(f"Human-validation artifact at {source_label} is not valid UTF-8: {exc}") from exc
    if not text.strip():
        raise RecordDeliveryError(f"Human-validation artifact at {source_label} must contain non-empty meaningful text.")


def validate_unity_log(data: bytes, source_label: str) -> None:
    if not data:
        raise RecordDeliveryError(f"Unity log artifact at {source_label} is empty.")


def determine_extension(artifact: ArtifactSpec) -> str:
    known = EXTENSION_BY_ARTIFACT_TYPE.get(artifact.type)
    if known is not None:
        return known
    suffix = Path(artifact.source_path).suffix
    if not suffix:
        raise RecordDeliveryError(
            f"Artifact {artifact.id!r} has type 'other' and source_path {artifact.source_path!r} has no "
            "file extension, so a destination extension cannot be derived."
        )
    return suffix.lower()


def _is_within(path: Path, ancestor: Path) -> bool:
    try:
        path.relative_to(ancestor)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------
# Result and reporting.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DeliveryResult:
    task_id: str
    validated_commit: str
    validated_tree: str
    base_commit: str
    candidate_commit: str
    record_id: str
    record_path: str
    created_paths: tuple[str, ...]
    unity_reports: tuple[tuple[str, UnityReport], ...]
    stage_command: tuple[str, ...]
    validate_command: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "validated_commit": self.validated_commit,
            "validated_tree": self.validated_tree,
            "base_commit": self.base_commit,
            "candidate_commit": self.candidate_commit,
            "record_id": self.record_id,
            "record_path": self.record_path,
            "created_paths": list(self.created_paths),
            "unity_results": [
                {"artifact_id": artifact_id, "result": report.result, "total": report.total,
                 "passed": report.passed, "failed": report.failed, "skipped": report.skipped}
                for artifact_id, report in self.unity_reports
            ],
            "stage_command": list(self.stage_command),
            "validate_command": list(self.validate_command),
            "committed": False,
            "conformant": False,
            "note": "TaskGraph determines conformance only after this evidence is committed.",
        }


# --------------------------------------------------------------------------
# Core packaging logic.
# --------------------------------------------------------------------------


def create_delivery_package(spec_path: Path, root: Path = ROOT) -> DeliveryResult:
    try:
        return _create_delivery_package(spec_path, root)
    except ConformanceRecordError as exc:
        raise RecordDeliveryError(str(exc)) from exc


def _create_delivery_package(spec_path: Path, root: Path) -> DeliveryResult:
    repo = GitRepository(root)
    try:
        head = repo.head()
    except ConformanceRecordError as exc:
        raise RecordDeliveryError(f"{root} is not a usable Git repository at a committed HEAD: {exc}") from exc
    if repo.dirty():
        raise RecordDeliveryError("Working tree must be completely clean before packaging delivery evidence.")

    spec = load_delivery_spec(spec_path)

    task_path = f"Tasks/{spec.task_id}.yaml"
    if not repo.exists(head, task_path):
        raise RecordDeliveryError(f"No committed task contract at HEAD: {task_path}")
    head_task = json.loads(repo.read(head, task_path).decode("utf-8-sig"))
    if not isinstance(head_task, dict):
        raise RecordDeliveryError(f"{task_path} at HEAD must contain a JSON object.")
    if head_task.get("schema_version") != "2.0":
        raise RecordDeliveryError(f"{task_path} at HEAD is not a schema-v2 task contract.")
    if head_task.get("id") != spec.task_id:
        raise RecordDeliveryError(f"{task_path} id {head_task.get('id')!r} does not match spec task_id {spec.task_id!r}.")

    validated_commit = resolve_commit(root, spec.validated_commit)
    if validated_commit != head:
        raise RecordDeliveryError(
            f"HEAD ({head}) does not equal validated_commit ({validated_commit}). "
            "This tool only packages the initial delivery workflow where HEAD is the validated commit."
        )
    validated_tree = repo.tree(validated_commit)

    base_commit = resolve_commit(root, spec.base_commit)
    if not repo.is_ancestor(base_commit, validated_commit):
        raise RecordDeliveryError(f"base_commit {base_commit} is not an ancestor of validated_commit {validated_commit}.")

    candidate_commit = resolve_commit(root, spec.candidate_commit)
    if not repo.is_ancestor(candidate_commit, validated_commit):
        raise RecordDeliveryError(
            f"candidate_commit {candidate_commit} is not an ancestor of, or equal to, validated_commit {validated_commit}."
        )

    if not repo.exists(validated_commit, task_path):
        raise RecordDeliveryError(f"No task contract at validated_commit {validated_commit}: {task_path}")
    task_contract_raw = repo.read(validated_commit, task_path)
    task_contract = json.loads(task_contract_raw.decode("utf-8-sig"))
    if not isinstance(task_contract, dict):
        raise RecordDeliveryError(f"{task_path} at {validated_commit} must contain a JSON object.")
    if task_contract.get("schema_version") != "2.0" or task_contract.get("id") != spec.task_id:
        raise RecordDeliveryError(f"{task_path} at {validated_commit} is not the expected schema-v2 {spec.task_id} contract.")
    contract_revision = task_contract.get("contract_revision")
    if not isinstance(contract_revision, int) or isinstance(contract_revision, bool) or contract_revision < 1:
        raise RecordDeliveryError(f"{task_path} at {validated_commit} has an invalid contract_revision.")

    if not repo.exists(validated_commit, CANON_PATH):
        raise RecordDeliveryError(f"No canon file at validated_commit {validated_commit}: {CANON_PATH}")
    canon_raw = repo.read(validated_commit, CANON_PATH)

    surface_records: list[dict[str, Any]] = []
    for surface in spec.surfaces:
        blob_sha = repo.blob(validated_commit, surface.path)
        require_committed_blob(root, blob_sha, surface.path)
        surface_records.append({"path": surface.path, "blob_sha": blob_sha, "role": surface.role})

    evidence_dir = (root / EVIDENCE_ROOT / spec.task_id).resolve()
    for artifact in spec.artifacts:
        source = Path(artifact.source_path)
        if not source.is_file():
            raise RecordDeliveryError(f"Artifact {artifact.id!r} source_path is not a regular file: {artifact.source_path}")
        if _is_within(source.resolve(), evidence_dir):
            raise RecordDeliveryError(
                f"Artifact {artifact.id!r} source_path refers to the destination evidence directory: {artifact.source_path}"
            )

    current_gate_order = _task_gate_ids(task_contract)
    spec_gate_ids = {gate.gate_id for gate in spec.gates}
    if spec_gate_ids != set(current_gate_order):
        raise RecordDeliveryError(
            "Delivery-spec gate IDs do not exactly equal the task contract's current completion-gate set "
            f"(spec={sorted(spec_gate_ids)}, contract={sorted(current_gate_order)})."
        )

    approval = spec.human_approval
    if approval.required:
        if approval.decision != "approved":
            raise RecordDeliveryError(
                "This tool packages successful delivery only; human_approval.required is true but "
                f"decision is {approval.decision!r}, not 'approved'."
            )
        approved_by = approval.approved_by.strip() or git_user_name(root)
        if not approved_by:
            raise RecordDeliveryError(
                "human_approval.approved_by is blank and no repository git user.name is configured."
            )
    else:
        if approval.decision != "not_required":
            raise RecordDeliveryError("human_approval.decision must be 'not_required' when required is false.")
        if approval.approved_by.strip():
            raise RecordDeliveryError("human_approval.approved_by must be blank when human_approval.required is false.")
        approved_by = ""

    short_sha = validated_commit[:12]
    artifacts_dir_repo = f"{EVIDENCE_ROOT}/{spec.task_id}/artifacts"
    records_dir_repo = f"{EVIDENCE_ROOT}/{spec.task_id}/records"

    with tempfile.TemporaryDirectory(prefix="taskgraph-delivery-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        staged: dict[str, dict[str, Any]] = {}
        seen_dest_paths: set[str] = set()
        unity_reports: list[tuple[str, UnityReport]] = []

        for artifact in spec.artifacts:
            data = Path(artifact.source_path).read_bytes()
            extension = determine_extension(artifact)
            dest_name = f"{artifact.name}-{short_sha}{extension}"
            dest_repo_path = f"{artifacts_dir_repo}/{dest_name}"
            if dest_repo_path in seen_dest_paths:
                raise RecordDeliveryError(f"Two artifacts resolve to the same destination path: {dest_repo_path}")
            seen_dest_paths.add(dest_repo_path)

            if artifact.type == "unity_test_results":
                report = validate_unity_test_results(data, artifact.source_path)
                unity_reports.append((artifact.id, report))
            elif artifact.type == "unity_log":
                validate_unity_log(data, artifact.source_path)
            elif artifact.type == "human_validation":
                validate_human_validation_text(data, artifact.source_path)
            # "other" artifacts are copied byte-for-byte with no semantic validation.

            temp_path = temp_dir / dest_name
            temp_path.write_bytes(data)
            blob_sha = hash_object_as_committed(root, dest_repo_path, data)
            staged[artifact.id] = {
                "dest_repo_path": dest_repo_path,
                "temp_path": temp_path,
                "blob_sha": blob_sha,
            }

        gate_by_id = {gate.gate_id: gate for gate in spec.gates}
        gate_results: list[dict[str, Any]] = []
        for gate_id in current_gate_order:
            gate = gate_by_id[gate_id]
            evidence = [
                {"path": staged[evidence_id]["dest_repo_path"], "blob_sha": staged[evidence_id]["blob_sha"]}
                for evidence_id in gate.evidence
            ]
            gate_results.append({"gate_id": gate_id, "result": "pass", "evidence": evidence, "notes": gate.notes})

        record_id = f"DEL-{spec.task_id}-{short_sha}"
        record_path_repo = f"{records_dir_repo}/{record_id}.json"
        record = {
            "schema_version": SCHEMA_VERSION,
            "record_type": "delivery",
            "record_id": record_id,
            "task_id": spec.task_id,
            "task_contract": {
                "path": task_path,
                "revision": contract_revision,
                "sha256": semantic_json_sha256(task_contract_raw),
            },
            "canon": {"path": CANON_PATH, "sha256": canonical_text_sha256(canon_raw)},
            "validated_state": {"commit": validated_commit, "tree": validated_tree},
            "conformance_surfaces": surface_records,
            "gate_results": gate_results,
            "human_approval": {
                "required": approval.required,
                "decision": approval.decision,
                "approved_by": approved_by,
                "notes": approval.notes,
            },
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "delivery": {
                "base_commit": base_commit,
                "candidate_commit": candidate_commit,
                "integrated_commit": validated_commit,
                "integrated_tree": validated_tree,
            },
        }

        validate_record_shape(record, record_path_repo)

        # Re-verify every generated hash against the exact bytes about to be published,
        # using the same path-aware filtered hashing rule that git add -f will apply.
        for entry in staged.values():
            if hash_object_as_committed(root, entry["dest_repo_path"], entry["temp_path"].read_bytes()) != entry["blob_sha"]:
                raise RecordDeliveryError("Internal error: staged artifact hash does not match its own bytes.")
        for surface in record["conformance_surfaces"]:
            if repo.blob(validated_commit, surface["path"]) != surface["blob_sha"]:
                raise RecordDeliveryError(f"Surface {surface['path']} no longer matches validated_commit; aborting.")
            require_committed_blob(root, surface["blob_sha"], surface["path"])

        final_artifact_paths = [(root / entry["dest_repo_path"], entry) for entry in staged.values()]
        final_record_path = root / record_path_repo
        for final_path, _ in final_artifact_paths:
            if final_path.exists():
                raise RecordDeliveryError(f"Refusing to overwrite existing evidence artifact: {final_path}")
        if final_record_path.exists():
            raise RecordDeliveryError(f"Refusing to overwrite existing delivery record: {final_record_path}")

        published: list[str] = []
        try:
            (root / artifacts_dir_repo).mkdir(parents=True, exist_ok=True)
            for final_path, entry in final_artifact_paths:
                shutil.copyfile(entry["temp_path"], final_path)
                published.append(str(final_path.relative_to(root)).replace("\\", "/"))
            (root / records_dir_repo).mkdir(parents=True, exist_ok=True)
            final_record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            published.append(str(final_record_path.relative_to(root)).replace("\\", "/"))
        except Exception as exc:  # noqa: BLE001 - report exactly what was published, then stop.
            raise PublicationFailure(published, exc) from exc

    stage_command = ("git", "add", "-f", "--", *published)
    validate_command = (
        "python", "Pipeline/TaskGraph/validate_draft_evidence.py", "--record", record_path_repo,
    )
    return DeliveryResult(
        task_id=spec.task_id,
        validated_commit=validated_commit,
        validated_tree=validated_tree,
        base_commit=base_commit,
        candidate_commit=candidate_commit,
        record_id=record_id,
        record_path=record_path_repo,
        created_paths=tuple(published),
        unity_reports=tuple(unity_reports),
        stage_command=stage_command,
        validate_command=validate_command,
    )


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------


def _quote_command(command: tuple[str, ...]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def print_human_report(result: DeliveryResult) -> None:
    print("DELIVERY EVIDENCE: READY")
    print()
    print(f"Task: {result.task_id}")
    print(f"Validated commit: {result.validated_commit}")
    print(f"Validated tree: {result.validated_tree}")
    print(f"Record: {result.record_path}")
    print()
    print("Unity results:")
    if result.unity_reports:
        for artifact_id, report in result.unity_reports:
            print(
                f"  [{artifact_id}] {report.result} "
                f"(total={report.total} passed={report.passed} failed={report.failed} skipped={report.skipped})"
            )
    else:
        print("  (no unity_test_results artifacts supplied)")
    print()
    print("CREATED:")
    for path in result.created_paths:
        print(f"- {path}")
    print()
    print("STAGE:")
    print(_quote_command(result.stage_command))
    print()
    print("VALIDATE DRAFT:")
    print(_quote_command(result.validate_command))
    print()
    print("CHECK:")
    print("git diff --cached --check")
    print("git diff --cached --stat")
    print()
    print("COMMIT:")
    print(f'git commit -m "Record {result.task_id} delivery evidence"')
    print()
    print("VERIFY AFTER COMMIT:")
    print(f"python Pipeline/TaskGraph/taskcontrol.py state {result.task_id} --json")
    print()
    print("This package has NOT been staged or committed. TaskGraph determines conformance")
    print("only after this evidence is committed; this tool never claims the task conformant.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic delivery-evidence packager for TaskGraph.")
    parser.add_argument("spec", help="Path to the delivery-spec JSON file.")
    parser.add_argument("--root", default=None, help="Repository root (defaults to this checkout's root).")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON summary instead of the human report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else ROOT
    try:
        result = create_delivery_package(Path(args.spec), root)
    except PublicationFailure as exc:
        print("DELIVERY EVIDENCE: PARTIAL PUBLICATION - DO NOT TRUST OR STAGE", file=sys.stderr)
        print("The following paths were written before the failure and were left in place for inspection:", file=sys.stderr)
        for path in exc.published:
            print(f"  - {path}", file=sys.stderr)
        print(f"Failure: {exc.cause}", file=sys.stderr)
        return 1
    except RecordDeliveryError as exc:
        print(f"record_delivery: FAIL\n{exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print_human_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
