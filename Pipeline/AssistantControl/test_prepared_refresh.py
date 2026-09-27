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

    def _advance(self) -> str:
        """A REPEATABLE Source advance.

        `advance_source` writes the same bytes to the same path every call, so a
        second call has nothing to commit and git exits 1 -- which reads as a
        defect in the code under test and is not one. Distinct file per call.
        """

        self._advanced = getattr(self, "_advanced", 0) + 1
        name = "source-step-%d.txt" % self._advanced
        (self.base.root / name).write_text("step %d\n" % self._advanced, encoding="utf-8")
        self.base.run_git("add", name)
        self.base.run_git("commit", "-q", "-m", "source step %d" % self._advanced)
        return self.base.run_git("rev-parse", "HEAD").decode().strip()

    def _commit_in_checkout(self, checkout: Path, name: str) -> str:
        (checkout / name).write_text("worker\n", encoding="utf-8")
        prepared_refresh.git(checkout, "add", name)
        prepared_refresh.git(checkout, "-c", "user.name=Worker",
                             "-c", "user.email=worker@nosafecircle.invalid",
                             "commit", "-q", "-m", "worker work")
        return prepared_refresh._head(checkout)

    def test_a_checkout_carrying_work_source_already_has_still_refreshes(self):
        """NSC-128's exact shape: the checkout is AHEAD of the recorded baseline.

        `refresh_prepared` compared the post-fetch checkout HEAD against
        `record["source_commit"]`, so a prepared checkout whose worker commit had
        already landed on Source could never be refreshed -- and every attempt
        left a journal behind, which then refused earlier and differently. The
        property that matters is that the advance is a fast-forward, and
        `merge --ff-only` is what enforces it; comparing against a value from the
        RECORD instead of the HEAD actually observed is the defect.
        """

        checkout = self.manager.root / "NSC-042"
        landed = self._advance()
        prepared_refresh.git(checkout, "fetch", "--no-tags", str(self.base.root), landed)
        prepared_refresh.git(checkout, "merge", "--ff-only", "FETCH_HEAD")
        self.assertEqual(landed, prepared_refresh._head(checkout))
        baseline = json.loads(self.record_path.read_text())["source_commit"]
        self.assertNotEqual(landed, baseline, "the fixture did not reproduce the drift")

        moved = self._advance()
        result = refresh_prepared(self.manager, "NSC-042", moved)

        self.assertEqual(moved, result["source_commit"])
        self.assertEqual(moved, prepared_refresh._head(checkout))
        self.assertFalse((self.manager.records / "NSC-042.prepared-refresh.json").exists())

    def test_a_checkout_carrying_work_source_does_not_have_is_still_refused(self):
        """The control. Unmerged local work must not be fast-forwarded away.

        This must refuse before and after the fix, and the commit must survive --
        otherwise the repair above would be a way to lose a worker's output.
        """

        checkout = self.manager.root / "NSC-042"
        unmerged = self._commit_in_checkout(checkout, "unmerged.txt")
        moved = self._advance()

        with self.assertRaises(PreparedRefreshError):
            refresh_prepared(self.manager, "NSC-042", moved)

        self.assertEqual(unmerged, prepared_refresh._head(checkout))
        self.assertNotEqual(moved, prepared_refresh._head(checkout))

    def test_a_journal_written_before_the_fast_forward_is_discarded_and_retried(self):
        """A journal with no `phase` proves nothing was applied, so restart.

        `phase` is written ONLY after the fast-forward completes, so its absence is
        positive evidence that the checkout is exactly where it was. Gating the
        discard on the journal naming the CURRENT Source made that window close on
        the next merge -- minutes, on this floor. NSC-128 was retried three times
        and got three different messages and no route forward.
        """

        journal_path = self.manager.records / "NSC-042.prepared-refresh.json"
        record = json.loads(self.record_path.read_text())
        abandoned_target = self._advance()
        write_record(journal_path, {
            "schema_version": "assistant-prepared-refresh/v1", "task_id": "NSC-042",
            "old_commit": record["source_commit"], "source_commit": abandoned_target,
            "new_commit": abandoned_target,
            "task_contract_sha256": record["task_contract_sha256"],
            "created_at": "2026-09-27T11:46:08.314421+00:00", "operation": "a" * 32,
        })
        moved = self._advance()

        result = refresh_prepared(self.manager, "NSC-042", moved)

        self.assertEqual(moved, result["source_commit"])
        self.assertEqual(moved, prepared_refresh._head(self.manager.root / "NSC-042"))
        self.assertFalse(journal_path.exists())

    def test_a_post_ff_journal_that_cannot_be_proven_still_refuses(self):
        """The other control. A journal that DID fast-forward is not discardable.

        Once the checkout moved, the record may need finishing, and throwing the
        journal away would lose that. This must refuse before and after, and the
        journal must survive for inspection.
        """

        journal_path = self.manager.records / "NSC-042.prepared-refresh.json"
        record = json.loads(self.record_path.read_text())
        moved = self._advance()
        write_record(journal_path, {
            "schema_version": "assistant-prepared-refresh/v1", "task_id": "NSC-042",
            "old_commit": record["source_commit"], "source_commit": moved,
            "new_commit": moved, "task_contract_sha256": record["task_contract_sha256"],
            "created_at": "2026-09-27T11:46:08.314421+00:00", "operation": "b" * 32,
            "phase": "post_ff",
        })

        with self.assertRaisesRegex(PreparedRefreshError, "not safely recoverable"):
            refresh_prepared(self.manager, "NSC-042", moved)

        self.assertTrue(journal_path.exists())



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
