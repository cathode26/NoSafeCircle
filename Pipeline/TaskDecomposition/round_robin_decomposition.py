"""Bounded cross-provider D1B.2 decomposition verification and refinement."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = ROOT / "Pipeline" / "TaskGraph"
for _module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))

from Pipeline.AgentRuntime.agent_runner import AgentRunner
from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.contracts import (
    AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
    AgentInvocationRequest,
    AgentResult,
    Budgets,
    ContractValidationError,
    WriteBoundaries,
)
from Pipeline.AgentRuntime.json_values import thaw_json
from Pipeline.AgentRuntime.provider_sessions import (
    ProviderSessionBinding,
    ProviderSessionLedger,
)
from Pipeline.TaskExecution.contracts import (
    TASK_EXECUTION_REQUEST_SCHEMA_VERSION,
    TaskContractIdentity,
    TaskExecutionRequest,
)
from Pipeline.TaskExecution.task_runner import TaskExecutionRunner
from TaskDecomposition.context_builder import (
    ContextPackage,
    DecompositionPreflightError,
    SourceIdentity,
    build_context,
    capture_clean_source,
    require_output_disjoint,
    require_physical_read_only,
    source_revalidation_reasons,
)
from TaskDecomposition.contracts import (
    DecompositionContractError,
    DecompositionResult,
)
from TaskDecomposition.live_decomposition import (
    ProgressReporter,
    ProviderFactory,
    _read_only_rejection_reasons,
    _validated_provider_bundle,
    decomposer_budgets,
    heartbeat_interval,
    publish_json_no_overwrite,
    publish_text_no_overwrite,
)
from TaskDecomposition.policy import (
    DecompositionPolicyError,
    validate_decomposition_result,
)
from TaskDecomposition.prompts import build_decomposer_prompt
from TaskDecomposition.review_contracts import (
    DecompositionReviewContractError,
    ReviewFinding,
)
from TaskDecomposition.review_policy import (
    DecompositionReviewPolicyError,
    validate_decomposition_review,
)
from TaskDecomposition.review_prompts import build_decomposition_reviewer_prompt
from TaskDecomposition.review_schemas import DECOMPOSITION_REVIEW_SCHEMA
from TaskDecomposition.schemas import DECOMPOSITION_RESULT_SCHEMA
from TaskDecomposition.session_pool_support import (
    DecompositionLeaseBundle,
    DecompositionSessionError,
    PooledRoundSessions,
    assert_lease_matches_route,
    bind_lease_bundle_to_run,
    canonical_artifact_sha256,
    lease_key,
    pooled_round_evidence,
)
from graph_delta import GraphDeltaPlan, GraphDeltaPlanningError, plan_graph_delta


ROUND_ROBIN_RUN_RESULT_SCHEMA_VERSION = "1.0"
ROUND_RESULT_SCHEMA_VERSION = "1.0"
SUPPORTED_PROVIDERS = frozenset({"claude", "codex"})
_RUN_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
ProviderBundle = tuple[str, RuntimeConfiguration, Mapping[str, Any]]


@dataclass(frozen=True)
class CandidateSnapshot:
    version: int
    author_provider: str
    result: DecompositionResult
    graph_delta: GraphDeltaPlan | None
    sha256: str

    def summary(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "author_provider": self.author_provider,
            "sha256": self.sha256,
            "decision": self.result.decision,
            "graph_delta_plan_id": (
                self.graph_delta.plan_id if self.graph_delta is not None else None
            ),
        }


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
    nonce = os.urandom(6).hex()
    return f"{task_id.lower()}-d1b2-{stamp}-{nonce}"


def _validate_run_id(run_id: str) -> str:
    if type(run_id) is not str or not _RUN_ID_RE.fullmatch(run_id):
        raise DecompositionPreflightError(
            "run_id must be a lowercase ASCII slug of 1..64 characters"
        )
    return run_id


def validate_provider_order(providers: Iterable[str]) -> tuple[str, ...]:
    order = tuple(providers)
    if len(order) < 2:
        raise DecompositionPreflightError(
            "D1B.2 requires at least two provider positions."
        )
    if any(type(provider) is not str or provider not in SUPPORTED_PROVIDERS for provider in order):
        raise DecompositionPreflightError(
            "D1B.2 providers must be claude or codex."
        )
    if len(set(order)) < 2:
        raise DecompositionPreflightError(
            "D1B.2 requires at least two distinct providers."
        )
    for index, provider in enumerate(order):
        if provider == order[(index + 1) % len(order)]:
            raise DecompositionPreflightError(
                "Adjacent round-robin provider positions must be distinct, including the cycle boundary."
            )
    return order


def round_robin_call_limit(value: int | None = None) -> int:
    raw: Any = value
    if raw is None:
        raw = os.getenv("NSC_DECOMPOSITION_ROUND_ROBIN_MAX_CALLS", "4")
    try:
        limit = int(raw)
    except (TypeError, ValueError) as exc:
        raise DecompositionPreflightError(
            "round-robin max calls must be an integer"
        ) from exc
    if not 2 <= limit <= 12:
        raise DecompositionPreflightError(
            "round-robin max calls must be between 2 and 12"
        )
    return limit


def reviewer_budgets() -> Budgets:
    raw_turns = os.getenv("NSC_DECOMPOSITION_REVIEWER_TURN_LIMIT", "36")
    raw_timeout = os.getenv("NSC_DECOMPOSITION_REVIEWER_TIMEOUT_SECONDS", "1200")
    try:
        turns = int(raw_turns)
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise DecompositionPreflightError(
            "decomposition reviewer budget overrides must be positive finite values"
        ) from exc
    if not math.isfinite(timeout):
        raise DecompositionPreflightError(
            "decomposition reviewer timeout must be finite"
        )
    try:
        return Budgets(turns, timeout, None)
    except ContractValidationError as exc:
        raise DecompositionPreflightError(
            f"invalid decomposition reviewer budget override: {exc}"
        ) from exc


def candidate_sha256(result: DecompositionResult) -> str:
    return hashlib.sha256(result.canonical_json().encode("utf-8")).hexdigest()


def _validate_candidate(
    raw: Any,
    *,
    context_payload: dict[str, Any],
    graph: Any,
    author_provider: str,
    version: int,
) -> CandidateSnapshot:
    result = validate_decomposition_result(
        raw,
        parent_task=context_payload["selected_task"]["contract"],
        existing_reconciliation_keys=graph.plan.id_map.keys(),
    )
    graph_delta = None
    if result.decision == "decomposed":
        graph_delta = plan_graph_delta(graph, result.parent_task, result)
    return CandidateSnapshot(
        version,
        author_provider,
        result,
        graph_delta,
        candidate_sha256(result),
    )


def _round_invocation_id(
    task_id: str,
    run_id: str,
    round_number: int,
    role: str,
) -> str:
    role_slug = role.replace("_", "-")
    suffix = hashlib.sha256(
        f"{run_id}:{round_number}:{role}".encode("utf-8")
    ).hexdigest()[:12]
    return _validate_run_id(
        f"{task_id.lower()}-d1b2-r{round_number:02d}-{role_slug}-{suffix}"
    )


def _round_request(
    *,
    round_number: int,
    role: str,
    provider: str,
    invocation_id: str,
    candidate: CandidateSnapshot | None,
    unresolved_findings: Mapping[str, ReviewFinding],
) -> dict[str, Any]:
    return {
        "schema_version": ROUND_RESULT_SCHEMA_VERSION,
        "round_number": round_number,
        "role": role,
        "requested_provider": provider,
        "invocation_id": invocation_id,
        "reviewed_candidate": candidate.summary() if candidate is not None else None,
        "unresolved_finding_ids": sorted(unresolved_findings),
        "authority": "review_only_not_applied",
    }


def _run_request(
    *,
    run_id: str,
    task_id: str,
    provider_order: tuple[str, ...],
    max_calls: int,
    source: SourceIdentity,
    context: ContextPackage,
) -> dict[str, Any]:
    payload = context.to_dict()
    return {
        "schema_version": "2.0",
        "mode": "round_robin_d1b2",
        "run_id": run_id,
        "selected_task_id": task_id,
        "provider_order": list(provider_order),
        "max_calls": max_calls,
        "source_identity": source.to_context_dict(),
        "task_execution_contract_identity": payload["selected_task"][
            "task_execution_identity"
        ],
        "d1a_semantic_parent_identity": payload["selected_task"][
            "d1a_semantic_parent_identity"
        ],
        "context_sha256": context.semantic_sha256,
        "authority": "review_only_not_applied",
    }


def _invoke_round(
    *,
    run_dir: Path,
    round_number: int,
    task_id: str,
    run_id: str,
    role: str,
    provider: str,
    provider_bundle: ProviderBundle,
    prompt: str,
    output_schema: dict[str, Any],
    context_paths: tuple[str, ...],
    task_contract_identity: TaskContractIdentity,
    budgets: Budgets,
    heartbeat_seconds: float,
    reporter: ProgressReporter,
    session_binding: ProviderSessionBinding | None = None,
) -> tuple[AgentResult | None, Exception | None, float, str]:
    invocation_id = _round_invocation_id(
        task_id, run_id, round_number, role
    )
    round_dir = run_dir / "rounds" / f"{round_number:02d}"
    round_dir.mkdir(parents=True)
    key, configuration, registry = provider_bundle
    invocation = AgentInvocationRequest(
        AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
        invocation_id,
        role,
        prompt,
        context_paths,
        ("repository_read", "repository_search"),
        WriteBoundaries((), ()),
        output_schema,
        "high_reasoning",
        budgets,
        key,
    )
    task_request = TaskExecutionRequest(
        TASK_EXECUTION_REQUEST_SCHEMA_VERSION,
        task_id,
        task_contract_identity,
        invocation,
    )

    reporter.emit(
        "round_provider_started",
        f"D1B.2 round {round_number} {role} started with {provider}",
        round_number=round_number,
        round_role=role,
        round_provider=provider,
        invocation_id=invocation_id,
        session_mode=None if session_binding is None else session_binding.mode,
    )
    stopped = threading.Event()
    invocation_started = time.monotonic()

    def heartbeat() -> None:
        while not stopped.wait(heartbeat_seconds):
            elapsed = round(time.monotonic() - invocation_started, 1)
            reporter.emit(
                "round_provider_heartbeat",
                f"D1B.2 round {round_number} still running: {elapsed:g}s",
                round_number=round_number,
                round_role=role,
                round_provider=provider,
                invocation_id=invocation_id,
                duration_seconds=elapsed,
                status="running",
            )

    heartbeat_thread = threading.Thread(
        target=heartbeat,
        name=f"d1b2-round-{round_number}-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()
    result: AgentResult | None = None
    invocation_exception: Exception | None = None
    try:
        result = TaskExecutionRunner(
            round_dir / "task_execution",
            AgentRunner(round_dir / "agent_runtime", configuration, registry),
        ).run(task_request)
    except Exception as exc:  # diagnostic artifact is preserved below.
        invocation_exception = exc
    finally:
        stopped.set()
        heartbeat_thread.join()
    duration = round(time.monotonic() - invocation_started, 3)
    reporter.emit(
        "round_provider_completed",
        f"D1B.2 round {round_number} {role} completed",
        round_number=round_number,
        round_role=role,
        round_provider=provider,
        invocation_id=invocation_id,
        status=(result.status if result is not None else "failed"),
        duration_seconds=duration,
    )
    return result, invocation_exception, duration, invocation_id


def _publish_candidate(round_dir: Path, candidate: CandidateSnapshot) -> None:
    publish_json_no_overwrite(
        round_dir / "candidate.json", candidate.result.to_dict()
    )
    publish_json_no_overwrite(
        round_dir / "candidate_identity.json", candidate.summary()
    )
    if candidate.graph_delta is not None:
        publish_text_no_overwrite(
            round_dir / "candidate_graph_delta.json",
            candidate.graph_delta.canonical_json() + "\n",
        )


def _human_next_step(run_status: str) -> str:
    return {
        "review_ready": (
            "Review decomposition_result.json, graph_delta.json when present, and the per-round review history. No graph change has been applied."
        ),
        "needs_human": (
            "Inspect unresolved_findings and round artifacts. The bounded independent-review circuit reached a human authority boundary; no candidate was approved or applied."
        ),
        "agent_failed": (
            "Inspect the failed round's AgentRuntime artifacts and provider log. No review-ready decomposition was emitted."
        ),
        "rejected": (
            "Inspect rejection_reasons and the per-round candidate/review artifacts. No review-ready decomposition was emitted."
        ),
    }[run_status]


def run_round_robin_decomposition(
    *,
    source: Path,
    output_root: Path,
    task_id: str,
    provider_order: Iterable[str] = ("codex", "claude"),
    max_calls: int | None = None,
    run_id: str | None = None,
    provider_factory: ProviderFactory | None = None,
    _require_physical_read_only_source: bool = True,
    lease_bundle: DecompositionLeaseBundle | None = None,
    scheduler_repository_identity: str | None = None,
) -> dict[str, Any]:
    """Run one bounded alternating-author/reviewer decomposition circuit."""

    started = time.monotonic()
    if not re.fullmatch(r"NSC-[0-9]{3}", task_id):
        raise DecompositionPreflightError("task ID must match NSC-###")
    order = validate_provider_order(provider_order)
    call_limit = round_robin_call_limit(max_calls)
    if (lease_bundle is None) != (scheduler_repository_identity is None):
        raise DecompositionPreflightError(
            "pooled decomposition sessions require both the lease bundle and the "
            "scheduler-proven repository identity"
        )
    if lease_bundle is not None and run_id is None:
        raise DecompositionPreflightError("pooled decomposition sessions require an explicit run id")
    source_identity = capture_clean_source(source)
    safe_output_root = require_output_disjoint(
        source_identity.root, output_root
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
    generator_prompt = build_decomposer_prompt(context)
    generator_budget = decomposer_budgets()
    reviewer_budget = reviewer_budgets()
    heartbeat_seconds = heartbeat_interval()
    selected_run_id = _validate_run_id(run_id or _new_run_id(task_id))
    # Every provider/role pair the circuit may reach is validated before the
    # run directory is published, ephemerally; the round itself constructs the
    # provider again with its exact role and, when pooled, its session.
    for provider in dict.fromkeys(order):
        for role_name in ("task_decomposer", "decomposition_reviewer"):
            _validated_provider_bundle(
                provider, source_identity.root, provider_factory, role=role_name
            )
    pooled_sessions: PooledRoundSessions | None = None
    codex_resume_sandbox_argument: tuple[str, ...] | None = None
    if lease_bundle is not None:
        assert scheduler_repository_identity is not None
        try:
            bind_lease_bundle_to_run(
                lease_bundle, task_id=task_id, source_head=source_identity.head,
                source_root=source_identity.root, decomposition_mode="round_robin_d1b2",
                scheduler_repository_identity=scheduler_repository_identity,
                provider_order=order,
            )
        except DecompositionSessionError as exc:
            raise DecompositionPreflightError(f"lease bundle does not bind to this run: {exc}") from exc
        pooled_sessions = PooledRoundSessions(lease_bundle)
        codex_resume_sandbox_argument = lease_bundle.codex_resume_sandbox_argument
    changed_during_provider_setup = source_revalidation_reasons(source_identity)
    if changed_during_provider_setup:
        raise DecompositionPreflightError(
            "; ".join(changed_during_provider_setup)
        )

    safe_output_root.mkdir(parents=True, exist_ok=True)
    run_dir = safe_output_root / selected_run_id
    try:
        run_dir.mkdir()
    except FileExistsError as exc:
        raise DecompositionPreflightError(
            f"decomposition run directory already exists: {selected_run_id}"
        ) from exc

    reporter = ProgressReporter(
        run_dir / "progress.jsonl",
        run_id=selected_run_id,
        task_id=task_id,
        provider="round-robin",
        started=started,
    )
    reporter.emit(
        "run_started",
        f"D1B.2 round-robin decomposition started: {task_id}",
        provider_order=list(order),
        max_calls=call_limit,
    )
    publish_json_no_overwrite(
        run_dir / "decomposition_request.json",
        _run_request(
            run_id=selected_run_id,
            task_id=task_id,
            provider_order=order,
            max_calls=call_limit,
            source=source_identity,
            context=context,
        ),
    )
    publish_text_no_overwrite(
        run_dir / "context.json", context.canonical_json() + "\n"
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

    candidate: CandidateSnapshot | None = None
    unresolved_findings: dict[str, ReviewFinding] = {}
    all_finding_ids: set[str] = set()
    review_history: list[dict[str, Any]] = []
    round_summaries: list[dict[str, Any]] = []
    rejection_reasons: list[str] = []
    run_status = "rejected"
    independent_approver: str | None = None
    calls_used = 0

    for round_number in range(1, call_limit + 1):
        calls_used = round_number
        provider = order[(round_number - 1) % len(order)]
        role = "task_decomposer" if round_number == 1 else "decomposition_reviewer"
        if candidate is not None and provider == candidate.author_provider:
            rejection_reasons.append(
                "round-robin provider order attempted to let the latest candidate author review its own candidate"
            )
            run_status = "rejected"
            break

        if round_number == 1:
            prompt = generator_prompt
            output_schema = DECOMPOSITION_RESULT_SCHEMA
            budgets = generator_budget
        else:
            assert candidate is not None
            prompt = build_decomposition_reviewer_prompt(
                context=context,
                candidate=candidate.result,
                candidate_sha256=candidate.sha256,
                candidate_author_provider=candidate.author_provider,
                reviewer_provider=provider,
                round_number=round_number,
                graph_delta=candidate.graph_delta,
                review_history=review_history,
                unresolved_findings=(
                    unresolved_findings[key]
                    for key in sorted(unresolved_findings)
                ),
            )
            output_schema = DECOMPOSITION_REVIEW_SCHEMA
            budgets = reviewer_budget

        invocation_id = _round_invocation_id(
            task_id, selected_run_id, round_number, role
        )
        round_dir = run_dir / "rounds" / f"{round_number:02d}"
        # The session for this round is the lease for exactly this provider
        # *and* this semantic role. An author lease is never handed to a
        # reviewer round, however many rounds the same provider serves.
        pooled_key: str | None = None
        session_binding: ProviderSessionBinding | None = None
        session_ledger: ProviderSessionLedger | None = None
        if pooled_sessions is not None and lease_bundle is not None:
            if lease_bundle.lease_for(provider, role) is not None:
                pooled_key = lease_key(provider, role)
                session_binding = pooled_sessions.binding_for(pooled_key)
                session_ledger = ProviderSessionLedger()
                prompt = pooled_sessions.capsule_for(
                    pooled_key,
                    current={
                        "task": task_id,
                        "decomposition_run": selected_run_id,
                        "round": str(round_number),
                        "decomposition_mode": "round_robin_d1b2",
                        "source_head": source_identity.head,
                        "source_tree": source_identity.tree,
                        "reviewed_candidate_sha256": (
                            "(none: this round authors the initial candidate)"
                            if candidate is None else candidate.sha256
                        ),
                    },
                    allowed_actions=(
                        ("author one structured decomposition result for the selected task",)
                        if role == "task_decomposer"
                        else ("return exactly one structured review verdict: pass, revise, or needs_human",)
                    ),
                ) + "\n\n" + prompt
        publish_json_no_overwrite(
            run_dir / "rounds" / f"{round_number:02d}-request.json",
            {
                **_round_request(
                    round_number=round_number,
                    role=role,
                    provider=provider,
                    invocation_id=invocation_id,
                    candidate=candidate,
                    unresolved_findings=unresolved_findings,
                ),
                "pooled_session_key": pooled_key,
                "session_mode": None if session_binding is None else session_binding.mode,
                "requested_session_id": None if session_binding is None else session_binding.session_id,
            },
        )
        provider_bundle = _validated_provider_bundle(
            provider, source_identity.root, provider_factory, role=role,
            session=session_binding, session_ledger=session_ledger,
            codex_resume_sandbox_argument=codex_resume_sandbox_argument,
        )
        route_model: str | None = None
        route_effort: str | None = None
        if pooled_key is not None:
            assert lease_bundle is not None
            bundle_key, bundle_configuration, bundle_registry = provider_bundle
            selection = bundle_configuration.resolve(bundle_key, "high_reasoning", bundle_registry)
            route_model = selection.model
            route_effort = getattr(bundle_registry[selection.provider], "reasoning_effort", None)
            try:
                assert_lease_matches_route(
                    lease_bundle.leases[pooled_key],
                    provider_identifier=selection.provider,
                    model=route_model,
                    reasoning_effort=route_effort,
                )
            except DecompositionSessionError as exc:
                raise DecompositionPreflightError(str(exc)) from exc

        agent_result, invocation_exception, round_duration, actual_invocation_id = _invoke_round(
            run_dir=run_dir,
            round_number=round_number,
            task_id=task_id,
            run_id=selected_run_id,
            role=role,
            provider=provider,
            provider_bundle=provider_bundle,
            prompt=prompt,
            output_schema=output_schema,
            context_paths=context_paths,
            task_contract_identity=task_contract_identity,
            budgets=budgets,
            heartbeat_seconds=heartbeat_seconds,
            reporter=reporter,
            session_binding=session_binding,
        )
        if actual_invocation_id != invocation_id:
            rejection_reasons.append("internal invocation identity mismatch")
            run_status = "rejected"
            break

        task_request_reference = (
            f"rounds/{round_number:02d}/task_execution/{invocation_id}/task_request.json"
        )
        agent_result_reference = (
            f"rounds/{round_number:02d}/agent_runtime/{invocation_id}/result.json"
        )
        round_summary: dict[str, Any] = {
            "schema_version": ROUND_RESULT_SCHEMA_VERSION,
            "round_number": round_number,
            "role": role,
            "requested_provider": provider,
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
            "duration_seconds": round_duration,
            "candidate_before": (
                candidate.summary() if candidate is not None else None
            ),
            "candidate_after": None,
            "verdict": None,
            "new_finding_ids": [],
            "unresolved_finding_ids": sorted(unresolved_findings),
            "task_execution_request_path": (
                task_request_reference
                if (run_dir / task_request_reference).is_file()
                else None
            ),
            "agent_runtime_result_path": (
                agent_result_reference
                if (run_dir / agent_result_reference).is_file()
                else None
            ),
            "status": "rejected",
            "authority": "review_only_not_applied",
            "pooled_session": None,
        }

        round_rejections: list[str] = []
        post_call_source_reasons = source_revalidation_reasons(source_identity)
        session_unproven = False
        if session_ledger is not None:
            assert session_binding is not None and pooled_key is not None
            if session_ledger.confirmed is None:
                # The provider never named the conversation, so this round's
                # output cannot be attributed to the conversation it was
                # supposed to come from. The run stops without an authoritative
                # result; the host quarantines the reservation.
                session_unproven = True
                detail = (
                    f"round {round_number} {role} asked to {session_binding.mode} provider "
                    f"session {session_binding.session_id or '(provider-assigned)'} but the "
                    "transcript never confirmed it; the conversation is unproven, quarantined, "
                    "and never reused"
                )
                reporter.emit(
                    "provider_session_identity_unproven", detail, round_number=round_number,
                    round_role=role, round_provider=provider, pooled_session_key=pooled_key,
                    session_mode=session_binding.mode,
                    requested_session_id=session_binding.session_id, status="quarantined",
                )
                round_rejections.append(f"provider session identity unproven: {detail}")
                run_status = "agent_failed"
                assert pooled_sessions is not None
                pooled_sessions.record_unproven(pooled_key, detail)
            else:
                confirmed = session_ledger.confirmed
                reporter.emit(
                    "provider_session_confirmed",
                    f"round {round_number} {role} confirmed provider session {confirmed.session_id}",
                    round_number=round_number, round_role=role, round_provider=provider,
                    pooled_session_key=pooled_key, session_mode=confirmed.mode,
                    session_id=confirmed.session_id, status="confirmed",
                )
        if session_unproven:
            pass
        elif invocation_exception is not None:
            round_rejections.append(
                "task-associated invocation failed: "
                f"{type(invocation_exception).__name__}: {invocation_exception}"
            )
            run_status = "agent_failed"
        elif agent_result is None:
            round_rejections.append("task-associated invocation returned no AgentResult")
            run_status = "agent_failed"
        elif agent_result.status != "succeeded":
            round_rejections.append(
                f"AgentResult failed ({agent_result.failure_classification}): {agent_result.failure_message}"
            )
            run_status = "agent_failed"
        else:
            round_rejections.extend(_read_only_rejection_reasons(agent_result))
        round_rejections.extend(post_call_source_reasons)

        if not round_rejections and agent_result is not None:
            if round_number == 1:
                try:
                    candidate = _validate_candidate(
                        thaw_json(agent_result.structured_output),
                        context_payload=context_payload,
                        graph=graph,
                        author_provider=provider,
                        version=1,
                    )
                    _publish_candidate(round_dir, candidate)
                    round_summary["candidate_after"] = candidate.summary()
                    round_summary["status"] = "candidate_valid"
                    if round_number == call_limit:
                        run_status = "needs_human"
                        rejection_reasons.append(
                            "call limit ended before an independent provider reviewed the initial candidate"
                        )
                    else:
                        run_status = "rejected"
                except (
                    DecompositionContractError,
                    DecompositionPolicyError,
                    GraphDeltaPlanningError,
                ) as exc:
                    round_rejections.append(
                        f"initial candidate deterministic validation failed: {exc}"
                    )
                    run_status = "rejected"
            else:
                assert candidate is not None
                try:
                    review, next_unresolved = validate_decomposition_review(
                        thaw_json(agent_result.structured_output),
                        expected_candidate_sha256=candidate.sha256,
                        round_number=round_number,
                        prior_unresolved_findings=unresolved_findings,
                        all_prior_finding_ids=all_finding_ids,
                    )
                    publish_json_no_overwrite(
                        round_dir / "review.json", review.to_dict()
                    )
                    round_summary["verdict"] = review.verdict
                    round_summary["new_finding_ids"] = [
                        finding.finding_id for finding in review.findings
                    ]
                    all_finding_ids.update(
                        finding.finding_id for finding in review.findings
                    )
                    history_entry = {
                        "round_number": round_number,
                        "reviewer_provider": provider,
                        "reviewed_candidate_sha256": candidate.sha256,
                        "verdict": review.verdict,
                        "summary": review.summary,
                        "findings": [
                            finding.to_dict() for finding in review.findings
                        ],
                        "prior_finding_resolutions": [
                            resolution.to_dict()
                            for resolution in review.prior_finding_resolutions
                        ],
                    }
                    review_history.append(history_entry)
                    publish_json_no_overwrite(
                        round_dir / "review_history_entry.json", history_entry
                    )

                    if review.verdict == "pass":
                        unresolved_findings = next_unresolved
                        independent_approver = provider
                        round_summary["status"] = "independent_pass"
                        run_status = "review_ready"
                    elif review.verdict == "needs_human":
                        unresolved_findings = next_unresolved
                        round_summary["status"] = "needs_human"
                        run_status = "needs_human"
                    else:
                        assert review.revised_decomposition is not None
                        revised = _validate_candidate(
                            review.revised_decomposition,
                            context_payload=context_payload,
                            graph=graph,
                            author_provider=provider,
                            version=candidate.version + 1,
                        )
                        if revised.sha256 == candidate.sha256:
                            raise DecompositionReviewPolicyError(
                                "revise emitted a candidate identical to the reviewed candidate"
                            )
                        candidate = revised
                        unresolved_findings = next_unresolved
                        _publish_candidate(round_dir, candidate)
                        round_summary["candidate_after"] = candidate.summary()
                        round_summary["status"] = "revised_candidate_valid"
                        if round_number == call_limit:
                            run_status = "needs_human"
                            rejection_reasons.append(
                                "call limit ended immediately after a revision; the latest author may not approve its own candidate"
                            )
                        else:
                            run_status = "rejected"
                except (
                    DecompositionReviewContractError,
                    DecompositionReviewPolicyError,
                    DecompositionContractError,
                    DecompositionPolicyError,
                    GraphDeltaPlanningError,
                ) as exc:
                    round_rejections.append(
                        f"review/revision deterministic validation failed: {exc}"
                    )
                    run_status = "rejected"

        if round_rejections:
            round_summary["rejection_reasons"] = round_rejections
            rejection_reasons.extend(
                f"round {round_number}: {reason}" for reason in round_rejections
            )
        else:
            round_summary["rejection_reasons"] = []
        round_summary["unresolved_finding_ids"] = sorted(unresolved_findings)
        if session_ledger is not None and session_ledger.confirmed is not None:
            assert pooled_sessions is not None and lease_bundle is not None
            assert pooled_key is not None and session_binding is not None and route_model is not None
            # The artifact this round produced, hashed exactly as published:
            # the author's or reviser's candidate, or the reviewer's verdict.
            artifact_path: str | None = None
            artifact_sha256: str | None = None
            if round_summary["candidate_after"] is not None and candidate is not None:
                artifact_path = f"rounds/{round_number:02d}/candidate.json"
                artifact_sha256 = canonical_artifact_sha256(candidate.result.to_dict())
            elif round_summary["verdict"] is not None and (round_dir / "review.json").is_file():
                artifact_path = f"rounds/{round_number:02d}/review.json"
                artifact_sha256 = hashlib.sha256((round_dir / "review.json").read_bytes()).hexdigest()
            evidence = pooled_round_evidence(
                lease_key_value=pooled_key,
                lease=lease_bundle.leases[pooled_key],
                task_id=task_id, run_id=selected_run_id, decomposition_mode="round_robin_d1b2",
                round_number=round_number, invocation_id=invocation_id, role=role,
                provider_name=provider, model=route_model, reasoning_effort=route_effort,
                source_head=source_identity.head, source_tree=source_identity.tree,
                checkout_identity=lease_bundle.checkout_identity,
                requested=session_binding, confirmed=session_ledger.confirmed,
                artifact_path=artifact_path, artifact_sha256=artifact_sha256,
                agent_status=str(round_summary["agent_status"]),
                round_status=str(round_summary["status"]),
            )
            round_summary["pooled_session"] = evidence
            pooled_sessions.record(pooled_key, session_ledger.confirmed, evidence)
        publish_json_no_overwrite(
            round_dir / "round_result.json", round_summary
        )
        round_summaries.append(round_summary)

        if round_rejections or run_status in {
            "review_ready",
            "needs_human",
            "agent_failed",
        }:
            break

    final_source_reasons = source_revalidation_reasons(source_identity)
    if final_source_reasons:
        rejection_reasons.extend(
            reason for reason in final_source_reasons
            if reason not in rejection_reasons
        )
        run_status = "rejected"
        independent_approver = None

    decomposition_result_path: str | None = None
    graph_delta_path: str | None = None
    if run_status == "review_ready":
        if candidate is None or independent_approver is None:
            rejection_reasons.append(
                "internal error: review_ready requires a candidate and independent approver"
            )
            run_status = "rejected"
        elif candidate.author_provider == independent_approver:
            rejection_reasons.append(
                "internal error: candidate author attempted to approve its own candidate"
            )
            run_status = "rejected"
        elif unresolved_findings:
            rejection_reasons.append(
                "internal error: review_ready candidate retains unresolved blocking findings"
            )
            run_status = "rejected"
        else:
            publish_json_no_overwrite(
                run_dir / "decomposition_result.json",
                candidate.result.to_dict(),
            )
            decomposition_result_path = "decomposition_result.json"
            if candidate.graph_delta is not None:
                publish_text_no_overwrite(
                    run_dir / "graph_delta.json",
                    candidate.graph_delta.canonical_json() + "\n",
                )
                graph_delta_path = "graph_delta.json"

    final = {
        "schema_version": ROUND_ROBIN_RUN_RESULT_SCHEMA_VERSION,
        "mode": "round_robin_d1b2",
        "run_id": selected_run_id,
        "task_id": task_id,
        "provider_order": list(order),
        "max_calls": call_limit,
        "calls_used": calls_used,
        "source_identity": source_identity.to_context_dict(),
        "task_execution_contract_identity": task_contract_identity.to_dict(),
        "d1a_semantic_parent_identity": context_payload["selected_task"][
            "d1a_semantic_parent_identity"
        ],
        "context_sha256": context.semantic_sha256,
        "run_status": run_status,
        "decision": candidate.result.decision if candidate is not None else None,
        "latest_candidate": candidate.summary() if candidate is not None else None,
        "independent_approver_provider": independent_approver,
        "decomposition_result_path": decomposition_result_path,
        "graph_delta_path": graph_delta_path,
        "rounds": round_summaries,
        "finding_history": review_history,
        "unresolved_findings": [
            unresolved_findings[key].to_dict()
            for key in sorted(unresolved_findings)
        ],
        "rejection_reasons": rejection_reasons,
        "human_next_step": _human_next_step(run_status),
        "duration_seconds": time.monotonic() - started,
        "authority": "review_only_not_applied",
        "pooled_sessions": None if pooled_sessions is None else pooled_sessions.summary(),
    }
    reporter.emit(
        "run_completed",
        f"D1B.2 round-robin decomposition completed: {run_status}",
        status=run_status,
        calls_used=calls_used,
        duration_seconds=round(final["duration_seconds"], 3),
    )
    publish_json_no_overwrite(
        run_dir / "decomposition_run_result.json", final
    )
    return final
