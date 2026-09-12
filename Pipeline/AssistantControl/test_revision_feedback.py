"""Revision feedback tests; context is a labeled pre-provider fixture seam."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from Pipeline.AssistantControl.revision_feedback import (
    RevisionFeedbackError,
    prepare_revision_feedback,
)


class RevisionFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source"
        self.checkout_root = root / "checkouts"
        self.checkout = self.checkout_root / "NSC-042"
        self.output = self.checkout / "Pipeline/ExecutionCrew/outputs"
        self.records = self.checkout_root / ".assistant-control"
        self.source.mkdir(parents=True)
        self.checkout.mkdir(parents=True)
        self.output.mkdir(parents=True)
        self.records.mkdir(parents=True)
        (self.source / "HEAD").write_text("source-head")
        self.run_id = "crew-old"
        run = self.output / self.run_id
        run.mkdir()
        result = b'{"run_id":"crew-old"}\n'
        patch_bytes = b"diff --git a/A b/A\n"
        (run / "crew_result.json").write_bytes(result)
        (run / "candidate.patch").write_bytes(patch_bytes)
        self.result_hash = hashlib.sha256(result).hexdigest()
        self.patch_hash = hashlib.sha256(patch_bytes).hexdigest()
        self.receipt = {
            "run_id": self.run_id, "task_id": "NSC-042", "lease_id": "lease-2",
            "plan_id": "plan-2", "task_contract_sha256": "c" * 64,
            "execution_result_sha256": self.result_hash,
            "candidate_patch_sha256": self.patch_hash,
            "candidate_commit": "b" * 40, "candidate_tree": "d" * 40,
            "candidate_parent": "a" * 40, "source_base": "a" * 40,
        }
        self.record = {
            "task_id": "NSC-042", "source": str(self.source),
            "checkout": str(self.checkout), "source_commit": "b" * 40,
            "task_contract_sha256": "c" * 64,
            "revision": {"candidate_commit": "b" * 40, "history_index": 0,
                          "rejected_review": {"commit": "b" * 40, "decision": "reject",
                                               "message": "Fix the failing assertion."}},
            "revision_history": [{
                "source_commit": "a" * 40,
                "candidate": {"commit": "b" * 40, "run_id": self.run_id,
                               "tree": "d" * 40, "parent": "a" * 40,
                               "lease_id": "lease-2", "plan_id": "plan-2",
                               "receipt": self.receipt},
                "human_review": {"commit": "b" * 40, "decision": "reject",
                                  "message": "Fix the failing assertion."},
            }],
        }
        self.reservation = {
            "source": str(self.source), "task_id": "NSC-042",
            "checkout_root": str(self.checkout_root), "checkout": str(self.checkout),
            "source_head": "b" * 40, "task_contract_sha256": "c" * 64,
            "lease_id": "lease-2", "plan_id": "plan-2",
            "plan": {"existing_implementation_paths": ["A"],
                      "new_implementation_paths": [],
                      "existing_test_paths": ["T"], "new_test_paths": []},
        }
        self.config = {"provider": "claude", "execution_model": "model-x",
                       "bridge": {"crew_profile": "full", "validation_profile": "full_relevant"}}
        self.context = SimpleNamespace(
            task_id="NSC-042", prior_run_id=self.run_id, provider="claude",
            execution_model="model-x", execution_reasoning_effort=None,
            crew_profile="full", validation_profile="full_relevant",
            implementation_paths=("A",), new_implementation_paths=(),
            test_paths=("T",), new_test_paths=(),
        )

    def _prepare(self, context=None):
        manager = SimpleNamespace(source=self.source, root=self.checkout_root, records=self.records)
        with patch("Pipeline.AssistantControl.revision_feedback.git", return_value=b"source-head\n"), \
             patch("Pipeline.AssistantControl.revision_feedback._revision_baseline",
                   return_value="b" * 40), \
             patch("Pipeline.ExecutionCrew.run_crew.capture_source", return_value=object()), \
             patch("Pipeline.ExecutionCrew.run_crew.load_retry_context",
                   return_value=context or self.context) as loader:
            result = prepare_revision_feedback(manager, self.record, self.reservation, self.config)
        return result, loader

    def test_no_revision_is_cheap_and_returns_no_retry_kwargs(self):
        manager = SimpleNamespace(source=self.source, root=self.checkout_root, records=self.records)
        with patch("Pipeline.AssistantControl.revision_feedback.git") as git:
            self.assertEqual({}, prepare_revision_feedback(manager, {"task_id": "NSC-042"}, {}, {}))
            git.assert_not_called()

    def test_stages_exact_archived_run_and_feedback_for_retry(self):
        result, loader = self._prepare()
        self.assertEqual(self.run_id, result["retry_run_id"])
        feedback = result["feedback_file"]
        self.assertEqual("Fix the failing assertion.", feedback.read_text(encoding="utf-8"))
        loader.assert_called_once()
        call = loader.call_args.kwargs
        self.assertEqual(self.checkout.resolve(), call["source"])
        self.assertEqual(self.output.resolve(), call["output_root"])
        self.assertEqual(self.run_id, call["prior_run_id"])
        self.assertEqual(feedback.resolve(), call["feedback_file"])
        self.assertTrue((self.records / "revision-feedback" / (hashlib.sha256(self.run_id.encode()).hexdigest() + ".json")).is_file())

    def test_changed_archived_patch_is_rejected_before_context(self):
        (self.output / self.run_id / "candidate.patch").write_bytes(b"tampered")
        manager = SimpleNamespace(source=self.source, root=self.checkout_root, records=self.records)
        with patch("Pipeline.AssistantControl.revision_feedback.git", return_value=b"source-head\n"), \
             patch("Pipeline.AssistantControl.revision_feedback._revision_baseline", return_value="b" * 40), \
             patch("Pipeline.ExecutionCrew.run_crew.load_retry_context") as loader:
            with self.assertRaisesRegex(RevisionFeedbackError, "patch hash"):
                prepare_revision_feedback(manager, self.record, self.reservation, self.config)
        loader.assert_not_called()

    def test_incompatible_context_settings_fail_before_provider(self):
        context = SimpleNamespace(**{**self.context.__dict__, "validation_profile": "full"})
        with self.assertRaisesRegex(RevisionFeedbackError, "rigor profile"):
            self._prepare(context)


if __name__ == "__main__":
    unittest.main()
