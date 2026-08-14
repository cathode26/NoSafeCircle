from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "GoalOrientedAgent"
PROMPT_ROOT = AGENT_ROOT / "prompts"
OUTPUT_ROOT = AGENT_ROOT / "outputs"

ANALYZE_PROMPT_PATH = PROMPT_ROOT / "analyze.md"
GOAL_ANALYSIS_PATH = OUTPUT_ROOT / "goal_analysis.json"

MODEL = os.environ.get("GOAL_AGENT_MODEL", "sonnet")
TIMEOUT_SECONDS = int(os.environ.get("GOAL_AGENT_TIMEOUT_SECONDS", "1800"))
MAX_TURNS = int(os.environ.get("GOAL_AGENT_MAX_TURNS", "40"))

# These repository areas are completely excluded from Assignment 5 gameplay
# analysis. The analysis Claude must never Read/Glob/Grep them, and this
# Python program must never save an analysis result that references them.
EXCLUDED_PATH_MARKERS = [
    "AgentCrew/",
    "AgentCrew\\",
    "DynamicContentPipeline/",
    "DynamicContentPipeline\\",
]


READINESS_ENUM = ["high", "medium", "low"]


CANDIDATE_GOAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "scope": {
            "type": "string",
            "enum": ["required", "stretch"],
        },
        "implementation_scope": {"type": "string"},
        "dependencies": {
            "type": "array",
            "items": {"type": "string"},
        },
        "prerequisites_ready": {"type": "boolean"},
        "resource_acquisition_readiness": {
            "type": "string",
            "enum": READINESS_ENUM,
        },
        "resource_acquisition_reasoning": {"type": "string"},
        "prototype_readiness": {
            "type": "string",
            "enum": READINESS_ENUM,
        },
        "integration_readiness": {
            "type": "string",
            "enum": READINESS_ENUM,
        },
        "systems_unlocked": {
            "type": "array",
            "items": {"type": "string"},
        },
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
        "systems_unlocked",
        "risk_and_size",
        "reasoning",
    ],
}


GOAL_ANALYSIS_SCHEMA: dict[str, Any] = {
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
        "gaps": {
            "type": "array",
            "items": {
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
            },
        },
        "non_code_requirements": {
            "type": "array",
            "items": {
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
            },
        },
        "candidate_goals": {
            "type": "array",
            "minItems": 3,
            "items": CANDIDATE_GOAL_SCHEMA,
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
        "dependencies": {
            "type": "array",
            "items": {"type": "string"},
        },
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
        },
        "rejected_high_priority_alternatives": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "reason_rejected": {"type": "string"},
                },
                "required": ["name", "reason_rejected"],
            },
        },
    },
    "required": [
        "desired_state",
        "current_state",
        "gaps",
        "non_code_requirements",
        "candidate_goals",
        "selected_goal",
        "selection_reason",
        "dependencies",
        "evidence",
        "rejected_high_priority_alternatives",
    ],
}


def load_prompt() -> str:
    if not ANALYZE_PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt not found: {ANALYZE_PROMPT_PATH}")

    return ANALYZE_PROMPT_PATH.read_text(encoding="utf-8-sig")


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def find_excluded_path_references(structured_output: dict[str, Any]) -> list[str]:
    """Defense-in-depth check: fail the run if the returned analysis
    references directories that are completely excluded from Assignment 5
    gameplay analysis (AgentCrew/ and DynamicContentPipeline/)."""

    serialized = json.dumps(structured_output, ensure_ascii=False)

    return [marker for marker in EXCLUDED_PATH_MARKERS if marker in serialized]


def run_analysis_agent() -> dict[str, Any]:
    prompt = load_prompt()

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
        "--input-format",
        "text",
    ]

    compact_schema = json.dumps(
        GOAL_ANALYSIS_SCHEMA,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    command.extend(["--json-schema", compact_schema])

    print()
    print("=" * 72)
    print("Starting agent: Goal-Oriented Analysis Agent")
    print(f"Model: {MODEL}")
    print("Tools: Read,Glob,Grep (read-only)")
    print("=" * 72)
    print("Claude may take several minutes to complete this stage.")

    started_timer = time.monotonic()

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
            f"Goal-Oriented Analysis Agent exceeded the {TIMEOUT_SECONDS}-second "
            "timeout."
        ) from exc

    duration = round(time.monotonic() - started_timer, 2)

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            "Goal-Oriented Analysis Agent failed with exit code "
            f"{process.returncode}.\n{error_text}"
        )

    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Goal-Oriented Analysis Agent returned output that was not valid "
            "Claude JSON."
        ) from exc

    print("Completed agent: Goal-Oriented Analysis Agent")
    print(f"Duration: {duration} seconds")

    structured_output = payload.get("structured_output")

    if not isinstance(structured_output, dict):
        raise RuntimeError(
            "Goal-Oriented Analysis Agent did not return structured_output."
        )

    return structured_output


def print_summary(structured_output: dict[str, Any]) -> None:
    gaps = structured_output.get("gaps", [])
    non_code_requirements = structured_output.get("non_code_requirements", [])
    candidate_goals = structured_output.get("candidate_goals", [])
    selected_goal = structured_output.get("selected_goal", {})
    rejected = structured_output.get("rejected_high_priority_alternatives", [])

    missing_or_partial = [
        gap for gap in gaps if gap.get("status") in ("missing", "partial")
    ]

    selected_candidate = None
    for candidate in candidate_goals:
        if candidate.get("name") == selected_goal.get("name"):
            selected_candidate = candidate
            break

    print()
    print("=" * 72)
    print("GOAL-ORIENTED ANALYSIS SUMMARY")
    print("=" * 72)

    print(f"Gameplay-code required features evaluated: {len(gaps)}")

    print()
    print("Missing or partial gameplay features:")
    if missing_or_partial:
        for gap in missing_or_partial:
            print(f"  - [{gap.get('status')}] {gap.get('feature')}")
    else:
        print("  (none)")

    print()
    print("Non-code requirements reported separately:")
    if non_code_requirements:
        for item in non_code_requirements:
            print(f"  - [{item.get('status')}] {item.get('feature')}")
    else:
        print("  (none)")

    print()
    print(f"Candidate goals considered: {len(candidate_goals)}")

    print()
    print(f"Selected goal: {selected_goal.get('name')}")
    print(f"Description: {selected_goal.get('description')}")

    print()
    print("Selection reason:")
    print(f"  {structured_output.get('selection_reason')}")

    print()
    print("Dependencies:")
    for dependency in structured_output.get("dependencies", []):
        print(f"  - {dependency}")

    if selected_candidate is not None:
        print()
        print(
            "Resource acquisition readiness: "
            f"{selected_candidate.get('resource_acquisition_readiness')}"
        )
        print(f"Prototype readiness: {selected_candidate.get('prototype_readiness')}")
        print(
            f"Integration readiness: {selected_candidate.get('integration_readiness')}"
        )

    print()
    print("Rejected high-priority alternatives:")
    for alternative in rejected:
        print(f"  - {alternative.get('name')}: {alternative.get('reason_rejected')}")

    print()
    print(f"Full analysis saved to: {GOAL_ANALYSIS_PATH.relative_to(ROOT)}")


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    try:
        structured_output = run_analysis_agent()
    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("GOAL-ORIENTED AGENT FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    excluded_hits = find_excluded_path_references(structured_output)

    if excluded_hits:
        print()
        print("=" * 72, file=sys.stderr)
        print("GOAL-ORIENTED AGENT FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(
            "Returned analysis references excluded repository paths: "
            f"{excluded_hits}. Refusing to save goal_analysis.json.",
            file=sys.stderr,
        )
        return 1

    save_json(GOAL_ANALYSIS_PATH, structured_output)

    print_summary(structured_output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
