#!/usr/bin/env python3
"""Write the origin-resolved GitHub repository for one exact source checkout.

The autonomous graph controller requires an explicit ``--confirm-repository``
assertion. A top-level Game Task Agent launch has no operator-supplied value, so
this helper reuses the single committed authority --
:func:`resolve_issue_backend_repository` -- instead of re-parsing a Git remote in
PowerShell. The controller still re-resolves and re-asserts the value against the
same origin, so nothing here becomes an independent repository authority.

The resolved value is written to ``--output`` as exact UTF-8 bytes with no
trailing newline. Machine data therefore never travels through a combined
stdout/stderr stream, which `Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md`
prohibits as machine authority. Diagnostics go to stderr only.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.issue_queue import repo_root  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowStoreError,
    resolve_issue_backend_repository,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Exact file to receive the resolved owner/repository as UTF-8 bytes.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = repo_root(args.source.resolve())
        repository = resolve_issue_backend_repository(source)
    except (IssueWorkflowStoreError, OSError, ValueError) as exc:
        print(f"RESOLVE ISSUE REPOSITORY: STOP\n{exc}", file=sys.stderr)
        return 2
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(repository.encode("utf-8"))
    except OSError as exc:
        print(f"RESOLVE ISSUE REPOSITORY: STOP\n{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
