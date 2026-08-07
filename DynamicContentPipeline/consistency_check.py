from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PIPELINE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_ROOT.parent
PROMPT_PATH = PIPELINE_ROOT / "prompts" / "critic.md"
INITIAL_ROOT = PIPELINE_ROOT / "outputs" / "initial"
FINAL_ROOT = PIPELINE_ROOT / "outputs" / "final"
CRITIC_ROOT = PIPELINE_ROOT / "outputs" / "critic"
FINAL_VALIDATION_ROOT = CRITIC_ROOT / "final_validation"

CRITIC_VERSION = "1.2"
MODEL = os.environ.get("CLAUDE_AGENT_MODEL", "sonnet")
TIMEOUT_SECONDS = int(os.environ.get("CLAUDE_AGENT_TIMEOUT_SECONDS", "900"))

ISSUE_CATEGORIES = [
    "unsupported_claim",
    "contradiction",
    "overstatement",
    "omitted_limitation",
    "misleading_strategy",
    "tone_drift",
]

CRITIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["pass", "revise"],
        },
        "content_id": {"type": "string"},
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ISSUE_CATEGORIES,
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "problematic_claim": {"type": "string"},
                    "evidence_chunk_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "explanation": {"type": "string"},
                    "revision_instruction": {"type": "string"},
                },
                "required": [
                    "category",
                    "severity",
                    "problematic_claim",
                    "evidence_chunk_ids",
                    "explanation",
                    "revision_instruction",
                ],
            },
        },
    },
    "required": ["verdict", "content_id", "summary", "issues"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_critic_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Critic prompt not found: {PROMPT_PATH}") from exc


def build_prompt(
    base_prompt: str,
    item: dict[str, Any],
    candidate_text: str,
    candidate_reason: str,
) -> str:
    evidence = item["retrieval"]["chunks"]

    payload = {
        "content_id": item["id"],
        "label": item["label"],
        "query": item["query"],
        "content_requirements": item["content_requirements"],
        "max_words": item["max_words"],
        "generated_text": candidate_text,
        "generation_reason": candidate_reason,
        "retrieved_gdd_evidence": evidence,
    }

    return (
        base_prompt.rstrip()
        + "\n\n# Review Package\n\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
        + "\n\n# Output Contract\n\n"
        + "Set `content_id` exactly to the supplied content_id. "
          "If the text is faithful, return verdict `pass` and an empty issues array. "
          "If revision is needed, return verdict `revise` and include only concrete, "
          "evidence-grounded issues. Do not rewrite the complete tooltip/tutorial/hint.\n"
    )


def run_claude(prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    schema = json.dumps(
        CRITIC_SCHEMA,
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
        "2",
        "--permission-mode",
        "dontAsk",
        "--tools",
        "",
        "--disallowedTools",
        "mcp__*",
        "--json-schema",
        schema,
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
            f"Claude critic exceeded {TIMEOUT_SECONDS} seconds."
        ) from exc

    duration = round(time.monotonic() - timer, 2)

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            f"Claude critic failed with exit code {process.returncode}.\n{error_text}"
        )

    try:
        wrapper = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Claude critic returned output that was not valid wrapper JSON."
        ) from exc

    structured = wrapper.get("structured_output")
    if not isinstance(structured, dict):
        raise RuntimeError(
            "Claude critic did not return structured_output matching the schema."
        )

    metadata = {
        "model": MODEL,
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "duration_seconds": duration,
        "session_id": wrapper.get("session_id"),
        "num_turns": wrapper.get("num_turns"),
    }

    return structured, metadata



def run_validated_critic(
    prompt: str,
    item: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Run the critic and validate its structured response.

    Claude occasionally returns a schema-shaped wrapper with malformed field
    contents (for example, serializing the entire JSON object into content_id).
    Retry once with an explicit repair instruction instead of aborting the
    whole validation set.
    """
    first_result, first_metadata = run_claude(prompt)

    try:
        validate_critic(first_result, item)
        first_metadata["validation_retry"] = {
            "required": False,
        }
        return first_result, first_metadata
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        first_error = str(exc)

    repair_prompt = (
        prompt.rstrip()
        + "\n\n# Structured Output Repair\n\n"
        + "Your previous structured response failed local validation.\n"
        + f"Validation error: {first_error}\n\n"
        + "Return a fresh response that matches the supplied JSON schema exactly. "
          "Do not serialize the entire JSON object into any string field. "
          "Set `content_id` to exactly "
        + json.dumps(item["id"])
        + ". If the verdict is `revise`, every issue must include all required "
          "fields, including `revision_instruction`. If the verdict is `pass`, "
          "`issues` must be an empty array. Re-evaluate the candidate from the "
          "same supplied evidence rather than merely copying the malformed response."
    )

    repaired_result, repair_metadata = run_claude(repair_prompt)

    try:
        validate_critic(repaired_result, item)
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise RuntimeError(
            "Critic structured output failed validation twice. "
            f"First error: {first_error} Second error: {exc}"
        ) from exc

    repair_metadata["validation_retry"] = {
        "required": True,
        "first_validation_error": first_error,
        "first_run": first_metadata,
    }
    return repaired_result, repair_metadata


def validate_critic(result: dict[str, Any], item: dict[str, Any]) -> None:
    if not isinstance(result, dict):
        raise RuntimeError("Critic result is not an object.")

    required_top_level = {
        "verdict",
        "content_id",
        "summary",
        "issues",
    }
    missing = required_top_level - set(result)
    if missing:
        raise RuntimeError(
            f"Critic result is missing required fields: {sorted(missing)}"
        )

    if not isinstance(result["content_id"], str):
        raise RuntimeError("Critic content_id is not a string.")

    if result["content_id"] != item["id"]:
        raise RuntimeError(
            f"Critic returned content_id {result['content_id']!r}; "
            f"expected {item['id']!r}."
        )

    if result["verdict"] not in {"pass", "revise"}:
        raise RuntimeError(
            f"Critic returned invalid verdict {result['verdict']!r}."
        )

    if not isinstance(result["summary"], str):
        raise RuntimeError("Critic summary is not a string.")

    if not isinstance(result["issues"], list):
        raise RuntimeError("Critic issues is not an array.")

    if result["verdict"] == "pass" and result["issues"]:
        raise RuntimeError("Critic returned pass with non-empty issues.")

    if result["verdict"] == "revise" and not result["issues"]:
        raise RuntimeError("Critic returned revise with no issues.")

    valid_chunk_ids = {
        chunk["chunk_id"]
        for chunk in item["retrieval"]["chunks"]
    }

    required_issue_fields = {
        "category",
        "severity",
        "problematic_claim",
        "evidence_chunk_ids",
        "explanation",
        "revision_instruction",
    }

    for issue_index, issue in enumerate(result["issues"], start=1):
        if not isinstance(issue, dict):
            raise RuntimeError(
                f"Critic issue {issue_index} is not an object."
            )

        missing_issue_fields = required_issue_fields - set(issue)
        if missing_issue_fields:
            raise RuntimeError(
                f"Critic issue {issue_index} is missing required fields: "
                f"{sorted(missing_issue_fields)}"
            )

        if issue["category"] not in ISSUE_CATEGORIES:
            raise RuntimeError(
                f"Critic issue {issue_index} has invalid category "
                f"{issue['category']!r}."
            )

        if issue["severity"] not in {"low", "medium", "high"}:
            raise RuntimeError(
                f"Critic issue {issue_index} has invalid severity "
                f"{issue['severity']!r}."
            )

        if not isinstance(issue["evidence_chunk_ids"], list):
            raise RuntimeError(
                f"Critic issue {issue_index} evidence_chunk_ids is not an array."
            )

        unknown = set(issue["evidence_chunk_ids"]) - valid_chunk_ids
        if unknown:
            raise RuntimeError(
                f"Critic cited chunks not supplied in retrieval evidence: "
                f"{sorted(unknown)}"
            )

        for string_field in (
            "problematic_claim",
            "explanation",
            "revision_instruction",
        ):
            if not isinstance(issue[string_field], str):
                raise RuntimeError(
                    f"Critic issue {issue_index} field "
                    f"{string_field!r} is not a string."
                )


def choose_items(
    initial: dict[str, Any],
    item_id: str | None,
) -> list[dict[str, Any]]:
    items = initial.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Initial output contains no items.")

    if item_id is None:
        return items

    selected = [item for item in items if item.get("id") == item_id]
    if not selected:
        available = ", ".join(item["id"] for item in items)
        raise ValueError(
            f"Unknown item {item_id!r}. Available items: {available}"
        )
    return selected


def get_candidate_fields(
    item: dict[str, Any],
    source: str,
) -> tuple[str, str]:
    if source == "initial":
        generation = item["generation"]
        return generation["text"], generation.get("reason", "")

    revision = item["revision"]
    return revision["final_text"], revision.get("reason", "")


def run_review(
    output_type: str,
    item_id: str | None,
    source: str,
) -> Path:
    if source == "initial":
        source_root = INITIAL_ROOT
    else:
        source_root = FINAL_ROOT

    source_path = source_root / f"{output_type}.json"
    source_data = load_json(source_path)
    base_prompt = load_critic_prompt()
    selected = choose_items(source_data, item_id)

    review: dict[str, Any] = {
        "schema_version": "1.0",
        "game": source_data["game"],
        "output_type": output_type,
        "review_source": source,
        "critic_version": CRITIC_VERSION,
        "critic_model": MODEL,
        "reviewed_at_utc": utc_now(),
        "reviewed_output": str(
            source_path.relative_to(REPO_ROOT)
        ).replace("\\", "/"),
        "items": [],
    }

    for item in selected:
        candidate_text, candidate_reason = get_candidate_fields(
            item,
            source,
        )

        print()
        print("=" * 72)
        print(f"Critiquing: {item['id']} — {item['label']}")
        print(f"Source: {source}")
        print(f"Candidate: {candidate_text}")
        print("=" * 72)

        prompt = build_prompt(
            base_prompt,
            item,
            candidate_text,
            candidate_reason,
        )
        critic, metadata = run_validated_critic(prompt, item)

        print(f"Verdict: {critic['verdict']}")
        print(f"Summary: {critic['summary']}")
        for index, issue in enumerate(critic["issues"], start=1):
            print(
                f"  {index}. [{issue['severity']}] "
                f"{issue['category']}: {issue['problematic_claim']}"
            )
            print(f"     {issue['explanation']}")
            print(f"     Revision: {issue['revision_instruction']}")

        review["items"].append(
            {
                "id": item["id"],
                "label": item["label"],
                "query": item["query"],
                "candidate_text": candidate_text,
                "retrieval": item["retrieval"],
                "critic": critic,
                "run_metadata": metadata,
            }
        )

    if source == "initial":
        filename = (
            f"{output_type}_{item_id}_critic.json"
            if item_id
            else f"{output_type}_critic.json"
        )
        output_path = CRITIC_ROOT / filename
        report_to_save = review
    else:
        output_path = (
            FINAL_VALIDATION_ROOT
            / f"{output_type}_final_critic.json"
        )

        if item_id and output_path.exists():
            existing = load_json(output_path)
            existing_items = {
                item["id"]: item
                for item in existing.get("items", [])
            }

            for reviewed_item in review["items"]:
                existing_items[reviewed_item["id"]] = reviewed_item

            ordered_ids = [
                item["id"]
                for item in source_data["items"]
            ]

            merged_items = [
                existing_items[current_id]
                for current_id in ordered_ids
                if current_id in existing_items
            ]

            report_to_save = existing
            report_to_save.update(
                {
                    "schema_version": review["schema_version"],
                    "game": review["game"],
                    "output_type": review["output_type"],
                    "review_source": review["review_source"],
                    "critic_version": review["critic_version"],
                    "critic_model": review["critic_model"],
                    "reviewed_at_utc": review["reviewed_at_utc"],
                    "reviewed_output": review["reviewed_output"],
                    "items": merged_items,
                }
            )
        else:
            report_to_save = review

    save_json(output_path, report_to_save)

    revise_count = sum(
        1
        for item in report_to_save["items"]
        if item["critic"]["verdict"] == "revise"
    )
    pass_count = len(report_to_save["items"]) - revise_count

    print()
    print(f"Saved: {output_path.relative_to(REPO_ROOT)}")
    print(f"Summary: {revise_count} revise, {pass_count} pass")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Review generated No Safe Circle content against the exact "
            "canonical GDD chunks used to generate it."
        )
    )
    parser.add_argument(
        "--output-type",
        required=True,
        choices=["spell_tooltips", "door_tutorial", "failure_hints"],
    )
    parser.add_argument(
        "--item",
        default=None,
        help="Review only one generated item ID",
    )
    parser.add_argument(
        "--source",
        choices=["initial", "final"],
        default="initial",
        help=(
            "Review the original generated content or the revised final content. "
            "Default: initial"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        run_review(args.output_type, args.item, args.source)
        return 0
    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("CONSISTENCY CRITIC FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
