"""Real Git proofs for local dependency acceptance; candidate review is fixture data."""
import json
import unittest

from Pipeline.AssistantControl import test_review as fixture
from Pipeline.AssistantControl.dependencies import approved_integration


class AcceptanceTests(unittest.TestCase):
    setUp = fixture.ReviewTests.setUp
    run_git = fixture.ReviewTests.run_git
    manager = fixture.ReviewTests.manager
    candidate = fixture.ReviewTests.candidate
    approve = fixture.ReviewTests.approve

    def test_approval_alone_cannot_unlock_but_integrated_candidate_can(self):
        gate, record, commit, branch = self.candidate()
        self.approve(gate, commit)
        def proof(head):
            return approved_integration(gate.checkouts.source, gate.checkouts.records, "NSC-042", head)
        self.assertIsNone(proof(record["source_commit"]))
        gate.integrate("NSC-042", expected_source_commit=record["source_commit"], target_branch=branch)
        self.assertEqual(commit, proof(commit)["commit"])
        self.assertIsNone(proof(record["source_commit"]))
        path = gate.checkouts.records / "NSC-042.json"
        saved = json.loads(path.read_text())
        saved["approval"]["commit"] = record["source_commit"]
        path.write_text(json.dumps(saved))
        self.assertIsNone(proof(commit))

    def test_changed_contract_or_corrupt_receipt_cannot_unlock(self):
        gate, record, commit, branch = self.candidate()
        self.approve(gate, commit)
        gate.integrate("NSC-042", expected_source_commit=record["source_commit"], target_branch=branch)
        path = self.root / "Tasks/NSC-042.yaml"
        task = json.loads(path.read_text())
        task["title"] = "Changed requirements fixture"
        path.write_text(json.dumps(task))
        self.run_git("add", "Tasks/NSC-042.yaml")
        self.run_git("commit", "-m", "Change task fixture")
        head = self.run_git("rev-parse", "HEAD").decode().strip()
        self.assertIsNone(approved_integration(gate.checkouts.source, gate.checkouts.records, "NSC-042", head))
        (gate.checkouts.records / "NSC-042.json").write_text("[]")
        self.assertIsNone(approved_integration(gate.checkouts.source, gate.checkouts.records, "NSC-042", head))


if __name__ == "__main__":
    unittest.main()
