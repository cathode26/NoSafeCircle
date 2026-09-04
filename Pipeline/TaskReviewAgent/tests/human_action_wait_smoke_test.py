#!/usr/bin/env python3
"""Regression tests for bounded automatic resume after direct human handoff."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.human_action_wait import (  # noqa: E402
    HumanActionWaitError,
    _snapshot_observation,
    wait_for_human_result,
)
from Pipeline.TaskReviewAgent.run_pipeline_agent import (  # noqa: E402
    _worker_terminal_contract,
)


TASK_ID = "NSC-912"
HEAD = "1" * 40


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def state(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "valid": True,
        "pending_transition": False,
        "reasons": [],
        "issue_number": 52,
        "task_id": TASK_ID,
        "state": "human_action_required",
        "phase": "unity_runtime_validation",
        "current_actor": "human",
        "branch": "nsc-912-test",
        "head_commit": HEAD,
        "human_handoff_commit": HEAD,
        "human_result": None,
    }
    value.update(changes)
    return value


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def run_sequence(values: list[dict[str, object]], *, timeout: float = 30.0):
    remaining = list(values)
    clock = Clock()

    def observe() -> dict[str, object]:
        if len(remaining) > 1:
            return remaining.pop(0)
        return remaining[0]

    return wait_for_human_result(
        observe,
        timeout_seconds=timeout,
        poll_seconds=5.0,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


def test_pass_resumes_same_exact_handoff() -> None:
    result = run_sequence(
        [
            state(),
            state(valid=False, pending_transition=True),
            state(
                state="agent_ready",
                phase="delivery_evidence",
                current_actor="agent",
                human_result="pass",
            ),
        ]
    )
    require(result["status"] == "agent_ready", str(result))
    require(result["poll_count"] == 2, str(result))


def test_fail_resumes_repair() -> None:
    result = run_sequence(
        [
            state(),
            state(
                state="agent_ready",
                phase="repair",
                current_actor="agent",
                human_result="fail",
            ),
        ]
    )
    require(result["status"] == "agent_ready", str(result))


def test_already_ready_first_read_closes_the_handoff_race() -> None:
    result = run_sequence(
        [
            state(
                state="agent_ready",
                phase="delivery_evidence",
                current_actor="agent",
                human_result="pass",
            )
        ]
    )
    require(result["status"] == "agent_ready", str(result))
    require(result["poll_count"] == 0, str(result))


def test_pending_transition_may_be_the_first_read() -> None:
    result = run_sequence(
        [
            state(valid=False, pending_transition=True),
            state(
                state="agent_ready",
                phase="delivery_evidence",
                current_actor="agent",
                human_result="pass",
            ),
        ]
    )
    require(result["status"] == "agent_ready", str(result))


def test_real_snapshot_shape_keeps_string_human_result() -> None:
    workflow_state = SimpleNamespace(
        task_id=TASK_ID,
        state=SimpleNamespace(value="agent_ready"),
        phase=SimpleNamespace(value="delivery_evidence"),
        current_actor=SimpleNamespace(value="agent"),
        branch="nsc-912-test",
        head_commit=HEAD,
        human_handoff_commit=HEAD,
        human_result="pass",
    )
    snapshot = SimpleNamespace(
        valid=True,
        managed=True,
        state=workflow_state,
        pending_transition=None,
        reasons=(),
        issue_number=52,
    )
    observed = _snapshot_observation(snapshot, TASK_ID)
    require(observed["human_result"] == "pass", str(observed))


def test_timeout_is_bounded() -> None:
    result = run_sequence([state()], timeout=12.0)
    require(result["status"] == "timeout", str(result))
    require(result["poll_count"] == 3, str(result))


def test_changed_handoff_identity_fails_closed() -> None:
    try:
        run_sequence([state(), state(head_commit="2" * 40, human_handoff_commit="2" * 40)])
    except HumanActionWaitError as exc:
        require("identity" in str(exc) or "commit changed" in str(exc), str(exc))
    else:
        raise AssertionError("changed handoff identity was accepted")


def test_unrelated_state_does_not_wait_or_resume() -> None:
    result = run_sequence([state(state="complete", phase="merge_closeout")])
    require(result["status"] == "not_waiting", str(result))
    require(result["poll_count"] == 0, str(result))


def test_scheduler_terminal_contract_accepts_revalidation_handoff() -> None:
    require(
        _worker_terminal_contract("human_revalidation_required")
        == ("human_action_required", 0),
        "human revalidation was still treated as a worker failure",
    )


def test_launcher_waits_only_for_direct_explicit_runs() -> None:
    launcher = (ROOT / "Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1").read_text(
        encoding="utf-8-sig"
    )
    require("[int]$HumanActionWaitMinutes = 60" in launcher, "one-hour default missing")
    require("[int]$HumanActionPollSeconds = 60" in launcher, "one-minute poll default missing")
    require("Pipeline/TaskReviewAgent/human_action_wait.py" in launcher, "waiter not invoked")
    require("-not [string]::IsNullOrWhiteSpace($RunId)" in launcher, "scheduler bypass missing")

    host = (ROOT / "Pipeline/TaskReviewAgent/host_worker_launcher.py").read_text(
        encoding="utf-8"
    )
    require('"-HumanActionWaitMinutes",\n        "0"' in host, "scheduler wait was not disabled")


def main() -> int:
    tests = (
        test_pass_resumes_same_exact_handoff,
        test_fail_resumes_repair,
        test_already_ready_first_read_closes_the_handoff_race,
        test_pending_transition_may_be_the_first_read,
        test_real_snapshot_shape_keeps_string_human_result,
        test_timeout_is_bounded,
        test_changed_handoff_identity_fails_closed,
        test_unrelated_state_does_not_wait_or_resume,
        test_scheduler_terminal_contract_accepts_revalidation_handoff,
        test_launcher_waits_only_for_direct_explicit_runs,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"human action wait tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
