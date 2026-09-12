#!/usr/bin/env python3
"""Component regressions for handoff 5.1-5.3 and browser fences 7.3/7.5.

All task state belongs to disposable Git fixtures. HTTP uses loopback only;
the browser-only cases feed an authoritative local payload directly to Node,
independently of backend support. No provider or canonical Unity asset is used.
"""
from __future__ import annotations

import io
import json
import os
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

import local_rehearsal_view_test as fixtures
from Pipeline.TaskReviewAgent import issue_workflow_store, local_rehearsal
from Pipeline.TaskReviewAgent.issue_workflow import (
    WorkflowActor, WorkflowEventType, WorkflowState, labels_for_state,
    render_event_comment, transition, update_issue_body,
)

server = fixtures.server


def timestamp(value):
    return value.isoformat().replace("+00:00", "Z")


def local_ui_payload():
    """Backend contract fixture: no Snapshot.build() may gate browser evidence."""
    task = {
        "id": "NSC-1001", "title": "Inspect a local candidate", "state": "active",
        "local_state": "agent_working", "in_scope": True, "parent": None,
        "depends_on": [], "acceptance": [], "resources": [], "worker": None,
        "kind": "implementation", "decomposition_state": "concrete",
        "execution_scope": "local", "disposition": "active", "progress": {},
        "token_cost": {"recorded_total_tokens": 31, "cost_label": "$0.25",
                       "projection_label": "$12345.67", "total_calls": 1},
    }
    return {"run": {"mode": "local_rehearsal", "run_id": "ui-only-local",
                    "targets": [task["id"]], "max_capacity": 1,
                    "status": "running", "complete": False, "repository": None},
            "scheduler": {"active": [task["id"]]}, "tasks": [task]}


class LocalBrowserAuthorityTests(unittest.TestCase):
    def render(self, snapshot):
        selected = os.environ.get("NSC_LOCAL_REVIEW_HTML")
        return fixtures.render_in_node(snapshot, html_path=Path(selected) if selected else None)

    def test_local_legend_hides_production_completion_states(self):
        rendered = self.render(local_ui_payload())
        legend = json.dumps(rendered["legend"])
        for forbidden in ("complete", "checks_pending", "integration_queued"):
            self.assertNotIn(f'state key \\"{forbidden}\\"', legend)
        self.assertIn("Local Review Ready", legend)
        self.assertNotIn("Task Complete", legend)

    def test_local_detail_suppresses_manufactured_projection(self):
        rendered = self.render(local_ui_payload())
        self.assertIn("Cost so far: $0.25", rendered["detail"])
        self.assertIn("Tokens used so far: 31", rendered["detail"])
        self.assertNotIn("Projected cost at completion", rendered["detail"])
        self.assertNotIn("12345.67", rendered["detail"])

    def test_production_legend_and_projection_remain_available(self):
        snapshot = local_ui_payload()
        snapshot["run"]["mode"] = "production"
        rendered = self.render(snapshot)
        legend = json.dumps(rendered["legend"])
        self.assertIn("Task Complete", legend)
        self.assertNotIn("Local Review Ready", legend)
        self.assertIn("Projected cost at completion: $12345.67", rendered["detail"])


class LocalRehearsalReviewTests(unittest.TestCase):
    setUp = fixtures.LocalRehearsalViewTests.setUp
    tearDown = fixtures.LocalRehearsalViewTests.tearDown
    git = fixtures.LocalRehearsalViewTests.git
    create_run = fixtures.LocalRehearsalViewTests.create_run
    view = fixtures.LocalRehearsalViewTests.view

    def acquire(self, context=None):
        context = context or self.context
        service = context.workflow_service("view-worker")
        result = service.acquire_agent_lease(
            task=context.manifest["contracts"][self.task_id], source_head=context.source_head,
            branch="local/view-fixture", checkout_path=str(context.checkout_root / self.task_id),
            planned_approach="Inspect the local view during execution.",
            expected_validation="Deterministic view regression.",
        )
        self.assertEqual(result["status"], "acquired")
        return service

    def test_released_lease_still_serves_ready_task_over_http(self):
        service = self.acquire()
        current = service.find(self.task_id)
        next_state, event = transition(
            current.state, event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
            actor_type=WorkflowActor.AGENT, actor_id="view-worker",
            to_state=WorkflowState.AGENT_READY, to_phase=current.state.phase,
            details={"reason": "supervisor turn budget exhausted"},
            now=local_rehearsal.utc_now(),
        )
        service.backend.add_comment(current.issue_number, render_event_comment(event, "Release test lease."))
        service.backend.update_issue(current.issue_number,
            body=update_issue_body(current.body, next_state, next_action="Resume the local task."),
            labels=labels_for_state(next_state.state, current.labels))
        self.assertEqual(self.context.task_state(self.task_id)["state"], "agent_ready")
        handler = type("LocalReviewHandler", (server.Handler,), {"snapshot": self.view()})
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
        try:
            connection.request("GET", "/api/state")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            state = json.loads(response.read())
            self.assertEqual(state["tasks"][0]["state"], "ready")
            self.assertEqual(state["scheduler"]["active"], [])
        finally:
            connection.close()
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

    def test_elapsed_starts_at_lease_acquisition_after_queue_wait(self):
        started = datetime.now(timezone.utc).replace(microsecond=0)
        created = started - timedelta(hours=3)
        with mock.patch.object(local_rehearsal, "utc_now", return_value=timestamp(created)):
            context = self.create_run("queued-view")
        with mock.patch.object(local_rehearsal, "utc_now", return_value=timestamp(started)), \
             mock.patch.object(issue_workflow_store, "utc_now", return_value=timestamp(started)):
            self.acquire(context)
        view = self.view(context)
        with mock.patch.object(server.time, "time", return_value=started.timestamp() + 30):
            task = view.build()["tasks"][0]
        self.assertEqual(task["state"], "active")
        self.assertEqual(task["worker"]["elapsed_seconds"], 30)
        self.assertEqual(task["progress"]["total_elapsed_seconds"], 30)
        self.assertIn("30s elapsed", " ".join(task["node_lines"]))

    def test_missing_start_time_never_substitutes_run_creation(self):
        self.acquire()
        view = self.view()
        payload = self.context.snapshot()
        payload["tasks"][self.task_id].pop("started_at_utc", None)
        with mock.patch.object(view, "local_snapshot", return_value=payload):
            task = view.build()["tasks"][0]
        self.assertIsNone(task["worker"]["elapsed_seconds"])
        self.assertIn("unavailable elapsed", " ".join(task["node_lines"]))

    def test_stream_refreshes_elapsed_without_durable_events(self):
        self.acquire()
        view = self.view()
        durable = self.context.state_path.read_bytes()
        now = datetime.now(timezone.utc).timestamp()
        output = io.BytesIO()
        handler = object.__new__(server.Handler)
        handler.snapshot, handler.wfile = view, output
        handler.send_response = mock.Mock()
        handler.send_header = mock.Mock()
        handler.end_headers = mock.Mock()
        with mock.patch.object(server.time, "time", side_effect=[now, now, now + 8, now + 8]), \
             mock.patch.object(server.time, "sleep", side_effect=[None, BrokenPipeError]):
            handler._stream()
        frames = [json.loads(line[6:]) for line in output.getvalue().decode().splitlines() if line.startswith("data: ")]
        self.assertEqual(len(frames), 2, "active local execution must refresh elapsed on each clock tick")
        first = frames[0]["tasks"][0]["worker"]["elapsed_seconds"]
        second = frames[1]["tasks"][0]["worker"]["elapsed_seconds"]
        self.assertAlmostEqual(second - first, 8, delta=0.1)
        self.assertEqual(self.context.state_path.read_bytes(), durable)

    def test_idle_run_fingerprint_does_not_tick(self):
        view = self.view()
        with mock.patch.object(server.time, "time", return_value=1000):
            first = view.fingerprint()
        with mock.patch.object(server.time, "time", return_value=9000):
            self.assertEqual(first, view.fingerprint())


if __name__ == "__main__":
    unittest.main()
