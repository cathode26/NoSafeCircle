"""readiness must say when a task it calls ready is already delivered.

`ready_to_reserve` means "may this be admitted". It does NOT mean "is there work
here", and nothing in the result said so -- so a fleet census of 30 prepared
records produced "23 tasks one refresh from dispatchable" when TWENTY-TWO of the
thirty were already `conformant`. The Producer Agent caught it and named the
mechanism: the signal cannot distinguish ready to start from already finished.

THE DECISIVE TEST IS `test_a_delivered_task_is_flagged_AND_STILL_READY`. An
advisory that blocked would recreate the readiness-versus-reserve disagreement
fixed twice tonight, in the other direction, and refuse 22 records that `reserve`
admits. The flag exists to stop the result being silent, not to gate anything.

Every case builds throwaway repositories through the admission fixture.
"""
from __future__ import annotations

import unittest

from Pipeline.AssistantControl.readiness import inspect_readiness
from Pipeline.AssistantControl.test_admission import AdmissionTests

TASK = "NSC-042"
EVIDENCE = f"Pipeline/TaskGraph/evidence/{TASK}/records/DEL-{TASK}-abc123.json"


class ReadinessDeliveryAdvisory(AdmissionTests):
    def commit_evidence(self, path: str = EVIDENCE) -> None:
        target = self.source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"record_id": "DEL"}\n', encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "delivery evidence")

    def view(self):
        return inspect_readiness(self.manager_one, TASK,
                                 dependency_reader=self.dependencies)

    def test_a_task_with_no_committed_evidence_is_not_flagged(self):
        self.plan(self.manager_one, TASK, "lease-042")
        view = self.view()
        self.assertFalse(view["committed_delivery_evidence"])
        self.assertTrue(view["ready_to_reserve"], view["problems"])

    def test_a_delivered_task_is_flagged_AND_STILL_READY(self):
        """The decisive one. Both halves matter: the flag must fire, and it must
        not become a refusal -- `reserve` admits this record, and an advisory that
        blocked would put the two answers back into disagreement."""
        self.commit_evidence()
        self.plan(self.manager_one, TASK, "lease-042")
        view = self.view()
        self.assertTrue(view["committed_delivery_evidence"])
        self.assertTrue(view["ready_to_reserve"], view["problems"])
        self.assertNotIn("committed_delivery_evidence", view["problems"])

    def test_the_flag_reads_the_commit_and_not_the_working_tree(self):
        """A proxy answering from the worktree would report a delivery that is not
        committed -- and what main contains is the whole point of the field."""
        self.plan(self.manager_one, TASK, "lease-042")
        target = self.source / EVIDENCE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"record_id": "UNCOMMITTED"}\n', encoding="utf-8")
        self.assertFalse(self.view()["committed_delivery_evidence"])

    def test_another_tasks_evidence_does_not_flag_this_one(self):
        """The boundary. A path-prefix match without the separator would let
        NSC-0420's evidence answer for NSC-042, so this pins the directory."""
        self.commit_evidence("Pipeline/TaskGraph/evidence/NSC-043/records/DEL-x.json")
        self.plan(self.manager_one, TASK, "lease-042")
        self.assertFalse(self.view()["committed_delivery_evidence"])


def load_tests(loader, tests, pattern):
    """Run only this module's cases, not the admission suite it borrows from."""
    suite = unittest.TestSuite()
    for name in loader.getTestCaseNames(ReadinessDeliveryAdvisory):
        if name in dir(AdmissionTests) and name.startswith("test_"):
            continue
        suite.addTest(ReadinessDeliveryAdvisory(name))
    return suite


if __name__ == "__main__":
    unittest.main()
