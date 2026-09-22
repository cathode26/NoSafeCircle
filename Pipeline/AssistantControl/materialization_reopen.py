"""Reopen one materialized candidate whose validation failed on a host defect.

NOT an approval path and NOT a rescue. It restores the exact original
crew-reviewed candidate and returns the record to ``needs_materialization`` so
the existing materializer re-runs against the repaired host.

WHY THIS AND NOT ``retry-candidate-validation``
-----------------------------------------------
Measured on NSC-046, 2026-09-22: that command refuses for three independent
reasons, and the status check is only the first.

    candidate.kind is "unity_materialization_failed", not "crew_reviewed"
    the record carries "materialization_failure", not
        "candidate_validation_failure"
    that mapping has no "candidate_commit" key at all -- it has
        "original_candidate_commit" and "materialized_commit"

It is scoped to crew-candidate validation failures. A materialized candidate
whose validation failed is a different shape and was never in view.

WHY RE-MATERIALIZE RATHER THAN RE-VALIDATE IN PLACE
---------------------------------------------------
Validating the retained materialized commit would mean hand-driving a record
past the gate that produced it. Materialization is deterministic and costs a
free Unity run and no provider spend, so re-running is the honest route.

WHAT THE RECORD ALREADY PRESERVES
---------------------------------
``_finalize_validation_failure`` keeps everything needed:

    source_candidate_crew_review  True   -- the crew-review authority SURVIVES
    original_candidate            the whole original crew-reviewed candidate

``_require_candidate`` already has a branch shaped for exactly this
(``source_synchronized``): a candidate whose own kind is not ``crew_reviewed``,
carrying ``source_candidate_crew_review`` and an ``original_candidate`` to take
the receipt from. The pattern existed; this shape was never added to it.

THE HOST-FIX BINDING IS THE POINT, NOT CEREMONY
-----------------------------------------------
It refuses a task with no host fix to bind to -- which is correct for NSC-045,
whose failure is a compile error from its own contract. Reopening that would
fail identically and re-freeze it. A guard that gets the next case right
without being told about it is worth more than a command that only knows this
one.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.candidate_validation_retry import (
    validation_failure_sha256,
)
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


SCHEMA_VERSION = "assistant-materialization-reopen/v1"
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REOPENABLE = {"validation_failed", "materialization_failed"}


class MaterializationReopenError(ValueError):
    """A failed materialized candidate cannot safely be reopened."""


def _commit(value: str, field: str) -> str:
    if type(value) is not str or not _COMMIT.fullmatch(value):
        raise MaterializationReopenError(f"{field} must be an exact full commit")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z")


def _source_changes(source: Path, base: str, head: str) -> tuple[str, ...]:
    output = git(source, "diff", "--name-only", "-z", f"{base}..{head}").decode()
    return tuple(sorted((item for item in output.split("\0") if item),
                        key=str.casefold))


def reopen_materialization(
    checkouts: Checkouts,
    task_id: str,
    *,
    expected_candidate: str,
    expected_failure_sha256: str,
    host_fix_commit: str,
    apply: bool = False,
) -> dict[str, Any]:
    """Return the original crew candidate to ``needs_materialization``.

    ``expected_candidate`` is the MATERIALIZED commit recorded on the failed
    candidate, not the original -- it is what the operator can see, and naming
    the original would let a stale request match the wrong record.

    Dry-run by default, like ``reconcile-admission``: a command that mutates
    pipeline control state should have to be asked twice.
    """
    task_id = validate_task_id(task_id)
    expected_candidate = _commit(expected_candidate, "materialized candidate commit")
    host_fix_commit = _commit(host_fix_commit, "host-fix commit")
    if type(expected_failure_sha256) is not str or not _SHA256.fullmatch(
            expected_failure_sha256):
        raise MaterializationReopenError(
            "failed validation sha256 must be an exact lowercase digest")

    record_path = checkouts.records / f"{task_id}.json"
    source_lock, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MaterializationReopenError("owned task record is unreadable") from exc
        if record.get("task_id") != task_id or record.get("source") != str(checkouts.source):
            raise MaterializationReopenError("task record identity differs")
        if record.get("status") not in _REOPENABLE:
            raise MaterializationReopenError(
                f"reopen requires a failed materialized candidate, not {record.get('status')!r}")
        if record.get("approval") is not None or record.get("human_review") is not None:
            raise MaterializationReopenError(
                "a reviewed candidate is not reopenable; that is an approval decision")

        candidate = record.get("candidate")
        if not isinstance(candidate, Mapping):
            raise MaterializationReopenError("record carries no candidate")
        if candidate.get("kind") != "unity_materialization_failed":
            raise MaterializationReopenError(
                f"reopen is for a failed MATERIALIZED candidate, not {candidate.get('kind')!r}")
        if candidate.get("commit") != expected_candidate:
            raise MaterializationReopenError(
                "materialized commit differs from the exact request")
        if candidate.get("source_candidate_crew_review") is not True:
            raise MaterializationReopenError(
                "candidate lost its crew-review authority; nothing to restore")
        original = candidate.get("original_candidate")
        if not isinstance(original, Mapping) or not original.get("commit"):
            raise MaterializationReopenError(
                "record does not retain the original crew-reviewed candidate")
        if original.get("kind", "crew_reviewed") != "crew_reviewed":
            raise MaterializationReopenError(
                "retained original is not a crew-reviewed candidate")

        failure = record.get("materialization_failure")
        if not isinstance(failure, Mapping):
            raise MaterializationReopenError("record carries no materialization failure")
        actual = validation_failure_sha256(failure)
        if actual != expected_failure_sha256:
            raise MaterializationReopenError(
                "recorded failure differs from the exact request")

        # The host fix must exist, be the named commit, and descend from the
        # Source the candidate was cut from. This is what refuses a task whose
        # failure has no host fix to bind to.
        source_head = git(checkouts.source, "rev-parse", "HEAD").decode().strip()
        if source_head != host_fix_commit:
            raise MaterializationReopenError(
                "current Source HEAD differs from host-fix commit")
        source_base = _commit(str(record.get("source_commit", "")), "recorded source commit")
        if source_head == source_base:
            raise MaterializationReopenError("Source contains no host fix after the failed run")
        try:
            git(checkouts.source, "merge-base", "--is-ancestor", source_base, source_head)
        except RuntimeError as exc:
            raise MaterializationReopenError(
                "host-fix commit does not descend from the candidate Source") from exc
        if not _source_changes(checkouts.source, source_base, source_head):
            raise MaterializationReopenError("Source contains no fix after the failed run")
        try:
            load_committed_task(
                checkouts.source, task_id, commit=source_head,
                expected_sha256=str(record.get("task_contract_sha256", "")),
            )
        except Exception as exc:
            raise MaterializationReopenError(
                "task contract changed at the host-fix commit") from exc

        checkout = Path(str(record.get("checkout", ""))).resolve()
        original_commit = str(original["commit"])
        plan = {
            "schema_version": SCHEMA_VERSION,
            "task_id": task_id,
            "applied": False,
            "materialized_commit": expected_candidate,
            "restore_candidate_commit": original_commit,
            "host_fix_commit": host_fix_commit,
            "failed_validation_sha256": expected_failure_sha256,
            "validation_error": failure.get("validation_error"),
            "checkout": str(checkout),
            "preserved_ref": f"refs/materialization-reopen/{task_id}/{expected_candidate}",
            "next_status": "needs_materialization",
        }

        with _exclusive_file_lock(source_lock, timeout_seconds=10):
            registry = _read_registry(registry_path, checkouts.source)
            if any(item.get("task_id") == task_id for item in registry["reservations"]):
                raise MaterializationReopenError("task still has an active admission")
            if not apply:
                return plan

            # Preserve the materialized commit BEFORE moving the branch. A
            # reopen must never be the reason a commit becomes unreachable,
            # even one we intend to replace.
            git(checkout, "update-ref", plan["preserved_ref"], expected_candidate)
            head = git(checkout, "rev-parse", "HEAD").decode().strip()
            if head != expected_candidate:
                raise MaterializationReopenError(
                    "checkout HEAD is not the materialized commit this request names")
            git(checkout, "reset", "--hard", original_commit)
            after = git(checkout, "rev-parse", "HEAD").decode().strip()
            if after != original_commit:
                raise MaterializationReopenError("checkout did not return to the original candidate")
            if git(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
                raise MaterializationReopenError("checkout is not clean after reopen")

            lineage = record.get("candidate_lineage")
            if not isinstance(lineage, list):
                lineage = []
            lineage.append({
                "kind": "unity_materialization_failed",
                "candidate": copy.deepcopy(dict(candidate)),
                "reopened_at": _now(),
                "host_fix_commit": host_fix_commit,
                "preserved_ref": plan["preserved_ref"],
            })
            record["candidate_lineage"] = lineage
            record["candidate"] = copy.deepcopy(dict(original))
            record["status"] = "needs_materialization"
            record["approval"] = None
            record["human_review"] = None
            record.pop("materialization_failure", None)
            record["materialization_reopen"] = {
                "schema_version": SCHEMA_VERSION,
                "reopened_at": _now(),
                "materialized_commit": expected_candidate,
                "host_fix_commit": host_fix_commit,
                "failed_validation_sha256": expected_failure_sha256,
                "preserved_ref": plan["preserved_ref"],
            }
            write_record(record_path, record)

        plan["applied"] = True
        return plan


__all__ = ["MaterializationReopenError", "reopen_materialization", "SCHEMA_VERSION"]
