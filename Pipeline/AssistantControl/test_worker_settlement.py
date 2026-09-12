"""Temporary Git + fixture receipts; host/Docker observations are mocked."""
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl import test_worker_control as fixture
from Pipeline.AssistantControl.admission import REGISTRY_SCHEMA, _source_registry_paths, _read_registry
from Pipeline.AssistantControl.checkouts import write_record
from Pipeline.AssistantControl.worker_settlement import settle_completed


class SettlementTests(unittest.TestCase):
    def setUp(self):
        fixture.StopTests.setUp(self)
        self.cleanup_patch = patch(
            "Pipeline.AssistantControl.worker_settlement.remove_unused_project_resources",
            return_value={"containers_removed": [], "networks_removed": [], "volumes_removed": []})
        self.cleanup_mock = self.cleanup_patch.start()
        self.addCleanup(self.cleanup_patch.stop)
    run_git = fixture.StopTests.run_git
    manager = fixture.StopTests.manager
    worker = fixture.StopTests.worker

    def completed(self):
        manager, record, _ = self.worker()
        record["scope"] = {"lease_id": "fixture-lease", "plan_id": "fixture-plan"}
        expected = {"task_id": "NSC-042", **record["scope"], "source_head": record["source_commit"],
                    "task_contract_sha256": record["task_contract_sha256"]}
        output = Path(record["checkout"]) / "Pipeline/ExecutionCrew/outputs/fixture"
        output.mkdir(parents=True)
        receipt = {**expected, "run_id": "crew-fixture"}
        for key, data in (("result", b"fixture-result"), ("candidate", b"fixture-patch")):
            path = output / key
            path.write_bytes(data)
            receipt[key + "_path"] = str(path)
            receipt[key + "_sha256"] = hashlib.sha256(data).hexdigest()
        record["worker"].update({**expected, "status": "succeeded", "crew_run_id": "crew-fixture",
                                 "receipt": receipt, "process_identity": {"fixture": True}})
        write_record(manager.records / "NSC-042.json", record)
        _, registry = _source_registry_paths(manager.source)
        owned = {"status": "active", "task_id": "NSC-042", "run_id": "fixture-run",
                 "lease_id": "fixture-lease", "checkout_root": str(manager.root), "checkout": record["checkout"]}
        other = {"status": "active", "task_id": "NSC-043", "run_id": "other-run"}
        write_record(registry, {"schema_version": REGISTRY_SCHEMA, "source": str(manager.source),
                                "reservations": [owned, other]})
        return manager, record, registry

    def test_exit_required_then_release_exactly_once_without_losing_other_arrival(self):
        manager, record, registry = self.completed()
        with patch("Pipeline.AssistantControl.worker_settlement.matches", return_value=True):
            with self.assertRaisesRegex(ValueError, "exit"):
                settle_completed(manager, "NSC-042", run_id="fixture-run")
        with patch("Pipeline.AssistantControl.worker_settlement.matches", return_value=False), \
             patch("Pipeline.AssistantControl.worker_settlement.inventory", return_value=[]):
            first = settle_completed(manager, "NSC-042", run_id="fixture-run")
            self.assertEqual(first, settle_completed(manager, "NSC-042", run_id="fixture-run"))
        self.assertEqual(2, self.cleanup_mock.call_count)
        remaining = _read_registry(registry, manager.source)["reservations"]
        self.assertEqual(["NSC-043"], [item["task_id"] for item in remaining])

    def test_changed_artifact_never_releases_capacity(self):
        manager, record, registry = self.completed()
        Path(record["worker"]["receipt"]["candidate_path"]).write_bytes(b"modified")
        with patch("Pipeline.AssistantControl.worker_settlement.matches", return_value=False):
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                settle_completed(manager, "NSC-042", run_id="fixture-run")
        self.assertEqual(2, len(_read_registry(registry, manager.source)["reservations"]))

    def test_rejected_receipt_with_no_candidate_artifact_settles_as_failed(self):
        manager, record, registry = self.completed()
        receipt = record["worker"]["receipt"]
        receipt.update(crew_status="rejected", returncode=1,
                       rejection_reasons=["max_turns"], candidate_path=None,
                       candidate_sha256=None)
        record["worker"]["status"] = "succeeded"
        write_record(manager.records / "NSC-042.json", record)
        with patch("Pipeline.AssistantControl.worker_settlement.matches", return_value=False), \
             patch("Pipeline.AssistantControl.worker_settlement.inventory", return_value=[]):
            self.assertTrue(settle_completed(manager, "NSC-042", run_id="fixture-run")["capacity_released"])
        settled = manager.observe("NSC-042")["worker"]
        self.assertEqual("failed", settled["status"])
        self.assertEqual("rejected", settled["receipt"]["crew_status"])
        self.assertEqual(["NSC-043"], [item["task_id"] for item in
            _read_registry(registry, manager.source)["reservations"]])

    def test_only_explicit_no_child_spawn_failure_can_settle_without_identity(self):
        manager, record, registry = self.completed()
        worker = record.pop("worker")
        record["launch"] = {key: worker[key] for key in
            ("task_id", "run_id", "lease_id", "stop_request_path")}
        record["launch"]["status"] = "starting"
        write_record(manager.records / "NSC-042.json", record)
        with patch("Pipeline.AssistantControl.worker_settlement.inventory", return_value=[]):
            with self.assertRaisesRegex(ValueError, "host exit"):
                settle_completed(manager, "NSC-042", run_id="fixture-run")
            record["launch"].update(status="spawn_failed", no_child_created=True)
            write_record(manager.records / "NSC-042.json", record)
            self.assertTrue(settle_completed(manager, "NSC-042", run_id="fixture-run")["capacity_released"])
        self.assertEqual(["NSC-043"], [item["task_id"] for item in
            _read_registry(registry, manager.source)["reservations"]])

    def test_terminal_host_with_live_descendant_keeps_capacity(self):
        manager, record, registry = self.completed()
        worker = record["worker"]
        worker["job_name"] = "assistant-job-" + hashlib.sha256(
            str(Path(worker["stop_request_path"]).parent).encode()).hexdigest()
        with patch("Pipeline.AssistantControl.worker_settlement.matches", return_value=False), \
             patch("Pipeline.AssistantControl.worker_settlement.active_count", return_value=1):
            for state in ("succeeded", "failed", "stopped"):
                worker["status"] = state
                write_record(manager.records / "NSC-042.json", record)
                with self.assertRaisesRegex(ValueError, "tree exit"):
                    settle_completed(manager, "NSC-042", run_id="fixture-run")
                self.assertEqual(2, len(_read_registry(registry, manager.source)["reservations"]))

    def test_child_exits_before_worker_record_is_retryable_after_settlement(self):
        manager, record, registry = self.completed()
        worker = record.pop("worker")
        record["launch"] = {key: worker[key] for key in
            ("task_id", "run_id", "lease_id", "stop_request_path", "process_identity")}
        record["launch"].update(status="ready_pending", job_name="assistant-job-" + hashlib.sha256(
            str(Path(worker["stop_request_path"]).parent).encode()).hexdigest())
        write_record(manager.records / "NSC-042.json", record)
        with patch("Pipeline.AssistantControl.worker_settlement.matches", return_value=False), \
             patch("Pipeline.AssistantControl.worker_settlement.active_count", return_value=0), \
             patch("Pipeline.AssistantControl.worker_settlement.inventory", return_value=[]):
            settle_completed(manager, "NSC-042", run_id="fixture-run")
        launch = manager.observe("NSC-042")["launch"]
        self.assertEqual("failed", launch["status"])
        self.assertTrue(launch["capacity_released"])

    def test_post_spawn_identity_failure_requires_held_child_exit_before_readiness(self):
        manager, record, registry = self.completed()
        worker = record.pop("worker")
        launch = {key: worker[key] for key in ("task_id", "run_id", "lease_id", "stop_request_path")}
        record["launch"] = launch
        launch.update(status="spawn_failed", no_child_created=False, before_ready=True)
        with patch("Pipeline.AssistantControl.worker_settlement.inventory", return_value=[]):
            write_record(manager.records / "NSC-042.json", record)
            with self.assertRaisesRegex(ValueError, "host exit"):
                settle_completed(manager, "NSC-042", run_id="fixture-run")
            launch["child_exit_confirmed"] = True
            write_record(manager.records / "NSC-042.json", record)
            ready = Path(launch["stop_request_path"]).parent / "ready.receipt.json"
            ready.parent.mkdir(parents=True, exist_ok=True)
            ready.write_text("{}")
            with self.assertRaisesRegex(ValueError, "host exit"):
                settle_completed(manager, "NSC-042", run_id="fixture-run")
            ready.unlink()
            self.assertTrue(settle_completed(manager, "NSC-042", run_id="fixture-run")["capacity_released"])

    def test_failed_worker_releases_after_tree_and_containers_exit(self):
        manager, record, registry = self.completed()
        worker = record["worker"]
        worker.update(status="failed", receipt=None)
        write_record(manager.records / "NSC-042.json", record)
        with patch("Pipeline.AssistantControl.worker_settlement.matches", return_value=False), \
             patch("Pipeline.AssistantControl.worker_settlement.active_count", return_value=0), \
             patch("Pipeline.AssistantControl.worker_settlement.inventory", return_value=[]) as containers:
            with self.assertRaisesRegex(ValueError, "tree exit"):
                settle_completed(manager, "NSC-042", run_id="fixture-run")
            worker["job_name"] = "assistant-job-" + hashlib.sha256(
                str(Path(worker["stop_request_path"]).parent).encode()).hexdigest()
            write_record(manager.records / "NSC-042.json", record)
            containers.return_value = [{"running": True}]
            with self.assertRaisesRegex(ValueError, "containers"):
                settle_completed(manager, "NSC-042", run_id="fixture-run")
            self.assertEqual(2, len(_read_registry(registry, manager.source)["reservations"]))
            containers.return_value = []
            result = settle_completed(manager, "NSC-042", run_id="fixture-run")
            self.assertTrue(result["capacity_released"])
            self.assertFalse(result["approval_granted"])
            self.assertEqual(["NSC-043"], [item["task_id"] for item in
                _read_registry(registry, manager.source)["reservations"]])

    def test_cleanup_failure_does_not_discard_completed_result_or_capacity_release(self):
        manager, record, registry = self.completed()
        self.cleanup_mock.side_effect = RuntimeError("Docker daemon unavailable")
        with patch("Pipeline.AssistantControl.worker_settlement.matches", return_value=False), \
             patch("Pipeline.AssistantControl.worker_settlement.inventory", return_value=[]):
            result = settle_completed(manager, "NSC-042", run_id="fixture-run")
        self.assertTrue(result["capacity_released"])
        settled = manager.observe("NSC-042")["worker"]
        self.assertEqual("succeeded", settled["status"])
        self.assertEqual("crew-fixture", settled["crew_run_id"])
        self.assertEqual(["NSC-043"], [item["task_id"] for item in
            _read_registry(registry, manager.source)["reservations"]])


if __name__ == "__main__":
    unittest.main()
