#!/usr/bin/env python3
"""Host boundary adapter for one exact polling-orchestrator worker."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.worker_result import (  # noqa: E402
    WorkerResultError,
    initialize_worker_run,
    validate_worker_result,
    write_worker_result,
)
from Pipeline.TaskReviewAgent.provider_policy import (  # noqa: E402
    parse_provider_allowlist,
    require_permitted_provider,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--mode", choices=("openai", "observe"), default="openai")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument(
        "--execution-provider",
        choices=("claude", "codex"),
        required=True,
    )
    parser.add_argument("--max-turns", type=int, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--admission-source-head")
    parser.add_argument("--task-contract-sha256")
    parser.add_argument("--admission-issue-number", type=int)
    parser.add_argument("--model")
    parser.add_argument("--supervisor-reasoning-effort")
    parser.add_argument("--execution-model")
    parser.add_argument("--execution-reasoning-effort")
    parser.add_argument("--crew-profile", choices=("lean", "standard", "full"))
    parser.add_argument(
        "--validation-profile",
        choices=("targeted", "task_specific", "full_relevant"),
    )
    parser.add_argument("--enable-execution-session-pool", action="store_true")
    parser.add_argument("--provider-allowlist", type=parse_provider_allowlist)
    return parser


def build_powershell_command(args: argparse.Namespace) -> tuple[str, ...]:
    source = args.source.resolve()
    checkout_root = args.checkout_root.resolve()
    output_root = args.output_root.resolve()
    starter = source / "Pipeline" / "TaskReviewAgent" / "Start-GameTaskAgent.ps1"
    permitted = getattr(args, "provider_allowlist", None)
    require_permitted_provider(args.execution_provider, permitted, role="execution")
    require_permitted_provider("codex", permitted, role="supervisor")
    if (args.crew_profile is None) != (args.validation_profile is None):
        raise ValueError(
            "crew profile and validation profile must be supplied together"
        )

    command: list[str] = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(starter),
        "-TaskId",
        str(args.task_id),
        "-Mode",
        str(args.mode),
        "-Source",
        str(source),
        "-CheckoutRoot",
        str(checkout_root),
        "-WorkerId",
        str(args.worker_id),
        "-ExecutionProvider",
        str(args.execution_provider),
        "-MaxTurns",
        str(args.max_turns),
        "-HumanActionWaitMinutes",
        "0",
        "-OutputRoot",
        str(output_root),
    ]
    result_identity = (
        args.run_id,
        args.admission_source_head,
        args.task_contract_sha256,
    )
    if any(value is not None for value in result_identity):
        if not all(isinstance(value, str) and value for value in result_identity):
            raise ValueError(
                "scheduler result identity requires run id, source HEAD, and contract hash"
            )
        command.extend(
            (
                "-RunId",
                args.run_id,
                "-AdmissionSourceHead",
                args.admission_source_head,
                "-TaskContractSha256",
                args.task_contract_sha256,
            )
        )
        if args.admission_issue_number is not None:
            command.extend(
                ("-AdmissionIssueNumber", str(args.admission_issue_number))
            )
    if args.model:
        command.extend(("-Model", str(args.model)))
    if args.supervisor_reasoning_effort:
        command.extend(
            ("-SupervisorReasoningEffort", str(args.supervisor_reasoning_effort))
        )
    if args.execution_model:
        command.extend(("-ExecutionModel", str(args.execution_model)))
    if args.execution_reasoning_effort:
        command.extend(
            ("-ExecutionReasoningEffort", str(args.execution_reasoning_effort))
        )
    if args.crew_profile:
        command.extend(("-CrewProfile", str(args.crew_profile)))
    if args.validation_profile:
        command.extend(("-ValidationProfile", str(args.validation_profile)))
    if args.enable_execution_session_pool:
        command.append("-EnableExecutionSessionPool")
    if permitted is not None:
        command.extend(("-ProviderAllowlist", ",".join(permitted)))
    return tuple(command)


def _scheduler_result_enabled(args: argparse.Namespace) -> bool:
    identity = (
        args.run_id,
        args.admission_source_head,
        args.task_contract_sha256,
    )
    if all(value is None for value in identity):
        if args.admission_issue_number is not None:
            raise ValueError("admission Issue number requires scheduler result identity")
        return False
    if not all(isinstance(value, str) and value for value in identity):
        raise ValueError(
            "scheduler result identity requires run id, source HEAD, and contract hash"
        )
    if args.admission_issue_number is not None and args.admission_issue_number < 1:
        raise ValueError("admission Issue number must be a positive integer")
    return True


def _publish_wrapper_error(
    args: argparse.Namespace,
    *,
    started_at_utc: str,
    authority: str,
) -> None:
    """Best-effort publication for failures outside the nested worker."""

    if not _scheduler_result_enabled(args):
        return
    run_dir = args.output_root.resolve() / str(args.task_id) / str(args.run_id)
    if not run_dir.exists():
        run_dir = initialize_worker_run(
            output_root=args.output_root,
            task_id=args.task_id,
            run_id=args.run_id,
            worker_id=args.worker_id,
            started_at_utc=started_at_utc,
        )
    write_worker_result(
        run_dir=run_dir,
        run_id=args.run_id,
        worker_id=args.worker_id,
        task_id=args.task_id,
        source_head=args.admission_source_head,
        task_contract_sha256=args.task_contract_sha256,
        terminal_status="error",
        outcome_authority=authority,
        issue_number=args.admission_issue_number,
        exit_code=2,
        pid=os.getpid(),
    )


def _report_wrapper_error(
    args: argparse.Namespace,
    *,
    started_at_utc: str,
    authority: str,
    message: str,
) -> int:
    artifact_error: Exception | None = None
    try:
        _publish_wrapper_error(
            args,
            started_at_utc=started_at_utc,
            authority=authority,
        )
    except (OSError, ValueError, WorkerResultError) as exc:
        artifact_error = exc
    print("GAME TASK AGENT: STOP\n" + message, file=sys.stderr, flush=True)
    if artifact_error is not None:
        print(
            "The host wrapper could not publish its terminal result: "
            f"{artifact_error}",
            file=sys.stderr,
            flush=True,
        )
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    started_at_utc = _utc_now()
    try:
        scheduler_result = _scheduler_result_enabled(args)
    except ValueError as exc:
        print(f"GAME TASK AGENT: STOP\n{exc}", file=sys.stderr, flush=True)
        return 2
    source = args.source.resolve()
    starter = source / "Pipeline" / "TaskReviewAgent" / "Start-GameTaskAgent.ps1"
    if not starter.is_file():
        return _report_wrapper_error(
            args,
            started_at_utc=started_at_utc,
            authority="host_launcher_missing",
            message=f"Host Game Task Agent launcher is missing: {starter}",
        )
    try:
        completed = subprocess.run(
            build_powershell_command(args),
            cwd=str(source),
            check=False,
        )
    except (OSError, ValueError) as exc:
        return _report_wrapper_error(
            args,
            started_at_utc=started_at_utc,
            authority="host_launcher_start_error",
            message=f"Host Game Task Agent launcher could not start: {exc}",
        )
    returncode = int(completed.returncode)
    if not scheduler_result:
        return returncode
    run_dir = (
        args.output_root.resolve() / str(args.task_id) / str(args.run_id)
    )
    pipeline_result_path = run_dir / "pipeline_result.json"
    try:
        pipeline_result = validate_worker_result(
            pipeline_result_path,
            expected_run_id=args.run_id,
            expected_worker_id=args.worker_id,
            expected_task_id=args.task_id,
            expected_source_head=args.admission_source_head,
            expected_task_contract_sha256=args.task_contract_sha256,
            expected_pid=None,
            observed_exit_code=returncode,
            started_at_utc=started_at_utc,
            observed_at_utc=_utc_now(),
            expected_issue_number=args.admission_issue_number,
        )
        write_worker_result(
            run_dir=run_dir,
            run_id=args.run_id,
            worker_id=args.worker_id,
            task_id=args.task_id,
            source_head=args.admission_source_head,
            task_contract_sha256=args.task_contract_sha256,
            terminal_status=pipeline_result["terminal_status"],
            outcome_authority=pipeline_result["outcome_authority"],
            issue_number=pipeline_result["issue_number"],
            exit_code=returncode,
            pid=os.getpid(),
        )
    except (OSError, ValueError, WorkerResultError) as exc:
        return _report_wrapper_error(
            args,
            started_at_utc=started_at_utc,
            authority="nested_worker_result_rejected",
            message=f"The nested worker result could not be authenticated: {exc}",
        )
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
