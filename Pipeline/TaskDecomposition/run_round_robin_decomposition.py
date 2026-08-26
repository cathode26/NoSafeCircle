#!/usr/bin/env python3
"""Run one human-authorized D1B.2 round-robin decomposition circuit."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = ROOT / "Pipeline" / "TaskGraph"
for _module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))

from Pipeline.AgentRuntime.contracts import ContractValidationError
from TaskDecomposition.context_builder import DecompositionPreflightError
from TaskDecomposition.round_robin_decomposition import (
    run_round_robin_decomposition,
)
from TaskDecomposition.run_decomposition import default_output_root


def _provider_order(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument(
        "--providers",
        default=os.getenv(
            "NSC_DECOMPOSITION_ROUND_ROBIN_PROVIDERS",
            "codex,claude",
        ),
        help="Comma-separated provider rotation; default: codex,claude",
    )
    parser.add_argument("--max-calls", type=int)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    output_root = args.output_root or default_output_root(args.source)
    try:
        result = run_round_robin_decomposition(
            source=args.source,
            output_root=output_root,
            task_id=args.task_id,
            provider_order=_provider_order(args.providers),
            max_calls=args.max_calls,
            run_id=args.run_id,
        )
    except (DecompositionPreflightError, ContractValidationError, OSError) as exc:
        print(f"Round-robin decomposition blocked: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["run_status"] in {"review_ready", "needs_human"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
