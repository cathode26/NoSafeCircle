"""Readiness and reserve must give the SAME answer about a reconciled baseline.

THE DEFECT. `admission.reserve` resolves a `revise-on-source` baseline at
admission.py:454 -- `_revision_baseline` first, then
`_revise_on_source_baseline`. `readiness.py` asked only the first, so a record
sitting on a reconciliation was measured against current Source HEAD, which a
merge of the rejected candidate and Source can never equal BY CONSTRUCTION. The
answer was `checkout_or_scope_not_ready: task checkout is not at current source
HEAD`.

That is a WRONG ANSWER, not a missing feature, and it is expensive because
readiness is what a dispatcher reads to choose work: it reported the one task
nobody could dispatch as un-dispatchable for a reason that was not its reason.
NSC-118 read exactly that at 2026-09-25 23:1xZ while every precondition
`reserve` has was satisfied.

Found by Astra reviewing the seam-1 branch: "admission recognizes reconciled
baselines, but readiness checks only ordinary revisions before falling back to
current Source HEAD. Consequently, a reconciled merge can fail readiness even
before main advances. Re-reconciling cannot satisfy that equality either."

THE DECISIVE TEST IS `test_readiness_and_reserve_agree_on_a_reconciled_record`,
because agreement is the property that was broken and neither half alone can
show it. `test_a_reconciliation_beside_the_main_line_is_still_refused` is the
boundary that keeps the fix from becoming "readiness stops checking staleness".

Every case builds throwaway repositories through the admission fixture, calls
the production writer `_publish_reconciled` rather than hand-shaping a record,
and reads and writes nothing live.
"""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from Pipeline.AssistantControl.admission import reserve
from Pipeline.AssistantControl.checkouts import write_record
from Pipeline.AssistantControl.readiness import inspect_readiness
from Pipeline.AssistantControl.revise_on_source import _publish_reconciled
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.AssistantControl.test_admission import AdmissionTests
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan

TASK = "NSC-042"


class ReadinessOnAReconciledBaseline(AdmissionTests):
    """Reuses the admission fixture, which already carries a real scope plan and
    an injected dependency reader -- so the only thing under test here is which
    commit readiness measures the checkout against."""

    def run_git(self, repo: Path, *args: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, check=True).stdout.decode().strip()

    def record_path(self) -> Path:
        return self.manager_one.records / f"{TASK}.json"

    def read_record(self) -> dict:
        return json.loads(self.record_path().read_text(encoding="utf-8"))

    def plan_at_head(self, lease_id: str):
        """Re-pin the persisted scope to whatever the checkout is on now."""
        return AssistantScopePlanner(self.manager_one).plan(
            TASK,
            ExecutionScopePlan(
                ("Assets/Feature/Feature.cs",), (),
                ("Assets/Feature/Tests/FeatureTests.cs",), (),
            ),
            lease_id=lease_id,
        )

    def reconcile(self, *, source_contains_the_merge: bool = False) -> tuple[str, str, str]:
        """Build a real reconciliation and publish it with the production writer.

        Returns (rejected_candidate, inspected_source, reconciled_commit).
        """
        self.plan(self.manager_one, TASK, "lease-042")
        checkout = self.root_one / TASK

        # The rejected candidate: crew work committed in the owned checkout.
        (checkout / "Assets/Feature/Feature.cs").write_text(
            "class Feature { /* crew pass */ }\n")
        self.run_git(checkout, "add", "--", "Assets/Feature/Feature.cs")
        self.run_git(checkout, "commit", "-m", "the candidate a human rejected")
        candidate = self.run_git(checkout, "rev-parse", "HEAD")

        # Source moves on WITHOUT touching this task's contract, so the pin the
        # checkout was prepared with is still the contract at the merge.
        (self.source / "Assets/Feature/Unrelated.cs").write_text("class Unrelated {}\n")
        self.git("add", ".")
        self.git("commit", "-m", "source advances beside the candidate")
        inspected = self.run_git(self.source, "rev-parse", "HEAD")

        # The reconciliation: first parent the candidate, second parent Source.
        self.run_git(checkout, "fetch", "--no-tags", str(self.source), inspected)
        self.run_git(checkout, "merge", "--no-ff", "--no-edit", "FETCH_HEAD")
        merged = self.run_git(checkout, "rev-parse", "HEAD")
        self.assertEqual(candidate, self.run_git(checkout, "rev-parse", f"{merged}^1"))
        self.assertEqual(inspected, self.run_git(checkout, "rev-parse", f"{merged}^2"))

        if source_contains_the_merge:
            # Not the reconciled shape: used only to show the ordinary path is
            # untouched when Source really does contain the checkout's HEAD.
            self.git("fetch", "--no-tags", str(checkout), merged)
            self.git("merge", "--ff-only", "FETCH_HEAD")

        record = self.read_record()
        pin = record["task_contract_sha256"]
        entry = {
            "schema_version": "assistant-revise-on-source/v1",
            "withdrawal_basis": "human_rejection",
            "rejected_candidate": candidate,
            "inspected_source_commit": inspected,
            "reconciled_commit": merged,
            "accepted_contract_sha256": pin,
            "reason": "a crew pass is needed against the current contract",
        }
        _publish_reconciled(record, entry, merged, pin)
        write_record(self.record_path(), record)

        # Scope LAST, in production's order: `scope.py:88` requires the checkout
        # to sit on the record's pinned source commit, and it is the publication
        # that moves that pin to the merge. Planning first raises "task checkout
        # is not at its pinned source commit" -- which is the planner correctly
        # refusing to pin a plan to a commit the record does not claim.
        self.plan_at_head("lease-042-reconciled")
        return candidate, inspected, merged

    # ------------------------------------------------------------------ cases
    def test_readiness_resolves_the_reconciled_commit_as_its_baseline(self):
        _, _, merged = self.reconcile()
        view = inspect_readiness(self.manager_one, TASK,
                                 dependency_reader=self.dependencies)
        # `revision_baseline` is readiness's existing name for "the commit I
        # measured the checkout against". A reconciled baseline now appears
        # there too, so the key is unchanged and its meaning is widened: a
        # reader asking why readiness said what it said gets the answer from the
        # field that was always there.
        self.assertEqual(merged, view["revision_baseline"],
                         "readiness measured the checkout against the wrong commit")
        stale = [problem for problem in view["problems"]
                 if problem.startswith("checkout_or_scope_not_ready")]
        self.assertEqual([], stale, view["problems"])
        self.assertTrue(view["ready_to_reserve"], view["problems"])

    def test_readiness_and_reserve_agree_on_a_reconciled_record(self):
        """The decisive one. Before the fix readiness said not ready and reserve
        admitted the same record in the same second -- and a dispatcher reads
        readiness. Neither call alone can show that; only both can."""
        _, _, merged = self.reconcile()
        view = inspect_readiness(self.manager_one, TASK,
                                 dependency_reader=self.dependencies)
        admitted = reserve(self.manager_one, TASK, "run-042",
                           dependency_reader=self.dependencies)
        self.assertTrue(admitted["admitted"])
        self.assertEqual(merged, admitted["source_head"])
        self.assertEqual(
            view["ready_to_reserve"], admitted["admitted"],
            "readiness and reserve disagreed about the same record: readiness "
            f"said {view['ready_to_reserve']!r} with {view['problems']!r}")

    def test_a_reconciliation_beside_the_main_line_is_still_refused(self):
        """The boundary. The fix must not turn into "readiness stops checking".

        A reconciliation built on a Source commit Source never had is exactly
        what `_revise_on_source_baseline` refuses, and readiness must surface
        that refusal rather than swallow it into a clean result.
        """
        _, _, merged = self.reconcile()
        record = self.read_record()
        record["revise_on_source_history"][-1]["inspected_source_commit"] = "0" * 40
        write_record(self.record_path(), record)

        view = inspect_readiness(self.manager_one, TASK,
                                 dependency_reader=self.dependencies)
        self.assertFalse(view["ready_to_reserve"], view["problems"])
        named = [problem for problem in view["problems"]
                 if problem.startswith("checkout_or_scope_not_ready")]
        self.assertEqual(1, len(named), view["problems"])
        self.assertIn(view["checkout_error"], named[0])
        self.assertNotEqual(merged, view["revision_baseline"])

    def test_a_record_with_no_reconciliation_is_still_measured_against_source(self):
        """The other boundary: an ordinary prepared checkout that Source has
        moved past must still read not ready, for the reason it always did."""
        self.plan(self.manager_one, TASK, "lease-042")
        (self.source / "Assets/Feature/Unrelated.cs").write_text("class Unrelated {}\n")
        self.git("add", ".")
        self.git("commit", "-m", "source moves on after the checkout was prepared")

        view = inspect_readiness(self.manager_one, TASK,
                                 dependency_reader=self.dependencies)
        self.assertFalse(view["ready_to_reserve"])
        self.assertIsNone(view["revision_baseline"])
        self.assertIn("not at current source HEAD", str(view["checkout_error"]))


def load_tests(loader, tests, pattern):
    """Run only this module's cases, not the admission suite it borrows from."""
    suite = unittest.TestSuite()
    for name in loader.getTestCaseNames(ReadinessOnAReconciledBaseline):
        if name in dir(AdmissionTests) and name.startswith("test_"):
            continue
        suite.addTest(ReadinessOnAReconciledBaseline(name))
    return suite


if __name__ == "__main__":
    unittest.main()
