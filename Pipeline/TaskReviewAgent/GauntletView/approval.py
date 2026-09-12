#!/usr/bin/env python3
"""Guarded, local-only human transitions exposed by architect GauntletView."""

from __future__ import annotations

import json
import re
import secrets
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from Pipeline.TaskReviewAgent.human_action_wait import (
    publish_resume_hint_with_notification,
)
from Pipeline.TaskReviewAgent.issue_workflow import (
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    default_actor_policy,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (
    IssueWorkflowService,
    IssueWorkflowSnapshot,
)
from Pipeline.TaskReviewAgent.pass_and_resume_task import (
    _apply_canonical_human_transition,
    _authenticated_human_login,
    _decomposition_comment,
    _pass_comment,
    _validate_handoff,
    _wait_for_decomposition_ready,
    _wait_for_delivery_ready,
)

SHA40_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
PLAN_RE = re.compile(r"GDP-([0-9a-f]{64})")


class ApprovalError(RuntimeError):
    """The local approval capability was absent, stale, or unsafe to apply."""


@dataclass(frozen=True)
class ApprovalBinding:
    action_kind: str
    label: str
    task_id: str
    issue_number: int
    issue_url: str
    repository: str
    autonomous_run_id: str
    workflow_schema_version: str
    workflow_state: str
    workflow_phase: str
    workflow_state_version: int
    workflow_event_id: str
    exact_commit: str | None
    decomposition_plan_id: str | None
    decomposition_plan_sha256: str | None

    def public(self, token: str) -> dict[str, Any]:
        return {**asdict(self), "action_token": token}


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), separators=(",", ":"), sort_keys=True)


def _complete_chain(snapshot: IssueWorkflowSnapshot) -> bool:
    state = snapshot.state
    return bool(
        snapshot.managed
        and snapshot.valid
        and state is not None
        and state.state_version == len(snapshot.events)
        and snapshot.events
        and state.last_event_id == snapshot.events[-1].event_id
    )


def _binding(
    snapshot: IssueWorkflowSnapshot,
    *,
    repository: str,
    run_id: str,
) -> ApprovalBinding:
    if not _complete_chain(snapshot) or snapshot.state is None:
        raise ApprovalError("managed Issue hash/event chain is incomplete or invalid")
    state = snapshot.state
    common = dict(
        task_id=state.task_id,
        issue_number=snapshot.issue_number,
        issue_url=snapshot.issue_url,
        repository=repository,
        autonomous_run_id=run_id,
        workflow_schema_version=state.schema_version,
        workflow_state=state.state.value,
        workflow_phase=state.phase.value,
        workflow_state_version=state.state_version,
        workflow_event_id=str(state.last_event_id),
    )
    if (
        state.state is not WorkflowState.HUMAN_ACTION_REQUIRED
        or state.current_actor is not WorkflowActor.HUMAN
    ):
        raise ApprovalError("managed Issue is no longer waiting for exact human action")
    if state.phase is WorkflowPhase.UNITY_RUNTIME_VALIDATION:
        if snapshot.events[-1].event_type is not WorkflowEventType.HUMAN_HANDOFF_CREATED:
            raise ApprovalError("human validation is not bound to the current handoff event")
        exact = state.head_commit
        if exact is None or exact != state.human_handoff_commit or SHA40_RE.fullmatch(exact) is None:
            raise ApprovalError("human validation handoff has no exact commit binding")
        return ApprovalBinding(
            action_kind="implementation_pass",
            label="Mark exact commit tested PASS and continue",
            exact_commit=exact,
            decomposition_plan_id=None,
            decomposition_plan_sha256=None,
            **common,
        )
    if state.phase is WorkflowPhase.DECOMPOSITION_APPLY_AUTHORIZATION:
        handoff = snapshot.events[-1]
        if handoff.event_type is not WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED:
            raise ApprovalError("decomposition authorization is not bound to the current plan event")
        details = handoff.details
        plan_id = details.get("graph_delta_plan_id")
        match = PLAN_RE.fullmatch(str(plan_id or ""))
        graph_hash = details.get("graph_delta_sha256") or (
            match.group(1) if match is not None else None
        )
        if match is None or SHA256_RE.fullmatch(str(graph_hash or "")) is None:
            raise ApprovalError("decomposition handoff has no exact plan ID/hash binding")
        return ApprovalBinding(
            action_kind="decomposition_approve",
            label="Approve exact decomposition plan and continue",
            exact_commit=None,
            decomposition_plan_id=str(plan_id),
            decomposition_plan_sha256=str(graph_hash),
            **common,
        )
    raise ApprovalError("managed Issue phase has no GauntletView human action")


def _default_waiter(
    *,
    action_kind: str,
    service: IssueWorkflowService,
    task_id: str,
    exact: str,
    timeout_seconds: float,
    poll_seconds: float,
) -> IssueWorkflowSnapshot:
    if action_kind == "decomposition_approve":
        return _wait_for_decomposition_ready(
            service,
            task_id,
            exact,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
        )
    return _wait_for_delivery_ready(
        service,
        task_id,
        exact,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
    )


class GauntletApprovalController:
    """Issues one-time capabilities for two existing guarded human transitions."""

    def __init__(
        self,
        *,
        enabled: bool,
        identity: Mapping[str, Any],
        service: IssueWorkflowService,
        state_provider: Callable[[], Mapping[str, Any]],
        identity_reader: Callable[[], Mapping[str, Any]],
        actor_resolver: Callable[[], str] | None = None,
        handoff_validator: Callable[..., Path] | None = None,
        consistency_waiter: Callable[..., IssueWorkflowSnapshot] | None = None,
        wake_publisher: Callable[..., Any] | None = None,
        wait_timeout_seconds: float = 15.0,
        poll_seconds: float = 0.25,
    ) -> None:
        if type(enabled) is not bool:
            raise ApprovalError("approval enabled setting must be boolean")
        self.enabled = enabled
        self.identity = dict(identity)
        self.service = service
        self.state_provider = state_provider
        self.identity_reader = identity_reader
        source = Path(str(self.identity.get("source") or "")).resolve()
        checkout_root = Path(str(self.identity.get("state_root") or "")).resolve()
        self.actor_resolver = actor_resolver or (lambda: _authenticated_human_login(source))
        self.handoff_validator = handoff_validator or (
            lambda **values: _validate_handoff(
                values["snapshot"],
                task_id=values["task_id"],
                tested_commit=values["tested_commit"],
                checkout_root=checkout_root,
                apply_recovery=False,
            )
        )
        self.consistency_waiter = consistency_waiter or _default_waiter
        self.wake_publisher = wake_publisher or publish_resume_hint_with_notification
        self.wait_timeout_seconds = wait_timeout_seconds
        self.poll_seconds = poll_seconds
        self._lock = threading.Lock()
        self._tokens: dict[str, ApprovalBinding] = {}
        self._tokens_by_task: dict[str, str] = {}

    def _local_actionable(self, task_id: str) -> Mapping[str, Any]:
        state = self.state_provider()
        run = state.get("run")
        if not isinstance(run, Mapping) or run.get("run_id") != self.identity.get("run_id"):
            raise ApprovalError("GauntletView autonomous run identity changed")
        if run.get("repository") != self.identity.get("repository"):
            raise ApprovalError("GauntletView repository identity changed")
        tasks = state.get("tasks")
        candidates = (
            [
                item
                for item in tasks
                if isinstance(item, Mapping) and item.get("id") == task_id
            ]
            if isinstance(tasks, list)
            else []
        )
        if len(candidates) != 1:
            raise ApprovalError("task is not in the exact displayed run scope")
        item = candidates[0]
        if item.get("state") != "human_action" or item.get("in_scope") is not True:
            raise ApprovalError("task is no longer actionable in the exact run")
        return item

    def _current_binding(self, task_id: str) -> ApprovalBinding:
        self._local_actionable(task_id)
        snapshot = self.service.find(task_id)
        if snapshot is None:
            raise ApprovalError("managed Issue disappeared")
        return _binding(
            snapshot,
            repository=str(self.identity["repository"]),
            run_id=str(self.identity["run_id"]),
        )

    def list_actions(self) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            identity_matches = (
                _canonical(self.identity_reader()) == _canonical(self.identity)
            )
        except (OSError, TypeError, ValueError):
            identity_matches = False
        if not identity_matches:
            return []
        state = self.state_provider()
        tasks = state.get("tasks")
        if not isinstance(tasks, list):
            return []
        actions: list[dict[str, Any]] = []
        for item in tasks:
            if (
                not isinstance(item, Mapping)
                or item.get("state") != "human_action"
                or item.get("in_scope") is not True
                or not isinstance(item.get("id"), str)
            ):
                continue
            try:
                binding = self._current_binding(str(item["id"]))
            except ApprovalError:
                continue
            with self._lock:
                token = self._tokens_by_task.get(binding.task_id)
                if token is None or self._tokens.get(token) != binding:
                    if token is not None:
                        self._tokens.pop(token, None)
                    token = secrets.token_urlsafe(32)
                    self._tokens[token] = binding
                    self._tokens_by_task[binding.task_id] = token
            actions.append(binding.public(token))
        return sorted(actions, key=lambda item: item["task_id"])

    def approve(self, token: str) -> dict[str, Any]:
        if not self.enabled:
            raise ApprovalError("GauntletView human approval is disabled")
        if not isinstance(token, str) or not token:
            raise ApprovalError("approval capability is missing")
        with self._lock:
            expected = self._tokens.pop(token, None)
            if expected is not None:
                self._tokens_by_task.pop(expected.task_id, None)
        if expected is None:
            raise ApprovalError("approval capability was already used or unknown")
        if _canonical(self.identity_reader()) != _canonical(self.identity):
            raise ApprovalError("GauntletView listener identity changed")
        current = self._current_binding(expected.task_id)
        if current != expected:
            raise ApprovalError("approval is stale because the exact Issue binding changed")
        snapshot = self.service.find(expected.task_id)
        if snapshot is None:
            raise ApprovalError("managed Issue disappeared")
        if _binding(
            snapshot,
            repository=str(self.identity["repository"]),
            run_id=str(self.identity["run_id"]),
        ) != expected:
            raise ApprovalError("approval is stale because the exact Issue binding changed")
        if expected.action_kind == "implementation_pass":
            exact = str(expected.exact_commit)
            self.handoff_validator(
                snapshot=snapshot,
                task_id=expected.task_id,
                tested_commit=exact,
            )
            body = _pass_comment(
                exact,
                "Human clicked GauntletView after testing this exact commit.",
            )
            decomposition = False
        else:
            exact = str(expected.decomposition_plan_id)
            body = _decomposition_comment(
                exact,
                "Human clicked GauntletView after reviewing this exact plan.",
            )
            decomposition = True
        actor_id = self.actor_resolver()
        if not default_actor_policy().is_authorized_human(actor_id):
            raise ApprovalError(
                "authenticated identity is not authorized for the exact human action"
            )
        comments = self.service.backend.get_comments(expected.issue_number)
        if not any(item.get("body") == body for item in comments):
            self.service.backend.add_comment(expected.issue_number, body)
        _apply_canonical_human_transition(
            self.service,
            task_id=expected.task_id,
            body=body,
            actor_id=actor_id,
            approve_decomposition=decomposition,
        )
        ready = self.consistency_waiter(
            action_kind=expected.action_kind,
            service=self.service,
            task_id=expected.task_id,
            exact=exact,
            timeout_seconds=self.wait_timeout_seconds,
            poll_seconds=self.poll_seconds,
        )
        state = ready.state
        if state is None or state.human_handoff_commit is None or state.last_event_id is None:
            raise ApprovalError("mutated workflow did not expose an exact resume binding")
        hint = self.wake_publisher(
            Path(str(self.identity["source"])),
            task_id=expected.task_id,
            human_handoff_commit=state.human_handoff_commit,
            state_version=state.state_version,
            event_id=state.last_event_id,
            to_phase=state.phase.value,
        )
        notified = bool(getattr(hint, "architect_notified", False))
        return {
            "status": (
                "mutation_succeeded" if notified else "mutation_succeeded_poke_failed"
            ),
            "task_id": expected.task_id,
            "issue_number": expected.issue_number,
            "workflow_state_version": state.state_version,
            "workflow_event_id": state.last_event_id,
            "architect_notified": notified,
        }


__all__ = ["ApprovalBinding", "ApprovalError", "GauntletApprovalController"]
