#!/usr/bin/env python3
"""No-network tests for the host decomposition lifecycle boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.host_decomposition_launcher as launcher  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
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

    @staticmethod
    def find(_task_id):
        return None


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
                workspace=root,
                output_root=output,
                source_head=SOURCE_HEAD,
                service=service,
            )
        finally:
            launcher.subprocess.run = original
        require(result == 3, f"handled proposal failure returned {result}")
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
    snapshot = SimpleNamespace(events=(handoff,))
    original = launcher.inspect_authorized_decomposition_replay
    launcher.inspect_authorized_decomposition_replay = lambda **_values: SimpleNamespace(
        plan_id=PLAN_ID,
        authorized_source_head=SOURCE_HEAD,
        inspection=SimpleNamespace(
            status="stale_or_partial",
            reason="fixture exact plan is absent",
        ),
    )
    try:
        result = launcher._apply_approved_plan(
            args=arguments(),
            source=Path("C:/fixture/source"),
            source_head="2" * 40,
            service=service,
            claim_client=SimpleNamespace(),
            prelease_snapshot=snapshot,
        )
    finally:
        launcher.inspect_authorized_decomposition_replay = original
    require(result == 3, str(result))
    require(len(service.releases) == 1, str(service.releases))
    require(
        "main moved" in service.releases[0].get("reason", ""),
        str(service.releases),
    )
    require(
        service.releases[0].get("retry_phase") is None,
        "stale authorization should use the default fresh-decomposition phase",
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
                workspace=root,
                output_root=output,
                source_head=SOURCE_HEAD,
                service=service,
            )
        finally:
            launcher.subprocess.run = original
        require(result == 3, str(result))
        require(len(service.releases) == 1, str(service.releases))
        require("artifacts" in service.releases[0]["reason"], str(service.releases))


def test_provider_start_error_releases_durable_lease() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        output = root / "outputs"
        output.mkdir()
        service = RecordingService()
        original = launcher.subprocess.run

        def fail_start(*_args, **_kwargs):
            raise FileNotFoundError("docker fixture missing")

        launcher.subprocess.run = fail_start
        try:
            result = launcher._run_proposal(
                args=arguments(),
                workspace=root,
                output_root=output,
                source_head=SOURCE_HEAD,
                service=service,
            )
        finally:
            launcher.subprocess.run = original
        require(result == 3, str(result))
        require(len(service.releases) == 1, str(service.releases))
        require("could not start" in service.releases[0]["reason"], str(service.releases))


def test_output_observation_error_releases_durable_lease() -> None:
    class FailingOutputRoot:
        def __init__(self) -> None:
            self.scans = 0

        @staticmethod
        def mkdir(**_values) -> None:
            return None

        def iterdir(self):
            self.scans += 1
            if self.scans == 1:
                return iter(())
            raise OSError("fixture output scan failure")

        @staticmethod
        def __str__() -> str:
            return "C:/fixture/decomposition-output"

    service = RecordingService()
    original = launcher.subprocess.run
    launcher.subprocess.run = lambda *args, **kwargs: subprocess.CompletedProcess(
        args=args[0], returncode=0
    )
    try:
        try:
            launcher._run_proposal(
                args=arguments(),
                workspace=Path("C:/fixture/workspace"),
                output_root=FailingOutputRoot(),
                source_head=SOURCE_HEAD,
                service=service,
            )
        except OSError as exc:
            require("output scan failure" in str(exc), str(exc))
        else:
            raise AssertionError("post-provider output scan failure did not propagate")
    finally:
        launcher.subprocess.run = original
    require(len(service.releases) == 1, str(service.releases))
    require("after provider exit" in service.releases[0]["reason"], str(service.releases))


def test_scheduler_proposal_rejects_wrong_run_directory_and_escaped_paths() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        output = root / "outputs"
        output.mkdir()
        service = RecordingService()
        args = arguments()
        args.run_id = "scheduler-nsc-777-exact-result"
        args.task_contract_sha256 = "a" * 64
        original = launcher.subprocess.run

        def wrong_directory(*args, **_kwargs):
            (output / "untrusted-other-run").mkdir()
            return subprocess.CompletedProcess(args=args[0], returncode=0)

        launcher.subprocess.run = wrong_directory
        try:
            result = launcher._run_proposal(
                args=args,
                workspace=root,
                output_root=output,
                source_head=SOURCE_HEAD,
                service=service,
            )
        finally:
            launcher.subprocess.run = original
        require(result == 3, str(result))
        require(len(service.releases) == 1, str(service.releases))

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        output = root / "outputs"
        output.mkdir()
        service = RecordingService()
        args = arguments()
        args.run_id = "scheduler-nsc-777-escaped-result"
        args.task_contract_sha256 = "a" * 64

        def escaped_paths(*command_args, **_kwargs):
            run_dir = output / args.run_id
            run_dir.mkdir()
            (run_dir / "decomposition_run_result.json").write_text(
                json.dumps(
                    {
                        "task_id": TASK_ID,
                        "run_id": args.run_id,
                        "run_status": "review_ready",
                        "source_identity": {"head_commit": SOURCE_HEAD},
                        "task_execution_contract_identity": {"sha256": "a" * 64},
                        "graph_delta_path": "../graph_delta.json",
                        "decomposition_result_path": "../decomposition_result.json",
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args=command_args[0], returncode=0)

        launcher.subprocess.run = escaped_paths
        try:
            result = launcher._run_proposal(
                args=args,
                workspace=root,
                output_root=output,
                source_head=SOURCE_HEAD,
                service=service,
            )
        finally:
            launcher.subprocess.run = original
        require(result == 3, str(result))
        require(len(service.releases) == 1, str(service.releases))
        require("non-canonical" in service.releases[0]["reason"], str(service.releases))


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
    original_replay = launcher.inspect_authorized_decomposition_replay
    launcher._git = lambda _source, *git_args: SOURCE_HEAD
    launcher.inspect_authorized_decomposition_replay = lambda **_values: SimpleNamespace(
        plan_id=PLAN_ID,
        authorized_source_head=SOURCE_HEAD,
        artifact_root=Path("C:/fixture/missing-output"),
        graph_delta=object(),
        inspection=SimpleNamespace(status="fresh_source", reason="fixture fresh"),
    )
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
        launcher.inspect_authorized_decomposition_replay = original_replay
    require(claims.released == [claims.receipt], str(claims.released))


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


def test_scheduler_decomposition_run_writes_identity_bound_terminal_result() -> None:
    originals = {
        name: getattr(launcher, name)
        for name in (
            "repo_root",
            "_git",
            "load_committed_task",
            "validate_decomposition_selection",
            "GhIssueBackend",
            "IssueWorkflowService",
            "DurableTaskCheckoutManager",
            "RealTaskObserver",
            "_acquire_workflow_lease",
            "_checkout_observation",
            "_run_proposal",
        )
    }

    class Service:
        releases = []
        snapshot = None

        @classmethod
        def find(cls, _task_id):
            return cls.snapshot

        @classmethod
        def release_decomposition_lease(cls, **values):
            cls.releases.append(dict(values))
            return {"status": "agent_ready"}

    class CheckoutManager:
        prepared_status = "created"

        def __init__(self, **values):
            self.checkout_path = Path(values["checkout_root"]) / values["task_id"]

        @staticmethod
        def expected_branch(_observation):
            return "nsc-777-decomposition-fixture"

        @staticmethod
        def prepare(_observation):
            if CheckoutManager.prepared_status == "oserror":
                raise OSError("fixture disk failure")
            return {
                "status": CheckoutManager.prepared_status,
                "reasons": ["fixture checkout conflict"],
            }

    class Observer:
        def __init__(self, *_args):
            pass

        @staticmethod
        def observe_goal_state():
            return {}

    def fake_git(_source, *args):
        if args[:3] == ("symbolic-ref", "--short", "HEAD"):
            return "main"
        if args[:2] == ("status", "--porcelain=v1"):
            return ""
        if args[:2] == ("rev-parse", "HEAD"):
            return SOURCE_HEAD
        raise AssertionError(f"unexpected git fixture command: {args}")

    try:
        launcher.repo_root = lambda value: value
        launcher._git = fake_git
        launcher.load_committed_task = lambda *_args: {
            "id": TASK_ID,
            "task_contract_sha256": "a" * 64,
        }
        launcher.validate_decomposition_selection = lambda *_args: None
        launcher.GhIssueBackend = lambda **_values: object()
        launcher.IssueWorkflowService = lambda **_values: Service()
        launcher.DurableTaskCheckoutManager = CheckoutManager
        launcher.RealTaskObserver = Observer
        launcher._checkout_observation = lambda **_values: {}

        cases = (
            (
                0,
                "human_action_required",
                {"status": "acquired", "issue_number": 777},
                "created",
                True,
                False,
                777,
                False,
                False,
            ),
            (
                3,
                "blocked",
                {"status": "acquired", "issue_number": 777},
                "created",
                True,
                False,
                777,
                False,
                False,
            ),
            (
                3,
                "blocked",
                {"status": "blocked", "reasons": ["claim conflict"]},
                "created",
                False,
                False,
                None,
                False,
                False,
            ),
            (
                3,
                "blocked",
                {"status": "acquired", "issue_number": 777},
                "blocked",
                False,
                True,
                777,
                False,
                False,
            ),
            (
                2,
                "error",
                {"status": "acquired", "issue_number": 777},
                "oserror",
                False,
                True,
                777,
                True,
                False,
            ),
            (
                2,
                "error",
                {"status": "acquired", "issue_number": 777},
                "created",
                True,
                True,
                777,
                False,
                True,
            ),
        )
        for index, (
            expected_code,
            terminal_status,
            lease_result,
            checkout_status,
            provider_expected,
            release_expected,
            expected_issue_number,
            resumed,
            proposal_raises,
        ) in enumerate(
            cases,
            start=1,
        ):
            with tempfile.TemporaryDirectory() as text:
                root = Path(text)
                source = root / "source"
                source.mkdir()
                run_id = f"scheduler-nsc-777-decomposition-{index}"
                launcher._acquire_workflow_lease = lambda **_values: (
                    object(),
                    lease_result,
                )
                CheckoutManager.prepared_status = checkout_status
                Service.releases = []
                Service.snapshot = (
                    SimpleNamespace(issue_number=777, state=None) if resumed else None
                )
                provider_calls = []

                def run_proposal(**_values):
                    provider_calls.append(True)
                    if proposal_raises:
                        Service.snapshot = SimpleNamespace(
                            valid=True,
                            issue_number=777,
                            state=SimpleNamespace(
                                state=WorkflowState.AGENT_WORKING,
                                worker_id="decomposition-scheduler-worker",
                            ),
                        )
                        raise OSError("fixture proposal publication failure")
                    return expected_code

                launcher._run_proposal = run_proposal
                command = [
                    "--task-id",
                    TASK_ID,
                    "--source",
                    str(source),
                    "--checkout-root",
                    str(root / "checkouts"),
                    "--output-root",
                    str(root / "provider-output"),
                    "--worker-id",
                    "decomposition-scheduler-worker",
                    "--scheduler-output-root",
                    str(root / "scheduler-output"),
                    "--run-id",
                    run_id,
                    "--admission-source-head",
                    SOURCE_HEAD,
                    "--task-contract-sha256",
                    "a" * 64,
                ]
                if resumed:
                    command.extend(("--admission-issue-number", "777"))
                result = launcher.main(command)
                require(result == expected_code, str(result))
                require(bool(provider_calls) is provider_expected, str(provider_calls))
                require(bool(Service.releases) is release_expected, str(Service.releases))
                result_path = (
                    root
                    / "scheduler-output"
                    / TASK_ID
                    / run_id
                    / "run_result.json"
                )
                payload = json.loads(result_path.read_text(encoding="utf-8"))
                require(payload["terminal_status"] == terminal_status, str(payload))
                require(payload["exit_code"] == expected_code, str(payload))
                require(payload["pid"] == os.getpid(), str(payload))
                require(
                    payload["issue_number"] == expected_issue_number,
                    str(payload),
                )
    finally:
        for name, value in originals.items():
            setattr(launcher, name, value)


def test_apply_resume_uses_historical_contract_and_skips_fresh_validation() -> None:
    current_head = "2" * 40
    old_hash = "a" * 64
    current_hash = "b" * 64
    prelease = SimpleNamespace(
        issue_number=777,
        valid=True,
        state=SimpleNamespace(
            phase=WorkflowPhase.DECOMPOSITION_APPLY,
            branch="main",
            task_contract_sha256=old_hash,
        ),
        events=(),
    )

    class Service:
        @staticmethod
        def find(_task_id):
            return prelease

    class CheckoutManager:
        def __init__(self, **values):
            self.checkout_path = Path(values["checkout_root"]) / values["task_id"]

    load_calls: list[dict] = []

    def load_task(_source, _task_id, **kwargs):
        load_calls.append(dict(kwargs))
        if kwargs:
            require(kwargs.get("commit") == SOURCE_HEAD, str(kwargs))
            require(kwargs.get("expected_sha256") == old_hash, str(kwargs))
            return {
                "id": TASK_ID,
                "task_contract_sha256": old_hash,
                "exclusive_resources": ["logical:historical-parent"],
            }
        return {
            "id": TASK_ID,
            "task_contract_sha256": current_hash,
            "exclusive_resources": [],
        }

    def fake_git(_source, *args):
        if args[:3] == ("symbolic-ref", "--short", "HEAD"):
            return "main"
        if args[:2] == ("status", "--porcelain=v1"):
            return ""
        if args[:2] == ("rev-parse", "HEAD"):
            return current_head
        raise AssertionError(f"unexpected git fixture command: {args}")

    acquired: list[dict] = []

    def acquire(**values):
        acquired.append(values)
        return object(), {"status": "acquired", "issue_number": 777}

    applied: list[dict] = []

    def apply_approved(**values):
        applied.append(values)
        return 0

    replay = SimpleNamespace(
        authorized_source_head=SOURCE_HEAD,
        inspection=SimpleNamespace(status="already_applied", reason="fixture replay"),
    )
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source = root / "source"
        source.mkdir()
        run_id = "scheduler-nsc-777-applied-replay"
        with (
            patch.object(launcher, "repo_root", side_effect=lambda value: value),
            patch.object(launcher, "_git", side_effect=fake_git),
            patch.object(launcher, "load_committed_task", side_effect=load_task),
            patch.object(
                launcher,
                "validate_decomposition_selection",
                side_effect=AssertionError(
                    "already-applied parent reached fresh decomposition validation"
                ),
            ),
            patch.object(launcher, "GhIssueBackend", return_value=object()),
            patch.object(launcher, "IssueWorkflowService", return_value=Service()),
            patch.object(launcher, "DurableTaskCheckoutManager", CheckoutManager),
            patch.object(
                launcher,
                "inspect_authorized_decomposition_replay",
                return_value=replay,
            ),
            patch.object(launcher, "_acquire_workflow_lease", side_effect=acquire),
            patch.object(
                launcher, "_apply_approved_plan", side_effect=apply_approved
            ) as apply_mock,
            patch.object(
                launcher,
                "_release_owned_decomposition_lease",
                return_value=True,
            ) as release_mock,
        ):
            result = launcher.main(
                [
                    "--task-id",
                    TASK_ID,
                    "--source",
                    str(source),
                    "--checkout-root",
                    str(root / "checkouts"),
                    "--output-root",
                    str(root / "provider-output"),
                    "--worker-id",
                    "decomposition-replay-worker",
                    "--scheduler-output-root",
                    str(root / "scheduler-output"),
                    "--run-id",
                    run_id,
                    "--admission-source-head",
                    current_head,
                    "--task-contract-sha256",
                    current_hash,
                    "--admission-issue-number",
                    "777",
                ]
            )
            retry_run_id = "scheduler-nsc-777-completion-retry"
            apply_mock.side_effect = launcher.DecompositionApplyRetryableError(
                "fixture remote-confirmed completion failure"
            )
            retry_result = launcher.main(
                [
                    "--task-id",
                    TASK_ID,
                    "--source",
                    str(source),
                    "--checkout-root",
                    str(root / "checkouts"),
                    "--output-root",
                    str(root / "provider-output"),
                    "--worker-id",
                    "decomposition-replay-worker",
                    "--scheduler-output-root",
                    str(root / "scheduler-output"),
                    "--run-id",
                    retry_run_id,
                    "--admission-source-head",
                    current_head,
                    "--task-contract-sha256",
                    current_hash,
                    "--admission-issue-number",
                    "777",
                ]
            )
        require(result == 0, str(result))
        require(retry_result == 3, str(retry_result))
        require(
            load_calls
            == [
                {},
                {"commit": SOURCE_HEAD, "expected_sha256": old_hash},
                {},
                {"commit": SOURCE_HEAD, "expected_sha256": old_hash},
            ],
            str(load_calls),
        )
        require(len(acquired) == 2, str(acquired))
        require(
            acquired[0]["task"]["task_contract_sha256"] == current_hash,
            str(acquired),
        )
        require(acquired[0]["source_head"] == current_head, str(acquired))
        require(
            acquired[0]["expected_workflow_contract_sha256"] == old_hash,
            str(acquired),
        )
        require(len(applied) == 1, str(applied))
        release_mock.assert_called_once()
        payload = json.loads(
            (
                root
                / "scheduler-output"
                / TASK_ID
                / run_id
                / "run_result.json"
            ).read_text(encoding="utf-8")
        )
        require(payload["terminal_status"] == "completed", str(payload))
        require(payload["task_contract_sha256"] == current_hash, str(payload))
        retry_payload = json.loads(
            (
                root
                / "scheduler-output"
                / TASK_ID
                / retry_run_id
                / "run_result.json"
            ).read_text(encoding="utf-8")
        )
        require(retry_payload["terminal_status"] == "blocked", str(retry_payload))
        require(retry_payload["exit_code"] == 3, str(retry_payload))


def main() -> int:
    tests = (
        test_proposal_failure_releases_durable_lease_without_killing_scheduler,
        test_stale_authorized_plan_releases_to_fresh_decomposition,
        test_malformed_proposal_artifact_releases_durable_lease,
        test_provider_start_error_releases_durable_lease,
        test_output_observation_error_releases_durable_lease,
        test_scheduler_proposal_rejects_wrong_run_directory_and_escaped_paths,
        test_apply_artifact_error_releases_global_claim,
        test_compose_command_is_exact_review_only_service,
        test_scheduler_decomposition_run_writes_identity_bound_terminal_result,
        test_apply_resume_uses_historical_contract_and_skips_fresh_validation,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"host decomposition launcher tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
