from __future__ import annotations

import verification_crew as base


def audit(agent: str) -> dict:
    return {
        "agent": agent,
        "requested_model": "test",
        "result": {
            "verdict": "pass_with_findings",
            "findings": [],
            "notes": [],
            "requirements": [
                {
                    "requirement_id": "R16",
                    "reference": "GDD test",
                    "requirement": f"Synthetic requirement for {agent}",
                    "classification": "required_process",
                    "representation": "acceptance_criterion",
                    "mapped_keys": ["no-safe-circle"],
                    "mapped_non_code_titles": [],
                    "explanation": "Synthetic collision test",
                }
            ],
        },
    }


def main() -> int:
    findings = base.deterministic_audit_checks(
        [audit("Coverage — Player Core"), audit("Coverage — Enemy State")]
    )
    ids = [entry["finding"]["finding_id"] for entry in findings]
    assert len(ids) == 2, ids
    assert len(set(ids)) == 2, ids
    assert any("coverage-player-core-r16" in value for value in ids), ids
    assert any("coverage-enemy-state-r16" in value for value in ids), ids
    print("deterministic_finding_identity_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
