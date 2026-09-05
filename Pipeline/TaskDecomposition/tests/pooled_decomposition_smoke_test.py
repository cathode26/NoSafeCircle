#!/usr/bin/env python3
"""Behavioral regressions for durable, role-scoped decomposition sessions.

Every test runs the real D1B.1 / D1B.2 runners against a synthetic committed
graph with session-aware fake providers, and the real host owner
(`DecompositionSessionPoolOwner`) around them: prepare a lease bundle, run
the circuit in-process where Docker would run it, settle from the run's
durable artifacts. No Docker, Claude, Codex, GitHub, Unity, or network call is
made.
"""

from __future__ import annotations

from copy import deepcopy
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Callable
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for _module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))

from Pipeline.AgentRuntime.config import RuntimeConfiguration  # noqa: E402
from Pipeline.AgentRuntime.contracts import Usage  # noqa: E402
from Pipeline.AgentRuntime.provider_sessions import (  # noqa: E402
    ProviderSessionBinding,
    ProviderSessionLedger,
)
from Pipeline.AgentRuntime.providers.base import ProviderInvocationResponse, ProviderTimeout  # noqa: E402
from TaskDecomposition.context_builder import DecompositionPreflightError  # noqa: E402
from TaskDecomposition.live_decomposition import run_live_decomposition  # noqa: E402
from TaskDecomposition.policy import validate_decomposition_result  # noqa: E402
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    candidate_sha256,
    run_round_robin_decomposition,
)
from TaskDecomposition.session_pool_support import (  # noqa: E402
    POOLED_ROUND_EVIDENCE_FIELDS,
    DecompositionSessionError,
    lease_bundle_from_dict,
    load_lease_bundle,
)
from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (  # noqa: E402
    pass_review,
    revise_review,
)
from TaskDecomposition.tests.test_support import (  # noqa: E402
    create_repository,
    decomposed_result,
)
from Pipeline.TaskReviewAgent.decomposition_session_pool import (  # noqa: E402
    DecompositionSessionPoolError,
    DecompositionSessionPoolOwner,
    possible_lease_keys,
)
from Pipeline.TaskReviewAgent.supervisor_session_pool import CodexResumeActivation  # noqa: E402


TASK = "NSC-010"
REPOSITORY = "https://example.invalid/nosafecircle.git"
MODEL = "deterministic-fake-model"
ACTIVATION = CodexResumeActivation(("-c", 'sandbox_mode="danger-full-access"'))
PROVIDER_MODELS = {"claude": (MODEL, None), "codex": (MODEL, "high")}
COMPOSE_PROJECT = "nosafecircle-m2a"
T0 = dt.datetime(2026, 9, 5, 9, 0, tzinfo=dt.timezone.utc)


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


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout.strip()


class SessionFakeProvider:
    """Session-aware fake provider: proves the identity it was given, or misbehaves on request."""

    def __init__(self, identifier: str, outputs: list[Any], *, session: ProviderSessionBinding | None,
                 ledger: ProviderSessionLedger | None, behaviors: list[str], log: list[dict[str, Any]],
                 usage_tokens: int, factory_role: str) -> None:
        self.provider_identifier = identifier
        self.factory_role = factory_role
        self.reasoning_effort = "high" if identifier == "openai-codex" else None
        self.outputs = outputs
        self.session = session
        self.ledger = ledger
        self.behaviors = behaviors
        self.log = log
        self.usage_tokens = usage_tokens

    def invoke(self, request, model):
        behavior = self.behaviors.pop(0) if self.behaviors else "ok"
        require(self.factory_role == request.role, f"factory role {self.factory_role!r} differs from invocation role {request.role!r}")
        require(self.session is None or self.session.role == request.role, "a session bound to another role reached this invocation")
        confirmed_id = None
        if self.session is not None and self.ledger is not None and behavior != "unproven":
            if self.session.session_id is not None:
                confirmed_id = self.session.session_id
            else:
                confirmed_id = str(uuid.uuid4())
            if behavior == "wrong_thread":
                confirmed_id = "9c858901-8a57-4791-81fe-4c455b099bc9"
                if self.session.session_id is not None:
                    # A pre-bound conversation cannot be re-identified; the
                    # adapter would raise before confirming. Emulate that.
                    confirmed_id = None
            if confirmed_id is not None:
                self.ledger.record_confirmed(self.session.confirm(confirmed_id))
        self.log.append({
            "provider": self.provider_identifier, "role": request.role, "factory_role": self.factory_role, "prompt": request.prompt,
            "requested_mode": None if self.session is None else self.session.mode,
            "requested_session_id": None if self.session is None else self.session.session_id,
            "confirmed_session_id": confirmed_id, "behavior": behavior,
        })
        if behavior == "timeout":
            raise ProviderTimeout("fake timeout", raw_log="fake\n")
        if not self.outputs:
            raise AssertionError(f"{self.provider_identifier} {request.role} was invoked more than configured")
        output = self.outputs.pop(0)
        return ProviderInvocationResponse(output, "fake provider log\n", (), Usage(self.usage_tokens, 5, self.usage_tokens + 5), False, ())


class Fixture:
    """One synthetic repository plus a host owner and session-aware provider queues."""

    def __init__(self, base: Path, *, activation: CodexResumeActivation | None = ACTIVATION,
                 provider_models=None, context_window: int | None = None,
                 clock: Callable[[], dt.datetime] | None = None) -> None:
        self.base = base
        self.source = base / "checkouts" / TASK
        self.output_root = base / "output"
        self.source.parent.mkdir(parents=True, exist_ok=True)
        self.tasks = create_repository(self.source)
        git(self.source, "remote", "add", "origin", REPOSITORY)
        manifest = self.source.parent / ".task-review-agent" / f"{TASK}.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"schema_version": "2", "task_id": TASK}), encoding="utf-8")
        self.head = git(self.source, "rev-parse", "HEAD")
        self.parent = self.tasks[TASK]
        self.owner = DecompositionSessionPoolOwner(
            checkout=self.source, repository_identity=REPOSITORY,
            provider_models=provider_models or PROVIDER_MODELS, codex_resume_activation=activation, compose_project=COMPOSE_PROJECT,
            context_window_tokens=context_window, clock=clock or (lambda: T0), host_identity="test-host",
        )
        self.outputs: dict[str, list[Any]] = {"claude": [], "codex": []}
        self.behaviors: dict[str, list[str]] = {"claude": [], "codex": []}
        self.log: list[dict[str, Any]] = []
        self.usage_tokens = 1000

    def candidate(self):
        raw = decomposed_result(self.parent)
        result = validate_decomposition_result(
            raw, parent_task=self.parent,
            existing_reconciliation_keys=(task["reconciliation_key"] for task in self.tasks.values()),
        )
        return raw, candidate_sha256(result)

    def factory(self):
        def build(provider_name: str, _source: Path, role: str, session=None, ledger=None, resume_argument=None):
            identifier = {"claude": "claude-code", "codex": "openai-codex"}[provider_name]
            key = f"{provider_name}-decomposition"
            configuration = RuntimeConfiguration({key: {"provider": identifier, "models": {
                "low_cost": MODEL, "standard": MODEL, "high_reasoning": MODEL}}})
            if session is not None and identifier == "openai-codex" and session.is_resume:
                require(resume_argument == ACTIVATION.argument, "codex resume must carry the verified control")
            provider = SessionFakeProvider(
                identifier, self.outputs[provider_name], session=session, ledger=ledger,
                behaviors=self.behaviors[provider_name], log=self.log, usage_tokens=self.usage_tokens,
                factory_role=role,
            )
            return key, configuration, {identifier: provider}
        return build

    def run(self, run_id: str, *, order=("claude", "codex"), max_calls: int = 2, mode: str = "round_robin_d1b2",
            settle: bool = True) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
        assignment = self.owner.prepare(
            run_id=run_id, task_id=TASK, decomposition_mode=mode, provider_order=tuple(order),
            max_calls=max_calls, source_commit=self.head, worker_id="worker-1",
        )
        bundle = load_lease_bundle(assignment["lease_bundle_path"], run_id=run_id)
        if mode == "d1b1":
            result = run_live_decomposition(
                source=self.source, output_root=self.output_root, task_id=TASK, provider_name=order[0],
                run_id=run_id, provider_factory=self.factory(), _require_physical_read_only_source=False,
                lease_bundle=bundle, scheduler_repository_identity=REPOSITORY,
            )
        else:
            result = run_round_robin_decomposition(
                source=self.source, output_root=self.output_root, task_id=TASK, provider_order=tuple(order),
                max_calls=max_calls, run_id=run_id, provider_factory=self.factory(),
                _require_physical_read_only_source=False, lease_bundle=bundle,
                scheduler_repository_identity=REPOSITORY,
            )
        settlement = self.owner.settle(run_id=run_id, run_dir=self.output_root / run_id) if settle else None
        return assignment, result, settlement

    def rounds(self, role: str | None = None, provider: str | None = None) -> list[dict[str, Any]]:
        return [
            entry for entry in self.log
            if (role is None or entry["role"] == role) and (provider is None or entry["provider"] == provider)
        ]

    def record_states(self) -> dict[str, tuple[str, str | None]]:
        return {f"{r.scope.provider_identifier}:{r.scope.role}:{r.record_id}": (r.state, r.session_id) for r in self.owner.records()}


def fixture():
    # Liveness locks are released explicitly by every test; the flag only keeps
    # a genuine assertion failure visible instead of a Windows cleanup error.
    return tempfile.TemporaryDirectory(prefix="nsc-pooled-decomposition-", ignore_cleanup_errors=True)


def test_author_and_reviewer_sessions_are_distinct_and_resume_exactly() -> None:
    with fixture() as text:
        fx = Fixture(Path(text))
        raw, initial_hash = fx.candidate()
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        assignment, result, settlement = fx.run("run-one")
        require(result["run_status"] == "review_ready", str(result["rejection_reasons"]))
        keys = set(assignment["leases"])
        require(keys == {"claude:task_decomposer", "codex:decomposition_reviewer"}, str(keys))
        author = fx.rounds("task_decomposer")[0]
        reviewer = fx.rounds("decomposition_reviewer")[0]
        require(author["requested_mode"] == "start" and reviewer["requested_mode"] == "start", "both cold")
        require(author["confirmed_session_id"] and reviewer["confirmed_session_id"], "both confirmed")
        require(author["confirmed_session_id"] != reviewer["confirmed_session_id"], "author and reviewer conversations must differ")
        require(all(v["state"] == "idle" for v in settlement["leases"].values()), str(settlement))
        pooled = result["pooled_sessions"]
        require(pooled["claude:task_decomposer"]["confirmed_session"]["session_id"] == author["confirmed_session_id"], str(pooled))
        require(pooled["codex:decomposition_reviewer"]["confirmed_session"]["session_id"] == reviewer["confirmed_session_id"], str(pooled))
        # A later revision of the same decomposition resumes both exact conversations.
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        assignment2, result2, settlement2 = fx.run("run-two")
        author2 = fx.rounds("task_decomposer")[1]
        reviewer2 = fx.rounds("decomposition_reviewer")[1]
        require(author2["requested_mode"] == "resume" and author2["requested_session_id"] == author["confirmed_session_id"], str(author2))
        require(reviewer2["requested_mode"] == "resume" and reviewer2["requested_session_id"] == reviewer["confirmed_session_id"], str(reviewer2))
        require(result2["run_status"] == "review_ready", str(result2["rejection_reasons"]))
        require(all(v["completed_assignment_count"] == 2 for v in settlement2["leases"].values()), str(settlement2))
        require("revoked" in author2["prompt"] and "Current task: NSC-010" in author2["prompt"], author2["prompt"][:400])
        require("Current decomposition run: run-two" in author2["prompt"], "capsule names the new run")
        require("Current round: 2" in reviewer2["prompt"] and "Current reviewed candidate sha256: " + initial_hash in reviewer2["prompt"], reviewer2["prompt"][:600])
        journal = (fx.owner.journal_path).read_text(encoding="utf-8")
        require("PROMPT" not in journal and raw["children"][0]["title"] not in journal, "journal never carries prompts or candidate text")
        events = [json.loads(line)["event"] for line in journal.splitlines()]
        require(events[:2] == ["cold_start", "cold_start"] and events.count("resume") == 2, events)


def test_same_provider_serves_both_roles_through_separate_conversations() -> None:
    with fixture() as text:
        fx = Fixture(Path(text))
        raw, initial_hash = fx.candidate()
        revised_raw = deepcopy(raw)
        revised_raw["children"][0]["notes"] = "Reviewer revision one."
        revised_hash = candidate_sha256(validate_decomposition_result(
            revised_raw, parent_task=fx.parent,
            existing_reconciliation_keys=(t["reconciliation_key"] for t in fx.tasks.values())))
        revised_two = deepcopy(raw)
        revised_two["children"][0]["notes"] = "Reviewer revision two."
        revised_two_hash = candidate_sha256(validate_decomposition_result(
            revised_two, parent_task=fx.parent,
            existing_reconciliation_keys=(t["reconciliation_key"] for t in fx.tasks.values())))
        resolved = {"finding_id": "round-02-a", "status": "resolved", "explanation": "Distinct ownership now."}
        resolved_two = {"finding_id": "round-03-b", "status": "resolved", "explanation": "Distinct ownership now."}
        fx.outputs["claude"] = [raw, revise_review(revised_hash, revised_two, round_number=3, suffix="b", resolutions=[resolved])]
        fx.outputs["codex"] = [revise_review(initial_hash, revised_raw, round_number=2, suffix="a"),
                               pass_review(revised_two_hash, resolutions=[resolved_two])]
        assignment, result, settlement = fx.run("run-four", max_calls=4)
        require(result["run_status"] == "review_ready" and result["calls_used"] == 4, str(result["rejection_reasons"]))
        require(set(assignment["leases"]) == {"claude:task_decomposer", "codex:decomposition_reviewer", "claude:decomposition_reviewer"}, str(assignment["leases"].keys()))
        claude_author = fx.rounds("task_decomposer", "claude-code")[0]
        claude_reviewer = fx.rounds("decomposition_reviewer", "claude-code")[0]
        codex_rounds = fx.rounds("decomposition_reviewer", "openai-codex")
        require(claude_author["confirmed_session_id"] != claude_reviewer["confirmed_session_id"], "same provider, distinct role conversations")
        require(claude_reviewer["requested_mode"] == "start", "the reviewer role never inherits the author's conversation")
        require(claude_author["confirmed_session_id"] not in claude_reviewer["prompt"], "reviewer prompt carries no author session identity")
        require("Current role: task_decomposer" not in claude_reviewer["prompt"] and "Current role: decomposition_reviewer" in claude_reviewer["prompt"], "reviewer capsule names the reviewer role only")
        require("author one structured decomposition result" not in claude_reviewer["prompt"], "reviewer receives no author authority")
        require(len(codex_rounds) == 2 and codex_rounds[1]["requested_mode"] == "resume", "reviewer round 4 resumes the reviewer session")
        require(codex_rounds[1]["requested_session_id"] == codex_rounds[0]["confirmed_session_id"], "exact reviewer identity")
        require("(1 completed before this one)" in codex_rounds[1]["prompt"] and "revoked" in codex_rounds[1]["prompt"], codex_rounds[1]["prompt"][:500])
        pooled = result["pooled_sessions"]["codex:decomposition_reviewer"]
        require(len(pooled["rounds"]) == 2 and [r["round_number"] for r in pooled["rounds"]] == [2, 4], str(pooled))
        require(pooled["rounds"][0]["artifact_path"] == "rounds/02/candidate.json" and pooled["rounds"][1]["artifact_path"] == "rounds/04/review.json", str(pooled))
        require(all(v["state"] == "idle" for v in settlement["leases"].values()), str(settlement))
        states = fx.record_states()
        require(len(states) == 3 and len({v[1] for v in states.values()}) == 3, str(states))


def test_artifact_or_identity_tampering_refuses_check_in() -> None:
    with fixture() as text:
        fx = Fixture(Path(text))
        raw, initial_hash = fx.candidate()
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        assignment, result, _ = fx.run("run-tamper", settle=False)
        run_dir = fx.output_root / "run-tamper"
        candidate = run_dir / "rounds" / "01" / "candidate.json"
        original = candidate.read_bytes()
        candidate.write_bytes(original.replace(b"\n", b"\n", 1) + b"\n")
        round_two = run_dir / "rounds" / "02" / "round_result.json"
        payload = json.loads(round_two.read_text(encoding="utf-8"))
        payload["pooled_session"]["run_id"] = "another-run"
        round_two.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        settlement = fx.owner.settle(run_id="run-tamper", run_dir=run_dir)
        author = settlement["leases"]["claude:task_decomposer"]
        reviewer = settlement["leases"]["codex:decomposition_reviewer"]
        require(author["state"] == "retired" and author["retirement_reason"] == "identity_failure", str(author))
        require(reviewer["state"] in {"retired", "quarantined"}, str(reviewer))
        require(
            "does not carry this exact evidence block" in str(reviewer.get("quarantine_reason"))
            or reviewer["retirement_reason"] == "identity_failure",
            str(reviewer),
        )
        require("artifact hash mismatch" in (fx.owner.journal_path.read_text(encoding="utf-8")), "author artifact tamper was named in the journal")
        require(all(r.state in {"retired", "quarantined"} for r in fx.owner.records()), "no tampered conversation is reusable")
        # Replaying the settlement is idempotent.
        require(fx.owner.settle(run_id="run-tamper", run_dir=run_dir) == settlement, "terminal settlement replay is a no-op")
        # A bundle bound to another task or run fails closed before any provider runs.
        bundle = json.loads(Path(assignment["lease_bundle_path"]).read_text(encoding="utf-8"))
        wrong_task = deepcopy(bundle)
        wrong_task["task_id"] = "NSC-011"
        expect_error(lambda: lease_bundle_from_dict(wrong_task, run_id="run-tamper"), DecompositionSessionError, "another run or task")
        expect_error(lambda: lease_bundle_from_dict(bundle, run_id="run-other"), DecompositionSessionError, "bound to run")
        wrong_commit = deepcopy(bundle)
        wrong_commit["source_commit"] = "f" * 40
        expect_error(lambda: lease_bundle_from_dict(wrong_commit, run_id="run-tamper"), DecompositionSessionError, "another source commit")
        # The conversation store is the only extra scope fact a lease may bind,
        # and it must be the volume its own provider uses.
        for label, bindings, fragment in (
            ("missing", [], "exactly its provider conversation store"),
            ("extra", [["conversation_store", f"compose:{COMPOSE_PROJECT}/codex-config"], ["task_id", TASK]], "exactly its provider conversation store"),
            ("renamed", [["session_store", f"compose:{COMPOSE_PROJECT}/codex-config"]], "exactly its provider conversation store"),
            ("other provider", [["conversation_store", f"compose:{COMPOSE_PROJECT}/claude-config"]], "its provider does not use"),
            ("malformed", [["conversation_store", "codex-config"]], "its provider does not use"),
            ("bad project", [["conversation_store", "compose:Not A Project/codex-config"]], "its provider does not use"),
        ):
            tampered = deepcopy(bundle)
            tampered["leases"]["codex:decomposition_reviewer"]["scope"]["bindings"] = bindings
            expect_error(lambda: lease_bundle_from_dict(tampered, run_id="run-tamper"), DecompositionSessionError, fragment)


def test_artifact_authority_is_host_derived_and_canonical() -> None:
    """Container evidence cannot choose which host file settlement reads."""

    cases = (
        "missing-required-binding",
        "hash-without-path",
        "absolute-path",
        "traversal-path",
        "foreign-in-root-path",
        "status-role-mismatch",
        "rejected-with-artifact",
        "path-without-hash",
    )
    for label in cases:
        with fixture() as text:
            fx = Fixture(Path(text))
            raw, initial_hash = fx.candidate()
            fx.outputs["claude"] = [raw]
            fx.outputs["codex"] = [pass_review(initial_hash)]
            run_id = f"run-authority-{label}"
            _, _, _ = fx.run(run_id, settle=False)
            run_dir = fx.output_root / run_id
            summary_path = run_dir / "decomposition_run_result.json"
            round_path = run_dir / "rounds" / "01" / "round_result.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            round_result = json.loads(round_path.read_text(encoding="utf-8"))
            key = "claude:task_decomposer"
            evidence = summary["pooled_sessions"][key]["rounds"][0]
            round_evidence = round_result["pooled_session"]

            if label == "missing-required-binding":
                artifact_path, artifact_sha256 = None, None
            elif label == "hash-without-path":
                artifact_path, artifact_sha256 = None, "0" * 64
            elif label == "absolute-path":
                foreign = Path(text) / "foreign-absolute.json"
                foreign.write_bytes(b"foreign absolute artifact\n")
                artifact_path = str(foreign.resolve())
                artifact_sha256 = hashlib.sha256(foreign.read_bytes()).hexdigest()
            elif label == "traversal-path":
                foreign = run_dir.parent / "foreign-traversal.json"
                foreign.write_bytes(b"foreign traversal artifact\n")
                artifact_path = "../foreign-traversal.json"
                artifact_sha256 = hashlib.sha256(foreign.read_bytes()).hexdigest()
            elif label == "foreign-in-root-path":
                foreign = run_dir / "rounds" / "02" / "review.json"
                artifact_path = "rounds/02/review.json"
                artifact_sha256 = hashlib.sha256(foreign.read_bytes()).hexdigest()
            else:
                artifact_path = evidence["artifact_path"]
                artifact_sha256 = evidence["artifact_sha256"]
                if label == "status-role-mismatch":
                    evidence["round_status"] = round_evidence["round_status"] = "independent_pass"
                elif label == "rejected-with-artifact":
                    evidence["round_status"] = round_evidence["round_status"] = "rejected"
                elif label == "path-without-hash":
                    artifact_sha256 = None

            evidence["artifact_path"] = round_evidence["artifact_path"] = artifact_path
            evidence["artifact_sha256"] = round_evidence["artifact_sha256"] = artifact_sha256
            summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            round_path.write_text(json.dumps(round_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            settlement = fx.owner.settle(run_id=run_id, run_dir=run_dir)
            author = settlement["leases"][key]
            require(
                author["state"] == "retired" and author["retirement_reason"] == "identity_failure",
                f"{label}: non-canonical artifact evidence must retire the conversation: {author}",
            )
            require(
                settlement["leases"]["codex:decomposition_reviewer"]["state"] == "idle",
                f"{label}: the untouched reviewer still settles",
            )
            fx.owner.close()

    # D1B.1 has its own canonical publication path; a successful author may
    # not omit that binding either.
    with fixture() as text:
        fx = Fixture(Path(text))
        raw, _ = fx.candidate()
        fx.outputs["claude"] = [raw]
        run_id = "run-authority-d1b1"
        _, _, _ = fx.run(
            run_id, order=("claude",), max_calls=1, mode="d1b1", settle=False,
        )
        result_path = fx.output_root / run_id / "decomposition_run_result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        key = "claude:task_decomposer"
        result["pooled_sessions"][key]["rounds"][0]["artifact_path"] = None
        result["pooled_sessions"][key]["rounds"][0]["artifact_sha256"] = None
        result["pooled_session_evidence"]["artifact_path"] = None
        result["pooled_session_evidence"]["artifact_sha256"] = None
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        settlement = fx.owner.settle(
            run_id=run_id, run_dir=fx.output_root / run_id,
        )
        author = settlement["leases"][key]
        require(
            author["state"] == "retired" and author["retirement_reason"] == "identity_failure",
            f"D1B.1 missing canonical artifact binding must retire: {author}",
        )
        fx.owner.close()


def test_every_check_in_binding_is_verified_individually() -> None:
    fields = {
        "task_id": "NSC-011", "run_id": "another-run", "round_number": 9, "invocation_id": "nsc-010-d1b2-r09-x-000000000000",
        "role": "task_decomposer", "provider_name": "claude", "provider_identifier": "claude-code", "model": "another-model",
        "reasoning_effort": "low", "decomposition_mode": "d1b1", "source_head": "f" * 40, "checkout_identity": "manifest-sha256:" + "0" * 64,
        "lease_id": "2f2504e0-4f89-41d3-9a0c-0305e82c3302", "record_id": "2f2504e0-4f89-41d3-9a0c-0305e82c3303",
        "requested_mode": "resume", "requested_session_id": "9c858901-8a57-4791-81fe-4c455b099bc9",
        "confirmed_session": {"schema_version": "1.0", "provider_identifier": "openai-codex", "role": "decomposition_reviewer", "mode": "start", "session_id": "9c858901-8a57-4791-81fe-4c455b099bc9"},
        "artifact_sha256": "0" * 64, "protocol_version": "9.9", "lease_key": "claude:decomposition_reviewer", "repository_identity": "https://example.invalid/other.git",
        "agent_status": "failed", "source_tree": "e" * 40,
        "conversation_store": "compose:nosafecircle-other/codex-config",
    }
    require(set(fields) == set(POOLED_ROUND_EVIDENCE_FIELDS) - {"schema_version", "pool_schema_version", "artifact_path", "round_status"}, "every host-verified evidence field is tampered once")
    for field, value in fields.items():
        with fixture() as text:
            fx = Fixture(Path(text))
            raw, initial_hash = fx.candidate()
            fx.outputs["claude"] = [raw]
            fx.outputs["codex"] = [pass_review(initial_hash)]
            _, result, _ = fx.run(f"run-{field.replace('_', '-')}", settle=False)
            run_dir = fx.output_root / f"run-{field.replace('_', '-')}"
            key = "codex:decomposition_reviewer"
            summary_path = run_dir / "decomposition_run_result.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["pooled_sessions"][key]["rounds"][0][field] = value
            summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            round_path = run_dir / "rounds" / "02" / "round_result.json"
            round_result = json.loads(round_path.read_text(encoding="utf-8"))
            round_result["pooled_session"][field] = value
            round_path.write_text(json.dumps(round_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            settlement = fx.owner.settle(run_id=f"run-{field.replace('_', '-')}", run_dir=run_dir)
            reviewer = settlement["leases"][key]
            require(reviewer["state"] in {"quarantined", "retired"} and reviewer["session_id"] is None, f"{field}: tampered binding must withdraw the conversation: {reviewer}")
            require(settlement["leases"]["claude:task_decomposer"]["state"] == "idle", f"{field}: the untouched author lease still settles")
            fx.owner.close()
    # A later round that proves a different conversation than the first round of
    # the same lease is a contradiction even when every other field agrees.
    with fixture() as text:
        fx = Fixture(Path(text))
        raw, initial_hash = fx.candidate()
        revised_raw = deepcopy(raw)
        revised_raw["children"][0]["notes"] = "Reviewer revision."
        revised_hash = candidate_sha256(validate_decomposition_result(
            revised_raw, parent_task=fx.parent,
            existing_reconciliation_keys=(t["reconciliation_key"] for t in fx.tasks.values())))
        revised_two = deepcopy(raw)
        revised_two["children"][0]["notes"] = "Reviewer revision two."
        revised_two_hash = candidate_sha256(validate_decomposition_result(
            revised_two, parent_task=fx.parent,
            existing_reconciliation_keys=(t["reconciliation_key"] for t in fx.tasks.values())))
        resolved = {"finding_id": "round-02-a", "status": "resolved", "explanation": "Fixed."}
        resolved_two = {"finding_id": "round-03-b", "status": "resolved", "explanation": "Fixed."}
        fx.outputs["claude"] = [raw, revise_review(revised_hash, revised_two, round_number=3, suffix="b", resolutions=[resolved])]
        fx.outputs["codex"] = [revise_review(initial_hash, revised_raw, round_number=2, suffix="a"), pass_review(revised_two_hash, resolutions=[resolved_two])]
        _, result, _ = fx.run("run-two-rounds", max_calls=4, settle=False)
        run_dir = fx.output_root / "run-two-rounds"
        key = "codex:decomposition_reviewer"
        summary_path = run_dir / "decomposition_run_result.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        rounds = summary["pooled_sessions"][key]["rounds"]
        require(len(rounds) == 2, f"codex reviewed twice: {len(rounds)}")
        other = "9c858901-8a57-4791-81fe-4c455b099bc9"
        rounds[1]["confirmed_session"]["session_id"] = other
        rounds[1]["requested_session_id"] = other
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        round_path = run_dir / "rounds" / "04" / "round_result.json"
        round_result = json.loads(round_path.read_text(encoding="utf-8"))
        round_result["pooled_session"]["confirmed_session"]["session_id"] = other
        round_result["pooled_session"]["requested_session_id"] = other
        round_path.write_text(json.dumps(round_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        settlement = fx.owner.settle(run_id="run-two-rounds", run_dir=run_dir)
        reviewer = settlement["leases"][key]
        require(reviewer["state"] in {"quarantined", "retired"} and reviewer["session_id"] is None, f"a later round proving another conversation withdraws the lease: {reviewer}")
        fx.owner.close()


def test_container_refuses_a_lease_whose_route_differs() -> None:
    with fixture() as text:
        fx = Fixture(Path(text), provider_models={"claude": (MODEL, None), "codex": (MODEL, "low")})
        raw, initial_hash = fx.candidate()
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        # The host reserved Codex at effort "low"; the container's route resolves "high".
        exc = expect_error(lambda: fx.run("run-route"), DecompositionPreflightError, "bound to reasoning effort")
        require(fx.rounds("decomposition_reviewer") == [], "no reviewer provider ran under a mismatched lease")
        fx.owner.close()
    with fixture() as text:
        fx = Fixture(Path(text), provider_models={"claude": ("another-model", None), "codex": (MODEL, "high")})
        raw, _ = fx.candidate()
        fx.outputs["claude"] = [raw]
        expect_error(lambda: fx.run("run-route-model"), DecompositionPreflightError, "bound to model")
        require(fx.log == [], "no provider ran under a mismatched lease")
        fx.owner.close()


def test_cross_task_reuse_needs_a_fresh_capsule_that_revokes_the_prior_task() -> None:
    from TaskDecomposition.session_pool_support import PooledRoundSessions

    with fixture() as text:
        fx = Fixture(Path(text))
        raw, initial_hash = fx.candidate()
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        _, _, settlement = fx.run("run-first-task")
        first_ids = {k: v["session_id"] for k, v in settlement["leases"].items()}
        assignment = fx.owner.prepare(
            run_id="run-second-task", task_id="NSC-002", decomposition_mode="round_robin_d1b2",
            provider_order=("claude", "codex"), max_calls=2, source_commit=fx.head, worker_id="worker-2",
        )
        for key, lease in assignment["leases"].items():
            require(lease["mode"] == "resume" and lease["session_id"] == first_ids[key], f"{key}: the repository-wide conversation is offered to the later task")
            require(dict(lease["assignment"])["task_id"] == "NSC-002", "the lease binds the new task")
        bundle = load_lease_bundle(assignment["lease_bundle_path"], run_id="run-second-task")
        require(bundle.task_id == "NSC-002", "bundle binds the new task")
        sessions = PooledRoundSessions(bundle)
        capsule = sessions.capsule_for(
            "claude:task_decomposer",
            current={"task": "NSC-002", "decomposition_run": "run-second-task", "round": "1", "source_head": fx.head},
            allowed_actions=("author one structured decomposition result for the selected task",),
        )
        require("New assignment capsule (resumed conversation)." in capsule and "revoked" in capsule, capsule[:300])
        require("Current task: NSC-002" in capsule and "NSC-010" not in capsule, "the capsule binds only the new task")
        require("(1 completed before this one)" in capsule, capsule[:400])
        fx.owner.close()


def test_unproven_identity_stops_the_run_and_quarantines() -> None:
    with fixture() as text:
        # A later round of an already-proven lease that proves nothing retires
        # the conversation as uncertain instead of returning it as idle.
        fx = Fixture(Path(text))
        raw, initial_hash = fx.candidate()
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        _, _, warm = fx.run("run-warm")
        warm_reviewer = warm["leases"]["codex:decomposition_reviewer"]
        require(warm_reviewer["state"] == "idle" and warm_reviewer["session_id"] is not None, str(warm_reviewer))
        revised_raw = deepcopy(raw)
        revised_raw["children"][0]["notes"] = "Reviewer revision."
        revised_hash = candidate_sha256(validate_decomposition_result(
            revised_raw, parent_task=fx.parent,
            existing_reconciliation_keys=(t["reconciliation_key"] for t in fx.tasks.values())))
        revised_two = deepcopy(raw)
        revised_two["children"][0]["notes"] = "Reviewer revision two."
        revised_two_hash = candidate_sha256(validate_decomposition_result(
            revised_two, parent_task=fx.parent,
            existing_reconciliation_keys=(t["reconciliation_key"] for t in fx.tasks.values())))
        resolved = {"finding_id": "round-02-a", "status": "resolved", "explanation": "Fixed."}
        resolved_two = {"finding_id": "round-03-b", "status": "resolved", "explanation": "Fixed."}
        fx.outputs["claude"] = [raw, revise_review(revised_hash, revised_two, round_number=3, suffix="b", resolutions=[resolved])]
        fx.outputs["codex"] = [revise_review(initial_hash, revised_raw, round_number=2, suffix="a"), pass_review(revised_two_hash, resolutions=[resolved_two])]
        fx.behaviors["codex"] = ["ok", "unproven"]
        assignment, result, settlement = fx.run("run-later-unproven", max_calls=4)
        require(result["run_status"] == "agent_failed", str(result["run_status"]))
        codex = result["pooled_sessions"]["codex:decomposition_reviewer"]
        require(codex["invoked"] and codex["identity_unproven"] and codex["confirmed_session"] is not None and len(codex["rounds"]) == 1, str(codex))
        require(codex["confirmed_session"]["session_id"] == warm_reviewer["session_id"], "round 2 resumed and confirmed the warm conversation")
        reviewer = settlement["leases"]["codex:decomposition_reviewer"]
        require(reviewer["state"] == "retired" and reviewer["retirement_reason"] == "interrupted_assignment", f"a proven conversation whose later round proved nothing is retired as uncertain: {reviewer}")
        require(reviewer["session_id"] == warm_reviewer["session_id"], "the retired record keeps the identity it had proven")
        fx.owner.close()
    with fixture() as text:
        fx = Fixture(Path(text))
        raw, initial_hash = fx.candidate()
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        fx.behaviors["codex"] = ["unproven"]
        assignment, result, settlement = fx.run("run-unproven")
        require(result["run_status"] == "agent_failed", str(result["run_status"]))
        require(any("provider session identity unproven" in reason for reason in result["rejection_reasons"]), str(result["rejection_reasons"]))
        require(result["pooled_sessions"]["codex:decomposition_reviewer"]["confirmed_session"] is None, "no identity adopted")
        reviewer = settlement["leases"]["codex:decomposition_reviewer"]
        require(reviewer["state"] == "quarantined" and reviewer["session_id"] is None, str(reviewer))
        require(settlement["leases"]["claude:task_decomposer"]["state"] == "idle", "the proven author conversation is unaffected")


def test_timeout_and_stranded_owner_retire_as_uncertain() -> None:
    with fixture() as text:
        fx = Fixture(Path(text))
        raw, initial_hash = fx.candidate()
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        fx.run("run-warm")
        fx.outputs["claude"] = [raw]
        fx.behaviors["codex"] = ["timeout"]
        assignment, result, settlement = fx.run("run-timeout")
        require(result["run_status"] == "agent_failed", str(result["run_status"]))
        reviewer = settlement["leases"]["codex:decomposition_reviewer"]
        require(reviewer["state"] == "retired" and reviewer["retirement_reason"] == "interrupted_assignment", str(reviewer))
        # A stranded run: prepared, never settled, owner gone. The next owner
        # holding the exact lock retires its leases as interrupted.
        fx.outputs["claude"] = [raw]
        stranded = fx.owner.prepare(
            run_id="run-stranded", task_id=TASK, decomposition_mode="round_robin_d1b2",
            provider_order=("claude", "codex"), max_calls=2, source_commit=fx.head, worker_id="worker-x",
        )
        fx.owner.close()
        successor = DecompositionSessionPoolOwner(
            checkout=fx.source, repository_identity=REPOSITORY, provider_models=PROVIDER_MODELS,
            codex_resume_activation=ACTIVATION, compose_project=COMPOSE_PROJECT, clock=lambda: T0, host_identity="test-host",
        )
        follow = successor.prepare(
            run_id="run-after-strand", task_id=TASK, decomposition_mode="round_robin_d1b2",
            provider_order=("claude", "codex"), max_calls=2, source_commit=fx.head, worker_id="worker-y",
        )
        assignments = successor.assignments()
        require(assignments["run-stranded"]["status"] == "stranded", str(assignments["run-stranded"]["status"]))
        stranded_ids = {v["record_id"] for v in stranded["leases"].values()}
        for record in successor.records():
            if record.record_id in stranded_ids:
                # A warm conversation is retired as interrupted; a cold one that
                # never proved an identity has nothing to retire and is quarantined.
                if record.session_id is not None:
                    require(record.state == "retired" and record.retirement_reason == "interrupted_assignment", str(record))
                else:
                    require(record.state == "quarantined" and "stranded run" in str(record.quarantine_reason), str(record))
        require(all(v["mode"] == "start" for v in follow["leases"].values()), "nothing stranded is resumed")
        successor.close()


def test_pool_document_is_atomic_and_internally_consistent() -> None:
    with fixture() as text:
        fx = Fixture(Path(text))
        fx.owner.prepare(
            run_id="run-doc", task_id=TASK, decomposition_mode="round_robin_d1b2",
            provider_order=("claude", "codex"), max_calls=2, source_commit=fx.head, worker_id="worker-a",
        )
        require(fx.owner.state_path.is_file() and not (fx.owner.root / "assignments.json").exists(), "one durable document")
        require(not list(fx.owner.root.glob(".state.json.*")), "no temporary file remains after the verified replace")
        document = json.loads(fx.owner.state_path.read_text(encoding="utf-8"))
        require(set(document) == {"schema_version", "pool", "assignments"}, str(document.keys()))
        document["assignments"] = {}
        fx.owner.state_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        expect_error(lambda: fx.owner.records(), DecompositionSessionPoolError, "no assignment names")
        fx.owner.close()


def test_cancel_unstarted_returns_leases_uncharged_and_only_to_the_lock_holder() -> None:
    with fixture() as text:
        fx = Fixture(Path(text))
        raw, initial_hash = fx.candidate()
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        _, _, settlement = fx.run("run-warm")
        ids = {k: v["session_id"] for k, v in settlement["leases"].items()}
        fx.owner.prepare(
            run_id="run-never-started", task_id=TASK, decomposition_mode="round_robin_d1b2",
            provider_order=("claude", "codex"), max_calls=2, source_commit=fx.head, worker_id="worker-a",
        )
        other = DecompositionSessionPoolOwner(
            checkout=fx.source, repository_identity=REPOSITORY, provider_models=PROVIDER_MODELS,
            codex_resume_activation=ACTIVATION, compose_project=COMPOSE_PROJECT, clock=lambda: T0, host_identity="test-host",
        )
        expect_error(lambda: other.cancel_unstarted(run_id="run-never-started"), DecompositionSessionPoolError, "only the owner holding")
        other.close()
        fx.owner.cancel_unstarted(run_id="run-never-started")
        require(fx.owner.assignments()["run-never-started"]["status"] == "cancelled", "the run is recorded as cancelled")
        records = {r.session_id: r for r in fx.owner.records()}
        for key, session_id in ids.items():
            require(records[session_id].state == "idle" and records[session_id].completed_assignment_count == 1, f"{key}: returned uncharged: {records[session_id]}")
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        assignment, _, _ = fx.run("run-after-cancel")
        require({k: v["session_id"] for k, v in assignment["leases"].items()} == ids, "the returned conversations resume exactly")
        fx.owner.close()


def test_concurrent_double_checkout_fails_closed() -> None:
    with fixture() as text:
        fx = Fixture(Path(text))
        fx.owner.prepare(
            run_id="run-a", task_id=TASK, decomposition_mode="round_robin_d1b2",
            provider_order=("claude", "codex"), max_calls=2, source_commit=fx.head, worker_id="worker-a",
        )
        expect_error(lambda: fx.owner.prepare(
            run_id="run-a", task_id=TASK, decomposition_mode="round_robin_d1b2",
            provider_order=("claude", "codex"), max_calls=2, source_commit=fx.head, worker_id="worker-a",
        ), DecompositionSessionPoolError, "already exists")
        second = fx.owner.prepare(
            run_id="run-b", task_id="NSC-002", decomposition_mode="round_robin_d1b2",
            provider_order=("claude", "codex"), max_calls=2, source_commit=fx.head, worker_id="worker-b",
        )
        first_records = {v["record_id"] for v in fx.owner.assignments()["run-a"]["leases"].values()}
        second_records = {v["record_id"] for v in second["leases"].values()}
        require(first_records.isdisjoint(second_records), "an active conversation is never handed to a second run")
        require(len(fx.owner.records()) == 4 and all(r.state == "active" for r in fx.owner.records()), "four active records")


def test_compatibility_mismatch_and_gate_off_cold_start() -> None:
    with fixture() as text:
        fx = Fixture(Path(text))
        raw, initial_hash = fx.candidate()
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        _, _, base_settlement = fx.run("run-base")
        base_ids = {key: value["session_id"] for key, value in base_settlement["leases"].items()}

        def owner(**overrides):
            options = dict(
                checkout=fx.source, repository_identity=REPOSITORY, provider_models=PROVIDER_MODELS,
                codex_resume_activation=ACTIVATION, compose_project=COMPOSE_PROJECT, clock=lambda: T0, host_identity="test-host",
            )
            options.update(overrides)
            return DecompositionSessionPoolOwner(**options)

        def prepared_with(instance, run_id: str) -> dict[str, Any]:
            # Every probe reservation is returned uncharged afterwards, so the
            # base conversations stay idle and each variant is judged on its
            # own compatibility rather than on stranded-owner reclamation.
            try:
                return instance.prepare(
                    run_id=run_id, task_id=TASK, decomposition_mode="round_robin_d1b2",
                    provider_order=("claude", "codex"), max_calls=2, source_commit=fx.head, worker_id="worker-v",
                )
            finally:
                instance.cancel_unstarted(run_id=run_id)
                instance.close()

        author_id = base_ids["claude:task_decomposer"]
        reviewer_id = base_ids["codex:decomposition_reviewer"]
        # Gate off: Codex is skipped, Claude still resumes its exact author session.
        prepared = prepared_with(owner(codex_resume_activation=None), "run-gate-off")
        require(set(prepared["leases"]) == {"claude:task_decomposer"} and prepared["skipped_keys"] == ["codex:decomposition_reviewer"], str(prepared))
        require(prepared["leases"]["claude:task_decomposer"]["mode"] == "resume", "claude still pools with the codex gate off")
        require(prepared["leases"]["claude:task_decomposer"]["session_id"] == author_id, "exact author session")
        for label, overrides, cold_key, warm_key, warm_id in (
            ("model", dict(provider_models={"claude": ("another-model", None), "codex": (MODEL, "high")}), "claude:task_decomposer", "codex:decomposition_reviewer", reviewer_id),
            ("effort", dict(provider_models={"claude": (MODEL, None), "codex": (MODEL, "low")}), "codex:decomposition_reviewer", "claude:task_decomposer", author_id),
            ("resume control", dict(codex_resume_activation=CodexResumeActivation(("-c", 'sandbox_mode="workspace-write"'))), "codex:decomposition_reviewer", "claude:task_decomposer", author_id),
        ):
            prepared = prepared_with(owner(**overrides), f"run-{label.replace(' ', '-')}")
            cold = prepared["leases"][cold_key]
            warm = prepared["leases"][warm_key]
            require(cold["mode"] == "start" and (cold["session_id"] is None or cold["session_id"] not in base_ids.values()), f"{label} mismatch must cold-start {cold_key}: {cold}")
            require(warm["mode"] == "resume" and warm["session_id"] == warm_id, f"{label}: the unaffected role still resumes its exact conversation: {warm}")
        # Another compose project names other configuration volumes, where
        # neither provider's conversation exists: both roles cold-start.
        prepared = prepared_with(owner(compose_project="nosafecircle-other"), "run-other-store")
        for key, lease in prepared["leases"].items():
            require(lease["mode"] == "start" and lease["session_id"] not in base_ids.values(), f"another conversation store must cold-start {key}: {lease}")
            provider_name = key.split(":", 1)[0]
            require(lease["scope"]["bindings"] == [["conversation_store", f"compose:nosafecircle-other/{provider_name}-config"]], str(lease["scope"]))
        base_again = prepared_with(owner(), "run-base-again")
        require({k: v["session_id"] for k, v in base_again["leases"].items()} == base_ids and all(v["mode"] == "resume" for v in base_again["leases"].values()), "an exactly matching owner resumes both base conversations")
        for key, lease in base_again["leases"].items():
            require(lease["scope"]["bindings"] == [["conversation_store", f"compose:{COMPOSE_PROJECT}/{key.split(':', 1)[0]}-config"]], str(lease["scope"]))
        import TaskDecomposition.session_pool_support as support
        original = support.DECOMPOSITION_SESSION_PROTOCOL_VERSION
        support.DECOMPOSITION_SESSION_PROTOCOL_VERSION = "9.9"
        try:
            bundle_path = Path(fx.owner.assignments()["run-base"]["lease_bundle_path"])
            expect_error(lambda: load_lease_bundle(bundle_path, run_id="run-base"), DecompositionSessionError, "speaks protocol")
        finally:
            support.DECOMPOSITION_SESSION_PROTOCOL_VERSION = original
        other_repository = owner(repository_identity="https://example.invalid/other.git")
        require(other_repository.records() == (), "another repository is another pool")
        other_repository.close()
        fx.owner.close()


def test_context_assignment_and_age_limits_rotate() -> None:
    with fixture() as text:
        fx = Fixture(Path(text), context_window=10000)
        raw, initial_hash = fx.candidate()
        fx.usage_tokens = 7000
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        _, _, settlement = fx.run("run-context")
        require(all(v["state"] == "retired" and v["retirement_reason"] == "known_context_window_threshold" for v in settlement["leases"].values()), str(settlement))
        fx.usage_tokens = 100
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        assignment, _, settlement = fx.run("run-after-context")
        require(all(v["mode"] == "start" for v in assignment["leases"].values()), "context cap rotates to cold starts")
        require(all(v["state"] == "idle" for v in settlement["leases"].values()), str(settlement))
        # Assignment cap: deep assignments cost 6 of 48 units, so the eighth
        # completed assignment retires the conversation.
        for index in range(2, 9):
            fx.outputs["claude"] = [raw]
            fx.outputs["codex"] = [pass_review(initial_hash)]
            assignment, _, settlement = fx.run(f"run-cap-{index}")
        require(all(v["retirement_reason"] == "worker_weighted_unit_limit" for v in settlement["leases"].values()), str(settlement))
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        assignment, _, _ = fx.run("run-after-cap")
        require(all(v["mode"] == "start" for v in assignment["leases"].values()), "assignment cap rotates to cold starts")
        # Age: a conversation created at T0 is expired at T0 + 14 days.
        later = DecompositionSessionPoolOwner(
            checkout=fx.source, repository_identity=REPOSITORY, provider_models=PROVIDER_MODELS,
            codex_resume_activation=ACTIVATION, compose_project=COMPOSE_PROJECT, context_window_tokens=10000,
            clock=lambda: T0 + dt.timedelta(days=14), host_identity="test-host",
        )
        prepared = later.prepare(
            run_id="run-aged", task_id=TASK, decomposition_mode="round_robin_d1b2",
            provider_order=("claude", "codex"), max_calls=2, source_commit=fx.head, worker_id="worker-l",
        )
        require(all(v["mode"] == "start" for v in prepared["leases"].values()), "age limit rotates to cold starts")
        require(any(r.state == "expired" and r.expiry_reason == "max_session_age" for r in later.records()), "aged conversations are expired explicitly")
        later.close()


def test_d1b1_author_pools_and_reachable_keys_are_exact() -> None:
    require(possible_lease_keys(decomposition_mode="round_robin_d1b2", provider_order=("codex", "claude"), max_calls=4)
            == ("codex:task_decomposer", "claude:decomposition_reviewer", "codex:decomposition_reviewer"), "reachable keys")
    require(possible_lease_keys(decomposition_mode="d1b1", provider_order=("claude",), max_calls=1) == ("claude:task_decomposer",), "d1b1 keys")
    with fixture() as text:
        fx = Fixture(Path(text))
        raw, _ = fx.candidate()
        fx.outputs["claude"] = [raw]
        assignment, result, settlement = fx.run("run-d1b1", order=("claude",), max_calls=1, mode="d1b1")
        require(result["run_status"] == "review_ready", str(result["rejection_reasons"]))
        evidence = result["pooled_session_evidence"]
        require(evidence["artifact_path"] == "decomposition_result.json" and evidence["role"] == "task_decomposer", str(evidence))
        require(settlement["leases"]["claude:task_decomposer"]["state"] == "idle", str(settlement))
        fx.outputs["claude"] = [raw]
        assignment, result, settlement = fx.run("run-d1b1-two", order=("claude",), max_calls=1, mode="d1b1")
        require(assignment["leases"]["claude:task_decomposer"]["mode"] == "resume", "d1b1 author resumes")
        require(settlement["leases"]["claude:task_decomposer"]["completed_assignment_count"] == 2, str(settlement))
        # A bundle for D1B.2 cannot drive a D1B.1 run.
        bundle = load_lease_bundle(assignment["lease_bundle_path"], run_id="run-d1b1-two")
        object.__setattr__(bundle, "decomposition_mode", "round_robin_d1b2")
        fx.outputs["claude"] = [raw]
        expect_error(lambda: run_live_decomposition(
            source=fx.source, output_root=fx.output_root, task_id=TASK, provider_name="claude", run_id="run-d1b1-three",
            provider_factory=fx.factory(), _require_physical_read_only_source=False,
            lease_bundle=bundle, scheduler_repository_identity=REPOSITORY,
        ), DecompositionPreflightError, "bound to mode")


def test_legacy_factories_and_ephemeral_runs_are_unchanged() -> None:
    with fixture() as text:
        fx = Fixture(Path(text))
        raw, initial_hash = fx.candidate()
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pass_review(initial_hash)]
        result = run_round_robin_decomposition(
            source=fx.source, output_root=fx.output_root, task_id=TASK, provider_order=("claude", "codex"),
            max_calls=2, run_id="run-ephemeral", provider_factory=fx.factory(), _require_physical_read_only_source=False,
        )
        require(result["run_status"] == "review_ready" and result["pooled_sessions"] is None, str(result["run_status"]))
        require(all(entry["requested_mode"] is None for entry in fx.log), "ephemeral rounds bind no session")

        def two_arg_factory(provider_name, source, role):
            return fx.factory()(provider_name, source, role)

        fx.outputs["claude"] = [raw]
        assignment = fx.owner.prepare(
            run_id="run-strict-factory", task_id=TASK, decomposition_mode="d1b1", provider_order=("claude",),
            max_calls=1, source_commit=fx.head, worker_id="worker-s",
        )
        bundle = load_lease_bundle(assignment["lease_bundle_path"], run_id="run-strict-factory")
        expect_error(lambda: run_live_decomposition(
            source=fx.source, output_root=fx.output_root, task_id=TASK, provider_name="claude", run_id="run-strict-factory",
            provider_factory=two_arg_factory, _require_physical_read_only_source=False,
            lease_bundle=bundle, scheduler_repository_identity=REPOSITORY,
        ), DecompositionPreflightError, "accepts the session binding")


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"pooled decomposition tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
