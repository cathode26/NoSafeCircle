"""Preserve and reopen the exact NSC-032 incidental-folder-meta failure.

This is an explicit operator action. It never runs Unity or a provider and
never approves the candidate. The original crew commit stays at checkout HEAD.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.review import _source_integration_lock
from Pipeline.AssistantControl.source_update import _require_settled_worker
from Pipeline.AssistantControl.unity_materialization import _candidate_receipt
from Pipeline.TaskReviewAgent.door_prototype_materialization import (
    NSC032_INCIDENTAL_FOLDER_META, changed_paths,
    is_expected_nsc032_folder_meta, is_unity_serialized,
)
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXACT_ERROR = (
    "Unity created untracked paths outside the DoorPrototype builder-owned "
    "boundary: ('Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies.meta',)"
)
_COVERAGE_SETTINGS = (
    "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json"
)


class MaterializationRecoveryError(ValueError):
    """The retained Unity failure differs from the one requested."""


def failure_sha256(failure: dict) -> str:
    body = json.dumps(failure, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaterializationRecoveryError(f"recovery record is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise MaterializationRecoveryError(f"recovery record is not an object: {path}")
    return value


def _refresh_exact_index(checkout: Path, candidate: str) -> list[str]:
    """Clear stale stat entries only when their normalized blobs equal HEAD."""
    if git(checkout, "diff", "--cached", "--name-only", "-z", "--"):
        raise MaterializationRecoveryError("recovered candidate has staged changes")
    raw_status = git(checkout, "status", "--porcelain=v1", "-z",
                     "--untracked-files=all").decode("utf-8", errors="strict")
    entries = [item for item in raw_status.split("\0") if item]
    stale_paths: list[str] = []
    for entry in entries:
        if not entry.startswith(" M "):
            raise MaterializationRecoveryError("recovered checkout has non-stat changes")
        path = entry[3:]
        if path in stale_paths:
            raise MaterializationRecoveryError("duplicate dirty path in Git status")
        if not (
            ((path.startswith("Assets/") or path.startswith("ProjectSettings/"))
             and is_unity_serialized(path))
            or path == _COVERAGE_SETTINGS
        ):
            raise MaterializationRecoveryError("non-Unity status path requires separate review")
        if not (checkout / path).is_file() or (checkout / path).is_symlink():
            raise MaterializationRecoveryError("stale path is not a regular archived file")
        expected = git(checkout, "rev-parse", f"{candidate}:{path}").decode().strip()
        normalized = git(checkout, "hash-object", f"--path={path}", "--", path).decode().strip()
        if normalized != expected:
            raise MaterializationRecoveryError("recovered file content differs from candidate HEAD")
        stale_paths.append(path)
    refresh_error: RuntimeError | None = None
    if stale_paths:
        try:
            git(checkout, "update-index", "--refresh", "--", *stale_paths)
        except RuntimeError as exc:
            # Git for Windows can return 1 for stale stat entries even after
            # refreshing them. The exact postcondition, not that exit code,
            # decides whether the checkout is usable.
            refresh_error = exc
    if git(checkout, "rev-parse", "HEAD").decode().strip() != candidate:
        raise MaterializationRecoveryError("candidate HEAD changed during index refresh")
    if (git(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all")
            or git(checkout, "diff", "--cached", "--name-only", "-z", "--")):
        raise MaterializationRecoveryError(
            "checkout remains dirty after verified index refresh"
        ) from refresh_error
    return stale_paths


def reopen_failed_nsc032_materialization(
    checkouts: Checkouts, task_id: str, *, expected_candidate: str,
    expected_failure_sha256: str,
) -> dict:
    """Archive exact failed output, restore original commit, then reopen it."""
    if task_id != "NSC-032" or not _SHA40.fullmatch(expected_candidate):
        raise MaterializationRecoveryError("recovery requires exact NSC-032 candidate commit")
    if not _SHA256.fullmatch(expected_failure_sha256):
        raise MaterializationRecoveryError("recovery requires exact failed-journal SHA-256")
    record_path = checkouts.records / f"{task_id}.json"
    journal_path = checkouts.records / f"{task_id}.unity-materialization.{expected_candidate}.json"
    source_lock, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        with _source_integration_lock(checkouts.source):
            with _exclusive_file_lock(source_lock, timeout_seconds=10):
                record = _read(record_path)
                candidate = record.get("candidate") or {}
                if candidate.get("commit") != expected_candidate:
                    raise MaterializationRecoveryError("candidate commit differs from exact request")
                journal = _read(journal_path)
                failure = record.get("materialization_failure") or {}
                if (
                    record.get("task_id") != task_id
                    or record.get("source") != str(checkouts.source)
                    or record.get("checkout") != str(checkouts.root / task_id)
                    or record.get("status") != "materialization_failed"
                    or record.get("approval") is not None
                    or record.get("human_review") is not None
                    or candidate.get("kind", "crew_reviewed") != "crew_reviewed"
                    or candidate.get("commit") != expected_candidate
                    or candidate.get("parent") != record.get("source_commit")
                    or failure != journal
                    or journal.get("phase") != "materialization_failed"
                    or journal.get("retryable") is not False
                    or journal.get("original_candidate_commit") != expected_candidate
                    or journal.get("original_candidate_tree") != candidate.get("tree")
                    or journal.get("materialization_error") != _EXACT_ERROR
                    or failure_sha256(journal) != expected_failure_sha256
                ):
                    raise MaterializationRecoveryError("retained candidate or failure differs")
                _candidate_receipt(record, candidate)
                _require_settled_worker(record)
                registry = _read_registry(registry_path, checkouts.source)
                if any(item.get("task_id") == task_id for item in registry["reservations"]):
                    raise MaterializationRecoveryError("task still has an active admission")
                checkout = checkouts.root / task_id
                if checkout.is_symlink() or checkout.resolve() != checkout:
                    raise MaterializationRecoveryError("task checkout was redirected")
                if (
                    Path(git(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve() != checkout
                    or git(checkout, "branch", "--show-current").decode().strip() != record.get("branch")
                    or git(checkout, "rev-parse", "HEAD").decode().strip() != expected_candidate
                    or git(checkout, "rev-parse", "HEAD^{tree}").decode().strip() != candidate.get("tree")
                ):
                    raise MaterializationRecoveryError("task checkout is not the exact candidate")
                source_head = git(checkouts.source, "rev-parse", "HEAD").decode().strip()
                try:
                    git(checkouts.source, "merge-base", "--is-ancestor", record["source_commit"], source_head)
                except RuntimeError as exc:
                    raise MaterializationRecoveryError("current Source does not descend from candidate Source") from exc
                staged = git(checkout, "diff", "--cached", "--name-only", "-z", "--").decode().split("\0")
                if any(staged):
                    raise MaterializationRecoveryError("candidate has staged changes")
                tracked = tuple(item for item in git(
                    checkout, "diff", "--name-only", "-z", "HEAD", "--"
                ).decode().split("\0") if item)
                untracked = tuple(item for item in git(
                    checkout, "ls-files", "--others", "--exclude-standard", "-z"
                ).decode().split("\0") if item)
                if untracked != (NSC032_INCIDENTAL_FOLDER_META,) or not tracked:
                    raise MaterializationRecoveryError("dirty paths differ from the retained Unity failure")
                if any(not ((path.startswith("Assets/") and is_unity_serialized(path))
                            or path == _COVERAGE_SETTINGS) for path in tracked):
                    raise MaterializationRecoveryError("non-Unity tracked edits require separate review")
                meta = checkout / NSC032_INCIDENTAL_FOLDER_META
                if not is_expected_nsc032_folder_meta(
                    checkout, NSC032_INCIDENTAL_FOLDER_META, meta.read_bytes(),
                ):
                    raise MaterializationRecoveryError("untracked Enemies.meta is not the expected folder meta")
                archive = (checkouts.records / "materialization-recovery"
                           / f"{task_id}-{expected_candidate}-{expected_failure_sha256[:12]}")
                if not archive.resolve().is_relative_to(checkouts.records.resolve()):
                    raise MaterializationRecoveryError("recovery archive escaped checkout records")
                if archive.exists():
                    raise MaterializationRecoveryError("recovery archive already exists; inspect before retrying")
                archive.mkdir(parents=True)
                copied: dict[str, str] = {}
                for path in (*tracked, *untracked):
                    source_file = checkout / path
                    target_file = archive / "dirty" / path
                    if not source_file.is_file() or source_file.is_symlink():
                        raise MaterializationRecoveryError("dirty path is not a regular file")
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    content = source_file.read_bytes()
                    with target_file.open("xb") as stream:
                        stream.write(content)
                    if target_file.read_bytes() != content:
                        raise MaterializationRecoveryError("archived Unity output differs")
                    copied[path] = hashlib.sha256(content).hexdigest()
                for name, content in (("failed-record.json", record_path.read_bytes()),
                                      ("failed-journal.json", journal_path.read_bytes())):
                    with (archive / name).open("xb") as stream:
                        stream.write(content)
                manifest = {
                    "schema_version": "assistant-nsc032-materialization-recovery/v1",
                    "task_id": task_id, "candidate_commit": expected_candidate,
                    "candidate_tree": candidate["tree"],
                    "source_base": record["source_commit"],
                    "source_head_at_recovery": source_head,
                    "failure_sha256": expected_failure_sha256,
                    "archived_paths_sha256": copied,
                    "archived_at": datetime.now(timezone.utc).isoformat(),
                }
                write_record(archive / "manifest.json", manifest)
                # The exact dirty bytes are durable before any checkout change.
                git(checkout, "restore", "--source", expected_candidate,
                    "--staged", "--worktree", "--", *tracked)
                if hashlib.sha256(meta.read_bytes()).hexdigest() != copied[NSC032_INCIDENTAL_FOLDER_META]:
                    raise MaterializationRecoveryError("folder meta changed after preservation")
                meta.unlink()
                refreshed_paths = _refresh_exact_index(checkout, expected_candidate)
                if changed_paths(checkout):
                    raise MaterializationRecoveryError("checkout is not clean after archived recovery")
                if git(checkouts.source, "rev-parse", "HEAD").decode().strip() != source_head:
                    raise MaterializationRecoveryError("Source moved during recovery")
                record["status"] = "needs_materialization"
                record["materialization_recovery"] = {
                    **manifest, "archive": str(archive),
                    "index_refreshed_paths": refreshed_paths,
                    "index_refreshed_at": datetime.now(timezone.utc).isoformat(),
                }
                record.pop("materialization_failure", None)
                write_record(record_path, record)
                journal_path.unlink()
                return {"task_id": task_id, "candidate_commit": expected_candidate,
                        "status": "needs_materialization", "archive": str(archive),
                        "checkout_clean": True}


def refresh_recovered_nsc032_index(
    checkouts: Checkouts, task_id: str, *, expected_candidate: str,
    expected_failure_sha256: str,
) -> dict:
    """Finish a prior exact recovery whose Git stat entries still look dirty."""
    if task_id != "NSC-032" or not _SHA40.fullmatch(expected_candidate):
        raise MaterializationRecoveryError("index refresh requires exact NSC-032 candidate")
    if not _SHA256.fullmatch(expected_failure_sha256):
        raise MaterializationRecoveryError("index refresh requires exact failure SHA-256")
    record_path = checkouts.records / f"{task_id}.json"
    source_lock, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        with _source_integration_lock(checkouts.source):
            with _exclusive_file_lock(source_lock, timeout_seconds=10):
                record = _read(record_path)
                candidate = record.get("candidate") or {}
                recovery = record.get("materialization_recovery") or {}
                archive = (checkouts.records / "materialization-recovery"
                           / f"{task_id}-{expected_candidate}-{expected_failure_sha256[:12]}")
                if (
                    record.get("task_id") != task_id
                    or record.get("source") != str(checkouts.source)
                    or record.get("checkout") != str(checkouts.root / task_id)
                    or record.get("status") != "needs_materialization"
                    or record.get("approval") is not None
                    or record.get("human_review") is not None
                    or candidate.get("kind", "crew_reviewed") != "crew_reviewed"
                    or candidate.get("commit") != expected_candidate
                    or candidate.get("parent") != record.get("source_commit")
                    or recovery.get("archive") != str(archive)
                    or recovery.get("failure_sha256") != expected_failure_sha256
                ):
                    raise MaterializationRecoveryError("reopened candidate or recovery differs")
                if not archive.resolve().is_relative_to(checkouts.records.resolve()):
                    raise MaterializationRecoveryError("recovery archive escaped checkout records")
                manifest = _read(archive / "manifest.json")
                if any(recovery.get(key) != value for key, value in manifest.items()):
                    raise MaterializationRecoveryError("recovery record differs from archived manifest")
                if (manifest.get("candidate_commit") != expected_candidate
                        or manifest.get("failure_sha256") != expected_failure_sha256
                        or not isinstance(manifest.get("archived_paths_sha256"), dict)):
                    raise MaterializationRecoveryError("archived recovery identity differs")
                _candidate_receipt(record, candidate)
                _require_settled_worker(record)
                registry = _read_registry(registry_path, checkouts.source)
                if any(item.get("task_id") == task_id for item in registry["reservations"]):
                    raise MaterializationRecoveryError("task still has an active admission")
                checkout = checkouts.root / task_id
                if checkout.is_symlink() or checkout.resolve() != checkout:
                    raise MaterializationRecoveryError("task checkout was redirected")
                if (
                    Path(git(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve() != checkout
                    or git(checkout, "branch", "--show-current").decode().strip() != record.get("branch")
                    or git(checkout, "rev-parse", "HEAD").decode().strip() != expected_candidate
                    or git(checkout, "rev-parse", "HEAD^{tree}").decode().strip() != candidate.get("tree")
                ):
                    raise MaterializationRecoveryError("task checkout is not the recovered candidate")
                refreshed_paths = _refresh_exact_index(checkout, expected_candidate)
                recovery["index_refreshed_paths"] = refreshed_paths
                recovery["index_refreshed_at"] = datetime.now(timezone.utc).isoformat()
                record["materialization_recovery"] = recovery
                write_record(record_path, record)
                return {"task_id": task_id, "candidate_commit": expected_candidate,
                        "status": "needs_materialization", "archive": str(archive),
                        "index_refreshed_paths": refreshed_paths,
                        "checkout_clean": True}


__all__ = ["MaterializationRecoveryError", "failure_sha256",
           "reopen_failed_nsc032_materialization", "refresh_recovered_nsc032_index"]
