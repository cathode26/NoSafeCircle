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
from TaskDecomposition.session_pool_support import (
    DecompositionSessionError,
    load_lease_bundle,
)


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
    parser.add_argument(
        "--role-session-leases",
        type=Path,
        help=(
            "Host-owned lease bundle for durable role-scoped provider sessions. "
            "Requires --run-id and --scheduler-repository-identity; omitting it "
            "leaves every round exactly ephemeral."
        ),
    )
    parser.add_argument(
        "--scheduler-repository-identity",
        help="The scheduler-proven repository identity every lease must name.",
    )
    args = parser.parse_args()
    output_root = args.output_root or default_output_root(args.source)
    lease_bundle = None
    if (args.role_session_leases is None) != (args.scheduler_repository_identity is None):
        print(
            "Decomposition blocked: --role-session-leases and "
            "--scheduler-repository-identity must be supplied together",
            file=sys.stderr,
        )
        return 2
    if args.role_session_leases is not None:
        if not args.run_id:
            print("Decomposition blocked: pooled sessions require --run-id", file=sys.stderr)
            return 2
        try:
            lease_bundle = load_lease_bundle(args.role_session_leases, run_id=args.run_id)
        except DecompositionSessionError as exc:
            print(f"Decomposition blocked: {exc}", file=sys.stderr)
            return 2
    try:
        result = run_round_robin_decomposition(
            source=args.source,
            output_root=output_root,
            task_id=args.task_id,
            provider_order=_provider_order(args.providers),
            max_calls=args.max_calls,
            run_id=args.run_id,
            lease_bundle=lease_bundle,
            scheduler_repository_identity=args.scheduler_repository_identity,
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
