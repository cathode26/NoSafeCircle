"""start-worker replaces a run the record proves is over, and still refuses a live one."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AssistantControl import worker_launcher  # noqa: E402
from Pipeline.AssistantControl.worker_state import finished_run_ids, is_finished_launch  # noqa: E402


SETTLED = {"run_id": "old-run", "status": "stopped", "capacity_released": True,
           "settled_at": "2026-09-17T01:00:00+00:00"}
STALE_LAUNCH = {"run_id": "old-run", "status": "ready_pending"}


def guard(record, run_id="new-run"):
    """Call the replacement check the way start-worker does."""
    return worker_launcher._archive_previous_attempt(record, task_id="NSC-046", run_id=run_id)


class FinishedLaunchReplacementTests(unittest.TestCase):
    def test_a_retired_runs_stale_launch_does_not_block_a_new_run(self):
        # The exact shape after retire-worker: no worker, a stale launch, the run in history.
        record = {"worker_history": [dict(SETTLED)], "launch": dict(STALE_LAUNCH)}
        guard(record)
        self.assertEqual(len(record["worker_history"]), 2, "the launch is archived, not dropped")

    def test_a_launcher_shaped_history_entry_also_counts_as_proof(self):
        # worker_launcher archives with the run's fields nested under "worker".
        record = {"worker_history": [{"run_id": "old-run", "worker": dict(SETTLED), "launch": None}],
                  "launch": dict(STALE_LAUNCH)}
        guard(record)

    def test_a_launch_whose_run_is_not_proven_finished_still_refuses(self):
        record = {"launch": dict(STALE_LAUNCH)}
        with self.assertRaises(worker_launcher.WorkerLauncherError) as caught:
            guard(record)
        self.assertIn("replacement refused", str(caught.exception))

    def test_a_launch_for_a_different_run_than_the_finished_one_still_refuses(self):
        record = {"worker_history": [dict(SETTLED)],
                  "launch": {"run_id": "another-run", "status": "ready_pending"}}
        with self.assertRaises(worker_launcher.WorkerLauncherError):
            guard(record)

    def test_a_live_worker_still_refuses(self):
        record = {"worker": {"run_id": "old-run", "status": "running"},
                  "worker_history": [dict(SETTLED)]}
        with self.assertRaises(worker_launcher.WorkerLauncherError) as caught:
            guard(record)
        self.assertIn("replacement refused", str(caught.exception))

    def test_a_terminal_worker_without_released_capacity_still_refuses(self):
        record = {"worker": {"run_id": "old-run", "status": "stopped"}}
        with self.assertRaises(worker_launcher.WorkerLauncherError) as caught:
            guard(record)
        self.assertIn("released capacity", str(caught.exception))

    def test_the_same_run_id_still_refuses(self):
        record = {"worker_history": [dict(SETTLED)], "launch": dict(STALE_LAUNCH)}
        with self.assertRaises(worker_launcher.WorkerLauncherError) as caught:
            guard(record, run_id="old-run")
        self.assertIn("same-run", str(caught.exception))

    def test_the_proof_reads_both_archive_shapes(self):
        flat = {"worker_history": [dict(SETTLED)]}
        nested = {"worker_history": [{"run_id": "old-run", "worker": dict(SETTLED)}]}
        self.assertEqual(finished_run_ids(flat), {"old-run"})
        self.assertEqual(finished_run_ids(nested), {"old-run"})
        self.assertTrue(is_finished_launch(flat, dict(STALE_LAUNCH)))
        self.assertTrue(is_finished_launch(nested, dict(STALE_LAUNCH)))


if __name__ == "__main__":
    unittest.main()
