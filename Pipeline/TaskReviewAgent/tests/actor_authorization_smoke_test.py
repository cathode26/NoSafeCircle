#!/usr/bin/env python3
"""Deterministic tests for actor authorization and human-result trust boundaries.

The repository is public. These tests prove that agent-authored instructional
text can never parse as human authority, that a human validation result counts
only when the authorized human operator posts it after the current handoff for
the exact handoff commit, and that outside public Issue authors and commenters
cannot initialize, approve, unblock, complete, or corrupt a managed task.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.actor_policy import (  # noqa: E402
    ActorPolicyError,
    actor_login,
    default_actor_policy,
    normalize_login,
    parse_actor_policy,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowContractError,
    find_human_validation_result,
    parse_events,
    parse_human_validation_result,
    parse_state,
    strip_fenced_blocks,
    initial_state,
    labels_for_state,
    update_issue_body,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
    _find_candidates,
    render_contract_body,
)

TASK_ID = "NSC-777"
OTHER_TASK_ID = "NSC-778"
CONTRACT_HASH = "a" * 64
SOURCE_HEAD = "1" * 40
HANDOFF_HEAD = "2" * 40
WRONG_HEAD = "3" * 40
CHECKOUT = r"C:\NSC\NSC\NSC-777"
BRANCH = "nsc-777-actor-authorization"
HUMAN = {"login": "cathode26"}
BOT = {"login": "github-actions[bot]"}
OUTSIDER = {"login": "drive-by-account"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def task(task_id: str = TASK_ID, resource: str = "unity-scene:Assets/Scenes/Shared.unity") -> dict:
    return {
        "id": task_id,
        "title": f"Actor authorization fixture {task_id}",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Prove actor authorization.",
        "depends_on": [],
        "exclusive_resources": [resource],
        "acceptance_criteria": [],
        "completion_gates": [],
        "task_contract_sha256": CONTRACT_HASH if task_id == TASK_ID else "b" * 64,
    }


def handed_off_service() -> tuple[MemoryIssueBackend, IssueWorkflowService, int, str]:
    """Create a managed Issue in human_action_required with a real handoff."""

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
        planned_approach="Implement and hand off.",
        expected_validation="Vincent validates in Unity.",
        now="2026-08-29T09:00:00Z",
    )
    service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=HANDOFF_HEAD,
        checkout_path=CHECKOUT,
        implementation_summary="Implemented the synthetic behavior.",
        completed_checks=("Branch pushed.",),
        human_steps=("Open Unity.", "Verify the behavior."),
        expected_result="The behavior passes.",
        now="2026-08-29T09:01:00Z",
    )
    snapshot = service.find(TASK_ID)
    require(snapshot is not None and snapshot.state is not None, "handoff fixture missing")
    require(snapshot.state.last_event_id is not None, "handoff event missing")
    return backend, service, snapshot.issue_number, snapshot.state.last_event_id


def pass_body(commit: str = HANDOFF_HEAD) -> str:
    return (
        "## Human validation result\n\n"
        "Result: PASS\n"
        f"Tested commit: `{commit}`\n\n"
        "Completed steps:\n- Entered Play Mode.\n"
    )


def fail_body(commit: str = HANDOFF_HEAD) -> str:
    return (
        "## Human validation result\n\n"
        "Result: FAIL\n"
        f"Tested commit: `{commit}`\n\n"
        "Failed step:\nThe door never opened.\n"
    )


def test_fenced_handoff_template_never_parses() -> None:
    fenced_placeholder = (
        "```text\n## Human validation result\n\n"
        "Result: <PASS or FAIL>\nTested commit: <40-character commit SHA>\n```\n"
    )
    require(
        parse_human_validation_result(fenced_placeholder) is None,
        "placeholder template parsed as a human result",
    )
    fenced_real = (
        "Instructions:\n\n```text\n## Human validation result\n\n"
        f"Result: PASS\nTested commit: `{HANDOFF_HEAD}`\n```\n"
    )
    require(
        parse_human_validation_result(fenced_real) is None,
        "fenced instructional PASS parsed as a human result",
    )
    unterminated = f"```\nResult: PASS\nTested commit: `{HANDOFF_HEAD}`\n"
    require(
        parse_human_validation_result(unterminated) is None,
        "unterminated fence did not fail closed",
    )
    require(
        strip_fenced_blocks("before\n```text\nquoted\n```\nafter") == "before\nafter",
        "fence stripping changed unfenced text",
    )
    # A four-backtick outer fence quoting a triple-backtick block is ONE fenced
    # region: the inner ``` lines must not close the outer fence early and let
    # quoted Result/Tested commit text leak back into parsing.
    four_backtick = (
        "Quoting the whole handoff for reference:\n\n"
        "````markdown\n"
        "```text\n"
        "## Human validation result\n\n"
        f"Result: PASS\nTested commit: `{HANDOFF_HEAD}`\n"
        "```\n"
        f"Result: PASS\nTested commit: `{HANDOFF_HEAD}`\n"
        "````\n"
    )
    require(
        parse_human_validation_result(four_backtick) is None,
        "a three-backtick line closed a four-backtick outer fence early",
    )
    tilde_fence = f"~~~\nResult: FAIL\nTested commit: `{HANDOFF_HEAD}`\n~~~\n"
    require(
        parse_human_validation_result(tilde_fence) is None,
        "tilde-fenced quoted text parsed as a human result",
    )
    mixed_markers = (
        f"~~~\nResult: PASS\nTested commit: `{HANDOFF_HEAD}`\n```\nstill quoted\n"
    )
    require(
        parse_human_validation_result(mixed_markers) is None,
        "a backtick line closed a tilde fence",
    )
    # Unfenced real PASS and FAIL results must still parse.
    for body, expected in ((pass_body(), "pass"), (fail_body(), "fail")):
        parsed = parse_human_validation_result(body)
        require(
            parsed is not None and parsed.result == expected,
            f"unfenced real {expected.upper()} result no longer parses",
        )
        require(parsed.tested_commit == HANDOFF_HEAD, "tested commit lost in parsing")

    backend, _, issue_number, _ = handed_off_service()
    handoff_comment = backend.comments[issue_number][-1]["body"]
    require("Human validation result" in handoff_comment, "handoff template missing")
    require(
        parse_human_validation_result(handoff_comment) is None,
        "the real agent handoff comment itself parsed as a human result",
    )


def test_actor_policy_never_collapses_bot_and_human_identities() -> None:
    policy = default_actor_policy()
    require(policy.is_authorized_human("cathode26"), "cathode26 is not an authorized human")
    require(policy.is_authorized_human("Cathode26"), "case folding does not authorize Cathode26")
    require(
        not policy.is_authorized_human("cathode26[bot]"),
        "removing a [bot] suffix granted human authority",
    )
    require(
        not policy.is_authorized_actor("cathode26[bot]"),
        "cathode26[bot] was treated as an authorized actor",
    )
    require(
        normalize_login("Cathode26[Bot]") == "cathode26[bot]",
        "normalization must fold case only, never strip a [bot] suffix",
    )
    for login in ("github-actions", "github-actions[bot]", "GitHub-Actions[Bot]"):
        require(
            policy.is_authorized_automation(login),
            f"automation alias {login!r} not recognized",
        )
        require(
            not policy.is_authorized_human(login),
            f"automation login {login!r} was treated as human",
        )

    def rejects(value: object, fragment: str) -> None:
        try:
            parse_actor_policy(value)
        except ActorPolicyError as exc:
            require(fragment in str(exc), f"unexpected policy error for {value!r}: {exc}")
        else:
            raise AssertionError(f"malformed/ambiguous policy was accepted: {value!r}")

    base = {
        "schema_version": "1.0",
        "authorized_human_logins": ["cathode26"],
        "authorized_automation_logins": ["github-actions", "github-actions[bot]"],
    }
    require(
        parse_actor_policy(base).is_authorized_human("cathode26"),
        "well-formed policy was rejected",
    )
    rejects({**base, "authorized_human_logins": ["cathode26", "Cathode26"]}, "duplicate")
    rejects(
        {**base, "authorized_human_logins": ["cathode26", "github-actions"]},
        "both human and automation",
    )
    rejects({**base, "authorized_human_logins": ["  "]}, "empty identity")
    rejects({**base, "authorized_human_logins": []}, "non-empty array")
    rejects({**base, "authorized_automation_logins": [42]}, "strings")
    rejects({**base, "schema_version": "9.9"}, "schema_version")
    rejects("not-a-policy", "JSON object")


def test_authorized_human_pass_and_fail_are_parsed() -> None:
    for body, expected in ((pass_body(), "pass"), (fail_body(), "fail")):
        backend, _, issue_number, handoff_event = handed_off_service()
        backend.comments[issue_number].append(
            {"id": 900, "author": HUMAN, "body": body}
        )
        found, reasons = find_human_validation_result(
            backend.comments[issue_number],
            after_event_id=handoff_event,
            expected_commit=HANDOFF_HEAD,
        )
        require(found is not None and found.result == expected, f"{expected} not accepted: {reasons}")
        require(found.tested_commit == HANDOFF_HEAD, "tested commit not bound")

    # The REST payload shape (user.login) carries the same authority.
    backend, _, issue_number, handoff_event = handed_off_service()
    backend.comments[issue_number].append(
        {"id": 901, "user": {"login": "cathode26"}, "body": pass_body()}
    )
    found, _ = find_human_validation_result(
        backend.comments[issue_number],
        after_event_id=handoff_event,
        expected_commit=HANDOFF_HEAD,
    )
    require(found is not None, "REST-shape human author was rejected")


def test_result_before_handoff_is_rejected() -> None:
    backend, _, issue_number, handoff_event = handed_off_service()
    # A stale PASS that predates the current handoff comment must not count.
    backend.comments[issue_number].insert(
        0, {"id": 890, "author": HUMAN, "body": pass_body()}
    )
    found, _ = find_human_validation_result(
        backend.comments[issue_number],
        after_event_id=handoff_event,
        expected_commit=HANDOFF_HEAD,
    )
    require(found is None, "a result posted before the handoff was accepted")

    # When the handoff comment cannot even be located, nothing is accepted.
    found, reasons = find_human_validation_result(
        [{"id": 1, "author": HUMAN, "body": pass_body()}],
        after_event_id="f" * 64,
        expected_commit=HANDOFF_HEAD,
    )
    require(found is None and reasons, "missing handoff anchor did not fail closed")


def test_result_for_wrong_commit_is_rejected() -> None:
    backend, _, issue_number, handoff_event = handed_off_service()
    backend.comments[issue_number].append(
        {"id": 900, "author": HUMAN, "body": pass_body(WRONG_HEAD)}
    )
    found, reasons = find_human_validation_result(
        backend.comments[issue_number],
        after_event_id=handoff_event,
        expected_commit=HANDOFF_HEAD,
    )
    require(found is None, "a result for the wrong commit was accepted")
    require(any(WRONG_HEAD in item for item in reasons), "wrong-commit diagnostic missing")


def test_agent_or_workflow_authored_pass_is_rejected() -> None:
    backend, _, issue_number, handoff_event = handed_off_service()
    backend.comments[issue_number].append(
        {"id": 900, "author": BOT, "body": pass_body()}
    )
    found, reasons = find_human_validation_result(
        backend.comments[issue_number],
        after_event_id=handoff_event,
        expected_commit=HANDOFF_HEAD,
    )
    require(found is None, "an automation-authored PASS was accepted as human authority")
    require(
        any("github-actions" in item for item in reasons),
        "automation rejection diagnostic missing",
    )
    # A GraphQL-shaped bot login (no [bot] suffix) is the same automation identity.
    policy = default_actor_policy()
    require(policy.is_authorized_automation("github-actions"), "GraphQL bot login unrecognized")
    require(not policy.is_authorized_human("github-actions"), "bot treated as human")
    require(not policy.is_authorized_human("github-actions[bot]"), "bot treated as human")

    backend, _, issue_number, handoff_event = handed_off_service()
    backend.comments[issue_number].append(
        {"id": 901, "author": OUTSIDER, "body": pass_body()}
    )
    found, reasons = find_human_validation_result(
        backend.comments[issue_number],
        after_event_id=handoff_event,
        expected_commit=HANDOFF_HEAD,
    )
    require(found is None, "an outside commenter's PASS was accepted")
    require(any("drive-by-account" in item for item in reasons), "outsider diagnostic missing")


def test_unauthorized_comments_never_poison_the_event_chain() -> None:
    backend, service, issue_number, _ = handed_off_service()
    baseline_events = parse_events(backend.comments[issue_number])
    # Ordinary public chatter without workflow markers must not disturb anything.
    backend.comments[issue_number].append(
        {"id": 700, "author": OUTSIDER, "body": "Nice progress on this feature!"}
    )
    require(
        service.observe(TASK_ID)["status"] == "human_action_required",
        "plain public comment corrupted the workflow",
    )
    # A copied workflow-event block from an unauthorized or authorless comment
    # creates no workflow authority AND must not invalidate the otherwise valid
    # authorized chain — otherwise any public commenter could brick the task.
    forged = backend.comments[issue_number][0]["body"]
    backend.comments[issue_number].append(
        {"id": 701, "author": OUTSIDER, "body": forged}
    )
    backend.comments[issue_number].append({"id": 702, "body": forged})
    ignored: list[str] = []
    events = parse_events(
        backend.comments[issue_number], ignored_diagnostics=ignored
    )
    require(
        events == baseline_events,
        "an ignored authority-shaped comment altered the event chain",
    )
    require(
        any("drive-by-account" in item and "701" in item for item in ignored),
        f"ignored-comment diagnostic missing login/comment: {ignored}",
    )
    require(
        any("no author identity" in item and "702" in item for item in ignored),
        f"authorless-comment diagnostic missing: {ignored}",
    )
    observed = service.observe(TASK_ID)
    require(
        observed["status"] == "human_action_required",
        f"an untrusted comment invalidated the managed Issue: {observed}",
    )
    diagnostics = observed.get("ignored_comment_diagnostics") or []
    require(
        any("drive-by-account" in item for item in diagnostics),
        f"observation output does not surface the ignored comment: {observed}",
    )

    # An AUTHORIZED malformed workflow event is trusted history gone wrong and
    # still fails closed as a real conflict.
    backend.comments[issue_number].append(
        {
            "id": 703,
            "author": HUMAN,
            "body": '<!-- nsc-workflow-event {"event_id": "tampered"} -->',
        }
    )
    try:
        parse_events(backend.comments[issue_number])
    except WorkflowContractError:
        pass
    else:
        raise AssertionError("authorized malformed event was parsed")
    require(
        service.observe(TASK_ID)["status"] == "conflict",
        "authorized malformed event did not surface a conflict",
    )


def test_unauthorized_issue_cannot_become_managed_task_issue() -> None:
    backend = MemoryIssueBackend()
    tasks = {TASK_ID: task(TASK_ID), OTHER_TASK_ID: task(OTHER_TASK_ID)}
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: tasks[task_id],
        worker_id="agent-a",
    )
    # An outside account creates an Issue that mimics a managed workflow Issue,
    # including a well-formed agent-ready state block and state label.
    backend.author_login = OUTSIDER["login"]
    state = initial_state(
        task_id=TASK_ID,
        task_contract_sha256=CONTRACT_HASH,
        now="2026-08-29T09:10:00Z",
    )
    backend.create_issue(
        title=f"{TASK_ID} — Forged workflow authority",
        body=update_issue_body(
            render_contract_body(tasks[TASK_ID]),
            state,
            next_action="Please pick this up.",
        ),
        labels=labels_for_state(state.state),
        assignees=["cathode26"],
    )
    backend.author_login = "cathode26"

    require(actor_login(backend.list_issues()[0]) == OUTSIDER["login"], "fixture author wrong")
    require(
        _find_candidates(backend.list_issues(), TASK_ID) == [],
        "an unauthorized Issue became a workflow candidate",
    )
    require(service.find(TASK_ID) is None, "an unauthorized Issue became the managed Issue")
    observed = service.observe(TASK_ID)
    require(
        observed["status"] == "agent_ready_uninitialized",
        "an unauthorized Issue was observed as workflow authority",
    )
    require(
        any(
            OUTSIDER["login"] in item
            for item in observed.get("ignored_issue_diagnostics") or []
        ),
        f"observation does not name the unauthorized Issue/login: {observed}",
    )
    require(
        service.list_agent_ready() == [],
        "an unauthorized agent-ready Issue entered the generic queue",
    )
    # It never reserves resources and never blocks a legitimate task: the
    # overlapping-resource task still acquires its lease, while the forged
    # Issue stays visible as a non-authoritative diagnostic naming the login.
    acquired = service.acquire_agent_lease(
        task=tasks[OTHER_TASK_ID],
        source_head=SOURCE_HEAD,
        branch="nsc-778-other",
        checkout_path=r"C:\NSC\NSC\NSC-778",
        planned_approach="Attempt work while a forged Issue exists.",
        expected_validation="The forged Issue is surfaced, not trusted, not blocking.",
        now="2026-08-29T09:11:00Z",
    )
    require(
        acquired["status"] == "acquired",
        f"a forged unauthorized Issue denied service to a legitimate task: {acquired}",
    )
    require(
        any(
            OUTSIDER["login"] in item
            for item in acquired.get("coordination_diagnostics") or []
        ),
        f"lease diagnostics did not name the unauthorized login: {acquired}",
    )
    # The state block itself is intact JSON; only authorship denies it authority.
    require(parse_state(backend.list_issues()[0]["body"]) is not None, "fixture lost its state block")


def test_authorized_fixture_shapes_remain_valid() -> None:
    # gh CLI issue/comment shape (author.login) and REST shape (user.login) are
    # both recognized, and legitimate managed history stays fully valid.
    backend, service, issue_number, _ = handed_off_service()
    for comment in backend.comments[issue_number]:
        comment.pop("author", None)
        comment["user"] = {"login": "cathode26"}
    observed = service.observe(TASK_ID)
    require(
        observed["status"] == "human_action_required",
        f"REST-shape authored history was rejected: {observed['reasons']}",
    )


def main() -> int:
    tests = (
        test_fenced_handoff_template_never_parses,
        test_actor_policy_never_collapses_bot_and_human_identities,
        test_authorized_human_pass_and_fail_are_parsed,
        test_result_before_handoff_is_rejected,
        test_result_for_wrong_commit_is_rejected,
        test_agent_or_workflow_authored_pass_is_rejected,
        test_unauthorized_comments_never_poison_the_event_chain,
        test_unauthorized_issue_cannot_become_managed_task_issue,
        test_authorized_fixture_shapes_remain_valid,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent actor authorization tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
