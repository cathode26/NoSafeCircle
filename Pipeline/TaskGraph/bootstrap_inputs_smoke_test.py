from __future__ import annotations

import json
import tempfile
from pathlib import Path

from bootstrap_inputs import BootstrapInputError, load_approved_bootstrap_inputs, sha256_file


SOURCE_RUN = "20260821T193541Z-998ee7b5"
VERIFY_RUN = "20260821T195959Z-43dba5de"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def build_fixture(root: Path) -> Path:
    verification_root = (
        root
        / "Pipeline"
        / "Reconciliation"
        / "outputs"
        / "runs"
        / SOURCE_RUN
        / "verifications"
        / VERIFY_RUN
    )
    candidate_path = verification_root / "refined_candidate.json"
    delta_path = verification_root / "PROPOSED_REFINED_GRAPH_DELTA.json"
    summary_path = verification_root / "VERIFICATION_SUMMARY.json"

    candidate = {
        "schema_version": "test",
        "reconciliation_run_id": SOURCE_RUN,
        "work_items": [
            {
                "key": "player",
                "title": "Player",
                "kind": "feature",
            },
            {
                "key": "player-movement",
                "title": "Player Movement",
                "kind": "implementation",
            },
        ],
    }
    delta = {
        "schema_version": "1.0",
        "reconciliation_run_id": SOURCE_RUN,
        "verification_run_id": VERIFY_RUN,
        "status": "bootstrap_seed_proposal",
        "persistent_graph_present": False,
        "persistent_graph_mutated": False,
        "proposed_seed_records": [
            {
                "reconciliation_key": "player",
                "title": "Player",
                "kind": "feature",
            },
            {
                "reconciliation_key": "player-movement",
                "title": "Player Movement",
                "kind": "implementation",
            },
        ],
        "exclusive_resource_groups": [],
        "proposed_non_code_records": [],
    }
    candidate_rel = candidate_path.relative_to(root).as_posix()
    summary = {
        "schema_version": "test",
        "source_run_id": SOURCE_RUN,
        "verification_run_id": VERIFY_RUN,
        "status": "verified_with_findings",
        "final_candidate": candidate_rel,
        "persistent_graph_mutated": False,
        "human_approval_required": True,
        "final_pass": {"material_finding_count": 0},
    }

    write_json(candidate_path, candidate)
    write_json(delta_path, delta)
    write_json(summary_path, summary)

    approval_path = root / "Pipeline" / "TaskGraph" / "APPROVED_BOOTSTRAP.json"
    approval = {
        "schema_version": "1.0",
        "approval_status": "approved",
        "approval_scope": "initial_persistent_work_graph_bootstrap",
        "approved_by": "Smoke Test",
        "source_reconciliation_run_id": SOURCE_RUN,
        "verification_run_id": VERIFY_RUN,
        "verification_status": "verified_with_findings",
        "final_material_findings": 0,
        "candidate_path": candidate_rel,
        "candidate_sha256": sha256_file(candidate_path),
        "delta_path": delta_path.relative_to(root).as_posix(),
        "delta_sha256": sha256_file(delta_path),
        "verification_summary_path": summary_path.relative_to(root).as_posix(),
        "verification_summary_sha256": sha256_file(summary_path),
    }
    write_json(approval_path, approval)

    # A misleading mutable current pointer must be irrelevant after approval.
    write_json(
        root / "Pipeline" / "Reconciliation" / "outputs" / "current" / "CURRENT.json",
        {
            "source_reconciliation_run_id": "WRONG-RUN",
            "verification_run_id": "WRONG-VERIFICATION",
        },
    )
    return approval_path


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        approval_path = build_fixture(root)

        loaded = load_approved_bootstrap_inputs(approval_path=approval_path, root=root)
        assert loaded.source_reconciliation_run_id == SOURCE_RUN
        assert loaded.verification_run_id == VERIFY_RUN
        assert len(loaded.seed_records) == 2

        delta_path = loaded.delta_path
        with delta_path.open("a", encoding="utf-8") as handle:
            handle.write("\n")

        try:
            load_approved_bootstrap_inputs(approval_path=approval_path, root=root)
        except BootstrapInputError as exc:
            assert "SHA-256 mismatch" in str(exc), str(exc)
        else:
            raise AssertionError("Tampered approved delta was not rejected.")

    print("bootstrap_inputs_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
