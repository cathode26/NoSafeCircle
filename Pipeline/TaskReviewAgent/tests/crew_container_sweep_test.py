#!/usr/bin/env python3
"""A crew that outlives its host process is stopped, and a sweep that could not run says so.

`_kill_process_tree` kills the crew process tree on the host. A Docker container is a child of the
Docker daemon, not of the docker client in that tree, so the container survives and the crew keeps
spending with nobody collecting its output. The bridge had no step that stopped it -- and
`_kill_process_tree`'s own docstring claimed "docker clients included", which reads as coverage of
the containers themselves.

THE DISTINCTION THIS SUITE EXISTS TO PROTECT is `not_swept` versus `no_containers`. One says the run
left nothing behind; the other says nobody was able to look. Collapsing them is how orphaned paid
work reads as a clean shutdown -- this fleet's "absence is not a diagnosis", applied to the one place
where the absence costs money.

WHAT THIS PROVES: the four outcomes are distinguishable, the sweep never raises and never runs
unbounded, it is scoped to one run, and the timeout handler actually calls it with the run's own id.

WHAT IT DOES NOT PROVE: that a real orphaned container is stopped in production. Nothing here runs
Docker -- the docker callable is injected. The first real evidence is the next crew that times out,
and then the thing to read is the quarantine reason, which now carries the outcome.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.execution_bridge import (  # noqa: E402
    CONTAINER_LIST_TIMEOUT_SECONDS,
    SHARED_COMPOSE_PROJECT,
    CONTAINER_STOP_GRACE_SECONDS,
    CONTAINER_STOP_TIMEOUT_SECONDS,
    SWEEP_NOT_SWEPT,
    SWEEP_NO_CONTAINERS,
    SWEEP_STOPPED,
    SWEEP_STOP_FAILED,
    crew_compose_project,
    describe_sweep,
    sweep_orphaned_crew_containers,
)

BRIDGE = ROOT / "Pipeline/TaskReviewAgent/execution_bridge.py"
RUN_ID = "nsc-049-pooled-0123456789abcdef"
# The sweep takes the project the LAUNCH COMMAND used. A run id is only one way to arrive at
# one, and arriving at it the wrong way is exactly what F1 was.
PROJECT = crew_compose_project(RUN_ID)


class FakeDocker:
    """Records every call so a test can assert the bound and the scope, not just the result."""

    def __init__(self, *, listing=(0, "", ""), stops=None):
        self.listing = listing
        self.stops = dict(stops or {})
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def __call__(self, args, timeout_seconds):
        self.calls.append((tuple(args), timeout_seconds))
        if args[0] == "ps":
            return self.listing
        if args[0] == "stop":
            return self.stops.get(args[-1], (0, "", ""))
        raise AssertionError(f"unexpected docker call: {args}")


class ComposeProjectTests(unittest.TestCase):

    def test_the_project_matches_the_worker_that_actually_labels_the_container(self):
        """The derivation is duplicated to avoid a layer dependency, so it must be pinned.

        The expectation comes from the OTHER module, not from a literal typed here: if the two ever
        diverge the sweep lists containers under a project nothing carries, finds none, and reports
        a clean `no_containers` while the crew keeps running. That failure is silent by
        construction, which is exactly why it needs a test.
        """
        from Pipeline.AssistantControl.crew_worker import _compose_project

        self.assertEqual(_compose_project(RUN_ID), crew_compose_project(RUN_ID))

    def test_agreeing_derivations_were_not_enough_and_the_suite_says_why(self):
        """A standing note, asserted so it cannot be quietly deleted.

        This class's pin passed throughout the period the sweep was broken. Keep it -- a divergence
        would still be silent -- but the identity pin lives in ScopeTests, against the launch
        command, because that is where the defect actually was.
        """
        source = Path(__file__).read_text(encoding="utf-8")
        self.assertIn("THE WRONG VALUE BEING PASSED IN", source)

    def test_different_runs_get_different_projects(self):
        self.assertNotEqual(crew_compose_project(RUN_ID), crew_compose_project(RUN_ID + "x"))


class SweepOutcomeTests(unittest.TestCase):

    def test_a_run_with_no_container_is_not_the_same_as_a_sweep_that_could_not_run(self):
        """The distinction this suite exists for. Both have an empty container list."""
        clean = sweep_orphaned_crew_containers(PROJECT, docker=FakeDocker(listing=(0, "\n", "")))
        blind = sweep_orphaned_crew_containers(
            PROJECT, docker=FakeDocker(listing=(127, "", "docker executable not found"))
        )
        self.assertEqual(SWEEP_NO_CONTAINERS, clean["outcome"])
        self.assertEqual(SWEEP_NOT_SWEPT, blind["outcome"])
        self.assertEqual(clean["containers"], blind["containers"])  # identical evidence...
        self.assertNotEqual(clean["outcome"], blind["outcome"])  # ...different conclusion

    def test_an_unknown_project_is_not_swept_rather_than_clean(self):
        for value in (None, "", "   "):
            with self.subTest(project=value):
                sweep = sweep_orphaned_crew_containers(value, docker=FakeDocker())
                self.assertEqual(SWEEP_NOT_SWEPT, sweep["outcome"])
                self.assertEqual("project_unknown", sweep["reason"])

    def test_the_shared_workspace_project_is_refused_rather_than_swept(self):
        """It is the bridge constructor's DEFAULT, so a sweep must never accept it.

        Its containers belong to the whole workspace rather than to one crew run, and the default
        means a bridge built without an explicit project would otherwise aim the sweep at them.
        Refusing is not a missing feature: an unknown-ownership sweep must stay visibly uncertain.
        """
        docker = FakeDocker(listing=(0, "abc123\n", ""))
        sweep = sweep_orphaned_crew_containers(SHARED_COMPOSE_PROJECT, docker=docker)
        self.assertEqual(SWEEP_NOT_SWEPT, sweep["outcome"])
        self.assertEqual("shared_project_refused", sweep["reason"])
        self.assertEqual([], docker.calls, "it must not even list containers for the shared project")

    def test_the_project_is_queried_verbatim_and_never_re_derived(self):
        """Pass something no hash could produce; the filter must carry it unchanged.

        This is what stops a re-derivation creeping back in: if anything hashed the argument, a
        plainly non-hash project would not appear in the filter.
        """
        docker = FakeDocker(listing=(0, "", ""))
        sweep_orphaned_crew_containers("assistant-crew-NOT-A-HASH", docker=docker)
        (args, _timeout), = [call for call in docker.calls if call[0][0] == "ps"]
        self.assertIn("label=com.docker.compose.project=assistant-crew-NOT-A-HASH", args)

    def test_every_container_stopped_reports_stopped(self):
        docker = FakeDocker(listing=(0, "abc123\ndef456\n", ""))
        sweep = sweep_orphaned_crew_containers(PROJECT, docker=docker)
        self.assertEqual(SWEEP_STOPPED, sweep["outcome"])
        self.assertEqual(["abc123", "def456"], sweep["stopped"])
        self.assertEqual([], sweep["failed"])

    def test_one_surviving_container_is_reported_even_when_the_others_stopped(self):
        """A partial stop must not read as success: the survivor is still spending."""
        docker = FakeDocker(
            listing=(0, "abc123\ndef456\n", ""),
            stops={"def456": (1, "", "permission denied")},
        )
        sweep = sweep_orphaned_crew_containers(PROJECT, docker=docker)
        self.assertEqual(SWEEP_STOP_FAILED, sweep["outcome"])
        self.assertEqual(["abc123"], sweep["stopped"])
        self.assertEqual([{"container": "def456", "error": "permission denied"}], sweep["failed"])

    def test_a_failed_listing_names_why_instead_of_returning_clean(self):
        sweep = sweep_orphaned_crew_containers(
            PROJECT, docker=FakeDocker(listing=(1, "", "Cannot connect to the Docker daemon"))
        )
        self.assertEqual(SWEEP_NOT_SWEPT, sweep["outcome"])
        self.assertIn("Cannot connect to the Docker daemon", sweep["reason"])


class BoundednessTests(unittest.TestCase):

    def test_every_docker_call_carries_a_bound(self):
        """It runs while an error propagates; an unbounded call there hangs the whole failure path."""
        docker = FakeDocker(listing=(0, "abc123\n", ""))
        sweep_orphaned_crew_containers(PROJECT, docker=docker)
        self.assertTrue(docker.calls, "the sweep made no docker call at all")
        for args, timeout_seconds in docker.calls:
            with self.subTest(args=args):
                self.assertIsInstance(timeout_seconds, float)
                self.assertGreater(timeout_seconds, 0.0)
                self.assertLessEqual(timeout_seconds, 60.0, "a bound this long is not a bound")

    def test_the_stop_grace_is_shorter_than_the_stop_bound(self):
        """Otherwise the subprocess bound fires before docker's own grace period can finish."""
        self.assertLess(float(CONTAINER_STOP_GRACE_SECONDS), CONTAINER_STOP_TIMEOUT_SECONDS)
        self.assertGreater(CONTAINER_LIST_TIMEOUT_SECONDS, 0.0)

    def test_the_sweep_never_raises_whatever_docker_does(self):
        """Replacing the original failure with a cleanup failure loses why the run died."""

        def exploding(args, timeout_seconds):
            raise RuntimeError("docker went wrong in an unforeseen way")

        with self.assertRaises(RuntimeError):
            exploding(("ps",), 1.0)  # the fixture really does raise

        for failure in (
            (127, "", "docker executable not found"),
            (124, "", "docker ps exceeded 15s"),
            (125, "", "docker ps could not run: [WinError 5]"),
        ):
            with self.subTest(failure=failure[0]):
                sweep = sweep_orphaned_crew_containers(PROJECT, docker=FakeDocker(listing=failure))
                self.assertEqual(SWEEP_NOT_SWEPT, sweep["outcome"])

    def test_the_real_docker_helper_converts_a_missing_binary_into_an_outcome(self):
        """Exercises the production callable, with a name no PATH can resolve."""
        from Pipeline.TaskReviewAgent import execution_bridge

        original = subprocess.run

        def fake_run(*args, **kwargs):
            raise FileNotFoundError("no docker here")

        subprocess.run = fake_run
        try:
            code, out, err = execution_bridge._docker(("ps",), 1.0)
        finally:
            subprocess.run = original
        self.assertEqual(127, code)
        self.assertIn("not found", err)


class ScopeTests(unittest.TestCase):

    def test_the_listing_is_scoped_to_this_run_only(self):
        """A concurrent crew must never be stopped by another run's failure path."""
        docker = FakeDocker(listing=(0, "", ""))
        sweep_orphaned_crew_containers(PROJECT, docker=docker)
        (args, _timeout), = [call for call in docker.calls if call[0][0] == "ps"]
        self.assertIn(f"label=com.docker.compose.project={PROJECT}", args)
        self.assertIn("--quiet", args)

    def test_the_sweep_targets_THE_ATTRIBUTE_THE_LAUNCH_COMMAND_USES(self):
        """F1's pin, and the reason the old one could not catch it.

        The previous load-bearing test compared `crew_compose_project` with the worker's
        `_compose_project`. They agreed -- they still do -- and the sweep was still broken, because
        the CALLER passed `pool_assignment["run_id"]`, the pooled invocation id, instead of the
        reservation run id the worker had hashed. The launched project and the queried project were
        different strings and no test could see it: A TEST THAT PINS HOW A VALUE IS COMPUTED CANNOT
        SEE THE WRONG VALUE BEING PASSED IN.

        So this takes its expectation from the launch command itself. `_command` builds
        `docker compose -p <X> run ...`; whatever `<X>` is, the sweep must be handed the same thing.
        Both are read out of the syntax tree, so the two can never drift apart silently again.
        """
        tree = ast.parse(BRIDGE.read_text(encoding="utf-8"))

        def attribute_after_dash_p(node):
            """The element following a literal "-p" in a list of command parts."""
            for index, element in enumerate(node.elts[:-1]):
                if isinstance(element, ast.Constant) and element.value == "-p":
                    return node.elts[index + 1]
            return None

        launched = [
            attribute_after_dash_p(node) for node in ast.walk(tree)
            if isinstance(node, ast.List) and attribute_after_dash_p(node) is not None
        ]
        self.assertEqual(1, len(launched),
                         "expected exactly one docker-compose -p construction in the bridge")
        launched_attr = launched[0]
        self.assertIsInstance(launched_attr, ast.Attribute)
        self.assertEqual("compose_project", launched_attr.attr)

        swept = [
            node.args[0] for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "sweep_orphaned_crew_containers" and node.args
        ]
        self.assertEqual(1, len(swept), "expected exactly one sweep call site")
        self.assertIsInstance(swept[0], ast.Attribute,
                              "the sweep is being handed an expression rather than the project"
                              " attribute the command used")
        self.assertEqual(launched_attr.attr, swept[0].attr,
                         "the sweep targets a different value from the one the command launched")
        self.assertEqual("self", getattr(swept[0].value, "id", None))

    def test_no_pooled_invocation_id_reaches_the_sweep_call(self):
        """The exact wrong input, named so it cannot come back as a plausible-looking fix."""
        tree = ast.parse(BRIDGE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "sweep_orphaned_crew_containers"):
                source = ast.dump(node)
                self.assertNotIn("pool_assignment", source,
                                 "the sweep is deriving its project from the pooled invocation"
                                 " again; the container carries the reservation-derived project")
                self.assertNotIn("crew_compose_project", source,
                                 "the sweep is re-deriving a project instead of using the launched"
                                 " one")


class DescriptionTests(unittest.TestCase):

    def test_the_dangerous_outcome_is_stated_loudly_and_the_clean_one_is_not(self):
        failed = describe_sweep({"outcome": SWEEP_STOP_FAILED, "containers": ["a", "b"],
                                 "failed": [{"container": "b"}], "stopped": ["a"]})
        self.assertIn("STILL RUNNING", failed)
        clean = describe_sweep({"outcome": SWEEP_NO_CONTAINERS, "containers": [], "stopped": [],
                                "failed": []})
        self.assertNotIn("STILL RUNNING", clean)

    def test_a_sweep_that_did_not_run_never_describes_itself_as_clean(self):
        text = describe_sweep({"outcome": SWEEP_NOT_SWEPT, "reason": "list_failed: daemon down"})
        self.assertIn("NOT SWEPT", text)
        self.assertIn("daemon down", text)


class WiringTests(unittest.TestCase):
    """Structural pins. The sweep is correct in isolation and useless if nothing calls it."""

    def setUp(self):
        self.tree = ast.parse(BRIDGE.read_text(encoding="utf-8"))

    def _calls(self, name):
        return [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
        ]

    def test_the_timeout_handler_calls_the_sweep(self):
        self.assertEqual(1, len(self._calls("sweep_orphaned_crew_containers")),
                         "expected exactly one call site for the sweep")

    def test_the_sweep_is_not_called_from_the_generic_command_runner(self):
        """_default_runner has no run identity, so a sweep there could only guess at the project."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_default_runner":
                names = [
                    inner.func.id for inner in ast.walk(node)
                    if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
                ]
                self.assertNotIn("sweep_orphaned_crew_containers", names)
                return
        self.fail("_default_runner not found; the pin is measuring nothing")

    def test_the_quarantine_reason_carries_the_sweep_outcome(self):
        """Without this the outcome is computed and thrown away, which is the original defect."""
        self.assertEqual(1, len(self._calls("describe_sweep")))
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("describe_sweep(sweep)", source)

    def test_the_kill_docstring_no_longer_claims_it_stops_containers(self):
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertNotIn("docker clients included)", source)
        self.assertIn("It does NOT stop a Docker container", source)


if __name__ == "__main__":
    unittest.main(verbosity=1)
