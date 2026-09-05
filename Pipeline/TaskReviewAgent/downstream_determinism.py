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
    WorkflowActor,
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
# The exact (action, arguments) pair the host derived for a sole forced action.
# Carried separately from the narrowed action menu so the existing zero-argument
# short-circuit keeps its own independent contract, and keyed by action name so
# a derivation can never be applied to a different action.
_FORCED_ARGUMENTS_CONTEXT: ContextVar[tuple[str, Mapping[str, Any]] | None] = (
    ContextVar(
        "nsc_downstream_forced_arguments",
        default=None,
    )
)

_NEXT_ACTION_ALIASES = {
    "run_authoritative_unity_tests": "run_authoritative_unity_test",
    "finalize_delivery_evidence": "finalize_delivery_evidence_and_open_pr",
    "open_pull_request": "finalize_delivery_evidence_and_open_pr",
}

# Actions whose complete arguments the host can derive and validate from durable
# state. A provider adds nothing here: it would only echo values the host already
# owns, which a measured NSC-914 delivery run showed costing 17,808 input tokens
# for acquire_agent_lease and 18,746 for run_authoritative_unity_test.
#
# Derivation is all-or-nothing. A derivation that cannot produce every required
# argument from durable state raises rather than returning None, because falling
# through to the provider is exactly how an inferred Unity filter or an invented
# lease rationale would re-enter the pipeline.
_HOST_DETERMINISTIC_ARGUMENT_ACTIONS = frozenset(
    {
        "acquire_agent_lease",
        "run_authoritative_unity_test",
    }
)

_HOST_DETERMINISTIC_ZERO_ARGUMENT_ACTIONS = frozenset(
    {
        "prepare_task_checkout",
        "integrate_current_main",
        "create_delivery_review_draft",
        "delivery_review_facts",
        "publish_delivery_review",
        "finalize_delivery_evidence_and_open_pr",
        "inspect_or_merge_pull_request",
        "verify_post_merge_and_complete",
    }
)


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


_AUTOMATED_VALIDATION_FIELDS = frozenset(
    {
        "schema_version",
        "authority",
        "repository",
        "repository_private",
        "gauntlet_id",
        "task_id",
        "handoff_event_id",
        "branch",
        "commit",
        "tree",
        "task_contract_sha256",
        "validation_policy_authority",
        "validation_policy_sha256",
        "required_validations",
        "unity_validations",
    }
)


def _authoritative_automated_validation(self: Any) -> dict[str, Any] | None:
    """Resolve exact synthetic validation authority without inventing human approval."""

    automated_type = getattr(
        WorkflowEventType,
        "AUTOMATED_VALIDATION_PASSED",
        None,
    )
    if automated_type is None:
        return None
    service = self.workflow.issue_workflow
    if service is None:
        return None
    snapshot = service.find(self.task_id)
    if snapshot is None or not snapshot.valid or snapshot.state is None:
        return None
    state = snapshot.state
    if state.human_result is not None:
        return None

    matches = [
        event
        for event in reversed(snapshot.events)
        if event.event_type is automated_type
    ]
    if not matches:
        return None
    event = matches[0]
    if event.actor_type is not WorkflowActor.AGENT:
        raise DownstreamPipelineError(
            "automated validation authority was not recorded by an agent"
        )
    details = event.details
    if set(details) != _AUTOMATED_VALIDATION_FIELDS:
        raise DownstreamPipelineError(
            "automated validation event details differ from the strict evidence schema"
        )
    if (
        details.get("schema_version") != "1.0"
        or details.get("authority")
        != "committed_private_synthetic_gauntlet_validation_evidence"
        or details.get("repository_private") is not True
        or details.get("gauntlet_id") != "synthetic-architect-gauntlet-v1"
        or details.get("task_id") != self.task_id
        or details.get("branch") != state.branch
        or details.get("commit") != state.head_commit
        or details.get("task_contract_sha256") != state.task_contract_sha256
    ):
        raise DownstreamPipelineError(
            "automated validation event does not match the current Issue state"
        )

    repository = getattr(service.backend, "repository", None)
    if repository is not None and str(repository).casefold() != str(
        details.get("repository")
    ).casefold():
        raise DownstreamPipelineError(
            "automated validation event targets a different repository"
        )

    task = service.task_loader(self.task_id)
    if not isinstance(task, Mapping):
        raise DownstreamPipelineError("current task contract is unavailable")
    task = dict(task)
    task.setdefault("id", self.task_id)
    if task.get("task_contract_sha256") != state.task_contract_sha256:
        raise DownstreamPipelineError(
            "automated validation event targets a stale task contract"
        )
    from .downstream_resilience import validation_plan_for

    plan = validation_plan_for(self.checkout, task)
    if plan is None:
        raise DownstreamPipelineError(
            "automated validation has no committed validation policy"
        )
    if (
        plan.get("policy_sha256") != details.get("validation_policy_sha256")
        or plan.get("authority") != details.get("validation_policy_authority")
    ):
        raise DownstreamPipelineError(
            "automated validation event targets a stale validation policy"
        )
    expected_required = sorted(
        (
            {
                "test_platform": platform,
                "test_filter": test_filter,
            }
            for platform, test_filter in plan["test_filters"].items()
        ),
        key=lambda item: (item["test_platform"], item["test_filter"]),
    )
    if details.get("required_validations") != expected_required:
        raise DownstreamPipelineError(
            "automated validation event does not match the committed test plan"
        )

    head = _git_text(self.command_runner, self.checkout, "rev-parse", "HEAD")
    tree = _git_text(
        self.command_runner,
        self.checkout,
        "rev-parse",
        f"{head}^{{tree}}",
    )
    branch = _git_text(
        self.command_runner,
        self.checkout,
        "branch",
        "--show-current",
    )
    if (
        head != details.get("commit")
        or tree != details.get("tree")
        or branch != details.get("branch")
    ):
        raise DownstreamPipelineError(
            "automated validation event does not match the current checkout"
        )
    return {
        "kind": "automated",
        "result": "pass",
        "tested_commit": head,
        "tree": tree,
        "event_id": event.event_id,
        "actor_id": event.actor_id,
        "policy_authority": plan["authority"],
        "policy_sha256": plan["policy_sha256"],
        "handoff_event_id": details["handoff_event_id"],
        "details": dict(details),
        "authority": "validated_automated_workflow_event_and_committed_policy",
    }


def _authoritative_validation(self: Any) -> dict[str, Any] | None:
    human = _authoritative_human_validation(self)
    if human is not None:
        return {"kind": "human", **human}
    return _authoritative_automated_validation(self)


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
    if self.action == "list_repository_files":
        prefix = values.get("prefix")
        if isinstance(prefix, str) and prefix.strip() in ("", ".", "./"):
            values["prefix"] = "."
    if self.action == "search_repository":
        prefixes = values.get("prefixes")
        if isinstance(prefixes, (list, tuple)):
            values["prefixes"] = [
                "."
                if isinstance(item, str) and item.strip() in ("", ".", "./")
                else item
                for item in prefixes
            ]
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
        task = observation.get("task")
        task_id = (
            task.get("task_id")
            if isinstance(task, Mapping)
            else "unknown task"
        )
        raise DownstreamPipelineError(
            "authoritative validation policy omitted an exact test plan for "
            f"{task_id}; refusing repository discovery or an inferred Unity filter"
        )

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


def _validated_platforms(downstream: Mapping[str, Any]) -> frozenset[str]:
    """Return the platforms whose authoritative manifests are already durable."""

    receipt = downstream.get("receipt")
    receipt = receipt if isinstance(receipt, Mapping) else {}
    manifests = receipt.get("validation_manifests")
    if not isinstance(manifests, list):
        return frozenset()
    return frozenset(
        item.get("test_platform")
        for item in manifests
        if isinstance(item, Mapping) and isinstance(item.get("test_platform"), str)
    )


def _forced_unity_test_arguments(
    observation: Mapping[str, Any],
    downstream: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive the exact platform/filter pair from the committed validation plan.

    `_patched_observe` already publishes `authoritative_test_plan` from
    `validation_plan_for`, and `_patched_render_supervisor_prompt` already pasted
    the same pair into the prompt as a host-authorized plan. The values are
    therefore durable, not judgmental, and are taken straight from that plan.

    The plan's platform order is committed, so when several platforms remain the
    first outstanding one is a deterministic choice and the loop covers the rest
    on later turns. Only a missing plan, no outstanding platform, or a
    missing/blank filter is genuinely underdetermined, and each of those raises.
    """

    plan = downstream.get("authoritative_test_plan")
    task = observation.get("task")
    task_id = task.get("task_id") if isinstance(task, Mapping) else None
    label = task_id if isinstance(task_id, str) and task_id else "this task"
    if not isinstance(plan, Mapping):
        raise DownstreamPipelineError(
            "authoritative validation policy omitted an exact test plan for "
            f"{label}; refusing repository discovery or an inferred Unity filter"
        )
    platforms = plan.get("required_test_platforms")
    filters = plan.get("test_filters")
    if (
        not isinstance(platforms, list)
        or not platforms
        or any(not isinstance(item, str) or not item for item in platforms)
        or not isinstance(filters, Mapping)
    ):
        raise DownstreamPipelineError(
            "authoritative test plan for "
            f"{label} is malformed; refusing an inferred Unity platform or filter"
        )
    validated = _validated_platforms(downstream)
    outstanding = [item for item in platforms if item not in validated]
    if not outstanding:
        raise DownstreamPipelineError(
            "every required authoritative platform for "
            f"{label} already has durable evidence; refusing a redundant Unity run"
        )
    platform = outstanding[0]
    test_filter = filters.get(platform)
    if not isinstance(test_filter, str) or not test_filter.strip():
        raise DownstreamPipelineError(
            "authoritative test plan for "
            f"{label} has no exact filter for {platform}; refusing an inferred filter"
        )
    return {"test_platform": platform, "test_filter": test_filter}


def _forced_lease_arguments(
    observation: Mapping[str, Any],
    downstream: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive fixed, auditable lease prose from durable state.

    `planned_approach` and `expected_validation` are recorded rationale, not
    decisions: the host has already established that the managed Issue is
    agent_ready and that this lease is the only available action. Paying a
    provider to phrase that is cost without authority, so the text is generated
    deterministically and names exactly the durable facts it was derived from.
    """

    state = _workflow_state(observation)
    task = observation.get("task")
    task_id = task.get("task_id") if isinstance(task, Mapping) else None
    label = task_id if isinstance(task_id, str) and task_id else "the managed task"
    phase = state.get("phase")
    phase_label = phase if isinstance(phase, str) and phase else "the recorded phase"
    planned_approach = (
        f"Deterministic downstream continuation for {label} in phase "
        f"{phase_label}. The managed Issue is agent_ready and the downstream "
        "pipeline names acquire_agent_lease as the only available action, so the "
        "host acquired the lease without provider judgment."
    )
    if phase == WorkflowPhase.DELIVERY_EVIDENCE.value:
        plan = downstream.get("authoritative_test_plan")
        pairs: list[str] = []
        if isinstance(plan, Mapping):
            platforms = plan.get("required_test_platforms")
            filters = plan.get("test_filters")
            if isinstance(platforms, list) and isinstance(filters, Mapping):
                pairs = [
                    f"{item} filter {filters.get(item)}"
                    for item in platforms
                    if isinstance(item, str)
                    and isinstance(filters.get(item), str)
                    and filters.get(item)
                ]
        expected_validation = (
            "Authoritative Unity validation against the committed validation "
            "policy (" + "; ".join(pairs) + "), then a delivery review proposal "
            "for Vincent."
            if pairs
            else (
                "Authoritative Unity validation against the committed validation "
                "policy, then a delivery review proposal for Vincent."
            )
        )
    else:
        expected_validation = (
            "Merge closeout verification of the already-approved delivery "
            "evidence: approval, evidence commit, pull request, merge, and "
            "post-merge conformance."
        )
    return {
        "planned_approach": planned_approach,
        "expected_validation": expected_validation,
    }


def forced_action_arguments(
    action: str,
    observation: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return the complete host-derived arguments for one sole forced action.

    Returns ``None`` only when the action is not host-derivable at all. An action
    that should be derivable but whose durable state is missing, ambiguous, or
    invalid raises instead, so no such state can quietly fall back to the
    provider and receive invented values.
    """

    if action in _HOST_DETERMINISTIC_ZERO_ARGUMENT_ACTIONS:
        return {}
    if action not in _HOST_DETERMINISTIC_ARGUMENT_ACTIONS:
        return None
    downstream = _downstream_state(observation)
    if action == "run_authoritative_unity_test":
        return _forced_unity_test_arguments(observation, downstream)
    if action == "acquire_agent_lease":
        return _forced_lease_arguments(observation, downstream)
    return None


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
    # Derive the sole forced action's arguments from the same observation the
    # prompt was built from, so the decision cannot use a later, different one.
    forced = (
        forced_action_arguments(selected[0], observation)
        if len(selected) == 1
        else None
    )
    _FORCED_ARGUMENTS_CONTEXT.set(
        None if forced is None else (selected[0], forced)
    )
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
    forced = _FORCED_ARGUMENTS_CONTEXT.get()
    try:
        arguments: dict[str, Any] | None = None
        if len(actual) == 1:
            if forced is not None and forced[0] == actual[0]:
                arguments = dict(forced[1])
            elif actual[0] in _HOST_DETERMINISTIC_ZERO_ARGUMENT_ACTIONS:
                arguments = {}
        if arguments is not None:
            self.last_usage = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "authority": "deterministic_host_single_action",
            }
            return SupervisorDecision(
                task_id=task_id,
                action=actual[0],
                arguments=arguments,
                rationale=(
                    "Deterministic host state permits exactly this action and "
                    "the host derived every required argument from durable "
                    "state; no provider judgment is required."
                ),
            )
        return _ORIGINALS["provider_decide"](
            self,
            task_id=task_id,
            turn=turn,
            prompt=prompt,
            allowed_actions=actual,
        )
    finally:
        _ALLOWED_ACTION_CONTEXT.set(None)
        _FORCED_ARGUMENTS_CONTEXT.set(None)


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
    original_error: DownstreamPipelineError | None = None
    try:
        return _ORIGINALS["assert_human_tested_head"](self, state)
    except DownstreamPipelineError as original:
        message = str(original)
        if not (
            "human PASS" in message
            or "original human PASS" in message
        ):
            raise
        original_error = original
    authority = _authoritative_automated_validation(self)
    if authority is None or authority.get("tested_commit") != state.get("head_commit"):
        assert original_error is not None
        raise original_error
    existing = self.state.get("validation_authority")
    if existing is not None and existing != authority:
        raise DownstreamPipelineError(
            "automated validation authority changed after downstream work began"
        )
    if existing is None:
        self.state["validation_authority"] = authority
    current_main = _git_text(
        self.command_runner,
        self.checkout,
        "rev-parse",
        "origin/main",
    )
    if current_main == state.get("head_commit"):
        raise DownstreamPipelineError(
            "automated-validated task branch contains no commits beyond current main"
        )
    existing_base = self.state.get("delivery_base_commit")
    if existing_base is not None and existing_base != current_main:
        raise DownstreamPipelineError(
            "origin/main changed after authoritative downstream work began. "
            "Integrate current main and repeat automated validation."
        )
    if existing_base is None:
        self.state["delivery_base_commit"] = current_main
    self._persist()


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
            "latest_validation_authority": downstream_pipeline.DownstreamTaskController._latest_validation_authority,
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
    downstream_pipeline.DownstreamTaskController._latest_validation_authority = (
        _authoritative_validation
    )
    controller._latest_human_validation = _authoritative_human_validation
    controller._latest_validation_authority = _authoritative_validation
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
