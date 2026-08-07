from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

RETRIEVER_VERSION = "1.1"

TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?", re.IGNORECASE)

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "does", "for",
    "from", "how", "in", "is", "it", "of", "on", "or", "that", "the", "their",
    "this", "to", "what", "when", "where", "which", "who", "why", "with",
}

FIELD_WEIGHTS = {
    "title": 4.0,
    "section": 2.0,
    "subsection": 2.5,
    "entities": 5.0,
    "keywords": 4.0,
    "text": 1.0,
}


def tokenize(value: str) -> list[str]:
    """Normalize text into searchable tokens while dropping common stop words."""
    return [
        token.lower()
        for token in TOKEN_PATTERN.findall(value or "")
        if token.lower() not in STOP_WORDS
    ]


def normalize_phrase(value: str) -> str:
    """Normalize a phrase for exact phrase matching."""
    return " ".join(tokenize(value))


def field_text(chunk: dict[str, Any], field: str) -> str:
    value = chunk.get(field)
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


class GDDRetriever:
    def __init__(self, knowledge_base_path: Path) -> None:
        self.knowledge_base_path = knowledge_base_path
        self.data = self._load_knowledge_base()
        self._validate_knowledge_base()

        default_filter = self.data["retrieval_guidance"]["assignment4_default_filter"]
        self.default_domain = default_filter["domain"]
        self.default_canonical = bool(default_filter["canonical"])
        self.default_top_k = int(self.data["chunking"]["recommended_top_k"])

    def _load_knowledge_base(self) -> dict[str, Any]:
        try:
            return json.loads(self.knowledge_base_path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Knowledge base not found: {self.knowledge_base_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Knowledge base is not valid JSON: {self.knowledge_base_path}"
            ) from exc

    def _validate_knowledge_base(self) -> None:
        required_top_level = {"document", "chunking", "retrieval_guidance", "chunks"}
        missing = required_top_level.difference(self.data)
        if missing:
            raise ValueError(f"Knowledge base is missing keys: {sorted(missing)}")

        chunks = self.data["chunks"]
        declared_count = int(self.data["document"]["total_chunks"])
        if declared_count != len(chunks):
            raise ValueError(
                f"Chunk count mismatch: declared {declared_count}, found {len(chunks)}"
            )

        chunk_ids = [chunk["chunk_id"] for chunk in chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("Knowledge base contains duplicate chunk IDs")

    def _eligible_chunks(
        self,
        domain: str | None,
        canonical_only: bool,
    ) -> list[dict[str, Any]]:
        selected_domain = domain or self.default_domain
        chunks = [
            chunk
            for chunk in self.data["chunks"]
            if chunk.get("domain") == selected_domain
            and (not canonical_only or chunk.get("canonical") is True)
        ]
        if not chunks:
            raise ValueError(
                f"No chunks matched domain={selected_domain!r}, "
                f"canonical_only={canonical_only}"
            )
        return chunks

    @staticmethod
    def _document_frequency(
        chunks: list[dict[str, Any]],
    ) -> Counter[str]:
        frequencies: Counter[str] = Counter()
        for chunk in chunks:
            unique_terms: set[str] = set()
            for field in FIELD_WEIGHTS:
                unique_terms.update(tokenize(field_text(chunk, field)))
            frequencies.update(unique_terms)
        return frequencies

    @staticmethod
    def _phrase_boost(query_phrase: str, chunk: dict[str, Any]) -> float:
        score = 0.0

        title = normalize_phrase(field_text(chunk, "title"))
        if title and title in query_phrase:
            score += 12.0

        for entity in chunk.get("entities", []):
            normalized_entity = normalize_phrase(str(entity))
            if normalized_entity and normalized_entity in query_phrase:
                score += 10.0

        for keyword in chunk.get("keywords", []):
            normalized_keyword = normalize_phrase(str(keyword))
            if normalized_keyword and normalized_keyword in query_phrase:
                score += 6.0

        return score

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        domain: str | None = None,
        canonical_only: bool | None = None,
    ) -> list[dict[str, Any]]:
        query_tokens = tokenize(query)
        if not query_tokens:
            raise ValueError("Query must contain at least one searchable term")

        selected_top_k = top_k or self.default_top_k
        if selected_top_k < 1:
            raise ValueError("top_k must be at least 1")

        selected_canonical = (
            self.default_canonical
            if canonical_only is None
            else canonical_only
        )

        chunks = self._eligible_chunks(domain, selected_canonical)
        document_frequency = self._document_frequency(chunks)
        document_count = len(chunks)
        normalized_query = normalize_phrase(query)
        query_term_counts = Counter(query_tokens)

        scored_results: list[dict[str, Any]] = []

        for chunk in chunks:
            score = self._phrase_boost(normalized_query, chunk)
            matched_terms: set[str] = set()

            for field, field_weight in FIELD_WEIGHTS.items():
                field_tokens = tokenize(field_text(chunk, field))
                if not field_tokens:
                    continue

                term_counts = Counter(field_tokens)
                field_length = len(field_tokens)

                for term, query_count in query_term_counts.items():
                    term_frequency = term_counts.get(term, 0)
                    if term_frequency == 0:
                        continue

                    matched_terms.add(term)
                    inverse_document_frequency = math.log(
                        1.0
                        + (
                            (document_count - document_frequency[term] + 0.5)
                            / (document_frequency[term] + 0.5)
                        )
                    )
                    saturated_tf = term_frequency / (
                        term_frequency + 0.75 + (0.25 * field_length / 100.0)
                    )
                    score += (
                        field_weight
                        * inverse_document_frequency
                        * saturated_tf
                        * query_count
                    )

            if score > 0:
                scored_results.append(
                    {
                        "chunk_id": chunk["chunk_id"],
                        "title": chunk["title"],
                        "section": chunk["section"],
                        "subsection": chunk.get("subsection"),
                        "domain": chunk["domain"],
                        "canonical": chunk["canonical"],
                        "score": round(score, 4),
                        "matched_terms": sorted(matched_terms),
                        "source": chunk["source"],
                        "text": chunk["text"],
                    }
                )

        scored_results.sort(
            key=lambda result: (-result["score"], result["chunk_id"])
        )
        return scored_results[:selected_top_k]


def build_parser() -> argparse.ArgumentParser:
    default_knowledge_base = (
        Path(__file__).resolve().parent
        / "knowledge_base"
        / "No_Safe_Circle_GDD_RAG.json"
    )

    parser = argparse.ArgumentParser(
        description="Retrieve targeted No Safe Circle GDD chunks."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {RETRIEVER_VERSION}")
    parser.add_argument("query", help="Natural-language retrieval query")
    parser.add_argument(
        "--knowledge-base",
        type=Path,
        default=default_knowledge_base,
        help="Path to the RAG JSON knowledge base",
    )
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--domain", default=None)
    parser.add_argument(
        "--include-noncanonical",
        action="store_true",
        help="Include chunks that are not marked canonical",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a text report",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        retriever = GDDRetriever(args.knowledge_base)
        results = retriever.retrieve(
            query=args.query,
            top_k=args.top_k,
            domain=args.domain,
            canonical_only=not args.include_noncanonical,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "query": args.query,
                    "result_count": len(results),
                    "results": results,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(f"Query: {args.query}")
    print(f"Results: {len(results)}")
    print()

    for index, result in enumerate(results, start=1):
        print(
            f"{index}. {result['chunk_id']} | "
            f"{result['title']} | score={result['score']}"
        )
        print(f"   Section: {result['section']}")
        if result["subsection"]:
            print(f"   Subsection: {result['subsection']}")
        print(f"   Matched terms: {', '.join(result['matched_terms'])}")
        print(f"   Source: {result['source']['file']}")
        print(f"   Text: {result['text']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
