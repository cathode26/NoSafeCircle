from __future__ import annotations

from pathlib import Path

import reconciliation_agent as recon
import verification_crew as verify

ROOT = Path(__file__).resolve().parents[2]


def check_provenance_guard() -> None:
    clean = {
        "summary": {
            "major_findings": [
                "Derived from GDD Shared Context and Coordination Rules plus current builder behavior."
            ]
        },
        "seed_assessment": {
            "status": "ready",
            "blockers": [],
            "warnings": [],
        },
    }
    recon.sanitize_non_authoritative_summary_provenance(clean)
    recon.validate_reconciliation_provenance(clean)

    # Regression from fresh run 20260821T180232Z-5668749f: the substantive
    # package finding was valid, but the worker accidentally named an internal
    # pipeline-hardening label in disposable summary prose. That must not throw
    # away the entire nine-worker run.
    summary_slip = {
        "summary": {
            "major_findings": [
                "Neither approved package is installed. Per the GDD's verification-hardening guidance, this is concrete missing configuration work."
            ]
        },
        "seed_assessment": {
            "status": "ready",
            "blockers": [],
            "warnings": [],
        },
    }
    removed = recon.sanitize_non_authoritative_summary_provenance(summary_slip)
    assert len(removed) == 1
    assert summary_slip["summary"]["major_findings"] == []
    assert summary_slip["seed_assessment"]["warnings"]
    recon.normalize_seed_assessment_consistency(summary_slip)
    assert summary_slip["seed_assessment"]["status"] == "ready_with_warnings"
    recon.validate_reconciliation_provenance(summary_slip)

    # Authoritative graph/evidence contamination remains a hard failure.
    authoritative_contamination = {
        "work_items": [
            {
                "gdd_evidence": [
                    {
                        "reference": "CLAUDE.md",
                        "requirement": "CLAUDE.md explicitly requires this lock.",
                    }
                ]
            }
        ]
    }
    try:
        recon.validate_reconciliation_provenance(authoritative_contamination)
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "Authoritative CLAUDE.md provenance contamination was not rejected."
        )


def check_seed_assessment_normalization() -> None:
    payload = {
        "unresolved_questions": [
            {
                "question": "Example unresolved review question",
                "affects_keys": [],
                "why_unresolved": "Example",
                "recommended_resolution": "human_review",
            }
        ],
        "seed_assessment": {
            "status": "ready_with_warnings",
            "blockers": [],
            "warnings": [],
        },
    }
    recon.normalize_seed_assessment_consistency(payload)
    seed = payload["seed_assessment"]
    assert seed["status"] == "ready_with_warnings"
    assert seed["warnings"], "Unresolved review state must produce a warning detail."
    recon._validate_seed_assessment_consistency(payload)

    clean_payload = {
        "unresolved_questions": [],
        "seed_assessment": {
            "status": "ready_with_warnings",
            "blockers": [],
            "warnings": [],
        },
    }
    recon.normalize_seed_assessment_consistency(clean_payload)
    assert clean_payload["seed_assessment"]["status"] == "ready"
    recon._validate_seed_assessment_consistency(clean_payload)


def check_coverage_metadata_boundary() -> None:
    audit = {
        "agent": "Coverage — Global Pipeline",
        "requested_model": "sonnet",
        "result": {
            "requirements": [
                {
                    "requirement_id": "R24",
                    "reference": "Pipeline/candidate self-assessment metadata",
                    "requirement": "seed_assessment should accurately reflect candidate warnings.",
                    "classification": "required_process",
                    "representation": "ambiguous",
                    "mapped_keys": [],
                    "mapped_non_code_titles": [],
                    "explanation": "Candidate bookkeeping consistency observation.",
                }
            ]
        },
    }
    findings = verify.deterministic_audit_checks([audit])
    assert len(findings) == 1
    finding = findings[0]["finding"]
    assert finding["severity"] == "warning"
    assert finding["category"] == "other"
    assert finding["finding_id"].startswith("deterministic-non-gdd-row-")


def check_required_representation_suggestion_refinement() -> None:
    # Regression from verification 20260821T182902Z-47b58eb5: Pass 1 noticed
    # the Frost/Ranged attack-preservation gap but graded it suggestion-level,
    # so the Refiner skipped it and Pass 2 promoted the same gap to an error.
    coverage_suggestion = {
        "source_agent": "Coverage — Enemy State",
        "finding": {
            "severity": "suggestion",
            "category": "requirement_representation_problem",
        },
    }
    assert verify.is_refiner_relevant_report(coverage_suggestion)

    ordinary_suggestion = {
        "source_agent": "Evidence — World Run Delivery",
        "finding": {
            "severity": "suggestion",
            "category": "evidence_problem",
        },
    }
    assert not verify.is_refiner_relevant_report(ordinary_suggestion)


def check_repository_metadata_boundary() -> None:
    # Regression from reconciliation 20260821T191952Z-12fa2f4a: the global
    # pipeline worker legitimately inspected .gitignore to establish that
    # UserSettings/ is excluded from committed project state. The boundary
    # should allow that one exact metadata file without opening arbitrary roots.
    assert recon._is_allowed_review_path(".gitignore")
    assert recon._is_allowed_review_path("./.gitignore")
    assert not recon._is_allowed_review_path("README.md")
    assert not recon._is_allowed_review_path("CLAUDE.md")


def check_prompt_closure() -> None:
    reconcile_prompt = (
        ROOT / "Pipeline" / "Reconciliation" / "prompts" / "reconcile.md"
    ).read_text(encoding="utf-8")
    normalized_reconcile_prompt = " ".join(reconcile_prompt.split())
    coverage_prompt = (
        ROOT
        / "Pipeline"
        / "Reconciliation"
        / "prompts"
        / "verification"
        / "coverage_auditor.md"
    ).read_text(encoding="utf-8")

    assert "2026-08-21 FRESH RUN CLOSURE" in reconcile_prompt
    assert "gameplay-navigation-locomotion" in reconcile_prompt
    assert "Current prototype scene-builder exclusive-write lock" in reconcile_prompt
    assert "requirements` array is a map of **actual current-GDD requirements only**" in coverage_prompt
    assert "`verification-hardening`" not in reconcile_prompt

    assert "2026-08-21 FINAL MATERIAL CONVERGENCE" in reconcile_prompt
    assert "current GDD does not require the camera to follow the player" in reconcile_prompt
    assert "does not suppress, pause, or slow Ranged Enemy attack execution" in reconcile_prompt
    assert "Explicit representation, not evidence-only coverage" in coverage_prompt

    assert "CURRENT REPOSITORY METADATA BOUNDARY 2026-08-21" in reconcile_prompt
    assert "`/.gitignore` is an approved current-project metadata source only" in reconcile_prompt
    assert (
        "No other root-level repository metadata file is approved by this exception"
        in normalized_reconcile_prompt
    )


def main() -> int:
    check_provenance_guard()
    check_seed_assessment_normalization()
    check_coverage_metadata_boundary()
    check_required_representation_suggestion_refinement()
    check_repository_metadata_boundary()
    check_prompt_closure()
    print("fresh_run_closure_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
