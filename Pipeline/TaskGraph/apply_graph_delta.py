"""Standalone deterministic Stage D1C graph application and local commit boundary."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from TaskDecomposition.context_builder import (
    DecompositionPreflightError,
    capture_clean_source,
)
from decomposition_graph_semantics import validate_decomposition_graph_semantics
from graph_apply_materialize import (
    GraphApplyMaterializationError,
    GraphApplyMaterializationResult,
    materialize_graph_apply,
)
from graph_apply_plan import (
    GraphApplyPlanResult,
    GraphApplyPlanningError,
    plan_graph_apply,
)
from graph_delta import (
    GraphDeltaPlan,
    GraphDeltaPlanningError,
    NSC_ID_RE,
    _identity_dict,
    _plan_payload,
    semantic_json_sha256,
)
from persistent_work_graph import PersistentWorkGraph, load_persistent_work_graph
from work_graph_validate import validate_work_graph_plan


_TASK_REVIEW_AGENT_ROOT = Path(__file__).resolve().parents[1] / "TaskReviewAgent"
if str(_TASK_REVIEW_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_TASK_REVIEW_AGENT_ROOT))

from git_identity_guard import (  # noqa: E402
    DEFAULT_AGENT_GIT_EMAIL,
    DEFAULT_AGENT_GIT_NAME,
    GitIdentityGuardError,
    validated_agent_git_identity,
)


GraphApplyStatus = Literal[
    "applied",
    "already_applied",
    "stale_proposal",
    "recompute_mismatch",
    "source_graph_invalid",
    "materialization_failed",
    "post_commit_validation_failed",
]
GraphApplyFailurePhase = Literal[
    "none",
    "replay_validation",
    "fresh_preflight",
    "materialization",
    "changed_path_verification",
    "git_commit",
    "post_commit_validation",
]
_PLAN_ID_RE = re.compile(r"^GDP-[0-9a-f]{64}$")
_GIT_OBJECT_ID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_COMMIT_STAGE_HOOK_NAMES = (
    "pre-commit",
    "prepare-commit-msg",
    "commit-msg",
    "post-commit",
)


class GraphApplyError(RuntimeError):
    """Base error for invalid inputs or an unsafe local repository boundary."""


class GraphApplyInputError(GraphApplyError):
    """Raised when caller-supplied reviewed authority violates the public API."""


class GraphApplyRepositoryError(GraphApplyError):
    """Raised when the target repository cannot prove safe local Git preconditions."""


class GraphApplyRollbackError(GraphApplyError):
    """Raised when a failed post-commit validation cannot be rolled back safely."""

    def __init__(
        self,
        message: str,
        *,
        pre_apply_head: str,
        failed_commit_sha: str,
        diagnostics: str,
    ) -> None:
        super().__init__(message)
        self.pre_apply_head = pre_apply_head
        self.failed_commit_sha = failed_commit_sha
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class GraphApplyValidationSummary:
    """Committed-state validation evidence for a successful fresh application."""

    head_commit: str
    graph_semantic_hash: str
    task_count: int
    parent_edge_count: int
    dependency_edge_count: int
    resource_group_count: int
    project_requirement_count: int
    task_schema_version: str
    decomposition_semantics: Literal["valid"]
    exact_reviewed_plan: bool
    clean_worktree: bool


@dataclass(frozen=True)
class GraphApplyResult:
    """Immutable outcome of one standalone local D1C application attempt."""

    status: GraphApplyStatus
    plan_id: str
    parent_task_id: str
    reason: str
    failure_phase: GraphApplyFailurePhase
    old_head: str
    current_head: str
    new_commit_sha: str | None
    failed_commit_sha: str | None
    committed_paths: tuple[str, ...]
    published_paths: tuple[str, ...]
    failed_authorities: tuple[str, ...]
    validation: GraphApplyValidationSummary | None


@dataclass(frozen=True)
class _StoredPlanAuthority:
    payload: dict[str, Any]
    canonical_json: str
    plan_id: str
    parent_task_id: str
    parent_before_revision: int
    parent_before_hash: str
    source_graph_semantic_hash: str
    proposed_graph_semantic_hash: str
    child_ids: tuple[str, ...]
    allocation: tuple[tuple[str, str], ...]
    proposed_children: tuple[dict[str, Any], ...]
    parent_after_summary: dict[str, Any]
    inbound_dependency_changes: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class _ReplayInspection:
    status: Literal["already_applied", "fresh_source", "stale_or_partial"]
    reason: str
    failures: tuple[str, ...]


@dataclass(frozen=True)
class GraphApplyReplayInspection:
    """Read-only evidence describing whether one reviewed plan is in HEAD."""

    status: Literal["already_applied", "fresh_source", "stale_or_partial"]
    plan_id: str
    parent_task_id: str
    reason: str
    failures: tuple[str, ...]
    current_head: str


MaterializeOperation = Callable[
    [GraphApplyPlanResult, Path],
    GraphApplyMaterializationResult,
]
PostCommitValidator = Callable[
    [Path, GraphDeltaPlan, str],
    GraphApplyValidationSummary,
]
RollbackOperation = Callable[[Path, str, str], None]


def _bounded_detail(error: BaseException, limit: int = 700) -> str:
    detail = " ".join(str(error).split()) or type(error).__name__
    if len(detail) <= limit:
        return detail
    return detail[: limit - 3] + "..."


def _decode_output(raw: bytes, limit: int = 700) -> str:
    text = " ".join(raw.decode("utf-8", "replace").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _git(
    root: Path,
    *args: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    effective_environment = os.environ.copy()
    if environment is not None:
        effective_environment.update(environment)
    effective_environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        return subprocess.run(
            ("git", "-C", str(root), *args),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=effective_environment,
        )
    except OSError as exc:
        raise GraphApplyRepositoryError(
            f"Unable to execute local Git command {args[0]!r}: {_bounded_detail(exc)}"
        ) from exc


def _require_git(
    root: Path,
    *args: str,
    environment: dict[str, str] | None = None,
) -> bytes:
    result = _git(root, *args, environment=environment)
    if result.returncode != 0:
        raise GraphApplyRepositoryError(
            f"Local Git command {args[0]!r} failed with exit {result.returncode}: "
            f"{_decode_output(result.stderr)}"
        )
    return result.stdout


def _git_text(root: Path, *args: str) -> str:
    return _require_git(root, *args).decode("utf-8", "replace").strip()


def _require_sha256(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GraphApplyInputError(f"{label} must be lowercase SHA-256.")
    return value


def _require_expected_head(value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _GIT_OBJECT_ID_RE.fullmatch(value) is None:
        raise GraphApplyInputError(
            "expected_head must be a full lowercase Git SHA-1 or SHA-256 object ID."
        )
    return value


def _require_task_id(value: Any, label: str) -> str:
    if type(value) is not str or NSC_ID_RE.fullmatch(value) is None:
        raise GraphApplyInputError(f"{label} must be an NSC task ID.")
    return value


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise GraphApplyInputError(f"{label} must be a JSON object.")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise GraphApplyInputError(f"{label} must be a JSON list.")
    return value


def _stored_authority(
    stored_graph_delta: GraphDeltaPlan,
    original_parent_selector: Any,
) -> _StoredPlanAuthority:
    if type(stored_graph_delta) is not GraphDeltaPlan:
        raise GraphApplyInputError(
            "stored_graph_delta must be an exact immutable GraphDeltaPlan review snapshot."
        )
    try:
        payload = stored_graph_delta.to_dict()
        canonical_json = stored_graph_delta.canonical_json()
        normalized = GraphDeltaPlan.from_payload(payload).canonical_json()
    except (AttributeError, GraphDeltaPlanningError, TypeError, ValueError) as exc:
        raise GraphApplyInputError(
            "Stored reviewed GraphDeltaPlan is corrupt or truncated: "
            f"{_bounded_detail(exc)}"
        ) from exc
    if type(payload) is not dict or type(canonical_json) is not str or not canonical_json:
        raise GraphApplyInputError(
            "Stored reviewed GraphDeltaPlan must serialize as one canonical JSON object."
        )
    if canonical_json != normalized:
        raise GraphApplyInputError(
            "Stored reviewed GraphDeltaPlan serialization is not canonical JSON."
        )

    plan_id = payload.get("plan_id")
    if type(plan_id) is not str or _PLAN_ID_RE.fullmatch(plan_id) is None:
        raise GraphApplyInputError(
            "stored_graph_delta.plan_id must be a deterministic GDP SHA-256 identity."
        )
    parent_before = _require_object(
        payload.get("parent_before_summary"),
        "stored_graph_delta.parent_before_summary",
    )
    parent_after = _require_object(
        payload.get("parent_after_summary"),
        "stored_graph_delta.parent_after_summary",
    )
    parent_id = _require_task_id(
        parent_before.get("task_id"),
        "stored_graph_delta.parent_before_summary.task_id",
    )
    if parent_after.get("task_id") != parent_id:
        raise GraphApplyInputError(
            "Stored reviewed GraphDeltaPlan before/after parent identities differ."
        )
    parent_revision = parent_before.get("contract_revision")
    if type(parent_revision) is not int or parent_revision < 1:
        raise GraphApplyInputError(
            "stored_graph_delta.parent_before_summary.contract_revision must be positive."
        )
    parent_hash = _require_sha256(
        payload.get("parent_before_hash"),
        "stored_graph_delta.parent_before_hash",
    )
    source_hash = _require_sha256(
        payload.get("source_graph_semantic_hash"),
        "stored_graph_delta.source_graph_semantic_hash",
    )
    proposed_hash = _require_sha256(
        payload.get("proposed_graph_semantic_hash"),
        "stored_graph_delta.proposed_graph_semantic_hash",
    )

    try:
        selector = _identity_dict(original_parent_selector, "original_parent_selector")
    except GraphDeltaPlanningError as exc:
        raise GraphApplyInputError(str(exc)) from exc
    expected_selector = {
        "task_id": parent_id,
        "contract_revision": parent_revision,
        "contract_sha256": parent_hash,
    }
    if selector != expected_selector:
        differences = [
            field
            for field in ("task_id", "contract_revision", "contract_sha256")
            if selector[field] != expected_selector[field]
        ]
        raise GraphApplyInputError(
            "original_parent_selector must be the exact planning-time selector stored "
            "in the independently reviewed GraphDeltaPlan; changed fields: "
            f"{differences}."
        )

    allocation_value = _require_object(
        payload.get("allocated_local_key_to_task_id"),
        "stored_graph_delta.allocated_local_key_to_task_id",
    )
    if not allocation_value:
        raise GraphApplyInputError(
            "Stored reviewed GraphDeltaPlan must allocate at least one child."
        )
    allocation: list[tuple[str, str]] = []
    for local_key, child_value in allocation_value.items():
        if type(local_key) is not str or not local_key.strip():
            raise GraphApplyInputError("Stored child allocation contains a blank local key.")
        child_id = _require_task_id(child_value, f"child allocation {local_key!r}")
        allocation.append((local_key, child_id))
    child_ids = tuple(child_id for _, child_id in allocation)
    if len(child_ids) != len(set(child_ids)):
        raise GraphApplyInputError("Stored reviewed GraphDeltaPlan allocates duplicate child IDs.")

    proposed_values = _require_list(
        payload.get("proposed_child_contracts"),
        "stored_graph_delta.proposed_child_contracts",
    )
    proposed_by_id: dict[str, dict[str, Any]] = {}
    for index, child_value in enumerate(proposed_values):
        child = _require_object(
            child_value,
            f"stored_graph_delta.proposed_child_contracts[{index}]",
        )
        child_id = _require_task_id(
            child.get("id"),
            f"stored_graph_delta.proposed_child_contracts[{index}].id",
        )
        if child_id in proposed_by_id:
            raise GraphApplyInputError(
                f"Stored reviewed GraphDeltaPlan repeats proposed child {child_id}."
            )
        proposed_by_id[child_id] = child
    if set(proposed_by_id) != set(child_ids):
        raise GraphApplyInputError(
            "Stored reviewed GraphDeltaPlan allocation and proposed-child IDs differ."
        )
    for local_key, child_id in allocation:
        child = proposed_by_id[child_id]
        provenance = _require_object(
            child.get("provenance"),
            f"stored proposed child {child_id}.provenance",
        )
        if (
            child.get("reconciliation_key") != local_key
            or child.get("parent") != parent_id
            or provenance.get("graph_delta_plan_id") != plan_id
            or provenance.get("parent_task_id") != parent_id
            or provenance.get("parent_contract_revision") != parent_revision
            or provenance.get("parent_contract_sha256") != parent_hash
        ):
            raise GraphApplyInputError(
                f"Stored proposed child {child_id} is not bound to the reviewed plan, "
                "allocation, and planning-time parent identity."
            )

    after_children = _require_list(
        parent_after.get("decomposition_children"),
        "stored_graph_delta.parent_after_summary.decomposition_children",
    )
    if not set(child_ids).issubset(after_children):
        raise GraphApplyInputError(
            "Stored parent-after summary does not include every allocated plan child."
        )
    inbound_values = _require_list(
        payload.get("inbound_dependency_changes"),
        "stored_graph_delta.inbound_dependency_changes",
    )
    inbound_changes: list[dict[str, Any]] = []
    seen_dependents: set[str] = set()
    for index, change_value in enumerate(inbound_values):
        change = _require_object(
            change_value,
            f"stored_graph_delta.inbound_dependency_changes[{index}]",
        )
        dependent_id = _require_task_id(
            change.get("dependent_task_id"),
            f"stored inbound change {index}.dependent_task_id",
        )
        if dependent_id in seen_dependents:
            raise GraphApplyInputError(
                f"Stored reviewed GraphDeltaPlan repeats dependent {dependent_id}."
            )
        seen_dependents.add(dependent_id)
        _require_list(change.get("after_dependencies"), f"{dependent_id}.after_dependencies")
        replacement_ids = _require_list(
            change.get("replacement_task_ids"),
            f"{dependent_id}.replacement_task_ids",
        )
        if not replacement_ids or any(value not in child_ids for value in replacement_ids):
            raise GraphApplyInputError(
                f"Stored inbound rewrite for {dependent_id} has invalid replacement children."
            )
        inbound_changes.append(change)

    return _StoredPlanAuthority(
        payload=payload,
        canonical_json=canonical_json,
        plan_id=plan_id,
        parent_task_id=parent_id,
        parent_before_revision=parent_revision,
        parent_before_hash=parent_hash,
        source_graph_semantic_hash=source_hash,
        proposed_graph_semantic_hash=proposed_hash,
        child_ids=child_ids,
        allocation=tuple(allocation),
        proposed_children=tuple(proposed_by_id[child_id] for child_id in child_ids),
        parent_after_summary=parent_after,
        inbound_dependency_changes=tuple(inbound_changes),
    )


def _effective_hooks_directory(root: Path) -> Path:
    raw = _require_git(root, "rev-parse", "--git-path", "hooks")
    try:
        value = raw.decode("utf-8", "surrogateescape").strip()
    except UnicodeError as exc:
        raise GraphApplyRepositoryError(
            f"Effective Git hooks path is not decodable: {_bounded_detail(exc)}"
        ) from exc
    if not value or "\x00" in value or "\n" in value or "\r" in value:
        raise GraphApplyRepositoryError(
            "Effective Git hooks path is blank or contains unsafe control characters."
        )
    hooks = Path(value)
    if not hooks.is_absolute():
        hooks = root / hooks
    return hooks.resolve()


def _require_no_commit_stage_hooks(root: Path) -> None:
    hooks_directory = _effective_hooks_directory(root)
    executable_hooks = tuple(
        hooks_directory / name
        for name in _COMMIT_STAGE_HOOK_NAMES
        if (hooks_directory / name).is_file()
        and os.access(hooks_directory / name, os.X_OK)
    )
    if executable_hooks:
        details = ", ".join(
            f"{path.name} ({path})" for path in executable_hooks
        )
        raise GraphApplyRepositoryError(
            "Target repository has executable commit-stage Git hook(s); standalone "
            f"D1C refuses to bypass operator/repository policy: {details}."
        )


def _repository_preflight(target_root: Path) -> tuple[Path, str]:
    root = Path(target_root).resolve()
    if not root.is_dir():
        raise GraphApplyRepositoryError(
            f"target_root must be an existing local Git repository directory: {root}"
        )
    try:
        identity = capture_clean_source(root)
    except DecompositionPreflightError as exc:
        raise GraphApplyRepositoryError(
            f"Target repository precondition failed: {_bounded_detail(exc)}"
        ) from exc
    if identity.root != root:
        raise GraphApplyRepositoryError(
            "target_root must be the exact local Git repository root, not a subdirectory."
        )
    if not identity.branch:
        raise GraphApplyRepositoryError(
            "Target repository must have an attached branch; detached HEAD is unsafe for "
            "the local commit/rollback boundary."
        )
    index = _git(root, "diff", "--cached", "--quiet", "--exit-code", "HEAD", "--")
    if index.returncode == 1:
        raise GraphApplyRepositoryError(
            "Target repository index must be empty before graph application."
        )
    if index.returncode != 0:
        raise GraphApplyRepositoryError(
            "Target repository index state could not be read: "
            f"{_decode_output(index.stderr)}"
        )
    try:
        _approved_identity()
    except GitIdentityGuardError as exc:
        raise GraphApplyRepositoryError(
            f"Approved automation Git identity is unavailable: {_bounded_detail(exc)}"
        ) from exc
    _require_no_commit_stage_hooks(root)
    return root, identity.head


def _approved_identity() -> tuple[str, str]:
    name, email = validated_agent_git_identity()
    if name != DEFAULT_AGENT_GIT_NAME or email != DEFAULT_AGENT_GIT_EMAIL:
        raise GitIdentityGuardError(
            "Standalone D1C commits require the exact repository-approved automation "
            f"identity {DEFAULT_AGENT_GIT_NAME} <{DEFAULT_AGENT_GIT_EMAIL}>."
        )
    return name, email


def _task_map(graph: PersistentWorkGraph) -> dict[str, dict[str, Any]]:
    return {task["id"]: task for task in graph.plan.tasks}


def _exact_application_failures(
    graph: PersistentWorkGraph,
    authority: _StoredPlanAuthority,
) -> tuple[str, ...]:
    failures: list[str] = []
    tasks = _task_map(graph)
    parent = tasks.get(authority.parent_task_id)
    if parent is None:
        failures.append(f"parent {authority.parent_task_id} is missing")
    else:
        expected_parent = authority.parent_after_summary
        for field in (
            "kind",
            "contract_disposition",
            "execution_scope",
            "decomposition_state",
            "decomposition_requirement_sha256",
        ):
            if parent.get(field) != expected_parent.get(field):
                failures.append(
                    f"parent {authority.parent_task_id}.{field} does not match the reviewed plan"
                )
        current_children = parent.get("decomposition_children")
        if type(current_children) is not list:
            failures.append(
                f"parent {authority.parent_task_id}.decomposition_children is not a list"
            )
        else:
            missing = sorted(set(authority.child_ids) - set(current_children))
            if missing:
                failures.append(
                    f"parent {authority.parent_task_id} omits reviewed plan children {missing}"
                )

    proposed_by_id = {child["id"]: child for child in authority.proposed_children}
    for local_key, child_id in authority.allocation:
        child = tasks.get(child_id)
        if child is None:
            failures.append(f"reviewed plan child {child_id} is missing")
            continue
        expected_child = proposed_by_id[child_id]
        if child.get("parent") != authority.parent_task_id:
            failures.append(
                f"reviewed plan child {child_id} has the wrong direct parent"
            )
        if child.get("reconciliation_key") != local_key:
            failures.append(
                f"reviewed plan child {child_id} has the wrong reconciliation key"
            )
        if graph.plan.id_map.get(local_key) != child_id:
            failures.append(
                f"work ID map does not bind {local_key!r} to reviewed child {child_id}"
            )
        provenance = child.get("provenance")
        expected_provenance = expected_child.get("provenance")
        if type(provenance) is not dict or type(expected_provenance) is not dict:
            failures.append(f"reviewed plan child {child_id} has invalid provenance")
            continue
        for field in (
            "origin",
            "parent_task_id",
            "parent_contract_revision",
            "parent_contract_sha256",
            "graph_delta_plan_id",
        ):
            if provenance.get(field) != expected_provenance.get(field):
                failures.append(
                    f"reviewed plan child {child_id} provenance.{field} differs"
                )

    for change in authority.inbound_dependency_changes:
        dependent_id = change["dependent_task_id"]
        dependent = tasks.get(dependent_id)
        if dependent is None:
            failures.append(f"reviewed rewritten dependent {dependent_id} is missing")
            continue
        if dependent.get("contract_disposition") != "active":
            continue
        dependencies = dependent.get("depends_on")
        if type(dependencies) is not list:
            failures.append(f"active dependent {dependent_id}.depends_on is invalid")
            continue
        if authority.parent_task_id in dependencies:
            failures.append(
                f"active dependent {dependent_id} still points at aggregate parent "
                f"{authority.parent_task_id}"
            )
        missing_replacements = sorted(
            set(change["replacement_task_ids"]) - set(dependencies)
        )
        if missing_replacements:
            failures.append(
                f"active dependent {dependent_id} omits reviewed replacement children "
                f"{missing_replacements}"
            )
    return tuple(failures)


def _inspect_replay(
    graph: PersistentWorkGraph,
    authority: _StoredPlanAuthority,
) -> _ReplayInspection:
    # Idempotency deliberately does not require the current whole-graph hash to
    # equal this plan's proposed hash. Unrelated, later graph evolution is valid;
    # this replay check instead requires exact provenance and parent/rewrite facts
    # for every child created by this reviewed plan.
    failures = _exact_application_failures(graph, authority)
    if not failures:
        return _ReplayInspection(
            status="already_applied",
            reason=(
                "The current committed graph fully validates and positively represents "
                "the exact stored reviewed plan and its child provenance."
            ),
            failures=(),
        )

    graph_hash = semantic_json_sha256(_plan_payload(graph.plan))
    parent = _task_map(graph).get(authority.parent_task_id)
    parent_hash = semantic_json_sha256(parent) if parent is not None else None
    if (
        graph_hash == authority.source_graph_semantic_hash
        and parent_hash == authority.parent_before_hash
        and parent is not None
        and parent.get("contract_revision") == authority.parent_before_revision
    ):
        return _ReplayInspection(
            status="fresh_source",
            reason=(
                "The exact reviewed plan is not applied and the current committed graph "
                "is the original planning-time source."
            ),
            failures=failures,
        )
    return _ReplayInspection(
        status="stale_or_partial",
        reason=(
            "The current committed graph is neither the original reviewed source nor a "
            "complete exact application of the stored plan: "
            + "; ".join(failures)
            + "."
        ),
        failures=failures,
    )


def inspect_graph_delta_replay(
    target_root: Path,
    original_parent_selector: Any,
    stored_graph_delta: GraphDeltaPlan,
    *,
    expected_head: str | None = None,
) -> GraphApplyReplayInspection:
    """Inspect exact reviewed-plan presence without materializing or committing.

    The repository and stored authority receive the same clean-source and
    exact-plan validation used by D1C. Unlike :func:`apply_graph_delta`, this
    function never consults commit identity, hooks, or any mutation seam and
    cannot advance Git state.
    """

    asserted_head = _require_expected_head(expected_head)
    root = Path(target_root).resolve()
    if not root.is_dir():
        raise GraphApplyRepositoryError(
            "target_root must be an existing local Git repository directory: "
            f"{root}"
        )
    try:
        identity = capture_clean_source(root)
    except DecompositionPreflightError as exc:
        raise GraphApplyRepositoryError(
            f"Target repository precondition failed: {_bounded_detail(exc)}"
        ) from exc
    if identity.root != root:
        raise GraphApplyRepositoryError(
            "target_root must be the exact local Git repository root, not a subdirectory."
        )
    if asserted_head is not None and identity.head != asserted_head:
        raise GraphApplyRepositoryError(
            "Target repository HEAD does not match caller-observed expected_head "
            f"(expected={asserted_head}, actual={identity.head})."
        )
    authority = _stored_authority(stored_graph_delta, original_parent_selector)
    try:
        graph = load_persistent_work_graph(root)
    except Exception as exc:
        raise GraphApplyRepositoryError(
            "Current committed graph failed full persistent replay validation: "
            f"{_bounded_detail(exc)}"
        ) from exc
    _require_same_clean_head(root, identity.head)
    replay = _inspect_replay(graph, authority)
    return GraphApplyReplayInspection(
        status=replay.status,
        plan_id=authority.plan_id,
        parent_task_id=authority.parent_task_id,
        reason=replay.reason,
        failures=replay.failures,
        current_head=identity.head,
    )


def _empty_result(
    *,
    status: GraphApplyStatus,
    authority: _StoredPlanAuthority,
    reason: str,
    failure_phase: GraphApplyFailurePhase,
    old_head: str,
    current_head: str,
    failed_authorities: tuple[str, ...] = (),
    published_paths: tuple[str, ...] = (),
    failed_commit_sha: str | None = None,
) -> GraphApplyResult:
    return GraphApplyResult(
        status=status,
        plan_id=authority.plan_id,
        parent_task_id=authority.parent_task_id,
        reason=reason,
        failure_phase=failure_phase,
        old_head=old_head,
        current_head=current_head,
        new_commit_sha=None,
        failed_commit_sha=failed_commit_sha,
        committed_paths=(),
        published_paths=published_paths,
        failed_authorities=failed_authorities,
        validation=None,
    )


def _require_same_clean_head(root: Path, expected_head: str) -> None:
    current = _git_text(root, "rev-parse", "--verify", "HEAD")
    if current != expected_head:
        raise GraphApplyRepositoryError(
            f"Target repository HEAD changed during preflight: {expected_head} -> {current}."
        )
    status = _require_git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if status:
        raise GraphApplyRepositoryError(
            "Target repository changed during preflight and is no longer completely clean."
        )
    index = _git(root, "diff", "--cached", "--quiet", "--exit-code", "HEAD", "--")
    if index.returncode != 0:
        raise GraphApplyRepositoryError(
            "Target repository index changed during preflight or could not be read."
        )


def _nul_paths(raw: bytes, label: str) -> tuple[str, ...]:
    paths: list[str] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        path = item.decode("utf-8", "surrogateescape")
        if not path or path.startswith("/") or "\\" in path:
            raise GraphApplyRepositoryError(f"{label} returned an unsafe path: {path!r}.")
        paths.append(path)
    return tuple(paths)


def _working_tree_paths(root: Path) -> tuple[str, ...]:
    _require_git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    tracked = _nul_paths(
        _require_git(root, "diff", "--name-only", "-z", "--no-renames", "HEAD", "--"),
        "git diff",
    )
    untracked = _nul_paths(
        _require_git(root, "ls-files", "--others", "--exclude-standard", "-z", "--"),
        "git ls-files",
    )
    return tuple(sorted(set((*tracked, *untracked))))


def _expected_changed_paths(
    materialized: GraphApplyMaterializationResult,
) -> tuple[str, ...]:
    paths = materialized.changed_paths
    if not paths or len(paths) != len(set(paths)):
        raise GraphApplyRepositoryError(
            "Slice 2 returned an empty or duplicate changed-path set."
        )
    for path in paths:
        candidate = Path(path)
        if (
            type(path) is not str
            or not path
            or candidate.is_absolute()
            or candidate.as_posix() != path
            or ".." in candidate.parts
        ):
            raise GraphApplyRepositoryError(
                f"Slice 2 returned an unsafe changed path: {path!r}."
            )
    return paths


def _stage_and_check(root: Path, expected_paths: tuple[str, ...]) -> None:
    actual_paths = _working_tree_paths(root)
    if set(actual_paths) != set(expected_paths):
        raise GraphApplyRepositoryError(
            "Materialized working-tree paths differ from the exact Slice 2 change set "
            f"(actual={list(actual_paths)}, expected={list(expected_paths)})."
        )
    _require_git(root, "add", "--", *expected_paths)
    staged = _nul_paths(
        _require_git(
            root,
            "diff",
            "--cached",
            "--name-only",
            "-z",
            "--no-renames",
            "HEAD",
            "--",
        ),
        "git diff --cached",
    )
    if set(staged) != set(expected_paths):
        raise GraphApplyRepositoryError(
            "Staged paths differ from the exact D1C change set "
            f"(staged={list(staged)}, expected={list(expected_paths)})."
        )
    unstaged = _require_git(root, "diff", "--name-only", "-z", "--no-renames", "--")
    untracked = _require_git(root, "ls-files", "--others", "--exclude-standard", "-z", "--")
    if unstaged or untracked:
        raise GraphApplyRepositoryError(
            "The working tree contains unstaged or untracked paths after exact staging."
        )
    check = _git(root, "diff", "--cached", "--check")
    if check.returncode != 0:
        raise GraphApplyRepositoryError(
            "git diff --cached --check rejected the exact staged graph change: "
            f"{_decode_output(check.stdout + b' ' + check.stderr)}"
        )


def _commit_message(authority: _StoredPlanAuthority) -> str:
    return f"taskgraph: apply {authority.parent_task_id} decomposition {authority.plan_id}"


def _create_commit(
    root: Path,
    authority: _StoredPlanAuthority,
) -> subprocess.CompletedProcess[bytes]:
    # Re-resolve effective repository/operator policy immediately before commit.
    # Once absence is proven, neutralizing the empty hook boundary keeps the
    # deterministic automation commit isolated from a concurrent ambient config.
    _require_no_commit_stage_hooks(root)
    name, email = _approved_identity()
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        }
    )
    with tempfile.TemporaryDirectory(prefix="nsc-d1c-empty-hooks-") as hooks:
        return _git(
            root,
            "-c",
            f"user.name={name}",
            "-c",
            f"user.email={email}",
            "-c",
            "commit.gpgSign=false",
            "-c",
            f"core.hooksPath={hooks}",
            "commit",
            "--no-verify",
            "--no-gpg-sign",
            "-m",
            _commit_message(authority),
            environment=environment,
        )


def _verify_commit_boundary(
    root: Path,
    old_head: str,
    new_commit: str,
    expected_paths: tuple[str, ...],
) -> None:
    if new_commit == old_head:
        raise GraphApplyRepositoryError("git commit did not move HEAD.")
    parent = _git_text(root, "rev-parse", f"{new_commit}^")
    if parent != old_head:
        raise GraphApplyRepositoryError(
            "The D1C commit is not exactly one commit whose parent is pre-apply HEAD."
        )
    count = _git_text(root, "rev-list", "--count", f"{old_head}..{new_commit}")
    if count != "1":
        raise GraphApplyRepositoryError(
            f"The D1C boundary created {count!r} commits instead of exactly one."
        )
    committed = _nul_paths(
        _require_git(
            root,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "-z",
            "--no-renames",
            new_commit,
        ),
        "git diff-tree",
    )
    if set(committed) != set(expected_paths):
        raise GraphApplyRepositoryError(
            "The D1C commit paths differ from the exact materialized path set "
            f"(committed={list(committed)}, expected={list(expected_paths)})."
        )


def _require_clean_committed_head(root: Path, expected_head: str) -> None:
    current_head = _git_text(root, "rev-parse", "--verify", "HEAD")
    if current_head != expected_head:
        raise GraphApplyRepositoryError(
            f"Committed validation expected HEAD {expected_head}, got {current_head}."
        )
    status = _require_git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if status:
        raise GraphApplyRepositoryError(
            "Repository is not clean at the committed-state validation boundary."
        )
    index = _git(root, "diff", "--cached", "--quiet", "--exit-code", "HEAD", "--")
    if index.returncode != 0:
        raise GraphApplyRepositoryError(
            "Repository index is not empty at the committed-state validation boundary."
        )


def _validate_committed_graph(
    root: Path,
    stored_graph_delta: GraphDeltaPlan,
    expected_commit: str,
) -> GraphApplyValidationSummary:
    # This selector reconstruction is an INTERNAL committed-state verification
    # detail only. The caller's original reviewed selector authority was already
    # established by _stored_authority before any replay or mutation.
    authority = _stored_authority(
        stored_graph_delta,
        {
            "task_id": stored_graph_delta.to_dict()["parent_before_summary"]["task_id"],
            "contract_revision": stored_graph_delta.to_dict()["parent_before_summary"][
                "contract_revision"
            ],
            "contract_sha256": stored_graph_delta.to_dict()["parent_before_hash"],
        },
    )
    _require_clean_committed_head(root, expected_commit)
    graph = load_persistent_work_graph(root)
    summary = validate_work_graph_plan(graph.plan)
    validate_decomposition_graph_semantics(graph.plan)
    failures = _exact_application_failures(graph, authority)
    if failures:
        raise GraphApplyRepositoryError(
            "Committed graph does not represent the exact reviewed plan: "
            + "; ".join(failures)
            + "."
        )
    graph_hash = semantic_json_sha256(_plan_payload(graph.plan))
    if graph_hash != authority.proposed_graph_semantic_hash:
        raise GraphApplyRepositoryError(
            "Committed graph semantic hash differs from the exact reviewed plan overlay."
        )
    _require_clean_committed_head(root, expected_commit)
    return GraphApplyValidationSummary(
        head_commit=expected_commit,
        graph_semantic_hash=graph_hash,
        task_count=summary.task_count,
        parent_edge_count=summary.parent_edge_count,
        dependency_edge_count=summary.dependency_edge_count,
        resource_group_count=summary.resource_group_count,
        project_requirement_count=summary.project_requirement_count,
        task_schema_version=summary.task_schema_version,
        decomposition_semantics="valid",
        exact_reviewed_plan=True,
        clean_worktree=True,
    )


def _require_authoritative_validation_summary(
    validation: Any,
    authority: _StoredPlanAuthority,
    actual_commit: str,
) -> GraphApplyValidationSummary:
    if type(validation) is not GraphApplyValidationSummary:
        raise GraphApplyRepositoryError(
            "Post-commit validator returned an invalid summary type."
        )
    contradictions: list[str] = []
    if validation.head_commit != actual_commit:
        contradictions.append(
            f"head_commit={validation.head_commit!r} (expected {actual_commit})"
        )
    if validation.graph_semantic_hash != authority.proposed_graph_semantic_hash:
        contradictions.append(
            "graph_semantic_hash does not match the reviewed proposed graph"
        )
    if validation.decomposition_semantics != "valid":
        contradictions.append(
            f"decomposition_semantics={validation.decomposition_semantics!r}"
        )
    if validation.exact_reviewed_plan is not True:
        contradictions.append(
            f"exact_reviewed_plan={validation.exact_reviewed_plan!r}"
        )
    if validation.clean_worktree is not True:
        contradictions.append(f"clean_worktree={validation.clean_worktree!r}")
    if contradictions:
        raise GraphApplyRepositoryError(
            "Post-commit validation summary contradicts required D1C authority: "
            + "; ".join(contradictions)
            + "."
        )
    return validation


def _rollback_failed_commit(root: Path, old_head: str, failed_commit: str) -> None:
    current = _git_text(root, "rev-parse", "--verify", "HEAD")
    if current != failed_commit:
        raise GraphApplyRepositoryError(
            "Rollback refused because HEAD no longer names the failed D1C commit "
            f"(expected={failed_commit}, actual={current})."
        )
    status = _require_git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if status:
        raise GraphApplyRepositoryError(
            "Destructive rollback refused because the failed D1C commit checkout "
            f"contains concurrent index/worktree changes: {_decode_output(status)}"
        )
    _require_git(root, "reset", "--hard", old_head)
    _require_clean_committed_head(root, old_head)


def _rollback_diagnostics(root: Path) -> str:
    parts: list[str] = []
    for label, args in (
        ("HEAD", ("rev-parse", "--verify", "HEAD")),
        ("status", ("status", "--short", "--untracked-files=all")),
        ("index", ("diff", "--cached", "--name-only")),
    ):
        try:
            result = _git(root, *args)
            parts.append(
                f"{label}(exit={result.returncode})="
                f"{_decode_output(result.stdout + b' ' + result.stderr, 300)!r}"
            )
        except GraphApplyRepositoryError as exc:
            parts.append(f"{label}=unavailable({_bounded_detail(exc, 200)})")
    return "; ".join(parts)


def _perform_rollback(
    operation: RollbackOperation,
    root: Path,
    old_head: str,
    failed_commit: str,
    validation_error: BaseException,
) -> None:
    try:
        current = _git_text(root, "rev-parse", "--verify", "HEAD")
        if current != failed_commit:
            raise GraphApplyRepositoryError(
                "Destructive rollback refused because HEAD no longer names the failed "
                f"D1C commit (expected={failed_commit}, actual={current})."
            )
        status = _require_git(
            root,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        )
        if status:
            raise GraphApplyRepositoryError(
                "Destructive rollback refused because authoritative Git status contains "
                f"concurrent index/worktree changes: {_decode_output(status)}"
            )
        operation(root, old_head, failed_commit)
    except Exception as rollback_error:
        diagnostics = _rollback_diagnostics(root)
        raise GraphApplyRollbackError(
            "SEVERE: post-commit validation failed and local rollback did not complete; "
            f"pre-apply HEAD={old_head}, failed commit={failed_commit}, "
            f"validation={_bounded_detail(validation_error)}, "
            f"rollback={_bounded_detail(rollback_error)}, diagnostics={diagnostics}",
            pre_apply_head=old_head,
            failed_commit_sha=failed_commit,
            diagnostics=diagnostics,
        ) from rollback_error
    try:
        _require_clean_committed_head(root, old_head)
    except Exception as verification_error:
        diagnostics = _rollback_diagnostics(root)
        raise GraphApplyRollbackError(
            "SEVERE: rollback operation returned without restoring the exact clean "
            "pre-apply committed state; "
            f"pre-apply HEAD={old_head}, failed commit={failed_commit}, "
            f"verification={_bounded_detail(verification_error)}, "
            f"diagnostics={diagnostics}",
            pre_apply_head=old_head,
            failed_commit_sha=failed_commit,
            diagnostics=diagnostics,
        ) from verification_error


def apply_graph_delta(
    target_root: Path,
    original_parent_selector: Any,
    decomposition_result: Any,
    stored_graph_delta: GraphDeltaPlan,
    *,
    expected_head: str | None = None,
    materialize_operation: MaterializeOperation | None = None,
    post_commit_validator: PostCommitValidator | None = None,
    rollback_operation: RollbackOperation | None = None,
) -> GraphApplyResult:
    """Apply one exact independently reviewed/authorized plan and make one local commit.

    This is a network-free low-level primitive. The caller is responsible for proving
    that the exact immutable ``stored_graph_delta`` received independent review and
    external authorization. ``review_ready`` or the plan's review-only authority field
    is never interpreted here as permission. The caller must pass the ORIGINAL
    planning-time ``original_parent_selector``; a selector reconstructed from current
    HEAD is rejected and is never substituted.

    When ``expected_head`` is provided, it must name the exact full current HEAD;
    mismatch fails closed before idempotency assessment or materialization. Omission
    preserves standalone semantic-hash-based behavior.

    The keyword-only operation seams exist for deterministic disposable-repository
    failure injection. Production callers must use the defaults and must not use the
    seams to weaken materialization, committed validation, or rollback.
    """

    asserted_head = _require_expected_head(expected_head)
    root, old_head = _repository_preflight(Path(target_root))
    if asserted_head is not None and old_head != asserted_head:
        raise GraphApplyRepositoryError(
            "Target repository HEAD does not match caller-authorized expected_head "
            f"(expected={asserted_head}, actual={old_head})."
        )
    authority = _stored_authority(stored_graph_delta, original_parent_selector)
    materialize = materialize_operation or materialize_graph_apply
    validate_commit = post_commit_validator or _validate_committed_graph
    rollback = rollback_operation or _rollback_failed_commit

    try:
        current_graph = load_persistent_work_graph(root)
    except Exception as exc:
        return _empty_result(
            status="source_graph_invalid",
            authority=authority,
            reason=(
                "Current committed graph failed full persistent replay validation; "
                f"no fresh preflight or mutation ran: {_bounded_detail(exc)}"
            ),
            failure_phase="replay_validation",
            old_head=old_head,
            current_head=old_head,
        )
    _require_same_clean_head(root, old_head)
    replay = _inspect_replay(current_graph, authority)
    if replay.status == "already_applied":
        return GraphApplyResult(
            status="already_applied",
            plan_id=authority.plan_id,
            parent_task_id=authority.parent_task_id,
            reason=replay.reason,
            failure_phase="none",
            old_head=old_head,
            current_head=old_head,
            new_commit_sha=None,
            failed_commit_sha=None,
            committed_paths=(),
            published_paths=(),
            failed_authorities=(),
            validation=None,
        )
    if replay.status == "stale_or_partial":
        return _empty_result(
            status="stale_proposal",
            authority=authority,
            reason=replay.reason,
            failure_phase="fresh_preflight",
            old_head=old_head,
            current_head=old_head,
            failed_authorities=("exact_reviewed_plan_replay", "fresh_source_identity"),
        )

    try:
        slice1_result = plan_graph_apply(
            current_graph,
            original_parent_selector,
            decomposition_result,
            stored_graph_delta,
        )
    except GraphApplyPlanningError as exc:
        raise GraphApplyInputError(
            f"Slice 1 rejected caller authority: {_bounded_detail(exc)}"
        ) from exc
    if slice1_result.status != "fresh":
        return _empty_result(
            status=slice1_result.status,
            authority=authority,
            reason=slice1_result.reason,
            failure_phase="fresh_preflight",
            old_head=old_head,
            current_head=old_head,
            failed_authorities=tuple(slice1_result.failed_authorities),
        )

    _require_same_clean_head(root, old_head)
    try:
        materialized = materialize(slice1_result, root)
    except GraphApplyMaterializationError as exc:
        return _empty_result(
            status="materialization_failed",
            authority=authority,
            reason=str(exc),
            failure_phase="materialization",
            old_head=old_head,
            current_head=old_head,
            published_paths=tuple(exc.published_paths),
        )
    except Exception as exc:
        return _empty_result(
            status="materialization_failed",
            authority=authority,
            reason=f"Unexpected Slice 2 materialization failure: {_bounded_detail(exc)}",
            failure_phase="materialization",
            old_head=old_head,
            current_head=old_head,
        )
    if type(materialized) is not GraphApplyMaterializationResult:
        return _empty_result(
            status="materialization_failed",
            authority=authority,
            reason="Slice 2 returned an invalid materialization result type.",
            failure_phase="materialization",
            old_head=old_head,
            current_head=old_head,
        )
    if (
        materialized.status != "materialized"
        or materialized.plan_id != authority.plan_id
        or materialized.parent_task_id != authority.parent_task_id
    ):
        return _empty_result(
            status="materialization_failed",
            authority=authority,
            reason="Slice 2 returned inconsistent materialization identity.",
            failure_phase="materialization",
            old_head=old_head,
            current_head=old_head,
            published_paths=tuple(materialized.publication_order),
        )

    try:
        expected_paths = _expected_changed_paths(materialized)
        _stage_and_check(root, expected_paths)
    except GraphApplyRepositoryError as exc:
        return _empty_result(
            status="materialization_failed",
            authority=authority,
            reason=str(exc),
            failure_phase="changed_path_verification",
            old_head=old_head,
            current_head=old_head,
            published_paths=tuple(materialized.publication_order),
        )

    commit = _create_commit(root, authority)
    head_after_commit_attempt = _git_text(root, "rev-parse", "--verify", "HEAD")
    if commit.returncode != 0 and head_after_commit_attempt == old_head:
        return _empty_result(
            status="materialization_failed",
            authority=authority,
            reason=(
                f"Local git commit failed with exit {commit.returncode}; no commit was "
                f"created: {_decode_output(commit.stderr)}"
            ),
            failure_phase="git_commit",
            old_head=old_head,
            current_head=old_head,
            published_paths=tuple(materialized.publication_order),
        )

    failed_commit = head_after_commit_attempt
    try:
        if commit.returncode != 0:
            raise GraphApplyRepositoryError(
                f"git commit returned exit {commit.returncode} after HEAD moved: "
                f"{_decode_output(commit.stderr)}"
            )
        _verify_commit_boundary(root, old_head, failed_commit, expected_paths)
        validation = validate_commit(root, stored_graph_delta, failed_commit)
        validation = _require_authoritative_validation_summary(
            validation,
            authority,
            failed_commit,
        )
        if post_commit_validator is not None:
            authoritative_validation = _validate_committed_graph(
                root,
                stored_graph_delta,
                failed_commit,
            )
            if validation != authoritative_validation:
                raise GraphApplyRepositoryError(
                    "Injected post-commit validation summary differs from independent "
                    "default committed-graph verification."
                )
            validation = authoritative_validation
        _require_clean_committed_head(root, failed_commit)
    except Exception as validation_error:
        _perform_rollback(
            rollback,
            root,
            old_head,
            failed_commit,
            validation_error,
        )
        return _empty_result(
            status="post_commit_validation_failed",
            authority=authority,
            reason=(
                "The local D1C commit failed committed-state validation and was rolled "
                f"back exactly to {old_head}: {_bounded_detail(validation_error)}"
            ),
            failure_phase="post_commit_validation",
            old_head=old_head,
            current_head=old_head,
            failed_commit_sha=failed_commit,
        )

    return GraphApplyResult(
        status="applied",
        plan_id=authority.plan_id,
        parent_task_id=authority.parent_task_id,
        reason=(
            "The exact reviewed graph delta was materialized, committed once, and fully "
            "validated from the new committed HEAD."
        ),
        failure_phase="none",
        old_head=old_head,
        current_head=failed_commit,
        new_commit_sha=failed_commit,
        failed_commit_sha=None,
        committed_paths=expected_paths,
        published_paths=tuple(materialized.publication_order),
        failed_authorities=(),
        validation=validation,
    )


__all__ = [
    "GraphApplyError",
    "GraphApplyInputError",
    "GraphApplyRepositoryError",
    "GraphApplyReplayInspection",
    "GraphApplyResult",
    "GraphApplyRollbackError",
    "GraphApplyStatus",
    "GraphApplyValidationSummary",
    "apply_graph_delta",
    "inspect_graph_delta_replay",
]
