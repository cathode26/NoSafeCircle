#!/usr/bin/env python3
"""Read-only AgentRuntime preflight for polling-orchestrator candidates.

The architect predicts likely Unity change surfaces and gives design advice.
It never owns scheduling, task, canon, Git, GitHub, claim, or lease authority.
Deterministic Python evaluates the returned advisory separately.

Admission optimizes for clean parallelism rather than worker utilization. Any
material uncertainty about parallel merge/integration safety resolves to WAIT:
a temporary per-pass exclusion that mutates nothing. HUMAN_REVIEW is reserved
for explicit design/canon authority ambiguity that the architect names.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.agent_runner import AgentRunner  # noqa: E402
from Pipeline.AgentRuntime.config import RuntimeConfiguration  # noqa: E402
from Pipeline.AgentRuntime.contracts import (  # noqa: E402
    AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
    AgentInvocationRequest,
    AgentResult,
    Budgets,
    ContractValidationError,
    WriteBoundaries,
    validate_repository_path,
)
from Pipeline.AgentRuntime.json_values import thaw_json  # noqa: E402
from Pipeline.AgentRuntime.providers.claude_code import (  # noqa: E402
    ClaudeCodeProvider,
)
from Pipeline.AgentRuntime.providers.openai_codex import (  # noqa: E402
    OpenAICodexProvider,
)
from Pipeline.AgentRuntime.schema_validation import (  # noqa: E402
    SchemaValidationError,
    validate_instance,
)
from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    GIT_SHA_RE,
    SHA256_RE,
    TaskReviewContractError,
    validate_task_id,
)
from Pipeline.TaskReviewAgent.execution_routing import (  # noqa: E402
    CAPABILITY_TIERS,
    MAX_RECOMMENDATION_RATIONALE_CHARACTERS,
    PROVIDER_PREFERENCES,
    ExecutionRecommendation,
    ExecutionRoutingError,
)


ARCHITECT_ADVISORY_SCHEMA_VERSION = "1.2"
ARCHITECT_PROVIDER_CONFIGURATION_KEYS = {
    "claude": "polling-architect-claude",
    "codex": "polling-architect-codex",
}
DEFAULT_ARCHITECT_TIMEOUT_SECONDS = 900.0
DEFAULT_ARCHITECT_MAX_TURNS = 24
DEFAULT_ARCHITECT_MIN_CONFIDENCE = 0.65
DEFAULT_ARCHITECT_DECISION_CACHE_ENTRIES = 256
UNITY_SERIALIZED_SUFFIXES = (
    ".unity",
    ".prefab",
    ".asset",
    ".inputactions",
)

# A design/canon escalation is the only basis for HUMAN_REVIEW. Merge or
# integration uncertainty is deliberately absent from this vocabulary so it
# cannot be encoded as a human question.
ARCHITECT_ESCALATION_CATEGORIES = (
    "none",
    "design_or_canon_ambiguity",
    "task_scope_or_contract_change",
    "decomposition_required",
)
DESIGN_ESCALATION_CATEGORIES = frozenset(ARCHITECT_ESCALATION_CATEGORIES[1:])


def _array(item_schema: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": dict(item_schema)}


def _strict_object(
    properties: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {key: dict(value) for key, value in properties.items()},
        "required": list(properties),
    }


_STRING = {"type": "string"}
_STRING_ARRAY = _array(_STRING)

PREDICTED_CHANGE_SURFACE_SCHEMA = _strict_object(
    {
        "exact_paths": _STRING_ARRAY,
        "path_patterns": _STRING_ARRAY,
        "unity_serialized_assets": _STRING_ARRAY,
        "symbols_or_components": _STRING_ARRAY,
        "shared_systems": _STRING_ARRAY,
    }
)

DESIGN_ADVICE_SCHEMA = _strict_object(
    {
        "implementation_summary": _STRING,
        "recommended_interfaces": _STRING_ARRAY,
        "sequencing_notes": _STRING_ARRAY,
        "suggested_exclusive_resources": _STRING_ARRAY,
        "suggested_taskgraph_changes": _STRING_ARRAY,
        "suggested_decomposition": _STRING_ARRAY,
    }
)

EVIDENCE_OBSERVATION_SCHEMA = _strict_object(
    {
        "path": _STRING,
        "observation": _STRING,
    }
)

ESCALATION_SCHEMA = _strict_object(
    {
        "category": {
            "type": "string",
            "enum": list(ARCHITECT_ESCALATION_CATEGORIES),
        },
        "question": _STRING,
    }
)

UNKNOWN_SURFACE_DISJOINTNESS_SCHEMA = _strict_object(
    {
        "task_id": _STRING,
        "justification": _STRING,
    }
)

EXECUTION_RECOMMENDATION_SCHEMA = _strict_object(
    {
        "capability_tier": {
            "type": "string",
            "enum": list(CAPABILITY_TIERS),
        },
        "provider_preference": {
            "type": "string",
            "enum": list(PROVIDER_PREFERENCES),
        },
        # AgentRuntime intentionally supports a small JSON Schema subset.
        # The non-empty and maximum-length bounds are enforced by the frozen
        # ExecutionRecommendation record immediately after schema validation.
        "rationale": _STRING,
    }
)

ARCHITECT_ADVISORY_SCHEMA: dict[str, Any] = _strict_object(
    {
        "task_id": _STRING,
        "source_head": _STRING,
        "task_contract_sha256": _STRING,
        "predicted_change_surface": PREDICTED_CHANGE_SURFACE_SCHEMA,
        "integration_risk": {
            "type": "string",
            "enum": ["none", "low", "medium", "high", "unknown"],
        },
        "parallel_recommendation": {
            "type": "string",
            "enum": ["start", "wait", "human_review"],
        },
        "work_type_recommendation": {
            "type": "string",
            "enum": ["implementation", "decomposition"],
        },
        "execution_recommendation": EXECUTION_RECOMMENDATION_SCHEMA,
        "conflicting_task_ids": _STRING_ARRAY,
        "conflict_reasons": _STRING_ARRAY,
        "escalation": ESCALATION_SCHEMA,
        "unknown_surface_disjointness": _array(UNKNOWN_SURFACE_DISJOINTNESS_SCHEMA),
        "design_advice": DESIGN_ADVICE_SCHEMA,
        "evidence": _array(EVIDENCE_OBSERVATION_SCHEMA),
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "assumptions": _STRING_ARRAY,
    }
)


class ArchitectPreflightError(TaskReviewContractError):
    """The advisory could not be produced or validated safely."""


def _nonempty_text(value: Any, *, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise ArchitectPreflightError(f"{field} must be a non-empty string")
    return value.strip()


def _text_tuple(
    value: Any,
    *,
    field: str,
    paths: bool = False,
    task_ids: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ArchitectPreflightError(f"{field} must be an array")
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        text = _nonempty_text(item, field=f"{field}[{index}]")
        if paths:
            try:
                text = validate_repository_path(text, field=f"{field}[{index}]")
            except ContractValidationError as exc:
                raise ArchitectPreflightError(str(exc)) from exc
        if task_ids:
            try:
                text = validate_task_id(text)
            except TaskReviewContractError as exc:
                raise ArchitectPreflightError(str(exc)) from exc
        identity = text.casefold()
        if identity in seen:
            raise ArchitectPreflightError(f"{field} contains duplicate values")
        seen.add(identity)
        result.append(text)
    return tuple(result)


@dataclass(frozen=True)
class PredictedChangeSurface:
    exact_paths: tuple[str, ...]
    path_patterns: tuple[str, ...]
    unity_serialized_assets: tuple[str, ...]
    symbols_or_components: tuple[str, ...]
    shared_systems: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PredictedChangeSurface":
        return cls(
            exact_paths=_text_tuple(
                value["exact_paths"], field="predicted_change_surface.exact_paths", paths=True
            ),
            path_patterns=_text_tuple(
                value["path_patterns"], field="predicted_change_surface.path_patterns"
            ),
            unity_serialized_assets=_text_tuple(
                value["unity_serialized_assets"],
                field="predicted_change_surface.unity_serialized_assets",
                paths=True,
            ),
            symbols_or_components=_text_tuple(
                value["symbols_or_components"],
                field="predicted_change_surface.symbols_or_components",
            ),
            shared_systems=_text_tuple(
                value["shared_systems"], field="predicted_change_surface.shared_systems"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "exact_paths": list(self.exact_paths),
            "path_patterns": list(self.path_patterns),
            "unity_serialized_assets": list(self.unity_serialized_assets),
            "symbols_or_components": list(self.symbols_or_components),
            "shared_systems": list(self.shared_systems),
        }


@dataclass(frozen=True)
class DesignAdvice:
    implementation_summary: str
    recommended_interfaces: tuple[str, ...]
    sequencing_notes: tuple[str, ...]
    suggested_exclusive_resources: tuple[str, ...]
    suggested_taskgraph_changes: tuple[str, ...]
    suggested_decomposition: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DesignAdvice":
        return cls(
            implementation_summary=_nonempty_text(
                value["implementation_summary"],
                field="design_advice.implementation_summary",
            ),
            recommended_interfaces=_text_tuple(
                value["recommended_interfaces"],
                field="design_advice.recommended_interfaces",
            ),
            sequencing_notes=_text_tuple(
                value["sequencing_notes"], field="design_advice.sequencing_notes"
            ),
            suggested_exclusive_resources=_text_tuple(
                value["suggested_exclusive_resources"],
                field="design_advice.suggested_exclusive_resources",
            ),
            suggested_taskgraph_changes=_text_tuple(
                value["suggested_taskgraph_changes"],
                field="design_advice.suggested_taskgraph_changes",
            ),
            suggested_decomposition=_text_tuple(
                value["suggested_decomposition"],
                field="design_advice.suggested_decomposition",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "implementation_summary": self.implementation_summary,
            "recommended_interfaces": list(self.recommended_interfaces),
            "sequencing_notes": list(self.sequencing_notes),
            "suggested_exclusive_resources": list(self.suggested_exclusive_resources),
            "suggested_taskgraph_changes": list(self.suggested_taskgraph_changes),
            "suggested_decomposition": list(self.suggested_decomposition),
        }


@dataclass(frozen=True)
class EvidenceObservation:
    path: str
    observation: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceObservation":
        try:
            path = validate_repository_path(value["path"], field="evidence.path")
        except ContractValidationError as exc:
            raise ArchitectPreflightError(str(exc)) from exc
        return cls(
            path=path,
            observation=_nonempty_text(value["observation"], field="evidence.observation"),
        )

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "observation": self.observation}


@dataclass(frozen=True)
class ArchitectEscalation:
    """A named design/canon question, the only basis for HUMAN_REVIEW."""

    category: str
    question: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ArchitectEscalation":
        category = value["category"]
        if category not in ARCHITECT_ESCALATION_CATEGORIES:
            raise ArchitectPreflightError(
                f"unsupported escalation category: {category!r}"
            )
        question = value["question"]
        if type(question) is not str:
            raise ArchitectPreflightError("escalation.question must be a string")
        return cls(category=category, question=question.strip())

    @property
    def is_design_escalation(self) -> bool:
        return self.category in DESIGN_ESCALATION_CATEGORIES

    def to_dict(self) -> dict[str, str]:
        return {"category": self.category, "question": self.question}


@dataclass(frozen=True)
class UnknownSurfaceDisjointness:
    """A positive claim that the candidate misses an unobservable surface."""

    task_id: str
    justification: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "UnknownSurfaceDisjointness":
        try:
            task_id = validate_task_id(value["task_id"])
        except TaskReviewContractError as exc:
            raise ArchitectPreflightError(str(exc)) from exc
        return cls(
            task_id=task_id,
            justification=_nonempty_text(
                value["justification"],
                field="unknown_surface_disjointness.justification",
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {"task_id": self.task_id, "justification": self.justification}


@dataclass(frozen=True)
class ArchitectAdvisory:
    task_id: str
    source_head: str
    task_contract_sha256: str
    predicted_change_surface: PredictedChangeSurface
    integration_risk: str
    parallel_recommendation: str
    work_type_recommendation: str
    execution_recommendation: ExecutionRecommendation
    conflicting_task_ids: tuple[str, ...]
    conflict_reasons: tuple[str, ...]
    escalation: ArchitectEscalation
    unknown_surface_disjointness: tuple[UnknownSurfaceDisjointness, ...]
    design_advice: DesignAdvice
    evidence: tuple[EvidenceObservation, ...]
    confidence: float
    assumptions: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Any) -> "ArchitectAdvisory":
        try:
            validate_instance(value, ARCHITECT_ADVISORY_SCHEMA)
        except SchemaValidationError as exc:
            raise ArchitectPreflightError(f"architect advisory schema rejected: {exc}") from exc
        if not isinstance(value, Mapping):
            raise ArchitectPreflightError("architect advisory must be an object")
        try:
            task_id = validate_task_id(value["task_id"])
        except TaskReviewContractError as exc:
            raise ArchitectPreflightError(str(exc)) from exc
        source_head = _nonempty_text(value["source_head"], field="source_head")
        if GIT_SHA_RE.fullmatch(source_head) is None:
            raise ArchitectPreflightError("source_head must be a 40-character Git SHA")
        contract_sha = _nonempty_text(
            value["task_contract_sha256"], field="task_contract_sha256"
        )
        if SHA256_RE.fullmatch(contract_sha) is None:
            raise ArchitectPreflightError(
                "task_contract_sha256 must be a lowercase SHA-256 identity"
            )
        confidence = value["confidence"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
        ):
            raise ArchitectPreflightError("confidence must be a finite number")
        evidence = tuple(
            EvidenceObservation.from_dict(item) for item in value["evidence"]
        )
        if len({item.path.casefold() for item in evidence}) != len(evidence):
            raise ArchitectPreflightError("evidence contains duplicate repository paths")
        disjointness = tuple(
            UnknownSurfaceDisjointness.from_dict(item)
            for item in value["unknown_surface_disjointness"]
        )
        if len({item.task_id for item in disjointness}) != len(disjointness):
            raise ArchitectPreflightError(
                "unknown_surface_disjointness contains duplicate task IDs"
            )
        try:
            execution_recommendation = ExecutionRecommendation.from_dict(
                value["execution_recommendation"]
            )
        except ExecutionRoutingError as exc:
            raise ArchitectPreflightError(str(exc)) from exc
        return cls(
            task_id=task_id,
            source_head=source_head,
            task_contract_sha256=contract_sha,
            predicted_change_surface=PredictedChangeSurface.from_dict(
                value["predicted_change_surface"]
            ),
            integration_risk=value["integration_risk"],
            parallel_recommendation=value["parallel_recommendation"],
            work_type_recommendation=value["work_type_recommendation"],
            execution_recommendation=execution_recommendation,
            conflicting_task_ids=_text_tuple(
                value["conflicting_task_ids"],
                field="conflicting_task_ids",
                task_ids=True,
            ),
            conflict_reasons=_text_tuple(
                value["conflict_reasons"], field="conflict_reasons"
            ),
            escalation=ArchitectEscalation.from_dict(value["escalation"]),
            unknown_surface_disjointness=disjointness,
            design_advice=DesignAdvice.from_dict(value["design_advice"]),
            evidence=evidence,
            confidence=float(confidence),
            assumptions=_text_tuple(value["assumptions"], field="assumptions"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "source_head": self.source_head,
            "task_contract_sha256": self.task_contract_sha256,
            "predicted_change_surface": self.predicted_change_surface.to_dict(),
            "integration_risk": self.integration_risk,
            "parallel_recommendation": self.parallel_recommendation,
            "work_type_recommendation": self.work_type_recommendation,
            "execution_recommendation": self.execution_recommendation.to_dict(),
            "conflicting_task_ids": list(self.conflicting_task_ids),
            "conflict_reasons": list(self.conflict_reasons),
            "escalation": self.escalation.to_dict(),
            "unknown_surface_disjointness": [
                item.to_dict() for item in self.unknown_surface_disjointness
            ],
            "design_advice": self.design_advice.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "confidence": self.confidence,
            "assumptions": list(self.assumptions),
        }


@dataclass(frozen=True)
class ArchitectPolicyDecision:
    decision: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.decision not in {"start", "wait", "human_review"}:
            raise ArchitectPreflightError(
                f"unsupported architect policy decision: {self.decision!r}"
            )


@dataclass(frozen=True)
class DeterministicConflict:
    kind: str
    conflicting_task_id: str
    overlapping_values: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ArchitectAnalysis:
    analysis_id: str
    advisory: ArchitectAdvisory
    artifact_path: Path
    active_surface_fingerprint: str
    invocation_metadata: Mapping[str, Any]

    def to_transport_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ARCHITECT_ADVISORY_SCHEMA_VERSION,
            "analysis_id": self.analysis_id,
            "advisory": self.advisory.to_dict(),
            "artifact_name": self.artifact_path.name,
            "active_surface_fingerprint": self.active_surface_fingerprint,
            "invocation_metadata": dict(self.invocation_metadata),
        }


class ArchitectInvoker(Protocol):
    def __call__(self, request: AgentInvocationRequest) -> AgentResult: ...


def _json_safe(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        value = value.to_dict()
    return json.loads(
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
    )


def _reservation_dicts(reservations: Iterable[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in reservations:
        value = _json_safe(item)
        if not isinstance(value, dict):
            raise ArchitectPreflightError("integration reservations must be objects")
        normalized.append(value)
    return sorted(
        normalized,
        key=lambda item: (
            str(item.get("task_id") or ""),
            str(item.get("evidence_type") or ""),
        ),
    )


def active_surface_fingerprint(reservations: Iterable[Any]) -> str:
    """Hash stable reservation identity, not the live changed-path inventory.

    Current actual paths are deliberately excluded. They are re-read and
    compared deterministically on every poll, while including them here would
    invalidate every cached WAIT whenever an active worker edits one more
    file. Membership, durable workflow identity, committed resources,
    predicted surfaces, and observability state still invalidate the cache.
    """

    payload = []
    for item in _reservation_dicts(reservations):
        predicted_paths = item.get("predicted_paths") or []
        payload.append(
            {
                "task_id": item.get("task_id"),
                "workflow_state": item.get("workflow_state"),
                "phase": item.get("phase"),
                "branch": item.get("branch"),
                "head": item.get("head"),
                "exclusive_resources": item.get("exclusive_resources") or [],
                "predicted_paths": predicted_paths,
                "unity_serialized_assets_predicted": [
                    path
                    for path in item.get("unity_serialized_assets") or []
                    if path in predicted_paths
                ],
                "shared_systems": item.get("shared_systems") or [],
                "surface_unknown": bool(item.get("surface_unknown", False)),
                "local_active": bool(item.get("local_active", False)),
            }
        )
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_architect_prompt(
    *,
    task: Mapping[str, Any],
    source_head: str,
    reservations: Sequence[Any],
) -> str:
    task_id = validate_task_id(task.get("id"))
    contract_hash = _nonempty_text(
        task.get("task_contract_sha256"), field="task.task_contract_sha256"
    )
    reservation_values = _reservation_dicts(reservations)
    return f"""# Polling orchestrator read-only architect preflight

You are the advisory software architect for candidate `{task_id}` at committed source
HEAD `{source_head}` and task-contract SHA-256 `{contract_hash}`.

Authority and safety rules:
- The supplied committed task contract and current repository are evidence.
- Existing approved GDD and TaskGraph canon are authority. Do not redesign requirements.
- You are advisory only. Do not create or edit Tasks, GDD/canon, dependencies, resources,
  Git, GitHub Issues, claims, leases, branches, or any repository file.
- Do not choose a replacement or lower-ranked task. The deterministic Stage-2 planner
  owns selection and deterministic Python owns admission.
- Predict files, Unity assets, symbols, and systems this task will LIKELY need to modify.
- Compare that prediction with every supplied in-flight integration reservation. Actual
  changed paths and committed exclusive resources are stronger evidence than prediction.
- Pay special attention to Unity merge hot spots: `.unity`, `.prefab`, `.asset`, `.meta`
  and GUID implications, ProjectSettings, Packages, Input Actions, shared
  ScriptableObjects, and central managers or registries.
- Identify interface or design choices that would reduce coupling. Keep design advice
  separate from the scheduling recommendation. Suggestions for resource tokens,
  dependencies, TaskGraph changes, or decomposition are proposals only and will not be
  applied by this run.
- Return the ENTIRE strict output schema, including every list even when it is empty.
- Echo task_id, source_head, and task_contract_sha256 exactly as supplied.

Work-type recommendation:
- Always return `work_type_recommendation` as either `implementation` or
  `decomposition`. This is advisory and cannot bypass deterministic eligibility.
- Choose `decomposition` when this parent should be split now to unlock useful
  near-frontier work, even when other implementation tasks are available. Do not defer
  decomposition merely because the implementation pool is non-empty.
- Choose `implementation` when the task is already a coherent bounded unit. The
  scheduler will reject a recommendation that is not in the candidate's independently
  validated work-type pool; do not use this field to rewrite the task contract.

Scheduling policy you must follow:
- This scheduler optimizes for clean parallelism, not worker utilization. Waiting is
  cheap and safe; a merge or Unity-asset conflict is expensive.
- Use `parallel_recommendation: start` only when you can positively establish that this
  candidate is safe to run concurrently with every supplied reservation, and set
  `integration_risk` to `none` or `low` with honest `confidence`.
- Use `parallel_recommendation: wait` for EVERY kind of merge/integration uncertainty,
  including insufficient repository evidence, ambiguous overlap you cannot rule out, and
  an in-flight reservation whose surface is unknown. Use `integration_risk: unknown` when
  you cannot judge the risk. A wait is not an error and blocks nothing permanently: the
  scheduler simply considers another task and reconsiders this one when the repository or
  in-flight state changes. Never fabricate certainty to avoid waiting.
- Use `parallel_recommendation: human_review` ONLY for genuine design or canon authority
  ambiguity: incompatible architectures that would change intended design, work that
  cannot proceed without changing task scope/requirements/dependencies, or a task that
  should be decomposed or contractually changed before implementation. Never ask for a
  human merely because conflict prediction is uncertain; that is a wait.
- Set `escalation.category` to `none` unless you are raising exactly such a design/canon
  question. When it is not `none`, state the specific question a human must answer in
  `escalation.question`; leave `escalation.question` empty only for `none`.
- A reservation whose `surface_unknown` is true cannot be compared by paths. List it in
  `unknown_surface_disjointness` ONLY when you can positively justify that this candidate
  cannot touch that work, citing committed resources, an established subsystem boundary,
  observed paths, or the task contract. Omit it when you cannot; omission means wait for
  that pair, and it does not block unrelated repository work.

Execution capability recommendation (advisory only):
- Always return `execution_recommendation`. It cannot change WAIT or HUMAN_REVIEW into
  START and cannot bypass any deterministic admission gate.
- Recommend `fast` for mechanical or local work with a strong established pattern and
  low uncertainty; `standard` for ordinary gameplay implementation needing moderate
  reasoning; and `deep` for cross-system architecture, refactors,
  decomposition-adjacent work, or high uncertainty. These are judgment heuristics, not
  deterministic eligibility rules.
- Consider task size and scope, architectural uncertainty, the number and sharedness of
  systems, Unity serialized-asset risk, subsystem familiarity, the strength of existing
  patterns and tests, and expected rework cost.
- `provider_preference` may be `openai`, `claude`, or `no_preference`. This preference is
  advisory. Deterministic Python maps it to an allowed execution provider, model,
  reasoning effort, and budget. Never put a model identifier, reasoning effort, turn
  limit, Docker service/command, or environment variable in this recommendation.
- Give a non-empty rationale of no more than
  {MAX_RECOMMENDATION_RATIONALE_CHARACTERS} characters. Model names are operational
  configuration and never TaskGraph or game-design authority.

Committed task contract:
```json
{json.dumps(_json_safe(task), indent=2, ensure_ascii=False, sort_keys=True)}
```

In-flight integration reservations:
```json
{json.dumps(reservation_values, indent=2, ensure_ascii=False, sort_keys=True)}
```

Inspect the repository with read/search capability as needed. Cite repository paths and
concrete observations in `evidence`. Do not report that a path exists unless you observed
it. Put likely but unconfirmed paths in the predicted surface and explain the assumption.
"""


def build_architect_request(
    *,
    task: Mapping[str, Any],
    source_head: str,
    reservations: Sequence[Any],
    provider_configuration_key: str,
    max_turns: int = DEFAULT_ARCHITECT_MAX_TURNS,
    timeout_seconds: float = DEFAULT_ARCHITECT_TIMEOUT_SECONDS,
    run_id: str | None = None,
) -> AgentInvocationRequest:
    task_id = validate_task_id(task.get("id"))
    if GIT_SHA_RE.fullmatch(str(source_head)) is None:
        raise ArchitectPreflightError("source_head must be a 40-character Git SHA")
    generated_run_id = run_id or f"architect-{task_id.casefold()}-{uuid.uuid4().hex[:16]}"
    return AgentInvocationRequest(
        schema_version=AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
        run_id=generated_run_id,
        role="polling_architect",
        prompt=build_architect_prompt(
            task=task,
            source_head=source_head,
            reservations=reservations,
        ),
        context_paths=(
            f"Tasks/{task_id}.yaml",
            "Assets",
            "Packages",
            "ProjectSettings",
        ),
        allowed_capabilities=("repository_read", "repository_search"),
        write_boundaries=WriteBoundaries((), ()),
        output_schema=ARCHITECT_ADVISORY_SCHEMA,
        model_capability_class="high_reasoning",
        budgets=Budgets(max_turns, timeout_seconds, None),
        provider_configuration_key=provider_configuration_key,
    )


def _portfolio_candidates(
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return one strict, deterministic mixed-work candidate portfolio."""

    if not candidates:
        raise ArchitectPreflightError("architect portfolio must not be empty")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping) or set(candidate) != {
            "task",
            "eligible_work_types",
        }:
            raise ArchitectPreflightError(
                f"portfolio candidate {index} must contain exactly task and "
                "eligible_work_types"
            )
        task = candidate["task"]
        work_types = candidate["eligible_work_types"]
        if not isinstance(task, Mapping) or not isinstance(work_types, list):
            raise ArchitectPreflightError(
                f"portfolio candidate {index} has invalid task/work-type values"
            )
        task_id = validate_task_id(task.get("id"))
        if task_id in seen:
            raise ArchitectPreflightError(
                f"architect portfolio contains duplicate task {task_id}"
            )
        seen.add(task_id)
        contract_hash = _nonempty_text(
            task.get("task_contract_sha256"),
            field=f"portfolio[{task_id}].task_contract_sha256",
        )
        if SHA256_RE.fullmatch(contract_hash) is None:
            raise ArchitectPreflightError(
                f"portfolio task {task_id} has an invalid contract SHA-256"
            )
        if (
            not work_types
            or len(set(work_types)) != len(work_types)
            or any(
                type(work_type) is not str
                or work_type not in {"implementation", "decomposition"}
                for work_type in work_types
            )
        ):
            raise ArchitectPreflightError(
                f"portfolio task {task_id} has invalid eligible_work_types"
            )
        normalized.append(
            {
                "task": _json_safe(task),
                "eligible_work_types": sorted(work_types),
            }
        )
    return sorted(normalized, key=lambda item: item["task"]["id"])


def build_portfolio_prompt(
    *,
    candidates: Sequence[Mapping[str, Any]],
    source_head: str,
    reservations: Sequence[Any],
) -> str:
    """Ask for one exact task/work-type choice from a mixed safe pool."""

    if GIT_SHA_RE.fullmatch(str(source_head)) is None:
        raise ArchitectPreflightError("source_head must be a 40-character Git SHA")
    portfolio = _portfolio_candidates(candidates)
    reservations_value = _reservation_dicts(reservations)
    return f"""# Polling orchestrator mixed-work portfolio selection

You are the read-only software architect selecting exactly one next work item at
committed source HEAD `{source_head}`. Deterministic Python has already computed the
eligible work types for every candidate. You may choose implementation or decomposition
even while both kinds are available; do not treat decomposition as a fallback.

Authority and safety rules:
- Select exactly one supplied candidate and one value from that candidate's
  `eligible_work_types`. Never invent or alter a task, work type, identity, dependency,
  resource, TaskGraph contract, or repository file.
- Return the existing complete strict architect advisory schema for the selected task.
  Echo its task ID, task-contract SHA-256, and source HEAD exactly. Put the selected work
  type in `work_type_recommendation`.
- Prefer useful near-frontier decomposition when it unlocks safe parallel work or makes
  an oversized/uncertain parent executable. Prefer implementation when it is the most
  useful coherent ready unit. The presence of implementation work does not disqualify
  decomposition.
- Apply the same conservative parallel-integration policy as ordinary architect
  preflight: uncertainty is WAIT, design/canon ambiguity alone is HUMAN_REVIEW, and
  START requires positive evidence of disjointness from every supplied reservation.
- `execution_recommendation` is advisory only. Inspect repository evidence as needed,
  but use read/search capability only and claim no commands, tests, or changes.
- Return every schema field and every list, including empty lists. Every
  `evidence[].path` must be one exact repository-relative file path you actually
  observed, using `/` separators. Never put a glob or wildcard (`*` or `?`), an
  absolute path, parentheses, prose, multiple paths, or a `repo-file:` resource
  identifier in that field. If an observation comes from the supplied in-flight
  reservation data rather than one repository file, explain it in `assumptions`,
  `conflict_reasons`, or `unknown_surface_disjointness`; do not invent an evidence path.

Mixed eligible portfolio:
```json
{json.dumps(portfolio, indent=2, ensure_ascii=False, sort_keys=True)}
```

In-flight integration reservations:
```json
{json.dumps(reservations_value, indent=2, ensure_ascii=False, sort_keys=True)}
```
"""


def build_portfolio_request(
    *,
    candidates: Sequence[Mapping[str, Any]],
    source_head: str,
    reservations: Sequence[Any],
    provider_configuration_key: str,
    max_turns: int = DEFAULT_ARCHITECT_MAX_TURNS,
    timeout_seconds: float = DEFAULT_ARCHITECT_TIMEOUT_SECONDS,
    run_id: str | None = None,
) -> AgentInvocationRequest:
    portfolio = _portfolio_candidates(candidates)
    generated_run_id = run_id or f"architect-portfolio-{uuid.uuid4().hex[:16]}"
    task_paths = tuple(f"Tasks/{item['task']['id']}.yaml" for item in portfolio)
    return AgentInvocationRequest(
        schema_version=AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
        run_id=generated_run_id,
        role="polling_architect",
        prompt=build_portfolio_prompt(
            candidates=portfolio,
            source_head=source_head,
            reservations=reservations,
        ),
        context_paths=(*task_paths, "Assets", "Packages", "ProjectSettings"),
        allowed_capabilities=("repository_read", "repository_search"),
        write_boundaries=WriteBoundaries((), ()),
        output_schema=ARCHITECT_ADVISORY_SCHEMA,
        model_capability_class="high_reasoning",
        budgets=Budgets(max_turns, timeout_seconds, None),
        provider_configuration_key=provider_configuration_key,
    )


def _safe_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ArchitectPreflightError(f"advisory artifact already exists: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                value,
                stream,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def persist_architect_advisory(
    *,
    artifact_root: Path | str,
    analysis_id: str,
    scheduler_id: str,
    task: Mapping[str, Any],
    source_head: str,
    reservations: Sequence[Any],
    advisory: ArchitectAdvisory,
    invocation_metadata: Mapping[str, Any] | None = None,
) -> Path:
    task_id = validate_task_id(task.get("id"))
    artifact_path = Path(artifact_root) / f"{analysis_id}.json"
    fingerprint = active_surface_fingerprint(reservations)
    payload = {
        "schema_version": ARCHITECT_ADVISORY_SCHEMA_VERSION,
        "analysis_id": analysis_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scheduler": {
            "scheduler_id": _nonempty_text(scheduler_id, field="scheduler_id"),
            "candidate_task_id": task_id,
        },
        "candidate": {
            "task_id": task_id,
            "source_head": source_head,
            "task_contract_sha256": task.get("task_contract_sha256"),
        },
        "active_integration_surface_fingerprint": fingerprint,
        "structured_architect_output": advisory.to_dict(),
        "invocation": _json_safe(dict(invocation_metadata or {})),
        "authority": "advisory_only_not_applied",
        "explicitly_not_applied": {
            "taskgraph_changes": True,
            "gdd_or_canon_changes": True,
            "exclusive_resource_changes": True,
            "dependency_changes": True,
            "decomposition_changes": True,
        },
    }
    _safe_write_json(artifact_path, payload)
    return artifact_path


def analyze_candidate(
    *,
    task: Mapping[str, Any],
    source_head: str,
    reservations: Sequence[Any],
    scheduler_id: str,
    artifact_root: Path | str,
    invoker: ArchitectInvoker,
    provider_configuration_key: str,
    max_turns: int = DEFAULT_ARCHITECT_MAX_TURNS,
    timeout_seconds: float = DEFAULT_ARCHITECT_TIMEOUT_SECONDS,
) -> ArchitectAnalysis:
    task_id = validate_task_id(task.get("id"))
    contract_hash = _nonempty_text(
        task.get("task_contract_sha256"), field="task.task_contract_sha256"
    )
    analysis_id = (
        f"architect-{task_id.casefold()}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:12]}"
    )
    request = build_architect_request(
        task=task,
        source_head=source_head,
        reservations=reservations,
        provider_configuration_key=provider_configuration_key,
        max_turns=max_turns,
        timeout_seconds=timeout_seconds,
    )
    try:
        result = invoker(request)
    except Exception as exc:
        raise ArchitectPreflightError(
            f"architect AgentRuntime invocation failed: {type(exc).__name__}: {exc}"
        ) from exc
    if type(result) is not AgentResult:
        raise ArchitectPreflightError("architect invoker returned an invalid result container")
    if result.status != "succeeded":
        raise ArchitectPreflightError(
            "architect AgentRuntime failed "
            f"({result.failure_classification}): {result.failure_message}"
        )
    if (
        result.claimed_changed_paths
        or result.claims_execution_occurred
        or result.claimed_test_commands
    ):
        raise ArchitectPreflightError(
            "read-only architect claimed repository changes, command execution, or tests"
        )
    advisory = ArchitectAdvisory.from_dict(thaw_json(result.structured_output))
    if advisory.task_id != task_id:
        raise ArchitectPreflightError("architect changed candidate task identity")
    if advisory.source_head != source_head:
        raise ArchitectPreflightError("architect changed source HEAD identity")
    if advisory.task_contract_sha256 != contract_hash:
        raise ArchitectPreflightError("architect changed task-contract hash identity")
    result_dict = result.to_dict()
    invocation_metadata = {
        "agent_runtime_run_id": result.run_id,
        "provider": result.provider,
        "model": result.model,
        "duration_seconds": result.duration_seconds,
        "usage": result_dict.get("usage"),
        "agent_runtime_artifacts": f"agent_runtime/{result.run_id}",
    }
    artifact_path = persist_architect_advisory(
        artifact_root=artifact_root,
        analysis_id=analysis_id,
        scheduler_id=scheduler_id,
        task=task,
        source_head=source_head,
        reservations=reservations,
        advisory=advisory,
        invocation_metadata=invocation_metadata,
    )
    return ArchitectAnalysis(
        analysis_id=analysis_id,
        advisory=advisory,
        artifact_path=artifact_path,
        active_surface_fingerprint=active_surface_fingerprint(reservations),
        invocation_metadata=invocation_metadata,
    )


def analyze_portfolio(
    *,
    candidates: Sequence[Mapping[str, Any]],
    source_head: str,
    reservations: Sequence[Any],
    scheduler_id: str,
    artifact_root: Path | str,
    invoker: ArchitectInvoker,
    provider_configuration_key: str,
    max_turns: int = DEFAULT_ARCHITECT_MAX_TURNS,
    timeout_seconds: float = DEFAULT_ARCHITECT_TIMEOUT_SECONDS,
) -> ArchitectAnalysis:
    """Select and bind one exact candidate/work-type pair from a mixed pool."""

    portfolio = _portfolio_candidates(candidates)
    allowed = {
        (item["task"]["id"], work_type): item["task"]
        for item in portfolio
        for work_type in item["eligible_work_types"]
    }
    request = build_portfolio_request(
        candidates=portfolio,
        source_head=source_head,
        reservations=reservations,
        provider_configuration_key=provider_configuration_key,
        max_turns=max_turns,
        timeout_seconds=timeout_seconds,
    )
    try:
        result = invoker(request)
    except Exception as exc:
        raise ArchitectPreflightError(
            f"architect AgentRuntime invocation failed: {type(exc).__name__}: {exc}"
        ) from exc
    if type(result) is not AgentResult:
        raise ArchitectPreflightError("architect invoker returned an invalid result container")
    if result.status != "succeeded":
        raise ArchitectPreflightError(
            "architect AgentRuntime failed "
            f"({result.failure_classification}): {result.failure_message}"
        )
    if (
        result.claimed_changed_paths
        or result.claims_execution_occurred
        or result.claimed_test_commands
    ):
        raise ArchitectPreflightError(
            "read-only architect claimed repository changes, command execution, or tests"
        )
    advisory = ArchitectAdvisory.from_dict(thaw_json(result.structured_output))
    pair = (advisory.task_id, advisory.work_type_recommendation)
    selected = allowed.get(pair)
    if selected is None:
        raise ArchitectPreflightError(
            "architect selected a task/work-type pair outside the deterministic portfolio"
        )
    if advisory.source_head != source_head:
        raise ArchitectPreflightError("architect changed source HEAD identity")
    if advisory.task_contract_sha256 != selected["task_contract_sha256"]:
        raise ArchitectPreflightError("architect changed task-contract hash identity")

    analysis_id = (
        f"architect-portfolio-{advisory.task_id.casefold()}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:12]}"
    )
    artifact_path = Path(artifact_root) / f"{analysis_id}.json"
    result_dict = result.to_dict()
    invocation_metadata = {
        "agent_runtime_run_id": result.run_id,
        "provider": result.provider,
        "model": result.model,
        "duration_seconds": result.duration_seconds,
        "usage": result_dict.get("usage"),
        "agent_runtime_artifacts": f"agent_runtime/{result.run_id}",
    }
    _safe_write_json(
        artifact_path,
        {
            "schema_version": ARCHITECT_ADVISORY_SCHEMA_VERSION,
            "analysis_id": analysis_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "scheduler": {
                "scheduler_id": _nonempty_text(scheduler_id, field="scheduler_id"),
                "selected_task_id": advisory.task_id,
                "selected_work_type": advisory.work_type_recommendation,
            },
            "source_head": source_head,
            "eligible_portfolio": portfolio,
            "active_integration_surface_fingerprint": active_surface_fingerprint(
                reservations
            ),
            "structured_architect_output": advisory.to_dict(),
            "invocation": invocation_metadata,
            "authority": "advisory_selection_only_not_applied",
        },
    )
    return ArchitectAnalysis(
        analysis_id=analysis_id,
        advisory=advisory,
        artifact_path=artifact_path,
        active_surface_fingerprint=active_surface_fingerprint(reservations),
        invocation_metadata=invocation_metadata,
    )


def evaluate_architect_policy(
    advisory: ArchitectAdvisory,
    *,
    min_confidence: float = DEFAULT_ARCHITECT_MIN_CONFIDENCE,
) -> ArchitectPolicyDecision:
    """Resolve one advisory into START, WAIT, or HUMAN_REVIEW.

    Every form of parallel merge/integration uncertainty resolves to WAIT. Only
    a named design/canon escalation reaches a human, so an architect cannot turn
    ordinary conflict uncertainty into a human question.
    """

    if (
        isinstance(min_confidence, bool)
        or not isinstance(min_confidence, (int, float))
        or not math.isfinite(min_confidence)
        or not 0 <= min_confidence <= 1
    ):
        raise ArchitectPreflightError("minimum confidence must be in [0, 1]")
    escalation = advisory.escalation
    if escalation.category != "none":
        if not escalation.question:
            return ArchitectPolicyDecision(
                "wait",
                (
                    f"architect claimed escalation category {escalation.category!r} "
                    "without stating the design/canon question",
                ),
            )
        return ArchitectPolicyDecision(
            "human_review",
            (
                f"architect raised a {escalation.category} question that only a human "
                "design/canon authority can answer",
                escalation.question,
            ),
        )
    if advisory.parallel_recommendation == "human_review":
        return ArchitectPolicyDecision(
            "wait",
            (
                "architect requested human review without a design/canon escalation; "
                "merge and integration uncertainty is a wait, not a human question",
            ),
        )
    if advisory.confidence < min_confidence:
        return ArchitectPolicyDecision(
            "wait",
            (
                f"architect confidence {advisory.confidence:.3f} is below "
                f"the required {float(min_confidence):.3f}",
            ),
        )
    if advisory.integration_risk == "unknown":
        return ArchitectPolicyDecision(
            "wait", ("architect reported unknown integration risk",)
        )
    if advisory.parallel_recommendation == "wait":
        return ArchitectPolicyDecision("wait", ("architect recommended waiting",))
    if advisory.integration_risk in {"medium", "high"}:
        return ArchitectPolicyDecision(
            "wait",
            (f"{advisory.integration_risk} integration risk is not parallel-safe",),
        )
    if (
        advisory.parallel_recommendation == "start"
        and advisory.integration_risk in {"none", "low"}
    ):
        return ArchitectPolicyDecision("start", ())
    return ArchitectPolicyDecision(
        "wait", ("architect output did not satisfy the conservative start gate",)
    )


def _folded(values: Iterable[str]) -> dict[str, str]:
    return {value.casefold(): value for value in values}


def _path_collision_identity(value: str) -> str:
    """Normalize a repository path and its Unity ``.meta`` companion."""

    identity = value.casefold()
    return identity[:-5] if identity.endswith(".meta") else identity


def _folded_paths(values: Iterable[str]) -> dict[str, str]:
    return {_path_collision_identity(value): value for value in values}


def _reservation_value(reservation: Any, name: str, default: Any) -> Any:
    if isinstance(reservation, Mapping):
        return reservation.get(name, default)
    return getattr(reservation, name, default)


def detect_deterministic_conflict(
    *,
    candidate_task_id: str,
    candidate_exclusive_resources: Iterable[str],
    candidate_surface: PredictedChangeSurface,
    reservations: Iterable[Any],
) -> DeterministicConflict | None:
    candidate_task_id = validate_task_id(candidate_task_id)
    candidate_resources = _folded(candidate_exclusive_resources)
    candidate_exact = _folded_paths(candidate_surface.exact_paths)
    candidate_unity = _folded_paths(candidate_surface.unity_serialized_assets)
    ordered = sorted(
        reservations,
        key=lambda item: (
            str(_reservation_value(item, "task_id", "")),
            str(_reservation_value(item, "evidence_type", "")),
        ),
    )
    for reservation in ordered:
        other_id = str(_reservation_value(reservation, "task_id", "unknown"))
        local_active = bool(_reservation_value(reservation, "local_active", False))
        if other_id.casefold() == candidate_task_id.casefold():
            if local_active:
                return DeterministicConflict(
                    "active_task_id",
                    other_id,
                    (candidate_task_id,),
                    f"{candidate_task_id} is already active in this scheduler",
                )
            # A durable reservation for the candidate itself is the unfinished
            # work Stage 2 wants to resume, not a competing owner. Its own
            # branch paths and exclusive resources must not block it.
            continue
        other_resources = _folded(
            _reservation_value(reservation, "exclusive_resources", ())
        )
        resource_overlap = tuple(
            candidate_resources[key]
            for key in sorted(set(candidate_resources) & set(other_resources))
        )
        if resource_overlap:
            return DeterministicConflict(
                "exclusive_resource",
                other_id,
                resource_overlap,
                f"committed exclusive resources overlap {other_id}",
            )
        actual = _folded_paths(_reservation_value(reservation, "actual_paths", ()))
        exact_actual = tuple(
            candidate_exact[key]
            for key in sorted(set(candidate_exact) & set(actual))
        )
        if exact_actual:
            return DeterministicConflict(
                "exact_path_actual",
                other_id,
                exact_actual,
                f"candidate exact paths overlap actual changed paths for {other_id}",
            )
        other_unity_values = list(
            _reservation_value(reservation, "unity_serialized_assets", ())
        )
        for path in _reservation_value(reservation, "actual_paths", ()):
            if str(path).casefold().endswith(UNITY_SERIALIZED_SUFFIXES):
                other_unity_values.append(str(path))
        other_unity = _folded_paths(other_unity_values)
        unity_overlap = tuple(
            candidate_unity[key]
            for key in sorted(set(candidate_unity) & set(other_unity))
        )
        if unity_overlap:
            return DeterministicConflict(
                "unity_serialized_asset",
                other_id,
                unity_overlap,
                f"predicted Unity serialized assets overlap {other_id}",
            )
        if local_active:
            active_predicted = _folded_paths(
                _reservation_value(reservation, "predicted_paths", ())
            )
            predicted_overlap = tuple(
                candidate_exact[key]
                for key in sorted(set(candidate_exact) & set(active_predicted))
            )
            if predicted_overlap:
                return DeterministicConflict(
                    "active_predicted_exact_path",
                    other_id,
                    predicted_overlap,
                    f"candidate exact paths overlap active predicted paths for {other_id}",
                )
    return None


def effective_candidate_surface(
    *,
    candidate_task_id: str,
    predicted_surface: PredictedChangeSurface,
    reservations: Iterable[Any],
) -> PredictedChangeSurface:
    """Union the candidate's observed branch evidence over model prediction.

    A resumable task's own reservation is skipped on the competing-reservation
    side, but its actual changed paths are still part of what the candidate is
    already changing. This effective surface is compared with every *other*
    reservation, so actual branch evidence cannot be hidden by an incomplete
    prediction of the remaining work.
    """

    candidate_task_id = validate_task_id(candidate_task_id)
    exact_paths = list(predicted_surface.exact_paths)
    unity_assets = list(predicted_surface.unity_serialized_assets)
    unity_meta_suffixes = tuple(
        f"{suffix}.meta" for suffix in UNITY_SERIALIZED_SUFFIXES
    )
    for reservation in reservations:
        other_id = str(_reservation_value(reservation, "task_id", ""))
        if other_id.casefold() != candidate_task_id.casefold():
            continue
        actual_paths = tuple(
            str(value)
            for value in _reservation_value(reservation, "actual_paths", ())
        )
        exact_paths.extend(actual_paths)
        unity_assets.extend(
            str(value)
            for value in _reservation_value(
                reservation, "unity_serialized_assets", ()
            )
        )
        unity_assets.extend(
            path
            for path in actual_paths
            if path.casefold().endswith(UNITY_SERIALIZED_SUFFIXES)
            or path.casefold().endswith(unity_meta_suffixes)
        )
    folded_exact = _folded_paths(exact_paths)
    folded_unity = _folded_paths(unity_assets)
    return PredictedChangeSurface(
        exact_paths=tuple(folded_exact[key] for key in sorted(folded_exact)),
        path_patterns=predicted_surface.path_patterns,
        unity_serialized_assets=tuple(
            folded_unity[key] for key in sorted(folded_unity)
        ),
        symbols_or_components=predicted_surface.symbols_or_components,
        shared_systems=predicted_surface.shared_systems,
    )


@dataclass(frozen=True)
class UnknownSurfaceAssessment:
    """Per-reservation verdict for in-flight work whose surface is unknown.

    The decision is made per candidate/reservation pair so one partially
    observable human-held branch cannot deadlock the whole repository. A pair is
    only ``architect_confirmable`` when both sides declare committed exclusive
    resources and those declarations are disjoint; the architect must then still
    justify disjointness before the candidate may start.
    """

    blocking_task_ids: tuple[str, ...]
    architect_confirmable_task_ids: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def blocks_without_architect(self) -> bool:
        return bool(self.blocking_task_ids)


def assess_unknown_surface_reservations(
    *,
    candidate_task_id: str,
    candidate_exclusive_resources: Iterable[str],
    reservations: Iterable[Any],
) -> UnknownSurfaceAssessment:
    candidate_task_id = validate_task_id(candidate_task_id)
    candidate_resources = set(_folded(candidate_exclusive_resources))
    blocking: list[str] = []
    confirmable: list[str] = []
    reasons: list[str] = []
    for reservation in sorted(
        reservations,
        key=lambda item: str(_reservation_value(item, "task_id", "")),
    ):
        if not bool(_reservation_value(reservation, "surface_unknown", False)):
            continue
        other_id = str(_reservation_value(reservation, "task_id", "unknown"))
        if other_id.casefold() == candidate_task_id.casefold():
            continue
        other_resources = set(
            _folded(_reservation_value(reservation, "exclusive_resources", ()))
        )
        if not candidate_resources or not other_resources:
            blocking.append(other_id)
            reasons.append(
                f"{other_id} has an unobservable integration surface and neither side "
                "declares committed exclusive resources that could prove disjointness"
            )
            continue
        overlap = candidate_resources & other_resources
        if overlap:
            blocking.append(other_id)
            reasons.append(
                f"{other_id} has an unobservable integration surface and shares "
                "committed exclusive resources with the candidate"
            )
            continue
        confirmable.append(other_id)
        reasons.append(
            f"{other_id} has an unobservable integration surface; disjoint committed "
            "exclusive resources allow the architect to justify disjointness"
        )
    return UnknownSurfaceAssessment(
        blocking_task_ids=tuple(sorted(set(blocking))),
        architect_confirmable_task_ids=tuple(sorted(set(confirmable))),
        reasons=tuple(reasons),
    )


def unconfirmed_unknown_surface_task_ids(
    advisory: ArchitectAdvisory,
    assessment: UnknownSurfaceAssessment,
) -> tuple[str, ...]:
    """Return confirmable unknown surfaces the architect did not clear."""

    asserted = {
        item.task_id.casefold(): item
        for item in advisory.unknown_surface_disjointness
        if item.justification
    }
    conflicting = {value.casefold() for value in advisory.conflicting_task_ids}
    unconfirmed = [
        task_id
        for task_id in assessment.architect_confirmable_task_ids
        if task_id.casefold() not in asserted or task_id.casefold() in conflicting
    ]
    return tuple(sorted(set(unconfirmed)))


def architect_decision_cache_key(
    *,
    task_id: str,
    task_contract_sha256: str,
    source_head: str,
    integration_fingerprint: str,
) -> str:
    """Bind a cached non-start decision to every input that could change it."""

    task_id = validate_task_id(task_id)
    contract = _nonempty_text(task_contract_sha256, field="task_contract_sha256")
    head = _nonempty_text(source_head, field="source_head")
    fingerprint = _nonempty_text(
        integration_fingerprint, field="integration_fingerprint"
    )
    if SHA256_RE.fullmatch(contract) is None:
        raise ArchitectPreflightError("cache key requires a task-contract SHA-256")
    if GIT_SHA_RE.fullmatch(head) is None:
        raise ArchitectPreflightError("cache key requires a 40-character source HEAD")
    if SHA256_RE.fullmatch(fingerprint) is None:
        raise ArchitectPreflightError(
            "cache key requires an integration-surface fingerprint"
        )
    return f"{task_id}\n{contract}\n{head}\n{fingerprint}"


class ArchitectDecisionCache:
    """In-memory reuse of WAIT/HUMAN_REVIEW decisions for identical inputs.

    START is never cached: launching is a mutation and is always re-decided.
    Any change to the task contract, the source HEAD, or the in-flight
    integration fingerprint produces a different key, so a WAIT is reconsidered
    instead of becoming a permanent conflict blacklist.
    """

    def __init__(
        self, *, max_entries: int = DEFAULT_ARCHITECT_DECISION_CACHE_ENTRIES
    ) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 1:
            raise ArchitectPreflightError("cache max_entries must be a positive integer")
        self.max_entries = max_entries
        self._entries: dict[str, ArchitectPolicyDecision] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: str) -> ArchitectPolicyDecision | None:
        return self._entries.get(key)

    def remember(self, key: str, decision: ArchitectPolicyDecision) -> None:
        if decision.decision == "start":
            return
        self._entries.pop(key, None)
        self._entries[key] = decision
        while len(self._entries) > self.max_entries:
            oldest = next(iter(self._entries))
            del self._entries[oldest]

    def clear(self) -> None:
        self._entries.clear()


def _default_architecture_review_model(provider: str) -> str:
    review_root = ROOT / "Pipeline" / "ArchitectureReview"
    if str(review_root) not in sys.path:
        sys.path.insert(0, str(review_root))
    module_name = (
        "architecture_review_claude"
        if provider == "claude"
        else "architecture_review_codex"
    )
    module = importlib.import_module(module_name)
    model = str(getattr(module, "SYNTHESIS_MODEL", "")).strip()
    if not model:
        raise ArchitectPreflightError(
            f"{module_name} did not provide a configured synthesis model"
        )
    return model


class RuntimeArchitectInvoker:
    """Real provider-neutral AgentRuntime wiring used inside review containers."""

    def __init__(
        self,
        *,
        source: Path | str,
        artifact_root: Path | str,
        provider: str,
        model: str | None = None,
    ) -> None:
        self.source = Path(source).resolve()
        self.artifact_root = Path(artifact_root)
        self.provider_name = str(provider).strip().casefold()
        if self.provider_name not in ARCHITECT_PROVIDER_CONFIGURATION_KEYS:
            raise ArchitectPreflightError("architect provider must be claude or codex")
        self.model = str(model).strip() if model else _default_architecture_review_model(
            self.provider_name
        )
        self.configuration_key = ARCHITECT_PROVIDER_CONFIGURATION_KEYS[self.provider_name]
        if self.provider_name == "claude":
            provider_identifier = "claude-code"
            provider_adapter: Any = ClaudeCodeProvider(repository_root=self.source)
        else:
            provider_identifier = "openai-codex"
            provider_adapter = OpenAICodexProvider(
                reasoning_effort="max",
                externally_enforced_read_only_repository=True,
                repository_root=self.source,
            )
        configuration = RuntimeConfiguration(
            {
                self.configuration_key: {
                    "provider": provider_identifier,
                    "models": {
                        "low_cost": self.model,
                        "standard": self.model,
                        "high_reasoning": self.model,
                    },
                }
            }
        )
        self.runner = AgentRunner(
            self.artifact_root / "agent_runtime",
            configuration,
            {provider_identifier: provider_adapter},
        )

    def __call__(self, request: AgentInvocationRequest) -> AgentResult:
        if request.provider_configuration_key != self.configuration_key:
            raise ArchitectPreflightError(
                "architect request/provider configuration identity mismatch"
            )
        return self.runner.run(request)


def _strict_json(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant: {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive finite number")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--scheduler-id", required=True)
    parser.add_argument("--provider", choices=("claude", "codex"), default="claude")
    parser.add_argument("--model")
    parser.add_argument(
        "--max-turns", type=_positive_int, default=DEFAULT_ARCHITECT_MAX_TURNS
    )
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_float,
        default=DEFAULT_ARCHITECT_TIMEOUT_SECONDS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = _strict_json(sys.stdin.read())
        if not isinstance(payload, Mapping) or set(payload) not in ({
            "source_head",
            "task",
            "reservations",
        }, {
            "source_head",
            "candidates",
            "reservations",
        }):
            raise ArchitectPreflightError(
                "stdin must contain source_head/reservations and exactly one of task "
                "or candidates"
            )
        reservations = payload["reservations"]
        if not isinstance(reservations, list):
            raise ArchitectPreflightError("stdin reservations type is invalid")
        invoker = RuntimeArchitectInvoker(
            source=args.source,
            artifact_root=args.artifact_root,
            provider=args.provider,
            model=args.model,
        )
        if "task" in payload:
            task = payload["task"]
            if not isinstance(task, Mapping):
                raise ArchitectPreflightError("stdin task type is invalid")
            analysis = analyze_candidate(
                task=task,
                source_head=payload["source_head"],
                reservations=reservations,
                scheduler_id=args.scheduler_id,
                artifact_root=args.artifact_root,
                invoker=invoker,
                provider_configuration_key=invoker.configuration_key,
                max_turns=args.max_turns,
                timeout_seconds=args.timeout_seconds,
            )
        else:
            candidates = payload["candidates"]
            if not isinstance(candidates, list):
                raise ArchitectPreflightError("stdin candidates type is invalid")
            analysis = analyze_portfolio(
                candidates=candidates,
                source_head=payload["source_head"],
                reservations=reservations,
                scheduler_id=args.scheduler_id,
                artifact_root=args.artifact_root,
                invoker=invoker,
                provider_configuration_key=invoker.configuration_key,
                max_turns=args.max_turns,
                timeout_seconds=args.timeout_seconds,
            )
        print(
            json.dumps(
                analysis.to_transport_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
            )
        )
        return 0
    except (ArchitectPreflightError, ContractValidationError, ValueError, OSError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": ARCHITECT_ADVISORY_SCHEMA_VERSION,
                    "status": "architect_failed",
                    "error_type": type(exc).__name__,
                    "error": " ".join(str(exc).split())[:900],
                },
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARCHITECT_ADVISORY_SCHEMA",
    "ARCHITECT_ADVISORY_SCHEMA_VERSION",
    "ARCHITECT_ESCALATION_CATEGORIES",
    "ARCHITECT_PROVIDER_CONFIGURATION_KEYS",
    "DEFAULT_ARCHITECT_DECISION_CACHE_ENTRIES",
    "DEFAULT_ARCHITECT_MAX_TURNS",
    "DEFAULT_ARCHITECT_MIN_CONFIDENCE",
    "DEFAULT_ARCHITECT_TIMEOUT_SECONDS",
    "DESIGN_ESCALATION_CATEGORIES",
    "EXECUTION_RECOMMENDATION_SCHEMA",
    "UNITY_SERIALIZED_SUFFIXES",
    "ArchitectAdvisory",
    "ArchitectAnalysis",
    "ArchitectDecisionCache",
    "ArchitectEscalation",
    "ArchitectPolicyDecision",
    "ArchitectPreflightError",
    "DesignAdvice",
    "DeterministicConflict",
    "EvidenceObservation",
    "ExecutionRecommendation",
    "PredictedChangeSurface",
    "RuntimeArchitectInvoker",
    "UnknownSurfaceAssessment",
    "UnknownSurfaceDisjointness",
    "active_surface_fingerprint",
    "analyze_candidate",
    "analyze_portfolio",
    "architect_decision_cache_key",
    "assess_unknown_surface_reservations",
    "build_architect_prompt",
    "build_architect_request",
    "build_portfolio_prompt",
    "build_portfolio_request",
    "detect_deterministic_conflict",
    "effective_candidate_surface",
    "evaluate_architect_policy",
    "persist_architect_advisory",
    "unconfirmed_unknown_surface_task_ids",
]
