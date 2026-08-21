from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import parallel_verification_crew as parallel
import verification_crew as base
from output_layout import write_current_view
from reconciliation_agent import (
    build_proposed_graph_delta,
    render_graph_delta_markdown,
    render_markdown,
    repair_missing_dependency_references,
    run_semantic_validation,
    sanitize_forbidden_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resume a failed parallel verification at the Refiner stage without "
            "rerunning the preserved pass-1 auditors."
        )
    )
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--verification-run-id", required=True)
    parser.add_argument(
        "--no-reverify",
        action="store_true",
        help="Stop after producing and validating the refined candidate.",
    )
    return parser.parse_args()


def build_paths(source_run_id: str, verification_run_id: str) -> dict[str, Any]:
    run_dir = base.verification_root(source_run_id) / verification_run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Verification directory not found: {run_dir}")

    return {
        "verification_run_id": verification_run_id,
        "created_at_utc": base.utc_now_iso(),
        "source_run_id": source_run_id,
        "run_dir": run_dir,
        "model_assignments": run_dir / "MODEL_ASSIGNMENTS.json",
        "pass1_dir": run_dir / "pass1",
        "merged_pass1": run_dir / "MERGED_FINDINGS_PASS1.json",
        "refiner_findings": run_dir / "REFINER_FINDINGS.json",
        "refiner_delta": run_dir / "REFINER_DELTA.json",
        "refined_raw": run_dir / "refined_candidate.raw.json",
        "refined_json": run_dir / "refined_candidate.json",
        "refined_markdown": run_dir / "REFINED_RECONCILIATION.md",
        "refined_delta_json": run_dir / "PROPOSED_REFINED_GRAPH_DELTA.json",
        "refined_delta_markdown": run_dir / "PROPOSED_REFINED_GRAPH_DELTA.md",
        "pass2_dir": run_dir / "pass2",
        "merged_pass2": run_dir / "MERGED_FINDINGS_PASS2.json",
        "summary_json": run_dir / "VERIFICATION_SUMMARY.json",
        "summary_markdown": run_dir / "VERIFICATION.md",
    }


def load_pass1_audits(pass1_dir: Path) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for spec in parallel.SPECS:
        path = pass1_dir / f"{spec.key}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Cannot resume: preserved auditor result is missing: {path}"
            )
        audits.append(base.load_json(path))
    audits.sort(key=lambda item: str(item.get("agent", "")))
    return audits


def main() -> int:
    paths: dict[str, Any] | None = None
    try:
        args = parse_args()
        paths = build_paths(args.source_run_id, args.verification_run_id)

        source_candidate = base.RUNS_DIR / args.source_run_id / "reconciliation.json"
        if not source_candidate.exists():
            raise FileNotFoundError(
                f"Source reconciliation not found: {source_candidate}"
            )

        for required in (
            paths["model_assignments"],
            paths["merged_pass1"],
            paths["refiner_findings"],
        ):
            if not required.exists():
                raise FileNotFoundError(
                    f"Cannot resume; required preserved artifact is missing: {required}"
                )

        for output in (
            paths["refiner_delta"],
            paths["refined_raw"],
            paths["refined_json"],
            paths["refined_markdown"],
            paths["refined_delta_json"],
            paths["refined_delta_markdown"],
            paths["merged_pass2"],
            paths["summary_json"],
            paths["summary_markdown"],
        ):
            if output.exists():
                raise RuntimeError(
                    "Resume target already contains post-refiner output; refusing "
                    f"to overwrite immutable artifact: {output}"
                )
        if paths["pass2_dir"].exists():
            raise RuntimeError(
                f"Resume target already contains pass2 directory: {paths['pass2_dir']}"
            )

        assignments = base.load_json(paths["model_assignments"])
        refiner_model = str(assignments.get("refiner", "")).strip()
        pass2_assignments = assignments.get("pass2", {})
        if not refiner_model:
            raise RuntimeError("MODEL_ASSIGNMENTS.json has no refiner model.")
        if not isinstance(pass2_assignments, dict):
            raise RuntimeError("MODEL_ASSIGNMENTS.json has invalid pass2 assignments.")

        source_payload = base.load_json(source_candidate)
        pass1_audits = load_pass1_audits(paths["pass1_dir"])
        merged1 = base.load_json(paths["merged_pass1"])
        refiner_findings = base.load_json(paths["refiner_findings"])

        print()
        print("=" * 72)
        print("RESUMING PARALLEL VERIFICATION AT REFINER")
        print("=" * 72)
        print(f"Source reconciliation: {args.source_run_id}")
        print(f"Verification run: {args.verification_run_id}")
        print("Preserved pass-1 auditors will NOT be rerun.")
        print(f"Refiner model: {refiner_model}")
        print("=" * 72)

        refiner = base.run_refiner(
            source_candidate=source_candidate,
            merged_findings_path=paths["refiner_findings"],
            source_run_id=args.source_run_id,
            model=refiner_model,
        )
        refiner_delta = refiner["result"]
        base.save_new_json(paths["refiner_delta"], refiner_delta)

        refined_payload = base.apply_refiner_delta(
            source_payload=source_payload,
            delta=refiner_delta,
            refiner_findings=refiner_findings,
        )
        base.save_new_json(paths["refined_raw"], refined_payload)

        removed = sanitize_forbidden_evidence(refined_payload)
        if removed:
            print(
                "Warning: Refiner returned forbidden evidence that was removed: "
                + ", ".join(removed)
            )

        removed_tracking = base.sanitize_refiner_input_tracking(refined_payload)
        if removed_tracking:
            print(
                "Normalized Refiner bookkeeping paths from files_reviewed: "
                + ", ".join(removed_tracking)
            )

        repair_missing_dependency_references(refined_payload)
        run_semantic_validation(refined_payload)

        base.save_new_json(paths["refined_json"], refined_payload)
        base.save_new_text(paths["refined_markdown"], render_markdown(refined_payload))

        refined_graph_delta = build_proposed_graph_delta(
            refined_payload,
            run_id=args.source_run_id,
            created_at_utc=paths["created_at_utc"],
        )
        refined_graph_delta["verification_run_id"] = args.verification_run_id
        refined_graph_delta["source_reconciliation_run_id"] = args.source_run_id
        base.save_new_json(paths["refined_delta_json"], refined_graph_delta)
        base.save_new_text(
            paths["refined_delta_markdown"],
            render_graph_delta_markdown(refined_graph_delta),
        )

        final_candidate = paths["refined_json"]
        final_merged = merged1
        selected_pass2_keys: set[str] = set()

        if not args.no_reverify:
            selected_pass2_keys = parallel.changed_audit_keys(
                source_payload,
                refined_payload,
            )
            selected_pass2_keys.update(
                parallel.auditors_with_findings(pass1_audits)
            )
            selected_specs = [
                spec for spec in parallel.SPECS
                if spec.key in selected_pass2_keys
            ]

            print()
            print("=" * 72)
            print("SELECTIVE PASS 2")
            print("=" * 72)
            print(
                f"Rerunning {len(selected_specs)} of {len(parallel.SPECS)} auditors."
            )
            if selected_specs:
                print("Auditors: " + ", ".join(spec.key for spec in selected_specs))
            print("=" * 72)

            if selected_specs:
                pass2_audits = parallel.run_specs(
                    specs=selected_specs,
                    candidate_path=final_candidate,
                    source_run_id=args.source_run_id,
                    pass_label="pass2-selective-resume",
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
                "rerun_auditor_count": len(selected_specs),
                "total_auditor_count": len(parallel.SPECS),
                "rerun_keys": sorted(selected_pass2_keys),
                "reuse_policy": (
                    "Pass-1 results are reused only for auditors outside the "
                    "Refiner's changed territory that did not themselves report "
                    "a finding requiring recheck."
                ),
                "resumed_from_preserved_pass1": True,
            }
            base.save_new_json(paths["merged_pass2"], final_merged)

        status = base.status_from_pass2(final_merged)
        summary = {
            "schema_version": "2.1-parallel-resume",
            "source_run_id": args.source_run_id,
            "verification_run_id": args.verification_run_id,
            "created_at_utc": paths["created_at_utc"],
            "status": status,
            "source_candidate": source_candidate.relative_to(base.ROOT).as_posix(),
            "final_candidate": final_candidate.relative_to(base.ROOT).as_posix(),
            "refinement_performed": True,
            "resumed_after_refiner_failure": True,
            "parallel_auditor_count": len(parallel.SPECS),
            "parallel_max_workers": parallel.PARALLEL_MAX_WORKERS,
            "model_assignments": {
                "pass1": assignments.get("pass1"),
                "refiner": refiner_model,
                "pass2": (
                    {
                        key: pass2_assignments[key]
                        for key in sorted(selected_pass2_keys)
                    }
                    if not args.no_reverify
                    else None
                ),
            },
            "pass1": merged1,
            "final_pass": final_merged,
            "human_approval_required": True,
            "persistent_graph_mutated": False,
        }

        base.save_new_json(paths["summary_json"], summary)
        base.save_new_text(
            paths["summary_markdown"],
            base.render_verification_markdown(summary),
        )
        base.write_latest_verification_pointer(paths, status)

        write_current_view(
            source_reconciliation_run_id=args.source_run_id,
            status=status,
            candidate_json=final_candidate,
            candidate_markdown=paths["refined_markdown"],
            delta_json=paths["refined_delta_json"],
            delta_markdown=paths["refined_delta_markdown"],
            verification_run_id=args.verification_run_id,
            verification_summary_json=paths["summary_json"],
            verification_markdown=paths["summary_markdown"],
        )

        print()
        print("=" * 72)
        print("RESUMED PARALLEL VERIFICATION COMPLETE")
        print("=" * 72)
        print(f"Status: {status}")
        print(
            "Pass 1 material findings: "
            f"{merged1.get('material_finding_count', 0)}"
        )
        if not args.no_reverify:
            print(
                f"Pass 2 auditors rerun: "
                f"{len(selected_pass2_keys)} / {len(parallel.SPECS)}"
            )
        print(
            "Final material findings: "
            f"{final_merged.get('material_finding_count', 0)}"
        )
        print(
            f"Refined candidate: "
            f"{paths['refined_json'].relative_to(base.ROOT)}"
        )
        print("Preserved pass-1 auditors were not rerun.")
        print("Tasks/*.yaml was not modified.")
        print("=" * 72)
        return 0

    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("RESUMED PARALLEL VERIFICATION FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        if paths is not None:
            print(
                "Verification directory preserved: "
                f"{paths['run_dir'].relative_to(base.ROOT)}",
                file=sys.stderr,
            )
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
