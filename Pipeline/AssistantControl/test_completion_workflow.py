"""One-task offline completion demonstration, not a live provider/Unity proof.

The fixture seeds a real Git candidate and fixture-generated crew artifacts.
Actual bridge verification, commit recovery, human gate, merge, preservation and
viewer projection then execute. The approval below is explicitly test-only.
"""
import unittest
from pathlib import Path

from Pipeline.AssistantControl import test_candidate as fixture
from Pipeline.AssistantControl.candidate import register_candidate
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.AssistantControl.successful_tasks import preserve_success
from Pipeline.AssistantControl.viewer import AssistantSnapshot


class CompletionWorkflowTests(unittest.TestCase):
    setUp = fixture.CandidateRecoveryTests.setUp
    git = fixture.CandidateRecoveryTests.git
    git_bytes = fixture.CandidateRecoveryTests.git_bytes
    valid = fixture.CandidateRecoveryTests.valid

    def test_fixture_candidate_cannot_integrate_until_exact_approval_then_is_preserved(self):
        candidate = register_candidate(self.checkouts, "NSC-042", self.run_id,
                                       {"execution_model": "recovery-model", "crew_profile": "full",
                                        "validation_profile": "full_relevant"})
        commit = candidate["candidate"]["commit"]
        gate = ReviewGate(self.checkouts)
        source_before = candidate["source_commit"]
        branch = self.git("branch", "--show-current").decode().strip()
        reader = AssistantSnapshot(self.source, self.checkouts.root)
        def row():
            return next(item for item in reader.build()["tasks"] if item["id"] == "NSC-042")
        self.assertEqual("human_action", row()["state"])
        self.assertEqual(commit, row()["candidate_commit"])
        with self.assertRaisesRegex(ValueError, "approve"):
            gate.integrate("NSC-042", expected_source_commit=source_before, target_branch=branch)
        self.assertEqual(source_before, self.git("rev-parse", "HEAD").decode().strip())
        gate.decide("NSC-042", tested_commit=commit, decision="approve",
                    message="Fixture-only approval; no real Vincent approval or Unity test")
        gate.integrate("NSC-042", expected_source_commit=source_before, target_branch=branch)
        result = preserve_success(self.checkouts, "NSC-042", Path(self.temp.name) / "SuccessfullTasks")
        self.assertEqual(commit, self.git("rev-parse", "HEAD").decode().strip())
        self.assertEqual("local_accepted", row()["state"])
        self.assertEqual(commit, row()["successful_project_commit"])
        self.assertEqual(result["successful_project"]["path"], row()["successful_project_path"])


if __name__ == "__main__":
    unittest.main()
