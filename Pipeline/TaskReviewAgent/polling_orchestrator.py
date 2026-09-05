#!/usr/bin/env python3
"""Supervised polling scheduler with a read-only architect preflight.

Stage 2 remains the only task-selection authority. This scheduler supplies
temporary per-poll exclusions, observes integration occupancy, asks the
architect for advice, applies deterministic conservative admission, and
launches one bounded ordered batch of exact-task workers per poll. It never claims a task or
mutates an Issue itself.

Admission optimizes for clean parallelism. Any uncertainty about parallel
merge/integration safety produces a WAIT: the candidate is excluded for this
scheduling pass only, nothing durable is mutated, Stage 2 may offer the next
ranked candidate, and the same task is reconsidered once the task contract,
source HEAD, or in-flight integration fingerprint changes. Only a named
design/canon escalation reaches a human.

``--dry-run`` is a pure observation mode: it acquires the singleton lock,
reaps already-injected local children, reads Stage 2 and integration state,
and reports the selected candidate. It never invokes an architect model and
never launches a worker. V1 has no cache-selection CLI, so dry-run does not
pretend that an absent advisory is approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PIPELINE_ROOT = ROOT / "Pipeline"
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

from Pipeline.TaskReviewAgent.architect_preflight import (  # noqa: E402
    ARCHITECT_ADVISORY_SCHEMA_VERSION,
    ARCHITECT_BATCH_SCHEMA_VERSION,
    ARCHITECT_SESSION_CAPABILITIES,
    ARCHITECT_SESSION_PROTOCOL,
    DEFAULT_ARCHITECT_MAX_TURNS,
    DEFAULT_ARCHITECT_MIN_CONFIDENCE,
    DEFAULT_ARCHITECT_TIMEOUT_SECONDS,
    UNITY_SERIALIZED_SUFFIXES,
    ArchitectAdvisory,
    ArchitectAnalysis,
    ArchitectBatch,
    ArchitectBatchAnalysis,
    ArchitectDecisionCache,
    ArchitectPolicyDecision,
    ArchitectPreflightError,
    PredictedChangeSurface,
    active_surface_fingerprint,
    architect_decision_cache_key,
    assess_unknown_surface_reservations,
    detect_deterministic_conflict,
    effective_candidate_surface,
    evaluate_architect_policy,
    unconfirmed_unknown_surface_task_ids,
    _default_architecture_review_model,
)
from Pipeline.TaskReviewAgent.architect_session_owner import (  # noqa: E402
    ARCHITECT_SESSION_ROLE,
    ArchitectSessionCompatibility,
    ArchitectSessionInvocationError,
    ArchitectSessionOwner,
    ArchitectSessionOwnerError,
    JsonArchitectSessionStore,
    provider_session_confirmation_from_dict,
)
from Pipeline.AgentRuntime.provider_sessions import (  # noqa: E402
    ProviderSessionBinding,
)
from Pipeline.TaskReviewAgent.committed_tasks import (  # noqa: E402
    CommittedTaskError,
    load_committed_task,
)
from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    GIT_SHA_RE,
    TaskReviewContractError,
    validate_task_id,
)
from Pipeline.TaskReviewAgent.decomposition_replay import (  # noqa: E402
    find_exact_d1c_commit,
    inspect_authorized_decomposition_replay,
)
from Pipeline.TaskReviewAgent.dispatch_plan import (  # noqa: E402
    DispatchPlan,
    TaskcontrolStateObservationError,
    plan_dispatch,
)
import Pipeline.TaskReviewAgent.dispatch_plan as dispatch_plan_module  # noqa: E402
from Pipeline.TaskReviewAgent.issue_queue import repo_root  # noqa: E402
from Pipeline.TaskReviewAgent.human_action_wait import (  # noqa: E402
    LocalArchitectWakeListener,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    STATE_RE,
    WorkflowContractError,
    WorkflowPhase,
    WorkflowState,
    parse_state,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueBackend,
    IssueConsistencyRetryBudget,
    IssueWorkflowSnapshot,
    IssueWorkflowService,
    IssueWorkflowStoreError,
    _consistent_snapshots,
    issue_author_authorized,
)
from Pipeline.TaskReviewAgent.real_checkout import default_checkout_root  # noqa: E402
from Pipeline.TaskReviewAgent.worker_result import (  # noqa: E402
    WorkerResultError,
    validate_worker_result,
)
from Pipeline.TaskReviewAgent.execution_routing import (  # noqa: E402
    ExecutionRoutingError,
    ExecutionRoutingPolicy,
    ResolvedExecutionRoute,
    load_execution_routing_policy,
    resolve_execution_route,
    resolve_task_rigor,
)
from Pipeline.TaskDecomposition.context_builder import (  # noqa: E402
    DecompositionPreflightError,
    validate_task_selection as validate_decomposition_task_selection,
)
from Pipeline.TaskReviewAgent.decomposition_policy_audit import (  # noqa: E402
    ValidationPolicyAuditError,
    audit_decomposition_policy,
    read_committed_tasks,
    read_policy_document,
)
from Pipeline.AgentRuntime.contracts import (  # noqa: E402
    ContractValidationError,
    validate_repository_path,
)


SCHEDULER_SCHEMA_VERSION = "1.0"
DEFAULT_POLL_SECONDS = 300.0
DEFAULT_MAX_WORKERS = 1
DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_POLL = 3
DEFAULT_ARCHITECT_MIN_REANALYSIS_SECONDS = 300.0
DEFAULT_MAX_CONSECUTIVE_OBSERVATION_FAILURES = 3
DEFAULT_FATAL_DRAIN_SECONDS = 1800.0
COMPOSE_PROJECT = "nosafecircle"
CONTAINER_SOURCE = "/workspace"
ARCHITECT_CONTAINER_ARTIFACT_ROOT = (
    "/workspace/Pipeline/ArchitectureReview/outputs/orchestrator/architect"
)
MAX_CANDIDATES_PER_POLL = 1000
FRESH_POOL_UNAVAILABLE_REASON = (
    "fresh_pool_unavailable_taskgraph_observation_failed_resume_only"
)

_DECOMPOSITION_COMPATIBLE_STAGE2_REASONS = frozenset(
    {
        "unsupported_kind",
        "execution_scope_not_single_agent",
        "decomposition_state_not_concrete",
        "derived_state_not_fresh:aggregate",
    }
)


class PollingOrchestratorError(TaskReviewContractError):
    """The scheduler could not safely continue."""


class SchedulerAlreadyActive(PollingOrchestratorError):
    """Another process owns the non-blocking OS scheduler lock."""


class IntegrationObservationError(PollingOrchestratorError):
    """An in-flight integration surface could not be observed safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_error(exc: BaseException, limit: int = 900) -> str:
    text = " ".join(str(exc).split()) or type(exc).__name__
    return text if len(text) <= limit else text[:limit] + "... [truncated]"


def _normalized_path(value: str) -> str:
    text = str(value).replace("\\", "/")
    try:
        return validate_repository_path(text, field="integration reservation path")
    except ContractValidationError as exc:
        raise IntegrationObservationError(
            f"Git returned a non-normalized repository path: {value!r}"
        ) from exc


def _path_tuple(values: Iterable[str]) -> tuple[str, ...]:
    by_identity: dict[str, str] = {}
    for value in values:
        path = _normalized_path(value)
        by_identity.setdefault(path.casefold(), path)
    return tuple(by_identity[key] for key in sorted(by_identity))


def _text_tuple(values: Iterable[str]) -> tuple[str, ...]:
    by_identity: dict[str, str] = {}
    for value in values:
        text = str(value).strip()
        if not text:
            raise IntegrationObservationError("reservation values must be non-empty")
        by_identity.setdefault(text.casefold(), text)
    return tuple(by_identity[key] for key in sorted(by_identity))


def _unity_paths(paths: Iterable[str]) -> tuple[str, ...]:
    return _path_tuple(
        path
        for path in paths
        if str(path).casefold().endswith(UNITY_SERIALIZED_SUFFIXES)
    )


@dataclass(frozen=True)
class IntegrationReservation:
    task_id: str
    workflow_state: str | None
    phase: str | None
    branch: str | None
    head: str | None
    checkout_path: str | None
    exclusive_resources: tuple[str, ...]
    predicted_paths: tuple[str, ...]
    actual_paths: tuple[str, ...]
    unity_serialized_assets: tuple[str, ...]
    shared_systems: tuple[str, ...]
    confidence: float
    evidence_type: str
    surface_unknown: bool = False
    local_active: bool = False
    # Set when this reservation is a bounded, recognized label-ahead-of-body
    # transition. The task is never admitted while set, but its resources stay
    # reserved and the rest of the poll continues normally.
    pending_transition: Mapping[str, Any] | None = None
    # Exact canonical D1C commit proven from the approved plan and current
    # controller ancestry. This permits only that task to recover when a prior
    # push failed after creating the local D1C commit.
    authorized_decomposition_apply_commit: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", validate_task_id(self.task_id))
        object.__setattr__(
            self, "exclusive_resources", _text_tuple(self.exclusive_resources)
        )
        object.__setattr__(self, "predicted_paths", _path_tuple(self.predicted_paths))
        object.__setattr__(self, "actual_paths", _path_tuple(self.actual_paths))
        object.__setattr__(
            self,
            "unity_serialized_assets",
            _path_tuple(self.unity_serialized_assets),
        )
        object.__setattr__(self, "shared_systems", _text_tuple(self.shared_systems))
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not math.isfinite(self.confidence)
            or not 0 <= self.confidence <= 1
        ):
            raise IntegrationObservationError("reservation confidence must be in [0, 1]")
        if type(self.evidence_type) is not str or not self.evidence_type.strip():
            raise IntegrationObservationError("reservation evidence_type must be non-empty")
        if type(self.surface_unknown) is not bool or type(self.local_active) is not bool:
            raise IntegrationObservationError("reservation flags must be boolean")
        if (
            self.authorized_decomposition_apply_commit is not None
            and re.fullmatch(
                r"[0-9a-f]{40}", self.authorized_decomposition_apply_commit
            )
            is None
        ):
            raise IntegrationObservationError(
                "authorized decomposition apply commit must be one exact Git SHA"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "workflow_state": self.workflow_state,
            "phase": self.phase,
            "branch": self.branch,
            "head": self.head,
            "checkout_path": self.checkout_path,
            "exclusive_resources": list(self.exclusive_resources),
            "predicted_paths": list(self.predicted_paths),
            "actual_paths": list(self.actual_paths),
            "unity_serialized_assets": list(self.unity_serialized_assets),
            "shared_systems": list(self.shared_systems),
            "confidence": self.confidence,
            "evidence_type": self.evidence_type,
            "surface_unknown": self.surface_unknown,
            "local_active": self.local_active,
            "pending_transition": (
                dict(self.pending_transition)
                if self.pending_transition is not None
                else None
            ),
            "authorized_decomposition_apply_commit": (
                self.authorized_decomposition_apply_commit
            ),
        }


@dataclass(frozen=True)
class DurableWorkflowObservation:
    """One shared managed-Issue batch and reservations derived from it."""

    snapshots: tuple[IssueWorkflowSnapshot, ...]
    reservations: tuple[IntegrationReservation, ...]

    def __post_init__(self) -> None:
        if type(self.snapshots) not in {tuple, list} or not all(
            hasattr(item, "issue_number") and hasattr(item, "state")
            for item in self.snapshots
        ):
            raise IntegrationObservationError(
                "durable workflow snapshots must contain parsed Issue workflow values"
            )
        if not all(type(item) is IntegrationReservation for item in self.reservations):
            raise IntegrationObservationError(
                "durable workflow reservations must contain exact IntegrationReservation values"
            )
        snapshots = tuple(sorted(self.snapshots, key=lambda item: item.issue_number))
        reservations = tuple(
            sorted(self.reservations, key=lambda item: (item.task_id, item.evidence_type))
        )
        if len({item.issue_number for item in snapshots}) != len(snapshots):
            raise IntegrationObservationError(
                "durable workflow observation contains duplicate Issue numbers"
            )
        object.__setattr__(self, "snapshots", snapshots)
        object.__setattr__(self, "reservations", reservations)


@dataclass
class ActiveAssignment:
    task_id: str
    worker_id: str
    process: Any
    checkout_path: Path
    exclusive_resources: tuple[str, ...]
    architect_surface: PredictedChangeSurface
    architect_confidence: float
    advisory_artifact_path: Path
    start_time_utc: str
    run_id: str
    result_artifact_path: Path
    source_head: str
    task_contract_sha256: str
    issue_number: int | None = None
    actual_changed_paths: tuple[str, ...] = field(default_factory=tuple)
    observation_error: str | None = None
    checkout_observed_once: bool = False

    @property
    def pid(self) -> int | None:
        value = getattr(self.process, "pid", None)
        return value if isinstance(value, int) else None

    def to_reservation(self) -> IntegrationReservation:
        unity = _path_tuple(
            (*self.architect_surface.unity_serialized_assets, *_unity_paths(self.actual_changed_paths))
        )
        return IntegrationReservation(
            task_id=self.task_id,
            workflow_state="scheduler_active",
            phase=None,
            branch=None,
            head=None,
            checkout_path=str(self.checkout_path),
            exclusive_resources=self.exclusive_resources,
            predicted_paths=self.architect_surface.exact_paths,
            actual_paths=self.actual_changed_paths,
            unity_serialized_assets=unity,
            shared_systems=self.architect_surface.shared_systems,
            confidence=self.architect_confidence,
            evidence_type=(
                "scheduler_prediction_actual_observation_unknown"
                if self.observation_error
                else (
                    "scheduler_prediction_and_actual_git"
                    if self.actual_changed_paths
                    else (
                        "scheduler_prediction_checkout_observed_empty"
                        if self.checkout_observed_once
                        else "scheduler_prediction_checkout_pending"
                    )
                )
            ),
            surface_unknown=self.observation_error is not None,
            local_active=True,
        )


class JsonEventEmitter:
    def __init__(
        self,
        stream: Any = None,
        *,
        journal_path: Path | str | None = None,
    ) -> None:
        self.stream = sys.stdout if stream is None else stream
        self.journal_path = (
            Path(journal_path).resolve() if journal_path is not None else None
        )
        if self.journal_path is not None:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, **values: Any) -> None:
        payload = {
            "schema_version": SCHEDULER_SCHEMA_VERSION,
            "event": event,
            "timestamp_utc": utc_now(),
            **values,
        }
        line = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
        ) + "\n"
        self.stream.write(line)
        self.stream.flush()
        if self.journal_path is not None:
            with self.journal_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()


class SchedulerLock:
    """Non-blocking OS-backed lock; file existence carries no authority."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._handle: Any = None

    def acquire(self) -> None:
        if self._handle is not None:
            raise PollingOrchestratorError("scheduler lock is already held by this object")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise SchedulerAlreadyActive("scheduler_already_active") from exc
            else:
                import fcntl

                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise SchedulerAlreadyActive("scheduler_already_active") from exc
        except BaseException:
            handle.close()
            raise
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None

    @property
    def is_held(self) -> bool:
        return self._handle is not None

    def __enter__(self) -> "SchedulerLock":
        self.acquire()
        return self

    def __exit__(self, _kind: Any, _value: Any, _traceback: Any) -> None:
        self.release()


def scheduler_lock_path(
    *,
    checkout_root: Path | str,
    source: Path | str | None = None,
) -> Path:
    # ``source`` is accepted for caller diagnostics/backward readability, but
    # it deliberately does not participate in either the path or digest. Two
    # source clones sharing one checkout root must contend on the same file.
    if source is not None:
        Path(source).resolve()
    resolved_checkout_root = Path(checkout_root).resolve()
    identity_text = str(resolved_checkout_root)
    if os.name == "nt":
        identity_text = identity_text.casefold()
    identity = identity_text.encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()[:24]
    return (
        resolved_checkout_root
        / ".task-review-agent"
        / "locks"
        / f"scheduler-{digest}.lock"
    )


def _run_git(
    root: Path,
    *args: str,
    timeout_seconds: float = 60.0,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ("git", "-C", str(root), *args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IntegrationObservationError(
            f"Git observation failed for {root}: {type(exc).__name__}: {exc}"
        ) from exc


def committed_path_probe(source: Path, commit: str) -> Callable[[str], bool]:
    """Return a bounded "does this exact path already exist at this commit" oracle.

    The rigor policy uses it to tell a brand-new deterministic `<script>.cs.meta`
    import sidecar apart from an edit to one that already exists. The committed
    tree is loaded once, compared case-insensitively for the Windows/Unity
    checkout contract, and cached for the complete admission batch. A Git
    observation failure raises instead of being misreported as a missing path.
    """

    committed_paths: frozenset[str] | None = None

    def load_committed_paths() -> frozenset[str]:
        nonlocal committed_paths
        if committed_paths is not None:
            return committed_paths
        result = _run_git(
            source,
            "ls-tree",
            "-r",
            "--name-only",
            "-z",
            commit,
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise IntegrationObservationError(
                f"could not inspect committed paths at {commit}"
                + (f": {detail[:500]}" if detail else "")
            )
        try:
            values = result.stdout.decode("utf-8").split("\x00")
        except UnicodeDecodeError as exc:
            raise IntegrationObservationError(
                "committed path observation was not UTF-8"
            ) from exc
        committed_paths = frozenset(
            value.replace("\\", "/").casefold() for value in values if value
        )
        return committed_paths

    def probe(path: str) -> bool:
        normalized = str(path).replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized.casefold() in load_committed_paths()

    return probe


def _git_text(root: Path, *args: str) -> str:
    result = _run_git(root, *args)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise IntegrationObservationError(
            f"Git observation failed ({result.returncode}) for {root}"
            + (f": {detail[:500]}" if detail else "")
        )
    try:
        return result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise IntegrationObservationError("Git text output was not UTF-8") from exc


def refresh_source_main(source: Path | str) -> dict[str, Any]:
    """Fast-forward a clean attached controller main to exact origin/main.

    Task workers use durable standalone checkouts, so refreshing the controller
    never changes a worker repository beneath it. Divergence and dirt stop
    closed: this operation never rebases, resets, or overwrites local state.
    """

    root = Path(source).resolve()
    branch = _git_text(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch != "main":
        raise IntegrationObservationError(
            f"scheduler controller must use attached main, found {branch!r}"
        )
    status = _git_text(
        root, "status", "--porcelain=v1", "--untracked-files=all"
    )
    if status:
        raise IntegrationObservationError(
            "scheduler controller main is not completely clean"
        )
    before = _git_text(root, "rev-parse", "--verify", "HEAD")
    fetched = _run_git(root, "fetch", "origin", "main")
    if fetched.returncode != 0:
        detail = fetched.stderr.decode("utf-8", errors="replace").strip()
        raise IntegrationObservationError(
            "could not refresh scheduler origin/main"
            + (f": {detail[:500]}" if detail else "")
        )
    remote = _git_text(root, "rev-parse", "--verify", "origin/main")
    ancestry = _run_git(root, "merge-base", "--is-ancestor", before, remote)
    if ancestry.returncode != 0:
        reverse_ancestry = _run_git(
            root, "merge-base", "--is-ancestor", remote, before
        )
        if reverse_ancestry.returncode == 0:
            verified_status = _git_text(
                root, "status", "--porcelain=v1", "--untracked-files=all"
            )
            if verified_status:
                raise IntegrationObservationError(
                    "scheduler controller became dirty while observing local-ahead main"
                )
            return {
                "before": before,
                "after": before,
                "changed": False,
                "local_ahead": True,
                "remote_head": remote,
            }
        raise IntegrationObservationError(
            "scheduler controller main diverged from origin/main; refusing rewrite"
        )
    if before != remote:
        merged = _run_git(root, "merge", "--ff-only", "origin/main")
        if merged.returncode != 0:
            detail = merged.stderr.decode("utf-8", errors="replace").strip()
            raise IntegrationObservationError(
                "scheduler controller main could not fast-forward"
                + (f": {detail[:500]}" if detail else "")
            )
    after = _git_text(root, "rev-parse", "--verify", "HEAD")
    verified_status = _git_text(
        root, "status", "--porcelain=v1", "--untracked-files=all"
    )
    if after != remote or verified_status:
        raise IntegrationObservationError(
            "scheduler controller refresh did not verify exact clean origin/main"
        )
    return {"before": before, "after": after, "changed": before != after}


def authorized_local_ahead_recovery_task(
    refresh: Mapping[str, Any],
    reservations: Iterable[IntegrationReservation],
) -> str | None:
    """Identify the sole D1C resume allowed to run from local-ahead main."""

    if refresh.get("local_ahead") is not True:
        return None
    local_commit = str(refresh.get("after") or "")
    before = str(refresh.get("before") or "")
    remote_head = str(refresh.get("remote_head") or "")
    if (
        re.fullmatch(r"[0-9a-f]{40}", local_commit) is None
        or before != local_commit
        or refresh.get("changed") is not False
        or re.fullmatch(r"[0-9a-f]{40}", remote_head) is None
    ):
        raise IntegrationObservationError(
            "scheduler source refresher returned malformed local-ahead evidence"
        )
    matches = [
        item
        for item in reservations
        if item.phase == WorkflowPhase.DECOMPOSITION_APPLY.value
        and item.authorized_decomposition_apply_commit == local_commit
    ]
    if len(matches) != 1:
        raise IntegrationObservationError(
            "scheduler controller main is ahead of origin/main without one exact "
            "authorized decomposition-apply recovery"
        )
    return matches[0].task_id


_authorized_local_ahead_recovery_task = authorized_local_ahead_recovery_task


def _decode_z_paths(raw: bytes) -> tuple[str, ...]:
    try:
        values = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    except UnicodeDecodeError as exc:
        raise IntegrationObservationError("Git path output was not UTF-8") from exc
    return _path_tuple(values)


def is_git_checkout(path: Path | str) -> bool:
    root = Path(path)
    if not root.is_dir():
        return False
    result = _run_git(root, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return False
    try:
        top = Path(result.stdout.decode("utf-8").strip()).resolve()
        return top == root.resolve()
    except (UnicodeDecodeError, OSError):
        return False


def read_working_tree_changed_paths(checkout: Path | str) -> tuple[str, ...]:
    """Read tracked, staged, and untracked names without reading file contents."""

    root = Path(checkout)
    commands = (
        ("diff", "--name-only", "-z", "--"),
        ("diff", "--cached", "--name-only", "-z", "--"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    )
    paths: list[str] = []
    for command in commands:
        result = _run_git(root, *command)
        if result.returncode != 0:
            raise IntegrationObservationError(
                f"could not observe working-tree paths in {root}"
            )
        paths.extend(_decode_z_paths(result.stdout))
    return _path_tuple(paths)


def read_branch_changed_paths(
    checkout: Path | str,
    *,
    head: str | None = None,
) -> tuple[str, ...]:
    """Read committed branch paths from the current origin/main merge base."""

    root = Path(checkout)
    base: str | None = None
    for candidate in ("refs/remotes/origin/main", "refs/heads/main"):
        result = _run_git(root, "rev-parse", "--verify", f"{candidate}^{{commit}}")
        if result.returncode == 0:
            base = result.stdout.decode("utf-8").strip()
            break
    if base is None:
        raise IntegrationObservationError(f"{root} has no observable origin/main or main")
    target = str(head).strip() if head else "HEAD"
    target_result = _run_git(root, "rev-parse", "--verify", f"{target}^{{commit}}")
    if target_result.returncode != 0:
        raise IntegrationObservationError(f"{root} does not contain branch head {target!r}")
    target_commit = target_result.stdout.decode("utf-8").strip()
    merge_base = _git_text(root, "merge-base", base, target_commit)
    result = _run_git(
        root,
        "diff",
        "--name-only",
        "-z",
        merge_base,
        target_commit,
        "--",
    )
    if result.returncode != 0:
        raise IntegrationObservationError(f"could not diff {target_commit} from main")
    return _decode_z_paths(result.stdout)


def observe_durable_workflows(
    *,
    source: Path | str,
    checkout_root: Path | str,
    worker_id: str,
    backend: IssueBackend | None = None,
    task_loader: Callable[[str], Mapping[str, Any]] | None = None,
    consistency_retry_budget: IssueConsistencyRetryBudget | None = None,
) -> DurableWorkflowObservation:
    """Observe valid managed workflows and derive reservations from one batch.

    ``IssueWorkflowService`` currently exposes no public all-incomplete
    enumeration. The observer therefore reuses the store's bounded consistency
    scan rather than reimplementing the Issue body/event parser. When supplied,
    one retry budget is shared with Stage 2 for the whole admission attempt.
    No backend mutation method is called.
    """

    source_root = Path(source).resolve()
    checkout_parent = Path(checkout_root)
    selected_backend = backend or GhIssueBackend(source_root=source_root)
    load_task = task_loader or (
        lambda task_id: load_committed_task(source_root, task_id)
    )
    reservations: list[IntegrationReservation] = []
    snapshots: list[IssueWorkflowSnapshot] = []
    candidates: list[Mapping[str, Any]] = []
    for issue in selected_backend.list_issues():
        body = str(issue.get("body") or "")
        if STATE_RE.search(body) is None:
            continue
        if not issue_author_authorized(issue):
            continue
        issue_is_open = str(issue.get("state") or "").upper() != "CLOSED"
        if not issue_is_open:
            try:
                closed_state = parse_state(body)
            except WorkflowContractError:
                continue
            if closed_state is None or closed_state.state is not WorkflowState.COMPLETE:
                continue
        candidates.append(issue)
    scanned = _consistent_snapshots(
        selected_backend,
        candidates,
        deadline=(
            consistency_retry_budget.deadline()
            if consistency_retry_budget is not None
            else None
        ),
    )
    for entry in scanned:
        if entry.error is not None:
            raise IntegrationObservationError(
                f"managed Issue #{entry.issue_number} could not be inspected: "
                f"{entry.error}"
            )
        snapshot = entry.snapshot
        if snapshot is None:
            continue
        # A recognized in-flight transition is an expected, bounded GitHub
        # Action window, not an observation failure. It is read from the
        # explicit typed classification, never by parsing reason strings. The
        # task still reserves its resources below; it is simply never admitted.
        pending_transition = (
            snapshot.pending_transition.to_dict()
            if snapshot.pending_transition is not None
            else None
        )
        if not snapshot.managed or snapshot.state is None:
            raise IntegrationObservationError(
                f"managed Issue #{snapshot.issue_number} is invalid: "
                + "; ".join(snapshot.reasons)
            )
        if not snapshot.valid and pending_transition is None:
            raise IntegrationObservationError(
                f"managed Issue #{snapshot.issue_number} is invalid: "
                + "; ".join(snapshot.reasons)
            )
        snapshots.append(snapshot)
        state = snapshot.state
        if state.state is WorkflowState.COMPLETE:
            continue
        try:
            task = dict(load_task(state.task_id))
        except Exception as exc:
            raise IntegrationObservationError(
                f"could not load committed task {state.task_id}: {_bounded_error(exc)}"
            ) from exc
        authorized_apply_commit: str | None = None
        if task.get("task_contract_sha256") != state.task_contract_sha256:
            if state.phase is not WorkflowPhase.DECOMPOSITION_APPLY:
                raise IntegrationObservationError(
                    f"durable {state.task_id} task-contract hash differs from committed HEAD"
                )
            try:
                current_source_head = _git_text(
                    source_root, "rev-parse", "--verify", "HEAD"
                )
                replay = inspect_authorized_decomposition_replay(
                    source=source_root,
                    snapshot=snapshot,
                    expected_head=current_source_head,
                )
            except Exception as exc:
                raise IntegrationObservationError(
                    f"durable {state.task_id} decomposition_apply contract changed "
                    "without an exact authorized-plan replay proof: "
                    f"{_bounded_error(exc)}"
                ) from exc
            if replay.inspection.status != "already_applied":
                raise IntegrationObservationError(
                    f"durable {state.task_id} decomposition_apply contract changed "
                    "but the authorized plan is not exactly applied: "
                    f"{replay.inspection.status}: {replay.inspection.reason}"
                )
            try:
                authorized_apply_commit = find_exact_d1c_commit(
                    source_root,
                    task_id=state.task_id,
                    plan_id=replay.plan_id,
                    authorized_head=replay.authorized_source_head,
                    current_head=current_source_head,
                )
            except Exception as exc:
                raise IntegrationObservationError(
                    f"durable {state.task_id} decomposition_apply graph is present "
                    "but its exact canonical D1C commit is not provable: "
                    f"{_bounded_error(exc)}"
                ) from exc

        candidate_checkouts: list[Path] = []
        if state.checkout_path:
            candidate_checkouts.append(Path(state.checkout_path))
        fallback = checkout_parent / state.task_id
        if all(str(item) != str(fallback) for item in candidate_checkouts):
            candidate_checkouts.append(fallback)

        paths: list[str] = []
        observed_checkout: Path | None = None
        working_tree_observed = False
        branch_observed = False
        for checkout in candidate_checkouts:
            if not is_git_checkout(checkout):
                continue
            observed_checkout = checkout
            try:
                paths.extend(read_working_tree_changed_paths(checkout))
                working_tree_observed = True
            except IntegrationObservationError:
                pass
            try:
                paths.extend(
                    read_branch_changed_paths(checkout, head=state.head_commit)
                )
                branch_observed = True
            except IntegrationObservationError:
                pass
            break

        if not branch_observed and state.head_commit:
            try:
                paths.extend(
                    read_branch_changed_paths(source_root, head=state.head_commit)
                )
                branch_observed = True
            except IntegrationObservationError:
                pass

        actual = _path_tuple(paths)
        if observed_checkout is not None:
            surface_unknown = not (working_tree_observed and branch_observed)
        else:
            surface_unknown = not branch_observed
        if not surface_unknown:
            evidence_type = (
                "durable_branch_or_checkout_actual_paths"
                if actual
                else "durable_branch_or_checkout_observed_empty"
            )
        else:
            evidence_type = "durable_incomplete_surface_unknown"
        resources = task.get("exclusive_resources") or []
        if not isinstance(resources, list):
            raise IntegrationObservationError(
                f"committed {state.task_id} exclusive_resources is malformed"
            )
        reservations.append(
            IntegrationReservation(
                task_id=state.task_id,
                workflow_state=state.state.value,
                phase=state.phase.value,
                branch=state.branch,
                head=state.head_commit,
                checkout_path=str(observed_checkout or state.checkout_path or fallback),
                exclusive_resources=tuple(resources),
                predicted_paths=(),
                actual_paths=actual,
                unity_serialized_assets=_unity_paths(actual),
                shared_systems=(),
                confidence=1.0 if not surface_unknown else 0.0,
                evidence_type=evidence_type,
                surface_unknown=surface_unknown,
                local_active=False,
                pending_transition=pending_transition,
                authorized_decomposition_apply_commit=authorized_apply_commit,
            )
        )
    return DurableWorkflowObservation(
        snapshots=tuple(snapshots),
        reservations=tuple(reservations),
    )


def observe_durable_integration_reservations(
    *,
    source: Path | str,
    checkout_root: Path | str,
    worker_id: str,
    backend: IssueBackend | None = None,
    task_loader: Callable[[str], Mapping[str, Any]] | None = None,
    consistency_retry_budget: IssueConsistencyRetryBudget | None = None,
) -> tuple[IntegrationReservation, ...]:
    """Compatibility view over :func:`observe_durable_workflows`."""

    return observe_durable_workflows(
        source=source,
        checkout_root=checkout_root,
        worker_id=worker_id,
        backend=backend,
        task_loader=task_loader,
        consistency_retry_budget=consistency_retry_budget,
    ).reservations


class _FreshPoolWorkflow:
    """Expose Stage 2's fresh kernel after resume work was observed once."""

    def __init__(self, workflow: IssueWorkflowService) -> None:
        self.workflow = workflow

    def list_agent_ready(self) -> list[dict[str, Any]]:
        return []

    def find(self, task_id: str) -> Any:
        return self.workflow.find(task_id)

    def resource_conflicts(
        self, task: Mapping[str, Any]
    ) -> tuple[list[str], list[str]]:
        return self.workflow.resource_conflicts(task)


def build_poll_dispatch_plan(
    *,
    source: Path | str,
    worker_id: str,
    remote: str = "origin",
    excluded_task_ids: Iterable[str] | None = None,
    backend: IssueBackend | None = None,
    consistency_retry_budget: IssueConsistencyRetryBudget | None = None,
) -> DispatchPlan:
    """Build resume-first and ranked-fresh Stage 2 authority once per poll.

    The public ``DispatchPlan`` resume shape intentionally omits fresh ranks
    because ordinary Stage 2 callers stop at resume work. The scheduler needs
    both from one observation so a WAIT on that resume task cannot starve safe
    fresh work. V1 therefore composes the existing Stage 2 pure kernel with
    its plan-scoped read-only caches. It does not reimplement eligibility or
    ranking, and it performs one Issue snapshot and one TaskGraph state
    snapshot for the whole poll.
    """

    try:
        requested_exclusions = tuple(excluded_task_ids or ())
        excluded_resume_task_ids = frozenset(
            task_id for task_id in requested_exclusions if type(task_id) is str
        )
        policy = dispatch_plan_module.load_dispatch_policy()
        root = repo_root(Path(source).resolve())
        source_commit = dispatch_plan_module._git_head(root)
        task_ids = dispatch_plan_module.list_committed_task_ids(root)
        cached_backend = backend or dispatch_plan_module._PlanScopedIssueBackend(
            GhIssueBackend(source_root=root)
        )
        issue_workflow = IssueWorkflowService(
            backend=cached_backend,
            task_loader=lambda task_id: load_committed_task(root, task_id),
            worker_id=worker_id,
            consistency_retry_budget=consistency_retry_budget,
        )
        agent_ready = [
            snapshot
            for snapshot in issue_workflow.list_agent_ready()
            if (snapshot.get("workflow_state") or {}).get("task_id")
            not in excluded_resume_task_ids
        ]
        (
            claimed_refs,
            claim_namespace,
            claim_observation,
            provisional_reasons,
        ) = dispatch_plan_module._read_only_claim_observation(
            root=root,
            remote=remote,
            claim_policy=None,
        )
        state_provider = dispatch_plan_module._LazyTaskcontrolStateProvider(
            root=root,
            expected_task_ids=task_ids,
            source_commit=source_commit,
            recognized_states=policy.known_dependency_states,
        )
        try:
            fresh_plan = plan_dispatch(
                source_commit=source_commit,
                task_ids=task_ids,
                task_loader=lambda task_id: load_committed_task(root, task_id),
                state_provider=state_provider,
                issue_workflow=_FreshPoolWorkflow(issue_workflow),
                claimed_refs=claimed_refs,
                claim_namespace=claim_namespace,
                claim_observation=claim_observation,
                provisional_reasons=provisional_reasons,
                policy=policy,
                excluded_task_ids=requested_exclusions,
            )
            if task_ids:
                state_provider.ensure_snapshot()
            elif not agent_ready:
                return dispatch_plan_module._blocked_plan(
                    source_commit=source_commit,
                    reasons=(
                        "no committed Tasks/NSC-*.yaml contracts exist at HEAD and no "
                        "valid resume work exists",
                    ),
                )
        except TaskcontrolStateObservationError as exc:
            if not agent_ready:
                return dispatch_plan_module._blocked_plan(
                    source_commit=source_commit,
                    reasons=(
                        "authoritative TaskGraph state observation failed: "
                        f"{_bounded_error(exc)}",
                    ),
                )
            fresh_plan = DispatchPlan(
                schema_version=dispatch_plan_module.DISPATCH_PLAN_SCHEMA_VERSION,
                source_commit=source_commit,
                mode="read_only_poll_authority",
                autonomous_dispatch=False,
                decision="no_safe_work",
                resume=None,
                selected_fresh_candidate=None,
                ranked_eligible_candidates=(),
                skipped_candidates=(),
                agent_ready_count=0,
                claim_observation=claim_observation,
                reasons=(
                    *provisional_reasons,
                    f"{FRESH_POOL_UNAVAILABLE_REASON}: {_bounded_error(exc)}",
                ),
                excluded_task_ids=tuple(
                    sorted(
                        task_id
                        for task_id in (excluded_task_ids or ())
                        if type(task_id) is str
                    )
                ),
            )
        final_head = dispatch_plan_module._git_head(root)
        if final_head != source_commit:
            return dispatch_plan_module._blocked_plan(
                source_commit=source_commit,
                reasons=(
                    f"Git HEAD moved from {source_commit} to {final_head} during "
                    "poll-scoped Stage 2 planning",
                ),
            )
    except Exception as exc:
        return dispatch_plan_module._blocked_plan(
            source_commit=locals().get("source_commit", "unknown"),
            reasons=(
                "poll-scoped Stage 2 authority could not be built: "
                f"{type(exc).__name__}: {_bounded_error(exc)}",
            ),
        )

    if not agent_ready:
        return fresh_plan
    selected = agent_ready[0]
    state = selected.get("workflow_state") or {}
    selected_task_id = state.get("task_id")
    if selected_task_id in excluded_resume_task_ids:
        return dispatch_plan_module._blocked_plan(
            source_commit=source_commit,
            reasons=(
                f"operator-excluded resume task {selected_task_id!r} reached the "
                "final Stage-2 admission boundary",
            ),
        )
    additional_resumes = []
    ready_task_ids = {selected_task_id}
    for snapshot in agent_ready[1:]:
        ready_state = snapshot.get("workflow_state") or {}
        ready_task_id = ready_state.get("task_id")
        if ready_task_id in excluded_resume_task_ids:
            continue
        ready_task_ids.add(ready_task_id)
        additional_resumes.append(
            {
                "task_id": ready_task_id,
                "issue_number": snapshot.get("issue_number"),
                "issue_url": snapshot.get("issue_url"),
                "phase": ready_state.get("phase"),
                "resume_phase": ready_state.get("phase"),
                "branch": ready_state.get("branch"),
                "commit": ready_state.get("head_commit"),
                "human_result": ready_state.get("human_result"),
            }
        )
    fresh_candidates = tuple(
        candidate
        for candidate in fresh_plan.ranked_eligible_candidates
        if candidate.get("task_id") not in ready_task_ids
    )
    return DispatchPlan(
        schema_version=fresh_plan.schema_version,
        source_commit=source_commit,
        mode="read_only_poll_authority",
        autonomous_dispatch=False,
        decision="resume_existing",
        resume={
            "task_id": selected_task_id,
            "issue_number": selected.get("issue_number"),
            "issue_url": selected.get("issue_url"),
            "phase": state.get("phase"),
            "branch": state.get("branch"),
            "commit": state.get("head_commit"),
            "human_result": state.get("human_result"),
        },
        selected_fresh_candidate=fresh_plan.selected_fresh_candidate,
        ranked_eligible_candidates=tuple(additional_resumes) + fresh_candidates,
        skipped_candidates=fresh_plan.skipped_candidates,
        agent_ready_count=len(agent_ready),
        claim_observation=fresh_plan.claim_observation,
        reasons=fresh_plan.reasons,
        excluded_task_ids=fresh_plan.excluded_task_ids,
    )


class DockerArchitectRunner:
    """Run architect_preflight through the existing read-only review service."""

    def __init__(
        self,
        *,
        source: Path | str,
        artifact_root: Path | str,
        provider: str,
        model: str | None,
        max_turns: int,
        timeout_seconds: float = DEFAULT_ARCHITECT_TIMEOUT_SECONDS,
        compose_project: str = COMPOSE_PROJECT,
        command_runner: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
    ) -> None:
        self.source = Path(source).resolve()
        self.artifact_root = Path(artifact_root)
        self.provider = str(provider).strip().casefold()
        if self.provider not in {"claude", "codex"}:
            raise PollingOrchestratorError("architect provider must be claude or codex")
        self.model = (
            str(model).strip()
            if model
            else _default_architecture_review_model(self.provider)
        )
        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds
        self.compose_project = str(compose_project).strip()
        self.command_runner = command_runner or self._run
        self.session_compatibility = ArchitectSessionCompatibility(
            "claude-code" if self.provider == "claude" else "openai-codex",
            ARCHITECT_SESSION_ROLE,
            self.model,
            None if self.provider == "claude" else "max",
            ARCHITECT_SESSION_PROTOCOL,
            ARCHITECT_SESSION_CAPABILITIES,
        )

    @staticmethod
    def _run(
        command: Sequence[str],
        *,
        cwd: Path,
        input_bytes: bytes,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(
                tuple(command),
                cwd=str(cwd),
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ArchitectPreflightError(
                f"architect Docker invocation failed: {type(exc).__name__}: {exc}"
            ) from exc

    def command(self, *, scheduler_id: str) -> tuple[str, ...]:
        service = f"{self.provider}-review"
        command = [
            "docker",
            "compose",
            "-p",
            self.compose_project,
            "run",
            "--rm",
            "-T",
            service,
            "python3",
            "Pipeline/TaskReviewAgent/architect_preflight.py",
            "--source",
            CONTAINER_SOURCE,
            "--artifact-root",
            ARCHITECT_CONTAINER_ARTIFACT_ROOT,
            "--scheduler-id",
            scheduler_id,
            "--provider",
            self.provider,
            "--max-turns",
            str(self.max_turns),
            "--timeout-seconds",
            str(self.timeout_seconds),
        ]
        command.extend(("--model", self.model))
        return tuple(command)

    def __call__(
        self,
        *,
        task: Mapping[str, Any] | None = None,
        candidates: Sequence[Mapping[str, Any]] | None = None,
        source_head: str,
        reservations: Sequence[IntegrationReservation],
        scheduler_id: str,
        admission_limit: int | None = None,
        session_binding: ProviderSessionBinding | None = None,
    ) -> ArchitectAnalysis | ArchitectBatchAnalysis:
        if (task is None) == (candidates is None):
            raise ArchitectPreflightError(
                "architect runner requires exactly one task or candidate portfolio"
            )
        request = {
            "source_head": source_head,
            "reservations": [item.to_dict() for item in reservations],
        }
        if session_binding is not None:
            if type(session_binding) is not ProviderSessionBinding:
                raise ArchitectPreflightError(
                    "architect session binding must be an exact ProviderSessionBinding"
                )
            request["provider_session"] = session_binding.to_dict()
        if task is not None:
            request["task"] = dict(task)
        else:
            request["candidates"] = [dict(item) for item in candidates or ()]
            resolved_admission_limit = (
                len(candidates or ()) if admission_limit is None else admission_limit
            )
            if (
                type(resolved_admission_limit) is not int
                or resolved_admission_limit < 1
            ):
                raise ArchitectPreflightError(
                    "architect batch admission limit must be a positive integer"
                )
            request["admission_limit"] = resolved_admission_limit
        completed = self.command_runner(
            self.command(scheduler_id=scheduler_id),
            cwd=self.source,
            input_bytes=(
                json.dumps(
                    request,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8"),
            timeout_seconds=self.timeout_seconds + 120.0,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            try:
                failure = json.loads(detail)
            except json.JSONDecodeError:
                failure = None
            if (
                type(failure) is dict
                and set(failure)
                == {
                    "schema_version",
                    "status",
                    "error_type",
                    "error",
                    "failure_classification",
                    "lifecycle_outcome",
                    "confirmed_session_id",
                }
                and failure["schema_version"] == "1.0"
                and failure["status"] == "architect_session_invocation_failed"
                and failure["error_type"] == "ArchitectSessionInvocationError"
            ):
                raise ArchitectSessionInvocationError(
                    failure["lifecycle_outcome"],
                    failure["failure_classification"],
                    failure["confirmed_session_id"],
                    failure["error"],
                )
            raise ArchitectPreflightError(
                f"architect container exited {completed.returncode}"
                + (f": {detail[:900]}" if detail else "")
            )
        try:
            value = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArchitectPreflightError(
                "architect container did not return one JSON result"
            ) from exc
        confirmation = None
        if session_binding is not None:
            candidate_metadata = (
                value.get("invocation_metadata") if isinstance(value, dict) else None
            )
            try:
                confirmation = provider_session_confirmation_from_dict(
                    candidate_metadata.get("provider_session_confirmation")
                    if isinstance(candidate_metadata, Mapping)
                    else None
                )
            except ArchitectSessionOwnerError as exc:
                raise ArchitectSessionInvocationError(
                    "identity_failure",
                    "schema_error",
                    None,
                    str(exc),
                ) from exc
            if (
                confirmation.provider_identifier
                != session_binding.provider_identifier
                or confirmation.role != session_binding.role
                or confirmation.mode != session_binding.mode
                or confirmation.session_id != session_binding.session_id
            ):
                raise ArchitectSessionInvocationError(
                    "identity_failure",
                    "schema_error",
                    confirmation.session_id,
                    "architect container returned a mismatched session confirmation",
                )

        def output_failure(message: str) -> Exception:
            if confirmation is None:
                return ArchitectPreflightError(message)
            return ArchitectSessionInvocationError(
                "output_failure",
                "schema_error",
                confirmation.session_id,
                message,
            )

        result_key = "advisory" if task is not None else "batch"
        expected = {
            "schema_version",
            "analysis_id",
            result_key,
            "artifact_name",
            "active_surface_fingerprint",
            "invocation_metadata",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise output_failure("architect container result envelope is invalid")
        expected_version = (
            ARCHITECT_ADVISORY_SCHEMA_VERSION
            if task is not None
            else ARCHITECT_BATCH_SCHEMA_VERSION
        )
        if value.get("schema_version") != expected_version:
            raise output_failure("architect container schema version is invalid")
        try:
            advisory = (
                ArchitectAdvisory.from_dict(value["advisory"])
                if task is not None
                else None
            )
            batch = ArchitectBatch.from_dict(value["batch"]) if task is None else None
        except ArchitectPreflightError as exc:
            raise output_failure(str(exc)) from exc
        artifact_name = value["artifact_name"]
        if (
            type(artifact_name) is not str
            or Path(artifact_name).name != artifact_name
            or not artifact_name.endswith(".json")
        ):
            raise output_failure("architect artifact name is invalid")
        artifact_path = self.artifact_root / artifact_name
        if not artifact_path.is_file():
            raise output_failure(
                f"architect advisory artifact is not visible on the host: {artifact_path}"
            )
        metadata = value["invocation_metadata"]
        if not isinstance(metadata, Mapping):
            raise output_failure("architect invocation metadata is invalid")
        analysis_values = {
            "analysis_id": str(value["analysis_id"]),
            "artifact_path": artifact_path,
            "active_surface_fingerprint": str(value["active_surface_fingerprint"]),
            "invocation_metadata": dict(metadata),
        }
        if advisory is not None:
            return ArchitectAnalysis(advisory=advisory, **analysis_values)
        assert batch is not None
        return ArchitectBatchAnalysis(batch=batch, **analysis_values)


def build_worker_command(
    *,
    task_id: str,
    worker_id: str,
    source: Path | str,
    checkout_root: Path | str,
    execution_provider: str | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    route: ResolvedExecutionRoute | None = None,
    run_id: str | None = None,
    admission_source_head: str | None = None,
    task_contract_sha256: str | None = None,
    admission_issue_number: int | None = None,
) -> tuple[str, ...]:
    # The Game Task Agent controller owns Git/GitHub/claim/Issue/checkout
    # authority and therefore runs on the Windows host. Claude/Codex remain
    # subordinate provider sandboxes launched by that host controller. The
    # outer argv keeps exact --task-id / --worker-id bindings for acceptance.
    task_id = validate_task_id(task_id)
    if type(worker_id) is not str or not worker_id.strip():
        raise PollingOrchestratorError("worker_id must be a non-empty string")
    if route is not None:
        if route.rigor is None:
            raise PollingOrchestratorError(
                "scheduler execution route omitted deterministic rigor authority"
            )
        provider = route.execution_provider
        supervisor_model = route.supervisor_model
        supervisor_reasoning_effort = route.supervisor_reasoning_effort
        execution_model = route.execution_model
        execution_reasoning_effort = route.execution_reasoning_effort
        supervisor_turns = route.max_supervisor_turns
        crew_profile = route.rigor.crew_profile
        validation_profile = route.rigor.validation_profile
    else:
        provider = str(execution_provider).strip().casefold()
        supervisor_model = str(model).strip() if model else None
        supervisor_reasoning_effort = None
        execution_model = None
        execution_reasoning_effort = None
        supervisor_turns = max_turns
        crew_profile = None
        validation_profile = None
    if provider not in {"claude", "codex"}:
        raise PollingOrchestratorError("execution provider must be claude or codex")
    if (
        isinstance(supervisor_turns, bool)
        or not isinstance(supervisor_turns, int)
        or supervisor_turns < 1
    ):
        raise PollingOrchestratorError("max_turns must be a positive integer")

    host_source = Path(source).resolve()
    host_checkout_root = Path(checkout_root).resolve()
    launcher = host_source / "Pipeline" / "TaskReviewAgent" / "host_worker_launcher.py"
    host_output_root = host_checkout_root / ".task-review-agent" / "outputs"

    command = [
        sys.executable,
        "-u",
        str(launcher),
        "--task-id",
        task_id,
        "--mode",
        "openai",
        "--source",
        str(host_source),
        "--checkout-root",
        str(host_checkout_root),
        "--worker-id",
        worker_id,
        "--execution-provider",
        provider,
        "--max-turns",
        str(supervisor_turns),
        "--output-root",
        str(host_output_root),
    ]
    if supervisor_model:
        command.extend(("--model", supervisor_model))
    if supervisor_reasoning_effort:
        command.extend(
            ("--supervisor-reasoning-effort", supervisor_reasoning_effort)
        )
    if execution_model:
        command.extend(("--execution-model", execution_model))
    if execution_reasoning_effort:
        command.extend(
            ("--execution-reasoning-effort", execution_reasoning_effort)
        )
    if crew_profile is not None and validation_profile is not None:
        command.extend(("--crew-profile", crew_profile))
        command.extend(("--validation-profile", validation_profile))
    if route is not None and provider == "claude" and execution_model:
        command.append("--enable-execution-session-pool")
    result_identity = (run_id, admission_source_head, task_contract_sha256)
    if any(value is not None for value in result_identity):
        if not all(isinstance(value, str) and value for value in result_identity):
            raise PollingOrchestratorError(
                "worker result identity requires run id, source HEAD, and contract hash"
            )
        command.extend(
            (
                "--run-id",
                str(run_id),
                "--admission-source-head",
                str(admission_source_head),
                "--task-contract-sha256",
                str(task_contract_sha256),
            )
        )
        if admission_issue_number is not None:
            if type(admission_issue_number) is not int or admission_issue_number < 1:
                raise PollingOrchestratorError(
                    "worker admission Issue number must be a positive integer"
                )
            command.extend(
                ("--admission-issue-number", str(admission_issue_number))
            )
    elif admission_issue_number is not None:
        raise PollingOrchestratorError(
            "worker admission Issue number requires result identity"
        )
    return tuple(command)


def build_decomposition_worker_command(
    *,
    task_id: str,
    worker_id: str,
    source: Path | str,
    checkout_root: Path | str,
    output_root: Path | str | None = None,
    scheduler_output_root: Path | str | None = None,
    run_id: str | None = None,
    admission_source_head: str | None = None,
    task_contract_sha256: str | None = None,
    admission_issue_number: int | None = None,
) -> tuple[str, ...]:
    """Build the distinct host boundary for review-only decomposition work."""

    task_id = validate_task_id(task_id)
    root = Path(source).resolve()
    if output_root is None:
        profile = os.environ.get("USERPROFILE")
        if not profile:
            raise PollingOrchestratorError(
                "USERPROFILE is required for decomposition output policy"
            )
        selected_output = (
            Path(profile) / "Downloads" / "NoSafeCircleOutput" / task_id
        )
    else:
        selected_output = Path(output_root).resolve()
    command = [
        sys.executable,
        "-u",
        str(root / "Pipeline" / "TaskReviewAgent" / "host_decomposition_launcher.py"),
        "--task-id",
        task_id,
        "--source",
        str(root),
        "--checkout-root",
        str(Path(checkout_root).resolve()),
        "--worker-id",
        str(worker_id),
        "--output-root",
        str(selected_output),
    ]
    result_identity = (
        scheduler_output_root,
        run_id,
        admission_source_head,
        task_contract_sha256,
    )
    if any(value is not None for value in result_identity):
        if scheduler_output_root is None or not all(
            isinstance(value, str) and value
            for value in (run_id, admission_source_head, task_contract_sha256)
        ):
            raise PollingOrchestratorError(
                "decomposition result identity requires output root, run id, source "
                "HEAD, and contract hash"
            )
        command.extend(
            (
                "--scheduler-output-root",
                str(Path(scheduler_output_root).resolve()),
                "--run-id",
                str(run_id),
                "--admission-source-head",
                str(admission_source_head),
                "--task-contract-sha256",
                str(task_contract_sha256),
            )
        )
        if admission_issue_number is not None:
            if type(admission_issue_number) is not int or admission_issue_number < 1:
                raise PollingOrchestratorError(
                    "decomposition admission Issue number must be a positive integer"
                )
            command.extend(
                ("--admission-issue-number", str(admission_issue_number))
            )
    elif admission_issue_number is not None:
        raise PollingOrchestratorError(
            "decomposition admission Issue number requires result identity"
        )
    return tuple(command)


@dataclass(frozen=True)
class PollCycleResult:
    status: str
    task_id: str | None = None
    worker_id: str | None = None
    fatal: bool = False


@dataclass(frozen=True)
class ArchitectCooldownEntry:
    decision: ArchitectPolicyDecision
    not_before: float


class PlanBuilder(Protocol):
    def __call__(self, **values: Any) -> DispatchPlan: ...


class PollingOrchestrator:
    def __init__(
        self,
        *,
        source: Path | str,
        checkout_root: Path | str,
        scheduler_id: str,
        execution_provider: str | None,
        model: str | None,
        max_turns: int | None,
        max_workers: int,
        architect_min_confidence: float,
        architect_runner: Callable[..., ArchitectAnalysis | ArchitectBatchAnalysis],
        routing_policy: ExecutionRoutingPolicy | None = None,
        routing_policy_loader: Callable[[], ExecutionRoutingPolicy] | None = None,
        max_architect_invocations_per_poll: int = (
            DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_POLL
        ),
        architect_min_reanalysis_seconds: float = (
            DEFAULT_ARCHITECT_MIN_REANALYSIS_SECONDS
        ),
        max_consecutive_observation_failures: int = (
            DEFAULT_MAX_CONSECUTIVE_OBSERVATION_FAILURES
        ),
        fatal_drain_seconds: float = DEFAULT_FATAL_DRAIN_SECONDS,
        decision_cache: ArchitectDecisionCache | None = None,
        plan_builder: PlanBuilder = build_poll_dispatch_plan,
        task_loader: Callable[[str], Mapping[str, Any]] | None = None,
        reservation_observer: Callable[[], Sequence[IntegrationReservation]] | None = None,
        source_refresher: Callable[[Path], Mapping[str, Any]] = refresh_source_main,
        process_factory: Callable[..., Any] = subprocess.Popen,
        event_emitter: JsonEventEmitter | None = None,
        excluded_task_ids: Sequence[str] = (),
        admission_allowlist: Sequence[str] | None = None,
        dry_run: bool = False,
        compose_project: str = COMPOSE_PROJECT,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.source = Path(source).resolve()
        self.checkout_root = Path(checkout_root)
        self.scheduler_id = str(scheduler_id).strip()
        self.execution_provider = (
            str(execution_provider).strip().casefold()
            if execution_provider is not None
            else None
        )
        self.model = str(model).strip() if model else None
        self.max_turns = max_turns
        self.max_workers = max_workers
        self.architect_min_confidence = architect_min_confidence
        self.architect_runner = architect_runner
        if routing_policy is not None and routing_policy_loader is not None:
            raise PollingOrchestratorError(
                "supply routing_policy or routing_policy_loader, not both"
            )
        self.routing_policy_loader = routing_policy_loader or (
            (lambda: routing_policy)
            if routing_policy is not None
            else lambda: load_execution_routing_policy(
                default_provider_override=self.execution_provider,
                supervisor_model_override=self.model,
                max_turns_override=self.max_turns,
            )
        )
        self.max_architect_invocations_per_poll = max_architect_invocations_per_poll
        self.architect_min_reanalysis_seconds = architect_min_reanalysis_seconds
        self.max_consecutive_observation_failures = (
            max_consecutive_observation_failures
        )
        self.fatal_drain_seconds = fatal_drain_seconds
        self.decision_cache = decision_cache or ArchitectDecisionCache()
        self.architect_invocations_this_poll = 0
        self.worker_launches_this_poll = 0
        self.worker_launches_total = 0
        self._worker_launch_task_ids_this_poll: list[str] | None = None
        self.architect_cooldowns: dict[str, ArchitectCooldownEntry] = {}
        self.consecutive_observation_failures = 0
        self.consecutive_source_refresh_failures = 0
        self.plan_builder = plan_builder
        self._uses_default_plan_builder = plan_builder is build_poll_dispatch_plan
        self.task_loader = task_loader or (
            lambda task_id: load_committed_task(self.source, task_id)
        )
        self._uses_default_reservation_observer = reservation_observer is None
        self.reservation_observer = reservation_observer or (
            lambda: observe_durable_integration_reservations(
                source=self.source,
                checkout_root=self.checkout_root,
                worker_id=self.scheduler_id,
            )
        )
        self.source_refresher = source_refresher
        self.process_factory = process_factory
        self.events = event_emitter or JsonEventEmitter()
        self.excluded_task_ids = frozenset(
            validate_task_id(task_id) for task_id in excluded_task_ids
        )
        self.admission_allowlist: frozenset[str] | None = None
        self.set_admission_allowlist(admission_allowlist)
        self.dry_run = bool(dry_run)
        self.compose_project = str(compose_project).strip()
        self.monotonic_clock = monotonic_clock
        self.worker_completion_event = threading.Event()
        self.architect_wake_listener: LocalArchitectWakeListener | None = None
        self._activity_listener_start_attempted = False
        self._activity_listener_closed = False
        self.architect_notification_revision = 0
        self.worker_slots = tuple(
            f"{self.scheduler_id}-slot-{index:02d}"
            for index in range(1, max_workers + 1)
        )
        self.active_assignments: dict[str, ActiveAssignment] = {}
        self.failed_child: tuple[str, int | None, int] | None = None
        if not self.scheduler_id:
            raise PollingOrchestratorError("scheduler_id must be non-empty")
        if self.execution_provider is not None and self.execution_provider not in {"claude", "codex"}:
            raise PollingOrchestratorError("execution provider must be claude or codex")
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise PollingOrchestratorError("max_workers must be a positive integer")
        if max_turns is not None and (
            isinstance(max_turns, bool)
            or not isinstance(max_turns, int)
            or max_turns < 1
        ):
            raise PollingOrchestratorError("max_turns must be a positive integer")
        if (
            isinstance(max_architect_invocations_per_poll, bool)
            or not isinstance(max_architect_invocations_per_poll, int)
            or max_architect_invocations_per_poll < 1
        ):
            raise PollingOrchestratorError(
                "max_architect_invocations_per_poll must be a positive integer"
            )
        if (
            isinstance(max_consecutive_observation_failures, bool)
            or not isinstance(max_consecutive_observation_failures, int)
            or max_consecutive_observation_failures < 1
        ):
            raise PollingOrchestratorError(
                "max_consecutive_observation_failures must be a positive integer"
            )
        if (
            isinstance(fatal_drain_seconds, bool)
            or not isinstance(fatal_drain_seconds, (int, float))
            or not math.isfinite(fatal_drain_seconds)
            or fatal_drain_seconds < 0
        ):
            raise PollingOrchestratorError(
                "fatal_drain_seconds must be a non-negative finite number"
            )
        if (
            isinstance(architect_min_reanalysis_seconds, bool)
            or not isinstance(architect_min_reanalysis_seconds, (int, float))
            or not math.isfinite(architect_min_reanalysis_seconds)
            or architect_min_reanalysis_seconds < 0
        ):
            raise PollingOrchestratorError(
                "architect_min_reanalysis_seconds must be a non-negative finite number"
            )
        if not callable(monotonic_clock):
            raise PollingOrchestratorError("monotonic_clock must be callable")
        if not callable(source_refresher):
            raise PollingOrchestratorError("source_refresher must be callable")
        if (
            isinstance(architect_min_confidence, bool)
            or not isinstance(architect_min_confidence, (int, float))
            or not math.isfinite(architect_min_confidence)
            or not 0 <= architect_min_confidence <= 1
        ):
            raise PollingOrchestratorError(
                "architect_min_confidence must be in [0, 1]"
            )

    def _watch_worker_return(self, assignment: ActiveAssignment) -> None:
        """Wake the architect when a real child returns its terminal status.

        The watcher owns no mutation and never terminates a worker. Test doubles
        that expose only ``poll`` deliberately keep the legacy timer seam.
        """

        wait = getattr(assignment.process, "wait", None)
        if not callable(wait):
            return

        def observe_return() -> None:
            try:
                wait()
            finally:
                self.worker_completion_event.set()

        threading.Thread(
            target=observe_return,
            name=f"architect-worker-return-{assignment.task_id.casefold()}",
            daemon=True,
        ).start()

    def _wait_for_architect_activity(self, poll_seconds: float) -> str:
        """Wait for a worker return, using the poll interval only as fallback."""

        if any(
            assignment.process.poll() is not None
            for assignment in self.active_assignments.values()
        ):
            return "worker_returned"
        self.worker_completion_event.clear()
        # Close the clear/check race: a worker may return immediately before its
        # watcher publishes the event.
        if any(
            assignment.process.poll() is not None
            for assignment in self.active_assignments.values()
        ):
            return "worker_returned"
        notification: dict[str, Any] | None = None
        if self.architect_wake_listener is not None:
            revision, notification = (
                self.architect_wake_listener.notification_snapshot()
            )
            if revision > self.architect_notification_revision:
                self.architect_notification_revision = revision
                self.events.emit(
                    "issue_state_change_notified_to_architect",
                    notification=notification,
                )
                return "issue_state_changed"
        watchable = bool(self.active_assignments) and all(
            callable(getattr(assignment.process, "wait", None))
            for assignment in self.active_assignments.values()
        )
        event_waitable = watchable or self.architect_wake_listener is not None
        self.events.emit(
            "architect_wait_started",
            wait_mode=("event_or_fallback" if event_waitable else "fallback_timer"),
            fallback_seconds=poll_seconds,
            active_worker_count=len(self.active_assignments),
        )
        if event_waitable:
            if self.worker_completion_event.wait(timeout=poll_seconds):
                if any(
                    assignment.process.poll() is not None
                    for assignment in self.active_assignments.values()
                ):
                    self.events.emit(
                        "worker_returned_to_architect",
                        active_worker_count=len(self.active_assignments),
                    )
                    return "worker_returned"
                if self.architect_wake_listener is not None:
                    revision, notification = (
                        self.architect_wake_listener.notification_snapshot()
                    )
                    self.architect_notification_revision = max(
                        self.architect_notification_revision,
                        revision,
                    )
                self.events.emit(
                    "issue_state_change_notified_to_architect",
                    notification=notification,
                )
                return "issue_state_changed"
        else:
            time.sleep(poll_seconds)
        return "fallback_elapsed"

    def _checkout_worker_slot(self) -> str:
        active_worker_ids = {
            assignment.worker_id for assignment in self.active_assignments.values()
        }
        for worker_id in self.worker_slots:
            if worker_id not in active_worker_ids:
                return worker_id
        raise PollingOrchestratorError(
            "worker pool has no idle slot despite available scheduler capacity"
        )

    def _collect_returned_workers(self) -> tuple[bool, frozenset[str]]:
        failed = False
        returned_task_ids: set[str] = set()
        for task_id, assignment in list(self.active_assignments.items()):
            try:
                returncode = assignment.process.poll()
            except Exception as exc:
                assignment.observation_error = _bounded_error(exc)
                failed = True
                self.events.emit(
                    "worker_poll_failed",
                    task_id=task_id,
                    worker_id=assignment.worker_id,
                    pid=assignment.pid,
                    checkout_path=str(assignment.checkout_path),
                    reason=(
                        "worker liveness could not be observed; assignment remains "
                        "supervised and no new admission is allowed"
                    ),
                    error=assignment.observation_error,
                )
                continue
            if returncode is None:
                continue
            del self.active_assignments[task_id]
            returned_task_ids.add(task_id)
            try:
                if assignment.pid is None:
                    raise WorkerResultError(
                        "active assignment has no observable process identity"
                    )
                worker_result = validate_worker_result(
                    assignment.result_artifact_path,
                    expected_run_id=assignment.run_id,
                    expected_worker_id=assignment.worker_id,
                    expected_task_id=assignment.task_id,
                    expected_source_head=assignment.source_head,
                    expected_task_contract_sha256=(
                        assignment.task_contract_sha256
                    ),
                    expected_pid=assignment.pid,
                    observed_exit_code=int(returncode),
                    started_at_utc=assignment.start_time_utc,
                    observed_at_utc=utc_now(),
                    expected_issue_number=assignment.issue_number,
                )
            except (OSError, ValueError, WorkerResultError) as exc:
                failed = True
                self.failed_child = (task_id, assignment.pid, int(returncode))
                self.events.emit(
                    "worker_failed",
                    task_id=task_id,
                    worker_id=assignment.worker_id,
                    pid=assignment.pid,
                    checkout_path=str(assignment.checkout_path),
                    returncode=returncode,
                    reason="worker terminal artifact was missing or invalid",
                    error=_bounded_error(exc),
                )
                continue
            terminal_status = worker_result["terminal_status"]
            if terminal_status in {
                "human_action_required",
                "completed",
                "blocked",
                "no_safe_work",
            }:
                self.events.emit(
                    "worker_returned_to_pool",
                    task_id=task_id,
                    worker_id=assignment.worker_id,
                    terminal_status=terminal_status,
                )
            if returncode == 0:
                self.events.emit(
                    "worker_finished",
                    task_id=task_id,
                    worker_id=assignment.worker_id,
                    pid=assignment.pid,
                    checkout_path=str(assignment.checkout_path),
                    returncode=0,
                    terminal_status=terminal_status,
                    run_id=assignment.run_id,
                )
                continue
            if terminal_status == "blocked":
                self.events.emit(
                    "worker_blocked",
                    task_id=task_id,
                    worker_id=assignment.worker_id,
                    pid=assignment.pid,
                    checkout_path=str(assignment.checkout_path),
                    returncode=returncode,
                    run_id=assignment.run_id,
                )
                continue
            if terminal_status == "no_safe_work":
                self.events.emit(
                    "worker_idle",
                    task_id=task_id,
                    worker_id=assignment.worker_id,
                    pid=assignment.pid,
                    checkout_path=str(assignment.checkout_path),
                    returncode=returncode,
                    run_id=assignment.run_id,
                )
                continue
            failed = True
            self.failed_child = (task_id, assignment.pid, int(returncode))
            self.events.emit(
                "worker_failed",
                task_id=task_id,
                worker_id=assignment.worker_id,
                pid=assignment.pid,
                checkout_path=str(assignment.checkout_path),
                returncode=returncode,
            )
        return failed, frozenset(returned_task_ids)

    def drain_active_workers(self, *, poll_seconds: float) -> bool:
        """Supervise existing children for a bounded interval after fatal stop."""

        deadline = self.monotonic_clock() + self.fatal_drain_seconds
        self.events.emit(
            "scheduler_draining",
            reason=(
                "new admissions stopped after a fatal cycle; existing children "
                "remain supervised for a bounded interval"
            ),
            fatal_drain_seconds=self.fatal_drain_seconds,
            active_children=self.active_child_summary(),
        )
        while self.active_assignments:
            self._collect_returned_workers()
            if not self.active_assignments:
                return True
            remaining = deadline - self.monotonic_clock()
            if remaining <= 0:
                self.events.emit(
                    "scheduler_drain_timeout",
                    reason=(
                        "fatal drain deadline expired; scheduler did not terminate "
                        "or release any remaining worker"
                    ),
                    active_children=self.active_child_summary(),
                )
                return False
            self.events.emit(
                "scheduler_drain_wait",
                remaining_seconds=remaining,
                active_children=self.active_child_summary(),
            )
            time.sleep(min(poll_seconds, remaining))
        return True

    def set_admission_allowlist(self, task_ids: Sequence[str] | None) -> None:
        """Restrict architect visibility and launch authority to exact task IDs.

        ``None`` preserves the normal unscoped polling behavior. Autonomous
        controllers replace the exact allowlist before each capacity pass after
        observing their root tasks and authorized decomposition descendants.
        """

        if task_ids is None:
            self.admission_allowlist = None
            return
        if type(task_ids) not in {list, tuple, set, frozenset}:
            raise PollingOrchestratorError(
                "admission allowlist must be a built-in task-ID collection"
            )
        normalized = frozenset(validate_task_id(task_id) for task_id in task_ids)
        if not normalized:
            raise PollingOrchestratorError("admission allowlist must not be empty")
        self.admission_allowlist = normalized

    def _refresh_active_reservations(self) -> tuple[IntegrationReservation, ...]:
        reservations: list[IntegrationReservation] = []
        for assignment in self.active_assignments.values():
            assignment.observation_error = None
            if is_git_checkout(assignment.checkout_path):
                assignment.checkout_observed_once = True
                paths: list[str] = []
                try:
                    paths.extend(read_working_tree_changed_paths(assignment.checkout_path))
                except IntegrationObservationError as exc:
                    assignment.observation_error = _bounded_error(exc)
                try:
                    paths.extend(read_branch_changed_paths(assignment.checkout_path))
                except IntegrationObservationError as exc:
                    if assignment.observation_error is None:
                        assignment.observation_error = _bounded_error(exc)
                observed_paths = _path_tuple(paths)
                assignment.actual_changed_paths = _path_tuple(
                    (*assignment.actual_changed_paths, *observed_paths)
                )
                if assignment.observation_error is not None:
                    self.events.emit(
                        "active_checkout_surface_unknown",
                        task_id=assignment.task_id,
                        checkout_path=str(assignment.checkout_path),
                        reason=assignment.observation_error,
                    )
            elif assignment.checkout_observed_once:
                assignment.observation_error = (
                    "previously observable active checkout is missing or unreadable"
                )
                self.events.emit(
                    "active_checkout_surface_unknown",
                    task_id=assignment.task_id,
                    checkout_path=str(assignment.checkout_path),
                    reason=assignment.observation_error,
                )
            else:
                self.events.emit(
                    "active_checkout_observation_pending",
                    task_id=assignment.task_id,
                    checkout_path=str(assignment.checkout_path),
                    reason=(
                        "new worker checkout has not appeared yet; launch-time architect "
                        "prediction remains the available integration evidence"
                    ),
                )
            reservations.append(assignment.to_reservation())
        return tuple(sorted(reservations, key=lambda item: item.task_id))

    def _integration_reservations(
        self,
        *,
        backend: IssueBackend | None = None,
        consistency_retry_budget: IssueConsistencyRetryBudget | None = None,
    ) -> tuple[IntegrationReservation, ...]:
        active = self._refresh_active_reservations()
        durable = (
            observe_durable_integration_reservations(
                source=self.source,
                checkout_root=self.checkout_root,
                worker_id=self.scheduler_id,
                backend=backend,
                consistency_retry_budget=consistency_retry_budget,
            )
            if backend is not None
            else tuple(self.reservation_observer())
        )
        reservations = tuple(
            sorted((*active, *durable), key=lambda item: (item.task_id, item.evidence_type))
        )
        self.events.emit(
            "integration_reservations_observed",
            reservation_count=len(reservations),
            reservations=[item.to_dict() for item in reservations],
        )
        return reservations

    @staticmethod
    def _ordered_candidates(
        plan: DispatchPlan,
    ) -> tuple[tuple[dict[str, Any], str | None], ...]:
        ordered: list[tuple[dict[str, Any], str | None]] = []
        if plan.decision == "resume_existing":
            resume = dict(plan.resume or {})
            ordered.append((resume, resume.get("phase")))
        if plan.decision in {"resume_existing", "fresh_candidate"}:
            ordered.extend(
                (dict(candidate), candidate.get("resume_phase"))
                for candidate in plan.ranked_eligible_candidates
            )
        return tuple(ordered)

    def _mixed_portfolio(
        self,
        plan: DispatchPlan,
        ordered: Sequence[tuple[dict[str, Any], str | None]],
    ) -> tuple[tuple[dict[str, Any], str | None, dict[str, Any]], ...]:
        """Bind Stage-2 implementation authority and safe decomposition options.

        A skipped Stage-2 entry may enter the decomposition pool only when all
        rejection reasons are intrinsic implementation-shape/dependency reasons.
        Issue ownership, claims, resources, malformed state, disposition, and
        delivery-state rejection therefore remain hard exclusions.
        """

        by_id: dict[str, tuple[dict[str, Any], str | None, dict[str, Any]]] = {}
        # The child-template policy is a property of the repository, not of any
        # one candidate, so it is proven once and its result is reused. Proving
        # it per candidate would both repeat the work and let a repository-wide
        # failure disappear into a per-candidate "not decomposition-relevant"
        # skip, which is a different fact and must not look like one.
        policy_document: Mapping[str, Any] | None = None
        policy_tasks: Mapping[str, Mapping[str, Any]] | None = None
        try:
            policy_document = read_policy_document(self.source)
            policy_tasks = read_committed_tasks(self.source)
            audit_decomposition_policy(
                self.source,
                document=policy_document,
                tasks=policy_tasks,
            )
        except ValidationPolicyAuditError as exc:
            self.events.emit(
                "decomposition_policy_unprovable",
                reason=str(exc),
                policy_path=(
                    "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
                ),
            )
            decomposition_offerable = False
        else:
            decomposition_offerable = True
        for candidate, resume_phase in ordered:
            task_id = validate_task_id(candidate.get("task_id"))
            task = self._load_candidate(plan, candidate, task_id)
            if resume_phase in {
                WorkflowPhase.DECOMPOSITION.value,
                WorkflowPhase.DECOMPOSITION_APPLY.value,
            }:
                work_types = ["decomposition"]
            else:
                work_types = ["implementation"]
            if resume_phase is None and decomposition_offerable:
                try:
                    validate_decomposition_task_selection(task_id, task)
                except DecompositionPreflightError:
                    # This contract is not decomposition-relevant. The
                    # repository-wide policy was already proven above, so this
                    # skip means only what it has always meant.
                    pass
                else:
                    work_types.append("decomposition")
            portfolio_entry = {
                "task": task,
                "eligible_work_types": sorted(work_types),
            }
            if resume_phase is not None:
                portfolio_entry["resume_phase"] = resume_phase
            by_id[task_id] = (
                dict(candidate),
                resume_phase,
                portfolio_entry,
            )

        for candidate in plan.skipped_candidates:
            task_id_raw = candidate.get("task_id")
            if type(task_id_raw) is not str or task_id_raw in by_id:
                continue
            if task_id_raw in plan.excluded_task_ids:
                continue
            reasons = tuple(candidate.get("reason_codes") or ())
            if not reasons or any(
                type(reason) is not str
                or (
                    reason not in _DECOMPOSITION_COMPATIBLE_STAGE2_REASONS
                    and not reason.startswith("dependency_blocked:")
                )
                for reason in reasons
            ):
                continue
            if not decomposition_offerable:
                continue
            task_id = validate_task_id(task_id_raw)
            task = self._load_candidate(plan, candidate, task_id)
            try:
                validate_decomposition_task_selection(task_id, task)
            except DecompositionPreflightError:
                continue
            by_id[task_id] = (
                dict(candidate),
                None,
                {"task": task, "eligible_work_types": ["decomposition"]},
            )

        return tuple(by_id[task_id] for task_id in sorted(by_id))

    def _load_candidate(
        self,
        plan: DispatchPlan,
        candidate: Mapping[str, Any],
        task_id: str,
    ) -> dict[str, Any]:
        task_id = validate_task_id(task_id)
        task = dict(self.task_loader(task_id))
        if task.get("id") != task_id:
            raise PollingOrchestratorError("committed task loader changed task identity")
        contract_hash = task.get("task_contract_sha256")
        if type(contract_hash) is not str:
            raise PollingOrchestratorError("committed task has no contract SHA-256")
        selected_hash = candidate.get("task_contract_sha256")
        if selected_hash is not None and selected_hash != contract_hash:
            raise PollingOrchestratorError(
                "Stage-2 candidate task-contract hash differs from committed HEAD"
            )
        head = _git_text(self.source, "rev-parse", "--verify", "HEAD")
        if head != plan.source_commit:
            raise PollingOrchestratorError(
                f"source HEAD moved from {plan.source_commit} to {head} after Stage 2"
            )
        return task

    @staticmethod
    def _cooldown_key(
        *, task_id: str, task_contract_sha256: str, source_head: str
    ) -> str:
        return f"{task_id}\n{task_contract_sha256}\n{source_head}"

    def _remember_nonstart(
        self,
        *,
        cache_key: str,
        cooldown_key: str,
        decision: ArchitectPolicyDecision,
    ) -> None:
        self.decision_cache.remember(cache_key, decision)
        self.architect_cooldowns[cooldown_key] = ArchitectCooldownEntry(
            decision=decision,
            not_before=(
                self.monotonic_clock() + self.architect_min_reanalysis_seconds
            ),
        )

    def _record_gate(
        self,
        *,
        task_id: str,
        cache_key: str,
        cooldown_key: str,
        decision: ArchitectPolicyDecision,
        analysis: ArchitectAnalysis | ArchitectBatchAnalysis | None = None,
        cached: bool = False,
    ) -> None:
        """Emit and remember one non-start admission decision.

        WAIT and HUMAN_REVIEW are temporary scheduling verdicts. Nothing durable
        changes, and the cached entry expires as soon as any of its bound inputs
        moves, so this can never become a permanent conflict blacklist.
        """

        if not cached:
            self._remember_nonstart(
                cache_key=cache_key,
                cooldown_key=cooldown_key,
                decision=decision,
            )
        self.events.emit(
            "architect_wait"
            if decision.decision == "wait"
            else "architect_human_review",
            task_id=task_id,
            analysis_id=analysis.analysis_id if analysis is not None else None,
            advisory_artifact_path=(
                str(analysis.artifact_path) if analysis is not None else None
            ),
            reasons=list(decision.reasons),
            cached=cached,
            scope=(
                "excluded for this scheduling pass only; no TaskGraph, Issue, claim, "
                "or lease state was mutated"
            ),
        )

    def _emit_conflict(self, task_id: str, conflict: Any) -> None:
        event = (
            "candidate_skipped_resource_conflict"
            if conflict.kind == "exclusive_resource"
            else "candidate_skipped_hard_conflict"
        )
        self.events.emit(
            event,
            task_id=task_id,
            conflicting_task_id=conflict.conflicting_task_id,
            conflict_kind=conflict.kind,
            overlapping_values=list(conflict.overlapping_values),
            reason=conflict.reason,
        )

    def poll_once(self, *, reset_architect_budget: bool = True) -> PollCycleResult:
        if reset_architect_budget:
            self.architect_invocations_this_poll = 0
        worker_failed, just_returned_task_ids = self._collect_returned_workers()
        if worker_failed:
            self.events.emit(
                "scheduler_blocked",
                reason="worker_failed; no further admissions are allowed",
            )
            return PollCycleResult("worker_failed", fatal=True)
        self.events.emit(
            "poll_started",
            active_worker_count=len(self.active_assignments),
            max_workers=self.max_workers,
            excluded_task_ids=sorted(self.excluded_task_ids),
            dry_run=self.dry_run,
        )
        refresh: dict[str, Any] = {}
        if not self.dry_run:
            try:
                refresh = dict(self.source_refresher(self.source))
            except (IntegrationObservationError, OSError) as exc:
                self.consecutive_source_refresh_failures += 1
                fatal = (
                    self.consecutive_source_refresh_failures
                    >= self.max_consecutive_observation_failures
                )
                self.events.emit(
                    "scheduler_blocked" if fatal else "scheduler_wait_source_refresh",
                    reason=(
                        "controller main refresh failed at the bounded consecutive-"
                        "failure limit"
                        if fatal
                        else "controller main refresh failed temporarily; no candidate "
                        "was planned or launched this poll"
                    ),
                    consecutive_observation_failures=(
                        self.consecutive_source_refresh_failures
                    ),
                    max_consecutive_observation_failures=(
                        self.max_consecutive_observation_failures
                    ),
                    error=_bounded_error(exc),
                )
                return PollCycleResult("source_refresh_failed", fatal=fatal)
            if self.consecutive_source_refresh_failures:
                self.events.emit(
                    "scheduler_source_refresh_recovered",
                    previous_consecutive_failures=(
                        self.consecutive_source_refresh_failures
                    ),
                )
            self.consecutive_source_refresh_failures = 0
            self.events.emit("source_main_refreshed", **refresh)
        if len(self.active_assignments) >= self.max_workers:
            self.events.emit(
                "scheduler_blocked",
                reason="local max_workers capacity is full",
                active_worker_count=len(self.active_assignments),
            )
            return PollCycleResult("capacity_full")
        shared_issue_backend: IssueBackend | None = None
        consistency_retry_budget: IssueConsistencyRetryBudget | None = None
        if (
            self._uses_default_plan_builder
            and self._uses_default_reservation_observer
        ):
            # Reservation and Stage-2 planning must observe one coherent GitHub
            # snapshot. The plan-scoped wrapper performs one paginated Issue read
            # and caches comments per Issue; a new wrapper is created after every
            # worker launch/capacity pass, so no mutation is hidden by stale data.
            shared_issue_backend = dispatch_plan_module._PlanScopedIssueBackend(
                GhIssueBackend(source_root=self.source)
            )
            consistency_retry_budget = IssueConsistencyRetryBudget()
        try:
            reservations = self._integration_reservations(
                backend=shared_issue_backend,
                consistency_retry_budget=consistency_retry_budget,
            )
        except (IntegrationObservationError, IssueWorkflowStoreError, OSError) as exc:
            self.consecutive_observation_failures += 1
            if (
                self.consecutive_observation_failures
                >= self.max_consecutive_observation_failures
            ):
                self.events.emit(
                    "scheduler_blocked",
                    reason=(
                        "integration reservation observation failed at the bounded "
                        "consecutive-failure limit"
                    ),
                    consecutive_observation_failures=(
                        self.consecutive_observation_failures
                    ),
                    max_consecutive_observation_failures=(
                        self.max_consecutive_observation_failures
                    ),
                    error=_bounded_error(exc),
                )
                return PollCycleResult(
                    "reservation_observation_failed", fatal=True
                )
            self.events.emit(
                "scheduler_wait_observation_failure",
                reason=(
                    "integration reservation observation failed temporarily; no "
                    "candidate was planned or launched this poll"
                ),
                consecutive_observation_failures=(
                    self.consecutive_observation_failures
                ),
                max_consecutive_observation_failures=(
                    self.max_consecutive_observation_failures
                ),
                fatal_drain_seconds=self.fatal_drain_seconds,
                error=_bounded_error(exc),
            )
            return PollCycleResult("reservation_observation_wait")

        if self.consecutive_observation_failures:
            self.events.emit(
                "scheduler_observation_recovered",
                previous_consecutive_failures=self.consecutive_observation_failures,
            )
        self.consecutive_observation_failures = 0

        pending_transitions = [
            {"task_id": item.task_id, **dict(item.pending_transition)}
            for item in reservations
            if item.pending_transition is not None
        ]
        if pending_transitions:
            # An expected, bounded GitHub Action window -- not an observation
            # failure. The counter is untouched, no blocker is written, and the
            # poll continues so unrelated candidates are still considered.
            self.events.emit(
                "issue_pending_transition",
                reason=(
                    "a managed Issue label is one legal state ahead of its body "
                    "while the state Action runs; the task keeps its exclusive "
                    "resources and is not admitted this poll"
                ),
                pending_transitions=pending_transitions,
                consecutive_observation_failures=(
                    self.consecutive_observation_failures
                ),
            )

        try:
            local_ahead_recovery_task_id = _authorized_local_ahead_recovery_task(
                refresh, reservations
            )
        except IntegrationObservationError as exc:
            self.events.emit(
                "scheduler_blocked",
                reason=(
                    "controller main is locally ahead without exact durable D1C "
                    "recovery authority"
                ),
                error=_bounded_error(exc),
            )
            return PollCycleResult("unproved_local_ahead", fatal=True)

        integration_fingerprint = active_surface_fingerprint(reservations)
        temporary_exclusions = set(self.active_assignments).union(
            self.excluded_task_ids,
            just_returned_task_ids,
            (item["task_id"] for item in pending_transitions),
        )
        if local_ahead_recovery_task_id is not None:
            try:
                committed_task_ids = dispatch_plan_module.list_committed_task_ids(
                    self.source
                )
            except (IssueWorkflowStoreError, OSError) as exc:
                self.events.emit(
                    "scheduler_blocked",
                    reason=(
                        "could not enumerate committed tasks while isolating exact "
                        "D1C local-ahead recovery"
                    ),
                    task_id=local_ahead_recovery_task_id,
                    error=_bounded_error(exc),
                )
                return PollCycleResult("local_ahead_inventory_failed", fatal=True)
            temporary_exclusions.update(
                task_id
                for task_id in committed_task_ids
                if task_id != local_ahead_recovery_task_id
            )
            self.events.emit(
                "source_main_local_ahead_recovery",
                task_id=local_ahead_recovery_task_id,
                local_commit=refresh["after"],
                remote_head=refresh["remote_head"],
                excluded_task_count=len(temporary_exclusions),
                reason=(
                    "only the exact approved decomposition-apply resume may retry "
                    "publishing this local D1C commit"
                ),
            )
        if shared_issue_backend is not None:
            plan = build_poll_dispatch_plan(
                source=self.source,
                worker_id=self.scheduler_id,
                excluded_task_ids=temporary_exclusions,
                backend=shared_issue_backend,
                consistency_retry_budget=consistency_retry_budget,
            )
        else:
            plan = self.plan_builder(
                source=self.source,
                worker_id=self.scheduler_id,
                excluded_task_ids=temporary_exclusions,
            )
        degraded_fresh_reasons = tuple(
            reason
            for reason in plan.reasons
            if reason.startswith(FRESH_POOL_UNAVAILABLE_REASON)
        )
        if degraded_fresh_reasons:
            self.events.emit(
                FRESH_POOL_UNAVAILABLE_REASON,
                reason=FRESH_POOL_UNAVAILABLE_REASON,
                details=list(degraded_fresh_reasons),
                resume_task_id=(plan.resume or {}).get("task_id"),
                fresh_candidate_count=0,
            )
        if plan.decision == "no_safe_work":
            self.events.emit(
                "plan_idle",
                decision=plan.decision,
                exclusions=sorted(temporary_exclusions),
            )
            return PollCycleResult("idle")
        if plan.decision == "blocked_invalid_state":
            self.events.emit(
                "scheduler_blocked",
                reason="Stage-2 planner reported blocked_invalid_state",
                plan_reasons=list(plan.reasons),
            )
            return PollCycleResult("blocked_invalid_state", fatal=True)
        if plan.decision not in {"fresh_candidate", "resume_existing"}:
            self.events.emit(
                "scheduler_blocked",
                reason=f"unsupported Stage-2 decision {plan.decision!r}",
            )
            return PollCycleResult("unsupported_plan", fatal=True)

        candidates = self._ordered_candidates(plan)
        if self.admission_allowlist is not None:
            outside_scope = tuple(
                sorted(
                    entry[0].get("task_id")
                    for entry in candidates
                    if entry[0].get("task_id") not in self.admission_allowlist
                )
            )
            candidates = tuple(
                entry
                for entry in candidates
                if entry[0].get("task_id") in self.admission_allowlist
            )
            if outside_scope:
                self.events.emit(
                    "candidate_skipped_outside_admission_scope",
                    task_ids=list(outside_scope),
                    admission_allowlist=sorted(self.admission_allowlist),
                    reason=(
                        "candidate is outside the controller-proven root and "
                        "authorized decomposition-descendant scope"
                    ),
                )
        if local_ahead_recovery_task_id is not None:
            candidates = tuple(
                entry
                for entry in candidates
                if entry[0].get("task_id") == local_ahead_recovery_task_id
            )
        if not candidates and self.admission_allowlist is not None:
            self.events.emit(
                "plan_idle",
                decision="no_candidate_inside_admission_scope",
                admission_allowlist=sorted(self.admission_allowlist),
                exclusions=sorted(temporary_exclusions),
            )
            return PollCycleResult("idle")
        if not candidates:
            self.events.emit(
                "scheduler_blocked",
                reason=(
                    "Stage-2 plan omitted the sole authorized local-ahead D1C recovery"
                    if local_ahead_recovery_task_id is not None
                    else "Stage-2 plan omitted its ordered candidate data"
                ),
            )
            return PollCycleResult("missing_candidate", fatal=True)

        try:
            mixed_portfolio = self._mixed_portfolio(plan, candidates)
        except (PollingOrchestratorError, CommittedTaskError, OSError) as exc:
            self.events.emit(
                "scheduler_blocked",
                reason="mixed architect portfolio could not be identity-verified",
                error=_bounded_error(exc),
            )
            return PollCycleResult("candidate_verification_failed", fatal=True)
        if self.admission_allowlist is not None:
            outside_mixed_scope = tuple(
                sorted(
                    entry[2]["task"]["id"]
                    for entry in mixed_portfolio
                    if entry[2]["task"]["id"] not in self.admission_allowlist
                )
            )
            mixed_portfolio = tuple(
                entry
                for entry in mixed_portfolio
                if entry[2]["task"]["id"] in self.admission_allowlist
            )
            if outside_mixed_scope:
                self.events.emit(
                    "candidate_skipped_outside_admission_scope",
                    task_ids=list(outside_mixed_scope),
                    admission_allowlist=sorted(self.admission_allowlist),
                    reason=(
                        "decomposition candidate is outside the controller-proven "
                        "root and authorized decomposition-descendant scope"
                    ),
                )
        if local_ahead_recovery_task_id is not None:
            mixed_portfolio = tuple(
                entry
                for entry in mixed_portfolio
                if entry[2]["task"]["id"] == local_ahead_recovery_task_id
            )
        if not mixed_portfolio:
            self.events.emit(
                "scheduler_blocked",
                reason="mixed architect portfolio contained no safe work type",
            )
            return PollCycleResult("missing_candidate", fatal=True)
        prefiltered_portfolio = []
        for entry in mixed_portfolio:
            task = entry[2]["task"]
            task_id = task["id"]
            empty_surface = effective_candidate_surface(
                candidate_task_id=task_id,
                predicted_surface=PredictedChangeSurface((), (), (), (), ()),
                reservations=reservations,
            )
            conflict = detect_deterministic_conflict(
                candidate_task_id=task_id,
                candidate_exclusive_resources=task.get("exclusive_resources") or (),
                candidate_surface=empty_surface,
                reservations=reservations,
            )
            if conflict is not None:
                self._emit_conflict(task_id, conflict)
                continue
            unknown = assess_unknown_surface_reservations(
                candidate_task_id=task_id,
                candidate_exclusive_resources=task.get("exclusive_resources") or (),
                reservations=reservations,
            )
            if unknown.blocks_without_architect:
                self.events.emit(
                    "candidate_wait_unknown_surface",
                    task_id=task_id,
                    blocking_task_ids=list(unknown.blocking_task_ids),
                    reasons=list(unknown.reasons),
                    scope="excluded before mixed-portfolio architect selection",
                )
                continue
            cache_key = architect_decision_cache_key(
                task_id=task_id,
                task_contract_sha256=str(task["task_contract_sha256"]),
                source_head=plan.source_commit,
                integration_fingerprint=integration_fingerprint,
            )
            cooldown_key = self._cooldown_key(
                task_id=task_id,
                task_contract_sha256=str(task["task_contract_sha256"]),
                source_head=plan.source_commit,
            )
            cached_decision = self.decision_cache.get(cache_key)
            if cached_decision is not None:
                self._record_gate(
                    task_id=task_id,
                    cache_key=cache_key,
                    cooldown_key=cooldown_key,
                    decision=cached_decision,
                    cached=True,
                )
                continue
            cooldown = self.architect_cooldowns.get(cooldown_key)
            now = self.monotonic_clock()
            if cooldown is not None and now < cooldown.not_before:
                self.events.emit(
                    "architect_wait",
                    task_id=task_id,
                    analysis_id=None,
                    advisory_artifact_path=None,
                    reasons=[
                        *cooldown.decision.reasons,
                        (
                            "minimum architect re-analysis interval remains active "
                            f"for {cooldown.not_before - now:.3f} seconds"
                        ),
                    ],
                    cached=False,
                    cooldown=True,
                    scope="excluded before mixed-portfolio architect selection",
                )
                continue
            prefiltered_portfolio.append(entry)
        mixed_portfolio = tuple(prefiltered_portfolio)
        if not mixed_portfolio:
            self.events.emit(
                "plan_idle",
                decision="all_mixed_portfolio_candidates_deterministically_waited",
            )
            return PollCycleResult("idle")
        resume_portfolio = tuple(
            entry for entry in mixed_portfolio if entry[1] is not None
        )
        if resume_portfolio:
            # A durable resume already passed through human or prior agent work, so
            # present it first without hiding fresh implementation or decomposition
            # work from the same bounded architect batch.
            resume_ids = {entry[2]["task"]["id"] for entry in resume_portfolio}
            mixed_portfolio = (
                *resume_portfolio,
                *(
                    entry
                    for entry in mixed_portfolio
                    if entry[2]["task"]["id"] not in resume_ids
                ),
            )
            self.events.emit(
                "resume_priority_applied",
                task_id=mixed_portfolio[0][2]["task"]["id"],
                resume_phase=mixed_portfolio[0][1],
                deferred_fresh_candidate_count=0,
                same_batch_fresh_candidate_count=len(mixed_portfolio) - len(resume_portfolio),
            )
        if self.dry_run:
            selected_id = mixed_portfolio[0][2]["task"]["id"]
            self.events.emit(
                "scheduler_blocked",
                task_id=selected_id,
                reason=(
                    "dry-run observed the mixed portfolio; architect model and worker "
                    "launch are disabled"
                ),
                portfolio_size=len(mixed_portfolio),
            )
            return PollCycleResult("dry_run_candidate", task_id=selected_id)
        if (
            self.architect_invocations_this_poll
            >= self.max_architect_invocations_per_poll
        ):
            self.events.emit(
                "scheduler_blocked",
                reason="per-poll architect invocation budget is exhausted",
            )
            return PollCycleResult("architect_budget_exhausted")
        portfolio_request = [item[2] for item in mixed_portfolio]
        admission_limit = min(
            self.max_workers - len(self.active_assignments),
            MAX_CANDIDATES_PER_POLL,
        )
        self.events.emit(
            "architect_started",
            source_head=plan.source_commit,
            portfolio_size=len(portfolio_request),
            eligible_pairs=[
                {
                    "task_id": item["task"]["id"],
                    "work_types": item["eligible_work_types"],
                }
                for item in portfolio_request
            ],
        )
        self.architect_invocations_this_poll += 1
        try:
            portfolio_analysis = self.architect_runner(
                candidates=portfolio_request,
                source_head=plan.source_commit,
                reservations=reservations,
                scheduler_id=self.scheduler_id,
                admission_limit=admission_limit,
            )
            if not isinstance(portfolio_analysis, ArchitectBatchAnalysis):
                raise ArchitectPreflightError(
                    "mixed-portfolio architect did not return a batch analysis"
                )
            entry_by_pair = {
                (item[2]["task"]["id"], work_type): item
                for item in mixed_portfolio
                for work_type in item[2]["eligible_work_types"]
            }
            ordered_admissions = []
            for advisory in portfolio_analysis.batch.admissions:
                selected_key = (
                    advisory.task_id,
                    advisory.work_type_recommendation,
                )
                selected_entry = entry_by_pair.get(selected_key)
                if selected_entry is None:
                    raise ArchitectPreflightError(
                        "architect selected a pair outside the revalidated mixed portfolio"
                    )
                ordered_admissions.append((*selected_entry, advisory))
        except Exception as exc:
            self.events.emit(
                "architect_wait",
                analysis_id=None,
                advisory_artifact_path=None,
                reasons=["mixed-portfolio architect invocation failed or was unusable"],
                error=_bounded_error(exc),
                cached=False,
            )
            return PollCycleResult("idle")
        candidates = tuple(ordered_admissions)

        analysis = portfolio_analysis
        admitted_task_ids = {
            advisory.task_id for advisory in analysis.batch.admissions
        }
        considerations_by_task: dict[str, list[Any]] = {}
        for item in analysis.batch.considered:
            considerations_by_task.setdefault(item.task_id, []).append(item)
        for task_id, task_considerations in considerations_by_task.items():
            if task_id in admitted_task_ids:
                continue
            matching_entry = next(
                (
                    entry
                    for entry in mixed_portfolio
                    if entry[2]["task"]["id"] == task_id
                ),
                None,
            )
            if matching_entry is None:
                continue
            task = matching_entry[2]["task"]
            cache_key = architect_decision_cache_key(
                task_id=task_id,
                task_contract_sha256=str(task["task_contract_sha256"]),
                source_head=plan.source_commit,
                integration_fingerprint=integration_fingerprint,
            )
            cooldown_key = self._cooldown_key(
                task_id=task_id,
                task_contract_sha256=str(task["task_contract_sha256"]),
                source_head=plan.source_commit,
            )
            human = next(
                (
                    item
                    for item in task_considerations
                    if item.disposition == "human_review"
                ),
                None,
            )
            chosen = human or task_considerations[0]
            decision = ArchitectPolicyDecision(
                "human_review" if human is not None else "wait",
                (chosen.rationale,),
            )
            self._record_gate(
                task_id=task_id,
                cache_key=cache_key,
                cooldown_key=cooldown_key,
                decision=decision,
                analysis=analysis,
            )
            temporary_exclusions.add(task_id)

        # Validate the complete ordered prefix before spawning anything. This is a
        # policy check, not schema recovery: malformed/incomplete batches have
        # already failed above and therefore launch zero workers.
        safe_candidates: list[tuple[Any, Any, Any, ArchitectAdvisory]] = []
        planned_reservations = list(reservations)
        for candidate, resume_phase, portfolio_entry, advisory in candidates:
            task_id = advisory.task_id
            task = portfolio_entry["task"]
            effective_surface = effective_candidate_surface(
                candidate_task_id=task_id,
                predicted_surface=advisory.predicted_change_surface,
                reservations=planned_reservations,
            )
            conflict = detect_deterministic_conflict(
                candidate_task_id=task_id,
                candidate_exclusive_resources=task.get("exclusive_resources") or (),
                candidate_surface=effective_surface,
                reservations=planned_reservations,
            )
            unknown_surface = assess_unknown_surface_reservations(
                candidate_task_id=task_id,
                candidate_exclusive_resources=task.get("exclusive_resources") or (),
                reservations=planned_reservations,
            )
            unconfirmed = unconfirmed_unknown_surface_task_ids(advisory, unknown_surface)
            gate = evaluate_architect_policy(
                advisory, min_confidence=self.architect_min_confidence
            )
            if (
                conflict is not None
                or unknown_surface.blocks_without_architect
                or unconfirmed
                or gate.decision != "start"
            ):
                reasons = []
                if conflict is not None:
                    reasons.append(conflict.reason)
                reasons.extend(unknown_surface.reasons if unknown_surface.blocks_without_architect else ())
                reasons.extend(
                    f"the architect did not establish that {task_id} is disjoint "
                    f"from the unobservable integration surface of {other_id}"
                    for other_id in unconfirmed
                )
                reasons.extend(gate.reasons if gate.decision != "start" else ())
                if conflict is not None:
                    self._emit_conflict(task_id, conflict)
                cache_key = architect_decision_cache_key(
                    task_id=task_id,
                    task_contract_sha256=str(task["task_contract_sha256"]),
                    source_head=plan.source_commit,
                    integration_fingerprint=integration_fingerprint,
                )
                cooldown_key = self._cooldown_key(
                    task_id=task_id,
                    task_contract_sha256=str(task["task_contract_sha256"]),
                    source_head=plan.source_commit,
                )
                self._record_gate(
                    task_id=task_id,
                    cache_key=cache_key,
                    cooldown_key=cooldown_key,
                    decision=ArchitectPolicyDecision(
                        "human_review" if gate.decision == "human_review" else "wait",
                        tuple(reasons) or ("ordered architect admission was not safe",),
                    ),
                    analysis=analysis,
                )
                temporary_exclusions.add(task_id)
                self.events.emit(
                    "architect_batch_candidate_withdrawn",
                    task_id=task_id,
                    reasons=reasons,
                    retained_task_ids=[item[3].task_id for item in safe_candidates],
                    reason=(
                        "this admission failed its deterministic gate; later ordered "
                        "admissions remain independently eligible"
                    ),
                )
                continue
            safe_candidates.append((candidate, resume_phase, portfolio_entry, advisory))
            planned_reservations.append(
                IntegrationReservation(
                    task_id=task_id,
                    workflow_state="architect_batch_planned",
                    phase=resume_phase,
                    branch=None,
                    head=plan.source_commit,
                    checkout_path=None,
                    exclusive_resources=_text_tuple(task.get("exclusive_resources") or ()),
                    predicted_paths=advisory.predicted_change_surface.exact_paths,
                    actual_paths=(),
                    unity_serialized_assets=(
                        advisory.predicted_change_surface.unity_serialized_assets
                    ),
                    shared_systems=advisory.predicted_change_surface.shared_systems,
                    confidence=advisory.confidence,
                    evidence_type="architect_batch_ordered_prediction",
                    surface_unknown=False,
                    local_active=True,
                )
            )

        last_launch: PollCycleResult | None = None
        admission_path_probe = committed_path_probe(self.source, plan.source_commit)
        considered: set[str] = set()
        for candidate, resume_phase, _portfolio_entry, advisory in safe_candidates:
            task_id = advisory.task_id
            if task_id in considered:
                self.events.emit(
                    "scheduler_blocked",
                    task_id=task_id,
                    reason="architect batch repeated a task after validation",
                )
                return PollCycleResult("duplicate_planned_candidate", task_id=task_id, fatal=True)
            considered.add(task_id)
            if len(self.active_assignments) >= self.max_workers:
                self.events.emit(
                    "architect_batch_capacity_truncated",
                    task_id=task_id,
                    launched_task_ids=sorted(considered - {task_id}),
                    reason="local capacity filled before launch",
                )
                break

            # Provider reasoning may take minutes. Refresh main, reservations, and
            # Stage 2 immediately before every launch, and throw away each Issue
            # cache after use because the newly spawned child can claim an Issue.
            try:
                refresh = dict(self.source_refresher(self.source))
                refreshed_head = str(refresh.get("after") or "")
                if refreshed_head != plan.source_commit:
                    raise PollingOrchestratorError(
                        f"source HEAD moved from {plan.source_commit} to {refreshed_head} "
                        "after architect batching"
                    )
                fresh_backend: IssueBackend | None = None
                fresh_budget: IssueConsistencyRetryBudget | None = None
                if self._uses_default_plan_builder and self._uses_default_reservation_observer:
                    fresh_backend = dispatch_plan_module._PlanScopedIssueBackend(
                        GhIssueBackend(source_root=self.source)
                    )
                    fresh_budget = IssueConsistencyRetryBudget()
                fresh_reservations = self._integration_reservations(
                    backend=fresh_backend,
                    consistency_retry_budget=fresh_budget,
                )
                refreshed_recovery_task_id = _authorized_local_ahead_recovery_task(
                    refresh, fresh_reservations
                )
                if (
                    local_ahead_recovery_task_id is not None
                    and refreshed_recovery_task_id
                    not in {None, local_ahead_recovery_task_id}
                ):
                    raise PollingOrchestratorError(
                        "local-ahead D1C recovery authority changed after architect batching"
                    )
                if refreshed_recovery_task_id is not None:
                    if refreshed_recovery_task_id != task_id:
                        raise PollingOrchestratorError(
                            "architect selected a task other than the sole authorized "
                            "local-ahead D1C recovery"
                        )
                    revalidation_exclusion_ids = (
                        dispatch_plan_module.list_committed_task_ids(self.source)
                    )
                    temporary_exclusions.update(
                        item
                        for item in revalidation_exclusion_ids
                        if item != refreshed_recovery_task_id
                    )
                revalidation_exclusions = set(self.active_assignments).union(
                    self.excluded_task_ids, temporary_exclusions
                )
                if fresh_backend is not None:
                    fresh_plan = build_poll_dispatch_plan(
                        source=self.source,
                        worker_id=self.scheduler_id,
                        excluded_task_ids=revalidation_exclusions,
                        backend=fresh_backend,
                        consistency_retry_budget=fresh_budget,
                    )
                else:
                    fresh_plan = self.plan_builder(
                        source=self.source,
                        worker_id=self.scheduler_id,
                        excluded_task_ids=revalidation_exclusions,
                    )
                if fresh_plan.source_commit != plan.source_commit:
                    raise PollingOrchestratorError(
                        "Stage 2 returned a different source HEAD during batch revalidation"
                    )
                if fresh_plan.decision == "blocked_invalid_state" or fresh_plan.decision not in {
                    "fresh_candidate",
                    "resume_existing",
                    "no_safe_work",
                }:
                    raise PollingOrchestratorError(
                        "Stage 2 returned an unusable decision during batch revalidation: "
                        f"{fresh_plan.decision}"
                    )
                fresh_entries = self._mixed_portfolio(
                    fresh_plan, self._ordered_candidates(fresh_plan)
                )
                if self.admission_allowlist is not None:
                    fresh_entries = tuple(
                        entry
                        for entry in fresh_entries
                        if entry[2]["task"]["id"] in self.admission_allowlist
                    )
                fresh_entry = next(
                    (
                        entry
                        for entry in fresh_entries
                        if entry[2]["task"]["id"] == task_id
                        and advisory.work_type_recommendation
                        in entry[2]["eligible_work_types"]
                    ),
                    None,
                )
            except Exception as exc:
                self.events.emit(
                    "architect_batch_discarded",
                    task_id=task_id,
                    launched_task_ids=sorted(considered - {task_id}),
                    reason="global source/reservation/Stage-2 revalidation failed",
                    error=_bounded_error(exc),
                )
                return last_launch or PollCycleResult("batch_revalidation_failed")
            if fresh_entry is None:
                self.events.emit(
                    "architect_batch_candidate_withdrawn",
                    task_id=task_id,
                    work_type=advisory.work_type_recommendation,
                    reason="candidate pair was no longer admissible in fresh Stage 2",
                )
                temporary_exclusions.add(task_id)
                continue
            candidate, resume_phase, portfolio_entry = fresh_entry
            task = portfolio_entry["task"]
            effective_surface = effective_candidate_surface(
                candidate_task_id=task_id,
                predicted_surface=advisory.predicted_change_surface,
                reservations=fresh_reservations,
            )
            conflict = detect_deterministic_conflict(
                candidate_task_id=task_id,
                candidate_exclusive_resources=task.get("exclusive_resources") or (),
                candidate_surface=effective_surface,
                reservations=fresh_reservations,
            )
            unknown_surface = assess_unknown_surface_reservations(
                candidate_task_id=task_id,
                candidate_exclusive_resources=task.get("exclusive_resources") or (),
                reservations=fresh_reservations,
            )
            unconfirmed = unconfirmed_unknown_surface_task_ids(advisory, unknown_surface)
            if conflict is not None or unknown_surface.blocks_without_architect or unconfirmed:
                if conflict is not None:
                    self._emit_conflict(task_id, conflict)
                self.events.emit(
                    "architect_batch_candidate_withdrawn",
                    task_id=task_id,
                    work_type=advisory.work_type_recommendation,
                    reason="fresh integration reservations no longer permit launch",
                    blocking_task_ids=list(
                        unknown_surface.blocking_task_ids or unconfirmed
                    ),
                )
                temporary_exclusions.add(task_id)
                continue

            self.events.emit(
                "architect_completed",
                task_id=task_id,
                analysis_id=analysis.analysis_id,
                advisory_artifact_path=str(analysis.artifact_path),
                integration_risk=advisory.integration_risk,
                parallel_recommendation=advisory.parallel_recommendation,
                work_type_recommendation=advisory.work_type_recommendation,
                confidence=advisory.confidence,
                execution_recommendation=advisory.execution_recommendation.to_dict(),
                design_advice=advisory.design_advice.to_dict(),
            )
            worker_id = self._checkout_worker_slot()
            worker_run_id = f"scheduler-{task_id.casefold()}-{uuid.uuid4().hex[:16]}"
            worker_output_root = (
                self.checkout_root / ".task-review-agent" / "outputs"
            )
            task_contract_sha256 = str(task.get("task_contract_sha256") or "")
            expected_issue_number = candidate.get("issue_number")
            if expected_issue_number is not None and (
                type(expected_issue_number) is not int or expected_issue_number < 1
            ):
                self.events.emit(
                    "worker_failed",
                    task_id=task_id,
                    worker_id=worker_id,
                    pid=None,
                    checkout_path=str(self.checkout_root / task_id),
                    returncode=None,
                    reason="scheduler admission Issue identity was malformed",
                )
                return PollCycleResult(
                    "worker_launch_failed", task_id=task_id, fatal=True
                )
            if not GIT_SHA_RE.fullmatch(plan.source_commit) or not re.fullmatch(
                r"[0-9a-f]{64}", task_contract_sha256
            ):
                self.events.emit(
                    "worker_failed",
                    task_id=task_id,
                    worker_id=worker_id,
                    pid=None,
                    checkout_path=str(self.checkout_root / task_id),
                    returncode=None,
                    reason="scheduler admission identity was malformed",
                )
                return PollCycleResult(
                    "worker_launch_failed", task_id=task_id, fatal=True
                )
            if advisory.work_type_recommendation == "decomposition":
                command = build_decomposition_worker_command(
                    task_id=task_id,
                    worker_id=worker_id,
                    source=self.source,
                    checkout_root=self.checkout_root,
                    scheduler_output_root=worker_output_root,
                    run_id=worker_run_id,
                    admission_source_head=plan.source_commit,
                    task_contract_sha256=task_contract_sha256,
                    admission_issue_number=expected_issue_number,
                )
                route_event = {
                    "work_type": "decomposition",
                    "execution_provider": "round_robin_codex_claude",
                    "capability_tier": "deep",
                    "route_reason": "architect_selected_eligible_decomposition",
                }
            else:
                try:
                    policy = self.routing_policy_loader()
                    if not isinstance(policy, ExecutionRoutingPolicy):
                        raise ExecutionRoutingError(
                            "routing policy loader returned an invalid policy"
                        )
                    rigor = resolve_task_rigor(
                        advisory.execution_recommendation,
                        task=task,
                        predicted_change_surface=effective_surface,
                        committed_path_probe=admission_path_probe,
                    )
                    route = resolve_execution_route(
                        advisory.execution_recommendation,
                        policy,
                        rigor=rigor,
                    )
                except (ExecutionRoutingError, TypeError, ValueError) as exc:
                    self.events.emit(
                        "execution_route_wait",
                        task_id=task_id,
                        reason=(
                            "deterministic execution routing policy was unusable; "
                            "no worker was launched"
                        ),
                        error=_bounded_error(exc),
                        capability_tier=(
                            advisory.execution_recommendation.capability_tier
                        ),
                        provider_preference=(
                            advisory.execution_recommendation.provider_preference
                        ),
                    )
                    temporary_exclusions.add(task_id)
                    continue
                command = build_worker_command(
                    task_id=task_id,
                    worker_id=worker_id,
                    source=self.source,
                    checkout_root=self.checkout_root,
                    route=route,
                    run_id=worker_run_id,
                    admission_source_head=plan.source_commit,
                    task_contract_sha256=task_contract_sha256,
                    admission_issue_number=expected_issue_number,
                )
                route_event = {"work_type": "implementation", **route.to_event_dict()}
            launch_started_utc = utc_now()
            try:
                process_kwargs: dict[str, Any] = {
                    "cwd": str(self.source),
                    "shell": False,
                }
                if os.name == "nt":
                    process_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    process_kwargs["start_new_session"] = True
                process = self.process_factory(command, **process_kwargs)
            except Exception as exc:
                self.events.emit(
                    "worker_failed",
                    task_id=task_id,
                    worker_id=worker_id,
                    pid=None,
                    checkout_path=str(self.checkout_root / task_id),
                    returncode=None,
                    reason="worker process launch failed; no scheduler lease was acquired",
                    error=_bounded_error(exc),
                )
                return PollCycleResult("worker_launch_failed", task_id=task_id, fatal=True)
            resources = task.get("exclusive_resources") or []
            assignment = ActiveAssignment(
                task_id=task_id,
                worker_id=worker_id,
                process=process,
                checkout_path=self.checkout_root / task_id,
                exclusive_resources=_text_tuple(resources),
                architect_surface=advisory.predicted_change_surface,
                architect_confidence=advisory.confidence,
                advisory_artifact_path=analysis.artifact_path,
                start_time_utc=launch_started_utc,
                run_id=worker_run_id,
                result_artifact_path=(
                    worker_output_root
                    / task_id
                    / worker_run_id
                    / "run_result.json"
                ),
                source_head=plan.source_commit,
                task_contract_sha256=task_contract_sha256,
                issue_number=expected_issue_number,
            )
            self.active_assignments[task_id] = assignment
            self.worker_launches_total += 1
            if self._worker_launch_task_ids_this_poll is not None:
                self._worker_launch_task_ids_this_poll.append(task_id)
            self._watch_worker_return(assignment)
            self.events.emit(
                "worker_launched",
                task_id=task_id,
                worker_id=worker_id,
                pid=assignment.pid,
                checkout_path=str(assignment.checkout_path),
                advisory_artifact_path=str(analysis.artifact_path),
                run_id=worker_run_id,
                result_artifact_path=str(assignment.result_artifact_path),
                argv=list(command),
                **route_event,
            )
            last_launch = PollCycleResult(
                "worker_launched", task_id=task_id, worker_id=worker_id
            )
            temporary_exclusions.add(task_id)

        if last_launch is not None:
            return last_launch
        self.events.emit(
            "plan_idle",
            decision="all_ordered_candidates_waited",
            considered_task_ids=sorted(considered),
            exclusions=sorted(temporary_exclusions),
            stage2_plan_count=1,
        )
        return PollCycleResult("idle")

    def poll_capacity_batch(self) -> PollCycleResult:
        """Fill available local capacity within one bounded scheduling poll.

        One architect call returns a bounded ordered admission batch. ``poll_once``
        refreshes source, Stage 2, and reservations before every launch in that
        batch, so capacity can be filled without repurchasing invariant context.
        """

        self.architect_invocations_this_poll = 0
        launches_before = self.worker_launches_total
        self.worker_launches_this_poll = 0
        self._worker_launch_task_ids_this_poll = []
        try:
            reported_cycle = self.poll_once(reset_architect_budget=False)
        finally:
            launched_task_ids = list(self._worker_launch_task_ids_this_poll)
            self._worker_launch_task_ids_this_poll = None
            self.worker_launches_this_poll = self.worker_launches_total - launches_before
        self.events.emit(
            "poll_capacity_batch_completed",
            launched_task_ids=launched_task_ids,
            launched_count=self.worker_launches_this_poll,
            active_worker_count=len(self.active_assignments),
            architect_invocations=self.architect_invocations_this_poll,
            result_status=reported_cycle.status,
            terminal_pass_status=reported_cycle.status,
            fatal=reported_cycle.fatal,
        )
        return reported_cycle

    def active_child_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "task_id": assignment.task_id,
                "worker_id": assignment.worker_id,
                "pid": assignment.pid,
                "checkout_path": str(assignment.checkout_path),
            }
            for assignment in sorted(
                self.active_assignments.values(), key=lambda item: item.task_id
            )
        ]

    def start_activity_listener(self) -> bool:
        """Start the Issue/worker wake listener once for an owning run loop.

        ``poll_once`` and ``poll_capacity_batch`` intentionally do not manage this
        lifecycle.  A caller that owns a multi-cycle loop starts it before the
        first possible wait and closes it in a ``finally`` boundary.
        """

        if (
            self._activity_listener_start_attempted
            and not self._activity_listener_closed
        ):
            return (
                self.architect_wake_listener is not None
            )
        if self._activity_listener_closed:
            self._activity_listener_start_attempted = False
            self._activity_listener_closed = False
        self._activity_listener_start_attempted = True
        try:
            listener = LocalArchitectWakeListener(
                self.source,
                scheduler_id=self.scheduler_id,
                wake_event=self.worker_completion_event,
            )
            listener.start()
            self.architect_wake_listener = listener
            return True
        except OSError as exc:
            self.architect_wake_listener = None
            self.events.emit(
                "architect_wake_listener_unavailable",
                reason=(
                    "local Issue-state notifications are unavailable; the bounded "
                    "fallback refresh remains active"
                ),
                error=_bounded_error(exc),
            )
            return False

    def close_activity_listener(self) -> None:
        """Close the owned activity listener at most once."""

        if self._activity_listener_closed:
            return
        self._activity_listener_closed = True
        listener = self.architect_wake_listener
        self.architect_wake_listener = None
        if listener is not None:
            listener.close()

    def reconcile_interrupted_architect_session(self, *, lock: SchedulerLock) -> bool:
        """Retire a prior process's uncertain architect call under scheduler lock.

        Production uses ``ArchitectSessionOwner``.  Tests and bounded adapters
        may inject a plain callable with no persistent lifecycle, in which case
        there is nothing to reconcile.
        """

        if type(lock) is not SchedulerLock or not lock.is_held:
            raise PollingOrchestratorError(
                "architect reconciliation requires the exact acquired scheduler lock"
            )
        reconcile = getattr(
            self.architect_runner,
            "reconcile_interrupted_assignment",
            None,
        )
        if reconcile is None:
            return False
        if not callable(reconcile):
            raise PollingOrchestratorError(
                "architect reconciliation boundary must be callable"
            )
        transition = reconcile()
        if transition is None:
            return False
        self.events.emit(
            "architect_session_reconciled",
            scheduler_id=self.scheduler_id,
            provider_identifier=transition.state.provider_identifier,
            role=transition.state.role,
            session_id=transition.state.session_id,
            assignment_id=transition.telemetry.assignment_id,
            retirement_reason=transition.state.retirement_reason,
        )
        return True

    def run(
        self,
        *,
        lock: SchedulerLock,
        poll_seconds: float,
        once: bool,
    ) -> int:
        try:
            lock.acquire()
        except SchedulerAlreadyActive as exc:
            self.events.emit(
                "scheduler_locked_out",
                status="scheduler_already_active",
                reason=str(exc),
                lock_path=str(lock.path),
            )
            return 2
        try:
            self.reconcile_interrupted_architect_session(lock=lock)
        except BaseException:
            lock.release()
            raise
        self.start_activity_listener()
        self.events.emit(
            "scheduler_started",
            scheduler_id=self.scheduler_id,
            source=str(self.source),
            checkout_root=str(self.checkout_root),
            max_workers=self.max_workers,
            poll_seconds=poll_seconds,
            dry_run=self.dry_run,
            event_journal_path=(
                str(self.events.journal_path)
                if self.events.journal_path is not None
                else None
            ),
            architect_max_invocations_per_poll=(
                self.max_architect_invocations_per_poll
            ),
            architect_min_reanalysis_seconds=(
                self.architect_min_reanalysis_seconds
            ),
            max_consecutive_observation_failures=(
                self.max_consecutive_observation_failures
            ),
            local_capacity_note=(
                "max_workers counts scheduler-owned live child processes only; durable "
                "external/manual workflows remain integration reservations"
            ),
        )
        exit_code = 0
        stop_reason = "once_complete" if once else "stopped"
        try:
            while True:
                cycle = self.poll_capacity_batch()
                if cycle.fatal:
                    exit_code = 2
                    stop_reason = cycle.status
                    if self.active_assignments:
                        drained = self.drain_active_workers(poll_seconds=poll_seconds)
                        if not drained:
                            stop_reason = f"{cycle.status}_drain_timeout"
                    break
                if once:
                    stop_reason = cycle.status
                    break
                self._wait_for_architect_activity(poll_seconds)
        except KeyboardInterrupt:
            if exit_code:
                stop_reason = f"{stop_reason}_drain_interrupted"
            else:
                stop_reason = "keyboard_interrupt"
                exit_code = 0
        finally:
            self.close_activity_listener()
            children = self.active_child_summary()
            self.events.emit(
                "scheduler_stopped",
                scheduler_id=self.scheduler_id,
                reason=stop_reason,
                active_children=children,
                child_policy=(
                    "the scheduler issued no termination request and released no "
                    "durable lease; operating-system child survival is not guaranteed, "
                    "and restart does not adopt prior worker processes"
                ),
            )
            lock.release()
        return exit_code


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive finite number")
    return parsed


def _non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a number") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError(
            "value must be a non-negative finite number"
        )
    return parsed


def _confidence(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("confidence must be a number") from exc
    if not math.isfinite(parsed) or not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("confidence must be in [0, 1]")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Observe Stage 2/reservations only; never invoke a model or launch a worker.",
    )
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--checkout-root", type=Path)
    parser.add_argument(
        "--poll-seconds", type=_positive_float, default=DEFAULT_POLL_SECONDS
    )
    parser.add_argument(
        "--max-workers", type=_positive_int, default=DEFAULT_MAX_WORKERS
    )
    parser.add_argument(
        "--exclude-task-id",
        action="append",
        default=[],
        metavar="NSC-NNN",
        help=(
            "Permanently exclude this exact task from every Stage-2 poll in this "
            "scheduler session; repeat for multiple tasks."
        ),
    )
    parser.add_argument(
        "--execution-provider",
        choices=("claude", "codex"),
        help=(
            "Optional deterministic default-provider override for every tier; "
            "architect preferences are still honored when policy-allowed."
        ),
    )
    parser.add_argument("--model")
    parser.add_argument(
        "--max-turns",
        type=_positive_int,
        help="Optional supervisor-turn override for every routing tier.",
    )
    parser.add_argument(
        "--architect-provider", choices=("claude", "codex"), default="claude"
    )
    parser.add_argument("--architect-model")
    parser.add_argument(
        "--architect-max-turns",
        type=_positive_int,
        default=DEFAULT_ARCHITECT_MAX_TURNS,
    )
    parser.add_argument(
        "--architect-min-confidence",
        type=_confidence,
        default=DEFAULT_ARCHITECT_MIN_CONFIDENCE,
    )
    parser.add_argument(
        "--architect-max-invocations-per-poll",
        type=_positive_int,
        default=DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_POLL,
        help=(
            "Bound the paid architect calls one poll may spend before the "
            "remaining candidates wait for the next poll."
        ),
    )
    parser.add_argument(
        "--architect-min-reanalysis-seconds",
        type=_non_negative_float,
        default=DEFAULT_ARCHITECT_MIN_REANALYSIS_SECONDS,
        help=(
            "Minimum interval before repurchasing a WAIT/HUMAN_REVIEW analysis "
            "for the same task, contract, and source HEAD."
        ),
    )
    parser.add_argument(
        "--max-consecutive-observation-failures",
        type=_positive_int,
        default=DEFAULT_MAX_CONSECUTIVE_OBSERVATION_FAILURES,
        help=(
            "Reservation-observation failures allowed to WAIT before the "
            "scheduler fails closed."
        ),
    )
    parser.add_argument(
        "--fatal-drain-seconds",
        type=_non_negative_float,
        default=DEFAULT_FATAL_DRAIN_SECONDS,
        help=(
            "Maximum time to supervise already-running children after a fatal cycle; "
            "the scheduler never terminates children or releases their leases."
        ),
    )
    return parser


def default_scheduler_id() -> str:
    return f"polling-orchestrator-{uuid.uuid4().hex[:16]}"


@dataclass(frozen=True)
class ProductionOrchestratorBinding:
    """One production scheduler, its singleton lock, and durable event sink."""

    source: Path
    checkout_root: Path
    operational_root: Path
    scheduler_id: str
    events: JsonEventEmitter
    orchestrator: PollingOrchestrator
    lock: SchedulerLock


def build_production_orchestrator(
    *,
    source: Path | str,
    checkout_root: Path | str | None = None,
    scheduler_id: str | None = None,
    execution_provider: str | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    architect_provider: str = "claude",
    architect_model: str | None = None,
    architect_max_turns: int = DEFAULT_ARCHITECT_MAX_TURNS,
    architect_min_confidence: float = DEFAULT_ARCHITECT_MIN_CONFIDENCE,
    max_architect_invocations_per_poll: int = (
        DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_POLL
    ),
    architect_min_reanalysis_seconds: float = (
        DEFAULT_ARCHITECT_MIN_REANALYSIS_SECONDS
    ),
    max_consecutive_observation_failures: int = (
        DEFAULT_MAX_CONSECUTIVE_OBSERVATION_FAILURES
    ),
    fatal_drain_seconds: float = DEFAULT_FATAL_DRAIN_SECONDS,
    excluded_task_ids: Sequence[str] = (),
    dry_run: bool = False,
    event_emitter_observer: Callable[[JsonEventEmitter], None] | None = None,
    event_journal_path: Path | str | None = None,
) -> ProductionOrchestratorBinding:
    """Build the canonical production scheduler composition without running it.

    Callers own the returned lock/listener lifecycle.  Keeping construction
    here ensures the polling CLI and autonomous graph runner use the same
    architect transport, persistent session owner, journal, worker-safety
    limits, and checkout-root singleton lock.

    ``event_emitter_observer`` lets a CLI retain the durable journal before
    later construction can fail, preserving initialization-failure reporting.
    """

    resolved_source = repo_root(Path(source).resolve())
    resolved_checkout_root = Path(checkout_root or default_checkout_root())
    resolved_scheduler_id = (
        default_scheduler_id()
        if scheduler_id is None
        else str(scheduler_id).strip()
    )
    if not resolved_scheduler_id:
        raise PollingOrchestratorError("scheduler_id must be non-empty")
    operational_root = (
        resolved_source
        / "Pipeline"
        / "ArchitectureReview"
        / "outputs"
        / "orchestrator"
    )
    artifact_root = operational_root / "architect"
    journal_path = (
        operational_root / "events" / f"{resolved_scheduler_id}.jsonl"
        if event_journal_path is None
        else Path(event_journal_path)
    )
    if not journal_path.is_absolute():
        raise PollingOrchestratorError("event_journal_path must be absolute")
    events = JsonEventEmitter(journal_path=journal_path)
    if event_emitter_observer is not None:
        if not callable(event_emitter_observer):
            raise PollingOrchestratorError(
                "event_emitter_observer must be callable"
            )
        event_emitter_observer(events)
    architect_transport = DockerArchitectRunner(
        source=resolved_source,
        artifact_root=artifact_root,
        provider=architect_provider,
        model=architect_model,
        max_turns=architect_max_turns,
    )
    architect_provider_identifier = (
        "claude-code"
        if architect_transport.provider == "claude"
        else "openai-codex"
    )
    architect_runner = ArchitectSessionOwner(
        architect_runner=architect_transport,
        provider_identifier=architect_provider_identifier,
        role=ARCHITECT_SESSION_ROLE,
        store=JsonArchitectSessionStore(
            operational_root
            / "architect-sessions"
            / architect_provider_identifier
            / ARCHITECT_SESSION_ROLE
        ),
        compatibility=architect_transport.session_compatibility,
    )
    orchestrator = PollingOrchestrator(
        source=resolved_source,
        checkout_root=resolved_checkout_root,
        scheduler_id=resolved_scheduler_id,
        execution_provider=execution_provider,
        model=model,
        max_turns=max_turns,
        max_workers=max_workers,
        architect_min_confidence=architect_min_confidence,
        architect_runner=architect_runner,
        max_architect_invocations_per_poll=max_architect_invocations_per_poll,
        architect_min_reanalysis_seconds=architect_min_reanalysis_seconds,
        max_consecutive_observation_failures=(
            max_consecutive_observation_failures
        ),
        fatal_drain_seconds=fatal_drain_seconds,
        event_emitter=events,
        excluded_task_ids=excluded_task_ids,
        dry_run=dry_run,
    )
    lock = SchedulerLock(
        scheduler_lock_path(
            checkout_root=resolved_checkout_root,
            source=resolved_source,
        )
    )
    return ProductionOrchestratorBinding(
        source=resolved_source,
        checkout_root=resolved_checkout_root,
        operational_root=operational_root,
        scheduler_id=resolved_scheduler_id,
        events=events,
        orchestrator=orchestrator,
        lock=lock,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    events = JsonEventEmitter()

    def observe_events(value: JsonEventEmitter) -> None:
        nonlocal events
        events = value

    try:
        production = build_production_orchestrator(
            source=args.source,
            checkout_root=args.checkout_root,
            execution_provider=args.execution_provider,
            model=args.model,
            max_turns=args.max_turns,
            max_workers=args.max_workers,
            architect_provider=args.architect_provider,
            architect_model=args.architect_model,
            architect_max_turns=args.architect_max_turns,
            architect_min_confidence=args.architect_min_confidence,
            max_architect_invocations_per_poll=args.architect_max_invocations_per_poll,
            architect_min_reanalysis_seconds=(
                args.architect_min_reanalysis_seconds
            ),
            max_consecutive_observation_failures=(
                args.max_consecutive_observation_failures
            ),
            fatal_drain_seconds=args.fatal_drain_seconds,
            excluded_task_ids=args.exclude_task_id,
            dry_run=args.dry_run,
            event_emitter_observer=observe_events,
        )
        events = production.events
        return production.orchestrator.run(
            lock=production.lock,
            poll_seconds=args.poll_seconds,
            once=args.once,
        )
    except (
        PollingOrchestratorError,
        ArchitectPreflightError,
        ArchitectSessionOwnerError,
        IssueWorkflowStoreError,
        TaskReviewContractError,
        ExecutionRoutingError,
        OSError,
        ValueError,
    ) as exc:
        events.emit(
            "scheduler_blocked",
            reason="scheduler initialization failed",
            error_type=type(exc).__name__,
            error=_bounded_error(exc),
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ActiveAssignment",
    "DockerArchitectRunner",
    "DurableWorkflowObservation",
    "FRESH_POOL_UNAVAILABLE_REASON",
    "IntegrationObservationError",
    "IntegrationReservation",
    "JsonEventEmitter",
    "PollCycleResult",
    "PollingOrchestrator",
    "PollingOrchestratorError",
    "ProductionOrchestratorBinding",
    "SchedulerAlreadyActive",
    "SchedulerLock",
    "build_production_orchestrator",
    "authorized_local_ahead_recovery_task",
    "build_worker_command",
    "build_poll_dispatch_plan",
    "is_git_checkout",
    "observe_durable_integration_reservations",
    "observe_durable_workflows",
    "read_branch_changed_paths",
    "read_working_tree_changed_paths",
    "scheduler_lock_path",
]
