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
import os
import re
import shutil
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.candidate_validation_retry import validation_failure_sha256
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.reconciliation_binding import (
    HUMAN_REJECTION,
    MATERIALIZATION_FAILURE,
    ReconciliationBindingError,
    candidate_receipt_problem,
    canonical_sha256,
    review_entry_index,
)
from Pipeline.AssistantControl.worker_state import is_settled_worker
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity

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


def _remove_staging(staging: Path, plan: dict[str, Any]) -> None:
    """Delete a finished staging clone, and SAY SO when it cannot be deleted.

    This was ``shutil.rmtree(staging, ignore_errors=True)``, which on Windows
    silently fails: git marks objects and packs read-only, and rmtree cannot
    unlink a read-only file. Every successful reconciliation therefore left a
    full ``--no-local`` clone behind -- a complete copy of the checkout, one per
    run, accumulating in the checkouts root with nothing reporting it.

    Found by a test written for a DIFFERENT defect: asserting that success does
    not litter is what surfaced it. ``ignore_errors=True`` is what made it
    invisible, which is the same shape as a guard that cannot fail.
    """
    def clear_readonly(function, path, _info):
        try:
            os.chmod(path, stat.S_IWRITE)
        except OSError:
            return
        function(path)

    shutil.rmtree(staging, onexc=clear_readonly)
    if staging.exists():
        # Never raise from the cleanup path: it runs in a `finally` and would
        # replace whatever real error is already in flight. Record it instead,
        # so a leaked clone is visible rather than merely absent from the logs.
        plan["staging_cleanup_failed"] = str(staging)


def _resume_interrupted(
    checkouts,
    task_id: str,
    record: dict[str, Any],
    record_path: Path,
    journal_path: Path,
    *,
    expected_candidate: str,
    expected_source_commit: str,
    accept_contract_sha256: str,
    apply: bool,
) -> dict[str, Any] | None:
    """Finish, or refuse to guess at, a reconciliation that was interrupted.

    THE STRANDING THIS REMOVES, found by Astra in the code as it stood. The
    archive is written BEFORE the owned checkout advances and the authoritative
    record AFTER it, so a crash between those two leaves one of two states and
    NEITHER could be retried:

        archive written, checkout still at C   ->  "a reconciliation archive
                                                   already exists for this pair"
        checkout at M, record still names C    ->  "checkout HEAD is not the
                                                   candidate this request names"

    Both messages describe a symptom, neither offers a route, and the task this
    command exists to rescue is stranded exactly as before.

    Returning None means "nothing durable happened; retry normally". Recovery is
    otherwise EXACT-REQUEST only: the journal names the request it was serving,
    and this finishes just that one, with the world in just the state the
    interrupted run left it. Anything else is refused WITH the journal path,
    because guessing which half-finished operation an operator meant is how a
    recovery path destroys work.
    """
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReviseOnSourceError(
            f"an interrupted reconciliation is journalled at {journal_path} and cannot "
            f"be read; inspect it before retrying") from exc
    if not isinstance(journal, Mapping):
        raise ReviseOnSourceError(
            f"the reconciliation journal at {journal_path} is not a record; inspect it")

    same_request = (
        journal.get("schema_version") == SCHEMA_VERSION
        and journal.get("task_id") == task_id
        and journal.get("rejected_candidate") == expected_candidate
        and journal.get("inspected_source_commit") == expected_source_commit
        and journal.get("accepted_contract_sha256") == accept_contract_sha256
    )
    if not same_request:
        raise ReviseOnSourceError(
            f"an interrupted reconciliation for a DIFFERENT request is journalled at "
            f"{journal_path}; resolve that one before starting another")

    merged = journal.get("reconciled_commit")
    archive = Path(str(journal.get("archived_record", "")))
    checkout = Path(str(record.get("checkout", "")))
    if not isinstance(merged, str) or not _COMMIT.fullmatch(merged):
        raise ReviseOnSourceError(
            f"the reconciliation journal at {journal_path} names no reconciled commit")

    head = git(checkout, "rev-parse", "HEAD").decode().strip()
    dirty = bool(git(checkout, "status", "--porcelain=v1", "--untracked-files=all"))

    if head == expected_candidate and not dirty and not archive.exists():
        # Interrupted before anything durable was written. The staging clone is
        # disposable and carries a fresh uuid per run, so there is nothing to
        # reconcile with: clear the journal and let the caller start over.
        journal_path.unlink()
        return None

    if record.get("status") == "prepared" and record.get("source_commit") == merged:
        # The record write landed and only the journal removal did not. The
        # operation is complete; saying so is the whole remedy.
        journal_path.unlink()
        return {
            "schema_version": SCHEMA_VERSION, "task_id": task_id, "applied": True,
            "resumed": "journal_only", "rejected_candidate": expected_candidate,
            "inspected_source_commit": expected_source_commit,
            "reconciled_commit": merged, "archived_record": str(archive),
            "next_status": "prepared", "carries_no_candidate": True,
        }

    if head != merged or dirty or not archive.exists():
        raise ReviseOnSourceError(
            f"a reconciliation was interrupted and this cannot finish it from here: "
            f"journal {journal_path}, phase {journal.get('phase')!r}, archive "
            f"{'present' if archive.exists() else 'absent'}, checkout HEAD {head}"
            f"{' (dirty)' if dirty else ''}. Inspect those before retrying.")

    plan = {
        "schema_version": SCHEMA_VERSION, "task_id": task_id, "applied": False,
        "resumed": "record_write", "rejected_candidate": expected_candidate,
        "inspected_source_commit": expected_source_commit,
        "reconciled_commit": merged, "archived_record": str(archive),
        "next_status": "prepared", "carries_no_candidate": True,
        "not_proven": (
            "the reconciled tree has never been built, tested or reviewed. This "
            "carries the rejected implementation forward as INPUT to fresh crew "
            "work; it carries none of its validation authority."
        ),
    }
    if not apply:
        return plan

    entry = journal.get("history_entry")
    if not isinstance(entry, Mapping):
        raise ReviseOnSourceError(
            f"the reconciliation journal at {journal_path} carries no history entry to publish")
    _publish_reconciled(record, dict(entry), merged, accept_contract_sha256)
    write_record(record_path, record)
    journal_path.unlink()
    plan["applied"] = True
    return plan


def _publish_reconciled(record: dict[str, Any], entry: dict[str, Any], merged: str,
                        accept_contract_sha256: str) -> None:
    """Move the record onto the reconciled baseline. The ONE writer of that shape.

    Called from the normal path and from the interrupted-run recovery, so a
    resumed reconciliation cannot publish a differently-shaped record from the
    one an uninterrupted run would have published.
    """
    record.setdefault("revise_on_source_history", []).append(entry)
    record["status"] = "prepared"
    record["source_commit"] = merged
    record["task_contract_sha256"] = accept_contract_sha256
    # No active candidate: nothing here has been built or reviewed, and a record
    # that still names one invites a reader to believe it has.
    record.pop("candidate", None)
    record.pop("materialization_failure", None)
    record.pop("human_review", None)
    # `review_history` is deliberately NOT popped: the withdrawal binds one of
    # its entries by index and hash, and dropping it would break that binding.
    record.pop("revision", None)


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
        journal_path = (checkouts.records / "revise-on-source" /
                        f"{task_id}.in-progress.json")
        if journal_path.is_file():
            # BEFORE the HEAD and status guards below, deliberately: an
            # interrupted run leaves the world in a state those guards refuse,
            # and refusing is what stranded the task in the first place.
            resumed = _resume_interrupted(
                checkouts, task_id, record, record_path, journal_path,
                expected_candidate=expected_candidate,
                expected_source_commit=expected_source_commit,
                accept_contract_sha256=accept_contract_sha256, apply=apply)
            if resumed is not None:
                return resumed

        if record.get("approval") is not None:
            raise ReviseOnSourceError(
                "an approved candidate is not reconciled here; that is an integration decision")
        candidate = record.get("candidate")
        if not isinstance(candidate, Mapping):
            raise ReviseOnSourceError("record carries no candidate")
        if candidate.get("commit") != expected_candidate:
            raise ReviseOnSourceError("candidate differs from the exact request")

        # TWO WAYS INTO ONE TRANSITION, AND THEY ARE NOT THE SAME FACT.
        #
        # The original basis is a MATERIALIZED candidate that failed
        # authoritative Unity validation. The second is an exact HUMAN REJECTION
        # of a registered crew candidate -- which is the shape every stranded
        # task on the board actually has, and which used to fall out of here as
        # "reconciliation is for a candidate that FAILED authoritative
        # validation, not 'changes_requested'".
        #
        # Astra, on whether the second is enough: "an exact human rejection is
        # sufficient reason to withdraw an authenticated crew candidate and
        # prepare it for fresh crew work on current Source. Crew provenance,
        # checkout ownership, settlement, scope and execution authorization
        # remain separate requirements." Each of those is checked separately
        # below and none of them is waived here.
        #
        # They enter ONE transition on purpose. What differs is the BASIS: what
        # is being withdrawn, and what the next crew has to be told about it.
        status = record.get("status")
        failure: Mapping[str, Any] | None = None
        review: Mapping[str, Any] | None = None
        review_index = -1
        review_digest = ""
        if status == "validation_failed":
            basis = MATERIALIZATION_FAILURE
            if candidate.get("kind") != "unity_materialization_failed":
                raise ReviseOnSourceError(
                    f"reconciliation is for a failed MATERIALIZED candidate, not "
                    f"{candidate.get('kind')!r}")
            if candidate.get("source_candidate_crew_review") is not True:
                raise ReviseOnSourceError(
                    "candidate lost its crew-review authority; there is no work to carry forward")
            failure = record.get("materialization_failure")
            if not isinstance(failure, Mapping):
                raise ReviseOnSourceError("record carries no materialization failure")
        elif status == "changes_requested":
            basis = HUMAN_REJECTION
            review = record.get("human_review")
            if not isinstance(review, Mapping) or review.get("decision") != "reject":
                raise ReviseOnSourceError(
                    "reconciliation on a human basis needs an exact recorded rejection")
            if review.get("commit") != expected_candidate:
                raise ReviseOnSourceError(
                    "the recorded rejection names a different commit from the request")
            message = review.get("message")
            if not isinstance(message, str) or not message.strip() or "\x00" in message:
                raise ReviseOnSourceError("the rejection carries no feedback a crew could use")
            if len(message.encode("utf-8")) > 64 * 1024:
                raise ReviseOnSourceError(
                    "the rejection exceeds the bounded feedback size a crew is given")
            # PROVENANCE, NOT AUTHORITY, AND THEY ARE ORTHOGONAL. The rejection
            # establishes that the named work needs changes; it establishes
            # nothing about who produced it. `source_candidate_crew_review` is a
            # MATERIALIZATION field and testing for it here would exclude
            # exactly the earlier-stage crew candidates this branch exists for.
            # A raw crew candidate proves its own provenance through its
            # registered commit receipt instead.
            problem = candidate_receipt_problem(record, candidate, task_id)
            if problem is not None:
                raise ReviseOnSourceError(
                    f"candidate is not an authenticated crew result: {problem}")
            # Bind the rejection by IDENTITY now, at plan time, so a request
            # that could never produce usable feedback fails before it moves
            # anything. `review_history` is append-only, so the index is stable;
            # the hash is what catches a later hand edit.
            try:
                review_index = review_entry_index(record, review)
            except ReconciliationBindingError as exc:
                raise ReviseOnSourceError(str(exc)) from exc
            review_digest = canonical_sha256(dict(review))
        else:
            raise ReviseOnSourceError(
                f"reconciliation is for a candidate that FAILED authoritative validation "
                f"or was rejected by a human, not {status!r}")

        worker = record.get("worker")
        if isinstance(worker, Mapping) and worker.get("capacity_released") is not True:
            raise ReviseOnSourceError(
                "the prior worker has not released capacity; settle it first")
        if (basis == HUMAN_REJECTION and isinstance(worker, Mapping)
                and not is_settled_worker(worker)):
            # Released capacity is not settlement. `settle-worker` writes
            # `settled_at` only after verifying the host process and the run's
            # containers are gone, and this path re-dispatches the task.
            raise ReviseOnSourceError(
                "the prior worker is not settled; its process or containers may still be running")

        # The runs whose output this withdrawal removes from the review path.
        # `output_was_withdrawn()` derives this today by comparing baselines,
        # which cannot tell WHICH run produced the candidate -- these two ids
        # already differ on NSC-118. Naming them is cheap now and impossible to
        # retrofit onto an entry once it is written.
        withdrawn_run_ids = sorted({
            run for run in (candidate.get("run_id"),
                            worker.get("run_id") if isinstance(worker, Mapping) else None)
            if isinstance(run, str) and run.strip()
        })

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
            "withdrawal_basis": basis,
            "withdrawn_run_ids": withdrawn_run_ids,
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
                # A CLONE DOES NOT INHERIT user.name/user.email from the source
                # repository's local config -- it falls through to the host's
                # global identity. The merge below WRITES A COMMIT, so without
                # this the reconciled baseline is authored by whoever owns the
                # machine. Reproduced by Astra's audit as merge 4da00660e,
                # authored by the fixture host despite the NSC automation
                # variables being set. Second instance of this class.
                name, email = validated_agent_git_identity()
                git(staging, "config", "user.name", name)
                git(staging, "config", "user.email", email)
                git(staging, "checkout", "-b", f"assistant-revise/{task_id}-{operation}",
                    expected_candidate, timeout_seconds=180)
                git(staging, "fetch", "--no-tags", str(checkouts.source), source_head,
                    timeout_seconds=300)
                try:
                    git(staging, "merge", "--no-ff", "--no-edit", "FETCH_HEAD",
                        timeout_seconds=300)
                except RuntimeError as exc:
                    # RETAIN IT, because the message says so. `staging_retained`
                    # was read in the finally block and set NOWHERE, so this
                    # directory was deleted on the way out and the error named a
                    # path the reader could no longer open. The staging path
                    # carries a fresh uuid per run, so keeping it blocks no
                    # retry -- it only preserves the conflict for inspection.
                    plan["staging_retained"] = True
                    raise ReviseOnSourceError(
                        f"Source merge conflicted; retained staging at {staging}") from exc
                if git(staging, "status", "--porcelain=v1", "--untracked-files=all"):
                    plan["staging_retained"] = True
                    raise ReviseOnSourceError(
                        f"staging merge is dirty; retained staging at {staging}")
                merged = git(staging, "rev-parse", "HEAD").decode().strip()
                # The reconciled baseline must genuinely contain Source, and its
                # contract must be the one that was accepted. Both are checked
                # on M itself rather than inferred from the merge succeeding.
                git(staging, "merge-base", "--is-ancestor", source_head, merged)
                load_committed_task(staging, task_id, commit=merged,
                                    expected_sha256=accept_contract_sha256)

                history_entry: dict[str, Any] = {
                    "schema_version": SCHEMA_VERSION, "at": _now(), "reason": reason,
                    "withdrawal_basis": basis,
                    "rejected_candidate": expected_candidate,
                    "rejected_candidate_tree": candidate.get("tree"),
                    "withdrawn_run_ids": withdrawn_run_ids,
                    "old_contract_sha256": record.get("task_contract_sha256"),
                    "accepted_contract_sha256": accept_contract_sha256,
                    # Admission needs the Source this merged. Entries written
                    # before this field existed force it to be derived from
                    # parent order.
                    "inspected_source_commit": source_head,
                    "reconciled_commit": merged, "archived_record": str(archive),
                }
                archive_body: dict[str, Any] = {
                    "schema_version": SCHEMA_VERSION, "task_id": task_id,
                    "archived_at": _now(), "reason": reason,
                    "withdrawal_basis": basis,
                    "rejected_candidate": copy.deepcopy(dict(candidate)),
                    "old_source_commit": old_source,
                    "old_contract_sha256": record.get("task_contract_sha256"),
                    "inspected_source_commit": source_head,
                    "reconciled_commit": merged,
                    "withdrawn_run_ids": withdrawn_run_ids,
                    "candidate_lineage": copy.deepcopy(record.get("candidate_lineage", [])),
                }
                if failure is not None:
                    archive_body["materialization_failure"] = copy.deepcopy(dict(failure))
                    archive_body["failure_sha256"] = validation_failure_sha256(failure)
                if review is not None:
                    # THE TYPED BINDING. Frozen here rather than looked up at
                    # dispatch: a correction landing after dispatch would
                    # otherwise change what a running crew had been told, with
                    # nothing in the record showing the feedback had moved.
                    frozen = copy.deepcopy(dict(review))
                    history_entry["rejected_review"] = frozen
                    history_entry["review_entry_index"] = review_index
                    history_entry["review_entry_sha256"] = review_digest
                    archive_body["rejected_review"] = copy.deepcopy(dict(review))
                    archive_body["review_entry_index"] = review_index
                    archive_body["review_entry_sha256"] = review_digest
                stale_revision = record.get("revision")
                if isinstance(stale_revision, Mapping):
                    # Astra: an ordinary `revision` left in place reintroduces
                    # the blockage -- admission examines it BEFORE reconciliation
                    # history, and worker retirement refuses an active revision.
                    # Archive it into the entry rather than dropping it silently.
                    history_entry["archived_revision"] = copy.deepcopy(dict(stale_revision))
                    archive_body["archived_revision"] = copy.deepcopy(dict(stale_revision))

                archive_dir.mkdir(parents=True, exist_ok=True)
                # THE JOURNAL GOES DOWN FIRST, before ANY durable write. A crash
                # from here on is recoverable by name; a crash before this point
                # touched nothing.
                write_record(journal_path, {
                    "schema_version": SCHEMA_VERSION, "task_id": task_id,
                    "phase": "merged", "operation": operation, "created_at": _now(),
                    "rejected_candidate": expected_candidate,
                    "inspected_source_commit": source_head,
                    "accepted_contract_sha256": accept_contract_sha256,
                    "reconciled_commit": merged, "archived_record": str(archive),
                    "checkout": str(checkout), "history_entry": history_entry,
                })
                archive.write_text(json.dumps(
                    archive_body, ensure_ascii=False, indent=2, sort_keys=True,
                ) + "\n", encoding="utf-8")

                git(checkout, "fetch", "--no-tags", str(staging), merged, timeout_seconds=300)
                git(checkout, "merge", "--ff-only", "--no-edit", "FETCH_HEAD",
                    timeout_seconds=180)
                if git(checkout, "rev-parse", "HEAD").decode().strip() != merged:
                    raise ReviseOnSourceError("task checkout did not fast-forward to the merge")
                write_record(journal_path, {
                    "schema_version": SCHEMA_VERSION, "task_id": task_id,
                    "phase": "checkout_advanced", "operation": operation,
                    "created_at": _now(),
                    "rejected_candidate": expected_candidate,
                    "inspected_source_commit": source_head,
                    "accepted_contract_sha256": accept_contract_sha256,
                    "reconciled_commit": merged, "archived_record": str(archive),
                    "checkout": str(checkout), "history_entry": history_entry,
                })
            finally:
                if staging.exists() and plan.get("staging_retained") is not True:
                    _remove_staging(staging, plan)

            _publish_reconciled(record, history_entry, merged, accept_contract_sha256)
            write_record(record_path, record)
            # Last: the journal only stops being needed once the authoritative
            # record agrees with it.
            journal_path.unlink(missing_ok=True)
            plan["applied"] = True
            plan["reconciled_commit"] = merged
            return plan


__all__ = ["ReviseOnSourceError", "revise_on_source", "SCHEMA_VERSION"]
