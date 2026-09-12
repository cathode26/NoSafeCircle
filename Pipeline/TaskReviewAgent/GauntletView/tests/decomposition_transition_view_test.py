#!/usr/bin/env python3
"""Component regressions for automatic decomposition viewer transitions."""

from __future__ import annotations

import importlib.util
import json
import shutil
import unittest
import uuid
from pathlib import Path


SERVER = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("decomposition_transition_server", SERVER)
server = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(server)


class DecompositionTransitionViewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (Path(r"C:\NSC") / f"decomposition-transition-view-{uuid.uuid4().hex}").resolve()
        self.root.mkdir()
        self.snapshot = server.Snapshot.__new__(server.Snapshot)
        self.snapshot.local_run_root = self.root
        self.snapshot.cache = server.FileCache()
        workflow = {
            "schema_version": "1.0", "task_id": "NSC-898", "state_version": 2,
            "state": "human_action_required", "current_actor": "human",
            "phase": "decomposition_apply_authorization", "worker_id": None,
            "lease_id": None, "branch": "nsc-898-test", "head_commit": "a" * 40,
            "checkout_path": str(self.root / "checkouts" / "NSC-898"),
            "task_contract_sha256": "c" * 64, "human_handoff_commit": "a" * 40,
            "human_result": None, "last_event_id": "d" * 64,
            "updated_at_utc": "2026-09-09T07:00:00Z",
        }
        self.local = {"run_id": "run-1", "local_decomposition_apply": True,
                      "decomposition_handoffs": {"NSC-898": workflow}}
        self.workflow_body = "<!-- nsc-workflow-state\n" + json.dumps(workflow) + "\n-->"
        self.record = {
            "state": "human_action_required", "pipeline_stage": "human_action_required",
            "worker_id": None, "lease_id": None, "worker_run_id": "worker-1",
            "route": {"work_type": "decomposition"}, "source_commit": "a" * 40,
            "source_tree": "b" * 40, "task_contract_sha256": "c" * 64,
            "last_event_id": "d" * 64,
        }

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def write_result(self, **changes) -> None:
        result = {
            "task_id": "NSC-898", "run_id": "worker-1", "exit_code": 0,
            "terminal_status": "local_review_ready", "outcome_authority": "local_rehearsal_only",
            "source_head": "a" * 40, "task_contract_sha256": "c" * 64,
        }
        result.update(changes)
        path = (self.root / "checkouts" / ".task-review-agent" / "outputs" /
                "NSC-898" / "worker-1" / "run_result.json")
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(result), encoding="utf-8")

    def test_bound_automatic_handoff_stays_decomposition_working(self) -> None:
        label = self.snapshot.local_decomposition_stage(self.local, "NSC-898", self.record)
        self.assertEqual(label, "Checking decomposition for automatic application")
        lines = server.Snapshot.node_lines({
            "state": "active", "active_work_type": "decomposition", "worker": {},
            "progress": {"transition_context_kind": None, "pipeline_stages": [], "agents": []},
        })
        self.assertEqual(lines[0], "TASK WORKING (DECOMPOSITION)")

    def test_unbound_or_needs_human_result_remains_human_action(self) -> None:
        self.local["local_decomposition_apply"] = False
        self.assertIsNone(self.snapshot.local_decomposition_stage(self.local, "NSC-898", self.record))
        lines = server.Snapshot.node_lines({
            "state": "human_action", "active_work_type": "decomposition", "worker": {},
            "progress": {"transition_context_kind": None},
        })
        self.assertIsNone(lines)

    def test_wrong_handoff_identity_is_not_projected_as_automatic(self) -> None:
        for key, value in (("source_commit", "e" * 40), ("task_contract_sha256", "e" * 64)):
            with self.subTest(key=key):
                record = dict(self.record, **{key: value})
                self.assertIsNone(self.snapshot.local_decomposition_stage(self.local, "NSC-898", record))

    def test_journal_event_hash_never_gates_the_automatic_handoff_label(self) -> None:
        # _save stamps record.last_event_id with the local journal hash; the
        # Issue workflow's last_event_id is a different id space. Real records
        # therefore never carried the workflow id (archived G8 run, NSC-898).
        record = dict(self.record, last_event_id="e" * 64)
        self.assertEqual(self.snapshot.local_decomposition_stage(self.local, "NSC-898", record),
                         "Checking decomposition for automatic application")

    def test_pending_applying_and_parent_display_sequence(self) -> None:
        pending = dict(self.record, pipeline_stage="decomposition_review_pending",
                       local_decomposition_pending={
                           "run_id": "run-1", "task_id": "NSC-898",
                           "source_commit": "a" * 40, "source_tree": "b" * 40,
                           "task_contract_sha256": "c" * 64, "human_result": None,
                           "handoff_event_id": "d" * 64, "graph_delta_plan_id": "GDP-1",
                           "worker_run_id": "worker-1",
                       })
        self.assertEqual(self.snapshot.local_decomposition_stage(self.local, "NSC-898", pending),
                         "Checking decomposition for automatic application")
        applying = dict(self.record, pipeline_stage="decomposition_apply_authorized",
                        local_decomposition_authorization={
                            "run_id": "run-1", "task_id": "NSC-898",
                            "source_commit": "a" * 40, "source_tree": "b" * 40,
                            "task_contract_sha256": "c" * 64, "human_result": None,
                            "handoff_event_id": "d" * 64, "graph_delta_plan_id": "GDP-1",
                            "authority": "local_rehearsal_only",
                            "basis": "explicit_run_setting:local_decomposition_apply",
                        })
        self.assertEqual(self.snapshot.local_decomposition_stage(self.local, "NSC-898", applying),
                         "Applying decomposition")
        aggregate = server.Snapshot.node_lines({
            "state": "aggregate", "worker": {},
            "progress": {"children_complete": 0, "children_total": 2,
                         "children_by_state": {"ready": 2}},
        })
        self.assertEqual(aggregate[0], "DECOMPOSED · CHILDREN IN PROGRESS")

    def test_fixture_name_is_removed_only_from_display_title(self) -> None:
        self.assertEqual(server.display_task_title(
            "Gauntlet 898: Split Alpha and Beta Values", "NSC-898"),
            "Gauntlet 898: Split Alpha and Beta Values")
        self.assertEqual(server.display_task_title("Gauntlet898Alpha", "NSC-1013"),
                         "Gauntlet898Alpha")

    def test_real_local_snapshot_shape_projects_exact_handoff(self) -> None:
        from Pipeline.TaskReviewAgent.local_rehearsal import LocalRunContext
        context = LocalRunContext.__new__(LocalRunContext)
        context.run_id, context.source_head, context.source_tree = "run-1", "a" * 40, "b" * 40
        context.source_root, context.provider_profile = self.root, "all-claude"
        context.local_decomposition_apply = True
        context.local_candidate_auto_accept = False
        context.initial_source_commit, context.initial_source_tree = "a" * 40, "b" * 40
        context.source_lineage = ()
        context.manifest = {"source_branch": "test", "max_capacity": 2, "contracts": {},
                            "runtime_patch": None}
        state = {"issues": {"1": {"body": self.workflow_body}}, "tasks": {}, "events": []}
        projected = context._snapshot_from_state(state)
        self.assertNotIn("issues", projected)
        self.assertEqual(projected["decomposition_handoffs"]["NSC-898"]["last_event_id"], "d" * 64)


if __name__ == "__main__":
    unittest.main()
