#!/usr/bin/env python3
"""Deterministic review-work Issue materialization regressions.

Test classification: pure/component tests plus a temporary-Git production
observation test. Every assertion is a regression-only orchestration invariant;
no Unity asset, real GitHub Issue, claim ref, or NSC-Vincent inbox is touched.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.run_pipeline_agent as run_pipeline_agent_module  # noqa: E402
import Pipeline.TaskReviewAgent.taskgraph_review_issues as review_module  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import TaskReviewContractError  # noqa: E402
from Pipeline.TaskReviewAgent.fresh_dispatch import (  # noqa: E402
    GenericDispatchRetryResult,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)
from Pipeline.TaskReviewAgent.taskgraph_review_issues import (  # noqa: E402
    MANAGED_BLOCK_END,
    MANAGED_BLOCK_START,
    REVIEW_MARKER_TEMPLATE,
    ReviewIssueMaterializationResult,
    TaskGraphReviewIssueError,
    materialize_taskgraph_review_issues,
    observe_taskgraph_review_snapshot,
)


HEAD_A = "a" * 40
HEAD_B = "b" * 40
AUTHORIZED_LOGIN = "cathode26"
OUTSIDER_LOGIN = "drive-by-account"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_task(task_id: str, **overrides: Any) -> dict[str, Any]:
    task = {
        "schema_version": "2.0",
        "id": task_id,
        "title": f"Review fixture {task_id}",
        "contract_revision": 7,
        "contract_disposition": "active",
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "parent": "NSC-001",
        "depends_on": [],
        "exclusive_resources": [],
        "completion_gates": [
            {
                "gate_id": "VAL-UNITY-EDITMODE",
                "requirement": "Run the current Edit Mode validation suite.",
            },
            {
                "gate_id": "VAL-HUMAN-RUNTIME",
                "requirement": "Verify the bounded runtime checklist if required.",
            },
        ],
    }
    task.update(overrides)
    return task


def make_state(
    task_id: str,
    state: str,
    *,
    selected_record_id: str | None = None,
    head: str = HEAD_A,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "state": state,
        "head_commit": head,
        "head_tree": "c" * 40,
        "selected_record_id": selected_record_id,
        "findings": [],
        "dirty_worktree": False,
        "error": None,
    }


class CountingBackend(MemoryIssueBackend):
    def __init__(self, *, author_login: str = AUTHORIZED_LOGIN) -> None:
        super().__init__(author_login=author_login)
        self.create_calls = 0
        self.update_calls = 0
        self.comment_calls = 0

    def create_issue(self, **kwargs: Any) -> dict[str, Any]:
        self.create_calls += 1
        return super().create_issue(**kwargs)

    def update_issue(self, issue_number: int, **kwargs: Any) -> dict[str, Any]:
        self.update_calls += 1
        return super().update_issue(issue_number, **kwargs)

    def add_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        self.comment_calls += 1
        return super().add_comment(issue_number, body)


class AcceptedCreateTimeoutBackend(CountingBackend):
    """Accept one create, hide it briefly, then report a transport timeout."""

    def __init__(self) -> None:
        super().__init__()
        self.hidden_reads_remaining = 0

    def list_issues(self) -> list[dict[str, Any]]:
        if self.hidden_reads_remaining > 0:
            self.hidden_reads_remaining -= 1
            return []
        return super().list_issues()

    def create_issue(self, **kwargs: Any) -> dict[str, Any]:
        issue = super().create_issue(**kwargs)
        self.hidden_reads_remaining = 2
        raise TimeoutError(f"synthetic timeout after accepting Issue #{issue['number']}")


def materialize(
    backend: MemoryIssueBackend,
    rows: list[dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    *,
    head: str = HEAD_A,
) -> ReviewIssueMaterializationResult:
    return materialize_taskgraph_review_issues(
        source_commit=head,
        states={row["task_id"]: row for row in rows},
        tasks=tasks,
        backend=backend,
    )


def issue_for(backend: MemoryIssueBackend, task_id: str) -> dict[str, Any]:
    marker = REVIEW_MARKER_TEMPLATE.format(task_id=task_id)
    matches = [
        issue
        for issue in backend.list_issues()
        if marker in str(issue.get("body") or "")
        and str(issue.get("state") or "").upper() != "CLOSED"
    ]
    require(len(matches) == 1, f"expected one {task_id} review Issue, found {matches}")
    return matches[0]


def reset_write_counts(backend: CountingBackend) -> None:
    backend.create_calls = 0
    backend.update_calls = 0
    backend.comment_calls = 0


def create_marked_issue(
    backend: CountingBackend,
    *,
    task_id: str,
    author_login: str,
    title: str,
    body_suffix: str,
) -> dict[str, Any]:
    previous_login = backend.author_login
    backend.author_login = author_login
    try:
        return backend.create_issue(
            title=title,
            body=(
                f"{REVIEW_MARKER_TEMPLATE.format(task_id=task_id)}\n\n"
                f"{body_suffix}\n"
            ),
            labels=[],
            assignees=[],
        )
    finally:
        backend.author_login = previous_login


def test_review_state_title_mapping_and_non_review_filter() -> None:
    states = {
        "NSC-801": "needs_testing",
        "NSC-802": "needs_replan",
        "NSC-803": "needs_human",
        "NSC-804": "invalid_evidence",
        "NSC-805": "ambiguous_evidence",
        "NSC-806": "conformant",
        "NSC-807": "not_delivered",
        "NSC-808": "aggregate",
        "NSC-809": "superseded",
        "NSC-810": "cancelled",
    }
    rows = [
        make_state(task_id, state, selected_record_id=f"REC-{task_id}")
        for task_id, state in states.items()
    ]
    tasks = {task_id: make_task(task_id) for task_id in states}
    backend = CountingBackend()

    result = materialize(backend, rows, tasks)

    expected_titles = {
        "NSC-801": "Revalidation NSC-801 — Review fixture NSC-801",
        "NSC-802": "Replan NSC-802 — Review fixture NSC-802",
        "NSC-803": "Human Review NSC-803 — Review fixture NSC-803",
        "NSC-804": "Evidence Investigation NSC-804 — Review fixture NSC-804",
        "NSC-805": "Evidence Investigation NSC-805 — Review fixture NSC-805",
    }
    require(result.review_task_count == 5, str(result.to_dict()))
    require(len(backend.issues) == 5, f"wrong Issue count: {backend.issues}")
    for task_id, expected_title in expected_titles.items():
        require(issue_for(backend, task_id)["title"] == expected_title, task_id)
    for task_id in ("NSC-806", "NSC-807", "NSC-808", "NSC-809", "NSC-810"):
        marker = REVIEW_MARKER_TEMPLATE.format(task_id=task_id)
        require(
            all(marker not in issue["body"] for issue in backend.issues.values()),
            f"non-review state created an Issue for {task_id}",
        )
    require(backend.comment_calls == 0, "review materialization posted a comment")
    require(
        all(not issue["assignees"] for issue in backend.issues.values()),
        "review debt assigned/notified a human",
    )


def test_multiple_review_states_create_distinct_per_task_issues() -> None:
    backend = CountingBackend()
    rows = [
        make_state("NSC-811", "needs_testing"),
        make_state("NSC-812", "needs_replan"),
        make_state("NSC-813", "needs_human"),
    ]
    tasks = {row["task_id"]: make_task(row["task_id"]) for row in rows}
    materialize(backend, rows, tasks)
    require(len(backend.issues) == 3, "review states did not create per-task Issues")
    require(
        len({issue["body"].splitlines()[0] for issue in backend.issues.values()}) == 3,
        "review Issues did not carry distinct exact task markers",
    )


def test_exact_repeat_is_write_free_and_comment_free() -> None:
    backend = CountingBackend()
    rows = [make_state("NSC-814", "needs_testing", selected_record_id="REV-814")]
    tasks = {"NSC-814": make_task("NSC-814")}
    first = materialize(backend, rows, tasks)
    writes_after_first = (backend.create_calls, backend.update_calls, backend.comment_calls)
    second = materialize(backend, rows, tasks)
    require(first.created_task_ids == ("NSC-814",), str(first.to_dict()))
    require(second.already_current_task_ids == ("NSC-814",), str(second.to_dict()))
    require(
        (backend.create_calls, backend.update_calls, backend.comment_calls)
        == writes_after_first,
        "exact repeat performed a GitHub write",
    )


def test_stale_managed_block_refresh_preserves_unrelated_prose() -> None:
    backend = CountingBackend()
    task_id = "NSC-815"
    marker = REVIEW_MARKER_TEMPLATE.format(task_id=task_id)
    original_body = (
        f"{marker}\n\n"
        "User-authored opening paragraph.\n\n"
        f"{MANAGED_BLOCK_START}\nold managed text\n{MANAGED_BLOCK_END}\n\n"
        "User-authored closing paragraph.\n"
    )
    created = backend.create_issue(
        title="Old review title",
        body=original_body,
        labels=["user-label"],
        assignees=[],
    )
    backend.create_calls = 0

    result = materialize(
        backend,
        [make_state(task_id, "needs_testing", selected_record_id="REV-815")],
        {task_id: make_task(task_id)},
    )

    refreshed = backend.issues[created["number"]]
    require(result.updated_task_ids == (task_id,), str(result.to_dict()))
    require("User-authored opening paragraph." in refreshed["body"], "opening prose lost")
    require("User-authored closing paragraph." in refreshed["body"], "closing prose lost")
    require("old managed text" not in refreshed["body"], "stale block not replaced")
    require(
        refreshed["labels"] == [{"name": "user-label"}],
        "review refresh changed unrelated labels",
    )
    require(backend.update_calls == 1 and backend.comment_calls == 0, "wrong write shape")


def test_review_state_change_updates_same_issue() -> None:
    backend = CountingBackend()
    task_id = "NSC-816"
    task = make_task(task_id)
    materialize(backend, [make_state(task_id, "needs_testing")], {task_id: task})
    number = issue_for(backend, task_id)["number"]
    result = materialize(
        backend,
        [make_state(task_id, "needs_replan", selected_record_id="DEL-816")],
        {task_id: task},
    )
    changed = issue_for(backend, task_id)
    require(len(backend.issues) == 1 and changed["number"] == number, "second Issue created")
    require(changed["title"].startswith("Replan NSC-816 —"), changed["title"])
    require("`needs_replan`" in changed["body"], "managed state not refreshed")
    require(result.updated_task_ids == (task_id,), str(result.to_dict()))


def test_one_unauthorized_marker_is_ignored_and_authorized_issue_is_created() -> None:
    backend = CountingBackend()
    task_id = "NSC-823"
    unauthorized = create_marked_issue(
        backend,
        task_id=task_id,
        author_login=OUTSIDER_LOGIN,
        title="Forged TaskGraph review work",
        body_suffix="Outside account review prose.",
    )
    backend.author_login = OUTSIDER_LOGIN
    backend.add_comment(unauthorized["number"], "Outside account comment.")
    backend.author_login = AUTHORIZED_LOGIN
    original_issue = json.loads(json.dumps(backend.issues[unauthorized["number"]]))
    original_comments = json.loads(json.dumps(backend.comments[unauthorized["number"]]))
    reset_write_counts(backend)

    result = materialize(
        backend,
        [make_state(task_id, "needs_testing")],
        {task_id: make_task(task_id)},
    )

    require(result.created_task_ids == (task_id,), str(result.to_dict()))
    require(len(backend.issues) == 2, "authorized review Issue was not created")
    authorized = [
        issue
        for issue in backend.issues.values()
        if issue["author"]["login"] == AUTHORIZED_LOGIN
    ]
    require(len(authorized) == 1, f"wrong authorized review Issues: {authorized}")
    require(
        backend.issues[unauthorized["number"]] == original_issue,
        "unauthorized Issue title/body/metadata changed",
    )
    require(
        backend.comments[unauthorized["number"]] == original_comments,
        "unauthorized Issue comments changed",
    )
    require(
        (backend.create_calls, backend.update_calls, backend.comment_calls) == (1, 0, 0),
        "materialization wrote to the unauthorized Issue",
    )


def test_authorized_plus_unauthorized_marker_updates_authorized_issue() -> None:
    backend = CountingBackend()
    task_id = "NSC-824"
    authorized = create_marked_issue(
        backend,
        task_id=task_id,
        author_login=AUTHORIZED_LOGIN,
        title="Stale authorized review title",
        body_suffix="Authorized prose to preserve.",
    )
    unauthorized = create_marked_issue(
        backend,
        task_id=task_id,
        author_login=OUTSIDER_LOGIN,
        title="Forged duplicate review title",
        body_suffix="Unauthorized duplicate prose.",
    )
    unauthorized_before = json.loads(json.dumps(backend.issues[unauthorized["number"]]))
    reset_write_counts(backend)

    result = materialize(
        backend,
        [make_state(task_id, "needs_replan", selected_record_id="DEL-824")],
        {task_id: make_task(task_id)},
    )

    require(result.updated_task_ids == (task_id,), str(result.to_dict()))
    require(result.created_task_ids == (), "authorized marker was not adopted")
    require(
        backend.issues[authorized["number"]]["title"].startswith(f"Replan {task_id} —"),
        "authorized Issue was not refreshed",
    )
    require(
        backend.issues[unauthorized["number"]] == unauthorized_before,
        "unauthorized duplicate Issue was edited",
    )
    require(
        (backend.create_calls, backend.update_calls, backend.comment_calls) == (0, 1, 0),
        "authorized/unauthorized resolution used the wrong write target",
    )


def test_two_unauthorized_same_task_markers_cannot_block_materialization() -> None:
    backend = CountingBackend()
    task_id = "NSC-825"
    unauthorized_numbers = []
    for index, login in enumerate((OUTSIDER_LOGIN, "another-public-account"), start=1):
        unauthorized_numbers.append(
            create_marked_issue(
                backend,
                task_id=task_id,
                author_login=login,
                title=f"Forged duplicate {index}",
                body_suffix=f"Unauthorized duplicate prose {index}.",
            )["number"]
        )
    unauthorized_before = {
        number: json.loads(json.dumps(backend.issues[number]))
        for number in unauthorized_numbers
    }
    reset_write_counts(backend)

    result = materialize(
        backend,
        [make_state(task_id, "needs_human")],
        {task_id: make_task(task_id)},
    )

    require(result.created_task_ids == (task_id,), str(result.to_dict()))
    require(len(backend.issues) == 3, "unauthorized copies blocked authorized creation")
    require(
        all(
            backend.issues[number] == unauthorized_before[number]
            for number in unauthorized_numbers
        ),
        "an unauthorized duplicate Issue was edited",
    )
    require(
        (backend.create_calls, backend.update_calls, backend.comment_calls) == (1, 0, 0),
        "unauthorized copies changed the materialization write shape",
    )


def test_two_authorized_exact_markers_fail_before_any_materialization_write() -> None:
    backend = CountingBackend()
    task_id = "NSC-817"
    marker = REVIEW_MARKER_TEMPLATE.format(task_id=task_id)
    for suffix in ("one", "two"):
        backend.create_issue(
            title=f"User Issue {suffix}",
            body=f"{marker}\n\nUser prose {suffix}.\n",
            labels=[],
            assignees=[],
        )
    reset_write_counts(backend)
    try:
        materialize(
            backend,
            [make_state(task_id, "needs_testing")],
            {task_id: make_task(task_id)},
        )
        raise AssertionError("duplicate exact review markers were accepted")
    except TaskGraphReviewIssueError as exc:
        require("multiple open GitHub Issues" in str(exc), str(exc))
    require(
        (backend.create_calls, backend.update_calls, backend.comment_calls) == (0, 0, 0),
        "duplicate mapping failed after a write",
    )


def test_body_binds_head_evidence_revision_and_every_completion_gate() -> None:
    backend = CountingBackend()
    task_id = "NSC-818"
    task = make_task(task_id, contract_revision=23)
    materialize(
        backend,
        [make_state(task_id, "needs_testing", selected_record_id="REV-NSC-818-deadbeef")],
        {task_id: task},
    )
    body = issue_for(backend, task_id)["body"]
    for required in (
        HEAD_A,
        "`needs_testing`",
        "`REV-NSC-818-deadbeef`",
        "`Tasks/NSC-818.yaml`",
        "`23`",
        "**VAL-UNITY-EDITMODE** — Run the current Edit Mode validation suite.",
        "**VAL-HUMAN-RUNTIME** — Verify the bounded runtime checklist if required.",
        "This Issue is operational work only.",
        "TaskGraph and committed evidence remain authoritative.",
    ):
        require(required in body, f"review body omitted {required!r}:\n{body}")
    require(body.count(MANAGED_BLOCK_START) == 1, "wrong managed start count")
    require(body.count(MANAGED_BLOCK_END) == 1, "wrong managed end count")


def test_selected_evidence_none_is_explicit() -> None:
    backend = CountingBackend()
    task_id = "NSC-819"
    materialize(
        backend,
        [make_state(task_id, "invalid_evidence", selected_record_id=None)],
        {task_id: make_task(task_id)},
    )
    require(
        "**Selected evidence record:** (none)" in issue_for(backend, task_id)["body"],
        "null selected evidence was not rendered as (none)",
    )


def test_review_issue_is_invisible_to_managed_implementation_find() -> None:
    backend = CountingBackend()
    task_id = "NSC-820"
    task = make_task(task_id)
    materialize(
        backend,
        [make_state(task_id, "needs_human", selected_record_id="DEL-820")],
        {task_id: task},
    )
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda selected: task | {"task_contract_sha256": "d" * 64},
        worker_id="review-fixture-worker",
    )
    issue = issue_for(backend, task_id)
    require(not issue["title"].startswith(f"{task_id} —"), issue["title"])
    require(service.find(task_id) is None, "review work masqueraded as implementation workflow")
    require(service.list_agent_ready() == [], "review work entered the managed resume queue")


def test_no_nsc_vincent_notification_or_comment_is_emitted() -> None:
    backend = CountingBackend()
    task_id = "NSC-821"
    materialize(
        backend,
        [make_state(task_id, "needs_human", selected_record_id="DEL-821")],
        {task_id: make_task(task_id)},
    )
    require(backend.comment_calls == 0, "materialization posted a routing comment")
    require(
        all(not comments for comments in backend.comments.values()),
        "materialization populated an Issue comment log",
    )
    require(
        all(issue["title"] != "NSC-Vincent" for issue in backend.issues.values()),
        "materialization created an NSC-Vincent inbox",
    )


def test_accepted_create_timeout_and_stale_reads_never_repeat_create() -> None:
    backend = AcceptedCreateTimeoutBackend()
    task_id = "NSC-822"
    rows = [make_state(task_id, "needs_testing", selected_record_id="REV-822")]
    tasks = {task_id: make_task(task_id)}
    first = materialize(backend, rows, tasks)
    second = materialize(backend, rows, tasks)
    require(first.created_task_ids == (task_id,), str(first.to_dict()))
    require(second.already_current_task_ids == (task_id,), str(second.to_dict()))
    require(backend.create_calls == 1, "accepted uncertain create was issued twice")
    require(len(backend.issues) == 1, "uncertain create produced duplicate Issues")


def test_state_specific_meaning_and_next_actions_are_present() -> None:
    cases = {
        "needs_testing": (
            "no longer proven against current HEAD",
            "prepare/run current-HEAD revalidation",
        ),
        "needs_replan": (
            "must not be \"fixed\" by merely rerunning old tests",
            "determine what requirement/contract changed",
        ),
        "needs_human": (
            "required human approval/decision is missing",
            "Do not notify Vincent merely because the state exists",
        ),
        "invalid_evidence": (
            "structurally or semantically invalid",
            "Never rewrite historical evidence in place",
        ),
        "ambiguous_evidence": (
            "prevents unique conformance",
            "do not choose by timestamp or Issue prose",
        ),
    }
    for offset, (state, fragments) in enumerate(cases.items(), start=1):
        task_id = f"NSC-{830 + offset:03d}"
        backend = CountingBackend()
        materialize(
            backend,
            [make_state(task_id, state, selected_record_id=f"REC-{task_id}")],
            {task_id: make_task(task_id)},
        )
        body = issue_for(backend, task_id)["body"]
        for fragment in fragments:
            require(fragment in body, f"{state} omitted {fragment!r}")


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120.0,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout.strip()


def test_production_observation_uses_one_bulk_snapshot_bound_to_head() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-review-observe-") as tmp:
        root = Path(tmp)
        counter = root / "outside-counter.txt"
        checkout = root / "checkout"
        run("git", "init", "-b", "main", str(checkout), cwd=root)
        run("git", "config", "user.name", "Review Fixture", cwd=checkout)
        run("git", "config", "user.email", "review-fixture@nosafecircle.invalid", cwd=checkout)
        (checkout / "Tasks").mkdir()
        (checkout / "Pipeline" / "TaskGraph").mkdir(parents=True)
        task_id = "NSC-840"
        (checkout / f"Tasks/{task_id}.yaml").write_text(
            json.dumps(make_task(task_id), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        stub = f'''from __future__ import annotations
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COUNTER = Path({str(counter)!r})
count = int(COUNTER.read_text() or "0") if COUNTER.exists() else 0
COUNTER.write_text(str(count + 1))
head = subprocess.check_output(("git", "-C", str(ROOT), "rev-parse", "HEAD"), text=True).strip()
tree = subprocess.check_output(
    ("git", "-C", str(ROOT), "rev-parse", "HEAD^{{tree}}"),
    text=True,
).strip()
print(json.dumps([{{
    "task_id": "{task_id}",
    "title": "Review fixture",
    "state": "needs_testing",
    "head_commit": head,
    "head_tree": tree,
    "selected_record_id": "REV-NSC-840-fixture",
    "findings": [],
    "dirty_worktree": False,
}}]))
'''
        (checkout / "Pipeline/TaskGraph/taskcontrol.py").write_text(
            stub,
            encoding="utf-8",
        )
        run("git", "add", ".", cwd=checkout)
        run("git", "commit", "-m", "review observation fixture", cwd=checkout)
        expected_head = run("git", "rev-parse", "HEAD", cwd=checkout)

        snapshot = observe_taskgraph_review_snapshot(checkout)

        require(counter.read_text() == "1", "observation ran taskcontrol more than once")
        require(snapshot.source_commit == expected_head, str(snapshot.source_commit))
        require(snapshot.states[task_id]["head_commit"] == expected_head, "row HEAD drifted")
        require(
            snapshot.states[task_id]["selected_record_id"] == "REV-NSC-840-fixture",
            "bulk selected evidence was not preserved",
        )
        require(snapshot.tasks[task_id]["contract_revision"] == 7, "wrong contract revision")


def _empty_review_result() -> ReviewIssueMaterializationResult:
    return ReviewIssueMaterializationResult(
        source_commit=HEAD_A,
        inspected_task_count=0,
        review_task_count=0,
        created_task_ids=(),
        updated_task_ids=(),
        already_current_task_ids=(),
    )


def test_generic_mutating_materializes_before_fresh_dispatch() -> None:
    order: list[str] = []
    original_materialize = run_pipeline_agent_module._materialize_generic_review_work
    original_dispatch = (
        run_pipeline_agent_module.resolve_generic_dispatch_with_contention_retry
    )

    def materialize_stub(*, source: Path) -> ReviewIssueMaterializationResult:
        order.append("materialize")
        return _empty_review_result()

    def dispatch_stub(**_kwargs: Any) -> GenericDispatchRetryResult:
        order.append("dispatch")
        return GenericDispatchRetryResult(decision="no_safe_work")

    run_pipeline_agent_module._materialize_generic_review_work = (  # type: ignore[assignment]
        materialize_stub
    )
    run_pipeline_agent_module.resolve_generic_dispatch_with_contention_retry = (  # type: ignore[assignment]
        dispatch_stub
    )
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exit_code = run_pipeline_agent_module.main(
                ["--source", str(ROOT), "--worker-id", "review-order-worker"]
            )
    finally:
        run_pipeline_agent_module._materialize_generic_review_work = (  # type: ignore[assignment]
            original_materialize
        )
        run_pipeline_agent_module.resolve_generic_dispatch_with_contention_retry = (  # type: ignore[assignment]
            original_dispatch
        )
    require(exit_code == 0, f"generic no-safe-work exit was {exit_code}")
    require(order == ["materialize", "dispatch"], f"wrong generic order: {order}")


def test_materialization_failure_prevents_fresh_dispatch_mutation() -> None:
    dispatch_called = False
    original_materialize = run_pipeline_agent_module._materialize_generic_review_work
    original_dispatch = (
        run_pipeline_agent_module.resolve_generic_dispatch_with_contention_retry
    )

    def failing_materialize(*, source: Path) -> ReviewIssueMaterializationResult:
        raise TaskGraphReviewIssueError("synthetic duplicate review marker")

    def dispatch_stub(**_kwargs: Any) -> GenericDispatchRetryResult:
        nonlocal dispatch_called
        dispatch_called = True
        return GenericDispatchRetryResult(decision="no_safe_work")

    run_pipeline_agent_module._materialize_generic_review_work = (  # type: ignore[assignment]
        failing_materialize
    )
    run_pipeline_agent_module.resolve_generic_dispatch_with_contention_retry = (  # type: ignore[assignment]
        dispatch_stub
    )
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exit_code = run_pipeline_agent_module.main(
                ["--source", str(ROOT), "--worker-id", "review-failure-worker"]
            )
    finally:
        run_pipeline_agent_module._materialize_generic_review_work = (  # type: ignore[assignment]
            original_materialize
        )
        run_pipeline_agent_module.resolve_generic_dispatch_with_contention_retry = (  # type: ignore[assignment]
            original_dispatch
        )
    require(exit_code == 2, f"materialization failure exited {exit_code}")
    require(not dispatch_called, "fresh dispatch mutated after materialization failure")


def test_observe_mode_never_invokes_review_materialization() -> None:
    materialize_called = False
    original_materialize = run_pipeline_agent_module._materialize_generic_review_work
    original_plan = run_pipeline_agent_module.build_dispatch_plan

    class FakePlan:
        def to_dict(self) -> dict[str, Any]:
            return {"decision": "no_safe_work", "mode": "read_only_plan"}

    def forbidden_materialize(*, source: Path) -> ReviewIssueMaterializationResult:
        nonlocal materialize_called
        materialize_called = True
        return _empty_review_result()

    run_pipeline_agent_module._materialize_generic_review_work = (  # type: ignore[assignment]
        forbidden_materialize
    )
    run_pipeline_agent_module.build_dispatch_plan = (  # type: ignore[assignment]
        lambda **_kwargs: FakePlan()
    )
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exit_code = run_pipeline_agent_module.main(
                [
                    "--source",
                    str(ROOT),
                    "--worker-id",
                    "review-observe-worker",
                    "--mode",
                    "observe",
                ]
            )
    finally:
        run_pipeline_agent_module._materialize_generic_review_work = (  # type: ignore[assignment]
            original_materialize
        )
        run_pipeline_agent_module.build_dispatch_plan = original_plan  # type: ignore[assignment]
    require(exit_code == 0, f"observe exited {exit_code}")
    require(not materialize_called, "observe mode invoked review materialization")


def test_explicit_task_id_never_invokes_unrelated_review_materialization() -> None:
    materialize_called = False
    original_materialize = run_pipeline_agent_module._materialize_generic_review_work
    original_phase = run_pipeline_agent_module._managed_issue_phase

    def forbidden_materialize(*, source: Path) -> ReviewIssueMaterializationResult:
        nonlocal materialize_called
        materialize_called = True
        return _empty_review_result()

    def stop_after_explicit_routing(**_kwargs: Any) -> str | None:
        raise TaskReviewContractError("synthetic stop after explicit task routing")

    run_pipeline_agent_module._materialize_generic_review_work = (  # type: ignore[assignment]
        forbidden_materialize
    )
    run_pipeline_agent_module._managed_issue_phase = (  # type: ignore[assignment]
        stop_after_explicit_routing
    )
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exit_code = run_pipeline_agent_module.main(
                [
                    "--source",
                    str(ROOT),
                    "--worker-id",
                    "review-explicit-worker",
                    "--task-id",
                    "NSC-840",
                    "--mode",
                    "observe",
                ]
            )
    finally:
        run_pipeline_agent_module._materialize_generic_review_work = (  # type: ignore[assignment]
            original_materialize
        )
        run_pipeline_agent_module._managed_issue_phase = original_phase  # type: ignore[assignment]
    require(exit_code == 2, f"synthetic explicit stop exited {exit_code}")
    require(not materialize_called, "explicit --task-id materialized unrelated review work")


def main() -> int:
    # Keep bounded verification instantaneous in deterministic in-memory tests.
    original_delays = review_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS
    review_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS = (0.0,) * 5
    tests = (
        test_review_state_title_mapping_and_non_review_filter,
        test_multiple_review_states_create_distinct_per_task_issues,
        test_exact_repeat_is_write_free_and_comment_free,
        test_stale_managed_block_refresh_preserves_unrelated_prose,
        test_review_state_change_updates_same_issue,
        test_one_unauthorized_marker_is_ignored_and_authorized_issue_is_created,
        test_authorized_plus_unauthorized_marker_updates_authorized_issue,
        test_two_unauthorized_same_task_markers_cannot_block_materialization,
        test_two_authorized_exact_markers_fail_before_any_materialization_write,
        test_body_binds_head_evidence_revision_and_every_completion_gate,
        test_selected_evidence_none_is_explicit,
        test_review_issue_is_invisible_to_managed_implementation_find,
        test_no_nsc_vincent_notification_or_comment_is_emitted,
        test_accepted_create_timeout_and_stale_reads_never_repeat_create,
        test_state_specific_meaning_and_next_actions_are_present,
        test_production_observation_uses_one_bulk_snapshot_bound_to_head,
        test_generic_mutating_materializes_before_fresh_dispatch,
        test_materialization_failure_prevents_fresh_dispatch_mutation,
        test_observe_mode_never_invokes_review_materialization,
        test_explicit_task_id_never_invokes_unrelated_review_materialization,
    )
    try:
        for test in tests:
            test()
            print(f"PASS: {test.__name__}")
    finally:
        review_module.POST_MUTATION_VERIFICATION_DELAYS_SECONDS = original_delays
    print(f"PASS: {len(tests)} TaskGraph review Issue materialization regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
