#!/usr/bin/env python3
"""Translate durable completed-Issue Git identities after an approved history rewrite.

This module deliberately does not rewrite or delete historical Issue comments. It
appends one new hashed workflow event and updates only the live managed Issue state
after committed repository migration authority proves the exact old->new commit
translation and tree identity.
"""

from __future__ import annotations

from typing import Any, Protocol

from Pipeline.TaskReviewAgent.issue_workflow import (
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
from Pipeline.TaskReviewAgent.issue_workflow_store import (
    IssueWorkflowService,
    IssueWorkflowStoreError,
)
from Pipeline.TaskGraph.history_identity_migrations import CommitTranslation


class TranslationResolver(Protocol):
    def resolve(self, commit: str) -> str: ...
    def translation_for(self, commit: str) -> CommitTranslation | None: ...


def migrate_completed_issue_history(
    *,
    service: IssueWorkflowService,
    resolver: TranslationResolver,
    task_id: str,
    actor_id: str,
    now: str | None = None,
) -> dict[str, Any]:
    """Append a complete->complete history migration event to one managed Issue.

    The caller must construct ``resolver`` from committed rewritten-history
    authority. This function validates the live Issue against that authority,
    appends one event, updates the dashboard/state block, and verifies the full
    hash chain again. It never edits pre-existing workflow comments.
    """

    snapshot = service.find(task_id)
    if snapshot is None or not snapshot.valid or snapshot.state is None:
        raise IssueWorkflowStoreError(
            "repository history migration requires a valid managed Issue"
        )
    state = snapshot.state
    if state.state is not WorkflowState.COMPLETE:
        raise IssueWorkflowStoreError(
            f"repository history migration requires complete state, found {state.state.value}"
        )
    if state.phase is not WorkflowPhase.MERGE_CLOSEOUT:
        raise IssueWorkflowStoreError(
            "repository history migration requires merge_closeout phase"
        )
    if state.head_commit is None:
        raise IssueWorkflowStoreError(
            "completed Issue has no head_commit to translate"
        )

    old_head = state.head_commit
    head_translation = resolver.translation_for(old_head)
    if head_translation is None:
        resolved = resolver.resolve(old_head)
        if resolved == old_head:
            return {
                "status": "unchanged",
                "reason": "workflow head is not translated by committed history migration authority",
                **snapshot.to_dict(),
            }
        raise IssueWorkflowStoreError(
            "workflow head resolves indirectly but has no direct committed translation; "
            "apply repository history migrations in manifest order"
        )
    new_head = head_translation.new_commit
    if resolver.resolve(old_head) != new_head:
        raise IssueWorkflowStoreError(
            "workflow head has a chained history translation; apply one manifest at a time"
        )

    old_handoff = state.human_handoff_commit
    new_handoff = old_handoff
    if old_handoff is not None:
        handoff_translation = resolver.translation_for(old_handoff)
        if handoff_translation is not None:
            if handoff_translation.migration_id != head_translation.migration_id:
                raise IssueWorkflowStoreError(
                    "workflow head and human handoff require different history migration manifests"
                )
            if resolver.resolve(old_handoff) != handoff_translation.new_commit:
                raise IssueWorkflowStoreError(
                    "human handoff has a chained history translation; apply one manifest at a time"
                )
            new_handoff = handoff_translation.new_commit
        elif resolver.resolve(old_handoff) != old_handoff:
            raise IssueWorkflowStoreError(
                "human handoff resolves indirectly but has no direct committed translation"
            )

    details = {
        "migration_id": head_translation.migration_id,
        "manifest_path": head_translation.manifest_path,
        "rewrite_report_sha256": head_translation.rewrite_report_sha256,
        "old_head_commit": old_head,
        "new_head_commit": new_head,
        "head_tree": head_translation.tree,
        "old_human_handoff_commit": old_handoff,
        "new_human_handoff_commit": new_handoff,
    }
    next_state, event = transition(
        state,
        event_type=WorkflowEventType.REPOSITORY_HISTORY_MIGRATED,
        actor_type=WorkflowActor.HUMAN,
        actor_id=actor_id,
        to_state=WorkflowState.COMPLETE,
        to_phase=WorkflowPhase.MERGE_CLOSEOUT,
        details=details,
        now=now or utc_now(),
    )

    existing_comment_bodies = tuple(
        str(item.get("body") or "")
        for item in service.backend.get_comments(snapshot.issue_number)
    )
    summary = (
        "The canonical Git history was sanitized to correct automation commit "
        "attribution. Existing workflow-event comments remain unchanged.\n\n"
        f"- **Migration:** `{head_translation.migration_id}`\n"
        f"- **Manifest:** `{head_translation.manifest_path}`\n"
        f"- **Workflow commit:** `{old_head}` -> `{new_head}`\n"
        f"- **Preserved tree:** `{head_translation.tree}`\n"
        + (
            f"- **Human-tested commit:** `{old_handoff}` -> `{new_handoff}`\n"
            if old_handoff is not None
            else ""
        )
    ).rstrip()
    service.backend.add_comment(
        snapshot.issue_number,
        render_event_comment(event, summary),
    )
    updated_body = update_issue_body(
        snapshot.body,
        next_state,
        next_action="No further workflow action is required.",
    )
    service.backend.update_issue(
        snapshot.issue_number,
        body=updated_body,
        labels=labels_for_state(next_state.state, snapshot.labels),
        assignees=list(snapshot.assignees),
    )

    verified = service.find(task_id)
    if verified is None or not verified.valid or verified.state != next_state:
        raise IssueWorkflowStoreError(
            "repository history migration Issue transition could not be verified"
        )
    verified_comments = service.backend.get_comments(snapshot.issue_number)
    if len(verified_comments) != len(existing_comment_bodies) + 1:
        raise IssueWorkflowStoreError(
            "repository history migration changed the unexpected number of Issue comments"
        )
    if tuple(
        str(item.get("body") or "") for item in verified_comments[:-1]
    ) != existing_comment_bodies:
        raise IssueWorkflowStoreError(
            "repository history migration altered existing append-only Issue comments"
        )
    return {
        "status": "history_migrated",
        "migration_id": head_translation.migration_id,
        "old_head_commit": old_head,
        "new_head_commit": new_head,
        "old_human_handoff_commit": old_handoff,
        "new_human_handoff_commit": new_handoff,
        **verified.to_dict(),
    }


__all__ = ["migrate_completed_issue_history"]
