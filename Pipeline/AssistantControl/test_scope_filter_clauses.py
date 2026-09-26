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

THE THIRD DEFECT WAS THAT A FILTER NAMES A TYPE AND THIS RESOLVER INDEXED FILE
STEMS. `RoomSceneCompositionFoundationTests` is a `public partial class` declared
in `RoomSceneComposerTests.cs:21` AND `RoomSceneContractTests.cs:16`; NSC-069 and
NSC-100 both name it and both refused with "matches no committed test file" -- an
absence that was a property of the query. Caught by the GER Agent, which checked
the contracts before editing one; I had published those two as contract defects
and they were not. The test tree already documents the limitation at
`RoomSceneCatalogGeometryTests.cs:12-19`, where an extra type exists so that a
filter can resolve to one file.

AND THE FOURTH WAS PROSE: `_FILTER_RE`'s character class contains `.`, so a gate
requirement written as correct English -- "...filter Foo.BarTests. It separately
runs..." -- captured the SENTENCE-ENDING PERIOD as part of the name.

THE PERIOD NEVER BROKE RESOLUTION AND I FIRST CLAIMED IT DID. Measured: the
capture becomes `Foo.BarTests.`, `split(".")` yields a trailing EMPTY segment, and
the reverse walk steps over it and finds the class anyway. What the period breaks
is the filter STRING -- so the refusal message quotes a name with a period on the
end, and a reader goes looking for a class that is not what the contract says.
NSC-088 refuses because `SpectralDecoySceneBuilderTests` has ZERO declarations
anywhere, not because of the punctuation. The failing-before proof is what caught
the overstatement: the test written for it passed on the old code.

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
        # A PARTIAL fixture: one type, two files, neither named after it. This is
        # the live shape -- RoomSceneCompositionFoundationTests across
        # RoomSceneComposerTests.cs and RoomSceneContractTests.cs.
        for name in ("SplitFirstTests", "SplitSecondTests"):
            path = self.root / TESTS / "Editor" / f"{name}.cs"
            path.write_text(
                "public partial class SplitFixtureTests\n{\n}\n", encoding="utf-8")
        # Two files declaring the SAME NON-partial type, which is the live shape
        # that must stay ambiguous: CatalogFile is a private helper in six files.
        for name in ("HelperOneTests", "HelperTwoTests"):
            path = self.root / TESTS / "Editor" / f"{name}.cs"
            path.write_text(
                "private sealed class SharedHelper\n{\n}\n", encoding="utf-8")
        # A COMMENT that mentions a class. The anchored declaration regex must not
        # read it; the live tree has four of these, one of them the very comment
        # describing this resolver.
        (self.root / TESTS / "Editor" / "CommentOnlyTests.cs").write_text(
            "// see class GhostFromAComment for why\n"
            "public sealed class CommentOnlyTests\n{\n}\n", encoding="utf-8")
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

    # ------------------------------------------------------------ type resolution
    def test_a_filter_naming_a_partial_type_resolves_to_every_file_declaring_it(self):
        """The NSC-069 and NSC-100 case. Unity runs a filter naming a partial type
        against every file contributing to it, so a plan holding one of them would
        grant write authority for half the fixture."""
        head = self.commit()
        task = self.task(gates=[f"{NAMESPACE}.Editor.SplitFixtureTests"])
        self.assertEqual(
            [f"{TESTS}/Editor/SplitFirstTests.cs", f"{TESTS}/Editor/SplitSecondTests.cs"],
            sorted(self.resolve(task, head)))

    def test_several_files_declaring_the_same_NON_partial_type_stay_ambiguous(self):
        """The discriminator, and the whole safety of the change above. Five type
        names in the live tree are declared in several files and are NOT partial --
        `CatalogFile` in six -- so returning every file for one of those would grant
        a crew write authority over six unrelated fixtures."""
        head = self.commit()
        task = self.task(gates=[f"{NAMESPACE}.Editor.SharedHelper"])
        with self.assertRaises(ValueError) as caught:
            self.resolve(task, head)
        self.assertIn("2 committed test files", str(caught.exception))

    def test_a_class_name_inside_a_comment_is_not_a_declaration(self):
        """Anchored at the start of the stripped line, so prose cannot supply a
        type. Measured on the live tree: the loose pattern finds 118 types and the
        anchored one 114, and all four it drops are comments."""
        head = self.commit()
        task = self.task(gates=[f"{NAMESPACE}.Editor.GhostFromAComment"])
        with self.assertRaises(ValueError) as caught:
            self.resolve(task, head)
        self.assertIn("no committed test file", str(caught.exception))

    def test_the_file_stem_still_wins_over_the_type_index(self):
        """Stem first, so no clause that resolves today can move to another path.
        `CommentOnlyTests` is both a file stem and a declared type here."""
        head = self.commit()
        task = self.task(gates=[f"{NAMESPACE}.Editor.CommentOnlyTests"])
        self.assertEqual([f"{TESTS}/Editor/CommentOnlyTests.cs"],
                         self.resolve(task, head))

    # --------------------------------------------------------- prose punctuation
    def test_a_gate_filter_ending_a_sentence_resolves_before_and_after(self):
        """CHARACTERISATION, not a regression guard, and labelled so on purpose.

        A trailing period leaves an EMPTY last segment, the reverse walk steps
        over it, and the class resolves either way. This test passed on the old
        code and that is what corrected my claim that the period stopped
        resolution. Keep it: it pins the behaviour the fix below must not change.
        """
        head = self.commit()
        task = {
            "id": "NSC-901", "task_contract_sha256": PIN, "exclusive_resources": [],
            "completion_gates": [{"requirement": (
                f"Unity EditMode filter {NAMESPACE}.AlphaPlayModeTests. It "
                "separately runs regression-only filters.")}],
        }
        self.assertEqual([f"{TESTS}/AlphaPlayModeTests.cs"], self.resolve(task, head))

    def test_a_gate_filter_is_captured_without_the_sentence_period(self):
        """What the period ACTUALLY breaks: the filter string, and therefore the
        refusal message. A reader sent after `...GhostTests.` goes looking for a
        class whose name the contract never wrote."""
        from Pipeline.AssistantControl.graph_controller import _test_filters
        head = self.commit()
        task = {
            "id": "NSC-901", "task_contract_sha256": PIN, "exclusive_resources": [],
            "completion_gates": [{"requirement": (
                f"Unity EditMode filter {NAMESPACE}.GhostTests. It separately "
                "runs regression-only filters.")}],
        }
        self.assertEqual([f"{NAMESPACE}.GhostTests"], _test_filters(self.root, task, head))
        with self.assertRaises(ValueError) as caught:
            self.resolve(task, head)
        message = str(caught.exception)
        self.assertIn(f"'{NAMESPACE}.GhostTests'", message)
        self.assertNotIn("GhostTests.'", message)

    def test_a_filter_that_is_only_punctuation_is_dropped_not_appended_empty(self):
        """An empty filter would resolve to nothing and refuse with an empty name,
        which is a worse message than not having a filter at all."""
        from Pipeline.AssistantControl.graph_controller import _test_filters
        head = self.commit()
        task = {
            "id": "NSC-901", "task_contract_sha256": PIN, "exclusive_resources": [],
            "completion_gates": [{"requirement": "Unity EditMode filter A."},
                                 {"requirement": f"filter {NAMESPACE}.BetaPlayModeTests"}],
        }
        self.assertEqual([f"{NAMESPACE}.BetaPlayModeTests".replace(NAMESPACE, NAMESPACE)],
                         [f for f in _test_filters(self.root, task, head)
                          if f.endswith("BetaPlayModeTests")])
        self.assertNotIn("", _test_filters(self.root, task, head))


if __name__ == "__main__":
    unittest.main()
