"""Tests for scene_path_policy, pinning the 2026-09-20 fix.

Context: `taskcontrol validate` - the main-write protocol's post-write gate, which every role is
told to run after moving main - failed on main from c90a1ec22 onward with 84 noncanonical-reference
findings and a hard ScenePathPolicyError. Nothing had gone wrong with the pipeline. Preservation
imports had landed under Docs/AI-Pipeline/Historical-Context-Sessions/reports/, while the policy
only exempted .../Historical-Context-Sessions/raw/, so imported history was scanned as live code.
Most of the 84 were copies of Pipeline/ExecutionCrew/outputs/ files, already exempt at their
original path: identical bytes, judged differently by folder alone.

There were no tests for this module. These build a real temporary git repository, so they are
portable: no host paths, no canonical checkout, no Unity.

Run:  python -B scene_path_policy_test.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scene_path_policy import (  # noqa: E402
    CANONICAL_SCENE_ROOT,
    inspect_scene_path_policy,
)

# Assembled from fragments on purpose. These are noncanonical scene paths, and this
# file lives under Pipeline/ - a live root - so spelling either of them out would make
# the suite fail the very check it exists to verify. The alternative, allowlisting the
# test's invented paths in the policy module, puts those literals in THAT file and needs
# its own allowlist entry. Build them instead.
LIVE_SCENE = "Assets/" + "NoSafeCircle/DoorPrototype/Scenes/" + "DoorPrototype.unity"
STRAY_SCENE = "Assets/" + "Somewhere/Else/" + "stray.unity"
HISTORY = "Docs/AI-Pipeline/Historical-Context-Sessions"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


class PolicyRepo(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="scenepolicy-"))
        self.addCleanup(self._clean)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "test@nosafecircle.invalid")
        git(self.repo, "config", "user.name", "Scene Policy Test")

    def _clean(self):
        import shutil
        shutil.rmtree(self.repo, ignore_errors=True)

    def write(self, rel: str, content: str | bytes) -> None:
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")

    def commit(self) -> None:
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")

    def findings(self) -> list[str]:
        return inspect_scene_path_policy(self.repo)["findings"]


class TheGuardStillWorks(PolicyRepo):
    """Whatever we exempt, the live checks must keep firing. Otherwise the fix is a hole."""

    def test_a_live_file_referencing_a_noncanonical_scene_is_a_finding(self):
        self.write("Pipeline/TaskGraph/some_live_thing.json",
                   json.dumps({"scene": LIVE_SCENE}))
        self.commit()
        found = self.findings()
        self.assertTrue(any("noncanonical live scene reference" in f for f in found),
                        f"expected a finding, got {found}")

    def test_a_tracked_unity_scene_outside_the_canonical_root_is_a_finding(self):
        self.write(STRAY_SCENE, "%YAML 1.1\n")
        self.commit()
        found = self.findings()
        self.assertTrue(any("outside " + CANONICAL_SCENE_ROOT in f for f in found),
                        f"expected a finding, got {found}")

    def test_a_scene_in_the_canonical_root_is_fine(self):
        self.write(CANONICAL_SCENE_ROOT + "Main.unity", "%YAML 1.1\n")
        self.commit()
        self.assertEqual(self.findings(), [])


class TheMutableFileInsideHistoryIsStillLive(PolicyRepo):
    """Main-Commit-Review 20260920-180652, finding 3, reproduced before fixing.

    d0bcba055 exempted this whole tree as immutable. The tree's own README says
    CURRENT_CONTEXT.md is deliberately mutable and is the first file a continuing
    agent reads, so a stale scene path there misdirects live work rather than
    recording history. The exemption belongs to archival material only.
    """

    def test_a_noncanonical_reference_in_current_context_IS_a_finding(self):
        self.write(f"{HISTORY}/CURRENT_CONTEXT.md",
                   f"Continue the door work in {STRAY_SCENE}." + chr(10))
        self.commit()
        self.assertEqual(len(self.findings()), 1, self.findings())

    def test_its_archived_neighbours_are_still_exempt(self):
        """The carve-out must not undo the fix it sits inside."""
        self.write(f"{HISTORY}/reports/some-import/notes.md",
                   f"Historically this lived at {STRAY_SCENE}." + chr(10))
        self.write(f"{HISTORY}/raw/transcript.md",
                   f"...and also {STRAY_SCENE}." + chr(10))
        self.commit()
        self.assertEqual(self.findings(), [])

    def test_identical_bytes_judged_by_file_not_by_tree(self):
        body = f"see {STRAY_SCENE}" + chr(10)
        self.write(f"{HISTORY}/CURRENT_CONTEXT.md", body)
        self.write(f"{HISTORY}/reports/archived-copy.md", body)
        self.commit()
        found = self.findings()
        self.assertEqual(len(found), 1, found)
        self.assertIn("CURRENT_CONTEXT.md", json.dumps(found))

    def test_the_carve_out_is_reported_not_only_applied(self):
        """A silent carve-out is how the original wrong premise survived review."""
        self.write("Docs/an-ordinary-live-note.md", "no scene reference here")
        self.commit()
        report = inspect_scene_path_policy(self.repo)
        self.assertIn(f"{HISTORY}/CURRENT_CONTEXT.md",
                      report["still_checked_inside_excluded"])


class ImportedHistoryIsNotLive(PolicyRepo):
    """The actual regression: the three shapes that broke main."""

    def test_a_noncanonical_reference_inside_imported_history_is_NOT_a_finding(self):
        """84 of these, mostly copies of ExecutionCrew outputs."""
        self.write(f"{HISTORY}/reports/untracked-project-outputs-20260920/"
                   "Pipeline/ExecutionCrew/outputs/run/request.json",
                   json.dumps({"scene": LIVE_SCENE}))
        self.commit()
        self.assertEqual(self.findings(), [])

    def test_a_tracked_unity_file_inside_imported_history_is_NOT_a_finding(self):
        """The one the prefix widening alone would have missed: the tracked-scene check does
        not go through _is_live_text_path, so it needed its own exemption."""
        self.write(f"{HISTORY}/reports/host-reports-20260920/originals/delivery/"
                   "NSC-069/scene-build2.unity", "%YAML 1.1\n")
        self.commit()
        found = self.findings()
        self.assertEqual(found, [], f"imported delivery evidence flagged as a live scene: {found}")

    def test_an_undecodable_text_file_inside_imported_history_is_NOT_a_finding(self):
        """A PixelLab measurement summary with a 0xd7 byte produced 'could not inspect'."""
        self.write(f"{HISTORY}/reports/art-reports-20260920/originals/measurement_summary.txt",
                   b"width \xd7 height\n")
        self.commit()
        self.assertEqual(self.findings(), [])

    def test_the_original_raw_subtree_is_still_exempt(self):
        """The prefix was widened, not moved; don't regress what already worked."""
        self.write(f"{HISTORY}/raw/old/request.json", json.dumps({"scene": LIVE_SCENE}))
        self.commit()
        self.assertEqual(self.findings(), [])

    def test_history_and_live_can_hold_the_SAME_bytes_and_be_judged_differently(self):
        """The whole point: identical content, exempt in one place, a finding in the other."""
        payload = json.dumps({"scene": LIVE_SCENE})
        self.write(f"{HISTORY}/reports/copy/request.json", payload)
        self.write("Pipeline/TaskGraph/live_copy.json", payload)
        self.commit()
        found = self.findings()
        self.assertEqual(len(found), 1, f"expected exactly the live one to fire, got {found}")
        self.assertIn("live_copy.json", found[0])


class ExemptionIsNotOpenEnded(PolicyRepo):
    def test_docs_outside_the_history_tree_are_still_live(self):
        """Docs/ is a live root. Only the imported-history subtree is exempt."""
        self.write("Docs/GDD/some_other_doc.md", f"see {LIVE_SCENE}\n")
        self.commit()
        found = self.findings()
        self.assertTrue(any("noncanonical live scene reference" in f for f in found),
                        f"exemption leaked to the rest of Docs/: {found}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
