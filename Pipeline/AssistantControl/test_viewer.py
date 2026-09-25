"""Component/HTTP regressions: reuse graph, reject mutations, retain children."""
import ast
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from Pipeline.AssistantControl import test_inspect_project as fixture
from Pipeline.AssistantControl import test_review as review_fixture
from Pipeline.AssistantControl import test_worker_control as worker_fixture
from Pipeline.AssistantControl import viewer as viewer_module
from Pipeline.AssistantControl.process_identity import identify
from Pipeline.AssistantControl.checkouts import write_record
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.AssistantControl.viewer import (
    AssistantSnapshot,
    ExclusiveListenerError,
    make_server,
)
from Pipeline.TaskDesignGER.ger_viewer_marker import change_marker


class ViewerTests(unittest.TestCase):
    setUp = fixture.InventoryTests.setUp
    run_git = fixture.InventoryTests.run_git

    def viewer_root(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Path(temp.name) / "Checkouts"

    def test_read_only_http_serves_existing_graph_and_refuses_every_mutation(self):
        root = self.viewer_root()
        server = make_server(self.root, root, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/") as response:
                document = response.read()
                self.assertEqual("no-store", response.headers["Cache-Control"])
                self.assertIn(b"cytoscape", document)
                self.assertIn(b'id="run-details-resize"', document)
                self.assertIn(b"Resize Project checkout height", document)
                self.assertIn(b"assistant_idle: { color: '#0b7348'", document)
                self.assertIn(b"borderWidth: 4, borderStyle: 'dashed'", document)
                self.assertIn(
                    b"const scopeOnly = document.getElementById('f-scope').checked", document,
                )
                self.assertIn(b'id="f-scope"> run scope only', document)
                self.assertIn(b"const saved = assistantFullGraph ? null", document)
                self.assertIn(b"controller.abort(), 120000", document)
                self.assertIn(b"label: 'Outside Current Run'", document)
                self.assertIn(b"task.held_overlay", document)
                self.assertIn(b"still part of the project graph", document)
                self.assertIn(b"if (scopeOnly && !t.in_scope) continue", document)
                self.assertIn(b"selectable: false", document)
            with urlopen(base + "/api/state") as response:
                self.assertEqual("no-store", response.headers["Cache-Control"])
                state = json.load(response)
            self.assertEqual("assistant", state["run"]["mode"])
            self.assertTrue(state["run"]["operator"]["read_only"])
            self.assertFalse(state["run"]["operator"]["viewer_persistent"])
            self.assertEqual([], state["human_actions"])
            for route in ("start", "stop", "reset", "force-stop", "scope", "issue"):
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base + "/api/local/" + route, b"{}", method="POST"))
                self.assertEqual(405, error.exception.code)
            self.assertFalse(root.exists())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_children_stay_visible_and_bad_record_is_not_accepted(self):
        root = self.viewer_root()
        child = self.root / "Tasks/NSC-043.yaml"
        child.write_text(json.dumps({"schema_version": "2.0", "id": "NSC-043", "title": "Child", "parent": "NSC-042",
                                     "contract_disposition": "active", "exclusive_resources": []}))
        self.run_git("add", "Tasks/NSC-043.yaml")
        self.run_git("commit", "-m", "Child fixture")
        records = root / ".assistant-control"
        records.mkdir(parents=True)
        (records / "NSC-043.json").write_text("{bad json")
        state = AssistantSnapshot(self.root, root).build()
        rows = {row["id"]: row for row in state["tasks"]}
        self.assertEqual("NSC-042", rows["NSC-043"]["parent"])
        self.assertEqual("blocked", rows["NSC-043"]["state"])
        self.assertIsNone(rows["NSC-043"]["checkout_commit"])

    def test_contract_loader_reads_each_pinned_contract_once_and_reuses_cache(self):
        reader = AssistantSnapshot(self.root, self.viewer_root())
        with unittest.mock.patch(
                "Pipeline.AssistantControl.viewer.load_committed_task",
                wraps=load_committed_task) as load:
            first = reader.build()
            second = reader.build()
        self.assertEqual(len(first["tasks"]), load.call_count)
        self.assertEqual(first["run"]["source_commit"], second["run"]["source_commit"])

    def test_untouched_executable_task_is_unstarted_not_awaiting_instruction(self):
        reader = AssistantSnapshot(self.root, self.viewer_root())
        row = reader.task_row({
            "schema_version": "2.0", "id": "NSC-777", "title": "Runnable fixture", "parent": None,
            "depends_on": [], "contract_disposition": "active",
            "execution_scope": "single_agent", "decomposition_state": "concrete",
            "decomposition_children": [], "exclusive_resources": [],
            "acceptance_criteria": [],
        }, read_durable_state=False)
        self.assertEqual("ready", row["state"])
        self.assertEqual("not_started", row["progress"]["phase"])

    def test_multiple_stream_clients_share_one_bounded_state_read(self):
        reader = AssistantSnapshot(self.root, self.viewer_root())
        with unittest.mock.patch.object(viewer_module, "git", wraps=viewer_module.git) as calls:
            first = reader.build(max_age_seconds=10)
            first_call_count = calls.call_count
            second = reader.build(max_age_seconds=10)
        self.assertIs(first, second)
        self.assertEqual(first_call_count, calls.call_count)

    def test_rebuild_reuses_committed_taskgraph_states_until_source_head_changes(self):
        reader = AssistantSnapshot(self.root, self.viewer_root())
        with unittest.mock.patch.object(
                reader, "_taskgraph_states", return_value={}) as calls:
            first = reader.build()
            second = reader.build()
        self.assertNotIn("inspection_error", first)
        self.assertNotIn("inspection_error", second)
        self.assertEqual(1, calls.call_count)

    def test_http_state_clients_share_the_bounded_snapshot_cache(self):
        root = self.viewer_root()
        server = make_server(self.root, root, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with unittest.mock.patch.object(
                    viewer_module, "git", wraps=viewer_module.git) as calls:
                with urlopen(base + "/api/state") as response:
                    first = json.load(response)
                first_call_count = calls.call_count
                with urlopen(base + "/api/state") as response:
                    second = json.load(response)
            self.assertEqual(first["run"]["source_commit"], second["run"]["source_commit"])
            self.assertEqual(first_call_count, calls.call_count)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_valid_simulation_bypasses_checkout_auth_and_scopes_only_visible_tasks(self):
        root = self.viewer_root()
        records = root / ".assistant-control"
        records.mkdir(parents=True)
        (records / "NSC-042.json").write_text("{bad real checkout", encoding="utf-8")
        (records / "viewer-simulation.json").write_text(json.dumps({
            "schema_version": "assistant-viewer-simulation/v1",
            "tasks": {
                "NSC-042": {
                    "state": "cancelled",
                    "phase": "simulation_out_of_scope",
                },
                "NSC-1101": {"state": "active", "phase": "execution_crew"},
                "NSC-1103": {
                    "state": "cancelled",
                    "phase": "simulation_out_of_scope",
                },
            },
            "virtual_tasks": [
                {"id": "NSC-1101", "title": "Visible simulation task"},
                {"id": "NSC-1103", "title": "Hidden simulation task"},
            ],
        }), encoding="utf-8")
        reader = AssistantSnapshot(self.root, root)

        with unittest.mock.patch.object(
                reader.manager, "observe", side_effect=AssertionError("must not authenticate")) as observe:
            state = reader.build()

        observe.assert_not_called()
        rows = {row["id"]: row for row in state["tasks"]}
        self.assertTrue(state["run"]["simulation"])
        self.assertFalse(rows["NSC-042"]["in_scope"])
        self.assertTrue(rows["NSC-1101"]["in_scope"])
        self.assertFalse(rows["NSC-1103"]["in_scope"])
        self.assertEqual(["NSC-1101"], state["run"]["targets"])

    def test_without_simulation_existing_checkout_is_still_authenticated(self):
        root = self.viewer_root()
        records = root / ".assistant-control"
        records.mkdir(parents=True)
        (records / "NSC-042.json").write_text("{}", encoding="utf-8")
        reader = AssistantSnapshot(self.root, root)

        with unittest.mock.patch.object(
                reader.manager, "observe", side_effect=ValueError("authenticated fixture")) as observe:
            state = reader.build()

        observe.assert_called_once_with("NSC-042")
        row = next(item for item in state["tasks"] if item["id"] == "NSC-042")
        self.assertEqual("blocked", row["state"])
        self.assertEqual("authenticated fixture", row["progress"]["blocked_reason"])

    def test_graph_controller_scope_includes_descendants_and_transitive_dependencies(self):
        reader = AssistantSnapshot(self.root, self.viewer_root())
        state = {"tasks": [
            {"id": "NSC-898", "parent": None, "depends_on": [], "in_scope": True},
            {"id": "NSC-1011", "parent": "NSC-898", "depends_on": ["NSC-1001"], "in_scope": True},
            {"id": "NSC-1012", "parent": "NSC-898", "depends_on": [], "in_scope": True},
            {"id": "NSC-1001", "parent": None, "depends_on": ["NSC-1002"], "in_scope": True},
            {"id": "NSC-1002", "parent": None, "depends_on": [], "in_scope": True},
            {"id": "NSC-9999", "parent": None, "depends_on": [], "in_scope": True},
        ], "run": {"targets": []}}

        reader._apply_controller_scope(state, ["NSC-898"])

        self.assertEqual(
            ["NSC-898", "NSC-1011", "NSC-1012", "NSC-1001", "NSC-1002"],
            state["run"]["targets"],
        )
        self.assertEqual(
            {"NSC-898", "NSC-1011", "NSC-1012", "NSC-1001", "NSC-1002"},
            {row["id"] for row in state["tasks"] if row["in_scope"]},
        )
        self.assertFalse(next(row for row in state["tasks"] if row["id"] == "NSC-9999")["in_scope"])
        excluded = next(row for row in state["tasks"] if row["id"] == "NSC-9999")
        self.assertEqual("excluded", excluded["state"])
        self.assertEqual("excluded_from_current_run", excluded["progress"]["phase"])

    def test_graph_controller_scope_does_not_include_missing_targets_or_children(self):
        reader = AssistantSnapshot(self.root, self.viewer_root())
        state = {"tasks": [
            {"id": "NSC-898", "parent": None, "depends_on": [], "in_scope": True},
            {"id": "NSC-1011", "parent": "NSC-898", "depends_on": [], "in_scope": True},
            {"id": "NSC-9999", "parent": "NSC-7777", "depends_on": [], "in_scope": True},
        ], "run": {"targets": ["NSC-898"]}}

        reader._apply_controller_scope(state, ["NSC-898", "NSC-missing"])

        self.assertEqual(["NSC-898", "NSC-1011"], state["run"]["targets"])
        excluded = next(row for row in state["tasks"] if row["id"] == "NSC-9999")
        self.assertFalse(excluded["in_scope"])
        self.assertEqual("excluded", excluded["state"])

    def test_stale_running_graph_projects_unknown_without_rewriting_evidence(self):
        root = self.viewer_root()
        reader = AssistantSnapshot(self.root, root)
        records = reader.manager.records
        records.mkdir(parents=True)
        path = records / "graph-controller.json"
        path.write_text(json.dumps({
            "schema_version": "assistant-graph-controller/v1",
            "status": "running", "invocation_id": "stale-invocation",
            "targets": ["NSC-1104"],
            "current_action": {"kind": "prepare", "task_id": "NSC-1104"},
        }), encoding="utf-8")
        lock_path = records / "graph-controller.lock"
        lock_path.write_bytes(b"\0")
        (records / "graph-controller-owner.json").write_text(json.dumps({
            "schema_version": "assistant-graph-controller-owner/v1",
            "status": "controller_started", "invocation_id": "stale-invocation",
            "pid": 7, "process_identity": {"pid": 7, "created_ticks": 1, "image": "x"},
            "source": str(reader.source), "checkout_root": str(reader.manager.root),
            "targets": ["NSC-1104"], "lock_path": str(lock_path),
        }), encoding="utf-8")
        before = {item.name: item.read_bytes() for item in records.iterdir()}
        state = {"run": {"targets": []}, "tasks": []}
        activity = {}

        with unittest.mock.patch.object(viewer_module, "matches", return_value=False) as probe:
            reader._apply_graph_controller(state, activity)

        probe.assert_called_once()
        self.assertEqual("unknown", state["run"]["status"])
        self.assertEqual("unknown", state["graph_controller"]["status"])
        self.assertEqual("running", state["graph_controller"]["recorded_status"])
        self.assertEqual("Graph controller ownership is unknown", activity["headline"])
        self.assertEqual("not running", activity["provider_profile"])
        self.assertEqual(before, {item.name: item.read_bytes() for item in records.iterdir()})

    def test_running_graph_projects_only_scoped_idle_tasks_as_unstarted(self):
        root = self.viewer_root()
        records = root / ".assistant-control"
        records.mkdir(parents=True)
        (records / "graph-controller.json").write_text(json.dumps({
            "schema_version": "assistant-graph-controller/v1",
            "status": "running",
            "targets": ["NSC-1104", "NSC-1105"],
            "current_action": {"kind": "prepare", "task_id": "NSC-1104"},
            "auto_approve_gauntlet": True,
        }), encoding="utf-8")
        reader = AssistantSnapshot(self.root, root)
        state = {
            "run": {"targets": [], "source_commit": "fixture"},
            "tasks": [
                {"id": "NSC-1104", "parent": None, "depends_on": [], "in_scope": True,
                 "state": "assistant_idle", "progress": {"phase": "awaiting_instruction"}},
                {"id": "NSC-1105", "parent": None, "depends_on": [], "in_scope": True,
                 "state": "assistant_idle", "progress": {"phase": "awaiting_instruction"}},
                {"id": "NSC-9999", "parent": None, "depends_on": [], "in_scope": True,
                 "state": "assistant_idle", "progress": {"phase": "awaiting_instruction"}},
            ],
        }
        activity = {}

        with unittest.mock.patch.object(reader, "_controller_owner_active", return_value=True):
            reader._apply_graph_controller(state, activity)

        rows = {row["id"]: row for row in state["tasks"]}
        self.assertEqual("ready", rows["NSC-1104"]["state"])
        self.assertEqual("ready", rows["NSC-1105"]["state"])
        self.assertEqual("assistant_idle", rows["NSC-9999"]["state"])
        self.assertFalse(rows["NSC-9999"]["in_scope"])

    def test_preflight_projects_ready_decomposition_and_dependency_states(self):
        root = self.viewer_root()
        records = root / ".assistant-control"
        records.mkdir(parents=True)
        targets = [f"NSC-{number}" for number in range(1120, 1128)]
        actions = [
            {"kind": "prepare", "task_id": task_id, "source_commit": "fixture"}
            for task_id in ("NSC-1120", "NSC-1125", "NSC-1126", "NSC-1127")
        ] + [{"kind": "decompose", "task_id": "NSC-1124"}]
        blocked = [
            {"task_id": "NSC-1121", "reason": "dependencies", "dependencies": ["NSC-1120"]},
            {"task_id": "NSC-1122", "reason": "dependencies", "dependencies": ["NSC-1121"]},
            {"task_id": "NSC-1123", "reason": "dependencies", "dependencies": ["NSC-1122"]},
        ]
        plan = {
            "schema_version": "assistant-graph-controller/v1",
            "source": str(self.root.resolve()),
            "source_commit": "fixture",
            "targets": targets,
            "in_scope": targets,
            "next_actions": actions,
            "blocked": blocked,
            "mutations_performed": False,
        }
        (records / "graph-controller.json").write_text(json.dumps({
            "schema_version": "assistant-graph-controller/v1",
            "status": "preflight",
            "targets": targets,
            "current_action": None,
            "preflight_plan": plan,
        }), encoding="utf-8")
        reader = AssistantSnapshot(self.root, root)
        state = {
            "run": {"targets": [], "source_commit": "fixture"},
            "tasks": [
                {
                    "id": task_id,
                    "parent": None,
                    "depends_on": [],
                    "in_scope": True,
                    "state": "ready",
                    "progress": {"phase": "not_started"},
                }
                for task_id in targets
            ],
        }

        reader._apply_graph_controller(state, {})

        rows = {row["id"]: row for row in state["tasks"]}
        self.assertEqual(
            {"NSC-1120", "NSC-1125", "NSC-1126", "NSC-1127"},
            {task_id for task_id, row in rows.items() if row["state"] == "ready"},
        )
        self.assertEqual("decomposition_ready", rows["NSC-1124"]["state"])
        self.assertEqual(
            {"NSC-1121", "NSC-1122", "NSC-1123"},
            {task_id for task_id, row in rows.items() if row["state"] == "pending"},
        )

    def test_running_graph_keeps_automatic_gauntlet_review_blue_but_not_042(self):
        root = self.viewer_root()
        records = root / ".assistant-control"
        records.mkdir(parents=True)
        (records / "graph-controller.json").write_text(json.dumps({
            "schema_version": "assistant-graph-controller/v1",
            "status": "running",
            "targets": ["NSC-1104", "NSC-042"],
            "current_action": {"kind": "auto_approve", "task_id": "NSC-1104"},
            "auto_approve_gauntlet": True,
        }), encoding="utf-8")
        reader = AssistantSnapshot(self.root, root)
        state = {
            "run": {"targets": [], "source_commit": "fixture"},
            "tasks": [
                {"id": "NSC-1104", "parent": None, "depends_on": [], "in_scope": True,
                 "state": "human_action", "candidate_commit": "a" * 40,
                 "progress": {"phase": "awaiting_human"}},
                {"id": "NSC-042", "parent": None, "depends_on": [], "in_scope": True,
                 "state": "human_action", "candidate_commit": "b" * 40,
                 "progress": {"phase": "awaiting_human"}},
            ],
        }
        activity = {}

        with unittest.mock.patch(
                "Pipeline.AssistantControl.viewer.is_synthetic_gauntlet", return_value=True), \
             unittest.mock.patch.object(reader, "_controller_owner_active", return_value=True):
            reader._apply_graph_controller(state, activity)

        rows = {row["id"]: row for row in state["tasks"]}
        self.assertEqual("active", rows["NSC-1104"]["state"])
        self.assertEqual("automatic_validation", rows["NSC-1104"]["progress"]["phase"])
        self.assertEqual("human_action", rows["NSC-042"]["state"])

    def test_review_queue_preserves_exact_candidate_without_alarm(self):
        root = self.viewer_root()
        records = root / ".assistant-control"
        records.mkdir(parents=True)
        record = records / "NSC-042.json"
        record.write_text("{}", encoding="utf-8")
        now_epoch = time.time()
        os.utime(record, (now_epoch - 1801, now_epoch - 1801))
        rows = [{
            "id": "NSC-042", "state": "human_action",
            "candidate_commit": "a" * 40,
        }]

        attention = AssistantSnapshot(self.root, root)._human_review_attention(
            rows, now_epoch=now_epoch,
        )

        self.assertNotIn("review_alarm", attention)
        self.assertEqual("a" * 40, attention["candidates"][0]["candidate_commit"])

    def test_review_queue_clears_after_approve_or_deny_state(self):
        root = self.viewer_root()
        records = root / ".assistant-control"
        records.mkdir(parents=True)
        record = records / "NSC-042.json"
        record.write_text("{}", encoding="utf-8")
        now_epoch = time.time()
        os.utime(record, (now_epoch - 3600, now_epoch - 3600))

        attention = AssistantSnapshot(self.root, root)._human_review_attention(
            [{"id": "NSC-042", "state": "assistant_idle",
              "candidate_commit": "a" * 40}],
            now_epoch=now_epoch,
        )

        self.assertNotIn("review_alarm", attention)
        self.assertEqual([], attention["task_ids"])

    def test_running_checkout_write_does_not_flash_blocked(self):
        root = self.viewer_root()
        records = root / ".assistant-control"
        records.mkdir(parents=True)
        (records / "graph-controller.json").write_text(json.dumps({
            "schema_version": "assistant-graph-controller/v1",
            "status": "running",
            "targets": ["NSC-1104"],
            "current_action": {"kind": "post_crew", "task_id": "NSC-1104"},
            "auto_approve_gauntlet": True,
        }), encoding="utf-8")
        reader = AssistantSnapshot(self.root, root)
        state = {
            "run": {"targets": [], "source_commit": "fixture"},
            "tasks": [{
                "id": "NSC-1104", "parent": None, "depends_on": [], "in_scope": True,
                "state": "blocked",
                "progress": {
                    "phase": "checkout_needs_attention",
                    "blocked_reason": "Task project has uncommitted changes",
                },
            }],
        }

        with unittest.mock.patch.object(reader, "_controller_owner_active", return_value=True):
            reader._apply_graph_controller(state, {})

        self.assertEqual("active", state["tasks"][0]["state"])
        self.assertEqual("automatic_validation", state["tasks"][0]["progress"]["phase"])

    def test_running_prepare_scope_and_reserve_do_not_flash_checkout_blocked(self):
        for action_kind in ("prepare", "scope", "reserve"):
            with self.subTest(action_kind=action_kind):
                root = self.viewer_root()
                records = root / ".assistant-control"
                records.mkdir(parents=True)
                (records / "graph-controller.json").write_text(json.dumps({
                    "schema_version": "assistant-graph-controller/v1",
                    "status": "running",
                    "targets": ["NSC-1104"],
                    "current_action": {"kind": action_kind, "task_id": "NSC-1104"},
                }), encoding="utf-8")
                reader = AssistantSnapshot(self.root, root)
                state = {
                    "run": {"targets": [], "source_commit": "fixture"},
                    "tasks": [{
                        "id": "NSC-1104", "parent": None, "depends_on": [], "in_scope": True,
                        "state": "blocked",
                        "progress": {
                            "phase": "checkout_needs_attention",
                            "blocked_reason": "Task project has uncommitted changes",
                        },
                    }],
                }

                with unittest.mock.patch.object(
                        reader, "_controller_owner_active", return_value=True):
                    reader._apply_graph_controller(state, {})

                self.assertEqual("active", state["tasks"][0]["state"])
                self.assertEqual("automatic_validation", state["tasks"][0]["progress"]["phase"])

    def test_checkout_blocked_state_returns_after_controller_action_ends(self):
        root = self.viewer_root()
        records = root / ".assistant-control"
        records.mkdir(parents=True)
        controller = {
            "schema_version": "assistant-graph-controller/v1",
            "status": "blocked",
            "targets": ["NSC-1104"],
            "current_action": {"kind": "prepare", "task_id": "NSC-1104"},
        }
        (records / "graph-controller.json").write_text(json.dumps(controller), encoding="utf-8")
        reader = AssistantSnapshot(self.root, root)
        state = {
            "run": {"targets": [], "source_commit": "fixture"},
            "tasks": [{
                "id": "NSC-1104", "parent": None, "depends_on": [], "in_scope": True,
                "state": "blocked",
                "progress": {
                    "phase": "checkout_needs_attention",
                    "blocked_reason": "Task project has uncommitted changes",
                },
            }],
        }

        reader._apply_graph_controller(state, {})

        self.assertEqual("blocked", state["tasks"][0]["state"])
        self.assertEqual("checkout_needs_attention", state["tasks"][0]["progress"]["phase"])

    def test_stopped_controller_scope_does_not_hide_direct_worker_or_delivery(self):
        root = self.viewer_root()
        records = root / ".assistant-control"
        records.mkdir(parents=True)
        (records / "graph-controller.json").write_text(json.dumps({
            "schema_version": "assistant-graph-controller/v1",
            "status": "blocked", "targets": ["NSC-1104"],
            "current_action": None,
        }), encoding="utf-8")
        reader = AssistantSnapshot(self.root, root)
        state = {
            "run": {"targets": []},
            "tasks": [
                {"id": "NSC-1104", "in_scope": False, "state": "ready"},
                {"id": "NSC-1105", "in_scope": True, "state": "active",
                 "worker": {"status": "running"}},
                {"id": "NSC-1106", "in_scope": False, "state": "complete"},
            ],
        }

        reader._apply_graph_controller(state, {})

        self.assertEqual(["ready", "active", "complete"],
                         [row["state"] for row in state["tasks"]])
        self.assertTrue(state["tasks"][1]["in_scope"])

    def test_decomposed_parent_is_accepted_only_when_every_exact_child_is_accepted(self):
        reader = AssistantSnapshot(self.root, self.viewer_root())
        rows = [
            {"id": "NSC-898", "decomposition_state": "decomposed",
             "decomposition_children": ["NSC-1011", "NSC-1012"],
             "state": "aggregate", "progress": {"phase": "decomposition_applied"}},
            {"id": "NSC-1011", "state": "local_accepted"},
            {"id": "NSC-1012", "state": "local_accepted"},
        ]
        reader._apply_decomposition_projection(rows)
        self.assertEqual("local_accepted", rows[0]["state"])
        self.assertEqual("children_integrated", rows[0]["progress"]["phase"])

    def test_decomposed_parent_stays_aggregate_for_pending_or_missing_child(self):
        reader = AssistantSnapshot(self.root, self.viewer_root())
        for child_rows in (
            [{"id": "NSC-1011", "state": "human_action"},
             {"id": "NSC-1012", "state": "local_accepted"}],
            [{"id": "NSC-1011", "state": "local_accepted"}],
        ):
            rows = [
                {"id": "NSC-898", "decomposition_state": "decomposed",
                 "decomposition_children": ["NSC-1011", "NSC-1012"],
                 "state": "aggregate", "progress": {"phase": "decomposition_applied"}},
                *child_rows,
            ]
            reader._apply_decomposition_projection(rows)
            self.assertEqual("aggregate", rows[0]["state"])


@unittest.skipUnless(os.name == "nt", "Windows host identity")
class WorkerViewTests(unittest.TestCase):
    setUp = worker_fixture.StopTests.setUp
    run_git = worker_fixture.StopTests.run_git
    manager = worker_fixture.StopTests.manager
    worker = worker_fixture.StopTests.worker

    def test_verified_host_runs_but_stale_identity_never_displays_running(self):
        manager, record, stop_path = self.worker()
        record["worker"].update({
            "process_identity": identify(os.getpid()),
            "plan_id": "fixture-plan",
            "source_head": record["source_commit"],
            "task_contract_sha256": record["task_contract_sha256"],
            "job_name": "assistant-job-" + hashlib.sha256(
                str(stop_path.parent).encode()
            ).hexdigest(),
        })
        write_record(manager.records / "NSC-042.json", record)
        reader = AssistantSnapshot(self.root, manager.root)
        def row():
            return next(item for item in reader.build()["tasks"] if item["id"] == "NSC-042")
        self.assertEqual("active", row()["state"])
        worker_fixture.request_stop(manager, "NSC-042", run_id="fixture-run")
        self.assertIn("Stop requested", row()["progress"]["transition_context"])
        record["worker"]["process_identity"]["created_ticks"] += 1
        write_record(manager.records / "NSC-042.json", record)
        self.assertEqual("blocked", row()["state"])
        self.assertFalse(row()["worker_observation"]["capacity_released"])

    def test_spawn_failed_is_blocked_with_exact_error_and_no_output_claim(self):
        manager, record, _ = self.worker()
        record["worker"].update(status="spawn_failed", error="CreateProcess denied")
        write_record(manager.records / "NSC-042.json", record)
        row = next(item for item in AssistantSnapshot(self.root, manager.root).build()["tasks"]
                   if item["id"] == "NSC-042")
        self.assertEqual("blocked", row["state"])
        self.assertEqual("worker_spawn_failed", row["progress"]["phase"])
        self.assertIn("CreateProcess denied", row["progress"]["transition_context"])
        self.assertNotIn("returned output", row["progress"]["transition_context"])

    def test_verified_running_rows_populate_scheduler_active(self):
        manager, record, _ = self.worker()
        record["worker"]["process_identity"] = identify(os.getpid())
        write_record(manager.records / "NSC-042.json", record)
        state = AssistantSnapshot(self.root, manager.root).build()
        self.assertEqual(["NSC-042"], state["scheduler"]["active"])

    def test_prepared_checkout_with_verified_running_worker_stays_active(self):
        manager, record, _ = self.worker()
        record["status"] = "prepared"
        write_record(manager.records / "NSC-042.json", record)
        observation = {"task_id": "NSC-042", "worker": record["worker"],
                       "host_identity_alive": True, "stop_requested": False,
                       "capacity_released": False}
        with unittest.mock.patch(
                "Pipeline.AssistantControl.worker_control.status", return_value=observation):
            row = next(item for item in AssistantSnapshot(self.root, manager.root).build()["tasks"]
                       if item["id"] == "NSC-042")
        self.assertEqual("active", row["state"])
        self.assertEqual("worker_running", row["progress"]["phase"])

    def test_prepared_launch_stays_active_during_identity_handoff(self):
        manager, record, _ = self.worker()
        record["status"] = "prepared"
        record["launch"] = {**record.pop("worker"), "status": "running"}
        write_record(manager.records / "NSC-042.json", record)
        observation = {"task_id": "NSC-042", "worker": record["launch"],
                       "host_identity_alive": None, "stop_requested": False,
                       "capacity_released": False}
        with unittest.mock.patch(
                "Pipeline.AssistantControl.worker_control.status", return_value=observation):
            state = AssistantSnapshot(self.root, manager.root).build()
        row = next(item for item in state["tasks"] if item["id"] == "NSC-042")
        self.assertEqual("active", row["state"])
        self.assertEqual(["NSC-042"], state["scheduler"]["active"])

    def test_prepared_checkout_with_settled_worker_is_no_longer_active(self):
        manager, record, _ = self.worker()
        record["status"] = "prepared"
        record["worker"]["status"] = "succeeded"
        write_record(manager.records / "NSC-042.json", record)
        observation = {"task_id": "NSC-042", "worker": record["worker"],
                       "host_identity_alive": False, "stop_requested": False,
                       "capacity_released": True}
        with unittest.mock.patch(
                "Pipeline.AssistantControl.worker_control.status", return_value=observation):
            row = next(item for item in AssistantSnapshot(self.root, manager.root).build()["tasks"]
                       if item["id"] == "NSC-042")
        self.assertEqual("assistant_idle", row["state"])
        self.assertEqual("worker_succeeded", row["progress"]["phase"])

    def test_committed_delivery_outweighs_stale_idle_checkout_but_not_live_work(self):
        manager, record, _ = self.worker()
        record["status"] = "prepared"
        record["worker"]["status"] = "succeeded"
        write_record(manager.records / "NSC-042.json", record)
        reader = AssistantSnapshot(self.root, manager.root)
        with unittest.mock.patch.object(
                reader, "_taskgraph_states", return_value={"NSC-042": {"state": "conformant"}}):
            row = next(item for item in reader.build()["tasks"] if item["id"] == "NSC-042")
        self.assertEqual("complete", row["state"])
        self.assertEqual("taskgraph_conformant", row["progress"]["phase"])

        record["worker"]["status"] = "running"
        write_record(manager.records / "NSC-042.json", record)
        observation = {"task_id": "NSC-042", "worker": record["worker"],
                       "host_identity_alive": True, "stop_requested": False,
                       "capacity_released": False}
        with unittest.mock.patch(
                "Pipeline.AssistantControl.worker_control.status", return_value=observation):
            row = next(item for item in reader.build()["tasks"] if item["id"] == "NSC-042")
        self.assertEqual("active", row["state"])

    @staticmethod
    def _write_crew_progress(checkout, *, rows, run_id="fixture-crew-run", task_id="NSC-042"):
        """Write a durable ExecutionCrew progress.jsonl exactly where compose.yaml
        binds ``/execution-output`` for the claude-exec/codex-exec services:
        directly inside this task's own checkout, at
        ``Pipeline/ExecutionCrew/outputs/<run_id>/progress.jsonl``.
        """
        run_dir = checkout / "Pipeline" / "ExecutionCrew" / "outputs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        with (run_dir / "progress.jsonl").open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps({"task_id": task_id, "run_id": run_id, **row}) + "\n")
        return run_dir

    def test_running_worker_reports_active_stage_and_current_agent(self):
        manager, record, _ = self.worker()
        record["worker"]["started_at"] = "2026-09-12T07:46:40Z"
        write_record(manager.records / "NSC-042.json", record)
        self._write_crew_progress(Path(record["checkout"]), rows=[
            {"event": "run_started", "timestamp_utc": "2026-09-12T07:46:47Z",
             "required_roles": ["implementer", "validator"]},
            {"event": "role_started", "role": "implementer", "attempt": 1,
             "timestamp_utc": "2026-09-12T07:46:50Z"},
            {"event": "role_completed", "role": "implementer", "attempt": 1,
             "status": "succeeded", "timestamp_utc": "2026-09-12T07:47:16Z"},
            {"event": "role_started", "role": "validator", "attempt": 1,
             "timestamp_utc": "2026-09-12T07:47:16Z"},
        ])
        observation = {"task_id": "NSC-042", "worker": record["worker"],
                       "host_identity_alive": True, "stop_requested": False,
                       "capacity_released": False}
        with unittest.mock.patch(
                "Pipeline.AssistantControl.worker_control.status", return_value=observation):
            row = next(item for item in AssistantSnapshot(self.root, manager.root).build()["tasks"]
                       if item["id"] == "NSC-042")
        self.assertEqual("active", row["state"])
        progress = row["progress"]
        agents = {agent["role"]: agent for agent in progress["agents"]}
        self.assertEqual("completed", agents["implementer"]["status"])
        self.assertEqual(26.0, agents["implementer"]["duration_seconds"])
        self.assertEqual("implementing the task", agents["implementer"]["action"])
        self.assertEqual("running", agents["validator"]["status"])
        self.assertGreaterEqual(agents["validator"]["duration_seconds"], 0)
        current = progress["current_agent"]
        self.assertEqual("validator", current["role"])
        self.assertEqual("validating the candidate", current["action"])
        self.assertEqual(
            [{"label": "Execution crew · Validator 2 of 2", "status": "active",
              "elapsed_seconds": current["duration_seconds"]}],
            progress["pipeline_stages"],
        )

    def test_completed_worker_retains_exact_recorded_stage_durations(self):
        manager, record, _ = self.worker()
        record["worker"]["started_at"] = "2026-09-12T07:46:40Z"
        record["worker"]["status"] = "succeeded"
        record["worker"]["finished_at"] = "2026-09-12T07:49:00Z"
        write_record(manager.records / "NSC-042.json", record)
        self._write_crew_progress(Path(record["checkout"]), rows=[
            {"event": "run_started", "timestamp_utc": "2026-09-12T07:46:47Z",
             "required_roles": ["implementer", "validator"]},
            {"event": "role_started", "role": "implementer", "attempt": 1,
             "timestamp_utc": "2026-09-12T07:46:50Z"},
            {"event": "role_completed", "role": "implementer", "attempt": 1,
             "status": "succeeded", "timestamp_utc": "2026-09-12T07:47:16Z"},
            {"event": "role_started", "role": "validator", "attempt": 1,
             "timestamp_utc": "2026-09-12T07:47:16Z"},
            {"event": "role_completed", "role": "validator", "attempt": 1,
             "status": "succeeded", "timestamp_utc": "2026-09-12T07:48:39Z"},
            {"event": "run_completed", "timestamp_utc": "2026-09-12T07:48:39Z",
             "status": "review_ready"},
        ])
        observation = {"task_id": "NSC-042", "worker": record["worker"],
                       "host_identity_alive": False, "stop_requested": False,
                       "capacity_released": True}
        with unittest.mock.patch(
                "Pipeline.AssistantControl.worker_control.status", return_value=observation):
            row = next(item for item in AssistantSnapshot(self.root, manager.root).build()["tasks"]
                       if item["id"] == "NSC-042")
        self.assertEqual("assistant_idle", row["state"])
        agents = {agent["role"]: agent for agent in row["progress"]["agents"]}
        # A role that already finished keeps its own exact recorded duration
        # even though the crew (and later roles) went on to finish afterward.
        self.assertEqual("completed", agents["implementer"]["status"])
        self.assertEqual(26.0, agents["implementer"]["duration_seconds"])
        self.assertEqual("completed", agents["validator"]["status"])
        self.assertEqual(83.0, agents["validator"]["duration_seconds"])
        self.assertIsNone(row["progress"]["current_agent"])
        self.assertNotIn("pipeline_stages", row["progress"])

    def test_missing_or_malformed_progress_evidence_fails_safely(self):
        manager, record, _ = self.worker()
        record["worker"]["started_at"] = "2026-09-12T07:46:40Z"
        write_record(manager.records / "NSC-042.json", record)
        checkout = Path(record["checkout"])
        observation = {"task_id": "NSC-042", "worker": record["worker"],
                       "host_identity_alive": True, "stop_requested": False,
                       "capacity_released": False}

        def active_row():
            with unittest.mock.patch(
                    "Pipeline.AssistantControl.worker_control.status", return_value=observation):
                return next(item for item in AssistantSnapshot(self.root, manager.root).build()["tasks"]
                           if item["id"] == "NSC-042")

        # No ExecutionCrew output has been written yet: /api/state still serves
        # the plain worker phase, with no fabricated stage/agent detail.
        row = active_row()
        self.assertEqual("active", row["state"])
        self.assertNotIn("agents", row["progress"])
        self.assertNotIn("current_agent", row["progress"])
        self.assertNotIn("pipeline_stages", row["progress"])

        # progress.jsonl exists but is entirely unusable (bad JSON, and one
        # line that parses but names no task): still no crash, no binding.
        run_dir = checkout / "Pipeline" / "ExecutionCrew" / "outputs" / "fixture-crew-run"
        run_dir.mkdir(parents=True)
        (run_dir / "progress.jsonl").write_text(
            "not json at all\n{\"event\": \"run_started\"}\n", encoding="utf-8")
        row = active_row()
        self.assertEqual("active", row["state"])
        self.assertNotIn("agents", row["progress"])
        self.assertNotIn("current_agent", row["progress"])
        self.assertNotIn("pipeline_stages", row["progress"])


class CandidateViewTests(unittest.TestCase):
    setUp = review_fixture.ReviewTests.setUp
    run_git = review_fixture.ReviewTests.run_git
    manager = review_fixture.ReviewTests.manager
    candidate = review_fixture.ReviewTests.candidate
    approve = review_fixture.ReviewTests.approve

    def test_exact_candidate_requests_human_review_and_approval_is_not_acceptance(self):
        gate, record, commit, branch = self.candidate()
        reader = AssistantSnapshot(self.root, gate.checkouts.root)
        def row():
            return next(item for item in reader.build()["tasks"] if item["id"] == "NSC-042")
        self.assertEqual("human_action", row()["state"])
        self.assertEqual(commit, row()["candidate_commit"])
        state = reader.build()
        self.assertEqual("🐴 Vincent needed", state["pipeline_activity"]["headline"])
        self.assertEqual({"kind": "human_review", "task_ids": ["NSC-042"]},
                         state["assistant_attention"])
        self.approve(gate, commit)
        self.assertEqual("approved", row()["progress"]["phase"])
        self.assertNotEqual("local_accepted", row()["state"])
        gate.decide("NSC-042", tested_commit=commit, decision="reject", message="Fix the seam")
        self.assertEqual("changes_requested", row()["progress"]["phase"])
        (Path(record["checkout"]) / "wall file.txt").write_text("changed after review")
        self.assertEqual("blocked", row()["state"])

    def test_integrated_candidate_displays_local_acceptance(self):
        gate, record, commit, branch = self.candidate()
        self.approve(gate, commit)
        gate.integrate(
            "NSC-042", expected_source_commit=record["source_commit"],
            target_branch=branch,
        )
        row = next(item for item in AssistantSnapshot(self.root, gate.checkouts.root).build()["tasks"]
                   if item["id"] == "NSC-042")
        self.assertEqual("local_accepted", row["state"])
        self.assertEqual("integrated", row["progress"]["phase"])

    def test_stale_integrated_record_is_blocked_when_source_lacks_candidate(self):
        gate, record, commit, branch = self.candidate()
        self.approve(gate, commit)
        record_path = gate.checkouts.records / "NSC-042.json"
        current = json.loads(record_path.read_text())
        current["status"] = "integrated"
        current["integration"] = {"candidate": commit, "branch": branch}
        write_record(record_path, current)
        row = next(item for item in AssistantSnapshot(self.root, gate.checkouts.root).build()["tasks"]
                   if item["id"] == "NSC-042")
        self.assertEqual("blocked", row["state"])
        self.assertEqual("checkout_needs_attention", row["progress"]["phase"])

    def test_restored_candidate_is_not_presented_as_crew_reviewed(self):
        gate, record, commit, branch = self.candidate()
        record_path = gate.checkouts.records / "NSC-042.json"
        current = json.loads(record_path.read_text())
        current["candidate"].update(kind="assistant_restored", crew_review=False)
        write_record(record_path, current)
        row = next(item for item in AssistantSnapshot(self.root, gate.checkouts.root).build()["tasks"]
                   if item["id"] == "NSC-042")
        self.assertEqual("assistant_restored", row["candidate_kind"])
        self.assertFalse(row["crew_review"])
        self.assertIn("crew review is false", row["progress"]["transition_context"])

    def test_materialized_candidate_names_builder_tests_and_visual_review(self):
        gate, record, commit, branch = self.candidate()
        record_path = gate.checkouts.records / "NSC-042.json"
        current = json.loads(record_path.read_text())
        current["candidate"].update(
            kind="unity_materialized", crew_review=False,
            source_candidate_crew_review=True,
        )
        write_record(record_path, current)
        row = next(item for item in AssistantSnapshot(self.root, gate.checkouts.root).build()["tasks"]
                   if item["id"] == "NSC-042")
        self.assertEqual("human_action", row["state"])
        self.assertFalse(row["crew_review"])
        self.assertIn("focused Unity tests passed", row["progress"]["transition_context"])
        self.assertIn("visually test", row["progress"]["transition_context"])


class DuplicateViewerPortTests(unittest.TestCase):
    """A second viewer must never share a port with an already-listening one."""

    setUp = fixture.InventoryTests.setUp
    run_git = fixture.InventoryTests.run_git

    REPO_ROOT = Path(__file__).resolve().parents[2]

    def checkout_root(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Path(temp.name) / "Checkouts"

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    def _launch(self, port: int) -> subprocess.Popen:
        proc = subprocess.Popen(
            [sys.executable, "-m", "Pipeline.AssistantControl",
             "--source", str(self.root), "--checkout-root", str(self.checkout_root()),
             "viewer", "--port", str(port)],
            cwd=str(self.REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
        )

        def _cleanup():
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            proc.stdout.close()
            proc.stderr.close()

        self.addCleanup(_cleanup)
        return proc

    @staticmethod
    def _readline(stream, timeout: float) -> str | None:
        box: dict = {}

        def _read():
            box["line"] = stream.readline()

        thread = threading.Thread(target=_read, daemon=True)
        thread.start()
        thread.join(timeout)
        return box.get("line") if not thread.is_alive() else None

    def test_second_process_on_same_port_fails_closed_first_stays_reachable(self):
        port = self._free_port()
        first = self._launch(port)
        line = self._readline(first.stdout, 10)
        self.assertIsNotNone(line, "first viewer never reported a ready viewer_url")
        first_payload = json.loads(line)
        self.assertEqual(f"http://127.0.0.1:{port}/", first_payload["viewer_url"])
        with urlopen(f"http://127.0.0.1:{port}/api/state", timeout=5) as response:
            first_identity = json.load(response)["viewer_identity"]
        self.assertEqual(port, first_identity["port"])
        self.assertEqual(str(Path(self.root).resolve()), first_identity["source"])

        second = self._launch(port)
        second_out, _second_err = second.communicate(timeout=15)
        self.assertNotEqual(0, second.returncode)
        self.assertNotIn("viewer_url", second_out)

        # The first viewer's own identity is unchanged: the second process
        # never displaced it or reset its state.
        with urlopen(f"http://127.0.0.1:{port}/api/state", timeout=5) as response:
            still_identity = json.load(response)["viewer_identity"]
        self.assertEqual(first_identity, still_identity)

        first.terminate()
        first.wait(timeout=10)

        third = self._launch(port)
        line = self._readline(third.stdout, 10)
        self.assertIsNotNone(line, "a later viewer could not reacquire the freed port")
        third_payload = json.loads(line)
        self.assertEqual(f"http://127.0.0.1:{port}/", third_payload["viewer_url"])
        with urlopen(f"http://127.0.0.1:{port}/api/state", timeout=5) as response:
            third_identity = json.load(response)["viewer_identity"]
        self.assertNotEqual(first_identity["instance_id"], third_identity["instance_id"])
        third.terminate()
        third.wait(timeout=10)

    def test_make_server_raises_before_returning_when_port_is_held(self):
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(holder.close)
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        port = holder.getsockname()[1]
        with self.assertRaises(ExclusiveListenerError):
            make_server(self.root, self.checkout_root(), port)

    def test_explicit_held_overlay_is_additive_and_default_is_unchanged(self):
        root = self.checkout_root()
        reader = AssistantSnapshot(self.root, root)
        rows = [
            {"id": "NSC-003", "state": "ready", "taskgraph": {"state": "needs_replan"}},
            {"id": "NSC-012", "state": "complete", "taskgraph": {"state": "conformant"}},
        ]
        reader._apply_held_task_overlay(rows)
        self.assertNotIn("held_overlay", rows[0])
        self.assertNotIn("held_overlay", rows[1])

        reader.manager.records.mkdir(parents=True)
        (reader.manager.records / "held-task-ids.json").write_text(json.dumps({
            "schema_version": "assistant-viewer-held-tasks/v1",
            "task_ids": ["NSC-003", "NSC-012"],
        }), encoding="utf-8")
        reader._apply_held_task_overlay(rows)
        self.assertEqual("Outside Current Run", rows[0]["held_overlay"]["label"])
        self.assertEqual("Outside Current Run", rows[1]["held_overlay"]["label"])
        self.assertEqual("ready", rows[0]["state"])
        self.assertEqual("complete", rows[1]["state"])
        self.assertEqual("conformant", rows[1]["taskgraph"]["state"])

    def test_external_work_overlay_shows_only_live_noncrew_work(self):
        reader = AssistantSnapshot(self.root, self.checkout_root())
        reader.manager.records.mkdir(parents=True)
        path = reader.manager.records / "external-work-ids.json"
        rows = [
            {"id": "NSC-003", "state": "ready", "in_scope": False},
            {"id": "NSC-012", "state": "complete", "in_scope": False},
            {"id": "NSC-013", "state": "human_action", "in_scope": False},
        ]
        path.write_text(json.dumps({
            "schema_version": "assistant-viewer-external-work/v1",
            "tasks": [
                {"task_id": "NSC-003", "description": "PixelLab revision",
                 "expires_at": "2999-01-01T00:00:00+00:00"},
                {"task_id": "NSC-012", "description": "Stale marker",
                 "expires_at": "2999-01-01T00:00:00+00:00"},
                {"task_id": "NSC-013", "description": "Manual recovery",
                 "expires_at": "2999-01-01T00:00:00+00:00"},
            ],
        }), encoding="utf-8")
        reader._apply_external_work_overlay(rows)
        self.assertEqual("active", rows[0]["state"])
        self.assertTrue(rows[0]["in_scope"])
        self.assertEqual("external_work", rows[0]["progress"]["phase"])
        self.assertEqual("complete", rows[1]["state"])
        self.assertEqual("active", rows[2]["state"])
        self.assertEqual("human_action", rows[2]["external_work_overlay"]["underlying_state"])
        self.assertEqual("Manual recovery", rows[2]["external_work_overlay"]["description"])
        path.write_text(json.dumps({
            "schema_version": "assistant-viewer-external-work/v1",
            "tasks": [{"task_id": "NSC-003", "description": "Expired",
                       "expires_at": "2000-01-01T00:00:00+00:00"}],
        }), encoding="utf-8")
        fresh = [{"id": "NSC-003", "state": "ready", "in_scope": False}]
        reader._apply_external_work_overlay(fresh)
        self.assertEqual("ready", fresh[0]["state"])

        expired_review = [{"id": "NSC-013", "state": "human_action", "in_scope": False}]
        path.write_text(json.dumps({
            "schema_version": "assistant-viewer-external-work/v1",
            "tasks": [{"task_id": "NSC-013", "description": "Expired review",
                       "expires_at": "2000-01-01T00:00:00+00:00"}],
        }), encoding="utf-8")
        reader._apply_external_work_overlay(expired_review)
        self.assertEqual("human_action", expired_review[0]["state"])
        self.assertNotIn("external_work_overlay", expired_review[0])

    def test_committed_decomposition_supersedes_old_failed_attempt(self):
        reader = AssistantSnapshot(self.root, self.checkout_root())
        reader.manager.records.mkdir(parents=True)
        (reader.manager.records / "NSC-025.decomposition.json").write_text(
            json.dumps({"schema_version": "assistant-decomposition/v1",
                        "task_id": "NSC-025", "source": str(reader.source),
                        "status": "failed", "error": "old proposal rejected"}),
            encoding="utf-8",
        )
        row = reader.task_row({
            "schema_version": "2.0", "id": "NSC-025", "title": "Navigation", "parent": None,
            "depends_on": [], "contract_disposition": "active",
            "decomposition_state": "decomposed",
            "decomposition_children": ["NSC-089", "NSC-090"],
            "execution_scope": "not_applicable", "kind": "feature",
        })
        self.assertEqual("aggregate", row["state"])
        self.assertEqual("decomposition_applied", row["progress"]["phase"])

    DECOMPOSED_PARENT = {
        "schema_version": "2.0", "id": "NSC-025", "title": "Navigation", "parent": None,
        "depends_on": [], "contract_disposition": "active",
        "decomposition_state": "decomposed",
        "decomposition_children": ["NSC-089", "NSC-090"],
        "execution_scope": "not_applicable", "kind": "feature",
    }

    def write_parent_receipt(self, reader, **fields):
        reader.manager.records.mkdir(parents=True, exist_ok=True)
        (reader.manager.records / "NSC-025.decomposition.json").write_text(json.dumps({
            "schema_version": "assistant-decomposition/v1", "task_id": "NSC-025",
            "source": str(reader.source), **fields,
        }), encoding="utf-8")

    def test_conformant_decomposed_parent_without_receipt_stays_complete(self):
        reader = AssistantSnapshot(self.root, self.checkout_root())
        row = reader.task_row(self.DECOMPOSED_PARENT, taskgraph_state={"state": "conformant"})
        self.assertEqual("complete", row["state"])
        self.assertEqual("taskgraph_conformant", row["progress"]["phase"])

    def test_conformant_decomposed_parent_with_clone_bound_receipt_stays_complete(self):
        reader = AssistantSnapshot(self.root, self.checkout_root())
        self.write_parent_receipt(
            reader, source=str(Path(self.root).parent / "isolated-clone"),
            status="applied", child_ids=["NSC-900", "NSC-901"], run_id="old-run")
        row = reader.task_row(self.DECOMPOSED_PARENT, taskgraph_state={"state": "conformant"})
        self.assertEqual("complete", row["state"])
        self.assertNotIn("decomposition_run", row)

    def test_stale_receipt_child_ids_are_not_projected_for_a_decomposed_parent(self):
        reader = AssistantSnapshot(self.root, self.checkout_root())
        self.write_parent_receipt(reader, status="review_ready",
                                  child_ids=["NSC-900", "NSC-901"], run_id="old-run")
        row = reader.task_row(self.DECOMPOSED_PARENT)
        self.assertEqual("aggregate", row["state"])
        self.assertNotIn("decomposition_run", row)

    def test_pending_decomposed_parent_stays_aggregate_whatever_its_receipt(self):
        foreign = str(Path(self.root).parent / "isolated-clone")
        cases = {
            "absent": None,
            "foreign": dict(source=foreign, status="applied", child_ids=["NSC-089", "NSC-090"]),
            "failed": dict(status="failed", error="old"),
            "review_ready": dict(status="review_ready"),
            "mismatched applied": dict(status="applied", child_ids=["NSC-900"]),
        }
        for name, fields in cases.items():
            with self.subTest(name):
                reader = AssistantSnapshot(self.root, self.checkout_root())
                receipt = reader.manager.records / "NSC-025.decomposition.json"
                if receipt.exists():
                    receipt.unlink()
                if fields is not None:
                    self.write_parent_receipt(reader, **fields)
                for taskgraph_state in (None, {"state": "needs_testing"}):
                    row = reader.task_row(self.DECOMPOSED_PARENT, taskgraph_state=taskgraph_state)
                    self.assertEqual("aggregate", row["state"])
                    self.assertEqual("decomposition_applied", row["progress"]["phase"])

    def test_undecomposed_parent_with_foreign_receipt_is_still_blocked(self):
        reader = AssistantSnapshot(self.root, self.checkout_root())
        self.write_parent_receipt(reader, source=str(Path(self.root).parent / "isolated-clone"),
                                  status="applied", child_ids=["NSC-089"])
        row = reader.task_row({**self.DECOMPOSED_PARENT, "decomposition_state": "concrete",
                               "decomposition_children": [],
                               "execution_scope": "needs_execution_decomposition",
                               "kind": "implementation"})
        self.assertEqual("blocked", row["state"])

    def test_human_completion_overlay_keeps_formal_state_visible(self):
        reader = AssistantSnapshot(self.root, self.checkout_root())
        reader.manager.records.mkdir(parents=True)
        (reader.manager.records / "human-complete-ids.json").write_text(json.dumps({
            "schema_version": "assistant-viewer-human-complete/v1",
            "tasks": [
                {"task_id": "NSC-003", "note": "Vincent confirmed it exists."},
                {"task_id": "NSC-012", "note": "Vincent confirmed it exists."},
            ],
        }), encoding="utf-8")
        rows = [
            {"id": "NSC-003", "state": "blocked", "taskgraph": {"state": "not_delivered"},
             "held_overlay": {"label": "Outside Current Run"}},
            {"id": "NSC-012", "state": "active", "taskgraph": {"state": "not_delivered"}},
        ]
        reader._apply_human_complete_overlay(rows)
        self.assertEqual("complete", rows[0]["state"])
        self.assertEqual("not_delivered", rows[0]["human_completion_overlay"]["taskgraph_state"])
        self.assertEqual("blocked", rows[0]["human_completion_overlay"]["underlying_state"])
        self.assertEqual("active", rows[1]["state"])

    def test_human_completion_overlay_does_not_override_active_ger(self):
        reader = AssistantSnapshot(self.root, self.checkout_root())
        reader.manager.records.mkdir(parents=True)
        (reader.manager.records / "human-complete-ids.json").write_text(json.dumps({
            "schema_version": "assistant-viewer-human-complete/v1",
            "tasks": [{"task_id": "NSC-003", "note": "Vincent confirmed it exists."}],
        }), encoding="utf-8")
        rows = [{"id": "NSC-003", "state": "blocked", "ger_overlay": {"phase": "active"}}]
        reader._apply_human_complete_overlay(rows)
        self.assertEqual("blocked", rows[0]["state"])

    def test_ger_overlay_config_is_exact_authoritative_set(self):
        config_path = Path(__file__).with_name("held-task-ids.ger-20260914.json")
        value = json.loads(config_path.read_text(encoding="utf-8"))
        expected = {
            "NSC-003", "NSC-004", "NSC-005", "NSC-007", "NSC-008", "NSC-009",
            "NSC-012", "NSC-015", "NSC-017", "NSC-020", "NSC-030", "NSC-041",
            "NSC-044", "NSC-045", "NSC-046", "NSC-047", "NSC-048", "NSC-049",
            "NSC-052", "NSC-053", "NSC-054", "NSC-066", "NSC-071", "NSC-072",
            "NSC-078", "NSC-079", "NSC-080", "NSC-081", "NSC-082", "NSC-083",
            "NSC-085", "NSC-088",
        }
        self.assertEqual("assistant-viewer-held-tasks/v1", value["schema_version"])
        self.assertEqual(expected, set(value["task_ids"]))
        self.assertIn("NSC-088", value["task_ids"])
        self.assertNotIn("NSC-033", value["task_ids"])
        self.assertNotIn("NSC-089", value["task_ids"])

    def test_held_overlay_rejects_unknown_task_ids(self):
        root = self.checkout_root()
        reader = AssistantSnapshot(self.root, root)
        reader.manager.records.mkdir(parents=True)
        (reader.manager.records / "held-task-ids.json").write_text(json.dumps({
            "schema_version": "assistant-viewer-held-tasks/v1",
            "task_ids": ["NSC-999"],
        }), encoding="utf-8")
        with self.assertRaises(ValueError):
            reader._apply_held_task_overlay([{"id": "NSC-003", "state": "ready"}])

    def test_ger_active_then_pause_then_release_is_display_only(self):
        root = self.checkout_root()
        reader = AssistantSnapshot(self.root, root)
        reader.manager.records.mkdir(parents=True)
        path = reader.manager.records / "held-task-ids.json"
        path.write_text(json.dumps({
            "schema_version": "assistant-viewer-held-tasks/v1",
            "task_ids": ["NSC-003"],
        }), encoding="utf-8")

        def rows():
            result = [{"id": "NSC-003", "state": "complete", "taskgraph": {"state": "conformant"}},
                      {"id": "NSC-012", "state": "ready"}]
            reader._apply_held_task_overlay(result)
            return result

        self.assertEqual("Outside Current Run", rows()[0]["held_overlay"]["label"])
        change_marker(root, "start", "NSC-003")
        active = rows()[0]
        self.assertEqual("active", active["ger_overlay"]["phase"])
        self.assertEqual("complete", active["state"])
        self.assertEqual("conformant", active["taskgraph"]["state"])
        change_marker(root, "pause", "NSC-003")
        self.assertNotIn("ger_overlay", rows()[0])
        change_marker(root, "start", "NSC-003")
        change_marker(root, "finish", "NSC-003", ("NSC-012",))
        finished = rows()
        self.assertNotIn("held_overlay", finished[0])
        self.assertEqual("released", finished[0]["ger_overlay"]["phase"])
        self.assertEqual("released", finished[1]["ger_overlay"]["phase"])
        self.assertEqual("complete", finished[0]["state"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([], saved["task_ids"])
        self.assertEqual(["NSC-003", "NSC-012"], saved["released_ger_task_ids"])
        parent = [{"id": "NSC-003", "state": "aggregate"},
                  {"id": "NSC-012", "state": "active"}]
        reader._apply_held_task_overlay(parent)
        self.assertNotIn("ger_overlay", parent[0])
        self.assertNotIn("ger_overlay", parent[1])

    def test_ger_start_requires_hold_and_finish_rejects_held_child(self):
        root = self.checkout_root()
        reader = AssistantSnapshot(self.root, root)
        reader.manager.records.mkdir(parents=True)
        path = reader.manager.records / "held-task-ids.json"
        path.write_text(json.dumps({
            "schema_version": "assistant-viewer-held-tasks/v1",
            "task_ids": ["NSC-003", "NSC-012"],
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must be held"):
            change_marker(root, "start", "NSC-020")
        change_marker(root, "start", "NSC-003")
        with self.assertRaisesRegex(ValueError, "still held"):
            change_marker(root, "finish", "NSC-003", ("NSC-012",))
        self.assertEqual(["NSC-003", "NSC-012"],
                         json.loads(path.read_text(encoding="utf-8"))["task_ids"])


class RunningControllerProjectionTests(unittest.TestCase):
    """graph-controller.json timing must merge into progress, never replace it."""

    @staticmethod
    def _iso(epoch: float) -> str:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()

    @staticmethod
    def _row(task_id: str) -> dict:
        return {
            "id": task_id, "in_scope": True,
            "progress": {"phase": "existing_phase", "transition_context": "keep me"},
        }

    def test_currently_running_action_reports_live_stage_and_total_elapsed(self):
        rows = [self._row("NSC-1120")]
        action = {"kind": "start_worker", "task_id": "NSC-1120", "run_id": "r1"}
        controller = {
            "status": "running", "current_action": action,
            "history": [{"at": self._iso(1000.0), "action": action, "result_status": None}],
        }
        AssistantSnapshot._apply_controller_timing_projection(rows, controller, now=1090.0)
        progress = rows[0]["progress"]
        self.assertEqual(90.0, progress["current_attempt_elapsed_seconds"])
        self.assertEqual(90.0, progress["stage_elapsed_seconds"])
        self.assertEqual(90.0, progress["total_elapsed_seconds"])
        self.assertIsNone(progress["durable_stage_elapsed_seconds"])
        self.assertIsNone(progress["durable_task_elapsed_seconds"])
        # Existing progress fields (phase/transition_context) survive the merge.
        self.assertEqual("keep me", progress["transition_context"])
        self.assertEqual("existing_phase", progress["phase"])

    def test_completed_action_reports_durable_durations_and_no_live_ticking(self):
        rows = [self._row("NSC-1121")]
        action = {"kind": "prepare", "task_id": "NSC-1121", "source_commit": "a" * 40}
        controller = {
            # A different task is the live one now; NSC-1121's own attempt is done.
            "status": "running", "current_action": {"kind": "scope", "task_id": "NSC-9999"},
            "history": [
                {"at": self._iso(1000.0), "action": action, "result_status": None},
                {"at": self._iso(1180.0), "action": action, "result_status": "prepared"},
            ],
        }
        AssistantSnapshot._apply_controller_timing_projection(rows, controller, now=5000.0)
        progress = rows[0]["progress"]
        self.assertIsNone(progress["current_attempt_elapsed_seconds"])
        self.assertIsNone(progress["stage_elapsed_seconds"])
        self.assertEqual(180.0, progress["durable_stage_elapsed_seconds"])
        self.assertEqual(180.0, progress["durable_task_elapsed_seconds"])
        self.assertEqual(180.0, progress["total_elapsed_seconds"])

    def test_decomposition_action_is_timed_like_any_other_action(self):
        rows = [self._row("NSC-898")]
        action = {"kind": "decompose", "task_id": "NSC-898"}
        controller = {
            "status": "running", "current_action": action,
            "history": [{"at": self._iso(2000.0), "action": action, "result_status": None}],
        }
        AssistantSnapshot._apply_controller_timing_projection(rows, controller, now=2045.0)
        self.assertEqual(45.0, rows[0]["progress"]["stage_elapsed_seconds"])

    def test_post_crew_validation_accumulates_into_durable_task_total(self):
        rows = [self._row("NSC-042")]
        prepare_action = {"kind": "prepare", "task_id": "NSC-042", "source_commit": "b" * 40}
        post_crew_action = {"kind": "post_crew", "task_id": "NSC-042", "crew_run_id": "run-1"}
        controller = {
            "status": "running", "current_action": post_crew_action,
            "history": [
                {"at": self._iso(1000.0), "action": prepare_action, "result_status": None},
                {"at": self._iso(1010.0), "action": prepare_action, "result_status": "prepared"},
                {"at": self._iso(1500.0), "action": post_crew_action, "result_status": None},
            ],
        }
        AssistantSnapshot._apply_controller_timing_projection(rows, controller, now=1620.0)
        progress = rows[0]["progress"]
        self.assertEqual(120.0, progress["stage_elapsed_seconds"])
        self.assertEqual(10.0, progress["durable_stage_elapsed_seconds"])
        self.assertEqual(10.0, progress["durable_task_elapsed_seconds"])
        self.assertEqual(620.0, progress["total_elapsed_seconds"])

    def test_row_with_no_timing_evidence_is_left_untouched(self):
        rows = [self._row("NSC-999")]
        action = {"kind": "prepare", "task_id": "NSC-1"}
        controller = {
            "status": "running", "current_action": action,
            "history": [{"at": self._iso(1000.0), "action": action, "result_status": None}],
        }
        AssistantSnapshot._apply_controller_timing_projection(rows, controller, now=2000.0)
        progress = rows[0]["progress"]
        self.assertNotIn("current_attempt_elapsed_seconds", progress)
        self.assertNotIn("durable_task_elapsed_seconds", progress)
        self.assertEqual("keep me", progress["transition_context"])

    def test_no_controller_record_is_a_no_op(self):
        rows = [self._row("NSC-1")]
        AssistantSnapshot._apply_controller_timing_projection(rows, None, now=100.0)
        self.assertNotIn("current_attempt_elapsed_seconds", rows[0]["progress"])

    def test_timing_merge_preserves_execution_crew_stage_and_agent_fields(self):
        agents = [{"role": "validator", "status": "running", "duration_seconds": 12.0}]
        current_agent = {"role": "validator", "status": "running", "duration_seconds": 12.0}
        pipeline_stages = [{"label": "Execution crew · Validator 1 of 1",
                            "status": "active", "elapsed_seconds": 12.0}]
        rows = [{
            "id": "NSC-042", "in_scope": True,
            "progress": {"phase": "worker_running", "transition_context": "keep me",
                        "agents": agents, "current_agent": current_agent,
                        "pipeline_stages": pipeline_stages},
        }]
        action = {"kind": "start_worker", "task_id": "NSC-042", "run_id": "r1"}
        controller = {
            "status": "running", "current_action": action,
            "history": [{"at": self._iso(1000.0), "action": action, "result_status": None}],
        }
        AssistantSnapshot._apply_controller_timing_projection(rows, controller, now=1090.0)
        progress = rows[0]["progress"]
        self.assertEqual(90.0, progress["stage_elapsed_seconds"])
        self.assertEqual(90.0, progress["total_elapsed_seconds"])
        # The controller-journal timing merge adds its own keys without
        # touching the ExecutionCrew stage/agent detail already in progress.
        self.assertIs(agents, progress["agents"])
        self.assertIs(current_agent, progress["current_agent"])
        self.assertIs(pipeline_stages, progress["pipeline_stages"])


class GraphControllerTimingEndToEndTests(unittest.TestCase):
    """build() must actually wire the projection into /api/state, not just the helper."""

    setUp = fixture.InventoryTests.setUp
    run_git = fixture.InventoryTests.run_git

    def viewer_root(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Path(temp.name) / "Checkouts"

    def test_build_projects_timing_for_the_in_scope_task_named_by_the_controller(self):
        # The bare InventoryTests fixture contract has no contract_disposition,
        # so it is never in_scope; commit an executable revision so this test
        # actually exercises the in-scope projection path.
        self.contract.write_text(json.dumps({
            "schema_version": "2.0", "id": "NSC-042", "title": "Committed wall task", "depends_on": [],
            "contract_disposition": "active", "execution_scope": "single_agent",
            "exclusive_resources": ["repo-file:wall file.txt"],
        }), encoding="utf-8")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "Make NSC-042 executable")
        root = self.viewer_root()
        reader = AssistantSnapshot(self.root, root)
        task_id = next(row["id"] for row in reader.build()["tasks"] if row["in_scope"])
        action = {"kind": "prepare", "task_id": task_id, "source_commit": "c" * 40}
        controller = {
            "schema_version": "assistant-graph-controller/v1", "status": "running",
            "current_action": action, "targets": [task_id],
            "human_review_tasks": [], "auto_approve_gauntlet": False, "last_error": None,
            "history": [{"at": datetime.fromtimestamp(time.time() - 42.0, tz=timezone.utc).isoformat(),
                         "action": action, "result_status": None}],
        }
        records = root / ".assistant-control"
        records.mkdir(parents=True, exist_ok=True)
        (records / "graph-controller.json").write_text(json.dumps(controller), encoding="utf-8")
        row = next(row for row in reader.build()["tasks"] if row["id"] == task_id)
        self.assertGreaterEqual(row["progress"]["stage_elapsed_seconds"], 42.0)
        self.assertIn("phase", row["progress"])


class DeferredImportConsistencyTests(unittest.TestCase):
    """A viewer that outlives a commit must not mix module generations.

    A long-lived process caches modules from the HEAD it started on. A DEFERRED
    ``Pipeline.*`` import then loads NEW code expecting symbols the cached OLD
    modules do not have, and /api/state dies with ImportError on every request.
    The bug is not staleness -- a process running entirely old code works -- it
    is INCONSISTENT staleness, so the remedy is to load one generation at start.
    """

    def _nested_imports(self, source):
        tree = ast.parse(source)
        top_level = {id(node) for node in tree.body}
        return [node for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                and id(node) not in top_level]

    @staticmethod
    def _names(node):
        if isinstance(node, ast.ImportFrom):
            return [node.module or ""]
        return [alias.name for alias in node.names]

    def test_viewer_defers_no_pipeline_imports(self):
        source = Path(viewer_module.__file__).read_text(encoding="utf-8")
        nested = self._nested_imports(source)
        # Sanity probe: viewer.py:357 imports current_conformance AFTER putting
        # Pipeline/TaskGraph on sys.path, so it cannot be hoisted and must stay
        # nested. If this probe stops matching, the scan is broken rather than
        # the file clean, and the assertion below would pass vacuously.
        self.assertIn("current_conformance",
                      [name for node in nested for name in self._names(node)],
                      "nested-import scan found nothing it should have found")
        deferred = sorted(
            "%s (line %d)" % (name, node.lineno)
            for node in nested for name in self._names(node)
            if name.startswith("Pipeline.")
        )
        self.assertEqual(deferred, [], "deferred Pipeline imports load a NEWER "
                         "generation into a process holding OLDER cached modules")


if __name__ == "__main__":
    unittest.main()
