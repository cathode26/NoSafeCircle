from __future__ import annotations

import argparse
import json
import random
import secrets
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import verification_crew as base
from reconciliation_agent import (
    build_proposed_graph_delta,
    render_graph_delta_markdown,
    render_markdown,
    repair_missing_dependency_references,
    run_semantic_validation,
    sanitize_forbidden_evidence,
)
from output_layout import write_current_view


# ============================================================
# PARALLEL VERIFICATION CONFIG
# ============================================================

PARALLEL_MAX_WORKERS = int(
    __import__("os").environ.get("RECONCILIATION_PARALLEL_VERIFY_MAX_WORKERS", "8")
)

COVERAGE_MAX_TURNS = int(
    __import__("os").environ.get("RECONCILIATION_PARALLEL_VERIFY_COVERAGE_TURNS", "16")
)
EVIDENCE_MAX_TURNS = int(
    __import__("os").environ.get("RECONCILIATION_PARALLEL_VERIFY_EVIDENCE_TURNS", "24")
)
RECOVERY_TURN_BONUS = int(
    __import__("os").environ.get("RECONCILIATION_PARALLEL_VERIFY_RECOVERY_TURN_BONUS", "12")
)
MAX_TURN_RECOVERY_ATTEMPTS = int(
    __import__("os").environ.get("RECONCILIATION_PARALLEL_VERIFY_MAX_TURN_RECOVERY_ATTEMPTS", "1")
)
STRUCTURE_MAX_TURNS = int(
    __import__("os").environ.get("RECONCILIATION_PARALLEL_VERIFY_STRUCTURE_TURNS", "18")
)
EXECUTION_MAX_TURNS = int(
    __import__("os").environ.get("RECONCILIATION_PARALLEL_VERIFY_EXECUTION_TURNS", "16")
)


@dataclass(frozen=True)
class AuditSpec:
    key: str
    agent_name: str
    prompt_file: str
    schema: dict[str, Any]
    kind: str
    domain: str
    scope: str
    max_turns: int


# Stable domain routing follows the same ownership split used by the parallel
# reconciliation path. These keys are routing metadata, not evidence/canon.
DOMAIN_KEYS: dict[str, set[str]] = {
    "player_core": {
        "player",
        "player-movement",
        "player-health",
        "player-mana",
    },
    "wizard_combat": {
        "combat",
        "fireball",
        "frost-field",
        "force-wave",
    },
    "enemy_state": {
        "enemies",
        "active-enemy-registry",
        "enemy-health-damage-defeat",
        "enemy-status-effect-displacement",
    },
    "enemy_behavior": {
        "enemy-pursuit-search-foundation",
        "melee-enemy",
        "ranged-enemy",
        "locked-door-enemy-attack",
    },
    "doors": {
        "doors",
        "door-open-interaction",
        "doorway-crossing-state",
        "door-close-lock-break-lifecycle",
    },
    "world_foundations": {
        "world",
        "fixed-isometric-camera",
        "tilemap-navigation-package-configuration",
        "gameplay-navigation-locomotion",
        "world-visual-foundation",
    },
    "content_encounters": {
        "five-room-content-authoring",
        "encounters",
        "encounter-admission-cap-enforcement",
        "dungeon-encounter-content-authoring",
    },
    "run_lifecycle": {
        "floor-run-restart",
        "floor-run-restart-bootstrap",
        "floor-run-restart-persistent-closure",
        "win-loss-conditions",
        "final-escape-victory",
    },
    "global_pipeline": {
        "no-safe-circle",
        "delivery-and-build",
        "windows-build-scene-registration",
    },
}

KEY_TO_DOMAIN = {
    key: domain
    for domain, keys in DOMAIN_KEYS.items()
    for key in keys
}


COVERAGE_SCOPES = {
    "player_core": (
        "Audit mandatory GDD coverage only for Player Movement/input, Player Health, "
        "Player Mana, player position/movement-restriction ownership, health/mana "
        "feedback, player-core reset responsibilities, and directly owned validation."
    ),
    "wizard_combat": (
        "Audit mandatory GDD coverage only for Fireball, Frost Field casting/player "
        "feedback, Force Wave, spell-local state/reset, mana-spend contracts, charged "
        "Fireball movement restriction consumption, cursor aiming where specified, and "
        "spell-to-enemy interfaces."
    ),
    "enemy_state": (
        "Audit mandatory GDD coverage only for Enemy Health/Defeat, Active Enemy "
        "Registry, persistent enemy bookkeeping, Frost slowdown application/restoration, "
        "forced displacement/state hand-back, defeat bookkeeping, and enemy-state reset."
    ),
    "enemy_behavior": (
        "Audit mandatory GDD coverage only for detection, pursuit, target loss/search/"
        "reacquisition, Melee Enemy, Ranged Enemy, telegraph/LOS/occlusion, locked-door "
        "attack initiation, and locomotion/navigation consumption."
    ),
    "doors": (
        "Audit mandatory GDD coverage only for door targeting/opening/interruption, "
        "doorway crossing, close/lock/heal request, durability/damage/breaking, semantic "
        "door state/passability publication, forward-only behavior, and door feedback."
    ),
    "world_foundations": (
        "Audit mandatory GDD coverage only for fixed isometric camera, approved packages, "
        "Tilemap/SpriteRenderer foundation, gameplay navigation/locomotion, passability "
        "translation, visual/gameplay separation, sorting, and world foundation."
    ),
    "content_encounters": (
        "Audit mandatory GDD coverage only for five named spaces/content authoring, "
        "encounter admission/cap runtime, encounter/content authoring and deferral, "
        "room-specific tactical checks, encounter size, and room/encounter prerequisites."
    ),
    "run_lifecycle": (
        "Audit mandatory GDD coverage only for zero-health loss, Floor Run/Restart "
        "orchestration, staged/current-owner and full persistent closure, win/loss, final "
        "escape/victory, input shutdown, and You Escaped presentation."
    ),
    "global_pipeline": (
        "Audit mandatory GDD coverage only for delivery/build obligations, Windows scene "
        "registration, no-runtime-AI requirement, Development Agent Ownership Invariants "
        "as process constraints, validation/human gates, minimal context, retry rules, "
        "token budget/process constraints, stretch/excluded scope, and global Player "
        "Experience validation requirements not naturally owned by one gameplay domain."
    ),
}


def build_specs() -> list[AuditSpec]:
    specs: list[AuditSpec] = []

    for domain, scope in COVERAGE_SCOPES.items():
        specs.append(
            AuditSpec(
                key=f"coverage_{domain}",
                agent_name=f"Coverage — {domain.replace('_', ' ').title()}",
                prompt_file="coverage_auditor.md",
                schema=base.COVERAGE_AUDIT_SCHEMA,
                kind="coverage",
                domain=domain,
                scope=scope,
                max_turns=COVERAGE_MAX_TURNS,
            )
        )

    specs.extend(
        [
            AuditSpec(
                key="evidence_player_combat_doors",
                agent_name="Evidence — Player Combat Doors",
                prompt_file="evidence_auditor.md",
                schema=base.GENERAL_AUDIT_SCHEMA,
                kind="evidence",
                domain="player_combat_doors",
                scope=(
                    "Audit repository evidence/status claims only for player core, spells/"
                    "combat, doors/interaction, doorway crossing, and directly connected "
                    "current prototype scene/input evidence. Do not audit enemy/world/"
                    "delivery evidence."
                ),
                max_turns=EVIDENCE_MAX_TURNS,
            ),
            AuditSpec(
                key="evidence_enemy_encounters",
                agent_name="Evidence — Enemies Encounters",
                prompt_file="evidence_auditor.md",
                schema=base.GENERAL_AUDIT_SCHEMA,
                kind="evidence",
                domain="enemy_encounters",
                scope=(
                    "Audit repository evidence/status claims only for enemy shared state, "
                    "enemy pursuit/archetypes/attacks, registry/status/displacement, "
                    "encounter admission, and current encounter/content evidence."
                ),
                max_turns=EVIDENCE_MAX_TURNS,
            ),
            AuditSpec(
                key="evidence_world_run_delivery",
                agent_name="Evidence — World Run Delivery",
                prompt_file="evidence_auditor.md",
                schema=base.GENERAL_AUDIT_SCHEMA,
                kind="evidence",
                domain="world_run_delivery",
                scope=(
                    "Audit repository evidence/status claims only for camera/world/"
                    "navigation/packages, run/restart/victory, ProjectSettings, scene/build "
                    "registration, and delivery/configuration."
                ),
                max_turns=EVIDENCE_MAX_TURNS,
            ),
            AuditSpec(
                key="structure_dependencies",
                agent_name="Structure — Dependencies Ownership Decomposition",
                prompt_file="structure_auditor.md",
                schema=base.GENERAL_AUDIT_SCHEMA,
                kind="structure",
                domain="dependencies",
                scope=(
                    "Audit ONLY parent hierarchy, dependency correctness, dependency target "
                    "kind, cycles, shared-capability ownership, under/over decomposition, "
                    "runtime-vs-deferred-content separation, reset closure, and cross-system "
                    "owner/consumer contracts. Ignore exclusive-resource coverage except "
                    "when needed to distinguish a lock from an illegal dependency."
                ),
                max_turns=STRUCTURE_MAX_TURNS,
            ),
            AuditSpec(
                key="structure_resources",
                agent_name="Structure — Exclusive Resources",
                prompt_file="structure_auditor.md",
                schema=base.GENERAL_AUDIT_SCHEMA,
                kind="resources",
                domain="resources",
                scope=(
                    "Audit ONLY exclusive_resources and shared-writer concurrency safety. "
                    "Require positive evidence that a task writes/integrates through the "
                    "resource. Detect missing identical locks for real concurrent writers "
                    "and overbroad locks on read-only/eventual consumers. Do not recommend "
                    "dependency ordering for pure write collisions."
                ),
                max_turns=STRUCTURE_MAX_TURNS,
            ),
            AuditSpec(
                key="execution_scope",
                agent_name="Execution Scope",
                prompt_file="execution_scope_auditor.md",
                schema=base.GENERAL_AUDIT_SCHEMA,
                kind="execution",
                domain="execution",
                scope=(
                    "Audit ONLY execution_scope/execution_reason and whether open executable "
                    "work is truly bounded for one agent versus needs execution decomposition "
                    "or human integration. Do not redesign dependencies or game mechanics."
                ),
                max_turns=EXECUTION_MAX_TURNS,
            ),
        ]
    )

    return specs


SPECS = build_specs()
SPEC_BY_KEY = {spec.key: spec for spec in SPECS}
SPEC_BY_AGENT = {spec.agent_name: spec for spec in SPECS}


# ============================================================
# MODEL ASSIGNMENT
# ============================================================

def choose_models(rng: random.Random) -> dict[str, str]:
    pool = list(base.MODEL_POOL)
    if not pool:
        raise RuntimeError("No verifier model pool configured.")

    # Shuffle then round-robin so large groups do not accidentally collapse to
    # one model while remaining reproducible from the saved seed.
    order = pool[:]
    rng.shuffle(order)

    assignments: dict[str, str] = {}
    for index, spec in enumerate(SPECS):
        assignments[spec.key] = order[index % len(order)]

    return assignments


# ============================================================
# AUDIT EXECUTION
# ============================================================

def build_scoped_prompt(
    *,
    spec: AuditSpec,
    candidate_path: Path,
    source_run_id: str,
    pass_label: str,
) -> str:
    original = base.build_audit_prompt(
        prompt_file=spec.prompt_file,
        candidate_path=candidate_path,
        source_run_id=source_run_id,
        pass_label=pass_label,
    )

    return (
        original
        + "\n\n---\n\n"
        + f"# PARALLEL AUDIT SCOPE — {spec.agent_name}\n\n"
        + spec.scope
        + "\n\n"
        + "This scope override is deliberate. Read the entire current GDD so cross-"
          "section qualifiers are not missed, but emit requirements/findings ONLY "
          "for this assigned audit territory. Do not report another parallel "
          "auditor's territory merely because you noticed it. Cross-domain facts "
          "may be cited only when necessary to evaluate an owner/consumer contract "
          "inside your territory.\n\n"
        + "The independent audit union—not any single auditor—provides whole-project "
          "coverage. Do not vote, defer, or assume another auditor's conclusion.\n"
    )


def _is_max_turn_failure(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "max_turns" in message
        or "maximum number of turns" in message
        or "error_max_turns" in message
    )


def _failure_payload(
    *,
    spec: AuditSpec,
    model: str,
    attempt: int,
    max_turns: int,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "agent": spec.agent_name,
        "audit_key": spec.key,
        "requested_model": model,
        "attempt": attempt,
        "max_turns": max_turns,
        "failure_type": (
            "max_turns" if _is_max_turn_failure(exc) else "other"
        ),
        "error": str(exc),
    }


def run_specs(
    *,
    specs: list[AuditSpec],
    candidate_path: Path,
    source_run_id: str,
    pass_label: str,
    output_dir: Path,
    assignments: dict[str, str],
) -> list[dict[str, Any]]:
    """
    Run all requested auditors without fail-fast loss.

    Successful auditor outputs are persisted as soon as each future is consumed.
    A max-turn failure does not abort collection of the other independent
    auditors. After the first wave finishes, only max-turn failures are retried,
    with a larger turn budget.

    This matters because independent verification work is expensive and should
    never be discarded just because one auditor needs a larger tool-use budget.
    """
    output_dir.mkdir(parents=True, exist_ok=False)

    results_by_key: dict[str, dict[str, Any]] = {}
    first_wave_failures: dict[str, tuple[AuditSpec, Exception]] = {}

    def invoke(spec: AuditSpec, *, max_turns: int) -> dict[str, Any]:
        result = base.invoke_read_only_agent(
            agent_name=spec.agent_name,
            model=assignments[spec.key],
            prompt=build_scoped_prompt(
                spec=spec,
                candidate_path=candidate_path,
                source_run_id=source_run_id,
                pass_label=pass_label,
            ),
            schema=spec.schema,
            timeout_seconds=base.VERIFY_TIMEOUT_SECONDS,
            max_turns=max_turns,
        )
        result["verification_attempt"] = 1
        result["max_turns_used"] = max_turns
        return result

    max_workers = max(1, min(PARALLEL_MAX_WORKERS, len(specs)))

    # First wave: never abort the whole wave on one auditor failure.
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(invoke, spec, max_turns=spec.max_turns): spec
            for spec in specs
        }

        for future in as_completed(future_map):
            spec = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                first_wave_failures[spec.key] = (spec, exc)
                base.save_new_json(
                    output_dir / f"{spec.key}.attempt1.failure.json",
                    _failure_payload(
                        spec=spec,
                        model=assignments[spec.key],
                        attempt=1,
                        max_turns=spec.max_turns,
                        exc=exc,
                    ),
                )
                print(
                    f"Auditor failed but other auditors will continue: "
                    f"{spec.agent_name} — {exc}"
                )
                continue

            results_by_key[spec.key] = result
            base.save_new_json(output_dir / f"{spec.key}.json", result)

    unrecovered: dict[str, tuple[AuditSpec, Exception]] = {}

    if first_wave_failures:
        max_turn_failures = {
            key: value
            for key, value in first_wave_failures.items()
            if _is_max_turn_failure(value[1])
        }
        non_retriable_failures = {
            key: value
            for key, value in first_wave_failures.items()
            if key not in max_turn_failures
        }
        unrecovered.update(non_retriable_failures)

        if max_turn_failures and MAX_TURN_RECOVERY_ATTEMPTS > 0:
            print()
            print("=" * 72)
            print("MAX-TURN RECOVERY")
            print("=" * 72)
            print(
                f"Retrying {len(max_turn_failures)} auditor(s) only; "
                "successful auditors will NOT be rerun."
            )
            for key, (spec, _) in sorted(max_turn_failures.items()):
                print(
                    f"  {key}: {spec.max_turns} -> "
                    f"{spec.max_turns + RECOVERY_TURN_BONUS} turns"
                )
            print("=" * 72)

            # Current policy is one bounded recovery wave. The env setting is
            # retained so the policy can be expanded without changing the CLI.
            recovery_specs = [value[0] for value in max_turn_failures.values()]

            def recover(spec: AuditSpec) -> dict[str, Any]:
                recovery_turns = spec.max_turns + RECOVERY_TURN_BONUS
                result = base.invoke_read_only_agent(
                    agent_name=f"{spec.agent_name} [recovery]",
                    model=assignments[spec.key],
                    prompt=build_scoped_prompt(
                        spec=spec,
                        candidate_path=candidate_path,
                        source_run_id=source_run_id,
                        pass_label=f"{pass_label}-max-turn-recovery",
                    ),
                    schema=spec.schema,
                    timeout_seconds=base.VERIFY_TIMEOUT_SECONDS,
                    max_turns=recovery_turns,
                )
                # Normalize the agent name so merge/final-pass replacement logic
                # treats the recovered result as the original auditor.
                result["agent"] = spec.agent_name
                result["verification_attempt"] = 2
                result["recovered_from"] = "max_turns"
                result["max_turns_used"] = recovery_turns
                return result

            recovery_workers = max(
                1,
                min(PARALLEL_MAX_WORKERS, len(recovery_specs)),
            )
            with ThreadPoolExecutor(max_workers=recovery_workers) as executor:
                future_map = {
                    executor.submit(recover, spec): spec
                    for spec in recovery_specs
                }

                for future in as_completed(future_map):
                    spec = future_map[future]
                    recovery_turns = spec.max_turns + RECOVERY_TURN_BONUS
                    try:
                        result = future.result()
                    except Exception as exc:
                        unrecovered[spec.key] = (spec, exc)
                        base.save_new_json(
                            output_dir / f"{spec.key}.attempt2.failure.json",
                            _failure_payload(
                                spec=spec,
                                model=assignments[spec.key],
                                attempt=2,
                                max_turns=recovery_turns,
                                exc=exc,
                            ),
                        )
                        continue

                    results_by_key[spec.key] = result
                    base.save_new_json(
                        output_dir / f"{spec.key}.json",
                        result,
                    )
        else:
            unrecovered.update(max_turn_failures)

    if unrecovered:
        details = "; ".join(
            f"{key}: {exc}"
            for key, (_, exc) in sorted(unrecovered.items())
        )
        raise RuntimeError(
            "Parallel verification preserved every successful auditor result, "
            "but one or more auditors still failed after bounded recovery. "
            + details
        )

    missing = [
        spec.key
        for spec in specs
        if spec.key not in results_by_key
    ]
    if missing:
        raise RuntimeError(
            "Parallel verification ended without results for: "
            + ", ".join(sorted(missing))
        )

    results = [
        results_by_key[spec.key]
        for spec in specs
    ]
    results.sort(key=lambda item: item["agent"])
    return results


# ============================================================
# SELECTIVE PASS 2
# ============================================================

STRUCTURE_FIELDS = {
    "kind",
    "parent_key",
    "depends_on",
    "decomposition_state",
    "decomposition_reason",
}
RESOURCE_FIELDS = {"exclusive_resources"}
EXECUTION_FIELDS = {"execution_scope", "execution_reason"}
EVIDENCE_FIELDS = {
    "repository_state",
    "graph_status",
    "repository_evidence",
}
COVERAGE_FIELDS = {
    "basis",
    "source_scope",
    "gdd_evidence",
    "acceptance_criteria",
    "validation_requirements",
    "notes",
}


def item_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("key", "")): item
        for item in payload.get("work_items", [])
        if str(item.get("key", "")).strip()
    }


def domain_for_key(
    key: str,
    source_items: dict[str, dict[str, Any]],
    refined_items: dict[str, dict[str, Any]],
) -> str | None:
    known = KEY_TO_DOMAIN.get(key)
    if known:
        return known

    # New implementation nodes often retain a known feature parent. Walk parent
    # chains in either candidate before falling back to broad re-audit.
    for mapping in (refined_items, source_items):
        current = key
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            item = mapping.get(current)
            if item is None:
                break
            parent = str(item.get("parent_key", "")).strip()
            if not parent:
                break
            known = KEY_TO_DOMAIN.get(parent)
            if known:
                return known
            current = parent

    return None


def evidence_specs_for_domain(domain: str) -> set[str]:
    if domain in {"player_core", "wizard_combat", "doors"}:
        return {"evidence_player_combat_doors"}
    if domain in {"enemy_state", "enemy_behavior", "content_encounters"}:
        return {"evidence_enemy_encounters"}
    if domain in {"world_foundations", "run_lifecycle", "global_pipeline"}:
        return {"evidence_world_run_delivery"}
    return {
        "evidence_player_combat_doors",
        "evidence_enemy_encounters",
        "evidence_world_run_delivery",
    }


def changed_audit_keys(
    source_payload: dict[str, Any],
    refined_payload: dict[str, Any],
) -> set[str]:
    selected: set[str] = set()

    source_items = item_map(source_payload)
    refined_items = item_map(refined_payload)
    all_keys = set(source_items) | set(refined_items)

    unknown_domain_change = False

    for key in all_keys:
        before = source_items.get(key)
        after = refined_items.get(key)

        if before is None or after is None:
            changed_fields = (
                STRUCTURE_FIELDS
                | RESOURCE_FIELDS
                | EXECUTION_FIELDS
                | EVIDENCE_FIELDS
                | COVERAGE_FIELDS
            )
        else:
            changed_fields = {
                field
                for field in (
                    STRUCTURE_FIELDS
                    | RESOURCE_FIELDS
                    | EXECUTION_FIELDS
                    | EVIDENCE_FIELDS
                    | COVERAGE_FIELDS
                )
                if before.get(field) != after.get(field)
            }

        if not changed_fields:
            continue

        domain = domain_for_key(key, source_items, refined_items)
        if domain is None:
            unknown_domain_change = True
        else:
            if changed_fields & COVERAGE_FIELDS:
                selected.add(f"coverage_{domain}")
                # Global Pipeline owns project-wide Player Experience/process
                # mappings that may point at domain-owned work items. Recheck it
                # whenever acceptance/validation/GDD mapping changes anywhere.
                selected.add("coverage_global_pipeline")
            if changed_fields & EVIDENCE_FIELDS:
                selected.update(evidence_specs_for_domain(domain))

        if changed_fields & STRUCTURE_FIELDS:
            selected.add("structure_dependencies")
        if changed_fields & RESOURCE_FIELDS:
            selected.add("structure_resources")
        if changed_fields & EXECUTION_FIELDS:
            selected.add("execution_scope")

    # Global typed/deferred records are covered by global_pipeline.
    if (
        source_payload.get("non_code_requirements")
        != refined_payload.get("non_code_requirements")
        or source_payload.get("deferred_or_excluded")
        != refined_payload.get("deferred_or_excluded")
    ):
        selected.add("coverage_global_pipeline")

    # Changes to unresolved questions may reflect cross-domain structural repair.
    if (
        source_payload.get("unresolved_questions")
        != refined_payload.get("unresolved_questions")
    ):
        selected.add("structure_dependencies")

    if unknown_domain_change:
        selected.update(
            spec.key for spec in SPECS if spec.kind in {"coverage", "evidence"}
        )
        selected.update({"structure_dependencies", "structure_resources"})

    return selected


def auditors_with_findings(
    audits: list[dict[str, Any]],
) -> set[str]:
    selected: set[str] = set()

    for audit in audits:
        result = audit.get("result", {})
        if result.get("findings"):
            spec = SPEC_BY_AGENT.get(str(audit.get("agent", "")))
            if spec is not None:
                selected.add(spec.key)

    return selected


def final_audit_set(
    *,
    pass1_audits: list[dict[str, Any]],
    rerun_audits: list[dict[str, Any]],
    selected_keys: set[str],
) -> list[dict[str, Any]]:
    rerun_by_agent = {
        str(audit.get("agent", "")): audit
        for audit in rerun_audits
    }

    final: list[dict[str, Any]] = []
    for audit in pass1_audits:
        agent = str(audit.get("agent", ""))
        spec = SPEC_BY_AGENT.get(agent)
        if spec is not None and spec.key in selected_keys:
            replacement = rerun_by_agent.get(agent)
            if replacement is None:
                raise RuntimeError(
                    f"Selective pass 2 expected rerun result for {spec.key!r}."
                )
            final.append(replacement)
        else:
            # Safe reuse: this auditor was clean or outside the Refiner's changed
            # territory. Its independent pass-1 result remains applicable.
            final.append(audit)

    return final


# ============================================================
# CLI / MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run domain-parallel multi-model verification over an immutable "
            "No Safe Circle reconciliation snapshot."
        )
    )
    parser.add_argument(
        "--run-id",
        help="Reconciliation run ID to verify. Defaults to outputs/LATEST.json.",
    )
    parser.add_argument(
        "--no-refine",
        action="store_true",
        help="Audit only; do not produce a refined candidate when errors are found.",
    )
    parser.add_argument(
        "--no-reverify",
        action="store_true",
        help="After refinement, do not run selective pass 2.",
    )
    parser.add_argument(
        "--full-pass2",
        action="store_true",
        help="After refinement, rerun every parallel auditor instead of selective pass 2.",
    )
    return parser.parse_args()


def main() -> int:
    paths: dict[str, Any] | None = None

    try:
        args = parse_args()

        source_run_id, source_candidate = base.resolve_source_snapshot(args.run_id)
        source_payload = base.load_json(source_candidate)
        paths = base.create_verification_paths(source_run_id)

        seed = secrets.randbits(64)
        rng = random.Random(seed)
        pass1_assignments = choose_models(rng)
        pass2_assignments = choose_models(rng)
        refiner_model = base.choose_refiner_model(rng, {})

        model_assignments = {
            "schema_version": "2.0-parallel",
            "random_seed": seed,
            "model_pool": base.MODEL_POOL,
            "parallel_max_workers": PARALLEL_MAX_WORKERS,
            "pass1": pass1_assignments,
            "refiner": refiner_model,
            "pass2": pass2_assignments,
            "recovery_policy": {
                "evidence_default_max_turns": EVIDENCE_MAX_TURNS,
                "max_turn_recovery_attempts": MAX_TURN_RECOVERY_ATTEMPTS,
                "recovery_turn_bonus": RECOVERY_TURN_BONUS,
                "successful_auditors_are_reused": True,
            },
            "note": (
                "Fifteen focused auditors are independently scoped and their findings "
                "are unioned, never voted. Pass 2 is selective unless --full-pass2 is used. "
                "A max-turn failure is retried without rerunning successful auditors."
            ),
        }
        base.save_new_json(paths["model_assignments"], model_assignments)

        print()
        print("=" * 72)
        print("NO SAFE CIRCLE -- PARALLEL RECONCILIATION VERIFICATION")
        print("=" * 72)
        print(f"Source reconciliation: {source_run_id}")
        print(f"Auditors: {len(SPECS)}")
        print(f"Parallel slots: {PARALLEL_MAX_WORKERS}")
        print(f"Model pool: {', '.join(base.MODEL_POOL)}")
        print(f"Random assignment seed: {seed}")
        print("Findings are unioned, not voted.")
        print("=" * 72)

        pass1_audits = run_specs(
            specs=SPECS,
            candidate_path=source_candidate,
            source_run_id=source_run_id,
            pass_label="pass1",
            output_dir=paths["pass1_dir"],
            assignments=pass1_assignments,
        )

        merged1 = base.merge_findings(pass1_audits)
        base.save_new_json(paths["merged_pass1"], merged1)

        refinement_performed = False
        final_candidate = source_candidate
        final_merged = merged1
        selected_pass2_keys: set[str] = set()

        if base.has_refiner_relevant_findings(merged1) and not args.no_refine:
            refinement_performed = True

            refiner_findings = base.build_refiner_findings(merged1)
            base.save_new_json(paths["refiner_findings"], refiner_findings)

            refiner = base.run_refiner(
                source_candidate=source_candidate,
                merged_findings_path=paths["refiner_findings"],
                source_run_id=source_run_id,
                model=refiner_model,
            )

            refined_payload = refiner["result"]
            base.save_new_json(paths["refined_raw"], refined_payload)

            removed = sanitize_forbidden_evidence(refined_payload)
            if removed:
                print(
                    "Warning: Refiner returned forbidden evidence that was removed: "
                    + ", ".join(removed)
                )

            removed_tracking = base.sanitize_refiner_input_tracking(refined_payload)
            if removed_tracking:
                print(
                    "Normalized Refiner bookkeeping paths from files_reviewed: "
                    + ", ".join(removed_tracking)
                )

            repair_missing_dependency_references(refined_payload)
            run_semantic_validation(refined_payload)

            base.save_new_json(paths["refined_json"], refined_payload)
            base.save_new_text(
                paths["refined_markdown"],
                render_markdown(refined_payload),
            )

            refined_delta = build_proposed_graph_delta(
                refined_payload,
                run_id=source_run_id,
                created_at_utc=paths["created_at_utc"],
            )
            refined_delta["verification_run_id"] = paths["verification_run_id"]
            refined_delta["source_reconciliation_run_id"] = source_run_id

            base.save_new_json(paths["refined_delta_json"], refined_delta)
            base.save_new_text(
                paths["refined_delta_markdown"],
                render_graph_delta_markdown(refined_delta),
            )

            final_candidate = paths["refined_json"]

            if not args.no_reverify:
                if args.full_pass2:
                    selected_pass2_keys = {spec.key for spec in SPECS}
                else:
                    selected_pass2_keys = changed_audit_keys(
                        source_payload,
                        refined_payload,
                    )
                    # Any auditor that found something in pass 1 gets another look,
                    # even when the field-diff router cannot prove the exact change.
                    selected_pass2_keys.update(
                        auditors_with_findings(pass1_audits)
                    )

                selected_specs = [
                    spec
                    for spec in SPECS
                    if spec.key in selected_pass2_keys
                ]

                print()
                print("=" * 72)
                print("SELECTIVE PASS 2")
                print("=" * 72)
                print(
                    f"Rerunning {len(selected_specs)} of {len(SPECS)} auditors."
                )
                if selected_specs:
                    print(
                        "Auditors: "
                        + ", ".join(spec.key for spec in selected_specs)
                    )
                print("=" * 72)

                if selected_specs:
                    pass2_audits = run_specs(
                        specs=selected_specs,
                        candidate_path=final_candidate,
                        source_run_id=source_run_id,
                        pass_label="pass2-selective",
                        output_dir=paths["pass2_dir"],
                        assignments=pass2_assignments,
                    )
                else:
                    paths["pass2_dir"].mkdir(parents=True, exist_ok=False)
                    pass2_audits = []

                final_audits = final_audit_set(
                    pass1_audits=pass1_audits,
                    rerun_audits=pass2_audits,
                    selected_keys=selected_pass2_keys,
                )

                final_merged = base.merge_findings(final_audits)
                final_merged["selective_pass2"] = {
                    "enabled": not args.full_pass2,
                    "rerun_auditor_count": len(selected_specs),
                    "total_auditor_count": len(SPECS),
                    "rerun_keys": sorted(selected_pass2_keys),
                    "reuse_policy": (
                        "Pass-1 results are reused only for auditors outside the "
                        "Refiner's changed territory that did not themselves report "
                        "a finding requiring recheck."
                    ),
                }
                base.save_new_json(paths["merged_pass2"], final_merged)

        status = base.status_from_pass2(final_merged)

        summary = {
            "schema_version": "2.0-parallel",
            "source_run_id": source_run_id,
            "verification_run_id": paths["verification_run_id"],
            "created_at_utc": paths["created_at_utc"],
            "status": status,
            "source_candidate": source_candidate.relative_to(base.ROOT).as_posix(),
            "final_candidate": final_candidate.relative_to(base.ROOT).as_posix(),
            "refinement_performed": refinement_performed,
            "parallel_auditor_count": len(SPECS),
            "parallel_max_workers": PARALLEL_MAX_WORKERS,
            "model_assignments": {
                "pass1": pass1_assignments,
                "refiner": refiner_model if refinement_performed else None,
                "pass2": (
                    {
                        key: pass2_assignments[key]
                        for key in sorted(selected_pass2_keys)
                    }
                    if refinement_performed
                    and not args.no_reverify
                    else None
                ),
            },
            "pass1": merged1,
            "final_pass": final_merged,
            "human_approval_required": True,
            "persistent_graph_mutated": False,
        }

        base.save_new_json(paths["summary_json"], summary)
        base.save_new_text(
            paths["summary_markdown"],
            base.render_verification_markdown(summary),
        )
        base.write_latest_verification_pointer(paths, status)

        if refinement_performed:
            current_delta_json = paths["refined_delta_json"]
            current_delta_markdown = paths["refined_delta_markdown"]
            current_candidate_markdown = paths["refined_markdown"]
        else:
            source_dir = base.RUNS_DIR / source_run_id
            current_delta_json = source_dir / "PROPOSED_GRAPH_DELTA.json"
            current_delta_markdown = source_dir / "PROPOSED_GRAPH_DELTA.md"
            current_candidate_markdown = source_dir / "RECONCILIATION.md"

        write_current_view(
            source_reconciliation_run_id=source_run_id,
            status=status,
            candidate_json=final_candidate,
            candidate_markdown=current_candidate_markdown,
            delta_json=current_delta_json,
            delta_markdown=current_delta_markdown,
            verification_run_id=paths["verification_run_id"],
            verification_summary_json=paths["summary_json"],
            verification_markdown=paths["summary_markdown"],
        )

        print()
        print("=" * 72)
        print("PARALLEL VERIFICATION COMPLETE")
        print("=" * 72)
        print(f"Status: {status}")
        print(f"Pass 1 auditors: {len(SPECS)}")
        print(
            f"Pass 1 material findings: "
            f"{merged1.get('material_finding_count', 0)}"
        )
        if refinement_performed and not args.no_reverify:
            print(
                f"Pass 2 auditors rerun: {len(selected_pass2_keys)} / {len(SPECS)}"
            )
        print(
            "Final material findings: "
            f"{final_merged.get('material_finding_count', 0)}"
        )
        print(f"Refinement performed: {refinement_performed}")
        print(f"Saved: {paths['summary_markdown'].relative_to(base.ROOT)}")
        print(f"Saved: {paths['summary_json'].relative_to(base.ROOT)}")
        if refinement_performed:
            print(
                f"Refined candidate: "
                f"{paths['refined_json'].relative_to(base.ROOT)}"
            )
            print("The original reconciliation snapshot was not modified.")
        print("Tasks/*.yaml was not modified.")
        print("=" * 72)
        return 0

    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("PARALLEL RECONCILIATION VERIFICATION FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        if paths is not None:
            print(
                "Verification directory preserved: "
                f"{paths['run_dir'].relative_to(base.ROOT)}",
                file=sys.stderr,
            )
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
