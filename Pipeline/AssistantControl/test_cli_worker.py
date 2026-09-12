import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl import __main__ as cli


class CliWorkerTests(unittest.TestCase):
    def setUp(self):
        self.task = "NSC-042"
        self.run_id = "run-1"
        self.lease_id = "lease-1"
        self.identity = {"pid": 42, "created_ticks": 123, "image": "python.exe"}
        self.started = {
            "started": True,
            "task_id": self.task,
            "run_id": self.run_id,
            "lease_id": self.lease_id,
            "pid": 42,
            "process_identity": self.identity,
        }

    def _invoke(self, command="run-worker", sleep_side_effect=None,
                statuses=None, request_stop=None, started=None):
        statuses = statuses or []
        request_stop = request_stop or unittest.mock.Mock()
        manager = object()
        config = {"provider": "fake", "execution_model": "test-model"}
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "worker.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            argv = ["--source", temp, "--checkout-root", temp, command,
                    self.task, "--run-id", self.run_id, "--lease-id", self.lease_id,
                    "--config", str(config_path), "--authorize-provider-spend"]
            output = io.StringIO()
            with patch.object(cli, "Checkouts", return_value=manager), \
                 patch("Pipeline.AssistantControl.worker_launcher.start",
                       return_value=started or self.started) as start, \
                 patch("Pipeline.AssistantControl.worker_control.status",
                       side_effect=statuses) as status, \
                 patch("Pipeline.AssistantControl.worker_control.request_stop",
                       side_effect=request_stop) as stop, \
                 patch.object(cli.time, "sleep", side_effect=sleep_side_effect or (lambda _: None)):
                with contextlib.redirect_stdout(output):
                    code = cli.main(argv)
        return code, json.loads(output.getvalue()), start, status, stop

    def test_foreground_uses_detached_launcher_and_waits_for_exact_child(self):
        worker = {"task_id": self.task, "run_id": self.run_id,
                  "process_identity": self.identity, "status": "succeeded"}
        code, result, start, status, stop = self._invoke(
            statuses=[{"worker": {**worker, "status": "running"},
                       "host_identity_alive": True},
                      {"worker": worker, "host_identity_alive": False}])

        self.assertEqual(code, 0)
        self.assertEqual(result["worker_status"]["worker"], worker)
        start.assert_called_once_with(
            unittest.mock.ANY, self.task, self.run_id, self.lease_id,
            {"provider": "fake", "execution_model": "test-model",
             "execution_authorized": True}, execution_authorized=True)
        self.assertEqual(status.call_count, 2)
        stop.assert_not_called()

    def test_ctrl_c_requests_stop_for_exact_run_and_waits(self):
        worker = {"task_id": self.task, "run_id": self.run_id,
                  "process_identity": self.identity, "status": "stopped"}
        stop = unittest.mock.Mock()
        code, result, _, _, stop_mock = self._invoke(
            sleep_side_effect=[KeyboardInterrupt(), None],
            statuses=[{"worker": {**worker, "status": "running"},
                       "host_identity_alive": True},
                      {"worker": worker, "host_identity_alive": False}],
            request_stop=stop)

        self.assertEqual(code, 1)
        self.assertEqual(result["worker_status"]["worker"]["status"], "stopped")
        stop.assert_called_once_with(unittest.mock.ANY, self.task, run_id=self.run_id)
        stop_mock.assert_called_once_with(unittest.mock.ANY, self.task, run_id=self.run_id)

    def test_ctrl_c_during_status_requests_stop_for_exact_run(self):
        worker = {"task_id": self.task, "run_id": self.run_id,
                  "process_identity": self.identity, "status": "stopped"}
        stop = unittest.mock.Mock()
        code, result, _, status, stop_mock = self._invoke(
            statuses=[KeyboardInterrupt(),
                      {"worker": worker, "host_identity_alive": False}],
            request_stop=stop)

        self.assertEqual(code, 1)
        self.assertEqual(result["worker_status"]["worker"]["status"], "stopped")
        status.assert_called_with(unittest.mock.ANY, self.task)
        self.assertEqual(status.call_count, 2)
        stop.assert_called_once_with(unittest.mock.ANY, self.task, run_id=self.run_id)
        stop_mock.assert_called_once_with(unittest.mock.ANY, self.task, run_id=self.run_id)

    def test_foreground_rejects_changed_identity(self):
        foreign = {"task_id": self.task, "run_id": self.run_id,
                   "process_identity": {"pid": 99}, "status": "succeeded"}
        code, result, _, status, stop = self._invoke(
            statuses=[{"worker": foreign, "host_identity_alive": False}])

        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "command_failed")
        self.assertIn("identity changed", result["error"])
        status.assert_called_once()
        stop.assert_not_called()

    def test_start_worker_alias_remains_detached(self):
        code, result, start, status, stop = self._invoke(command="start-worker")

        self.assertEqual(code, 0)
        self.assertTrue(result["started"])
        start.assert_called_once()
        status.assert_not_called()
        stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
