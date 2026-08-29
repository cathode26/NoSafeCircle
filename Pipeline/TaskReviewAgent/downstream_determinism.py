"""Deterministic downstream authority, routing, and bounded supervisor context.

This extension is installed after the existing mainline-reintegration and
resilience layers. It closes five production gaps without weakening any
commit-bound authority:

* human Unity results come only from validated workflow events and the exact
  hash-bound human comment, never from instructional templates in agent prose;
* automation-only integration receipts can be rebuilt from the durable Issue
  event and re-verified against Git when machine-local cache state is missing;
* stale checkout refs route to checkout preparation before Unity validation;
* the downstream supervisor sees only actions relevant to the deterministic
  next state, and its prompt history contains bounded summaries rather than
  complete Issue logs or file contents;
* malformed repository searches and repeated same-state rejections fail closed.
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .codex_supervisor import (
    CodexDockerDecisionProvider,
    CodexSupervisorError,
    SupervisorDecision,
)
from .contracts import TaskReviewContractError, semantic_sha256
from .downstream_pipeline import (
    _SHA40,
    DownstreamPipelineError,
    _decode,
    _git,
    _git_text,
)
from .issue_workflow import (
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    parse_human_validation_result,
)
from .progress import summarize_result


_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_ACTION_CONTEXT: ContextVar[tuple[str, ...] | None] = ContextVar(
    "nsc_downstream_allowed_actions",
    default=None,
)

_NEXT_ACTION_ALIASES = {
    "run_authoritative_unity_tests": "run_authoritative_unity_test",
    "finalize_delivery_evidence": "finalize_delivery_evidence_and_open_pr",
    "open_pull_request": "finalize_delivery_evidence_and_open_pr",
}


def _short(value: Any, *, limit: int = 700) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _workflow_state(observation: Mapping[str, Any]) -> dict[str, Any]:
    coordination = observation.get("coordination")
    if not isinstance(coordination, Mapping):
        return {}
    state = coordination.get("workflow_state")
    return dict(state) if isinstance(state, Mapping) else {}


def _downstream_state(observation: Mapping[str, Any]) -> dict[str, Any]:
    downstream = observation.get("downstream")
    return dict(downstream) if isinstance(downstream, Mapping) else {}


def _authoritative_human_validation(self: Any) -> dict[str, Any] | None:
    """Resolve the exact human result authorized by the validated event chain.

    Agent-written handoff comments contain a copyable PASS/FAIL template. Those
    comments must never be interpreted as human authority. The workflow event
    identifies the human result and hashes the original result comment; only a
    comment with that exact hash is returned.
    """

    service = self.workflow.issue_workflow
    if service is None:
        return None
    snapshot = service.find(self.task_id)
    if snapshot is None or not snapshot.valid or snapshot.state is None:
        return None

    expected_commit = snapshot.state.human_handoff_commit
    expected_result = snapshot.state.human_result
    candidates = []
    for event in reversed(snapshot.events):
        if event.event_type not in {
            WorkflowEventType.HUMAN_VALIDATION_PASSED,
            WorkflowEventType.HUMAN_VALIDATION_FAILED,
        }:
            continue
        details = event.details
        result = details.get("result")
        tested_commit = details.get("tested_commit")
        if expected_commit is not None and tested_commit != expected_commit:
            continue
        if expected_result is not None and result != expected_result:
            continue
        candidates.append(event)

    if not candidates:
        return None
    event = candidates[0]
    expected_comment_hash = event.details.get("human_comment_sha256")
    if not isinstance(expected_comment_hash, str) or not _SHA256.fullmatch(
        expected_comment_hash
    ):
        raise DownstreamPipelineError(
            "authoritative human validation event omitted its comment identity"
        )

    matches: list[dict[str, Any]] = []
    for comment in service.backend.get_comments(snapshot.issue_number):
        if not isinstance(comment, Mapping):
            continue
        body = comment.get("body")
        if not isinstance(body, str):
            continue
        if semantic_sha256({"body": body}) != expected_comment_hash:
            continue
        parsed = parse_human_validation_result(body)
        if (
            parsed is None
            or parsed.result != event.details.get("result")
            or parsed.tested_commit != event.details.get("tested_commit")
        ):
            raise DownstreamPipelineError(
                "hash-bound human validation comment does not match its workflow event"
            )
        matches.append(
            {
                "result": parsed.result,
                "tested_commit": parsed.tested_commit,
                "body": parsed.body,
                "comment_id": comment.get("id"),
                "event_id": event.event_id,
                "actor_id": event.actor_id,
                "human_comment_sha256": expected_comment_hash,
                "authority": "validated_human_workflow_event_and_comment_hash",
            }
        )

    if len(matches) != 1:
        raise DownstreamPipelineError(
            "authoritative human validation comment is missing, duplicated, or changed"
        )
    return matches[0]


def _schema_types(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def _strengthen_schema(node: Any) -> None:
    if not isinstance(node, dict):
        return
    kinds = _schema_types(node.get("type"))
    if "string" in kinds:
        node.setdefault("minLength", 1)
    if "array" in kinds:
        _strengthen_schema(node.get("items"))
    if "object" in kinds:
        properties = node.get("properties")
        if isinstance(properties, dict):
            for child in properties.values():
                _strengthen_schema(child)


def _patched_decision_schema(allowed_actions: Sequence[str]) -> dict[str, Any]:
    schema = _ORIGINALS["decision_schema"](allowed_actions)
    _strengthen_schema(schema)
    arguments = schema["properties"]["arguments"]["properties"]
    prefixes = arguments.get("prefixes")
    if isinstance(prefixes, dict):
        prefixes["minItems"] = 1
    return schema


def _patched_validate_arguments(
    self: SupervisorDecision,
    *,
    required: Sequence[str] = (),
    optional: Sequence[str] = (),
) -> dict[str, Any]:
    values = _ORIGINALS["validate_arguments"](
        self,
        required=required,
        optional=optional,
    )
    for key, value in values.items():
        if isinstance(value, str) and not value.strip():
            raise CodexSupervisorError(
                f"action {self.action} argument {key} must be non-empty"
            )
        if isinstance(value, (list, tuple)):
            if key == "prefixes" and not value:
                raise CodexSupervisorError(
                    "action search_repository requires at least one repository prefix"
                )
            if any(isinstance(item, str) and not item.strip() for item in value):
                raise CodexSupervisorError(
                    f"action {self.action} argument {key} contains a blank entry"
                )
    return values


def bounded_history(
    history: Sequence[Mapping[str, Any]],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Keep only bounded action identity, rationale, result facts, and errors."""

    values: list[dict[str, Any]] = []
    for item in history[-limit:]:
        record: dict[str, Any] = {}
        turn = item.get("turn")
        if isinstance(turn, int):
            record["turn"] = turn
        action = item.get("action")
        if isinstance(action, str):
            record["action"] = action
        rationale = item.get("rationale")
        if isinstance(rationale, str) and rationale.strip():
            record["rationale"] = _short(rationale, limit=500)
        if "result" in item:
            record["result"] = summarize_result(item.get("result"))
        error = item.get("tool_error")
        if error is not None:
            record["tool_error"] = _short(error, limit=700)
        values.append(record)
    return values


def _normalize_next_action(value: Any) -> str:
    text = str(value or "")
    return _NEXT_ACTION_ALIASES.get(text, text)


def _history_has_success(history: Sequence[Mapping[str, Any]], action: str) -> bool:
    return any(
        item.get("action") == action
        and "result" in item
        and "tool_error" not in item
        for item in history
        if isinstance(item, Mapping)
    )


def allowed_actions_for(
    observation: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    actions: Mapping[str, str],
) -> tuple[str, ...]:
    """Return the smallest safe action menu for the current deterministic state."""

    downstream = _downstream_state(observation)
    checkout = observation.get("checkout")
    checkout = checkout if isinstance(checkout, Mapping) else {}
    mainline = downstream.get("mainline_reintegration")
    mainline = mainline if isinstance(mainline, Mapping) else {}

    if checkout.get("origin_main_refresh_required") is True or mainline.get(
        "status"
    ) == "main_commit_unavailable":
        next_action = "prepare_task_checkout"
    elif mainline.get("status") == "required":
        next_action = "integrate_current_main"
    else:
        next_action = _normalize_next_action(downstream.get("next_action"))

    if next_action == "create_delivery_review_proposal":
        selected = (
            "create_delivery_review_proposal"
            if _history_has_success(history, "delivery_review_facts")
            else "delivery_review_facts"
        )
        return (selected,) if selected in actions else tuple(actions)

    if next_action == "run_authoritative_unity_test":
        plan = downstream.get("authoritative_test_plan")
        if isinstance(plan, Mapping):
            return (
                ("run_authoritative_unity_test",)
                if "run_authoritative_unity_test" in actions
                else tuple(actions)
            )
        fallback = tuple(
            name
            for name in (
                "read_issue_log",
                "list_repository_files",
                "search_repository",
                "read_repository_file",
                "run_authoritative_unity_test",
            )
            if name in actions
        )
        return fallback or tuple(actions)

    direct = {
        "acquire_agent_lease",
        "prepare_task_checkout",
        "integrate_current_main",
        "create_delivery_review_draft",
        "publish_delivery_review",
        "finalize_delivery_evidence_and_open_pr",
        "inspect_or_merge_pull_request",
        "verify_post_merge_and_complete",
    }
    if next_action in direct and next_action in actions:
        return (next_action,)
    return tuple(actions)


def _patched_render_supervisor_prompt(
    *,
    task_id: str,
    goal_and_rules: str,
    observation: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    actions: Mapping[str, str],
) -> str:
    selected = allowed_actions_for(observation, history, actions)
    narrowed = {name: actions[name] for name in selected}
    downstream = _downstream_state(observation)
    plan = downstream.get("authoritative_test_plan")
    if (
        selected == ("run_authoritative_unity_test",)
        and isinstance(plan, Mapping)
    ):
        platforms = plan.get("required_test_platforms")
        filters = plan.get("test_filters")
        if isinstance(platforms, list) and isinstance(filters, Mapping):
            pairs = [
                f"{platform}: {filters.get(platform)}"
                for platform in platforms
                if isinstance(filters.get(platform), str)
            ]
            if pairs:
                narrowed["run_authoritative_unity_test"] += (
                    " Host-authorized exact plan: " + "; ".join(pairs) + "."
                )
    _ALLOWED_ACTION_CONTEXT.set(selected)
    return _ORIGINALS["render_supervisor_prompt"](
        task_id=task_id,
        goal_and_rules=goal_and_rules,
        observation=observation,
        history=history,
        actions=narrowed,
    )


def _patched_provider_decide(
    self: CodexDockerDecisionProvider,
    *,
    task_id: str,
    turn: int,
    prompt: str,
    allowed_actions: Sequence[str],
) -> SupervisorDecision:
    selected = _ALLOWED_ACTION_CONTEXT.get()
    actual = (
        tuple(name for name in selected if name in set(allowed_actions))
        if selected
        else tuple(allowed_actions)
    )
    if not actual:
        actual = tuple(allowed_actions)
    try:
        return _ORIGINALS["provider_decide"](
            self,
            task_id=task_id,
            turn=turn,
            prompt=prompt,
            allowed_actions=actual,
        )
    finally:
        _ALLOWED_ACTION_CONTEXT.set(None)


def _patched_next_action(
    self: Any,
    observation: Mapping[str, Any],
    state: Mapping[str, Any] | None,
) -> str:
    action = _ORIGINALS["next_action"](self, observation, state)
    if state is None:
        return _normalize_next_action(action)
    checkout = observation.get("checkout")
    checkout = checkout if isinstance(checkout, Mapping) else {}
    status = getattr(self, "_mainline_reintegration_status", None)
    status = status if isinstance(status, Mapping) else {}
    if (
        state.get("state") == WorkflowState.AGENT_WORKING.value
        and state.get("worker_id") == self.workflow.worker_id
        and (
            checkout.get("origin_main_refresh_required") is True
            or status.get("status") == "main_commit_unavailable"
        )
    ):
        return "prepare_task_checkout"
    if status.get("status") == "required":
        return "integrate_current_main"

    if (
        state.get("state") == WorkflowState.AGENT_WORKING.value
        and state.get("phase") == WorkflowPhase.DELIVERY_EVIDENCE.value
        and checkout.get("status") == "ready"
    ):
        from .downstream_resilience import validation_plan_for

        task = observation.get("task")
        plan = (
            validation_plan_for(self.checkout, task)
            if isinstance(task, Mapping)
            else None
        )
        if plan is not None:
            completed = {
                item.get("test_platform")
                for item in self.state.get("validation_manifests") or []
                if isinstance(item, Mapping)
            }
            if not set(plan["required_test_platforms"]).issubset(completed):
                return "run_authoritative_unity_test"
    return _normalize_next_action(action)


def _patched_search_repository(
    self: Any,
    *,
    query: str,
    prefixes: Iterable[str] = ("Assets/",),
    limit: int = 100,
) -> dict[str, Any]:
    if isinstance(prefixes, (str, bytes)):
        raise DownstreamPipelineError(
            "repository prefixes must be a non-empty list of safe paths"
        )
    values = list(prefixes)
    if not values:
        raise DownstreamPipelineError(
            "repository prefixes must contain at least one safe path"
        )
    return _ORIGINALS["search_repository"](
        self,
        query=query,
        prefixes=values,
        limit=limit,
    )


def _task_contract_at(controller: Any, commit: str, path: str) -> dict[str, Any]:
    result = _git(
        controller.command_runner,
        controller.checkout,
        "show",
        f"{commit}:{path}",
        check=False,
    )
    if result.returncode != 0:
        raise DownstreamPipelineError(
            f"task contract is missing while reconstructing integration authority: {path}"
        )
    try:
        value = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DownstreamPipelineError(
            "task contract is invalid while reconstructing integration authority"
        ) from exc
    if not isinstance(value, dict):
        raise DownstreamPipelineError(
            "task contract is not an object while reconstructing integration authority"
        )
    return value


def _automation_receipt_from_issue(controller: Any, commit: str) -> dict[str, Any] | None:
    """Rebuild an automation-only receipt from one durable Issue event and Git."""

    service = controller.workflow.issue_workflow
    if service is None:
        return None
    snapshot = service.find(controller.task_id)
    if snapshot is None or not snapshot.valid or snapshot.state is None:
        return None
    candidates = [
        event
        for event in snapshot.events
        if event.event_type is WorkflowEventType.AGENT_LEASE_RELEASED
        and event.details.get("reason") == "automation_only_mainline_reintegration"
        and event.details.get("integrated_commit") == commit
    ]
    if not candidates:
        return None
    if len(candidates) != 1:
        raise DownstreamPipelineError(
            "multiple durable automation-only integration events name the same commit"
        )
    event = candidates[0]
    details = event.details
    prior = details.get("prior_task_head")
    main = details.get("main_head")
    human = details.get("human_validation_preserved_for")
    source_receipt = details.get("integration_receipt_sha256")
    if (
        not isinstance(prior, str)
        or not _SHA40.fullmatch(prior)
        or not isinstance(main, str)
        or not _SHA40.fullmatch(main)
        or not isinstance(human, str)
        or not _SHA40.fullmatch(human)
        or not isinstance(source_receipt, str)
        or not _SHA256.fullmatch(source_receipt)
    ):
        raise DownstreamPipelineError(
            "durable automation-only integration event has invalid identities"
        )
    parents = _git_text(
        controller.command_runner,
        controller.checkout,
        "rev-list",
        "--parents",
        "-n",
        "1",
        commit,
        check=False,
    ).split()
    if parents != [commit, prior, main]:
        raise DownstreamPipelineError(
            "durable automation-only integration event does not match ordered Git parents"
        )

    from . import mainline_reintegration as reintegration

    merge_base = _git_text(
        controller.command_runner,
        controller.checkout,
        "merge-base",
        prior,
        main,
    )
    main_paths = reintegration._diff_paths(
        controller,
        merge_base,
        main,
        label="reconstructed mainline diff",
    )
    task_paths = reintegration._diff_paths(
        controller,
        merge_base,
        prior,
        label="reconstructed task diff",
    )
    observation = getattr(controller, "last_observation", None)
    task = (
        observation.get("task")
        if isinstance(observation, Mapping)
        and isinstance(observation.get("task"), Mapping)
        else {}
    )
    contract_path = str(
        task.get("contract_path") or f"Tasks/{controller.task_id}.yaml"
    )
    contract = _task_contract_at(controller, commit, contract_path)
    classification = reintegration.classify_mainline_drift(
        main_changed_paths=main_paths,
        task_changed_paths=task_paths,
        exclusive_resources=reintegration._resource_paths(
            contract.get("exclusive_resources") or []
        ),
        task_contract_path=contract_path,
    )
    if classification.get("classification") != "automation_only":
        raise DownstreamPipelineError(
            "durable integration event no longer verifies as automation_only"
        )

    exclusive_paths = reintegration._resource_paths(
        contract.get("exclusive_resources") or []
    )
    blob_changed: list[str] = []
    for path in sorted(set(task_paths) | set(exclusive_paths), key=str.casefold):
        before = reintegration._object_id_at(controller, prior, path)
        after = reintegration._object_id_at(controller, commit, path)
        if before != after and (before is not None or after is not None):
            blob_changed.append(path)
    if blob_changed:
        raise DownstreamPipelineError(
            "durable automation-only integration changed task-owned blobs: "
            + ", ".join(blob_changed)
        )

    payload = {
        "schema_version": reintegration.INTEGRATION_RECEIPT_VERSION,
        "task_id": controller.task_id,
        "branch": snapshot.state.branch,
        "prior_task_head": prior,
        "human_tested_commit": human,
        "main_head": main,
        "merge_base": merge_base,
        "integrated_commit": commit,
        "classification": "automation_only",
        "human_revalidation_required": False,
        "main_changed_paths": classification["main_changed_paths"],
        "task_changed_paths": classification["task_changed_paths"],
        "overlap_paths": classification["overlap_paths"],
        "exclusive_overlap_paths": classification["exclusive_overlap_paths"],
        "non_automation_paths": classification["non_automation_paths"],
        "task_blob_changes_after_merge": [],
        "created_at_utc": event.occurred_at_utc,
        "authority": "durable_issue_event_git_reconstruction",
        "source_event_id": event.event_id,
        "source_integration_receipt_sha256": source_receipt,
    }
    receipt = {**payload, "receipt_sha256": semantic_sha256(payload)}
    existing_base = controller.state.get("delivery_base_commit")
    if existing_base is not None and existing_base != main:
        raise DownstreamPipelineError(
            "reconstructed integration authority conflicts with local delivery base"
        )
    controller.state["mainline_reintegration"] = receipt
    controller.state["delivery_base_commit"] = main
    controller._persist()
    return receipt


def _patched_automation_receipt_for(
    controller: Any,
    commit: str,
) -> dict[str, Any] | None:
    existing = _ORIGINALS["automation_receipt_for"](controller, commit)
    if existing is not None:
        return existing
    return _automation_receipt_from_issue(controller, commit)


def _assert_current_main_integrated(
    controller: Any,
    state: Mapping[str, Any],
) -> None:
    controller._assert_checkout()
    head = _git_text(
        controller.command_runner,
        controller.checkout,
        "rev-parse",
        "HEAD",
    )
    branch = _git_text(
        controller.command_runner,
        controller.checkout,
        "branch",
        "--show-current",
    )
    if head != state.get("head_commit") or branch != state.get("branch"):
        raise DownstreamPipelineError(
            "checkout differs from the exact branch/commit recorded in the Issue"
        )
    _git(
        controller.command_runner,
        controller.checkout,
        "fetch",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        timeout_seconds=900.0,
    )
    current_main = _git_text(
        controller.command_runner,
        controller.checkout,
        "rev-parse",
        "origin/main",
    )
    if (
        _git(
            controller.command_runner,
            controller.checkout,
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


def _patched_assert_human_tested_head(
    self: Any,
    state: Mapping[str, Any],
) -> None:
    _assert_current_main_integrated(self, state)
    return _ORIGINALS["assert_human_tested_head"](self, state)


def _same_state_rejection_identity(controller: Any) -> tuple[str, dict[str, Any]]:
    underlying = getattr(controller, "_controller", controller)
    observation = getattr(underlying, "last_observation", None)
    if not isinstance(observation, Mapping):
        observation = underlying.observe()
    state = _workflow_state(observation)
    checkout = observation.get("checkout")
    checkout = checkout if isinstance(checkout, Mapping) else {}
    downstream = _downstream_state(observation)
    payload = {
        "state_version": state.get("state_version"),
        "state": state.get("state"),
        "phase": state.get("phase"),
        "next_action": _normalize_next_action(downstream.get("next_action")),
        "checkout_status": checkout.get("status"),
        "checkout_head": checkout.get("head_commit"),
    }
    return semantic_sha256(payload), payload


def _record_same_state_rejection(
    controller: Any,
    *,
    action: str,
    error: BaseException,
    threshold: int = 3,
) -> bool:
    from . import downstream_resilience as resilience

    identity, payload = _same_state_rejection_identity(controller)
    active = getattr(controller, "_same_state_rejection_identity", None)
    count = (
        int(getattr(controller, "_same_state_rejection_count", 0)) + 1
        if active == identity
        else 1
    )
    controller._same_state_rejection_identity = identity
    controller._same_state_rejection_count = count
    if count < threshold:
        return False
    detail = _short(error, limit=900)
    released = resilience._release_active_lease(
        controller,
        reason="same_state_action_rejection_streak",
        details={
            "action": action,
            "error_type": type(error).__name__,
            "error": detail,
            "state_rejection_identity": identity,
            "same_state_rejection_count": count,
            **payload,
        },
    )
    if released:
        controller._terminal_reasons = [
            f"{count} deterministic actions were rejected without workflow progress: {detail}"
        ]
        controller._resilience_terminal_status = (
            "same_state_action_rejection_streak"
        )
        progress = getattr(controller, "_progress", None)
        if progress is not None:
            progress.emit(
                "same_state_action_rejection_streak",
                "Several different actions were rejected without workflow progress; the lease was released",
                action=action,
                error=detail,
                same_state_rejection_count=count,
                state_rejection_identity=identity,
            )
    return released


def _patched_record_action_rejection(
    self: Any,
    *,
    action: str,
    error: BaseException,
) -> bool:
    if _ORIGINALS["record_action_rejection"](
        self,
        action=action,
        error=error,
    ):
        return True
    return _record_same_state_rejection(
        self,
        action=action,
        error=error,
    )


def _patch_goal_rules(openai_downstream: Any) -> None:
    rules = openai_downstream._GOAL_AND_RULES
    rules = rules.replace(
        "- Read the Issue log, task contract, Unity testing policy, and programmer-language policy.\n",
        "- The host has already loaded and validated the committed Unity policy. Do not search for a second policy.\n",
    )
    rules = rules.replace(
        "- Select exact Unity test filters from committed tests and run every required platform.\n",
        "- When downstream.authoritative_test_plan exists, use its exact platform/filter pair without inference or repository discovery.\n",
    )
    if "The host narrows ALLOWED NEXT ACTIONS" not in rules:
        rules += """
- The host narrows ALLOWED NEXT ACTIONS to the current deterministic state. Choose
  only from that displayed menu; do not perform exploratory reads when one exact
  side-effect action is supplied.
"""
    openai_downstream._GOAL_AND_RULES = rules


def install_downstream_determinism() -> None:
    """Install downstream authority and routing fixes exactly once."""

    global _INSTALLED
    if _INSTALLED:
        return

    from . import codex_supervisor
    from . import downstream_pipeline
    from . import downstream_runtime
    from . import mainline_reintegration
    from . import openai_downstream
    from . import progress
    from .goal_loop_guard import GuardedTaskController

    controller = downstream_runtime.ResumableDownstreamTaskController
    _ORIGINALS.update(
        {
            "decision_schema": codex_supervisor.decision_schema,
            "validate_arguments": SupervisorDecision.validate_arguments,
            "provider_decide": CodexDockerDecisionProvider.decide,
            "compact_history": codex_supervisor.compact_history,
            "render_supervisor_prompt": openai_downstream.render_supervisor_prompt,
            "next_action": controller._next_action,
            "search_repository": controller.search_repository,
            "latest_human_validation": downstream_pipeline.DownstreamTaskController._latest_human_validation,
            "automation_receipt_for": mainline_reintegration._automation_receipt_for,
            "assert_human_tested_head": controller._assert_human_tested_head,
            "record_action_rejection": GuardedTaskController.record_action_rejection,
        }
    )

    codex_supervisor.decision_schema = _patched_decision_schema
    codex_supervisor.compact_history = bounded_history
    SupervisorDecision.validate_arguments = _patched_validate_arguments
    CodexDockerDecisionProvider.decide = _patched_provider_decide

    downstream_pipeline.DownstreamTaskController._latest_human_validation = (
        _authoritative_human_validation
    )
    controller._latest_human_validation = _authoritative_human_validation
    controller._next_action = _patched_next_action
    controller.search_repository = _patched_search_repository
    controller._assert_human_tested_head = _patched_assert_human_tested_head

    mainline_reintegration._automation_receipt_for = (
        _patched_automation_receipt_for
    )
    openai_downstream.render_supervisor_prompt = (
        _patched_render_supervisor_prompt
    )
    GuardedTaskController.record_action_rejection = (
        _patched_record_action_rejection
    )

    _patch_goal_rules(openai_downstream)
    progress._OPERATOR_LABELS["same_state_action_rejection_streak"] = "BLOCKED"
    _INSTALLED = True


__all__ = [
    "allowed_actions_for",
    "bounded_history",
    "install_downstream_determinism",
]
