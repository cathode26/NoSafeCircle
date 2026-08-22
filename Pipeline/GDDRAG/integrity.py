from __future__ import annotations

"""Strict production integrity validation for the current-GDD RAG index.

The historical index-builder validator performs lightweight structural checks.
This module is the production trust boundary used by ``gddctl`` and
``GDDRetriever``. It proves that every served chunk is an exact deterministic
projection of the current canonical Markdown GDD.
"""

from pathlib import Path
from typing import Any

from index_builder import (
    CANONICAL_GDD_PATH,
    CANONICAL_GDD_RELATIVE,
    DEFAULT_TOP_K,
    DOMAIN,
    MAX_CHUNK_CHARS,
    SCHEMA_VERSION,
    ValidationResult,
    build_knowledge_base,
    read_source,
    sha256_text,
)


def _exact_int(value: Any) -> bool:
    """Return True only for an actual int, not bool or an integer-like value."""
    return type(value) is int


def validate_current_knowledge_base(
    knowledge_base: dict[str, Any],
    source_path: Path = CANONICAL_GDD_PATH,
) -> ValidationResult:
    """Validate freshness, provenance, chunk integrity, and reproducibility.

    A valid production index must equal a deterministic rebuild from the current
    canonical GDD. Detailed checks are retained so failures explain the exact
    broken trust claim rather than reporting only a generic mismatch.
    """

    findings: list[str] = []

    if not isinstance(knowledge_base, dict):
        return ValidationResult(["Knowledge base root must be an object."])

    if knowledge_base.get("schema_version") != SCHEMA_VERSION:
        findings.append(
            f"Unsupported schema_version: {knowledge_base.get('schema_version')!r}"
        )

    for field in ("source", "document", "chunking", "retrieval_guidance", "chunks"):
        if field not in knowledge_base:
            findings.append(f"Missing top-level field: {field}")

    source_metadata = knowledge_base.get("source")
    if not isinstance(source_metadata, dict):
        findings.append("Missing or invalid top-level source object in knowledge base.")
        source_metadata = {}

    document = knowledge_base.get("document")
    if not isinstance(document, dict):
        findings.append("Missing or invalid document object in knowledge base.")
        document = {}

    chunking = knowledge_base.get("chunking")
    if not isinstance(chunking, dict):
        findings.append("Missing or invalid chunking object in knowledge base.")
        chunking = {}

    retrieval_guidance = knowledge_base.get("retrieval_guidance")
    if not isinstance(retrieval_guidance, dict):
        findings.append("Missing or invalid retrieval_guidance object in knowledge base.")
        retrieval_guidance = {}

    default_filter = retrieval_guidance.get("default_filter")
    if not isinstance(default_filter, dict):
        findings.append("retrieval_guidance.default_filter must be an object.")
    else:
        if default_filter.get("domain") != DOMAIN:
            findings.append(
                f"retrieval_guidance.default_filter.domain must be {DOMAIN!r}."
            )
        if default_filter.get("canonical") is not True:
            findings.append(
                "retrieval_guidance.default_filter.canonical must be exactly true."
            )

    max_chunk_chars = chunking.get("max_chunk_chars")
    if not _exact_int(max_chunk_chars) or max_chunk_chars < 1:
        findings.append(
            f"chunking.max_chunk_chars must be a positive integer; got {max_chunk_chars!r}."
        )
        max_chunk_chars = MAX_CHUNK_CHARS

    recommended_top_k = chunking.get("recommended_top_k")
    if not _exact_int(recommended_top_k) or recommended_top_k < 1:
        findings.append(
            f"chunking.recommended_top_k must be a positive integer; got {recommended_top_k!r}."
        )

    indexed_source_file = source_metadata.get("file")
    if indexed_source_file != CANONICAL_GDD_RELATIVE:
        findings.append(
            f"source.file {indexed_source_file!r} is not the canonical GDD path "
            f"{CANONICAL_GDD_RELATIVE!r}."
        )

    indexed_hash = source_metadata.get("sha256")
    if not isinstance(indexed_hash, str) or not indexed_hash.strip():
        findings.append("Missing source.sha256 in knowledge base.")

    source_lines: list[str] | None = None
    actual_hash: str | None = None
    try:
        source_text, source_lines = read_source(source_path)
    except Exception as exc:  # normalized into a validation finding
        findings.append(str(exc))
    else:
        actual_hash = sha256_text(source_text)
        if indexed_hash and actual_hash != indexed_hash:
            findings.append(
                f"Index is stale: source sha256 {actual_hash} does not match indexed {indexed_hash}."
            )

    chunks = knowledge_base.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        findings.append("Knowledge base contains no chunks.")
        return ValidationResult(findings)

    declared_count = document.get("total_chunks")
    if declared_count != len(chunks):
        findings.append(
            f"document.total_chunks ({declared_count!r}) does not match actual chunk count ({len(chunks)})."
        )

    seen_ids: set[str] = set()
    required_fields = (
        "chunk_id",
        "title",
        "text",
        "domain",
        "canonical",
        "source",
        "char_count",
        "sha256",
    )

    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            findings.append(f"chunks[{index}] is not an object.")
            continue

        raw_id = chunk.get("chunk_id")
        label = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else f"chunks[{index}]"

        missing: list[str] = []
        for field in required_fields:
            if field not in chunk or chunk[field] is None:
                missing.append(field)
            elif isinstance(chunk[field], str) and not chunk[field].strip():
                missing.append(field)
        if missing:
            findings.append(f"{label}: missing required field(s) {missing}")

        if isinstance(raw_id, str) and raw_id.strip():
            chunk_id = raw_id.strip()
            if chunk_id in seen_ids:
                findings.append(f"Duplicate chunk_id: {chunk_id}")
            seen_ids.add(chunk_id)

        if chunk.get("canonical") is not True:
            findings.append(f"{label}: canonical must be exactly true.")

        if chunk.get("domain") != DOMAIN:
            findings.append(
                f"{label}: domain {chunk.get('domain')!r} must be {DOMAIN!r}."
            )

        chunk_source = chunk.get("source")
        if not isinstance(chunk_source, dict):
            findings.append(f"{label}: source must be an object.")
            continue

        if chunk_source.get("file") != CANONICAL_GDD_RELATIVE:
            findings.append(
                f"{label}: source.file {chunk_source.get('file')!r} is not the canonical GDD path."
            )

        start_line = chunk_source.get("start_line")
        end_line = chunk_source.get("end_line")
        valid_range = (
            _exact_int(start_line)
            and _exact_int(end_line)
            and start_line >= 1
            and end_line >= start_line
            and source_lines is not None
            and end_line <= len(source_lines)
        )
        if not valid_range:
            upper = len(source_lines) if source_lines is not None else "unavailable"
            findings.append(
                f"{label}: invalid line range start_line={start_line!r} "
                f"end_line={end_line!r}; source line count={upper}."
            )

        text = chunk.get("text")
        if isinstance(text, str):
            declared_chars = chunk.get("char_count")
            if not _exact_int(declared_chars) or declared_chars != len(text):
                findings.append(
                    f"{label}: char_count {declared_chars!r} does not match actual text length {len(text)}."
                )

            declared_chunk_hash = chunk.get("sha256")
            actual_chunk_hash = sha256_text(text)
            if declared_chunk_hash != actual_chunk_hash:
                findings.append(
                    f"{label}: sha256 {declared_chunk_hash!r} does not match indexed text "
                    f"sha256 {actual_chunk_hash}."
                )

            if valid_range and source_lines is not None:
                expected_text = "\n".join(source_lines[start_line - 1 : end_line])
                if text != expected_text:
                    findings.append(
                        f"{label}: indexed text does not exactly match canonical GDD "
                        f"lines {start_line}-{end_line}."
                    )

    # Close the remaining metadata/order surface: the only valid CURRENT index
    # is the exact deterministic builder output for the current source.
    if actual_hash is not None and indexed_hash == actual_hash:
        try:
            expected = build_knowledge_base(
                source_path=source_path, max_chars=max_chunk_chars
            )
        except Exception as exc:
            findings.append(f"Unable to rebuild current GDD index for comparison: {exc}")
        else:
            if knowledge_base != expected:
                findings.append(
                    "Knowledge base does not exactly match the deterministic rebuild "
                    "from the current canonical GDD."
                )

    return ValidationResult(findings)
