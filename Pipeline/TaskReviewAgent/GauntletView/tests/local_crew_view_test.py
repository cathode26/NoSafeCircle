"""Pure/component regressions for local crew display and run isolation.

Handcrafted disposable artifacts test display-only joins; they do not claim
real task admission, delivery, provider execution or Unity validation.
"""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import unittest
import uuid
from unittest.mock import patch

sys.dont_write_bytecode = True
VIEW = Path(os.environ.get("NSC_LOCAL_CREW_VIEW_SOURCE", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(VIEW.parents[2]))
sys.path.insert(0, str(VIEW))
from Pipeline.TaskReviewAgent.contracts import semantic_sha256

spec = importlib.util.spec_from_file_location("local_crew_view_server", VIEW / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

TASK, WORKER_RUN, CREW = "NSC-1013", "worker-run-1", "crew-run-1"
HEAD, TREE, CONTRACT = "a" * 40, "b" * 40, "c" * 64


class LocalCrewViewTests(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ.get("NSC_LOCAL_CREW_VIEW_TEMP", r"C:\NSC\LocalCrewViewTmp")).resolve()
        self.root = parent / ("crew-view-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.source = self.root / "source"
        (self.source / "Tasks").mkdir(parents=True)
        self.run_root = self.root / "run"
        self.checkout = self.run_root / "checkouts" / TASK
        self.checkout.mkdir(parents=True)
        self.state = self.run_root / "checkouts" / ".task-review-agent"
        self.worker = self.state / "outputs" / TASK / WORKER_RUN
        self.crew = self.run_root / "crew-output" / TASK / CREW
        self.assignment = self.state / "session-pools" / "repository" / "profile" / "assignments" / (CREW + ".leases.json")
        self.record = {"task_id": TASK, "run_id": "local-run", "worker_id": "slot-01", "lease_id": "lease-01",
            "worker_run_id": WORKER_RUN, "source_commit": HEAD, "source_tree": TREE,
            "task_contract_sha256": CONTRACT, "checkout_path": str(self.checkout), "state": "agent_working",
            "pipeline_stage": "execution_crew", "action": "validate_execution_scope",
            "started_at_utc": "2026-09-09T04:21:00Z", "updated_at_utc": "2026-09-09T04:28:00Z"}
        self.local = {"execution_mode": "local_rehearsal", "run_id": "local-run", "source_commit": HEAD,
            "source_tree": TREE, "source_repository": str(self.source), "source_branch": "fixture", "source_clean": True,
            "provider_profile": "all-claude", "max_capacity": 1, "status": "running", "events": [],
            "tasks": {TASK: self.record}, "contracts": {TASK: {"id": TASK, "title": "Create Alpha script",
                "kind": "implementation", "contract_disposition": "active", "depends_on": []}}}
        manifest = {"task_id": TASK, "local_run_id": "local-run", "worker_id": "slot-01", "lease_id": "lease-01",
            "source_head": HEAD, "source_tree": TREE, "task_contract_sha256": CONTRACT,
            "checkout_path": str(self.checkout)}
        manifest["manifest_sha256"] = semantic_sha256(manifest)
        self.write(self.state / (TASK + ".json"), manifest)
        self.write(self.worker / "run.json", {"run_id": WORKER_RUN, "task_id": TASK, "worker_id": "slot-01"})
        self.write_rows(self.worker / "progress.jsonl", [{"event": "pipeline_action_started", "run_id": WORKER_RUN,
            "task_id": TASK, "worker_id": "slot-01", "timestamp_utc": "2026-09-09T04:28:00Z",
            "fields": {"action": "run_execution_crew"}}])
        self.lease = {"task_id": TASK, "worker_slot_id": "slot-01", "worker_run_id": CREW, "source_commit": HEAD,
                      "checkout_identity": "manifest-sha256:" + hashlib.sha256((self.state / (TASK + ".json")).read_bytes()).hexdigest()}
        self.write(self.assignment, {"run_id": CREW, "leases": {"implementer": self.lease}})
        self.rows = [self.event("run_started", "04:28:01", required_roles=["contract_locality_auditor", "implementer", "test_author", "validator"]),
                     self.event("role_started", "04:28:02", role="implementer", attempt=1, provider="claude")]
        self.write_rows(self.crew / "progress.jsonl", self.rows)
        self.view = server.Snapshot(self.source / "Tasks", self.run_root / "checkouts", local_run_root=self.run_root)
        self.view.local_snapshot = lambda: self.local

    def tearDown(self):
        parent = Path(os.environ.get("NSC_LOCAL_CREW_VIEW_TEMP", r"C:\NSC\LocalCrewViewTmp")).resolve()
        if self.root.resolve().parent != parent or not self.root.name.startswith("crew-view-"):
            raise AssertionError("fixture cleanup escaped its exact temporary root")
        shutil.rmtree(self.root)

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

    @staticmethod
    def write_rows(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    @staticmethod
    def event(event, clock, **fields):
        return {"event": event, "run_id": CREW, "task_id": TASK, "timestamp_utc": "2026-09-09T" + clock + "Z", **fields}

    def bound(self):
        return self.view.bound_local_crew(self.local, TASK, self.record)

    def test_current_role_is_read_before_any_completed_role_result_exists(self):
        with patch.object(server.time, "time", return_value=server.parse_timestamp("2026-09-09T04:28:07Z")):
            task = self.view.build()["tasks"][0]
        self.assertEqual(task["progress"]["current_agent"]["role"], "implementer")
        self.assertEqual(task["progress"]["current_agent"]["duration_seconds"], 5)
        self.assertEqual(task["worker"]["role"], "implementer")
        self.assertEqual(task["progress"]["crew_run_id"], CREW)
        self.assertIn("Implementer", " ".join(task["node_summary_lines"]))
        self.assertIn("Execution crew · Implementer 1 of 3", " ".join(task["node_summary_lines"]))
        self.assertEqual(task["progress"]["stage_elapsed_seconds"], 5)

    def test_progress_changes_fingerprint_and_moves_display_to_next_role(self):
        with patch.object(server.time, "time", return_value=server.parse_timestamp("2026-09-09T04:28:20Z")):
            before = self.view.fingerprint()
            self.write_rows(self.crew / "progress.jsonl", self.rows + [
                self.event("role_completed", "04:28:10", role="implementer", attempt=1, status="succeeded"),
                self.event("role_started", "04:28:11", role="validator", attempt=1)])
            after = self.view.fingerprint()
            task = self.view.build()["tasks"][0]
        self.assertNotEqual(before, after)
        self.assertEqual(task["progress"]["current_agent"]["role"], "validator")
        self.assertEqual(task["progress"]["agents"][0]["status"], "completed")

    def test_stale_crew_from_previous_action_is_not_selected(self):
        self.write_rows(self.crew / "progress.jsonl", [self.event("run_started", "04:27:00")])
        self.assertIsNone(self.bound())

    def test_foreign_source_worker_and_checkout_binding_are_rejected(self):
        for key, value in (("source_commit", "d" * 40), ("worker_slot_id", "other-slot"),
                           ("checkout_identity", "manifest-sha256:" + "0" * 64)):
            with self.subTest(key=key):
                self.write(self.assignment, {"run_id": CREW, "leases": {"implementer": {**self.lease, key: value}}})
                self.assertIsNone(self.bound())

    def test_foreign_worker_run_metadata_and_changed_manifest_are_rejected(self):
        self.write(self.worker / "run.json", {"run_id": "another-run", "task_id": TASK, "worker_id": "slot-01"})
        self.assertIsNone(self.bound())
        self.write(self.worker / "run.json", {"run_id": WORKER_RUN, "task_id": TASK, "worker_id": "slot-01"})
        path = self.state / (TASK + ".json")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["worker_id"] = "other"
        self.write(path, manifest)
        self.assertIsNone(self.bound())

    def test_pool_identity_requires_exact_manifest_bytes_not_only_semantic_hash(self):
        path = self.state / (TASK + ".json")
        original = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(original, indent=4), encoding="utf-8")
        self.assertIsNone(self.bound())
        updated = {**self.lease, "checkout_identity": "manifest-sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()}
        self.write(self.assignment, {"run_id": CREW, "leases": {"implementer": updated}})
        self.assertIsNotNone(self.bound())

    def test_unrelated_crew_changes_do_not_change_local_fingerprint(self):
        with patch.object(server.time, "time", return_value=server.parse_timestamp("2026-09-09T04:28:07Z")):
            before = self.view.fingerprint()
            other = self.run_root / "crew-output" / "NSC-999" / "unrelated" / "progress.jsonl"
            self.write_rows(other, [self.event("role_started", "04:28:03", task_id="NSC-999", role="validator")])
            self.assertEqual(before, self.view.fingerprint())

    def test_locality_audit_is_preparation_not_one_of_three_execution_roles(self):
        self.write_rows(self.crew / "progress.jsonl", [self.rows[0],
            self.event("role_started", "04:28:02", role="contract_locality_auditor", attempt=1)])
        task = self.view.build()["tasks"][0]
        self.assertEqual(task["progress"]["stage_label"], "Preparing execution crew · Contract Locality Auditor")
        self.assertNotIn("role_count", task["progress"]["current_agent"])

    def test_exact_supervisor_step_overrides_stale_checkout_stage_with_own_clock(self):
        event = {"event": "pipeline_action_started", "run_id": WORKER_RUN, "task_id": TASK, "worker_id": "slot-01",
            "timestamp_utc": "2026-09-09T04:28:00Z", "fields": {"action": "prepare_task_checkout"}}
        self.write_rows(self.worker / "progress.jsonl", [event])
        with patch.object(server.time, "time", return_value=server.parse_timestamp("2026-09-09T04:28:24Z")):
            before = self.view.fingerprint()
            task = self.view.build()["tasks"][0]
            self.write_rows(self.worker / "progress.jsonl", [event, {**event,
                "event": "state_observation_started", "timestamp_utc": "2026-09-09T04:28:23Z", "fields": {}}])
            self.assertNotEqual(before, self.view.fingerprint())
            observed = self.view.build()["tasks"][0]
        self.assertEqual(task["progress"]["stage_label"], "Preparing checkout")
        self.assertEqual(task["progress"]["stage_elapsed_seconds"], 24)
        self.assertEqual(observed["progress"]["stage_label"], "Reading workflow state")
        self.assertEqual(observed["progress"]["stage_elapsed_seconds"], 1)

    def launch_fixture(self):
        self.record.update(state="architect_admission", pipeline_stage="architect_admission",
                           lease_id=None, started_at_utc=None)
        self.write(self.run_root / "autonomous-manifest.json", {"run_id": "local-run",
            "local_rehearsal_root": str(self.run_root), "source_repository": str(self.source)})
        launch = {"event": "worker_launched", "run_id": WORKER_RUN, "task_id": TASK, "worker_id": "slot-01",
            "pid": 100, "timestamp_utc": "2026-09-09T04:27:50Z", "checkout_path": str(self.checkout),
            "result_artifact_path": str(self.worker / "run_result.json")}
        self.write_rows(self.run_root / "scheduler-events.jsonl", [launch])
        return launch

    def test_exact_recorded_worker_launch_is_active_before_lease(self):
        self.launch_fixture()
        task = self.view.build()["tasks"][0]
        self.assertEqual(task["state"], "active")
        self.assertEqual(task["local_state"], "architect_admission")
        self.assertEqual(task["worker"]["status"], "starting")
        self.assertEqual(task["worker"]["pid"], 100)

    def test_admission_without_matching_launch_does_not_claim_active(self):
        launch = self.launch_fixture()
        for key, value in (("event", "architect_selected"), ("worker_id", "different-slot"),
                           ("run_id", "different-run"), ("pid", None), ("result_artifact_path", str(self.root / "foreign.json"))):
            with self.subTest(key=key):
                self.write_rows(self.run_root / "scheduler-events.jsonl", [{**launch, key: value}])
                self.assertEqual(self.view.build()["tasks"][0]["state"], "ready")

    def test_recorded_return_or_result_stops_prelease_startup_display(self):
        launch = self.launch_fixture()
        self.write_rows(self.run_root / "scheduler-events.jsonl", [launch, {"event": "worker_returned_to_pool",
            "task_id": TASK, "worker_id": "slot-01", "timestamp_utc": "2026-09-09T04:28:01Z"}])
        self.assertEqual(self.view.build()["tasks"][0]["state"], "ready")
        self.write_rows(self.run_root / "scheduler-events.jsonl", [launch])
        self.write(self.worker / "run_result.json", {"status": "failed"})
        self.assertEqual(self.view.build()["tasks"][0]["state"], "ready")


if __name__ == "__main__":
    unittest.main(verbosity=2)
