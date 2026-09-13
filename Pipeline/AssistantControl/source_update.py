"""Synchronize an approved candidate with a later Source commit mechanically."""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.review import ReviewGate, _source_integration_lock
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
from Pipeline.TaskReviewAgent.contracts import validate_task_id


class CandidateSynchronizationError(ValueError):
    """A candidate cannot be synchronized without losing evidence."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_path(checkouts: Checkouts, task_id: str) -> Path:
    return checkouts.records / f"{validate_task_id(task_id)}.json"


def _journal_path(checkouts: Checkouts, task_id: str) -> Path:
    return checkouts.records / f"{validate_task_id(task_id)}.candidate-sync.json"


def _completed_dir(checkouts: Checkouts, task_id: str) -> Path:
    return checkouts.records / "candidate-sync" / validate_task_id(task_id)


def _read_json(path: Path, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateSynchronizationError(f"{field} is unreadable") from exc
    if not isinstance(value, dict):
        raise CandidateSynchronizationError(f"{field} must be an object")
    return value


def _source_snapshot(source: Path) -> tuple[str, str, str]:
    return (git(source, "rev-parse", "HEAD").decode().strip(),
            git(source, "rev-parse", "HEAD^{tree}").decode().strip(),
            git(source, "branch", "--show-current").decode().strip())


def _require_no_active_reservation(checkouts: Checkouts, task_id: str) -> None:
    _, registry_path = _source_registry_paths(checkouts.source)
    registry = _read_registry(registry_path, checkouts.source)
    if any(item.get("task_id") == task_id for item in registry["reservations"]):
        raise CandidateSynchronizationError("task has an active reservation; settle it before synchronization")


def _require_settled_worker(record: Mapping[str, Any]) -> None:
    worker = record.get("worker")
    launch = record.get("launch")
    if isinstance(worker, Mapping):
        if (worker.get("status") in {"running", "starting", "ready_pending", "stopping"}
                or worker.get("capacity_released") is not True):
            raise CandidateSynchronizationError("worker is active or unsettled")
        if isinstance(launch, Mapping) and launch.get("run_id") != worker.get("run_id"):
            raise CandidateSynchronizationError("worker and launch identify different runs")
        # A matching launcher record predates the worker's settlement field;
        # the settled worker is the authoritative capacity proof for that pair.
        if isinstance(launch, Mapping) and launch.get("run_id") == worker.get("run_id"):
            return
    if isinstance(launch, Mapping) and (
            launch.get("status") in {"running", "starting", "ready_pending", "stopping"}
            or launch.get("capacity_released") is not True):
        raise CandidateSynchronizationError("launch is active or unsettled")


def _synchronization_state(record: Mapping[str, Any], expected_candidate: str) -> str | None:
    """Return the exact review state allowed to receive a mechanical Source merge."""
    candidate = record.get("candidate")
    if not isinstance(candidate, Mapping) or candidate.get("commit") != expected_candidate:
        return None
    approval = record.get("approval")
    if (record.get("status") == "approved" and isinstance(approval, Mapping)
            and approval.get("decision") == "approve"
            and approval.get("commit") == expected_candidate):
        return "approved"
    # Synchronizing before Vincent tests avoids asking him to test a candidate
    # that is already stale. This grants no approval: the merged commit still
    # enters awaiting_human and must be tested by its new exact SHA.
    if record.get("status") == "awaiting_human" and approval is None:
        return "unreviewed"
    failure = record.get("candidate_validation_failure") or {}
    expected_error = (
        f"authoritative validation policy for {record.get('task_id')} is stale"
    )
    if (record.get("status") == "validation_failed" and approval is None
            and record.get("human_review") is None
            and failure.get("candidate_commit") == expected_candidate
            and failure.get("validation_error") == expected_error):
        # A corrected committed policy must be merged into the retained exact
        # candidate before its focused validation can be retried. This grants
        # no approval and retains the failed attempt in candidate lineage.
        return "stale_policy_validation_retry"
    retry = record.get("candidate_validation_retry") or {}
    retry_failure_sha256 = None
    if record.get("status") == "validation_retry_authorized" and isinstance(failure, Mapping):
        try:
            retry_failure_sha256 = hashlib.sha256(json.dumps(
                failure,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")).hexdigest()
        except (TypeError, ValueError):
            return None
    if (record.get("status") == "validation_retry_authorized" and approval is None
            and record.get("human_review") is None
            and retry.get("schema_version") == "assistant-candidate-validation-retry/v1"
            and retry.get("task_id") == record.get("task_id")
            and retry.get("candidate_commit") == expected_candidate
            and retry.get("failed_validation") == failure
            and retry.get("failed_validation_sha256") == retry_failure_sha256
            and retry.get("source_base") == record.get("source_commit")
            and retry.get("host_fix_commit")):
        return "host_validation_retry"
    return None


def _source_candidate_was_crew_reviewed(candidate: Mapping[str, Any] | None) -> bool:
    """Recover the underlying candidate authority through mechanical wrappers."""
    node = candidate
    seen: set[int] = set()
    while isinstance(node, Mapping) and id(node) not in seen:
        seen.add(id(node))
        kind = node.get("kind", "crew_reviewed")
        if kind == "crew_reviewed":
            return node.get("crew_review", True) is True
        if node.get("source_candidate_crew_review") is True:
            return True
        nested = node.get("original_candidate")
        node = nested if isinstance(nested, Mapping) else None
    return False


def _finalize(record_path: Path, record: dict[str, Any], journal: Mapping[str, Any]) -> dict[str, Any]:
    old = copy.deepcopy(record.get("candidate"))
    original = (copy.deepcopy(old.get("original_candidate"))
                if isinstance(old, Mapping) and old.get("kind") == "source_synchronized"
                else copy.deepcopy(old))
    original_scope = (copy.deepcopy(old.get("original_scope"))
                      if isinstance(old, Mapping) and old.get("kind") == "source_synchronized"
                      else copy.deepcopy(record.get("scope")))
    lineage = record.get("candidate_lineage")
    if not isinstance(lineage, list):
        lineage = []
    lineage.append({
        "kind": (old.get("kind", "crew_reviewed") if isinstance(old, Mapping) else "crew_reviewed"),
        "candidate": old,
        "approval": copy.deepcopy(record.get("approval")),
        "human_review": copy.deepcopy(record.get("human_review")),
        "source_commit": record.get("source_commit"),
    })
    record["candidate_lineage"] = lineage
    record["candidate"] = {
        "kind": "source_synchronized", "commit": journal["sync_commit"],
        "crew_review": False,
        "source_candidate_crew_review": _source_candidate_was_crew_reviewed(old),
        "tree": journal["sync_tree"], "parent": journal["old_candidate_commit"],
        "source_commit": journal["source_commit"],
        "original_candidate": original,
        "original_scope": original_scope,
        "mechanical_merge": dict(journal),
    }
    record["source_commit"] = journal["source_commit"]
    record["task_contract_sha256"] = journal["task_contract_sha256"]
    record["approval"] = None
    record["human_review"] = None
    record["status"] = "awaiting_human"
    retry = record.get("candidate_validation_retry")
    if isinstance(retry, Mapping) and journal.get("prior_review_state") == "host_validation_retry":
        record["candidate_validation_retry"] = {
            **copy.deepcopy(dict(retry)),
            "phase": "source_synchronized",
            "synchronized_candidate": journal["sync_commit"],
            "synchronized_at": _now(),
        }
        record.pop("candidate_validation_failure", None)
    for field in ("scope", "worker", "launch", "integration"):
        record.pop(field, None)
    write_record(record_path, record)
    return record


def _archive_completed(checkouts: Checkouts, journal_path: Path, journal: Mapping[str, Any]) -> None:
    operation = journal.get("operation")
    if not isinstance(operation, str) or not operation:
        raise CandidateSynchronizationError("completed synchronization journal has no operation identity")
    target = _completed_dir(checkouts, str(journal["task_id"])) / f"{operation}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_record(target, dict(journal)) if not target.exists() else None
    try:
        journal_path.unlink(missing_ok=True)
    except OSError as exc:
        raise CandidateSynchronizationError("completed synchronization journal could not be archived") from exc


def _recover_if_possible(record_path: Path, record: dict[str, Any], journal_path: Path,
                         expected_candidate: str, expected_source_commit: str,
                         checkouts: Checkouts) -> dict[str, Any] | None:
    journal = _read_json(journal_path, field="candidate synchronization journal") if journal_path.is_file() else None
    if journal is not None and journal.get("phase") in {"pre_ff", "post_ff"}:
        checkout = Path(record.get("checkout", ""))
        current = git(checkout, "rev-parse", "HEAD").decode().strip()
        candidate = record.get("candidate") or {}
        if (journal.get("old_candidate_commit") == expected_candidate
                and journal.get("source_commit") == expected_source_commit
                and candidate.get("commit") == expected_candidate
                and _synchronization_state(record, expected_candidate) is not None
                and current == journal.get("sync_commit")):
            parents = git(checkout, "rev-list", "--parents", "-n", "1", current).decode().strip().split()
            tree = git(checkout, "rev-parse", "HEAD^{tree}").decode().strip()
            if tree != journal.get("sync_tree") or parents != [current, expected_candidate, journal.get("source_commit")]:
                raise CandidateSynchronizationError("candidate synchronization recovery merge proof differs")
            if journal.get("old_candidate_commit") != expected_candidate or journal.get("source_commit") != expected_source_commit:
                raise CandidateSynchronizationError("candidate synchronization journal does not match the exact command")
            journal = {**journal, "phase": "post_ff", "recovered": True}
            write_record(journal_path, journal)
            return _finalize(record_path, record, journal)
    if journal is not None and journal.get("phase") == "post_ff" \
            and (record.get("candidate") or {}).get("kind") == "source_synchronized" \
            and (record.get("candidate") or {}).get("commit") == journal.get("sync_commit"):
        replay = (expected_candidate == journal.get("old_candidate_commit")
                  and expected_source_commit == journal.get("source_commit"))
        _archive_completed(checkouts, journal_path, journal)
        if replay:
            return record
        journal = None
    if journal is None:
        for candidate_journal in sorted(_completed_dir(checkouts, record["task_id"]).glob("*.json")):
            saved = _read_json(candidate_journal, field="completed synchronization journal")
            if (saved.get("phase") == "post_ff" and saved.get("task_id") == record.get("task_id")
                    and saved.get("old_candidate_commit") == expected_candidate
                    and saved.get("source_commit") == expected_source_commit):
                current = git(Path(record["checkout"]), "rev-parse", "HEAD").decode().strip()
                if (record.get("candidate") or {}).get("kind") == "source_synchronized":
                    return record
                if ((record.get("candidate") or {}).get("commit") == expected_candidate
                        and _synchronization_state(record, expected_candidate) is not None
                        and current == saved.get("sync_commit")):
                    parents = git(Path(record["checkout"]), "rev-list", "--parents", "-n", "1", current).decode().strip().split()
                    tree = git(Path(record["checkout"]), "rev-parse", "HEAD^{tree}").decode().strip()
                    if parents != [current, expected_candidate, expected_source_commit] or tree != saved.get("sync_tree"):
                        raise CandidateSynchronizationError("completed synchronization record has an invalid merge proof")
                    return _finalize(record_path, record, saved)
                raise CandidateSynchronizationError("completed synchronization record does not match the owned checkout")
        return None
    if ((record.get("candidate") or {}).get("kind") == "source_synchronized"
            and journal.get("task_id") == record.get("task_id")
            and (journal.get("old_candidate_commit") != expected_candidate
                 or journal.get("source_commit") != expected_source_commit)):
        raise CandidateSynchronizationError("candidate is already source synchronized; repeated synchronization is unsupported")
    if (journal.get("task_id") != record.get("task_id")
            or journal.get("old_candidate_commit") != expected_candidate
            or journal.get("source_commit") != expected_source_commit):
        raise CandidateSynchronizationError("candidate synchronization journal task differs")
    checkout = Path(record.get("checkout", ""))
    if ((record.get("branch") != git(checkout, "branch", "--show-current").decode().strip())
            or git(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all")):
        raise CandidateSynchronizationError("candidate synchronization recovery checkout is not clean and owned")
    current = git(checkout, "rev-parse", "HEAD").decode().strip()
    if ((record.get("candidate") or {}).get("commit") == expected_candidate
            and _synchronization_state(record, expected_candidate) is not None
            and current == journal.get("sync_commit") and journal.get("phase") in {"pre_ff", "post_ff"}):
        tree = git(checkout, "rev-parse", "HEAD^{tree}").decode().strip()
        parents = git(checkout, "rev-list", "--parents", "-n", "1", current).decode().strip().split()
        if tree != journal.get("sync_tree") or parents != [current, expected_candidate, expected_source_commit]:
            raise CandidateSynchronizationError("candidate synchronization recovery merge proof differs")
        journal = {**journal, "phase": "post_ff", "recovered": True}
        write_record(journal_path, journal)
        return _finalize(record_path, record, journal)
    raise CandidateSynchronizationError("candidate synchronization is pending; retained journal and staging require inspection")


def synchronize_candidate(
    checkouts: Checkouts, task_id: str, expected_candidate: str,
    expected_source_commit: str,
) -> dict[str, Any]:
    """Merge current clean Source history into one exact candidate checkout.

    The resulting commit is ``source_synchronized`` and awaits a fresh human
    test. An awaiting-human candidate may be synchronized before its first test;
    this grants no approval. No provider or ExecutionCrew receipt is created.
    """
    task_id = validate_task_id(task_id)
    if (not isinstance(expected_candidate, str) or not expected_candidate
            or not isinstance(expected_source_commit, str) or not expected_source_commit):
        raise CandidateSynchronizationError("synchronization requires exact candidate and Source commits")
    record_path = _record_path(checkouts, task_id)
    journal_path = _journal_path(checkouts, task_id)
    source_lock, _ = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        record = _read_json(record_path, field="owned task record")
        if record.get("task_id") != task_id or record.get("source") != str(checkouts.source):
            raise CandidateSynchronizationError("task record identity differs")
        _require_settled_worker(record)
        with _source_integration_lock(checkouts.source), _exclusive_file_lock(source_lock, timeout_seconds=10):
            _require_no_active_reservation(checkouts, task_id)
            checkouts.observe(task_id)  # Recovery must establish canonical ownership too.
            recovered = _recover_if_possible(record_path, record, journal_path,
                                              expected_candidate, expected_source_commit, checkouts)
            if recovered is not None:
                return recovered
            checkout = checkouts.observe(task_id)
            if checkout.get("local_changes"):
                raise CandidateSynchronizationError("task checkout is dirty; changes were preserved")
            ReviewGate(checkouts)._require_candidate(
                record, expected_candidate, allow_stale_policy_failure=True,
            )
            prior_review_state = _synchronization_state(record, expected_candidate)
            if prior_review_state is None:
                raise CandidateSynchronizationError(
                    "synchronization requires the exact current approved or unreviewed candidate"
                )
            old_source = record.get("source_commit")
            revision = record.get("revision")
            # A fresh revision may be based on a rejected synchronized
            # candidate.  Its record source_commit is that rejected merge,
            # while revision.source_commit is the verified Source base from
            # which the revision was actually prepared.
            if (isinstance(revision, Mapping)
                    and revision.get("candidate_commit") == old_source
                    and isinstance(revision.get("source_commit"), str)):
                old_source = revision["source_commit"]
            source_head, source_tree, source_branch = _source_snapshot(checkouts.source)
            if source_head != expected_source_commit:
                raise CandidateSynchronizationError("Source HEAD differs from the inspected expected_source_commit")
            if (prior_review_state == "host_validation_retry"
                    and (record.get("candidate_validation_retry") or {}).get("host_fix_commit") != source_head):
                raise CandidateSynchronizationError(
                    "Source HEAD differs from the authorized validation host-fix commit"
                )
            if not isinstance(old_source, str):
                raise CandidateSynchronizationError("record has no source base")
            if old_source == source_head:
                raise CandidateSynchronizationError(
                    "Source has not advanced beyond the candidate's current Source binding"
                )
            try:
                git(checkouts.source, "merge-base", "--is-ancestor", old_source, source_head)
            except RuntimeError as exc:
                raise CandidateSynchronizationError("current Source is not a descendant of the candidate source") from exc
            load_committed_task(checkouts.source, task_id, commit=source_head,
                                expected_sha256=record.get("task_contract_sha256"))
            operation = uuid.uuid4().hex
            # Keep transient Git paths short enough for Windows runners.  The
            # complete UUID remains in the durable journal; this prefix only
            # names the private staging checkout and its temporary branch.
            operation_slug = operation[:12]
            staging = checkouts.records / f".sync-{task_id}-{operation_slug}"
            # Clone the source repository, whose config is not task-owned, then
            # fetch the candidate object from the owned checkout.
            git(checkouts.root, "clone", "--no-local", str(checkouts.source), str(staging), timeout_seconds=180)
            try:
                git(staging, "config", "core.hooksPath", "/dev/null")
                git(staging, "fetch", "--no-tags", str(checkout["checkout"]),
                    expected_candidate, timeout_seconds=180)
                git(staging, "checkout", "-b", f"assistant-sync/{task_id}-{operation_slug}", expected_candidate)
                git(staging, "fetch", "--no-tags", str(checkouts.source), source_head,
                    timeout_seconds=180)
                try:
                    merge_tree = git(staging, "merge-tree", "--write-tree", expected_candidate,
                                     "FETCH_HEAD", timeout_seconds=180).decode().splitlines()[0].strip()
                    git(staging, "merge", "--no-ff", "--no-edit", "FETCH_HEAD", timeout_seconds=180)
                except Exception as exc:
                    raise CandidateSynchronizationError(
                        f"Source merge conflicted; retained staging at {staging}") from exc
                if git(staging, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
                    raise CandidateSynchronizationError(f"staging merge is dirty; retained staging at {staging}")
                sync_commit = git(staging, "rev-parse", "HEAD").decode().strip()
                sync_tree = git(staging, "rev-parse", "HEAD^{tree}").decode().strip()
                parents = git(staging, "rev-list", "--parents", "-n", "1", sync_commit).decode().strip().split()
                if parents != [sync_commit, expected_candidate, source_head] or sync_tree != merge_tree:
                    raise CandidateSynchronizationError("mechanical merge parents or tree differ from merge-tree proof")
                def paths_between(left: str, right: str) -> set[str]:
                    raw = git(staging, "diff", "--name-only", "--no-renames", "-z", left, right)
                    return {item for item in raw.decode("utf-8", "surrogateescape").split("\0") if item}
                original_paths = paths_between(old_source, expected_candidate)
                synchronized_paths = paths_between(source_head, sync_commit)
                if not synchronized_paths.issubset(original_paths):
                    raise CandidateSynchronizationError(
                        f"mechanical merge changed paths outside the original candidate: retained staging at {staging}")
                task = load_committed_task(staging, task_id, commit=sync_commit,
                                            expected_sha256=record.get("task_contract_sha256"))
                journal = {
                    "schema_version": "assistant-candidate-sync/v1", "phase": "pre_ff",
                    "task_id": task_id, "operation": operation, "staging": str(staging),
                    "old_candidate_commit": expected_candidate, "source_commit": source_head,
                    "source_tree": source_tree, "source_branch": source_branch,
                    "sync_commit": sync_commit, "sync_tree": sync_tree,
                    "merge_tree": merge_tree,
                    "prior_review_state": prior_review_state,
                    "task_contract_sha256": task["task_contract_sha256"], "created_at": _now(),
                }
                write_record(journal_path, journal)
                # Final Source and task checkpoints immediately before mutating the owned checkout.
                if _source_snapshot(checkouts.source) != (source_head, source_tree, source_branch):
                    raise CandidateSynchronizationError("Source changed before candidate FF; retained staging and journal")
                if (git(checkout["checkout"], "rev-parse", "HEAD").decode().strip() != expected_candidate
                        or git(checkout["checkout"], "status", "--porcelain=v1", "-z", "--untracked-files=all")):
                    raise CandidateSynchronizationError("task checkout changed before candidate FF; retained staging and journal")
                load_committed_task(checkouts.source, task_id, commit=source_head,
                                    expected_sha256=record.get("task_contract_sha256"))
                git(checkout["checkout"], "fetch", "--no-tags", str(staging), sync_commit,
                    timeout_seconds=180)
                if (_source_snapshot(checkouts.source) != (source_head, source_tree, source_branch)
                        or git(checkout["checkout"], "branch", "--show-current").decode().strip() != record["branch"]
                        or git(checkout["checkout"], "rev-parse", "HEAD").decode().strip() != expected_candidate
                        or git(checkout["checkout"], "status", "--porcelain=v1", "-z", "--untracked-files=all")):
                    raise CandidateSynchronizationError("Source or task checkout changed after fetch; retained staging and journal")
                load_committed_task(checkouts.source, task_id, commit=source_head,
                                    expected_sha256=record.get("task_contract_sha256"))
                git(checkout["checkout"], "merge", "--ff-only", "--no-overwrite-ignore", "FETCH_HEAD",
                    timeout_seconds=180)
                journal = {**journal, "phase": "post_ff", "published_at": _now()}
                write_record(journal_path, journal)
                return _finalize(record_path, record, journal)
            except CandidateSynchronizationError:
                raise
            except Exception as exc:
                raise CandidateSynchronizationError(
                    f"candidate synchronization failed; retained staging at {staging}") from exc


def validate_synchronized_candidate(
    checkouts: Checkouts, record: Mapping[str, Any], tested_commit: str,
) -> None:
    """Validate a mechanical sync candidate for a parent review gate.

    This is read-only and deliberately does not authenticate a new crew run.
    """
    candidate = record.get("candidate") or {}
    if candidate.get("kind") != "source_synchronized" or candidate.get("commit") != tested_commit:
        raise CandidateSynchronizationError("tested commit is not a synchronized candidate")
    checkout = Path(record.get("checkout", ""))
    if git(checkout, "rev-parse", "HEAD").decode().strip() != tested_commit:
        raise CandidateSynchronizationError("synchronized checkout changed after publication")
    if git(checkout, "branch", "--show-current").decode().strip() != record.get("branch"):
        raise CandidateSynchronizationError("synchronized checkout branch changed")
    if git(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
        raise CandidateSynchronizationError("synchronized checkout has local changes")
    parents = git(checkout, "rev-list", "--parents", "-n", "1", tested_commit).decode().strip().split()
    if len(parents) != 3 or parents[1] != candidate.get("parent"):
        raise CandidateSynchronizationError("synchronized candidate does not retain its exact old candidate parent")
    source_commit = candidate.get("source_commit")
    if not isinstance(source_commit, str) or parents[2] != source_commit:
        raise CandidateSynchronizationError("synchronized candidate has no Source binding")
    original = candidate.get("original_candidate")
    lineage = record.get("candidate_lineage")
    if (not isinstance(original, Mapping) or not original.get("commit")
            or not isinstance(lineage, list)):
        raise CandidateSynchronizationError("synchronized candidate lost its original candidate lineage")
    lineage_candidates = {
        item["candidate"].get("commit"): item["candidate"]
        for item in lineage if isinstance(item, Mapping) and isinstance(item.get("candidate"), Mapping)
        and isinstance(item["candidate"].get("commit"), str)
    }
    node = candidate
    commit = tested_commit
    visited = set()
    while isinstance(node, Mapping) and node.get("kind") == "source_synchronized":
        if commit in visited:
            raise CandidateSynchronizationError("synchronized candidate lineage cycles")
        visited.add(commit)
        parent = node.get("parent")
        source = node.get("source_commit")
        mechanical = node.get("mechanical_merge")
        parents = git(checkout, "rev-list", "--parents", "-n", "1", commit).decode().strip().split()
        tree = git(checkout, "rev-parse", f"{commit}^{{tree}}").decode().strip()
        if (not isinstance(parent, str) or not isinstance(source, str)
                or parents != [commit, parent, source] or tree != node.get("tree")
                or not isinstance(mechanical, Mapping)
                or mechanical.get("sync_commit") != commit
                or mechanical.get("old_candidate_commit") != parent
                or mechanical.get("source_commit") != source
                or mechanical.get("sync_tree") != tree):
            raise CandidateSynchronizationError("synchronized candidate lineage merge proof is incomplete")
        merge_tree = git(checkout, "merge-tree", "--write-tree", parent, source).decode().splitlines()[0].strip()
        if mechanical.get("merge_tree") != merge_tree or merge_tree != tree:
            raise CandidateSynchronizationError("synchronized candidate lineage differs from merge-tree proof")
        real_source_head = git(checkouts.source, "rev-parse", "HEAD").decode().strip()
        try:
            git(checkouts.source, "merge-base", "--is-ancestor", source, real_source_head)
        except RuntimeError as exc:
            raise CandidateSynchronizationError("synchronized Source binding is not an ancestor of real Source") from exc
        for revision in (parent, source, commit):
            load_committed_task(checkout, record["task_id"], commit=revision,
                                expected_sha256=record.get("task_contract_sha256"))
        node = lineage_candidates.get(parent)
        commit = parent
        if node is None:
            raise CandidateSynchronizationError("synchronized candidate lineage is missing its parent")
    if not isinstance(node, Mapping) or node.get("commit") != original.get("commit"):
        raise CandidateSynchronizationError("synchronized candidate lost its original crew candidate")
    load_committed_task(checkouts.source, record["task_id"], commit=source_commit,
                        expected_sha256=record.get("task_contract_sha256"))


__all__ = ["CandidateSynchronizationError", "synchronize_candidate",
           "validate_synchronized_candidate"]
