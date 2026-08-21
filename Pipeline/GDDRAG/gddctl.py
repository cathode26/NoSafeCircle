from __future__ import annotations

"""Deterministic local CLI for the production GDD RAG index.

python Pipeline/GDDRAG/gddctl.py rebuild
python Pipeline/GDDRAG/gddctl.py status
python Pipeline/GDDRAG/gddctl.py validate
python Pipeline/GDDRAG/gddctl.py search "<query>"
python Pipeline/GDDRAG/gddctl.py search "<query>" --json

No LLM or external API call is made anywhere in this tool.
"""

import argparse
import json
import sys
from pathlib import Path

from index_builder import (
    DEFAULT_KNOWLEDGE_BASE_PATH,
    GDDIndexError,
    build_knowledge_base,
    load_knowledge_base,
    status_report,
    validate_knowledge_base,
    write_knowledge_base,
)
from retrieval import GDDRetriever


def command_rebuild(knowledge_base_path: Path) -> int:
    knowledge_base = build_knowledge_base()
    write_knowledge_base(knowledge_base, knowledge_base_path)

    document = knowledge_base["document"]
    print("gddctl rebuild: PASS")
    print(f"Source:        {knowledge_base['source']['file']}")
    print(f"Source sha256: {knowledge_base['source']['sha256']}")
    print(f"Chunks:        {document['total_chunks']}")
    print(f"Output:        {knowledge_base_path}")
    return 0


def command_status(knowledge_base_path: Path) -> int:
    report = status_report(knowledge_base_path)
    print(f"Canonical GDD:          {report['canonical_gdd_path']}")
    print(f"Current source sha256:  {report['current_source_sha256']}")
    print(f"Indexed source sha256:  {report['indexed_source_sha256']}")
    print(f"Chunk count:            {report['chunk_count']}")
    print(f"State:                  {report['state']}")
    return 0 if report["state"] == "CURRENT" else 1


def command_validate(knowledge_base_path: Path) -> int:
    knowledge_base = load_knowledge_base(knowledge_base_path)
    result = validate_knowledge_base(knowledge_base)
    if result.ok:
        print("gddctl validate: PASS")
        print(f"Chunks: {len(knowledge_base['chunks'])}")
        return 0

    print("gddctl validate: FAIL")
    for finding in result.findings:
        print(f"  - {finding}")
    return 1


def command_search(
    knowledge_base_path: Path, query: str, top_k: int | None, as_json: bool
) -> int:
    knowledge_base = load_knowledge_base(knowledge_base_path)
    result = validate_knowledge_base(knowledge_base)
    if not result.ok:
        print("gddctl search: REFUSED (index is not valid/current)", file=sys.stderr)
        for finding in result.findings:
            print(f"  - {finding}", file=sys.stderr)
        print("Run `python Pipeline/GDDRAG/gddctl.py rebuild` to refresh the index.", file=sys.stderr)
        return 1

    retriever = GDDRetriever(knowledge_base_path)
    try:
        results = retriever.retrieve(query=query, top_k=top_k)
    except ValueError as exc:
        print(f"gddctl search: FAIL\n{exc}", file=sys.stderr)
        return 1

    if as_json:
        print(
            json.dumps(
                {"query": query, "result_count": len(results), "results": results},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(f"Query: {query}")
    print(f"Results: {len(results)}")
    print()
    for index, item in enumerate(results, start=1):
        print(f"{index}. {item['chunk_id']} | {item['title']} | score={item['score']}")
        print(f"   Section: {item['section']}")
        if item["subsection"]:
            print(f"   Subsection: {item['subsection']}")
        print(f"   Source: {item['source']['file']} lines {item['source']['start_line']}-{item['source']['end_line']}")
        print(f"   Text: {item['text']}")
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic local CLI for the production GDD RAG index.")
    parser.add_argument(
        "--knowledge-base", type=Path, default=DEFAULT_KNOWLEDGE_BASE_PATH, help="Path to the index JSON file."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("rebuild", help="Rebuild the index from the canonical GDD Markdown.")
    subparsers.add_parser("status", help="Report freshness of the current index.")
    subparsers.add_parser("validate", help="Validate index structure and freshness.")

    search_parser = subparsers.add_parser("search", help="Search the index. Refuses to run on a stale index.")
    search_parser.add_argument("query")
    search_parser.add_argument("--top-k", type=int, default=None)
    search_parser.add_argument("--json", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "rebuild":
            return command_rebuild(args.knowledge_base)
        if args.command == "status":
            return command_status(args.knowledge_base)
        if args.command == "validate":
            return command_validate(args.knowledge_base)
        if args.command == "search":
            return command_search(args.knowledge_base, args.query, args.top_k, args.json)
        parser.error(f"Unknown command: {args.command}")
    except GDDIndexError as exc:
        print(f"gddctl {args.command}: FAIL\n{exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
