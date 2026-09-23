"""Durable, local admission for assistant-selected task workers.

Admission reserves capacity and repository resources. It never launches a
worker, and a caller must supply proof of terminal completion before release.
"""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from Pipeline.AssistantControl.dependencies import inspect_dependencies
from Pipeline.AssistantControl.inspect_project import git, unresolvable_commit
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan, validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
from Pipeline.TaskReviewAgent.pipeline_scope import RepositoryScopeAuthority

from .checkouts import Checkouts, write_record


REGISTRY_SCHEMA = "assistant-admission/v1"
_ACTIVE = "active"
DependencyReader = Callable[[Path, str, Path], Mapping[str, Any]]


def _source_registry_paths(source: Path) -> tuple[Path, Path]:
    # Deliberately keyed by --git-common-dir, not source itself: a Git
    # worktree of an already-admitted repository must share this file with
    # the repository's other worktrees, because exclusive resource claims
    # only prevent conflicts if every worktree of one repo reads and writes
    # the same registry.
    common = Path(git(source, "rev-parse", "--git-common-dir").decode().strip())
    if not common.is_absolute():
        common = source / common
    common = common.resolve()
    return common / "assistant-control-admission.lock", common / "assistant-control-admissions.json"


def _registry_identity(path: Path) -> str:
    """The registry's self-described identity: the shared repository root.

    ``path`` is ``<git-common-dir>/assistant-control-admissions.json``, so
    its grandparent directory is whatever repository owns that common Git
    dir. That grandparent is invariant across every worktree of one repo,
    since --git-common-dir already resolves every worktree to the same
    directory (see ``_source_registry_paths``) -- so two worktrees of one
    repo compute the same identity here even though their own
    ``--show-toplevel`` paths differ. For a plain, non-worktree checkout it
    is exactly that checkout's own toplevel, which is what every registry
    ever written (before this fix keyed identity on the caller's own
    ``source`` toplevel) already stored -- so this keeps old registries
    valid with no migration, while a worktree of an already-admitted repo
    no longer looks like a different, incompatible source.
    """
    return str(path.parent.parent)


def _read_registry(path: Path, source: Path) -> dict[str, Any]:
    identity = _registry_identity(path)
    if not path.is_file():
        return {"schema_version": REGISTRY_SCHEMA, "source": identity, "reservations": []}
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("assistant admission registry is unreadable") from exc
    if (not isinstance(registry, dict) or registry.get("schema_version") != REGISTRY_SCHEMA
            or registry.get("source") != identity or not isinstance(registry.get("reservations"), list)):
        raise ValueError("assistant admission registry identity or schema differs")
    if any(not isinstance(item, dict) or item.get("status") != _ACTIVE for item in registry["reservations"]):
        raise ValueError("assistant admission registry contains an invalid reservation")
    return registry


def _resource_path(value: str) -> str:
    text = value.strip().replace("\\", "/")
    if ":" in text:
        kind, path = text.split(":", 1)
        if kind in {"repo-file", "unity-scene"}:
            text = path
    text = text.strip("/")
    if not text or text in {".", ".."} or any(part in {"", ".", ".."} for part in PurePosixPath(text).parts):
        raise ValueError(f"invalid reservation resource path: {value!r}")
    return text.casefold()


def _overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _reservation_resources(task: Mapping[str, Any], scope: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for resource in task.get("exclusive_resources") or []:
        if not isinstance(resource, str) or not resource.strip():
            raise ValueError("active task contract has an invalid exclusive resource")
        values.append(_resource_path(resource))
    raw_plan = scope.get("plan")
    plan = ExecutionScopePlan.from_dict(raw_plan)
    for field in ("existing_implementation_paths", "new_implementation_paths",
                  "existing_test_paths", "new_test_paths"):
        values.extend(_resource_path(path) for path in getattr(plan, field))
    return sorted(set(values))


def _overlapping_resources(requested: list[str], owner: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    owned = owner.get("resources")
    if not isinstance(owned, list) or any(not isinstance(value, str) for value in owned):
        raise ValueError("active admission has invalid resources")
    return (
        sorted({left for left in requested for right in owned if _overlap(left, right)}),
        sorted({right for left in requested for right in owned if _overlap(left, right)}),
    )


def _parallel_checkout_overlap_allowed(
    checkouts: Checkouts, task_id: str, owner: Mapping[str, Any],
    requested_resources: list[str], owner_resources: list[str],
) -> bool:
    """Share only repository paths between distinct owned task checkouts.

    Typed logical locks retain their exclusive meaning. A reservation made
    through another checkout root cannot be opted into this local workflow.
    """
    owner_id = owner.get("task_id")
    try:
        validate_task_id(owner_id)
    except (TypeError, ValueError):
        return False
    return bool(
        owner_id != task_id
        and owner.get("source") == str(checkouts.source)
        and owner.get("checkout_root") == str(checkouts.root)
        and owner.get("checkout") == str(checkouts.root / owner_id)
        and all(":" not in path for path in requested_resources + owner_resources)
    )


def _clean_checkout(checkouts: Checkouts, record: Mapping[str, Any], source_head: str) -> Path:
    checkout = Path(record.get("checkout", ""))
    if (record.get("source") != str(checkouts.source) or record.get("checkout") != str(checkout)
            or checkout != checkouts.root / record.get("task_id", "")):
        raise ValueError("task checkout record identity differs")
    if checkout.resolve() != checkout or checkout.is_symlink():
        raise ValueError("task checkout was redirected")
    if Path(git(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve() != checkout:
        raise ValueError("task checkout is not an owned independent Git root")
    if git(checkout, "rev-parse", "HEAD").decode().strip() != source_head:
        raise ValueError("task checkout is not at current source HEAD")
    if git(checkout, "branch", "--show-current").decode().strip() != record.get("branch"):
        raise ValueError("task checkout branch changed")
    status = git(checkout, "status", "--porcelain=v1", "-z",
                 "--untracked-files=all", "--ignored=matching")
    if status:
        for entry in status.decode("utf-8", "surrogateescape").split("\0"):
            if not entry:
                continue
            if not entry.startswith("!! ") or not _allowed_ignored_checkout_path(
                    checkout, entry[3:]):
                raise ValueError("task checkout has local changes")
    return checkout


# Directories Unity and the build regenerate wholesale. A checkout Unity has
# opened always has these, so requiring their absence would refuse every task
# whose crew ever ran.
_GENERATED_CACHE_DIRECTORIES = frozenset(
    {"Library", "Temp", "Logs", "obj", "UserSettings"})

# Unity rewrites the solution and per-assembly project files beside Library/ and
# obj/ every time it opens a project. The repository's own .gitignore declares
# this exact family generated (*.csproj, *.unityproj, *.sln, *.slnx), and they
# are allowed ONLY as a single top-level entry: a .csproj deeper in the tree is
# not Unity's and stays a local change.
_GENERATED_IDE_PROJECT_SUFFIXES = frozenset(
    {".csproj", ".unityproj", ".sln", ".slnx"})


def _allowed_ignored_checkout_path(checkout: Path, value: str) -> bool:
    """Allow only owned generated caches and verified crew output files.

    Everything reaching here is already ignored by the repository's own rules --
    the caller asks Git for ``--ignored=matching`` -- so the question is which of
    the project's OWN generated artifacts an admission may tolerate, not whether
    to trust arbitrary untracked files.

    The list previously named Library, Temp, Logs and obj but not the .csproj,
    .sln and UserSettings/ siblings Unity writes in the same breath. That made
    the guard narrower than its own docstring: those ARE owned generated caches,
    and every checkout whose crew has run Unity carries them, so admission
    refused the whole class rather than a defect. Deleting them per task is not a
    remedy either -- the next Unity run recreates them.
    """
    relative = value.replace("\\", "/").strip().strip("/")
    parts = PurePosixPath(relative).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return False
    if not (parts[0] in _GENERATED_CACHE_DIRECTORIES
            or parts[:3] == ("Pipeline", "ExecutionCrew", "outputs")
            or (len(parts) == 1
                and PurePosixPath(parts[0]).suffix.casefold()
                in _GENERATED_IDE_PROJECT_SUFFIXES)):
        return False
    candidate = checkout.joinpath(*parts)
    checkout_resolved = checkout.resolve()
    try:
        if not candidate.resolve(strict=False).is_relative_to(checkout_resolved):
            return False
    except OSError:
        return False
    current = checkout
    for part in parts:
        current = current / part
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            return False
    return True


def _dependency_is_satisfied(result: Mapping[str, Any], task_id: str, source_head: str) -> None:
    if (result.get("task_id") != task_id or result.get("source_commit") != source_head
            or result.get("source_unchanged_during_read") is False
            or result.get("source_unchanged_during_read") is None
            or result.get("dependencies_satisfied") is not True):
        raise ValueError("dependency inspection did not establish a stable satisfied task")


def _executable_task(task: Mapping[str, Any]) -> None:
    if (task.get("kind") != "implementation"
            or task.get("execution_scope") != "single_agent"
            or task.get("decomposition_state") != "concrete"):
        raise ValueError("task contract is not an executable single-agent implementation")


def _validate_persisted_scope(checkouts: Checkouts, record: Mapping[str, Any],
                              task_id: str, checkout: Path, task: Mapping[str, Any]) -> dict[str, Any]:
    scope = record.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("admission requires a persisted accepted scope")
    lease_id = scope.get("lease_id")
    plan_id = scope.get("plan_id")
    if (type(lease_id) is not str or not lease_id.strip()
            or type(plan_id) is not str or not plan_id.strip()):
        raise ValueError("admission requires a persisted accepted scope")
    authority = RepositoryScopeAuthority(
        checkout=checkout, task=task, lease_id=lease_id,
        expected_branch=record["branch"],
        state_root=checkouts.records / ".scope-state",
    )
    try:
        accepted = authority.require(plan_id)
    except Exception as exc:
        raise ValueError("persisted execution scope is not currently valid") from exc
    if accepted.to_dict() != scope:
        raise ValueError("persisted execution scope differs from its verified authority")
    return scope


_SHA40 = re.compile(r"[0-9a-f]{40}")


def _reconciled_source_commit(checkouts: Checkouts, record: Mapping[str, Any],
                              entry: Mapping[str, Any], reconciled: str) -> str:
    """The Source commit a reconciliation merged.

    Entries written after this field was added record it outright. The first
    reconciliations predate it, so it is DERIVED from the merge -- and the
    derivation is verified rather than assumed: ``revise-on-source`` branches at
    the rejected candidate and merges Source, so the first parent must be the
    candidate the entry names. If it is not, this is not a merge that command
    made and nothing may be concluded from its parent order.
    """
    recorded = entry.get("inspected_source_commit")
    if isinstance(recorded, str) and _SHA40.fullmatch(recorded):
        return recorded
    checkout = Path(str(record.get("checkout", "")))
    unresolvable = unresolvable_commit(checkout, ("reconciled commit", reconciled))
    if unresolvable:
        raise ValueError(unresolvable)
    first = git(checkout, "rev-parse", f"{reconciled}^1").decode().strip()
    if first != entry.get("rejected_candidate"):
        raise ValueError(
            "the reconciled commit's first parent is not the rejected candidate, "
            "so its Source parent cannot be identified")
    return git(checkout, "rev-parse", f"{reconciled}^2").decode().strip()


def _revise_on_source_baseline(checkouts: Checkouts, record: Mapping[str, Any],
                               source_head: str) -> str | None:
    """Baseline for a record ``revise-on-source`` reconciled with Source.

    A reconciliation is a MERGE of the rejected candidate and Source, so BY
    CONSTRUCTION it can never equal Source HEAD. The ordinary path below demands
    ``record["source_commit"] == source_head``, which no reconciled record can
    ever satisfy -- not "is stale now" but "cannot become admissible", because
    ``refresh-prepared`` would move the checkout to Source and discard the
    reconciliation that is the entire point of the command.

    THE REVISION PATH'S FRESHNESS RULE IS DELIBERATELY NOT COPIED. It requires
    the rework decision to have been taken at current Source HEAD. But
    ``revise-on-source`` archives the rejected candidate and pops it, so it
    cannot be run a second time: copying that rule would make every
    reconciliation UNRECOVERABLE the moment ``main`` moved, and here ``main``
    moves every few minutes.

    What is required instead is that the reconciliation sits ON the main line
    rather than beside it -- the Source commit it merged must be an ancestor of
    current Source HEAD. A reconciliation MAY lag Source. It may not be built on
    a commit Source never had.
    """
    history = record.get("revise_on_source_history")
    if not isinstance(history, list) or not history:
        return None
    entry = history[-1]
    if not isinstance(entry, Mapping):
        raise ValueError("revise-on-source history is malformed")
    reconciled = entry.get("reconciled_commit")
    baseline = record.get("source_commit")
    if not isinstance(reconciled, str) or reconciled != baseline:
        # Something moved the record past this reconciliation. Guessing which
        # entry is current would be worse than declining to supply a baseline.
        return None
    if entry.get("accepted_contract_sha256") != record.get("task_contract_sha256"):
        raise ValueError("the reconciled contract is not the record's pinned contract")
    if record.get("candidate"):
        raise ValueError("a reconciled record must carry no candidate")
    merged = _reconciled_source_commit(checkouts, record, entry, reconciled)
    unresolvable = unresolvable_commit(
        checkouts.source, ("merged Source commit", merged), ("Source HEAD", source_head))
    if unresolvable:
        raise ValueError(unresolvable)
    try:
        git(checkouts.source, "merge-base", "--is-ancestor", merged, source_head)
    except RuntimeError as exc:
        raise ValueError(
            "the reconciliation was built on a Source commit that is not an "
            "ancestor of current Source HEAD") from exc
    return reconciled


def _revision_baseline(checkouts: Checkouts, record: Mapping[str, Any],
                       task_id: str, source_head: str) -> str | None:
    revision = record.get("revision")
    if not isinstance(revision, Mapping):
        return None
    baseline = record.get("source_commit")
    if (not isinstance(baseline, str) or revision.get("candidate_commit") != baseline
            or revision.get("source_commit") != source_head
            or revision.get("task_contract_sha256") != record.get("task_contract_sha256")):
        raise ValueError("revision source binding is stale or invalid")
    source_tree = git(checkouts.source, "rev-parse", "HEAD^{tree}").decode().strip()
    if revision.get("source_tree") != source_tree:
        raise ValueError("revision source tree changed")
    history = record.get("revision_history")
    index = revision.get("history_index")
    if (not isinstance(history, list) or type(index) is not int
            or not 0 <= index < len(history)):
        raise ValueError("revision history binding is invalid")
    archived = history[index]
    candidate = archived.get("candidate") if isinstance(archived, Mapping) else None
    review = (archived.get("revision_feedback") or archived.get("human_review")
              if isinstance(archived, Mapping) else None)
    if (not isinstance(archived, Mapping)
            or archived.get("task_id") != task_id
            or not isinstance(candidate, Mapping)
            or candidate.get("commit") != baseline
            or candidate.get("tree") != revision.get("candidate_tree")
            or archived.get("candidate_tree") != revision.get("candidate_tree")
            or archived.get("task_contract_sha256") != record.get("task_contract_sha256")
            or not isinstance(review, Mapping)
            or review.get("commit") != baseline
            or review.get("decision") != "reject"
            or revision.get("rejected_review") != dict(review)):
        raise ValueError("revision does not bind the exact rejected candidate history")
    mode = revision.get("feedback_mode", "legacy_retry")
    if candidate.get("kind") == "source_synchronized":
        if mode != "fresh":
            raise ValueError("synchronized revision requires fresh feedback")
        from Pipeline.AssistantControl.source_update import validate_synchronized_candidate
        archived_view = dict(record, candidate=dict(candidate),
                             candidate_lineage=archived.get("candidate_lineage", []))
        validate_synchronized_candidate(checkouts, archived_view, baseline)
    elif candidate.get("kind") == "unity_materialization_failed":
        if mode != "fresh":
            raise ValueError("failed Unity validation revision requires fresh feedback")
        from Pipeline.AssistantControl.review import ReviewGate
        archived_view = dict(
            record, candidate=dict(candidate), status="validation_failed",
            materialization_failure=archived.get("materialization_failure"),
        )
        ReviewGate(checkouts)._require_candidate(
            archived_view, baseline, allow_failed_materialization=True,
        )
    elif mode != "legacy_retry":
        raise ValueError("unsupported revision feedback mode")
    # Same defect and same precondition as revisions.py: an absent object is not
    # a proven non-ancestor, and this check also runs in the task checkout.
    checkout_root = checkouts.root / task_id
    missing = unresolvable_commit(
        checkout_root,
        ("current source HEAD", source_head),
        ("the revision baseline", baseline),
    )
    if missing is not None:
        raise ValueError(
            f"{missing}, so whether the revision candidate is based on current "
            "source HEAD was never determined"
        )
    try:
        git(checkout_root, "merge-base", "--is-ancestor", source_head, baseline)
    except RuntimeError as exc:
        raise ValueError("revision candidate is not based on current source HEAD") from exc
    return baseline


def reserve(
    checkouts: Checkouts,
    task_id: str,
    run_id: str,
    capacity: int = 1,
    *,
    dependency_reader: DependencyReader | None = None,
    allow_resource_overlap: bool = False,
) -> dict[str, Any]:
    """Reserve one executable plan for ``run_id`` without launching anything.

    ``dependency_reader`` is an explicitly injectable fixture seam. Production
    callers use ``inspect_dependencies``. A caller must prove terminal worker
    completion before calling :func:`release`; admission makes no liveness or
    timeout claim.
    """
    task_id = validate_task_id(task_id)
    if type(run_id) is not str or not run_id.strip():
        raise ValueError("admission requires a run_id")
    if type(capacity) is not int or isinstance(capacity, bool) or capacity < 1:
        raise ValueError("admission capacity must be a positive integer")
    if type(allow_resource_overlap) is not bool:
        raise ValueError("allow_resource_overlap must be a boolean")
    reader = dependency_reader or inspect_dependencies
    source = checkouts.source
    lock_path, registry_path = _source_registry_paths(source)
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        with _exclusive_file_lock(lock_path, timeout_seconds=10):
            registry = _read_registry(registry_path, source)
            record_path = checkouts.records / f"{task_id}.json"
            if not record_path.is_file():
                raise ValueError("task checkout record does not exist")
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("task checkout record is unreadable") from exc
            source_head = git(source, "rev-parse", "HEAD").decode().strip()
            baseline = _revision_baseline(checkouts, record, task_id, source_head)
            if baseline is None:
                baseline = _revise_on_source_baseline(checkouts, record, source_head)
            scope = record.get("scope")
            if baseline is None and (record.get("source_commit") != source_head
                                     or not isinstance(scope, dict)
                                     or scope.get("source_head") != source_head):
                raise ValueError("source or persisted scope is not at current HEAD")
            checkout_head = baseline or source_head
            if baseline is not None and (not isinstance(scope, dict)
                                         or scope.get("source_head") != baseline):
                raise ValueError("revision scope is not pinned to the rejected candidate")
            checkout = _clean_checkout(checkouts, {**record, "task_id": task_id}, checkout_head)
            task = load_committed_task(checkout, task_id, commit=checkout_head,
                                       expected_sha256=record.get("task_contract_sha256"))
            if task.get("contract_disposition") != "active":
                raise ValueError("only active task contracts can be admitted")
            _executable_task(task)
            scope = _validate_persisted_scope(checkouts, record, task_id, checkout, task)
            lease_id = scope["lease_id"]
            dependency = dict(reader(source, task_id, checkouts.root))
            _dependency_is_satisfied(dependency, task_id, source_head)
            resources = _reservation_resources(task, scope)
            existing = registry["reservations"]
            checkout_root = str(checkouts.root)
            checkout_path = str(checkout)
            for item in existing:
                same_key = (item.get("task_id") == task_id and item.get("run_id") == run_id
                            and item.get("lease_id") == lease_id)
                if same_key:
                    if (item.get("checkout_root") != checkout_root
                            or item.get("checkout") != checkout_path):
                        raise ValueError("reservation identity differs by checkout root or checkout")
                    if item.get("resource_overlap_authorized", False) != allow_resource_overlap:
                        raise ValueError("reservation overlap authorization differs")
                    return {**item, "admitted": True, "execution_authorized": False}
                if item.get("task_id") == task_id:
                    raise ValueError("task already has a different active admission")
                if item.get("run_id") == run_id or item.get("lease_id") == lease_id:
                    raise ValueError("run or lease identity is already reserved")
            if len(existing) >= capacity:
                raise ValueError("assistant worker capacity is exhausted")
            overlap_with = []
            for item in existing:
                requested_overlap, owner_overlap = _overlapping_resources(resources, item)
                if not requested_overlap:
                    continue
                if not (allow_resource_overlap and _parallel_checkout_overlap_allowed(
                    checkouts, task_id, item, requested_overlap, owner_overlap,
                )):
                    raise ValueError("requested execution resources overlap an active admission")
                overlap_with.append({
                    "task_id": item["task_id"], "run_id": item["run_id"],
                    "requested_resources": requested_overlap,
                    "owner_resources": owner_overlap,
                })
            reservation = {
                "schema_version": REGISTRY_SCHEMA, "status": _ACTIVE,
                "source": str(source), "task_id": task_id, "run_id": run_id,
                "lease_id": lease_id, "checkout_root": checkout_root,
                "checkout": checkout_path, "source_head": checkout_head,
                "task_contract_sha256": record["task_contract_sha256"],
                "plan_id": scope["plan_id"], "plan": scope["plan"],
                "resources": resources, "dependency_inspection": dependency,
                "resource_overlap_authorized": allow_resource_overlap,
                "overlap_with": overlap_with,
            }
            # This is the final source checkpoint before the durable admission.
            if git(source, "rev-parse", "HEAD").decode().strip() != source_head:
                raise ValueError("source HEAD changed before durable admission")
            if baseline is not None:
                _revision_baseline(checkouts, record, task_id, source_head)
            existing.append(reservation)
            write_record(registry_path, registry)
            return {**reservation, "admitted": True, "execution_authorized": False}


def release(checkouts: Checkouts, task_id: str, run_id: str, lease_id: str) -> dict[str, Any]:
    """Release only the exact reservation identity after caller-proven termination."""
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        return release_under_checkouts_lock(checkouts, task_id, run_id, lease_id)


def release_under_checkouts_lock(checkouts: Checkouts, task_id: str, run_id: str,
                                 lease_id: str) -> dict[str, Any]:
    """``release`` for a caller that already holds ``checkouts.lock``.

    A caller that must PROVE something about a run and then release it has to
    hold one lock across both halves. ``worker_launcher.launch_worker`` verifies
    its reservation and creates the run directory inside a single hold of
    ``checkouts.lock``, so evidence gathered outside that lock can be overtaken
    between the reading and the release -- which would drop a reservation for a
    run that had just started. Re-entering the file lock from inside it would
    deadlock, hence this split. ``release`` itself is unchanged: same locks, same
    order, same refusal.
    """
    task_id = validate_task_id(task_id)
    if type(run_id) is not str or not run_id.strip() or type(lease_id) is not str or not lease_id.strip():
        raise ValueError("release requires exact run_id and lease_id")
    lock_path, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(lock_path, timeout_seconds=10):
        registry = _read_registry(registry_path, checkouts.source)
        matches = [item for item in registry["reservations"]
                   if item.get("task_id") == task_id and item.get("run_id") == run_id
                   and item.get("lease_id") == lease_id
                   and item.get("checkout_root") == str(checkouts.root)]
        if len(matches) != 1:
            raise ValueError("exact active admission reservation was not found")
        registry["reservations"].remove(matches[0])
        write_record(registry_path, registry)
        return {"released": True, "task_id": task_id, "run_id": run_id, "lease_id": lease_id}


def require_reservation(checkouts: Checkouts, task_id: str, run_id: str,
                        lease_id: str) -> dict[str, Any]:
    """Return the exact current reservation owned by this checkout root.

    The worker remains responsible for proving terminal completion before
    releasing it; this check makes no process-liveness claim.
    """
    task_id = validate_task_id(task_id)
    if (type(run_id) is not str or not run_id.strip()
            or type(lease_id) is not str or not lease_id.strip()):
        raise ValueError("reservation lookup requires exact run_id and lease_id")
    lock_path, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        with _exclusive_file_lock(lock_path, timeout_seconds=10):
            registry = _read_registry(registry_path, checkouts.source)
            matches = [item for item in registry["reservations"]
                       if item.get("task_id") == task_id and item.get("run_id") == run_id
                       and item.get("lease_id") == lease_id]
            if len(matches) != 1 or matches[0].get("checkout_root") != str(checkouts.root):
                raise ValueError("exact current admission reservation is not owned by this checkout root")
            reservation = matches[0]
            record_path = checkouts.records / f"{task_id}.json"
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("owned task checkout record is unreadable") from exc
            if (record.get("checkout") != reservation.get("checkout")
                    or reservation.get("checkout_root") != str(checkouts.root)
                    or reservation.get("checkout") != str(checkouts.root / task_id)
                    or record.get("source") != reservation.get("source")
                    or record.get("source_commit") != reservation.get("source_head")
                    or not isinstance(record.get("scope"), dict)
                    or record["scope"].get("lease_id") != lease_id
                    or record["scope"].get("plan_id") != reservation.get("plan_id")):
                raise ValueError("reservation no longer matches the owned task record")
            return {**reservation, "admitted": True, "execution_authorized": False}


__all__ = ["REGISTRY_SCHEMA", "release", "require_reservation", "reserve"]
