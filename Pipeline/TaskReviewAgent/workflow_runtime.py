"""Workflow observation that preserves managed Issue authority after delivery evidence."""

from __future__ import annotations

import json
from typing import Any

from .contracts import semantic_sha256
from .real_workflow import RealTaskReviewWorkflow


class DurableIssueTaskReviewWorkflow(RealTaskReviewWorkflow):
    """Continue an existing managed Issue even after the task leaves not_delivered.

    Fresh task initialization retains every original eligibility and dependency gate.
    This override only changes observation when a valid managed Issue already exists,
    which is required after an evidence commit makes TaskGraph derive `conformant`
    while the operational Issue still has PR merge/closeout work remaining.
    """

    def observe_goal_state(self) -> dict[str, Any]:
        observation = super().observe_goal_state()
        coordination = observation.get("coordination") or {}
        if (
            self.issue_workflow is None
            or coordination.get("status") != "not_observed"
        ):
            return observation

        managed = self.issue_workflow.observe(self.task_id)
        if not isinstance(managed.get("workflow_state"), dict):
            # No initialized workflow exists, so fresh-task eligibility remains the
            # sole authority for whether the Issue may be consulted or created.
            return observation

        workflow_status = managed.get("status")
        managed = {**managed, "workflow_status": workflow_status}
        if workflow_status == "agent_working_by_worker":
            managed["status"] = "claimed_by_worker"
        elif workflow_status == "agent_working_by_other":
            managed["status"] = "claimed_by_other"
        elif workflow_status in ("agent_ready_uninitialized", "agent_ready"):
            managed["status"] = "available_unassigned"

        observation["coordination"] = managed
        identity = {
            "environment": observation["environment"],
            "task": observation["task"],
            "coordination": managed,
        }
        observation["observation_sha256"] = semantic_sha256(identity)
        checkout = self.checkout_manager.inspect(observation)
        observation["checkout"] = checkout
        observation["checkout_sha256"] = semantic_sha256(checkout)
        observation["agent_lease"] = self.last_lease_result
        observation["checkout_preparation"] = self.last_checkout_result
        observation["human_handoff"] = self.last_handoff_result
        self.last_observation = json.loads(
            json.dumps(observation, ensure_ascii=False, allow_nan=False)
        )
        return json.loads(
            json.dumps(self.last_observation, ensure_ascii=False, allow_nan=False)
        )
