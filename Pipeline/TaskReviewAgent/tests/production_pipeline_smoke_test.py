#!/usr/bin/env python3
"""Deterministic end-to-end test from scope approval to pushed candidate commit."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.candidate_integration import (  # noqa: E402
    CandidateIntegrationError,
    CandidateIntegrator,
)
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge  # noqa: E402
from Pipeline.TaskReviewAgent.pipeline_scope import RepositoryScopeAuthority  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan  # noqa: E402


TASK_ID = "NSC-777"
BRANCH = "nsc-777-synthetic-pipeline-task"
LEASE_ID = "7" * 64
IMPLEMENTATION = "Assets/NoSafeCircle/Synthetic/Scripts/Feature.cs"
NEW_TEST = "Assets/NoSafeCircle/Synthetic/Tests/FeaturePlayModeTests.cs"
NEW_META = NEW_TEST + ".meta"
DOOR_BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs"
DOOR_TEST = (
    "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPrototypeSceneBuilderTests.cs"
)
DOOR_STATE = "Assets/NoSafeCircle/DoorPrototype/Support/BuilderState.asset"
DOOR_PREFAB = "Assets/NoSafeCircle/DoorPrototype/Future/GeneratedDoor.prefab"
DOOR_PREFAB_META = DOOR_PREFAB + ".meta"
DOOR_SCENE = "Assets/Scenes/DoorPrototype.unity"
EDITOR_BUILD_SETTINGS = "ProjectSettings/EditorBuildSettings.asset"
COVERAGE_SETTINGS = (
    "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json"
)
DOOR_BUILD_METHOD = "NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build"
UNITY_VERSION = "6000.0.55f1"


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
        raise AssertionError(
            f"binary git command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )
    return result.stdout


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def taskcontrol_source() -> str:
    return """from __future__ import annotations
import sys
if sys.argv[1:] == ["validate"]:
    print("taskcontrol validate: PASS")
    raise SystemExit(0)
raise SystemExit(2)
"""


def create_fixture(
    root: Path,
    *,
    implementation: str = IMPLEMENTATION,
    authoritative_validation: bool = False,
) -> tuple[Path, Path, dict, str]:
    remote = root / "remote.git"
    seed = root / "seed"
    checkout = root / "operator" / TASK_ID
    run("git", "init", "--bare", str(remote), cwd=root)
    run("git", "init", "-b", "main", str(seed), cwd=root)
    git(seed, "config", "user.name", "Pipeline Smoke")
    git(seed, "config", "user.email", "pipeline@example.invalid")

    (seed / "Assets/NoSafeCircle/Synthetic/Scripts").mkdir(parents=True)
    (seed / "Assets/NoSafeCircle/Synthetic/Tests").mkdir(parents=True)
    (seed / "Assets/NoSafeCircle/DoorPrototype/Editor").mkdir(parents=True)
    (seed / "Assets/NoSafeCircle/DoorPrototype/Support").mkdir(parents=True)
    (seed / "Assets/NoSafeCircle/DoorPrototype/Tests/Editor").mkdir(parents=True)
    (seed / "Assets/Scenes").mkdir(parents=True)
    (seed / "Pipeline/TaskGraph").mkdir(parents=True)
    (seed / "Tasks").mkdir(parents=True)
    (seed / "Pipeline/ExecutionCrew/outputs").mkdir(parents=True)
    (seed / "ProjectSettings/Packages/com.unity.testtools.codecoverage").mkdir(
        parents=True
    )
    (seed / IMPLEMENTATION).write_text(
        "namespace Synthetic { public static class Feature { public const int Value = 1; } }\n",
        encoding="utf-8",
        newline="\n",
    )
    (seed / "Assets/NoSafeCircle/Synthetic/Tests/.keep").write_text(
        "tracked parent\n", encoding="utf-8", newline="\n"
    )
    (seed / DOOR_BUILDER).write_text(
        "namespace DoorPrototype { public static class Builder { public const int Revision = 1; } }\n",
        encoding="utf-8",
        newline="\n",
    )
    (seed / DOOR_TEST).write_text(
        "namespace DoorPrototype.Tests { public sealed class BuilderTests { public const int Revision = 1; } }\n",
        encoding="utf-8",
        newline="\n",
    )
    (seed / DOOR_STATE).write_text(
        "builder-state: original\n", encoding="utf-8", newline="\n"
    )
    (seed / DOOR_SCENE).write_text(
        "door-scene: original\n", encoding="utf-8", newline="\n"
    )
    (seed / "ProjectSettings/ProjectVersion.txt").write_text(
        f"m_EditorVersion: {UNITY_VERSION}\n", encoding="utf-8", newline="\n"
    )
    (seed / EDITOR_BUILD_SETTINGS).write_text(
        "editor-build-settings: original\n", encoding="utf-8", newline="\n"
    )
    (seed / COVERAGE_SETTINGS).write_text(
        '{"enabled": false}\n', encoding="utf-8", newline="\n"
    )
    (seed / "Pipeline/TaskGraph/taskcontrol.py").write_text(
        taskcontrol_source(), encoding="utf-8", newline="\n"
    )
    (seed / ".gitignore").write_text(
        "Pipeline/ExecutionCrew/outputs/\n", encoding="utf-8", newline="\n"
    )
    exclusive_resources = [f"repo-file:{implementation}"]
    if implementation == DOOR_BUILDER:
        exclusive_resources.append(f"repo-file:{DOOR_TEST}")
    contract = {
        "schema_version": "2.0",
        "id": TASK_ID,
        "title": "Synthetic Pipeline Task",
        "contract_revision": 1,
        "contract_disposition": "active",
        "kind": "implementation",
        "type": "gameplay_system",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "depends_on": [],
        "exclusive_resources": exclusive_resources,
        "acceptance_criteria": [],
        "completion_gates": [],
        "downstream_integration_obligations": [],
    }
    contract_path = seed / f"Tasks/{TASK_ID}.yaml"
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    git(seed, "add", ".")
    git(seed, "commit", "-m", "Create synthetic production pipeline fixture")
    if authoritative_validation:
        contract_hash = hashlib.sha256(
            git_bytes(seed, "show", f"HEAD:Tasks/{TASK_ID}.yaml")
        ).hexdigest()
        (seed / "Pipeline/TaskReviewAgent").mkdir(parents=True, exist_ok=True)
        (seed / "Pipeline/Testing").mkdir(parents=True, exist_ok=True)
        policy = {
            "schema_version": "1.0",
            "tasks": {
                TASK_ID: {
                    "task_contract_sha256": contract_hash,
                    "required_test_platforms": ["EditMode"],
                    "test_filters": {
                        "EditMode": "Synthetic.Tests.FeatureEditModeTests"
                    },
                    "authority": "synthetic_pre_handoff_validation",
                }
            },
        }
        (seed / "Pipeline/TaskReviewAgent/authoritative_validation_policy.json").write_text(
            json.dumps(policy, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        (seed / "Pipeline/Testing/run_unity_tests_clean.ps1").write_text(
            "# synthetic clean Unity runner contract\n",
            encoding="utf-8",
            newline="\n",
        )
        git(seed, "add", "Pipeline")
        git(seed, "commit", "-m", "Add authoritative validation policy")
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
    checkout.parent.mkdir(parents=True)
    run("git", "clone", str(remote), str(checkout), cwd=root)
    git(checkout, "switch", "-c", BRANCH)
    contract_bytes = git_bytes(checkout, "show", f"HEAD:Tasks/{TASK_ID}.yaml")
    task = {
        **contract,
        "task_id": TASK_ID,
        "contract_path": f"Tasks/{TASK_ID}.yaml",
        "task_contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
    }
    return checkout, remote, task, git(checkout, "rev-parse", "HEAD")


def write_validation_manifest(
    directory: Path,
    *,
    commit: str,
    tree: str,
    platform: str,
    test_filter: str,
) -> Path:
    directory.mkdir(parents=True)
    xml = (
        '<test-run result="Passed" total="1" passed="1" failed="0" skipped="0">'
        "</test-run>\n"
    ).encode("utf-8")
    log = b"Synthetic Unity validation passed.\n"
    (directory / "test-results.xml").write_bytes(xml)
    (directory / "unity.log").write_bytes(log)
    manifest = {
        "schema_version": "1.0",
        "manifest_type": "unity_test_validation",
        "status": "passed",
        "validated_state": {
            "commit": commit,
            "tree": tree,
            "post_commit": commit,
            "post_tree": tree,
            "repository_clean_before": True,
            "repository_clean_after": True,
        },
        "unity": {
            "version": UNITY_VERSION,
            "executable": "synthetic-unity.exe",
            "exit_code": 0,
            "test_platform": platform,
            "test_filter": test_filter,
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
        "runner": {"path": "Pipeline/Testing/run_unity_tests_clean.ps1"},
    }
    path = directory / "validation-manifest.json"
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


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
+guid: 0123456789abcdef0123456789abcdef
""".encode("utf-8")


def builder_candidate_patch() -> bytes:
    return f"""diff --git a/{DOOR_BUILDER} b/{DOOR_BUILDER}
--- a/{DOOR_BUILDER}
+++ b/{DOOR_BUILDER}
@@ -1 +1 @@
-namespace DoorPrototype {{ public static class Builder {{ public const int Revision = 1; }} }}
+namespace DoorPrototype {{ public static class Builder {{ public const int Revision = 2; }} }}
diff --git a/{DOOR_TEST} b/{DOOR_TEST}
--- a/{DOOR_TEST}
+++ b/{DOOR_TEST}
@@ -1 +1 @@
-namespace DoorPrototype.Tests {{ public sealed class BuilderTests {{ public const int Revision = 1; }} }}
+namespace DoorPrototype.Tests {{ public sealed class BuilderTests {{ public const int Revision = 2; }} }}
""".encode("utf-8")


def prepare_builder_execution(
    root: Path,
    *,
    run_id: str,
) -> tuple[Path, Path, dict, str, RepositoryScopeAuthority, ExecutionCrewBridge]:
    checkout, remote, task, source_head = create_fixture(
        root,
        implementation=DOOR_BUILDER,
    )
    scope = RepositoryScopeAuthority(
        checkout=checkout,
        task=task,
        lease_id=LEASE_ID,
        expected_branch=BRANCH,
    )
    accepted = scope.validate(ExecutionScopePlan((DOOR_BUILDER,), (), (DOOR_TEST,), ()))
    require(accepted.accepted and accepted.plan_id, "builder scope was rejected")
    patch = builder_candidate_patch()

    def fake_execution_runner(args, cwd, timeout):
        _ = (cwd, timeout)
        require("--implementation-path" in args, "builder implementation flag missing")
        output = checkout / "Pipeline/ExecutionCrew/outputs" / run_id
        output.mkdir(parents=True, exist_ok=True)
        (output / "candidate.patch").write_bytes(patch)
        result = {
            "schema_version": "1.0",
            "run_id": run_id,
            "task_id": TASK_ID,
            "task_contract_identity": {
                "path": f"Tasks/{TASK_ID}.yaml",
                "revision": 1,
                "sha256": task["task_contract_sha256"],
            },
            "source_head": source_head,
            "source_tree": git(checkout, "rev-parse", "HEAD^{tree}"),
            "source_branch": BRANCH,
            "provider": "claude",
            "crew_status": "review_ready",
            "requested_implementation_paths": [DOOR_BUILDER],
            "requested_test_paths": [DOOR_TEST],
            "requested_existing_implementation_paths": [DOOR_BUILDER],
            "requested_new_implementation_paths": [],
            "requested_existing_test_paths": [DOOR_TEST],
            "requested_new_test_paths": [],
            "pipeline_generated_paths": [],
            "implementation_actual_changed_paths": [DOOR_BUILDER],
            "test_actual_changed_paths": [DOOR_TEST],
            "final_actual_changed_paths": sorted([DOOR_BUILDER, DOOR_TEST]),
            "role_results": [],
            "candidate_patch_path": f"/execution-output/{run_id}/candidate.patch",
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
            "human_next_step": "Review candidate.patch",
            "human_result": {"status": "REVIEW_READY"},
            "attempts_used": 1,
            "duration_seconds": 1.0,
        }
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        (output / "crew_result.json").write_text(
            payload,
            encoding="utf-8",
            newline="\n",
        )
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=payload.encode(),
            stderr=b"",
        )

    bridge = ExecutionCrewBridge(
        checkout=checkout,
        scope=scope,
        command_runner=fake_execution_runner,
    )
    crew = bridge.run(plan_id=accepted.plan_id, provider="claude")
    require(crew.crew_status == "review_ready", "builder crew did not reach review_ready")
    return checkout, remote, task, source_head, scope, bridge


def fake_unity_executable(root: Path) -> Path:
    executable = (
        root
        / "Program Files"
        / "Unity"
        / "Hub"
        / "Editor"
        / UNITY_VERSION
        / "Editor"
        / "Unity.exe"
    )
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fake Unity executable\n")
    return executable


def assert_builder_command(
    args,
    *,
    checkout: Path,
    executable: Path,
) -> None:
    require(Path(args[0]).resolve() == executable.resolve(), "wrong Unity executable")
    require(
        tuple(args[1:-1])
        == (
            "-batchmode",
            "-quit",
            "-projectPath",
            str(checkout.resolve()),
            "-executeMethod",
            DOOR_BUILD_METHOD,
            "-logFile",
        ),
        f"wrong DoorPrototype builder command: {args}",
    )
    log_path = Path(args[-1])
    require(checkout not in log_path.parents, "Unity log was placed inside the checkout")


def test_scope_execution_commit_push() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-production-pipeline-") as temporary:
        root = Path(temporary)
        checkout, remote, task, source_head = create_fixture(
            root,
            authoritative_validation=True,
        )
        scope = RepositoryScopeAuthority(
            checkout=checkout,
            task=task,
            lease_id=LEASE_ID,
            expected_branch=BRANCH,
        )
        facts = scope.facts()
        require(IMPLEMENTATION in facts["existing_resource_paths"], "resource fact missing")
        require(
            IMPLEMENTATION in scope.list_files(prefix=".")["paths"],
            "approved-root file listing omitted the implementation",
        )
        require(
            IMPLEMENTATION in scope.list_files(prefix="Assets/")["paths"],
            "normal approved-prefix file listing regressed",
        )
        require(scope.search(query="Value", prefixes=["Assets/"])["count"] == 1, "search failed")
        require(
            scope.search(query="Value", prefixes=["."])["count"] == 1,
            "approved-root search failed",
        )
        require("Value = 1" in scope.read_file(path=IMPLEMENTATION)["content"], "read failed")

        wrong = ExecutionScopePlan(
            (IMPLEMENTATION,),
            (),
            (NEW_TEST,),
            (),
        )
        rejected = scope.validate(wrong)
        require(not rejected.accepted, "absent test was accepted as existing")

        plan = ExecutionScopePlan(
            (IMPLEMENTATION,),
            (),
            (),
            (NEW_TEST,),
        )
        accepted = scope.validate(plan)
        require(accepted.accepted and accepted.plan_id, "valid scope was rejected")

        patch = candidate_patch()
        run_id = "nsc-777-pipeline-smoke"

        def fake_runner(args, cwd, timeout):
            _ = (cwd, timeout)
            require("claude-exec" in args, "wrong ExecutionCrew service")
            require("--implementation-path" in args, "existing implementation flag missing")
            require("--new-test-path" in args, "new test flag missing")
            output = checkout / "Pipeline/ExecutionCrew/outputs" / run_id
            output.mkdir(parents=True, exist_ok=True)
            (output / "candidate.patch").write_bytes(patch)
            result = {
                "schema_version": "1.0",
                "run_id": run_id,
                "task_id": TASK_ID,
                "task_contract_identity": {
                    "path": f"Tasks/{TASK_ID}.yaml",
                    "revision": 1,
                    "sha256": task["task_contract_sha256"],
                },
                "source_head": source_head,
                "source_tree": git(checkout, "rev-parse", "HEAD^{tree}"),
                "source_branch": BRANCH,
                "provider": "claude",
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
                "candidate_patch_path": f"/execution-output/{run_id}/candidate.patch",
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
                "human_next_step": "Review candidate.patch",
                "human_result": {"status": "REVIEW_READY"},
                "attempts_used": 1,
                "duration_seconds": 1.0,
            }
            payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
            (output / "crew_result.json").write_text(payload, encoding="utf-8", newline="\n")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=payload.encode(), stderr=b"")

        bridge = ExecutionCrewBridge(
            checkout=checkout,
            scope=scope,
            command_runner=fake_runner,
        )
        crew = bridge.run(plan_id=accepted.plan_id, provider="claude")
        require(crew.crew_status == "review_ready", "fake crew did not reach review_ready")

        main_writer = root / "main-writer"
        run("git", "clone", str(remote), str(main_writer), cwd=root)
        git(main_writer, "config", "user.name", "Pipeline Smoke")
        git(main_writer, "config", "user.email", "pipeline@example.invalid")
        (main_writer / "later-main.txt").write_text(
            "main advanced while the candidate was being prepared\n",
            encoding="utf-8",
            newline="\n",
        )
        git(main_writer, "add", "later-main.txt")
        git(main_writer, "commit", "-m", "Advance main during candidate preparation")
        git(main_writer, "push", "origin", "main")
        current_main = git(main_writer, "rev-parse", "HEAD")

        unity_calls: list[tuple[str, ...]] = []

        def pre_handoff_unity_runner(args, cwd, timeout):
            _ = timeout
            require(cwd.resolve() == checkout.resolve(), "Unity ran in the wrong checkout")
            require(args[0].casefold().endswith("powershell.exe"), "wrong Unity runner shell")
            require(args[args.index("-TestPlatform") + 1] == "EditMode", "wrong platform")
            test_filter = args[args.index("-TestFilter") + 1]
            require(
                test_filter == "Synthetic.Tests.FeatureEditModeTests",
                "wrong authoritative test filter",
            )
            candidate_commit = git(checkout, "rev-parse", "HEAD")
            require(
                git(checkout, "rev-parse", "HEAD^") == current_main,
                "authoritative validation ran before current main was integrated",
            )
            require(
                git(checkout, "status", "--porcelain=v1", "--untracked-files=all") == "",
                "authoritative validation did not receive a clean committed candidate",
            )
            require(
                git(checkout, "ls-remote", "--heads", "origin", f"refs/heads/{BRANCH}") == "",
                "candidate was pushed before authoritative validation",
            )
            unity_calls.append(tuple(args))
            if len(unity_calls) == 1:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=23,
                    stdout=b"Synthetic first validation failed.\n",
                    stderr=b"",
                )
            manifest = write_validation_manifest(
                root / "unity-validation",
                commit=candidate_commit,
                tree=git(checkout, "rev-parse", "HEAD^{tree}"),
                platform="EditMode",
                test_filter=test_filter,
            )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"Validation manifest: {manifest}\n".encode(),
                stderr=b"",
            )

        integrator = CandidateIntegrator(
            checkout=checkout,
            branch=BRANCH,
            task_title=task["title"],
            scope=scope,
            execution=bridge,
            unity_command_runner=pre_handoff_unity_runner,
        )
        try:
            integrator.integrate(run_id)
        except CandidateIntegrationError as exc:
            require(
                "pre-handoff EditMode Unity test failed (23)" in str(exc),
                f"wrong pre-handoff validation failure: {exc}",
            )
        else:
            raise AssertionError("failed pre-handoff validation was accepted")
        require(
            git(checkout, "rev-parse", "HEAD^") == current_main,
            "failed validation lost the current-main-based local commit",
        )
        require(
            git(checkout, "ls-remote", "--heads", "origin", f"refs/heads/{BRANCH}") == "",
            "failed validation pushed a human handoff branch",
        )

        integrated = integrator.integrate(run_id)
        require(git(checkout, "rev-parse", "HEAD") == integrated.commit, "commit not checked out")
        require(integrated.base_head == current_main, "candidate did not use current main as its base")
        require(
            git(checkout, "rev-parse", "HEAD^") == current_main,
            "task commit parent is not the pre-handoff main head",
        )
        require(
            git(checkout, "show", f"{integrated.commit}:later-main.txt")
            == "main advanced while the candidate was being prepared",
            "task commit omitted the latest main content",
        )
        require(git(checkout, "status", "--porcelain=v1", "--untracked-files=all") == "", "checkout dirty")
        remote_head = run(
            "git",
            "--git-dir",
            str(remote),
            "rev-parse",
            f"refs/heads/{BRANCH}",
            cwd=root,
        ).stdout.strip()
        require(remote_head == integrated.commit, "task branch was not pushed")
        require(
            git(checkout, "show", f"{integrated.commit}:{IMPLEMENTATION}").find("Value = 2") >= 0,
            "implementation change missing from commit",
        )
        require(
            integrated.changed_paths == tuple(sorted([IMPLEMENTATION, NEW_TEST, NEW_META])),
            "normal candidate receipt path set changed",
        )
        require(len(unity_calls) == 2, "authoritative validation retry count changed")
        require(
            len(integrated.pre_handoff_validations) == 1,
            "authoritative validation evidence was not bound to the integration receipt",
        )
        require(
            integrated.pre_handoff_validations[0]["commit"] == integrated.commit,
            "validation evidence was not bound to the exact candidate commit",
        )
        require(
            integrator.integrate(run_id).commit == integrated.commit,
            "integration was not idempotent",
        )


def write_builder_owned_outputs(checkout: Path) -> tuple[str, ...]:
    (checkout / DOOR_STATE).write_text(
        "builder-state: regenerated\n", encoding="utf-8", newline="\n"
    )
    (checkout / DOOR_SCENE).write_text(
        "door-scene: regenerated   \nnext: value\t\n",
        encoding="utf-8",
        newline="\n",
    )
    (checkout / DOOR_PREFAB).parent.mkdir(parents=True, exist_ok=True)
    (checkout / DOOR_PREFAB).write_text(
        "future generated prefab\n", encoding="utf-8", newline="\n"
    )
    (checkout / DOOR_PREFAB_META).write_text(
        "fileFormatVersion: 2\nguid: fedcba9876543210fedcba9876543210\n",
        encoding="utf-8",
        newline="\n",
    )
    return tuple(
        sorted(
            (
                DOOR_BUILDER,
                DOOR_TEST,
                DOOR_STATE,
                DOOR_PREFAB,
                DOOR_PREFAB_META,
                DOOR_SCENE,
            ),
            key=str.casefold,
        )
    )


def test_door_builder_outputs_and_incidental_cleanup() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-door-builder-pipeline-") as temporary:
        root = Path(temporary)
        run_id = "nsc-777-door-builder-success"
        checkout, remote, task, source_head, scope, bridge = prepare_builder_execution(
            root,
            run_id=run_id,
        )
        executable = fake_unity_executable(root)
        events: list[str] = []

        def fake_unity_runner(args, cwd, timeout):
            _ = timeout
            require(cwd.resolve() == checkout.resolve(), "Unity did not run in the canonical checkout")
            assert_builder_command(args, checkout=checkout, executable=executable)
            require(
                tuple(
                    sorted(
                        git(checkout, "diff", "--name-only", "--").splitlines(),
                        key=str.casefold,
                    )
                )
                == tuple(sorted((DOOR_BUILDER, DOOR_TEST), key=str.casefold)),
                "Unity ran before the candidate path set was applied and verified",
            )
            events.append("builder")
            write_builder_owned_outputs(checkout)
            (checkout / EDITOR_BUILD_SETTINGS).write_text(
                "editor-build-settings: incidental Unity churn\n",
                encoding="utf-8",
                newline="\n",
            )
            (checkout / COVERAGE_SETTINGS).write_text(
                '{"enabled": true}\n', encoding="utf-8", newline="\n"
            )
            git(checkout, "add", "--", COVERAGE_SETTINGS)
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=b"builder complete\n",
                stderr=b"",
            )

        integrator = CandidateIntegrator(
            checkout=checkout,
            branch=BRANCH,
            task_title=task["title"],
            scope=scope,
            execution=bridge,
            unity_command_runner=fake_unity_runner,
        )
        original_verify = integrator._verify_applied_state

        def recording_verify(verify_root, execution, *, expected_paths=None):
            original_verify(
                verify_root,
                execution,
                expected_paths=expected_paths,
            )
            if verify_root.resolve() == checkout.resolve():
                events.append("verify")

        integrator._verify_applied_state = recording_verify
        previous_program_files = os.environ.get("ProgramFiles")
        os.environ["ProgramFiles"] = str(root / "Program Files")
        try:
            integrated = integrator.integrate(run_id)
        finally:
            if previous_program_files is None:
                os.environ.pop("ProgramFiles", None)
            else:
                os.environ["ProgramFiles"] = previous_program_files

        expected = tuple(
            sorted(
                (
                    DOOR_BUILDER,
                    DOOR_TEST,
                    DOOR_STATE,
                    DOOR_PREFAB,
                    DOOR_PREFAB_META,
                    DOOR_SCENE,
                ),
                key=str.casefold,
            )
        )
        committed = tuple(
            sorted(
                git(checkout, "diff", "--name-only", f"{source_head}..HEAD", "--").splitlines(),
                key=str.casefold,
            )
        )
        require(events == ["verify", "builder", "verify"], f"wrong integration order: {events}")
        require(committed == expected, f"wrong builder commit path set: {committed}")
        require(integrated.changed_paths == committed, "receipt does not match committed paths")
        require(EDITOR_BUILD_SETTINGS not in committed, "EditorBuildSettings was committed")
        require(COVERAGE_SETTINGS not in committed, "coverage settings were committed")
        require(
            git(checkout, "show", f"HEAD:{DOOR_SCENE}")
            == "door-scene: regenerated\nnext: value",
            "builder scene trailing whitespace was committed",
        )
        require(
            git(checkout, "diff", "--check", f"{source_head}..HEAD", "--") == "",
            "builder commit failed git diff --check",
        )
        require(
            git(checkout, "show", f"HEAD:{EDITOR_BUILD_SETTINGS}")
            == "editor-build-settings: original",
            "EditorBuildSettings incidental change was not restored",
        )
        require(
            git(checkout, "show", f"HEAD:{COVERAGE_SETTINGS}") == '{"enabled": false}',
            "coverage settings incidental change was not restored",
        )
        require(
            git(checkout, "status", "--porcelain=v1", "--untracked-files=all") == "",
            "successful builder integration left the checkout dirty",
        )
        remote_head = run(
            "git",
            "--git-dir",
            str(remote),
            "rev-parse",
            f"refs/heads/{BRANCH}",
            cwd=root,
        ).stdout.strip()
        require(remote_head == integrated.commit, "builder integration was not pushed")


def test_door_builder_untracked_incidental_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-door-builder-untracked-") as temporary:
        root = Path(temporary)
        run_id = "nsc-777-door-builder-untracked"
        checkout, _, task, source_head, scope, bridge = prepare_builder_execution(
            root,
            run_id=run_id,
        )
        executable = fake_unity_executable(root)
        incidental_path = checkout / "UnityIncidental.tmp"

        def fake_unity_runner(args, cwd, timeout):
            _ = (cwd, timeout)
            assert_builder_command(args, checkout=checkout, executable=executable)
            incidental_path.write_text("untracked Unity churn\n", encoding="utf-8", newline="\n")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

        integrator = CandidateIntegrator(
            checkout=checkout,
            branch=BRANCH,
            task_title=task["title"],
            scope=scope,
            execution=bridge,
            unity_command_runner=fake_unity_runner,
            unity_executable=executable,
        )
        try:
            integrator.integrate(run_id)
        except CandidateIntegrationError as exc:
            require("untracked paths outside" in str(exc), f"wrong failure: {exc}")
        else:
            raise AssertionError("incidental untracked Unity path was accepted")
        require(git(checkout, "rev-parse", "HEAD") == source_head, "failure created a commit")
        require(incidental_path.is_file(), "incidental untracked path was deleted")
        require(
            git(checkout, "ls-remote", "--heads", "origin", f"refs/heads/{BRANCH}") == "",
            "failure pushed the task branch",
        )


def test_door_builder_nonzero_prevents_commit_and_push() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-door-builder-nonzero-") as temporary:
        root = Path(temporary)
        run_id = "nsc-777-door-builder-nonzero"
        checkout, _, task, source_head, scope, bridge = prepare_builder_execution(
            root,
            run_id=run_id,
        )
        executable = fake_unity_executable(root)

        def fake_unity_runner(args, cwd, timeout):
            _ = (cwd, timeout)
            assert_builder_command(args, checkout=checkout, executable=executable)
            return subprocess.CompletedProcess(
                args=args,
                returncode=17,
                stdout=b"",
                stderr=b"synthetic builder failure\n",
            )

        integrator = CandidateIntegrator(
            checkout=checkout,
            branch=BRANCH,
            task_title=task["title"],
            scope=scope,
            execution=bridge,
            unity_command_runner=fake_unity_runner,
            unity_executable=executable,
        )
        try:
            integrator.integrate(run_id)
        except CandidateIntegrationError as exc:
            require("builder failed (17)" in str(exc), f"wrong failure: {exc}")
        else:
            raise AssertionError("nonzero Unity exit was accepted")
        require(git(checkout, "rev-parse", "HEAD") == source_head, "failure created a commit")
        require(
            git(checkout, "ls-remote", "--heads", "origin", f"refs/heads/{BRANCH}") == "",
            "failure pushed the task branch",
        )


def create_existing_builder_commit(
    checkout: Path,
    bridge: ExecutionCrewBridge,
    *,
    run_id: str,
    include_unrelated: bool,
) -> tuple[str, ...]:
    execution = bridge.require(run_id)
    git(checkout, "apply", "--", str(execution.candidate_path))
    expected = write_builder_owned_outputs(checkout)
    paths = list(expected)
    if include_unrelated:
        (checkout / EDITOR_BUILD_SETTINGS).write_text(
            "editor-build-settings: unauthorized extra\n",
            encoding="utf-8",
            newline="\n",
        )
        paths.append(EDITOR_BUILD_SETTINGS)
    git(checkout, "add", "--", *paths)
    git(checkout, "config", "user.name", "Pipeline Smoke")
    git(checkout, "config", "user.email", "pipeline@example.invalid")
    git(
        checkout,
        "commit",
        "-m",
        "Create resumable synthetic integration",
        "-m",
        f"ExecutionCrew-Run: {run_id}",
    )
    return tuple(sorted(paths, key=str.casefold))


def test_builder_existing_commit_resume_boundary() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-door-builder-resume-") as temporary:
        root = Path(temporary)
        accepted_root = root / "accepted"
        accepted_root.mkdir()
        accepted_run = "nsc-777-door-builder-resume-accepted"
        checkout, remote, task, _, scope, bridge = prepare_builder_execution(
            accepted_root,
            run_id=accepted_run,
        )
        expected = create_existing_builder_commit(
            checkout,
            bridge,
            run_id=accepted_run,
            include_unrelated=False,
        )

        def forbidden_unity_runner(args, cwd, timeout):
            _ = (args, cwd, timeout)
            raise AssertionError("resume unexpectedly reran Unity")

        integrator = CandidateIntegrator(
            checkout=checkout,
            branch=BRANCH,
            task_title=task["title"],
            scope=scope,
            execution=bridge,
            unity_command_runner=forbidden_unity_runner,
        )
        integrated = integrator.integrate(accepted_run)
        require(integrated.changed_paths == expected, "resume receipt omitted builder output")
        require(
            run(
                "git",
                "--git-dir",
                str(remote),
                "rev-parse",
                f"refs/heads/{BRANCH}",
                cwd=accepted_root,
            ).stdout.strip()
            == integrated.commit,
            "accepted resume was not pushed",
        )

        rejected_root = root / "rejected"
        rejected_root.mkdir()
        rejected_run = "nsc-777-door-builder-resume-rejected"
        checkout, _, task, _, scope, bridge = prepare_builder_execution(
            rejected_root,
            run_id=rejected_run,
        )
        create_existing_builder_commit(
            checkout,
            bridge,
            run_id=rejected_run,
            include_unrelated=True,
        )
        integrator = CandidateIntegrator(
            checkout=checkout,
            branch=BRANCH,
            task_title=task["title"],
            scope=scope,
            execution=bridge,
            unity_command_runner=forbidden_unity_runner,
        )
        try:
            integrator.integrate(rejected_run)
        except CandidateIntegrationError as exc:
            require("wrong path set" in str(exc), f"wrong resume rejection: {exc}")
        else:
            raise AssertionError("resume accepted an unrelated ProjectSettings path")
        require(
            git(checkout, "ls-remote", "--heads", "origin", f"refs/heads/{BRANCH}") == "",
            "rejected resume pushed the task branch",
        )


def main() -> int:
    test_scope_execution_commit_push()
    print("PASS test_scope_execution_commit_push")
    test_door_builder_outputs_and_incidental_cleanup()
    print("PASS test_door_builder_outputs_and_incidental_cleanup")
    test_door_builder_untracked_incidental_fails_closed()
    print("PASS test_door_builder_untracked_incidental_fails_closed")
    test_door_builder_nonzero_prevents_commit_and_push()
    print("PASS test_door_builder_nonzero_prevents_commit_and_push")
    test_builder_existing_commit_resume_boundary()
    print("PASS test_builder_existing_commit_resume_boundary")
    print("TaskReviewAgent production pipeline smoke tests: PASS (5 tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
