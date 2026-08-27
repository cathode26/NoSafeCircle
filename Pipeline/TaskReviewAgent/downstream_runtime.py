"""Production wrappers that keep downstream state resumable across agent runs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

from .downstream_issue import DownstreamIssueCoordinator, DownstreamIssueError, _meaningful
from .downstream_pipeline import (
    DownstreamPipelineError,
    DownstreamTaskController,
    _copy,
    _decode,
    _git,
    _git_text,
)
from .issue_workflow import (
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    labels_for_state,
    render_event_comment,
    transition,
    update_issue_body,
    utc_now,
)
from .issue_workflow_store import IssueWorkflowStoreError


_READ_PREFIXES = (
    "Assets/",
    "Tasks/",
    "Docs/GDD/",
    "Docs/Engineering/",
    "Docs/AI-Pipeline/UNITY_PROGRAMMER_LANGUAGE.md",
)


def _safe_prefix(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DownstreamPipelineError("repository prefix must be non-empty")
    value = value.strip().replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise DownstreamPipelineError("repository prefix must be a safe relative path")
    check = value if value.endswith("/") else value + "/"
    if not any(
        check.casefold().startswith(prefix.casefold())
        or prefix.casefold().startswith(check.casefold())
        for prefix in _READ_PREFIXES
    ):
        raise DownstreamPipelineError("repository prefix is outside downstream read roots")
    return value


class ResumableDownstreamIssueCoordinator(DownstreamIssueCoordinator):
    """Advance the managed checkout identity when an evidence commit is published."""

    def release_for_pending_checks(
        self,
        *,
        task_id: str,
        pull_request_url: str,
        head_commit: str,
        reason: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.service.find(task_id)
        if snapshot is None or not snapshot.valid or snapshot.state is None:
            raise DownstreamIssueError("lease release requires a valid Issue")
        state = snapshot.state
        if (
            state.state is not WorkflowState.AGENT_WORKING
            or state.worker_id != self.worker_id
            or state.phase is not WorkflowPhase.MERGE_CLOSEOUT
        ):
            raise DownstreamIssueError(
                "pending-check release requires this worker's merge_closeout lease"
            )
        exact_head = _meaningful(head_commit, "head_commit")
        next_state, event = transition(
            state,
            event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
            actor_type=WorkflowActor.AGENT,
            actor_id=self.worker_id,
            to_state=WorkflowState.AGENT_READY,
            to_phase=WorkflowPhase.MERGE_CLOSEOUT,
            details={
                "reason": _meaningful(reason, "reason"),
                "pull_request_url": _meaningful(
                    pull_request_url, "pull_request_url"
                ),
                "head_commit": exact_head,
            },
            now=now or utc_now(),
        )
        # Keep Vincent's original human_handoff_commit intact while advancing the
        # exact branch head that the next generic agent must resume.
        next_state = replace(next_state, head_commit=exact_head)
        self.service.backend.add_comment(
            snapshot.issue_number,
            render_event_comment(
                event,
                "The evidence commit and pull request are published. The agent "
                "released its lease so any later generic agent can resume merge "
                f"closeout at `{exact_head}` from {pull_request_url}.",
            ),
        )
        self.service.backend.update_issue(
            snapshot.issue_number,
            body=update_issue_body(
                snapshot.body,
                next_state,
                next_action=(
                    "Resume merge closeout at the recorded evidence commit, inspect "
                    "pull-request checks, and merge only after they pass."
                ),
            ),
            labels=labels_for_state(next_state.state, snapshot.labels),
            assignees=[self.service.assignee],
        )
        verified = self.service.find(task_id)
        if verified is None or not verified.valid or verified.state != next_state:
            raise IssueWorkflowStoreError("evidence-head lease release could not be verified")
        return {"status": "agent_ready", **verified.to_dict()}


class ResumableDownstreamTaskController(DownstreamTaskController):
    """Connected controller used by the generic launcher."""

    def __init__(self, **values: Any) -> None:
        super().__init__(**values)
        if self.workflow.issue_workflow is not None:
            self.issue = ResumableDownstreamIssueCoordinator(
                self.workflow.issue_workflow
            )

    def _next_action(
        self,
        observation: Mapping[str, Any],
        state: Mapping[str, Any] | None,
    ) -> str:
        action = super()._next_action(observation, state)
        if (
            state is not None
            and state.get("state") == WorkflowState.AGENT_WORKING.value
            and state.get("worker_id") == self.workflow.worker_id
            and state.get("phase") == WorkflowPhase.DELIVERY_EVIDENCE.value
        ):
            approval = self._latest_delivery_approval()
            if (
                approval is not None
                and approval.get("decision") == "request_changes"
                and approval.get("proposal_sha256")
                == self.state.get("proposal_sha256")
            ):
                return "create_delivery_review_proposal"
        return action

    def list_repository_files(
        self,
        *,
        prefix: str = "Assets/",
        limit: int = 300,
    ) -> dict[str, Any]:
        self._assert_checkout()
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise DownstreamPipelineError("repository file limit must be 1 through 1000")
        prefix = _safe_prefix(prefix)
        raw = _git_text(
            self.command_runner,
            self.checkout,
            "ls-tree",
            "-r",
            "--name-only",
            "HEAD",
            "--",
            prefix,
        )
        paths = [line for line in raw.splitlines() if line]
        return {
            "prefix": prefix,
            "count": min(len(paths), limit),
            "truncated": len(paths) > limit,
            "paths": paths[:limit],
        }

    def search_repository(
        self,
        *,
        query: str,
        prefixes: Iterable[str] = ("Assets/",),
        limit: int = 100,
    ) -> dict[str, Any]:
        self._assert_checkout()
        if not isinstance(query, str) or not query.strip() or len(query) > 160:
            raise DownstreamPipelineError("search query must be 1 through 160 characters")
        if any(ord(character) < 32 or ord(character) == 127 for character in query):
            raise DownstreamPipelineError("search query contains a control character")
        if not isinstance(limit, int) or not 1 <= limit <= 300:
            raise DownstreamPipelineError("search limit must be 1 through 300")
        approved = [_safe_prefix(value) for value in prefixes]
        result = _git(
            self.command_runner,
            self.checkout,
            "grep",
            "-n",
            "-I",
            "-F",
            "--",
            query,
            "HEAD",
            "--",
            *approved,
            check=False,
        )
        if result.returncode not in (0, 1):
            raise DownstreamPipelineError("git grep failed")
        matches: list[dict[str, Any]] = []
        for line in _decode(result.stdout, "git grep output").splitlines():
            rendered = line[5:] if line.startswith("HEAD:") else line
            try:
                path, line_number, text = rendered.split(":", 2)
                matches.append(
                    {
                        "path": path,
                        "line": int(line_number),
                        "text": text[:500],
                    }
                )
            except (TypeError, ValueError):
                continue
            if len(matches) >= limit:
                break
        return {
            "query": query,
            "prefixes": approved,
            "count": len(matches),
            "truncated": len(matches) >= limit,
            "matches": matches,
        }

    def finalize_delivery_evidence_and_open_pr(self) -> dict[str, Any]:
        result = super().finalize_delivery_evidence_and_open_pr()
        if self.issue is None:
            raise DownstreamPipelineError("Issue workflow is unavailable")
        evidence_commit = self.state.get("evidence_commit")
        pull_request_url = self.state.get("pull_request_url")
        if not isinstance(evidence_commit, str) or not isinstance(
            pull_request_url, str
        ):
            raise DownstreamPipelineError(
                "delivery finalization did not persist PR/evidence identities"
            )
        release = self.issue.release_for_pending_checks(
            task_id=self.task_id,
            pull_request_url=pull_request_url,
            head_commit=evidence_commit,
            reason=(
                "Delivery evidence was committed, TaskGraph derived conformant, and "
                "the pull request was opened. Resume after its checks finish."
            ),
        )
        return {
            **_copy(result),
            "status": "checks_pending",
            "lease_release": release,
        }
