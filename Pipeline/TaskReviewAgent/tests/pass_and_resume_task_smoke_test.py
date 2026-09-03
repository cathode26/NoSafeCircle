#!/usr/bin/env python3
"""Smoke tests for exact-commit PASS-and-resume safeguards."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowActor,
    WorkflowPhase,
    WorkflowState,
    parse_human_validation_result,
)
from Pipeline.TaskReviewAgent.pass_and_resume_task import (  # noqa: E402
    _pass_comment,
    _ready_for_delivery,
)

COMMIT = "a" * 40


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def snapshot(*, version: int = 3, commit: str = COMMIT):
    state = SimpleNamespace(
        state=WorkflowState.AGENT_READY,
        phase=WorkflowPhase.DELIVERY_EVIDENCE,
        current_actor=WorkflowActor.AGENT,
        head_commit=commit,
        human_handoff_commit=commit,
        human_result="pass",
        state_version=version,
    )
    return SimpleNamespace(
        managed=True,
        valid=True,
        state=state,
        events=(object(), object(), object()),
        labels=("nsc-state:agent-ready",),
    )


def test_comment_has_canonical_exact_commit_result() -> None:
    body = _pass_comment(COMMIT, "Validated in Unity.")
    result = parse_human_validation_result(body)
    require(result is not None, "generated PASS comment was not parseable")
    require(result.result == "pass", "generated result was not PASS")
    require(result.tested_commit == COMMIT, "generated result used the wrong commit")


def test_ready_requires_consistent_event_count_and_commit() -> None:
    require(_ready_for_delivery(snapshot(), COMMIT), "consistent ready state was rejected")
    require(
        not _ready_for_delivery(snapshot(version=2), COMMIT),
        "state/event race was accepted",
    )
    require(
        not _ready_for_delivery(snapshot(commit="b" * 40), COMMIT),
        "different tested commit was accepted",
    )


def main() -> int:
    tests = (
        test_comment_has_canonical_exact_commit_result,
        test_ready_requires_consistent_event_count_and_commit,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"pass_and_resume_task smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
