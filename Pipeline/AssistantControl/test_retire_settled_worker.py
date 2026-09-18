"""Retiring a settled worker returns its task to a dispatchable state."""
from __future__ import annotations

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AssistantControl import worker_control  # noqa: E402
from Pipeline.AssistantControl.scope import AssistantScopePlanner  # noqa: E402


DEAD_IDENTITY = {"pid": 4242, "started_at": "2026-09-17T00:00:00+00:00", "executable": "python.exe"}


def settled_worker(**overrides):
    worker = {
        "run_id": "nsc-007-run",
        "status": "failed",
        "capacity_released": True,
        "settled_at": "2026-09-17T01:00:00+00:00",
        "process_identity": dict(DEAD_IDENTITY),
    }
    worker.update(overrides)
    return worker


class RetireSettledWorkerTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory(prefix="nsc-retire-")
        root = Path(self._temporary.name)
        self.records = root / "records"
        self.records.mkdir(parents=True)
        self.checkouts = types.SimpleNamespace(records=self.records, root=root / "checkouts",
                                               source=root / "source")
        self.path = self.records / "NSC-007.json"

    def tearDown(self):
        self._temporary.cleanup()

    def write(self, record):
        self.path.write_text(json.dumps(record), encoding="utf-8")

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def retire(self, run_id="nsc-007-run"):
        # The host identity is dead and the worker job is empty: the run really is over.
        with patch.object(worker_control, "matches", return_value=False), \
             patch.object(worker_control, "active_count", return_value=0):
            return worker_control.retire_settled_worker(self.checkouts, "NSC-007", run_id=run_id)

    def test_a_settled_failed_worker_is_archived_and_the_task_becomes_dispatchable(self):
        self.write({"task_id": "NSC-007", "status": "prepared", "worker": settled_worker()})
        result = self.retire()
        record = self.read()
        self.assertNotIn("worker", record, "the dispatch gates test presence, so it must be gone")
        self.assertEqual(record["status"], "prepared")
        self.assertEqual(record["worker_history"][0]["run_id"], "nsc-007-run")
        self.assertTrue(record["worker_history"][0]["retired_at"], "the archive says when")
        self.assertTrue(result["retired"])
        # The gate that blocked re-dispatch now passes on this record.
        self.assertFalse(AssistantScopePlanner._worker_underway(record))

    def test_a_stopped_worker_is_retired_too(self):
        # Vincent cancelling a run must not take the task out of circulation.
        self.write({"task_id": "NSC-007", "status": "prepared", "worker": settled_worker(status="stopped")})
        self.retire()
        self.assertNotIn("worker", self.read())

    def test_an_unsettled_worker_is_refused(self):
        self.write({"task_id": "NSC-007", "status": "prepared",
                    "worker": settled_worker(capacity_released=False)})
        with self.assertRaises(ValueError) as caught:
            self.retire()
        self.assertIn("settle-worker", str(caught.exception))
        self.assertIn("worker", self.read())

    def test_a_live_host_identity_is_refused(self):
        self.write({"task_id": "NSC-007", "status": "prepared", "worker": settled_worker()})
        with patch.object(worker_control, "matches", return_value=True), \
             patch.object(worker_control, "active_count", return_value=0):
            with self.assertRaises(ValueError) as caught:
                worker_control.retire_settled_worker(self.checkouts, "NSC-007", run_id="nsc-007-run")
        self.assertIn("dead host identity", str(caught.exception))
        self.assertIn("worker", self.read())

    def test_a_live_worker_job_is_refused(self):
        self.write({"task_id": "NSC-007", "status": "prepared",
                    "worker": settled_worker(job_name="nsc-007-job")})
        with patch.object(worker_control, "matches", return_value=False), \
             patch.object(worker_control, "active_count", return_value=2):
            with self.assertRaises(ValueError) as caught:
                worker_control.retire_settled_worker(self.checkouts, "NSC-007", run_id="nsc-007-run")
        self.assertIn("live processes", str(caught.exception))

    def test_a_succeeded_worker_is_refused(self):
        # Its output belongs to the review path; re-dispatch would discard real work.
        self.write({"task_id": "NSC-007", "status": "prepared",
                    "worker": settled_worker(status="succeeded")})
        with self.assertRaises(ValueError) as caught:
            self.retire()
        self.assertIn("succeeded", str(caught.exception))

    def test_a_record_with_a_candidate_is_refused(self):
        self.write({"task_id": "NSC-007", "status": "prepared", "worker": settled_worker(),
                    "candidate": {"commit": "abc123"}})
        with self.assertRaises(ValueError) as caught:
            self.retire()
        self.assertIn("candidate", str(caught.exception))
        self.assertIn("worker", self.read())

    def test_a_mismatched_run_id_is_refused(self):
        self.write({"task_id": "NSC-007", "status": "prepared", "worker": settled_worker()})
        with self.assertRaises(ValueError) as caught:
            self.retire(run_id="some-other-run")
        self.assertIn("run id", str(caught.exception))

    def test_a_non_prepared_record_is_refused(self):
        self.write({"task_id": "NSC-007", "status": "integrated", "worker": settled_worker()})
        with self.assertRaises(ValueError) as caught:
            self.retire()
        self.assertIn("prepared", str(caught.exception))

    def test_retiring_the_same_run_twice_is_refused(self):
        self.write({"task_id": "NSC-007", "status": "prepared", "worker": settled_worker()})
        self.retire()
        record = self.read()
        record["worker"] = settled_worker()
        self.write(record)
        with self.assertRaises(ValueError) as caught:
            self.retire()
        self.assertIn("already in worker_history", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
