#!/usr/bin/env python3
"""Pure deterministic execution-routing and CLI propagation smoke tests."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.openai_pipeline as openai_pipeline  # noqa: E402
import Pipeline.TaskReviewAgent.run_pipeline_agent as run_pipeline_agent  # noqa: E402
import Pipeline.TaskReviewAgent.host_worker_launcher as host_worker_launcher  # noqa: E402
from Pipeline.ExecutionCrew.run_crew import (  # noqa: E402
    construct_real_provider,
    runtime_configuration,
)
from Pipeline.TaskReviewAgent.contracts import TaskReviewRequest  # noqa: E402
from Pipeline.TaskReviewAgent.execution_routing import (  # noqa: E402
    CAPABILITY_TIERS,
    MAX_SUPERVISOR_TURNS,
    MIN_SUPERVISOR_TURNS,
    ExecutionRecommendation,
    ExecutionRoutingError,
    load_execution_routing_policy,
    resolve_execution_route,
    resolve_task_rigor,
)
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge  # noqa: E402
from Pipeline.TaskReviewAgent.polling_orchestrator import (  # noqa: E402
    build_worker_command,
)
from Pipeline.TaskReviewAgent.host_worker_launcher import (  # noqa: E402
    build_parser as build_host_worker_parser,
    build_powershell_command,
)
from Pipeline.TaskReviewAgent.progress import NullProgress  # noqa: E402
from Pipeline.TaskReviewAgent.run_pipeline_agent import build_parser  # noqa: E402
from Pipeline.TaskReviewAgent.worker_result import (  # noqa: E402
    initialize_worker_run,
    write_pipeline_result,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def recommendation(
    tier: str = "standard",
    preference: str = "no_preference",
    rationale: str = "Ordinary implementation with established repository patterns.",
) -> ExecutionRecommendation:
    return ExecutionRecommendation.from_dict(
        {
            "capability_tier": tier,
            "provider_preference": preference,
            "rationale": rationale,
        }
    )


def policy_environment() -> dict[str, str]:
    environment: dict[str, str] = {}
    for tier in CAPABILITY_TIERS:
        prefix = f"NSC_ROUTE_{tier.upper()}"
        environment[f"{prefix}_DEFAULT_PROVIDER"] = "claude"
        environment[f"{prefix}_ALLOWED_PROVIDERS"] = "openai,claude"
        environment[f"{prefix}_CLAUDE_MODEL"] = f"claude-{tier}-policy"
        environment[f"{prefix}_OPENAI_MODEL"] = f"openai-{tier}-policy"
        environment[f"{prefix}_SUPERVISOR_MODEL"] = f"supervisor-{tier}-policy"
    return environment


def rigor_task(*, synthetic: bool = False, scope: str = "single_agent") -> dict[str, object]:
    value: dict[str, object] = {
        "execution_scope": scope,
        "decomposition_state": "concrete",
        "exclusive_resources": [
            "repo-file:Assets/NoSafeCircle/Feature/FastValue.cs",
            "repo-file:Assets/NoSafeCircle/Feature/FastValue.cs.meta",
        ],
        "completion_gates": [{"gate_id": "VAL-001"}],
    }
    if synthetic:
        value["provenance"] = {
            "origin": "human_approved_synthetic_gauntlet",
            "gauntlet_id": "synthetic-architect-gauntlet-v1",
        }
    return value


def surface(
    *paths: str,
    patterns: tuple[str, ...] = (),
    serialized: tuple[str, ...] = (),
    symbols: tuple[str, ...] = (),
    shared: tuple[str, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        exact_paths=paths,
        path_patterns=patterns,
        unity_serialized_assets=serialized,
        symbols_or_components=symbols,
        shared_systems=shared,
    )


def test_recommendation_parses_all_tiers_strictly() -> None:
    for tier in CAPABILITY_TIERS:
        parsed = recommendation(tier)
        require(parsed.capability_tier == tier, tier)


def test_recommendation_rejects_unknown_empty_missing_and_extra_values() -> None:
    invalid = (
        {"capability_tier": "ultra", "provider_preference": "openai", "rationale": "x"},
        {"capability_tier": "fast", "provider_preference": "other", "rationale": "x"},
        {"capability_tier": "fast", "provider_preference": "openai", "rationale": ""},
        {"capability_tier": "fast", "provider_preference": "openai"},
        {"capability_tier": "fast", "provider_preference": "openai", "rationale": "x", "model": "forbidden"},
    )
    for value in invalid:
        try:
            ExecutionRecommendation.from_dict(value)
        except ExecutionRoutingError:
            pass
        else:
            raise AssertionError(f"invalid recommendation was accepted: {value}")


def test_provider_preferences_resolve_deterministically() -> None:
    policy = load_execution_routing_policy(policy_environment())
    openai = resolve_execution_route(recommendation("standard", "openai"), policy)
    claude = resolve_execution_route(recommendation("standard", "claude"), policy)
    neutral = resolve_execution_route(
        recommendation("standard", "no_preference"), policy
    )
    require(openai.execution_provider == "codex" and openai.preference_honored, str(openai))
    require(claude.execution_provider == "claude" and claude.preference_honored, str(claude))
    require(neutral.execution_provider == "claude" and neutral.preference_honored, str(neutral))


def test_unavailable_preference_uses_only_allowed_default_and_records_fallback() -> None:
    environment = policy_environment()
    environment["NSC_ROUTE_FAST_ALLOWED_PROVIDERS"] = "claude"
    route = resolve_execution_route(
        recommendation("fast", "openai"),
        load_execution_routing_policy(environment),
    )
    require(route.execution_provider == "claude", str(route))
    require(route.preference_honored is False, str(route))
    require("unavailable" in route.route_reason, route.route_reason)


def test_tier_strength_and_budget_are_policy_owned() -> None:
    policy = load_execution_routing_policy(policy_environment())
    routes = [
        resolve_execution_route(recommendation(tier, "openai"), policy)
        for tier in CAPABILITY_TIERS
    ]
    require([item.max_supervisor_turns for item in routes] == [40, 80, 120], str(routes))
    require(
        [item.execution_reasoning_effort for item in routes]
        == ["medium", "high", "xhigh"],
        str(routes),
    )
    require(
        [item.supervisor_reasoning_effort for item in routes]
        == ["medium", "high", "xhigh"],
        str(routes),
    )


def test_architect_text_cannot_supply_a_model_identifier() -> None:
    policy = load_execution_routing_policy(policy_environment())
    route = resolve_execution_route(
        recommendation(
            "deep",
            "openai",
            "Please use architect-invented-model, effort infinite, and 999 turns.",
        ),
        policy,
    )
    require(route.execution_model == "openai-deep-policy", str(route))
    require(route.supervisor_model == "supervisor-deep-policy", str(route))
    require(route.max_supervisor_turns == 120, str(route))


def test_malformed_policy_fails_closed() -> None:
    environment = policy_environment()
    environment["NSC_ROUTE_FAST_MAX_TURNS"] = "unbounded"
    try:
        load_execution_routing_policy(environment)
    except ExecutionRoutingError:
        pass
    else:
        raise AssertionError("malformed routing turn budget was accepted")


def test_host_launcher_turn_range_matches_routing_contract() -> None:
    script = (
        ROOT / "Pipeline" / "TaskReviewAgent" / "Start-GameTaskAgent.ps1"
    ).read_text(encoding="utf-8")
    match = re.search(
        r"\[ValidateRange\((\d+),\s*(\d+)\)\]\s*\[int\]\$MaxTurns\b",
        script,
    )
    require(match is not None, "Start-GameTaskAgent.ps1 MaxTurns range was not found")
    observed = (int(match.group(1)), int(match.group(2)))
    expected = (MIN_SUPERVISOR_TURNS, MAX_SUPERVISOR_TURNS)
    require(observed == expected, f"host MaxTurns range {observed} != routing contract {expected}")

def test_worker_argv_contains_exact_resolved_route() -> None:
    deep_rigor = resolve_task_rigor(
        recommendation("deep", "openai"),
        task={**rigor_task(), "exclusive_resources": []},
        predicted_change_surface=surface("Assets/NoSafeCircle/Feature/FastValue.cs"),
    )
    route = resolve_execution_route(
        recommendation("deep", "openai"),
        load_execution_routing_policy(policy_environment()),
        rigor=deep_rigor,
    )
    command = build_worker_command(
        task_id="NSC-101",
        worker_id="routing-smoke-worker",
        source=Path("/tmp/routing-smoke-source"),
        checkout_root=Path("/tmp/routing-smoke-checkouts"),
        route=route,
        run_id="scheduler-nsc-101-routing-fixture",
        admission_source_head="1" * 40,
        task_contract_sha256="a" * 64,
        admission_issue_number=101,
        provider_allowlist=("codex",),
    )
    require(command[0] == sys.executable and command[1] == "-u", str(command))
    require(Path(command[2]).name == "host_worker_launcher.py", str(command))
    require("docker" not in command, str(command))
    require("--enable-execution-session-pool" not in command, str(command))
    expected = {
        "--execution-provider": "codex",
        "--provider-allowlist": "codex",
        "--execution-model": "openai-deep-policy",
        "--execution-reasoning-effort": "xhigh",
        "--crew-profile": "full",
        "--validation-profile": "full_relevant",
        "--model": "supervisor-deep-policy",
        "--supervisor-reasoning-effort": "xhigh",
        "--max-turns": "120",
        "--run-id": "scheduler-nsc-101-routing-fixture",
        "--admission-source-head": "1" * 40,
        "--task-contract-sha256": "a" * 64,
        "--admission-issue-number": "101",
    }
    for option, value in expected.items():
        require(command[command.index(option) + 1] == value, str(command))

    host_args = build_host_worker_parser().parse_args(list(command[3:]))
    powershell = build_powershell_command(host_args)
    require(powershell[0] == "powershell.exe", str(powershell))
    require("-EnableExecutionSessionPool" not in powershell, str(powershell))
    require(
        any(item.endswith("Start-GameTaskAgent.ps1") for item in powershell),
        str(powershell),
    )
    powershell_expected = {
        "-TaskId": "NSC-101",
        "-WorkerId": "routing-smoke-worker",
        "-ExecutionProvider": "codex",
        "-ProviderAllowlist": "codex",
        "-ExecutionModel": "openai-deep-policy",
        "-ExecutionReasoningEffort": "xhigh",
        "-CrewProfile": "full",
        "-ValidationProfile": "full_relevant",
        "-Model": "supervisor-deep-policy",
        "-SupervisorReasoningEffort": "xhigh",
        "-MaxTurns": "120",
        "-RunId": "scheduler-nsc-101-routing-fixture",
        "-AdmissionSourceHead": "1" * 40,
        "-TaskContractSha256": "a" * 64,
        "-AdmissionIssueNumber": "101",
    }
    for option, value in powershell_expected.items():
        require(powershell[powershell.index(option) + 1] == value, str(powershell))

    claude_recommendation = recommendation("deep", "claude")
    claude_route = resolve_execution_route(
        claude_recommendation,
        load_execution_routing_policy(policy_environment()),
        rigor=resolve_task_rigor(
            claude_recommendation,
            task={**rigor_task(), "exclusive_resources": []},
            predicted_change_surface=surface(
                "Assets/NoSafeCircle/Feature/FastValue.cs"
            ),
        ),
    )
    claude_command = build_worker_command(
        task_id="NSC-101",
        worker_id="routing-claude-worker",
        source=Path("/tmp/routing-smoke-source"),
        checkout_root=Path("/tmp/routing-smoke-checkouts"),
        route=claude_route,
        run_id="scheduler-nsc-101-claude-fixture",
        admission_source_head="1" * 40,
        task_contract_sha256="a" * 64,
        admission_issue_number=101,
    )
    require("--enable-execution-session-pool" in claude_command, str(claude_command))
    claude_host_args = build_host_worker_parser().parse_args(list(claude_command[3:]))
    claude_powershell = build_powershell_command(claude_host_args)
    require("-EnableExecutionSessionPool" in claude_powershell, str(claude_powershell))

    starter_text = (
        ROOT / "Pipeline" / "TaskReviewAgent" / "Start-GameTaskAgent.ps1"
    ).read_text(encoding="utf-8-sig")
    for token in (
        "$SupervisorReasoningEffort",
        "$ExecutionModel",
        "$ExecutionReasoningEffort",
        "$CrewProfile",
        "$ValidationProfile",
        "$EnableExecutionSessionPool",
        "'--supervisor-reasoning-effort'",
        "'--execution-model'",
        "'--execution-reasoning-effort'",
        "'--crew-profile'",
        "'--validation-profile'",
        "'--enable-execution-session-pool'",
        "'--run-id'",
        "'--admission-source-head'",
        "'--task-contract-sha256'",
        "'--admission-issue-number'",
        "exit $AgentExitCode",
    ):
        require(token in starter_text, f"host starter does not propagate {token}")


def test_worker_parser_preserves_manual_defaults_and_accepts_route() -> None:
    defaults = build_parser().parse_args(["--task-id", "NSC-101"])
    require(defaults.execution_provider == "claude", str(defaults))
    require(defaults.model is None and defaults.execution_model is None, str(defaults))
    require(defaults.crew_profile is None and defaults.validation_profile is None, str(defaults))
    require(defaults.enable_execution_session_pool is False, str(defaults))
    require(defaults.max_turns == 120, str(defaults))
    routed = build_parser().parse_args(
        [
            "--task-id", "NSC-101",
            "--execution-provider", "codex",
            "--execution-model", "openai-deep-policy",
            "--execution-reasoning-effort", "xhigh",
            "--crew-profile", "full",
            "--validation-profile", "full_relevant",
            "--model", "supervisor-deep-policy",
            "--supervisor-reasoning-effort", "xhigh",
            "--max-turns", "120",
        ]
    )
    require(routed.execution_model == "openai-deep-policy", str(routed))
    require(routed.supervisor_reasoning_effort == "xhigh", str(routed))
    require(routed.crew_profile == "full", str(routed))
    require(routed.validation_profile == "full_relevant", str(routed))
    pooled = build_parser().parse_args(
        [
            "--task-id", "NSC-101",
            "--execution-provider", "claude",
            "--execution-model", "claude-standard-policy",
            "--enable-execution-session-pool",
        ]
    )
    require(pooled.enable_execution_session_pool is True, str(pooled))


def test_manual_entrypoint_cannot_claim_scheduler_pool_authority() -> None:
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        code = run_pipeline_agent.main(
            [
                "--task-id", "NSC-101",
                "--execution-provider", "claude",
                "--execution-model", "claude-standard-policy",
                "--enable-execution-session-pool",
            ]
        )
    require(code == 2, stderr.getvalue())
    require("requires scheduler-owned run identity" in stderr.getvalue(), stderr.getvalue())


def test_host_wrapper_authenticates_and_republishes_nested_worker_result() -> None:
    with tempfile.TemporaryDirectory(prefix="host-worker-result-") as text:
        root = Path(text)
        source = root / "source"
        starter = source / "Pipeline" / "TaskReviewAgent" / "Start-GameTaskAgent.ps1"
        starter.parent.mkdir(parents=True)
        starter.write_text("exit 0\n", encoding="utf-8")
        output_root = root / "outputs"
        run_id = "scheduler-nsc-101-host-wrapper-fixture"
        worker_id = "polling-worker-nsc-101-host-wrapper"
        original_run = host_worker_launcher.subprocess.run

        def nested_worker(command, **_values):
            run_dir = initialize_worker_run(
                output_root=output_root,
                task_id="NSC-101",
                run_id=run_id,
                worker_id=worker_id,
                started_at_utc=host_worker_launcher._utc_now(),
            )
            write_pipeline_result(
                run_dir=run_dir,
                run_id=run_id,
                worker_id=worker_id,
                task_id="NSC-101",
                source_head="1" * 40,
                task_contract_sha256="a" * 64,
                terminal_status="blocked",
                outcome_authority="fixture_nested_pipeline",
                issue_number=101,
                exit_code=3,
                pid=9876,
            )
            return subprocess.CompletedProcess(command, 3)

        host_worker_launcher.subprocess.run = nested_worker
        try:
            code = host_worker_launcher.main(
                [
                    "--task-id",
                    "NSC-101",
                    "--source",
                    str(source),
                    "--checkout-root",
                    str(root / "checkouts"),
                    "--worker-id",
                    worker_id,
                    "--execution-provider",
                    "claude",
                    "--max-turns",
                    "12",
                    "--output-root",
                    str(output_root),
                    "--run-id",
                    run_id,
                    "--admission-source-head",
                    "1" * 40,
                    "--task-contract-sha256",
                    "a" * 64,
                    "--admission-issue-number",
                    "101",
                ]
            )
        finally:
            host_worker_launcher.subprocess.run = original_run
        require(code == 3, str(code))
        final_path = output_root / "NSC-101" / run_id / "run_result.json"
        payload = json.loads(final_path.read_text(encoding="utf-8"))
        require(payload["terminal_status"] == "blocked", str(payload))
        require(payload["exit_code"] == 3, str(payload))
        require(payload["pid"] == os.getpid(), str(payload))
        require(payload["issue_number"] == 101, str(payload))


def test_host_wrapper_start_failure_writes_authenticated_error_result() -> None:
    with tempfile.TemporaryDirectory(prefix="host-worker-start-error-") as text:
        root = Path(text)
        source = root / "source"
        source.mkdir()
        output_root = root / "outputs"
        run_id = "scheduler-nsc-101-wrapper-start-error"
        worker_id = "polling-worker-nsc-101-wrapper-start-error"
        code = host_worker_launcher.main(
            [
                "--task-id", "NSC-101",
                "--source", str(source),
                "--checkout-root", str(root / "checkouts"),
                "--worker-id", worker_id,
                "--execution-provider", "claude",
                "--max-turns", "12",
                "--output-root", str(output_root),
                "--run-id", run_id,
                "--admission-source-head", "1" * 40,
                "--task-contract-sha256", "a" * 64,
                "--admission-issue-number", "101",
            ]
        )
        require(code == 2, str(code))
        payload = json.loads(
            (
                output_root / "NSC-101" / run_id / "run_result.json"
            ).read_text(encoding="utf-8")
        )
        require(payload["terminal_status"] == "error", str(payload))
        require(payload["outcome_authority"] == "host_launcher_missing", str(payload))
        require(payload["issue_number"] == 101, str(payload))
        require(payload["exit_code"] == 2 and payload["pid"] == os.getpid(), str(payload))


def test_resumed_worker_exception_keeps_admitted_issue_in_pipeline_result() -> None:
    names = (
        "_scheduler_result_enabled",
        "_managed_issue_phase",
        "_require_explicit_fresh_admission",
        "RealTaskReviewWorkflow",
        "ProductionTaskController",
        "GuardedTaskController",
        "run_openai_production_pipeline",
    )
    originals = {name: getattr(run_pipeline_agent, name) for name in names}

    class Workflow:
        def __init__(self, *, source: Path, **_values: object) -> None:
            self.base_observer = SimpleNamespace(root=source)

        @staticmethod
        def observe_goal_state() -> dict[str, object]:
            return {"coordination": {"workflow_state": {"phase": "implementation"}}}

    try:
        run_pipeline_agent._scheduler_result_enabled = lambda _args: True
        run_pipeline_agent._managed_issue_phase = lambda **_values: "implementation"
        run_pipeline_agent._require_explicit_fresh_admission = lambda **_values: None
        run_pipeline_agent.RealTaskReviewWorkflow = Workflow
        run_pipeline_agent.ProductionTaskController = lambda **_values: object()
        run_pipeline_agent.GuardedTaskController = lambda value, progress=None: value

        def fail_pipeline(*_args: object, **_values: object) -> dict[str, object]:
            raise ValueError("fixture resumed pipeline failure")

        run_pipeline_agent.run_openai_production_pipeline = fail_pipeline
        with tempfile.TemporaryDirectory(prefix="resumed-worker-error-") as text:
            root = Path(text)
            run_id = "scheduler-nsc-101-resumed-error"
            code = run_pipeline_agent.main(
                [
                    "--task-id", "NSC-101",
                    "--source", str(root / "source"),
                    "--checkout-root", str(root / "checkouts"),
                    "--output-root", str(root / "outputs"),
                    "--worker-id", "resumed-worker-error-fixture",
                    "--run-id", run_id,
                    "--admission-source-head", "1" * 40,
                    "--task-contract-sha256", "a" * 64,
                    "--admission-issue-number", "101",
                ]
            )
            require(code == 2, str(code))
            payload = json.loads(
                (
                    root
                    / "outputs"
                    / "NSC-101"
                    / run_id
                    / "pipeline_result.json"
                ).read_text(encoding="utf-8")
            )
            require(payload["terminal_status"] == "error", str(payload))
            require(payload["issue_number"] == 101, str(payload))
            require(payload["exit_code"] == 2, str(payload))
    finally:
        for name, value in originals.items():
            setattr(run_pipeline_agent, name, value)


def test_fast_synthetic_task_resolves_lean_but_keeps_human_verification() -> None:
    decision = resolve_task_rigor(
        recommendation("fast"),
        task=rigor_task(synthetic=True),
        predicted_change_surface=surface(
            "Assets/NoSafeCircle/Feature/FastValue.cs",
            "Assets/NoSafeCircle/Feature/FastValue.cs.meta",
        ),
        # Prove that this exact C# sidecar is new; an unproven or existing
        # .meta file must retain full rigor.
        committed_path_probe=committed(),
    )
    require(decision.minimum_capability_tier == "fast", str(decision))
    require(decision.effective_capability_tier == "fast", str(decision))
    require(decision.crew_profile == "lean", str(decision))
    require(decision.validation_profile == "targeted", str(decision))
    require(
        decision.human_verification_policy == "required",
        str(decision),
    )
    route = resolve_execution_route(
        recommendation("fast"),
        load_execution_routing_policy(policy_environment()),
        rigor=decision,
    )
    event = route.to_event_dict()
    require(event["crew_profile"] == "lean", str(event))
    require(event["architect_capability_tier"] == "fast", str(event))


# NSC-914 shape: one trivial C# constant plus the deterministic import sidecar
# ExecutionCrew generates for it. The architect returned fast/low/no_preference.
EXECUTION_ROUTING_SOURCE = ROOT / "Pipeline/TaskReviewAgent/execution_routing.py"
NSC914_SCRIPT = "Assets/NoSafeCircle/DoorPrototype/Scripts/MuffcabbageGauntlet914.cs"
NSC914_META = NSC914_SCRIPT + ".meta"


def committed(*paths: str):
    """Return a probe reporting exactly these paths as already committed."""

    known = {path.replace("\\", "/").casefold() for path in paths}
    return lambda path: path.replace("\\", "/").casefold() in known


def test_new_script_meta_companion_keeps_the_architect_fast_profile() -> None:
    """NSC-914: a deterministic new .cs.meta sidecar is import metadata.

    The architect asked for fast/low. Only the sidecar stood between that and
    the full profile, and a sidecar carries nothing but a schema version and a
    generated GUID.
    """

    decision = resolve_task_rigor(
        recommendation("fast"),
        task={**rigor_task(synthetic=True), "exclusive_resources": []},
        predicted_change_surface=surface(
            NSC914_SCRIPT, serialized=(NSC914_META,)
        ),
        committed_path_probe=committed(),
    )
    require(decision.minimum_capability_tier == "fast", str(decision))
    require(decision.effective_capability_tier == "fast", str(decision))
    require(decision.crew_profile == "lean", str(decision))
    require(decision.validation_profile == "targeted", str(decision))
    require(decision.architect_recommendation_honored, str(decision))
    require(decision.override_reasons == (), str(decision))
    require(
        any("import companions" in reason for reason in decision.reasons),
        str(decision.reasons),
    )
    # The routed model/provider must come from the same effective tier.
    route = resolve_execution_route(
        recommendation("fast"),
        load_execution_routing_policy(policy_environment()),
        rigor=decision,
    )
    require(route.capability_tier == "fast", str(route))
    require(route.execution_model == "claude-fast-policy", str(route))
    require(route.supervisor_model == "supervisor-fast-policy", str(route))


def test_substantive_unity_serialized_assets_still_force_the_full_profile() -> None:
    for asset in (
        "Assets/Scenes/Arena.unity",
        "Assets/NoSafeCircle/Prefabs/Door.prefab",
        "Assets/NoSafeCircle/Data/DoorTuning.asset",
        "Assets/NoSafeCircle/Input/Player.inputactions",
        # A .meta for anything other than a C# script stays substantive.
        "Assets/NoSafeCircle/Prefabs/Door.prefab.meta",
    ):
        decision = resolve_task_rigor(
            recommendation("fast"),
            task={**rigor_task(synthetic=True), "exclusive_resources": []},
            predicted_change_surface=surface(asset, serialized=(asset,)),
            # Even a brand-new asset keeps the full profile.
            committed_path_probe=committed(),
        )
        require(decision.minimum_capability_tier == "deep", f"{asset}: {decision}")
        require(decision.crew_profile == "full", f"{asset}: {decision}")
        require(decision.validation_profile == "full_relevant", f"{asset}: {decision}")
        require(not decision.architect_recommendation_honored, f"{asset}: {decision}")
        require(decision.override_reasons, f"{asset}: {decision}")


def test_orphaned_or_existing_meta_never_receives_the_companion_exemption() -> None:
    orphan = resolve_task_rigor(
        recommendation("fast"),
        task={**rigor_task(synthetic=True), "exclusive_resources": []},
        # The sidecar's own script is not part of this change.
        predicted_change_surface=surface(
            "Assets/NoSafeCircle/Feature/Other.cs", serialized=(NSC914_META,)
        ),
        committed_path_probe=committed(),
    )
    require(orphan.effective_capability_tier == "deep", str(orphan))

    existing = resolve_task_rigor(
        recommendation("fast"),
        task={**rigor_task(synthetic=True), "exclusive_resources": []},
        predicted_change_surface=surface(
            NSC914_SCRIPT, serialized=(NSC914_META,)
        ),
        # Rewriting an existing sidecar changes a GUID other assets reference.
        committed_path_probe=committed(NSC914_SCRIPT, NSC914_META),
        )
    require(existing.effective_capability_tier == "deep", str(existing))

    unprovable = resolve_task_rigor(
        recommendation("fast"),
        task={**rigor_task(synthetic=True), "exclusive_resources": []},
        predicted_change_surface=surface(
            NSC914_SCRIPT, serialized=(NSC914_META,)
        ),
        # No probe: newness is unproven, so the historical full profile stands.
        )
    require(unprovable.effective_capability_tier == "deep", str(unprovable))

    def broken(path: str) -> bool:
        raise OSError("git observation failed")

    unanswerable = resolve_task_rigor(
        recommendation("fast"),
        task={**rigor_task(synthetic=True), "exclusive_resources": []},
        predicted_change_surface=surface(
            NSC914_SCRIPT, serialized=(NSC914_META,)
        ),
        committed_path_probe=broken,
    )
    require(unanswerable.effective_capability_tier == "deep", str(unanswerable))

    outside = resolve_task_rigor(
        recommendation("fast"),
        task={**rigor_task(synthetic=True), "exclusive_resources": []},
        # Import metadata only exists under Assets/.
        predicted_change_surface=surface(
            "Pipeline/Tools/Helper.cs", serialized=("Pipeline/Tools/Helper.cs.meta",)
        ),
        committed_path_probe=committed(),
    )
    require(outside.effective_capability_tier == "deep", str(outside))


def test_broad_or_shared_script_and_meta_work_still_escalates() -> None:
    """The exemption removes one signal; every other risk signal still applies."""

    exempt_surface = {"serialized": (NSC914_META,)}
    for label, task_value, changed_surface in (
        (
            "shared system",
            {**rigor_task(synthetic=True), "exclusive_resources": []},
            surface(NSC914_SCRIPT, shared=("DoorRuntime",), **exempt_surface),
        ),
        (
            "path pattern",
            {**rigor_task(synthetic=True), "exclusive_resources": []},
            surface(NSC914_SCRIPT, patterns=("Assets/**/*.cs",), **exempt_surface),
        ),
        (
            "decomposable work",
            {
                **rigor_task(synthetic=True, scope="needs_execution_decomposition"),
                "exclusive_resources": [],
            },
            surface(NSC914_SCRIPT, **exempt_surface),
        ),
        (
            "protected infrastructure",
            {**rigor_task(synthetic=True), "exclusive_resources": []},
            surface(
                NSC914_SCRIPT,
                "Pipeline/TaskReviewAgent/polling_orchestrator.py",
                **exempt_surface,
            ),
        ),
        (
            "more than four exact paths",
            {**rigor_task(synthetic=True), "exclusive_resources": []},
            surface(
                NSC914_SCRIPT,
                "Assets/NoSafeCircle/Feature/A.cs",
                "Assets/NoSafeCircle/Feature/B.cs",
                "Assets/NoSafeCircle/Feature/C.cs",
                "Assets/NoSafeCircle/Feature/D.cs",
                **exempt_surface,
            ),
        ),
    ):
        decision = resolve_task_rigor(
            recommendation("fast"),
            task=task_value,
            predicted_change_surface=changed_surface,
            committed_path_probe=committed(),
        )
        require(
            decision.effective_capability_tier != "fast",
            f"{label} stayed fast: {decision}",
        )
        require(decision.override_reasons, f"{label}: {decision}")
        require(
            not decision.architect_recommendation_honored, f"{label}: {decision}"
        )


def test_every_meta_spelling_is_classified_even_when_architect_omits_serialized_list() -> None:
    decision = resolve_task_rigor(
        recommendation("fast"),
        task={**rigor_task(), "exclusive_resources": []},
        predicted_change_surface=surface(NSC914_SCRIPT, NSC914_META),
        # Existing sidecar identity is substantive even when the architect did
        # not repeat it in unity_serialized_assets.
        committed_path_probe=committed(NSC914_SCRIPT, NSC914_META),
    )
    require(decision.effective_capability_tier == "deep", str(decision))


def test_unity_scene_logical_and_dot_github_surfaces_force_full_rigor() -> None:
    cases = (
        (
            {
                **rigor_task(),
                "exclusive_resources": [
                    "unity-scene:Assets/Scenes/DoorPrototype.unity"
                ],
            },
            surface("Assets/NoSafeCircle/Feature/FastValue.cs"),
        ),
        (
            {
                **rigor_task(),
                "exclusive_resources": ["logical:door-runtime-contract"],
            },
            surface("Assets/NoSafeCircle/Feature/FastValue.cs"),
        ),
        (
            {**rigor_task(), "exclusive_resources": []},
            surface(".github/workflows/task-review-agent-deterministic.yml"),
        ),
    )
    for task_value, predicted in cases:
        decision = resolve_task_rigor(
            recommendation("fast"),
            task=task_value,
            predicted_change_surface=predicted,
        )
        require(decision.effective_capability_tier == "deep", str(decision))


def test_case_aliases_do_not_inflate_surface_and_broad_symbols_do() -> None:
    aliases = resolve_task_rigor(
        recommendation("fast"),
        task={**rigor_task(), "exclusive_resources": []},
        predicted_change_surface=surface(
            "Assets/NoSafeCircle/Feature/FastValue.cs",
            "assets/nosafecircle/feature/fastvalue.cs",
            "ASSETS/NOSAFECIRCLE/FEATURE/FASTVALUE.CS",
            symbols=("FastValue",),
        ),
    )
    require(aliases.effective_capability_tier == "fast", str(aliases))
    broad_symbols = resolve_task_rigor(
        recommendation("fast"),
        task={**rigor_task(), "exclusive_resources": []},
        predicted_change_surface=surface(
            "Assets/NoSafeCircle/Feature/FastValue.cs",
            symbols=("A", "B", "C", "D", "E"),
        ),
    )
    require(broad_symbols.effective_capability_tier == "standard", str(broad_symbols))


def test_scheduler_worker_builder_refuses_route_without_rigor_authority() -> None:
    route = resolve_execution_route(
        recommendation("fast"), load_execution_routing_policy(policy_environment())
    )
    try:
        build_worker_command(
            task_id="NSC-101",
            worker_id="missing-rigor-worker",
            source=Path("/tmp/routing-smoke-source"),
            checkout_root=Path("/tmp/routing-smoke-checkouts"),
            route=route,
        )
    except Exception as exc:
        require("omitted deterministic rigor authority" in str(exc), str(exc))
    else:
        raise AssertionError("scheduler worker builder accepted an unfloored route")

    scheduler_source = (
        ROOT / "Pipeline" / "TaskReviewAgent" / "polling_orchestrator.py"
    ).read_text(encoding="utf-8")
    require(
        "predicted_change_surface=effective_surface" in scheduler_source,
        "scheduler rigor decision ignored the effective predicted-plus-actual surface",
    )


def test_rigor_event_reports_requested_effective_and_override_policy() -> None:
    policy = load_execution_routing_policy(policy_environment())
    honored = resolve_task_rigor(
        recommendation("fast"),
        task={**rigor_task(synthetic=True), "exclusive_resources": []},
        predicted_change_surface=surface(NSC914_SCRIPT, serialized=(NSC914_META,)),
        committed_path_probe=committed(),
    )
    event = resolve_execution_route(
        recommendation("fast"), policy, rigor=honored
    ).to_event_dict()
    require(event["architect_capability_tier"] == "fast", str(event))
    require(event["capability_tier"] == "fast", str(event))
    require(event["minimum_capability_tier"] == "fast", str(event))
    require(event["crew_profile"] == "lean", str(event))
    require(event["validation_profile"] == "targeted", str(event))
    require(event["architect_recommendation_honored"] is True, str(event))
    require(event["rigor_override_reasons"] == [], str(event))
    require(event["execution_model"] == "claude-fast-policy", str(event))

    overruled = resolve_task_rigor(
        recommendation("fast"),
        task={**rigor_task(synthetic=True), "exclusive_resources": []},
        predicted_change_surface=surface(
            "Assets/Scenes/Arena.unity", serialized=("Assets/Scenes/Arena.unity",)
        ),
        committed_path_probe=committed(),
    )
    overruled_event = resolve_execution_route(
        recommendation("fast"), policy, rigor=overruled
    ).to_event_dict()
    require(overruled_event["architect_capability_tier"] == "fast", str(overruled_event))
    require(overruled_event["capability_tier"] == "deep", str(overruled_event))
    require(overruled_event["crew_profile"] == "full", str(overruled_event))
    require(
        overruled_event["architect_recommendation_honored"] is False,
        str(overruled_event),
    )
    overrides = overruled_event["rigor_override_reasons"]
    require(
        any("Arena.unity" in reason for reason in overrides), str(overrides)
    )
    require(
        any("raised architect tier fast to deep" in reason for reason in overrides),
        str(overrides),
    )
    require(
        set(overrides).issubset(overruled_event["rigor_reasons"]), str(overruled_event)
    )
    require(overruled_event["execution_model"] == "claude-deep-policy", str(overruled_event))


def test_override_reasons_name_only_policy_that_actually_overruled_the_architect() -> None:
    deep_honored = resolve_task_rigor(
        recommendation("deep"),
        task={**rigor_task(synthetic=True), "exclusive_resources": []},
        predicted_change_surface=surface(
            "Assets/NoSafeCircle/Feature/A.cs",
            "Assets/NoSafeCircle/Feature/B.cs",
            "Assets/NoSafeCircle/Feature/C.cs",
            "Assets/NoSafeCircle/Feature/D.cs",
            "Assets/NoSafeCircle/Feature/E.cs",
        ),
        committed_path_probe=committed(),
    )
    require(deep_honored.minimum_capability_tier == "standard", str(deep_honored))
    require(deep_honored.architect_recommendation_honored, str(deep_honored))
    require(deep_honored.override_reasons == (), str(deep_honored))
    require(
        any("more than four exact paths" in reason for reason in deep_honored.reasons),
        str(deep_honored.reasons),
    )

    standard_overruled = resolve_task_rigor(
        recommendation("standard"),
        task={**rigor_task(synthetic=True), "exclusive_resources": []},
        predicted_change_surface=surface(
            "Assets/NoSafeCircle/Feature/A.cs",
            "Assets/NoSafeCircle/Feature/B.cs",
            "Assets/NoSafeCircle/Feature/C.cs",
            "Assets/NoSafeCircle/Feature/D.cs",
            "Assets/Scenes/Arena.unity",
            serialized=("Assets/Scenes/Arena.unity",),
        ),
        committed_path_probe=committed(),
    )
    require(standard_overruled.minimum_capability_tier == "deep", str(standard_overruled))
    require(not standard_overruled.architect_recommendation_honored, str(standard_overruled))
    require(
        not any(
            "more than four exact paths" in reason
            for reason in standard_overruled.override_reasons
        ),
        str(standard_overruled.override_reasons),
    )
    require(
        any("Arena.unity" in reason for reason in standard_overruled.override_reasons),
        str(standard_overruled.override_reasons),
    )
    require(
        any(
            "raised architect tier standard to deep" in reason
            for reason in standard_overruled.override_reasons
        ),
        str(standard_overruled.override_reasons),
    )


def test_human_verification_is_never_reduced_by_the_companion_exemption() -> None:
    """The exemption changes how much machine work runs, never who signs off."""

    for changed_surface, probe in (
        (surface(NSC914_SCRIPT, serialized=(NSC914_META,)), committed()),
        (surface(NSC914_SCRIPT, NSC914_META), committed()),
        (surface("Assets/Scenes/Arena.unity", serialized=("Assets/Scenes/Arena.unity",)), committed()),
    ):
        decision = resolve_task_rigor(
            recommendation("fast"),
            task={**rigor_task(synthetic=True), "exclusive_resources": []},
            predicted_change_surface=changed_surface,
            committed_path_probe=probe,
        )
        require(
            decision.human_verification_policy == "required", str(decision)
        )
    source = Path(EXECUTION_ROUTING_SOURCE).read_text(encoding="utf-8")
    require(
        'human_policy = "required"' in source
        and 'human_policy = "machine_evidence_permitted"' not in source,
        "routing must never select machine_evidence_permitted yet",
    )


def test_policy_raises_fast_serialized_and_infrastructure_work_to_deep() -> None:
    policy = load_execution_routing_policy(policy_environment())
    for changed_surface in (
        surface(
            "Assets/Scenes/Arena.unity",
            serialized=("Assets/Scenes/Arena.unity",),
        ),
        surface("Pipeline/TaskReviewAgent/polling_orchestrator.py"),
    ):
        decision = resolve_task_rigor(
            recommendation("fast"),
            task=rigor_task(synthetic=True),
            predicted_change_surface=changed_surface,
        )
        route = resolve_execution_route(
            recommendation("fast"), policy, rigor=decision
        )
        require(decision.minimum_capability_tier == "deep", str(decision))
        require(route.capability_tier == "deep", str(route))
        require(
            route.rigor is not None and route.rigor.crew_profile == "full",
            str(route),
        )
        require(
            route.rigor.human_verification_policy == "required", str(route)
        )


def test_policy_raises_unknown_or_broad_surface_and_never_lowers_architect() -> None:
    broad = resolve_task_rigor(
        recommendation("fast"),
        task={**rigor_task(), "exclusive_resources": []},
        predicted_change_surface=surface(patterns=("Assets/**/*.cs",)),
    )
    require(broad.minimum_capability_tier == "standard", str(broad))
    require(broad.effective_capability_tier == "standard", str(broad))
    require(broad.human_verification_policy == "required", str(broad))

    conservative = resolve_task_rigor(
        recommendation("deep"),
        task={**rigor_task(), "exclusive_resources": []},
        predicted_change_surface=surface(
            "Assets/NoSafeCircle/Feature/FastValue.cs"
        ),
    )
    require(conservative.minimum_capability_tier == "fast", str(conservative))
    require(conservative.effective_capability_tier == "deep", str(conservative))
    require(conservative.crew_profile == "full", str(conservative))


def test_decomposition_and_shared_systems_always_require_full_profile() -> None:
    for task, changed_surface in (
        (rigor_task(scope="needs_execution_decomposition"), surface("Assets/A.cs")),
        (rigor_task(), surface("Assets/A.cs", shared=("DoorRuntime",))),
    ):
        decision = resolve_task_rigor(
            recommendation("fast"),
            task=task,
            predicted_change_surface=changed_surface,
        )
        require(decision.effective_capability_tier == "deep", str(decision))
        require(decision.validation_profile == "full_relevant", str(decision))
        require(decision.human_verification_policy == "required", str(decision))


def test_worker_entrypoint_propagates_routed_values_without_changing_defaults() -> None:
    captured_controller: dict[str, object] = {}
    captured_supervisor: dict[str, object] = {}
    names = (
        "_managed_issue_phase",
        "_require_explicit_fresh_admission",
        "RealTaskReviewWorkflow",
        "ProductionTaskController",
        "GuardedTaskController",
        "run_openai_production_pipeline",
    )
    originals = {name: getattr(run_pipeline_agent, name) for name in names}

    class Workflow:
        def __init__(self, *, source: Path, task_id: str, checkout_root: Path | None, worker_id: str) -> None:
            self.base_observer = SimpleNamespace(root=source)

        @staticmethod
        def observe_goal_state() -> dict[str, object]:
            return {}

    def controller(**values: object) -> SimpleNamespace:
        captured_controller.update(values)
        return SimpleNamespace(observe=lambda: {})

    def supervisor(*_args: object, **values: object) -> dict[str, str]:
        captured_supervisor.update(values)
        return {"status": "human_action_required"}

    try:
        run_pipeline_agent._managed_issue_phase = lambda **_values: None
        run_pipeline_agent._require_explicit_fresh_admission = lambda **_values: None
        run_pipeline_agent.RealTaskReviewWorkflow = Workflow
        run_pipeline_agent.ProductionTaskController = controller
        run_pipeline_agent.GuardedTaskController = lambda value, progress=None: value
        run_pipeline_agent.run_openai_production_pipeline = supervisor
        with tempfile.TemporaryDirectory(prefix="execution-routing-worker-") as text:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = run_pipeline_agent.main(
                    [
                        "--task-id", "NSC-101",
                        "--source", text,
                        "--output-root", text,
                        "--worker-id", "routing-entrypoint-worker",
                        "--provider-allowlist", "codex",
                        "--execution-provider", "codex",
                        "--execution-model", "openai-deep-policy",
                        "--execution-reasoning-effort", "xhigh",
                        "--crew-profile", "full",
                        "--validation-profile", "full_relevant",
                        "--model", "supervisor-deep-policy",
                        "--supervisor-reasoning-effort", "xhigh",
                        "--max-turns", "120",
                    ]
                )
        require(code == 0, stdout.getvalue())
        require(captured_controller["execution_provider"] == "codex", str(captured_controller))
        require(captured_controller["provider_allowlist"] == ("codex",), str(captured_controller))
        require("quota_fallback_provider" not in captured_controller, str(captured_controller))
        require(captured_controller["execution_model"] == "openai-deep-policy", str(captured_controller))
        require(captured_controller["execution_reasoning_effort"] == "xhigh", str(captured_controller))
        require(captured_controller["crew_profile"] == "full", str(captured_controller))
        require(captured_controller["validation_profile"] == "full_relevant", str(captured_controller))
        require(captured_controller["enable_execution_session_pool"] is False, str(captured_controller))
        require(captured_supervisor["model"] == "supervisor-deep-policy", str(captured_supervisor))
        require(captured_supervisor["reasoning_effort"] == "xhigh", str(captured_supervisor))
        require(captured_supervisor["max_turns"] == 120, str(captured_supervisor))
        captured_controller.clear()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = run_pipeline_agent.main([
                "--task-id", "NSC-101", "--mode", "observe",
                "--execution-provider", "claude", "--provider-allowlist", "claude,codex",
            ])
        require(code == 0, "explicitly permitted Claude route was rejected")
        require(captured_controller["provider_allowlist"] == ("claude", "codex"), str(captured_controller))
        require(captured_controller["quota_fallback_provider"] == "codex", str(captured_controller))
        captured_controller.clear()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = run_pipeline_agent.main([
                "--task-id", "NSC-101", "--mode", "observe",
                "--execution-provider", "claude", "--provider-allowlist", "codex",
            ])
        require(code == 2 and not captured_controller, "forbidden provider reached the worker controller")
    finally:
        for name, value in originals.items():
            setattr(run_pipeline_agent, name, value)


def test_execution_bridge_builds_exact_normal_and_retry_route_commands() -> None:
    with tempfile.TemporaryDirectory(prefix="execution-routing-bridge-") as text:
        checkout = Path(text)
        scope = SimpleNamespace(task_id="NSC-101", accepted=None)
        accepted = SimpleNamespace(
            task_id="NSC-101",
            plan=SimpleNamespace(
                existing_implementation_paths=("Assets/Runtime.cs",),
                new_implementation_paths=(),
                existing_test_paths=("Assets/RuntimeTests.cs",),
                new_test_paths=(),
            ),
        )
        bridge = ExecutionCrewBridge(
            checkout=checkout,
            scope=scope,
            execution_model="openai-deep-policy",
            execution_reasoning_effort="xhigh",
            crew_profile="full",
            validation_profile="full_relevant",
            command_runner=lambda *_args: None,
        )
        normal = bridge._command(
            accepted,
            provider="codex",
            retry_run_id=None,
            feedback_file=None,
        )
        require(normal[normal.index("--model") + 1] == "openai-deep-policy", str(normal))
        require(normal[normal.index("--openai-reasoning-effort") + 1] == "xhigh", str(normal))
        require(normal[normal.index("--provider") + 1] == "codex", str(normal))
        require(normal[normal.index("--crew-profile") + 1] == "full", str(normal))
        require(
            normal[normal.index("--validation-profile") + 1] == "full_relevant",
            str(normal),
        )

        feedback = checkout / "review.txt"
        feedback.write_text("Fix the reviewed behavior.\n", encoding="utf-8")
        retry = bridge._command(
            accepted,
            provider="codex",
            retry_run_id="prior-routing-run",
            feedback_file=feedback,
        )
        require(retry[retry.index("--expected-provider") + 1] == "codex", str(retry))
        require(retry[retry.index("--model") + 1] == "openai-deep-policy", str(retry))
        require(retry[retry.index("--openai-reasoning-effort") + 1] == "xhigh", str(retry))
        require("--crew-profile" not in retry, str(retry))
        require("--validation-profile" not in retry, str(retry))


def test_supervisor_reasoning_reaches_existing_provider_constructor() -> None:
    captured: dict[str, object] = {}
    original = openai_pipeline.CodexDockerDecisionProvider

    class Provider:
        def __init__(self, **values: object) -> None:
            captured.update(values)

    class Controller:
        workflow = SimpleNamespace(
            base_observer=SimpleNamespace(root=ROOT),
            worker_id="routing-smoke-worker",
        )

        @staticmethod
        def observe() -> dict[str, object]:
            return {
                "coordination": {
                    "workflow_state": {
                        "state": "human_action_required",
                        "branch": "orchestrator/routing-smoke",
                        "head_commit": "1" * 40,
                    }
                },
                "production_pipeline": {"status": "human_action_required"},
                "environment": {"ready": True},
                "task": {},
            }

    openai_pipeline.CodexDockerDecisionProvider = Provider
    try:
        result = openai_pipeline.run_openai_production_pipeline(
            TaskReviewRequest("NSC-101"),
            Controller(),
            model="supervisor-deep-policy",
            reasoning_effort="xhigh",
            max_turns=4,
            progress=NullProgress(),
        )
    finally:
        openai_pipeline.CodexDockerDecisionProvider = original
    require(result["status"] == "human_action_required", str(result))
    require(captured["model"] == "supervisor-deep-policy", str(captured))
    require(captured["reasoning_effort"] == "xhigh", str(captured))


def test_executioncrew_runtime_configuration_uses_selected_models_and_codex_effort() -> None:
    claude_key, claude_config = runtime_configuration("claude", "claude-deep-policy")
    codex_key, codex_config = runtime_configuration("codex", "openai-deep-policy")
    for key, config, expected in (
        (claude_key, claude_config, "claude-deep-policy"),
        (codex_key, codex_config, "openai-deep-policy"),
    ):
        models = config.to_dict()["provider_configurations"][key]["models"]
        require(set(models.values()) == {expected}, str(models))
    provider = construct_real_provider("codex", ROOT, False, "xhigh")
    require(provider.reasoning_effort == "xhigh", str(provider.reasoning_effort))


def test_explicit_provider_restriction_overrules_preference_and_ambient_default() -> None:
    from Pipeline.TaskReviewAgent.provider_policy import parse_provider_allowlist
    require(parse_provider_allowlist("codex") == ("codex",), "Codex restriction lost")
    for invalid in ("", "codex,codex", "codex,claude", "openai", " codex"):
        try:
            parse_provider_allowlist(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"malformed restriction accepted: {invalid!r}")
    environment = {
        f"NSC_ROUTE_{tier.upper()}_DEFAULT_PROVIDER": "claude"
        for tier in CAPABILITY_TIERS
    }
    unrestricted = load_execution_routing_policy(environment, default_provider_override="codex")
    restricted = load_execution_routing_policy(environment, provider_allowlist=("codex",))
    for tier in CAPABILITY_TIERS:
        recommendation = ExecutionRecommendation(tier, "claude", "Fixture provider preference")
        require(resolve_execution_route(recommendation, unrestricted).execution_provider == "claude",
                "legacy default override was silently turned into a restriction")
        route = resolve_execution_route(recommendation, restricted)
        require(route.execution_provider == "codex" and not route.preference_honored, str(route))
        require(restricted.for_tier(tier).allowed_execution_providers == {"codex"}, str(restricted))
    environment["NSC_ROUTE_FAST_ALLOWED_PROVIDERS"] = "claude"
    try:
        load_execution_routing_policy(environment, provider_allowlist=("codex",))
    except ExecutionRoutingError as exc:
        require("no provider permitted" in str(exc), str(exc))
    else:
        raise AssertionError("contradictory ambient permissions launched a forbidden provider")


def main() -> int:
    tests = (
        test_explicit_provider_restriction_overrules_preference_and_ambient_default,
        test_recommendation_parses_all_tiers_strictly,
        test_recommendation_rejects_unknown_empty_missing_and_extra_values,
        test_provider_preferences_resolve_deterministically,
        test_unavailable_preference_uses_only_allowed_default_and_records_fallback,
        test_tier_strength_and_budget_are_policy_owned,
        test_fast_synthetic_task_resolves_lean_but_keeps_human_verification,
        test_new_script_meta_companion_keeps_the_architect_fast_profile,
        test_substantive_unity_serialized_assets_still_force_the_full_profile,
        test_orphaned_or_existing_meta_never_receives_the_companion_exemption,
        test_broad_or_shared_script_and_meta_work_still_escalates,
        test_every_meta_spelling_is_classified_even_when_architect_omits_serialized_list,
        test_unity_scene_logical_and_dot_github_surfaces_force_full_rigor,
        test_case_aliases_do_not_inflate_surface_and_broad_symbols_do,
        test_scheduler_worker_builder_refuses_route_without_rigor_authority,
        test_rigor_event_reports_requested_effective_and_override_policy,
        test_override_reasons_name_only_policy_that_actually_overruled_the_architect,
        test_human_verification_is_never_reduced_by_the_companion_exemption,
        test_policy_raises_fast_serialized_and_infrastructure_work_to_deep,
        test_policy_raises_unknown_or_broad_surface_and_never_lowers_architect,
        test_decomposition_and_shared_systems_always_require_full_profile,
        test_architect_text_cannot_supply_a_model_identifier,
        test_malformed_policy_fails_closed,
        test_host_launcher_turn_range_matches_routing_contract,
        test_worker_argv_contains_exact_resolved_route,
        test_worker_parser_preserves_manual_defaults_and_accepts_route,
        test_manual_entrypoint_cannot_claim_scheduler_pool_authority,
        test_host_wrapper_authenticates_and_republishes_nested_worker_result,
        test_host_wrapper_start_failure_writes_authenticated_error_result,
        test_resumed_worker_exception_keeps_admitted_issue_in_pipeline_result,
        test_worker_entrypoint_propagates_routed_values_without_changing_defaults,
        test_execution_bridge_builds_exact_normal_and_retry_route_commands,
        test_supervisor_reasoning_reaches_existing_provider_constructor,
        test_executioncrew_runtime_configuration_uses_selected_models_and_codex_effort,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Execution routing tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
