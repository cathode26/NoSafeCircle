from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CURRENT_REASON_CODE = "evidence_derived_dispatch_policy_not_enabled"
# Compatibility alias retained for the Phase 1 regression harness.
PHASE1_REASON_CODE = CURRENT_REASON_CODE
DENIAL_MESSAGE = (
    "Evidence-derived current-state inspection exists, but production delivery/revalidation "
    "evidence has not yet been proven on a real task and dependency-readiness and dispatch "
    "authorization policy are not enabled. State inspection alone never authorizes execution; "
    "zero tasks may be autonomously dispatched."
)


class UnsafeExecutionAuthorizationError(RuntimeError):
    """Raised when code attempts to dispatch without enabled dispatch authority."""


@dataclass(frozen=True)
class ExecutionAuthorization:
    task_id: str
    authorized: bool
    reason_code: str
    message: str


def assess_execution_authorization(task: dict[str, Any]) -> ExecutionAuthorization:
    task_id = str(task.get("id") or "").strip()
    if not task_id:
        raise ValueError("Execution authorization requires a task with a non-empty id.")
    return ExecutionAuthorization(
        task_id=task_id,
        authorized=False,
        reason_code=CURRENT_REASON_CODE,
        message=DENIAL_MESSAGE,
    )


def require_execution_authorization(task: dict[str, Any]) -> None:
    assessment = assess_execution_authorization(task)
    if not assessment.authorized:
        raise UnsafeExecutionAuthorizationError(
            f"{assessment.task_id}: {assessment.reason_code}: {assessment.message}"
        )
