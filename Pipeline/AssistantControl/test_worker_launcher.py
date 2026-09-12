"""Temporary real-subprocess tests for the readiness-gated worker launcher."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

from Pipeline.AssistantControl.admission import release, reserve
from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.AssistantControl.worker_launcher import WorkerLauncherError, start
from Pipeline.AssistantControl.checkouts import write_record
from Pipeline.AssistantControl.process_identity import identify
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity
from Pipeline.AssistantControl.process_identity import matches
from Pipeline.AssistantControl.windows_job import create_and_assign


class WorkerLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git("init")
        name, email = validated_agent_git_identity()
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)
        (self.source / "Tasks").mkdir()
        (self.source / "Assets/Feature/Tests").mkdir(parents=True)
        (self.source / "Assets/Feature/Feature.cs").write_text("class Feature {}\n")
        (self.source / "Assets/Feature/Tests/FeatureTests.cs").write_text("class FeatureTests {}\n")
        (self.source / "Tasks/NSC-042.yaml").write_text(json.dumps({
            "id": "NSC-042", "title": "launcher fixture", "contract_disposition": "active",
            "kind": "implementation", "execution_scope": "single_agent",
            "decomposition_state": "concrete", "depends_on": [],
            "exclusive_resources": ["repo-file:Assets/Feature"],
        }))
        self.git("add", ".")
        self.git("commit", "-m", "launcher fixture")
        self.checkouts = Checkouts(self.source, self.root / "checkouts")
        self.checkouts.prepare("NSC-042")
        AssistantScopePlanner(self.checkouts).plan(
            "NSC-042", ExecutionScopePlan(
                ("Assets/Feature/Feature.cs",), (),
                ("Assets/Feature/Tests/FeatureTests.cs",), (),
            ), lease_id="lease-042")
        self.reservation = reserve(self.checkouts, "NSC-042", "run-042", dependency_reader=self.dependencies)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.source), *args],
                              capture_output=True, check=True).stdout

    @staticmethod
    def dependencies(source, task_id, checkout_root):
        return {"task_id": task_id,
                "source_commit": subprocess.run(
                    ["git", "-C", str(source), "rev-parse", "HEAD"],
                    capture_output=True, check=True).stdout.decode().strip(),
                "source_unchanged_during_read": True,
                "dependencies_satisfied": True,
                "fixture_dependency_reader": True}

    def worker_config(self):
        return {"ready_timeout_seconds": 5}

    def wait_for_status(self, run_root):
        status = run_root / "launcher.status.json"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if status.is_file():
                return json.loads(status.read_text())
            time.sleep(.05)
        self.fail("launcher child did not publish a bounded status")

    def wait_for_exit(self, pid, identity):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if not matches(identity):
                    return
            except (OSError, ValueError, NotImplementedError):
                return
            time.sleep(.05)
        self.fail("launcher child did not exit")

    def test_no_authorization_does_not_spawn(self):
        with self.assertRaisesRegex(WorkerLauncherError, "execution_authorized"):
            start(self.checkouts, "NSC-042", "run-042", "lease-042", self.worker_config())
        self.assertFalse((self.checkouts.records / "worker-runs").exists())

    def _fixture_child(self, run_id="run-042", *, ready=True, stop=False, tamper_config=False,
                       job_handoff=False):
        run_root = self.checkouts.records / "worker-runs" / "NSC-042" / hashlib.sha256(run_id.encode()).hexdigest()
        run_root.mkdir(parents=True)
        config_path = run_root / "launch.config.json"
        marker = run_root / "fixture.marker"
        config_path.write_bytes(json.dumps({"_test_fixture": {"marker": str(marker)}}).encode())
        request_path = run_root / "launch.request.json"
        ready_path = run_root / "ready.receipt.json"
        request = {
            "schema_version": "assistant-worker-launch/v1", "task_id": "NSC-042",
            "run_id": run_id, "lease_id": "lease-042", "source": str(self.source.resolve()),
            "checkout_root": str(self.checkouts.root.resolve()),
            "checkout": str((self.checkouts.root / "NSC-042").resolve()),
            "reservation_plan_id": self.reservation["plan_id"], "parent_identity": {},
            "config": str(config_path), "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "ready": str(ready_path), "stop_request": str(run_root / "stop.request"),
            "ready_timeout_seconds": .5, "test_fixture": {"marker": str(marker)},
        }
        if job_handoff:
            request["job_name"] = "assistant-job-" + hashlib.sha256(str(run_root).encode()).hexdigest()
        if tamper_config:
            request["config_sha256"] = "0" * 64
        write_record(request_path, request)
        if stop:
            write_record(run_root / "stop.request", {"task_id": "NSC-042", "run_id": run_id,
                                                       "lease_id": "lease-042"})
        proc = subprocess.Popen([
            sys.executable, "-m", "Pipeline.AssistantControl.worker_launcher", "--child",
            "--request", str(request_path), "--source", str(self.source),
            "--checkout-root", str(self.checkouts.root), "--task", "NSC-042",
            "--run", run_id, "--lease", "lease-042", "--fixture",
        ], cwd=str(Path(__file__).resolve().parents[2]), stdout=subprocess.DEVNULL,
           stderr=subprocess.DEVNULL, shell=False)
        if ready:
            child_identity = identify(proc.pid)
            ready_receipt = {
                "schema_version": "assistant-worker-ready/v1", "task_id": "NSC-042",
                "run_id": run_id, "lease_id": "lease-042", "request": str(request_path),
                "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
                "parent_identity": {}, "child_identity": child_identity, "pid": proc.pid,
            }
            if job_handoff:
                with create_and_assign(request["job_name"], child_identity):
                    write_record(ready_path, ready_receipt)
                    deadline = time.monotonic() + 5
                    while not (run_root / "job.opened.json").is_file() and time.monotonic() < deadline:
                        time.sleep(.02)
                    self.assertTrue((run_root / "job.opened.json").is_file())
            else:
                write_record(ready_path, ready_receipt)
        return proc, run_root, marker

    def test_real_fixture_subprocess_waits_for_ready_and_completes(self):
        proc, run_root, marker = self._fixture_child()
        self.assertEqual(0, proc.wait(timeout=10))
        self.assertEqual("fixture_completed", self.wait_for_status(run_root)["status"])
        self.assertEqual("fixture_started", json.loads(marker.read_text())["status"])
        child = json.loads((run_root / "child.identity.json").read_text())
        self.assertEqual("NSC-042", child["task_id"])
        self.assertEqual("run-042", child["run_id"])
        self.assertEqual("lease-042", child["lease_id"])
        self.assertEqual(hashlib.sha256((run_root / "launch.request.json").read_bytes()).hexdigest(),
                         child["request_sha256"])
        self.assertEqual(child["pid"], child["process_identity"]["pid"])

    def test_real_fixture_child_opens_job_before_creator_closes(self):
        proc, run_root, marker = self._fixture_child(run_id="run-042", job_handoff=True)
        code = proc.wait(timeout=10)
        detail = (run_root / "launcher.status.json").read_text() if (run_root / "launcher.status.json").exists() else "no status"
        self.assertEqual(0, code, detail)
        self.assertEqual("fixture_started", json.loads(marker.read_text())["status"])
        self.assertTrue((run_root / "job.opened.json").is_file())

    def test_tampered_config_bytes_are_rejected_before_fixture(self):
        proc, run_root, marker = self._fixture_child(tamper_config=True)
        self.assertEqual(1, proc.wait(timeout=10))
        self.assertEqual("child_failed", self.wait_for_status(run_root)["status"])
        self.assertFalse(marker.exists())

    def test_stop_before_ready_exits_without_fixture(self):
        proc, run_root, marker = self._fixture_child(ready=False, stop=True)
        self.assertEqual(0, proc.wait(timeout=10))
        self.assertEqual("stopped_before_worker", self.wait_for_status(run_root)["status"])
        self.assertFalse(marker.exists())

    def test_duplicate_launch_for_same_run_is_refused(self):
        first = start(self.checkouts, "NSC-042", "run-042", "lease-042",
                      self.worker_config(), execution_authorized=True)
        with self.assertRaisesRegex(WorkerLauncherError, "duplicate"):
            start(self.checkouts, "NSC-042", "run-042", "lease-042",
                 self.worker_config(), execution_authorized=True)
        self.assertEqual("child_failed", self.wait_for_status(Path(first["run_root"]))["status"])
        self.wait_for_exit(first["pid"], first["process_identity"])

    def test_child_without_parent_ready_receipt_times_out_without_fixture(self):
        run_root = self.checkouts.records / "worker-runs" / "NSC-042" / hashlib.sha256(b"run-gated").hexdigest()
        run_root.mkdir(parents=True)
        marker = self.root / "must-not-start.marker"
        request_path = run_root / "launch.request.json"
        config_path = run_root / "launch.config.json"
        config_path.write_text(json.dumps({"_test_fixture": {"marker": str(marker)}}))
        request_path.write_text(json.dumps({
            "schema_version": "assistant-worker-launch/v1", "task_id": "NSC-042",
            "run_id": "run-gated", "lease_id": "lease-042",
            "source": str(self.source.resolve()), "checkout_root": str(self.checkouts.root.resolve()),
            "checkout": str((self.checkouts.root / "NSC-042").resolve()),
            "reservation_plan_id": self.reservation["plan_id"],
            "parent_identity": {}, "config": str(config_path),
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "ready": str(run_root / "ready.receipt.json"),
            "stop_request": str(run_root / "stop.request"), "ready_timeout_seconds": .25,
            "test_fixture": {"marker": str(marker)},
        }))
        proc = subprocess.Popen([
            sys.executable, "-m", "Pipeline.AssistantControl.worker_launcher", "--child",
            "--request", str(request_path), "--source", str(self.source),
            "--checkout-root", str(self.checkouts.root), "--task", "NSC-042",
            "--run", "run-gated", "--lease", "lease-042", "--fixture",
        ], cwd=str(Path(__file__).resolve().parents[2]), stdout=subprocess.DEVNULL,
           stderr=subprocess.DEVNULL, shell=False)
        self.assertEqual(2, proc.wait(timeout=10))
        self.assertEqual("ready_timeout", json.loads((run_root / "launcher.status.json").read_text())["status"])
        self.assertFalse(marker.exists())

    def _prepare_retry(self, *, old_status="failed", released=True):
        release(self.checkouts, "NSC-042", "run-042", "lease-042")
        record_path = self.checkouts.records / "NSC-042.json"
        record = json.loads(record_path.read_text())
        record["worker"] = {
            "status": old_status, "task_id": "NSC-042", "run_id": "run-042",
            "lease_id": "lease-042", "capacity_released": released,
        }
        record["launch"] = {
            "status": old_status, "task_id": "NSC-042", "run_id": "run-042",
            "lease_id": "lease-042", "stop_request_path": str(
                self.checkouts.records / "worker-runs" / "NSC-042" / "old" / "stop.request"),
        }
        write_record(record_path, record)
        return reserve(self.checkouts, "NSC-042", "run-043", dependency_reader=self.dependencies)

    def test_settled_failed_old_attempt_is_archived_before_new_launch(self):
        self._prepare_retry()
        result = start(self.checkouts, "NSC-042", "run-043", "lease-042",
                       self.worker_config(), execution_authorized=True)
        self.addCleanup(lambda: self.wait_for_exit(result["pid"], result["process_identity"]))
        record = json.loads((self.checkouts.records / "NSC-042.json").read_text())
        self.assertNotIn("worker", record)
        self.assertEqual("ready_pending", record["launch"]["status"])
        self.assertEqual("run-042", record["worker_history"][0]["run_id"])
        self.assertEqual("failed", record["worker_history"][0]["worker"]["status"])
        self.assertEqual("failed", record["worker_history"][0]["launch"]["status"])

    def test_unreleased_old_attempt_refuses_replacement(self):
        self._prepare_retry(released=False)
        with self.assertRaisesRegex(WorkerLauncherError, "released capacity"):
            start(self.checkouts, "NSC-042", "run-043", "lease-042",
                 self.worker_config(), execution_authorized=True)

    def test_definite_spawn_failure_records_exact_no_child_state(self):
        release(self.checkouts, "NSC-042", "run-042", "lease-042")
        reservation = reserve(self.checkouts, "NSC-042", "run-043",
                              dependency_reader=self.dependencies)
        real_popen = subprocess.Popen
        def fail_worker_spawn(*args, **kwargs):
            command = args[0] if args else kwargs.get("args", [])
            if isinstance(command, list) and "Pipeline.AssistantControl.worker_launcher" in command:
                raise OSError("fixture spawn failure")
            return real_popen(*args, **kwargs)
        with mock.patch("Pipeline.AssistantControl.worker_launcher.subprocess.Popen",
                        side_effect=fail_worker_spawn):
            with self.assertRaisesRegex(WorkerLauncherError, "could not be spawned"):
                start(self.checkouts, "NSC-042", "run-043", reservation["lease_id"],
                     self.worker_config(), execution_authorized=True)
        record = json.loads((self.checkouts.records / "NSC-042.json").read_text())
        self.assertEqual("spawn_failed", record["launch"]["status"])
        self.assertTrue(record["launch"]["no_child_created"])
        self.assertNotIn("pid", record["launch"])

    def test_settled_no_child_spawn_failure_can_be_retried(self):
        release(self.checkouts, "NSC-042", "run-042", "lease-042")
        record_path = self.checkouts.records / "NSC-042.json"
        record = json.loads(record_path.read_text())
        record["launch"] = {
            "status": "spawn_failed", "task_id": "NSC-042", "run_id": "run-042",
            "lease_id": "lease-042", "no_child_created": True,
            "capacity_released": True,
        }
        write_record(record_path, record)
        reservation = reserve(self.checkouts, "NSC-042", "run-043",
                              dependency_reader=self.dependencies)
        result = start(self.checkouts, "NSC-042", "run-043", reservation["lease_id"],
                       self.worker_config(), execution_authorized=True)
        self.addCleanup(lambda: self.wait_for_exit(result["pid"], result["process_identity"]))
        current = json.loads(record_path.read_text())
        self.assertEqual("run-043", current["launch"]["run_id"])
        self.assertEqual("run-042", current["worker_history"][0]["run_id"])

    def test_post_spawn_identity_failure_is_never_marked_no_child(self):
        real_identity = identify(os.getpid())
        with mock.patch("Pipeline.AssistantControl.worker_launcher._identity",
                        side_effect=[real_identity, WorkerLauncherError("identity unavailable")]):
            with self.assertRaisesRegex(WorkerLauncherError, "identity unavailable"):
                start(self.checkouts, "NSC-042", "run-042", "lease-042",
                     self.worker_config(), execution_authorized=True)
        record = json.loads((self.checkouts.records / "NSC-042.json").read_text())
        self.assertEqual("spawn_failed", record["launch"]["status"])
        self.assertFalse(record["launch"]["no_child_created"])
        self.assertTrue(record["launch"]["child_exit_confirmed"])
        self.assertNotIn("pid", record["launch"])


if __name__ == "__main__":
    unittest.main()
