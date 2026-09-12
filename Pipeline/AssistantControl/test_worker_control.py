"""Fixture worker records, real isolated Git checkouts; no worker/provider launch."""
import hashlib
import json
import unittest
from unittest.mock import patch

from Pipeline.AssistantControl import test_checkouts as fixture
from Pipeline.AssistantControl.checkouts import write_record
from Pipeline.AssistantControl.result_inspection import ResultInspectionError
from Pipeline.AssistantControl.worker_control import request_stop, status, force_stop


class StopTests(unittest.TestCase):
    setUp = fixture.CheckoutTests.setUp
    run_git = fixture.CheckoutTests.run_git
    manager = fixture.CheckoutTests.manager

    def worker(self):
        manager = self.manager()
        record = manager.prepare("NSC-042")
        path = manager.records / "worker-runs" / "NSC-042" / hashlib.sha256(b"fixture-run").hexdigest() / "stop.request"
        record["worker"] = {"task_id": "NSC-042", "run_id": "fixture-run", "lease_id": "fixture-lease",
                            "status": "running", "stop_request_path": str(path)}
        write_record(manager.records / "NSC-042.json", record)
        return manager, record, path

    def test_stop_exact_run_is_idempotent_and_does_not_claim_exit(self):
        manager, record, path = self.worker()
        with self.assertRaisesRegex(ValueError, "differs"):
            request_stop(manager, "NSC-042", run_id="other-run")
        self.assertFalse(path.exists())
        first = request_stop(manager, "NSC-042", run_id="fixture-run")
        saved = path.read_bytes()
        second = request_stop(manager, "NSC-042", run_id="fixture-run")
        self.assertEqual(first, second)
        self.assertEqual(saved, path.read_bytes())
        view = status(manager, "NSC-042")
        self.assertIsNone(view["host_identity_alive"])
        self.assertFalse(view["capacity_released"])
        self.assertEqual("running", view["worker"]["status"])

    def test_foreign_stop_path_is_refused(self):
        manager, record, path = self.worker()
        record["worker"]["stop_request_path"] = str(self.root / "do-not-write")
        write_record(manager.records / "NSC-042.json", record)
        with self.assertRaisesRegex(ValueError, "path differs"):
            request_stop(manager, "NSC-042", run_id="fixture-run")
        self.assertFalse((self.root / "do-not-write").exists())

    def test_startup_can_be_stopped_before_worker_record_exists(self):
        manager, record, path = self.worker()
        record["launch"] = {**record.pop("worker"), "status": "starting"}
        write_record(manager.records / "NSC-042.json", record)
        result = request_stop(manager, "NSC-042", run_id="fixture-run")
        self.assertTrue(result["stop_requested"])
        self.assertTrue(path.is_file())
        self.assertEqual("starting", status(manager, "NSC-042")["worker"]["status"])

    def test_child_handshake_recovers_parent_crash_without_guessing_pid(self):
        manager, record, path = self.worker()
        record["launch"] = {**record.pop("worker"), "status": "starting"}
        write_record(manager.records / "NSC-042.json", record)
        path.parent.mkdir(parents=True)
        request = {key: record["launch"][key] for key in ("task_id", "run_id", "lease_id")}
        request.update(source=str(manager.source), checkout_root=str(manager.root), checkout=record["checkout"])
        request_path = path.parent / "launch.request.json"
        write_record(request_path, request)
        identity = {"pid": 123, "created_ticks": 5, "image": "fixture"}
        proof = {**request, "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
                 "process_identity": identity}
        write_record(path.parent / "child.identity.json", proof)
        with patch("Pipeline.AssistantControl.worker_control.matches", return_value=False) as match:
            self.assertFalse(status(manager, "NSC-042")["host_identity_alive"])
            match.assert_called_once_with(identity)
        request_path.write_text("{}")
        with self.assertRaisesRegex(ValueError, "handshake"):
            status(manager, "NSC-042")

    def test_force_stop_targets_recorded_host_and_checkout_without_releasing_capacity(self):
        manager, record, path = self.worker()
        record["worker"]["process_identity"] = {"pid": 123, "created_ticks": 1, "image": "fixture"}
        write_record(manager.records / "NSC-042.json", record)
        with patch("Pipeline.AssistantControl.worker_control.matches", return_value=True), \
             patch("Pipeline.AssistantControl.worker_control.terminate", return_value=True) as stop_host, \
             patch("Pipeline.AssistantControl.worker_control.stop_containers", return_value={"containers_stopped": True}) as stop_docker:
            result = force_stop(manager, "NSC-042", run_id="fixture-run")
        stop_host.assert_called_once_with(record["worker"]["process_identity"])
        self.assertEqual(manager.root / "NSC-042", stop_docker.call_args.args[0])
        self.assertTrue(result["host_exit_confirmed"])
        self.assertFalse(result["capacity_released"])
        self.assertEqual("stopped", manager.observe("NSC-042")["worker"]["status"])

    def test_terminal_recycled_host_is_not_killed_but_owned_container_cleanup_runs(self):
        manager, record, _ = self.worker()
        record["worker"].update(status="failed", process_identity={"pid": 123, "created_ticks": 1, "image": "fixture"})
        write_record(manager.records / "NSC-042.json", record)
        with patch("Pipeline.AssistantControl.worker_control.matches", return_value=False), \
             patch("Pipeline.AssistantControl.worker_control.terminate") as stop_host, \
             patch("Pipeline.AssistantControl.worker_control.stop_containers", return_value={"containers_stopped": True}) as stop_docker:
            result = force_stop(manager, "NSC-042", run_id="fixture-run")
        stop_host.assert_not_called()
        stop_docker.assert_called_once()
        self.assertTrue(result["host_exit_confirmed"])


class PostExitStatusTests(unittest.TestCase):
    def attempt(self, worker_status="running"):
        return {
            "task_id": "NSC-899",
            "run_id": "assistant-run",
            "process_identity": {"pid": 123, "created_ticks": 5, "image": "python.exe"},
            "lease_id": "lease",
            "plan_id": "plan",
            "source_head": "a" * 40,
            "task_contract_sha256": "b" * 64,
            "stop_request_path": r"C:\fixture\worker-runs\NSC-899\run\stop.request",
            "job_name": "assistant-job-fixture",
            "status": worker_status,
        }

    def test_dead_host_rereads_and_authenticates_same_succeeded_attempt(self):
        original = self.attempt()
        refreshed = self.attempt("succeeded")
        checkouts = object()
        with patch("Pipeline.AssistantControl.worker_control._worker",
                   side_effect=[original, refreshed]) as observe, \
             patch("Pipeline.AssistantControl.worker_control.matches", return_value=False), \
             patch("Pipeline.AssistantControl.result_inspection.inspect_result",
                   return_value={"status": "review_ready"}) as inspect:
            result = status(checkouts, "NSC-899")
        self.assertEqual("succeeded", result["worker"]["status"])
        self.assertFalse(result["host_identity_alive"])
        self.assertEqual(2, observe.call_count)
        inspect.assert_called_once_with(checkouts, "NSC-899", assistant_run_id="assistant-run")

    def test_dead_host_rejects_changed_owned_attempt_identity(self):
        for field in ("task_id", "run_id", "process_identity", "lease_id", "plan_id",
                      "source_head", "task_contract_sha256", "stop_request_path", "job_name"):
            with self.subTest(field=field):
                original = self.attempt()
                refreshed = json.loads(json.dumps(self.attempt("succeeded")))
                refreshed[field] = ({"pid": 999, "created_ticks": 9, "image": "other.exe"}
                                    if field == "process_identity" else "changed")
                with patch("Pipeline.AssistantControl.worker_control._worker",
                           side_effect=[original, refreshed]), \
                     patch("Pipeline.AssistantControl.worker_control.matches", return_value=False), \
                     self.assertRaisesRegex(ValueError, "identity changed after host exit"):
                    status(object(), "NSC-899")

    def test_dead_host_with_still_running_record_fails_closed(self):
        original = self.attempt()
        refreshed = json.loads(json.dumps(original))
        with patch("Pipeline.AssistantControl.worker_control._worker",
                   side_effect=[original, refreshed]), \
             patch("Pipeline.AssistantControl.worker_control.matches", return_value=False), \
             patch("Pipeline.AssistantControl.result_inspection.inspect_result") as inspect:
            result = status(object(), "NSC-899")
        self.assertEqual("running", result["worker"]["status"])
        self.assertFalse(result["host_identity_alive"])
        inspect.assert_not_called()

    def test_dead_host_rejects_tampered_succeeded_artifacts(self):
        original = self.attempt()
        refreshed = self.attempt("succeeded")
        with patch("Pipeline.AssistantControl.worker_control._worker",
                   side_effect=[original, refreshed]), \
             patch("Pipeline.AssistantControl.worker_control.matches", return_value=False), \
             patch("Pipeline.AssistantControl.result_inspection.inspect_result",
                   side_effect=ResultInspectionError("crew result bytes differ from receipt")):
            with self.assertRaisesRegex(ResultInspectionError, "result bytes differ"):
                status(object(), "NSC-899")


if __name__ == "__main__":
    unittest.main()
