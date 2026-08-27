from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

GDDRAG_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GDDRAG_DIR))

from index_builder import build_knowledge_base, write_knowledge_base  # noqa: E402
from retrieval import GDDRetriever  # noqa: E402

# Pinned against the reviewed canonical GDD state. If the GDD changes and
# `gddctl.py rebuild` legitimately shifts these top hits, inspect every changed
# result with `--review-baseline` and update this table deliberately. Never
# auto-accept new chunk IDs merely because the index was rebuilt.
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


def baseline_review_rows(retriever: GDDRetriever) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for query, expected_chunk_id in EXPECTED_TOP_HITS.items():
        results = retriever.retrieve(query, top_k=3)
        top = results[0] if results else None
        rows.append(
            {
                "query": query,
                "expected_chunk_id": expected_chunk_id,
                "current_chunk_id": top["chunk_id"] if top else None,
                "changed": top is None or top["chunk_id"] != expected_chunk_id,
                "current_title": top["title"] if top else None,
                "current_section": top["section"] if top else None,
                "current_subsection": top["subsection"] if top else None,
                "current_source": top["source"] if top else None,
                "current_score": top["score"] if top else None,
                "current_text": top["text"] if top else None,
                "top_three_chunk_ids": [item["chunk_id"] for item in results],
            }
        )
    return rows


def print_baseline_review(retriever: GDDRetriever, *, as_json: bool) -> None:
    rows = baseline_review_rows(retriever)
    if as_json:
        print(json.dumps({"baseline_review": rows}, indent=2, ensure_ascii=False))
        return

    print("GDDRAG PINNED BASELINE REVIEW")
    print("=" * 110)
    print(
        f"{'STATE':<8} {'EXPECTED':<13} {'CURRENT':<13} "
        f"{'LINES':<11} QUERY"
    )
    print("-" * 110)
    for row in rows:
        source = row["current_source"] or {}
        if isinstance(source, dict):
            lines = f"{source.get('start_line', '?')}-{source.get('end_line', '?')}"
        else:
            lines = "?"
        state = "CHANGED" if row["changed"] else "same"
        print(
            f"{state:<8} {str(row['expected_chunk_id']):<13} "
            f"{str(row['current_chunk_id']):<13} {lines:<11} {row['query']}"
        )

    changed = [row for row in rows if row["changed"]]
    print()
    print(f"Changed pinned queries: {len(changed)} / {len(rows)}")
    if not changed:
        print("No baseline update is required.")
        return

    print()
    print("CHANGED RESULT DETAILS")
    print("=" * 110)
    for row in changed:
        source = row["current_source"] or {}
        location = "unknown"
        if isinstance(source, dict):
            location = (
                f"{source.get('file', '?')} lines "
                f"{source.get('start_line', '?')}-{source.get('end_line', '?')}"
            )
        print(f"Query:     {row['query']}")
        print(f"Previous:  {row['expected_chunk_id']}")
        print(f"Current:   {row['current_chunk_id']}")
        print(f"Heading:   {row['current_title']}")
        print(f"Section:   {row['current_section']}")
        print(f"Subsection:{row['current_subsection']}")
        print(f"Source:    {location}")
        print(f"Top 3:     {', '.join(row['top_three_chunk_ids'])}")
        print(f"Text:      {row['current_text']}")
        print("-" * 110)

    print()
    print(
        "Review these changed hits against current canon. If they are semantically "
        "correct, deliberately update EXPECTED_TOP_HITS and rerun the normal strict test."
    )


def check_pinned_current_gdd_queries(retriever: GDDRetriever) -> None:
    mismatches: list[str] = []
    for row in baseline_review_rows(retriever):
        if row["changed"]:
            mismatches.append(
                f"Query {row['query']!r} expected top hit "
                f"{row['expected_chunk_id']}, got {row['current_chunk_id']} "
                f"(all: {row['top_three_chunk_ids']})"
            )
    assert not mismatches, (
        "Pinned current-GDD retrieval baseline changed. Run "
        "`python Pipeline/GDDRAG/tests/retrieval_regression_test.py --review-baseline` "
        "to inspect every changed query at once before updating EXPECTED_TOP_HITS.\n  - "
        + "\n  - ".join(mismatches)
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
    # Build a fully valid synthetic index containing two identically scored chunks.
    # Direct retriever construction now enforces the same integrity boundary as gddctl.
    source_text = (
        "# Fixture Game\n\n"
        "## Test\n\n"
        "identical scoring content for tie break test\n\n"
        "identical scoring content for tie break test\n"
    )

    with tempfile.TemporaryDirectory(prefix="gddrag-tiebreak-") as temp_dir:
        root = Path(temp_dir)
        source_path = root / "No_Safe_Circle_GDD.md"
        kb_path = root / "kb.json"
        source_path.write_text(source_text, encoding="utf-8", newline="\n")
        knowledge_base = build_knowledge_base(source_path=source_path, max_chars=20)
        write_knowledge_base(knowledge_base, kb_path)
        retriever = GDDRetriever(kb_path, source_path=source_path)

        results = retriever.retrieve("duplicate topic identical scoring content", top_k=2)

    assert len(results) == 2
    assert results[0]["score"] == results[1]["score"]
    assert results[0]["chunk_id"] == "nsc-gdd-001", "Tied scores must break by chunk_id ascending."
    assert results[1]["chunk_id"] == "nsc-gdd-002"


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review-baseline",
        action="store_true",
        help=(
            "Print all pinned queries with previous/current top hits and full details "
            "for every changed result. This is inspection only and does not update files."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="With --review-baseline, emit machine-readable JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    retriever = _build_retriever()

    if args.review_baseline:
        print_baseline_review(retriever, as_json=args.json)
        return 0
    if args.json:
        raise SystemExit("--json is only valid with --review-baseline")

    check_pinned_current_gdd_queries(retriever)
    check_results_are_stably_ordered(retriever)
    check_tie_break_order_directly()
    check_unrelated_content_is_not_returned(retriever)

    print("retrieval_regression_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
