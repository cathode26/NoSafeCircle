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
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "does", "do",
    "for", "from", "happens", "how", "in", "into", "is", "it", "of", "on",
    "or", "should", "that", "the", "their", "this", "to", "what", "when",
    "where", "which", "who", "why", "with", "after",
}

FIELD_WEIGHTS = {
    "title": 4.0,
    "section": 2.0,
    "subsection": 2.5,
    "entities": 5.0,
    "keywords": 4.0,
    "text": 1.0,
}

PHRASE_WEIGHTS = {
    2: 3.5,
    3: 7.5,
    4: 12.0,
}

QUERY_COVERAGE_WEIGHT = 25.0


def stem_token(token: str) -> str:
    """Apply a small deterministic stemmer suitable for this compact GDD."""
    value = token.lower()

    if len(value) > 4 and value.endswith("ies"):
        value = value[:-3] + "y"

    if len(value) > 5 and value.endswith("ly"):
        value = value[:-2]

    if len(value) > 5 and value.endswith("ing"):
        value = value[:-3]
    elif len(value) > 4 and value.endswith("ed"):
        value = value[:-2]

    if len(value) > 4 and value.endswith("es"):
        value = value[:-2]
    elif len(value) > 3 and value.endswith("s"):
        value = value[:-1]

    return value


def tokenize(value: str) -> list[str]:
    """Normalize text into searchable stemmed tokens and remove stop words."""
    return [
        stem_token(token)
        for token in TOKEN_PATTERN.findall(value or "")
        if token.lower() not in STOP_WORDS
    ]


def raw_tokens(value: str) -> list[str]:
    """Normalize text for readable contiguous phrase matching."""
    return [token.lower() for token in TOKEN_PATTERN.findall(value or "")]


def normalize_phrase(value: str) -> str:
    """Normalize a phrase for metadata matching."""
    return " ".join(tokenize(value))


def field_text(chunk: dict[str, Any], field: str) -> str:
    value = chunk.get(field)
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def build_ngrams(tokens: list[str], minimum: int = 2, maximum: int = 4) -> list[str]:
    phrases: list[str] = []
    upper = min(maximum, len(tokens))

    for size in range(minimum, upper + 1):
        for index in range(len(tokens) - size + 1):
            phrase_tokens = tokens[index:index + size]
            content_tokens = [
                token for token in phrase_tokens if token not in STOP_WORDS
            ]

            # Avoid noisy phrases such as "the player" or "breaks and".
            if (
                len(content_tokens) >= 2
                and phrase_tokens[0] not in STOP_WORDS
                and phrase_tokens[-1] not in STOP_WORDS
            ):
                phrases.append(" ".join(phrase_tokens))

    return phrases


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
    def _metadata_boost(query_phrase: str, chunk: dict[str, Any]) -> float:
        score = 0.0

        title = normalize_phrase(field_text(chunk, "title"))
        if title and title in query_phrase:
            score += 8.0

        for entity in chunk.get("entities", []):
            normalized_entity = normalize_phrase(str(entity))
            if normalized_entity and normalized_entity in query_phrase:
                score += 6.0

        for keyword in chunk.get("keywords", []):
            normalized_keyword = normalize_phrase(str(keyword))
            if normalized_keyword and normalized_keyword in query_phrase:
                score += 4.0

        return score

    @staticmethod
    def _phrase_score(
        query_phrases: list[str],
        chunk: dict[str, Any],
    ) -> tuple[float, list[str]]:
        combined_text = " ".join(
            field_text(chunk, field) for field in FIELD_WEIGHTS
        )
        normalized_chunk = " ".join(raw_tokens(combined_text))

        score = 0.0
        matched_phrases: list[str] = []

        for phrase in query_phrases:
            if phrase in normalized_chunk:
                phrase_length = len(phrase.split())
                score += PHRASE_WEIGHTS[phrase_length]
                matched_phrases.append(phrase)

        return score, matched_phrases

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
        unique_query_terms = set(query_tokens)
        query_phrases = build_ngrams(raw_tokens(query))

        scored_results: list[dict[str, Any]] = []

        for chunk in chunks:
            score = self._metadata_boost(normalized_query, chunk)
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

            phrase_score, matched_phrases = self._phrase_score(
                query_phrases,
                chunk,
            )
            score += phrase_score

            query_coverage = (
                len(matched_terms) / len(unique_query_terms)
                if unique_query_terms
                else 0.0
            )
            score += query_coverage * QUERY_COVERAGE_WEIGHT

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
                        "matched_phrases": matched_phrases,
                        "query_coverage": round(query_coverage, 4),
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
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {RETRIEVER_VERSION}",
    )
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
                    "retriever_version": RETRIEVER_VERSION,
                    "query": args.query,
                    "result_count": len(results),
                    "results": results,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(f"Retriever version: {RETRIEVER_VERSION}")
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
        print(
            "   Matched phrases: "
            + (
                ", ".join(result["matched_phrases"])
                if result["matched_phrases"]
                else "(none)"
            )
        )
        print(f"   Query coverage: {result['query_coverage']:.0%}")
        print(f"   Source: {result['source']['file']}")
        print(f"   Text: {result['text']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())