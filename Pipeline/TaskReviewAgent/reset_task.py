#!/usr/bin/env python3
"""Safely clear abandoned task state in production or repeat a rehearsal task."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import validate_task_id  # noqa: E402
from Pipeline.TaskReviewAgent.real_checkout import branch_name  # noqa: E402
from Pipeline.TaskReviewAgent.reset_rehearsal_task import (  # noqa: E402
    CommandRunner,
    RehearsalResetError,
    RehearsalTaskReset,
    _archive_state_files,
    _create_report,
    _git,
    _git_text,
    _json_command,
    _relevant_claims,
    _remote_ref_oid,
    _repo_metadata,
    _repository_from_origin,
    _state_paths,
    _task_state,
    _validate_taskgraph,
    _write_report,
)


class TaskResetError(RehearsalResetError):
    """Raised when production abandoned-state cleanup cannot be proven safe."""


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
        else:
            owner, name = repository.split("/", 1)
            archive = args.archive_repository or f"{owner}/{name}-Archive"
            operation = RehearsalTaskReset(
                source=source,
                checkout_root=checkout_root,
                task_id=args.task_id,
                archive_repository=archive,
                runner=runner,
            )
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
