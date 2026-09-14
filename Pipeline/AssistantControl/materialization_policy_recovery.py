"""Reclassify the exact retained NSC-032 missing-policy result without Unity.

The generated commit is preserved. This operation records that automated
validation did not run; it cannot create a test pass, approval, or integration.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from pathlib import Path

from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.review import _source_integration_lock
from Pipeline.AssistantControl.source_update import _require_settled_worker
from Pipeline.AssistantControl.unity_materialization import _candidate_receipt
from Pipeline.TaskReviewAgent.authoritative_candidate_validation import policy_unavailable_reason
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class MaterializationPolicyRecoveryError(ValueError):
    """The retained materialization differs from the exact missing-policy case."""


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaterializationPolicyRecoveryError(f"record is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise MaterializationPolicyRecoveryError(f"record is not an object: {path}")
    return value


def _verify_checkout(checkouts: Checkouts, record: dict, journal: dict, materialized: str) -> None:
    checkout = checkouts.root / "NSC-032"
    if checkout.is_symlink() or checkout.resolve() != checkout:
        raise MaterializationPolicyRecoveryError("task checkout was redirected")
    if (
        Path(git(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve() != checkout
        or git(checkout, "branch", "--show-current").decode().strip() != record.get("branch")
        or git(checkout, "rev-parse", "HEAD").decode().strip() != materialized
        or git(checkout, "rev-parse", "HEAD^{tree}").decode().strip()
        != journal.get("materialized_tree")
        or git(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    ):
        raise MaterializationPolicyRecoveryError("materialized checkout identity or cleanliness differs")
    original = journal["original_candidate_commit"]
    parents = git(checkout, "rev-list", "--parents", "-n", "1", materialized).decode().split()
    if parents != [materialized, original]:
        raise MaterializationPolicyRecoveryError("materialized commit parent differs")
    changed = tuple(path for path in git(
        checkout, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", materialized,
    ).decode().split("\0") if path)
    if tuple(sorted(changed, key=str.casefold)) != tuple(journal.get("materialized_paths") or ()):
        raise MaterializationPolicyRecoveryError("materialized commit paths differ from journal")
    if git(checkout, "rev-parse", f"{original}^{{tree}}").decode().strip() != journal.get("original_candidate_tree"):
        raise MaterializationPolicyRecoveryError("original candidate tree differs")
    load_committed_task(
        checkout, "NSC-032", commit=materialized,
        expected_sha256=str(record["task_contract_sha256"]),
    )


def _promote(record_path: Path, record: dict, journal: dict, failure_sha256: str) -> dict:
    failed = record["candidate"]
    promoted = copy.deepcopy(failed)
    promoted["kind"] = "unity_materialized"
    promoted.pop("validation_failure", None)
    promoted.pop("authoritative_validations", None)
    record["candidate"] = promoted
    record["status"] = "awaiting_human"
    record["approval"] = None
    record["human_review"] = None
    record["candidate_validation_unavailable"] = {
        "candidate_commit": journal["materialized_commit"],
        "automated_unity_validation": "not_run",
        "reason": journal["validation_unavailable_reason"],
        "observed_at": journal["validation_unavailable_at"],
    }
    record["materialization_policy_recovery"] = {
        "original_failed_journal_sha256": failure_sha256,
        "materialized_commit": journal["materialized_commit"],
    }
    record.pop("materialization_failure", None)
    record.pop("candidate_validation_failure", None)
    write_record(record_path, record)
    return record


def recover_nsc032_missing_validation_policy(
    checkouts: Checkouts, task_id: str, *, original_candidate: str,
    materialized_candidate: str, failed_journal_sha256: str,
) -> dict:
    """Reclassify one exact retained failed-policy journal, never rebuild."""
    if (task_id != "NSC-032" or not _SHA40.fullmatch(original_candidate)
            or not _SHA40.fullmatch(materialized_candidate)
            or not _SHA256.fullmatch(failed_journal_sha256)):
        raise MaterializationPolicyRecoveryError("exact NSC-032 commit and journal identities are required")
    record_path = checkouts.records / f"{task_id}.json"
    journal_path = checkouts.records / f"{task_id}.unity-materialization.{original_candidate}.json"
    archive = (checkouts.records / "materialization-policy-recovery"
               / f"{task_id}-{materialized_candidate}-{failed_journal_sha256[:12]}.json")
    source_lock, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        with _source_integration_lock(checkouts.source):
            with _exclusive_file_lock(source_lock, timeout_seconds=10):
                record = _read(record_path)
                journal = _read(journal_path)
                candidate = record.get("candidate") or {}
                original = candidate.get("original_candidate") or {}
                if (
                    record.get("task_id") != task_id
                    or record.get("source") != str(checkouts.source)
                    or record.get("checkout") != str(checkouts.root / task_id)
                    or record.get("task_contract_sha256") != journal.get("task_contract_sha256")
                    or journal.get("schema_version") != "assistant-unity-materialization/v1"
                    or journal.get("task_id") != task_id
                    or journal.get("original_candidate_commit") != original_candidate
                    or journal.get("materialized_commit") != materialized_candidate
                    or candidate.get("commit") != materialized_candidate
                    or candidate.get("tree") != journal.get("materialized_tree")
                    or candidate.get("parent") != original_candidate
                    or candidate.get("plan_id") != journal.get("plan_id")
                    or candidate.get("lease_id") != journal.get("lease_id")
                    or candidate.get("changed_paths") != journal.get("materialized_paths")
                    or original.get("commit") != original_candidate
                    or original.get("tree") != journal.get("original_candidate_tree")
                    or original.get("plan_id") != journal.get("plan_id")
                    or original.get("lease_id") != journal.get("lease_id")
                    or record.get("approval") is not None
                    or record.get("human_review") is not None
                ):
                    raise MaterializationPolicyRecoveryError("retained candidate or journal identity differs")
                _candidate_receipt(record, original)
                _require_settled_worker(record)
                registry = _read_registry(registry_path, checkouts.source)
                if any(item.get("task_id") == task_id for item in registry["reservations"]):
                    raise MaterializationPolicyRecoveryError("task still has an active admission")
                _verify_checkout(checkouts, record, journal, materialized_candidate)
                if (archive.is_symlink()
                        or not archive.resolve().is_relative_to(checkouts.records.resolve())):
                    raise MaterializationPolicyRecoveryError("recovery archive escaped records")
                if journal.get("phase") == "validation_unavailable":
                    archived_bytes = archive.read_bytes() if archive.is_file() else b""
                    try:
                        archived = json.loads(archived_bytes)
                    except (UnicodeError, json.JSONDecodeError) as exc:
                        raise MaterializationPolicyRecoveryError("archived failure is unreadable") from exc
                    if not isinstance(archived, dict):
                        raise MaterializationPolicyRecoveryError("archived failure is malformed")
                    expected_journal = dict(archived)
                    expected_journal.update({
                        "phase": "validation_unavailable",
                        "validation_unavailable_reason": expected_journal.pop("validation_error", None),
                        "validation_unavailable_at": expected_journal.pop("failed_at", None),
                        "automated_unity_validation": "not_run",
                        "recovered_from_failed_journal_sha256": failed_journal_sha256,
                    })
                    if (journal.get("recovered_from_failed_journal_sha256") != failed_journal_sha256
                            or not archive.is_file()
                            or hashlib.sha256(archived_bytes).hexdigest() != failed_journal_sha256
                            or not policy_unavailable_reason(task_id, str(archived.get("validation_error")))
                            or journal != expected_journal):
                        raise MaterializationPolicyRecoveryError("completed recovery evidence differs")
                    if (record.get("status") == "awaiting_human"
                            and candidate.get("kind") == "unity_materialized"
                            and record.get("materialization_policy_recovery") == {
                                "original_failed_journal_sha256": failed_journal_sha256,
                                "materialized_commit": materialized_candidate,
                            }
                            and (record.get("candidate_validation_unavailable") or {}).get("candidate_commit")
                            == materialized_candidate
                            and "authoritative_validations" not in candidate):
                        return record
                    if record.get("status") == "validation_failed" and candidate.get("kind") == "unity_materialization_failed":
                        return _promote(record_path, record, journal, failed_journal_sha256)
                    raise MaterializationPolicyRecoveryError("partially recovered record differs")
                raw_journal = journal_path.read_bytes()
                if (
                    journal.get("phase") != "validation_failed"
                    or hashlib.sha256(raw_journal).hexdigest() != failed_journal_sha256
                    or record.get("status") != "validation_failed"
                    or candidate.get("kind") != "unity_materialization_failed"
                    or record.get("materialization_failure") != journal
                    or (candidate.get("validation_failure") or {}).get("error") != journal.get("validation_error")
                    or not policy_unavailable_reason(task_id, str(journal.get("validation_error")))
                    or "authoritative_validations" in candidate
                ):
                    raise MaterializationPolicyRecoveryError("retained failure is not the exact missing-policy case")
                archive.parent.mkdir(parents=True, exist_ok=True)
                if archive.exists():
                    if archive.read_bytes() != raw_journal:
                        raise MaterializationPolicyRecoveryError("existing recovery archive differs")
                else:
                    with archive.open("xb") as stream:
                        stream.write(raw_journal)
                        stream.flush()
                        os.fsync(stream.fileno())
                journal.update({
                    "phase": "validation_unavailable",
                    "validation_unavailable_reason": journal.pop("validation_error"),
                    "validation_unavailable_at": journal.pop("failed_at"),
                    "automated_unity_validation": "not_run",
                    "recovered_from_failed_journal_sha256": failed_journal_sha256,
                })
                write_record(journal_path, journal)
                return _promote(record_path, record, journal, failed_journal_sha256)


__all__ = ["MaterializationPolicyRecoveryError", "recover_nsc032_missing_validation_policy"]
