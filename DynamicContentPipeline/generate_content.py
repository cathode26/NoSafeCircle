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
REQUEST_ROOT = PIPELINE_ROOT / "content_requests"
PROMPT_ROOT = PIPELINE_ROOT / "prompts"
OUTPUT_ROOT = PIPELINE_ROOT / "outputs" / "initial"
RUN_LOG_PATH = PIPELINE_ROOT / "outputs" / "generation_run_log.json"
KNOWLEDGE_BASE_PATH = (
    PIPELINE_ROOT
    / "knowledge_base"
    / "No_Safe_Circle_GDD_RAG.json"
)

sys.path.insert(0, str(PIPELINE_ROOT))

from retrieval import GDDRetriever, RETRIEVER_VERSION  # noqa: E402

GENERATOR_VERSION = "1.1"
MODEL = os.environ.get("CLAUDE_AGENT_MODEL", "sonnet")
TIMEOUT_SECONDS = int(
    os.environ.get("CLAUDE_AGENT_TIMEOUT_SECONDS", "900")
)

GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": ["generated", "insufficient_context"],
        },
        "content_id": {"type": "string"},
        "label": {"type": "string"},
        "text": {"type": "string"},
        "reason": {"type": "string"},
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


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc


def load_prompt() -> str:
    path = PROMPT_ROOT / "generator.md"
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Generator prompt not found: {path}") from exc


def request_path(request_name: str) -> Path:
    return REQUEST_ROOT / f"{request_name}.json"


def serialize_retrieval(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []

    for rank, result in enumerate(results, start=1):
        serialized.append(
            {
                "rank": rank,
                "chunk_id": result["chunk_id"],
                "title": result["title"],
                "section": result["section"],
                "subsection": result.get("subsection"),
                "domain": result["domain"],
                "canonical": result["canonical"],
                "score": result["score"],
                "query_coverage": result.get("query_coverage"),
                "matched_terms": result.get("matched_terms", []),
                "matched_phrases": result.get("matched_phrases", []),
                "source": result["source"],
                "text": result["text"],
            }
        )

    return serialized


def build_generation_prompt(
    base_prompt: str,
    request: dict[str, Any],
    item: dict[str, Any],
    retrieved_chunks: list[dict[str, Any]],
) -> str:
    evidence = serialize_retrieval(retrieved_chunks)

    task_payload = {
        "game": request["game"],
        "output_type": request["output_type"],
        "game_gap": request["game_gap"],
        "content_item": {
            "id": item["id"],
            "label": item["label"],
            "trigger": item.get("trigger"),
            "query": item["query"],
            "content_requirements": item["content_requirements"],
            "max_words": item["max_words"],
        },
        "retrieved_gdd_evidence": evidence,
    }

    return (
        base_prompt.rstrip()
        + "\n\n# Current Content Item\n\n"
        + "The following JSON is the complete evidence package for this item. "
          "Do not use outside game facts.\n\n"
        + json.dumps(task_payload, indent=2, ensure_ascii=False)
        + "\n\n# Output Contract\n\n"
        + "Return status `generated` when the evidence supports the requested "
          "content. Set `content_id` and `label` exactly to the supplied values. "
          "Place only the player-facing copy in `text`. Keep `text` within the "
          f"{item['max_words']}-word limit. Set `reason` to a short evidence-based "
          "explanation of why the output is supported. If evidence is insufficient, "
          "return status `insufficient_context`, an empty `text`, and explain the "
          "missing support in `reason`.\n"
    )



def build_length_repair_prompt(
    original_prompt: str,
    generated: dict[str, Any],
    item: dict[str, Any],
    actual_word_count: int,
) -> str:
    return (
        original_prompt.rstrip()
        + "\n\n# Length Repair\n\n"
        + "Your previous candidate exceeded the allowed player-facing word count. "
          "Revise only for concision. Preserve the same supported mechanics and "
          "limitations, do not add new claims, and do not omit a required limitation.\n\n"
        + f"Maximum words: {item['max_words']}\n"
        + f"Previous word count: {actual_word_count}\n"
        + "Previous structured output:\n"
        + json.dumps(generated, indent=2, ensure_ascii=False)
        + "\n\nReturn a corrected structured JSON object using the same output contract.\n"
    )


def run_claude(prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    compact_schema = json.dumps(
        GENERATION_SCHEMA,
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
        compact_schema,
        "--input-format",
        "text",
    ]

    started_at = utc_now()
    started_timer = time.monotonic()

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
            f"Claude generation exceeded {TIMEOUT_SECONDS} seconds."
        ) from exc

    duration = round(time.monotonic() - started_timer, 2)

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            f"Claude failed with exit code {process.returncode}.\n{error_text}"
        )

    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Claude returned output that was not valid wrapper JSON."
        ) from exc

    structured = payload.get("structured_output")
    if not isinstance(structured, dict):
        raise RuntimeError(
            "Claude did not return structured_output matching the schema."
        )

    run_metadata = {
        "model": MODEL,
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "duration_seconds": duration,
        "session_id": payload.get("session_id"),
        "num_turns": payload.get("num_turns"),
    }

    return structured, run_metadata


def validate_generated_item(
    generated: dict[str, Any],
    item: dict[str, Any],
) -> int:
    if generated["content_id"] != item["id"]:
        raise RuntimeError(
            f"Claude returned content_id {generated['content_id']!r}; "
            f"expected {item['id']!r}."
        )

    if generated["label"] != item["label"]:
        raise RuntimeError(
            f"Claude returned label {generated['label']!r}; "
            f"expected {item['label']!r}."
        )

    if generated["status"] != "generated":
        return 0

    return len(generated["text"].split())


def choose_items(
    request: dict[str, Any],
    item_id: str | None,
) -> list[dict[str, Any]]:
    items = request.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Request file must contain a non-empty items array")

    if item_id is None:
        return items

    matches = [item for item in items if item.get("id") == item_id]
    if not matches:
        available = ", ".join(item["id"] for item in items)
        raise ValueError(
            f"Unknown item {item_id!r}. Available items: {available}"
        )

    return matches


def make_item_record(
    *,
    request: dict[str, Any],
    item: dict[str, Any],
    retrieval_results: list[dict[str, Any]],
    generation: dict[str, Any] | None,
    run_metadata: dict[str, Any] | None,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "id": item["id"],
        "label": item["label"],
        "trigger": item.get("trigger"),
        "query": item["query"],
        "top_k": item.get("top_k", 4),
        "content_requirements": item["content_requirements"],
        "max_words": item["max_words"],
        "retrieval": {
            "retriever_version": RETRIEVER_VERSION,
            "chunks": serialize_retrieval(retrieval_results),
        },
        "generation": (
            {
                "status": "dry_run",
                "text": "",
                "reason": "Claude was not invoked.",
            }
            if dry_run
            else generation
        ),
        "run_metadata": run_metadata,
    }


def save_run_log_entry(entry: dict[str, Any]) -> None:
    if RUN_LOG_PATH.exists():
        log = load_json(RUN_LOG_PATH)
    else:
        log = {
            "game": "No Safe Circle",
            "pipeline": "Dynamic Content Pipeline",
            "runs": [],
        }

    log["runs"].append(entry)
    save_json(RUN_LOG_PATH, log)


def run_request(
    request_name: str,
    item_id: str | None,
    dry_run: bool,
) -> Path:
    request = load_json(request_path(request_name))
    base_prompt = load_prompt()
    retriever = GDDRetriever(KNOWLEDGE_BASE_PATH)
    selected_items = choose_items(request, item_id)

    output: dict[str, Any] = {
        "schema_version": "1.0",
        "game": request["game"],
        "output_type": request["output_type"],
        "game_gap": request["game_gap"],
        "retriever_version": RETRIEVER_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generator_model": None if dry_run else MODEL,
        "generated_at_utc": utc_now(),
        "dry_run": dry_run,
        "items": [],
    }

    for item in selected_items:
        print()
        print("=" * 72)
        print(f"Content item: {item['id']} — {item['label']}")
        print(f"Query: {item['query']}")
        print("=" * 72)

        retrieval_results = retriever.retrieve(
            item["query"],
            top_k=int(item.get("top_k", 4)),
        )

        print("Retrieved:")
        for rank, result in enumerate(retrieval_results, start=1):
            print(
                f"  {rank}. {result['chunk_id']} | "
                f"{result['title']} | score={result['score']}"
            )

        generation: dict[str, Any] | None = None
        run_metadata: dict[str, Any] | None = None

        if dry_run:
            print("Dry run: Claude not invoked.")
        else:
            prompt = build_generation_prompt(
                base_prompt,
                request,
                item,
                retrieval_results,
            )
            generation, run_metadata = run_claude(prompt)
            word_count = validate_generated_item(generation, item)

            if (
                generation["status"] == "generated"
                and word_count > int(item["max_words"])
            ):
                print(
                    f"Generated text exceeded max_words: "
                    f"{word_count} > {item['max_words']}; retrying once for length."
                )
                repair_prompt = build_length_repair_prompt(
                    prompt,
                    generation,
                    item,
                    word_count,
                )
                repaired_generation, repair_metadata = run_claude(repair_prompt)
                repaired_word_count = validate_generated_item(
                    repaired_generation,
                    item,
                )
                if (
                    repaired_generation["status"] == "generated"
                    and repaired_word_count > int(item["max_words"])
                ):
                    raise RuntimeError(
                        f"Length repair still exceeded max_words: "
                        f"{repaired_word_count} > {item['max_words']}"
                    )

                generation = repaired_generation
                run_metadata["length_repair"] = {
                    "required": True,
                    "original_word_count": word_count,
                    "max_words": item["max_words"],
                    "repair_run": repair_metadata,
                }
            else:
                run_metadata["length_repair"] = {
                    "required": False,
                    "original_word_count": word_count,
                    "max_words": item["max_words"],
                }

            print(f"Claude status: {generation['status']}")
            if generation["text"]:
                print(f"Generated text: {generation['text']}")
                print(f"Word count: {len(generation['text'].split())}/{item['max_words']}")
            print(f"Reason: {generation['reason']}")

        output["items"].append(
            make_item_record(
                request=request,
                item=item,
                retrieval_results=retrieval_results,
                generation=generation,
                run_metadata=run_metadata,
                dry_run=dry_run,
            )
        )

    output_filename = (
        f"{request['output_type']}_dry_run.json"
        if dry_run
        else f"{request['output_type']}.json"
    )
    output_path = OUTPUT_ROOT / output_filename
    save_json(output_path, output)

    save_run_log_entry(
        {
            "request": request_name,
            "generator_version": GENERATOR_VERSION,
            "item_filter": item_id,
            "dry_run": dry_run,
            "model": None if dry_run else MODEL,
            "completed_at_utc": utc_now(),
            "output": str(output_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "item_count": len(selected_items),
        }
    )

    print()
    print(f"Saved: {output_path.relative_to(REPO_ROOT)}")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Retrieve canonical No Safe Circle GDD evidence and generate "
            "player-facing content with Claude."
        )
    )
    parser.add_argument(
        "--request",
        required=True,
        choices=[
            "spell_tooltips",
            "door_tutorial",
            "failure_hints",
        ],
    )
    parser.add_argument(
        "--item",
        default=None,
        help="Generate only one item ID from the request file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run retrieval and save evidence without invoking Claude",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        run_request(
            request_name=args.request,
            item_id=args.item,
            dry_run=args.dry_run,
        )
        return 0
    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("GENERATION PIPELINE FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
