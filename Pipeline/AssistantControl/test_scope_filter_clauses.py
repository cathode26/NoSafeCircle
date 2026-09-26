"""A validation filter must not stop the task that exists to write the test it names.

THE DEADLOCK. `automatic_scope_plan` already supports a test that does not exist
yet: an uncommitted path in `exclusive_resources` lands in `new_test_paths` and
plans fine. The SAME file named through a validation FILTER used to hard-raise at
`_resolve_test_paths`, so a task whose whole purpose is to write that test could
never be scoped and therefore never dispatched. Measured over all 128 committed
contracts on 2026-09-25: ten refused on a filter, and five of them started
planning the moment the resolver consulted the contract's own declaration --
NSC-008 Frost Field and NSC-009 Force Wave among them, both required spells.
Reported by the GER Agent, which measured the refusals and refused to rewrite the
contract entries to make scheduling work.

THE SECOND DEFECT WAS WORSE, BECAUSE IT DID NOT REFUSE. The Unity runner joins
several test classes with ";" -- eleven entries across nine live contracts use
it. The resolver walked DOT segments in reverse, so on a joined string it took
the LAST class and returned one path for a filter naming thirteen, silently. NSC-077
plans OK today and eight of the thirteen classes its own gates name were absent
from its scope plan; those paths are also what `admission._reservation_resources`
registers, so the contention guard could not see them either.

THE DECISIVE TEST IS `test_a_resolvable_last_clause_no_longer_hides_an_unresolvable_first`:
before this change that filter returned one path and raised nothing, which is the
only failure here that a passing suite could never have revealed.

Every case builds a throwaway repository. Nothing reads or writes live state.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

# ONLY `_resolve_test_paths` is imported at module scope, deliberately. The two
# helpers below are new, so importing them here would make the whole module fail
# to IMPORT when the implementation is reverted -- an ImportError, which proves
# the helpers are absent and says nothing about behaviour. The behavioural cases
# must fail behaviourally on the old code, so the helpers are imported inside the
# two tests that are about the helpers themselves.
from Pipeline.AssistantControl.graph_controller import _resolve_test_paths

PIN = "a" * 64
TESTS = "Assets/NoSafeCircle/DoorPrototype/Tests"
NAMESPACE = "NoSafeCircle.DoorPrototype.Tests"


class ScopeFilterClauseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nsc-filter-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ("AlphaPlayModeTests", "BetaPlayModeTests"):
            path = self.root / TESTS / f"{name}.cs"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"class {name} {{}}\n", encoding="utf-8")
        editor = self.root / TESTS / "Editor/GammaTests.cs"
        editor.parent.mkdir(parents=True, exist_ok=True)
        editor.write_text("class GammaTests {}\n", encoding="utf-8")
        # Two files sharing a stem, so ambiguity has something to be ambiguous about.
        for prefix in ("Editor", "Editor/Nested"):
            path = self.root / TESTS / prefix / "TwinTests.cs"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("class TwinTests {}\n", encoding="utf-8")
        self.git("init", "-b", "master")
        self.git("config", "user.name", "Filter Fixture")
        self.git("config", "user.email", "filter@example.invalid")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args],
                              capture_output=True, check=True).stdout.decode().strip()

    def commit(self, policy_filters=None) -> str:
        """Commit the tree, optionally with a validation policy for NSC-901.

        The policy path is the only way to reach a SEMICOLON-JOINED filter:
        `_FILTER_RE` stops at the first character outside
        `[A-Za-z0-9_.+`]`, so a filter written into a completion gate is
        truncated at the semicolon before `_resolve_test_paths` ever sees it.
        That truncation is a separate defect and is deliberately not touched
        here; this fixture documents it by having to work around it.
        """
        if policy_filters is not None:
            path = self.root / "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "tasks": {"NSC-901": {"task_contract_sha256": PIN,
                                      "test_filters": policy_filters}},
            }), encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-m", "filter fixture")
        return self.git("rev-parse", "HEAD")

    @staticmethod
    def task(*, gates=(), resources=()):
        return {
            "id": "NSC-901",
            "task_contract_sha256": PIN,
            "exclusive_resources": list(resources),
            "completion_gates": [{"requirement": f"Unity EditMode filter {value} passes"}
                                 for value in gates],
        }

    def resolve(self, task, head):
        return _resolve_test_paths(self.root, task, head)

    # ---------------------------------------------------------------- clauses
    def test_a_filter_entry_can_name_several_classes(self):
        from Pipeline.AssistantControl.graph_controller import _filter_clauses
        self.assertEqual(["A.One", "B.Two", "C.Three"],
                         _filter_clauses("A.One;B.Two; C.Three "))
        self.assertEqual(["A.One"], _filter_clauses("A.One"))
        self.assertEqual([], _filter_clauses("  ;  "))

    def test_every_class_in_a_semicolon_joined_filter_is_resolved(self):
        head = self.commit({"PlayMode": f"{NAMESPACE}.AlphaPlayModeTests;"
                                        f"{NAMESPACE}.BetaPlayModeTests"})
        self.assertEqual(
            [f"{TESTS}/AlphaPlayModeTests.cs", f"{TESTS}/BetaPlayModeTests.cs"],
            sorted(self.resolve(self.task(), head)))

    def test_a_resolvable_last_clause_no_longer_hides_an_unresolvable_first(self):
        """The decisive case, and the only one a passing suite could never reveal.

        The resolver walks dot segments in REVERSE, so on a joined string the
        last class was found first and the ones before it were never looked at.
        A filter naming a class that does not exist AND one that does returned a
        path and raised nothing.
        """
        head = self.commit({"PlayMode": f"{NAMESPACE}.MissingPlayModeTests;"
                                        f"{NAMESPACE}.AlphaPlayModeTests"})
        with self.assertRaises(ValueError) as caught:
            self.resolve(self.task(), head)
        self.assertIn("MissingPlayModeTests", str(caught.exception))

    def test_an_unresolvable_clause_is_named_on_its_own(self):
        """Before, the message quoted the whole joined string and named no class,
        so a reader could not tell which of them was missing."""
        joined = f"{NAMESPACE}.AlphaPlayModeTests;{NAMESPACE}.GhostTests"
        head = self.commit({"PlayMode": joined})
        with self.assertRaises(ValueError) as caught:
            self.resolve(self.task(), head)
        message = str(caught.exception)
        self.assertIn(f"'{NAMESPACE}.GhostTests'", message)
        self.assertNotIn(joined, message)
        self.assertIn("not declared by this task", message)

    # --------------------------------------------------------------- deadlock
    def test_a_filter_naming_a_test_this_task_declares_does_not_refuse(self):
        """The deadlock. The task exists to write `DeltaPlayModeTests`, declares
        it, and its gate names it -- which used to refuse."""
        head = self.commit()
        task = self.task(gates=[f"{NAMESPACE}.DeltaPlayModeTests"],
                         resources=[f"repo-file:{TESTS}/DeltaPlayModeTests.cs"])
        self.assertEqual([], self.resolve(task, head))

    def test_a_declared_clause_contributes_no_path_of_its_own(self):
        """Resolution must not invent authority. A declared path is already in
        the plan, put there by `automatic_scope_plan`'s resource loop, so
        returning it here would duplicate it -- and returning an UNDECLARED
        uncommitted path would grant a write the contract never named."""
        head = self.commit()
        task = self.task(
            gates=[f"{NAMESPACE}.AlphaPlayModeTests"],
            resources=[f"repo-file:{TESTS}/DeltaPlayModeTests.cs"])
        self.assertEqual([f"{TESTS}/AlphaPlayModeTests.cs"], self.resolve(task, head))

    def test_a_committed_clause_still_resolves_when_the_task_declares_it_too(self):
        head = self.commit()
        task = self.task(gates=[f"{NAMESPACE}.AlphaPlayModeTests"],
                         resources=[f"repo-file:{TESTS}/AlphaPlayModeTests.cs"])
        self.assertEqual([f"{TESTS}/AlphaPlayModeTests.cs"], self.resolve(task, head))

    def test_only_declared_TEST_paths_count(self):
        """A declared implementation file must not satisfy a test filter."""
        from Pipeline.AssistantControl.graph_controller import _declared_test_paths
        head = self.commit()
        declared = _declared_test_paths({"exclusive_resources": [
            f"repo-file:{TESTS}/DeltaPlayModeTests.cs",
            "repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/Delta.cs",
            f"repo-file:{TESTS}/NotCSharp.txt",
            f"logical:{TESTS}/Locked.cs",
        ]})
        self.assertEqual({"DeltaPlayModeTests"}, set(declared))
        task = self.task(gates=["NoSafeCircle.DoorPrototype.Scripts.Delta"],
                         resources=["repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/Delta.cs"])
        with self.assertRaises(ValueError):
            self.resolve(task, head)

    # ------------------------------------------------------------- boundaries
    def test_an_ambiguous_clause_is_still_refused_and_says_how_many(self):
        head = self.commit()
        task = self.task(gates=[f"{NAMESPACE}.Editor.TwinTests"])
        with self.assertRaises(ValueError) as caught:
            self.resolve(task, head)
        self.assertIn("2 committed test files", str(caught.exception))

    def test_a_method_suffix_still_resolves_to_its_class(self):
        head = self.commit()
        task = self.task(gates=[f"{NAMESPACE}.AlphaPlayModeTests.SomeTestMethod"])
        self.assertEqual([f"{TESTS}/AlphaPlayModeTests.cs"], self.resolve(task, head))

    def test_a_single_unresolvable_filter_is_still_refused(self):
        head = self.commit()
        task = self.task(gates=[f"{NAMESPACE}.GhostTests"])
        with self.assertRaises(ValueError):
            self.resolve(task, head)

    def test_no_filters_resolve_to_nothing_rather_than_raising(self):
        head = self.commit()
        self.assertEqual([], self.resolve(self.task(), head))

    def test_duplicate_clauses_resolve_once(self):
        head = self.commit({"PlayMode": f"{NAMESPACE}.AlphaPlayModeTests;"
                                        f"{NAMESPACE}.AlphaPlayModeTests"})
        self.assertEqual([f"{TESTS}/AlphaPlayModeTests.cs"], self.resolve(self.task(), head))


if __name__ == "__main__":
    unittest.main()
