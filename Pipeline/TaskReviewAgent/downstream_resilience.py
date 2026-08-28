"""Verified downstream PASS carry-forward and generic rejection resilience.

This module is installed after mainline_reintegration. It does not weaken the
exact-commit human-validation rule. Instead, it recognizes one additional,
hash-bound authority: a verified clerical task-contract migration whose event,
committed migration ledger, contract delta, Git ancestry, and protected task
blobs all agree.

It also makes authoritative test-platform selection explicit for hash-bound task
contracts and prevents deterministic downstream action rejections from consuming
the full supervisor turn budget while leaving a stale Issue lease behind.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .contracts import TaskReviewContractError, semantic_sha256
from .downstream_pipeline import (
    _SHA40,
    DownstreamPipelineError,
    _copy,
    _file_fact,
    _git,
    _git_text,
)
from .issue_workflow import (
    WorkflowActor,
    WorkflowEventType,
    WorkflowState,
    labels_for_state,
    render_event_comment,
    transition,
    update_issue_body,
    utc_now,
)
from .issue_workflow_store import IssueWorkflowStoreError


_POLICY_FILE = Path(__file__).with_name("authoritative_validation_policy.json")
_LEDGER_PATH = "Pipeline/TaskGraph/migrations/canonical-unity-scene-paths-20260828.json"
_RECEIPT_KEY = "human_pass_carry_forward"
_RECEIPT_VERSION = "1.0"
_STALE_DOWNSTREAM_KEYS = (
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
    "delivery_base_commit",
)
_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}


def _normalized_error(value: BaseException) -> str:
    return " ".join(str(value).split())[:1200]


def _task_id(task: Mapping[str, Any]) -> str | None:
    for key in ("id", "task_id"):
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _safe_repository_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return None
    return path.as_posix()


def _policy_document() -> dict[str, Any]:
    try:
        value = json.loads(_POLICY_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DownstreamPipelineError(
            "authoritative validation policy is missing or invalid"
        ) from exc
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise DownstreamPipelineError(
            "authoritative validation policy has an unsupported schema"
        )
    tasks = value.get("tasks")
    if not isinstance(tasks, dict):
        raise DownstreamPipelineError(
            "authoritative validation policy omitted tasks"
        )
    return value


def _policy_for_task(task: Mapping[str, Any]) -> dict[str, Any] | None:
    identifier = _task_id(task)
    if identifier is None:
        return None
    raw = _policy_document()["tasks"].get(identifier)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise DownstreamPipelineError(
            f"authoritative validation policy for {identifier} is invalid"
        )
    expected_hash = raw.get("task_contract_sha256")
    observed_hash = task.get("task_contract_sha256")
    if (
        not isinstance(expected_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
        or observed_hash != expected_hash
    ):
        raise DownstreamPipelineError(
            f"authoritative validation policy for {identifier} is stale for the task contract"
        )
    platforms = raw.get("required_test_platforms")
    filters = raw.get("test_filters")
    protected = raw.get("protected_paths")
    if (
        not isinstance(platforms, list)
        or not platforms
        or any(item not in ("EditMode", "PlayMode") for item in platforms)
        or len(platforms) != len(set(platforms))
        or not isinstance(filters, dict)
        or any(
            not isinstance(filters.get(platform), str)
            or not filters[platform].strip()
            for platform in platforms
        )
        or not isinstance(protected, list)
        or not protected
    ):
        raise DownstreamPipelineError(
            f"authoritative validation policy for {identifier} is incomplete"
        )
    normalized_paths = [_safe_repository_path(item) for item in protected]
    if any(item is None for item in normalized_paths):
        raise DownstreamPipelineError(
            f"authoritative validation policy for {identifier} contains an unsafe path"
        )
    return {
        **raw,
        "required_test_platforms": list(platforms),
        "test_filters": {
            platform: str(filters[platform]).strip() for platform in platforms
        },
        "protected_paths": sorted(
            {str(item) for item in normalized_paths}, key=str.casefold
        ),
    }


def _patched_required_platforms(task: Mapping[str, Any]) -> tuple[str, ...]:
    policy = _policy_for_task(task)
    if policy is not None:
        return tuple(policy["required_test_platforms"])
    return _ORIGINALS["required_platforms"](task)


def _git_bytes(controller: Any, commit: str, path: str) -> bytes:
    result = _git(
        controller.command_runner,
        controller.checkout,
        "show",
        f"{commit}:{path}",
        check=False,
    )
    if result.returncode != 0:
        raise DownstreamPipelineError(
            f"required committed migration input is missing: {commit}:{path}"
        )
    return bytes(result.stdout or b"")


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
    value = (result.stdout or b"").decode("utf-8", errors="strict").strip()
    return value if _SHA40.fullmatch(value) else None


def _replace_contract_strings(value: Any, replacements: list[dict[str, str]]) -> Any:
    if isinstance(value, str):
        updated = value
        for replacement in replacements:
            updated = updated.replace(replacement["from"], replacement["to"])
        return updated
    if isinstance(value, list):
        return [_replace_contract_strings(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_contract_strings(item, replacements)
            for key, item in value.items()
        }
    return value


def _migration_ledger_entry(
    controller: Any,
    *,
    task_id: str,
    operational_head: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        ledger = json.loads(
            _git_bytes(controller, operational_head, _LEDGER_PATH).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DownstreamPipelineError("task-contract migration ledger is invalid") from exc
    if (
        not isinstance(ledger, dict)
        or ledger.get("schema_version") != "1.0"
        or not isinstance(ledger.get("migration_id"), str)
        or not isinstance(ledger.get("task_contracts"), list)
    ):
        raise DownstreamPipelineError("task-contract migration ledger is incomplete")
    matches = [
        item
        for item in ledger["task_contracts"]
        if isinstance(item, dict) and item.get("task_id") == task_id
    ]
    if len(matches) != 1:
        raise DownstreamPipelineError(
            f"task-contract migration ledger does not uniquely identify {task_id}"
        )
    return ledger, matches[0]


def _migration_event(snapshot: Any, operational_head: str) -> Any | None:
    for event in reversed(snapshot.events):
        if event.event_type is not WorkflowEventType.TASK_CONTRACT_MIGRATED:
            continue
        details = event.details
        if details.get("head_commit") == operational_head:
            return event
    return None


def _receipt_payload(
    controller: Any,
    *,
    state: Mapping[str, Any],
    task: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    service = controller.workflow.issue_workflow
    if service is None:
        raise DownstreamPipelineError("Issue workflow is unavailable")
    snapshot = service.find(controller.task_id)
    if snapshot is None or not snapshot.valid or snapshot.state is None:
        raise DownstreamPipelineError(
            "verified contract migration requires a valid managed Issue"
        )

    operational_head = state.get("head_commit")
    human_commit = state.get("human_handoff_commit")
    if (
        not isinstance(operational_head, str)
        or not _SHA40.fullmatch(operational_head)
        or not isinstance(human_commit, str)
        or not _SHA40.fullmatch(human_commit)
        or state.get("human_result") != "pass"
    ):
        raise DownstreamPipelineError(
            "verified contract migration requires preserved human PASS identities"
        )
    event = _migration_event(snapshot, operational_head)
    if event is None:
        raise DownstreamPipelineError(
            "operational head has no matching task_contract_migrated event"
        )
    details = event.details
    if (
        details.get("human_handoff_commit") != human_commit
        or details.get("human_result") != "pass"
        or details.get("new_task_contract_sha256")
        != state.get("task_contract_sha256")
        or details.get("branch") != state.get("branch")
    ):
        raise DownstreamPipelineError(
            "task_contract_migrated event does not match current Issue identities"
        )

    human = controller._latest_human_validation()
    if (
        human is None
        or human.get("result") != "pass"
        or human.get("tested_commit") != human_commit
    ):
        raise DownstreamPipelineError(
            "verified contract migration is missing its original exact human PASS"
        )
    if (
        _git(
            controller.command_runner,
            controller.checkout,
            "merge-base",
            "--is-ancestor",
            human_commit,
            operational_head,
            check=False,
        ).returncode
        != 0
    ):
        raise DownstreamPipelineError(
            "human-tested commit is not an ancestor of the operational head"
        )

    ledger, entry = _migration_ledger_entry(
        controller,
        task_id=controller.task_id,
        operational_head=operational_head,
    )
    if (
        details.get("migration_id") != ledger.get("migration_id")
        or policy.get("migration_id") != ledger.get("migration_id")
        or details.get("old_task_contract_sha256") != entry.get("old_sha256")
        or details.get("new_task_contract_sha256") != entry.get("new_sha256")
    ):
        raise DownstreamPipelineError(
            "task-contract migration event and committed ledger disagree"
        )
    contract_path = entry.get("path")
    replacements = entry.get("replacements")
    if (
        contract_path != task.get("contract_path")
        or not isinstance(contract_path, str)
        or not isinstance(replacements, list)
        or not replacements
        or any(
            not isinstance(item, dict)
            or set(item) != {"from", "to"}
            or not isinstance(item["from"], str)
            or not isinstance(item["to"], str)
            or not item["from"]
            or not item["to"]
            for item in replacements
        )
    ):
        raise DownstreamPipelineError(
            "task-contract migration ledger entry is not a bounded path migration"
        )

    old_bytes = _git_bytes(controller, human_commit, contract_path)
    new_bytes = _git_bytes(controller, operational_head, contract_path)
    old_sha = hashlib.sha256(old_bytes).hexdigest()
    new_sha = hashlib.sha256(new_bytes).hexdigest()
    if old_sha != entry.get("old_sha256") or new_sha != entry.get("new_sha256"):
        raise DownstreamPipelineError(
            "task-contract bytes do not match the committed migration ledger"
        )
    try:
        old_contract = json.loads(old_bytes.decode("utf-8-sig"))
        new_contract = json.loads(new_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DownstreamPipelineError("migrated task contract is invalid JSON") from exc
    if not isinstance(old_contract, dict) or not isinstance(new_contract, dict):
        raise DownstreamPipelineError("migrated task contract must be an object")
    old_revision = old_contract.get("contract_revision")
    new_revision = new_contract.get("contract_revision")
    if (
        not isinstance(old_revision, int)
        or not isinstance(new_revision, int)
        or new_revision != old_revision + 1
        or entry.get("old_contract_revision") != old_revision
        or entry.get("new_contract_revision") != new_revision
    ):
        raise DownstreamPipelineError(
            "task-contract migration revision transition is invalid"
        )
    normalized_old = _replace_contract_strings(old_contract, replacements)
    normalized_old["contract_revision"] = new_revision
    if normalized_old != new_contract:
        raise DownstreamPipelineError(
            "task-contract migration changed more than revision and declared paths"
        )

    changed_protected: list[str] = []
    for path in policy["protected_paths"]:
        before = _object_id_at(controller, human_commit, path)
        after = _object_id_at(controller, operational_head, path)
        if before is None or after is None or before != after:
            changed_protected.append(path)
    if changed_protected:
        raise DownstreamPipelineError(
            "task-contract migration changed protected task blobs: "
            + ", ".join(changed_protected)
        )

    payload = {
        "schema_version": _RECEIPT_VERSION,
        "receipt_type": "verified_clerical_task_contract_migration",
        "task_id": controller.task_id,
        "branch": state.get("branch"),
        "operational_commit": operational_head,
        "human_tested_commit": human_commit,
        "human_result": "pass",
        "migration_id": ledger["migration_id"],
        "migration_event_id": event.event_id,
        "migration_event_sequence": event.sequence,
        "migration_ledger_path": _LEDGER_PATH,
        "migration_ledger_entry_sha256": semantic_sha256(entry),
        "old_task_contract_sha256": old_sha,
        "new_task_contract_sha256": new_sha,
        "task_contract_path": contract_path,
        "replacements": replacements,
        "protected_paths": list(policy["protected_paths"]),
        "required_test_platforms": list(policy["required_test_platforms"]),
        "test_filters": dict(policy["test_filters"]),
        "authority": "verified_clerical_task_contract_migration",
    }
    return payload


def _verified_contract_migration_receipt(
    controller: Any,
    *,
    state: Mapping[str, Any],
    task: Mapping[str, Any],
) -> dict[str, Any] | None:
    policy = _policy_for_task(task)
    if policy is None:
        return None
    try:
        payload = _receipt_payload(
            controller,
            state=state,
            task=task,
            policy=policy,
        )
    except DownstreamPipelineError:
        return None
    receipt = {**payload, "receipt_sha256": semantic_sha256(payload)}
    current = controller.state.get(_RECEIPT_KEY)
    if current != receipt:
        for key in _STALE_DOWNSTREAM_KEYS:
            controller.state.pop(key, None)
        controller.state["validation_manifests"] = []
        controller.state[_RECEIPT_KEY] = receipt
        controller._persist()
    return receipt


def _patched_controller_observe(self: Any) -> dict[str, Any]:
    observation = _ORIGINALS["controller_observe"](self)
    downstream = observation.get("downstream")
    task = observation.get("task")
    if isinstance(downstream, dict) and isinstance(task, Mapping):
        policy = _policy_for_task(task)
        if policy is not None:
            downstream["authoritative_validation_policy"] = {
                "required_test_platforms": list(
                    policy["required_test_platforms"]
                ),
                "test_filters": dict(policy["test_filters"]),
                "task_contract_sha256": policy["task_contract_sha256"],
                "authority": policy["authority"],
            }
    return observation


def _patched_assert_human_tested_head(
    self: Any,
    state: Mapping[str, Any],
) -> None:
    try:
        _ORIGINALS["assert_human_tested_head"](self, state)
        return
    except DownstreamPipelineError as original_error:
        if _normalized_error(original_error) not in {
            "exact human PASS for checkout HEAD is missing",
            "automation-only receipt is missing its original exact human PASS",
        }:
            raise

    observation = self.observe()
    task = observation.get("task")
    if not isinstance(task, Mapping):
        raise DownstreamPipelineError("downstream observation omitted task authority")
    receipt = _verified_contract_migration_receipt(
        self,
        state=state,
        task=task,
    )
    if receipt is None:
        raise DownstreamPipelineError("exact human PASS for checkout HEAD is missing")

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
    if receipt["operational_commit"] != head:
        raise DownstreamPipelineError(
            "contract-migration carry-forward receipt is stale for checkout HEAD"
        )

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
            "origin/main advanced beyond the validated contract migration; integrate current main"
        )
    existing_base = self.state.get("delivery_base_commit")
    if existing_base is not None and existing_base != current_main:
        raise DownstreamPipelineError(
            "delivery base changed after authoritative work began; reintegrate main"
        )
    if existing_base is None:
        self.state["delivery_base_commit"] = current_main
        self._persist()


def _patched_human_validation_artifact(
    self: Any,
    commit: str,
) -> dict[str, Any]:
    observation = self.observe()
    state = (
        observation.get("coordination", {}).get("workflow_state", {})
        if isinstance(observation.get("coordination"), Mapping)
        else {}
    )
    task = observation.get("task")
    receipt = (
        _verified_contract_migration_receipt(
            self,
            state=state,
            task=task,
        )
        if isinstance(task, Mapping) and isinstance(state, Mapping)
        else None
    )
    if receipt is None or receipt.get("operational_commit") != commit:
        return _ORIGINALS["human_validation_artifact"](self, commit)

    current = self.state.get("human_validation")
    if (
        isinstance(current, Mapping)
        and current.get("carry_forward_receipt_sha256")
        == receipt["receipt_sha256"]
    ):
        path = Path(str(current.get("path") or ""))
        if path.is_file() and current.get("sha256") == _file_fact(path)["sha256"]:
            return dict(current)

    human = self._latest_human_validation()
    if (
        human is None
        or human.get("result") != "pass"
        or human.get("tested_commit") != receipt["human_tested_commit"]
    ):
        raise DownstreamPipelineError("original human PASS is unavailable")
    service = self.workflow.issue_workflow
    if service is None:
        raise DownstreamPipelineError("Issue workflow is unavailable")
    snapshot = service.find(self.task_id)
    if snapshot is None:
        raise DownstreamPipelineError("managed Issue is missing")

    output = self._output_root(commit) / "human-validation.txt"
    if output.exists():
        raise DownstreamPipelineError(
            "human-validation output exists with unknown identity"
        )
    output.write_text(
        "\n".join(
            (
                f"Task: {self.task_id}",
                f"Issue: {snapshot.issue_url}",
                f"Human-tested implementation commit: {receipt['human_tested_commit']}",
                f"Operational commit under automated validation: {commit}",
                "Human result: PASS",
                "Operational-commit human revalidation: NOT PERFORMED",
                "Carry-forward authority: verified clerical task-contract migration",
                f"Migration ID: {receipt['migration_id']}",
                f"Carry-forward receipt SHA256: {receipt['receipt_sha256']}",
                "Authoritative Unity validation on the operational commit is required.",
                "",
                str(human.get("body") or "").strip(),
                "",
            )
        ),
        encoding="utf-8",
        newline="\n",
    )
    fact = {
        **_file_fact(output),
        "carry_forward_receipt_sha256": receipt["receipt_sha256"],
        "human_tested_commit": receipt["human_tested_commit"],
        "operational_commit": commit,
    }
    self.state["human_validation"] = fact
    self._persist()
    return dict(fact)


def _patched_run_authoritative_unity_test(
    self: Any,
    *,
    test_platform: str,
    test_filter: str,
) -> dict[str, Any]:
    observation = self.observe()
    task = observation.get("task")
    policy = _policy_for_task(task) if isinstance(task, Mapping) else None
    if policy is not None:
        expected = policy["test_filters"].get(test_platform)
        if expected is None or test_filter != expected:
            raise DownstreamPipelineError(
                "authoritative Unity invocation does not match the committed task policy"
            )
    return _ORIGINALS["run_authoritative_unity_test"](
        self,
        test_platform=test_platform,
        test_filter=test_filter,
    )


def _rejection_observation_payload(
    controller: Any,
    *,
    action: str,
    error: BaseException,
) -> dict[str, Any]:
    observation = controller._controller.observe()
    coordination = observation.get("coordination")
    coordination = coordination if isinstance(coordination, Mapping) else {}
    state = coordination.get("workflow_state")
    state = state if isinstance(state, Mapping) else {}
    checkout = observation.get("checkout")
    checkout = checkout if isinstance(checkout, Mapping) else {}
    downstream = observation.get("downstream")
    downstream = downstream if isinstance(downstream, Mapping) else {}
    return {
        "action": action,
        "error_type": type(error).__name__,
        "error": _normalized_error(error),
        "state_version": state.get("state_version"),
        "state": state.get("state"),
        "phase": state.get("phase"),
        "worker_id": state.get("worker_id"),
        "next_action": downstream.get("next_action"),
        "checkout_status": checkout.get("status"),
        "checkout_head": checkout.get("head_commit"),
    }


def _release_guard_lease(
    controller: Any,
    *,
    reason: str,
    details: Mapping[str, Any],
) -> bool:
    underlying = controller._controller
    workflow = getattr(underlying, "workflow", None)
    service = getattr(workflow, "issue_workflow", None)
    worker_id = str(getattr(workflow, "worker_id", "") or "")
    task_id = str(getattr(underlying, "task_id", "") or "")
    if service is None or not worker_id or not task_id:
        return False
    snapshot = service.find(task_id)
    if snapshot is None or not snapshot.valid or snapshot.state is None:
        return False
    state = snapshot.state
    if state.state is not WorkflowState.AGENT_WORKING or state.worker_id != worker_id:
        return False

    next_state, event = transition(
        state,
        event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
        actor_type=WorkflowActor.AGENT,
        actor_id=worker_id,
        to_state=WorkflowState.AGENT_READY,
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
                    "The downstream agent released its lease instead of repeating a deterministic failure.",
                    "",
                    f"- **Reason:** `{reason}`",
                    f"- **Action:** `{details.get('action')}`",
                    f"- **Error:** {details.get('error')}",
                    "",
                    "The same generic Game Task Agent command may be used after the recorded cause is fixed.",
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
                "Resolve the latest downstream rejection or update the agent code, then run "
                "the same generic Game Task Agent command."
            ),
        ),
        labels=labels_for_state(next_state.state, snapshot.labels),
        assignees=[service.assignee],
    )
    verified = service.find(task_id)
    if verified is None or not verified.valid or verified.state != next_state:
        raise IssueWorkflowStoreError(
            "downstream rejection lease release could not be verified"
        )
    controller._downstream_terminal_reasons = [
        f"{reason}: {details.get('action')}: {details.get('error')}"
    ]
    controller._downstream_terminal_context = dict(details)
    return True


def _record_guard_rejection(
    controller: Any,
    *,
    action: str,
    error: BaseException,
) -> None:
    payload = _rejection_observation_payload(
        controller,
        action=action,
        error=error,
    )
    fingerprint = semantic_sha256(payload)
    prior = getattr(controller, "_downstream_rejection_fingerprint", None)
    count = (
        int(getattr(controller, "_downstream_rejection_count", 0)) + 1
        if prior == fingerprint
        else 1
    )
    state_fingerprint = semantic_sha256(
        {
            key: payload[key]
            for key in (
                "state_version",
                "state",
                "phase",
                "worker_id",
                "next_action",
                "checkout_status",
                "checkout_head",
            )
        }
    )
    prior_state = getattr(controller, "_downstream_rejection_state", None)
    state_count = (
        int(getattr(controller, "_downstream_rejection_state_count", 0)) + 1
        if prior_state == state_fingerprint
        else 1
    )
    controller._downstream_rejection_fingerprint = fingerprint
    controller._downstream_rejection_count = count
    controller._downstream_rejection_state = state_fingerprint
    controller._downstream_rejection_state_count = state_count
    if count >= 2 or state_count >= 3:
        _release_guard_lease(
            controller,
            reason="repeated_downstream_action_rejection",
            details={
                **payload,
                "rejection_fingerprint": fingerprint,
                "identical_rejection_count": count,
                "unchanged_state_rejection_count": state_count,
            },
        )


def _patched_guard_getattr(self: Any, name: str) -> Any:
    value = _ORIGINALS["guard_getattr"](self, name)
    if not callable(value) or name.startswith("_"):
        return value

    def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            result = value(*args, **kwargs)
        except TaskReviewContractError as exc:
            _record_guard_rejection(self, action=name, error=exc)
            raise
        self._downstream_rejection_fingerprint = None
        self._downstream_rejection_count = 0
        self._downstream_rejection_state = None
        self._downstream_rejection_state_count = 0
        return result

    return guarded


def _patched_guard_observe(self: Any) -> dict[str, Any]:
    observation = _ORIGINALS["guard_observe"](self)
    reasons = list(getattr(self, "_downstream_terminal_reasons", []) or [])
    if not reasons:
        return observation
    guarded = _copy(observation)
    environment = guarded.get("environment")
    if not isinstance(environment, dict):
        environment = {}
        guarded["environment"] = environment
    environment["ready"] = False
    errors = [str(item) for item in environment.get("errors") or []]
    environment["errors"] = list(dict.fromkeys(errors + reasons))
    guarded["goal_loop_guard"] = {
        "status": "repeated_downstream_action_rejection",
        "reasons": reasons,
        "details": dict(
            getattr(self, "_downstream_terminal_context", {}) or {}
        ),
        "authority": "deterministic_rejection_circuit_breaker",
    }
    return guarded


def _abort_guarded_run(
    controller: Any,
    *,
    reason: str,
    error: BaseException,
) -> None:
    if getattr(controller, "_downstream_terminal_reasons", None):
        return
    _release_guard_lease(
        controller,
        reason=reason,
        details={
            "action": "downstream_goal_loop",
            "error_type": type(error).__name__,
            "error": _normalized_error(error),
        },
    )


def _patched_run_openai_downstream_pipeline(*args: Any, **kwargs: Any) -> Any:
    controller = args[1] if len(args) > 1 else kwargs.get("controller")
    try:
        return _ORIGINALS["run_openai_downstream_pipeline"](*args, **kwargs)
    except BaseException as exc:
        if controller is not None and hasattr(controller, "_controller"):
            reason = (
                "downstream_turn_budget_exhausted"
                if "exhausted" in _normalized_error(exc).casefold()
                else "downstream_run_interrupted"
                if isinstance(exc, KeyboardInterrupt)
                else "downstream_run_failed"
            )
            try:
                _abort_guarded_run(controller, reason=reason, error=exc)
            except Exception:
                pass
        raise


def install_downstream_resilience() -> None:
    """Install the verified carry-forward and rejection guards exactly once."""

    global _INSTALLED
    if _INSTALLED:
        return

    from . import downstream_pipeline as base
    from . import downstream_runtime as runtime
    from . import openai_downstream as openai
    from .goal_loop_guard import GuardedTaskController

    controller = runtime.ResumableDownstreamTaskController
    _ORIGINALS.update(
        {
            "required_platforms": base._required_platforms,
            "controller_observe": controller.observe,
            "assert_human_tested_head": controller._assert_human_tested_head,
            "human_validation_artifact": controller._human_validation_artifact,
            "run_authoritative_unity_test": controller.run_authoritative_unity_test,
            "guard_getattr": GuardedTaskController.__getattr__,
            "guard_observe": GuardedTaskController.observe,
            "run_openai_downstream_pipeline": openai.run_openai_downstream_pipeline,
        }
    )

    base._required_platforms = _patched_required_platforms
    runtime._required_platforms = _patched_required_platforms
    controller.observe = _patched_controller_observe
    controller._assert_human_tested_head = _patched_assert_human_tested_head
    controller._human_validation_artifact = _patched_human_validation_artifact
    controller.run_authoritative_unity_test = _patched_run_authoritative_unity_test
    GuardedTaskController.__getattr__ = _patched_guard_getattr
    GuardedTaskController.observe = _patched_guard_observe
    openai.run_openai_downstream_pipeline = _patched_run_openai_downstream_pipeline

    existing = openai._ACTIONS.get("run_authoritative_unity_test", "")
    openai._ACTIONS["run_authoritative_unity_test"] = (
        existing
        + " When downstream.authoritative_validation_policy is present, use its exact "
        "test platform and filter; deterministic code rejects any other invocation."
    )
    openai._GOAL_AND_RULES += """
- A verified clerical task-contract migration may preserve an earlier exact human PASS
  only when its append-only event, committed migration ledger, contract delta, Git
  ancestry, and protected task blobs all agree. Host Python verifies that authority.
- When downstream.authoritative_validation_policy is present, run exactly the listed
  platform/filter pairs and do not invent an additional EditMode or PlayMode obligation.
- Do not retry an action after deterministic validation rejects the same action under
  the same workflow identity. The host circuit breaker releases the lease on repetition.
"""
    _INSTALLED = True


__all__ = [
    "install_downstream_resilience",
    "_policy_for_task",
    "_receipt_payload",
]
