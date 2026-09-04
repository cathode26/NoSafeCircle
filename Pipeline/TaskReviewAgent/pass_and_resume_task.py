#!/usr/bin/env python3
"""Record exact human approval, await GitHub, and resume the correct worker."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import TaskReviewContractError, validate_task_id  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowActor,
    WorkflowPhase,
    WorkflowState,
    WorkflowEventType,
)
from Pipeline.TaskReviewAgent.polling_orchestrator import (  # noqa: E402
    build_decomposition_worker_command,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowSnapshot,
    IssueWorkflowStoreError,
    VINCENT_INBOX_TITLE,
)
from Pipeline.TaskReviewAgent.human_action_wait import publish_resume_hint  # noqa: E402
from Pipeline.TaskReviewAgent.safe_unity_churn import (  # noqa: E402
    classify_safe_post_unity_churn,
)

SHA40 = re.compile(r"^[0-9a-f]{40}$")


class PassAndResumeError(RuntimeError):
    """Raised when exact-commit PASS automation cannot proceed safely."""


def _run_text(args: tuple[str, ...], *, cwd: Path, timeout: float = 60.0) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0:
        raise PassAndResumeError(
            f"command failed ({result.returncode}): {' '.join(args)}\n{stdout}\n{stderr}"
        )
    return stdout.strip()


def _repo_root(source: Path) -> Path:
    value = _run_text(
        ("git", "-C", str(source), "rev-parse", "--show-toplevel"),
        cwd=source,
    )
    root = Path(value).resolve()
    if not (root / "Pipeline" / "TaskReviewAgent" / "Start-GameTaskAgent.ps1").is_file():
        raise PassAndResumeError("source does not contain the canonical Game Task Agent launcher")
    return root


def _authenticated_human_login(root: Path) -> str:
    """Resolve the GitHub identity whose explicit human result is being recorded."""

    login = _run_text(("gh", "api", "user", "--jq", ".login"), cwd=root)
    if not login:
        raise PassAndResumeError("GitHub CLI did not return an authenticated login")
    return login


def _apply_canonical_human_transition(
    service: IssueWorkflowService,
    *,
    task_id: str,
    body: str,
    actor_id: str,
    approve_decomposition: bool,
) -> None:
    """Advance body, state label, and hashed event through the canonical service."""

    if approve_decomposition:
        service.apply_decomposition_result(
            task_id=task_id,
            result_body=body,
            actor_id=actor_id,
        )
    else:
        service.apply_human_result(
            task_id=task_id,
            result_body=body,
            actor_id=actor_id,
        )


def _stable_status(checkout: Path) -> str:
    """Read raw porcelain after a bounded filesystem settling window."""

    previous: str | None = None
    stable = 0
    for _ in range(20):
        result = subprocess.run(
            (
                "git",
                "-C",
                str(checkout),
                "-c",
                "core.quotepath=false",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ),
            cwd=str(checkout),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60.0,
        )
        if result.returncode != 0:
            raise PassAndResumeError(
                "could not read checkout status: "
                + result.stderr.decode("utf-8", errors="replace").strip()
            )
        current = result.stdout.decode("utf-8", errors="strict").rstrip("\r\n")
        if previous is not None and current == previous:
            stable += 1
        else:
            previous = current
            stable = 1
        if stable >= 4:
            return current
        time.sleep(0.5)
    raise PassAndResumeError("checkout status did not become stable after Unity exited")


def _recover_safe_unity_churn(
    checkout: Path,
    tested_commit: str,
    *,
    apply: bool = True,
) -> tuple[str, ...]:
    raw_status = _stable_status(checkout)
    if not raw_status:
        return ()
    paths = classify_safe_post_unity_churn(raw_status, checkout)
    if paths is None or not paths:
        raise PassAndResumeError("checkout has uncommitted or untracked changes")
    if not apply:
        return paths
    _run_text(
        (
            "git",
            "-C",
            str(checkout),
            "restore",
            f"--source={tested_commit}",
            "--worktree",
            "--",
            *paths,
        ),
        cwd=checkout,
    )
    if _stable_status(checkout):
        raise PassAndResumeError(
            "checkout remained dirty after exact safe Unity churn recovery"
        )
    return paths


def _validate_handoff(
    snapshot: IssueWorkflowSnapshot,
    *,
    task_id: str,
    tested_commit: str,
    checkout_root: Path,
    apply_recovery: bool,
) -> Path:
    if not snapshot.managed or not snapshot.valid or snapshot.state is None:
        reasons = "; ".join(snapshot.reasons) or "managed workflow state is unavailable"
        raise PassAndResumeError(f"Issue is not a valid managed workflow: {reasons}")
    state = snapshot.state
    if state.task_id != task_id:
        raise PassAndResumeError("Issue task identity differs from the requested task")
    if state.state is not WorkflowState.HUMAN_ACTION_REQUIRED:
        raise PassAndResumeError(
            f"Issue is {state.state.value}, not human_action_required"
        )
    if state.phase is not WorkflowPhase.UNITY_RUNTIME_VALIDATION:
        raise PassAndResumeError(
            f"Issue phase is {state.phase.value}, not unity_runtime_validation"
        )
    if state.current_actor is not WorkflowActor.HUMAN:
        raise PassAndResumeError("Issue is not currently owned by the human validator")
    if state.head_commit != tested_commit or state.human_handoff_commit != tested_commit:
        raise PassAndResumeError(
            "tested commit does not equal both the Issue head and human handoff commit"
        )
    if state.checkout_path is None:
        raise PassAndResumeError("Issue does not record a checkout path")
    checkout = Path(state.checkout_path).resolve()
    root = checkout_root.resolve()
    if checkout.parent != root:
        raise PassAndResumeError(
            f"Issue checkout {checkout} is not a direct child of checkout root {root}"
        )
    if not checkout.is_dir():
        raise PassAndResumeError(f"Issue checkout does not exist: {checkout}")
    local_head = _run_text(("git", "-C", str(checkout), "rev-parse", "HEAD"), cwd=checkout)
    if local_head != tested_commit:
        raise PassAndResumeError(
            f"checkout HEAD {local_head!r} differs from tested commit {tested_commit!r}"
        )
    _recover_safe_unity_churn(checkout, tested_commit, apply=apply_recovery)
    remote_head = _run_text(
        ("git", "-C", str(checkout), "rev-parse", "@{upstream}"), cwd=checkout
    )
    if remote_head != tested_commit:
        raise PassAndResumeError(
            f"remote-tracking task branch {remote_head!r} differs from tested commit"
        )
    return checkout


def _pass_comment(tested_commit: str, notes: str) -> str:
    return "\n".join(
        (
            "## Human validation result",
            "",
            "Result: PASS",
            f"Tested commit: `{tested_commit}`",
            "",
            "Completed steps:",
            "- Completed every step in the managed Issue's exact Unity checklist.",
            "",
            "Notes:",
            notes,
        )
    )


def _decomposition_comment(plan_id: str, notes: str) -> str:
    return "\n".join(
        (
            "## Decomposition application result",
            "",
            "Result: APPROVE",
            f"Reviewed plan_id: {plan_id}",
            "",
            "Notes:",
            notes,
        )
    )


def _decomposition_plan_id(snapshot: IssueWorkflowSnapshot) -> str:
    if not snapshot.managed or not snapshot.valid or snapshot.state is None:
        raise PassAndResumeError("Issue is not a valid managed decomposition workflow")
    state = snapshot.state
    waiting = (
        state.state is WorkflowState.HUMAN_ACTION_REQUIRED
        and state.phase is WorkflowPhase.DECOMPOSITION_APPLY_AUTHORIZATION
        and state.current_actor is WorkflowActor.HUMAN
    )
    ready = (
        state.state is WorkflowState.AGENT_READY
        and state.phase is WorkflowPhase.DECOMPOSITION_APPLY
        and state.current_actor is WorkflowActor.AGENT
    )
    if not waiting and not ready:
        raise PassAndResumeError(
            "Issue is neither waiting for decomposition authorization nor ready "
            "to apply its approved plan"
        )
    handoffs = [
        event
        for event in snapshot.events
        if event.event_type is WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED
    ]
    if not handoffs:
        raise PassAndResumeError("decomposition workflow has no durable plan handoff")
    plan_id = handoffs[-1].details.get("graph_delta_plan_id")
    if type(plan_id) is not str or re.fullmatch(r"GDP-[0-9a-f]{64}", plan_id) is None:
        raise PassAndResumeError("decomposition handoff plan_id is invalid")
    return plan_id


def _ready_for_decomposition_apply(
    snapshot: IssueWorkflowSnapshot, plan_id: str
) -> bool:
    if not snapshot.managed or not snapshot.valid or snapshot.state is None:
        return False
    state = snapshot.state
    approvals = [
        event
        for event in snapshot.events
        if event.event_type is WorkflowEventType.DECOMPOSITION_APPLICATION_APPROVED
    ]
    return (
        state.state is WorkflowState.AGENT_READY
        and state.phase is WorkflowPhase.DECOMPOSITION_APPLY
        and state.current_actor is WorkflowActor.AGENT
        and bool(approvals)
        and approvals[-1].details.get("reviewed_plan_id") == plan_id
        and "nsc-state:agent-ready" in snapshot.labels
    )


def _ready_for_delivery(snapshot: IssueWorkflowSnapshot, tested_commit: str) -> bool:
    if not snapshot.managed or not snapshot.valid or snapshot.state is None:
        return False
    state = snapshot.state
    return (
        state.state is WorkflowState.AGENT_READY
        and state.phase is WorkflowPhase.DELIVERY_EVIDENCE
        and state.current_actor is WorkflowActor.AGENT
        and state.head_commit == tested_commit
        and state.human_handoff_commit == tested_commit
        and state.human_result == "pass"
        and state.state_version == len(snapshot.events)
        and "nsc-state:agent-ready" in snapshot.labels
    )


def _wait_for_delivery_ready(
    service: IssueWorkflowService,
    task_id: str,
    tested_commit: str,
    *,
    timeout_seconds: float,
    poll_seconds: float,
) -> IssueWorkflowSnapshot:
    deadline = time.monotonic() + timeout_seconds
    last_status = "GitHub workflow has not been observed"
    while time.monotonic() <= deadline:
        snapshot = service.find(task_id)
        if snapshot is None:
            raise PassAndResumeError("managed Issue disappeared while waiting for GitHub")
        if _ready_for_delivery(snapshot, tested_commit):
            return snapshot
        state = snapshot.state
        last_status = (
            f"valid={snapshot.valid}, labels={list(snapshot.labels)}, "
            f"state={state.state.value if state else None}, "
            f"phase={state.phase.value if state else None}, "
            f"version={state.state_version if state else None}, events={len(snapshot.events)}, "
            f"reasons={list(snapshot.reasons)}"
        )
        time.sleep(poll_seconds)
    raise PassAndResumeError(
        f"timed out waiting for agent_ready / delivery_evidence: {last_status}"
    )


def _wait_for_decomposition_ready(
    service: IssueWorkflowService,
    task_id: str,
    plan_id: str,
    *,
    timeout_seconds: float,
    poll_seconds: float,
) -> IssueWorkflowSnapshot:
    deadline = time.monotonic() + timeout_seconds
    last_status = "GitHub workflow has not been observed"
    while time.monotonic() <= deadline:
        snapshot = service.find(task_id)
        if snapshot is None:
            raise PassAndResumeError("managed Issue disappeared while waiting for GitHub")
        if _ready_for_decomposition_apply(snapshot, plan_id):
            return snapshot
        state = snapshot.state
        last_status = (
            f"valid={snapshot.valid}, state={state.state.value if state else None}, "
            f"phase={state.phase.value if state else None}, reasons={list(snapshot.reasons)}"
        )
        time.sleep(poll_seconds)
    raise PassAndResumeError(
        f"timed out waiting for agent_ready / decomposition_apply: {last_status}"
    )


def _poke_waiting_game_task_launcher(
    root: Path,
    *,
    task_id: str,
    snapshot: IssueWorkflowSnapshot,
) -> Path | None:
    """Best-effort wake-up after GitHub is already authoritative and consistent."""

    state = snapshot.state
    if state is None:
        return None
    try:
        return publish_resume_hint(
            root,
            task_id=task_id,
            human_handoff_commit=str(state.human_handoff_commit),
            state_version=state.state_version,
            event_id=str(state.last_event_id),
        )
    except (OSError, TaskReviewContractError, ValueError) as exc:
        print(
            "PASS AND RESUME: WARNING\n"
            f"GitHub is agent_ready, but the local launcher poke failed: {exc}\n"
            "The launcher's one-minute GitHub poll remains active.",
            file=sys.stderr,
        )
        return None


def _clear_vincent_notification(
    service: IssueWorkflowService,
    *,
    task_id: str,
) -> str:
    """Clean the exact inbox notification without blocking an approved task."""

    try:
        return service.clear_vincent_notification(task_id)
    except (IssueWorkflowStoreError, OSError, subprocess.TimeoutExpired) as exc:
        print(
            "PASS AND RESUME: WARNING\n"
            f"GitHub is agent_ready, but its NSC-Vincent notification was not removed: {exc}",
            file=sys.stderr,
        )
        return "warning"


def _launch(
    root: Path,
    *,
    task_id: str,
    checkout_root: Path,
    execution_provider: str,
) -> int:
    launcher = root / "Pipeline" / "TaskReviewAgent" / "Start-GameTaskAgent.ps1"
    return subprocess.run(
        (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(launcher),
            "-TaskId",
            task_id,
            "-ExecutionProvider",
            execution_provider,
            "-CheckoutRoot",
            str(checkout_root.resolve()),
        ),
        cwd=str(root),
        check=False,
    ).returncode


def _launch_decomposition(
    root: Path, *, task_id: str, checkout_root: Path
) -> int:
    worker_id = f"approve-decomposition-{task_id.casefold()}-{uuid.uuid4().hex[:12]}"
    return subprocess.run(
        build_decomposition_worker_command(
            task_id=task_id,
            worker_id=worker_id,
            source=root,
            checkout_root=checkout_root,
        ),
        cwd=str(root),
        check=False,
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id")
    parser.add_argument("--tested-commit")
    parser.add_argument(
        "--approve-decomposition",
        action="store_true",
        help="Approve the exact durable decomposition plan instead of a Unity commit.",
    )
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--execution-provider", choices=("claude", "codex"), default="claude")
    parser.add_argument("--wait-timeout-seconds", type=float, default=300.0)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument(
        "--notes",
        default="All exact-commit Unity/runtime checks passed.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Post PASS, change the state label, wait for GitHub, and launch.",
    )
    parser.add_argument(
        "--defer-launch",
        action="store_true",
        help=(
            "After --apply posts and verifies the exact result, poke an active "
            "direct launcher and leave the task agent_ready for scheduler fallback."
        ),
    )
    args = parser.parse_args()
    try:
        task_id = validate_task_id(args.task_id)
        if args.approve_decomposition and args.tested_commit:
            raise PassAndResumeError(
                "--approve-decomposition and --tested-commit are mutually exclusive"
            )
        tested_commit = str(args.tested_commit or "").strip().lower()
        if not args.approve_decomposition and SHA40.fullmatch(tested_commit) is None:
            raise PassAndResumeError(
                "--tested-commit must be a 40-character lowercase SHA"
            )
        if args.wait_timeout_seconds <= 0 or args.poll_seconds <= 0:
            raise PassAndResumeError("wait and poll durations must be positive")
        if args.defer_launch and not args.apply:
            raise PassAndResumeError("--defer-launch requires --apply")
        root = _repo_root(args.source.resolve())
        backend = GhIssueBackend(source_root=root)
        service = IssueWorkflowService(
            backend=backend,
            task_loader=lambda requested: load_committed_task(root, requested),
            worker_id="pass-and-resume-task",
            vincent_inbox_title=VINCENT_INBOX_TITLE,
        )
        snapshot = service.find(task_id)
        if snapshot is None:
            raise PassAndResumeError(f"no open managed Issue exists for {task_id}")

        if args.approve_decomposition:
            plan_id = _decomposition_plan_id(snapshot)
            checkout = root
            status = (
                "already_ready"
                if _ready_for_decomposition_apply(snapshot, plan_id)
                else "ready_to_approve_decomposition"
            )
        elif _ready_for_delivery(snapshot, tested_commit):
            checkout = Path(snapshot.state.checkout_path).resolve()  # type: ignore[union-attr]
            status = "already_ready"
        else:
            checkout = _validate_handoff(
                snapshot,
                task_id=task_id,
                tested_commit=tested_commit,
                checkout_root=args.checkout_root,
                apply_recovery=bool(args.apply),
            )
            status = "ready_to_apply"
        plan = {
            "task_id": task_id,
            "issue_number": snapshot.issue_number,
            "issue_url": snapshot.issue_url,
            "tested_commit": tested_commit,
            "decomposition_plan_id": plan_id if args.approve_decomposition else None,
            "checkout": str(checkout),
            "status": status,
            "will_launch": bool(args.apply and not args.defer_launch),
        }
        print(json.dumps(plan, indent=2, sort_keys=True))
        if not args.apply:
            print("PASS AND RESUME: DRY RUN (add --apply to mutate and launch)")
            return 0

        if status != "already_ready":
            body = (
                _decomposition_comment(plan_id, str(args.notes).strip())
                if args.approve_decomposition
                else _pass_comment(tested_commit, str(args.notes).strip())
            )
            existing_comments = backend.get_comments(snapshot.issue_number)
            if not any(item.get("body") == body for item in existing_comments):
                backend.add_comment(snapshot.issue_number, body)
            _apply_canonical_human_transition(
                service,
                task_id=task_id,
                body=body,
                actor_id=_authenticated_human_login(root),
                approve_decomposition=bool(args.approve_decomposition),
            )
            if args.approve_decomposition:
                snapshot = _wait_for_decomposition_ready(
                    service,
                    task_id,
                    plan_id,
                    timeout_seconds=args.wait_timeout_seconds,
                    poll_seconds=args.poll_seconds,
                )
            else:
                snapshot = _wait_for_delivery_ready(
                    service,
                    task_id,
                    tested_commit,
                    timeout_seconds=args.wait_timeout_seconds,
                    poll_seconds=args.poll_seconds,
                )
        if args.approve_decomposition:
            print(
                f"GitHub ready: Issue #{snapshot.issue_number} is agent_ready / "
                f"decomposition_apply for {plan_id}"
            )
            if args.defer_launch:
                print("Launch deferred to the supervised software architect.")
                return 0
            return _launch_decomposition(
                root, task_id=task_id, checkout_root=args.checkout_root
            )
        print(
            f"GitHub ready: Issue #{snapshot.issue_number} is agent_ready / delivery_evidence "
            f"at {tested_commit}"
        )
        notification_status = _clear_vincent_notification(
            service, task_id=task_id
        )
        print(f"NSC-Vincent notification: {notification_status}.")
        if args.defer_launch:
            hint_path = _poke_waiting_game_task_launcher(
                root, task_id=task_id, snapshot=snapshot
            )
            if hint_path is not None:
                print(f"Poked the waiting Game Task Agent via {hint_path}.")
            print("Launch deferred to the supervised software architect.")
            return 0
        return _launch(
            root,
            task_id=task_id,
            checkout_root=args.checkout_root,
            execution_provider=args.execution_provider,
        )
    except (
        IssueWorkflowStoreError,
        PassAndResumeError,
        TaskReviewContractError,
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(f"PASS AND RESUME: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
