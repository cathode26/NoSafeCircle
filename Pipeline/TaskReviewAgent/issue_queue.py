#!/usr/bin/env python3
"""List validated agent-ready No Safe Circle Issues before selecting new work."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import TaskReviewContractError  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowStoreError,
)


def repo_root(source: Path) -> Path:
    result = subprocess.run(
        ("git", "-C", str(source), "rev-parse", "--show-toplevel"),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60.0,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise IssueWorkflowStoreError("source is not a readable Git repository")
    return Path(result.stdout.strip()).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--worker-id", default="task-review-agent-queue")
    args = parser.parse_args()
    try:
        root = repo_root(args.source.resolve())
        service = IssueWorkflowService(
            backend=GhIssueBackend(source_root=root),
            task_loader=lambda task_id: load_committed_task(root, task_id),
            worker_id=args.worker_id,
        )
        ready = service.list_agent_ready()
        print(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "selection_priority": "resume_agent_ready_before_new_task",
                    "agent_ready_count": len(ready),
                    "agent_ready": ready,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (TaskReviewContractError, OSError) as exc:
        print(f"ISSUE WORKFLOW QUEUE: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
