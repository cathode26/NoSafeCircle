#!/usr/bin/env python3
"""Focused regression tests for the read-only GauntletView server and UI.

Classification: pure/component tests using disposable local task/run artifacts.
These tests exercise regression-only invariants for managed-Issue navigation,
state classification, SSE fingerprints, and visually distinct state colors.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


VIEW_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = VIEW_ROOT / "server.py"
INDEX_PATH = VIEW_ROOT / "index.html"
EXPECTED_REPOSITORY = "fixture-owner/pipeline-rehearsal"
EXPECTED_ISSUE_URL = (
    "https://github.com/fixture-owner/pipeline-rehearsal/issues/112"
)
EXPECTED_PR_URL = (
    "https://github.com/fixture-owner/pipeline-rehearsal/pull/116"
)

SPEC = importlib.util.spec_from_file_location("gauntlet_view_server", SERVER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {SERVER_PATH}")
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8", newline="\n")


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events),
        encoding="utf-8",
        newline="\n",
    )


def event(
    kind: str,
    fields: dict | None = None,
    *,
    message: str | None = None,
    timestamp: str = "2026-09-07T01:00:00Z",
    elapsed_seconds: float | None = None,
) -> dict:
    value = {
        "event": kind,
        "fields": fields or {},
        "message": message or kind.replace("_", " "),
        "timestamp_utc": timestamp,
        "worker_id": "worker-a",
    }
    if elapsed_seconds is not None:
        value["elapsed_seconds"] = elapsed_seconds
    return value


class Fixture:
    def __init__(self) -> None:
        temporary_root = Path(
            os.getenv("NSC_GAUNTLET_VIEW_TEST_TEMP") or tempfile.gettempdir()
        )
        self.root = temporary_root / f"gauntlet-view-test-{uuid.uuid4().hex}"
        # tempfile.TemporaryDirectory requests mode 0700. Python 3.13 maps that
        # to a restrictive Windows ACL that sandboxed child writes cannot use,
        # so create the disposable directory with the platform default mode.
        self.root.mkdir(parents=True)
        self.tasks = self.root / "checkout" / "Tasks"
        self.tasks.mkdir(parents=True)
        self.state = self.root / "state"
        self.run = (
            self.state
            / ".task-review-agent"
            / "autonomous-runs"
            / "repository-id"
            / "run-a"
        )
        self.write_manifest(EXPECTED_REPOSITORY)
        write_json(self.run / "progress.json", {"poll_cycles_total": 1})
        write_jsonl(self.run / "events.jsonl", [])

    def close(self) -> None:
        shutil.rmtree(self.root)

    def write_manifest(self, repository: object) -> None:
        write_json(
            self.run / "manifest.json",
            {
                "run_id": "run-a",
                "github_repository": repository,
                "target_task_ids": ["NSC-112"],
                "excluded_task_ids": [],
                "max_capacity": 3,
            },
        )

    def write_scheduler_events(self, events: list[dict]) -> None:
        write_jsonl(self.run / "events.jsonl", events)

    @staticmethod
    def agent_ready_event(task_id: str = "NSC-112") -> dict:
        return {
            "event": "local_resume_hint_send_completed",
            "timestamp_utc": "2026-09-07T02:00:00Z",
            "task_id": task_id,
            "workflow_transition": {
                "from_state": "human_action_required",
                "from_phase": "unity_runtime_validation",
                "to_state": "agent_ready",
                "to_phase": "delivery_evidence",
            },
        }

    @staticmethod
    def gate_event(queued_task_ids: list[str]) -> dict:
        return {
            "event": "integration_gate_observed",
            "timestamp_utc": "2026-09-07T02:01:00Z",
            "gate_ref": "refs/nsc/integration-gate",
            "owner": "NSC-701",
            "queued_task_ids": queued_task_ids,
            "next_task_id": queued_task_ids[0] if queued_task_ids else None,
        }

    def add_task(
        self,
        task_id: str = "NSC-112",
        *,
        progress_events: list[dict] | None = None,
        run_result: dict | None = None,
        parent: str | None = None,
        ci_snapshot: dict | None = None,
    ) -> tuple[Path, Path]:
        write_json(
            self.tasks / f"{task_id}.yaml",
            {
                "id": task_id,
                "title": f"Task {task_id}",
                "parent": parent,
                "depends_on": [],
                "kind": "implementation",
                "contract_disposition": "active",
                "decomposition_state": "concrete",
                "execution_scope": "single_agent",
                "exclusive_resources": [],
                "acceptance_criteria": [],
                "provenance": {"wave": 1, "column": 1},
            },
        )
        return self.add_worker_run(
            task_id,
            "worker-run-a",
            progress_events=progress_events,
            run_result=run_result,
            ci_snapshot=ci_snapshot,
            mtime=1_788_745_600,
        )

    def add_worker_run(
        self,
        task_id: str,
        run_id: str,
        *,
        progress_events: list[dict] | None = None,
        run_result: dict | None = None,
        ci_snapshot: dict | None = None,
        mtime: float,
    ) -> tuple[Path, Path]:
        run_dir = self.state / ".task-review-agent" / "outputs" / task_id / run_id
        progress = run_dir / "progress.jsonl"
        write_jsonl(progress, progress_events or [event("run_started")])
        os.utime(progress, (mtime, mtime))
        if run_result is not None:
            write_json(run_dir / "run_result.json", run_result)
            os.utime(run_dir / "run_result.json", (mtime, mtime))
        if ci_snapshot is not None:
            write_json(run_dir / "ci_snapshot.json", ci_snapshot)
            os.utime(run_dir / "ci_snapshot.json", (mtime, mtime))
        return run_dir, progress

    def task(self, task_id: str = "NSC-112") -> dict:
        snapshot = server.Snapshot(self.tasks, self.state).build()
        return next(task for task in snapshot["tasks"] if task["id"] == task_id)

    def snapshot(self):
        return server.Snapshot(self.tasks, self.state)


def usage_event(
    *,
    turn: int,
    provider: str,
    model: str,
    role: str = "task_supervisor",
    usage: dict | None,
    status: str = "succeeded",
    session_id: str | None = None,
) -> dict:
    fields: dict = {
        "turn": turn,
        "action": "search_repository",
        "provider": provider,
        "model": model,
        "role": role,
        "provider_call_status": status,
    }
    if usage is not None:
        fields["provider_usage"] = usage
    if session_id is not None:
        fields["provider_session"] = {
            "warm_pooling_active": True,
            "confirmed_session_id": session_id,
            "provider": provider,
        }
    return event("supervisor_decision", fields)


class GauntletViewIssueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_active_task_discovers_result_issue_number(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("run_started"),
                event("action_completed", {"result_issue_number": 112}),
            ]
        )
        task = self.fixture.task()
        self.assertEqual(task["state"], "active")
        self.assertEqual(task["worker"]["issue_number"], 112)
        self.assertEqual(task["worker"]["issue_url"], EXPECTED_ISSUE_URL)

    def test_all_canonical_progress_issue_fields_are_recognized(self) -> None:
        cases = (
            ("issue_number", 112),
            ("result_issue_number", 112),
            ("issue_url", EXPECTED_ISSUE_URL),
            ("result_issue_url", EXPECTED_ISSUE_URL),
        )
        for field_name, value in cases:
            with self.subTest(field=field_name):
                self.fixture.add_task(
                    progress_events=[event("state_observed", {field_name: value})]
                )
                worker = self.fixture.task()["worker"]
                self.assertEqual(worker["issue_number"], 112)
                self.assertEqual(worker["issue_url"], EXPECTED_ISSUE_URL)

    def test_human_action_task_exposes_exact_issue_url(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {
                    "status": "human_action_required",
                    "issue_url": EXPECTED_ISSUE_URL,
                }),
                event("run_finished", {"status": "human_action_required"}),
            ]
        )
        task = self.fixture.task()
        self.assertEqual(task["state"], "human_action")
        self.assertEqual(task["worker"]["issue_number"], 112)
        self.assertEqual(task["worker"]["issue_url"], EXPECTED_ISSUE_URL)

    def test_run_result_supplies_issue_after_progress_event_falls_outside_tail(self) -> None:
        early = event("state_observed", {"issue_number": 999})
        filler = [event("heartbeat", {"padding": "x" * 1800}) for _ in range(60)]
        terminal = [
            event("terminal_state", {"status": "complete"}),
            event("run_finished", {"status": "complete"}),
        ]
        run_dir, progress = self.fixture.add_task(
            progress_events=[early, *filler, *terminal],
            run_result={"issue_number": 112},
        )
        self.assertGreater(progress.stat().st_size, server.TAIL_BYTES)
        tail = server.read_jsonl_tail(progress)
        self.assertFalse(any(item.get("fields", {}).get("issue_number") == 999 for item in tail))
        self.assertTrue((run_dir / "run_result.json").is_file())
        task = self.fixture.task()
        self.assertEqual(task["worker"]["issue_number"], 112)
        self.assertEqual(task["worker"]["issue_url"], EXPECTED_ISSUE_URL)

    def test_completed_task_retains_issue_link(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {"status": "complete"}),
                event("run_finished", {"status": "complete"}),
            ],
            run_result={"issue_number": 112},
        )
        task = self.fixture.task()
        self.assertEqual(task["state"], "complete")
        self.assertEqual(task["worker"]["issue_url"], EXPECTED_ISSUE_URL)

    def test_missing_issue_evidence_does_not_invent_url(self) -> None:
        self.fixture.add_task()
        worker = self.fixture.task()["worker"]
        self.assertIsNone(worker["issue_number"])
        self.assertIsNone(worker["issue_url"])

    def test_invalid_repository_slugs_are_rejected(self) -> None:
        invalid = (
            "fixture-owner",
            "fixture-owner/repo/extra",
            "https://github.com/fixture-owner/repo",
            "fixture-owner/../repo",
            "fixture-owner/repo?tab=issues",
            "fixture-owner//repo",
            112,
        )
        for repository in invalid:
            with self.subTest(repository=repository):
                self.fixture.write_manifest(repository)
                self.fixture.add_task(
                    progress_events=[event("state_observed", {"issue_number": 112})]
                )
                worker = self.fixture.task()["worker"]
                self.assertIsNone(worker["issue_url"])

    def test_invalid_issue_numbers_are_rejected(self) -> None:
        invalid = (0, -1, 1.5, "112", True, None)
        for issue_number in invalid:
            with self.subTest(issue_number=issue_number):
                self.fixture.add_task(
                    progress_events=[event("state_observed", {"issue_number": issue_number})],
                    run_result={"issue_number": issue_number},
                )
                worker = self.fixture.task()["worker"]
                self.assertIsNone(worker["issue_number"])
                self.assertIsNone(worker["issue_url"])

    def test_hostile_artifact_urls_cannot_become_href(self) -> None:
        hostile_urls = (
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "https://evil.example/issues/112",
            "https://github.com/fixture-owner/Other/issues/112",
            EXPECTED_ISSUE_URL + '?next=" onmouseover="alert(1)',
        )
        html = INDEX_PATH.read_text(encoding="utf-8")
        for hostile_url in hostile_urls:
            with self.subTest(url=hostile_url):
                self.fixture.add_task(
                    progress_events=[event("terminal_state", {
                        "status": "human_action_required",
                        "issue_url": hostile_url,
                    })]
                )
                worker = self.fixture.task()["worker"]
                self.assertIsNone(worker["issue_url"])
                self.assertNotIn(f'href="{hostile_url}"', html)

    def test_exact_issue_112_url(self) -> None:
        self.fixture.add_task(
            progress_events=[event("state_observed", {"issue_number": 112})]
        )
        self.assertEqual(self.fixture.task()["worker"]["issue_url"], EXPECTED_ISSUE_URL)

    def test_hostile_pull_request_url_is_never_exposed(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event(
                    "state_observed",
                    {
                        "phase": "merge_closeout",
                        "pull_request_url": "javascript:alert(1)",
                    },
                ),
                event("pipeline_action_started", {"action": "inspect_or_merge_pull_request"}),
            ]
        )
        worker = self.fixture.task()["worker"]
        self.assertIsNone(worker["pull_request_number"])
        self.assertIsNone(worker["pull_request_url"])

    def test_exact_pull_request_url_is_reconstructed_from_local_evidence(self) -> None:
        self.fixture.add_task(
            progress_events=[event("state_observed", {"pull_request_number": 116})]
        )
        self.assertEqual(self.fixture.task()["worker"]["pull_request_url"], EXPECTED_PR_URL)


class GauntletViewStateAndSseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_existing_terminal_state_classification_is_unchanged(self) -> None:
        cases = {
            "complete": "complete",
            "checks_pending": "checks_pending",
            "human_action_required": "human_action",
            "human_revalidation_required": "human_action",
            "blocked": "blocked",
            "failed": "failed",
        }
        for index, (terminal, expected) in enumerate(cases.items(), start=112):
            task_id = f"NSC-{index}"
            self.fixture.add_task(
                task_id,
                progress_events=[
                    event("terminal_state", {"status": terminal}),
                    event("run_finished", {"status": terminal}),
                ],
            )
            self.assertEqual(self.fixture.task(task_id)["state"], expected)

    def test_existing_progress_change_updates_sse_fingerprint(self) -> None:
        _, progress = self.fixture.add_task()
        snapshot = self.fixture.snapshot()
        before = snapshot.fingerprint()
        with progress.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event("state_observed", {"turn": 2})) + "\n")
        self.assertNotEqual(snapshot.fingerprint(), before)

    def test_current_autonomous_run_does_not_reuse_stale_worker_terminal_state(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {"status": "blocked"}),
                event("run_finished", {"status": "blocked"}),
            ]
        )
        self.fixture.write_scheduler_events(
            [
                {
                    "event": "poll_started",
                    "timestamp_utc": "2026-09-07T02:00:00Z",
                    "active_worker_count": 0,
                },
                {
                    "event": "architect_started",
                    "timestamp_utc": "2026-09-07T02:00:01Z",
                    "eligible_pairs": [
                        {"task_id": "NSC-112", "work_types": ["implementation"]}
                    ],
                },
            ]
        )

        task = self.fixture.task()

        self.assertEqual(task["state"], "ready")
        self.assertIsNone(task["worker"])
        self.assertIsNone(task["progress"]["attempt"])

    def test_current_autonomous_run_uses_only_its_exact_launched_worker(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {"status": "blocked"}),
                event("run_finished", {"status": "blocked"}),
            ]
        )
        self.fixture.add_worker_run(
            "NSC-112",
            "current-worker",
            progress_events=[
                event("state_observed", {"phase": "implementation", "turn": 1}),
                event("pipeline_action_started", {"action": "implement_task", "turn": 1}),
            ],
            mtime=1_788_745_700,
        )
        self.fixture.write_scheduler_events(
            [
                {
                    "event": "poll_started",
                    "timestamp_utc": "2026-09-07T02:00:00Z",
                    "active_worker_count": 0,
                },
                {
                    "event": "worker_launched",
                    "timestamp_utc": "2026-09-07T02:00:01Z",
                    "task_id": "NSC-112",
                    "run_id": "current-worker",
                    "worker_id": "worker-current",
                },
            ]
        )

        task = self.fixture.task()

        self.assertEqual(task["state"], "active")
        self.assertEqual(task["worker"]["run_id"], "current-worker")
        self.assertEqual(task["progress"]["attempt"], 1)

    def test_available_decomposition_has_distinct_state_and_node_label(self) -> None:
        self.fixture.add_task(
            progress_events=[event("run_finished", {"status": "stopped"})]
        )
        contract_path = self.fixture.tasks / "NSC-112.yaml"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["execution_scope"] = "needs_execution_decomposition"
        write_json(contract_path, contract)

        task = self.fixture.task()

        self.assertEqual(task["state"], "decomposition_ready")
        self.assertEqual(task["node_lines"], ["DECOMPOSITION AVAILABLE"])

    def test_active_decomposition_launch_outranks_same_second_finished_artifact(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("run_finished", {"status": "stopped"}, timestamp="2026-09-07T01:00:00Z")
            ]
        )
        contract_path = self.fixture.tasks / "NSC-112.yaml"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["execution_scope"] = "needs_execution_decomposition"
        write_json(contract_path, contract)
        self.fixture.write_scheduler_events(
            [
                {
                    "event": "worker_launched",
                    "timestamp_utc": "2026-09-07T01:00:00Z",
                    "task_id": "NSC-112",
                    "run_id": "worker-run-a",
                    "worker_id": "worker-a",
                    "work_type": "decomposition",
                }
            ]
        )

        task = self.fixture.task()

        self.assertEqual(task["state"], "active")
        self.assertEqual(task["worker"]["phase"], "decomposition")
        self.assertIn("DECOMPOSING", "\n".join(task["node_lines"]))
        self.assertNotIn("DECOMPOSITION AVAILABLE", task["node_lines"])

    def test_deterministic_decomposition_apply_uses_exact_scheduler_phase(self) -> None:
        self.fixture.add_task(
            progress_events=[event("run_started", timestamp="2026-09-07T01:00:02Z")]
        )
        self.fixture.write_scheduler_events(
            [
                {
                    "event": "local_resume_hint_send_completed",
                    "timestamp_utc": "2026-09-07T01:00:00Z",
                    "task_id": "NSC-112",
                    "workflow_transition": {
                        "from_state": "human_action_required",
                        "from_phase": "decomposition_apply_authorization",
                        "to_state": "agent_ready",
                        "to_phase": "decomposition_apply",
                    },
                },
                {
                    "event": "integration_gate_resume_admitted",
                    "timestamp_utc": "2026-09-07T01:00:01Z",
                    "task_id": "NSC-112",
                    "resume_phase": "decomposition_apply",
                },
                {
                    "event": "worker_launched",
                    "timestamp_utc": "2026-09-07T01:00:02Z",
                    "task_id": "NSC-112",
                    "run_id": "worker-run-a",
                    "worker_id": "worker-a",
                    "work_type": "implementation",
                },
            ]
        )

        task = self.fixture.task()

        self.assertEqual(task["state"], "active")
        self.assertEqual(task["worker"]["phase"], "decomposition_apply")
        self.assertEqual(task["progress"]["phase"], "decomposition_apply")
        self.assertIn("DECOMPOSING", "\n".join(task["node_lines"]))
        self.assertNotIn("PHASE UNAVAILABLE", "\n".join(task["node_lines"]))

    def test_ordinary_available_work_remains_ready(self) -> None:
        self.fixture.add_task(
            progress_events=[event("run_finished", {"status": "stopped"})]
        )

        task = self.fixture.task()

        self.assertEqual(task["state"], "ready")

    def test_only_exact_decomposition_contract_is_visually_distinguished(self) -> None:
        self.fixture.add_task(
            progress_events=[event("run_finished", {"status": "stopped"})]
        )
        contract_path = self.fixture.tasks / "NSC-112.yaml"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["execution_scope"] = "needs_execution_decomposition"
        contract["decomposition_state"] = "decomposed"
        write_json(contract_path, contract)

        task = self.fixture.task()
        self.assertEqual(task["state"], "aggregate")
        self.assertEqual(task["progress"]["children_total"], 0)

    def test_decomposed_parent_is_aggregate_with_exact_child_rollup(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {"phase": "implementation", "turn": 2}),
                event("pipeline_action_started", {"action": "implement_task"}),
            ]
        )
        parent_path = self.fixture.tasks / "NSC-112.yaml"
        parent = json.loads(parent_path.read_text(encoding="utf-8"))
        parent["decomposition_state"] = "decomposed"
        parent["decomposition_children"] = ["NSC-113", "NSC-114"]
        write_json(parent_path, parent)
        self.fixture.add_task(
            "NSC-113",
            parent="NSC-112",
            progress_events=[
                usage_event(
                    turn=1,
                    provider="codex",
                    model="gpt-fixture",
                    usage={
                        "input_tokens": 100,
                        "output_tokens": 25,
                        "total_tokens": 125,
                        "estimated_cost_usd": 0.01,
                    },
                ),
                event("state_observed", {"phase": "implementation", "turn": 2}),
            ],
        )
        self.fixture.add_task(
            "NSC-114",
            parent="NSC-112",
            progress_events=[
                event("terminal_state", {"status": "human_action_required"}),
                event("run_finished", {"status": "human_action_required"}),
            ],
        )

        state = self.fixture.snapshot().build()
        by_id = {task["id"]: task for task in state["tasks"]}
        aggregate = by_id["NSC-112"]

        self.assertEqual(aggregate["state"], "aggregate")
        self.assertEqual(aggregate["progress"]["children_total"], 2)
        self.assertEqual(aggregate["progress"]["children_complete"], 0)
        self.assertEqual(
            aggregate["progress"]["children_by_state"],
            {"active": 1, "human_action": 1},
        )
        self.assertEqual(
            aggregate["progress"]["children_recorded_total_tokens"],
            125,
        )
        self.assertEqual(by_id["NSC-113"]["state"], "active")
        self.assertEqual(by_id["NSC-114"]["state"], "human_action")
        self.assertIn("0/2 children complete", aggregate["node_lines"][1])

    def test_agent_ready_delivery_without_gate_snapshot_is_not_unstarted(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {"status": "human_action_required"}),
                event("run_finished", {"status": "human_action_required"}),
            ]
        )
        self.fixture.write_scheduler_events([self.fixture.agent_ready_event()])

        task = self.fixture.task()

        self.assertEqual(task["state"], "delivery_ready")
        self.assertNotEqual(task["state"], "ready")

    def test_run_result_change_updates_sse_fingerprint(self) -> None:
        run_dir, _ = self.fixture.add_task()
        snapshot = self.fixture.snapshot()
        before = snapshot.fingerprint()
        write_json(run_dir / "run_result.json", {"issue_number": 112})
        self.assertNotEqual(snapshot.fingerprint(), before)

    def seed_human_action_then_agent_ready_queue(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {"status": "human_action_required"}),
                event("run_finished", {"status": "human_action_required"}),
            ]
        )
        self.fixture.write_scheduler_events(
            [
                self.fixture.agent_ready_event(),
                self.fixture.gate_event(["NSC-112"]),
            ]
        )

    def test_human_action_followed_by_agent_ready_displays_integration_queued(self) -> None:
        self.seed_human_action_then_agent_ready_queue()
        self.assertEqual(self.fixture.task()["state"], "integration_queued")

    def test_queued_work_is_not_displayed_as_task_needs_you(self) -> None:
        self.seed_human_action_then_agent_ready_queue()
        self.assertNotEqual(self.fixture.task()["state"], "human_action")

    def test_queued_work_is_not_in_ci_without_checks_pending_evidence(self) -> None:
        self.seed_human_action_then_agent_ready_queue()
        self.assertNotEqual(self.fixture.task()["state"], "checks_pending")
        self.assertEqual(self.fixture.task()["state"], "integration_queued")

    def test_gate_release_and_worker_launch_changes_queue_to_active(self) -> None:
        self.seed_human_action_then_agent_ready_queue()
        self.assertEqual(self.fixture.task()["state"], "integration_queued")
        self.fixture.write_scheduler_events(
            [
                self.fixture.agent_ready_event(),
                self.fixture.gate_event([]),
                {
                    "event": "worker_launched",
                    "timestamp_utc": "2026-09-07T02:02:00Z",
                    "task_id": "NSC-112",
                    "worker_id": "worker-b",
                },
            ]
        )
        self.assertEqual(self.fixture.task()["state"], "active")

    def test_completed_state_cannot_regress_because_of_older_worker_event(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event(
                    "terminal_state",
                    {"status": "complete"},
                    timestamp="2026-09-07T03:00:00Z",
                ),
                event(
                    "run_finished",
                    {"status": "complete"},
                    timestamp="2026-09-07T03:00:01Z",
                ),
            ]
        )
        self.fixture.write_scheduler_events(
            [
                {
                    "event": "worker_launched",
                    "timestamp_utc": "2026-09-07T00:59:00Z",
                    "task_id": "NSC-112",
                    "worker_id": "worker-old",
                }
            ]
        )
        self.assertEqual(self.fixture.task()["state"], "complete")

    def test_newer_agent_ready_queue_overrides_stale_checks_pending(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {"status": "checks_pending"}),
                event("run_finished", {"status": "checks_pending"}),
            ]
        )
        self.fixture.write_scheduler_events(
            [
                self.fixture.agent_ready_event(),
                self.fixture.gate_event(["NSC-112"]),
            ]
        )
        self.assertEqual(self.fixture.task()["state"], "integration_queued")

    def test_ci_snapshot_change_updates_sse_fingerprint(self) -> None:
        run_dir, _ = self.fixture.add_task()
        snapshot = self.fixture.snapshot()
        before = snapshot.fingerprint()
        write_json(
            run_dir / "ci_snapshot.json",
            {
                "schema_version": "1.0",
                "task_id": "NSC-112",
                "run_id": "worker-run-a",
                "repository": EXPECTED_REPOSITORY,
                "pull_request_number": 116,
                "observed_at_utc": "2026-09-07T01:00:00Z",
                "checks": [{"name": "windows-core", "status": "IN_PROGRESS"}],
            },
        )
        self.assertNotEqual(snapshot.fingerprint(), before)

    def test_taskgraph_conformance_is_authoritative_for_completion(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {"status": "failed"}),
                event("run_finished", {"status": "failed"}),
            ]
        )
        authoritative = {
            "NSC-112": {
                "state": "conformant",
                "selected_record_id": "DEL-NSC-112-example",
                "total_tokens_used": 318_400,
                "token_usage_complete": True,
                "token_usage_status": "complete",
                "token_usage_scope": "through_delivery_evidence",
            }
        }
        with mock.patch.object(
            server.Snapshot,
            "taskgraph_states",
            return_value=(True, authoritative),
        ):
            task = self.fixture.task()
        self.assertEqual(task["state"], "complete")
        self.assertEqual(task["token_cost"]["recorded_total_tokens"], 318_400)
        self.assertEqual(
            task["token_cost"]["token_source"],
            "committed TaskGraph token-usage.json",
        )

    def test_worker_complete_is_not_authoritative_when_taskgraph_disagrees(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {"status": "complete"}),
                event("run_finished", {"status": "complete"}),
            ]
        )
        with mock.patch.object(
            server.Snapshot,
            "taskgraph_states",
            return_value=(True, {"NSC-112": {"state": "not_delivered"}}),
        ):
            task = self.fixture.task()
        self.assertEqual(task["state"], "ready")

    def seed_nsc_929_pr_monitor(self, *, include_pr: bool = True) -> None:
        fields = {
            "issue_state": "agent_working",
            "phase": "merge_closeout",
            "turn": 4,
            "issue_number": 113,
        }
        if include_pr:
            fields["pull_request_url"] = EXPECTED_PR_URL
        self.fixture.add_task(
            "NSC-701",
            progress_events=[
                event("state_observed", fields),
                event(
                    "supervisor_decision",
                    {"turn": 4, "action": "inspect_or_merge_pull_request"},
                    timestamp="2026-09-07T01:00:01Z",
                ),
                event(
                    "pipeline_action_started",
                    {"turn": 4, "action": "inspect_or_merge_pull_request"},
                    timestamp="2026-09-07T01:00:02Z",
                ),
            ],
        )
        self.fixture.write_scheduler_events(
            [
                {
                    "event": "worker_launched",
                    "timestamp_utc": "2026-09-07T00:59:00Z",
                    "task_id": "NSC-701",
                    "worker_id": "worker-a",
                }
            ]
        )

    def test_active_pr_monitor_projects_as_checks_pending(self) -> None:
        self.seed_nsc_929_pr_monitor()
        task = self.fixture.task("NSC-701")
        self.assertEqual(task["state"], "checks_pending")
        self.assertEqual(task["worker"]["pull_request_url"], EXPECTED_PR_URL)

    def test_ci_node_retains_active_worker_and_turn_information(self) -> None:
        self.seed_nsc_929_pr_monitor()
        worker = self.fixture.task("NSC-701")["worker"]
        self.assertIs(worker["active"], True)
        self.assertIs(worker["monitoring_ci"], True)
        self.assertEqual(worker["turn"], 4)

    def test_generic_active_implementation_remains_working(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {"phase": "implementation", "turn": 2}),
                event("pipeline_action_started", {"action": "implement_task", "turn": 2}),
            ]
        )
        self.assertEqual(self.fixture.task()["state"], "active")

    def test_later_completion_overrides_earlier_ci_evidence(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {
                    "phase": "merge_closeout",
                    "pull_request_url": EXPECTED_PR_URL,
                }),
                event("pipeline_action_started", {
                    "action": "inspect_or_merge_pull_request",
                }),
                event(
                    "action_completed",
                    {
                        "action": "inspect_or_merge_pull_request",
                        "result_summary": {"status": "merged"},
                    },
                    timestamp="2026-09-07T01:00:03Z",
                ),
                event(
                    "terminal_state",
                    {"status": "complete"},
                    timestamp="2026-09-07T01:00:04Z",
                ),
                event(
                    "run_finished",
                    {"status": "complete"},
                    timestamp="2026-09-07T01:00:05Z",
                ),
            ]
        )
        self.assertEqual(self.fixture.task()["state"], "complete")

    def test_later_failure_or_human_action_overrides_earlier_ci_evidence(self) -> None:
        for terminal, expected in (
            ("failed", "failed"),
            ("human_action_required", "human_action"),
        ):
            with self.subTest(terminal=terminal):
                self.fixture.add_task(
                    progress_events=[
                        event("state_observed", {
                            "phase": "merge_closeout",
                            "pull_request_url": EXPECTED_PR_URL,
                        }),
                        event("pipeline_action_started", {
                            "action": "inspect_or_merge_pull_request",
                        }),
                        event(
                            "terminal_state",
                            {"status": terminal},
                            timestamp="2026-09-07T01:00:04Z",
                        ),
                        event(
                            "run_finished",
                            {"status": terminal},
                            timestamp="2026-09-07T01:00:05Z",
                        ),
                    ]
                )
                self.assertEqual(self.fixture.task()["state"], expected)

    def test_later_repair_work_overrides_stale_ci_evidence(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {
                    "phase": "merge_closeout",
                    "pull_request_url": EXPECTED_PR_URL,
                }),
                event("pipeline_action_started", {
                    "action": "inspect_or_merge_pull_request",
                }),
                event(
                    "supervisor_decision",
                    {"action": "prepare_task_checkout", "turn": 5},
                    timestamp="2026-09-07T01:00:04Z",
                ),
                event(
                    "pipeline_action_started",
                    {"action": "prepare_task_checkout", "turn": 5},
                    timestamp="2026-09-07T01:00:05Z",
                ),
            ]
        )
        self.assertEqual(self.fixture.task()["state"], "active")

    def test_previous_checks_pending_run_supports_new_active_pr_monitor(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {
                    "status": "checks_pending",
                    "pull_request_url": EXPECTED_PR_URL,
                }),
                event("run_finished", {"status": "checks_pending"}),
            ]
        )
        self.fixture.add_worker_run(
            "NSC-112",
            "worker-run-b",
            progress_events=[
                event("state_observed", {
                    "phase": "merge_closeout",
                    "turn": 3,
                    "issue_number": 112,
                }),
                event("pipeline_action_started", {
                    "action": "inspect_or_merge_pull_request",
                    "turn": 3,
                }),
            ],
            mtime=1_788_745_700,
        )
        task = self.fixture.task()
        self.assertEqual(task["state"], "checks_pending")
        self.assertEqual(task["worker"]["pull_request_url"], EXPECTED_PR_URL)
        self.assertIs(task["worker"]["active"], True)

    def test_no_pr_evidence_does_not_classify_arbitrary_active_work_as_ci(self) -> None:
        self.seed_nsc_929_pr_monitor(include_pr=False)
        self.assertEqual(self.fixture.task("NSC-701")["state"], "active")

    def test_current_checks_pending_result_projects_as_ci(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {
                    "phase": "merge_closeout",
                    "pull_request_url": EXPECTED_PR_URL,
                }),
                event("action_completed", {
                    "action": "inspect_or_merge_pull_request",
                    "result_summary": {"status": "checks_pending"},
                }),
            ]
        )
        self.assertEqual(self.fixture.task()["state"], "checks_pending")

    def test_newer_workflow_human_action_overrides_older_ci(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {"status": "checks_pending"}),
                event("run_finished", {"status": "checks_pending"}),
            ]
        )
        self.fixture.write_scheduler_events(
            [
                {
                    "event": "workflow_transition_observed",
                    "timestamp_utc": "2026-09-07T02:00:00Z",
                    "task_id": "NSC-112",
                    "workflow_transition": {
                        "from_state": "agent_working",
                        "from_phase": "merge_closeout",
                        "to_state": "human_action_required",
                        "to_phase": "unity_runtime_validation",
                    },
                }
            ]
        )
        self.assertEqual(self.fixture.task()["state"], "human_action")


class GauntletViewCompactProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()

    def tearDown(self) -> None:
        self.fixture.close()

    @staticmethod
    def ci_checks() -> list[dict]:
        return [
            {
                "name": "checkout-root-policy",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "name": "windows-smoke",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "name": "windows-core",
                "status": "IN_PROGRESS",
                "conclusion": None,
                "step": "Core tests",
            },
        ]

    def test_ci_node_has_check_counts_and_running_check_before_click(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {
                    "phase": "merge_closeout",
                    "pull_request_url": EXPECTED_PR_URL,
                }),
                event(
                    "pipeline_action_heartbeat",
                    {"action": "inspect_or_merge_pull_request", "turn": 6},
                    elapsed_seconds=360,
                ),
            ],
            ci_snapshot={
                "schema_version": "1.0",
                "task_id": "NSC-112",
                "run_id": "worker-run-a",
                "repository": EXPECTED_REPOSITORY,
                "pull_request_number": 116,
                "observed_at_utc": "2026-09-07T01:00:00Z",
                "checks": self.ci_checks(),
            },
        )
        task = self.fixture.task()
        self.assertEqual(task["state"], "checks_pending")
        rendered = "\n".join(task["node_lines"])
        self.assertIn("IN CI · 2/3 checks passed", rendered)
        self.assertIn("windows-core: Core tests", rendered)

    def test_active_implementation_shows_phase_action_and_elapsed(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {"phase": "implementation", "turn": 6}),
                event(
                    "pipeline_action_heartbeat",
                    {"action": "run_execution_crew", "turn": 6},
                    elapsed_seconds=420,
                ),
            ]
        )
        with mock.patch.object(server.time, "time", return_value=1788743220):
            rendered = "\n".join(self.fixture.task()["node_lines"])
        self.assertNotIn("Stage 3/6", rendered)
        self.assertIn("ExecutionCrew", rendered)
        self.assertIn("IMPLEMENT / IMPLEMENTING", rendered)
        self.assertIn("7m", rendered)
        self.assertIn("turn 6", rendered)

    def test_active_node_clocks_use_durable_stage_and_task_start_timestamps(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("run_started", timestamp="2026-09-07T00:59:00Z", elapsed_seconds=9999),
                event(
                    "state_observed",
                    {"phase": "waiting", "turn": 1},
                    timestamp="2026-09-07T01:00:00Z",
                    elapsed_seconds=9999,
                ),
                event(
                    "state_observed",
                    {"phase": "checkout_preparation", "turn": 1},
                    timestamp="2026-09-07T01:01:00Z",
                    elapsed_seconds=9999,
                ),
                event(
                    "state_observed",
                    {"phase": "implementation", "turn": 2},
                    timestamp="2026-09-07T01:02:00Z",
                    elapsed_seconds=9999,
                ),
                event(
                    "pipeline_action_started",
                    {"action": "run_execution_crew", "turn": 2},
                    timestamp="2026-09-07T01:02:00Z",
                    elapsed_seconds=9999,
                ),
            ]
        )

        with mock.patch.object(server.time, "time", return_value=1788743100):
            task = self.fixture.task()

        self.assertEqual(task["progress"]["durable_stage_elapsed_seconds"], 180)
        self.assertEqual(task["progress"]["durable_task_elapsed_seconds"], 360)
        stages = task["progress"]["pipeline_stages"]
        self.assertEqual([stage["label"] for stage in stages], [
            "WAITING", "CHECKOUT", "IMPLEMENT", "VALIDATE", "EVIDENCE", "CI",
        ])
        self.assertEqual(
            [(stage["status"], stage["elapsed_seconds"]) for stage in stages],
            [
                ("complete", 60),
                ("complete", 60),
                ("active", 180),
                ("future", None),
                ("future", None),
                ("future", None),
            ],
        )
        rendered = "\n".join(task["node_lines"])
        self.assertIn("IMPLEMENT / IMPLEMENTING", rendered)
        self.assertEqual(task["node_heading"], "NSC-112 · TOTAL TASK 6m")
        self.assertIn("CURRENT STAGE 3m", task["node_summary_lines"][0])

    def test_active_execution_crew_roles_have_ordered_durable_receipt_details(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("run_started", timestamp="2026-09-07T01:00:00Z"),
                event("state_observed", {"phase": "implementation"}, timestamp="2026-09-07T01:01:00Z"),
                event(
                    "pipeline_action_started",
                    {"action": "run_execution_crew"},
                    timestamp="2026-09-07T01:01:00Z",
                ),
            ]
        )
        checkout = self.fixture.state / "NSC-112"
        crew = checkout / "Pipeline" / "ExecutionCrew" / "outputs" / "crew-current"
        write_jsonl(
            crew / "progress.jsonl",
            [
                {"event": "run_started", "timestamp_utc": "2026-09-07T01:01:01Z", "run_id": "crew-current", "task_id": "NSC-112", "provider": "codex", "required_roles": ["implementer", "test_author", "validator"]},
                {"event": "role_started", "timestamp_utc": "2026-09-07T01:02:00Z", "run_id": "crew-current", "task_id": "NSC-112", "provider": "codex", "role": "implementer", "attempt": 1},
                {"event": "role_completed", "timestamp_utc": "2026-09-07T01:03:29Z", "run_id": "crew-current", "task_id": "NSC-112", "provider": "codex", "role": "implementer", "attempt": 1, "status": "succeeded"},
                {"event": "role_started", "timestamp_utc": "2026-09-07T01:03:30Z", "run_id": "crew-current", "task_id": "NSC-112", "provider": "codex", "role": "test_author", "attempt": 1},
                {"event": "role_completed", "timestamp_utc": "2026-09-07T01:09:18Z", "run_id": "crew-current", "task_id": "NSC-112", "provider": "codex", "role": "test_author", "attempt": 1, "status": "succeeded"},
                {"event": "role_started", "timestamp_utc": "2026-09-07T01:09:19Z", "run_id": "crew-current", "task_id": "NSC-112", "provider": "codex", "role": "validator", "attempt": 1},
            ],
        )
        write_json(
            crew / "role_results" / "implementer_1.json",
            {
                "role": "implementer",
                "attempt": 1,
                "provider": "codex",
                "model": "gpt-fixture",
                "usage": {"total_tokens": 1234, "estimated_cost_usd": 0.125},
            },
        )
        self.fixture.write_scheduler_events(
            [
                {
                    "event": "worker_launched",
                    "timestamp_utc": "2026-09-07T01:00:00Z",
                    "task_id": "NSC-112",
                    "run_id": "worker-run-a",
                    "worker_id": "worker-a",
                    "work_type": "implementation",
                    "checkout_path": str(checkout),
                }
            ]
        )

        with mock.patch.object(server.time, "time", return_value=1788743451):
            task = self.fixture.task()

        crew_agents = [agent for agent in task["progress"]["agents"] if agent["role"] != "task_supervisor"]
        self.assertEqual(
            [(agent["role"], agent["status"], agent["duration_seconds"]) for agent in crew_agents],
            [
                ("implementer", "completed", 89),
                ("test_author", "completed", 348),
                ("validator", "running", 92),
            ],
        )
        self.assertEqual(
            (crew_agents[0]["provider"], crew_agents[0]["model"], crew_agents[0]["total_tokens"], crew_agents[0]["cost_usd"]),
            ("codex", "gpt-fixture", 1234, 0.125),
        )
        self.assertIsNone(crew_agents[2]["model"])
        self.assertIsNone(crew_agents[2]["total_tokens"])
        self.assertEqual(task["progress"]["current_agent"]["role"], "validator")
        self.assertIn("CURRENT AGENT Validator", "\n".join(task["node_summary_lines"]))
        self.assertIn("1m 32s", "\n".join(task["node_summary_lines"]))
        expanded = "\n".join(task["node_lines"])
        self.assertLess(expanded.index("Implementer"), expanded.index("Test Author"))
        self.assertLess(expanded.index("Test Author"), expanded.index("Validator"))

    def test_retry_count_and_current_attempt_timing_are_separate(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {"phase": "repair"}),
                event(
                    "run_finished",
                    {"status": "failed"},
                    elapsed_seconds=60,
                ),
            ]
        )
        self.fixture.add_worker_run(
            "NSC-112",
            "worker-run-b",
            progress_events=[
                event("state_observed", {"phase": "repair"}),
                event(
                    "pipeline_action_heartbeat",
                    {"action": "run_execution_crew", "turn": 2},
                    elapsed_seconds=90,
                ),
            ],
            mtime=1_788_745_700,
        )
        progress = self.fixture.task()["progress"]
        self.assertEqual(progress["attempt"], 2)
        self.assertEqual(progress["retry_count"], 1)
        self.assertEqual(progress["current_attempt_elapsed_seconds"], 90)
        self.assertEqual(progress["stage_elapsed_seconds"], 90)
        self.assertEqual(progress["total_elapsed_seconds"], 150)

    def test_completed_task_exposes_total_duration_without_live_node_noise(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {"status": "complete"}, elapsed_seconds=872),
                event("run_finished", {"status": "complete"}, elapsed_seconds=872),
            ]
        )
        task = self.fixture.task()
        self.assertEqual(task["state"], "complete")
        self.assertEqual(task["progress"]["total_elapsed_seconds"], 872)
        self.assertNotIn("node_lines", task)

    def test_gate_waiter_has_queue_position_and_wait_duration(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("terminal_state", {"status": "human_action_required"}),
                event("run_finished", {"status": "human_action_required"}),
            ]
        )
        self.fixture.write_scheduler_events(
            [
                self.fixture.agent_ready_event(),
                self.fixture.gate_event(["NSC-112", "NSC-702"]),
            ]
        )
        task = self.fixture.task()
        self.assertEqual(task["state"], "integration_queued")
        self.assertEqual(task["progress"]["queue_position"], 1)
        self.assertGreater(task["progress"]["queue_wait_seconds"], 0)
        self.assertIn("queue position 1", "\n".join(task["node_lines"]))

    def test_insufficient_history_reports_estimate_unavailable(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {"phase": "implementation"}),
                event(
                    "pipeline_action_heartbeat",
                    {"action": "run_execution_crew"},
                    elapsed_seconds=60,
                ),
            ]
        )
        estimate = self.fixture.task()["progress"]["estimate"]
        self.assertEqual(estimate["label"], "Estimate unavailable")
        self.assertEqual(estimate["sample_count"], 0)

    def seed_duration_history(self, current_elapsed: float) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {"phase": "merge_closeout"}),
                event("pipeline_action_started", {
                    "action": "inspect_or_merge_pull_request",
                    "pull_request_url": EXPECTED_PR_URL,
                }),
                event("run_finished", {"status": "checks_pending"}, elapsed_seconds=600),
            ]
        )
        for index, duration in enumerate((720, 840), start=2):
            self.fixture.add_worker_run(
                "NSC-112",
                f"worker-run-history-{index}",
                progress_events=[
                    event("state_observed", {"phase": "merge_closeout"}),
                    event("pipeline_action_started", {
                        "action": "inspect_or_merge_pull_request",
                        "pull_request_url": EXPECTED_PR_URL,
                    }),
                    event(
                        "run_finished",
                        {"status": "checks_pending"},
                        elapsed_seconds=duration,
                    ),
                ],
                mtime=1_788_745_600 + index,
            )
        self.fixture.add_worker_run(
            "NSC-112",
            "worker-run-current",
            progress_events=[
                event("state_observed", {"phase": "merge_closeout"}),
                event(
                    "pipeline_action_heartbeat",
                    {
                        "action": "inspect_or_merge_pull_request",
                        "pull_request_url": EXPECTED_PR_URL,
                    },
                    elapsed_seconds=current_elapsed,
                ),
            ],
            mtime=1_788_745_900,
        )

    def test_adequate_history_produces_bounded_range_and_sample_count(self) -> None:
        self.seed_duration_history(300)
        estimate = self.fixture.task()["progress"]["estimate"]
        self.assertEqual(estimate["sample_count"], 3)
        self.assertGreaterEqual(estimate["remaining_high_seconds"], estimate["remaining_low_seconds"])
        self.assertIn("remaining", estimate["label"])

    def test_overlong_run_reports_unusual_duration_without_negative_eta(self) -> None:
        self.seed_duration_history(900)
        estimate = self.fixture.task()["progress"]["estimate"]
        self.assertIn("Running longer than usual", estimate["label"])
        self.assertNotIn("-", estimate["label"])
        self.assertGreaterEqual(estimate["remaining_low_seconds"], 0)

    def test_stale_local_ci_data_is_marked_without_changing_state(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {
                    "phase": "merge_closeout",
                    "pull_request_url": EXPECTED_PR_URL,
                    "checks": self.ci_checks(),
                }),
                event(
                    "pipeline_action_heartbeat",
                    {"action": "inspect_or_merge_pull_request"},
                    elapsed_seconds=360,
                ),
            ]
        )
        task = self.fixture.task()
        self.assertEqual(task["state"], "checks_pending")
        self.assertIs(task["progress"]["ci"]["stale"], True)
        self.assertIn("stale", "\n".join(task["node_lines"]).casefold())

    def test_active_decomposition_parent_reports_child_progress(self) -> None:
        self.fixture.add_task(
            "NSC-900",
            progress_events=[
                event("state_observed", {"phase": "decomposition"}),
                event(
                    "pipeline_action_heartbeat",
                    {"action": "run_decomposition"},
                    elapsed_seconds=300,
                ),
            ],
        )
        self.fixture.add_task(
            "NSC-901",
            parent="NSC-900",
            progress_events=[
                event("terminal_state", {"status": "complete"}),
                event("run_finished", {"status": "complete"}),
            ],
        )
        self.fixture.add_task("NSC-902", parent="NSC-900")
        task = self.fixture.task("NSC-900")
        self.assertEqual(task["progress"]["children_complete"], 1)
        self.assertEqual(task["progress"]["children_total"], 2)
        self.assertIn("1/2 children complete", "\n".join(task["node_lines"]))

    def test_event_timestamps_drive_clocks_when_legacy_elapsed_field_is_absent(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {"phase": "implementation"}),
                event("pipeline_action_started", {"action": "run_execution_crew"}),
            ]
        )
        task = self.fixture.task()
        self.assertEqual(task["state"], "active")
        self.assertNotIn("elapsed unavailable", "\n".join(task["node_lines"]))


class GauntletViewTokenCostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()

    def tearDown(self) -> None:
        self.fixture.close()

    @staticmethod
    def usage(
        *,
        input_tokens: int = 100,
        cached_tokens: int = 40,
        output_tokens: int = 20,
        total_tokens: int = 120,
        cost: float = 0.12,
    ) -> dict:
        return {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": cost,
        }

    def test_complete_persisted_usage_from_one_provider(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {"phase": "implementation"}),
                usage_event(
                    turn=1,
                    provider="openai-codex",
                    model="gpt-recorded",
                    usage=self.usage(),
                ),
            ]
        )
        usage = self.fixture.task()["token_cost"]
        self.assertEqual(usage["recorded_cost_usd"], 0.12)
        self.assertEqual(usage["recorded_total_tokens"], 120)
        self.assertIs(usage["usage_complete"], True)

    def test_mixed_claude_and_codex_usage_keeps_provider_breakdown(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {"phase": "implementation"}),
                usage_event(
                    turn=1,
                    provider="openai-codex",
                    model="gpt-recorded",
                    role="implementer",
                    usage=self.usage(cost=0.21),
                ),
                usage_event(
                    turn=2,
                    provider="claude-code",
                    model="claude-recorded",
                    role="validator",
                    usage=self.usage(cost=0.09),
                ),
            ]
        )
        usage = self.fixture.task()["token_cost"]
        self.assertAlmostEqual(usage["recorded_cost_usd"], 0.30)
        self.assertEqual(
            {(item["role"], item["provider"]) for item in usage["breakdown"]},
            {("implementer", "openai-codex"), ("validator", "claude-code")},
        )

    def test_cached_input_categories_are_preserved_not_repriced(self) -> None:
        self.fixture.add_task(
            progress_events=[
                usage_event(
                    turn=1,
                    provider="claude-code",
                    model="claude-recorded",
                    usage={
                        "input_tokens": 100,
                        "cache_read_input_tokens": 70,
                        "cache_creation_input_tokens": 10,
                        "output_tokens": 20,
                        "reasoning_tokens": 5,
                        "total_tokens": 120,
                        "estimated_cost_usd": 0.42,
                    },
                )
            ]
        )
        usage = self.fixture.task()["token_cost"]
        self.assertEqual(usage["cache_read_input_tokens"], 70)
        self.assertEqual(usage["cache_creation_input_tokens"], 10)
        self.assertEqual(usage["reasoning_tokens"], 5)
        self.assertIsNone(usage["estimated_cache_savings_usd"])

    def test_pooled_session_usage_stays_with_its_task_assignment(self) -> None:
        self.fixture.add_task(
            "NSC-201",
            progress_events=[
                usage_event(
                    turn=1,
                    provider="openai-codex",
                    model="gpt-recorded",
                    usage=self.usage(cost=0.11),
                    session_id="pool-session",
                )
            ],
        )
        self.fixture.add_task(
            "NSC-202",
            progress_events=[
                usage_event(
                    turn=1,
                    provider="openai-codex",
                    model="gpt-recorded",
                    usage=self.usage(cost=0.23),
                    session_id="pool-session",
                )
            ],
        )
        self.assertEqual(self.fixture.task("NSC-201")["token_cost"]["recorded_cost_usd"], 0.11)
        self.assertEqual(self.fixture.task("NSC-202")["token_cost"]["recorded_cost_usd"], 0.23)

    def test_failed_call_with_missing_usage_is_explicitly_partial(self) -> None:
        self.fixture.add_task(
            progress_events=[
                usage_event(
                    turn=1,
                    provider="openai-codex",
                    model="gpt-recorded",
                    usage=self.usage(cost=0.42),
                ),
                usage_event(
                    turn=2,
                    provider="claude-code",
                    model="claude-recorded",
                    usage=None,
                    status="failed",
                ),
            ]
        )
        usage = self.fixture.task()["token_cost"]
        self.assertIs(usage["usage_complete"], False)
        self.assertEqual(usage["missing_usage_calls"], 1)
        self.assertEqual(usage["cost_label"], "at least $0.42")

    def test_unknown_model_uses_persisted_cost_without_local_pricing(self) -> None:
        self.fixture.add_task(
            progress_events=[
                usage_event(
                    turn=1,
                    provider="provider-x",
                    model="unknown-model",
                    usage=self.usage(cost=0.17),
                )
            ]
        )
        usage = self.fixture.task()["token_cost"]
        self.assertEqual(usage["recorded_cost_usd"], 0.17)
        self.assertEqual(usage["cost_source"], "persisted provider usage")

    def test_shared_architect_cost_is_allocated_once_across_named_tasks(self) -> None:
        for task_id in ("NSC-301", "NSC-302", "NSC-303"):
            self.fixture.add_task(task_id)
        self.fixture.write_scheduler_events(
            [
                {
                    "event": "architect_provider_call",
                    "timestamp_utc": "2026-09-07T01:00:00Z",
                    "agent_runtime_run_id": "architect-batch-1",
                    "provider": "openai-codex",
                    "model": "gpt-recorded",
                    "role": "software_architect",
                    "task_ids": ["NSC-301", "NSC-302", "NSC-303"],
                    "provider_usage": {**self.usage(cost=0.24), "total_tokens": 300},
                }
            ]
        )
        usage = self.fixture.task("NSC-301")["token_cost"]
        self.assertEqual(usage["shared_calls"][0]["complete_cost_usd"], 0.24)
        self.assertEqual(usage["allocated_shared_cost_usd"], 0.08)
        self.assertEqual(usage["shared_calls"][0]["allocation_method"], "equal share across 3 named tasks")

    def test_retry_cost_accumulates_unique_run_turn_receipts(self) -> None:
        self.fixture.add_task(
            progress_events=[
                usage_event(
                    turn=1,
                    provider="openai-codex",
                    model="gpt-recorded",
                    usage=self.usage(cost=0.10),
                ),
                event("run_finished", {"status": "failed"}),
            ]
        )
        self.fixture.add_worker_run(
            "NSC-112",
            "worker-run-b",
            progress_events=[
                usage_event(
                    turn=1,
                    provider="openai-codex",
                    model="gpt-recorded",
                    usage=self.usage(cost=0.20),
                )
            ],
            mtime=1_788_745_700,
        )
        usage = self.fixture.task()["token_cost"]
        self.assertAlmostEqual(usage["recorded_cost_usd"], 0.30)
        self.assertEqual(usage["total_calls"], 2)

    def test_insufficient_cost_history_keeps_projection_separate(self) -> None:
        self.fixture.add_task(
            progress_events=[
                event("state_observed", {"phase": "implementation"}),
                usage_event(
                    turn=1,
                    provider="openai-codex",
                    model="gpt-recorded",
                    usage=self.usage(cost=0.10),
                ),
            ]
        )
        self.assertEqual(
            self.fixture.task()["token_cost"]["projection_label"],
            "insufficient history",
        )

    def test_three_comparable_completed_tasks_produce_cost_projection_range(self) -> None:
        for index, cost in enumerate((0.50, 0.60, 0.80), start=401):
            self.fixture.add_task(
                f"NSC-{index}",
                progress_events=[
                    event("state_observed", {"phase": "implementation"}),
                    usage_event(
                        turn=1,
                        provider="openai-codex",
                        model="gpt-recorded",
                        usage=self.usage(cost=cost),
                    ),
                    event("terminal_state", {"status": "complete"}),
                    event("run_finished", {"status": "complete"}),
                ],
            )
        self.fixture.add_task(
            "NSC-450",
            progress_events=[
                event("state_observed", {"phase": "implementation"}),
                usage_event(
                    turn=1,
                    provider="openai-codex",
                    model="gpt-recorded",
                    usage=self.usage(cost=0.10),
                ),
            ],
        )
        projection = self.fixture.task("NSC-450")["token_cost"]
        self.assertEqual(projection["projection_sample_count"], 3)
        self.assertEqual(projection["projected_final_cost_usd"], [0.50, 0.80])

    def test_artifact_refresh_does_not_double_count_receipts(self) -> None:
        self.fixture.add_task(
            progress_events=[
                usage_event(
                    turn=1,
                    provider="openai-codex",
                    model="gpt-recorded",
                    usage=self.usage(cost=0.12),
                )
            ]
        )
        snapshot = self.fixture.snapshot()
        first = snapshot.build()["tasks"][0]["token_cost"]
        second = snapshot.build()["tasks"][0]["token_cost"]
        self.assertEqual(first["recorded_cost_usd"], 0.12)
        self.assertEqual(second["recorded_cost_usd"], 0.12)
        self.assertEqual(second["total_calls"], 1)

    def test_duplicate_run_turn_receipt_is_not_double_counted(self) -> None:
        receipt = usage_event(
            turn=1,
            provider="openai-codex",
            model="gpt-recorded",
            usage=self.usage(cost=0.12),
        )
        self.fixture.add_task(progress_events=[receipt, receipt])
        usage = self.fixture.task()["token_cost"]
        self.assertEqual(usage["recorded_cost_usd"], 0.12)
        self.assertEqual(usage["recorded_total_tokens"], 120)
        self.assertEqual(usage["total_calls"], 1)

    def test_completed_task_final_totals_match_persisted_receipts(self) -> None:
        self.fixture.add_task(
            progress_events=[
                usage_event(
                    turn=1,
                    provider="openai-codex",
                    model="gpt-recorded",
                    usage=self.usage(total_tokens=318_400, cost=0.42),
                ),
                event("terminal_state", {"status": "complete"}),
                event("run_finished", {"status": "complete"}),
            ]
        )
        task = self.fixture.task()
        self.assertEqual(task["state"], "complete")
        self.assertEqual(task["token_cost"]["recorded_cost_usd"], 0.42)
        self.assertEqual(task["token_cost"]["recorded_total_tokens"], 318_400)

    def test_server_remains_read_only_without_provider_or_github_calls(self) -> None:
        source = SERVER_PATH.read_text(encoding="utf-8")
        for forbidden in ("subprocess", "urlopen", "requests.", '"gh"', "'gh'"):
            self.assertNotIn(forbidden, source)


class GauntletViewHtmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = INDEX_PATH.read_text(encoding="utf-8")

    def test_human_action_primary_destination_is_issue(self) -> None:
        self.assertIn("function githubIssueNavigation(task)", self.html)
        self.assertIn("task.state === 'human_action' ? ' primary' : ''", self.html)
        self.assertIn(">Open GitHub Issue</a>", self.html)
        function_start = self.html.index("function showDetail(id)")
        function_end = self.html.index("// Highlight a node", function_start)
        detail_source = self.html[function_start:function_end]
        task_position = detail_source.index("field('task'")
        issue_position = detail_source.index("githubIssueNavigation(task)")
        worker_position = detail_source.index("field('worker'")
        self.assertLess(task_position, issue_position)
        self.assertLess(issue_position, worker_position)

    def test_guarded_human_actions_are_distinct_and_capability_only(self) -> None:
        self.assertIn("${esc(action.label)}</button>", self.html)
        self.assertIn("fetch('/api/approve'", self.html)
        self.assertIn("JSON.stringify({ action_token: button.dataset.actionToken })", self.html)
        self.assertNotIn("JSON.stringify({ repository:", self.html)
        self.assertIn("mutation_succeeded_poke_failed", self.html)
        self.assertIn("workflow_schema_version", self.html)
        self.assertIn("approvalOutcomes", self.html)

    def test_run_scope_is_the_default_proof_view(self) -> None:
        self.assertIn('id="f-scope" checked', self.html)

    def test_dependency_and_hierarchy_layouts_are_top_to_bottom(self) -> None:
        self.assertIn("const MAX_COLUMNS = 4", self.html)
        self.assertIn("name: 'preset'", self.html)
        self.assertIn("componentRows", self.html)
        self.assertNotIn("rankDir: mode === 'deps' ? 'LR' : 'TB'", self.html)

    def test_dependency_and_decomposition_edges_render_together(self) -> None:
        self.assertIn('id="mode-all"', self.html)
        self.assertNotIn('id="mode-deps"', self.html)
        self.assertNotIn('id="mode-tree"', self.html)
        self.assertIn("for (const dep of t.depends_on)", self.html)
        self.assertIn("if (t.parent && ids.has(t.parent))", self.html)
        self.assertRegex(
            self.html,
            r'(?s)edge\[kind = "parent"\].*?line-style.*?dashed',
        )

    def test_decomposed_parent_has_dedicated_legend_state(self) -> None:
        self.assertRegex(
            self.html,
            r"aggregate:\s*\{[^}]*label:\s*'Decomposed Parent'",
        )

    def test_delivery_ready_has_non_unstarted_legend_state(self) -> None:
        self.assertRegex(
            self.html,
            r"delivery_ready:\s*\{[^}]*label:\s*'Verified — Ready to Continue'",
        )

    def test_issue_link_opens_safely_in_new_tab(self) -> None:
        self.assertIn('target="_blank" rel="noopener noreferrer"', self.html)

    def test_missing_issue_message_is_visible(self) -> None:
        self.assertIn("GitHub Issue unavailable", self.html)

    def test_node_click_still_selects_without_navigating(self) -> None:
        tap_start = self.html.index("cy.on('tap', 'node'")
        tap_end = self.html.index("cy.on('tap', evt", tap_start)
        tap_source = self.html[tap_start:tap_end]
        self.assertIn("showDetail(node.id())", tap_source)
        self.assertNotIn("window.open", tap_source)
        self.assertNotIn("location.href", tap_source)

    def test_every_state_color_is_visibly_separated(self) -> None:
        def color(state: str) -> tuple[int, int, int]:
            match = re.search(
                rf"^\s*{state}:\s+\{{ color: '#([0-9a-fA-F]{{6}})'",
                self.html,
                re.MULTILINE,
            )
            self.assertIsNotNone(match, f"missing color for {state}")
            value = match.group(1)
            return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))

        states = (
            "ready", "decomposition_ready", "pending", "human_action",
            "blocked", "failed", "active", "checks_pending",
            "integration_queued", "aggregate", "delivery_ready", "complete",
            "cancelled", "excluded",
        )
        colors = {state: color(state) for state in states}
        self.assertEqual(len(set(colors.values())), len(states))
        for index, left in enumerate(states):
            for right in states[index + 1:]:
                distance = sum(
                    (a - b) ** 2 for a, b in zip(colors[left], colors[right])
                ) ** 0.5
                self.assertGreaterEqual(
                    distance,
                    75.0,
                    f"{left} and {right} are too visually similar: {distance:.1f}",
                )

    def test_available_decomposition_uses_a_distinct_color_and_legend_label(self) -> None:
        def color(state: str) -> tuple[int, int, int]:
            match = re.search(
                rf"^\s*{state}:\s+\{{ color: '#([0-9a-fA-F]{{6}})'",
                self.html,
                re.MULTILINE,
            )
            self.assertIsNotNone(match, f"missing color for {state}")
            value = match.group(1)
            return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))

        self.assertNotEqual(color("ready"), color("decomposition_ready"))
        self.assertRegex(
            self.html,
            r"decomposition_ready:\s*\{[^}]*label:\s*'Decomposition Available'",
        )

    def test_integration_queue_state_has_explicit_label(self) -> None:
        self.assertRegex(
            self.html,
            r"integration_queued:\s*\{[^}]*label:\s*'Verified — Waiting for CI Slot'",
        )

    def test_issue_and_pull_request_links_remain_clickable(self) -> None:
        self.assertIn(">Open GitHub Issue</a>", self.html)
        self.assertIn(">Open Pull Request / Checks</a>", self.html)
        self.assertGreaterEqual(
            self.html.count('target="_blank" rel="noopener noreferrer"'),
            2,
        )

    def test_ci_detail_distinguishes_worker_activity_from_lifecycle(self) -> None:
        self.assertIn("Worker active", self.html)
        self.assertIn("Monitoring CI", self.html)
        self.assertIn("Check status unavailable", self.html)

    def test_initial_node_render_uses_normalized_compact_lines(self) -> None:
        label_start = self.html.index("function labelFor(task)")
        label_end = self.html.index("function buildElements", label_start)
        label_source = self.html[label_start:label_end]
        self.assertIn("task.node_lines", label_source)

    def test_detail_has_recorded_token_and_cost_section(self) -> None:
        self.assertIn("Token &amp; cost", self.html)
        self.assertIn("Cost so far", self.html)
        self.assertIn("Tokens used so far", self.html)
        self.assertIn("Final recorded cost", self.html)
        self.assertIn("Final recorded tokens", self.html)
        self.assertIn("Usage coverage", self.html)


class PipelineActivityTests(unittest.TestCase):
    """Pure/component acceptance regressions for request items 1–10.

    Synthetic artifacts only; no Unity, provider, Docker, or GitHub execution.
    Clock is fixed, and historical worker artifacts are intentionally present.
    """

    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)
        self.ids = [f"NSC-{1000 + i}" for i in range(7)]
        self.manifest = {
            "run_id": "run-a", "github_repository": EXPECTED_REPOSITORY,
            "target_task_ids": self.ids, "max_capacity": 3,
            "runtime_configuration": {
                "architect_provider": "codex", "architect_model": "gpt-5.4",
                "provider_allowlist": ["codex"],
                "provider_topology": {"profile": "all-codex", "architect": "codex"},
            },
        }
        write_json(self.fixture.run / "manifest.json", self.manifest)
        for task_id in self.ids:
            _, progress_path = self.fixture.add_task(task_id)
            # These tasks have never launched. The generic fixture normally
            # creates run_started, which would correctly make a node active.
            progress_path.unlink()
        self.started = self.row("architect_started", portfolio_size=7,
                                eligible_pairs=[{"task_id": task_id,
                                                 "work_types": ["implementation", "decomposition"]}
                                                for task_id in self.ids])

    @staticmethod
    def row(kind, second=0, **fields):
        return {"event": kind, "timestamp_utc": f"2026-09-07T01:00:{second:02d}Z", **fields}

    def build(self, events=None):
        self.fixture.write_scheduler_events(events if events is not None else [self.started])
        with mock.patch.object(server.time, "time", return_value=1788743100):
            return self.fixture.snapshot().build()

    def activity(self, events=None):
        return self.build(events)["pipeline_activity"]

    def test_open_architect_seven_candidates(self):
        value = self.activity()
        self.assertEqual(value["stage"], "architect")
        self.assertEqual(value["headline"], "Software Architect is reviewing 7 eligible tasks")
        self.assertEqual(value["candidate_count"], 7)
        self.assertEqual(value["candidates"], self.started["eligible_pairs"])
        self.assertEqual(value["stage_elapsed_seconds"], 300)
        self.assertIn("safely in parallel", value["description"])
        self.assertIn("recorded as in progress", value["call_status"])

    def test_pipeline_reports_durable_total_run_and_current_stage_clocks(self):
        write_jsonl(
            self.fixture.run / "run_timeline.jsonl",
            [
                {
                    "event": "autonomous_run_started",
                    "timestamp_utc": "2026-09-07T00:55:00Z",
                    "run_id": "run-a",
                }
            ],
        )

        value = self.activity()

        self.assertEqual(value["stage_elapsed_seconds"], 300)
        self.assertEqual(value["run_elapsed_seconds"], 600)

    def test_dynamic_child_worker_outranks_capacity_full_scheduler_wait(self):
        parent_path = self.fixture.tasks / f"{self.ids[0]}.yaml"
        parent = json.loads(parent_path.read_text(encoding="utf-8"))
        parent["decomposition_state"] = "decomposed"
        parent["decomposition_children"] = ["NSC-1011"]
        write_json(parent_path, parent)
        _, child_progress = self.fixture.add_task("NSC-1011", parent=self.ids[0])
        child_progress.unlink()
        self.fixture.add_worker_run(
            "NSC-1011",
            "child-current",
            progress_events=[
                event(
                    "pipeline_action_started",
                    {"action": "run_execution_crew"},
                    timestamp="2026-09-07T01:00:03Z",
                )
            ],
            mtime=1788742803,
        )
        self.manifest["max_capacity"] = 1
        write_json(self.fixture.run / "manifest.json", self.manifest)

        value = self.activity(
            [
                self.row(
                    "worker_launched",
                    2,
                    task_id="NSC-1011",
                    run_id="child-current",
                    worker_id="worker-child",
                    work_type="implementation",
                ),
                self.row(
                    "scheduler_blocked",
                    4,
                    reason="local max_workers capacity is full",
                    active_worker_count=1,
                ),
                self.row(
                    "architect_wait_started",
                    5,
                    wait_mode="event_or_fallback",
                    active_worker_count=1,
                ),
            ]
        )

        self.assertEqual(value["stage"], "implementation")
        self.assertEqual(
            value["headline"],
            "NSC-1011: ExecutionCrew is implementing Task NSC-1011 (4m 57s); "
            "scheduler is holding the only slot until it returns.",
        )
        self.assertEqual(value["counters"]["active_workers"], 1)
        self.assertEqual(value["counters"]["capacity"], 1)
        self.assertIn("normal", value["description"].casefold())
        self.assertNotIn("admissions are blocked", value["headline"].casefold())

    def test_recorded_worker_without_action_still_outranks_generic_wait_headline(self):
        value = self.activity(
            [
                self.row(
                    "worker_launched",
                    2,
                    task_id=self.ids[0],
                    run_id="current",
                    worker_id="worker-a",
                ),
                self.row(
                    "architect_wait_started",
                    3,
                    wait_mode="event_or_fallback",
                    active_worker_count=1,
                ),
            ]
        )

        self.assertEqual(
            value["headline"],
            f"{self.ids[0]} work is in progress; scheduler is waiting for its worker to return.",
        )
        self.assertIn("state-change poke", value["description"])

    def test_completion_followed_by_launch(self):
        value = self.activity([self.started, self.row("architect_completed", 5, task_id=self.ids[0]),
                               self.row("worker_launched", 6, task_id=self.ids[0], run_id="current")])
        self.assertEqual(value["stage"], "worker_launch")
        self.assertIn(self.ids[0], value["headline"])
        self.assertFalse(value["provider_call_open"])

    def test_provider_receipt_closes_call_before_per_task_completion(self):
        value = self.activity([self.started, self.row("architect_provider_call", 5,
                               analysis_id="a", agent_runtime_run_id="invocation-a", provider="codex", model="actual")])
        self.assertFalse(value["provider_call_open"])
        self.assertEqual(value["counters"]["architect_calls_completed"], 1)

    def test_fallback_wait_is_not_provider_activity(self):
        value = self.activity([self.row("architect_wait_started", wait_mode="fallback_timer")])
        self.assertEqual(value["stage"], "fallback_wait")
        self.assertFalse(value["provider_call_open"])
        self.assertIn("fallback", value["headline"])

    def test_event_wait_explains_poke(self):
        value = self.activity([self.row("architect_wait_started", wait_mode="event_or_fallback")])
        self.assertEqual(value["stage"], "event_wait")
        self.assertIn("state-change poke", value["headline"])

    def test_cached_wait_is_distinct(self):
        value = self.activity([self.row("architect_wait", cached=True, task_id=self.ids[0])])
        self.assertEqual(value["stage"], "architect_cached")
        self.assertFalse(value["provider_call_open"])

    def test_all_wait_requires_complete_portfolio_coverage(self):
        receipt = self.row("architect_provider_call", 1, analysis_id="a")
        waits = [self.row("architect_capacity_deferred", 2+i, analysis_id="a", task_id=task_id)
                 for i, task_id in enumerate(self.ids)]
        self.assertNotEqual(self.activity([self.started, receipt, waits[0]])["stage"], "all_wait")
        value = self.activity([self.started, receipt, *waits, self.row("plan_idle", 12,
                              decision="all_ordered_candidates_waited")])
        self.assertEqual(value["stage"], "all_wait")
        self.assertIn("all 7", value["headline"])

    def test_failed_architect_is_wait_not_open_or_all_wait(self):
        value = self.activity([self.started, self.row("architect_wait", 2, cached=False,
                              analysis_id=None, error="unusable")])
        self.assertEqual(value["stage"], "architect_unavailable")
        self.assertFalse(value["provider_call_open"])

    def test_staleness_and_absent_events_are_honest(self):
        self.assertEqual(self.activity()["freshness"],
                         "No new durable event for 5m 0s; process status is unknown from artifacts.")
        value = self.activity([])
        self.assertEqual(value["stage"], "unknown")
        self.assertIsNone(value["last_event_age_seconds"])
        self.assertIn("unavailable", value["freshness"])

    def test_graph_complete_outranks_open_call(self):
        write_json(self.fixture.run / "graph-complete.json", {"receipt_sha256": "a" * 64})
        value = self.activity()
        self.assertEqual(value["headline"], "Graph complete")
        self.assertFalse(value["provider_call_open"])

    def test_fatal_outranks_later_worker_and_stop(self):
        value = self.activity([self.started, self.row("poll_capacity_batch_completed", 2, fatal=True),
                              self.row("worker_launched", 3, task_id=self.ids[0]),
                              self.row("scheduler_stopped", 4)])
        self.assertEqual(value["headline"], "Run failed")
        self.assertFalse(value["provider_call_open"])

    def test_stopped_outranks_earlier_architect(self):
        self.assertEqual(self.activity([self.started, self.row("scheduler_stopped", 2)])["headline"], "Run stopped")

    def test_architect_does_not_change_node_truth(self):
        value = self.build()
        self.assertEqual(value["pipeline_activity"]["stage"], "architect")
        self.assertTrue(all(task["state"] == "ready" for task in value["tasks"]))
        self.assertEqual(value["scheduler"]["active"], [])

    def test_all_codex_manifest_and_missing_model(self):
        value = self.activity()
        self.assertEqual(value["provider"], "codex")
        self.assertEqual(value["model"], "gpt-5.4")
        self.assertEqual(value["provider_source"], "manifest configuration")
        self.manifest["runtime_configuration"].pop("architect_model")
        write_json(self.fixture.run / "manifest.json", self.manifest)
        self.assertEqual(self.activity()["model"], "unavailable")

    def test_optional_fields_are_unavailable(self):
        self.manifest.pop("runtime_configuration")
        self.manifest.pop("max_capacity")
        write_json(self.fixture.run / "manifest.json", self.manifest)
        value = self.activity([self.row("architect_started")])
        self.assertEqual(value["provider"], "unavailable")
        self.assertEqual(value["model"], "unavailable")
        self.assertIsNone(value["candidate_count"])
        self.assertIsNone(value["counters"]["capacity"])
        self.assertIsNone(value["counters"]["wakeups"])

    def test_run_counters_exclude_history_and_deduplicate_calls(self):
        self.fixture.add_task("NSC-999")
        write_json(self.fixture.run / "progress.json", {"worker_launches_total": 2, "wakeups_total": 4})
        receipt = self.row("architect_provider_call", 1, agent_runtime_run_id="invocation-a", analysis_id="a")
        value = self.activity([self.started, receipt, receipt,
                              self.row("architect_completed", 2, task_id=self.ids[0], analysis_id="a"),
                              self.row("worker_launched", 3, task_id=self.ids[0], run_id="current")])
        self.assertEqual(value["counters"], {"active_workers": 1, "capacity": 3,
                         "eligible_or_queued": 6, "dependency_blocked": 0, "completed": 0,
                         "architect_calls_completed": 1, "worker_launches": 2, "wakeups": 4})

    def test_timeline_terminal_and_fingerprint(self):
        before = self.fixture.snapshot().fingerprint()
        write_jsonl(self.fixture.run / "run_timeline.jsonl", [
            self.row("autonomous_run_error", 1, run_id="run-a", exception_type="RuntimeError")])
        self.assertNotEqual(before, self.fixture.snapshot().fingerprint())
        self.assertEqual(self.activity()["headline"], "Run failed")

    def test_unknown_events_order_and_recent_timeline(self):
        value = self.activity([self.row("future_event", 2), self.started])
        self.assertEqual(value["stage"], "architect")
        self.assertEqual(value["recent_activity"][0]["event"], "future_event")
        self.assertEqual(value["last_event_age_seconds"], 298)

    def test_worker_activity_requires_exact_run_launch(self):
        self.fixture.add_worker_run(self.ids[0], "current", progress_events=[event(
            "pipeline_action_started", {"action": "run_execution_crew"},
            timestamp="2026-09-07T01:00:04Z")], mtime=1788742804)
        rows = [self.row("worker_launched", 2, task_id=self.ids[0], run_id="current")]
        self.assertEqual(
            self.activity(rows)["headline"],
            "NSC-1000: ExecutionCrew is implementing Task NSC-1000 (4m 56s)",
        )
        self.assertEqual(self.activity()["stage"], "architect")

    def test_open_architect_outranks_concurrent_worker_activity(self):
        self.fixture.add_worker_run(self.ids[0], "current", progress_events=[event(
            "pipeline_action_started", {"action": "run_execution_crew"},
            timestamp="2026-09-07T01:00:04Z")], mtime=1788742804)
        value = self.activity([self.row("worker_launched", task_id=self.ids[0], run_id="current"),
                               {**self.started, "timestamp_utc": "2026-09-07T01:00:02Z"}])
        self.assertEqual(value["stage"], "architect")
        self.assertEqual(value["counters"]["active_workers"], 1)

    def test_later_failure_wins_over_timestamped_completion_receipt(self):
        write_json(self.fixture.run / "graph-complete.json", {"receipt_sha256": "a" * 64})
        write_jsonl(self.fixture.run / "run_timeline.jsonl", [
            self.row("graph_complete_receipt_written", 1, run_id="run-a"),
            self.row("autonomous_run_error", 2, run_id="run-a", exception_type="RuntimeError")])
        self.assertEqual(self.activity()["headline"], "Run failed")

    def test_worker_heartbeat_keeps_start_and_advances_freshness(self):
        self.fixture.add_worker_run(self.ids[0], "current", progress_events=[
            event("pipeline_action_started", {"action": "prepare_task_checkout"}, timestamp="2026-09-07T01:00:02Z"),
            event("pipeline_action_heartbeat", {"action": "prepare_task_checkout"}, timestamp="2026-09-07T01:00:12Z"),
        ], mtime=1788742812)
        value = self.activity([self.row("worker_launched", task_id=self.ids[0], run_id="current")])
        self.assertEqual(value["stage"], "checkout")
        self.assertEqual(value["stage_elapsed_seconds"], 298)
        self.assertEqual(value["last_event_age_seconds"], 288)

    def test_idle_and_foreign_timeline_are_not_live_or_terminal(self):
        write_jsonl(self.fixture.run / "run_timeline.jsonl", [
            self.row("autonomous_run_error", 2, run_id="another-run")])
        value = self.activity([self.row("plan_idle", decision="no_safe_work")])
        self.assertEqual(value["stage"], "idle")
        self.assertFalse(value["terminal"])

    def test_worker_action_completion_does_not_claim_action_still_running(self):
        self.fixture.add_worker_run(self.ids[0], "current", progress_events=[
            event("pipeline_action_started", {"action": "run_execution_crew"}, timestamp="2026-09-07T01:00:02Z"),
            event("pipeline_action_completed", {"action": "run_execution_crew"}, timestamp="2026-09-07T01:00:12Z"),
        ], mtime=1788742812)
        value = self.activity([self.row("worker_launched", task_id=self.ids[0], run_id="current")])
        self.assertNotEqual(value["stage"], "implementation")
        self.assertIn("completed", value["headline"])

    def test_panel_has_live_elapsed_and_safe_timeline_rendering(self):
        html = INDEX_PATH.read_text(encoding="utf-8")
        self.assertIn('id="pipeline-activity"', html)
        self.assertLess(html.index('id="pipeline-activity"'), html.index('id="cy"'))
        self.assertIn("renderPipelineActivity(snap.pipeline_activity)", html)
        self.assertIn("updatePipelineTimers", html)
        self.assertIn("Current stage elapsed", html)
        self.assertIn("Total run elapsed", html)
        self.assertIn("expandedStageNodes", html)
        self.assertIn("+ Expand", html)
        self.assertIn("− Collapse", html)
        self.assertIn("configureStageExpansion(snap)", html)
        self.assertIn("esc(item.headline)", html)
        self.assertIn("process status is unknown from artifacts", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
