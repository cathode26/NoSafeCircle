#!/usr/bin/env python3
"""Quota handoff regression tests using real crew/runtime code and fake providers.

Classification: pure/component and temporary-repository orchestration tests.
These prove regression-only provider, role, scope, provenance, and session gates;
they do not prove a Unity acceptance criterion or fabricate human verification.
No provider executable, Docker, network, Unity, real task or claim is used.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.process_runner import ProcessResult
from Pipeline.AgentRuntime.provider_failover import claude_quota_evidence
from Pipeline.AgentRuntime.providers.base import ProviderFailure, ProviderInvocationResponse, ProviderQuotaExhausted
from Pipeline.AgentRuntime.providers.claude_code import ClaudeCodeProvider
from Pipeline.ExecutionCrew.run_crew import CrewBlocked, run_crew, load_retry_context, capture_source
from Pipeline.ExecutionCrew.tests import pooled_run_crew_smoke_test as shared
from Pipeline.TaskReviewAgent.execution_session_pool import ExecutionCrewSessionPoolOwner, ExecutionCrewSessionPoolError
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge, ExecutionBridgeError

# The shared fake model must also satisfy the real Claude adapter's syntax check.
shared.MODEL = "claude-quota-fixture"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def quota_terminal(**changes):
    value = {"type": "result", "is_error": True, "subtype": "error_during_execution",
             "terminal_reason": "error", "error": {"type": "quota_exhausted"}}
    value.update(changes)
    return value


class QuotaProcess:
    """Only emits terminal bytes; never starts a subprocess."""
    def __init__(self, session, *, omit_identity=False):
        self.session = session
        self.omit_identity = omit_identity

    def run(self, argv, **kwargs):
        terminal = quota_terminal()
        # Quota proof does not depend on the optional terminal_reason field
        # required by the separate legacy success parser.
        del terminal["terminal_reason"]
        if self.session is not None and not self.omit_identity:
            terminal["session_id"] = self.session.session_id
        return ProcessResult(argv, 1, (json.dumps(terminal) + "\n").encode(), b"", 0.01)


class FakeRole(shared.PooledFakeProvider):
    def invoke(self, request, model):
        attempt = self.state.attempts(self.role) + 1
        self.state.invocations.append({"role": self.role, "attempt": attempt,
            "provider": self.provider_identifier, "request": request, "repo": self.repo,
            "session": self.session})
        is_claude = self.provider_identifier == "claude-code"
        if is_claude and self.role == self.state.quota_role:
            if self.state.scenario == "quota_after_repair" and attempt == 1:
                self.session_ledger.record(self.session.confirm(self.session.session_id))
                raise ProviderFailure("fake structured-output formatting failure", raw_log="fake format failure")
            if self.state.scenario == "unrelated":
                raise ProviderFailure("authentication denied, quota_exhausted mentioned only in text", raw_log="auth failure")
            if self.state.scenario != "pass":
                if self.writable:
                    target = shared.OTHER if self.state.scenario == "scope_escape" else (
                        shared.TEST if self.role == "test_author" else shared.IMPL)
                    shared.write(self.repo / target, "public class PlayerMana { public int Partial; }\n")
                adapter = ClaudeCodeProvider(repository_root=self.repo,
                    externally_isolated_writable_repository=self.writable,
                    session=self.session, session_ledger=self.session_ledger,
                    process_runner=QuotaProcess(self.session, omit_identity=self.state.scenario == "quota_no_identity"))
                return adapter.invoke(request, model)
        if self.session is not None:
            session_id = self.session.session_id or f"beef0000-1111-4111-8111-{next(self.state.assigned):012x}"
            self.session_ledger.record(self.session.confirm(session_id))
        if not is_claude and self.role == "implementer":
            if self.state.scenario != "pass":
                require("Partial" in (self.repo / shared.IMPL).read_text(), "partial work was concealed or reset")
            if self.state.scenario == "fallback_failure":
                raise ProviderQuotaExhausted("Codex account exhausted too", raw_log="fake Codex quota evidence")
        output = self.role_output(attempt)
        return ProviderInvocationResponse(output, "fake role completed\n")


def role_factory(state):
    def create(provider, repo, writable, role, session=None, session_ledger=None):
        identifier = {"claude": "claude-code", "codex": "openai-codex"}[provider]
        key = provider + "-crew"
        config = RuntimeConfiguration({key: {"provider": identifier,
            "models": {name: shared.MODEL for name in shared.ROLE_CLASSES.values()}}})
        fake = FakeRole(state, repo, writable, role, session, session_ledger)
        fake.provider_identifier = identifier
        return key, config, {identifier: fake}
    return create


@contextmanager
def case(scenario="quota", *, pooled=False, primary="claude", permitted=("claude", "codex"), fallback="codex", quota_role="implementer"):
    with tempfile.TemporaryDirectory(prefix="quota-crew-") as text:
        parent = Path(text)
        source = shared.fixture(parent)
        head, checkout = shared.source_identity(source)
        state = shared.State(scenario)
        state.quota_role = quota_role
        pool = shared.new_pool()
        run_id = "quota-regression"
        leases = {role: shared.lease_for(pool, role, head=head, checkout=checkout, run_id=run_id)
                  for role in shared.ROLE_CLASSES} if pooled else None
        with patch("time.sleep", side_effect=AssertionError("quota recovery must never sleep")), patch(
                "Pipeline.ExecutionCrew.run_crew.construct_real_provider",
                side_effect=AssertionError("live provider construction forbidden")):
            result = run_crew(source=source, output_root=parent / "outputs", task_id=shared.TASK,
                provider_name=primary, run_id=run_id, implementation_paths=(shared.IMPL,), test_paths=(shared.TEST,),
                execution_model=shared.MODEL, crew_profile="full", validation_profile="full_relevant",
                provider_factory=role_factory(state), _require_physical_read_only_source=False,
                provider_allowlist=permitted, quota_fallback_provider=fallback, role_session_leases=leases,
                scheduler_repository_identity=shared.REPOSITORY if pooled else None)
        require(shared.cmd(source, "status", "--porcelain=v1", "--untracked-files=all") == "", "fixture source mutated")
        yield result, state, parent / "outputs" / run_id, pool, leases


def test_structured_quota_requires_explicit_completed_machine_evidence():
    require(claude_quota_evidence((quota_terminal(),)) == "terminal_error:quota_exhausted", "quota not recognized")
    terminal = quota_terminal()
    del terminal["error"]
    del terminal["terminal_reason"]
    rejected = {"type": "rate_limit_event", "rate_limit_info": {
        "status": "rejected", "rateLimitType": "five_hour", "resetsAt": 2000000000}}
    require(claude_quota_evidence((rejected, terminal)) == "rejected_account_window:five_hour", "window not recognized")
    negatives = [quota_terminal(is_error=False), quota_terminal(terminal_reason="completed"),
                 quota_terminal(permission_denials=["Edit"]), quota_terminal(structured_output={}),
                 quota_terminal(error={"type": "authentication_error"}),
                 quota_terminal(error={"code": "rate_limit_error"}),
                 quota_terminal(subtype="error_max_turns"),
                 quota_terminal(error="quota_exhausted")]
    for value in negatives:
        require(claude_quota_evidence((value,)) is None, f"nonquota accepted: {value}")
    rejected["rate_limit_info"]["status"] = "allowed_warning"
    require(claude_quota_evidence((rejected, terminal)) is None, "warning authorized handoff")
    for raw in (json.dumps(quota_terminal()) + "\n{}\n", '{"type":"result","type":"result"}\n'):
        try:
            ClaudeCodeProvider()._response_from_result(ProcessResult(("fake",), 1, raw.encode(), b"", 0.01))
        except ProviderQuotaExhausted:
            raise AssertionError("malformed transcript authorized handoff")
        except Exception:
            pass


def assert_success(result, state, run_dir):
    require(result["crew_status"] == "review_ready", result["rejection_reasons"])
    calls = state.for_role("implementer")
    require([call["provider"] for call in calls] == ["claude-code", "openai-codex"], "handoff was retried or duplicated")
    first, second = (call["request"] for call in calls)
    require(calls[0]["repo"] == calls[1]["repo"], "handoff created another worker checkout")
    for field in ("role", "allowed_capabilities", "write_boundaries", "context_paths", "model_capability_class", "budgets", "output_schema"):
        require(getattr(first, field) == getattr(second, field), "handoff changed " + field)
    require(calls[1]["session"].provider_identifier == "openai-codex" and
            calls[1]["session"].mode == "start" and calls[1]["session"].session_id is None,
            "Codex resumed the exhausted Claude session")
    require(len(state.invocations) == 5, "earlier roles reran or a second worker was hidden")
    require(set(result["provider_handoffs"]) == {"implementer"}, "wrong roles handed off")
    handoff = result["provider_handoffs"]["implementer"]
    require(handoff["status"] == "succeeded" and handoff["partial_changed_paths"] == [shared.IMPL], "handoff evidence lost")
    partial = (run_dir / handoff["partial_patch_path"]).read_bytes()
    require(b"Partial" in partial and hashlib.sha256(partial).hexdigest() == handoff["partial_patch_sha256"], "partial patch lost")
    failure = result["provider_quota_failures"]["implementer"]
    for metadata in failure["evidence"].values():
        require(hashlib.sha256((run_dir / metadata["path"]).read_bytes()).hexdigest() == metadata["sha256"], "failed evidence changed")
    records = [json.loads((run_dir / path).read_text()) for path in result["role_results"]]
    role = next(item for item in records if item["role"] == "implementer")
    require(role["provider"] == "openai-codex", "final role result claims Claude authored Codex work")
    require(result["human_result"]["status"] == "REVIEW_READY", "human PASS fabricated")
    validator = next(item for item in records if item["role"] == "validator")
    require(any(item["id"] == "VAL-001" and item["status"] == "not_proven"
                for item in validator["structured_output"]["criteria_results"]), "human/runtime gate weakened")
    require(result["crew_profile"] == "full" and result["validation_profile"] == "full_relevant", "rigor downgraded")


def test_real_crew_preserves_scope_partial_changes_and_evidence():
    with case() as (result, state, run_dir, _, _):
        assert_success(result, state, run_dir)
        source = run_dir.parent.parent / "source"
        feedback = run_dir.parent / "feedback.txt"
        feedback.write_text("Inspect the reviewed candidate and add the requested regression assertion.\n")
        retry = load_retry_context(source=source, identity=capture_source(source), output_root=run_dir.parent,
                                   prior_run_id=result["run_id"], feedback_file=feedback)
        require(retry.provider_allowlist == ("claude", "codex") and retry.quota_fallback_provider == "codex",
                "retry lost the prior provider permission decision")
        try:
            run_crew(source=source, output_root=run_dir.parent, retry_run_id=result["run_id"],
                     review_feedback_file=feedback, provider_allowlist=("claude",),
                     provider_factory=lambda *_: (_ for _ in ()).throw(AssertionError("provider ran before retry policy validation")),
                     _require_physical_read_only_source=False)
        except CrewBlocked as exc:
            require("allowlist differs" in str(exc), str(exc))
        else:
            raise AssertionError("retry silently replaced its original permissions")

        accepted = SimpleNamespace(task_id=shared.TASK, lease_id="fixture-lease", plan_id="fixture-plan",
            source_head=result["source_head"], task_contract_sha256=result["task_contract_identity"]["sha256"],
            plan=SimpleNamespace(existing_implementation_paths=(shared.IMPL,), new_implementation_paths=(),
                                 existing_test_paths=(shared.TEST,), new_test_paths=()))
        commands = []
        def runner(command, *_):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, json.dumps(result).encode(), b"")
        bridge = ExecutionCrewBridge(checkout=source, scope=SimpleNamespace(task_id=shared.TASK),
            command_runner=runner, provider_allowlist=("claude", "codex"), quota_fallback_provider="codex")
        bridge.output_root = run_dir.parent
        receipt = bridge._run_prepared(accepted=accepted, provider="claude", retry_run_id=None,
                                      feedback=None, pool_owner=None, pool_assignment=None)
        require(bridge.require(receipt.run_id) == receipt, "handoff receipt did not survive reload checks")
        command = commands[0]
        require(len(commands) == 1 and command[command.index("--provider-allowlist")+1] == "claude,codex",
                "bridge duplicated the worker or omitted permissions")
        require(command[command.index("--quota-fallback-provider")+1] == "codex", "fallback not forwarded")
        require("nosafecircle_codex-config:/home/agent/.codex" in command, "authorized Codex config unavailable")
        require(receipt.result_sha256 == hashlib.sha256((run_dir/"crew_result.json").read_bytes()).hexdigest(),
                "receipt did not bind the full handoff evidence")
        bridge.provider_allowlist = ("claude",)
        bridge.quota_fallback_provider = None
        try:
            bridge._validate_result(result, accepted=accepted, provider="claude")
        except ExecutionBridgeError:
            pass
        else:
            raise AssertionError("receipt accepted a handoff outside run permissions")


def test_pool_quarantines_exhausted_lease_and_never_reuses_codex_as_claude():
    with case(pooled=True) as (result, state, run_dir, pool, leases):
        assert_success(result, state, run_dir)
        require("implementer" not in result["durable_assignment_results"], "Codex result recycled a Claude lease")
        assignment = {"run_id": result["run_id"], "task_id": shared.TASK, "source_commit": result["source_head"],
                      "model": shared.MODEL, "task_contract_sha256": result["task_contract_identity"]["sha256"],
                      "leases": {role: lease.to_dict() for role, lease in leases.items()}}
        owner = object.__new__(ExecutionCrewSessionPoolOwner)
        # Prove settlement validates failed artifacts before touching any lease.
        bad = deepcopy(result)
        bad["provider_quota_failures"]["implementer"]["evidence"]["result.json"]["sha256"] = "0" * 64
        try:
            owner._settle_payload(pool, assignment, bad, run_dir)
        except ExecutionCrewSessionPoolError:
            pass
        else:
            raise AssertionError("tampered quota evidence was accepted")
        require(len(pool.sessions_for("active")) == 4, "failed evidence mutated pool")
        owner._settle_payload(pool, assignment, result, run_dir)
        quarantine = pool.sessions_for("quarantined")
        require(len(quarantine) == 1 and quarantine[0].record_id == leases["implementer"].record_id,
                "exhausted session was not quarantined")
        require(len(pool.sessions_for("idle")) == 3, "other roles lost valid session evidence")


def test_no_fallback_for_unrelated_errors_forbidden_codex_or_second_exhaustion():
    for scenario, permitted, fallback, expected in (
            ("unrelated", ("claude", "codex"), "codex", ["claude-code"]),
            ("quota", ("claude",), None, ["claude-code"]),
            ("fallback_failure", ("claude", "codex"), "codex", ["claude-code", "openai-codex"]),
            ("scope_escape", ("claude", "codex"), "codex", ["claude-code"])):
        with case(scenario, permitted=permitted, fallback=fallback) as (result, state, run_dir, _, _):
            require(result["crew_status"] != "review_ready", f"{scenario} fabricated success")
            require(result["candidate_patch_sha256"] is None, f"{scenario} emitted accepted evidence")
            require([call["provider"] for call in state.for_role("implementer")] == expected, f"{scenario} retried/fell back")
            if scenario == "fallback_failure":
                require(result["provider_handoffs"]["implementer"]["status"] == "failed", "fallback failure concealed")
            else:
                require(not result["provider_handoffs"], f"{scenario} authorized a handoff")


def test_codex_only_never_invokes_claude_and_invalid_routes_fail_before_work():
    with case("pass", primary="codex", permitted=("codex",), fallback=None) as (result, state, _, _, _):
        require(result["crew_status"] == "review_ready", result["rejection_reasons"])
        require({call["provider"] for call in state.invocations} == {"openai-codex"}, "Claude ran in Codex-only mode")
    for permitted, fallback in ((("codex",), None), (("claude",), "codex"), (None, "codex")):
        try:
            with case(permitted=permitted, fallback=fallback):
                pass
        except CrewBlocked as exc:
            require("permitted" in str(exc), str(exc))
        else:
            raise AssertionError("invalid route ran")


def test_all_roles_preserve_their_own_scope_and_unconfirmed_source_session_is_never_invented():
    for role in ("contract_locality_auditor", "test_author", "validator"):
        with case(quota_role=role) as (result, state, _, _, _):
            require(result["crew_status"] == "review_ready", result["rejection_reasons"])
            calls = state.for_role(role)
            require([item["provider"] for item in calls] == ["claude-code", "openai-codex"], "wrong role replayed")
            first, second = [item["request"] for item in calls]
            require(first.write_boundaries == second.write_boundaries and first.allowed_capabilities == second.allowed_capabilities,
                    "role authority changed at handoff")
            require(len(state.invocations) == 5, "handoff replayed other roles")
    with case("quota_no_identity", pooled=True) as (result, state, run_dir, _, _):
        assert_success(result, state, run_dir)
        failure = result["provider_quota_failures"]["implementer"]
        require(failure["confirmed_session"] is None and failure["session_disposition"] == "quarantined",
                "unproven old session identity was fabricated")


def test_quota_after_existing_format_repair_still_hands_off_only_once():
    with case("quota_after_repair", pooled=True) as (result, state, _, _, _):
        require(result["crew_status"] == "review_ready", result["rejection_reasons"])
        calls = state.for_role("implementer")
        require([item["provider"] for item in calls] == ["claude-code", "claude-code", "openai-codex"],
                "format repair concealed or duplicated the quota handoff")
        require(calls[1]["session"].mode == "resume" and calls[1]["session"].session_id == calls[0]["session"].session_id,
                "existing format repair opened a second Claude session")
        require(calls[2]["session"].mode == "start" and calls[2]["session"].session_id is None,
                "Codex resumed Claude after the format repair")
        require(result["provider_handoffs"]["implementer"]["failed_run_id"].endswith("-r2"),
                "handoff refers to the wrong failed provider attempt")


TESTS = (test_structured_quota_requires_explicit_completed_machine_evidence,
         test_real_crew_preserves_scope_partial_changes_and_evidence,
         test_pool_quarantines_exhausted_lease_and_never_reuses_codex_as_claude,
         test_no_fallback_for_unrelated_errors_forbidden_codex_or_second_exhaustion,
         test_codex_only_never_invokes_claude_and_invalid_routes_fail_before_work,
         test_all_roles_preserve_their_own_scope_and_unconfirmed_source_session_is_never_invented,
         test_quota_after_existing_format_repair_still_hands_off_only_once)


if __name__ == "__main__":
    for test in TESTS:
        test()
        print("PASS", test.__name__, flush=True)
    print(f"{len(TESTS)} quota failover tests passed")
