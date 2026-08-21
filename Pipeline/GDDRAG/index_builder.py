from __future__ import annotations

"""Deterministic GDD index builder.

Parses the canonical Markdown GDD into structural chunks (heading section /
table / list-item boundaries only) and writes a versioned, hash-stamped
knowledge-base JSON file. No LLM or external API call is used anywhere in
this module.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_GDD_PATH = ROOT / "Docs" / "GDD" / "No_Safe_Circle_GDD.md"
CANONICAL_GDD_RELATIVE = "Docs/GDD/No_Safe_Circle_GDD.md"
DEFAULT_KNOWLEDGE_BASE_PATH = Path(__file__).resolve().parent / "knowledge_base" / "No_Safe_Circle_GDD_RAG.json"

SCHEMA_VERSION = "2.0"
BUILDER_VERSION = "1.0"
MAX_CHUNK_CHARS = 3200
DEFAULT_TOP_K = 4
DOMAIN = "game_design"

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
FRONT_MATTER_FIELD_PATTERN = re.compile(r'^(\w+):\s*"(.*)"\s*$')
LIST_ITEM_PATTERN = re.compile(r"^\s*(?:-|\*|\d+\.)\s")


class GDDIndexError(RuntimeError):
    """Raised when the canonical GDD or a knowledge-base index cannot be trusted."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_source(path: Path = CANONICAL_GDD_PATH) -> tuple[str, list[str]]:
    if not path.is_file():
        raise GDDIndexError(f"Canonical GDD not found: {path}")
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    return text, lines


def parse_front_matter(lines: list[str]) -> dict[str, str]:
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = FRONT_MATTER_FIELD_PATTERN.match(line)
        if match:
            fields[match.group(1)] = match.group(2)
    return fields


def _front_matter_end_line(lines: list[str]) -> int:
    """1-indexed line number of the closing '---', or 0 if there is none."""
    if not lines or lines[0].strip() != "---":
        return 0
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return index + 1
    return 0


def parse_headings(lines: list[str], body_start_line: int) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    for line_no in range(body_start_line, len(lines) + 1):
        text = lines[line_no - 1]
        match = HEADING_PATTERN.match(text)
        if not match:
            continue
        level = len(match.group(1))
        if level > 3:
            # No heading in the current GDD goes deeper than level 3. A deeper
            # heading is treated as ordinary content of its nearest level-3
            # ancestor rather than inventing an unproven chunk boundary.
            continue
        headings.append({"line": line_no, "level": level, "title": match.group(2)})
    return headings


def compute_sections(headings: list[dict[str, Any]], total_lines: int) -> list[dict[str, Any]]:
    """Attach a content span and heading_path to every heading.

    A heading's content span runs from the line after the heading to the
    line before the *next* heading of any level, so child subsections get
    their own chunk rather than duplicating their text inside the parent.
    """
    sections: list[dict[str, Any]] = []
    path_stack: list[tuple[int, str]] = []
    current_section: str | None = None
    current_subsection: str | None = None

    for index, heading in enumerate(headings):
        level = heading["level"]
        title = heading["title"]

        while path_stack and path_stack[-1][0] >= level:
            path_stack.pop()
        path_stack.append((level, title))

        if level == 1:
            section, subsection = None, None
            current_section, current_subsection = None, None
        elif level == 2:
            section, subsection = title, None
            current_section, current_subsection = title, None
        else:
            section, subsection = current_section, title
            current_subsection = title

        content_start = heading["line"] + 1
        content_end = (
            headings[index + 1]["line"] - 1 if index + 1 < len(headings) else total_lines
        )

        sections.append(
            {
                "level": level,
                "title": title,
                "section": section,
                "subsection": subsection,
                "heading_path": [item_title for _, item_title in path_stack],
                "content_start": content_start,
                "content_end": content_end,
            }
        )

    return sections


def _raw_text(lines: list[str], start_line: int, end_line: int) -> str:
    return "\n".join(lines[start_line - 1 : end_line])


def _trim_blank_edges(lines: list[str], start_line: int, end_line: int) -> tuple[int, int] | None:
    while start_line <= end_line and lines[start_line - 1].strip() == "":
        start_line += 1
    while end_line >= start_line and lines[end_line - 1].strip() == "":
        end_line -= 1
    if start_line > end_line:
        return None
    return start_line, end_line


def _split_blank_line_blocks(lines: list[str], start_line: int, end_line: int) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    block_start: int | None = None
    for line_no in range(start_line, end_line + 1):
        blank = lines[line_no - 1].strip() == ""
        if blank:
            if block_start is not None:
                blocks.append((block_start, line_no - 1))
                block_start = None
        else:
            if block_start is None:
                block_start = line_no
    if block_start is not None:
        blocks.append((block_start, end_line))
    return blocks


def _classify_block(lines: list[str], start_line: int, end_line: int) -> str:
    block_lines = [lines[i - 1] for i in range(start_line, end_line + 1)]
    if all(line.lstrip().startswith("|") for line in block_lines):
        return "table"
    if LIST_ITEM_PATTERN.match(block_lines[0]):
        return "list"
    return "paragraph"


def _split_list_items(lines: list[str], start_line: int, end_line: int) -> list[tuple[int, int]]:
    items: list[tuple[int, int]] = []
    item_start: int | None = None
    for line_no in range(start_line, end_line + 1):
        text = lines[line_no - 1]
        if LIST_ITEM_PATTERN.match(text) and item_start is not None:
            items.append((item_start, line_no - 1))
            item_start = line_no
        elif item_start is None:
            item_start = line_no
    if item_start is not None:
        items.append((item_start, end_line))
    return items


def _compute_atomic_units(
    lines: list[str], start_line: int, end_line: int, max_chars: int
) -> list[tuple[int, int]]:
    units: list[tuple[int, int]] = []
    for block_start, block_end in _split_blank_line_blocks(lines, start_line, end_line):
        block_text = _raw_text(lines, block_start, block_end)
        kind = _classify_block(lines, block_start, block_end)

        if len(block_text) <= max_chars or kind == "table":
            # Tables are never split, even when they exceed max_chars, so a
            # table row set is never left structurally broken.
            units.append((block_start, block_end))
            continue

        if kind == "list":
            units.extend(_split_list_items(lines, block_start, block_end))
            continue

        if block_end > block_start:
            # A multi-line paragraph block can be split at its own line
            # boundaries. A single physical line has no deterministic
            # sub-boundary, so it is kept whole even if it exceeds
            # max_chars (documented as a known limitation).
            units.extend((line_no, line_no) for line_no in range(block_start, block_end + 1))
        else:
            units.append((block_start, block_end))

    return units


def _pack_units_into_chunks(
    lines: list[str], units: list[tuple[int, int]], max_chars: int
) -> list[tuple[int, int]]:
    chunks: list[tuple[int, int]] = []
    current_start: int | None = None
    current_end: int | None = None
    current_len = 0

    for unit_start, unit_end in units:
        unit_len = len(_raw_text(lines, unit_start, unit_end))
        if current_start is not None and current_len + 1 + unit_len > max_chars:
            chunks.append((current_start, current_end))
            current_start = None

        if current_start is None:
            current_start, current_end, current_len = unit_start, unit_end, unit_len
        else:
            current_end = unit_end
            current_len += 1 + unit_len

    if current_start is not None:
        chunks.append((current_start, current_end))

    return chunks


def _section_chunk_ranges(
    lines: list[str], content_start: int, content_end: int, max_chars: int
) -> list[tuple[int, int]]:
    trimmed = _trim_blank_edges(lines, content_start, content_end)
    if trimmed is None:
        return []
    start_line, end_line = trimmed

    whole_text = _raw_text(lines, start_line, end_line)
    if len(whole_text) <= max_chars:
        return [(start_line, end_line)]

    units = _compute_atomic_units(lines, start_line, end_line, max_chars)
    return _pack_units_into_chunks(lines, units, max_chars)


def build_chunks(
    lines: list[str], sections: list[dict[str, Any]], max_chars: int = MAX_CHUNK_CHARS
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    order = 0

    for section in sections:
        ranges = _section_chunk_ranges(lines, section["content_start"], section["content_end"], max_chars)
        if not ranges:
            continue

        for part_index, (start_line, end_line) in enumerate(ranges, start=1):
            order += 1
            text = _raw_text(lines, start_line, end_line)
            chunk = {
                "chunk_id": f"nsc-gdd-{order:03d}",
                "order": order,
                "title": section["title"],
                "section": section["section"],
                "subsection": section["subsection"],
                "heading_path": list(section["heading_path"]),
                "domain": DOMAIN,
                "canonical": True,
                "source": {
                    "file": CANONICAL_GDD_RELATIVE,
                    "start_line": start_line,
                    "end_line": end_line,
                },
                "chunk_part": (
                    {"index": part_index, "count": len(ranges)} if len(ranges) > 1 else None
                ),
                "text": text,
                "char_count": len(text),
                "sha256": sha256_text(text),
            }
            chunks.append(chunk)

    return chunks


def build_knowledge_base(
    source_path: Path = CANONICAL_GDD_PATH, max_chars: int = MAX_CHUNK_CHARS
) -> dict[str, Any]:
    text, lines = read_source(source_path)
    front_matter = parse_front_matter(lines)
    body_start_line = _front_matter_end_line(lines) + 1

    headings = parse_headings(lines, body_start_line)
    if not headings:
        raise GDDIndexError(f"No Markdown headings found in canonical GDD: {source_path}")

    sections = compute_sections(headings, len(lines))
    chunks = build_chunks(lines, sections, max_chars)

    title = front_matter.get("title", "No Safe Circle")
    revised_date = front_matter.get("revised_date", "")
    document_id_source = f"{title}|{revised_date}"

    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {
            "name": "Pipeline/GDDRAG index_builder",
            "version": BUILDER_VERSION,
        },
        "source": {
            "file": CANONICAL_GDD_RELATIVE,
            "sha256": sha256_text(text),
        },
        "document": {
            "document_id": f"no-safe-circle-gdd-{sha256_text(document_id_source)[:12]}",
            "title": title,
            "document_type": front_matter.get("document_type", ""),
            "status": front_matter.get("status", ""),
            "author": front_matter.get("author", ""),
            "original_date": front_matter.get("original_date", ""),
            "revised_date": revised_date,
            "source_docx": front_matter.get("source_docx", ""),
            "canonical_markdown": CANONICAL_GDD_RELATIVE,
            "language": "en",
            "total_chunks": len(chunks),
        },
        "chunking": {
            "strategy": "deterministic markdown heading/table/list structural chunking",
            "max_chunk_chars": max_chars,
            "overlap": 0,
            "recommended_top_k": DEFAULT_TOP_K,
            "recommended_search_fields": ["title", "section", "subsection", "text"],
        },
        "retrieval_guidance": {
            "canonicality_rule": (
                "Treat retrieved chunk text as authoritative. Consumers may summarize or "
                "rephrase it but must not invent, redesign, or contradict game rules."
            ),
            "default_filter": {"domain": DOMAIN, "canonical": True},
        },
        "chunks": chunks,
    }


def write_knowledge_base(knowledge_base: dict[str, Any], path: Path = DEFAULT_KNOWLEDGE_BASE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(knowledge_base, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def load_knowledge_base(path: Path = DEFAULT_KNOWLEDGE_BASE_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise GDDIndexError(f"Knowledge base not found: {path}. Run `gddctl.py rebuild` first.")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise GDDIndexError(f"Knowledge base is not valid JSON: {path}: {exc}") from exc


def current_source_sha256(source_path: Path = CANONICAL_GDD_PATH) -> str:
    text, _ = read_source(source_path)
    return sha256_text(text)


class ValidationResult:
    def __init__(self, findings: list[str]) -> None:
        self.findings = findings

    @property
    def ok(self) -> bool:
        return not self.findings


def validate_knowledge_base(
    knowledge_base: dict[str, Any], source_path: Path = CANONICAL_GDD_PATH
) -> ValidationResult:
    findings: list[str] = []

    if knowledge_base.get("schema_version") != SCHEMA_VERSION:
        findings.append(f"Unsupported schema_version: {knowledge_base.get('schema_version')!r}")

    indexed_hash = knowledge_base.get("source", {}).get("sha256")
    if not indexed_hash:
        findings.append("Missing source.sha256 in knowledge base.")
    else:
        try:
            actual_hash = current_source_sha256(source_path)
        except GDDIndexError as exc:
            findings.append(str(exc))
        else:
            if actual_hash != indexed_hash:
                findings.append(
                    f"Index is stale: source sha256 {actual_hash} does not match indexed {indexed_hash}."
                )

    chunks = knowledge_base.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        findings.append("Knowledge base contains no chunks.")
        return ValidationResult(findings)

    declared_count = knowledge_base.get("document", {}).get("total_chunks")
    if declared_count != len(chunks):
        findings.append(
            f"document.total_chunks ({declared_count!r}) does not match actual chunk count ({len(chunks)})."
        )

    seen_ids: set[str] = set()
    required_fields = ("chunk_id", "title", "text", "domain", "canonical", "source")
    for chunk in chunks:
        missing = [field for field in required_fields if chunk.get(field) in (None, "")]
        # canonical=False and domain="" are not valid, but canonical is a bool so
        # explicitly re-check it rather than relying on truthiness of False.
        if "canonical" not in chunk:
            missing.append("canonical")
        if missing:
            findings.append(f"{chunk.get('chunk_id', '<unknown>')}: missing required field(s) {missing}")
            continue

        chunk_id = chunk["chunk_id"]
        if chunk_id in seen_ids:
            findings.append(f"Duplicate chunk_id: {chunk_id}")
        seen_ids.add(chunk_id)

        source = chunk.get("source", {})
        if source.get("file") != CANONICAL_GDD_RELATIVE:
            findings.append(f"{chunk_id}: source.file {source.get('file')!r} is not the canonical GDD path.")

        start_line = source.get("start_line")
        end_line = source.get("end_line")
        if not isinstance(start_line, int) or not isinstance(end_line, int) or start_line < 1 or end_line < start_line:
            findings.append(f"{chunk_id}: invalid line range start_line={start_line!r} end_line={end_line!r}")

    return ValidationResult(findings)


def status_report(
    knowledge_base_path: Path = DEFAULT_KNOWLEDGE_BASE_PATH, source_path: Path = CANONICAL_GDD_PATH
) -> dict[str, Any]:
    actual_hash = current_source_sha256(source_path)

    if not knowledge_base_path.is_file():
        return {
            "canonical_gdd_path": CANONICAL_GDD_RELATIVE,
            "current_source_sha256": actual_hash,
            "indexed_source_sha256": None,
            "chunk_count": 0,
            "state": "MISSING",
        }

    knowledge_base = load_knowledge_base(knowledge_base_path)
    indexed_hash = knowledge_base.get("source", {}).get("sha256")
    chunk_count = len(knowledge_base.get("chunks", []))
    state = "CURRENT" if indexed_hash == actual_hash else "STALE"

    return {
        "canonical_gdd_path": CANONICAL_GDD_RELATIVE,
        "current_source_sha256": actual_hash,
        "indexed_source_sha256": indexed_hash,
        "chunk_count": chunk_count,
        "state": state,
    }
