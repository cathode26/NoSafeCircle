#!/usr/bin/env python3
"""Replay one immutable decomposition candidate through full-context and GDDRAG reviewers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for _module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))

from Pipeline.AgentRuntime.contracts import ContractValidationError
from Pipeline.AgentRuntime.json_values import thaw_json
from Pipeline.TaskExecution.contracts import TaskContractIdentity
from TaskDecomposition.context_builder import (
    DecompositionPreflightError,
    build_context,
    capture_clean_source,
    require_output_disjoint,
    require_physical_read_only,
    source_revalidation_reasons,
)
from TaskDecomposition.contracts import (
    DecompositionContractError,
)
from TaskDecomposition.gdd_rag_review_context import (
    DEFAULT_MAX_CHUNKS,
    DEFAULT_MAX_TEXT_CHARS,
    DEFAULT_TOP_K,
    build_review_rag_context,
    validate_current_review_retriever,
)
from TaskDecomposition.live_decomposition import (
    ProgressReporter,
    ProviderFactory,
    _read_only_rejection_reasons,
    _validated_provider_bundle,
    heartbeat_interval,
    publish_json_no_overwrite,
    publish_text_no_overwrite,
)
from TaskDecomposition.policy import DecompositionPolicyError
from TaskDecomposition.review_contracts import (
    DecompositionReviewContractError,
)
from TaskDecomposition.review_policy import (
    DecompositionReviewPolicyError,
    validate_decomposition_review,
)
from TaskDecomposition.review_prompts import build_decomposition_reviewer_prompt
from TaskDecomposition.review_schemas import DECOMPOSITION_REVIEW_SCHEMA
from TaskDecomposition.run_decomposition import default_output_root
from TaskDecomposition.round_robin_decomposition import (
    CandidateSnapshot,
    _invoke_round,
    _validate_candidate,
    _validate_run_id,
    reviewer_budgets,
    validate_provider_order,
)
from graph_delta import GraphDeltaPlanningError


REVIEWER_REPLAY_SCHEMA_VERSION = "1.0"
ARM_NAMES = ("full", "rag")


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _new_run_id(task_id: str) -> str:
    stamp = time.strftime("%Y%m%dt%H%M%Sz", time.gmtime())
    return f"{task_id.lower()}-d1b2-replay-{stamp}-{os.urandom(4).hex()}"


def _validate_arm_order(value: Iterable[str]) -> tuple[str, str]:
    order = tuple(value)
    if len(order) != 2 or set(order) != set(ARM_NAMES):
        raise DecompositionPreflightError(
            "reviewer replay arm order must contain exactly `full` and `rag` once each"
        )
    return order[0], order[1]


def _insert_rag_hints(prompt: str, artifact: dict[str, Any]) -> str:
    marker = "Return only the structured object required by the supplied output schema."
    if marker not in prompt:
        raise DecompositionPreflightError(
            "D1B.2 reviewer prompt marker changed; replay refuses ambiguous RAG injection"
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


def _read_candidate(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise DecompositionPreflightError(
            f"candidate JSON could not be read: {path}: {exc}"
        ) from exc
    try:
        value = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecompositionPreflightError(
            f"candidate must be valid UTF-8 JSON: {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise DecompositionPreflightError(
            "candidate JSON root must be an object"
        )
    return value, hashlib.sha256(raw_bytes).hexdigest()


def _prompt_identity(prompt: str) -> dict[str, Any]:
    raw = prompt.encode("utf-8")
    return {
        "utf8_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _candidate_artifacts(
    directory: Path,
    candidate: CandidateSnapshot,
    *,
    prefix: str,
) -> dict[str, str | None]:
    result_name = f"{prefix}_candidate.json"
    identity_name = f"{prefix}_candidate_identity.json"
    graph_name = (
        f"{prefix}_candidate_graph_delta.json"
        if candidate.graph_delta is not None
        else None
    )
    publish_json_no_overwrite(directory / result_name, candidate.result.to_dict())
    publish_json_no_overwrite(directory / identity_name, candidate.summary())
    if graph_name is not None:
        publish_text_no_overwrite(
            directory / graph_name,
            candidate.graph_delta.canonical_json() + "\n",
        )
    return {
        "candidate_path": result_name,
        "candidate_identity_path": identity_name,
        "candidate_graph_delta_path": graph_name,
    }


def _usage_dict(agent_result: Any) -> dict[str, Any] | None:
    if agent_result is None or agent_result.usage is None:
        return None
    return agent_result.usage.to_dict()


def _numeric_comparison(
    full_value: int | float | None,
    rag_value: int | float | None,
) -> dict[str, Any] | None:
    if full_value is None or rag_value is None:
        return None
    full_number = float(full_value)
    rag_number = float(rag_value)
    delta = rag_number - full_number
    percent = None
    if full_number != 0:
        percent = (delta / full_number) * 100.0
    return {
        "full": full_value,
        "rag": rag_value,
        "rag_minus_full": delta,
        "percent_change_from_full": percent,
    }


def _comparison(arms: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    full = arms["full"]
    rag = arms["rag"]
    full_usage = full.get("usage") or {}
    rag_usage = rag.get("usage") or {}
    full_revised = full.get("revised_candidate") or {}
    rag_revised = rag.get("revised_candidate") or {}
    return {
        "same_provider": full.get("actual_provider") == rag.get("actual_provider"),
        "same_model": full.get("actual_model") == rag.get("actual_model"),
        "same_reviewed_candidate_sha256": (
            full.get("reviewed_candidate_sha256")
            == rag.get("reviewed_candidate_sha256")
        ),
        "verdicts_match": full.get("verdict") == rag.get("verdict"),
        "finding_categories_match": (
            full.get("finding_categories") == rag.get("finding_categories")
        ),
        "revised_candidate_sha256_match": (
            full_revised.get("sha256") == rag_revised.get("sha256")
        ),
        "prompt_utf8_bytes": _numeric_comparison(
            full["prompt"]["utf8_bytes"],
            rag["prompt"]["utf8_bytes"],
        ),
        "input_tokens": _numeric_comparison(
            full_usage.get("input_tokens"),
            rag_usage.get("input_tokens"),
        ),
        "output_tokens": _numeric_comparison(
            full_usage.get("output_tokens"),
            rag_usage.get("output_tokens"),
        ),
        "total_tokens": _numeric_comparison(
            full_usage.get("total_tokens"),
            rag_usage.get("total_tokens"),
        ),
        "estimated_cost_usd": _numeric_comparison(
            full_usage.get("estimated_cost_usd"),
            rag_usage.get("estimated_cost_usd"),
        ),
        "provider_duration_seconds": _numeric_comparison(
            full.get("provider_duration_seconds"),
            rag.get("provider_duration_seconds"),
        ),
        "wall_duration_seconds": _numeric_comparison(
            full.get("wall_duration_seconds"),
            rag.get("wall_duration_seconds"),
        ),
        "interpretation": (
            "This is a controlled candidate replay. Generator variance is removed. "
            "Provider stochasticity and sequential arm-order/cache effects are still possible; "
            "use --arm-order to run a second replay in reverse order when that distinction matters."
        ),
    }


def _review_prompt(
    *,
    context: Any,
    candidate: CandidateSnapshot,
    reviewer_provider: str,
) -> str:
    return build_decomposition_reviewer_prompt(
        context=context,
        candidate=candidate.result,
        candidate_sha256=candidate.sha256,
        candidate_author_provider=candidate.author_provider,
        reviewer_provider=reviewer_provider,
        round_number=2,
        graph_delta=candidate.graph_delta,
        review_history=(),
        unresolved_findings=(),
    )


def run_reviewer_replay_ab(
    *,
    source: Path,
    output_root: Path,
    task_id: str,
    candidate_path: Path,
    expected_candidate_sha256: str,
    candidate_author_provider: str = "codex",
    reviewer_provider: str = "claude",
    arm_order: Iterable[str] = ARM_NAMES,
    run_id: str | None = None,
    rag_top_k: int = DEFAULT_TOP_K,
    rag_max_chunks: int = DEFAULT_MAX_CHUNKS,
    rag_max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
    provider_factory: ProviderFactory | None = None,
    retriever: Any | None = None,
    _require_physical_read_only_source: bool = True,
) -> dict[str, Any]:
    """Review the same validated candidate once with full GDD and once with GDDRAG."""

    started = time.monotonic()
    if not re.fullmatch(r"NSC-[0-9]{3}", task_id):
        raise DecompositionPreflightError("task ID must match NSC-###")
    validate_provider_order((candidate_author_provider, reviewer_provider))
    selected_arm_order = _validate_arm_order(arm_order)
    if not re.fullmatch(r"[0-9a-f]{64}", expected_candidate_sha256):
        raise DecompositionPreflightError(
            "expected candidate SHA-256 must be 64 lowercase hexadecimal characters"
        )

    source_identity = capture_clean_source(source)
    safe_output_root = require_output_disjoint(
        source_identity.root,
        output_root,
    )
    if not _require_physical_read_only_source and provider_factory is None:
        raise DecompositionPreflightError(
            "writable-source test injection requires an injected provider factory"
        )
    if _require_physical_read_only_source:
        require_physical_read_only(source_identity.root)

    context, graph = build_context(source_identity, task_id)
    changed_during_context = source_revalidation_reasons(source_identity)
    if changed_during_context:
        raise DecompositionPreflightError("; ".join(changed_during_context))

    raw_candidate, candidate_file_sha256 = _read_candidate(candidate_path)
    try:
        candidate = _validate_candidate(
            raw_candidate,
            context_payload=context.to_dict(),
            graph=graph,
            author_provider=candidate_author_provider,
            version=1,
        )
    except (
        DecompositionContractError,
        DecompositionPolicyError,
        GraphDeltaPlanningError,
    ) as exc:
        raise DecompositionPreflightError(
            f"replay candidate failed deterministic validation: {exc}"
        ) from exc
    if candidate.sha256 != expected_candidate_sha256:
        raise DecompositionPreflightError(
            "candidate semantic SHA-256 mismatch: "
            f"expected {expected_candidate_sha256}, found {candidate.sha256}"
        )

    selected_run_id = _validate_run_id(run_id or _new_run_id(task_id))
    actual_retriever = (
        retriever
        if retriever is not None
        else validate_current_review_retriever(source_identity.root)
    )
    rag = build_review_rag_context(
        context=context,
        candidate=candidate.result,
        unresolved_findings=(),
        retriever=actual_retriever,
        top_k=rag_top_k,
        max_chunks=rag_max_chunks,
        max_text_chars=rag_max_text_chars,
    )

    prompts = {
        "full": _review_prompt(
            context=context,
            candidate=candidate,
            reviewer_provider=reviewer_provider,
        ),
        "rag": _insert_rag_hints(
            _review_prompt(
                context=rag.prompt_context,
                candidate=candidate,
                reviewer_provider=reviewer_provider,
            ),
            rag.artifact,
        ),
    }

    provider_bundle = _validated_provider_bundle(
        reviewer_provider,
        source_identity.root,
        provider_factory,
        role="decomposition_reviewer",
    )
    changed_during_provider_setup = source_revalidation_reasons(source_identity)
    if changed_during_provider_setup:
        raise DecompositionPreflightError(
            "; ".join(changed_during_provider_setup)
        )

    context_payload = context.to_dict()
    task_identity_payload = context_payload["selected_task"][
        "task_execution_identity"
    ]
    task_contract_identity = TaskContractIdentity(
        task_identity_payload["path"],
        task_identity_payload["revision"],
        task_identity_payload["sha256"],
    )
    context_paths = tuple(context_payload["context_paths"])
    reviewer_budget = reviewer_budgets()
    heartbeat_seconds = heartbeat_interval()

    safe_output_root.mkdir(parents=True, exist_ok=True)
    run_dir = safe_output_root / selected_run_id
    try:
        run_dir.mkdir()
    except FileExistsError as exc:
        raise DecompositionPreflightError(
            f"reviewer replay run directory already exists: {selected_run_id}"
        ) from exc

    reporter = ProgressReporter(
        run_dir / "progress.jsonl",
        run_id=selected_run_id,
        task_id=task_id,
        provider="reviewer-replay-ab",
        started=started,
    )
    reporter.emit(
        "run_started",
        f"D1B.2 controlled reviewer replay started: {task_id}",
        reviewer_provider=reviewer_provider,
        candidate_sha256=candidate.sha256,
        arm_order=list(selected_arm_order),
    )
    candidate_artifacts = _candidate_artifacts(
        run_dir,
        candidate,
        prefix="reviewed",
    )
    publish_json_no_overwrite(
        run_dir / "replay_request.json",
        {
            "schema_version": REVIEWER_REPLAY_SCHEMA_VERSION,
            "mode": "d1b2-controlled-reviewer-replay-ab",
            "task_id": task_id,
            "run_id": selected_run_id,
            "candidate_author_provider": candidate_author_provider,
            "reviewer_provider": reviewer_provider,
            "candidate_semantic_sha256": candidate.sha256,
            "candidate_file_sha256": candidate_file_sha256,
            "expected_candidate_sha256": expected_candidate_sha256,
            "source_identity": source_identity.to_context_dict(),
            "context_sha256": context.semantic_sha256,
            "arm_order": list(selected_arm_order),
            "rag_limits": {
                "top_k_per_query": rag_top_k,
                "max_unique_chunks": rag_max_chunks,
                "max_text_chars": rag_max_text_chars,
            },
            "authority": "review_only_not_applied",
        },
    )

    arm_results: dict[str, dict[str, Any]] = {}
    failure_reasons: list[str] = []

    for arm in selected_arm_order:
        arm_root = run_dir / "arms" / arm
        prompt = prompts[arm]
        prompt_identity = _prompt_identity(prompt)
        publish_json_no_overwrite(
            arm_root / "review_request.json",
            {
                "schema_version": REVIEWER_REPLAY_SCHEMA_VERSION,
                "arm": arm,
                "task_id": task_id,
                "reviewed_candidate": candidate.summary(),
                "reviewer_provider": reviewer_provider,
                "prompt": prompt_identity,
                "context_strategy": (
                    "full_committed_gdd"
                    if arm == "full"
                    else "authoritative_non_gdd_context_plus_bounded_current_gddrag_hints"
                ),
                "authority": "review_only_not_applied",
            },
        )
        if arm == "rag":
            publish_json_no_overwrite(
                arm_root / "gdd_rag_review_context.json",
                rag.artifact,
            )

        reporter.emit(
            "arm_started",
            f"D1B.2 controlled reviewer replay arm started: {arm}",
            arm=arm,
            prompt_utf8_bytes=prompt_identity["utf8_bytes"],
        )
        arm_started = time.monotonic()
        agent_result, invocation_exception, round_duration, invocation_id = _invoke_round(
            run_dir=arm_root,
            round_number=2,
            task_id=task_id,
            run_id=f"{selected_run_id}:{arm}",
            role="decomposition_reviewer",
            provider=reviewer_provider,
            provider_bundle=provider_bundle,
            prompt=prompt,
            output_schema=DECOMPOSITION_REVIEW_SCHEMA,
            context_paths=context_paths,
            task_contract_identity=task_contract_identity,
            budgets=reviewer_budget,
            heartbeat_seconds=heartbeat_seconds,
            reporter=reporter,
        )
        wall_duration = round(time.monotonic() - arm_started, 3)
        arm_rejections: list[str] = []
        if invocation_exception is not None:
            arm_rejections.append(
                "task-associated reviewer invocation failed: "
                f"{type(invocation_exception).__name__}: {invocation_exception}"
            )
        elif agent_result is None:
            arm_rejections.append(
                "task-associated reviewer invocation returned no AgentResult"
            )
        elif agent_result.status != "succeeded":
            arm_rejections.append(
                f"AgentResult failed ({agent_result.failure_classification}): "
                f"{agent_result.failure_message}"
            )
        else:
            arm_rejections.extend(_read_only_rejection_reasons(agent_result))
        arm_rejections.extend(source_revalidation_reasons(source_identity))

        summary: dict[str, Any] = {
            "schema_version": REVIEWER_REPLAY_SCHEMA_VERSION,
            "arm": arm,
            "status": "rejected",
            "reviewed_candidate_sha256": candidate.sha256,
            "prompt": prompt_identity,
            "requested_provider": reviewer_provider,
            "actual_provider": (
                agent_result.provider if agent_result is not None else None
            ),
            "actual_model": (
                agent_result.model if agent_result is not None else None
            ),
            "agent_status": (
                agent_result.status if agent_result is not None else "failed"
            ),
            "agent_failure_classification": (
                agent_result.failure_classification
                if agent_result is not None
                else "internal_error"
            ),
            "provider_duration_seconds": (
                agent_result.duration_seconds
                if agent_result is not None
                else None
            ),
            "round_duration_seconds": round_duration,
            "wall_duration_seconds": wall_duration,
            "usage": _usage_dict(agent_result),
            "verdict": None,
            "review_summary": None,
            "finding_ids": [],
            "finding_categories": [],
            "unresolved_finding_ids": [],
            "revised_candidate": None,
            "invocation_id": invocation_id,
            "agent_runtime_result_path": (
                f"rounds/02/agent_runtime/{invocation_id}/result.json"
                if (
                    arm_root
                    / "rounds"
                    / "02"
                    / "agent_runtime"
                    / invocation_id
                    / "result.json"
                ).is_file()
                else None
            ),
            "rejection_reasons": arm_rejections,
            "authority": "review_only_not_applied",
        }

        if not arm_rejections and agent_result is not None:
            try:
                review, next_unresolved = validate_decomposition_review(
                    thaw_json(agent_result.structured_output),
                    expected_candidate_sha256=candidate.sha256,
                    round_number=2,
                    prior_unresolved_findings={},
                    all_prior_finding_ids=set(),
                )
                publish_json_no_overwrite(
                    arm_root / "review.json",
                    review.to_dict(),
                )
                summary["status"] = "valid_review"
                summary["verdict"] = review.verdict
                summary["review_summary"] = review.summary
                summary["finding_ids"] = [
                    finding.finding_id for finding in review.findings
                ]
                summary["finding_categories"] = sorted(
                    finding.category for finding in review.findings
                )
                summary["unresolved_finding_ids"] = sorted(next_unresolved)
                if review.revised_decomposition is not None:
                    revised = _validate_candidate(
                        review.revised_decomposition,
                        context_payload=context_payload,
                        graph=graph,
                        author_provider=reviewer_provider,
                        version=2,
                    )
                    revised_paths = _candidate_artifacts(
                        arm_root,
                        revised,
                        prefix="revised",
                    )
                    summary["revised_candidate"] = {
                        **revised.summary(),
                        **revised_paths,
                    }
            except (
                DecompositionReviewContractError,
                DecompositionReviewPolicyError,
                DecompositionContractError,
                DecompositionPolicyError,
                GraphDeltaPlanningError,
            ) as exc:
                summary["rejection_reasons"] = [
                    f"review/revision deterministic validation failed: {exc}"
                ]

        publish_json_no_overwrite(
            arm_root / "arm_result.json",
            summary,
        )
        arm_results[arm] = summary
        reporter.emit(
            "arm_completed",
            f"D1B.2 controlled reviewer replay arm completed: {arm}",
            arm=arm,
            status=summary["status"],
            verdict=summary["verdict"],
            wall_duration_seconds=wall_duration,
        )
        if summary["status"] != "valid_review":
            failure_reasons.extend(
                f"{arm}: {reason}" for reason in summary["rejection_reasons"]
            )
            break

    final_source_reasons = source_revalidation_reasons(source_identity)
    failure_reasons.extend(
        reason for reason in final_source_reasons
        if reason not in failure_reasons
    )

    comparison = None
    if set(arm_results) == set(ARM_NAMES) and not failure_reasons:
        comparison = _comparison(arm_results)
        if not comparison["same_provider"]:
            failure_reasons.append(
                "controlled replay arms did not use the same actual provider"
            )
        if not comparison["same_model"]:
            failure_reasons.append(
                "controlled replay arms did not use the same actual model"
            )
        if not comparison["same_reviewed_candidate_sha256"]:
            failure_reasons.append(
                "controlled replay arms did not review the same candidate"
            )

    run_status = (
        "comparison_ready"
        if comparison is not None and not failure_reasons
        else "rejected"
    )
    final = {
        "schema_version": REVIEWER_REPLAY_SCHEMA_VERSION,
        "mode": "d1b2-controlled-reviewer-replay-ab",
        "run_id": selected_run_id,
        "task_id": task_id,
        "run_status": run_status,
        "source_identity": source_identity.to_context_dict(),
        "context_sha256": context.semantic_sha256,
        "candidate": {
            **candidate.summary(),
            "input_file_sha256": candidate_file_sha256,
            **candidate_artifacts,
        },
        "candidate_author_provider": candidate_author_provider,
        "reviewer_provider": reviewer_provider,
        "arm_order": list(selected_arm_order),
        "arms": arm_results,
        "comparison": comparison,
        "failure_reasons": failure_reasons,
        "duration_seconds": time.monotonic() - started,
        "human_next_step": (
            "Compare verdicts, findings, revised-candidate identities, prompt bytes, token/cache accounting, cost, and duration. No graph change has been applied."
            if run_status == "comparison_ready"
            else "Inspect the rejected arm artifacts and failure_reasons. No graph change has been applied."
        ),
        "authority": "review_only_not_applied",
    }
    reporter.emit(
        "run_completed",
        f"D1B.2 controlled reviewer replay completed: {run_status}",
        status=run_status,
        duration_seconds=round(final["duration_seconds"], 3),
    )
    publish_json_no_overwrite(
        run_dir / "reviewer_replay_result.json",
        final,
    )
    return final


def _provider_order(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--expected-candidate-sha256", required=True)
    parser.add_argument("--candidate-author-provider", default="codex")
    parser.add_argument("--reviewer-provider", default="claude")
    parser.add_argument(
        "--arm-order",
        default="full,rag",
        help="Exactly full,rag or rag,full",
    )
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--rag-top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--rag-max-chunks", type=int, default=DEFAULT_MAX_CHUNKS)
    parser.add_argument(
        "--rag-max-text-chars",
        type=int,
        default=DEFAULT_MAX_TEXT_CHARS,
    )
    args = parser.parse_args()
    source = args.source.resolve()
    output_root = (args.output_root or default_output_root(source)).resolve()
    try:
        result = run_reviewer_replay_ab(
            source=source,
            output_root=output_root,
            task_id=args.task_id,
            candidate_path=args.candidate.resolve(),
            expected_candidate_sha256=args.expected_candidate_sha256,
            candidate_author_provider=args.candidate_author_provider,
            reviewer_provider=args.reviewer_provider,
            arm_order=_provider_order(args.arm_order),
            run_id=args.run_id,
            rag_top_k=args.rag_top_k,
            rag_max_chunks=args.rag_max_chunks,
            rag_max_text_chars=args.rag_max_text_chars,
        )
    except (
        DecompositionPreflightError,
        ContractValidationError,
        OSError,
    ) as exc:
        print(f"Controlled reviewer replay blocked: {exc}", file=sys.stderr)
        return 2
    print(_json(result), end="")
    return 0 if result["run_status"] == "comparison_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
