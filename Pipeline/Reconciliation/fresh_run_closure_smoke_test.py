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


def check_prompt_closure() -> None:
    reconcile_prompt = (
        ROOT / "Pipeline" / "Reconciliation" / "prompts" / "reconcile.md"
    ).read_text(encoding="utf-8")
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


def main() -> int:
    check_provenance_guard()
    check_seed_assessment_normalization()
    check_coverage_metadata_boundary()
    check_prompt_closure()
    print("fresh_run_closure_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
