"""Composition of real observation, GitHub claim inspection, and checkout preparation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .contracts import TaskReviewContractError, semantic_sha256, validate_task_id
from .coordination import CoordinationObserver, GhCoordinationObserver
from .real_checkout import RealTaskCheckoutManager
from .real_observation import RealTaskObserver


class RealTaskReviewWorkflow:
    """Real early-stage tool surface; path planning and ExecutionCrew remain unavailable."""

    def __init__(
        self,
        *,
        source: Path | str,
        task_id: str,
        checkout_root: Path | str | None,
        worker_id: str,
        coordination_observer: CoordinationObserver | None = None,
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
        self.coordination_observer = coordination_observer or GhCoordinationObserver(
            source_root=self.base_observer.root,
            task_id=self.task_id,
            worker_id=self.worker_id,
        )
        self.action_log: list[str] = []
        self.last_observation: dict[str, Any] | None = None
        self.last_checkout_result: dict[str, Any] | None = None

    def observe_goal_state(self) -> dict[str, Any]:
        self.action_log.append("observe_goal_state")
        base = self.base_observer.observe_goal_state()
        task = base["task"]
        environment = dict(base["environment"])
        try:
            remote_result = subprocess.run(
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
            environment["remote_url"] = None
        else:
            environment["remote_url"] = (
                remote_result.stdout.strip() if remote_result.returncode == 0 else None
            )
        base["environment"] = environment
        expected_branch = self.checkout_manager.expected_branch(base)
        task_ready_for_coordination = (
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
        if task_ready_for_coordination:
            coordination = self.coordination_observer.observe(
                task=task,
                source_head=environment["source_head"],
                checkout_path=str(self.checkout_manager.checkout_path),
                branch=expected_branch,
            )
        else:
            coordination = {
                "status": "not_observed",
                "worker_id": self.worker_id,
                "claim_worker_id": None,
                "issue_number": None,
                "issue_url": None,
                "assignees": [],
                "reasons": [
                    "task must pass deterministic eligibility/dependency checks before "
                    "GitHub coordination is consulted"
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
        observation["checkout_preparation"] = self.last_checkout_result
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
