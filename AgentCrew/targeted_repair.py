from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import orchestrator as orch


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "AgentCrew" / "outputs"
FEEDBACK_PATH = ROOT / "AgentCrew" / "inputs" / "human_playtest_feedback.md"
CONTRACT_PATH = OUTPUT_ROOT / "feature_contract.json"
SUMMARY_PATH = OUTPUT_ROOT / "implementation_summary.md"
VALIDATION_PATH = OUTPUT_ROOT / "validation_report.json"
RUN_LOG_PATH = OUTPUT_ROOT / "crew_run_log.json"


def load_existing_log() -> dict[str, Any]:
    if not RUN_LOG_PATH.exists():
        return {
            "game": "No Safe Circle",
            "feature": "Sealed Door Prototype",
            "orchestration": (
                "Four-agent pipeline followed by a human-playtest repair loop"
            ),
            "model": orch.MODEL,
            "status": "unknown",
            "agents": [],
        }

    try:
        value = json.loads(RUN_LOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(
            f"Could not read existing run log: {RUN_LOG_PATH}"
        ) from exc

    if not isinstance(value, dict):
        raise RuntimeError("Existing crew_run_log.json is not a JSON object.")

    value.setdefault("agents", [])
    return value


def require_path(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"Required file was not found: {path}")


def save_latest_validation(value: dict[str, Any]) -> None:
    orch.save_json(VALIDATION_PATH, value)


def run_targeted_repair() -> None:
    require_path(FEEDBACK_PATH)
    require_path(CONTRACT_PATH)
    require_path(SUMMARY_PATH)

    existing_log = load_existing_log()
    orch.RUN_LOG.clear()
    orch.RUN_LOG.update(existing_log)
    orch.RUN_LOG["human_repair_status"] = "running"
    orch.RUN_LOG["human_repair_started_at_utc"] = orch.utc_now()
    orch.RUN_LOG["human_playtest_feedback_file"] = (
        "AgentCrew/inputs/human_playtest_feedback.md"
    )
    orch.save_run_log()

    validation_passed = False

    for attempt in range(1, 3):
        if attempt == 1:
            extra = """
Read AgentCrew/inputs/human_playtest_feedback.md before editing.

This is a targeted human-playtest repair. The door already opens after five
seconds, but the visible progress bar does not visually update.

Inspect the runtime UI binding, progress presentation component, and Editor
scene-builder configuration. Diagnose the actual cause instead of assuming it.

Repair the generated implementation so rebuilding the scene produces a
progress indicator that visibly fills from 0 to 1 during interaction and
resets after release, movement, or damage. Do not rely on a one-time manual
Inspector change.

Update AgentCrew/outputs/implementation_summary.md with:
- the human-reported defect,
- the diagnosed cause,
- files changed,
- automated coverage added or updated,
- exact human retest steps.

Do not change the approved gameplay scope.
"""
        else:
            extra = """
This is the second targeted repair attempt.

Read:
- AgentCrew/inputs/human_playtest_feedback.md
- AgentCrew/outputs/validation_report.json

Correct every blocking issue in the latest validation report while preserving
working door behavior. Update the implementation summary again.
"""

        orch.run_agent(
            role=(
                "Door and Interaction Agent — Human Playtest Repair"
                if attempt == 1
                else "Door and Interaction Agent — Human Repair Pass 2"
            ),
            prompt_filename="02_implementer.md",
            tools="Read,Glob,Grep,Edit,Write",
            permission_mode="acceptEdits",
            max_turns=30,
            extra_instructions=extra,
        )

        require_path(SUMMARY_PATH)

        validator_result = orch.run_agent(
            role=f"Unity Validation Agent — Human Repair Review {attempt}",
            prompt_filename="03_validator.md",
            tools="Read,Glob,Grep",
            permission_mode="dontAsk",
            max_turns=20,
            schema=orch.VALIDATOR_SCHEMA,
            extra_instructions="""
Also read AgentCrew/inputs/human_playtest_feedback.md.

This is a targeted review of a human-reported runtime UI defect. Confirm there
is concrete static evidence that:

1. The progress indicator is correctly configured by the scene builder every
   time the scene is rebuilt.
2. The runtime UI receives and displays normalized door progress continuously.
3. Release, movement, and damage reset both gameplay progress and the visible
   indicator.
4. The door still opens after five uninterrupted seconds.
5. Automated coverage was added or updated where practical.
6. The repair does not depend on a manual Inspector-only adjustment.

Do not claim Unity runtime proof. Static validation must be followed by the
documented human retest.
""",
        )

        validation = validator_result.get("structured_output")
        if not isinstance(validation, dict):
            raise RuntimeError(
                "Validation agent did not return structured_output."
            )

        save_latest_validation(validation)

        if validation.get("status") == "pass":
            validation_passed = True
            break

        print()
        print("The targeted validator requested another repair pass.")

    if not validation_passed:
        orch.RUN_LOG["human_repair_status"] = "needs_changes"
        orch.RUN_LOG["human_repair_finished_at_utc"] = orch.utc_now()
        orch.save_run_log()
        raise RuntimeError(
            "The targeted repair still has blocking issues after two attempts."
        )

    orch.RUN_LOG["human_repair_status"] = "validation_passed"
    orch.RUN_LOG["human_repair_finished_at_utc"] = orch.utc_now()
    orch.save_run_log()

    print()
    print("=" * 72)
    print("TARGETED REPAIR AND VALIDATION COMPLETED")
    print("=" * 72)
    print("Human feedback: AgentCrew/inputs/human_playtest_feedback.md")
    print("Latest validation: AgentCrew/outputs/validation_report.json")
    print()
    print("Next:")
    print("1. Return to Unity and allow scripts to compile.")
    print("2. Run No Safe Circle > Build Door Prototype Scene twice.")
    print("3. Retest visible fill, all cancellation paths, and door opening.")
    print("4. Run all generated Play Mode tests.")
    print("5. Do not mark the defect closed until the human retest passes.")


def main() -> int:
    try:
        run_targeted_repair()
        return 0
    except Exception as exc:
        try:
            orch.RUN_LOG["human_repair_status"] = "failed"
            orch.RUN_LOG["human_repair_finished_at_utc"] = orch.utc_now()
            orch.RUN_LOG["human_repair_failure"] = str(exc)
            orch.save_run_log()
        except Exception:
            pass

        print()
        print("=" * 72, file=sys.stderr)
        print("TARGETED REPAIR FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

