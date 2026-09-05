#!/usr/bin/env python3
"""Offline component regressions for pooled Codex architect production wiring.

Only the Docker process and Codex process boundaries are replaced. The real
host factory, request decoder, architect analysis, AgentRuntime, transcript
confirmation, durable pool and scheduler lock execute in disposable folders.
No Unity acceptance or human verification is claimed.
"""

from __future__ import annotations

import contextlib
from dataclasses import replace
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.process_runner import ProcessResult
from Pipeline.AgentRuntime.provider_sessions import RESUMED_AUTHORITY_NOTICE
from Pipeline.AgentRuntime.providers.openai_codex import OpenAICodexProvider
from Pipeline.TaskReviewAgent import architect_preflight as preflight
from Pipeline.TaskReviewAgent.architect_session_owner import ArchitectSessionOwnerError
from Pipeline.TaskReviewAgent.architect_session_pool import CodexArchitectSessionOwner
from Pipeline.TaskReviewAgent.polling_orchestrator import (
    SchedulerLock, build_production_orchestrator, scheduler_lock_path,
)
from Pipeline.TaskReviewAgent.supervisor_session_pool import CodexResumeActivation
from Pipeline.TaskReviewAgent.tests.architect_preflight_smoke_test import (
    SOURCE_HEAD, portfolio, portfolio_result_value, require,
)

SESSION_A = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
SESSION_B = "9c858901-8a57-4791-81fe-4c455b099bc9"
ACTIVATION = CodexResumeActivation(("-c", 'sandbox_mode="danger-full-access"'))


def rejects(action, expected=Exception):
    try:
        action()
    except expected as exc:
        return exc
    raise AssertionError("expected failure")


class OfflineArchitect:
    def __init__(self, root):
        self.root = root.resolve()
        self.root.joinpath("source").mkdir()
        subprocess.run(("git", "init", "--quiet", str(self.root / "source")), check=True)
        self.argv = []
        self.prompts = []
        self.requests = []
        self.response_session = SESSION_A
        self.mode = "success"
        self.metadata_mutation = None
        self.owner = None
        self.binding = self.build()

    def build(self, **overrides):
        options = dict(
            source=self.root / "source", checkout_root=self.root / "checkouts",
            execution_provider="codex", architect_provider="codex", architect_model="gpt-fixture",
            scheduler_id="offline-architect", max_workers=10,
        )
        options.update(overrides)
        with patch.dict("os.environ", {"NSC_CODEX_RESUME_SANDBOX_ARGUMENT": json.dumps(ACTIVATION.argument)}), \
                patch("Pipeline.TaskReviewAgent.supervisor_session_pool._repository_identity", return_value="fixture-origin"):
            binding = build_production_orchestrator(**options)
        owner = binding.orchestrator.architect_runner
        require(type(owner) is CodexArchitectSessionOwner, "factory did not select adopt-on-confirm owner")
        owner.architect_runner.command_runner = self.docker
        self.owner = owner
        return binding

    def takeover(self, binding=None):
        selected = binding or self.binding
        selected.lock.acquire()
        selected.orchestrator.reconcile_interrupted_architect_session(lock=selected.lock)

    def call(self):
        # Any accidental real subprocess is a test failure, including provider,
        # Docker, GitHub, Git, and network helpers.
        with patch("subprocess.Popen", side_effect=AssertionError("unexpected executable")):
            return self.owner(
                candidates=portfolio(), source_head=SOURCE_HEAD,
                reservations=(), scheduler_id="offline-architect", admission_limit=2,
            )

    def docker(self, command, **values):
        require(command[:4] == ("docker", "compose", "-p", self.owner.architect_runner.compose_project), "wrong store selection")
        require("codex-review" in command and "claude-review" not in command, "wrong provider service")
        request = json.loads(values["input_bytes"])
        self.requests.append(request)
        persisted = self.owner.store.load()
        require(persisted.active_assignment_count == 1, "provider work preceded durable assignment")
        active = next(item for item in persisted.sessions if item.state == "active")
        require(active.active_lease.binding().to_dict() == request["provider_session"], "persisted binding differs from request")
        require(request["codex_resume_sandbox_argument"] == list(ACTIVATION.argument), "resume control was not transported")
        if self.mode == "interrupt":
            raise KeyboardInterrupt("simulated interrupted Docker call")
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "stdin", io.StringIO(values["input_bytes"].decode())), \
                patch.object(OpenAICodexProvider, "_run", self.codex), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = preflight.main([
                "--source", str(self.root / "source"),
                "--artifact-root", str(self.owner.architect_runner.artifact_root),
                "--scheduler-id", "offline-architect", "--provider", "codex", "--model", "gpt-fixture",
            ])
        output = stdout.getvalue()
        if status == 0 and self.metadata_mutation:
            envelope = json.loads(output)
            self.metadata_mutation(envelope["invocation_metadata"])
            output = json.dumps(envelope)
        return subprocess.CompletedProcess(command, status, output.encode(), stderr.getvalue().encode())

    def codex(self, argv, stdin, cwd, timeout):
        self.argv.append(argv)
        self.prompts.append(stdin.decode())
        require("--ephemeral" not in argv and "--last" not in argv, "pooling silently discarded or guessed a conversation")
        require(cwd == self.root / "source", "provider received wrong repository")
        final_path = Path(argv[argv.index("--output-last-message") + 1])
        final_path.write_text(json.dumps(portfolio_result_value()), encoding="utf-8")
        events = [] if self.mode == "missing_confirmation" else [
            {"type": "thread.started", "thread_id": self.response_session},
        ]
        events.append({"type": "turn.completed", "usage": {"input_tokens": 120, "cached_input_tokens": 0, "output_tokens": 30}})
        return ProcessResult(argv, 1 if self.mode == "provider_failure" else 0, ("\n".join(json.dumps(event) for event in events) + "\n").encode(), b"", 0.01)


def test_codex_factory_fresh_warm_and_restart_use_transcript_identity():
    with tempfile.TemporaryDirectory() as text:
        fixture = OfflineArchitect(Path(text))
        try:
            fixture.takeover()
            first = fixture.call()
            require(first.invocation_metadata["provider_session_confirmation"]["session_id"] == SESSION_A, "fresh transcript identity lost")
            require(fixture.requests[0]["provider_session"]["session_id"] is None, "a Codex conversation UUID was minted")
            fixture.call()
            require(fixture.argv[1][1:3] == ("exec", "resume"), "warm call was not a resume")
            require(fixture.argv[1][-2] == SESSION_A, "warm call guessed a thread")
            require('sandbox_mode="danger-full-access"' in fixture.argv[1], "resume lost pinned sandbox control")
            require(fixture.prompts[1].startswith(RESUMED_AUTHORITY_NOTICE), "warm turn retained old authority")
            fixture.binding.lock.release()
            replacement = fixture.build()
            fixture.takeover(replacement)
            try:
                fixture.call()
                require(len(fixture.argv) == 3, "hidden second invocation")
                require(fixture.argv[-1][-2] == SESSION_A, "clean restart discarded exact warm identity")
                record = fixture.owner.store.load().sessions[0]
                require(record.completed_assignment_count == 3, "cycle accounting was not durable")
                require(record.scope.binding("conversation_store") == "compose:nosafecircle/codex-config", "actual Compose store absent from scope")
            finally:
                replacement.lock.release()
        finally:
            fixture.binding.lock.release()


def test_codex_interrupted_cold_and_warm_assignments_require_exact_locked_recovery():
    for warm in (False, True):
        with tempfile.TemporaryDirectory() as text:
            fixture = OfflineArchitect(Path(text))
            fixture.takeover()
            try:
                if warm:
                    fixture.call()
                fixture.mode = "interrupt"
                rejects(fixture.call, KeyboardInterrupt)
                require(fixture.owner.store.load().active_assignment_count == 1, "interruption erased active assignment")
                before = len(fixture.requests)
                rejects(fixture.call, ArchitectSessionOwnerError)
                require(len(fixture.requests) == before, "active call was duplicated")
                replacement = fixture.build()
                wrong = SchedulerLock(Path(text) / "wrong.lock")
                with wrong:
                    rejects(lambda: fixture.owner.reconcile_interrupted_assignment(lock=wrong), ArchitectSessionOwnerError)
                require(fixture.owner.store.load().active_assignment_count == 1, "wrong lock mutated recovery")
            finally:
                fixture.binding.lock.release()
            fixture.takeover(replacement)
            try:
                old = fixture.owner.store.load().sessions[0]
                require(old.state == ("retired" if warm else "quarantined"), "uncertain conversation was left reusable")
                fixture.mode, fixture.response_session = "success", SESSION_B
                fixture.call()
                require(fixture.requests[-1]["provider_session"]["session_id"] is None, "interrupted session was resumed")
            finally:
                replacement.lock.release()


def test_codex_missing_or_wrong_confirmation_never_reuses_uncertain_conversation():
    for failure in ("missing_confirmation", "wrong_id", "wrong_provider", "wrong_role", "wrong_mode"):
        with tempfile.TemporaryDirectory() as text:
            fixture = OfflineArchitect(Path(text))
            fixture.takeover()
            try:
                if failure == "wrong_id":
                    fixture.call()
                    fixture.response_session = SESSION_B
                elif failure == "missing_confirmation":
                    fixture.mode = failure
                else:
                    key, value = {"wrong_provider": ("provider_identifier", "claude-code"), "wrong_role": ("role", "implementer"), "wrong_mode": ("mode", "resume")}[failure]
                    fixture.metadata_mutation = lambda metadata: metadata["provider_session_confirmation"].update({key: value})
                before = len(fixture.argv)
                rejects(fixture.call)
                require(len(fixture.argv) == before + 1, "failure caused a provider retry")
                require(all(item.state in {"retired", "quarantined"} for item in fixture.owner.store.load().sessions), "unproven identity was reusable")
            finally:
                fixture.binding.lock.release()


def test_codex_compatibility_and_storage_changes_retire_without_inheriting_history():
    for changed in ("model", "repository", "storage", "resume", "role", "protocol", "capabilities"):
        with tempfile.TemporaryDirectory() as text:
            fixture = OfflineArchitect(Path(text))
            fixture.takeover()
            fixture.call()
            fixture.binding.lock.release()
            previous = fixture.owner
            compatibility = previous.compatibility
            if changed in {"model", "role", "protocol", "capabilities"}:
                key = changed
                value = {"model": "gpt-other", "role": "implementer", "protocol": "next-protocol", "capabilities": ("repository_read",)}[changed]
                compatibility = replace(compatibility, **{key: value})
            options = dict(
                architect_runner=previous.architect_runner, compatibility=compatibility,
                source=previous.source, checkout_root=previous.checkout_root,
                repository_identity="other-origin" if changed == "repository" else "fixture-origin",
                compose_project="other-project" if changed == "storage" else "nosafecircle",
                resume_activation=CodexResumeActivation(("--config", 'sandbox_mode="danger-full-access"')) if changed == "resume" else ACTIVATION,
                scheduler_lock_type=SchedulerLock,
                scheduler_lock_path=scheduler_lock_path(checkout_root=previous.checkout_root),
            )
            if changed == "role":
                rejects(lambda: CodexArchitectSessionOwner(**options), ArchitectSessionOwnerError)
                continue
            replacement = CodexArchitectSessionOwner(**options)
            lock = SchedulerLock(scheduler_lock_path(checkout_root=previous.checkout_root))
            with lock:
                replacement.reconcile_interrupted_assignment(lock=lock)
                record = replacement.store.load().sessions[0]
                require(record.state == "retired" and record.retirement_reason == "session_incompatibility", "changed scope inherited old conversation")
                require(len(fixture.argv) == 1, "compatibility change contacted provider")


def test_codex_checkpoint_failures_poison_without_duplicate_calls():
    for stage in ("checkout", "settlement", "recovery"):
        with tempfile.TemporaryDirectory() as text:
            fixture = OfflineArchitect(Path(text))
            fixture.takeover()
            try:
                if stage == "recovery":
                    fixture.mode = "interrupt"
                    rejects(fixture.call, KeyboardInterrupt)
                    fixture.binding.lock.release()
                    replacement = fixture.build()
                    replacement.lock.acquire()
                    action = lambda: fixture.owner.reconcile_interrupted_assignment(lock=replacement.lock)
                else:
                    action = fixture.call
                save = fixture.owner.store.save
                count = 0

                def fail_save(pool):
                    nonlocal count
                    count += 1
                    if stage != "settlement" or count == 2:
                        raise OSError("fixture checkpoint failure")
                    return save(pool)

                with patch.object(fixture.owner.store, "save", side_effect=fail_save):
                    rejects(action, ArchitectSessionOwnerError)
                calls = len(fixture.requests)
                rejects(fixture.call, ArchitectSessionOwnerError)
                require(len(fixture.requests) == calls, "persistence failure launched a duplicate call")
                require(calls == (0 if stage == "checkout" else 1), "unexpected invocation count")
                if stage != "checkout":
                    require(fixture.owner.store.load().active_assignment_count == 1, "failed settlement hid stranded assignment")
            finally:
                fixture.binding.lock.release()
                if stage == "recovery":
                    replacement.lock.release()


def test_codex_context_and_completed_cycle_retirement_preserve_final_result():
    for budget in ("context", "cycles"):
        with tempfile.TemporaryDirectory() as text:
            fixture = OfflineArchitect(Path(text))
            fixture.takeover()
            try:
                fixture.call()
                if budget == "context":
                    fixture.metadata_mutation = lambda metadata: metadata.update(known_context_window_percent=70)
                else:
                    record = fixture.owner.pool.sessions[0]
                    lifecycle = replace(record.lifecycle, sequence=198, completed_assignments=99, architect_completed_admission_cycles=99)
                    # Restore an actual serialized pool at the committed boundary.
                    payload = fixture.owner.pool.to_dict()
                    payload["sessions"][0] = replace(record, completed_assignment_count=99, lifecycle=lifecycle).to_dict()
                    fixture.owner.pool = type(fixture.owner.pool).from_dict(payload, lifetime=fixture.owner.store.lifetime)
                    fixture.owner.store.save(fixture.owner.pool)
                result = fixture.call()
                require(result.batch.source_head == SOURCE_HEAD, "retirement discarded the valid final decision")
                require(fixture.owner.store.load().sessions[0].state == "retired", "committed retirement boundary ignored")
            finally:
                fixture.binding.lock.release()


def test_codex_missing_activation_fails_factory_before_any_invocation():
    with tempfile.TemporaryDirectory() as text, patch.dict("os.environ", {"NSC_CODEX_RESUME_SANDBOX_ARGUMENT": ""}), \
            patch("Pipeline.TaskReviewAgent.supervisor_session_pool._repository_identity", return_value="fixture-origin"), \
            patch("Pipeline.TaskReviewAgent.polling_orchestrator.repo_root", side_effect=lambda source: source), \
            patch("subprocess.Popen", side_effect=AssertionError("unexpected executable")):
        rejects(lambda: build_production_orchestrator(source=Path(text) / "source", checkout_root=Path(text) / "checkouts", architect_provider="codex"), ArchitectSessionOwnerError)


def test_codex_confirmed_failures_use_shared_budget_without_internal_retry():
    with tempfile.TemporaryDirectory() as text:
        fixture = OfflineArchitect(Path(text))
        fixture.takeover()
        try:
            fixture.mode = "provider_failure"
            rejects(fixture.call)
            require(len(fixture.argv) == 1, "provider failure caused internal retry")
            require(fixture.owner.store.load().sessions[0].state == "probation", "one confirmed failure ignored shared probation policy")
            rejects(fixture.call)
            require(len(fixture.argv) == 2, "explicit next assignment made duplicate calls")
            record = fixture.owner.store.load().sessions[0]
            require(record.state == "retired" and record.retirement_reason == "consecutive_provider_output_failures", "two confirmed failures ignored retirement policy")
            require(record.lifecycle.architect_completed_admission_cycles == 0, "failed decisions counted as completed admission cycles")
        finally:
            fixture.binding.lock.release()


def test_codex_preflight_rejects_malformed_resume_control_before_provider_work():
    for invalid in (None, "-c", 7, {"-c": 1, 'sandbox_mode="danger-full-access"': 2}):
        with tempfile.TemporaryDirectory() as text:
            request = dict(source_head=SOURCE_HEAD, candidates=portfolio(), reservations=[], admission_limit=2,
                provider_session={"schema_version": "1.0", "provider_identifier": "openai-codex", "role": "polling_architect", "mode": "start", "session_id": None},
                codex_resume_sandbox_argument=invalid)
            with patch.object(sys, "stdin", io.StringIO(json.dumps(request))), \
                    patch.object(OpenAICodexProvider, "_run", side_effect=AssertionError("unexpected provider call")), \
                    contextlib.redirect_stderr(io.StringIO()):
                status = preflight.main(["--source", text, "--artifact-root", str(Path(text) / "artifacts"), "--scheduler-id", "fixture", "--provider", "codex"])
            require(status == 2, "malformed control reached the provider")


CODEX_TESTS = (
    test_codex_factory_fresh_warm_and_restart_use_transcript_identity,
    test_codex_interrupted_cold_and_warm_assignments_require_exact_locked_recovery,
    test_codex_missing_or_wrong_confirmation_never_reuses_uncertain_conversation,
    test_codex_compatibility_and_storage_changes_retire_without_inheriting_history,
    test_codex_checkpoint_failures_poison_without_duplicate_calls,
    test_codex_context_and_completed_cycle_retirement_preserve_final_result,
    test_codex_missing_activation_fails_factory_before_any_invocation,
    test_codex_confirmed_failures_use_shared_budget_without_internal_retry,
    test_codex_preflight_rejects_malformed_resume_control_before_provider_work,
)


if __name__ == "__main__":
    for test in CODEX_TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"Codex architect pool tests: PASS ({len(CODEX_TESTS)} tests)")
