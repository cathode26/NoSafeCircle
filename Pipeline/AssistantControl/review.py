"""Human decisions and local integration for a validated candidate commit.

Only the candidate-commit adapter may register reviewed crew work. Human
approval is a separate explicit tool operation; no provider grants it.
"""
from __future__ import annotations

import json
import hashlib
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git, unresolvable_commit
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_integration_lock(source: Path):
    """Coordinate cooperating integrations for every checkout root of source."""
    common_dir = Path(git(source, "rev-parse", "--git-common-dir").decode().strip())
    if not common_dir.is_absolute():
        common_dir = source / common_dir
    return _exclusive_file_lock(common_dir.resolve() / "assistant-control-integration.lock",
                                timeout_seconds=10)


def _z_paths(raw: bytes) -> set[str]:
    return {item for item in raw.decode("utf-8", "surrogateescape").split("\0") if item}


def _worktree_snapshot(source: Path) -> dict:
    """Bind every visible local edit by status, index entry, kind and bytes."""
    status = git(source, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    paths = _z_paths(git(source, "diff", "--name-only", "--no-renames", "-z", "HEAD", "--"))
    paths.update(_z_paths(git(source, "ls-files", "--others", "--exclude-standard", "-z")))
    entries = []
    for relative in sorted(paths, key=str.casefold):
        path = source / Path(relative)
        index = git(source, "ls-files", "--stage", "-z", "--", relative)
        if path.is_symlink():
            kind = "symlink"
            payload = str(path.readlink()).encode("utf-8", "surrogateescape")
        elif path.is_file():
            kind = "file"
            payload = path.read_bytes()
        elif path.is_dir():
            kind = "directory"
            payload = b""
        else:
            kind = "absent"
            payload = b""
        entries.append({
            "path": relative,
            "kind": kind,
            "content_sha256": hashlib.sha256(payload).hexdigest(),
            "index_sha256": hashlib.sha256(index).hexdigest(),
        })
    return {
        "status_sha256": hashlib.sha256(status).hexdigest(),
        "paths": entries,
    }


def _changed_paths(checkout: Path, base: str, candidate: str) -> set[str]:
    # `integrate` passes CANONICAL's HEAD as `base` while running in the TASK
    # CHECKOUT, which `prepare` cut at an older commit and which no command
    # updates at that stage -- `refresh-prepared` accepts only `prepared`
    # records. Git then answers "fatal: bad object" naming a commit that IS in
    # canonical, which points nowhere near the cause. Measured on NSC-047.
    #
    # The check lives here rather than at the call site so every caller is
    # covered. `reset_task.py` passes `checkouts.source`, where both objects
    # exist by construction, so it cannot fire there.
    missing = unresolvable_commit(
        checkout, ("the integration base", base), ("the candidate", candidate),
    )
    if missing is not None:
        raise ValueError(
            f"{missing}, so the changed-path comparison could not run; fetch that "
            "commit into the task checkout before integrating"
        )
    return _z_paths(git(
        checkout, "diff", "--name-only", "--no-renames", "-z", base, candidate, "--",
    ))


class ReviewGate:
    def __init__(self, checkouts: Checkouts):
        self.checkouts = checkouts

    def _path(self, task_id: str) -> Path:
        return self.checkouts.records / f"{validate_task_id(task_id)}.json"

    def _read(self, task_id: str) -> dict:
        self.checkouts.observe(task_id)  # Establish owned checkout identity.
        return json.loads(self._path(task_id).read_text(encoding="utf-8"))

    def _require_candidate(
        self, record: dict, tested_commit: str, *,
        allow_failed_materialization: bool = False,
        allow_pending_materialization: bool = False,
        allow_stale_policy_failure: bool = False,
    ) -> None:
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", tested_commit):
            raise ValueError("Use the exact full tested commit")
        candidate = record.get("candidate") or {}
        if (record.get("status") in {"needs_materialization", "materialization_failed"}
                and not allow_pending_materialization):
            raise ValueError(
                "candidate has not completed required Unity materialization and cannot be reviewed"
            )
        if candidate.get("commit") != tested_commit:
            raise ValueError("Tested commit is not the registered reviewed candidate")
        checkout = Path(record["checkout"])
        if git(checkout, "rev-parse", "HEAD").decode().strip() != tested_commit:
            raise ValueError("Checkout changed after review; test the new candidate")
        if git(checkout, "branch", "--show-current").decode().strip() != record["branch"]:
            raise ValueError("Checkout branch changed after review")
        if git(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
            raise ValueError("Task project has uncommitted changes; preserve and review them first")
        if git(checkout, "rev-parse", "HEAD^{tree}").decode().strip() != candidate.get("tree"):
            raise ValueError("Candidate tree differs from the reviewed result")
        load_committed_task(checkout, record["task_id"], commit=tested_commit,
                            expected_sha256=record["task_contract_sha256"])
        if candidate.get("kind") == "unity_materialization_failed":
            if not allow_failed_materialization:
                raise ValueError(
                    "candidate failed authoritative Unity validation and cannot be approved"
                )
            failure = record.get("materialization_failure") or {}
            if (candidate.get("kind") != "unity_materialization_failed"
                    or failure.get("materialized_commit") != tested_commit
                    or failure.get("materialized_tree") != candidate.get("tree")
                    or failure.get("validation_error")
                    != (candidate.get("validation_failure") or {}).get("error")):
                raise ValueError("failed Unity candidate evidence differs")
        elif record.get("status") == "validation_failed":
            failure = record.get("candidate_validation_failure") or {}
            expected_error = (
                f"authoritative validation policy for {record.get('task_id')} is stale"
            )
            if (not allow_stale_policy_failure
                    or failure.get("candidate_commit") != tested_commit
                    or failure.get("validation_error") != expected_error
                    or record.get("approval") is not None
                    or record.get("human_review") is not None):
                raise ValueError(
                    "candidate failed authoritative Unity validation and cannot be approved"
                )
        if candidate.get("kind") == "source_synchronized":
            from Pipeline.AssistantControl.source_update import validate_synchronized_candidate
            validate_synchronized_candidate(self.checkouts, record, tested_commit)

    @contextmanager
    def human_approved_candidate(
        self, task_id: str, *, tested_commit: str,
    ) -> Iterator[dict]:
        """Hold the task-record lock while yielding one exact human approval.

        Publication is deliberately stricter than local Gauntlet integration:
        an automated approval populates ``approval`` too, but cannot cross this
        GitHub boundary.  Keeping the lock held lets a caller perform a bounded
        write-ahead remote operation without the reviewed record changing under
        it.
        """
        with _exclusive_file_lock(self.checkouts.records / "checkouts.lock",
                                  timeout_seconds=10):
            record = self._read(task_id)
            self._require_candidate(record, tested_commit)
            human = record.get("human_review")
            approval = record.get("approval")
            if (not isinstance(human, dict) or not isinstance(approval, dict)
                    or human != approval
                    or human.get("decision") != "approve"
                    or human.get("commit") != tested_commit
                    or record.get("status")
                    not in {"approved", "integrating", "integrated"}):
                raise ValueError(
                    "GitHub publication requires Vincent's exact human approval"
                )
            yield record

    def decide(self, task_id: str, *, tested_commit: str, decision: str, message: str) -> dict:
        if decision not in {"approve", "reject"} or not message.strip():
            raise ValueError("Record approve or reject with Vincent's actual feedback")
        with _exclusive_file_lock(self.checkouts.records / "checkouts.lock", timeout_seconds=10):
            record = self._read(task_id)
            if record["status"] in {"integrating", "integrated"}:
                raise ValueError("Integration has already started; inspect its result")
            self._require_candidate(record, tested_commit)
            review = {"commit": tested_commit, "decision": decision, "message": message}
            previous = record.get("human_review") or {}
            if all(previous.get(key) == value for key, value in review.items()):
                return record
            review["recorded_at"] = now()
            record.setdefault("review_history", []).append(review)
            record["human_review"] = review
            record["approval"] = review if decision == "approve" else None
            record["status"] = "approved" if decision == "approve" else "changes_requested"
            write_record(self._path(task_id), record)
            return record

    def approve_validated_gauntlet(
        self, task_id: str, *, tested_commit: str,
        message: str = "Automated Gauntlet approval after exact focused validation.",
    ) -> dict:
        """Approve only a synthetic Gauntlet candidate with authenticated tests.

        This is intentionally separate from :meth:`decide`: it never records a
        human decision and permanently excludes NSC-042.
        """
        from Pipeline.AssistantControl.automation_policy import (
            authenticate_passing_validations,
            is_synthetic_gauntlet,
        )
        if not message.strip():
            raise ValueError("Automated Gauntlet approval requires a message")
        with _exclusive_file_lock(self.checkouts.records / "checkouts.lock", timeout_seconds=10):
            record = self._read(task_id)
            if record["status"] in {"integrating", "integrated"}:
                raise ValueError("Integration has already started; inspect its result")
            self._require_candidate(record, tested_commit)
            if not is_synthetic_gauntlet(Path(record["checkout"]), task_id, tested_commit):
                raise ValueError("Automated approval is limited to synthetic Gauntlet tasks")
            facts = authenticate_passing_validations(
                self.checkouts.records, record, tested_commit,
            )
            approval = {
                "commit": tested_commit,
                "decision": "approve",
                "message": message.strip(),
                "authority": "assistant_gauntlet_automation",
                "validation_count": len(facts),
                "recorded_at": now(),
            }
            previous = record.get("automation_review") or {}
            if all(previous.get(key) == value for key, value in approval.items()
                   if key != "recorded_at"):
                return record
            record.setdefault("automation_review_history", []).append(approval)
            record["automation_review"] = approval
            record["human_review"] = None
            record["approval"] = approval
            record["status"] = "approved"
            write_record(self._path(task_id), record)
            return record

    def integrate(self, task_id: str, *, expected_source_commit: str, target_branch: str) -> dict:
        """Fast-forward only; never rewrite history, stash edits or push GitHub."""
        with _exclusive_file_lock(self.checkouts.records / "checkouts.lock", timeout_seconds=10):
            with _source_integration_lock(self.checkouts.source):
                record = self._read(task_id)
                approval = record.get("approval") or {}
                commit = approval.get("commit", "")
                if approval.get("decision") != "approve" or record["status"] not in {"approved", "integrating", "integrated"}:
                    raise ValueError("The exact reviewed candidate must be approved before integration")
                if (record.get("candidate") or {}).get("kind") == "source_synchronized":
                    self._require_candidate(record, commit)
                source = self.checkouts.source
                if not target_branch:
                    raise ValueError("Source is not on the selected integration branch")
                git(source, "check-ref-format", "--branch", target_branch)
                branch = git(source, "branch", "--show-current").decode().strip()
                head = git(source, "rev-parse", "HEAD").decode().strip()
                target_ref = git(source, "rev-parse", "--verify", f"refs/heads/{target_branch}").decode().strip()
                if branch != target_branch or target_ref != head:
                    raise ValueError("Source is not on the selected integration branch")
                worktree_before = _worktree_snapshot(source)
                pending = record.get("integration") or {}
                if record["status"] in {"integrating", "integrated"}:
                    if pending.get("candidate") != commit or pending.get("branch") != target_branch:
                        raise ValueError("Integration receipt differs from this request")
                    preserved = pending.get("preserved_worktree")
                    if isinstance(preserved, dict) and preserved != worktree_before:
                        raise ValueError(
                            "Source local edits differ from the retained integration receipt"
                        )
                    if head == commit:
                        record["status"] = "integrated"
                        record["integration"]["completed_at"] = pending.get("completed_at") or now()
                        write_record(self._path(task_id), record)
                        return record
                    if record["status"] == "integrated":
                        # An acknowledged integration can be observed after later
                        # approved work advances the same branch.
                        git(source, "merge-base", "--is-ancestor", commit, head)
                        return record
                    if pending.get("source_before") != head:
                        raise ValueError("Source moved during unfinished integration; inspect before retrying")
                if head != expected_source_commit:
                    raise ValueError("Source changed since inspection; no integration attempted")
                self._require_candidate(record, commit)
                checkout = Path(record["checkout"])
                candidate_paths = _changed_paths(checkout, head, commit)
                local_paths = {
                    item["path"].casefold(): item["path"] for item in worktree_before["paths"]
                }
                collisions = sorted(
                    {local_paths[path.casefold()] for path in candidate_paths
                     if path.casefold() in local_paths},
                    key=str.casefold,
                )
                if collisions:
                    raise ValueError(
                        "Source changes overlap candidate paths; they were preserved and "
                        "integration was not attempted: " + ", ".join(collisions)
                    )
                # Fetch objects only from the owned local project, never a remote.
                git(source, "fetch", "--no-tags", "--no-write-fetch-head", "--",
                    str(checkout), commit, timeout_seconds=180)
                # Fetch is a checkpoint: a cooperating actor must not switch the
                # branch, move HEAD or move its selected branch ref underneath us.
                if (git(source, "branch", "--show-current").decode().strip() != target_branch
                        or git(source, "rev-parse", "HEAD").decode().strip() != head
                        or git(source, "rev-parse", "--verify", f"refs/heads/{target_branch}").decode().strip() != target_ref
                        or _worktree_snapshot(source) != worktree_before):
                    raise ValueError("Source branch, HEAD, ref or edits changed during fetch; no merge attempted")
                try:
                    git(source, "merge-base", "--is-ancestor", head, commit)
                except RuntimeError as exc:
                    raise ValueError("Candidate needs synchronization with Source and another review; no merge attempted") from exc
                record["integration"] = {"source_before": head, "candidate": commit,
                                         "branch": target_branch, "started_at": now(),
                                         "preserved_worktree": worktree_before}
                record["status"] = "integrating"
                write_record(self._path(task_id), record)
                git(source, "-c", "core.hooksPath=/dev/null", "merge", "--ff-only", "--no-edit",
                    "--no-overwrite-ignore", commit, timeout_seconds=180)
                if (git(source, "branch", "--show-current").decode().strip() != target_branch
                        or git(source, "rev-parse", "HEAD").decode().strip() != commit
                        or git(source, "rev-parse", "--verify", f"refs/heads/{target_branch}").decode().strip() != commit
                        or _worktree_snapshot(source) != worktree_before):
                    raise ValueError(
                        "Source branch, commit, or preserved local edits changed during integration; "
                        "inspect the retained record"
                    )
                record["status"] = "integrated"
                record["integration"]["completed_at"] = now()
                write_record(self._path(task_id), record)
                return record
