from __future__ import annotations

import hashlib
import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl.result_inspection import (
    ResultInspectionError,
    inspect_result,
)


class FakeCheckouts:
    def __init__(self, record):
        self.record = record

    def observe(self, task_id):
        if task_id != self.record["task_id"]:
            raise ValueError("wrong task")
        return json.loads(json.dumps(self.record))


class ResultInspectionTests(unittest.TestCase):
    def setUp(self):
        parent = Path.cwd() / ".test-work"
        parent.mkdir(exist_ok=True)
        self.root = parent / f"assistant-result-inspection-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.checkout = self.root / "NSC-042"
        output = self.checkout / "Pipeline/ExecutionCrew/outputs/crew-one"
        output.mkdir(parents=True)
        self.result_path = output / "crew_result.json"
        self.patch_path = output / "candidate.patch"
        changed = ["Assets/Code.cs"]
        result = {
            "task_id": "NSC-042", "run_id": "crew-one",
            "source_head": "a" * 40, "crew_status": "review_ready",
            "final_actual_changed_paths": changed, "attempts_used": 1,
            "duration_seconds": 12.5, "validator_status": "pass",
            "task_contract_identity": {"sha256": "b" * 64},
            "candidate_patch_sha256": None,
            "human_next_step": "Test the exact candidate",
        }
        self.patch_path.write_bytes(b"diff --git a/Assets/Code.cs b/Assets/Code.cs\n")
        patch_hash = hashlib.sha256(self.patch_path.read_bytes()).hexdigest()
        result["candidate_patch_sha256"] = patch_hash
        self.result_path.write_text(json.dumps(result), encoding="utf-8", newline="\n")
        receipt = {
            "schema_version": "1.0", "task_id": "NSC-042",
            "run_id": "crew-one", "source_head": "a" * 40,
            "task_contract_sha256": "b" * 64, "crew_status": "review_ready",
            "result_path": str(self.result_path),
            "result_sha256": hashlib.sha256(self.result_path.read_bytes()).hexdigest(),
            "candidate_path": str(self.patch_path), "candidate_sha256": patch_hash,
            "final_actual_changed_paths": changed, "rejection_reasons": [],
        }
        self.record = {
            "task_id": "NSC-042", "checkout": str(self.checkout),
            "worker": {
                "status": "succeeded", "run_id": "assistant-one",
                "crew_run_id": "crew-one", "source_head": "a" * 40,
                "task_contract_sha256": "b" * 64,
                "capacity_released": True, "receipt": receipt,
            },
        }

    def test_authenticates_and_summarizes_exact_result_and_patch(self):
        with patch("Pipeline.AssistantControl.result_inspection.load_committed_task"):
            result = inspect_result(FakeCheckouts(self.record), "NSC-042")
        self.assertTrue(result["authenticated"])
        self.assertFalse(result["mutations_performed"])
        self.assertEqual("review_ready", result["crew_status"])
        self.assertEqual(str(self.patch_path.resolve()), result["candidate_patch"]["path"])
        self.assertEqual(["Assets/Code.cs"], result["final_actual_changed_paths"])

    def test_tampered_result_is_rejected(self):
        self.result_path.write_text("{}", encoding="utf-8")
        with patch("Pipeline.AssistantControl.result_inspection.load_committed_task"), \
             self.assertRaisesRegex(ResultInspectionError, "bytes differ"):
            inspect_result(FakeCheckouts(self.record), "NSC-042")


if __name__ == "__main__":
    unittest.main()
