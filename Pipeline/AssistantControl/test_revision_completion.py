"""Narrow offline rejection-to-completion integration over real Git authorities."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.admission import reserve
from Pipeline.AssistantControl.candidate import register_candidate, _scope
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.AssistantControl.revision_feedback import prepare_revision_feedback
from Pipeline.AssistantControl.revisions import begin_revision
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.AssistantControl.source_update import synchronize_candidate
from Pipeline.ExecutionCrew.run_crew import run_crew
from Pipeline.ExecutionCrew.tests.execution_crew_smoke_test import State, execute, factory, fixture
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge, ExecutionCrewReceipt


class RevisionCompletionTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> str:
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, check=True).stdout.strip()

    def test_rejected_candidate_is_revised_registered_and_test_only_integrated(self):
        with tempfile.TemporaryDirectory(prefix="revision-completion-") as temporary:
            root = Path(temporary)
            source = fixture(root)
            (source / "Pipeline" / "TaskGraph" / "taskcontrol.py").write_text(
                "print('taskcontrol validate: PASS')\n", encoding="utf-8",
                newline="\n",
            )
            self.git(source, "add", "Pipeline/TaskGraph/taskcontrol.py")
            self.git(source, "commit", "-qm", "fixture taskcontrol prerequisite")
            outputs = root / "seed-outputs"
            prior, _, prior_dir = execute(source, outputs, "seed_preserve", 920, provider="claude")
            base = self.git(source, "rev-parse", "HEAD")
            task = prior["task_id"]
            checkout_root = root / "checkouts"
            manager = Checkouts(source, checkout_root)
            manager.prepare(task)
            old_scope = AssistantScopePlanner(manager).plan(
                task, ExecutionScopePlan(
                    ("Assets/Scripts/PlayerMana.cs",), (),
                    ("Assets/Tests/PlayerManaTests.cs",), (),
                ), lease_id="revision-old-lease")
            checkout = checkout_root / task
            patch_bytes = (prior_dir / "candidate.patch").read_bytes()
            subprocess.run(["git", "-C", str(checkout), "apply", "--binary",
                            str(prior_dir / "candidate.patch")], check=True)
            self.git(checkout, "add", "Assets/Scripts/PlayerMana.cs",
                     "Assets/Tests/PlayerManaTests.cs")
            self.git(checkout, "commit", "-qm", "fixture rejected candidate")
            first_candidate = self.git(checkout, "rev-parse", "HEAD")
            first_tree = self.git(checkout, "rev-parse", "HEAD^{tree}")
            task_hash = json.loads((manager.records / f"{task}.json").read_text())["task_contract_sha256"]
            result_bytes = (prior_dir / "crew_result.json").read_bytes()
            first_metadata = {
                "commit": first_candidate, "tree": first_tree, "parent": base,
                "run_id": prior["run_id"], "lease_id": old_scope["lease_id"],
                "plan_id": old_scope["plan_id"], "fixture_candidate_metadata": True,
                "receipt": {
                    "task_id": task, "run_id": prior["run_id"],
                    "lease_id": old_scope["lease_id"], "plan_id": old_scope["plan_id"],
                    "candidate_commit": first_candidate, "candidate_tree": first_tree,
                    "candidate_parent": base, "source_base": base,
                    "task_contract_sha256": task_hash,
                    "execution_result_sha256": hashlib.sha256(result_bytes).hexdigest(),
                    "candidate_patch_sha256": hashlib.sha256(patch_bytes).hexdigest(),
                },
            }
            record_path = manager.records / f"{task}.json"
            record = json.loads(record_path.read_text())
            record["candidate"] = first_metadata
            write_record(record_path, record)
            ReviewGate(manager).decide(
                task, tested_commit=first_candidate, decision="reject",
                message="Fixture-only human rejection: add the regression correction.")
            rejected_record = json.loads(record_path.read_text())
            self.assertEqual("changes_requested", rejected_record["status"])

            # The first candidate and its review are retained by the real revision authority.
            revised = begin_revision(manager, task, first_candidate)
            self.assertEqual(first_candidate, revised["revision"]["candidate_commit"])
            self.assertEqual(1, len(revised["revision_history"]))
            self.assertTrue((checkout / "Assets/Scripts/PlayerMana.cs").read_bytes())

            new_scope = AssistantScopePlanner(manager).plan(
                task, ExecutionScopePlan(
                    ("Assets/Scripts/PlayerMana.cs",), (),
                    ("Assets/Tests/PlayerManaTests.cs",), (),
                ), lease_id="revision-new-lease")
            admission = reserve(manager, task, "revision-worker-920",
                                dependency_reader=lambda source_root, task_id, root_path: {
                                    "task_id": task_id,
                                    "source_commit": self.git(source_root, "rev-parse", "HEAD"),
                                    "source_unchanged_during_read": True,
                                    "dependencies_satisfied": True,
                                    "fixture_dependency_reader": True,
                                })
            self.assertEqual(first_candidate, admission["source_head"])
            self.assertIn("PriorCandidateMarker",
                          (checkout / "Assets" / "Scripts" / "PlayerMana.cs").read_text())

            retry_output = checkout / "Pipeline" / "ExecutionCrew" / "outputs"
            retry_output.mkdir(parents=True)
            (checkout / ".git" / "info" / "exclude").write_text(
                "Pipeline/ExecutionCrew/outputs/\n", encoding="utf-8")
            shutil.copytree(prior_dir, retry_output / prior["run_id"])
            feedback_text = "Fixture-only human rejection: add the regression correction."
            feedback = root / "rejection-feedback.txt"
            feedback.write_text(feedback_text, encoding="utf-8", newline="\n")
            feedback_kwargs = prepare_revision_feedback(
                manager, json.loads(record_path.read_text()), admission,
                {"provider": "claude", "execution_model": prior["execution_model"]},
            )
            state = State("retry_impl_only", checkout, None)
            retry = run_crew(
                source=checkout, output_root=retry_output,
                run_id="revision-worker-920", retry_run_id=prior["run_id"],
                review_feedback_file=feedback_kwargs["feedback_file"],
                provider_factory=factory(state), _require_physical_read_only_source=False,
            )
            self.assertEqual("review_ready", retry["crew_status"])
            self.assertEqual("already_present", retry["retry_seed_mode"])
            self.assertEqual(first_candidate, retry["source_head"])
            for role in ("implementer", "test_author", "validator"):
                prompts = [request.prompt for called, request, _ in state.calls if called == role]
                self.assertTrue(prompts, role)
                self.assertTrue(all(feedback_text in prompt for prompt in prompts), role)

            # Persist the real bridge receipt, then let the real committer apply and commit B.
            record = json.loads(record_path.read_text())
            scope = _scope(manager, record)
            result_path = retry_output / retry["run_id"] / "crew_result.json"
            candidate_path = retry_output / retry["run_id"] / "candidate.patch"
            receipt = ExecutionCrewReceipt(
                run_id=retry["run_id"], task_id=task, lease_id=new_scope["lease_id"],
                plan_id=new_scope["plan_id"], provider="claude",
                execution_model=retry["execution_model"], execution_reasoning_effort=None,
                crew_profile=retry["crew_profile"], validation_profile=retry["validation_profile"],
                source_head=first_candidate, task_contract_sha256=task_hash,
                crew_status="review_ready", result_path=str(result_path),
                result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
                candidate_path=str(candidate_path),
                candidate_sha256=hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
                final_actual_changed_paths=tuple(retry["final_actual_changed_paths"]),
                returncode=0, rejection_reasons=(),
            )
            bridge = ExecutionCrewBridge(
                checkout=checkout, scope=scope,
                execution_model=receipt.execution_model,
                crew_profile=receipt.crew_profile,
                validation_profile=receipt.validation_profile,
            )
            bridge._persist(receipt)
            registered = register_candidate(
                manager, task, retry["run_id"],
                {"execution_model": receipt.execution_model,
                 "crew_profile": receipt.crew_profile,
                 "validation_profile": receipt.validation_profile},
            )
            second_candidate = registered["candidate"]["commit"]
            self.assertNotEqual(first_candidate, second_candidate)
            self.assertEqual(second_candidate, self.git(checkout, "rev-parse", "HEAD"))
            with self.assertRaisesRegex(ValueError, "registered"):
                ReviewGate(manager).decide(
                    task, tested_commit=first_candidate, decision="approve",
                    message="Fixture-only stale approval")
            ReviewGate(manager).decide(
                task, tested_commit=second_candidate, decision="approve",
                message="TESTONLY approval for offline fixture; no human authorization")
            source_before = self.git(source, "rev-parse", "HEAD")
            integrated = ReviewGate(manager).integrate(
                task, expected_source_commit=source_before,
                target_branch=self.git(source, "branch", "--show-current"))
            self.assertEqual("integrated", integrated["status"])
            self.assertEqual(second_candidate, self.git(source, "rev-parse", "HEAD"))
            self.assertEqual(base, source_before)

    def test_synchronized_rejection_runs_fresh_crew_and_registers_real_candidate(self):
        """Exercise Source advance -> mechanical M -> fresh rejection feedback."""
        with tempfile.TemporaryDirectory(prefix="revision-sync-completion-") as temporary:
            root = Path(temporary)
            source = fixture(root)
            (source / "Pipeline" / "TaskGraph" / "taskcontrol.py").write_text(
                "print('taskcontrol validate: PASS')\n", encoding="utf-8", newline="\n")
            self.git(source, "add", "Pipeline/TaskGraph/taskcontrol.py")
            self.git(source, "commit", "-qm", "fixture taskcontrol prerequisite")
            outputs = root / "seed-outputs"
            prior, _, prior_dir = execute(source, outputs, "seed_preserve", 921, provider="claude")
            base = self.git(source, "rev-parse", "HEAD")
            task = prior["task_id"]
            manager = Checkouts(source, root / "checkouts")
            manager.prepare(task)
            checkout = manager.root / task
            old_scope = AssistantScopePlanner(manager).plan(
                task, ExecutionScopePlan(
                    ("Assets/Scripts/PlayerMana.cs",), (),
                    ("Assets/Tests/PlayerManaTests.cs",), (),
                ), lease_id="sync-old-lease")
            subprocess.run(["git", "-C", str(checkout), "apply", "--binary",
                            str(prior_dir / "candidate.patch")], check=True)
            self.git(checkout, "add", "Assets/Scripts/PlayerMana.cs",
                     "Assets/Tests/PlayerManaTests.cs")
            self.git(checkout, "commit", "-qm", "fixture first candidate")
            first = self.git(checkout, "rev-parse", "HEAD")
            first_tree = self.git(checkout, "rev-parse", "HEAD^{tree}")
            record_path = manager.records / f"{task}.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            task_hash = record["task_contract_sha256"]
            result_bytes = (prior_dir / "crew_result.json").read_bytes()
            patch_bytes = (prior_dir / "candidate.patch").read_bytes()
            record["candidate"] = {
                "commit": first, "tree": first_tree, "parent": base,
                "run_id": prior["run_id"], "lease_id": old_scope["lease_id"],
                "plan_id": old_scope["plan_id"], "fixture_candidate_metadata": True,
                "receipt": {
                    "task_id": task, "run_id": prior["run_id"],
                    "lease_id": old_scope["lease_id"], "plan_id": old_scope["plan_id"],
                    "candidate_commit": first, "candidate_tree": first_tree,
                    "candidate_parent": base, "source_base": base,
                    "task_contract_sha256": task_hash,
                    "execution_result_sha256": hashlib.sha256(result_bytes).hexdigest(),
                    "candidate_patch_sha256": hashlib.sha256(patch_bytes).hexdigest(),
                },
            }
            write_record(record_path, record)
            ReviewGate(manager).decide(
                task, tested_commit=first, decision="approve",
                message="TESTONLY approval for offline source synchronization")

            # Advance Source independently, then create the mechanical merge M.
            (source / "README-source-advance.txt").write_text(
                "unrelated fixture Source advance\n", encoding="utf-8", newline="\n")
            self.git(source, "add", "README-source-advance.txt")
            self.git(source, "commit", "-qm", "fixture unrelated Source advance")
            source_advance = self.git(source, "rev-parse", "HEAD")
            synced = synchronize_candidate(manager, task, first, source_advance)
            mechanical = synced["candidate"]
            merge_candidate = mechanical["commit"]
            self.assertEqual("source_synchronized", mechanical["kind"])
            self.assertEqual(first, mechanical["parent"])
            self.assertEqual(source_advance, mechanical["source_commit"])
            self.assertEqual(source_advance, self.git(source, "rev-parse", "HEAD"))

            ReviewGate(manager).decide(
                task, tested_commit=merge_candidate, decision="reject",
                message="Fixture-only rejection of M: preserve the source advance and correct the regression.")
            revised = begin_revision(manager, task, merge_candidate)
            self.assertEqual("fresh", revised["revision"]["feedback_mode"])
            self.assertEqual(merge_candidate, revised["revision"]["candidate_commit"])

            new_scope = AssistantScopePlanner(manager).plan(
                task, ExecutionScopePlan(
                    ("Assets/Scripts/PlayerMana.cs",), (),
                    ("Assets/Tests/PlayerManaTests.cs",), (),
                ), lease_id="sync-new-lease")
            admission = reserve(
                manager, task, "sync-worker-921",
                dependency_reader=lambda source_root, task_id, root_path: {
                    "task_id": task_id,
                    "source_commit": self.git(source_root, "rev-parse", "HEAD"),
                    "source_unchanged_during_read": True,
                    "dependencies_satisfied": True,
                    "fixture_dependency_reader": True,
                })
            self.assertEqual(merge_candidate, admission["source_head"])

            output_root = checkout / "Pipeline" / "ExecutionCrew" / "outputs"
            output_root.mkdir(parents=True)
            (checkout / ".git" / "info" / "exclude").write_text(
                "Pipeline/ExecutionCrew/outputs/\n", encoding="utf-8")
            feedback_kwargs = prepare_revision_feedback(
                manager, json.loads(record_path.read_text(encoding="utf-8")), admission,
                {"provider": "claude", "execution_model": prior["execution_model"]})
            feedback_file = Path(feedback_kwargs["revision_feedback_file"])
            feedback_text = "Fixture-only rejection of M: preserve the source advance and correct the regression."
            self.assertEqual(feedback_text.encode("utf-8"), feedback_file.read_bytes())
            # This fixture scenario makes a deterministic production correction on fresh runs;
            # it is not a retry invocation and receives no retry seed arguments.
            state = State("retry_impl_only", checkout, None)
            fresh = run_crew(
                source=checkout, output_root=output_root, task_id=task,
                provider_name="claude",
                implementation_paths=("Assets/Scripts/PlayerMana.cs",),
                test_paths=("Assets/Tests/PlayerManaTests.cs",),
                run_id="sync-worker-921", revision_feedback_file=feedback_file,
                provider_factory=factory(state), _require_physical_read_only_source=False)
            self.assertEqual("review_ready", fresh["crew_status"])
            self.assertIsNone(fresh["retry_seed_mode"])
            self.assertEqual(merge_candidate, fresh["source_head"])
            run_dir = output_root / fresh["run_id"]
            self.assertEqual(feedback_text.encode("utf-8"),
                             (run_dir / "human_review_feedback.txt").read_bytes())
            self.assertEqual(hashlib.sha256(feedback_text.encode("utf-8")).hexdigest(),
                             fresh["revision_feedback_sha256"])
            for role in ("implementer", "test_author", "validator"):
                prompts = [request.prompt for called, request, _ in state.calls if called == role]
                self.assertTrue(prompts, role)
                self.assertTrue(all(feedback_text in prompt for prompt in prompts), role)

            result_path = run_dir / "crew_result.json"
            candidate_path = run_dir / "candidate.patch"
            receipt = ExecutionCrewReceipt(
                run_id=fresh["run_id"], task_id=task, lease_id=new_scope["lease_id"],
                plan_id=new_scope["plan_id"], provider="claude",
                execution_model=fresh["execution_model"], execution_reasoning_effort=None,
                crew_profile=fresh["crew_profile"], validation_profile=fresh["validation_profile"],
                source_head=merge_candidate, task_contract_sha256=task_hash,
                crew_status="review_ready", result_path=str(result_path),
                result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
                candidate_path=str(candidate_path),
                candidate_sha256=hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
                final_actual_changed_paths=tuple(fresh["final_actual_changed_paths"]),
                returncode=0, rejection_reasons=(),
            )
            scope = _scope(manager, json.loads(record_path.read_text(encoding="utf-8")))
            ExecutionCrewBridge(
                checkout=checkout, scope=scope,
                execution_model=receipt.execution_model,
                crew_profile=receipt.crew_profile,
                validation_profile=receipt.validation_profile,
            )._persist(receipt)
            registered = register_candidate(
                manager, task, fresh["run_id"], {
                    "execution_model": receipt.execution_model,
                    "crew_profile": receipt.crew_profile,
                    "validation_profile": receipt.validation_profile,
                })
            second = registered["candidate"]["commit"]
            self.assertEqual(merge_candidate, registered["candidate"]["parent"])
            self.assertEqual(merge_candidate, self.git(checkout, "rev-parse", "HEAD~1"))
            self.assertEqual(source_advance, self.git(source, "rev-parse", "HEAD"))

            with self.assertRaisesRegex(ValueError, "registered"):
                ReviewGate(manager).decide(
                    task, tested_commit=first, decision="approve",
                    message="Fixture-only stale approval")
            ReviewGate(manager).decide(
                task, tested_commit=second, decision="approve",
                message="TESTONLY approval for offline synchronized revision")
            ReviewGate(manager).integrate(
                task, expected_source_commit=source_advance,
                target_branch=self.git(source, "branch", "--show-current"))
            self.assertEqual(second, self.git(source, "rev-parse", "HEAD"))


if __name__ == "__main__":
    unittest.main()
