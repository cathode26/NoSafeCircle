#!/usr/bin/env python3
"""Pure deterministic execution-routing and CLI propagation smoke tests."""

from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.openai_pipeline as openai_pipeline  # noqa: E402
import Pipeline.TaskReviewAgent.run_pipeline_agent as run_pipeline_agent  # noqa: E402
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
    route = resolve_execution_route(
        recommendation("deep", "openai"),
        load_execution_routing_policy(policy_environment()),
    )
    command = build_worker_command(
        task_id="NSC-101",
        worker_id="routing-smoke-worker",
        source=Path("/tmp/routing-smoke-source"),
        checkout_root=Path("/tmp/routing-smoke-checkouts"),
        route=route,
    )
    require(command[0] == sys.executable and command[1] == "-u", str(command))
    require(Path(command[2]).name == "host_worker_launcher.py", str(command))
    require("docker" not in command, str(command))
    expected = {
        "--execution-provider": "codex",
        "--execution-model": "openai-deep-policy",
        "--execution-reasoning-effort": "xhigh",
        "--model": "supervisor-deep-policy",
        "--supervisor-reasoning-effort": "xhigh",
        "--max-turns": "120",
    }
    for option, value in expected.items():
        require(command[command.index(option) + 1] == value, str(command))

    host_args = build_host_worker_parser().parse_args(list(command[3:]))
    powershell = build_powershell_command(host_args)
    require(powershell[0] == "powershell.exe", str(powershell))
    require(
        any(item.endswith("Start-GameTaskAgent.ps1") for item in powershell),
        str(powershell),
    )
    powershell_expected = {
        "-TaskId": "NSC-101",
        "-WorkerId": "routing-smoke-worker",
        "-ExecutionProvider": "codex",
        "-ExecutionModel": "openai-deep-policy",
        "-ExecutionReasoningEffort": "xhigh",
        "-Model": "supervisor-deep-policy",
        "-SupervisorReasoningEffort": "xhigh",
        "-MaxTurns": "120",
    }
    for option, value in powershell_expected.items():
        require(powershell[powershell.index(option) + 1] == value, str(powershell))

    starter_text = (
        ROOT / "Pipeline" / "TaskReviewAgent" / "Start-GameTaskAgent.ps1"
    ).read_text(encoding="utf-8-sig")
    for token in (
        "$SupervisorReasoningEffort",
        "$ExecutionModel",
        "$ExecutionReasoningEffort",
        "'--supervisor-reasoning-effort'",
        "'--execution-model'",
        "'--execution-reasoning-effort'",
    ):
        require(token in starter_text, f"host starter does not propagate {token}")


def test_worker_parser_preserves_manual_defaults_and_accepts_route() -> None:
    defaults = build_parser().parse_args(["--task-id", "NSC-101"])
    require(defaults.execution_provider == "claude", str(defaults))
    require(defaults.model is None and defaults.execution_model is None, str(defaults))
    require(defaults.max_turns == 120, str(defaults))
    routed = build_parser().parse_args(
        [
            "--task-id", "NSC-101",
            "--execution-provider", "codex",
            "--execution-model", "openai-deep-policy",
            "--execution-reasoning-effort", "xhigh",
            "--model", "supervisor-deep-policy",
            "--supervisor-reasoning-effort", "xhigh",
            "--max-turns", "120",
        ]
    )
    require(routed.execution_model == "openai-deep-policy", str(routed))
    require(routed.supervisor_reasoning_effort == "xhigh", str(routed))


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
        return {"status": "succeeded"}

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
                        "--execution-provider", "codex",
                        "--execution-model", "openai-deep-policy",
                        "--execution-reasoning-effort", "xhigh",
                        "--model", "supervisor-deep-policy",
                        "--supervisor-reasoning-effort", "xhigh",
                        "--max-turns", "120",
                    ]
                )
        require(code == 0, stdout.getvalue())
        require(captured_controller["execution_provider"] == "codex", str(captured_controller))
        require(captured_controller["execution_model"] == "openai-deep-policy", str(captured_controller))
        require(captured_controller["execution_reasoning_effort"] == "xhigh", str(captured_controller))
        require(captured_supervisor["model"] == "supervisor-deep-policy", str(captured_supervisor))
        require(captured_supervisor["reasoning_effort"] == "xhigh", str(captured_supervisor))
        require(captured_supervisor["max_turns"] == 120, str(captured_supervisor))
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


def main() -> int:
    tests = (
        test_recommendation_parses_all_tiers_strictly,
        test_recommendation_rejects_unknown_empty_missing_and_extra_values,
        test_provider_preferences_resolve_deterministically,
        test_unavailable_preference_uses_only_allowed_default_and_records_fallback,
        test_tier_strength_and_budget_are_policy_owned,
        test_architect_text_cannot_supply_a_model_identifier,
        test_malformed_policy_fails_closed,
        test_host_launcher_turn_range_matches_routing_contract,
        test_worker_argv_contains_exact_resolved_route,
        test_worker_parser_preserves_manual_defaults_and_accepts_route,
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
