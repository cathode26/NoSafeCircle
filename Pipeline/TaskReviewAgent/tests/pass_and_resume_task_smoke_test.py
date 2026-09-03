#!/usr/bin/env python3
"""Smoke tests for exact-commit PASS-and-resume safeguards."""

from __future__ import annotations

import sys
import subprocess
import tempfile
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
    PassAndResumeError,
    _pass_comment,
    _recover_safe_unity_churn,
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


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def test_safe_unity_churn_is_restored_but_other_edits_are_refused() -> None:
    with tempfile.TemporaryDirectory(prefix="pass-and-resume-") as directory:
        root = Path(directory)
        _git(root, "init", "-b", "main")
        _git(root, "config", "user.name", "Smoke Test")
        _git(root, "config", "user.email", "smoke@example.invalid")
        safe = root / "ProjectSettings" / "EditorBuildSettings.asset"
        safe.parent.mkdir(parents=True)
        safe.write_text("baseline\n", encoding="utf-8")
        unsafe = root / "unsafe.txt"
        unsafe.write_text("baseline\n", encoding="utf-8")
        _git(root, "add", ".")
        _git(root, "commit", "-m", "baseline")
        commit = _git(root, "rev-parse", "HEAD")

        safe.write_text("Unity rewrite\n", encoding="utf-8")
        recovered = _recover_safe_unity_churn(root, commit)
        require(
            recovered == ("ProjectSettings/EditorBuildSettings.asset",),
            f"safe Unity path was not recovered exactly: {recovered}",
        )
        require(not _git(root, "status", "--porcelain"), "safe checkout stayed dirty")

        unsafe.write_text("operator edit\n", encoding="utf-8")
        try:
            _recover_safe_unity_churn(root, commit)
        except PassAndResumeError:
            pass
        else:
            raise AssertionError("non-Unity edit was restored or accepted")
    require(
        not _ready_for_delivery(snapshot(commit="b" * 40), COMMIT),
        "different tested commit was accepted",
    )


def main() -> int:
    tests = (
        test_comment_has_canonical_exact_commit_result,
        test_ready_requires_consistent_event_count_and_commit,
        test_safe_unity_churn_is_restored_but_other_edits_are_refused,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"pass_and_resume_task smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
