from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GOAL_ROOT = ROOT / "GoalOrientedAgent"
PROMPT_PATH = GOAL_ROOT / "prompts" / "implement.md"
ANALYSIS_PATH = GOAL_ROOT / "outputs" / "goal_analysis.json"
RESULT_PATH = GOAL_ROOT / "outputs" / "implementation_result.json"

MODEL = os.environ.get("GOAL_IMPLEMENTATION_MODEL", "sonnet")
TIMEOUT_SECONDS = int(os.environ.get("GOAL_IMPLEMENTATION_TIMEOUT_SECONDS", "1800"))
MAX_TURNS = int(os.environ.get("GOAL_IMPLEMENTATION_MAX_TURNS", "40"))

BASE_TOOLS = "Read,Glob,Grep,Edit,Write,Bash"
PIXELLAB_TOOL_GLOB = "mcp__pixellab__*"

# Files/directories that Step 2 must not alter.
PROTECTED_PATHS = [
    ROOT / "Docs" / "GDD" / "No_Safe_Circle_GDD.md",
    ROOT / "AgentCrew",
    ROOT / "DynamicContentPipeline",
    GOAL_ROOT / "goal_agent.py",
    GOAL_ROOT / "prompts" / "analyze.md",
    ANALYSIS_PATH,
]


VALIDATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["passed", "failed", "not_available", "not_run"],
        },
        "details": {"type": "string"},
    },
    "required": ["name", "status", "details"],
}


RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": ["implemented", "partial", "blocked"],
        },
        "selected_goal_name": {"type": "string"},
        "selected_goal_description": {"type": "string"},
        "implementation_summary": {"type": "string"},
        "files_created": {
            "type": "array",
            "items": {"type": "string"},
        },
        "files_modified": {
            "type": "array",
            "items": {"type": "string"},
        },
        "tests_added": {
            "type": "array",
            "items": {"type": "string"},
        },
        "validations": {
            "type": "array",
            "items": VALIDATION_SCHEMA,
        },
        "unity_run_status": {
            "type": "string",
            "enum": ["ran_passed", "ran_failed", "not_available", "not_run"],
        },
        "manual_unity_validation": {
            "type": "array",
            "items": {"type": "string"},
        },
        "requirements_satisfied": {
            "type": "array",
            "items": {"type": "string"},
        },
        "remaining_work": {
            "type": "array",
            "items": {"type": "string"},
        },
        "notes": {"type": "string"},
    },
    "required": [
        "status",
        "selected_goal_name",
        "selected_goal_description",
        "implementation_summary",
        "files_created",
        "files_modified",
        "tests_added",
        "validations",
        "unity_run_status",
        "manual_unity_validation",
        "requirements_satisfied",
        "remaining_work",
        "notes",
    ],
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object in {path}")
    return value


def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Implementation prompt not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8-sig")


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def find_selected_candidate(
    analysis: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected = analysis.get("selected_goal")
    candidates = analysis.get("candidate_goals")

    if not isinstance(selected, dict):
        raise RuntimeError("goal_analysis.json has no valid selected_goal.")
    if not isinstance(candidates, list):
        raise RuntimeError("goal_analysis.json has no valid candidate_goals array.")

    selected_name = selected.get("name")
    if not isinstance(selected_name, str) or not selected_name:
        raise RuntimeError("selected_goal.name is missing.")

    matches = [
        candidate
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("name") == selected_name
    ]

    if len(matches) != 1:
        raise RuntimeError(
            "selected_goal.name must match exactly one candidate_goals entry. "
            f"Found {len(matches)} matches for {selected_name!r}."
        )

    candidate = matches[0]

    if candidate.get("prerequisites_ready") is not True:
        raise RuntimeError(
            f"Selected goal {selected_name!r} is not prerequisite-ready. "
            "Step 2 refuses to re-select or silently absorb blockers. "
            "Resolve Phase 1 first."
        )

    if candidate.get("is_focused_slice") is False:
        raise RuntimeError(
            f"Selected goal {selected_name!r} is not a focused slice. "
            "Step 2 refuses to implement a knowingly bundled goal."
        )

    return selected, candidate


def candidate_needs_pixellab(candidate: dict[str, Any]) -> bool:
    for dep in candidate.get("dependencies", []):
        if not isinstance(dep, dict):
            continue
        if dep.get("state") != "acquired_in_goal":
            continue
        text = " ".join(
            str(dep.get(field, ""))
            for field in ("name", "evidence", "reasoning")
        ).lower()
        if "pixellab" in text:
            return True

    resource_reasoning = str(
        candidate.get("resource_acquisition_reasoning", "")
    ).lower()

    return (
        "pixellab" in resource_reasoning
        and "not relevant" not in resource_reasoning
        and "not required" not in resource_reasoning
    )


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def snapshot_path(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    if path.is_file():
        return {str(path.relative_to(ROOT)).replace("\\", "/"): hash_file(path)}

    snapshot: dict[str, str] = {}
    for child in sorted(path.rglob("*")):
        if child.is_file():
            rel = str(child.relative_to(ROOT)).replace("\\", "/")
            snapshot[rel] = hash_file(child)
    return snapshot


def snapshot_many(paths: list[Path]) -> dict[str, str]:
    combined: dict[str, str] = {}
    for path in paths:
        combined.update(snapshot_path(path))
    return combined


def compare_snapshots(
    before: dict[str, str], after: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    before_keys = set(before)
    after_keys = set(after)

    created = sorted(after_keys - before_keys)
    deleted = sorted(before_keys - after_keys)
    modified = sorted(
        key
        for key in before_keys & after_keys
        if before[key] != after[key]
    )

    return created, modified, deleted


def validate_protected_paths(
    before: dict[str, str], after: dict[str, str]
) -> None:
    created, modified, deleted = compare_snapshots(before, after)
    violations = created + modified + deleted

    if violations:
        raise RuntimeError(
            "Implementation agent changed protected Assignment 5/prior-work "
            "paths. The result was NOT saved. Violations: "
            + ", ".join(violations)
        )


def build_contract(
    analysis: dict[str, Any],
    selected: dict[str, Any],
    candidate: dict[str, Any],
) -> str:
    contract = {
        "selected_goal": selected,
        "selected_candidate": candidate,
        "selection_reason": analysis.get("selection_reason", ""),
        "top_level_dependencies": analysis.get("dependencies", []),
        "evidence": analysis.get("evidence", []),
    }

    return (
        "============================================================\n"
        "SELECTED GOAL CONTRACT â€” DO NOT RESELECT\n"
        "============================================================\n\n"
        + json.dumps(contract, indent=2, ensure_ascii=False)
        + "\n\n"
        "============================================================\n"
        "IMPLEMENTATION INSTRUCTIONS\n"
        "============================================================\n\n"
    )


def run_implementation_agent(
    analysis: dict[str, Any],
    selected: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    base_prompt = load_prompt()
    prompt = build_contract(analysis, selected, candidate) + base_prompt

    needs_pixellab = candidate_needs_pixellab(candidate)

    tools = BASE_TOOLS
    if needs_pixellab:
        tools = f"{BASE_TOOLS},{PIXELLAB_TOOL_GLOB}"

    compact_schema = json.dumps(
        RESULT_SCHEMA,
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
        tools,
        "--allowedTools",
        tools,
        "--json-schema",
        compact_schema,
        "--input-format",
        "text",
    ]

    print()
    print("=" * 72)
    print("Starting agent: Goal-Oriented Implementation Agent")
    print(f"Selected goal: {selected['name']}")
    print(f"Model: {MODEL}")
    print(f"Tools: {tools}")
    print(f"Max turns: {MAX_TURNS}")
    print(f"PixelLab enabled for this goal: {needs_pixellab}")
    print("=" * 72)
    print("Claude will implement the selected goal without re-selecting it.")

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
            "Implementation agent exceeded the "
            f"{TIMEOUT_SECONDS}-second timeout."
        ) from exc

    duration = round(time.monotonic() - started, 2)

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            "Implementation agent failed with exit code "
            f"{process.returncode}.\n{error_text}"
        )

    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Implementation agent returned output that was not valid Claude JSON."
        ) from exc

    structured_output = payload.get("structured_output")
    if not isinstance(structured_output, dict):
        raise RuntimeError(
            "Implementation agent did not return structured_output."
        )

    print(f"Completed implementation agent in {duration} seconds.")

    return structured_output


def validate_result(
    result: dict[str, Any],
    selected: dict[str, Any],
) -> None:
    if result.get("selected_goal_name") != selected.get("name"):
        raise RuntimeError(
            "Implementation result selected_goal_name does not match Phase 1 "
            "selected_goal.name. Step 2 is not allowed to re-select."
        )

    expected_description = selected.get("description")
    if result.get("selected_goal_description") != expected_description:
        raise RuntimeError(
            "Implementation result selected_goal_description does not exactly "
            "match Phase 1 selected_goal.description."
        )

    if result.get("status") == "implemented":
        total_changes = len(result.get("files_created", [])) + len(
            result.get("files_modified", [])
        )
        if total_changes == 0:
            raise RuntimeError(
                "Implementation agent claimed status='implemented' but reported "
                "no created or modified files."
            )


def print_summary(
    result: dict[str, Any],
    observed_created: list[str],
    observed_modified: list[str],
    observed_deleted: list[str],
) -> None:
    print()
    print("=" * 72)
    print("ASSIGNMENT 5 â€” IMPLEMENTATION SUMMARY")
    print("=" * 72)
    print(f"Status: {result['status']}")
    print(f"Selected goal: {result['selected_goal_name']}")
    print()
    print(result["implementation_summary"])

    print("\nClaude-reported files created:")
    for path in result["files_created"]:
        print(f"  - {path}")
    if not result["files_created"]:
        print("  (none)")

    print("\nClaude-reported files modified:")
    for path in result["files_modified"]:
        print(f"  - {path}")
    if not result["files_modified"]:
        print("  (none)")

    print("\nObserved Assets/ changes during this run:")
    for path in observed_created:
        print(f"  + {path}")
    for path in observed_modified:
        print(f"  ~ {path}")
    for path in observed_deleted:
        print(f"  - {path}")
    if not (observed_created or observed_modified or observed_deleted):
        print("  (none)")

    print("\nValidations:")
    for validation in result["validations"]:
        print(
            f"  - [{validation['status']}] {validation['name']}: "
            f"{validation['details']}"
        )

    print(f"\nUnity run status: {result['unity_run_status']}")
    if result["manual_unity_validation"]:
        print("Manual Unity validation:")
        for step in result["manual_unity_validation"]:
            print(f"  - {step}")

    print("\nRequirements satisfied:")
    for item in result["requirements_satisfied"]:
        print(f"  - {item}")

    if result["remaining_work"]:
        print("\nRemaining selected-goal work:")
        for item in result["remaining_work"]:
            print(f"  - {item}")

    print()
    print(f"Saved report: {RESULT_PATH.relative_to(ROOT)}")
    print("=" * 72)


def main() -> int:
    try:
        analysis = load_json(ANALYSIS_PATH)
        selected, candidate = find_selected_candidate(analysis)

        protected_before = snapshot_many(PROTECTED_PATHS)
        assets_before = snapshot_path(ROOT / "Assets")

        result = run_implementation_agent(
            analysis,
            selected,
            candidate,
        )

        protected_after = snapshot_many(PROTECTED_PATHS)
        assets_after = snapshot_path(ROOT / "Assets")

        validate_protected_paths(protected_before, protected_after)
        validate_result(result, selected)

        observed_created, observed_modified, observed_deleted = compare_snapshots(
            assets_before,
            assets_after,
        )

        # Add observed change information to notes without changing the schema.
        observed_note = (
            "Observed Assets/ delta during orchestrated run: "
            f"created={observed_created}; modified={observed_modified}; "
            f"deleted={observed_deleted}."
        )
        existing_notes = str(result.get("notes", "")).strip()
        result["notes"] = (
            f"{existing_notes}\n\n{observed_note}".strip()
            if existing_notes
            else observed_note
        )

        save_json(RESULT_PATH, result)
        print_summary(
            result,
            observed_created,
            observed_modified,
            observed_deleted,
        )

        return 0

    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("IMPLEMENTATION AGENT FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
