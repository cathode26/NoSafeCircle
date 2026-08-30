#!/usr/bin/env python3
"""Deterministic tests for the durable GitHub Issue workflow controller."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.dispatch_plan as dispatch_plan_module  # noqa: E402
import Pipeline.TaskReviewAgent.durable_selection as durable_selection_module  # noqa: E402
import Pipeline.TaskReviewAgent.generic_selection as generic_selection_module  # noqa: E402
import Pipeline.TaskReviewAgent.issue_queue as issue_queue_module  # noqa: E402
import Pipeline.TaskReviewAgent.issue_workflow_store as issue_workflow_store_module  # noqa: E402
import Pipeline.TaskReviewAgent.real_workflow as real_workflow_module  # noqa: E402
import Pipeline.TaskReviewAgent.run_pipeline_agent as run_pipeline_agent_module  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    STATE_LABELS,
    IssueWorkflowEvent,
    WorkflowActor,
    WorkflowContractError,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    initial_state,
    labels_for_state,
    parse_events,
    parse_state,
    render_event_comment,
    transition,
    update_issue_body,
    validate_event_chain,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER,
    BLOCKED_KIND_DURABLE_RESOURCE_RESERVATION_CONFLICT,
    REPOSITORY,
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowStoreError,
    MemoryIssueBackend,
    resolve_issue_backend_repository,
)

TASK_ID = "NSC-777"
OTHER_TASK_ID = "NSC-778"
CONTRACT_HASH = "a" * 64
SOURCE_HEAD = "1" * 40
HANDOFF_HEAD = "2" * 40
CHECKOUT = r"C:\NSC\NSC\NSC-777"
BRANCH = "nsc-777-synthetic-workflow"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_error(action, text: str) -> None:
    try:
        action()
    except (WorkflowContractError, IssueWorkflowStoreError) as exc:
        require(text in str(exc), f"unexpected error: {exc}")
    else:
        raise AssertionError(f"expected workflow error containing {text!r}")


def task(
    task_id: str,
    resource: str = "unity-scene:Assets/Scenes/Test.unity",
) -> dict:
    return {
        "id": task_id,
        "title": f"Synthetic workflow task {task_id}",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Prove the durable issue workflow.",
        "depends_on": [],
        "exclusive_resources": [resource],
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "requirement": "The workflow is durable."}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "requirement": "The issue resumes safely."}
        ],
        "task_contract_sha256": CONTRACT_HASH if task_id == TASK_ID else "b" * 64,
    }


def test_state_event_round_trip_and_chain() -> None:
    state = initial_state(
        task_id=TASK_ID,
        task_contract_sha256=CONTRACT_HASH,
        now="2026-08-27T10:00:00Z",
    )
    state, lease = transition(
        state,
        event_type=WorkflowEventType.AGENT_LEASE_ACQUIRED,
        actor_type=WorkflowActor.AGENT,
        actor_id="agent-a",
        to_state=WorkflowState.AGENT_WORKING,
        details={"worker_id": "agent-a", "lease_id": "c" * 64},
        now="2026-08-27T10:01:00Z",
    )
    state, handoff = transition(
        state,
        event_type=WorkflowEventType.HUMAN_HANDOFF_CREATED,
        actor_type=WorkflowActor.AGENT,
        actor_id="agent-a",
        to_state=WorkflowState.HUMAN_ACTION_REQUIRED,
        to_phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
        details={
            "branch": BRANCH,
            "head_commit": HANDOFF_HEAD,
            "checkout_path": CHECKOUT,
        },
        now="2026-08-27T10:02:00Z",
    )
    state, failed = transition(
        state,
        event_type=WorkflowEventType.HUMAN_VALIDATION_FAILED,
        actor_type=WorkflowActor.HUMAN,
        actor_id="cathode26",
        to_state=WorkflowState.AGENT_READY,
        to_phase=WorkflowPhase.REPAIR,
        details={"tested_commit": HANDOFF_HEAD, "result": "fail"},
        now="2026-08-27T10:03:00Z",
    )

    body = update_issue_body(
        "# Original task body\n",
        state,
        next_action="Repair the failure.",
    )
    require(parse_state(body) == state, "state block round trip changed bytes")
    author = {"login": "cathode26"}
    comments = [
        {"author": author, "body": render_event_comment(lease, "lease")},
        {"author": author, "body": render_event_comment(handoff, "handoff")},
        {"author": author, "body": render_event_comment(failed, "failure")},
    ]
    events = parse_events(comments)
    require(validate_event_chain(state, events) == events, "valid chain was rejected")
    require(
        labels_for_state(state.state) == [STATE_LABELS["agent_ready"]],
        "agent-ready label was not selected",
    )

    tampered = json.loads(json.dumps(failed.to_dict()))
    tampered["details"]["result"] = "pass"
    expect_error(lambda: IssueWorkflowEvent.from_dict(tampered), "event_id")

    wrong_state = replace(state, last_event_id="d" * 64)
    expect_error(
        lambda: validate_event_chain(wrong_state, events),
        "final workflow event",
    )


def test_issue_service_handoff_human_result_and_resume() -> None:
    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    acquired = service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Implement the task and commit the exact branch.",
        expected_validation="Run checks, then hand Unity validation to Vincent.",
        now="2026-08-27T11:00:00Z",
    )
    require(acquired["status"] == "acquired", f"lease was not acquired: {acquired}")
    require(
        service.observe(TASK_ID)["status"] == "agent_working_by_worker",
        "working lease not observed",
    )

    handoff = service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Implemented the synthetic gameplay behavior and tests.",
        completed_checks=("TaskGraph validation passed.", "Branch was pushed."),
        human_steps=("Open the project.", "Enter Play Mode.", "Verify the behavior."),
        expected_result="The behavior matches AC-001.",
        now="2026-08-27T11:01:00Z",
    )
    require(handoff["status"] == "human_action_required", "handoff state was wrong")
    require(not service.list_agent_ready(), "human task incorrectly appeared agent-ready")

    wrong_result = """## Human validation result

Result: PASS
Tested commit: `3333333333333333333333333333333333333333`
"""
    expect_error(
        lambda: service.apply_human_result(
            task_id=TASK_ID,
            result_body=wrong_result,
            actor_id="cathode26",
            now="2026-08-27T11:02:00Z",
        ),
        "handoff commit",
    )

    failure_result = f"""## Human validation result

Result: FAIL
Tested commit: `{HANDOFF_HEAD}`

Failed step:
The player crossed the blocker.
"""
    ready = service.apply_human_result(
        task_id=TASK_ID,
        result_body=failure_result,
        actor_id="cathode26",
        now="2026-08-27T11:03:00Z",
    )
    require(ready["status"] == "agent_ready", "human failure did not return agent-ready")
    queue = service.list_agent_ready()
    require(len(queue) == 1, f"agent-ready queue was wrong: {queue}")
    require(
        queue[0]["workflow_state"]["phase"] == "repair",
        "failed human validation did not select repair phase",
    )

    next_agent = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-b",
    )
    resumed = next_agent.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Repair the human-reported blocker on the existing branch.",
        expected_validation="Commit, push, and return a new Unity checklist.",
        now="2026-08-27T11:04:00Z",
    )
    require(resumed["status"] == "acquired", "next agent could not resume the issue")
    require(
        resumed["workflow_state"]["worker_id"] == "agent-b",
        "new agent lease did not record its worker ID",
    )


def test_resource_conflict_and_tampered_history_fail_closed() -> None:
    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Reserve the shared scene.",
        expected_validation="Return it to human review.",
        now="2026-08-27T12:00:00Z",
    )
    blocked = service.acquire_agent_lease(
        task=tasks[OTHER_TASK_ID],
        source_head=SOURCE_HEAD,
        branch="nsc-778-other",
        checkout_path=r"C:\NSC\NSC\NSC-778",
        planned_approach="Attempt overlapping work.",
        expected_validation="Should be blocked.",
        now="2026-08-27T12:01:00Z",
    )
    require(blocked["status"] == "blocked", "resource conflict was not blocked")
    require("overlapping resources" in blocked["reasons"][0], "resource reason missing")
    # MEDIUM-1: a proven overlap against another currently-valid, authorized,
    # managed Issue is exactly the positively-typed benign resource-
    # reservation conflict Stage 3 may retry as ordinary claim_conflict.
    require(
        blocked.get("blocked_kind") == BLOCKED_KIND_DURABLE_RESOURCE_RESERVATION_CONFLICT,
        f"a proven durable resource-reservation overlap must carry the typed benign "
        f"blocked_kind: {blocked}",
    )

    issue_number = next(iter(backend.issues))
    backend.comments[issue_number][0]["body"] = backend.comments[issue_number][0][
        "body"
    ].replace('"worker_id": "agent-a"', '"worker_id": "tampered"')
    observed = service.observe(TASK_ID)
    require(observed["status"] == "conflict", "tampered event history was accepted")

    # An invalid/tampered managed Issue is never benign contention: acquiring
    # against it must fail closed with an exception, never a typed
    # blocked_kind that Stage 3 could retry.
    expect_error(
        lambda: service.acquire_agent_lease(
            task=tasks[TASK_ID],
            source_head=SOURCE_HEAD,
            branch=BRANCH,
            checkout_path=CHECKOUT,
            planned_approach="Resume after tampering.",
            expected_validation="Should fail closed, not retry.",
            now="2026-08-27T12:02:00Z",
        ),
        "invalid workflow state",
    )


def test_durable_ownership_by_other_is_typed_blocked_kind() -> None:
    """MEDIUM-1: another authorized worker's valid agent_working Issue for
    the SAME task, with no exclusive-resource overlap involved, must block
    with the positively-typed BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER --
    exactly the shape Stage 3 maps to ordinary claim_conflict."""

    backend = MemoryIssueBackend()
    solo_task = {
        **task(TASK_ID),
        "exclusive_resources": [],
    }
    tasks = {TASK_ID: solo_task}
    worker_a = IssueWorkflowService(
        backend=backend, task_loader=lambda task_id: tasks[task_id], worker_id="agent-a"
    )
    acquired = worker_a.acquire_agent_lease(
        task=solo_task,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Reserve the task.",
        expected_validation="Held by agent-a.",
        now="2026-08-27T13:00:00Z",
    )
    require(acquired["status"] == "acquired", f"setup lease was not acquired: {acquired}")

    worker_b = IssueWorkflowService(
        backend=backend, task_loader=lambda task_id: tasks[task_id], worker_id="agent-b"
    )
    blocked = worker_b.acquire_agent_lease(
        task=solo_task,
        source_head=SOURCE_HEAD,
        branch="nsc-777-worker-b",
        checkout_path=r"C:\NSC\NSC\NSC-777-worker-b",
        planned_approach="A different worker attempts the same task.",
        expected_validation="Should be blocked as ordinary durable ownership.",
        now="2026-08-27T13:01:00Z",
    )
    require(blocked["status"] == "blocked", f"a different worker's lease attempt was not blocked: {blocked}")
    require(
        blocked.get("blocked_kind") == BLOCKED_KIND_DURABLE_OWNERSHIP_BY_OTHER,
        f"another worker's valid agent_working Issue must carry the typed benign "
        f"blocked_kind: {blocked}",
    )

    # The SAME worker resuming its own lease must never carry a blocked_kind
    # (it is not even blocked -- "resumed" -- so this also proves the
    # blocked_kind is never emitted merely because the state is AGENT_WORKING).
    resumed = worker_a.acquire_agent_lease(
        task=solo_task,
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Resume the held task.",
        expected_validation="Still held by agent-a.",
        now="2026-08-27T13:02:00Z",
    )
    require(resumed["status"] == "resumed", f"the owning worker could not resume: {resumed}")
    require("blocked_kind" not in resumed, f"a successful resume must never carry a blocked_kind: {resumed}")


def test_operational_resource_inspection_failure_is_not_benign() -> None:
    """MEDIUM-1 safety boundary: a task-load failure while scanning another
    Issue's reserved resources is an operational failure, not proven ordinary
    contention, even though a real overlap also exists elsewhere. Mixing one
    unprovable conflict into the result must suppress blocked_kind entirely."""

    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    holder = IssueWorkflowService(
        backend=backend, task_loader=lambda task_id: tasks[task_id], worker_id="agent-a"
    )
    holder.acquire_agent_lease(
        task=tasks[OTHER_TASK_ID],
        source_head=SOURCE_HEAD,
        branch="nsc-778-holder",
        checkout_path=r"C:\NSC\NSC\NSC-778",
        planned_approach="Reserve the shared scene under a different task.",
        expected_validation="Held by agent-a.",
        now="2026-08-27T14:00:00Z",
    )

    def failing_task_loader(task_id: str) -> dict:
        if task_id == OTHER_TASK_ID:
            raise RuntimeError("synthetic committed-task load outage")
        return tasks[task_id]

    challenger = IssueWorkflowService(
        backend=backend, task_loader=failing_task_loader, worker_id="agent-b"
    )
    blocked = challenger.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Attempt the overlapping resource.",
        expected_validation="Should be blocked, but never as benign contention.",
        now="2026-08-27T14:01:00Z",
    )
    require(blocked["status"] == "blocked", f"the resource scan should still block: {blocked}")
    require(
        "blocked_kind" not in blocked,
        f"an operational task-load failure must never be misclassified as benign "
        f"typed contention: {blocked}",
    )


def test_untyped_blocked_state_carries_no_blocked_kind() -> None:
    """MEDIUM-1 safety boundary: a workflow state other than agent_ready or
    agent_working (e.g. human_action_required) is an ordinary, unrelated
    blocked shape and must stay untyped/terminal."""

    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID)}
    service = IssueWorkflowService(
        backend=backend, task_loader=lambda task_id: tasks[task_id], worker_id="agent-a"
    )
    service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Implement the task and commit the exact branch.",
        expected_validation="Run checks, then hand Unity validation to Vincent.",
        now="2026-08-27T15:00:00Z",
    )
    service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Implemented the synthetic gameplay behavior and tests.",
        completed_checks=("TaskGraph validation passed.",),
        human_steps=("Open the project.",),
        expected_result="The behavior matches AC-001.",
        now="2026-08-27T15:01:00Z",
    )

    blocked = service.acquire_agent_lease(
        task=tasks[TASK_ID],
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=CHECKOUT,
        planned_approach="Attempt to re-acquire while awaiting human validation.",
        expected_validation="Should be blocked, but never as benign contention.",
        now="2026-08-27T15:02:00Z",
    )
    require(blocked["status"] == "blocked", f"human_action_required must still block: {blocked}")
    require(
        "blocked_kind" not in blocked,
        f"a non-agent_working blocked state must never carry a blocked_kind: {blocked}",
    )


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(cwd), *args),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=60.0,
    )


def _make_repo(origin: str | None) -> tempfile.TemporaryDirectory:
    """A throwaway local Git repository with an optional 'origin' remote.

    Never contacts a network: 'git init'/'git remote add' only write local
    Git metadata, and no fetch/push/clone is performed.
    """

    tmp = tempfile.TemporaryDirectory(prefix="nsc-repo-binding-")
    root = Path(tmp.name)
    _run_git(root, "init", "--quiet")
    if origin is not None:
        _run_git(root, "remote", "add", "origin", origin)
    return tmp


def test_resolve_repository_from_production_https_origin() -> None:
    """Case A: production checkout origin resolves to cathode26/NoSafeCircle."""

    with _make_repo("https://github.com/cathode26/NoSafeCircle.git") as tmp:
        resolved = resolve_issue_backend_repository(tmp)
        require(resolved == "cathode26/NoSafeCircle", f"unexpected resolution: {resolved}")
        require(resolved == REPOSITORY, "production origin must match the REPOSITORY constant")


def test_resolve_repository_from_disposable_https_origin() -> None:
    """Case B: a disposable Gauntlet origin never resolves to NoSafeCircle."""

    with _make_repo(
        "https://github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
    ) as tmp:
        resolved = resolve_issue_backend_repository(tmp)
        require(
            resolved == "cathode26/orchestrator-gauntlet-stage4-test",
            f"unexpected resolution: {resolved}",
        )
        require(resolved != REPOSITORY, "disposable origin must not resolve to production")


def test_resolve_repository_from_scp_style_ssh_origin() -> None:
    """Case C: SCP-style SSH origin (git@github.com:owner/repo.git)."""

    with _make_repo(
        "git@github.com:cathode26/orchestrator-gauntlet-stage4-test.git"
    ) as tmp:
        resolved = resolve_issue_backend_repository(tmp)
        require(
            resolved == "cathode26/orchestrator-gauntlet-stage4-test",
            f"unexpected SSH resolution: {resolved}",
        )


def test_resolve_repository_from_ssh_url_origin() -> None:
    """Fable Medium-2: the supported ssh://git@github.com/... URL form resolves."""

    with _make_repo(
        "ssh://git@github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
    ) as tmp:
        resolved = resolve_issue_backend_repository(tmp)
        require(
            resolved == "cathode26/orchestrator-gauntlet-stage4-test",
            f"unexpected ssh:// resolution: {resolved}",
        )
        # Constructor-level coverage: a matching explicit repository assertion
        # is accepted for the same supported ssh:// origin form.
        resolved_with_assertion = resolve_issue_backend_repository(
            tmp, repository="cathode26/orchestrator-gauntlet-stage4-test"
        )
        require(
            resolved_with_assertion == "cathode26/orchestrator-gauntlet-stage4-test",
            f"unexpected ssh:// resolution with assertion: {resolved_with_assertion}",
        )


def test_credential_bearing_ssh_origin_fails_safely_without_leaking_secret() -> None:
    """Fable Medium-1: an unsupported ssh://user:secret@... origin must still

    fail closed (it is not one of the three accepted GitHub remote shapes),
    but the embedded credential must never reach the exception text.
    """

    with _make_repo("ssh://user:secret@github.com/owner/repo.git") as tmp:
        try:
            resolve_issue_backend_repository(tmp)
        except IssueWorkflowStoreError as exc:
            message = str(exc)
            require("secret" not in message, f"credential leaked into error: {message}")
            require(
                "not a supported GitHub repository remote" in message,
                f"unexpected error: {message}",
            )
        else:
            raise AssertionError("credential-bearing ssh:// origin must fail closed")


def test_https_credential_origin_remains_redacted() -> None:
    """https://user:secret@... stays redacted when it fails closed."""

    with _make_repo("https://user:secret@gitlab.com/owner/repo.git") as tmp:
        try:
            resolve_issue_backend_repository(tmp)
        except IssueWorkflowStoreError as exc:
            message = str(exc)
            require("secret" not in message, f"credential leaked into error: {message}")
        else:
            raise AssertionError("non-GitHub credentialed origin must fail closed")


def test_https_token_origin_remains_redacted() -> None:
    """https://TOKEN@... (single-value userinfo) stays redacted when it fails closed."""

    with _make_repo("https://ghp_faketoken@gitlab.com/owner/repo.git") as tmp:
        try:
            resolve_issue_backend_repository(tmp)
        except IssueWorkflowStoreError as exc:
            message = str(exc)
            require(
                "ghp_faketoken" not in message, f"token leaked into error: {message}"
            )
        else:
            raise AssertionError("non-GitHub token-bearing origin must fail closed")


def test_resolve_repository_missing_origin_fails_closed() -> None:
    """Case D: no 'origin' remote at all fails closed rather than defaulting."""

    with _make_repo(None) as tmp:
        expect_error(
            lambda: resolve_issue_backend_repository(tmp),
            "no readable Git 'origin' remote",
        )


def test_gh_issue_backend_fails_closed_for_local_filesystem_origin() -> None:
    """Case E: a REAL GhIssueBackend fails closed for a local/bare remote."""

    with _make_repo("/tmp/some/bare/repo.git") as tmp:
        expect_error(
            lambda: GhIssueBackend(source_root=tmp),
            "not a supported GitHub repository remote",
        )


def test_resolve_repository_non_github_remote_fails_closed() -> None:
    """Case F: a well-formed but non-GitHub remote fails closed."""

    with _make_repo("https://gitlab.com/cathode26/NoSafeCircle.git") as tmp:
        expect_error(
            lambda: resolve_issue_backend_repository(tmp),
            "not a supported GitHub repository remote",
        )


def test_resolve_repository_malformed_github_remote_fails_closed() -> None:
    """Case G: a GitHub host URL missing a repository segment fails closed."""

    with _make_repo("https://github.com/cathode26") as tmp:
        expect_error(
            lambda: resolve_issue_backend_repository(tmp),
            "not a supported GitHub repository remote",
        )


def test_explicit_repository_assertion_matching_origin_is_accepted() -> None:
    """Case H: an explicit --repo-style assertion matching origin is accepted."""

    with _make_repo("https://github.com/cathode26/NoSafeCircle.git") as tmp:
        resolved = resolve_issue_backend_repository(tmp, repository="cathode26/NoSafeCircle")
        require(resolved == "cathode26/NoSafeCircle", f"unexpected resolution: {resolved}")
        # A case-insensitive assertion is accepted too, but the origin's own
        # casing remains canonical.
        resolved_case = resolve_issue_backend_repository(
            tmp, repository="Cathode26/NoSafeCircle"
        )
        require(
            resolved_case == "cathode26/NoSafeCircle",
            f"case-insensitive assertion should still resolve to origin casing: {resolved_case}",
        )


def test_explicit_repository_assertion_mismatch_fails_closed() -> None:
    """Case I: a mismatched explicit assertion fails BEFORE any Issue call."""

    with _make_repo(
        "https://github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
    ) as tmp:
        expect_error(
            lambda: resolve_issue_backend_repository(tmp, repository="cathode26/NoSafeCircle"),
            "does not match",
        )


def test_gh_issue_backend_requires_source_root() -> None:
    """Case J: constructing GhIssueBackend with no source_root stays impossible."""

    try:
        GhIssueBackend()  # type: ignore[call-arg]
    except TypeError:
        pass
    else:
        raise AssertionError("GhIssueBackend() without source_root must be impossible")


def test_gh_issue_backend_mismatch_fails_before_any_gh_invocation() -> None:
    """Network-side-effect regression: a repository-assertion mismatch must
    fail during safe construction, before 'gh' is even probed for -- i.e.
    strictly before any possible ensure_labels/list_issues/create_issue/
    update_issue/add_comment side effect."""

    class _ForbiddenShutil:
        @staticmethod
        def which(name: str) -> str | None:
            raise AssertionError(
                f"repository mismatch must fail before probing for {name!r}"
            )

    original_shutil = issue_workflow_store_module.shutil
    issue_workflow_store_module.shutil = _ForbiddenShutil()
    try:
        with _make_repo(
            "https://github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
        ) as tmp:
            expect_error(
                lambda: GhIssueBackend(source_root=tmp, repository="cathode26/NoSafeCircle"),
                "does not match",
            )
    finally:
        issue_workflow_store_module.shutil = original_shutil


def test_production_composition_binds_to_checkout_origin_not_default() -> None:
    """Every real production construction site shares the same, repository-
    bound GhIssueBackend symbol, and a disposable-origin checkout composes a
    backend targeting itself -- never cathode26/NoSafeCircle. Covers Stage 2
    read-only planning (dispatch_plan/durable_selection/generic_selection/
    issue_queue) and Stage 3/4 durable Issue routing (real_workflow/
    run_pipeline_agent). No GitHub network call is made: only 'gh auth
    status' is faked, and every other subprocess call (git) runs for real
    against the local throwaway repository."""

    production_modules = (
        dispatch_plan_module,
        durable_selection_module,
        generic_selection_module,
        issue_queue_module,
        real_workflow_module,
        run_pipeline_agent_module,
    )
    for module in production_modules:
        require(
            module.GhIssueBackend is GhIssueBackend,
            f"{module.__name__} must construct the shared, repository-bound "
            "GhIssueBackend rather than a private copy",
        )

    class _FakeShutil:
        @staticmethod
        def which(name: str) -> str | None:
            return f"/usr/bin/{name}"

    original_shutil = issue_workflow_store_module.shutil
    original_run = issue_workflow_store_module.subprocess.run

    def fake_run(args, **kwargs):
        args_tuple = tuple(args)
        if args_tuple[:1] == ("gh",):
            if args_tuple[:3] == ("gh", "auth", "status"):
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            raise AssertionError(f"unexpected 'gh' invocation in a network-free test: {args}")
        return original_run(args, **kwargs)

    issue_workflow_store_module.shutil = _FakeShutil()
    issue_workflow_store_module.subprocess.run = fake_run
    try:
        with _make_repo(
            "https://github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
        ) as tmp:
            for module in production_modules:
                backend = module.GhIssueBackend(source_root=tmp)
                require(
                    backend.repository == "cathode26/orchestrator-gauntlet-stage4-test",
                    f"{module.__name__} composition bound to {backend.repository!r} "
                    "instead of the checkout origin",
                )
                require(
                    backend.repository != REPOSITORY,
                    f"{module.__name__} composition must never silently target "
                    f"{REPOSITORY}",
                )
    finally:
        issue_workflow_store_module.shutil = original_shutil
        issue_workflow_store_module.subprocess.run = original_run


def main() -> int:
    tests = (
        test_state_event_round_trip_and_chain,
        test_issue_service_handoff_human_result_and_resume,
        test_resource_conflict_and_tampered_history_fail_closed,
        test_durable_ownership_by_other_is_typed_blocked_kind,
        test_operational_resource_inspection_failure_is_not_benign,
        test_untyped_blocked_state_carries_no_blocked_kind,
        test_resolve_repository_from_production_https_origin,
        test_resolve_repository_from_disposable_https_origin,
        test_resolve_repository_from_scp_style_ssh_origin,
        test_resolve_repository_from_ssh_url_origin,
        test_credential_bearing_ssh_origin_fails_safely_without_leaking_secret,
        test_https_credential_origin_remains_redacted,
        test_https_token_origin_remains_redacted,
        test_resolve_repository_missing_origin_fails_closed,
        test_gh_issue_backend_fails_closed_for_local_filesystem_origin,
        test_resolve_repository_non_github_remote_fails_closed,
        test_resolve_repository_malformed_github_remote_fails_closed,
        test_explicit_repository_assertion_matching_origin_is_accepted,
        test_explicit_repository_assertion_mismatch_fails_closed,
        test_gh_issue_backend_requires_source_root,
        test_gh_issue_backend_mismatch_fails_before_any_gh_invocation,
        test_production_composition_binds_to_checkout_origin_not_default,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent issue workflow smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
