"""Focused regressions for authenticated AssistantControl D1C application."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.decomposition import _verify_review, apply
from Pipeline.TaskDecomposition.round_robin_decomposition import candidate_sha256
from Pipeline.TaskDecomposition.tests.test_support import create_repository, decomposed_result
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from TaskDecomposition.policy import validate_decomposition_result
from graph_delta import plan_graph_delta
from persistent_work_graph import load_persistent_work_graph


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return completed.stdout.decode("utf-8", "replace").strip()


class RetainedReviewConcurrencyTests(unittest.TestCase):
    def test_unrelated_integration_retains_review_and_applies_at_current_source(self):
        temporary = tempfile.TemporaryDirectory(prefix="assistant-d1c-concurrency-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source"
        source.mkdir()
        create_repository(source)
        task_id = "NSC-004"
        task_path = source / "Tasks" / f"{task_id}.yaml"
        selected = json.loads(task_path.read_text(encoding="utf-8"))
        selected.update(
            execution_scope="needs_execution_decomposition",
            execution_reason="Synthetic concurrency regression requires decomposition.",
        )
        _write_json(task_path, selected)
        _git(source, "add", "--", f"Tasks/{task_id}.yaml")
        _git(source, "commit", "-m", "fixture: select childless decomposition parent")
        graph = load_persistent_work_graph(source)
        parent = graph.tasks_by_id[task_id]
        proposal = decomposed_result(parent)
        proposal["children"][0]["exclusive_resources"] = []
        proposal["inbound_dependency_rewrites"] = []
        decomposition = validate_decomposition_result(
            proposal,
            parent_task=parent,
            existing_reconciliation_keys=graph.plan.id_map,
        )
        stored_plan = plan_graph_delta(graph, decomposition.parent_task, decomposition)
        reviewed_head = _git(source, "rev-parse", "HEAD")
        manager = Checkouts(source, root / "checkouts")
        manager.records.mkdir(parents=True)

        run_id = "fixture-reviewed-decomposition"
        output_root = (manager.records / "decomposition-runs").resolve()
        artifact_root = output_root / run_id
        artifact_root.mkdir(parents=True)
        branch = _git(source, "branch", "--show-current")
        reviewed_tree = _git(source, "rev-parse", "HEAD^{tree}")
        task = load_committed_task(source, task_id, commit=reviewed_head)
        digest = candidate_sha256(decomposition)
        candidate = {
            "version": 1,
            "author_provider": "claude",
            "sha256": digest,
            "decision": "decomposed",
            "graph_delta_plan_id": stored_plan.plan_id,
        }
        run_result = {
            "schema_version": "1.0",
            "mode": "round_robin_d1b2",
            "run_id": run_id,
            "task_id": task_id,
            "provider_order": ["claude", "codex"],
            "max_calls": 2,
            "calls_used": 2,
            "run_status": "review_ready",
            "decision": "decomposed",
            "review_independence": "cross_provider",
            "authority": "review_only_not_applied",
            "unresolved_findings": [],
            "rejection_reasons": [],
            "source_identity": {
                "head_commit": reviewed_head,
                "head_tree": reviewed_tree,
            },
            "task_execution_contract_identity": {
                "revision": task["contract_revision"],
                "sha256": task["task_contract_sha256"],
            },
            "latest_candidate": candidate,
            "independent_approver_provider": "codex",
            "rounds": [
                {
                    "role": "task_decomposer",
                    "requested_provider": "claude",
                    "actual_model": "fixture-author",
                    "agent_status": "succeeded",
                    "status": "candidate_valid",
                    "candidate_after": candidate,
                },
                {
                    "role": "decomposition_reviewer",
                    "requested_provider": "codex",
                    "actual_model": "fixture-reviewer",
                    "agent_status": "succeeded",
                    "status": "independent_pass",
                    "verdict": "pass",
                    "candidate_before": candidate,
                    "candidate_after": None,
                },
            ],
            "finding_history": [{
                "verdict": "pass",
                "reviewed_candidate_sha256": digest,
                "findings": [],
            }],
        }
        _write_json(artifact_root / "decomposition_run_result.json", run_result)
        _write_json(
            artifact_root / "decomposition_result.json",
            decomposition.to_dict(),
        )
        _write_json(artifact_root / "graph_delta.json", stored_plan.to_dict())
        artifact_bytes = {
            path.name: path.read_bytes() for path in artifact_root.iterdir()
        }
        record = {
            "schema_version": "assistant-decomposition/v1",
            "task_id": task_id,
            "run_id": run_id,
            "source": str(source.resolve()),
            "source_commit": reviewed_head,
            "source_tree": reviewed_tree,
            "source_branch": branch,
            "task_contract_sha256": task["task_contract_sha256"],
            "providers": ["claude", "codex"],
            "output_root": str(output_root),
            "artifact_root": str(artifact_root),
            "status": "review_ready",
        }
        original_review = _verify_review(manager, record)
        record["review"] = original_review
        write_record(manager.records / f"{task_id}.decomposition.json", record)

        concurrent_path = source / "Assets" / "ConcurrentImplementation.cs"
        concurrent_path.write_text(
            "// Concurrent implementation integrated.\n", encoding="utf-8", newline="\n",
        )
        _git(source, "add", "--", "Assets/ConcurrentImplementation.cs")
        _git(source, "commit", "-m", "fixture: concurrent implementation")
        current_head = _git(source, "rev-parse", "HEAD")
        current_review = _verify_review(manager, record)
        proof = current_review["source_advancement"]
        self.assertEqual(reviewed_head, proof["reviewed_source_commit"])
        self.assertEqual(current_head, proof["apply_source_commit"])
        self.assertTrue(proof["reviewed_source_is_ancestor"])
        self.assertTrue(proof["authoritative_graph_inputs_unchanged"])
        self.assertTrue(proof["parent_contract_semantic_authorization_compatible"])
        self.assertEqual(
            proof["reviewed_parent_semantic_sha256"],
            proof["current_parent_semantic_sha256"],
        )

        with patch.dict(os.environ, {
            "NSC_AGENT_GIT_NAME": "No Safe Circle TaskReviewAgent",
            "NSC_AGENT_GIT_EMAIL": "task-review-agent@nosafecircle.invalid",
        }):
            applied = apply(
                manager,
                task_id,
                run_id=run_id,
                expected_source_commit=current_head,
                target_branch=branch,
            )

        self.assertEqual(current_head, _git(source, "rev-parse", "HEAD^"))
        self.assertEqual(original_review, applied["review"])
        self.assertEqual(current_review, applied["application_authentication"])
        self.assertEqual(
            artifact_bytes,
            {path.name: path.read_bytes() for path in artifact_root.iterdir()},
        )


if __name__ == "__main__":
    unittest.main()
