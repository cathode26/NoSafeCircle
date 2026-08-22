from __future__ import annotations

"""Schema and Git-object helpers for immutable conformance records."""

import hashlib
import json
import posixpath
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
CANON_PATH = "Docs/GDD/No_Safe_Circle_GDD.md"
EVIDENCE_ROOT = "Pipeline/TaskGraph/evidence"
TASK_ID_RE = re.compile(r"NSC-\d{3,}")
HEX_RE = re.compile(r"[0-9a-f]{40}")
FORBIDDEN_AUTHORITY_FIELDS = {"status", "complete", "current", "ready", "authorized"}


class ConformanceRecordError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommittedRecord:
    path: str
    data: dict[str, Any]

    @property
    def record_id(self) -> str:
        return self.data["record_id"]

    @property
    def validated_commit(self) -> str:
        return self.data["validated_state"]["commit"]


class GitRepository:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()

    def _run(self, *args: str, check: bool = True) -> bytes:
        result = subprocess.run(
            ["git", *args], cwd=self.root, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        )
        if check and result.returncode:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise ConformanceRecordError(f"git {' '.join(args)} failed: {detail}")
        return result.stdout

    def head(self) -> str:
        return self._run("rev-parse", "HEAD").decode().strip()

    def tree(self, commit: str) -> str:
        return self._run("rev-parse", f"{commit}^{{tree}}").decode().strip()

    def read(self, commit: str, path: str) -> bytes:
        safe_repository_path(path, "Git object path")
        return self._run("show", f"{commit}:{path}")

    def blob(self, commit: str, path: str) -> str:
        safe_repository_path(path, "Git blob path")
        value = self._run("rev-parse", f"{commit}:{path}").decode().strip()
        if not HEX_RE.fullmatch(value):
            raise ConformanceRecordError(f"{path!r} is not a committed blob at {commit}.")
        return value

    def exists(self, commit: str, path: str) -> bool:
        safe_repository_path(path, "Git object path")
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}:{path}"], cwd=self.root,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        return result.returncode == 0

    def files(self, commit: str, prefix: str) -> list[str]:
        safe_repository_path(prefix, "Git tree prefix")
        output = self._run("ls-tree", "-r", "--name-only", commit, "--", prefix)
        return [line for line in output.decode("utf-8").splitlines() if line]

    def is_ancestor(self, older: str, newer: str) -> bool:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer], cwd=self.root,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        return result.returncode == 0

    def dirty(self) -> bool:
        return bool(self._run("status", "--porcelain"))

    def path_history(self, commit: str, path: str) -> list[str]:
        safe_repository_path(path, "Git history path")
        output = self._run("log", "--format=%H", commit, "--", path)
        return [line for line in output.decode("utf-8").splitlines() if line]


def safe_repository_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConformanceRecordError(f"{label} must be a non-empty repository path.")
    if any(ord(character) < 32 for character in value):
        raise ConformanceRecordError(f"{label} contains a control character.")
    if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value):
        raise ConformanceRecordError(f"{label} must be relative: {value!r}.")
    if "\\" in value or posixpath.normpath(value) != value or value in {".", ".."}:
        raise ConformanceRecordError(f"{label} is not a canonical repository path: {value!r}.")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ConformanceRecordError(f"{label} contains path traversal: {value!r}.")
    return value


def semantic_json_sha256(raw: bytes | str | Any) -> str:
    if isinstance(raw, bytes):
        value = json.loads(raw.decode("utf-8-sig"))
    elif isinstance(raw, str):
        value = json.loads(raw.lstrip("\ufeff"))
    else:
        value = raw
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_text_sha256(raw: bytes | str) -> str:
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _object(value: Any, label: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConformanceRecordError(f"{label} must be an object.")
    extra = set(value) - fields
    missing = fields - set(value)
    if extra or missing:
        raise ConformanceRecordError(
            f"{label} fields differ from schema (missing={sorted(missing)}, extra={sorted(extra)})."
        )
    return value


def _text(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ConformanceRecordError(f"{label} must be a {'string' if allow_empty else 'non-empty string'}.")
    return value


def _sha(value: Any, label: str) -> str:
    value = _text(value, label)
    if not HEX_RE.fullmatch(value):
        raise ConformanceRecordError(f"{label} must be a lowercase 40-character Git SHA.")
    return value


def validate_record_shape(record: Any, path: str) -> dict[str, Any]:
    common = {
        "schema_version", "record_type", "record_id", "task_id", "task_contract",
        "canon", "validated_state", "conformance_surfaces", "gate_results",
        "human_approval", "recorded_at",
    }
    if not isinstance(record, dict):
        raise ConformanceRecordError(f"{path}: record must be an object.")
    forbidden = FORBIDDEN_AUTHORITY_FIELDS.intersection(record)
    if forbidden:
        raise ConformanceRecordError(f"{path}: mutable authority fields are forbidden: {sorted(forbidden)}.")
    record_type = record.get("record_type")
    specific = (
        "delivery" if record_type == "delivery"
        else "baseline" if record_type == "baseline"
        else "revalidation" if record_type == "revalidation"
        else None
    )
    if specific is None:
        raise ConformanceRecordError(f"{path}: record_type must be delivery, baseline, or revalidation.")
    _object(record, path, common | {specific})
    if record["schema_version"] != SCHEMA_VERSION:
        raise ConformanceRecordError(f"{path}: unsupported schema_version {record['schema_version']!r}.")

    task_id = _text(record["task_id"], f"{path}.task_id")
    if not TASK_ID_RE.fullmatch(task_id):
        raise ConformanceRecordError(f"{path}: invalid task_id {task_id!r}.")
    record_id = _text(record["record_id"], f"{path}.record_id")
    prefix = {"delivery": "DEL-", "baseline": "BASE-", "revalidation": "REV-"}[record_type]
    if not record_id.startswith(f"{prefix}{task_id}-"):
        raise ConformanceRecordError(f"{path}: record_id prefix/task identity mismatch.")
    expected_prefix = f"{EVIDENCE_ROOT}/{task_id}/records/"
    if not path.startswith(expected_prefix) or path != f"{expected_prefix}{record_id}.json":
        raise ConformanceRecordError(f"{path}: record path, task_id, filename, and record_id disagree.")

    contract = _object(record["task_contract"], f"{path}.task_contract", {"path", "revision", "sha256"})
    safe_repository_path(contract["path"], f"{path}.task_contract.path")
    if isinstance(contract["revision"], bool) or not isinstance(contract["revision"], int) or contract["revision"] < 1:
        raise ConformanceRecordError(f"{path}.task_contract.revision must be a positive integer.")
    if not re.fullmatch(r"[0-9a-f]{64}", _text(contract["sha256"], f"{path}.task_contract.sha256")):
        raise ConformanceRecordError(f"{path}.task_contract.sha256 must be lowercase SHA-256.")
    canon = _object(record["canon"], f"{path}.canon", {"path", "sha256"})
    safe_repository_path(canon["path"], f"{path}.canon.path")
    if not re.fullmatch(r"[0-9a-f]{64}", _text(canon["sha256"], f"{path}.canon.sha256")):
        raise ConformanceRecordError(f"{path}.canon.sha256 must be lowercase SHA-256.")
    state = _object(record["validated_state"], f"{path}.validated_state", {"commit", "tree"})
    _sha(state["commit"], f"{path}.validated_state.commit")
    _sha(state["tree"], f"{path}.validated_state.tree")

    surfaces = record["conformance_surfaces"]
    if not isinstance(surfaces, list):
        raise ConformanceRecordError(f"{path}.conformance_surfaces must be a list.")
    surface_paths: set[str] = set()
    for index, raw in enumerate(surfaces):
        surface = _object(raw, f"{path}.conformance_surfaces[{index}]", {"path", "blob_sha", "role"})
        item_path = safe_repository_path(surface["path"], f"{path}.conformance_surfaces[{index}].path")
        if item_path in surface_paths:
            raise ConformanceRecordError(f"{path}: duplicate conformance surface path {item_path!r}.")
        surface_paths.add(item_path)
        _sha(surface["blob_sha"], f"{path}.conformance_surfaces[{index}].blob_sha")
        _text(surface["role"], f"{path}.conformance_surfaces[{index}].role")

    gates = record["gate_results"]
    if not isinstance(gates, list):
        raise ConformanceRecordError(f"{path}.gate_results must be a list.")
    gate_ids: set[str] = set()
    for index, raw in enumerate(gates):
        gate = _object(raw, f"{path}.gate_results[{index}]", {"gate_id", "result", "evidence", "notes"})
        gate_id = _text(gate["gate_id"], f"{path}.gate_results[{index}].gate_id")
        if gate_id in gate_ids:
            raise ConformanceRecordError(f"{path}: duplicate gate_id {gate_id!r}.")
        gate_ids.add(gate_id)
        if gate["result"] != "pass":
            raise ConformanceRecordError(f"{path}: only a pass gate result can establish conformance.")
        if not isinstance(gate["evidence"], list):
            raise ConformanceRecordError(f"{path}.gate_results[{index}].evidence must be a list.")
        for evidence_index, raw_evidence in enumerate(gate["evidence"]):
            evidence = _object(raw_evidence, f"{path}.gate_results[{index}].evidence[{evidence_index}]", {"path", "blob_sha"})
            safe_repository_path(evidence["path"], f"{path}.gate_results[{index}].evidence[{evidence_index}].path")
            _sha(evidence["blob_sha"], f"{path}.gate_results[{index}].evidence[{evidence_index}].blob_sha")
        _text(gate["notes"], f"{path}.gate_results[{index}].notes", allow_empty=True)

    approval = _object(record["human_approval"], f"{path}.human_approval", {"required", "decision", "approved_by", "notes"})
    if not isinstance(approval["required"], bool):
        raise ConformanceRecordError(f"{path}.human_approval.required must be boolean.")
    if approval["decision"] not in {"approved", "not_required"}:
        raise ConformanceRecordError(f"{path}.human_approval.decision is unsupported.")
    _text(approval["approved_by"], f"{path}.human_approval.approved_by", allow_empty=True)
    _text(approval["notes"], f"{path}.human_approval.notes", allow_empty=True)
    _text(record["recorded_at"], f"{path}.recorded_at")

    if record_type == "delivery":
        delivery = _object(record["delivery"], f"{path}.delivery", {"base_commit", "candidate_commit", "integrated_commit", "integrated_tree"})
        for field in delivery:
            _sha(delivery[field], f"{path}.delivery.{field}")
        if state["commit"] != delivery["integrated_commit"] or state["tree"] != delivery["integrated_tree"]:
            raise ConformanceRecordError(f"{path}: delivery integrated and validated states must match.")
    elif record_type == "baseline":
        baseline = _object(record["baseline"], f"{path}.baseline", {"reason_type", "summary"})
        if baseline["reason_type"] != "pre_evidence_existing_implementation":
            raise ConformanceRecordError(f"{path}.baseline.reason_type is unsupported.")
        _text(baseline["summary"], f"{path}.baseline.summary")
    else:
        revalidation = _object(record["revalidation"], f"{path}.revalidation", {"basis_record_id", "reason_type", "summary"})
        _text(revalidation["basis_record_id"], f"{path}.revalidation.basis_record_id")
        if revalidation["reason_type"] not in {"code_change", "gdd_change", "contract_change", "periodic", "manual"}:
            raise ConformanceRecordError(f"{path}.revalidation.reason_type is unsupported.")
        _text(revalidation["summary"], f"{path}.revalidation.summary")
    return record


def load_committed_records(repo: GitRepository, head: str, task_id: str) -> list[CommittedRecord]:
    prefix = f"{EVIDENCE_ROOT}/{task_id}/records"
    records: list[CommittedRecord] = []
    ids: set[str] = set()
    for path in repo.files(head, prefix):
        if not path.endswith(".json"):
            raise ConformanceRecordError(f"Unsupported committed record file: {path}.")
        if len(repo.path_history(head, path)) != 1:
            raise ConformanceRecordError(
                f"Immutable record {path} was modified, deleted/recreated, or has ambiguous history."
            )
        try:
            value = json.loads(repo.read(head, path).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConformanceRecordError(f"Unable to parse committed record {path}: {exc}") from exc
        validate_record_shape(value, path)
        if value["record_id"] in ids:
            raise ConformanceRecordError(f"Duplicate record_id {value['record_id']!r}.")
        ids.add(value["record_id"])
        records.append(CommittedRecord(path, value))
    return records
