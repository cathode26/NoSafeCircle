"""Whether a recorded run is finished, shared by the gates that must not block on history.

`settle-worker` updates a worker entry rather than removing it, and `retire-worker` archives it into
`worker_history`. Both leave evidence of a finished run in the record, so any gate that tests for the
*presence* of that evidence refuses forever. These predicates let a gate ask the question it means:
is this run still going?
"""
from __future__ import annotations

from typing import Any, Mapping


# `succeeded` is deliberately absent. A successful run's output belongs to the review path,
# and treating it as finished here would let a caller scope or refresh over real work.
FINISHED_WORKER_STATUSES = frozenset({"failed", "stopped"})


def is_finished_worker(entry: Any) -> bool:
    """True when a worker entry describes a run that ended and was settled.

    `capacity_released` and `settled_at` are both required: `settle-worker` writes them only
    after verifying the host process and the run's containers are gone, so together they are
    the record's proof that nothing is still running.
    """

    return (isinstance(entry, Mapping)
            and entry.get("status") in FINISHED_WORKER_STATUSES
            and entry.get("capacity_released") is True
            and bool(entry.get("settled_at")))


def is_settled_worker(entry: Any) -> bool:
    """True when the record proves this run's process and containers are gone.

    Split out of `is_finished_worker` so the withdrawn-output case below can reuse
    the settlement proof WITHOUT relaxing it. Settlement is never waived.
    """

    return (isinstance(entry, Mapping)
            and entry.get("capacity_released") is True
            and bool(entry.get("settled_at")))


def output_was_withdrawn(record: Mapping[str, Any], entry: Any) -> bool:
    """True when `revise-on-source` explicitly withdrew THIS run's output.

    The single named form of a question four gates have now had to ask. A crew can
    succeed and still leave nothing in the review path: `revise-on-source` archives
    the rejected candidate, carries its implementation forward as INPUT to fresh
    work, and deliberately discards its validation authority. After that the run is
    as over as a failed one, but `status` still reads "succeeded" forever.

    The exclusion of "succeeded" from `FINISHED_WORKER_STATUSES` is RIGHT for every
    other case and is not being softened -- a successful run's output does belong to
    the review path. This is the one case where the record itself proves the output
    left it.

    The discriminator is two facts already on the record, compared by identity
    rather than by timestamp:

      * the newest withdrawal produced the baseline the task sits on NOW
        (`reconciled_commit` == `record["source_commit"]`), and
      * this run worked against a Source that withdrawal superseded
        (`source_head` is present and is not that commit).

    A run dispatched AFTER the reconciliation carries the reconciled commit as its
    own `source_head`, so it fails the second test and is still treated as live.
    That is the case this must never swallow: a succeeded crew whose candidate is
    merely waiting to be harvested. An absent `source_head` is refused rather than
    waved through, because the permissive direction here lets a gate re-dispatch
    over work that may still be real.
    """

    if not isinstance(entry, Mapping):
        return False
    history = record.get("revise_on_source_history")
    if not isinstance(history, list) or not history:
        return False
    newest = history[-1]
    if not isinstance(newest, Mapping):
        return False
    reconciled = newest.get("reconciled_commit")
    if not isinstance(reconciled, str) or not reconciled:
        return False
    if reconciled != record.get("source_commit"):
        return False
    worked_against = entry.get("source_head")
    return (isinstance(worked_against, str) and bool(worked_against)
            and worked_against != reconciled)


def finished_run_ids(record: Mapping[str, Any]) -> set[str]:
    """Run ids the record itself proves are over, live entry and archive alike."""

    finished: set[str] = set()
    for entry in (record.get("worker"), *(record.get("worker_history") or ())):
        if not isinstance(entry, Mapping):
            continue
        # Two archive shapes exist: `retire-worker` copies the worker's fields to the top
        # level, while `worker_launcher` nests them under "worker". Read both, or a run
        # archived by one of them would not count as finished by the other.
        for candidate in (entry, entry.get("worker")):
            # A settled run whose output was withdrawn is as over as a failed one;
            # settlement is still required, only the status test is widened.
            if is_finished_worker(candidate) or (
                    is_settled_worker(candidate)
                    and output_was_withdrawn(record, candidate)):
                run_id = candidate.get("run_id") or entry.get("run_id")
                if isinstance(run_id, str):
                    finished.add(run_id)
    return finished


def is_finished_launch(record: Mapping[str, Any], launch: Any) -> bool:
    """True when a launcher record belongs to a run the record proves is over.

    A launch keeps whatever status it had when the launcher wrote it, so a finished run can
    leave `ready_pending` behind. `source_update._require_settled_worker` already resolves this
    the same way: the settled worker is the authoritative proof for the pair sharing its run id.
    """

    if not isinstance(launch, Mapping):
        return False
    if is_finished_worker(launch):
        return True
    run_id = launch.get("run_id")
    return isinstance(run_id, str) and run_id in finished_run_ids(record)
