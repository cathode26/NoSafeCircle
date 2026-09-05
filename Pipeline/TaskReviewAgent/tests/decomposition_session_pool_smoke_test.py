#!/usr/bin/env python3
"""Host-launcher regressions for pooled decomposition author/reviewer sessions.

The real `host_decomposition_launcher._run_proposal` runs against a synthetic
committed graph. `docker compose run` is replaced by an in-process execution of
the real round-robin runner with session-aware fake providers, driven by the
exact lease bundle the launcher mounted, so the test proves the host-to-
container contract end to end: reservation, exact compose argv, evidence-bound
settlement, and the degraded path. No Docker, provider, GitHub, or network call
is made.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for _module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))

from Pipeline.TaskReviewAgent import host_decomposition_launcher as launcher  # noqa: E402
from Pipeline.TaskReviewAgent.decomposition_session_pool import (  # noqa: E402
    DecompositionSessionPoolError,
    DecompositionSessionPoolOwner,
)
from Pipeline.TaskReviewAgent.polling_orchestrator import (  # noqa: E402
    PollingOrchestratorError,
    build_decomposition_worker_command,
)
from Pipeline.TaskReviewAgent.supervisor_session_pool import CodexResumeActivation  # noqa: E402
from TaskDecomposition.round_robin_decomposition import run_round_robin_decomposition  # noqa: E402
from TaskDecomposition.session_pool_support import load_lease_bundle  # noqa: E402
from TaskDecomposition.tests import pooled_decomposition_smoke_test as pooled  # noqa: E402


TASK = pooled.TASK
REPOSITORY = pooled.REPOSITORY
# `launcher.subprocess` is the standard module, so replacing `run` there is
# process-wide; every fake forwards anything that is not the Docker launch.
ORIGINAL_RUN = subprocess.run


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class RecordingService:
    def __init__(self) -> None:
        self.releases: list[dict] = []
        self.handoffs: list[dict] = []

    def release_decomposition_lease(self, **values):
        self.releases.append(dict(values))
        return {"status": "agent_ready"}

    def publish_decomposition_handoff(self, **values):
        self.handoffs.append(dict(values))
        return {"status": "human_action_required"}

    @staticmethod
    def find(_task_id):
        return None


def test_compose_command_mounts_the_bundle_and_pins_the_route() -> None:
    assignment = {
        "lease_bundle_path": "C:/pool/run.leases.json",
        "repository_identity": REPOSITORY,
        "provider_environment": {"NSC_CLAUDE_MODEL": "claude-sonnet-5", "NSC_OPENAI_CODEX_MODEL": "gpt-5.6-sol"},
    }
    command = launcher.build_compose_command(
        task_id=TASK, project="nosafecircle-m2a", providers="codex,claude", max_calls=4,
        run_id="nsc-010-d1b2-run", pool_assignment=assignment,
    )
    service_index = command.index("round-robin-decompose")
    require(command[:7] == ("docker", "compose", "-p", "nosafecircle-m2a", "run", "--rm", "-T"), str(command))
    require(("--volume", "C:/pool/run.leases.json:/nsc-pool/decomposition-leases.json:ro") == command[7:9], str(command))
    require(("--env", "NSC_CLAUDE_MODEL=claude-sonnet-5", "--env", "NSC_OPENAI_CODEX_MODEL=gpt-5.6-sol") == command[9:13], str(command))
    require(service_index == 13, str(command))
    tail = command[service_index:]
    require(tail[1:3] == ("python3", "Pipeline/TaskDecomposition/run_round_robin_decomposition.py"), str(tail))
    require(tail[tail.index("--run-id") + 1] == "nsc-010-d1b2-run", str(tail))
    require(tail[tail.index("--role-session-leases") + 1] == "/nsc-pool/decomposition-leases.json", str(tail))
    require(tail[tail.index("--scheduler-repository-identity") + 1] == REPOSITORY, str(tail))
    plain = launcher.build_compose_command(task_id=TASK, project="nosafecircle-m2a", providers="codex,claude", max_calls=4)
    require("--volume" not in plain and "--role-session-leases" not in plain and "--env" not in plain, str(plain))
    try:
        launcher.build_compose_command(task_id=TASK, project="p", providers="codex,claude", max_calls=4, pool_assignment=assignment)
    except RuntimeError as exc:
        require("explicit run id" in str(exc), str(exc))
    else:
        raise AssertionError("pooling without a run id was accepted")


def test_scheduler_command_carries_the_pool_opt_in_only_with_run_identity() -> None:
    command = build_decomposition_worker_command(
        task_id="NSC-102", worker_id="w", source=Path("C:/fixture/source"), checkout_root=Path("C:/fixture/checkouts"),
        output_root=Path("C:/fixture/outputs/NSC-102"), scheduler_output_root=Path("C:/fixture/results"),
        run_id="scheduler-nsc-102", admission_source_head="1" * 40, task_contract_sha256="b" * 64,
        admission_issue_number=102, enable_session_pool=True,
    )
    require("--enable-decomposition-session-pool" in command, str(command))
    plain = build_decomposition_worker_command(
        task_id="NSC-102", worker_id="w", source=Path("C:/fixture/source"), checkout_root=Path("C:/fixture/checkouts"),
        output_root=Path("C:/fixture/outputs/NSC-102"),
    )
    require("--enable-decomposition-session-pool" not in plain, str(plain))
    try:
        build_decomposition_worker_command(
            task_id="NSC-102", worker_id="w", source=Path("C:/fixture/source"), checkout_root=Path("C:/fixture/checkouts"),
            output_root=Path("C:/fixture/outputs/NSC-102"), enable_session_pool=True,
        )
    except PollingOrchestratorError as exc:
        require("run identity" in str(exc), str(exc))
    else:
        raise AssertionError("pooling without scheduler run identity was accepted")


def test_production_owner_factory_resolves_models_activation_and_window() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-decomp-owner-factory-", ignore_cleanup_errors=True) as text:
        fx = pooled.Fixture(Path(text))
        fx.owner.close()
        keys = ("NSC_CLAUDE_MODEL", "NSC_OPENAI_CODEX_MODEL", "NSC_CODEX_RESUME_SANDBOX_ARGUMENT", "NSC_DECOMPOSITION_CONTEXT_WINDOW_TOKENS")
        saved = {key: os.environ.pop(key) for key in keys if key in os.environ}
        try:
            os.environ["NSC_CLAUDE_MODEL"] = "claude-fixture-model"
            os.environ["NSC_OPENAI_CODEX_MODEL"] = "codex-fixture-model"
            os.environ["NSC_CODEX_RESUME_SANDBOX_ARGUMENT"] = json.dumps(list(pooled.ACTIVATION.argument))
            os.environ["NSC_DECOMPOSITION_CONTEXT_WINDOW_TOKENS"] = "250000"
            owner = launcher._decomposition_pool_owner(workspace=fx.source, compose_project="nosafecircle-m2a")
            try:
                require(owner.repository_identity == REPOSITORY, owner.repository_identity)
                require(owner.compose_project == "nosafecircle-m2a", owner.compose_project)
                require(owner.provider_models == {"claude": ("claude-fixture-model", None), "codex": ("codex-fixture-model", "high")}, str(owner.provider_models))
                require(owner.codex_resume_activation == pooled.ACTIVATION and owner.context_window_tokens == 250000, "activation and window from the environment")
                prepared = owner.prepare(
                    run_id="nsc-010-d1b2-factory", task_id=TASK, decomposition_mode="round_robin_d1b2",
                    provider_order=("codex", "claude"), max_calls=4, source_commit=fx.head, worker_id="w",
                )
                require(prepared["provider_environment"] == {"NSC_CLAUDE_MODEL": "claude-fixture-model", "NSC_OPENAI_CODEX_MODEL": "codex-fixture-model"}, str(prepared["provider_environment"]))
                require(set(prepared["leases"]) == {"codex:task_decomposer", "claude:decomposition_reviewer", "codex:decomposition_reviewer"}, str(prepared["leases"].keys()))
                # Every lease names the volume its provider's conversation lives
                # in, under the exact project the launcher will run the container with.
                stores = {key: value["scope"]["bindings"] for key, value in prepared["leases"].items()}
                require(stores == {
                    "codex:task_decomposer": [["conversation_store", "compose:nosafecircle-m2a/codex-config"]],
                    "claude:decomposition_reviewer": [["conversation_store", "compose:nosafecircle-m2a/claude-config"]],
                    "codex:decomposition_reviewer": [["conversation_store", "compose:nosafecircle-m2a/codex-config"]],
                }, str(stores))
                require(prepared["compose_project"] == "nosafecircle-m2a", str(prepared))
            finally:
                owner.close()
            try:
                launcher._decomposition_pool_owner(workspace=fx.source, compose_project="Not A Project")
            except DecompositionSessionPoolError as exc:
                require("Docker Compose project" in str(exc), str(exc))
            else:
                raise AssertionError("an invalid compose project was accepted as a conversation store")
            os.environ.pop("NSC_CODEX_RESUME_SANDBOX_ARGUMENT")
            gate_off = launcher._decomposition_pool_owner(workspace=fx.source, compose_project="nosafecircle-m2a")
            try:
                require(gate_off.codex_resume_activation is None, "gate off without the control")
            finally:
                gate_off.close()
        finally:
            for key in keys:
                os.environ.pop(key, None)
            os.environ.update(saved)


def _proposal_harness(temp: Path, *, activation=pooled.ACTIVATION):
    """A synthetic checkout, an owner factory bound to it, and an in-process container."""

    fx = pooled.Fixture(temp, activation=activation)
    fx.owner.close()
    raw, initial_hash = fx.candidate()
    calls: list[tuple[str, ...]] = []

    def owner_factory(*, workspace: Path, compose_project: str) -> DecompositionSessionPoolOwner:
        require(Path(workspace) == fx.source, str(workspace))
        require(compose_project == pooled.COMPOSE_PROJECT, f"the launcher passes its own compose project: {compose_project}")
        return DecompositionSessionPoolOwner(
            checkout=fx.source, repository_identity=REPOSITORY, provider_models=pooled.PROVIDER_MODELS,
            codex_resume_activation=activation, compose_project=compose_project,
            clock=lambda: pooled.T0, host_identity="test-host",
        )

    def fake_docker(command, **kwargs):
        if tuple(command)[:1] != ("docker",):
            return ORIGINAL_RUN(command, **kwargs)
        env = kwargs["env"]
        calls.append(tuple(command))
        bundle_path = Path(command[command.index("--volume") + 1].split(":/nsc-pool")[0])
        run_id = command[command.index("--run-id") + 1]
        bundle = load_lease_bundle(bundle_path, run_id=run_id)
        fx.outputs["claude"] = [raw]
        fx.outputs["codex"] = [pooled.pass_review(initial_hash)]
        run_round_robin_decomposition(
            source=fx.source, output_root=Path(env["NSC_DECOMPOSITION_HOST_OUTPUT_ROOT"]), task_id=TASK,
            provider_order=("claude", "codex"), max_calls=2, run_id=run_id, provider_factory=fx.factory(),
            _require_physical_read_only_source=False, lease_bundle=bundle,
            scheduler_repository_identity=command[command.index("--scheduler-repository-identity") + 1],
        )
        return subprocess.CompletedProcess(args=command, returncode=0)

    return fx, owner_factory, fake_docker, calls


def test_run_proposal_reserves_runs_and_settles_pooled_sessions() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-decomp-pool-launcher-", ignore_cleanup_errors=True) as text:
        temp = Path(text)
        fx, owner_factory, fake_docker, calls = _proposal_harness(temp)
        originals = (launcher.subprocess.run, launcher._decomposition_pool_owner)
        launcher.subprocess.run = fake_docker
        launcher._decomposition_pool_owner = owner_factory
        service = RecordingService()
        try:
            for attempt in (1, 2):
                args = SimpleNamespace(
                    task_id=TASK, compose_project="nosafecircle-m2a", providers="claude,codex", max_calls=2,
                    run_id=None, worker_id="worker-launcher", enable_decomposition_session_pool=True,
                )
                code = launcher._run_proposal(
                    args=args, workspace=fx.source, output_root=fx.output_root, source_head=fx.head, service=service,
                )
                require(code == 0, f"attempt {attempt}: proposal returned {code}; releases={service.releases}")
            require(len(calls) == 2 and len(service.handoffs) == 2 and service.releases == [], str(service.releases))
            first, second = calls
            require("--volume" in first and first[first.index("--role-session-leases") + 1] == "/nsc-pool/decomposition-leases.json", str(first))
            require(first[first.index("--run-id") + 1].startswith("nsc-010-d1b2-"), "the host minted a run id it owns")
            require(first[first.index("--run-id") + 1] != second[second.index("--run-id") + 1], "distinct run ids")
            require(("--env", "NSC_CLAUDE_MODEL=deterministic-fake-model") == first[first.index("--env"):first.index("--env") + 2], str(first))
            rounds = fx.rounds()
            require([r["requested_mode"] for r in rounds] == ["start", "start", "resume", "resume"], str([r["requested_mode"] for r in rounds]))
            require(rounds[2]["requested_session_id"] == rounds[0]["confirmed_session_id"], "second run resumes the exact author session")
            require(rounds[3]["requested_session_id"] == rounds[1]["confirmed_session_id"], "second run resumes the exact reviewer session")
            owner = owner_factory(workspace=fx.source, compose_project=pooled.COMPOSE_PROJECT)
            try:
                records = owner.records()
                require(len(records) == 2 and all(r.state == "idle" and r.completed_assignment_count == 2 for r in records), str(records))
                assignments = owner.assignments()
                require(all(a["status"] == "settled" for a in assignments.values()), str({k: a["status"] for k, a in assignments.items()}))
            finally:
                owner.close()
            require(not list(fx.output_root.glob("*/pool_degraded.json")), "no degraded marker on the healthy path")
        finally:
            launcher.subprocess.run, launcher._decomposition_pool_owner = originals


def test_pool_settlement_failure_degrades_pooling_but_keeps_the_result() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-decomp-pool-degraded-", ignore_cleanup_errors=True) as text:
        temp = Path(text)
        fx, owner_factory, fake_docker, calls = _proposal_harness(temp)

        def corrupting_docker(command, **kwargs):
            completed = fake_docker(command, **kwargs)
            if tuple(command)[:1] != ("docker",):
                return completed
            owner = owner_factory(workspace=fx.source, compose_project=pooled.COMPOSE_PROJECT)
            owner.state_path.write_text("{not json", encoding="utf-8")
            owner.close()
            return completed

        originals = (launcher.subprocess.run, launcher._decomposition_pool_owner)
        launcher.subprocess.run = corrupting_docker
        launcher._decomposition_pool_owner = owner_factory
        service = RecordingService()
        try:
            args = SimpleNamespace(
                task_id=TASK, compose_project="nosafecircle-m2a", providers="claude,codex", max_calls=2,
                run_id="nsc-010-d1b2-degraded", worker_id="worker-launcher", enable_decomposition_session_pool=True,
            )
            code = launcher._run_proposal(
                args=args, workspace=fx.source, output_root=fx.output_root, source_head=fx.head, service=service,
            )
            require(code == 0 and len(service.handoffs) == 1, f"the review-ready result must still hand off: {code} {service.releases}")
            degraded = json.loads((fx.output_root / "nsc-010-d1b2-degraded" / "pool_degraded.json").read_text(encoding="utf-8"))
            require(degraded["status"] == "pool_degraded" and degraded["run_id"] == "nsc-010-d1b2-degraded", str(degraded))
        finally:
            launcher.subprocess.run, launcher._decomposition_pool_owner = originals


def test_provider_start_failure_returns_the_reserved_conversations() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-decomp-pool-unstarted-", ignore_cleanup_errors=True) as text:
        temp = Path(text)
        fx, owner_factory, fake_docker, calls = _proposal_harness(temp)
        originals = (launcher.subprocess.run, launcher._decomposition_pool_owner)
        launcher.subprocess.run = fake_docker
        launcher._decomposition_pool_owner = owner_factory
        service = RecordingService()
        try:
            args = SimpleNamespace(
                task_id=TASK, compose_project="nosafecircle-m2a", providers="claude,codex", max_calls=2,
                run_id=None, worker_id="worker-launcher", enable_decomposition_session_pool=True,
            )
            code = launcher._run_proposal(args=args, workspace=fx.source, output_root=fx.output_root, source_head=fx.head, service=service)
            require(code == 0, str(service.releases))
            warmed = {r.session_id for r in owner_factory(workspace=fx.source, compose_project=pooled.COMPOSE_PROJECT).records()}

            def cannot_start(command, **kwargs):
                if tuple(command)[:1] != ("docker",):
                    return ORIGINAL_RUN(command, **kwargs)
                raise OSError("docker is not on PATH")

            launcher.subprocess.run = cannot_start
            code = launcher._run_proposal(args=args, workspace=fx.source, output_root=fx.output_root, source_head=fx.head, service=service)
            require(code == 3 and service.releases and "could not start" in service.releases[-1]["reason"], str(service.releases))
            owner = owner_factory(workspace=fx.source, compose_project=pooled.COMPOSE_PROJECT)
            try:
                assignments = owner.assignments()
                cancelled = [a for a in assignments.values() if a["status"] == "cancelled"]
                require(len(cancelled) == 1, str({k: a["status"] for k, a in assignments.items()}))
                records = owner.records()
                require({r.session_id for r in records} == warmed and all(r.state == "idle" and r.completed_assignment_count == 1 for r in records), f"a start failure returns the warm conversations uncharged: {records}")
            finally:
                owner.close()
        finally:
            launcher.subprocess.run, launcher._decomposition_pool_owner = originals


def test_gate_off_pools_claude_only_and_ephemeral_launch_is_unchanged() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-decomp-pool-gate-", ignore_cleanup_errors=True) as text:
        temp = Path(text)
        fx, owner_factory, fake_docker, calls = _proposal_harness(temp, activation=None)
        originals = (launcher.subprocess.run, launcher._decomposition_pool_owner)
        launcher.subprocess.run = fake_docker
        launcher._decomposition_pool_owner = owner_factory
        service = RecordingService()
        try:
            args = SimpleNamespace(
                task_id=TASK, compose_project="nosafecircle-m2a", providers="claude,codex", max_calls=2,
                run_id="nsc-010-d1b2-gate-off", worker_id="worker-launcher", enable_decomposition_session_pool=True,
            )
            code = launcher._run_proposal(
                args=args, workspace=fx.source, output_root=fx.output_root, source_head=fx.head, service=service,
            )
            require(code == 0, str(service.releases))
            rounds = fx.rounds()
            require(rounds[0]["requested_mode"] == "start" and rounds[1]["requested_mode"] is None, "claude pooled, codex ephemeral with the gate off")
            bundle = json.loads(Path(calls[0][calls[0].index("--volume") + 1].split(":/nsc-pool")[0]).read_text(encoding="utf-8"))
            require(set(bundle["leases"]) == {"claude:task_decomposer"} and bundle["codex_resume_sandbox_argument"] is None, str(bundle["leases"].keys()))
            calls.clear()
            plain = SimpleNamespace(task_id=TASK, compose_project="nosafecircle-m2a", providers="claude,codex", max_calls=2, run_id="nsc-010-plain")

            def ephemeral_docker(command, **kwargs):
                if tuple(command)[:1] != ("docker",):
                    return ORIGINAL_RUN(command, **kwargs)
                env = kwargs["env"]
                calls.append(tuple(command))
                fx.outputs["claude"] = [fx.candidate()[0]]
                fx.outputs["codex"] = [pooled.pass_review(fx.candidate()[1])]
                run_round_robin_decomposition(
                    source=fx.source, output_root=Path(env["NSC_DECOMPOSITION_HOST_OUTPUT_ROOT"]), task_id=TASK,
                    provider_order=("claude", "codex"), max_calls=2, run_id="nsc-010-plain", provider_factory=fx.factory(),
                    _require_physical_read_only_source=False,
                )
                return subprocess.CompletedProcess(args=command, returncode=0)

            launcher.subprocess.run = ephemeral_docker
            code = launcher._run_proposal(args=plain, workspace=fx.source, output_root=fx.output_root, source_head=fx.head, service=service)
            require(code == 0 and "--volume" not in calls[0] and "--role-session-leases" not in calls[0], str(calls[0]))
        finally:
            launcher.subprocess.run, launcher._decomposition_pool_owner = originals


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"decomposition session pool launcher tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
