from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

GDDRAG_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GDDRAG_DIR))

from index_builder import build_knowledge_base, sha256_text, write_knowledge_base  # noqa: E402
from integrity import validate_current_knowledge_base  # noqa: E402
from retrieval import GDDRetriever  # noqa: E402


FIXTURE = """---
title: \"Fixture\"
---

# Fixture Game

## Movement

Mouse-directed movement uses one shared cursor projection.

### Ownership

Player Movement owns the projection and exposes it to spells.
"""


def _fixture() -> tuple[tempfile.TemporaryDirectory[str], Path, Path, dict]:
    temp = tempfile.TemporaryDirectory(prefix="gddrag-integrity-")
    root = Path(temp.name)
    source = root / "No_Safe_Circle_GDD.md"
    index = root / "No_Safe_Circle_GDD_RAG.json"
    source.write_text(FIXTURE, encoding="utf-8", newline="\n")
    knowledge_base = build_knowledge_base(source_path=source)
    write_knowledge_base(knowledge_base, index)
    return temp, source, index, knowledge_base


def _expect_failure(knowledge_base: dict, source: Path, phrase: str) -> None:
    result = validate_current_knowledge_base(knowledge_base, source_path=source)
    assert not result.ok, "Corrupt production index unexpectedly passed validation."
    assert any(phrase in finding for finding in result.findings), result.findings


def check_fresh_index_passes() -> None:
    temp, source, _, knowledge_base = _fixture()
    try:
        result = validate_current_knowledge_base(knowledge_base, source_path=source)
        assert result.ok, result.findings
    finally:
        temp.cleanup()


def check_altered_chunk_text_is_rejected() -> None:
    temp, source, _, knowledge_base = _fixture()
    try:
        tampered = copy.deepcopy(knowledge_base)
        tampered["chunks"][0]["text"] = "FABRICATED CANON"
        tampered["chunks"][0]["char_count"] = len("FABRICATED CANON")
        tampered["chunks"][0]["sha256"] = sha256_text("FABRICATED CANON")
        _expect_failure(tampered, source, "does not exactly match canonical GDD")
    finally:
        temp.cleanup()


def check_chunk_metadata_is_rejected() -> None:
    temp, source, _, knowledge_base = _fixture()
    try:
        noncanonical = copy.deepcopy(knowledge_base)
        noncanonical["chunks"][0]["canonical"] = False
        _expect_failure(noncanonical, source, "canonical must be exactly true")

        wrong_domain = copy.deepcopy(knowledge_base)
        wrong_domain["chunks"][0]["domain"] = "other"
        _expect_failure(wrong_domain, source, "must be 'game_design'")

        bad_range = copy.deepcopy(knowledge_base)
        bad_range["chunks"][0]["source"]["start_line"] = 9999
        bad_range["chunks"][0]["source"]["end_line"] = 10000
        _expect_failure(bad_range, source, "invalid line range")
    finally:
        temp.cleanup()


def check_self_hash_and_count_are_rejected() -> None:
    temp, source, _, knowledge_base = _fixture()
    try:
        bad_count = copy.deepcopy(knowledge_base)
        bad_count["chunks"][0]["char_count"] += 1
        _expect_failure(bad_count, source, "char_count")

        bad_hash = copy.deepcopy(knowledge_base)
        bad_hash["chunks"][0]["sha256"] = "0" * 64
        _expect_failure(bad_hash, source, "indexed text sha256")
    finally:
        temp.cleanup()


def check_direct_retriever_refuses_tampered_or_stale_index() -> None:
    temp, source, index, knowledge_base = _fixture()
    try:
        tampered = copy.deepcopy(knowledge_base)
        tampered["chunks"][0]["text"] = "FABRICATED CANON"
        tampered["chunks"][0]["char_count"] = len("FABRICATED CANON")
        tampered["chunks"][0]["sha256"] = sha256_text("FABRICATED CANON")
        index.write_text(json.dumps(tampered, indent=2) + "\n", encoding="utf-8")
        try:
            GDDRetriever(index, source_path=source)
        except ValueError as exc:
            assert "cannot be searched" in str(exc)
        else:
            raise AssertionError("Direct retriever accepted tampered indexed canon.")

        write_knowledge_base(knowledge_base, index)
        source.write_text(FIXTURE + "\nNew canonical rule.\n", encoding="utf-8", newline="\n")
        try:
            GDDRetriever(index, source_path=source)
        except ValueError as exc:
            assert "cannot be searched" in str(exc)
        else:
            raise AssertionError("Direct retriever accepted a stale index.")
    finally:
        temp.cleanup()


def main() -> int:
    check_fresh_index_passes()
    check_altered_chunk_text_is_rejected()
    check_chunk_metadata_is_rejected()
    check_self_hash_and_count_are_rejected()
    check_direct_retriever_refuses_tampered_or_stale_index()
    print("integrity_regression_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
