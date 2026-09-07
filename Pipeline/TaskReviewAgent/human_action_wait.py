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
from Pipeline.TaskReviewAgent.jsonl_journal import append_jsonl_bytes  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowStoreError,
)


class HumanActionWaitError(TaskReviewContractError):
    """Raised when the exact human handoff cannot be followed safely."""


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HINT_ID = re.compile(r"^[0-9a-f]{32}$")
_HINT_SCHEMA = "nsc-human-resume-hint/v1"
_ARCHITECT_WAKE_SCHEMA = "nsc-architect-wake/v1"
_RESUME_PHASE_PREDECESSORS = {
    "delivery_evidence": "unity_runtime_validation",
    "repair": "unity_runtime_validation",
    "decomposition_apply": "decomposition_apply_authorization",
}


def _resume_transition(to_phase: str) -> dict[str, str]:
    normalized = str(to_phase).strip()
    from_phase = _RESUME_PHASE_PREDECESSORS.get(normalized)
    if from_phase is None:
        raise HumanActionWaitError(
            f"resume hint target phase is unsupported: {normalized or '<empty>'}"
        )
    return {
        "from_state": "human_action_required",
        "from_phase": from_phase,
        "to_state": "agent_ready",
        "to_phase": normalized,
    }


def _warning(message: str) -> None:
    print(f"LOCAL RESUME HINT TELEMETRY: WARNING\n{message}", file=sys.stderr)


def _append_sender_result(
    endpoint: Mapping[str, Any],
    *,
    hint_id: str,
    task_id: str,
    human_handoff_commit: str,
    state_version: int,
    event_id: str,
    transition: Mapping[str, str],
    sender_result: str,
    bytes_sent: int | None = None,
    failure_reason: str | None = None,
    error: BaseException | None = None,
) -> None:
    """Append one bounded sender outcome to the listener's run journal.

    The architect endpoint already routes the advisory datagram. Advertising
    its run-local journal beside that route lets the separate sender process
    persist success or failure even when UDP delivery never reaches the
    listener. The shared append boundary serializes this process with the
    scheduler's own journal writer.
    """

    journal_value = endpoint.get("event_journal_path")
    schema_version = endpoint.get("event_schema_version")
    scheduler_id = endpoint.get("scheduler_id")
    if (
        type(journal_value) is not str
        or not journal_value.strip()
        or not Path(journal_value).is_absolute()
        or type(schema_version) is not str
        or not schema_version.strip()
        or type(scheduler_id) is not str
        or not scheduler_id.strip()
    ):
        _warning(
            "the active architect endpoint does not advertise a valid run journal; "
            f"the {sender_result} send result for {task_id} / {hint_id} could not be persisted"
        )
        return
    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "event": "local_resume_hint_send_completed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scheduler_id": scheduler_id,
        "hint_id": hint_id,
        "task_id": task_id,
        "human_handoff_commit": human_handoff_commit,
        "state_version": state_version,
        "workflow_event_id": event_id,
        "workflow_transition": dict(transition),
        "sender_result": sender_result,
    }
    if bytes_sent is not None:
        payload["bytes_sent"] = bytes_sent
    if failure_reason is not None:
        payload["failure_reason"] = failure_reason
    if error is not None:
        payload["error_type"] = type(error).__name__
        payload["error"] = str(error)[:500]
    line = (
        json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    try:
        append_jsonl_bytes(journal_value, line)
    except (OSError, TypeError, ValueError) as exc:
        _warning(
            f"could not persist the {sender_result} send result for "
            f"{task_id} / {hint_id}: {type(exc).__name__}: {str(exc)[:500]}"
        )


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
        event_recorder: Callable[..., None] | None = None,
        event_journal_path: Path | str | None = None,
        event_schema_version: str = "1.0",
    ) -> None:
        self.source = source.resolve()
        self.scheduler_id = str(scheduler_id)
        self.wake_event = wake_event
        self.event_recorder = event_recorder
        self.event_journal_path = (
            Path(event_journal_path).resolve()
            if event_journal_path is not None
            else None
        )
        self.event_schema_version = str(event_schema_version).strip()
        if self.event_recorder is not None and not callable(self.event_recorder):
            raise HumanActionWaitError("architect wake event recorder must be callable")
        if not self.event_schema_version:
            raise HumanActionWaitError("architect wake event schema must be non-empty")
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
        self.scheduler_wait_active = False

    def _record_event(self, event: str, **values: Any) -> None:
        if self.event_recorder is None:
            return
        try:
            self.event_recorder(event, **values)
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            _warning(
                f"could not persist {event}: {type(exc).__name__}: {str(exc)[:500]}"
            )

    def begin_scheduler_wait(self) -> None:
        with self.notification_lock:
            self.scheduler_wait_active = True

    def end_scheduler_wait(self) -> None:
        with self.notification_lock:
            self.scheduler_wait_active = False

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
            "event_journal_path": (
                str(self.event_journal_path)
                if self.event_journal_path is not None
                else None
            ),
            "event_schema_version": self.event_schema_version,
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
                wait_active = self.scheduler_wait_active
                wake_already_set = self.wake_event.is_set()
                self.notification_revision += 1
                self.last_notification = {
                    key: item for key, item in value.items() if key != "token"
                }
            self.wake_event.set()
            hint_id = value.get("hint_id")
            task_id = value.get("task_id")
            if (
                isinstance(hint_id, str)
                and _HINT_ID.fullmatch(hint_id) is not None
                and isinstance(task_id, str)
            ):
                disposition = (
                    "already_waking"
                    if wake_already_set
                    else "woke_early" if wait_active else "already_awake"
                )
                self._record_event(
                    "local_resume_hint_consumed",
                    scheduler_id=self.scheduler_id,
                    hint_id=hint_id,
                    task_id=task_id,
                    human_handoff_commit=value.get("human_handoff_commit"),
                    state_version=value.get("state_version"),
                    workflow_event_id=value.get("event_id"),
                    workflow_transition=value.get("workflow_transition"),
                    sender_result="success",
                    scheduler_disposition=disposition,
                )

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
    hint_id: str,
    workflow_transition: Mapping[str, str],
) -> bool:
    """Notify the current local architect after GitHub state is authoritative."""

    selected_task = validate_task_id(task_id)
    if _SHA40.fullmatch(human_handoff_commit) is None:
        raise HumanActionWaitError("architect wake requires an exact lowercase commit SHA")
    if type(state_version) is not int or state_version <= 0:
        raise HumanActionWaitError("architect wake requires a positive state version")
    if _SHA256.fullmatch(event_id) is None:
        raise HumanActionWaitError("architect wake requires an exact lowercase event ID")
    if _HINT_ID.fullmatch(hint_id) is None:
        raise HumanActionWaitError("architect wake requires an exact resume hint ID")
    transition = dict(workflow_transition)
    if transition != _resume_transition(str(transition.get("to_phase") or "")):
        raise HumanActionWaitError("architect wake transition is not an exact resume transition")
    path = architect_wake_endpoint_path(source)
    endpoint: dict[str, Any] | None = None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        endpoint = loaded if isinstance(loaded, dict) else None
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
            "hint_id": hint_id,
            "task_id": selected_task,
            "human_handoff_commit": human_handoff_commit,
            "state_version": state_version,
            "event_id": event_id,
            "workflow_transition": transition,
        }
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            bytes_sent = sender.sendto(
                encoded,
                (host, port),
            )
        _append_sender_result(
            endpoint,
            hint_id=hint_id,
            task_id=selected_task,
            human_handoff_commit=human_handoff_commit,
            state_version=state_version,
            event_id=event_id,
            transition=transition,
            sender_result="success",
            bytes_sent=bytes_sent,
        )
        return True
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        if endpoint is not None:
            _append_sender_result(
                endpoint,
                hint_id=hint_id,
                task_id=selected_task,
                human_handoff_commit=human_handoff_commit,
                state_version=state_version,
                event_id=event_id,
                transition=transition,
                sender_result="failure",
                failure_reason="local_datagram_send_failed",
                error=exc,
            )
        else:
            _warning(
                f"the local architect endpoint was unavailable for {selected_task} / "
                f"{hint_id}; its failed send result could not be attached to a run journal"
            )
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
    if not isinstance(hint_id, str) or _HINT_ID.fullmatch(hint_id) is None:
        return None
    return raw


def publish_resume_hint(
    source: Path,
    *,
    task_id: str,
    human_handoff_commit: str,
    state_version: int,
    event_id: str,
    to_phase: str,
) -> Path:
    """Atomically publish a non-authoritative hint for a waiting local launcher."""

    if _SHA40.fullmatch(human_handoff_commit) is None:
        raise HumanActionWaitError("resume hint requires an exact lowercase commit SHA")
    if type(state_version) is not int or state_version <= 0:
        raise HumanActionWaitError("resume hint requires a positive state version")
    if _SHA256.fullmatch(event_id) is None:
        raise HumanActionWaitError("resume hint requires an exact lowercase event ID")
    transition = _resume_transition(to_phase)
    path = resume_hint_path(source, task_id)
    payload = {
        "schema": _HINT_SCHEMA,
        "hint_id": uuid.uuid4().hex,
        "task_id": validate_task_id(task_id),
        "human_handoff_commit": human_handoff_commit,
        "state_version": state_version,
        "event_id": event_id,
        "workflow_transition": transition,
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
        hint_id=payload["hint_id"],
        workflow_transition=transition,
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
