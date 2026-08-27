"""Deterministic bounded GDDRAG context for D1B.2 reviewer A/B runs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable

from TaskDecomposition.context_builder import ContextPackage, DecompositionPreflightError
from TaskDecomposition.contracts import DecompositionResult
from TaskDecomposition.review_contracts import ReviewFinding


ROOT = Path(__file__).resolve().parents[2]
GDDRAG_ROOT = ROOT / "Pipeline" / "GDDRAG"
if str(GDDRAG_ROOT) not in sys.path:
    sys.path.append(str(GDDRAG_ROOT))

from index_builder import DEFAULT_KNOWLEDGE_BASE_PATH  # type: ignore  # noqa: E402
from retrieval import GDDRetriever  # type: ignore  # noqa: E402


RAG_REVIEW_CONTEXT_SCHEMA_VERSION = "1.0"
DEFAULT_TOP_K = 3
DEFAULT_MAX_CHUNKS = 10
DEFAULT_MAX_TEXT_CHARS = 16000


@dataclass(frozen=True)
class ReviewRagContext:
    prompt_context: ContextPackage
    artifact: dict[str, Any]


def _strict_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _require_positive(value: int, label: str) -> int:
    if type(value) is not int or value < 1:
        raise DecompositionPreflightError(f"{label} must be a positive integer")
    return value


def validate_current_review_retriever(source_root: Path = ROOT) -> GDDRetriever:
    """Fail before provider work when the committed production RAG index is stale/invalid."""

    source_root = Path(source_root)
    knowledge_base = source_root / "Pipeline" / "GDDRAG" / "knowledge_base" / "No_Safe_Circle_GDD_RAG.json"
    canonical_gdd = source_root / "Docs" / "GDD" / "No_Safe_Circle_GDD.md"
    try:
        return GDDRetriever(knowledge_base, source_path=canonical_gdd)
    except (FileNotFoundError, ValueError) as exc:
        raise DecompositionPreflightError(
            "D1B.2 RAG reviewer mode requires a current valid production GDDRAG index. "
            "Run `python Pipeline/GDDRAG/gddctl.py rebuild` and commit the regenerated index before retrying. "
            f"Details: {exc}"
        ) from exc


def _entry_query(prefix: str, entry: dict[str, Any]) -> str:
    return " ".join(
        part.strip()
        for part in (
            prefix,
            str(entry.get("reference") or ""),
            str(entry.get("requirement") or ""),
        )
        if part and part.strip()
    )


def build_review_queries(
    *,
    context: ContextPackage,
    candidate: DecompositionResult,
    unresolved_findings: Iterable[ReviewFinding],
) -> list[dict[str, str]]:
    """Derive stable review searches from authoritative task/candidate semantics."""

    payload = context.to_dict()
    parent = payload["selected_task"]["contract"]
    queries: list[dict[str, str]] = []

    parent_specs = (
        ("acceptance_criteria", "criterion_id", "parent-ac"),
        ("completion_gates", "gate_id", "parent-val"),
        ("downstream_integration_obligations", "obligation_id", "parent-int"),
    )
    for field, id_field, tag in parent_specs:
        for entry in parent.get(field, []):
            entry_id = str(entry.get(id_field) or "unknown").lower()
            queries.append(
                {
                    "query_id": f"{tag}-{entry_id}",
                    "source": f"{parent['id']}/{entry.get(id_field)}",
                    "query": _entry_query(parent["title"], entry),
                }
            )

    for child in candidate.children:
        child_parts = [child.title, child.basis, child.source_scope]
        for collection in (
            child.acceptance_criteria,
            child.completion_gates,
            child.downstream_integration_obligations,
        ):
            child_parts.extend(entry.requirement for entry in collection)
        child_parts.extend(entry.requirement for entry in child.gdd_evidence)
        queries.append(
            {
                "query_id": f"child-{child.local_key}",
                "source": f"proposed:{child.local_key}",
                "query": " ".join(part.strip() for part in child_parts if part.strip()),
            }
        )

    dependents = {
        item["id"]: item
        for item in payload["graph_neighborhood"]["direct_dependent_contracts"]
    }
    for rewrite in candidate.inbound_dependency_rewrites:
        dependent = dependents.get(rewrite.dependent_task_id, {})
        title = str(dependent.get("title") or rewrite.dependent_task_id)
        queries.append(
            {
                "query_id": f"rewrite-{rewrite.dependent_task_id.lower()}",
                "source": rewrite.dependent_task_id,
                "query": " ".join(
                    (
                        title,
                        rewrite.reason,
                        " ".join(rewrite.replacement_local_keys),
                    )
                ),
            }
        )

    for finding in unresolved_findings:
        queries.append(
            {
                "query_id": f"finding-{finding.finding_id}",
                "source": finding.finding_id,
                "query": " ".join(
                    (
                        " ".join(finding.affected_contracts),
                        finding.problem,
                        finding.required_resolution,
                    )
                ),
            }
        )

    seen_ids: set[str] = set()
    unique: list[dict[str, str]] = []
    for query in queries:
        query_id = query["query_id"]
        if query_id in seen_ids:
            raise DecompositionPreflightError(
                f"deterministic RAG review query ID collision: {query_id}"
            )
        seen_ids.add(query_id)
        if query["query"].strip():
            unique.append(query)
    return unique


def _prompt_context_without_full_gdd(context: ContextPackage) -> ContextPackage:
    payload = context.to_dict()
    canonical = deepcopy(payload["canonical_gdd"])
    canonical.pop("full_committed_utf8_text", None)
    canonical["review_delivery"] = (
        "Full GDD text intentionally omitted from this reviewer prompt for the explicit RAG A/B mode. "
        "The path and exact committed hash remain authoritative; bounded current-index GDDRAG hints are supplied separately. "
        "Repository read/search remains available when a potentially blocking canon question is not answered by the hints."
    )
    payload["canonical_gdd"] = canonical
    payload["authority_notes"]["gdd_rag"] = (
        "Retrieved GDDRAG chunks are navigation hints, not exhaustive canon. Missing retrieval is never proof that a rule does not exist."
    )
    return ContextPackage.from_payload(payload)


def build_review_rag_context(
    *,
    context: ContextPackage,
    candidate: DecompositionResult,
    unresolved_findings: Iterable[ReviewFinding],
    retriever: Any,
    top_k: int = DEFAULT_TOP_K,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
) -> ReviewRagContext:
    top_k = _require_positive(top_k, "RAG top_k")
    max_chunks = _require_positive(max_chunks, "RAG max_chunks")
    max_text_chars = _require_positive(max_text_chars, "RAG max_text_chars")
    unresolved = tuple(unresolved_findings)
    queries = build_review_queries(
        context=context,
        candidate=candidate,
        unresolved_findings=unresolved,
    )

    per_query: list[tuple[dict[str, str], list[dict[str, Any]]]] = []
    for query in queries:
        results = retriever.retrieve(query["query"], top_k=top_k)
        per_query.append((query, results))

    selected: list[dict[str, Any]] = []
    selected_by_chunk: dict[str, dict[str, Any]] = {}
    text_chars = 0
    for rank in range(top_k):
        for query, results in per_query:
            if rank >= len(results):
                continue
            result = results[rank]
            chunk_id = str(result["chunk_id"])
            existing = selected_by_chunk.get(chunk_id)
            if existing is not None:
                if query["query_id"] not in existing["query_ids"]:
                    existing["query_ids"].append(query["query_id"])
                continue
            if len(selected) >= max_chunks:
                continue
            text = str(result["text"])
            if selected and text_chars + len(text) > max_text_chars:
                continue
            record = {
                "chunk_id": chunk_id,
                "title": result["title"],
                "section": result["section"],
                "subsection": result.get("subsection"),
                "score": result["score"],
                "source": result["source"],
                "query_ids": [query["query_id"]],
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "text": text,
            }
            selected.append(record)
            selected_by_chunk[chunk_id] = record
            text_chars += len(text)

    payload = context.to_dict()
    canonical = payload["canonical_gdd"]
    retriever_data = getattr(retriever, "data", {})
    indexed_source = retriever_data.get("source", {}) if isinstance(retriever_data, dict) else {}
    artifact = {
        "schema_version": RAG_REVIEW_CONTEXT_SCHEMA_VERSION,
        "mode": "d1b2-reviewer-gdd-rag-ab",
        "authority": "navigation_hints_not_canon_replacement",
        "canonical_gdd": {
            "path": canonical["path"],
            "context_exact_byte_sha256": canonical["exact_byte_sha256"],
            "indexed_source_sha256": indexed_source.get("sha256"),
        },
        "limits": {
            "top_k_per_query": top_k,
            "max_unique_chunks": max_chunks,
            "max_text_chars": max_text_chars,
            "selected_text_chars": text_chars,
        },
        "queries": queries,
        "hits": selected,
        "review_instruction": (
            "Use these current-index chunks as high-signal navigation hints. They are not exhaustive. "
            "The committed task contracts and canonical GDD remain authoritative; if a potentially blocking canon question is not answered here, use repository read/search on the canonical GDD before concluding the rule is absent."
        ),
    }
    artifact["semantic_sha256"] = hashlib.sha256(
        _strict_json(artifact).encode("utf-8")
    ).hexdigest()
    return ReviewRagContext(
        prompt_context=_prompt_context_without_full_gdd(context),
        artifact=artifact,
    )
