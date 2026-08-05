from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import orchestrator as orch


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "AgentCrew" / "outputs"
AMENDMENT_PATH = (
    ROOT
    / "AgentCrew"
    / "inputs"
    / "approved_scope_amendment_controls_hud.md"
)
PLAYTEST_FEEDBACK_PATH = (
    ROOT / "AgentCrew" / "inputs" / "human_playtest_feedback.md"
)
CONTRACT_PATH = OUTPUT_ROOT / "feature_contract.json"
SUMMARY_PATH = OUTPUT_ROOT / "implementation_summary.md"
VALIDATION_PATH = OUTPUT_ROOT / "validation_report.json"
RUN_LOG_PATH = OUTPUT_ROOT / "crew_run_log.json"


def require_path(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"Required file was not found: {path}")


def load_existing_log() -> dict[str, Any]:
    if not RUN_LOG_PATH.exists():
        return {
            "game": "No Safe Circle",
            "feature": "Sealed Door Prototype",
            "orchestration": (
                "Four-agent pipeline followed by a targeted human-approved "
                "UI enhancement"
            ),
            "model": orch.MODEL,
            "status": "unknown",
            "agents": [],
        }

    value = json.loads(RUN_LOG_PATH.read_text(encoding="utf-8"))

    if not isinstance(value, dict):
        raise RuntimeError("Existing crew_run_log.json is not a JSON object.")

    value.setdefault("agents", [])
    return value


def run_targeted_ui_pass() -> None:
    require_path(AMENDMENT_PATH)
    require_path(CONTRACT_PATH)
    require_path(SUMMARY_PATH)

    existing_log = load_existing_log()
    orch.RUN_LOG.clear()
    orch.RUN_LOG.update(existing_log)
    orch.RUN_LOG["targeted_ui_status"] = "running"
    orch.RUN_LOG["targeted_ui_started_at_utc"] = orch.utc_now()
    orch.RUN_LOG["targeted_ui_scope_amendment"] = (
        "AgentCrew/inputs/approved_scope_amendment_controls_hud.md"
    )
    orch.save_run_log()

    feedback_instruction = ""
    if PLAYTEST_FEEDBACK_PATH.exists():
        feedback_instruction = """
Also read AgentCrew/inputs/human_playtest_feedback.md. Preserve or complete
the progress-indicator repair described there. Do not regress visible progress
updates while adding the controls HUD.
"""

    validation_passed = False

    for attempt in range(1, 3):
        if attempt == 1:
            extra = f"""
Read:
- AgentCrew/inputs/approved_scope_amendment_controls_hud.md
- AgentCrew/outputs/feature_contract.json
- AgentCrew/outputs/implementation_summary.md
{feedback_instruction}

This is a targeted, human-approved presentation enhancement. Do not rerun or
reinterpret the full feature plan.

Add a compact, always-visible controls HUD that communicates:
- WASD — Move
- Hold E — Open Door
- Moving or taking damage cancels the opening attempt

Inspect the actual input implementation before writing labels. Do not display
a debug-only damage key as a normal gameplay ability. If it is useful to show
the damage test binding, label it explicitly as Debug/Test and use the actual
implemented key.

The Editor scene builder must generate and wire the HUD every time it runs,
without duplication. Keep it separate from the interaction prompt and progress
indicator. Use only built-in Unity UI and existing project resources.

Preserve all working door behavior and tests. Add or update automated coverage
where practical. Update AgentCrew/outputs/implementation_summary.md with the
scope amendment, files changed, design decisions, and human retest steps.
"""
        else:
            extra = """
This is targeted UI repair pass 2.

Read:
- AgentCrew/inputs/approved_scope_amendment_controls_hud.md
- AgentCrew/outputs/validation_report.json
- AgentCrew/outputs/implementation_summary.md

Correct every blocking issue in the latest validation report. Preserve all
behavior that already passed and update the implementation summary.
"""

        orch.run_agent(
            role=(
                "Door and Interaction Agent — Controls HUD Enhancement"
                if attempt == 1
                else "Door and Interaction Agent — Controls HUD Repair Pass"
            ),
            prompt_filename="02_implementer.md",
            tools="Read,Glob,Grep,Edit,Write",
            permission_mode="acceptEdits",
            max_turns=30,
            extra_instructions=extra,
        )

        require_path(SUMMARY_PATH)

        validator_result = orch.run_agent(
            role=f"Unity Validation Agent — Controls HUD Review {attempt}",
            prompt_filename="03_validator.md",
            tools="Read,Glob,Grep",
            permission_mode="dontAsk",
            max_turns=20,
            schema=orch.VALIDATOR_SCHEMA,
            extra_instructions=f"""
Read:
- AgentCrew/inputs/approved_scope_amendment_controls_hud.md
- AgentCrew/outputs/implementation_summary.md
{feedback_instruction}

Perform a targeted static review of the controls HUD enhancement.

Confirm concrete evidence that:
1. The scene builder creates a readable controls panel every time it runs.
2. The displayed labels match the actual input implementation.
3. The panel includes WASD movement, Hold E to open, and the interruption rule.
4. Debug-only controls are omitted or clearly labeled as Debug/Test.
5. The HUD does not replace or obscure the interaction progress UI by design.
6. Repeated scene builds do not intentionally duplicate the HUD.
7. Existing five-second opening and cancellation behavior remain intact.
8. No external package, art, or unrelated mechanic was introduced.
9. Automated coverage was added or updated where practical.

Do not claim visual proof from static inspection. The human developer must
still rebuild the scene twice and verify layout and behavior in Play Mode.
""",
        )

        validation = validator_result.get("structured_output")
        if not isinstance(validation, dict):
            raise RuntimeError(
                "Validation agent did not return structured_output."
            )

        orch.save_json(VALIDATION_PATH, validation)

        if validation.get("status") == "pass":
            validation_passed = True
            break

        print()
        print("The HUD validator requested one repair pass.")

    if not validation_passed:
        orch.RUN_LOG["targeted_ui_status"] = "needs_changes"
        orch.RUN_LOG["targeted_ui_finished_at_utc"] = orch.utc_now()
        orch.save_run_log()
        raise RuntimeError(
            "The controls HUD still has blocking issues after two attempts."
        )

    orch.RUN_LOG["targeted_ui_status"] = "validation_passed"
    orch.RUN_LOG["targeted_ui_finished_at_utc"] = orch.utc_now()
    orch.save_run_log()

    print()
    print("=" * 72)
    print("TARGETED CONTROLS HUD ENHANCEMENT COMPLETED")
    print("=" * 72)
    print("Next human checks:")
    print("1. Open Unity and allow compilation.")
    print("2. Run No Safe Circle > Build Door Prototype Scene twice.")
    print("3. Confirm there is one controls panel, not duplicates.")
    print("4. Confirm labels match actual controls.")
    print("5. Verify the progress bar and door behavior still work.")
    print("6. Run all Play Mode tests.")


def main() -> int:
    try:
        run_targeted_ui_pass()
        return 0
    except Exception as exc:
        try:
            orch.RUN_LOG["targeted_ui_status"] = "failed"
            orch.RUN_LOG["targeted_ui_finished_at_utc"] = orch.utc_now()
            orch.RUN_LOG["targeted_ui_failure"] = str(exc)
            orch.save_run_log()
        except Exception:
            pass

        print()
        print("=" * 72, file=sys.stderr)
        print("TARGETED CONTROLS HUD PASS FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

