"""Select a validated agent-ready Issue when a generic agent has no explicit task ID."""

from __future__ import annotations

from pathlib import Path

from .contracts import validate_task_id
from .issue_queue import repo_root
from .issue_workflow_store import GhIssueBackend, IssueWorkflowService, IssueWorkflowStoreError


class GenericSelectionError(IssueWorkflowStoreError):
    """Raised when generic durable-work selection cannot produce one task."""


def select_agent_ready_task(*, source: Path | str, worker_id: str) -> dict:
    root = repo_root(Path(source).resolve())
    service = IssueWorkflowService(
        backend=GhIssueBackend(source_root=root),
        task_loader=lambda task_id: {"id": task_id, "exclusive_resources": []},
        worker_id=worker_id,
    )
    ready = service.list_agent_ready()
    if not ready:
        raise GenericSelectionError(
            "No validated agent-ready Issue exists. Pass an explicit -TaskId to begin fresh "
            "work; generic resume never silently invents a new task."
        )
    selected = ready[0]
    state = selected.get("workflow_state")
    if not isinstance(state, dict):
        raise GenericSelectionError("agent-ready Issue omitted workflow_state")
    task_id = validate_task_id(state.get("task_id"))
    return {
        "selection_priority": "resume_agent_ready_before_new_task",
        "task_id": task_id,
        "issue_number": selected.get("issue_number"),
        "issue_url": selected.get("issue_url"),
        "phase": state.get("phase"),
        "branch": state.get("branch"),
        "commit": state.get("head_commit"),
        "human_result": state.get("human_result"),
        "agent_ready_count": len(ready),
    }
