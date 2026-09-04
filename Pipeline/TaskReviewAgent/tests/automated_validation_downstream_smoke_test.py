#!/usr/bin/env python3
"""Downstream regressions for exact automated synthetic validation authority."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.downstream_determinism import (  # noqa: E402
    _authoritative_automated_validation,
    _patched_assert_human_tested_head,
)
from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
    _default_runner,
)
from Pipeline.TaskReviewAgent.downstream_issue import DownstreamIssueCoordinator  # noqa: E402
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
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)

TASK_ID = "NSC-912"
CONTRACT_HASH = "a" * 64
BRANCH = "nsc-912-synthetic-gauntlet"
WORKER = "synthetic-validation-service"
FILTER = "NoSafeCircle.SyntheticGauntlet.Tests.NSC912Tests"


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
        "exclusive_resources": ["repo-file:Assets/Synthetic/NSC912Value.cs"],
        "provenance": {
            "origin": "human_approved_synthetic_gauntlet",
            "gauntlet_id": AUTOMATED_VALIDATION_GAUNTLET_ID,
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


def main() -> int:
    tests = (
        test_exact_automated_event_resolves_without_human_pass,
        test_policy_or_checkout_drift_invalidates_automated_authority,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Automated validation downstream tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
