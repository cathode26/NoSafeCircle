"""Authorize another materialization attempt for an INTACT candidate.

`reopen-materialization` and this are different transitions, and conflating them
is how NSC-048 stayed frozen with everything about it correct:

    reopen  a NEW MATERIALIZED COMMIT failed validation. The candidate was
            REPLACED with kind `unity_materialization_failed`
            (`unity_materialization._finalize_validation_failure`), so reopen
            preserves that commit and RESETS the branch back to the retained
            original.
    retry   the materialization ATTEMPT failed with its input candidate
            untouched. `_record_materialization_failure` only writes the failure
            and changes status; no candidate was replaced and no branch moved.
            So there is nothing to restore -- only an attempt to retire.

Widening reopen's kind check would have been wrong: everything after it assumes
a retained `original_candidate` and it ends in `reset --hard` to that commit.
This case needs neither.

Measured on NSC-048, 2026-09-23. Its candidate is crew-reviewed and intact, its
worker settled, its builder method present, and the defect that stopped it --
the room registry naming `.Build` where the class declares `BuildAndSave` -- was
fixed host-side hours earlier. The registry is imported by the host from
canonical, so that fix genuinely reaches a parked candidate. Every command
refused anyway, and `reopen` refused with "not None" because the candidate
carries no `kind` key at all.

WHAT THIS DOES NOT CLAIM. It authorizes an attempt; it does not establish that
the attempt will succeed. `host_fix_commit` is provenance, not proof of repair:
it shows Source advanced with changed paths, never that the next run consumes
them. The operator supplies the rationale, and `reason` is recorded so a later
reader can judge it. Notably the validation runner is still selected from the
CANDIDATE checkout, so a host-side runner fix does NOT reach this candidate even
though the registry fix does.

Design reviewed by Astra before implementation; the report is at
`C:/nscrev/codex-jobs/codex-advice-healthyrerun-20260923-0530.report.md`.
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
from Pipeline.AssistantControl.candidate_validation_retry import validation_failure_sha256
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock

SCHEMA_VERSION = "assistant-materialization-retry/v1"
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class MaterializationRetryError(ValueError):
    """Cannot authorize another attempt, with a reason an operator can act on."""


def _commit(value: str, field: str) -> str:
    if type(value) is not str or not _COMMIT.fullmatch(value):
        raise MaterializationRetryError(f"{field} must be an exact full commit")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _journal_path(checkouts: Checkouts, task_id: str, candidate: str) -> Path:
    return checkouts.records / f"{task_id}.unity-materialization.{candidate}.json"


def _archive_paths(checkouts: Checkouts, task_id: str, candidate: str,
                   digest: str) -> tuple[Path, Path, Path]:
    """Archive keyed by candidate AND failure digest, so a second attempt's
    failure cannot overwrite the first one's evidence."""
    directory = checkouts.records / "materialization-retry"
    stem = f"{task_id}.{candidate}.{digest[:16]}"
    return directory, directory / f"{stem}.failure.json", directory / f"{stem}.journal.json"


def retry_materialization(
    checkouts: Checkouts,
    task_id: str,
    *,
    expected_candidate: str,
    expected_failure_sha256: str,
    reason: str,
    apply: bool = False,
) -> dict[str, Any]:
    """Plan, or perform, one authorized re-attempt of a failed materialization.

    Read-only by default. `apply=True` archives the failure and its journal,
    then returns the record to `needs_materialization` so the ORDINARY
    `materialize-candidate` can run against the same candidate SHA. It launches
    no provider, approves nothing and manufactures no validation result.
    """
    task_id = validate_task_id(task_id)
    expected_candidate = _commit(expected_candidate, "candidate commit")
    if type(expected_failure_sha256) is not str or not re.fullmatch(
            r"^[0-9a-f]{64}$", expected_failure_sha256):
        raise MaterializationRetryError("failure digest must be an exact sha256")
    if type(reason) is not str or not reason.strip():
        raise MaterializationRetryError(
            "a retry needs a stated reason; the mechanical checks cannot establish "
            "that the blocker is gone, so the operator's rationale is the evidence")

    record_path = checkouts.records / f"{task_id}.json"
    # LOCK first, then registry. Every other caller unpacks it this way;
    # reversing it parses the lock file as JSON and reports the registry as
    # unreadable, which names neither.
    source_lock, registry_path = _source_registry_paths(checkouts.source)

    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        if not record_path.is_file():
            raise MaterializationRetryError(f"no owned task record for {task_id}")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("task_id") != task_id or record.get("source") != str(checkouts.source):
            raise MaterializationRetryError("task record identity differs")
        if record.get("approval") is not None or record.get("human_review") is not None:
            raise MaterializationRetryError(
                "a reviewed candidate is not retryable; that is an approval decision")
        if record.get("status") != "materialization_failed":
            raise MaterializationRetryError(
                f"retry is for a failed materialization ATTEMPT, not "
                f"{record.get('status')!r}; a candidate that was REPLACED by a failed "
                f"validation is reopen-materialization's case")

        candidate = record.get("candidate")
        if not isinstance(candidate, Mapping):
            raise MaterializationRetryError("record carries no candidate")
        # An ABSENT kind means crew_reviewed, exactly as the materializer reads
        # it; an explicit null does not. NSC-048 has no kind key, which is why
        # reopen refused it with "not None".
        kind = candidate.get("kind", "crew_reviewed")
        if kind != "crew_reviewed":
            raise MaterializationRetryError(
                f"retry preserves an intact crew-reviewed candidate, not {kind!r}")
        if candidate.get("commit") != expected_candidate:
            raise MaterializationRetryError("candidate differs from the exact request")

        failure = record.get("materialization_failure")
        if not isinstance(failure, Mapping):
            raise MaterializationRetryError("record carries no materialization failure")
        # The discriminator that keeps this off reopen's ground: a failure that
        # produced a materialized commit is a VALIDATION failure, and its
        # candidate was replaced. This one failed before any commit existed.
        if failure.get("phase") != "materialization_failed":
            raise MaterializationRetryError(
                f"failure phase is {failure.get('phase')!r}, not a materialization attempt")
        if failure.get("materialized_commit") is not None:
            raise MaterializationRetryError(
                "failure records a materialized commit, so it is a validation failure; "
                "reopen-materialization owns that case")
        actual = validation_failure_sha256(failure)
        if actual != expected_failure_sha256:
            raise MaterializationRetryError("recorded failure differs from the exact request")

        worker = record.get("worker")
        if isinstance(worker, Mapping) and worker.get("capacity_released") is not True:
            raise MaterializationRetryError(
                "the prior worker has not released capacity; settle it first")

        checkout = Path(str(record.get("checkout", ""))).resolve()
        if not (checkout / ".git").exists():
            raise MaterializationRetryError("record does not name a task checkout")
        head = git(checkout, "rev-parse", "HEAD").decode().strip()
        if head != expected_candidate:
            raise MaterializationRetryError(
                "checkout HEAD is not the candidate this request names")
        if git(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
            raise MaterializationRetryError(
                "checkout is not clean; a retry never decides what to discard")

        # The pin is read at the CANDIDATE commit, deliberately. A contract
        # revision that landed on Source while this task sat frozen does not
        # change what THIS candidate was built against, and materialization
        # itself reads it the same way. That is why a moved contract blocks
        # `revise` and `sync-candidate` and does not block this.
        try:
            load_committed_task(
                checkout, task_id, commit=expected_candidate,
                expected_sha256=str(record.get("task_contract_sha256", "")),
            )
        except Exception as exc:
            raise MaterializationRetryError(
                "task contract differs from the record pin at the candidate commit"
            ) from exc

        journal_path = _journal_path(checkouts, task_id, expected_candidate)
        archive_dir, failure_archive, journal_archive = _archive_paths(
            checkouts, task_id, expected_candidate, expected_failure_sha256)

        plan = {
            "schema_version": SCHEMA_VERSION,
            "task_id": task_id,
            "applied": False,
            "candidate_commit": expected_candidate,
            "failure_sha256": expected_failure_sha256,
            "failed_builder": failure.get("builder"),
            "reason": reason,
            "checkout": str(checkout),
            "retained_journal": str(journal_path) if journal_path.is_file() else None,
            "archived_failure": str(failure_archive),
            "archived_journal": str(journal_archive),
            "next_status": "needs_materialization",
            # What applying COSTS, not only what it does. If the re-attempt
            # materializes and then fails validation, the intact candidate is
            # REPLACED and this command can never reach it again.
            "cost_if_validation_fails": (
                "materialization replaces this intact candidate with a degraded "
                "one (kind unity_materialization_failed). retry-materialization "
                "cannot reach that; reopen-materialization becomes the only route "
                "and re-runs the same tests, and revise is refused whenever Source "
                "has advanced past the candidate. Measured on NSC-048."
            ),
        }

        with _exclusive_file_lock(source_lock, timeout_seconds=10):
            registry = _read_registry(registry_path, checkouts.source)
            if any(item.get("task_id") == task_id for item in registry["reservations"]):
                raise MaterializationRetryError("task still has an active admission")
            if not apply:
                return plan

            if failure_archive.exists() or journal_archive.exists():
                raise MaterializationRetryError(
                    "a retry archive already exists for this candidate and failure; "
                    f"inspect it before retrying: {failure_archive}")
            archive_dir.mkdir(parents=True, exist_ok=True)
            if not archive_dir.resolve().is_relative_to(checkouts.records.resolve()):
                raise MaterializationRetryError("retry archive escaped the records directory")

            # Preserve the evidence BEFORE the record becomes runnable, so an
            # interruption can never leave a runnable record whose failure was
            # discarded. `retryable` is archived as it was recorded and is not
            # rewritten into permission.
            failure_archive.write_text(
                json.dumps({"schema_version": SCHEMA_VERSION, "task_id": task_id,
                            "archived_at": _now(), "reason": reason,
                            "materialization_failure": copy.deepcopy(dict(failure))},
                           ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8")

            # The materializer inspects an existing journal BEFORE it checks
            # candidate eligibility, so a status change alone yields "unfinished
            # Unity materialization was retained". Retiring it is not tidying.
            if journal_path.is_file():
                journal_path.rename(journal_archive)
                if journal_path.exists() or not journal_archive.is_file():
                    raise MaterializationRetryError("retained journal could not be archived")

            record["status"] = "needs_materialization"
            record.pop("materialization_failure", None)
            record["materialization_retry"] = {
                "schema_version": SCHEMA_VERSION,
                "candidate_commit": expected_candidate,
                "failure_sha256": expected_failure_sha256,
                "reason": reason,
                "archived_failure": str(failure_archive),
                "archived_journal": str(journal_archive) if plan["retained_journal"] else None,
                "authorized_at": _now(),
            }
            write_record(record_path, record)
            plan["applied"] = True
            return plan


__all__ = ["MaterializationRetryError", "retry_materialization", "SCHEMA_VERSION"]
