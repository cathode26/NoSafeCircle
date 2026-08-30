#!/usr/bin/env python3
"""Regression tests for terminal completed-Issue discovery and duplicate prevention."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent import openai_downstream  # noqa: E402
from Pipeline.TaskReviewAgent import issue_workflow_store as store  # noqa: E402
from Pipeline.TaskReviewAgent.completed_issue_guard import (  # noqa: E402
    _completed_aware_candidates,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    initial_state,
    labels_for_state,
    render_event_comment,
    transition,
    update_issue_body,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueWorkflowService,
    MemoryIssueBackend,
    render_contract_body,
)

TASK_ID = "NSC-777"
CONTRACT_HASH = "7" * 64
SOURCE_HEAD = "1" * 40
BRANCH = "nsc-777-completed-issue-guard"
CHECKOUT = "C:/NSC/NSC/NSC-777"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def task() -> dict:
    return {
        "schema_version": "2.0",
        "id": TASK_ID,
        "title": "Completed Issue Guard Fixture",
        "contract_revision": 1,
        "contract_disposition": "active",
        "kind": "implementation",
        "type": "gameplay_system",
        "execution_scope": "single_agent",
        "execution_reason": "Exercise completed workflow discovery.",
        "decomposition_state": "concrete",
        "decomposition_reason": "Fixture is concrete.",
        "parent": None,
        "depends_on": [],
        "exclusive_resources": [],
        "acceptance_criteria": [],
        "completion_gates": [],
        "downstream_integration_obligations": [],
        "task_contract_sha256": CONTRACT_HASH,
    }


def create_closed_complete(service: IssueWorkflowService, backend: MemoryIssueBackend) -> int:
    claimed = service.acquire_agent_lease(
        task=task(),
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Complete the synthetic task.",
        expected_validation="The completed workflow remains terminal.",
        now="2026-08-29T06:00:00Z",
    )
    issue_number = claimed["issue_number"]
    snapshot = service.find(TASK_ID)
    require(snapshot is not None and snapshot.state is not None, "fixture Issue was not created")
    next_state, event = transition(
        snapshot.state,
        event_type=WorkflowEventType.COMPLETED,
        actor_type=WorkflowActor.AGENT,
        actor_id=service.worker_id,
        to_state=WorkflowState.COMPLETE,
        to_phase=WorkflowPhase.MERGE_CLOSEOUT,
        details={
            "pull_request_url": "https://example.invalid/pull/777",
            "pull_request_number": 777,
            "merged_commit": "2" * 40,
            "conformant_record_id": "DEL-NSC-777-fixture",
        },
        now="2026-08-29T06:01:00Z",
    )
    backend.add_comment(
        issue_number,
        render_event_comment(event, "Synthetic task closeout completed."),
    )
    backend.update_issue(
        issue_number,
        body=update_issue_body(
            snapshot.body,
            next_state,
            next_action="No further workflow action is required.",
        ),
        labels=labels_for_state(next_state.state, snapshot.labels),
        assignees=[service.assignee],
    )
    backend.issues[issue_number]["state"] = "CLOSED"
    return issue_number


def create_closed_incomplete_duplicate(backend: MemoryIssueBackend) -> int:
    state = initial_state(
        task_id=TASK_ID,
        task_contract_sha256=CONTRACT_HASH,
        now="2026-08-29T06:02:00Z",
    )
    issue = backend.create_issue(
        title=f"{TASK_ID} — Erroneous duplicate",
        body=update_issue_body(
            render_contract_body(task()),
            state,
            next_action="This closed duplicate must never be resumed.",
        ),
        labels=labels_for_state(state.state),
        assignees=["cathode26"],
    )
    backend.issues[issue["number"]]["state"] = "CLOSED"
    return issue["number"]


def test_guard_is_installed_on_live_issue_store() -> None:
    require(
        store._find_candidates.__module__.endswith("completed_issue_guard"),
        "completed-aware candidate selection is not installed",
    )
    require(
        GhIssueBackend.list_issues.__module__.endswith("completed_issue_guard"),
        "GitHub backend does not enumerate completed Issues",
    )
    require(
        IssueWorkflowService.list_agent_ready.__module__.endswith("completed_issue_guard"),
        "agent-ready queue is not filtering closed Issues",
    )


def test_closed_complete_issue_remains_terminal_and_cannot_duplicate() -> None:
    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: task(),
        worker_id="completed-issue-guard-worker",
    )
    canonical_number = create_closed_complete(service, backend)
    issue_count = len(backend.issues)

    snapshot = service.find(TASK_ID)
    require(snapshot is not None, "closed completed Issue became undiscoverable")
    require(snapshot.issue_number == canonical_number, "wrong completed Issue was selected")
    require(snapshot.state is not None and snapshot.state.state is WorkflowState.COMPLETE, "completed state was lost")

    coordination = service.observe(TASK_ID)
    require(coordination["status"] == "complete", "closed completed Issue did not observe as complete")
    outcome = openai_downstream._terminal_outcome(
        SimpleNamespace(task_id=TASK_ID),
        {
            "coordination": coordination,
            "downstream": {},
            "environment": {"ready": True},
        },
    )
    require(isinstance(outcome, dict) and outcome.get("status") == "complete", "goal loop did not stop at completed Issue")

    retry = service.acquire_agent_lease(
        task=task(),
        source_head="3" * 40,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="This must not initialize another Issue.",
        expected_validation="No duplicate is created.",
        now="2026-08-29T06:03:00Z",
    )
    require(retry["status"] == "blocked", "completed task unexpectedly acquired a new lease")
    require(retry["workflow_state"]["state"] == "complete", "retry did not report terminal authority")
    require(len(backend.issues) == issue_count, "completed task created a duplicate Issue")


def test_closed_incomplete_duplicate_is_ignored_by_find_and_queue() -> None:
    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: task(),
        worker_id="completed-issue-guard-worker",
    )
    canonical_number = create_closed_complete(service, backend)
    duplicate_number = create_closed_incomplete_duplicate(backend)
    require(duplicate_number != canonical_number, "fixture did not create a duplicate")

    candidates = _completed_aware_candidates(backend.list_issues(), TASK_ID)
    require(
        [item["number"] for item in candidates] == [canonical_number],
        f"closed incomplete duplicate remained a workflow candidate: {candidates}",
    )
    snapshot = service.find(TASK_ID)
    require(snapshot is not None and snapshot.issue_number == canonical_number, "duplicate displaced canonical completion")
    require(service.list_agent_ready() == [], "closed duplicate leaked into generic agent queue")


def test_github_backend_paginates_all_issues_completely() -> None:
    """The listing must never truncate: an old completed Issue past the first
    result page has to stay discoverable so it remains terminal authority."""

    backend = object.__new__(GhIssueBackend)
    backend.repository = "cathode26/NoSafeCircle"
    observed: dict[str, tuple[str, ...]] = {}

    def rest_issue(number: int, **extra):
        # The REST API reports the API endpoint as `url` and the browser page
        # as `html_url`; the backend must normalize `url` to the browser URL.
        return {
            "number": number,
            "state": "open",
            "user": {"login": "cathode26"},
            "url": f"https://api.github.com/repos/cathode26/NoSafeCircle/issues/{number}",
            "html_url": f"https://github.com/cathode26/NoSafeCircle/issues/{number}",
            **extra,
        }

    page_one = [
        rest_issue(index, title=f"NSC-{index:03d}") for index in range(1, 101)
    ]
    page_two = [
        rest_issue(101, title="pull request", pull_request={}),
        rest_issue(102, title=f"{TASK_ID} — Old completed task", state="closed"),
    ]
    # `gh api --paginate` emits one JSON array per page, concatenated.
    stdout = json.dumps(page_one) + "\n" + json.dumps(page_two)

    def fake_run(args, *, check=True):
        observed["args"] = tuple(args)
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    backend._run = fake_run
    result = GhIssueBackend.list_issues(backend)
    args = observed.get("args") or ()
    require("api" in args, "GitHub backend no longer uses the REST issues API")
    require("--paginate" in args, "GitHub backend does not paginate the Issue listing")
    require(
        any("state=all" in str(item) for item in args),
        "GitHub backend does not request open and closed Issues",
    )
    require(len(result) == 101, f"pagination lost or invented Issues: {len(result)}")
    require(
        all("pull_request" not in item for item in result),
        "pull requests leaked into the Issue listing",
    )
    require(
        any(item.get("number") == 102 for item in result),
        "the completed Issue beyond the first page was forgotten",
    )
    require(
        all(
            item.get("url") == f"https://github.com/cathode26/NoSafeCircle/issues/{item['number']}"
            for item in result
        ),
        "workflow snapshots would lose the human-facing browser URL: the REST "
        "html_url was not normalized into the issue url field",
    )


def test_completed_issue_beyond_first_page_prevents_redispatch() -> None:
    """A closed COMPLETE Issue that only complete pagination can see must keep
    the task terminal instead of allowing a duplicate initialization."""

    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: task(),
        worker_id="completed-issue-guard-worker",
    )
    # Fill more than one REST page of unrelated open Issues before the
    # canonical completed workflow so it sits beyond the first 100 results.
    for index in range(105):
        backend.create_issue(
            title=f"Unrelated operational note {index}",
            body="No workflow state here.",
            labels=[],
            assignees=["cathode26"],
        )
    canonical_number = create_closed_complete(service, backend)
    require(canonical_number > 100, "fixture did not push the completed Issue past page one")
    issue_count = len(backend.issues)

    snapshot = service.find(TASK_ID)
    require(snapshot is not None, "completed Issue beyond page one was not discovered")
    require(snapshot.issue_number == canonical_number, "wrong Issue selected as terminal authority")
    retry = service.acquire_agent_lease(
        task=task(),
        source_head="4" * 40,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="This must not reinitialize the completed task.",
        expected_validation="No duplicate is created.",
        now="2026-08-29T07:00:00Z",
    )
    require(retry["status"] == "blocked", "completed task beyond page one was redispatched")
    require(len(backend.issues) == issue_count, "a duplicate Issue was created")


def main() -> int:
    tests = (
        test_guard_is_installed_on_live_issue_store,
        test_closed_complete_issue_remains_terminal_and_cannot_duplicate,
        test_closed_incomplete_duplicate_is_ignored_by_find_and_queue,
        test_github_backend_paginates_all_issues_completely,
        test_completed_issue_beyond_first_page_prevents_redispatch,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Completed Issue guard tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
