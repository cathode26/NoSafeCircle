"""One bounded read-only model-backed Stage D1B.1 decomposition invocation."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping


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
from Pipeline.AgentRuntime.providers.claude_code import ClaudeCodeProvider
from Pipeline.AgentRuntime.providers.openai_codex import OpenAICodexProvider
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
from TaskDecomposition.contracts import DecompositionContractError
from TaskDecomposition.policy import (
    DecompositionPolicyError,
    validate_decomposition_result,
)
from TaskDecomposition.prompts import build_decomposer_prompt
from TaskDecomposition.schemas import DECOMPOSITION_RESULT_SCHEMA
from Pipeline.TaskExecution.contracts import (
    TASK_EXECUTION_REQUEST_SCHEMA_VERSION,
    TaskContractIdentity,
    TaskExecutionRequest,
)
from Pipeline.TaskExecution.task_runner import TaskExecutionRunner
from graph_delta import GraphDeltaPlanningError, plan_graph_delta


RUN_RESULT_SCHEMA_VERSION = "1.0"
_RUN_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
ProviderFactory = Callable[
    [str, Path], tuple[str, RuntimeConfiguration, Mapping[str, Any]]
]


def _json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True
    ) + "\n"


def publish_text_no_overwrite(path: Path, content: str) -> None:
    """Atomically publish UTF-8 text without replacing an existing artifact."""

    if type(content) is not str:
        raise TypeError("artifact content must be exact text")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink()
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def publish_json_no_overwrite(path: Path, value: Any) -> None:
    publish_text_no_overwrite(path, _json(value))


class ProgressReporter:
    """Non-authoritative stderr and JSONL progress without prompt/provider content."""

    def __init__(
        self,
        path: Path,
        *,
        run_id: str,
        task_id: str,
        provider: str,
        started: float,
    ) -> None:
        self.path = path
        self.run_id = run_id
        self.task_id = task_id
        self.provider = provider
        self.started = started
        self._lock = threading.Lock()
        self.path.open("x", encoding="utf-8", newline="\n").close()

    def emit(self, event: str, message: str, **fields: Any) -> None:
        record = {
            "schema_version": "1.0",
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            "event": event,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "provider": self.provider,
            **fields,
            "message": message,
        }
        line = json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line + "\n")
                stream.flush()
            print(f"[{record['timestamp_utc']}] {message}", file=sys.stderr, flush=True)


def heartbeat_interval() -> float:
    raw = os.getenv("NSC_DECOMPOSITION_HEARTBEAT_SECONDS", "15")
    try:
        value = float(raw)
    except ValueError as exc:
        raise DecompositionPreflightError(
            "NSC_DECOMPOSITION_HEARTBEAT_SECONDS must be a positive finite number"
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise DecompositionPreflightError(
            "NSC_DECOMPOSITION_HEARTBEAT_SECONDS must be a positive finite number"
        )
    return value


def decomposer_budgets() -> Budgets:
    raw_turns = os.getenv("NSC_TASK_DECOMPOSER_TURN_LIMIT", "48")
    raw_timeout = os.getenv("NSC_TASK_DECOMPOSER_TIMEOUT_SECONDS", "1440")
    try:
        turns = int(raw_turns)
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise DecompositionPreflightError(
            "task decomposer budget overrides must be positive finite values"
        ) from exc
    try:
        return Budgets(turns, timeout, None)
    except ContractValidationError as exc:
        raise DecompositionPreflightError(
            f"invalid task decomposer budget override: {exc}"
        ) from exc


def provider_configuration(provider_name: str) -> tuple[str, RuntimeConfiguration]:
    if provider_name == "claude":
        key = "claude-decomposition"
        identifier = "claude-code"
        model = os.getenv("NSC_CLAUDE_MODEL", "claude-sonnet-5")
    elif provider_name == "codex":
        key = "codex-decomposition"
        identifier = "openai-codex"
        model = os.getenv("NSC_OPENAI_CODEX_MODEL", "gpt-5.6-sol")
    else:
        raise DecompositionPreflightError("provider must be claude or codex")
    try:
        configuration = RuntimeConfiguration({
            key: {
                "provider": identifier,
                "models": {
                    "low_cost": model,
                    "standard": model,
                    "high_reasoning": model,
                },
            }
        })
    except ContractValidationError as exc:
        raise DecompositionPreflightError(f"invalid provider model configuration: {exc}") from exc
    return key, configuration


def _real_provider_bundle(
    provider_name: str, source_root: Path
) -> tuple[str, RuntimeConfiguration, Mapping[str, Any]]:
    key, configuration = provider_configuration(provider_name)
    if provider_name == "claude":
        provider = ClaudeCodeProvider(repository_root=source_root)
    elif provider_name == "codex":
        provider = OpenAICodexProvider(
            repository_root=source_root,
            externally_enforced_read_only_repository=True,
        )
    else:
        raise DecompositionPreflightError("provider must be claude or codex")
    return key, configuration, {provider.provider_identifier: provider}


def _validated_provider_bundle(
    provider_name: str,
    source_root: Path,
    factory: ProviderFactory | None,
) -> tuple[str, RuntimeConfiguration, Mapping[str, Any]]:
    expected_key = f"{provider_name}-decomposition"
    try:
        key, configuration, registry = (
            _real_provider_bundle(provider_name, source_root)
            if factory is None
            else factory(provider_name, source_root)
        )
    except DecompositionPreflightError:
        raise
    except Exception as exc:
        raise DecompositionPreflightError(
            f"provider factory failed during deterministic setup: {type(exc).__name__}: {exc}"
        ) from exc
    if key != expected_key:
        raise DecompositionPreflightError(
            "provider factory configuration key does not match the requested provider"
        )
    if type(configuration) is not RuntimeConfiguration or not isinstance(registry, Mapping):
        raise DecompositionPreflightError(
            "provider factory returned invalid configuration or registry"
        )
    try:
        selection = configuration.resolve(key, "high_reasoning", registry)
        provider = registry[selection.provider]
        if provider.provider_identifier != selection.provider:
            raise DecompositionPreflightError(
                "provider factory registry identity does not match configuration"
            )
    except DecompositionPreflightError:
        raise
    except Exception as exc:
        raise DecompositionPreflightError(
            f"provider factory/configuration mismatch: {exc}"
        ) from exc
    expected_identifier = {
        "claude": "claude-code",
        "codex": "openai-codex",
    }[provider_name]
    if selection.provider not in {expected_identifier, "fake"}:
        raise DecompositionPreflightError(
            "provider factory/configuration selected a provider incompatible with the request"
        )
    return key, configuration, registry


def _new_run_id(task_id: str) -> str:
    stamp = time.strftime("%Y%m%dt%H%M%Sz", time.gmtime())
    nonce = os.urandom(6).hex()
    return f"{task_id.lower()}-decomp-{stamp}-{nonce}"


def _validate_run_id(run_id: str) -> str:
    if type(run_id) is not str or not _RUN_ID_RE.fullmatch(run_id):
        raise DecompositionPreflightError(
            "run_id must be a lowercase ASCII slug of 1..64 characters"
        )
    return run_id


def _invocation_id(task_id: str, run_id: str) -> str:
    suffix = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
    return f"{task_id.lower()}-task-decomposer-{suffix}"


def _decomposition_request(
    *,
    run_id: str,
    task_id: str,
    provider_name: str,
    source: SourceIdentity,
    context: ContextPackage,
) -> dict[str, Any]:
    payload = context.to_dict()
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "selected_task_id": task_id,
        "requested_provider": provider_name,
        "source_identity": source.to_context_dict(),
        "task_execution_contract_identity": payload["selected_task"]["task_execution_identity"],
        "d1a_semantic_parent_identity": payload["selected_task"]["d1a_semantic_parent_identity"],
        "context_sha256": context.semantic_sha256,
        "authority": "review_only_not_applied",
    }


def _human_next_step(decision: str | None, run_status: str) -> str:
    if run_status != "review_ready":
        return "Inspect AgentRuntime and decomposition diagnostics. No review-ready decomposition was emitted."
    return {
        "decomposed": "Review decomposition_result.json and graph_delta.json. No graph change has been applied.",
        "already_concrete": "Review the no-decomposition recommendation. No task contract has been changed.",
        "needs_artifact": (
            "Review the artifact proposal. Artifact Authority is not implemented and no artifact has been authorized or generated."
        ),
        "needs_human": (
            "Answer the unresolved questions or revise the selected task. No graph change has been applied."
        ),
    }[decision]


def _read_only_rejection_reasons(result: AgentResult) -> list[str]:
    reasons: list[str] = []
    if result.claimed_changed_paths:
        reasons.append(
            "read-only Decomposer rejected nonempty claimed_changed_paths: "
            + ", ".join(result.claimed_changed_paths)
        )
    if result.claims_execution_occurred:
        reasons.append("read-only Decomposer rejected claims_execution_occurred=true")
    if result.claimed_test_commands:
        reasons.append(
            "read-only Decomposer rejected nonempty claimed_test_commands: "
            + ", ".join(result.claimed_test_commands)
        )
    return reasons


def run_live_decomposition(
    *,
    source: Path,
    output_root: Path,
    task_id: str,
    provider_name: str,
    run_id: str | None = None,
    provider_factory: ProviderFactory | None = None,
    _require_physical_read_only_source: bool = True,
) -> dict[str, Any]:
    """Run exactly one task-associated invocation and publish review-only artifacts."""

    started = time.monotonic()
    if provider_name not in {"claude", "codex"}:
        raise DecompositionPreflightError("provider must be claude or codex")
    if not re.fullmatch(r"NSC-[0-9]{3}", task_id):
        raise DecompositionPreflightError("task ID must match NSC-###")
    source_identity = capture_clean_source(source)
    safe_output_root = require_output_disjoint(source_identity.root, output_root)
    if not _require_physical_read_only_source and provider_factory is None:
        raise DecompositionPreflightError(
            "writable-source test injection requires an injected provider factory"
        )
    if _require_physical_read_only_source:
        require_physical_read_only(source_identity.root)
    interval = heartbeat_interval()
    budgets = decomposer_budgets()
    context, graph = build_context(source_identity, task_id)
    changed_during_context = source_revalidation_reasons(source_identity)
    if changed_during_context:
        raise DecompositionPreflightError("; ".join(changed_during_context))
    prompt = build_decomposer_prompt(context)
    key, configuration, registry = _validated_provider_bundle(
        provider_name, source_identity.root, provider_factory
    )
    selected_run_id = _validate_run_id(run_id or _new_run_id(task_id))
    invocation_id = _invocation_id(task_id, selected_run_id)

    context_payload = context.to_dict()
    task_identity_payload = context_payload["selected_task"]["task_execution_identity"]
    task_contract_identity = TaskContractIdentity(
        task_identity_payload["path"],
        task_identity_payload["revision"],
        task_identity_payload["sha256"],
    )
    invocation = AgentInvocationRequest(
        AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
        invocation_id,
        "task_decomposer",
        prompt,
        tuple(context_payload["context_paths"]),
        ("repository_read", "repository_search"),
        WriteBoundaries((), ()),
        DECOMPOSITION_RESULT_SCHEMA,
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
        provider=provider_name,
        started=started,
    )
    reporter.emit("run_started", f"Decomposition started: {task_id} / {provider_name}")
    publish_json_no_overwrite(
        run_dir / "decomposition_request.json",
        _decomposition_request(
            run_id=selected_run_id,
            task_id=task_id,
            provider_name=provider_name,
            source=source_identity,
            context=context,
        ),
    )
    publish_text_no_overwrite(run_dir / "context.json", context.canonical_json() + "\n")

    reporter.emit(
        "provider_started",
        "Read-only task_decomposer provider invocation started",
        invocation_id=invocation_id,
    )
    stopped = threading.Event()
    invocation_started = time.monotonic()

    def heartbeat() -> None:
        while not stopped.wait(interval):
            elapsed = round(time.monotonic() - invocation_started, 1)
            reporter.emit(
                "provider_heartbeat",
                f"Read-only task_decomposer still running: {elapsed:g}s",
                invocation_id=invocation_id,
                duration_seconds=elapsed,
                status="running",
            )

    heartbeat_thread = threading.Thread(
        target=heartbeat, name="decomposition-provider-heartbeat", daemon=True
    )
    heartbeat_thread.start()
    agent_result: AgentResult | None = None
    invocation_exception: Exception | None = None
    try:
        agent_result = TaskExecutionRunner(
            run_dir / "task_execution",
            AgentRunner(run_dir / "agent_runtime", configuration, registry),
        ).run(task_request)
    except Exception as exc:
        invocation_exception = exc
    finally:
        stopped.set()
        heartbeat_thread.join()

    invocation_duration = round(time.monotonic() - invocation_started, 3)
    reporter.emit(
        "provider_completed",
        "Read-only task_decomposer provider invocation completed",
        invocation_id=invocation_id,
        status=(agent_result.status if agent_result is not None else "failed"),
        duration_seconds=invocation_duration,
    )

    rejection_reasons: list[str] = []
    decision: str | None = None
    accepted_result = None
    graph_delta = None
    run_status = "rejected"
    agent_status: str | None = None
    failure_classification: str | None = None
    actual_provider: str | None = None
    actual_model: str | None = None

    post_invocation_source_reasons = source_revalidation_reasons(source_identity)
    if invocation_exception is not None:
        run_status = "agent_failed"
        agent_status = "failed"
        failure_classification = "internal_error"
        rejection_reasons.append(
            f"task-associated invocation failed: {type(invocation_exception).__name__}: {invocation_exception}"
        )
    else:
        assert agent_result is not None
        agent_status = agent_result.status
        failure_classification = agent_result.failure_classification
        actual_provider = agent_result.provider
        actual_model = agent_result.model
        if agent_result.status != "succeeded":
            run_status = "agent_failed"
            rejection_reasons.append(
                f"AgentResult failed ({agent_result.failure_classification}): {agent_result.failure_message}"
            )
        else:
            rejection_reasons.extend(_read_only_rejection_reasons(agent_result))
    rejection_reasons.extend(post_invocation_source_reasons)

    if agent_result is not None and agent_result.status == "succeeded" and not rejection_reasons:
        try:
            accepted_result = validate_decomposition_result(
                thaw_json(agent_result.structured_output),
                parent_task=context_payload["selected_task"]["contract"],
                existing_reconciliation_keys=graph.plan.id_map.keys(),
            )
            decision = accepted_result.decision
        except (DecompositionContractError, DecompositionPolicyError) as exc:
            rejection_reasons.append(f"D1A semantic validation failed: {exc}")

    if accepted_result is not None and accepted_result.decision == "decomposed" and not rejection_reasons:
        try:
            graph_delta = plan_graph_delta(
                graph, accepted_result.parent_task, accepted_result
            )
        except GraphDeltaPlanningError as exc:
            rejection_reasons.append(f"D1A graph-delta planning failed: {exc}")

    final_source_reasons = source_revalidation_reasons(source_identity)
    for reason in final_source_reasons:
        if reason not in rejection_reasons:
            rejection_reasons.append(reason)

    decomposition_result_path: str | None = None
    graph_delta_path: str | None = None
    if accepted_result is not None and not rejection_reasons:
        publish_json_no_overwrite(
            run_dir / "decomposition_result.json", accepted_result.to_dict()
        )
        decomposition_result_path = "decomposition_result.json"
        if graph_delta is not None:
            publish_text_no_overwrite(
                run_dir / "graph_delta.json", graph_delta.canonical_json() + "\n"
            )
            graph_delta_path = "graph_delta.json"
        run_status = "review_ready"
    elif run_status != "agent_failed":
        run_status = "rejected"

    task_request_reference = f"task_execution/{invocation_id}/task_request.json"
    agent_result_reference = f"agent_runtime/{invocation_id}/result.json"
    final = {
        "schema_version": RUN_RESULT_SCHEMA_VERSION,
        "run_id": selected_run_id,
        "task_id": task_id,
        "requested_provider": provider_name,
        "actual_provider": actual_provider,
        "actual_model": actual_model,
        "source_identity": source_identity.to_context_dict(),
        "task_execution_contract_identity": task_contract_identity.to_dict(),
        "d1a_semantic_parent_identity": context_payload["selected_task"]["d1a_semantic_parent_identity"],
        "context_sha256": context.semantic_sha256,
        "run_status": run_status,
        "agent_result_status": agent_status,
        "agent_failure_classification": failure_classification,
        "decision": decision,
        "decomposition_result_path": decomposition_result_path,
        "graph_delta_path": graph_delta_path,
        "task_execution_request_path": (
            task_request_reference if (run_dir / task_request_reference).is_file() else None
        ),
        "agent_runtime_result_path": (
            agent_result_reference if (run_dir / agent_result_reference).is_file() else None
        ),
        "rejection_reasons": rejection_reasons,
        "human_next_step": _human_next_step(decision, run_status),
        "duration_seconds": time.monotonic() - started,
        "authority": "review_only_not_applied",
    }
    reporter.emit(
        "run_completed",
        f"Decomposition completed: {run_status}",
        status=run_status,
        duration_seconds=round(final["duration_seconds"], 3),
    )
    publish_json_no_overwrite(run_dir / "decomposition_run_result.json", final)
    return final
