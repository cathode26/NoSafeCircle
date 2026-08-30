#!/usr/bin/env python3
"""Regression tests for append-only completed-Issue history migration."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.HistoryMigration.issue_migration import (  # noqa: E402
    migrate_completed_issue_history,
)
from Pipeline.TaskGraph.history_identity_migrations import CommitTranslation  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowActor,
    WorkflowContractError,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    initial_state,
    labels_for_state,
    parse_events,
    parse_state,
    render_event_comment,
    transition,
    update_issue_body,
    validate_event_chain,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    IssueWorkflowStoreError,
    MemoryIssueBackend,
)

TASK_ID = "NSC-777"
CONTRACT_HASH = "a" * 64
OLD_HANDOFF = "3" * 40
OLD_HEAD = "4" * 40
NEW_HEAD = "5" * 40
HEAD_TREE = "6" * 40
REPORT_HASH = "7" * 64
MIGRATION_ID = "synthetic-history-rewrite"
MANIFEST_PATH = (
    "Pipeline/TaskGraph/migrations/"
    f"repository-history-identity-{MIGRATION_ID}.json"
)
BRANCH = "nsc-777-history-migration"
CHECKOUT = r"C:\NSC\NSC\NSC-777"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def task() -> dict:
    return {
        "id": TASK_ID,
        "title": "History migration fixture",
        "task_contract_sha256": CONTRACT_HASH,
        "exclusive_resources": [],
    }


class FakeResolver:
    def __init__(self) -> None:
        self.entry = CommitTranslation(
            old_commit=OLD_HEAD,
            new_commit=NEW_HEAD,
            tree=HEAD_TREE,
            migration_id=MIGRATION_ID,
            manifest_path=MANIFEST_PATH,
            rewrite_report_sha256=REPORT_HASH,
        )

    def resolve(self, commit: str) -> str:
        return NEW_HEAD if commit == OLD_HEAD else commit

    def translation_for(self, commit: str) -> CommitTranslation | None:
        return self.entry if commit == OLD_HEAD else None


def create_closed_complete_fixture() -> tuple[MemoryIssueBackend, IssueWorkflowService, int]:
    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda _task_id: task(),
        worker_id="history-migration-test-worker",
    )
    state = initial_state(
        task_id=TASK_ID,
        task_contract_sha256=CONTRACT_HASH,
        now="2026-08-29T01:00:00Z",
    )
    events = []
    state, event = transition(
        state,
        event_type=WorkflowEventType.AGENT_LEASE_ACQUIRED,
        actor_type=WorkflowActor.AGENT,
        actor_id="agent-a",
        to_state=WorkflowState.AGENT_WORKING,
        details={"worker_id": "agent-a", "lease_id": "b" * 64},
        now="2026-08-29T01:01:00Z",
    )
    events.append(event)
    state, event = transition(
        state,
        event_type=WorkflowEventType.HUMAN_HANDOFF_CREATED,
        actor_type=WorkflowActor.AGENT,
        actor_id="agent-a",
        to_state=WorkflowState.HUMAN_ACTION_REQUIRED,
        to_phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
        details={
            "branch": BRANCH,
            "head_commit": OLD_HANDOFF,
            "checkout_path": CHECKOUT,
        },
        now="2026-08-29T01:02:00Z",
    )
    events.append(event)
    state, event = transition(
        state,
        event_type=WorkflowEventType.HUMAN_VALIDATION_PASSED,
        actor_type=WorkflowActor.HUMAN,
        actor_id="Vincent",
        to_state=WorkflowState.AGENT_READY,
        to_phase=WorkflowPhase.DELIVERY_EVIDENCE,
        details={"tested_commit": OLD_HANDOFF, "result": "pass"},
        now="2026-08-29T01:03:00Z",
    )
    events.append(event)
    state, event = transition(
        state,
        event_type=WorkflowEventType.AGENT_LEASE_ACQUIRED,
        actor_type=WorkflowActor.AGENT,
        actor_id="agent-b",
        to_state=WorkflowState.AGENT_WORKING,
        details={"worker_id": "agent-b", "lease_id": "c" * 64},
        now="2026-08-29T01:04:00Z",
    )
    events.append(event)
    # Delivery/reintegration can advance the operational head after the human-tested
    # handoff without changing the human result. Model that exact completed-state
    # shape before closeout.
    state = replace(state, head_commit=OLD_HEAD)
    state, event = transition(
        state,
        event_type=WorkflowEventType.COMPLETED,
        actor_type=WorkflowActor.AGENT,
        actor_id="agent-b",
        to_state=WorkflowState.COMPLETE,
        to_phase=WorkflowPhase.MERGE_CLOSEOUT,
        details={
            "pull_request_url": "https://example.invalid/pull/777",
            "pull_request_number": 777,
            "merged_commit": "d" * 40,
            "conformant_record_id": "DEL-NSC-777-fixture",
        },
        now="2026-08-29T01:05:00Z",
    )
    events.append(event)

    issue = backend.create_issue(
        title=f"{TASK_ID} — History migration fixture",
        body=update_issue_body(
            f"<!-- no-safe-circle-task: {TASK_ID} -->\n# fixture\n",
            state,
            next_action="No further workflow action is required.",
        ),
        labels=labels_for_state(state.state),
        assignees=["cathode26"],
    )
    issue_number = issue["number"]
    backend.comments[issue_number] = [
        {
            "id": index,
            "author": {"login": "cathode26"},
            "body": render_event_comment(item, f"fixture event {index}"),
        }
        for index, item in enumerate(events, start=1)
    ]
    backend.next_comment = len(events) + 1
    backend.issues[issue_number]["state"] = "CLOSED"
    snapshot = service.find(TASK_ID)
    require(snapshot is not None and snapshot.valid, "closed complete fixture is invalid")
    return backend, service, issue_number


def test_completed_issue_migration_preserves_old_comments_and_terminal_state() -> None:
    backend, service, issue_number = create_closed_complete_fixture()
    before = tuple(item["body"] for item in backend.comments[issue_number])
    result = migrate_completed_issue_history(
        service=service,
        resolver=FakeResolver(),
        task_id=TASK_ID,
        actor_id="Vincent",
        now="2026-08-29T01:06:00Z",
    )
    require(result["status"] == "history_migrated", f"migration failed: {result}")
    require(backend.issues[issue_number]["state"] == "CLOSED", "migration reopened Issue")
    after = tuple(item["body"] for item in backend.comments[issue_number])
    require(after[:-1] == before, "migration edited historical workflow comments")
    require(len(after) == len(before) + 1, "migration did not append exactly one event")

    state = parse_state(backend.issues[issue_number]["body"])
    require(state is not None, "migrated Issue lost workflow state")
    require(state.state is WorkflowState.COMPLETE, "migration changed terminal state")
    require(state.phase is WorkflowPhase.MERGE_CLOSEOUT, "migration changed terminal phase")
    require(state.current_actor is WorkflowActor.NONE, "migration assigned a terminal owner")
    require(state.head_commit == NEW_HEAD, "live Issue head was not translated")
    require(state.human_handoff_commit == OLD_HANDOFF, "unchanged human-tested commit moved")
    require(state.human_result == "pass", "migration lost human PASS")

    events = parse_events(backend.comments[issue_number])
    require(validate_event_chain(state, events) == events, "migrated event chain is invalid")
    latest = events[-1]
    require(
        latest.event_type is WorkflowEventType.REPOSITORY_HISTORY_MIGRATED,
        "migration did not append the dedicated event type",
    )
    require(latest.details["old_head_commit"] == OLD_HEAD, "old head missing from event")
    require(latest.details["new_head_commit"] == NEW_HEAD, "new head missing from event")
    require(latest.details["head_tree"] == HEAD_TREE, "tree proof missing from event")

    second = migrate_completed_issue_history(
        service=service,
        resolver=FakeResolver(),
        task_id=TASK_ID,
        actor_id="Vincent",
        now="2026-08-29T01:07:00Z",
    )
    require(second["status"] == "unchanged", "already migrated Issue was not idempotent")
    require(len(backend.comments[issue_number]) == len(after), "idempotent retry added an event")


def test_history_migration_rejects_wrong_old_head_and_noncomplete_state() -> None:
    backend, service, issue_number = create_closed_complete_fixture()
    state = parse_state(backend.issues[issue_number]["body"])
    assert state is not None
    wrong_details = {
        "migration_id": MIGRATION_ID,
        "manifest_path": MANIFEST_PATH,
        "rewrite_report_sha256": REPORT_HASH,
        "old_head_commit": "e" * 40,
        "new_head_commit": NEW_HEAD,
        "head_tree": HEAD_TREE,
        "old_human_handoff_commit": OLD_HANDOFF,
        "new_human_handoff_commit": OLD_HANDOFF,
    }
    try:
        transition(
            state,
            event_type=WorkflowEventType.REPOSITORY_HISTORY_MIGRATED,
            actor_type=WorkflowActor.HUMAN,
            actor_id="Vincent",
            to_state=WorkflowState.COMPLETE,
            to_phase=WorkflowPhase.MERGE_CLOSEOUT,
            details=wrong_details,
            now="2026-08-29T01:06:00Z",
        )
    except WorkflowContractError as exc:
        require("old_head_commit" in str(exc), f"unexpected wrong-head error: {exc}")
    else:
        raise AssertionError("wrong old_head_commit was accepted")

    open_backend = MemoryIssueBackend()
    open_service = IssueWorkflowService(
        backend=open_backend,
        task_loader=lambda _task_id: task(),
        worker_id="history-migration-test-worker",
    )
    acquired = open_service.acquire_agent_lease(
        task=task(),
        source_head="f" * 40,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="fixture",
        expected_validation="fixture",
        now="2026-08-29T02:00:00Z",
    )
    require(acquired["status"] == "acquired", "noncomplete fixture was not created")
    try:
        migrate_completed_issue_history(
            service=open_service,
            resolver=FakeResolver(),
            task_id=TASK_ID,
            actor_id="Vincent",
            now="2026-08-29T02:01:00Z",
        )
    except IssueWorkflowStoreError as exc:
        require("complete state" in str(exc), f"unexpected noncomplete error: {exc}")
    else:
        raise AssertionError("noncomplete Issue accepted repository history migration")


def test_tampered_migration_event_fails_closed() -> None:
    backend, service, issue_number = create_closed_complete_fixture()
    migrate_completed_issue_history(
        service=service,
        resolver=FakeResolver(),
        task_id=TASK_ID,
        actor_id="Vincent",
        now="2026-08-29T03:00:00Z",
    )
    body = backend.comments[issue_number][-1]["body"]
    backend.comments[issue_number][-1]["body"] = body.replace(
        f'"new_head_commit": "{NEW_HEAD}"',
        f'"new_head_commit": "{"8" * 40}"',
    )
    observed = service.observe(TASK_ID)
    require(observed["status"] == "conflict", "tampered migration event was accepted")


def main() -> int:
    tests = (
        test_completed_issue_migration_preserves_old_comments_and_terminal_state,
        test_history_migration_rejects_wrong_old_head_and_noncomplete_state,
        test_tampered_migration_event_fails_closed,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Completed Issue history migration tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
