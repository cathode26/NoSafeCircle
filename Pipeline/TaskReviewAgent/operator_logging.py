"""Unity-developer-facing presentation for TaskReviewAgent progress events.

The machine-readable event journal remains authoritative. This module only adds
bounded operator wording, sanitized action arguments, provider usage counters,
and practical error hints to the terminal/progress log.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Mapping

from .codex_supervisor import CodexDockerDecisionProvider, SupervisorDecision
from .progress import ProgressLog


_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}
_DECISION_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "task_agent_operator_decision",
    default=None,
)

_ACTION_LABELS = {
    "acquire_agent_lease": "Claim the task so this agent can work safely",
    "prepare_task_checkout": "Prepare the isolated Unity project checkout",
    "repository_facts": "Inspect the task-owned scripts, scenes, and tests",
    "read_issue_log": "Read the task history and human validation notes",
    "list_repository_files": "List project files",
    "search_repository": "Search project code and documentation",
    "read_repository_file": "Read a project file",
    "latest_human_feedback": "Read the latest human test feedback",
    "validate_execution_scope": "Confirm the exact implementation and test files",
    "run_execution_crew": "Run the Claude implementation crew",
    "integrate_commit_push_and_handoff": "Commit and push the implementation for Unity testing",
    "record_pipeline_blocker": "Record a task blocker",
    "integrate_current_main": "Merge current main into the task branch",
    "run_authoritative_unity_test": "Run the required Unity tests",
    "create_delivery_review_draft": "Build the delivery-evidence draft",
    "delivery_review_facts": "Inspect delivery-evidence candidates",
    "create_delivery_review_proposal": "Prepare the delivery-evidence review",
    "publish_delivery_review": "Carry the unchanged human PASS into merge closeout",
    "finalize_delivery_evidence_and_open_pr": "Commit delivery evidence and open the pull request",
    "inspect_or_merge_pull_request": "Check the pull request and merge it when ready",
    "verify_post_merge_and_complete": "Verify main and finish the task",
}
_PHASE_LABELS = {
    "implementation": "Implementation",
    "unity_runtime_validation": "Waiting for Unity validation",
    "delivery_evidence": "Delivery evidence",
    "merge_closeout": "Pull request closeout",
}
_CHECKOUT_LABELS = {
    "ready": "ready",
    "conflict": "needs repair",
    "missing": "not created",
    "unmanaged_exact": "exact but not yet registered",
}


def _clean_text(value: Any, *, limit: int = 220) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return "<blank>"
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _clean_list(values: Any, *, limit: int = 8) -> list[str] | None:
    if not isinstance(values, (list, tuple)):
        return None
    result: list[str] = []
    for item in values[:limit]:
        if isinstance(item, str):
            result.append(_clean_text(item, limit=120) or "<blank>")
        elif isinstance(item, (int, float, bool)):
            result.append(str(item))
    if len(values) > len(result):
        result.append(f"+{len(values) - len(result)} more")
    return result


def action_display_name(action: Any, arguments: Mapping[str, Any] | None = None) -> str:
    name = _ACTION_LABELS.get(str(action), str(action).replace("_", " "))
    if str(action) == "run_authoritative_unity_test" and isinstance(arguments, Mapping):
        platform = _clean_text(arguments.get("test_platform"), limit=40)
        if platform and platform != "<blank>":
            return f"Run Unity {platform} tests"
    return name


def decision_fields(decision: SupervisorDecision) -> dict[str, Any]:
    """Return bounded operator-safe arguments, never prompts or repository contents."""

    arguments = decision.arguments
    fields: dict[str, Any] = {
        "action_display": action_display_name(decision.action, arguments),
    }
    scalar_keys = (
        "planned_approach",
        "expected_validation",
        "prefix",
        "limit",
        "query",
        "path",
        "start_line",
        "end_line",
        "plan_id",
        "retry_run_id",
        "feedback_file",
        "run_id",
        "implementation_summary",
        "expected_result",
        "summary",
        "test_platform",
        "test_filter",
        "approval_notes",
    )
    for key in scalar_keys:
        value = arguments.get(key)
        if isinstance(value, str):
            fields[key] = _clean_text(value)
        elif isinstance(value, (int, float, bool)):
            fields[key] = value
    for key in (
        "prefixes",
        "existing_implementation_paths",
        "new_implementation_paths",
        "existing_test_paths",
        "new_test_paths",
    ):
        value = _clean_list(arguments.get(key))
        if value is not None:
            fields[key] = value
    for key in (
        "human_steps",
        "details",
        "selected_surfaces",
        "gate_mappings",
    ):
        value = arguments.get(key)
        if isinstance(value, (list, tuple)):
            fields[f"{key}_count"] = len(value)
    return fields


def usage_fields(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "cached_input_tokens",
        "total_tokens",
        "estimated_cost_usd",
    ):
        item = value.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            result[key] = item
    return result


def error_hint(error: Any) -> str | None:
    text = " ".join(str(error).split()).casefold()
    hints = (
        (
            "repository prefix must be non-empty",
            "The agent sent a blank search folder. No project files were read or changed.",
        ),
        (
            "repository prefix is outside downstream read roots",
            "The agent tried to search outside the allowed Unity/task documentation folders. No project files were changed.",
        ),
        (
            "exact human pass for checkout head is missing",
            "The task branch is safe, but the pipeline does not recognize the preserved human Unity PASS for this commit.",
        ),
        (
            "no unique task-contract migration authorizes the preserved human pass",
            "The pipeline could not match the preserved Unity PASS to exactly one approved task-contract migration.",
        ),
        (
            "origin/main advanced",
            "The task branch must receive the latest main branch before Unity validation can continue.",
        ),
        (
            "stored validation manifest is stale",
            "A previous Unity test result belongs to an older commit and cannot be reused.",
        ),
        (
            "unity test validated a different commit",
            "Unity tested a different Git commit than the one recorded in the task Issue.",
        ),
        (
            "unity test validated a different git tree",
            "Unity tested different project files than the exact committed task checkout.",
        ),
    )
    for fragment, hint in hints:
        if fragment in text:
            return hint
    return None


def _remember(decision: SupervisorDecision, usage: Any = None) -> None:
    _DECISION_CONTEXT.set(
        {
            "decision": decision,
            "usage": usage_fields(usage),
        }
    )


def remember_supervisor_decision_for_logging(
    decision: SupervisorDecision,
    *,
    usage: Any = None,
) -> None:
    """Test/support hook for non-Docker decision providers."""

    _remember(decision, usage)


def _context_for_action(action: Any) -> dict[str, Any] | None:
    context = _DECISION_CONTEXT.get()
    if not isinstance(context, Mapping):
        return None
    decision = context.get("decision")
    if not isinstance(decision, SupervisorDecision) or decision.action != action:
        return None
    return dict(context)


def _patched_decide(self: Any, *args: Any, **kwargs: Any) -> SupervisorDecision:
    decision = _ORIGINALS["decide"](self, *args, **kwargs)
    _remember(decision, getattr(self, "last_usage", None))
    return decision


def _operator_message(event: str, message: str, fields: Mapping[str, Any]) -> str:
    turn = fields.get("turn")
    prefix = f"Turn {turn}: " if isinstance(turn, int) else ""
    action = fields.get("action")
    context = _context_for_action(action)
    arguments = (
        context["decision"].arguments
        if isinstance(context, Mapping) and isinstance(context.get("decision"), SupervisorDecision)
        else None
    )
    action_name = action_display_name(action, arguments) if action else None

    if event == "state_observed":
        phase = _PHASE_LABELS.get(str(fields.get("phase")), str(fields.get("phase") or "Workflow"))
        checkout = _CHECKOUT_LABELS.get(
            str(fields.get("checkout_status")),
            str(fields.get("checkout_status") or "unknown"),
        )
        next_step = action_display_name(fields.get("next_action"))
        return f"{prefix}{phase}. Unity checkout: {checkout}. Next required step: {next_step}."
    if event == "codex_supervisor_started":
        next_step = action_display_name(fields.get("expected_next_action"))
        return f"{prefix}Agent is choosing the next safe step. Expected: {next_step}."
    if event == "codex_supervisor_heartbeat":
        return f"{prefix}Agent is still choosing the next safe step."
    if event == "supervisor_decision" and action_name:
        return f"{prefix}Agent chose: {action_name}."
    if event == "pipeline_action_started" and action_name:
        return f"{prefix}Working: {action_name}."
    if event == "pipeline_action_heartbeat" and action_name:
        return f"{prefix}Still working: {action_name}."
    if event == "action_completed" and action_name:
        return f"{prefix}Completed: {action_name}."
    if event == "action_rejected" and action_name:
        return f"{prefix}Blocked while trying to {action_name.casefold()}."
    if event == "terminal_state":
        status = fields.get("status") or "terminal"
        return f"{prefix}Task reached {str(status).replace('_', ' ')}."
    if event == "run_finished":
        return f"Task-agent run finished: {str(fields.get('status') or 'unknown').replace('_', ' ')}."
    return message


def _patched_emit(self: ProgressLog, event: str, message: str, **fields: Any) -> None:
    event_name = str(event).strip().casefold().replace("-", "_")
    original_message = message
    action = fields.get("action")
    context = _context_for_action(action)
    if event_name in {"supervisor_decision", "pipeline_action_started", "action_rejected"} and context:
        decision = context["decision"]
        fields.setdefault("action_arguments", decision_fields(decision))
        usage = context.get("usage")
        if usage:
            fields.setdefault("provider_usage", usage)
    if event_name == "action_rejected":
        hint = error_hint(fields.get("error"))
        if hint:
            fields.setdefault("operator_hint", hint)
    message = _operator_message(event_name, message, fields)
    if message != original_message:
        fields.setdefault("technical_message", original_message)
    _ORIGINALS["emit"](self, event, message, **fields)
    if event_name in {"action_completed", "action_rejected"}:
        _DECISION_CONTEXT.set(None)


@contextmanager
def _patched_heartbeat(
    self: ProgressLog,
    event: str,
    message: str,
    *,
    interval_seconds: float | None = None,
    **fields: Any,
) -> Iterator[None]:
    action = fields.get("action")
    context = _context_for_action(action)
    if str(event).strip().casefold() == "pipeline_action" and context:
        decision = context["decision"]
        fields.setdefault("action_arguments", decision_fields(decision))
        usage = context.get("usage")
        if usage:
            fields.setdefault("provider_usage", usage)
        message = f"Working: {action_display_name(action, decision.arguments)}"
    with _ORIGINALS["heartbeat"](
        self,
        event,
        message,
        interval_seconds=interval_seconds,
        **fields,
    ):
        yield


def install_operator_logging() -> None:
    """Install operator-facing presentation exactly once."""

    global _INSTALLED
    if _INSTALLED:
        return
    _ORIGINALS.update(
        {
            "decide": CodexDockerDecisionProvider.decide,
            "emit": ProgressLog.emit,
            "heartbeat": ProgressLog.heartbeat,
        }
    )
    CodexDockerDecisionProvider.decide = _patched_decide
    ProgressLog.emit = _patched_emit
    ProgressLog.heartbeat = _patched_heartbeat
    _INSTALLED = True


__all__ = [
    "action_display_name",
    "decision_fields",
    "error_hint",
    "install_operator_logging",
    "remember_supervisor_decision_for_logging",
    "usage_fields",
]
