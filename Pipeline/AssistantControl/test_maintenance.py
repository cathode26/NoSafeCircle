import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl.maintenance import MaintenanceExecutor, MaintenanceTicket, _ticket_sha


class FakeCheckouts:
    def __init__(self, root):
        self.source = root / "source"
        self.root = root / "checkouts"
        self.records = self.root / ".assistant-control"
        (self.source / ".git").mkdir(parents=True)
        (self.root / "NSC-042").mkdir(parents=True)
        self.record = {"task_id": "NSC-042", "checkout": str(self.root / "NSC-042"),
                       "source_commit": "s" * 40, "task_contract_sha256": "c" * 64}
        self.worker = {"task_id": "NSC-042", "run_id": "run-1", "lease_id": "lease-1",
                       "plan_id": "plan-1", "source_head": "s" * 40,
                       "task_contract_sha256": "c" * 64, "process_identity": {"pid": 1},
                       "stop_request_path": "stop", "job_name": None, "status": "succeeded",
                       "capacity_released": True}

    def observe(self, task):
        return self.record


def ticket_body(fake, action="inspect-worker"):
    body = {"schema_version": "assistant-maintenance-ticket/v1", "action": action,
            "task_id": "NSC-042", "source": str(fake.source), "source_head": "h" * 40,
            "checkout_root": str(fake.root), "checkout": str(fake.root / "NSC-042"),
            "branch": "assistant/NSC-042", "checkout_commit": "k" * 40,
            "task_contract_sha256": "c" * 64, "assistant_run_id": "run-1",
            "worker": fake.worker, "issued_at_utc": "2026-01-01T00:00:00+00:00"}
    body["semantic_sha256"] = _ticket_sha(body)
    return body


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fake = FakeCheckouts(Path(self.temp.name))
        self.executor = MaintenanceExecutor(self.fake)
        self.executor.tickets.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def write_ticket(self, body=None):
        body = body or ticket_body(self.fake)
        path = self.executor.tickets / "ticket.json"
        path.write_text(json.dumps(body), encoding="utf-8")
        return path

    def run_patches(self, action):
        path = self.write_ticket(ticket_body(self.fake, action))
        def git_probe(_path, *args):
            if args == ("branch", "--show-current"):
                return b"assistant/NSC-042\n"
            if args == ("rev-parse", "HEAD"):
                return (b"h" * 40 if _path == self.fake.source else b"k" * 40) + b"\n"
            return b"h" * 40 + b"\n"
        with patch("Pipeline.AssistantControl.maintenance.git", side_effect=git_probe), \
             patch("Pipeline.AssistantControl.maintenance._worker", return_value=self.fake.worker), \
             patch.object(self.executor, "_dispatch", return_value={"ok": True}) as dispatch:
            first = self.executor.run(path)
            second = self.executor.run(path)
        dispatch.assert_called_once()
        self.assertEqual(first, second)

    def test_each_action_dispatches_through_the_executor(self):
        for action in ("inspect-worker", "verify-candidate", "settle-worker", "cleanup-worker-docker"):
            with self.subTest(action=action):
                self.run_patches(action)

    def test_tampered_ticket_and_path_escape_are_rejected(self):
        path = self.write_ticket()
        body = json.loads(path.read_text())
        body["action"] = "run-command"
        path.write_text(json.dumps(body))
        with self.assertRaisesRegex(ValueError, "authentication"):
            self.executor.run(path)
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text(json.dumps(ticket_body(self.fake)))
        with self.assertRaisesRegex(ValueError, "inside"):
            self.executor.run(outside)

    def test_stale_source_and_foreign_worker_are_rejected(self):
        path = self.write_ticket()
        def stale_git(_path, *args):
            return b"x" * 40 + b"\n" if args == ("rev-parse", "HEAD") else b"assistant/NSC-042\n"
        with patch("Pipeline.AssistantControl.maintenance.git", side_effect=stale_git), \
             patch("Pipeline.AssistantControl.maintenance._worker", return_value=self.fake.worker):
            with self.assertRaisesRegex(ValueError, "Source changed"):
                self.executor.run(path)
        self.write_ticket(ticket_body(self.fake))
        self.fake.worker = {**self.fake.worker, "lease_id": "foreign"}
        def git_probe(_path, *args):
            if args == ("branch", "--show-current"):
                return b"assistant/NSC-042\n"
            if args == ("rev-parse", "HEAD"):
                return (b"h" * 40 if _path == self.fake.source else b"k" * 40) + b"\n"
            return b"h" * 40 + b"\n"
        with patch("Pipeline.AssistantControl.maintenance.git", side_effect=git_probe), \
             patch("Pipeline.AssistantControl.maintenance._worker", return_value=self.fake.worker):
            with self.assertRaisesRegex(ValueError, "identity"):
                self.executor.run(path)

    def test_cleanup_requires_terminal_released_dead_and_empty_job(self):
        executor = self.executor
        ticket = MaintenanceTicket(ticket_body(self.fake, "cleanup-worker-docker"))
        for changes, message in (({"status": "starting"}, "terminal"),
                                 ({"capacity_released": False}, "released"),
                                 ({"process_identity": None}, "dead"),
                                 ({"job_name": "job"}, "empty")):
            worker = {**self.fake.worker, **changes}
            with patch("Pipeline.AssistantControl.maintenance.matches", return_value=False), \
                 patch("Pipeline.AssistantControl.maintenance.active_count", return_value=1):
                with self.assertRaisesRegex(ValueError, message):
                    executor._dispatch(ticket, self.fake.record, worker)

    def test_no_arbitrary_command_field_is_accepted(self):
        body = ticket_body(self.fake)
        body["command"] = "docker system prune --volumes"
        body["semantic_sha256"] = _ticket_sha(body)
        path = self.write_ticket(body)
        with self.assertRaisesRegex(ValueError, "authentication"):
            self.executor.run(path)

    def test_plan_rejects_incomplete_identity(self):
        self.fake.worker = {**self.fake.worker, "lease_id": None}
        with patch("Pipeline.AssistantControl.maintenance._worker", return_value=self.fake.worker):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                self.executor.plan("NSC-042", "inspect-worker", run_id="run-1")

    def test_plan_rejects_worker_bound_to_another_source(self):
        self.fake.worker = {**self.fake.worker, "source_head": "x" * 40}
        with patch("Pipeline.AssistantControl.maintenance._worker", return_value=self.fake.worker):
            with self.assertRaisesRegex(ValueError, "differs from the owned task"):
                self.executor.plan("NSC-042", "inspect-worker", run_id="run-1")

    def test_run_rejects_foreign_record_checkout(self):
        path = self.write_ticket()
        self.fake.record["checkout"] = str(self.fake.root / "other")
        with self.assertRaisesRegex(ValueError, "Observed checkout"):
            self.executor.run(path)

    def test_tampered_replayed_receipt_is_rejected(self):
        path = self.write_ticket()
        def git_probe(_path, *args):
            if args == ("branch", "--show-current"):
                return b"assistant/NSC-042\n"
            if args == ("rev-parse", "HEAD"):
                return (b"h" * 40 if _path == self.fake.source else b"k" * 40) + b"\n"
            return b"h" * 40 + b"\n"
        with patch("Pipeline.AssistantControl.maintenance.git", side_effect=git_probe), \
             patch("Pipeline.AssistantControl.maintenance._worker", return_value=self.fake.worker), \
             patch.object(self.executor, "_dispatch", return_value={"ok": True}):
            first = self.executor.run(path)
        receipt = self.executor.receipts / (ticket_body(self.fake)["semantic_sha256"] + ".json")
        self.assertTrue(receipt.exists())
        data = json.loads(receipt.read_text())
        data["result"] = {"ok": False}
        receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "authentication"):
            self.executor.run(path)


if __name__ == "__main__":
    unittest.main()
