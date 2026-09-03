#!/usr/bin/env python3
"""No-network tests for the host decomposition lifecycle boundary."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.host_decomposition_launcher as launcher  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowEventType,
    WorkflowPhase,
)


TASK_ID = "NSC-777"
SOURCE_HEAD = "1" * 40
PLAN_ID = "GDP-" + "a" * 64


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class RecordingService:
    def __init__(self) -> None:
        self.releases: list[dict] = []

    def release_decomposition_lease(self, **values):
        self.releases.append(dict(values))
        return {"status": "agent_ready"}


class RecordingClaimClient:
    def __init__(self) -> None:
        self.receipt = object()
        self.released: list[object] = []

    def acquire(self, **_values):
        return self.receipt

    def release(self, receipt):
        self.released.append(receipt)
        return {"status": "released"}


def arguments() -> SimpleNamespace:
    return SimpleNamespace(
        task_id=TASK_ID,
        compose_project="nosafecircle-m2a",
        providers="codex,claude",
        max_calls=4,
    )


def test_proposal_failure_releases_durable_lease_without_killing_scheduler() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        output = root / "outputs"
        output.mkdir()
        service = RecordingService()
        original = launcher.subprocess.run
        launcher.subprocess.run = lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=7
        )
        try:
            result = launcher._run_proposal(
                args=arguments(),
                source=root,
                output_root=output,
                source_head=SOURCE_HEAD,
                service=service,
            )
        finally:
            launcher.subprocess.run = original
        require(result == 0, f"handled proposal failure returned {result}")
        require(len(service.releases) == 1, str(service.releases))
        require(
            service.releases[0].get("task_id") == TASK_ID,
            str(service.releases),
        )


def test_stale_authorized_plan_releases_to_fresh_decomposition() -> None:
    service = RecordingService()
    handoff = SimpleNamespace(
        event_type=WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED,
        details={
            "graph_delta_plan_id": PLAN_ID,
            "head_commit": SOURCE_HEAD,
            "artifact_root": "C:/fixture/output",
        },
    )


def test_malformed_proposal_artifact_releases_durable_lease() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        output = root / "outputs"
        output.mkdir()
        service = RecordingService()
        original = launcher.subprocess.run

        def fake_run(*args, **kwargs):
            (output / "new-run").mkdir()
            return subprocess.CompletedProcess(args=args[0], returncode=0)

        launcher.subprocess.run = fake_run
        try:
            result = launcher._run_proposal(
                args=arguments(),
                source=root,
                output_root=output,
                source_head=SOURCE_HEAD,
                service=service,
            )
        finally:
            launcher.subprocess.run = original
        require(result == 0, str(result))
        require(len(service.releases) == 1, str(service.releases))
        require("artifacts" in service.releases[0]["reason"], str(service.releases))


def test_apply_artifact_error_releases_global_claim() -> None:
    service = RecordingService()
    claims = RecordingClaimClient()
    handoff = SimpleNamespace(
        event_type=WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED,
        details={
            "graph_delta_plan_id": PLAN_ID,
            "head_commit": SOURCE_HEAD,
            "artifact_root": "C:/fixture/missing-output",
        },
    )
    snapshot = SimpleNamespace(events=(handoff,))
    original_git = launcher._git
    launcher._git = lambda _source, *git_args: SOURCE_HEAD
    try:
        try:
            launcher._apply_approved_plan(
                args=arguments(),
                source=Path("C:/fixture/source"),
                source_head=SOURCE_HEAD,
                service=service,
                claim_client=claims,
                prelease_snapshot=snapshot,
            )
        except OSError:
            pass
        else:
            raise AssertionError("missing authorized artifacts did not fail closed")
    finally:
        launcher._git = original_git
    require(claims.released == [claims.receipt], str(claims.released))
    snapshot = SimpleNamespace(events=(handoff,))
    result = launcher._apply_approved_plan(
        args=arguments(),
        source=Path("C:/fixture/source"),
        source_head="2" * 40,
        service=service,
        claim_client=SimpleNamespace(),
        prelease_snapshot=snapshot,
    )
    require(result == 0, str(result))
    require(len(service.releases) == 1, str(service.releases))
    require(
        service.releases[0].get("retry_phase") is None,
        "stale authorization should use the default fresh-decomposition phase",
    )


def test_compose_command_is_exact_review_only_service() -> None:
    command = launcher.build_compose_command(
        task_id=TASK_ID,
        project="nosafecircle-m2a",
        providers="codex,claude",
        max_calls=4,
    )
    require("round-robin-decompose" in command, str(command))
    require(
        any(item.endswith("run_round_robin_decomposition.py") for item in command),
        str(command),
    )
    require(command[command.index("--task-id") + 1] == TASK_ID, str(command))
    require("apply_graph_delta.py" not in command, str(command))


def main() -> int:
    tests = (
        test_proposal_failure_releases_durable_lease_without_killing_scheduler,
        test_stale_authorized_plan_releases_to_fresh_decomposition,
        test_malformed_proposal_artifact_releases_durable_lease,
        test_apply_artifact_error_releases_global_claim,
        test_compose_command_is_exact_review_only_service,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"host decomposition launcher tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
