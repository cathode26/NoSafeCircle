#!/usr/bin/env python3
"""Pure/component regressions for the TaskExecution/AgentRuntime boundary."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.agent_runner import AgentRunner
from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.contracts import (
    AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
    AgentInvocationRequest,
    Budgets,
    ContractValidationError,
    WriteBoundaries,
)
from Pipeline.AgentRuntime.providers.base import ProviderInvocationResponse
from Pipeline.TaskExecution.contracts import (
    TASK_EXECUTION_REQUEST_SCHEMA_VERSION,
    TaskContractIdentity,
    TaskExecutionRequest,
)
from Pipeline.TaskExecution.task_runner import TaskExecutionRunner


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
    "additionalProperties": False,
}


def invocation(run_id: str = "task-execution-001") -> AgentInvocationRequest:
    return AgentInvocationRequest(
        AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
        run_id,
        "implementer",
        "Perform one bounded task-associated invocation.",
        ("Pipeline/TaskExecution",),
        ("repository_read",),
        WriteBoundaries((), ()),
        OUTPUT_SCHEMA,
        "standard",
        Budgets(3, 10),
        "fake-default",
    )


def request(**changes: Any) -> TaskExecutionRequest:
    values = {
        "schema_version": TASK_EXECUTION_REQUEST_SCHEMA_VERSION,
        "task_id": "NSC-003",
        "task_contract_identity": TaskContractIdentity(
            "Tasks/NSC-003.yaml", 2, "a" * 64
        ),
        "invocation": invocation(),
    }
    values.update(changes)
    return TaskExecutionRequest(**values)


def rejects(callable_: Any, exception: type[BaseException] = ValueError) -> None:
    try:
        callable_()
    except exception:
        return
    raise AssertionError("expected rejection")


class RecordingProvider:
    provider_identifier = "fake"

    def __init__(self) -> None:
        self.received: AgentInvocationRequest | None = None

    def invoke(
        self, candidate: AgentInvocationRequest, model: str
    ) -> ProviderInvocationResponse:
        self.received = candidate
        assert model == "fake-standard"
        return ProviderInvocationResponse({"message": "ok"}, "task fake log\n")


def configuration() -> RuntimeConfiguration:
    return RuntimeConfiguration(
        {
            "fake-default": {
                "provider": "fake",
                "models": {
                    "low_cost": "fake-low",
                    "standard": "fake-standard",
                    "high_reasoning": "fake-high",
                },
            }
        }
    )


def test_contract_validation_and_round_trip() -> None:
    candidate = request()
    assert TaskExecutionRequest.from_dict(candidate.to_dict()) == candidate
    rejects(
        lambda: TaskExecutionRequest.from_dict(
            {**candidate.to_dict(), "authoritative": True}
        )
    )
    for bad_id in ("NSC-3", "nsc-003", "ARCH-003"):
        rejects(lambda bad_id=bad_id: request(task_id=bad_id))
    rejects(
        lambda: request(
            task_contract_identity=TaskContractIdentity(
                "Tasks/NSC-004.yaml", 2, "a" * 64
            )
        )
    )
    rejects(lambda: TaskContractIdentity("Tasks/NSC-003.yaml", 0, "a" * 64))
    rejects(lambda: TaskContractIdentity("Tasks/NSC-003.yaml", 1, "A" * 64))
    rejects(lambda: request(invocation=object()), ContractValidationError)
    assert set(candidate.to_dict()).isdisjoint(
        {"ready", "authorized", "conformant", "complete", "delivered"}
    )


def test_exact_delegation_and_separate_audit_artifacts() -> None:
    provider = RecordingProvider()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        agent_root = root / "agent-runs"
        task_root = root / "task-runs"
        agent_runner = AgentRunner(agent_root, configuration(), {"fake": provider})
        runner = TaskExecutionRunner(task_root, agent_runner)
        candidate = request()
        result = runner.run(candidate)

        assert result.status == "succeeded"
        assert provider.received is candidate.invocation
        task_value = json.loads(
            (task_root / candidate.invocation.run_id / "task_request.json").read_text(
                "utf-8"
            )
        )
        generic_value = json.loads(
            (agent_root / candidate.invocation.run_id / "request.json").read_text(
                "utf-8"
            )
        )
        assert TaskExecutionRequest.from_dict(task_value) == candidate
        assert task_value["task_id"] == "NSC-003"
        assert task_value["task_contract_identity"]["path"] == "Tasks/NSC-003.yaml"
        assert "task_id" not in generic_value
        assert "task_contract_identity" not in generic_value
        assert AgentInvocationRequest.from_dict(generic_value) == candidate.invocation
        rejects(lambda: runner.run(candidate), FileExistsError)


def test_dependency_direction() -> None:
    code = (
        "import sys; import Pipeline.AgentRuntime; "
        "assert not any(name == 'Pipeline.TaskExecution' or "
        "name.startswith('Pipeline.TaskExecution.') for name in sys.modules)"
    )
    subprocess.run([sys.executable, "-S", "-c", code], cwd=ROOT, check=True)


def main() -> None:
    status_before = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    test_contract_validation_and_round_trip()
    test_exact_delegation_and_separate_audit_artifacts()
    test_dependency_direction()
    status_after = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert status_before == status_after, "TaskExecution tests modified repository files"
    print("TaskExecution smoke test: PASS (task/generic boundary regressions)")


if __name__ == "__main__":
    main()
