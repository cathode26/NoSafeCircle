#!/usr/bin/env python3
"""Run one human-selected Stage D1B.1 read-only decomposition proposal."""

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
from TaskDecomposition.live_decomposition import run_live_decomposition


def default_output_root(source: Path) -> Path:
    configured_output = os.getenv("NSC_DECOMPOSITION_OUTPUT_ROOT")
    if configured_output:
        return Path(configured_output)
    return source.resolve().parent / "NoSafeCircle-DecompositionOutputs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--provider", required=True, choices=("claude", "codex"))
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    output_root = args.output_root or default_output_root(args.source)
    try:
        result = run_live_decomposition(
            source=args.source,
            output_root=output_root,
            task_id=args.task_id,
            provider_name=args.provider,
            run_id=args.run_id,
        )
    except (DecompositionPreflightError, ContractValidationError, OSError) as exc:
        print(f"Decomposition blocked: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
    )
    return 0 if result["run_status"] == "review_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
