#!/usr/bin/env python3
"""Deterministic run-to-completion wrapper for the polling orchestrator.

This module deliberately does not select candidates, inspect change surfaces, or
launch workers.  ``PollingOrchestrator.poll_capacity_batch`` remains the single
scheduling authority and ``PollingOrchestrator._wait_for_architect_activity``
remains the worker/Issue wake implementation with its 300-second fallback.

The wrapper owns only an exact run manifest, coherent pre/post-poll observations,
strict graph-completion evidence, monotonic lifetime accounting, and conservative
deadlock detection.  The optional synthetic evidence pump is an injected host
boundary; it may publish exact machine-validation events, but this module has no
human-result API and cannot fabricate a human PASS.

Production snapshot, manifest/receipt-path, evidence-pump, CLI, and launcher
adapters live in separate modules so this controller retains injected,
deterministic authority boundaries. The shared scheduler factory owns the
100-completed-cycle architect lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping, Protocol, Sequence

from Pipeline.TaskReviewAgent.issue_workflow import WorkflowPhase, WorkflowState


AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION = "3.0"
AUTONOMOUS_GRAPH_PROGRESS_SCHEMA_VERSION = "1.0"
GRAPH_COMPLETE_RECEIPT_SCHEMA_VERSION = "1.0"
DEFAULT_FALLBACK_SECONDS = 300.0
MAX_AUTONOMOUS_CAPACITY = 10

_TASK_ID_RE = re.compile(r"NSC-[0-9]{3,}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
_RUN_ID_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?")
_GRAPH_PLAN_ID_RE = re.compile(r"GDP-[0-9a-f]{64}")
_GITHUB_REPOSITORY_RE = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})"
)
_LIFETIME_COUNTER_FIELDS = (
    "architect_invocations_total",
    "fallback_waits_total",
    "poll_cycles_total",
    "synthetic_pump_calls_total",
    "wakeups_total",
    "worker_launches_total",
)

CONFORMANCE_STATES = frozenset(
    {
        "conformant",
        "not_delivered",
        "needs_replan",
        "needs_human",
        "needs_testing",
        "invalid_evidence",
        "ambiguous_evidence",
        "aggregate",
        "superseded",
        "cancelled",
    }
)
_CONFORMANCE_DISPOSITION = {
    "conformant": "terminal_success",
    "not_delivered": "actionable",
    "needs_testing": "actionable",
    "aggregate": "actionable",
    "needs_replan": "terminal_blocked",
    "needs_human": "terminal_blocked",
    "invalid_evidence": "terminal_blocked",
    "ambiguous_evidence": "terminal_blocked",
    "superseded": "terminal_blocked",
    "cancelled": "terminal_blocked",
}
_LEGAL_STATE_PHASES = {
    WorkflowState.AGENT_READY: frozenset(
        {
            WorkflowPhase.IMPLEMENTATION,
            WorkflowPhase.REPAIR,
            WorkflowPhase.DELIVERY_EVIDENCE,
            WorkflowPhase.MERGE_CLOSEOUT,
            WorkflowPhase.DECOMPOSITION,
            WorkflowPhase.DECOMPOSITION_APPLY,
        }
    ),
    WorkflowState.AGENT_WORKING: frozenset(
        {
            WorkflowPhase.IMPLEMENTATION,
            WorkflowPhase.REPAIR,
            WorkflowPhase.DELIVERY_EVIDENCE,
            WorkflowPhase.MERGE_CLOSEOUT,
            WorkflowPhase.DECOMPOSITION,
            WorkflowPhase.DECOMPOSITION_APPLY,
        }
    ),
    WorkflowState.HUMAN_ACTION_REQUIRED: frozenset(
        {
            WorkflowPhase.UNITY_RUNTIME_VALIDATION,
            WorkflowPhase.DECOMPOSITION_APPLY_AUTHORIZATION,
        }
    ),
    WorkflowState.BLOCKED: frozenset(WorkflowPhase),
    WorkflowState.COMPLETE: frozenset(
        {WorkflowPhase.MERGE_CLOSEOUT, WorkflowPhase.DECOMPOSITION_APPLY}
    ),
}


class AutonomousGraphRunError(ValueError):
    """The autonomous run cannot be observed or continued safely."""


@dataclass(frozen=True)
class AutonomousRuntimeConfiguration:
    """Exact provider, rigor, retry, and synthetic-authority run binding."""

    execution_provider: str | None
    execution_model: str | None
    execution_max_turns: int | None
    architect_provider: str
    architect_model: str | None
    architect_max_turns: int
    architect_min_confidence: float
    architect_max_invocations_per_poll: int
    architect_min_reanalysis_seconds: float
    max_consecutive_observation_failures: int
    fatal_drain_seconds: float
    fallback_seconds: float
    synthetic_evidence_enabled: bool

    def __post_init__(self) -> None:
        if self.execution_provider not in {None, "claude", "codex"}:
            raise AutonomousGraphRunError("unsupported execution provider")
        if self.architect_provider not in {"claude", "codex"}:
            raise AutonomousGraphRunError("unsupported architect provider")
        for field in ("execution_model", "architect_model"):
            value = getattr(self, field)
            if value is not None:
                _text(value, field=field)
        for field in (
            "execution_max_turns",
            "architect_max_turns",
            "architect_max_invocations_per_poll",
            "max_consecutive_observation_failures",
        ):
            value = getattr(self, field)
            if value is None and field == "execution_max_turns":
                continue
            if type(value) is not int or value < 1:
                raise AutonomousGraphRunError(f"{field} must be a positive integer")
        for field in (
            "architect_min_confidence",
            "architect_min_reanalysis_seconds",
            "fatal_drain_seconds",
            "fallback_seconds",
        ):
            value = getattr(self, field)
            if type(value) not in {int, float} or isinstance(value, bool):
                raise AutonomousGraphRunError(f"{field} must be numeric")
            if not math.isfinite(value) or value < 0:
                raise AutonomousGraphRunError(f"{field} must be finite and non-negative")
        if not 0 <= self.architect_min_confidence <= 1:
            raise AutonomousGraphRunError("architect_min_confidence must be in [0, 1]")
        if not 0 < self.fallback_seconds <= DEFAULT_FALLBACK_SECONDS:
            raise AutonomousGraphRunError(
                f"fallback_seconds must be in (0, {DEFAULT_FALLBACK_SECONDS}]"
            )
        if type(self.synthetic_evidence_enabled) is not bool:
            raise AutonomousGraphRunError("synthetic_evidence_enabled must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }

    @classmethod
    def from_dict(cls, value: Any) -> "AutonomousRuntimeConfiguration":
        item = _exact_object(
            value,
            set(cls.__dataclass_fields__),
            label="autonomous runtime configuration",
        )
        return cls(**item)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _exact_object(value: Any, fields: set[str], *, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise AutonomousGraphRunError(f"{label} must be a built-in JSON object")
    if set(value) != fields:
        raise AutonomousGraphRunError(
            f"{label} fields differ from schema; "
            f"missing={sorted(fields - set(value))}, extras={sorted(set(value) - fields)}"
        )
    return value


def _text(value: Any, *, field: str) -> str:
    if type(value) is not str or not value:
        raise AutonomousGraphRunError(f"{field} must be non-empty built-in text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AutonomousGraphRunError(f"{field} must be valid UTF-8") from exc
    return value


def _task_id(value: Any, *, field: str) -> str:
    text = _text(value, field=field)
    if _TASK_ID_RE.fullmatch(text) is None:
        raise AutonomousGraphRunError(f"{field} must be an exact NSC task ID")
    return text


def _git_sha(value: Any, *, field: str) -> str:
    text = _text(value, field=field)
    if _GIT_SHA_RE.fullmatch(text) is None:
        raise AutonomousGraphRunError(f"{field} must be one exact lowercase Git SHA")
    return text


def _task_ids(values: Any, *, field: str, allow_empty: bool) -> tuple[str, ...]:
    if type(values) not in {list, tuple}:
        raise AutonomousGraphRunError(f"{field} must be a built-in list or tuple")
    normalized = tuple(_task_id(value, field=f"{field}[]") for value in values)
    if not allow_empty and not normalized:
        raise AutonomousGraphRunError(f"{field} must not be empty")
    if normalized != tuple(sorted(set(normalized))):
        raise AutonomousGraphRunError(f"{field} must be sorted and duplicate-free")
    return normalized


def _non_negative_integer(value: Any, *, field: str) -> int:
    if type(value) is not int or value < 0:
        raise AutonomousGraphRunError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class AutonomousRunManifest:
    """Exact immutable scope for one graph-completion run."""

    schema_version: str
    run_id: str
    source_repository: str
    github_repository: str
    runtime_configuration: AutonomousRuntimeConfiguration
    initial_source_commit: str
    initial_source_tree: str
    target_task_ids: tuple[str, ...]
    excluded_task_ids: tuple[str, ...]
    max_capacity: int

    def __post_init__(self) -> None:
        if self.schema_version != AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION:
            raise AutonomousGraphRunError("unsupported autonomous run schema version")
        run_id = _text(self.run_id, field="run_id")
        if _RUN_ID_RE.fullmatch(run_id) is None:
            raise AutonomousGraphRunError("run_id must be a lowercase ASCII slug")
        source = _text(self.source_repository, field="source_repository")
        if not Path(source).is_absolute():
            raise AutonomousGraphRunError("source_repository must be an absolute path")
        github_repository = _text(
            self.github_repository, field="github_repository"
        )
        if _GITHUB_REPOSITORY_RE.fullmatch(github_repository) is None:
            raise AutonomousGraphRunError(
                "github_repository must be an exact GitHub owner/repository identity"
            )
        if type(self.runtime_configuration) is not AutonomousRuntimeConfiguration:
            raise AutonomousGraphRunError(
                "runtime_configuration must be an exact AutonomousRuntimeConfiguration"
            )
        _git_sha(self.initial_source_commit, field="initial_source_commit")
        _git_sha(self.initial_source_tree, field="initial_source_tree")
        targets = _task_ids(
            self.target_task_ids, field="target_task_ids", allow_empty=False
        )
        excluded = _task_ids(
            self.excluded_task_ids, field="excluded_task_ids", allow_empty=True
        )
        if set(targets) & set(excluded):
            raise AutonomousGraphRunError(
                "target_task_ids and excluded_task_ids must be disjoint"
            )
        if (
            type(self.max_capacity) is not int
            or not 1 <= self.max_capacity <= MAX_AUTONOMOUS_CAPACITY
        ):
            raise AutonomousGraphRunError(
                f"max_capacity must be an integer in 1..{MAX_AUTONOMOUS_CAPACITY}"
            )
        object.__setattr__(self, "target_task_ids", targets)
        object.__setattr__(self, "excluded_task_ids", excluded)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "source_repository": self.source_repository,
            "github_repository": self.github_repository,
            "runtime_configuration": self.runtime_configuration.to_dict(),
            "initial_source_commit": self.initial_source_commit,
            "initial_source_tree": self.initial_source_tree,
            "target_task_ids": list(self.target_task_ids),
            "excluded_task_ids": list(self.excluded_task_ids),
            "max_capacity": self.max_capacity,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "AutonomousRunManifest":
        item = _exact_object(
            value,
            {
                "schema_version",
                "run_id",
                "source_repository",
                "github_repository",
                "runtime_configuration",
                "initial_source_commit",
                "initial_source_tree",
                "target_task_ids",
                "excluded_task_ids",
                "max_capacity",
            },
            label="autonomous run manifest",
        )
        return cls(
            schema_version=item["schema_version"],
            run_id=item["run_id"],
            source_repository=item["source_repository"],
            github_repository=item["github_repository"],
            runtime_configuration=AutonomousRuntimeConfiguration.from_dict(
                item["runtime_configuration"]
            ),
            initial_source_commit=item["initial_source_commit"],
            initial_source_tree=item["initial_source_tree"],
            target_task_ids=tuple(item["target_task_ids"]),
            excluded_task_ids=tuple(item["excluded_task_ids"]),
            max_capacity=item["max_capacity"],
        )

    @property
    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_json)


@dataclass(frozen=True)
class AutonomousRunPaths:
    """Host-owned artifact paths for one repository-bound autonomous run."""

    root: Path
    manifest: Path
    progress: Path
    receipt: Path
    events: Path


def autonomous_run_paths(
    *,
    checkout_root: Path | str,
    github_repository: str,
    run_id: str,
) -> AutonomousRunPaths:
    root = Path(checkout_root)
    if not root.is_absolute():
        raise AutonomousGraphRunError("checkout_root must be an absolute path")
    repository = _text(github_repository, field="github_repository")
    if _GITHUB_REPOSITORY_RE.fullmatch(repository) is None:
        raise AutonomousGraphRunError(
            "github_repository must be an exact GitHub owner/repository identity"
        )
    normalized_run_id = _text(run_id, field="run_id")
    if _RUN_ID_RE.fullmatch(normalized_run_id) is None:
        raise AutonomousGraphRunError("run_id must be a lowercase ASCII slug")
    repository_identity = _sha256(repository.casefold())
    run_root = (
        root
        / ".task-review-agent"
        / "autonomous-runs"
        / repository_identity
        / normalized_run_id
    )
    return AutonomousRunPaths(
        root=run_root,
        manifest=run_root / "manifest.json",
        progress=run_root / "progress.json",
        receipt=run_root / "graph-complete.json",
        events=run_root / "events.jsonl",
    )


class JsonManifestStore:
    """Create or load one immutable exact run manifest."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> AutonomousRunManifest | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AutonomousGraphRunError(
                f"autonomous run manifest is unreadable: {self.path}"
            ) from exc
        return AutonomousRunManifest.from_dict(payload)

    def create_or_load(
        self, expected: AutonomousRunManifest
    ) -> AutonomousRunManifest:
        existing = self.load()
        if existing is not None:
            if existing != expected:
                raise AutonomousGraphRunError(
                    "persisted manifest differs from the exact requested run"
                )
            return existing
        self.path.parent.mkdir(parents=True, exist_ok=True)
        claim_path = self.path.with_name(self.path.name + ".claim")
        temporary_path: Path | None = None
        claim_descriptor: int | None = None
        claim_owned = False
        try:
            try:
                claim_descriptor = os.open(
                    claim_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError as exc:
                existing = self.load()
                if existing is not None:
                    if existing != expected:
                        raise AutonomousGraphRunError(
                            "persisted manifest differs from the exact requested run"
                        ) from exc
                    return existing
                raise AutonomousGraphRunError(
                    "autonomous run manifest publication is already claimed"
                ) from exc
            claim_owned = True
            os.close(claim_descriptor)
            claim_descriptor = None
            existing = self.load()
            if existing is not None:
                if existing != expected:
                    raise AutonomousGraphRunError(
                        "persisted manifest differs from the exact requested run"
                    )
                return existing
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=self.path.name + ".",
                suffix=".tmp",
                dir=self.path.parent,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(expected.canonical_json + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            return expected
        finally:
            if claim_descriptor is not None:
                os.close(claim_descriptor)
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            if claim_owned:
                claim_path.unlink(missing_ok=True)


@dataclass(frozen=True)
class TaskObservation:
    """Conformance plus authorized committed decomposition descendants."""

    task_id: str
    conformance_state: str
    decomposition_children: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _task_id(self.task_id, field="task_id"))
        object.__setattr__(
            self,
            "conformance_state",
            _text(self.conformance_state, field="conformance_state"),
        )
        if self.conformance_state not in CONFORMANCE_STATES:
            raise AutonomousGraphRunError("conformance_state is unsupported")
        object.__setattr__(
            self,
            "decomposition_children",
            _task_ids(
                self.decomposition_children,
                field=f"{self.task_id}.decomposition_children",
                allow_empty=True,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "conformance_state": self.conformance_state,
            "decomposition_children": list(self.decomposition_children),
        }


@dataclass(frozen=True)
class ManagedIssueObservation:
    task_id: str
    state: WorkflowState
    phase: WorkflowPhase
    state_version: int
    last_event_id: str | None
    head_commit: str | None
    human_handoff_commit: str | None
    worker_id: str | None
    lease_id: str | None
    decomposition_run_id: str | None
    graph_delta_plan_id: str | None
    last_event_evidence_sha256: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _task_id(self.task_id, field="task_id"))
        if type(self.state) is not WorkflowState:
            raise AutonomousGraphRunError("issue.state must be an exact WorkflowState")
        if type(self.phase) is not WorkflowPhase:
            raise AutonomousGraphRunError("issue.phase must be an exact WorkflowPhase")
        if self.phase not in _LEGAL_STATE_PHASES[self.state]:
            raise AutonomousGraphRunError("Issue state/phase pair is not legal")
        _non_negative_integer(self.state_version, field="issue.state_version")
        if self.state_version == 0 and self.last_event_id is not None:
            raise AutonomousGraphRunError("version-zero Issue cannot name a last event")
        if self.state_version > 0 and (
            self.last_event_id is None or _SHA256_RE.fullmatch(self.last_event_id) is None
        ):
            raise AutonomousGraphRunError("versioned Issue requires an exact last event ID")
        for field in ("head_commit", "human_handoff_commit"):
            value = getattr(self, field)
            if value is not None:
                _git_sha(value, field=f"issue.{field}")
        for field in ("lease_id", "last_event_evidence_sha256"):
            value = getattr(self, field)
            if value is not None and _SHA256_RE.fullmatch(value) is None:
                raise AutonomousGraphRunError(f"issue.{field} must be null or SHA-256")
        if self.worker_id is not None:
            _text(self.worker_id, field="issue.worker_id")
        if self.decomposition_run_id is not None:
            _text(self.decomposition_run_id, field="issue.decomposition_run_id")
        if self.graph_delta_plan_id is not None and _GRAPH_PLAN_ID_RE.fullmatch(
            self.graph_delta_plan_id
        ) is None:
            raise AutonomousGraphRunError(
                "issue.graph_delta_plan_id must be null or an exact graph plan ID"
            )
        if self.state is WorkflowState.AGENT_WORKING:
            if self.worker_id is None or self.lease_id is None:
                raise AutonomousGraphRunError(
                    "agent_working Issue requires worker and lease identities"
                )
        elif self.worker_id is not None or self.lease_id is not None:
            raise AutonomousGraphRunError(
                "only agent_working Issue may retain worker or lease identity"
            )
        if self.state is WorkflowState.HUMAN_ACTION_REQUIRED and (
            self.head_commit is None
            or self.human_handoff_commit != self.head_commit
        ):
            raise AutonomousGraphRunError(
                "human_action_required Issue requires matching head/handoff commits"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "phase": self.phase.value,
            "state_version": self.state_version,
            "last_event_id": self.last_event_id,
            "head_commit": self.head_commit,
            "human_handoff_commit": self.human_handoff_commit,
            "worker_id": self.worker_id,
            "lease_id": self.lease_id,
            "decomposition_run_id": self.decomposition_run_id,
            "graph_delta_plan_id": self.graph_delta_plan_id,
            "last_event_evidence_sha256": self.last_event_evidence_sha256,
        }


@dataclass(frozen=True)
class CoherentGraphSnapshot:
    """One observer-produced TaskGraph/Issue/reservation point-in-time view."""

    observation_revision: int
    source_branch: str
    source_attached: bool
    source_clean: bool
    source_head: str
    source_tree: str
    origin_main_head: str
    initial_source_commit_is_ancestor: bool
    initial_source_tree: str
    tasks: tuple[TaskObservation, ...]
    managed_issues: tuple[ManagedIssueObservation, ...]
    active_assignment_task_ids: tuple[str, ...] = ()
    pending_transition_task_ids: tuple[str, ...] = ()
    reservation_task_ids: tuple[str, ...] = ()
    origin_main_is_ancestor_of_source: bool = True
    authorized_local_ahead_recovery_task_id: str | None = None
    authorized_local_ahead_recovery_commit: str | None = None

    def __post_init__(self) -> None:
        _non_negative_integer(self.observation_revision, field="observation_revision")
        _text(self.source_branch, field="source_branch")
        if type(self.source_attached) is not bool or type(self.source_clean) is not bool:
            raise AutonomousGraphRunError("source_attached/source_clean must be booleans")
        _git_sha(self.source_head, field="source_head")
        _git_sha(self.source_tree, field="source_tree")
        _git_sha(self.origin_main_head, field="origin_main_head")
        _git_sha(self.initial_source_tree, field="initial_source_tree")
        if type(self.initial_source_commit_is_ancestor) is not bool:
            raise AutonomousGraphRunError(
                "initial_source_commit_is_ancestor must be boolean"
            )
        if type(self.origin_main_is_ancestor_of_source) is not bool:
            raise AutonomousGraphRunError(
                "origin_main_is_ancestor_of_source must be boolean"
            )
        if (
            self.source_head == self.origin_main_head
            and not self.origin_main_is_ancestor_of_source
        ):
            raise AutonomousGraphRunError(
                "synced source must prove origin/main ancestry"
            )
        recovery_values = (
            self.authorized_local_ahead_recovery_task_id,
            self.authorized_local_ahead_recovery_commit,
        )
        if (recovery_values[0] is None) != (recovery_values[1] is None):
            raise AutonomousGraphRunError(
                "authorized local-ahead recovery requires task and commit identities"
            )
        if recovery_values[0] is not None:
            _task_id(recovery_values[0], field="authorized_local_ahead_recovery_task_id")
            _git_sha(
                recovery_values[1],
                field="authorized_local_ahead_recovery_commit",
            )
            if recovery_values[1] != self.source_head:
                raise AutonomousGraphRunError(
                    "authorized local-ahead recovery commit must equal source HEAD"
                )
            if self.source_head == self.origin_main_head:
                raise AutonomousGraphRunError(
                    "authorized local-ahead recovery cannot be declared on synced main"
                )
        if type(self.tasks) not in {tuple, list} or not all(
            type(item) is TaskObservation for item in self.tasks
        ):
            raise AutonomousGraphRunError("tasks must contain exact TaskObservation values")
        if type(self.managed_issues) not in {tuple, list} or not all(
            type(item) is ManagedIssueObservation for item in self.managed_issues
        ):
            raise AutonomousGraphRunError(
                "managed_issues must contain exact ManagedIssueObservation values"
            )
        tasks = tuple(sorted(self.tasks, key=lambda item: item.task_id))
        issues = tuple(sorted(self.managed_issues, key=lambda item: item.task_id))
        if len({item.task_id for item in tasks}) != len(tasks):
            raise AutonomousGraphRunError("snapshot contains duplicate task observations")
        if len({item.task_id for item in issues}) != len(issues):
            raise AutonomousGraphRunError("snapshot contains duplicate managed Issues")
        object.__setattr__(self, "tasks", tasks)
        object.__setattr__(self, "managed_issues", issues)
        for field in (
            "active_assignment_task_ids",
            "pending_transition_task_ids",
            "reservation_task_ids",
        ):
            object.__setattr__(
                self,
                field,
                _task_ids(getattr(self, field), field=field, allow_empty=True),
            )


@dataclass(frozen=True)
class GraphStateEvaluation:
    classification: str
    fingerprint: str
    relevant_task_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    internally_stalled: bool

    def __post_init__(self) -> None:
        if self.classification not in {
            "complete",
            "actionable",
            "temporary_wait",
            "blocked",
            "deadlock",
        }:
            raise AutonomousGraphRunError("unsupported graph-state classification")
        if _SHA256_RE.fullmatch(self.fingerprint) is None:
            raise AutonomousGraphRunError("evaluation fingerprint must be SHA-256")


def _relevant_task_ids(
    manifest: AutonomousRunManifest,
    tasks_by_id: Mapping[str, TaskObservation],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    excluded = set(manifest.excluded_task_ids)
    pending = list(reversed(manifest.target_task_ids))
    relevant: set[str] = set()
    missing: set[str] = set()
    while pending:
        task_id = pending.pop()
        if task_id in excluded or task_id in relevant:
            continue
        relevant.add(task_id)
        task = tasks_by_id.get(task_id)
        if task is None:
            missing.add(task_id)
            continue
        for child_id in reversed(task.decomposition_children):
            if child_id not in excluded and child_id not in relevant:
                pending.append(child_id)
    return tuple(sorted(relevant)), tuple(sorted(missing))


def eligible_synthetic_handoff_task_ids(
    snapshot: CoherentGraphSnapshot,
    *,
    relevant_task_ids: Sequence[str],
    excluded_task_ids: Sequence[str] = (),
) -> tuple[str, ...]:
    """Return the relevant tasks a synthetic evidence pump could act on now.

    These are the necessary conditions a waiting handoff must satisfy before an
    attempt is worth making: it is in run scope, it is not preserved for a real
    human result, nothing else currently owns it, and its managed Issue is
    actually waiting on a human action. The pump remains the sole authority on
    what it will finally select and mutate; this only decides whether asking is
    justified, so a conservative extra call is a no-op rather than a defect.

    A failed-push D1C recovery owns the source-main divergence, so no synthetic
    handoff is eligible while one is authorized.
    """
    if snapshot.authorized_local_ahead_recovery_task_id is not None:
        return ()
    relevant = set(relevant_task_ids)
    excluded = set(excluded_task_ids)
    unavailable = set(snapshot.active_assignment_task_ids).union(
        snapshot.pending_transition_task_ids
    )
    return tuple(
        sorted(
            issue.task_id
            for issue in snapshot.managed_issues
            if issue.task_id in relevant
            and issue.task_id not in excluded
            and issue.task_id not in unavailable
            and issue.state is WorkflowState.HUMAN_ACTION_REQUIRED
        )
    )


def evaluate_graph_state(
    manifest: AutonomousRunManifest,
    snapshot: CoherentGraphSnapshot,
) -> GraphStateEvaluation:
    """Classify one coherent observation without performing any mutation."""

    tasks_by_id = {item.task_id: item for item in snapshot.tasks}
    issues_by_id = {item.task_id: item for item in snapshot.managed_issues}
    relevant, missing = _relevant_task_ids(manifest, tasks_by_id)
    relevant_set = set(relevant)
    excluded = set(manifest.excluded_task_ids)

    active = tuple(
        task_id
        for task_id in snapshot.active_assignment_task_ids
        if task_id in relevant_set and task_id not in excluded
    )
    out_of_scope_active = tuple(
        task_id
        for task_id in snapshot.active_assignment_task_ids
        if task_id not in relevant_set
    )
    transitions = tuple(
        task_id
        for task_id in snapshot.pending_transition_task_ids
        if task_id in relevant_set and task_id not in excluded
    )
    reservations = tuple(
        task_id
        for task_id in snapshot.reservation_task_ids
        if task_id in relevant_set and task_id not in excluded
    )
    task_payload = [tasks_by_id[task_id].to_dict() for task_id in relevant if task_id in tasks_by_id]
    issue_payload = [
        issues_by_id[task_id].to_dict()
        for task_id in relevant
        if task_id in issues_by_id
    ]
    fingerprint_payload = {
        "manifest_sha256": manifest.sha256,
        "source": {
            "branch": snapshot.source_branch,
            "attached": snapshot.source_attached,
            "clean": snapshot.source_clean,
            "head": snapshot.source_head,
            "tree": snapshot.source_tree,
            "origin_main_head": snapshot.origin_main_head,
            "initial_source_commit_is_ancestor": (
                snapshot.initial_source_commit_is_ancestor
            ),
            "initial_source_tree": snapshot.initial_source_tree,
            "origin_main_is_ancestor_of_source": (
                snapshot.origin_main_is_ancestor_of_source
            ),
            "authorized_local_ahead_recovery_task_id": (
                snapshot.authorized_local_ahead_recovery_task_id
            ),
            "authorized_local_ahead_recovery_commit": (
                snapshot.authorized_local_ahead_recovery_commit
            ),
        },
        "tasks": task_payload,
        "managed_issues": issue_payload,
        "active_assignment_task_ids": list(active),
        "pending_transition_task_ids": list(transitions),
        "reservation_task_ids": list(reservations),
        "missing_task_ids": list(missing),
        "out_of_scope_active_assignment_task_ids": list(out_of_scope_active),
    }
    fingerprint = _sha256(_canonical_json(fingerprint_payload))

    reasons: list[str] = []
    source_base_safe = (
        snapshot.source_attached
        and snapshot.source_clean
        and snapshot.source_branch == "main"
    )
    source_synced = snapshot.source_head == snapshot.origin_main_head
    recovery_task_id = snapshot.authorized_local_ahead_recovery_task_id
    recovery_issue = issues_by_id.get(recovery_task_id or "")
    authorized_local_ahead = (
        recovery_task_id is not None
        and recovery_task_id in relevant_set
        and snapshot.authorized_local_ahead_recovery_commit == snapshot.source_head
        and snapshot.origin_main_is_ancestor_of_source
        and not source_synced
        and recovery_task_id in set(snapshot.reservation_task_ids)
        and recovery_issue is not None
        and recovery_issue.state is WorkflowState.AGENT_READY
        and recovery_issue.phase is WorkflowPhase.DECOMPOSITION_APPLY
    )
    if not source_base_safe or not (source_synced or authorized_local_ahead):
        reasons.append("source_not_clean_attached_main_synced_to_origin_main")
    if not snapshot.initial_source_commit_is_ancestor:
        reasons.append("initial_source_commit_is_not_an_ancestor_of_current_main")
    if snapshot.initial_source_tree != manifest.initial_source_tree or (
        snapshot.source_head == manifest.initial_source_commit
        and snapshot.source_tree != snapshot.initial_source_tree
    ):
        reasons.append("initial_source_tree_identity_mismatch")
    if missing:
        reasons.append("missing_authorized_tasks:" + ",".join(missing))
    terminal_dispositions = tuple(
        task_id
        for task_id in relevant
        if task_id in tasks_by_id
        and _CONFORMANCE_DISPOSITION[tasks_by_id[task_id].conformance_state]
        == "terminal_blocked"
    )
    blocked_issues = tuple(
        task_id
        for task_id in relevant
        if task_id in issues_by_id
        and issues_by_id[task_id].state is WorkflowState.BLOCKED
    )
    if terminal_dispositions:
        reasons.append(
            "terminal_task_disposition:"
            + ",".join(
                f"{task_id}={tasks_by_id[task_id].conformance_state}"
                for task_id in terminal_dispositions
            )
        )
    if blocked_issues:
        reasons.append("blocked_managed_issue:" + ",".join(blocked_issues))
    if out_of_scope_active:
        reasons.append(
            "live_assignment_outside_run_scope:" + ",".join(out_of_scope_active)
        )
    if reasons:
        return GraphStateEvaluation(
            "blocked", fingerprint, relevant, tuple(reasons), False
        )

    nonconformant = tuple(
        task_id
        for task_id in relevant
        if tasks_by_id[task_id].conformance_state != "conformant"
    )
    missing_issues = tuple(task_id for task_id in relevant if task_id not in issues_by_id)
    nonterminal_issues = tuple(
        task_id
        for task_id in relevant
        if task_id in issues_by_id
        and issues_by_id[task_id].state is not WorkflowState.COMPLETE
    )
    if (
        not nonconformant
        and not missing_issues
        and not nonterminal_issues
        and not active
        and not transitions
        and not reservations
        and source_synced
    ):
        return GraphStateEvaluation(
            "complete",
            fingerprint,
            relevant,
            ("strict_graph_completion_proven",),
            False,
        )

    externally_waiting = bool(active or transitions or reservations) or any(
        issues_by_id[task_id].state
        in {WorkflowState.AGENT_WORKING, WorkflowState.HUMAN_ACTION_REQUIRED}
        for task_id in relevant
        if task_id in issues_by_id
    )
    task_actionable = any(
        _CONFORMANCE_DISPOSITION[tasks_by_id[task_id].conformance_state]
        == "actionable"
        for task_id in relevant
        if task_id in tasks_by_id
    )
    actionable = bool(missing_issues) or task_actionable or any(
        task_id not in issues_by_id
        or issues_by_id[task_id].state is WorkflowState.AGENT_READY
        for task_id in set(nonconformant) | set(nonterminal_issues)
    )
    if externally_waiting:
        classification = "temporary_wait"
        reasons.append("external_work_or_transition_is_still_in_flight")
    elif actionable:
        classification = "actionable"
        reasons.append("run_scope_contains_schedulable_or_resumable_work")
    else:
        classification = "temporary_wait"
        reasons.append("no_external_progress_and_no_schedulable_work_observed")
    return GraphStateEvaluation(
        classification,
        fingerprint,
        relevant,
        tuple(reasons),
        not externally_waiting,
    )


@dataclass(frozen=True)
class AutonomousRunProgress:
    schema_version: str
    manifest_sha256: str
    poll_cycles_total: int = 0
    architect_invocations_total: int = 0
    worker_launches_total: int = 0
    synthetic_pump_calls_total: int = 0
    fallback_waits_total: int = 0
    wakeups_total: int = 0
    baseline_verified: bool = False
    last_fingerprint: str | None = None
    last_fallback_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != AUTONOMOUS_GRAPH_PROGRESS_SCHEMA_VERSION:
            raise AutonomousGraphRunError("unsupported autonomous progress schema")
        if _SHA256_RE.fullmatch(self.manifest_sha256) is None:
            raise AutonomousGraphRunError("manifest_sha256 must be SHA-256")
        for field in (
            "poll_cycles_total",
            "architect_invocations_total",
            "worker_launches_total",
            "synthetic_pump_calls_total",
            "fallback_waits_total",
            "wakeups_total",
        ):
            _non_negative_integer(getattr(self, field), field=field)
        if type(self.baseline_verified) is not bool:
            raise AutonomousGraphRunError("baseline_verified must be boolean")
        for field in ("last_fingerprint", "last_fallback_fingerprint"):
            value = getattr(self, field)
            if value is not None and _SHA256_RE.fullmatch(value) is None:
                raise AutonomousGraphRunError(f"{field} must be null or SHA-256")

    @classmethod
    def create(cls, manifest: AutonomousRunManifest) -> "AutonomousRunProgress":
        return cls(AUTONOMOUS_GRAPH_PROGRESS_SCHEMA_VERSION, manifest.sha256)

    def to_dict(self) -> dict[str, Any]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }

    @classmethod
    def from_dict(cls, value: Any) -> "AutonomousRunProgress":
        item = _exact_object(
            value,
            set(cls.__dataclass_fields__),
            label="autonomous run progress",
        )
        return cls(**item)


class ProgressStore(Protocol):
    def load(self) -> AutonomousRunProgress | None: ...
    def save(self, progress: AutonomousRunProgress) -> None: ...


class MemoryProgressStore:
    """Non-mutating process-memory store used by deterministic tests."""

    def __init__(self, value: AutonomousRunProgress | None = None) -> None:
        self.value = value

    def load(self) -> AutonomousRunProgress | None:
        return self.value

    def save(self, progress: AutonomousRunProgress) -> None:
        self.value = progress


class JsonProgressStore:
    """No-overwrite-identity, atomic JSON persistence for a host-owned run."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> AutonomousRunProgress | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AutonomousGraphRunError(
                f"autonomous progress is unreadable: {self.path}"
            ) from exc
        return AutonomousRunProgress.from_dict(payload)

    def save(self, progress: AutonomousRunProgress) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(_canonical_json(progress.to_dict()) + "\n", encoding="utf-8")
        temporary.replace(self.path)


class SchedulerPort(Protocol):
    source: Path
    max_workers: int
    excluded_task_ids: frozenset[str]
    active_assignments: Mapping[str, Any]
    architect_invocations_this_poll: int
    worker_launches_this_poll: int

    def set_admission_allowlist(self, task_ids: Sequence[str] | None) -> None: ...
    def start_activity_listener(self) -> bool: ...
    def close_activity_listener(self) -> None: ...
    def drain_active_workers(self, *, poll_seconds: float) -> bool: ...
    def poll_capacity_batch(self) -> Any: ...
    def _wait_for_architect_activity(self, poll_seconds: float) -> str: ...


class SchedulerLockPort(Protocol):
    def acquire(self) -> None: ...
    def release(self) -> None: ...


@dataclass(frozen=True)
class SyntheticEvidencePumpResult:
    """Exact machine-event identity claimed by one synthetic evidence pump."""

    task_id: str
    event_id: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _task_id(self.task_id, field="pump.task_id"))
        for field in ("event_id", "evidence_sha256"):
            if _SHA256_RE.fullmatch(getattr(self, field)) is None:
                raise AutonomousGraphRunError(f"pump.{field} must be SHA-256")


@dataclass(frozen=True)
class GraphCompleteReceipt:
    schema_version: str
    manifest_sha256: str
    evidence_fingerprint: str
    source_commit: str
    source_tree: str
    relevant_task_ids: tuple[str, ...]
    lifetime_counters: tuple[tuple[str, int], ...]
    receipt_sha256: str

    @classmethod
    def create(
        cls,
        *,
        manifest: AutonomousRunManifest,
        snapshot: CoherentGraphSnapshot,
        evaluation: GraphStateEvaluation,
        progress: AutonomousRunProgress,
    ) -> "GraphCompleteReceipt":
        if evaluation.classification != "complete":
            raise AutonomousGraphRunError(
                "a graph-complete receipt requires strict complete classification"
            )
        counters = tuple(
            (key, getattr(progress, key)) for key in _LIFETIME_COUNTER_FIELDS
        )
        body = {
            "schema_version": GRAPH_COMPLETE_RECEIPT_SCHEMA_VERSION,
            "manifest_sha256": manifest.sha256,
            "evidence_fingerprint": evaluation.fingerprint,
            "source_commit": snapshot.source_head,
            "source_tree": snapshot.source_tree,
            "relevant_task_ids": list(evaluation.relevant_task_ids),
            "lifetime_counters": dict(counters),
        }
        return cls(
            schema_version=body["schema_version"],
            manifest_sha256=body["manifest_sha256"],
            evidence_fingerprint=body["evidence_fingerprint"],
            source_commit=body["source_commit"],
            source_tree=body["source_tree"],
            relevant_task_ids=tuple(body["relevant_task_ids"]),
            lifetime_counters=counters,
            receipt_sha256=_sha256(_canonical_json(body)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest_sha256": self.manifest_sha256,
            "evidence_fingerprint": self.evidence_fingerprint,
            "source_commit": self.source_commit,
            "source_tree": self.source_tree,
            "relevant_task_ids": list(self.relevant_task_ids),
            "lifetime_counters": dict(self.lifetime_counters),
            "receipt_sha256": self.receipt_sha256,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "GraphCompleteReceipt":
        item = _exact_object(
            value,
            {
                "schema_version",
                "manifest_sha256",
                "evidence_fingerprint",
                "source_commit",
                "source_tree",
                "relevant_task_ids",
                "lifetime_counters",
                "receipt_sha256",
            },
            label="graph-complete receipt",
        )
        body = {key: item[key] for key in item if key != "receipt_sha256"}
        if item["schema_version"] != GRAPH_COMPLETE_RECEIPT_SCHEMA_VERSION:
            raise AutonomousGraphRunError("unsupported graph-complete receipt schema")
        for field in ("manifest_sha256", "evidence_fingerprint", "receipt_sha256"):
            value = item[field]
            if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
                raise AutonomousGraphRunError(f"receipt.{field} must be SHA-256")
        if _sha256(_canonical_json(body)) != item["receipt_sha256"]:
            raise AutonomousGraphRunError("graph-complete receipt identity is invalid")
        counters_raw = item["lifetime_counters"]
        if type(counters_raw) is not dict:
            raise AutonomousGraphRunError("receipt lifetime_counters must be an object")
        if set(counters_raw) != set(_LIFETIME_COUNTER_FIELDS):
            raise AutonomousGraphRunError(
                "receipt lifetime_counters differ from the exact counter schema"
            )
        counters = tuple(sorted(counters_raw.items()))
        for key, count in counters:
            _text(key, field="receipt lifetime counter")
            _non_negative_integer(count, field=f"receipt.{key}")
        return cls(
            schema_version=item["schema_version"],
            manifest_sha256=item["manifest_sha256"],
            evidence_fingerprint=item["evidence_fingerprint"],
            source_commit=_git_sha(item["source_commit"], field="receipt.source_commit"),
            source_tree=_git_sha(item["source_tree"], field="receipt.source_tree"),
            relevant_task_ids=_task_ids(
                item["relevant_task_ids"],
                field="receipt.relevant_task_ids",
                allow_empty=False,
            ),
            lifetime_counters=counters,
            receipt_sha256=item["receipt_sha256"],
        )


class ReceiptStore(Protocol):
    def load(self) -> GraphCompleteReceipt | None: ...
    def save(self, receipt: GraphCompleteReceipt) -> None: ...


class MemoryReceiptStore:
    def __init__(self) -> None:
        self.value: GraphCompleteReceipt | None = None

    def load(self) -> GraphCompleteReceipt | None:
        return self.value

    def save(self, receipt: GraphCompleteReceipt) -> None:
        if self.value is not None and self.value != receipt:
            raise AutonomousGraphRunError("a different graph-complete receipt already exists")
        self.value = receipt


class JsonReceiptStore:
    """Atomically persist exactly one immutable graph-complete receipt."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> GraphCompleteReceipt | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AutonomousGraphRunError(
                f"existing graph-complete receipt is unreadable: {self.path}"
            ) from exc
        return GraphCompleteReceipt.from_dict(payload)

    def _require_same_existing(self, receipt: GraphCompleteReceipt) -> None:
        existing = self.load()
        if existing is None:
            raise AutonomousGraphRunError(
                f"existing graph-complete receipt disappeared: {self.path}"
            )
        if existing != receipt:
            raise AutonomousGraphRunError(
                "a different graph-complete receipt already exists"
            )

    def save(self, receipt: GraphCompleteReceipt) -> None:
        if self.path.exists():
            self._require_same_existing(receipt)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        claim_path = self.path.with_name(self.path.name + ".claim")
        claim_descriptor: int | None = None
        claim_owned = False
        try:
            try:
                claim_descriptor = os.open(
                    claim_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError as exc:
                if self.path.exists():
                    self._require_same_existing(receipt)
                    return
                raise AutonomousGraphRunError(
                    "graph-complete receipt publication is already claimed"
                ) from exc
            claim_owned = True
            os.close(claim_descriptor)
            claim_descriptor = None
            if self.path.exists():
                self._require_same_existing(receipt)
                return
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=self.path.name + ".",
                suffix=".tmp",
                dir=self.path.parent,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(_canonical_json(receipt.to_dict()) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
        finally:
            if claim_descriptor is not None:
                os.close(claim_descriptor)
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            if claim_owned:
                claim_path.unlink(missing_ok=True)


@dataclass(frozen=True)
class AutonomousStepResult:
    evaluation: GraphStateEvaluation
    progress: AutonomousRunProgress
    cycle_status: str
    wait_reason: str | None = None
    receipt: GraphCompleteReceipt | None = None
    scheduler_fatal: bool = False


class AutonomousGraphController:
    """Thin locked run loop over one injected ``PollingOrchestrator`` instance."""

    def __init__(
        self,
        *,
        manifest: AutonomousRunManifest,
        scheduler: SchedulerPort,
        scheduler_lock: SchedulerLockPort,
        snapshotter: Callable[[], CoherentGraphSnapshot],
        progress_store: ProgressStore,
        receipt_store: ReceiptStore,
        synthetic_evidence_pump: (
            Callable[[CoherentGraphSnapshot], SyntheticEvidencePumpResult | None] | None
        ) = None,
        synthetic_excluded_task_ids: Sequence[str] = (),
        fallback_seconds: float = DEFAULT_FALLBACK_SECONDS,
    ) -> None:
        if type(fallback_seconds) not in {int, float} or isinstance(fallback_seconds, bool):
            raise AutonomousGraphRunError("fallback_seconds must be numeric")
        if not math.isfinite(fallback_seconds) or not 0 < fallback_seconds <= DEFAULT_FALLBACK_SECONDS:
            raise AutonomousGraphRunError(
                f"fallback_seconds must be in (0, {DEFAULT_FALLBACK_SECONDS}]"
            )
        self.manifest = manifest
        self._validate_scheduler_binding(scheduler)
        self.scheduler = scheduler
        self.scheduler_lock = scheduler_lock
        self.snapshotter = snapshotter
        self.progress_store = progress_store
        self.receipt_store = receipt_store
        self.synthetic_evidence_pump = synthetic_evidence_pump
        # Owned by the composition root so this deterministic controller never
        # has to name a gauntlet task ID itself.
        self.synthetic_excluded_task_ids = tuple(
            _task_id(value, field="synthetic_excluded_task_ids")
            for value in synthetic_excluded_task_ids
        )
        self.fallback_seconds = float(fallback_seconds)
        self._run_owned = False
        progress = progress_store.load() or AutonomousRunProgress.create(manifest)
        if progress.manifest_sha256 != manifest.sha256:
            raise AutonomousGraphRunError(
                "persisted progress belongs to a different exact run manifest"
            )
        self.progress = progress

    def _validate_scheduler_binding(self, scheduler: SchedulerPort) -> None:
        if getattr(scheduler, "max_workers", None) != self.manifest.max_capacity:
            raise AutonomousGraphRunError(
                "scheduler max_workers must exactly equal manifest max_capacity"
            )
        source = getattr(scheduler, "source", None)
        if source is None or Path(source).resolve() != Path(
            self.manifest.source_repository
        ).resolve():
            raise AutonomousGraphRunError(
                "scheduler source differs from the exact run manifest"
            )
        exclusions = getattr(scheduler, "excluded_task_ids", None)
        if type(exclusions) not in {set, frozenset} or set(exclusions) != set(
            self.manifest.excluded_task_ids
        ):
            raise AutonomousGraphRunError(
                "scheduler exclusions differ from the exact run manifest"
            )

    def _save(self, progress: AutonomousRunProgress) -> None:
        previous = self.progress
        for field in (
            "poll_cycles_total",
            "architect_invocations_total",
            "worker_launches_total",
            "synthetic_pump_calls_total",
            "fallback_waits_total",
            "wakeups_total",
        ):
            if getattr(progress, field) < getattr(previous, field):
                raise AutonomousGraphRunError(f"lifetime counter regressed: {field}")
        self.progress_store.save(progress)
        self.progress = progress

    def _completed_result_from_receipt(self) -> AutonomousStepResult | None:
        receipt = self.receipt_store.load()
        if receipt is None:
            return None
        if receipt.manifest_sha256 != self.manifest.sha256:
            raise AutonomousGraphRunError(
                "graph-complete receipt belongs to a different exact run manifest"
            )
        counters = dict(receipt.lifetime_counters)
        progress = replace(
            self.progress,
            **counters,
            baseline_verified=True,
            last_fingerprint=receipt.evidence_fingerprint,
            last_fallback_fingerprint=None,
        )
        evaluation = GraphStateEvaluation(
            "complete",
            receipt.evidence_fingerprint,
            receipt.relevant_task_ids,
            ("existing_graph_complete_receipt",),
            False,
        )
        return AutonomousStepResult(
            evaluation=evaluation,
            progress=progress,
            cycle_status="already_complete",
            receipt=receipt,
        )

    def _snapshot(self) -> CoherentGraphSnapshot:
        snapshot = self.snapshotter()
        if type(snapshot) is not CoherentGraphSnapshot:
            raise AutonomousGraphRunError(
                "snapshotter must return one exact CoherentGraphSnapshot"
            )
        return snapshot

    def _require_run_ownership(self) -> None:
        if not self._run_owned:
            raise AutonomousGraphRunError(
                "autonomous capacity passes require run-owned lock/listener lifecycle"
            )

    def _active_assignment_error(
        self,
        snapshot: CoherentGraphSnapshot,
        relevant_task_ids: Sequence[str],
    ) -> str | None:
        scheduler_active = set(self.scheduler.active_assignments)
        observed_active = set(snapshot.active_assignment_task_ids)
        if scheduler_active != observed_active:
            return "coherent snapshot and scheduler active assignments disagree"
        outside = sorted(scheduler_active - set(relevant_task_ids))
        if outside:
            return "live assignment outside exact run scope: " + ",".join(outside)
        return None

    def _evaluate_snapshot(
        self, snapshot: CoherentGraphSnapshot
    ) -> GraphStateEvaluation:
        evaluation = evaluate_graph_state(self.manifest, snapshot)
        assignment_error = self._active_assignment_error(
            snapshot, evaluation.relevant_task_ids
        )
        if assignment_error is None:
            return evaluation
        return GraphStateEvaluation(
            "blocked",
            evaluation.fingerprint,
            evaluation.relevant_task_ids,
            (assignment_error, *evaluation.reasons),
            False,
        )

    def _set_admission_scope(
        self,
        snapshot: CoherentGraphSnapshot,
        evaluation: GraphStateEvaluation,
    ) -> None:
        admission_scope = (
            (snapshot.authorized_local_ahead_recovery_task_id,)
            if snapshot.authorized_local_ahead_recovery_task_id is not None
            else evaluation.relevant_task_ids
        )
        self.scheduler.set_admission_allowlist(admission_scope)

    def _preflight(self) -> tuple[CoherentGraphSnapshot, GraphStateEvaluation]:
        self._require_run_ownership()
        snapshot = self._snapshot()
        evaluation = self._evaluate_snapshot(snapshot)
        if evaluation.classification != "blocked":
            self._set_admission_scope(snapshot, evaluation)
            if not self.progress.baseline_verified:
                self._save(replace(self.progress, baseline_verified=True))
        return snapshot, evaluation

    def _pump(
        self,
        pre_snapshot: CoherentGraphSnapshot,
        relevant_task_ids: Sequence[str],
    ) -> SyntheticEvidencePumpResult | None:
        self._require_run_ownership()
        if self.synthetic_evidence_pump is None:
            return None
        pump_result = self.synthetic_evidence_pump(pre_snapshot)
        if pump_result is not None and type(pump_result) is not SyntheticEvidencePumpResult:
            raise AutonomousGraphRunError(
                "synthetic evidence pump returned an unsupported result"
            )
        if pump_result is not None and pump_result.task_id not in set(
            relevant_task_ids
        ):
            raise AutonomousGraphRunError(
                "synthetic evidence pump targeted a task outside the pre-pump run scope"
            )
        self._save(
            replace(
                self.progress,
                synthetic_pump_calls_total=self.progress.synthetic_pump_calls_total + 1,
            )
        )
        return pump_result

    def _eligible_synthetic_handoffs(
        self,
        snapshot: CoherentGraphSnapshot,
        evaluation: GraphStateEvaluation,
    ) -> tuple[str, ...]:
        if self.synthetic_evidence_pump is None:
            return ()
        return eligible_synthetic_handoff_task_ids(
            snapshot,
            relevant_task_ids=evaluation.relevant_task_ids,
            excluded_task_ids=self.synthetic_excluded_task_ids,
        )

    def _pump_and_reobserve(
        self,
        snapshot: CoherentGraphSnapshot,
        evaluation: GraphStateEvaluation,
        *,
        cycle_status: str,
    ) -> tuple[
        SyntheticEvidencePumpResult | None,
        CoherentGraphSnapshot,
        GraphStateEvaluation,
        AutonomousStepResult | None,
    ]:
        """Attempt one synthetic mutation and prove it against a fresh observation.

        Returns the pump result, the authoritative snapshot/evaluation to carry
        forward, and a terminal step result when the mutation could not be proven
        or left the run blocked. This is the single mutation-and-proof path; both
        the pre-poll and post-poll attempts go through it so an unproven event,
        evidence hash, or state version fails closed identically either way.
        """
        pump_result = self._pump(snapshot, evaluation.relevant_task_ids)
        if pump_result is None:
            return None, snapshot, evaluation, None
        pump_snapshot = self._snapshot()
        pump_evaluation = self._evaluate_snapshot(pump_snapshot)
        if not self._pump_progress_proven(
            pump_result,
            pre_snapshot=snapshot,
            post_snapshot=pump_snapshot,
            relevant_task_ids=evaluation.relevant_task_ids,
        ):
            unproven = GraphStateEvaluation(
                "blocked",
                pump_evaluation.fingerprint,
                pump_evaluation.relevant_task_ids,
                ("synthetic_evidence_progress_was_not_proven_post_pump",),
                False,
            )
            return (
                pump_result,
                pump_snapshot,
                pump_evaluation,
                self._terminal_result(
                    unproven, pump_snapshot, "synthetic_evidence_unproven"
                ),
            )
        if pump_evaluation.classification == "blocked":
            return (
                pump_result,
                pump_snapshot,
                pump_evaluation,
                self._terminal_result(
                    pump_evaluation, pump_snapshot, cycle_status
                ),
            )
        self._set_admission_scope(pump_snapshot, pump_evaluation)
        return pump_result, pump_snapshot, pump_evaluation, None

    def _persist_poll_accounting(self) -> int:
        architect_invocations = getattr(
            self.scheduler, "architect_invocations_this_poll", None
        )
        _non_negative_integer(
            architect_invocations,
            field="scheduler.architect_invocations_this_poll",
        )
        launched = getattr(self.scheduler, "worker_launches_this_poll", None)
        _non_negative_integer(
            launched,
            field="scheduler.worker_launches_this_poll",
        )
        progress = self.progress
        progress = replace(
            progress,
            poll_cycles_total=progress.poll_cycles_total + 1,
            architect_invocations_total=(
                progress.architect_invocations_total + architect_invocations
            ),
            worker_launches_total=progress.worker_launches_total + launched,
        )
        self._save(progress)
        return launched

    def _poll(self) -> tuple[Any, int]:
        self._require_run_ownership()
        try:
            cycle = self.scheduler.poll_capacity_batch()
        finally:
            # The scheduler finalizes both per-pass counters even when its pass
            # raises after a spawn. Checkpoint them exactly once before Python
            # propagates that exception so a new controller cannot lose the
            # worker/architect cost from the interrupted pass.
            launched = self._persist_poll_accounting()
        return cycle, launched

    @staticmethod
    def _pump_progress_proven(
        result: SyntheticEvidencePumpResult,
        *,
        pre_snapshot: CoherentGraphSnapshot,
        post_snapshot: CoherentGraphSnapshot,
        relevant_task_ids: Sequence[str],
    ) -> bool:
        if result.task_id not in set(relevant_task_ids):
            return False
        before = next(
            (item for item in pre_snapshot.managed_issues if item.task_id == result.task_id),
            None,
        )
        after = next(
            (item for item in post_snapshot.managed_issues if item.task_id == result.task_id),
            None,
        )
        return (
            after is not None
            and (before is None or before.last_event_id != result.event_id)
            and (
                before is None
                or after.state_version > before.state_version
            )
            and after.last_event_id == result.event_id
            and after.last_event_evidence_sha256 == result.evidence_sha256
        )

    def _terminal_result(
        self,
        evaluation: GraphStateEvaluation,
        snapshot: CoherentGraphSnapshot,
        cycle_status: str,
        *,
        scheduler_fatal: bool = False,
    ) -> AutonomousStepResult:
        progress = replace(
            self.progress,
            last_fingerprint=evaluation.fingerprint,
            last_fallback_fingerprint=None,
        )
        self._save(progress)
        receipt = (
            GraphCompleteReceipt.create(
                manifest=self.manifest,
                snapshot=snapshot,
                evaluation=evaluation,
                progress=progress,
            )
            if evaluation.classification == "complete"
            else None
        )
        return AutonomousStepResult(
            evaluation,
            progress,
            cycle_status,
            receipt=receipt,
            scheduler_fatal=scheduler_fatal,
        )

    def _step(self) -> AutonomousStepResult:
        self._require_run_ownership()
        pre_snapshot, pre_evaluation = self._preflight()
        if pre_evaluation.classification in {"complete", "blocked"}:
            return self._terminal_result(
                pre_evaluation,
                pre_snapshot,
                "preflight_" + pre_evaluation.classification,
            )

        pump_result, pre_snapshot, pre_evaluation, terminal = self._pump_and_reobserve(
            pre_snapshot, pre_evaluation, cycle_status="post_pump_blocked"
        )
        if terminal is not None:
            return terminal

        cycle, launched = self._poll()
        cycle_status = _text(getattr(cycle, "status", None), field="cycle.status")
        cycle_fatal = getattr(cycle, "fatal", False)
        if type(cycle_fatal) is not bool:
            raise AutonomousGraphRunError("cycle.fatal must be boolean")
        snapshot = self._snapshot()
        evaluation = self._evaluate_snapshot(snapshot)
        if cycle_fatal:
            evaluation = GraphStateEvaluation(
                "blocked",
                evaluation.fingerprint,
                evaluation.relevant_task_ids,
                (f"scheduler_fatal:{cycle_status}", *evaluation.reasons),
                False,
            )
        if evaluation.classification in {"complete", "blocked"}:
            return self._terminal_result(
                evaluation,
                snapshot,
                cycle_status,
                scheduler_fatal=cycle_fatal,
            )

        # The poll itself can expose a newly eligible handoff by reaping the
        # worker that owned the task, so the pre-poll attempt legitimately saw
        # nothing. Waiting on that observation would wait for an external event
        # nobody is going to send, because the next action is this controller's
        # own synthetic transition. At most one mutation happens per step, so
        # this runs only when the pre-poll attempt produced none.
        if pump_result is None and self._eligible_synthetic_handoffs(
            snapshot, evaluation
        ):
            pump_result, snapshot, evaluation, terminal = self._pump_and_reobserve(
                snapshot, evaluation, cycle_status=cycle_status
            )
            if terminal is not None:
                return terminal
            if evaluation.classification in {"complete", "blocked"}:
                return self._terminal_result(evaluation, snapshot, cycle_status)

        changed = (
            pre_evaluation.fingerprint != evaluation.fingerprint
            or (
                self.progress.last_fingerprint is not None
                and self.progress.last_fingerprint != evaluation.fingerprint
            )
        )
        cycle_made_progress = launched > 0
        if (
            evaluation.internally_stalled
            and pump_result is None
            and not (cycle_made_progress or changed)
            and self.progress.last_fallback_fingerprint == evaluation.fingerprint
        ):
            deadlock = GraphStateEvaluation(
                "deadlock",
                evaluation.fingerprint,
                evaluation.relevant_task_ids,
                (*evaluation.reasons, "same_internal_state_observed_after_fallback"),
                True,
            )
            return self._terminal_result(deadlock, snapshot, cycle_status)

        progress = replace(
            self.progress,
            last_fingerprint=evaluation.fingerprint,
            last_fallback_fingerprint=(
                None if changed else self.progress.last_fallback_fingerprint
            ),
        )
        self._save(progress)
        if pump_result is not None or cycle_made_progress or changed:
            return AutonomousStepResult(evaluation, progress, cycle_status)

        wait_reason = self.scheduler._wait_for_architect_activity(self.fallback_seconds)
        if wait_reason in {"worker_returned", "issue_state_changed"}:
            progress = replace(
                self.progress,
                wakeups_total=self.progress.wakeups_total + 1,
                last_fallback_fingerprint=None,
            )
        elif wait_reason == "fallback_elapsed":
            progress = replace(
                self.progress,
                fallback_waits_total=self.progress.fallback_waits_total + 1,
                last_fallback_fingerprint=(
                    evaluation.fingerprint if evaluation.internally_stalled else None
                ),
            )
        else:
            raise AutonomousGraphRunError(
                f"scheduler returned unsupported wait reason: {wait_reason!r}"
            )
        self._save(progress)
        return AutonomousStepResult(
            evaluation, progress, cycle_status, wait_reason=wait_reason
        )

    def run(self, *, max_steps: int | None = None) -> AutonomousStepResult:
        if max_steps is not None and (type(max_steps) is not int or max_steps < 1):
            raise AutonomousGraphRunError("max_steps must be a positive integer")
        if self._run_owned:
            raise AutonomousGraphRunError("autonomous run lifecycle is already active")
        completed = self._completed_result_from_receipt()
        if completed is not None:
            return completed
        steps = 0
        lock_acquired = False
        drain_attempted = False
        try:
            self.scheduler_lock.acquire()
            lock_acquired = True
            self.scheduler.start_activity_listener()
            self._run_owned = True
            while True:
                result = self._step()
                steps += 1
                stopping = result.evaluation.classification in {
                    "complete",
                    "blocked",
                    "deadlock",
                } or (max_steps is not None and steps >= max_steps)
                if stopping and self.scheduler.active_assignments:
                    drain_attempted = True
                    drained = self.scheduler.drain_active_workers(
                        poll_seconds=self.fallback_seconds
                    )
                    if not drained:
                        raise AutonomousGraphRunError(
                            "active worker drain timed out before autonomous run stop"
                        )
                if result.receipt is not None:
                    self.receipt_store.save(result.receipt)
                if stopping:
                    return result
        except BaseException:
            if (
                lock_acquired
                and not drain_attempted
                and self.scheduler.active_assignments
            ):
                self.scheduler.drain_active_workers(poll_seconds=self.fallback_seconds)
            raise
        finally:
            if lock_acquired:
                self._run_owned = False
                try:
                    self.scheduler.close_activity_listener()
                finally:
                    self.scheduler_lock.release()


__all__ = [
    "AUTONOMOUS_GRAPH_PROGRESS_SCHEMA_VERSION",
    "AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION",
    "DEFAULT_FALLBACK_SECONDS",
    "GRAPH_COMPLETE_RECEIPT_SCHEMA_VERSION",
    "MAX_AUTONOMOUS_CAPACITY",
    "AutonomousGraphController",
    "AutonomousGraphRunError",
    "AutonomousRunManifest",
    "AutonomousRunPaths",
    "AutonomousRuntimeConfiguration",
    "AutonomousRunProgress",
    "AutonomousStepResult",
    "CoherentGraphSnapshot",
    "GraphCompleteReceipt",
    "GraphStateEvaluation",
    "JsonProgressStore",
    "JsonManifestStore",
    "JsonReceiptStore",
    "ManagedIssueObservation",
    "MemoryProgressStore",
    "MemoryReceiptStore",
    "SchedulerLockPort",
    "SyntheticEvidencePumpResult",
    "TaskObservation",
    "autonomous_run_paths",
    "eligible_synthetic_handoff_task_ids",
    "evaluate_graph_state",
]
