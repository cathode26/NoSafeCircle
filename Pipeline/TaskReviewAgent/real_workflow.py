"""Compose real task observation, durable Issue workflow, and checkout preparation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .contracts import TaskReviewContractError, semantic_sha256, validate_task_id
from .coordination import CoordinationObserver
from .issue_workflow_store import (
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowStoreError,
)
from .real_checkout import RealTaskCheckoutManager
from .real_observation import RealTaskObserver


class RealTaskReviewWorkflow:
    """Real early-stage tools; path planning and ExecutionCrew remain unavailable."""

    def __init__(
        self,
        *,
        source: Path | str,
        task_id: str,
        checkout_root: Path | str | None,
        worker_id: str,
        coordination_observer: CoordinationObserver | None = None,
        issue_workflow_service: IssueWorkflowService | None = None,
        allow_local_remote_for_tests: bool = False,
    ) -> None:
        self.task_id = validate_task_id(task_id)
        self.source = Path(source)
        self.worker_id = str(worker_id).strip()
        if not self.worker_id:
            raise TaskReviewContractError("worker_id must be non-empty")
        self.base_observer = RealTaskObserver(self.source, self.task_id)
        self.checkout_manager = RealTaskCheckoutManager(
            source_root=self.base_observer.root,
            task_id=self.task_id,
            checkout_root=checkout_root,
            worker_id=self.worker_id,
            allow_local_remote_for_tests=allow_local_remote_for_tests,
        )
        self.legacy_coordination_observer = coordination_observer
        if issue_workflow_service is not None:
            self.issue_workflow = issue_workflow_service
        elif coordination_observer is None:
            self.issue_workflow = IssueWorkflowService(
                backend=GhIssueBackend(source_root=self.base_observer.root),
                task_loader=self._load_committed_task,
                worker_id=self.worker_id,
            )
        else:
            self.issue_workflow = None
        self.action_log: list[str] = []
        self.last_observation: dict[str, Any] | None = None
        self.last_lease_result: dict[str, Any] | None = None
        self.last_checkout_result: dict[str, Any] | None = None
        self.last_handoff_result: dict[str, Any] | None = None

    def _load_committed_task(self, task_id: str) -> dict[str, Any]:
        task_id = validate_task_id(task_id)
        path = f"Tasks/{task_id}.yaml"
        result = subprocess.run(
            ("git", "-C", str(self.base_observer.root), "show", f"HEAD:{path}"),
            cwd=str(self.base_observer.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60.0,
        )
        if result.returncode != 0:
            raise IssueWorkflowStoreError(
                f"committed task contract is missing while reading Issue resources: {path}"
            )
        try:
            task = json.loads(result.stdout.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IssueWorkflowStoreError(
                f"committed task contract is invalid JSON: {path}"
            ) from exc
        if not isinstance(task, dict) or task.get("id") != task_id:
            raise IssueWorkflowStoreError(f"committed task identity mismatch: {path}")
        return {
            **task,
            "task_contract_sha256": hashlib.sha256(result.stdout).hexdigest(),
        }

    def _remote_url(self) -> str | None:
        try:
            result = subprocess.run(
                (
                    "git",
                    "-C",
                    str(self.base_observer.root),
                    "remote",
                    "get-url",
                    "origin",
                ),
                cwd=str(self.base_observer.root),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=60.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    def _task_ready_for_coordination(
        self,
        environment: dict[str, Any],
        task: dict[str, Any],
    ) -> bool:
        return (
            environment.get("ready") is True
            and environment.get("controller_clean") is True
            and environment.get("taskgraph_valid") is True
            and task.get("contract_disposition") == "active"
            and task.get("kind") == "implementation"
            and task.get("execution_scope") == "single_agent"
            and task.get("decomposition_state") == "concrete"
            and task.get("derived_state") == "not_delivered"
            and task.get("dependencies_conformant") is True
        )

    def observe_goal_state(self) -> dict[str, Any]:
        self.action_log.append("observe_goal_state")
        base = self.base_observer.observe_goal_state()
        task = base["task"]
        environment = dict(base["environment"])
        environment["remote_url"] = self._remote_url()
        base["environment"] = environment
        expected_branch = self.checkout_manager.expected_branch(base)

        if self._task_ready_for_coordination(environment, task):
            if self.issue_workflow is not None:
                coordination = self.issue_workflow.observe(self.task_id)
                workflow_status = coordination.get("status")
                coordination = {**coordination, "workflow_status": workflow_status}
                if workflow_status == "agent_working_by_worker":
                    coordination["status"] = "claimed_by_worker"
                elif workflow_status in ("agent_ready_uninitialized", "agent_ready"):
                    coordination["status"] = "available_unassigned"
                elif workflow_status == "agent_working_by_other":
                    coordination["status"] = "claimed_by_other"
            elif self.legacy_coordination_observer is not None:
                coordination = self.legacy_coordination_observer.observe(
                    task=task,
                    source_head=environment["source_head"],
                    checkout_path=str(self.checkout_manager.checkout_path),
                    branch=expected_branch,
                )
            else:
                raise TaskReviewContractError(
                    "no Issue coordination implementation exists"
                )
        else:
            coordination = {
                "status": "not_observed",
                "worker_id": self.worker_id,
                "issue_number": None,
                "issue_url": None,
                "workflow_state": None,
                "reasons": [
                    "task must pass deterministic eligibility/dependency checks before "
                    "Issue workflow is consulted"
                ],
                "authority": "not_observed",
            }

        identity = {
            "environment": environment,
            "task": task,
            "coordination": coordination,
        }
        observation = {
            **base,
            "coordination": coordination,
            "observation_sha256": semantic_sha256(identity),
        }
        checkout = self.checkout_manager.inspect(observation)
        observation["checkout"] = checkout
        observation["checkout_sha256"] = semantic_sha256(checkout)
        observation["agent_lease"] = self.last_lease_result
        observation["checkout_preparation"] = self.last_checkout_result
        observation["human_handoff"] = self.last_handoff_result
        observation["repository_scope_facts"] = {
            "status": "not_observed",
            "authority": "not_yet_implemented",
        }
        observation["accepted_plan_id"] = None
        observation["execution_run"] = None
        self.last_observation = json.loads(
            json.dumps(observation, ensure_ascii=False, allow_nan=False)
        )
        return json.loads(
            json.dumps(self.last_observation, ensure_ascii=False, allow_nan=False)
        )

    def acquire_agent_lease(
        self,
        *,
        planned_approach: str,
        expected_validation: str,
    ) -> dict[str, Any]:
        self.action_log.append("acquire_agent_lease")
        if self.issue_workflow is None:
            raise TaskReviewContractError(
                "the injected legacy coordination observer cannot mutate Issue workflow state"
            )
        if self.last_observation is None:
            raise TaskReviewContractError(
                "acquire_agent_lease requires a current observe_goal_state result"
            )
        task = dict(self.last_observation["task"])
        task["id"] = self.task_id
        result = self.issue_workflow.acquire_agent_lease(
            task=task,
            source_head=self.last_observation["environment"]["source_head"],
            branch=self.checkout_manager.expected_branch(self.last_observation),
            checkout_path=str(self.checkout_manager.checkout_path),
            planned_approach=planned_approach,
            expected_validation=expected_validation,
        )
        self.last_lease_result = json.loads(
            json.dumps(result, ensure_ascii=False, allow_nan=False)
        )
        return json.loads(
            json.dumps(self.last_lease_result, ensure_ascii=False, allow_nan=False)
        )

    def prepare_task_checkout(self) -> dict[str, Any]:
        self.action_log.append("prepare_task_checkout")
        if self.last_observation is None:
            raise TaskReviewContractError(
                "prepare_task_checkout requires a current observe_goal_state result"
            )
        result = self.checkout_manager.prepare(self.last_observation)
        self.last_checkout_result = json.loads(
            json.dumps(result, ensure_ascii=False, allow_nan=False)
        )
        return json.loads(
            json.dumps(self.last_checkout_result, ensure_ascii=False, allow_nan=False)
        )

    def publish_human_handoff(
        self,
        *,
        branch: str,
        head_commit: str,
        implementation_summary: str,
        completed_checks: list[str],
        human_steps: list[str],
        expected_result: str,
    ) -> dict[str, Any]:
        self.action_log.append("publish_human_handoff")
        if self.issue_workflow is None:
            raise TaskReviewContractError("Issue workflow writes are unavailable")
        result = self.issue_workflow.publish_human_handoff(
            task_id=self.task_id,
            branch=branch,
            head_commit=head_commit,
            checkout_path=str(self.checkout_manager.checkout_path),
            implementation_summary=implementation_summary,
            completed_checks=completed_checks,
            human_steps=human_steps,
            expected_result=expected_result,
        )
        self.last_handoff_result = json.loads(
            json.dumps(result, ensure_ascii=False, allow_nan=False)
        )
        return json.loads(
            json.dumps(self.last_handoff_result, ensure_ascii=False, allow_nan=False)
        )
