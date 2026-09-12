"""The viewer's Stop button issues the same stop request as Stop-NscRun, once."""

from __future__ import annotations

import json
import time
import os
from datetime import datetime, timezone
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from Pipeline.TaskReviewAgent.GauntletView import server
from contextlib import contextmanager


@contextmanager
def patch_module_attr(module, name, value):
    previous = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, previous)


class LocalStopEndpointTests(unittest.TestCase):
    def make_run(self):
        base = Path(tempfile.mkdtemp(prefix="nsc-viewer-stop-"))
        self.addCleanup(shutil.rmtree, base, True)
        source = base / "Source"
        source.mkdir()
        run_root = base / "Checkouts" / ".task-review-agent" / "local-rehearsals" / "run-1"
        run_root.mkdir(parents=True)
        (run_root / "local-manifest.json").write_text(json.dumps({
            "run_id": "run-1", "source_repository": str(source)}), encoding="utf-8")
        return base, source, run_root

    def test_first_request_writes_the_file_and_second_is_refused(self):
        _base, _source, run_root = self.make_run()
        result = server.request_local_stop(run_root)
        self.assertEqual(result["status"], "stop_requested")
        self.assertFalse(result["wake_sent"], "no wake endpoint exists in this fixture")
        request = json.loads((run_root / "stop-request.json").read_text(encoding="utf-8"))
        self.assertEqual(request["reason"], "GauntletView stop button")
        with self.assertRaisesRegex(server.LocalStopError, "already requested"):
            server.request_local_stop(run_root)

    def test_missing_manifest_or_root_is_refused_without_writing(self):
        base, _source, run_root = self.make_run()
        (run_root / "local-manifest.json").unlink()
        with self.assertRaisesRegex(server.LocalStopError, "manifest"):
            server.request_local_stop(run_root)
        self.assertFalse((run_root / "stop-request.json").exists())
        with self.assertRaisesRegex(server.LocalStopError, "missing"):
            server.request_local_stop(base / "absent")

    def test_state_reports_stop_requested_for_local_runs(self):
        _base, _source, run_root = self.make_run()

        class FakeSnapshot:
            local_run_root = run_root

            def build(self):
                return {"run": {"mode": "local_rehearsal"}, "tasks": []}

        handler = server.Handler.__new__(server.Handler)
        handler.snapshot = FakeSnapshot()
        handler.approval = None
        self.assertFalse(handler._state()["run"]["stop_requested"])
        server.request_local_stop(run_root)
        self.assertTrue(handler._state()["run"]["stop_requested"])

    def test_stop_state_reports_the_drain_the_scheduler_journaled(self):
        _base, _source, run_root = self.make_run()
        self.assertFalse(server.local_stop_state(run_root)["requested"])
        server.request_local_stop(run_root)
        state = server.local_stop_state(run_root)
        self.assertTrue(state["requested"])
        self.assertFalse(state["acknowledged"], "no scheduler journal yet")
        requested_at = state["requested_at_utc"]
        lines = [
            json.dumps({"event": "scheduler_draining", "timestamp_utc": "2000-01-01T00:00:00+00:00",
                        "active_children": [{}], "fatal_drain_seconds": 1.0}),
            json.dumps({"event": "poll_started", "timestamp_utc": "2099-01-01T00:00:00+00:00"}),
            json.dumps({"event": "scheduler_draining", "timestamp_utc": "2099-01-01T00:00:01+00:00",
                        "active_children": [{}, {}, {}], "fatal_drain_seconds": 1800.0}),
        ]
        (run_root / "scheduler-events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        state = server.local_stop_state(run_root)
        self.assertTrue(state["acknowledged"])
        self.assertEqual(state["active_children"], 3)
        self.assertEqual(state["drain_limit_seconds"], 1800.0)
        self.assertGreater(state["draining_since_utc"], requested_at)

    def test_reset_and_force_stop_need_a_receipt_and_reset_needs_a_stop_receipt(self):
        _base, _source, run_root = self.make_run()
        previous = server.LAUNCH_RECEIPT_PATH
        try:
            server.LAUNCH_RECEIPT_PATH = None
            operator = server.local_operator_state(run_root)
            self.assertFalse(operator["force_stop_available"])
            self.assertFalse(operator["reset_available"])
            with self.assertRaisesRegex(server.LocalStopError, "launch receipt"):
                server.request_local_reset(run_root, viewer_pid=1)
            with self.assertRaisesRegex(server.LocalStopError, "launch receipt"):
                server.request_local_force_stop(run_root)
            receipt = run_root.parents[3] / "launch-receipt.json"
            receipt.write_text("{}", encoding="utf-8")
            server.LAUNCH_RECEIPT_PATH = receipt
            operator = server.local_operator_state(run_root)
            self.assertTrue(operator["force_stop_available"])
            self.assertFalse(operator["reset_available"], "no stop receipt yet")
            with self.assertRaisesRegex(server.LocalStopError, "stop the run first"):
                server.request_local_reset(run_root, viewer_pid=1)
            (receipt.parent / "stop-receipt.json").write_text("{}", encoding="utf-8")
            self.assertTrue(server.local_operator_state(run_root)["reset_available"])
        finally:
            server.LAUNCH_RECEIPT_PATH = previous

    def test_persistent_mode_follows_the_newest_run_and_idles_without_one(self):
        base = Path(tempfile.mkdtemp(prefix="nsc-viewer-follow-"))
        self.addCleanup(shutil.rmtree, base, True)
        runs = base / "local-rehearsals"
        runs.mkdir()
        previous = (server.LOCAL_RUNS_ROOT, server.LAUNCH_RECEIPTS_ROOT, server.LAUNCH_RECEIPT_PATH)
        try:
            server.LOCAL_RUNS_ROOT, server.LAUNCH_RECEIPTS_ROOT = runs, base / "runs"
            self.assertIsNone(server.newest_local_run(runs))
            snapshot = server.Snapshot(runs, runs, local_run_root=None)
            # The constructor must finish (it once lost its tail to an inserted method).
            self.assertIsNone(snapshot.display_task_ids)
            self.assertIsNotNone(snapshot.cache)
            self.assertEqual(snapshot.outputs, runs / ".task-review-agent" / "outputs")
            snapshot.follow_newest_local_run()
            self.assertIsNone(snapshot.local_run_root)
            idle = snapshot.idle_local_state()
            self.assertEqual(idle["run"]["status"], "waiting_for_run")
            self.assertEqual(idle["tasks"], [])
            # Mirror the page's validPipelineActivity(): a rejected record blanks the whole page.
            activity = idle["pipeline_activity"]
            for key in ("headline", "description", "provider_profile", "provider", "provider_source",
                        "model", "model_source", "call_status", "liveness"):
                self.assertIsInstance(activity[key], str)
            self.assertTrue(activity["headline"].strip())
            self.assertIs(activity["terminal"], False)
            self.assertIs(activity["provider_call_open"], False)
            self.assertEqual(activity["mode"], "local_rehearsal")
            self.assertGreaterEqual(activity["stale_after_seconds"], 0)
            for key in ("active_workers", "capacity", "eligible_or_queued", "dependency_blocked", "completed",
                        "architect_calls_completed", "worker_launches", "wakeups", "awaiting_worker", "local_review_ready"):
                self.assertIn(key, activity["counters"])
            self.assertEqual(activity["candidates"], [])
            self.assertEqual(activity["recent_activity"], [])
            first = runs / "run-a"
            first.mkdir()
            (first / "local-manifest.json").write_text("{}", encoding="utf-8")
            snapshot.follow_newest_local_run()
            self.assertEqual(snapshot.local_run_root, first.resolve())
            self.assertEqual(server.LAUNCH_RECEIPT_PATH, base / "runs" / "run-a" / "launch-receipt.json")
            second = runs / "run-b"
            second.mkdir()
            import os as _os, time as _time
            (second / "local-manifest.json").write_text("{}", encoding="utf-8")
            later = _time.time() + 5
            _os.utime(second / "local-manifest.json", (later, later))
            snapshot.follow_newest_local_run()
            self.assertEqual(snapshot.local_run_root, second.resolve())
            shutil.rmtree(second)
            snapshot.follow_newest_local_run()
            self.assertEqual(snapshot.local_run_root, first.resolve(), "falls back to the remaining run")
            shutil.rmtree(first)
            snapshot.follow_newest_local_run()
            self.assertIsNone(snapshot.local_run_root)
        finally:
            server.LOCAL_RUNS_ROOT, server.LAUNCH_RECEIPTS_ROOT, server.LAUNCH_RECEIPT_PATH = previous

    def test_start_button_availability_and_pending_marker(self):
        base = Path(tempfile.mkdtemp(prefix="nsc-viewer-start-"))
        self.addCleanup(shutil.rmtree, base, True)
        runs = base / "Checkouts" / ".task-review-agent" / "local-rehearsals"
        runs.mkdir(parents=True)
        saved = (server.LOCAL_RUNS_ROOT, server.LAUNCH_RECEIPTS_ROOT, server.LAUNCH_SOURCE,
                 server.LAUNCH_CHECKOUT_ROOT, server.LAUNCH_RECEIPT_PATH)
        try:
            server.LOCAL_RUNS_ROOT, server.LAUNCH_RECEIPTS_ROOT = runs, base / "Runs"
            server.LAUNCH_SOURCE, server.LAUNCH_CHECKOUT_ROOT = base / "Project", base / "Checkouts"
            server.LAUNCH_RECEIPT_PATH = None
            snapshot = server.Snapshot(runs, runs, local_run_root=None)
            idle = snapshot.idle_local_state()["run"]["operator"]
            self.assertTrue(idle["start_available"])
            self.assertFalse(idle["start_pending"])
            # A live run (no stop receipt, no scheduler_stopped) blocks Start.
            run_root = runs / "run-a"
            run_root.mkdir()
            (run_root / "local-manifest.json").write_text(json.dumps({"source_repository": str(base / "Project")}), encoding="utf-8")
            receipt = base / "Runs" / "run-a" / "launch-receipt.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text("{}", encoding="utf-8")
            server.LAUNCH_RECEIPT_PATH = receipt
            live = server.local_operator_state(run_root)
            self.assertFalse(live["start_available"])
            self.assertFalse(live["reset_available"])
            # scheduler_stopped in the journal (a run that ended on its own) unlocks both.
            (run_root / "scheduler-events.jsonl").write_text(
                json.dumps({"event": "scheduler_stopped", "timestamp_utc": "2026-09-09T00:00:00+00:00"}) + "\n", encoding="utf-8")
            done = server.local_operator_state(run_root)
            self.assertTrue(done["start_available"])
            self.assertTrue(done["reset_available"])
            # A pending marker newer than the run hides Start until a newer run appears.
            marker = base / "Checkouts" / "start-pending.json"
            marker.write_text("{}", encoding="utf-8")
            import os as _os, time as _time
            future = _time.time() + 5
            _os.utime(marker, (future, future))
            pending = server.local_operator_state(run_root)
            self.assertTrue(pending["start_pending"])
            self.assertFalse(pending["start_available"])
            with self.assertRaisesRegex(server.LocalStopError, "already in progress"):
                server.request_local_start()
        finally:
            (server.LOCAL_RUNS_ROOT, server.LAUNCH_RECEIPTS_ROOT, server.LAUNCH_SOURCE,
             server.LAUNCH_CHECKOUT_ROOT, server.LAUNCH_RECEIPT_PATH) = saved

    def test_dirty_checkout_blocks_start_and_a_dead_launcher_reports_its_log(self):
        base = Path(tempfile.mkdtemp(prefix="nsc-viewer-dirty-"))
        self.addCleanup(shutil.rmtree, base, True)
        import subprocess
        repo = base / "Project"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        (repo / "a.txt").write_text("x", encoding="utf-8")
        runs = base / "Checkouts" / ".task-review-agent" / "local-rehearsals"
        runs.mkdir(parents=True)
        saved = (server.LOCAL_RUNS_ROOT, server.LAUNCH_RECEIPTS_ROOT, server.LAUNCH_SOURCE,
                 server.LAUNCH_CHECKOUT_ROOT, server.LAUNCH_RECEIPT_PATH, server._LAST_START_ERROR)
        try:
            server.LOCAL_RUNS_ROOT, server.LAUNCH_RECEIPTS_ROOT = runs, base / "Runs"
            server.LAUNCH_SOURCE, server.LAUNCH_CHECKOUT_ROOT = repo, base / "Checkouts"
            server.LAUNCH_RECEIPT_PATH = None
            server._DIRTY_CACHE.clear()
            snapshot = server.Snapshot(runs, runs, local_run_root=None)
            operator = snapshot.idle_local_state()["run"]["operator"]
            self.assertFalse(operator["start_available"])
            self.assertIn("a.txt", operator["start_blocker"])
            with self.assertRaisesRegex(server.LocalStopError, "uncommitted"):
                server.request_local_start()
            # A launcher that died without a run: its log tail surfaces as start_error.
            log = base / "Checkouts" / "viewer-start-x.log"
            log.write_text("Claude login valid\nIn-place Source is dirty: refused\n", encoding="utf-8")
            (base / "Checkouts" / "start-pending.json").write_text(json.dumps(
                {"requested_at_utc": "now", "helper_pid": 4_000_009, "log": str(log)}), encoding="utf-8")
            server._PID_CACHE.clear()
            self.assertFalse(server.start_pending())
            self.assertIn("refused", server._LAST_START_ERROR)
            self.assertFalse((base / "Checkouts" / "start-pending.json").exists())
        finally:
            (server.LOCAL_RUNS_ROOT, server.LAUNCH_RECEIPTS_ROOT, server.LAUNCH_SOURCE,
             server.LAUNCH_CHECKOUT_ROOT, server.LAUNCH_RECEIPT_PATH, server._LAST_START_ERROR) = saved
            server._DIRTY_CACHE.clear()

    @unittest.skipIf(shutil.which("powershell") is None, "PowerShell is unavailable")
    def test_background_powershell_actually_runs(self):
        # A detached spawn used to exit 0 without executing; the helper must really run.
        import time
        base = Path(tempfile.mkdtemp(prefix="nsc-viewer-spawn-"))
        self.addCleanup(shutil.rmtree, base, True)
        target = base / "ran.txt"
        pid = server._detached_powershell("'ok' | Out-File -FilePath '" + str(target).replace("'", "''") + "'")
        self.assertIsInstance(pid, int)
        for _ in range(80):
            if target.exists():
                break
            time.sleep(0.25)
        self.assertTrue(target.exists(), "background PowerShell did not execute its command")

    def test_architect_state_reads_the_journal_and_poke_needs_a_live_endpoint(self):
        _base, _source, run_root = self.make_run()
        with patch_module_attr(server, "scheduler_process", lambda _run_id: None):
            dead = server.architect_state(run_root, "run-1")
            self.assertFalse(dead["alive"])
            self.assertFalse(dead["finished"])
            (run_root / "scheduler-events.jsonl").write_text(
                json.dumps({"event": "poll_started", "timestamp_utc": "2026-09-09T00:00:00+00:00"}) + "\n"
                + json.dumps({"event": "scheduler_stopped", "timestamp_utc": "2026-09-09T00:00:05+00:00"}) + "\n",
                encoding="utf-8")
            done = server.architect_state(run_root, "run-1")
            self.assertTrue(done["finished"])
            self.assertEqual(done["last_event"], "scheduler_stopped")
            self.assertGreater(done["seconds_since_event"], 0)
        with patch_module_attr(server, "scheduler_process", lambda _run_id: 4242):
            alive = server.architect_state(run_root, "run-1")
            self.assertTrue(alive["alive"])
            self.assertEqual(alive["pid"], 4242)
        with self.assertRaisesRegex(server.LocalStopError, "no live wake endpoint"):
            server.request_local_poke(run_root)

    def test_production_mode_follows_autonomous_runs_and_uses_their_journal(self):
        base = Path(tempfile.mkdtemp(prefix="nsc-viewer-prod-"))
        self.addCleanup(shutil.rmtree, base, True)
        source = base / "Project"
        (source / "Tasks").mkdir(parents=True)
        checkouts = base / "Project-Checkouts"
        run_root = checkouts / ".task-review-agent" / "autonomous-runs" / "abc" / "production-x"
        run_root.mkdir(parents=True)
        (run_root / "manifest.json").write_text(json.dumps({"run_id": "production-x", "source_repository": str(source),
                                                              "target_task_ids": ["NSC-042"], "github_repository": "o/r"}), encoding="utf-8")
        (run_root / "events.jsonl").write_text(json.dumps({"event": "scheduler_stopped", "timestamp_utc": "2026-09-09T00:00:00+00:00"}) + "\n", encoding="utf-8")
        saved = (server.RUNS_MODE, server.LAUNCH_SOURCE, server.LAUNCH_CHECKOUT_ROOT, server.LAUNCH_RECEIPTS_ROOT,
                 server.LAUNCH_REPOSITORY, server.LAUNCH_RECEIPT_PATH, server.LOCAL_RUNS_ROOT, server.ENABLED_TASK_IDS,
                 server.LAUNCH_TASK_IDS)
        try:
            server.RUNS_MODE, server.LAUNCH_SOURCE, server.LAUNCH_CHECKOUT_ROOT = "production", source, checkouts
            server.LAUNCH_RECEIPTS_ROOT, server.LAUNCH_REPOSITORY = checkouts / "launch-receipts", "o/r"
            server.LAUNCH_RECEIPT_PATH, server.LOCAL_RUNS_ROOT = None, None
            server.LAUNCH_TASK_IDS, server.ENABLED_TASK_IDS = ("NSC-042",), frozenset({"NSC-042"})
            server._DIRTY_CACHE.clear()
            self.assertEqual(server._events_file(run_root), run_root / "events.jsonl")
            self.assertEqual(server._run_source(run_root), source)
            self.assertTrue(server.scheduler_finished(run_root))
            # A run that died at preflight journals autonomous_run_error and nothing
            # else; it is over, so the page must offer Start rather than Stop.
            failed = checkouts / ".task-review-agent" / "autonomous-runs" / "abc" / "production-failed"
            failed.mkdir(parents=True)
            (failed / "events.jsonl").write_text(json.dumps({"event": "autonomous_run_error", "stage": "preflight",
                                                             "timestamp_utc": "2026-09-09T15:47:28.810067+00:00"}) + "\n", encoding="utf-8")
            self.assertTrue(server.scheduler_finished(failed))
            with patch_module_attr(server, "scheduler_process", lambda _run_id: 4242):
                self.assertFalse(server.scheduler_finished(failed), "a draining scheduler still holds the lock; not finished")
            # A stop that was acknowledged but never journaled scheduler_stopped
            # (force stop, crash) is complete once the scheduler is gone.
            gone = checkouts / ".task-review-agent" / "autonomous-runs" / "abc" / "production-gone"
            gone.mkdir(parents=True)
            (gone / "stop-request.json").write_text(json.dumps({"requested_at_utc": "2026-09-09T17:15:49+00:00"}), encoding="utf-8")
            (gone / "events.jsonl").write_text(
                json.dumps({"event": "scheduler_draining", "timestamp_utc": "2026-09-09T17:15:49+00:00",
                            "active_children": [{"task_id": "NSC-042"}]}) + "\n"
                + json.dumps({"event": "worker_failed", "task_id": "NSC-042", "timestamp_utc": "2026-09-09T17:20:49+00:00"}) + "\n",
                encoding="utf-8")
            with patch_module_attr(server, "scheduler_process", lambda _run_id: 4242):
                live = server.local_stop_state(gone)
                self.assertTrue(live["acknowledged"])
                self.assertFalse(live["completed"], "a live scheduler is still draining")
            with patch_module_attr(server, "scheduler_process", lambda _run_id: None):
                done = server.local_stop_state(gone)
                self.assertTrue(done["completed"], "no scheduler process means the stop is over")
            silent = checkouts / ".task-review-agent" / "autonomous-runs" / "abc" / "production-silent"
            silent.mkdir(parents=True)
            (silent / "events.jsonl").write_text(json.dumps({"event": "scheduler_started",
                                                             "timestamp_utc": "2026-09-09T00:00:00+00:00"}) + "\n", encoding="utf-8")
            with patch_module_attr(server, "scheduler_process", lambda _run_id: 4242):
                self.assertFalse(server.scheduler_finished(silent), "a live scheduler keeps a quiet run alive")
            with patch_module_attr(server, "scheduler_process", lambda _run_id: None):
                self.assertTrue(server.scheduler_finished(silent), "no scheduler and a stale journal means the run is over")
            # A run that died before writing any journal (only manifest.json exists)
            # is over once its scheduler is gone and its files have been quiet.
            journalless = checkouts / ".task-review-agent" / "autonomous-runs" / "abc" / "production-journalless"
            journalless.mkdir(parents=True)
            (journalless / "manifest.json").write_text("{}", encoding="utf-8")
            old = time.time() - 600
            os.utime(journalless / "manifest.json", (old, old))
            with patch_module_attr(server, "scheduler_process", lambda _run_id: None):
                self.assertTrue(server.scheduler_finished(journalless), "journal-less dead run must count as finished")
            with patch_module_attr(server, "scheduler_process", lambda _run_id: 4242):
                self.assertFalse(server.scheduler_finished(journalless), "a live scheduler keeps a journal-less run alive")
            fresh = checkouts / ".task-review-agent" / "autonomous-runs" / "abc" / "production-fresh"
            fresh.mkdir(parents=True)
            (fresh / "events.jsonl").write_text(json.dumps({"event": "scheduler_started",
                                                            "timestamp_utc": datetime.now(timezone.utc).isoformat()}) + "\n", encoding="utf-8")
            with patch_module_attr(server, "scheduler_process", lambda _run_id: None):
                self.assertFalse(server.scheduler_finished(fresh), "a run that just started is not declared dead")
            (checkouts / "launch-receipts").mkdir(parents=True)
            (checkouts / "launch-receipts" / "production-x.json").write_text("{}", encoding="utf-8")
            (checkouts / "launch-receipts" / "stop-receipt.json").write_text(json.dumps({"run_id": "older-run"}), encoding="utf-8")
            self.assertFalse(server.stop_receipt_present(checkouts / "launch-receipts" / "production-x.json", run_root),
                             "another run's stop receipt must not count for this run")
            with patch_module_attr(server, "source_dirty_files", lambda _s: []):
                operator = server.local_operator_state(run_root)
            self.assertEqual(operator["launch_receipt"], str(checkouts / "launch-receipts" / "production-x.json"))
            self.assertTrue(operator["reset_available"], "a finished production run unlocks reset")
            self.assertTrue(operator["start_available"])
            snapshot = server.Snapshot(source / "Tasks", checkouts, local_run_root=None)
            self.assertEqual(server.current_followed_run_root(snapshot), run_root)
            self.assertEqual(server.production_display_ids(snapshot), ("NSC-042",))
            idle = snapshot.idle_local_state()
            self.assertEqual(idle["run"]["marker"], "PRODUCTION")
            self.assertEqual(idle["run"]["source_repository"], str(source))
            # Scope toggles persist beside the checkout root and drive Start's -TaskId.
            changed = server.request_scope_change({"task_id": "NSC-1007", "enabled": True})
            self.assertEqual(changed["scope_task_ids"], ["NSC-042", "NSC-1007"])
            self.assertEqual(server.load_enabled_scope(), frozenset({"NSC-042", "NSC-1007"}))
            server.request_scope_change({"task_id": "NSC-042", "enabled": False})
            server.request_scope_change({"task_id": "NSC-1007", "enabled": False})
            with self.assertRaises(server.LocalStopError):
                server.request_local_start()
            with self.assertRaises(server.LocalStopError):
                server.request_scope_change({"task_id": "bogus", "enabled": True})
            saved_review = server.LAUNCH_HUMAN_REVIEW
            try:
                server.LAUNCH_HUMAN_REVIEW = True
                command = server.start_command(("NSC-1001", "NSC-042"))
                self.assertIn("-Mode production", command)
                self.assertIn("-HumanReview", command)
                self.assertIn("-TaskId 'NSC-1001,NSC-042'", command)
                server.LAUNCH_HUMAN_REVIEW = False
                self.assertNotIn("-HumanReview", server.start_command(("NSC-042",)))
            finally:
                server.LAUNCH_HUMAN_REVIEW = saved_review
            run = {"operator": {}, "repository": None}
            server.annotate_operator(run, persistent=True)
            self.assertEqual(run["github_url"], "https://github.com/o/r")
            self.assertEqual(run["operator"]["runs_mode"], "production")
            result = server.request_local_stop(run_root)
            self.assertEqual(result["status"], "stop_requested")
        finally:
            (server.RUNS_MODE, server.LAUNCH_SOURCE, server.LAUNCH_CHECKOUT_ROOT, server.LAUNCH_RECEIPTS_ROOT,
             server.LAUNCH_REPOSITORY, server.LAUNCH_RECEIPT_PATH, server.LOCAL_RUNS_ROOT, server.ENABLED_TASK_IDS,
             server.LAUNCH_TASK_IDS) = saved

    def test_task_record_names_its_checkout_folder(self):
        base = Path(tempfile.mkdtemp(prefix="nsc-viewer-checkout-"))
        self.addCleanup(shutil.rmtree, base, True)
        tasks_dir = Path(__file__).resolve().parents[4] / "Tasks"
        snapshot = server.Snapshot(tasks_dir, base, display_task_ids=["NSC-042"], local_run_root=None)
        task = next(item for item in snapshot.build()["tasks"] if item["id"] == "NSC-042")
        self.assertEqual(task["checkout_path"], str(base / "NSC-042"))
        self.assertFalse(task["checkout_exists"])
        (base / "NSC-042").mkdir()
        task = next(item for item in snapshot.build()["tasks"] if item["id"] == "NSC-042")
        self.assertTrue(task["checkout_exists"])

    def test_create_issue_uses_the_workers_initialisation_path(self):
        # The button must leave exactly the Issue a production worker expects to
        # find: an existing managed Issue is reported, otherwise _initialize_issue runs.
        base = Path(tempfile.mkdtemp(prefix="nsc-viewer-issue-"))
        self.addCleanup(shutil.rmtree, base, True)
        calls = []

        class FakeInbox:
            issue_number, issue_url, disposition = 7, "https://github.com/o/r/issues/7", "existing"

        class FakeState:
            class state:
                value = "open"

        class FakeSnapshot:
            issue_number, issue_url, managed, state = 12, "https://github.com/o/r/issues/12", True, FakeState

        class FakeService:
            def __init__(self, **kwargs):
                calls.append(("service", kwargs["worker_id"]))
            def find(self, task_id):
                calls.append(("find", task_id))
                return None
            def _initialize_issue(self, task, *, now):
                calls.append(("initialize", task["id"], bool(now)))
                return FakeSnapshot

        import types
        fake_store = types.SimpleNamespace(VINCENT_INBOX_TITLE="NSC-Vincent", GhIssueBackend=lambda **kw: object(),
                                           IssueWorkflowService=FakeService, IssueWorkflowStoreError=RuntimeError,
                                           utc_now=lambda: "2026-09-09T00:00:00Z")
        fake_committed = types.SimpleNamespace(CommittedTaskError=RuntimeError, load_committed_task=lambda root, tid: {"id": tid})
        fake_bootstrap = types.SimpleNamespace(ensure_autonomous_vincent_inbox=lambda **kw: (calls.append(("inbox", kw["repository"])) or FakeInbox))
        saved = (server.RUNS_MODE, server.LAUNCH_SOURCE, server.LAUNCH_CHECKOUT_ROOT, server.LAUNCH_REPOSITORY, dict(server._ISSUE_RESULTS))
        modules = {"Pipeline.TaskReviewAgent.issue_workflow_store": fake_store,
                   "Pipeline.TaskReviewAgent.committed_tasks": fake_committed,
                   "Pipeline.TaskReviewAgent.vincent_inbox_bootstrap": fake_bootstrap}
        import sys
        previous = {name: sys.modules.get(name) for name in modules}
        try:
            server.RUNS_MODE, server.LAUNCH_SOURCE, server.LAUNCH_CHECKOUT_ROOT, server.LAUNCH_REPOSITORY = "production", base, base / "c", "o/r"
            sys.modules.update(modules)
            result = server.request_task_issue({"task_id": "NSC-042"})
            self.assertEqual(result["status"], "created")
            self.assertEqual(result["issue_number"], 12)
            self.assertEqual(result["inbox_number"], 7)
            self.assertEqual(result["state"], "open")
            self.assertEqual(calls, [("inbox", "o/r"), ("service", "gauntlet-view-operator"), ("find", "NSC-042"),
                                     ("initialize", "NSC-042", True)])
            self.assertEqual(server._ISSUE_RESULTS["NSC-042"]["issue_url"], "https://github.com/o/r/issues/12")
            server.RUNS_MODE = "local"
            with self.assertRaises(server.LocalStopError):
                server.request_task_issue({"task_id": "NSC-042"})
        finally:
            for name, module in previous.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
            server.RUNS_MODE, server.LAUNCH_SOURCE, server.LAUNCH_CHECKOUT_ROOT, server.LAUNCH_REPOSITORY = saved[:4]
            server._ISSUE_RESULTS.clear()
            server._ISSUE_RESULTS.update(saved[4])

    @unittest.skipIf(shutil.which("node") is None, "node is unavailable")
    def test_inline_script_still_parses(self):
        html = (ROOT / "Pipeline" / "TaskReviewAgent" / "GauntletView" / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html, re.S)
        self.assertTrue(scripts)
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
            handle.write("\n".join(scripts))
            path = handle.name
        self.addCleanup(Path(path).unlink, True)
        completed = subprocess.run(["node", "--check", path], capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("requestLocalStop", "\n".join(scripts))


if __name__ == "__main__":
    unittest.main(verbosity=2)
