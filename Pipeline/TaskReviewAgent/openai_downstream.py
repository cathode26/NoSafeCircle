"""OpenAI supervisor for delivery evidence, conformance, PR merge, and closeout."""

from __future__ import annotations

import os
from typing import Any

from .contracts import TASK_REVIEW_SCHEMA_VERSION, TaskReviewContractError, TaskReviewRequest
from .downstream_runtime import ResumableDownstreamTaskController
from .openai_agent import DEFAULT_MODEL, _json, _require_runtime


class OpenAIDownstreamPipelineError(TaskReviewContractError):
    """Raised when model output disagrees with deterministic downstream state."""


def run_openai_downstream_pipeline(
    request: TaskReviewRequest,
    controller: ResumableDownstreamTaskController,
    *,
    model: str | None = None,
    max_turns: int = 100,
) -> dict[str, Any]:
    """Advance a human-passed task through evidence review and verified merge."""

    Agent, _, Runner, function_tool, pydantic_types = _require_runtime(max_turns)
    BaseModel, ConfigDict = pydantic_types

    class DownstreamOutcomeModel(BaseModel):
        model_config = ConfigDict(extra="forbid")

        schema_version: str
        task_id: str
        status: str
        issue_url: str | None
        branch: str | None
        commit: str | None
        pull_request_url: str | None
        next_action: str
        blockers: list[str]
        authority: str

    observations_before = len(controller.workflow.action_log)

    @function_tool
    def observe_goal_state() -> str:
        """Read TaskGraph, Issue, checkout, validation, evidence, PR, and closeout state."""

        return _json(controller.observe())

    @function_tool
    def acquire_agent_lease(planned_approach: str, expected_validation: str) -> str:
        """Acquire the current delivery/closeout phase for this exact worker."""

        return _json(
            controller.acquire_agent_lease(
                planned_approach=planned_approach,
                expected_validation=expected_validation,
            )
        )

    @function_tool
    def prepare_task_checkout() -> str:
        """Resume or recreate the canonical checkout at the exact recorded branch commit."""

        return _json(controller.prepare_task_checkout())

    @function_tool
    def read_issue_log() -> str:
        """Read the validated workflow events and human comments for this task."""

        return _json(controller.read_issue_log())

    @function_tool
    def list_repository_files(prefix: str = "Assets/", limit: int = 300) -> str:
        """List committed files under one approved downstream read prefix."""

        return _json(controller.list_repository_files(prefix=prefix, limit=limit))

    @function_tool
    def search_repository(
        query: str,
        prefixes: list[str],
        limit: int = 100,
    ) -> str:
        """Search committed Unity/task/policy text without shell or write authority."""

        return _json(
            controller.search_repository(
                query=query,
                prefixes=prefixes,
                limit=limit,
            )
        )

    @function_tool
    def read_repository_file(
        path: str,
        start_line: int = 1,
        end_line: int = 500,
    ) -> str:
        """Read a bounded range from an approved committed repository file."""

        return _json(
            controller.read_repository_file(
                path=path,
                start_line=start_line,
                end_line=end_line,
            )
        )

    @function_tool
    def run_authoritative_unity_test(
        test_platform: str,
        test_filter: str,
    ) -> str:
        """Run one clean manifest-producing Unity EditMode or PlayMode test filter."""

        return _json(
            controller.run_authoritative_unity_test(
                test_platform=test_platform,
                test_filter=test_filter,
            )
        )

    @function_tool
    def create_delivery_review_draft() -> str:
        """Create TaskDelivery's immutable clerical draft from exact validation facts."""

        return _json(controller.create_delivery_review_draft())

    @function_tool
    def delivery_review_facts() -> str:
        """Read exact candidate surfaces, evidence IDs, and gates from the draft."""

        return _json(controller.delivery_review_facts())

    @function_tool
    def create_delivery_review_proposal(
        selected_surfaces: list[dict[str, str]],
        gate_mappings: list[dict[str, Any]],
        approval_notes: str,
    ) -> str:
        """Create a hash-bound proposal; this does not grant human approval."""

        return _json(
            controller.create_delivery_review_proposal(
                selected_surfaces=selected_surfaces,
                gate_mappings=gate_mappings,
                approval_notes=approval_notes,
            )
        )

    @function_tool
    def publish_delivery_review() -> str:
        """Give Vincent the exact proposal and move the Issue to human-owned review."""

        return _json(controller.publish_delivery_review())

    @function_tool
    def finalize_delivery_evidence_and_open_pr() -> str:
        """Use the approved proposal to commit evidence, prove conformance, and open the PR."""

        return _json(controller.finalize_delivery_evidence_and_open_pr())

    @function_tool
    def inspect_or_merge_pull_request() -> str:
        """Inspect checks; release if pending, block on failure, or merge exact passing head."""

        return _json(controller.inspect_or_merge_pull_request())

    @function_tool
    def verify_post_merge_and_complete() -> str:
        """Verify fresh main remains conformant, complete the journal, and close the Issue."""

        return _json(controller.verify_post_merge_and_complete())

    instructions = f"""
You are the No Safe Circle downstream task supervisor for exact task {request.task_id}.

GOAL
Resume the durable managed Issue after Vincent's Unity PASS and advance it through the repository's
existing authority boundaries:
1. authoritative clean Unity validation manifest(s);
2. a TaskDelivery review draft;
3. an exact hash-bound proposal for conformance surfaces, semantic roles, gate evidence, and notes;
4. a human delivery-evidence review recorded in the Issue;
5. after exact approval, strict TaskDelivery finalization;
6. record_delivery packaging, staging validation, evidence commit, push, and TaskGraph conformant;
7. pull-request creation and terminal check inspection;
8. merge with history preserved at the exact expected head; and
9. fresh-main TaskGraph validation, conformant verification, Issue completion, and closeout.

HUMAN AUTHORITY
You may propose delivery mappings, but you may never approve them. The Issue must become a
human-owned delivery review before TaskDelivery finalization. Only a validated APPROVE event whose
Proposal SHA256 matches the current proposal authorizes finalization. REQUEST_CHANGES means create a
new proposal revision after reading the human comment; never reuse the rejected proposal.

OPERATING LOOP
- Always call observe_goal_state first and after lease/checkout state changes.
- Follow downstream.next_action exactly. Never skip a prerequisite.
- Acquire a lease before any downstream side effect. Keep the planned approach concrete.
- Read the Issue log, task contract, Unity testing policy, and Unity programmer language policy.
- To choose Unity filters, list/search/read the committed test files and use exact test class or
  namespace filters that exercise this task. Run every required_test_platform reported by observe.
- A human PASS is not an authoritative automated test. Only run_authoritative_unity_test produces
  validation manifests usable by TaskDelivery.
- Before drafting, ensure each required platform has a passed manifest at the exact human-tested
  commit/tree. Do not change code or integrate main after human testing; a stale base is a blocker.
- After create_delivery_review_draft, inspect every surface candidate, artifact ID, and gate.
- Select only truthful committed conformance surfaces. Give every selected path a concrete semantic
  role. Map each gate to specific evidence IDs and explain why those artifacts prove that gate.
  Do not map every artifact to every gate reflexively.
- create_delivery_review_proposal does not approve anything. Publish it and stop when the managed
  Issue becomes blocked/delivery_evidence with current_actor=human.
- After a validated approval, finalize_delivery_evidence_and_open_pr performs the clerical package,
  exact staging validation, evidence commit/push, TaskGraph conformance check, and PR creation. It
  then releases the lease at the evidence commit. Stop with checks_pending; a future generic run
  will resume automatically.
- On a later merge_closeout lease, inspect_or_merge_pull_request. Pending checks release the lease.
  Failed checks are a real blocker. Passing checks may merge only the exact recorded evidence head
  with merge history preserved.
- After merge, verify_post_merge_and_complete must clone/fetch fresh main, validate the TaskGraph,
  require this task to remain conformant, append the completion event, and close the Issue.
- Never edit game code, task contracts, the GDD, delivery mappings after approval, validation
  manifests, or immutable evidence bytes. Never force-push, squash, rebase, or claim conformance
  before deterministic tools return it.

FINAL OUTPUT
Return schema_version={TASK_REVIEW_SCHEMA_VERSION}, task_id={request.task_id}, and authority exactly
`delivery_evidence_to_verified_merge_closeout`.
Supported statuses are:
- human_delivery_review: waiting for Vincent's exact proposal decision;
- checks_pending: evidence branch and PR are published and the Issue is agent_ready/merge_closeout;
- complete: PR merged and fresh main is conformant;
- blocked or needs_human: a genuine bounded stop.
Copy Issue/branch/commit/PR identities only from deterministic tool results.
""".strip()

    agent = Agent(
        name="No Safe Circle Downstream Delivery Supervisor",
        model=model or os.getenv("TASK_REVIEW_AGENT_MODEL", DEFAULT_MODEL),
        instructions=instructions,
        tools=[
            observe_goal_state,
            acquire_agent_lease,
            prepare_task_checkout,
            read_issue_log,
            list_repository_files,
            search_repository,
            read_repository_file,
            run_authoritative_unity_test,
            create_delivery_review_draft,
            delivery_review_facts,
            create_delivery_review_proposal,
            publish_delivery_review,
            finalize_delivery_evidence_and_open_pr,
            inspect_or_merge_pull_request,
            verify_post_merge_and_complete,
        ],
        output_type=DownstreamOutcomeModel,
    )

    result = Runner.run_sync(
        agent,
        f"Advance {request.task_id} through its current downstream Issue phase.",
        max_turns=max_turns,
    )
    final_output = result.final_output
    if not isinstance(final_output, DownstreamOutcomeModel):
        raise OpenAIDownstreamPipelineError(
            "OpenAI downstream supervisor did not return the required structured output"
        )
    if len(controller.workflow.action_log) <= observations_before:
        raise OpenAIDownstreamPipelineError(
            "OpenAI downstream supervisor returned without observing workflow state"
        )

    payload = final_output.model_dump(mode="json")
    if payload.get("schema_version") != TASK_REVIEW_SCHEMA_VERSION:
        raise OpenAIDownstreamPipelineError("model changed schema_version")
    if payload.get("task_id") != request.task_id:
        raise OpenAIDownstreamPipelineError("model changed task identity")
    if payload.get("authority") != "delivery_evidence_to_verified_merge_closeout":
        raise OpenAIDownstreamPipelineError("model changed authority boundary")

    final_observation = controller.observe()
    coordination = final_observation.get("coordination") or {}
    state = coordination.get("workflow_state") or {}
    status = payload.get("status")
    if status == "human_delivery_review":
        if not (
            state.get("state") == "blocked"
            and state.get("phase") == "delivery_evidence"
            and state.get("current_actor") == "human"
        ):
            raise OpenAIDownstreamPipelineError(
                "model claimed delivery review before deterministic Issue handoff"
            )
    elif status == "checks_pending":
        if not (
            state.get("state") == "agent_ready"
            and state.get("phase") == "merge_closeout"
            and isinstance(state.get("head_commit"), str)
        ):
            raise OpenAIDownstreamPipelineError(
                "model claimed pending checks before durable evidence-head release"
            )
    elif status == "complete":
        if state.get("state") != "complete":
            raise OpenAIDownstreamPipelineError(
                "model claimed completion before deterministic closeout"
            )
    elif status not in ("blocked", "needs_human"):
        raise OpenAIDownstreamPipelineError("model returned an unsupported status")

    fixed = {
        "issue_url": coordination.get("issue_url"),
        "branch": state.get("branch"),
        "commit": state.get("head_commit"),
        "pull_request_url": (
            (final_observation.get("downstream") or {}).get("receipt") or {}
        ).get("pull_request_url"),
    }
    for field, expected in fixed.items():
        if payload.get(field) != expected:
            raise OpenAIDownstreamPipelineError(
                f"model changed final {field}: {payload.get(field)!r} != {expected!r}"
            )
    if status in ("human_delivery_review", "checks_pending", "complete") and payload.get(
        "blockers"
    ):
        raise OpenAIDownstreamPipelineError(f"{status} cannot contain blockers")
    return {**payload, "deterministic_final_state": final_observation}
