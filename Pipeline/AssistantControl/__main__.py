"""JSON commands used by the assistant; no commands launch work implicitly."""
import argparse
import json
import subprocess
import time
from pathlib import Path

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.inspect_project import inspect


def _wait_foreground_worker(manager, task_id: str, run_id: str,
                            process_identity: dict) -> dict:
    """Wait for exactly the launcher child and return its durable worker view."""
    from Pipeline.AssistantControl import worker_control

    stop_sent = False
    while True:
        try:
            observed = worker_control.status(manager, task_id)
            worker = observed.get("worker") or {}
            if (worker.get("task_id") != task_id or worker.get("run_id") != run_id
                    or worker.get("process_identity") != process_identity):
                raise ValueError("foreground worker identity changed; exact run retained for inspection")
            if observed.get("host_identity_alive") is False:
                return observed
            time.sleep(0.05)
        except KeyboardInterrupt:
            if stop_sent:
                raise
            worker_control.request_stop(manager, task_id, run_id=run_id)
            stop_sent = True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--checkout-root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="Read source and committed tasks; no admission claim")
    status.add_argument("--task")
    dependencies = commands.add_parser("dependencies", help="Read committed dependency delivery evidence")
    dependencies.add_argument("task")
    readiness = commands.add_parser(
        "readiness", help="Read dependency, checkout, capacity and resource readiness without reserving",
    )
    readiness.add_argument("task")
    readiness.add_argument("--capacity", type=int, default=1)
    readiness.add_argument("--allow-resource-overlap", action="store_true",
                           help="Preview manually authorized parallel file/scene work in separate task checkouts")
    viewer = commands.add_parser("viewer", help="Serve the existing graph as a read-only dashboard")
    viewer.add_argument("--port", type=int, default=8813)
    prepare = commands.add_parser("prepare", help="Create an isolated task project; does not start a worker")
    prepare.add_argument("task")
    prepare.add_argument("--source-commit", required=True, help="Exact HEAD from the previous inspection")
    refresh = commands.add_parser("refresh-prepared", help="Update a pristine, never-started task checkout to an inspected Source commit")
    refresh.add_argument("task")
    refresh.add_argument("--source-commit", required=True)
    checkout = commands.add_parser("checkout", help="Read an existing assistant-owned task checkout")
    checkout.add_argument("task")
    result = commands.add_parser(
        "inspect-result", help="Authenticate and summarize a retained crew result and patch",
    )
    result.add_argument("task")
    result.add_argument("--run-id", help="Exact assistant worker run; defaults to latest receipt")
    scope = commands.add_parser("scope", help="Validate an explicit scope; does not admit or launch work")
    scope.add_argument("task")
    scope.add_argument("--plan", type=Path, required=True, help="ExecutionScopePlan JSON file")
    scope.add_argument("--lease-id", required=True)
    candidate = commands.add_parser("candidate", help="Verify an existing crew result and commit it for human review; never launches a provider")
    candidate.add_argument("task")
    candidate.add_argument("--run-id", required=True)
    candidate.add_argument("--config", type=Path, required=True, help="The bridge configuration used by that crew")
    materialize = commands.add_parser(
        "materialize-candidate",
        help="Run the Door Prototype Unity builder and focused tests for one exact crew candidate",
    )
    materialize.add_argument("task")
    materialize.add_argument("--candidate-commit", required=True)
    materialize.add_argument("--unity-executable", type=Path)
    recover_materialization = commands.add_parser(
        "recover-nsc032-materialization",
        help="Archive the exact failed NSC-032 Unity output and reopen its original candidate",
    )
    recover_materialization.add_argument("task")
    recover_materialization.add_argument("--candidate-commit", required=True)
    recover_materialization.add_argument("--failure-sha256", required=True)
    refresh_recovered_index = commands.add_parser(
        "refresh-nsc032-recovered-index",
        help="Verify and refresh stale Git stat entries after exact NSC-032 recovery",
    )
    refresh_recovered_index.add_argument("task")
    refresh_recovered_index.add_argument("--candidate-commit", required=True)
    refresh_recovered_index.add_argument("--failure-sha256", required=True)
    recover_policy = commands.add_parser(
        "recover-nsc032-missing-validation-policy",
        help="Reclassify an exact retained NSC-032 missing-policy materialization without Unity",
    )
    recover_policy.add_argument("task")
    recover_policy.add_argument("--original-candidate", required=True)
    recover_policy.add_argument("--materialized-candidate", required=True)
    recover_policy.add_argument("--failed-journal-sha256", required=True)
    retry_validation = commands.add_parser(
        "retry-candidate-validation",
        help=(
            "Reopen one exact machine-validation failure after a bound "
            "AssistantControl host fix; never approves or materializes"
        ),
    )
    retry_validation.add_argument("task")
    retry_validation.add_argument("--candidate-commit", required=True)
    retry_validation.add_argument("--failed-validation-sha256", required=True)
    retry_validation.add_argument("--host-fix-commit", required=True)
    post_crew = commands.add_parser(
        "post-crew",
        help=(
            "Register a finished crew run's candidate and, if the task registers "
            "a Unity builder, materialize and validate it in one bounded step"
        ),
    )
    post_crew.add_argument("task")
    post_crew.add_argument("--run-id", required=True)
    post_crew.add_argument("--config", type=Path, required=True, help="The bridge configuration used by that crew")
    post_crew.add_argument("--unity-executable", type=Path)
    restored = commands.add_parser(
        "register-restored-candidate",
        help="Register a committed assistant-restored candidate for Vincent's review; no crew-review claim",
    )
    restored.add_argument("task")
    restored.add_argument("--base-commit", required=True)
    restored.add_argument("--candidate-commit", required=True)
    restored.add_argument("--candidate-tree", required=True)
    restored.add_argument("--task-contract-sha256", required=True)
    restored.add_argument("--changed-paths", type=Path, required=True)
    restored.add_argument("--evidence", type=Path, required=True)
    restored.add_argument("--reference-provenance", type=Path, required=True)
    reopen = commands.add_parser(
        "reopen-materialization",
        help=(
            "Dry-run (default) or --apply the return of ONE failed materialized "
            "candidate to needs_materialization, after proving a host fix "
            "landed since the failure. Not an approval path."
        ),
    )
    reopen.add_argument("task")
    reopen.add_argument("--candidate-commit", required=True,
                        help="The MATERIALIZED commit recorded on the failed candidate")
    reopen.add_argument("--failed-validation-sha256", required=True)
    reopen.add_argument("--host-fix-commit", required=True)
    reopen.add_argument("--apply", action="store_true",
                        help="Without this the command only reports what it would do")
    retry = commands.add_parser(
        "retry-materialization",
        help=(
            "Dry-run (default) or --apply another materialization attempt for ONE "
            "candidate whose ATTEMPT failed while the candidate itself stayed "
            "intact. Distinct from reopen-materialization, which restores a "
            "candidate that a failed validation replaced. Not an approval path."
        ),
    )
    retry.add_argument("task")
    retry.add_argument("--candidate-commit", required=True,
                       help="The intact crew-reviewed commit the failed attempt ran against")
    retry.add_argument("--failure-sha256", required=True,
                       help="Digest of the exact retained materialization_failure")
    retry.add_argument("--reason", required=True,
                       help=("Why another attempt is expected to behave differently. The "
                             "mechanical checks cannot establish that the blocker is gone, "
                             "so this is the evidence a later reader judges."))
    retry.add_argument("--apply", action="store_true",
                       help="Without this the command only reports what it would do")
    representation = commands.add_parser(
        "repair-checkout-representation",
        help=(
            "Dry-run (default) or --apply the restore of ONE tracked path that "
            "does not match its FILTERED checkout representation. Refuses unless "
            "it can prove the worktree holds no edit, which is what makes it safe "
            "where a bare git checkout is not."
        ),
    )
    representation.add_argument("task")
    representation.add_argument("--path", required=True,
                                help="One relative path inside the task checkout")
    representation.add_argument("--apply", action="store_true",
                                help="Without this the command only reports what it would do")
    on_source = commands.add_parser(
        "revise-on-source",
        help=(
            "Dry-run (default) or --apply the reconciliation of ONE rejected "
            "candidate with an inspected Source and an explicitly named contract. "
            "Publishes prepared with NO active candidate, for fresh crew work. "
            "Carries the implementation forward, never its validation authority."
        ),
    )
    on_source.add_argument("task")
    on_source.add_argument("--candidate-commit", required=True,
                           help="The rejected materialized commit")
    on_source.add_argument("--source-commit", required=True,
                           help="The Source commit you INSPECTED; must equal Source HEAD")
    on_source.add_argument("--accept-contract-sha256", required=True,
                           help=("The contract you are ADOPTING at that Source commit. "
                                 "Named, never inferred: carrying work across a changed "
                                 "task is a decision, not a side effect."))
    on_source.add_argument("--reason", required=True,
                           help="Why this work is worth carrying forward")
    on_source.add_argument("--apply", action="store_true",
                           help="Without this the command only reports what it would do")
    worker_status = commands.add_parser("worker-status", help="Inspect host identity and retained worker state")
    worker_status.add_argument("task")
    settlement = commands.add_parser("settle-worker", help="Release ended worker capacity after verified process/container exit")
    settlement.add_argument("task")
    settlement.add_argument("--run-id", required=True)
    reconcile = commands.add_parser(
        "reconcile-admission",
        help=(
            "Dry-run (default) or --apply the release of one admission "
            "reservation that no worker settlement can reach, after "
            "proving the run never launched or has ended"
        ),
    )
    reconcile.add_argument("task")
    reconcile.add_argument("--run-id")
    reconcile.add_argument("--lease-id")
    reconcile.add_argument("--apply", action="store_true")
    retire = commands.add_parser(
        "retire-worker",
        help="Archive one settled, dead failed/stopped worker so its task can be dispatched again",
    )
    retire.add_argument("task")
    retire.add_argument("--run-id", required=True)
    revision = commands.add_parser("revise", help="Reopen an explicitly rejected candidate without discarding its work")
    revision.add_argument("task")
    revision.add_argument("--candidate-commit", required=True)
    reset_task_cmd = commands.add_parser(
        "reset-task",
        help=(
            "Dry-run (default) or --apply a selective revert of one exact "
            "integrated task's own commits on a local no-remote "
            "gauntlet-replay/* branch, preserving every other task's work"
        ),
    )
    reset_task_cmd.add_argument("task")
    reset_task_cmd.add_argument("--apply", action="store_true")
    sync = commands.add_parser("sync-candidate", help="Merge an inspected Source commit into an approved candidate for fresh human testing; no provider or publication")
    sync.add_argument("task")
    sync.add_argument("--candidate-commit", required=True)
    sync.add_argument("--source-commit", required=True)
    stop = commands.add_parser("stop-worker", help="Request cooperative stop of one exact run; never deletes work")
    stop.add_argument("task")
    stop.add_argument("--run-id", required=True)
    stop.add_argument("--force", action="store_true", help="Terminate exact host and stop run-bound containers; preserve files")
    admission = commands.add_parser("reserve", help="Reserve capacity and resources; does not launch work")
    admission.add_argument("task")
    admission.add_argument("--run-id", required=True)
    admission.add_argument("--capacity", type=int, default=1)
    admission.add_argument("--allow-resource-overlap", action="store_true",
                           help="Authorize overlapping repository paths only in separate task checkouts of this checkout root")
    run = commands.add_parser("run-worker", aliases=["start-worker"], help="Run an authorized crew; start-worker launches it detached")
    run.add_argument("task")
    run.add_argument("--run-id", required=True)
    run.add_argument("--lease-id", required=True)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--authorize-provider-spend", action="store_true")
    decision = commands.add_parser("review", help="Record Vincent's explicit decision on the exact tested candidate")
    decision.add_argument("task")
    decision.add_argument("--tested-commit", required=True)
    decision.add_argument("--decision", choices=("approve", "reject"), required=True)
    decision.add_argument("--message", required=True)
    integration = commands.add_parser("integrate", help="Integrate only the exact approved candidate locally")
    integration.add_argument("task")
    integration.add_argument("--source-commit", required=True)
    integration.add_argument("--target-branch", required=True)
    publish = commands.add_parser(
        "publish-approved",
        help="Push one exact human-approved candidate and create or reuse its sole pull request",
    )
    publish.add_argument("task")
    publish.add_argument("--candidate-commit", required=True)
    publish.add_argument("--base-branch", default="main")
    publish.add_argument("--repo", help="Optional owner/repo assertion; must match Source origin")
    inspect_ci = commands.add_parser(
        "inspect-ci",
        help="Record pull-request checks only when its head is the exact approved candidate",
    )
    inspect_ci.add_argument("task")
    inspect_ci.add_argument("--candidate-commit", required=True)
    inspect_ci.add_argument("--base-branch", default="main")
    inspect_ci.add_argument("--repo", help="Optional owner/repo assertion; must match Source origin")
    archive = commands.add_parser("preserve-success", help="Keep an approved, integrated Unity project in SuccessfullTasks")
    archive.add_argument("task")
    archive.add_argument("--success-root", type=Path, default=Path("C:/NSC/SuccessfullTasks"))
    decompose = commands.add_parser("decompose", help="Run one bounded two-role decomposition proposal; no graph mutation")
    decompose.add_argument("task")
    decompose.add_argument("--run-id", required=True)
    decompose.add_argument("--providers", default="claude,codex")
    decompose.add_argument("--compose-project", default="nosafecircle")
    decompose.add_argument("--authorize-provider-spend", action="store_true")
    decompose.add_argument(
        "--max-calls", type=int, choices=(2, 3), default=2,
        help="Review-call budget; 3 (two distinct providers only) lets an independent PASS approve a reviewer revision")
    decompose.add_argument(
        "--author-checklist", choices=("parent-contract-v1",),
        help="Opt-in author checklist for the author, correction and reviewer; omit for unchanged prompts")
    inspect_decomposition = commands.add_parser("inspect-decomposition", help="Recheck the exact retained decomposition review")
    inspect_decomposition.add_argument("task")
    diagnose_decomposition = commands.add_parser(
        "diagnose-decomposition", help="Explain why one retained decomposition run stopped; read-only, never retries")
    diagnose_decomposition.add_argument("task")
    diagnose_decomposition.add_argument("--run-id", required=True)
    diagnose_decomposition.add_argument(
        "--ger-packet", type=Path,
        help="For a CONTRACT diagnosis, write GER_PROBLEM.md and MANIFEST.json into this new directory")
    apply_decomposition = commands.add_parser("apply-decomposition", help="Apply one exact reviewed decomposition locally; never pushes")
    apply_decomposition.add_argument("task")
    apply_decomposition.add_argument("--run-id", required=True)
    apply_decomposition.add_argument("--source-commit", required=True)
    apply_decomposition.add_argument("--target-branch", required=True)
    graph_plan = commands.add_parser(
        "graph-plan", help="Show the next bounded graph actions without mutating or starting providers",
    )
    graph_plan.add_argument("--task", action="append", required=True,
                            help="Target task; repeat for a bounded graph")
    graph_plan.add_argument("--human-review-task", action="append", default=[])
    graph_plan.add_argument("--auto-approve-gauntlet", action="store_true")
    graph_plan.add_argument("--capacity", type=int, default=1)
    graph_plan.add_argument("--target-branch")
    graph_plan.add_argument("--scope-dir", type=Path)
    graph_preflight = commands.add_parser(
        "graph-preflight",
        help="Persist an exact read-only graph plan required before run-graph",
    )
    graph_preflight.add_argument("--task", action="append", required=True,
                                 help="Execution target; repeat for a bounded graph")
    graph_preflight.add_argument("--human-review-task", action="append", default=[])
    graph_preflight.add_argument("--auto-approve-gauntlet", action="store_true")
    graph_preflight.add_argument("--capacity", type=int, default=1)
    graph_preflight.add_argument("--target-branch")
    graph_preflight.add_argument("--scope-dir", type=Path)
    graph_preflight.add_argument("--worker-config", type=Path)
    graph_preflight.add_argument("--providers", default="claude,codex")
    graph_preflight.add_argument("--compose-project", default="nosafecircle")
    graph_preflight.add_argument("--authorize-provider-spend", action="store_true")
    run_graph = commands.add_parser(
        "run-graph", help="Resume the bounded local graph until complete, blocked, or awaiting human review",
    )
    run_graph.add_argument("--task", action="append", required=True,
                           help="Target task; repeat for a bounded graph")
    run_graph.add_argument(
        "--worker-config", type=Path,
        help="Required for normal execution; optional in --delegate-safe mode",
    )
    maintenance_plan = commands.add_parser("maintenance-plan", help="Create one authenticated bounded maintenance ticket")
    maintenance_plan.add_argument("task")
    maintenance_plan.add_argument("--action", required=True,
                                   choices=("inspect-worker", "verify-candidate", "settle-worker", "cleanup-worker-docker"))
    maintenance_plan.add_argument("--run-id", required=True)
    maintenance_run = commands.add_parser("maintenance-run", help="Run one owned maintenance ticket")
    maintenance_run.add_argument("ticket", type=Path)
    run_graph.add_argument("--human-review-task", action="append", default=[])
    run_graph.add_argument("--auto-approve-gauntlet", action="store_true")
    run_graph.add_argument("--authorize-provider-spend", action="store_true")
    run_graph.add_argument("--capacity", type=int, default=1)
    run_graph.add_argument("--target-branch")
    run_graph.add_argument("--scope-dir", type=Path)
    run_graph.add_argument("--providers", default="claude,codex")
    run_graph.add_argument("--compose-project", default="nosafecircle")
    run_graph.add_argument("--max-actions", type=int, default=100)
    run_graph.add_argument("--once", action="store_true",
                           help="Perform at most one durable graph transition")
    run_graph.add_argument(
        "--delegate-safe", action="store_true",
        help="Permit only bounded non-provider, non-approval, non-integration transitions",
    )
    for graph_parser in (graph_plan, graph_preflight, run_graph):
        graph_parser.add_argument(
            "--background-jobs", type=int, default=4,
            help="Maximum concurrent owned background jobs (decomposition, post-crew validation)",
        )
    clear_job = commands.add_parser(
        "clear-background-job",
        help="Archive one ended background job index so the graph may launch a fresh ticket",
    )
    clear_job.add_argument("task")
    clear_job.add_argument("--job-id", required=True)
    stop_jobs = commands.add_parser(
        "stop-background-jobs",
        help=(
            "Recovery after the controller process was lost: stop every exact owned "
            "decomposition or post-crew child (bound stop request, bounded grace, then "
            "its recorded Job Object tree); refuses while a graph controller is running"
        ),
    )
    stop_jobs.add_argument("--grace-seconds", type=float, default=15.0)
    stop_graph = commands.add_parser(
        "stop-graph",
        help=(
            "Ask the running graph controller to stop: it cancels its background jobs "
            "(bound stop request, bounded grace, exact Job Object trees) and returns "
            "status stopped; refuses when no controller owns the graph"
        ),
    )
    stop_graph.add_argument("--reason", default="operator requested graph stop")
    stop_graph.add_argument("--grace-seconds", type=float, default=15.0)
    stop_graph.add_argument("--wait-seconds", type=float, default=120.0)
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            result = inspect(args.source, args.task)
        elif args.command == "dependencies":
            from Pipeline.AssistantControl.dependencies import inspect_dependencies
            result = inspect_dependencies(args.source, args.task, args.checkout_root)
        else:
            if args.checkout_root is None:
                raise ValueError("Specify --checkout-root outside the source project")
            manager = Checkouts(args.source, args.checkout_root)
            if args.command == "maintenance-plan":
                from Pipeline.AssistantControl.maintenance import MaintenanceExecutor
                result = MaintenanceExecutor(manager).plan(args.task, args.action, run_id=args.run_id)
                print(json.dumps(result, indent=2)); return 0
            if args.command == "maintenance-run":
                from Pipeline.AssistantControl.maintenance import MaintenanceExecutor
                result = MaintenanceExecutor(manager).run(args.ticket)
                print(json.dumps(result, indent=2)); return 0
            if args.command == "viewer":
                from Pipeline.AssistantControl.viewer import make_server
                server = make_server(args.source, args.checkout_root, args.port)
                print(json.dumps({"viewer_url": f"http://127.0.0.1:{server.server_port}/", "read_only": True}), flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
                finally:
                    server.server_close()
                return 0
            if args.command in {"graph-plan", "graph-preflight", "run-graph"}:
                from Pipeline.AssistantControl.graph_controller import (
                    DELEGATE_SAFE_ACTIONS,
                    GraphController,
                    GraphPolicy,
                )
                human = frozenset({"NSC-042", *args.human_review_task})
                policy = GraphPolicy(
                    targets=tuple(dict.fromkeys(args.task)),
                    human_review_tasks=human,
                    auto_approve_gauntlet=args.auto_approve_gauntlet,
                    capacity=args.capacity,
                    target_branch=args.target_branch,
                    scope_dir=args.scope_dir,
                    decomposition_providers=getattr(args, "providers", "claude,codex"),
                    compose_project=getattr(args, "compose_project", "nosafecircle"),
                    background_job_limit=args.background_jobs,
                )
                config = {}
                if args.command in {"graph-preflight", "run-graph"}:
                    if getattr(args, "delegate_safe", False) and args.authorize_provider_spend:
                        raise ValueError(
                            "--delegate-safe cannot be combined with --authorize-provider-spend"
                        )
                    if args.worker_config is None:
                        if args.command == "run-graph" and not args.delegate_safe:
                            raise ValueError(
                                "run-graph requires --worker-config unless --delegate-safe is used"
                            )
                    else:
                        config = json.loads(args.worker_config.read_text(encoding="utf-8-sig"))
                        if not isinstance(config, dict):
                            raise ValueError("Worker configuration must be a JSON object")
                controller = GraphController(
                    manager, policy, config,
                    execution_authorized=(
                        args.command in {"graph-preflight", "run-graph"}
                        and args.authorize_provider_spend
                        and not getattr(args, "delegate_safe", False)
                    ),
                    require_preflight=args.command == "run-graph",
                )
                if args.command == "graph-plan":
                    result = controller.plan()
                elif args.command == "graph-preflight":
                    result = controller.persist_preflight()
                else:
                    result = controller.run(
                        max_actions=1 if args.once else args.max_actions,
                        allowed_actions=(DELEGATE_SAFE_ACTIONS if args.delegate_safe else None),
                    )
                print(json.dumps(result, indent=2))
                return 0 if result.get("status") not in {"blocked", "command_failed"} else 1
            if args.command == "stop-graph":
                from Pipeline.AssistantControl.graph_controller import request_stop
                result = request_stop(
                    manager, reason=args.reason, grace_seconds=args.grace_seconds,
                    wait_seconds=args.wait_seconds,
                )
                print(json.dumps(result, indent=2))
                return 0 if result.get("status") in {"stopped", "stop_requested", "already_released"} else 1
            if args.command == "stop-background-jobs":
                from Pipeline.AssistantControl import background_jobs
                from Pipeline.TaskReviewAgent.execution_session_pool import (
                    _acquire_liveness_lock,
                    _release_liveness_lock,
                )
                manager.records.mkdir(parents=True, exist_ok=True)
                try:
                    held = _acquire_liveness_lock(manager.records / "graph-controller.lock")
                except (BlockingIOError, PermissionError) as exc:
                    raise ValueError(
                        "a graph controller owns these jobs; interrupt it instead of "
                        "stopping its jobs underneath it"
                    ) from exc
                try:
                    # Finalize: wait each container's tombstone out (bounded, about a
                    # minute) and record the final recheck, so `stopped` means done.
                    stopped = background_jobs.cancel_all(
                        manager, host=background_jobs.DetachedHost(),
                        reason="operator requested background-job stop",
                        grace_seconds=args.grace_seconds, finalize=True,
                    )
                finally:
                    _release_liveness_lock(held)
                failed = [item for item in stopped if item.get("status") in {"stop_failed", "running"}]
                pending = [item for item in stopped if item.get("cleanup_pending")]
                unreadable = [item for item in stopped if item.get("status") == "unreadable_index"]
                # Stopped is claimed only once every exact provider container is
                # verified absent and every index can be authenticated; a pending
                # cleanup is retried by running again, an unreadable index is an
                # operator repair (nothing here deletes or rewrites one).
                status = "stop_failed" if failed else ("cleanup_pending" if pending else "stopped")
                result = {"status": status, "jobs": stopped,
                          "cleanup_pending": [item.get("task_id") for item in pending],
                          "retry_after_utc": [item.get("retry_after_utc") for item in pending],
                          "unreadable_indexes": [
                              {"task_id": item.get("task_id"), "path": item.get("path"),
                               "error": item.get("error")} for item in unreadable]}
                print(json.dumps(result, indent=2))
                return 0 if status == "stopped" else 1
            if args.command == "clear-background-job":
                from Pipeline.AssistantControl import background_jobs
                result = background_jobs.clear(
                    manager, args.task, job_id=args.job_id, host=background_jobs.DetachedHost(),
                )
            elif args.command == "readiness":
                from Pipeline.AssistantControl.readiness import inspect_readiness
                result = inspect_readiness(
                    manager, args.task, capacity=args.capacity,
                    allow_resource_overlap=args.allow_resource_overlap,
                )
            elif args.command == "prepare":
                result = manager.prepare(args.task, expected_commit=args.source_commit)
            elif args.command == "checkout":
                result = manager.observe(args.task)
            elif args.command == "inspect-result":
                from Pipeline.AssistantControl.result_inspection import inspect_result
                result = inspect_result(
                    manager, args.task, assistant_run_id=args.run_id,
                )
            elif args.command == "scope":
                from Pipeline.AssistantControl.scope import AssistantScopePlanner
                plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
                result = AssistantScopePlanner(manager).validate_and_persist(
                    args.task, plan, lease_id=args.lease_id)
            elif args.command == "candidate":
                from Pipeline.AssistantControl.candidate import register_candidate
                config = json.loads(args.config.read_text(encoding="utf-8-sig"))
                if not isinstance(config, dict):
                    raise ValueError("Candidate configuration must be a JSON object")
                result = register_candidate(manager, args.task, args.run_id, config)
            elif args.command == "materialize-candidate":
                from Pipeline.AssistantControl.unity_materialization import materialize_candidate
                result = materialize_candidate(
                    manager, args.task, args.candidate_commit,
                    unity_executable=args.unity_executable,
                )
            elif args.command == "recover-nsc032-materialization":
                from Pipeline.AssistantControl.materialization_recovery import (
                    reopen_failed_nsc032_materialization,
                )
                result = reopen_failed_nsc032_materialization(
                    manager, args.task, expected_candidate=args.candidate_commit,
                    expected_failure_sha256=args.failure_sha256,
                )
            elif args.command == "refresh-nsc032-recovered-index":
                from Pipeline.AssistantControl.materialization_recovery import (
                    refresh_recovered_nsc032_index,
                )
                result = refresh_recovered_nsc032_index(
                    manager, args.task, expected_candidate=args.candidate_commit,
                    expected_failure_sha256=args.failure_sha256,
                )
            elif args.command == "recover-nsc032-missing-validation-policy":
                from Pipeline.AssistantControl.materialization_policy_recovery import (
                    recover_nsc032_missing_validation_policy,
                )
                result = recover_nsc032_missing_validation_policy(
                    manager, args.task,
                    original_candidate=args.original_candidate,
                    materialized_candidate=args.materialized_candidate,
                    failed_journal_sha256=args.failed_journal_sha256,
                )
            elif args.command == "retry-candidate-validation":
                from Pipeline.AssistantControl.candidate_validation_retry import (
                    reopen_candidate_validation,
                )
                result = reopen_candidate_validation(
                    manager,
                    args.task,
                    expected_candidate=args.candidate_commit,
                    expected_failure_sha256=args.failed_validation_sha256,
                    host_fix_commit=args.host_fix_commit,
                )
            elif args.command == "post-crew":
                from Pipeline.AssistantControl.post_crew_workflow import run_post_crew_workflow
                config = json.loads(args.config.read_text(encoding="utf-8-sig"))
                if not isinstance(config, dict):
                    raise ValueError("Candidate configuration must be a JSON object")
                result = run_post_crew_workflow(
                    manager, args.task, args.run_id, config,
                    unity_executable=args.unity_executable,
                )
            elif args.command == "register-restored-candidate":
                from Pipeline.AssistantControl.assistant_restored_candidate import (
                    register_assistant_restored_candidate,
                )
                result = register_assistant_restored_candidate(
                    manager,
                    args.task,
                    base_commit=args.base_commit,
                    candidate_commit=args.candidate_commit,
                    candidate_tree=args.candidate_tree,
                    task_contract_sha256=args.task_contract_sha256,
                    changed_paths=json.loads(args.changed_paths.read_text(encoding="utf-8-sig")),
                    evidence=json.loads(args.evidence.read_text(encoding="utf-8-sig")),
                    reference_provenance=json.loads(
                        args.reference_provenance.read_text(encoding="utf-8-sig")
                    ),
                )
            elif args.command == "reopen-materialization":
                from Pipeline.AssistantControl.materialization_reopen import (
                    reopen_materialization,
                )
                result = reopen_materialization(
                    manager,
                    args.task,
                    expected_candidate=args.candidate_commit,
                    expected_failure_sha256=args.failed_validation_sha256,
                    host_fix_commit=args.host_fix_commit,
                    apply=args.apply,
                )
            elif args.command == "retry-materialization":
                from Pipeline.AssistantControl.materialization_retry import (
                    retry_materialization,
                )
                result = retry_materialization(
                    manager,
                    args.task,
                    expected_candidate=args.candidate_commit,
                    expected_failure_sha256=args.failure_sha256,
                    reason=args.reason,
                    apply=args.apply,
                )
            elif args.command == "repair-checkout-representation":
                from Pipeline.AssistantControl.checkout_representation import (
                    repair_checkout_representation,
                )
                result = repair_checkout_representation(
                    manager, args.task, path=args.path, apply=args.apply,
                )
            elif args.command == "revise-on-source":
                from Pipeline.AssistantControl.revise_on_source import revise_on_source
                result = revise_on_source(
                    manager,
                    args.task,
                    expected_candidate=args.candidate_commit,
                    expected_source_commit=args.source_commit,
                    accept_contract_sha256=args.accept_contract_sha256,
                    reason=args.reason,
                    apply=args.apply,
                )
            elif args.command == "refresh-prepared":
                from Pipeline.AssistantControl.prepared_refresh import refresh_prepared
                result = refresh_prepared(manager, args.task, expected_source_commit=args.source_commit)
            elif args.command in {"worker-status", "stop-worker"}:
                from Pipeline.AssistantControl import worker_control
                result = (worker_control.status(manager, args.task) if args.command == "worker-status"
                          else (worker_control.force_stop(manager, args.task, run_id=args.run_id) if args.force
                                else worker_control.request_stop(manager, args.task, run_id=args.run_id)))
            elif args.command == "reserve":
                from Pipeline.AssistantControl.admission import reserve
                result = reserve(
                    manager, args.task, args.run_id, capacity=args.capacity,
                    allow_resource_overlap=args.allow_resource_overlap,
                )
            elif args.command == "settle-worker":
                from Pipeline.AssistantControl.worker_settlement import settle_completed
                result = settle_completed(manager, args.task, run_id=args.run_id)
            elif args.command == "reconcile-admission":
                from Pipeline.AssistantControl.admission_reconciliation import (
                    reconcile_admission)
                result = reconcile_admission(
                    manager, args.task, run_id=args.run_id,
                    lease_id=args.lease_id, apply=args.apply)
            elif args.command == "retire-worker":
                from Pipeline.AssistantControl import worker_control as _worker_control
                result = _worker_control.retire_settled_worker(manager, args.task, run_id=args.run_id)
            elif args.command == "revise":
                from Pipeline.AssistantControl.revisions import begin_revision
                result = begin_revision(manager, args.task, expected_candidate=args.candidate_commit)
            elif args.command == "reset-task":
                from Pipeline.AssistantControl.reset_task import reset_task
                result = reset_task(manager, args.task, apply=args.apply)
            elif args.command == "sync-candidate":
                from Pipeline.AssistantControl.source_update import synchronize_candidate
                result = synchronize_candidate(manager, args.task,
                                               expected_candidate=args.candidate_commit,
                                               expected_source_commit=args.source_commit)
            elif args.command in {"run-worker", "start-worker"}:
                if not args.authorize_provider_spend:
                    raise ValueError("Explicit provider-spend authorization is required; no worker started")
                config = json.loads(args.config.read_text(encoding="utf-8-sig"))
                if not isinstance(config, dict):
                    raise ValueError("Worker configuration must be a JSON object")
                config["execution_authorized"] = True
                if args.command == "start-worker":
                    from Pipeline.AssistantControl.worker_launcher import start
                    result = start(manager, args.task, args.run_id, args.lease_id, config,
                                   execution_authorized=True)
                else:
                    from Pipeline.AssistantControl.worker_launcher import start
                    started = start(manager, args.task, args.run_id, args.lease_id, config,
                                    execution_authorized=True)
                    if (started.get("task_id") != args.task
                            or started.get("run_id") != args.run_id):
                        raise ValueError("foreground launcher returned a different task or run")
                    identity = started.get("process_identity")
                    if not isinstance(identity, dict):
                        raise ValueError("foreground launcher returned no exact child identity")
                    observed = _wait_foreground_worker(
                        manager, args.task, args.run_id, identity)
                    result = {**started, "worker": observed.get("worker"),
                              "worker_status": observed}
            elif args.command == "preserve-success":
                from Pipeline.AssistantControl.successful_tasks import preserve_success
                result = preserve_success(manager, args.task, args.success_root)
            elif args.command in {"publish-approved", "inspect-ci"}:
                from Pipeline.AssistantControl.publication import PublicationAdapter
                publication = PublicationAdapter(manager)
                values = {
                    "candidate_commit": args.candidate_commit,
                    "base_branch": args.base_branch,
                    "repository": args.repo,
                }
                result = (
                    publication.publish_approved(args.task, **values)
                    if args.command == "publish-approved"
                    else publication.inspect_ci(args.task, **values)
                )
            elif args.command == "diagnose-decomposition":
                from Pipeline.AssistantControl import decomposition_diagnosis
                result = decomposition_diagnosis.diagnose(
                    manager, args.task, run_id=args.run_id, ger_packet=args.ger_packet)
            elif args.command in {"decompose", "inspect-decomposition", "apply-decomposition"}:
                from Pipeline.AssistantControl import decomposition
                if args.command == "decompose":
                    result = decomposition.run(
                        manager, args.task, args.run_id,
                        providers=args.providers,
                        compose_project=args.compose_project,
                        execution_authorized=args.authorize_provider_spend,
                        author_checklist=args.author_checklist,
                        max_calls=args.max_calls,
                    )
                elif args.command == "inspect-decomposition":
                    result = decomposition.inspect(manager, args.task)
                else:
                    result = decomposition.apply(
                        manager, args.task,
                        run_id=args.run_id,
                        expected_source_commit=args.source_commit,
                        target_branch=args.target_branch,
                    )
            else:
                from Pipeline.AssistantControl.review import ReviewGate
                gate = ReviewGate(manager)
                if args.command == "review":
                    result = gate.decide(args.task, tested_commit=args.tested_commit,
                                         decision=args.decision, message=args.message)
                else:
                    result = gate.integrate(args.task, expected_source_commit=args.source_commit,
                                            target_branch=args.target_branch)
        print(json.dumps(result, indent=2))
        if args.command == "run-worker" and (result.get("worker") or {}).get("status") != "succeeded":
            return 1
        if args.command == "decompose" and result.get("status") != "review_ready":
            return 1
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "command_failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
