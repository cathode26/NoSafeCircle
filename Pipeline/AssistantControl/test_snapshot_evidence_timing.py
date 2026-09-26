"""The paired evidence-timing test: identical later evidence, opposite answers.

THIS IS THE ACCEPTANCE CRITERION FOR SNAPSHOT VALIDITY, and Astra named it as
the clearest one: *"identical later evidence must admit the checkout that already
contains the accepted dependency and reject the checkout that does not."*

WHY THE PAIR AND NOT THE REJECTION ALONE. Today's `reserve` refuses BOTH of these
records, because an ordinary record must sit on exactly current Source HEAD. So a
test that asserted only *"the baseline without the dependency is refused"* would
PASS on today's code and prove nothing whatever -- it would be satisfied by a rule
that refuses everything. **The ADMIT half is what makes the pair a test of the
right property**, and the REJECT half asserts the REASON, because "it was
refused" is the assertion that passes on an earlier, unrelated refusal.

The two cases differ in exactly one input: which commit is the execution
baseline. Same repository, same dependency, same delivery record, same Source
head. `test_the_pair_differs_only_in_the_baseline` holds that.

Astra's later fixtures are here too, and the revert case is the one that decides
whether the content proof is real: *"Validated dependency commit is an ancestor of
B, but B reverts a required script or prefab -> Refuse. This defeats ancestry-only
admission."* It asserts BOTH that ancestry holds and that the assessment refuses,
because a refusal without the ancestry assertion cannot distinguish the content
proof from an ancestry proof that happened to fail.

Everything is built in a disposable repository with the production conformance
evaluator selecting the record; nothing here hand-shapes a dependency result, so
the record id the assessment reads is the one the evaluator chose.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.dependencies import inspect_dependencies
from Pipeline.AssistantControl.snapshot import (
    CONTENT_PROOF_DECLARED_SURFACES,
    CONTENT_PROOF_NONE,
    _surface_applicability,
    assess_execution_snapshot,
)

_TASKGRAPH = str(Path(__file__).resolve().parents[1] / "TaskGraph")
if _TASKGRAPH not in sys.path:
    sys.path.insert(0, _TASKGRAPH)
from conformance_records import (  # noqa: E402
    CANON_PATH,
    GitRepository,
    canonical_text_sha256,
    semantic_json_sha256,
)

DEPENDENCY = "NSC-041"
DEPENDENT = "NSC-042"
SURFACE = "src/dependency.txt"
ARTIFACT = f"Pipeline/TaskGraph/evidence/{DEPENDENCY}/artifacts/gate.txt"
# conformance_records.py:536 requires "DEL-<task>-" for a delivery record.
# The fixture control is what found this; a hand-picked id is refused as
# record_structure_invalid and every case below would have gone vacuous.
RECORD_ID = f"DEL-{DEPENDENCY}-001"


def contract(task_id: str, *, depends_on: tuple[str, ...] = ()) -> dict:
    return {
        "schema_version": "2.0", "id": task_id, "contract_revision": 1,
        "contract_disposition": "active", "title": f"Synthetic {task_id}",
        "reconciliation_key": task_id.lower(), "kind": "implementation",
        "execution_scope": "single_agent", "decomposition_state": "concrete",
        "depends_on": list(depends_on),
        "exclusive_resources": [f"repo-file:{SURFACE}"],
        "completion_gates": [
            {"gate_id": "VAL-001", "reference": "test", "requirement": "passes"}],
    }


class EvidenceTimingSnapshot(unittest.TestCase):
    """base -> I (implementation) -> R (revert) -> E (evidence) = S.

    Four commits is the smallest history that can hold all of Astra's cases: a
    baseline before the implementation, one containing it, one that contains it
    and then destroys it, and evidence arriving after all three.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        self.sh("git", "init", "-b", "main")
        self.sh("git", "config", "user.email", "snapshot@example.invalid")
        self.sh("git", "config", "user.name", "Snapshot Test")

        self.write(CANON_PATH, "# Canon\nRules.\n")
        self.write_json(f"Tasks/{DEPENDENCY}.yaml", contract(DEPENDENCY))
        self.write_json(f"Tasks/{DEPENDENT}.yaml",
                        contract(DEPENDENT, depends_on=(DEPENDENCY,)))
        self.write(ARTIFACT, "gate passed\n")
        self.base = self.commit("tasks and canon, no implementation yet")

        self.write(SURFACE, "the accepted implementation\n")
        self.implemented = self.commit("dependency implementation integrated")
        self.implemented_tree = self.sh("git", "rev-parse", "HEAD^{tree}")

        self.write(SURFACE, "someone rewrote this after the fact\n")
        self.reverted = self.commit("a later commit destroys the accepted surface")

        # The evidence is published by each test, not by setUp. A delivery record
        # is IMMUTABLE once committed -- rewriting one earns
        # `record_structure_invalid: Immutable record ... was modified`, which is
        # a different guard from the one a test may mean to exercise, and it
        # silently substituted itself for the empty-surface case until the
        # finding MESSAGE was read rather than its code.
        self.evidence = None
        self.head = self.reverted

    def publish_evidence(self, surfaces: list | None = None) -> str:
        """Commit the dependency's delivery record, ONCE, and move Source head."""
        assert self.evidence is None, "a delivery record is immutable; publish once"
        self.record_value = self.delivery_record(RECORD_ID, surfaces=surfaces)
        self.evidence = self.add_record(self.record_value)
        self.head = self.evidence
        return self.evidence

    # ------------------------------------------------------------------ helpers
    def sh(self, *args: str) -> str:
        # NOT `run`: that is unittest.TestCase.run, and shadowing it makes the
        # runner call this with a TestResult as argv.
        result = subprocess.run(args, cwd=self.source, capture_output=True, check=False)
        if result.returncode:
            raise AssertionError("%s failed: %s"
                                 % (" ".join(args), result.stderr.decode("utf-8", "replace")))
        return result.stdout.decode("utf-8", "replace").strip()

    def write(self, path: str, content: str) -> None:
        target = self.source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def write_json(self, path: str, value: dict) -> None:
        self.write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")

    def commit(self, message: str) -> str:
        self.sh("git", "add", "-A")
        self.sh("git", "commit", "-m", message)
        return self.sh("git", "rev-parse", "HEAD")

    def delivery_record(self, record_id: str, *, surfaces: list | None = None) -> dict:
        """A record whose validated state is the IMPLEMENTATION commit.

        Built with the same field shapes the conformance evaluator's own smoke
        fixture uses, and the hashes are computed from the repository rather than
        written by hand, so an evaluator change breaks this loudly.
        """
        repo = GitRepository(self.source)
        raw = repo.read(self.implemented, f"Tasks/{DEPENDENCY}.yaml")
        value = json.loads(raw.decode())
        declared = surfaces if surfaces is not None else [
            {"path": SURFACE, "blob_sha": repo.blob(self.implemented, SURFACE),
             "role": "implementation"}]
        return {
            "schema_version": "1.0", "record_type": "delivery", "record_id": record_id,
            "task_id": DEPENDENCY,
            "task_contract": {"path": f"Tasks/{DEPENDENCY}.yaml",
                              "revision": value["contract_revision"],
                              "sha256": semantic_json_sha256(raw)},
            "canon": {"path": CANON_PATH,
                      "sha256": canonical_text_sha256(repo.read(self.implemented, CANON_PATH))},
            "validated_state": {"commit": self.implemented, "tree": self.implemented_tree},
            "conformance_surfaces": declared,
            "gate_results": [{"gate_id": "VAL-001", "result": "pass",
                              "evidence": [{"path": ARTIFACT,
                                            "blob_sha": repo.blob(self.implemented, ARTIFACT)}],
                              "notes": "synthetic"}],
            "human_approval": {"required": False, "decision": "not_required",
                               "approved_by": "", "notes": "synthetic"},
            "recorded_at": "2026-09-26T00:00:00Z",
            "delivery": {"base_commit": self.implemented,
                         "candidate_commit": self.implemented,
                         "integrated_commit": self.implemented,
                         "integrated_tree": self.implemented_tree},
        }

    @staticmethod
    def record_path(task_id: str = DEPENDENCY, record_id: str = RECORD_ID) -> str:
        return "Pipeline/TaskGraph/evidence/%s/records/%s.json" % (task_id, record_id)

    def add_record(self, value: dict) -> str:
        self.write_json(self.record_path(value["task_id"], value["record_id"]), value)
        return self.commit("commit the dependency's delivery evidence")

    def dependency_at_source(self) -> dict:
        """The REAL inspection, so the selected record id is the evaluator's."""
        return inspect_dependencies(self.source, DEPENDENT)

    def assess(self, baseline: str) -> dict:
        return assess_execution_snapshot(
            self.source, baseline, self.head, self.dependency_at_source())

    # ------------------------------------------------------------------ control
    def test_the_fixture_really_makes_the_dependency_accepted_at_source(self):
        """Without this, every case below could pass on an unaccepted dependency.

        `_ACCEPTED_DEPENDENCY_STATES` skips the content proof for a dependency
        Source has not accepted, so an evaluator that called this record anything
        other than conformant would make the whole file vacuous -- the shape
        `CLAUDE.md` calls a missing test read as a passing one.
        """
        self.publish_evidence()
        dependency = self.dependency_at_source()
        states = {item["task_id"]: item["state"] for item in dependency["dependencies"]}
        self.assertEqual(states, {DEPENDENCY: "conformant"}, dependency)
        selected = dependency["dependencies"][0]["selected_record_id"]
        self.assertEqual(selected, RECORD_ID, dependency)

    def test_the_pair_differs_only_in_the_baseline(self):
        """The two halves must be the same question asked of two commits."""
        self.publish_evidence()
        dependency = self.dependency_at_source()
        admitted = assess_execution_snapshot(
            self.source, self.implemented, self.head, dependency)
        refused = assess_execution_snapshot(
            self.source, self.base, self.head, dependency)
        self.assertEqual(admitted["source_head"], refused["source_head"])
        self.assertEqual(
            [item["selected_record_id"] for item in admitted["dependencies"]],
            [item["selected_record_id"] for item in refused["dependencies"]])
        self.assertNotEqual(admitted["baseline"], refused["baseline"])
        self.assertNotEqual(admitted["snapshot_content_verified"],
                            refused["snapshot_content_verified"])

    # ------------------------------------------------- the paired criterion
    def test_identical_later_evidence_admits_the_baseline_that_contains_it(self):
        """THE POSITIVE CONTROL. Requiring the evidence FILE in B fails this.

        The baseline is the implementation commit; the delivery record does not
        exist there at all -- it is two commits later. Astra: *"Requiring the
        evidence file in B fails this positive control."*
        """
        self.publish_evidence()
        result = self.assess(self.implemented)
        self.assertTrue(result["snapshot_content_verified"], result)
        self.assertEqual(result["refusals"], [], result)
        self.assertTrue(result["baseline_is_source_ancestor"])
        self.assertFalse(result["baseline_equals_source_head"],
                         "the whole point is that B is NOT S")
        entry = result["dependencies"][0]
        self.assertIs(entry["applicable"], True, entry)
        self.assertEqual(entry["content_proof"], CONTENT_PROOF_DECLARED_SURFACES)
        self.assertEqual(entry["surfaces_matching"], 1, entry)
        # And the record really is absent from the baseline, so this is the
        # evidence-arrives-later shape rather than a coincidence.
        self.assertEqual(
            self.sh("git", "cat-file", "-t", "%s:%s" % (self.head, self.record_path())),
            "blob")
        missing = subprocess.run(
            ["git", "-C", str(self.source), "cat-file", "-e",
             "%s:%s" % (self.implemented, self.record_path())], capture_output=True)
        self.assertNotEqual(missing.returncode, 0,
                            "the evidence must NOT exist at the admitted baseline")

    def test_identical_later_evidence_rejects_the_baseline_that_does_not(self):
        """THE NEGATIVE HALF, AND IT NAMES ITS REFUSAL.

        Source reports the dependency `conformant`; the implementation is simply
        not in this tree. Astra: *"Source's delivery record cannot make I appear
        in B."* Asserting only that it was refused would pass on today's
        equality rule, which refuses every ordinary record.
        """
        self.publish_evidence()
        result = self.assess(self.base)
        self.assertFalse(result["snapshot_content_verified"], result)
        self.assertIn("dependency_%s_accepted_dependency_surface_absent_at_baseline"
                      % DEPENDENCY, result["refusals"], result)
        self.assertNotIn("baseline_is_not_a_source_ancestor", result["refusals"],
                         "the baseline IS an ancestor; the refusal must be the content")
        entry = result["dependencies"][0]
        self.assertIs(entry["applicable"], False, entry)
        self.assertEqual(entry["absent_at_baseline"], [SURFACE], entry)
        self.assertEqual(entry["changed_at_baseline"], [], entry)
        self.assertEqual(entry["state"], "conformant",
                         "Source accepted it; only its applicability to B failed")

    # ------------------------------------------- ancestry is not the proof
    def test_a_baseline_that_destroys_an_accepted_surface_is_refused(self):
        """THE CASE THAT DEFEATS ANCESTRY-ONLY ADMISSION.

        The validated commit IS an ancestor of this baseline and the accepted
        content is gone anyway. Both halves are asserted: an ancestry-only rule
        would admit this, and a refusal that did not also assert the ancestry
        could not tell the two rules apart.
        """
        self.publish_evidence()
        result = self.assess(self.reverted)
        entry = result["dependencies"][0]
        self.assertIs(entry["validated_commit_is_baseline_ancestor"], True,
                      "ancestry must HOLD, or this case tests nothing")
        self.assertEqual(entry["validated_commit"], self.implemented)
        self.assertIs(entry["applicable"], False, entry)
        self.assertEqual(entry["changed_at_baseline"], [SURFACE], entry)
        self.assertEqual(entry["absent_at_baseline"], [], entry)
        self.assertFalse(result["snapshot_content_verified"], result)
        self.assertIn("dependency_%s_accepted_dependency_surface_differs_at_baseline"
                      % DEPENDENCY, result["refusals"], result)

    # ------------------------------------------- coverage is not completeness
    def test_a_dependency_declaring_no_surfaces_reports_insufficient_coverage(self):
        """An empty surface list is shape-valid and proves nothing.

        Astra: `conformance_records.py` *"does not establish that this list
        completely covers the dependency's runtime requirements. It even permits
        an empty list."* A content proof that made no comparison must not read as
        a pass, so it is reported as no proof at all.
        """
        self.publish_evidence(surfaces=[])
        dependency = self.dependency_at_source()
        entry_state = dependency["dependencies"][0]["state"]
        result = self.assess(self.implemented)
        entry = result["dependencies"][0]
        if entry_state != "conformant":
            # The evaluator refused it upstream, which is a BETTER outcome than
            # this module reporting it -- record which guard fired rather than
            # claiming this module caught it.
            self.assertIs(entry["applicable"], None, entry)
            self.assertEqual(entry["reason"], "dependency_not_accepted_at_source")
            return
        self.assertIs(entry["applicable"], False, entry)
        self.assertEqual(entry["content_proof"], CONTENT_PROOF_NONE, entry)
        self.assertEqual(entry["reason"],
                         "dependency_declares_no_conformance_surfaces", entry)
        self.assertFalse(result["snapshot_content_verified"], result)

    # ------------------------------------------- an unrelated advance is not news
    def test_unrelated_source_advances_do_not_change_the_assessment(self):
        """Astra: *"Advance Source repeatedly with unrelated commits -> the same B
        and plan remain admissible across completed assessments, without
        refresh."* This is the property the equality rule cannot express."""
        self.publish_evidence()
        first = self.assess(self.implemented)
        for index in range(3):
            self.write("docs/unrelated-%d.md" % index, "nothing to do with the task\n")
            self.head = self.commit("unrelated advance %d" % index)
        later = self.assess(self.implemented)
        self.assertTrue(later["snapshot_content_verified"], later)
        self.assertEqual(first["refusals"], later["refusals"])
        self.assertNotEqual(first["source_head"], later["source_head"],
                            "Source must actually have moved")

    # ------------------------------- silence is not establishment
    def test_an_unassessed_dependency_does_not_read_as_verified(self):
        """THE DEFECT MY OWN MUTATION HARNESS FOUND UNPINNED.

        A dependency Source has not accepted gets NO content proof here on
        purpose -- `_dependency_is_satisfied` already refuses it, and reporting it
        twice would name one cause as two problems. But an earlier version then
        returned `snapshot_content_verified: True` with an empty `refusals`,
        because nothing this module refused had gone wrong. **The content question
        was never asked and the answer read as yes.**

        `refusals` says what this module REFUSES; the flag says what it
        ESTABLISHED. This test is the difference between them, and the weakening
        that removes it (`all(applicable is True)`) broke no other test.

        No evidence is published, so the dependency is `not_delivered`.
        """
        self.assertIsNone(self.evidence, "this case runs BEFORE the evidence exists")
        dependency = self.dependency_at_source()
        entry = dependency["dependencies"][0]
        self.assertNotEqual(entry["state"], "conformant", entry)
        result = assess_execution_snapshot(
            self.source, self.implemented, self.head, dependency)
        self.assertEqual(result["refusals"], [],
                         "this module refuses nothing here -- that is the point")
        self.assertFalse(result["snapshot_content_verified"],
                         "an unasked question must not answer yes")
        self.assertEqual(result["dependencies_unassessed"], 1, result)
        self.assertEqual(result["dependencies_applicable"], 0, result)

    def test_a_dependency_source_has_not_accepted_gets_no_content_proof(self):
        """And the per-dependency entry says which question was skipped, and why.

        The weakening that hands an unaccepted dependency a content proof anyway
        broke no other test either: without this, `snapshot.py` could start
        comparing surfaces from a record the evaluator rejected and nothing would
        notice.
        """
        self.assertIsNone(self.evidence)
        dependency = self.dependency_at_source()
        result = assess_execution_snapshot(
            self.source, self.implemented, self.head, dependency)
        entry = result["dependencies"][0]
        self.assertIsNone(entry["applicable"], entry)
        self.assertEqual(entry["content_proof"], CONTENT_PROOF_NONE, entry)
        self.assertEqual(entry["reason"], "dependency_not_accepted_at_source", entry)
        # No comparison was attempted, so none of the surface fields exist.
        for field in ("surfaces_declared", "surfaces_matching", "absent_at_baseline",
                      "changed_at_baseline", "validated_commit"):
            self.assertNotIn(field, entry,
                             "%s means a surface comparison ran on an unaccepted "
                             "dependency" % field)

    # ------------------------------- the repository stores forward slashes
    def test_a_windows_style_surface_path_still_matches_at_the_baseline(self):
        """A backslash in a declared surface must not read as an absent file.

        Git stores forward slashes; a record written by a Windows tool can carry
        backslashes, and `rev-parse <commit>:src\\dependency.txt` finds nothing.
        Without the normalisation this would report the accepted implementation
        ABSENT from a baseline that contains it -- a false refusal, which is the
        expensive direction. Called at unit level because a record declaring a
        backslash path may not survive the evaluator's own path validation, and
        the property under test is this module's, not the evaluator's.
        """
        repo = GitRepository(self.source)
        blob = repo.blob(self.implemented, SURFACE)
        windows = SURFACE.replace("/", "\\")
        self.assertIn("\\", windows, "the fixture must actually use a backslash")
        proof = _surface_applicability(
            self.source, self.implemented,
            [{"path": windows, "blob_sha": blob, "role": "implementation"}])
        self.assertIs(proof["applicable"], True, proof)
        self.assertEqual(proof["surfaces_matching"], 1, proof)
        self.assertEqual(proof["absent_at_baseline"], [], proof)
        # The control: the same declaration against a baseline WITHOUT the file
        # must still be recognised as the same path and reported absent, by its
        # normalised name rather than its backslash form.
        missing = _surface_applicability(
            self.source, self.base,
            [{"path": windows, "blob_sha": blob, "role": "implementation"}])
        self.assertIs(missing["applicable"], False, missing)
        self.assertEqual(missing["absent_at_baseline"], [SURFACE], missing)

    def test_a_divergent_baseline_is_reported_as_not_a_source_ancestor(self):
        """The boundary that keeps this from becoming "staleness no longer matters".

        A baseline off the main line is not a snapshot OF Source at all. It is
        reported as such and not silently folded into the content result.
        """
        self.publish_evidence()
        self.sh("git", "checkout", "-q", "-b", "sidebranch", self.implemented)
        self.write("docs/divergent.md", "off the main line\n")
        divergent = self.commit("a commit Source does not contain")
        self.sh("git", "checkout", "-q", "main")
        result = assess_execution_snapshot(
            self.source, divergent, self.head, self.dependency_at_source())
        self.assertFalse(result["baseline_is_source_ancestor"], result)
        self.assertIn("baseline_is_not_a_source_ancestor", result["refusals"])
        self.assertFalse(result["snapshot_content_verified"], result)


if __name__ == "__main__":
    unittest.main()
