from __future__ import annotations

import sys
import tempfile
from pathlib import Path

GDDRAG_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GDDRAG_DIR))

from index_builder import build_knowledge_base, write_knowledge_base  # noqa: E402
from retrieval import GDDRetriever  # noqa: E402

# Pinned against the current canonical GDD (Docs/GDD/No_Safe_Circle_GDD.md). If the GDD
# changes and `gddctl.py rebuild` legitimately shifts these top hits, update this table
# deliberately rather than treating a failure here as a false positive.
EXPECTED_TOP_HITS = {
    "mouse-directed movement and cursor-to-gameplay-plane projection": "nsc-gdd-007",
    "Charged Fireball movement restriction ownership": "nsc-gdd-026",
    "Frost Field cursor placement and Ranged Enemy limitation": "nsc-gdd-025",
    "door click-to-approach and automatic five-second timer": "nsc-gdd-025",
    "locked-door break and forward enemy pursuit": "nsc-gdd-018",
    "floor restart owner-controlled reset entry points": "nsc-gdd-037",
    "victory suspend/re-enable ownership": "nsc-gdd-027",
    "Active Enemy Registry fifteen-enemy cap": "nsc-gdd-019",
    "fixed isometric camera requirements": "nsc-gdd-034",
    "Windows build and canonical scene registration": "nsc-gdd-039",
}


def _build_retriever() -> GDDRetriever:
    knowledge_base = build_knowledge_base()
    temp_dir = tempfile.mkdtemp(prefix="gddrag-regression-")
    kb_path = Path(temp_dir) / "kb.json"
    write_knowledge_base(knowledge_base, kb_path)
    return GDDRetriever(kb_path)


def check_pinned_current_gdd_queries(retriever: GDDRetriever) -> None:
    for query, expected_chunk_id in EXPECTED_TOP_HITS.items():
        results = retriever.retrieve(query, top_k=3)
        assert results, f"No results for query: {query}"
        top = results[0]["chunk_id"]
        assert top == expected_chunk_id, (
            f"Query {query!r} expected top hit {expected_chunk_id}, got {top} "
            f"(all: {[r['chunk_id'] for r in results]})"
        )


def check_results_are_stably_ordered(retriever: GDDRetriever) -> None:
    query = "mouse-directed movement and cursor-to-gameplay-plane projection"
    first_run = [r["chunk_id"] for r in retriever.retrieve(query, top_k=5)]
    second_run = [r["chunk_id"] for r in retriever.retrieve(query, top_k=5)]
    assert first_run == second_run, (first_run, second_run)

    # Scores must be non-increasing, and any exact tie must be broken by chunk_id
    # ascending, matching the documented (-score, chunk_id) sort key.
    results = retriever.retrieve(query, top_k=len(retriever.data["chunks"]))
    for previous, current in zip(results, results[1:]):
        assert previous["score"] >= current["score"], (previous, current)
        if previous["score"] == current["score"]:
            assert previous["chunk_id"] < current["chunk_id"], (previous, current)


def check_tie_break_order_directly() -> None:
    # A minimal synthetic knowledge base isolates the sort-key tie-break behavior
    # from real GDD content, so this assertion cannot pass by coincidental scoring.
    knowledge_base = {
        "document": {"total_chunks": 2},
        "chunking": {"recommended_top_k": 4},
        "retrieval_guidance": {"default_filter": {"domain": "game_design", "canonical": True}},
        "chunks": [
            {
                "chunk_id": "nsc-gdd-900",
                "title": "Duplicate Topic",
                "section": "Test",
                "subsection": None,
                "domain": "game_design",
                "canonical": True,
                "source": {"file": "Docs/GDD/No_Safe_Circle_GDD.md", "start_line": 1, "end_line": 1},
                "text": "identical scoring content for tie break test",
            },
            {
                "chunk_id": "nsc-gdd-899",
                "title": "Duplicate Topic",
                "section": "Test",
                "subsection": None,
                "domain": "game_design",
                "canonical": True,
                "source": {"file": "Docs/GDD/No_Safe_Circle_GDD.md", "start_line": 2, "end_line": 2},
                "text": "identical scoring content for tie break test",
            },
        ],
    }

    with tempfile.TemporaryDirectory(prefix="gddrag-tiebreak-") as temp_dir:
        kb_path = Path(temp_dir) / "kb.json"
        import json

        kb_path.write_text(json.dumps(knowledge_base), encoding="utf-8")
        retriever = GDDRetriever(kb_path)

    results = retriever.retrieve("duplicate topic identical scoring content", top_k=2)
    assert len(results) == 2
    assert results[0]["score"] == results[1]["score"]
    assert results[0]["chunk_id"] == "nsc-gdd-899", "Tied scores must break by chunk_id ascending."
    assert results[1]["chunk_id"] == "nsc-gdd-900"


def check_unrelated_content_is_not_returned(retriever: GDDRetriever) -> None:
    # None of these terms appear anywhere in the No Safe Circle GDD. A deterministic
    # keyword/phrase retriever must not surface unrelated repository content merely
    # because some file elsewhere in the repo happens to mention similar words.
    for query in (
        "spreadsheet pivot table formula macro",
        "chocolate chip cookie recipe baking temperature",
        "mortgage refinance interest rate escrow",
    ):
        try:
            results = retriever.retrieve(query, top_k=4)
        except ValueError:
            results = []
        assert not results, f"Unrelated query unexpectedly matched: {query} -> {results}"


def main() -> int:
    retriever = _build_retriever()
    check_pinned_current_gdd_queries(retriever)
    check_results_are_stably_ordered(retriever)
    check_tie_break_order_directly()
    check_unrelated_content_is_not_returned(retriever)

    print("retrieval_regression_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
