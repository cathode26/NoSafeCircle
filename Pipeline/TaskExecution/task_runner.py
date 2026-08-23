"""Thin task-identity wrapper around one generic AgentRuntime invocation."""

from __future__ import annotations

from pathlib import Path

from Pipeline.AgentRuntime.agent_runner import AgentRunner, _json, _publish
from Pipeline.AgentRuntime.contracts import AgentResult, ContractValidationError

from .contracts import TaskExecutionRequest


class TaskExecutionRunner:
    def __init__(self, task_run_root: Path, agent_runner: AgentRunner) -> None:
        self.task_run_root = Path(task_run_root)
        if type(agent_runner) is not AgentRunner:
            raise ContractValidationError("agent_runner must be an exact AgentRunner")
        self.agent_runner = agent_runner

    def run(self, request: TaskExecutionRequest) -> AgentResult:
        if type(request) is not TaskExecutionRequest:
            raise ContractValidationError(
                "request must be an exact TaskExecutionRequest"
            )
        task_run_dir = self.task_run_root / request.invocation.run_id
        task_run_dir.mkdir(parents=True, exist_ok=False)
        try:
            _publish(
                task_run_dir / "task_request.json",
                _json(TaskExecutionRequest.to_dict(request)),
            )
        except BaseException:
            try:
                task_run_dir.rmdir()
            except OSError:
                pass
            raise
        return self.agent_runner.run(request.invocation)
