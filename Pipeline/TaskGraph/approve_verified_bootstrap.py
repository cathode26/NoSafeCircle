from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CURRENT_PATH = ROOT / "Pipeline" / "Reconciliation" / "outputs" / "current" / "CURRENT.json"
APPROVAL_PATH = ROOT / "Pipeline" / "TaskGraph" / "APPROVED_BOOTSTRAP.json"

ALLOWED_VERIFICATION_STATUSES = {"verified", "verified_with_findings"}


class ApprovalGateError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedBootstrapState:
    source_reconciliation_run_id: str
    verification_run_id: str
    verification_status: str
    final_material_findings: int
    candidate_path: str
    candidate_sha256: str
    delta_path: str
    delta_sha256: str
    verification_summary_path: str
    verification_summary_sha256: str


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ApprovalGateError(f"Expected a JSON object in {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_path(relative_path: str) -> Path:
    raw = str(relative_path).strip().replace("\\", "/")
    if not raw:
        raise ApprovalGateError("Expected a non-empty repository-relative path.")
    candidate = (ROOT / raw).resolve()
    root = ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ApprovalGateError(f"Path escapes repository root: {relative_path!r}") from exc
    return candidate


def require_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise ApprovalGateError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def inspect_verified_state(root: Path = ROOT) -> VerifiedBootstrapState:
    current_path = root / "Pipeline" / "Reconciliation" / "outputs" / "current" / "CURRENT.json"
    current = load_json(current_path)

    status = str(current.get("status", "")).strip()
    if status not in ALLOWED_VERIFICATION_STATUSES:
        raise ApprovalGateError(
            f"Current reconciliation is not in an approvable verification state: {status!r}"
        )
    if current.get("persistent_graph_mutated") is not False:
        raise ApprovalGateError("Verification current-state record does not prove persistent_graph_mutated=false.")

    source_run_id = str(current.get("source_reconciliation_run_id", "")).strip()
    verification_run_id = str(current.get("verification_run_id", "")).strip()
    if not source_run_id or not verification_run_id:
        raise ApprovalGateError("CURRENT.json is missing reconciliation or verification run identity.")

    def resolve_from_root(relative_path: str) -> Path:
        raw = str(relative_path).strip().replace("\\", "/")
        if not raw:
            raise ApprovalGateError("CURRENT.json contains a blank artifact path.")
        candidate = (root / raw).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError as exc:
            raise ApprovalGateError(f"Artifact path escapes repository root: {relative_path!r}") from exc
        if not candidate.is_file():
            raise ApprovalGateError(f"Required verified artifact does not exist: {relative_path}")
        return candidate

    candidate_rel = str(current.get("candidate_source", "")).strip().replace("\\", "/")
    delta_rel = str(current.get("delta_source", "")).strip().replace("\\", "/")
    summary_rel = str(current.get("verification_summary_source", "")).strip().replace("\\", "/")

    candidate_path = resolve_from_root(candidate_rel)
    delta_path = resolve_from_root(delta_rel)
    summary_path = resolve_from_root(summary_rel)

    # Approval must bind immutable run history, never the mutable outputs/current copies.
    immutable_prefix = f"Pipeline/Reconciliation/outputs/runs/{source_run_id}/"
    for label, relative_path in (
        ("candidate", candidate_rel),
        ("delta", delta_rel),
        ("verification summary", summary_rel),
    ):
        if not relative_path.startswith(immutable_prefix):
            raise ApprovalGateError(
                f"{label} is not bound to immutable run history for {source_run_id}: {relative_path}"
            )

    summary = load_json(summary_path)
    require_equal("verification summary source run", summary.get("source_run_id"), source_run_id)
    require_equal("verification summary run", summary.get("verification_run_id"), verification_run_id)
    require_equal("verification summary status", summary.get("status"), status)
    require_equal("verification final candidate", summary.get("final_candidate"), candidate_rel)
    if summary.get("persistent_graph_mutated") is not False:
        raise ApprovalGateError("Verification summary does not prove persistent_graph_mutated=false.")
    if summary.get("human_approval_required") is not True:
        raise ApprovalGateError("Verification summary does not require human approval; refusing bootstrap approval.")

    final_pass = summary.get("final_pass")
    if not isinstance(final_pass, dict):
        raise ApprovalGateError("Verification summary is missing final_pass.")
    final_material = final_pass.get("material_finding_count")
    if not isinstance(final_material, int):
        raise ApprovalGateError("Verification summary final_pass.material_finding_count is not an integer.")
    if final_material != 0:
        raise ApprovalGateError(
            f"Verified bootstrap candidate still has {final_material} material finding(s); refusing approval."
        )

    delta = load_json(delta_path)
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
        raise ApprovalGateError("Bootstrap delta says a persistent graph is already present.")
    if delta.get("persistent_graph_mutated") is not False:
        raise ApprovalGateError("Bootstrap delta says the persistent graph was mutated.")
    records = delta.get("proposed_seed_records")
    if not isinstance(records, list) or not records:
        raise ApprovalGateError("Bootstrap delta contains no proposed_seed_records.")

    return VerifiedBootstrapState(
        source_reconciliation_run_id=source_run_id,
        verification_run_id=verification_run_id,
        verification_status=status,
        final_material_findings=final_material,
        candidate_path=candidate_rel,
        candidate_sha256=sha256_file(candidate_path),
        delta_path=delta_rel,
        delta_sha256=sha256_file(delta_path),
        verification_summary_path=summary_rel,
        verification_summary_sha256=sha256_file(summary_path),
    )


def write_approval_manifest(state: VerifiedBootstrapState, approved_by: str) -> None:
    name = approved_by.strip()
    if not name:
        raise ApprovalGateError("--approved-by must identify the human approving the verified bootstrap.")
    if APPROVAL_PATH.exists():
        raise ApprovalGateError(
            f"Approval manifest already exists at {APPROVAL_PATH.relative_to(ROOT)}; refusing to overwrite it."
        )

    payload = {
        "schema_version": "1.0",
        "approval_status": "approved",
        "approval_scope": "initial_persistent_work_graph_bootstrap",
        "approved_by": name,
        "approved_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        **asdict(state),
        "policy": (
            "This approval binds one immutable verified reconciliation candidate, its verified bootstrap graph delta, "
            "and its verification summary by SHA-256. It authorizes deterministic initial Tasks/*.yaml seeding only. "
            "It does not authorize later reconciliation runs to mutate the persistent graph automatically."
        ),
    }
    APPROVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with APPROVAL_PATH.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def print_state(state: VerifiedBootstrapState) -> None:
    print("Verified bootstrap approval gate: PASS")
    print(f"Reconciliation run: {state.source_reconciliation_run_id}")
    print(f"Verification run:   {state.verification_run_id}")
    print(f"Verification status:{state.verification_status:>25}")
    print(f"Final material findings: {state.final_material_findings}")
    print(f"Candidate: {state.candidate_path}")
    print(f"Candidate SHA-256: {state.candidate_sha256}")
    print(f"Delta: {state.delta_path}")
    print(f"Delta SHA-256: {state.delta_sha256}")
    print(f"Verification summary SHA-256: {state.verification_summary_sha256}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and explicitly approve one verified reconciliation for deterministic Milestone 1 bootstrap seeding."
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Write Pipeline/TaskGraph/APPROVED_BOOTSTRAP.json after all deterministic checks pass.",
    )
    parser.add_argument(
        "--approved-by",
        default="",
        help="Human approver recorded in the manifest; required with --approve.",
    )
    args = parser.parse_args()

    state = inspect_verified_state()
    print_state(state)

    if args.approve:
        write_approval_manifest(state, args.approved_by)
        print(f"Human approval recorded: {APPROVAL_PATH.relative_to(ROOT).as_posix()}")
    else:
        print("No approval was written. Re-run with --approve --approved-by <name> after human review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
