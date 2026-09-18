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
            if is_finished_worker(candidate):
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
