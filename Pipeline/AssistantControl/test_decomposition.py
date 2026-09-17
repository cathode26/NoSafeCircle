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


POOL_REPOSITORY = "https://example.invalid/NoSafeCircle.git"
POOL_MODEL = "claude-fixture-5"
POOL_LEASE_IDS = {
    "claude:task_decomposer": "11111111-1111-4111-8111-111111111111",
    "claude:decomposition_reviewer": "22222222-2222-4222-8222-222222222222",
}


def _decomposition_parent_fixture(test: unittest.TestCase, prefix: str) -> tuple[Checkouts, str]:
    """One committed childless decomposition parent with a configured origin."""

    temporary = tempfile.TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=True)
    test.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    source = root / "source"
    source.mkdir()
    create_repository(source)
    _git(source, "remote", "add", "origin", POOL_REPOSITORY)
    task_path = source / "Tasks" / "NSC-004.yaml"
    selected = json.loads(task_path.read_text(encoding="utf-8"))
    selected.update(
        execution_scope="needs_execution_decomposition",
        execution_reason="Synthetic pooled-decomposition regression requires decomposition.",
    )
    _write_json(task_path, selected)
    _git(source, "add", "--", "Tasks/NSC-004.yaml")
    _git(source, "commit", "-m", "fixture: childless decomposition parent")
    return Checkouts(source, root / "checkouts"), _git(source, "rev-parse", "HEAD")


class PooledSameProviderLaunchTests(unittest.TestCase):
    """`claude,claude` reserves two role sessions and launches with them mounted."""

    def test_same_provider_launch_reserves_role_leases_and_pins_the_model(self):
        from Pipeline.AssistantControl import decomposition as decomposition_module
        from Pipeline.AssistantControl.decomposition_transport import POOL_LEASE_MOUNT

        manager, head = _decomposition_parent_fixture(self, "assistant-decompose-pooled-")
        commands: list[list[str]] = []
        real_run = subprocess.run

        def fake_run(command, *args, **kwargs):
            if list(command)[:2] == ["docker", "compose"]:
                commands.append(list(command))
                return subprocess.CompletedProcess(command, 1)
            return real_run(command, *args, **kwargs)

        with patch.dict(os.environ, {"NSC_CLAUDE_MODEL": POOL_MODEL}), \
                patch.object(decomposition_module, "decomposition_preflight",
                             return_value={"source_commit": head}), \
                patch.object(decomposition_module.subprocess, "run", side_effect=fake_run):
            record = decomposition_module.run(
                manager, "NSC-004", "nsc-004-pooled-run", providers="claude,claude",
                compose_project="assistant-pool", execution_authorized=True,
            )

        self.assertEqual(["claude", "claude"], record["providers"])
        pool = record["pool"]
        self.assertEqual(
            ["claude:decomposition_reviewer", "claude:task_decomposer"],
            sorted(pool["lease_keys"]),
        )
        self.assertEqual(POOL_REPOSITORY, pool["repository_identity"])
        self.assertTrue(pool["checkout_identity"].startswith("manifest-sha256:"))
        # The manifest whose bytes are that identity is AssistantControl's own
        # record, never a file inside Source.
        manifest = manager.records / "decomposition-pool" / "checkout-identity.json"
        self.assertTrue(manifest.is_file())
        self.assertFalse((manager.source / ".task-review-agent").exists())

        bundle = Path(pool["lease_bundle_path"])
        payload = json.loads(bundle.read_text(encoding="utf-8"))
        self.assertEqual("nsc-004-pooled-run", payload["run_id"])
        self.assertEqual("NSC-004", payload["task_id"])
        self.assertEqual(head, payload["source_commit"])
        self.assertEqual(POOL_REPOSITORY, payload["repository_identity"])
        self.assertEqual(sorted(pool["lease_keys"]), sorted(payload["leases"]))
        self.assertIsNone(payload["codex_resume_sandbox_argument"])

        self.assertEqual(1, len(commands))
        command = commands[0]
        self.assertEqual(
            ["docker", "compose", "-p", "assistant-pool", "run", "--rm", "-T"], command[:7],
        )
        self.assertEqual(["--volume", f"{bundle}:{POOL_LEASE_MOUNT}:ro"], command[7:9])
        self.assertEqual(["--env", f"NSC_CLAUDE_MODEL={POOL_MODEL}"], command[9:11])
        self.assertEqual("round-robin-decompose", command[11])
        self.assertEqual("claude,claude", command[command.index("--providers") + 1])
        self.assertEqual(POOL_LEASE_MOUNT, command[command.index("--role-session-leases") + 1])
        self.assertEqual(
            POOL_REPOSITORY, command[command.index("--scheduler-repository-identity") + 1],
        )
        self.assertEqual("failed", record["status"])

    def test_cross_provider_launch_reserves_nothing(self):
        from Pipeline.AssistantControl import decomposition as decomposition_module

        manager, head = _decomposition_parent_fixture(self, "assistant-decompose-cross-")
        commands: list[list[str]] = []
        real_run = subprocess.run

        def fake_run(command, *args, **kwargs):
            if list(command)[:2] == ["docker", "compose"]:
                commands.append(list(command))
                return subprocess.CompletedProcess(command, 1)
            return real_run(command, *args, **kwargs)

        with patch.object(decomposition_module, "decomposition_preflight",
                          return_value={"source_commit": head}), \
                patch.object(decomposition_module.subprocess, "run", side_effect=fake_run):
            record = decomposition_module.run(
                manager, "NSC-004", "nsc-004-cross-run", providers="claude,codex",
                compose_project="assistant-pool", execution_authorized=True,
            )
        self.assertIsNone(record.get("pool"))
        self.assertIsNone(record.get("pool_lifecycle"))
        self.assertNotIn("--volume", commands[0])
        self.assertNotIn("--role-session-leases", commands[0])

    def test_a_pooled_run_id_the_pool_cannot_own_is_refused_before_any_record(self):
        from Pipeline.AssistantControl import decomposition as decomposition_module

        manager, head = _decomposition_parent_fixture(self, "assistant-decompose-runid-")
        with patch.object(decomposition_module, "decomposition_preflight",
                          return_value={"source_commit": head}):
            with self.assertRaisesRegex(ValueError, "pooled decomposition run id"):
                decomposition_module.run(
                    manager, "NSC-004", "NSC-004.Pooled_Run", providers="claude,claude",
                    compose_project="assistant-pool", execution_authorized=True,
                )
        self.assertFalse((manager.records / "NSC-004.decomposition.json").exists())


class FakePoolOwner:
    """Records the exact lifecycle calls AssistantControl makes on the pool."""

    def __init__(self, bundle: Path, *, settle_error: BaseException | None = None):
        self.bundle = bundle
        self.settle_error = settle_error
        self.calls: list[tuple] = []

    def prepare(self, **kwargs):
        self.calls.append(("prepare", kwargs))
        return {
            "run_id": kwargs["run_id"],
            "repository_identity": POOL_REPOSITORY,
            "compose_project": "assistant-pool",
            "checkout_identity": "manifest-sha256:" + "0" * 64,
            "lease_bundle_path": str(self.bundle),
            "leases": {key: {"lease_id": value} for key, value in POOL_LEASE_IDS.items()},
            "skipped_keys": [],
            "provider_environment": {"NSC_CLAUDE_MODEL": POOL_MODEL, "NSC_OPENAI_CODEX_MODEL": ""},
        }

    def settle(self, *, run_id, run_dir):
        self.calls.append(("settle", run_id, str(run_dir)))
        if self.settle_error is not None:
            raise self.settle_error
        return {"run_id": run_id, "run_status": "review_ready", "leases": {}}

    def cancel_unstarted(self, *, run_id):
        self.calls.append(("cancel_unstarted", run_id))

    def close(self):
        self.calls.append(("close",))

    def actions(self) -> list[str]:
        return [call[0] for call in self.calls]


class PooledLifecycleTests(unittest.TestCase):
    """Settle from artifacts, cancel only a proven non-start, always close."""

    def launch(self, prefix: str, *, exit_code: int = 0, run_directory: bool = True,
               start_error: BaseException | None = None,
               settle_error: BaseException | None = None):
        from Pipeline.AssistantControl import decomposition as decomposition_module

        manager, head = _decomposition_parent_fixture(self, prefix)
        run_id = "nsc-004-lifecycle-run"
        artifact_root = (manager.records / "decomposition-runs").resolve() / run_id
        bundle = manager.root / "fixture.leases.json"
        manager.root.mkdir(parents=True, exist_ok=True)
        bundle.write_text("{}\n", encoding="utf-8", newline="\n")
        owner = FakePoolOwner(bundle, settle_error=settle_error)
        real_run = subprocess.run

        def fake_run(command, *args, **kwargs):
            if list(command)[:2] == ["docker", "compose"]:
                if start_error is not None:
                    raise start_error
                if run_directory:
                    artifact_root.mkdir(parents=True, exist_ok=True)
                return subprocess.CompletedProcess(command, exit_code)
            return real_run(command, *args, **kwargs)

        context = [
            patch.object(decomposition_module, "_pool_owner", return_value=owner),
            patch.object(decomposition_module, "decomposition_preflight",
                         return_value={"source_commit": head}),
            patch.object(decomposition_module.subprocess, "run", side_effect=fake_run),
            patch.object(decomposition_module, "_verify_review",
                         return_value={"status": "review_ready", "child_ids": ["NSC-1001"]}),
        ]
        for entered in context:
            entered.start()
            self.addCleanup(entered.stop)
        return decomposition_module, manager, owner, run_id, artifact_root

    def test_a_successful_run_settles_from_its_run_directory_and_closes(self):
        module, manager, owner, run_id, artifact_root = self.launch("assistant-pool-settle-")
        record = module.run(
            manager, "NSC-004", run_id, providers="claude,claude",
            compose_project="assistant-pool", execution_authorized=True,
        )
        self.assertEqual("review_ready", record["status"])
        self.assertEqual(["prepare", "settle", "close"], owner.actions())
        self.assertEqual(("settle", run_id, str(artifact_root)), owner.calls[1])
        prepared = owner.calls[0][1]
        self.assertEqual("round_robin_d1b2", prepared["decomposition_mode"])
        self.assertEqual(("claude", "claude"), prepared["provider_order"])
        self.assertEqual(2, prepared["max_calls"])
        self.assertEqual(record["source_commit"], prepared["source_commit"])
        self.assertEqual("settled", record["pool_lifecycle"]["status"])

    def test_a_failed_run_that_produced_a_run_directory_still_settles(self):
        module, manager, owner, run_id, artifact_root = self.launch(
            "assistant-pool-failed-", exit_code=1,
        )
        record = module.run(
            manager, "NSC-004", run_id, providers="claude,claude",
            compose_project="assistant-pool", execution_authorized=True,
        )
        self.assertEqual("failed", record["status"])
        self.assertEqual(["prepare", "settle", "close"], owner.actions())
        self.assertEqual("settled", record["pool_lifecycle"]["status"])

    def test_a_provider_that_never_started_returns_the_leases_uncharged(self):
        module, manager, owner, run_id, _root = self.launch(
            "assistant-pool-unstarted-", start_error=OSError("docker is unavailable"),
        )
        with self.assertRaises(OSError):
            module.run(
                manager, "NSC-004", run_id, providers="claude,claude",
                compose_project="assistant-pool", execution_authorized=True,
            )
        self.assertEqual(["prepare", "cancel_unstarted", "close"], owner.actions())
        record = json.loads(
            (manager.records / "NSC-004.decomposition.json").read_text(encoding="utf-8")
        )
        self.assertEqual("failed", record["status"])
        self.assertEqual("cancelled_unstarted", record["pool_lifecycle"]["status"])

    def test_a_run_without_a_run_directory_is_never_cancelled_as_unstarted(self):
        module, manager, owner, run_id, _root = self.launch(
            "assistant-pool-nodir-", exit_code=1, run_directory=False,
        )
        record = module.run(
            manager, "NSC-004", run_id, providers="claude,claude",
            compose_project="assistant-pool", execution_authorized=True,
        )
        self.assertEqual("failed", record["status"])
        # The provider may have run: the leases stay active and the next owner
        # reclaims them as stranded.
        self.assertEqual(["prepare", "close"], owner.actions())
        self.assertEqual("run_directory_missing", record["pool_lifecycle"]["status"])

    def test_a_settle_failure_degrades_pooling_and_never_fails_a_good_run(self):
        from Pipeline.TaskReviewAgent.decomposition_session_pool import (
            DecompositionSessionPoolError,
        )

        module, manager, owner, run_id, _root = self.launch(
            "assistant-pool-degraded-",
            settle_error=DecompositionSessionPoolError("fixture settlement failure"),
        )
        record = module.run(
            manager, "NSC-004", run_id, providers="claude,claude",
            compose_project="assistant-pool", execution_authorized=True,
        )
        self.assertEqual("review_ready", record["status"])
        self.assertEqual(["prepare", "settle", "close"], owner.actions())
        self.assertEqual("pool_degraded", record["pool_lifecycle"]["status"])
        self.assertIn("fixture settlement failure", record["pool_lifecycle"]["error"])


class SameProviderReviewIndependenceTests(unittest.TestCase):
    """`same_provider_separate_sessions` is admitted only for a pooled same-provider run."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="assistant-d1c-same-provider-")
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
            execution_reason="Synthetic same-provider regression requires decomposition.",
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
            proposal, parent_task=parent, existing_reconciliation_keys=graph.plan.id_map,
        )
        stored_plan = plan_graph_delta(graph, decomposition.parent_task, decomposition)
        head = _git(source, "rev-parse", "HEAD")
        tree = _git(source, "rev-parse", "HEAD^{tree}")
        branch = _git(source, "branch", "--show-current")
        task = load_committed_task(source, self.task_id, commit=head)
        self.manager = Checkouts(source, root / "checkouts")
        self.manager.records.mkdir(parents=True)
        self.run_id = "nsc-004-same-provider-run"
        output_root = (self.manager.records / "decomposition-runs").resolve()
        self.artifact_root = output_root / self.run_id
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
        self.head, self.tree, self.branch, self.task = head, tree, branch, task
        self.output_root = output_root

    # -- exact fixtures ----------------------------------------------------

    def pooled_sessions(self, **overrides) -> dict:
        sessions = {}
        for index, (key, lease_id) in enumerate(sorted(POOL_LEASE_IDS.items())):
            role = key.split(":", 1)[1]
            sessions[key] = {
                "lease_id": lease_id,
                "record_id": f"{index}0000000-0000-4000-8000-000000000000",
                "role": role,
                "provider_identifier": "claude-code",
                "invoked": True,
                "identity_unproven": None,
                "confirmed_session": {
                    "provider_identifier": "claude-code",
                    "role": role,
                    "mode": "start",
                    "session_id": f"{index + 3}3333333-3333-4333-8333-333333333333",
                },
            }
        sessions.update(overrides)
        return sessions

    def run_result(self, providers, *, independence, sessions=None) -> dict:
        return {
            "schema_version": "1.0",
            "mode": "round_robin_d1b2",
            "run_id": self.run_id,
            "task_id": self.task_id,
            "provider_order": list(providers),
            "max_calls": 2,
            "calls_used": 2,
            "run_status": "review_ready",
            "decision": "decomposed",
            "review_independence": independence,
            "authority": "review_only_not_applied",
            "unresolved_findings": [],
            "rejection_reasons": [],
            "source_identity": {"head_commit": self.head, "head_tree": self.tree},
            "task_execution_contract_identity": {
                "revision": self.task["contract_revision"],
                "sha256": self.task["task_contract_sha256"],
            },
            "latest_candidate": self.candidate,
            "independent_approver_provider": providers[1],
            "pooled_sessions": sessions,
            "rounds": [
                {
                    "role": "task_decomposer", "correction_of_round": None,
                    "requested_provider": providers[0], "actual_model": POOL_MODEL,
                    "agent_status": "succeeded", "status": "candidate_valid",
                    "candidate_after": self.candidate,
                },
                {
                    "role": "decomposition_reviewer", "correction_of_round": None,
                    "requested_provider": providers[1], "actual_model": POOL_MODEL,
                    "agent_status": "succeeded", "status": "independent_pass",
                    "verdict": "pass", "candidate_before": self.candidate,
                    "candidate_after": None,
                },
            ],
            "finding_history": [{
                "verdict": "pass",
                "reviewed_candidate_sha256": self.digest,
                "findings": [],
            }],
        }

    def record(self, providers, *, pool=True, lease_ids=None) -> dict:
        value = {
            "schema_version": "assistant-decomposition/v1",
            "task_id": self.task_id,
            "run_id": self.run_id,
            "source": str(self.manager.source),
            "source_commit": self.head,
            "source_tree": self.tree,
            "source_branch": self.branch,
            "task_contract_sha256": self.task["task_contract_sha256"],
            "providers": list(providers),
            "output_root": str(self.output_root),
            "artifact_root": str(self.artifact_root),
            "status": "review_ready",
        }
        if pool:
            value["pool"] = {
                "lease_bundle_path": str(self.manager.records / "fixture.leases.json"),
                "repository_identity": POOL_REPOSITORY,
                "checkout_identity": "manifest-sha256:" + "0" * 64,
                "compose_project": "assistant-pool",
                "lease_keys": sorted(POOL_LEASE_IDS),
                "lease_ids": dict(lease_ids or POOL_LEASE_IDS),
            }
        return value

    def verify(self, providers, *, independence, sessions=None, pool=True, lease_ids=None):
        _write_json(
            self.artifact_root / "decomposition_run_result.json",
            self.run_result(providers, independence=independence, sessions=sessions),
        )
        return _verify_review(self.manager, self.record(providers, pool=pool, lease_ids=lease_ids))

    # -- accepted ----------------------------------------------------------

    def test_pooled_same_provider_run_verifies(self):
        review = self.verify(
            ("claude", "claude"),
            independence="same_provider_separate_sessions",
            sessions=self.pooled_sessions(),
        )
        self.assertEqual("review_ready", review["status"])
        self.assertEqual(self.digest, review["candidate_sha256"])
        self.assertEqual("claude", review["reviewer_provider"])

    def test_cross_provider_verification_is_unchanged(self):
        review = self.verify(("claude", "codex"), independence="cross_provider", pool=False)
        self.assertEqual("review_ready", review["status"])

    # -- refused -----------------------------------------------------------

    def test_a_same_provider_run_may_not_claim_cross_provider_independence(self):
        with self.assertRaisesRegex(ValueError, "review_independence"):
            self.verify(
                ("claude", "claude"), independence="cross_provider",
                sessions=self.pooled_sessions(),
            )

    def test_a_cross_provider_run_may_not_claim_separate_sessions(self):
        with self.assertRaisesRegex(ValueError, "review_independence"):
            self.verify(
                ("claude", "codex"), independence="same_provider_separate_sessions",
                pool=False,
            )

    def test_a_same_provider_record_without_a_lease_reservation_is_refused(self):
        with self.assertRaisesRegex(ValueError, "lease reservation"):
            self.verify(
                ("claude", "claude"), independence="same_provider_separate_sessions",
                sessions=self.pooled_sessions(), pool=False,
            )

    def test_a_same_provider_run_that_used_other_leases_is_refused(self):
        with self.assertRaisesRegex(ValueError, "reserved role leases"):
            self.verify(
                ("claude", "claude"), independence="same_provider_separate_sessions",
                sessions=self.pooled_sessions(),
                lease_ids={key: "99999999-9999-4999-8999-999999999999"
                           for key in POOL_LEASE_IDS},
            )
        with self.assertRaisesRegex(ValueError, "reserved role leases"):
            self.verify(
                ("claude", "claude"), independence="same_provider_separate_sessions",
                sessions=None,
            )
        partial = self.pooled_sessions()
        del partial["claude:decomposition_reviewer"]
        with self.assertRaisesRegex(ValueError, "reserved role leases"):
            self.verify(
                ("claude", "claude"), independence="same_provider_separate_sessions",
                sessions=partial,
            )


if __name__ == "__main__":
    unittest.main()
