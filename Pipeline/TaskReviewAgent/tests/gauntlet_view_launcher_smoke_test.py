#!/usr/bin/env python3
"""Pure/component tests for architect-managed GauntletView lifecycle.

The tests use injected loopback probes and never start a browser, scheduler,
provider, Docker container, GitHub mutation, or long-lived viewer process.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.gauntlet_view_launcher import (  # noqa: E402
    ViewerIdentity,
    choose_existing_or_free_port,
    viewer_command,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def identity(*, run_id: str = "run-a", approval: bool = False) -> ViewerIdentity:
    return ViewerIdentity(
        source=Path("C:/fixture/source"),
        source_branch="main",
        source_commit="a" * 40,
        state_root=Path("C:/fixture/state"),
        run_id=run_id,
        run_dir=Path(f"C:/fixture/state/.task-review-agent/autonomous-runs/repo/{run_id}"),
        repository="owner/repository",
        display_task_ids=("NSC-1001", "NSC-1002"),
        human_approval_enabled=approval,
    )


def health(expected: ViewerIdentity) -> dict:
    return {
        "schema": "nsc-gauntlet-view-health/v1",
        "status": "ok",
        "identity": expected.to_dict(),
    }


def test_matching_listener_is_reused_without_a_spawn_port() -> None:
    expected = identity()
    decision = choose_existing_or_free_port(
        expected,
        range(8787, 8790),
        probe=lambda port: health(expected) if port == 8788 else None,
        port_available=lambda port: port == 8787,
    )
    require(decision.disposition == "reuse", str(decision))
    require(decision.port == 8788, str(decision))


def test_mismatched_gauntlet_listener_is_never_reused() -> None:
    expected = identity()
    other = identity(run_id="run-b")
    decision = choose_existing_or_free_port(
        expected,
        range(8787, 8790),
        probe=lambda port: health(other) if port == 8787 else None,
        port_available=lambda port: port == 8788,
    )
    require(decision.disposition == "start", str(decision))
    require(decision.port == 8788, str(decision))


def test_unknown_occupied_port_is_skipped_not_killed() -> None:
    expected = identity()
    availability_calls: list[int] = []

    def available(port: int) -> bool:
        availability_calls.append(port)
        return port == 8788

    decision = choose_existing_or_free_port(
        expected,
        range(8787, 8790),
        probe=lambda _port: None,
        port_available=available,
    )
    require(decision == decision.__class__("start", 8788), str(decision))
    require(availability_calls == [8787, 8788], str(availability_calls))


def test_raw_identity_without_health_schema_is_an_unknown_listener() -> None:
    expected = identity()
    decision = choose_existing_or_free_port(
        expected,
        range(8787, 8790),
        probe=lambda port: expected.to_dict() if port == 8787 else None,
        port_available=lambda port: port == 8788,
    )
    require(decision == decision.__class__("start", 8788), str(decision))


def test_viewer_command_binds_exact_run_identity_and_never_opens_browser() -> None:
    expected = identity(approval=True)
    command = viewer_command(
        expected,
        port=8791,
        python_executable="python-fixture",
        server_path=Path("C:/fixture/server.py"),
    )
    joined = " ".join(command)
    for value in (
        str(expected.source / "Tasks"),
        str(expected.state_root),
        str(expected.run_dir),
        expected.source_branch,
        expected.source_commit,
        expected.run_id,
        expected.repository,
        "NSC-1001",
        "NSC-1002",
    ):
        require(value in command, f"missing exact binding {value!r}: {command}")
    require("--enable-human-approval" in command, joined)
    require("browser" not in joined.casefold(), joined)


def test_read_only_command_omits_human_approval_capability() -> None:
    command = viewer_command(
        identity(),
        port=8791,
        python_executable="python-fixture",
        server_path=Path("C:/fixture/server.py"),
    )
    require("--enable-human-approval" not in command, str(command))


def main() -> int:
    tests = (
        test_matching_listener_is_reused_without_a_spawn_port,
        test_mismatched_gauntlet_listener_is_never_reused,
        test_unknown_occupied_port_is_skipped_not_killed,
        test_raw_identity_without_health_schema_is_an_unknown_listener,
        test_viewer_command_binds_exact_run_identity_and_never_opens_browser,
        test_read_only_command_omits_human_approval_capability,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"gauntlet view launcher smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
