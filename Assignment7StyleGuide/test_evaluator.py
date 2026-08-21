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
EVALUATOR_PROMPT_PATH = A7_ROOT / "prompts" / "evaluator.md"
SCHEMA_PATH = A7_ROOT / "evaluator_schema.json"
DEFAULT_CASES_PATH = A7_ROOT / "test_cases" / "evaluator_smoke_tests.json"
OUTPUT_PATH = A7_ROOT / "outputs" / "tests" / "evaluator_test_results.json"

MODEL = os.environ.get("CLAUDE_AGENT_MODEL", "sonnet")
TIMEOUT_SECONDS = int(os.environ.get("CLAUDE_AGENT_TIMEOUT_SECONDS", "900"))
MAX_TURNS = int(os.environ.get("CLAUDE_AGENT_MAX_TURNS", "6"))

RULE_ID_RE = re.compile(r"^NSC-(TONE|CANON|MECH|FORMAT)-[0-9]{2}$")


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


def build_prompt(
    base_prompt: str,
    style_guide: str,
    case: dict[str, Any],
) -> str:
    review_package = {
        "content_id": case["id"],
        "label": case["label"],
        "content_type": case["content_type"],
        "max_words": case["max_words"],
        "content_requirements": case.get("content_requirements", []),
        "task_context": case.get("task_context", {}),
        "candidate_text": case["candidate_text"],
    }

    return (
        base_prompt.rstrip()
        + "\n\n# Supplied No Safe Circle Style Guide\n\n"
        + style_guide.rstrip()
        + "\n\n# Current Evaluation Package\n\n"
        + json.dumps(review_package, indent=2, ensure_ascii=False)
        + "\n\n# Final Instruction\n\n"
        + "Evaluate only the supplied candidate. Return the structured JSON "
          "object required by the output contract. Do not rewrite the candidate.\n"
    )


def run_claude(prompt: str, schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    compact_schema = json.dumps(schema, separators=(",", ":"), ensure_ascii=False)

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
            f"Claude evaluator exceeded {TIMEOUT_SECONDS} seconds."
        ) from exc

    duration = round(time.monotonic() - timer, 2)

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            f"Claude evaluator failed with exit code {process.returncode}.\n"
            f"{error_text}"
        )

    try:
        wrapper = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Claude returned output that was not valid wrapper JSON."
        ) from exc

    structured = wrapper.get("structured_output")
    if not isinstance(structured, dict):
        raise RuntimeError(
            "Claude did not return structured_output matching the supplied schema."
        )

    metadata = {
        "model": MODEL,
        "max_turns": MAX_TURNS,
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "duration_seconds": duration,
        "session_id": wrapper.get("session_id"),
        "num_turns": wrapper.get("num_turns"),
    }

    return structured, metadata


def validate_result_shape(result: dict[str, Any], expected_id: str) -> list[str]:
    errors: list[str] = []

    if result.get("content_id") != expected_id:
        errors.append(
            f"content_id was {result.get('content_id')!r}; expected {expected_id!r}"
        )

    score = result.get("score")
    if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 10:
        errors.append(f"score must be an integer from 1–10; got {score!r}")

    reason = result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append("reason must be a non-empty string")

    violations = result.get("violations")
    if not isinstance(violations, list):
        errors.append("violations must be an array")
        return errors

    if score == 10 and violations:
        errors.append("score 10 must have an empty violations array")

    if isinstance(score, int) and score < 10 and not violations:
        errors.append("score below 10 must include at least one violation")

    for index, violation in enumerate(violations, start=1):
        if not isinstance(violation, dict):
            errors.append(f"violation #{index} must be an object")
            continue

        rule_id = violation.get("rule_id")
        if not isinstance(rule_id, str) or not RULE_ID_RE.fullmatch(rule_id):
            errors.append(
                f"violation #{index} has invalid rule_id {rule_id!r}"
            )

        severity = violation.get("severity")
        if severity not in {"minor", "meaningful", "major"}:
            errors.append(
                f"violation #{index} has invalid severity {severity!r}"
            )

        for key in ("problematic_text", "explanation", "revision_instruction"):
            value = violation.get(key)
            if not isinstance(value, str):
                errors.append(
                    f"violation #{index} field {key!r} must be a string"
                )
            elif key != "problematic_text" and not value.strip():
                errors.append(
                    f"violation #{index} field {key!r} must not be empty"
                )

    return errors


def evaluate_expectation(
    result: dict[str, Any],
    expectation: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    score = result["score"]
    violations = result["violations"]
    rule_ids = {
        item.get("rule_id")
        for item in violations
        if isinstance(item, dict)
    }

    min_score = expectation.get("min_score")
    if isinstance(min_score, int) and score < min_score:
        errors.append(
            f"score {score} is below expected minimum {min_score}"
        )

    max_score = expectation.get("max_score")
    if isinstance(max_score, int) and score > max_score:
        errors.append(
            f"score {score} is above expected maximum {max_score}"
        )

    min_violations = expectation.get("min_violations")
    if isinstance(min_violations, int) and len(violations) < min_violations:
        errors.append(
            f"expected at least {min_violations} violation(s); got {len(violations)}"
        )

    max_violations = expectation.get("max_violations")
    if isinstance(max_violations, int) and len(violations) > max_violations:
        errors.append(
            f"expected at most {max_violations} violation(s); got {len(violations)}"
        )

    required_any = expectation.get("required_any_rule_ids", [])
    if required_any and not any(rule_id in rule_ids for rule_id in required_any):
        errors.append(
            "expected at least one of these rule IDs: "
            + ", ".join(required_any)
            + "; evaluator returned: "
            + (", ".join(sorted(str(x) for x in rule_ids if x)) or "(none)")
        )

    forbidden = expectation.get("forbidden_rule_ids", [])
    found_forbidden = [rule_id for rule_id in forbidden if rule_id in rule_ids]
    if found_forbidden:
        errors.append(
            "returned forbidden rule ID(s): " + ", ".join(found_forbidden)
        )

    return errors


def run_case(
    case: dict[str, Any],
    base_prompt: str,
    style_guide: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    prompt = build_prompt(base_prompt, style_guide, case)
    result, metadata = run_claude(prompt, schema)

    shape_errors = validate_result_shape(result, case["id"])
    expectation_errors: list[str] = []

    if not shape_errors:
        expectation_errors = evaluate_expectation(
            result,
            case.get("expectation", {}),
        )

    passed = not shape_errors and not expectation_errors

    return {
        "case_id": case["id"],
        "label": case["label"],
        "candidate_text": case["candidate_text"],
        "expectation": case.get("expectation", {}),
        "evaluator": result,
        "metadata": metadata,
        "shape_errors": shape_errors,
        "expectation_errors": expectation_errors,
        "status": "pass" if passed else "fail",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test the Assignment 7 No Safe Circle Style Evaluator "
            "before wiring it to the Refiner."
        )
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to evaluator smoke-test JSON.",
    )
    parser.add_argument(
        "--case",
        default=None,
        help="Run only one case ID instead of the full suite.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Where to save the combined evaluator test results.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        base_prompt = load_text(EVALUATOR_PROMPT_PATH)
        style_guide = load_text(STYLE_GUIDE_PATH)
        schema = load_json(SCHEMA_PATH)
        suite = load_json(args.cases)

        cases = suite.get("cases")
        if not isinstance(cases, list) or not cases:
            raise RuntimeError("Test suite contains no cases.")

        if args.case:
            cases = [case for case in cases if case.get("id") == args.case]
            if not cases:
                raise RuntimeError(f"Unknown test case: {args.case!r}")

        print()
        print("=" * 72)
        print("ASSIGNMENT 7 — STYLE EVALUATOR SMOKE TESTS")
        print("=" * 72)
        print(f"Model: {MODEL}")
        print(f"Max turns per evaluator call: {MAX_TURNS}")
        print(f"Cases: {len(cases)}")
        print()

        results: list[dict[str, Any]] = []

        for index, case in enumerate(cases, start=1):
            print(f"[{index}/{len(cases)}] {case['id']} — {case['label']}")

            try:
                case_result = run_case(
                    case,
                    base_prompt,
                    style_guide,
                    schema,
                )
            except Exception as exc:
                case_result = {
                    "case_id": case["id"],
                    "label": case["label"],
                    "candidate_text": case["candidate_text"],
                    "expectation": case.get("expectation", {}),
                    "evaluator": None,
                    "metadata": {
                        "model": MODEL,
                        "max_turns": MAX_TURNS,
                    },
                    "shape_errors": [],
                    "expectation_errors": [],
                    "runtime_error": str(exc),
                    "status": "error",
                }
                results.append(case_result)
                print(f"  TEST: ERROR")
                print(f"    Runtime error: {exc}")
                print()
                continue

            results.append(case_result)

            evaluation = case_result["evaluator"]
            print(
                f"  Score: {evaluation.get('score')}/10 | "
                f"Violations: {len(evaluation.get('violations', []))}"
            )
            print(f"  Reason: {evaluation.get('reason')}")
            print(f"  TEST: {case_result['status'].upper()}")

            for error in case_result["shape_errors"]:
                print(f"    Shape error: {error}")
            for error in case_result["expectation_errors"]:
                print(f"    Expectation error: {error}")

            print()

        passed_count = sum(item["status"] == "pass" for item in results)
        error_count = sum(item["status"] == "error" for item in results)
        failed_count = len(results) - passed_count

        payload = {
            "suite": suite.get("suite", "Assignment 7 Style Evaluator Smoke Tests"),
            "game": "No Safe Circle",
            "model": MODEL,
            "started_from": str(args.cases),
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
        print("EVALUATOR TEST HARNESS FAILED")
        print("=" * 72)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
