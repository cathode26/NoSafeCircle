"""Make merge-closeout reruns inspect live PR checks before stopping.

A prior terminal shortcut treated every agent-ready merge-closeout Issue with an
open PR as ``checks_pending``. Because that shortcut ran before lease acquisition,
a later generic invocation could never reach ``inspect_or_merge_pull_request``—
even after GitHub reported all checks successful.

This compatibility layer keeps ``checks_pending`` terminal only for the run that
has just inspected the live pull request and released its lease for genuinely
pending checks. A new process invocation starts unconfirmed, reacquires the lease,
and performs a fresh GitHub inspection. The layer does not alter check authority,
merge authority, or Issue transitions.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Mapping


_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}
_PENDING_CHECKS_CONFIRMED: ContextVar[bool] = ContextVar(
    "nsc_pending_checks_confirmed_for_current_run",
    default=False,
)


def _workflow_state(observation: Mapping[str, Any]) -> Mapping[str, Any]:
    coordination = observation.get("coordination")
    if not isinstance(coordination, Mapping):
        return {}
    state = coordination.get("workflow_state")
    return state if isinstance(state, Mapping) else {}


def _receipt(observation: Mapping[str, Any]) -> Mapping[str, Any]:
    downstream = observation.get("downstream")
    if not isinstance(downstream, Mapping):
        return {}
    receipt = downstream.get("receipt")
    return receipt if isinstance(receipt, Mapping) else {}


def _is_unresolved_agent_ready_closeout(observation: Mapping[str, Any]) -> bool:
    state = _workflow_state(observation)
    receipt = _receipt(observation)
    return (
        state.get("state") == "agent_ready"
        and state.get("phase") == "merge_closeout"
        and isinstance(receipt.get("evidence_commit"), str)
        and bool(receipt.get("evidence_commit"))
        and isinstance(receipt.get("pull_request_url"), str)
        and bool(receipt.get("pull_request_url"))
        and not receipt.get("merged_commit")
    )


def _record_inspection_result(result: Any) -> None:
    pending = isinstance(result, Mapping) and result.get("status") == "checks_pending"
    _PENDING_CHECKS_CONFIRMED.set(bool(pending))


def _patched_inspect_or_merge_pull_request(self: Any) -> Any:
    result = _ORIGINALS["inspect_or_merge_pull_request"](self)
    _record_inspection_result(result)
    return result


def _patched_terminal_outcome(
    request: Any,
    observation: Mapping[str, Any],
) -> dict[str, Any] | None:
    # An agent-ready merge-closeout Issue is not proof that checks are still
    # pending. On a new invocation, bypass the legacy shortcut so the agent can
    # acquire a lease and inspect GitHub again.
    if (
        _is_unresolved_agent_ready_closeout(observation)
        and not _PENDING_CHECKS_CONFIRMED.get()
    ):
        return None

    outcome = _ORIGINALS["terminal_outcome"](request, observation)
    if isinstance(outcome, Mapping) and outcome.get("status") == "checks_pending":
        # Consume the run-local confirmation. The enclosing run wrapper also
        # restores the prior context in every exit path.
        _PENDING_CHECKS_CONFIRMED.set(False)
    return outcome


def _patched_run(
    request: Any,
    controller: Any,
    **values: Any,
) -> Any:
    token = _PENDING_CHECKS_CONFIRMED.set(False)
    try:
        return _ORIGINALS["run_openai_downstream_pipeline"](
            request,
            controller,
            **values,
        )
    finally:
        _PENDING_CHECKS_CONFIRMED.reset(token)


def install_merge_closeout_check_repoll() -> None:
    """Install live check repolling after all other downstream wrappers."""

    global _INSTALLED
    if _INSTALLED:
        return

    from . import downstream_runtime as runtime
    from . import openai_downstream as openai

    controller = runtime.ResumableDownstreamTaskController
    _ORIGINALS.update(
        {
            "inspect_or_merge_pull_request": controller.inspect_or_merge_pull_request,
            "terminal_outcome": openai._terminal_outcome,
            "run_openai_downstream_pipeline": openai.run_openai_downstream_pipeline,
        }
    )

    controller.inspect_or_merge_pull_request = _patched_inspect_or_merge_pull_request
    openai._terminal_outcome = _patched_terminal_outcome
    openai.run_openai_downstream_pipeline = _patched_run
    _INSTALLED = True


__all__ = [
    "install_merge_closeout_check_repoll",
]
