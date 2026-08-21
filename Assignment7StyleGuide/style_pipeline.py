from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


A7_ROOT = Path(__file__).resolve().parent
REPO_ROOT = A7_ROOT.parent

STYLE_GUIDE_PATH = A7_ROOT / "STYLE_GUIDE.md"
GENERATOR_PROMPT_PATH = A7_ROOT / "prompts" / "generator.md"
EVALUATOR_PROMPT_PATH = A7_ROOT / "prompts" / "evaluator.md"
REFINER_PROMPT_PATH = A7_ROOT / "prompts" / "refiner.md"
EVALUATOR_SCHEMA_PATH = A7_ROOT / "evaluator_schema.json"
REFINER_SCHEMA_PATH = A7_ROOT / "refiner_schema.json"

DEFAULT_CASES_PATH = A7_ROOT / "test_cases" / "assignment7_demo_cases.json"
OUTPUT_ROOT = A7_ROOT / "outputs" / "pipeline"
LATEST_SUMMARY_PATH = OUTPUT_ROOT / "latest_summary.json"

MODEL = os.environ.get("CLAUDE_AGENT_MODEL", "sonnet")
TIMEOUT_SECONDS = int(os.environ.get("CLAUDE_AGENT_TIMEOUT_SECONDS", "900"))
MAX_TURNS = int(os.environ.get("CLAUDE_AGENT_MAX_TURNS", "6"))

RULE_ID_RE = re.compile(r"^NSC-(TONE|CANON|MECH|FORMAT)-[0-9]{2}$")

# Assignment 7 deliberately does NOT use the Assignment 4 RAG knowledge base.
# The Style Guide and per-item content contract are the authority for this
# style-specialization exercise. If RAG is reintroduced later, rebuild it from
# the current GDD first rather than silently using the stale Assignment 4 index.

# Reuse the bounded retry behavior proven in Assignment 6.
sys.path.insert(0, str(REPO_ROOT / "Assignment6GER"))
from circuit_breaker import CircuitBreaker  # noqa: E402


GENERATOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": ["generated"],
        },
        "content_id": {
            "type": "string",
            "minLength": 1,
        },
        "label": {
            "type": "string",
            "minLength": 1,
        },
        "text": {
            "type": "string",
            "minLength": 1,
        },
        "reason": {
            "type": "string",
            "minLength": 1,
        },
    },
    "required": [
        "status",
        "content_id",
        "label",
        "text",
        "reason",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_id_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_text(path: Path, *, require_nonempty: bool = True) -> str:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Required file not found: {path}") from exc

    if require_nonempty and not text.strip():
        raise RuntimeError(
            f"Required text file is empty: {path}\n"
            "Build/populate this file before running the full pipeline."
        )
    return text


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Required file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc

    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
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


def run_claude(
    prompt: str,
    schema: dict[str, Any],
    *,
    role: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    compact_schema = json.dumps(
        schema,
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
        "",
        "--disallowedTools",
        "mcp__*",
        "--json-schema",
        compact_schema,
        "--input-format",
        "text",
    ]

    started_at = utc_now()
    timer = time.monotonic()

    try:
        process = subprocess.run(
            command,
            cwd=REPO_ROOT,
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
            f"Claude {role} exceeded {TIMEOUT_SECONDS} seconds."
        ) from exc

    duration = round(time.monotonic() - timer, 2)

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            f"Claude {role} failed with exit code {process.returncode}.\n"
            f"{error_text}"
        )

    try:
        wrapper = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Claude {role} returned output that was not valid wrapper JSON."
        ) from exc

    structured = wrapper.get("structured_output")
    if not isinstance(structured, dict):
        raise RuntimeError(
            f"Claude {role} did not return structured_output matching "
            "the supplied schema."
        )

    metadata = {
        "role": role,
        "model": MODEL,
        "max_turns": MAX_TURNS,
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "duration_seconds": duration,
        "session_id": wrapper.get("session_id"),
        "num_turns": wrapper.get("num_turns"),
    }

    return structured, metadata


def validate_case(case: dict[str, Any]) -> None:
    required_strings = [
        "id",
        "label",
        "content_type",
        "style_problem",
        "generator_instruction",
    ]
    for key in required_strings:
        value = case.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(
                f"Demo case requires non-empty string field {key!r}: {case}"
            )

    max_words = case.get("max_words")
    if not isinstance(max_words, int) or max_words < 1:
        raise RuntimeError(
            f"Demo case {case['id']!r} requires max_words >= 1."
        )

    requirements = case.get("content_requirements")
    if not isinstance(requirements, list) or not requirements:
        raise RuntimeError(
            f"Demo case {case['id']!r} requires content_requirements."
        )
    if any(not isinstance(item, str) or not item.strip() for item in requirements):
        raise RuntimeError(
            f"Demo case {case['id']!r} has invalid content_requirements."
        )

    task_context = case.get("task_context", {})
    if not isinstance(task_context, dict):
        raise RuntimeError(
            f"Demo case {case['id']!r} task_context must be an object."
        )

    require_refinement = case.get("require_refinement", True)
    if not isinstance(require_refinement, bool):
        raise RuntimeError(
            f"Demo case {case['id']!r} require_refinement must be boolean."
        )


def validate_demo_suite(
    suite: dict[str, Any],
    *,
    selected_case: str | None,
) -> list[dict[str, Any]]:
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RuntimeError("Demo suite contains no cases.")

    for case in cases:
        if not isinstance(case, dict):
            raise RuntimeError("Every demo case must be a JSON object.")
        validate_case(case)

    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Demo case IDs must be unique.")

    if selected_case is not None:
        selected = [case for case in cases if case["id"] == selected_case]
        if not selected:
            raise RuntimeError(f"Unknown demo case: {selected_case!r}")
        return selected

    # Assignment 7 asks for exactly three before/after examples, each testing a
    # different style problem. Enforce that on a normal full run.
    if len(cases) != 3:
        raise RuntimeError(
            "A full Assignment 7 demonstration run must contain exactly "
            f"3 cases; found {len(cases)}."
        )

    problems = [case["style_problem"] for case in cases]
    if len(problems) != len(set(problems)):
        raise RuntimeError(
            "The three Assignment 7 demo cases must use distinct "
            "style_problem values."
        )

    return cases


def build_generator_prompt(
    base_prompt: str,
    case: dict[str, Any],
) -> str:
    # Deliberately do not give the Generator STYLE_GUIDE.md. Assignment 7 is
    # demonstrating the downstream Style Evaluator correcting generated copy.
    # The generator gets only the content contract plus the case's generation
    # instruction, which may intentionally request a style mistake.
    package = {
        "content_id": case["id"],
        "label": case["label"],
        "content_type": case["content_type"],
        "max_words": case["max_words"],
        "content_requirements": case["content_requirements"],
        "task_context": case.get("task_context", {}),
        "generation_instruction": case["generator_instruction"],
    }

    return (
        base_prompt.rstrip()
        + "\n\n# Current Generation Package\n\n"
        + json.dumps(package, indent=2, ensure_ascii=False)
        + "\n\n# Output Contract\n\n"
        + "Set `content_id` and `label` exactly to the supplied values. "
          "Place only the generated player-facing candidate in `text`. "
          "This Generator is producing the initial candidate for a Style "
          "Evaluator demonstration, so follow the supplied generation_instruction "
          "even when it intentionally produces a style problem. "
          "Do not mention the evaluator, refiner, assignment, prompt, or test in "
          "the player-facing text. Return structured JSON only.\n"
    )


def build_evaluator_prompt(
    base_prompt: str,
    style_guide: str,
    case: dict[str, Any],
    candidate_text: str,
) -> str:
    package = {
        "content_id": case["id"],
        "label": case["label"],
        "content_type": case["content_type"],
        "max_words": case["max_words"],
        "content_requirements": case["content_requirements"],
        "task_context": case.get("task_context", {}),
        "candidate_text": candidate_text,
    }

    return (
        base_prompt.rstrip()
        + "\n\n# Supplied No Safe Circle Style Guide\n\n"
        + style_guide.rstrip()
        + "\n\n# Current Evaluation Package\n\n"
        + json.dumps(package, indent=2, ensure_ascii=False)
        + "\n\n# Final Instruction\n\n"
        + "Evaluate only the supplied candidate against the Style Guide while "
          "treating the supplied content requirements/task context as authoritative "
          "for this item. Return the structured JSON object required by the output "
          "contract. Do not rewrite the candidate.\n"
    )


def build_refiner_prompt(
    base_prompt: str,
    style_guide: str,
    case: dict[str, Any],
    candidate_text: str,
    evaluation: dict[str, Any],
) -> str:
    package = {
        "content_id": case["id"],
        "label": case["label"],
        "content_type": case["content_type"],
        "max_words": case["max_words"],
        "content_requirements": case["content_requirements"],
        "task_context": case.get("task_context", {}),
        "current_candidate_text": candidate_text,
        "style_evaluator": {
            "score": evaluation["score"],
            "reason": evaluation["reason"],
            "violations": evaluation["violations"],
        },
    }

    return (
        base_prompt.rstrip()
        + "\n\n# Supplied No Safe Circle Style Guide\n\n"
        + style_guide.rstrip()
        + "\n\n# Current Refinement Package\n\n"
        + json.dumps(package, indent=2, ensure_ascii=False)
        + "\n\n# Final Instruction\n\n"
        + "Revise the current candidate only. Address every current evaluator "
          "violation, preserve already-correct content, avoid repeating the same "
          "limitation or consequence in multiple ways, stay within the maximum "
          "word count, and return the structured JSON object required by the "
          "output contract.\n"
    )


def validate_generator(
    generated: dict[str, Any],
    case: dict[str, Any],
) -> None:
    if generated.get("status") != "generated":
        raise RuntimeError(
            f"Generator returned invalid status: {generated.get('status')!r}"
        )

    if generated.get("content_id") != case["id"]:
        raise RuntimeError(
            f"Generator content_id {generated.get('content_id')!r} does not "
            f"match {case['id']!r}."
        )

    if generated.get("label") != case["label"]:
        raise RuntimeError(
            f"Generator label {generated.get('label')!r} does not "
            f"match {case['label']!r}."
        )

    text = generated.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Generator returned empty player-facing text.")

    reason = generated.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise RuntimeError("Generator returned an empty reason.")


def validate_evaluator(
    evaluation: dict[str, Any],
    case: dict[str, Any],
) -> None:
    if evaluation.get("content_id") != case["id"]:
        raise RuntimeError(
            f"Evaluator content_id {evaluation.get('content_id')!r} does not "
            f"match {case['id']!r}."
        )

    score = evaluation.get("score")
    if not isinstance(score, int) or isinstance(score, bool):
        raise RuntimeError("Evaluator score must be an integer.")
    if not 1 <= score <= 10:
        raise RuntimeError(
            f"Evaluator score must be 1–10; got {score!r}."
        )

    reason = evaluation.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise RuntimeError("Evaluator reason must be a non-empty string.")

    violations = evaluation.get("violations")
    if not isinstance(violations, list):
        raise RuntimeError("Evaluator violations must be an array.")

    if score == 10 and violations:
        raise RuntimeError(
            "Evaluator score 10 must have an empty violations array."
        )

    if score < 10 and not violations:
        raise RuntimeError(
            "Evaluator score below 10 must include at least one violation."
        )

    for index, violation in enumerate(violations, start=1):
        if not isinstance(violation, dict):
            raise RuntimeError(
                f"Evaluator violation #{index} must be an object."
            )

        rule_id = violation.get("rule_id")
        if not isinstance(rule_id, str) or not RULE_ID_RE.fullmatch(rule_id):
            raise RuntimeError(
                f"Evaluator violation #{index} has invalid rule_id "
                f"{rule_id!r}."
            )

        if violation.get("severity") not in {
            "minor",
            "meaningful",
            "major",
        }:
            raise RuntimeError(
                f"Evaluator violation #{index} has invalid severity."
            )

        for key in (
            "problematic_text",
            "explanation",
            "revision_instruction",
        ):
            value = violation.get(key)
            if not isinstance(value, str):
                raise RuntimeError(
                    f"Evaluator violation #{index} field {key!r} "
                    "must be a string."
                )
            if key != "problematic_text" and not value.strip():
                raise RuntimeError(
                    f"Evaluator violation #{index} field {key!r} "
                    "must not be empty."
                )


def evaluator_rule_ids(evaluation: dict[str, Any]) -> set[str]:
    return {
        violation["rule_id"]
        for violation in evaluation["violations"]
        if isinstance(violation, dict)
        and isinstance(violation.get("rule_id"), str)
    }


def validate_refiner(
    refined: dict[str, Any],
    case: dict[str, Any],
    evaluation: dict[str, Any],
) -> int:
    if refined.get("status") != "revised":
        raise RuntimeError(
            f"Refiner status must be 'revised'; got "
            f"{refined.get('status')!r}."
        )

    if refined.get("content_id") != case["id"]:
        raise RuntimeError(
            f"Refiner content_id {refined.get('content_id')!r} does not "
            f"match {case['id']!r}."
        )

    if refined.get("label") != case["label"]:
        raise RuntimeError(
            f"Refiner label {refined.get('label')!r} does not "
            f"match {case['label']!r}."
        )

    text = refined.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Refiner returned empty player-facing text.")

    word_count = len(text.split())
    if word_count > case["max_words"]:
        raise RuntimeError(
            f"Refiner output is {word_count} words; maximum is "
            f"{case['max_words']}."
        )

    addressed = refined.get("addressed_rule_ids")
    if not isinstance(addressed, list):
        raise RuntimeError("Refiner addressed_rule_ids must be an array.")

    addressed_set = {
        item for item in addressed if isinstance(item, str)
    }
    if len(addressed_set) != len(addressed):
        raise RuntimeError(
            "Refiner addressed_rule_ids contains duplicates or invalid IDs."
        )

    expected = evaluator_rule_ids(evaluation)
    invented = addressed_set - expected
    missing = expected - addressed_set

    if invented:
        raise RuntimeError(
            "Refiner invented addressed rule IDs: "
            + ", ".join(sorted(invented))
        )

    if missing:
        raise RuntimeError(
            "Refiner did not report addressing evaluator rule IDs: "
            + ", ".join(sorted(missing))
        )

    changes = refined.get("changes_made")
    if not isinstance(changes, list) or not changes:
        raise RuntimeError(
            "Refiner changes_made must contain at least one correction."
        )

    if any(not isinstance(item, str) or not item.strip() for item in changes):
        raise RuntimeError(
            "Every Refiner changes_made entry must be non-empty."
        )

    reason = refined.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise RuntimeError("Refiner reason must be a non-empty string.")

    return word_count


def run_generator(
    case: dict[str, Any],
    generator_prompt: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    prompt = build_generator_prompt(generator_prompt, case)
    generated, metadata = run_claude(
        prompt,
        GENERATOR_SCHEMA,
        role="generator",
    )
    validate_generator(generated, case)
    return generated, metadata


def run_evaluator(
    case: dict[str, Any],
    candidate_text: str,
    evaluator_prompt: str,
    evaluator_schema: dict[str, Any],
    style_guide: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    prompt = build_evaluator_prompt(
        evaluator_prompt,
        style_guide,
        case,
        candidate_text,
    )
    evaluation, metadata = run_claude(
        prompt,
        evaluator_schema,
        role="style evaluator",
    )
    validate_evaluator(evaluation, case)
    return evaluation, metadata


def run_refiner(
    case: dict[str, Any],
    candidate_text: str,
    evaluation: dict[str, Any],
    refiner_prompt: str,
    refiner_schema: dict[str, Any],
    style_guide: str,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    prompt = build_refiner_prompt(
        refiner_prompt,
        style_guide,
        case,
        candidate_text,
        evaluation,
    )
    refined, metadata = run_claude(
        prompt,
        refiner_schema,
        role="style refiner",
    )
    word_count = validate_refiner(
        refined,
        case,
        evaluation,
    )
    return refined, metadata, word_count


def run_case(
    *,
    case: dict[str, Any],
    case_output_root: Path,
    acceptance_score: int,
    max_refinements: int,
    generator_prompt: str,
    evaluator_prompt: str,
    refiner_prompt: str,
    evaluator_schema: dict[str, Any],
    refiner_schema: dict[str, Any],
    style_guide: str,
) -> dict[str, Any]:
    case_output_root.mkdir(parents=True, exist_ok=True)

    print_stage(
        f"CASE — {case['id']} ({case['style_problem']})"
    )

    print("Generator: creating initial candidate...")
    generated, generator_metadata = run_generator(
        case,
        generator_prompt,
    )

    candidate_text = generated["text"]

    generation_artifact = {
        "case": case,
        "generation": generated,
        "metadata": generator_metadata,
    }
    save_json(
        case_output_root / "generation.json",
        generation_artifact,
    )

    print(f"Generated: {candidate_text}")

    print("Style Evaluator: scoring initial candidate...")
    evaluation, evaluator_metadata = run_evaluator(
        case,
        candidate_text,
        evaluator_prompt,
        evaluator_schema,
        style_guide,
    )

    save_json(
        case_output_root / "evaluation_pass_0.json",
        {
            "pass_number": 0,
            "candidate_text": candidate_text,
            "evaluation": evaluation,
            "metadata": evaluator_metadata,
        },
    )

    initial_evaluation = evaluation
    score_history = [evaluation["score"]]

    print(
        f"Initial score: {evaluation['score']}/10 — "
        f"{evaluation['reason']}"
    )

    breaker = CircuitBreaker(
        max_refinements=max_refinements,
        refinements_used=0,
    )

    refinements: list[dict[str, Any]] = []
    refinement_number = 0

    while evaluation["score"] < acceptance_score:
        if not breaker.can_refine():
            final = {
                "case_id": case["id"],
                "label": case["label"],
                "style_problem": case["style_problem"],
                "status": "human_review_required",
                "reason": (
                    "Circuit breaker stopped the Style GER loop because "
                    f"the candidate remained below {acceptance_score}/10 "
                    f"after {breaker.refinements_used} refinement(s)."
                ),
                "acceptance_score": acceptance_score,
                "original_generated_content": generated["text"],
                "initial_evaluation": initial_evaluation,
                "final_content": candidate_text,
                "final_evaluation": evaluation,
                "score_history": score_history,
                "refinements_used": breaker.refinements_used,
                "circuit_breaker": breaker.status(),
                "refinements": refinements,
                "demonstration_requirement_met": (
                    breaker.refinements_used > 0
                ),
            }
            save_json(case_output_root / "final_result.json", final)
            print(
                "Circuit breaker tripped. Human review required."
            )
            return final

        breaker.record_refinement()
        refinement_number += 1

        print(
            f"Refiner pass {refinement_number}: "
            f"repairing score {evaluation['score']}/10..."
        )

        prior_text = candidate_text
        prior_score = evaluation["score"]

        refined, refiner_metadata, word_count = run_refiner(
            case,
            candidate_text,
            evaluation,
            refiner_prompt,
            refiner_schema,
            style_guide,
        )

        candidate_text = refined["text"]

        refinement_artifact = {
            "refinement_number": refinement_number,
            "input_text": prior_text,
            "input_evaluation": evaluation,
            "refiner": refined,
            "word_count": word_count,
            "metadata": refiner_metadata,
            "changed_text": candidate_text != prior_text,
        }
        save_json(
            case_output_root
            / f"refinement_pass_{refinement_number}.json",
            refinement_artifact,
        )

        print(f"Refined: {candidate_text}")

        print(
            f"Style Evaluator: re-scoring refinement "
            f"{refinement_number}..."
        )
        evaluation, evaluator_metadata = run_evaluator(
            case,
            candidate_text,
            evaluator_prompt,
            evaluator_schema,
            style_guide,
        )

        score_history.append(evaluation["score"])

        evaluation_artifact = {
            "pass_number": refinement_number,
            "candidate_text": candidate_text,
            "previous_score": prior_score,
            "evaluation": evaluation,
            "metadata": evaluator_metadata,
        }
        save_json(
            case_output_root
            / f"evaluation_pass_{refinement_number}.json",
            evaluation_artifact,
        )

        refinements.append(
            {
                "refinement_number": refinement_number,
                "input_score": prior_score,
                "output_score": evaluation["score"],
                "input_text": prior_text,
                "output_text": candidate_text,
                "refiner": refined,
                "evaluation": evaluation,
            }
        )

        delta = evaluation["score"] - prior_score
        sign = "+" if delta >= 0 else ""
        print(
            f"New score: {evaluation['score']}/10 "
            f"({sign}{delta}) — {evaluation['reason']}"
        )

    require_refinement = case.get("require_refinement", True)
    demo_met = (
        not require_refinement
        or breaker.refinements_used > 0
    )

    status = "accepted"
    reason = (
        f"Style Evaluator reached {evaluation['score']}/10, "
        f"meeting the configured acceptance score of "
        f"{acceptance_score}/10."
    )

    if not demo_met:
        status = "accepted_but_demo_invalid"
        reason = (
            "The generated candidate already met the acceptance score, "
            "so this case did not demonstrate the required automatic "
            "Evaluator → Refiner correction."
        )

    final = {
        "case_id": case["id"],
        "label": case["label"],
        "style_problem": case["style_problem"],
        "status": status,
        "reason": reason,
        "acceptance_score": acceptance_score,
        "original_generated_content": generated["text"],
        "generation_reason": generated["reason"],
        "initial_evaluation": initial_evaluation,
        "final_content": candidate_text,
        "final_evaluation": evaluation,
        "score_history": score_history,
        "refinements_used": breaker.refinements_used,
        "circuit_breaker": breaker.status(),
        "refinements": refinements,
        "demonstration_requirement_met": demo_met,
    }

    save_json(case_output_root / "final_result.json", final)

    print(
        f"Accepted: {evaluation['score']}/10 after "
        f"{breaker.refinements_used} refinement(s)."
    )
    return final


def build_run_summary(
    *,
    run_id: str,
    cases_path: Path,
    acceptance_score: int,
    max_refinements: int,
    case_results: list[dict[str, Any]],
) -> dict[str, Any]:
    accepted = [
        result
        for result in case_results
        if result["status"] == "accepted"
    ]
    demo_valid = [
        result
        for result in case_results
        if result.get("demonstration_requirement_met") is True
    ]

    return {
        "assignment": 7,
        "game": "No Safe Circle",
        "pipeline": (
            "Generator -> Style Evaluator (SCORE + REASON) -> "
            "automatic Refiner -> re-evaluation"
        ),
        "rag_used": False,
        "rag_policy": (
            "Assignment 7 does not use the Assignment 4 RAG index. "
            "The Style Guide plus the per-item content requirements/task "
            "context are supplied directly. Rebuild the RAG from the current "
            "GDD before reintroducing retrieval later."
        ),
        "run_id": run_id,
        "model": MODEL,
        "acceptance_score": acceptance_score,
        "max_refinements": max_refinements,
        "cases_source": str(cases_path),
        "completed_at_utc": utc_now(),
        "summary": {
            "total_cases": len(case_results),
            "accepted": len(accepted),
            "all_accepted": len(accepted) == len(case_results),
            "demonstration_valid_cases": len(demo_valid),
            "all_demonstrations_valid": (
                len(demo_valid) == len(case_results)
            ),
        },
        "results": case_results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assignment 7 No Safe Circle Style Guide Agent pipeline. "
            "Runs Generator -> scored Style Evaluator -> automatic Refiner "
            "until accepted or the Assignment 6-style circuit breaker trips."
        )
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help=(
            "Assignment 7 demonstration suite JSON. "
            "A normal full run must contain exactly 3 distinct style problems."
        ),
    )
    parser.add_argument(
        "--case",
        default=None,
        help="Run one case ID for debugging instead of the full 3-case suite.",
    )
    parser.add_argument(
        "--acceptance-score",
        type=int,
        default=9,
        help="Minimum Style Evaluator score required for acceptance. Default: 9.",
    )
    parser.add_argument(
        "--max-refinements",
        type=int,
        default=3,
        help=(
            "Maximum automatic Refiner passes before human review. "
            "Default: 3."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if not 1 <= args.acceptance_score <= 10:
        print(
            "--acceptance-score must be an integer from 1 through 10.",
            file=sys.stderr,
        )
        return 1

    if args.max_refinements < 0:
        print(
            "--max-refinements must be >= 0.",
            file=sys.stderr,
        )
        return 1

    try:
        style_guide = load_text(STYLE_GUIDE_PATH)
        generator_prompt = load_text(GENERATOR_PROMPT_PATH)
        evaluator_prompt = load_text(EVALUATOR_PROMPT_PATH)
        refiner_prompt = load_text(REFINER_PROMPT_PATH)
        evaluator_schema = load_json(EVALUATOR_SCHEMA_PATH)
        refiner_schema = load_json(REFINER_SCHEMA_PATH)
        suite = load_json(args.cases)

        cases = validate_demo_suite(
            suite,
            selected_case=args.case,
        )

        run_id = run_id_now()
        run_root = OUTPUT_ROOT / run_id
        run_root.mkdir(parents=True, exist_ok=False)

        print_stage("ASSIGNMENT 7 — STYLE GUIDE AGENT")
        print(f"Model: {MODEL}")
        print(f"Cases: {len(cases)}")
        print(f"Acceptance score: {args.acceptance_score}/10")
        print(f"Maximum refinements per case: {args.max_refinements}")
        print("RAG: NOT USED")
        print(
            "Authority: STYLE_GUIDE.md + per-item content contract"
        )
        print(
            "Loop: Generator -> Style Evaluator -> Refiner -> "
            "Style Evaluator"
        )
        print(f"Run output: {run_root}")

        case_results: list[dict[str, Any]] = []

        for case in cases:
            case_result = run_case(
                case=case,
                case_output_root=run_root / case["id"],
                acceptance_score=args.acceptance_score,
                max_refinements=args.max_refinements,
                generator_prompt=generator_prompt,
                evaluator_prompt=evaluator_prompt,
                refiner_prompt=refiner_prompt,
                evaluator_schema=evaluator_schema,
                refiner_schema=refiner_schema,
                style_guide=style_guide,
            )
            case_results.append(case_result)

        summary = build_run_summary(
            run_id=run_id,
            cases_path=args.cases,
            acceptance_score=args.acceptance_score,
            max_refinements=args.max_refinements,
            case_results=case_results,
        )

        save_json(run_root / "run_summary.json", summary)
        save_json(LATEST_SUMMARY_PATH, summary)

        print_stage("ASSIGNMENT 7 — FINAL RESULT")
        print(
            f"Accepted: {summary['summary']['accepted']}/"
            f"{summary['summary']['total_cases']}"
        )
        print(
            "Valid before/after demonstrations: "
            f"{summary['summary']['demonstration_valid_cases']}/"
            f"{summary['summary']['total_cases']}"
        )
        print(f"Saved: {run_root / 'run_summary.json'}")
        print(f"Latest: {LATEST_SUMMARY_PATH}")

        success = (
            summary["summary"]["all_accepted"]
            and summary["summary"]["all_demonstrations_valid"]
        )
        return 0 if success else 2

    except Exception as exc:
        print()
        print_stage("ASSIGNMENT 7 STYLE PIPELINE FAILED")
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
