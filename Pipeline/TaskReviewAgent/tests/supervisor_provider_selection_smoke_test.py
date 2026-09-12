#!/usr/bin/env python3
"""Deterministic proof that the TaskReviewAgent supervisor provider is selectable.

Classification: pure/component and in-memory boundary tests. Every test drives a
real parameter, propagation, or factory boundary -- argparse namespaces, the
frozen run-manifest dataclass, ``build_worker_command``, ``build_powershell_command``,
the supervisor decision-provider factory, and the durable supervisor session
scope. Nothing here searches source text for a string.

No provider, Docker daemon, container, GitHub call, Unity invocation, network
access, scheduler, rehearsal checkout, or tracked repository file is involved.
Every assertion is a regression-only orchestration invariant.

Before the fix the supervisor was pinned to Codex by six literals -- one in each
of ``Start-GameTaskAgent.ps1``, ``run_pipeline_agent.py``,
``host_worker_launcher.py``, ``autonomous_graph_run.py``, and two in
``polling_orchestrator.py`` -- so a Claude-only run was impossible and every run
had to authorize Codex. These tests fail on the starting commit because the
selection, the manifest field, the argv token, and the provider registry did not
exist at all.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.autonomous_graph_run import (  # noqa: E402
    AutonomousRuntimeConfiguration,
)
from Pipeline.TaskReviewAgent.host_worker_launcher import (  # noqa: E402
    build_parser as worker_launcher_parser,
    build_powershell_command,
)
from Pipeline.TaskReviewAgent.polling_orchestrator import build_worker_command  # noqa: E402
from Pipeline.TaskReviewAgent.provider_policy import ProviderPolicyError  # noqa: E402
from Pipeline.TaskReviewAgent.run_autonomous_graph import (  # noqa: E402
    build_parser as graph_parser,
    _runtime_configuration,
)
from Pipeline.TaskReviewAgent.run_pipeline_agent import (  # noqa: E402
    build_parser as worker_parser,
)
from Pipeline.TaskReviewAgent.codex_supervisor import describe_codex_runtime  # noqa: E402
from Pipeline.TaskReviewAgent.supervisor_session_pool import (  # noqa: E402
    CodexResumeActivation,
    SupervisorSessionOwner,
    SupervisorSessionPoolError,
    gate_off_activation_state,
)

# The selection API did not exist at the starting commit. Importing it lazily --
# the same shape `supervisor_session_pool_smoke_test.py` already uses -- lets
# every test below fail on its own named assertion against the pre-fix
# semantics instead of collapsing the whole module into one ImportError.
SELECTION_IMPORT_ERROR: str | None = None
try:
    from Pipeline.TaskReviewAgent.codex_supervisor import (  # noqa: E402
        CodexDockerDecisionProvider,
        SupervisorDockerDecisionProvider,
        build_supervisor_decision_provider,
    )
    from Pipeline.TaskReviewAgent.provider_policy import (  # noqa: E402
        DEFAULT_SUPERVISOR_PROVIDER,
        resolve_supervisor_provider,
    )
    from Pipeline.TaskReviewAgent.supervisor_providers import (  # noqa: E402
        supervisor_provider_for_identifier,
        supervisor_provider_profile,
    )
    from Pipeline.TaskReviewAgent.supervisor_session_pool import (  # noqa: E402
        ClaudeResumeActivation,
    )
except ImportError as exc:  # pragma: no cover - exercised only at the base commit
    SELECTION_IMPORT_ERROR = str(exc)
    DEFAULT_SUPERVISOR_PROVIDER = "codex"


def require_selection_api() -> None:
    """Fail with the defect this suite exists to close, not with an ImportError."""

    require(
        SELECTION_IMPORT_ERROR is None,
        "pre-fix semantics: the TaskReviewAgent supervisor is structurally pinned "
        "to Codex, so there is no explicit supervisor-provider selection to "
        f"validate, propagate, persist, or bind ({SELECTION_IMPORT_ERROR})",
    )


TASK = "NSC-900"
OTHER_TASK = "NSC-901"
# Supervisor models must belong to their provider: the host now refuses a
# cross-provider model before any container round trip.
CLAUDE_MODEL = "claude-supervisor-selection-model"
CODEX_MODEL = "gpt-supervisor-selection-model"
MODEL = CLAUDE_MODEL
REPOSITORY = "https://github.com/cathode26/NoSafeCircle.git"
CODEX_ACTIVATION = CodexResumeActivation(("-c", 'sandbox_mode="danger-full-access"'))

_RUNTIME_BASE = {
    "execution_provider": None,
    "execution_model": None,
    "execution_max_turns": 120,
    "architect_provider": "claude",
    "architect_model": None,
    "architect_max_turns": 40,
    "architect_min_confidence": 0.5,
    "architect_max_invocations_per_poll": 2,
    "architect_min_reanalysis_seconds": 1.0,
    "max_consecutive_observation_failures": 3,
    "fatal_drain_seconds": 1.0,
    "fallback_seconds": 1.0,
    "synthetic_evidence_enabled": False,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_error(action, kind, fragment: str) -> BaseException:
    try:
        action()
    except kind as exc:
        require(
            fragment.casefold() in str(exc).casefold(),
            f"expected {fragment!r} in {exc!r}",
        )
        return exc
    raise AssertionError(f"expected {kind.__name__} mentioning {fragment!r}")


def names_codex(values) -> bool:
    """True when any emitted token would name Codex as an executable provider."""

    return any("codex" in str(item).casefold() for item in values)


def worker_arguments(**overrides: str) -> list[str]:
    arguments = {
        "--task-id": TASK,
        "--source": str(ROOT),
        "--checkout-root": str(ROOT),
        "--output-root": str(ROOT),
        "--worker-id": "selection-worker",
        "--execution-provider": "claude",
        "--max-turns": "40",
    }
    arguments.update(overrides)
    result: list[str] = []
    for flag, value in arguments.items():
        result.extend((flag, value))
    return result


# ------------------------------------------------------------------ selection


def test_default_callers_and_legacy_artifacts_still_select_codex() -> None:
    """Requirement 12: omitting the selection anywhere keeps the Codex supervisor."""

    require_selection_api()
    require(DEFAULT_SUPERVISOR_PROVIDER == "codex", DEFAULT_SUPERVISOR_PROVIDER)
    require(resolve_supervisor_provider(None) == "codex", "None must mean Codex")
    require(supervisor_provider_profile(None).supervisor_provider == "codex", "profile")

    worker = worker_parser().parse_args(["--task-id", TASK, "--source", str(ROOT)])
    require(worker.supervisor_provider is None, "worker default must stay unchosen")

    graph = graph_parser().parse_args(
        ["--source", str(ROOT), "--run-id", "r1", "--confirm-repository", "a/b"]
    )
    require(graph.supervisor_provider is None, "graph default must stay unchosen")

    legacy = AutonomousRuntimeConfiguration(**_RUNTIME_BASE)
    require(legacy.supervisor_provider == "codex", legacy.supervisor_provider)
    require(
        "supervisor_provider" not in legacy.to_dict(),
        "a run that never selected a supervisor must serialize exactly as before, "
        "because the manifest hash gates resume against persisted progress",
    )
    restored = AutonomousRuntimeConfiguration.from_dict(legacy.to_dict())
    require(restored.supervisor_provider == "codex", "legacy manifest must load as Codex")

    command = build_worker_command(
        task_id=TASK,
        worker_id="w",
        source=ROOT,
        checkout_root=ROOT,
        execution_provider="codex",
        max_turns=40,
    )
    index = command.index("--supervisor-provider")
    require(command[index + 1] == "codex", "default scheduler argv must name Codex")


def test_the_three_provider_selectors_stay_independent() -> None:
    """Requirement 8: architect, supervisor, and execution never overwrite one another."""

    require_selection_api()
    runtime = AutonomousRuntimeConfiguration(
        **{**_RUNTIME_BASE, "architect_provider": "claude", "execution_provider": "codex"},
        supervisor_provider="claude",
    )
    require(runtime.architect_provider == "claude", runtime.architect_provider)
    require(runtime.supervisor_provider == "claude", runtime.supervisor_provider)
    require(runtime.execution_provider == "codex", runtime.execution_provider)

    mirrored = AutonomousRuntimeConfiguration(
        **{**_RUNTIME_BASE, "architect_provider": "codex", "execution_provider": "claude"},
        supervisor_provider="codex",
    )
    require(
        (
            mirrored.architect_provider,
            mirrored.supervisor_provider,
            mirrored.execution_provider,
        )
        == ("codex", "codex", "claude"),
        "each selector must survive independently",
    )

    args = worker_parser().parse_args(
        [
            "--task-id",
            TASK,
            "--source",
            str(ROOT),
            "--execution-provider",
            "codex",
            "--supervisor-provider",
            "claude",
        ]
    )
    require(args.execution_provider == "codex", args.execution_provider)
    require(args.supervisor_provider == "claude", args.supervisor_provider)


def test_unsupported_supervisor_values_are_refused() -> None:
    require_selection_api()
    expect_error(
        lambda: resolve_supervisor_provider("gpt"), ProviderPolicyError, "supervisor_provider"
    )
    expect_error(
        lambda: AutonomousRuntimeConfiguration(**_RUNTIME_BASE, supervisor_provider="gpt"),
        ProviderPolicyError,
        "supervisor_provider",
    )


# ------------------------------------------------------- manifest and resume


def test_manifest_persists_claude_and_refuses_a_changed_supervisor_on_resume() -> None:
    """Requirement 2 and 14: the selection is immutable for the life of a run."""

    require_selection_api()
    persisted = AutonomousRuntimeConfiguration(
        **_RUNTIME_BASE, supervisor_provider="claude", provider_allowlist=("claude",)
    )
    payload = persisted.to_dict()
    require(payload["supervisor_provider"] == "claude", payload)
    require(
        AutonomousRuntimeConfiguration.from_dict(payload).supervisor_provider == "claude",
        "an explicit Claude supervisor must survive a manifest round trip",
    )

    def namespace(**overrides):
        values = {
            "provider_allowlist": ("claude",),
            "supervisor_provider": None,
            "execution_provider": None,
            "model": None,
            "max_turns": None,
            "architect_provider": None,
            "architect_model": None,
            "architect_max_turns": None,
            "architect_min_confidence": None,
            "architect_max_invocations_per_poll": None,
            "architect_min_reanalysis_seconds": None,
            "max_consecutive_observation_failures": None,
            "fatal_drain_seconds": None,
            "fallback_seconds": None,
            "synthetic_evidence_enabled": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    # Omitting the flag on resume keeps the persisted selection and never
    # rewrites it to the Codex default.
    resumed = _runtime_configuration(namespace(), persisted)
    require(resumed.supervisor_provider == "claude", resumed.supervisor_provider)

    # Naming the same one is accepted; naming a different one is refused.
    same = _runtime_configuration(namespace(supervisor_provider="claude"), persisted)
    require(same.supervisor_provider == "claude", same.supervisor_provider)
    expect_error(
        lambda: _runtime_configuration(namespace(supervisor_provider="codex"), persisted),
        Exception,
        "supervisor_provider differs from the persisted run",
    )

    # The mirror case: a persisted Codex run is never silently promoted.
    codex_run = AutonomousRuntimeConfiguration(**_RUNTIME_BASE)
    expect_error(
        lambda: _runtime_configuration(
            namespace(provider_allowlist=None, supervisor_provider="claude"), codex_run
        ),
        Exception,
        "supervisor_provider differs from the persisted run",
    )


def test_a_supervisor_outside_the_allowlist_stops_before_any_provider() -> None:
    """Requirements 6 and 7: both directions fail closed at construction."""

    require_selection_api()
    # The architect selector is set to the permitted provider so the refusal
    # under test is unambiguously the supervisor's.
    expect_error(
        lambda: AutonomousRuntimeConfiguration(
            **{**_RUNTIME_BASE, "architect_provider": "codex"},
            supervisor_provider="claude",
            provider_allowlist=("codex",),
        ),
        ProviderPolicyError,
        "supervisor provider 'claude' is not in provider_allowlist",
    )
    expect_error(
        lambda: AutonomousRuntimeConfiguration(
            **{**_RUNTIME_BASE, "architect_provider": "claude"},
            supervisor_provider="codex",
            provider_allowlist=("claude",),
        ),
        ProviderPolicyError,
        "supervisor provider 'codex' is not in provider_allowlist",
    )
    # The scheduler refuses before it can build any worker argv at all.
    # Execution is set to the permitted provider in both argv builders so the
    # refusal proves the supervisor gate, not the execution gate.
    expect_error(
        lambda: build_worker_command(
            task_id=TASK,
            worker_id="w",
            source=ROOT,
            checkout_root=ROOT,
            execution_provider="codex",
            max_turns=40,
            supervisor_provider="claude",
            provider_allowlist=("codex",),
        ),
        ProviderPolicyError,
        "supervisor provider 'claude' is not in provider_allowlist",
    )
    expect_error(
        lambda: build_powershell_command(
            worker_launcher_parser().parse_args(
                worker_arguments(**{"--execution-provider": "codex"})
                + ["--supervisor-provider", "claude", "--provider-allowlist", "codex"]
            )
        ),
        ProviderPolicyError,
        "supervisor provider 'claude' is not in provider_allowlist",
    )


def test_a_mixed_allowlist_permits_an_explicit_selection() -> None:
    """Requirement 14: a mixed allowlist authorizes, it does not choose."""

    require_selection_api()
    for selected in ("claude", "codex"):
        runtime = AutonomousRuntimeConfiguration(
            **_RUNTIME_BASE,
            supervisor_provider=selected,
            provider_allowlist=("claude", "codex"),
        )
        require(runtime.supervisor_provider == selected, runtime.supervisor_provider)
        command = build_worker_command(
            task_id=TASK,
            worker_id="w",
            source=ROOT,
            checkout_root=ROOT,
            execution_provider="claude",
            max_turns=40,
            supervisor_provider=selected,
            provider_allowlist=("claude", "codex"),
        )
        index = command.index("--supervisor-provider")
        require(command[index + 1] == selected, command)


# ------------------------------------------------------- argv propagation


def test_scheduler_worker_command_carries_the_exact_selected_supervisor() -> None:
    """Requirement 3: the worker never re-derives the supervisor from a default."""

    require_selection_api()
    command = build_worker_command(
        task_id=TASK,
        worker_id="w",
        source=ROOT,
        checkout_root=ROOT,
        execution_provider="claude",
        max_turns=40,
        supervisor_provider="claude",
        provider_allowlist=("claude",),
    )
    index = command.index("--supervisor-provider")
    require(command[index + 1] == "claude", command)
    require(
        not names_codex(command),
        f"a Claude-only worker command must not name Codex: {command}",
    )
    # The worker's own parser accepts exactly what the scheduler emitted.
    parsed = worker_parser().parse_args(list(command[3:]))
    require(parsed.supervisor_provider == "claude", parsed.supervisor_provider)


def test_host_worker_launcher_forwards_the_selection_into_powershell() -> None:
    """Requirement 3: the host argv adapter names -SupervisorProvider exactly."""

    require_selection_api()
    args = worker_launcher_parser().parse_args(
        worker_arguments()
        + ["--supervisor-provider", "claude", "--provider-allowlist", "claude"]
    )
    command = build_powershell_command(args)
    index = command.index("-SupervisorProvider")
    require(command[index + 1] == "claude", command)
    require(not names_codex(command), f"Claude-only PowerShell argv named Codex: {command}")

    default_args = worker_launcher_parser().parse_args(worker_arguments())
    default_command = build_powershell_command(default_args)
    default_index = default_command.index("-SupervisorProvider")
    require(default_command[default_index + 1] == "codex", default_command)


# --------------------------------------------------------- provider factory


def test_the_factory_builds_the_claude_route_and_no_codex_command() -> None:
    """Requirement 5 and 13: the Claude route names no Codex service, volume, or script."""

    require_selection_api()
    provider = build_supervisor_decision_provider(
        supervisor_provider="claude",
        source=ROOT,
        model=MODEL,
        command_runner=lambda *values, **options: None,
    )
    require(type(provider) is SupervisorDockerDecisionProvider, type(provider).__name__)
    require(provider.supervisor_provider == "claude", provider.supervisor_provider)
    require(provider.service == "claude-supervisor", provider.service)
    require(
        provider.turn_entrypoint == "Pipeline/TaskReviewAgent/claude_supervisor_turn.py",
        provider.turn_entrypoint,
    )
    require(
        not names_codex(
            (
                provider.service,
                provider.turn_entrypoint,
                provider.conversation_store,
                provider.conversation_store_volume,
            )
        ),
        "the Claude supervisor resolved a Codex service, volume, or entrypoint",
    )

    default_provider = build_supervisor_decision_provider(
        source=ROOT, model=CODEX_MODEL, command_runner=lambda *values, **options: None
    )
    require(default_provider.supervisor_provider == "codex", "default must stay Codex")
    require(default_provider.service == "codex-supervisor", default_provider.service)
    require(
        CodexDockerDecisionProvider is SupervisorDockerDecisionProvider,
        "the historical name must stay the same class object so existing "
        "imports and decide() monkeypatches keep covering every route",
    )


def test_durable_runtime_evidence_names_the_actual_supervisor() -> None:
    """Requirement 9: evidence records the provider that really ran."""

    require_selection_api()
    codex_runtime = describe_codex_runtime()
    require(
        codex_runtime
        == {
            "runtime": "authenticated_codex_cli_docker_goal_loop",
            "api_key_required": False,
            "default_model": codex_runtime["default_model"],
            "credential_source": "CODEX_HOME Docker volume",
        },
        f"the historical Codex runtime description changed: {codex_runtime}",
    )
    claude_runtime = describe_codex_runtime("claude")
    require(claude_runtime["supervisor_provider"] == "claude", claude_runtime)
    require(
        not names_codex(claude_runtime.values()),
        f"Claude runtime evidence named Codex: {claude_runtime}",
    )

    gate_off = gate_off_activation_state(TASK, "claude")
    require(gate_off["supervisor_provider"] == "claude", gate_off)
    require(gate_off["provider"] == "claude-code", gate_off)
    require(
        not names_codex((gate_off["provider"], gate_off["supervisor_provider"])),
        gate_off,
    )
    require(
        gate_off_activation_state(TASK)["provider"] == "openai-codex",
        "the default gate-off report must stay exactly as it was",
    )
    require(
        supervisor_provider_for_identifier("claude-code") == "claude",
        "adapter identity must invert back to the operator selector",
    )


# ---------------------------------------------------------- session identity


def test_supervisor_sessions_never_cross_providers_or_authority() -> None:
    """Requirement 4 and 10: the scope binds provider, model, repository, task, authority."""

    require_selection_api()
    with tempfile.TemporaryDirectory(prefix="supervisor-selection-") as text:
        temp = Path(text)
        common = {
            "source": ROOT,
            "checkout_root": temp / "checkouts",
            "worker_id": "selection-worker",
            "run_id": "selection-run",
            "model": MODEL,
            "reasoning_effort": "high",
            "repository_identity": REPOSITORY,
            "host_identity": "test-host",
        }
        claude = SupervisorSessionOwner(
            **common,
            task_id=TASK,
            supervisor_provider="claude",
            resume_activation=ClaudeResumeActivation(),
        )
        try:
            require(claude.supervisor_provider == "claude", claude.supervisor_provider)
            require(claude.scope is not None, "a Claude activation must open a scope")
            require(
                claude.scope.provider_identifier == "claude-code",
                claude.scope.provider_identifier,
            )
            require(
                not names_codex(
                    (claude.conversation_store, claude.conversation_store_volume)
                ),
                "a Claude supervisor bound the Codex conversation store",
            )
            claude_key = claude.scope.key_sha256()
        finally:
            claude.close()

        codex = SupervisorSessionOwner(
            **common,
            task_id=TASK,
            supervisor_provider="codex",
            resume_activation=CODEX_ACTIVATION,
        )
        try:
            require(
                codex.scope.provider_identifier == "openai-codex",
                codex.scope.provider_identifier,
            )
            require(
                codex.scope.key_sha256() != claude_key,
                "a Claude conversation and a Codex conversation must never share "
                "one compatibility identity",
            )
        finally:
            codex.close()

        # A control verified for one provider can never activate the other.
        expect_error(
            lambda: SupervisorSessionOwner(
                **common,
                task_id=TASK,
                supervisor_provider="claude",
                resume_activation=CODEX_ACTIVATION,
            ),
            SupervisorSessionPoolError,
            "requires an exact ClaudeResumeActivation",
        )
        expect_error(
            lambda: SupervisorSessionOwner(
                **common,
                task_id=TASK,
                supervisor_provider="codex",
                resume_activation=ClaudeResumeActivation(),
            ),
            SupervisorSessionPoolError,
            "requires an exact CodexResumeActivation",
        )

        # Model, repository, and task remain part of the identity.
        def claude_owner(**overrides):
            values = {
                **common,
                "task_id": TASK,
                "supervisor_provider": "claude",
                "resume_activation": ClaudeResumeActivation(),
            }
            values.update(overrides)
            return SupervisorSessionOwner(**values)

        for label, overrides in (
            ("model", {"model": "a-different-model"}),
            ("repository", {"repository_identity": "https://example.invalid/other.git"}),
            ("task", {"task_id": OTHER_TASK}),
        ):
            other = claude_owner(**overrides)
            try:
                require(
                    other.scope.key_sha256() != claude_key,
                    f"a different {label} must not share the Claude session identity",
                )
            finally:
                other.close()


def test_the_provider_refuses_a_session_owner_from_another_provider() -> None:
    """Requirement 4: the decision provider and its pooled owner must agree."""

    require_selection_api()
    with tempfile.TemporaryDirectory(prefix="supervisor-owner-") as text:
        temp = Path(text)
        owner = SupervisorSessionOwner(
            source=ROOT,
            checkout_root=temp / "checkouts",
            task_id=TASK,
            worker_id="selection-worker",
            run_id="selection-run",
            model=MODEL,
            reasoning_effort="high",
            supervisor_provider="claude",
            resume_activation=ClaudeResumeActivation(),
            repository_identity=REPOSITORY,
            host_identity="test-host",
        )
        try:
            expect_error(
                # A Codex model is supplied so the refusal proves the session
                # owner mismatch rather than the model/provider guard.
                lambda: build_supervisor_decision_provider(
                    supervisor_provider="codex",
                    source=ROOT,
                    model=CODEX_MODEL,
                    command_runner=lambda *values, **options: None,
                    session_owner=owner,
                ),
                Exception,
                "names a different provider",
            )
            paired = build_supervisor_decision_provider(
                supervisor_provider="claude",
                source=ROOT,
                model=MODEL,
                command_runner=lambda *values, **options: None,
                session_owner=owner,
            )
            require(paired.supervisor_provider == "claude", paired.supervisor_provider)
        finally:
            owner.close()


def main() -> int:
    tests = (
        test_default_callers_and_legacy_artifacts_still_select_codex,
        test_the_three_provider_selectors_stay_independent,
        test_unsupported_supervisor_values_are_refused,
        test_manifest_persists_claude_and_refuses_a_changed_supervisor_on_resume,
        test_a_supervisor_outside_the_allowlist_stops_before_any_provider,
        test_a_mixed_allowlist_permits_an_explicit_selection,
        test_scheduler_worker_command_carries_the_exact_selected_supervisor,
        test_host_worker_launcher_forwards_the_selection_into_powershell,
        test_the_factory_builds_the_claude_route_and_no_codex_command,
        test_durable_runtime_evidence_names_the_actual_supervisor,
        test_supervisor_sessions_never_cross_providers_or_authority,
        test_the_provider_refuses_a_session_owner_from_another_provider,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"supervisor provider selection tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
