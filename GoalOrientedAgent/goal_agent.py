from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GOAL_ROOT = ROOT / "GoalOrientedAgent"
PROMPT_PATH = GOAL_ROOT / "prompts" / "analyze.md"
OUTPUT_PATH = GOAL_ROOT / "outputs" / "goal_analysis.json"

MODEL = os.environ.get("GOAL_AGENT_MODEL", "sonnet")
TIMEOUT_SECONDS = int(os.environ.get("GOAL_AGENT_TIMEOUT_SECONDS", "1800"))
MAX_TURNS = int(os.environ.get("GOAL_AGENT_MAX_TURNS", "40"))


# ============================================================
# JSON SCHEMA
# ============================================================

READINESS_ENUM = {"type": "string", "enum": ["high", "medium", "low"]}

DEPENDENCY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "strength": {
            "type": "string",
            "enum": [
                "hard_prerequisite",
                "supporting_dependency",
                "shared_future_dependency",
            ],
        },
        "state": {
            "type": "string",
            "enum": [
                "ready_compatible",
                "present_incompatible",
                "missing_prerequisite",
                "created_in_goal",
                "acquired_in_goal",
            ],
        },
        "evidence": {"type": "string"},
        "reasoning": {"type": "string"},
        "required_gdd_work": {"type": "boolean"},
        "independently_testable": {"type": "boolean"},
        "should_promote_to_candidate": {"type": "boolean"},
        "promoted_candidate_name": {"type": "string"},
    },
    "required": [
        "name",
        "strength",
        "state",
        "evidence",
        "reasoning",
        "required_gdd_work",
        "independently_testable",
        "should_promote_to_candidate",
        "promoted_candidate_name",
    ],
}

GAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "feature": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["implemented", "partial", "missing"],
        },
        "evidence": {"type": "string"},
    },
    "required": ["feature", "status", "evidence"],
}

NON_CODE_REQUIREMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "feature": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["confirmed", "not_assessable_from_assets"],
        },
        "evidence": {"type": "string"},
    },
    "required": ["feature", "status", "evidence"],
}

FOUNDATION_GAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "desired_architecture": {"type": "string"},
        "current_state": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["compatible", "partial_mismatch", "incompatible", "missing"],
        },
        "evidence": {"type": "string"},
        "downstream_systems_affected": {
            "type": "array",
            "items": {"type": "string"},
        },
        "candidate_worthy": {"type": "boolean"},
        "promoted_candidate_name": {"type": "string"},
    },
    "required": [
        "name",
        "desired_architecture",
        "current_state",
        "status",
        "evidence",
        "downstream_systems_affected",
        "candidate_worthy",
        "promoted_candidate_name",
    ],
}

CANDIDATE_GOAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "scope": {"type": "string", "enum": ["required", "stretch"]},
        "implementation_scope": {"type": "string"},
        "dependencies": {"type": "array", "items": DEPENDENCY_SCHEMA},
        "prerequisites_ready": {"type": "boolean"},
        "resource_acquisition_readiness": READINESS_ENUM,
        "resource_acquisition_reasoning": {"type": "string"},
        "prototype_readiness": READINESS_ENUM,
        "integration_readiness": READINESS_ENUM,
        "foundation_compatibility": {
            "type": "string",
            "enum": ["compatible", "mixed", "incompatible"],
        },
        "foundation_reasoning": {"type": "string"},
        "expected_rework_risk": READINESS_ENUM,
        "implementation_risk": READINESS_ENUM,
        "unlock_value": READINESS_ENUM,
        "unlock_reasoning": {"type": "string"},
        "is_focused_slice": {"type": "boolean"},
        "decomposition_reasoning": {"type": "string"},
        "systems_unlocked": {"type": "array", "items": {"type": "string"}},
        "risk_and_size": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": [
        "name",
        "description",
        "scope",
        "implementation_scope",
        "dependencies",
        "prerequisites_ready",
        "resource_acquisition_readiness",
        "resource_acquisition_reasoning",
        "prototype_readiness",
        "integration_readiness",
        "foundation_compatibility",
        "foundation_reasoning",
        "expected_rework_risk",
        "implementation_risk",
        "unlock_value",
        "unlock_reasoning",
        "is_focused_slice",
        "decomposition_reasoning",
        "systems_unlocked",
        "risk_and_size",
        "reasoning",
    ],
}

COMPARISON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "alternative": {"type": "string"},
        "dimension": {
            "type": "string",
            "enum": [
                "prerequisites_ready",
                "resource_acquisition_readiness",
                "prototype_readiness",
                "integration_readiness",
                "foundation_compatibility",
                "expected_rework_risk",
                "implementation_risk",
                "unlock_value",
            ],
        },
        "winner_value": {"type": "string"},
        "alternative_value": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": [
        "alternative",
        "dimension",
        "winner_value",
        "alternative_value",
        "reasoning",
    ],
}

REJECTED_ALTERNATIVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "reason_rejected": {"type": "string"},
    },
    "required": ["name", "reason_rejected"],
}

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "desired_state": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "source": {"type": "string"},
                "required_features": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["source", "required_features"],
        },
        "current_state": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "source": {"type": "string"},
                "implemented_summary": {"type": "string"},
                "files_reviewed": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["source", "implemented_summary", "files_reviewed"],
        },
        "gaps": {"type": "array", "items": GAP_SCHEMA},
        "non_code_requirements": {
            "type": "array",
            "items": NON_CODE_REQUIREMENT_SCHEMA,
        },
        "foundation_gaps": {"type": "array", "items": FOUNDATION_GAP_SCHEMA},
        "candidate_goals": {
            "type": "array",
            "items": CANDIDATE_GOAL_SCHEMA,
            "minItems": 3,
        },
        "selected_goal": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name", "description"],
        },
        "selection_reason": {"type": "string"},
        "dependencies": {"type": "array", "items": DEPENDENCY_SCHEMA},
        "winner_tradeoffs": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "advantages": {"type": "array", "items": COMPARISON_SCHEMA},
                "disadvantages": {"type": "array", "items": COMPARISON_SCHEMA},
                "summary": {"type": "string"},
            },
            "required": ["advantages", "disadvantages", "summary"],
        },
        "evidence": {"type": "array", "items": {"type": "string"}},
        "rejected_high_priority_alternatives": {
            "type": "array",
            "items": REJECTED_ALTERNATIVE_SCHEMA,
            "minItems": 1,
        },
    },
    "required": [
        "desired_state",
        "current_state",
        "gaps",
        "non_code_requirements",
        "foundation_gaps",
        "candidate_goals",
        "selected_goal",
        "selection_reason",
        "dependencies",
        "winner_tradeoffs",
        "evidence",
        "rejected_high_priority_alternatives",
    ],
}


# ============================================================
# DEFENSIVE REPOSITORY-BOUNDARY VALIDATION
# ============================================================


def check_excluded_paths(structured_output: dict[str, Any]) -> None:
    files_reviewed = (
        structured_output.get("current_state", {}).get("files_reviewed", [])
    )

    forbidden_tokens = (
        "AgentCrew/",
        "AgentCrew\\",
        "DynamicContentPipeline/",
        "DynamicContentPipeline\\",
    )

    violations = [
        str(item)
        for item in files_reviewed
        if any(token in str(item) for token in forbidden_tokens)
    ]

    if violations:
        raise RuntimeError(
            "Analysis reports inspecting excluded repository paths in "
            f"current_state.files_reviewed: {violations}"
        )


# ============================================================
# SEMANTIC VALIDATION
# ============================================================

RANKS: dict[str, dict[str, int]] = {
    "prerequisites_ready": {"false": 0, "true": 1},
    "resource_acquisition_readiness": {"low": 0, "medium": 1, "high": 2},
    "prototype_readiness": {"low": 0, "medium": 1, "high": 2},
    "integration_readiness": {"low": 0, "medium": 1, "high": 2},
    "foundation_compatibility": {"incompatible": 0, "mixed": 1, "compatible": 2},
    "expected_rework_risk": {"high": 0, "medium": 1, "low": 2},
    "implementation_risk": {"high": 0, "medium": 1, "low": 2},
    "unlock_value": {"low": 0, "medium": 1, "high": 2},
}

BLOCKING_STATES = {"present_incompatible", "missing_prerequisite"}

DECOUPLING_KEYWORDS = (
    "decoupl",
    "disposable",
    "harness",
    "isolat",
    "test-only",
    "throwaway",
    "not depend",
    "does not depend",
    "independent of",
)


def _candidate_field_value(candidate: dict[str, Any], dimension: str) -> str:
    if dimension == "prerequisites_ready":
        return "true" if candidate.get("prerequisites_ready") else "false"
    return str(candidate.get(dimension))


def _validate_candidate_names_unique(candidates: list[dict[str, Any]]) -> None:
    names = [c.get("name") for c in candidates]
    if len(names) != len(set(names)):
        raise RuntimeError(
            "candidate_goals contains duplicate names: "
            f"{sorted(n for n in names if names.count(n) > 1)}"
        )


def _validate_selected_goal(
    structured_output: dict[str, Any],
    candidates_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selected_name = structured_output.get("selected_goal", {}).get("name")
    if selected_name not in candidates_by_name:
        raise RuntimeError(
            f"selected_goal.name {selected_name!r} does not exactly match any "
            "candidate_goals entry."
        )
    return candidates_by_name[selected_name]


def _validate_focused_slice(candidates: list[dict[str, Any]]) -> None:
    for candidate in candidates:
        if candidate.get("is_focused_slice") is not True:
            raise RuntimeError(
                f"Candidate {candidate.get('name')!r} has is_focused_slice != "
                "true. Every returned candidate must pass the self-"
                "decomposition check before being included."
            )


def _validate_dependency_object(
    dep: dict[str, Any],
    owner_name: str,
    candidate_names: set[str],
) -> bool:
    strength = dep.get("strength")
    state = dep.get("state")

    if state in ("created_in_goal", "acquired_in_goal") and strength == "hard_prerequisite":
        raise RuntimeError(
            f"Dependency {dep.get('name')!r} on {owner_name!r} is in state "
            f"{state!r} but has strength=hard_prerequisite. "
            "created_in_goal/acquired_in_goal must not be hard_prerequisite."
        )

    if dep.get("should_promote_to_candidate") is True:
        promoted = dep.get("promoted_candidate_name")
        if promoted not in candidate_names:
            raise RuntimeError(
                f"Dependency {dep.get('name')!r} on {owner_name!r} has "
                "should_promote_to_candidate=true but promoted_candidate_name "
                f"{promoted!r} does not match any candidate_goals name."
            )
    else:
        if dep.get("promoted_candidate_name") != "":
            raise RuntimeError(
                f"Dependency {dep.get('name')!r} on {owner_name!r} has "
                "should_promote_to_candidate=false but promoted_candidate_name "
                "is not an empty string."
            )

    is_blocking = strength == "hard_prerequisite" and state in BLOCKING_STATES

    if (
        is_blocking
        and dep.get("required_gdd_work") is True
        and dep.get("independently_testable") is True
        and dep.get("should_promote_to_candidate") is not True
    ):
        raise RuntimeError(
            f"Dependency {dep.get('name')!r} on {owner_name!r} is a blocking "
            "hard_prerequisite that is required_gdd_work and "
            "independently_testable, but should_promote_to_candidate is not "
            "true. Blocked substantial prerequisites must be promoted into "
            "candidate_goals."
        )

    return is_blocking


def _validate_candidate_dependencies_and_readiness(
    candidates: list[dict[str, Any]],
    candidate_names: set[str],
) -> None:
    for candidate in candidates:
        name = candidate.get("name", "<unnamed>")
        any_blocking = False
        for dep in candidate.get("dependencies", []):
            if _validate_dependency_object(dep, name, candidate_names):
                any_blocking = True

        expected_ready = not any_blocking
        if candidate.get("prerequisites_ready") is not expected_ready:
            raise RuntimeError(
                f"Candidate {name!r} has prerequisites_ready="
                f"{candidate.get('prerequisites_ready')!r}, but the structured "
                "dependencies imply prerequisites_ready="
                f"{expected_ready!r} (NOT any hard_prerequisite dependency in "
                "present_incompatible/missing_prerequisite state)."
            )


def _validate_foundation_gaps(
    foundation_gaps: list[dict[str, Any]],
    candidate_names: set[str],
) -> None:
    for gap in foundation_gaps:
        name = gap.get("name", "<unnamed>")
        if gap.get("candidate_worthy") is True:
            promoted = gap.get("promoted_candidate_name")
            if promoted not in candidate_names:
                raise RuntimeError(
                    f"foundation_gaps entry {name!r} has candidate_worthy=true "
                    f"but promoted_candidate_name {promoted!r} does not match "
                    "any candidate_goals name."
                )
        else:
            if gap.get("promoted_candidate_name") != "":
                raise RuntimeError(
                    f"foundation_gaps entry {name!r} has candidate_worthy=false "
                    "but promoted_candidate_name is not an empty string."
                )


def _validate_winner_tradeoffs(
    structured_output: dict[str, Any],
    candidates_by_name: dict[str, dict[str, Any]],
    winner: dict[str, Any],
) -> None:
    winner_name = winner.get("name")
    winner_tradeoffs = structured_output.get("winner_tradeoffs", {})

    def check_entries(entries: list[dict[str, Any]], expect_winner_ahead: bool) -> None:
        for entry in entries:
            alt_name = entry.get("alternative")
            if alt_name == winner_name or alt_name not in candidates_by_name:
                raise RuntimeError(
                    "winner_tradeoffs entry references alternative "
                    f"{alt_name!r}, which is not a distinct candidate_goals "
                    "entry."
                )
            alt = candidates_by_name[alt_name]
            dimension = entry.get("dimension")

            expected_winner_value = _candidate_field_value(winner, dimension)
            expected_alt_value = _candidate_field_value(alt, dimension)

            if str(entry.get("winner_value")) != expected_winner_value:
                raise RuntimeError(
                    "winner_tradeoffs entry winner_value "
                    f"{entry.get('winner_value')!r} does not match the "
                    f"winner candidate's {dimension} value "
                    f"{expected_winner_value!r}."
                )
            if str(entry.get("alternative_value")) != expected_alt_value:
                raise RuntimeError(
                    "winner_tradeoffs entry alternative_value "
                    f"{entry.get('alternative_value')!r} does not match "
                    f"{alt_name!r}'s {dimension} value {expected_alt_value!r}."
                )

            rank_map = RANKS[dimension]
            winner_rank = rank_map[expected_winner_value.lower()]
            alt_rank = rank_map[expected_alt_value.lower()]

            if expect_winner_ahead and winner_rank <= alt_rank:
                raise RuntimeError(
                    f"winner_tradeoffs.advantages entry for {alt_name!r} on "
                    f"{dimension} does not actually favor the winner "
                    f"({expected_winner_value!r} vs {expected_alt_value!r})."
                )
            if not expect_winner_ahead and alt_rank <= winner_rank:
                raise RuntimeError(
                    f"winner_tradeoffs.disadvantages entry for {alt_name!r} on "
                    f"{dimension} does not actually favor the alternative "
                    f"({expected_alt_value!r} vs {expected_winner_value!r})."
                )

    check_entries(winner_tradeoffs.get("advantages", []), expect_winner_ahead=True)
    check_entries(winner_tradeoffs.get("disadvantages", []), expect_winner_ahead=False)

    disadvantage_pairs = {
        (entry.get("alternative"), entry.get("dimension"))
        for entry in winner_tradeoffs.get("disadvantages", [])
    }

    for rejected in structured_output.get("rejected_high_priority_alternatives", []):
        alt_name = rejected.get("name")
        alt = candidates_by_name.get(alt_name)
        if alt is None:
            continue
        for dimension, rank_map in RANKS.items():
            winner_value = _candidate_field_value(winner, dimension)
            alt_value = _candidate_field_value(alt, dimension)
            if rank_map[alt_value.lower()] > rank_map[winner_value.lower()]:
                if (alt_name, dimension) not in disadvantage_pairs:
                    raise RuntimeError(
                        f"Rejected high-priority alternative {alt_name!r} "
                        f"outranks the winner on {dimension} "
                        f"({alt_value!r} vs {winner_value!r}) but this is not "
                        "recorded in winner_tradeoffs.disadvantages."
                    )


def _validate_incompatible_foundation_reasoning(candidates: list[dict[str, Any]]) -> None:
    for candidate in candidates:
        if (
            candidate.get("foundation_compatibility") == "incompatible"
            and candidate.get("prerequisites_ready") is True
        ):
            reasoning = str(candidate.get("foundation_reasoning", "")).lower()
            if not any(keyword in reasoning for keyword in DECOUPLING_KEYWORDS):
                raise RuntimeError(
                    f"Candidate {candidate.get('name')!r} has "
                    "foundation_compatibility=incompatible and "
                    "prerequisites_ready=true, but foundation_reasoning does "
                    "not explain why the incompatible foundation is only a "
                    "disposable test harness with decoupled core "
                    "implementation."
                )


def run_semantic_validation(structured_output: dict[str, Any]) -> dict[str, Any]:
    candidates = structured_output.get("candidate_goals", [])
    if not isinstance(candidates, list) or len(candidates) < 3:
        raise RuntimeError("candidate_goals must contain at least 3 entries.")

    _validate_candidate_names_unique(candidates)
    candidates_by_name = {c.get("name"): c for c in candidates}
    candidate_names = set(candidates_by_name)

    winner = _validate_selected_goal(structured_output, candidates_by_name)

    _validate_focused_slice(candidates)
    _validate_candidate_dependencies_and_readiness(candidates, candidate_names)
    _validate_foundation_gaps(
        structured_output.get("foundation_gaps", []), candidate_names
    )
    _validate_winner_tradeoffs(structured_output, candidates_by_name, winner)
    _validate_incompatible_foundation_reasoning(candidates)

    rejected = structured_output.get("rejected_high_priority_alternatives", [])
    if not isinstance(rejected, list) or len(rejected) < 1:
        raise RuntimeError(
            "rejected_high_priority_alternatives must contain at least 1 entry."
        )

    # The top-level `dependencies` field represents the selected goal's
    # dependencies. Derive it from the winning candidate so it is
    # mechanically guaranteed to match rather than trusting a duplicated
    # copy from the model.
    structured_output["dependencies"] = winner.get("dependencies", [])

    return winner


# ============================================================
# CLAUDE INVOCATION
# ============================================================


def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Analysis prompt not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8-sig")


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_analysis_agent() -> dict[str, Any]:
    prompt = load_prompt()

    compact_schema = json.dumps(
        ANALYSIS_SCHEMA,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    command = [
        "claude",
        "-p",
        "--model",
        MODEL,
        "--output-format",
        "json",
        "--no-session-persistence",
        "--max-turns",
        str(MAX_TURNS),
        "--permission-mode",
        "dontAsk",
        "--tools",
        "Read,Glob,Grep",
        "--allowedTools",
        "Read,Glob,Grep",
        "--disallowedTools",
        "Edit,Write,mcp__*",
        "--json-schema",
        compact_schema,
        "--input-format",
        "text",
    ]

    print()
    print("=" * 72)
    print("Starting agent: Goal-Oriented Analysis Agent")
    print(f"Model: {MODEL}")
    print("Tools: Read,Glob,Grep (read-only, no MCP)")
    print(f"Max turns: {MAX_TURNS}")
    print("=" * 72)
    print("Claude may take several minutes to analyze the GDD and Assets/.")

    started = time.monotonic()

    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Analysis agent exceeded the {TIMEOUT_SECONDS}-second timeout."
        ) from exc

    duration = round(time.monotonic() - started, 2)

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            f"Analysis agent failed with exit code {process.returncode}.\n"
            f"{error_text}"
        )

    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Analysis agent returned output that was not valid Claude JSON."
        ) from exc

    structured_output = payload.get("structured_output")
    if not isinstance(structured_output, dict):
        raise RuntimeError("Analysis agent did not return structured_output.")

    print(f"Completed analysis agent in {duration} seconds.")

    return structured_output


# ============================================================
# TERMINAL SUMMARY
# ============================================================


def print_summary(structured_output: dict[str, Any], winner: dict[str, Any]) -> None:
    gaps = structured_output.get("gaps", [])
    non_code = structured_output.get("non_code_requirements", [])
    candidates = structured_output.get("candidate_goals", [])
    selected = structured_output.get("selected_goal", {})
    foundation_gaps = structured_output.get("foundation_gaps", [])
    winner_tradeoffs = structured_output.get("winner_tradeoffs", {})
    rejected = structured_output.get("rejected_high_priority_alternatives", [])

    print()
    print("=" * 72)
    print("ASSIGNMENT 5 -- GOAL ANALYSIS SUMMARY")
    print("=" * 72)

    print(f"\nRequired gameplay-code features evaluated: {len(gaps)}")
    missing_or_partial = [
        g for g in gaps if g.get("status") in ("missing", "partial")
    ]
    print("Missing or partial gameplay features:")
    for gap in missing_or_partial:
        print(f"  - [{gap.get('status')}] {gap.get('feature')}: {gap.get('evidence')}")
    if not missing_or_partial:
        print("  (none)")

    print("\nNon-code requirements reported separately:")
    for item in non_code:
        print(f"  - [{item.get('status')}] {item.get('feature')}: {item.get('evidence')}")
    if not non_code:
        print("  (none)")

    print(f"\nCandidate goals considered: {len(candidates)}")
    for candidate in candidates:
        print(f"  - {candidate.get('name')} (scope={candidate.get('scope')})")

    print(f"\nSelected goal: {selected.get('name')}")
    print(f"Description: {selected.get('description')}")
    print(f"\nSelection reason:\n{structured_output.get('selection_reason')}")

    print("\nSelected goal dependencies:")
    for dep in structured_output.get("dependencies", []):
        print(
            f"  - [{dep.get('strength')}/{dep.get('state')}] {dep.get('name')}: "
            f"{dep.get('reasoning')}"
        )

    print(f"\nResource acquisition readiness: {winner.get('resource_acquisition_readiness')}")
    print(f"Resource acquisition reasoning: {winner.get('resource_acquisition_reasoning')}")
    print(f"Prototype readiness: {winner.get('prototype_readiness')}")
    print(f"Integration readiness: {winner.get('integration_readiness')}")
    print(f"Foundation compatibility: {winner.get('foundation_compatibility')}")
    print(f"Expected rework risk: {winner.get('expected_rework_risk')}")
    print(f"Implementation risk: {winner.get('implementation_risk')}")
    print(f"Unlock value: {winner.get('unlock_value')}")

    print("\nPromoted foundational prerequisites/candidates:")
    promoted_any = False
    for gap in foundation_gaps:
        if gap.get("candidate_worthy"):
            promoted_any = True
            print(f"  - foundation_gaps: {gap.get('name')} -> {gap.get('promoted_candidate_name')}")
    for candidate in candidates:
        for dep in candidate.get("dependencies", []):
            if dep.get("should_promote_to_candidate"):
                promoted_any = True
                print(
                    f"  - dependency: {dep.get('name')} (of {candidate.get('name')}) "
                    f"-> {dep.get('promoted_candidate_name')}"
                )
    if not promoted_any:
        print("  (none)")

    print("\nWinner advantages:")
    for entry in winner_tradeoffs.get("advantages", []):
        print(
            f"  - vs {entry.get('alternative')} on {entry.get('dimension')}: "
            f"{entry.get('winner_value')} > {entry.get('alternative_value')} "
            f"-- {entry.get('reasoning')}"
        )
    if not winner_tradeoffs.get("advantages"):
        print("  (none)")

    print("\nWinner disadvantages (acknowledged tradeoffs):")
    for entry in winner_tradeoffs.get("disadvantages", []):
        print(
            f"  - vs {entry.get('alternative')} on {entry.get('dimension')}: "
            f"{entry.get('winner_value')} < {entry.get('alternative_value')} "
            f"-- {entry.get('reasoning')}"
        )
    if not winner_tradeoffs.get("disadvantages"):
        print("  (none)")

    print(f"\nWinner tradeoffs summary:\n{winner_tradeoffs.get('summary')}")

    print("\nSemantic validation: PASSED")

    print("\nRejected high-priority alternatives:")
    for item in rejected:
        print(f"  - {item.get('name')}: {item.get('reason_rejected')}")

    print()
    print(f"Saved: {OUTPUT_PATH.relative_to(ROOT)}")
    print("=" * 72)


# ============================================================
# MAIN
# ============================================================


def main() -> int:
    try:
        structured_output = run_analysis_agent()

        check_excluded_paths(structured_output)

        winner = run_semantic_validation(structured_output)

        save_json(OUTPUT_PATH, structured_output)

        print_summary(structured_output, winner)

        return 0

    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("GOAL ANALYSIS AGENT FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
