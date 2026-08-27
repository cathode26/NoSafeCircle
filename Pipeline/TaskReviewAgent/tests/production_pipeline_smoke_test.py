#!/usr/bin/env python3
"""Deterministic end-to-end test from scope approval to pushed candidate commit."""

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

from Pipeline.TaskReviewAgent.candidate_integration import CandidateIntegrator  # noqa: E402
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge  # noqa: E402
from Pipeline.TaskReviewAgent.pipeline_scope import RepositoryScopeAuthority  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan  # noqa: E402


TASK_ID = "NSC-777"
BRANCH = "nsc-777-synthetic-pipeline-task"
LEASE_ID = "7" * 64
IMPLEMENTATION = "Assets/NoSafeCircle/Synthetic/Scripts/Feature.cs"
NEW_TEST = "Assets/NoSafeCircle/Synthetic/Tests/FeaturePlayModeTests.cs"
NEW_META = NEW_TEST + ".meta"


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


def create_fixture(root: Path) -> tuple[Path, Path, dict, str]:
    remote = root / "remote.git"
    seed = root / "seed"
    checkout = root / "operator" / TASK_ID
    run("git", "init", "--bare", str(remote), cwd=root)
    run("git", "init", "-b", "main", str(seed), cwd=root)
    git(seed, "config", "user.name", "Pipeline Smoke")
    git(seed, "config", "user.email", "pipeline@example.invalid")

    (seed / "Assets/NoSafeCircle/Synthetic/Scripts").mkdir(parents=True)
    (seed / "Assets/NoSafeCircle/Synthetic/Tests").mkdir(parents=True)
    (seed / "Pipeline/TaskGraph").mkdir(parents=True)
    (seed / "Tasks").mkdir(parents=True)
    (seed / "Pipeline/ExecutionCrew/outputs").mkdir(parents=True)
    (seed / IMPLEMENTATION).write_text(
        "namespace Synthetic { public static class Feature { public const int Value = 1; } }\n",
        encoding="utf-8",
        newline="\n",
    )
    (seed / "Assets/NoSafeCircle/Synthetic/Tests/.keep").write_text(
        "tracked parent\n", encoding="utf-8", newline="\n"
    )
    (seed / "Pipeline/TaskGraph/taskcontrol.py").write_text(
        taskcontrol_source(), encoding="utf-8", newline="\n"
    )
    (seed / ".gitignore").write_text(
        "Pipeline/ExecutionCrew/outputs/\n", encoding="utf-8", newline="\n"
    )
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
        "exclusive_resources": [f"repo-file:{IMPLEMENTATION}"],
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
    contract_bytes = git(checkout, "show", f"HEAD:Tasks/{TASK_ID}.yaml").encode("utf-8")
    task = {
        **contract,
        "task_id": TASK_ID,
        "contract_path": f"Tasks/{TASK_ID}.yaml",
        "task_contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
    }
    return checkout, remote, task, git(checkout, "rev-parse", "HEAD")


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


def test_scope_execution_commit_push() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-production-pipeline-") as temporary:
        root = Path(temporary)
        checkout, remote, task, source_head = create_fixture(root)
        scope = RepositoryScopeAuthority(
            checkout=checkout,
            task=task,
            lease_id=LEASE_ID,
            expected_branch=BRANCH,
        )
        facts = scope.facts()
        require(IMPLEMENTATION in facts["existing_resource_paths"], "resource fact missing")
        require(scope.search(query="Value", prefixes=["Assets/"])["count"] == 1, "search failed")
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

        integrator = CandidateIntegrator(
            checkout=checkout,
            branch=BRANCH,
            task_title=task["title"],
            scope=scope,
            execution=bridge,
        )
        integrated = integrator.integrate(run_id)
        require(git(checkout, "rev-parse", "HEAD") == integrated.commit, "commit not checked out")
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
            integrator.integrate(run_id).commit == integrated.commit,
            "integration was not idempotent",
        )


def main() -> int:
    test_scope_execution_commit_push()
    print("PASS test_scope_execution_commit_push")
    print("TaskReviewAgent production pipeline smoke tests: PASS (1 test)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
