#!/usr/bin/env python3
"""Read-only architect schema, runtime, persistence, and gate smoke tests.

Classification: pure/component tests with temporary AgentRuntime artifacts.
These tests prove polling-orchestrator infrastructure invariants; they do not
claim a Unity task acceptance criterion or touch a canonical Unity asset.

The admission tests below prove the WAIT policy: every form of merge or
integration uncertainty waits, and only a named design/canon escalation
produces HUMAN_REVIEW.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.agent_runner import AgentRunner  # noqa: E402
from Pipeline.AgentRuntime.config import RuntimeConfiguration  # noqa: E402
from Pipeline.AgentRuntime.providers.fake import FakeProvider  # noqa: E402
from Pipeline.AgentRuntime.provider_sessions import (  # noqa: E402
    ProviderSessionBinding,
    ProviderSessionConfirmation,
)
import Pipeline.TaskReviewAgent.architect_preflight as architect_module  # noqa: E402
from Pipeline.TaskReviewAgent.architect_preflight import (  # noqa: E402
    ARCHITECT_ADVISORY_SCHEMA,
    ARCHITECT_BATCH_SCHEMA,
    ArchitectAdvisory,
    ArchitectDecisionCache,
    ArchitectPolicyDecision,
    ArchitectPreflightError,
    PredictedChangeSurface,
    RuntimeArchitectInvoker,
    active_surface_fingerprint,
    analyze_candidate,
    analyze_portfolio,
    architect_decision_cache_key,
    assess_unknown_surface_reservations,
    build_architect_request,
    build_portfolio_request,
    detect_deterministic_conflict,
    evaluate_architect_policy,
    persist_architect_advisory,
    unconfirmed_unknown_surface_task_ids,
)
from Pipeline.TaskReviewAgent.architect_session_owner import (  # noqa: E402
    ArchitectSessionInvocationError,
)


TASK_ID = "NSC-101"
SOURCE_HEAD = "1" * 40
CONTRACT_SHA = "a" * 64
PROVIDER_KEY = "polling-architect-fake"
SESSION_ID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def task() -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "id": TASK_ID,
        "title": "Player HUD health binding",
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "contract_disposition": "active",
        "depends_on": [],
        "exclusive_resources": ["logical:player-hud"],
        "acceptance_criteria": [],
        "completion_gates": [],
        "task_contract_sha256": CONTRACT_SHA,
    }


def advisory_value(
    *,
    task_id: str = TASK_ID,
    contract_sha: str = CONTRACT_SHA,
    work_type: str = "implementation",
    risk: str = "low",
    recommendation: str = "start",
    confidence: float = 0.9,
    exact_paths: list[str] | None = None,
    unity_assets: list[str] | None = None,
    escalation_category: str = "none",
    escalation_question: str = "",
    disjointness: list[dict[str, str]] | None = None,
    conflicting_task_ids: list[str] | None = None,
    capability_tier: str = "standard",
    provider_preference: str = "no_preference",
    execution_rationale: str = "Ordinary local gameplay work with established tests.",
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "source_head": SOURCE_HEAD,
        "task_contract_sha256": contract_sha,
        "predicted_change_surface": {
            "exact_paths": exact_paths or ["Assets/NoSafeCircle/UI/PlayerHud.cs"],
            "path_patterns": ["Assets/NoSafeCircle/UI/*.cs"],
            "unity_serialized_assets": unity_assets or [],
            "symbols_or_components": ["PlayerHud"],
            "shared_systems": ["player health UI"],
        },
        "integration_risk": risk,
        "parallel_recommendation": recommendation,
        "work_type_recommendation": work_type,
        "execution_recommendation": {
            "capability_tier": capability_tier,
            "provider_preference": provider_preference,
            "rationale": execution_rationale,
        },
        "conflicting_task_ids": list(conflicting_task_ids or []),
        "conflict_reasons": [],
        "escalation": {
            "category": escalation_category,
            "question": escalation_question,
        },
        "unknown_surface_disjointness": list(disjointness or []),
        "design_advice": {
            "implementation_summary": (
                "Bind the HUD through the existing player-health API instead of "
                "adding health state to a central manager."
            ),
            "recommended_interfaces": [
                "Prefer the existing player-health event boundary over editing GameManager."
            ],
            "sequencing_notes": ["Wire the component before touching HUD.prefab."],
            "suggested_exclusive_resources": ["logical:player-hud"],
            "suggested_taskgraph_changes": [
                "Consider a dependency only if the health event does not exist."
            ],
            "suggested_decomposition": [
                "Split prefab assembly only if the task also owns scene-wide HUD setup."
            ],
        },
        "evidence": [
            {
                "path": "Assets/NoSafeCircle/UI/PlayerHud.cs",
                "observation": "The fixture treats this as the likely binding component.",
            }
        ],
        "confidence": confidence,
        "assumptions": ["The existing health event remains the supported API."],
    }


def fake_analysis(
    root: Path,
    value: dict[str, Any],
    *,
    reservations: list[dict[str, Any]] | None = None,
) -> tuple[Any, list[Any]]:
    configuration = RuntimeConfiguration(
        {
            PROVIDER_KEY: {
                "provider": "fake",
                "models": {
                    "low_cost": "fake-model",
                    "standard": "fake-model",
                    "high_reasoning": "fake-model",
                },
            }
        }
    )
    runner = AgentRunner(
        root / "agent-runtime",
        configuration,
        {"fake": FakeProvider(structured_output=value)},
    )
    captured: list[Any] = []

    def invoke(request: Any) -> Any:
        captured.append(request)
        return runner.run(request)

    analysis = analyze_candidate(
        task=task(),
        source_head=SOURCE_HEAD,
        reservations=reservations or [],
        scheduler_id="architect-smoke-scheduler",
        artifact_root=root / "advisories",
        invoker=invoke,
        provider_configuration_key=PROVIDER_KEY,
        max_turns=7,
        timeout_seconds=30.0,
    )
    return analysis, captured


def portfolio() -> list[dict[str, Any]]:
    second = dict(task())
    second.update(
        {
            "id": "NSC-102",
            "title": "Split a broad encounter task",
            "execution_scope": "needs_execution_decomposition",
            "decomposition_state": "atomicity_unknown",
            "task_contract_sha256": "b" * 64,
        }
    )
    return [
        {"task": task(), "eligible_work_types": ["implementation"]},
        {"task": second, "eligible_work_types": ["implementation", "decomposition"]},
    ]


def portfolio_result_value() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_head": SOURCE_HEAD,
        "batch_rationale": (
            "Decompose the broad encounter task, then implement the independent HUD task."
        ),
        "considered": [
            {
                "task_id": TASK_ID,
                "work_type": "implementation",
                "disposition": "admit",
                "rationale": "The HUD work is independent and ready.",
            },
            {
                "task_id": "NSC-102",
                "work_type": "decomposition",
                "disposition": "admit",
                "rationale": "Decomposition unlocks smaller encounter tasks.",
            },
            {
                "task_id": "NSC-102",
                "work_type": "implementation",
                "disposition": "wait",
                "rationale": "The broad implementation is not yet atomic.",
            },
        ],
        "admissions": [
            advisory_value(),
            advisory_value(
                task_id="NSC-102",
                contract_sha="b" * 64,
                work_type="decomposition",
            ),
        ],
    }


def portfolio_analysis(
    root: Path,
    value: dict[str, Any],
    *,
    admission_limit: int | None = None,
) -> tuple[Any, list[Any]]:
    configuration = RuntimeConfiguration(
        {
            PROVIDER_KEY: {
                "provider": "fake",
                "models": {
                    "low_cost": "fake-model",
                    "standard": "fake-model",
                    "high_reasoning": "fake-model",
                },
            }
        }
    )
    runner = AgentRunner(
        root / "agent-runtime",
        configuration,
        {"fake": FakeProvider(structured_output=value)},
    )
    captured: list[Any] = []

    def invoke(request: Any) -> Any:
        captured.append(request)
        return runner.run(request)

    analysis = analyze_portfolio(
        candidates=portfolio(),
        source_head=SOURCE_HEAD,
        reservations=[],
        scheduler_id="portfolio-smoke-scheduler",
        artifact_root=root / "advisories",
        invoker=invoke,
        provider_configuration_key=PROVIDER_KEY,
        max_turns=7,
        timeout_seconds=30.0,
        admission_limit=admission_limit,
    )
    return analysis, captured


def test_schema_accepts_complete_advisory() -> None:
    parsed = ArchitectAdvisory.from_dict(advisory_value())
    require(parsed.task_id == TASK_ID, "valid advisory lost task identity")
    require(parsed.integration_risk == "low", "valid risk was not retained")
    require(
        set(ARCHITECT_ADVISORY_SCHEMA["required"])
        == set(ARCHITECT_ADVISORY_SCHEMA["properties"]),
        "schema does not require its entire top-level shape",
    )


def test_malformed_or_missing_fields_fail_closed() -> None:
    malformed = advisory_value()
    del malformed["assumptions"]
    try:
        ArchitectAdvisory.from_dict(malformed)
    except ArchitectPreflightError:
        pass
    else:
        raise AssertionError("missing assumptions was accepted")

    with tempfile.TemporaryDirectory() as text:
        try:
            fake_analysis(Path(text), malformed)
        except ArchitectPreflightError as exc:
            require("schema" in str(exc).casefold(), str(exc))
        else:
            raise AssertionError("AgentRuntime schema failure did not stop analysis")


def test_execution_recommendation_is_strict_and_advisory() -> None:
    for tier in ("fast", "standard", "deep"):
        parsed = ArchitectAdvisory.from_dict(advisory_value(capability_tier=tier))
        require(parsed.execution_recommendation.capability_tier == tier, tier)
    for field, value in (
        ("capability_tier", "ultra"),
        ("provider_preference", "arbitrary-provider"),
        ("rationale", ""),
    ):
        malformed = advisory_value()
        malformed["execution_recommendation"][field] = value
        try:
            ArchitectAdvisory.from_dict(malformed)
        except ArchitectPreflightError:
            pass
        else:
            raise AssertionError(f"invalid execution recommendation {field} was accepted")
    extra = advisory_value()
    extra["execution_recommendation"]["model"] = "architect-controlled-model"
    try:
        ArchitectAdvisory.from_dict(extra)
    except ArchitectPreflightError:
        pass
    else:
        raise AssertionError("architect was allowed to add an execution model")

    wait_advisory = ArchitectAdvisory.from_dict(
        advisory_value(
            recommendation="wait",
            risk="unknown",
            capability_tier="deep",
            provider_preference="openai",
        )
    )
    require(
        evaluate_architect_policy(wait_advisory).decision == "wait",
        "execution recommendation changed WAIT into START",
    )


def test_prompt_contains_task_identity_and_reservation_context() -> None:
    reservation = {
        "task_id": "NSC-202",
        "workflow_state": "human_action_required",
        "phase": "unity_runtime_validation",
        "actual_paths": ["Assets/Scenes/Game.unity"],
        "predicted_paths": [],
        "exclusive_resources": [],
        "unity_serialized_assets": ["Assets/Scenes/Game.unity"],
        "shared_systems": [],
        "evidence_type": "durable_branch_actual",
        "confidence": 1.0,
        "surface_unknown": False,
        "local_active": False,
    }
    request = build_architect_request(
        task=task(),
        source_head=SOURCE_HEAD,
        reservations=[reservation],
        provider_configuration_key=PROVIDER_KEY,
        max_turns=5,
        timeout_seconds=20.0,
        run_id="architect-context-fixture",
    )
    for expected in (TASK_ID, SOURCE_HEAD, CONTRACT_SHA, "NSC-202", "Game.unity"):
        require(expected in request.prompt, f"architect prompt omitted {expected}")
    require("Existing approved GDD and TaskGraph canon are authority" in request.prompt, "canon authority rule missing")
    require("Do not redesign requirements" in request.prompt, "no-redesign rule missing")
    require("central managers or registries" in request.prompt, "Unity hot spots missing")
    require(
        "clean parallelism, not worker utilization" in request.prompt,
        "prompt does not state the parallelism objective",
    )
    require(
        "Never ask for a\n  human merely because conflict prediction is uncertain"
        in request.prompt,
        "prompt does not narrow human review to design/canon ambiguity",
    )


def test_real_request_is_read_only_with_empty_write_boundaries() -> None:
    request = build_architect_request(
        task=task(),
        source_head=SOURCE_HEAD,
        reservations=[],
        provider_configuration_key=PROVIDER_KEY,
        max_turns=6,
        timeout_seconds=25.0,
        run_id="architect-read-only-fixture",
    )
    require(
        request.allowed_capabilities == ("repository_read", "repository_search"),
        str(request.allowed_capabilities),
    )
    require(request.write_boundaries.allowed_paths == (), "architect has allowed writes")
    require(request.write_boundaries.denied_paths == (), "architect has write paths")
    require("repository_write" not in request.allowed_capabilities, "write capability leaked")
    require("approved_command_execution" not in request.allowed_capabilities, "command capability leaked")
    require(request.budgets.turn_limit == 6, "turn budget changed")
    require(request.budgets.timeout_seconds == 25.0, "timeout budget changed")


def test_high_risk_waits() -> None:
    decision = evaluate_architect_policy(
        ArchitectAdvisory.from_dict(advisory_value(risk="high"))
    )
    require(decision.decision == "wait", str(decision))


def test_medium_risk_waits() -> None:
    decision = evaluate_architect_policy(
        ArchitectAdvisory.from_dict(advisory_value(risk="medium"))
    )
    require(decision.decision == "wait", str(decision))


def test_unknown_risk_waits() -> None:
    decision = evaluate_architect_policy(
        ArchitectAdvisory.from_dict(advisory_value(risk="unknown"))
    )
    require(decision.decision == "wait", str(decision))


def test_architect_wait_recommendation_waits() -> None:
    decision = evaluate_architect_policy(
        ArchitectAdvisory.from_dict(advisory_value(recommendation="wait"))
    )
    require(decision.decision == "wait", str(decision))


def test_low_start_with_confidence_passes() -> None:
    decision = evaluate_architect_policy(
        ArchitectAdvisory.from_dict(advisory_value()), min_confidence=0.65
    )
    require(decision.decision == "start", str(decision))


def test_low_confidence_waits() -> None:
    decision = evaluate_architect_policy(
        ArchitectAdvisory.from_dict(advisory_value(confidence=0.64)),
        min_confidence=0.65,
    )
    require(decision.decision == "wait", str(decision))
    require(
        any("confidence" in reason for reason in decision.reasons), str(decision)
    )


def test_merge_conflict_uncertainty_never_reaches_a_human() -> None:
    for value in (
        advisory_value(risk="unknown", recommendation="human_review"),
        advisory_value(risk="medium", recommendation="human_review"),
        advisory_value(confidence=0.10, recommendation="human_review"),
        advisory_value(recommendation="human_review"),
    ):
        decision = evaluate_architect_policy(ArchitectAdvisory.from_dict(value))
        require(decision.decision == "wait", str(decision))


def test_design_or_canon_ambiguity_is_the_only_human_review_basis() -> None:
    for category in (
        "design_or_canon_ambiguity",
        "task_scope_or_contract_change",
        "decomposition_required",
    ):
        decision = evaluate_architect_policy(
            ArchitectAdvisory.from_dict(
                advisory_value(
                    recommendation="human_review",
                    escalation_category=category,
                    escalation_question=(
                        "Should the HUD own health state or read the existing "
                        "player-health event?"
                    ),
                )
            )
        )
        require(decision.decision == "human_review", f"{category}: {decision}")
        require(
            any("player-health event" in reason for reason in decision.reasons),
            str(decision),
        )


def test_escalation_without_a_stated_question_waits() -> None:
    decision = evaluate_architect_policy(
        ArchitectAdvisory.from_dict(
            advisory_value(
                recommendation="human_review",
                escalation_category="decomposition_required",
                escalation_question="   ",
            )
        )
    )
    require(decision.decision == "wait", str(decision))


def test_unknown_surface_blocks_without_disjoint_committed_resources() -> None:
    assessment = assess_unknown_surface_reservations(
        candidate_task_id=TASK_ID,
        candidate_exclusive_resources=(),
        reservations=[
            {
                "task_id": "NSC-202",
                "exclusive_resources": [],
                "surface_unknown": True,
            }
        ],
    )
    require(assessment.blocks_without_architect, str(assessment))
    require(assessment.blocking_task_ids == ("NSC-202",), str(assessment))


def test_unknown_surface_does_not_deadlock_provably_disjoint_work() -> None:
    reservations = [
        {
            "task_id": "NSC-202",
            "exclusive_resources": ["logical:chapel-blockout"],
            "surface_unknown": True,
        }
    ]
    assessment = assess_unknown_surface_reservations(
        candidate_task_id=TASK_ID,
        candidate_exclusive_resources=("logical:player-hud",),
        reservations=reservations,
    )
    require(not assessment.blocks_without_architect, str(assessment))
    require(
        assessment.architect_confirmable_task_ids == ("NSC-202",), str(assessment)
    )
    silent = ArchitectAdvisory.from_dict(advisory_value())
    require(
        unconfirmed_unknown_surface_task_ids(silent, assessment) == ("NSC-202",),
        "an unjustified unknown surface was treated as safe",
    )
    justified = ArchitectAdvisory.from_dict(
        advisory_value(
            disjointness=[
                {
                    "task_id": "NSC-202",
                    "justification": (
                        "NSC-202 owns Chapel blockout geometry; the HUD binding "
                        "touches no scene geometry."
                    ),
                }
            ]
        )
    )
    require(
        unconfirmed_unknown_surface_task_ids(justified, assessment) == (),
        "a justified disjointness claim was ignored",
    )
    contradicted = ArchitectAdvisory.from_dict(
        advisory_value(
            conflicting_task_ids=["NSC-202"],
            disjointness=[
                {"task_id": "NSC-202", "justification": "claims disjoint anyway"}
            ],
        )
    )
    require(
        unconfirmed_unknown_surface_task_ids(contradicted, assessment) == ("NSC-202",),
        "a self-contradicting advisory was accepted",
    )


def test_wait_cache_key_binds_task_head_and_integration_fingerprint() -> None:
    base = dict(
        task_id=TASK_ID,
        task_contract_sha256=CONTRACT_SHA,
        source_head=SOURCE_HEAD,
        integration_fingerprint="d" * 64,
    )
    key = architect_decision_cache_key(**base)
    require(key == architect_decision_cache_key(**base), "cache key is not stable")
    for field, value in (
        ("task_id", "NSC-102"),
        ("task_contract_sha256", "e" * 64),
        ("source_head", "2" * 40),
        ("integration_fingerprint", "f" * 64),
    ):
        changed = dict(base)
        changed[field] = value
        require(
            architect_decision_cache_key(**changed) != key,
            f"cache key ignored a change to {field}",
        )


def test_wait_is_reused_but_start_is_never_cached() -> None:
    cache = ArchitectDecisionCache(max_entries=2)
    key = architect_decision_cache_key(
        task_id=TASK_ID,
        task_contract_sha256=CONTRACT_SHA,
        source_head=SOURCE_HEAD,
        integration_fingerprint="d" * 64,
    )
    wait = ArchitectPolicyDecision("wait", ("medium integration risk",))
    cache.remember(key, wait)
    require(cache.get(key) == wait, "cached wait was not reusable")
    cache.remember(key, ArchitectPolicyDecision("start", ()))
    require(cache.get(key) == wait, "start overwrote a cached wait")
    other = architect_decision_cache_key(
        task_id=TASK_ID,
        task_contract_sha256=CONTRACT_SHA,
        source_head="2" * 40,
        integration_fingerprint="d" * 64,
    )
    require(cache.get(other) is None, "a moved HEAD reused a stale wait")
    third = architect_decision_cache_key(
        task_id="NSC-103",
        task_contract_sha256=CONTRACT_SHA,
        source_head=SOURCE_HEAD,
        integration_fingerprint="d" * 64,
    )
    cache.remember(other, wait)
    cache.remember(third, wait)
    require(len(cache) == 2, f"cache exceeded its bound: {len(cache)}")


def test_a_task_never_conflicts_with_its_own_durable_reservation() -> None:
    resumable = detect_deterministic_conflict(
        candidate_task_id=TASK_ID,
        candidate_exclusive_resources=("logical:player-hud",),
        candidate_surface=ArchitectAdvisory.from_dict(
            advisory_value()
        ).predicted_change_surface,
        reservations=[
            {
                "task_id": TASK_ID,
                "actual_paths": ["Assets/NoSafeCircle/UI/PlayerHud.cs"],
                "predicted_paths": [],
                "unity_serialized_assets": [],
                "exclusive_resources": ["logical:player-hud"],
                "local_active": False,
            }
        ],
    )
    require(resumable is None, str(resumable))
    running = detect_deterministic_conflict(
        candidate_task_id=TASK_ID,
        candidate_exclusive_resources=(),
        candidate_surface=PredictedChangeSurface((), (), (), (), ()),
        reservations=[
            {
                "task_id": TASK_ID,
                "actual_paths": [],
                "predicted_paths": [],
                "unity_serialized_assets": [],
                "exclusive_resources": [],
                "local_active": True,
            }
        ],
    )
    require(running is not None and running.kind == "active_task_id", str(running))


def test_design_suggestions_are_persisted_but_not_applied() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        analysis, captured = fake_analysis(root, advisory_value())
        persisted = json.loads(analysis.artifact_path.read_text(encoding="utf-8"))
        advice = persisted["structured_architect_output"]["design_advice"]
        require("logical:player-hud" in advice["suggested_exclusive_resources"], str(advice))
        require(persisted["authority"] == "advisory_only_not_applied", str(persisted))
        require(all(persisted["explicitly_not_applied"].values()), str(persisted))
        require(not (root / "Tasks").exists(), "architect created a TaskGraph path")
        require(not (root / "Docs").exists(), "architect created a GDD/docs path")
        require(len(captured) == 1, "fake AgentRuntime was not invoked exactly once")


def test_exact_predicted_path_overlap_with_actual_hard_blocks() -> None:
    advisory = ArchitectAdvisory.from_dict(advisory_value())
    conflict = detect_deterministic_conflict(
        candidate_task_id=TASK_ID,
        candidate_exclusive_resources=(),
        candidate_surface=advisory.predicted_change_surface,
        reservations=[
            {
                "task_id": "NSC-202",
                "actual_paths": ["Assets/NoSafeCircle/UI/PlayerHud.cs"],
                "predicted_paths": [],
                "unity_serialized_assets": [],
                "exclusive_resources": [],
                "local_active": False,
            }
        ],
    )
    require(conflict is not None and conflict.kind == "exact_path_actual", str(conflict))


def test_shared_predicted_unity_asset_hard_blocks() -> None:
    surface = ArchitectAdvisory.from_dict(
        advisory_value(
            exact_paths=[], unity_assets=["Assets/NoSafeCircle/UI/HUD.prefab"]
        )
    ).predicted_change_surface
    conflict = detect_deterministic_conflict(
        candidate_task_id=TASK_ID,
        candidate_exclusive_resources=(),
        candidate_surface=surface,
        reservations=[
            {
                "task_id": "NSC-202",
                "actual_paths": [],
                "predicted_paths": [],
                "unity_serialized_assets": ["Assets/NoSafeCircle/UI/HUD.prefab"],
                "exclusive_resources": [],
                "local_active": True,
            }
        ],
    )
    require(conflict is not None and conflict.kind == "unity_serialized_asset", str(conflict))


def test_exact_resource_overlap_blocks_without_llm_judgment() -> None:
    conflict = detect_deterministic_conflict(
        candidate_task_id=TASK_ID,
        candidate_exclusive_resources=("logical:player-hud",),
        candidate_surface=PredictedChangeSurface((), (), (), (), ()),
        reservations=[
            {
                "task_id": "NSC-202",
                "actual_paths": [],
                "predicted_paths": [],
                "unity_serialized_assets": [],
                "exclusive_resources": ["logical:player-hud"],
                "local_active": False,
            }
        ],
    )
    require(conflict is not None and conflict.kind == "exclusive_resource", str(conflict))


def test_meta_companion_paths_conservatively_collide() -> None:
    conflict = detect_deterministic_conflict(
        candidate_task_id=TASK_ID,
        candidate_exclusive_resources=(),
        candidate_surface=PredictedChangeSurface(
            ("Assets/NoSafeCircle/UI/HUD.prefab",), (), (), (), ()
        ),
        reservations=[
            {
                "task_id": "NSC-202",
                "actual_paths": ["Assets/NoSafeCircle/UI/HUD.prefab.meta"],
                "predicted_paths": [],
                "unity_serialized_assets": [],
                "exclusive_resources": [],
                "local_active": False,
            }
        ],
    )
    require(conflict is not None and conflict.kind == "exact_path_actual", str(conflict))


def test_stable_surface_fingerprint_ignores_only_actual_path_growth() -> None:
    reservation = {
        "task_id": "NSC-202",
        "workflow_state": "agent_in_progress",
        "phase": "implementation",
        "branch": "nsc-202-fixture",
        "head": "2" * 40,
        "exclusive_resources": ["logical:fixture"],
        "predicted_paths": ["Assets/Predicted.cs"],
        "actual_paths": ["Assets/First.cs"],
        "unity_serialized_assets": [],
        "shared_systems": ["fixture system"],
        "surface_unknown": False,
        "local_active": True,
    }
    first = active_surface_fingerprint([reservation])
    grown = dict(reservation)
    grown["actual_paths"] = ["Assets/First.cs", "Assets/Second.cs"]
    require(
        active_surface_fingerprint([grown]) == first,
        "actual path growth churned the stable reservation fingerprint",
    )
    changed_membership = dict(reservation)
    changed_membership["head"] = "3" * 40
    require(
        active_surface_fingerprint([changed_membership]) != first,
        "durable branch/head identity did not invalidate the fingerprint",
    )


def test_advisory_artifact_safe_write() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        advisory = ArchitectAdvisory.from_dict(advisory_value())
        path = persist_architect_advisory(
            artifact_root=root,
            analysis_id="safe-write-fixture",
            scheduler_id="scheduler-fixture",
            task=task(),
            source_head=SOURCE_HEAD,
            reservations=[],
            advisory=advisory,
            invocation_metadata={"provider": "fake", "model": "fake-model"},
        )
        require(path.is_file(), "advisory artifact was not published")
        require(not list(root.glob("*.tmp")), "temporary advisory file leaked")
        try:
            persist_architect_advisory(
                artifact_root=root,
                analysis_id="safe-write-fixture",
                scheduler_id="scheduler-fixture",
                task=task(),
                source_head=SOURCE_HEAD,
                reservations=[],
                advisory=advisory,
            )
        except ArchitectPreflightError:
            pass
        else:
            raise AssertionError("safe write overwrote an existing advisory")


def test_same_inputs_yield_same_deterministic_enforcement() -> None:
    advisory = ArchitectAdvisory.from_dict(advisory_value())
    decisions = [
        evaluate_architect_policy(advisory, min_confidence=0.65)
        for _index in range(3)
    ]
    require(decisions[0] == decisions[1] == decisions[2], str(decisions))
    reservations = [
        {
            "task_id": "NSC-202",
            "actual_paths": ["Assets/Other.cs"],
            "predicted_paths": [],
            "unity_serialized_assets": [],
            "exclusive_resources": [],
            "local_active": False,
        }
    ]
    conflicts = [
        detect_deterministic_conflict(
            candidate_task_id=TASK_ID,
            candidate_exclusive_resources=(),
            candidate_surface=advisory.predicted_change_surface,
            reservations=reservations,
        )
        for _index in range(3)
    ]
    require(conflicts[0] == conflicts[1] == conflicts[2], str(conflicts))


def test_mixed_portfolio_request_exposes_both_work_types_read_only() -> None:
    request = build_portfolio_request(
        candidates=portfolio(),
        source_head=SOURCE_HEAD,
        reservations=[],
        provider_configuration_key=PROVIDER_KEY,
        run_id="architect-portfolio-fixture",
    )
    require(request.write_boundaries.allowed_paths == (), str(request.write_boundaries))
    require(request.write_boundaries.denied_paths == (), str(request.write_boundaries))
    require(
        request.to_dict()["output_schema"] == ARCHITECT_BATCH_SCHEMA,
        "portfolio did not request a batch",
    )
    require("at most 2 tasks" in request.prompt, request.prompt)
    require("decomposition as a fallback" in request.prompt, request.prompt)
    require('"decomposition"' in request.prompt, request.prompt)
    require("NSC-101" in request.prompt and "NSC-102" in request.prompt, request.prompt)
    require("`evidence[].path` must be one exact" in request.prompt, request.prompt)
    require("glob or wildcard (`*` or `?`)" in request.prompt, request.prompt)


def test_portfolio_preserves_valid_resume_phase_and_rejects_unknown_phase() -> None:
    candidates = portfolio()
    candidates[1]["resume_phase"] = "decomposition_apply"
    request = build_portfolio_request(
        candidates=candidates,
        source_head=SOURCE_HEAD,
        reservations=[],
        provider_configuration_key=PROVIDER_KEY,
        run_id="architect-resume-phase-fixture",
    )
    require('"resume_phase": "decomposition_apply"' in request.prompt, request.prompt)
    require(
        "exact plan is already human-approved" in request.prompt,
        request.prompt,
    )

    candidates[1]["resume_phase"] = "invented_phase"
    try:
        build_portfolio_request(
            candidates=candidates,
            source_head=SOURCE_HEAD,
            reservations=[],
            provider_configuration_key=PROVIDER_KEY,
            run_id="architect-invalid-resume-phase-fixture",
        )
    except ArchitectPreflightError as exc:
        require("invalid resume_phase" in str(exc), str(exc))
    else:
        raise AssertionError("portfolio accepted an unknown resume phase")


def test_portfolio_returns_ordered_batch_and_persists_full_decision() -> None:
    with tempfile.TemporaryDirectory() as text:
        analysis, captured = portfolio_analysis(Path(text), portfolio_result_value())
        require(
            [item.task_id for item in analysis.batch.admissions]
            == [TASK_ID, "NSC-102"],
            str(analysis.batch),
        )
        artifact = json.loads(analysis.artifact_path.read_text(encoding="utf-8"))
        require(len(artifact["eligible_portfolio"]) == 2, str(artifact))
        require(
            artifact["scheduler"]["admission_count"] == 2,
            str(artifact),
        )
        require(len(artifact["structured_architect_output"]["considered"]) == 3, str(artifact))
        require(len(captured) == 1, str(captured))


def test_portfolio_rejects_pair_outside_deterministic_eligibility() -> None:
    value = portfolio_result_value()
    value["admissions"][0]["work_type_recommendation"] = "decomposition"
    value["considered"][0]["work_type"] = "decomposition"
    with tempfile.TemporaryDirectory() as text:
        try:
            portfolio_analysis(Path(text), value)
        except ArchitectPreflightError as exc:
            require("deterministic portfolio" in str(exc), str(exc))
        else:
            raise AssertionError("portfolio accepted an ineligible task/work-type pair")


def test_portfolio_rejects_missing_pair_consideration() -> None:
    value = portfolio_result_value()
    value["considered"].pop()
    with tempfile.TemporaryDirectory() as text:
        try:
            portfolio_analysis(Path(text), value)
        except ArchitectPreflightError as exc:
            require("consider" in str(exc).casefold(), str(exc))
        else:
            raise AssertionError("portfolio accepted an incomplete consideration set")


def test_portfolio_rejects_duplicate_task_admissions() -> None:
    value = portfolio_result_value()
    value["admissions"].append(
        advisory_value(
            task_id="NSC-102",
            contract_sha="b" * 64,
            work_type="implementation",
        )
    )
    value["considered"][2]["disposition"] = "admit"
    with tempfile.TemporaryDirectory() as text:
        try:
            portfolio_analysis(Path(text), value)
        except ArchitectPreflightError as exc:
            require("duplicate task" in str(exc).casefold(), str(exc))
        else:
            raise AssertionError("portfolio accepted two admissions for one task")


def test_portfolio_rejects_admit_disposition_without_admission() -> None:
    value = portfolio_result_value()
    value["admissions"].pop()
    with tempfile.TemporaryDirectory() as text:
        try:
            portfolio_analysis(Path(text), value)
        except ArchitectPreflightError as exc:
            require("admit" in str(exc).casefold(), str(exc))
        else:
            raise AssertionError("portfolio silently omitted a pair marked admit")


def test_portfolio_rejects_admissions_above_host_capacity() -> None:
    value = portfolio_result_value()
    with tempfile.TemporaryDirectory() as text:
        try:
            portfolio_analysis(Path(text), value, admission_limit=1)
        except ArchitectPreflightError as exc:
            require("admission limit" in str(exc).casefold(), str(exc))
        else:
            raise AssertionError("portfolio exceeded the host admission capacity")


def test_confirmed_invalid_output_uses_typed_session_failure_transport() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        binding = ProviderSessionBinding(
            "claude-code", "polling_architect", "start", SESSION_ID
        )

        class ConfirmedInvalidRuntime:
            configuration_key = PROVIDER_KEY
            confirmed_session = ProviderSessionConfirmation(
                "claude-code", "polling_architect", "start", SESSION_ID
            )

            def __init__(self, **values: Any) -> None:
                require(values["session_binding"] == binding, "CLI lost exact binding")
                configuration = RuntimeConfiguration(
                    {
                        PROVIDER_KEY: {
                            "provider": "fake",
                            "models": {
                                "low_cost": "fake-model",
                                "standard": "fake-model",
                                "high_reasoning": "fake-model",
                            },
                        }
                    }
                )
                self.runner = AgentRunner(
                    root / "agent-runtime",
                    configuration,
                    {"fake": FakeProvider(structured_output={})},
                )

            def __call__(self, request: Any) -> Any:
                return self.runner.run(request)

        original = architect_module.RuntimeArchitectInvoker
        stdin = io.StringIO(
            json.dumps(
                {
                    "source_head": SOURCE_HEAD,
                    "candidates": portfolio(),
                    "reservations": [],
                    "admission_limit": 1,
                    "provider_session": binding.to_dict(),
                }
            )
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        architect_module.RuntimeArchitectInvoker = ConfirmedInvalidRuntime
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                old_stdin = sys.stdin
                sys.stdin = stdin
                try:
                    code = architect_module.main(
                        [
                            "--source",
                            str(ROOT),
                            "--artifact-root",
                            str(root / "advisories"),
                            "--scheduler-id",
                            "typed-output-fixture",
                        ]
                    )
                finally:
                    sys.stdin = old_stdin
        finally:
            architect_module.RuntimeArchitectInvoker = original
        require(code == 2, f"invalid output exit was {code}")
        require(not stdout.getvalue(), "invalid output emitted a success envelope")
        failure = json.loads(stderr.getvalue())
        require(failure["status"] == "architect_session_invocation_failed", str(failure))
        require(failure["lifecycle_outcome"] == "output_failure", str(failure))
        require(failure["confirmed_session_id"] == SESSION_ID, str(failure))


def test_known_codex_resume_retains_the_verified_sandbox_guard() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        binding = ProviderSessionBinding(
            "openai-codex", "polling_architect", "resume", SESSION_ID
        )
        invoker = RuntimeArchitectInvoker(
            source=ROOT,
            artifact_root=root,
            provider="codex",
            model="gpt-fixture",
            session_binding=binding,
        )
        request = architect_module.build_portfolio_request(
            candidates=portfolio(),
            source_head=SOURCE_HEAD,
            reservations=[],
            provider_configuration_key=invoker.configuration_key,
            max_turns=1,
            timeout_seconds=1.0,
            admission_limit=1,
        )
        try:
            invoker(request)
        except ArchitectSessionInvocationError as exc:
            require(exc.lifecycle_outcome == "session_incompatibility", str(exc))
            require(exc.failure_classification == "invalid_request", str(exc))
            require("sandbox" in str(exc).casefold(), str(exc))
        else:
            raise AssertionError("Codex resume bypassed the verified sandbox guard")


def main() -> int:
    tests = (
        test_schema_accepts_complete_advisory,
        test_malformed_or_missing_fields_fail_closed,
        test_execution_recommendation_is_strict_and_advisory,
        test_prompt_contains_task_identity_and_reservation_context,
        test_real_request_is_read_only_with_empty_write_boundaries,
        test_high_risk_waits,
        test_medium_risk_waits,
        test_unknown_risk_waits,
        test_architect_wait_recommendation_waits,
        test_low_start_with_confidence_passes,
        test_low_confidence_waits,
        test_merge_conflict_uncertainty_never_reaches_a_human,
        test_design_or_canon_ambiguity_is_the_only_human_review_basis,
        test_escalation_without_a_stated_question_waits,
        test_unknown_surface_blocks_without_disjoint_committed_resources,
        test_unknown_surface_does_not_deadlock_provably_disjoint_work,
        test_wait_cache_key_binds_task_head_and_integration_fingerprint,
        test_wait_is_reused_but_start_is_never_cached,
        test_a_task_never_conflicts_with_its_own_durable_reservation,
        test_design_suggestions_are_persisted_but_not_applied,
        test_exact_predicted_path_overlap_with_actual_hard_blocks,
        test_shared_predicted_unity_asset_hard_blocks,
        test_exact_resource_overlap_blocks_without_llm_judgment,
        test_meta_companion_paths_conservatively_collide,
        test_stable_surface_fingerprint_ignores_only_actual_path_growth,
        test_advisory_artifact_safe_write,
        test_same_inputs_yield_same_deterministic_enforcement,
        test_mixed_portfolio_request_exposes_both_work_types_read_only,
        test_portfolio_preserves_valid_resume_phase_and_rejects_unknown_phase,
        test_portfolio_returns_ordered_batch_and_persists_full_decision,
        test_portfolio_rejects_pair_outside_deterministic_eligibility,
        test_portfolio_rejects_missing_pair_consideration,
        test_portfolio_rejects_duplicate_task_admissions,
        test_portfolio_rejects_admit_disposition_without_admission,
        test_portfolio_rejects_admissions_above_host_capacity,
        test_confirmed_invalid_output_uses_typed_session_failure_transport,
        test_known_codex_resume_retains_the_verified_sandbox_guard,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Architect preflight tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
