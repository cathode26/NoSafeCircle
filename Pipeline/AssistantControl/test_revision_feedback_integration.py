"""Offline real retry integration over a committed revision base.

This deliberately uses the small fixture provider from ExecutionCrew's smoke
fixture. It does not invoke a paid provider, Unity, Docker, or the smoke main.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.revision_feedback import prepare_revision_feedback
from Pipeline.ExecutionCrew.run_crew import run_crew
from Pipeline.ExecutionCrew.tests.execution_crew_smoke_test import (
    State,
    execute,
    factory,
    fixture,
)


class RevisionFeedbackIntegrationTests(unittest.TestCase):
    def git(self, root: Path, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True,
            text=True, check=check,
        )
        return result.stdout.strip()

    def test_revision_feedback_retries_on_already_present_candidate_base(self):
        with tempfile.TemporaryDirectory(prefix="assistant-revision-feedback-") as temporary:
            root = Path(temporary)
            source = fixture(root)
            original_head = self.git(source, "rev-parse", "HEAD")
            original_status = self.git(source, "status", "--porcelain=v1", "--untracked-files=all")
            original_outputs = root / "original-outputs"
            prior, prior_state, prior_dir = execute(
                source, original_outputs, "seed_preserve", 910, provider="claude",
            )
            self.assertEqual("review_ready", prior["crew_status"])
            self.assertFalse(prior_state.calls == [])
            patch_bytes = (prior_dir / "candidate.patch").read_bytes()
            result_bytes = (prior_dir / "crew_result.json").read_bytes()
            prior_run_id = prior["run_id"]
            candidate_sha = hashlib.sha256(patch_bytes).hexdigest()
            result_sha = hashlib.sha256(result_bytes).hexdigest()

            checkout_root = root / "checkouts"
            checkout = checkout_root / "NSC-005"
            subprocess.run(["git", "clone", "-q", str(source), str(checkout)], check=True)
            self.git(checkout, "config", "user.name", "Crew Smoke")
            self.git(checkout, "config", "user.email", "crew@example.invalid")
            subprocess.run(["git", "-C", str(checkout), "apply", "--binary", str(prior_dir / "candidate.patch")], check=True)
            self.git(checkout, "add", "Assets/Scripts/PlayerMana.cs", "Assets/Tests/PlayerManaTests.cs")
            self.git(checkout, "commit", "-qm", "fixture rejected candidate")
            candidate_commit = self.git(checkout, "rev-parse", "HEAD")
            candidate_tree = self.git(checkout, "rev-parse", "HEAD^{tree}")
            self.assertNotEqual(original_head, candidate_commit)

            output_root = checkout / "Pipeline" / "ExecutionCrew" / "outputs"
            output_root.mkdir(parents=True)
            self.git(checkout, "config", "core.excludesFile", "")
            (checkout / ".git" / "info" / "exclude").write_text(
                "Pipeline/ExecutionCrew/outputs/\n", encoding="utf-8",
            )
            shutil.copytree(prior_dir, output_root / prior_run_id)
            feedback_text = "Human review: preserve the candidate and add the regression correction.\n"
            feedback_source = root / "feedback.txt"
            feedback_source.write_text(feedback_text, encoding="utf-8", newline="\n")

            manager = Checkouts(source, checkout_root)
            manager.records.mkdir(parents=True)
            task_contract_sha = prior["task_contract_identity"]["sha256"]
            candidate_record = {
                "task_id": "NSC-005", "run_id": prior_run_id,
                "lease_id": "revision-lease", "plan_id": "revision-plan",
                "commit": candidate_commit, "tree": candidate_tree,
                "parent": original_head,
                "receipt": {
                    "task_id": "NSC-005", "run_id": prior_run_id,
                    "lease_id": "revision-lease", "plan_id": "revision-plan",
                    "candidate_commit": candidate_commit, "candidate_tree": candidate_tree,
                    "candidate_parent": original_head, "source_base": original_head,
                    "task_contract_sha256": task_contract_sha,
                    "execution_result_sha256": result_sha,
                    "candidate_patch_sha256": candidate_sha,
                },
            }
            record = {
                "schema_version": "assistant-checkout/v1", "task_id": "NSC-005",
                "source": str(source.resolve()), "checkout": str(checkout.resolve()),
                "source_commit": candidate_commit, "task_contract_sha256": task_contract_sha,
                "branch": self.git(checkout, "branch", "--show-current"),
                "status": "prepared", "revision": {
                    "candidate_commit": candidate_commit, "candidate_tree": candidate_tree,
                    "source_commit": original_head,
                    "source_tree": self.git(source, "rev-parse", "HEAD^{tree}"),
                    "task_contract_sha256": task_contract_sha,
                    "rejected_review": {"commit": candidate_commit, "decision": "reject",
                                         "message": feedback_text},
                    "history_index": 0,
                },
                "revision_history": [{
                    "schema_version": "assistant-revision-history/v1", "task_id": "NSC-005",
                    "source_commit": original_head, "candidate": candidate_record,
                    "human_review": {"commit": candidate_commit, "decision": "reject",
                                      "message": feedback_text},
                    "candidate_tree": candidate_tree,
                    "task_contract_sha256": task_contract_sha,
                }],
            }
            write_record(manager.records / "NSC-005.json", record)

            prepared = prepare_revision_feedback(
                manager, record, {
                    "plan": {
                        "existing_implementation_paths": ["Assets/Scripts/PlayerMana.cs"],
                        "new_implementation_paths": [],
                        "existing_test_paths": ["Assets/Tests/PlayerManaTests.cs"],
                        "new_test_paths": [],
                    },
                },
                {"provider": "claude", "execution_model": prior["execution_model"]},
            )
            feedback_file = prepared["feedback_file"]
            self.assertEqual(feedback_text, feedback_file.read_text(encoding="utf-8"))

            state = State("retry_test_only", checkout, feedback_text)
            result = run_crew(
                source=checkout, output_root=output_root,
                run_id="revision-feedback-910-new", retry_run_id=prior_run_id,
                review_feedback_file=feedback_file, provider_factory=factory(state),
                _require_physical_read_only_source=False,
            )
            self.assertEqual("review_ready", result["crew_status"])
            self.assertEqual("already_present", result["retry_seed_mode"])
            self.assertEqual(candidate_commit, result["source_head"])
            self.assertEqual(candidate_tree, result["source_tree"])
            self.assertEqual(original_head, self.git(source, "rev-parse", "HEAD"))
            self.assertEqual(original_status, self.git(source, "status", "--porcelain=v1", "--untracked-files=all"))
            for role in ("implementer", "test_author", "validator"):
                requests = [request for called_role, request, _ in state.calls if called_role == role]
                self.assertTrue(requests, role)
                self.assertTrue(all(feedback_text.strip() in request.prompt for request in requests), role)


if __name__ == "__main__":
    unittest.main()
