"""Mainline reintegration with mandatory revalidation for downstream tasks.

Codex may select the bounded action, but host Python owns classification, Git
integration, validation, push, and durable Issue transitions.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

from .contracts import TASK_REVIEW_SCHEMA_VERSION, semantic_sha256
from .downstream_pipeline import (
    _SHA40,
    DownstreamPipelineError,
    _decode,
    _git,
    _git_text,
    _run,
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


INTEGRATION_RECEIPT_VERSION = "1.0"
_AUTOMATION_ONLY_PREFIXES = (
    ".github/workflows/",
    "Pipeline/TaskReviewAgent/",
    "Docs/AI-Pipeline/",
)
_AUTOMATION_ONLY_FILES = frozenset({"AGENTS.md", "compose.override.yaml"})
_SENSITIVE_PREFIXES = (
    "Assets/",
    "Packages/",
    "ProjectSettings/",
    "Tasks/",
    "Docs/GDD/",
    "Docs/Engineering/",
    "Pipeline/Testing/",
    "Pipeline/TaskGraph/",
    "Pipeline/TaskDelivery/",
)
_STALE_RECEIPT_KEYS = (
    "validation_manifests",
    "implementation_commit",
    "implementation_tree",
    "human_validation",
    "draft_path",
    "draft_sha256",
    "proposal_path",
    "proposal_sha256",
    "proposal_revision",
    "approved_review_path",
    "approved_review_sha256",
    "delivery_spec_path",
    "delivery_spec_sha256",
    "record_id",
    "record_path",
    "created_paths",
    "evidence_commit",
    "evidence_tree",
    "conformance_record_id",
    "pull_request_number",
    "pull_request_url",
    "pull_request_head",
    "merged_commit",
)
_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _normalize_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = PurePosixPath(value.strip().replace("\\", "/"))
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return None
    return path.as_posix()


def _normalized_paths(values: Iterable[Any]) -> list[str]:
    result = {_normalize_path(item) for item in values}
    result.discard(None)
    return sorted(result, key=str.casefold)


def _paths_from_nul(data: bytes, *, label: str) -> list[str]:
    result: set[str] = set()
    for raw in data.split(b"\0"):
        if not raw:
            continue
        path = _normalize_path(_decode(raw, label))
        if path is None:
            raise DownstreamPipelineError(f"{label} returned an unsafe repository path")
        result.add(path)
    return sorted(result, key=str.casefold)


def _resource_paths(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        text = value
        for prefix in ("repo-file:", "unity-scene:"):
            if text.startswith(prefix):
                text = text[len(prefix) :]
                break
        result.append(text)
    return _normalized_paths(result)


def _is_automation_only_path(path: str) -> bool:
    folded = path.casefold()
    if folded in {item.casefold() for item in _AUTOMATION_ONLY_FILES}:
        return True
    return any(
        folded.startswith(prefix.casefold())
        for prefix in _AUTOMATION_ONLY_PREFIXES
    )


def classify_mainline_drift(
    *,
    main_changed_paths: Iterable[str],
    task_changed_paths: Iterable[str],
    exclusive_resources: Iterable[str],
    task_contract_path: str,
) -> dict[str, Any]:
    """Classify drift deterministically and fail closed for unknown paths."""

    main_paths = _normalized_paths(main_changed_paths)
    task_paths = _normalized_paths(task_changed_paths)
    exclusive_paths = _normalized_paths(exclusive_resources)
    contract_path = _normalize_path(task_contract_path)
    main_set = set(main_paths)
    overlap = sorted(main_set & set(task_paths), key=str.casefold)
    exclusive_overlap = sorted(main_set & set(exclusive_paths), key=str.casefold)
    non_automation = sorted(
        [path for path in main_paths if not _is_automation_only_path(path)],
        key=str.casefold,
    )
    contract_changed = bool(contract_path and contract_path in main_set)
    sensitive_paths = sorted(
        [
            path
            for path in main_paths
            if any(
                path.casefold().startswith(prefix.casefold())
                for prefix in _SENSITIVE_PREFIXES
            )
        ],
        key=str.casefold,
    )

    reasons: list[str] = []
    if overlap:
        reasons.append("main changed paths also changed by the task branch")
    if exclusive_overlap:
        reasons.append("main changed task-exclusive resources")
    if contract_changed:
        reasons.append("main changed the task contract")
    if non_automation:
        reasons.append("main changed paths outside the automation-only allowlist")

    automation_only = bool(main_paths) and not (
        overlap or exclusive_overlap or contract_changed or non_automation
    )
    return {
        "classification": (
            "automation_only" if automation_only else "runtime_sensitive"
        ),
        # A merge creates a new commit even when main changed only automation
        # files. Human approval is commit-bound, so every integration must be
        # tested and approved as the exact integrated commit.
        "human_revalidation_required": True,
        "main_changed_paths": main_paths,
        "task_changed_paths": task_paths,
        "overlap_paths": overlap,
        "exclusive_overlap_paths": exclusive_overlap,
        "sensitive_paths": sensitive_paths,
        "non_automation_paths": non_automation,
        "task_contract_changed": contract_changed,
        "reasons": reasons,
        "authority": "deterministic_mainline_drift_classifier",
    }


def _workflow_state(observation: Mapping[str, Any]) -> dict[str, Any]:
    coordination = observation.get("coordination")
    if not isinstance(coordination, Mapping):
        return {}
    state = coordination.get("workflow_state")
    return dict(state) if isinstance(state, Mapping) else {}


def _mainline_status(
    controller: Any,
    observation: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    phase = state.get("phase")
    if (
        state.get("state") != WorkflowState.AGENT_WORKING.value
        or phase not in (
            WorkflowPhase.DELIVERY_EVIDENCE.value,
            WorkflowPhase.MERGE_CLOSEOUT.value,
        )
        or state.get("worker_id") != controller.workflow.worker_id
    ):
        return {"status": "not_applicable"}
    checkout = observation.get("checkout")
    if not isinstance(checkout, Mapping) or checkout.get("status") != "ready":
        return {"status": "checkout_not_ready"}
    task_head = state.get("head_commit")
    recovery = checkout.get("persisted_evidence_recovery")
    if phase == WorkflowPhase.MERGE_CLOSEOUT.value and isinstance(recovery, Mapping):
        task_head = recovery.get("evidence_commit")
    environment = observation.get("environment")
    main_head = (
        environment.get("source_head")
        if isinstance(environment, Mapping)
        else None
    )
    if not isinstance(task_head, str) or not _SHA40.fullmatch(task_head):
        return {"status": "invalid_task_head"}
    if not isinstance(main_head, str) or not _SHA40.fullmatch(main_head):
        return {"status": "invalid_main_head"}
    if task_head == main_head:
        return {
            "status": "no_task_delta",
            "task_head": task_head,
            "main_head": main_head,
        }
    ancestry = _git(
        controller.command_runner,
        controller.checkout,
        "merge-base",
        "--is-ancestor",
        main_head,
        task_head,
        check=False,
    )
    if ancestry.returncode == 0:
        return {
            "status": "integrated",
            "task_head": task_head,
            "main_head": main_head,
        }
    if ancestry.returncode != 1:
        return {
            "status": "main_commit_unavailable",
            "task_head": task_head,
            "main_head": main_head,
        }
    return {
        "status": "required",
        "task_head": task_head,
        "main_head": main_head,
        "authority": "git_ancestry",
    }


def _diff_paths(controller: Any, base: str, head: str, *, label: str) -> list[str]:
    result = _git(
        controller.command_runner,
        controller.checkout,
        "diff",
        "--name-only",
        "-z",
        base,
        head,
        "--",
    )
    return _paths_from_nul(result.stdout, label=label)


def _remote_branch_head(controller: Any, branch: str) -> str | None:
    values = _git_text(
        controller.command_runner,
        controller.checkout,
        "ls-remote",
        "--heads",
        "origin",
        f"refs/heads/{branch}",
        check=False,
    ).split()
    return values[0] if values else None


def _object_id_at(controller: Any, commit: str, path: str) -> str | None:
    result = _git(
        controller.command_runner,
        controller.checkout,
        "rev-parse",
        "--verify",
        f"{commit}:{path}",
        check=False,
    )
    if result.returncode != 0:
        return None
    value = _decode(result.stdout or b"", "git object identity").strip()
    return value if _SHA40.fullmatch(value) else None


def _restore_unpushed_head(controller: Any, task_head: str) -> None:
    _git(
        controller.command_runner,
        controller.checkout,
        "merge",
        "--abort",
        check=False,
    )
    _git(
        controller.command_runner,
        controller.checkout,
        "reset",
        "--hard",
        task_head,
    )
    status = _git_text(
        controller.command_runner,
        controller.checkout,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    head = _git_text(
        controller.command_runner,
        controller.checkout,
        "rev-parse",
        "HEAD",
    )
    if status or head != task_head:
        raise DownstreamPipelineError(
            "failed integration could not restore the exact original task head"
        )


def _block_current_lease(
    controller: Any,
    *,
    reason: str,
    details: Mapping[str, Any],
) -> dict[str, Any]:
    service = controller.workflow.issue_workflow
    if service is None:
        raise DownstreamPipelineError("Issue workflow is unavailable")
    snapshot = service.find(controller.task_id)
    if snapshot is None or not snapshot.valid or snapshot.state is None:
        raise DownstreamPipelineError(
            "mainline integration blocker requires a valid Issue"
        )
    state = snapshot.state
    if (
        state.state is not WorkflowState.AGENT_WORKING
        or state.worker_id != controller.workflow.worker_id
    ):
        raise DownstreamPipelineError(
            "mainline integration blocker requires this worker's lease"
        )
    next_state, event = transition(
        state,
        event_type=WorkflowEventType.BLOCKED,
        actor_type=WorkflowActor.AGENT,
        actor_id=controller.workflow.worker_id,
        to_state=WorkflowState.BLOCKED,
        to_phase=state.phase,
        details={"reason": reason, **dict(details)},
        now=utc_now(),
    )
    service.backend.add_comment(
        snapshot.issue_number,
        render_event_comment(
            event,
            "\n".join(
                (
                    "Mainline reintegration stopped without rewriting the remote task branch.",
                    "",
                    f"- **Reason:** {reason}",
                    "",
                    "Resolve the recorded identities before retrying.",
                )
            ),
        ),
    )
    service.backend.update_issue(
        snapshot.issue_number,
        body=update_issue_body(
            snapshot.body,
            next_state,
            next_action=(
                "Resolve the mainline reintegration blocker recorded in the latest event."
            ),
        ),
        labels=labels_for_state(next_state.state, snapshot.labels),
        assignees=[service.assignee],
    )
    verified = service.verify_post_mutation_state(
        controller.task_id,
        next_state,
        transition_name="mainline integration blocker",
    )
    return {"status": "blocked", "reason": reason, **verified.to_dict()}


def _invalidate_downstream_receipt(
    controller: Any,
    receipt: Mapping[str, Any],
) -> None:
    for key in _STALE_RECEIPT_KEYS:
        controller.state.pop(key, None)
    controller.state["validation_manifests"] = []
    controller.state["delivery_base_commit"] = receipt["main_head"]
    controller.state["mainline_reintegration"] = _copy(receipt)
    controller._persist()


def _advance_automation_only_issue(
    controller: Any,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    service = controller.workflow.issue_workflow
    if service is None:
        raise DownstreamPipelineError("Issue workflow is unavailable")
    snapshot = service.find(controller.task_id)
    if snapshot is None or not snapshot.valid or snapshot.state is None:
        raise DownstreamPipelineError(
            "automation-only reintegration requires a valid Issue"
        )
    state = snapshot.state
    if (
        state.state is not WorkflowState.AGENT_WORKING
        or state.worker_id != controller.workflow.worker_id
        or state.phase is not WorkflowPhase.DELIVERY_EVIDENCE
    ):
        raise DownstreamPipelineError(
            "automation-only reintegration requires this worker's delivery lease"
        )
    next_state, event = transition(
        state,
        event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
        actor_type=WorkflowActor.AGENT,
        actor_id=controller.workflow.worker_id,
        to_state=WorkflowState.AGENT_READY,
        to_phase=WorkflowPhase.DELIVERY_EVIDENCE,
        details={
            "reason": "automation_only_mainline_reintegration",
            "prior_task_head": receipt["prior_task_head"],
            "main_head": receipt["main_head"],
            "integrated_commit": receipt["integrated_commit"],
            "integration_receipt_sha256": receipt["receipt_sha256"],
            "human_validation_preserved_for": receipt["human_tested_commit"],
        },
        now=utc_now(),
    )
    next_state = replace(next_state, head_commit=receipt["integrated_commit"])
    service.backend.add_comment(
        snapshot.issue_number,
        render_event_comment(
            event,
            "\n".join(
                (
                    "Current main was merged into the task branch with history preserved.",
                    "",
                    f"- **Prior task head:** `{receipt['prior_task_head']}`",
                    f"- **Integrated main:** `{receipt['main_head']}`",
                    f"- **New task head:** `{receipt['integrated_commit']}`",
                    "- **Classification:** `automation_only`",
                    f"- **Original human-tested commit:** `{receipt['human_tested_commit']}`",
                    "",
                    "The original human PASS remains attached only to its original commit. "
                    "Fresh authoritative Unity validation is required on the integrated head.",
                )
            ),
        ),
    )
    service.backend.update_issue(
        snapshot.issue_number,
        body=update_issue_body(
            snapshot.body,
            next_state,
            next_action=(
                "A generic agent may reacquire delivery evidence and run authoritative "
                "Unity validation on the integrated commit."
            ),
        ),
        labels=labels_for_state(next_state.state, snapshot.labels),
        assignees=[service.assignee],
    )
    service.verify_post_mutation_state(
        controller.task_id,
        next_state,
        transition_name="automation-only integration state",
    )

    controller.workflow.observe_goal_state()
    reacquired = controller.workflow.acquire_agent_lease(
        planned_approach=(
            "Resume delivery evidence at the automation-only integrated head and run "
            "authoritative validation before drafting evidence."
        ),
        expected_validation=(
            "Unity manifests identify the integrated commit and delivery records "
            "distinguish it from the original human-tested commit."
        ),
    )
    return {"status": "integrated_automation_only", "lease": reacquired}


def _automation_receipt_for(
    controller: Any,
    commit: str,
) -> dict[str, Any] | None:
    receipt = controller.state.get("mainline_reintegration")
    if not isinstance(receipt, Mapping):
        return None
    payload = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if (
        receipt.get("classification") != "automation_only"
        or receipt.get("integrated_commit") != commit
        or receipt.get("receipt_sha256") != semantic_sha256(payload)
    ):
        return None
    return dict(receipt)


def _patched_next_action(
    self: Any,
    observation: Mapping[str, Any],
    state: Mapping[str, Any] | None,
) -> str:
    action = _ORIGINALS["next_action"](self, observation, state)
    if state is None:
        return action
    status = _mainline_status(self, observation, state)
    self._mainline_reintegration_status = status
    if status.get("status") == "required":
        return "integrate_current_main"
    return action


def _patched_observe(self: Any) -> dict[str, Any]:
    observation = _ORIGINALS["observe"](self)
    downstream = observation.get("downstream")
    status = getattr(self, "_mainline_reintegration_status", None)
    if isinstance(downstream, dict) and isinstance(status, Mapping):
        downstream["mainline_reintegration"] = _copy(status)
    return observation


def _patched_assert_human_tested_head(
    self: Any,
    state: Mapping[str, Any],
) -> None:
    self._assert_checkout()
    head = _git_text(self.command_runner, self.checkout, "rev-parse", "HEAD")
    branch = _git_text(
        self.command_runner,
        self.checkout,
        "branch",
        "--show-current",
    )
    if head != state.get("head_commit") or branch != state.get("branch"):
        raise DownstreamPipelineError(
            "checkout differs from the exact branch/commit recorded in the Issue"
        )
    human = self._latest_human_validation()
    if (
        human is None
        or human.get("result") != "pass"
        or human.get("tested_commit") != head
    ):
        raise DownstreamPipelineError("exact human PASS for checkout HEAD is missing")

    _git(
        self.command_runner,
        self.checkout,
        "fetch",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        timeout_seconds=900.0,
    )
    current_main = _git_text(
        self.command_runner,
        self.checkout,
        "rev-parse",
        "origin/main",
    )
    if (
        _git(
            self.command_runner,
            self.checkout,
            "merge-base",
            "--is-ancestor",
            current_main,
            head,
            check=False,
        ).returncode
        != 0
    ):
        raise DownstreamPipelineError(
            "origin/main advanced beyond the validated integration; run integrate_current_main"
        )
    receipt = _automation_receipt_for(self, head)
    base_commit = receipt.get("main_head") if receipt is not None else current_main
    existing = self.state.get("delivery_base_commit")
    if existing is not None and existing != base_commit:
        raise DownstreamPipelineError(
            "delivery base changed after authoritative work began; reintegrate main"
        )
    if existing is None:
        self.state["delivery_base_commit"] = base_commit
        self._persist()


def _patched_human_validation_artifact(
    self: Any,
    commit: str,
) -> dict[str, Any]:
    return _ORIGINALS["human_validation_artifact"](self, commit)


def _integrate_current_main(self: Any) -> dict[str, Any]:
    observation = self.observe()
    workflow_state = _workflow_state(observation)
    phase = workflow_state.get("phase")
    if (
        workflow_state.get("state") != WorkflowState.AGENT_WORKING.value
        or workflow_state.get("worker_id") != self.workflow.worker_id
        or phase not in (
            WorkflowPhase.DELIVERY_EVIDENCE.value,
            WorkflowPhase.MERGE_CLOSEOUT.value,
        )
    ):
        raise DownstreamPipelineError(
            "mainline integration requires this worker's active downstream lease"
        )
    checkout_state = observation.get("checkout")
    if not isinstance(checkout_state, Mapping) or checkout_state.get("status") != "ready":
        raise DownstreamPipelineError("mainline integration requires a ready checkout")
    self._assert_checkout()
    task_head = _git_text(
        self.command_runner,
        self.checkout,
        "rev-parse",
        "HEAD",
    )
    branch = _git_text(
        self.command_runner,
        self.checkout,
        "branch",
        "--show-current",
    )
    recovery = checkout_state.get("persisted_evidence_recovery")
    recovered_evidence = (
        phase == WorkflowPhase.MERGE_CLOSEOUT.value
        and isinstance(recovery, Mapping)
        and recovery.get("status") == "recovered"
        and recovery.get("evidence_commit") == task_head
        and recovery.get("implementation_commit") == workflow_state.get("head_commit")
        and self.state.get("evidence_commit") == task_head
        and self.state.get("implementation_commit") == workflow_state.get("head_commit")
    )
    if (
        (task_head != workflow_state.get("head_commit") and not recovered_evidence)
        or branch != workflow_state.get("branch")
    ):
        raise DownstreamPipelineError(
            "integration requires the exact Issue branch and head"
        )
    human = self._latest_human_validation()
    expected_human_commit = (
        str(self.state.get("implementation_commit"))
        if recovered_evidence
        else task_head
    )
    if (
        human is None
        or human.get("result") != "pass"
        or human.get("tested_commit") != expected_human_commit
    ):
        raise DownstreamPipelineError(
            "integration requires the recorded exact human PASS"
        )

    _git(
        self.command_runner,
        self.checkout,
        "fetch",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        timeout_seconds=900.0,
    )
    main_head = _git_text(
        self.command_runner,
        self.checkout,
        "rev-parse",
        "origin/main",
    )
    if not _SHA40.fullmatch(main_head):
        raise DownstreamPipelineError("origin/main did not resolve to a commit")
    if (
        _git(
            self.command_runner,
            self.checkout,
            "merge-base",
            "--is-ancestor",
            main_head,
            task_head,
            check=False,
        ).returncode
        == 0
    ):
        return {
            "status": "already_integrated",
            "task_head": task_head,
            "main_head": main_head,
        }
    if (
        _git(
            self.command_runner,
            self.checkout,
            "merge-base",
            "--is-ancestor",
            task_head,
            main_head,
            check=False,
        ).returncode
        == 0
    ):
        return _block_current_lease(
            self,
            reason="current main already contains the task head",
            details={"task_head": task_head, "main_head": main_head},
        )
    remote_head = _remote_branch_head(self, branch)
    if remote_head != task_head:
        return _block_current_lease(
            self,
            reason="remote task branch moved before integration",
            details={
                "expected_remote_head": task_head,
                "actual_remote_head": remote_head,
            },
        )

    merge_base = _git_text(
        self.command_runner,
        self.checkout,
        "merge-base",
        task_head,
        main_head,
    )
    task = (
        observation.get("task")
        if isinstance(observation.get("task"), Mapping)
        else {}
    )
    main_paths = _diff_paths(
        self,
        merge_base,
        main_head,
        label="mainline diff",
    )
    task_paths = _diff_paths(
        self,
        merge_base,
        task_head,
        label="task diff",
    )
    classification = classify_mainline_drift(
        main_changed_paths=main_paths,
        task_changed_paths=task_paths,
        exclusive_resources=_resource_paths(
            task.get("exclusive_resources") or []
        ),
        task_contract_path=str(
            task.get("contract_path") or f"Tasks/{self.task_id}.yaml"
        ),
    )

    self._ensure_git_identity()
    merge_result = _git(
        self.command_runner,
        self.checkout,
        "merge",
        "--no-ff",
        "--no-edit",
        "-m",
        f"Integrate main for {self.task_id} downstream validation",
        main_head,
        check=False,
        timeout_seconds=900.0,
    )
    if merge_result.returncode != 0:
        _restore_unpushed_head(self, task_head)
        return _block_current_lease(
            self,
            reason="mainline merge conflict",
            details={
                "task_head": task_head,
                "main_head": main_head,
                "merge_base": merge_base,
                "main_changed_paths": main_paths,
                "task_changed_paths": task_paths,
            },
        )

    integrated_commit = _git_text(
        self.command_runner,
        self.checkout,
        "rev-parse",
        "HEAD",
    )
    parents = _git_text(
        self.command_runner,
        self.checkout,
        "rev-list",
        "--parents",
        "-n",
        "1",
        integrated_commit,
    ).split()
    if parents != [integrated_commit, task_head, main_head]:
        _restore_unpushed_head(self, task_head)
        return _block_current_lease(
            self,
            reason="integration commit did not preserve ordered merge parents",
            details={
                "observed_parents": parents,
                "task_head": task_head,
                "main_head": main_head,
            },
        )

    exclusive_paths = _resource_paths(task.get("exclusive_resources") or [])
    blob_changed: list[str] = []
    for path in sorted(set(task_paths) | set(exclusive_paths), key=str.casefold):
        before = _object_id_at(self, task_head, path)
        after = _object_id_at(self, integrated_commit, path)
        if before != after and (before is not None or after is not None):
            blob_changed.append(path)
    if blob_changed and classification["classification"] == "automation_only":
        classification = {
            **classification,
            "classification": "runtime_sensitive",
            "human_revalidation_required": True,
            "reasons": [
                *classification.get("reasons", []),
                "integration changed task-owned blob identities",
            ],
        }

    whitespace = _git(
        self.command_runner,
        self.checkout,
        "diff",
        "--check",
        task_head,
        integrated_commit,
        "--",
        check=False,
    )
    validation = _run(
        self.command_runner,
        (sys.executable, "Pipeline/TaskGraph/taskcontrol.py", "validate"),
        cwd=self.checkout,
        timeout_seconds=900.0,
        check=False,
    )
    if whitespace.returncode != 0 or validation.returncode != 0:
        detail = "\n".join(
            item
            for item in (
                _decode(
                    whitespace.stdout + whitespace.stderr,
                    "whitespace output",
                ).strip(),
                _decode(
                    validation.stdout + validation.stderr,
                    "TaskGraph output",
                ).strip(),
            )
            if item
        )
        _restore_unpushed_head(self, task_head)
        return _block_current_lease(
            self,
            reason="integrated commit failed deterministic validation",
            details={
                "task_head": task_head,
                "main_head": main_head,
                "detail": detail[:4000],
            },
        )

    if _remote_branch_head(self, branch) != task_head:
        _restore_unpushed_head(self, task_head)
        return _block_current_lease(
            self,
            reason="remote task branch moved during integration",
            details={"task_head": task_head, "main_head": main_head},
        )
    push = _git(
        self.command_runner,
        self.checkout,
        "push",
        "origin",
        f"{integrated_commit}:refs/heads/{branch}",
        check=False,
        timeout_seconds=900.0,
    )
    remote_after_push = _remote_branch_head(self, branch)
    if remote_after_push != integrated_commit:
        _restore_unpushed_head(self, task_head)
        return _block_current_lease(
            self,
            reason="integrated commit could not be published exactly",
            details={
                "task_head": task_head,
                "main_head": main_head,
                "push_returncode": push.returncode,
                "remote_after_push": remote_after_push,
            },
        )

    receipt_payload = {
        "schema_version": INTEGRATION_RECEIPT_VERSION,
        "task_id": self.task_id,
        "branch": branch,
        "prior_task_head": task_head,
        "human_tested_commit": expected_human_commit,
        "main_head": main_head,
        "merge_base": merge_base,
        "integrated_commit": integrated_commit,
        "classification": classification["classification"],
        "human_revalidation_required": classification[
            "human_revalidation_required"
        ],
        "main_changed_paths": classification["main_changed_paths"],
        "task_changed_paths": classification["task_changed_paths"],
        "overlap_paths": classification["overlap_paths"],
        "exclusive_overlap_paths": classification[
            "exclusive_overlap_paths"
        ],
        "non_automation_paths": classification["non_automation_paths"],
        "task_blob_changes_after_merge": blob_changed,
        "created_at_utc": utc_now(),
        "authority": "deterministic_mainline_reintegration",
    }
    receipt = {
        **receipt_payload,
        "receipt_sha256": semantic_sha256(receipt_payload),
    }
    _invalidate_downstream_receipt(self, receipt)

    handoff = self.workflow.publish_human_handoff(
        branch=branch,
        head_commit=integrated_commit,
        implementation_summary=(
            "Merged current main into the previously human-tested task branch. "
            "Because the merge created a new commit, that exact integrated commit "
            "requires a new Unity result before delivery."
        ),
        completed_checks=[
            "Merge commit preserves the prior task head as first parent.",
            "TaskGraph validation passed on the integrated commit.",
            "git diff --check passed on the integration delta.",
            f"Integration classification: {receipt['classification']}",
            f"Integration receipt: {receipt['receipt_sha256']}",
        ],
        human_steps=[
            "Open the recorded NSC task checkout in Unity.",
            "Run the Issue's named EditMode/PlayMode tests.",
            "Repeat the prior gameplay checks on this exact integrated commit.",
            "Post PASS or FAIL for the exact commit and apply nsc-state:agent-ready.",
        ],
        expected_result=(
            "The integrated commit preserves the task behavior and all required "
            "tests pass without unexpected Console errors."
        ),
    )
    return {
        "status": "human_revalidation_required",
        "receipt": receipt,
        "handoff": handoff,
    }


def _patched_execute(decision: Any, controller: Any) -> Any:
    if decision.action == "integrate_current_main":
        decision.validate_arguments()
        return controller.integrate_current_main()
    return _ORIGINALS["execute"](decision, controller)


def _patched_terminal_outcome(
    request: Any,
    observation: Mapping[str, Any],
) -> dict[str, Any] | None:
    state = _workflow_state(observation)
    if (
        state.get("state") == WorkflowState.HUMAN_ACTION_REQUIRED.value
        and state.get("phase")
        == WorkflowPhase.UNITY_RUNTIME_VALIDATION.value
    ):
        coordination = (
            observation.get("coordination")
            if isinstance(observation.get("coordination"), Mapping)
            else {}
        )
        downstream = (
            observation.get("downstream")
            if isinstance(observation.get("downstream"), Mapping)
            else {}
        )
        receipt = (
            downstream.get("receipt")
            if isinstance(downstream.get("receipt"), Mapping)
            else {}
        )
        return {
            "schema_version": TASK_REVIEW_SCHEMA_VERSION,
            "task_id": request.task_id,
            "status": "human_revalidation_required",
            "issue_url": coordination.get("issue_url"),
            "branch": state.get("branch"),
            "commit": state.get("head_commit"),
            "pull_request_url": receipt.get("pull_request_url"),
            "authority": "delivery_evidence_to_verified_merge_closeout",
            "deterministic_final_state": observation,
            "next_action": (
                "Vincent validates the exact integrated commit recorded in the Issue."
            ),
            "blockers": [],
        }
    return _ORIGINALS["terminal_outcome"](request, observation)


def install_mainline_reintegration() -> None:
    """Install the transition once when TaskReviewAgent is imported."""

    global _INSTALLED
    if _INSTALLED:
        return
    from . import downstream_runtime as runtime
    from . import openai_downstream as openai

    controller = runtime.ResumableDownstreamTaskController
    _ORIGINALS.update(
        {
            "next_action": controller._next_action,
            "observe": controller.observe,
            "assert_human_tested_head": controller._assert_human_tested_head,
            "human_validation_artifact": (
                controller._human_validation_artifact
            ),
            "execute": openai._execute,
            "terminal_outcome": openai._terminal_outcome,
        }
    )
    controller._next_action = _patched_next_action
    controller.observe = _patched_observe
    controller._assert_human_tested_head = _patched_assert_human_tested_head
    controller._human_validation_artifact = _patched_human_validation_artifact
    controller.integrate_current_main = _integrate_current_main

    openai._ACTIONS["integrate_current_main"] = (
        "Merge current origin/main into the exact task branch with history preserved, "
        "classify drift, push the merge commit, and create a new exact-commit "
        "human Unity handoff. "
        "No arguments."
    )
    openai._GOAL_AND_RULES += """
- If downstream.next_action is integrate_current_main, select it before any Unity or
  delivery-evidence action. Host Python alone classifies drift and performs the merge.
- Every mainline integration creates a new exact-commit human Unity handoff,
  including automation-only drift. A PASS for the pre-merge commit is never reused
  as approval for the merge commit.
"""
    openai._execute = _patched_execute
    openai._terminal_outcome = _patched_terminal_outcome

    if "Pipeline/Testing/" not in runtime._READ_PREFIXES:
        runtime._READ_PREFIXES = (
            *runtime._READ_PREFIXES,
            "Pipeline/Testing/",
        )
    _INSTALLED = True


__all__ = [
    "classify_mainline_drift",
    "install_mainline_reintegration",
]
