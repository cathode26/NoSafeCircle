#!/usr/bin/env python3
"""Safely clear abandoned task state in production or repeat a rehearsal task."""

from __future__ import annotations

import argparse
import datetime as dt
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
    source_head: str,
    source_tree: str,
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
        "initial_source_head": source_head,
        "initial_source_tree": source_tree,
        "task_contract_path": f"Tasks/{task.get('id')}.yaml",
        "task_contract_revision": task.get("contract_revision"),
        "task_contract_sha256": task.get("task_contract_sha256"),
        "authority": "durable_checkout_identity",
    }
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
        if task_state.get("state") != "not_delivered":
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
        if task_head is not None and (
            _git(
                self.runner,
                self.source,
                "merge-base",
                "--is-ancestor",
                task_head,
                head,
                check=False,
            ).returncode
            == 0
        ):
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
        remote_branch_oid = _remote_ref_oid(
            self.runner,
            self.source,
            "origin",
            f"refs/heads/{self.branch}",
        )
        if remote_branch_oid != task_head:
            raise TaskResetError("remote task branch differs from the managed Issue head")
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
            assert checkout_head is not None
            checkout_tree = _git_text(
                self.runner, self.source, "rev-parse", f"{checkout_head}^{{tree}}"
            )
            if task_head is None:
                _validate_branchless_checkout_manifest(
                    self.state_root / f"{self.task_id}.json",
                    task=self.task,
                    checkout=self.checkout,
                    branch=self.branch,
                    source_head=checkout_head,
                    source_tree=checkout_tree,
                    origin=self.origin,
                )
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
            "taskgraph_state": "not_delivered",
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
            ) != plan["task_head"]:
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
            if _task_state(self.runner, self.source, self.task_id).get("state") != "not_delivered":
                raise TaskResetError("TaskGraph did not remain not_delivered")
            _validate_taskgraph(self.runner, self.source)
            report.update({"status": "complete", "taskgraph_state": "not_delivered"})
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
        if _task_state(self.runner, self.source, self.task_id).get("state") != "not_delivered":
            raise TaskResetError("TaskGraph did not remain not_delivered")
        _validate_taskgraph(self.runner, self.source)
        report.update({"status": "complete", "taskgraph_state": "not_delivered"})
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
    changed = [
        path
        for path in paths
        if _tree_entry(runner, source, merge_commit, path)
        != _tree_entry(runner, source, current_main, path)
    ]
    if changed:
        raise TaskResetError(
            "later production commits changed task-owned paths; automatic revert is refused: "
            + ", ".join(changed)
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
            if not args.abandon_incomplete_rehearsal or not args.apply:
                raise TaskResetError(
                    "--resume-report requires --abandon-incomplete-rehearsal --apply"
                )
            if not args.confirm_repository or args.confirm_repository.casefold() != repository.casefold():
                raise TaskResetError(f"--apply requires --confirm-repository {repository}")
            report = operation.resume(args.resume_report)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        plan = operation.preflight()
        if not args.apply:
            print(json.dumps({**plan, "status": "ready_dry_run"}, indent=2, sort_keys=True))
            return 0
        if not args.confirm_repository or args.confirm_repository.casefold() != repository.casefold():
            raise TaskResetError(f"--apply requires --confirm-repository {repository}")
        report = operation.apply(plan)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, RehearsalResetError) as exc:
        print(f"TASK RESET: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
