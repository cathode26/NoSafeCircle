from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "Pipeline" / "Reconciliation"
if str(RECON) not in sys.path:
    sys.path.insert(0, str(RECON))

import verification_crew as base  # noqa: E402
import parallel_verification_crew as parallel  # noqa: E402
import streaming_refinement_v2 as stream_v2  # noqa: E402
from output_layout import write_current_view  # noqa: E402


def load_pass1(run_dir: Path) -> list[dict]:
    pass1_dir = run_dir / "pass1"
    files = sorted(pass1_dir.glob("*.json"))
    if len(files) != len(parallel.SPECS):
        raise RuntimeError(
            f"Expected {len(parallel.SPECS)} preserved pass-1 auditor files; found {len(files)}."
        )
    audits = [base.load_json(path) for path in files]
    audits.sort(key=lambda item: str(item.get("agent", "")))
    return audits


def load_repairs(run_dir: Path) -> dict[str, dict]:
    repairs: dict[str, dict] = {}
    root = run_dir / "stream_repairs"
    for repair_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        candidate = repair_dir / "RECOVERED_FIELD_REPAIR.json"
        if not candidate.exists():
            candidate = repair_dir / "PROPOSED_FIELD_REPAIR.json"
        if candidate.exists():
            repairs[repair_dir.name] = base.load_json(candidate)
    if not repairs:
        raise RuntimeError("No preserved streaming field repairs were found.")
    return repairs


def copy_preserved_inputs(
    *,
    failed_dir: Path,
    paths: dict,
    repairs: dict[str, dict],
) -> None:
    paths["pass1_dir"].mkdir(parents=True, exist_ok=False)
    for source in sorted((failed_dir / "pass1").glob("*.json")):
        shutil.copy2(source, paths["pass1_dir"] / source.name)

    for audit_key, envelope in sorted(repairs.items()):
        target_dir = paths["run_dir"] / "stream_repairs" / audit_key
        target_dir.mkdir(parents=True, exist_ok=False)
        source_findings = failed_dir / "stream_repairs" / audit_key / "REFINER_FINDINGS.json"
        if source_findings.exists():
            shutil.copy2(source_findings, target_dir / "REFINER_FINDINGS.json")
        base.save_new_json(target_dir / "REUSED_FIELD_REPAIR.json", envelope)


def build_manifest(coordinator: stream_v2.StreamingRepairCoordinator) -> dict:
    return {
        "schema_version": "2.1-field-ops-resume",
        "repair_model": stream_v2.STREAM_REPAIR_MODEL,
        "repairs": [
            {
                "audit_key": key,
                "requested_model": envelope.get("requested_model"),
                "duration_seconds": envelope.get("duration_seconds"),
                "repair": envelope.get("result"),
                "reused_from_failed_verification": True,
            }
            for key, envelope in sorted(coordinator.repairs.items())
        ],
        "failures": {},
        "deterministic_conflict_report": coordinator.conflict_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resume a streaming-v2 verification that finished pass 1 and local field repairs "
            "but failed during deterministic synthesis/semantic validation."
        )
    )
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--verification-run-id", required=True)
    args = parser.parse_args()

    source_run_id = args.source_run_id
    source_candidate = base.RUNS_DIR / source_run_id / "reconciliation.json"
    if not source_candidate.exists():
        raise FileNotFoundError(source_candidate)

    failed_dir = base.verification_root(source_run_id) / args.verification_run_id
    if not failed_dir.exists():
        raise FileNotFoundError(failed_dir)

    pass1_audits = load_pass1(failed_dir)
    repairs = load_repairs(failed_dir)
    old_assignments = base.load_json(failed_dir / "MODEL_ASSIGNMENTS.json")

    paths = base.create_verification_paths(source_run_id)
    copy_preserved_inputs(
        failed_dir=failed_dir,
        paths=paths,
        repairs=repairs,
    )

    merged1 = base.merge_findings(pass1_audits)
    base.save_new_json(paths["merged_pass1"], merged1)
    refiner_findings = base.build_refiner_findings(merged1)
    base.save_new_json(paths["refiner_findings"], refiner_findings)

    coordinator = stream_v2.StreamingRepairCoordinator(
        source_candidate=source_candidate,
        source_run_id=source_run_id,
        run_dir=paths["run_dir"],
    )
    # The constructor created a fresh empty stream_repairs directory, but the preserved
    # copies were already placed there. No new local repairs are submitted during resume.
    coordinator.executor.shutdown(wait=False)
    coordinator._collected = True
    coordinator.repairs = copy.deepcopy(repairs)
    coordinator.failures = {}
    coordinator._build_conflict_report()
    base.save_json(coordinator.manifest_path, build_manifest(coordinator))

    print()
    print("=" * 72)
    print("RESUMED STREAMING REPAIR SYNTHESIS")
    print("=" * 72)
    print(f"Source reconciliation: {source_run_id}")
    print(f"Failed verification reused: {args.verification_run_id}")
    print(f"Preserved pass-1 auditors: {len(pass1_audits)}")
    print(f"Preserved field repairs: {len(repairs)}")
    print(
        "Mechanical field conflicts: "
        f"{coordinator.summary()['mechanical_conflict_count']}"
    )
    print("No pass-1 auditors or local field-repair agents will be rerun.")
    print("=" * 72)

    refiner_model = str(old_assignments.get("refiner", base.REFINER_MODEL))
    refiner = coordinator.arbitrate(
        full_findings_path=paths["refiner_findings"],
        model=refiner_model,
    )
    refiner_delta = refiner["result"]
    base.save_new_json(paths["refiner_delta"], refiner_delta)

    source_payload = base.load_json(source_candidate)
    refined_payload = base.apply_refiner_delta(
        source_payload=source_payload,
        delta=refiner_delta,
        refiner_findings=refiner_findings,
    )
    base.save_new_json(paths["refined_raw"], refined_payload)

    removed = parallel.sanitize_forbidden_evidence(refined_payload)
    if removed:
        print("Removed forbidden evidence: " + ", ".join(removed))
    base.sanitize_refiner_input_tracking(refined_payload)
    parallel.repair_missing_dependency_references(refined_payload)
    parallel.run_semantic_validation(refined_payload)

    base.save_new_json(paths["refined_json"], refined_payload)
    base.save_new_text(paths["refined_markdown"], parallel.render_markdown(refined_payload))

    refined_delta = parallel.build_proposed_graph_delta(
        refined_payload,
        run_id=source_run_id,
        created_at_utc=paths["created_at_utc"],
    )
    refined_delta["verification_run_id"] = paths["verification_run_id"]
    refined_delta["source_reconciliation_run_id"] = source_run_id
    refined_delta["resumed_from_verification_run_id"] = args.verification_run_id
    base.save_new_json(paths["refined_delta_json"], refined_delta)
    base.save_new_text(
        paths["refined_delta_markdown"],
        parallel.render_graph_delta_markdown(refined_delta),
    )

    selected_pass2_keys = parallel.changed_audit_keys(source_payload, refined_payload)
    selected_pass2_keys.update(parallel.auditors_with_findings(pass1_audits))
    selected_specs = [spec for spec in parallel.SPECS if spec.key in selected_pass2_keys]

    pass2_assignments = old_assignments.get("pass2", {})
    missing_models = [spec.key for spec in selected_specs if spec.key not in pass2_assignments]
    if missing_models:
        raise RuntimeError(f"Preserved MODEL_ASSIGNMENTS lacks pass2 models for {missing_models}.")

    print()
    print("=" * 72)
    print("SELECTIVE PASS 2 — RESUMED RUN")
    print("=" * 72)
    print(f"Rerunning {len(selected_specs)} of {len(parallel.SPECS)} auditors.")
    if selected_specs:
        print("Auditors: " + ", ".join(spec.key for spec in selected_specs))
    print("=" * 72)

    if selected_specs:
        pass2_audits = parallel.run_specs(
            specs=selected_specs,
            candidate_path=paths["refined_json"],
            source_run_id=source_run_id,
            pass_label="pass2-selective-resumed",
            output_dir=paths["pass2_dir"],
            assignments=pass2_assignments,
        )
    else:
        paths["pass2_dir"].mkdir(parents=True, exist_ok=False)
        pass2_audits = []

    final_audits = parallel.final_audit_set(
        pass1_audits=pass1_audits,
        rerun_audits=pass2_audits,
        selected_keys=selected_pass2_keys,
    )
    final_merged = base.merge_findings(final_audits)
    final_merged["selective_pass2"] = {
        "enabled": True,
        "resumed": True,
        "rerun_auditor_count": len(selected_specs),
        "total_auditor_count": len(parallel.SPECS),
        "rerun_keys": sorted(selected_pass2_keys),
        "reuse_policy": (
            "Pass 1 and field-repair artifacts were reused from the failed verification; "
            "only synthesis and selective Pass 2 were rerun after deterministic merge repair."
        ),
    }
    base.save_new_json(paths["merged_pass2"], final_merged)

    status = base.status_from_pass2(final_merged)
    model_assignments = copy.deepcopy(old_assignments)
    model_assignments["schema_version"] = "2.1-parallel-resumed"
    model_assignments["resumed_from_verification_run_id"] = args.verification_run_id
    base.save_new_json(paths["model_assignments"], model_assignments)

    summary = {
        "schema_version": "2.1-parallel-resumed",
        "source_run_id": source_run_id,
        "verification_run_id": paths["verification_run_id"],
        "resumed_from_verification_run_id": args.verification_run_id,
        "created_at_utc": paths["created_at_utc"],
        "status": status,
        "source_candidate": source_candidate.relative_to(ROOT).as_posix(),
        "final_candidate": paths["refined_json"].relative_to(ROOT).as_posix(),
        "refinement_performed": True,
        "parallel_auditor_count": len(parallel.SPECS),
        "parallel_max_workers": parallel.PARALLEL_MAX_WORKERS,
        "streaming_refinement": {
            **coordinator.summary(),
            "resumed_from_failed_verification": True,
            "reused_pass1_auditors": len(pass1_audits),
            "reused_field_repairs": len(repairs),
        },
        "model_assignments": {
            "pass1": old_assignments.get("pass1"),
            "refiner": refiner_model,
            "pass2": {key: pass2_assignments[key] for key in sorted(selected_pass2_keys)},
        },
        "pass1": merged1,
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
    print("RESUMED VERIFICATION COMPLETE")
    print("=" * 72)
    print(f"Status: {status}")
    print(f"Pass 1 material findings: {merged1.get('material_finding_count', 0)}")
    print(f"Pass 2 auditors rerun: {len(selected_specs)} / {len(parallel.SPECS)}")
    print(f"Final material findings: {final_merged.get('material_finding_count', 0)}")
    print(f"Verification run: {paths['verification_run_id']}")
    print("The original reconciliation and failed verification artifacts were not modified.")
    print("Tasks/*.yaml was not modified.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
