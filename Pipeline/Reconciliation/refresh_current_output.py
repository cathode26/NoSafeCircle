from __future__ import annotations

import sys
from pathlib import Path

from output_layout import (
    LATEST_POINTER_PATH,
    LATEST_VERIFICATION_POINTER_PATH,
    ROOT,
    RUNS_DIR,
    load_json,
    resolve_verification_dir,
    write_current_view,
)


def main() -> int:
    try:
        if not LATEST_POINTER_PATH.exists():
            raise FileNotFoundError("No outputs/LATEST.json exists.")

        latest = load_json(LATEST_POINTER_PATH)
        source_run_id = str(latest.get("latest_successful_run_id", "")).strip()
        if not source_run_id:
            raise RuntimeError("LATEST.json has no latest_successful_run_id.")

        source_dir = RUNS_DIR / source_run_id
        source_candidate = source_dir / "reconciliation.json"
        source_markdown = source_dir / "RECONCILIATION.md"
        source_delta_json = source_dir / "PROPOSED_GRAPH_DELTA.json"
        source_delta_md = source_dir / "PROPOSED_GRAPH_DELTA.md"

        if LATEST_VERIFICATION_POINTER_PATH.exists():
            vp = load_json(LATEST_VERIFICATION_POINTER_PATH)
            if str(vp.get("source_reconciliation_run_id", "")) == source_run_id:
                verification_run_id = str(vp.get("latest_verification_run_id", "")).strip()
                status = str(vp.get("status", "needs_human_review"))
                vdir = resolve_verification_dir(source_run_id, verification_run_id)
                summary_json = vdir / "VERIFICATION_SUMMARY.json"
                summary_md = vdir / "VERIFICATION.md"

                if summary_json.exists():
                    summary = load_json(summary_json)
                    final_candidate_text = str(summary.get("final_candidate", "")).strip()
                    final_candidate = ROOT / final_candidate_text if final_candidate_text else vdir / "refined_candidate.json"
                    if not final_candidate.exists() and (vdir / "refined_candidate.json").exists():
                        final_candidate = vdir / "refined_candidate.json"

                    candidate_md = (
                        vdir / "REFINED_RECONCILIATION.md"
                        if (vdir / "REFINED_RECONCILIATION.md").exists()
                        else source_markdown
                    )
                    delta_json = (
                        vdir / "PROPOSED_REFINED_GRAPH_DELTA.json"
                        if (vdir / "PROPOSED_REFINED_GRAPH_DELTA.json").exists()
                        else source_delta_json
                    )
                    delta_md = (
                        vdir / "PROPOSED_REFINED_GRAPH_DELTA.md"
                        if (vdir / "PROPOSED_REFINED_GRAPH_DELTA.md").exists()
                        else source_delta_md
                    )

                    write_current_view(
                        source_reconciliation_run_id=source_run_id,
                        status=status,
                        candidate_json=final_candidate,
                        candidate_markdown=candidate_md,
                        delta_json=delta_json,
                        delta_markdown=delta_md,
                        verification_run_id=verification_run_id,
                        verification_summary_json=summary_json,
                        verification_markdown=summary_md,
                    )
                    print("Refreshed outputs/current from latest verification.")
                    return 0

        write_current_view(
            source_reconciliation_run_id=source_run_id,
            status="unverified_reconciliation",
            candidate_json=source_candidate,
            candidate_markdown=source_markdown,
            delta_json=source_delta_json,
            delta_markdown=source_delta_md,
        )
        print("Refreshed outputs/current from latest reconciliation.")
        return 0

    except Exception as exc:
        print(f"CURRENT OUTPUT REFRESH FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
