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
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest import mock

from gauntlet_view_smoke_test import Fixture, event, server, write_json

DISPLAY_IDS = [f"NSC-{number}" for number in range(1001, 1009)]


def proof_fixture():
    fixture = Fixture()
    dependencies = {
        # Exact committed family in the target rehearsal graph.
        "NSC-1007": ["NSC-1001"],
        "NSC-1008": ["NSC-1007"],
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
def fixture_http(snapshot, approval=None):
    class FixtureHandler(server.Handler):
        def handle(self):
            try:
                super().handle()
            except ConnectionError:
                # Closing a headless browser aborts its idle HTTP sockets on Windows.
                pass
    handler = FixtureHandler
    handler.snapshot = snapshot
    handler.approval = approval
    http = server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    handler.origin = f"http://127.0.0.1:{http.server_port}"
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

    def test_generated_descendants_materialize_after_snapshot_start(self):
        snapshot = display_snapshot(self.fixture, ["NSC-1006"])
        before = snapshot.build()
        self.assertEqual([task["id"] for task in before["tasks"]], ["NSC-1006"])

        parent_path = self.fixture.tasks / "NSC-1006.yaml"
        parent = server.read_json(parent_path)
        parent["decomposition_state"] = "decomposed"
        parent["decomposition_children"] = ["NSC-1010", "NSC-1011"]
        write_json(parent_path, parent)
        for task_id in ("NSC-1010", "NSC-1011"):
            self.fixture.add_task(
                task_id,
                parent="NSC-1006",
                progress_events=[event("run_finished", {"status": "stopped"})],
            )

        after = snapshot.build()

        self.assertEqual(
            [task["id"] for task in after["tasks"]],
            ["NSC-1006", "NSC-1010", "NSC-1011"],
        )
        self.assertEqual(after["display"]["task_ids"], ["NSC-1006"])
        self.assertEqual(
            after["display"]["expanded_task_ids"],
            ["NSC-1006", "NSC-1010", "NSC-1011"],
        )
        self.assertEqual(after["tasks"][0]["state"], "aggregate")

    def test_generated_descendants_extend_run_scope_without_unrelated_tasks(self):
        parent_path = self.fixture.tasks / "NSC-1001.yaml"
        parent = server.read_json(parent_path)
        parent["decomposition_state"] = "decomposed"
        parent["decomposition_children"] = ["NSC-1010"]
        write_json(parent_path, parent)
        self.fixture.add_task(
            "NSC-1010",
            parent="NSC-1001",
            progress_events=[event("run_finished", {"status": "stopped"})],
        )

        state = self.snapshot.build()
        ids = [task["id"] for task in state["tasks"]]

        self.assertEqual(ids, [*DISPLAY_IDS, "NSC-1010"])
        self.assertNotIn("NSC-1009", ids)
        self.assertEqual(state["run"]["targets"], ["NSC-1001"])
        self.assertEqual(
            state["run"]["expanded_targets"],
            ["NSC-1001", "NSC-1010"],
        )
        self.assertTrue(next(task for task in state["tasks"] if task["id"] == "NSC-1010")["in_scope"])

    def test_exact_eight_roots_admit_only_the_four_committed_generated_children(self):
        relationships = {
            "NSC-1006": ("NSC-1009", "NSC-1010"),
            "NSC-1007": ("NSC-1011", "NSC-1012"),
        }
        for parent_id, child_ids in relationships.items():
            parent_path = self.fixture.tasks / f"{parent_id}.yaml"
            parent = server.read_json(parent_path)
            parent["decomposition_state"] = "decomposed"
            parent["decomposition_children"] = list(child_ids)
            write_json(parent_path, parent)
            for child_id in child_ids:
                child_path = self.fixture.tasks / f"{child_id}.yaml"
                if child_path.is_file():
                    child = server.read_json(child_path)
                    child["parent"] = parent_id
                    write_json(child_path, child)
                else:
                    self.fixture.add_task(
                        child_id,
                        parent=parent_id,
                        progress_events=[event("run_finished", {"status": "stopped"})],
                    )

        state = self.snapshot.build()
        self.assertEqual(
            [task["id"] for task in state["tasks"]],
            [*DISPLAY_IDS, "NSC-1009", "NSC-1010", "NSC-1011", "NSC-1012"],
        )
        self.assertEqual(state["display"]["task_ids"], DISPLAY_IDS)
        self.assertEqual(
            state["display"]["expanded_task_ids"],
            [*DISPLAY_IDS, "NSC-1009", "NSC-1010", "NSC-1011", "NSC-1012"],
        )
        self.assertEqual(
            {task["id"]: task["parent"] for task in state["tasks"] if task["parent"]},
            {
                "NSC-1009": "NSC-1006",
                "NSC-1010": "NSC-1006",
                "NSC-1011": "NSC-1007",
                "NSC-1012": "NSC-1007",
            },
        )

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

    def test_cli_managed_mode_publishes_exact_manifest_identity(self):
        manifest = server.read_json(self.fixture.run / "manifest.json")
        manifest.update(
            source_repository=str(self.fixture.tasks.parent),
            initial_source_commit="a" * 40,
            target_task_ids=DISPLAY_IDS,
        )
        write_json(self.fixture.run / "manifest.json", manifest)
        argv = [
            "server.py",
            "--tasks", str(self.fixture.tasks),
            "--state", str(self.fixture.state),
            "--run-dir", str(self.fixture.run),
            "--source-commit", "a" * 40,
            "--source-branch", "main",
            "--run-id", "run-a",
            "--repository", "fixture-owner/pipeline-rehearsal",
        ]
        for task_id in DISPLAY_IDS:
            argv += ["--display-task-id", task_id]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(
            server, "ThreadingHTTPServer"
        ) as http, mock.patch.object(server, "git_branch", return_value="main"):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(server.main(), 0)
        identity = server.Handler.health["identity"]
        self.assertEqual(identity["source"], str(self.fixture.tasks.parent.resolve()))
        self.assertEqual(identity["source_branch"], "main")
        self.assertEqual(identity["source_commit"], "a" * 40)
        self.assertEqual(identity["run_id"], "run-a")
        self.assertEqual(identity["display_task_ids"], DISPLAY_IDS)
        self.assertFalse(identity["human_approval_enabled"])
        http.return_value.serve_forever.assert_called_once()

    def test_exact_run_binding_does_not_drift_to_a_newer_run(self):
        fixed = server.Snapshot(
            self.fixture.tasks,
            self.fixture.state,
            display_task_ids=DISPLAY_IDS,
            run_dir=self.fixture.run,
        )
        newer = self.fixture.run.parent / "run-newer"
        write_json(
            newer / "manifest.json",
            {
                "run_id": "run-newer",
                "github_repository": "other/repository",
                "target_task_ids": ["NSC-1009"],
                "excluded_task_ids": [],
            },
        )
        state = fixed.build()
        self.assertEqual(state["run"]["run_id"], "run-a")
        self.assertEqual(state["run"]["targets"], ["NSC-1001"])
        fingerprint = fixed.fingerprint()
        newer_manifest = server.read_json(newer / "manifest.json")
        newer_manifest["target_task_ids"] = ["NSC-1008"]
        write_json(newer / "manifest.json", newer_manifest)
        self.assertEqual(fixed.fingerprint(), fingerprint)
        manifest = server.read_json(self.fixture.run / "manifest.json")
        manifest["max_capacity"] = 4
        write_json(self.fixture.run / "manifest.json", manifest)
        self.assertNotEqual(fixed.fingerprint(), fingerprint)

    def test_health_endpoint_publishes_exact_listener_identity(self):
        identity = {
            "schema": server.HEALTH_SCHEMA,
            "status": "ok",
            "identity": {
                "source": str(self.fixture.tasks.parent),
                "run_id": "run-a",
            },
        }
        previous = server.Handler.health
        server.Handler.health = identity
        try:
            with fixture_http(self.snapshot) as url, urlopen(
                url + "/api/health", timeout=5
            ) as response:
                self.assertEqual(json.load(response), identity)
        finally:
            server.Handler.health = previous

    def test_approval_post_accepts_only_same_origin_one_time_capability(self):
        class Approval:
            def __init__(self):
                self.tokens = {"one-time-token"}

            def list_actions(self):
                return [{"task_id": "NSC-1001", "action_token": "one-time-token"}]

            def approve(self, token):
                if token not in self.tokens:
                    raise RuntimeError("approval capability was already used or unknown")
                self.tokens.remove(token)
                return {"status": "mutation_succeeded", "architect_notified": True}

        approval = Approval()
        with fixture_http(self.snapshot, approval) as url:
            state = json.load(urlopen(url + "/api/state", timeout=5))
            self.assertEqual(state["human_actions"][0]["action_token"], "one-time-token")
            request = Request(
                url + "/api/approve",
                data=json.dumps({"action_token": "one-time-token"}).encode(),
                headers={"Content-Type": "application/json", "Origin": url},
                method="POST",
            )
            self.assertEqual(json.load(urlopen(request, timeout=5))["status"], "mutation_succeeded")
            with self.assertRaises(HTTPError) as duplicate:
                urlopen(request, timeout=5)
            self.assertEqual(duplicate.exception.code, 409)

    def test_approval_post_rejects_cross_origin_and_arbitrary_identity_fields(self):
        class Approval:
            def list_actions(self):
                return []

            def approve(self, _token):
                self.fail("invalid requests reached the controller")

        with fixture_http(self.snapshot, Approval()) as url:
            for body, origin, expected in (
                ({"action_token": "x"}, "http://evil.invalid", 403),
                ({"action_token": "x", "repository": "other/repo"}, url, 400),
                ({"action_token": "x", "command": "anything"}, url, 400),
            ):
                request = Request(
                    url + "/api/approve",
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json", "Origin": origin},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as rejected:
                    urlopen(request, timeout=5)
                self.assertEqual(rejected.exception.code, expected)


if __name__ == "__main__":
    unittest.main()
