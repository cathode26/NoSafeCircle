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
OUTPUT_ROOT = GOAL_ROOT / "outputs"

ANALYSIS_PATH = OUTPUT_ROOT / "goal_analysis.json"
IMPLEMENTATION_RESULT_PATH = OUTPUT_ROOT / "implementation_result.json"
PROMPT_PATH = GOAL_ROOT / "prompts" / "reselect.md"
NEXT_SELECTION_PATH = OUTPUT_ROOT / "next_goal_selection.json"

MODEL = os.environ.get("GOAL_RESELECT_MODEL", "sonnet")
TIMEOUT_SECONDS = int(os.environ.get("GOAL_RESELECT_TIMEOUT_SECONDS", "300"))
MAX_TURNS = int(os.environ.get("GOAL_RESELECT_MAX_TURNS", "4"))


SELECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "selected_goal_name": {"type": "string"},
        "selected_goal_description": {"type": "string"},
        "selection_reason": {"type": "string"},
        "alternatives_considered": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "reason_not_selected": {"type": "string"},
                },
                "required": ["name", "reason_not_selected"],
            },
        },
    },
    "required": [
        "selected_goal_name",
        "selected_goal_description",
        "selection_reason",
        "alternatives_considered",
    ],
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object in {path}")
    return value


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def completed_goal_names() -> list[str]:
    if not IMPLEMENTATION_RESULT_PATH.exists():
        return []

    result = load_json(IMPLEMENTATION_RESULT_PATH)
    if result.get("status") != "implemented":
        return []

    name = result.get("selected_goal_name")
    if isinstance(name, str) and name.strip():
        return [name.strip()]

    return []


def eligible_candidates(
    analysis: dict[str, Any],
    completed: list[str],
) -> list[dict[str, Any]]:
    candidates = analysis.get("candidate_goals")
    if not isinstance(candidates, list):
        raise RuntimeError("goal_analysis.json has no valid candidate_goals array.")

    eligible: list[dict[str, Any]] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        name = candidate.get("name")
        if not isinstance(name, str) or not name:
            continue

        if name in completed:
            continue

        if candidate.get("prerequisites_ready") is not True:
            continue

        # Older saved analyses may not have this field. Only an explicit false
        # makes the candidate ineligible.
        if candidate.get("is_focused_slice") is False:
            continue

        eligible.append(candidate)

    if not eligible:
        raise RuntimeError(
            "No eligible candidate goals remain in the saved goal_analysis.json."
        )

    return eligible


def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Reselection prompt not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8-sig")


def build_prompt(
    analysis: dict[str, Any],
    completed: list[str],
    candidates: list[dict[str, Any]],
) -> str:
    base = load_prompt()

    saved_context = {
        "completed_goals": completed,
        "original_selected_goal": analysis.get("selected_goal"),
        "original_selection_reason": analysis.get("selection_reason"),
        "eligible_candidates": candidates,
        "rejected_high_priority_alternatives":
            analysis.get("rejected_high_priority_alternatives", []),
        "winner_tradeoffs": analysis.get("winner_tradeoffs"),
    }

    return (
        base
        + "\n\n"
        + "SAVED ASSIGNMENT 5 ARTIFACT — USE ONLY THIS DATA\n"
        + "================================================\n"
        + json.dumps(saved_context, indent=2, ensure_ascii=False)
    )


def run_selector(prompt: str) -> dict[str, Any]:
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
        "",
        "--json-schema",
        json.dumps(SELECTION_SCHEMA, separators=(",", ":"), ensure_ascii=False),
        "--input-format",
        "text",
    ]

    print()
    print("=" * 72)
    print("Assignment 5 — Reuse Saved Goal Analysis")
    print("=" * 72)
    print(f"Model: {MODEL}")
    print("Repository scan: DISABLED")
    print("GDD/Assets reread: DISABLED")
    print(f"Source: {ANALYSIS_PATH.relative_to(ROOT)}")
    print("=" * 72)

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
            f"Goal reselection exceeded the {TIMEOUT_SECONDS}-second timeout."
        ) from exc

    duration = round(time.monotonic() - started, 2)

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            f"Goal reselection failed with exit code {process.returncode}.\n"
            f"{error_text}"
        )

    try:
        wrapper = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Goal reselection returned output that was not valid Claude JSON.\n"
            f"{process.stdout[:2000]}"
        ) from exc

    structured = wrapper.get("structured_output")
    if not isinstance(structured, dict):
        raise RuntimeError("Goal reselection did not return structured_output.")

    print(f"Selection completed in {duration} seconds.")
    return structured


def validate_selection(
    selection: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    selected_name = selection.get("selected_goal_name")
    matches = [
        candidate
        for candidate in candidates
        if candidate.get("name") == selected_name
    ]

    if len(matches) != 1:
        allowed = [candidate.get("name") for candidate in candidates]
        raise RuntimeError(
            "Selector must choose exactly one eligible candidate from the saved "
            f"analysis. Chose {selected_name!r}; eligible={allowed!r}"
        )

    selected_candidate = matches[0]

    expected_description = selected_candidate.get("description")
    if selection.get("selected_goal_description") != expected_description:
        # The saved artifact is authoritative; do not permit paraphrasing to
        # silently change the contract.
        selection["selected_goal_description"] = expected_description

    return selected_candidate


def main() -> int:
    try:
        analysis = load_json(ANALYSIS_PATH)
        completed = completed_goal_names()
        candidates = eligible_candidates(analysis, completed)

        print(f"Completed goals excluded: {completed or '(none)'}")
        print("Eligible candidates:")
        for candidate in candidates:
            print(f"  - {candidate.get('name')}")

        prompt = build_prompt(analysis, completed, candidates)
        selection = run_selector(prompt)
        selected_candidate = validate_selection(selection, candidates)

        output = {
            "mode": "reuse_saved_goal_analysis",
            "source_analysis": str(ANALYSIS_PATH.relative_to(ROOT)).replace("\\", "/"),
            "source_implementation_result": (
                str(IMPLEMENTATION_RESULT_PATH.relative_to(ROOT)).replace("\\", "/")
                if IMPLEMENTATION_RESULT_PATH.exists()
                else None
            ),
            "fresh_repository_analysis_performed": False,
            "snapshot_warning": (
                "This selection reuses the saved Assignment 5 analysis. It does "
                "not rescan the current GDD or Assets/, so it is a continuation "
                "from that snapshot rather than a fresh current-state analysis."
            ),
            "completed_goals": completed,
            "eligible_goal_names": [
                candidate.get("name") for candidate in candidates
            ],
            "selected_goal": selected_candidate,
            "selection_reason": selection["selection_reason"],
            "alternatives_considered": selection["alternatives_considered"],
        }

        save_json(NEXT_SELECTION_PATH, output)

        print()
        print("=" * 72)
        print("NEXT GOAL SELECTED FROM SAVED ANALYSIS")
        print("=" * 72)
        print(f"Selected: {selected_candidate.get('name')}")
        print(selection["selection_reason"])
        print()
        print(
            "Saved: "
            f"{NEXT_SELECTION_PATH.relative_to(ROOT)}"
        )
        print("=" * 72)

        return 0

    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("GOAL RESELECTION FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
