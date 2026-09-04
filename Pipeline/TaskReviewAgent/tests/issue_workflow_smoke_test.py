#!/usr/bin/env python3
"""Deterministic tests for the durable GitHub Issue workflow controller."""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.dispatch_plan as dispatch_plan_module  # noqa: E402
import Pipeline.TaskReviewAgent.durable_selection as durable_selection_module  # noqa: E402
import Pipeline.TaskReviewAgent.generic_selection as generic_selection_module  # noqa: E402
import Pipeline.TaskReviewAgent.issue_queue as issue_queue_module  # noqa: E402
import Pipeline.TaskReviewAgent.issue_workflow_store as issue_workflow_store_module  # noqa: E402
import Pipeline.TaskReviewAgent.real_workflow as real_workflow_module  # noqa: E402
import Pipeline.TaskReviewAgent.run_pipeline_agent as run_pipeline_agent_module  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    STATE_LABELS,
    IssueWorkflowEvent,
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
    BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER,
    BLOCKED_KIND_DURABLE_RESOURCE_RESERVATION_CONFLICT,
    REPOSITORY,
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowStoreError,
    MemoryIssueBackend,
    resolve_issue_backend_repository,
)

TASK_ID = "NSC-777"
OTHER_TASK_ID = "NSC-778"
CONTRACT_HASH = "a" * 64
SOURCE_HEAD = "1" * 40
HANDOFF_HEAD = "2" * 40
CHECKOUT = r"C:\NSC\NSC\NSC-777"
BRANCH = "nsc-777-synthetic-workflow"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_error(action, text: str) -> None:
    try:
        action()
    except (WorkflowContractError, IssueWorkflowStoreError) as exc:
        require(text in str(exc), f"unexpected error: {exc}")
    else:
        raise AssertionError(f"expected workflow error containing {text!r}")


def task(
    task_id: str,
    resource: str = "unity-scene:Assets/Scenes/Test.unity",
) -> dict:
    return {
        "id": task_id,
        "title": f"Synthetic workflow task {task_id}",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Prove the durable issue workflow.",
        "depends_on": [],
        "exclusive_resources": [resource],
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "requirement": "The workflow is durable."}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "requirement": "The issue resumes safely."}
        ],
        "task_contract_sha256": CONTRACT_HASH if task_id == TASK_ID else "b" * 64,
    }



def create_vincent_inbox(backend: MemoryIssueBackend) -> int:
    issue = backend.create_issue(
        title=issue_workflow_store_module.VINCENT_INBOX_TITLE,
        body=(
            "# NSC-Vincent\n\n"
            "Human-action routing inbox.\n\n"
            f"{issue_workflow_store_module.VINCENT_INBOX_MARKER}\n"
        ),
        labels=[],
        assignees=["cathode26"],
    )
    return int(issue["number"])


class AcceptedWriteTimeoutVincentBackend(MemoryIssueBackend):
    # Accept one Vincent comment, then simulate uncertain transport/read state.
    def __init__(self) -> None:
        super().__init__()
        self.vincent_issue_number: int | None = None
        self.add_comment_calls = 0
        self._post_write_reads = 0
        self._simulate_after_accept = False

    def arm_for_vincent_notification(self, issue_number: int) -> None:
        self.vincent_issue_number = issue_number
        self._simulate_after_accept = True
        self._post_write_reads = 0

    def add_comment(self, issue_number: int, body: str) -> dict:
        if (
            self._simulate_after_accept
            and issue_number == self.vincent_issue_number
            and issue_workflow_store_module.VINCENT_NOTIFICATION_MARKER_PREFIX in body
        ):
            self.add_comment_calls += 1
            super().add_comment(issue_number, body)
            self._simulate_after_accept = False
            raise subprocess.TimeoutExpired(
                cmd=("gh", "issue", "comment"),
                timeout=180,
            )
        return super().add_comment(issue_number, body)

    def get_comments(self, issue_number: int) -> list[dict]:
        if (
            issue_number == self.vincent_issue_number
            and self.add_comment_calls == 1
            and self._post_write_reads < 2
        ):
            self._post_write_reads += 1
            if self._post_write_reads == 1:
                raise OSError("synthetic transient verification read failure")
            # Second read is stale: the accepted comment is temporarily hidden.
            return []
        return super().get_comments(issue_number)


class LaggyMemoryIssueBackend(MemoryIssueBackend):
    # Writes current state immediately but exposes stale Issue bodies for a
    # configured number of subsequent list_issues() reads.
    def __init__(self, *, stale_reads_per_update: int) -> None:
        super().__init__()
        self.stale_reads_per_update = stale_reads_per_update
        self._stale_issue: dict | None = None
        self._stale_reads_remaining = 0
        self.add_comment_calls = 0
        self.update_issue_calls = 0

    def list_issues(self) -> list[dict]:
        current = super().list_issues()
        if self._stale_reads_remaining <= 0 or self._stale_issue is None:
            return current

        self._stale_reads_remaining -= 1
        stale_number = self._stale_issue["number"]
        return [
            json.loads(json.dumps(self._stale_issue))
            if item["number"] == stale_number
            else item
            for item in current
        ]

    def get_issue(self, issue_number: int) -> dict | None:
        current = super().get_issue(issue_number)
        if (
            current is None
            or self._stale_reads_remaining <= 0
            or self._stale_issue is None
            or self._stale_issue.get("number") != issue_number
        ):
            return current
        self._stale_reads_remaining -= 1
        return json.loads(json.dumps(self._stale_issue))

    def add_comment(self, issue_number: int, body: str) -> dict:
        self.add_comment_calls += 1
        return super().add_comment(issue_number, body)

    def update_issue(
        self,
        issue_number: int,
        *,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict:
        stale = json.loads(json.dumps(self.issues[issue_number]))
        self.update_issue_calls += 1
        updated = super().update_issue(
            issue_number,
            body=body,
            labels=labels,
            assignees=assignees,
        )
        self._stale_issue = stale
        self._stale_reads_remaining = self.stale_reads_per_update
        return updated

    def reveal_current_reads(self) -> None:
        self._stale_reads_remaining = 0
        self._stale_issue = None


class BodyBeforeCommentMemoryBackend(MemoryIssueBackend):
    """Expose a current Issue body before its newest event comment."""

    def __init__(self) -> None:
        super().__init__()
        self.hidden_comment_reads = 0
        self.comment_reads = 0

    def get_comments(self, issue_number: int) -> list[dict]:
        self.comment_reads += 1
        comments = super().get_comments(issue_number)
        if self.hidden_comment_reads > 0:
            self.hidden_comment_reads -= 1
            return comments[:-1]
        return comments


class MissingExactReadMemoryBackend(BodyBeforeCommentMemoryBackend):
    def __init__(self) -> None:
        super().__init__()
        self.hide_exact_issue_once = False

    def get_issue(self, issue_number: int) -> dict | None:
        if self.hide_exact_issue_once:
            self.hide_exact_issue_once = False
            return None
        return super().get_issue(issue_number)


class PerIssueSkewMemoryBackend(MemoryIssueBackend):
    """Hide each Issue's newest event comment for its own read budget.

    ``hidden_comment_reads`` is per Issue so one scan can hold several Issues
    inside the GitHub body/event visibility window at the same time, which is
    the case where a shared retry ladder and a per-Issue ladder differ.
    """

    def __init__(self) -> None:
        super().__init__()
        self.hidden_comment_reads: dict[int, int] = {}
        self.comment_reads: dict[int, int] = {}
        self.exact_reads: dict[int, int] = {}

    def get_comments(self, issue_number: int) -> list[dict]:
        self.comment_reads[issue_number] = self.comment_reads.get(issue_number, 0) + 1
        comments = super().get_comments(issue_number)
        remaining = self.hidden_comment_reads.get(issue_number, 0)
        if remaining > 0:
            self.hidden_comment_reads[issue_number] = remaining - 1
            return comments[:-1]
        return comments

    def get_issue(self, issue_number: int) -> dict | None:
        self.exact_reads[issue_number] = self.exact_reads.get(issue_number, 0) + 1
        return super().get_issue(issue_number)


class FakeConsistencyClock:
    """Monotonic clock advanced only by injected sleeps.

    Real wall-clock time must never decide how many retry rounds a
    deterministic test observes, and the recorded sleeps are the evidence that
    the scan deadline is shared rather than paid per Issue.
    """

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(float(seconds))
        self.now += float(seconds)


@contextlib.contextmanager
def fake_consistency_clock():
    """Bind the store module's ``time`` name to a fake clock for one scan."""

    clock = FakeConsistencyClock()
    original = issue_workflow_store_module.time
    issue_workflow_store_module.time = clock
    try:
        yield clock
    finally:
        issue_workflow_store_module.time = original


# A skew budget no bounded ladder can outlast, used to prove fail-closed
# behavior instead of accidental convergence.
NEVER_CONVERGES = 99
CHECKER_TASK_ID = "NSC-999"
CHECKER_TASK = task(
    CHECKER_TASK_ID,
    resource="unity-scene:Assets/Scenes/ScanChecker.unity",
)


def seed_scan_issues(backend: MemoryIssueBackend, *, count: int) -> dict[str, dict]:
    """Create ``count`` coherent agent_working Issues with disjoint resources."""

    tasks = {
        f"NSC-{901 + offset}": task(
            f"NSC-{901 + offset}",
            resource=f"unity-scene:Assets/Scenes/Scan{offset:02d}.unity",
        )
        for offset in range(count)
    }
    for offset, task_id in enumerate(sorted(tasks)):
        owner = IssueWorkflowService(
            backend=backend,
            task_loader=lambda requested: tasks[requested],
            worker_id=f"agent-{offset:02d}",
        )
        acquired = owner.acquire_agent_lease(
            task=tasks[task_id],
            source_head=SOURCE_HEAD,
            branch=f"nsc-{task_id[4:]}-scan",
            checkout_path=rf"C:\NSC\NSC\{task_id}",
            planned_approach="Reserve one distinct scene.",
            expected_validation="The listing is coherent before skew is injected.",
            now=f"2026-09-03T22:{offset:02d}:00Z",
        )
        require(acquired["status"] == "acquired", str(acquired))
    return tasks


def scan_service(
    backend: MemoryIssueBackend,
    tasks: dict[str, dict],
    *,
    consistency_retry_budget: object | None = None,
) -> IssueWorkflowService:
    """Build the scanning worker whose own task overlaps nothing."""

    loader = dict(tasks)
    loader[CHECKER_TASK_ID] = CHECKER_TASK
    values = {
        "backend": backend,
        "task_loader": lambda task_id: loader[task_id],
        "worker_id": "agent-scan",
    }
    if consistency_retry_budget is not None:
        values["consistency_retry_budget"] = consistency_retry_budget
    return IssueWorkflowService(
        **values,
    )


class ClosingExactReadMemoryBackend(BodyBeforeCommentMemoryBackend):
    def __init__(self) -> None:
        super().__init__()
        self.close_on_exact_read = False

    def get_issue(self, issue_number: int) -> dict | None:
        if self.close_on_exact_read:
            self.close_on_exact_read = False
            self.issues[issue_number]["state"] = "CLOSED"
        return super().get_issue(issue_number)


def test_state_event_round_trip_and_chain() -> None:
    state = initial_state(
        task_id=TASK_ID,
        task_contract_sha256=CONTRACT_HASH,
        now="2026-08-27T10:00:00Z",
    )
    state, lease = transition(
        state,
        event_type=WorkflowEventType.AGENT_LEASE_ACQUIRED,
        actor_type=WorkflowActor.AGENT,
        actor_id="agent-a",
        to_state=WorkflowState.AGENT_WORKING,
        details={"worker_id": "agent-a", "lease_id": "c" * 64},
        now="2026-08-27T10:01:00Z",
    )
    state, handoff = transition(
        state,
        event_type=WorkflowEventType.HUMAN_HANDOFF_CREATED,
        actor_type=WorkflowActor.AGENT,
        actor_id="agent-a",
        to_state=WorkflowState.HUMAN_ACTION_REQUIRED,
        to_phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
        details={
            "branch": BRANCH,
            "head_commit": HANDOFF_HEAD,
            "checkout_path": CHECKOUT,
        },
        now="2026-08-27T10:02:00Z",
    )
    state, failed = transition(
        state,
        event_type=WorkflowEventType.HUMAN_VALIDATION_FAILED,
        actor_type=WorkflowActor.HUMAN,
        actor_id="cathode26",
        to_state=WorkflowState.AGENT_READY,
        to_phase=WorkflowPhase.REPAIR,
        details={"tested_commit": HANDOFF_HEAD, "result": "fail"},
        now="2026-08-27T10:03:00Z",
    )

    body = update_issue_body(
        "# Original task body\n",
        state,
        next_action="Repair the failure.",
    )
    require(parse_state(body) == state, "state block round trip changed bytes")
    author = {"login": "cathode26"}
    comments = [
        {"author": author, "body": render_event_comment(lease, "lease")},
        {"author": author, "body": render_event_comment(handoff, "handoff")},
        {"author": author, "body": render_event_comment(failed, "failure")},
    ]
    events = parse_events(comments)
    require(validate_event_chain(state, events) == events, "valid chain was rejected")
    require(
        labels_for_state(state.state) == [STATE_LABELS["agent_ready"]],
        "agent-ready label was not selected",
    )

    tampered = json.loads(json.dumps(failed.to_dict()))
    tampered["details"]["result"] = "pass"
    expect_error(lambda: IssueWorkflowEvent.from_dict(tampered), "event_id")

    wrong_state = replace(state, last_event_id="d" * 64)
    expect_error(
        lambda: validate_event_chain(wrong_state, events),
        "final workflow event",
    )


def test_issue_service_handoff_human_result_and_resume() -> None:
    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    acquired = service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Implement the task and commit the exact branch.",
        expected_validation="Run checks, then hand Unity validation to Vincent.",
        now="2026-08-27T11:00:00Z",
    )
    require(acquired["status"] == "acquired", f"lease was not acquired: {acquired}")
    require(
        service.observe(TASK_ID)["status"] == "agent_working_by_worker",
        "working lease not observed",
    )

    handoff = service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Implemented the synthetic gameplay behavior and tests.",
        completed_checks=("TaskGraph validation passed.", "Branch was pushed."),
        human_steps=("Open the project.", "Enter Play Mode.", "Verify the behavior."),
        expected_result="The behavior matches AC-001.",
        now="2026-08-27T11:01:00Z",
    )
    require(handoff["status"] == "human_action_required", "handoff state was wrong")
    require(not service.list_agent_ready(), "human task incorrectly appeared agent-ready")
    waiting = service.list_human_action_required()
    require(len(waiting) == 1, f"human-action queue was wrong: {waiting}")
    require(
        waiting[0]["workflow_state"]["task_id"] == TASK_ID,
        f"human-action queue changed task identity: {waiting}",
    )

    wrong_result = """## Human validation result

Result: PASS
Tested commit: `3333333333333333333333333333333333333333`
"""
    expect_error(
        lambda: service.apply_human_result(
            task_id=TASK_ID,
            result_body=wrong_result,
            actor_id="cathode26",
            now="2026-08-27T11:02:00Z",
        ),
        "handoff commit",
    )

    failure_result = f"""## Human validation result

Result: FAIL
Tested commit: `{HANDOFF_HEAD}`

Failed step:
The player crossed the blocker.
"""
    ready = service.apply_human_result(
        task_id=TASK_ID,
        result_body=failure_result,
        actor_id="cathode26",
        now="2026-08-27T11:03:00Z",
    )
    require(ready["status"] == "agent_ready", "human failure did not return agent-ready")
    require(
        not service.list_human_action_required(),
        "agent-ready task remained in the human-action queue",
    )
    queue = service.list_agent_ready()
    require(len(queue) == 1, f"agent-ready queue was wrong: {queue}")
    require(
        queue[0]["workflow_state"]["phase"] == "repair",
        "failed human validation did not select repair phase",
    )

    next_agent = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-b",
    )
    resumed = next_agent.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Repair the human-reported blocker on the existing branch.",
        expected_validation="Commit, push, and return a new Unity checklist.",
        now="2026-08-27T11:04:00Z",
    )
    require(resumed["status"] == "acquired", "next agent could not resume the issue")
    require(
        resumed["workflow_state"]["worker_id"] == "agent-b",
        "new agent lease did not record its worker ID",
    )


def test_decomposition_handoff_binds_exact_plan_and_resumes_apply_phase() -> None:
    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="decomposition-agent-a",
    )
    acquired = service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch="main",
        checkout_path=CHECKOUT,
        planned_approach="work_type: decomposition",
        expected_validation="Independent review then exact plan authorization.",
        now="2026-09-03T10:00:00Z",
    )
    require(acquired["status"] == "acquired", str(acquired))
    plan_id = "GDP-" + "c" * 64
    handoff = service.publish_decomposition_handoff(
        task_id=TASK_ID,
        source_head=SOURCE_HEAD,
        checkout_path=CHECKOUT,
        decomposition_run_id="nsc-777-fixture-run",
        artifact_root=r"C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-777\fixture",
        graph_delta_plan_id=plan_id,
        graph_delta_sha256="e" * 64,
        summary="Split the parent into two tiny ordered children.",
        now="2026-09-03T10:01:00Z",
    )
    require(handoff["status"] == "human_action_required", str(handoff))
    require(
        handoff["workflow_state"]["phase"]
        == "decomposition_apply_authorization",
        str(handoff),
    )
    wrong = "## Decomposition application result\n\nResult: APPROVE\nReviewed plan_id: GDP-" + "d" * 64
    expect_error(
        lambda: service.apply_decomposition_result(
            task_id=TASK_ID,
            result_body=wrong,
            actor_id="cathode26",
        ),
        "does not match",
    )
    approved = service.apply_decomposition_result(
        task_id=TASK_ID,
        result_body=(
            "## Decomposition application result\n\n"
            f"Result: APPROVE\nReviewed plan_id: {plan_id}\n"
        ),
        actor_id="cathode26",
        now="2026-09-03T10:02:00Z",
    )
    require(approved["decision"] == "approve", str(approved))
    require(
        approved["workflow_state"]["phase"] == "decomposition_apply",
        str(approved),
    )
    require(len(service.list_agent_ready()) == 1, "approved plan did not resume")
    applier = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="decomposition-agent-b",
    )
    current_parent = {
        **tasks[TASK_ID],
        "task_contract_sha256": "d" * 64,
        "exclusive_resources": [],
    }
    resumed = applier.acquire_agent_lease(
        task=current_parent,
        source_head=SOURCE_HEAD,
        branch="main",
        checkout_path=CHECKOUT,
        planned_approach="Apply the exact approved graph plan.",
        expected_validation="Validate committed graph and push main.",
        expected_workflow_contract_sha256=tasks[TASK_ID][
            "task_contract_sha256"
        ],
        now="2026-09-03T10:03:00Z",
    )
    require(resumed["status"] == "acquired", str(resumed))
    completed = applier.complete_decomposition(
        task_id=TASK_ID,
        graph_delta_plan_id=plan_id,
        applied_commit=HANDOFF_HEAD,
        now="2026-09-03T10:04:00Z",
    )
    require(completed["status"] == "complete", str(completed))
    require(completed["workflow_state"]["state"] == "complete", str(completed))



def test_human_handoff_notifies_vincent_once_and_exact_retry_is_notification_only() -> None:
    backend = MemoryIssueBackend()
    vincent_issue = create_vincent_inbox(backend)
    tasks = {TASK_ID: task(TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
        vincent_inbox_title=issue_workflow_store_module.VINCENT_INBOX_TITLE,
    )
    acquired = service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Implement, commit, and hand validation to Vincent.",
        expected_validation="Vincent follows the source Issue checklist.",
        now="2026-09-01T20:00:00Z",
    )
    require(acquired["status"] == "acquired", f"lease failed: {acquired}")

    handoff = service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Implemented the synthetic behavior.",
        completed_checks=("deterministic checks passed",),
        human_steps=("Open Unity.", "Verify the behavior."),
        expected_result="The behavior is correct.",
        now="2026-09-01T20:01:00Z",
    )
    require(handoff["status"] == "human_action_required", str(handoff))
    require(handoff["vincent_notification"] == "created", str(handoff))

    task_issue = int(handoff["issue_number"])
    source_comments_before_retry = len(backend.get_comments(task_issue))
    vincent_comments = backend.get_comments(vincent_issue)
    require(len(vincent_comments) == 1, f"Vincent inbox comments wrong: {vincent_comments}")
    body = str(vincent_comments[0]["body"])
    require(f"Source Issue: #{task_issue}" in body, body)
    require(HANDOFF_HEAD in body, body)
    require("Report result: Comment on the source Issue, not here." in body, body)
    require("approval helper removes this notification comment." in body, body)
    require(issue_workflow_store_module.VINCENT_NOTIFICATION_MARKER_PREFIX in body, body)

    retry = service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Ignored on notification-only retry.",
        completed_checks=(),
        human_steps=(),
        expected_result="Ignored on notification-only retry.",
        now="2026-09-01T20:02:00Z",
    )
    require(retry["vincent_notification"] == "existing", str(retry))
    require(len(backend.get_comments(task_issue)) == source_comments_before_retry, "exact handoff retry repeated a source Issue mutation")
    require(len(backend.get_comments(vincent_issue)) == 1, "exact handoff retry duplicated the NSC-Vincent notification")

    ready = service.apply_human_result(
        task_id=TASK_ID,
        result_body=(
            "## Human validation result\n\n"
            f"Result: PASS\nTested commit: {HANDOFF_HEAD}\n"
        ),
        actor_id="cathode26",
        now="2026-09-01T20:03:00Z",
    )
    require(ready["status"] == "agent_ready", str(ready))
    delete_calls: list[tuple[int, int | str]] = []

    def accepted_delete_timeout(issue_number: int, comment_id: int | str) -> None:
        delete_calls.append((issue_number, comment_id))
        MemoryIssueBackend.delete_comment(backend, issue_number, comment_id)
        raise subprocess.TimeoutExpired(
            cmd=("gh", "api", "graphql"),
            timeout=180,
        )

    backend.delete_comment = accepted_delete_timeout  # type: ignore[method-assign]
    require(
        service.clear_vincent_notification(TASK_ID) == "deleted",
        "exact NSC-Vincent notification was not deleted",
    )
    require(len(delete_calls) == 1, f"uncertain deletion was repeated: {delete_calls}")
    require(
        backend.get_comments(vincent_issue) == [],
        "notification remained after verified deletion",
    )
    require(
        service.clear_vincent_notification(TASK_ID) == "absent",
        "notification cleanup was not safely idempotent",
    )


def test_github_notification_deletion_uses_exact_graphql_node_id() -> None:
    calls: list[tuple[str, ...]] = []
    backend = SimpleNamespace(_run=lambda args: calls.append(tuple(args)))
    GhIssueBackend.delete_comment(backend, 17, "IC_kwDOFixture123")
    require(len(calls) == 1, str(calls))
    require(calls[0][:3] == ("gh", "api", "graphql"), str(calls[0]))
    require(calls[0][-1] == "id=IC_kwDOFixture123", str(calls[0]))
    expect_error(
        lambda: GhIssueBackend.delete_comment(backend, 17, 123),
        "GraphQL node ID",
    )


def test_configured_vincent_inbox_is_preflighted_before_source_handoff_mutation() -> None:
    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
        vincent_inbox_title=issue_workflow_store_module.VINCENT_INBOX_TITLE,
    )
    acquired = service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Prepare a human handoff.",
        expected_validation="The handoff must not mutate without NSC-Vincent.",
        now="2026-09-01T21:00:00Z",
    )
    task_issue = int(acquired["issue_number"])
    source_comments_before = len(backend.get_comments(task_issue))

    expect_error(
        lambda: service.publish_human_handoff(
            task_id=TASK_ID,
            branch=BRANCH,
            head_commit=HANDOFF_HEAD,
            checkout_path=CHECKOUT,
            implementation_summary="Should not become human-owned.",
            completed_checks=(),
            human_steps=("Synthetic step.",),
            expected_result="Synthetic result.",
            now="2026-09-01T21:01:00Z",
        ),
        "configured Vincent inbox",
    )
    require(service.observe(TASK_ID)["status"] == "agent_working_by_worker", "missing NSC-Vincent allowed the source Issue to enter human_action_required")
    require(len(backend.get_comments(task_issue)) == source_comments_before, "missing NSC-Vincent mutated the source Issue before failing")



def test_vincent_notification_accepted_write_timeout_and_stale_reads_never_rewrite() -> None:
    backend = AcceptedWriteTimeoutVincentBackend()
    vincent_issue = create_vincent_inbox(backend)
    backend.arm_for_vincent_notification(vincent_issue)
    tasks = {TASK_ID: task(TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
        vincent_inbox_title=issue_workflow_store_module.VINCENT_INBOX_TITLE,
    )

    original_delays = issue_workflow_store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS
    issue_workflow_store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS = (
        0.0,
        0.0,
        0.0,
        0.0,
    )
    try:
        acquired = service.acquire_agent_lease(
            task=tasks[TASK_ID],
            source_head=SOURCE_HEAD,
            branch=BRANCH,
            checkout_path=CHECKOUT,
            planned_approach="Exercise uncertain Vincent notification transport.",
            expected_validation="Accepted remote write is verified without rewriting.",
            now="2026-09-01T22:00:00Z",
        )
        require(acquired["status"] == "acquired", f"lease failed: {acquired}")

        handoff = service.publish_human_handoff(
            task_id=TASK_ID,
            branch=BRANCH,
            head_commit=HANDOFF_HEAD,
            checkout_path=CHECKOUT,
            implementation_summary="Synthetic uncertain-write fixture.",
            completed_checks=("deterministic checks passed",),
            human_steps=("Open Unity.",),
            expected_result="Human checklist is routed exactly once.",
            now="2026-09-01T22:01:00Z",
        )
        require(handoff["status"] == "human_action_required", str(handoff))
        require(handoff["vincent_notification"] == "created", str(handoff))
        require(
            backend.add_comment_calls == 1,
            f"uncertain notification path rewrote add_comment: {backend.add_comment_calls}",
        )

        comments = backend.get_comments(vincent_issue)
        matching = [
            comment
            for comment in comments
            if issue_workflow_store_module.VINCENT_NOTIFICATION_MARKER_PREFIX
            in str(comment.get("body") or "")
        ]
        require(
            len(matching) == 1,
            f"accepted timeout produced duplicate notification comments: {matching}",
        )

        retry = service.publish_human_handoff(
            task_id=TASK_ID,
            branch=BRANCH,
            head_commit=HANDOFF_HEAD,
            checkout_path=CHECKOUT,
            implementation_summary="Ignored on exact retry.",
            completed_checks=(),
            human_steps=(),
            expected_result="Ignored on exact retry.",
            now="2026-09-01T22:02:00Z",
        )
        require(retry["vincent_notification"] == "existing", str(retry))
        require(
            backend.add_comment_calls == 1,
            "exact retry repeated the uncertain Vincent notification write",
        )
    finally:
        issue_workflow_store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS = original_delays


def test_post_mutation_verification_retries_stale_reads_without_repeating_writes() -> None:
    backend = LaggyMemoryIssueBackend(stale_reads_per_update=2)
    tasks = {TASK_ID: task(TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )

    original_delays = issue_workflow_store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS
    issue_workflow_store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS = (0.0, 0.0, 0.0)
    try:
        acquired = service.acquire_agent_lease(
            task=tasks[TASK_ID],
            source_head=SOURCE_HEAD,
            branch=BRANCH,
            checkout_path=CHECKOUT,
            planned_approach="Exercise stale verification after lease mutation.",
            expected_validation="The read retries without repeating the lease write.",
            now="2026-08-31T01:00:00Z",
        )
        require(acquired["status"] == "acquired", f"laggy lease did not succeed: {acquired}")
        require(
            backend.add_comment_calls == 1 and backend.update_issue_calls == 1,
            "lease verification retried a mutation instead of reads only",
        )

        handoff = service.publish_human_handoff(
            task_id=TASK_ID,
            branch=BRANCH,
            head_commit=HANDOFF_HEAD,
            checkout_path=CHECKOUT,
            implementation_summary="Exercise stale verification after handoff mutation.",
            completed_checks=("synthetic check",),
            human_steps=("synthetic step",),
            expected_result="The read retries without repeating the handoff write.",
            now="2026-08-31T01:01:00Z",
        )
        require(
            handoff["status"] == "human_action_required",
            f"laggy handoff did not succeed: {handoff}",
        )
        require(
            backend.add_comment_calls == 2 and backend.update_issue_calls == 2,
            "handoff verification retried a mutation instead of reads only",
        )

        failure_result = (
            "## Human validation result\n\n"
            "Result: FAIL\n"
            f"Tested commit: `{HANDOFF_HEAD}`\n\n"
            "Notes:\n"
            "Synthetic stale-read verification fixture.\n"
        )
        ready = service.apply_human_result(
            task_id=TASK_ID,
            result_body=failure_result,
            actor_id="cathode26",
            now="2026-08-31T01:02:00Z",
        )
        require(ready["status"] == "agent_ready", f"laggy human result failed: {ready}")
        require(
            ready["workflow_state"]["phase"] == "repair",
            "laggy human result did not preserve repair semantics",
        )
        require(
            backend.add_comment_calls == 3 and backend.update_issue_calls == 3,
            "human-result verification retried a mutation instead of reads only",
        )
    finally:
        issue_workflow_store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS = original_delays


def test_post_mutation_verification_exhaustion_fails_closed_without_repeating_write() -> None:
    backend = LaggyMemoryIssueBackend(stale_reads_per_update=100)
    tasks = {TASK_ID: task(TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )

    original_delays = issue_workflow_store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS
    issue_workflow_store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS = (0.0, 0.0, 0.0)
    try:
        expect_error(
            lambda: service.acquire_agent_lease(
                task=tasks[TASK_ID],
                source_head=SOURCE_HEAD,
                branch=BRANCH,
                checkout_path=CHECKOUT,
                planned_approach="Exhaust bounded stale verification.",
                expected_validation="Fail closed without repeating the lease write.",
                now="2026-08-31T02:00:00Z",
            ),
            "after 3 bounded read attempt(s)",
        )
        require(
            backend.add_comment_calls == 1 and backend.update_issue_calls == 1,
            "exhausted verification repeated the durable lease mutation",
        )

        backend.reveal_current_reads()
        observed = service.observe(TASK_ID)
        require(
            observed["status"] == "agent_working_by_worker",
            f"durable lease was not preserved after verification exhaustion: {observed}",
        )
    finally:
        issue_workflow_store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS = original_delays


def test_post_mutation_verification_rejects_visible_same_version_conflict() -> None:
    backend = LaggyMemoryIssueBackend(stale_reads_per_update=0)
    tasks = {TASK_ID: task(TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Create exact authority for the conflict test.",
        expected_validation="A same-version mismatch fails closed.",
        now="2026-08-31T03:00:00Z",
    )
    snapshot = service.find(TASK_ID)
    assert snapshot is not None and snapshot.state is not None
    conflicting = replace(
        snapshot,
        state=replace(
            snapshot.state,
            updated_at_utc="2026-08-31T03:00:01Z",
        ),
    )
    reads = 0

    class ConflictReader:
        def find(self, _task_id: str):
            nonlocal reads
            reads += 1
            return conflicting

    comments_before = backend.add_comment_calls
    updates_before = backend.update_issue_calls
    original_delays = issue_workflow_store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS
    issue_workflow_store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS = (0.0,) * 3
    try:
        expect_error(
            lambda: issue_workflow_store_module.verify_post_mutation_state(
                ConflictReader(),
                TASK_ID,
                snapshot.state,
                transition_name="visible conflict",
            ),
            "after 1 bounded read attempt(s)",
        )
    finally:
        issue_workflow_store_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS = original_delays
    require(reads == 1, "same-version conflict was treated as stale and retried")
    require(
        backend.add_comment_calls == comments_before
        and backend.update_issue_calls == updates_before,
        "visible conflict caused a durable mutation",
    )


def test_resource_conflict_and_tampered_history_fail_closed() -> None:
    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Reserve the shared scene.",
        expected_validation="Return it to human review.",
        now="2026-08-27T12:00:00Z",
    )
    blocked = service.acquire_agent_lease(
        task=tasks[OTHER_TASK_ID],
        source_head=SOURCE_HEAD,
        branch="nsc-778-other",
        checkout_path=r"C:\NSC\NSC\NSC-778",
        planned_approach="Attempt overlapping work.",
        expected_validation="Should be blocked.",
        now="2026-08-27T12:01:00Z",
    )
    require(blocked["status"] == "blocked", "resource conflict was not blocked")
    require("overlapping resources" in blocked["reasons"][0], "resource reason missing")
    # MEDIUM-1: a proven overlap against another currently-valid, authorized,
    # managed Issue is exactly the positively-typed benign resource-
    # reservation conflict Stage 3 may retry as ordinary claim_conflict.
    require(
        blocked.get("blocked_kind") == BLOCKED_KIND_DURABLE_RESOURCE_RESERVATION_CONFLICT,
        f"a proven durable resource-reservation overlap must carry the typed benign "
        f"blocked_kind: {blocked}",
    )

    issue_number = next(iter(backend.issues))
    backend.comments[issue_number][0]["body"] = backend.comments[issue_number][0][
        "body"
    ].replace('"worker_id": "agent-a"', '"worker_id": "tampered"')
    observed = service.observe(TASK_ID)
    require(observed["status"] == "conflict", "tampered event history was accepted")

    # An invalid/tampered managed Issue is never benign contention: acquiring
    # against it must fail closed with an exception, never a typed
    # blocked_kind that Stage 3 could retry.
    expect_error(
        lambda: service.acquire_agent_lease(
            task=tasks[TASK_ID],
            source_head=SOURCE_HEAD,
            branch=BRANCH,
            checkout_path=CHECKOUT,
            planned_approach="Resume after tampering.",
            expected_validation="Should fail closed, not retry.",
            now="2026-08-27T12:02:00Z",
        ),
        "invalid workflow state",
    )


def test_resource_scan_retries_body_before_comment_visibility_skew() -> None:
    backend = BodyBeforeCommentMemoryBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    owner = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    acquired = owner.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Reserve the shared scene.",
        expected_validation="Expose the reservation after GitHub converges.",
        now="2026-09-03T21:00:00Z",
    )
    require(acquired["status"] == "acquired", str(acquired))

    backend.hidden_comment_reads = 1
    reads_before = backend.comment_reads
    checker = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-b",
    )
    original_delays = issue_workflow_store_module.RESERVATION_CONSISTENCY_DELAYS_SECONDS
    issue_workflow_store_module.RESERVATION_CONSISTENCY_DELAYS_SECONDS = (0.0, 0.0)
    try:
        conflicts, _diagnostics = checker.resource_conflicts(tasks[OTHER_TASK_ID])
    finally:
        issue_workflow_store_module.RESERVATION_CONSISTENCY_DELAYS_SECONDS = original_delays

    require(
        conflicts == [
            f"{TASK_ID} reserves overlapping resources: "
            "['unity-scene:Assets/Scenes/Test.unity']"
        ],
        str(conflicts),
    )
    require(
        backend.comment_reads - reads_before == 2,
        "reservation scan did not perform exactly one bounded consistency reread",
    )


def test_resource_scan_never_treats_missing_exact_read_as_closed() -> None:
    backend = MissingExactReadMemoryBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    owner = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    owner.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Reserve the shared scene.",
        expected_validation="A missing read must remain fail-closed.",
        now="2026-09-03T21:10:00Z",
    )
    backend.hidden_comment_reads = 1
    backend.hide_exact_issue_once = True
    checker = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-b",
    )
    conflicts, _diagnostics = checker.resource_conflicts(tasks[OTHER_TASK_ID])
    require(len(conflicts) == 1, str(conflicts))
    require("closure was not proven" in conflicts[0], str(conflicts))
    issue_number = next(iter(backend.issues))
    require(backend.issues[issue_number]["state"] == "OPEN", "fixture Issue closed")


def test_resource_scan_skips_only_positively_closed_exact_issue() -> None:
    backend = ClosingExactReadMemoryBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    owner = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    owner.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Reserve then close the shared scene.",
        expected_validation="A positive closed read releases the reservation.",
        now="2026-09-03T21:15:00Z",
    )
    backend.hidden_comment_reads = 1
    backend.close_on_exact_read = True
    checker = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-b",
    )
    conflicts, diagnostics = checker.resource_conflicts(tasks[OTHER_TASK_ID])
    require(conflicts == [] and diagnostics == [], str((conflicts, diagnostics)))
    issue_number = next(iter(backend.issues))
    require(backend.issues[issue_number]["state"] == "CLOSED", "closure was not positive")


def test_deferred_retry_gives_a_late_listed_issue_the_same_rounds() -> None:
    """B6: every listed Issue shares one backoff ladder.

    Four Issues open the same body/event skew at once. Under the previous
    per-Issue sleeping retry the first Issues spent the whole scan deadline and
    the last-listed Issue converged with fewer rounds or not at all. The
    deferred queue must give each Issue the same rounds.
    """

    backend = PerIssueSkewMemoryBackend()
    tasks = seed_scan_issues(backend, count=4)
    checker = scan_service(backend, tasks)
    for issue_number in backend.issues:
        backend.hidden_comment_reads[issue_number] = 3
    backend.comment_reads.clear()

    with fake_consistency_clock() as clock:
        conflicts, diagnostics = checker.resource_conflicts(CHECKER_TASK)

    require(conflicts == [] and diagnostics == [], str((conflicts, diagnostics)))
    require(clock.sleeps == [1.0, 2.0], f"unexpected shared ladder: {clock.sleeps}")
    reads = dict(backend.comment_reads)
    require(
        sorted(reads) == sorted(backend.issues),
        f"the scan did not read every listed Issue: {reads}",
    )
    require(
        set(reads.values()) == {4},
        f"a late-listed Issue did not receive the same retry rounds: {reads}",
    )


def test_shared_ladder_bounds_injected_sleep_for_one_and_many_issues() -> None:
    """B6: total injected sleep stays at the seven-second scan deadline."""

    single_backend = PerIssueSkewMemoryBackend()
    single_tasks = seed_scan_issues(single_backend, count=1)
    single_checker = scan_service(single_backend, single_tasks)
    for issue_number in single_backend.issues:
        single_backend.hidden_comment_reads[issue_number] = NEVER_CONVERGES

    with fake_consistency_clock() as single_clock:
        single_conflicts, _diagnostics = single_checker.resource_conflicts(CHECKER_TASK)

    require(len(single_conflicts) == 1, str(single_conflicts))
    require(
        sum(single_clock.sleeps) <= 7.0,
        f"one Issue exceeded the scan deadline: {single_clock.sleeps}",
    )

    many_backend = PerIssueSkewMemoryBackend()
    many_tasks = seed_scan_issues(many_backend, count=24)
    many_checker = scan_service(many_backend, many_tasks)
    for issue_number in many_backend.issues:
        many_backend.hidden_comment_reads[issue_number] = NEVER_CONVERGES

    with fake_consistency_clock() as many_clock:
        many_conflicts, _diagnostics = many_checker.resource_conflicts(CHECKER_TASK)

    require(len(many_conflicts) == 24, str(len(many_conflicts)))
    require(
        sum(many_clock.sleeps) <= 7.0,
        f"a 24-Issue listing exceeded the scan deadline: {many_clock.sleeps}",
    )
    require(
        single_clock.sleeps == many_clock.sleeps,
        f"listing size changed the sleep ladder: {single_clock.sleeps} vs "
        f"{many_clock.sleeps}",
    )


def test_shared_budget_bounds_repeated_candidate_scans() -> None:
    """B6: one admission cannot re-arm seven seconds for every candidate."""

    backend = PerIssueSkewMemoryBackend()
    tasks = seed_scan_issues(backend, count=1)
    issue_number = next(iter(backend.issues))
    backend.hidden_comment_reads[issue_number] = NEVER_CONVERGES

    with fake_consistency_clock() as clock:
        budget = issue_workflow_store_module.IssueConsistencyRetryBudget()
        checker = scan_service(
            backend,
            tasks,
            consistency_retry_budget=budget,
        )
        first_conflicts, _first_diagnostics = checker.resource_conflicts(CHECKER_TASK)
        second_conflicts, _second_diagnostics = checker.resource_conflicts(CHECKER_TASK)

    require(len(first_conflicts) == 1 and len(second_conflicts) == 1, str((first_conflicts, second_conflicts)))
    require(
        clock.sleeps == [1.0, 2.0, 4.0],
        f"the consistency deadline was re-armed across candidates: {clock.sleeps}",
    )


def test_exact_reads_are_bounded_without_per_issue_sleep_amplification() -> None:
    """B6: exact reads stay bounded per Issue and sleeps do not multiply."""

    backend = PerIssueSkewMemoryBackend()
    tasks = seed_scan_issues(backend, count=12)
    checker = scan_service(backend, tasks)
    for issue_number in backend.issues:
        backend.hidden_comment_reads[issue_number] = NEVER_CONVERGES
    backend.exact_reads.clear()

    with fake_consistency_clock() as clock:
        conflicts, _diagnostics = checker.resource_conflicts(CHECKER_TASK)

    ladder = issue_workflow_store_module.RESERVATION_CONSISTENCY_DELAYS_SECONDS
    require(len(conflicts) == 12, str(len(conflicts)))
    require(
        len(clock.sleeps) == len(ladder) - 1,
        f"the shared ladder slept {len(clock.sleeps)} time(s) for 12 Issues: "
        f"{clock.sleeps}",
    )
    exact_reads = dict(backend.exact_reads)
    require(
        set(exact_reads.values()) == {len(ladder)},
        f"exact reads per Issue are not bounded by the ladder: {exact_reads}",
    )
    require(
        sum(exact_reads.values()) == 12 * len(ladder),
        f"unexpected total exact reads: {exact_reads}",
    )


def test_pending_retry_cap_overflow_is_explicit_and_fails_closed() -> None:
    """B6: an oversized pending queue is never silently truncated."""

    require(
        issue_workflow_store_module.MAX_PENDING_CONSISTENCY_RETRIES == 32,
        "the committed pending retry cap changed",
    )

    backend = PerIssueSkewMemoryBackend()
    tasks = seed_scan_issues(backend, count=3)
    checker = scan_service(backend, tasks)
    for issue_number in backend.issues:
        backend.hidden_comment_reads[issue_number] = NEVER_CONVERGES

    original_cap = issue_workflow_store_module.MAX_PENDING_CONSISTENCY_RETRIES
    issue_workflow_store_module.MAX_PENDING_CONSISTENCY_RETRIES = 2
    try:
        with fake_consistency_clock() as clock:
            conflicts, diagnostics, blocked_kind = (
                checker._resource_conflicts_classified(CHECKER_TASK)
            )
        require(clock.sleeps == [], f"overflow slept before failing closed: {clock.sleeps}")
        require(len(conflicts) == 1 and diagnostics == [], str((conflicts, diagnostics)))
        require(
            blocked_kind is None,
            f"an unreadable reservation picture must never be typed benign "
            f"contention: {blocked_kind}",
        )
        overflow_reason = conflicts[0]
        require(
            "consistency retry queue overflow" in overflow_reason,
            overflow_reason,
        )
        require(
            "exceeding the pending retry cap of 2" in overflow_reason,
            overflow_reason,
        )
        expected_numbers = tuple(sorted(backend.issues))
        for number in expected_numbers:
            require(f"#{number}" in overflow_reason, overflow_reason)

        blocked = checker.acquire_agent_lease(
            task=CHECKER_TASK,
            source_head=SOURCE_HEAD,
            branch="nsc-999-scan",
            checkout_path=r"C:\NSC\NSC\NSC-999",
            planned_approach="Attempt work while the listing cannot be read.",
            expected_validation="Overflow must fail closed, never retry.",
            now="2026-09-03T23:30:00Z",
        )
        require(blocked["status"] == "blocked", str(blocked))
        require(
            "blocked_kind" not in blocked,
            f"retry-cap overflow must not be retryable contention: {blocked}",
        )

        expect_error(checker.list_agent_ready, "consistency retry queue overflow")
        try:
            checker.list_agent_ready()
        except issue_workflow_store_module.IssueConsistencyRetryOverflowError as exc:
            require(
                exc.pending_issue_numbers == expected_numbers,
                f"overflow diagnostic is not deterministic: {exc.pending_issue_numbers}",
            )
        else:
            raise AssertionError("list_agent_ready accepted an overflowing scan")
    finally:
        issue_workflow_store_module.MAX_PENDING_CONSISTENCY_RETRIES = original_cap

    require(
        len(backend.issues) == 3,
        "the overflow path must not create or repair Issues",
    )


def test_persistent_incoherence_still_fails_closed_after_the_ladder() -> None:
    """B6: exhausting the shared ladder is a blocking coordination conflict."""

    backend = PerIssueSkewMemoryBackend()
    tasks = seed_scan_issues(backend, count=1)
    checker = scan_service(backend, tasks)
    issue_number = next(iter(backend.issues))
    backend.hidden_comment_reads[issue_number] = NEVER_CONVERGES

    with fake_consistency_clock() as clock:
        conflicts, diagnostics, blocked_kind = (
            checker._resource_conflicts_classified(CHECKER_TASK)
        )

    require(clock.sleeps == [1.0, 2.0, 4.0], f"unexpected ladder: {clock.sleeps}")
    require(len(conflicts) == 1 and diagnostics == [], str((conflicts, diagnostics)))
    require(
        f"Issue #{issue_number} claims managed workflow state but is invalid"
        in conflicts[0],
        conflicts[0],
    )
    require(
        "state_version does not match workflow event count" in conflicts[0],
        conflicts[0],
    )
    require(blocked_kind is None, f"unreadable state was typed benign: {blocked_kind}")

    with fake_consistency_clock():
        expect_error(checker.list_agent_ready, "is invalid")

    require(
        backend.issues[issue_number]["state"] == "OPEN",
        "the failing scan must not mutate the Issue",
    )


def test_queue_reads_retry_body_before_comment_visibility_skew() -> None:
    backend = BodyBeforeCommentMemoryBackend()
    tasks = {TASK_ID: task(TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Reach human review.",
        expected_validation="Queue reads remain coherent.",
        now="2026-09-03T21:20:00Z",
    )
    service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Synthetic handoff.",
        completed_checks=("synthetic check",),
        human_steps=("Inspect the fixture.",),
        expected_result="The fixture passes.",
        now="2026-09-03T21:21:00Z",
    )
    backend.hidden_comment_reads = 1
    waiting = service.list_human_action_required()
    require(len(waiting) == 1, str(waiting))

    result_body = (
        "## Human validation result\n\n"
        "Result: PASS\n"
        f"Tested commit: `{HANDOFF_HEAD}`\n"
    )
    service.apply_human_result(
        task_id=TASK_ID,
        result_body=result_body,
        actor_id="cathode26",
        now="2026-09-03T21:22:00Z",
    )
    backend.hidden_comment_reads = 1
    ready = service.list_agent_ready()
    require(len(ready) == 1, str(ready))
    backend.hidden_comment_reads = 1
    snapshot = service.find(TASK_ID)
    require(snapshot is not None and snapshot.valid, str(snapshot))


def test_durable_ownership_by_other_is_typed_blocked_kind() -> None:
    """MEDIUM-1: another authorized worker's valid agent_working Issue for
    the SAME task, with no exclusive-resource overlap involved, must block
    with the positively-typed BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER --
    exactly the shape Stage 3 maps to ordinary claim_conflict."""

    backend = MemoryIssueBackend()
    solo_task = {
        **task(TASK_ID),
        "exclusive_resources": [],
    }
    tasks = {TASK_ID: solo_task}
    worker_a = IssueWorkflowService(
        backend=backend, task_loader=lambda task_id: tasks[task_id], worker_id="agent-a"
    )
    acquired = worker_a.acquire_agent_lease(
        task=solo_task,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Reserve the task.",
        expected_validation="Held by agent-a.",
        now="2026-08-27T13:00:00Z",
    )
    require(acquired["status"] == "acquired", f"setup lease was not acquired: {acquired}")

    worker_b = IssueWorkflowService(
        backend=backend, task_loader=lambda task_id: tasks[task_id], worker_id="agent-b"
    )
    blocked = worker_b.acquire_agent_lease(
        task=solo_task,
        source_head=SOURCE_HEAD,
        branch="nsc-777-worker-b",
        checkout_path=r"C:\NSC\NSC\NSC-777-worker-b",
        planned_approach="A different worker attempts the same task.",
        expected_validation="Should be blocked as ordinary durable ownership.",
        now="2026-08-27T13:01:00Z",
    )
    require(blocked["status"] == "blocked", f"a different worker's lease attempt was not blocked: {blocked}")
    require(
        blocked.get("blocked_kind") == BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER,
        f"another worker's valid agent_working Issue must carry the typed benign "
        f"blocked_kind: {blocked}",
    )

    # The SAME worker resuming its own lease must never carry a blocked_kind
    # (it is not even blocked -- "resumed" -- so this also proves the
    # blocked_kind is never emitted merely because the state is AGENT_WORKING).
    resumed = worker_a.acquire_agent_lease(
        task=solo_task,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Resume the held task.",
        expected_validation="Still held by agent-a.",
        now="2026-08-27T13:02:00Z",
    )
    require(resumed["status"] == "resumed", f"the owning worker could not resume: {resumed}")
    require("blocked_kind" not in resumed, f"a successful resume must never carry a blocked_kind: {resumed}")


def test_operational_resource_inspection_failure_is_not_benign() -> None:
    """MEDIUM-1 safety boundary: a task-load failure while scanning another
    Issue's reserved resources is an operational failure, not proven ordinary
    contention, even though a real overlap also exists elsewhere. Mixing one
    unprovable conflict into the result must suppress blocked_kind entirely."""

    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    holder = IssueWorkflowService(
        backend=backend, task_loader=lambda task_id: tasks[task_id], worker_id="agent-a"
    )
    holder.acquire_agent_lease(
        task=tasks[OTHER_TASK_ID],
        source_head=SOURCE_HEAD,
        branch="nsc-778-holder",
        checkout_path=r"C:\NSC\NSC\NSC-778",
        planned_approach="Reserve the shared scene under a different task.",
        expected_validation="Held by agent-a.",
        now="2026-08-27T14:00:00Z",
    )

    def failing_task_loader(task_id: str) -> dict:
        if task_id == OTHER_TASK_ID:
            raise RuntimeError("synthetic committed-task load outage")
        return tasks[task_id]

    challenger = IssueWorkflowService(
        backend=backend, task_loader=failing_task_loader, worker_id="agent-b"
    )
    blocked = challenger.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Attempt the overlapping resource.",
        expected_validation="Should be blocked, but never as benign contention.",
        now="2026-08-27T14:01:00Z",
    )
    require(blocked["status"] == "blocked", f"the resource scan should still block: {blocked}")
    require(
        "blocked_kind" not in blocked,
        f"an operational task-load failure must never be misclassified as benign "
        f"typed contention: {blocked}",
    )


def test_untyped_blocked_state_carries_no_blocked_kind() -> None:
    """MEDIUM-1 safety boundary: a workflow state other than agent_ready or
    agent_working (e.g. human_action_required) is an ordinary, unrelated
    blocked shape and must stay untyped/terminal."""

    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID)}
    service = IssueWorkflowService(
        backend=backend, task_loader=lambda task_id: tasks[task_id], worker_id="agent-a"
    )
    service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Implement the task and commit the exact branch.",
        expected_validation="Run checks, then hand Unity validation to Vincent.",
        now="2026-08-27T15:00:00Z",
    )
    service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Implemented the synthetic gameplay behavior and tests.",
        completed_checks=("TaskGraph validation passed.",),
        human_steps=("Open the project.",),
        expected_result="The behavior matches AC-001.",
        now="2026-08-27T15:01:00Z",
    )

    blocked = service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Attempt to re-acquire while awaiting human validation.",
        expected_validation="Should be blocked, but never as benign contention.",
        now="2026-08-27T15:02:00Z",
    )
    require(blocked["status"] == "blocked", f"human_action_required must still block: {blocked}")
    require(
        "blocked_kind" not in blocked,
        f"a non-agent_working blocked state must never carry a blocked_kind: {blocked}",
    )


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(cwd), *args),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=60.0,
    )


def _make_repo(origin: str | None) -> tempfile.TemporaryDirectory:
    """A throwaway local Git repository with an optional 'origin' remote.

    Never contacts a network: 'git init'/'git remote add' only write local
    Git metadata, and no fetch/push/clone is performed.
    """

    tmp = tempfile.TemporaryDirectory(prefix="nsc-repo-binding-")
    root = Path(tmp.name)
    _run_git(root, "init", "--quiet")
    if origin is not None:
        _run_git(root, "remote", "add", "origin", origin)
    return tmp


def test_resolve_repository_from_production_https_origin() -> None:
    """Case A: production checkout origin resolves to cathode26/NoSafeCircle."""

    with _make_repo("https://github.com/cathode26/NoSafeCircle.git") as tmp:
        resolved = resolve_issue_backend_repository(tmp)
        require(resolved == "cathode26/NoSafeCircle", f"unexpected resolution: {resolved}")
        require(resolved == REPOSITORY, "production origin must match the REPOSITORY constant")


def test_resolve_repository_from_disposable_https_origin() -> None:
    """Case B: a disposable Gauntlet origin never resolves to NoSafeCircle."""

    with _make_repo(
        "https://github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
    ) as tmp:
        resolved = resolve_issue_backend_repository(tmp)
        require(
            resolved == "cathode26/orchestrator-gauntlet-stage4-test",
            f"unexpected resolution: {resolved}",
        )
        require(resolved != REPOSITORY, "disposable origin must not resolve to production")


def test_resolve_repository_from_scp_style_ssh_origin() -> None:
    """Case C: SCP-style SSH origin (git@github.com:owner/repo.git)."""

    with _make_repo(
        "git@github.com:cathode26/orchestrator-gauntlet-stage4-test.git"
    ) as tmp:
        resolved = resolve_issue_backend_repository(tmp)
        require(
            resolved == "cathode26/orchestrator-gauntlet-stage4-test",
            f"unexpected SSH resolution: {resolved}",
        )


def test_resolve_repository_from_ssh_url_origin() -> None:
    """Fable Medium-2: the supported ssh://git@github.com/... URL form resolves."""

    with _make_repo(
        "ssh://git@github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
    ) as tmp:
        resolved = resolve_issue_backend_repository(tmp)
        require(
            resolved == "cathode26/orchestrator-gauntlet-stage4-test",
            f"unexpected ssh:// resolution: {resolved}",
        )
        # Constructor-level coverage: a matching explicit repository assertion
        # is accepted for the same supported ssh:// origin form.
        resolved_with_assertion = resolve_issue_backend_repository(
            tmp, repository="cathode26/orchestrator-gauntlet-stage4-test"
        )
        require(
            resolved_with_assertion == "cathode26/orchestrator-gauntlet-stage4-test",
            f"unexpected ssh:// resolution with assertion: {resolved_with_assertion}",
        )


def test_credential_bearing_ssh_origin_fails_safely_without_leaking_secret() -> None:
    """Fable Medium-1: an unsupported ssh://user:secret@... origin must still

    fail closed (it is not one of the three accepted GitHub remote shapes),
    but the embedded credential must never reach the exception text.
    """

    with _make_repo("ssh://user:secret@github.com/owner/repo.git") as tmp:
        try:
            resolve_issue_backend_repository(tmp)
        except IssueWorkflowStoreError as exc:
            message = str(exc)
            require("secret" not in message, f"credential leaked into error: {message}")
            require(
                "not a supported GitHub repository remote" in message,
                f"unexpected error: {message}",
            )
        else:
            raise AssertionError("credential-bearing ssh:// origin must fail closed")


def test_https_credential_origin_remains_redacted() -> None:
    """https://user:secret@... stays redacted when it fails closed."""

    with _make_repo("https://user:secret@gitlab.com/owner/repo.git") as tmp:
        try:
            resolve_issue_backend_repository(tmp)
        except IssueWorkflowStoreError as exc:
            message = str(exc)
            require("secret" not in message, f"credential leaked into error: {message}")
        else:
            raise AssertionError("non-GitHub credentialed origin must fail closed")


def test_https_token_origin_remains_redacted() -> None:
    """https://TOKEN@... (single-value userinfo) stays redacted when it fails closed."""

    with _make_repo("https://ghp_faketoken@gitlab.com/owner/repo.git") as tmp:
        try:
            resolve_issue_backend_repository(tmp)
        except IssueWorkflowStoreError as exc:
            message = str(exc)
            require(
                "ghp_faketoken" not in message, f"token leaked into error: {message}"
            )
        else:
            raise AssertionError("non-GitHub token-bearing origin must fail closed")


def test_resolve_repository_missing_origin_fails_closed() -> None:
    """Case D: no 'origin' remote at all fails closed rather than defaulting."""

    with _make_repo(None) as tmp:
        expect_error(
            lambda: resolve_issue_backend_repository(tmp),
            "no readable Git 'origin' remote",
        )


def test_gh_issue_backend_fails_closed_for_local_filesystem_origin() -> None:
    """Case E: a REAL GhIssueBackend fails closed for a local/bare remote."""

    with _make_repo("/tmp/some/bare/repo.git") as tmp:
        expect_error(
            lambda: GhIssueBackend(source_root=tmp),
            "not a supported GitHub repository remote",
        )


def test_resolve_repository_non_github_remote_fails_closed() -> None:
    """Case F: a well-formed but non-GitHub remote fails closed."""

    with _make_repo("https://gitlab.com/cathode26/NoSafeCircle.git") as tmp:
        expect_error(
            lambda: resolve_issue_backend_repository(tmp),
            "not a supported GitHub repository remote",
        )


def test_resolve_repository_malformed_github_remote_fails_closed() -> None:
    """Case G: a GitHub host URL missing a repository segment fails closed."""

    with _make_repo("https://github.com/cathode26") as tmp:
        expect_error(
            lambda: resolve_issue_backend_repository(tmp),
            "not a supported GitHub repository remote",
        )


def test_explicit_repository_assertion_matching_origin_is_accepted() -> None:
    """Case H: an explicit --repo-style assertion matching origin is accepted."""

    with _make_repo("https://github.com/cathode26/NoSafeCircle.git") as tmp:
        resolved = resolve_issue_backend_repository(tmp, repository="cathode26/NoSafeCircle")
        require(resolved == "cathode26/NoSafeCircle", f"unexpected resolution: {resolved}")
        # A case-insensitive assertion is accepted too, but the origin's own
        # casing remains canonical.
        resolved_case = resolve_issue_backend_repository(
            tmp, repository="Cathode26/NoSafeCircle"
        )
        require(
            resolved_case == "cathode26/NoSafeCircle",
            f"case-insensitive assertion should still resolve to origin casing: {resolved_case}",
        )


def test_explicit_repository_assertion_mismatch_fails_closed() -> None:
    """Case I: a mismatched explicit assertion fails BEFORE any Issue call."""

    with _make_repo(
        "https://github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
    ) as tmp:
        expect_error(
            lambda: resolve_issue_backend_repository(tmp, repository="cathode26/NoSafeCircle"),
            "does not match",
        )


def test_gh_issue_backend_requires_source_root() -> None:
    """Case J: constructing GhIssueBackend with no source_root stays impossible."""

    try:
        GhIssueBackend()  # type: ignore[call-arg]
    except TypeError:
        pass
    else:
        raise AssertionError("GhIssueBackend() without source_root must be impossible")


def test_gh_issue_backend_mismatch_fails_before_any_gh_invocation() -> None:
    """Network-side-effect regression: a repository-assertion mismatch must
    fail during safe construction, before 'gh' is even probed for -- i.e.
    strictly before any possible ensure_labels/list_issues/create_issue/
    update_issue/add_comment side effect."""

    class _ForbiddenShutil:
        @staticmethod
        def which(name: str) -> str | None:
            raise AssertionError(
                f"repository mismatch must fail before probing for {name!r}"
            )

    original_shutil = issue_workflow_store_module.shutil
    issue_workflow_store_module.shutil = _ForbiddenShutil()
    try:
        with _make_repo(
            "https://github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
        ) as tmp:
            expect_error(
                lambda: GhIssueBackend(source_root=tmp, repository="cathode26/NoSafeCircle"),
                "does not match",
            )
    finally:
        issue_workflow_store_module.shutil = original_shutil


def test_production_composition_binds_to_checkout_origin_not_default() -> None:
    """Every real production construction site shares the same, repository-
    bound GhIssueBackend symbol, and a disposable-origin checkout composes a
    backend targeting itself -- never cathode26/NoSafeCircle. Covers Stage 2
    read-only planning (dispatch_plan/durable_selection/generic_selection/
    issue_queue) and Stage 3/4 durable Issue routing (real_workflow/
    run_pipeline_agent). No GitHub network call is made: only 'gh auth
    status' is faked, and every other subprocess call (git) runs for real
    against the local throwaway repository."""

    real_workflow_source = Path(real_workflow_module.__file__).read_text(encoding="utf-8")
    require(
        "vincent_inbox_title=VINCENT_INBOX_TITLE" in real_workflow_source,
        "real production workflow does not enable the configured NSC-Vincent inbox",
    )

    production_modules = (
        dispatch_plan_module,
        durable_selection_module,
        generic_selection_module,
        issue_queue_module,
        real_workflow_module,
        run_pipeline_agent_module,
    )
    for module in production_modules:
        require(
            module.GhIssueBackend is GhIssueBackend,
            f"{module.__name__} must construct the shared, repository-bound "
            "GhIssueBackend rather than a private copy",
        )

    class _FakeShutil:
        @staticmethod
        def which(name: str) -> str | None:
            return f"/usr/bin/{name}"

    original_shutil = issue_workflow_store_module.shutil
    original_run = issue_workflow_store_module.subprocess.run

    def fake_run(args, **kwargs):
        args_tuple = tuple(args)
        if args_tuple[:1] == ("gh",):
            if args_tuple[:3] == ("gh", "auth", "status"):
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            raise AssertionError(f"unexpected 'gh' invocation in a network-free test: {args}")
        return original_run(args, **kwargs)

    issue_workflow_store_module.shutil = _FakeShutil()
    issue_workflow_store_module.subprocess.run = fake_run
    try:
        with _make_repo(
            "https://github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
        ) as tmp:
            for module in production_modules:
                backend = module.GhIssueBackend(source_root=tmp)
                require(
                    backend.repository == "cathode26/orchestrator-gauntlet-stage4-test",
                    f"{module.__name__} composition bound to {backend.repository!r} "
                    "instead of the checkout origin",
                )
                require(
                    backend.repository != REPOSITORY,
                    f"{module.__name__} composition must never silently target "
                    f"{REPOSITORY}",
                )
    finally:
        issue_workflow_store_module.shutil = original_shutil
        issue_workflow_store_module.subprocess.run = original_run


def main() -> int:
    tests = (
        test_state_event_round_trip_and_chain,
        test_issue_service_handoff_human_result_and_resume,
        test_decomposition_handoff_binds_exact_plan_and_resumes_apply_phase,
        test_human_handoff_notifies_vincent_once_and_exact_retry_is_notification_only,
        test_github_notification_deletion_uses_exact_graphql_node_id,
        test_configured_vincent_inbox_is_preflighted_before_source_handoff_mutation,
        test_vincent_notification_accepted_write_timeout_and_stale_reads_never_rewrite,
        test_post_mutation_verification_retries_stale_reads_without_repeating_writes,
        test_post_mutation_verification_exhaustion_fails_closed_without_repeating_write,
        test_post_mutation_verification_rejects_visible_same_version_conflict,
        test_resource_conflict_and_tampered_history_fail_closed,
        test_resource_scan_retries_body_before_comment_visibility_skew,
        test_resource_scan_never_treats_missing_exact_read_as_closed,
        test_resource_scan_skips_only_positively_closed_exact_issue,
        test_deferred_retry_gives_a_late_listed_issue_the_same_rounds,
        test_shared_ladder_bounds_injected_sleep_for_one_and_many_issues,
        test_shared_budget_bounds_repeated_candidate_scans,
        test_exact_reads_are_bounded_without_per_issue_sleep_amplification,
        test_pending_retry_cap_overflow_is_explicit_and_fails_closed,
        test_persistent_incoherence_still_fails_closed_after_the_ladder,
        test_queue_reads_retry_body_before_comment_visibility_skew,
        test_durable_ownership_by_other_is_typed_blocked_kind,
        test_operational_resource_inspection_failure_is_not_benign,
        test_untyped_blocked_state_carries_no_blocked_kind,
        test_resolve_repository_from_production_https_origin,
        test_resolve_repository_from_disposable_https_origin,
        test_resolve_repository_from_scp_style_ssh_origin,
        test_resolve_repository_from_ssh_url_origin,
        test_credential_bearing_ssh_origin_fails_safely_without_leaking_secret,
        test_https_credential_origin_remains_redacted,
        test_https_token_origin_remains_redacted,
        test_resolve_repository_missing_origin_fails_closed,
        test_gh_issue_backend_fails_closed_for_local_filesystem_origin,
        test_resolve_repository_non_github_remote_fails_closed,
        test_resolve_repository_malformed_github_remote_fails_closed,
        test_explicit_repository_assertion_matching_origin_is_accepted,
        test_explicit_repository_assertion_mismatch_fails_closed,
        test_gh_issue_backend_requires_source_root,
        test_gh_issue_backend_mismatch_fails_before_any_gh_invocation,
        test_production_composition_binds_to_checkout_origin_not_default,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent issue workflow smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
