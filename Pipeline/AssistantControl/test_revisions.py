"""Focused real-Git revision tests in disposable repositories."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from Pipeline.AssistantControl.admission import reserve
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.revisions import RevisionError, begin_revision
from Pipeline.AssistantControl.scope import AssistantScopePlanner
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        self.git("init")
        name, email = validated_agent_git_identity()
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)
        (self.source / "Tasks").mkdir()
        (self.source / "Assets/Feature/Tests").mkdir(parents=True)
        (self.source / "Assets/Feature/Feature.cs").write_text("class Feature {}\n")
        (self.source / "Assets/Feature/Tests/FeatureTests.cs").write_text("class FeatureTests {}\n")
        (self.source / "Tasks/NSC-042.yaml").write_text(json.dumps({
            "id": "NSC-042", "title": "revision", "contract_disposition": "active",
            "kind": "implementation", "execution_scope": "single_agent",
            "decomposition_state": "concrete", "depends_on": [],
            "exclusive_resources": ["repo-file:Assets/Feature"],
        }))
        self.git("add", ".")
        self.git("commit", "-m", "base")
        self.checkouts = Checkouts(self.source, Path(self.temp.name) / "checkouts")
        self.checkouts.prepare("NSC-042")
        AssistantScopePlanner(self.checkouts).plan(
            "NSC-042", ExecutionScopePlan(
                ("Assets/Feature/Feature.cs",), (),
                ("Assets/Feature/Tests/FeatureTests.cs",), (),
            ), lease_id="lease-old")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.source), *args],
                              capture_output=True, check=True).stdout

    def checkout_git(self, *args):
        return subprocess.run(["git", "-C", str(self.checkouts.root / "NSC-042"), *args],
                              capture_output=True, check=True).stdout

    def dependencies(self, source, task_id, _root):
        return {"task_id": task_id,
                "source_commit": self.git("rev-parse", "HEAD").decode().strip(),
                "source_unchanged_during_read": True,
                "dependencies_satisfied": True,
                "fixture_dependency_reader": True}

    def make_rejected_candidate(self, *, paired_worker=False):
        checkout = self.checkouts.root / "NSC-042"
        (checkout / "Assets/Feature/revision.cs").write_text("class Revision {}\n")
        self.checkout_git("add", ".")
        self.checkout_git("commit", "-m", "candidate")
        candidate = self.checkout_git("rev-parse", "HEAD").decode().strip()
        record_path = self.checkouts.records / "NSC-042.json"
        record = json.loads(record_path.read_text())
        record["candidate"] = {
            "commit": candidate,
            "tree": self.checkout_git("rev-parse", "HEAD^{tree}").decode().strip(),
        }
        record["human_review"] = {"commit": candidate, "decision": "reject",
                                  "message": "revise"}
        record["status"] = "changes_requested"
        if paired_worker:
            record["worker"] = {"run_id": "old", "status": "failed", "capacity_released": True}
            record["launch"] = {"run_id": "old", "status": "failed"}
        write_record(record_path, record)
        return candidate

    def test_reject_revision_replans_and_admits_without_losing_candidate_files(self):
        candidate = self.make_rejected_candidate()
        revised = begin_revision(self.checkouts, "NSC-042", candidate)
        self.assertEqual("prepared", revised["status"])
        self.assertEqual(candidate, revised["source_commit"])
        self.assertIsNone(revised.get("approval"))
        candidate_file = self.checkouts.root / "NSC-042" / "Assets/Feature/revision.cs"
        self.assertTrue(candidate_file.exists())
        self.assertEqual("class Revision {}\n", candidate_file.read_text())
        self.assertEqual(candidate, revised["revision"]["candidate_commit"])
        self.assertEqual(1, len(revised["revision_history"]))

        AssistantScopePlanner(self.checkouts).plan(
            "NSC-042", ExecutionScopePlan(
                ("Assets/Feature/Feature.cs",), (),
                ("Assets/Feature/Tests/FeatureTests.cs",), (),
            ), lease_id="lease-new")
        admission = reserve(self.checkouts, "NSC-042", "run-new",
                            dependency_reader=self.dependencies)
        self.assertEqual(candidate, admission["source_head"])
        self.assertEqual(self.git("rev-parse", "HEAD").decode().strip(),
                         admission["dependency_inspection"]["source_commit"])
        current = json.loads((self.checkouts.records / "NSC-042.json").read_text())
        self.assertIsNone(current.get("approval"))
        self.assertEqual("reject", current["revision_history"][0]["human_review"]["decision"])

    def test_paired_worker_and_launch_use_effective_worker_release(self):
        candidate = self.make_rejected_candidate(paired_worker=True)
        revised = begin_revision(self.checkouts, "NSC-042", candidate)
        self.assertNotIn("worker", revised)
        self.assertNotIn("launch", revised)

    def test_ignored_unity_cache_is_preserved_but_other_ignored_files_block(self):
        checkout = self.checkouts.root / "NSC-042"
        with (checkout / ".git/info/exclude").open("a") as rules:
            rules.write("\nLibrary/\nprivate.txt\n")
        cache = checkout / "Library/cache.bin"
        cache.parent.mkdir()
        cache.write_bytes(b"Unity cache fixture")
        hidden = checkout / "private.txt"
        hidden.write_text("Unrelated ignored content")
        with self.assertRaisesRegex(ValueError, "local changes"):
            reserve(self.checkouts, "NSC-042", "cache-test", dependency_reader=self.dependencies)
        hidden.unlink()
        self.assertTrue(reserve(self.checkouts, "NSC-042", "cache-test", dependency_reader=self.dependencies)["admitted"])
        self.assertEqual(b"Unity cache fixture", cache.read_bytes())

    def test_active_worker_or_moved_source_refuses_revision(self):
        candidate = self.make_rejected_candidate(paired_worker=False)
        record_path = self.checkouts.records / "NSC-042.json"
        record = json.loads(record_path.read_text())
        record["worker"] = {"run_id": "old", "status": "failed", "capacity_released": False}
        write_record(record_path, record)
        with self.assertRaisesRegex(RevisionError, "release capacity"):
            begin_revision(self.checkouts, "NSC-042", candidate)

    def test_source_advance_refuses_revision_and_preserves_record_bytes(self):
        candidate = self.make_rejected_candidate()
        record_path = self.checkouts.records / "NSC-042.json"
        before = record_path.read_bytes()
        (self.source / "source-advance.txt").write_text("advance\n")
        self.git("add", "source-advance.txt")
        self.git("commit", "-m", "advance source")
        # Names the refusal it actually gets. The bare substring "ancestor"
        # passed here for a message about a DIFFERENT cause: an advanced Source
        # is absent from the task checkout, so the ancestry check never ran.
        # The two branches now have a test each, above.
        with self.assertRaisesRegex(RevisionError, "not present in the task checkout"):
            begin_revision(self.checkouts, "NSC-042", candidate)
        self.assertEqual(before, record_path.read_bytes())

    def test_an_unresolvable_source_commit_says_so_rather_than_claiming_non_ancestry(self):
        """The live NSC-046 shape: Source HEAD is absent from the task checkout.

        The checkout is created by `prepare` and never fetches later Source
        commits, so `merge-base` exits 128 "Not a valid commit name" rather
        than 1. Reporting that as non-ancestry states a fact nobody measured.
        """
        candidate = self.make_rejected_candidate()
        (self.source / "source-advance.txt").write_text("advance\n")
        self.git("add", "source-advance.txt")
        self.git("commit", "-m", "advance source")
        head = self.git("rev-parse", "HEAD").decode().strip()
        checkout = self.checkouts.root / "NSC-042"
        with self.assertRaises(RuntimeError):
            # Establishes the precondition rather than assuming it: the commit
            # really is absent from the checkout this check runs in.
            git(checkout, "cat-file", "-e", head + "^{commit}")
        with self.assertRaisesRegex(RevisionError, "not present in the task checkout"):
            begin_revision(self.checkouts, "NSC-042", candidate)

    def test_a_resolvable_commit_that_is_genuinely_not_an_ancestor_still_says_so(self):
        """The control, and the one that keeps the fix honest.

        Here the Source commit IS in the checkout, so the ancestry question is
        actually asked and actually answered no. A fix that relabelled every
        refusal as "not present" would pass the test above and fail this one.
        """
        candidate = self.make_rejected_candidate()
        (self.source / "source-advance.txt").write_text("advance\n")
        self.git("add", "source-advance.txt")
        self.git("commit", "-m", "advance source")
        head = self.git("rev-parse", "HEAD").decode().strip()
        checkout = self.checkouts.root / "NSC-042"
        git(checkout, "fetch", "--no-tags", str(self.source), head)
        git(checkout, "cat-file", "-e", head + "^{commit}")  # precondition, proven
        with self.assertRaisesRegex(RevisionError, "is not an ancestor"):
            begin_revision(self.checkouts, "NSC-042", candidate)

    def test_revision_second_candidate_approval_and_integration(self):
        old_candidate = self.make_rejected_candidate()
        begin_revision(self.checkouts, "NSC-042", old_candidate)
        record_path = self.checkouts.records / "NSC-042.json"
        self.assertIsNone(json.loads(record_path.read_text()).get("approval"))
        branch = self.git("branch", "--show-current").decode().strip()
        source_head = self.git("rev-parse", "HEAD").decode().strip()
        with self.assertRaisesRegex(ValueError, "approve"):
            ReviewGate(self.checkouts).integrate(
                "NSC-042", expected_source_commit=source_head, target_branch=branch)

        AssistantScopePlanner(self.checkouts).plan(
            "NSC-042", ExecutionScopePlan(
                ("Assets/Feature/Feature.cs",), (),
                ("Assets/Feature/Tests/FeatureTests.cs",), (),
            ), lease_id="lease-new")
        checkout = self.checkouts.root / "NSC-042"
        (checkout / "Assets/Feature/retested.cs").write_text("class Retested {}\n")
        self.checkout_git("add", ".")
        self.checkout_git("commit", "-m", "retested candidate")
        new_candidate = self.checkout_git("rev-parse", "HEAD").decode().strip()
        record = json.loads(record_path.read_text())
        record["candidate"] = {
            "commit": new_candidate,
            "tree": self.checkout_git("rev-parse", "HEAD^{tree}").decode().strip(),
            "fixture_candidate_metadata": True,
        }
        record.pop("human_review", None)
        record["status"] = "planned"
        write_record(record_path, record)
        with self.assertRaisesRegex(ValueError, "not the registered"):
            ReviewGate(self.checkouts).decide(
                "NSC-042", tested_commit=old_candidate, decision="approve", message="test-only stale approval")
        ReviewGate(self.checkouts).decide(
            "NSC-042", tested_commit=new_candidate, decision="approve", message="approved")
        integrated = ReviewGate(self.checkouts).integrate(
            "NSC-042", expected_source_commit=source_head, target_branch=branch)
        self.assertEqual("integrated", integrated["status"])
        self.assertEqual(new_candidate, self.git("rev-parse", "HEAD").decode().strip())


if __name__ == "__main__":
    unittest.main()
