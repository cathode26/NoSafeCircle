from __future__ import annotations

import argparse
import copy
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "Pipeline" / "Reconciliation"
if str(RECON) not in sys.path:
    sys.path.insert(0, str(RECON))

import verification_crew as base  # noqa: E402
import parallel_verification_crew as parallel  # noqa: E402
from output_layout import write_current_view  # noqa: E402

BAD_LABEL = "2026-08-21 VERIFIED CLOSURE"
TARGET_KEY = "enemy-pursuit-search-foundation"
RERUN_KEYS = {"coverage_enemy_behavior", "evidence_enemy_encounters"}


def load_audits(directory: Path) -> list[dict[str, Any]]:
    audits = [base.load_json(path) for path in sorted(directory.glob("*.json"))]
    audits.sort(key=lambda item: str(item.get("agent", "")))
    return audits


def reconstruct_prior_final_audits(prior_dir: Path) -> list[dict[str, Any]]:
    pass1 = load_audits(prior_dir / "pass1")
    if len(pass1) != len(parallel.SPECS):
        raise RuntimeError(
            f"Expected {len(parallel.SPECS)} baseline audits in pass1; found {len(pass1)}."
        )
    pass2_dir = prior_dir / "pass2"
    pass2 = load_audits(pass2_dir)
    selected = {path.stem for path in pass2_dir.glob("*.json")}
    if not selected:
        return pass1
    return parallel.final_audit_set(
        pass1_audits=pass1,
        rerun_audits=pass2,
        selected_keys=selected,
    )


def copy_baseline_audits(audits: list[dict[str, Any]], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    by_agent = {str(audit.get("agent", "")): audit for audit in audits}
    for spec in parallel.SPECS:
        audit = by_agent.get(spec.agent_name)
        if audit is None:
            raise RuntimeError(f"Missing baseline audit for {spec.agent_name}.")
        base.save_new_json(target / f"{spec.key}.json", audit)


def apply_final_provenance_cleanup(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    corrected = copy.deepcopy(payload)
    items = {
        str(item.get("key", "")): item
        for item in corrected.get("work_items", [])
    }
    item = items.get(TARGET_KEY)
    if item is None:
        raise RuntimeError(f"Missing work item {TARGET_KEY!r}.")

    changes: list[str] = []
    for criterion in item.get("acceptance_criteria", []):
        reference = str(criterion.get("reference", ""))
        if BAD_LABEL in reference:
            criterion["reference"] = "Door and Pursuit Rules"
            changes.append(
                "Removed fabricated VERIFIED CLOSURE fragment from enemy pursuit acceptance criterion."
            )

    for validation in item.get("validation_requirements", []):
        reference = str(validation.get("reference", ""))
        if BAD_LABEL in reference:
            validation["reference"] = "Door and Pursuit Rules"
            changes.append(
                "Replaced fabricated VERIFIED CLOSURE validation citation with Door and Pursuit Rules."
            )

    # This continuation is intentionally narrow. Refuse to silently leave the known
    # fabricated label anywhere in durable GDD-reference fields.
    leftovers: list[str] = []
    for work_item in corrected.get("work_items", []):
        for field in ("gdd_evidence", "acceptance_criteria", "validation_requirements"):
            for entry in work_item.get(field, []):
                if BAD_LABEL in str(entry.get("reference", "")):
                    leftovers.append(f"{work_item.get('key')}:{field}:{entry.get('reference')}")
    if leftovers:
        raise RuntimeError(
            "Final provenance cleanup still found fabricated VERIFIED CLOSURE references: "
            + "; ".join(leftovers)
        )
    if len(changes) != 2:
        raise RuntimeError(
            f"Expected exactly two final provenance corrections; found {len(changes)}."
        )
    return corrected, changes


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Continue the completed round-3 verification, remove the final fabricated "
            "VERIFIED CLOSURE citations, and rerun only enemy-behavior coverage/evidence."
        )
    )
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--verification-run-id", required=True)
    args = parser.parse_args()

    source_run_id = args.source_run_id
    prior_dir = base.verification_root(source_run_id) / args.verification_run_id
    baseline_candidate = prior_dir / "refined_candidate.json"
    assignments_path = prior_dir / "MODEL_ASSIGNMENTS.json"
    if not baseline_candidate.exists():
        raise FileNotFoundError(baseline_candidate)
    if not assignments_path.exists():
        raise FileNotFoundError(assignments_path)

    baseline_payload = base.load_json(baseline_candidate)
    baseline_audits = reconstruct_prior_final_audits(prior_dir)
    baseline_merged = base.merge_findings(baseline_audits)
    assignments = base.load_json(assignments_path)

    corrected_payload, changes = apply_final_provenance_cleanup(baseline_payload)
    probe = copy.deepcopy(corrected_payload)
    parallel.sanitize_forbidden_evidence(probe)
    base.sanitize_refiner_input_tracking(probe)
    parallel.repair_missing_dependency_references(probe)
    parallel.run_semantic_validation(probe)
    corrected_payload = probe

    paths = base.create_verification_paths(source_run_id)
    copy_baseline_audits(baseline_audits, paths["pass1_dir"])
    base.save_new_json(paths["merged_pass1"], baseline_merged)
    base.save_new_json(paths["refined_raw"], corrected_payload)
    base.save_new_json(paths["refined_json"], corrected_payload)
    base.save_new_text(paths["refined_markdown"], parallel.render_markdown(corrected_payload))
    base.save_new_json(
        paths["run_dir"] / "FINAL_PROVENANCE_CORRECTIONS.json",
        {
            "schema_version": "1.0",
            "continued_from_verification_run_id": args.verification_run_id,
            "changes": changes,
        },
    )

    refined_delta = parallel.build_proposed_graph_delta(
        corrected_payload,
        run_id=source_run_id,
        created_at_utc=paths["created_at_utc"],
    )
    refined_delta["verification_run_id"] = paths["verification_run_id"]
    refined_delta["source_reconciliation_run_id"] = source_run_id
    refined_delta["continued_from_verification_run_id"] = args.verification_run_id
    base.save_new_json(paths["refined_delta_json"], refined_delta)
    base.save_new_text(
        paths["refined_delta_markdown"],
        parallel.render_graph_delta_markdown(refined_delta),
    )

    selected_specs = [spec for spec in parallel.SPECS if spec.key in RERUN_KEYS]
    pass2_assignments = assignments.get("pass2", {})
    pass1_assignments = assignments.get("pass1", {})
    models: dict[str, str] = {}
    for spec in selected_specs:
        model = pass2_assignments.get(spec.key) or pass1_assignments.get(spec.key)
        if not model:
            raise RuntimeError(f"No preserved model assignment for {spec.key}.")
        models[spec.key] = model

    print()
    print("=" * 72)
    print("FINAL PROVENANCE VERIFICATION CONTINUATION")
    print("=" * 72)
    print(f"Source reconciliation: {source_run_id}")
    print(f"Continued from verification: {args.verification_run_id}")
    print(f"Baseline material findings: {baseline_merged.get('material_finding_count', 0)}")
    print("Applied corrections:")
    for change in changes:
        print(f"  - {change}")
    print(f"Rerunning {len(selected_specs)} of {len(parallel.SPECS)} auditors.")
    print("Auditors: " + ", ".join(spec.key for spec in selected_specs))
    print("=" * 72)

    rerun_audits = parallel.run_specs(
        specs=selected_specs,
        candidate_path=paths["refined_json"],
        source_run_id=source_run_id,
        pass_label="final-provenance-targeted",
        output_dir=paths["pass2_dir"],
        assignments=models,
    )
    final_audits = parallel.final_audit_set(
        pass1_audits=baseline_audits,
        rerun_audits=rerun_audits,
        selected_keys=RERUN_KEYS,
    )
    final_merged = base.merge_findings(final_audits)
    final_merged["selective_pass2"] = {
        "enabled": True,
        "final_provenance_continuation": True,
        "rerun_auditor_count": len(selected_specs),
        "total_auditor_count": len(parallel.SPECS),
        "rerun_keys": sorted(RERUN_KEYS),
        "reuse_policy": (
            "The completed round-3 final audit set is reused. Only enemy-behavior coverage "
            "and enemy/encounter evidence are rerun after the provenance-only correction."
        ),
    }
    base.save_new_json(paths["merged_pass2"], final_merged)

    status = base.status_from_pass2(final_merged)
    model_assignments = copy.deepcopy(assignments)
    model_assignments["schema_version"] = "2.3-final-provenance-continuation"
    model_assignments["continued_from_verification_run_id"] = args.verification_run_id
    model_assignments["pass2"] = models
    base.save_new_json(paths["model_assignments"], model_assignments)

    summary = {
        "schema_version": "2.3-final-provenance-continuation",
        "source_run_id": source_run_id,
        "verification_run_id": paths["verification_run_id"],
        "continued_from_verification_run_id": args.verification_run_id,
        "created_at_utc": paths["created_at_utc"],
        "status": status,
        "source_candidate": baseline_candidate.relative_to(ROOT).as_posix(),
        "final_candidate": paths["refined_json"].relative_to(ROOT).as_posix(),
        "refinement_performed": True,
        "parallel_auditor_count": len(parallel.SPECS),
        "parallel_max_workers": parallel.PARALLEL_MAX_WORKERS,
        "streaming_refinement": {
            "enabled": True,
            "version": "2.3-final-provenance-continuation",
            "reused_completed_auditors": len(parallel.SPECS) - len(selected_specs),
            "targeted_rerun_auditors": len(selected_specs),
        },
        "model_assignments": {
            "pass1": "reused completed round-3 final audit set",
            "refiner": "deterministic final provenance correction",
            "pass2": models,
        },
        "pass1": baseline_merged,
        "final_pass": final_merged,
        "human_approval_required": True,
        "persistent_graph_mutated": False,
    }
    base.save_new_json(paths["summary_json"], summary)
    base.save_new_text(paths["summary_markdown"], base.render_verification_markdown(summary))
    base.write_latest_verification_pointer(paths, status)

    write_current_view(
        source_reconciliation_run_id=source_run_id,
        status=status,
        candidate_json=paths["refined_json"],
        candidate_markdown=paths["refined_markdown"],
        delta_json=paths["refined_delta_json"],
        delta_markdown=paths["refined_delta_markdown"],
        verification_run_id=paths["verification_run_id"],
        verification_summary_json=paths["summary_json"],
        verification_markdown=paths["summary_markdown"],
    )

    print()
    print("=" * 72)
    print("FINAL PROVENANCE VERIFICATION COMPLETE")
    print("=" * 72)
    print(f"Status: {status}")
    print(f"Baseline material findings: {baseline_merged.get('material_finding_count', 0)}")
    print(f"Auditors rerun: {len(selected_specs)} / {len(parallel.SPECS)}")
    print(f"Final material findings: {final_merged.get('material_finding_count', 0)}")
    print(f"Verification run: {paths['verification_run_id']}")
    print("The source reconciliation and prior verification artifacts were not modified.")
    print("Tasks/*.yaml was not modified.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
