from __future__ import annotations

from types import SimpleNamespace

from execution_authority import (
    CURRENT_REASON_CODE,
    UnsafeExecutionAuthorizationError,
    assess_execution_authorization,
    require_execution_authorization,
)
from taskcontrol import advisory_ready_tasks, ready_tasks


class FakeGraph:
    def __init__(self, tasks: list[dict]) -> None:
        self.plan = SimpleNamespace(tasks=tuple(tasks))
        self.tasks_by_id = {task["id"]: task for task in tasks}
        self.tasks_by_key = {task["reconciliation_key"]: task for task in tasks}
        self.validation = SimpleNamespace(task_schema_version="2.0")


def main() -> int:
    task = {
        "schema_version": "2.0",
        "id": "NSC-003",
        "reconciliation_key": "candidate",
        "title": "Candidate",
        "contract_revision": 1,
        "contract_disposition": "active",
        "kind": "implementation",
        "execution_scope": "single_agent",
        "depends_on": [],
    }
    graph = FakeGraph([task])
    assert advisory_ready_tasks(graph) == []
    assessment = assess_execution_authorization(task)
    assert assessment.authorized is False
    assert assessment.reason_code == CURRENT_REASON_CODE
    assert CURRENT_REASON_CODE == "evidence_derived_dispatch_policy_not_enabled"
    assert "State inspection alone never authorizes execution" in assessment.message
    try:
        require_execution_authorization(task)
    except UnsafeExecutionAuthorizationError as exc:
        assert CURRENT_REASON_CODE in str(exc)
    else:
        raise AssertionError("Expected authorization to fail closed.")
    try:
        ready_tasks(graph)
    except UnsafeExecutionAuthorizationError:
        pass
    else:
        raise AssertionError("Expected ready_tasks to remain disabled.")

    # Even an injected legacy status cannot create authority.
    task["status"] = "complete"
    edited_assessment = assess_execution_authorization(task)
    assert edited_assessment.authorized is False
    assert edited_assessment.reason_code == CURRENT_REASON_CODE

    print("phase1_execution_authority_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
