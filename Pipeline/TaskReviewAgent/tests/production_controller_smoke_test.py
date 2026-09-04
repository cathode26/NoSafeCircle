#!/usr/bin/env python3
"""Prove the connected controller reaches a durable human-action Issue handoff."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)
from Pipeline.TaskReviewAgent.contracts import TaskReviewContractError  # noqa: E402
from Pipeline.TaskReviewAgent.production_pipeline import ProductionTaskController  # noqa: E402
from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow  # noqa: E402
from Pipeline.TaskReviewAgent.safe_unity_churn import (  # noqa: E402
    classify_safe_post_unity_churn,
)
from Pipeline.TaskReviewAgent.tests.real_checkout_smoke_test import (  # noqa: E402
    TASK_ID,
    create_fixture,
)


WORKER = "task-review-agent-production-controller"
IMPLEMENTATION = "Assets/NoSafeCircle/Synthetic/Scripts/Feature.cs"
NEW_TEST = "Assets/NoSafeCircle/Synthetic/Tests/FeaturePlayModeTests.cs"
NEW_META = NEW_TEST + ".meta"
EDITOR_BUILD_SETTINGS = "ProjectSettings/EditorBuildSettings.asset"
COVERAGE_SETTINGS = (
    "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json"
)
SAFE_HANDOFF_CHURN = (EDITOR_BUILD_SETTINGS, COVERAGE_SETTINGS)
RUN_ID = "nsc-777-controller-smoke"


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def git(root: Path, *args: str, check: bool = True) -> str:
    return run("git", "-C", str(root), *args, cwd=root, check=check).stdout.strip()


def git_bytes(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def add_game_surface(controller: Path) -> None:
    git(controller, "config", "user.name", "Production Controller Smoke")
    git(controller, "config", "user.email", "production-controller@example.invalid")
    (controller / "Assets/NoSafeCircle/Synthetic/Scripts").mkdir(parents=True)
    (controller / "Assets/NoSafeCircle/Synthetic/Tests").mkdir(parents=True)
    (controller / IMPLEMENTATION).write_text(
        "namespace Synthetic { public static class Feature { public const int Value = 1; } }\n",
        encoding="utf-8",
        newline="\n",
    )
    (controller / "Assets/NoSafeCircle/Synthetic/Tests/.keep").write_text(
        "tracked parent\n", encoding="utf-8", newline="\n"
    )
    (controller / ".gitignore").write_text(
        "Pipeline/ExecutionCrew/outputs/\n", encoding="utf-8", newline="\n"
    )
    for relative in SAFE_HANDOFF_CHURN:
        path = controller / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"baseline:{relative}\n", encoding="utf-8", newline="\n")
    git(
        controller,
        "add",
        ".gitignore",
        "Assets/NoSafeCircle/Synthetic",
        *SAFE_HANDOFF_CHURN,
    )
    git(controller, "commit", "-m", "Add synthetic game surface")
    git(controller, "push", "origin", "main")


def candidate_patch() -> bytes:
    return f"""diff --git a/{IMPLEMENTATION} b/{IMPLEMENTATION}
--- a/{IMPLEMENTATION}
+++ b/{IMPLEMENTATION}
@@ -1 +1 @@
-namespace Synthetic {{ public static class Feature {{ public const int Value = 1; }} }}
+namespace Synthetic {{ public static class Feature {{ public const int Value = 2; }} }}
diff --git a/{NEW_TEST} b/{NEW_TEST}
new file mode 100644
--- /dev/null
+++ b/{NEW_TEST}
@@ -0,0 +1 @@
+namespace Synthetic.Tests {{ public sealed class FeaturePlayModeTests {{ }} }}
diff --git a/{NEW_META} b/{NEW_META}
new file mode 100644
--- /dev/null
+++ b/{NEW_META}
@@ -0,0 +1,2 @@
+fileFormatVersion: 2
+guid: fedcba9876543210fedcba9876543210
""".encode("utf-8")


def task_loader(controller: Path, task_id: str) -> dict:
    raw = git_bytes(controller, "show", f"HEAD:Tasks/{task_id}.yaml")
    value = json.loads(raw.decode("utf-8-sig"))
    return {**value, "task_contract_sha256": hashlib.sha256(raw).hexdigest()}


def test_controller_reaches_human_issue_handoff() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-production-controller-") as temporary:
        root = Path(temporary)
        source, _, _ = create_fixture(root)
        add_game_surface(source)
        checkout_root = root / "operator"
        checkout = checkout_root / TASK_ID
        patch = candidate_patch()
        backend = MemoryIssueBackend()
        service = IssueWorkflowService(
            backend=backend,
            task_loader=lambda task_id: task_loader(source, task_id),
            worker_id=WORKER,
        )

        def fake_runner(args, cwd, timeout):
            _ = timeout
            require(Path(cwd).resolve() == checkout.resolve(), "ExecutionCrew used wrong checkout")
            require("claude-exec" in args, "ExecutionCrew used wrong provider service")
            output = checkout / "Pipeline/ExecutionCrew/outputs" / RUN_ID
            output.mkdir(parents=True, exist_ok=True)
            (output / "candidate.patch").write_bytes(patch)
            task = task_loader(checkout, TASK_ID)
            result = {
                "schema_version": "1.0",
                "run_id": RUN_ID,
                "task_id": TASK_ID,
                "task_contract_identity": {
                    "path": f"Tasks/{TASK_ID}.yaml",
                    "revision": 1,
                    "sha256": task["task_contract_sha256"],
                },
                "source_head": git(checkout, "rev-parse", "HEAD"),
                "source_tree": git(checkout, "rev-parse", "HEAD^{tree}"),
                "source_branch": git(checkout, "branch", "--show-current"),
                "provider": "claude",
                "crew_profile": "full",
                "validation_profile": "full_relevant",
                "crew_status": "review_ready",
                "requested_implementation_paths": [IMPLEMENTATION],
                "requested_test_paths": [NEW_TEST],
                "requested_existing_implementation_paths": [IMPLEMENTATION],
                "requested_new_implementation_paths": [],
                "requested_existing_test_paths": [],
                "requested_new_test_paths": [NEW_TEST],
                "pipeline_generated_paths": [NEW_META],
                "implementation_actual_changed_paths": [IMPLEMENTATION],
                "test_actual_changed_paths": [NEW_TEST],
                "final_actual_changed_paths": sorted([IMPLEMENTATION, NEW_TEST, NEW_META]),
                "role_results": [],
                "candidate_patch_path": f"/execution-output/{RUN_ID}/candidate.patch",
                "candidate_patch_sha256": hashlib.sha256(patch).hexdigest(),
                "retry_seed_candidate_sha256": None,
                "retry_seed_mode": None,
                "workspace_diagnostic_patch_path": None,
                "candidate_patch_host_path": str(output / "candidate.patch"),
                "workspace_diagnostic_patch_host_path": None,
                "contract_locality_status": "pass",
                "contract_locality_audit_path": None,
                "contract_locality_audit_host_path": None,
                "rejection_reasons": [],
                "validator_status": "pass",
                "review_origin": None,
                "human_next_step": "Commit and hand off",
                "human_result": {"status": "REVIEW_READY"},
                "attempts_used": 1,
                "duration_seconds": 1.0,
            }
            payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
            (output / "crew_result.json").write_text(payload, encoding="utf-8", newline="\n")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=payload.encode(), stderr=b"")

        workflow = RealTaskReviewWorkflow(
            source=source,
            task_id=TASK_ID,
            checkout_root=checkout_root,
            worker_id=WORKER,
            issue_workflow_service=service,
            allow_local_remote_for_tests=True,
        )
        controller = ProductionTaskController(
            workflow=workflow,
            execution_provider="claude",
            execution_command_runner=fake_runner,
        )

        first = controller.observe()
        require(first["production_pipeline"]["next_action"] == "acquire_agent_lease", "lease not requested")
        lease = controller.acquire_agent_lease(
            planned_approach="Update Feature and add a focused Play Mode test.",
            expected_validation="ExecutionCrew review followed by Vincent's Unity Play Mode check.",
        )
        require(lease["status"] == "acquired", f"lease failed: {lease}")
        second = controller.observe()
        require(second["production_pipeline"]["next_action"] == "prepare_task_checkout", "checkout not requested")
        prepared = controller.prepare_task_checkout()
        require(prepared["status"] in ("created", "ready"), f"checkout failed: {prepared}")
        third = controller.observe()
        require(third["production_pipeline"]["next_action"] == "validate_execution_scope", "scope not requested")
        for provider, model in (("claude", None), ("claude", "manual-model"), ("codex", "manual-codex")):
            manual = ProductionTaskController(
                workflow=workflow,
                execution_provider=provider,
                execution_model=model,
            )
            manual.observe()
            require(manual.execution is not None, "manual controller omitted ExecutionCrew bridge")
            require(
                manual.execution.enable_session_pool is False,
                f"manual {provider}/{model} controller enabled the scheduler-owned pool",
            )
        scheduler = ProductionTaskController(
            workflow=workflow,
            execution_provider="claude",
            execution_model="scheduler-model",
            enable_execution_session_pool=True,
        )
        scheduler.observe()
        require(scheduler.execution is not None, "scheduler controller omitted ExecutionCrew bridge")
        require(
            scheduler.execution.enable_session_pool is True,
            "scheduler opt-in did not reach ExecutionCrew bridge",
        )

        scope_result = controller.validate_execution_scope(
            existing_implementation_paths=[IMPLEMENTATION],
            new_implementation_paths=[],
            existing_test_paths=[],
            new_test_paths=[NEW_TEST],
        )
        require(scope_result["accepted"], f"scope rejected: {scope_result}")
        crew = controller.run_execution_crew(plan_id=scope_result["plan_id"])
        require(crew["crew_status"] == "review_ready", "crew did not reach review_ready")

        publish_human_handoff = workflow.publish_human_handoff

        def publish_with_post_commit_unity_churn(**values):
            for relative in SAFE_HANDOFF_CHURN:
                (checkout / relative).write_text(
                    f"post-commit-unity-churn:{relative}\n",
                    encoding="utf-8",
                    newline="\n",
                )
            return publish_human_handoff(**values)

        workflow.publish_human_handoff = publish_with_post_commit_unity_churn
        handoff = controller.integrate_commit_push_and_handoff(
            run_id=RUN_ID,
            implementation_summary=(
                "Updated the synthetic Feature behavior and added a focused Play Mode test."
            ),
            human_steps=[
                "Open the canonical task checkout in Unity.",
                "Enter Play Mode and verify the Feature value-driven behavior.",
            ],
            expected_result="The updated behavior is visible and no Unity errors occur.",
        )
        require(handoff["status"] == "human_action_required", "handoff did not complete")
        final = controller.observe()
        state = final["coordination"]["workflow_state"]
        require(state["state"] == "human_action_required", "Issue did not become human-owned")
        require(state["head_commit"] == git(checkout, "rev-parse", "HEAD"), "Issue commit is wrong")
        require(git(checkout, "status", "--porcelain=v1", "--untracked-files=all") == "", "handoff checkout dirty")
        for relative in SAFE_HANDOFF_CHURN:
            require(
                (checkout / relative).read_text(encoding="utf-8")
                == f"baseline:{relative}\n",
                f"final handoff did not restore {relative} from pushed HEAD",
            )
        comments = backend.get_comments(final["coordination"]["issue_number"])
        require(any("Steps for Vincent" in item["body"] for item in comments), "human checklist missing")

        head_commit = state["head_commit"]

        def expect_handoff_rejection(label: str) -> None:
            try:
                workflow._verify_pushed_handoff(state["branch"], head_commit)
            except TaskReviewContractError as exc:
                require("completely clean" in str(exc), f"{label} had wrong failure: {exc}")
            else:
                raise AssertionError(f"{label} was auto-recovered")

        workflow._verify_pushed_handoff(state["branch"], head_commit)

        unsafe_path = checkout / IMPLEMENTATION
        unsafe_value = "unsafe tracked handoff change\n"
        unsafe_path.write_text(unsafe_value, encoding="utf-8", newline="\n")
        expect_handoff_rejection("unknown tracked path")
        require(unsafe_path.read_text(encoding="utf-8") == unsafe_value, "unknown dirt was changed")
        git(checkout, "restore", f"--source={head_commit}", "--worktree", "--", IMPLEMENTATION)

        staged_value = "staged safe-path handoff change\n"
        (checkout / EDITOR_BUILD_SETTINGS).write_text(
            staged_value, encoding="utf-8", newline="\n"
        )
        git(checkout, "add", "--", EDITOR_BUILD_SETTINGS)
        expect_handoff_rejection("staged safe path")
        require(
            (checkout / EDITOR_BUILD_SETTINGS).read_text(encoding="utf-8") == staged_value,
            "staged safe-path dirt was changed",
        )
        require(
            git(checkout, "diff", "--cached", "--name-only", "--")
            == EDITOR_BUILD_SETTINGS,
            "staged safe-path dirt was unstaged",
        )
        git(
            checkout,
            "restore",
            f"--source={head_commit}",
            "--staged",
            "--worktree",
            "--",
            EDITOR_BUILD_SETTINGS,
        )

        untracked_relative = EDITOR_BUILD_SETTINGS + ".tmp"
        untracked_path = checkout / untracked_relative
        untracked_path.write_text("safe-looking untracked path\n", encoding="utf-8", newline="\n")
        expect_handoff_rejection("untracked safe-looking path")
        require(untracked_path.is_file(), "untracked safe-looking path was deleted")
        untracked_path.unlink()

        safe_value = "mixed safe change\n"
        mixed_unsafe_value = "mixed unsafe change\n"
        (checkout / COVERAGE_SETTINGS).write_text(safe_value, encoding="utf-8", newline="\n")
        unsafe_path.write_text(mixed_unsafe_value, encoding="utf-8", newline="\n")
        expect_handoff_rejection("mixed safe and unsafe paths")
        require(
            (checkout / COVERAGE_SETTINGS).read_text(encoding="utf-8") == safe_value,
            "safe half of mixed dirt was changed",
        )
        require(
            unsafe_path.read_text(encoding="utf-8") == mixed_unsafe_value,
            "unsafe half of mixed dirt was changed",
        )
        git(
            checkout,
            "restore",
            f"--source={head_commit}",
            "--worktree",
            "--",
            COVERAGE_SETTINGS,
            IMPLEMENTATION,
        )

        renamed_relative = COVERAGE_SETTINGS + ".renamed"
        git(checkout, "mv", "--", COVERAGE_SETTINGS, renamed_relative)
        expect_handoff_rejection("renamed safe path")
        require((checkout / renamed_relative).is_file(), "renamed safe path was changed")
        require(not (checkout / COVERAGE_SETTINGS).exists(), "renamed source was restored")
        require(
            classify_safe_post_unity_churn(
                f"R  {COVERAGE_SETTINGS} -> {renamed_relative}\n"
            )
            is None,
            "rename status was classified as safe",
        )
        require(
            classify_safe_post_unity_churn(
                f"C  {COVERAGE_SETTINGS} -> {renamed_relative}\n"
            )
            is None,
            "copy status was classified as safe",
        )
        require(
            classify_safe_post_unity_churn(" M\n") is None,
            "malformed porcelain was classified as safe",
        )


def main() -> int:
    test_controller_reaches_human_issue_handoff()
    print("PASS test_controller_reaches_human_issue_handoff")
    print("TaskReviewAgent production controller smoke tests: PASS (1 test)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
