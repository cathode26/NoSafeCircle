"""Real-Git fixture checks for the selective per-task gauntlet-replay revert."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.reset_task import (
    ResetTaskError,
    _journal_path,
    plan_reset,
    reset_task,
)
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(("git", "-C", str(root), *args), capture_output=True, check=False)
    if result.returncode:
        raise AssertionError(result.stderr.decode(errors="replace"))
    return result.stdout.decode().strip()


def _contract(task_id: str, title: str, depends_on: list[str] | None = None) -> bytes:
    return json.dumps({
        "id": task_id, "title": title, "contract_disposition": "active",
        "depends_on": depends_on or [], "exclusive_resources": [],
    }).encode("utf-8")


class ResetTaskTests(unittest.TestCase):
    """NSC-1124 (task A) is always the task under test; NSC-1125 (task B)
    represents unrelated later-integrated work that must survive intact."""

    def setUp(self):
        test_root = Path.cwd() / ".test-work"
        test_root.mkdir(exist_ok=True)
        self.root = test_root / f"reset-task-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.source = self.root / "source"
        self.source.mkdir()
        _git(self.source, "init", "-q")
        name, email = validated_agent_git_identity()
        _git(self.source, "config", "user.name", name)
        _git(self.source, "config", "user.email", email)
        (self.source / "Tasks").mkdir()
        (self.source / "Tasks/NSC-1124.yaml").write_bytes(_contract("NSC-1124", "Task A"))
        (self.source / "Tasks/NSC-1125.yaml").write_bytes(_contract("NSC-1125", "Task B"))
        _git(self.source, "add", ".")
        _git(self.source, "commit", "-q", "-m", "fixture base")
        _git(self.source, "checkout", "-q", "-b", "gauntlet-replay/demo")
        self.base_commit = _git(self.source, "rev-parse", "HEAD")

        self.checkout_root = self.root / "checkouts"
        self.manager = Checkouts(self.source, self.checkout_root)
        self.manager.records.mkdir(parents=True, exist_ok=True)

        # Integrate task A: one commit changing a-file.txt.
        (self.source / "a-file.txt").write_text("task A content\n")
        _git(self.source, "add", ".")
        _git(self.source, "commit", "-q", "-m", "Implement NSC-1124")
        self.task_a_commit = _git(self.source, "rev-parse", "HEAD")
        self._write_integrated_record("NSC-1124", source_commit=self.base_commit,
                                       candidate_commit=self.task_a_commit)

    def _write_integrated_record(self, task_id: str, *, source_commit: str, candidate_commit: str) -> None:
        write_record(self.manager.records / f"{task_id}.json", {
            "task_id": task_id, "source": str(self.manager.source),
            "checkout": str(self.checkout_root / task_id),
            "branch": "gauntlet-replay/demo", "source_commit": source_commit,
            "status": "integrated",
            "integration": {"candidate": candidate_commit, "branch": "gauntlet-replay/demo"},
        })

    def _integrate_task_b(self, *, filename: str = "b-file.txt") -> str:
        pre = _git(self.source, "rev-parse", "HEAD")
        (self.source / filename).write_text("task B content\n")
        _git(self.source, "add", ".")
        _git(self.source, "commit", "-q", "-m", "Implement NSC-1125")
        commit = _git(self.source, "rev-parse", "HEAD")
        self._write_integrated_record("NSC-1125", source_commit=pre, candidate_commit=commit)
        return commit

    def test_dry_run_reports_plan_and_mutates_nothing(self):
        self._integrate_task_b()
        head_before = _git(self.source, "rev-parse", "HEAD")
        plan = reset_task(self.manager, "NSC-1124", apply=False)
        self.assertFalse(plan["apply"])
        self.assertEqual(self.base_commit, plan["pre_task_commit"])
        self.assertEqual(self.task_a_commit, plan["task_candidate_commit"])
        self.assertEqual(["a-file.txt"], plan["task_changed_paths"])
        self.assertEqual(head_before, _git(self.source, "rev-parse", "HEAD"))
        self.assertEqual("", _git(self.source, "status", "--porcelain"))

    def test_unrelated_later_commit_is_preserved_byte_for_byte(self):
        task_b_commit = self._integrate_task_b()
        original_b_bytes = (self.source / "b-file.txt").read_bytes()
        result = reset_task(self.manager, "NSC-1124", apply=True)
        self.assertEqual("done", result["phase"])
        # Task B's own commit is still reachable on the branch.
        ancestor_check = subprocess.run(
            ("git", "-C", str(self.source), "merge-base", "--is-ancestor", task_b_commit, "HEAD"),
            capture_output=True,
        )
        self.assertEqual(0, ancestor_check.returncode)
        self.assertEqual(original_b_bytes, (self.source / "b-file.txt").read_bytes())
        self.assertFalse((self.source / "a-file.txt").exists())
        self.assertEqual("", _git(self.source, "status", "--porcelain=v1", "--untracked-files=all"))

    def test_two_selected_tasks_with_interleaved_unrelated_work(self):
        task_b_commit = self._integrate_task_b()
        # Task C integrates after B, also unrelated to A and B.
        (self.source / "c-file.txt").write_text("task C content\n")
        (self.source / "Tasks/NSC-1126.yaml").write_bytes(_contract("NSC-1126", "Task C"))
        _git(self.source, "add", ".")
        _git(self.source, "commit", "-q", "-m", "Implement NSC-1126")
        task_c_commit = _git(self.source, "rev-parse", "HEAD")
        self._write_integrated_record("NSC-1126", source_commit=task_b_commit, candidate_commit=task_c_commit)

        reset_task(self.manager, "NSC-1124", apply=True)
        reset_task(self.manager, "NSC-1126", apply=True)

        self.assertFalse((self.source / "a-file.txt").exists())
        self.assertFalse((self.source / "c-file.txt").exists())
        self.assertTrue((self.source / "b-file.txt").exists())
        self.assertEqual("task B content\n", (self.source / "b-file.txt").read_text())
        self.assertEqual("", _git(self.source, "status", "--porcelain=v1", "--untracked-files=all"))

    def test_refuses_overlapping_paths_instead_of_guessing(self):
        # Task B (unrelated but touches the SAME file task A changed).
        pre = _git(self.source, "rev-parse", "HEAD")
        (self.source / "a-file.txt").write_text("task A content\ntask B addition\n")
        _git(self.source, "add", ".")
        _git(self.source, "commit", "-q", "-m", "Implement NSC-1125 overlapping A")
        commit = _git(self.source, "rev-parse", "HEAD")
        self._write_integrated_record("NSC-1125", source_commit=pre, candidate_commit=commit)
        with self.assertRaisesRegex(ResetTaskError, "same paths"):
            reset_task(self.manager, "NSC-1124", apply=True)
        self.assertEqual(commit, _git(self.source, "rev-parse", "HEAD"))

    def test_refuses_a_decomposition_parent_whose_generated_child_is_integrated_later(self):
        task_b_commit = self._integrate_task_b()
        # NSC-1124's own committed contract is rewritten to record a
        # decomposition child, matching what applying a decomposition does.
        (self.source / "Tasks/NSC-1124.yaml").write_bytes(json.dumps({
            "id": "NSC-1124", "title": "Task A", "contract_disposition": "active",
            "depends_on": [], "exclusive_resources": [],
            "decomposition_state": "decomposed", "decomposition_children": ["NSC-1128"],
        }).encode("utf-8"))
        (self.source / "Tasks/NSC-1128.yaml").write_bytes(_contract("NSC-1128", "Generated child of A"))
        (self.source / "child-file.txt").write_text("generated child content\n")
        _git(self.source, "add", ".")
        _git(self.source, "commit", "-q", "-m", "Apply decomposition and implement child NSC-1128")
        child_commit = _git(self.source, "rev-parse", "HEAD")
        self._write_integrated_record("NSC-1128", source_commit=task_b_commit, candidate_commit=child_commit)
        with self.assertRaisesRegex(ResetTaskError, "NSC-1128"):
            reset_task(self.manager, "NSC-1124", apply=True)
        self.assertEqual(child_commit, _git(self.source, "rev-parse", "HEAD"))

    def test_refuses_when_later_task_depends_on_the_selected_task(self):
        task_b_commit = self._integrate_task_b()
        (self.source / "d-file.txt").write_text("task D content\n")
        (self.source / "Tasks/NSC-1127.yaml").write_bytes(
            _contract("NSC-1127", "Task D depends on A", depends_on=["NSC-1124"]))
        _git(self.source, "add", ".")
        _git(self.source, "commit", "-q", "-m", "Implement NSC-1127 depends on NSC-1124")
        task_d_commit = _git(self.source, "rev-parse", "HEAD")
        self._write_integrated_record("NSC-1127", source_commit=task_b_commit, candidate_commit=task_d_commit)
        with self.assertRaisesRegex(ResetTaskError, "NSC-1127"):
            reset_task(self.manager, "NSC-1124", apply=True)
        self.assertEqual(task_d_commit, _git(self.source, "rev-parse", "HEAD"))

    def test_interrupted_recovery_resumes_without_re_reverting(self):
        self._integrate_task_b()
        plan = plan_reset(self.manager, "NSC-1124")
        # Simulate a crash: the revert commit already happened, but the
        # archive step never ran and 'done' was never written.
        _git(self.source, "revert", "--no-commit",
             f"{plan['pre_task_commit']}..{plan['task_candidate_commit']}")
        name, email = validated_agent_git_identity()
        _git(self.source, "-c", f"user.name={name}", "-c", f"user.email={email}",
             "commit", "-m", "Revert NSC-1124 for a fresh local replay")
        revert_commit = _git(self.source, "rev-parse", "HEAD")
        journal_path = _journal_path(self.checkout_root, "NSC-1124")
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        write_record(journal_path, {
            "schema_version": "assistant-reset-task/v2", "phase": "reverted",
            "task_id": "NSC-1124", "plan": plan, "revert_commit": revert_commit,
        })
        result = reset_task(self.manager, "NSC-1124", apply=True)
        self.assertEqual("done", result["phase"])
        # Exactly one revert commit was ever created (recovery did not
        # attempt a second revert against the already-clean tree).
        self.assertEqual(revert_commit, _git(self.source, "rev-parse", "HEAD"))
        archive = Path(result["task_archive_destination"])
        self.assertTrue(archive.is_dir())

    def test_repeated_apply_recovers_without_duplicating_the_archive(self):
        first = reset_task(self.manager, "NSC-1124", apply=True)
        self.assertEqual("done", first["phase"])
        second = reset_task(self.manager, "NSC-1124", apply=True)
        self.assertEqual(first, second)
        head_after_first = _git(self.source, "rev-parse", "HEAD")
        self.assertEqual(head_after_first, _git(self.source, "rev-parse", "HEAD"))
        archives = list((self.checkout_root / ".assistant-control-reset-archive").glob("NSC-1124-*"))
        archives = [item for item in archives if item.is_dir()]
        self.assertEqual(1, len(archives))

    def test_apply_archives_only_the_selected_task(self):
        self._integrate_task_b()
        result = reset_task(self.manager, "NSC-1124", apply=True)
        self.assertTrue((self.manager.records / "NSC-1125.json").is_file())
        self.assertFalse((self.manager.records / "NSC-1124.json").is_file())
        archive = Path(result["task_archive_destination"])
        self.assertTrue((archive / ".assistant-control" / "NSC-1124.json").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
