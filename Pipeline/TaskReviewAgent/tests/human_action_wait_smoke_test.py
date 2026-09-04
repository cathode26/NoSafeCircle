#!/usr/bin/env python3
"""Regression tests for bounded automatic resume after direct human handoff."""

from __future__ import annotations

import sys
import json
import socket
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.human_action_wait import (  # noqa: E402
    HumanActionWaitError,
    LocalArchitectWakeListener,
    LocalResumeHintWaiter,
    _snapshot_observation,
    architect_wake_endpoint_path,
    notify_local_architect,
    publish_resume_hint,
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
        "state_version": 4,
        "last_event_id": "2" * 64,
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
        state_version=5,
        last_event_id="3" * 64,
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


def test_exact_local_poke_interrupts_the_minute_poll() -> None:
    hint = {
        "schema": "nsc-human-resume-hint/v1",
        "hint_id": "4" * 32,
        "task_id": TASK_ID,
        "human_handoff_commit": HEAD,
        "state_version": 5,
        "event_id": "3" * 64,
    }
    with patch(
        "Pipeline.TaskReviewAgent.human_action_wait._validated_resume_hint",
        side_effect=(None, hint),
    ):
        clock = Clock()
        reads = 0

        def observe() -> dict[str, object]:
            nonlocal reads
            reads += 1
            if reads == 1:
                return state()
            return state(
                state="agent_ready",
                phase="delivery_evidence",
                current_actor="agent",
                human_result="pass",
                state_version=5,
                last_event_id="3" * 64,
            )

        waiter = LocalResumeHintWaiter(
            Path("C:/fixture/repo"),
            TASK_ID,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )
        result = wait_for_human_result(
            observe,
            timeout_seconds=3600.0,
            poll_seconds=60.0,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
            local_waiter=waiter,
        )
        require(result["status"] == "agent_ready", str(result))
        require(clock.now == 1.0, f"poke did not interrupt promptly: {clock.now}")


def test_wrong_commit_local_poke_is_only_advisory() -> None:
    wrong = {
        "schema": "nsc-human-resume-hint/v1",
        "hint_id": "5" * 32,
        "task_id": TASK_ID,
        "human_handoff_commit": "9" * 40,
        "state_version": 5,
        "event_id": "3" * 64,
    }
    with patch(
        "Pipeline.TaskReviewAgent.human_action_wait._validated_resume_hint",
        side_effect=(None, wrong, wrong),
    ):
        clock = Clock()
        waiter = LocalResumeHintWaiter(
            Path("C:/fixture/repo"),
            TASK_ID,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )
        result = wait_for_human_result(
            lambda: state(),
            timeout_seconds=2.0,
            poll_seconds=2.0,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
            local_waiter=waiter,
        )
        require(result["status"] == "timeout", str(result))
        require(clock.now == 2.0, f"wrong-commit hint woke the waiter: {clock.now}")


def test_publisher_rejects_unbound_hint_before_writing() -> None:
    try:
        publish_resume_hint(
            Path("C:/fixture/repo"),
            task_id=TASK_ID,
            human_handoff_commit="not-a-commit",
            state_version=5,
            event_id="3" * 64,
        )
    except HumanActionWaitError as exc:
        require("exact lowercase commit" in str(exc), str(exc))
    else:
        raise AssertionError("publisher accepted an unbound local poke")


def test_local_architect_wake_requires_exact_token_and_cleans_its_endpoint() -> None:
    with tempfile.TemporaryDirectory() as text:
        source = Path(text) / "source"
        source.mkdir()
        event = threading.Event()
        listener = LocalArchitectWakeListener(
            source,
            scheduler_id="fixture-scheduler",
            wake_event=event,
        )
        listener.start()
        endpoint_path = architect_wake_endpoint_path(source)
        endpoint = json.loads(endpoint_path.read_text(encoding="utf-8"))
        forged = {
            "schema": "nsc-architect-wake/v1",
            "scheduler_id": "fixture-scheduler",
            "token": "0" * 64,
            "task_id": TASK_ID,
        }
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(
                json.dumps(forged).encode("utf-8"),
                (endpoint["host"], endpoint["port"]),
            )
        require(not event.wait(0.1), "forged architect wake was accepted")
        require(
            notify_local_architect(
                source,
                task_id=TASK_ID,
                human_handoff_commit=HEAD,
                state_version=5,
                event_id="3" * 64,
            ),
            "valid architect wake was not sent",
        )
        require(event.wait(1.0), "valid architect wake was not observed")
        revision, notification = listener.notification_snapshot()
        require(revision == 1, f"unexpected notification revision: {revision}")
        require(notification is not None, "accepted notification was not retained")
        require(notification["task_id"] == TASK_ID, str(notification))
        listener.close()
        require(not endpoint_path.exists(), "owned architect endpoint was not removed")


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
        test_exact_local_poke_interrupts_the_minute_poll,
        test_wrong_commit_local_poke_is_only_advisory,
        test_publisher_rejects_unbound_hint_before_writing,
        test_local_architect_wake_requires_exact_token_and_cleans_its_endpoint,
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
