#!/usr/bin/env python3
"""Verify each supervisor reuses its own existing credential volume as external."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OVERRIDE = ROOT / "compose.override.yaml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_supervisor_credential_volume_is_external() -> None:
    text = OVERRIDE.read_text(encoding="utf-8")
    expected = (
        "  task-supervisor-codex-config:\n"
        "    external: true\n"
        "    name: ${NSC_TASK_SUPERVISOR_CODEX_VOLUME:-nosafecircle_codex-config}\n"
    )
    require(
        expected in text,
        "Codex supervisor credential volume must be declared external before its exact name",
    )
    require(
        "- task-supervisor-codex-config:/home/agent/.codex" in text,
        "codex-supervisor service no longer mounts the selected credential volume",
    )


def test_claude_supervisor_service_matches_the_codex_contract() -> None:
    """The Claude supervisor mounts its own store and a read-only source.

    Without this the Claude route had no committed proof at all: the service,
    its credential volume, and its read-only repository mount were untested.
    """

    text = OVERRIDE.read_text(encoding="utf-8")
    expected = (
        "  task-supervisor-claude-config:\n"
        "    external: true\n"
        "    name: ${NSC_TASK_SUPERVISOR_CLAUDE_VOLUME:-nosafecircle_claude-config}\n"
    )
    require(
        expected in text,
        "Claude supervisor credential volume must be declared external before its exact name",
    )
    require(
        "  claude-supervisor:\n" in text,
        "compose.override.yaml no longer declares the claude-supervisor service",
    )
    require(
        "- task-supervisor-claude-config:/home/agent/.claude" in text,
        "claude-supervisor does not mount the selected credential volume",
    )
    require(
        "      CLAUDE_CONFIG_DIR: /home/agent/.claude" in text,
        "claude-supervisor must point the Claude CLI at the mounted store",
    )
    # A supervisor observes the repository and may never write to it.
    require(
        text.count("      - .:/workspace:ro") >= 2,
        "both supervisor services must mount the repository read-only",
    )


def main() -> int:
    test_supervisor_credential_volume_is_external()
    print("PASS test_supervisor_credential_volume_is_external")
    test_claude_supervisor_service_matches_the_codex_contract()
    print("PASS test_claude_supervisor_service_matches_the_codex_contract")
    print("TaskReviewAgent Compose credential-volume tests: PASS (2 tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
