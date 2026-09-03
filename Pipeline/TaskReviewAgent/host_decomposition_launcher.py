#!/usr/bin/env python3
"""Host boundary for the durable proposal and application decomposition phases.

The proposal phase supplies the external Windows output mount and invokes the
canonical round-robin Compose service with the repository mounted read-only. The
separate apply phase runs only for an exact-plan human authorization recorded in
the durable Issue and serializes the network-free D1C commit with a global claim.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    semantic_sha256,
    validate_task_id,
)
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.durable_checkout import (  # noqa: E402
    DurableCheckoutError,
    DurableTaskCheckoutManager,
)
from Pipeline.TaskReviewAgent.claim_refs import (  # noqa: E402
    ClaimConflict,
    acquire_issue_lease_with_claims,
    build_activated_claim_client,
)
from Pipeline.TaskReviewAgent.issue_queue import repo_root  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowEventType,
    WorkflowPhase,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueWorkflowService,
)
from Pipeline.TaskReviewAgent.real_observation import RealTaskObserver  # noqa: E402
from Pipeline.TaskDecomposition.context_builder import (  # noqa: E402
    validate_task_selection as validate_decomposition_selection,
)
from TaskDecomposition.contracts import DecompositionResult  # noqa: E402
from graph_delta import GraphDeltaPlan  # noqa: E402
from apply_graph_delta import apply_graph_delta  # noqa: E402


GLOBAL_D1C_RESOURCE = "logical:taskgraph-decomposition-apply"


def default_host_output_root(task_id: str) -> Path:
    task_id = validate_task_id(task_id)
    profile = os.environ.get("USERPROFILE")
    if not profile:
        raise RuntimeError("USERPROFILE is required for decomposition output policy")
    return Path(profile) / "Downloads" / "NoSafeCircleOutput" / task_id


def build_compose_command(
    *,
    task_id: str,
    project: str,
    providers: str,
    max_calls: int,
) -> tuple[str, ...]:
    return (
        "docker",
        "compose",
        "-p",
        project,
        "run",
        "--rm",
        "-T",
        "round-robin-decompose",
        "python3",
        "Pipeline/TaskDecomposition/run_round_robin_decomposition.py",
        "--task-id",
        validate_task_id(task_id),
        "--providers",
        providers,
        "--max-calls",
        str(max_calls),
    )


def _git(source: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(source), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=180.0,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {' '.join(completed.stderr.split())[:700]}"
        )
    return completed.stdout.strip()


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise RuntimeError(f"expected one JSON object: {path}")
    return value


def _decomposition_handoff_event(snapshot) -> object:
    matches = [
        event
        for event in snapshot.events
        if event.event_type is WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED
    ]
    if not matches:
        raise RuntimeError("approved decomposition Issue has no durable handoff event")
    return matches[-1]


def _acquire_workflow_lease(
    *,
    source: Path,
    task: dict,
    source_head: str,
    worker_id: str,
    service: IssueWorkflowService,
    branch: str,
    checkout_path: Path,
):
    remote_url = _git(source, "remote", "get-url", "origin")
    client = build_activated_claim_client(
        local_repository=source,
        remote=remote_url,
        worker_id=worker_id,
    )
    result = acquire_issue_lease_with_claims(
        claim_client=client,
        issue_workflow=service,
        task=task,
        source_head=source_head,
        branch=branch,
        checkout_path=str(checkout_path),
        planned_approach=(
            "work_type: decomposition\nRun or resume the independently reviewed "
            "round-robin decomposition lifecycle for this exact parent contract."
        ),
        expected_validation=(
            "Require an exact plan_id authorization before D1C, validate the committed "
            "TaskGraph, and push only the exact applied commit."
        ),
    )
    if result.get("status") not in {"acquired", "resumed"}:
        raise RuntimeError(
            "decomposition Issue/claim lease was not acquired: "
            + json.dumps(result, sort_keys=True)
        )
    return client, result


def _checkout_observation(
    *,
    source: Path,
    task_id: str,
    service: IssueWorkflowService,
) -> dict:
    observation = RealTaskObserver(source, task_id).observe_goal_state()
    environment = dict(observation["environment"])
    environment["remote_url"] = _git(source, "remote", "get-url", "origin")
    coordination = dict(service.observe(task_id))
    workflow_status = coordination.get("status")
    coordination["workflow_status"] = workflow_status
    identity = {
        "environment": environment,
        "task": observation["task"],
        "coordination": coordination,
    }
    return {
        **observation,
        **identity,
        "observation_sha256": semantic_sha256(identity),
    }


def _run_proposal(
    *,
    args: argparse.Namespace,
    workspace: Path,
    output_root: Path,
    source_head: str,
    service: IssueWorkflowService,
) -> int:
    output_root.mkdir(parents=True, exist_ok=True)
    before = {path.name for path in output_root.iterdir() if path.is_dir()}
    environment = os.environ.copy()
    environment["NSC_DECOMPOSITION_HOST_OUTPUT_ROOT"] = str(output_root)
    try:
        completed = subprocess.run(
            build_compose_command(
                task_id=args.task_id,
                project=args.compose_project,
                providers=args.providers,
                max_calls=args.max_calls,
            ),
            cwd=str(workspace),
            env=environment,
            check=False,
        )
    except OSError as exc:
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason=(
                "D1B.2 provider process could not start; no provider ran: "
                f"{type(exc).__name__}: {exc}"
            ),
        )
        print(
            json.dumps(
                {
                    "status": "proposal_retry_required",
                    "task_id": args.task_id,
                    "provider_start_error": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 0
    after = [
        path
        for path in output_root.iterdir()
        if path.is_dir() and path.name not in before
    ]
    if completed.returncode != 0 or len(after) != 1:
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason=(
                f"D1B.2 exited {completed.returncode}; expected exactly one new run "
                f"directory and observed {len(after)}."
            ),
        )
        print(
            json.dumps(
                {
                    "status": "proposal_retry_required",
                    "task_id": args.task_id,
                    "provider_exit_code": completed.returncode,
                    "new_run_directory_count": len(after),
                },
                sort_keys=True,
            )
        )
        return 0
    run_dir = after[0]
    try:
        result = _load_json(run_dir / "decomposition_run_result.json")
    except (OSError, RuntimeError, ValueError) as exc:
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason=f"D1B.2 result artifacts were unreadable or invalid: {exc}",
        )
        print(
            json.dumps(
                {
                    "status": "proposal_retry_required",
                    "task_id": args.task_id,
                    "artifact_error": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 0
    if result.get("run_status") != "review_ready" or not result.get("graph_delta_path"):
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason=f"D1B.2 ended with {result.get('run_status')!r}, not review_ready.",
        )
        print(
            json.dumps(
                {
                    "status": "proposal_retry_required",
                    "task_id": args.task_id,
                    "run_status": result.get("run_status"),
                },
                sort_keys=True,
            )
        )
        return 0
    try:
        graph_path = run_dir / str(result["graph_delta_path"])
        graph = GraphDeltaPlan.from_payload(_load_json(graph_path))
        decomposition = DecompositionResult.from_dict(
            _load_json(run_dir / str(result["decomposition_result_path"]))
        )
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason=f"D1B.2 review-ready artifacts were unreadable or invalid: {exc}",
        )
        print(
            json.dumps(
                {
                    "status": "proposal_retry_required",
                    "task_id": args.task_id,
                    "artifact_error": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 0
    service.publish_decomposition_handoff(
        task_id=args.task_id,
        source_head=source_head,
        checkout_path=str(workspace),
        decomposition_run_id=str(result["run_id"]),
        artifact_root=str(run_dir),
        graph_delta_plan_id=graph.plan_id,
        summary=(
            f"Proposed {len(decomposition.children)} executable child task(s) for "
            f"{args.task_id}; independent reviewer: "
            f"{result.get('independent_approver_provider')}."
        ),
        branch=_git(workspace, "branch", "--show-current"),
    )
    print(
        json.dumps(
            {
                "status": "human_action_required",
                "task_id": args.task_id,
                "plan_id": graph.plan_id,
                "run_directory": str(run_dir),
            },
            sort_keys=True,
        )
    )
    return 0


def _apply_approved_plan(
    *,
    args: argparse.Namespace,
    source: Path,
    source_head: str,
    service: IssueWorkflowService,
    claim_client,
    prelease_snapshot,
) -> int:
    handoff = _decomposition_handoff_event(prelease_snapshot)
    details = handoff.details
    plan_id = str(details["graph_delta_plan_id"])
    authorized_head = str(details["head_commit"])
    if source_head != authorized_head:
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason=(
                f"main moved after authorization (authorized={authorized_head}, "
                f"current={source_head}); a fresh D1B.2 proposal is required."
            ),
        )
        return 0
    _git(source, "fetch", "origin", "main")
    remote_main = _git(source, "rev-parse", "origin/main")
    if remote_main != source_head:
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason=(
                f"origin/main moved after authorization (authorized={source_head}, "
                f"remote={remote_main}); a fresh D1B.2 proposal is required."
            ),
        )
        return 0
    global_claim = claim_client.acquire(
        task_id=args.task_id,
        exclusive_resources=(GLOBAL_D1C_RESOURCE,),
        source_head=source_head,
    )
    if isinstance(global_claim, ClaimConflict):
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason="another decomposition currently owns the global D1C application claim",
            retry_phase=WorkflowPhase.DECOMPOSITION_APPLY,
        )
        return 0
    try:
        run_dir = Path(str(details["artifact_root"])).resolve()
        decomposition = DecompositionResult.from_dict(
            _load_json(run_dir / "decomposition_result.json")
        )
        graph = GraphDeltaPlan.from_payload(_load_json(run_dir / "graph_delta.json"))
        if graph.plan_id != plan_id:
            raise RuntimeError("durable handoff plan_id does not match graph_delta.json")
        applied = apply_graph_delta(
            source,
            decomposition.parent_task.to_dict(),
            decomposition,
            graph,
            expected_head=source_head,
        )
        if applied.status not in {"applied", "already_applied"}:
            raise RuntimeError(
                f"D1C did not apply plan {plan_id}: {applied.status}: {applied.reason}"
            )
        commit = applied.new_commit_sha or applied.current_head
        _git(source, "push", "origin", f"{commit}:refs/heads/main")
        _git(source, "fetch", "origin", "main")
        if _git(source, "rev-parse", "origin/main") != commit:
            raise RuntimeError("origin/main did not verify at the exact D1C commit")
        service.complete_decomposition(
            task_id=args.task_id,
            graph_delta_plan_id=plan_id,
            applied_commit=commit,
        )
        print(
            json.dumps(
                {
                    "status": "complete",
                    "task_id": args.task_id,
                    "plan_id": plan_id,
                    "applied_commit": commit,
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        claim_client.release(global_claim)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--compose-project", default="nosafecircle-m2a")
    parser.add_argument("--providers", default="codex,claude")
    parser.add_argument("--max-calls", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        task_id = validate_task_id(args.task_id)
        source = repo_root(args.source.resolve())
        output_root = (args.output_root or default_host_output_root(task_id)).resolve()
        if output_root == source or output_root.is_relative_to(source):
            raise RuntimeError("decomposition output root must be outside the source repository")
        if args.max_calls < 2:
            raise RuntimeError("round-robin decomposition requires at least two calls")
        branch = _git(source, "symbolic-ref", "--short", "HEAD")
        if branch != "main":
            raise RuntimeError(
                f"decomposition controller must run from attached main, found {branch!r}"
            )
        if _git(source, "status", "--porcelain=v1", "--untracked-files=all"):
            raise RuntimeError("decomposition controller source must be completely clean")
        source_head = _git(source, "rev-parse", "HEAD")
        task = load_committed_task(source, task_id)
        validate_decomposition_selection(task_id, task)
        service = IssueWorkflowService(
            backend=GhIssueBackend(source_root=source),
            task_loader=lambda selected: load_committed_task(source, selected),
            worker_id=args.worker_id,
        )
        prelease = service.find(task_id)
        resume_phase = (
            prelease.state.phase if prelease is not None and prelease.state is not None else None
        )
        checkout_manager = DurableTaskCheckoutManager(
            source_root=source,
            task_id=task_id,
            checkout_root=args.checkout_root.resolve(),
            worker_id=args.worker_id,
            work_type="decomposition",
        )
        expected_branch = checkout_manager.expected_branch(
            RealTaskObserver(source, task_id).observe_goal_state()
        )
        claim_client, _lease = _acquire_workflow_lease(
            source=source,
            task=task,
            source_head=source_head,
            worker_id=args.worker_id,
            service=service,
            branch=expected_branch,
            checkout_path=checkout_manager.checkout_path,
        )
        if resume_phase is WorkflowPhase.DECOMPOSITION_APPLY:
            if prelease is None:
                raise RuntimeError("decomposition apply resume lost its durable Issue")
            return _apply_approved_plan(
                args=args,
                source=source,
                source_head=source_head,
                service=service,
                claim_client=claim_client,
                prelease_snapshot=prelease,
            )
        try:
            observation = _checkout_observation(
                source=source,
                task_id=task_id,
                service=service,
            )
            checkout = checkout_manager.prepare(observation)
        except (DurableCheckoutError, OSError, RuntimeError, ValueError) as exc:
            service.release_decomposition_lease(
                task_id=task_id,
                reason=(
                    "canonical decomposition checkout preparation failed before "
                    f"provider start: {type(exc).__name__}: {exc}"
                ),
            )
            raise
        if checkout.get("status") not in {"created", "adopted", "resumed"}:
            service.release_decomposition_lease(
                task_id=task_id,
                reason=(
                    "canonical decomposition checkout could not be prepared: "
                    + json.dumps(checkout.get("reasons") or [], sort_keys=True)
                ),
            )
            raise RuntimeError(
                "canonical decomposition checkout is blocked; existing path was not changed"
            )
        return _run_proposal(
            args=args,
            workspace=checkout_manager.checkout_path,
            output_root=output_root,
            source_head=source_head,
            service=service,
        )
    except (DurableCheckoutError, OSError, RuntimeError, ValueError) as exc:
        print(f"Decomposition launcher blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
