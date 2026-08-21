from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Reuse the evaluator harness's already-tested Claude runner and evaluator
# prompt-building logic. This keeps the refiner test focused on the new
# component rather than duplicating the invocation layer.
import test_evaluator as evaluator_harness


A7_ROOT = Path(__file__).resolve().parent

STYLE_GUIDE_PATH = A7_ROOT / "STYLE_GUIDE.md"
REFINER_PROMPT_PATH = A7_ROOT / "prompts" / "refiner.md"
REFINER_SCHEMA_PATH = A7_ROOT / "refiner_schema.json"
EVALUATOR_PROMPT_PATH = A7_ROOT / "prompts" / "evaluator.md"
EVALUATOR_SCHEMA_PATH = A7_ROOT / "evaluator_schema.json"

DEFAULT_CASES_PATH = A7_ROOT / "test_cases" / "refiner_smoke_tests.json"
DEFAULT_OUTPUT_PATH = (
    A7_ROOT / "outputs" / "tests" / "refiner_test_results.json"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Required file not found: {path}") from exc


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


def unique_rule_ids(evaluation: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    violations = evaluation.get("violations", [])
    if not isinstance(violations, list):
        return ids

    for violation in violations:
        if not isinstance(violation, dict):
            continue
        rule_id = violation.get("rule_id")
        if isinstance(rule_id, str) and rule_id:
            ids.add(rule_id)

    return ids


def build_refiner_prompt(
    base_prompt: str,
    style_guide: str,
    case: dict[str, Any],
    evaluation: dict[str, Any],
) -> str:
    package = {
        "content_id": case["id"],
        "label": case["label"],
        "content_type": case["content_type"],
        "max_words": case["max_words"],
        "content_requirements": case.get("content_requirements", []),
        "current_candidate_text": case["candidate_text"],
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
        + "Revise the supplied candidate only. Address every evaluator violation, "
          "stay within the supplied maximum word count, preserve the content purpose, "
          "and return the structured JSON object required by the output contract.\n"
    )


def evaluate_candidate(
    *,
    case: dict[str, Any],
    candidate_text: str,
    evaluator_prompt: str,
    evaluator_schema: dict[str, Any],
    style_guide: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    eval_case = {
        "id": case["id"],
        "label": case["label"],
        "content_type": case["content_type"],
        "max_words": case["max_words"],
        "content_requirements": case.get("content_requirements", []),
        "task_context": case.get("task_context", {}),
        "candidate_text": candidate_text,
    }

    prompt = evaluator_harness.build_prompt(
        evaluator_prompt,
        style_guide,
        eval_case,
    )
    result, metadata = evaluator_harness.run_claude(
        prompt,
        evaluator_schema,
    )

    shape_errors = evaluator_harness.validate_result_shape(
        result,
        case["id"],
    )
    if shape_errors:
        raise RuntimeError(
            "Evaluator returned invalid structured output: "
            + "; ".join(shape_errors)
        )

    return result, metadata


def validate_initial_evaluation(
    evaluation: dict[str, Any],
    expected: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    max_score = expected.get("max_score")
    if isinstance(max_score, int) and evaluation["score"] > max_score:
        errors.append(
            f"initial score {evaluation['score']} is above expected maximum "
            f"{max_score}; the intentionally bad case was not detected strongly enough"
        )

    required_any = expected.get("required_any_rule_ids", [])
    actual_ids = unique_rule_ids(evaluation)

    if required_any and not any(rule_id in actual_ids for rule_id in required_any):
        errors.append(
            "initial evaluation did not identify any expected rule family; "
            f"expected one of {required_any}, got {sorted(actual_ids)}"
        )

    return errors


def validate_refiner_result(
    result: dict[str, Any],
    case: dict[str, Any],
    initial_evaluation: dict[str, Any],
) -> tuple[list[str], int]:
    errors: list[str] = []

    if result.get("status") != "revised":
        errors.append(
            f"status must be 'revised'; got {result.get('status')!r}"
        )

    if result.get("content_id") != case["id"]:
        errors.append(
            f"content_id was {result.get('content_id')!r}; "
            f"expected {case['id']!r}"
        )

    if result.get("label") != case["label"]:
        errors.append(
            f"label was {result.get('label')!r}; expected {case['label']!r}"
        )

    text = result.get("text")
    if not isinstance(text, str) or not text.strip():
        errors.append("text must be a non-empty string")
        word_count = 0
    else:
        word_count = len(text.split())
        if word_count > case["max_words"]:
            errors.append(
                f"revised text is {word_count} words; maximum is "
                f"{case['max_words']}"
            )

    addressed = result.get("addressed_rule_ids")
    if not isinstance(addressed, list):
        errors.append("addressed_rule_ids must be an array")
        addressed_set: set[str] = set()
    else:
        if len(addressed) != len(set(addressed)):
            errors.append("addressed_rule_ids must not contain duplicates")
        addressed_set = {
            rule_id for rule_id in addressed if isinstance(rule_id, str)
        }

    supplied_rule_ids = unique_rule_ids(initial_evaluation)

    invented_ids = addressed_set - supplied_rule_ids
    if invented_ids:
        errors.append(
            "addressed_rule_ids contains IDs not supplied by the evaluator: "
            + ", ".join(sorted(invented_ids))
        )

    missing_ids = supplied_rule_ids - addressed_set
    if missing_ids:
        errors.append(
            "refiner did not report addressing evaluator rule ID(s): "
            + ", ".join(sorted(missing_ids))
        )

    changes = result.get("changes_made")
    if not isinstance(changes, list) or not changes:
        errors.append("changes_made must contain at least one correction")
    elif any(not isinstance(item, str) or not item.strip() for item in changes):
        errors.append("every changes_made item must be a non-empty string")

    reason = result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append("reason must be a non-empty string")

    return errors, word_count


def validate_post_evaluation(
    *,
    initial: dict[str, Any],
    final: dict[str, Any],
    acceptance_score: int,
) -> list[str]:
    errors: list[str] = []

    if final["score"] <= initial["score"]:
        errors.append(
            f"style score did not improve: {initial['score']} -> {final['score']}"
        )

    if final["score"] < acceptance_score:
        errors.append(
            f"refined score {final['score']} is below acceptance target "
            f"{acceptance_score}"
        )

    major_violations = [
        violation
        for violation in final.get("violations", [])
        if isinstance(violation, dict)
        and violation.get("severity") == "major"
    ]
    if major_violations:
        errors.append(
            f"refined text still has {len(major_violations)} major violation(s)"
        )

    return errors


def run_case(
    *,
    case: dict[str, Any],
    acceptance_score: int,
    style_guide: str,
    evaluator_prompt: str,
    evaluator_schema: dict[str, Any],
    refiner_prompt: str,
    refiner_schema: dict[str, Any],
) -> dict[str, Any]:
    initial_evaluation, initial_eval_metadata = evaluate_candidate(
        case=case,
        candidate_text=case["candidate_text"],
        evaluator_prompt=evaluator_prompt,
        evaluator_schema=evaluator_schema,
        style_guide=style_guide,
    )

    initial_errors = validate_initial_evaluation(
        initial_evaluation,
        case.get("expected_initial", {}),
    )

    if initial_evaluation["score"] >= acceptance_score:
        initial_errors.append(
            f"initial candidate already scored {initial_evaluation['score']}, "
            f"which meets acceptance target {acceptance_score}; "
            "this is not a valid refiner smoke-test case"
        )

    if initial_errors:
        return {
            "case_id": case["id"],
            "label": case["label"],
            "candidate_text": case["candidate_text"],
            "initial_evaluation": initial_evaluation,
            "initial_evaluator_metadata": initial_eval_metadata,
            "refiner": None,
            "refiner_metadata": None,
            "final_evaluation": None,
            "final_evaluator_metadata": None,
            "validation_errors": initial_errors,
            "status": "fail",
        }

    prompt = build_refiner_prompt(
        refiner_prompt,
        style_guide,
        case,
        initial_evaluation,
    )
    refined, refiner_metadata = evaluator_harness.run_claude(
        prompt,
        refiner_schema,
    )

    refiner_errors, word_count = validate_refiner_result(
        refined,
        case,
        initial_evaluation,
    )

    if refiner_errors:
        return {
            "case_id": case["id"],
            "label": case["label"],
            "candidate_text": case["candidate_text"],
            "initial_evaluation": initial_evaluation,
            "initial_evaluator_metadata": initial_eval_metadata,
            "refiner": refined,
            "refiner_metadata": refiner_metadata,
            "refined_word_count": word_count,
            "final_evaluation": None,
            "final_evaluator_metadata": None,
            "validation_errors": refiner_errors,
            "status": "fail",
        }

    final_evaluation, final_eval_metadata = evaluate_candidate(
        case=case,
        candidate_text=refined["text"],
        evaluator_prompt=evaluator_prompt,
        evaluator_schema=evaluator_schema,
        style_guide=style_guide,
    )

    post_errors = validate_post_evaluation(
        initial=initial_evaluation,
        final=final_evaluation,
        acceptance_score=acceptance_score,
    )

    return {
        "case_id": case["id"],
        "label": case["label"],
        "candidate_text": case["candidate_text"],
        "initial_evaluation": initial_evaluation,
        "initial_evaluator_metadata": initial_eval_metadata,
        "refiner": refined,
        "refiner_metadata": refiner_metadata,
        "refined_word_count": word_count,
        "final_evaluation": final_evaluation,
        "final_evaluator_metadata": final_eval_metadata,
        "score_change": (
            final_evaluation["score"] - initial_evaluation["score"]
        ),
        "validation_errors": post_errors,
        "status": "pass" if not post_errors else "fail",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test the Assignment 7 Style Refiner by evaluating bad copy, "
            "refining it from evaluator feedback, and evaluating the revision again."
        )
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to refiner smoke-test JSON.",
    )
    parser.add_argument(
        "--case",
        default=None,
        help="Run only one case ID instead of the full suite.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Where to save the combined refiner test results.",
    )
    parser.add_argument(
        "--acceptance-score",
        type=int,
        default=None,
        help=(
            "Override the suite's acceptance score. "
            "Default comes from refiner_smoke_tests.json."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        style_guide = load_text(STYLE_GUIDE_PATH)
        evaluator_prompt = load_text(EVALUATOR_PROMPT_PATH)
        evaluator_schema = load_json(EVALUATOR_SCHEMA_PATH)
        refiner_prompt = load_text(REFINER_PROMPT_PATH)
        refiner_schema = load_json(REFINER_SCHEMA_PATH)
        suite = load_json(args.cases)

        acceptance_score = (
            args.acceptance_score
            if args.acceptance_score is not None
            else suite.get("acceptance_score", 9)
        )
        if not isinstance(acceptance_score, int) or not 1 <= acceptance_score <= 10:
            raise RuntimeError("Acceptance score must be an integer from 1–10.")

        cases = suite.get("cases")
        if not isinstance(cases, list) or not cases:
            raise RuntimeError("Refiner test suite contains no cases.")

        if args.case:
            cases = [case for case in cases if case.get("id") == args.case]
            if not cases:
                raise RuntimeError(f"Unknown test case: {args.case!r}")

        print()
        print("=" * 72)
        print("ASSIGNMENT 7 — STYLE REFINER SMOKE TESTS")
        print("=" * 72)
        print(f"Model: {evaluator_harness.MODEL}")
        print(f"Max turns per Claude call: {evaluator_harness.MAX_TURNS}")
        print(f"Acceptance score: {acceptance_score}/10")
        print(f"Cases: {len(cases)}")
        print()

        results: list[dict[str, Any]] = []

        for index, case in enumerate(cases, start=1):
            print(f"[{index}/{len(cases)}] {case['id']} — {case['label']}")

            try:
                result = run_case(
                    case=case,
                    acceptance_score=acceptance_score,
                    style_guide=style_guide,
                    evaluator_prompt=evaluator_prompt,
                    evaluator_schema=evaluator_schema,
                    refiner_prompt=refiner_prompt,
                    refiner_schema=refiner_schema,
                )
            except Exception as exc:
                result = {
                    "case_id": case["id"],
                    "label": case["label"],
                    "candidate_text": case["candidate_text"],
                    "runtime_error": str(exc),
                    "status": "error",
                }

            results.append(result)

            if result["status"] == "error":
                print("  TEST: ERROR")
                print(f"    Runtime error: {result['runtime_error']}")
                print()
                continue

            initial = result.get("initial_evaluation")
            refined = result.get("refiner")
            final = result.get("final_evaluation")

            if initial:
                print(
                    f"  Initial score: {initial['score']}/10 | "
                    f"Violations: {len(initial.get('violations', []))}"
                )

            if refined:
                print(f"  Refined text: {refined['text']}")
                print(
                    f"  Refined words: {result.get('refined_word_count')}/"
                    f"{case['max_words']}"
                )

            if final:
                print(
                    f"  Final score: {final['score']}/10 | "
                    f"Violations: {len(final.get('violations', []))}"
                )
                print(f"  Score change: +{result.get('score_change', 0)}")

            print(f"  TEST: {result['status'].upper()}")

            for error in result.get("validation_errors", []):
                print(f"    Validation error: {error}")

            print()

        passed_count = sum(item["status"] == "pass" for item in results)
        error_count = sum(item["status"] == "error" for item in results)
        failed_count = len(results) - passed_count

        payload = {
            "suite": suite.get(
                "suite",
                "Assignment 7 Style Refiner Smoke Tests",
            ),
            "game": "No Safe Circle",
            "model": evaluator_harness.MODEL,
            "max_turns": evaluator_harness.MAX_TURNS,
            "acceptance_score": acceptance_score,
            "completed_at_utc": utc_now(),
            "summary": {
                "total": len(results),
                "passed": passed_count,
                "failed": failed_count,
                "errors": error_count,
                "all_passed": failed_count == 0,
            },
            "results": results,
        }

        save_json(args.output, payload)

        print("=" * 72)
        print(
            f"RESULT: {passed_count}/{len(results)} tests passed "
            f"({failed_count} failed, {error_count} runtime error(s))"
        )
        print(f"Saved: {args.output}")
        print("=" * 72)

        return 0 if failed_count == 0 else 2

    except Exception as exc:
        print()
        print("=" * 72)
        print("REFINER TEST HARNESS FAILED")
        print("=" * 72)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
