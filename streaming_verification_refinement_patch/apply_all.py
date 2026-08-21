from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

NORMALIZE_PATHS = [
    ROOT / "CLAUDE.md",
    ROOT / "Docs" / "GDD" / "No_Safe_Circle_GDD.md",
    ROOT / "Pipeline" / "Reconciliation" / "reconciliation_agent.py",
    ROOT / "Pipeline" / "Reconciliation" / "parallel_reconciliation_agent.py",
    ROOT / "Pipeline" / "Reconciliation" / "verification_crew.py",
    ROOT / "Pipeline" / "Reconciliation" / "parallel_verification_crew.py",
    ROOT / "Pipeline" / "Reconciliation" / "streaming_refinement_v2.py",
    ROOT / "Pipeline" / "Reconciliation" / "fresh_run_closure_smoke_test.py",
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "reconcile.md",
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "coverage_auditor.md",
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "refiner.md",
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "structure_auditor.md",
    ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "evidence_auditor.md",
    ROOT / "streaming_verification_refinement_patch" / "resume_streaming_verification.py",
    ROOT / "streaming_verification_refinement_patch" / "continue_round3_verification.py",
    ROOT / "streaming_verification_refinement_patch" / "continue_final_provenance_verification.py",
]


def run_script(name: str) -> None:
    path = HERE / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.main()
    if result not in (None, 0):
        raise RuntimeError(f"{name} failed with result {result}")


def normalize_lf() -> None:
    for path in NORMALIZE_PATHS:
        if not path.exists():
            continue
        data = path.read_bytes()
        normalized = data.replace(b"\r\n", b"\n")
        if normalized != data:
            path.write_bytes(normalized)


def main() -> int:
    run_script("apply_verified_closure_fixes.py")
    run_script("apply_frost_field_cursor_clarification.py")
    run_script("apply_reconciliation_evidence_guard.py")
    run_script("apply_round2_closure_fixes.py")
    run_script("apply_round3_closure_fixes.py")
    run_script("apply_final_provenance_guard.py")
    run_script("apply_fresh_run_closure_fixes.py")
    run_script("apply_summary_provenance_tolerance_fix.py")
    run_script("apply_streaming_verification_refinement.py")
    run_script("apply_streaming_refinement_v2.py")
    run_script("apply_streaming_v2_hardening.py")
    run_script("apply_streaming_v2_guidance.py")
    run_script("apply_streaming_v2_recovery_fix.py")
    run_script("apply_streaming_v2_semantic_list_dedupe.py")
    run_script("apply_streaming_v2_identity_order_fix.py")
    run_script("apply_deterministic_finding_identity_fix.py")
    run_script("apply_resume_verification_order_fix.py")
    run_script("apply_resume_deterministic_identity_remap.py")
    normalize_lf()
    print("All streaming verification + approved closure fixes are installed.")
    print("Clarified Frost Field placement at the shared cursor world target.")
    print("Installed reconciliation evidence-path precision guard.")
    print("Installed six round-2 verification closure rules.")
    print("Installed round-3 evidence integrity, melee-clustering, and stub-scene closure rules.")
    print("Installed final guard against verifier/patch bookkeeping labels being cited as project evidence.")
    print("Installed fresh-run provenance, navigation-lock, scene-builder-constraint, coverage-boundary, and seed-assessment fixes.")
    print("Non-authoritative summary provenance slips are now removed without weakening graph/evidence provenance checks.")
    print("Installed streaming refinement v2 field-level operations and clustered arbitration.")
    print("Hardened record-level remove/upsert conflict semantics.")
    print("Field repair workers inherit the standard Refiner correctness guidance.")
    print("Fixed streaming v2 recovery bookkeeping for derived in-progress artifacts.")
    print("Deduplicated depends_on/exclusive_resources additions and removals by durable key.")
    print("Identity-field renames now apply after other edits addressed to the immutable source identity.")
    print("Made deterministic coverage finding IDs globally unique by originating auditor.")
    print("Installed failed-verification resume support without rerunning Pass 1 repairs.")
    print("Fixed resume verification initialization order.")
    print("Resume now migrates preserved deterministic finding IDs to the global identity format.")
    print("Normalized patched text files to LF line endings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
