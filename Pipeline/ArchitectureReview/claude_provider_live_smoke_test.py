#!/usr/bin/env python3
"""Opt-in live smoke for the AgentRuntime-backed Claude review adapter."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

import architecture_review as shared
import architecture_review_claude as claude_review


SMOKE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "read_found": {"type": "boolean"},
        "search_found": {"type": "boolean"},
    },
    "required": ["read_found", "search_found"],
}


def main() -> int:
    if os.environ.get("NSC_RUN_ARCH_REVIEW_CLAUDE_SMOKE") != "1":
        print(
            "claude_provider_live_smoke_test: SKIP "
            "(set NSC_RUN_ARCH_REVIEW_CLAUDE_SMOKE=1)"
        )
        return 0

    model = os.environ.get("NSC_ARCH_REVIEW_CLAUDE_MODEL", "claude-sonnet-5")
    shared.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="claude-live-smoke-", dir=shared.OUTPUT_ROOT
    ) as temporary:
        claude_review.configure_invocation_run_root(Path(temporary))
        result = claude_review.invoke_claude_agent(
            agent_name="Architecture Review Live Smoke",
            model=model,
            prompt=(
                "Use Read to inspect Pipeline/ArchitectureReview/README.md. "
                "Use Glob or Grep to find architecture_review_claude.py under "
                "Pipeline/ArchitectureReview. Do not write files or run commands. "
                "Return read_found=true and search_found=true only after both succeed."
            ),
            schema=SMOKE_SCHEMA,
            max_turns=4,
        )

    assert result["provider"] == "claude-code"
    assert result["model"] == model
    assert result["result"] == {"read_found": True, "search_found": True}
    print("claude_provider_live_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
