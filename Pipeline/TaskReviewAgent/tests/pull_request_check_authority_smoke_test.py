#!/usr/bin/env python3
"""Regression tests for latest-only PR check evaluation and terminal lease release."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent import pull_request_check_authority as authority  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    ResumableDownstreamTaskController,
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def check(
    *,
    workflow: str,
    name: str,
    status: str,
    conclusion: str,
    started: str | None,
    run: int | None,
    job: int | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "__typename": "CheckRun",
        "workflowName": workflow,
        "name": name,
        "status": status,
        "conclusion": conclusion,
    }
    if started is not None:
        value["startedAt"] = started
    if run is not None:
        suffix = f"/job/{job or run + 1000}" if job is not None else ""
        value["detailsUrl"] = f"https://github.com/example/repo/actions/runs/{run}{suffix}"
    return value


def test_historical_failures_do_not_override_latest_success() -> None:
    raw = [
        check(
            workflow="TaskReviewAgent Deterministic Validation",
            name="windows-smoke",
            status="COMPLETED",
            conclusion="SUCCESS",
            started="2026-08-29T04:53:33Z",
            run=33234882338,
            job=99053996324,
        ),
        check(
            workflow="D1B.2 Core Deterministic Validation",
            name="windows-core",
            status="COMPLETED",
            conclusion="SUCCESS",
            started="2026-08-29T04:53:33Z",
            run=33234882318,
            job=99053996205,
        ),
        check(
            workflow="TaskReviewAgent Deterministic Validation",
            name="windows-smoke",
            status="COMPLETED",
            conclusion="FAILURE",
            started="2026-08-29T04:25:39Z",
            run=33233788956,
            job=99051093100,
        ),
        check(
            workflow="TaskReviewAgent Deterministic Validation",
            name="windows-smoke",
            status="COMPLETED",
            conclusion="FAILURE",
            started="2026-08-29T04:15:00Z",
            run=33233688428,
            job=99050000001,
        ),
        check(
            workflow="TaskReviewAgent Deterministic Validation",
            name="windows-smoke",
            status="COMPLETED",
            conclusion="FAILURE",
            started="2026-08-29T03:50:00Z",
            run=33232385094,
            job=99049000001,
        ),
        check(
            workflow="D1B.2 Core Deterministic Validation",
            name="windows-core",
            status="COMPLETED",
            conclusion="FAILURE",
            started="2026-08-29T04:20:00Z",
            run=33233688430,
            job=99050000002,
        ),
        check(
            workflow="D1B.2 Core Deterministic Validation",
            name="windows-core",
            status="COMPLETED",
            conclusion="FAILURE",
            started="2026-08-29T03:49:00Z",
            run=33232385079,
            job=99049000002,
        ),
    ]
    result = authority.latest_effective_check_state(raw)
    require(result["failed"] == [], f"historical failures still blocked: {result}")
    require(result["pending"] == [], f"successful latest checks became pending: {result}")
    require(len(result["passed"]) == 2, f"expected two current checks: {result}")
    require(result["ignored_historical_count"] == 5, "wrong ignored-history count")


def test_newer_failure_or_pending_remains_authoritative() -> None:
    old_success = check(
        workflow="Workflow",
        name="job",
        status="COMPLETED",
        conclusion="SUCCESS",
        started="2026-08-29T01:00:00Z",
        run=10,
        job=20,
    )
    newer_failure = check(
        workflow="Workflow",
        name="job",
        status="COMPLETED",
        conclusion="FAILURE",
        started="2026-08-29T02:00:00Z",
        run=11,
        job=21,
    )
    failed = authority.latest_effective_check_state([old_success, newer_failure])
    require(failed["failed"] == ["Workflow / job"], "new failure was ignored")
    require(failed["passed"] == [], "old success was still counted")

    newer_pending = check(
        workflow="Workflow",
        name="job",
        status="IN_PROGRESS",
        conclusion="",
        started="2026-08-29T03:00:00Z",
        run=12,
        job=22,
    )
    pending = authority.latest_effective_check_state(
        [old_success, newer_failure, newer_pending]
    )
    require(pending["pending"] == ["Workflow / job"], "new pending run was ignored")
    require(pending["failed"] == [], "superseded failure remained active")


def test_same_job_name_in_different_workflows_stays_distinct() -> None:
    raw = [
        check(
            workflow="Workflow A",
            name="validate",
            status="COMPLETED",
            conclusion="SUCCESS",
            started="2026-08-29T01:00:00Z",
            run=1,
        ),
        check(
            workflow="Workflow B",
            name="validate",
            status="COMPLETED",
            conclusion="FAILURE",
            started="2026-08-29T01:00:01Z",
            run=2,
        ),
    ]
    result = authority.latest_effective_check_state(raw)
    require(result["passed"] == ["Workflow A / validate"], "workflow A was lost")
    require(result["failed"] == ["Workflow B / validate"], "workflow B was merged")


def test_ambiguous_or_missing_current_state_fails_closed() -> None:
    ambiguous = authority.latest_effective_check_state(
        [
            {
                "__typename": "CheckRun",
                "workflowName": "Workflow",
                "name": "job",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "__typename": "CheckRun",
                "workflowName": "Workflow",
                "name": "job",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
            },
        ]
    )
    require(not ambiguous["failed"], "ambiguous history was guessed as failed")
    require(
        ambiguous["pending"]
        and "ambiguous latest result" in ambiguous["pending"][0],
        "ambiguous history did not fail closed as pending",
    )

    empty = authority.latest_effective_check_state([])
    require(empty["pending"], "empty check rollup was accepted")
    require(empty["passed"] == [] and empty["failed"] == [], "empty rollup was misclassified")


def test_status_context_uses_latest_state() -> None:
    result = authority.latest_effective_check_state(
        [
            {
                "__typename": "StatusContext",
                "context": "external/status",
                "state": "FAILURE",
                "startedAt": "2026-08-29T01:00:00Z",
            },
            {
                "__typename": "StatusContext",
                "context": "external/status",
                "state": "SUCCESS",
                "startedAt": "2026-08-29T02:00:00Z",
            },
        ]
    )
    require(result["passed"] == ["external/status"], "latest status context was not used")
    require(result["failed"] == [], "historical status context remained active")


def test_circuit_breaker_release_is_terminal_before_reacquisition() -> None:
    request = SimpleNamespace(task_id="NSC-020")
    observation = {
        "goal_loop_guard": {
            "status": "repeated_action_rejection",
            "reasons": ["inspect_or_merge_pull_request was rejected twice"],
        },
        "coordination": {
            "issue_url": "https://example.invalid/issues/64",
            "workflow_state": {
                "state": "agent_ready",
                "phase": "merge_closeout",
                "branch": "nsc-020-test",
                "head_commit": "a" * 40,
            },
        },
        "downstream": {
            "next_action": "acquire_agent_lease",
            "receipt": {"pull_request_url": "https://example.invalid/pull/77"},
        },
    }
    outcome = authority._guard_terminal_outcome(request, observation)
    require(outcome is not None, "released circuit breaker was not terminal")
    require(outcome["status"] == "blocked", "wrong circuit-breaker terminal status")
    require(outcome["blockers"] == observation["goal_loop_guard"]["reasons"], "reason lost")


def test_extension_is_installed_last() -> None:
    require(
        ResumableDownstreamTaskController._check_state
        is authority._patched_check_state,
        "latest check authority is not installed on the runtime controller",
    )


def main() -> int:
    tests = (
        test_historical_failures_do_not_override_latest_success,
        test_newer_failure_or_pending_remains_authoritative,
        test_same_job_name_in_different_workflows_stays_distinct,
        test_ambiguous_or_missing_current_state_fails_closed,
        test_status_context_uses_latest_state,
        test_circuit_breaker_release_is_terminal_before_reacquisition,
        test_extension_is_installed_last,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Pull-request check authority tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
