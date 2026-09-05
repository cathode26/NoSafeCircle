#!/usr/bin/env python3
"""Focused local tests for production delivered-task revert safeguards."""

from __future__ import annotations

import os
import json
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.reset_rehearsal_task import (  # noqa: E402
    CommandRunner,
    RehearsalResetError,
    _remove_tree_exact,
)
from Pipeline.TaskReviewAgent.reset_task import (  # noqa: E402
    TaskResetError,
    _abandoned_rehearsal_state_is_undelivered,
    _fetch_exact_remote_commit_object,
    _is_unpushed_decomposition_baseline,
    _require_task_paths_unchanged_since_merge,
    _transitive_active_dependents,
    _tree_entry,
    _validate_branchless_checkout_manifest,
    _validate_branchless_checkout_source,
)
from Pipeline.TaskReviewAgent.contracts import semantic_sha256  # noqa: E402
from Pipeline.TaskReviewAgent.claim_policy import activated_claim_namespace  # noqa: E402
from Pipeline.TaskReviewAgent.claim_refs import task_claim_ref  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import WorkflowPhase  # noqa: E402


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"command failed: {args}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_dependency_walk() -> None:
    contracts = {
        "NSC-100": {
            "contract_disposition": "active",
            "depends_on": [],
        },
        "NSC-101": {
            "contract_disposition": "active",
            "depends_on": ["NSC-100"],
        },
        "NSC-102": {
            "contract_disposition": "active",
            "depends_on": ["NSC-101"],
        },
        "NSC-103": {
            "contract_disposition": "cancelled",
            "depends_on": ["NSC-100"],
        },
    }
    expect(
        _transitive_active_dependents(contracts, "NSC-100")
        == ("NSC-101", "NSC-102"),
        "direct/transitive active dependents were not discovered exactly",
    )


def test_undecomposed_aggregate_is_safe_abandoned_rehearsal_state() -> None:
    task = {
        "execution_scope": "needs_execution_decomposition",
        "decomposition_state": "concrete",
    }
    expect(
        _abandoned_rehearsal_state_is_undelivered(task, "aggregate"),
        "undecomposed aggregate was not recognized as undelivered",
    )
    task["decomposition_state"] = "decomposed"
    task["decomposition_children"] = ["NSC-991", "NSC-992"]
    expect(
        not _abandoned_rehearsal_state_is_undelivered(task, "aggregate"),
        "applied decomposition was accepted as an abandoned undecomposed parent",
    )


def test_unpushed_decomposition_baseline_is_safe() -> None:
    head = "1" * 40
    state = SimpleNamespace(
        phase=WorkflowPhase.DECOMPOSITION,
        human_handoff_commit=head,
    )
    task = {
        "execution_scope": "needs_execution_decomposition",
        "decomposition_state": "concrete",
    }
    expect(
        _is_unpushed_decomposition_baseline(
            state,
            task,
            task_head=head,
            remote_branch_oid=None,
        ),
        "plan-only decomposition baseline was not recognized",
    )
    expect(
        not _is_unpushed_decomposition_baseline(
            state,
            task,
            task_head=head,
            remote_branch_oid=head,
        ),
        "pushed decomposition branch was mistaken for a plan-only baseline",
    )


def test_path_guard(repository: Path) -> None:
    repository.mkdir()
    run("git", "init", "-b", "main", cwd=repository)
    run("git", "config", "user.name", "Smoke Test", cwd=repository)
    run("git", "config", "user.email", "smoke@example.invalid", cwd=repository)
    (repository / "task.txt").write_text("base\n", encoding="utf-8")
    (repository / "later.txt").write_text("base\n", encoding="utf-8")
    run("git", "add", "task.txt", "later.txt", cwd=repository)
    run("git", "commit", "-m", "base", cwd=repository)
    run("git", "switch", "-c", "task", cwd=repository)
    (repository / "task.txt").write_text("delivered\n", encoding="utf-8")
    run("git", "commit", "-am", "delivery", cwd=repository)
    run("git", "switch", "main", cwd=repository)
    run("git", "merge", "--no-ff", "task", "-m", "merge delivery", cwd=repository)
    merge = run("git", "rev-parse", "HEAD", cwd=repository)
    (repository / "later.txt").write_text("later production work\n", encoding="utf-8")
    run("git", "commit", "-am", "later unrelated work", cwd=repository)
    head = run("git", "rev-parse", "HEAD", cwd=repository)
    runner = CommandRunner()
    _require_task_paths_unchanged_since_merge(
        runner,
        repository,
        merge_commit=merge,
        current_main=head,
        paths=("task.txt",),
    )
    expect(
        _tree_entry(runner, repository, merge, "later.txt")
        != _tree_entry(runner, repository, head, "later.txt"),
        "fixture did not create unrelated later production work",
    )
    (repository / "task.txt").write_text("temporary task edit\n", encoding="utf-8")
    run("git", "commit", "-am", "temporary task edit", cwd=repository)
    (repository / "task.txt").write_text("delivered\n", encoding="utf-8")
    run("git", "commit", "-am", "restore task bytes", cwd=repository)
    restored_head = run("git", "rev-parse", "HEAD", cwd=repository)
    try:
        _require_task_paths_unchanged_since_merge(
            runner,
            repository,
            merge_commit=merge,
            current_main=restored_head,
            paths=("task.txt",),
        )
    except TaskResetError as exc:
        expect("task.txt" in str(exc), "transient-touch refusal omitted the path")
    else:
        raise AssertionError("a transient task-path edit was hidden by restored bytes")
    (repository / "task.txt").write_text("later task edit\n", encoding="utf-8")
    run("git", "commit", "-am", "later task edit", cwd=repository)
    changed_head = run("git", "rev-parse", "HEAD", cwd=repository)
    try:
        _require_task_paths_unchanged_since_merge(
            runner,
            repository,
            merge_commit=merge,
            current_main=changed_head,
            paths=("task.txt",),
        )
    except TaskResetError as exc:
        expect("task.txt" in str(exc), "refusal did not identify the changed path")
    else:
        raise AssertionError("later task-owned changes were not refused")


def test_readonly_tree_removal(root: Path) -> None:
    target = root / "readonly-tree"
    target.mkdir()
    readonly = target / "object"
    readonly.write_bytes(b"git object fixture\n")
    readonly.chmod(stat.S_IREAD)
    _remove_tree_exact(target)
    expect(not target.exists(), "read-only checkout tree was not removed")


def test_branchless_checkout_manifest_guard(root: Path) -> None:
    checkout = root / "NSC-901"
    checkout.mkdir()
    task = {
        "id": "NSC-901",
        "contract_revision": 1,
        "task_contract_sha256": "a" * 64,
    }
    payload = {
        "schema_version": "2.0",
        "task_id": "NSC-901",
        "checkout_path": str(checkout),
        "branch": "nsc-901-smoke",
        "remote_url": "https://github.com/example/rehearsal.git",
        "initial_source_head": "1" * 40,
        "initial_source_tree": "2" * 40,
        "task_contract_path": "Tasks/NSC-901.yaml",
        "task_contract_revision": 1,
        "task_contract_sha256": "a" * 64,
        "authority": "durable_checkout_identity",
    }
    manifest = {"manifest_sha256": semantic_sha256(payload), **payload}
    path = root / "NSC-901.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    _validate_branchless_checkout_manifest(
        path,
        task=task,
        checkout=checkout,
        branch="nsc-901-smoke",
        source_head="1" * 40,
        source_tree="2" * 40,
        origin="https://github.com/example/rehearsal.git",
    )
    observed = _validate_branchless_checkout_manifest(
        path,
        task=task,
        checkout=checkout,
        branch="nsc-901-smoke",
        source_head=None,
        source_tree=None,
        origin="https://github.com/example/rehearsal.git",
    )
    expect(
        observed["initial_source_head"] == "1" * 40,
        "hash-bound manifest source identity was not returned",
    )
    manifest["initial_source_head"] = "3" * 40
    path.write_text(json.dumps(manifest), encoding="utf-8")
    try:
        _validate_branchless_checkout_manifest(
            path,
            task=task,
            checkout=checkout,
            branch="nsc-901-smoke",
            source_head="1" * 40,
            source_tree="2" * 40,
            origin="https://github.com/example/rehearsal.git",
        )
    except TaskResetError as exc:
        expect("manifest hash" in str(exc), "tampered manifest failure was unclear")
    else:
        raise AssertionError("tampered branchless checkout manifest was accepted")


def test_branchless_checkout_source_may_advance_on_main(root: Path) -> None:
    repository = root / "source-advance"
    repository.mkdir()
    run("git", "init", "-b", "main", cwd=repository)
    run("git", "config", "user.name", "Smoke Test", cwd=repository)
    run("git", "config", "user.email", "smoke@example.invalid", cwd=repository)
    (repository / "value.txt").write_text("lease\n", encoding="utf-8")
    run("git", "add", "value.txt", cwd=repository)
    run("git", "commit", "-m", "lease", cwd=repository)
    acquired = run("git", "rev-parse", "HEAD", cwd=repository)
    (repository / "value.txt").write_text("checkout\n", encoding="utf-8")
    run("git", "commit", "-am", "checkout", cwd=repository)
    checkout = run("git", "rev-parse", "HEAD", cwd=repository)
    checkout_tree = run("git", "rev-parse", "HEAD^{tree}", cwd=repository)
    (repository / "value.txt").write_text("current\n", encoding="utf-8")
    run("git", "commit", "-am", "current", cwd=repository)
    current = run("git", "rev-parse", "HEAD", cwd=repository)
    expect(
        _validate_branchless_checkout_source(
            CommandRunner(),
            repository,
            manifest={
                "initial_source_head": checkout,
                "initial_source_tree": checkout_tree,
            },
            current_main=current,
        )
        == checkout,
        "mainline checkout refresh after lease acquisition was rejected",
    )
    run("git", "switch", "-c", "divergent", acquired, cwd=repository)
    (repository / "divergent.txt").write_text("divergent\n", encoding="utf-8")
    run("git", "add", "divergent.txt", cwd=repository)
    run("git", "commit", "-m", "divergent", cwd=repository)
    divergent = run("git", "rev-parse", "HEAD", cwd=repository)
    divergent_tree = run("git", "rev-parse", "HEAD^{tree}", cwd=repository)
    try:
        _validate_branchless_checkout_source(
            CommandRunner(),
            repository,
            manifest={
                "initial_source_head": divergent,
                "initial_source_tree": divergent_tree,
            },
            current_main=current,
        )
    except TaskResetError as exc:
        expect("ancestry" in str(exc), "divergent source failure was unclear")
    else:
        raise AssertionError("divergent checkout source was accepted")


def test_exact_remote_branch_object_is_fetched_without_local_ref(root: Path) -> None:
    remote = root / "remote.git"
    producer = root / "producer"
    consumer = root / "consumer"
    run("git", "init", "--bare", str(remote), cwd=root)
    run("git", "clone", str(remote), str(producer), cwd=root)
    run("git", "config", "user.name", "Smoke Test", cwd=producer)
    run("git", "config", "user.email", "smoke@example.invalid", cwd=producer)
    run("git", "switch", "-c", "main", cwd=producer)
    (producer / "base.txt").write_text("base\n", encoding="utf-8")
    run("git", "add", "base.txt", cwd=producer)
    run("git", "commit", "-m", "base", cwd=producer)
    run("git", "push", "-u", "origin", "main", cwd=producer)
    run("git", "symbolic-ref", "HEAD", "refs/heads/main", cwd=remote)
    run("git", "clone", "--branch", "main", str(remote), str(consumer), cwd=root)

    run("git", "switch", "-c", "task-branch", cwd=producer)
    (producer / "task.txt").write_text("task\n", encoding="utf-8")
    run("git", "add", "task.txt", cwd=producer)
    run("git", "commit", "-m", "task", cwd=producer)
    task_head = run("git", "rev-parse", "HEAD", cwd=producer)
    run("git", "push", "origin", "HEAD:refs/heads/task-branch", cwd=producer)
    missing = subprocess.run(
        ("git", "cat-file", "-e", f"{task_head}^{{commit}}"),
        cwd=str(consumer),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    expect(missing.returncode != 0, "consumer unexpectedly had remote task object")

    _fetch_exact_remote_commit_object(
        CommandRunner(),
        consumer,
        remote="origin",
        ref="refs/heads/task-branch",
        expected_oid=task_head,
    )
    expect(
        run("git", "cat-file", "-t", task_head, cwd=consumer) == "commit",
        "exact remote task object was not fetched",
    )
    local_ref = subprocess.run(
        ("git", "show-ref", "--verify", "--quiet", "refs/heads/task-branch"),
        cwd=str(consumer),
        check=False,
    )
    expect(local_ref.returncode != 0, "preflight fetch created a local task branch")


# ---------------------------------------------------------------------------
# Decomposition undo (--undo-decomposition)
#
# Every test below uses a disposable local Git repository plus a local bare
# "origin". No real GitHub object, remote ref, or network call is used: `gh`
# and `git remote get-url origin` are answered by FakeGitHubRunner.
# ---------------------------------------------------------------------------

TASK_GRAPH_DIR = ROOT / "Pipeline" / "TaskGraph"
for _module_root in (str(ROOT / "Pipeline"), str(TASK_GRAPH_DIR)):
    if _module_root not in sys.path:
        sys.path.insert(0, _module_root)

from apply_graph_delta import apply_graph_delta  # noqa: E402
from undo_graph_delta import undo_graph_delta  # noqa: E402
from graph_apply_smoke_test import (  # noqa: E402
    approved_identity_environment,
    create_fixture,
)
from Pipeline.TaskReviewAgent.real_checkout import branch_name  # noqa: E402
from Pipeline.TaskReviewAgent.reset_rehearsal_task import CommandResult  # noqa: E402
from Pipeline.TaskReviewAgent.reset_task import (  # noqa: E402
    DecompositionUndoReset,
    PublishedDecompositionUndoRecovery,
    _decomposition_children,
    main as reset_task_main,
)
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)

FIXTURE_REPOSITORY = "cathode26/NoSafeCircle-Rehearsal-UndoFixture"
FIXTURE_ORIGIN_URL = "https://github.com/" + FIXTURE_REPOSITORY + ".git"


class FakeGitHubRunner(CommandRunner):
    """Real git against a local bare origin; every `gh` call is faked."""

    def __init__(self, *, open_issues=None, fail_push: bool = False, task_states=None) -> None:
        self.open_issues = dict(open_issues or {})
        self.fail_push = fail_push
        # The disposable fixture holds a real persisted TaskGraph but no
        # taskcontrol.py CLI, so those two exact invocations are answered here.
        self.task_states = dict(task_states or {})
        self.gh_calls = []
        self.push_calls = []

    def run(self, args, *, cwd, check: bool = True, timeout: float = 600.0):
        argv = tuple(args)
        if argv and argv[0] == "gh":
            self.gh_calls.append(argv)
            return CommandResult(
                args=argv, returncode=0, stdout=self._gh_payload(argv), stderr=""
            )
        # The fixture origin is a local bare repository, but production code
        # legitimately requires a GitHub-shaped identity. Answer only that
        # identity question; every other git call runs for real.
        if argv[0] == "git" and argv[-3:] == ("remote", "get-url", "origin"):
            return CommandResult(
                args=argv, returncode=0, stdout=FIXTURE_ORIGIN_URL + "\n", stderr=""
            )
        if len(argv) >= 2 and argv[1].endswith("taskcontrol.py"):
            return self._taskcontrol(argv)
        if argv[0] == "git" and "push" in argv:
            self.push_calls.append(argv)
            if self.fail_push:
                if check:
                    raise TaskResetError("command failed (1): fixture push failure")
                return CommandResult(
                    args=argv, returncode=1, stdout="", stderr="fixture push failure\n"
                )
        return super().run(argv, cwd=cwd, check=check, timeout=timeout)

    def _taskcontrol(self, argv):
        if argv[2] == "validate":
            return CommandResult(
                args=argv,
                returncode=0,
                stdout="taskcontrol validate: PASS" + chr(10),
                stderr="",
            )
        if argv[2] == "state":
            task_id = argv[3]
            return CommandResult(
                args=argv,
                returncode=0,
                stdout=json.dumps(
                    {
                        "task_id": task_id,
                        "state": self.task_states.get(task_id, "not_delivered"),
                    }
                ),
                stderr="",
            )
        raise AssertionError("unexpected taskcontrol invocation: " + " ".join(argv))

    def _gh_payload(self, argv) -> str:
        if "issue" in argv and "list" in argv:
            state = argv[argv.index("--state") + 1]
            search = argv[argv.index("--search") + 1]
            task_id = search.split(" ", 1)[0]
            if state == "open":
                return json.dumps(self.open_issues.get(task_id, []))
        return json.dumps([])


class RecoveryGitHubRunner(FakeGitHubRunner):
    def __init__(
        self,
        backend: MemoryIssueBackend,
        *,
        visibility: str = "PRIVATE",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.backend = backend
        self.visibility = visibility

    def run(self, args, *, cwd, check: bool = True, timeout: float = 600.0):
        argv = tuple(args)
        if argv[:3] == ("gh", "repo", "view"):
            return CommandResult(
                argv,
                0,
                json.dumps(
                    {
                        "nameWithOwner": FIXTURE_REPOSITORY,
                        "visibility": self.visibility,
                        "isArchived": False,
                        "url": "https://example.invalid/rehearsal",
                    }
                ),
                "",
            )
        if argv[:3] == ("gh", "issue", "list"):
            state = argv[argv.index("--state") + 1].upper()
            task_id = argv[argv.index("--search") + 1].split(" ", 1)[0]
            issues = [
                issue
                for issue in self.backend.list_issues()
                if (state == "ALL" or issue.get("state") == state)
                and (
                    str(issue.get("title") or "") == task_id
                    or str(issue.get("title") or "").startswith(task_id + " —")
                    or f"<!-- no-safe-circle-task: {task_id} -->"
                    in str(issue.get("body") or "")
                )
            ]
            return CommandResult(argv, 0, json.dumps(issues), "")
        if argv[:3] == ("gh", "issue", "view"):
            number = int(argv[3])
            issue = self.backend.get_issue(number)
            if issue is None:
                return CommandResult(argv, 1, "", "missing issue")
            issue["comments"] = self.backend.get_comments(number)
            return CommandResult(argv, 0, json.dumps(issue), "")
        if argv[:3] == ("gh", "issue", "comment"):
            number = int(argv[3])
            self.backend.add_comment(number, argv[argv.index("--body") + 1])
            return CommandResult(argv, 0, "", "")
        if argv[:3] == ("gh", "issue", "close"):
            self.backend.issues[int(argv[3])]["state"] = "CLOSED"
            return CommandResult(argv, 0, "", "")
        if argv[:3] == ("gh", "pr", "list"):
            return CommandResult(argv, 0, "[]", "")
        if argv[:3] == ("docker", "ps", "-q"):
            return CommandResult(argv, 0, "", "")
        if argv and argv[0].casefold().endswith("powershell.exe"):
            return CommandResult(argv, 0, "", "")
        return super().run(argv, cwd=cwd, check=check, timeout=timeout)


class UndoEnvironment:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.work = root / "work"
        self.bare = root / "origin.git"
        self.checkout_root = root / "checkouts"
        self.checkout_root.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)

        self.fixture = create_fixture(self.work)
        run("git", "branch", "-M", "main", cwd=self.work)
        with approved_identity_environment():
            self.applied = apply_graph_delta(
                self.work,
                self.fixture.selector,
                self.fixture.decomposition_result,
                self.fixture.stored_plan,
                expected_head=self.fixture.initial_head,
            )
        run("git", "init", "--bare", "-q", str(self.bare), cwd=root)
        run("git", "remote", "add", "origin", str(self.bare), cwd=self.work)
        run("git", "push", "-q", "origin", "HEAD:refs/heads/main", cwd=self.work)
        run("git", "fetch", "-q", "--prune", "origin", "main", cwd=self.work)

        payload = self.fixture.stored_plan.to_dict()
        self.parent_id = payload["parent_before_summary"]["task_id"]
        self.plan_id = payload["plan_id"]
        self.graph_delta = root / "graph_delta.json"
        self.graph_delta.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def operation(self, runner=None) -> DecompositionUndoReset:
        return DecompositionUndoReset(
            source=self.work,
            checkout_root=self.checkout_root,
            task_id=self.parent_id,
            graph_delta=self.graph_delta,
            runner=runner or FakeGitHubRunner(),
        )

    def head(self) -> str:
        return run("git", "rev-parse", "HEAD", cwd=self.work)

    def origin_main(self) -> str:
        line = run("git", "ls-remote", "origin", "refs/heads/main", cwd=self.work)
        return line.split()[0]

    def commit_count(self) -> int:
        return int(run("git", "rev-list", "--count", "HEAD", cwd=self.work))


class PublishedUndoEnvironment(UndoEnvironment):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        with approved_identity_environment():
            undone = undo_graph_delta(
                self.work,
                self.fixture.stored_plan,
                expected_head=self.applied.new_commit_sha,
            )
        self.undo_commit = undone.undo_commit
        run("git", "push", "-q", "origin", "HEAD:refs/heads/main", cwd=self.work)
        (self.work / "LaterUnrelated.txt").write_text(
            "preserved later work\n", encoding="utf-8", newline="\n"
        )
        run("git", "add", "--", "LaterUnrelated.txt", cwd=self.work)
        run(
            "git",
            "commit",
            "-q",
            "--no-gpg-sign",
            "-m",
            "fixture: later unrelated work",
            cwd=self.work,
        )
        run("git", "push", "-q", "origin", "HEAD:refs/heads/main", cwd=self.work)
        run("git", "fetch", "-q", "origin", "main", cwd=self.work)
        self.later_head = self.head()
        self.task = load_committed_task(self.work, self.parent_id)
        self.branch = branch_name(self.parent_id, self.task.get("title"))
        self.checkout = self.checkout_root / self.parent_id
        run(
            "git",
            "clone",
            "-q",
            "--no-checkout",
            str(self.bare),
            str(self.checkout),
            cwd=root,
        )
        run(
            "git",
            "checkout",
            "-q",
            "-b",
            self.branch,
            self.fixture.initial_head,
            cwd=self.checkout,
        )
        source_tree = run(
            "git", "rev-parse", self.fixture.initial_head + "^{tree}", cwd=self.work
        )
        state_root = self.checkout_root / ".task-review-agent"
        state_root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": "2.0",
            "task_id": self.parent_id,
            "checkout_path": str(self.checkout),
            "branch": self.branch,
            "task_contract_path": f"Tasks/{self.parent_id}.yaml",
            "task_contract_revision": self.task["contract_revision"],
            "task_contract_sha256": self.task["task_contract_sha256"],
            "authority": "durable_checkout_identity",
            "checkout_purpose": "decomposition",
            "initial_source_head": self.fixture.initial_head,
            "initial_source_tree": source_tree,
            "remote_url": FIXTURE_ORIGIN_URL,
        }
        manifest["manifest_sha256"] = semantic_sha256(manifest)
        (state_root / f"{self.parent_id}.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        self.backend = MemoryIssueBackend()
        service = IssueWorkflowService(
            backend=self.backend,
            task_loader=lambda _task_id: self.task,
            worker_id="fixture-worker",
        )
        service.acquire_agent_lease(
            task=self.task,
            source_head=self.fixture.initial_head,
            branch=self.branch,
            checkout_path=str(self.checkout),
            planned_approach="Review and apply the exact decomposition.",
            expected_validation="Validate the applied TaskGraph.",
            now="2026-09-04T01:00:00Z",
        )
        service.publish_decomposition_handoff(
            task_id=self.parent_id,
            source_head=self.fixture.initial_head,
            checkout_path=str(self.checkout),
            decomposition_run_id="fixture-decomposition-run",
            artifact_root=str(root / "artifacts"),
            graph_delta_plan_id=self.plan_id,
            summary="Two exact children.",
            branch=self.branch,
            now="2026-09-04T01:01:00Z",
        )
        service.apply_decomposition_result(
            task_id=self.parent_id,
            result_body=(
                "## Decomposition application result\n\n"
                f"Result: APPROVE\nReviewed plan_id: {self.plan_id}\n"
            ),
            actor_id="cathode26",
            now="2026-09-04T01:02:00Z",
        )
        service.acquire_agent_lease(
            task=self.task,
            source_head=self.fixture.initial_head,
            branch=self.branch,
            checkout_path=str(self.checkout),
            planned_approach="Apply the approved graph delta.",
            expected_validation="Validate the exact graph commit.",
            now="2026-09-04T01:03:00Z",
        )
        service.complete_decomposition(
            task_id=self.parent_id,
            graph_delta_plan_id=self.plan_id,
            applied_commit=self.applied.new_commit_sha,
            now="2026-09-04T01:04:00Z",
        )

    def recovery(self, runner=None) -> PublishedDecompositionUndoRecovery:
        return PublishedDecompositionUndoRecovery(
            source=self.work,
            checkout_root=self.checkout_root,
            task_id=self.parent_id,
            graph_delta=self.graph_delta,
            runner=runner or RecoveryGitHubRunner(self.backend),
        )


def _expect_refusal(callable_, fragment: str, message: str) -> str:
    try:
        callable_()
    except TaskResetError as exc:
        expect(fragment in str(exc), message + ": unexpected error " + str(exc))
        return str(exc)
    raise AssertionError(message + ": no refusal was raised")


def _create_stopped_undo(
    environment: UndoEnvironment,
) -> tuple[Path, str, dict[str, object]]:
    state_root = environment.checkout_root / ".task-review-agent"
    state_root.mkdir(parents=True, exist_ok=True)
    parent_state = state_root / (environment.parent_id + ".json")
    parent_state.write_text("{}\n", encoding="utf-8", newline="\n")
    operation = environment.operation(FakeGitHubRunner(fail_push=True))
    plan = operation.preflight()
    with approved_identity_environment():
        try:
            operation.apply(plan)
        except TaskResetError:
            pass
        else:
            raise AssertionError("failed push did not stop the apply")
    reports = sorted(
        (state_root / "reset-runs" / environment.parent_id).glob(
            "*-undo-decomposition.json"
        )
    )
    expect(len(reports) == 1, "expected exactly one stopped undo receipt")
    return reports[0], environment.head(), plan


def test_undo_decomposition_dry_run_is_read_only(root: Path) -> None:
    environment = UndoEnvironment(root)
    before_head = environment.head()
    before_count = environment.commit_count()
    plan = environment.operation().preflight()
    expect(plan["operation"] == "decomposition_undo_reset", "wrong operation name")
    expect(plan["task_id"] == environment.parent_id, "wrong parent task")
    expect(plan["plan_id"] == environment.plan_id, "wrong plan id")
    expect(plan["apply_commit"] == environment.applied.new_commit_sha, "wrong D1C commit")
    expect(plan["origin_main"] == before_head, "origin/main identity was not proven")
    expect(
        tuple(plan["decomposition_children"]) == ("NSC-043", "NSC-044"),
        "children were not discovered exactly",
    )
    expect(plan["audit_history_rewritten"] is False, "undo claimed to rewrite audit history")
    expect(environment.head() == before_head, "dry run moved HEAD")
    expect(environment.commit_count() == before_count, "dry run created a commit")
    expect(
        run("git", "status", "--porcelain=v1", cwd=environment.work) == "",
        "dry run dirtied the checkout",
    )


def test_undo_decomposition_restores_exact_source_tree(root: Path) -> None:
    environment = UndoEnvironment(root)
    runner = FakeGitHubRunner()
    operation = environment.operation(runner)
    plan = operation.preflight()
    source_tree = run(
        "git",
        "rev-parse",
        environment.fixture.initial_head + "^{tree}",
        cwd=environment.work,
    )
    with approved_identity_environment():
        report = operation.apply(plan)
    expect(report["status"] == "complete", "undo did not complete")
    expect(report["undo_commit"] != plan["apply_commit"], "undo reused the apply commit")
    expect(
        run("git", "rev-parse", "HEAD^{tree}", cwd=environment.work) == source_tree,
        "undo did not restore the exact pre-D1C tree",
    )
    expect(
        run("git", "rev-parse", "HEAD^", cwd=environment.work) == plan["apply_commit"],
        "undo commit is not additive on the exact D1C commit",
    )
    expect(environment.origin_main() == report["undo_commit"], "origin/main was not updated")
    expect(environment.commit_count() == 3, "undo was not exactly one additive commit")
    for child in plan["decomposition_children"]:
        expect(
            not (environment.work / "Tasks" / (child + ".yaml")).exists(),
            "child contract " + child + " survived the undo",
        )
    parent = json.loads(
        (environment.work / "Tasks" / (environment.parent_id + ".yaml")).read_text(
            encoding="utf-8"
        )
    )
    expect(
        parent.get("decomposition_state") != "decomposed",
        "parent is still marked decomposed",
    )
    expect(
        not parent.get("decomposition_children"),
        "parent still records decomposition children",
    )
    expect(report["parent_eligible_for_fresh_decomposition"] is True, "parent not freed")
    expect(
        all("--force" not in " ".join(call) for call in runner.push_calls),
        "undo used a force push",
    )
    expect(
        run("git", "cat-file", "-t", plan["apply_commit"], cwd=environment.work) == "commit",
        "the original D1C commit was removed from history",
    )


def test_undo_decomposition_refuses_later_main(root: Path) -> None:
    environment = UndoEnvironment(root)
    (environment.work / "FixtureUnrelated.txt").write_text(
        "later dependent work\n", encoding="utf-8", newline="\n"
    )
    run("git", "add", "--", "FixtureUnrelated.txt", cwd=environment.work)
    run(
        "git", "commit", "-q", "--no-gpg-sign", "-m", "fixture: later work",
        cwd=environment.work,
    )
    run("git", "push", "-q", "origin", "HEAD:refs/heads/main", cwd=environment.work)
    run("git", "fetch", "-q", "--prune", "origin", "main", cwd=environment.work)
    before = environment.commit_count()
    _expect_refusal(
        environment.operation().preflight,
        "HEAD is not the exact D1C decomposition commit",
        "later main was not refused",
    )
    expect(environment.commit_count() == before, "refusal created a commit")


def test_undo_decomposition_refuses_changed_graph(root: Path) -> None:
    environment = UndoEnvironment(root)
    contract = json.loads(
        (environment.work / "Tasks" / "NSC-043.yaml").read_text(encoding="utf-8")
    )
    contract["id"] = "NSC-050"
    (environment.work / "Tasks" / "NSC-050.yaml").write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    run("git", "add", "--", "Tasks/NSC-050.yaml", cwd=environment.work)
    run(
        "git", "commit", "-q", "--no-gpg-sign", "-m", "fixture: graph moved",
        cwd=environment.work,
    )
    run("git", "push", "-q", "origin", "HEAD:refs/heads/main", cwd=environment.work)
    run("git", "fetch", "-q", "--prune", "origin", "main", cwd=environment.work)
    _expect_refusal(
        environment.operation().preflight,
        "exact D1C undo authority was refused",
        "changed graph was not refused",
    )


def test_undo_decomposition_refuses_consumed_child_issue(root: Path) -> None:
    environment = UndoEnvironment(root)
    runner = FakeGitHubRunner(
        open_issues={
            "NSC-044": [
                {
                    "number": 77,
                    "title": "NSC-044",
                    "state": "OPEN",
                    "url": "https://example.invalid/issues/77",
                    "body": "<!-- no-safe-circle-task: NSC-044 -->",
                    "labels": [],
                }
            ]
        }
    )
    message = _expect_refusal(
        environment.operation(runner).preflight,
        "already consumed or reserved",
        "open child Issue was not refused",
    )
    expect("NSC-044" in message and "77" in message, "refusal did not name the Issue")


def test_undo_decomposition_refuses_child_branch(root: Path) -> None:
    environment = UndoEnvironment(root)
    child = json.loads(
        (environment.work / "Tasks" / "NSC-043.yaml").read_text(encoding="utf-8")
    )
    branch = branch_name("NSC-043", child.get("title"))
    run("git", "branch", branch, cwd=environment.work)
    message = _expect_refusal(
        environment.operation().preflight,
        "already consumed or reserved",
        "local child branch was not refused",
    )
    expect(branch in message, "refusal did not name the branch")


def test_undo_decomposition_refuses_child_checkout(root: Path) -> None:
    environment = UndoEnvironment(root)
    (environment.checkout_root / "NSC-043").mkdir(parents=True)
    message = _expect_refusal(
        environment.operation().preflight,
        "already consumed or reserved",
        "child checkout was not refused",
    )
    expect("NSC-043" in message, "refusal did not name the checkout")


def test_undo_decomposition_refuses_child_linked_worktree(root: Path) -> None:
    environment = UndoEnvironment(root)
    linked = root / "linked" / "NSC-043"
    linked.parent.mkdir(parents=True)
    run(
        "git",
        "worktree",
        "add",
        "--detach",
        str(linked),
        "HEAD",
        cwd=environment.work,
    )
    message = _expect_refusal(
        environment.operation().preflight,
        "already consumed or reserved",
        "child linked worktree was not refused",
    )
    expect("linked worktree" in message, "refusal did not name the linked worktree")


def test_undo_decomposition_refuses_child_claim_ref(root: Path) -> None:
    environment = UndoEnvironment(root)
    claim_ref = task_claim_ref(activated_claim_namespace(), "NSC-043")
    run("git", "push", "-q", "origin", "HEAD:" + claim_ref, cwd=environment.work)
    message = _expect_refusal(
        environment.operation().preflight,
        "already consumed or reserved",
        "child claim ref was not refused",
    )
    expect(claim_ref in message, "refusal did not name the claim ref")


def test_undo_decomposition_refuses_child_state_file(root: Path) -> None:
    environment = UndoEnvironment(root)
    state_root = environment.checkout_root / ".task-review-agent"
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "NSC-044.json").write_text("{}\n", encoding="utf-8", newline="\n")
    message = _expect_refusal(
        environment.operation().preflight,
        "already consumed or reserved",
        "child state file was not refused",
    )
    expect("NSC-044.json" in message, "refusal did not name the state file")


def test_undo_decomposition_refuses_advanced_child_taskgraph_state(root: Path) -> None:
    environment = UndoEnvironment(root)
    runner = FakeGitHubRunner(task_states={"NSC-043": "delivered"})
    message = _expect_refusal(
        environment.operation(runner).preflight,
        "already consumed or reserved",
        "advanced child TaskGraph state was not refused",
    )
    expect("delivered" in message, "refusal did not name the TaskGraph state")


def test_undo_decomposition_refuses_wrong_plan_identity(root: Path) -> None:
    environment = UndoEnvironment(root)
    payload = json.loads(environment.graph_delta.read_text(encoding="utf-8"))
    payload["parent_before_summary"]["task_id"] = "NSC-030"
    other = root / "other_graph_delta.json"
    other.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    operation = DecompositionUndoReset(
        source=environment.work,
        checkout_root=environment.checkout_root,
        task_id=environment.parent_id,
        graph_delta=other,
        runner=FakeGitHubRunner(),
    )
    _expect_refusal(
        operation.preflight,
        "belongs to NSC-030",
        "mismatched plan artifact was not refused",
    )


def test_undo_decomposition_refuses_dirty_controller(root: Path) -> None:
    environment = UndoEnvironment(root)
    (environment.work / "FixtureUnrelated.txt").write_text(
        "uncommitted operator edit\n", encoding="utf-8", newline="\n"
    )
    _expect_refusal(
        environment.operation().preflight,
        "not completely clean",
        "dirty controller was not refused",
    )
    expect(
        (environment.work / "FixtureUnrelated.txt").read_text(encoding="utf-8")
        == "uncommitted operator edit\n",
        "refusal silently cleaned the dirty checkout",
    )


def test_undo_decomposition_refuses_origin_movement_after_preflight(root: Path) -> None:
    environment = UndoEnvironment(root)
    operation = environment.operation()
    plan = operation.preflight()
    before_count = environment.commit_count()

    mover = root / "mover"
    run("git", "clone", "-q", "-b", "main", str(environment.bare), str(mover), cwd=root)
    run("git", "config", "user.email", "t@t.invalid", cwd=mover)
    run("git", "config", "user.name", "t", cwd=mover)
    (mover / "FixtureUnrelated.txt").write_text(
        "other operator\n", encoding="utf-8", newline="\n"
    )
    run("git", "add", "-A", cwd=mover)
    run("git", "commit", "-q", "--no-gpg-sign", "-m", "other", cwd=mover)
    run("git", "push", "-q", "origin", "HEAD:refs/heads/main", cwd=mover)

    with approved_identity_environment():
        _expect_refusal(
            lambda: operation.apply(plan),
            "origin/main",
            "origin/main movement was not refused",
        )
    expect(environment.commit_count() == before_count, "refused apply created a commit")


def test_undo_decomposition_resume_does_not_create_a_second_undo(root: Path) -> None:
    environment = UndoEnvironment(root)
    report_path, undo_commit, plan = _create_stopped_undo(environment)
    after_undo_count = environment.commit_count()
    expect(after_undo_count == 3, "undo commit was not created before the push failure")
    expect(environment.origin_main() == plan["apply_commit"], "push unexpectedly succeeded")
    receipt = json.loads(report_path.read_text(encoding="utf-8"))
    expect(receipt["status"] == "stopped", "receipt did not record the stop")
    expect(receipt["undo_commit"] == undo_commit, "receipt did not record the undo commit")

    with approved_identity_environment():
        resumed = environment.operation(FakeGitHubRunner()).resume(report_path)
    expect(resumed["status"] == "complete", "resume did not complete")
    expect(resumed["resumed"] is True, "resume did not mark itself")
    expect(
        environment.commit_count() == after_undo_count,
        "resume created a second undo commit",
    )
    expect(environment.head() == undo_commit, "resume moved HEAD")
    expect(environment.origin_main() == undo_commit, "resume did not publish the undo")


def test_undo_decomposition_resume_refuses_dirty_controller(root: Path) -> None:
    environment = UndoEnvironment(root)
    report_path, _, _ = _create_stopped_undo(environment)
    dirty = environment.work / "FixtureUnrelated.txt"
    dirty.write_text("operator edit\n", encoding="utf-8", newline="\n")
    _expect_refusal(
        lambda: environment.operation().resume(report_path),
        "not completely clean",
        "dirty resume checkout was not refused",
    )
    expect(dirty.read_text(encoding="utf-8") == "operator edit\n", "resume cleaned work")
    expect(
        (
            environment.checkout_root
            / ".task-review-agent"
            / (environment.parent_id + ".json")
        ).is_file(),
        "dirty refusal archived parent state",
    )


def test_undo_decomposition_resume_refuses_wrong_branch(root: Path) -> None:
    environment = UndoEnvironment(root)
    report_path, _, _ = _create_stopped_undo(environment)
    run("git", "switch", "-q", "-c", "wrong-resume-branch", cwd=environment.work)
    _expect_refusal(
        lambda: environment.operation().resume(report_path),
        "requires the controller on main",
        "wrong resume branch was not refused",
    )
    expect(
        (
            environment.checkout_root
            / ".task-review-agent"
            / (environment.parent_id + ".json")
        ).is_file(),
        "wrong-branch refusal archived parent state",
    )


def test_undo_decomposition_resume_refuses_wrong_head(root: Path) -> None:
    environment = UndoEnvironment(root)
    report_path, undo_commit, _ = _create_stopped_undo(environment)
    later = environment.work / "FixtureUnrelated.txt"
    later.write_text("later local work\n", encoding="utf-8", newline="\n")
    run("git", "add", "--", "FixtureUnrelated.txt", cwd=environment.work)
    run(
        "git",
        "commit",
        "-q",
        "--no-gpg-sign",
        "-m",
        "fixture: later local work",
        cwd=environment.work,
    )
    expect(environment.head() != undo_commit, "fixture did not move HEAD")
    _expect_refusal(
        lambda: environment.operation().resume(report_path),
        "not the receipt undo commit",
        "wrong resume HEAD was not refused",
    )
    expect(
        (
            environment.checkout_root
            / ".task-review-agent"
            / (environment.parent_id + ".json")
        ).is_file(),
        "wrong-HEAD refusal archived parent state",
    )


def test_published_decomposition_undo_recovery_cleans_only_stale_coordination(
    root: Path,
) -> None:
    environment = PublishedUndoEnvironment(root)
    runner = RecoveryGitHubRunner(environment.backend)
    operation = environment.recovery(runner)
    before_head = environment.head()
    before_count = environment.commit_count()
    plan = operation.preflight()
    expect(plan["undo_commit"] == environment.undo_commit, "wrong undo was adopted")
    expect(plan["main_head"] == environment.later_head, "later main was not preserved")
    expect(plan["git_commit_created"] is False, "dry run claimed to create Git history")
    report = operation.apply(plan)
    expect(report["status"] == "complete", "published undo recovery did not complete")
    expect(environment.head() == before_head, "recovery moved main")
    expect(environment.commit_count() == before_count, "recovery created another commit")
    expect(not runner.push_calls, "recovery attempted a Git push")
    issue = environment.backend.list_issues()[0]
    expect(issue["state"] == "CLOSED", "completed parent Issue remains open")
    expect(not environment.checkout.exists(), "stale parent checkout remains")
    expect(
        not (
            environment.checkout_root
            / ".task-review-agent"
            / f"{environment.parent_id}.json"
        ).exists(),
        "active parent state remains",
    )
    expect(report["parent_eligible_for_fresh_decomposition"] is True, "parent not freed")
    expect(
        (environment.work / "LaterUnrelated.txt").read_text(encoding="utf-8")
        == "preserved later work\n",
        "later unrelated work was not preserved",
    )


def test_published_decomposition_undo_recovery_refuses_later_protected_path(
    root: Path,
) -> None:
    environment = PublishedUndoEnvironment(root)
    id_map = environment.work / "Pipeline" / "TaskGraph" / "WORK_ID_MAP.json"
    id_map.write_text(id_map.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    run(
        "git",
        "add",
        "--",
        "Pipeline/TaskGraph/WORK_ID_MAP.json",
        cwd=environment.work,
    )
    run(
        "git",
        "commit",
        "-q",
        "--no-gpg-sign",
        "-m",
        "fixture: touch recovered parent",
        cwd=environment.work,
    )
    run("git", "push", "-q", "origin", "HEAD:refs/heads/main", cwd=environment.work)
    _expect_refusal(
        environment.recovery().preflight,
        "later history touched decomposition or child-owned paths",
        "later parent-path change was not refused",
    )


def test_published_decomposition_undo_recovery_refuses_any_child_issue(
    root: Path,
) -> None:
    environment = PublishedUndoEnvironment(root)
    environment.backend.create_issue(
        title="NSC-043 — consumed child",
        body="<!-- no-safe-circle-task: NSC-043 -->\n",
        labels=[],
        assignees=[],
    )
    _expect_refusal(
        environment.recovery().preflight,
        "children were consumed or remain reserved",
        "child Issue was not refused",
    )


def test_published_recovery_protects_unity_resources_without_false_existing_path(
    root: Path,
) -> None:
    environment = PublishedUndoEnvironment(root)
    operation = environment.recovery()
    paths = operation._repo_paths_for_child(
        {
            "exclusive_resources": [
                "repo-file:Assets/Fixture/Code.cs",
                "unity-scene:Assets/Scenes/Fixture.unity",
                "unity-prefab:Assets/Prefabs/Fixture.prefab",
                "logical:fixture",
            ],
            "provenance": {"expected_paths": ["Assets/Fixture/Expected.txt"]},
        }
    )
    expect(
        paths
        == (
            "Assets/Fixture/Code.cs",
            "Assets/Fixture/Expected.txt",
            "Assets/Prefabs/Fixture.prefab",
            "Assets/Scenes/Fixture.unity",
        ),
        "Unity scene/prefab resources were not converted to protected paths",
    )

    unchanged_existing = {
        "id": "NSC-043",
        "title": "Existing path fixture",
        "exclusive_resources": ["repo-file:FixtureUnrelated.txt"],
    }
    reasons = operation._child_consumption_from_stored(
        unchanged_existing,
        source_commit=environment.fixture.initial_head,
    )
    expect(
        not any("child-owned path" in reason for reason in reasons),
        "an unchanged pre-decomposition file was treated as child consumption",
    )

    scene = environment.work / "Assets" / "Scenes" / "Consumed.unity"
    scene.parent.mkdir(parents=True)
    scene.write_text("consumed scene\n", encoding="utf-8", newline="\n")
    run("git", "add", "--", "Assets/Scenes/Consumed.unity", cwd=environment.work)
    run(
        "git",
        "commit",
        "-q",
        "--no-gpg-sign",
        "-m",
        "fixture: consume child scene",
        cwd=environment.work,
    )
    consumed_scene = {
        "id": "NSC-043",
        "title": "Consumed scene fixture",
        "exclusive_resources": ["unity-scene:Assets/Scenes/Consumed.unity"],
    }
    reasons = operation._child_consumption_from_stored(
        consumed_scene,
        source_commit=environment.fixture.initial_head,
    )
    expect(
        any("Assets/Scenes/Consumed.unity" in reason for reason in reasons),
        "a newly committed child-owned Unity scene was not treated as consumption",
    )


def test_published_recovery_refuses_parent_linked_worktree(root: Path) -> None:
    environment = PublishedUndoEnvironment(root)
    linked = root / "linked-parent"
    run(
        "git",
        "branch",
        environment.branch,
        environment.fixture.initial_head,
        cwd=environment.work,
    )
    run(
        "git",
        "worktree",
        "add",
        "-q",
        str(linked),
        environment.branch,
        cwd=environment.work,
    )
    _expect_refusal(
        environment.recovery().preflight,
        "linked worktree",
        "a parent linked worktree was not inventoried before cleanup",
    )
    expect(linked.is_dir(), "refused recovery removed the linked worktree")


def test_published_recovery_refuses_canonical_checkout_linked_elsewhere(
    root: Path,
) -> None:
    environment = PublishedUndoEnvironment(root)
    _remove_tree_exact(environment.checkout)
    donor = root / "donor"
    run(
        "git",
        "clone",
        "-q",
        "--no-checkout",
        str(environment.bare),
        str(donor),
        cwd=root,
    )
    run(
        "git",
        "worktree",
        "add",
        "-q",
        "-b",
        environment.branch,
        str(environment.checkout),
        environment.fixture.initial_head,
        cwd=donor,
    )
    try:
        environment.recovery().preflight()
    except RehearsalResetError as exc:
        expect(
            "standalone Git clone" in str(exc),
            "linked-checkout refusal reported an unexpected reason",
        )
    else:
        raise AssertionError(
            "a canonical linked worktree from another clone was accepted for raw removal"
        )
    expect(environment.checkout.is_dir(), "refused recovery removed the linked checkout")
    expect(
        (environment.checkout / ".git").is_file(),
        "fixture canonical checkout was not a linked worktree",
    )


def _stopped_recovery_before_cleanup(
    environment: PublishedUndoEnvironment,
) -> Path:
    operation = environment.recovery(RecoveryGitHubRunner(environment.backend))
    plan = operation.preflight()

    def interrupt_before_close(_report):
        raise TaskResetError("fixture interruption before Issue close")

    operation._close_exact_issue = interrupt_before_close
    try:
        operation.apply(plan)
    except TaskResetError as exc:
        expect("fixture interruption" in str(exc), "unexpected recovery stop")
    else:
        raise AssertionError("fixture recovery did not stop before cleanup")
    receipts = sorted(
        (
            environment.checkout_root
            / ".task-review-agent"
            / "reset-runs"
            / environment.parent_id
        ).glob("*-recover-published-decomposition-undo.json")
    )
    expect(len(receipts) == 1, "stopped recovery receipt was not preserved")
    return receipts[0]


def test_published_recovery_resume_revalidates_before_mutation(root: Path) -> None:
    environment = PublishedUndoEnvironment(root)
    receipt = _stopped_recovery_before_cleanup(environment)
    environment.backend.create_issue(
        title="NSC-043 — consumed after preflight",
        body="<!-- no-safe-circle-task: NSC-043 -->\n",
        labels=[],
        assignees=[],
    )
    _expect_refusal(
        lambda: environment.recovery(
            RecoveryGitHubRunner(environment.backend)
        ).resume(receipt),
        "children were consumed or remain reserved",
        "resume did not revalidate child consumption before cleanup",
    )
    expect(
        environment.backend.get_issue(1)["state"] == "OPEN",
        "resume closed the parent Issue before detecting new child work",
    )
    expect(environment.checkout.is_dir(), "resume removed the parent checkout")
    expect(
        (
            environment.checkout_root
            / ".task-review-agent"
            / f"{environment.parent_id}.json"
        ).is_file(),
        "resume archived parent state before detecting new child work",
    )


def test_published_recovery_resume_rebinds_receipt_authority(root: Path) -> None:
    environment = PublishedUndoEnvironment(root)
    receipt = _stopped_recovery_before_cleanup(environment)
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["plan_id"] = "GDP-" + "0" * 64
    receipt.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _expect_refusal(
        lambda: environment.recovery(
            RecoveryGitHubRunner(environment.backend)
        ).resume(receipt),
        "plan_id differs",
        "resume did not rebind the receipt to graph/history authority",
    )
    expect(
        environment.backend.get_issue(1)["state"] == "OPEN",
        "authority mismatch closed the parent Issue",
    )
    expect(environment.checkout.is_dir(), "authority mismatch removed the checkout")


def test_published_recovery_resume_rechecks_private_repository(root: Path) -> None:
    environment = PublishedUndoEnvironment(root)
    runner = RecoveryGitHubRunner(environment.backend)
    operation = environment.recovery(runner)
    plan = operation.preflight()

    def interrupt_before_close(_report):
        raise TaskResetError("fixture interruption before Issue close")

    operation._close_exact_issue = interrupt_before_close
    try:
        operation.apply(plan)
    except TaskResetError as exc:
        expect("fixture interruption" in str(exc), "unexpected recovery stop")
    else:
        raise AssertionError("fixture recovery did not stop before cleanup")
    receipt = next(
        (
            environment.checkout_root
            / ".task-review-agent"
            / "reset-runs"
            / environment.parent_id
        ).glob("*-recover-published-decomposition-undo.json")
    )
    runner.visibility = "PUBLIC"
    try:
        environment.recovery(runner).resume(receipt)
    except RehearsalResetError as exc:
        expect(
            "PRIVATE GitHub repository" in str(exc),
            "repository-privacy refusal reported an unexpected reason",
        )
    else:
        raise AssertionError(
            "resume did not re-check repository privacy before cleanup"
        )
    expect(
        environment.backend.get_issue(1)["state"] == "OPEN",
        "resume closed the Issue",
    )
    expect(environment.checkout.is_dir(), "resume removed the checkout")


def test_published_recovery_resume_rechecks_state_file_bytes(root: Path) -> None:
    environment = PublishedUndoEnvironment(root)
    scope = (
        environment.checkout_root
        / ".task-review-agent"
        / f"{environment.parent_id}.scope.json"
    )
    scope.write_text('{"scope":"before"}\n', encoding="utf-8", newline="\n")
    receipt = _stopped_recovery_before_cleanup(environment)
    scope.write_text('{"scope":"after"}\n', encoding="utf-8", newline="\n")
    _expect_refusal(
        lambda: environment.recovery(
            RecoveryGitHubRunner(environment.backend)
        ).resume(receipt),
        "state file content changed",
        "resume rebound state authority by filename without checking bytes",
    )
    expect(
        environment.backend.get_issue(1)["state"] == "OPEN",
        "resume closed the Issue",
    )
    expect(environment.checkout.is_dir(), "resume removed the checkout")
    expect(scope.is_file(), "resume archived the changed state file")


def test_published_recovery_resume_refuses_closed_issue_without_marker(
    root: Path,
) -> None:
    environment = PublishedUndoEnvironment(root)
    receipt = _stopped_recovery_before_cleanup(environment)
    environment.backend.issues[1]["state"] = "CLOSED"
    _expect_refusal(
        lambda: environment.recovery(
            RecoveryGitHubRunner(environment.backend)
        ).resume(receipt),
        "recovery audit marker",
        "an externally closed Issue bypassed the recovery audit marker",
    )
    expect(environment.checkout.is_dir(), "resume removed the checkout")
    expect(
        (
            environment.checkout_root
            / ".task-review-agent"
            / f"{environment.parent_id}.json"
        ).is_file(),
        "resume archived parent state",
    )


def test_published_decomposition_undo_recovery_resumes_partial_cleanup(
    root: Path,
) -> None:
    environment = PublishedUndoEnvironment(root)
    first = environment.recovery(RecoveryGitHubRunner(environment.backend))
    plan = first.preflight()
    original_remove = first._remove_exact_checkout

    def remove_then_interrupt(report):
        original_remove(report)
        raise TaskResetError("fixture interruption after checkout removal")

    first._remove_exact_checkout = remove_then_interrupt
    try:
        first.apply(plan)
    except TaskResetError as exc:
        expect("fixture interruption" in str(exc), "unexpected interruption error")
    else:
        raise AssertionError("fixture interruption did not stop recovery")
    receipts = sorted(
        (
            environment.checkout_root
            / ".task-review-agent"
            / "reset-runs"
            / environment.parent_id
        ).glob("*-recover-published-decomposition-undo.json")
    )
    expect(len(receipts) == 1, "partial recovery receipt was not preserved")
    before_count = environment.commit_count()
    resumed = environment.recovery(
        RecoveryGitHubRunner(environment.backend)
    ).resume(receipts[0])
    expect(resumed["status"] == "complete", "partial recovery did not resume")
    expect(environment.commit_count() == before_count, "resume created Git history")
    marker = f"nsc-published-decomposition-undo-recovery: {environment.undo_commit}"
    comments = environment.backend.get_comments(1)
    expect(
        sum(marker in str(item.get("body") or "") for item in comments) == 1,
        "resume duplicated the recovery audit comment",
    )


def test_undo_decomposition_rejects_invalid_graph_delta_cleanly(root: Path) -> None:
    environment = UndoEnvironment(root)
    invalid = root / "invalid_graph_delta.json"
    invalid.write_text("not json\n", encoding="utf-8", newline="\n")
    _expect_refusal(
        lambda: DecompositionUndoReset(
            source=environment.work,
            checkout_root=environment.checkout_root,
            task_id=environment.parent_id,
            graph_delta=invalid,
            runner=FakeGitHubRunner(),
        ),
        "graph-delta authority was refused",
        "invalid graph delta escaped the reset error boundary",
    )


def test_ordinary_reset_modes_are_unchanged(root: Path) -> None:
    del root
    from Pipeline.TaskReviewAgent import reset_task as module

    for name in (
        "ProductionAbandonedStateCleanup",
        "RehearsalTaskReset",
        "AbandonedRehearsalTaskReset",
        "ProductionDeliveredTaskReset",
    ):
        expect(hasattr(module, name), "ordinary reset mode " + name + " disappeared")
    expect(
        _decomposition_children(
            {"decomposition_state": "decomposed", "decomposition_children": ["NSC-043"]}
        )
        == ("NSC-043",),
        "child discovery did not read the applied parent contract",
    )
    for task in (
        {"decomposition_state": "concrete", "decomposition_children": ["NSC-043"]},
        {"decomposition_state": "decomposed"},
        {"decomposition_state": "decomposed", "decomposition_children": []},
    ):
        try:
            _decomposition_children(task)
        except TaskResetError:
            continue
        raise AssertionError("unsafe parent contract was accepted")
    expect(
        reset_task_main(["NSC-042", "--undo-decomposition"]) == 2,
        "--undo-decomposition without --graph-delta was not refused",
    )


def main() -> int:
    test_dependency_walk()
    test_undecomposed_aggregate_is_safe_abandoned_rehearsal_state()
    test_unpushed_decomposition_baseline_is_safe()
    preferred = Path(os.environ.get("NSC_TEST_TEMP_ROOT", ""))
    temporary_parent = preferred if str(preferred) else None
    if temporary_parent:
        temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="reset-production-task-",
        dir=str(temporary_parent) if temporary_parent else None,
    ) as directory:
        root = Path(directory)
        test_path_guard(root / "repo")
        test_readonly_tree_removal(root)
        test_branchless_checkout_manifest_guard(root)
        test_branchless_checkout_source_may_advance_on_main(root)
        test_exact_remote_branch_object_is_fetched_without_local_ref(root)

        undo_tests = (
            test_undo_decomposition_dry_run_is_read_only,
            test_undo_decomposition_restores_exact_source_tree,
            test_undo_decomposition_refuses_later_main,
            test_undo_decomposition_refuses_changed_graph,
            test_undo_decomposition_refuses_consumed_child_issue,
            test_undo_decomposition_refuses_child_branch,
            test_undo_decomposition_refuses_child_checkout,
            test_undo_decomposition_refuses_child_linked_worktree,
            test_undo_decomposition_refuses_child_claim_ref,
            test_undo_decomposition_refuses_child_state_file,
            test_undo_decomposition_refuses_advanced_child_taskgraph_state,
            test_undo_decomposition_refuses_wrong_plan_identity,
            test_undo_decomposition_refuses_dirty_controller,
            test_undo_decomposition_refuses_origin_movement_after_preflight,
            test_undo_decomposition_resume_does_not_create_a_second_undo,
            test_undo_decomposition_resume_refuses_dirty_controller,
            test_undo_decomposition_resume_refuses_wrong_branch,
            test_undo_decomposition_resume_refuses_wrong_head,
            test_published_decomposition_undo_recovery_cleans_only_stale_coordination,
            test_published_decomposition_undo_recovery_refuses_later_protected_path,
            test_published_decomposition_undo_recovery_refuses_any_child_issue,
            test_published_recovery_protects_unity_resources_without_false_existing_path,
            test_published_recovery_refuses_parent_linked_worktree,
            test_published_recovery_refuses_canonical_checkout_linked_elsewhere,
            test_published_recovery_resume_revalidates_before_mutation,
            test_published_recovery_resume_rebinds_receipt_authority,
            test_published_recovery_resume_rechecks_private_repository,
            test_published_recovery_resume_rechecks_state_file_bytes,
            test_published_recovery_resume_refuses_closed_issue_without_marker,
            test_published_decomposition_undo_recovery_resumes_partial_cleanup,
            test_undo_decomposition_rejects_invalid_graph_delta_cleanly,
            test_ordinary_reset_modes_are_unchanged,
        )
        for index, undo_test in enumerate(undo_tests):
            case_root = root / f"undo-{index:02d}"
            case_root.mkdir(parents=True, exist_ok=True)
            undo_test(case_root)
            print(f"PASS {undo_test.__name__}")
    print("reset_task_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
