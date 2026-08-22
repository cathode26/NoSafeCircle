from __future__ import annotations

import json
import tempfile
from pathlib import Path

from task_contract_quality_audit import audit_contracts


def write_contract(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def contract(task_id: str, *, duplicate: bool = False, future_gate: bool = False) -> dict:
    acceptance = [
        {
            "criterion_id": "AC-001",
            "reference": "GDD",
            "requirement": "Expose an owner-controlled gameplay suspend interface that immediately halts active movement and rejects new movement commands.",
        }
    ]
    if duplicate:
        acceptance.append(
            {
                "criterion_id": "AC-002",
                "reference": "GDD duplicate wording",
                "requirement": "Expose an owner controlled gameplay-suspend interface which immediately stops active movement and rejects new movement commands.",
            }
        )

    gate_requirement = "Play Mode validation confirms movement stops when gameplay is suspended."
    if future_gate:
        gate_requirement = (
            "Validate that the pointer target is consumed by Door Interaction once that system exists."
        )

    return {
        "schema_version": "2.0",
        "id": task_id,
        "contract_revision": 1,
        "contract_disposition": "active",
        "title": task_id,
        "reconciliation_key": task_id.lower(),
        "kind": "implementation",
        "type": "implementation",
        "execution_scope": "single_agent",
        "execution_reason": "test",
        "decomposition_state": "concrete",
        "decomposition_reason": "test",
        "parent": "",
        "depends_on": [],
        "exclusive_resources": [],
        "acceptance_criteria": acceptance,
        "completion_gates": [
            {
                "gate_id": "VAL-001",
                "reference": "test",
                "requirement": gate_requirement,
            }
        ],
        "downstream_integration_obligations": [],
        "gdd_evidence": [],
        "basis": "direct_gdd",
        "source_scope": "required",
        "confidence": "high",
        "notes": "",
        "repository_state_at_bootstrap": "missing",
        "repository_evidence_at_bootstrap": [],
        "provenance": {"origin": "test"},
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="task-contract-quality-") as temp_dir:
        tasks_dir = Path(temp_dir) / "Tasks"
        write_contract(tasks_dir / "NSC-001.yaml", contract("NSC-001"))
        write_contract(
            tasks_dir / "NSC-002.yaml",
            contract("NSC-002", duplicate=True, future_gate=True),
        )

        audit = audit_contracts(tasks_dir)
        assert audit.contract_count == 2
        assert len(audit.duplicate_acceptance_findings) == 1
        assert len(audit.future_gate_findings) == 1

        duplicate = audit.duplicate_acceptance_findings[0]
        assert duplicate.task_id == "NSC-002"
        assert duplicate.entry_ids == ("AC-001", "AC-002")

        future = audit.future_gate_findings[0]
        assert future.task_id == "NSC-002"
        assert future.entry_ids == ("VAL-001",)

    print("task_contract_quality_audit_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
