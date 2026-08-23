#!/usr/bin/env python3
"""Opt-in live smoke for Claude repository Read/Glob/Grep access."""

from __future__ import annotations

import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.contracts import (
    AgentRequest,
    Budgets,
    SCHEMA_VERSION,
    TaskContractIdentity,
    WriteBoundaries,
)
from Pipeline.AgentRuntime.providers import ClaudeCodeProvider


def main() -> None:
    if os.environ.get("NSC_RUN_CLAUDE_REPOSITORY_SMOKE") != "1":
        print(
            "Claude repository read/search live smoke: SKIP "
            "(set NSC_RUN_CLAUDE_REPOSITORY_SMOKE=1)"
        )
        return

    model = os.environ.get("NSC_CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
    schema = {
        "type": "object",
        "properties": {
            "read_found": {"type": "boolean"},
            "search_found": {"type": "boolean"},
            "summary": {"type": "string"},
        },
        "required": ["read_found", "search_found", "summary"],
        "additionalProperties": False,
    }
    request = AgentRequest(
        SCHEMA_VERSION,
        "claude-repository-live-smoke",
        "NSC-001",
        TaskContractIdentity("Tasks/NSC-001.yaml", 1, "a" * 64),
        "validator",
        (
            "Use Read to inspect Pipeline/AgentRuntime/README.md and confirm it "
            "describes a provider-neutral AgentRuntime. Use Glob or Grep to find "
            "the harmless string 'ProviderOutputInvalid' in Pipeline/AgentRuntime. "
            "Do not write files or run commands. Return only the requested JSON."
        ),
        ("Pipeline/AgentRuntime/README.md", "Pipeline/AgentRuntime"),
        ("repository_read", "repository_search"),
        WriteBoundaries((), ()),
        schema,
        "standard",
        Budgets(8, 120),
        "claude-default",
    )
    response = ClaudeCodeProvider().invoke(request, model)
    output = response.structured_output
    if output.get("read_found") is not True or output.get("search_found") is not True:
        raise AssertionError(f"Claude did not confirm both operations: {output!r}")
    print("Claude repository read/search live smoke: PASS")


if __name__ == "__main__":
    main()
