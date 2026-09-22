"""Release an admission reservation that no supported action can reach.

``admission.reserve`` takes a reservation BEFORE any process exists: it records
the task, run and lease identity with the resources to be held, and the worker
is launched afterwards by ``worker_launcher.launch_worker``.  Every supported
way of removing a reservation runs from the other end --
``worker_settlement.settle_completed`` proves a *worker* reached a terminal
state and then drops the reservation that worker owned.

So a lease that reserves capacity and never launches leaves a reservation that
nothing can settle.  There is no worker to prove terminal, and
``settle_completed`` refuses because the record's run identity is not the
reservation's.  NSC-046 is the measured case: a 09-18 scope lease took
``task-orch-nsc046-20260918-2`` while the record's launch still described the
already-settled 09-17 run, and the reservation then held two of NSC-101's three
exclusive resources with no command able to name it.

``reset-task`` cannot help either -- it refuses while any reservation for the
task exists -- so the two guards deadlock: the reservation blocks the reset, and
the reset is the only other thing that would have cleared the state.

WHAT IS PROVEN BEFORE ANYTHING IS RELEASED

The point of this module is the proof, not the release.  Hand-editing the
registry would take one line; what that line cannot do is establish that the
run is dead, and a reservation released while its worker is alive hands another
task resources that are actively being written.

Four independent probes, each derivable from the run id alone, so none of them
depends on the record that is already known to be unreliable:

1.  **The run directory.**  ``worker_launcher`` derives it as
    ``<records>/worker-runs/<task_id>/sha256(run_id)`` and creates it under
    ``checkouts.lock`` *before* it spawns anything.  Nothing in the tree ever
    removes or archives a run root -- ``_archive_previous_attempt`` archives the
    record's worker entry, not the directory -- so its absence is positive
    evidence that no process was ever spawned for this run, rather than an
    absence of evidence.  Verified by grep across ``Pipeline/`` on 2026-09-22:
    the only ``rmtree`` in AssistantControl is candidate recovery cleanup, which
    is bounded to its own candidate root.
2.  **The Job Object.**  ``assistant-job-<sha256(run_root)>``, probed whether or
    not the directory exists, because the name is a hash of a path string and
    not of the directory's contents.  This is the probe that answers "is
    anything alive right now", and it does not rest on (1) being true.
3.  **The recorded process identities**, when a run root exists: the launcher's
    and the child's, compared against the live process table by
    ``process_identity.matches``, which checks creation ticks and image and so
    cannot be fooled by pid reuse.
4.  **Docker containers** for the run's compose project, derived from the run id
    the same way ``worker_settlement`` derives it.

If the record *does* name this run in its active worker or launch entry and that
entry is not finished, this command refuses and points at ``settle-worker``.
That path is supported, it proves more than this one does, and a second way to
do the same thing is how a guard gets bypassed rather than fixed.

WHY THE CHECKOUT LOCK IS HELD ACROSS THE PROOF AND THE RELEASE

``launch_worker`` verifies its reservation and creates the run root inside one
hold of ``checkouts.lock``.  A probe that reads the run root outside that lock
can be overtaken between the read and the release, and would then drop a
reservation for a run that had just started.  So the proof and the release
happen under a single hold, via ``admission.release_under_checkouts_lock``.
Without that, this module would be one more guard that reads as protective and
cannot fire.

Dry run by default.  ``--apply`` is required to write.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl import admission, worker_state
from Pipeline.AssistantControl.admission import (
    _read_registry, _source_registry_paths)
from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.process_identity import matches
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


class AdmissionReconciliationError(ValueError):
    """The reservation could not be proven abandoned, so nothing was released."""


def run_root_for(records: Path, task_id: str, run_id: str) -> Path:
    """Mirror ``worker_launcher._run_root``.

    Deliberately duplicated rather than imported: importing the launcher to
    reconcile a launch that never happened pulls in the spawn machinery, and
    this module must stay usable when that machinery is what failed. The
    duplication is pinned by a test that asserts the two agree.
    """
    return (records / "worker-runs" / task_id /
            hashlib.sha256(run_id.encode("utf-8")).hexdigest())


def job_name_for(run_root: Path) -> str:
    """Mirror the launcher's Job Object name, which hashes the path string."""
    return "assistant-job-" + hashlib.sha256(str(run_root).encode()).hexdigest()


def compose_project_for(run_id: str) -> str:
    """Mirror ``worker_settlement``'s Compose project for a run."""
    return "assistant-crew-" + hashlib.sha256(run_id.encode()).hexdigest()[:20]


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AdmissionReconciliationError(
            f"{path.name} is unreadable, so the run cannot be proven ended") from exc
    return value if isinstance(value, dict) else None


def _job_active(run_root: Path) -> int | None:
    """Active processes in the run's Job Object, or None when unknowable."""
    from Pipeline.AssistantControl import windows_job
    try:
        return int(windows_job.active_count(job_name_for(run_root)))
    except (windows_job.WindowsJobError, NotImplementedError, OSError,
            ValueError):
        return None


def _containers_running(checkout: Path, run_id: str) -> bool | None:
    """True/False, or None when Docker cannot answer."""
    from Pipeline.AssistantControl.docker_workers import inventory
    worker = {"run_id": run_id, "compose_project": compose_project_for(run_id)}
    try:
        return any(item["running"] for item in inventory(checkout, worker))
    except RuntimeError:
        return None
    except (ValueError, OSError):
        return None


def _live_identities(run_root: Path) -> list[dict[str, Any]]:
    """Every recorded identity for the run that is still a live process."""
    live: list[dict[str, Any]] = []
    for name in ("launcher.identity.json", "child.identity.json",
                 "job.opened.json"):
        body = _read_json(run_root / name)
        if not body:
            continue
        for key in ("process_identity", "child_identity"):
            identity = body.get(key)
            if not isinstance(identity, Mapping):
                continue
            try:
                alive = matches(dict(identity))
            except (ValueError, OSError, NotImplementedError):
                # An identity we cannot evaluate is not an identity we may
                # assume dead.
                live.append({"source": name, "field": key,
                             "pid": identity.get("pid"), "alive": "unknown"})
                continue
            if alive:
                live.append({"source": name, "field": key,
                             "pid": identity.get("pid"), "alive": True})
    return live


def _controller_running(checkouts: Checkouts) -> bool:
    body = _read_json(checkouts.records / "graph-controller.json")
    return bool(body) and body.get("status") == "running"


def _record(checkouts: Checkouts, task_id: str) -> dict[str, Any] | None:
    return _read_json(checkouts.records / f"{task_id}.json")


def _select(reservations: list[dict[str, Any]], task_id: str,
            run_id: str | None, lease_id: str | None,
            checkout_root: str) -> dict[str, Any]:
    owned = [item for item in reservations if item.get("task_id") == task_id
             and item.get("checkout_root") == checkout_root]
    if not owned:
        raise AdmissionReconciliationError(
            f"{task_id} holds no admission reservation in this checkout root; "
            f"there is nothing to reconcile")
    if run_id is None and lease_id is None:
        if len(owned) != 1:
            raise AdmissionReconciliationError(
                f"{task_id} holds {len(owned)} reservations; name the exact "
                f"--run-id and --lease-id to reconcile one of them")
        return owned[0]
    exact = [item for item in owned if item.get("run_id") == run_id
             and item.get("lease_id") == lease_id]
    if len(exact) != 1:
        raise AdmissionReconciliationError(
            f"no reservation for {task_id} matches run {run_id!r} and lease "
            f"{lease_id!r}; reconciliation releases an exact identity only")
    return exact[0]


def _refuse_when_the_record_owns_this_run(record: Mapping[str, Any] | None,
                                          task_id: str, run_id: str) -> str:
    """Refuse if `settle-worker` could act on this run; else say why it cannot.

    This is the boundary between the two commands. `settle_completed` proves a
    worker's own terminal state and cleans up after it; this command only
    exists for a reservation that no record can reach. If a record does reach
    it, using this command instead would skip the crew-artifact and container
    checks `settle_completed` performs.
    """
    if not record:
        return "no owned task record exists for this task at all"
    for field in ("worker", "launch"):
        entry = record.get(field)
        if not isinstance(entry, Mapping) or entry.get("run_id") != run_id:
            continue
        finished = (worker_state.is_finished_worker(entry) if field == "worker"
                    else worker_state.is_finished_launch(record, entry))
        if not finished:
            raise AdmissionReconciliationError(
                f"the owned record's {field} entry names run {run_id} and is "
                f"not finished (status {entry.get('status')!r}); "
                f"`settle-worker` is the supported command for that, and it "
                f"proves more than this one does")
        return (f"the record's {field} entry names this run and is already "
                f"finished, so no settlement remains to be done")
    named = sorted({str(entry.get("run_id"))
                    for field in ("worker", "launch")
                    for entry in [record.get(field)]
                    if isinstance(entry, Mapping) and entry.get("run_id")})
    return (f"no active record entry names run {run_id}"
            + (f"; the record names {', '.join(named)} instead" if named else ""))


def reconcile_admission(checkouts: Checkouts, task_id: str, *,
                        run_id: str | None = None,
                        lease_id: str | None = None,
                        apply: bool = False) -> dict[str, Any]:
    """Prove an admission reservation abandoned, then optionally release it."""
    task_id = validate_task_id(task_id)
    _, registry_path = _source_registry_paths(checkouts.source)

    with _exclusive_file_lock(checkouts.records / "checkouts.lock",
                              timeout_seconds=10):
        registry = _read_registry(registry_path, checkouts.source)
        reservation = _select(registry.get("reservations", []), task_id,
                              run_id, lease_id, str(checkouts.root))
        run_id = reservation["run_id"]
        lease_id = reservation["lease_id"]

        if _controller_running(checkouts):
            raise AdmissionReconciliationError(
                "a graph controller is running against this checkout root; it "
                "may be mid-launch for this very lease, so stop it first")

        record = _record(checkouts, task_id)
        record_finding = _refuse_when_the_record_owns_this_run(
            record, task_id, run_id)

        run_root = run_root_for(checkouts.records, task_id, run_id)
        launched = run_root.is_dir()
        job_active = _job_active(run_root)
        containers = _containers_running(
            Path(reservation.get("checkout", checkouts.root / task_id)), run_id)
        live = _live_identities(run_root) if launched else []

        proofs = {
            "run_root": str(run_root),
            "run_root_exists": launched,
            "job_name": job_name_for(run_root),
            "job_active_processes": job_active,
            "compose_project": compose_project_for(run_id),
            "containers_running": containers,
            "live_identities": live,
            "record_finding": record_finding,
            "finished_run_ids": sorted(worker_state.finished_run_ids(record))
                                if record else [],
        }

        refusals: list[str] = []
        if job_active is None:
            refusals.append(
                f"the Job Object {proofs['job_name']} could not be queried, so "
                f"a live process tree cannot be ruled out")
        elif job_active > 0:
            refusals.append(
                f"{job_active} process(es) are alive in this run's Job Object")
        if live:
            refusals.append(
                f"the run directory records identities that are still live or "
                f"unverifiable: {live}")
        if containers is True:
            refusals.append("containers for this run's Compose project are running")
        if containers is None and launched:
            # For a run that never launched, no process existed to create a
            # container, so Docker being unavailable costs nothing. For a run
            # that did launch, it is the difference between proven and assumed.
            refusals.append(
                "Docker could not be queried and this run did launch, so its "
                "containers cannot be proven exited")
        if refusals:
            raise AdmissionReconciliationError(
                "the reservation was NOT released; " + "; ".join(refusals))

        basis = ("never launched: the launcher creates the run directory before "
                 "it spawns anything, and this run has none"
                 if not launched else
                 "launched and ended: every recorded identity is dead, the Job "
                 "Object is empty and no container is running")

        result = {
            "task_id": task_id, "run_id": run_id, "lease_id": lease_id,
            "resources": reservation.get("resources", []),
            "basis": basis, "proofs": proofs,
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "applied": False, "released": False,
        }
        if not apply:
            result["would_release"] = True
            return result

        released = admission.release_under_checkouts_lock(
            checkouts, task_id, run_id, lease_id)
        result["applied"] = True
        result["released"] = bool(released.get("released"))
        return result
