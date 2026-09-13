"""Reopen one exact crew candidate after an AssistantControl host fix.

This is an operator recovery boundary, not an approval path.  It preserves the
failed validation and authorizes the exact clean candidate for the existing
crash-safe Source synchronization path.  The synchronized candidate can then
be materialized against the repaired host and current deterministic assets.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.AssistantControl.unity_materialization import (
    MaterializationError,
    _candidate_receipt,
    _generated_paths,
)
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


SCHEMA_VERSION = "assistant-candidate-validation-retry/v1"
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CandidateValidationRetryError(ValueError):
    """An exact failed candidate cannot safely be reopened."""


def validation_failure_sha256(failure: Mapping[str, Any]) -> str:
    payload = json.dumps(
        failure, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _commit(value: str, field: str) -> str:
    if type(value) is not str or not _COMMIT.fullmatch(value):
        raise CandidateValidationRetryError(f"{field} must be an exact full commit")
    return value


def _source_changes(source: Path, base: str, head: str) -> tuple[str, ...]:
    raw = git(source, "diff", "--name-only", "--no-renames", "-z", base, head, "--")
    return tuple(sorted(
        (item for item in raw.decode("utf-8", errors="strict").split("\0") if item),
        key=str.casefold,
    ))


def reopen_candidate_validation(
    checkouts: Checkouts,
    task_id: str,
    *,
    expected_candidate: str,
    expected_failure_sha256: str,
    host_fix_commit: str,
) -> dict[str, Any]:
    """Durably reopen one failed candidate for the existing materializer."""
    task_id = validate_task_id(task_id)
    expected_candidate = _commit(expected_candidate, "candidate commit")
    host_fix_commit = _commit(host_fix_commit, "host-fix commit")
    if type(expected_failure_sha256) is not str or not _SHA256.fullmatch(
        expected_failure_sha256
    ):
        raise CandidateValidationRetryError(
            "failed-validation SHA-256 must be an exact lowercase SHA-256"
        )

    record_path = checkouts.records / f"{task_id}.json"
    source_lock, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CandidateValidationRetryError("owned task record is unreadable") from exc
        if record.get("task_id") != task_id or record.get("source") != str(checkouts.source):
            raise CandidateValidationRetryError("task record identity differs")

        candidate = record.get("candidate") or {}
        if candidate.get("commit") != expected_candidate:
            raise CandidateValidationRetryError("candidate commit differs from the exact request")
        if candidate.get("kind", "crew_reviewed") != "crew_reviewed":
            raise CandidateValidationRetryError("only the original crew-reviewed candidate can retry")

        current_retry = record.get("candidate_validation_retry") or {}
        if record.get("status") == "validation_retry_authorized":
            if (
                current_retry.get("candidate_commit") == expected_candidate
                and current_retry.get("failed_validation_sha256") == expected_failure_sha256
                and current_retry.get("host_fix_commit") == host_fix_commit
            ):
                return record
            raise CandidateValidationRetryError("another materialization retry is already pending")

        failure = record.get("candidate_validation_failure")
        if (
            record.get("status") != "validation_failed"
            or not isinstance(failure, Mapping)
            or failure.get("candidate_commit") != expected_candidate
            or not isinstance(failure.get("validation_error"), str)
            or not failure["validation_error"].strip()
            or record.get("approval") is not None
            or record.get("human_review") is not None
        ):
            raise CandidateValidationRetryError(
                "retry requires the exact unreviewed machine-validation failure"
            )
        actual_failure_sha256 = validation_failure_sha256(failure)
        if actual_failure_sha256 != expected_failure_sha256:
            raise CandidateValidationRetryError("failed validation differs from the exact request")

        # Reuse the existing candidate verifier without weakening its normal
        # validation-failure refusal: only this in-memory copy is reviewable.
        candidate_view = copy.deepcopy(record)
        candidate_view["status"] = "awaiting_human"
        candidate_view.pop("candidate_validation_failure", None)
        try:
            ReviewGate(checkouts)._require_candidate(candidate_view, expected_candidate)
        except Exception as exc:
            raise CandidateValidationRetryError(
                "candidate is not the exact clean owned crew-reviewed commit"
            ) from exc

        try:
            receipt = _candidate_receipt(record, candidate)
            generated = _generated_paths(record.get("scope") or {}, receipt["changed_paths"])
        except MaterializationError as exc:
            raise CandidateValidationRetryError(
                "current host cannot authenticate and materialize the exact candidate"
            ) from exc

        source_head = git(checkouts.source, "rev-parse", "HEAD").decode().strip()
        if source_head != host_fix_commit:
            raise CandidateValidationRetryError("current Source HEAD differs from host-fix commit")
        source_base = _commit(str(record.get("source_commit", "")), "recorded source commit")
        if source_head == source_base:
            raise CandidateValidationRetryError("Source contains no host fix after the failed run")
        try:
            git(checkouts.source, "merge-base", "--is-ancestor", source_base, source_head)
        except RuntimeError as exc:
            raise CandidateValidationRetryError(
                "host-fix commit does not descend from the candidate Source"
            ) from exc
        changed_paths = _source_changes(checkouts.source, source_base, source_head)
        if not changed_paths:
            raise CandidateValidationRetryError("Source contains no fix after the failed run")
        try:
            load_committed_task(
                checkouts.source,
                task_id,
                commit=source_head,
                expected_sha256=str(record.get("task_contract_sha256", "")),
            )
        except Exception as exc:
            raise CandidateValidationRetryError(
                "task contract changed at the host-fix commit"
            ) from exc

        with _exclusive_file_lock(source_lock, timeout_seconds=10):
            registry = _read_registry(registry_path, checkouts.source)
            if any(item.get("task_id") == task_id for item in registry["reservations"]):
                raise CandidateValidationRetryError("task still has an active admission")
            if git(checkouts.source, "rev-parse", "HEAD").decode().strip() != source_head:
                raise CandidateValidationRetryError("Source advanced during retry validation")

            reopened_at = datetime.now(timezone.utc).isoformat()
            retry = {
                "schema_version": SCHEMA_VERSION,
                "task_id": task_id,
                "candidate_commit": expected_candidate,
                "failed_validation_sha256": actual_failure_sha256,
                "failed_validation": copy.deepcopy(dict(failure)),
                "source_base": source_base,
                "host_fix_commit": source_head,
                "host_fix_tree": git(
                    checkouts.source, "rev-parse", "HEAD^{tree}"
                ).decode().strip(),
                "host_changed_paths": list(changed_paths),
                "registered_generated_paths": list(generated),
                "reopened_at": reopened_at,
            }
            history = record.get("candidate_validation_retry_history", [])
            if not isinstance(history, list):
                raise CandidateValidationRetryError("validation retry history is malformed")
            history.append(copy.deepcopy(retry))
            record["candidate_validation_retry_history"] = history
            record["candidate_validation_retry"] = retry
            record["status"] = "validation_retry_authorized"
            write_record(record_path, record)
            return record


__all__ = [
    "CandidateValidationRetryError",
    "reopen_candidate_validation",
    "validation_failure_sha256",
]
