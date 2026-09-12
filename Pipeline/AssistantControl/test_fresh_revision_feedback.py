"""Focused offline tests for fresh scoped revision feedback transport."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.ExecutionCrew.run_crew import CrewBlocked, run_crew
from Pipeline.ExecutionCrew.tests.execution_crew_smoke_test import (
    State, factory, fixture,
)
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge
from Pipeline.AssistantControl.candidate import _scope


class FreshRevisionFeedbackTests(unittest.TestCase):
    def test_fresh_feedback_reaches_roles_and_is_persisted_exactly(self):
        with tempfile.TemporaryDirectory(prefix="fresh-revision-feedback-") as temporary:
            root = Path(temporary)
            source = fixture(root)
            output_root = source / "Pipeline" / "ExecutionCrew" / "outputs"
            output_root.mkdir(parents=True)
            (source / ".git" / "info" / "exclude").write_text(
                "Pipeline/ExecutionCrew/outputs/\n", encoding="utf-8")
            feedback_text = "TESTONLY revision feedback: preserve the rejected-base context.\n"
            feedback_file = output_root / "revision-feedback.txt"
            feedback_file.write_text(feedback_text, encoding="utf-8", newline="\n")
            state = State("seed_preserve", source, None)
            result = run_crew(
                source=source, output_root=output_root, task_id="NSC-005",
                provider_name="claude", implementation_paths=("Assets/Scripts/PlayerMana.cs",),
                test_paths=("Assets/Tests/PlayerManaTests.cs",),
                run_id="fresh-revision-feedback-1",
                revision_feedback_file=feedback_file,
                provider_factory=factory(state),
                _require_physical_read_only_source=False,
            )
            self.assertEqual("review_ready", result["crew_status"])
            run_dir = output_root / result["run_id"]
            persisted = run_dir / "human_review_feedback.txt"
            self.assertEqual(feedback_text, persisted.read_text(encoding="utf-8"))
            expected_hash = hashlib.sha256(feedback_text.encode("utf-8")).hexdigest()
            self.assertEqual(expected_hash, result["revision_feedback_sha256"])
            self.assertEqual("human_review_feedback.txt", result["revision_feedback_file"])
            self.assertEqual(
                "", self._git(source, "status", "--porcelain=v1", "--untracked-files=all")
            )
            for role in ("implementer", "test_author", "validator"):
                prompts = [request.prompt for called, request, _ in state.calls if called == role]
                self.assertTrue(prompts, role)
                self.assertTrue(all(feedback_text.strip() in prompt for prompt in prompts), role)

    def test_retry_cannot_be_combined_with_fresh_revision_feedback(self):
        with tempfile.TemporaryDirectory(prefix="fresh-revision-feedback-combine-") as temporary:
            root = Path(temporary)
            source = fixture(root)
            feedback = source / "feedback.txt"
            feedback.write_text("TESTONLY feedback\n", encoding="utf-8")
            with self.assertRaisesRegex(CrewBlocked, "combined"):
                run_crew(
                    source=source, output_root=root / "outputs",
                    retry_run_id="prior-run", review_feedback_file=feedback,
                    revision_feedback_file=feedback,
                )

    def test_bridge_maps_fresh_feedback_only_to_normal_command(self):
        with tempfile.TemporaryDirectory(prefix="fresh-revision-bridge-") as temporary:
            root = Path(temporary)
            source = fixture(root)
            manager = Checkouts(source, root / "checkouts")
            manager.prepare("NSC-005")
            accepted = AssistantScopePlanner(manager).plan(
                "NSC-005", ExecutionScopePlan(
                    ("Assets/Scripts/PlayerMana.cs",), (),
                    ("Assets/Tests/PlayerManaTests.cs",), (),
                ), lease_id="fresh-lease")
            scope = _scope(manager, json.loads(
                (manager.records / "NSC-005.json").read_text(encoding="utf-8")))
            checkout = manager.root / "NSC-005"
            feedback = checkout / "Pipeline" / "ExecutionCrew" / "outputs" / "feedback.txt"
            feedback.parent.mkdir(parents=True)
            feedback.write_text("TESTONLY bridge feedback\n", encoding="utf-8")
            bridge = ExecutionCrewBridge(
                checkout=checkout, scope=scope, execution_model="fixture-model",
                crew_profile="full", validation_profile="full_relevant")
            command = bridge._command(
                scope.accepted, provider="claude", retry_run_id=None,
                feedback_file=None, revision_feedback_file=feedback)
            self.assertIn("--revision-feedback-file", command)
            self.assertIn("/workspace/Pipeline/ExecutionCrew/outputs/feedback.txt", command)
            self.assertNotIn("--review-feedback-file", command)
            self.assertEqual("fresh-lease", accepted["lease_id"])

    def test_bridge_run_forwards_default_and_fresh_feedback_to_prepared_runner(self):
        """Exercise run -> _run_prepared without starting Docker or a provider."""
        class RunnerSentinel(RuntimeError):
            pass

        for fresh in (False, True):
            with self.subTest(fresh=fresh), tempfile.TemporaryDirectory(
                    prefix="fresh-revision-bridge-run-") as temporary:
                root = Path(temporary)
                source = fixture(root)
                manager = Checkouts(source, root / "checkouts")
                manager.prepare("NSC-005")
                accepted = AssistantScopePlanner(manager).plan(
                    "NSC-005", ExecutionScopePlan(
                        ("Assets/Scripts/PlayerMana.cs",), (),
                        ("Assets/Tests/PlayerManaTests.cs",), (),
                    ), lease_id="fresh-run-lease")
                checkout = manager.root / "NSC-005"
                (checkout / ".git" / "info" / "exclude").write_text(
                    "Pipeline/ExecutionCrew/outputs/\n", encoding="utf-8")
                feedback = None
                if fresh:
                    feedback = (checkout / "Pipeline" / "ExecutionCrew" /
                                "outputs" / "revision-feedback.txt")
                    feedback.parent.mkdir(parents=True)
                    feedback.write_text("TESTONLY bridge run feedback\n", encoding="utf-8")
                calls = []

                def runner(command, cwd, timeout):
                    calls.append((list(command), Path(cwd), timeout))
                    raise RunnerSentinel("fixture runner reached _run_prepared")

                scope = _scope(manager, json.loads(
                    (manager.records / "NSC-005.json").read_text(encoding="utf-8")))
                bridge = ExecutionCrewBridge(
                    checkout=checkout, scope=scope, execution_model="fixture-model",
                    crew_profile="full", validation_profile="full_relevant",
                    command_runner=runner)
                with self.assertRaises(RunnerSentinel):
                    bridge.run(
                        plan_id=accepted["plan_id"], provider="claude",
                        revision_feedback_file=feedback)
                self.assertEqual(1, len(calls))
                command = calls[0][0]
                self.assertEqual(fresh, "--revision-feedback-file" in command)
                self.assertEqual(fresh, any(
                    item.endswith("/Pipeline/ExecutionCrew/outputs/revision-feedback.txt")
                    for item in command))
                self.assertNotIn("--review-feedback-file", command)

    @staticmethod
    def _git(root: Path, *args: str) -> str:
        import subprocess
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, check=True).stdout


if __name__ == "__main__":
    unittest.main()
