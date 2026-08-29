#!/usr/bin/env python3
"""Regression tests for downstream event authority and deterministic routing."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.codex_supervisor import (  # noqa: E402
    CodexSupervisorError,
    SupervisorDecision,
)
from Pipeline.TaskReviewAgent.contracts import semantic_sha256  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_determinism import (  # noqa: E402
    _assert_current_main_integrated,
    _authoritative_human_validation,
    _record_same_state_rejection,
    allowed_actions_for,
    bounded_history,
)
from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
    _default_runner,
)
from Pipeline.TaskReviewAgent.downstream_resilience import validation_plan_for  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    ResumableDownstreamTaskController,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    IssueWorkflowEvent,
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
)
from Pipeline.TaskReviewAgent.mainline_reintegration import (  # noqa: E402
    _automation_receipt_for,
)
from Pipeline.TaskReviewAgent.tests.downstream_resilience_smoke_test import (  # noqa: E402
    BRANCH,
    CONTRACT_PATH,
    TASK_ID,
    create_migration_fixture,
    git,
    migration_event,
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


class FakeBackend:
    def __init__(self, comments: list[dict[str, Any]]) -> None:
        self.comments = comments

    def get_comments(self, issue_number: int) -> list[dict[str, Any]]:
        del issue_number
        return json.loads(json.dumps(self.comments))


class FakeService:
    def __init__(
        self,
        *,
        events: list[IssueWorkflowEvent],
        state: Any,
        comments: list[dict[str, Any]] | None = None,
    ) -> None:
        self.backend = FakeBackend(comments or [])
        self.snapshot = SimpleNamespace(
            valid=True,
            managed=True,
            state=state,
            events=events,
            issue_number=777,
            issue_url="https://example.invalid/issues/777",
        )

    def find(self, task_id: str):
        return self.snapshot if task_id == TASK_ID else None


def test_human_authority_ignores_agent_template() -> None:
    human_commit = "1" * 40
    false_template_commit = "2" * 40
    human_body = (
        "## Human validation result\n\n"
        "Result: PASS\n"
        f"Tested commit: `{human_commit}`\n\n"
        "Completed steps:\n- focused PlayMode tests passed.\n"
    )
    event = IssueWorkflowEvent.create(
        task_id=TASK_ID,
        sequence=1,
        previous_event_id=None,
        event_type=WorkflowEventType.HUMAN_VALIDATION_PASSED,
        from_state=WorkflowState.HUMAN_ACTION_REQUIRED,
        to_state=WorkflowState.AGENT_READY,
        from_phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
        to_phase=WorkflowPhase.DELIVERY_EVIDENCE,
        actor_type=WorkflowActor.HUMAN,
        actor_id="Vincent",
        task_contract_sha256="a" * 64,
        occurred_at_utc="2026-08-28T10:00:00Z",
        details={
            "tested_commit": human_commit,
            "result": "pass",
            "human_comment_sha256": semantic_sha256({"body": human_body}),
        },
    )
    template = (
        "## Workflow event: human_handoff_created\n\n"
        "Copy this example:\n\n```text\n"
        "## Human validation result\n\n"
        "Result: PASS\n"
        f"Tested commit: `{false_template_commit}`\n"
        "```\n"
    )
    state = SimpleNamespace(
        human_handoff_commit=human_commit,
        human_result="pass",
        branch=BRANCH,
    )
    service = FakeService(
        events=[event],
        state=state,
        comments=[
            {"id": 10, "body": human_body},
            {"id": 11, "body": template},
        ],
    )
    controller = SimpleNamespace(
        task_id=TASK_ID,
        workflow=SimpleNamespace(issue_workflow=service),
    )
    result = _authoritative_human_validation(controller)
    require(result is not None, "authoritative human result was not found")
    require(result["tested_commit"] == human_commit, "agent template replaced human authority")
    require(result["comment_id"] == 10, "wrong Issue comment was selected")
    require(result["event_id"] == event.event_id, "workflow event identity was lost")


def _advance_with_automation_merge(
    repo: Path,
    prior_head: str,
    *,
    mutate_task_blob: bool = False,
) -> tuple[str, str]:
    git(repo, "switch", "main")
    path = repo / "Pipeline/TaskReviewAgent/later_automation.py"
    path.write_text("# later automation-only change\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Advance automation after migration")
    main_head = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", BRANCH)
    require(git(repo, "rev-parse", "HEAD") == prior_head, "fixture branch moved unexpectedly")
    git(
        repo,
        "merge",
        "--no-ff",
        "--no-edit",
        "-m",
        "Integrate later automation",
        main_head,
    )
    if mutate_task_blob:
        (repo / "Assets/Feature.cs").write_text(
            "task blob changed during integration\n",
            encoding="utf-8",
        )
        git(repo, "add", "Assets/Feature.cs")
        git(repo, "commit", "--amend", "--no-edit")
    return main_head, git(repo, "rev-parse", "HEAD")


def _receipt_controller(
    repo: Path,
    *,
    state: dict[str, Any],
    human_commit: str,
    prior_head: str,
    main_head: str,
    integrated_head: str,
) -> Any:
    old_hash = hashlib.sha256(
        subprocess.check_output(
            ["git", "-C", str(repo), "show", f"{human_commit}:{CONTRACT_PATH}"]
        )
    ).hexdigest()
    migration = migration_event(
        old_hash=old_hash,
        new_hash=state["task_contract_sha256"],
        human_commit=human_commit,
        operational_commit=prior_head,
    )
    integration = IssueWorkflowEvent.create(
        task_id=TASK_ID,
        sequence=4,
        previous_event_id=migration.event_id,
        event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
        from_state=WorkflowState.AGENT_WORKING,
        to_state=WorkflowState.AGENT_READY,
        from_phase=WorkflowPhase.DELIVERY_EVIDENCE,
        to_phase=WorkflowPhase.DELIVERY_EVIDENCE,
        actor_type=WorkflowActor.AGENT,
        actor_id="integration-worker",
        task_contract_sha256=state["task_contract_sha256"],
        occurred_at_utc="2026-08-28T21:00:00Z",
        details={
            "reason": "automation_only_mainline_reintegration",
            "prior_task_head": prior_head,
            "main_head": main_head,
            "integrated_commit": integrated_head,
            "integration_receipt_sha256": "b" * 64,
            "human_validation_preserved_for": human_commit,
        },
    )
    issue_state = SimpleNamespace(
        branch=BRANCH,
        human_handoff_commit=human_commit,
        human_result="pass",
    )
    service = FakeService(events=[migration, integration], state=issue_state)
    controller = object.__new__(ResumableDownstreamTaskController)
    controller.task_id = TASK_ID
    controller.checkout = repo
    controller.command_runner = _default_runner
    controller.workflow = SimpleNamespace(
        issue_workflow=service,
        worker_id="worker",
    )
    controller.state = {}
    controller.last_observation = {
        "task": {
            "task_id": TASK_ID,
            "contract_path": CONTRACT_PATH,
            "task_contract_sha256": state["task_contract_sha256"],
        }
    }
    controller._persist = lambda: None
    return controller


def test_automation_receipt_rebuilds_from_issue_and_git() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-durable-receipt-") as temporary:
        repo, state, _human, human_commit, prior_head = create_migration_fixture(
            Path(temporary)
        )
        main_head, integrated_head = _advance_with_automation_merge(repo, prior_head)
        controller = _receipt_controller(
            repo,
            state=state,
            human_commit=human_commit,
            prior_head=prior_head,
            main_head=main_head,
            integrated_head=integrated_head,
        )
        receipt = _automation_receipt_for(controller, integrated_head)
        require(isinstance(receipt, dict), "durable integration receipt was not rebuilt")
        require(receipt["classification"] == "automation_only", "classification changed")
        require(receipt["human_tested_commit"] == human_commit, "human identity changed")
        require(
            receipt["authority"] == "durable_issue_event_git_reconstruction",
            "receipt did not use durable Issue reconstruction",
        )
        require(
            controller.state["mainline_reintegration"]["receipt_sha256"]
            == receipt["receipt_sha256"],
            "rebuilt receipt was not cached",
        )


def test_automation_receipt_rejects_task_blob_change() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-durable-receipt-tamper-") as temporary:
        repo, state, _human, human_commit, prior_head = create_migration_fixture(
            Path(temporary)
        )
        main_head, integrated_head = _advance_with_automation_merge(
            repo,
            prior_head,
            mutate_task_blob=True,
        )
        controller = _receipt_controller(
            repo,
            state=state,
            human_commit=human_commit,
            prior_head=prior_head,
            main_head=main_head,
            integrated_head=integrated_head,
        )
        try:
            _automation_receipt_for(controller, integrated_head)
        except DownstreamPipelineError as exc:
            require("task-owned blobs" in str(exc), "wrong tamper failure")
        else:
            raise AssertionError("task-owned blob mutation was accepted")


def test_action_narrowing_and_host_validation_are_strict() -> None:
    actions = {
        "prepare_task_checkout": "prepare",
        "read_issue_log": "read",
        "search_repository": "search",
        "run_authoritative_unity_test": "test",
        "integrate_current_main": "integrate",
        "delivery_review_facts": "facts",
        "create_delivery_review_proposal": "proposal",
    }
    observation = {
        "checkout": {"status": "ready"},
        "downstream": {
            "next_action": "run_authoritative_unity_tests",
            "authoritative_test_plan": {
                "required_test_platforms": ["PlayMode"],
                "test_filters": {"PlayMode": "Example.Tests"},
            },
        },
    }
    require(
        allowed_actions_for(observation, [], actions)
        == ("run_authoritative_unity_test",),
        "Unity state still exposes exploratory actions",
    )
    observation["downstream"]["mainline_reintegration"] = {
        "status": "main_commit_unavailable"
    }
    require(
        allowed_actions_for(observation, [], actions) == ("prepare_task_checkout",),
        "missing main object did not route to checkout preparation",
    )

    for prefixes in ([], [""], ["Assets/", "  "]):
        decision = SupervisorDecision(
            TASK_ID,
            "search_repository",
            {"query": "door", "prefixes": prefixes},
            "Search the task files.",
        )
        try:
            decision.validate_arguments(required=("query", "prefixes"))
        except CodexSupervisorError:
            pass
        else:
            raise AssertionError(
                f"unsafe search prefixes passed host validation: {prefixes!r}"
            )


def test_controller_rejects_empty_prefixes() -> None:
    controller = object.__new__(ResumableDownstreamTaskController)
    try:
        controller.search_repository(query="door", prefixes=[])
    except DownstreamPipelineError as exc:
        require("at least one" in str(exc), "wrong empty-prefix controller error")
    else:
        raise AssertionError("empty prefix list reached unrestricted git grep")


def test_history_is_bounded() -> None:
    history = [
        {
            "turn": 1,
            "action": "read_issue_log",
            "rationale": "Inspect the Issue.",
            "result": {
                "status": "ok",
                "events": [{"body": "x" * 100000}],
                "comments": [{"body": "y" * 100000}],
                "content": "secret-content",
            },
        }
    ]
    compact = bounded_history(history)
    rendered = json.dumps(compact)
    require(len(rendered) < 4000, "supervisor history still contains full tool results")
    require("secret-content" not in rendered, "file/Issue content leaked into history")
    require(compact[0]["result"]["events_count"] == 1, "safe event count was lost")


def test_same_state_rejection_streak_releases_after_three() -> None:
    from Pipeline.TaskReviewAgent import downstream_resilience as resilience

    observation = {
        "coordination": {
            "workflow_state": {
                "state_version": 9,
                "state": "agent_working",
                "phase": "delivery_evidence",
            }
        },
        "checkout": {"status": "ready", "head_commit": "c" * 40},
        "downstream": {"next_action": "run_authoritative_unity_test"},
    }
    underlying = SimpleNamespace(last_observation=observation)
    controller = SimpleNamespace(_controller=underlying, _progress=None)
    calls: list[dict[str, Any]] = []
    original = resilience._release_active_lease
    resilience._release_active_lease = lambda _controller, **values: (
        calls.append(values) or True
    )
    try:
        require(
            not _record_same_state_rejection(
                controller,
                action="search_repository",
                error=DownstreamPipelineError("first"),
            ),
            "first rejection released too early",
        )
        require(
            not _record_same_state_rejection(
                controller,
                action="list_repository_files",
                error=DownstreamPipelineError("second"),
            ),
            "second distinct rejection released too early",
        )
        require(
            _record_same_state_rejection(
                controller,
                action="run_authoritative_unity_test",
                error=DownstreamPipelineError("third"),
            ),
            "third same-state rejection did not release",
        )
    finally:
        resilience._release_active_lease = original
    require(len(calls) == 1, "lease release was not invoked exactly once")
    require(
        calls[0]["reason"] == "same_state_action_rejection_streak",
        "wrong release reason",
    )


def test_mainline_drift_is_reported_before_pass_receipt_work() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-mainline-preflight-") as temporary:
        repo, state, _human, _human_commit, task_head = create_migration_fixture(
            Path(temporary)
        )
        git(repo, "switch", "main")
        path = repo / "Pipeline/TaskReviewAgent/advanced.py"
        path.write_text("# advanced main\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "Advance main")
        git(repo, "push", "origin", "main")
        git(repo, "switch", BRANCH)
        controller = SimpleNamespace(
            checkout=repo,
            command_runner=_default_runner,
            _assert_checkout=lambda: None,
        )
        workflow_state = {
            "branch": BRANCH,
            "head_commit": task_head,
            "task_contract_sha256": state["task_contract_sha256"],
        }
        try:
            _assert_current_main_integrated(controller, workflow_state)
        except DownstreamPipelineError as exc:
            require("run integrate_current_main" in str(exc), "drift error was obscured")
        else:
            raise AssertionError("advanced main was treated as integrated")


def test_nsc020_policy_remains_playmode_only() -> None:
    task = json.loads((ROOT / "Tasks/NSC-020.yaml").read_text(encoding="utf-8"))
    task["task_id"] = task["id"]
    task["task_contract_sha256"] = hashlib.sha256(
        (ROOT / "Tasks/NSC-020.yaml").read_bytes()
    ).hexdigest()
    plan = validation_plan_for(ROOT, task)
    require(plan is not None, "NSC-020 policy is missing")
    require(plan["required_test_platforms"] == ["PlayMode"], "NSC-020 policy broadened")


def main() -> int:
    tests = (
        test_human_authority_ignores_agent_template,
        test_automation_receipt_rebuilds_from_issue_and_git,
        test_automation_receipt_rejects_task_blob_change,
        test_action_narrowing_and_host_validation_are_strict,
        test_controller_rejects_empty_prefixes,
        test_history_is_bounded,
        test_same_state_rejection_streak_releases_after_three,
        test_mainline_drift_is_reported_before_pass_receipt_work,
        test_nsc020_policy_remains_playmode_only,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent downstream determinism smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
