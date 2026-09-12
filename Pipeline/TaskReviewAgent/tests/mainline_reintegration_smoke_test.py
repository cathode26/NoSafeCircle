#!/usr/bin/env python3
"""Regression tests for mainline reintegration and mandatory revalidation."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.downstream_pipeline import _default_runner  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    ResumableDownstreamTaskController,
)
from Pipeline.TaskReviewAgent.issue_workflow import WorkflowPhase  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)
from Pipeline.TaskReviewAgent.mainline_reintegration import (  # noqa: E402
    classify_mainline_drift,
)
from Pipeline.TaskReviewAgent import openai_downstream  # noqa: E402


TASK_ID = "NSC-777"
BRANCH = "nsc-777-mainline-integration"
CONTRACT_HASH = "1" * 64


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(
    *args: str,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        tuple(args),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout.decode('utf-8', errors='replace')}\n"
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )
    return result


def git(root: Path, *args: str, check: bool = True) -> str:
    return run(
        "git",
        "-C",
        str(root),
        *args,
        cwd=root,
        check=check,
    ).stdout.decode().strip()


def commit_all(root: Path, message: str) -> str:
    git(root, "add", ".")
    git(root, "commit", "-m", message)
    return git(root, "rev-parse", "HEAD")


def task() -> dict[str, Any]:
    return {
        "id": TASK_ID,
        "title": "Synthetic mainline reintegration",
        "task_contract_sha256": CONTRACT_HASH,
        "contract_path": f"Tasks/{TASK_ID}.yaml",
        "contract_revision": 1,
        "exclusive_resources": ["repo-file:Assets/Feature.cs"],
        "completion_gates": [
            {
                "gate_id": "VAL-001",
                "requirement": "PlayMode validation",
            }
        ],
    }


class FakeWorkflow:
    def __init__(
        self,
        *,
        service: IssueWorkflowService,
        checkout: Path,
        main_head: str,
        worker_id: str,
    ) -> None:
        self.issue_workflow = service
        self.checkout = checkout
        self.main_head = main_head
        self.worker_id = worker_id
        self.last_observation: dict[str, Any] | None = None

    def observe_goal_state(self) -> dict[str, Any]:
        snapshot = self.issue_workflow.find(TASK_ID)
        assert snapshot is not None and snapshot.state is not None
        state = snapshot.state.to_dict()
        observation = {
            "schema_version": "1.0",
            "observation_authority": "real_read_only",
            "environment": {
                "source_head": self.main_head,
                "source_tree": git(
                    self.checkout,
                    "rev-parse",
                    f"{self.main_head}^{{tree}}",
                ),
                "remote_url": git(
                    self.checkout,
                    "remote",
                    "get-url",
                    "origin",
                ),
            },
            "task": {"task_id": TASK_ID, **task()},
            "coordination": {
                "workflow_state": state,
                "issue_number": snapshot.issue_number,
                "issue_url": snapshot.issue_url,
            },
            "checkout": {
                "status": "ready",
                "head_commit": git(self.checkout, "rev-parse", "HEAD"),
                "branch": git(
                    self.checkout,
                    "branch",
                    "--show-current",
                ),
                "clean": not bool(
                    git(
                        self.checkout,
                        "status",
                        "--porcelain=v1",
                    )
                ),
            },
        }
        self.last_observation = observation
        return observation

    def acquire_agent_lease(
        self,
        *,
        planned_approach: str,
        expected_validation: str,
    ) -> dict[str, Any]:
        return self.issue_workflow.acquire_agent_lease(
            task=task(),
            source_head=self.main_head,
            branch=BRANCH,
            checkout_path=str(self.checkout),
            planned_approach=planned_approach,
            expected_validation=expected_validation,
        )

    def publish_human_handoff(self, **values: Any) -> dict[str, Any]:
        return self.issue_workflow.publish_human_handoff(
            task_id=TASK_ID,
            checkout_path=str(self.checkout),
            **values,
        )


def create_fixture(
    root: Path,
    *,
    sensitive: bool,
) -> tuple[Path, str, str, str]:
    remote = root / "remote.git"
    seed = root / "seed"
    checkout = root / "checkout"
    run("git", "init", "--bare", str(remote), cwd=root)
    run("git", "init", "-b", "main", str(seed), cwd=root)
    git(seed, "config", "user.name", "Mainline Reintegration Test")
    git(
        seed,
        "config",
        "user.email",
        "reintegration@example.invalid",
    )
    (seed / "Tasks").mkdir()
    (seed / "Assets").mkdir()
    (seed / "Pipeline/TaskGraph").mkdir(parents=True)
    (seed / f"Tasks/{TASK_ID}.yaml").write_text(
        "id: NSC-777\n",
        encoding="utf-8",
        newline="\n",
    )
    (seed / "Assets/Feature.cs").write_text("base\n", encoding="utf-8", newline="\n")
    (seed / "Pipeline/TaskGraph/taskcontrol.py").write_text(
        "import sys\n"
        "if sys.argv[1:] == ['validate']:\n"
        "    print('taskcontrol validate: PASS')\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
        newline="\n",
    )
    base = commit_all(seed, "Create base")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "main")
    run(
        "git",
        "--git-dir",
        str(remote),
        "symbolic-ref",
        "HEAD",
        "refs/heads/main",
        cwd=root,
    )

    git(seed, "switch", "-c", BRANCH)
    (seed / "Assets/Feature.cs").write_text(
        "task implementation\n",
        encoding="utf-8",
        newline="\n",
    )
    task_head = commit_all(seed, "Implement task")
    git(seed, "push", "-u", "origin", BRANCH)

    git(seed, "switch", "main")
    if sensitive:
        (seed / "Assets/MainlineRuntime.cs").write_text(
            "runtime change\n",
            encoding="utf-8",
            newline="\n",
        )
    else:
        (seed / "Pipeline/TaskReviewAgent").mkdir(parents=True)
        (seed / "Pipeline/TaskReviewAgent/runtime.py").write_text(
            "automation change\n",
            encoding="utf-8",
            newline="\n",
        )
    main_head = commit_all(seed, "Advance main")
    git(seed, "push", "origin", "main")

    run("git", "clone", str(remote), str(checkout), cwd=root)
    git(
        checkout,
        "config",
        "user.name",
        "Mainline Reintegration Test",
    )
    git(
        checkout,
        "config",
        "user.email",
        "reintegration@example.invalid",
    )
    git(checkout, "switch", BRANCH)
    git(
        checkout,
        "fetch",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
    )
    return checkout, base, task_head, main_head


def prepare_service(
    checkout: Path,
    base: str,
    task_head: str,
    main_head: str,
) -> tuple[IssueWorkflowService, FakeWorkflow]:
    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda _: task(),
        worker_id="worker-a",
    )
    service.acquire_agent_lease(
        task=task(),
        source_head=base,
        branch=BRANCH,
        checkout_path=str(checkout),
        planned_approach="Implement task.",
        expected_validation="Human validation.",
    )
    service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=task_head,
        checkout_path=str(checkout),
        implementation_summary="Synthetic implementation.",
        completed_checks=["Synthetic checks passed."],
        human_steps=["Validate behavior."],
        expected_result="Behavior works.",
    )
    service.apply_human_result(
        task_id=TASK_ID,
        result_body=(
            "## Human validation result\n\n"
            "Result: PASS\n"
            f"Tested commit: `{task_head}`\n"
        ),
        actor_id="cathode26",
    )
    service.acquire_agent_lease(
        task=task(),
        source_head=main_head,
        branch=BRANCH,
        checkout_path=str(checkout),
        planned_approach="Prepare delivery evidence.",
        expected_validation="Authoritative Unity tests.",
    )
    return service, FakeWorkflow(
        service=service,
        checkout=checkout,
        main_head=main_head,
        worker_id="worker-a",
    )


def controller_for(
    checkout: Path,
    service: IssueWorkflowService,
    workflow: FakeWorkflow,
    task_head: str,
) -> ResumableDownstreamTaskController:
    controller = object.__new__(ResumableDownstreamTaskController)
    controller.task_id = TASK_ID
    controller.checkout = checkout
    controller.command_runner = _default_runner
    controller.state = {}
    controller.workflow = workflow
    controller._assert_checkout = lambda: require(
        not bool(git(checkout, "status", "--porcelain=v1")),
        "checkout is dirty",
    )
    human_validation = {
        "result": "pass",
        "tested_commit": task_head,
        "body": (
            "## Human validation result\n\n"
            "Result: PASS\n"
            f"Tested commit: `{task_head}`\n"
        ),
    }
    controller._latest_human_validation = lambda: dict(human_validation)
    controller._latest_validation_authority = lambda: {
        "kind": "human",
        **human_validation,
    }
    controller._ensure_git_identity = lambda: None
    controller._persist = lambda: None

    def require_lease(phase: WorkflowPhase):
        snapshot = service.find(TASK_ID)
        assert snapshot is not None and snapshot.state is not None
        require(snapshot.state.phase is phase, "wrong phase")
        return workflow.observe_goal_state(), snapshot.state.to_dict()

    controller._require_lease = require_lease
    return controller


def test_classifier_is_narrow() -> None:
    automation = classify_mainline_drift(
        main_changed_paths=[
            ".github/workflows/task-review-agent-deterministic.yml",
            "Pipeline/TaskReviewAgent/progress.py",
        ],
        task_changed_paths=["Assets/Feature.cs"],
        exclusive_resources=["Assets/Feature.cs"],
        task_contract_path=f"Tasks/{TASK_ID}.yaml",
    )
    require(
        automation["classification"] == "automation_only",
        "automation drift was rejected",
    )
    require(
        automation["human_revalidation_required"] is True,
        "automation-only drift bypassed exact-commit human review",
    )
    sensitive = classify_mainline_drift(
        main_changed_paths=["Assets/MainlineRuntime.cs"],
        task_changed_paths=["Assets/Feature.cs"],
        exclusive_resources=["Assets/Feature.cs"],
        task_contract_path=f"Tasks/{TASK_ID}.yaml",
    )
    require(
        sensitive["human_revalidation_required"] is True,
        "runtime drift bypassed human review",
    )
    unknown = classify_mainline_drift(
        main_changed_paths=["unexpected.txt"],
        task_changed_paths=[],
        exclusive_resources=[],
        task_contract_path=f"Tasks/{TASK_ID}.yaml",
    )
    require(
        unknown["classification"] == "runtime_sensitive",
        "unknown drift was allowlisted",
    )


def test_action_and_terminal_contract_installed() -> None:
    require(
        "integrate_current_main" in openai_downstream._ACTIONS,
        "action was not installed",
    )
    require(
        hasattr(
            ResumableDownstreamTaskController,
            "integrate_current_main",
        ),
        "controller transition was not installed",
    )
    request = SimpleNamespace(task_id=TASK_ID)
    observation = {
        "coordination": {
            "issue_url": (
                "https://github.com/cathode26/NoSafeCircle/issues/777"
            ),
            "workflow_state": {
                "state": "human_action_required",
                "phase": "unity_runtime_validation",
                "branch": BRANCH,
                "head_commit": "a" * 40,
            },
        },
        "downstream": {"receipt": None},
    }
    terminal = openai_downstream._terminal_outcome(request, observation)
    require(
        terminal and terminal["status"] == "human_revalidation_required",
        "handoff was not terminal",
    )


def test_automation_only_integration_creates_new_handoff() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-mainline-auto-") as temporary:
        checkout, base, task_head, main_head = create_fixture(
            Path(temporary),
            sensitive=False,
        )
        service, workflow = prepare_service(
            checkout,
            base,
            task_head,
            main_head,
        )
        controller = controller_for(
            checkout,
            service,
            workflow,
            task_head,
        )
        result = controller.integrate_current_main()
        require(
            result["status"] == "human_revalidation_required",
            f"unexpected result: {result}",
        )
        integrated = git(checkout, "rev-parse", "HEAD")
        parents = git(
            checkout,
            "rev-list",
            "--parents",
            "-n",
            "1",
            integrated,
        ).split()
        require(
            parents == [integrated, task_head, main_head],
            "merge parent order changed",
        )
        require(
            git(checkout, "rev-parse", f"origin/{BRANCH}") == integrated,
            "remote was not advanced",
        )
        snapshot = service.find(TASK_ID)
        assert snapshot is not None and snapshot.state is not None
        require(
            snapshot.state.state.value == "human_action_required",
            "human handoff was not created",
        )
        require(
            snapshot.state.head_commit == integrated,
            "Issue head was not advanced",
        )
        require(
            snapshot.state.human_handoff_commit == integrated,
            "new handoff identity is wrong",
        )
        require(
            snapshot.state.human_result is None,
            "old PASS leaked into new handoff",
        )
        require(
            controller.state["delivery_base_commit"] == main_head,
            "delivery base was not stabilized",
        )
        require(
            controller.state["validation_manifests"] == [],
            "stale manifests were not invalidated",
        )


def test_runtime_sensitive_integration_creates_new_handoff() -> None:
    with tempfile.TemporaryDirectory(
        prefix="nsc-mainline-sensitive-"
    ) as temporary:
        checkout, base, task_head, main_head = create_fixture(
            Path(temporary),
            sensitive=True,
        )
        service, workflow = prepare_service(
            checkout,
            base,
            task_head,
            main_head,
        )
        controller = controller_for(
            checkout,
            service,
            workflow,
            task_head,
        )
        result = controller.integrate_current_main()
        require(
            result["status"] == "human_revalidation_required",
            f"unexpected result: {result}",
        )
        integrated = git(checkout, "rev-parse", "HEAD")
        snapshot = service.find(TASK_ID)
        assert snapshot is not None and snapshot.state is not None
        require(
            snapshot.state.state.value == "human_action_required",
            "human handoff was not created",
        )
        require(
            snapshot.state.phase.value == "unity_runtime_validation",
            "wrong handoff phase",
        )
        require(
            snapshot.state.head_commit == integrated,
            "handoff did not bind integrated commit",
        )
        require(
            snapshot.state.human_result is None,
            "old PASS leaked into new handoff",
        )
        require(
            snapshot.state.human_handoff_commit == integrated,
            "new handoff identity is wrong",
        )


def _run_partial_evidence_closeout_integration(
    *, workflow_head_tracks_evidence: bool
) -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-mainline-partial-evidence-") as temporary:
        checkout, _base, implementation, main_head = create_fixture(
            Path(temporary),
            sensitive=False,
        )
        evidence_path = "Pipeline/TaskGraph/evidence/NSC-777/record.json"
        target = checkout / evidence_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8", newline="\n")
        evidence = commit_all(checkout, "Record delivery evidence")
        git(checkout, "push", "origin", BRANCH)
        captured: dict[str, Any] = {}

        controller = object.__new__(ResumableDownstreamTaskController)
        controller.task_id = TASK_ID
        controller.checkout = checkout
        controller.command_runner = _default_runner
        controller.workflow = SimpleNamespace(
            worker_id="worker-a",
            publish_human_handoff=lambda **values: captured.update(values) or values,
        )
        controller.state = {
            "implementation_commit": implementation,
            "evidence_commit": evidence,
            "evidence_tree": git(checkout, "rev-parse", "HEAD^{tree}"),
            "created_paths": [evidence_path],
            "validation_manifests": [{"stale": True}],
        }
        observation = {
            "task": {"task_id": TASK_ID, **task()},
            "environment": {"source_head": main_head},
            "coordination": {
                "workflow_state": {
                    "state": "agent_working",
                    "phase": "merge_closeout",
                    "worker_id": "worker-a",
                    "head_commit": (
                        evidence if workflow_head_tracks_evidence else implementation
                    ),
                    "human_handoff_commit": implementation,
                    "branch": BRANCH,
                }
            },
            "checkout": {
                "status": "ready",
                "head_commit": evidence,
                "branch": BRANCH,
                "clean": True,
                "persisted_evidence_recovery": (
                    None
                    if workflow_head_tracks_evidence
                    else {
                        "status": "recovered",
                        "implementation_commit": implementation,
                        "evidence_commit": evidence,
                        "created_paths": [evidence_path],
                    }
                ),
            },
        }
        controller.observe = lambda: observation
        controller._assert_checkout = lambda: require(
            not bool(git(checkout, "status", "--porcelain=v1")),
            "checkout is dirty",
        )
        controller._latest_human_validation = lambda: {
            "result": "pass",
            "tested_commit": implementation,
            "body": "synthetic PASS",
        }
        controller._latest_validation_authority = lambda: {
            "kind": "human",
            "result": "pass",
            "tested_commit": implementation,
            "body": "synthetic PASS",
        }
        controller._ensure_git_identity = lambda: None
        controller._persist = lambda: None

        result = controller.integrate_current_main()
        require(
            result["status"] == "human_revalidation_required",
            f"unexpected partial-evidence integration result: {result}",
        )
        integrated = git(checkout, "rev-parse", "HEAD")
        parents = git(checkout, "rev-list", "--parents", "-n", "1", integrated).split()
        require(
            parents == [integrated, evidence, main_head],
            "integration did not preserve evidence head and current main as ordered parents",
        )
        require(captured.get("head_commit") == integrated, "new handoff used the wrong commit")
        require(not target.exists(), "invalidated evidence remained in integrated commit")
        require(
            result["receipt"]["invalidated_evidence_paths"] == [evidence_path],
            "integration receipt omitted invalidated evidence paths",
        )
        require("evidence_commit" not in controller.state, "stale evidence receipt survived")
        require(controller.state["validation_manifests"] == [], "stale tests survived")


def test_interrupted_evidence_closeout_integrates_new_main_before_pr() -> None:
    _run_partial_evidence_closeout_integration(workflow_head_tracks_evidence=False)


def test_released_evidence_head_integrates_new_main_after_pr_checks() -> None:
    _run_partial_evidence_closeout_integration(workflow_head_tracks_evidence=True)


def test_merge_rechecks_main_after_checks_before_mutating_main() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-mainline-pre-merge-") as temporary:
        checkout, base, task_head, main_head = create_fixture(
            Path(temporary),
            sensitive=False,
        )
        captured: dict[str, Any] = {}
        workflow_state = {
            "state": "agent_working",
            "phase": "merge_closeout",
            "worker_id": "worker-a",
            "head_commit": task_head,
            "human_handoff_commit": task_head,
            "branch": BRANCH,
        }
        observation = {
            "task": {"task_id": TASK_ID, **task()},
            # This deliberately models the observation made before PR checks
            # started.  origin/main advances while the worker waits.
            "environment": {"source_head": base},
            "coordination": {"workflow_state": workflow_state},
            "checkout": {
                "status": "ready",
                "head_commit": task_head,
                "branch": BRANCH,
                "clean": True,
            },
        }
        controller = object.__new__(ResumableDownstreamTaskController)
        controller.task_id = TASK_ID
        controller.checkout = checkout
        commands: list[tuple[str, ...]] = []

        def command_runner(args, cwd, timeout_seconds):
            command = tuple(args)
            commands.append(command)
            if command and command[0] == "gh":
                return subprocess.CompletedProcess(command, 0, b"", b"")
            return _default_runner(command, cwd, timeout_seconds)

        controller.command_runner = command_runner
        controller.workflow = SimpleNamespace(
            worker_id="worker-a",
            issue_workflow=None,
            publish_human_handoff=lambda **values: captured.update(values) or values,
        )
        controller.state = {
            "pull_request_number": 1,
            "pull_request_url": "https://example.invalid/pull/1",
            "evidence_commit": task_head,
            "validation_manifests": [{"stale": True}],
        }
        controller.observe = lambda: observation
        controller._require_lease = lambda phase: (
            observation,
            workflow_state,
        )
        controller._assert_checkout = lambda: require(
            not bool(git(checkout, "status", "--porcelain=v1")),
            "checkout is dirty",
        )
        controller._latest_human_validation = lambda: {
            "result": "pass",
            "tested_commit": task_head,
            "body": "synthetic PASS",
        }
        controller._latest_validation_authority = lambda: {
            "kind": "human",
            "result": "pass",
            "tested_commit": task_head,
            "body": "synthetic PASS",
        }
        controller._ensure_git_identity = lambda: None
        controller._persist = lambda: None
        controller._bound_repository = lambda: "example/fixture"
        controller._view_pr = lambda _number: {
            "number": 1,
            "url": "https://example.invalid/pull/1",
            "state": "OPEN",
            "headRefOid": task_head,
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [],
        }
        controller._check_state = lambda _checks: {
            "passed": [],
            "pending": [],
            "failed": [],
        }

        result = controller.inspect_or_merge_pull_request()

        require(
            result["status"] == "human_revalidation_required",
            f"advanced main was merged without task-branch reintegration: {result}",
        )
        integrated = git(checkout, "rev-parse", "HEAD")
        require(
            git(checkout, "rev-list", "--parents", "-n", "1", integrated).split()
            == [integrated, task_head, main_head],
            "the pre-merge guard did not preserve main as the second parent",
        )
        require(
            captured.get("head_commit") == integrated,
            "the exact integrated commit was not handed back for validation",
        )
        require(
            controller.state.get("merged_commit") is None,
            "main was recorded merged before the integrated branch was revalidated",
        )
        require(
            not any(command and command[0] == "gh" for command in commands),
            "the stale PR was merged before current main was revalidated",
        )


def test_merged_closeout_refreshes_stale_main_then_recognizes_ancestry() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-merged-closeout-resume-") as temporary:
        root = Path(temporary)
        checkout, _base, task_head, stale_main = create_fixture(
            root,
            sensitive=False,
        )
        remote = Path(git(checkout, "remote", "get-url", "origin"))
        publisher = root / "publisher"
        run("git", "clone", str(remote), str(publisher), cwd=root)
        git(publisher, "config", "user.name", "Merged Closeout Test")
        git(publisher, "config", "user.email", "merged-closeout@example.invalid")
        git(publisher, "merge", "--no-ff", f"origin/{BRANCH}", "-m", "Merge task")
        merged_commit = git(publisher, "rev-parse", "HEAD")
        git(publisher, "push", "origin", "main")
        (publisher / "Pipeline/TaskReviewAgent/later.py").write_text(
            "# later controller fix\n",
            encoding="utf-8",
            newline="\n",
        )
        current_main = commit_all(publisher, "Advance main after task merge")
        git(publisher, "push", "origin", "main")
        require(
            git(publisher, "merge-base", "--is-ancestor", task_head, current_main)
            == "",
            "fixture did not contain the exact task head in current main",
        )
        require(merged_commit != current_main, "fixture did not advance after merge")
        require(
            git(checkout, "rev-parse", "origin/main") == stale_main,
            "task checkout unexpectedly refreshed current main",
        )

        class MergedCloseoutWorkflow:
            def __init__(self) -> None:
                self.worker_id = "worker-a"
                self.last_checkout_result: dict[str, Any] | None = None
                self.state = {
                    "state": "agent_ready",
                    "phase": "merge_closeout",
                    "worker_id": None,
                    "branch": BRANCH,
                    "head_commit": task_head,
                }

            def observe_goal_state(self) -> dict[str, Any]:
                refreshed = git(checkout, "rev-parse", "origin/main") == current_main
                checkout_state: dict[str, Any] = {
                    "status": "ready",
                    "head_commit": task_head,
                    "branch": BRANCH,
                    "clean": True,
                }
                if not refreshed:
                    checkout_state["origin_main_refresh_required"] = True
                return {
                    "environment": {"source_head": current_main},
                    "task": {
                        "task_id": TASK_ID,
                        "derived_state": "conformant",
                        **task(),
                    },
                    "coordination": {"workflow_state": dict(self.state)},
                    "checkout": checkout_state,
                }

            def acquire_agent_lease(self, **_values: Any) -> dict[str, Any]:
                self.state.update(state="agent_working", worker_id=self.worker_id)
                return {"status": "acquired"}

            def prepare_task_checkout(self) -> dict[str, Any]:
                raise AssertionError(
                    "merged closeout fell into fresh implementation preparation"
                )

        workflow = MergedCloseoutWorkflow()
        controller = object.__new__(ResumableDownstreamTaskController)
        controller.task_id = TASK_ID
        controller.checkout = checkout
        controller.command_runner = _default_runner
        controller.workflow = workflow
        controller.state = {
            "evidence_commit": task_head,
            "pull_request_number": 82,
            "pull_request_url": "https://example.invalid/pull/82",
        }
        controller.last_observation = None
        controller._latest_delivery_approval = lambda: {"decision": "approve"}

        initial = controller.observe()
        require(
            initial["downstream"]["next_action"] == "acquire_agent_lease",
            "agent-ready merge closeout did not request its lease",
        )
        controller.acquire_agent_lease(
            planned_approach="Verify the already-merged pull request.",
            expected_validation="Prove the exact merge commit remains in current main.",
        )
        stale = controller.observe()
        require(
            stale["downstream"]["mainline_reintegration"]["status"]
            == "main_commit_unavailable",
            "fixture did not reproduce the stale-ref ancestry gap",
        )
        require(
            stale["downstream"]["next_action"] == "prepare_task_checkout",
            "fixture did not reproduce the bad deterministic route",
        )

        refreshed = controller.prepare_task_checkout()
        require(refreshed["origin_main_refreshed"] is True, "main ref was not refreshed")
        resumed = controller.observe()
        require(
            resumed["downstream"]["mainline_reintegration"]["status"]
            == "task_already_in_main",
            "exact task ancestry in current main was not recognized",
        )
        require(
            resumed["downstream"]["next_action"] == "inspect_or_merge_pull_request",
            "merged closeout did not continue to exact pull-request verification",
        )


def main() -> int:
    tests = (
        test_classifier_is_narrow,
        test_action_and_terminal_contract_installed,
        test_automation_only_integration_creates_new_handoff,
        test_runtime_sensitive_integration_creates_new_handoff,
        test_interrupted_evidence_closeout_integrates_new_main_before_pr,
        test_released_evidence_head_integrates_new_main_after_pr_checks,
        test_merge_rechecks_main_after_checks_before_mutating_main,
        test_merged_closeout_refreshes_stale_main_then_recognizes_ancestry,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(
        "TaskReviewAgent mainline reintegration smoke tests: "
        f"PASS ({len(tests)} tests)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
