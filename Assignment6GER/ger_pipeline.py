from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# REUSE FROM ASSIGNMENT 5:
# The existing goal-oriented implementation agent is our Generator and Refiner.
from GoalOrientedAgent import implementation_agent as assignment5_impl

# REUSE FROM ASSIGNMENT 3:
# The existing agent-runner and validator schema are reused for our Evaluator.
from AgentCrew import orchestrator as assignment3_crew

from circuit_breaker import CircuitBreaker


GER_ROOT = ROOT / "Assignment6GER"
OUTPUT_ROOT = GER_ROOT / "outputs"
PROMPT_ROOT = GER_ROOT / "prompts"

SELECTION_PATH = (
    ROOT / "GoalOrientedAgent" / "outputs" / "next_goal_selection.json"
)
RULE_PATH = GER_ROOT / "config" / "current_rule.json"
CONTRACT_PATH = OUTPUT_ROOT / "ger_contract.json"
LATEST_IMPLEMENTATION_PATH = OUTPUT_ROOT / "implementation_result.json"
FINAL_RESULT_PATH = OUTPUT_ROOT / "final_result.json"
EVALUATOR_LOG_PATH = OUTPUT_ROOT / "evaluator_agent_log.json"
RUNTIME_FEEDBACK_PREFIX = "runtime_feedback"

# Assignment 6 must not let a code-writing pass rewrite its own rules or
# previous-assignment infrastructure. Assets/ is the implementation workspace.
A6_PROTECTED_PATHS = [
    ROOT / "Docs" / "GDD" / "No_Safe_Circle_GDD.md",
    ROOT / "AgentCrew",
    ROOT / "DynamicContentPipeline",
    ROOT / "GoalOrientedAgent" / "goal_agent.py",
    ROOT / "GoalOrientedAgent" / "implementation_agent.py",
    ROOT / "GoalOrientedAgent" / "prompts",
    ROOT / "GoalOrientedAgent" / "outputs" / "goal_analysis.json",
    ROOT / "GoalOrientedAgent" / "outputs" / "next_goal_selection.json",
    GER_ROOT / "config",
    GER_ROOT / "prompts",
    GER_ROOT / "ger_pipeline.py",
    GER_ROOT / "circuit_breaker.py",
    GER_ROOT / "README.md",
    GER_ROOT / "Pre-Build_Declaration.txt",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def print_stage(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def validate_runtime_feedback(feedback: dict[str, Any]) -> None:
    if feedback.get("status") != "needs_changes":
        raise RuntimeError(
            "Runtime feedback must use status='needs_changes' to resume GER."
        )

    source = feedback.get("source")
    if not isinstance(source, str) or not source:
        raise RuntimeError("Runtime feedback requires a non-empty source.")

    summary = feedback.get("summary")
    if not isinstance(summary, str) or not summary:
        raise RuntimeError("Runtime feedback requires a non-empty summary.")

    issues = feedback.get("blocking_issues")
    if not isinstance(issues, list) or not issues:
        raise RuntimeError(
            "Runtime feedback requires at least one blocking_issues entry."
        )

    for index, issue in enumerate(issues, start=1):
        if not isinstance(issue, dict):
            raise RuntimeError(
                f"Runtime feedback issue #{index} must be an object."
            )
        if not isinstance(issue.get("issue"), str) or not issue["issue"]:
            raise RuntimeError(
                f"Runtime feedback issue #{index} has no issue text."
            )
        if (
            not isinstance(issue.get("required_fix"), str)
            or not issue["required_fix"]
        ):
            raise RuntimeError(
                f"Runtime feedback issue #{index} has no required_fix."
            )



def runtime_feedback_history_paths() -> list[Path]:
    pattern = re.compile(r"^runtime_feedback(\d{3})\.json$")
    matches: list[tuple[int, Path]] = []

    if not OUTPUT_ROOT.exists():
        return []

    for path in OUTPUT_ROOT.glob("runtime_feedback*.json"):
        match = pattern.match(path.name)
        if match:
            matches.append((int(match.group(1)), path))

    return [path for _, path in sorted(matches, key=lambda item: item[0])]


def persist_runtime_feedback_history(
    source_path: Path,
    feedback: dict[str, Any],
) -> Path:
    """
    Preserve every human Unity runtime-feedback artifact.

    If the caller already supplied Assignment6GER/outputs/runtime_feedbackNNN.json,
    use that immutable history file directly.

    Otherwise copy the supplied feedback into the next sequential history file:
    runtime_feedback000.json, runtime_feedback001.json, ...
    """

    try:
        resolved_source = source_path.resolve()
    except OSError:
        resolved_source = source_path

    history_pattern = re.compile(r"^runtime_feedback(\d{3})\.json$")

    if source_path.parent.resolve() == OUTPUT_ROOT.resolve():
        match = history_pattern.match(source_path.name)
        if match:
            # Never rewrite an existing numbered history artifact.
            existing = load_json(resolved_source)
            if existing != feedback:
                raise RuntimeError(
                    f"Versioned runtime feedback changed unexpectedly: {source_path}"
                )
            return resolved_source

    existing_history = runtime_feedback_history_paths()

    if existing_history:
        last_match = history_pattern.match(existing_history[-1].name)
        assert last_match is not None
        next_number = int(last_match.group(1)) + 1
    else:
        next_number = 0

    if next_number > 999:
        raise RuntimeError("Runtime feedback history exceeded 999 entries.")

    destination = OUTPUT_ROOT / f"{RUNTIME_FEEDBACK_PREFIX}{next_number:03d}.json"

    # Never overwrite history.
    if destination.exists():
        raise RuntimeError(
            f"Refusing to overwrite runtime feedback history: {destination}"
        )

    save_json(destination, feedback)
    return destination



def load_handoff() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    selection = load_json(SELECTION_PATH)
    rule = load_json(RULE_PATH)

    candidate = selection.get("selected_goal")
    if not isinstance(candidate, dict):
        raise RuntimeError(
            "next_goal_selection.json does not contain selected_goal."
        )

    selected_name = candidate.get("name")
    selected_description = candidate.get("description")

    if not isinstance(selected_name, str) or not selected_name:
        raise RuntimeError("Selected goal has no valid name.")
    if not isinstance(selected_description, str) or not selected_description:
        raise RuntimeError("Selected goal has no valid description.")

    if rule.get("selected_goal_name") != selected_name:
        raise RuntimeError(
            "Assignment 6 evaluator rule does not match Assignment 5's "
            "selected goal.\n"
            f"Assignment 5: {selected_name!r}\n"
            f"Assignment 6 rule: {rule.get('selected_goal_name')!r}\n"
            "Update Assignment6GER/config/current_rule.json deliberately "
            "before running a different selected goal."
        )

    if candidate.get("prerequisites_ready") is not True:
        raise RuntimeError(
            f"Assignment 5 selected goal {selected_name!r} is not "
            "prerequisite-ready."
        )

    selected = {
        "name": selected_name,
        "description": selected_description,
    }

    return selection, selected, candidate


def build_ger_contract(
    selection: dict[str, Any],
    selected: dict[str, Any],
    candidate: dict[str, Any],
    rule: dict[str, Any],
    runtime_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = {
        "game_name": "No Safe Circle",
        "source_assignment_5": (
            "GoalOrientedAgent/outputs/next_goal_selection.json"
        ),
        "selected_goal": selected,
        "selected_candidate": candidate,
        "selection_reason": selection.get("selection_reason", ""),
        "gdd_source": rule["gdd_source"],
        "gdd_section": rule["gdd_section"],
        "gdd_rule_id": rule["rule_id"],
        "gdd_rule": rule["rule_text"],
        "acceptance_criteria": rule["required_checks"],
        "failure_definition": rule["failure_definition"],
        "ger_mapping": {
            "generator": (
                "Assignment 5 Goal-Oriented Implementation Agent"
            ),
            "evaluator": (
                "Assignment 3 agent runner + Unity Validation Agent pattern"
            ),
            "refiner": (
                "Assignment 5 Goal-Oriented Implementation Agent, "
                "re-invoked with evaluator/runtime feedback"
            ),
            "circuit_breaker": (
                "Assignment 6 bounded retry/escalation logic"
            ),
        },
    }

    if runtime_feedback is not None:
        contract["runtime_feedback"] = runtime_feedback
        contract["runtime_feedback_policy"] = (
            "Human Unity runtime feedback is an approved integration constraint "
            "for refining the already-selected goal. It may clarify how the "
            "selected feature must behave in the real game, but it does not "
            "authorize unrelated scope expansion or a new goal."
        )

    return contract


def build_assignment5_analysis_context(
    selection: dict[str, Any],
    candidate: dict[str, Any],
    evaluator_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence: list[Any] = []

    original_evidence = candidate.get("evidence")
    if isinstance(original_evidence, list):
        evidence.extend(original_evidence)

    if evaluator_feedback is not None:
        evidence.append(
            {
                "assignment6_ger_refinement": True,
                "instruction": (
                    "This is a REFINE pass, not a new goal. Correct every "
                    "blocking issue reported by the Assignment 6 evaluation "
                    "feedback. Preserve behavior that already passed, remain "
                    "inside the exact selected-goal scope, then revalidate and "
                    "report. Human Unity runtime feedback is authoritative "
                    "integration evidence for this repair pass."
                ),
                "evaluator_feedback": evaluator_feedback,
            }
        )

    return {
        "selection_reason": selection.get("selection_reason", ""),
        "dependencies": candidate.get("dependencies", []),
        "evidence": evidence,
    }


def candidate_for_pass(
    base_candidate: dict[str, Any],
    evaluator_feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    candidate = copy.deepcopy(base_candidate)

    if evaluator_feedback is not None:
        candidate["assignment6_ger_mode"] = "refine"
        candidate["assignment6_refinement_instruction"] = (
            "Repair the current implementation using the evaluation feedback "
            "below. Do not start over, re-select, or broaden scope. Treat "
            "human Unity runtime observations as real evidence."
        )
        candidate["assignment6_evaluator_feedback"] = evaluator_feedback

    return candidate


def validate_assignment6_result_identity(
    result: dict[str, Any],
    selected: dict[str, Any],
) -> None:
    """
    Validate the parts of the Assignment 5 result contract that must still hold
    during Assignment 6 refinement.

    Assignment 5's validate_result() also requires an "implemented" response to
    report at least one created/modified file. That rule is appropriate for the
    original one-shot implementation phase, but it is too strict for GER:
    a Refiner may incorrectly make no changes, and that should become an
    evaluator failure / Circuit Breaker event rather than crashing the pipeline.
    """
    if result.get("selected_goal_name") != selected.get("name"):
        raise RuntimeError(
            "Implementation result selected_goal_name does not match the "
            "Assignment 5 selected goal. Refinement is not allowed to re-select."
        )

    expected_description = selected.get("description")
    if result.get("selected_goal_description") != expected_description:
        raise RuntimeError(
            "Implementation result selected_goal_description does not exactly "
            "match the Assignment 5 selected goal description."
        )

    if result.get("status") not in {"implemented", "blocked"}:
        raise RuntimeError(
            f"Unexpected implementation status: {result.get('status')!r}"
        )


def run_generator_or_refiner(
    *,
    pass_number: int,
    selection: dict[str, Any],
    selected: dict[str, Any],
    base_candidate: dict[str, Any],
    evaluator_feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    role = "GENERATOR" if evaluator_feedback is None else "REFINER"
    print_stage(f"{role} — IMPLEMENTATION PASS {pass_number}")
    print(
        "Reusing Assignment 5 GoalOrientedAgent/implementation_agent.py"
    )

    protected_before = assignment5_impl.snapshot_many(A6_PROTECTED_PATHS)
    assets_before = assignment5_impl.snapshot_path(ROOT / "Assets")

    analysis_context = build_assignment5_analysis_context(
        selection,
        base_candidate,
        evaluator_feedback,
    )
    pass_candidate = candidate_for_pass(
        base_candidate,
        evaluator_feedback,
    )

    result = assignment5_impl.run_implementation_agent(
        analysis_context,
        selected,
        pass_candidate,
    )

    protected_after = assignment5_impl.snapshot_many(A6_PROTECTED_PATHS)
    assets_after = assignment5_impl.snapshot_path(ROOT / "Assets")

    assignment5_impl.validate_protected_paths(
        protected_before,
        protected_after,
    )

    created, modified, deleted = assignment5_impl.compare_snapshots(
        assets_before,
        assets_after,
    )

    if role == "GENERATOR":
        # Preserve Assignment 5's original strict implementation contract for
        # the first generation pass.
        assignment5_impl.validate_result(result, selected)
    else:
        # During refinement, a no-op is not a Python/orchestration crash. It is
        # a failed repair attempt that GER must evaluate and count toward the
        # Circuit Breaker.
        validate_assignment6_result_identity(result, selected)

    result = copy.deepcopy(result)
    result["assignment6_ger_role"] = role.lower()
    result["assignment6_pass_number"] = pass_number
    result["observed_assets_delta"] = {
        "created": created,
        "modified": modified,
        "deleted": deleted,
    }
    result["assignment6_refinement_noop"] = (
        role == "REFINER"
        and not created
        and not modified
        and not deleted
    )

    if result["assignment6_refinement_noop"]:
        print(
            "WARNING: Refiner made no observed Assets/ changes. "
            "GER will treat this as a failed repair attempt instead of crashing."
        )

    save_json(
        OUTPUT_ROOT / f"implementation_pass_{pass_number}.json",
        result,
    )
    save_json(LATEST_IMPLEMENTATION_PATH, result)

    print(f"Implementation status: {result['status']}")
    print("Observed Assets/ delta:")
    print(f"  created: {created}")
    print(f"  modified: {modified}")
    print(f"  deleted: {deleted}")

    return result


def _configure_assignment3_runner_for_assignment6() -> dict[str, Any]:
    """Temporarily redirect Assignment 3's reusable runner to A6 resources."""

    old = {
        "PROMPT_ROOT": assignment3_crew.PROMPT_ROOT,
        "RUN_LOG_PATH": assignment3_crew.RUN_LOG_PATH,
        "RUN_LOG": assignment3_crew.RUN_LOG,
    }

    assignment3_crew.PROMPT_ROOT = PROMPT_ROOT
    assignment3_crew.RUN_LOG_PATH = EVALUATOR_LOG_PATH
    assignment3_crew.RUN_LOG = {
        "game": "No Safe Circle",
        "feature": "Assignment 6 GER Evaluator",
        "orchestration": (
            "Assignment 3 run_agent reused as Assignment 6 Evaluator"
        ),
        "model": assignment3_crew.MODEL,
        "started_at_utc": utc_now(),
        "finished_at_utc": None,
        "status": "running",
        "agents": [],
    }

    return old


def _restore_assignment3_runner(old: dict[str, Any]) -> None:
    assignment3_crew.PROMPT_ROOT = old["PROMPT_ROOT"]
    assignment3_crew.RUN_LOG_PATH = old["RUN_LOG_PATH"]
    assignment3_crew.RUN_LOG = old["RUN_LOG"]


def evaluator_log_history_path(pass_number: int) -> Path:
    return OUTPUT_ROOT / f"evaluator_agent_log_pass_{pass_number}.json"


def normalize_evaluation(
    validation: dict[str, Any],
    rule: dict[str, Any],
) -> dict[str, Any]:
    """Make the static evaluator mechanically accountable to every GDD check."""

    result = copy.deepcopy(validation)
    expected = {
        item["id"]: item
        for item in rule["required_checks"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    actual_list = result.get("criteria_results")
    if not isinstance(actual_list, list):
        actual_list = []
        result["criteria_results"] = actual_list

    actual = {
        item.get("id"): item
        for item in actual_list
        if isinstance(item, dict)
    }

    missing = [criterion_id for criterion_id in expected if criterion_id not in actual]

    for criterion_id in missing:
        requirement = expected[criterion_id]["requirement"]
        actual_list.append(
            {
                "id": criterion_id,
                "status": "fail",
                "evidence": (
                    "Evaluator omitted this required GDD-specific check: "
                    + requirement
                ),
            }
        )
        result.setdefault("blocking_issues", []).append(
            {
                "file": "Assignment6GER/outputs/ger_contract.json",
                "issue": (
                    f"Required evaluator criterion {criterion_id!r} "
                    "was not evaluated."
                ),
                "required_fix": (
                    "Evaluate the implementation explicitly against: "
                    + requirement
                ),
            }
        )

    any_failed = any(
        item.get("status") != "pass"
        for item in actual_list
        if item.get("id") in expected
    )

    if any_failed or result.get("blocking_issues"):
        result["status"] = "needs_changes"
    else:
        result["status"] = "pass"

    return result


def run_evaluator(
    *,
    pass_number: int,
    rule: dict[str, Any],
) -> dict[str, Any]:
    print_stage(f"EVALUATOR — PASS {pass_number}")
    print(
        "Reusing Assignment 3 AgentCrew/orchestrator.py run_agent() "
        "and VALIDATOR_SCHEMA"
    )

    old_globals = _configure_assignment3_runner_for_assignment6()

    try:
        evaluator_result = assignment3_crew.run_agent(
            role=f"Assignment 6 Unity Validation Agent — Pass {pass_number}",
            prompt_filename="evaluator.md",
            tools="Read,Glob,Grep",
            permission_mode="dontAsk",
            max_turns=20,
            schema=assignment3_crew.VALIDATOR_SCHEMA,
            extra_instructions=(
                f"This is GER evaluation pass {pass_number}. "
                "Use Assignment6GER/outputs/ger_contract.json as the "
                "approved contract and enforce its specific GDD rule. "
                "If that contract contains runtime_feedback, verify that the "
                "refined camera implementation addresses the human-observed "
                "integration failures without violating the canonical GDD. "
                "Do not use Assignment 3's old sealed-door contract."
            ),
        )
    finally:
        _restore_assignment3_runner(old_globals)

    validation = evaluator_result.get("structured_output")
    if not isinstance(validation, dict):
        raise RuntimeError(
            "Assignment 3 evaluator runner did not return structured_output."
        )

    validation = normalize_evaluation(validation, rule)

    # Preserve the Assignment 3 runner log for every evaluator pass instead of
    # keeping only the latest evaluator_agent_log.json.
    if EVALUATOR_LOG_PATH.exists():
        shutil.copy2(
            EVALUATOR_LOG_PATH,
            evaluator_log_history_path(pass_number),
        )

    save_json(
        OUTPUT_ROOT / f"evaluation_pass_{pass_number}.json",
        validation,
    )

    print(f"Evaluator status: {validation['status']}")
    print(validation["summary"])

    return validation


def enforce_refinement_progress(
    evaluation: dict[str, Any],
    implementation: dict[str, Any],
    feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    A refinement triggered by a concrete failed evaluation/runtime observation
    cannot be considered repaired when the Refiner changed nothing in Assets/.

    The independent static evaluator still runs, and its raw agent log is
    preserved. This guardrail normalizes the pipeline decision afterward so a
    no-op consumes a refinement attempt and can eventually trip the Circuit
    Breaker rather than aborting the program or falsely passing.
    """
    if feedback is None:
        return evaluation

    if implementation.get("assignment6_refinement_noop") is not True:
        return evaluation

    result = copy.deepcopy(evaluation)
    result["status"] = "needs_changes"

    blocking = result.setdefault("blocking_issues", [])
    blocking.append(
        {
            "file": (
                "Assignment6GER/outputs/"
                f"implementation_pass_{implementation.get('assignment6_pass_number')}.json"
            ),
            "issue": (
                "The Refiner made no observed changes under Assets/ even though "
                "this pass was triggered by unresolved evaluation/runtime feedback."
            ),
            "required_fix": (
                "Make a concrete implementation or test change that addresses the "
                "blocking feedback, or return status='blocked' if the selected goal "
                "cannot be repaired within scope."
            ),
        }
    )

    original_summary = str(result.get("summary", "")).strip()
    guard_summary = (
        "GER refinement-progress guard failed: the Refiner made no observed "
        "Assets/ changes in response to unresolved feedback."
    )
    result["summary"] = (
        f"{guard_summary} Static evaluator summary: {original_summary}"
        if original_summary
        else guard_summary
    )
    result["assignment6_pipeline_guardrail"] = {
        "name": "refinement_must_make_progress",
        "status": "fail",
        "reason": (
            "A no-op refinement cannot resolve a human/runtime or evaluator "
            "failure that existed before the pass."
        ),
    }

    return result


def save_final(
    *,
    status: str,
    selected: dict[str, Any],
    rule: dict[str, Any],
    breaker: CircuitBreaker,
    pass_number: int,
    implementation: dict[str, Any],
    evaluation: dict[str, Any] | None,
    reason: str,
    runtime_feedback: dict[str, Any] | None = None,
) -> None:
    payload = {
        "game": "No Safe Circle",
        "selected_goal": selected,
        "gdd_rule_id": rule["rule_id"],
        "status": status,
        "reason": reason,
        "implementation_passes": pass_number,
        "refinements_used": breaker.refinements_used,
        "circuit_breaker": breaker.status(),
        "latest_implementation": implementation,
        "latest_evaluation": evaluation,
        "completed_at_utc": utc_now(),
    }

    if runtime_feedback is not None:
        payload["runtime_feedback_used"] = runtime_feedback
        history = runtime_feedback_history_paths()
        if history:
            payload["runtime_feedback_history"] = [
                str(path.relative_to(ROOT)).replace("\\", "/")
                for path in history
            ]

    final_history = final_result_history_paths()
    if final_history:
        payload["final_result_history"] = [
            str(path.relative_to(ROOT)).replace("\\", "/")
            for path in final_history
        ]

    evaluator_history = sorted(OUTPUT_ROOT.glob("evaluator_agent_log_pass_*.json"))
    if evaluator_history:
        payload["evaluator_log_history"] = [
            str(path.relative_to(ROOT)).replace("\\", "/")
            for path in evaluator_history
        ]

    save_json(FINAL_RESULT_PATH, payload)


def existing_pass_numbers() -> list[int]:
    numbers: list[int] = []
    pattern = re.compile(r"implementation_pass_(\d+)\.json$")

    if not OUTPUT_ROOT.exists():
        return numbers

    for path in OUTPUT_ROOT.glob("implementation_pass_*.json"):
        match = pattern.match(path.name)
        if match:
            numbers.append(int(match.group(1)))

    return sorted(set(numbers))


def previous_refinement_count() -> int:
    if not FINAL_RESULT_PATH.exists():
        return 0

    try:
        previous = load_json(FINAL_RESULT_PATH)
    except Exception:
        return 0

    value = previous.get("refinements_used", 0)
    return value if isinstance(value, int) and value >= 0 else 0


def final_result_history_paths() -> list[Path]:
    pattern = re.compile(r"^final_result_pass_(\d{3})\.json$")
    matches: list[tuple[int, Path]] = []

    if not OUTPUT_ROOT.exists():
        return []

    for path in OUTPUT_ROOT.glob("final_result_pass_*.json"):
        match = pattern.match(path.name)
        if match:
            matches.append((int(match.group(1)), path))

    return [path for _, path in sorted(matches, key=lambda item: item[0])]


def archive_previous_final_before_runtime_resume() -> Path | None:
    """
    Preserve the current final_result.json before a runtime-feedback resume.

    Every archived result is immutable and numbered:
    final_result_pass_001.json, final_result_pass_002.json, ...
    """
    if not FINAL_RESULT_PATH.exists():
        return None

    current = load_json(FINAL_RESULT_PATH)

    # Prefer the implementation-pass number recorded by the final result so the
    # archive lines up with implementation_pass_N/evaluation_pass_N history.
    pass_number = current.get("implementation_passes")
    if not isinstance(pass_number, int) or pass_number < 1:
        existing = final_result_history_paths()
        if existing:
            match = re.match(r"^final_result_pass_(\d{3})\.json$", existing[-1].name)
            assert match is not None
            pass_number = int(match.group(1)) + 1
        else:
            pass_number = 1

    archive = OUTPUT_ROOT / f"final_result_pass_{pass_number:03d}.json"

    if archive.exists():
        existing = load_json(archive)
        if existing != current:
            raise RuntimeError(
                f"Refusing to overwrite final-result history: {archive}"
            )
        return archive

    shutil.copy2(FINAL_RESULT_PATH, archive)
    return archive


def run_pipeline(
    max_refinements: int,
    runtime_feedback_path: Path | None,
) -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    selection, selected, base_candidate = load_handoff()
    rule = load_json(RULE_PATH)

    runtime_feedback: dict[str, Any] | None = None
    feedback: dict[str, Any] | None = None

    existing_passes = existing_pass_numbers()
    pass_number = 1
    initial_refinements = 0

    if runtime_feedback_path is not None:
        runtime_feedback = load_json(runtime_feedback_path)
        validate_runtime_feedback(runtime_feedback)

        if not existing_passes:
            raise RuntimeError(
                "Runtime-feedback resume requires an existing GER "
                "implementation pass. Run the normal GER pipeline first."
            )

        archived_final = archive_previous_final_before_runtime_resume()
        if archived_final is not None:
            print(
                "Archived previous final result: "
                f"{archived_final.relative_to(ROOT)}"
            )

        history_path = persist_runtime_feedback_history(
            runtime_feedback_path,
            runtime_feedback,
        )
        print(
            "Saved runtime feedback history: "
            f"{history_path.relative_to(ROOT)}"
        )

        pass_number = max(existing_passes) + 1
        initial_refinements = previous_refinement_count()
        feedback = runtime_feedback

    contract = build_ger_contract(
        selection,
        selected,
        base_candidate,
        rule,
        runtime_feedback,
    )
    save_json(CONTRACT_PATH, contract)

    print_stage("ASSIGNMENT 6 — GER PIPELINE")
    print(f"Selected by Assignment 5: {selected['name']}")
    print(
        "Generator/Refiner: Assignment 5 Goal-Oriented Implementation Agent"
    )
    print(
        "Evaluator: Assignment 3 agent runner + validation pattern"
    )
    print(f"Circuit breaker: {max_refinements} refinements maximum")
    print(f"GDD rule: {rule['rule_id']}")

    breaker = CircuitBreaker(
        max_refinements=max_refinements,
        refinements_used=initial_refinements,
    )

    if runtime_feedback is not None:
        print("Mode: RESUME FROM HUMAN UNITY RUNTIME FEEDBACK")
        print(f"Runtime feedback source: {runtime_feedback['source']}")
        print(f"Next implementation pass: {pass_number}")

        if not breaker.can_refine():
            placeholder = load_json(
                OUTPUT_ROOT / f"implementation_pass_{max(existing_passes)}.json"
            )
            save_final(
                status="human_review_required",
                selected=selected,
                rule=rule,
                breaker=breaker,
                pass_number=max(existing_passes),
                implementation=placeholder,
                evaluation=runtime_feedback,
                reason=(
                    "Runtime feedback requires another repair, but the "
                    "Circuit Breaker has no refinement attempts remaining."
                ),
                runtime_feedback=runtime_feedback,
            )
            print_stage("CIRCUIT BREAKER — HUMAN REVIEW REQUIRED")
            return 3

        # A human runtime failure is a failed evaluation just like an agent
        # evaluation failure. The next implementation pass is therefore one
        # refinement attempt.
        breaker.record_refinement()

    while True:
        implementation = run_generator_or_refiner(
            pass_number=pass_number,
            selection=selection,
            selected=selected,
            base_candidate=base_candidate,
            evaluator_feedback=feedback,
        )

        if implementation.get("status") == "blocked":
            save_final(
                status="human_review_required",
                selected=selected,
                rule=rule,
                breaker=breaker,
                pass_number=pass_number,
                implementation=implementation,
                evaluation=feedback,
                reason=(
                    "The Assignment 5 implementation agent reported the "
                    "selected goal as blocked."
                ),
                runtime_feedback=runtime_feedback,
            )
            print_stage("HUMAN REVIEW REQUIRED")
            print("Generator/Refiner reported BLOCKED.")
            return 2

        evaluation = run_evaluator(
            pass_number=pass_number,
            rule=rule,
        )

        evaluation = enforce_refinement_progress(
            evaluation,
            implementation,
            feedback,
        )
        save_json(
            OUTPUT_ROOT / f"evaluation_pass_{pass_number}.json",
            evaluation,
        )

        if evaluation.get("status") == "pass":
            save_final(
                status="accepted_static",
                selected=selected,
                rule=rule,
                breaker=breaker,
                pass_number=pass_number,
                implementation=implementation,
                evaluation=evaluation,
                reason=(
                    "The implementation passed the Assignment 6 static "
                    "GDD-specific Evaluator. If this run followed human "
                    "runtime feedback, the developer must now test the "
                    "refined result again in Unity."
                ),
                runtime_feedback=runtime_feedback,
            )
            print_stage("GER RESULT — STATIC PASS")
            print(
                f"Accepted after implementation pass {pass_number} "
                f"with {breaker.refinements_used} refinement(s) used."
            )
            if runtime_feedback is not None:
                print(
                    "Runtime feedback was incorporated. Rebuild/test the "
                    "scene in Unity again before treating the feature as done."
                )
            else:
                print(
                    "Next: open Unity, compile, rebuild/inspect the scene as "
                    "appropriate, and perform the manual validation steps."
                )
            return 0

        if not breaker.can_refine():
            save_final(
                status="human_review_required",
                selected=selected,
                rule=rule,
                breaker=breaker,
                pass_number=pass_number,
                implementation=implementation,
                evaluation=evaluation,
                reason=(
                    "Circuit breaker stopped the GER loop because the "
                    "implementation still failed after the allowed "
                    "refinement attempts."
                ),
                runtime_feedback=runtime_feedback,
            )
            print_stage("CIRCUIT BREAKER — HUMAN REVIEW REQUIRED")
            print(
                f"Stopped after {breaker.refinements_used} refinement(s)."
            )
            return 3

        breaker.record_refinement()
        feedback = evaluation
        pass_number += 1

        print()
        print(
            "Evaluator requested changes. Reusing the Assignment 5 "
            "implementation agent as the Refiner."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assignment 6 GER pipeline reusing Assignment 3 and "
            "Assignment 5 agents."
        )
    )
    parser.add_argument(
        "--max-refinements",
        type=int,
        default=3,
        help=(
            "Maximum refinement passes before the circuit breaker "
            "requires human review. Default: 3."
        ),
    )
    parser.add_argument(
        "--runtime-feedback",
        type=Path,
        default=None,
        help=(
            "Resume an existing GER run from human Unity runtime feedback. "
            "The next pass starts at Refiner instead of Generator. "
            "Each feedback artifact is preserved as runtime_feedbackNNN.json."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.max_refinements < 0:
        print("--max-refinements must be >= 0", file=sys.stderr)
        return 1

    try:
        return run_pipeline(
            max_refinements=args.max_refinements,
            runtime_feedback_path=args.runtime_feedback,
        )
    except Exception as exc:
        print()
        print_stage("ASSIGNMENT 6 GER FAILED")
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
