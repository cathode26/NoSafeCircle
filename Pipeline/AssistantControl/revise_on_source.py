"""Send a rejected candidate back for crew work, reconciled with current Source.

THE DOUBLE-BIND THIS EXISTS FOR. A candidate that failed authoritative Unity
validation needs another crew pass. `revise` is built for exactly that -- it
names `unity_materialization_failed` as a "fresh" feedback mode -- and refuses
once Source has moved, on two guards that are both correct:

    revisions.py:115  merge-base --is-ancestor <source_head> <candidate>
                      `revise` sets record["source_commit"] = candidate, so the
                      candidate must already CONTAIN Source or the task loses
                      main's progress from its view.
    revisions.py:119  load_committed_task(commit=source_head,
                      expected_sha256=<the record's OLD pin>)

The only command that brings a candidate forward is `sync-candidate`, and it
refuses this candidate kind at `review.py:117-121` before reaching either. So
the sequence is broken at step one, and both remaining frozen rooms sit in it:

    NSC-046  a83fc0ff  pin 4f7c2b44   main holds 154521d1
    NSC-048  79308ab9  pin c109a17d   main holds 4a314c9b
    both: crew-review authority intact, original candidate retained,
          source_commit 04d37a7c5, which main left behind long ago.

WHAT THIS DOES. It reconciles the rejected work with an explicitly inspected
Source, adopts an explicitly named contract, and publishes a PREPARED record with
NO ACTIVE CANDIDATE -- the shape `scope`/`reserve`/`run-worker` consume. It never
publishes `source_synchronized` or `awaiting_human`, because neither is true:
nothing here has been tested and nothing is awaiting a human.

WHAT IT REFUSES TO PRETEND. Carrying an implementation forward as INPUT to fresh
work is sound; carrying its old VALIDATION AUTHORITY forward is not. The failed
candidate, its failure, its pin and its lineage are archived unchanged, and the
new contract must be named on the command line -- adopting "whatever is at HEAD"
is the decision this refuses to make silently.

Design reviewed by Astra:
`C:/nscrev/codex-jobs/codex-advice-syncrevise-20260922-2114.report.md`.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import uuid
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

SCHEMA_VERSION = "assistant-revise-on-source/v1"
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ReviseOnSourceError(ValueError):
    """Cannot reconcile this candidate, with a reason an operator can act on."""


def _commit(value: str, field: str) -> str:
    if type(value) is not str or not _COMMIT.fullmatch(value):
        raise ReviseOnSourceError(f"{field} must be an exact full commit")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def revise_on_source(
    checkouts: Checkouts,
    task_id: str,
    *,
    expected_candidate: str,
    expected_source_commit: str,
    accept_contract_sha256: str,
    reason: str,
    apply: bool = False,
) -> dict[str, Any]:
    """Plan, or perform, the reconciliation of ONE rejected candidate.

    Read-only by default. `expected_source_commit` is the Source the operator
    INSPECTED, and `accept_contract_sha256` is the contract they are adopting;
    both are named explicitly so neither is decided by whatever HEAD happens to
    be when a subprocess runs.
    """
    task_id = validate_task_id(task_id)
    expected_candidate = _commit(expected_candidate, "candidate commit")
    expected_source_commit = _commit(expected_source_commit, "inspected source commit")
    if type(accept_contract_sha256) is not str or not _SHA256.fullmatch(accept_contract_sha256):
        raise ReviseOnSourceError("the accepted contract must be an exact sha256")
    if type(reason) is not str or not reason.strip():
        raise ReviseOnSourceError("a reconciliation needs a stated reason")

    record_path = checkouts.records / f"{task_id}.json"
    source_lock, registry_path = _source_registry_paths(checkouts.source)

    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        if not record_path.is_file():
            raise ReviseOnSourceError(f"no owned task record for {task_id}")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("task_id") != task_id or record.get("source") != str(checkouts.source):
            raise ReviseOnSourceError("task record identity differs")
        if record.get("approval") is not None:
            raise ReviseOnSourceError(
                "an approved candidate is not reconciled here; that is an integration decision")
        if record.get("status") != "validation_failed":
            raise ReviseOnSourceError(
                f"reconciliation is for a candidate that FAILED authoritative validation, "
                f"not {record.get('status')!r}")

        candidate = record.get("candidate")
        if not isinstance(candidate, Mapping):
            raise ReviseOnSourceError("record carries no candidate")
        if candidate.get("kind") != "unity_materialization_failed":
            raise ReviseOnSourceError(
                f"reconciliation is for a failed MATERIALIZED candidate, not "
                f"{candidate.get('kind')!r}")
        if candidate.get("commit") != expected_candidate:
            raise ReviseOnSourceError("candidate differs from the exact request")
        if candidate.get("source_candidate_crew_review") is not True:
            raise ReviseOnSourceError(
                "candidate lost its crew-review authority; there is no work to carry forward")

        failure = record.get("materialization_failure")
        if not isinstance(failure, Mapping):
            raise ReviseOnSourceError("record carries no materialization failure")

        worker = record.get("worker")
        if isinstance(worker, Mapping) and worker.get("capacity_released") is not True:
            raise ReviseOnSourceError(
                "the prior worker has not released capacity; settle it first")

        source_head = git(checkouts.source, "rev-parse", "HEAD").decode().strip()
        if source_head != expected_source_commit:
            raise ReviseOnSourceError(
                "Source HEAD differs from the inspected commit; re-inspect and re-run")
        old_source = str(record.get("source_commit", ""))
        if old_source == source_head:
            raise ReviseOnSourceError(
                "Source has not advanced past the candidate's base; ordinary revise applies")

        # The adopted contract is named, never inferred. `revise` refuses when
        # the contract moved precisely so that carrying work across a changed
        # task is a decision somebody makes rather than a side effect.
        task = load_committed_task(
            checkouts.source, task_id, commit=source_head,
            expected_sha256=accept_contract_sha256)
        if task.get("id") != task_id:
            raise ReviseOnSourceError("the accepted contract is not this task")

        checkout = Path(str(record.get("checkout", ""))).resolve()
        head = git(checkout, "rev-parse", "HEAD").decode().strip()
        if head != expected_candidate:
            raise ReviseOnSourceError("checkout HEAD is not the candidate this request names")
        if git(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
            raise ReviseOnSourceError("task checkout is not clean; preserve those changes first")

        operation = uuid.uuid4().hex[:12]
        staging = checkouts.root / f".{task_id}-revise-{operation}"
        archive_dir = checkouts.records / "revise-on-source"
        archive = archive_dir / f"{task_id}.{expected_candidate}.{source_head}.json"

        plan = {
            "schema_version": SCHEMA_VERSION,
            "task_id": task_id,
            "applied": False,
            "rejected_candidate": expected_candidate,
            "old_source_commit": old_source,
            "old_contract_sha256": record.get("task_contract_sha256"),
            "inspected_source_commit": source_head,
            "accepted_contract_sha256": accept_contract_sha256,
            "reason": reason,
            "checkout": str(checkout),
            "staging": str(staging),
            "archived_record": str(archive),
            "next_status": "prepared",
            "carries_no_candidate": True,
            "not_proven": (
                "the reconciled tree has never been built, tested or reviewed. This "
                "carries the rejected implementation forward as INPUT to fresh crew "
                "work; it carries none of its validation authority."
            ),
        }
        if not apply:
            return plan

        with _exclusive_file_lock(source_lock, timeout_seconds=10):
            registry = _read_registry(registry_path, checkouts.source)
            if any(item.get("task_id") == task_id for item in registry["reservations"]):
                raise ReviseOnSourceError("task still has an active admission; release it first")
            if archive.exists():
                raise ReviseOnSourceError(
                    f"a reconciliation archive already exists for this pair: {archive}")

            # Merge in STAGING, never in the task checkout: a conflict must not
            # leave the owned checkout half-merged.
            if staging.exists():
                raise ReviseOnSourceError(f"staging path already exists: {staging}")
            git(checkouts.root, "clone", "--no-local", "--no-checkout",
                str(checkout), str(staging), timeout_seconds=300)
            try:
                git(staging, "config", "core.hooksPath", "/dev/null")
                git(staging, "checkout", "-b", f"assistant-revise/{task_id}-{operation}",
                    expected_candidate, timeout_seconds=180)
                git(staging, "fetch", "--no-tags", str(checkouts.source), source_head,
                    timeout_seconds=300)
                try:
                    git(staging, "merge", "--no-ff", "--no-edit", "FETCH_HEAD",
                        timeout_seconds=300)
                except RuntimeError as exc:
                    raise ReviseOnSourceError(
                        f"Source merge conflicted; retained staging at {staging}") from exc
                if git(staging, "status", "--porcelain=v1", "--untracked-files=all"):
                    raise ReviseOnSourceError(
                        f"staging merge is dirty; retained staging at {staging}")
                merged = git(staging, "rev-parse", "HEAD").decode().strip()
                # The reconciled baseline must genuinely contain Source, and its
                # contract must be the one that was accepted. Both are checked
                # on M itself rather than inferred from the merge succeeding.
                git(staging, "merge-base", "--is-ancestor", source_head, merged)
                load_committed_task(staging, task_id, commit=merged,
                                    expected_sha256=accept_contract_sha256)

                archive_dir.mkdir(parents=True, exist_ok=True)
                archive.write_text(json.dumps({
                    "schema_version": SCHEMA_VERSION, "task_id": task_id,
                    "archived_at": _now(), "reason": reason,
                    "rejected_candidate": copy.deepcopy(dict(candidate)),
                    "materialization_failure": copy.deepcopy(dict(failure)),
                    "old_source_commit": old_source,
                    "old_contract_sha256": record.get("task_contract_sha256"),
                    "failure_sha256": validation_failure_sha256(failure),
                    "candidate_lineage": copy.deepcopy(record.get("candidate_lineage", [])),
                }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

                git(checkout, "fetch", "--no-tags", str(staging), merged, timeout_seconds=300)
                git(checkout, "merge", "--ff-only", "--no-edit", "FETCH_HEAD",
                    timeout_seconds=180)
                if git(checkout, "rev-parse", "HEAD").decode().strip() != merged:
                    raise ReviseOnSourceError("task checkout did not fast-forward to the merge")
            finally:
                if staging.exists() and plan.get("staging_retained") is not True:
                    shutil.rmtree(staging, ignore_errors=True)

            history = record.setdefault("revise_on_source_history", [])
            history.append({
                "schema_version": SCHEMA_VERSION, "at": _now(), "reason": reason,
                "rejected_candidate": expected_candidate,
                "old_contract_sha256": record.get("task_contract_sha256"),
                "accepted_contract_sha256": accept_contract_sha256,
                "reconciled_commit": merged, "archived_record": str(archive),
            })
            record["status"] = "prepared"
            record["source_commit"] = merged
            record["task_contract_sha256"] = accept_contract_sha256
            # No active candidate: nothing here has been built or reviewed, and
            # a record that still names one invites a reader to believe it has.
            record.pop("candidate", None)
            record.pop("materialization_failure", None)
            record.pop("human_review", None)
            write_record(record_path, record)
            plan["applied"] = True
            plan["reconciled_commit"] = merged
            return plan


__all__ = ["ReviseOnSourceError", "revise_on_source", "SCHEMA_VERSION"]
