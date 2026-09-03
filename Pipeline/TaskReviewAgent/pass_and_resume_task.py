#!/usr/bin/env python3
"""Record an exact-commit human PASS, await GitHub, and resume the task agent."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import TaskReviewContractError, validate_task_id  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    ALL_STATE_LABELS,
    WorkflowActor,
    WorkflowPhase,
    WorkflowState,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowSnapshot,
    IssueWorkflowStoreError,
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


def _validate_handoff(
    snapshot: IssueWorkflowSnapshot,
    *,
    task_id: str,
    tested_commit: str,
    checkout_root: Path,
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
    if _run_text(("git", "-C", str(checkout), "status", "--porcelain"), cwd=checkout):
        raise PassAndResumeError("checkout has uncommitted or untracked changes")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id")
    parser.add_argument("--tested-commit", required=True)
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
    args = parser.parse_args()
    try:
        task_id = validate_task_id(args.task_id)
        tested_commit = str(args.tested_commit).strip().lower()
        if SHA40.fullmatch(tested_commit) is None:
            raise PassAndResumeError("--tested-commit must be a 40-character lowercase SHA")
        if args.wait_timeout_seconds <= 0 or args.poll_seconds <= 0:
            raise PassAndResumeError("wait and poll durations must be positive")
        root = _repo_root(args.source.resolve())
        backend = GhIssueBackend(source_root=root)
        service = IssueWorkflowService(
            backend=backend,
            task_loader=lambda requested: load_committed_task(root, requested),
            worker_id="pass-and-resume-task",
        )
        snapshot = service.find(task_id)
        if snapshot is None:
            raise PassAndResumeError(f"no open managed Issue exists for {task_id}")

        if _ready_for_delivery(snapshot, tested_commit):
            checkout = Path(snapshot.state.checkout_path).resolve()  # type: ignore[union-attr]
            status = "already_ready"
        else:
            checkout = _validate_handoff(
                snapshot,
                task_id=task_id,
                tested_commit=tested_commit,
                checkout_root=args.checkout_root,
            )
            status = "ready_to_apply"
        plan = {
            "task_id": task_id,
            "issue_number": snapshot.issue_number,
            "issue_url": snapshot.issue_url,
            "tested_commit": tested_commit,
            "checkout": str(checkout),
            "status": status,
            "will_launch": bool(args.apply),
        }
        print(json.dumps(plan, indent=2, sort_keys=True))
        if not args.apply:
            print("PASS AND RESUME: DRY RUN (add --apply to mutate and launch)")
            return 0

        if status != "already_ready":
            body = _pass_comment(tested_commit, str(args.notes).strip())
            existing_comments = backend.get_comments(snapshot.issue_number)
            if not any(item.get("body") == body for item in existing_comments):
                backend.add_comment(snapshot.issue_number, body)
            desired_labels = [
                label for label in snapshot.labels if label not in ALL_STATE_LABELS
            ] + ["nsc-state:agent-ready"]
            backend.update_issue(snapshot.issue_number, labels=desired_labels)
            snapshot = _wait_for_delivery_ready(
                service,
                task_id,
                tested_commit,
                timeout_seconds=args.wait_timeout_seconds,
                poll_seconds=args.poll_seconds,
            )
        print(
            f"GitHub ready: Issue #{snapshot.issue_number} is agent_ready / delivery_evidence "
            f"at {tested_commit}"
        )
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
