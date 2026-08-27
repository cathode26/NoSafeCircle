#!/usr/bin/env python3
"""Run D1B.2 with full generator context and bounded GDDRAG reviewer context."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for _module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))

from Pipeline.AgentRuntime.contracts import ContractValidationError
from TaskDecomposition.context_builder import DecompositionPreflightError
from TaskDecomposition.gdd_rag_review_context import (
    DEFAULT_MAX_CHUNKS,
    DEFAULT_MAX_TEXT_CHARS,
    DEFAULT_TOP_K,
    build_review_rag_context,
    validate_current_review_retriever,
)
from TaskDecomposition.live_decomposition import publish_json_no_overwrite
from TaskDecomposition.run_decomposition import default_output_root
import TaskDecomposition.round_robin_decomposition as round_robin
from TaskDecomposition.review_prompts import (
    build_decomposition_reviewer_prompt as full_context_reviewer_prompt,
)


def _provider_order(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _new_run_id(task_id: str) -> str:
    stamp = time.strftime("%Y%m%dt%H%M%Sz", time.gmtime())
    return f"{task_id.lower()}-d1b2-rag-{stamp}-{os.urandom(4).hex()}"


def _insert_rag_hints(prompt: str, artifact: dict[str, Any]) -> str:
    marker = "Return only the structured object required by the supplied output schema."
    if marker not in prompt:
        raise DecompositionPreflightError(
            "D1B.2 reviewer prompt marker changed; RAG A/B wrapper refuses to inject hints ambiguously"
        )
    block = (
        "BEGIN DETERMINISTIC GDDRAG REVIEW HINTS\n"
        + json.dumps(
            artifact,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\nEND DETERMINISTIC GDDRAG REVIEW HINTS\n\n"
    )
    return prompt.replace(marker, block + marker, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument(
        "--providers",
        default=os.getenv(
            "NSC_DECOMPOSITION_ROUND_ROBIN_PROVIDERS",
            "codex,claude",
        ),
        help="Comma-separated provider rotation; default: codex,claude",
    )
    parser.add_argument("--max-calls", type=int)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--rag-top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--rag-max-chunks", type=int, default=DEFAULT_MAX_CHUNKS)
    parser.add_argument("--rag-max-text-chars", type=int, default=DEFAULT_MAX_TEXT_CHARS)
    args = parser.parse_args()

    source = args.source.resolve()
    output_root = (args.output_root or default_output_root(source)).resolve()
    run_id = args.run_id or _new_run_id(args.task_id)

    try:
        # This intentionally happens before the core run creates output or spends a
        # provider call. A stale/invalid index makes the A/B experiment meaningless.
        retriever = validate_current_review_retriever(source)

        original_builder = round_robin.build_decomposition_reviewer_prompt
        if original_builder is not full_context_reviewer_prompt:
            raise DecompositionPreflightError(
                "unexpected D1B.2 reviewer prompt binding; refusing nested/ambiguous RAG wrapping"
            )

        run_dir = output_root / run_id
        rag_round_artifacts: list[str] = []

        def rag_reviewer_prompt(**kwargs: Any) -> str:
            # Core passes unresolved findings as a generator. Materialize it once so
            # both deterministic retrieval and the actual reviewer prompt see the
            # identical unresolved-finding set.
            unresolved = tuple(kwargs["unresolved_findings"])
            rag = build_review_rag_context(
                context=kwargs["context"],
                candidate=kwargs["candidate"],
                unresolved_findings=unresolved,
                retriever=retriever,
                top_k=args.rag_top_k,
                max_chunks=args.rag_max_chunks,
                max_text_chars=args.rag_max_text_chars,
            )
            prompt_kwargs = dict(kwargs)
            prompt_kwargs["context"] = rag.prompt_context
            prompt_kwargs["unresolved_findings"] = unresolved
            prompt = full_context_reviewer_prompt(**prompt_kwargs)
            prompt = _insert_rag_hints(prompt, rag.artifact)

            round_number = int(kwargs["round_number"])
            artifact_path = run_dir / "rounds" / f"{round_number:02d}-gdd-rag-review-context.json"
            publish_json_no_overwrite(artifact_path, rag.artifact)
            rag_round_artifacts.append(str(artifact_path.relative_to(run_dir)).replace("\\", "/"))
            return prompt

        round_robin.build_decomposition_reviewer_prompt = rag_reviewer_prompt
        try:
            result = round_robin.run_round_robin_decomposition(
                source=source,
                output_root=output_root,
                task_id=args.task_id,
                provider_order=_provider_order(args.providers),
                max_calls=args.max_calls,
                run_id=run_id,
            )
        finally:
            round_robin.build_decomposition_reviewer_prompt = original_builder

        manifest = {
            "schema_version": "1.0",
            "mode": "d1b2-reviewer-gdd-rag-ab",
            "task_id": args.task_id,
            "run_id": run_id,
            "generator_context": "full_original_d1b2_context",
            "reviewer_context": "authoritative_non_gdd_context_plus_bounded_current_gddrag_hints",
            "rag_limits": {
                "top_k_per_query": args.rag_top_k,
                "max_unique_chunks": args.rag_max_chunks,
                "max_text_chars": args.rag_max_text_chars,
            },
            "rag_round_artifacts": rag_round_artifacts,
            "run_status": result["run_status"],
            "calls_used": result["calls_used"],
            "authority": "review_only_not_applied",
        }
        publish_json_no_overwrite(run_dir / "gdd_rag_ab_manifest.json", manifest)
    except (DecompositionPreflightError, ContractValidationError, OSError) as exc:
        print(f"Round-robin RAG A/B decomposition blocked: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "gdd_rag_ab": manifest,
                "decomposition_run_result": result,
            },
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["run_status"] in {"review_ready", "needs_human"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
