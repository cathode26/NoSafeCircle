"""`reserve` must refuse a record `readiness` already calls unreservable.

THE GAP. `readiness` appends `task_checkout_has_work_or_review_state` for any
record whose status is outside {prepared, planned}. `reserve` checked the
record's status NOWHERE -- a grep for `record.get("status")` over `admission.py`
returned zero hits. So an `awaiting_human` record, carrying a registered
candidate that is waiting for a person, was reservable for as long as its
checkout still sat on the baseline and its scope was still valid. That is
precisely the state a finished crew leaves behind, and it lasts until main moves.

Found by Astra while answering a different question -- snapshot validity for
ordinary prepared records -- because it read `readiness` and `reserve` side by
side: "readiness checks prepared/planned state at line 180, while reserve lacks
that explicit status check."

THE DECISIVE TEST IS `test_readiness_and_reserve_agree_that_review_state_is_not_reservable`.
An advisory that refuses more than the gate it advises on is the whole defect,
and only calling both can show it. The positive controls matter as much: a
`prepared` record and a `planned` record must both still reserve, or this has
replaced one disagreement with another.

Every case builds throwaway repositories through the admission fixture.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from Pipeline.AssistantControl.admission import reserve
from Pipeline.AssistantControl.checkouts import write_record
from Pipeline.AssistantControl.readiness import inspect_readiness
from Pipeline.AssistantControl.test_admission import AdmissionTests

TASK = "NSC-042"


class ReserveRefusesUnreservableState(AdmissionTests):
    def record_path(self) -> Path:
        return self.manager_one.records / f"{TASK}.json"

    def set_status(self, status: str) -> dict:
        """Plan the task, then move only its status, leaving everything else
        exactly as a reservable record has it -- checkout on the baseline, scope
        valid, contract pinned. The point is that nothing else has to be wrong."""
        self.plan(self.manager_one, TASK, "lease-042")
        record = json.loads(self.record_path().read_text(encoding="utf-8"))
        record["status"] = status
        write_record(self.record_path(), record)
        return record

    def test_reserve_refuses_a_record_awaiting_human_review(self):
        self.set_status("awaiting_human")
        with self.assertRaises(ValueError) as caught:
            reserve(self.manager_one, TASK, "run-042",
                    dependency_reader=self.dependencies)
        message = str(caught.exception)
        self.assertIn("awaiting_human", message,
                      "the refusal must name the state it refused")
        self.assertIn("not reservable", message)

    def test_reserve_refuses_every_non_reservable_state_the_fleet_has(self):
        """The live statuses on 2026-09-26, minus the two reservable ones."""
        for status in ("awaiting_human", "changes_requested", "validation_failed",
                       "materialization_failed", "needs_materialization",
                       "approved", "integrated"):
            with self.subTest(status=status):
                self.setUp()
                self.set_status(status)
                with self.assertRaises(ValueError) as caught:
                    reserve(self.manager_one, TASK, "run-042",
                            dependency_reader=self.dependencies)
                self.assertIn(status, str(caught.exception))

    def test_readiness_and_reserve_agree_that_review_state_is_not_reservable(self):
        """The decisive one: before this change readiness said not ready and
        reserve admitted the same record in the same second."""
        self.set_status("awaiting_human")
        view = inspect_readiness(self.manager_one, TASK,
                                 dependency_reader=self.dependencies)
        self.assertFalse(view["ready_to_reserve"])
        self.assertIn("task_checkout_has_work_or_review_state", view["problems"])
        with self.assertRaises(ValueError):
            reserve(self.manager_one, TASK, "run-042",
                    dependency_reader=self.dependencies)

    # ---------------------------------------------------------------- controls
    def test_a_prepared_record_is_still_reservable(self):
        """Without this the change could refuse everything and look correct."""
        self.plan(self.manager_one, TASK, "lease-042")
        admitted = reserve(self.manager_one, TASK, "run-042",
                           dependency_reader=self.dependencies)
        self.assertTrue(admitted["admitted"])

    def test_a_planned_record_is_still_reservable(self):
        """`readiness` accepts `planned`, so `reserve` must too -- otherwise this
        has replaced one disagreement with the mirror image of it. No production
        path writes this status today; readiness's set is what defines it."""
        self.set_status("planned")
        view = inspect_readiness(self.manager_one, TASK,
                                 dependency_reader=self.dependencies)
        self.assertNotIn("task_checkout_has_work_or_review_state", view["problems"])
        admitted = reserve(self.manager_one, TASK, "run-042",
                           dependency_reader=self.dependencies)
        self.assertTrue(admitted["admitted"])

    def test_the_same_reservation_is_still_idempotent(self):
        """The check sits before the idempotence branch, so prove the branch
        still works for the retry it exists for."""
        self.plan(self.manager_one, TASK, "lease-042")
        first = reserve(self.manager_one, TASK, "run-042",
                        dependency_reader=self.dependencies)
        second = reserve(self.manager_one, TASK, "run-042",
                         dependency_reader=self.dependencies)
        self.assertEqual(first, second)


def load_tests(loader, tests, pattern):
    """Run only this module's cases, not the admission suite it borrows from."""
    suite = unittest.TestSuite()
    for name in loader.getTestCaseNames(ReserveRefusesUnreservableState):
        if name in dir(AdmissionTests) and name.startswith("test_"):
            continue
        suite.addTest(ReserveRefusesUnreservableState(name))
    return suite


if __name__ == "__main__":
    unittest.main()
