#!/usr/bin/env python3
"""Reject an unsafe explicit fresh task before Docker startup work."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    TaskReviewContractError,
    TaskReviewRequest,
)
from Pipeline.TaskReviewAgent.generic_selection import GenericSelectionError  # noqa: E402
from Pipeline.TaskReviewAgent.run_pipeline_agent import (  # noqa: E402
    _managed_issue_phase,
    _require_explicit_fresh_admission,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--worker-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = TaskReviewRequest(args.task_id)
        selected_phase = _managed_issue_phase(
            source=args.source,
            task_id=request.task_id,
            worker_id=args.worker_id,
        )
        _require_explicit_fresh_admission(
            source=args.source,
            task_id=request.task_id,
            worker_id=args.worker_id,
            selected_phase=selected_phase,
        )
        print(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "task_id": request.task_id,
                    "status": "resume_allowed" if selected_phase else "fresh_allowed",
                    "phase": selected_phase,
                    "authority": "canonical_explicit_task_admission",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (TaskReviewContractError, GenericSelectionError, OSError, ValueError) as exc:
        print(f"LAUNCHER PREFLIGHT: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
