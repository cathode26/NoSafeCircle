#!/usr/bin/env python3
"""Host boundary for one physically read-only D1B.2 decomposition run.

This launcher intentionally does not apply a graph delta. It supplies the external
Windows output mount and invokes the canonical round-robin Compose service with the
repository mounted read-only. Durable Issue claim/authorization is owned by the
calling orchestrator layer.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.contracts import validate_task_id  # noqa: E402
from Pipeline.TaskReviewAgent.issue_queue import repo_root  # noqa: E402


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path)
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
        output_root.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment["NSC_DECOMPOSITION_HOST_OUTPUT_ROOT"] = str(output_root)
        completed = subprocess.run(
            build_compose_command(
                task_id=task_id,
                project=args.compose_project,
                providers=args.providers,
                max_calls=args.max_calls,
            ),
            cwd=str(source),
            env=environment,
            check=False,
        )
        return completed.returncode
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Decomposition launcher blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

