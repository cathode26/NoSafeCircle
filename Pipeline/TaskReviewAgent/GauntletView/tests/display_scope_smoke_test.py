"""Pure/component regression tests; disposable artifacts, no task execution.

Acceptance mapping: request A and regression invariants 1-3, 10-11.
The signature fallback deliberately exercises the old server's behavior for
red-before evidence rather than failing on an unsupported constructor argument.
"""
from __future__ import annotations

import contextlib
import hashlib
import inspect
import io
import json
import sys
import threading
import unittest
from urllib.request import urlopen
from unittest import mock

from gauntlet_view_smoke_test import Fixture, event, server, write_json

DISPLAY_IDS = [f"NSC-{number}" for number in range(1001, 1009)]


def proof_fixture():
    fixture = Fixture()
    dependencies = {
        "NSC-1002": ["NSC-1001"], "NSC-1003": ["NSC-1001"],
        "NSC-1004": ["NSC-1002"], "NSC-1005": ["NSC-1002"],
        "NSC-1006": ["NSC-1003"], "NSC-1007": ["NSC-1003"],
        "NSC-1008": ["NSC-1004", "NSC-1005", "NSC-1006", "NSC-1007"],
    }
    for task_id in [*DISPLAY_IDS, "NSC-1009"]:
        fixture.add_task(task_id, progress_events=[event("run_finished", {
            "status": "human_action_required", "issue_number": 112,
            "pull_request_number": 116,
        })])
        path = fixture.tasks / f"{task_id}.yaml"
        contract = server.read_json(path)
        contract["depends_on"] = dependencies.get(task_id, [])
        write_json(path, contract)
    manifest = server.read_json(fixture.run / "manifest.json")
    manifest["target_task_ids"] = [DISPLAY_IDS[0]]
    write_json(fixture.run / "manifest.json", manifest)
    fixture.write_scheduler_events([{
        "event": "architect_wait_started", "wait_mode": "event_or_fallback",
        "timestamp_utc": "2026-09-07T01:00:00Z",
    }])
    return fixture


def display_snapshot(fixture, ids=DISPLAY_IDS):
    if "display_task_ids" in inspect.signature(server.Snapshot).parameters:
        return server.Snapshot(fixture.tasks, fixture.state, display_task_ids=ids)
    return fixture.snapshot()


def artifact_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


@contextlib.contextmanager
def fixture_http(snapshot):
    class FixtureHandler(server.Handler):
        def handle(self):
            try:
                super().handle()
            except ConnectionError:
                # Closing a headless browser aborts its idle HTTP sockets on Windows.
                pass
    handler = FixtureHandler
    handler.snapshot = snapshot
    http = server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    http.daemon_threads = True
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}"
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=5)


class DisplayScopeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = proof_fixture()
        self.snapshot = display_snapshot(self.fixture)

    def tearDown(self):
        self.fixture.close()

    def assert_display(self, state):
        self.assertEqual([task["id"] for task in state["tasks"]], DISPLAY_IDS)
        self.assertEqual(state["display"]["task_ids"], DISPLAY_IDS)

    def test_one_task_run_keeps_explicit_eight_task_display(self):
        state = self.snapshot.build()
        self.assert_display(state)
        self.assertEqual(state["run"]["targets"], ["NSC-1001"])
        self.assertEqual(sum(t["in_scope"] for t in state["tasks"]), 1)

    def test_api_state_serves_all_eight_requested_ids(self):
        with fixture_http(self.snapshot) as url, urlopen(url + "/api/state", timeout=5) as response:
            self.assert_display(json.load(response))

    def test_real_sse_preserves_display_after_manifest_refresh(self):
        with fixture_http(self.snapshot) as url, urlopen(url + "/api/stream", timeout=5) as response:
            first = json.loads(response.readline().decode()[6:])
            self.assert_display(first)
            manifest = server.read_json(self.fixture.run / "manifest.json")
            manifest["target_task_ids"] = ["NSC-1002"]
            write_json(self.fixture.run / "manifest.json", manifest)
            for _ in range(12):
                line = response.readline().decode()
                if line.startswith("data: "):
                    second = json.loads(line[6:])
                    if second["run"]["targets"] == ["NSC-1002"]:
                        self.assert_display(second)
                        break
            else:
                self.fail("SSE did not deliver changed manifest")

    def test_display_does_not_change_states_links_or_pipeline_classification(self):
        with mock.patch.object(server.time, "time", return_value=1788746400):
            original = self.fixture.snapshot().build()
            selected = self.snapshot.build()
        by_id = {task["id"]: task for task in original["tasks"]}
        for task in selected["tasks"]:
            self.assertEqual(task, by_id[task["id"]])
            self.assertEqual(task["state"], "human_action")
            self.assertTrue(task["worker"]["issue_url"].endswith("/issues/112"))
            self.assertTrue(task["worker"]["pull_request_url"].endswith("/pull/116"))
        self.assertEqual(selected["pipeline_activity"], original["pipeline_activity"])
        self.assertEqual(selected["pipeline_activity"]["stage"], "event_wait")

    def test_scope_reads_do_not_mutate_any_artifact(self):
        before = artifact_hashes(self.fixture.root)
        for _ in range(3):
            self.snapshot.build()
            self.snapshot.fingerprint()
        with fixture_http(self.snapshot) as url, urlopen(url + "/api/state", timeout=5) as response:
            response.read()
        self.assertEqual(artifact_hashes(self.fixture.root), before)

    def test_display_does_not_remove_dependency_truth_outside_selection(self):
        path = self.fixture.tasks / "NSC-1001.yaml"
        contract = server.read_json(path)
        contract["depends_on"] = ["NSC-1009"]
        write_json(path, contract)
        # An empty existing journal still represents a worker attempt. This
        # dependency test needs a task that has never had a worker journal.
        (self.fixture.state / ".task-review-agent" / "outputs" / "NSC-1001" / "worker-run-a" / "progress.jsonl").unlink()
        original = self.fixture.snapshot().build()["tasks"][0]
        selected = self.snapshot.build()["tasks"][0]
        self.assertEqual(selected["depends_on"], ["NSC-1009"])
        self.assertEqual(selected["state"], original["state"])
        self.assertEqual(selected["state"], "pending")

    def test_missing_display_contract_is_reported_without_fabricating_node(self):
        snapshot = display_snapshot(self.fixture, ["NSC-1001", "NSC-1999"])
        state = snapshot.build()
        self.assertEqual([task["id"] for task in state["tasks"]], ["NSC-1001"])
        self.assertEqual(state["display"]["missing_task_ids"], ["NSC-1999"])

    def test_cli_accepts_repeatable_display_ids(self):
        argv = ["server.py", "--tasks", str(self.fixture.tasks), "--state", str(self.fixture.state)]
        for task_id in DISPLAY_IDS:
            argv += ["--display-task-id", task_id]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(server, "ThreadingHTTPServer") as http:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                try:
                    result = server.main()
                except SystemExit as error:
                    self.fail(f"Display launch rejected with exit {error.code}")
            self.assertEqual(result, 0)
            http.return_value.serve_forever.assert_called_once()
            self.assert_display(server.Handler.snapshot.build())


if __name__ == "__main__":
    unittest.main()
