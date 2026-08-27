from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from TaskDecomposition.context_builder import build_context, capture_clean_source
from TaskDecomposition.gdd_rag_review_context import build_review_rag_context
from TaskDecomposition.policy import validate_decomposition_result
from TaskDecomposition.review_contracts import ReviewFinding
from TaskDecomposition.tests.test_support import create_repository, decomposed_result


class FakeRetriever:
    def __init__(self) -> None:
        self.data = {"source": {"sha256": "f" * 64}}
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        self.calls.append((query, top_k))
        shared = {
            "chunk_id": "nsc-gdd-001",
            "title": "Shared Canon",
            "section": "Synthetic",
            "subsection": None,
            "score": 50.0,
            "source": {
                "file": "Docs/GDD/No_Safe_Circle_GDD.md",
                "start_line": 1,
                "end_line": 3,
            },
            "text": "Shared relevant canon.",
        }
        unique = {
            "chunk_id": f"nsc-gdd-{len(self.calls) + 1:03d}",
            "title": "Specific Canon",
            "section": "Synthetic",
            "subsection": None,
            "score": 25.0,
            "source": {
                "file": "Docs/GDD/No_Safe_Circle_GDD.md",
                "start_line": 4,
                "end_line": 5,
            },
            "text": "Specific bounded canon for this query.",
        }
        return [shared, unique][:top_k]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nsc-d1b2-rag-context-") as temp_text:
        source = Path(temp_text) / "source"
        tasks = create_repository(source)
        identity = capture_clean_source(source)
        context, graph = build_context(identity, "NSC-010")
        parent = tasks["NSC-010"]
        candidate = validate_decomposition_result(
            decomposed_result(parent),
            parent_task=parent,
            existing_reconciliation_keys=graph.plan.id_map.keys(),
        )
        finding = ReviewFinding(
            "round-02-synthetic-ownership",
            "blocking",
            "duplicate_responsibility",
            ("NSC-010", "proposed:bounded-child"),
            "Synthetic ownership question.",
            "Confirm canon ownership.",
        )
        retriever = FakeRetriever()
        rag = build_review_rag_context(
            context=context,
            candidate=candidate,
            unresolved_findings=(finding,),
            retriever=retriever,
            top_k=2,
            max_chunks=4,
            max_text_chars=500,
        )

        original = context.to_dict()
        prompt_context = rag.prompt_context.to_dict()
        assert "full_committed_utf8_text" in original["canonical_gdd"]
        assert "full_committed_utf8_text" not in prompt_context["canonical_gdd"]
        assert prompt_context["canonical_gdd"]["path"] == original["canonical_gdd"]["path"]
        assert prompt_context["canonical_gdd"]["exact_byte_sha256"] == original["canonical_gdd"]["exact_byte_sha256"]
        assert "not exhaustive" in prompt_context["authority_notes"]["gdd_rag"]

        artifact = rag.artifact
        assert artifact["authority"] == "navigation_hints_not_canon_replacement"
        assert artifact["canonical_gdd"]["indexed_source_sha256"] == "f" * 64
        assert 1 <= len(artifact["hits"]) <= 4
        assert artifact["limits"]["selected_text_chars"] <= 500
        assert artifact["hits"][0]["chunk_id"] == "nsc-gdd-001"
        assert len(artifact["hits"][0]["query_ids"]) > 1
        query_ids = {query["query_id"] for query in artifact["queries"]}
        assert "parent-ac-ac-001" in query_ids
        assert "parent-val-val-001" in query_ids
        assert "parent-int-int-001" in query_ids
        assert "child-bounded-child" in query_ids
        assert "rewrite-nsc-012" in query_ids
        assert "finding-round-02-synthetic-ownership" in query_ids
        assert retriever.calls and all(top_k == 2 for _, top_k in retriever.calls)
        assert len(artifact["semantic_sha256"]) == 64

    print("gdd_rag_review_context_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
