#!/usr/bin/env python3
"""Regression tests for bounded automatic resume after direct human handoff."""

from __future__ import annotations

import io
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
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
    publish_resume_hint,
    wait_for_human_result,
)
from Pipeline.TaskReviewAgent.run_pipeline_agent import (  # noqa: E402
    _worker_terminal_contract,
)
from Pipeline.TaskReviewAgent.polling_orchestrator import JsonEventEmitter  # noqa: E402
import Pipeline.TaskReviewAgent.human_action_wait as human_action_wait_module  # noqa: E402
import Pipeline.TaskReviewAgent.jsonl_journal as jsonl_journal  # noqa: E402


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
            to_phase="delivery_evidence",
        )
    except HumanActionWaitError as exc:
        require("exact lowercase commit" in str(exc), str(exc))
    else:
        raise AssertionError("publisher accepted an unbound local poke")


def test_local_architect_wake_requires_exact_token_and_cleans_its_endpoint() -> None:
    with tempfile.TemporaryDirectory() as text:
        source = Path(text) / "source"
        source.mkdir()
        journal = Path(text) / "events.jsonl"
        emitter = JsonEventEmitter(stream=io.StringIO(), journal_path=journal)
        event = threading.Event()
        listener = LocalArchitectWakeListener(
            source,
            scheduler_id="fixture-scheduler",
            wake_event=event,
            event_recorder=emitter.emit,
            event_journal_path=journal,
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
        hint_path = publish_resume_hint(
            source,
            task_id=TASK_ID,
            human_handoff_commit=HEAD,
            state_version=5,
            event_id="3" * 64,
            to_phase="delivery_evidence",
        )
        require(hint_path.is_file(), "resume hint file was not published")
        require(event.wait(1.0), "valid architect wake was not observed")
        revision, notification = listener.notification_snapshot()
        require(revision == 1, f"unexpected notification revision: {revision}")
        require(notification is not None, "accepted notification was not retained")
        require(notification["task_id"] == TASK_ID, str(notification))
        require("token" not in notification, "listener retained the endpoint secret")
        listener.close()
        records = [
            json.loads(line)
            for line in journal.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        sends = [
            item
            for item in records
            if item.get("event") == "local_resume_hint_send_completed"
        ]
        consumed = [
            item
            for item in records
            if item.get("event") == "local_resume_hint_consumed"
        ]
        require(len(sends) == 1, f"send result was not journaled once: {records}")
        require(sends[0]["sender_result"] == "success", str(sends[0]))
        require(sends[0]["workflow_transition"]["to_phase"] == "delivery_evidence", str(sends[0]))
        require(len(consumed) == 1, f"consumption was not journaled once: {records}")
        require(consumed[0]["hint_id"] == sends[0]["hint_id"], str(records))
        require(consumed[0]["scheduler_disposition"] == "already_awake", str(consumed[0]))
        require(not endpoint_path.exists(), "owned architect endpoint was not removed")


def test_failed_architect_send_is_journaled_instead_of_omitted() -> None:
    class FailingSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def sendto(self, *_args: object) -> int:
            raise OSError("fixture datagram failure")

    with tempfile.TemporaryDirectory() as text:
        source = Path(text) / "source"
        source.mkdir()
        journal = Path(text) / "events.jsonl"
        endpoint_path = architect_wake_endpoint_path(source)
        endpoint_path.parent.mkdir(parents=True)
        endpoint_path.write_text(
            json.dumps(
                {
                    "schema": "nsc-architect-wake/v1",
                    "scheduler_id": "fixture-scheduler",
                    "host": "127.0.0.1",
                    "port": 32123,
                    "token": "f" * 64,
                    "pid": 123,
                    "event_journal_path": str(journal.resolve()),
                    "event_schema_version": "1.0",
                }
            ),
            encoding="utf-8",
        )
        with patch(
            "Pipeline.TaskReviewAgent.human_action_wait.socket.socket",
            return_value=FailingSocket(),
        ):
            publish_resume_hint(
                source,
                task_id=TASK_ID,
                human_handoff_commit=HEAD,
                state_version=5,
                event_id="3" * 64,
                to_phase="delivery_evidence",
            )
        records = [
            json.loads(line)
            for line in journal.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        require(len(records) == 1, f"failed send was omitted or duplicated: {records}")
        failure = records[0]
        require(failure["event"] == "local_resume_hint_send_completed", str(failure))
        require(failure["sender_result"] == "failure", str(failure))
        require(failure["failure_reason"] == "local_datagram_send_failed", str(failure))
        require(failure["error_type"] == "OSError", str(failure))
        require(failure["task_id"] == TASK_ID, str(failure))


def test_sender_and_scheduler_cannot_interleave_jsonl_records() -> None:
    with tempfile.TemporaryDirectory() as text:
        journal = Path(text) / "events.jsonl"
        emitter = JsonEventEmitter(stream=io.StringIO(), journal_path=journal)
        endpoint = {
            "event_journal_path": str(journal.resolve()),
            "event_schema_version": "1.0",
            "scheduler_id": "fixture-scheduler",
        }
        first_half_written = threading.Event()
        release_first_writer = threading.Event()
        scheduler_finished = threading.Event()
        real_write = jsonl_journal.os.write
        first_call = True

        def split_first_write(descriptor: int, payload: bytes) -> int:
            nonlocal first_call
            if not first_call:
                return real_write(descriptor, payload)
            first_call = False
            midpoint = max(1, len(payload) // 2)
            written = real_write(descriptor, payload[:midpoint])
            first_half_written.set()
            require(
                release_first_writer.wait(2.0),
                "fixture did not release the split journal writer",
            )
            return written

        def append_sender_result() -> None:
            human_action_wait_module._append_sender_result(
                endpoint,
                hint_id="5" * 32,
                task_id=TASK_ID,
                human_handoff_commit=HEAD,
                state_version=5,
                event_id="3" * 64,
                transition={
                    "from_state": "human_action_required",
                    "from_phase": "unity_runtime_validation",
                    "to_state": "agent_ready",
                    "to_phase": "delivery_evidence",
                },
                sender_result="success",
                bytes_sent=123,
            )

        def append_scheduler_result() -> None:
            emitter.emit("poll_started", scheduler_id="fixture-scheduler")
            scheduler_finished.set()

        with patch.object(jsonl_journal.os, "write", side_effect=split_first_write):
            sender = threading.Thread(target=append_sender_result)
            sender.start()
            require(first_half_written.wait(2.0), "sender never entered the split write")
            scheduler = threading.Thread(target=append_scheduler_result)
            scheduler.start()
            time.sleep(0.05)
            require(
                not scheduler_finished.is_set(),
                "scheduler crossed the sender's whole-record append boundary",
            )
            release_first_writer.set()
            sender.join(2.0)
            scheduler.join(2.0)
        require(not sender.is_alive(), "sender thread did not finish")
        require(not scheduler.is_alive(), "scheduler thread did not finish")
        records = [
            json.loads(line)
            for line in journal.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        require(len(records) == 2, f"journal records were lost or fused: {records}")
        require(
            {record["event"] for record in records}
            == {"local_resume_hint_send_completed", "poll_started"},
            f"unexpected journal records: {records}",
        )


def test_shared_append_boundary_holds_across_processes() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        journal = root / "events.jsonl"
        ready = root / "first-half-written"
        release = root / "release-first-writer"
        sender_payload = (
            json.dumps({"event": "sender", "value": "a" * 200}, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        scheduler_payload = (
            json.dumps({"event": "scheduler", "value": "b" * 200}, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        child_script = "\n".join(
            (
                "import os, time",
                "from pathlib import Path",
                "import Pipeline.TaskReviewAgent.jsonl_journal as journal_module",
                f"journal = Path({str(journal)!r})",
                f"ready = Path({str(ready)!r})",
                f"release = Path({str(release)!r})",
                f"payload = {sender_payload!r}",
                "real_write = journal_module.os.write",
                "first_call = True",
                "def split_write(descriptor, value):",
                "    global first_call",
                "    if not first_call:",
                "        return real_write(descriptor, value)",
                "    first_call = False",
                "    midpoint = max(1, len(value) // 2)",
                "    written = real_write(descriptor, value[:midpoint])",
                "    ready.write_text('ready', encoding='utf-8')",
                "    deadline = time.monotonic() + 5.0",
                "    while not release.exists():",
                "        if time.monotonic() >= deadline:",
                "            raise TimeoutError('parent did not release child writer')",
                "        time.sleep(0.01)",
                "    return written",
                "journal_module.os.write = split_write",
                "journal_module.append_jsonl_bytes(journal, payload)",
            )
        )
        child = subprocess.Popen(
            [sys.executable, "-c", child_script],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        parent_finished = threading.Event()

        def append_from_parent() -> None:
            jsonl_journal.append_jsonl_bytes(journal, scheduler_payload)
            parent_finished.set()

        try:
            deadline = time.monotonic() + 5.0
            while not ready.exists() and child.poll() is None:
                require(time.monotonic() < deadline, "child did not split its journal write")
                time.sleep(0.01)
            require(ready.exists(), "child exited before splitting its journal write")
            parent = threading.Thread(target=append_from_parent)
            parent.start()
            time.sleep(0.1)
            require(
                not parent_finished.is_set(),
                "separate process crossed the child's whole-record append boundary",
            )
            release.write_text("release", encoding="utf-8")
            stdout, stderr = child.communicate(timeout=5.0)
            parent.join(5.0)
            require(child.returncode == 0, f"child failed: stdout={stdout!r} stderr={stderr!r}")
            require(not parent.is_alive(), "parent append did not finish after release")
        finally:
            release.touch(exist_ok=True)
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5.0)
        records = [
            json.loads(line)
            for line in journal.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        require(len(records) == 2, f"cross-process records were lost or fused: {records}")
        require(
            {record["event"] for record in records} == {"sender", "scheduler"},
            f"unexpected cross-process records: {records}",
        )


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
        test_failed_architect_send_is_journaled_instead_of_omitted,
        test_sender_and_scheduler_cannot_interleave_jsonl_records,
        test_shared_append_boundary_holds_across_processes,
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
