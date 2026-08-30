#!/usr/bin/env python3
"""Deterministic downstream evidence, resume, and closeout smoke tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.delivery_review import (  # noqa: E402
    create_delivery_review_proposal,
    materialize_approved_review,
)
from Pipeline.TaskReviewAgent.downstream_issue import DownstreamIssueCoordinator  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
    _manifest,
)
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    DownstreamTaskReviewWorkflow,
    ResumableDownstreamIssueCoordinator,
    ResumableDownstreamTaskController,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)
from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow  # noqa: E402

TASK_ID = "NSC-777"
BRANCH = "nsc-777-downstream-smoke"
CONTRACT_HASH = "1" * 64
SOURCE_HEAD = "2" * 40
IMPLEMENTATION_HEAD = "3" * 40
EVIDENCE_HEAD = "4" * 40


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[bytes]:
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
    return run("git", "-C", str(root), *args, cwd=root, check=check).stdout.decode().strip()


def init_repo(path: Path) -> None:
    run("git", "init", "-b", "main", str(path), cwd=path.parent)
    git(path, "config", "user.name", "Downstream Smoke")
    git(path, "config", "user.email", "downstream@example.invalid")


def commit_all(path: Path, message: str) -> str:
    git(path, "add", ".")
    git(path, "commit", "-m", message)
    return git(path, "rev-parse", "HEAD")


def task() -> dict[str, Any]:
    return {
        "id": TASK_ID,
        "title": "Synthetic Downstream Task",
        "task_contract_sha256": CONTRACT_HASH,
        "exclusive_resources": [],
    }


def test_issue_lifecycle_resumes_evidence_head() -> None:
    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda _: task(),
        worker_id="worker-a",
    )
    service.acquire_agent_lease(
        task=task(),
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=f"C:/Tasks/{TASK_ID}",
        planned_approach="Implement the bounded task.",
        expected_validation="Unity runtime validation.",
        now="2026-08-27T12:00:00Z",
    )
    service.publish_human_handoff(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=IMPLEMENTATION_HEAD,
        checkout_path=f"C:/Tasks/{TASK_ID}",
        implementation_summary="Implemented the synthetic behavior.",
        completed_checks=["ExecutionCrew passed."],
        human_steps=["Validate the behavior in Unity."],
        expected_result="The behavior works.",
        now="2026-08-27T12:01:00Z",
    )
    service.apply_human_result(
        task_id=TASK_ID,
        result_body=(
            "## Human validation result\n\n"
            "Result: PASS\n"
            f"Tested commit: `{IMPLEMENTATION_HEAD}`\n"
        ),
        actor_id="cathode26",
        now="2026-08-27T12:02:00Z",
    )
    service.acquire_agent_lease(
        task=task(),
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=f"C:/Tasks/{TASK_ID}",
        planned_approach="Prepare delivery evidence.",
        expected_validation="Human delivery review.",
        now="2026-08-27T12:03:00Z",
    )
    issue = DownstreamIssueCoordinator(service)
    issue.request_delivery_review(
        task_id=TASK_ID,
        branch=BRANCH,
        head_commit=IMPLEMENTATION_HEAD,
        checkout_path=f"C:/Tasks/{TASK_ID}",
        draft_path="C:/Output/draft.json",
        draft_sha256="5" * 64,
        proposal_path="C:/Output/proposal.json",
        proposal_sha256="6" * 64,
        surface_summary=["`Assets/Feature.cs` — gameplay behavior"],
        gate_summary=["`VAL-001` → unity_01_results"],
        now="2026-08-27T12:04:00Z",
    )
    issue.apply_delivery_review(
        task_id=TASK_ID,
        result_body=(
            "## Human delivery evidence review\n\n"
            "Decision: APPROVE\n"
            f"Proposal SHA256: `{'6' * 64}`\n"
        ),
        actor_id="cathode26",
        now="2026-08-27T12:05:00Z",
    )
    service.acquire_agent_lease(
        task=task(),
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=f"C:/Tasks/{TASK_ID}",
        planned_approach="Commit evidence and open the PR.",
        expected_validation="Passing checks and merge closeout.",
        now="2026-08-27T12:06:00Z",
    )
    released = ResumableDownstreamIssueCoordinator(service).release_for_pending_checks(
        task_id=TASK_ID,
        pull_request_url="https://github.com/cathode26/NoSafeCircle/pull/999",
        head_commit=EVIDENCE_HEAD,
        reason="Checks are pending.",
        now="2026-08-27T12:07:00Z",
    )
    state = released["workflow_state"]
    require(state["state"] == "agent_ready", "release did not become agent-ready")
    require(state["phase"] == "merge_closeout", "release lost closeout phase")
    require(state["head_commit"] == EVIDENCE_HEAD, "release did not advance head")
    require(
        state["human_handoff_commit"] == IMPLEMENTATION_HEAD,
        "release changed the human-tested implementation identity",
    )

    later = IssueWorkflowService(
        backend=backend,
        task_loader=lambda _: task(),
        worker_id="worker-b",
    )
    resumed = later.acquire_agent_lease(
        task=task(),
        source_head=SOURCE_HEAD,
        branch=BRANCH,
        checkout_path=f"C:/Tasks/{TASK_ID}",
        planned_approach="Resume the evidence head.",
        expected_validation="Fresh-main conformance after merge.",
        now="2026-08-27T12:08:00Z",
    )
    require(resumed["status"] == "acquired", f"later lease failed: {resumed}")
    require(
        resumed["workflow_state"]["head_commit"] == EVIDENCE_HEAD,
        "later worker did not resume the evidence commit",
    )


def test_downstream_workflow_accepts_conformant_task_only() -> None:
    environment = {
        "ready": True,
        "controller_clean": True,
        "taskgraph_valid": True,
    }
    selected = {
        "contract_disposition": "active",
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "derived_state": "conformant",
        "dependencies_conformant": True,
    }
    downstream = object.__new__(DownstreamTaskReviewWorkflow)
    ordinary = object.__new__(RealTaskReviewWorkflow)
    require(
        downstream._task_ready_for_coordination(environment, selected),
        "downstream workflow rejected a conformant managed task",
    )
    require(
        not ordinary._task_ready_for_coordination(environment, selected),
        "ordinary implementation workflow admitted a conformant task",
    )


def make_manifest(directory: Path, *, commit: str, tree: str) -> Path:
    directory.mkdir(parents=True)
    xml = directory / "test-results.xml"
    log = directory / "unity.log"
    xml.write_text("<test-run result=\"Passed\" />\n", encoding="utf-8")
    log.write_text("Unity test passed.\n", encoding="utf-8")
    manifest = directory / "validation-manifest.json"
    value = {
        "schema_version": "1.0",
        "manifest_type": "unity_test_validation",
        "status": "passed",
        "validated_state": {"commit": commit, "tree": tree},
        "unity": {"test_platform": "PlayMode", "test_filter": "Synthetic.Tests"},
        "artifacts": {
            "xml": {
                "relative_path": xml.name,
                "sha256": hashlib.sha256(xml.read_bytes()).hexdigest(),
                "size_bytes": xml.stat().st_size,
            },
            "log": {
                "relative_path": log.name,
                "sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                "size_bytes": log.stat().st_size,
            },
        },
    }
    manifest.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def test_delivery_draft_uses_stable_main_base() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-downstream-base-") as temporary:
        root = Path(temporary)
        repository = root / "repo"
        init_repo(repository)
        (repository / "feature.txt").write_text("base\n", encoding="utf-8")
        main_commit = commit_all(repository, "Create main")
        git(repository, "switch", "-c", BRANCH)
        (repository / "feature.txt").write_text("implementation\n", encoding="utf-8")
        commit_all(repository, "Initial implementation")
        (repository / "feature.txt").write_text("repaired\n", encoding="utf-8")
        human_head = commit_all(repository, "Human-requested repair")
        require(git(repository, "rev-parse", "HEAD^") != main_commit, "fixture needs two task commits")
        tree = git(repository, "rev-parse", "HEAD^{tree}")
        manifest_path = make_manifest(root / "validation", commit=human_head, tree=tree)
        human_path = root / "human-validation.txt"
        human_path.write_text("Result: PASS\n", encoding="utf-8")
        output = root / "output"
        output.mkdir()
        captured: dict[str, Any] = {}

        def runner(
            args: Sequence[str],
            cwd: Path,
            timeout_seconds: float,
        ) -> subprocess.CompletedProcess[bytes]:
            del timeout_seconds
            values = tuple(args)
            if len(values) >= 3 and values[0] == sys.executable and values[2] == "draft":
                captured["command"] = values
                output_path = Path(values[values.index("--output") + 1])
                base = values[values.index("--base-commit") + 1]
                output_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "1.0",
                            "review_kind": "delivery_spec_review",
                            "review_status": "needs_human",
                            "task": {"id": TASK_ID},
                            "validated_commit": human_head,
                            "base_commit": base,
                            "surface_candidates": [],
                            "artifacts": [],
                            "gates": [],
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(values, 0, b"", b"")
            return subprocess.run(values, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        controller = object.__new__(ResumableDownstreamTaskController)
        controller.task_id = TASK_ID
        controller.checkout = repository
        controller.command_runner = runner
        controller.state = {
            "validation_manifests": [_manifest(manifest_path)],
            "delivery_base_commit": main_commit,
        }
        controller._require_lease = lambda phase: (
            {"task": {"completion_gates": [{"requirement": "Play Mode validation."}]}},
            {"head_commit": human_head, "branch": BRANCH},
        )
        controller._assert_human_tested_head = lambda state: None
        controller._human_validation_artifact = lambda commit: {
            "path": str(human_path),
            "sha256": hashlib.sha256(human_path.read_bytes()).hexdigest(),
            "size_bytes": human_path.stat().st_size,
        }
        controller._output_root = lambda commit: output
        controller._persist = lambda: None

        facts = controller.create_delivery_review_draft()
        command = captured["command"]
        require(
            command[command.index("--base-commit") + 1] == main_commit,
            "draft used only the final repair parent",
        )
        require(facts["validated_commit"] == human_head, "draft commit changed")


class CompleteIssue:
    def complete(self, **values: Any) -> dict[str, Any]:
        return {"status": "complete", "values": values}


class NoIssueService:
    def find(self, task_id: str) -> None:
        del task_id
        return None


def test_post_merge_accepts_newer_main() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-downstream-post-merge-") as temporary:
        root = Path(temporary)
        remote = root / "remote.git"
        seed = root / "seed"
        run("git", "init", "--bare", str(remote), cwd=root)
        init_repo(seed)
        (seed / "Pipeline/TaskGraph").mkdir(parents=True)
        (seed / "Pipeline/TaskGraph/taskcontrol.py").write_text(
            "import sys\n"
            "if sys.argv[1:] == ['validate']:\n"
            "    print('taskcontrol validate: PASS')\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit(2)\n",
            encoding="utf-8",
        )
        (seed / "merged.txt").write_text("merged\n", encoding="utf-8")
        merge_commit = commit_all(seed, "Synthetic merged task")
        (seed / "later.txt").write_text("later mainline work\n", encoding="utf-8")
        main_head = commit_all(seed, "Unrelated later mainline work")
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

        def runner(
            args: Sequence[str],
            cwd: Path,
            timeout_seconds: float,
        ) -> subprocess.CompletedProcess[bytes]:
            del timeout_seconds
            values = tuple(args)
            if values[:3] == ("gh", "issue", "close"):
                return subprocess.CompletedProcess(values, 0, b"", b"")
            return subprocess.run(values, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        controller = object.__new__(ResumableDownstreamTaskController)
        controller.task_id = TASK_ID
        controller.checkout = seed
        controller.command_runner = runner
        controller.state = {
            "merged_commit": merge_commit,
            "pull_request_url": "https://github.com/cathode26/NoSafeCircle/pull/999",
            "pull_request_number": 999,
            "record_id": "delivery-record-777",
        }
        controller.issue = CompleteIssue()
        controller.workflow = SimpleNamespace(issue_workflow=NoIssueService())
        controller._require_lease = lambda phase: ({}, {})
        controller._task_state = lambda root, selected: {
            "task_id": selected,
            "state": "conformant",
            "selected_record_id": "delivery-record-777",
        }

        result = controller.verify_post_merge_and_complete()
        require(result["status"] == "complete", "post-merge closeout did not complete")
        require(result["merged_commit"] == merge_commit, "merge identity changed")
        require(result["main_head"] == main_head, "newer main head was not inspected")


def test_delivery_review_materializes_exact_proposal() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-delivery-review-") as temporary:
        root = Path(temporary)
        draft_path = root / "draft.json"
        proposal_path = root / "proposal.json"
        approved_path = root / "approved.json"
        draft = {
            "schema_version": "1.0",
            "review_kind": "delivery_spec_review",
            "review_status": "needs_human",
            "task": {"id": TASK_ID},
            "validated_commit": IMPLEMENTATION_HEAD,
            "surface_candidates": [
                {"path": "Assets/Feature.cs", "selected": False, "role": ""},
                {"path": "Assets/FeatureTests.cs", "selected": False, "role": ""},
            ],
            "artifacts": [
                {"id": "unity_01_results"},
                {"id": "human_validation_01"},
            ],
            "gates": [{"gate_id": "VAL-001", "evidence": [], "notes": ""}],
            "human_approval": {
                "required": True,
                "decision": "",
                "approved_by": "",
                "notes": "",
            },
        }
        draft_path.write_text(json.dumps(draft, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        proposal = create_delivery_review_proposal(
            draft_path=draft_path,
            output_path=proposal_path,
            task_id=TASK_ID,
            branch=BRANCH,
            selected_surfaces=[
                {"path": "Assets/Feature.cs", "role": "Runtime gameplay implementation"}
            ],
            gate_mappings=[
                {
                    "gate_id": "VAL-001",
                    "evidence": ["unity_01_results", "human_validation_01"],
                    "notes": "Automated and human evidence prove the runtime behavior.",
                }
            ],
            approval_notes="Reviewed against the task contract.",
            created_by="worker-a",
        )
        materialize_approved_review(
            proposal_path=proposal_path,
            expected_proposal_sha256=proposal["proposal_sha256"],
            output_path=approved_path,
            approved_by="Vincent",
        )
        approved = json.loads(approved_path.read_text(encoding="utf-8"))
        selected = {item["path"]: item for item in approved["surface_candidates"]}
        require(approved["review_status"] == "approved", "review not approved")
        require(selected["Assets/Feature.cs"]["selected"] is True, "surface missing")
        require(selected["Assets/FeatureTests.cs"]["selected"] is False, "extra surface selected")
        require(
            approved["gates"][0]["evidence"]
            == ["unity_01_results", "human_validation_01"],
            "gate evidence changed",
        )


def main() -> int:
    tests = (
        test_issue_lifecycle_resumes_evidence_head,
        test_downstream_workflow_accepts_conformant_task_only,
        test_delivery_draft_uses_stable_main_base,
        test_post_merge_accepts_newer_main,
        test_delivery_review_materializes_exact_proposal,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent downstream smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
