#!/usr/bin/env python3
"""Regression tests for deterministic launcher admission before Docker."""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent import launcher_preflight  # noqa: E402
from Pipeline.TaskReviewAgent.generic_selection import GenericSelectionError  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_fresh_admission() -> None:
    calls: list[tuple[str, str | None]] = []
    original_phase = launcher_preflight._managed_issue_phase
    original_admission = launcher_preflight._require_explicit_fresh_admission
    try:
        launcher_preflight._managed_issue_phase = lambda **_: None

        def accept(**values):
            calls.append((values["task_id"], values["selected_phase"]))

        launcher_preflight._require_explicit_fresh_admission = accept
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = launcher_preflight.main(
                [
                    "--task-id",
                    "NSC-910",
                    "--source",
                    str(ROOT),
                    "--worker-id",
                    "launcher-smoke",
                ]
            )
        require(code == 0, "fresh admission did not succeed")
        require(calls == [("NSC-910", None)], "fresh admission arguments changed")
        require('"status": "fresh_allowed"' in output.getvalue(), "fresh status missing")
    finally:
        launcher_preflight._managed_issue_phase = original_phase
        launcher_preflight._require_explicit_fresh_admission = original_admission


def test_dependency_rejection() -> None:
    original_phase = launcher_preflight._managed_issue_phase
    original_admission = launcher_preflight._require_explicit_fresh_admission
    try:
        launcher_preflight._managed_issue_phase = lambda **_: None

        def reject(**_):
            raise GenericSelectionError("dependency_blocked:NSC-909:not_delivered")

        launcher_preflight._require_explicit_fresh_admission = reject
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            code = launcher_preflight.main(
                [
                    "--task-id",
                    "NSC-910",
                    "--source",
                    str(ROOT),
                    "--worker-id",
                    "launcher-smoke",
                ]
            )
        require(code == 2, "blocked dependency did not fail admission")
        require("dependency_blocked:NSC-909:not_delivered" in error.getvalue(), "reason missing")
    finally:
        launcher_preflight._managed_issue_phase = original_phase
        launcher_preflight._require_explicit_fresh_admission = original_admission


def test_launcher_orders_admission_before_docker() -> None:
    launcher = (ROOT / "Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1").read_text(
        encoding="utf-8"
    )
    admission = launcher.index("Pipeline/TaskReviewAgent/launcher_preflight.py")
    docker = launcher.index("Get-Command 'docker'")
    require(admission < docker, "launcher touches Docker before task admission")


def main() -> int:
    test_fresh_admission()
    test_dependency_rejection()
    test_launcher_orders_admission_before_docker()
    print("launcher_preflight_smoke_test: PASS (3 tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
