"""Focused real-Git tests for refreshing prepared, unadmitted checkouts."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.admission import _source_registry_paths
from Pipeline.AssistantControl.prepared_refresh import PreparedRefreshError, refresh_prepared
from Pipeline.AssistantControl import prepared_refresh
from Pipeline.AssistantControl import test_inspect_project as fixture


class PreparedRefreshTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture.InventoryTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        contract = json.loads(self.base.contract.read_text())
        contract["contract_disposition"] = "active"
        self.base.contract.write_text(json.dumps(contract), encoding="utf-8")
        self.base.run_git("add", "Tasks/NSC-042.yaml")
        self.base.run_git("commit", "-q", "-m", "activate")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = Checkouts(self.base.root, Path(self.temp.name) / "checkouts")
        self.record = self.manager.prepare("NSC-042")
        self.record_path = self.manager.records / "NSC-042.json"

    def advance_source(self):
        (self.base.root / "new-source.txt").write_text("source\n", encoding="utf-8")
        self.base.run_git("add", "new-source.txt")
        self.base.run_git("commit", "-q", "-m", "source update")
        return self.base.run_git("rev-parse", "HEAD").decode().strip()

    def test_refresh_ff_preserves_dirty_source_and_clears_scope(self):
        record = json.loads(self.record_path.read_text())
        record["scope"] = {"lease_id": "lease", "plan_id": "plan"}
        write_record(self.record_path, record)
        (self.base.root / "operator-edit.txt").write_text("keep", encoding="utf-8")
        expected = self.advance_source()
        result = refresh_prepared(self.manager, "NSC-042", expected)
        self.assertEqual(expected, result["source_commit"])
        self.assertNotIn("scope", result)
        self.assertEqual("prepared", result["status"])
        self.assertEqual("keep", (self.base.root / "operator-edit.txt").read_text())
        self.assertTrue((self.manager.root / "NSC-042" / "new-source.txt").is_file())
        self.assertEqual(1, len(result["preparation_history"]))
        self.assertEqual(result, refresh_prepared(self.manager, "NSC-042", expected))

    def test_dirty_task_worker_and_admission_are_refused(self):
        expected = self.advance_source()
        checkout = self.manager.root / "NSC-042"
        (checkout / "local.txt").write_text("do not touch")
        with self.assertRaisesRegex(PreparedRefreshError, "dirty"):
            refresh_prepared(self.manager, "NSC-042", expected)
        (checkout / "local.txt").unlink()
        record = json.loads(self.record_path.read_text())
        record["worker"] = {"status": "running"}
        write_record(self.record_path, record)
        with self.assertRaisesRegex(PreparedRefreshError, "worker"):
            refresh_prepared(self.manager, "NSC-042", expected)
        record.pop("worker")
        write_record(self.record_path, record)
        lock, registry_path = _source_registry_paths(self.base.root)
        write_record(registry_path, {"schema_version": "assistant-admission/v1",
                                     "source": str(self.manager.source),
                                     "reservations": [{"status": "active", "task_id": "NSC-042"}]})
        with self.assertRaisesRegex(PreparedRefreshError, "active admission"):
            refresh_prepared(self.manager, "NSC-042", expected)

    def test_write_failure_after_ff_recovers_exact_head(self):
        expected = self.advance_source()
        original = prepared_refresh.write_record
        failed = {"value": False}

        def fail_record(path, value):
            if path == self.record_path and value.get("source_commit") == expected and not failed["value"]:
                failed["value"] = True
                raise OSError("injected record write failure")
            return original(path, value)

        with patch.object(prepared_refresh, "write_record", side_effect=fail_record):
            with self.assertRaisesRegex(PreparedRefreshError, "retained journal"):
                refresh_prepared(self.manager, "NSC-042", expected)
        self.assertEqual(expected, prepared_refresh._head(self.manager.root / "NSC-042"))
        result = refresh_prepared(self.manager, "NSC-042", expected)
        self.assertEqual(expected, result["source_commit"])
        self.assertFalse((self.manager.records / "NSC-042.prepared-refresh.json").exists())


class RefreshAcceptsFinishedHistoryTests(unittest.TestCase):
    """A refresh refuses live work; finished history must not block it forever.

    `settle-worker` updates the worker entry and `retire-worker` archives it into
    `worker_history`, so a record always carries evidence of a finished run. Refusing on that
    evidence left NSC-046 and NSC-007 with no way to move their checkouts to current HEAD, which
    is what `reserve` requires.
    """

    @staticmethod
    def settled(**overrides):
        entry = {"run_id": "r1", "status": "stopped", "capacity_released": True,
                 "settled_at": "2026-09-17T01:00:00+00:00"}
        entry.update(overrides)
        return entry

    def base(self, **fields):
        record = {"task_id": "NSC-046", "status": "prepared"}
        record.update(fields)
        return record

    def test_a_retired_run_does_not_block_a_refresh(self):
        # The exact shape after retire-worker: history plus the launcher record it left.
        record = self.base(worker_history=[self.settled()],
                           launch={"run_id": "r1", "status": "ready_pending"})
        prepared_refresh._forbidden(record)

    def test_a_settled_worker_still_in_place_does_not_block(self):
        record = self.base(worker=self.settled(),
                           launch={"run_id": "r1", "status": "ready_pending"})
        prepared_refresh._forbidden(record)

    def test_a_live_worker_still_blocks(self):
        record = self.base(worker=self.settled(status="running", capacity_released=False))
        with self.assertRaises(prepared_refresh.PreparedRefreshError) as caught:
            prepared_refresh._forbidden(record)
        self.assertIn("worker", str(caught.exception))

    def test_a_succeeded_worker_still_blocks(self):
        # Its output belongs to the review path; refreshing over it would discard real work.
        record = self.base(worker=self.settled(status="succeeded"))
        with self.assertRaises(prepared_refresh.PreparedRefreshError):
            prepared_refresh._forbidden(record)

    def test_a_launch_for_an_unknown_run_still_blocks(self):
        # No worker and no history proves this run ended, so the launch is taken at face value.
        record = self.base(launch={"run_id": "mystery", "status": "ready_pending"})
        with self.assertRaises(prepared_refresh.PreparedRefreshError) as caught:
            prepared_refresh._forbidden(record)
        self.assertIn("launch", str(caught.exception))

    def test_a_launch_for_a_different_run_than_the_finished_one_still_blocks(self):
        record = self.base(worker_history=[self.settled(run_id="r1")],
                           launch={"run_id": "r2", "status": "ready_pending"})
        with self.assertRaises(prepared_refresh.PreparedRefreshError):
            prepared_refresh._forbidden(record)

    def test_real_output_still_blocks(self):
        for field, value in (("candidate", {"commit": "abc"}), ("integration", {"commit": "abc"}),
                             ("revision", {"id": 1}), ("human_review", {"state": "pending"})):
            with self.subTest(field=field):
                record = self.base(worker_history=[self.settled()], **{field: value})
                with self.assertRaises(prepared_refresh.PreparedRefreshError) as caught:
                    prepared_refresh._forbidden(record)
                self.assertIn(field, str(caught.exception))

    def test_a_non_prepared_record_still_blocks(self):
        record = self.base(worker_history=[self.settled()])
        record["status"] = "integrated"
        with self.assertRaises(prepared_refresh.PreparedRefreshError):
            prepared_refresh._forbidden(record)

if __name__ == "__main__":
    unittest.main(verbosity=2)
