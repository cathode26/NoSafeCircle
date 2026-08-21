from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

GDDRAG_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = GDDRAG_DIR.parents[1]
sys.path.insert(0, str(GDDRAG_DIR))

import index_builder  # noqa: E402
from index_builder import (  # noqa: E402
    build_knowledge_base,
    load_knowledge_base,
    status_report,
    validate_knowledge_base,
    write_knowledge_base,
)


def _write_json(path: Path, value: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def check_byte_identical_rebuild() -> None:
    first = build_knowledge_base()
    second = build_knowledge_base()

    with tempfile.TemporaryDirectory(prefix="gddrag-smoke-") as temp_dir:
        first_path = Path(temp_dir) / "first.json"
        second_path = Path(temp_dir) / "second.json"
        write_knowledge_base(first, first_path)
        write_knowledge_base(second, second_path)
        assert first_path.read_bytes() == second_path.read_bytes(), (
            "Two rebuilds from identical source must produce byte-identical output."
        )
    assert first["document"]["total_chunks"] > 0


def check_current_source_hash_stored_and_validated() -> None:
    knowledge_base = build_knowledge_base()
    result = validate_knowledge_base(knowledge_base)
    assert result.ok, f"Freshly built index unexpectedly failed validation: {result.findings}"

    with tempfile.TemporaryDirectory(prefix="gddrag-smoke-") as temp_dir:
        kb_path = Path(temp_dir) / "kb.json"
        write_knowledge_base(knowledge_base, kb_path)
        report = status_report(kb_path)
        assert report["state"] == "CURRENT", report
        assert report["current_source_sha256"] == report["indexed_source_sha256"]


def check_changed_source_makes_index_stale() -> None:
    real_text = index_builder.CANONICAL_GDD_PATH.read_text(encoding="utf-8")
    modified_text = real_text + "\n\n### Injected Smoke-Test Heading\n\nInjected content for staleness test.\n"

    with tempfile.TemporaryDirectory(prefix="gddrag-smoke-") as temp_dir:
        fixture_path = Path(temp_dir) / "modified_gdd.md"
        fixture_path.write_text(modified_text, encoding="utf-8")

        # Build against the original source, then validate it against the modified fixture's
        # hash by swapping in a mismatched sha256, simulating a canonical GDD edit after indexing.
        knowledge_base = build_knowledge_base()
        result = validate_knowledge_base(knowledge_base, source_path=fixture_path)
        assert not result.ok, "Index built from stale source should fail validation against changed GDD."
        assert any("stale" in finding.lower() for finding in result.findings), result.findings

        kb_path = Path(temp_dir) / "kb.json"
        write_knowledge_base(knowledge_base, kb_path)
        report = status_report(kb_path, source_path=fixture_path)
        assert report["state"] == "STALE", report


def check_search_refuses_stale_index() -> None:
    import subprocess

    knowledge_base = build_knowledge_base()
    knowledge_base["source"]["sha256"] = "0" * 64  # force a hash mismatch

    with tempfile.TemporaryDirectory(prefix="gddrag-smoke-") as temp_dir:
        kb_path = Path(temp_dir) / "kb.json"
        write_knowledge_base(knowledge_base, kb_path)

        completed = subprocess.run(
            [
                sys.executable,
                str(GDDRAG_DIR / "gddctl.py"),
                "--knowledge-base",
                str(kb_path),
                "search",
                "mouse-directed movement",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode != 0, "search must fail on a stale index."
        assert "REFUSED" in completed.stderr, completed.stderr


def check_duplicate_chunk_ids_fail_validation() -> None:
    knowledge_base = build_knowledge_base()
    assert len(knowledge_base["chunks"]) >= 2
    knowledge_base["chunks"][1]["chunk_id"] = knowledge_base["chunks"][0]["chunk_id"]

    result = validate_knowledge_base(knowledge_base)
    assert not result.ok
    assert any("Duplicate chunk_id" in finding for finding in result.findings), result.findings


def check_bad_line_ranges_fail_validation() -> None:
    knowledge_base = build_knowledge_base()
    knowledge_base["chunks"][0]["source"]["end_line"] = knowledge_base["chunks"][0]["source"]["start_line"] - 1

    result = validate_knowledge_base(knowledge_base)
    assert not result.ok
    assert any("invalid line range" in finding for finding in result.findings), result.findings


def check_historical_knowledge_base_is_never_read() -> None:
    for path in GDDRAG_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "DynamicContentPipeline" not in text, (
            f"{path} references the historical Assignment 4 pipeline, which must not be read at runtime."
        )

    historical_path = REPO_ROOT / "DynamicContentPipeline" / "knowledge_base" / "No_Safe_Circle_GDD_RAG.json"
    before_mtime = historical_path.stat().st_mtime_ns if historical_path.is_file() else None

    build_knowledge_base()
    load_knowledge_base(index_builder.DEFAULT_KNOWLEDGE_BASE_PATH)

    after_mtime = historical_path.stat().st_mtime_ns if historical_path.is_file() else None
    assert before_mtime == after_mtime, "Historical Assignment 4 knowledge base must not be touched."


def check_declared_chunk_count_mismatch_fails_validation() -> None:
    knowledge_base = build_knowledge_base()
    knowledge_base["document"]["total_chunks"] = len(knowledge_base["chunks"]) + 1

    result = validate_knowledge_base(knowledge_base)
    assert not result.ok
    assert any("total_chunks" in finding for finding in result.findings), result.findings


def check_missing_required_field_fails_validation() -> None:
    knowledge_base = build_knowledge_base()
    del knowledge_base["chunks"][0]["title"]

    result = validate_knowledge_base(knowledge_base)
    assert not result.ok
    assert any("missing required field" in finding for finding in result.findings), result.findings


def main() -> int:
    check_byte_identical_rebuild()
    check_current_source_hash_stored_and_validated()
    check_changed_source_makes_index_stale()
    check_search_refuses_stale_index()
    check_duplicate_chunk_ids_fail_validation()
    check_bad_line_ranges_fail_validation()
    check_declared_chunk_count_mismatch_fails_validation()
    check_missing_required_field_fails_validation()
    check_historical_knowledge_base_is_never_read()

    print("gdd_rag_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
