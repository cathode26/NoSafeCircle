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

PIPELINE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_ROOT.parent
PROMPT_PATH = PIPELINE_ROOT / "prompts" / "revisor.md"
INITIAL_ROOT = PIPELINE_ROOT / "outputs" / "initial"
CRITIC_ROOT = PIPELINE_ROOT / "outputs" / "critic"
FINAL_ROOT = PIPELINE_ROOT / "outputs" / "final"
FINAL_VALIDATION_ROOT = CRITIC_ROOT / "final_validation"

REVISOR_VERSION = "1.2"
MODEL = os.environ.get("CLAUDE_AGENT_MODEL", "sonnet")
TIMEOUT_SECONDS = int(os.environ.get("CLAUDE_AGENT_TIMEOUT_SECONDS", "900"))

REVISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": ["revised"],
        },
        "content_id": {"type": "string"},
        "label": {"type": "string"},
        "text": {"type": "string"},
        "changes_made": {
            "type": "array",
            "items": {"type": "string"},
        },
        "reason": {"type": "string"},
    },
    "required": [
        "status",
        "content_id",
        "label",
        "text",
        "changes_made",
        "reason",
    ],
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


def load_revisor_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Revisor prompt not found: {PROMPT_PATH}") from exc


def get_candidate_text(item: dict[str, Any], source: str) -> str:
    if source == "initial":
        return item["generation"]["text"]
    return item["revision"]["final_text"]


def build_revision_prompt(
    base_prompt: str,
    source_item: dict[str, Any],
    critic_item: dict[str, Any],
    source: str,
) -> str:
    original_text = get_candidate_text(source_item, source)

    payload = {
        "content_id": source_item["id"],
        "label": source_item["label"],
        "query": source_item["query"],
        "content_requirements": source_item["content_requirements"],
        "max_words": source_item["max_words"],
        "original_text": original_text,
        "retrieved_gdd_evidence": source_item["retrieval"]["chunks"],
        "critic_verdict": critic_item["critic"]["verdict"],
        "critic_summary": critic_item["critic"]["summary"],
        "critic_issues": critic_item["critic"]["issues"],
        "revision_source": source,
    }

    refinement_note = ""
    if source == "final":
        refinement_note = (
            "\nThis is a second-pass refinement of already revised content. "
            "Preserve corrections that are already faithful. Fix the current "
            "critic issue without reintroducing earlier errors. Also obey all "
            "global evidence-preservation rules in the revisor prompt, even if "
            "the current critic does not repeat every previously learned constraint.\n"
        )

    return (
        base_prompt.rstrip()
        + "\n\n# Revision Package\n\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
        + "\n\n# Output Contract\n\n"
        + refinement_note
        + "Set `content_id` and `label` exactly to the supplied values. "
          "Return only the corrected player-facing copy in `text`. "
          f"Keep `text` at or below {source_item['max_words']} words. "
          "List the specific corrections you made in `changes_made`. "
          "Use `reason` to explain briefly how the revision now matches the supplied evidence.\n"
    )


def build_length_repair_prompt(
    original_prompt: str,
    result: dict[str, Any],
    max_words: int,
    word_count: int,
) -> str:
    return (
        original_prompt.rstrip()
        + "\n\n# Length Repair\n\n"
        + f"The revised text is {word_count} words, but the maximum is {max_words}. "
          "Shorten it without undoing any critic correction, dropping a required "
          "limitation, or adding new claims.\n\n"
        + "Previous structured output:\n"
        + json.dumps(result, indent=2, ensure_ascii=False)
        + "\n\nReturn corrected structured JSON using the same schema.\n"
    )


def run_claude(prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    schema = json.dumps(
        REVISION_SCHEMA,
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
            f"Claude revision exceeded {TIMEOUT_SECONDS} seconds."
        ) from exc

    duration = round(time.monotonic() - timer, 2)

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            f"Claude revisor failed with exit code {process.returncode}.\n{error_text}"
        )

    try:
        wrapper = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Claude revisor returned output that was not valid wrapper JSON."
        ) from exc

    structured = wrapper.get("structured_output")
    if not isinstance(structured, dict):
        raise RuntimeError(
            "Claude revisor did not return structured_output matching the schema."
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



_STRAY_CLAUDE_TAG_RE = re.compile(
    r"</?(?:reason|invoke)>",
    flags=re.IGNORECASE,
)


def clean_revision_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """
    Remove known Claude wrapper-tag leakage from non-player-facing metadata.

    Player-facing `text` is never silently modified. If wrapper tags appear
    there, validation fails so the item can be regenerated instead.
    """
    cleaned = dict(result)

    reason = cleaned.get("reason")
    if isinstance(reason, str):
        cleaned["reason"] = _STRAY_CLAUDE_TAG_RE.sub("", reason).strip()

    changes = cleaned.get("changes_made")
    if isinstance(changes, list):
        cleaned["changes_made"] = [
            _STRAY_CLAUDE_TAG_RE.sub("", change).strip()
            if isinstance(change, str)
            else change
            for change in changes
        ]

    return cleaned


def validate_revision(
    result: dict[str, Any],
    source_item: dict[str, Any],
) -> int:
    if result["content_id"] != source_item["id"]:
        raise RuntimeError(
            f"Revisor returned content_id {result['content_id']!r}; "
            f"expected {source_item['id']!r}."
        )

    if result["label"] != source_item["label"]:
        raise RuntimeError(
            f"Revisor returned label {result['label']!r}; "
            f"expected {source_item['label']!r}."
        )

    player_text = result["text"]
    if _STRAY_CLAUDE_TAG_RE.search(player_text):
        raise RuntimeError(
            "Revisor leaked wrapper tags into player-facing text; "
            "refusing to silently modify final content."
        )

    return len(player_text.split())


def index_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in items}


def run_revision(
    output_type: str,
    item_id: str | None,
    source: str,
) -> Path:
    if source == "initial":
        source_path = INITIAL_ROOT / f"{output_type}.json"
        critic_path = CRITIC_ROOT / f"{output_type}_critic.json"
    else:
        source_path = FINAL_ROOT / f"{output_type}.json"
        critic_path = (
            FINAL_VALIDATION_ROOT
            / f"{output_type}_final_critic.json"
        )

    source_data = load_json(source_path)
    critic = load_json(critic_path)
    base_prompt = load_revisor_prompt()

    source_items = index_by_id(source_data["items"])
    critic_items = index_by_id(critic["items"])

    if set(source_items) != set(critic_items):
        raise RuntimeError(
            "Source and critic files contain different item IDs."
        )

    selected_ids = [item_id] if item_id else list(source_items.keys())

    for selected_id in selected_ids:
        if selected_id not in source_items:
            available = ", ".join(source_items)
            raise ValueError(
                f"Unknown item {selected_id!r}. Available: {available}"
            )

    if source == "initial":
        final: dict[str, Any] = {
            "schema_version": "1.0",
            "game": source_data["game"],
            "output_type": output_type,
            "source_initial_output": str(
                source_path.relative_to(REPO_ROOT)
            ).replace("\\", "/"),
            "source_critic_output": str(
                critic_path.relative_to(REPO_ROOT)
            ).replace("\\", "/"),
            "revisor_version": REVISOR_VERSION,
            "revisor_model": MODEL,
            "revised_at_utc": utc_now(),
            "items": [],
        }
    else:
        # Deep-copy the current full final file so targeted refinements update
        # one item without dropping all of the already-passing items.
        final = json.loads(json.dumps(source_data))
        final["revisor_version"] = REVISOR_VERSION
        final["revisor_model"] = MODEL
        final["revised_at_utc"] = utc_now()
        final["source_final_validation_critic"] = str(
            critic_path.relative_to(REPO_ROOT)
        ).replace("\\", "/")

    final_items = index_by_id(final["items"]) if source == "final" else {}

    revised_count = 0
    unchanged_count = 0

    for current_id in selected_ids:
        source_item = source_items[current_id]
        critic_item = critic_items[current_id]
        verdict = critic_item["critic"]["verdict"]
        candidate_text = get_candidate_text(source_item, source)

        print()
        print("=" * 72)
        print(f"Revising: {current_id} — {source_item['label']}")
        print(f"Revision source: {source}")
        print(f"Critic verdict: {verdict}")
        print(f"Current text: {candidate_text}")
        print("=" * 72)

        if verdict == "pass":
            print("No revision required; preserving current text.")
            unchanged_count += 1

            if source == "initial":
                revision_record = {
                    "revision_required": False,
                    "original_text": candidate_text,
                    "final_text": candidate_text,
                    "critic_verdict": "pass",
                    "critic_issues": [],
                    "changes_made": [],
                    "reason": "Critic passed the original text unchanged.",
                    "run_metadata": None,
                }

                final["items"].append(
                    {
                        "id": source_item["id"],
                        "label": source_item["label"],
                        "trigger": source_item.get("trigger"),
                        "query": source_item["query"],
                        "content_requirements": source_item[
                            "content_requirements"
                        ],
                        "max_words": source_item["max_words"],
                        "retrieval": source_item["retrieval"],
                        "revision": revision_record,
                    }
                )
            continue

        prompt = build_revision_prompt(
            base_prompt,
            source_item,
            critic_item,
            source,
        )
        revised, metadata = run_claude(prompt)
        revised = clean_revision_metadata(revised)
        word_count = validate_revision(revised, source_item)

        if word_count > int(source_item["max_words"]):
            print(
                f"Revision exceeded max_words: "
                f"{word_count} > {source_item['max_words']}; "
                "retrying once for length."
            )
            repair_prompt = build_length_repair_prompt(
                prompt,
                revised,
                int(source_item["max_words"]),
                word_count,
            )
            repaired, repair_metadata = run_claude(repair_prompt)
            repaired = clean_revision_metadata(repaired)
            repaired_count = validate_revision(
                repaired,
                source_item,
            )
            if repaired_count > int(source_item["max_words"]):
                raise RuntimeError(
                    f"Length repair still exceeded max_words: "
                    f"{repaired_count} > {source_item['max_words']}"
                )
            revised = repaired
            metadata["length_repair"] = {
                "required": True,
                "original_word_count": word_count,
                "max_words": source_item["max_words"],
                "repair_run": repair_metadata,
            }
        else:
            metadata["length_repair"] = {
                "required": False,
                "original_word_count": word_count,
                "max_words": source_item["max_words"],
            }

        print(f"Revised: {revised['text']}")
        print(
            f"Word count: "
            f"{len(revised['text'].split())}/{source_item['max_words']}"
        )
        for change in revised["changes_made"]:
            print(f"  - {change}")

        revised_count += 1

        if source == "initial":
            revision_record = {
                "revision_required": True,
                "original_text": candidate_text,
                "final_text": revised["text"],
                "critic_verdict": "revise",
                "critic_issues": critic_item["critic"]["issues"],
                "changes_made": revised["changes_made"],
                "reason": revised["reason"],
                "run_metadata": metadata,
            }

            final["items"].append(
                {
                    "id": source_item["id"],
                    "label": source_item["label"],
                    "trigger": source_item.get("trigger"),
                    "query": source_item["query"],
                    "content_requirements": source_item[
                        "content_requirements"
                    ],
                    "max_words": source_item["max_words"],
                    "retrieval": source_item["retrieval"],
                    "revision": revision_record,
                }
            )
        else:
            final_item = final_items[current_id]
            revision_record = final_item["revision"]

            if "original_critic_issues" not in revision_record:
                revision_record["original_critic_issues"] = list(
                    revision_record.get("critic_issues", [])
                )

            history = revision_record.setdefault(
                "refinement_history",
                [],
            )
            history.append(
                {
                    "source_critic_output": str(
                        critic_path.relative_to(REPO_ROOT)
                    ).replace("\\", "/"),
                    "previous_text": candidate_text,
                    "critic_summary": critic_item["critic"]["summary"],
                    "critic_issues": critic_item["critic"]["issues"],
                    "final_text": revised["text"],
                    "changes_made": revised["changes_made"],
                    "reason": revised["reason"],
                    "run_metadata": metadata,
                }
            )

            revision_record["revision_required"] = True
            revision_record["final_text"] = revised["text"]
            revision_record["critic_verdict"] = "revise"
            revision_record["critic_issues"] = critic_item["critic"]["issues"]
            revision_record["changes_made"] = revised["changes_made"]
            revision_record["reason"] = revised["reason"]
            revision_record["run_metadata"] = metadata

    if source == "initial":
        filename = (
            f"{output_type}_{item_id}_final.json"
            if item_id
            else f"{output_type}.json"
        )
        output_path = FINAL_ROOT / filename
    else:
        # Final-source refinements always merge back into the canonical full
        # output file, even when --item targets a single piece of content.
        output_path = FINAL_ROOT / f"{output_type}.json"

    save_json(output_path, final)

    print()
    print(f"Saved: {output_path.relative_to(REPO_ROOT)}")
    print(
        f"Summary: {revised_count} revised, "
        f"{unchanged_count} preserved unchanged"
    )
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Revise generated No Safe Circle content using the "
            "consistency critic findings."
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
        help="Revise only one item ID",
    )
    parser.add_argument(
        "--source",
        choices=["initial", "final"],
        default="initial",
        help=(
            "Revise from the original generation/critic or refine the current "
            "final output using its latest final-validation critic. Default: initial"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        run_revision(args.output_type, args.item, args.source)
        return 0
    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("CONTENT REVISION FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
