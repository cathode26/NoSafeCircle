#!/usr/bin/env python3
"""Behavioral regressions for durable, task-scoped Codex supervisor sessions.

Every test drives the real host boundary (`CodexDockerDecisionProvider.decide`)
through the real container boundary (`codex_supervisor_turn.main`, executed
in-process in place of Docker) into a fake Codex process runner that records
the exact argv it was given and answers with a scripted JSONL transcript. No
Docker, Codex, GitHub, Unity, or network call is made.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from typing import Any, Callable

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.process_runner import ProcessResult, ProcessTimeoutError  # noqa: E402
from Pipeline.AgentRuntime.providers.openai_codex import OpenAICodexProvider  # noqa: E402
from Pipeline.TaskReviewAgent import codex_supervisor  # noqa: E402
from Pipeline.TaskReviewAgent import codex_supervisor_turn  # noqa: E402
from Pipeline.TaskReviewAgent.codex_supervisor import (  # noqa: E402
    CodexDockerDecisionProvider,
    CodexSupervisorError,
    SUPERVISOR_TURN_SCHEMA_VERSION,
    resolve_supervisor_reasoning_effort,
)

# The pooled-turn contract test below needs only the pre-existing turn
# boundary, so it can state the intended pre-fix failure ("unsupported turn
# request schema_version") instead of an import error. Everything else needs
# the owner and the primitive, which do not exist before the fix.
POOLED_SUPERVISOR_TURN_SCHEMA_VERSION = getattr(
    codex_supervisor, "POOLED_SUPERVISOR_TURN_SCHEMA_VERSION", "1.1"
)
try:
    from Pipeline.AgentRuntime.durable_session_pool import DurableSessionPoolStore  # noqa: E402
    from Pipeline.TaskReviewAgent.supervisor_session_pool import (  # noqa: E402
        CODEX_RESUME_GATE_OFF_REASON,
        SUPERVISOR_SESSION_LIFETIME,
        CodexResumeActivation,
        SupervisorSessionOwner,
        SupervisorSessionPoolError,
        codex_resume_activation_from_environment,
    )
    POOL_IMPORT_ERROR: Exception | None = None
except ModuleNotFoundError as exc:  # pragma: no cover - pre-fix semantics only
    POOL_IMPORT_ERROR = exc
    DurableSessionPoolStore = None  # type: ignore[assignment]
    CODEX_RESUME_GATE_OFF_REASON = ""
    SUPERVISOR_SESSION_LIFETIME = None
    CodexResumeActivation = None  # type: ignore[assignment]
    SupervisorSessionOwner = None  # type: ignore[assignment]
    SupervisorSessionPoolError = RuntimeError  # type: ignore[assignment]
    codex_resume_activation_from_environment = None  # type: ignore[assignment]


TASK = "NSC-914"
OTHER_TASK = "NSC-915"
REPOSITORY = "https://github.com/cathode26/NoSafeCircle.git"
MODEL = "gpt-5.6-sol"
RESUME_ARGUMENT = ("-c", 'sandbox_mode="danger-full-access"')
ACTIVATION = None if POOL_IMPORT_ERROR is not None else CodexResumeActivation(RESUME_ARGUMENT)
JUDGMENT_MENU = ("create_delivery_review_proposal", "read_repository_file")
T0 = dt.datetime(2026, 9, 4, 12, 0, tzinfo=dt.timezone.utc)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_error(action: Callable[[], Any], expected: type[BaseException], fragment: str = "") -> BaseException:
    try:
        action()
    except expected as exc:
        require(fragment in str(exc), f"expected {fragment!r} in {exc}")
        return exc
    raise AssertionError(f"expected {expected.__name__}")


def decision_json(action: str = JUDGMENT_MENU[0], task_id: str = TASK) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "task_id": task_id,
            "action": action,
            "arguments": {"summary": "Reviewer summary authored by the fake provider."},
            "rationale": "The fake provider chose the first judgmental action.",
        }
    )


class FakeCodex:
    """Fake `codex` executable: records argv, answers with a scripted transcript."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.behavior = "ok"
        self.usage = {"input_tokens": 1200, "output_tokens": 40, "reasoning_output_tokens": 10}
        self.thread_ids: list[str] = []
        self.wrong_thread: str | None = None
        self.task_id = TASK

    def run(self, argv: tuple[str, ...], *, stdin: bytes, cwd: Path, timeout_seconds: float) -> ProcessResult:
        args = tuple(argv)
        prompt = stdin.decode("utf-8")
        final_path = Path(args[args.index("--output-last-message") + 1])
        record = {"argv": args, "prompt": prompt, "cwd": Path(cwd), "timeout": timeout_seconds}
        self.calls.append(record)
        behavior = self.behavior
        self.behavior = "ok"
        if behavior == "timeout":
            raise ProcessTimeoutError(ProcessResult(args, -9, b"", b"", 1.0))
        if "resume" in args[:3]:
            thread_id = args[-2]
        else:
            thread_id = self.wrong_thread or str(uuid.uuid4())
        if behavior == "wrong_thread":
            thread_id = "9c858901-8a57-4791-81fe-4c455b099bc9"
        self.thread_ids.append(thread_id)
        lines = []
        if behavior != "no_thread_event":
            lines.append(json.dumps({"type": "thread.started", "thread_id": thread_id}))
        lines.append(json.dumps({"type": "turn.completed", "usage": dict(self.usage)}))
        stdout = ("\n".join(lines) + "\n").encode("utf-8")
        if behavior == "fail":
            return ProcessResult(args, 1, stdout, b"provider refused", 0.2)
        final_path.write_text(decision_json(task_id=self.task_id), encoding="utf-8")
        return ProcessResult(args, 0, stdout, b"", 0.2)


def container_runner(fake: FakeCodex, *, requests: list[dict[str, Any]] | None = None):
    """Run the real container turn script in-process in place of `docker compose run`."""

    def runner(command, *, cwd, input_bytes, timeout_seconds):
        require("codex-supervisor" in command and "codex_supervisor_turn.py" in command[-1], str(command))
        request = json.loads(input_bytes.decode("utf-8"))
        if requests is not None:
            requests.append(request)
        original_provider = codex_supervisor_turn.OpenAICodexProvider

        def provider_factory(**options):
            options["process_runner"] = fake
            return OpenAICodexProvider(**options)

        stdout, stderr = io.StringIO(), io.StringIO()
        original_stdin = sys.stdin
        codex_supervisor_turn.OpenAICodexProvider = provider_factory
        try:
            sys.stdin = io.StringIO(input_bytes.decode("utf-8"))
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = codex_supervisor_turn.main()
        finally:
            codex_supervisor_turn.OpenAICodexProvider = original_provider
            sys.stdin = original_stdin
        return subprocess.CompletedProcess(
            command, code, stdout.getvalue().encode("utf-8"), stderr.getvalue().encode("utf-8")
        )

    return runner


class Harness:
    def __init__(self, temp: Path, *, activation: Any = ACTIVATION,
                 task_id: str = TASK, run_id: str = "run-1", worker_id: str = "worker-1",
                 model: str = MODEL, effort: str = "high", repository: str = REPOSITORY,
                 context_window: int | None = None, clock: Callable[[], dt.datetime] | None = None,
                 compose_project: str = "nosafecircle", provider_compose_project: str | None = None) -> None:
        if POOL_IMPORT_ERROR is not None:
            raise AssertionError(f"pre-fix semantics: supervisor pooling does not exist ({POOL_IMPORT_ERROR})")
        self.temp = temp
        self.fake = FakeCodex()
        self.fake.task_id = task_id
        self.requests: list[dict[str, Any]] = []
        self.owner = SupervisorSessionOwner(
            source=ROOT, checkout_root=temp / "checkouts", task_id=task_id, worker_id=worker_id,
            run_id=run_id, model=model, reasoning_effort=effort, resume_activation=activation,
            context_window_tokens=context_window, repository_identity=repository,
            compose_project=compose_project,
            clock=clock or (lambda: T0), host_identity="test-host",
        )
        self.provider = CodexDockerDecisionProvider(
            source=ROOT, model=model, reasoning_effort=effort, timeout_seconds=30.0,
            compose_project=provider_compose_project or compose_project,
            command_runner=container_runner(self.fake, requests=self.requests),
            session_owner=self.owner,
        )

    def observe(self, *, phase="delivery_evidence", state="agent_working", version=7, head="a" * 40, tree="b" * 40):
        self.provider.bind_turn_observation({
            "coordination": {"workflow_state": {"phase": phase, "state": state, "state_version": version}},
            "environment": {"source_head": head, "source_tree": tree},
            "checkout": {"status": "ready"},
        })

    def decide(self, turn: int, *, menu=JUDGMENT_MENU, **facts):
        self.observe(**facts)
        return self.provider.decide(task_id=self.owner.task_id, turn=turn, prompt=f"PROMPT turn {turn}", allowed_actions=menu)

    def records(self):
        return self.owner.records()

    def close(self) -> None:
        self.owner.close()


def argv_of(fake: FakeCodex, index: int) -> tuple[str, ...]:
    return fake.calls[index]["argv"]


def test_gate_off_keeps_turns_ephemeral_and_claims_nothing() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        harness = Harness(temp, activation=None)
        try:
            require(not harness.owner.warm_pooling_active, "gate off must not be active")
            state = harness.owner.activation_state()
            require(state["warm_pooling_active"] is False and state["reason"] == CODEX_RESUME_GATE_OFF_REASON, str(state))
            decision = harness.decide(1)
            require(decision.action == JUDGMENT_MENU[0], "decision")
            request = harness.requests[0]
            require(request["schema_version"] == SUPERVISOR_TURN_SCHEMA_VERSION and "provider_session" not in request, str(request))
            require("--ephemeral" in argv_of(harness.fake, 0) and "resume" not in argv_of(harness.fake, 0), str(argv_of(harness.fake, 0)))
            require(harness.provider.last_session["warm_pooling_active"] is False, str(harness.provider.last_session))
            require(harness.provider.last_usage == {"input_tokens": 1200, "output_tokens": 50, "total_tokens": 1250, "estimated_cost_usd": None}, str(harness.provider.last_usage))
            require(not harness.owner.state_path.exists(), "gate off writes no pool state")
        finally:
            harness.close()


def test_pooled_turns_cold_start_then_resume_with_exact_argv() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        harness = Harness(temp)
        try:
            require(harness.owner.warm_pooling_active, "activation supplied")
            heads = ["1" * 40, "2" * 40, "3" * 40]
            for turn, head in enumerate(heads, 1):
                harness.fake.usage = {"input_tokens": 1000 * turn, "output_tokens": 5, "reasoning_output_tokens": 0}
                decision = harness.decide(turn, head=head, version=turn)
                require(decision.action == JUDGMENT_MENU[0], "decision")
                require(harness.provider.last_usage["input_tokens"] == 1000 * turn, "usage recorded exactly once per turn")
                require(harness.provider.last_session["mode"] == ("start" if turn == 1 else "resume"), str(harness.provider.last_session))
            thread = harness.fake.thread_ids[0]
            start = argv_of(harness.fake, 0)
            require(start[:2] == ("codex", "exec") and start[2] != "resume", str(start))
            require("--ephemeral" not in start and ("--sandbox", "danger-full-access") == start[start.index("--sandbox"):start.index("--sandbox") + 2], str(start))
            for index in (1, 2):
                argv = argv_of(harness.fake, index)
                require(argv[:3] == ("codex", "exec", "resume"), str(argv))
                require(argv[-2] == thread and argv[-1] == "-", f"resume must name the exact thread: {argv}")
                require("--sandbox" not in argv and "--last" not in argv and "--ephemeral" not in argv, str(argv))
                require(("-c", 'sandbox_mode="danger-full-access"') == argv[argv.index("-c"):argv.index("-c") + 2], str(argv))
                require(argv[argv.index("--model") + 1] == MODEL and "model_reasoning_effort=high" in argv, str(argv))
            requests = harness.requests
            require(all(r["schema_version"] == POOLED_SUPERVISOR_TURN_SCHEMA_VERSION for r in requests), "pooled requests")
            require(requests[0]["provider_session"] == {"mode": "start", "session_id": None, "resume_sandbox_argument": ["-c", 'sandbox_mode="danger-full-access"']}, str(requests[0]["provider_session"]))
            require(requests[1]["provider_session"]["session_id"] == thread and requests[1]["provider_session"]["mode"] == "resume", str(requests[1]["provider_session"]))
            # Each turn's capsule carries that turn's durable facts and only those.
            for turn, head in enumerate(heads, 1):
                prompt = harness.fake.calls[turn - 1]["prompt"]
                require(f"Current turn: {turn}" in prompt and f"Current source head: {head}" in prompt, prompt[:400])
                require(f"Current issue state version: {turn}" in prompt and "Current phase: delivery_evidence" in prompt, prompt[:400])
                require("Current task: NSC-914" in prompt and "- create_delivery_review_proposal" in prompt, prompt[:400])
                require(f"PROMPT turn {turn}" in prompt, "original prompt follows the capsule")
                for other in heads:
                    if other != head:
                        require(other not in prompt, "stale source head leaked into a later capsule")
                if turn == 1:
                    require("no prior assignment" in prompt, "cold capsule")
                else:
                    require("revoked" in prompt and f"({turn - 1} completed before this one)" in prompt, prompt[:600])
            records = harness.records()
            require(len(records) == 1 and records[0].state == "idle" and records[0].session_id == thread, str(records))
            require(records[0].completed_assignment_count == 3, "three accounted turns")
            journal = [json.loads(line) for line in harness.owner.journal_path.read_text(encoding="utf-8").splitlines()]
            events = [e["event"] for e in journal]
            require(events == ["cold_start", "check_in", "resume", "check_in", "resume", "check_in"], events)
            require(all("PROMPT" not in json.dumps(e) for e in journal), "journal never records prompt text")
            require([e["evidence"]["input_tokens"] for e in journal if e["event"] == "check_in"] == ["1000", "2000", "3000"], "usage evidence once per turn")
        finally:
            harness.close()


def test_later_delivery_worker_resumes_the_same_task_session() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        first = Harness(temp, run_id="run-implementation", worker_id="worker-a")
        try:
            first.decide(1)
            thread = first.fake.thread_ids[0]
        finally:
            first.close()
        later = Harness(temp, run_id="run-delivery", worker_id="worker-b",
                        clock=lambda: T0 + dt.timedelta(days=2))
        try:
            later.decide(1, phase="merge_closeout")
            argv = argv_of(later.fake, 0)
            require(argv[:3] == ("codex", "exec", "resume") and argv[-2] == thread, str(argv))
            require("Current run: run-delivery" in later.fake.calls[0]["prompt"], "capsule names the new run")
            require(later.records()[0].completed_assignment_count == 2, "history continues across workers")
        finally:
            later.close()


def test_other_task_cannot_inherit_active_or_task_bound_session() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        first = Harness(temp)
        try:
            first.decide(1)
            thread = first.fake.thread_ids[0]
            other = Harness(temp, task_id=OTHER_TASK, run_id="run-other", worker_id="worker-other")
            try:
                other.decide(1)
                argv = argv_of(other.fake, 0)
                require(argv[2] != "resume" and "--ephemeral" not in argv, "another task cold-starts its own session")
                require(other.fake.thread_ids[0] != thread, "distinct conversation")
                require({r.session_id for r in first.records()} == {thread}, "NSC-914 keeps its own record")
                require(all(r.scope.binding("task_id") == OTHER_TASK for r in other.records()), "task-bound scope")
            finally:
                other.close()
        finally:
            first.close()


def test_missing_confirmation_quarantines_and_next_turn_cold_starts() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        harness = Harness(temp)
        try:
            harness.fake.behavior = "no_thread_event"
            expect_error(lambda: harness.decide(1), CodexSupervisorError, "turn failed")
            records = harness.records()
            require(len(records) == 1 and records[0].state == "quarantined" and records[0].session_id is None, str(records))
            require("no confirmed session identity" in records[0].quarantine_reason, records[0].quarantine_reason)
            harness.decide(2)
            argv = argv_of(harness.fake, 1)
            require(argv[2] != "resume", "quarantined conversation is never resumed")
            require(len(harness.records()) == 2, "a fresh record was created")
        finally:
            harness.close()


def test_mismatched_resume_identity_retires_and_rejects_decision() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        harness = Harness(temp)
        try:
            harness.decide(1)
            thread = harness.fake.thread_ids[0]
            harness.fake.behavior = "wrong_thread"
            expect_error(lambda: harness.decide(2), CodexSupervisorError, "turn failed")
            record = harness.records()[0]
            require(record.state == "retired" and record.retirement_reason == "identity_failure", str(record))
            harness.decide(3)
            argv = argv_of(harness.fake, 2)
            require(argv[2] != "resume" and harness.fake.thread_ids[-1] != thread, "identity failure cold-starts")
        finally:
            harness.close()


def test_timeout_and_transport_uncertainty_retire() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        harness = Harness(temp)
        try:
            harness.decide(1)
            harness.fake.behavior = "timeout"
            expect_error(lambda: harness.decide(2), CodexSupervisorError, "turn failed")
            record = harness.records()[0]
            require(record.state == "retired" and record.retirement_reason == "interrupted_assignment", str(record))
            require(harness.provider.last_session["outcome"] == "uncertain", str(harness.provider.last_session))
            harness.decide(3)
            require(argv_of(harness.fake, 2)[2] != "resume", "uncertain conversation is never resumed")
        finally:
            harness.close()
        broken = Harness(temp, run_id="run-2", worker_id="worker-2")
        try:
            broken.decide(1)
            resumed_record = broken.provider.last_session["record_id"]
            resumed_thread = broken.provider.last_session["confirmed_session_id"]

            def explode(command, *, cwd, input_bytes, timeout_seconds):
                raise subprocess.TimeoutExpired(command, timeout_seconds)

            broken.provider.command_runner = explode
            expect_error(lambda: broken.decide(2), subprocess.TimeoutExpired)
            require(broken.provider.last_session["outcome"] == "uncertain" and broken.provider.last_session["record_id"] == resumed_record, str(broken.provider.last_session))
            record = [r for r in broken.records() if r.record_id == resumed_record][0]
            require(record.state == "retired" and record.retirement_reason == "interrupted_assignment", f"docker-level timeout must retire this exact conversation: {record}")
            broken.provider.command_runner = container_runner(broken.fake, requests=broken.requests)
            broken.decide(3)
            require(argv_of(broken.fake, len(broken.fake.calls) - 1)[2] != "resume" and broken.fake.thread_ids[-1] != resumed_thread, "the uncertain conversation is never resumed")
        finally:
            broken.close()


def test_provider_failure_counts_then_second_failure_retires() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        harness = Harness(temp)
        try:
            harness.decide(1)
            thread = harness.fake.thread_ids[0]
            harness.fake.behavior = "fail"
            expect_error(lambda: harness.decide(2), CodexSupervisorError, "turn failed")
            record = harness.records()[0]
            require(record.state == "probation" and record.session_id == thread, str(record))
            harness.decide(3)
            argv = argv_of(harness.fake, 2)
            require(argv[:3] == ("codex", "exec", "resume") and argv[-2] == thread, "one deliberate retry resumes the same thread")
            require(harness.records()[0].state == "idle", "success resets the streak")
            harness.fake.behavior = "fail"
            expect_error(lambda: harness.decide(4), CodexSupervisorError, "turn failed")
            harness.fake.behavior = "fail"
            expect_error(lambda: harness.decide(5), CodexSupervisorError, "turn failed")
            require(harness.records()[0].state == "retired" and harness.records()[0].retirement_reason == "consecutive_provider_output_failures", str(harness.records()))
        finally:
            harness.close()


def test_interrupted_owner_is_reconciled_only_by_exact_lock_holder() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        first = Harness(temp)
        first.decide(1)
        thread = first.fake.thread_ids[0]
        # Simulate a crash mid-turn: the lease is checked out and never settled.
        stranded = first.owner.begin_turn(turn=2, allowed_actions=JUDGMENT_MENU)
        require(stranded is not None and stranded.mode == "resume", "lease is active")
        expect_error(lambda: Harness(temp, run_id="run-2", worker_id="worker-2"), SupervisorSessionPoolError, "another live worker")
        first.close()
        successor = Harness(temp, run_id="run-2", worker_id="worker-2")
        try:
            actions = [item["action"] for item in successor.owner.reconciliation]
            require(actions == ["retired_interrupted"], str(successor.owner.reconciliation))
            record = [r for r in successor.records() if r.session_id == thread][0]
            require(record.state == "retired" and record.retirement_reason == "interrupted_assignment", str(record))
            successor.decide(1)
            require(argv_of(successor.fake, 0)[2] != "resume", "the interrupted conversation is never resumed")
        finally:
            successor.close()
        # Terminal check-in is idempotent: settling the stranded lease again is a no-op.
        replay = Harness(temp, run_id="run-3", worker_id="worker-3")
        try:
            before = replay.records()
            replay.owner.finish_turn(stranded, outcome="uncertain", confirmation=None, detail="interrupted assignment: owner worker-1 run run-1 no longer holds the task liveness lock")
            require(replay.records() == before, "identical terminal settlement replay changes nothing")
        finally:
            replay.close()


def test_foreign_host_interruption_cannot_be_reconciled() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        first = Harness(temp)
        first.decide(1)
        first.owner.begin_turn(turn=2, allowed_actions=JUDGMENT_MENU)
        first.close()
        store = DurableSessionPoolStore(first.owner.state_path, lifetime=SUPERVISOR_SESSION_LIFETIME)
        payload = json.loads(first.owner.state_path.read_text(encoding="utf-8"))
        for session in payload["sessions"]:
            if session["active_lease"] is not None:
                session["active_lease"]["assignment"] = [
                    [name, "other-host" if name == "host" else value]
                    for name, value in session["active_lease"]["assignment"]
                ]
        first.owner.state_path.write_text(json.dumps(payload), encoding="utf-8")
        del store
        expect_error(lambda: Harness(temp, run_id="run-2", worker_id="worker-2"), SupervisorSessionPoolError, "cannot be proven stranded")


def test_compatibility_mismatch_cold_starts_and_retires_the_old_session() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        base = Harness(temp)
        base.decide(1)
        thread = base.fake.thread_ids[0]
        base.close()
        variants = {
            "model": dict(model="gpt-other"),
            "effort": dict(effort="low"),
            "repository": dict(repository="https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal.git"),
            "resume control": dict(activation=CodexResumeActivation(("-c", 'sandbox_mode="workspace-write"'))),
            # Another compose project mounts another codex-config volume, where
            # the old conversation's session files do not exist.
            "conversation store": dict(compose_project="nosafecircle-other"),
        }
        for label, overrides in variants.items():
            harness = Harness(temp, run_id=f"run-{label.replace(' ', '-')}", worker_id="worker-x", **overrides)
            try:
                harness.decide(1)
                require(argv_of(harness.fake, 0)[2] != "resume", f"{label} mismatch must cold-start")
                require(harness.fake.thread_ids[0] != thread, f"{label} mismatch must not reuse the thread")
                same_task = [r for r in harness.records() if r.session_id == thread]
                if label == "repository":
                    # Another repository is another pool entirely: the old
                    # conversation is not even visible, let alone resumable.
                    require(same_task == [], f"{label}: pools are repository-scoped: {same_task}")
                    continue
                require(same_task and same_task[0].state in {"retired", "expired"}, f"{label}: old session must be retired explicitly: {same_task}")
                thread = harness.fake.thread_ids[0]
            finally:
                harness.close()
        import Pipeline.TaskReviewAgent.supervisor_session_pool as module
        original = module.SUPERVISOR_SESSION_PROTOCOL_VERSION
        module.SUPERVISOR_SESSION_PROTOCOL_VERSION = "9.9"
        try:
            harness = Harness(temp, run_id="run-protocol", worker_id="worker-p",
                              activation=CodexResumeActivation(("-c", 'sandbox_mode="workspace-write"')))
            try:
                harness.decide(1)
                require(argv_of(harness.fake, 0)[2] != "resume", "protocol mismatch must cold-start")
            finally:
                harness.close()
        finally:
            module.SUPERVISOR_SESSION_PROTOCOL_VERSION = original


def test_conversation_store_is_part_of_the_session_identity() -> None:
    """The exact externally selected supervisor volume is session identity."""

    from Pipeline.TaskReviewAgent.supervisor_session_pool import (
        conversation_store_binding, gate_off_activation_state, resolve_compose_project,
    )

    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        saved_volume = os.environ.pop("NSC_TASK_SUPERVISOR_CODEX_VOLUME", None)
        try:
            harness = Harness(temp, compose_project="nosafecircle-m2a")
            try:
                state = harness.owner.activation_state()
                expected = "docker-volume:nosafecircle_codex-config"
                require(state["conversation_store"] == expected, str(state))
                require(harness.owner.scope.binding("conversation_store") == expected, str(harness.owner.scope))
                require(f"conversation_store={expected}" in harness.owner.scope.key(), harness.owner.scope.key())
                harness.decide(1)
                record = harness.records()[0]
                require(record.scope.binding("conversation_store") == expected, "the durable record carries the store")
            finally:
                harness.close()
            require(gate_off_activation_state(TASK)["conversation_store"] is None, "gate off names no store")

            # Changing only the authenticated external volume makes the old
            # durable thread unreachable. It must be retired and the next
            # invocation must cold-start instead of issuing a doomed resume.
            os.environ["NSC_TASK_SUPERVISOR_CODEX_VOLUME"] = "authenticated-store-a"
            first = Harness(temp, run_id="run-store-a", worker_id="worker-store-a")
            try:
                first.decide(1)
                first_thread = first.fake.thread_ids[0]
                require(first.owner.conversation_store == "docker-volume:authenticated-store-a", "selected store A")
            finally:
                first.close()
            os.environ["NSC_TASK_SUPERVISOR_CODEX_VOLUME"] = "authenticated-store-b"
            second = Harness(temp, run_id="run-store-b", worker_id="worker-store-b")
            try:
                second.decide(1)
                require(argv_of(second.fake, 0)[2] != "resume", str(argv_of(second.fake, 0)))
                require(second.fake.thread_ids[0] != first_thread, "a different volume cold-starts a new thread")
                old = [r for r in second.records() if r.scope.binding("conversation_store") == "docker-volume:authenticated-store-a"]
                require(old and old[0].state == "retired" and old[0].retirement_reason == "session_incompatibility", str(old))
            finally:
                second.close()

            os.environ["NSC_TASK_SUPERVISOR_CODEX_VOLUME"] = "authenticated-store-a"
            drift = Harness(temp, task_id=OTHER_TASK, run_id="run-store-drift", worker_id="worker-store-drift")
            try:
                os.environ["NSC_TASK_SUPERVISOR_CODEX_VOLUME"] = "authenticated-store-b"
                expect_error(
                    lambda: drift.decide(1), CodexSupervisorError,
                    "conversation store changed",
                )
                require(drift.fake.calls == [], "store drift must fail before Docker/provider execution")
            finally:
                drift.close()

            # Owner/provider agreement is rechecked at construction time. An
            # environment change between them fails closed before any turn.
            os.environ["NSC_TASK_SUPERVISOR_CODEX_VOLUME"] = "authenticated-store-a"
            owner = SupervisorSessionOwner(
                source=ROOT, checkout_root=temp / "checkouts", task_id=OTHER_TASK,
                worker_id="worker-store-owner", run_id="run-store-owner", model=MODEL,
                reasoning_effort="high", resume_activation=ACTIVATION,
                repository_identity=REPOSITORY, clock=lambda: T0, host_identity="test-host",
            )
            try:
                os.environ["NSC_TASK_SUPERVISOR_CODEX_VOLUME"] = "authenticated-store-b"
                expect_error(
                    lambda: CodexDockerDecisionProvider(
                        source=ROOT, model=MODEL, reasoning_effort="high",
                        timeout_seconds=30.0, command_runner=container_runner(FakeCodex()),
                        session_owner=owner,
                    ),
                    CodexSupervisorError, "conversation store",
                )
            finally:
                owner.close()
        finally:
            os.environ.pop("NSC_TASK_SUPERVISOR_CODEX_VOLUME", None)
            if saved_volume is not None:
                os.environ["NSC_TASK_SUPERVISOR_CODEX_VOLUME"] = saved_volume

        try:
            Harness(temp, run_id="run-mismatch", compose_project="nosafecircle-m2a", provider_compose_project="nosafecircle")
        except CodexSupervisorError as exc:
            require("compose project" in str(exc), str(exc))
        else:
            raise AssertionError("a provider under another compose project accepted the owner")
        for bad in ("Not A Project", "", "-leading", "has space", "UPPER"):
            try:
                resolve_compose_project(bad or None) if bad else None
                if bad:
                    raise AssertionError(f"{bad!r} was accepted as a compose project")
            except SupervisorSessionPoolError as exc:
                require("Docker Compose project" in str(exc), str(exc))
        saved = os.environ.pop("NSC_TASK_AGENT_COMPOSE_PROJECT", None)
        try:
            require(resolve_compose_project(None) == "nosafecircle", "repository default")
            os.environ["NSC_TASK_AGENT_COMPOSE_PROJECT"] = "nosafecircle-env"
            require(resolve_compose_project(None) == "nosafecircle-env" and resolve_compose_project("explicit-1") == "explicit-1", "environment then explicit")
            owner = SupervisorSessionOwner(
                source=ROOT, checkout_root=temp / "checkouts", task_id=TASK, worker_id="worker-env", run_id="run-env",
                model=MODEL, reasoning_effort="high", resume_activation=ACTIVATION, repository_identity=REPOSITORY,
                clock=lambda: T0, host_identity="test-host",
            )
            try:
                selected_volume = os.environ.get("NSC_TASK_SUPERVISOR_CODEX_VOLUME", "nosafecircle_codex-config")
                require(owner.compose_project == "nosafecircle-env" and owner.conversation_store == f"docker-volume:{selected_volume}", "compose project and external store are separate validated facts")
            finally:
                owner.close()
        finally:
            os.environ.pop("NSC_TASK_AGENT_COMPOSE_PROJECT", None)
            if saved is not None:
                os.environ["NSC_TASK_AGENT_COMPOSE_PROJECT"] = saved
        require(conversation_store_binding("nosafecircle", "claude") == ("conversation_store", "compose:nosafecircle/claude-config"), "claude store")
        import Pipeline.TaskReviewAgent.supervisor_session_pool as pool_module
        require(pool_module.external_conversation_store_binding("codex", "volume-1") == ("conversation_store", "docker-volume:volume-1"), "external Codex store")
        for bad in ("", " padded ", "../escape", "has/slash", "has:colon", "has space"):
            expect_error(lambda bad=bad: pool_module.resolve_supervisor_codex_volume(bad), SupervisorSessionPoolError, "Docker volume name")
        try:
            conversation_store_binding("nosafecircle", "gemini")
        except SupervisorSessionPoolError:
            pass
        else:
            raise AssertionError("an unknown provider has no conversation store")


def test_context_and_assignment_caps_rotate() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        harness = Harness(temp, context_window=10000)
        try:
            harness.fake.usage = {"input_tokens": 6900, "output_tokens": 1, "reasoning_output_tokens": 0}
            harness.decide(1)
            require(harness.records()[0].state == "idle", "69% is below the committed threshold")
            harness.fake.usage = {"input_tokens": 7000, "output_tokens": 1, "reasoning_output_tokens": 0}
            harness.decide(2)
            record = harness.records()[0]
            require(record.state == "retired" and record.retirement_reason == "known_context_window_threshold", str(record))
            harness.decide(3)
            require(argv_of(harness.fake, 2)[2] != "resume", "context cap rotates to a cold start")
        finally:
            harness.close()
        unknown = Harness(temp, run_id="run-unknown", worker_id="worker-u", context_window=None)
        try:
            unknown.fake.usage = {"input_tokens": 999999, "output_tokens": 1, "reasoning_output_tokens": 0}
            unknown.decide(1)
            require(unknown.records()[-1].state == "idle" or any(r.state == "idle" for r in unknown.records()), "unknown window never retires")
        finally:
            unknown.close()
        capped = Harness(temp, task_id=OTHER_TASK, run_id="run-cap", worker_id="worker-c")
        try:
            capped.decide(1)
            payload = json.loads(capped.owner.state_path.read_text(encoding="utf-8"))
            for session in payload["sessions"]:
                if ["task_id", OTHER_TASK] in session["scope"]["bindings"] and session["state"] == "idle":
                    session["completed_assignment_count"] = 99
                    session["lifecycle"]["completed_assignments"] = 99
                    session["lifecycle"]["architect_completed_admission_cycles"] = 99
            capped.owner.state_path.write_text(json.dumps(payload), encoding="utf-8")
            capped.decide(2)
            record = [r for r in capped.records() if r.scope.binding("task_id") == OTHER_TASK][0]
            require(record.state == "retired" and record.retirement_reason == "architect_completed_cycle_limit", str(record))
            capped.decide(3)
            require(argv_of(capped.fake, 2)[2] != "resume", "assignment cap rotates to a cold start")
        finally:
            capped.close()


def test_deterministic_forced_action_invokes_zero_providers() -> None:
    from Pipeline.TaskReviewAgent.downstream_determinism import install_downstream_determinism

    install_downstream_determinism()
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        harness = Harness(temp)
        try:
            decision = harness.provider.decide(
                task_id=TASK, turn=1, prompt="forced", allowed_actions=("prepare_task_checkout",)
            )
            require(decision.action == "prepare_task_checkout" and decision.arguments == {}, str(decision))
            require(harness.fake.calls == [] and harness.requests == [], "deterministic action must not reach the provider")
            require(harness.provider.last_usage["authority"] == "deterministic_host_single_action", str(harness.provider.last_usage))
            require(not harness.owner.state_path.exists(), "no session was checked out for a deterministic action")
            # A genuinely judgmental menu still uses the pooled conversation.
            harness.decide(2)
            require(len(harness.fake.calls) == 1 and harness.requests[0]["schema_version"] == POOLED_SUPERVISOR_TURN_SCHEMA_VERSION, "judgment turn is pooled")
            require(harness.provider.last_session["mode"] == "start", str(harness.provider.last_session))
            # A later deterministic turn must not journal the pooled turn's
            # lease as its own: no session took part in it.
            harness.observe(head="9" * 40)
            harness.provider.decide(task_id=TASK, turn=3, prompt="forced", allowed_actions=("prepare_task_checkout",))
            require(harness.provider.last_session is None, str(harness.provider.last_session))
            require(harness.provider._turn_observation == {}, "the observation bound for a deterministic turn is spent")
            require(len(harness.fake.calls) == 1, "still no provider call")
        finally:
            harness.close()


def test_gate_off_retires_leftover_sessions_and_never_resumes_them() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        warm = Harness(temp)
        warm.decide(1)
        thread = warm.fake.thread_ids[0]
        warm.close()
        cold = Harness(temp, run_id="run-off", worker_id="worker-off", activation=None)
        try:
            require([item["action"] for item in cold.owner.reconciliation] == ["retired_incompatible"], str(cold.owner.reconciliation))
            record = [r for r in cold.records() if r.session_id == thread][0]
            require(record.state == "retired" and record.retirement_reason == "session_incompatibility", str(record))
            cold.decide(1)
            require("--ephemeral" in argv_of(cold.fake, 0) and "resume" not in argv_of(cold.fake, 0), "gate off is ephemeral")
        finally:
            cold.close()


def test_resume_activation_validation_and_environment() -> None:
    if POOL_IMPORT_ERROR is not None:
        raise AssertionError(f"pre-fix semantics: supervisor pooling does not exist ({POOL_IMPORT_ERROR})")
    for bad in (("--sandbox", "danger-full-access"), ("--last",), ("-s", "danger-full-access"),
                ("--ephemeral",), ("--dangerously-bypass-approvals-and-sandbox",),
                ("3f2504e0-4f89-41d3-9a0c-0305e82c3301",), ("",), (" -c",),
                # Only sandbox configuration overrides reproduce the pinned policy;
                # a working directory, approval policy, profile, or feature flag
                # would widen what the resumed turn may do beyond the start.
                ("-C", "/workspace"), ("--add-dir", "/workspace"), ("-c", 'approval_policy="never"'),
                ("--profile=verified-resume",), ("-c",), ("-c", 'sandbox_mode="danger-full-access"', "-C", "/workspace"),
                ("-c", "3f2504e0-4f89-41d3-9a0c-0305e82c3301")):
        expect_error(lambda bad=bad: CodexResumeActivation(bad), SupervisorSessionPoolError)
    require(CodexResumeActivation(("--config", 'sandbox_mode="danger-full-access"')).argument[0] == "--config", "long flag accepted")
    parsed = CodexResumeActivation.parse('["-c", "sandbox_mode=\\"danger-full-access\\""]')
    require(parsed == ACTIVATION and parsed.fingerprint == ACTIVATION.fingerprint, "parse")
    expect_error(lambda: CodexResumeActivation.parse('{"-c": 1}'), SupervisorSessionPoolError, "JSON array")
    require(codex_resume_activation_from_environment({}) is None, "absent means gate off")
    require(codex_resume_activation_from_environment({"NSC_CODEX_RESUME_SANDBOX_ARGUMENT": "  "}) is None, "blank means gate off")
    require(codex_resume_activation_from_environment({"NSC_CODEX_RESUME_SANDBOX_ARGUMENT": '["-c","sandbox_mode=\\"danger-full-access\\""]'}) == ACTIVATION, "environment")


def test_host_rejects_a_decision_whose_resumed_identity_is_unproven() -> None:
    """Exit code 0 and a valid decision prove nothing about the conversation.

    The in-process container refuses a mismatched transcript itself, so this
    test bypasses it with crafted envelopes to prove the host's own guard.
    """

    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        harness = Harness(temp)
        try:
            harness.decide(1)
            thread = harness.fake.thread_ids[0]
            cases = {
                "null": None,
                "other_thread": {"schema_version": "1.0", "provider_identifier": "openai-codex", "role": "task_supervisor", "mode": "resume", "session_id": "9c858901-8a57-4791-81fe-4c455b099bc9"},
                "start_mode": {"schema_version": "1.0", "provider_identifier": "openai-codex", "role": "task_supervisor", "mode": "start", "session_id": thread},
                "other_role": {"schema_version": "1.0", "provider_identifier": "openai-codex", "role": "implementer", "mode": "resume", "session_id": thread},
            }
            for label, confirmation in cases.items():
                def crafted(command, *, cwd, input_bytes, timeout_seconds, confirmation=confirmation):
                    envelope = {
                        "schema_version": POOLED_SUPERVISOR_TURN_SCHEMA_VERSION,
                        "structured_output": json.loads(decision_json()),
                        "usage": {"input_tokens": 10, "output_tokens": 1, "total_tokens": 11, "estimated_cost_usd": None},
                        "provider_session_confirmation": confirmation,
                    }
                    return subprocess.CompletedProcess(command, 0, (json.dumps(envelope) + "\n").encode("utf-8"), b"")

                real_runner = harness.provider.command_runner
                harness.provider.command_runner = crafted
                try:
                    exc = expect_error(lambda: harness.decide(2), CodexSupervisorError, "did not prove its pooled session identity")
                finally:
                    harness.provider.command_runner = real_runner
                record = [r for r in harness.records() if r.session_id == thread or r.state == "quarantined"]
                require(all(r.state in {"retired", "quarantined"} for r in record) and any(
                    r.retirement_reason == "identity_failure" for r in record
                ), f"{label}: {record}")
                harness.decide(3)
                fresh = harness.fake.thread_ids[-1]
                require(argv_of(harness.fake, len(harness.fake.calls) - 1)[2] != "resume" and fresh != thread, f"{label}: unproven identity is never resumed")
                thread = fresh
        finally:
            harness.close()


def test_request_build_failure_returns_the_lease_uncharged() -> None:
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        harness = Harness(temp)
        try:
            harness.decide(1)
            thread = harness.fake.thread_ids[0]
            harness.observe()
            expect_error(
                lambda: harness.provider.decide(task_id=TASK, turn=2, prompt="bad \udcff surrogate", allowed_actions=JUDGMENT_MENU),
                UnicodeEncodeError,
            )
            record = harness.records()[0]
            require(record.state == "idle" and record.completed_assignment_count == 1, f"lease must be returned uncharged: {record}")
            require(len(harness.fake.calls) == 1, "no provider call happened for the failed request")
            harness.decide(3)
            require(argv_of(harness.fake, 1)[:3] == ("codex", "exec", "resume") and argv_of(harness.fake, 1)[-2] == thread, "the returned conversation resumes normally")
        finally:
            harness.close()


def test_worker_entry_point_wires_the_owner_and_reports_the_gate() -> None:
    from Pipeline.TaskReviewAgent import run_pipeline_agent
    from types import SimpleNamespace

    names = (
        "_scheduler_result_enabled", "_managed_issue_phase", "_require_explicit_fresh_admission",
        "RealTaskReviewWorkflow", "ProductionTaskController", "GuardedTaskController",
        "run_openai_production_pipeline",
    )
    originals = {name: getattr(run_pipeline_agent, name) for name in names}
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        source = temp / "source"
        source.mkdir()
        subprocess.run(("git", "init", "-q", "-b", "main"), cwd=source, check=True)
        subprocess.run(("git", "remote", "add", "origin", REPOSITORY), cwd=source, check=True)
        seen: list[dict[str, Any]] = []

        class Workflow:
            def __init__(self, *, source: Path, **_values: object) -> None:
                self.base_observer = SimpleNamespace(root=Path(source))

            @staticmethod
            def observe_goal_state() -> dict[str, object]:
                return {"coordination": {"workflow_state": {"phase": "implementation"}}}

        def capture_pipeline(request, controller, **options):
            owner = options.get("session_owner")
            seen.append({"owner": owner, "task": request.task_id})
            return {"status": "human_action_required", "authority": "fixture"}

        environment = {key: os.environ.pop(key) for key in ("NSC_CODEX_RESUME_SANDBOX_ARGUMENT", "NSC_TASK_SUPERVISOR_CONTEXT_WINDOW_TOKENS") if key in os.environ}
        try:
            run_pipeline_agent._scheduler_result_enabled = lambda _args: False
            run_pipeline_agent._managed_issue_phase = lambda **_values: "implementation"
            run_pipeline_agent._require_explicit_fresh_admission = lambda **_values: None
            run_pipeline_agent.RealTaskReviewWorkflow = Workflow
            run_pipeline_agent.ProductionTaskController = lambda **_values: object()
            run_pipeline_agent.GuardedTaskController = lambda value, progress=None: value
            run_pipeline_agent.run_openai_production_pipeline = capture_pipeline
            common = ["--task-id", TASK, "--source", str(source), "--checkout-root", str(temp / "checkouts"),
                      "--output-root", str(temp / "outputs"), "--worker-id", "wiring-fixture", "--mode", "openai"]
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = run_pipeline_agent.main(common)
            require(code == 0, f"gate-off worker exited {code}")
            gate_off = json.loads(stdout.getvalue())
            require(seen[-1]["owner"] is None, "with the gate off the pipeline receives no owner")
            require(gate_off["supervisor_session_pool"]["warm_pooling_active"] is False and CODEX_RESUME_GATE_OFF_REASON == gate_off["supervisor_session_pool"]["reason"], str(gate_off["supervisor_session_pool"]))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = run_pipeline_agent.main(common + [
                    "--supervisor-codex-resume-sandbox-argument", json.dumps(list(RESUME_ARGUMENT)),
                    "--supervisor-context-window-tokens", "400000", "--model", MODEL, "--supervisor-reasoning-effort", "high",
                ])
            require(code == 0, f"gate-on worker exited {code}")
            gate_on = json.loads(stdout.getvalue())
            owner = seen[-1]["owner"]
            require(isinstance(owner, SupervisorSessionOwner) and owner.task_id == TASK and owner.model == MODEL, str(owner))
            require(owner.resume_activation == ACTIVATION and owner.context_window_tokens == 400000, "owner built from the flags")
            require(owner.repository_identity == REPOSITORY and owner.root.is_relative_to((temp / "checkouts").resolve()), str(owner.root))
            require(gate_on["supervisor_session_pool"]["warm_pooling_active"] is True and gate_on["supervisor_session_pool"]["resume_contract"] == ACTIVATION.fingerprint, str(gate_on["supervisor_session_pool"]))
            require(owner._liveness is None, "the worker closes the owner when it finishes")
            os.environ["NSC_CODEX_RESUME_SANDBOX_ARGUMENT"] = json.dumps(list(RESUME_ARGUMENT))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = run_pipeline_agent.main(common + ["--model", MODEL])
            require(code == 0 and isinstance(seen[-1]["owner"], SupervisorSessionOwner), "the environment alone activates the gate")
            progress = list((temp / "outputs" / TASK).glob("*/progress.jsonl"))
            events = [json.loads(line) for path in progress for line in path.read_text(encoding="utf-8").splitlines()]
            pool_events = [e for e in events if e.get("event") == "supervisor_session_pool"]
            require(len(pool_events) == 3 and sorted(e["fields"]["warm_pooling_active"] for e in pool_events) == [False, True, True], str(pool_events))
        finally:
            os.environ.pop("NSC_CODEX_RESUME_SANDBOX_ARGUMENT", None)
            os.environ.update(environment)
            for name, value in originals.items():
                setattr(run_pipeline_agent, name, value)


def test_downstream_worker_keeps_the_routed_effort_for_the_task_conversation() -> None:
    """The delivery/merge-closeout worker resumes the same task conversation.

    The pool's compatibility key binds the supervisor model and reasoning
    effort. The scheduler routes one supervisor effort per task, so the
    downstream phase must build its provider and its owner from that routed
    effort; otherwise the closeout worker would cold-start a second
    conversation instead of resuming the one the implementation phase proved.
    """

    from Pipeline.TaskReviewAgent import run_pipeline_agent
    from types import SimpleNamespace

    names = (
        "_scheduler_result_enabled", "_managed_issue_phase", "_require_explicit_fresh_admission",
        "DownstreamTaskReviewWorkflow", "ResumableDownstreamTaskController", "GuardedTaskController",
        "run_openai_downstream_pipeline",
    )
    originals = {name: getattr(run_pipeline_agent, name) for name in names}
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        source = temp / "source"
        source.mkdir()
        subprocess.run(("git", "init", "-q", "-b", "main"), cwd=source, check=True)
        subprocess.run(("git", "remote", "add", "origin", REPOSITORY), cwd=source, check=True)
        seen: list[dict[str, Any]] = []

        class Workflow:
            def __init__(self, *, source: Path, **_values: object) -> None:
                self.base_observer = SimpleNamespace(root=Path(source))

            @staticmethod
            def observe_goal_state() -> dict[str, object]:
                return {"coordination": {"workflow_state": {"phase": "merge_closeout"}}}

        def capture_pipeline(request, controller, **options):
            seen.append({"options": options, "task": request.task_id})
            return {"status": "human_action_required", "authority": "fixture"}

        environment = {key: os.environ.pop(key) for key in ("NSC_CODEX_RESUME_SANDBOX_ARGUMENT", "NSC_TASK_SUPERVISOR_CONTEXT_WINDOW_TOKENS", "NSC_TASK_SUPERVISOR_REASONING_EFFORT") if key in os.environ}
        try:
            run_pipeline_agent._scheduler_result_enabled = lambda _args: False
            run_pipeline_agent._managed_issue_phase = lambda **_values: "merge_closeout"
            run_pipeline_agent._require_explicit_fresh_admission = lambda **_values: None
            run_pipeline_agent.DownstreamTaskReviewWorkflow = Workflow
            run_pipeline_agent.ResumableDownstreamTaskController = lambda **_values: object()
            run_pipeline_agent.GuardedTaskController = lambda value, progress=None: value
            run_pipeline_agent.run_openai_downstream_pipeline = capture_pipeline
            common = ["--task-id", TASK, "--source", str(source), "--checkout-root", str(temp / "checkouts"),
                      "--output-root", str(temp / "outputs"), "--worker-id", "closeout-fixture", "--mode", "openai",
                      "--model", MODEL, "--supervisor-reasoning-effort", "medium"]
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = run_pipeline_agent.main(common)
            require(code == 0, f"gate-off downstream worker exited {code}")
            gate_off = json.loads(stdout.getvalue())
            require(gate_off["selected_pipeline"] == "downstream", str(gate_off["selected_pipeline"]))
            require(seen[-1]["options"]["session_owner"] is None and seen[-1]["options"]["reasoning_effort"] == "medium", str(seen[-1]))
            require(gate_off["supervisor_session_pool"]["warm_pooling_active"] is False, str(gate_off["supervisor_session_pool"]))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = run_pipeline_agent.main(common + ["--supervisor-codex-resume-sandbox-argument", json.dumps(list(RESUME_ARGUMENT))])
            require(code == 0, f"gate-on downstream worker exited {code}")
            gate_on = json.loads(stdout.getvalue())
            options = seen[-1]["options"]
            owner = options["session_owner"]
            require(isinstance(owner, SupervisorSessionOwner) and owner.task_id == TASK, str(owner))
            require(options["reasoning_effort"] == "medium" and owner.reasoning_effort == "medium" and owner.model == MODEL, "the downstream provider and the owner share the routed effort and model")
            require(gate_on["selected_pipeline"] == "downstream" and gate_on["supervisor_session_pool"]["warm_pooling_active"] is True, str(gate_on))
            require(owner._liveness is None, "the worker closes the owner when it finishes")
            # The routed effort is the only thing that changes the key: a worker
            # launched without one resolves the same default the provider uses.
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = run_pipeline_agent.main(common[:-2] + ["--supervisor-codex-resume-sandbox-argument", json.dumps(list(RESUME_ARGUMENT))])
            require(code == 0, f"unrouted downstream worker exited {code}")
            options = seen[-1]["options"]
            require("reasoning_effort" not in options and options["session_owner"].reasoning_effort == resolve_supervisor_reasoning_effort(None), str(options))
        finally:
            os.environ.update(environment)
            for name, value in originals.items():
                setattr(run_pipeline_agent, name, value)


def test_turn_request_contract_and_failure_envelope() -> None:
    fake = FakeCodex()
    runner = container_runner(fake)
    base = {
        "run_id": "nsc-914-supervisor-001", "prompt": "p", "model": MODEL, "reasoning_effort": "high",
        "provider_turn_limit": 8, "timeout_seconds": 30.0,
        "output_schema": {"type": "object", "additionalProperties": False, "required": ["schema_version", "task_id", "action", "arguments", "rationale"],
                          "properties": {"schema_version": {"type": "string"}, "task_id": {"type": "string"}, "action": {"type": "string"},
                                         "arguments": {"type": "object", "additionalProperties": False, "properties": {"summary": {"type": ["string", "null"]}}},
                                         "rationale": {"type": "string"}}},
    }

    def run(request: dict[str, Any]) -> subprocess.CompletedProcess:
        return runner(("docker", "compose", "run", "codex-supervisor", "python3", "Pipeline/TaskReviewAgent/codex_supervisor_turn.py"),
                      cwd=ROOT, input_bytes=json.dumps(request).encode("utf-8"), timeout_seconds=60.0)

    legacy = run({**base, "schema_version": "1.0"})
    require(legacy.returncode == 0, legacy.stderr.decode())
    envelope = json.loads(legacy.stdout.decode("utf-8"))
    require(envelope["provider_session_confirmation"] is None and "--ephemeral" in fake.calls[-1]["argv"], "legacy request stays ephemeral")
    for bad_session, fragment in (
        ({"mode": "start", "session_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301", "resume_sandbox_argument": None}, "must not bind"),
        ({"mode": "resume", "session_id": None, "resume_sandbox_argument": ["-c", "x=y"]}, "requires the exact session_id"),
        ({"mode": "last", "session_id": None, "resume_sandbox_argument": None}, "exactly 'start' or 'resume'"),
        ({"mode": "resume", "session_id": "last", "resume_sandbox_argument": ["-c", "x=y"]}, "binding is invalid"),
        ({"mode": "start", "session_id": None}, "fields mismatch"),
    ):
        completed = run({**base, "schema_version": "1.1", "provider_session": bad_session})
        require(completed.returncode == 2 and fragment in completed.stderr.decode(), f"{bad_session}: {completed.stderr.decode()}")
        failure = json.loads(completed.stdout.decode("utf-8"))
        require(failure["failure"]["classification"] == "SupervisorTurnError" and failure["provider_session_confirmation"] is None, str(failure))
    require(len(fake.calls) == 1, "invalid session blocks reject before any Codex process")
    gated = run({**base, "schema_version": "1.1", "provider_session": {"mode": "resume", "session_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301", "resume_sandbox_argument": None}})
    require(gated.returncode == 2 and "CODEX_RESUME" not in gated.stdout.decode() and "danger-full-access" in gated.stderr.decode(), gated.stderr.decode())
    require(json.loads(gated.stdout.decode())["failure"]["classification"] == "ProviderRequestRejected", "resume without the verified control is refused by the adapter")
    require(len(fake.calls) == 1, "the refused resume never launched codex")
    fake.behavior = "fail"
    failed = run({**base, "schema_version": "1.1", "provider_session": {"mode": "start", "session_id": None, "resume_sandbox_argument": None}})
    failure = json.loads(failed.stdout.decode("utf-8"))
    require(failed.returncode == 2 and failure["failure"]["classification"] == "ProviderFailure", str(failure))
    require(failure["provider_session_confirmation"]["session_id"] == fake.thread_ids[-1], "identity confirmed before the failure is reported")
    require("provider refused" in failed.stderr.decode(), "human diagnostic stays on stderr")


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    # Importing Pipeline.TaskReviewAgent installs the production wrappers
    # (downstream determinism and operator logging) on
    # CodexDockerDecisionProvider.decide, so every test here runs under exactly
    # the wrappers production runs under. The order below is only cosmetic.
    tests.sort(key=lambda test: test.__name__ == "test_deterministic_forced_action_invokes_zero_providers")
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"supervisor session pool tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
