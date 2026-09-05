#!/usr/bin/env python3
"""Safely make one merged task fresh again in a disposable rehearsal repository.

This is deliberately not a Git-history eraser.  It creates and pushes a normal
revert commit, preserves the merged pull request and completed Issue, removes
only exact task-owned operational state, and proves the task is ``not_delivered``
again.  Production repositories and ambiguous partial state fail closed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.claim_policy import activated_claim_namespace  # noqa: E402
from Pipeline.TaskReviewAgent.claim_refs import (  # noqa: E402
    GitRefClaimClient,
    resource_claim_ref,
    task_claim_ref,
)
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import GIT_SHA_RE, validate_task_id  # noqa: E402
from Pipeline.TaskReviewAgent.git_identity_guard import (  # noqa: E402
    validated_agent_git_identity,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    ALL_STATE_LABELS,
    STATE_LABELS,
    WorkflowContractError,
    WorkflowState,
    parse_events,
    parse_state,
    validate_event_chain,
)
from Pipeline.TaskReviewAgent.real_checkout import branch_name  # noqa: E402


STATE_SUFFIXES = (
    ".json",
    ".scope.json",
    ".execution.json",
    ".integration.json",
    ".downstream.json",
)
RESET_TASK_TRAILER = "NSC-Rehearsal-Reset-Task"
RESET_MERGE_TRAILER = "NSC-Rehearsal-Reset-Merge"
GITHUB_REPOSITORY_RE = re.compile(
    r"^(?:https://github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?$",
    re.IGNORECASE,
)


class RehearsalResetError(RuntimeError):
    """Raised when a reset safety precondition cannot be proven."""


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    """Run exact argv commands with UTF-8 and separate stdout/stderr."""

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        check: bool = True,
        timeout: float = 600.0,
    ) -> CommandResult:
        if not args or any(type(item) is not str or not item for item in args):
            raise RehearsalResetError("commands require non-empty exact string arguments")
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            completed = subprocess.run(
                tuple(args),
                cwd=str(cwd),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
            raise RehearsalResetError(
                f"command could not be executed safely: {' '.join(args)}"
            ) from exc
        result = CommandResult(
            args=tuple(args),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if check and result.returncode != 0:
            detail = "\n".join(
                value.strip() for value in (result.stdout, result.stderr) if value.strip()
            )
            raise RehearsalResetError(
                f"command failed ({result.returncode}): {' '.join(args)}"
                + (f"\n{detail}" if detail else "")
            )
        return result


def _git(runner: CommandRunner, root: Path, *args: str, check: bool = True) -> CommandResult:
    return runner.run(("git", "-C", str(root), *args), cwd=root, check=check)


def _git_text(runner: CommandRunner, root: Path, *args: str, check: bool = True) -> str:
    return _git(runner, root, *args, check=check).stdout.strip()


def _json_command(runner: CommandRunner, args: Sequence[str], *, cwd: Path) -> Any:
    result = runner.run(args, cwd=cwd)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RehearsalResetError(
            f"command returned invalid JSON: {' '.join(args)}"
        ) from exc


def _repository_from_origin(origin: str) -> str:
    match = GITHUB_REPOSITORY_RE.fullmatch(origin.strip().replace("\\", "/"))
    if match is None:
        raise RehearsalResetError("origin must be one exact github.com HTTPS or SSH repository")
    repository = f"{match.group(1)}/{match.group(2)}"
    if repository.endswith(".git"):
        repository = repository[:-4]
    return repository


def _repo_metadata(runner: CommandRunner, root: Path, repository: str) -> dict[str, Any]:
    value = _json_command(
        runner,
        (
            "gh",
            "repo",
            "view",
            repository,
            "--json",
            "nameWithOwner,visibility,isArchived,url",
        ),
        cwd=root,
    )
    if not isinstance(value, dict):
        raise RehearsalResetError(f"GitHub repository lookup was invalid for {repository}")
    return value


def _require_private_rehearsal_repository(metadata: dict[str, Any], expected: str) -> None:
    actual = str(metadata.get("nameWithOwner") or "")
    if actual.casefold() != expected.casefold():
        raise RehearsalResetError(
            f"GitHub repository identity changed: expected {expected!r}, found {actual!r}"
        )
    if str(metadata.get("visibility") or "").upper() != "PRIVATE":
        raise RehearsalResetError("rehearsal reset requires a PRIVATE GitHub repository")
    if metadata.get("isArchived") is True:
        raise RehearsalResetError("rehearsal reset cannot mutate an archived repository")
    if "rehearsal" not in actual.casefold():
        raise RehearsalResetError(
            "repository name does not identify a rehearsal repository; production is refused"
        )


def _require_archive_repository(
    metadata: dict[str, Any], *, source_repository: str, archive_repository: str
) -> None:
    actual = str(metadata.get("nameWithOwner") or "")
    if actual.casefold() != archive_repository.casefold():
        raise RehearsalResetError("archive repository identity changed")
    if actual.casefold() == source_repository.casefold():
        raise RehearsalResetError("Issue archive must be a different repository")
    if actual.split("/", 1)[0].casefold() != source_repository.split("/", 1)[0].casefold():
        raise RehearsalResetError("Issue archive must have the same GitHub owner")
    if str(metadata.get("visibility") or "").upper() != "PRIVATE":
        raise RehearsalResetError("Issue archive repository must be PRIVATE")
    if metadata.get("isArchived") is True:
        raise RehearsalResetError("Issue archive repository is archived")


def _task_state(runner: CommandRunner, root: Path, task_id: str) -> dict[str, Any]:
    value = _json_command(
        runner,
        (
            sys.executable,
            str(root / "Pipeline" / "TaskGraph" / "taskcontrol.py"),
            "state",
            task_id,
            "--json",
        ),
        cwd=root,
    )
    if not isinstance(value, dict) or value.get("task_id") != task_id:
        raise RehearsalResetError("TaskGraph state result did not match the requested task")
    return value


def _validate_taskgraph(runner: CommandRunner, root: Path) -> None:
    result = runner.run(
        (
            sys.executable,
            str(root / "Pipeline" / "TaskGraph" / "taskcontrol.py"),
            "validate",
        ),
        cwd=root,
        timeout=300.0,
    )
    if "taskcontrol validate: PASS" not in result.stdout:
        raise RehearsalResetError("TaskGraph validation did not report PASS")


def _remote_ref_oid(
    runner: CommandRunner, root: Path, remote: str, ref: str
) -> str | None:
    output = _git_text(runner, root, "ls-remote", remote, ref)
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return None
    if len(lines) != 1:
        raise RehearsalResetError(f"remote lookup returned multiple entries for {ref}")
    parts = lines[0].split("\t")
    if len(parts) != 2 or parts[1] != ref or GIT_SHA_RE.fullmatch(parts[0]) is None:
        raise RehearsalResetError(f"remote lookup returned an invalid entry for {ref}")
    return parts[0]


def _commit_parents(runner: CommandRunner, root: Path, commit: str) -> tuple[str, ...]:
    fields = _git_text(runner, root, "rev-list", "--parents", "-n", "1", commit).split()
    if not fields or fields[0] != commit:
        raise RehearsalResetError(f"could not prove commit parents for {commit}")
    return tuple(fields[1:])


def _commit_tree(runner: CommandRunner, root: Path, commit: str) -> str:
    value = _git_text(runner, root, "rev-parse", f"{commit}^{{tree}}")
    if GIT_SHA_RE.fullmatch(value) is None:
        raise RehearsalResetError(f"commit tree identity was invalid for {commit}")
    return value


def _trailer(runner: CommandRunner, root: Path, commit: str, name: str) -> str | None:
    value = _git_text(
        runner,
        root,
        "show",
        "-s",
        f"--format=%(trailers:key={name},valueonly)",
        commit,
    )
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return None
    if len(lines) != 1:
        raise RehearsalResetError(f"reset commit has multiple {name} trailers")
    return lines[0]


def _resolve_main_state(
    runner: CommandRunner,
    root: Path,
    task_id: str,
    head: str,
    *,
    require_reset_marker: bool = False,
) -> tuple[str, bool]:
    parents = _commit_parents(runner, root, head)
    task_trailer = _trailer(runner, root, head, RESET_TASK_TRAILER)
    merge_trailer = _trailer(runner, root, head, RESET_MERGE_TRAILER)
    if task_trailer is None and merge_trailer is None:
        if len(parents) == 2 and not require_reset_marker:
            return head, False

        # A completed reset remains the recovery authority when later,
        # unrelated infrastructure commits have advanced main. Locate only the
        # newest matching marker on first-parent history, validate that marker
        # through this same exact-reset path, and then prove every later commit
        # left the reverted task surface untouched.
        first_parent_history = tuple(
            line
            for line in _git_text(
                runner, root, "rev-list", "--first-parent", head
            ).splitlines()
            if line
        )
        for candidate in first_parent_history[1:]:
            if _trailer(runner, root, candidate, RESET_TASK_TRAILER) != task_id:
                continue
            resolved_merge, already_reverted = _resolve_main_state(
                runner, root, task_id, candidate
            )
            merge_parents = _commit_parents(runner, root, resolved_merge)
            if len(merge_parents) != 2:
                raise RehearsalResetError(
                    "recorded task merge is not a two-parent merge commit"
                )
            changed_paths = _changed_paths(
                runner, root, merge_parents[0], resolved_merge
            )
            _require_task_paths_unchanged_since_merge(
                runner,
                root,
                merge_commit=candidate,
                current_main=head,
                paths=changed_paths,
            )
            return resolved_merge, already_reverted

        raise RehearsalResetError(
            "current main is not the task merge commit and is not a resumable reset commit"
        )
    if task_trailer != task_id or merge_trailer is None or GIT_SHA_RE.fullmatch(merge_trailer) is None:
        raise RehearsalResetError("current reset-commit trailers do not match this task")
    if len(parents) != 1:
        raise RehearsalResetError("reset commit must have exactly one parent")
    reset_parent = parents[0]
    if (
        _git(
            runner,
            root,
            "merge-base",
            "--is-ancestor",
            merge_trailer,
            reset_parent,
            check=False,
        ).returncode
        != 0
    ):
        raise RehearsalResetError(
            "recorded task merge is not an ancestor of the reset commit parent"
        )
    merge_parents = _commit_parents(runner, root, merge_trailer)
    if len(merge_parents) != 2:
        raise RehearsalResetError("recorded task merge is not a two-parent merge commit")
    changed_paths = _changed_paths(runner, root, merge_parents[0], merge_trailer)
    _require_task_paths_unchanged_since_merge(
        runner,
        root,
        merge_commit=merge_trailer,
        current_main=reset_parent,
        paths=changed_paths,
    )
    _validate_additive_revert_commit(
        runner,
        root,
        previous_main=reset_parent,
        revert_commit=head,
        merge_parent=merge_parents[0],
        expected_paths=changed_paths,
    )
    return merge_trailer, True


def _changed_paths(runner: CommandRunner, root: Path, old: str, new: str) -> tuple[str, ...]:
    value = _git_text(runner, root, "diff", "--name-only", "--no-renames", old, new)
    paths = tuple(line for line in value.splitlines() if line)
    if not paths:
        raise RehearsalResetError("task merge has no changed paths")
    return paths


def _tree_entry(
    runner: CommandRunner, root: Path, commit: str, path: str
) -> tuple[str, str, str] | None:
    value = _git_text(runner, root, "ls-tree", commit, "--", path)
    if not value:
        return None
    lines = value.splitlines()
    if len(lines) != 1:
        raise RehearsalResetError(f"tree lookup returned multiple entries for {path}")
    metadata, separator, returned_path = lines[0].partition("\t")
    fields = metadata.split()
    if not separator or returned_path != path or len(fields) != 3:
        raise RehearsalResetError(f"tree lookup returned an invalid entry for {path}")
    return fields[0], fields[1], fields[2]


def _require_task_paths_unchanged_since_merge(
    runner: CommandRunner,
    root: Path,
    *,
    merge_commit: str,
    current_main: str,
    paths: Sequence[str],
) -> None:
    protected = {str(path).casefold(): str(path) for path in paths}
    later_commits = tuple(
        line
        for line in _git_text(
            runner,
            root,
            "rev-list",
            "--ancestry-path",
            current_main,
            f"^{merge_commit}",
        ).splitlines()
        if line
    )
    touched: dict[str, list[str]] = {}
    for commit in later_commits:
        parents = _commit_parents(runner, root, commit)
        if not parents:
            raise RehearsalResetError(
                "later main history contains a parentless commit"
            )
        changed = {
            line.casefold()
            for line in _git_text(
                runner,
                root,
                "diff",
                "--name-only",
                "--no-renames",
                parents[0],
                commit,
            ).splitlines()
            if line
        }
        protected_hits = sorted(
            (original for folded, original in protected.items() if folded in changed),
            key=str.casefold,
        )
        if protected_hits:
            touched[commit] = protected_hits
    if touched:
        raise RehearsalResetError(
            "later commits changed task-owned paths; rehearsal reset is refused:\n"
            + json.dumps(touched, indent=2, sort_keys=True)
        )


def _validate_additive_revert_commit(
    runner: CommandRunner,
    root: Path,
    *,
    previous_main: str,
    revert_commit: str,
    merge_parent: str,
    expected_paths: Sequence[str],
) -> None:
    if _commit_parents(runner, root, revert_commit) != (previous_main,):
        raise RehearsalResetError(
            "rehearsal revert is not additive on the verified current main"
        )
    committed_paths = _changed_paths(runner, root, previous_main, revert_commit)
    if tuple(sorted(committed_paths)) != tuple(sorted(expected_paths)):
        raise RehearsalResetError("rehearsal revert commit changed an unexpected path")
    for path in expected_paths:
        if _tree_entry(runner, root, revert_commit, path) != _tree_entry(
            runner, root, merge_parent, path
        ):
            raise RehearsalResetError(
                f"rehearsal revert did not restore the pre-delivery tree entry: {path}"
            )


def _find_pull_request(
    runner: CommandRunner,
    root: Path,
    repository: str,
    branch: str,
    merge_commit: str,
) -> dict[str, Any]:
    listing = _json_command(
        runner,
        (
            "gh",
            "pr",
            "list",
            "--repo",
            repository,
            "--state",
            "merged",
            "--head",
            branch,
            "--limit",
            "100",
            "--json",
            "number,mergeCommit",
        ),
        cwd=root,
    )
    if not isinstance(listing, list):
        raise RehearsalResetError("GitHub pull-request listing was invalid")
    matches = [
        item
        for item in listing
        if isinstance(item, dict)
        and isinstance(item.get("mergeCommit"), dict)
        and item["mergeCommit"].get("oid") == merge_commit
    ]
    if len(matches) != 1 or type(matches[0].get("number")) is not int:
        raise RehearsalResetError(
            "exactly one merged pull request must own the current task merge commit"
        )
    value = _json_command(
        runner,
        (
            "gh",
            "pr",
            "view",
            str(matches[0]["number"]),
            "--repo",
            repository,
            "--json",
            "number,title,state,url,baseRefName,headRefName,headRefOid,mergeCommit,files",
        ),
        cwd=root,
    )
    if not isinstance(value, dict):
        raise RehearsalResetError("GitHub pull-request view was invalid")
    return value


def _validate_pull_request(
    runner: CommandRunner,
    root: Path,
    pull_request: dict[str, Any],
    *,
    branch: str,
    merge_commit: str,
) -> tuple[str, tuple[str, ...]]:
    merge_parents = _commit_parents(runner, root, merge_commit)
    if len(merge_parents) != 2:
        raise RehearsalResetError("task commit must be a two-parent pull-request merge")
    merge = pull_request.get("mergeCommit")
    files = pull_request.get("files")
    pr_paths = tuple(
        str(item.get("path"))
        for item in files or []
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    )
    local_paths = _changed_paths(runner, root, merge_parents[0], merge_commit)
    reasons: list[str] = []
    if pull_request.get("state") != "MERGED":
        reasons.append("pull request is not MERGED")
    if pull_request.get("baseRefName") != "main":
        reasons.append("pull request base is not main")
    if pull_request.get("headRefName") != branch:
        reasons.append("pull request head branch differs from the task branch")
    if not isinstance(merge, dict) or merge.get("oid") != merge_commit:
        reasons.append("pull request merge commit identity differs")
    if pull_request.get("headRefOid") != merge_parents[1]:
        reasons.append("pull request head OID differs from merge second parent")
    if tuple(sorted(pr_paths)) != tuple(sorted(local_paths)):
        reasons.append("pull request changed paths differ from the local merge")
    if reasons:
        raise RehearsalResetError("; ".join(reasons))
    return merge_parents[0], local_paths


def _issue_labels(issue: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for item in issue.get("labels") or []:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            values.add(item["name"])
        elif isinstance(item, str):
            values.add(item)
    return values


def _complete_issue_candidates(
    runner: CommandRunner,
    root: Path,
    repository: str,
    task_id: str,
    branch: str,
    head_commit: str,
) -> list[dict[str, Any]]:
    listing = _json_command(
        runner,
        (
            "gh",
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "all",
            "--search",
            f"{task_id} in:title",
            "--limit",
            "100",
            "--json",
            "number,title,state,url,body,labels",
        ),
        cwd=root,
    )
    if not isinstance(listing, list):
        raise RehearsalResetError("GitHub Issue listing was invalid")
    matches: list[dict[str, Any]] = []
    for issue in listing:
        if not isinstance(issue, dict) or not isinstance(issue.get("body"), str):
            continue
        try:
            state = parse_state(issue["body"])
        except ValueError:
            continue
        if (
            state is not None
            and state.task_id == task_id
            and state.state is WorkflowState.COMPLETE
            and state.branch == branch
            and state.head_commit == head_commit
        ):
            matches.append({**issue, "workflow_state": state})
    return matches


def _validate_complete_issue(
    runner: CommandRunner,
    root: Path,
    repository: str,
    issue: dict[str, Any],
    *,
    require_state_label: bool,
) -> dict[str, Any]:
    number = issue.get("number")
    listed_state = issue.get("workflow_state")
    if type(number) is not int or listed_state is None:
        raise RehearsalResetError("completed Issue identity is invalid")
    # `gh issue list` and `gh issue view` are separately cached GitHub queries.
    # The list result is discovery only: after a transfer it can expose a newer
    # dashboard body while the separately fetched comments are still one event
    # behind. Re-read body, labels, metadata, and comments together so the
    # hashed state is compared only with the event chain from one exact view.
    value = _json_command(
        runner,
        (
            "gh",
            "issue",
            "view",
            str(number),
            "--repo",
            repository,
            "--json",
            "number,title,state,url,body,labels,comments",
        ),
        cwd=root,
    )
    if not isinstance(value, dict) or value.get("number") != number:
        raise RehearsalResetError("exact completed Issue view has the wrong identity")
    if issue.get("url") != value.get("url"):
        raise RehearsalResetError("exact completed Issue URL differs from discovery")
    if value.get("state") != "CLOSED":
        raise RehearsalResetError("completed task Issue must be closed")
    body = value.get("body")
    comments = value.get("comments")
    if not isinstance(body, str) or not isinstance(comments, list):
        raise RehearsalResetError("completed Issue body or comments were not readable")
    try:
        state = parse_state(body)
    except WorkflowContractError as exc:
        raise RehearsalResetError(
            f"exact completed Issue state is invalid: {exc}"
        ) from exc
    if state is None:
        raise RehearsalResetError("exact completed Issue has no workflow state")
    stable_fields = (
        "task_id",
        "state",
        "phase",
        "current_actor",
        "task_contract_sha256",
        "worker_id",
        "lease_id",
        "branch",
        "head_commit",
        "checkout_path",
        "human_handoff_commit",
        "human_result",
    )
    if any(
        getattr(state, field) != getattr(listed_state, field)
        for field in stable_fields
    ):
        raise RehearsalResetError(
            "exact completed Issue workflow identity differs from discovery"
        )
    state_labels = _issue_labels(value) & ALL_STATE_LABELS
    if require_state_label and state_labels != {
        STATE_LABELS[WorkflowState.COMPLETE.value]
    }:
        raise RehearsalResetError(
            "source Issue must have exactly the complete workflow label"
        )
    try:
        events = parse_events(comments)
        validate_event_chain(state, events)
    except WorkflowContractError as exc:
        raise RehearsalResetError(
            f"exact completed Issue event chain is invalid: {exc}"
        ) from exc
    return {**value, "workflow_state": state}


def _find_complete_issue(
    runner: CommandRunner,
    root: Path,
    repository: str,
    task_id: str,
    branch: str,
    head_commit: str,
    *,
    require_state_label: bool,
) -> dict[str, Any] | None:
    matches = _complete_issue_candidates(
        runner, root, repository, task_id, branch, head_commit
    )
    if len(matches) > 1:
        raise RehearsalResetError(
            f"multiple completed Issues in {repository} match this exact task run"
        )
    if not matches:
        return None
    return _validate_complete_issue(
        runner,
        root,
        repository,
        matches[0],
        require_state_label=require_state_label,
    )


def _find_unique_source_complete_issue(
    runner: CommandRunner,
    root: Path,
    repository: str,
    task_id: str,
    branch: str,
) -> dict[str, Any]:
    listing = _json_command(
        runner,
        (
            "gh",
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "closed",
            "--search",
            f"{task_id} in:title",
            "--limit",
            "100",
            "--json",
            "number,title,state,url,body,labels",
        ),
        cwd=root,
    )
    if not isinstance(listing, list):
        raise RehearsalResetError("GitHub Issue listing was invalid")
    matches: list[dict[str, Any]] = []
    for issue in listing:
        if not isinstance(issue, dict) or not isinstance(issue.get("body"), str):
            continue
        try:
            state = parse_state(issue["body"])
        except ValueError:
            continue
        if (
            state is not None
            and state.task_id == task_id
            and state.state is WorkflowState.COMPLETE
            and state.branch == branch
            and state.head_commit is not None
        ):
            matches.append({**issue, "workflow_state": state})
    if len(matches) != 1:
        raise RehearsalResetError(
            "exactly one closed completed source Issue must identify the delivered run"
        )
    return _validate_complete_issue(
        runner,
        root,
        repository,
        matches[0],
        require_state_label=True,
    )


def _find_pull_request_for_task_head(
    runner: CommandRunner,
    root: Path,
    repository: str,
    branch: str,
    task_head: str,
) -> tuple[dict[str, Any], str]:
    listing = _json_command(
        runner,
        (
            "gh",
            "pr",
            "list",
            "--repo",
            repository,
            "--state",
            "merged",
            "--head",
            branch,
            "--limit",
            "100",
            "--json",
            "number,headRefOid,mergeCommit",
        ),
        cwd=root,
    )
    if not isinstance(listing, list):
        raise RehearsalResetError("GitHub pull-request listing was invalid")
    matches = [
        item
        for item in listing
        if isinstance(item, dict)
        and item.get("headRefOid") == task_head
        and isinstance(item.get("mergeCommit"), dict)
        and isinstance(item["mergeCommit"].get("oid"), str)
    ]
    if len(matches) != 1:
        raise RehearsalResetError(
            "exactly one merged pull request must match the completed Issue head"
        )
    merge_commit = str(matches[0]["mergeCommit"]["oid"])
    return (
        _find_pull_request(
            runner,
            root,
            repository,
            branch,
            merge_commit,
        ),
        merge_commit,
    )


def _relevant_claims(root: Path, task: dict[str, Any]) -> list[dict[str, Any]]:
    namespace = activated_claim_namespace()
    client = GitRefClaimClient(
        local_repository=root,
        remote="origin",
        namespace=namespace,
        worker_id="rehearsal-reset-inspector",
    )
    refs = {task_claim_ref(namespace, task["id"])}
    refs.update(resource_claim_ref(namespace, item) for item in task.get("exclusive_resources") or [])
    return [entry for entry in client.inspect_claims() if entry.get("ref") in refs]


def _state_paths(state_root: Path, task_id: str) -> tuple[Path, ...]:
    return tuple(state_root / f"{task_id}{suffix}" for suffix in STATE_SUFFIXES)


def _path_is_reparse_point(path: Path) -> bool:
    try:
        attributes = os.lstat(path).st_file_attributes
    except AttributeError:
        return path.is_symlink()
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _remove_tree_exact(path: Path) -> None:
    """Remove one prevalidated tree, retrying Windows read-only files exactly."""

    def handle_readonly(function: Any, value: str, exception: Any) -> None:
        _ = exception
        os.chmod(value, stat.S_IWRITE)
        function(value)

    shutil.rmtree(path, onerror=handle_readonly)


def _inspect_checkout(
    runner: CommandRunner,
    checkout: Path,
    *,
    expected_root: Path,
    expected_origin: str,
    expected_branch: str,
    expected_head: str,
    remote_branch_oid: str | None,
) -> dict[str, Any]:
    expected_literal = expected_root.resolve() / checkout.name
    if checkout.resolve() != expected_literal or checkout.parent.resolve() != expected_root.resolve():
        raise RehearsalResetError("checkout path escaped the exact configured checkout root")
    if _path_is_reparse_point(checkout):
        raise RehearsalResetError("checkout path is a symbolic link or reparse point")
    facts = {
        "path": str(checkout),
        "root": _git_text(runner, checkout, "rev-parse", "--show-toplevel"),
        "origin": _git_text(runner, checkout, "remote", "get-url", "origin"),
        "branch": _git_text(runner, checkout, "branch", "--show-current"),
        "head": _git_text(runner, checkout, "rev-parse", "HEAD"),
        "status": _git_text(
            runner, checkout, "status", "--porcelain=v1", "--untracked-files=all"
        ),
        "upstream": _git_text(runner, checkout, "rev-parse", "@{upstream}", check=False),
    }
    if Path(facts["root"]).resolve() != checkout.resolve():
        raise RehearsalResetError("task checkout is nested inside another Git repository")
    if _repository_from_origin(facts["origin"]).casefold() != _repository_from_origin(expected_origin).casefold():
        raise RehearsalResetError("task checkout origin differs from the controller origin")
    if facts["branch"] != expected_branch or facts["head"] != expected_head:
        raise RehearsalResetError("task checkout branch or HEAD differs from the completed run")
    if facts["status"]:
        raise RehearsalResetError("task checkout is dirty; it was not removed")
    if remote_branch_oid is not None and facts["upstream"] != expected_head:
        raise RehearsalResetError("task checkout upstream differs from its pushed HEAD")
    return facts


def _controller_task_worktrees(
    runner: CommandRunner, root: Path, task_id: str, branch: str
) -> list[dict[str, str]]:
    lines = _git_text(runner, root, "worktree", "list", "--porcelain").splitlines()
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in (*lines, ""):
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    wanted_ref = f"refs/heads/{branch}"
    return [
        item
        for item in records
        if item.get("branch") == wanted_ref
        or Path(item.get("worktree") or ".").name.casefold() == task_id.casefold()
    ]


def _processes_using_checkout(runner: CommandRunner, root: Path, checkout: Path) -> list[dict[str, Any]]:
    if os.name != "nt":
        raise RehearsalResetError("checkout process verification is implemented only on Windows")
    literal = str(checkout.resolve()).replace("'", "''")
    script = (
        f"$needle = '{literal}'; "
        "$items = @(Get-CimInstance Win32_Process | Where-Object { "
        "$_.ProcessId -ne $PID -and $_.CommandLine -and "
        "$_.CommandLine.IndexOf($needle, [StringComparison]::OrdinalIgnoreCase) -ge 0 "
        "} | Select-Object ProcessId,Name,CommandLine); "
        "$items | ConvertTo-Json -Compress"
    )
    result = runner.run(
        ("powershell.exe", "-NoProfile", "-Command", script),
        cwd=root,
        timeout=120.0,
    )
    text = result.stdout.strip()
    if not text:
        return []
    value = json.loads(text)
    return value if isinstance(value, list) else [value]


def _containers_using_checkout(runner: CommandRunner, root: Path, checkout: Path) -> list[str]:
    listing = runner.run(("docker", "ps", "-q"), cwd=root, timeout=120.0)
    identifiers = [line.strip() for line in listing.stdout.splitlines() if line.strip()]
    if not identifiers:
        return []
    inspections = _json_command(runner, ("docker", "inspect", *identifiers), cwd=root)
    if not isinstance(inspections, list):
        raise RehearsalResetError("Docker inspection result was invalid")
    target = os.path.normcase(str(checkout.resolve()))
    matches: list[str] = []
    for item in inspections:
        if not isinstance(item, dict):
            continue
        mounts = item.get("Mounts") or []
        if any(
            isinstance(mount, dict)
            and isinstance(mount.get("Source"), str)
            and (
                os.path.normcase(mount["Source"]) == target
                or os.path.normcase(mount["Source"]).startswith(target + os.sep)
            )
            for mount in mounts
        ):
            matches.append(str(item.get("Name") or item.get("Id") or "unknown-container"))
    return matches


def _archive_state_files(
    state_root: Path,
    task_id: str,
    *,
    timestamp: str,
) -> tuple[Path | None, tuple[str, ...]]:
    existing = tuple(path for path in _state_paths(state_root, task_id) if path.is_file())
    if not existing:
        return None, ()
    archive = state_root / "archive" / task_id / timestamp
    if archive.exists():
        raise RehearsalResetError(f"state archive already exists: {archive}")
    archive.mkdir(parents=True, exist_ok=False)
    moved: list[str] = []
    for source in existing:
        destination = archive / source.name
        if destination.exists():
            raise RehearsalResetError(f"state archive destination already exists: {destination}")
        source.replace(destination)
        moved.append(source.name)
    archived = tuple(sorted(path.name for path in archive.iterdir() if path.is_file()))
    if archived != tuple(sorted(moved)):
        raise RehearsalResetError("archived state filename verification failed")
    return archive, archived


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _create_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise RehearsalResetError(f"reset receipt already exists: {path}") from exc


class RehearsalTaskReset:
    def __init__(
        self,
        *,
        source: Path,
        checkout_root: Path,
        task_id: str,
        archive_repository: str,
        runner: CommandRunner | None = None,
    ) -> None:
        self.runner = runner or CommandRunner()
        self.source = source.resolve()
        self.checkout_root = checkout_root.resolve()
        self.task_id = validate_task_id(task_id)
        self.archive_repository = archive_repository
        self.state_root = self.checkout_root / ".task-review-agent"
        self.checkout = self.checkout_root / self.task_id
        self.task = load_committed_task(self.source, self.task_id)
        self.branch = branch_name(self.task_id, self.task.get("title"))
        self.origin = _git_text(self.runner, self.source, "remote", "get-url", "origin")
        self.repository = _repository_from_origin(self.origin)

    def preflight(self) -> dict[str, Any]:
        if not self.source.is_dir() or not self.checkout_root.is_dir():
            raise RehearsalResetError("source and checkout root must already exist")
        if Path(_git_text(self.runner, self.source, "rev-parse", "--show-toplevel")).resolve() != self.source:
            raise RehearsalResetError("source is not the exact Git repository root")
        if _git_text(self.runner, self.source, "branch", "--show-current") != "main":
            raise RehearsalResetError("controller must be on main")
        status = _git_text(
            self.runner,
            self.source,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        if status:
            raise RehearsalResetError("controller working tree is not completely clean")

        source_meta = _repo_metadata(self.runner, self.source, self.repository)
        _require_private_rehearsal_repository(source_meta, self.repository)
        archive_meta = _repo_metadata(
            self.runner, self.source, self.archive_repository
        )
        _require_archive_repository(
            archive_meta,
            source_repository=self.repository,
            archive_repository=self.archive_repository,
        )

        _git(self.runner, self.source, "fetch", "--prune", "origin", "main")
        head = _git_text(self.runner, self.source, "rev-parse", "HEAD")
        origin_main = _git_text(self.runner, self.source, "rev-parse", "origin/main")
        if head != origin_main:
            raise RehearsalResetError("controller HEAD must exactly equal fetched origin/main")
        task_state = _task_state(self.runner, self.source, self.task_id)
        source_issue = None
        try:
            merge_commit, already_reverted = _resolve_main_state(
                self.runner,
                self.source,
                self.task_id,
                head,
                require_reset_marker=task_state.get("state") == "not_delivered",
            )
            pull_request = _find_pull_request(
                self.runner,
                self.source,
                self.repository,
                self.branch,
                merge_commit,
            )
        except RehearsalResetError:
            if task_state.get("state") != "conformant":
                raise
            source_issue = _find_unique_source_complete_issue(
                self.runner,
                self.source,
                self.repository,
                self.task_id,
                self.branch,
            )
            task_head = str(source_issue["workflow_state"].head_commit)
            pull_request, merge_commit = _find_pull_request_for_task_head(
                self.runner,
                self.source,
                self.repository,
                self.branch,
                task_head,
            )
            if (
                _git(
                    self.runner,
                    self.source,
                    "merge-base",
                    "--is-ancestor",
                    merge_commit,
                    head,
                    check=False,
                ).returncode
                != 0
            ):
                raise RehearsalResetError(
                    "task merge commit is not an ancestor of current rehearsal main"
                )
            already_reverted = False
        merge_parent, changed_paths = _validate_pull_request(
            self.runner,
            self.source,
            pull_request,
            branch=self.branch,
            merge_commit=merge_commit,
        )
        task_head = str(pull_request["headRefOid"])
        if not already_reverted and head != merge_commit:
            _require_task_paths_unchanged_since_merge(
                self.runner,
                self.source,
                merge_commit=merge_commit,
                current_main=head,
                paths=changed_paths,
            )

        if source_issue is None:
            source_issue = _find_complete_issue(
                self.runner,
                self.source,
                self.repository,
                self.task_id,
                self.branch,
                task_head,
                require_state_label=True,
            )
        archived_issue = _find_complete_issue(
            self.runner,
            self.source,
            self.archive_repository,
            self.task_id,
            self.branch,
            task_head,
            require_state_label=False,
        )
        if source_issue is not None and archived_issue is not None:
            raise RehearsalResetError("the exact completed Issue exists in both source and archive")
        if not already_reverted and source_issue is None:
            raise RehearsalResetError("current task merge has no exact completed source Issue")
        if already_reverted and source_issue is None and archived_issue is None:
            raise RehearsalResetError("resumed reset cannot find the exact completed Issue")

        remote_ref = f"refs/heads/{self.branch}"
        remote_branch_oid = _remote_ref_oid(
            self.runner, self.source, "origin", remote_ref
        )
        if remote_branch_oid is not None and remote_branch_oid != task_head:
            raise RehearsalResetError("remote task branch moved after the completed pull request")

        claims = _relevant_claims(self.source, self.task)
        if claims:
            raise RehearsalResetError(
                "task/resource claim refs still exist; confirm the owning process is dead and "
                "repair them with GitRefClaimClient.repair_stale_claim using these exact facts:\n"
                + json.dumps(claims, indent=2, sort_keys=True)
            )

        worktrees = _controller_task_worktrees(
            self.runner, self.source, self.task_id, self.branch
        )
        unexpected_worktrees = [
            item
            for item in worktrees
            if Path(item.get("worktree") or ".").resolve() != self.source
        ]
        if unexpected_worktrees:
            raise RehearsalResetError(
                "task-specific linked worktrees require separate inspection; nothing was removed:\n"
                + json.dumps(unexpected_worktrees, indent=2, sort_keys=True)
            )

        checkout_facts = None
        if self.checkout.exists():
            if not self.checkout.is_dir():
                raise RehearsalResetError("canonical task checkout exists but is not a directory")
            checkout_facts = _inspect_checkout(
                self.runner,
                self.checkout,
                expected_root=self.checkout_root,
                expected_origin=self.origin,
                expected_branch=self.branch,
                expected_head=task_head,
                remote_branch_oid=remote_branch_oid,
            )
            processes = _processes_using_checkout(
                self.runner, self.source, self.checkout
            )
            containers = _containers_using_checkout(
                self.runner, self.source, self.checkout
            )
            if processes or containers:
                raise RehearsalResetError(
                    "task checkout is still in use; nothing was removed:\n"
                    + json.dumps(
                        {"processes": processes, "containers": containers},
                        indent=2,
                        sort_keys=True,
                    )
                )

        local_branch_oid = _git_text(
            self.runner,
            self.source,
            "rev-parse",
            "--verify",
            f"refs/heads/{self.branch}",
            check=False,
        ) or None
        if local_branch_oid is not None and local_branch_oid != task_head:
            raise RehearsalResetError("controller local task branch moved from the completed head")

        expected_state = "not_delivered" if already_reverted else "conformant"
        if task_state.get("state") != expected_state:
            raise RehearsalResetError(
                f"TaskGraph state must be {expected_state!r}, found {task_state.get('state')!r}"
            )
        _validate_taskgraph(self.runner, self.source)
        active_state_files = [
            str(path) for path in _state_paths(self.state_root, self.task_id) if path.is_file()
        ]
        return {
            "schema_version": "1.0",
            "operation": "repeat_merged_task_in_private_rehearsal",
            "task_id": self.task_id,
            "repository": self.repository,
            "archive_repository": self.archive_repository,
            "main_head": head,
            "already_reverted": already_reverted,
            "merge_commit": merge_commit,
            "merge_first_parent": merge_parent,
            "task_branch": self.branch,
            "task_head": task_head,
            "pull_request": {
                "number": pull_request["number"],
                "url": pull_request["url"],
            },
            "source_issue": (
                {"number": source_issue["number"], "url": source_issue["url"]}
                if source_issue
                else None
            ),
            "archived_issue": (
                {"number": archived_issue["number"], "url": archived_issue["url"]}
                if archived_issue
                else None
            ),
            "changed_paths": list(changed_paths),
            "remote_branch_oid": remote_branch_oid,
            "local_branch_oid": local_branch_oid,
            "checkout": checkout_facts,
            "active_state_files": active_state_files,
            "retained_outputs": str(self.state_root / "outputs" / self.task_id),
            "taskgraph_state": task_state["state"],
        }

    def _create_and_push_revert(self, plan: dict[str, Any]) -> str:
        previous_main = str(plan["main_head"])
        merge_commit = str(plan["merge_commit"])
        merge_parent = str(plan["merge_first_parent"])
        if (
            _remote_ref_oid(self.runner, self.source, "origin", "refs/heads/main")
            != previous_main
        ):
            raise RehearsalResetError("origin/main moved after preflight; no revert was created")
        _require_task_paths_unchanged_since_merge(
            self.runner,
            self.source,
            merge_commit=merge_commit,
            current_main=previous_main,
            paths=plan["changed_paths"],
        )
        _git(self.runner, self.source, "revert", "-m", "1", "--no-commit", merge_commit)
        staged = tuple(
            line
            for line in _git_text(
                self.runner, self.source, "diff", "--cached", "--name-only", "--no-renames"
            ).splitlines()
            if line
        )
        unstaged = _git_text(self.runner, self.source, "diff", "--name-only")
        untracked = _git_text(
            self.runner,
            self.source,
            "ls-files",
            "--others",
            "--exclude-standard",
        )
        if tuple(sorted(staged)) != tuple(sorted(plan["changed_paths"])):
            raise RehearsalResetError("staged revert paths differ from the verified task merge")
        if unstaged or untracked:
            raise RehearsalResetError("revert produced unstaged or untracked files")
        name, email = validated_agent_git_identity()
        _git(
            self.runner,
            self.source,
            "-c",
            f"user.name={name}",
            "-c",
            f"user.email={email}",
            "commit",
            "-m",
            f"Revert {self.task_id} for rehearsal rerun",
            "-m",
            (
                "Preserve the completed rehearsal run in history while restoring "
                "the exact pre-task tree for another end-to-end pipeline run."
            ),
            "-m",
            f"{RESET_TASK_TRAILER}: {self.task_id}\n{RESET_MERGE_TRAILER}: {merge_commit}",
        )
        revert_commit = _git_text(self.runner, self.source, "rev-parse", "HEAD")
        _validate_additive_revert_commit(
            self.runner,
            self.source,
            previous_main=previous_main,
            revert_commit=revert_commit,
            merge_parent=merge_parent,
            expected_paths=plan["changed_paths"],
        )
        if _task_state(self.runner, self.source, self.task_id).get("state") != "not_delivered":
            raise RehearsalResetError(
                "additive rehearsal revert did not restore not_delivered"
            )
        _validate_taskgraph(self.runner, self.source)
        _git(self.runner, self.source, "diff", "--check", f"{revert_commit}^")
        _git(
            self.runner,
            self.source,
            "push",
            "origin",
            f"{revert_commit}:refs/heads/main",
        )
        _git(self.runner, self.source, "fetch", "origin", "main")
        if _git_text(self.runner, self.source, "rev-parse", "origin/main") != revert_commit:
            raise RehearsalResetError("pushed rehearsal main could not be verified")
        return revert_commit

    def _transfer_issue(self, plan: dict[str, Any], revert_commit: str) -> str:
        source_issue = plan.get("source_issue")
        if source_issue is None:
            archived = plan.get("archived_issue")
            if not isinstance(archived, dict):
                raise RehearsalResetError("completed Issue is absent from source and archive")
            return str(archived["url"])
        number = int(source_issue["number"])
        comment = (
            "## Disposable rehearsal task reset\n\n"
            f"Vincent requested another end-to-end run of `{self.task_id}` in this private "
            "rehearsal repository. The completed run remains preserved by its merged pull "
            "request and Git history.\n\n"
            f"- Task branch: `{plan['task_branch']}`\n"
            f"- Task head: `{plan['task_head']}`\n"
            f"- Merged PR: {plan['pull_request']['url']}\n"
            f"- Merge commit: `{plan['merge_commit']}`\n"
            f"- Additive revert commit: `{revert_commit}`\n"
            f"- Issue archive: `{self.archive_repository}`\n\n"
            "No commit was erased and `main` history was not rewritten."
        )
        self.runner.run(
            (
                "gh",
                "issue",
                "comment",
                str(number),
                "--repo",
                self.repository,
                "--body",
                comment,
            ),
            cwd=self.source,
        )
        transfer = self.runner.run(
            (
                "gh",
                "issue",
                "transfer",
                str(number),
                self.archive_repository,
                "--repo",
                self.repository,
            ),
            cwd=self.source,
        )
        reported_url = transfer.stdout.strip()
        last_observation_error: RehearsalResetError | None = None
        for delay in (0.0, 1.0, 2.0, 4.0):
            if delay:
                time.sleep(delay)
            try:
                archived = _find_complete_issue(
                    self.runner,
                    self.source,
                    self.archive_repository,
                    self.task_id,
                    self.branch,
                    str(plan["task_head"]),
                    require_state_label=False,
                )
            except RehearsalResetError as exc:
                last_observation_error = exc
                continue
            if archived is not None:
                return str(archived["url"])
        detail = (
            f"; last archive observation error: {last_observation_error}"
            if last_observation_error is not None
            else ""
        )
        raise RehearsalResetError(
            "Issue transfer ran but the exact completed Issue was not visible in the archive"
            + (f"; gh reported {reported_url}" if reported_url else "")
            + detail
        )

    def _delete_task_branch(self, plan: dict[str, Any]) -> None:
        ref = f"refs/heads/{self.branch}"
        raw_expected = plan.get("task_head")
        expected = str(raw_expected) if raw_expected is not None else None
        current = _remote_ref_oid(self.runner, self.source, "origin", ref)
        if current is not None:
            if expected is None or current != expected:
                raise RehearsalResetError("remote task branch moved before exact deletion")
            _git(
                self.runner,
                self.source,
                "push",
                "--porcelain",
                f"--force-with-lease={ref}:{expected}",
                "origin",
                f":{ref}",
            )
            if _remote_ref_oid(self.runner, self.source, "origin", ref) is not None:
                raise RehearsalResetError("remote task branch deletion was not verified")

    def _remove_checkout_and_local_branch(self, plan: dict[str, Any]) -> None:
        expected_checkout_head = str(plan.get("checkout_head") or plan["task_head"])
        if self.checkout.exists():
            remote_oid = _remote_ref_oid(
                self.runner,
                self.source,
                "origin",
                f"refs/heads/{self.branch}",
            )
            _inspect_checkout(
                self.runner,
                self.checkout,
                expected_root=self.checkout_root,
                expected_origin=self.origin,
                expected_branch=self.branch,
                expected_head=expected_checkout_head,
                remote_branch_oid=remote_oid,
            )
            processes = _processes_using_checkout(self.runner, self.source, self.checkout)
            containers = _containers_using_checkout(self.runner, self.source, self.checkout)
            if processes or containers:
                raise RehearsalResetError("task checkout became active after preflight")
            _remove_tree_exact(self.checkout)
            if self.checkout.exists():
                raise RehearsalResetError("task checkout removal was not verified")
        local = _git_text(
            self.runner,
            self.source,
            "rev-parse",
            "--verify",
            f"refs/heads/{self.branch}",
            check=False,
        )
        if local:
            if local != expected_checkout_head:
                raise RehearsalResetError("controller local task branch moved before deletion")
            _git(self.runner, self.source, "branch", "-d", self.branch)

    def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        report_path = (
            self.state_root / "reset-runs" / self.task_id / f"{timestamp}.json"
        )
        report = {**plan, "status": "applying", "report_path": str(report_path)}
        _create_report(report_path, report)
        try:
            revert_commit = (
                str(plan["main_head"])
                if plan["already_reverted"]
                else self._create_and_push_revert(plan)
            )
            report.update({"revert_commit": revert_commit, "status": "main_reverted"})
            _write_report(report_path, report)

            archived_issue_url = self._transfer_issue(plan, revert_commit)
            report.update(
                {"archived_issue_url": archived_issue_url, "status": "issue_archived"}
            )
            _write_report(report_path, report)

            self._delete_task_branch(plan)
            report["status"] = "remote_branch_removed"
            _write_report(report_path, report)

            self._remove_checkout_and_local_branch(plan)
            report["status"] = "checkout_removed"
            _write_report(report_path, report)

            archive, archived_names = _archive_state_files(
                self.state_root, self.task_id, timestamp=timestamp
            )
            report.update(
                {
                    "state_archive": str(archive) if archive else None,
                    "archived_state_files": list(archived_names),
                    "status": "state_archived",
                }
            )
            _write_report(report_path, report)

            _git(self.runner, self.source, "fetch", "--prune", "origin")
            if _git_text(self.runner, self.source, "rev-parse", "HEAD") != revert_commit:
                raise RehearsalResetError("controller HEAD changed during final verification")
            if _git_text(self.runner, self.source, "rev-parse", "origin/main") != revert_commit:
                raise RehearsalResetError("origin/main changed during final verification")
            if _git_text(
                self.runner,
                self.source,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ):
                raise RehearsalResetError("controller is dirty after reset")
            if _remote_ref_oid(
                self.runner,
                self.source,
                "origin",
                f"refs/heads/{self.branch}",
            ) is not None:
                raise RehearsalResetError("task branch still exists after reset")
            if self.checkout.exists():
                raise RehearsalResetError("task checkout still exists after reset")
            remaining_state = [
                str(path)
                for path in _state_paths(self.state_root, self.task_id)
                if path.exists()
            ]
            if remaining_state:
                raise RehearsalResetError(
                    f"active task state remains after reset: {remaining_state}"
                )
            if _relevant_claims(self.source, self.task):
                raise RehearsalResetError("task/resource claim refs appeared during reset")
            source_issue = _find_complete_issue(
                self.runner,
                self.source,
                self.repository,
                self.task_id,
                self.branch,
                str(plan["task_head"]),
                require_state_label=True,
            )
            if source_issue is not None:
                raise RehearsalResetError("completed Issue still exists in the active repository")
            archived_issue = _find_complete_issue(
                self.runner,
                self.source,
                self.archive_repository,
                self.task_id,
                self.branch,
                str(plan["task_head"]),
                require_state_label=False,
            )
            if archived_issue is None:
                raise RehearsalResetError("completed Issue is not preserved in the archive")
            task_state = _task_state(self.runner, self.source, self.task_id)
            if task_state.get("state") != "not_delivered":
                raise RehearsalResetError("TaskGraph did not return to not_delivered")
            _validate_taskgraph(self.runner, self.source)
            report.update(
                {
                    "status": "complete",
                    "main_head": revert_commit,
                    "taskgraph_state": "not_delivered",
                    "archived_issue_url": archived_issue["url"],
                }
            )
            _write_report(report_path, report)
            return report
        except Exception as exc:
            report.update({"status": "stopped", "error": str(exc)})
            _write_report(report_path, report)
            raise


def _default_archive_repository(repository: str) -> str:
    owner, name = repository.split("/", 1)
    return f"{owner}/{name}-Archive"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id", help="Exact task ID, for example NSC-901")
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument(
        "--checkout-root",
        type=Path,
        help="Parent containing <TASK-ID> and .task-review-agent (default: source parent)",
    )
    parser.add_argument(
        "--archive-repository",
        help="Private Issue archive (default: <source-repository>-Archive)",
    )
    parser.add_argument(
        "--confirm-repository",
        help="Required with --apply; must exactly match the source GitHub repository",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the guarded revert and cleanup; omission is read-only preflight",
    )
    args = parser.parse_args(argv)
    try:
        source = args.source.resolve()
        origin = _git_text(CommandRunner(), source, "remote", "get-url", "origin")
        repository = _repository_from_origin(origin)
        archive_repository = args.archive_repository or _default_archive_repository(repository)
        reset = RehearsalTaskReset(
            source=source,
            checkout_root=(args.checkout_root or source.parent),
            task_id=args.task_id,
            archive_repository=archive_repository,
        )
        plan = reset.preflight()
        if not args.apply:
            print(json.dumps({**plan, "status": "ready_dry_run"}, indent=2, sort_keys=True))
            print(
                "\nDry run only. Re-run with --apply and "
                f"--confirm-repository {repository} to perform the reset.",
                file=sys.stderr,
            )
            return 0
        if not args.confirm_repository or args.confirm_repository.casefold() != repository.casefold():
            raise RehearsalResetError(
                f"--apply requires --confirm-repository {repository}"
            )
        report = reset.apply(plan)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, RehearsalResetError) as exc:
        print(f"REHEARSAL TASK RESET: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
