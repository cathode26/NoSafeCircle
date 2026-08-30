"""Stage 2 deterministic, read-only dispatch planning for generic get-work.

This module answers "what work would a generic orchestrator be allowed to
attempt next?" without starting it. It never creates/edits/closes a GitHub
Issue, never creates or deletes a Stage 1 claim ref, never creates a task
checkout, and never changes Git HEAD/index/working tree.

Two layers:

- :func:`evaluate_fresh_candidate` is the deterministic safety kernel for one
  task. It is deliberately reusable for both automatic generic ranking and
  explicit ``-TaskId`` admission (Stage 3), so a task rejected one way is
  rejected identically the other way.
- :func:`plan_dispatch` composes the resume-first preference, the fresh
  candidate pool, and deterministic ranking into one bounded, typed
  :class:`DispatchPlan`. :func:`build_dispatch_plan` is the production
  wrapper that wires real Git/GitHub/Stage-1-claim components; tests call
  :func:`plan_dispatch` directly with in-memory fakes.

Autonomous dispatch remains disabled: this module only plans, it never
executes, claims, or hands work to a worker.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from .claim_policy import (
    ACTIVATION_ACTIVE,
    ClaimPolicy,
    ClaimPolicyError,
    load_claim_policy,
)
from .claim_refs import (
    ClaimRefsError,
    GitRefClaimClient,
    resource_claim_ref,
    task_claim_ref,
)
from .committed_tasks import CommittedTaskError, load_committed_task
from .contracts import TASK_ID_RE, TaskReviewContractError, validate_task_id
from .dispatch_policy import DispatchPolicy, load_dispatch_policy
from .issue_queue import repo_root
from .issue_workflow import WorkflowState
from .issue_workflow_store import (
    GhIssueBackend,
    IssueBackend,
    IssueWorkflowService,
    IssueWorkflowStoreError,
)

DISPATCH_PLAN_SCHEMA_VERSION = "1.0"
_READONLY_CLAIM_WORKER_ID = "stage2-dispatch-plan-readonly"


class StateProvider(Protocol):
    def __call__(self, task_id: str) -> Mapping[str, Any]:
        """Return ``{"task_id", "state", "error", ...}`` for one task's
        evidence-derived current-conformance state (never mutates anything)."""


class TaskLoader(Protocol):
    def __call__(self, task_id: str) -> Mapping[str, Any]:
        """Return the committed schema-v2 task contract for one task ID."""


@dataclass(frozen=True)
class DependencyObservation:
    task_id: str
    state: str | None
    dispatch_satisfied: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "state": self.state,
            "dispatch_satisfied": self.dispatch_satisfied,
            "note": self.note,
        }


@dataclass(frozen=True)
class FreshCandidateEvaluation:
    task_id: str
    eligible: bool
    reason_codes: tuple[str, ...]
    title: str | None
    derived_state: str | None
    kind: str | None
    execution_scope: str | None
    decomposition_state: str | None
    contract_disposition: str | None
    exclusive_resources: tuple[str, ...]
    depends_on: tuple[str, ...]
    dependency_observations: tuple[DependencyObservation, ...]
    task_contract_sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "eligible": self.eligible,
            "reason_codes": list(self.reason_codes),
            "title": self.title,
            "derived_state": self.derived_state,
            "kind": self.kind,
            "execution_scope": self.execution_scope,
            "decomposition_state": self.decomposition_state,
            "contract_disposition": self.contract_disposition,
            "exclusive_resources": list(self.exclusive_resources),
            "depends_on": list(self.depends_on),
            "dependency_observations": [
                item.to_dict() for item in self.dependency_observations
            ],
            "task_contract_sha256": self.task_contract_sha256,
        }


def _rejected(task_id: str, *reason_codes: str) -> FreshCandidateEvaluation:
    return FreshCandidateEvaluation(
        task_id=task_id,
        eligible=False,
        reason_codes=tuple(reason_codes),
        title=None,
        derived_state=None,
        kind=None,
        execution_scope=None,
        decomposition_state=None,
        contract_disposition=None,
        exclusive_resources=(),
        depends_on=(),
        dependency_observations=(),
        task_contract_sha256=None,
    )


def evaluate_fresh_candidate(
    task_id: str,
    *,
    task_loader: TaskLoader,
    state_provider: StateProvider,
    issue_workflow: IssueWorkflowService,
    claimed_refs: Mapping[str, str],
    claim_namespace: str | None,
    policy: DispatchPolicy | None = None,
) -> FreshCandidateEvaluation:
    """Deterministically decide whether ``task_id`` is safe fresh Stage 2 work.

    This is the ONE safety kernel: both automatic generic ranking
    (:func:`plan_dispatch`) and explicit ``-TaskId`` admission call this exact
    function, so a task rejected one way is rejected identically the other
    way. It never mutates anything — every input is read-only.
    """

    policy = policy or load_dispatch_policy()
    try:
        task_id = validate_task_id(task_id)
    except TaskReviewContractError:
        return _rejected(str(task_id), "malformed_task_id")

    try:
        task = task_loader(task_id)
    except (TaskReviewContractError, CommittedTaskError) as exc:
        return _rejected(task_id, f"committed_task_load_failed:{exc}")

    reasons: list[str] = []

    if task.get("schema_version") != "2.0":
        reasons.append("unsupported_schema_version")
    if task.get("contract_disposition") != "active":
        reasons.append("contract_not_active")
    parent = task.get("parent")
    if not isinstance(parent, str) or not parent.strip():
        reasons.append("is_root_task")
    kind = task.get("kind")
    if kind not in ("implementation", "artifact"):
        reasons.append("unsupported_kind")
    if task.get("execution_scope") != "single_agent":
        reasons.append("execution_scope_not_single_agent")
    if task.get("decomposition_state") != "concrete":
        reasons.append("decomposition_state_not_concrete")

    depends_on_raw = task.get("depends_on") or []
    if not isinstance(depends_on_raw, list) or any(
        type(item) is not str or not item.strip() for item in depends_on_raw
    ):
        reasons.append("malformed_depends_on")
        depends_on: tuple[str, ...] = ()
    else:
        depends_on = tuple(depends_on_raw)

    resources_raw = task.get("exclusive_resources") or []
    if not isinstance(resources_raw, list) or any(
        type(item) is not str or not item.strip() for item in resources_raw
    ):
        reasons.append("malformed_exclusive_resources")
        resources: tuple[str, ...] = ()
    else:
        resources = tuple(resources_raw)

    own_observation = dict(state_provider(task_id) or {})
    derived_state = own_observation.get("state")
    if own_observation.get("error") is not None or not isinstance(derived_state, str):
        reasons.append("state_lookup_failed")
        derived_state = None
    elif derived_state not in policy.fresh_implementation_derived_states:
        reasons.append(f"derived_state_not_fresh:{derived_state}")

    dependency_observations: list[DependencyObservation] = []
    for dependency_id in depends_on:
        dep_observation = dict(state_provider(dependency_id) or {})
        dep_state = dep_observation.get("state")
        if dep_observation.get("error") is not None or not isinstance(dep_state, str):
            dependency_observations.append(
                DependencyObservation(dependency_id, None, False, "state_lookup_failed")
            )
            reasons.append(f"dependency_blocked:{dependency_id}:state_lookup_failed")
            continue
        if dep_state in policy.dependency_dispatch_satisfied_states:
            note = "conformant" if dep_state == "conformant" else "revalidation_debt"
            dependency_observations.append(
                DependencyObservation(dependency_id, dep_state, True, note)
            )
            continue
        if dep_state in policy.known_dependency_states:
            dependency_observations.append(
                DependencyObservation(dependency_id, dep_state, False, "not_dispatch_satisfied")
            )
            reasons.append(f"dependency_blocked:{dependency_id}:{dep_state}")
            continue
        # Fail closed: a dependency state outside the committed known set is
        # never silently treated as satisfied.
        dependency_observations.append(
            DependencyObservation(dependency_id, dep_state, False, "unknown_state_fails_closed")
        )
        reasons.append(f"dependency_blocked:{dependency_id}:unknown_state")

    try:
        snapshot = issue_workflow.find(task_id)
    except IssueWorkflowStoreError as exc:
        reasons.append(f"managed_issue_invalid:{exc}")
    else:
        if snapshot is not None:
            if not snapshot.valid:
                reasons.append("managed_issue_invalid")
            elif (
                snapshot.managed
                and snapshot.state is not None
                and snapshot.state.state is not WorkflowState.COMPLETE
            ):
                reasons.append("operationally_owned_by_managed_issue")

    try:
        conflicts, _diagnostics = issue_workflow.resource_conflicts(task)
    except IssueWorkflowStoreError as exc:
        reasons.append(f"resource_reservation_scan_failed:{exc}")
    else:
        for conflict in conflicts:
            reasons.append(f"resource_reservation_conflict:{conflict}")

    if claim_namespace is not None:
        try:
            if task_claim_ref(claim_namespace, task_id) in claimed_refs:
                reasons.append("active_stage1_task_claim")
            for resource in resources:
                if resource_claim_ref(claim_namespace, resource) in claimed_refs:
                    reasons.append("active_stage1_resource_claim")
                    break
        except ClaimRefsError as exc:
            # A malformed/oversized resource token (see
            # claim_refs.canonical_resource_hash) must reject only this one
            # candidate, never crash the whole generic dispatch plan.
            reasons.append(f"malformed_exclusive_resource_token:{exc}")

    return FreshCandidateEvaluation(
        task_id=task_id,
        eligible=not reasons,
        reason_codes=tuple(reasons),
        title=task.get("title") if isinstance(task.get("title"), str) else None,
        derived_state=derived_state,
        kind=kind if isinstance(kind, str) else None,
        execution_scope=task.get("execution_scope")
        if isinstance(task.get("execution_scope"), str)
        else None,
        decomposition_state=task.get("decomposition_state")
        if isinstance(task.get("decomposition_state"), str)
        else None,
        contract_disposition=task.get("contract_disposition")
        if isinstance(task.get("contract_disposition"), str)
        else None,
        exclusive_resources=resources,
        depends_on=depends_on,
        dependency_observations=tuple(dependency_observations),
        task_contract_sha256=task.get("task_contract_sha256")
        if isinstance(task.get("task_contract_sha256"), str)
        else None,
    )


def _numeric_task_id(task_id: str) -> int:
    try:
        return int(task_id.split("-", 1)[1])
    except (IndexError, ValueError):
        return 0


@dataclass(frozen=True)
class DispatchPlan:
    schema_version: str
    source_commit: str
    mode: str
    autonomous_dispatch: bool
    decision: str
    resume: dict[str, Any] | None
    selected_fresh_candidate: dict[str, Any] | None
    ranked_eligible_candidates: tuple[dict[str, Any], ...]
    skipped_candidates: tuple[dict[str, Any], ...]
    agent_ready_count: int
    claim_observation: dict[str, Any]
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_commit": self.source_commit,
            "mode": self.mode,
            "autonomous_dispatch": self.autonomous_dispatch,
            "decision": self.decision,
            "resume": self.resume,
            "selected_fresh_candidate": self.selected_fresh_candidate,
            "ranked_eligible_candidates": list(self.ranked_eligible_candidates),
            "skipped_candidates": list(self.skipped_candidates),
            "agent_ready_count": self.agent_ready_count,
            "claim_observation": self.claim_observation,
            "reasons": list(self.reasons),
        }


def _blocked_plan(*, source_commit: str, reasons: Iterable[str]) -> DispatchPlan:
    return DispatchPlan(
        schema_version=DISPATCH_PLAN_SCHEMA_VERSION,
        source_commit=source_commit,
        mode="read_only_plan",
        autonomous_dispatch=False,
        decision="blocked_invalid_state",
        resume=None,
        selected_fresh_candidate=None,
        ranked_eligible_candidates=(),
        skipped_candidates=(),
        agent_ready_count=0,
        claim_observation={"status": "not_consulted"},
        reasons=tuple(reasons),
    )


def plan_dispatch(
    *,
    source_commit: str,
    task_ids: Iterable[str],
    task_loader: TaskLoader,
    state_provider: StateProvider,
    issue_workflow: IssueWorkflowService,
    claimed_refs: Mapping[str, str] | None = None,
    claim_namespace: str | None = None,
    claim_observation: Mapping[str, Any] | None = None,
    provisional_reasons: Iterable[str] = (),
    policy: DispatchPolicy | None = None,
) -> DispatchPlan:
    """Pure, deterministic Stage 2 planning core: no filesystem/network I/O
    of its own. Every side-effecting input (task/state lookup, Issue
    observation, claim-ref snapshot) is injected, so this function is safe to
    call repeatedly with in-memory fakes in tests.

    ``provisional_reasons`` carries plan-level caveats that are true of the
    whole plan regardless of decision -- for example, an unread Stage 1
    claim snapshot. They are attached to the resulting plan's ``reasons``
    even when the decision is an ordinary ``resume_existing`` or
    ``fresh_candidate``, so a normal-looking plan still says out loud that it
    is provisional.
    """

    policy = policy or load_dispatch_policy()
    claimed_refs = dict(claimed_refs or {})
    claim_observation = dict(claim_observation or {"status": "not_consulted"})
    provisional = tuple(provisional_reasons)

    try:
        agent_ready = issue_workflow.list_agent_ready()
    except IssueWorkflowStoreError as exc:
        return _blocked_plan(
            source_commit=source_commit,
            reasons=(f"could not list agent-ready Issues: {exc}",),
        )

    if agent_ready:
        selected = agent_ready[0]
        state = selected.get("workflow_state") or {}
        resume = {
            "task_id": state.get("task_id"),
            "issue_number": selected.get("issue_number"),
            "issue_url": selected.get("issue_url"),
            "phase": state.get("phase"),
            "branch": state.get("branch"),
            "commit": state.get("head_commit"),
            "human_result": state.get("human_result"),
        }
        return DispatchPlan(
            schema_version=DISPATCH_PLAN_SCHEMA_VERSION,
            source_commit=source_commit,
            mode="read_only_plan",
            autonomous_dispatch=False,
            decision="resume_existing",
            resume=resume,
            selected_fresh_candidate=None,
            ranked_eligible_candidates=(),
            skipped_candidates=(),
            agent_ready_count=len(agent_ready),
            claim_observation=claim_observation,
            reasons=provisional,
        )

    normalized_ids: list[str] = []
    for task_id in sorted(set(task_ids)):
        if type(task_id) is str and TASK_ID_RE.fullmatch(task_id):
            normalized_ids.append(task_id)

    evaluations = [
        evaluate_fresh_candidate(
            task_id,
            task_loader=task_loader,
            state_provider=state_provider,
            issue_workflow=issue_workflow,
            claimed_refs=claimed_refs,
            claim_namespace=claim_namespace,
            policy=policy,
        )
        for task_id in normalized_ids
    ]

    def _rank_key(item: FreshCandidateEvaluation) -> tuple[int, str]:
        return (_numeric_task_id(item.task_id), item.task_id)

    eligible = sorted((item for item in evaluations if item.eligible), key=_rank_key)
    skipped = sorted((item for item in evaluations if not item.eligible), key=_rank_key)

    decision = "fresh_candidate" if eligible else "no_safe_work"
    return DispatchPlan(
        schema_version=DISPATCH_PLAN_SCHEMA_VERSION,
        source_commit=source_commit,
        mode="read_only_plan",
        autonomous_dispatch=False,
        decision=decision,
        resume=None,
        selected_fresh_candidate=eligible[0].to_dict() if eligible else None,
        ranked_eligible_candidates=tuple(item.to_dict() for item in eligible),
        skipped_candidates=tuple(item.to_dict() for item in skipped),
        agent_ready_count=0,
        claim_observation=claim_observation,
        reasons=provisional,
    )


# ---------------------------------------------------------------------------
# Production wiring: real Git/GitHub/Stage-1-claim components.
# ---------------------------------------------------------------------------


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ("git", "-C", str(root), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60.0,
    )


def _git_head(root: Path) -> str:
    result = _run_git(root, "rev-parse", "--verify", "HEAD")
    if result.returncode != 0:
        raise IssueWorkflowStoreError("could not resolve committed HEAD")
    return result.stdout.decode("utf-8").strip()


def list_committed_task_ids(root: Path) -> list[str]:
    """Every ``Tasks/NSC-###.yaml`` task ID at committed HEAD (read-only)."""

    result = _run_git(root, "ls-tree", "--name-only", "-r", "HEAD", "--", "Tasks")
    if result.returncode != 0:
        raise IssueWorkflowStoreError("could not list committed Tasks/ contracts")
    task_ids: set[str] = set()
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        name = Path(line.strip()).name
        if not name.endswith(".yaml"):
            continue
        candidate = name[: -len(".yaml")]
        if TASK_ID_RE.fullmatch(candidate):
            task_ids.add(candidate)
    return sorted(task_ids)


def _taskcontrol_states_snapshot(root: Path) -> tuple[dict[str, dict[str, Any]], str | None]:
    """One bulk ``taskcontrol.py states --json`` call for the whole plan.

    Delegates current-conformance evaluation to the same committed authority
    :mod:`real_observation` uses, but as ONE subprocess for every task
    instead of one ``taskcontrol.py state <id> --json`` subprocess per
    candidate/dependency edge -- on the committed 60-task/106-edge graph that
    per-task shape cost roughly 166 redundant subprocess launches per plan.

    Returns ``(task_id -> {"task_id", "state", "error", "head_commit"},
    bulk_error)``. A bulk failure never crashes the whole plan: it is
    surfaced as a per-task ``state_lookup_failed`` reason by the returned
    state-provider closure, exactly as an individual lookup failure already
    was.
    """

    taskcontrol_path = root / "Pipeline" / "TaskGraph" / "taskcontrol.py"
    try:
        result = subprocess.run(
            (sys.executable, str(taskcontrol_path), "states", "--json"),
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=300.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, f"taskcontrol states could not run: {exc}"
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        return {}, f"taskcontrol states failed ({result.returncode}): {detail}"
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, f"taskcontrol states returned invalid JSON: {exc}"
    if not isinstance(payload, list):
        return {}, "taskcontrol states payload malformed: expected a JSON array"

    snapshot: dict[str, dict[str, Any]] = {}
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        task_id = entry.get("task_id")
        state = entry.get("state")
        if type(task_id) is not str or type(state) is not str:
            continue
        head_commit = entry.get("head_commit")
        snapshot[task_id] = {
            "task_id": task_id,
            "state": state,
            "error": None,
            "head_commit": head_commit if isinstance(head_commit, str) else None,
        }
    return snapshot, None


class _PlanScopedIssueBackend:
    """Read-through Issue-snapshot cache scoped to one dispatch-plan call.

    Without this, ``IssueWorkflowService.find`` and ``.resource_conflicts``
    each call ``list_issues``/``get_comments`` again for every candidate and
    dependency edge, which is slow and lets two candidates evaluated within
    one plan observe two different GitHub states. ``list_issues`` is fetched
    once and reused; ``get_comments`` is cached per Issue number. The cache
    is a plain instance created fresh inside :func:`build_dispatch_plan` and
    discarded when that call returns -- it is never persisted or shared
    across plan invocations. Every mutating method raises: Stage 2 dispatch
    planning must never create, update, or comment on a GitHub Issue.
    """

    def __init__(self, backend: IssueBackend) -> None:
        self._backend = backend
        self._issues: list[dict[str, Any]] | None = None
        self._comments: dict[int, list[dict[str, Any]]] = {}

    def list_issues(self) -> list[dict[str, Any]]:
        if self._issues is None:
            self._issues = self._backend.list_issues()
        return self._issues

    def get_comments(self, issue_number: int) -> list[dict[str, Any]]:
        if issue_number not in self._comments:
            self._comments[issue_number] = self._backend.get_comments(issue_number)
        return self._comments[issue_number]

    def create_issue(self, **_kwargs: Any) -> dict[str, Any]:
        raise IssueWorkflowStoreError(
            "Stage 2 dispatch planning is read-only and must never create a GitHub Issue"
        )

    def update_issue(self, _issue_number: int, **_kwargs: Any) -> dict[str, Any]:
        raise IssueWorkflowStoreError(
            "Stage 2 dispatch planning is read-only and must never update a GitHub Issue"
        )

    def add_comment(self, _issue_number: int, _body: str) -> dict[str, Any]:
        raise IssueWorkflowStoreError(
            "Stage 2 dispatch planning is read-only and must never comment on a GitHub Issue"
        )

    def ensure_labels(self) -> None:
        raise IssueWorkflowStoreError(
            "Stage 2 dispatch planning is read-only and must never mutate GitHub labels"
        )


def _read_only_claim_observation(
    *,
    root: Path,
    remote: str,
    claim_policy: ClaimPolicy | None,
) -> tuple[dict[str, str], str | None, dict[str, Any], tuple[str, ...]]:
    """Best-effort read-only Stage 1 claim-ref snapshot.

    Returns ``(claimed_refs, claim_namespace, observation,
    provisional_reasons)``. Never creates, updates, or deletes a claim ref —
    only ``git ls-remote`` (see :meth:`GitRefClaimClient.list_remote_claims`).
    Stage 3's atomic claim acquisition remains the real arbitration
    authority.

    Two failure modes are deliberately distinguished:

    - An INVALID committed claim policy (:class:`ClaimPolicyError`) is a
      corrupt committed coordination policy, not a transient read problem.
      It is never caught here — it propagates so the caller returns
      ``blocked_invalid_state`` instead of a normal plan.
    - A TRANSIENT read failure (:class:`ClaimRefsError` from
      ``list_remote_claims``, e.g. an unreachable remote) never blocks the
      whole plan, but it must never look like "zero active claims were
      observed": ``claim_namespace`` comes back ``None`` — an explicit
      "claims were not observed" signal, never an active namespace paired
      with an empty claimed-ref map — and one clear plan-level reason
      explains that Stage 3's atomic claim acquisition remains authoritative.
    """

    policy = claim_policy or load_claim_policy()
    if policy.activation_status != ACTIVATION_ACTIVE or not policy.activated_namespace:
        return {}, None, {"status": "not_activated"}, ()
    namespace = policy.activated_namespace
    try:
        client = GitRefClaimClient(
            local_repository=root,
            remote=remote,
            namespace=namespace,
            worker_id=_READONLY_CLAIM_WORKER_ID,
        )
        claimed_refs = client.list_remote_claims()
    except ClaimRefsError as exc:
        return (
            {},
            None,
            {
                "status": "unavailable",
                "namespace": namespace,
                "reason": f"could not read remote claim refs: {exc}",
            },
            (
                "Stage 1 claim snapshot unavailable; claim eligibility was not "
                "checked; Stage 3 atomic claim remains authoritative.",
            ),
        )
    return (
        claimed_refs,
        namespace,
        {
            "status": "observed",
            "namespace": namespace,
            "claimed_ref_count": len(claimed_refs),
        },
        (),
    )


def build_dispatch_plan(
    *,
    source: Path | str,
    worker_id: str,
    remote: str = "origin",
    policy: DispatchPolicy | None = None,
    claim_policy: ClaimPolicy | None = None,
) -> DispatchPlan:
    """Production Stage 2 entry point: real committed Git state, the real
    durable GitHub Issue reservation authority, and a best-effort read-only
    Stage 1 claim-ref snapshot. Performs no mutation of any kind.

    Uses one bulk ``taskcontrol.py states --json`` subprocess and one
    plan-scoped GitHub Issue-listing snapshot (see
    :func:`_taskcontrol_states_snapshot` and :class:`_PlanScopedIssueBackend`)
    instead of repeating either lookup per candidate/dependency. Captures
    ``source_commit`` at the start and re-verifies committed HEAD has not
    moved, both against each state observation's own ``head_commit`` and
    against a final HEAD re-read after every production observation has been
    assembled — a plan must never mix observations from multiple Git
    revisions.
    """

    try:
        root = repo_root(Path(source).resolve())
        source_commit = _git_head(root)
        task_ids = list_committed_task_ids(root)
        issue_workflow = IssueWorkflowService(
            backend=_PlanScopedIssueBackend(GhIssueBackend(source_root=root)),
            task_loader=lambda task_id: load_committed_task(root, task_id),
            worker_id=worker_id,
        )
    except (IssueWorkflowStoreError, TaskReviewContractError) as exc:
        return _blocked_plan(
            source_commit="unknown",
            reasons=(f"could not observe committed repository state: {exc}",),
        )

    try:
        claimed_refs, claim_namespace, claim_observation, provisional_reasons = (
            _read_only_claim_observation(root=root, remote=remote, claim_policy=claim_policy)
        )
    except ClaimPolicyError as exc:
        return _blocked_plan(
            source_commit=source_commit,
            reasons=(f"committed Stage 1 claim policy is invalid: {exc}",),
        )

    states_snapshot, states_error = _taskcontrol_states_snapshot(root)
    drifted_commits = sorted(
        {
            entry["head_commit"]
            for entry in states_snapshot.values()
            if entry.get("head_commit") not in (None, source_commit)
        }
    )
    if drifted_commits:
        return _blocked_plan(
            source_commit=source_commit,
            reasons=(
                "taskcontrol states snapshot reports committed HEAD "
                f"{drifted_commits} different from the captured source_commit "
                f"{source_commit}; Git HEAD moved during dispatch planning",
            ),
        )

    def _snapshot_state_provider(task_id: str) -> dict[str, Any]:
        entry = states_snapshot.get(task_id)
        if entry is not None:
            return entry
        return {
            "task_id": task_id,
            "state": None,
            "error": states_error or f"no taskcontrol states entry for {task_id}",
        }

    plan = plan_dispatch(
        source_commit=source_commit,
        task_ids=task_ids,
        task_loader=lambda task_id: load_committed_task(root, task_id),
        state_provider=_snapshot_state_provider,
        issue_workflow=issue_workflow,
        claimed_refs=claimed_refs,
        claim_namespace=claim_namespace,
        claim_observation=claim_observation,
        provisional_reasons=provisional_reasons,
        policy=policy,
    )

    try:
        final_head = _git_head(root)
    except IssueWorkflowStoreError as exc:
        return _blocked_plan(
            source_commit=source_commit,
            reasons=(f"could not re-verify committed HEAD after planning: {exc}",),
        )
    if final_head != source_commit:
        return _blocked_plan(
            source_commit=source_commit,
            reasons=(
                f"Git HEAD moved from {source_commit} to {final_head} during "
                "dispatch planning; a plan must never mix observations from "
                "multiple Git revisions",
            ),
        )

    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 2 read-only dispatch plan: what fresh/resume work is safe to "
            "attempt next. Never mutates Issues, claim refs, checkouts, or Git "
            "state. Autonomous dispatch remains disabled."
        )
    )
    parser.add_argument("--source", default=".", help="Path inside the Git repository")
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--remote", default="origin")
    args = parser.parse_args(argv)
    plan = build_dispatch_plan(source=args.source, worker_id=args.worker_id, remote=args.remote)
    print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DISPATCH_PLAN_SCHEMA_VERSION",
    "DependencyObservation",
    "DispatchPlan",
    "FreshCandidateEvaluation",
    "build_dispatch_plan",
    "evaluate_fresh_candidate",
    "list_committed_task_ids",
    "plan_dispatch",
]
