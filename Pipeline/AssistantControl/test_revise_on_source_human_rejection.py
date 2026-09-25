"""A human-rejected crew candidate, reconciled with a Source that moved.

THE DEFECT. `revise` is the ordinary route for a rejected candidate and it
refuses the moment Source advances past the candidate's base -- correctly, on
two guards that both protect real invariants. `revise-on-source` is the route
built for exactly that situation, and it accepted only ONE basis: a MATERIALIZED
candidate whose authoritative Unity validation failed. A candidate Vincent
rejected by hand fell out of it as

    reconciliation is for a candidate that FAILED authoritative validation,
    not 'changes_requested'

so a human rejection had no route at all once any concurrent commit landed, and
the revise window here is minutes wide. Three tasks carrying real crew work sat
in it with crew capacity idle behind them.

THE TEST THAT MATTERS IS `test_the_next_crew_is_given_the_exact_rejection`. A
guard-only fix passes every other test in this file and fails that one: Astra's
finding is that `prepare_revision_feedback()` returns nothing for a record with
no ordinary `revision`, and a reconciliation makes the rejected commit and the
execution baseline different commits by construction, so the ordinary structure
cannot express it. Widening the guards alone therefore ships a task that
re-scopes perfectly and whose crew is told NOTHING about why the last attempt
was rejected -- it would be sent to repeat the rejected work at full provider
cost, with nothing in the record showing anything wrong.

Design: C:/nscrev/codex-jobs/pm-stranded-candidate-design.report.md (gpt-6-astra).
"""
from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from Pipeline.AssistantControl import test_materialization_reopen as fixture
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.reconciliation_binding import (
    HUMAN_REJECTION,
    canonical_sha256,
)
from Pipeline.AssistantControl.revise_on_source import (
    ReviseOnSourceError,
    revise_on_source,
)
from Pipeline.AssistantControl.revision_feedback import (
    RevisionFeedbackError,
    prepare_revision_feedback,
)
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.AssistantControl.test_revise_on_source import ReviseOnSourceTests

TASK = "NSC-046"

# Deliberately multi-line and non-ASCII: the bytes a crew is handed must survive
# the record, the archive, the journal and the staged file unchanged, and on
# Windows every layer between here and disk will re-interpret them given a
# chance.
REJECTION = (
    "The door opens but the latch never re-arms -- second breach is free.\n"
    "Re-run ChapelOfAshSceneTests after fixing, and keep the \u2014 dash here.\n"
)


class HumanRejectionReconciliationTests(unittest.TestCase):
    setUp = fixture.ReopenMaterializationTests.setUp
    git = staticmethod(fixture.ReopenMaterializationTests.git)
    register_candidate = fixture.ReopenMaterializationTests.register_candidate
    advance_source = ReviseOnSourceTests.advance_source

    # ------------------------------------------------------------------ helpers

    def record(self) -> dict:
        return json.loads(
            (self.manager.records / f"{TASK}.json").read_text(encoding="utf-8"))

    def rejected_pair(self, message: str = REJECTION) -> tuple[str, str, str]:
        """A REAL registered crew candidate, rejected through the real gate.

        Neither half is hand-written: `register_candidate` produces the receipt
        the way candidate registration does, and `ReviewGate.decide` writes the
        rejection the way Vincent's does. A test that authors the state it then
        accepts proves only that two pieces of my own writing agree.
        """
        candidate = self.register_candidate()
        ReviewGate(self.manager).decide(
            TASK, tested_commit=candidate, decision="reject", message=message)
        record = self.record()
        self.assertEqual("changes_requested", record["status"])
        self.assertEqual(candidate, record["human_review"]["commit"])
        head, contract = self.advance_source(revise_contract=True)
        return candidate, head, contract

    def reconcile(self, candidate: str, head: str, contract: str, **kwargs) -> dict:
        return revise_on_source(
            self.manager, TASK, expected_candidate=candidate,
            expected_source_commit=head, accept_contract_sha256=contract,
            reason="rejected by hand; Source moved past the revise window",
            **kwargs)

    def reservation(self, record: dict) -> dict:
        return {
            "task_id": TASK, "source_head": record["source_commit"],
            "run_id": "nsc-046-retry-1", "lease_id": "fixture-lease",
            "plan_id": "fixture-plan",
        }

    # ------------------------------------------------------- the transition

    def test_a_human_rejection_is_a_sufficient_basis(self):
        candidate, head, contract = self.rejected_pair()
        plan = self.reconcile(candidate, head, contract, apply=True)
        self.assertTrue(plan["applied"])
        self.assertEqual(HUMAN_REJECTION, plan["withdrawal_basis"])
        record = self.record()
        self.assertEqual("prepared", record["status"])
        self.assertNotIn("candidate", record)
        self.assertNotIn("human_review", record)
        self.assertEqual(contract, record["task_contract_sha256"])
        self.assertEqual(plan["reconciled_commit"], record["source_commit"])

    def test_a_plan_changes_nothing(self):
        candidate, head, contract = self.rejected_pair()
        before = (self.manager.records / f"{TASK}.json").read_bytes()
        plan = self.reconcile(candidate, head, contract)
        self.assertFalse(plan["applied"])
        self.assertEqual(HUMAN_REJECTION, plan["withdrawal_basis"])
        self.assertEqual(before, (self.manager.records / f"{TASK}.json").read_bytes())

    def test_the_reconciled_tree_holds_BOTH_the_crew_work_and_source(self):
        """The rejected implementation is carried forward as INPUT, not discarded."""
        candidate, head, contract = self.rejected_pair()
        plan = self.reconcile(candidate, head, contract, apply=True)
        checkout = Path(plan["checkout"])
        merged = plan["reconciled_commit"]
        self.assertEqual(merged, self.git(checkout, "rev-parse", "HEAD"))
        git(checkout, "merge-base", "--is-ancestor", head, merged)
        git(checkout, "merge-base", "--is-ancestor", candidate, merged)
        self.assertTrue((checkout / "Pipeline/Testing/source-moved.txt").is_file())

    def test_the_withdrawal_names_the_exact_review_history_entry(self):
        """Bind by identity, so a later correction cannot change what was sent."""
        candidate, head, contract = self.rejected_pair()
        before = self.record()["review_history"]
        self.reconcile(candidate, head, contract, apply=True)
        record = self.record()
        entry = record["revise_on_source_history"][-1]
        self.assertEqual(HUMAN_REJECTION, entry["withdrawal_basis"])
        self.assertEqual(candidate, entry["rejected_candidate"])
        self.assertEqual(head, entry["inspected_source_commit"])
        self.assertEqual(record["source_commit"], entry["reconciled_commit"])
        # review_history survives the withdrawal: the binding indexes into it.
        self.assertEqual(before, record["review_history"])
        index = entry["review_entry_index"]
        self.assertEqual(REJECTION, record["review_history"][index]["message"])
        self.assertEqual(canonical_sha256(record["review_history"][index]),
                         entry["review_entry_sha256"])
        self.assertEqual(REJECTION, entry["rejected_review"]["message"])
        self.assertIn("fixture-crew", entry["withdrawn_run_ids"])

    def test_the_rejection_is_archived_with_the_withdrawn_candidate(self):
        candidate, head, contract = self.rejected_pair()
        plan = self.reconcile(candidate, head, contract, apply=True)
        archived = json.loads(Path(plan["archived_record"]).read_text(encoding="utf-8"))
        self.assertEqual(HUMAN_REJECTION, archived["withdrawal_basis"])
        self.assertEqual(candidate, archived["rejected_candidate"]["commit"])
        self.assertEqual(REJECTION, archived["rejected_review"]["message"])
        self.assertNotIn("materialization_failure", archived)

    # -------------------------------------------- the half Astra said was missing

    def test_the_next_crew_is_given_the_exact_rejection(self):
        """THE DECISIVE ONE. A guard-only fix passes everything else and fails here.

        Without the typed binding `prepare_revision_feedback` returns {} for this
        record -- there is no ordinary `revision`, and there cannot be one -- so
        the crew dispatched onto the reconciled baseline is told nothing about
        why the previous attempt was rejected.
        """
        candidate, head, contract = self.rejected_pair()
        self.reconcile(candidate, head, contract, apply=True)
        record = self.record()
        prepared = prepare_revision_feedback(
            self.manager, record, self.reservation(record), {})
        self.assertEqual({"revision_feedback_file"}, set(prepared),
                         "the reconciled crew was dispatched with no feedback at all")
        staged = Path(prepared["revision_feedback_file"])
        self.assertEqual(REJECTION.encode("utf-8"), staged.read_bytes())

    def test_the_staged_feedback_keeps_the_three_commits_apart(self):
        """Never rewrite the rejection as though the merge had been rejected."""
        candidate, head, contract = self.rejected_pair()
        self.reconcile(candidate, head, contract, apply=True)
        record = self.record()
        prepared = prepare_revision_feedback(
            self.manager, record, self.reservation(record), {})
        metadata = json.loads(
            (Path(prepared["revision_feedback_file"]).parent / "metadata.json")
            .read_text(encoding="utf-8"))
        self.assertEqual(candidate, metadata["rejected_candidate"])
        self.assertEqual(head, metadata["inspected_source_commit"])
        self.assertEqual(record["source_commit"], metadata["reconciled_commit"])
        self.assertNotEqual(metadata["rejected_candidate"], metadata["reconciled_commit"])
        self.assertEqual(hashlib.sha256(REJECTION.encode("utf-8")).hexdigest(),
                         metadata["feedback_sha256"])

    def test_a_rejection_edited_after_the_withdrawal_refuses_rather_than_ships(self):
        """The Pipeline Runner's case, one level deeper.

        A rejection can be wrong by the time a crew reads it -- NSC-118's says a
        regression check "is still owed" and it had since passed. Correcting it
        BEFORE the withdrawal is safe and is the remedy. Correcting it after, when
        the withdrawal has already frozen what a crew will be dispatched with,
        must be loud: silently handing over different bytes would leave nothing
        in the record showing the feedback had moved.
        """
        candidate, head, contract = self.rejected_pair()
        self.reconcile(candidate, head, contract, apply=True)
        record = self.record()
        index = record["revise_on_source_history"][-1]["review_entry_index"]
        record["review_history"][index]["message"] = "actually that check passed"
        with self.assertRaisesRegex(RevisionFeedbackError, "has changed since the withdrawal"):
            prepare_revision_feedback(self.manager, record, self.reservation(record), {})

    def test_a_reservation_on_a_different_baseline_is_refused(self):
        candidate, head, contract = self.rejected_pair()
        self.reconcile(candidate, head, contract, apply=True)
        record = self.record()
        reservation = {**self.reservation(record), "source_head": head}
        with self.assertRaisesRegex(RevisionFeedbackError, "differs from the reconciled baseline"):
            prepare_revision_feedback(self.manager, record, reservation, {})

    def test_an_unreconciled_record_still_returns_nothing(self):
        """The empty return must keep meaning "never reconciled", not "no feedback"."""
        self.register_candidate()
        self.assertEqual({}, prepare_revision_feedback(
            self.manager, self.record(), {}, {}))

    # ------------------------------------------------------------- refusals

    def test_an_intact_candidate_is_refused(self):
        candidate = self.register_candidate()
        head, contract = self.advance_source(revise_contract=True)
        with self.assertRaisesRegex(ReviseOnSourceError, "rejected by a human"):
            self.reconcile(candidate, head, contract, apply=True)

    def test_a_rejection_of_a_different_commit_is_refused(self):
        candidate, head, contract = self.rejected_pair()
        record = self.record()
        record["human_review"]["commit"] = "f" * 40
        (self.manager.records / f"{TASK}.json").write_text(
            json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ReviseOnSourceError, "names a different commit"):
            self.reconcile(candidate, head, contract, apply=True)

    def test_a_candidate_without_crew_provenance_is_refused(self):
        """Human rejection establishes that work needs changes, not who made it."""
        candidate, head, contract = self.rejected_pair()
        record = self.record()
        del record["candidate"]["receipt"]
        (self.manager.records / f"{TASK}.json").write_text(
            json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ReviseOnSourceError, "not an authenticated crew result"):
            self.reconcile(candidate, head, contract, apply=True)

    def test_a_receipt_for_a_different_tree_is_refused(self):
        candidate, head, contract = self.rejected_pair()
        record = self.record()
        record["candidate"]["receipt"]["candidate_tree"] = "0" * 40
        (self.manager.records / f"{TASK}.json").write_text(
            json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ReviseOnSourceError, "candidate_tree"):
            self.reconcile(candidate, head, contract, apply=True)

    def test_an_unsettled_worker_is_refused(self):
        """Released capacity is not settlement, and this path re-dispatches."""
        candidate, head, contract = self.rejected_pair()
        record = self.record()
        record["worker"] = {"run_id": "nsc-046-worker", "status": "succeeded",
                            "capacity_released": True}
        (self.manager.records / f"{TASK}.json").write_text(
            json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ReviseOnSourceError, "not settled"):
            self.reconcile(candidate, head, contract, apply=True)

    def test_a_source_that_has_not_advanced_is_refused(self):
        candidate = self.register_candidate()
        ReviewGate(self.manager).decide(
            TASK, tested_commit=candidate, decision="reject", message=REJECTION)
        head = self.git(self.source, "rev-parse", "HEAD")
        blob = git(self.source, "cat-file", "blob", f"{head}:Tasks/{TASK}.yaml")
        with self.assertRaisesRegex(ReviseOnSourceError, "ordinary revise applies"):
            self.reconcile(candidate, head, hashlib.sha256(blob).hexdigest(), apply=True)

    # ------------------------------------------- the interrupted-run journal

    def journal_path(self) -> Path:
        return self.manager.records / "revise-on-source" / f"{TASK}.in-progress.json"

    def test_an_interrupted_reconciliation_is_finished_by_the_exact_request(self):
        """Astra's first unsafe property, reproduced rather than reasoned about.

        The archive lands before the checkout advances and the authoritative
        record after it. A crash between them used to leave HEAD at the merge
        while the record still named the candidate -- which trips "checkout HEAD
        is not the candidate this request names" on every retry, with no route
        out. The journal is what turns that into a resumable operation.
        """
        candidate, head, contract = self.rejected_pair()
        before = copy.deepcopy(self.record())
        plan = self.reconcile(candidate, head, contract, apply=True)
        merged = plan["reconciled_commit"]
        # Exactly the crash state: everything durable except the record write.
        self.assertFalse(self.journal_path().exists())
        (self.manager.records / f"{TASK}.json").write_text(
            json.dumps(before), encoding="utf-8")
        journal = {
            "schema_version": plan["schema_version"], "task_id": TASK,
            "phase": "checkout_advanced", "operation": "fixture",
            "rejected_candidate": candidate, "inspected_source_commit": head,
            "accepted_contract_sha256": contract, "reconciled_commit": merged,
            "archived_record": plan["archived_record"],
            "checkout": plan["checkout"],
            "history_entry": {"schema_version": plan["schema_version"],
                              "withdrawal_basis": HUMAN_REJECTION,
                              "rejected_candidate": candidate,
                              "accepted_contract_sha256": contract,
                              "inspected_source_commit": head,
                              "reconciled_commit": merged},
        }
        self.journal_path().write_text(json.dumps(journal), encoding="utf-8")

        resumed = self.reconcile(candidate, head, contract, apply=True)
        self.assertTrue(resumed["applied"])
        self.assertEqual("record_write", resumed["resumed"])
        record = self.record()
        self.assertEqual("prepared", record["status"])
        self.assertEqual(merged, record["source_commit"])
        self.assertFalse(self.journal_path().exists())

    def test_an_interrupted_reconciliation_for_another_request_is_refused(self):
        candidate, head, contract = self.rejected_pair()
        self.journal_path().parent.mkdir(parents=True, exist_ok=True)
        self.journal_path().write_text(json.dumps({
            "schema_version": "assistant-revise-on-source/v1", "task_id": TASK,
            "phase": "merged", "rejected_candidate": "e" * 40,
            "inspected_source_commit": head, "accepted_contract_sha256": contract,
            "reconciled_commit": "d" * 40,
        }), encoding="utf-8")
        with self.assertRaisesRegex(ReviseOnSourceError, "DIFFERENT request"):
            self.reconcile(candidate, head, contract, apply=True)
        self.assertTrue(self.journal_path().exists(),
                        "a refusal must not delete the journal it refused on")

    def test_a_journal_from_before_any_durable_write_clears_itself(self):
        """Nothing was written, so there is nothing to reconcile with: retry."""
        candidate, head, contract = self.rejected_pair()
        self.journal_path().parent.mkdir(parents=True, exist_ok=True)
        self.journal_path().write_text(json.dumps({
            "schema_version": "assistant-revise-on-source/v1", "task_id": TASK,
            "phase": "merged", "rejected_candidate": candidate,
            "inspected_source_commit": head, "accepted_contract_sha256": contract,
            "reconciled_commit": "d" * 40,
            "archived_record": str(self.manager.records / "revise-on-source" / "absent.json"),
        }), encoding="utf-8")
        plan = self.reconcile(candidate, head, contract, apply=True)
        self.assertTrue(plan["applied"])
        self.assertNotIn("resumed", plan)
        self.assertFalse(self.journal_path().exists())

    def test_a_successful_reconciliation_leaves_no_journal(self):
        candidate, head, contract = self.rejected_pair()
        self.reconcile(candidate, head, contract, apply=True)
        self.assertFalse(self.journal_path().exists())


if __name__ == "__main__":
    unittest.main()
