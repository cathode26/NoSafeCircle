from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECON_DIR = ROOT / "Pipeline" / "Reconciliation"
if str(RECON_DIR) not in sys.path:
    sys.path.insert(0, str(RECON_DIR))

import reconciliation_agent as base  # noqa: E402
import parallel_reconciliation_agent as parallel  # noqa: E402

NON_EVIDENCE_ROOTS = {"Assets", "Assets/", "ProjectSettings", "ProjectSettings/"}


def normalize(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def strip_non_evidence_roots(payload: dict[str, Any]) -> list[str]:
    removed: list[str] = []
    sources = payload.setdefault("sources", {})

    reviewed = []
    for value in sources.get("files_reviewed", []):
        if normalize(str(value)) in NON_EVIDENCE_ROOTS:
            removed.append(str(value))
        else:
            reviewed.append(value)
    sources["files_reviewed"] = reviewed

    for item in payload.get("work_items", []):
        clean = []
        for evidence in item.get("repository_evidence", []):
            path = str(evidence.get("path", ""))
            if normalize(path) in NON_EVIDENCE_ROOTS:
                removed.append(f"{item.get('key', '<unknown>')}:{path}")
            else:
                clean.append(evidence)
        item["repository_evidence"] = clean

    return removed


def load_workers(source_run_id: str) -> dict[str, dict[str, Any]]:
    source_dir = base.RUNS_DIR / source_run_id
    worker_dir = source_dir / "workers"
    if not worker_dir.exists():
        raise RuntimeError(f"No workers directory found for {source_run_id}: {worker_dir}")

    expected = {spec.slug for spec in parallel.DOMAINS}
    results: dict[str, dict[str, Any]] = {}
    for slug in sorted(expected):
        path = worker_dir / f"{slug}.json"
        if not path.exists():
            raise RuntimeError(
                f"Cannot recover {source_run_id}: missing completed worker {path.name}."
            )
        results[slug] = json.loads(path.read_text(encoding="utf-8"))

    extras = sorted(
        p.stem for p in worker_dir.glob("*.json") if p.stem not in expected
    )
    if extras:
        print("Ignoring non-domain worker JSON files: " + ", ".join(extras))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recover a failed parallel reconciliation by reusing all preserved "
            "successful domain worker outputs instead of rerunning Claude."
        )
    )
    parser.add_argument("--source-run-id", required=True)
    args = parser.parse_args()

    source_run_id = args.source_run_id
    results = load_workers(source_run_id)
    payload, diagnostics = parallel.merge_workers(results)

    run_paths = base.create_run_paths()
    new_worker_dir = run_paths["run_dir"] / "workers"
    new_worker_dir.mkdir(parents=True, exist_ok=False)
    source_worker_dir = base.RUNS_DIR / source_run_id / "workers"
    for spec in parallel.DOMAINS:
        shutil.copy2(
            source_worker_dir / f"{spec.slug}.json",
            new_worker_dir / f"{spec.slug}.json",
        )

    diagnostics["recovery"] = {
        "recovered_from_run_id": source_run_id,
        "reused_worker_count": len(results),
        "claude_workers_rerun": False,
        "reason": (
            "The source run completed all domain workers but failed semantic "
            "validation because a worker emitted a non-specific repository "
            "container root as evidence."
        ),
    }
    base.save_new_json(
        run_paths["run_dir"] / "PARALLEL_MERGE_DIAGNOSTICS.json",
        diagnostics,
    )
    base.save_new_json(
        run_paths["run_dir"] / "PARALLEL_MERGED_CANDIDATE.raw.json",
        payload,
    )
    base.save_new_json(run_paths["raw"], payload)

    removed_roots = strip_non_evidence_roots(payload)
    if removed_roots:
        print(
            "Removed non-specific repository container-root evidence: "
            + ", ".join(removed_roots)
        )

    removed_forbidden = base.sanitize_forbidden_evidence(payload)
    if removed_forbidden:
        print(
            "Removed forbidden reconciliation evidence before semantic validation: "
            + ", ".join(removed_forbidden)
        )

    base.repair_missing_dependency_references(payload)
    base.run_semantic_validation(payload)

    delta = base.build_proposed_graph_delta(
        payload,
        run_id=run_paths["run_id"],
        created_at_utc=run_paths["created_at_utc"],
    )

    base.save_new_json(run_paths["json"], payload)
    base.save_new_text(run_paths["markdown"], base.render_markdown(payload))
    base.save_new_json(run_paths["delta_json"], delta)
    base.save_new_text(
        run_paths["delta_markdown"],
        base.render_graph_delta_markdown(delta),
    )

    base.write_latest_pointer(run_paths)
    base.write_current_view(
        source_reconciliation_run_id=run_paths["run_id"],
        status="unverified_reconciliation",
        candidate_json=run_paths["json"],
        candidate_markdown=run_paths["markdown"],
        delta_json=run_paths["delta_json"],
        delta_markdown=run_paths["delta_markdown"],
    )

    print()
    print("=" * 72)
    print("PARALLEL RECONCILIATION RECOVERED")
    print("=" * 72)
    print(f"Source failed run : {source_run_id}")
    print(f"Recovered run     : {run_paths['run_id']}")
    print(f"Workers reused    : {len(results)} / {len(parallel.DOMAINS)}")
    print("Claude reruns     : 0")
    print(f"Root evidence removed: {len(removed_roots)}")
    print(f"Saved             : {run_paths['markdown'].relative_to(base.ROOT)}")
    print("Tasks/*.yaml was not modified.")
    print("=" * 72)

    base.print_summary(payload, run_paths, delta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
