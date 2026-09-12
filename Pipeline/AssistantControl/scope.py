"""Assistant-owned persistence for an explicit, bounded task scope."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import (
    ExecutionScopePlan,
    TaskReviewContractError,
    validate_task_id,
)
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
from Pipeline.TaskReviewAgent.pipeline_scope import RepositoryScopeAuthority

from .checkouts import Checkouts, write_record


class ScopePlanningError(ValueError):
    """A scope could not be safely validated or recorded."""


_HEX_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
_UNDERWAY_STATUSES = {
    "working", "running", "executing", "stopping", "candidate", "reviewing",
    "integrating", "integrated", "approved", "changes_requested",
}


def _plan_from_input(value: ExecutionScopePlan | Mapping[str, Any]) -> ExecutionScopePlan:
    if isinstance(value, ExecutionScopePlan):
        return value
    try:
        return ExecutionScopePlan.from_dict(value)
    except (TaskReviewContractError, TypeError, KeyError) as exc:
        raise ScopePlanningError(f"invalid execution scope plan: {exc}") from exc


class AssistantScopePlanner:
    """Validate and persist scope for an already-owned prepared checkout."""

    def __init__(self, checkouts: Checkouts):
        self.checkouts = checkouts

    def _path(self, task_id: str) -> Path:
        return self.checkouts.records / f"{validate_task_id(task_id)}.json"

    def _owned_record(self, task_id: str) -> tuple[Path, dict[str, Any]]:
        path = self._path(task_id)
        if not path.is_file():
            raise ScopePlanningError("task checkout record does not exist")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ScopePlanningError("task checkout record is unreadable") from exc
        expected_checkout = self.checkouts.root / task_id
        if (record.get("source") != str(self.checkouts.source)
                or record.get("task_id") != task_id
                or record.get("checkout") != str(expected_checkout)):
            raise ScopePlanningError("task checkout record identity differs")
        return path, record

    @staticmethod
    def _worker_underway(record: Mapping[str, Any]) -> bool:
        return (record.get("status") in _UNDERWAY_STATUSES
                or record.get("worker") is not None
                or record.get("candidate") is not None)

    def validate_and_persist(
        self,
        task_id: str,
        plan: ExecutionScopePlan | Mapping[str, Any],
        *,
        lease_id: str,
    ) -> dict[str, Any]:
        task_id = validate_task_id(task_id)
        if type(lease_id) is not str or not lease_id.strip():
            raise ScopePlanningError("assistant scope planning requires a lease_id")
        requested = _plan_from_input(plan)
        with _exclusive_file_lock(self.checkouts.records / "checkouts.lock", timeout_seconds=10):
            record_path, record = self._owned_record(task_id)
            observation = self.checkouts.observe(task_id)
            source_commit = record.get("source_commit")
            if (not isinstance(source_commit, str) or not _HEX_COMMIT.fullmatch(source_commit)
                    or observation.get("current_commit") != source_commit):
                raise ScopePlanningError("task checkout is not at its pinned source commit")
            if record.get("status") not in {"prepared", "planned"}:
                raise ScopePlanningError("task checkout is not available for scope planning")
            if self._worker_underway(record):
                raise ScopePlanningError("worker or candidate work is already underway; previous scope preserved")
            task = load_committed_task(
                Path(record["checkout"]), task_id, commit=source_commit,
                expected_sha256=record.get("task_contract_sha256"),
            )
            authority = RepositoryScopeAuthority(
                checkout=record["checkout"], task=task, lease_id=lease_id.strip(),
                expected_branch=record["branch"],
                state_root=self.checkouts.records / ".scope-state",
            )
            validation = authority.validate(requested)
            if not validation.accepted:
                raise ScopePlanningError("invalid execution scope: " + "; ".join(validation.reasons))
            accepted = authority.accepted
            assert accepted is not None
            persisted = accepted.to_dict()
            record["scope"] = persisted
            write_record(record_path, record)
            return {
                "accepted": True,
                "plan_id": accepted.plan_id,
                "source_commit": accepted.source_head,
                "source_head": accepted.source_head,
                "task_contract_sha256": accepted.task_contract_sha256,
                "lease_id": accepted.lease_id,
                "plan": accepted.plan.to_dict(),
                "execution_authorized": False,
            }

    plan = validate_and_persist


def validate_and_persist_scope(
    checkouts: Checkouts,
    task_id: str,
    plan: ExecutionScopePlan | Mapping[str, Any],
    *,
    lease_id: str,
) -> dict[str, Any]:
    return AssistantScopePlanner(checkouts).validate_and_persist(
        task_id, plan, lease_id=lease_id
    )
