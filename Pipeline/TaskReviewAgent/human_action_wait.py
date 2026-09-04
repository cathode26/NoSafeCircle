#!/usr/bin/env python3
"""Wait for one exact human-owned task to become agent-ready again."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    TaskReviewContractError,
    validate_task_id,
)
from Pipeline.TaskReviewAgent.issue_queue import repo_root  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowStoreError,
)


class HumanActionWaitError(TaskReviewContractError):
    """Raised when the exact human handoff cannot be followed safely."""


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HINT_SCHEMA = "nsc-human-resume-hint/v1"
_ARCHITECT_WAKE_SCHEMA = "nsc-architect-wake/v1"


def resume_hint_path(source: Path, task_id: str) -> Path:
    """Return the task-scoped advisory wake path outside the Git checkout."""

    selected = validate_task_id(task_id)
    return (
        source.resolve().parent
        / ".task-review-agent"
        / "resume-hints"
        / f"{selected}.json"
    )


def architect_wake_endpoint_path(source: Path) -> Path:
    return (
        source.resolve().parent
        / ".task-review-agent"
        / "architect-wake.json"
    )


class LocalArchitectWakeListener:
    """Best-effort localhost signal; GitHub remains the only state authority."""

    def __init__(
        self,
        source: Path,
        *,
        scheduler_id: str,
        wake_event: threading.Event,
    ) -> None:
        self.source = source.resolve()
        self.scheduler_id = str(scheduler_id)
        self.wake_event = wake_event
        self.token = secrets.token_hex(32)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.settimeout(0.1)
        self.path = architect_wake_endpoint_path(self.source)
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.notification_lock = threading.Lock()
        self.notification_revision = 0
        self.last_notification: dict[str, Any] | None = None

    def start(self) -> None:
        if self.thread is not None:
            raise HumanActionWaitError("architect wake listener already started")
        payload = {
            "schema": _ARCHITECT_WAKE_SCHEMA,
            "scheduler_id": self.scheduler_id,
            "host": "127.0.0.1",
            "port": self.socket.getsockname()[1],
            "token": self.token,
            "pid": os.getpid(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(
            f".{self.path.name}.{secrets.token_hex(8)}.tmp"
        )
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
        self.thread = threading.Thread(
            target=self._listen,
            name="nsc-architect-wake-listener",
            daemon=True,
        )
        self.thread.start()

    def _listen(self) -> None:
        while not self.stop_event.is_set():
            try:
                data, _address = self.socket.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                value = json.loads(data.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict):
                continue
            if (
                value.get("schema") != _ARCHITECT_WAKE_SCHEMA
                or value.get("scheduler_id") != self.scheduler_id
                or not secrets.compare_digest(str(value.get("token") or ""), self.token)
            ):
                continue
            with self.notification_lock:
                self.notification_revision += 1
                self.last_notification = value
            self.wake_event.set()

    def notification_snapshot(self) -> tuple[int, dict[str, Any] | None]:
        """Return one internally consistent view of accepted local notifications."""

        with self.notification_lock:
            notification = (
                None
                if self.last_notification is None
                else dict(self.last_notification)
            )
            return self.notification_revision, notification

    def close(self) -> None:
        self.stop_event.set()
        self.socket.close()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        try:
            current = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return
        if (
            isinstance(current, dict)
            and current.get("scheduler_id") == self.scheduler_id
            and secrets.compare_digest(str(current.get("token") or ""), self.token)
        ):
            self.path.unlink(missing_ok=True)


def notify_local_architect(
    source: Path,
    *,
    task_id: str,
    human_handoff_commit: str,
    state_version: int,
    event_id: str,
) -> bool:
    """Notify the current local architect after GitHub state is authoritative."""

    path = architect_wake_endpoint_path(source)
    try:
        endpoint = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(endpoint, dict) or endpoint.get("schema") != _ARCHITECT_WAKE_SCHEMA:
            return False
        host = endpoint.get("host")
        port = endpoint.get("port")
        token = endpoint.get("token")
        scheduler_id = endpoint.get("scheduler_id")
        if (
            host != "127.0.0.1"
            or type(port) is not int
            or not 1 <= port <= 65535
            or type(token) is not str
            or type(scheduler_id) is not str
        ):
            return False
        payload = {
            "schema": _ARCHITECT_WAKE_SCHEMA,
            "scheduler_id": scheduler_id,
            "token": token,
            "task_id": validate_task_id(task_id),
            "human_handoff_commit": human_handoff_commit,
            "state_version": state_version,
            "event_id": event_id,
        }
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(
                json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                (host, port),
            )
        return True
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return False


def _validated_resume_hint(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or raw.get("schema") != _HINT_SCHEMA:
        return None
    task_id = raw.get("task_id")
    handoff_commit = raw.get("human_handoff_commit")
    state_version = raw.get("state_version")
    event_id = raw.get("event_id")
    hint_id = raw.get("hint_id")
    if not isinstance(task_id, str):
        return None
    try:
        validate_task_id(task_id)
    except TaskReviewContractError:
        return None
    if not isinstance(handoff_commit, str) or _SHA40.fullmatch(handoff_commit) is None:
        return None
    if type(state_version) is not int or state_version <= 0:
        return None
    if not isinstance(event_id, str) or _SHA256.fullmatch(event_id) is None:
        return None
    if not isinstance(hint_id, str) or re.fullmatch(r"[0-9a-f]{32}", hint_id) is None:
        return None
    return raw


def publish_resume_hint(
    source: Path,
    *,
    task_id: str,
    human_handoff_commit: str,
    state_version: int,
    event_id: str,
) -> Path:
    """Atomically publish a non-authoritative hint for a waiting local launcher."""

    if _SHA40.fullmatch(human_handoff_commit) is None:
        raise HumanActionWaitError("resume hint requires an exact lowercase commit SHA")
    if type(state_version) is not int or state_version <= 0:
        raise HumanActionWaitError("resume hint requires a positive state version")
    if _SHA256.fullmatch(event_id) is None:
        raise HumanActionWaitError("resume hint requires an exact lowercase event ID")
    path = resume_hint_path(source, task_id)
    payload = {
        "schema": _HINT_SCHEMA,
        "hint_id": uuid.uuid4().hex,
        "task_id": validate_task_id(task_id),
        "human_handoff_commit": human_handoff_commit,
        "state_version": state_version,
        "event_id": event_id,
        "published_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    temporary = path.with_name(f".{path.name}.{payload['hint_id']}.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    notify_local_architect(
        source,
        task_id=task_id,
        human_handoff_commit=human_handoff_commit,
        state_version=state_version,
        event_id=event_id,
    )
    return path


class LocalResumeHintWaiter:
    """Interrupt one GitHub polling delay for a new exact-handoff local hint."""

    def __init__(
        self,
        source: Path,
        task_id: str,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        check_seconds: float = 1.0,
    ) -> None:
        if not check_seconds > 0:
            raise HumanActionWaitError("local resume-hint interval must be positive")
        self.path = resume_hint_path(source, task_id)
        self.task_id = validate_task_id(task_id)
        self.monotonic = monotonic
        self.sleep = sleep
        self.check_seconds = check_seconds
        self.seen_hint_id = (_validated_resume_hint(self.path) or {}).get("hint_id")

    def wait(self, observation: Mapping[str, Any], timeout_seconds: float) -> bool:
        deadline = self.monotonic() + timeout_seconds
        while True:
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                return False
            self.sleep(min(self.check_seconds, remaining))
            hint = _validated_resume_hint(self.path)
            if hint is None or hint.get("hint_id") == self.seen_hint_id:
                continue
            self.seen_hint_id = hint["hint_id"]
            if (
                hint["task_id"] == self.task_id
                and hint["human_handoff_commit"]
                == observation.get("human_handoff_commit")
                and hint["state_version"] > observation.get("state_version", -1)
                and hint["event_id"] != observation.get("last_event_id")
            ):
                return True


def _snapshot_observation(snapshot: Any, task_id: str) -> dict[str, Any]:
    if snapshot is None:
        raise HumanActionWaitError("managed Issue disappeared during the human wait")
    state = snapshot.state
    if not snapshot.managed or state is None:
        raise HumanActionWaitError("task no longer has a managed Issue workflow")
    if state.task_id != task_id:
        raise HumanActionWaitError("managed Issue task identity changed during the human wait")
    pending = getattr(snapshot, "pending_transition", None)
    return {
        "valid": bool(snapshot.valid),
        "pending_transition": pending is not None,
        "reasons": list(snapshot.reasons),
        "issue_number": snapshot.issue_number,
        "task_id": state.task_id,
        "state": state.state.value,
        "phase": state.phase.value,
        "current_actor": state.current_actor.value,
        "branch": state.branch,
        "head_commit": state.head_commit,
        "human_handoff_commit": state.human_handoff_commit,
        "human_result": state.human_result,
        "state_version": state.state_version,
        "last_event_id": state.last_event_id,
    }


def _require_valid(observation: Mapping[str, Any]) -> None:
    if observation.get("valid") is True:
        return
    reasons = observation.get("reasons")
    detail = "; ".join(str(item) for item in reasons or ())
    raise HumanActionWaitError(
        "managed Issue became invalid during the human wait"
        + (f": {detail}" if detail else "")
    )


def _handoff_identity(observation: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        observation.get("issue_number"),
        observation.get("task_id"),
        observation.get("branch"),
        observation.get("head_commit"),
        observation.get("human_handoff_commit"),
    )


def _is_supported_handoff(observation: Mapping[str, Any]) -> bool:
    return (
        observation.get("state") == "human_action_required"
        and observation.get("phase") == "unity_runtime_validation"
        and observation.get("current_actor") == "human"
        and observation.get("human_result") is None
        and isinstance(observation.get("head_commit"), str)
        and observation.get("human_handoff_commit") == observation.get("head_commit")
    )


def _is_ready_resume(observation: Mapping[str, Any]) -> bool:
    result = observation.get("human_result")
    expected_phase = "delivery_evidence" if result == "pass" else "repair"
    return (
        result in {"pass", "fail"}
        and observation.get("state") == "agent_ready"
        and observation.get("current_actor") == "agent"
        and observation.get("phase") == expected_phase
    )


def wait_for_human_result(
    observe: Callable[[], Mapping[str, Any]],
    *,
    timeout_seconds: float,
    poll_seconds: float,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    report: Callable[[str], None] | None = None,
    local_waiter: LocalResumeHintWaiter | None = None,
) -> dict[str, Any]:
    """Poll one immutable handoff until its validated PASS/FAIL is agent-ready.

    The function never acquires a lease or mutates the Issue. A narrowly
    recognized GitHub label/body transition may be temporarily inconsistent;
    all other invalid state fails closed.
    """

    if not timeout_seconds > 0:
        raise HumanActionWaitError("human-action wait timeout must be positive")
    if not poll_seconds > 0:
        raise HumanActionWaitError("human-action poll interval must be positive")

    initial = dict(observe())
    if initial.get("valid") is True and _is_ready_resume(initial):
        return {"status": "agent_ready", "observation": initial, "poll_count": 0}
    if initial.get("valid") is not True and not (
        initial.get("pending_transition") is True and _is_supported_handoff(initial)
    ):
        _require_valid(initial)
    if not _is_supported_handoff(initial):
        return {"status": "not_waiting", "observation": initial, "poll_count": 0}

    identity = _handoff_identity(initial)
    deadline = monotonic() + timeout_seconds
    polls = 0
    next_report = monotonic() + 30.0
    if report is not None:
        report(
            "Waiting for PASS or FAIL on exact commit "
            f"{initial['head_commit']} (Issue #{initial['issue_number']})."
        )

    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            return {
                "status": "timeout",
                "observation": initial,
                "poll_count": polls,
            }
        delay = min(poll_seconds, remaining)
        if local_waiter is None:
            sleep(delay)
        else:
            local_waiter.wait(initial, delay)
        current = dict(observe())
        polls += 1

        if current.get("valid") is not True:
            if current.get("pending_transition") is True:
                continue
            _require_valid(current)

        if _handoff_identity(current) != identity:
            raise HumanActionWaitError(
                "Issue, branch, or exact human handoff commit changed while waiting"
            )
        if _is_supported_handoff(current):
            if report is not None and monotonic() >= next_report:
                report(
                    "Still waiting for PASS or FAIL on exact commit "
                    f"{initial['head_commit']}."
                )
                next_report = monotonic() + 30.0
            continue
        if _is_ready_resume(current):
            return {
                "status": "agent_ready",
                "observation": current,
                "poll_count": polls,
            }
        return {"status": "state_changed", "observation": current, "poll_count": polls}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        task_id = validate_task_id(args.task_id)
        root = repo_root(args.source.resolve())
        service = IssueWorkflowService(
            backend=GhIssueBackend(source_root=root),
            task_loader=lambda selected: load_committed_task(root, selected),
            worker_id=args.worker_id,
        )
        local_waiter = LocalResumeHintWaiter(root, task_id)
        result = wait_for_human_result(
            lambda: _snapshot_observation(service.find(task_id), task_id),
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
            report=lambda message: print(
                f"[task-agent] {message}", file=sys.stderr, flush=True
            ),
            local_waiter=local_waiter,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        if result["status"] == "agent_ready":
            return 0
        if result["status"] == "timeout":
            return 4
        return 3
    except (TaskReviewContractError, IssueWorkflowStoreError, OSError, ValueError) as exc:
        print(f"HUMAN ACTION WAIT: STOP\n{exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
