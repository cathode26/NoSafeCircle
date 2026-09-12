"""Regression-only component replay of local acceptance; no IO or providers.

Builds terminal state with the real local acceptance mutator and receipt type,
then exercises the viewer and counters. This is not Unity/delivery evidence.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

VIEW = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VIEW.parents[2]))
from Pipeline.TaskReviewAgent.local_candidate_commit import LocalCandidateCommitReceipt
from Pipeline.TaskReviewAgent.local_rehearsal import LocalRunContext

spec = importlib.util.spec_from_file_location("local_acceptance_server", VIEW / "server.py")
server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(server)


class LocalCandidateAcceptanceViewTests(unittest.TestCase):
    def setUp(self):
        self.local = {
            "execution_mode": "local_rehearsal", "run_id": "local-view-run",
            "source_commit": "a" * 40, "source_tree": "d" * 40,
            "initial_source_commit": "a" * 40, "initial_source_tree": "d" * 40,
            "source_repository": "C:/NSC/fixture-source", "source_lineage": [],
            "local_candidate_auto_accept": True, "local_decomposition_apply": True,
            "provider_profile": "all-claude", "max_capacity": 20,
            "tasks": {}, "contracts": {}, "events": [], "status": "running",
        }
        self.view = server.Snapshot.__new__(server.Snapshot)
        self.view.local_run_root = Path("C:/NSC/local-acceptance-view-unused")
        self.view.tasks_dir = Path("C:/NSC/fixture-source/Tasks")
        self.view.local_snapshot = lambda: copy.deepcopy(self.local)
        self.view.bound_local_launch = lambda *_: None
        self.view.bound_local_worker = lambda *_: None
        self.view.bound_local_crew = lambda *_: None
        self.view.token_cost = lambda *_: {
            "shared_calls": [], "recorded_total_tokens": 0, "recorded_cost_usd": 0,
            "total_calls": 0, "missing_usage_calls": 0,
        }

    def add_candidate(self, task_id="NSC-1013", *, accepted=True, parent=None):
        index = len(self.local["source_lineage"]) + 1
        commit, tree = f"{index:040x}", f"{index + 20:040x}"
        receipt = LocalCandidateCommitReceipt(
            task_id=task_id, lease_id="lease-" + task_id, plan_id="plan-" + task_id,
            run_id="crew-" + task_id, source_base="a" * 40,
            candidate_commit=f"{index + 40:040x}", candidate_tree=f"{index + 60:040x}",
            candidate_parent="a" * 40, task_contract_sha256="c" * 64,
            execution_result_sha256="e" * 64, candidate_patch_sha256="f" * 64,
            changed_paths=("Assets/" + task_id + ".cs",), validation_sha256="d" * 64,
        )
        contract = {"id": task_id, "title": task_id, "task_contract_sha256": "c" * 64,
                    "parent": parent, "kind": "implementation", "depends_on": [],
                    "decomposition_state": "not_applicable", "decomposition_children": [],
                    "execution_scope": "direct_implementation"}
        record = {
            "run_id": self.local["run_id"], "task_id": task_id,
            "state": "local_review_ready", "pipeline_stage": "local_review_ready",
            "worker_id": "worker-" + task_id, "lease_id": receipt.lease_id,
            "source_commit": receipt.source_base, "source_tree": "d" * 40,
            "task_contract_sha256": receipt.task_contract_sha256,
            "started_at_utc": "2026-09-09T07:00:00Z", "updated_at_utc": "2026-09-09T07:01:00Z",
            "result": {"local_run_id": self.local["run_id"], "task_id": task_id,
                "authority": "local_rehearsal_only", "crew_status": "review_ready",
                "returncode": 0, "rejection_reasons": [], "run_id": receipt.run_id,
                "lease_id": receipt.lease_id, "plan_id": receipt.plan_id,
                "source_head": receipt.source_base, "task_contract_sha256": receipt.task_contract_sha256,
                "result_sha256": receipt.execution_result_sha256,
                "candidate_sha256": receipt.candidate_patch_sha256,
                "final_actual_changed_paths": list(receipt.changed_paths),
                "local_candidate_commit": receipt.to_dict()},
        }
        self.local["contracts"][task_id], self.local["tasks"][task_id] = contract, record
        if accepted:
            entry = {
                "kind": "candidate", "plan_id": receipt.plan_id, "task_id": task_id,
                "parent_commit": self.local["source_commit"], "parent_tree": self.local["source_tree"],
                "applied_commit": commit, "applied_tree": tree,
                "candidate_commit": receipt.candidate_commit, "candidate_tree": receipt.candidate_tree,
                "candidate_receipt_sha256": receipt.to_dict()["receipt_sha256"],
                "child_ids": [], "rewritten_task_ids": [],
            }
            # Reuse the real durable-state transition; replace only its disk save.
            context = LocalRunContext.__new__(LocalRunContext)
            context.manifest = {"manifest_sha256": "9" * 64}
            context._save = lambda *args, **kwargs: None
            context._complete_candidate_state_after_revision(
                {"tasks": self.local["tasks"], "issues": {}}, entry, receipt)
            self.local["source_lineage"].append(entry)
            self.local.update(source_commit=commit, source_tree=tree)
        return record

    def add_parent(self):
        task = "NSC-898"
        self.local["contracts"][task] = {
            "id": task, "title": "Split values", "task_contract_sha256": "b" * 64,
            "kind": "feature", "decomposition_state": "decomposed",
            "decomposition_children": ["NSC-1013", "NSC-1014"], "execution_scope": "not_applicable",
        }
        self.local["tasks"][task] = {
            "run_id": self.local["run_id"], "task_id": task,
            "state": "local_review_ready", "pipeline_stage": "decomposition_applied",
            "worker_id": None, "lease_id": None,
            "source_commit": "a" * 40, "source_tree": "d" * 40, "task_contract_sha256": "b" * 64,
        }

    def test_pending_candidate_remains_review_ready(self):
        self.add_candidate(accepted=False)
        result = self.view.build_local()
        self.assertEqual(result["tasks"][0]["state"], "local_review_ready")
        self.assertEqual(result["pipeline_activity"]["counters"]["local_review_ready"], 1)
        self.assertEqual(result["pipeline_activity"]["counters"]["local_accepted"], 0)

    def test_accepted_candidate_leaves_review_without_production_claim(self):
        self.add_candidate()
        result = self.view.build_local()
        task = result["tasks"][0]
        self.assertEqual(task["state"], "complete")
        self.assertEqual(task["local_state"], "local_review_ready")
        self.assertEqual(task["node_lines"], ["LOCAL ACCEPTED", "Integrated into local Source"])
        self.assertTrue(task["worker"]["finished"])
        self.assertFalse(result["run"]["complete"])
        self.assertIsNone(task["taskgraph"])
        self.assertEqual(result["pipeline_activity"]["counters"]["local_review_ready"], 0)
        self.assertEqual(result["pipeline_activity"]["counters"]["local_accepted"], 1)
        self.assertIsNone(result["pipeline_activity"]["counters"]["completed"])
        self.assertEqual(result["pipeline_activity"]["stage"], "local_accepted")
        self.assertEqual(result["pipeline_activity"]["description"], "")

    def test_parent_counts_only_locally_accepted_children(self):
        self.add_parent()
        self.add_candidate("NSC-1013", parent="NSC-898")
        self.add_candidate("NSC-1014", parent="NSC-898", accepted=False)
        first = self.view.build_local()
        parent = next(task for task in first["tasks"] if task["id"] == "NSC-898")
        self.assertEqual(parent["state"], "aggregate")
        self.assertEqual(parent["progress"]["children_complete"], 1)
        self.assertIn("1/2 children locally accepted", parent["node_lines"][1])
        self.add_candidate("NSC-1014", parent="NSC-898")
        final = self.view.build_local()
        parent = next(task for task in final["tasks"] if task["id"] == "NSC-898")
        self.assertEqual(parent["node_lines"][0], "DECOMPOSED · CHILDREN LOCALLY ACCEPTED")
        self.assertEqual(parent["progress"]["children_complete"], 2)
        self.assertTrue(final["pipeline_activity"]["terminal"])
        self.assertEqual(final["pipeline_activity"]["counters"]["local_review_ready"], 0)
        self.assertFalse(final["run"]["complete"])

    def test_foreign_or_malformed_bindings_never_claim_acceptance(self):
        self.add_candidate()
        original = copy.deepcopy(self.local)
        cases = [
            ("local", "local_candidate_auto_accept", False),
            ("record", "run_id", "other-run"), ("record", "task_id", "NSC-1014"),
            ("record", "source_commit", "0" * 40), ("record", "source_tree", "0" * 40),
            ("record", "task_contract_sha256", "0" * 64),
            ("record", "automated_acceptance_authority", "human"),
            ("record", "worker_id", "still-working"), ("record", "lease_id", "still-leased"),
            ("record", "local_candidate_receipt_sha256", "0" * 64),
            ("record", "human_result", "PASS"), ("record", "blocked_reason", "failed"),
            ("result", "local_run_id", "other-run"), ("result", "crew_status", "failed"),
            ("result", "task_id", "NSC-1014"), ("result", "plan_id", "other-plan"),
            ("result", "result_sha256", "0" * 64), ("result", "lease_id", "other-lease"),
            ("receipt", "candidate_tree", "0" * 40), ("receipt", "changed_paths", []),
            ("entry", "kind", "decomposition"), ("entry", "task_id", "NSC-1014"),
            ("entry", "candidate_receipt_sha256", "0" * 64),
            ("entry", "candidate_tree", "0" * 40), ("entry", "applied_tree", "0" * 40),
        ]
        for target, key, value in cases:
            with self.subTest(target=target, key=key):
                self.local = copy.deepcopy(original)
                record = self.local["tasks"]["NSC-1013"]
                holders = {"local": self.local, "record": record, "result": record["result"],
                    "receipt": record["result"]["local_candidate_commit"], "entry": self.local["source_lineage"][0]}
                holders[target][key] = value
                task = self.view.build_local()["tasks"][0]
                self.assertNotEqual(task["state"], "complete")
                self.assertIsNone(task["local_acceptance"])

    def test_missing_or_foreign_child_cannot_complete_parent(self):
        self.add_parent()
        self.add_candidate("NSC-1013", parent="NSC-898")
        self.add_candidate("NSC-1014", parent="NSC-899")
        parent = next(task for task in self.view.build_local()["tasks"] if task["id"] == "NSC-898")
        self.assertEqual(parent["progress"]["children_complete"], 1)
        self.assertEqual(parent["progress"]["children_total"], 2)
        self.assertEqual(parent["node_lines"][0], "DECOMPOSED · CHILDREN IN PROGRESS")


if __name__ == "__main__":
    unittest.main()
