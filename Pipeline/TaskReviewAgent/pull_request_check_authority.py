"""Evaluate only the latest effective result for each pull-request check.

GitHub keeps historical check runs attached to a commit when a pull request is
closed/reopened or rerun against a newer base. ``gh pr view --json
statusCheckRollup`` may therefore contain several results with the same logical
workflow/job name. Treating every historical result as current makes an old
failure permanently veto a newer success.

This layer groups checks by stable logical identity and chooses the newest
unambiguous run using GitHub timestamps and Actions run/job identifiers. Unknown
or chronologically ambiguous current state fails closed as pending. It also
ensures a circuit-breaker lease release is terminal for the current process, so
that same process cannot immediately reacquire the lease it just released.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .contracts import TASK_REVIEW_SCHEMA_VERSION
from .downstream_pipeline import DownstreamPipelineError


_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}
_ACTIONS_URL_RE = re.compile(r"/actions/runs/(?P<run>\d+)(?:/job/(?P<job>\d+))?")
_SUCCESS = frozenset({"SUCCESS", "NEUTRAL", "SKIPPED"})
_PENDING = frozenset({"", "PENDING", "EXPECTED", "QUEUED", "IN_PROGRESS", "REQUESTED", "WAITING"})
_NONTERMINAL_GUARD_STATUSES = frozenset({"", "ready", "not_applicable"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _timestamp(value: Any) -> float | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _run_job_ids(item: Mapping[str, Any]) -> tuple[int, int]:
    for key in ("detailsUrl", "details_url", "targetUrl", "target_url"):
        match = _ACTIONS_URL_RE.search(_text(item.get(key)))
        if match is not None:
            return int(match.group("run")), int(match.group("job") or 0)
    return 0, 0


def _identity(item: Mapping[str, Any], index: int) -> tuple[tuple[str, ...], str]:
    typename = _text(item.get("__typename")).casefold()
    context = _text(item.get("context"))
    if typename == "statuscontext" or context:
        name = context or _text(item.get("name")) or f"status-{index + 1}"
        return ("status", name.casefold()), name

    name = _text(item.get("name")) or f"check-{index + 1}"
    workflow = _text(item.get("workflowName") or item.get("workflow_name"))
    app = _text(item.get("appName") or item.get("app_name"))
    label = f"{workflow} / {name}" if workflow else name
    return (
        "check",
        workflow.casefold(),
        app.casefold(),
        name.casefold(),
    ), label


def _recency(item: Mapping[str, Any]) -> tuple[float, int, int, float]:
    started = _timestamp(item.get("startedAt") or item.get("started_at"))
    completed = _timestamp(item.get("completedAt") or item.get("completed_at"))
    run_id, job_id = _run_job_ids(item)
    return (
        started if started is not None else -1.0,
        run_id,
        job_id,
        completed if completed is not None else -1.0,
    )


def _outcome(item: Mapping[str, Any]) -> tuple[str, str]:
    return (
        _text(item.get("status")).upper(),
        _text(item.get("conclusion") or item.get("state")).upper(),
    )


def _selected_latest(
    raw: Sequence[Mapping[str, Any]],
) -> tuple[list[tuple[str, Mapping[str, Any]]], list[str], int]:
    groups: dict[tuple[str, ...], list[tuple[str, Mapping[str, Any]]]] = {}
    for index, item in enumerate(raw):
        key, label = _identity(item, index)
        groups.setdefault(key, []).append((label, item))

    selected: list[tuple[str, Mapping[str, Any]]] = []
    ambiguous: list[str] = []
    ignored = 0
    for values in groups.values():
        ignored += max(0, len(values) - 1)
        highest = max(_recency(item) for _, item in values)
        leaders = [(label, item) for label, item in values if _recency(item) == highest]
        outcomes = {_outcome(item) for _, item in leaders}
        has_chronology = highest != (-1.0, 0, 0, -1.0)
        if len(outcomes) > 1 or (len(values) > 1 and not has_chronology and len(leaders) > 1):
            ambiguous.append(
                f"{leaders[0][0]} (ambiguous latest result; waiting for a uniquely ordered run)"
            )
            continue
        selected.append(leaders[0])
    return selected, ambiguous, ignored


def latest_effective_check_state(raw: Any) -> dict[str, Any]:
    """Classify latest logical checks while ignoring superseded history."""

    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise DownstreamPipelineError("pull-request statusCheckRollup is invalid")
    if any(not isinstance(item, Mapping) for item in raw):
        raise DownstreamPipelineError("pull-request statusCheckRollup contains an invalid entry")
    if not raw:
        return {
            "pending": ["pull-request checks have not reported a result"],
            "failed": [],
            "passed": [],
            "selected_count": 0,
            "ignored_historical_count": 0,
        }

    selected, ambiguous, ignored = _selected_latest(raw)
    pending = list(ambiguous)
    failed: list[str] = []
    passed: list[str] = []
    for label, item in selected:
        status, conclusion = _outcome(item)
        if status not in ("", "COMPLETED") or conclusion in _PENDING:
            pending.append(label)
        elif conclusion in _SUCCESS:
            passed.append(label)
        else:
            # Unknown terminal conclusions fail closed rather than being silently
            # accepted as success.
            failed.append(label)

    return {
        "pending": sorted(set(pending), key=str.casefold),
        "failed": sorted(set(failed), key=str.casefold),
        "passed": sorted(set(passed), key=str.casefold),
        "selected_count": len(selected),
        "ignored_historical_count": ignored,
    }


def _patched_check_state(self: Any, raw: Any) -> dict[str, Any]:
    del self
    return latest_effective_check_state(raw)


def _guard_terminal_outcome(
    request: Any,
    observation: Mapping[str, Any],
) -> dict[str, Any] | None:
    guard = observation.get("goal_loop_guard")
    guard = guard if isinstance(guard, Mapping) else {}
    status = _text(guard.get("status")).casefold()
    if status not in _NONTERMINAL_GUARD_STATUSES:
        coordination = observation.get("coordination")
        coordination = coordination if isinstance(coordination, Mapping) else {}
        state = coordination.get("workflow_state")
        state = state if isinstance(state, Mapping) else {}
        downstream = observation.get("downstream")
        downstream = downstream if isinstance(downstream, Mapping) else {}
        receipt = downstream.get("receipt")
        receipt = receipt if isinstance(receipt, Mapping) else {}
        reasons = guard.get("reasons")
        blockers = [str(item).strip() for item in reasons or [] if str(item).strip()]
        if not blockers:
            blockers = [f"The deterministic circuit breaker stopped this run: {status}."]
        return {
            "schema_version": TASK_REVIEW_SCHEMA_VERSION,
            "task_id": request.task_id,
            "status": "blocked",
            "issue_url": coordination.get("issue_url"),
            "branch": state.get("branch"),
            "commit": state.get("head_commit"),
            "pull_request_url": receipt.get("pull_request_url"),
            "authority": "deterministic_action_rejection_circuit_breaker",
            "deterministic_final_state": observation,
            "next_action": (
                "Correct the recorded deterministic failure, then run the generic agent again."
            ),
            "blockers": blockers,
        }
    return _ORIGINALS["terminal_outcome"](request, observation)


def install_pull_request_check_authority() -> None:
    """Install latest-check authority after the existing closeout wrappers."""

    global _INSTALLED
    if _INSTALLED:
        return
    from . import downstream_runtime as runtime
    from . import openai_downstream as openai

    controller = runtime.ResumableDownstreamTaskController
    _ORIGINALS.update(
        {
            "check_state": controller._check_state,
            "terminal_outcome": openai._terminal_outcome,
        }
    )
    controller._check_state = _patched_check_state
    openai._terminal_outcome = _guard_terminal_outcome
    _INSTALLED = True


__all__ = [
    "install_pull_request_check_authority",
    "latest_effective_check_state",
]
