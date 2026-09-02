#!/usr/bin/env python3
"""Host boundary adapter for one exact polling-orchestrator worker."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


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
    parser.add_argument("--model")
    parser.add_argument("--supervisor-reasoning-effort")
    parser.add_argument("--execution-model")
    parser.add_argument("--execution-reasoning-effort")
    return parser


def build_powershell_command(args: argparse.Namespace) -> tuple[str, ...]:
    source = args.source.resolve()
    checkout_root = args.checkout_root.resolve()
    output_root = args.output_root.resolve()
    starter = source / "Pipeline" / "TaskReviewAgent" / "Start-GameTaskAgent.ps1"

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
        "-OutputRoot",
        str(output_root),
    ]
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
    return tuple(command)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.source.resolve()
    starter = source / "Pipeline" / "TaskReviewAgent" / "Start-GameTaskAgent.ps1"
    if not starter.is_file():
        print(
            "GAME TASK AGENT: STOP\n"
            f"Host Game Task Agent launcher is missing: {starter}",
            file=sys.stderr,
            flush=True,
        )
        return 2
    try:
        completed = subprocess.run(
            build_powershell_command(args),
            cwd=str(source),
            check=False,
        )
    except OSError as exc:
        print(
            "GAME TASK AGENT: STOP\n"
            f"Host Game Task Agent launcher could not start: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return 2
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
