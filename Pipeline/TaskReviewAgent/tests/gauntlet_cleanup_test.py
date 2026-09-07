"""Whole-run reset coordination with fake canonical reset boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from Pipeline.TaskReviewAgent import gauntlet_cleanup as c
from Pipeline.TaskReviewAgent import prepare_synthetic_gauntlet as g
from Pipeline.TaskReviewAgent.issue_workflow import AUTOMATED_VALIDATION_REPOSITORIES


class CleanupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle, cls.manifest = g.build_bundle(
            ROOT, "thousand", target_repository=g.PRIVATE_REPOSITORY
        )
        cls.tasks = {key: json.loads(bundle[Path(f"Tasks/{key}.yaml")]) for key in cls.manifest["target_task_ids"]}

    def manifest_for(self, repository):
        manifest = {**self.manifest, "target_repository": repository}
        manifest.pop("manifest_sha256")
        return {**manifest, "manifest_sha256": c.digest(manifest)}

    def make_plan(self, directory, manifest=None):
        return c.plan_cleanup(manifest or self.manifest, self.tasks,
            {"NSC-2999": {"mode": "abandon"}, "NSC-2998": {"mode": "abandon"}},
            source=directory / "controller", checkout_root=directory / "checkouts", expected_head="a" * 40)

    def test_dry_plan_covers_scope_and_preserves_code(self):
        with tempfile.TemporaryDirectory() as text:
            root = Path(text)
            plan = self.make_plan(root)
            self.assertEqual(len(plan["steps"]), 1000)
            self.assertEqual(sum(step["mode"] == "retain" for step in plan["steps"]), 998)
            self.assertEqual(list(root.iterdir()), [])

    def test_partial_reset_resumes_exact_receipt_without_second_apply(self):
        with tempfile.TemporaryDirectory() as text:
            root = Path(text)
            repository = next(item for item in AUTOMATED_VALIDATION_REPOSITORIES if item != g.PRIVATE_REPOSITORY)
            plan = self.make_plan(root, self.manifest_for(repository))
            path = root / "progress.json"
            calls = []
            class Operation:
                def __init__(self, task): self.task = task
                def preflight(self): return {"main_head": "a" * 40}
                def apply(self, exact, *, receipt_path):
                    calls.append((self.task, "apply"))
                    receipt_path.parent.mkdir(parents=True, exist_ok=True)
                    value = {"status": "complete", "task_id": self.task, "repository": repository}
                    receipt_path.write_text(json.dumps(value), encoding="utf-8")
                    if self.task == "NSC-2998": raise RuntimeError("interrupted after canonical side effect")
                    return value
                def resume(self, receipt):
                    calls.append((self.task, "resume"))
                    return json.loads(receipt.read_text())
            factory = lambda plan, step: Operation(step["task_id"])
            guards = []
            source_guards = []
            with self.assertRaises(RuntimeError):
                c.execute(plan, path, factory=factory, guard=guards.append, source_guard=source_guards.append)
            saved = json.loads(path.read_text())
            with self.assertRaises(c.CleanupError):
                c.execute(plan, path, expected_progress_sha256="f" * 64, factory=factory, guard=guards.append,
                          source_guard=source_guards.append)
            result = c.execute(plan, path, expected_progress_sha256=saved["sha256"], factory=factory,
                               guard=guards.append, source_guard=source_guards.append)
            self.assertEqual(len(result["completed"]), 1000)
            self.assertEqual(calls, [("NSC-2999", "apply"), ("NSC-2998", "apply"), ("NSC-2998", "resume")])
            self.assertEqual(guards, ["a" * 40, "a" * 40])
            self.assertEqual(source_guards, [plan, plan, plan])
            c.execute(plan, path, expected_progress_sha256=result["sha256"], factory=factory,
                guard=lambda _: self.fail("completed resume called remote guard"),
                source_guard=lambda _: self.fail("completed resume repeated source check"))
            self.assertEqual(len(calls), 3)

    def test_both_repository_plans_bind_actual_committed_manifest(self):
        with tempfile.TemporaryDirectory() as text:
            root = Path(text)
            for repository in sorted(AUTOMATED_VALIDATION_REPOSITORIES):
                manifest = self.manifest_for(repository)
                plan = self.make_plan(root, manifest)
                self.assertEqual(plan["repository"], repository)
                calls = []
                def observed(source, *args):
                    self.assertEqual(source, (root / "controller").resolve())
                    calls.append(args)
                    if args == ("git", "remote", "get-url", "origin"):
                        return f"https://github.com/{repository}.git"
                    self.assertEqual(args, ("git", "show", f"HEAD:{g.MANIFEST_RELATIVE.as_posix()}"))
                    return json.dumps(manifest)
                with patch.object(g, "_run", observed):
                    c.verify_plan_source(plan)
                self.assertEqual(len(calls), 2)
                self.assertEqual(list(root.iterdir()), [])

    def test_wrong_actual_repository_or_committed_manifest_blocks_reset(self):
        with tempfile.TemporaryDirectory() as text:
            root = Path(text)
            plan = self.make_plan(root)
            other = next(item for item in AUTOMATED_VALIDATION_REPOSITORIES if item != g.PRIVATE_REPOSITORY)
            for fault in ("repository", "manifest"):
                def observed(source, *args):
                    if args == ("git", "remote", "get-url", "origin"):
                        return f"https://github.com/{other if fault == 'repository' else g.PRIVATE_REPOSITORY}.git"
                    self.assertEqual(args, ("git", "show", f"HEAD:{g.MANIFEST_RELATIVE.as_posix()}"))
                    changed = {**self.manifest, "source_head": "c" * 40}
                    return json.dumps(changed)
                with patch.object(g, "_run", observed), self.assertRaises(c.CleanupError):
                    c.execute(plan, root / f"{fault}.json",
                              factory=lambda *_: self.fail("reset reached"),
                              guard=lambda *_: self.fail("remote guard reached"))
                self.assertFalse((root / f"{fault}.json").exists())

    def test_apply_cli_binds_reviewed_source_checkout_root_and_repository(self):
        with tempfile.TemporaryDirectory() as text:
            root = Path(text)
            repository = next(item for item in AUTOMATED_VALIDATION_REPOSITORIES if item != g.PRIVATE_REPOSITORY)
            plan = self.make_plan(root, self.manifest_for(repository))
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            args = ["gauntlet_cleanup.py", "--source", plan["source"], "--checkout-root", plan["checkout_root"],
                    "--inventory", str(root / "unused-inventory.json"), "--expected-head", plan["expected_head"],
                    "--plan", str(plan_path), "--progress", str(root / "progress.json"),
                    "--confirm-repository", repository, "--confirm-plan-sha256", plan["sha256"], "--apply"]
            for flag, value in (("--source", str(root / "other-source")),
                                ("--checkout-root", str(root / "other-checkouts")),
                                ("--confirm-repository", g.PRIVATE_REPOSITORY),
                                ("--expected-head", "b" * 40)):
                changed = list(args)
                changed[changed.index(flag) + 1] = value
                with patch.object(sys, "argv", changed), patch.object(c, "execute") as execute:
                    with self.assertRaises(c.CleanupError):
                        c.main()
                    execute.assert_not_called()
            with patch.object(sys, "argv", args), patch.object(c, "execute", return_value={"status": "fake"}) as execute, \
                    patch("builtins.print"):
                c.main()
                self.assertEqual(execute.call_count, 1)
                self.assertEqual(execute.call_args.args[0], plan)

    def test_retention_only_progress_requires_actual_source_binding(self):
        with tempfile.TemporaryDirectory() as text:
            root = Path(text)
            plan = c.plan_cleanup(self.manifest, self.tasks, {}, source=root / "controller",
                                  checkout_root=root / "checkouts", expected_head="a" * 40)
            path = root / "progress.json"
            def reject_source(_):
                raise c.CleanupError("wrong source")
            with self.assertRaisesRegex(c.CleanupError, "wrong source"):
                c.execute(plan, path, source_guard=reject_source,
                          factory=lambda *_: self.fail("retention launched a reset"))
            self.assertFalse(path.exists())
            with patch.object(c, "verify_plan_source") as observed:
                result = c.execute(plan, path, source_guard=observed,
                                   factory=lambda *_: self.fail("retention launched a reset"))
                observed.assert_called_once_with(plan)
            self.assertEqual(len(result["completed"]), 1000)

    def test_wrong_manifest_scope_and_corrupt_plan_fail(self):
        with tempfile.TemporaryDirectory() as text:
            root = Path(text)
            for update in ({"target_repository": "cathode26/NoSafeCircle"}, {"excluded_task_ids": []}, {"schema_version": "999"}):
                manifest = {**self.manifest, **update}
                with self.assertRaises(c.CleanupError):
                    c.plan_cleanup(manifest, self.tasks, {}, source=root, checkout_root=root, expected_head="a" * 40)
            with self.assertRaises(c.CleanupError):
                c.plan_cleanup(self.manifest, self.tasks, {"NSC-042": {"mode": "abandon"}}, source=root, checkout_root=root, expected_head="a" * 40)
            plan = self.make_plan(root)
            plan["steps"][0]["mode"] = "delete-everything"
            with self.assertRaises(c.CleanupError):
                c.execute(plan, root / "progress.json")
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    run_with_synthetic_authority(unittest.main)
