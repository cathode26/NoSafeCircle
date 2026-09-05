#!/usr/bin/env python3
"""Deterministic production-wiring tests for the autonomous graph CLI."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
from typing import Any
from unittest.mock import patch


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.autonomous_graph_run import (  # noqa: E402
    AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
    GRAPH_COMPLETE_RECEIPT_SCHEMA_VERSION,
    AutonomousRunManifest,
    AutonomousRuntimeConfiguration,
    CoherentGraphSnapshot,
    GraphCompleteReceipt,
    JsonManifestStore,
    JsonReceiptStore,
    ManagedIssueObservation,
    TaskObservation,
    autonomous_run_paths,
)
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowPhase,
    WorkflowState,
)
import Pipeline.TaskReviewAgent.run_autonomous_graph as cli  # noqa: E402


HEAD = "1" * 40
TREE = "2" * 40
REPOSITORY = "cathode26/NoSafeCircle-Homework-Rehearsal"
TASK = "NSC-922"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def manifest(source: Path, *, capacity: int = 2) -> AutonomousRunManifest:
    return AutonomousRunManifest(
        schema_version=AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
        run_id="autonomous-cli-test",
        source_repository=str(source.resolve()),
        github_repository=REPOSITORY,
        runtime_configuration=AutonomousRuntimeConfiguration(
            execution_provider="claude",
            execution_model=None,
            execution_max_turns=120,
            architect_provider="claude",
            architect_model=None,
            architect_max_turns=12,
            architect_min_confidence=0.7,
            architect_max_invocations_per_poll=3,
            architect_min_reanalysis_seconds=300.0,
            max_consecutive_observation_failures=3,
            fatal_drain_seconds=1800.0,
            fallback_seconds=300.0,
            synthetic_evidence_enabled=False,
        ),
        initial_source_commit=HEAD,
        initial_source_tree=TREE,
        target_task_ids=(TASK,),
        excluded_task_ids=("NSC-042",),
        max_capacity=capacity,
    )


def receipt(run_manifest: AutonomousRunManifest) -> GraphCompleteReceipt:
    counters = {
        "architect_invocations_total": 1,
        "fallback_waits_total": 0,
        "poll_cycles_total": 1,
        "synthetic_pump_calls_total": 1,
        "wakeups_total": 0,
        "worker_launches_total": 1,
    }
    body = {
        "schema_version": GRAPH_COMPLETE_RECEIPT_SCHEMA_VERSION,
        "manifest_sha256": run_manifest.sha256,
        "evidence_fingerprint": "3" * 64,
        "source_commit": HEAD,
        "source_tree": TREE,
        "relevant_task_ids": [TASK],
        "lifetime_counters": counters,
    }
    digest = hashlib.sha256(
        json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return GraphCompleteReceipt.from_dict({**body, "receipt_sha256": digest})


def common_argv(source: Path, checkout_root: Path) -> list[str]:
    return [
        "--source",
        str(source),
        "--checkout-root",
        str(checkout_root),
        "--run-id",
        "autonomous-cli-test",
        "--confirm-repository",
        REPOSITORY,
    ]


def pump_snapshot() -> CoherentGraphSnapshot:
    return CoherentGraphSnapshot(
        observation_revision=1,
        source_branch="main",
        source_attached=True,
        source_clean=True,
        source_head=HEAD,
        source_tree=TREE,
        origin_main_head=HEAD,
        initial_source_commit_is_ancestor=True,
        initial_source_tree=TREE,
        tasks=(TaskObservation(TASK, "needs_testing"),),
        managed_issues=(
            ManagedIssueObservation(
                task_id=TASK,
                state=WorkflowState.HUMAN_ACTION_REQUIRED,
                phase=WorkflowPhase.UNITY_RUNTIME_VALIDATION,
                state_version=1,
                last_event_id="4" * 64,
                head_commit=HEAD,
                human_handoff_commit=HEAD,
                worker_id=None,
                lease_id=None,
                decomposition_run_id=None,
                graph_delta_plan_id=None,
                last_event_evidence_sha256=None,
            ),
        ),
    )


def test_synthetic_pump_waits_for_worker_transition_and_d1c_recovery() -> None:
    created: list[dict[str, Any]] = []
    processed: list[str] = []

    class FakeProcessor:
        def __init__(self, **values: Any) -> None:
            created.append(values)

        def process_one(
            self, task_id: str, *, expected_source_head: str | None = None
        ) -> str:
            require(expected_source_head == HEAD, str(expected_source_head))
            processed.append(task_id)
            return task_id

    run_manifest = manifest(ROOT)
    pump = cli._SyntheticEvidencePump(
        manifest=run_manifest,
        source=ROOT,
        checkout_root=ROOT.parent,
        repository=REPOSITORY,
    )
    base = pump_snapshot()
    with patch.object(cli, "SyntheticHandoffProcessor", FakeProcessor):
        require(
            pump(replace(base, active_assignment_task_ids=(TASK,))) is None,
            "active worker reached synthetic validation",
        )
        require(
            pump(replace(base, pending_transition_task_ids=(TASK,))) is None,
            "pending Issue transition reached synthetic validation",
        )
        require(
            pump(
                replace(
                    base,
                    source_head="5" * 40,
                    origin_main_is_ancestor_of_source=True,
                    authorized_local_ahead_recovery_task_id=TASK,
                    authorized_local_ahead_recovery_commit="5" * 40,
                )
            )
            is None,
            "D1C recovery reached the exact-origin synthetic preflight",
        )
        require(created == [], f"processor opened without an eligible handoff: {created}")
        require(pump(base) == TASK, "eligible handoff did not run")
        require(pump(base) == TASK, "reusable processor did not run again")
    require(len(created) == 1, f"processor session was not reused: {created}")
    require(processed == [TASK, TASK], str(processed))


def test_new_run_persists_manifest_before_shared_factory_and_wires_exact_paths() -> None:
    with tempfile.TemporaryDirectory(prefix="autonomous-cli-", dir=ROOT) as text:
        fixture = Path(text)
        source = fixture / "source"
        checkout_root = fixture / "checkouts"
        source.mkdir()
        calls: list[dict[str, Any]] = []
        controller_values: list[dict[str, Any]] = []

        orchestrator = SimpleNamespace(
            active_assignments={},
            max_workers=2,
            excluded_task_ids=frozenset({"NSC-042"}),
            provider_allowlist=("codex",),
        )
        lock_events: list[str] = []

        class FakeManifestLock:
            def acquire(self) -> None:
                lock_events.append("manifest_acquire")

            def release(self) -> None:
                lock_events.append("manifest_release")

        class FakeRunLock:
            def acquire(self) -> None:
                lock_events.append("run_acquire")

            def release(self) -> None:
                lock_events.append("run_release")

        lock = FakeRunLock()

        def fake_factory(**values: Any) -> Any:
            paths = autonomous_run_paths(
                checkout_root=checkout_root,
                github_repository=REPOSITORY,
                run_id="autonomous-cli-test",
            )
            require(paths.manifest.is_file(), "scheduler was built before durable manifest")
            require(
                lock_events == ["manifest_acquire", "manifest_release"],
                "scheduler was built before the manifest lock was released",
            )
            calls.append(values)
            return SimpleNamespace(
                orchestrator=orchestrator,
                lock=lock,
                scheduler_id=values["scheduler_id"],
            )

        class FakeController:
            def __init__(self, **values: Any) -> None:
                controller_values.append(values)

            def run(self) -> Any:
                controller_values[-1]["scheduler_lock"].acquire()
                controller_values[-1]["scheduler_lock"].release()
                return SimpleNamespace(
                    evaluation=SimpleNamespace(
                        classification="blocked", reasons=("fixture",)
                    ),
                    cycle_status="fixture_blocked",
                    scheduler_fatal=False,
                    receipt=None,
                )

        with (
            patch.object(cli, "repo_root", side_effect=lambda value: Path(value)),
            patch.object(
                cli,
                "resolve_issue_backend_repository",
                return_value=REPOSITORY,
            ),
            patch.object(
                cli,
                "refresh_source_main",
                side_effect=lambda _source: require(
                    lock_events == ["manifest_acquire"],
                    "source refresh ran outside manifest lock",
                ),
            ) as refresh,
            patch.object(
                cli,
                "_git_text",
                side_effect=lambda _source, *args: TREE
                if args[-1].endswith("^{tree}")
                else HEAD,
            ),
            patch.object(cli, "SchedulerLock", return_value=FakeManifestLock()),
            patch.object(cli, "build_production_orchestrator", side_effect=fake_factory),
            patch.object(cli, "ProductionCoherentSnapshotter", return_value=object()),
            patch.object(cli, "AutonomousGraphController", FakeController),
            patch("sys.stdout", new=io.StringIO()),
        ):
            exit_code = cli.main(
                common_argv(source, checkout_root)
                + [
                    "--target-task-id",
                    TASK,
                    "--exclude-task-id",
                    "NSC-042",
                    "--max-workers",
                    "2",
                    "--execution-provider",
                    "codex",
                    "--architect-provider", "codex",
                    "--provider-allowlist", "codex",
                ]
            )

        require(exit_code == cli.EXIT_BLOCKED, f"wrong blocked exit: {exit_code}")
        refresh.assert_called_once_with(source.resolve())
        require(len(calls) == 1, str(calls))
        values = calls[0]
        require(values["provider_allowlist"] == ("codex",), str(values))
        require(values["max_workers"] == 2, str(values))
        require(values["excluded_task_ids"] == ("NSC-042",), str(values))
        require(values["execution_provider"] == "codex", str(values))
        require(values["architect_provider"] == "codex", str(values))
        require(values["event_journal_path"].name == "events.jsonl", str(values))
        require(len(controller_values) == 1, str(controller_values))
        paths = autonomous_run_paths(
            checkout_root=checkout_root,
            github_repository=REPOSITORY,
            run_id="autonomous-cli-test",
        )
        require(paths.manifest.is_file(), "controller was built before durable manifest")
        require(controller_values[0]["scheduler"] is orchestrator, "wrong scheduler")
        require(controller_values[0]["scheduler_lock"] is lock, "wrong lock")
        require(
            lock_events
            == [
                "manifest_acquire",
                "manifest_release",
                "run_acquire",
                "run_release",
            ],
            str(lock_events),
        )


def test_completed_resume_uses_receipt_without_refresh_factory_or_observation() -> None:
    with tempfile.TemporaryDirectory(prefix="autonomous-resume-", dir=ROOT) as text:
        fixture = Path(text)
        source = fixture / "source"
        checkout_root = fixture / "checkouts"
        source.mkdir()
        run_manifest = manifest(source)
        paths = autonomous_run_paths(
            checkout_root=checkout_root,
            github_repository=REPOSITORY,
            run_id=run_manifest.run_id,
        )
        JsonManifestStore(paths.manifest).create_or_load(run_manifest)
        exact_receipt = receipt(run_manifest)
        JsonReceiptStore(paths.receipt).save(exact_receipt)

        with (
            patch.object(cli, "repo_root", side_effect=lambda value: Path(value)),
            patch.object(
                cli,
                "resolve_issue_backend_repository",
                return_value=REPOSITORY,
            ),
            patch.object(
                cli,
                "refresh_source_main",
                side_effect=AssertionError("completed resume refreshed Git"),
            ),
            patch.object(
                cli,
                "build_production_orchestrator",
                side_effect=AssertionError("completed resume built scheduler"),
            ),
            patch.object(
                cli,
                "ProductionCoherentSnapshotter",
                side_effect=AssertionError("completed resume observed GitHub"),
            ),
            patch("sys.stdout", new=io.StringIO()) as output,
        ):
            exit_code = cli.main(common_argv(source, checkout_root))

        require(exit_code == cli.EXIT_COMPLETE, f"resume returned {exit_code}")
        require("already_complete" in output.getvalue(), output.getvalue())


def test_resume_mismatch_and_terminal_exit_codes_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="autonomous-exits-", dir=ROOT) as text:
        fixture = Path(text)
        source = fixture / "source"
        checkout_root = fixture / "checkouts"
        source.mkdir()
        run_manifest = manifest(source)
        paths = autonomous_run_paths(
            checkout_root=checkout_root,
            github_repository=REPOSITORY,
            run_id=run_manifest.run_id,
        )
        JsonManifestStore(paths.manifest).create_or_load(run_manifest)
        with (
            patch.object(cli, "repo_root", side_effect=lambda value: Path(value)),
            patch.object(
                cli,
                "resolve_issue_backend_repository",
                return_value=REPOSITORY,
            ),
            patch("sys.stderr", new=io.StringIO()),
        ):
            mismatch = cli.main(
                common_argv(source, checkout_root)
                + ["--target-task-id", "NSC-923"]
            )
        require(mismatch == cli.EXIT_ADAPTER_FAILURE, str(mismatch))
        with (
            patch.object(cli, "repo_root", side_effect=lambda value: Path(value)),
            patch.object(
                cli,
                "resolve_issue_backend_repository",
                return_value=REPOSITORY,
            ),
            patch.object(
                cli,
                "build_production_orchestrator",
                side_effect=AssertionError("runtime mismatch reached scheduler factory"),
            ),
            patch("sys.stderr", new=io.StringIO()),
        ):
            runtime_mismatch = cli.main(
                common_argv(source, checkout_root)
                + ["--enable-synthetic-evidence"]
            )
        require(runtime_mismatch == cli.EXIT_ADAPTER_FAILURE, str(runtime_mismatch))

        def invoke(classification: str, *, fatal: bool = False) -> int:
            class FakeLock:
                def acquire(self) -> None:
                    pass

                def release(self) -> None:
                    pass

            binding = SimpleNamespace(
                orchestrator=SimpleNamespace(
                    active_assignments={},
                    max_workers=2,
                    excluded_task_ids=frozenset({"NSC-042"}),
                ),
                lock=FakeLock(),
                scheduler_id="fixture-scheduler",
            )

            class FakeController:
                def __init__(self, **_values: Any) -> None:
                    pass

                def run(self) -> Any:
                    return SimpleNamespace(
                        evaluation=SimpleNamespace(
                            classification=classification, reasons=()
                        ),
                        cycle_status="fixture",
                        scheduler_fatal=fatal,
                        receipt=None,
                    )

            with (
                patch.object(cli, "repo_root", side_effect=lambda value: Path(value)),
                patch.object(
                    cli,
                    "resolve_issue_backend_repository",
                    return_value=REPOSITORY,
                ),
                patch.object(cli, "build_production_orchestrator", return_value=binding),
                patch.object(cli, "ProductionCoherentSnapshotter", return_value=object()),
                patch.object(cli, "AutonomousGraphController", FakeController),
                patch("sys.stdout", new=io.StringIO()),
            ):
                return cli.main(common_argv(source, checkout_root))

        require(invoke("deadlock") == cli.EXIT_DEADLOCK, "wrong deadlock exit")
        require(invoke("blocked", fatal=True) == cli.EXIT_SCHEDULER_FATAL, "wrong fatal exit")


def test_provider_restriction_is_persisted_and_cannot_change_on_resume() -> None:
    with tempfile.TemporaryDirectory() as text:
        legacy = manifest(Path(text))
        original = legacy.to_dict()
        require("provider_allowlist" not in original["runtime_configuration"], str(original))
        require(AutonomousRunManifest.from_dict(original).sha256 == legacy.sha256,
                "legacy manifest identity changed")
        runtime = replace(legacy.runtime_configuration, execution_provider="codex",
                          architect_provider="codex", provider_allowlist=("codex",))
        run = replace(legacy, runtime_configuration=runtime)
        store = JsonManifestStore(Path(text) / "manifest.json")
        store.create_or_load(run)
        restored = store.load()
        require(restored is not None and restored.runtime_configuration.provider_allowlist == ("codex",),
                "provider restriction was not durable")
        args = cli.build_parser().parse_args(common_argv(Path(text), Path(text) / "checkouts"))
        require(cli._runtime_configuration(args, runtime) == runtime, "omitted resume broadened providers")
        for requested in (("claude", "codex"), ("claude",)):
            args.provider_allowlist = requested
            try:
                cli._runtime_configuration(args, runtime)
            except ValueError as exc:
                require("differs from the persisted run" in str(exc), str(exc))
            else:
                raise AssertionError("resume accepted changed provider permission")
        for field in ("architect_provider", "execution_provider"):
            try:
                replace(runtime, **{field: "claude"})
            except ValueError as exc:
                require("not in provider_allowlist" in str(exc), str(exc))
            else:
                raise AssertionError(f"restricted run accepted Claude {field}")


def main() -> int:
    tests = [
        test_provider_restriction_is_persisted_and_cannot_change_on_resume,
        test_synthetic_pump_waits_for_worker_transition_and_d1c_recovery,
        test_new_run_persists_manifest_before_shared_factory_and_wires_exact_paths,
        test_completed_resume_uses_receipt_without_refresh_factory_or_observation,
        test_resume_mismatch_and_terminal_exit_codes_fail_closed,
    ]
    for test in tests:
        test()
    print(f"autonomous graph CLI smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
