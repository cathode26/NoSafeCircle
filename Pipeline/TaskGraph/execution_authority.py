from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PHASE1_REASON_CODE = "legacy_yaml_status_is_not_execution_authority"
PHASE1_DENIAL_MESSAGE = (
    "Tasks/*.yaml status is mutable bootstrap planning metadata. "
    "Until evidence-derived conformance is implemented, no task may be "
    "autonomously dispatched from that status or from the advisory ready queue."
)


class UnsafeExecutionAuthorizationError(RuntimeError):
    """Raised when code tries to treat legacy task status as execution authority."""


@dataclass(frozen=True)
class ExecutionAuthorization:
    task_id: str
    authorized: bool
    reason_code: str
    message: str


def assess_execution_authorization(task: dict[str, Any]) -> ExecutionAuthorization:
    """Return the Phase 1 authorization decision for one legacy task contract.

    Phase 1 deliberately denies every task. The current task files do not carry
    evidence-bound delivery/conformance state, so neither ``status: open`` nor
    ``status: complete`` can authorize an autonomous worker.
    """

    task_id = str(task.get("id") or "").strip()
    if not task_id:
        raise ValueError("Execution authorization requires a task with a non-empty id.")

    return ExecutionAuthorization(
        task_id=task_id,
        authorized=False,
        reason_code=PHASE1_REASON_CODE,
        message=PHASE1_DENIAL_MESSAGE,
    )


def require_execution_authorization(task: dict[str, Any]) -> None:
    """Fail closed until Phase 2 supplies evidence-derived conformance."""

    assessment = assess_execution_authorization(task)
    if not assessment.authorized:
        raise UnsafeExecutionAuthorizationError(
            f"{assessment.task_id}: {assessment.reason_code}: {assessment.message}"
        )
