from __future__ import annotations

import argparse
import copy
import json
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


FABRICATED_OWNER_PHRASE = "Enemy archetype prefab composition must have an owner"
FABRICATED_HARDENING_PHRASE = "verification-hardening"

LOCK_EVIDENCE = (
    "Derived scheduling rationale from GDD §5 Agent Coordination: tasks that share "
    "gameplay files or Unity assets must not modify them simultaneously; these enemy "
    "work items share the enemy locomotion/behavior surface."
)
ARCHETYPE_DEP_EVIDENCE = (
    "Derived from GDD §3 Dungeon Floor Structure and §4 Dungeon Encounter Agent: "
    "Chapel of Ash and the Final Room use mixed Melee/Ranged compositions, so encounter "
    "content authoring consumes the concrete enemy archetype work items it places."
)


def append_unique_by_content(sequence: list[dict[str, Any]], value: dict[str, Any]) -> bool:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False)
    if any(json.dumps(existing, sort_keys=True, ensure_ascii=False) == encoded for existing in sequence):
        return False
    sequence.append(copy.deepcopy(value))
    return True


def item_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("key", "")): item
        for item in payload.get("work_items", [])
        if str(item.get("key", "")).strip()
    }


def repair_fabricated_evidence(payload: dict[str, Any], changes: list[str]) -> None:
    items = item_map(payload)

    melee = items["melee-enemy"]
    before = len(melee.get("gdd_evidence", []))
    melee["gdd_evidence"] = [
        evidence
        for evidence in melee.get("gdd_evidence", [])
        if FABRICATED_OWNER_PHRASE not in str(evidence.get("reference", ""))
        and FABRICATED_OWNER_PHRASE not in str(evidence.get("requirement", ""))
    ]
    if len(melee["gdd_evidence"]) != before:
        changes.append("Removed fabricated CLAUDE.md ownership quotation from melee-enemy.gdd_evidence.")

    archetype_reference = (
        "Required Enemy Roster + 2.5D Isometric Visual and World Representation / Runtime Implementation"
    )
    for key, label in (("melee-enemy", "Melee"), ("ranged-enemy", "Ranged")):
        item = items[key]
        for criterion in item.get("acceptance_criteria", []):
            text = str(criterion.get("reference", "")) + " " + str(criterion.get("requirement", ""))
            if FABRICATED_OWNER_PHRASE in text:
                criterion["reference"] = archetype_reference
                criterion["requirement"] = (
                    f"Delivers a usable assembled {label} Enemy archetype that combines its required "
                    "archetype behavior with the shared pursuit/locomotion, Enemy Health/Defeat, "
                    "Active Enemy Registry participation, and world-space SpriteRenderer presentation "
                    "consumed by encounter content."
                )
                changes.append(f"Replaced fabricated ownership citation on {key}.acceptance_criteria.")

    dungeon = items["dungeon-encounter-content-authoring"]
    for dependency in dungeon.get("depends_on", []):
        if str(dependency.get("key", "")) not in {"melee-enemy", "ranged-enemy"}:
            continue
        if FABRICATED_OWNER_PHRASE in str(dependency.get("evidence", "")):
            dependency["evidence"] = ARCHETYPE_DEP_EVIDENCE
            changes.append(
                f"Replaced fabricated CLAUDE.md dependency evidence for dungeon-encounter-content-authoring -> {dependency['key']}."
            )

    for key in (
        "enemy-pursuit-search-foundation",
        "melee-enemy",
        "ranged-enemy",
        "locked-door-enemy-attack",
    ):
        for resource in items[key].get("exclusive_resources", []):
            evidence = str(resource.get("evidence", ""))
            if FABRICATED_HARDENING_PHRASE in evidence:
                resource["evidence"] = LOCK_EVIDENCE
                changes.append(f"Replaced fabricated verification-hardening lock evidence on {key}.")


def add_melee_clustering_coverage(payload: dict[str, Any], changes: list[str]) -> None:
    melee = item_map(payload)["melee-enemy"]
    criterion = {
        "reference": "Spell and Enemy Interactions — Charged Fireball / Frost Field vs Melee Enemies",
        "requirement": (
            "When multiple Melee Enemies pursue the wizard, ordinary pursuit/avoidance allows them "
            "to naturally cluster enough that Charged Fireball area damage and Frost Field formation "
            "stretching remain meaningful; exact avoidance/separation tuning remains a playtesting detail."
        ),
    }
    validation = {
        "reference": "Spell and Enemy Interactions — Charged Fireball / Frost Field vs Melee Enemies",
        "requirement": (
            "Play Mode validation with multiple simultaneously pursuing Melee Enemies confirms that "
            "their locomotion does not enforce separation that removes the GDD's natural-clustering "
            "premise; the group can still form meaningful Fireball/Frost Field targets."
        ),
    }
    if append_unique_by_content(melee.setdefault("acceptance_criteria", []), criterion):
        changes.append("Added melee multi-pursuer natural-clustering acceptance coverage.")
    if append_unique_by_content(melee.setdefault("validation_requirements", []), validation):
        changes.append("Added melee multi-pursuer clustering Play Mode validation.")


def add_stub_scene_pipeline_constraint(payload: dict[str, Any], changes: list[str]) -> None:
    title = "Non-canonical stub scene preservation requires human decision"
    existing = {
        str(record.get("title", "")): record
        for record in payload.setdefault("non_code_requirements", [])
    }
    record = {
        "title": title,
        "requirement_type": "pipeline_constraint",
        "status": "confirmed",
        "gdd_evidence": [
            {
                "reference": "Current Prototype Scene Evidence",
                "requirement": (
                    "Deletion, retention, or repurposing of the non-canonical stub scenes is a human "
                    "decision; agents and reconciliation steps must not delete or reinterpret them merely "
                    "to make scene inventory evidence cleaner."
                ),
            }
        ],
        "evidence": (
            "The current GDD explicitly reserves deletion, retention, and repurposing of "
            "Assets/Scenes/DoorPrototype.unity and Assets/Scenes/SampleScene.unity to human decision."
        ),
    }
    if title not in existing:
        payload["non_code_requirements"].append(record)
        changes.append("Added typed pipeline constraint protecting non-canonical stub scenes.")
    elif existing[title] != record:
        existing[title].clear()
        existing[title].update(record)
        changes.append("Normalized existing non-canonical stub-scene pipeline constraint.")


def apply_round3_corrections(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    corrected = copy.deepcopy(payload)
    changes: list[str] = []
    repair_fabricated_evidence(corrected, changes)
    add_melee_clustering_coverage(corrected, changes)
    add_stub_scene_pipeline_constraint(corrected, changes)
    return corrected, changes


def load_audits(directory: Path) -> list[dict[str, Any]]:
    files = sorted(directory.glob("*.json"))
    audits = [base.load_json(path) for path in files]
    if len(audits) != len(parallel.SPECS):
        raise RuntimeError(
            f"Expected {len(parallel.SPECS)} completed auditor artifacts in {directory}; found {len(audits)}."
        )
    audits.sort(key=lambda item: str(item.get("agent", "")))
    return audits


def copy_baseline_audits(audits: list[dict[str, Any]], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    by_agent = {str(audit.get("agent", "")): audit for audit in audits}
    for spec in parallel.SPECS:
        audit = by_agent.get(spec.agent_name)
        if audit is None:
            raise RuntimeError(f"Missing baseline audit for {spec.agent_name}.")
        base.save_new_json(target / f"{spec.key}.json", audit)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Continue a completed verification from its refined candidate, apply the three "
            "confirmed round-3 corrections, and rerun only affected auditors."
        )
    )
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--verification-run-id", required=True)
    args = parser.parse_args()

    source_run_id = args.source_run_id
    prior_dir = base.verification_root(source_run_id) / args.verification_run_id
    baseline_candidate = prior_dir / "refined_candidate.json"
    baseline_pass2 = prior_dir / "pass2"
    assignments_path = prior_dir / "MODEL_ASSIGNMENTS.json"
    for required in (baseline_candidate, baseline_pass2, assignments_path):
        if not required.exists():
            raise FileNotFoundError(required)

    baseline_payload = base.load_json(baseline_candidate)
    baseline_audits = load_audits(baseline_pass2)
    baseline_merged = base.merge_findings(baseline_audits)
    assignments = base.load_json(assignments_path)

    corrected_payload, changes = apply_round3_corrections(baseline_payload)
    if not changes:
        raise RuntimeError("Round-3 continuation found nothing to correct.")

    raw_probe = copy.deepcopy(corrected_payload)
    parallel.sanitize_forbidden_evidence(raw_probe)
    base.sanitize_refiner_input_tracking(raw_probe)
    parallel.repair_missing_dependency_references(raw_probe)
    parallel.run_semantic_validation(raw_probe)
    corrected_payload = raw_probe

    paths = base.create_verification_paths(source_run_id)
    copy_baseline_audits(baseline_audits, paths["pass1_dir"])
    base.save_new_json(paths["merged_pass1"], baseline_merged)
    base.save_new_json(paths["refined_raw"], corrected_payload)
    base.save_new_json(paths["refined_json"], corrected_payload)
    base.save_new_text(paths["refined_markdown"], parallel.render_markdown(corrected_payload))
    base.save_new_json(
        paths["run_dir"] / "ROUND3_CORRECTIONS.json",
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

    selected_keys = parallel.changed_audit_keys(baseline_payload, corrected_payload)
    selected_keys.update(
        {
            "coverage_enemy_behavior",
            "coverage_world_foundations",
            "coverage_global_pipeline",
            "evidence_enemy_encounters",
            "structure_dependencies",
            "structure_resources",
        }
    )
    selected_specs = [spec for spec in parallel.SPECS if spec.key in selected_keys]

    pass2_assignments = assignments.get("pass2", {})
    missing = [spec.key for spec in selected_specs if spec.key not in pass2_assignments]
    if missing:
        raise RuntimeError(f"Prior MODEL_ASSIGNMENTS lacks models for affected auditors: {missing}")

    print()
    print("=" * 72)
    print("ROUND 3 TARGETED VERIFICATION CONTINUATION")
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
        pass_label="round3-targeted",
        output_dir=paths["pass2_dir"],
        assignments=pass2_assignments,
    )

    final_audits = parallel.final_audit_set(
        pass1_audits=baseline_audits,
        rerun_audits=rerun_audits,
        selected_keys=selected_keys,
    )
    final_merged = base.merge_findings(final_audits)
    final_merged["selective_pass2"] = {
        "enabled": True,
        "round3_continuation": True,
        "rerun_auditor_count": len(selected_specs),
        "total_auditor_count": len(parallel.SPECS),
        "rerun_keys": sorted(selected_keys),
        "reuse_policy": (
            "The completed prior Pass 2 is the baseline. Only auditors affected by the three "
            "confirmed round-3 corrections are rerun; unaffected prior Pass-2 results are reused."
        ),
    }
    base.save_new_json(paths["merged_pass2"], final_merged)

    status = base.status_from_pass2(final_merged)
    model_assignments = copy.deepcopy(assignments)
    model_assignments["schema_version"] = "2.2-round3-continuation"
    model_assignments["continued_from_verification_run_id"] = args.verification_run_id
    model_assignments["pass2"] = {
        key: pass2_assignments[key] for key in sorted(selected_keys)
    }
    base.save_new_json(paths["model_assignments"], model_assignments)

    summary = {
        "schema_version": "2.2-round3-continuation",
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
            "version": "2.2-round3-continuation",
            "reused_completed_pass2_auditors": len(parallel.SPECS) - len(selected_specs),
            "targeted_rerun_auditors": len(selected_specs),
        },
        "model_assignments": {
            "pass1": "reused completed Pass 2 from prior verification",
            "refiner": "deterministic round-3 confirmed corrections",
            "pass2": {key: pass2_assignments[key] for key in sorted(selected_keys)},
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
    print("ROUND 3 TARGETED VERIFICATION COMPLETE")
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
