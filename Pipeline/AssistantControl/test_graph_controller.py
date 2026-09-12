"""Focused offline tests for the bounded AssistantControl graph loop."""
from __future__ import annotations

import contextlib
import io
import json
from dataclasses import replace
import multiprocessing
import os
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl.automation_policy import is_synthetic_gauntlet
from Pipeline.AssistantControl import __main__ as assistant_cli
from Pipeline.AssistantControl import checkouts as checkouts_module
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.graph_controller import (
    ControllerOwnerActiveError,
    DELEGATE_SAFE_ACTIONS,
    GraphController,
    GraphPolicy,
    automatic_scope_plan,
)
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


def _read_record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _fixture_controller(source, checkout_root) -> GraphController:
    return GraphController(
        Checkouts(Path(source), Path(checkout_root)),
        GraphPolicy(targets=("NSC-899",), target_branch="master"),
        {"provider": "claude", "execution_model": "fixture"},
    )


def _execute_owned(controller: GraphController, action: dict) -> dict:
    with controller._controller_owner(
        uuid.uuid4().hex, max_actions=1, allowed_actions=None,
    ):
        return controller.execute(action)


def _controller_lock_process(
    source: str, checkout_root: str, mode: str, ready, release, planned,
) -> None:
    controller = _fixture_controller(source, checkout_root)
    if mode != "owner":
        def forbidden_plan():
            planned.set()
            return {"status": "complete", "next_actions": []}

        controller.plan = forbidden_plan
        try:
            if mode == "preflight":
                controller.persist_preflight()
            else:
                controller.run(max_actions=1)
        except ControllerOwnerActiveError:
            return
        raise AssertionError("contending controller unexpectedly acquired ownership")

    first_plan = True

    def held_plan():
        nonlocal first_plan
        if not first_plan:
            return {"status": "complete", "next_actions": []}
        first_plan = False
        ready.set()
        if not release.wait(20):
            raise RuntimeError("controller lock fixture timed out")
        return {"status": "actionable", "next_actions": [
            {"kind": "auto_approve", "task_id": "NSC-899"},
        ]}

    controller.plan = held_plan
    controller.execute = lambda _action: {"status": "fixture"}
    controller.run(max_actions=1)


class GraphControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        self.git("init")
        name, email = validated_agent_git_identity()
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)
        (self.source / "Tasks").mkdir()
        (self.source / "Assets/Feature/Scripts").mkdir(parents=True)
        (self.source / "Assets/Feature/Tests/Editor").mkdir(parents=True)
        (self.source / "Assets/Feature/Scripts/.gitkeep").write_text("", encoding="utf-8")
        (self.source / "Assets/Feature/Tests/Editor/GauntletTests.cs").write_text(
            "class GauntletTests {}\n", encoding="utf-8",
        )
        self.write_task("NSC-899", origin="human_approved_synthetic_gauntlet")
        self.write_task("NSC-042", origin="human_scope_correction")
        self.write_task(
            "NSC-898", origin="human_approved_synthetic_gauntlet",
            execution_scope="needs_execution_decomposition",
        )
        self.write_task(
            "NSC-1011", origin="progressive_decomposition", parent="NSC-898",
        )
        self.write_task(
            "NSC-1010", origin="human_approved_synthetic_gauntlet",
            depends_on=["NSC-1011"],
        )
        self.git("add", ".")
        self.git("commit", "-m", "graph fixture")
        self.head = self.git("rev-parse", "HEAD").decode().strip()
        self.manager = Checkouts(self.source, Path(self.temp.name) / "checkouts")

    def git(self, *args: str) -> bytes:
        return subprocess.run(
            ["git", "-C", str(self.source), *args], capture_output=True, check=True,
        ).stdout

    def write_task(
        self, task_id: str, *, origin: str, execution_scope: str = "single_agent",
        parent: str = "NSC-001", depends_on: list[str] | None = None,
        gauntlet_id: str | None = None,
    ) -> None:
        number = task_id.removeprefix("NSC-")
        value = {
            "schema_version": "2.0", "id": task_id, "title": task_id,
            "contract_revision": 1, "contract_disposition": "active",
            "kind": "implementation", "type": "engineering-validation",
            "execution_scope": execution_scope,
            "decomposition_state": "concrete",
            "decomposition_reason": "fixture",
            "execution_reason": "fixture", "parent": parent,
            "depends_on": depends_on or [],
            "exclusive_resources": [
                f"repo-file:Assets/Feature/Scripts/Gauntlet{number}.cs",
                f"repo-file:Assets/Feature/Scripts/Gauntlet{number}.cs.meta",
            ],
            "acceptance_criteria": [],
            "completion_gates": [{
                "gate_id": "VAL-001", "reference": "fixture",
                "requirement": (
                    "Unity EditMode filter Fixture.GauntletTests."
                    f"Gauntlet{number}HasExpectedValue passes."
                ),
            }],
            "downstream_integration_obligations": [],
            "basis": "human_approved_engineering_guidance",
            "source_scope": "engineering", "confidence": "high",
            "provenance": {
                "origin": origin,
                **({"gauntlet_id": gauntlet_id} if gauntlet_id else {}),
            },
        }
        (self.source / f"Tasks/{task_id}.yaml").write_text(json.dumps(value), encoding="utf-8")

    def controller(self, *targets: str, auto: bool = True) -> GraphController:
        return GraphController(
            self.manager,
            GraphPolicy(
                targets=targets,
                auto_approve_gauntlet=auto,
                target_branch="master",
            ),
            {"provider": "claude", "execution_model": "fixture"},
        )

    def test_automatic_scope_uses_exact_new_files_and_resolves_committed_test(self):
        task = load_committed_task(self.source, "NSC-899", commit=self.head)
        plan = automatic_scope_plan(self.source, task, self.head)
        self.assertEqual((), plan.existing_implementation_paths)
        self.assertEqual(
            ("Assets/Feature/Scripts/Gauntlet899.cs",),
            plan.new_implementation_paths,
        )
        self.assertEqual(
            ("Assets/Feature/Tests/Editor/GauntletTests.cs",),
            plan.existing_test_paths,
        )

    def test_target_expansion_and_dependencies_are_rechecked(self):
        plan = self.controller("NSC-898", "NSC-1010").plan()
        self.assertIn("NSC-1011", plan["in_scope"])
        self.assertIn(
            {"kind": "decompose", "task_id": "NSC-898"},
            plan["next_actions"],
        )
        blocked = {item["task_id"]: item for item in plan["blocked"]}
        self.assertEqual(["NSC-1011"], blocked["NSC-1010"]["dependencies"])

        dependency_plan = self.controller("NSC-1010").plan()
        self.assertEqual(["NSC-1010", "NSC-1011"], dependency_plan["in_scope"])
        self.assertEqual("prepare", dependency_plan["next_actions"][0]["kind"])
        self.assertEqual("NSC-1011", dependency_plan["next_actions"][0]["task_id"])

    def test_needs_testing_without_receipt_does_not_complete_task(self):
        controller = self.controller("NSC-899")
        tasks = controller._contracts(self.head)
        with patch(
            "Pipeline.AssistantControl.graph_controller.inspect_dependencies",
            return_value={"task_state": {"state": "needs_testing"}},
        ):
            self.assertFalse(
                controller._task_complete("NSC-899", tasks, self.head, {}, set())
            )

    def test_decomposed_parent_requires_matching_application_receipt(self):
        task_path = self.source / "Tasks/NSC-898.yaml"
        parent = json.loads(task_path.read_text(encoding="utf-8"))
        parent.update(
            decomposition_state="decomposed",
            decomposition_children=["NSC-1011"],
        )
        task_path.write_text(json.dumps(parent), encoding="utf-8")
        self.git("add", "Tasks/NSC-898.yaml")
        self.git("commit", "-m", "apply decomposition fixture")
        head = self.git("rev-parse", "HEAD").decode().strip()
        tasks = self.controller("NSC-898")._contracts(head)
        controller = self.controller("NSC-898")
        self.assertFalse(controller._applied_decomposition("NSC-898", tasks["NSC-898"], head))
        self.manager.records.mkdir(parents=True, exist_ok=True)
        write_record(
            self.manager.records / "NSC-898.decomposition.json",
            {
                "schema_version": "assistant-decomposition/v1",
                "task_id": "NSC-898",
                "source": str(self.source.resolve()),
                "status": "applied",
                "applied_commit": head,
                "child_ids": ["NSC-1011"],
                "application": {"new_commit_sha": head},
            },
        )
        self.assertTrue(controller._applied_decomposition("NSC-898", tasks["NSC-898"], head))
        saved = json.loads(
            (self.manager.records / "NSC-898.decomposition.json").read_text()
        )
        saved["child_ids"] = ["NSC-9999"]
        write_record(self.manager.records / "NSC-898.decomposition.json", saved)
        self.assertFalse(controller._applied_decomposition("NSC-898", tasks["NSC-898"], head))

    def test_reviewed_decomposition_applies_against_current_compatible_source(self):
        self.manager.records.mkdir(parents=True, exist_ok=True)
        write_record(
            self.manager.records / "NSC-898.decomposition.json",
            {
                "schema_version": "assistant-decomposition/v1",
                "task_id": "NSC-898",
                "run_id": "fixture-reviewed-decomposition",
                "source_commit": self.head,
                "status": "review_ready",
            },
        )
        (self.source / "unrelated-implementation.txt").write_text(
            "integrated\n", encoding="utf-8",
        )
        self.git("add", "unrelated-implementation.txt")
        self.git("commit", "-m", "integrate unrelated implementation")
        current_head = self.git("rev-parse", "HEAD").decode().strip()

        action = self.controller("NSC-898").plan()["next_actions"][0]
        self.assertEqual("apply_decomposition", action["kind"])
        self.assertEqual(self.head, json.loads(
            (self.manager.records / "NSC-898.decomposition.json").read_text()
        )["source_commit"])
        self.assertEqual(current_head, action["source_commit"])

    def test_preflight_persists_exact_scope_without_executing_actions(self):
        controller = self.controller("NSC-899", "NSC-898")

        plan = controller.persist_preflight()

        saved = json.loads(controller.state_path.read_text(encoding="utf-8"))
        self.assertEqual("preflight", saved["status"])
        self.assertEqual(plan, saved["preflight_plan"])
        self.assertFalse(plan["mutations_performed"])
        self.assertFalse(controller.event_path.exists())
        self.assertEqual(
            ["graph-controller.json", "graph-controller.lock"],
            sorted(path.name for path in self.manager.records.iterdir()),
        )

    def test_execute_refuses_without_owned_invocation(self):
        controller = self.controller("NSC-899")
        action = {"kind": "prepare", "task_id": "NSC-899", "source_commit": self.head}
        with self.assertRaisesRegex(RuntimeError, "active controller invocation"):
            controller.execute(action)
        self.assertFalse(self.manager.records.exists())

    def test_prepared_task_advances_prepare_scope_reserve_without_provider(self):
        controller = self.controller("NSC-899")
        first = controller.plan()
        self.assertEqual("prepare", first["next_actions"][0]["kind"])
        _execute_owned(controller, first["next_actions"][0])
        second = controller.plan()
        self.assertEqual("scope", second["next_actions"][0]["kind"])
        _execute_owned(controller, second["next_actions"][0])
        third = controller.plan()
        self.assertEqual("reserve", third["next_actions"][0]["kind"])
        _execute_owned(controller, third["next_actions"][0])
        fourth = controller.plan()
        self.assertEqual("start_worker", fourth["next_actions"][0]["kind"])
        with self.assertRaisesRegex(ValueError, "authorize-provider-spend"):
            _execute_owned(controller, fourth["next_actions"][0])

    def test_failed_prepare_without_checkout_retries_before_scope(self):
        controller = self.controller("NSC-899")
        prepare = controller.plan()["next_actions"][0]
        real_git = checkouts_module.git

        def fail_clone(repository, *args, **kwargs):
            if args and args[0] == "clone":
                raise RuntimeError("fixture clone failure")
            return real_git(repository, *args, **kwargs)

        with patch("Pipeline.AssistantControl.checkouts.git", side_effect=fail_clone):
            with self.assertRaisesRegex(RuntimeError, "fixture clone failure"):
                _execute_owned(controller, prepare)

        record_path = self.manager.records / "NSC-899.json"
        failed_record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual("preparing", failed_record["status"])
        self.assertFalse(Path(failed_record["checkout"]).exists())
        self.assertFalse(Path(failed_record["staging"]).exists())

        (self.source / "controller-repair.txt").write_text("fixed\n", encoding="utf-8")
        self.git("add", "controller-repair.txt")
        self.git("commit", "-m", "controller repair")
        repaired_head = self.git("rev-parse", "HEAD").decode().strip()

        with self.assertRaisesRegex(ValueError, "Source commit changed after failed preparation"):
            self.manager.prepare("NSC-899")
        recovery = controller.plan()["next_actions"][0]
        self.assertEqual("prepare", recovery["kind"])
        self.assertEqual(repaired_head, recovery["source_commit"])
        recovered = _execute_owned(controller, recovery)
        self.assertEqual("prepared", recovered["status"])
        self.assertEqual(repaired_head, recovered["source_commit"])
        self.assertNotEqual(failed_record["staging"], recovered["staging"])
        self.assertEqual("scope", controller.plan()["next_actions"][0]["kind"])

    def test_gauntlet_can_auto_approve_but_042_always_waits_for_vincent(self):
        for task_id in ("NSC-899", "NSC-042"):
            self.manager.prepare(task_id, expected_commit=self.head)
            path = self.manager.records / f"{task_id}.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            record["status"] = "awaiting_human"
            record["candidate"] = {"commit": self.head, "tree": self.git("rev-parse", "HEAD^{tree}").decode().strip()}
            write_record(path, record)
        gauntlet = self.controller("NSC-899").plan()
        self.assertEqual("auto_approve", gauntlet["next_actions"][0]["kind"])
        human = self.controller("NSC-042").plan()
        self.assertEqual([], human["next_actions"])
        self.assertEqual("awaiting_human", human["status"])
        self.assertEqual("NSC-042", human["waiting_human"][0]["task_id"])
        self.assertTrue(is_synthetic_gauntlet(self.source, "NSC-899", self.head))
        self.assertFalse(is_synthetic_gauntlet(self.source, "NSC-042", self.head))

    def test_fresh_replay_gauntlet_identity_is_eligible_for_auto_approval(self):
        self.write_task(
            "NSC-1099", origin="assistant_control_local_gauntlet_replay",
            gauntlet_id="assistant-control-local-replay-v1",
        )
        self.git("add", "Tasks/NSC-1099.yaml")
        self.git("commit", "-m", "fresh replay fixture")
        head = self.git("rev-parse", "HEAD").decode().strip()
        self.assertTrue(is_synthetic_gauntlet(self.source, "NSC-1099", head))

    def test_stale_policy_failure_syncs_after_source_policy_repair(self):
        observed = self.manager.prepare("NSC-899", expected_commit=self.head)
        path = self.manager.records / "NSC-899.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record.update(
            status="validation_failed",
            candidate={"commit": self.head, "tree": self.git("rev-parse", "HEAD^{tree}").decode().strip()},
            candidate_validation_failure={
                "candidate_commit": self.head,
                "validation_error": "authoritative validation policy for NSC-899 is stale",
            },
        )
        write_record(path, record)
        (self.source / "policy-fix.txt").write_text("fixed\n", encoding="utf-8")
        self.git("add", "policy-fix.txt")
        self.git("commit", "-m", "repair validation policy")
        source_head = self.git("rev-parse", "HEAD").decode().strip()
        plan = self.controller("NSC-899").plan()
        self.assertEqual({
            "kind": "sync_candidate", "task_id": "NSC-899",
            "candidate_commit": self.head, "source_commit": source_head,
        }, plan["next_actions"][0])

    def test_dirty_task_graph_fails_before_any_action(self):
        (self.source / "Tasks/NSC-899.yaml").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "local edits"):
            self.controller("NSC-899").plan()

    def test_real_process_run_and_preflight_contenders_cannot_mutate_or_plan(self):
        process_context = multiprocessing.get_context("spawn")
        checkout_root = Path(self.temp.name) / "process-lock-checkouts"
        preflight_controller = _fixture_controller(self.source, checkout_root)
        preflight_controller.persist_preflight()
        preflight_state = _read_record(preflight_controller.state_path)
        preflight = preflight_state["preflight_binding"]
        preflight_state["history"] = [{"legacy": "kept"}]
        write_record(preflight_controller.state_path, preflight_state)
        ready, release, planned = (process_context.Event() for _ in range(3))
        arguments = (str(self.source), str(checkout_root), ready, release, planned)
        owner = process_context.Process(
            target=_controller_lock_process,
            args=(*arguments[:2], "owner", *arguments[2:]),
        )
        contenders = [process_context.Process(
            target=_controller_lock_process,
            args=(*arguments[:2], mode, *arguments[2:]),
        ) for mode in ("run", "preflight")]

        def stop(process):
            if process.pid is None:
                return
            if process.is_alive():
                process.terminate()
            process.join(5)

        for contender in contenders:
            self.addCleanup(stop, contender)
        self.addCleanup(stop, owner)
        owner.start()
        self.assertTrue(ready.wait(10), f"owner failed before barrier: {owner.exitcode}")

        records = preflight_controller.manager.records
        owner_record = _read_record(records / "graph-controller-owner.json")
        running = _read_record(records / "graph-controller.json")
        started_events = _read_events(records / "graph-controller-events.jsonl")
        invocation_id = owner_record["invocation_id"]
        fields = (
            "status", "pid", "source", "source_commit", "source_branch",
            "targets", "checkout_root", "capacity", "lock_path",
        )
        self.assertEqual((
            "controller_started", owner.pid, str(self.source.resolve()), self.head, "master",
            ["NSC-899"], str(checkout_root.resolve()), 1,
            str(records / "graph-controller.lock"),
        ), tuple(owner_record[field] for field in fields))
        self.assertRegex(owner_record["started_at_utc"], r"\+00:00$")
        self.assertEqual(preflight, owner_record["preflight_binding"])
        self.assertEqual(preflight_controller._policy_fields(), owner_record["policy"])
        self.assertEqual(preflight["policy_sha256"], owner_record["policy_sha256"])
        self.assertEqual(preflight["worker_config_sha256"], owner_record["worker_config_sha256"])
        if os.name == "nt":
            self.assertEqual(owner.pid, owner_record["process_identity"]["pid"])
            self.assertIsInstance(owner_record["process_identity"]["created_ticks"], int)
        self.assertEqual(("running", invocation_id), (
            running["status"], running["invocation_id"],
        ))
        self.assertEqual([("controller_started", invocation_id)], [
            (event["event"], event["invocation_id"]) for event in started_events
        ])
        paths = [records / name for name in (
            "graph-controller.json", "graph-controller-owner.json",
            "graph-controller-events.jsonl",
        )]
        before = {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths
        }
        self.assertTrue((records / "graph-controller.lock").is_file())
        for contender in contenders:
            planned.clear()
            contender.start()
            contender.join(5)
            self.assertFalse(contender.is_alive(), "contender did not fail immediately")
            self.assertEqual(0, contender.exitcode)
            self.assertEqual(before, {
                path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths
            })
            self.assertFalse(planned.is_set())

        release.set()
        owner.join(10)
        self.assertFalse(owner.is_alive(), "owner did not release")
        self.assertEqual(0, owner.exitcode)
        events = _read_events(records / "graph-controller-events.jsonl")
        self.assertEqual(
            ["controller_started", "action_started", "action_completed", "controller_released"],
            [event["event"] for event in events],
        )
        self.assertEqual({invocation_id}, {event["invocation_id"] for event in events})
        self.assertEqual(events[1]["action_id"], events[2]["action_id"])
        final_state = _read_record(records / "graph-controller.json")
        self.assertEqual("action_limit_reached", final_state["status"])
        self.assertEqual(invocation_id, final_state["invocation_id"])
        self.assertEqual({"legacy": "kept"}, final_state["history"][0])
        self.assertTrue(all(
            item["invocation_id"] == invocation_id for item in final_state["history"][1:]
        ))
        released = _read_record(records / "graph-controller-owner.json")
        self.assertEqual(("controller_released", "returned", invocation_id), (
            released["status"], released["outcome"], released["invocation_id"],
        ))

    def test_startup_failure_and_run_failures_release_for_reacquisition(self):
        cases = (
            ("startup", RuntimeError("metadata failed"), "startup_failed", None),
            ("exception", RuntimeError("planning failed"), "exception", "blocked"),
            ("interrupt", KeyboardInterrupt(), "interrupted", "interrupted"),
        )
        for label, failure, outcome, graph_status in cases:
            with self.subTest(label=label):
                manager = Checkouts(
                    self.source, Path(self.temp.name) / f"{label}-checkouts",
                )
                controller = _fixture_controller(self.source, manager.root)
                target = "_source_snapshot" if label == "startup" else "plan"
                with patch.object(controller, target, side_effect=failure):
                    with self.assertRaises(type(failure)):
                        controller.run(max_actions=1)

                released = _read_record(controller.owner_path)
                self.assertEqual("controller_released", released["status"])
                self.assertEqual(outcome, released["outcome"])
                events = _read_events(controller.event_path)
                self.assertEqual("controller_released", events[-1]["event"])
                self.assertEqual(released["invocation_id"], events[-1]["invocation_id"])
                state = (_read_record(controller.state_path)
                         if controller.state_path.exists() else {})
                self.assertEqual(graph_status, state.get("status"))

                with patch.object(
                    controller, "plan", return_value={"status": "complete", "next_actions": []},
                ):
                    result = controller.run(max_actions=1)
                self.assertEqual("complete", result["status"])
                reacquired = _read_record(controller.owner_path)
                self.assertEqual("controller_released", reacquired["status"])
                self.assertNotEqual(released["invocation_id"], reacquired["invocation_id"])

    def test_delegate_safe_mode_hands_provider_launch_back_without_starting_it(self):
        self.assertEqual(
            frozenset({"prepare", "refresh_prepared", "scope"}),
            DELEGATE_SAFE_ACTIONS,
        )
        controller = self.controller("NSC-899")
        result = controller.run(max_actions=5, allowed_actions=DELEGATE_SAFE_ACTIONS)
        self.assertEqual("handoff_required", result["status"])
        self.assertEqual("reserve", result["handoff_action"]["kind"])
        self.assertEqual(
            ["prepare", "scope"],
            [item["action"]["kind"] for item in result["completed_actions"]],
        )
        self.assertEqual({}, controller._reservations())

    def test_run_priority_starts_single_agent_work_before_decompose_and_wait(self):
        controller = self.controller("NSC-898", "NSC-899")
        plan = {"next_actions": [
            {"kind": "decompose", "task_id": "NSC-898"},
            {"kind": "wait_worker", "task_id": "NSC-1010", "run_id": "running"},
            {"kind": "prepare", "task_id": "NSC-899", "source_commit": self.head},
        ]}
        with patch.object(controller, "_reservations", return_value={}):
            self.assertEqual("prepare", controller._next_run_action(plan)["kind"])
        plan["next_actions"] = [plan["next_actions"][0], plan["next_actions"][1]]
        with patch.object(controller, "_reservations", return_value={}):
            self.assertEqual("decompose", controller._next_run_action(plan)["kind"])
        plan["next_actions"] = [plan["next_actions"][1]]
        with patch.object(controller, "_reservations", return_value={}):
            self.assertEqual("wait_worker", controller._next_run_action(plan)["kind"])

    def test_available_slot_admits_later_task_before_processing_fast_result(self):
        controller = self.controller("NSC-899")
        controller.policy = replace(controller.policy, capacity=4)
        plan = {"next_actions": [
            {"kind": "post_crew", "task_id": "NSC-1101", "crew_run_id": "done"},
            {"kind": "reserve", "task_id": "NSC-1105", "run_id": "new-run"},
        ]}
        reservations = {
            "NSC-1101": {"task_id": "NSC-1101"},
            "NSC-1103": {"task_id": "NSC-1103"},
            "NSC-1104": {"task_id": "NSC-1104"},
        }
        with patch.object(controller, "_reservations", return_value=reservations), \
             patch.object(controller, "_resource_overlap_action", return_value=None):
            self.assertEqual(
                {"kind": "reserve", "task_id": "NSC-1105", "run_id": "new-run"},
                controller._next_run_action(plan),
            )

    def test_portable_setup_drains_before_first_reservation(self):
        controller = self.controller("NSC-899")
        plan = {"next_actions": [
            {"kind": "reserve", "task_id": "NSC-1120", "run_id": "first"},
            {"kind": "prepare", "task_id": "NSC-1125", "source_commit": self.head},
        ]}
        with patch.object(controller, "_reservations", return_value={}):
            self.assertEqual(
                {"kind": "prepare", "task_id": "NSC-1125", "source_commit": self.head},
                controller._next_run_action(plan),
            )

    def test_setup_of_later_task_precedes_earlier_candidate_integration(self):
        controller = self.controller("NSC-899")
        plan = {"next_actions": [
            {"kind": "integrate", "task_id": "NSC-1101", "source_commit": self.head},
            {"kind": "prepare", "task_id": "NSC-1105", "source_commit": self.head},
        ]}
        with patch.object(controller, "_reservations", return_value={}):
            self.assertEqual(
                {"kind": "prepare", "task_id": "NSC-1105", "source_commit": self.head},
                controller._next_run_action(plan),
            )

    def test_full_capacity_waits_instead_of_attempting_another_reserve(self):
        controller = self.controller("NSC-899")
        reservation = {
            "task_id": "NSC-1010", "run_id": "active-run", "lease_id": "active-lease",
            "plan_id": "active-plan", "source": str(self.manager.source),
            "source_head": self.head, "task_contract_sha256": "active-contract",
            "checkout_root": str(self.manager.root),
            "checkout": str(self.manager.root / "NSC-1010"),
        }
        active = {
            "task_id": "NSC-1010", "source": str(self.manager.source),
            "source_commit": self.head, "task_contract_sha256": "active-contract",
            "checkout": str(self.manager.root / "NSC-1010"),
            "scope": {"lease_id": "active-lease", "plan_id": "active-plan"},
            "worker": {"task_id": "NSC-1010", "run_id": "active-run",
                       "lease_id": "active-lease", "status": "running",
                       "capacity_released": False},
        }
        plan = {"next_actions": [
            {"kind": "reserve", "task_id": "NSC-899", "run_id": "new-run"},
        ]}
        with patch.object(controller, "_reservations", return_value={"NSC-1010": reservation}), \
             patch.object(controller, "_record",
                          side_effect=lambda task: active if task == "NSC-1010" else None):
            self.assertEqual(
                {"kind": "wait_worker", "task_id": "NSC-1010", "run_id": "active-run"},
                controller._next_run_action(plan),
            )

    def test_reserved_start_remains_runnable_when_capacity_is_full(self):
        controller = self.controller("NSC-899")
        actions = {"next_actions": [
            {"kind": "reserve", "task_id": "NSC-898", "run_id": "other"},
            {"kind": "start_worker", "task_id": "NSC-899", "run_id": "owned", "lease_id": "lease"},
            {"kind": "wait_worker", "task_id": "NSC-1010", "run_id": "running"},
        ]}
        with patch.object(controller, "_reservations", return_value={"NSC-899": {"run_id": "owned"}}):
            self.assertEqual("start_worker", controller._next_run_action(actions)["kind"])

    def test_resource_overlap_defers_exactly_to_active_owner(self):
        controller = self.controller("NSC-899")
        prepared = self.manager.prepare("NSC-899", expected_commit=self.head)
        path = self.manager.records / "NSC-899.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["scope"] = {"lease_id": "new-lease", "plan_id": "new-plan",
                           "source_head": self.head, "task_contract_sha256": record["task_contract_sha256"],
                           "plan": {"existing_implementation_paths": [],
                                    "new_implementation_paths": ["Assets/Feature/Scripts/Gauntlet899.cs"],
                                    "existing_test_paths": ["Assets/Feature/Tests/Editor/GauntletTests.cs"],
                                    "new_test_paths": []}}
        write_record(path, record)
        owner = {
            "task_id": "NSC-042", "run_id": "owner-run", "lease_id": "owner-lease",
            "plan_id": "owner-plan", "source": str(self.manager.source),
            "source_head": self.head, "task_contract_sha256": "owner-contract",
            "checkout_root": str(self.manager.root),
            "checkout": str(self.manager.root / "NSC-042"),
            "resources": ["assets/feature/scripts"],
        }
        owner_record = {
            "task_id": "NSC-042", "source": str(self.manager.source),
            "source_commit": self.head, "task_contract_sha256": "owner-contract",
            "checkout": str(self.manager.root / "NSC-042"),
            "scope": {"lease_id": "owner-lease", "plan_id": "owner-plan"},
            "worker": {"task_id": "NSC-042", "run_id": "owner-run",
                       "lease_id": "owner-lease", "status": "running",
                       "capacity_released": False},
        }
        with patch.object(controller, "_record", side_effect=lambda task: record if task == "NSC-899" else owner_record):
            self.assertEqual(
                {"kind": "wait_worker", "task_id": "NSC-042", "run_id": "owner-run"},
                controller._resource_overlap_action(
                    {"kind": "reserve", "task_id": "NSC-899", "run_id": "new-run"},
                    reservations={"NSC-042": owner},
                ),
            )

    def test_resource_overlap_settles_exact_terminal_owner_outside_targets(self):
        controller = self.controller("NSC-899")
        self.manager.prepare("NSC-899", expected_commit=self.head)
        path = self.manager.records / "NSC-899.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["scope"] = {
            "lease_id": "new-lease", "plan_id": "new-plan",
            "source_head": self.head,
            "task_contract_sha256": record["task_contract_sha256"],
            "plan": {"existing_implementation_paths": [],
                     "new_implementation_paths": ["Assets/Feature/Scripts/Gauntlet899.cs"],
                     "existing_test_paths": ["Assets/Feature/Tests/Editor/GauntletTests.cs"],
                     "new_test_paths": []},
        }
        owner = {
            "task_id": "NSC-042", "run_id": "owner-run", "lease_id": "owner-lease",
            "plan_id": "owner-plan", "source": str(self.manager.source),
            "source_head": self.head, "task_contract_sha256": "owner-contract",
            "checkout_root": str(self.manager.root),
            "checkout": str(self.manager.root / "NSC-042"),
            "resources": ["assets/feature/scripts"],
        }
        owner_record = {
            "task_id": "NSC-042", "source": str(self.manager.source),
            "source_commit": self.head, "task_contract_sha256": "owner-contract",
            "checkout": str(self.manager.root / "NSC-042"),
            "scope": {"lease_id": "owner-lease", "plan_id": "owner-plan"},
            "worker": {"task_id": "NSC-042", "run_id": "owner-run",
                       "lease_id": "owner-lease", "status": "succeeded",
                       "capacity_released": False},
        }
        plan = {"next_actions": [
            {"kind": "reserve", "task_id": "NSC-899", "run_id": "new-run"},
        ]}
        plans = [plan, {"next_actions": [], "status": "complete"}]
        executed = []
        with patch.object(controller, "_reservations", return_value={"NSC-042": owner}), \
             patch.object(controller, "_record",
                          side_effect=lambda task: record if task == "NSC-899" else owner_record), \
             patch.object(controller, "plan", side_effect=plans), \
             patch.object(controller, "execute",
                          side_effect=lambda action: executed.append(dict(action)) or {"capacity_released": True}), \
             patch.object(controller, "_save_state"):
            result = controller.run(max_actions=2)
        expected = {"kind": "settle_worker", "task_id": "NSC-042", "run_id": "owner-run"}
        self.assertEqual([expected], executed)
        self.assertEqual("complete", result["status"])
        self.assertEqual(expected, result["completed_actions"][0]["action"])

    def test_overlap_race_waits_and_replans_without_weakening_reserve(self):
        controller = self.controller("NSC-899")
        reserve_action = {"kind": "reserve", "task_id": "NSC-899", "run_id": "new-run"}
        plans = [{"next_actions": [reserve_action], "status": "actionable"},
                 {"next_actions": [], "status": "complete"}]
        wait = {"kind": "wait_worker", "task_id": "NSC-042", "run_id": "owner-run"}
        executed = []
        def execute(action):
            executed.append(dict(action))
            if action["kind"] == "reserve":
                raise ValueError("requested execution resources overlap an active admission")
            return {"status": "succeeded"}
        with patch.object(controller, "plan", side_effect=plans), \
             patch.object(controller, "_next_run_action", return_value=reserve_action), \
             patch.object(controller, "_resource_overlap_action", return_value=wait), \
             patch.object(controller, "execute", side_effect=execute), \
             patch.object(controller, "_save_state"):
            result = controller.run(max_actions=2)
        self.assertEqual([reserve_action, wait], executed)
        self.assertEqual("complete", result["status"])
        self.assertEqual("wait_worker", result["completed_actions"][0]["action"]["kind"])

    def test_non_overlap_reserve_error_still_blocks(self):
        controller = self.controller("NSC-899")
        action = {"kind": "reserve", "task_id": "NSC-899", "run_id": "new-run"}
        with patch.object(controller, "plan", return_value={"next_actions": [action]}), \
             patch.object(controller, "_next_run_action", return_value=action), \
             patch.object(controller, "execute", side_effect=ValueError("source changed")), \
             patch.object(controller, "_save_state"):
            with self.assertRaisesRegex(ValueError, "source changed"):
                controller.run(max_actions=1)

    def test_delegate_cli_needs_no_config_and_rejects_spend_authority(self):
        fake = unittest.mock.Mock()
        fake.run.return_value = {"status": "handoff_required"}
        base = [
            "--source", str(self.source),
            "--checkout-root", str(Path(self.temp.name) / "delegated"),
            "run-graph", "--task", "NSC-899", "--delegate-safe",
        ]
        output = io.StringIO()
        with patch.object(assistant_cli, "Checkouts", return_value=self.manager), patch(
            "Pipeline.AssistantControl.graph_controller.GraphController", return_value=fake,
        ) as graph, contextlib.redirect_stdout(output):
            code = assistant_cli.main(base)
        self.assertEqual(0, code)
        self.assertFalse(graph.call_args.kwargs["execution_authorized"])
        self.assertEqual(DELEGATE_SAFE_ACTIONS, fake.run.call_args.kwargs["allowed_actions"])

        output = io.StringIO()
        with patch.object(assistant_cli, "Checkouts", return_value=self.manager), patch(
            "Pipeline.AssistantControl.graph_controller.GraphController",
        ) as graph, contextlib.redirect_stdout(output):
            code = assistant_cli.main([*base, "--authorize-provider-spend"])
        self.assertEqual(1, code)
        self.assertIn("cannot be combined", json.loads(output.getvalue())["error"])
        graph.assert_not_called()

    def test_automated_gate_records_machine_authority_without_human_review(self):
        observed = self.manager.prepare("NSC-899", expected_commit=self.head)
        checkout = Path(observed["checkout"])
        created = checkout / "Assets/Feature/Scripts/Gauntlet899.cs"
        created.write_text("class Gauntlet899 {}\n", encoding="utf-8")
        name, email = validated_agent_git_identity()
        subprocess.run(["git", "-C", str(checkout), "add", "--", created.relative_to(checkout)], check=True)
        subprocess.run([
            "git", "-C", str(checkout), "-c", f"user.name={name}",
            "-c", f"user.email={email}", "commit", "-m", "fixture candidate",
        ], capture_output=True, check=True)
        commit = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            capture_output=True, check=True,
        ).stdout.decode().strip()
        tree = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD^{tree}"],
            capture_output=True, check=True,
        ).stdout.decode().strip()
        path = self.manager.records / "NSC-899.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record.update(status="awaiting_human", candidate={
            "commit": commit, "tree": tree,
            "authoritative_validations": [{"fixture": True}],
        })
        write_record(path, record)
        with patch(
            "Pipeline.AssistantControl.automation_policy.authenticate_passing_validations",
            return_value=({"fixture": True},),
        ):
            approved = ReviewGate(self.manager).approve_validated_gauntlet(
                "NSC-899", tested_commit=commit,
            )
        self.assertIsNone(approved["human_review"])
        self.assertEqual("assistant_gauntlet_automation", approved["approval"]["authority"])
        self.assertEqual("approved", approved["status"])


if __name__ == "__main__":
    unittest.main()
