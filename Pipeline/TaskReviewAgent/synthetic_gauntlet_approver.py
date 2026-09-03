#!/usr/bin/env python3
"""Validate and approve one waiting private synthetic-gauntlet Issue.

This is deliberately not a general human-approval bot. It recognizes only the
committed private rehearsal gauntlet provenance, excludes NSC-042, runs the
exact committed Unity validation plan for implementation handoffs, and reviews
the exact two-child decomposition artifact before invoking the existing
PASS/decomposition approval helper with scheduler-deferred launch.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_resilience import (  # noqa: E402
    validation_plan_for,
)
from Pipeline.TaskReviewAgent.issue_queue import repo_root  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowEventType,
    WorkflowPhase,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowSnapshot,
)
from Pipeline.TaskReviewAgent.prepare_synthetic_gauntlet import (  # noqa: E402
    GAUNTLET_ID,
    PRESERVED_TASK_ID,
    _repository_from_origin,
    _test_filter,
)
from TaskDecomposition.contracts import DecompositionResult  # noqa: E402
from graph_apply_plan import plan_graph_apply  # noqa: E402
from graph_delta import GraphDeltaPlan, semantic_json_sha256  # noqa: E402
from persistent_work_graph import load_persistent_work_graph  # noqa: E402


class SyntheticApprovalError(RuntimeError):
    """The waiting Issue is outside the exact disposable approval policy."""


def _run_text(
    command: Sequence[str], *, cwd: Path, timeout_seconds: float = 180.0
) -> str:
    completed = subprocess.run(
        tuple(command),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        detail = " ".join((completed.stderr or completed.stdout).split())[:900]
        raise SyntheticApprovalError(
            f"command failed ({completed.returncode}): {' '.join(command)}"
            + (f": {detail}" if detail else "")
        )
    return completed.stdout.strip()


def _require_private_rehearsal(source: Path, confirmed_repository: str) -> str:
    origin = _run_text(
        ("git", "-C", str(source), "remote", "get-url", "origin"), cwd=source
    )
    repository = _repository_from_origin(origin)
    if repository.casefold() != confirmed_repository.casefold():
        raise SyntheticApprovalError(
            f"--confirm-repository must exactly name {repository}"
        )
    if repository.casefold() == "cathode26/nosafecircle":
        raise SyntheticApprovalError("synthetic approval refuses production")
    if "rehearsal" not in repository.casefold():
        raise SyntheticApprovalError("repository name must identify a rehearsal")
    metadata = json.loads(
        _run_text(
            (
                "gh",
                "repo",
                "view",
                repository,
                "--json",
                "nameWithOwner,isPrivate,defaultBranchRef",
            ),
            cwd=source,
        )
    )
    if (
        str(metadata.get("nameWithOwner") or "").casefold()
        != repository.casefold()
        or metadata.get("isPrivate") is not True
        or (metadata.get("defaultBranchRef") or {}).get("name") != "main"
    ):
        raise SyntheticApprovalError(
            "synthetic approval requires the exact private rehearsal with default main"
        )
    if _run_text(
        ("git", "-C", str(source), "branch", "--show-current"), cwd=source
    ) != "main":
        raise SyntheticApprovalError("synthetic approval requires attached main")
    if _run_text(
        (
            "git",
            "-C",
            str(source),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        cwd=source,
    ):
        raise SyntheticApprovalError("synthetic approval controller must be clean")
    head = _run_text(
        ("git", "-C", str(source), "rev-parse", "HEAD"), cwd=source
    )
    _run_text(("git", "-C", str(source), "fetch", "origin", "main"), cwd=source)
    remote = _run_text(
        ("git", "-C", str(source), "rev-parse", "origin/main"), cwd=source
    )
    if head != remote:
        raise SyntheticApprovalError(
            "synthetic approval controller HEAD must exactly match current origin/main"
        )
    return repository


def _direct_gauntlet_task(task: Mapping[str, Any]) -> bool:
    provenance = task.get("provenance")
    return bool(
        isinstance(provenance, Mapping)
        and provenance.get("origin") == "human_approved_synthetic_gauntlet"
        and provenance.get("gauntlet_id") == GAUNTLET_ID
    )


def _require_gauntlet_task(source: Path, task_id: str) -> dict[str, Any]:
    if task_id == PRESERVED_TASK_ID:
        raise SyntheticApprovalError("NSC-042 always requires Vincent's real validation")
    task = load_committed_task(source, task_id)
    if _direct_gauntlet_task(task):
        return task
    provenance = task.get("provenance")
    if not isinstance(provenance, Mapping) or provenance.get(
        "origin"
    ) != "progressive_decomposition":
        raise SyntheticApprovalError(f"{task_id} is not a synthetic gauntlet task")
    parent_id = provenance.get("parent_task_id")
    if not isinstance(parent_id, str):
        raise SyntheticApprovalError(f"{task_id} has no decomposition parent identity")
    parent = load_committed_task(source, parent_id)
    if not _direct_gauntlet_task(parent):
        raise SyntheticApprovalError(
            f"{task_id} was not decomposed from the exact synthetic gauntlet"
        )
    return task


def _expected_implementation_filter(source: Path, task: Mapping[str, Any]) -> str:
    provenance = task.get("provenance")
    if _direct_gauntlet_task(task):
        value = provenance.get("expected_value") if isinstance(provenance, Mapping) else None
        if type(value) is not int or task.get("execution_scope") != "single_agent":
            raise SyntheticApprovalError("direct synthetic task has no exact expected value")
        return _test_filter(value)
    if not isinstance(provenance, Mapping):
        raise SyntheticApprovalError("synthetic child omitted decomposition provenance")
    parent_id = provenance.get("parent_task_id")
    if not isinstance(parent_id, str):
        raise SyntheticApprovalError("synthetic child omitted its parent task ID")
    parent = load_committed_task(source, parent_id)
    number = int(parent_id.split("-")[1])
    expected_paths = (parent.get("provenance") or {}).get("expected_paths")
    resources = set(task.get("exclusive_resources") or ())
    if not isinstance(expected_paths, list) or len(expected_paths) != 4:
        raise SyntheticApprovalError("synthetic parent has no exact expected child paths")
    if resources == {f"repo-file:{path}" for path in expected_paths[:2]}:
        return _test_filter(number, "Alpha")
    if resources == {f"repo-file:{path}" for path in expected_paths[2:]}:
        return _test_filter(number, "Beta")
    raise SyntheticApprovalError("synthetic child resources do not select one exact test")


def _last_decomposition_handoff(snapshot: IssueWorkflowSnapshot):
    handoffs = [
        event
        for event in snapshot.events
        if event.event_type is WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED
    ]
    if not handoffs:
        raise SyntheticApprovalError("decomposition Issue has no exact plan handoff")
    return handoffs[-1]


def review_decomposition_plan(
    source: Path, snapshot: IssueWorkflowSnapshot, task: Mapping[str, Any]
) -> dict[str, Any]:
    handoff = _last_decomposition_handoff(snapshot)
    details = handoff.details
    artifact_root = Path(str(details.get("artifact_root") or "")).resolve()
    graph = GraphDeltaPlan.from_payload(
        json.loads((artifact_root / "graph_delta.json").read_text(encoding="utf-8"))
    )
    decomposition = DecompositionResult.from_dict(
        json.loads(
            (artifact_root / "decomposition_result.json").read_text(encoding="utf-8")
        )
    )
    plan_id = details.get("graph_delta_plan_id")
    if graph.plan_id != plan_id:
        raise SyntheticApprovalError("artifact plan_id differs from the Issue handoff")
    if not _direct_gauntlet_task(task) or not task.get("provenance", {}).get(
        "requires_decomposition"
    ):
        raise SyntheticApprovalError("decomposition parent is not a gauntlet split task")
    if (
        decomposition.decision != "decomposed"
        or len(decomposition.children) != 2
        or decomposition.unsupported_assumptions
        or decomposition.unresolved_questions
    ):
        raise SyntheticApprovalError(
            "synthetic decomposition must be an exact resolved two-child plan"
        )
    parent_payload = dict(task)
    parent_payload.pop("task_contract_sha256", None)
    parent_hash = semantic_json_sha256(parent_payload)
    preflight = plan_graph_apply(
        load_persistent_work_graph(source),
        decomposition.parent_task,
        decomposition,
        graph,
    )
    if preflight.status != "fresh" or preflight.recomputed_plan_id != graph.plan_id:
        raise SyntheticApprovalError(
            "stored decomposition is not an exact fresh deterministic graph plan: "
            f"{preflight.status}: {preflight.reason}"
        )
    graph_payload = graph.to_dict()
    if (
        graph_payload.get("parent_before_hash") != parent_hash
        or decomposition.parent_task.task_id != task.get("id")
        or decomposition.parent_task.contract_sha256 != parent_hash
    ):
        raise SyntheticApprovalError("decomposition parent contract identity changed")

    contracts = graph.proposed_child_contracts
    if len(contracts) != 2:
        raise SyntheticApprovalError("graph delta does not contain exactly two children")
    expected_paths = task.get("provenance", {}).get("expected_paths")
    expected_resources = set(task.get("exclusive_resources") or ())
    if (
        not isinstance(expected_paths, list)
        or len(expected_paths) != 4
        or len(expected_resources) != 4
        or expected_resources != {f"repo-file:{path}" for path in expected_paths}
    ):
        raise SyntheticApprovalError(
            "synthetic decomposition parent does not own its exact four expected paths"
        )
    owned: set[str] = set()
    number = int(str(task["id"]).split("-")[1])
    for child in contracts:
        resources = set(child.get("exclusive_resources") or ())
        if (
            not isinstance(child.get("id"), str)
            or child.get("execution_scope") != "single_agent"
            or child.get("decomposition_state") != "concrete"
            or child.get("parent") != task.get("id")
            or not resources
            or owned.intersection(resources)
        ):
            raise SyntheticApprovalError(
                "synthetic child identity, scope, or resource ownership is invalid"
            )
        provenance = child.get("provenance") or {}
        if (
            provenance.get("origin") != "progressive_decomposition"
            or provenance.get("parent_contract_sha256") != parent_hash
            or provenance.get("graph_delta_plan_id") != plan_id
        ):
            raise SyntheticApprovalError("synthetic child provenance is not exact")
        if resources == {f"repo-file:{path}" for path in expected_paths[:2]}:
            expected_filter = _test_filter(number, "Alpha")
        elif resources == {f"repo-file:{path}" for path in expected_paths[2:]}:
            expected_filter = _test_filter(number, "Beta")
        else:
            raise SyntheticApprovalError(
                "synthetic child does not own one exact Alpha or Beta resource pair"
            )
        gate_text = "\n".join(
            str(item.get("requirement") or "")
            for item in child.get("completion_gates") or ()
            if isinstance(item, Mapping)
        )
        if expected_filter not in gate_text:
            raise SyntheticApprovalError(
                "synthetic child omitted the exact Unity EditMode filter"
            )
        owned.update(resources)
    if owned != expected_resources:
        raise SyntheticApprovalError(
            "two children do not exactly partition the parent's four file resources"
        )
    return {
        "task_id": task["id"],
        "issue_number": snapshot.issue_number,
        "plan_id": plan_id,
        "artifact_root": str(artifact_root),
        "child_ids": [item["id"] for item in contracts],
        "status": "exact_synthetic_decomposition_review_passed",
    }


def _run_unity_validation(
    *, source: Path, checkout_root: Path, snapshot: IssueWorkflowSnapshot, task: dict
) -> dict[str, Any]:
    assert snapshot.state is not None
    checkout = Path(str(snapshot.state.checkout_path)).resolve()
    expected_checkout = checkout_root.resolve() / task["id"]
    if checkout != expected_checkout or not checkout.is_dir():
        raise SyntheticApprovalError(
            "implementation handoff is not the exact canonical task checkout"
        )
    plan = validation_plan_for(checkout, task)
    expected_filter = _expected_implementation_filter(source, task)
    if (
        plan is None
        or plan.get("required_test_platforms") != ["EditMode"]
        or plan.get("test_filters", {}).get("EditMode") != expected_filter
    ):
        raise SyntheticApprovalError(
            "synthetic task has no exact committed EditMode validation plan"
        )
    script = checkout / "Pipeline" / "Testing" / "run_unity_tests_clean.ps1"
    command = (
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-TestPlatform",
        "EditMode",
        "-TestFilter",
        expected_filter,
        "-ProjectPath",
        str(checkout),
    )
    completed = subprocess.run(command, cwd=str(checkout), check=False)
    if completed.returncode != 0:
        raise SyntheticApprovalError(
            f"exact synthetic Unity validation failed ({completed.returncode})"
        )
    return {
        "task_id": task["id"],
        "commit": snapshot.state.head_commit,
        "checkout": str(checkout),
        "test_platform": "EditMode",
        "test_filter": expected_filter,
        "status": "exact_synthetic_unity_validation_passed",
    }


def _approve(
    *,
    source: Path,
    checkout_root: Path,
    task_id: str,
    decomposition: bool,
    tested_commit: str | None,
) -> None:
    command = [
        sys.executable,
        str(source / "Pipeline" / "TaskReviewAgent" / "pass_and_resume_task.py"),
        task_id,
        "--source",
        str(source),
        "--checkout-root",
        str(checkout_root.resolve()),
        "--execution-provider",
        "claude",
        "--apply",
        "--defer-launch",
        "--notes",
        "Private synthetic gauntlet exact-policy validation passed.",
    ]
    if decomposition:
        command.append("--approve-decomposition")
    else:
        command.extend(("--tested-commit", str(tested_commit)))
    completed = subprocess.run(command, cwd=str(source), check=False)
    if completed.returncode != 0:
        raise SyntheticApprovalError(
            f"PASS/decomposition helper failed ({completed.returncode})"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--confirm-repository", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        source = repo_root(args.source.resolve())
        repository = _require_private_rehearsal(source, args.confirm_repository)
        service = IssueWorkflowService(
            backend=GhIssueBackend(source_root=source),
            task_loader=lambda task_id: load_committed_task(source, task_id),
            worker_id="synthetic-gauntlet-approver",
        )
        waiting = service.list_human_action_required()
        selected: tuple[IssueWorkflowSnapshot, dict[str, Any]] | None = None
        for entry in waiting:
            state = entry.get("workflow_state") or {}
            task_id = str(state.get("task_id") or "")
            try:
                task = _require_gauntlet_task(source, task_id)
            except SyntheticApprovalError:
                continue
            snapshot = service.find(task_id)
            if snapshot is None or snapshot.state is None:
                raise SyntheticApprovalError("selected managed Issue disappeared")
            selected = snapshot, task
            break
        if selected is None:
            print(
                json.dumps(
                    {
                        "status": "no_synthetic_human_action_required",
                        "repository": repository,
                        "waiting_issue_count": len(waiting),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        snapshot, task = selected
        phase = snapshot.state.phase
        if phase is WorkflowPhase.DECOMPOSITION_APPLY_AUTHORIZATION:
            result = review_decomposition_plan(source, snapshot, task)
            print(json.dumps(result, indent=2, sort_keys=True))
            if args.apply:
                _approve(
                    source=source,
                    checkout_root=args.checkout_root,
                    task_id=task["id"],
                    decomposition=True,
                    tested_commit=None,
                )
        elif phase is WorkflowPhase.UNITY_RUNTIME_VALIDATION:
            plan = {
                "task_id": task["id"],
                "issue_number": snapshot.issue_number,
                "commit": snapshot.state.head_commit,
                "status": "exact_synthetic_unity_validation_ready",
            }
            print(json.dumps(plan, indent=2, sort_keys=True))
            if args.apply:
                validated = _run_unity_validation(
                    source=source,
                    checkout_root=args.checkout_root,
                    snapshot=snapshot,
                    task=task,
                )
                print(json.dumps(validated, indent=2, sort_keys=True))
                _approve(
                    source=source,
                    checkout_root=args.checkout_root,
                    task_id=task["id"],
                    decomposition=False,
                    tested_commit=snapshot.state.head_commit,
                )
        else:
            raise SyntheticApprovalError(
                f"unsupported human-owned phase for synthetic task: {phase.value}"
            )
        print(
            "SYNTHETIC APPROVER: "
            + ("APPLIED" if args.apply else "DRY RUN (add --apply)")
        )
        return 0
    except (
        json.JSONDecodeError,
        OSError,
        RuntimeError,
        subprocess.TimeoutExpired,
        ValueError,
    ) as exc:
        print(f"SYNTHETIC APPROVER: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
