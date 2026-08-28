#!/usr/bin/env python3
"""Verify the Codex supervisor reuses an existing credential volume as external."""

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


def main() -> int:
    test_supervisor_credential_volume_is_external()
    print("PASS test_supervisor_credential_volume_is_external")
    print("TaskReviewAgent Compose credential-volume tests: PASS (1 test)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
