"""Fail closed when checkout preparation cannot make deterministic progress."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .contracts import TaskReviewContractError, semantic_sha256
from .issue_workflow import (
    WorkflowActor,
    WorkflowEventType,
    WorkflowState,
    labels_for_state,
    render_event_comment,
    transition,
    update_issue_body,
    utc_now,
)
from .issue_workflow_store import IssueWorkflowStoreError
from .progress import ProgressLog


class GoalLoopGuardError(TaskReviewContractError):
    """Raised when the goal-loop circuit breaker cannot preserve durable state."""


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _strings(values: Any) -> list[str]:
    if isinstance(values, (list, tuple)):
        return [str(item).strip() for item in values if str(item).strip()]
    return []


def _blocked_reasons(result: Any) -> list[str]:
    if not isinstance(result, Mapping):
        return []
    status = str(result.get("status") or "").casefold()
    if status not in {"blocked", "conflict"}:
        return []
    reasons = _strings(result.get("reasons"))
    if reasons:
        return reasons
    checkout = result.get("checkout")
    if isinstance(checkout, Mapping):
        reasons = _strings(checkout.get("reasons"))
    return reasons or [f"checkout preparation returned status={status}"]


def _fingerprint(observation: Mapping[str, Any]) -> str:
    coordination = observation.get("coordination")
    coordination = coordination if isinstance(coordination, Mapping) else {}
    checkout = observation.get("checkout")
    checkout = checkout if isinstance(checkout, Mapping) else {}
    pipeline = observation.get("downstream")
    if not isinstance(pipeline, Mapping):
        pipeline = observation.get("production_pipeline")
    pipeline = pipeline if isinstance(pipeline, Mapping) else {}
    payload = {
        "coordination_status": coordination.get("status"),
        "workflow_state": coordination.get("workflow_state"),
        "checkout": {
            "status": checkout.get("status"),
            "path": checkout.get("path"),
            "branch": checkout.get("branch"),
            "head_commit": checkout.get("head_commit"),
            "clean": checkout.get("clean"),
            "reasons": checkout.get("reasons"),
        },
        "next_action": pipeline.get("next_action"),
        "receipt": pipeline.get("receipt"),
        "accepted_plan_id": observation.get("accepted_plan_id"),
        "execution_run": observation.get("execution_run"),
        "candidate_integration": observation.get("candidate_integration"),
    }
    return semantic_sha256(payload)


class GuardedTaskController:
    """Wrap a task controller with a checkout-preparation circuit breaker.

    The underlying controller remains authoritative. This wrapper only detects a
    blocked/no-op checkout preparation, releases the active lease through a valid
    append-only workflow event, and makes the next observation terminal for the
    current process. A later generic run may retry after the checkout is reconciled.
    """

    def __init__(
        self,
        controller: Any,
        *,
        progress: ProgressLog | None = None,
    ) -> None:
        self._controller = controller
        self._progress = progress
        self._terminal_reasons: list[str] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._controller, name)

    def observe(self) -> dict[str, Any]:
        observation = self._controller.observe()
        if not self._terminal_reasons:
            return observation
        guarded = _copy(observation)
        environment = guarded.get("environment")
        if not isinstance(environment, dict):
            environment = {}
            guarded["environment"] = environment
        environment["ready"] = False
        existing = _strings(environment.get("errors"))
        environment["errors"] = list(dict.fromkeys(existing + self._terminal_reasons))
        guarded["goal_loop_guard"] = {
            "status": "checkout_preparation_blocked",
            "reasons": list(self._terminal_reasons),
            "authority": "deterministic_no_progress_circuit_breaker",
        }
        return guarded

    def prepare_task_checkout(self) -> Any:
        before = self._controller.observe()
        before_fingerprint = _fingerprint(before)
        result = self._controller.prepare_task_checkout()
        reasons = _blocked_reasons(result)

        if not reasons:
            after = self._controller.observe()
            if _fingerprint(after) == before_fingerprint:
                reasons = [
                    "prepare_task_checkout returned without changing the workflow, "
                    "checkout, or next-action identity"
                ]

        if reasons:
            self._release_active_lease(reasons)
            self._terminal_reasons = list(dict.fromkeys(reasons))
            if self._progress is not None:
                self._progress.emit(
                    "checkout_preparation_blocked",
                    "Checkout preparation made no safe progress; the agent lease was released",
                    reasons=self._terminal_reasons,
                )
        return result

    def _release_active_lease(self, reasons: list[str]) -> None:
        workflow = getattr(self._controller, "workflow", None)
        service = getattr(workflow, "issue_workflow", None)
        worker_id = str(getattr(workflow, "worker_id", "") or "")
        task_id = str(getattr(self._controller, "task_id", "") or "")
        if service is None or not worker_id or not task_id:
            raise GoalLoopGuardError(
                "checkout circuit breaker cannot access the durable Issue workflow"
            )
        snapshot = service.find(task_id)
        if snapshot is None or not snapshot.valid or snapshot.state is None:
            raise GoalLoopGuardError(
                "checkout circuit breaker requires a valid managed Issue"
            )
        state = snapshot.state
        if state.state is not WorkflowState.AGENT_WORKING or state.worker_id != worker_id:
            raise GoalLoopGuardError(
                "checkout circuit breaker cannot release a lease owned by another worker"
            )

        next_state, event = transition(
            state,
            event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
            actor_type=WorkflowActor.AGENT,
            actor_id=worker_id,
            to_state=WorkflowState.AGENT_READY,
            to_phase=state.phase,
            details={
                "reason": "checkout_preparation_blocked",
                "action": "prepare_task_checkout",
                "reasons": list(dict.fromkeys(reasons)),
            },
            now=utc_now(),
        )
        service.backend.add_comment(
            snapshot.issue_number,
            render_event_comment(
                event,
                "\n".join(
                    (
                        "The agent released its lease because checkout preparation could not "
                        "make deterministic progress.",
                        "",
                        "### Checkout findings",
                        *[f"- {item}" for item in reasons],
                        "",
                        "Resolve the checkout findings, then run the same generic Game Task "
                        "Agent command again.",
                    )
                ),
            ),
        )
        service.backend.update_issue(
            snapshot.issue_number,
            body=update_issue_body(
                snapshot.body,
                next_state,
                next_action=(
                    "Resolve the recorded checkout findings, then run the generic Game "
                    "Task Agent again. The Issue remains the resume token."
                ),
            ),
            labels=labels_for_state(next_state.state, snapshot.labels),
            assignees=[service.assignee],
        )
        verified = service.find(task_id)
        if verified is None or not verified.valid or verified.state != next_state:
            raise IssueWorkflowStoreError(
                "checkout circuit-breaker lease release could not be verified"
            )
