from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_APPROVAL_PATH = ROOT / "Pipeline" / "TaskGraph" / "APPROVED_BOOTSTRAP.json"

APPROVAL_SCHEMA_VERSION = "1.0"
APPROVAL_STATUS = "approved"
APPROVAL_SCOPE = "initial_persistent_work_graph_bootstrap"
ALLOWED_VERIFICATION_STATUSES = {"verified", "verified_with_findings"}


class BootstrapInputError(RuntimeError):
    """Raised when an approved bootstrap input cannot be trusted."""


@dataclass(frozen=True)
class ApprovedBootstrapInputs:
    source_reconciliation_run_id: str
    verification_run_id: str
    verification_status: str
    approved_by: str
    approval_path: Path
    candidate_path: Path
    delta_path: Path
    verification_summary_path: Path
    candidate: dict[str, Any]
    delta: dict[str, Any]
    verification_summary: dict[str, Any]

    @property
    def seed_records(self) -> list[dict[str, Any]]:
        records = self.delta["proposed_seed_records"]
        return records

    @property
    def exclusive_resource_groups(self) -> list[dict[str, Any]]:
        groups = self.delta.get("exclusive_resource_groups", [])
        return groups if isinstance(groups, list) else []

    @property
    def proposed_non_code_records(self) -> list[dict[str, Any]]:
        records = self.delta.get("proposed_non_code_records", [])
        return records if isinstance(records, list) else []


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BootstrapInputError(f"Required file does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapInputError(f"Unable to read JSON object from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BootstrapInputError(f"Expected a JSON object in {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BootstrapInputError(f"Approval manifest field {field!r} must be a non-empty string.")
    return value.strip()


def require_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise BootstrapInputError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def resolve_repo_file(root: Path, relative_path: str, label: str) -> Path:
    normalized = relative_path.strip().replace("\\", "/")
    if not normalized:
        raise BootstrapInputError(f"{label} path is blank.")

    root_resolved = root.resolve()
    candidate = (root_resolved / normalized).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise BootstrapInputError(f"{label} path escapes repository root: {relative_path!r}") from exc

    if not candidate.is_file():
        raise BootstrapInputError(f"{label} file does not exist: {normalized}")
    return candidate


def require_immutable_verification_path(
    relative_path: str,
    source_run_id: str,
    verification_run_id: str,
    label: str,
) -> None:
    normalized = relative_path.strip().replace("\\", "/")
    prefix = (
        f"Pipeline/Reconciliation/outputs/runs/{source_run_id}/"
        f"verifications/{verification_run_id}/"
    )
    if not normalized.startswith(prefix):
        raise BootstrapInputError(
            f"{label} must come from immutable verification history {prefix!r}; got {normalized!r}."
        )
    if "/outputs/current/" in f"/{normalized}":
        raise BootstrapInputError(f"{label} may not use mutable outputs/current/: {normalized}")


def verify_bound_hash(path: Path, expected_hash: str, label: str) -> None:
    expected = expected_hash.strip().lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise BootstrapInputError(f"Approval manifest contains an invalid SHA-256 for {label}: {expected_hash!r}")
    actual = sha256_file(path)
    if actual != expected:
        raise BootstrapInputError(
            f"{label} SHA-256 mismatch: approval binds {expected}, current file is {actual}."
        )


def validate_candidate(candidate: dict[str, Any], source_run_id: str) -> None:
    work_items = candidate.get("work_items")
    if not isinstance(work_items, list) or not work_items:
        raise BootstrapInputError("Approved candidate contains no work_items.")

    seen_keys: set[str] = set()
    for index, item in enumerate(work_items):
        if not isinstance(item, dict):
            raise BootstrapInputError(f"Candidate work_items[{index}] is not an object.")
        key = item.get("key")
        if not isinstance(key, str) or not key.strip():
            raise BootstrapInputError(f"Candidate work_items[{index}] has no non-empty key.")
        if key in seen_keys:
            raise BootstrapInputError(f"Approved candidate contains duplicate work key: {key}")
        seen_keys.add(key)

    candidate_source_run = candidate.get("run_id") or candidate.get("reconciliation_run_id")
    if candidate_source_run is not None:
        require_equal("candidate reconciliation run", candidate_source_run, source_run_id)


def validate_delta(
    delta: dict[str, Any],
    source_run_id: str,
    verification_run_id: str,
) -> None:
    require_equal("graph delta reconciliation run", delta.get("reconciliation_run_id"), source_run_id)
    if "source_reconciliation_run_id" in delta:
        require_equal(
            "graph delta source reconciliation run",
            delta.get("source_reconciliation_run_id"),
            source_run_id,
        )
    if "verification_run_id" in delta:
        require_equal("graph delta verification run", delta.get("verification_run_id"), verification_run_id)
    require_equal("graph delta status", delta.get("status"), "bootstrap_seed_proposal")

    if delta.get("persistent_graph_present") is not False:
        raise BootstrapInputError("Approved graph delta does not prove persistent_graph_present=false.")
    if delta.get("persistent_graph_mutated") is not False:
        raise BootstrapInputError("Approved graph delta does not prove persistent_graph_mutated=false.")

    records = delta.get("proposed_seed_records")
    if not isinstance(records, list) or not records:
        raise BootstrapInputError("Approved graph delta contains no proposed_seed_records.")

    seen_keys: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise BootstrapInputError(f"proposed_seed_records[{index}] is not an object.")
        key = record.get("reconciliation_key")
        if not isinstance(key, str) or not key.strip():
            raise BootstrapInputError(
                f"proposed_seed_records[{index}] has no non-empty reconciliation_key."
            )
        if key in seen_keys:
            raise BootstrapInputError(f"Approved graph delta contains duplicate seed key: {key}")
        seen_keys.add(key)


def validate_verification_summary(
    summary: dict[str, Any],
    source_run_id: str,
    verification_run_id: str,
    verification_status: str,
    candidate_relative_path: str,
) -> None:
    require_equal("verification summary source run", summary.get("source_run_id"), source_run_id)
    require_equal("verification summary run", summary.get("verification_run_id"), verification_run_id)
    require_equal("verification summary status", summary.get("status"), verification_status)
    require_equal("verification final candidate", summary.get("final_candidate"), candidate_relative_path)

    if summary.get("persistent_graph_mutated") is not False:
        raise BootstrapInputError("Verification summary does not prove persistent_graph_mutated=false.")
    if summary.get("human_approval_required") is not True:
        raise BootstrapInputError("Verification summary no longer records human_approval_required=true.")

    final_pass = summary.get("final_pass")
    if not isinstance(final_pass, dict):
        raise BootstrapInputError("Verification summary is missing final_pass.")
    require_equal("final material finding count", final_pass.get("material_finding_count"), 0)


def load_approved_bootstrap_inputs(
    approval_path: Path = DEFAULT_APPROVAL_PATH,
    root: Path = ROOT,
) -> ApprovedBootstrapInputs:
    """Load and re-verify the exact immutable artifacts authorized for bootstrap seeding.

    This intentionally does not read Pipeline/Reconciliation/outputs/current/. The approval
    manifest is the authority after human approval, and every consumed artifact is re-hashed
    before it is returned to the seeder.
    """

    approval = load_json(approval_path)

    require_equal("approval schema", approval.get("schema_version"), APPROVAL_SCHEMA_VERSION)
    require_equal("approval status", approval.get("approval_status"), APPROVAL_STATUS)
    require_equal("approval scope", approval.get("approval_scope"), APPROVAL_SCOPE)

    source_run_id = require_text(approval, "source_reconciliation_run_id")
    verification_run_id = require_text(approval, "verification_run_id")
    verification_status = require_text(approval, "verification_status")
    approved_by = require_text(approval, "approved_by")

    if verification_status not in ALLOWED_VERIFICATION_STATUSES:
        raise BootstrapInputError(
            f"Approval binds unsupported verification status: {verification_status!r}"
        )
    require_equal("approved final material finding count", approval.get("final_material_findings"), 0)

    candidate_rel = require_text(approval, "candidate_path").replace("\\", "/")
    delta_rel = require_text(approval, "delta_path").replace("\\", "/")
    summary_rel = require_text(approval, "verification_summary_path").replace("\\", "/")

    for relative_path, label in (
        (candidate_rel, "candidate"),
        (delta_rel, "graph delta"),
        (summary_rel, "verification summary"),
    ):
        require_immutable_verification_path(
            relative_path,
            source_run_id,
            verification_run_id,
            label,
        )

    candidate_path = resolve_repo_file(root, candidate_rel, "candidate")
    delta_path = resolve_repo_file(root, delta_rel, "graph delta")
    summary_path = resolve_repo_file(root, summary_rel, "verification summary")

    verify_bound_hash(candidate_path, require_text(approval, "candidate_sha256"), "candidate")
    verify_bound_hash(delta_path, require_text(approval, "delta_sha256"), "graph delta")
    verify_bound_hash(
        summary_path,
        require_text(approval, "verification_summary_sha256"),
        "verification summary",
    )

    candidate = load_json(candidate_path)
    delta = load_json(delta_path)
    summary = load_json(summary_path)

    validate_candidate(candidate, source_run_id)
    validate_delta(delta, source_run_id, verification_run_id)
    validate_verification_summary(
        summary,
        source_run_id,
        verification_run_id,
        verification_status,
        candidate_rel,
    )

    candidate_keys = {
        item["key"]
        for item in candidate["work_items"]
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    seed_keys = {record["reconciliation_key"] for record in delta["proposed_seed_records"]}
    unknown_seed_keys = sorted(seed_keys - candidate_keys)
    if unknown_seed_keys:
        raise BootstrapInputError(
            "Approved graph delta proposes seed records not present in the approved candidate: "
            + ", ".join(unknown_seed_keys)
        )

    return ApprovedBootstrapInputs(
        source_reconciliation_run_id=source_run_id,
        verification_run_id=verification_run_id,
        verification_status=verification_status,
        approved_by=approved_by,
        approval_path=approval_path,
        candidate_path=candidate_path,
        delta_path=delta_path,
        verification_summary_path=summary_path,
        candidate=candidate,
        delta=delta,
        verification_summary=summary,
    )


def main() -> int:
    inputs = load_approved_bootstrap_inputs()
    print("Approved bootstrap input loader: PASS")
    print(f"Approved by:          {inputs.approved_by}")
    print(f"Reconciliation run:   {inputs.source_reconciliation_run_id}")
    print(f"Verification run:     {inputs.verification_run_id}")
    print(f"Verification status:  {inputs.verification_status}")
    print(f"Seed records:         {len(inputs.seed_records)}")
    print(f"Resource groups:      {len(inputs.exclusive_resource_groups)}")
    print(f"Non-code records:     {len(inputs.proposed_non_code_records)}")
    print("All approved artifact hashes and bootstrap invariants match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
