#!/usr/bin/env python3
"""Regression tests for cross-run pull-request check repolling."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent import openai_downstream  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    ResumableDownstreamTaskController,
)
from Pipeline.TaskReviewAgent.merge_closeout_check_repoll import (  # noqa: E402
    _PENDING_CHECKS_CONFIRMED,
    _is_unresolved_agent_ready_closeout,
    _record_inspection_result,
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def closeout_observation() -> dict:
    return {
        "coordination": {
            "issue_url": "https://example.invalid/issues/64",
            "workflow_state": {
                "state": "agent_ready",
                "phase": "merge_closeout",
                "branch": "nsc-020-example",
                "head_commit": "a" * 40,
            },
        },
        "checkout": {"status": "ready"},
        "downstream": {
            "next_action": "acquire_agent_lease",
            "receipt": {
                "evidence_commit": "a" * 40,
                "pull_request_url": "https://example.invalid/pull/77",
            },
        },
        "environment": {"ready": True},
    }


def test_repoll_layer_is_installed_last() -> None:
    require(
        openai_downstream._terminal_outcome.__module__.endswith(
            "merge_closeout_check_repoll"
        ),
        "terminal outcome was not wrapped by merge-closeout repolling",
    )
    require(
        openai_downstream.run_openai_downstream_pipeline.__module__.endswith(
            "merge_closeout_check_repoll"
        ),
        "downstream run scope was not wrapped by merge-closeout repolling",
    )
    require(
        ResumableDownstreamTaskController.inspect_or_merge_pull_request.__module__.endswith(
            "merge_closeout_check_repoll"
        ),
        "live PR inspection was not wrapped by merge-closeout repolling",
    )


def test_new_invocation_does_not_assume_checks_are_pending() -> None:
    observation = closeout_observation()
    require(
        _is_unresolved_agent_ready_closeout(observation),
        "fixture is not an unresolved agent-ready closeout",
    )
    token = _PENDING_CHECKS_CONFIRMED.set(False)
    try:
        outcome = openai_downstream._terminal_outcome(
            SimpleNamespace(task_id="NSC-020"),
            observation,
        )
    finally:
        _PENDING_CHECKS_CONFIRMED.reset(token)
    require(
        outcome is None,
        "a fresh generic run stopped before reacquiring the lease and inspecting GitHub",
    )


def test_live_pending_result_terminates_only_the_current_run() -> None:
    observation = closeout_observation()
    token = _PENDING_CHECKS_CONFIRMED.set(False)
    try:
        _record_inspection_result({"status": "checks_pending"})
        outcome = openai_downstream._terminal_outcome(
            SimpleNamespace(task_id="NSC-020"),
            observation,
        )
        require(isinstance(outcome, dict), "confirmed pending checks were not terminal")
        require(outcome.get("status") == "checks_pending", "wrong pending outcome")
        require(
            not _PENDING_CHECKS_CONFIRMED.get(),
            "pending confirmation was not consumed after the terminal result",
        )
    finally:
        _PENDING_CHECKS_CONFIRMED.reset(token)


def test_merged_or_failed_inspection_does_not_arm_pending_terminal() -> None:
    token = _PENDING_CHECKS_CONFIRMED.set(False)
    try:
        for result in (
            {"status": "merged"},
            {"status": "complete"},
            None,
        ):
            _record_inspection_result(result)
            require(
                not _PENDING_CHECKS_CONFIRMED.get(),
                f"non-pending inspection armed terminal state: {result!r}",
            )
    finally:
        _PENDING_CHECKS_CONFIRMED.reset(token)


def main() -> int:
    tests = (
        test_repoll_layer_is_installed_last,
        test_new_invocation_does_not_assume_checks_are_pending,
        test_live_pending_result_terminates_only_the_current_run,
        test_merged_or_failed_inspection_does_not_arm_pending_terminal,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Merge-closeout check repoll tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
