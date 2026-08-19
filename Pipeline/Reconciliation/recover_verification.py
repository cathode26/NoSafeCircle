from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from output_layout import resolve_verification_dir, write_current_view

from reconciliation_agent import (
    build_proposed_graph_delta,
    render_graph_delta_markdown,
    render_markdown,
    repair_missing_dependency_references,
    run_semantic_validation,
    sanitize_forbidden_evidence,
)
from verification_crew import (
    ROOT,
    RUNS_DIR,
    REFINER_MODEL,
    build_refiner_findings,
    create_verification_paths,
    load_json,
    merge_findings,
    render_verification_markdown,
    run_audit_pass,
    run_refiner,
    sanitize_refiner_input_tracking,
    save_json,
    save_new_json,
    save_new_text,
    status_from_pass2,
    write_latest_verification_pointer,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resume a preserved multi-model reconciliation verification after "
            "a post-refiner deterministic-validation failure."
        )
    )
    parser.add_argument(
        "--source-run-id",
        required=True,
        help="Immutable reconciliation run ID that was being verified.",
    )
    parser.add_argument(
        "--verification-run-id",
        required=True,
        help="Preserved verification run directory ID to resume.",
    )
    return parser.parse_args()


def created_at_from_run_id(run_id: str) -> str:
    stamp = run_id.split("-", 1)[0]
    try:
        dt = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
        return dt.isoformat().replace("+00:00", "Z")
    except ValueError:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )


def existing_paths(source_run_id: str, verification_run_id: str) -> dict[str, Any]:
    run_dir = resolve_verification_dir(source_run_id, verification_run_id)
    if not run_dir.exists():
        raise FileNotFoundError(f"Verification directory not found: {run_dir}")

    return {
        "verification_run_id": verification_run_id,
        "created_at_utc": created_at_from_run_id(verification_run_id),
        "source_run_id": source_run_id,
        "run_dir": run_dir,
        "model_assignments": run_dir / "MODEL_ASSIGNMENTS.json",
        "pass1_dir": run_dir / "pass1",
        "merged_pass1": run_dir / "MERGED_FINDINGS_PASS1.json",
        "refiner_findings": run_dir / "REFINER_FINDINGS.json",
        "recovery_json": run_dir / "RECOVERY.json",
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


def main() -> int:
    try:
        args = parse_args()
        paths = existing_paths(args.source_run_id, args.verification_run_id)

        source_candidate = (
            RUNS_DIR / args.source_run_id / "reconciliation.json"
        )
        if not source_candidate.exists():
            raise FileNotFoundError(
                f"Source reconciliation not found: {source_candidate}"
            )

        for required in (
            paths["model_assignments"],
            paths["merged_pass1"],
        ):
            if not required.exists():
                raise FileNotFoundError(
                    "Cannot resume because required preserved artifact is "
                    f"missing: {required}"
                )

        if paths["summary_json"].exists():
            raise RuntimeError(
                "This verification already has VERIFICATION_SUMMARY.json; "
                "refusing to resume a completed verification."
            )

        assignments = load_json(paths["model_assignments"])
        merged1 = load_json(paths["merged_pass1"])

        print()
        print("=" * 72)
        print("RESUMING PRESERVED RECONCILIATION VERIFICATION")
        print("=" * 72)
        print(f"Source reconciliation: {args.source_run_id}")
        print(f"Verification run: {args.verification_run_id}")
        print("Reusing completed pass-1 audits and merged findings.")
        print("Pass 1 will NOT be rerun.")

        actual_refiner_model = str(assignments.get("refiner", "")).strip()

        if paths["refined_raw"].exists():
            refined_payload = load_json(paths["refined_raw"])
            print("Completed Refiner output exists and will be reused.")
        else:
            if not paths["refiner_findings"].exists():
                save_new_json(
                    paths["refiner_findings"],
                    build_refiner_findings(merged1),
                )

            recovery_model = os.environ.get(
                "RECONCILIATION_VERIFY_RECOVERY_REFINER_MODEL",
                REFINER_MODEL,
            ).strip() or REFINER_MODEL
            original_model = str(assignments.get("refiner", "")).strip()

            print(
                "No completed Refiner output exists. This preserved run stopped "
                "during refinement, so only the Refiner will be rerun."
            )
            print(f"Original Refiner assignment: {original_model or '(unknown)'}")
            print(f"Recovery Refiner model: {recovery_model}")

            refiner = run_refiner(
                source_candidate=source_candidate,
                merged_findings_path=paths["refiner_findings"],
                source_run_id=args.source_run_id,
                model=recovery_model,
            )
            refined_payload = refiner["result"]
            save_new_json(paths["refined_raw"], refined_payload)
            actual_refiner_model = recovery_model

            if not paths["recovery_json"].exists():
                save_new_json(
                    paths["recovery_json"],
                    {
                        "schema_version": "1.0",
                        "reason": "refiner_timeout_or_missing_refined_raw",
                        "source_reconciliation_run_id": args.source_run_id,
                        "verification_run_id": args.verification_run_id,
                        "pass1_reused": True,
                        "original_refiner_model": original_model,
                        "recovery_refiner_model": recovery_model,
                    },
                )

        print("=" * 72)

        removed_forbidden = sanitize_forbidden_evidence(refined_payload)
        if removed_forbidden:
            print(
                "Warning: removed forbidden evidence before validation: "
                + ", ".join(removed_forbidden)
            )

        removed_tracking = sanitize_refiner_input_tracking(refined_payload)
        if removed_tracking:
            print(
                "Normalized Refiner bookkeeping paths out of "
                "sources.files_reviewed: " + ", ".join(removed_tracking)
            )

        repair_missing_dependency_references(refined_payload)
        run_semantic_validation(refined_payload)

        if not paths["refined_json"].exists():
            save_new_json(paths["refined_json"], refined_payload)
        if not paths["refined_markdown"].exists():
            save_new_text(
                paths["refined_markdown"], render_markdown(refined_payload)
            )

        refined_delta = build_proposed_graph_delta(
            refined_payload,
            run_id=args.source_run_id,
            created_at_utc=paths["created_at_utc"],
        )
        refined_delta["verification_run_id"] = args.verification_run_id
        refined_delta["source_reconciliation_run_id"] = args.source_run_id

        if not paths["refined_delta_json"].exists():
            save_new_json(paths["refined_delta_json"], refined_delta)
        if not paths["refined_delta_markdown"].exists():
            save_new_text(
                paths["refined_delta_markdown"],
                render_graph_delta_markdown(refined_delta),
            )

        if paths["merged_pass2"].exists():
            print("Pass 2 merged findings already exist; reusing them.")
            final_merged = load_json(paths["merged_pass2"])
        else:
            if paths["pass2_dir"].exists():
                raise RuntimeError(
                    "A partial pass2 directory already exists without "
                    "MERGED_FINDINGS_PASS2.json. Preserve it and review before "
                    "retrying so completed verifier output is not overwritten."
                )

            pass2_assignments = assignments.get("pass2")
            if not isinstance(pass2_assignments, dict):
                raise RuntimeError(
                    "MODEL_ASSIGNMENTS.json does not contain pass2 assignments."
                )

            pass2_audits = run_audit_pass(
                candidate_path=paths["refined_json"],
                source_run_id=args.source_run_id,
                pass_label="pass2",
                output_dir=paths["pass2_dir"],
                assignments=pass2_assignments,
            )
            final_merged = merge_findings(pass2_audits)
            save_new_json(paths["merged_pass2"], final_merged)

        status = status_from_pass2(final_merged)

        summary = {
            "schema_version": "1.0",
            "source_run_id": args.source_run_id,
            "verification_run_id": args.verification_run_id,
            "created_at_utc": paths["created_at_utc"],
            "status": status,
            "source_candidate": source_candidate.relative_to(ROOT).as_posix(),
            "final_candidate": paths["refined_json"].relative_to(ROOT).as_posix(),
            "refinement_performed": True,
            "recovered_from_preserved_run": True,
            "refiner_recovered": paths["recovery_json"].exists(),
            "model_assignments": {
                "pass1": assignments.get("pass1"),
                "refiner": actual_refiner_model,
                "original_refiner_assignment": assignments.get("refiner"),
                "pass2": assignments.get("pass2"),
            },
            "pass1": merged1,
            "final_pass": final_merged,
            "human_approval_required": True,
            "persistent_graph_mutated": False,
        }

        save_new_json(paths["summary_json"], summary)
        save_new_text(
            paths["summary_markdown"], render_verification_markdown(summary)
        )
        write_latest_verification_pointer(paths, status)
        write_current_view(
            source_reconciliation_run_id=args.source_run_id,
            status=status,
            candidate_json=paths["refined_json"],
            candidate_markdown=paths["refined_markdown"],
            delta_json=paths["refined_delta_json"],
            delta_markdown=paths["refined_delta_markdown"],
            verification_run_id=args.verification_run_id,
            verification_summary_json=paths["summary_json"],
            verification_markdown=paths["summary_markdown"],
        )

        print()
        print("=" * 72)
        print("RECOVERED MULTI-MODEL VERIFICATION COMPLETE")
        print("=" * 72)
        print(f"Status: {status}")
        print(
            "Pass 1 material findings: "
            f"{merged1.get('material_finding_count', 0)}"
        )
        print(
            "Final material findings: "
            f"{final_merged.get('material_finding_count', 0)}"
        )
        print(f"Saved: {paths['summary_markdown'].relative_to(ROOT)}")
        print(f"Saved: {paths['summary_json'].relative_to(ROOT)}")
        print(
            "Original reconciliation snapshot, pass-1 audits, and Refiner raw "
            "output were preserved."
        )
        print("Tasks/*.yaml was not modified.")
        print("=" * 72)
        return 0

    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("VERIFICATION RECOVERY FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
