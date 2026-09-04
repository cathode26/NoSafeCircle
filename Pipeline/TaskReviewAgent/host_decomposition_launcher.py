#!/usr/bin/env python3
"""Host boundary for the durable proposal and application decomposition phases.

The proposal phase supplies the external Windows output mount and invokes the
canonical round-robin Compose service with the repository mounted read-only. The
separate apply phase runs only for an exact-plan human authorization recorded in
the durable Issue and serializes the network-free D1C commit with a global claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import uuid


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
from Pipeline.TaskReviewAgent.decomposition_replay import (  # noqa: E402
    inspect_authorized_decomposition_replay,
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
    WorkflowState,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueWorkflowService,
)
from Pipeline.TaskReviewAgent.real_observation import RealTaskObserver  # noqa: E402
from Pipeline.TaskReviewAgent.worker_result import (  # noqa: E402
    initialize_worker_run,
    write_worker_result,
)
from Pipeline.TaskDecomposition.context_builder import (  # noqa: E402
    validate_task_selection as validate_decomposition_selection,
)
from TaskDecomposition.contracts import DecompositionResult  # noqa: E402
from graph_delta import GraphDeltaPlan  # noqa: E402
from graph_apply_plan import plan_graph_apply  # noqa: E402
from apply_graph_delta import apply_graph_delta  # noqa: E402
from persistent_work_graph import load_persistent_work_graph  # noqa: E402


GLOBAL_D1C_RESOURCE = "logical:taskgraph-decomposition-apply"


class DecompositionApplyRetryableError(RuntimeError):
    """Remote D1C is proven, but durable Issue completion needs another worker."""


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
    run_id: str | None = None,
) -> tuple[str, ...]:
    command = [
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
    ]
    if run_id:
        command.extend(("--run-id", run_id))
    return tuple(command)


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


def _exact_d1c_commit(
    source: Path,
    *,
    task_id: str,
    plan_id: str,
    authorized_head: str,
    current_head: str,
) -> str:
    """Locate the one canonical D1C commit in current main ancestry."""

    subject = f"taskgraph: apply {task_id} decomposition {plan_id}"
    commits = tuple(
        line
        for line in _git(
            source,
            "rev-list",
            "--ancestry-path",
            f"{authorized_head}..{current_head}",
        ).splitlines()
        if line
    )
    matches = []
    for commit in commits:
        if _git(source, "show", "-s", "--format=%s", commit) != subject:
            continue
        parents = _git(source, "show", "-s", "--format=%P", commit).split()
        if parents == [authorized_head]:
            matches.append(commit)
    if len(matches) != 1:
        raise RuntimeError(
            "exact already-applied D1C commit could not be identified uniquely "
            f"from {authorized_head} to {current_head}; matches={matches}"
        )
    return matches[0]


def _exact_handoff_is_durable(
    snapshot,
    *,
    run_id: str,
    source_head: str,
    plan_id: str,
    artifact_root: str,
    graph_delta_sha256: str,
) -> bool:
    if (
        snapshot is None
        or not snapshot.valid
        or snapshot.state is None
        or snapshot.state.state is not WorkflowState.HUMAN_ACTION_REQUIRED
        or snapshot.state.phase
        is not WorkflowPhase.DECOMPOSITION_APPLY_AUTHORIZATION
    ):
        return False
    handoffs = [
        event
        for event in snapshot.events
        if event.event_type is WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED
    ]
    if not handoffs:
        return False
    handoff = handoffs[-1]
    details = handoff.details
    return (
        details.get("decomposition_run_id") == run_id
        and details.get("head_commit") == source_head
        and details.get("graph_delta_plan_id") == plan_id
        and details.get("artifact_root") == artifact_root
        and details.get("graph_delta_sha256") == graph_delta_sha256
    )


def _exact_completion_is_durable(
    snapshot,
    *,
    plan_id: str,
    applied_commit: str,
) -> bool:
    if (
        snapshot is None
        or not snapshot.valid
        or snapshot.state is None
        or snapshot.state.state is not WorkflowState.COMPLETE
        or snapshot.state.phase is not WorkflowPhase.DECOMPOSITION_APPLY
    ):
        return False
    completed = [
        event
        for event in snapshot.events
        if event.event_type is WorkflowEventType.COMPLETED
    ]
    if not completed:
        return False
    details = completed[-1].details
    return (
        details.get("work_type") == "decomposition"
        and details.get("graph_delta_plan_id") == plan_id
        and details.get("applied_commit") == applied_commit
    )


def _release_owned_decomposition_lease(
    *,
    service: IssueWorkflowService,
    task_id: str,
    worker_id: str,
    retry_phase: WorkflowPhase,
    reason: str,
) -> bool:
    """Release only a still-valid lease that this exact process still owns."""

    snapshot = service.find(task_id)
    if (
        snapshot is None
        or not getattr(snapshot, "valid", False)
        or getattr(snapshot, "state", None) is None
        or snapshot.state.state is not WorkflowState.AGENT_WORKING
        or snapshot.state.worker_id != worker_id
    ):
        return False
    service.release_decomposition_lease(
        task_id=task_id,
        reason=reason,
        retry_phase=retry_phase,
    )
    return True


def _acquire_workflow_lease(
    *,
    source: Path,
    task: dict,
    source_head: str,
    worker_id: str,
    service: IssueWorkflowService,
    branch: str,
    checkout_path: Path,
    expected_workflow_contract_sha256: str | None = None,
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
        expected_workflow_contract_sha256=expected_workflow_contract_sha256,
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
    requested_run_id = getattr(args, "run_id", None)
    expected_run_dir: Path | None = None
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        if requested_run_id:
            expected_run_dir = output_root / requested_run_id
            if expected_run_dir.exists():
                raise RuntimeError(
                    "D1B.2 exact decomposition run directory already exists: "
                    f"{requested_run_id}"
                )
            before: set[str] | None = None
        else:
            before = {path.name for path in output_root.iterdir() if path.is_dir()}
    except (OSError, RuntimeError) as exc:
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason=(
                "D1B.2 output directory could not be observed before provider start: "
                f"{type(exc).__name__}: {exc}"
            ),
        )
        raise
    environment = os.environ.copy()
    environment["NSC_DECOMPOSITION_HOST_OUTPUT_ROOT"] = str(output_root)
    try:
        completed = subprocess.run(
            build_compose_command(
                task_id=args.task_id,
                project=args.compose_project,
                providers=args.providers,
                max_calls=args.max_calls,
                run_id=getattr(args, "run_id", None),
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
        return 3
    try:
        if expected_run_dir is not None:
            after = [expected_run_dir] if expected_run_dir.is_dir() else []
        else:
            after = [
                path
                for path in output_root.iterdir()
                if path.is_dir() and path.name not in (before or set())
            ]
    except OSError as exc:
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason=(
                "D1B.2 output directory could not be observed after provider exit: "
                f"{type(exc).__name__}: {exc}"
            ),
        )
        raise
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
        return 3
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
        return 3
    source_identity = result.get("source_identity")
    contract_identity = result.get("task_execution_contract_identity")
    expected_contract_sha256 = getattr(args, "task_contract_sha256", None)
    identity_reasons = []
    if result.get("task_id") != args.task_id:
        identity_reasons.append("task_id")
    if result.get("run_id") != run_dir.name:
        identity_reasons.append("run_id")
    if requested_run_id and result.get("run_id") != requested_run_id:
        identity_reasons.append("scheduler_run_id")
    if (
        not isinstance(source_identity, dict)
        or source_identity.get("head_commit") != source_head
    ):
        identity_reasons.append("source_head")
    if expected_contract_sha256 and (
        not isinstance(contract_identity, dict)
        or contract_identity.get("sha256") != expected_contract_sha256
    ):
        identity_reasons.append("task_contract_sha256")
    if identity_reasons:
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason=(
                "D1B.2 result identity did not match its exact admission: "
                + ", ".join(identity_reasons)
            ),
        )
        print(
            json.dumps(
                {
                    "status": "proposal_retry_required",
                    "task_id": args.task_id,
                    "identity_mismatch": identity_reasons,
                },
                sort_keys=True,
            )
        )
        return 3
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
        return 3
    if (
        result.get("graph_delta_path") != "graph_delta.json"
        or result.get("decomposition_result_path") != "decomposition_result.json"
    ):
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason="D1B.2 review-ready result named a non-canonical artifact path.",
        )
        print(
            json.dumps(
                {
                    "status": "proposal_retry_required",
                    "task_id": args.task_id,
                    "artifact_error": "non_canonical_result_path",
                },
                sort_keys=True,
            )
        )
        return 3
    try:
        graph = GraphDeltaPlan.from_payload(_load_json(run_dir / "graph_delta.json"))
        decomposition = DecompositionResult.from_dict(
            _load_json(run_dir / "decomposition_result.json")
        )
        plan_id = graph.plan_id
        if re.fullmatch(r"GDP-[0-9a-f]{64}", plan_id) is None:
            raise RuntimeError("D1B.2 graph plan has an invalid plan_id")
        preflight = plan_graph_apply(
            load_persistent_work_graph(workspace),
            decomposition.parent_task.to_dict(),
            decomposition,
            graph,
        )
        if preflight.status != "fresh":
            raise RuntimeError(
                "D1B.2 review-ready artifacts failed exact deterministic D1C "
                f"preflight: {preflight.status}: {preflight.reason}"
            )
        graph_delta_sha256 = hashlib.sha256(
            graph.canonical_json().encode("utf-8")
        ).hexdigest()
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
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
        return 3
    handoff_values = {
        "task_id": args.task_id,
        "source_head": source_head,
        "checkout_path": str(workspace),
        "decomposition_run_id": str(result["run_id"]),
        "artifact_root": str(run_dir),
        "graph_delta_plan_id": plan_id,
        "graph_delta_sha256": graph_delta_sha256,
        "summary": (
            f"Proposed {len(decomposition.children)} executable child task(s) for "
            f"{args.task_id}; independent reviewer: "
            f"{result.get('independent_approver_provider')}."
        ),
        "branch": _git(workspace, "branch", "--show-current"),
    }
    try:
        service.publish_decomposition_handoff(**handoff_values)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        snapshot = service.find(args.task_id)
        if not _exact_handoff_is_durable(
            snapshot,
            run_id=str(result["run_id"]),
            source_head=source_head,
            plan_id=plan_id,
            artifact_root=str(run_dir),
            graph_delta_sha256=graph_delta_sha256,
        ):
            raise
    print(
        json.dumps(
            {
                "status": "human_action_required",
                "task_id": args.task_id,
                "plan_id": plan_id,
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
    replay = inspect_authorized_decomposition_replay(
        source=source,
        snapshot=prelease_snapshot,
        expected_head=source_head,
    )
    plan_id = replay.plan_id
    authorized_head = replay.authorized_source_head
    if (
        source_head != authorized_head
        and replay.inspection.status != "already_applied"
    ):
        service.release_decomposition_lease(
            task_id=args.task_id,
            reason=(
                f"main moved after authorization (authorized={authorized_head}, "
                f"current={source_head}) and the exact approved plan is not applied: "
                f"{replay.inspection.status}: {replay.inspection.reason}; a fresh "
                "D1B.2 proposal is required."
            ),
        )
        return 3
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
        return 3
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
        return 3
    applied_commit: str | None = None
    try:
        run_dir = replay.artifact_root
        decomposition = DecompositionResult.from_dict(
            _load_json(run_dir / "decomposition_result.json")
        )
        applied = apply_graph_delta(
            source,
            decomposition.parent_task.to_dict(),
            decomposition,
            replay.graph_delta,
            expected_head=source_head,
        )
        if applied.status not in {"applied", "already_applied"}:
            raise RuntimeError(
                f"D1C did not apply plan {plan_id}: {applied.status}: {applied.reason}"
            )
        applied_commit = applied.new_commit_sha
        if applied.status == "already_applied":
            applied_commit = _exact_d1c_commit(
                source,
                task_id=args.task_id,
                plan_id=plan_id,
                authorized_head=authorized_head,
                current_head=source_head,
            )
        if applied_commit is None:
            raise RuntimeError("D1C success omitted its exact application commit")
        if applied.status == "applied":
            try:
                _git(source, "push", "origin", f"{applied_commit}:refs/heads/main")
            except RuntimeError:
                # A transport failure can be reported after the remote accepted
                # the exact push. Re-observe only; never repeat the mutation.
                _git(source, "fetch", "origin", "main")
                if _git(source, "rev-parse", "origin/main") != applied_commit:
                    raise
        _git(source, "fetch", "origin", "main")
        expected_remote_head = (
            applied_commit if applied.status == "applied" else source_head
        )
        if _git(source, "rev-parse", "origin/main") != expected_remote_head:
            raise RuntimeError(
                "origin/main did not verify at the exact observed D1C boundary"
            )
        try:
            service.complete_decomposition(
                task_id=args.task_id,
                graph_delta_plan_id=plan_id,
                applied_commit=applied_commit,
            )
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
            snapshot = service.find(args.task_id)
            if not _exact_completion_is_durable(
                snapshot,
                plan_id=plan_id,
                applied_commit=applied_commit,
            ):
                raise DecompositionApplyRetryableError(
                    "D1C commit is present on origin/main, but Issue completion "
                    f"did not become durable: {type(exc).__name__}: {exc}"
                ) from exc
        print(
            json.dumps(
                {
                    "status": "complete",
                    "task_id": args.task_id,
                    "plan_id": plan_id,
                    "applied_commit": applied_commit,
                },
                sort_keys=True,
            )
        )
        return 0
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        snapshot = service.find(args.task_id)
        if applied_commit is None or not _exact_completion_is_durable(
            snapshot,
            plan_id=plan_id,
            applied_commit=applied_commit,
        ):
            raise
        print(
            json.dumps(
                {
                    "status": "complete",
                    "task_id": args.task_id,
                    "plan_id": plan_id,
                    "applied_commit": applied_commit,
                    "recovered_after_post_mutation_error": True,
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
    parser.add_argument("--scheduler-output-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--admission-source-head")
    parser.add_argument("--task-contract-sha256")
    parser.add_argument("--admission-issue-number", type=int)
    args = parser.parse_args(argv)
    scheduler_run_dir: Path | None = None
    known_issue_number: int | None = args.admission_issue_number
    service: IssueWorkflowService | None = None
    lease_acquired = False
    lease_retry_phase = WorkflowPhase.DECOMPOSITION
    scheduler_started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    scheduler_fields = (
        args.scheduler_output_root,
        args.run_id,
        args.admission_source_head,
        args.task_contract_sha256,
    )

    def finish(
        exit_code: int,
        terminal_status: str,
        authority: str,
        issue_number: int | None = None,
    ) -> int:
        result_issue_number = (
            known_issue_number if issue_number is None else issue_number
        )
        if scheduler_run_dir is not None:
            write_worker_result(
                run_dir=scheduler_run_dir,
                run_id=args.run_id,
                worker_id=args.worker_id,
                task_id=args.task_id,
                source_head=args.admission_source_head,
                task_contract_sha256=args.task_contract_sha256,
                terminal_status=terminal_status,
                outcome_authority=authority,
                issue_number=result_issue_number,
                exit_code=exit_code,
                pid=os.getpid(),
            )
        return exit_code

    try:
        task_id = validate_task_id(args.task_id)
        if args.admission_issue_number is not None and not any(
            value is not None for value in scheduler_fields
        ):
            raise RuntimeError(
                "scheduler admission Issue number requires scheduler result identity"
            )
        if any(value is not None for value in scheduler_fields):
            if args.scheduler_output_root is None or not all(
                isinstance(value, str) and value
                for value in (
                    args.run_id,
                    args.admission_source_head,
                    args.task_contract_sha256,
                )
            ):
                raise RuntimeError(
                    "scheduler result identity requires output root, run id, source "
                    "HEAD, and contract hash together"
                )
            if re.fullmatch(r"[0-9a-f]{40}", args.admission_source_head) is None:
                raise RuntimeError("scheduler admission source HEAD is invalid")
            if re.fullmatch(r"[0-9a-f]{64}", args.task_contract_sha256) is None:
                raise RuntimeError("scheduler task-contract hash is invalid")
            if (
                args.admission_issue_number is not None
                and args.admission_issue_number < 1
            ):
                raise RuntimeError(
                    "scheduler admission Issue number must be a positive integer"
                )
            scheduler_run_dir = initialize_worker_run(
                output_root=args.scheduler_output_root,
                task_id=task_id,
                run_id=args.run_id,
                worker_id=args.worker_id,
                started_at_utc=scheduler_started_at,
            )
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
        if scheduler_run_dir is not None and (
            source_head != args.admission_source_head
            or task.get("task_contract_sha256") != args.task_contract_sha256
        ):
            raise RuntimeError("scheduler decomposition admission identity changed")
        if scheduler_run_dir is None:
            args.run_id = f"host-{task_id.casefold()}-{uuid.uuid4().hex[:16]}"
            args.task_contract_sha256 = task.get("task_contract_sha256")
            if re.fullmatch(r"[0-9a-f]{64}", str(args.task_contract_sha256)) is None:
                raise RuntimeError(
                    "committed decomposition task has no valid contract hash"
                )
        service = IssueWorkflowService(
            backend=GhIssueBackend(source_root=source),
            task_loader=lambda selected: load_committed_task(source, selected),
            worker_id=args.worker_id,
        )
        prelease = service.find(task_id)
        if args.admission_issue_number is not None:
            if prelease is None or prelease.issue_number != args.admission_issue_number:
                raise RuntimeError(
                    "scheduler decomposition admission Issue identity changed"
                )
            known_issue_number = prelease.issue_number
        resume_phase = (
            prelease.state.phase if prelease is not None and prelease.state is not None else None
        )
        apply_replay = None
        lease_task = task
        expected_workflow_contract_sha256 = None
        if resume_phase is WorkflowPhase.DECOMPOSITION_APPLY:
            if prelease is None or prelease.state is None:
                raise RuntimeError("decomposition apply resume lost its durable Issue")
            apply_replay = inspect_authorized_decomposition_replay(
                source=source,
                snapshot=prelease,
                expected_head=source_head,
            )
            load_committed_task(
                source,
                task_id,
                commit=apply_replay.authorized_source_head,
                expected_sha256=prelease.state.task_contract_sha256,
            )
            expected_workflow_contract_sha256 = (
                prelease.state.task_contract_sha256
            )
        else:
            validate_decomposition_selection(task_id, task)
        checkout_manager = DurableTaskCheckoutManager(
            source_root=source,
            task_id=task_id,
            checkout_root=args.checkout_root.resolve(),
            worker_id=args.worker_id,
            work_type="decomposition",
        )
        if resume_phase is WorkflowPhase.DECOMPOSITION_APPLY:
            expected_branch = str(prelease.state.branch or "").strip()
            if not expected_branch:
                raise RuntimeError(
                    "decomposition apply resume Issue has no recorded branch"
                )
        else:
            expected_branch = checkout_manager.expected_branch(
                RealTaskObserver(source, task_id).observe_goal_state()
            )
        claim_client, lease = _acquire_workflow_lease(
            source=source,
            task=lease_task,
            source_head=source_head,
            worker_id=args.worker_id,
            service=service,
            branch=expected_branch,
            checkout_path=checkout_manager.checkout_path,
            expected_workflow_contract_sha256=(
                expected_workflow_contract_sha256
            ),
        )
        if lease.get("status") not in {"acquired", "resumed"}:
            issue_number = lease.get("issue_number")
            if prelease is not None:
                if issue_number is not None and issue_number != prelease.issue_number:
                    raise RuntimeError(
                        "blocked decomposition lease changed its durable Issue identity"
                    )
                issue_number = prelease.issue_number
            elif type(issue_number) is not int or issue_number < 1:
                issue_number = None
            return finish(
                3,
                "blocked",
                "decomposition_lease_not_acquired",
                issue_number,
            )
        lease_issue_number = lease.get("issue_number")
        if type(lease_issue_number) is not int or lease_issue_number < 1:
            raise RuntimeError("decomposition lease omitted its durable Issue identity")
        if prelease is not None and prelease.issue_number != lease_issue_number:
            raise RuntimeError("decomposition lease changed its durable Issue identity")
        known_issue_number = lease_issue_number
        lease_acquired = True
        if resume_phase is WorkflowPhase.DECOMPOSITION_APPLY:
            lease_retry_phase = WorkflowPhase.DECOMPOSITION_APPLY
            if prelease is None:
                raise RuntimeError("decomposition apply resume lost its durable Issue")
            result_code = _apply_approved_plan(
                args=args,
                source=source,
                source_head=source_head,
                service=service,
                claim_client=claim_client,
                prelease_snapshot=prelease,
            )
            return finish(
                result_code,
                "completed" if result_code == 0 else "blocked",
                "reviewed_decomposition_application",
                prelease.issue_number,
            )
        try:
            observation = _checkout_observation(
                source=source,
                task_id=task_id,
                service=service,
            )
            checkout = checkout_manager.prepare(observation)
        except DurableCheckoutError as exc:
            service.release_decomposition_lease(
                task_id=task_id,
                reason=(
                    "canonical decomposition checkout preparation failed before "
                    f"provider start: {type(exc).__name__}: {exc}"
                ),
            )
            return finish(
                3,
                "blocked",
                "decomposition_checkout_preparation_blocked",
                lease_issue_number,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            service.release_decomposition_lease(
                task_id=task_id,
                reason=(
                    "canonical decomposition checkout preparation failed with an "
                    f"operational error: {type(exc).__name__}: {exc}"
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
            return finish(
                3,
                "blocked",
                "decomposition_checkout_preparation_blocked",
                lease_issue_number,
            )
        result_code = _run_proposal(
            args=args,
            workspace=checkout_manager.checkout_path,
            output_root=output_root,
            source_head=source_head,
            service=service,
        )
        return finish(
            result_code,
            "human_action_required" if result_code == 0 else "blocked",
            "review_only_decomposition_handoff",
            lease_issue_number,
        )
    except (
        DurableCheckoutError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        release_error: Exception | None = None
        lease_released = False
        if service is not None and lease_acquired:
            try:
                lease_released = _release_owned_decomposition_lease(
                    service=service,
                    task_id=args.task_id,
                    worker_id=args.worker_id,
                    retry_phase=lease_retry_phase,
                    reason=(
                        "decomposition worker stopped after acquiring its durable "
                        f"lease: {type(exc).__name__}: {exc}"
                    ),
                )
            except (OSError, RuntimeError, ValueError) as cleanup_exc:
                release_error = cleanup_exc
        if (
            isinstance(exc, DecompositionApplyRetryableError)
            and lease_released
            and release_error is None
        ):
            print(f"Decomposition apply will retry: {exc}", file=sys.stderr)
            return finish(
                3,
                "blocked",
                "decomposition_apply_completion_retry",
            )
        print(f"Decomposition launcher blocked: {exc}", file=sys.stderr)
        if release_error is not None:
            print(
                "Decomposition launcher could not safely release its durable lease: "
                f"{release_error}",
                file=sys.stderr,
            )
        return finish(2, "error", "decomposition_launcher_exception")


if __name__ == "__main__":
    raise SystemExit(main())
