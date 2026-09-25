"""A retry proposal is written only for a change that answers the diagnosed cause."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.decomposition_recovery import RetryPlanError, plan_retry

FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "TaskDecomposition" / "tests" / "fixtures" / "failure_diagnosis"
)


class FixtureRuns(unittest.TestCase):
    """Real retained runs, each behind a receipt recording its inputs."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="assistant-retry-plan-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = self.root / "source"
        source.mkdir()
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        self.manager = Checkouts(source, self.root / "checkouts")
        self.manager.records.mkdir(parents=True, exist_ok=True)

    def install(self, run: str, task: str, **inputs) -> None:
        run_dir = self.manager.records / "decomposition-runs" / run
        shutil.copytree(FIXTURES / run, run_dir)
        write_record(self.manager.records / f"{task}.decomposition.json", {
            "schema_version": "assistant-decomposition/v1", "task_id": task, "run_id": run,
            "status": "failed", "source": str(self.manager.source), "artifact_root": str(run_dir),
            "providers": ["claude", "codex"], "max_calls": 2,
            "provider_environment": {"NSC_CLAUDE_MODEL": "claude-opus-5-5",
                                     "NSC_OPENAI_CODEX_MODEL": "gpt-5.6-sol"},
            "task_contract_sha256": "a" * 64, **inputs,
        })

    def plan(self, task: str, run: str, change: str, **kwargs) -> dict:
        return plan_retry(self.manager, task, run_id=run, out=self.root / "out" / f"{run}.json",
                          change=change, **kwargs)

    def test_a_capacity_stop_needs_a_one_million_context_model(self):
        run = "decomp-nsc088-clone-20260924a"
        self.install(run, "NSC-088")
        with self.assertRaisesRegex(RetryPlanError, "needs a 1M-context model"):
            self.plan("NSC-088", run, "provider-route", models={"NSC_CLAUDE_MODEL": "claude-opus-5"})
        proposal = self.plan("NSC-088", run, "provider-route",
                             models={"NSC_CLAUDE_MODEL": "claude-opus-5-5[1m]"})
        self.assertEqual("claude-opus-5-5[1m]", proposal["proposed_inputs"]["provider_environment"]["NSC_CLAUDE_MODEL"])
        self.assertIs(False, proposal["retry_authorized"])
        self.assertIs(False, proposal["reserves_attempt"])
        saved = json.loads(Path(proposal["proposal_path"]).read_text(encoding="utf-8"))
        self.assertEqual("provider-route", saved["change"])

    def test_the_same_model_again_is_not_a_repair(self):
        run = "decomp-nsc088-clone-20260924b"
        self.install(run, "NSC-088", provider_environment={"NSC_CLAUDE_MODEL": "claude-opus-5-5[1m]"})
        with self.assertRaisesRegex(RetryPlanError, "is already"):
            self.plan("NSC-088", run, "provider-route", models={"NSC_CLAUDE_MODEL": "claude-opus-5-5[1m]"})

    def test_a_budget_stop_is_answered_only_by_moving_from_two_to_three_calls(self):
        run = "decomp-nsc088-clone-20260924c"
        self.install(run, "NSC-088")
        with self.assertRaisesRegex(RetryPlanError, "answered by 'budget-3', not 'author-checklist'"):
            self.plan("NSC-088", run, "author-checklist")
        proposal = self.plan("NSC-088", run, "budget-3")
        self.assertEqual((2, 3), (proposal["prior_inputs"]["max_calls"], proposal["proposed_inputs"]["max_calls"]))

    def test_an_exhausted_three_call_run_gets_no_bigger_budget(self):
        run = "decomp-nsc088-clone-20260924c"
        self.install(run, "NSC-088", max_calls=3)
        with self.assertRaisesRegex(RetryPlanError, "already had a three-call budget"):
            self.plan("NSC-088", run, "budget-3")

    def test_an_author_failure_is_answered_by_newly_enabling_the_checklist(self):
        run = "decomp-nsc007-20260918a"
        self.install(run, "NSC-007")
        proposal = self.plan("NSC-007", run, "author-checklist")
        self.assertEqual("parent-contract-v1", proposal["proposed_inputs"]["author_checklist"])

    def test_an_author_failure_with_the_checklist_already_on_has_no_automatic_retry(self):
        run = "decomp-nsc007-20260918a"
        self.install(run, "NSC-007", author_checklist="parent-contract-v1")
        with self.assertRaisesRegex(RetryPlanError, "already used"):
            self.plan("NSC-007", run, "author-checklist")

    def test_a_stop_is_never_proposed_for_retry_and_nothing_is_written(self):
        run = "decomp-nsc007-20260922a"
        self.install(run, "NSC-007")
        with self.assertRaisesRegex(RetryPlanError, "needs manual investigation"):
            self.plan("NSC-007", run, "author-checklist")
        self.assertFalse((self.root / "out").exists())

    def test_an_existing_proposal_is_never_overwritten(self):
        run = "decomp-nsc088-clone-20260924c"
        self.install(run, "NSC-088")
        self.plan("NSC-088", run, "budget-3")
        with self.assertRaisesRegex(RetryPlanError, "refusing to overwrite"):
            self.plan("NSC-088", run, "budget-3")


class ContractRevisionTests(unittest.TestCase):
    """A CONTRACT stop is answered only by a committed revision, explained."""

    def setUp(self):
        from Pipeline.AssistantControl.decomposition import load_committed_task  # noqa: F401 (sys.path)
        from TaskDecomposition.round_robin_decomposition import (
            candidate_sha256, run_round_robin_decomposition,
        )
        from TaskDecomposition.tests.review_chain_smoke_test import factory
        from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (
            QueueProvider, needs_human_review, validated_candidate,
        )
        from TaskDecomposition.tests.test_support import create_repository, decomposed_result

        temporary = tempfile.TemporaryDirectory(prefix="assistant-retry-contract-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.root = root
        self.source = root / "source"
        self.source.mkdir()
        tasks = create_repository(self.source)
        self.manager = Checkouts(self.source, root / "checkouts")
        output_root = (self.manager.records / "decomposition-runs").resolve()
        output_root.mkdir(parents=True)
        parent = tasks["NSC-010"]
        raw = decomposed_result(parent)
        review = needs_human_review(candidate_sha256(validated_candidate(raw, parent, tasks)))
        run_round_robin_decomposition(
            source=self.source, output_root=output_root, task_id="NSC-010",
            provider_order=("codex", "claude"), max_calls=2, run_id="contract-stop",
            provider_factory=factory({"codex": QueueProvider([raw]), "claude": QueueProvider([review])}),
            _require_physical_read_only_source=False,
        )
        head = subprocess.run(["git", "-C", str(self.source), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
        self.reviewed_sha = load_committed_task(self.source, "NSC-010", commit=head)["task_contract_sha256"]
        write_record(self.manager.records / "NSC-010.decomposition.json", {
            "schema_version": "assistant-decomposition/v1", "task_id": "NSC-010", "run_id": "contract-stop",
            "status": "failed", "source": str(self.source.resolve()),
            "artifact_root": str(output_root / "contract-stop"), "providers": ["codex", "claude"],
            "max_calls": 2, "task_contract_sha256": self.reviewed_sha,
        })

    def plan(self, **kwargs) -> dict:
        return plan_retry(self.manager, "NSC-010", run_id="contract-stop",
                          out=self.root / "out" / f"p{len(list((self.root).glob('out/*')))}.json",
                          change="contract-revision", **kwargs)

    def test_an_unchanged_contract_or_missing_explanation_is_refused(self):
        with self.assertRaisesRegex(RetryPlanError, "explain how"):
            self.plan()
        with self.assertRaisesRegex(RetryPlanError, "unchanged since the failed run"):
            self.plan(explanation="GER clarified the owner.")

    def test_a_committed_revision_with_an_explanation_is_proposed(self):
        path = self.source / "Tasks" / "NSC-010.yaml"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["notes"] = "GER revision: the owning capability is NSC-012."
        path.write_text(json.dumps(value), encoding="utf-8")
        for args in (("add", "--", "Tasks/NSC-010.yaml"),
                     ("-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q", "-m", "revise")):
            subprocess.run(["git", "-C", str(self.source), *args], check=True)
        proposal = self.plan(explanation="GER named NSC-012 as the owning capability.")
        self.assertNotEqual(self.reviewed_sha, proposal["proposed_inputs"]["task_contract_sha256"])
        self.assertEqual("GER named NSC-012 as the owning capability.",
                         proposal["evidence"]["contract"]["explanation"])


if __name__ == "__main__":
    unittest.main()
