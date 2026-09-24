"""Warn when revising a contract will close a live candidate's revise path.

THE LOSS IS SILENT AND AFTER THE FACT, which is why it needs saying at the
moment of the revision rather than being discoverable afterwards.

`revisions.py:134-140` loads the task contract at **Source HEAD** and requires
it to equal the control record's `task_contract_sha256`:

    contract_sha = record.get("task_contract_sha256")
    load_committed_task(source, task_id, commit=source_head,
                        expected_sha256=contract_sha)
    -> RevisionError("task contract changed at current source HEAD")

That check runs BEFORE either revise branch, so revising a contract while a
candidate is pinned to the old revision makes that candidate unrevisable by
EVERY route: the human `changes_requested` branch, the machine
`unity_materialization_failed` branch, and `prepared_refresh`, which refuses a
record holding a candidate anyway.

MEASURED 2026-09-24 by the Pipeline Runner across all 13 control records holding
a candidate: 7 pin mismatches, 4 of them genuinely stuck on the revise path
(NSC-007, NSC-009, NSC-046, NSC-097). NSC-047 mismatches but is INTEGRATED, a
useful negative control: the pin gates RECOVERY only, never merged work.

This WARNS rather than refuses, deliberately. The revision is often exactly what
is needed -- NSC-097's rev 6 was requested and correct. The cost should be
CHOSEN, not prevented, and not discovered a day later.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
from typing import Any

import main_write

RECORDS_DEFAULT = main_write.JOURNAL.parent


def _committed_contract_sha256(repo: pathlib.Path, task_id: str, commit: str = "HEAD") -> str | None:
    """sha256 of the contract's committed bytes, or None when it is absent.

    Hashes the BLOB as committed, which is what `load_committed_task`'s
    `expected_sha256` compares against -- not the working-tree file, whose line
    endings may differ.
    """
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:Tasks/{task_id}.yaml"],
                          capture_output=True)
    if proc.returncode != 0:
        return None
    return hashlib.sha256(proc.stdout).hexdigest()


def pinned_candidate(task_id: str, repo: pathlib.Path,
                     records: pathlib.Path | None = None) -> dict[str, Any] | None:
    """The live candidate a revision of `task_id` would strand, or None.

    Returns None when there is no record, no candidate, or the record is already
    pinned to something other than the current contract -- in that last case the
    recovery path is ALREADY closed and this revision is not what closed it.
    """
    root = records or RECORDS_DEFAULT
    path = root / f"{task_id}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or not record.get("candidate"):
        return None
    # INTEGRATED work is not at risk: the pin gates recovery, never merged work.
    if record.get("status") == "integrated":
        return None
    pin = record.get("task_contract_sha256")
    current = _committed_contract_sha256(repo, task_id)
    if not pin or not current or pin != current:
        return None
    return {
        "task_id": task_id,
        "status": record.get("status"),
        "candidate_commit": (record.get("candidate") or {}).get("commit"),
        "pinned_sha256": pin,
    }


def warn(task_id: str, repo: pathlib.Path, records: pathlib.Path | None = None) -> bool:
    """Print the warning if this revision would strand a candidate. True if warned."""
    at_risk = pinned_candidate(task_id, repo, records)
    if at_risk is None:
        return False
    print()
    print("  " + "!" * 72)
    print(f"  !! REVISING {task_id} CLOSES ITS CANDIDATE'S REVISE PATH, PERMANENTLY.")
    print("  !!")
    print(f"  !! status            {at_risk['status']}")
    print(f"  !! candidate         {at_risk['candidate_commit']}")
    print(f"  !! pinned contract   {str(at_risk['pinned_sha256'])[:16]}  == the CURRENT one")
    print("  !!")
    print("  !! revisions.py:134-140 loads the contract at SOURCE HEAD and requires it")
    print("  !! to equal the record's pin, BEFORE either revise branch. After this")
    print("  !! commit, revise refuses by every route and prepared_refresh refuses a")
    print("  !! record holding a candidate. The candidate can then only be SALVAGED")
    print("  !! by hand or re-dispatched cold.")
    print("  !!")
    print("  !! This is a WARNING, not a refusal -- the revision may be exactly right.")
    print("  !! Measured 2026-09-24: 4 of 13 candidate-holding records are already")
    print("  !! stuck this way, every one of them silently.")
    print("  " + "!" * 72)
    print()
    return True
