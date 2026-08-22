from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace

from execution_authority import (
    PHASE1_REASON_CODE,
    UnsafeExecutionAuthorizationError,
    assess_execution_authorization,
    require_execution_authorization,
)
from taskcontrol import (
    advisory_ready_tasks,
    command_authorize,
    command_ready,
    ready_tasks,
)


class FakeGraph:
    def __init__(self, tasks: list[dict]) -> None:
        self.plan = SimpleNamespace(tasks=tuple(tasks))
        self.tasks_by_id = {task["id"]: task for task in tasks}
        self.tasks_by_key = {task["reconciliation_key"]: task for task in tasks}


def make_task(
    task_id: str,
    key: str,
    *,
    status: str,
    kind: str = "implementation",
    execution_scope: str = "single_agent",
    depends_on: list[str] | None = None,
) -> dict:
    return {
        "id": task_id,
        "reconciliation_key": key,
        "title": key.replace("-", " ").title(),
        "status": status,
        "kind": kind,
        "execution_scope": execution_scope,
        "depends_on": list(depends_on or []),
    }


def main() -> int:
    dependency = make_task(
        "NSC-002",
        "dependency",
        status="open",
        kind="feature",
        execution_scope="not_applicable",
    )
    candidate = make_task(
        "NSC-003",
        "candidate",
        status="open",
        depends_on=["NSC-002"],
    )
    graph = FakeGraph([dependency, candidate])

    # Before the mutable YAML edit, the legacy advisory frontier is empty.
    assert advisory_ready_tasks(graph) == []

    # A one-line status edit can change the advisory calculation...
    dependency["status"] = "complete"
    assert [task["id"] for task in advisory_ready_tasks(graph)] == ["NSC-003"]

    # ...but it must never create execution authority.
    assessment = assess_execution_authorization(candidate)
    assert assessment.authorized is False
    assert assessment.reason_code == PHASE1_REASON_CODE

    try:
        require_execution_authorization(candidate)
    except UnsafeExecutionAuthorizationError as exc:
        assert PHASE1_REASON_CODE in str(exc)
    else:
        raise AssertionError("Expected Phase 1 authorization to fail closed.")

    # The old ambiguous API is intentionally unusable by a dispatcher.
    try:
        ready_tasks(graph)
    except UnsafeExecutionAuthorizationError as exc:
        assert "advisory_ready_tasks" in str(exc)
    else:
        raise AssertionError("Expected ready_tasks() to reject dispatch use.")

    ready_output = StringIO()
    with redirect_stdout(ready_output):
        assert command_ready(graph) == 0
    rendered_ready = ready_output.getvalue()
    assert "ADVISORY READY WORK" in rendered_ready
    assert "NOT AUTHORIZED FOR AUTONOMOUS DISPATCH" in rendered_ready
    assert "NSC-003" in rendered_ready

    authorize_output = StringIO()
    with redirect_stdout(authorize_output):
        assert command_authorize(graph, "NSC-003") == 2
    rendered_authorize = authorize_output.getvalue()
    assert "EXECUTION AUTHORIZATION: DENIED" in rendered_authorize
    assert PHASE1_REASON_CODE in rendered_authorize

    # Even changing the candidate itself to complete still does not authorize it.
    candidate["status"] = "complete"
    assert assess_execution_authorization(candidate).authorized is False

    print("phase1_execution_authority_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
