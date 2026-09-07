#!/usr/bin/env python3
"""Downstream regressions for exact automated synthetic validation authority."""

from __future__ import annotations

import hashlib
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

from Pipeline.TaskReviewAgent.downstream_determinism import (  # noqa: E402
    _authoritative_automated_validation,
    _patched_assert_human_tested_head,
)
from Pipeline.TaskReviewAgent import synthetic_gauntlet_approver as approver  # noqa: E402
from Pipeline.TaskReviewAgent import openai_downstream  # noqa: E402
from Pipeline.TaskReviewAgent import run_autonomous_graph  # noqa: E402
from Pipeline.TaskReviewAgent.autonomous_graph_run import (  # noqa: E402
    AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
    AutonomousGraphController,
    AutonomousRunManifest,
    AutonomousRuntimeConfiguration,
    CoherentGraphSnapshot,
    ManagedIssueObservation,
    MemoryProgressStore,
    MemoryReceiptStore,
    TaskObservation,
)
from Pipeline.TaskReviewAgent.codex_supervisor import SupervisorDecision  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import semantic_sha256  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
    _default_runner,
)
from Pipeline.TaskReviewAgent.downstream_issue import DownstreamIssueCoordinator  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    ResumableDownstreamIssueCoordinator,
    ResumableDownstreamTaskController,
)
from Pipeline.TaskReviewAgent.downstream_resilience import (  # noqa: E402
    validation_plan_for,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    AUTOMATED_VALIDATION_EVIDENCE_AUTHORITY,
    AUTOMATED_VALIDATION_EVIDENCE_SCHEMA_VERSION,
    AUTOMATED_VALIDATION_GAUNTLET_ID,
    AUTOMATED_VALIDATION_REPOSITORY,
    WorkflowActor,
    WorkflowEventType,
    update_issue_body,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)
from Pipeline.TaskReviewAgent.mainline_reintegration import (  # noqa: E402
    _integrate_current_main,
)

TASK_ID = "NSC-912"
CONTRACT_HASH = "a658f6fd3f19e0dd6e59fe64f87bd1b6606a972bad2b2bfaab974f81136d7000"
BRANCH = "nsc-912-synthetic-gauntlet"
WORKER = "synthetic-gauntlet-approver"
FILTER = (
    "NoSafeCircle.DoorPrototype.Tests.Editor.MuffcabbageGauntletTests."
    "MuffcabbageGauntlet912HasExpectedValue"
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout.decode("utf-8").strip()


def selected_task() -> dict:
    return {
        "id": TASK_ID,
        "title": "Set one synthetic C# value",
        "task_contract_sha256": CONTRACT_HASH,
        "execution_scope": "single_agent",
        "exclusive_resources": ["repo-file:Assets/Synthetic/NSC912Value.cs"],
        "provenance": {
            "origin": "human_approved_synthetic_gauntlet",
            "gauntlet_id": AUTOMATED_VALIDATION_GAUNTLET_ID,
            "expected_value": 912,
        },
    }


def fixture(root: Path):
    git(root.parent, "init", "-b", "main", str(root))
    git(root, "config", "user.name", "Automation Test")
    git(root, "config", "user.email", "automation-test@example.invalid")
    policy_path = root / "Pipeline" / "TaskReviewAgent" / "authoritative_validation_policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "tasks": {
                    TASK_ID: {
                        "task_contract_sha256": CONTRACT_HASH,
                        "required_test_platforms": ["EditMode"],
                        "test_filters": {"EditMode": FILTER},
                        "authority": "committed_private_synthetic_gauntlet_validation_policy",
                    }
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    taskcontrol = root / "Pipeline" / "TaskGraph" / "taskcontrol.py"
    taskcontrol.parent.mkdir(parents=True)
    taskcontrol.write_text(
        "import sys\n"
        "if sys.argv[1:] == ['validate']:\n"
        "    print('taskcontrol validate: PASS')\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
    )
    unity_runner = root / "Pipeline" / "Testing" / "run_unity_tests_clean.ps1"
    unity_runner.parent.mkdir(parents=True, exist_ok=True)
    unity_runner.write_text("# trusted fixture runner A\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base validation policy")
    origin = root.parent / "origin.git"
    git(root.parent, "init", "--bare", str(origin))
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "-u", "origin", "main")
    git(root, "switch", "-c", BRANCH)
    implementation = root / "Assets" / "Synthetic" / "NSC912Value.cs"
    implementation.parent.mkdir(parents=True)
    implementation.write_text("internal static class NSC912Value {}\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "fixture implementation")
    head = git(root, "rev-parse", "HEAD")
    git(root, "push", "-u", "origin", BRANCH)
    tree = git(root, "rev-parse", "HEAD^{tree}")
    task = selected_task()
    backend = MemoryIssueBackend()
    backend.repository = AUTOMATED_VALIDATION_REPOSITORY
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda _: task,
        worker_id=WORKER,
    )
    service.acquire_agent_lease(
        task=task,
        source_head=head,
        branch=BRANCH,
        checkout_path=str(root),
        planned_approach="Use the exact synthetic implementation.",
        expected_validation="Run the committed exact Edit Mode filter.",
        now="2026-09-04T12:00:00Z",
    )
    service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=head,
        checkout_path=str(root),
        implementation_summary="Committed the exact synthetic implementation.",
        completed_checks=("Implementation commit is published.",),
        human_steps=("Inspect the synthetic value.",),
        expected_result="The exact value is present.",
        now="2026-09-04T12:01:00Z",
    )
    handoff_id = service.find(TASK_ID).state.last_event_id
    plan = validation_plan_for(root, task)
    assert plan is not None
    required = [{"test_platform": "EditMode", "test_filter": FILTER}]
    evidence = {
        "schema_version": AUTOMATED_VALIDATION_EVIDENCE_SCHEMA_VERSION,
        "authority": AUTOMATED_VALIDATION_EVIDENCE_AUTHORITY,
        "repository": AUTOMATED_VALIDATION_REPOSITORY,
        "repository_private": True,
        "gauntlet_id": AUTOMATED_VALIDATION_GAUNTLET_ID,
        "task_id": TASK_ID,
        "handoff_event_id": handoff_id,
        "branch": BRANCH,
        "commit": head,
        "tree": tree,
        "task_contract_sha256": CONTRACT_HASH,
        "validation_policy_authority": plan["authority"],
        "validation_policy_sha256": plan["policy_sha256"],
        "required_validations": required,
        "unity_validations": [
            {
                "test_platform": "EditMode",
                "test_filter": FILTER,
                "manifest_sha256": "1" * 64,
                "xml_sha256": "2" * 64,
                "log_sha256": "3" * 64,
                "commit": head,
                "tree": tree,
                "post_commit": head,
                "post_tree": tree,
                "repository_clean_before": True,
                "repository_clean_after": True,
                "total": 1,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
            }
        ],
    }
    result = service.apply_automated_validation(
        task_id=TASK_ID,
        evidence=evidence,
        actor_id=WORKER,
        now="2026-09-04T12:02:00Z",
    )
    controller = SimpleNamespace(
        task_id=TASK_ID,
        checkout=root,
        command_runner=_default_runner,
        workflow=SimpleNamespace(issue_workflow=service),
        state={},
        _assert_checkout=lambda: None,
        _persist=lambda: None,
        _latest_human_validation=lambda: None,
    )
    return controller, service, result, plan


def test_exact_automated_event_resolves_without_human_pass() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-auto-downstream-") as temporary:
        controller, service, result, plan = fixture(Path(temporary) / "repo")
        authority = _authoritative_automated_validation(controller)
        require(authority is not None, "automated authority did not resolve")
        require(authority["kind"] == "automated", str(authority))
        require(authority["event_id"] == result["automated_validation_event_id"], str(authority))
        require(authority["policy_sha256"] == plan["policy_sha256"], str(authority))
        require(service.find(TASK_ID).state.human_result is None, "machine evidence became human PASS")
        workflow_state = service.find(TASK_ID).state.to_dict()
        _patched_assert_human_tested_head(controller, workflow_state)
        require(
            controller.state["validation_authority"] == authority,
            "automated authority was not persisted exactly",
        )
        require(
            controller.state["delivery_base_commit"]
            == git(controller.checkout, "rev-parse", "origin/main"),
            "automated downstream authority did not bind its current main base",
        )
        service.acquire_agent_lease(
            task=selected_task(),
            source_head=authority["tested_commit"],
            branch=BRANCH,
            checkout_path=str(controller.checkout),
            planned_approach="Package the validated synthetic task.",
            expected_validation="Preserve the exact automated validation event.",
            now="2026-09-04T12:03:00Z",
        )
        accepted = DownstreamIssueCoordinator(service).accept_unchanged_delivery_after_human_pass(
            task_id=TASK_ID,
            branch=BRANCH,
            head_commit=authority["tested_commit"],
            checkout_path=str(controller.checkout),
            draft_path=str(controller.checkout.parent / "draft.json"),
            draft_sha256="4" * 64,
            proposal_path=str(controller.checkout.parent / "proposal.json"),
            proposal_sha256="5" * 64,
            validation_authority=authority,
            now="2026-09-04T12:04:00Z",
        )
        final_event = service.find(TASK_ID).events[-1]
        require(accepted["status"] == "agent_ready", str(accepted))
        require(final_event.event_type is WorkflowEventType.AGENT_LEASE_RELEASED, str(final_event))
        require(final_event.actor_type is WorkflowActor.AGENT, str(final_event))
        require(
            final_event.details.get("automated_validation_event_id") == authority["event_id"],
            str(final_event.details),
        )
        require(
            "human_validation_event_id" not in final_event.details,
            "machine delivery acceptance was relabeled as human",
        )


def test_policy_or_checkout_drift_invalidates_automated_authority() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-auto-downstream-stale-") as temporary:
        root = Path(temporary) / "repo"
        controller, _, _, _ = fixture(root)
        policy = root / "Pipeline" / "TaskReviewAgent" / "authoritative_validation_policy.json"
        value = json.loads(policy.read_text(encoding="utf-8"))
        value["tasks"][TASK_ID]["test_filters"]["EditMode"] += ".Changed"
        policy.write_text(json.dumps(value), encoding="utf-8")
        try:
            _authoritative_automated_validation(controller)
        except DownstreamPipelineError as exc:
            require("stale validation policy" in str(exc), str(exc))
        else:
            raise AssertionError("changed validation policy retained machine authority")

    with tempfile.TemporaryDirectory(prefix="nsc-auto-downstream-commit-") as temporary:
        root = Path(temporary) / "repo"
        controller, _, _, _ = fixture(root)
        (root / "later-main.txt").write_text("new integration\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-m", "new integration commit")
        try:
            _authoritative_automated_validation(controller)
        except DownstreamPipelineError as exc:
            require("current checkout" in str(exc), str(exc))
        else:
            raise AssertionError("new integration commit retained machine authority")

    with tempfile.TemporaryDirectory(prefix="nsc-auto-downstream-contract-") as temporary:
        root = Path(temporary) / "repo"
        controller, service, _, _ = fixture(root)
        service.task_loader(TASK_ID)["task_contract_sha256"] = "b" * 64
        try:
            _authoritative_automated_validation(controller)
        except DownstreamPipelineError as exc:
            require("stale task contract" in str(exc), str(exc))
        else:
            raise AssertionError("contract migration retained machine authority")


def test_current_main_integration_accepts_only_exact_synthetic_authority() -> None:
    """Regression-only: private synthetic evidence may reach a new exact handoff.

    The integration itself is real Git work in a disposable repository.  The
    resulting merge commit must not be described or persisted as human-tested,
    and ordinary missing validation authority must remain a hard refusal.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-auto-mainline-") as temporary:
        temporary_root = Path(temporary)
        checkout = temporary_root / "repo"
        controller, service, _, _ = fixture(checkout)
        task_head = git(checkout, "rev-parse", "HEAD")
        prior_authority = _authoritative_automated_validation(controller)
        assert prior_authority is not None
        controller.state["validation_authority"] = prior_authority

        mainline = temporary_root / "mainline"
        git(
            temporary_root,
            "clone",
            "--branch",
            "main",
            str(temporary_root / "origin.git"),
            str(mainline),
        )
        git(mainline, "config", "user.name", "Automation Test")
        git(mainline, "config", "user.email", "automation-test@example.invalid")
        automation_change = mainline / "Pipeline" / "TaskReviewAgent" / "runtime.py"
        automation_change.write_text("private gauntlet update\n", encoding="utf-8")
        git(mainline, "add", ".")
        git(mainline, "commit", "-m", "Advance private gauntlet main")
        main_head = git(mainline, "rev-parse", "HEAD")
        git(mainline, "push", "origin", "main")

        service.acquire_agent_lease(
            task=selected_task(),
            source_head=main_head,
            branch=BRANCH,
            checkout_path=str(checkout),
            planned_approach="Integrate current main before delivery evidence.",
            expected_validation="Require exact synthetic validation authority.",
            now="2026-09-04T12:03:00Z",
        )

        def observe() -> dict:
            snapshot = service.find(TASK_ID)
            assert snapshot is not None and snapshot.state is not None
            return {
                "task": {"task_id": TASK_ID, **selected_task()},
                "coordination": {
                    "workflow_state": snapshot.state.to_dict(),
                    "issue_number": snapshot.issue_number,
                    "issue_url": snapshot.issue_url,
                },
                "checkout": {
                    "status": "ready",
                    "head_commit": git(checkout, "rev-parse", "HEAD"),
                    "branch": git(checkout, "branch", "--show-current"),
                    "clean": not bool(git(checkout, "status", "--porcelain=v1")),
                },
            }

        controller.observe = observe
        controller.workflow = SimpleNamespace(
            issue_workflow=service,
            worker_id=WORKER,
            publish_human_handoff=lambda **values: service.publish_human_handoff(
                task_id=TASK_ID,
                checkout_path=str(checkout),
                **values,
            ),
        )
        controller._latest_validation_authority = lambda: (
            _authoritative_automated_validation(controller)
        )
        controller._ensure_git_identity = lambda: None

        result = _integrate_current_main(controller)
        integrated = git(checkout, "rev-parse", "HEAD")
        parents = git(checkout, "rev-list", "--parents", "-n", "1", integrated).split()
        require(result["status"] == "human_revalidation_required", str(result))
        require(parents == [integrated, task_head, main_head], str(parents))
        require(
            result["receipt"].get("validation_authority_kind") == "automated",
            str(result["receipt"]),
        )
        require(
            result["receipt"].get("validated_commit") == task_head,
            str(result["receipt"]),
        )
        require(
            result["receipt"].get("human_tested_commit") is None,
            "automated authority was persisted as a human-tested commit",
        )
        snapshot = service.find(TASK_ID)
        assert snapshot is not None and snapshot.state is not None
        require(snapshot.state.human_result is None, "integration fabricated human PASS")


def test_controller_b_revalidates_old_handoff_before_reintegration_and_graph_progress() -> None:
    """Controller B validates A, is reintegrated, then validates the new B commit.

    This composes the installed action router, both real reintegration receipts,
    the synthetic adapter, schema-1.1 importer, workflow events, and downstream
    resume. Only the Unity process is a deterministic stand-in.
    """

    with tempfile.TemporaryDirectory(prefix="nsc-auto-revalidation-") as temporary:
        temporary_root = Path(temporary)
        checkout = temporary_root / TASK_ID
        fixture_controller, service, _, _ = fixture(checkout)
        controller = object.__new__(ResumableDownstreamTaskController)
        controller.__dict__.update(fixture_controller.__dict__)
        for overridden_method in (
            "_assert_checkout",
            "_latest_human_validation",
            "_persist",
        ):
            controller.__dict__.pop(overridden_method, None)
        controller.unity_executable = None
        controller.explicit_output_root = temporary_root / "outputs"
        controller.state_root = temporary_root / ".task-review-agent"
        controller.state_path = controller.state_root / f"{TASK_ID}.downstream.json"
        controller.last_observation = None
        task_head = git(checkout, "rev-parse", "HEAD")
        prior_authority = _authoritative_automated_validation(controller)
        assert prior_authority is not None
        controller.state["validation_authority"] = prior_authority

        mainline = temporary_root / "mainline"
        git(
            temporary_root,
            "clone",
            "--branch",
            "main",
            str(temporary_root / "origin.git"),
            str(mainline),
        )
        git(mainline, "config", "user.name", "Automation Test")
        git(mainline, "config", "user.email", "automation-test@example.invalid")
        automation_change = mainline / "Pipeline" / "TaskReviewAgent" / "runtime.py"
        automation_change.write_text("private gauntlet update\n", encoding="utf-8")
        controller_runner = (
            mainline / "Pipeline" / "Testing" / "run_unity_tests_clean.ps1"
        )
        git(mainline, "add", ".")
        git(mainline, "commit", "-m", "Advance private gauntlet main with runner A")
        main_head = git(mainline, "rev-parse", "HEAD")
        git(mainline, "push", "origin", "main")

        service.acquire_agent_lease(
            task=selected_task(),
            source_head=main_head,
            branch=BRANCH,
            checkout_path=str(checkout),
            planned_approach="Integrate current main before delivery evidence.",
            expected_validation="Require new exact synthetic validation authority.",
            now="2026-09-04T12:03:00Z",
        )

        def observe() -> dict:
            snapshot = service.find(TASK_ID)
            assert snapshot is not None and snapshot.state is not None
            return {
                "task": {"task_id": TASK_ID, **selected_task()},
                "coordination": {
                    "workflow_state": snapshot.state.to_dict(),
                    "issue_number": snapshot.issue_number,
                    "issue_url": snapshot.issue_url,
                },
                "environment": {
                    "source_head": git(mainline, "rev-parse", "HEAD"),
                    "source_tree": git(mainline, "rev-parse", "HEAD^{tree}"),
                },
                "checkout": {
                    "status": "ready",
                    "head_commit": git(checkout, "rev-parse", "HEAD"),
                    "branch": git(checkout, "branch", "--show-current"),
                    "clean": not bool(git(checkout, "status", "--porcelain=v1")),
                },
            }

        controller.observe = observe
        controller.workflow = SimpleNamespace(
            issue_workflow=service,
            worker_id=WORKER,
            publish_human_handoff=lambda **values: service.publish_human_handoff(
                task_id=TASK_ID,
                checkout_path=str(checkout),
                **values,
            ),
        )
        controller._ensure_git_identity = lambda: None

        def dispatch(action: str, arguments: dict | None = None):
            return openai_downstream._execute(
                SupervisorDecision(
                    task_id=TASK_ID,
                    action=action,
                    arguments=arguments or {},
                    rationale=f"exercise installed downstream route for {action}",
                ),
                controller,
            )

        integration = _integrate_current_main(controller)
        integrated = git(checkout, "rev-parse", "HEAD")
        require(integration["status"] == "human_revalidation_required", str(integration))
        require(integrated != task_head, "fixture did not create an integrated commit")

        handoff = service.find(TASK_ID)
        assert handoff is not None and handoff.state is not None
        require(
            handoff.state.state.value == "human_action_required",
            "integration did not create a new validation handoff",
        )
        integrated_tree = git(checkout, "rev-parse", "HEAD^{tree}")
        require(
            controller.state.get("validation_authority") is None,
            "reintegration retained the old exact-commit authority",
        )

        checkout_runner = checkout / "Pipeline/Testing/run_unity_tests_clean.ps1"
        controller_runner.write_text("# trusted fixture runner B\n", encoding="utf-8")
        git(mainline, "add", ".")
        git(mainline, "commit", "-m", "Advance trusted controller to runner B")
        git(mainline, "push", "origin", "main")
        require(
            checkout_runner.read_bytes() != controller_runner.read_bytes(),
            "fixture did not preserve historical checkout runner A against controller B",
        )

        source_commit = git(mainline, "rev-parse", "HEAD")
        source_tree = git(mainline, "rev-parse", "HEAD^{tree}")
        commands: list[tuple[str, ...]] = []
        original_run = approver.subprocess.run

        def publish_manifest(command) -> Path:
            values = tuple(str(value) for value in command)
            commands.append(values)
            target = Path(values[values.index("-ProjectPath") + 1]).resolve()
            target_commit = git(target, "rev-parse", "HEAD")
            target_tree = git(target, "rev-parse", "HEAD^{tree}")
            runner_path = Path(values[values.index("-File") + 1]).resolve()
            runner_root = runner_path.parents[2]
            runner_source_commit = git(runner_root, "rev-parse", "HEAD")
            runner_source_tree = git(runner_root, "rev-parse", "HEAD^{tree}")
            runner_sha256 = hashlib.sha256(runner_path.read_bytes()).hexdigest()
            artifact_root = temporary_root / f"fresh-controller-b-validation-{len(commands)}"
            artifact_root.mkdir(exist_ok=True)
            xml = b'<test-run result="Passed" total="1" passed="1" failed="0" skipped="0" />\n'
            log = b"controller B validation passed\n"
            (artifact_root / "test-results.xml").write_bytes(xml)
            (artifact_root / "unity.log").write_bytes(log)
            manifest = {
                "schema_version": "1.1",
                "manifest_type": "unity_test_validation",
                "status": "passed",
                "validated_state": {
                    "commit": target_commit,
                    "tree": target_tree,
                    "post_commit": target_commit,
                    "post_tree": target_tree,
                    "repository_clean_before": True,
                    "repository_clean_after": True,
                },
                "unity": {
                    "version": "fixture-1.1",
                    "executable": "fixture://unity",
                    "exit_code": 0,
                    "test_platform": "EditMode",
                    "test_filter": FILTER,
                },
                "test_run": {
                    "result": "Passed",
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                },
                "artifacts": {
                    "xml": {
                        "relative_path": "test-results.xml",
                        "sha256": hashlib.sha256(xml).hexdigest(),
                        "size_bytes": len(xml),
                    },
                    "log": {
                        "relative_path": "unity.log",
                        "sha256": hashlib.sha256(log).hexdigest(),
                        "size_bytes": len(log),
                    },
                },
                "runner": {
                    "path": "Pipeline/Testing/run_unity_tests_clean.ps1",
                    "sha256": runner_sha256,
                    "source_commit": runner_source_commit,
                    "source_tree": runner_source_tree,
                },
            }
            manifest_path = artifact_root / "validation-manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            return manifest_path

        def run_or_publish_manifest(command, *args, **kwargs):
            values = tuple(str(value) for value in command)
            if not values or Path(values[0]).name.casefold() != "powershell.exe":
                return original_run(command, *args, **kwargs)
            manifest_path = publish_manifest(values)
            return SimpleNamespace(
                returncode=0,
                stdout=f"Validation manifest: {manifest_path}\n",
            )

        graph_manifest = AutonomousRunManifest(
            schema_version=AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
            run_id="runner-drift-fixture",
            source_repository=str(mainline.resolve()),
            github_repository=AUTOMATED_VALIDATION_REPOSITORY,
            runtime_configuration=AutonomousRuntimeConfiguration(
                execution_provider="codex",
                execution_model=None,
                execution_max_turns=40,
                architect_provider="codex",
                architect_model=None,
                architect_max_turns=4,
                architect_min_confidence=0.7,
                architect_max_invocations_per_poll=1,
                architect_min_reanalysis_seconds=1.0,
                max_consecutive_observation_failures=1,
                fatal_drain_seconds=1.0,
                fallback_seconds=1.0,
                synthetic_evidence_enabled=True,
            ),
            initial_source_commit=source_commit,
            initial_source_tree=source_tree,
            target_task_ids=(TASK_ID,),
            excluded_task_ids=(),
            max_capacity=1,
        )
        pump = run_autonomous_graph._SyntheticEvidencePump(
            manifest=graph_manifest,
            source=mainline,
            checkout_root=temporary_root,
            repository=AUTOMATED_VALIDATION_REPOSITORY,
        )

        observation_revision = 0

        def graph_snapshot(
            active_assignment_task_ids: tuple[str, ...] = (),
        ) -> CoherentGraphSnapshot:
            nonlocal observation_revision
            observation_revision += 1
            current = service.find(TASK_ID)
            assert current is not None and current.state is not None
            state = current.state
            last_event = current.events[-1]
            return CoherentGraphSnapshot(
                observation_revision=observation_revision,
                source_branch="main",
                source_attached=True,
                source_clean=True,
                source_head=source_commit,
                source_tree=source_tree,
                origin_main_head=source_commit,
                initial_source_commit_is_ancestor=True,
                initial_source_tree=source_tree,
                tasks=(TaskObservation(TASK_ID, "not_delivered"),),
                managed_issues=(
                    ManagedIssueObservation(
                        task_id=TASK_ID,
                        state=state.state,
                        phase=state.phase,
                        state_version=state.state_version,
                        last_event_id=state.last_event_id,
                        head_commit=state.head_commit,
                        human_handoff_commit=state.human_handoff_commit,
                        worker_id=state.worker_id,
                        lease_id=state.lease_id,
                        decomposition_run_id=None,
                        graph_delta_plan_id=None,
                        last_event_evidence_sha256=semantic_sha256(
                            last_event.details
                        ),
                    ),
                ),
                active_assignment_task_ids=active_assignment_task_ids,
                pending_transition_task_ids=(),
                reservation_task_ids=(),
                authorized_local_ahead_recovery_task_id=None,
                authorized_local_ahead_recovery_commit=None,
            )

        def process_public_handoff(snapshot: CoherentGraphSnapshot):
            original_task_gate = approver._require_gauntlet_task
            original_preflight = approver._require_private_rehearsal
            original_hint = approver.publish_resume_hint
            original_backend = approver.GhIssueBackend
            original_service = approver.IssueWorkflowService

            def exact_fixture_task(source: Path, task_id: str) -> dict:
                require(source.resolve() == mainline.resolve(), str(source))
                require(task_id == TASK_ID, task_id)
                return selected_task()

            def exact_fixture_preflight(
                source: Path,
                repository: str,
                expected_source_head: str | None = None,
            ) -> str:
                require(source.resolve() == mainline.resolve(), str(source))
                require(repository == AUTOMATED_VALIDATION_REPOSITORY, repository)
                require(
                    expected_source_head is None
                    or git(source, "rev-parse", "HEAD") == expected_source_head,
                    "controller source moved during public adapter processing",
                )
                require(
                    not git(source, "status", "--porcelain=v1"),
                    "controller source became dirty during public adapter processing",
                )
                return repository

            approver.subprocess.run = run_or_publish_manifest
            approver._require_gauntlet_task = exact_fixture_task
            approver._require_private_rehearsal = exact_fixture_preflight
            approver.publish_resume_hint = lambda *_args, **_kwargs: (
                temporary_root / "synthetic-resume-hint.json"
            )
            approver.GhIssueBackend = lambda **_kwargs: object()
            approver.IssueWorkflowService = lambda **_kwargs: service
            try:
                return pump(snapshot)
            finally:
                approver.subprocess.run = original_run
                approver._require_gauntlet_task = original_task_gate
                approver._require_private_rehearsal = original_preflight
                approver.publish_resume_hint = original_hint
                approver.GhIssueBackend = original_backend
                approver.IssueWorkflowService = original_service

        pumped_a = process_public_handoff(graph_snapshot())

        require(len(commands) == 1, f"controller runner executions: {commands}")
        command = commands[0]
        require(
            Path(command[command.index("-File") + 1]).resolve()
            == controller_runner.resolve(),
            f"historical checkout runner was executed: {command}",
        )
        require(
            Path(command[command.index("-ProjectPath") + 1]).resolve()
            == checkout.resolve(),
            f"controller runner targeted the wrong checkout: {command}",
        )
        after_a = service.find(TASK_ID)
        assert after_a is not None
        event_a = next(
            event for event in after_a.events if event.event_id == pumped_a.event_id
        )
        evidence_a = event_a.details
        require(evidence_a["commit"] == integrated, str(evidence_a))
        require(
            pumped_a.evidence_sha256 == semantic_sha256(evidence_a),
            "autonomous pump result did not bind the exact A-handoff evidence",
        )
        applied_a_event_id = pumped_a.event_id

        service.acquire_agent_lease(
            task=selected_task(),
            source_head=source_commit,
            branch=BRANCH,
            checkout_path=str(checkout),
            planned_approach="Reintegrate runner B before any downstream Unity launch.",
            expected_validation="The installed router selects current-main integration first.",
            now="2026-09-04T12:05:00Z",
        )
        git(
            checkout,
            "fetch",
            "origin",
            "+refs/heads/main:refs/remotes/origin/main",
        )
        resumed_a = service.find(TASK_ID)
        assert resumed_a is not None and resumed_a.state is not None
        action = controller._next_action(observe(), resumed_a.state.to_dict())
        require(action == "integrate_current_main", f"unsafe first action: {action}")
        require(len(commands) == 1, "routing launched historical checkout runner A")

        guarded_runner = controller.command_runner
        blocked_power_commands: list[tuple[str, ...]] = []

        def refuse_historical_power_shell(args, cwd, timeout_seconds):
            values = tuple(str(value) for value in args)
            if values and Path(values[0]).name.casefold() == "powershell.exe":
                blocked_power_commands.append(values)
                raise AssertionError("historical checkout runner A reached execution")
            return guarded_runner(values, cwd, timeout_seconds)

        controller.command_runner = refuse_historical_power_shell
        try:
            controller.run_authoritative_unity_test(
                test_platform="EditMode",
                test_filter=FILTER,
            )
        except DownstreamPipelineError as exc:
            require("origin/main advanced" in str(exc), str(exc))
        else:
            raise AssertionError("direct downstream Unity bypassed mainline reintegration")
        finally:
            controller.command_runner = guarded_runner
        require(not blocked_power_commands, str(blocked_power_commands))

        class FixtureGraphLock:
            def __init__(self) -> None:
                self.held = False

            def acquire(self) -> None:
                require(not self.held, "fixture graph lock was acquired twice")
                self.held = True

            def release(self) -> None:
                require(self.held, "fixture graph lock was released while unheld")
                self.held = False

        class ReintegrationScheduler:
            def __init__(self) -> None:
                self.source = mainline
                self.max_workers = 1
                self.excluded_task_ids = frozenset()
                self.provider_allowlist = (
                    graph_manifest.runtime_configuration.provider_allowlist
                )
                self.active_assignments = {TASK_ID: object()}
                self.architect_invocations_this_poll = 0
                self.worker_launches_this_poll = 0
                self.poll_calls = 0
                self.wait_calls = 0
                self.lifecycle_events: list[str] = []
                self.integration_result = None
                self.handoff = None

            def set_admission_allowlist(self, _task_ids) -> None:
                pass

            def reconcile_interrupted_architect_session(self, *, lock) -> bool:
                require(lock.held, "graph recovery ran without the fixture lock")
                return False

            def start_activity_listener(self) -> bool:
                self.lifecycle_events.append("start")
                return True

            def close_activity_listener(self) -> None:
                self.lifecycle_events.append("close")

            def drain_active_workers(self, **_values) -> bool:
                self.lifecycle_events.append("drain")
                self.active_assignments.clear()
                return True

            def poll_capacity_batch(self):
                self.lifecycle_events.append("poll")
                self.poll_calls += 1
                try:
                    self.integration_result = dispatch("integrate_current_main")
                    self.handoff = service.find(TASK_ID)
                finally:
                    self.active_assignments.clear()
                return SimpleNamespace(status="worker_returned", fatal=False)

            def _wait_for_architect_activity(self, _poll_seconds: float) -> str:
                self.wait_calls += 1
                raise AssertionError(
                    "the reintegration/post-poll-pump graph step must not wait"
                )

        scheduler = ReintegrationScheduler()

        def autonomous_snapshot() -> CoherentGraphSnapshot:
            return graph_snapshot(tuple(sorted(scheduler.active_assignments)))

        graph_controller = AutonomousGraphController(
            manifest=graph_manifest,
            scheduler=scheduler,
            scheduler_lock=FixtureGraphLock(),
            snapshotter=autonomous_snapshot,
            progress_store=MemoryProgressStore(),
            receipt_store=MemoryReceiptStore(),
            synthetic_evidence_pump=process_public_handoff,
            fallback_seconds=1.0,
            transition_settle_seconds=1.0,
        )
        graph_result = graph_controller.run(max_steps=1)
        integration_b = scheduler.integration_result
        require(isinstance(integration_b, dict), str(integration_b))
        integrated_b = git(checkout, "rev-parse", "HEAD")
        integrated_b_tree = git(checkout, "rev-parse", "HEAD^{tree}")
        parents_b = git(
            checkout,
            "rev-list",
            "--parents",
            "-n",
            "1",
            integrated_b,
        ).split()
        require(
            integration_b["status"] == "human_revalidation_required",
            str(integration_b),
        )
        require(parents_b == [integrated_b, integrated, source_commit], str(parents_b))
        require(
            checkout_runner.read_bytes() == controller_runner.read_bytes(),
            "runner B was not materialized by current-main reintegration",
        )
        require(
            controller.state.get("validation_authority") is None
            and controller.state.get("validation_manifests") == [],
            "runner-B reintegration retained stale validation authority",
        )
        handoff_b = scheduler.handoff
        assert handoff_b is not None and handoff_b.state is not None
        require(
            handoff_b.state.state.value == "human_action_required"
            and handoff_b.state.head_commit == integrated_b
            and handoff_b.state.last_event_id
            != applied_a_event_id,
            "runner-B reintegration did not publish a distinct exact handoff",
        )

        require(scheduler.poll_calls == 1, str(scheduler.poll_calls))
        require(scheduler.wait_calls == 0, str(scheduler.wait_calls))
        require(
            scheduler.lifecycle_events == ["start", "poll", "close"],
            str(scheduler.lifecycle_events),
        )
        require(
            graph_result.evaluation.classification == "actionable",
            str(graph_result.evaluation),
        )
        require(
            graph_result.progress.synthetic_pump_calls_total == 2,
            str(graph_result.progress),
        )
        require(len(commands) == 2, f"controller runner executions: {commands}")
        second_command = commands[1]
        require(
            Path(second_command[second_command.index("-File") + 1]).resolve()
            == controller_runner.resolve(),
            f"new handoff did not execute controller runner B: {second_command}",
        )
        after_b = service.find(TASK_ID)
        assert after_b is not None and after_b.state is not None
        pumped_b = SimpleNamespace(event_id=after_b.state.last_event_id)
        event_b = next(
            event for event in after_b.events if event.event_id == pumped_b.event_id
        )
        evidence_b = event_b.details
        require(
            evidence_b["commit"] == integrated_b
            and evidence_b["tree"] == integrated_b_tree,
            str(evidence_b),
        )
        require(
            pumped_b.event_id != pumped_a.event_id,
            "fresh integrated commit reused the old validation event",
        )

        service.acquire_agent_lease(
            task=selected_task(),
            source_head=source_commit,
            branch=BRANCH,
            checkout_path=str(checkout),
            planned_approach="Advance delivery for the freshly validated B commit.",
            expected_validation="Only runner B may execute from this point onward.",
            now="2026-09-04T12:07:00Z",
        )
        resumed_b = service.find(TASK_ID)
        assert resumed_b is not None and resumed_b.state is not None
        action = controller._next_action(observe(), resumed_b.state.to_dict())
        require(action == "run_authoritative_unity_test", f"unexpected action: {action}")

        def record_downstream_power_shell(args, cwd, timeout_seconds):
            values = tuple(str(value) for value in args)
            if values and Path(values[0]).name.casefold() == "powershell.exe":
                manifest_path = publish_manifest(values)
                return subprocess.CompletedProcess(
                    values,
                    0,
                    stdout=f"Validation manifest: {manifest_path}\n".encode("utf-8"),
                    stderr=b"",
                )
            return guarded_runner(values, cwd, timeout_seconds)

        controller.command_runner = record_downstream_power_shell
        try:
            dispatch(
                "run_authoritative_unity_test",
                {
                    "test_platform": "EditMode",
                    "test_filter": FILTER,
                },
            )
        finally:
            controller.command_runner = guarded_runner
        require(len(commands) == 3, f"Unity command count: {commands}")
        downstream_command = commands[2]
        downstream_file = Path(
            downstream_command[downstream_command.index("-File") + 1]
        ).resolve()
        require(
            downstream_file == checkout_runner.resolve()
            and downstream_file.read_bytes() == controller_runner.read_bytes(),
            f"downstream executed bytes other than runner B: {downstream_command}",
        )
        require(
            controller._next_action(observe(), resumed_b.state.to_dict())
            == "create_delivery_review_draft",
            "real downstream graph did not advance after exact B validation",
        )
        refreshed_authority = controller.state.get("validation_authority")
        require(
            isinstance(refreshed_authority, dict)
            and refreshed_authority["event_id"]
            == pumped_b.event_id
            and refreshed_authority["tested_commit"] == integrated_b,
            "downstream did not persist the new exact automated authority",
        )

        coordinator = DownstreamIssueCoordinator(service)
        accepted = coordinator.accept_unchanged_delivery_after_human_pass(
            task_id=TASK_ID,
            branch=BRANCH,
            head_commit=integrated_b,
            checkout_path=str(checkout),
            draft_path=str(temporary_root / "draft.json"),
            draft_sha256="4" * 64,
            proposal_path=str(temporary_root / "proposal.json"),
            proposal_sha256="5" * 64,
            validation_authority=refreshed_authority,
            now="2026-09-04T12:08:00Z",
        )
        require(accepted["status"] == "agent_ready", str(accepted))
        service.acquire_agent_lease(
            task=selected_task(),
            source_head=source_commit,
            branch=BRANCH,
            checkout_path=str(checkout),
            planned_approach="Close the exact runner-B delivery.",
            expected_validation="Preserve the new automated event identity.",
            now="2026-09-04T12:09:00Z",
        )
        completed = coordinator.complete(
            task_id=TASK_ID,
            pull_request_url="https://example.invalid/pull/84",
            pull_request_number=84,
            merged_commit=integrated_b,
            conformant_record_id="DEL-NSC-912-fixture",
            now="2026-09-04T12:10:00Z",
        )
        require(completed["status"] == "complete", str(completed))


def test_current_main_integration_still_refuses_missing_validation_authority() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-no-mainline-authority-") as temporary:
        checkout = Path(temporary) / "repo"
        controller, _, _, _ = fixture(checkout)
        service = controller.workflow.issue_workflow
        service.acquire_agent_lease(
            task=selected_task(),
            source_head=git(checkout, "rev-parse", "origin/main"),
            branch=BRANCH,
            checkout_path=str(checkout),
            planned_approach="Attempt downstream work.",
            expected_validation="Require exact validation authority.",
            now="2026-09-04T12:03:00Z",
        )
        snapshot = service.find(TASK_ID)
        assert snapshot is not None and snapshot.state is not None
        controller.observe = lambda: {
            "task": {"task_id": TASK_ID, **selected_task()},
            "coordination": {"workflow_state": snapshot.state.to_dict()},
            "checkout": {
                "status": "ready",
                "head_commit": git(checkout, "rev-parse", "HEAD"),
                "branch": git(checkout, "branch", "--show-current"),
                "clean": True,
            },
        }
        controller.workflow.worker_id = WORKER
        controller._latest_validation_authority = lambda: None
        try:
            _integrate_current_main(controller)
        except DownstreamPipelineError as exc:
            require("exact validation authority" in str(exc), str(exc))
        else:
            raise AssertionError("missing validation authority reached mainline integration")


def evidence_closeout_fixture(root: Path):
    checkout = root / "repo"
    controller, service, _, _ = fixture(checkout)
    implementation_commit = git(checkout, "rev-parse", "HEAD")
    authority = _authoritative_automated_validation(controller)
    assert authority is not None
    service.acquire_agent_lease(
        task=selected_task(),
        source_head=git(checkout, "rev-parse", "origin/main"),
        branch=BRANCH,
        checkout_path=str(checkout),
        planned_approach="Prepare exact delivery evidence.",
        expected_validation="Preserve the automated validation identity.",
        now="2026-09-04T12:03:00Z",
    )
    DownstreamIssueCoordinator(service).accept_unchanged_delivery_after_human_pass(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=implementation_commit,
        checkout_path=str(checkout),
        draft_path=str(root / "draft.json"),
        draft_sha256="4" * 64,
        proposal_path=str(root / "proposal.json"),
        proposal_sha256="5" * 64,
        validation_authority=authority,
        now="2026-09-04T12:04:00Z",
    )
    service.acquire_agent_lease(
        task=selected_task(),
        source_head=git(checkout, "rev-parse", "origin/main"),
        branch=BRANCH,
        checkout_path=str(checkout),
        planned_approach="Publish the exact delivery evidence and pull request.",
        expected_validation="Verify the exact pull request head and checks.",
        now="2026-09-04T12:05:00Z",
    )
    evidence_path = f"Pipeline/TaskGraph/evidence/{TASK_ID}/records/record.json"
    target = checkout / evidence_path
    target.parent.mkdir(parents=True)
    target.write_text("{}\n", encoding="utf-8", newline="\n")
    git(checkout, "add", evidence_path)
    git(checkout, "commit", "-m", "Record exact delivery evidence")
    evidence_commit = git(checkout, "rev-parse", "HEAD")
    evidence_tree = git(checkout, "rev-parse", "HEAD^{tree}")
    git(checkout, "push", "origin", BRANCH)
    ResumableDownstreamIssueCoordinator(service).release_for_pending_checks(
        task_id=TASK_ID,
        pull_request_url="https://example.invalid/pull/84",
        head_commit=evidence_commit,
        reason="Delivery evidence and pull request are published.",
        now="2026-09-04T12:06:00Z",
    )

    mainline = root / "mainline"
    git(root, "clone", "--branch", "main", str(root / "origin.git"), str(mainline))
    git(mainline, "config", "user.name", "Automation Test")
    git(mainline, "config", "user.email", "automation-test@example.invalid")
    later = mainline / "Pipeline" / "TaskReviewAgent" / "later.py"
    later.write_text("# later mainline work\n", encoding="utf-8", newline="\n")
    git(mainline, "add", ".")
    git(mainline, "commit", "-m", "Advance main during pull request checks")
    main_head = git(mainline, "rev-parse", "HEAD")
    git(mainline, "push", "origin", "main")

    service.acquire_agent_lease(
        task=selected_task(),
        source_head=main_head,
        branch=BRANCH,
        checkout_path=str(checkout),
        planned_approach="Integrate current main before merging the pull request.",
        expected_validation="Require new exact validation for the merge commit.",
        now="2026-09-04T12:07:00Z",
    )
    controller.state = {
        "implementation_commit": implementation_commit,
        "evidence_commit": evidence_commit,
        "evidence_tree": evidence_tree,
        "created_paths": [evidence_path],
        "validation_authority": authority,
        "pull_request_number": 84,
        "pull_request_url": "https://example.invalid/pull/84",
    }

    def observe() -> dict:
        snapshot = service.find(TASK_ID)
        assert snapshot is not None and snapshot.state is not None
        return {
            "task": {"task_id": TASK_ID, **selected_task()},
            "coordination": {
                "workflow_state": snapshot.state.to_dict(),
                "issue_number": snapshot.issue_number,
                "issue_url": snapshot.issue_url,
            },
            "checkout": {
                "status": "ready",
                "head_commit": git(checkout, "rev-parse", "HEAD"),
                "branch": git(checkout, "branch", "--show-current"),
                "clean": not bool(git(checkout, "status", "--porcelain=v1")),
            },
        }

    controller.observe = observe
    controller.workflow = SimpleNamespace(
        issue_workflow=service,
        worker_id=WORKER,
        publish_human_handoff=lambda **values: service.publish_human_handoff(
            task_id=TASK_ID,
            checkout_path=str(checkout),
            **values,
        ),
    )
    controller._latest_validation_authority = lambda: (
        _authoritative_automated_validation(controller)
    )
    controller._ensure_git_identity = lambda: None
    return controller, service, authority, implementation_commit, evidence_commit, main_head


def test_evidence_head_preserves_exact_automated_authority_during_main_integration() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-auto-evidence-mainline-") as temporary:
        controller, service, authority, implementation, evidence, main_head = (
            evidence_closeout_fixture(Path(temporary))
        )
        resolved = _authoritative_automated_validation(controller)
        require(resolved is not None, "evidence closeout lost automated authority")
        require(resolved["tested_commit"] == implementation, str(resolved))
        require(git(controller.checkout, "rev-parse", "HEAD") == evidence, "wrong head")

        result = _integrate_current_main(controller)
        integrated = git(controller.checkout, "rev-parse", "HEAD")
        require(result["status"] == "human_revalidation_required", str(result))
        require(
            git(controller.checkout, "rev-list", "--parents", "-n", "1", integrated).split()
            == [integrated, evidence, main_head],
            "integration did not preserve evidence head and current main",
        )
        require(result["receipt"]["validated_commit"] == implementation, str(result))
        require(
            result["receipt"]["automated_validation_event_id"] == authority["event_id"],
            str(result),
        )
        snapshot = service.find(TASK_ID)
        assert snapshot is not None and snapshot.state is not None
        require(snapshot.state.human_result is None, "integration fabricated human PASS")


def test_evidence_head_authority_mismatch_guards_remain_fail_closed() -> None:
    mutations = (
        (
            "implementation commit",
            lambda c, _s: c.state.__setitem__(
                "implementation_commit",
                "f" * 40,
            ),
        ),
        ("evidence tree", lambda c, _s: c.state.__setitem__("evidence_tree", "f" * 40)),
        (
            "validation event",
            lambda c, _s: c.state["validation_authority"].__setitem__("event_id", "f" * 64),
        ),
        (
            "validation policy",
            lambda c, _s: c.state["validation_authority"].__setitem__("policy_sha256", "f" * 64),
        ),
    )
    for label, mutate in mutations:
        with tempfile.TemporaryDirectory(prefix="nsc-auto-evidence-guard-") as temporary:
            controller, service, *_ = evidence_closeout_fixture(Path(temporary))
            mutate(controller, service)
            try:
                _authoritative_automated_validation(controller)
            except DownstreamPipelineError:
                pass
            else:
                raise AssertionError(f"wrong {label} retained automated authority")

    with tempfile.TemporaryDirectory(prefix="nsc-auto-evidence-issue-head-") as temporary:
        controller, service, *_ = evidence_closeout_fixture(Path(temporary))
        snapshot = service.find(TASK_ID)
        assert snapshot is not None and snapshot.state is not None
        wrong_state = replace(snapshot.state, head_commit="f" * 40)
        service.backend.update_issue(
            snapshot.issue_number,
            body=update_issue_body(snapshot.body, wrong_state),
        )
        try:
            _authoritative_automated_validation(controller)
        except DownstreamPipelineError:
            pass
        else:
            raise AssertionError("wrong Issue head retained automated authority")


def main() -> int:
    tests = (
        test_exact_automated_event_resolves_without_human_pass,
        test_policy_or_checkout_drift_invalidates_automated_authority,
        test_current_main_integration_accepts_only_exact_synthetic_authority,
        test_controller_b_revalidates_old_handoff_before_reintegration_and_graph_progress,
        test_current_main_integration_still_refuses_missing_validation_authority,
        test_evidence_head_preserves_exact_automated_authority_during_main_integration,
        test_evidence_head_authority_mismatch_guards_remain_fail_closed,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Automated validation downstream tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    raise SystemExit(run_with_synthetic_authority(main))
