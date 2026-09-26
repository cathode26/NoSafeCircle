"""A crew retry's feedback path must satisfy the guard the CREW applies to it.

THE DEFECT, measured live on NSC-127 run `nsc-127-20260926t0315z-2` and not
inferred. `execution_bridge._command` translated a retry's feedback file with the
SOURCE mount prefix:

    /workspace/Pipeline/ExecutionCrew/outputs/assistant-feedback/<hash>/feedback.txt

`compose.yaml` mounts the same host directory twice -- `.:/workspace:ro` and
`./Pipeline/ExecutionCrew/outputs:/execution-output:rw` -- and sets
`NSC_EXECUTION_OUTPUT_ROOT: /execution-output`, so inside the container that path
EXISTS, RESOLVES, and is not under the output root.
`run_crew.load_retry_context` then raises through `_resolve_existing_under`:

    ExecutionCrew blocked: human review feedback file must resolve strictly
    underneath the ExecutionCrew output root

That is the whole failure, and it left NSC-127 with no retry route. The host
geometry was never wrong: the container has two names for one directory and the
bridge emitted the one the guard does not measure against.

WHY THIS TEST IS NOT A STRING COMPARISON. Asserting the command contains
"/execution-output/..." would pass on any prefix someone types there later. The
decisive case REPRODUCES THE CREW'S OWN PREDICATE over PurePosixPath -- the
container-side `resolved == root or not is_relative_to(root)` from
`run_crew._resolve_existing_under` -- against the container output root the
compose file actually declares. A test that only matched the new string could not
tell a correct prefix from a plausible one.

`--revision-feedback-file` is asserted to KEEP its `/workspace` form. A fresh run
never calls `load_retry_context`, nothing measures it against the output root, and
three live runs depend on it. Changing it on the strength of this defect would be
the narrow-truth-generalised error; this test pins it so nobody does.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.AssistantControl.test_fresh_revision_feedback import _scope, fixture
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.execution_bridge import (
    ExecutionCrewBridge,
    ExecutionBridgeError,
)

TASK = "NSC-005"
#: What `compose.yaml` declares for the exec services. Read from the repository in
#: `test_the_container_output_root_is_the_one_compose_declares` rather than
#: trusted here, so this constant cannot drift away from the deployment.
CONTAINER_OUTPUT_ROOT = PurePosixPath("/execution-output")
CONTAINER_SOURCE_ROOT = PurePosixPath("/workspace")


def strictly_under(root: PurePosixPath, candidate: PurePosixPath) -> bool:
    """`run_crew._resolve_existing_under`'s predicate, without the filesystem.

    The crew calls `resolve(strict=True)` on both and then applies exactly this.
    Reproducing the comparison is the point: the container paths do not exist on
    this host, and the property under test is the containment, not the file.
    """
    return candidate != root and candidate.is_relative_to(root)


class RetryFeedbackContainerPath(unittest.TestCase):
    def build(self, temporary: str):
        root = Path(temporary)
        source = fixture(root)
        manager = Checkouts(source, root / "checkouts")
        manager.prepare(TASK)
        accepted = AssistantScopePlanner(manager).plan(
            TASK, ExecutionScopePlan(
                ("Assets/Scripts/PlayerMana.cs",), (),
                ("Assets/Tests/PlayerManaTests.cs",), (),
            ), lease_id="retry-path-lease")
        scope = _scope(manager, json.loads(
            (manager.records / f"{TASK}.json").read_text(encoding="utf-8")))
        checkout = manager.root / TASK
        bridge = ExecutionCrewBridge(
            checkout=checkout, scope=scope, execution_model="fixture-model",
            crew_profile="full", validation_profile="full_relevant")
        return manager, scope, checkout, bridge, accepted

    @staticmethod
    def write_retry_feedback(checkout: Path) -> Path:
        """Where `revision_feedback.py` puts a legacy-retry feedback file."""
        feedback = (checkout / "Pipeline" / "ExecutionCrew" / "outputs"
                    / "assistant-feedback" / ("a" * 64) / "feedback.txt")
        feedback.parent.mkdir(parents=True)
        feedback.write_text("TESTONLY retry feedback\n", encoding="utf-8")
        return feedback

    @staticmethod
    def emitted(command: list[str], flag: str) -> str:
        index = command.index(flag)
        return command[index + 1]

    # ------------------------------------------------------------- the decisive case
    def test_the_retry_feedback_path_satisfies_the_crews_own_containment_guard(self):
        with tempfile.TemporaryDirectory(prefix="retry-feedback-path-") as temporary:
            _, scope, checkout, bridge, _ = self.build(temporary)
            feedback = self.write_retry_feedback(checkout)
            command = bridge._command(
                scope.accepted, provider="claude", retry_run_id="prior-run-1",
                feedback_file=feedback, revision_feedback_file=None)
            self.assertIn("--review-feedback-file", command)
            emitted = PurePosixPath(self.emitted(command, "--review-feedback-file"))
            self.assertTrue(
                strictly_under(CONTAINER_OUTPUT_ROOT, emitted),
                "the crew resolves this against %s and refuses anything not strictly "
                "underneath it; got %s" % (CONTAINER_OUTPUT_ROOT, emitted))
            # And the failing form is specifically excluded: /workspace/... also
            # resolves in the container, which is why the old bug was invisible
            # until the guard ran.
            self.assertFalse(strictly_under(CONTAINER_SOURCE_ROOT, emitted), emitted)
            self.assertEqual(
                emitted,
                CONTAINER_OUTPUT_ROOT / "assistant-feedback" / ("a" * 64) / "feedback.txt")

    def test_the_old_workspace_form_would_have_failed_that_same_guard(self):
        """The control. Without it, the assertion above could pass by accident.

        This is the exact string the bridge used to emit. If it satisfied the
        crew's predicate, the defect would not exist and the test above would be
        proving nothing.
        """
        old = PurePosixPath("/workspace/Pipeline/ExecutionCrew/outputs/"
                            "assistant-feedback/" + "a" * 64 + "/feedback.txt")
        self.assertFalse(strictly_under(CONTAINER_OUTPUT_ROOT, old),
                         "the pre-fix path must fail the guard, or nothing was wrong")
        self.assertTrue(strictly_under(CONTAINER_SOURCE_ROOT, old),
                        "and it must be a real path under the source mount")

    # ------------------------------------------------------- the deployment is the authority
    def test_the_container_output_root_is_the_one_compose_declares(self):
        """This test's constant must match the deployment, not the other way round.

        `CLAUDE.md`'s own rule: a check whose expectations come from the artifact
        it checks cannot catch the field you forgot. So read compose.yaml.
        """
        compose = Path(__file__).resolve().parents[2] / "compose.yaml"
        text = compose.read_text(encoding="utf-8")
        self.assertIn("NSC_EXECUTION_OUTPUT_ROOT: %s" % CONTAINER_OUTPUT_ROOT, text)
        self.assertIn("./Pipeline/ExecutionCrew/outputs:%s:rw" % CONTAINER_OUTPUT_ROOT, text)
        self.assertIn(".:%s:ro" % CONTAINER_SOURCE_ROOT, text)

    # ------------------------------------------------------- what must NOT change
    def test_fresh_revision_feedback_keeps_the_workspace_prefix(self):
        """Three live runs depend on this path; the retry defect does not touch it."""
        with tempfile.TemporaryDirectory(prefix="retry-feedback-fresh-") as temporary:
            _, scope, checkout, bridge, _ = self.build(temporary)
            feedback = (checkout / "Pipeline" / "ExecutionCrew" / "outputs"
                        / "revision-feedback.txt")
            feedback.parent.mkdir(parents=True)
            feedback.write_text("TESTONLY fresh feedback\n", encoding="utf-8")
            command = bridge._command(
                scope.accepted, provider="claude", retry_run_id=None,
                feedback_file=None, revision_feedback_file=feedback)
            emitted = PurePosixPath(self.emitted(command, "--revision-feedback-file"))
            self.assertTrue(strictly_under(CONTAINER_SOURCE_ROOT, emitted), emitted)
            self.assertEqual(
                emitted,
                CONTAINER_SOURCE_ROOT / "Pipeline/ExecutionCrew/outputs/revision-feedback.txt")

    def test_a_retry_feedback_file_outside_the_output_root_is_refused_by_name(self):
        """A refusal that names the output root, not a traceback from relative_to."""
        with tempfile.TemporaryDirectory(prefix="retry-feedback-outside-") as temporary:
            _, scope, checkout, bridge, _ = self.build(temporary)
            stray = checkout / "Assets" / "stray-feedback.txt"
            stray.parent.mkdir(parents=True, exist_ok=True)
            stray.write_text("TESTONLY stray\n", encoding="utf-8")
            with self.assertRaises(ExecutionBridgeError) as caught:
                bridge._command(
                    scope.accepted, provider="claude", retry_run_id="prior-run-1",
                    feedback_file=stray, revision_feedback_file=None)
            self.assertIn("ExecutionCrew output root", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
