"""Selectively revert one integrated task's own commits for a fresh replay.

This is a from-scratch, AssistantControl-native adapter. It reuses the
*operator meaning* of the existing GitHub-rehearsal reset
(``Pipeline/TaskReviewAgent/reset_rehearsal_task.py``) -- dry-run by
default, read exact identity from an authenticated record rather than a
guessed base, and the additive-revert-not-hard-reset mechanism that module
uses for a single merge commit -- generalized here to an arbitrary commit
range, since none of that module's GitHub repository/pull-request/Issue
machinery applies to a disposable local ``gauntlet-replay/*`` branch with
no Git remote.

Earlier revision history: a first version of this module did
``git reset --hard`` to the selected task's pre-task commit and archived
the whole checkout root. That is only correct when the selected task is
the *only* thing integrated on the branch; if another task was integrated
afterwards, a hard reset silently erases that unrelated task's commits and
state. This revision instead reverts only the selected task's own commit
range (``git revert --no-commit <pre_task_commit>..<candidate_commit>``),
refuses when later work touches the same paths (an auto-revert could then
silently misapply against the overlap) or when a later-integrated task
declares a dependency on the selected one, and archives only that task's
own records/checkout/evidence rather than the whole checkout root.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl import worker_control
from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.review import _changed_paths
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
GAUNTLET_REPLAY_PREFIX = "gauntlet-replay/"
RESET_TASK_TRAILER = "Assistant-Reset-Task"
RESET_BASE_TRAILER = "Assistant-Reset-Base"


class ResetTaskError(ValueError):
    """The selected task could not be safely reverted for a fresh replay."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_path(checkouts: Checkouts, task_id: str) -> Path:
    return checkouts.records / f"{task_id}.json"


def _read_record(checkouts: Checkouts, task_id: str) -> dict[str, Any] | None:
    path = _record_path(checkouts, task_id)
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResetTaskError(f"{task_id} owned record is unreadable") from exc
    if not isinstance(record, dict):
        raise ResetTaskError(f"{task_id} owned record must be an object")
    return record


def _all_task_records(checkouts: Checkouts) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not checkouts.records.is_dir():
        return records
    for path in checkouts.records.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and record.get("task_id") == path.stem:
            records[path.stem] = record
    return records


def _require_no_live_worker(checkouts: Checkouts, task_id: str, record: Mapping[str, Any]) -> None:
    if not isinstance(record.get("worker"), Mapping) and not isinstance(record.get("launch"), Mapping):
        return
    observation = worker_control.status(checkouts, task_id)
    if observation.get("host_identity_alive") is True:
        raise ResetTaskError(f"{task_id} has a live worker; stop and settle it before reset")
    worker = observation.get("worker") or {}
    if worker.get("capacity_released") is False:
        raise ResetTaskError(f"{task_id} worker capacity is not settled; settle it before reset")


def _require_no_active_reservation(checkouts: Checkouts, task_id: str) -> None:
    _, registry_path = _source_registry_paths(checkouts.source)
    registry = _read_registry(registry_path, checkouts.source)
    if any(item.get("task_id") == task_id for item in registry.get("reservations", [])):
        raise ResetTaskError(f"{task_id} has an active reservation; release it before reset")


def _require_controller_not_running(checkouts: Checkouts) -> None:
    path = checkouts.records / "graph-controller.json"
    if not path.is_file():
        return
    try:
        controller = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResetTaskError("graph controller record is unreadable") from exc
    if isinstance(controller, dict) and controller.get("status") == "running":
        raise ResetTaskError(
            "graph controller is still running against this checkout root; stop it before reset"
        )


def _integration_identity(record: Mapping[str, Any], task_id: str) -> tuple[str, str, str]:
    """Return (pre_task_commit, candidate_commit, branch), or refuse."""
    if record.get("status") != "integrated":
        raise ResetTaskError(
            f"{task_id} status is {record.get('status')!r}, not the required 'integrated'"
        )
    integration = record.get("integration")
    if not isinstance(integration, Mapping):
        raise ResetTaskError(f"{task_id} has no recorded integration; nothing to reset")
    candidate_commit = integration.get("candidate")
    branch = integration.get("branch")
    pre_task_commit = record.get("source_commit")
    if not isinstance(candidate_commit, str) or not _SHA40.fullmatch(candidate_commit):
        raise ResetTaskError(f"{task_id} integration record has no exact candidate commit")
    if not isinstance(pre_task_commit, str) or not _SHA40.fullmatch(pre_task_commit):
        raise ResetTaskError(f"{task_id} has no exact recorded pre-task source commit")
    if not isinstance(branch, str) or not branch.startswith(GAUNTLET_REPLAY_PREFIX):
        raise ResetTaskError(
            f"reset-task only operates on a local {GAUNTLET_REPLAY_PREFIX}* branch with no "
            f"remote; {task_id} is recorded on {branch!r}"
        )
    return pre_task_commit, candidate_commit, branch


def _archive_root(checkout_root: Path) -> Path:
    return checkout_root / ".assistant-control-reset-archive"


def _task_archive_destination(checkout_root: Path, task_id: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())
    root = _archive_root(checkout_root)
    candidate = root / f"{task_id}-{stamp}"
    suffix = 2
    while candidate.exists():
        candidate = root / f"{task_id}-{stamp}-{suffix}"
        suffix += 1
    return candidate


def _journal_path(checkout_root: Path, task_id: str) -> Path:
    return _archive_root(checkout_root) / f"{task_id}.reset-journal.json"


def _lock_path(checkout_root: Path, task_id: str) -> Path:
    return _archive_root(checkout_root) / f"{task_id}.reset.lock"


def plan_reset(checkouts: Checkouts, task_id: str) -> dict[str, Any]:
    """Validate every precondition and return the exact plan; mutate nothing."""
    task_id = validate_task_id(task_id)
    record = _read_record(checkouts, task_id)
    if record is None:
        raise ResetTaskError(f"{task_id} has no owned checkout record")
    if record.get("source") != str(checkouts.source):
        raise ResetTaskError(f"{task_id} record does not belong to this source")
    pre_task_commit, candidate_commit, branch = _integration_identity(record, task_id)

    remotes = git(checkouts.source, "remote").decode().split()
    if remotes:
        raise ResetTaskError(f"reset-task refuses a source with a Git remote: {remotes}")
    current_branch = git(checkouts.source, "branch", "--show-current").decode().strip()
    if current_branch != branch:
        raise ResetTaskError(f"source is on branch {current_branch!r}, expected the recorded {branch!r}")
    status_text = git(
        checkouts.source, "status", "--porcelain=v1", "--untracked-files=all",
    ).decode()
    if status_text:
        raise ResetTaskError("source working tree is not clean")
    head = git(checkouts.source, "rev-parse", "HEAD").decode().strip()
    try:
        git(checkouts.source, "merge-base", "--is-ancestor", candidate_commit, head)
    except RuntimeError as exc:
        raise ResetTaskError(
            f"{task_id}'s integrated commit is not an ancestor of the current source HEAD"
        ) from exc

    _require_controller_not_running(checkouts)
    _require_no_live_worker(checkouts, task_id, record)
    _require_no_active_reservation(checkouts, task_id)

    task_changed_paths = sorted(
        _changed_paths(checkouts.source, pre_task_commit, candidate_commit), key=str.casefold,
    )
    if not task_changed_paths:
        raise ResetTaskError(f"{task_id}'s integration recorded no changed paths; refusing to guess a revert")

    later_commits: list[str] = []
    if candidate_commit != head:
        later_commits = [
            line for line in git(
                checkouts.source, "rev-list", "--reverse", f"{candidate_commit}..{head}",
            ).decode().splitlines() if line
        ]
    if later_commits:
        later_paths = _changed_paths(checkouts.source, candidate_commit, head)
        task_paths_casefold = {path.casefold() for path in task_changed_paths}
        overlap = sorted(
            {path for path in later_paths if path.casefold() in task_paths_casefold},
            key=str.casefold,
        )
        if overlap:
            raise ResetTaskError(
                f"later integrated work touches the same paths as {task_id}'s own integration; "
                f"refusing an ambiguous revert instead of guessing: {overlap}"
            )
        later_integrated_ids = {
            other_id for other_id, other_record in _all_task_records(checkouts).items()
            if other_id != task_id
            and other_record.get("status") == "integrated"
            and (other_record.get("integration") or {}).get("candidate") in later_commits
        }
        try:
            task_contract = load_committed_task(checkouts.source, task_id, commit=head)
        except Exception as exc:
            raise ResetTaskError(
                f"{task_id}'s committed contract could not be read at current HEAD"
            ) from exc
        decomposition_children = set(task_contract.get("decomposition_children") or [])
        dependents = []
        for other_id in sorted(later_integrated_ids):
            if other_id in decomposition_children:
                dependents.append(other_id)
                continue
            try:
                other_contract = load_committed_task(checkouts.source, other_id, commit=head)
            except Exception:
                continue
            if task_id in (other_contract.get("depends_on") or []):
                dependents.append(other_id)
        if dependents:
            raise ResetTaskError(
                f"{sorted(set(dependents))} depend on (or were decomposed from) {task_id} and "
                "were integrated after it; refusing to revert a task that later integrated "
                "work depends on"
            )

    return {
        "schema_version": "assistant-reset-task/v2",
        "task_id": task_id,
        "source": str(checkouts.source),
        "checkout_root": str(checkouts.root),
        "branch": branch,
        "pre_task_commit": pre_task_commit,
        "task_candidate_commit": candidate_commit,
        "current_head": head,
        "task_changed_paths": task_changed_paths,
        "task_archive_destination": str(_task_archive_destination(checkouts.root, task_id)),
    }


def reset_task(checkouts: Checkouts, task_id: str, *, apply: bool = False) -> dict[str, Any]:
    """Dry-run by default; ``apply=True`` performs the revert idempotently.

    A dry run never touches the filesystem or Git beyond read-only
    inspection. An interrupted apply resumes from its retained per-task
    journal on the next call rather than reverting or archiving twice;
    a retained journal for a *different* task is refused rather than
    silently reinterpreted.
    """
    task_id = validate_task_id(task_id)
    if not apply:
        return {**plan_reset(checkouts, task_id), "apply": False}

    checkout_root = checkouts.root
    _archive_root(checkout_root).mkdir(parents=True, exist_ok=True)
    lock = _lock_path(checkout_root, task_id)
    with _exclusive_file_lock(lock, timeout_seconds=10):
        journal_path = _journal_path(checkout_root, task_id)
        journal: dict[str, Any] | None = None
        if journal_path.is_file():
            try:
                journal = json.loads(journal_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ResetTaskError(f"retained reset journal is unreadable: {journal_path}") from exc
            if journal.get("task_id") != task_id:
                raise ResetTaskError(
                    f"an unfinished reset for a different task is retained at {journal_path}; "
                    "resolve it before starting a different reset"
                )
            if journal.get("phase") == "done":
                return {**journal, "apply": True}

        if journal is None:
            plan = plan_reset(checkouts, task_id)
            journal = {
                "schema_version": "assistant-reset-task/v2", "phase": "starting",
                "task_id": task_id, "plan": plan, "started_at": _now(),
            }
            write_record(journal_path, journal)

        plan = journal["plan"]
        source = Path(plan["source"])
        pre_task_commit = str(plan["pre_task_commit"])
        candidate_commit = str(plan["task_candidate_commit"])
        task_changed_paths = list(plan["task_changed_paths"])

        if journal["phase"] == "starting":
            # Re-verify nothing changed since planning; a resumed later
            # phase reads only the retained plan, never re-derives it,
            # because this task's own record may already be archived by
            # then.
            reverified = plan_reset(checkouts, task_id)
            if reverified["current_head"] != plan["current_head"]:
                raise ResetTaskError(
                    "source state changed since the retained plan; re-run reset-task to replan"
                )
            git(source, "revert", "--no-commit", f"{pre_task_commit}..{candidate_commit}")
            staged = sorted(
                (line for line in git(
                    source, "diff", "--cached", "--name-only", "--no-renames",
                ).decode().splitlines() if line),
                key=str.casefold,
            )
            unstaged = git(source, "diff", "--name-only").decode()
            untracked = git(source, "ls-files", "--others", "--exclude-standard").decode()
            if staged != sorted(task_changed_paths, key=str.casefold) or unstaged or untracked:
                raise ResetTaskError(
                    "revert staged unexpected paths or left the tree dirty; the revert was "
                    "not committed and the source retains its pre-revert state for inspection"
                )
            name, email = validated_agent_git_identity()
            git(
                source, "-c", f"user.name={name}", "-c", f"user.email={email}", "commit",
                "-m", f"Revert {plan['task_id']} for a fresh local replay",
                "-m", (
                    "Preserve every other integrated task's commits and state; only this "
                    "task's own changes are undone."
                ),
                "-m", f"{RESET_TASK_TRAILER}: {plan['task_id']}\n{RESET_BASE_TRAILER}: {pre_task_commit}",
            )
            revert_commit = git(source, "rev-parse", "HEAD").decode().strip()
            journal.update(phase="reverted", revert_commit=revert_commit, reverted_at=_now())
            write_record(journal_path, journal)

        if journal["phase"] == "reverted":
            task_checkout = checkout_root / plan["task_id"]
            destination = Path(plan["task_archive_destination"])
            if task_checkout.exists() or _record_path(checkouts, plan["task_id"]).is_file():
                destination.mkdir(parents=True, exist_ok=True)
                if task_checkout.exists():
                    shutil.move(str(task_checkout), str(destination / "checkout"))
                owned_records = list(checkouts.records.glob(f"{plan['task_id']}.*")) + [
                    _record_path(checkouts, plan["task_id"]),
                ]
                archived_records = destination / ".assistant-control"
                archived_records.mkdir(parents=True, exist_ok=True)
                for record_file in sorted(set(owned_records)):
                    if record_file.is_file():
                        shutil.move(str(record_file), str(archived_records / record_file.name))
            journal.update(phase="done", completed_at=_now(),
                            task_archive_destination=str(destination))
            write_record(journal_path, journal)

        return {**journal, "apply": True}


__all__ = ["GAUNTLET_REPLAY_PREFIX", "ResetTaskError", "plan_reset", "reset_task"]
