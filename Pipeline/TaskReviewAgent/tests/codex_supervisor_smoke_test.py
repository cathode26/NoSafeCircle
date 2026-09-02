#!/usr/bin/env python3
"""Deterministic tests for the authenticated Codex CLI goal supervisor."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.schema_validation import (  # noqa: E402
    validate_instance,
    validate_schema,
)
from Pipeline.TaskReviewAgent.codex_supervisor import (  # noqa: E402
    CodexDockerDecisionProvider,
    CodexSupervisorError,
    DEFAULT_SUPERVISOR_TIMEOUT_SECONDS,
    MAX_SUPERVISOR_TIMEOUT_SECONDS,
    SUPERVISOR_DOCKER_TIMEOUT_ALLOWANCE_SECONDS,
    SUPERVISOR_PROVIDER_TURN_LIMIT,
    SupervisorDecision,
    decision_schema,
)
from Pipeline.TaskReviewAgent.contracts import TaskReviewRequest  # noqa: E402
from Pipeline.TaskReviewAgent.openai_downstream import (  # noqa: E402
    run_openai_downstream_pipeline,
)
from Pipeline.TaskReviewAgent.openai_pipeline import (  # noqa: E402
    run_openai_production_pipeline,
)


TASK_ID = "NSC-777"
HEAD = "1" * 40
CONTRACT_HASH = "a" * 64
LEASE_ID = "b" * 64


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_error(action, text: str) -> None:
    try:
        action()
    except CodexSupervisorError as exc:
        require(text in str(exc), f"unexpected error: {exc}")
    else:
        raise AssertionError(f"expected CodexSupervisorError containing {text!r}")


class FakeDecisionProvider:
    def __init__(self, decisions: list[SupervisorDecision]) -> None:
        self.decisions = list(decisions)
        self.calls = 0
        self.turns: list[int] = []
        self.prompts: list[str] = []

    def decide(self, *, task_id, turn, prompt, allowed_actions):
        require(task_id == TASK_ID, "provider received wrong task")
        require(not self.turns or turn > self.turns[-1], "provider turn sequence changed")
        require("CURRENT DETERMINISTIC OBSERVATION" in prompt, "prompt omitted observation")
        if not self.decisions:
            raise AssertionError("goal loop requested an unexpected decision")
        decision = self.decisions.pop(0)
        require(decision.action in allowed_actions, "test decision was not allowed")
        self.calls += 1
        self.turns.append(turn)
        self.prompts.append(prompt)
        return decision


class NeverDecisionProvider:
    def decide(self, **_values):
        raise AssertionError("terminal deterministic state should not call a model")


class FakeProductionController:
    def __init__(self, *, stage: int = 0, checkout_conflict: bool = False) -> None:
        self.stage = stage
        self.checkout_conflict = checkout_conflict
        self.observed_stages: list[int] = []
        self.prepare_calls = 0
        self.workflow = SimpleNamespace(
            worker_id="worker-one",
            base_observer=SimpleNamespace(root=ROOT),
        )

    def _state(self):
        if self.stage == 0:
            return None
        if self.stage == 5:
            return {
                "state": "human_action_required",
                "phase": "unity_runtime_validation",
                "current_actor": "human",
                "worker_id": None,
                "lease_id": None,
                "branch": "nsc-777-synthetic",
                "head_commit": HEAD,
            }
        return {
            "state": "agent_working",
            "phase": "implementation",
            "current_actor": "agent",
            "worker_id": "worker-one",
            "lease_id": LEASE_ID,
            "branch": "nsc-777-synthetic",
            "head_commit": HEAD,
        }

    def observe(self):
        self.observed_stages.append(self.stage)
        state = self._state()
        if self.stage == 0:
            coordination_status = "available_unassigned"
            next_action = "acquire_agent_lease"
            pipeline_status = "agent_ready"
            checkout_status = "missing"
        elif self.stage == 1:
            coordination_status = "claimed_by_worker"
            next_action = "prepare_task_checkout"
            pipeline_status = "agent_working"
            checkout_status = "conflict" if self.checkout_conflict else "missing"
        elif self.stage == 2:
            coordination_status = "claimed_by_worker"
            next_action = "validate_execution_scope"
            pipeline_status = "agent_working"
            checkout_status = "ready"
        elif self.stage == 3:
            coordination_status = "claimed_by_worker"
            next_action = "run_execution_crew"
            pipeline_status = "agent_working"
            checkout_status = "ready"
        elif self.stage == 4:
            coordination_status = "claimed_by_worker"
            next_action = "integrate_commit_push_and_handoff"
            pipeline_status = "agent_working"
            checkout_status = "ready"
        else:
            coordination_status = "human_action_required"
            next_action = "Vincent completes the Issue checklist."
            pipeline_status = "human_action_required"
            checkout_status = "ready"
        return {
            "environment": {"ready": True, "errors": []},
            "task": {
                "task_id": TASK_ID,
                "contract_disposition": "active",
                "kind": "implementation",
                "execution_scope": "single_agent",
                "decomposition_state": "concrete",
                "derived_state": "not_delivered",
                "dependencies_conformant": True,
            },
            "coordination": {
                "status": coordination_status,
                "issue_url": "https://example.invalid/issues/777" if self.stage else None,
                "workflow_state": state,
                "reasons": [],
            },
            "checkout": {"status": checkout_status},
            "production_pipeline": {
                "status": pipeline_status,
                "next_action": next_action,
            },
        }

    def acquire_agent_lease(self, *, planned_approach, expected_validation):
        require(planned_approach, "approach was empty")
        require(expected_validation, "validation was empty")
        self.stage = 1
        return {"status": "agent_working", "lease_id": LEASE_ID}

    def prepare_task_checkout(self):
        require(self.stage == 1, "checkout was prepared out of order")
        self.prepare_calls += 1
        self.stage = 2
        return {"status": "ready", "branch": "nsc-777-synthetic"}

    def repository_facts(self):
        return {"status": "ready"}

    def list_repository_files(self, **values):
        return values

    def search_repository(self, **values):
        return values

    def read_repository_file(self, **values):
        return values

    def latest_human_feedback(self):
        return None

    def validate_execution_scope(self, **values):
        require(self.stage == 2, "scope was validated out of order")
        require(values["existing_implementation_paths"], "implementation scope was empty")
        require(values["existing_test_paths"], "test scope was empty")
        self.stage = 3
        return {"accepted": True, "plan_id": "plan-777", "reasons": []}

    def run_execution_crew(self, **values):
        require(self.stage == 3, "ExecutionCrew ran out of order")
        require(values["plan_id"] == "plan-777", "wrong plan ID")
        self.stage = 4
        return {"crew_status": "review_ready", "run_id": "run-777"}

    def integrate_commit_push_and_handoff(self, **values):
        require(self.stage == 4, "candidate integration ran out of order")
        require(values["run_id"] == "run-777", "wrong run ID")
        require(values["human_steps"], "human steps were empty")
        self.stage = 5
        return {
            "status": "human_action_required",
            "branch": "nsc-777-synthetic",
            "commit": HEAD,
        }

    def record_pipeline_blocker(self, **_values):
        raise AssertionError("happy-path test should not record a blocker")


class FakeDownstreamController:
    def __init__(self) -> None:
        self.workflow = SimpleNamespace(
            worker_id="worker-two",
            base_observer=SimpleNamespace(root=ROOT),
        )

    def observe(self):
        return {
            "environment": {"ready": True, "errors": []},
            "coordination": {
                "status": "blocked",
                "issue_url": "https://example.invalid/issues/777",
                "reasons": [],
                "workflow_state": {
                    "state": "blocked",
                    "phase": "delivery_evidence",
                    "current_actor": "human",
                    "branch": "nsc-777-synthetic",
                    "head_commit": HEAD,
                },
            },
            "downstream": {
                "next_action": "vincent_reviews_delivery_proposal",
                "receipt": {
                    "proposal_sha256": "c" * 64,
                    "pull_request_url": None,
                },
            },
        }


class RecordingProgress:
    def __init__(self) -> None:
        self.heartbeats: list[tuple[str, dict]] = []
        self.events: list[tuple[str, dict]] = []

    def emit(self, event, _message, **fields):
        self.events.append((event, fields))

    @contextmanager
    def heartbeat(self, event, _message, **fields):
        self.heartbeats.append((event, fields))
        yield

    def finish(self, _status, **_fields):
        return None


def decision(action: str, arguments: dict) -> SupervisorDecision:
    return SupervisorDecision(TASK_ID, action, arguments, f"Use {action} next.")


def test_decision_contract() -> None:
    schema = decision_schema(("acquire_agent_lease", "prepare_task_checkout"))
    validate_schema(schema)
    value = {
        "schema_version": "1.0",
        "task_id": TASK_ID,
        "action": "acquire_agent_lease",
        "arguments": {
            "planned_approach": "Implement the bounded owner behavior.",
            "expected_validation": "Run the exact Unity regression test.",
        },
        "rationale": "The task is eligible and unclaimed.",
    }
    validate_instance(value, schema)
    parsed = SupervisorDecision.from_dict(
        value,
        expected_task_id=TASK_ID,
        allowed_actions=("acquire_agent_lease", "prepare_task_checkout"),
    )
    parsed.validate_arguments(
        required=("planned_approach", "expected_validation")
    )
    expect_error(
        lambda: SupervisorDecision.from_dict(
            {**value, "task_id": "NSC-778"},
            expected_task_id=TASK_ID,
            allowed_actions=("acquire_agent_lease",),
        ),
        "changed task identity",
    )
    expect_error(
        lambda: decision("prepare_task_checkout", {"summary": "not allowed"}).validate_arguments(),
        "extras",
    )


def test_docker_provider_envelope() -> None:
    captured = {}

    def runner(command, *, cwd, input_bytes, timeout_seconds):
        captured.update(
            {
                "command": tuple(command),
                "cwd": cwd,
                "request": json.loads(input_bytes.decode("utf-8")),
                "timeout_seconds": timeout_seconds,
            }
        )
        response = {
            "schema_version": "1.0",
            "structured_output": {
                "schema_version": "1.0",
                "task_id": TASK_ID,
                "action": "prepare_task_checkout",
                "arguments": {},
                "rationale": "The deterministic state requires checkout preparation.",
            },
            "usage": None,
        }
        return subprocess.CompletedProcess(
            command,
            0,
            (json.dumps(response) + "\n").encode("utf-8"),
            b"",
        )

    prior_timeout = os.environ.pop("NSC_TASK_SUPERVISOR_TIMEOUT_SECONDS", None)
    try:
        provider = CodexDockerDecisionProvider(source=ROOT, command_runner=runner)
        result = provider.decide(
            task_id=TASK_ID,
            turn=1,
            prompt="Choose checkout preparation from deterministic state.",
            allowed_actions=("prepare_task_checkout",),
        )
    finally:
        if prior_timeout is not None:
            os.environ["NSC_TASK_SUPERVISOR_TIMEOUT_SECONDS"] = prior_timeout
    require(result.action == "prepare_task_checkout", "provider changed action")
    require("codex-supervisor" in captured["command"], "wrong Docker service")
    require(captured["request"]["model"], "model was not supplied")
    require("api_key" not in json.dumps(captured["request"]).casefold(), "request exposed an API key")
    require(
        captured["request"]["provider_turn_limit"] == SUPERVISOR_PROVIDER_TURN_LIMIT <= 8,
        "supervisor provider turn budget is not bounded",
    )
    require(
        captured["request"]["timeout_seconds"]
        == DEFAULT_SUPERVISOR_TIMEOUT_SECONDS
        <= 240,
        "default supervisor provider timeout is too large",
    )
    require(
        captured["timeout_seconds"]
        == DEFAULT_SUPERVISOR_TIMEOUT_SECONDS
        + SUPERVISOR_DOCKER_TIMEOUT_ALLOWANCE_SECONDS
        <= 300,
        "outer Docker timeout is not a few-minute ceiling",
    )


def test_supervisor_timeout_configuration_is_lower_only_and_fail_closed() -> None:
    prior_timeout = os.environ.get("NSC_TASK_SUPERVISOR_TIMEOUT_SECONDS")
    try:
        os.environ["NSC_TASK_SUPERVISOR_TIMEOUT_SECONDS"] = "90"
        lowered = CodexDockerDecisionProvider(source=ROOT)
        require(lowered.timeout_seconds == 90.0, "environment did not lower timeout")

        for invalid, expected in (
            ("not-a-number", "finite number"),
            ("0", "positive"),
            ("-1", "positive"),
            ("nan", "finite number"),
            (str(MAX_SUPERVISOR_TIMEOUT_SECONDS + 1), "may not exceed"),
        ):
            os.environ["NSC_TASK_SUPERVISOR_TIMEOUT_SECONDS"] = invalid
            expect_error(
                lambda: CodexDockerDecisionProvider(source=ROOT),
                expected,
            )
    finally:
        if prior_timeout is None:
            os.environ.pop("NSC_TASK_SUPERVISOR_TIMEOUT_SECONDS", None)
        else:
            os.environ["NSC_TASK_SUPERVISOR_TIMEOUT_SECONDS"] = prior_timeout


def test_production_goal_loop() -> None:
    controller = FakeProductionController()
    provider = FakeDecisionProvider(
        [
            decision(
                "acquire_agent_lease",
                {
                    "planned_approach": "Implement the crossing owner and its focused tests.",
                    "expected_validation": "Run the task-owned Unity tests and human checklist.",
                },
            ),
            decision(
                "validate_execution_scope",
                {
                    "existing_implementation_paths": ["Assets/Feature.cs"],
                    "new_implementation_paths": [],
                    "existing_test_paths": ["Assets/Tests/FeatureTests.cs"],
                    "new_test_paths": [],
                },
            ),
            decision("run_execution_crew", {"plan_id": "plan-777"}),
            decision(
                "integrate_commit_push_and_handoff",
                {
                    "run_id": "run-777",
                    "implementation_summary": "Added crossing state and reset coverage.",
                    "human_steps": [
                        "Open the canonical checkout.",
                        "Enter Play Mode and cross the open doorway.",
                    ],
                    "expected_result": "Crossing is published only after forward-side traversal.",
                },
            ),
        ]
    )
    outcome = run_openai_production_pipeline(
        TaskReviewRequest(TASK_ID),
        controller,
        max_turns=10,
        decision_provider=provider,
    )
    require(outcome["status"] == "human_action_required", "goal loop did not reach human handoff")
    require(outcome["commit"] == HEAD, "goal loop changed commit identity")
    require(provider.calls == 4, "mechanical checkout preparation called the provider")
    require(provider.turns == [1, 3, 4, 5], f"wrong semantic decision turns: {provider.turns}")
    require(controller.prepare_calls == 1, "checkout preparation did not run exactly once")
    require(
        controller.observed_stages == [0, 1, 2, 3, 4, 5],
        f"pipeline did not re-observe after direct preparation: {controller.observed_stages}",
    )
    require(
        "Deterministic host selection followed production_pipeline.next_action"
        in provider.prompts[1],
        "supervisor history omitted the deterministic host action",
    )


def test_conflicted_checkout_preparation_bypasses_supervisor() -> None:
    controller = FakeProductionController(stage=1, checkout_conflict=True)
    provider = FakeDecisionProvider(
        [
            decision(
                "validate_execution_scope",
                {
                    "existing_implementation_paths": ["Assets/Feature.cs"],
                    "new_implementation_paths": [],
                    "existing_test_paths": ["Assets/Tests/FeatureTests.cs"],
                    "new_test_paths": [],
                },
            ),
            decision("run_execution_crew", {"plan_id": "plan-777"}),
            decision(
                "integrate_commit_push_and_handoff",
                {
                    "run_id": "run-777",
                    "implementation_summary": "Added crossing state and reset coverage.",
                    "human_steps": ["Open the checkout.", "Verify the behavior in Play Mode."],
                    "expected_result": "The updated behavior is visible without Unity errors.",
                },
            ),
        ]
    )
    progress = RecordingProgress()
    outcome = run_openai_production_pipeline(
        TaskReviewRequest(TASK_ID),
        controller,
        max_turns=8,
        decision_provider=provider,
        progress=progress,
    )
    require(outcome["status"] == "human_action_required", "conflict recovery did not finish")
    require(provider.calls == 3, "conflicted checkout preparation called the provider")
    require(provider.turns == [2, 3, 4], f"wrong post-recovery turns: {provider.turns}")
    require(controller.prepare_calls == 1, "conflicted checkout was not prepared once")
    require(
        controller.observed_stages == [1, 2, 3, 4, 5],
        f"conflict recovery did not re-observe: {controller.observed_stages}",
    )
    require(
        any(
            event == "pipeline_action"
            and fields.get("action") == "prepare_task_checkout"
            and fields.get("selection") == "deterministic_host"
            for event, fields in progress.heartbeats
        ),
        "direct checkout preparation omitted the normal action heartbeat",
    )
    require(
        any(
            event == "action_completed"
            and fields.get("action") == "prepare_task_checkout"
            and fields.get("selection") == "deterministic_host"
            for event, fields in progress.events
        ),
        "direct checkout preparation omitted completion logging",
    )


def test_downstream_terminal_without_model() -> None:
    outcome = run_openai_downstream_pipeline(
        TaskReviewRequest(TASK_ID),
        FakeDownstreamController(),
        max_turns=10,
        decision_provider=NeverDecisionProvider(),
    )
    require(outcome["status"] == "human_delivery_review", "human review state was not recognized")
    require(outcome["blockers"] == [], "human review returned blockers")


def main() -> int:
    tests = (
        test_decision_contract,
        test_docker_provider_envelope,
        test_supervisor_timeout_configuration_is_lower_only_and_fail_closed,
        test_production_goal_loop,
        test_conflicted_checkout_preparation_bypasses_supervisor,
        test_downstream_terminal_without_model,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent Codex supervisor tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
