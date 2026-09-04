#!/usr/bin/env python3
"""Supervised polling scheduler with a read-only architect preflight.

Stage 2 remains the only task-selection authority. This scheduler supplies
temporary per-poll exclusions, observes integration occupancy, asks the
architect for advice, applies deterministic conservative admission, and
launches at most one exact-task worker per poll. It never claims a task or
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
import subprocess
import sys
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
    DEFAULT_ARCHITECT_MAX_TURNS,
    DEFAULT_ARCHITECT_MIN_CONFIDENCE,
    DEFAULT_ARCHITECT_TIMEOUT_SECONDS,
    UNITY_SERIALIZED_SUFFIXES,
    ArchitectAdvisory,
    ArchitectAnalysis,
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
from Pipeline.TaskReviewAgent.dispatch_plan import (  # noqa: E402
    DispatchPlan,
    TaskcontrolStateObservationError,
    plan_dispatch,
)
import Pipeline.TaskReviewAgent.dispatch_plan as dispatch_plan_module  # noqa: E402
from Pipeline.TaskReviewAgent.issue_queue import repo_root  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    STATE_RE,
    WorkflowPhase,
    WorkflowState,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueBackend,
    IssueConsistencyRetryBudget,
    IssueWorkflowService,
    IssueWorkflowStoreError,
    _consistent_snapshots,
    issue_author_authorized,
)
from Pipeline.TaskReviewAgent.real_checkout import default_checkout_root  # noqa: E402
from Pipeline.TaskReviewAgent.execution_routing import (  # noqa: E402
    ExecutionRoutingError,
    ExecutionRoutingPolicy,
    ResolvedExecutionRoute,
    load_execution_routing_policy,
    resolve_execution_route,
)
from Pipeline.TaskDecomposition.context_builder import (  # noqa: E402
    DecompositionPreflightError,
    validate_task_selection as validate_decomposition_selection,
)
from Pipeline.AgentRuntime.contracts import (  # noqa: E402
    ContractValidationError,
    validate_repository_path,
)


SCHEDULER_SCHEMA_VERSION = "1.0"
DEFAULT_POLL_SECONDS = 60.0
DEFAULT_MAX_WORKERS = 1
DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_POLL = 3
DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_SESSION = 12
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
        }


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


def observe_durable_integration_reservations(
    *,
    source: Path | str,
    checkout_root: Path | str,
    worker_id: str,
    backend: IssueBackend | None = None,
    task_loader: Callable[[str], Mapping[str, Any]] | None = None,
    consistency_retry_budget: IssueConsistencyRetryBudget | None = None,
) -> tuple[IntegrationReservation, ...]:
    """Enumerate incomplete valid managed workflows through existing parsing.

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
    candidates: list[Mapping[str, Any]] = []
    for issue in selected_backend.list_issues():
        if str(issue.get("state") or "").upper() == "CLOSED":
            continue
        body = str(issue.get("body") or "")
        if STATE_RE.search(body) is None:
            continue
        if not issue_author_authorized(issue):
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
        if not snapshot.valid or not snapshot.managed or snapshot.state is None:
            raise IntegrationObservationError(
                f"managed Issue #{snapshot.issue_number} is invalid: "
                + "; ".join(snapshot.reasons)
            )
        state = snapshot.state
        if state.state is WorkflowState.COMPLETE:
            continue
        try:
            task = dict(load_task(state.task_id))
        except Exception as exc:
            raise IntegrationObservationError(
                f"could not load committed task {state.task_id}: {_bounded_error(exc)}"
            ) from exc
        if task.get("task_contract_sha256") != state.task_contract_sha256:
            raise IntegrationObservationError(
                f"durable {state.task_id} task-contract hash differs from committed HEAD"
            )

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
            )
        )
    return tuple(
        sorted(reservations, key=lambda item: (item.task_id, item.evidence_type))
    )


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
        ranked_eligible_candidates=fresh_plan.ranked_eligible_candidates,
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
        self.model = str(model).strip() if model else None
        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds
        self.compose_project = str(compose_project).strip()
        self.command_runner = command_runner or self._run

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
        if self.model:
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
    ) -> ArchitectAnalysis:
        if (task is None) == (candidates is None):
            raise ArchitectPreflightError(
                "architect runner requires exactly one task or candidate portfolio"
            )
        request = {
            "source_head": source_head,
            "reservations": [item.to_dict() for item in reservations],
        }
        if task is not None:
            request["task"] = dict(task)
        else:
            request["candidates"] = [dict(item) for item in candidates or ()]
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
        expected = {
            "schema_version",
            "analysis_id",
            "advisory",
            "artifact_name",
            "active_surface_fingerprint",
            "invocation_metadata",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ArchitectPreflightError("architect container result envelope is invalid")
        if value.get("schema_version") != ARCHITECT_ADVISORY_SCHEMA_VERSION:
            raise ArchitectPreflightError("architect container schema version is invalid")
        advisory = ArchitectAdvisory.from_dict(value["advisory"])
        artifact_name = value["artifact_name"]
        if (
            type(artifact_name) is not str
            or Path(artifact_name).name != artifact_name
            or not artifact_name.endswith(".json")
        ):
            raise ArchitectPreflightError("architect artifact name is invalid")
        artifact_path = self.artifact_root / artifact_name
        if not artifact_path.is_file():
            raise ArchitectPreflightError(
                f"architect advisory artifact is not visible on the host: {artifact_path}"
            )
        metadata = value["invocation_metadata"]
        if not isinstance(metadata, Mapping):
            raise ArchitectPreflightError("architect invocation metadata is invalid")
        return ArchitectAnalysis(
            analysis_id=str(value["analysis_id"]),
            advisory=advisory,
            artifact_path=artifact_path,
            active_surface_fingerprint=str(value["active_surface_fingerprint"]),
            invocation_metadata=dict(metadata),
        )


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
) -> tuple[str, ...]:
    # The Game Task Agent controller owns Git/GitHub/claim/Issue/checkout
    # authority and therefore runs on the Windows host. Claude/Codex remain
    # subordinate provider sandboxes launched by that host controller. The
    # outer argv keeps exact --task-id / --worker-id bindings for acceptance.
    task_id = validate_task_id(task_id)
    if type(worker_id) is not str or not worker_id.strip():
        raise PollingOrchestratorError("worker_id must be a non-empty string")
    if route is not None:
        provider = route.execution_provider
        supervisor_model = route.supervisor_model
        supervisor_reasoning_effort = route.supervisor_reasoning_effort
        execution_model = route.execution_model
        execution_reasoning_effort = route.execution_reasoning_effort
        supervisor_turns = route.max_supervisor_turns
    else:
        provider = str(execution_provider).strip().casefold()
        supervisor_model = str(model).strip() if model else None
        supervisor_reasoning_effort = None
        execution_model = None
        execution_reasoning_effort = None
        supervisor_turns = max_turns
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
    return tuple(command)


def build_decomposition_worker_command(
    *,
    task_id: str,
    worker_id: str,
    source: Path | str,
    checkout_root: Path | str,
    output_root: Path | str | None = None,
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
    return (
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
    )


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
        architect_runner: Callable[..., ArchitectAnalysis],
        routing_policy: ExecutionRoutingPolicy | None = None,
        routing_policy_loader: Callable[[], ExecutionRoutingPolicy] | None = None,
        max_architect_invocations_per_poll: int = (
            DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_POLL
        ),
        max_architect_invocations_per_session: int = (
            DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_SESSION
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
        self.max_architect_invocations_per_session = (
            max_architect_invocations_per_session
        )
        self.architect_min_reanalysis_seconds = architect_min_reanalysis_seconds
        self.max_consecutive_observation_failures = (
            max_consecutive_observation_failures
        )
        self.fatal_drain_seconds = fatal_drain_seconds
        self.decision_cache = decision_cache or ArchitectDecisionCache()
        self.architect_invocations_this_poll = 0
        self.architect_invocations_this_session = 0
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
        self.dry_run = bool(dry_run)
        self.compose_project = str(compose_project).strip()
        self.monotonic_clock = monotonic_clock
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
            isinstance(max_architect_invocations_per_session, bool)
            or not isinstance(max_architect_invocations_per_session, int)
            or max_architect_invocations_per_session < 1
        ):
            raise PollingOrchestratorError(
                "max_architect_invocations_per_session must be a positive integer"
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

    def _reap_workers(self) -> bool:
        failed = False
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
            if returncode == 0:
                self.events.emit(
                    "worker_finished",
                    task_id=task_id,
                    worker_id=assignment.worker_id,
                    pid=assignment.pid,
                    checkout_path=str(assignment.checkout_path),
                    returncode=0,
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
        return failed

    def _drain_active_workers(self, *, poll_seconds: float) -> bool:
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
            self._reap_workers()
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
                (dict(candidate), None)
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
            if resume_phase is None:
                try:
                    validate_decomposition_selection(task_id, task)
                except DecompositionPreflightError:
                    pass
                else:
                    work_types.append("decomposition")
            by_id[task_id] = (
                dict(candidate),
                resume_phase,
                {"task": task, "eligible_work_types": sorted(work_types)},
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
            task_id = validate_task_id(task_id_raw)
            task = self._load_candidate(plan, candidate, task_id)
            try:
                validate_decomposition_selection(task_id, task)
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
        analysis: ArchitectAnalysis | None = None,
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
        if self._reap_workers():
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

        integration_fingerprint = active_surface_fingerprint(reservations)
        temporary_exclusions = set(self.active_assignments).union(
            self.excluded_task_ids
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
        if not candidates:
            self.events.emit(
                "scheduler_blocked",
                reason="Stage-2 plan omitted its ordered candidate data",
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
            # A durable resume already passed through human or prior agent work. Give
            # it a dedicated architect decision before offering fresh work. If the
            # architect returns WAIT/HUMAN_REVIEW, the decision cache removes the
            # resume on the next capacity pass and fresh work can still proceed.
            mixed_portfolio = resume_portfolio[:1]
            self.events.emit(
                "resume_priority_applied",
                task_id=mixed_portfolio[0][2]["task"]["id"],
                resume_phase=mixed_portfolio[0][1],
                deferred_fresh_candidate_count=len(prefiltered_portfolio) - 1,
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
            self.architect_invocations_this_session
            >= self.max_architect_invocations_per_session
        ):
            self.events.emit(
                "scheduler_blocked",
                reason="cumulative architect session invocation cap is exhausted",
            )
            return PollCycleResult("architect_session_budget_exhausted", fatal=True)
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
        self.architect_invocations_this_session += 1
        try:
            portfolio_analysis = self.architect_runner(
                candidates=portfolio_request,
                source_head=plan.source_commit,
                reservations=reservations,
                scheduler_id=self.scheduler_id,
            )
            selected_advisory = portfolio_analysis.advisory
            selected_key = (
                selected_advisory.task_id,
                selected_advisory.work_type_recommendation,
            )
            selected_entry = next(
                (
                    item
                    for item in mixed_portfolio
                    if item[2]["task"]["id"] == selected_key[0]
                    and selected_key[1] in item[2]["eligible_work_types"]
                ),
                None,
            )
            if selected_entry is None:
                raise ArchitectPreflightError(
                    "architect selected a pair outside the revalidated mixed portfolio"
                )
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
        candidates = ((selected_entry[0], selected_entry[1]),)

        considered: set[str] = set()
        for candidate, resume_phase in candidates[:MAX_CANDIDATES_PER_POLL]:
            task_id_raw = candidate.get("task_id")
            if type(task_id_raw) is not str:
                self.events.emit(
                    "scheduler_blocked",
                    reason="Stage-2 plan omitted the selected task identity",
                )
                return PollCycleResult("missing_candidate", fatal=True)
            task_id = validate_task_id(task_id_raw)
            if task_id in considered:
                self.events.emit(
                    "scheduler_blocked",
                    task_id=task_id,
                    reason="Stage 2 emitted a duplicate task in one ordered poll plan",
                )
                return PollCycleResult(
                    "duplicate_planned_candidate", task_id=task_id, fatal=True
                )
            considered.add(task_id)
            if resume_phase == "unity_runtime_validation":
                self.events.emit(
                    "scheduler_blocked",
                    task_id=task_id,
                    reason="human_action_required/unity_runtime_validation is never agent work",
                )
                temporary_exclusions.add(task_id)
                continue
            try:
                task = self._load_candidate(plan, candidate, task_id)
            except (PollingOrchestratorError, CommittedTaskError, OSError) as exc:
                self.events.emit(
                    "scheduler_blocked",
                    task_id=task_id,
                    reason="candidate identity could not be re-verified",
                    error=_bounded_error(exc),
                )
                return PollCycleResult("candidate_verification_failed", task_id=task_id, fatal=True)

            empty_surface = effective_candidate_surface(
                candidate_task_id=task_id,
                predicted_surface=PredictedChangeSurface((), (), (), (), ()),
                reservations=reservations,
            )
            preflight_conflict = detect_deterministic_conflict(
                candidate_task_id=task_id,
                candidate_exclusive_resources=task.get("exclusive_resources") or (),
                candidate_surface=empty_surface,
                reservations=reservations,
            )
            if preflight_conflict is not None:
                self._emit_conflict(task_id, preflight_conflict)
                temporary_exclusions.add(task_id)
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
            unknown_surface = assess_unknown_surface_reservations(
                candidate_task_id=task_id,
                candidate_exclusive_resources=task.get("exclusive_resources") or (),
                reservations=reservations,
            )
            if unknown_surface.blocks_without_architect:
                self.events.emit(
                    "candidate_wait_unknown_surface",
                    task_id=task_id,
                    blocking_task_ids=list(unknown_surface.blocking_task_ids),
                    reasons=list(unknown_surface.reasons),
                    scope=(
                        "excluded for this scheduling pass only; unrelated candidates "
                        "remain eligible"
                    ),
                )
                temporary_exclusions.add(task_id)
                continue

            analysis = portfolio_analysis
            advisory = selected_advisory
            if advisory.task_id != task_id:
                self.events.emit(
                    "scheduler_blocked",
                    task_id=task_id,
                    reason="portfolio advisory identity changed after selection",
                )
                return PollCycleResult("candidate_verification_failed", fatal=True)
            self.events.emit(
                "architect_completed",
                task_id=task_id,
                analysis_id=analysis.analysis_id,
                advisory_artifact_path=str(analysis.artifact_path),
                integration_risk=advisory.integration_risk,
                parallel_recommendation=advisory.parallel_recommendation,
                work_type_recommendation=advisory.work_type_recommendation,
                confidence=advisory.confidence,
                execution_recommendation=(
                    advisory.execution_recommendation.to_dict()
                ),
                design_advice=advisory.design_advice.to_dict(),
            )

            effective_surface = effective_candidate_surface(
                candidate_task_id=task_id,
                predicted_surface=advisory.predicted_change_surface,
                reservations=reservations,
            )
            conflict = detect_deterministic_conflict(
                candidate_task_id=task_id,
                candidate_exclusive_resources=task.get("exclusive_resources") or (),
                candidate_surface=effective_surface,
                reservations=reservations,
            )
            if conflict is not None:
                self._emit_conflict(task_id, conflict)
                self._remember_nonstart(
                    cache_key=cache_key,
                    cooldown_key=cooldown_key,
                    decision=ArchitectPolicyDecision(
                        "wait", (conflict.reason,)
                    ),
                )
                temporary_exclusions.add(task_id)
                continue
            unconfirmed = unconfirmed_unknown_surface_task_ids(advisory, unknown_surface)
            if unconfirmed:
                self._record_gate(
                    task_id=task_id,
                    cache_key=cache_key,
                    cooldown_key=cooldown_key,
                    decision=ArchitectPolicyDecision(
                        "wait",
                        tuple(
                            f"the architect did not establish that {task_id} is disjoint "
                            f"from the unobservable integration surface of {other_id}"
                            for other_id in unconfirmed
                        ),
                    ),
                    analysis=analysis,
                )
                temporary_exclusions.add(task_id)
                continue
            gate = evaluate_architect_policy(
                advisory, min_confidence=self.architect_min_confidence
            )
            if gate.decision in {"wait", "human_review"}:
                self._record_gate(
                    task_id=task_id,
                    cache_key=cache_key,
                    cooldown_key=cooldown_key,
                    decision=gate,
                    analysis=analysis,
                )
                temporary_exclusions.add(task_id)
                continue

            if len(self.active_assignments) >= self.max_workers:
                self.events.emit(
                    "scheduler_blocked",
                    task_id=task_id,
                    reason="local capacity filled before launch",
                )
                return PollCycleResult("capacity_full")
            worker_id = f"polling-worker-{task_id.casefold()}-{uuid.uuid4().hex[:12]}"
            if advisory.work_type_recommendation == "decomposition":
                command = build_decomposition_worker_command(
                    task_id=task_id,
                    worker_id=worker_id,
                    source=self.source,
                    checkout_root=self.checkout_root,
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
                    route = resolve_execution_route(
                        advisory.execution_recommendation,
                        policy,
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
                )
                route_event = {"work_type": "implementation", **route.to_event_dict()}
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
                start_time_utc=utc_now(),
            )
            self.active_assignments[task_id] = assignment
            self.events.emit(
                "worker_launched",
                task_id=task_id,
                worker_id=worker_id,
                pid=assignment.pid,
                checkout_path=str(assignment.checkout_path),
                advisory_artifact_path=str(analysis.artifact_path),
                argv=list(command),
                **route_event,
            )
            return PollCycleResult("worker_launched", task_id=task_id, worker_id=worker_id)

        if len(candidates) > MAX_CANDIDATES_PER_POLL:
            self.events.emit(
                "scheduler_blocked",
                reason="candidate evaluation exceeded the finite per-poll safety bound",
            )
            return PollCycleResult("candidate_bound_exceeded", fatal=True)
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

        Each launch is followed by a complete source refresh, Stage-2 plan, and
        reservation re-observation through ``poll_once``. This preserves the
        integration safety boundary while making the per-poll architect budget and
        ``max_workers`` settings operational rather than merely descriptive.
        """

        self.architect_invocations_this_poll = 0
        launched_task_ids: list[str] = []
        last_launch: PollCycleResult | None = None
        while True:
            invocations_before = self.architect_invocations_this_poll
            cycle = self.poll_once(reset_architect_budget=False)
            architect_invoked = (
                self.architect_invocations_this_poll > invocations_before
            )
            if cycle.status == "worker_launched" and cycle.task_id is not None:
                launched_task_ids.append(cycle.task_id)
                last_launch = cycle
            if cycle.fatal:
                break
            if len(self.active_assignments) >= self.max_workers:
                break
            if (
                self.architect_invocations_this_poll
                >= self.max_architect_invocations_per_poll
            ):
                break
            if cycle.status == "worker_launched":
                continue
            # One paid WAIT/HUMAN_REVIEW decision may have removed a candidate
            # from the next pass through the decision cache. Continue within the
            # same bounded poll so an unrelated candidate is not starved.
            if cycle.status == "idle" and architect_invoked:
                continue
            break
        reported_cycle = (
            last_launch
            if last_launch is not None and not cycle.fatal
            else cycle
        )
        self.events.emit(
            "poll_capacity_batch_completed",
            launched_task_ids=launched_task_ids,
            launched_count=len(launched_task_ids),
            active_worker_count=len(self.active_assignments),
            architect_invocations=self.architect_invocations_this_poll,
            result_status=reported_cycle.status,
            terminal_pass_status=cycle.status,
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
            architect_max_invocations_per_session=(
                self.max_architect_invocations_per_session
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
                        drained = self._drain_active_workers(poll_seconds=poll_seconds)
                        if not drained:
                            stop_reason = f"{cycle.status}_drain_timeout"
                    break
                if once:
                    stop_reason = cycle.status
                    break
                time.sleep(poll_seconds)
        except KeyboardInterrupt:
            if exit_code:
                stop_reason = f"{stop_reason}_drain_interrupted"
            else:
                stop_reason = "keyboard_interrupt"
                exit_code = 0
        finally:
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
        "--architect-max-invocations-per-session",
        type=_positive_int,
        default=DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_SESSION,
        help=(
            "Hard cumulative paid architect-call cap for this scheduler session. "
            "Exhaustion stops new admissions with a non-success result."
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    events = JsonEventEmitter()
    try:
        source = repo_root(args.source.resolve())
        checkout_root = Path(args.checkout_root or default_checkout_root())
        operational_root = (
            source / "Pipeline" / "ArchitectureReview" / "outputs" / "orchestrator"
        )
        artifact_root = operational_root / "architect"
        scheduler_id = default_scheduler_id()
        events = JsonEventEmitter(
            journal_path=operational_root / "events" / f"{scheduler_id}.jsonl"
        )
        architect_runner = DockerArchitectRunner(
            source=source,
            artifact_root=artifact_root,
            provider=args.architect_provider,
            model=args.architect_model,
            max_turns=args.architect_max_turns,
        )
        orchestrator = PollingOrchestrator(
            source=source,
            checkout_root=checkout_root,
            scheduler_id=scheduler_id,
            execution_provider=args.execution_provider,
            model=args.model,
            max_turns=args.max_turns,
            max_workers=args.max_workers,
            architect_min_confidence=args.architect_min_confidence,
            architect_runner=architect_runner,
            max_architect_invocations_per_poll=args.architect_max_invocations_per_poll,
            max_architect_invocations_per_session=(
                args.architect_max_invocations_per_session
            ),
            architect_min_reanalysis_seconds=(
                args.architect_min_reanalysis_seconds
            ),
            max_consecutive_observation_failures=(
                args.max_consecutive_observation_failures
            ),
            fatal_drain_seconds=args.fatal_drain_seconds,
            event_emitter=events,
            excluded_task_ids=args.exclude_task_id,
            dry_run=args.dry_run,
        )
        lock = SchedulerLock(
            scheduler_lock_path(
                checkout_root=checkout_root,
                source=source,
            )
        )
        return orchestrator.run(
            lock=lock,
            poll_seconds=args.poll_seconds,
            once=args.once,
        )
    except (
        PollingOrchestratorError,
        ArchitectPreflightError,
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
    "FRESH_POOL_UNAVAILABLE_REASON",
    "IntegrationObservationError",
    "IntegrationReservation",
    "JsonEventEmitter",
    "PollCycleResult",
    "PollingOrchestrator",
    "PollingOrchestratorError",
    "SchedulerAlreadyActive",
    "SchedulerLock",
    "build_worker_command",
    "build_poll_dispatch_plan",
    "is_git_checkout",
    "observe_durable_integration_reservations",
    "read_branch_changed_paths",
    "read_working_tree_changed_paths",
    "scheduler_lock_path",
]
