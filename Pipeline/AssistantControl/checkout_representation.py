"""Repair a worktree file that does not match its FILTERED checkout representation.

`git status` compares the worktree against the blob AFTER Git's configured
filters, not against the raw blob. With `core.autocrlf=true` a file written
directly -- bytes copied rather than checked out -- is byte-identical to the raw
blob and still correctly reported ` M`, because checkout would have written the
CRLF form. `git update-index --refresh` cannot clear it: refresh updates stat
information, and this is a real content difference.

Measured on NSC-048, 2026-09-23:

    worktree    403 bytes  CR=0   LF=13     == raw blob      True
    filtered    416 bytes  CR=13  LF=13     == worktree      False
    core.autocrlf = true

Two agents called that a phantom-dirty pipeline defect before Astra pointed at
the filtered form. It is not a defect; `git status` is right. But it blocks
admission, materialization (`observe -> changes`) and validation independently,
so a frozen task cannot move until the checkout is repaired.

WHY THIS EXISTS RATHER THAN `git checkout -- <path>`. A bare restore is safe only
when someone has already established there is nothing to lose, and that proof is
exactly what a future operator should not have to reconstruct under time
pressure. This refuses unless it can prove the worktree holds no edit: the bytes
must equal the raw blob, the index must match HEAD, and there must be no
conflict. When it cannot prove that, it stops and says so rather than discarding
whatever is there.

`materialization_recovery`'s existing helper ends at an index refresh and
explicitly refuses if status stays dirty, so it cannot repair this variant.
Design reviewed by Astra:
`C:/nscrev/codex-jobs/codex-advice-healthyrerun-20260923-0530.report.md`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock

SCHEMA_VERSION = "assistant-checkout-representation/v1"


class CheckoutRepresentationError(ValueError):
    """Cannot repair this path safely, with a reason an operator can act on."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repair_checkout_representation(
    checkouts: Checkouts,
    task_id: str,
    *,
    path: str,
    apply: bool = False,
) -> dict[str, Any]:
    """Plan, or perform, the restore of ONE path to its checkout representation.

    Read-only by default. It never decides what to discard: if the worktree
    holds anything other than the raw committed blob, it refuses.
    """
    task_id = validate_task_id(task_id)
    if type(path) is not str or not path.strip() or path.startswith("/") or ".." in path:
        raise CheckoutRepresentationError("path must be one relative path inside the checkout")
    path = path.replace("\\", "/").strip()

    record_path = checkouts.records / f"{task_id}.json"
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        if not record_path.is_file():
            raise CheckoutRepresentationError(f"no owned task record for {task_id}")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("task_id") != task_id or record.get("source") != str(checkouts.source):
            raise CheckoutRepresentationError("task record identity differs")
        checkout = Path(str(record.get("checkout", ""))).resolve()
        if not (checkout / ".git").exists():
            raise CheckoutRepresentationError("record does not name a task checkout")

        head = git(checkout, "rev-parse", "HEAD").decode().strip()
        tree = git(checkout, "rev-parse", "HEAD^{tree}").decode().strip()

        tracked = git(checkout, "ls-files", "--", path).decode().strip()
        if tracked != path:
            raise CheckoutRepresentationError(
                f"{path} is not a single tracked path in this checkout")
        if git(checkout, "ls-files", "-u", "--", path).strip():
            raise CheckoutRepresentationError(f"{path} has an unresolved merge conflict")
        # A staged change is a real edit somebody made; this repairs
        # representation, never content.
        if git(checkout, "diff", "--cached", "--name-only", "HEAD", "--", path).strip():
            raise CheckoutRepresentationError(
                f"{path} has staged changes against HEAD; this repairs representation, "
                "not content")

        target = checkout / path
        if not target.is_file() or target.is_symlink():
            raise CheckoutRepresentationError(f"{path} is not a regular file in the worktree")

        observed = target.read_bytes()
        raw = git(checkout, "cat-file", "blob", f"HEAD:{path}")
        filtered = git(checkout, "cat-file", "--filters", f"HEAD:{path}")

        if observed == filtered:
            return {
                "schema_version": SCHEMA_VERSION, "task_id": task_id, "path": path,
                "applied": False, "nothing_to_do": True,
                "reason": "the worktree already matches its checkout representation",
            }
        # THE SAFETY PROOF, and the whole reason this is not `git checkout --`:
        # the worktree must be exactly the committed bytes, merely unfiltered.
        # Anything else is an edit, and an edit is not ours to discard.
        if observed != raw:
            raise CheckoutRepresentationError(
                f"{path} differs from its committed blob, so it holds an edit; "
                "this repairs only an unfiltered copy of the committed bytes")

        plan = {
            "schema_version": SCHEMA_VERSION,
            "task_id": task_id,
            "path": path,
            "applied": False,
            "checkout": str(checkout),
            "head": head,
            "observed_sha256": _sha256(observed),
            "observed_bytes": len(observed),
            "expected_sha256": _sha256(filtered),
            "expected_bytes": len(filtered),
            "autocrlf": git(checkout, "config", "--get", "core.autocrlf").decode().strip() or None,
        }
        if not apply:
            return plan

        git(checkout, "checkout", "--", path)

        after = target.read_bytes()
        if after != filtered:
            raise CheckoutRepresentationError(
                f"{path} did not return to its checkout representation")
        if git(checkout, "rev-parse", "HEAD").decode().strip() != head:
            raise CheckoutRepresentationError("checkout HEAD moved during the repair")
        if git(checkout, "rev-parse", "HEAD^{tree}").decode().strip() != tree:
            raise CheckoutRepresentationError("checkout tree changed during the repair")
        if git(checkout, "status", "--porcelain=v1", "--", path).strip():
            raise CheckoutRepresentationError(
                f"{path} is still reported modified after the repair")
        plan["applied"] = True
        plan["repaired_at"] = _now()
        return plan


__all__ = [
    "CheckoutRepresentationError",
    "repair_checkout_representation",
    "SCHEMA_VERSION",
]
