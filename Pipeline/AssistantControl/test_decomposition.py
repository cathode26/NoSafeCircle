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


class ProposalContainerNameTests(unittest.TestCase):
    """A named proposal container lets an owner stop exactly one proposal; nothing else changes."""

    def test_run_names_the_compose_container_after_the_run_subcommand(self):
        from Pipeline.AssistantControl import decomposition as decomposition_module
        temporary = tempfile.TemporaryDirectory(prefix="assistant-decompose-name-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source"
        source.mkdir()
        create_repository(source)
        task_path = source / "Tasks" / "NSC-004.yaml"
        selected = json.loads(task_path.read_text(encoding="utf-8"))
        selected.update(execution_scope="needs_execution_decomposition",
                        execution_reason="Synthetic container-name regression requires decomposition.")
        _write_json(task_path, selected)
        _git(source, "add", "--", "Tasks/NSC-004.yaml")
        _git(source, "commit", "-m", "fixture: childless decomposition parent")
        head = _git(source, "rev-parse", "HEAD")
        manager = Checkouts(source, root / "checkouts")
        commands: list[list[str]] = []
        real_run = subprocess.run

        def fake_run(command, *args, **kwargs):
            if list(command)[:2] == ["docker", "compose"]:
                commands.append(list(command))
                return subprocess.CompletedProcess(command, 1)
            return real_run(command, *args, **kwargs)

        with patch.object(decomposition_module, "build_compose_command",
                          return_value=("docker", "compose", "-p", "nosafecircle", "run", "--rm", "-T",
                                        "round-robin-decompose", "python3",
                                        "Pipeline/TaskDecomposition/run_round_robin_decomposition.py")), \
                patch.object(decomposition_module, "decomposition_preflight",
                             return_value={"source_commit": head}), \
                patch.object(decomposition_module.subprocess, "run", side_effect=fake_run):
            record = decomposition_module.run(
                manager, "NSC-004", "fixture-run", providers="claude,codex",
                compose_project="nosafecircle", execution_authorized=True,
                container_name="nsc-decompose-fixture000000000000",
                container_labels={"com.nosafecircle.assistant.job": "fixture000000000000",
                                  "com.nosafecircle.assistant.checkout": "abc123"},
            )
        self.assertEqual("failed", record["status"])
        self.assertEqual("nsc-decompose-fixture000000000000", record["container_name"])
        # The container carries the owning ticket and checkout, so only that
        # owner can prove the container is its own before removing it.
        self.assertEqual({"com.nosafecircle.assistant.job": "fixture000000000000",
                          "com.nosafecircle.assistant.checkout": "abc123"},
                         record["container_labels"])
        self.assertEqual(1, len(commands))
        position = commands[0].index("run")
        self.assertEqual(["run", "--name", "nsc-decompose-fixture000000000000",
                          "--label", "com.nosafecircle.assistant.checkout=abc123",
                          "--label", "com.nosafecircle.assistant.job=fixture000000000000",
                          "--rm", "-T"],
                         commands[0][position:position + 9])
        with self.assertRaisesRegex(ValueError, "container name"):
            decomposition_module.run(
                manager, "NSC-004", "fixture-run-2", providers="claude,codex",
                compose_project="nosafecircle", execution_authorized=True,
                container_name="bad name!",
            )
        with self.assertRaisesRegex(ValueError, "container label"):
            decomposition_module.run(
                manager, "NSC-004", "fixture-run-3", providers="claude,codex",
                compose_project="nosafecircle", execution_authorized=True,
                container_name="nsc-decompose-fixture000000000001",
                container_labels={"bad key": "value"},
            )
        with self.assertRaisesRegex(ValueError, "labels require the named container"):
            decomposition_module.run(
                manager, "NSC-004", "fixture-run-4", providers="claude,codex",
                compose_project="nosafecircle", execution_authorized=True,
                container_labels={"com.nosafecircle.assistant.job": "x"},
            )
        self.assertEqual(1, len(commands))


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


class BoundedAuthorCorrectionReviewTests(unittest.TestCase):
    """Apply admits the uncorrected pair and exactly one bounded author correction.

    A corrected `review_ready` run retains its deterministically rejected first
    round, so its `rounds` list is three entries long and the round that
    authored the reviewed candidate is the correction. Every other shape stays
    refused, including a run that claims a correction it does not carry.
    """

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="assistant-d1c-correction-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source"
        source.mkdir()
        create_repository(source)
        self.task_id = "NSC-004"
        task_path = source / "Tasks" / f"{self.task_id}.yaml"
        selected = json.loads(task_path.read_text(encoding="utf-8"))
        selected.update(
            execution_scope="needs_execution_decomposition",
            execution_reason="Synthetic bounded-correction regression requires decomposition.",
        )
        _write_json(task_path, selected)
        _git(source, "add", "--", f"Tasks/{self.task_id}.yaml")
        _git(source, "commit", "-m", "fixture: select childless decomposition parent")
        graph = load_persistent_work_graph(source)
        parent = graph.tasks_by_id[self.task_id]
        proposal = decomposed_result(parent)
        proposal["children"][0]["exclusive_resources"] = []
        proposal["inbound_dependency_rewrites"] = []
        decomposition = validate_decomposition_result(
            proposal,
            parent_task=parent,
            existing_reconciliation_keys=graph.plan.id_map,
        )
        stored_plan = plan_graph_delta(graph, decomposition.parent_task, decomposition)
        head = _git(source, "rev-parse", "HEAD")
        tree = _git(source, "rev-parse", "HEAD^{tree}")
        branch = _git(source, "branch", "--show-current")
        task = load_committed_task(source, self.task_id, commit=head)
        self.manager = Checkouts(source, root / "checkouts")
        self.manager.records.mkdir(parents=True)

        run_id = "fixture-corrected-decomposition"
        output_root = (self.manager.records / "decomposition-runs").resolve()
        self.artifact_root = output_root / run_id
        self.artifact_root.mkdir(parents=True)
        _write_json(self.artifact_root / "decomposition_result.json", decomposition.to_dict())
        _write_json(self.artifact_root / "graph_delta.json", stored_plan.to_dict())
        self.digest = candidate_sha256(decomposition)
        self.candidate = {
            "version": 1,
            "author_provider": "claude",
            "sha256": self.digest,
            "decision": "decomposed",
            "graph_delta_plan_id": stored_plan.plan_id,
        }
        self.run_result = {
            "schema_version": "1.0",
            "mode": "round_robin_d1b2",
            "run_id": run_id,
            "task_id": self.task_id,
            "provider_order": ["claude", "codex"],
            "max_calls": 2,
            "calls_used": 2,
            "run_status": "review_ready",
            "decision": "decomposed",
            "review_independence": "cross_provider",
            "authority": "review_only_not_applied",
            "unresolved_findings": [],
            "rejection_reasons": [],
            "source_identity": {"head_commit": head, "head_tree": tree},
            "task_execution_contract_identity": {
                "revision": task["contract_revision"],
                "sha256": task["task_contract_sha256"],
            },
            "latest_candidate": self.candidate,
            "independent_approver_provider": "codex",
            "finding_history": [{
                "verdict": "pass",
                "reviewed_candidate_sha256": self.digest,
                "findings": [],
            }],
        }
        self.record = {
            "schema_version": "assistant-decomposition/v1",
            "task_id": self.task_id,
            "run_id": run_id,
            "source": str(source.resolve()),
            "source_commit": head,
            "source_tree": tree,
            "source_branch": branch,
            "task_contract_sha256": task["task_contract_sha256"],
            "providers": ["claude", "codex"],
            "output_root": str(output_root),
            "artifact_root": str(self.artifact_root),
            "status": "review_ready",
        }

    # -- exact round fixtures ---------------------------------------------

    def author_round(self, **overrides) -> dict:
        return {"role": "task_decomposer", "correction_of_round": None,
                "requested_provider": "claude", "actual_model": "fixture-author",
                "agent_status": "succeeded", "status": "candidate_valid",
                "candidate_after": self.candidate, **overrides}

    def rejected_round(self, **overrides) -> dict:
        return {"role": "task_decomposer", "correction_of_round": None,
                "requested_provider": "claude", "actual_model": "fixture-author",
                "agent_status": "succeeded", "status": "rejected",
                "candidate_after": None,
                "rejection_reasons": [
                    "initial candidate deterministic validation failed: fixture rejection",
                ],
                **overrides}

    def correction_round(self, **overrides) -> dict:
        return {"role": "task_decomposer", "correction_of_round": 1,
                "requested_provider": "claude", "actual_model": "fixture-correction",
                "agent_status": "succeeded", "status": "correction_candidate_valid",
                "candidate_after": self.candidate, **overrides}

    def reviewer_round(self, **overrides) -> dict:
        return {"role": "decomposition_reviewer", "correction_of_round": None,
                "requested_provider": "codex", "actual_model": "fixture-reviewer",
                "agent_status": "succeeded", "status": "independent_pass",
                "verdict": "pass", "candidate_before": self.candidate,
                "candidate_after": None, **overrides}

    def verify(self, rounds, **run_fields) -> dict:
        _write_json(
            self.artifact_root / "decomposition_run_result.json",
            {**self.run_result, "rounds": rounds, **run_fields},
        )
        return _verify_review(self.manager, self.record)

    # -- accepted shapes ---------------------------------------------------

    def test_uncorrected_author_reviewer_pair_still_verifies(self):
        review = self.verify([self.author_round(), self.reviewer_round()])
        self.assertEqual("review_ready", review["status"])
        self.assertEqual(self.digest, review["candidate_sha256"])
        self.assertEqual(["fixture-author", "fixture-reviewer"], review["models"])
        # An explicit zero count is the same uncorrected run.
        self.assertEqual(review["candidate_sha256"], self.verify(
            [self.author_round(), self.reviewer_round()], author_corrections_used=0,
        )["candidate_sha256"])

    def test_one_bounded_correction_between_the_rounds_verifies(self):
        review = self.verify(
            [self.rejected_round(), self.correction_round(), self.reviewer_round()],
            author_corrections_used=1,
        )
        self.assertEqual("review_ready", review["status"])
        self.assertEqual(self.digest, review["candidate_sha256"])
        # The correction, not the rejected first round, authored the candidate
        # the independent reviewer passed.
        self.assertEqual(["fixture-correction", "fixture-reviewer"], review["models"])
        self.assertEqual(
            self.verify([self.author_round(), self.reviewer_round()])["child_ids"],
            review["child_ids"],
        )

    # -- refused shapes ----------------------------------------------------

    def test_correction_with_the_wrong_status_is_refused(self):
        with self.assertRaisesRegex(ValueError, "exact independent author/reviewer pass"):
            self.verify(
                [self.rejected_round(),
                 self.correction_round(status="candidate_valid"),
                 self.reviewer_round()],
                author_corrections_used=1,
            )

    def test_correction_without_author_corrections_used_is_refused(self):
        with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
            self.verify(
                [self.rejected_round(), self.correction_round(), self.reviewer_round()],
            )
        with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
            self.verify(
                [self.rejected_round(), self.correction_round(), self.reviewer_round()],
                author_corrections_used=0,
            )

    def test_uncorrected_pair_may_not_claim_a_correction(self):
        with self.assertRaisesRegex(ValueError, "counts an author correction"):
            self.verify(
                [self.author_round(), self.reviewer_round()], author_corrections_used=1,
            )

    def test_a_second_correction_entry_is_refused(self):
        with self.assertRaisesRegex(ValueError, "exactly one author and one reviewer round"):
            self.verify(
                [self.rejected_round(), self.correction_round(),
                 self.correction_round(), self.reviewer_round()],
                author_corrections_used=1,
            )
        # Three rounds whose last entry is a second correction rather than the
        # independent reviewer are refused by the reviewer checks.
        with self.assertRaisesRegex(ValueError, "exact independent author/reviewer pass"):
            self.verify(
                [self.rejected_round(), self.correction_round(), self.correction_round()],
                author_corrections_used=1,
            )

    def test_correction_must_follow_a_round_that_produced_no_candidate(self):
        with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
            self.verify(
                [self.author_round(), self.correction_round(), self.reviewer_round()],
                author_corrections_used=1,
            )
        with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
            self.verify(
                [self.rejected_round(correction_of_round=1),
                 self.correction_round(), self.reviewer_round()],
                author_corrections_used=1,
            )

    def test_correction_must_name_the_round_it_corrects(self):
        with self.assertRaisesRegex(ValueError, "exact independent author/reviewer pass"):
            self.verify(
                [self.rejected_round(),
                 self.correction_round(correction_of_round=2),
                 self.reviewer_round()],
                author_corrections_used=1,
            )

    def test_a_reviewer_round_may_not_be_a_correction(self):
        with self.assertRaisesRegex(ValueError, "exact independent author/reviewer pass"):
            self.verify(
                [self.rejected_round(), self.correction_round(),
                 self.reviewer_round(correction_of_round=1)],
                author_corrections_used=1,
            )

    def test_correction_from_another_provider_is_refused(self):
        """The correction is the author's own call: another provider cannot author it."""
        with self.assertRaisesRegex(ValueError, "exact independent author/reviewer pass"):
            self.verify(
                [self.rejected_round(), self.correction_round(requested_provider="codex"),
                 self.reviewer_round()],
                author_corrections_used=1,
            )

    def test_boolean_correction_counts_are_refused(self):
        """`author_corrections_used` is an exact integer; JSON booleans are not counts."""
        with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
            self.verify(
                [self.rejected_round(), self.correction_round(), self.reviewer_round()],
                author_corrections_used=True,
            )
        with self.assertRaisesRegex(ValueError, "counts an author correction"):
            self.verify(
                [self.author_round(), self.reviewer_round()],
                author_corrections_used=False,
            )

    def test_rejected_first_round_must_retain_its_rejection(self):
        """The retained round 1 carries the exact deterministic rejection the correction answered."""
        for rejections in ([], None, ["", "x"], "not a list"):
            with self.subTest(rejection_reasons=rejections):
                with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
                    self.verify(
                        [self.rejected_round(rejection_reasons=rejections),
                         self.correction_round(), self.reviewer_round()],
                        author_corrections_used=1,
                    )
        absent = self.rejected_round()
        del absent["rejection_reasons"]
        with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
            self.verify([absent, self.correction_round(), self.reviewer_round()],
                        author_corrections_used=1)


if __name__ == "__main__":
    unittest.main()
