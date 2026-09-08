#!/usr/bin/env python3
"""1000-contract production scheduler/controller component simulation.

Only Git observation, Stage-2 observation, architect answers and worker processes
are fixture boundaries. Admission, reservations, routing, result verification,
controller waits and terminal receipt handling execute production code. This is
not evidence that 1000 real Issues, merges or decompositions have completed.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import shlex
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from Pipeline.TaskReviewAgent import prepare_synthetic_gauntlet as generation
from Pipeline.TaskReviewAgent.tests import polling_orchestrator_smoke_test as fixture
from Pipeline.TaskReviewAgent.tests import autonomous_graph_run_smoke_test as graph_fixture
from Pipeline.TaskReviewAgent import autonomous_graph_run as graph
from Pipeline.TaskReviewAgent.worker_result import initialize_worker_run, write_worker_result
from Pipeline.TaskReviewAgent.tests.architect_capacity_test import CapacityArchitect


class ScaleArchitect(CapacityArchitect):
    def __init__(self, values, *, runtime_configuration):
        super().__init__(values)
        # The response remains a deterministic fake; this pins the intended
        # architect route without claiming a paid Codex invocation occurred.
        self.runtime_configuration = runtime_configuration
        assert runtime_configuration.architect_provider == "codex"
        assert runtime_configuration.provider_allowlist == ("codex",)

    def __call__(self, **values):
        assert all(candidate["capacity_context"]["execution_provider"] ==
                   self.runtime_configuration.execution_provider for candidate in values["candidates"])
        self.desired = 6 if len(self.calls) % 10 == 5 else 10
        return super().__call__(**values)


def simulate():
    bundle, profile = generation.build_bundle(
        ROOT, "thousand", target_repository=generation.PRIVATE_REPOSITORY
    )
    tasks = {task_id: json.loads(bundle[Path(f"Tasks/{task_id}.yaml")])
             for task_id in profile["target_task_ids"]}
    policy_document = json.loads(
        bundle[
            Path(
                "Pipeline/TaskReviewAgent/"
                "authoritative_validation_policy.json"
            )
        ]
    )
    for task_id, task in tasks.items():
        task["task_contract_sha256"] = hashlib.sha256(bundle[Path(f"Tasks/{task_id}.yaml")]).hexdigest()
    counts = Counter()
    completed = set()
    expansions = {}
    launches = Counter()
    peak = 0
    with tempfile.TemporaryDirectory(prefix="thousand-scheduler-") as text:
        source, head = fixture.create_source(Path(text))
        old_contracts = dict(fixture.CONTRACTS)
        fixture.CONTRACTS.update({key: value["task_contract_sha256"] for key, value in tasks.items()})
        try:
            initial_manifest = graph_fixture.manifest(targets=tuple(tasks), excluded=("NSC-042",))
            runtime = replace(initial_manifest.runtime_configuration,
                              execution_provider="codex", architect_provider="codex",
                              provider_allowlist=("codex",), architect_min_confidence=0.65,
                              architect_max_invocations_per_poll=8, fatal_drain_seconds=0.0)
            architect = ScaleArchitect({key: fixture.advisory(
                key, head, exact_paths=tuple(value["provenance"]["expected_paths"]),
                work_type="decomposition" if value["provenance"].get("requires_decomposition") else "implementation",
                capability_tier="fast", shared_systems=(),
            ) for key, value in tasks.items()}, runtime_configuration=runtime)
            processes = fixture.ProcessFactory()
            clock = fixture.MutableClock()

            def planner(**values):
                counts["stage2_observations"] += 1
                excluded = set(values["excluded_task_ids"])
                ready = [key for key, task in tasks.items() if key not in excluded | completed
                         and set(task["depends_on"]) <= completed]
                concrete = [fixture._candidate(key) for key in ready
                            if not tasks[key]["provenance"].get("requires_decomposition")]
                decomposition = [{**fixture._candidate(key), "eligible": False,
                                  "reason_codes": ["execution_scope_not_single_agent"]}
                                 for key in ready if tasks[key]["provenance"].get("requires_decomposition")]
                return fixture.DispatchPlan(
                    schema_version="1.0", source_commit=head, mode="read_only_plan",
                    autonomous_dispatch=False, decision="fresh_candidate" if ready else "no_safe_work",
                    resume=None, selected_fresh_candidate=concrete[0] if concrete else None,
                    ranked_eligible_candidates=tuple(concrete), skipped_candidates=tuple(decomposition),
                    agent_ready_count=0, claim_observation={"status": "fixture"},
                )

            def reservations():
                counts["durable_reservation_observations"] += 1
                return ()

            def refresh(_source):
                counts["main_observations"] += 1
                return {"before": head, "after": head, "changed": False}

            scheduler, stream = fixture.make_orchestrator(
                source=source, planner=planner, architect=architect, processes=processes,
                tasks=tasks, max_workers=10, excluded_task_ids=("NSC-042",),
                source_refresher=refresh, reservation_observer=reservations,
                provider_allowlist=runtime.provider_allowlist,
                max_architect_invocations_per_poll=runtime.architect_max_invocations_per_poll,
                fatal_drain_seconds=runtime.fatal_drain_seconds,
                monotonic_clock=clock,
            )
            scheduler._current_admission_snapshot = fixture.FixtureAdmissionSnapshot(
                source=source,
                source_commit=head,
                tasks=tasks,
                policy_document=policy_document,
            )
            tree = fixture.git(source, "rev-parse", "HEAD^{tree}")
            manifest = replace(initial_manifest, runtime_configuration=runtime,
                               source_repository=str(source), initial_source_commit=head, initial_source_tree=tree)
            manifest_store = graph.JsonManifestStore(Path(text) / "manifest.json")
            manifest = manifest_store.create_or_load(manifest)
            assert manifest_store.load() == manifest
            assert manifest.runtime_configuration == architect.runtime_configuration
            assert manifest.runtime_configuration.execution_provider == scheduler.execution_provider == "codex"
            assert manifest.runtime_configuration.provider_allowlist == scheduler.provider_allowlist == ("codex",)
            broadened = replace(manifest, runtime_configuration=replace(runtime, provider_allowlist=("claude", "codex")))
            try:
                manifest_store.create_or_load(broadened)
            except graph.AutonomousGraphRunError:
                pass
            else:
                raise AssertionError("scale run accepted a broadened immutable provider allowlist")
            assert manifest_store.load() == manifest
            revision = 0

            def snapshot():
                nonlocal revision, peak
                revision += 1
                peak = max(peak, len(scheduler.active_assignments))
                assert len(scheduler.active_assignments) <= 10
                return graph_fixture.snapshot(
                    revision=revision, source_head=head, source_tree=tree, origin_head=head, initial_tree=tree,
                    tasks=tuple(graph.TaskObservation(key, "conformant" if key in completed
                                and set(expansions.get(key, ())) <= completed else "not_delivered",
                                tuple(expansions.get(key, ())))
                                for key in tasks),
                    issues=tuple(graph_fixture.managed_issue(key, "complete", "merge_closeout")
                                 for key in sorted(completed)),
                    active=tuple(scheduler.active_assignments),
                )

            def wait(_seconds):
                nonlocal head
                counts["waits"] += 1
                if not scheduler.active_assignments:
                    counts["idle_fallbacks"] += 1
                    assert counts["idle_fallbacks"] <= 10, "fixture made no durable progress"
                    clock.advance(_seconds)
                    return "fallback_elapsed"
                # The fixture publishes durable results before raising the wake.
                # No elapsed-time sleeps or OS worker processes are involved.
                for key, assignment in scheduler.active_assignments.items():
                    if key in completed:
                        continue
                    launches[key] += 1
                    assert launches[key] == 1, f"duplicate worker for {key}"
                    directory = initialize_worker_run(
                        output_root=scheduler.checkout_root / ".task-review-agent/outputs",
                        task_id=key, run_id=assignment.run_id, worker_id=assignment.worker_id,
                        started_at_utc=assignment.start_time_utc,
                    )
                    write_worker_result(
                        run_dir=directory, run_id=assignment.run_id, worker_id=assignment.worker_id,
                        task_id=key, source_head=assignment.source_head, task_contract_sha256=assignment.task_contract_sha256,
                        terminal_status="completed", outcome_authority="deterministic_scale_fixture",
                        issue_number=int(key[4:]), exit_code=0, pid=assignment.pid,
                    )
                    assignment.process.returncode = 0
                    completed.add(key)
                    if tasks[key]["provenance"].get("requires_decomposition"):
                        assert key not in expansions
                        child_ids = [f"NSC-{3000 + 2 * len(expansions) + index}" for index in range(2)]
                        expansions[key] = child_ids
                        for index, child_id in enumerate(child_ids):
                            child = deepcopy(tasks[key])
                            child.update(id=child_id, execution_scope="single_agent", parent=key)
                            child["depends_on"] = list(tasks[key]["depends_on"]) + (child_ids[:1] if index else [])
                            child["provenance"]["requires_decomposition"] = False
                            child["provenance"]["expected_paths"] = tasks[key]["provenance"]["expected_paths"][index * 2:index * 2 + 2]
                            child["exclusive_resources"] = [f"repo-file:{path}" for path in child["provenance"]["expected_paths"]]
                            child["task_contract_sha256"] = hashlib.sha256(json.dumps(child, sort_keys=True).encode()).hexdigest()
                            tasks[child_id] = child
                            fixture.CONTRACTS[child_id] = child["task_contract_sha256"]
                            architect.values[child_id] = fixture.advisory(child_id, head,
                                exact_paths=tuple(child["provenance"]["expected_paths"]),
                                work_type="implementation", capability_tier="fast", shared_systems=())
                        for consumer in tasks.values():
                            if key in consumer["depends_on"]:
                                consumer["depends_on"] = [dep for dep in consumer["depends_on"] if dep != key] + child_ids
                # Model the main movement caused by integrations in a live run.
                # This is explicitly an empty simulation checkpoint, not a fake
                # delivery commit. It invalidates architect decisions tied to the
                # previous exact main and preserves normal cooldown/cache policy.
                fixture.git(source, "commit", "--allow-empty", "-m", f"fixture: {len(completed)} completions")
                head = fixture.git(source, "rev-parse", "HEAD")
                counts["main_checkpoint_commits"] += 1
                architect.values = {key: replace(value, source_head=head)
                                    for key, value in architect.values.items()}
                # The component fixture owns its in-memory committed-task
                # universe. Rebind that exact universe to the simulated new
                # HEAD just as a live scheduler obtains a new bulk snapshot
                # after integrations move main.
                scheduler._current_admission_snapshot = fixture.FixtureAdmissionSnapshot(
                    source=source,
                    source_commit=head,
                    tasks=tasks,
                    policy_document=policy_document,
                )
                return "worker_returned"

            scheduler._wait_for_architect_activity = wait
            original_drain = scheduler.drain_active_workers
            def drain(**values):
                if scheduler.active_assignments:
                    wait(0)
                return original_drain(**values)
            scheduler.drain_active_workers = drain
            receipt_store = graph.JsonReceiptStore(Path(text) / "graph-complete.json")
            progress = graph.JsonProgressStore(Path(text) / "progress.json")
            controller = graph.AutonomousGraphController(
                manifest=manifest, scheduler=scheduler, scheduler_lock=graph_fixture.FakeLock(),
                snapshotter=snapshot, progress_store=progress, receipt_store=receipt_store,
            )
            # Activity transport is an OS boundary; production ownership and the
            # real controller's call to its wait port are still exercised.
            with patch.object(scheduler, "start_activity_listener", return_value=True), \
                 patch.object(scheduler, "close_activity_listener"), \
                 patch.object(scheduler, "reconcile_interrupted_architect_session", return_value=False):
                assert controller.run(max_steps=40).receipt is None
                assert 0 < len(completed) < 1040
                persisted = progress.load()
                resumed_manifest = manifest_store.load()
                assert resumed_manifest == manifest
                controller = graph.AutonomousGraphController(
                    manifest=resumed_manifest, scheduler=scheduler, scheduler_lock=graph_fixture.FakeLock(),
                    snapshotter=snapshot, progress_store=graph.JsonProgressStore(progress.path), receipt_store=receipt_store)
                assert controller.progress == persisted
                counts["controller_reconstructions"] += 1
                result = controller.run(max_steps=500)
                assert result.receipt is not None, result
                before = (len(processes.calls), len(architect.calls), revision, dict(counts))
                resumed = controller.run()
                assert resumed.receipt == result.receipt
                assert before == (len(processes.calls), len(architect.calls), revision, dict(counts))
            assert len(completed) == 1040 and len(expansions) == 20 and set(launches.values()) == {1}
            assert peak == 10, f"capacity was serialized: {peak}"
            assert not scheduler.active_assignments
            assert len(architect.calls) <= 2 * profile["dependency_waves"]
            assert counts["stage2_observations"] <= 1040 + 3 * profile["dependency_waves"]
            assert counts["durable_reservation_observations"] <= 1040 + 3 * profile["dependency_waves"]
            assert counts["waits"] <= 2 * profile["dependency_waves"]
            mixed = [batch for batch in architect.portfolio_calls
                     if any(tasks[key]["provenance"].get("requires_decomposition") for key in batch)
                     and any(not tasks[key]["provenance"].get("requires_decomposition") for key in batch)]
            assert len(mixed) >= 20, len(mixed)
            launch_events = [event for event in map(json.loads, stream.getvalue().splitlines())
                             if event["event"] == "worker_launched"]
            assert len(launch_events) == len(processes.calls) == 1040
            routed_work_types = Counter()
            for (command, _kwargs), event in zip(processes.calls, launch_events):
                assert event["argv"] == list(command), "durable route differs from actual worker argv"
                assert command.count("--provider-allowlist") == 1
                assert command[command.index("--provider-allowlist") + 1] == "codex"
                assert event["provider_allowlist"] == ["codex"]
                assert not any("claude" in argument.casefold() for argument in command), command
                assert command[command.index("--task-id") + 1] == event["task_id"]
                assert command[command.index("--run-id") + 1] == event["run_id"]
                work_type = event["work_type"]
                routed_work_types[work_type] += 1
                if work_type == "decomposition":
                    assert event["execution_provider"] == "independent_codex_roles"
                    assert event["decomposition_mode"] == "round_robin_d1b2"
                    assert command.count("--providers") == 1 and command[command.index("--providers") + 1] == "codex,codex"
                    assert command.count("--max-calls") == 1 and command[command.index("--max-calls") + 1] == "2"
                    assert "--enable-decomposition-session-pool" in command
                else:
                    assert work_type == "implementation" and event["execution_provider"] == "codex"
                    assert command.count("--execution-provider") == 1
                    assert command[command.index("--execution-provider") + 1] == "codex"
                    for flag, field in (("--crew-profile", "crew_profile"), ("--validation-profile", "validation_profile")):
                        assert command.count(flag) == 1 and command[command.index(flag) + 1] == event[field]
            assert routed_work_types == {"implementation": 1020, "decomposition": 20}, routed_work_types
            assert manifest_store.load() == manifest and result.receipt.manifest_sha256 == manifest.sha256
            return {**counts, "initial_contracts": 1000, "dynamic_children": 40, "simulated_worker_launches": len(processes.calls),
                    "architect_batches": len(architect.calls), "mixed_batches": len(mixed),
                    "maximum_active_workers": peak, "graph_snapshots": revision,
                    "execution_provider": runtime.execution_provider, "architect_provider": runtime.architect_provider,
                    "provider_allowlist": list(runtime.provider_allowlist), "routed_work_types": dict(routed_work_types),
                    "os_worker_processes": 0, "provider_calls": 0}
        finally:
            fixture.CONTRACTS.clear()
            fixture.CONTRACTS.update(old_contracts)


if __name__ == "__main__":
    commands = Counter()
    def audit(event, arguments):
        if event == "subprocess.Popen":
            executable, command = arguments[:2]
            if isinstance(command, str):
                command = shlex.split(command, posix=False)
            executable = executable or command[0].strip('"')
            assert Path(str(executable)).name.lower() in {"git", "git.exe"}, f"unexpected subprocess: {executable}"
            assert not {"fetch", "push", "pull", "clone", "ls-remote"}.intersection(command), "network Git forbidden"
            commands["total"] += 1
            for verb in ("log", "rev-list", "ls-tree", "show", "status", "rev-parse", "commit"):
                if verb in command:
                    commands[verb] += 1
                    break
    sys.addaudithook(audit)
    started = time.perf_counter()
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    result = run_with_synthetic_authority(simulate)
    # Admission observes immutable repository facts per source commit, not per
    # candidate and not per candidate-times-launch. Before that change this
    # same simulation spent 6,605 Git subprocesses, 6,306 of them rev-parse,
    # with 6,163 coming from one HEAD observation per candidate. These bounds
    # are deliberately tight so a return to per-candidate observation fails
    # here. There is no elapsed-time assertion: wall clock is not a contract.
    assert commands["rev-parse"] <= 1350, commands
    assert commands["total"] <= 1800, commands
    assert commands["log"] + commands["rev-list"] <= 3 * 100, commands
    print(json.dumps({"suite": "thousand-scheduler", "result": "PASS", **result,
                      "git_subprocesses": dict(commands), "network_commands": 0, "elapsed_time_sleeps": 0,
                      "duration_seconds": round(time.perf_counter() - started, 3)}, sort_keys=True))
