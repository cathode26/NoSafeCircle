#!/usr/bin/env python3
"""Safely clear abandoned task state in production or repeat a rehearsal task."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import semantic_sha256, validate_task_id  # noqa: E402
from Pipeline.TaskReviewAgent.git_identity_guard import (  # noqa: E402
    validated_agent_git_identity,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    ALL_STATE_LABELS,
    STATE_LABELS,
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    parse_events,
    parse_state,
    validate_event_chain,
)
from Pipeline.TaskReviewAgent.real_checkout import branch_name  # noqa: E402
from Pipeline.TaskReviewAgent.reset_rehearsal_task import (  # noqa: E402
    CommandRunner,
    RehearsalResetError,
    RehearsalTaskReset,
    _archive_state_files,
    _changed_paths,
    _commit_parents,
    _containers_using_checkout,
    _create_report,
    _controller_task_worktrees,
    _find_pull_request,
    _git,
    _git_text,
    _inspect_checkout,
    _json_command,
    _path_is_reparse_point,
    _processes_using_checkout,
    _relevant_claims,
    _remote_ref_oid,
    _remove_tree_exact,
    _repo_metadata,
    _repository_from_origin,
    _require_archive_repository,
    _require_private_rehearsal_repository,
    _state_paths,
    _task_state,
    _validate_complete_issue,
    _validate_pull_request,
    _validate_taskgraph,
    _write_report,
)


class TaskResetError(RehearsalResetError):
    """Raised when production abandoned-state cleanup cannot be proven safe."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


PRODUCTION_RESET_TASK_TRAILER = "NSC-Production-Reset-Task"
PRODUCTION_RESET_MERGE_TRAILER = "NSC-Production-Reset-Merge"


def _managed_task_issues(
    runner: CommandRunner,
    source: Path,
    repository: str,
    task_id: str,
    state: str,
) -> list[dict[str, Any]]:
    value = _json_command(
        runner,
        (
            "gh",
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            state,
            "--search",
            f"{task_id} in:title",
            "--limit",
            "100",
            "--json",
            "number,title,state,url,body,labels",
        ),
        cwd=source,
    )
    if not isinstance(value, list):
        raise TaskResetError("GitHub Issue listing was invalid")
    marker = f"<!-- no-safe-circle-task: {task_id} -->"
    return [
        issue
        for issue in value
        if isinstance(issue, dict)
        and (
            str(issue.get("title") or "") == task_id
            or str(issue.get("title") or "").startswith(f"{task_id} —")
            or marker in str(issue.get("body") or "")
        )
    ]


def _task_pull_requests(
    runner: CommandRunner,
    source: Path,
    repository: str,
    branch: str,
    state: str,
) -> list[dict[str, Any]]:
    value = _json_command(
        runner,
        (
            "gh",
            "pr",
            "list",
            "--repo",
            repository,
            "--state",
            state,
            "--head",
            branch,
            "--limit",
            "100",
            "--json",
            "number,title,state,url,headRefName,headRefOid,mergeCommit",
        ),
        cwd=source,
    )
    if not isinstance(value, list):
        raise TaskResetError("GitHub pull-request listing was invalid")
    return [item for item in value if isinstance(item, dict)]


def _wait_for_managed_issue_close(
    runner: CommandRunner,
    source: Path,
    repository: str,
    task_id: str,
    issue_number: int,
) -> None:
    """Wait for GitHub's exact Issue view and search indexes to agree."""

    for attempt in range(8):
        exact = _json_command(
            runner,
            (
                "gh",
                "issue",
                "view",
                str(issue_number),
                "--repo",
                repository,
                "--json",
                "number,state",
            ),
            cwd=source,
        )
        open_issues = _managed_task_issues(
            runner, source, repository, task_id, "open"
        )
        closed_numbers = {
            item.get("number")
            for item in _managed_task_issues(
                runner, source, repository, task_id, "closed"
            )
        }
        if (
            isinstance(exact, dict)
            and exact.get("number") == issue_number
            and exact.get("state") == "CLOSED"
            and not open_issues
            and issue_number in closed_numbers
        ):
            return
        if attempt < 7:
            time.sleep(min(1 + attempt, 4))
    raise TaskResetError(
        "GitHub Issue close did not become consistent across exact view and search"
    )


def _fetch_exact_remote_commit_object(
    runner: CommandRunner,
    source: Path,
    *,
    remote: str,
    ref: str,
    expected_oid: str,
) -> None:
    """Fetch one observed remote ref without creating or moving a local ref."""

    if re.fullmatch(r"[0-9a-f]{40}", expected_oid) is None:
        raise TaskResetError("remote task branch OID is invalid")
    _git(
        runner,
        source,
        "fetch",
        "--no-tags",
        "--no-write-fetch-head",
        remote,
        ref,
    )
    object_type = _git_text(
        runner,
        source,
        "cat-file",
        "-t",
        expected_oid,
        check=False,
    )
    if object_type != "commit":
        raise TaskResetError(
            "the exact observed remote task-branch commit was not fetched"
        )


def _validated_incomplete_issue(
    runner: CommandRunner,
    source: Path,
    repository: str,
    issue: dict[str, Any],
    *,
    task_id: str,
    branch: str,
) -> tuple[Any, str | None, dict[str, Any] | None]:
    number = issue.get("number")
    body = issue.get("body")
    if type(number) is not int or not isinstance(body, str):
        raise TaskResetError("managed Issue identity is invalid")
    state = parse_state(body)
    if state is None or state.task_id != task_id:
        raise TaskResetError("open Issue does not contain the exact managed task state")
    if state.state is WorkflowState.COMPLETE:
        raise TaskResetError("completed rehearsal work requires merged-rehearsal reset mode")
    if state.branch not in (None, branch):
        raise TaskResetError("open Issue branch differs from the abandoned task branch")
    comments_value = _json_command(
        runner,
        (
            "gh",
            "issue",
            "view",
            str(number),
            "--repo",
            repository,
            "--json",
            "comments",
        ),
        cwd=source,
    )
    comments = comments_value.get("comments") if isinstance(comments_value, dict) else None
    if not isinstance(comments, list):
        raise TaskResetError("managed Issue comments were not readable")
    events = parse_events(comments)
    validate_event_chain(state, events)
    task_head = str(state.head_commit) if state.head_commit is not None else None
    lease_events = [
        event
        for event in events
        if event.event_type.value == "agent_lease_acquired"
    ]
    latest_lease = dict(lease_events[-1].details) if lease_events else None
    if task_head is None:
        # A run may be abandoned after its lease is released or blocked but before
        # prepare_task_checkout creates a branch.  In that state the projected
        # workflow deliberately clears branch/head/checkout identity.  The
        # append-only lease event must still name this contract's exact branch if
        # a lease was ever acquired; otherwise this is the pristine initialized
        # Issue and has no run-owned Git object to remove.
        leased_branches = {
            event.details.get("branch")
            for event in lease_events
        }
        if leased_branches and leased_branches != {branch}:
            raise TaskResetError(
                "managed Issue lease history differs from the abandoned task branch"
            )
        if any(
            value is not None
            for value in (
                state.branch,
                state.checkout_path,
                state.head_commit,
                state.human_handoff_commit,
            )
        ):
            raise TaskResetError(
                "branchless abandoned Issue retains partial Git identity"
            )
    return state, task_head, latest_lease


def _validate_branchless_checkout_manifest(
    path: Path,
    *,
    task: dict[str, Any],
    checkout: Path,
    branch: str,
    source_head: str | None,
    source_tree: str | None,
    origin: str,
) -> dict[str, Any]:
    """Validate the durable identity of a pre-candidate checkout.

    A released implementation lease deliberately projects branch/head/checkout
    as null in the live Issue. The standalone checkout may nevertheless exist
    at the exact clean base recorded by the final acquired lease. Only its
    hash-bound durable manifest can authorize removing that otherwise
    branchless local state.
    """

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TaskResetError("branchless checkout manifest is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise TaskResetError("branchless checkout manifest must be a JSON object")
    manifest_hash = value.get("manifest_sha256")
    payload = {key: item for key, item in value.items() if key != "manifest_sha256"}
    if manifest_hash != semantic_sha256(payload):
        raise TaskResetError("branchless checkout manifest hash is invalid")
    expected = {
        "schema_version": "2.0",
        "task_id": task.get("id"),
        "checkout_path": str(checkout),
        "branch": branch,
        "task_contract_path": f"Tasks/{task.get('id')}.yaml",
        "task_contract_revision": task.get("contract_revision"),
        "task_contract_sha256": task.get("task_contract_sha256"),
        "authority": "durable_checkout_identity",
    }
    if source_head is not None:
        expected["initial_source_head"] = source_head
    if source_tree is not None:
        expected["initial_source_tree"] = source_tree
    mismatched = [
        key for key, expected_value in expected.items()
        if value.get(key) != expected_value
    ]
    if mismatched:
        raise TaskResetError(
            "branchless checkout manifest differs from the exact abandoned lease: "
            + ", ".join(mismatched)
        )
    if _repository_from_origin(str(value.get("remote_url") or "")).casefold() != (
        _repository_from_origin(origin).casefold()
    ):
        raise TaskResetError("branchless checkout manifest origin differs from controller origin")
    return value


def _validate_branchless_checkout_source(
    runner: CommandRunner,
    source: Path,
    *,
    manifest: dict[str, Any],
    current_main: str,
) -> str:
    """Return a hash-bound checkout base proven to be in current main history."""

    manifest_head = manifest.get("initial_source_head")
    manifest_tree = manifest.get("initial_source_tree")
    if (
        not isinstance(manifest_head, str)
        or re.fullmatch(r"[0-9a-f]{40}", manifest_head) is None
        or not isinstance(manifest_tree, str)
        or re.fullmatch(r"[0-9a-f]{40}", manifest_tree) is None
    ):
        raise TaskResetError("branchless checkout manifest source identity is invalid")
    if (
        _git(
            runner,
            source,
            "merge-base",
            "--is-ancestor",
            manifest_head,
            current_main,
            check=False,
        ).returncode
        != 0
    ):
        raise TaskResetError(
            "branchless checkout manifest source is outside current main ancestry"
        )
    if (
        _git_text(runner, source, "rev-parse", f"{manifest_head}^{{tree}}")
        != manifest_tree
    ):
        raise TaskResetError(
            "branchless checkout manifest source tree differs from its commit"
        )
    return manifest_head


def _is_unpushed_decomposition_baseline(
    workflow_state: Any,
    task: Mapping[str, Any],
    *,
    task_head: str | None,
    remote_branch_oid: str | None,
) -> bool:
    """Recognize a plan-only decomposition checkout that has no pushed code."""

    return bool(
        task_head is not None
        and remote_branch_oid is None
        and workflow_state.phase
        in {
            WorkflowPhase.DECOMPOSITION,
            WorkflowPhase.DECOMPOSITION_APPLY_AUTHORIZATION,
            WorkflowPhase.DECOMPOSITION_APPLY,
        }
        and workflow_state.human_handoff_commit == task_head
        and task.get("execution_scope") == "needs_execution_decomposition"
        and task.get("decomposition_state") != "decomposed"
        and not task.get("decomposition_children")
    )


def _abandoned_rehearsal_state_is_undelivered(
    task: Mapping[str, Any], state: str | None
) -> bool:
    if state == "not_delivered":
        return True
    return bool(
        state == "aggregate"
        and task.get("execution_scope") == "needs_execution_decomposition"
        and task.get("decomposition_state") != "decomposed"
        and not task.get("decomposition_children")
    )


class AbandonedRehearsalTaskReset(RehearsalTaskReset):
    """Close and remove one exact unmerged rehearsal run without touching main."""

    def preflight(self) -> dict[str, Any]:
        if not self.source.is_dir() or not self.checkout_root.is_dir():
            raise TaskResetError("source and checkout root must already exist")
        if Path(_git_text(self.runner, self.source, "rev-parse", "--show-toplevel")).resolve() != self.source:
            raise TaskResetError("source is not the exact Git repository root")
        if _git_text(self.runner, self.source, "branch", "--show-current") != "main":
            raise TaskResetError("controller must be on main")
        if _git_text(
            self.runner,
            self.source,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            raise TaskResetError("controller working tree is not completely clean")

        source_meta = _repo_metadata(self.runner, self.source, self.repository)
        _require_private_rehearsal_repository(source_meta, self.repository)
        _git(self.runner, self.source, "fetch", "--prune", "origin", "main")
        head = _git_text(self.runner, self.source, "rev-parse", "HEAD")
        if _git_text(self.runner, self.source, "rev-parse", "origin/main") != head:
            raise TaskResetError("controller HEAD must exactly equal fetched origin/main")
        task_state = _task_state(self.runner, self.source, self.task_id)
        if not _abandoned_rehearsal_state_is_undelivered(
            self.task, task_state.get("state")
        ):
            raise TaskResetError(
                "abandoned rehearsal cleanup cannot remove delivered work; TaskGraph must "
                f"report not_delivered, found {task_state.get('state')!r}"
            )
        _validate_taskgraph(self.runner, self.source)

        issues = _managed_task_issues(
            self.runner, self.source, self.repository, self.task_id, "open"
        )
        if len(issues) != 1:
            raise TaskResetError(
                "exactly one open managed Issue must identify the abandoned rehearsal run"
            )
        issue = issues[0]
        workflow_state, task_head, latest_lease = _validated_incomplete_issue(
            self.runner,
            self.source,
            self.repository,
            issue,
            task_id=self.task_id,
            branch=self.branch,
        )
        if workflow_state.task_contract_sha256 != self.task.get("task_contract_sha256"):
            raise TaskResetError("managed Issue task-contract identity changed")
        remote_ref = f"refs/heads/{self.branch}"
        remote_branch_oid = _remote_ref_oid(
            self.runner,
            self.source,
            "origin",
            remote_ref,
        )
        unpushed_decomposition_baseline = _is_unpushed_decomposition_baseline(
            workflow_state,
            self.task,
            task_head=task_head,
            remote_branch_oid=remote_branch_oid,
        )
        if remote_branch_oid != task_head and not unpushed_decomposition_baseline:
            raise TaskResetError("remote task branch differs from the managed Issue head")
        if remote_branch_oid is not None:
            _fetch_exact_remote_commit_object(
                self.runner,
                self.source,
                remote="origin",
                ref=remote_ref,
                expected_oid=remote_branch_oid,
            )
        task_head_is_in_main = bool(
            task_head is not None
            and _git(
                self.runner,
                self.source,
                "merge-base",
                "--is-ancestor",
                task_head,
                head,
                check=False,
            ).returncode
            == 0
        )
        if task_head_is_in_main and not unpushed_decomposition_baseline:
            raise TaskResetError("abandoned task head is already contained in main")

        pull_requests = _task_pull_requests(
            self.runner, self.source, self.repository, self.branch, "open"
        )
        if len(pull_requests) > 1:
            raise TaskResetError("multiple open pull requests use the abandoned task branch")
        if pull_requests and (
            task_head is None or pull_requests[0].get("headRefOid") != task_head
        ):
            raise TaskResetError("open pull-request head differs from the managed Issue head")
        claims = _relevant_claims(self.source, self.task)
        if claims:
            raise TaskResetError(
                "task/resource claim refs still exist; exact-OID stale-claim repair is required:\n"
                + json.dumps(claims, indent=2, sort_keys=True)
            )
        worktrees = _controller_task_worktrees(
            self.runner, self.source, self.task_id, self.branch
        )
        if any(Path(item.get("worktree") or ".").resolve() != self.source for item in worktrees):
            raise TaskResetError("task-specific linked worktree exists; reset is refused")

        checkout_facts = None
        checkout_head = task_head
        if self.checkout.exists():
            if task_head is None:
                if not isinstance(latest_lease, dict):
                    raise TaskResetError(
                        "branchless abandoned Issue has a checkout but no acquired lease"
                    )
                lease_branch = latest_lease.get("branch")
                lease_path = latest_lease.get("checkout_path")
                lease_head = latest_lease.get("source_head")
                if lease_branch != self.branch:
                    raise TaskResetError("latest abandoned lease branch differs from task branch")
                try:
                    lease_checkout = Path(str(lease_path)).resolve()
                except (OSError, ValueError) as exc:
                    raise TaskResetError("latest abandoned lease checkout path is invalid") from exc
                if lease_checkout != self.checkout.resolve():
                    raise TaskResetError("latest abandoned lease checkout differs from canonical path")
                if (
                    not isinstance(lease_head, str)
                    or re.fullmatch(r"[0-9a-f]{40}", lease_head) is None
                ):
                    raise TaskResetError("latest abandoned lease source head is invalid")
                if (
                    _git(
                        self.runner,
                        self.source,
                        "merge-base",
                        "--is-ancestor",
                        lease_head,
                        head,
                        check=False,
                    ).returncode
                    != 0
                ):
                    raise TaskResetError("latest abandoned lease source is not in current main history")
                checkout_head = lease_head
            if not self.checkout.is_dir():
                raise TaskResetError("canonical task checkout is not a directory")
            if task_head is None:
                manifest = _validate_branchless_checkout_manifest(
                    self.state_root / f"{self.task_id}.json",
                    task=self.task,
                    checkout=self.checkout,
                    branch=self.branch,
                    source_head=None,
                    source_tree=None,
                    origin=self.origin,
                )
                checkout_head = _validate_branchless_checkout_source(
                    self.runner,
                    self.source,
                    manifest=manifest,
                    current_main=head,
                )
            assert checkout_head is not None
            checkout_facts = _inspect_checkout(
                self.runner,
                self.checkout,
                expected_root=self.checkout_root,
                expected_origin=self.origin,
                expected_branch=self.branch,
                expected_head=checkout_head,
                remote_branch_oid=remote_branch_oid,
            )
            processes = _processes_using_checkout(self.runner, self.source, self.checkout)
            containers = _containers_using_checkout(self.runner, self.source, self.checkout)
            if processes or containers:
                raise TaskResetError(
                    "task checkout is still in use; reset is refused:\n"
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
        if local_branch_oid is not None and local_branch_oid != checkout_head:
            raise TaskResetError("controller local task branch differs from the managed Issue head")
        active_state_files = [
            str(path) for path in _state_paths(self.state_root, self.task_id) if path.is_file()
        ]
        return {
            "schema_version": "1.0",
            "operation": "abandon_incomplete_task_in_private_rehearsal",
            "task_id": self.task_id,
            "repository": self.repository,
            "main_head": head,
            "taskgraph_state": task_state.get("state"),
            "task_branch": self.branch,
            "task_head": task_head,
            "checkout_head": checkout_head,
            "issue": {"number": issue["number"], "url": issue["url"]},
            "pull_request": (
                {
                    "number": pull_requests[0]["number"],
                    "url": pull_requests[0]["url"],
                }
                if pull_requests
                else None
            ),
            "remote_branch_oid": remote_branch_oid,
            "local_branch_oid": local_branch_oid,
            "checkout": checkout_facts,
            "active_state_files": active_state_files,
            "retained_outputs": str(self.state_root / "outputs" / self.task_id),
        }

    def _close_abandoned_github_objects(self, plan: dict[str, Any]) -> None:
        task_head = plan.get("task_head") or "not created"
        body = (
            "## Abandoned rehearsal run reset\n\n"
            f"Vincent explicitly requested a fresh `{self.task_id}` rehearsal run. "
            "This incomplete run was not merged and no completion was fabricated.\n\n"
            f"- Task branch: `{plan['task_branch']}`\n"
            f"- Abandoned head: `{task_head}`\n"
            f"- Replacement base: current `main` at `{plan['main_head']}`\n\n"
            "The Issue/PR discussion and immutable run outputs remain as audit history."
        )
        pull_request = plan.get("pull_request")
        if isinstance(pull_request, dict):
            number = str(pull_request["number"])
            self.runner.run(
                ("gh", "pr", "comment", number, "--repo", self.repository, "--body", body),
                cwd=self.source,
            )
            self.runner.run(
                ("gh", "pr", "close", number, "--repo", self.repository),
                cwd=self.source,
            )
        issue_number = str(plan["issue"]["number"])
        self.runner.run(
            ("gh", "issue", "comment", issue_number, "--repo", self.repository, "--body", body),
            cwd=self.source,
        )
        self.runner.run(
            ("gh", "issue", "close", issue_number, "--repo", self.repository),
            cwd=self.source,
        )

    def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        report_path = self.state_root / "reset-runs" / self.task_id / f"{timestamp}.json"
        report = {**plan, "status": "applying", "report_path": str(report_path)}
        _create_report(report_path, report)
        try:
            if _git_text(self.runner, self.source, "rev-parse", "HEAD") != plan["main_head"]:
                raise TaskResetError("controller main moved after preflight")
            if _remote_ref_oid(
                self.runner, self.source, "origin", f"refs/heads/{self.branch}"
            ) != plan["remote_branch_oid"]:
                raise TaskResetError("remote task branch moved after preflight")
            self._close_abandoned_github_objects(plan)
            report["status"] = "github_objects_closed"
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
            if _git_text(self.runner, self.source, "rev-parse", "HEAD") != plan["main_head"]:
                raise TaskResetError("controller main changed during reset")
            if _git_text(self.runner, self.source, "rev-parse", "origin/main") != plan["main_head"]:
                raise TaskResetError("origin/main changed during reset")
            if _git_text(
                self.runner,
                self.source,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ):
                raise TaskResetError("controller is dirty after reset")
            _wait_for_managed_issue_close(
                self.runner,
                self.source,
                self.repository,
                self.task_id,
                int(plan["issue"]["number"]),
            )
            if _task_pull_requests(
                self.runner, self.source, self.repository, self.branch, "open"
            ):
                raise TaskResetError("task pull request is still open after reset")
            if _remote_ref_oid(
                self.runner, self.source, "origin", f"refs/heads/{self.branch}"
            ) is not None:
                raise TaskResetError("task branch still exists after reset")
            if self.checkout.exists():
                raise TaskResetError("task checkout still exists after reset")
            if any(path.exists() for path in _state_paths(self.state_root, self.task_id)):
                raise TaskResetError("active task state remains after reset")
            if _relevant_claims(self.source, self.task):
                raise TaskResetError("task/resource claim refs appeared during reset")
            final_task_state = _task_state(
                self.runner, self.source, self.task_id
            ).get("state")
            if not _abandoned_rehearsal_state_is_undelivered(
                self.task, final_task_state
            ):
                raise TaskResetError("TaskGraph did not remain undelivered")
            _validate_taskgraph(self.runner, self.source)
            report.update({"status": "complete", "taskgraph_state": final_task_state})
            _write_report(report_path, report)
            return report
        except Exception as exc:
            report.update({"status": "stopped", "error": str(exc)})
            _write_report(report_path, report)
            raise

    def resume(self, report_path: Path) -> dict[str, Any]:
        report_path = report_path.resolve()
        expected_parent = (self.state_root / "reset-runs" / self.task_id).resolve()
        if report_path.parent != expected_parent or not report_path.is_file():
            raise TaskResetError("resume receipt is not the exact task reset receipt path")
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TaskResetError("resume receipt is not valid UTF-8 JSON") from exc
        if not isinstance(report, dict):
            raise TaskResetError("resume receipt must be a JSON object")
        fixed = {
            "operation": "abandon_incomplete_task_in_private_rehearsal",
            "task_id": self.task_id,
            "repository": self.repository,
            "report_path": str(report_path),
        }
        for field, expected in fixed.items():
            if report.get(field) != expected:
                raise TaskResetError(
                    f"resume receipt {field} differs from the requested reset"
                )
        if report.get("status") not in {
            "stopped",
            "github_objects_closed",
            "remote_branch_removed",
            "checkout_removed",
            "state_archived",
        }:
            raise TaskResetError("resume receipt status is not safely resumable")
        main_head = str(report.get("main_head") or "")
        raw_task_head = report.get("task_head")
        task_head = str(raw_task_head) if raw_task_head is not None else None
        raw_checkout_head = report.get("checkout_head")
        checkout_head = (
            str(raw_checkout_head)
            if raw_checkout_head is not None
            else task_head
        )
        issue = report.get("issue")
        checkout_facts = report.get("checkout")
        if (
            not re.fullmatch(r"[0-9a-f]{40}", main_head)
            or (task_head is not None and not re.fullmatch(r"[0-9a-f]{40}", task_head))
            or (
                checkout_head is not None
                and not re.fullmatch(r"[0-9a-f]{40}", checkout_head)
            )
            or not isinstance(issue, dict)
            or type(issue.get("number")) is not int
            or (
                checkout_facts is not None
                and (
                    checkout_head is None
                    or not isinstance(checkout_facts, dict)
                    or checkout_facts.get("path") != str(self.checkout)
                    or checkout_facts.get("head") != checkout_head
                    or checkout_facts.get("branch") != self.branch
                )
            )
        ):
            raise TaskResetError("resume receipt omitted exact preflight identities")
        if _git_text(self.runner, self.source, "rev-parse", "HEAD") != main_head:
            raise TaskResetError("controller main moved after the stopped reset")
        _git(self.runner, self.source, "fetch", "origin", "main")
        if _git_text(self.runner, self.source, "rev-parse", "origin/main") != main_head:
            raise TaskResetError("origin/main moved after the stopped reset")
        if _remote_ref_oid(
            self.runner, self.source, "origin", f"refs/heads/{self.branch}"
        ) is not None:
            raise TaskResetError("remote task branch reappeared after the stopped reset")
        issue_value = _json_command(
            self.runner,
            (
                "gh",
                "issue",
                "view",
                str(issue["number"]),
                "--repo",
                self.repository,
                "--json",
                "state,url",
            ),
            cwd=self.source,
        )
        if not isinstance(issue_value, dict) or issue_value.get("state") != "CLOSED":
            raise TaskResetError("abandoned Issue is not closed during resume")
        if self.checkout.exists():
            if checkout_head is None or not isinstance(checkout_facts, dict):
                raise TaskResetError("resume receipt does not authorize checkout removal")
            if (
                self.checkout.resolve() != (self.checkout_root / self.task_id).resolve()
                or self.checkout.parent.resolve() != self.checkout_root
                or _path_is_reparse_point(self.checkout)
            ):
                raise TaskResetError("partial checkout path no longer matches the exact target")
            _inspect_checkout(
                self.runner,
                self.checkout,
                expected_root=self.checkout_root,
                expected_origin=self.origin,
                expected_branch=self.branch,
                expected_head=checkout_head,
                remote_branch_oid=None,
            )
            processes = _processes_using_checkout(self.runner, self.source, self.checkout)
            containers = _containers_using_checkout(self.runner, self.source, self.checkout)
            if processes or containers:
                raise TaskResetError("partial checkout became active; resume is refused")
            _remove_tree_exact(self.checkout)
            if self.checkout.exists():
                raise TaskResetError("partial checkout removal was not verified")
        report["status"] = "checkout_removed"
        report.pop("error", None)
        _write_report(report_path, report)
        archive, archived_names = _archive_state_files(
            self.state_root,
            self.task_id,
            timestamp=report_path.stem,
        )
        report.update(
            {
                "state_archive": str(archive) if archive else None,
                "archived_state_files": list(archived_names),
                "status": "state_archived",
            }
        )
        _write_report(report_path, report)
        if any(path.exists() for path in _state_paths(self.state_root, self.task_id)):
            raise TaskResetError("active task state remains after resumed reset")
        final_task_state = _task_state(self.runner, self.source, self.task_id).get(
            "state"
        )
        if not _abandoned_rehearsal_state_is_undelivered(
            self.task, final_task_state
        ):
            raise TaskResetError("TaskGraph did not remain undelivered")
        _validate_taskgraph(self.runner, self.source)
        report.update({"status": "complete", "taskgraph_state": final_task_state})
        _write_report(report_path, report)
        return report


def _tree_entry(
    runner: CommandRunner, source: Path, commit: str, path: str
) -> tuple[str, str, str] | None:
    value = _git_text(runner, source, "ls-tree", commit, "--", path)
    if not value:
        return None
    lines = value.splitlines()
    if len(lines) != 1:
        raise TaskResetError(f"tree lookup returned multiple entries for {path}")
    metadata, separator, returned_path = lines[0].partition("\t")
    fields = metadata.split()
    if not separator or returned_path != path or len(fields) != 3:
        raise TaskResetError(f"tree lookup returned an invalid entry for {path}")
    return fields[0], fields[1], fields[2]


def _require_task_paths_unchanged_since_merge(
    runner: CommandRunner,
    source: Path,
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
            source,
            "rev-list",
            "--ancestry-path",
            current_main,
            f"^{merge_commit}",
        ).splitlines()
        if line
    )
    touched: dict[str, list[str]] = {}
    for commit in later_commits:
        parents = _commit_parents(runner, source, commit)
        if not parents:
            raise TaskResetError("later production history contains a parentless commit")
        changed = {
            line.casefold()
            for line in _git_text(
                runner,
                source,
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
        raise TaskResetError(
            "later production commits changed task-owned paths; automatic revert is refused:\n"
            + json.dumps(touched, indent=2, sort_keys=True)
        )


def _committed_task_contracts(
    runner: CommandRunner, source: Path
) -> dict[str, dict[str, Any]]:
    listing = _git_text(
        runner, source, "ls-tree", "-r", "--name-only", "HEAD", "--", "Tasks"
    )
    contracts: dict[str, dict[str, Any]] = {}
    for path in listing.splitlines():
        if not re.fullmatch(r"Tasks/NSC-[0-9]{3}\.yaml", path):
            continue
        raw = _git_text(runner, source, "show", f"HEAD:{path}")
        try:
            contract = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TaskResetError(f"committed task contract is invalid JSON: {path}") from exc
        task_id = contract.get("id") if isinstance(contract, dict) else None
        if not isinstance(task_id, str) or task_id in contracts:
            raise TaskResetError(f"committed task identity is invalid or duplicated: {path}")
        contracts[task_id] = contract
    return contracts


def _transitive_active_dependents(
    contracts: dict[str, dict[str, Any]], task_id: str
) -> tuple[str, ...]:
    reverse: dict[str, set[str]] = {}
    for dependent_id, contract in contracts.items():
        if contract.get("contract_disposition") != "active":
            continue
        dependencies = contract.get("depends_on")
        if not isinstance(dependencies, list):
            raise TaskResetError(f"{dependent_id}.depends_on is not a list")
        for dependency_id in dependencies:
            if not isinstance(dependency_id, str):
                raise TaskResetError(f"{dependent_id}.depends_on contains a non-string")
            reverse.setdefault(dependency_id, set()).add(dependent_id)
    found: set[str] = set()
    pending = list(sorted(reverse.get(task_id, set())))
    while pending:
        dependent_id = pending.pop(0)
        if dependent_id in found:
            continue
        found.add(dependent_id)
        pending.extend(sorted(reverse.get(dependent_id, set()) - found))
    return tuple(sorted(found))


def _require_no_built_dependents(
    runner: CommandRunner, source: Path, task_id: str
) -> None:
    contracts = _committed_task_contracts(runner, source)
    dependents = _transitive_active_dependents(contracts, task_id)
    if not dependents:
        return
    value = _json_command(
        runner,
        (
            sys.executable,
            str(source / "Pipeline" / "TaskGraph" / "taskcontrol.py"),
            "states",
            "--json",
        ),
        cwd=source,
    )
    if not isinstance(value, list):
        raise TaskResetError("TaskGraph states result was invalid")
    by_id = {
        item.get("task_id"): item
        for item in value
        if isinstance(item, dict) and isinstance(item.get("task_id"), str)
    }
    missing = [dependent_id for dependent_id in dependents if dependent_id not in by_id]
    if missing:
        raise TaskResetError(
            "TaskGraph did not report dependent state for: " + ", ".join(missing)
        )
    built = [
        {
            "task_id": dependent_id,
            "state": by_id[dependent_id].get("state"),
            "selected_record_id": by_id[dependent_id].get("selected_record_id"),
        }
        for dependent_id in dependents
        if by_id[dependent_id].get("state") != "not_delivered"
    ]
    if built:
        raise TaskResetError(
            "one or more direct/transitive dependent tasks are already built or otherwise "
            "past not_delivered; production revert is refused:\n"
            + json.dumps(built, indent=2, sort_keys=True)
        )


def _complete_production_issues(
    runner: CommandRunner,
    source: Path,
    repository: str,
    task_id: str,
    branch: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for issue in _managed_task_issues(
        runner, source, repository, task_id, "closed"
    ):
        body = issue.get("body")
        if not isinstance(body, str):
            continue
        try:
            state = parse_state(body)
        except ValueError:
            continue
        if (
            state is not None
            and state.state is WorkflowState.COMPLETE
            and state.task_id == task_id
            and state.branch == branch
            and state.head_commit is not None
        ):
            candidate = {**issue, "workflow_state": state}
            _validate_complete_issue(
                runner,
                source,
                repository,
                candidate,
                require_state_label=True,
            )
            candidates.append(candidate)
    return candidates


class ProductionDeliveredTaskReset(RehearsalTaskReset):
    """Additively revert one exact completed production delivery."""

    def preflight(self) -> dict[str, Any]:
        if Path(_git_text(self.runner, self.source, "rev-parse", "--show-toplevel")).resolve() != self.source:
            raise TaskResetError("source is not the exact Git repository root")
        if _git_text(self.runner, self.source, "branch", "--show-current") != "main":
            raise TaskResetError("production controller must be on main")
        if _git_text(
            self.runner,
            self.source,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            raise TaskResetError("production controller is not completely clean")
        metadata = _repo_metadata(self.runner, self.source, self.repository)
        if str(metadata.get("nameWithOwner") or "").casefold() != self.repository.casefold():
            raise TaskResetError("GitHub repository identity changed")
        if metadata.get("isArchived") is True:
            raise TaskResetError("production repository is archived")
        if "rehearsal" in self.repository.casefold():
            raise TaskResetError("use merged-rehearsal mode for rehearsal repositories")

        _git(self.runner, self.source, "fetch", "--prune", "origin", "main")
        head = _git_text(self.runner, self.source, "rev-parse", "HEAD")
        if _git_text(self.runner, self.source, "rev-parse", "origin/main") != head:
            raise TaskResetError("production HEAD must exactly equal fetched origin/main")
        task_state = _task_state(self.runner, self.source, self.task_id)
        if task_state.get("state") != "conformant":
            raise TaskResetError(
                "there is no conformant delivered production task to revert; "
                f"TaskGraph reports {task_state.get('state')!r}"
            )
        _validate_taskgraph(self.runner, self.source)
        _require_no_built_dependents(self.runner, self.source, self.task_id)

        archive_meta = _repo_metadata(
            self.runner, self.source, self.archive_repository
        )
        _require_archive_repository(
            archive_meta,
            source_repository=self.repository,
            archive_repository=self.archive_repository,
        )
        open_issues = _managed_task_issues(
            self.runner, self.source, self.repository, self.task_id, "open"
        )
        if open_issues:
            raise TaskResetError("an open task Issue exists; delivered reset is refused")
        issues = _complete_production_issues(
            self.runner,
            self.source,
            self.repository,
            self.task_id,
            self.branch,
        )
        if len(issues) != 1:
            raise TaskResetError(
                "exactly one closed, valid COMPLETE Issue must identify the production delivery"
            )
        issue = issues[0]
        workflow_state = issue["workflow_state"]
        task_head = str(workflow_state.head_commit)

        merged_prs = _task_pull_requests(
            self.runner, self.source, self.repository, self.branch, "merged"
        )
        matching_prs = [
            item
            for item in merged_prs
            if item.get("headRefOid") == task_head
            and isinstance(item.get("mergeCommit"), dict)
            and item["mergeCommit"].get("oid")
        ]
        if len(matching_prs) != 1:
            raise TaskResetError(
                "exactly one merged pull request must match the completed Issue head"
            )
        merge_commit = str(matching_prs[0]["mergeCommit"]["oid"])
        ancestor = _git(
            self.runner,
            self.source,
            "merge-base",
            "--is-ancestor",
            merge_commit,
            head,
            check=False,
        )
        if ancestor.returncode != 0:
            raise TaskResetError("task merge commit is not an ancestor of current production main")
        pull_request = _find_pull_request(
            self.runner,
            self.source,
            self.repository,
            self.branch,
            merge_commit,
        )
        merge_parent, changed_paths = _validate_pull_request(
            self.runner,
            self.source,
            pull_request,
            branch=self.branch,
            merge_commit=merge_commit,
        )
        _require_task_paths_unchanged_since_merge(
            self.runner,
            self.source,
            merge_commit=merge_commit,
            current_main=head,
            paths=changed_paths,
        )

        remote_branch_oid = _remote_ref_oid(
            self.runner,
            self.source,
            "origin",
            f"refs/heads/{self.branch}",
        )
        if remote_branch_oid is not None and remote_branch_oid != task_head:
            raise TaskResetError("remote task branch moved after completed delivery")
        claims = _relevant_claims(self.source, self.task)
        if claims:
            raise TaskResetError(
                "task/resource claim refs still exist; exact-OID review is required:\n"
                + json.dumps(claims, indent=2, sort_keys=True)
            )
        worktrees = _controller_task_worktrees(
            self.runner, self.source, self.task_id, self.branch
        )
        if any(
            Path(item.get("worktree") or ".").resolve() != self.source
            for item in worktrees
        ):
            raise TaskResetError("task-specific linked worktree exists; reset is refused")

        checkout_facts = None
        if self.checkout.exists():
            if not self.checkout.is_dir():
                raise TaskResetError("canonical task checkout is not a directory")
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
                raise TaskResetError("task checkout is still in use; reset is refused")
        local_branch_oid = _git_text(
            self.runner,
            self.source,
            "rev-parse",
            "--verify",
            f"refs/heads/{self.branch}",
            check=False,
        ) or None
        if local_branch_oid is not None and local_branch_oid != task_head:
            raise TaskResetError("controller local task branch moved after delivery")
        active_state_files = [
            str(path) for path in _state_paths(self.state_root, self.task_id) if path.is_file()
        ]
        return {
            "schema_version": "1.0",
            "operation": "revert_delivered_production_task",
            "task_id": self.task_id,
            "repository": self.repository,
            "archive_repository": self.archive_repository,
            "main_head": head,
            "already_reverted": False,
            "merge_commit": merge_commit,
            "merge_first_parent": merge_parent,
            "task_branch": self.branch,
            "task_head": task_head,
            "pull_request": {
                "number": pull_request["number"],
                "url": pull_request["url"],
            },
            "source_issue": {"number": issue["number"], "url": issue["url"]},
            "archived_issue": None,
            "changed_paths": list(changed_paths),
            "remote_branch_oid": remote_branch_oid,
            "local_branch_oid": local_branch_oid,
            "checkout": checkout_facts,
            "active_state_files": active_state_files,
            "retained_outputs": str(self.state_root / "outputs" / self.task_id),
            "taskgraph_state": "conformant",
        }

    def _create_and_push_revert(self, plan: dict[str, Any]) -> str:
        previous_main = str(plan["main_head"])
        merge_commit = str(plan["merge_commit"])
        merge_parent = str(plan["merge_first_parent"])
        if _remote_ref_oid(self.runner, self.source, "origin", "refs/heads/main") != previous_main:
            raise TaskResetError("origin/main moved after preflight; no revert was created")
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
        if tuple(sorted(staged)) != tuple(sorted(plan["changed_paths"])):
            raise TaskResetError("staged production revert paths differ from the verified merge")
        if _git_text(self.runner, self.source, "diff", "--name-only"):
            raise TaskResetError("production revert produced unstaged changes")
        if _git_text(
            self.runner, self.source, "ls-files", "--others", "--exclude-standard"
        ):
            raise TaskResetError("production revert produced untracked files")
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
            f"Revert delivered {self.task_id} for a fresh run",
            "-m",
            "Preserve production history while removing only the unchanged task delivery.",
            "-m",
            (
                f"{PRODUCTION_RESET_TASK_TRAILER}: {self.task_id}\n"
                f"{PRODUCTION_RESET_MERGE_TRAILER}: {merge_commit}"
            ),
        )
        revert_commit = _git_text(self.runner, self.source, "rev-parse", "HEAD")
        if _commit_parents(self.runner, self.source, revert_commit) != (previous_main,):
            raise TaskResetError("production revert is not additive on the verified current main")
        committed_paths = _changed_paths(
            self.runner, self.source, previous_main, revert_commit
        )
        if tuple(sorted(committed_paths)) != tuple(sorted(plan["changed_paths"])):
            raise TaskResetError("production revert commit changed an unexpected path")
        for path in plan["changed_paths"]:
            if _tree_entry(self.runner, self.source, revert_commit, path) != _tree_entry(
                self.runner, self.source, merge_parent, path
            ):
                raise TaskResetError(
                    f"production revert did not restore the pre-delivery tree entry: {path}"
                )
        if _task_state(self.runner, self.source, self.task_id).get("state") != "not_delivered":
            raise TaskResetError("additive production revert did not restore not_delivered")
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
            raise TaskResetError("pushed production revert could not be verified")
        return revert_commit


class ProductionAbandonedStateCleanup:
    """Archive exact stale cache files only after production is already fresh."""

    def __init__(
        self,
        *,
        source: Path,
        checkout_root: Path,
        task_id: str,
        runner: CommandRunner | None = None,
    ) -> None:
        self.runner = runner or CommandRunner()
        self.source = source.resolve()
        self.checkout_root = checkout_root.resolve()
        self.task_id = validate_task_id(task_id)
        self.state_root = self.checkout_root / ".task-review-agent"
        self.checkout = self.checkout_root / self.task_id
        self.origin = _git_text(self.runner, self.source, "remote", "get-url", "origin")
        self.repository = _repository_from_origin(self.origin)
        self.task = load_committed_task(self.source, self.task_id)
        self.branch = branch_name(self.task_id, self.task.get("title"))

    def preflight(self) -> dict[str, Any]:
        if Path(_git_text(self.runner, self.source, "rev-parse", "--show-toplevel")).resolve() != self.source:
            raise TaskResetError("source is not the exact Git repository root")
        if _git_text(self.runner, self.source, "branch", "--show-current") != "main":
            raise TaskResetError("production controller must be on main")
        if _git_text(
            self.runner,
            self.source,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            raise TaskResetError("production controller is not completely clean")

        metadata = _repo_metadata(self.runner, self.source, self.repository)
        if str(metadata.get("nameWithOwner") or "").casefold() != self.repository.casefold():
            raise TaskResetError("GitHub repository identity changed")
        if metadata.get("isArchived") is True:
            raise TaskResetError("production repository is archived")
        if "rehearsal" in self.repository.casefold():
            raise TaskResetError("use merged-rehearsal mode for rehearsal repositories")

        _git(self.runner, self.source, "fetch", "--prune", "origin", "main")
        head = _git_text(self.runner, self.source, "rev-parse", "HEAD")
        origin_main = _git_text(self.runner, self.source, "rev-parse", "origin/main")
        if head != origin_main:
            raise TaskResetError("production HEAD must exactly equal fetched origin/main")
        task_state = _task_state(self.runner, self.source, self.task_id)
        if task_state.get("state") != "not_delivered":
            raise TaskResetError(
                "production cleanup cannot revert delivered work; TaskGraph must already "
                f"report not_delivered, found {task_state.get('state')!r}"
            )
        _validate_taskgraph(self.runner, self.source)

        open_issues = _managed_task_issues(
            self.runner, self.source, self.repository, self.task_id, "open"
        )
        if open_issues:
            raise TaskResetError(
                "an open task Issue still owns this task; follow the abandoned-task runbook:\n"
                + json.dumps(open_issues, indent=2, sort_keys=True)
            )
        open_pull_requests = _task_pull_requests(
            self.runner, self.source, self.repository, self.branch, "open"
        )
        if open_pull_requests:
            raise TaskResetError(
                "an open task pull request still exists; close it through the abandoned-task runbook"
            )
        remote_branch = _remote_ref_oid(
            self.runner, self.source, "origin", f"refs/heads/{self.branch}"
        )
        if remote_branch is not None:
            raise TaskResetError(
                f"remote task branch still exists at {remote_branch}; exact branch cleanup is required"
            )
        local_branch = _git_text(
            self.runner,
            self.source,
            "rev-parse",
            "--verify",
            f"refs/heads/{self.branch}",
            check=False,
        ) or None
        if local_branch is not None:
            raise TaskResetError(
                f"local task branch still exists at {local_branch}; it was not deleted"
            )
        claims = _relevant_claims(self.source, self.task)
        if claims:
            raise TaskResetError(
                "task/resource claim refs still exist; they require exact-OID stale-claim review:\n"
                + json.dumps(claims, indent=2, sort_keys=True)
            )
        if self.checkout.exists():
            raise TaskResetError(
                f"task checkout still exists at {self.checkout}; inspect it through the full "
                "abandoned-task procedure instead of deleting it as cache"
            )
        active_state = [
            str(path) for path in _state_paths(self.state_root, self.task_id) if path.is_file()
        ]
        closed_issues = _managed_task_issues(
            self.runner, self.source, self.repository, self.task_id, "closed"
        )
        closed_pull_requests = _task_pull_requests(
            self.runner, self.source, self.repository, self.branch, "closed"
        )
        return {
            "schema_version": "1.0",
            "operation": "production_abandoned_state_cleanup",
            "repository": self.repository,
            "task_id": self.task_id,
            "main_head": head,
            "taskgraph_state": "not_delivered",
            "task_branch": self.branch,
            "active_state_files": active_state,
            "closed_issues_retained": [
                {"number": item.get("number"), "url": item.get("url")}
                for item in closed_issues
            ],
            "closed_pull_requests_retained": [
                {"number": item.get("number"), "url": item.get("url")}
                for item in closed_pull_requests
            ],
            "retained_outputs": str(self.state_root / "outputs" / self.task_id),
        }

    def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        report_path = self.state_root / "reset-runs" / self.task_id / f"{timestamp}.json"
        report = {**plan, "status": "applying", "report_path": str(report_path)}
        _create_report(report_path, report)
        try:
            if _git_text(self.runner, self.source, "rev-parse", "HEAD") != plan["main_head"]:
                raise TaskResetError("production HEAD moved after preflight")
            if _git_text(self.runner, self.source, "rev-parse", "origin/main") != plan["main_head"]:
                raise TaskResetError("origin/main moved after preflight")
            current_files = [
                str(path) for path in _state_paths(self.state_root, self.task_id) if path.is_file()
            ]
            if current_files != plan["active_state_files"]:
                raise TaskResetError("active task state changed after preflight")
            archive, names = _archive_state_files(
                self.state_root, self.task_id, timestamp=timestamp
            )
            report.update(
                {
                    "state_archive": str(archive) if archive else None,
                    "archived_state_files": list(names),
                    "status": "state_archived",
                }
            )
            _write_report(report_path, report)
            verification = self.preflight()
            if verification["active_state_files"]:
                raise TaskResetError("active task state remains after archive")
            report.update(
                {
                    "status": "complete",
                    "taskgraph_state": verification["taskgraph_state"],
                    "main_head": verification["main_head"],
                }
            )
            _write_report(report_path, report)
            return report
        except Exception as exc:
            report.update({"status": "stopped", "error": str(exc)})
            _write_report(report_path, report)
            raise


DECOMPOSITION_UNDO_OPERATION = "decomposition_undo_reset"
PUBLISHED_DECOMPOSITION_UNDO_RECOVERY_OPERATION = (
    "published_decomposition_undo_recovery"
)


def _decomposition_children(task: dict[str, Any]) -> tuple[str, ...]:
    """Read the exact child set recorded by the applied parent contract."""

    if str(task.get("decomposition_state") or "") != "decomposed":
        raise TaskResetError(
            "parent contract is not in decomposition_state 'decomposed'; there is no "
            "applied decomposition to undo"
        )
    raw = task.get("decomposition_children")
    if not isinstance(raw, list) or not raw:
        raise TaskResetError(
            "applied parent contract records no decomposition_children; refusing to "
            "guess the child set"
        )
    children: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise TaskResetError("decomposition_children contains a non-string entry")
        children.append(validate_task_id(item))
    if len(set(children)) != len(children):
        raise TaskResetError("decomposition_children contains a duplicate task id")
    return tuple(children)


class DecompositionUndoReset:
    """Undo one exact, unconsumed D1C decomposition and free the parent again.

    The additive inverse commit is produced only by
    ``Pipeline/TaskGraph/undo_graph_delta.py``. This operation adds the
    repository-coordination safety that primitive intentionally does not own:
    exact origin/main identity, per-child consumption discovery, guarded
    fast-forward publication, parent state archival, and a resumable receipt.
    Audit history is never rewritten.
    """

    def __init__(
        self,
        *,
        source: Path,
        checkout_root: Path,
        task_id: str,
        graph_delta: Path,
        runner: CommandRunner | None = None,
    ) -> None:
        from Pipeline.TaskGraph.undo_graph_delta import (
            GraphDeltaUndoError,
            _load_stored_plan,
        )

        self.runner = runner or CommandRunner()
        self.source = source.resolve()
        self.checkout_root = checkout_root.resolve()
        self.task_id = validate_task_id(task_id)
        self.state_root = self.checkout_root / ".task-review-agent"
        self.graph_delta_path = Path(graph_delta).resolve()
        self.origin = _git_text(self.runner, self.source, "remote", "get-url", "origin")
        self.repository = _repository_from_origin(self.origin)
        try:
            self.stored = _load_stored_plan(self.graph_delta_path)
        except GraphDeltaUndoError as exc:
            raise TaskResetError(f"graph-delta authority was refused: {exc}") from exc

    def _stored_parent_task_id(self) -> str:
        payload = self.stored.to_dict()
        summary = payload.get("parent_before_summary")
        if not isinstance(summary, dict):
            raise TaskResetError("stored graph delta omitted its parent summary")
        stored_parent = summary.get("task_id")
        if not isinstance(stored_parent, str) or not stored_parent:
            raise TaskResetError("stored graph delta omitted its parent task id")
        return stored_parent

    def _undo_plan(self, head: str):
        from Pipeline.TaskGraph.undo_graph_delta import (
            GraphDeltaUndoError,
            inspect_graph_delta_undo,
        )

        try:
            return inspect_graph_delta_undo(self.source, self.stored, expected_head=head)
        except GraphDeltaUndoError as exc:
            raise TaskResetError(f"exact D1C undo authority was refused: {exc}") from exc

    def _child_consumption(self, child_id: str) -> list[str]:
        """Return every proven reason this child is already consumed or reserved."""

        reasons: list[str] = []
        child_task = load_committed_task(self.source, child_id)
        branch = branch_name(child_id, child_task.get("title"))

        open_issues = _managed_task_issues(
            self.runner, self.source, self.repository, child_id, "open"
        )
        if open_issues:
            numbers = sorted(str(item.get("number")) for item in open_issues)
            reasons.append(f"open managed Issue(s) {', '.join(numbers)}")

        remote_branch = _remote_ref_oid(
            self.runner, self.source, "origin", f"refs/heads/{branch}"
        )
        if remote_branch is not None:
            reasons.append(f"remote branch refs/heads/{branch} at {remote_branch}")

        local_branch = (
            _git_text(
                self.runner,
                self.source,
                "rev-parse",
                "--verify",
                f"refs/heads/{branch}",
                check=False,
            )
            or None
        )
        if local_branch is not None:
            reasons.append(f"local branch refs/heads/{branch} at {local_branch}")

        checkout = self.checkout_root / child_id
        present = checkout.exists()
        if not present:
            # A dangling junction/symlink still reserves the exact path.
            try:
                present = _path_is_reparse_point(checkout)
            except OSError:
                present = False
        if present:
            reasons.append(f"task checkout {checkout}")

        worktrees = _controller_task_worktrees(
            self.runner, self.source, child_id, branch
        )
        if worktrees:
            reasons.append(f"linked worktree(s) {json.dumps(worktrees, sort_keys=True)}")

        claims = _relevant_claims(self.source, child_task)
        if claims:
            refs = sorted(str(entry.get("ref")) for entry in claims)
            reasons.append(f"claim ref(s) {', '.join(refs)}")

        active_state = [
            str(path)
            for path in _state_paths(self.state_root, child_id)
            if path.is_file()
        ]
        if active_state:
            reasons.append(f"active state file(s) {', '.join(sorted(active_state))}")

        state = _task_state(self.runner, self.source, child_id)
        if str(state.get("state") or "") != "not_delivered":
            reasons.append(f"TaskGraph state {state.get('state')!r}")
        return reasons

    def preflight(self) -> dict[str, Any]:
        if (
            Path(
                _git_text(self.runner, self.source, "rev-parse", "--show-toplevel")
            ).resolve()
            != self.source
        ):
            raise TaskResetError("source is not the exact Git repository root")
        if _git_text(self.runner, self.source, "branch", "--show-current") != "main":
            raise TaskResetError("decomposition undo requires the controller on main")
        if _git_text(
            self.runner,
            self.source,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            raise TaskResetError(
                "controller checkout is not completely clean; decomposition undo never "
                "cleans a dirty checkout"
            )

        stored_parent = self._stored_parent_task_id()
        if stored_parent != self.task_id:
            raise TaskResetError(
                f"stored graph delta belongs to {stored_parent}, not {self.task_id}"
            )

        _git(self.runner, self.source, "fetch", "--prune", "origin", "main")
        head = _git_text(self.runner, self.source, "rev-parse", "HEAD")
        origin_main = _git_text(self.runner, self.source, "rev-parse", "origin/main")
        if head != origin_main:
            raise TaskResetError(
                "controller HEAD must exactly equal fetched origin/main before an undo"
            )
        remote_main = _remote_ref_oid(
            self.runner, self.source, "origin", "refs/heads/main"
        )
        if remote_main != head:
            raise TaskResetError(
                f"origin/main is {remote_main}, not the exact local HEAD {head}"
            )

        undo_plan = self._undo_plan(head)
        if undo_plan.parent_task_id != self.task_id:
            raise TaskResetError(
                f"D1C commit decomposes {undo_plan.parent_task_id}, not {self.task_id}"
            )

        _validate_taskgraph(self.runner, self.source)
        parent_task = load_committed_task(self.source, self.task_id)
        children = _decomposition_children(parent_task)

        blocked: dict[str, list[str]] = {}
        for child_id in children:
            reasons = self._child_consumption(child_id)
            if reasons:
                blocked[child_id] = reasons
        if blocked:
            raise TaskResetError(
                "decomposition children are already consumed or reserved; undo refuses "
                "to strand them:\n" + json.dumps(blocked, indent=2, sort_keys=True)
            )

        parent_state = _task_state(self.runner, self.source, self.task_id)
        parent_active_state = [
            str(path)
            for path in _state_paths(self.state_root, self.task_id)
            if path.is_file()
        ]
        closed_issues = _managed_task_issues(
            self.runner, self.source, self.repository, self.task_id, "closed"
        )
        return {
            "schema_version": "1.0",
            "operation": DECOMPOSITION_UNDO_OPERATION,
            "repository": self.repository,
            "task_id": self.task_id,
            "graph_delta_path": str(self.graph_delta_path),
            "plan_id": undo_plan.plan_id,
            "apply_commit": undo_plan.apply_commit,
            "source_commit": undo_plan.source_commit,
            "apply_tree": undo_plan.apply_tree,
            "source_tree": undo_plan.source_tree,
            "changed_paths": list(undo_plan.changed_paths),
            "source_graph_semantic_hash": undo_plan.source_graph_semantic_hash,
            "proposed_graph_semantic_hash": undo_plan.proposed_graph_semantic_hash,
            "main_head": undo_plan.apply_commit,
            "origin_main": remote_main,
            "decomposition_children": list(children),
            "parent_taskgraph_state": parent_state.get("state"),
            "parent_active_state_files": parent_active_state,
            "closed_issues_retained": [
                {"number": item.get("number"), "url": item.get("url")}
                for item in closed_issues
            ],
            "retained_outputs": str(self.state_root / "outputs" / self.task_id),
            "audit_history_rewritten": False,
        }

    def _verify_undo_commit(self, plan: dict[str, Any], undo_commit: str) -> None:
        from Pipeline.TaskGraph.undo_graph_delta import _graph_hash

        if (
            _git_text(self.runner, self.source, "rev-parse", f"{undo_commit}^")
            != plan["apply_commit"]
        ):
            raise TaskResetError("undo commit parent is not the exact D1C apply commit")
        if (
            _git_text(self.runner, self.source, "rev-parse", f"{undo_commit}^{{tree}}")
            != plan["source_tree"]
        ):
            raise TaskResetError(
                "undo commit tree does not restore the exact pre-D1C source tree"
            )
        if _graph_hash(self.source) != plan["source_graph_semantic_hash"]:
            raise TaskResetError("undo commit did not restore the source TaskGraph")

    def _verify_cleanup_boundary(
        self,
        plan: dict[str, Any],
        undo_commit: str,
        *,
        require_published: bool,
    ) -> None:
        """Prove the exact local and remote state before archiving controller data."""

        if (
            Path(
                _git_text(self.runner, self.source, "rev-parse", "--show-toplevel")
            ).resolve()
            != self.source
        ):
            raise TaskResetError("source is not the exact Git repository root")
        if _git_text(self.runner, self.source, "branch", "--show-current") != "main":
            raise TaskResetError("decomposition undo resume requires the controller on main")
        if _git_text(
            self.runner,
            self.source,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            raise TaskResetError(
                "controller checkout is not completely clean; decomposition undo resume "
                "never cleans a dirty checkout"
            )
        head = _git_text(self.runner, self.source, "rev-parse", "HEAD")
        if head != undo_commit:
            raise TaskResetError(
                f"controller HEAD is {head}, not the receipt undo commit {undo_commit}"
            )
        remote_main = _remote_ref_oid(
            self.runner, self.source, "origin", "refs/heads/main"
        )
        allowed_remote = (
            (undo_commit,)
            if require_published
            else (plan["apply_commit"], undo_commit)
        )
        if remote_main not in allowed_remote:
            raise TaskResetError(
                f"origin/main is {remote_main}, not "
                + (
                    "the published receipt undo commit"
                    if require_published
                    else "the receipt apply or undo commit"
                )
            )
        self._verify_undo_commit(plan, undo_commit)

    def _publish_undo(self, plan: dict[str, Any], undo_commit: str) -> str:
        """Fast-forward origin/main from the exact expected old value."""

        remote_main = _remote_ref_oid(
            self.runner, self.source, "origin", "refs/heads/main"
        )
        if remote_main == undo_commit:
            return "already_published"
        if remote_main != plan["apply_commit"]:
            raise TaskResetError(
                f"origin/main is {remote_main}, not the expected old value "
                f"{plan['apply_commit']}; refusing to publish the undo"
            )
        # Additive fast-forward only. No force, no lease override, no rewind.
        _git(
            self.runner,
            self.source,
            "push",
            "origin",
            f"{undo_commit}:refs/heads/main",
        )
        published = _remote_ref_oid(
            self.runner, self.source, "origin", "refs/heads/main"
        )
        if published != undo_commit:
            raise TaskResetError(
                f"origin/main is {published} after push, expected {undo_commit}"
            )
        return "published"

    def _finish_cleanup(
        self,
        plan: dict[str, Any],
        report: dict[str, Any],
        report_path: Path,
        timestamp: str,
    ) -> dict[str, Any]:
        archive, names = _archive_state_files(
            self.state_root, self.task_id, timestamp=timestamp
        )
        report.update(
            {
                "state_archive": str(archive) if archive else None,
                "archived_state_files": list(names),
                "status": "state_archived",
            }
        )
        _write_report(report_path, report)

        remaining = [
            str(path)
            for path in _state_paths(self.state_root, self.task_id)
            if path.is_file()
        ]
        if remaining:
            raise TaskResetError(
                "active parent decomposition state remains after archive: "
                + ", ".join(sorted(remaining))
            )
        parent_task = load_committed_task(self.source, self.task_id)
        if str(parent_task.get("decomposition_state") or "") == "decomposed":
            raise TaskResetError("parent contract is still marked decomposed")
        if parent_task.get("decomposition_children"):
            raise TaskResetError("parent contract still records decomposition children")
        surviving = [
            child_id
            for child_id in plan["decomposition_children"]
            if (self.source / "Tasks" / f"{child_id}.yaml").exists()
        ]
        if surviving:
            raise TaskResetError(
                "child contracts still exist after undo: " + ", ".join(surviving)
            )
        _validate_taskgraph(self.runner, self.source)
        report.update(
            {
                "status": "complete",
                "parent_decomposition_state": parent_task.get("decomposition_state"),
                "parent_eligible_for_fresh_decomposition": True,
                "origin_main": _remote_ref_oid(
                    self.runner, self.source, "origin", "refs/heads/main"
                ),
            }
        )
        _write_report(report_path, report)
        return report

    def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        from Pipeline.TaskGraph.undo_graph_delta import (
            GraphDeltaUndoError,
            undo_graph_delta,
        )

        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        report_path = (
            self.state_root
            / "reset-runs"
            / self.task_id
            / f"{timestamp}-undo-decomposition.json"
        )
        report = {**plan, "status": "applying", "report_path": str(report_path)}
        _create_report(report_path, report)
        try:
            verification = self.preflight()
            for field in (
                "plan_id",
                "apply_commit",
                "source_commit",
                "source_tree",
                "source_graph_semantic_hash",
                "decomposition_children",
            ):
                if verification[field] != plan[field]:
                    raise TaskResetError(
                        f"{field} changed between preflight and apply"
                    )
            remote_main = _remote_ref_oid(
                self.runner, self.source, "origin", "refs/heads/main"
            )
            if remote_main != plan["apply_commit"]:
                raise TaskResetError(
                    f"origin/main moved to {remote_main} after preflight"
                )
            try:
                result = undo_graph_delta(
                    self.source,
                    self.stored,
                    expected_head=plan["apply_commit"],
                )
            except GraphDeltaUndoError as exc:
                raise TaskResetError(f"exact D1C undo failed: {exc}") from exc
            self._verify_undo_commit(plan, result.undo_commit)
            report.update(
                {
                    "undo_commit": result.undo_commit,
                    "committed_paths": list(result.committed_paths),
                    "status": "undo_committed",
                }
            )
            _write_report(report_path, report)

            report["publish"] = self._publish_undo(plan, result.undo_commit)
            report["status"] = "undo_published"
            _write_report(report_path, report)

            self._verify_cleanup_boundary(
                plan, result.undo_commit, require_published=True
            )
            return self._finish_cleanup(plan, report, report_path, timestamp)
        except Exception as exc:
            report.update({"status": "stopped", "error": str(exc)})
            _write_report(report_path, report)
            raise

    def resume(self, report_path: Path) -> dict[str, Any]:
        """Finish cleanup for a receipt whose undo commit already exists.

        This never creates a second undo commit. It requires the receipt's exact
        identities and reuses the recorded additive commit.
        """

        path = Path(report_path).resolve()
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TaskResetError(f"reset receipt is not readable UTF-8 JSON: {path}") from exc
        if not isinstance(report, dict):
            raise TaskResetError("reset receipt must contain one JSON object")
        if report.get("operation") != DECOMPOSITION_UNDO_OPERATION:
            raise TaskResetError("reset receipt is not a decomposition-undo receipt")
        if report.get("task_id") != self.task_id:
            raise TaskResetError("reset receipt belongs to a different task")
        if report.get("repository") != self.repository:
            raise TaskResetError("reset receipt belongs to a different repository")
        if report.get("plan_id") != self.stored.to_dict().get("plan_id"):
            raise TaskResetError("reset receipt names a different decomposition plan")
        undo_commit = report.get("undo_commit")
        if (
            not isinstance(undo_commit, str)
            or re.fullmatch(r"[0-9a-f]{40}", undo_commit) is None
        ):
            raise TaskResetError(
                "reset receipt records no undo commit; rerun the ordinary "
                "--undo-decomposition --apply preflight instead of resuming"
            )
        if report.get("status") == "complete":
            return report
        if not _git_text(
            self.runner,
            self.source,
            "rev-parse",
            "--verify",
            f"{undo_commit}^{{commit}}",
            check=False,
        ):
            raise TaskResetError(
                f"receipt undo commit {undo_commit} does not exist in this repository"
            )
        for field in ("apply_commit", "source_tree"):
            value = report.get(field)
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
                raise TaskResetError(f"reset receipt has an invalid {field}")
        graph_hash = report.get("source_graph_semantic_hash")
        if (
            not isinstance(graph_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", graph_hash) is None
        ):
            raise TaskResetError("reset receipt has an invalid source_graph_semantic_hash")
        children = report.get("decomposition_children")
        if not isinstance(children, list) or any(
            not isinstance(child, str) for child in children
        ):
            raise TaskResetError("reset receipt has an invalid decomposition_children set")
        self._verify_cleanup_boundary(
            report, undo_commit, require_published=False
        )
        report["publish"] = self._publish_undo(report, undo_commit)
        report["status"] = "undo_published"
        report["resumed"] = True
        _write_report(path, report)
        self._verify_cleanup_boundary(report, undo_commit, require_published=True)
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        return self._finish_cleanup(report, report, path, timestamp)


class PublishedDecompositionUndoRecovery(DecompositionUndoReset):
    """Retire stale coordination after an exact undo already reached main.

    This is deliberately separate from :class:`DecompositionUndoReset`.  It
    never creates or publishes a Git commit and it does not make the ordinary
    exact-HEAD undo accept later history.  The completed decomposition Issue is
    the authority for the historical apply commit; the operator separately
    confirms the exact additive undo commit before cleanup can begin.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.checkout = self.checkout_root / self.task_id
        self.task = load_committed_task(self.source, self.task_id)
        self.branch = branch_name(self.task_id, self.task.get("title"))

    @staticmethod
    def _issue_labels(issue: dict[str, Any]) -> set[str]:
        values: set[str] = set()
        for item in issue.get("labels") or []:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                values.add(item["name"])
            elif isinstance(item, str):
                values.add(item)
        return values

    def _issue_view(self, number: int) -> dict[str, Any]:
        value = _json_command(
            self.runner,
            (
                "gh",
                "issue",
                "view",
                str(number),
                "--repo",
                self.repository,
                "--json",
                "number,state,url,body,labels,comments",
            ),
            cwd=self.source,
        )
        if not isinstance(value, dict) or value.get("number") != number:
            raise TaskResetError("completed decomposition Issue view was invalid")
        return value

    def _validated_completed_issue(
        self,
        issue: dict[str, Any],
        *,
        expected_github_state: str,
    ) -> tuple[Any, tuple[Any, ...], dict[str, Any]]:
        number = issue.get("number")
        if type(number) is not int:
            raise TaskResetError("completed decomposition Issue number is invalid")
        exact = self._issue_view(number)
        if exact.get("state") != expected_github_state:
            raise TaskResetError(
                "completed decomposition Issue GitHub state changed"
            )
        body = exact.get("body")
        comments = exact.get("comments")
        if not isinstance(body, str) or not isinstance(comments, list):
            raise TaskResetError("completed decomposition Issue content is invalid")
        state = parse_state(body)
        if state is None or state.task_id != self.task_id:
            raise TaskResetError(
                "completed decomposition Issue does not contain the exact task state"
            )
        if (
            state.state is not WorkflowState.COMPLETE
            or state.phase is not WorkflowPhase.DECOMPOSITION_APPLY
            or state.current_actor is not WorkflowActor.NONE
        ):
            raise TaskResetError(
                "Issue is not an exact completed decomposition_apply workflow"
            )
        state_labels = self._issue_labels(exact) & ALL_STATE_LABELS
        if state_labels != {STATE_LABELS[WorkflowState.COMPLETE.value]}:
            raise TaskResetError(
                "completed decomposition Issue does not have exactly the complete state label"
            )
        if state.branch != self.branch or state.checkout_path != str(self.checkout):
            raise TaskResetError(
                "completed decomposition Issue branch or checkout identity differs"
            )
        if state.task_contract_sha256 != self.task.get("task_contract_sha256"):
            raise TaskResetError(
                "completed decomposition Issue task-contract identity differs"
            )
        events = tuple(parse_events(comments))
        validate_event_chain(state, events)
        completed = events[-1] if events else None
        if (
            completed is None
            or completed.event_type is not WorkflowEventType.COMPLETED
            or completed.actor_type is not WorkflowActor.AGENT
            or completed.to_phase is not WorkflowPhase.DECOMPOSITION_APPLY
            or completed.to_state is not WorkflowState.COMPLETE
        ):
            raise TaskResetError(
                "completed decomposition Issue has no exact terminal application event"
            )
        details = dict(completed.details)
        if details.get("work_type") != "decomposition":
            raise TaskResetError(
                "completed decomposition Issue terminal event has the wrong work type"
            )
        return state, events, details

    @staticmethod
    def _commit_identity_fields(
        runner: CommandRunner, source: Path, commit: str
    ) -> tuple[str, str, str, str]:
        value = _git_text(
            runner,
            source,
            "show",
            "-s",
            "--format=%an%x00%ae%x00%cn%x00%ce",
            commit,
        ).split("\0")
        if len(value) != 4:
            raise TaskResetError("Git commit identity record was invalid")
        return tuple(value)  # type: ignore[return-value]

    def _require_automation_commit(self, commit: str, *, label: str) -> None:
        name, email = validated_agent_git_identity()
        actual = self._commit_identity_fields(self.runner, self.source, commit)
        expected = (name, email, name, email)
        if actual != expected:
            raise TaskResetError(
                f"{label} was not authored and committed by the approved automation identity"
            )

    def _proposed_children(self) -> tuple[dict[str, Any], ...]:
        payload = self.stored.to_dict()
        children = payload.get("proposed_child_contracts")
        after = payload.get("parent_after_summary")
        expected_ids = (
            after.get("decomposition_children") if isinstance(after, dict) else None
        )
        if (
            not isinstance(children, list)
            or not children
            or any(not isinstance(item, dict) for item in children)
            or not isinstance(expected_ids, list)
        ):
            raise TaskResetError("stored graph delta has an invalid child set")
        ids = [item.get("id") for item in children]
        if ids != expected_ids or any(not isinstance(item, str) for item in ids):
            raise TaskResetError(
                "stored graph delta child contracts differ from the parent child set"
            )
        return tuple(dict(item) for item in children)

    @staticmethod
    def _repo_paths_for_child(child: dict[str, Any]) -> tuple[str, ...]:
        values: set[str] = set()
        for resource in child.get("exclusive_resources") or []:
            if not isinstance(resource, str):
                continue
            for prefix in ("repo-file:", "unity-scene:", "unity-prefab:"):
                if resource.startswith(prefix):
                    values.add(resource.removeprefix(prefix))
                    break
        provenance = child.get("provenance")
        for path in (
            provenance.get("expected_paths", [])
            if isinstance(provenance, dict)
            else []
        ):
            if isinstance(path, str):
                values.add(path)
        safe: list[str] = []
        for value in values:
            candidate = Path(value)
            if (
                not value
                or candidate.is_absolute()
                or candidate.as_posix() != value
                or ".." in candidate.parts
            ):
                raise TaskResetError(
                    f"stored child contract contains an unsafe repository path: {value!r}"
                )
            safe.append(value)
        return tuple(sorted(safe, key=str.casefold))

    def _historical_plan(
        self,
        current_head: str,
        completed_details: dict[str, Any],
        children: tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        from Pipeline.TaskGraph.undo_graph_delta import _commit_graph_hash

        payload = self.stored.to_dict()
        plan_id = payload.get("plan_id")
        apply_commit = completed_details.get("applied_commit")
        if completed_details.get("graph_delta_plan_id") != plan_id:
            raise TaskResetError(
                "completed decomposition Issue plan differs from graph-delta authority"
            )
        if (
            not isinstance(apply_commit, str)
            or re.fullmatch(r"[0-9a-f]{40}", apply_commit) is None
        ):
            raise TaskResetError(
                "completed decomposition Issue has an invalid applied commit"
            )
        if not _git_text(
            self.runner,
            self.source,
            "rev-parse",
            "--verify",
            f"{apply_commit}^{{commit}}",
            check=False,
        ):
            raise TaskResetError("completed decomposition apply commit is unavailable")
        parents = _commit_parents(self.runner, self.source, apply_commit)
        if len(parents) != 1:
            raise TaskResetError("D1C apply commit must have exactly one parent")
        source_commit = parents[0]
        expected_apply_subject = (
            f"taskgraph: apply {self.task_id} decomposition {plan_id}"
        )
        if (
            _git_text(
                self.runner,
                self.source,
                "show",
                "-s",
                "--format=%s",
                apply_commit,
            )
            != expected_apply_subject
        ):
            raise TaskResetError("completed Issue does not identify the exact D1C commit")
        self._require_automation_commit(apply_commit, label="D1C apply commit")
        if _commit_graph_hash(self.source, source_commit) != payload.get(
            "source_graph_semantic_hash"
        ):
            raise TaskResetError(
                "D1C apply parent differs from the reviewed source graph"
            )
        if _commit_graph_hash(self.source, apply_commit) != payload.get(
            "proposed_graph_semantic_hash"
        ):
            raise TaskResetError(
                "D1C apply commit differs from the reviewed proposed graph"
            )
        changed_paths = tuple(
            sorted(
                _changed_paths(self.runner, self.source, source_commit, apply_commit),
                key=str.casefold,
            )
        )
        if not changed_paths:
            raise TaskResetError("D1C apply commit changed no paths")

        first_parent = _git_text(
            self.runner, self.source, "rev-list", "--first-parent", current_head
        ).splitlines()
        if apply_commit not in first_parent:
            raise TaskResetError(
                "completed D1C apply commit is not in current main's first-parent history"
            )
        expected_undo_subject = (
            f"taskgraph: undo {self.task_id} decomposition {plan_id}"
        )
        undo_candidates = [
            commit
            for commit in first_parent
            if _commit_parents(self.runner, self.source, commit) == (apply_commit,)
            and _git_text(
                self.runner,
                self.source,
                "show",
                "-s",
                "--format=%s",
                commit,
            )
            == expected_undo_subject
        ]
        if len(undo_candidates) != 1:
            raise TaskResetError(
                "expected exactly one immediate additive undo commit in current main history"
            )
        undo_commit = undo_candidates[0]
        self._require_automation_commit(undo_commit, label="decomposition undo commit")
        source_tree = _git_text(
            self.runner, self.source, "rev-parse", f"{source_commit}^{{tree}}"
        )
        undo_tree = _git_text(
            self.runner, self.source, "rev-parse", f"{undo_commit}^{{tree}}"
        )
        if undo_tree != source_tree:
            raise TaskResetError(
                "published decomposition undo tree does not equal the D1C source tree"
            )
        undo_paths = tuple(
            sorted(
                _changed_paths(self.runner, self.source, apply_commit, undo_commit),
                key=str.casefold,
            )
        )
        if undo_paths != changed_paths:
            raise TaskResetError(
                "published decomposition undo path set differs from the D1C apply"
            )
        if _commit_graph_hash(self.source, undo_commit) != payload.get(
            "source_graph_semantic_hash"
        ):
            raise TaskResetError(
                "published decomposition undo does not restore the reviewed source graph"
            )

        protected_exact = set(changed_paths)
        protected_prefixes: set[str] = set()
        for child in children:
            child_id = str(child["id"])
            protected_exact.update(self._repo_paths_for_child(child))
            protected_prefixes.add(f"Pipeline/TaskGraph/evidence/{child_id}/")
        later_commits = tuple(
            _git_text(
                self.runner,
                self.source,
                "rev-list",
                "--ancestry-path",
                current_head,
                f"^{undo_commit}",
            ).splitlines()
        )
        touched: dict[str, list[str]] = {}
        for commit in later_commits:
            commit_parents = _commit_parents(self.runner, self.source, commit)
            if not commit_parents:
                raise TaskResetError("later main history contains a parentless commit")
            paths = tuple(
                line
                for line in _git_text(
                    self.runner,
                    self.source,
                    "diff",
                    "--name-only",
                    "--no-renames",
                    commit_parents[0],
                    commit,
                ).splitlines()
                if line
            )
            protected = [
                path
                for path in paths
                if path in protected_exact
                or any(path.startswith(prefix) for prefix in protected_prefixes)
            ]
            if protected:
                touched[commit] = sorted(protected, key=str.casefold)
        if touched:
            raise TaskResetError(
                "later history touched decomposition or child-owned paths; recovery refuses:\n"
                + json.dumps(touched, indent=2, sort_keys=True)
            )
        return {
            "plan_id": plan_id,
            "apply_commit": apply_commit,
            "source_commit": source_commit,
            "source_tree": source_tree,
            "apply_tree": _git_text(
                self.runner, self.source, "rev-parse", f"{apply_commit}^{{tree}}"
            ),
            "undo_commit": undo_commit,
            "undo_tree": undo_tree,
            "changed_paths": list(changed_paths),
            "source_graph_semantic_hash": payload.get("source_graph_semantic_hash"),
            "proposed_graph_semantic_hash": payload.get(
                "proposed_graph_semantic_hash"
            ),
            "later_commits": list(later_commits),
            "protected_child_paths": sorted(
                protected_exact - set(changed_paths), key=str.casefold
            ),
            "protected_evidence_prefixes": sorted(
                protected_prefixes, key=str.casefold
            ),
        }

    def _child_consumption_from_stored(
        self,
        child: dict[str, Any],
        *,
        source_commit: str,
    ) -> list[str]:
        child_id = validate_task_id(str(child.get("id") or ""))
        reasons: list[str] = []
        issues = _managed_task_issues(
            self.runner, self.source, self.repository, child_id, "all"
        )
        if issues:
            reasons.append(
                "managed Issue(s) "
                + ", ".join(sorted(str(item.get("number")) for item in issues))
            )
        child_branch = branch_name(child_id, child.get("title"))
        remote = _remote_ref_oid(
            self.runner, self.source, "origin", f"refs/heads/{child_branch}"
        )
        if remote:
            reasons.append(f"remote branch refs/heads/{child_branch} at {remote}")
        local = _git_text(
            self.runner,
            self.source,
            "rev-parse",
            "--verify",
            f"refs/heads/{child_branch}",
            check=False,
        )
        if local:
            reasons.append(f"local branch refs/heads/{child_branch} at {local}")
        child_checkout = self.checkout_root / child_id
        child_checkout_present = child_checkout.exists()
        if not child_checkout_present:
            try:
                child_checkout_present = _path_is_reparse_point(child_checkout)
            except OSError:
                child_checkout_present = False
        if child_checkout_present:
            reasons.append(f"task checkout {child_checkout}")
        worktrees = _controller_task_worktrees(
            self.runner, self.source, child_id, child_branch
        )
        if worktrees:
            reasons.append(f"linked worktree(s) {json.dumps(worktrees, sort_keys=True)}")
        claims = _relevant_claims(self.source, child)
        if claims:
            reasons.append(
                "claim ref(s) "
                + ", ".join(sorted(str(entry.get("ref")) for entry in claims))
            )
        state_files = [
            str(path)
            for path in _state_paths(self.state_root, child_id)
            if path.is_file()
        ]
        if state_files:
            reasons.append("active state file(s) " + ", ".join(state_files))
        if (self.source / "Tasks" / f"{child_id}.yaml").exists():
            reasons.append("current TaskGraph child contract")
        for path in self._repo_paths_for_child(child):
            if _tree_entry(self.runner, self.source, "HEAD", path) != _tree_entry(
                self.runner, self.source, source_commit, path
            ):
                reasons.append(f"current child-owned path changed from baseline: {path}")
        evidence = self.source / "Pipeline" / "TaskGraph" / "evidence" / child_id
        if evidence.exists():
            reasons.append(f"current child evidence {evidence}")
        return reasons

    def preflight(self) -> dict[str, Any]:
        if (
            Path(
                _git_text(self.runner, self.source, "rev-parse", "--show-toplevel")
            ).resolve()
            != self.source
        ):
            raise TaskResetError("source is not the exact Git repository root")
        if _git_text(self.runner, self.source, "branch", "--show-current") != "main":
            raise TaskResetError("published-undo recovery requires the controller on main")
        if _git_text(
            self.runner,
            self.source,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            raise TaskResetError(
                "controller checkout is not completely clean; recovery never cleans it"
            )
        metadata = _repo_metadata(self.runner, self.source, self.repository)
        _require_private_rehearsal_repository(metadata, self.repository)
        _git(self.runner, self.source, "fetch", "--prune", "origin", "main")
        head = _git_text(self.runner, self.source, "rev-parse", "HEAD")
        if _git_text(self.runner, self.source, "rev-parse", "origin/main") != head:
            raise TaskResetError("controller HEAD must equal fetched origin/main")
        if _remote_ref_oid(
            self.runner, self.source, "origin", "refs/heads/main"
        ) != head:
            raise TaskResetError("remote main differs from the exact local HEAD")
        if self._stored_parent_task_id() != self.task_id:
            raise TaskResetError("stored graph delta belongs to a different parent")

        issues = _managed_task_issues(
            self.runner, self.source, self.repository, self.task_id, "open"
        )
        if len(issues) != 1:
            raise TaskResetError(
                "exactly one open completed decomposition Issue must authorize recovery"
            )
        state, _, completed_details = self._validated_completed_issue(
            issues[0], expected_github_state="OPEN"
        )
        children = self._proposed_children()
        history = self._historical_plan(head, completed_details, children)
        if state.head_commit != history["source_commit"]:
            raise TaskResetError(
                "completed decomposition Issue baseline differs from the D1C source commit"
            )
        if state.human_handoff_commit != history["source_commit"]:
            raise TaskResetError(
                "completed decomposition Issue handoff differs from the D1C source commit"
            )

        _validate_taskgraph(self.runner, self.source)
        current_parent = load_committed_task(self.source, self.task_id)
        if (
            current_parent.get("decomposition_state") == "decomposed"
            or current_parent.get("decomposition_children")
            or current_parent.get("execution_scope") != "needs_execution_decomposition"
        ):
            raise TaskResetError(
                "current parent contract is not restored for fresh decomposition"
            )
        blocked: dict[str, list[str]] = {}
        for child in children:
            reasons = self._child_consumption_from_stored(
                child,
                source_commit=str(history["source_commit"]),
            )
            if reasons:
                blocked[str(child["id"])] = reasons
        if blocked:
            raise TaskResetError(
                "decomposition children were consumed or remain reserved; recovery refuses:\n"
                + json.dumps(blocked, indent=2, sort_keys=True)
            )
        if _relevant_claims(self.source, current_parent):
            raise TaskResetError("parent task/resource claim refs still exist")
        if _remote_ref_oid(
            self.runner, self.source, "origin", f"refs/heads/{self.branch}"
        ) is not None:
            raise TaskResetError("parent decomposition branch still exists remotely")
        if _task_pull_requests(
            self.runner, self.source, self.repository, self.branch, "open"
        ):
            raise TaskResetError("parent decomposition branch has an open pull request")
        parent_worktrees = _controller_task_worktrees(
            self.runner, self.source, self.task_id, self.branch
        )
        if parent_worktrees:
            raise TaskResetError(
                "parent task-specific linked worktree exists; recovery refuses:\n"
                + json.dumps(parent_worktrees, indent=2, sort_keys=True)
            )

        checkout_facts = None
        manifest = None
        if self.checkout.exists():
            manifest = _validate_branchless_checkout_manifest(
                self.state_root / f"{self.task_id}.json",
                task=current_parent,
                checkout=self.checkout,
                branch=self.branch,
                source_head=str(history["source_commit"]),
                source_tree=str(history["source_tree"]),
                origin=self.origin,
            )
            checkout_facts = _inspect_checkout(
                self.runner,
                self.checkout,
                expected_root=self.checkout_root,
                expected_origin=self.origin,
                expected_branch=self.branch,
                expected_head=str(history["source_commit"]),
                remote_branch_oid=None,
            )
            processes = _processes_using_checkout(
                self.runner, self.source, self.checkout
            )
            containers = _containers_using_checkout(
                self.runner, self.source, self.checkout
            )
            if processes or containers:
                raise TaskResetError(
                    "parent decomposition checkout is still in use:\n"
                    + json.dumps(
                        {"processes": processes, "containers": containers},
                        indent=2,
                        sort_keys=True,
                    )
                )
        elif (self.state_root / f"{self.task_id}.json").is_file():
            raise TaskResetError(
                "parent checkout manifest exists but the exact checkout is absent"
            )
        local_branch = _git_text(
            self.runner,
            self.source,
            "rev-parse",
            "--verify",
            f"refs/heads/{self.branch}",
            check=False,
        ) or None
        if local_branch is not None and local_branch != history["source_commit"]:
            raise TaskResetError("parent local branch differs from the source baseline")
        active_state = [
            str(path)
            for path in _state_paths(self.state_root, self.task_id)
            if path.is_file()
        ]
        active_state_sha256 = {
            Path(value).name: _file_sha256(Path(value)) for value in active_state
        }
        task_state = _task_state(self.runner, self.source, self.task_id)
        if not _abandoned_rehearsal_state_is_undelivered(
            current_parent, task_state.get("state")
        ):
            raise TaskResetError(
                "restored parent is not eligible for fresh decomposition"
            )
        return {
            "schema_version": "1.0",
            "operation": PUBLISHED_DECOMPOSITION_UNDO_RECOVERY_OPERATION,
            "repository": self.repository,
            "task_id": self.task_id,
            "graph_delta_path": str(self.graph_delta_path),
            "main_head": head,
            **history,
            "decomposition_children": [str(item["id"]) for item in children],
            "issue": {
                "number": issues[0]["number"],
                "url": issues[0].get("url"),
            },
            "checkout": checkout_facts,
            "checkout_manifest_sha256": (
                manifest.get("manifest_sha256") if isinstance(manifest, dict) else None
            ),
            "local_branch_oid": local_branch,
            "active_state_files": active_state,
            "active_state_file_sha256": active_state_sha256,
            "retained_outputs": str(self.state_root / "outputs" / self.task_id),
            "taskgraph_state": task_state.get("state"),
            "git_commit_created": False,
            "git_push_required": False,
            "audit_history_rewritten": False,
        }

    def _recovery_marker(self, plan: dict[str, Any]) -> str:
        return (
            "<!-- nsc-published-decomposition-undo-recovery: "
            f"{plan['undo_commit']} -->"
        )

    def _recovery_comment(self, plan: dict[str, Any]) -> str:
        marker = self._recovery_marker(plan)
        return (
            "## Published decomposition undo recovered\n\n"
            f"The exact `{self.task_id}` D1C application `{plan['apply_commit']}` "
            f"for `{plan['plan_id']}` was already additively undone by "
            f"`{plan['undo_commit']}`. The undo is in current `main` history and "
            "no later commit touched the decomposition or child-owned paths.\n\n"
            "This Issue is being closed to retire stale coordination only. Its "
            "hashed workflow state and audit comments are retained unchanged; no "
            "task delivery or child work is being erased.\n\n"
            + marker
        )

    def _close_exact_issue(self, report: dict[str, Any]) -> None:
        number = int(report["issue"]["number"])
        exact = self._issue_view(number)
        marker = self._recovery_marker(report)
        if exact.get("state") == "CLOSED":
            self._validated_completed_issue(
                exact, expected_github_state="CLOSED"
            )
            comments = exact.get("comments") or []
            if not any(
                isinstance(item, dict) and marker in str(item.get("body") or "")
                for item in comments
            ):
                raise TaskResetError(
                    "closed parent Issue lacks the exact recovery audit marker"
                )
            return
        self._validated_completed_issue(exact, expected_github_state="OPEN")
        body = self._recovery_comment(report)
        comments = exact.get("comments") or []
        if not any(
            isinstance(item, dict) and marker in str(item.get("body") or "")
            for item in comments
        ):
            self.runner.run(
                (
                    "gh",
                    "issue",
                    "comment",
                    str(number),
                    "--repo",
                    self.repository,
                    "--body",
                    body,
                ),
                cwd=self.source,
            )
        self.runner.run(
            (
                "gh",
                "issue",
                "close",
                str(number),
                "--repo",
                self.repository,
            ),
            cwd=self.source,
        )
        _wait_for_managed_issue_close(
            self.runner, self.source, self.repository, self.task_id, number
        )

    def _remove_exact_checkout(self, report: dict[str, Any]) -> None:
        checkout = report.get("checkout")
        if self.checkout.exists():
            if not isinstance(checkout, dict):
                raise TaskResetError("recovery receipt did not inventory the checkout")
            _validate_branchless_checkout_manifest(
                self.state_root / f"{self.task_id}.json",
                task=load_committed_task(self.source, self.task_id),
                checkout=self.checkout,
                branch=self.branch,
                source_head=str(report["source_commit"]),
                source_tree=str(report["source_tree"]),
                origin=self.origin,
            )
        AbandonedRehearsalTaskReset._remove_checkout_and_local_branch(
            self,
            {
                "checkout_head": report["source_commit"],
                "task_head": report["source_commit"],
            },
        )

    def _archive_recovery_state(self, report: dict[str, Any]) -> tuple[Path | None, tuple[str, ...]]:
        names = tuple(
            sorted(Path(value).name for value in report.get("active_state_files") or [])
        )
        if not names:
            return None, ()
        archive = Path(str(report["planned_state_archive"]))
        if archive.resolve().parent != (
            self.state_root / "archive" / self.task_id
        ).resolve():
            raise TaskResetError("recovery receipt state archive path escaped its task")
        archive.mkdir(parents=True, exist_ok=True)
        active_by_name = {
            path.name: path
            for path in _state_paths(self.state_root, self.task_id)
            if path.is_file()
        }
        archived_by_name = {
            path.name: path for path in archive.iterdir() if path.is_file()
        }
        if set(active_by_name) | set(archived_by_name) != set(names):
            raise TaskResetError(
                "active/archived parent state differs from the recovery receipt"
            )
        if set(active_by_name) & set(archived_by_name):
            raise TaskResetError("parent state exists in both active and archive locations")
        expected_hashes = report.get("active_state_file_sha256")
        if not isinstance(expected_hashes, dict) or {
            **{name: _file_sha256(path) for name, path in active_by_name.items()},
            **{name: _file_sha256(path) for name, path in archived_by_name.items()},
        } != expected_hashes:
            raise TaskResetError("parent state file content changed after recovery preflight")
        for name, source in active_by_name.items():
            destination = archive / name
            if destination.exists():
                raise TaskResetError(f"state archive destination exists: {destination}")
            source.replace(destination)
        archived = tuple(sorted(path.name for path in archive.iterdir() if path.is_file()))
        if archived != names:
            raise TaskResetError("recovery state archive filename verification failed")
        return archive, archived

    def _verify_recovery_main(self, report: dict[str, Any]) -> None:
        if _git_text(self.runner, self.source, "branch", "--show-current") != "main":
            raise TaskResetError("published-undo recovery requires main")
        if _git_text(
            self.runner,
            self.source,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            raise TaskResetError("controller became dirty during recovery")
        _git(self.runner, self.source, "fetch", "--prune", "origin", "main")
        head = _git_text(self.runner, self.source, "rev-parse", "HEAD")
        remote = _git_text(self.runner, self.source, "rev-parse", "origin/main")
        if head != report.get("main_head") or remote != head:
            raise TaskResetError("current main moved after the recovery preflight")

    def _revalidate_recovery_authority(self, report: dict[str, Any]) -> None:
        """Re-prove immutable authority and non-consumption before each cleanup step."""

        self._verify_recovery_main(report)
        metadata = _repo_metadata(self.runner, self.source, self.repository)
        _require_private_rehearsal_repository(metadata, self.repository)
        if self._stored_parent_task_id() != self.task_id:
            raise TaskResetError("stored graph delta belongs to a different parent")

        issue_record = report.get("issue")
        if not isinstance(issue_record, dict):
            raise TaskResetError("recovery receipt has an invalid Issue record")
        number = issue_record.get("number")
        if type(number) is not int or number < 1:
            raise TaskResetError("recovery receipt has an invalid Issue identity")
        exact_issue = self._issue_view(number)
        github_state = str(exact_issue.get("state") or "").upper()
        if github_state not in {"OPEN", "CLOSED"}:
            raise TaskResetError("recovery Issue state was not observable")
        state, _, completed_details = self._validated_completed_issue(
            exact_issue,
            expected_github_state=github_state,
        )
        open_issues = _managed_task_issues(
            self.runner, self.source, self.repository, self.task_id, "open"
        )
        open_numbers = {
            item.get("number") for item in open_issues if isinstance(item, dict)
        }
        expected_open_numbers = {number} if github_state == "OPEN" else set()
        if open_numbers != expected_open_numbers:
            raise TaskResetError(
                "parent managed Issue set changed after the recovery preflight"
            )
        if github_state == "CLOSED":
            marker = self._recovery_marker(report)
            comments = exact_issue.get("comments") or []
            if not any(
                isinstance(item, dict) and marker in str(item.get("body") or "")
                for item in comments
            ):
                raise TaskResetError(
                    "closed parent Issue lacks the exact recovery audit marker"
                )

        children = self._proposed_children()
        history = self._historical_plan(
            str(report["main_head"]), completed_details, children
        )
        for field in (
            "plan_id",
            "apply_commit",
            "source_commit",
            "source_tree",
            "apply_tree",
            "undo_commit",
            "undo_tree",
            "changed_paths",
            "source_graph_semantic_hash",
            "proposed_graph_semantic_hash",
            "later_commits",
            "protected_child_paths",
            "protected_evidence_prefixes",
        ):
            if report.get(field) != history.get(field):
                raise TaskResetError(
                    f"recovery receipt {field} differs from current graph/history authority"
                )
        expected_children = [str(item["id"]) for item in children]
        if report.get("decomposition_children") != expected_children:
            raise TaskResetError(
                "recovery receipt child set differs from graph-delta authority"
            )
        if state.head_commit != history["source_commit"]:
            raise TaskResetError(
                "completed decomposition Issue baseline differs from the D1C source commit"
            )
        if state.human_handoff_commit != history["source_commit"]:
            raise TaskResetError(
                "completed decomposition Issue handoff differs from the D1C source commit"
            )

        _validate_taskgraph(self.runner, self.source)
        parent = load_committed_task(self.source, self.task_id)
        if (
            parent.get("decomposition_state") == "decomposed"
            or parent.get("decomposition_children")
            or parent.get("execution_scope") != "needs_execution_decomposition"
        ):
            raise TaskResetError(
                "current parent contract is not restored for fresh decomposition"
            )
        blocked: dict[str, list[str]] = {}
        for child in children:
            reasons = self._child_consumption_from_stored(
                child,
                source_commit=str(history["source_commit"]),
            )
            if reasons:
                blocked[str(child["id"])] = reasons
        if blocked:
            raise TaskResetError(
                "decomposition children were consumed or remain reserved; recovery refuses:\n"
                + json.dumps(blocked, indent=2, sort_keys=True)
            )
        if _relevant_claims(self.source, parent):
            raise TaskResetError("parent task/resource claim refs still exist")
        if _remote_ref_oid(
            self.runner, self.source, "origin", f"refs/heads/{self.branch}"
        ) is not None:
            raise TaskResetError("parent decomposition branch appeared remotely")
        if _task_pull_requests(
            self.runner, self.source, self.repository, self.branch, "open"
        ):
            raise TaskResetError("parent decomposition branch has an open pull request")
        parent_worktrees = _controller_task_worktrees(
            self.runner, self.source, self.task_id, self.branch
        )
        if parent_worktrees:
            raise TaskResetError(
                "parent task-specific linked worktree exists; recovery refuses:\n"
                + json.dumps(parent_worktrees, indent=2, sort_keys=True)
            )

        if self.checkout.exists():
            if not isinstance(report.get("checkout"), dict):
                raise TaskResetError(
                    "a parent checkout appeared after the recovery preflight"
                )
            manifest = _validate_branchless_checkout_manifest(
                self.state_root / f"{self.task_id}.json",
                task=parent,
                checkout=self.checkout,
                branch=self.branch,
                source_head=str(history["source_commit"]),
                source_tree=str(history["source_tree"]),
                origin=self.origin,
            )
            if manifest.get("manifest_sha256") != report.get(
                "checkout_manifest_sha256"
            ):
                raise TaskResetError("parent checkout manifest changed after preflight")
            _inspect_checkout(
                self.runner,
                self.checkout,
                expected_root=self.checkout_root,
                expected_origin=self.origin,
                expected_branch=self.branch,
                expected_head=str(history["source_commit"]),
                remote_branch_oid=None,
            )
            processes = _processes_using_checkout(
                self.runner, self.source, self.checkout
            )
            containers = _containers_using_checkout(
                self.runner, self.source, self.checkout
            )
            if processes or containers:
                raise TaskResetError(
                    "parent decomposition checkout became active during recovery"
                )

        local_branch = _git_text(
            self.runner,
            self.source,
            "rev-parse",
            "--verify",
            f"refs/heads/{self.branch}",
            check=False,
        ) or None
        recorded_branch = report.get("local_branch_oid")
        if local_branch is not None and local_branch != recorded_branch:
            raise TaskResetError("parent local branch changed after preflight")

        expected_state_names = {
            Path(value).name for value in report.get("active_state_files") or []
        }
        active_names = {
            path.name
            for path in _state_paths(self.state_root, self.task_id)
            if path.is_file()
        }
        archive = Path(str(report.get("planned_state_archive") or "")).resolve()
        expected_archive_parent = (
            self.state_root / "archive" / self.task_id
        ).resolve()
        if archive.parent != expected_archive_parent:
            raise TaskResetError("recovery receipt state archive path escaped its task")
        archived_names = (
            {path.name for path in archive.iterdir() if path.is_file()}
            if archive.is_dir()
            else set()
        )
        if active_names & archived_names or active_names | archived_names != expected_state_names:
            raise TaskResetError(
                "active/archived parent state differs from the recovery receipt"
            )
        expected_state_hashes = report.get("active_state_file_sha256")
        archived_state_paths = tuple(archive.iterdir()) if archive.is_dir() else ()
        current_state_hashes = {
            **{
                path.name: _file_sha256(path)
                for path in _state_paths(self.state_root, self.task_id)
                if path.is_file()
            },
            **{
                path.name: _file_sha256(path)
                for path in archived_state_paths
                if path.is_file()
            },
        }
        if not isinstance(expected_state_hashes, dict) or (
            current_state_hashes != expected_state_hashes
        ):
            raise TaskResetError("parent state file content changed after recovery preflight")
        task_state = _task_state(self.runner, self.source, self.task_id).get("state")
        if not _abandoned_rehearsal_state_is_undelivered(parent, task_state):
            raise TaskResetError(
                "restored parent is not eligible for fresh decomposition"
            )

    def _finish_recovery(self, report: dict[str, Any], path: Path) -> dict[str, Any]:
        self._revalidate_recovery_authority(report)
        number = int(report["issue"]["number"])
        self._validated_completed_issue(
            self._issue_view(number), expected_github_state="CLOSED"
        )
        if _managed_task_issues(
            self.runner, self.source, self.repository, self.task_id, "open"
        ):
            raise TaskResetError("parent managed Issue remains open after recovery")
        if self.checkout.exists():
            raise TaskResetError("parent checkout remains after recovery")
        if any(path.is_file() for path in _state_paths(self.state_root, self.task_id)):
            raise TaskResetError("active parent state remains after recovery")
        if _remote_ref_oid(
            self.runner, self.source, "origin", f"refs/heads/{self.branch}"
        ) is not None:
            raise TaskResetError("parent remote branch appeared during recovery")
        parent = load_committed_task(self.source, self.task_id)
        if _relevant_claims(self.source, parent):
            raise TaskResetError("parent claim appeared during recovery")
        for child in self._proposed_children():
            reasons = self._child_consumption_from_stored(
                child,
                source_commit=str(report["source_commit"]),
            )
            if reasons:
                raise TaskResetError(
                    f"child {child['id']} changed during recovery: " + "; ".join(reasons)
                )
        _validate_taskgraph(self.runner, self.source)
        task_state = _task_state(self.runner, self.source, self.task_id).get("state")
        if not _abandoned_rehearsal_state_is_undelivered(parent, task_state):
            raise TaskResetError("parent is not eligible for fresh decomposition")
        report.update(
            {
                "status": "complete",
                "taskgraph_state": task_state,
                "parent_eligible_for_fresh_decomposition": True,
                "origin_main": report["main_head"],
            }
        )
        _write_report(path, report)
        return report

    def _continue_recovery(self, report: dict[str, Any], path: Path) -> dict[str, Any]:
        self._revalidate_recovery_authority(report)
        self._close_exact_issue(report)
        report["status"] = "issue_closed"
        _write_report(path, report)
        self._revalidate_recovery_authority(report)
        self._remove_exact_checkout(report)
        report["status"] = "checkout_removed"
        _write_report(path, report)
        self._revalidate_recovery_authority(report)
        archive, names = self._archive_recovery_state(report)
        report.update(
            {
                "state_archive": str(archive) if archive else None,
                "archived_state_files": list(names),
                "status": "state_archived",
            }
        )
        _write_report(path, report)
        return self._finish_recovery(report, path)

    def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        path = (
            self.state_root
            / "reset-runs"
            / self.task_id
            / f"{timestamp}-recover-published-decomposition-undo.json"
        )
        report = {
            **plan,
            "reset_timestamp": timestamp,
            "planned_state_archive": str(
                self.state_root / "archive" / self.task_id / timestamp
            ),
            "report_path": str(path),
            "status": "applying",
        }
        _create_report(path, report)
        try:
            verification = self.preflight()
            for field in (
                "repository",
                "task_id",
                "plan_id",
                "apply_commit",
                "undo_commit",
                "source_commit",
                "source_tree",
                "apply_tree",
                "undo_tree",
                "main_head",
                "changed_paths",
                "source_graph_semantic_hash",
                "proposed_graph_semantic_hash",
                "later_commits",
                "protected_child_paths",
                "protected_evidence_prefixes",
                "decomposition_children",
                "issue",
                "checkout",
                "checkout_manifest_sha256",
                "local_branch_oid",
                "active_state_files",
                "active_state_file_sha256",
            ):
                if verification.get(field) != plan.get(field):
                    raise TaskResetError(f"{field} changed between preflight and apply")
            return self._continue_recovery(report, path)
        except Exception as exc:
            report.update({"status": "stopped", "error": str(exc)})
            _write_report(path, report)
            raise

    def resume(self, report_path: Path) -> dict[str, Any]:
        path = Path(report_path).resolve()
        expected_parent = (self.state_root / "reset-runs" / self.task_id).resolve()
        if path.parent != expected_parent or not path.is_file():
            raise TaskResetError("resume receipt is not the exact task recovery path")
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TaskResetError("recovery receipt is not valid UTF-8 JSON") from exc
        if not isinstance(report, dict):
            raise TaskResetError("recovery receipt must contain one JSON object")
        fixed = {
            "operation": PUBLISHED_DECOMPOSITION_UNDO_RECOVERY_OPERATION,
            "repository": self.repository,
            "task_id": self.task_id,
            "graph_delta_path": str(self.graph_delta_path),
            "report_path": str(path),
        }
        for field, expected in fixed.items():
            if report.get(field) != expected:
                raise TaskResetError(f"recovery receipt {field} identity differs")
        if report.get("status") == "complete":
            return report
        for field in ("main_head", "apply_commit", "undo_commit", "source_commit"):
            if not isinstance(report.get(field), str) or re.fullmatch(
                r"[0-9a-f]{40}", str(report.get(field))
            ) is None:
                raise TaskResetError(f"recovery receipt has an invalid {field}")
        self._revalidate_recovery_authority(report)
        return self._continue_recovery(report, path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id", help="Exact task ID, for example NSC-042")
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--checkout-root", type=Path)
    parser.add_argument("--archive-repository")
    parser.add_argument("--confirm-repository")
    parser.add_argument(
        "--resume-report",
        type=Path,
        help="Resume one exact stopped abandoned-rehearsal reset receipt",
    )
    parser.add_argument(
        "--graph-delta",
        type=Path,
        help=(
            "Exact stored graph_delta.json authority for --undo-decomposition or "
            "--recover-published-decomposition-undo"
        ),
    )
    parser.add_argument(
        "--confirm-plan-id",
        help="Exact decomposition plan id required by decomposition reset apply modes",
    )
    parser.add_argument(
        "--confirm-undo-commit",
        help=(
            "Exact published additive undo commit required by "
            "--recover-published-decomposition-undo --apply"
        ),
    )
    parser.add_argument("--apply", action="store_true")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument(
        "--production-state-cleanup",
        action="store_true",
        help="Archive stale cache only when production is already not_delivered and branchless",
    )
    modes.add_argument(
        "--repeat-merged-rehearsal",
        action="store_true",
        help="Additively revert and clean a completed private rehearsal task",
    )
    modes.add_argument(
        "--abandon-incomplete-rehearsal",
        action="store_true",
        help="Close and remove one exact unmerged private rehearsal run",
    )
    modes.add_argument(
        "--revert-delivered-production",
        action="store_true",
        help="Additively revert an unchanged completed production delivery",
    )
    modes.add_argument(
        "--undo-decomposition",
        action="store_true",
        help=(
            "Additively undo one exact unconsumed D1C decomposition and leave the "
            "parent eligible for a fresh decomposition run"
        ),
    )
    modes.add_argument(
        "--recover-published-decomposition-undo",
        action="store_true",
        help=(
            "Retire exact stale coordination after a separately verified additive "
            "decomposition undo is already in private rehearsal main history"
        ),
    )
    args = parser.parse_args(argv)
    try:
        source = args.source.resolve()
        checkout_root = (args.checkout_root or source.parent).resolve()
        runner = CommandRunner()
        repository = _repository_from_origin(
            _git_text(runner, source, "remote", "get-url", "origin")
        )
        if args.production_state_cleanup:
            operation: Any = ProductionAbandonedStateCleanup(
                source=source,
                checkout_root=checkout_root,
                task_id=args.task_id,
                runner=runner,
            )
        elif args.repeat_merged_rehearsal:
            owner, name = repository.split("/", 1)
            archive = args.archive_repository or f"{owner}/{name}-Archive"
            operation = RehearsalTaskReset(
                source=source,
                checkout_root=checkout_root,
                task_id=args.task_id,
                archive_repository=archive,
                runner=runner,
            )
        elif args.abandon_incomplete_rehearsal:
            owner, name = repository.split("/", 1)
            archive = args.archive_repository or f"{owner}/{name}-Archive"
            operation = AbandonedRehearsalTaskReset(
                source=source,
                checkout_root=checkout_root,
                task_id=args.task_id,
                archive_repository=archive,
                runner=runner,
            )
        elif args.undo_decomposition:
            if args.graph_delta is None:
                raise TaskResetError(
                    "--undo-decomposition requires --graph-delta <graph_delta.json>"
                )
            operation = DecompositionUndoReset(
                source=source,
                checkout_root=checkout_root,
                task_id=args.task_id,
                graph_delta=args.graph_delta,
                runner=runner,
            )
        elif args.recover_published_decomposition_undo:
            if args.graph_delta is None:
                raise TaskResetError(
                    "--recover-published-decomposition-undo requires "
                    "--graph-delta <graph_delta.json>"
                )
            operation = PublishedDecompositionUndoRecovery(
                source=source,
                checkout_root=checkout_root,
                task_id=args.task_id,
                graph_delta=args.graph_delta,
                runner=runner,
            )
        else:
            owner, name = repository.split("/", 1)
            archive = args.archive_repository or f"{owner}/{name}-Archive"
            operation = ProductionDeliveredTaskReset(
                source=source,
                checkout_root=checkout_root,
                task_id=args.task_id,
                archive_repository=archive,
                runner=runner,
            )
        if args.resume_report is not None:
            if not (
                args.abandon_incomplete_rehearsal
                or args.undo_decomposition
                or args.recover_published_decomposition_undo
            ):
                raise TaskResetError(
                    "--resume-report requires --abandon-incomplete-rehearsal or "
                    "a decomposition reset mode"
                )
            if not args.apply:
                raise TaskResetError("--resume-report requires --apply")
            if not args.confirm_repository or args.confirm_repository.casefold() != repository.casefold():
                raise TaskResetError(f"--apply requires --confirm-repository {repository}")
            if args.recover_published_decomposition_undo:
                try:
                    recovery_receipt = json.loads(
                        args.resume_report.resolve().read_text(encoding="utf-8")
                    )
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise TaskResetError(
                        "published-undo recovery receipt is not readable UTF-8 JSON"
                    ) from exc
                if not isinstance(recovery_receipt, dict):
                    raise TaskResetError(
                        "published-undo recovery receipt must contain one JSON object"
                    )
                if args.confirm_plan_id != recovery_receipt.get("plan_id"):
                    raise TaskResetError(
                        "recovery resume requires --confirm-plan-id matching its receipt"
                    )
                if args.confirm_undo_commit != recovery_receipt.get("undo_commit"):
                    raise TaskResetError(
                        "recovery resume requires --confirm-undo-commit matching its receipt"
                    )
            report = operation.resume(args.resume_report)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        plan = operation.preflight()
        if not args.apply:
            print(json.dumps({**plan, "status": "ready_dry_run"}, indent=2, sort_keys=True))
            return 0
        if not args.confirm_repository or args.confirm_repository.casefold() != repository.casefold():
            raise TaskResetError(f"--apply requires --confirm-repository {repository}")
        if (
            args.undo_decomposition or args.recover_published_decomposition_undo
        ) and args.confirm_plan_id != plan["plan_id"]:
            raise TaskResetError(
                f"--apply requires --confirm-plan-id {plan['plan_id']}"
            )
        if (
            args.recover_published_decomposition_undo
            and args.confirm_undo_commit != plan["undo_commit"]
        ):
            raise TaskResetError(
                f"--apply requires --confirm-undo-commit {plan['undo_commit']}"
            )
        report = operation.apply(plan)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, RehearsalResetError) as exc:
        print(f"TASK RESET: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
