#!/usr/bin/env python
"""Shared main-write admission and abort behavior; throwaway Git repositories only.

Classification: pure/component and subprocess integration tests. Mapping:
MainWriteLock acceptance and regression invariants, not Unity gameplay gates.
"""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

GER = Path(__file__).resolve().parents[1]
HOST = GER.parent
sys.path.insert(0, str(GER))
sys.path.insert(0, str(HOST))
import main_write as mw
import main_write_lock as lock
import apply_contract as ac
import contract_commit as cc
import apply_followup_revision as follow


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ger-main-write-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture@nosafecircle.invalid")
        (self.repo / "base.txt").write_text("base")
        git(self.repo, "add", "base.txt")
        git(self.repo, "commit", "-m", "base", "--no-gpg-sign")
        self.head = git(self.repo, "rev-parse", "HEAD")
        self.journal = self.root / "journal.md"
        self.env = mock.patch.dict(os.environ, {"NSC_ROLE": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def start(self, **kwargs):
        return mw.start("fixture", kwargs.pop("head", self.head), repo=self.repo,
                        role=kwargs.pop("role", "Test Agent"), journal=self.journal, **kwargs)

    def transaction(self, **kwargs):
        return mw.transaction("fixture", self.head, repo=self.repo, role="Test Agent",
                              journal=self.journal, touched=["base.txt"], **kwargs)

    def text(self):
        return self.journal.read_text() if self.journal.exists() else ""


class AdmissionAndJournal(Base):
    def test_different_and_same_roles_contend(self):
        first = self.start()
        for role in ("Other Agent", "Test Agent"):
            with self.assertRaises(lock.MainWriteLockBusy):
                self.start(role=role, timeout=0)
        self.assertEqual(1, self.text().count("MAIN-WRITE START"))
        mw.end(first, self.head, "done")
        self.assertIn("MAIN-WRITE END Test Agent:", self.text())
        second = self.start()
        mw.end(second, self.head, "done")

    def test_historical_unclosed_start_does_not_block(self):
        self.journal.write_text("- 2026-09-22 21:00 UTC MAIN-WRITE START Other Agent: stale\n")
        first = self.start()
        mw.end(first, self.head, "done")

    def test_exact_handle_binds_journal_and_prevents_duplicate_end(self):
        first = self.start()
        self.assertIn(first.lock.operation_id, self.text())
        mw.end(first, self.head, "done")
        second = self.start()
        before = self.text()
        mw.end(first, self.head, "duplicate")
        self.assertEqual(before, self.text())
        self.assertEqual(second.lock.owner_oid, lock.inspect(repo=self.repo)[0])
        mw.end(second, self.head, "done")

    def test_role_required_environment_allowed(self):
        with self.assertRaises(SystemExit):
            self.start(role=None)
        with mock.patch.dict(os.environ, {"NSC_ROLE": "Cleanup Agent"}):
            owner = self.start(role=None)
        self.assertEqual("Cleanup Agent", owner.lock.role)
        mw.end(owner, self.head, "done")

    def test_invalid_role_is_refused_without_journal(self):
        for role in ("Vincent", "Agent 7", "pipeline-maintainer"):
            with self.assertRaises(SystemExit):
                self.start(role=role)
        self.assertEqual("", self.text())

    def test_start_append_failure_releases(self):
        with mock.patch.object(mw, "_append", side_effect=OSError("fixture journal failure")):
            with self.assertRaises(OSError):
                self.start()
        self.assertIsNone(lock.inspect(repo=self.repo))

    def test_end_append_failure_releases(self):
        owner = self.start()
        with mock.patch.object(mw, "_append", side_effect=OSError("fixture journal failure")):
            with self.assertRaises(OSError):
                mw.end(owner, self.head, "done")
        self.assertIsNone(lock.inspect(repo=self.repo))
        before = self.text()
        mw.end(owner, self.head, "retry")
        self.assertEqual(before, self.text())

    def test_head_change_before_acquire_refuses_without_start(self):
        git(self.repo, "commit", "--allow-empty", "-m", "concurrent write", "--no-gpg-sign")
        with self.assertRaisesRegex(SystemExit, "HEAD moved"):
            self.start()
        self.assertEqual("", self.text())
        self.assertIsNone(lock.inspect(repo=self.repo))

    def test_default_journal_is_private_for_fixture(self):
        self.assertEqual(self.repo / ".git/nsc-main-write-journal.md", mw.default_journal(self.repo))

    def test_diagnostic_parser_reads_new_seconds(self):
        owner = self.start()
        self.assertEqual(1, len(mw.open_writes(journal=self.journal)))
        mw.end(owner, self.head, "done")
        self.assertEqual([], mw.open_writes(journal=self.journal))


class ProtectedChecksAndRestoration(Base):
    def test_non_main_branch_refuses_before_mutation(self):
        git(self.repo, "checkout", "-b", "feature")
        entered = False
        try:
            with self.transaction():
                entered = True
        except SystemExit as error:
            self.assertIn("not checked out on main", str(error))
        self.assertFalse(entered, "a writer must not enter its mutation body off main")
        self.assertEqual(self.head, git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual("", git(self.repo, "status", "--porcelain"))
        self.assertIsNone(lock.inspect(repo=self.repo))

    def test_changed_touched_path_is_not_restored_by_refused_writer(self):
        (self.repo / "base.txt").write_text("other writer")
        with self.assertRaisesRegex(SystemExit, "target paths"):
            with self.transaction():
                self.fail("must not enter")
        self.assertEqual("other writer", (self.repo / "base.txt").read_text())
        self.assertIsNone(lock.inspect(repo=self.repo))

    def test_staged_unrelated_path_refuses_without_reset(self):
        (self.repo / "other.txt").write_text("other writer")
        git(self.repo, "add", "other.txt")
        with self.assertRaisesRegex(SystemExit, "index"):
            with self.transaction():
                self.fail("must not enter")
        self.assertEqual("other.txt", git(self.repo, "diff", "--cached", "--name-only"))

    def test_plan_input_drift_refuses_before_snapshot(self):
        with self.assertRaisesRegex(SystemExit, "changed since planning"):
            with self.transaction(expected_files={"base.txt": b"different planning bytes"}):
                self.fail("must not enter")
        self.assertEqual("base", (self.repo / "base.txt").read_text())

    def test_body_failure_restores_bytes_and_index_while_held(self):
        with self.assertRaises(ValueError):
            with self.transaction() as owner:
                self.assertEqual(owner.lock.owner_oid, lock.inspect(repo=self.repo)[0])
                (self.repo / "base.txt").write_text("changed")
                git(self.repo, "add", "base.txt")
                raise ValueError("fixture failure")
        self.assertEqual("base", (self.repo / "base.txt").read_text())
        self.assertEqual("", git(self.repo, "status", "--porcelain"))
        self.assertIsNone(lock.inspect(repo=self.repo))

    def test_postcommit_failure_preserves_commit_and_reports_it(self):
        with self.assertRaises(ValueError):
            with self.transaction():
                (self.repo / "base.txt").write_text("committed")
                git(self.repo, "add", "base.txt")
                git(self.repo, "commit", "-m", "fixture commit", "--no-gpg-sign")
                raise ValueError("output/report failed after commit")
        self.assertNotEqual(self.head, git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual("committed", (self.repo / "base.txt").read_text())
        self.assertIn("committed result retained", self.text())
        self.assertNotIn("nothing committed", self.text())
        self.assertIsNone(lock.inspect(repo=self.repo))

    def test_observation_failure_releases_and_fails(self):
        original = mw._git
        with self.assertRaisesRegex(OSError, "HEAD observation"):
            with self.transaction():
                def failed(repo, *args):
                    if args == ("rev-parse", "HEAD"):
                        raise OSError("HEAD observation fixture")
                    return original(repo, *args)
                patcher = mock.patch.object(mw, "_git", side_effect=failed)
                patcher.start()
                self.addCleanup(patcher.stop)
        self.assertIsNone(lock.inspect(repo=self.repo))

    def test_uncertain_child_retains_lock_and_changed_bytes(self):
        with self.assertRaises(lock.MutationChildUncertain):
            with self.transaction() as owner:
                (self.repo / "base.txt").write_text("possibly still writing")
                raise lock.MutationChildUncertain("fixture child")
        self.assertEqual(owner.lock.owner_oid, lock.inspect(repo=self.repo)[0])
        self.assertEqual("possibly still writing", (self.repo / "base.txt").read_text())
        lock.release(owner.lock)

    def test_incomplete_restore_is_reported_but_releases(self):
        original = Path.write_bytes
        with self.assertRaisesRegex(lock.MainWriteLockError, "restoration incomplete"):
            with self.transaction():
                (self.repo / "base.txt").write_text("changed")
                def blocked(path, data):
                    if path.resolve() == (self.repo / "base.txt").resolve():
                        raise OSError("fixture locked file")
                    return original(path, data)
                patcher = mock.patch.object(Path, "write_bytes", blocked)
                patcher.start()
                self.addCleanup(patcher.stop)
                raise ValueError("fixture abort")
        self.assertIn("restoration incomplete", self.text())
        self.assertIsNone(lock.inspect(repo=self.repo))


class AllCallersUseTheSharedTransaction(unittest.TestCase):
    CALLERS = [GER / name for name in ("apply_contract.py", "contract_commit.py", "apply_followup_revision.py")] + [
        HOST / "ger-contract-revisions-20260916" / name for name in ("new_task_commit.py", "policy_entry_commit.py")]

    def test_all_five_require_repo_role_journal_and_touched_paths(self):
        for path in self.CALLERS:
            with self.subTest(path=path.name):
                tree = ast.parse(path.read_text())
                calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and
                         isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and
                         n.func.value.id == "main_write" and n.func.attr == "transaction"]
                self.assertEqual(1, len(calls))
                self.assertTrue({"repo", "role", "journal", "touched", "expected_files"} <= {k.arg for k in calls[0].keywords})
                legacy = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and
                          isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and
                          n.func.value.id == "main_write" and n.func.attr in ("start", "end")]
                self.assertEqual([], legacy)

    def test_extras_import_bundled_ger_in_fresh_process(self):
        for path in self.CALLERS[-2:]:
            script = "import runpy,sys; d=runpy.run_path(sys.argv[1]); print(d['main_write'].__file__); print(d['ac'].__file__)"
            result = subprocess.run([sys.executable, "-B", "-c", script, str(path)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn(str(GER / "main_write.py"), result.stdout)
            self.assertIn(str(GER / "apply_contract.py"), result.stdout)


class FiveCallerFixture(Base):
    """Real entry points commit only throwaway tasks, with a local validator stub."""
    NAMES = ("apply_contract", "contract_commit", "apply_followup_revision", "new_task_commit", "policy_entry_commit")

    def build(self, name):
        repo = self.root / name
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@nosafecircle.invalid")
        git(repo, "config", "core.autocrlf", "false")
        contract = {"schema_version": 1, "id": "NSC-001", "parent": "NSC-001",
                    "reconciliation_key": "fixture-one", "contract_revision": 1,
                    "title": "Fixture task", "depends_on": [], "exclusive_resources": [], "provenance": {}}
        files = {"Tasks/NSC-001.yaml": contract,
                 "Pipeline/TaskGraph/RESOURCE_GROUPS.yaml": {"resource_groups": [], "schema_version": 1},
                 "Pipeline/TaskGraph/WORK_ID_MAP.json": {"id_map": {"fixture-one": "NSC-001"}},
                 "Pipeline/TaskReviewAgent/authoritative_validation_policy.json": {"tasks": {}}}
        for rel, data in files.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(ac.serialize(data, False))
        validator = repo / "Pipeline/TaskGraph/taskcontrol.py"
        validator.write_text("import subprocess\nr = subprocess.run(['git','show-ref','--verify','--quiet','refs/locks/main-write'])\nassert r.returncode == 0, 'validator must run while owner holds lock'\nprint('PASS')\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "fixture graph", "--no-gpg-sign")
        head = git(repo, "rev-parse", "HEAD")
        output = self.root / (name + "-output")
        output.mkdir()
        revised = dict(contract, contract_revision=2, title="Revised fixture task")
        revised_path = output / "revision.json"
        revised_path.write_bytes(ac.serialize(revised, False))
        common = ["--role", "Test Agent"]
        modules = {"apply_contract": ac, "contract_commit": cc, "apply_followup_revision": follow}
        if name in ("new_task_commit", "policy_entry_commit"):
            path = HOST / "ger-contract-revisions-20260916" / (name + ".py")
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        else:
            module = modules[name]
        if name == "contract_commit":
            args = ["--task", "NSC-001", "--revised", str(revised_path), "--reason", "fixture"]
        elif name == "apply_followup_revision":
            from ger_fixtures import result_bytes
            report = output / "review.json"
            report.write_bytes(result_bytes(artifact=revised_path.read_bytes()))
            args = ["--task", "NSC-001", "--revised", str(revised_path), "--report", str(report),
                    "--reviewer", "Fixture reviewer", "--reason", "fixture"]
        elif name == "new_task_commit":
            draft = dict(contract, id="NSC-002", reconciliation_key="fixture-two")
            draft_path = output / "new.json"
            draft_path.write_bytes(ac.serialize(draft, False))
            args = ["--new", "NSC-002=" + str(draft_path), "--template", "NSC-001", "--reason", "fixture"]
        elif name == "policy_entry_commit":
            args = ["--task", "NSC-001", "--editmode", "FixtureTest", "--reason", "fixture"]
        else:
            from ger_fixtures import reviewed, decision, result_bytes
            original = (repo / "Tasks/NSC-001.yaml").read_bytes()
            (output / "SOURCE_IDENTITY.json").write_text(json.dumps(
                {"task_id": "NSC-001", "task_sha256": ac.sha256(original), "source_head": head}))
            for round_name in ac.ROUNDS[:2]:
                directory = output / round_name
                directory.mkdir()
                (directory / "OUTPUT.md").write_text("Fixture intermediate output")
            candidate = ("Final proposed task contract\n```json\n" + json.dumps(revised) + "\n```\n").encode()
            reviewed(output, candidate)
            decision(output, result_bytes(artifact=candidate))
            args = ["--packet", str(output)]
        return repo, head, module, args + common

    def invoke(self, repo, module, args):
        with mock.patch.object(ac, "REPO", repo), mock.patch.object(sys, "argv", [module.__file__, *args]), contextlib.redirect_stdout(io.StringIO()):
            return module.main()

    def test_all_five_dry_runs_leave_no_lock_journal_or_changes(self):
        for name in self.NAMES:
            with self.subTest(name=name):
                repo, head, module, args = self.build(name)
                self.assertEqual(0, self.invoke(repo, module, args))
                self.assertEqual(head, git(repo, "rev-parse", "HEAD"))
                self.assertEqual("", git(repo, "status", "--porcelain"))
                self.assertFalse(mw.default_journal(repo).exists())
                self.assertIsNone(lock.inspect(repo=repo))

    def test_all_five_commit_under_lock_and_leave_clean_results(self):
        for name in self.NAMES:
            with self.subTest(name=name):
                repo, head, module, args = self.build(name)
                self.assertEqual(0, self.invoke(repo, module, args + ["--commit"]))
                self.assertNotEqual(head, git(repo, "rev-parse", "HEAD"))
                self.assertEqual("", git(repo, "status", "--porcelain"))
                journal = mw.default_journal(repo).read_text()
                self.assertEqual(1, journal.count("MAIN-WRITE START"))
                self.assertEqual(1, journal.count("MAIN-WRITE END"))
                self.assertIsNone(lock.inspect(repo=repo))

    def test_all_five_repeat_path_checks_after_start(self):
        for name in self.NAMES:
            with self.subTest(name=name):
                repo, head, module, args = self.build(name)
                target = (repo / ("Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
                                 if name == "policy_entry_commit" else
                                 "Pipeline/TaskGraph/WORK_ID_MAP.json" if name == "new_task_commit" else "Tasks/NSC-001.yaml"))
                real_start = mw.start
                def changed(*a, **kw):
                    owner = real_start(*a, **kw)
                    target.write_bytes(target.read_bytes() + b" ")
                    return owner
                with mock.patch.object(mw, "start", side_effect=changed):
                    with self.assertRaisesRegex(SystemExit, "target paths"):
                        self.invoke(repo, module, args + ["--commit"])
                self.assertEqual(head, git(repo, "rev-parse", "HEAD"))
                self.assertTrue(target.read_bytes().endswith(b" "))
                self.assertIsNone(lock.inspect(repo=repo))

    def test_all_five_validation_failure_restores_and_releases(self):
        for name in self.NAMES:
            with self.subTest(name=name):
                repo, head, module, args = self.build(name)
                validator = repo / "Pipeline/TaskGraph/taskcontrol.py"
                validator.write_text("import sys\nprint('fixture validation failed')\nsys.exit(1)\n")
                git(repo, "add", "Pipeline/TaskGraph/taskcontrol.py")
                git(repo, "commit", "-m", "failing fixture validator", "--no-gpg-sign")
                before = git(repo, "rev-parse", "HEAD")
                with self.assertRaisesRegex(SystemExit, "taskcontrol validate failed"):
                    self.invoke(repo, module, args + ["--commit"])
                self.assertEqual(before, git(repo, "rev-parse", "HEAD"))
                self.assertEqual("", git(repo, "status", "--porcelain"))
                self.assertIsNone(lock.inspect(repo=repo))

    def test_all_five_commit_hook_failure_restores_and_releases(self):
        for name in self.NAMES:
            with self.subTest(name=name):
                repo, head, module, args = self.build(name)
                hook = repo / ".git/hooks/pre-commit"
                hook.write_bytes(b"#!/bin/sh\nexit 1\n")
                hook.chmod(0o755)
                with self.assertRaises(SystemExit):
                    self.invoke(repo, module, args + ["--commit"])
                self.assertEqual(head, git(repo, "rev-parse", "HEAD"))
                self.assertEqual("", git(repo, "status", "--porcelain"))
                self.assertIsNone(lock.inspect(repo=repo))


class CrossAdapterProcesses(FiveCallerFixture):
    # Inherit fixture methods but do not repeat its three entry-point test groups.
    test_all_five_dry_runs_leave_no_lock_journal_or_changes = None
    test_all_five_commit_under_lock_and_leave_clean_results = None
    test_all_five_repeat_path_checks_after_start = None
    test_all_five_validation_failure_restores_and_releases = None
    test_all_five_commit_hook_failure_restores_and_releases = None

    def sources(self):
        import shutil
        roots = []
        for name in ("source-a", "source-b"):
            root = self.root / name
            (root / "ger").mkdir(parents=True)
            for file in ("main_write_lock.py", "guarded_merge.py"):
                shutil.copyfile(HOST / file, root / file)
            shutil.copyfile(GER / "main_write.py", root / "ger/main_write.py")
            roots.append(root)
        return roots

    def exercise(self, holder_kind):
        repo, head, module, args = self.build("contract_commit")
        git(repo, "checkout", "-b", "candidate")
        (repo / "independent.txt").write_text("independent merge work")
        git(repo, "add", "independent.txt")
        git(repo, "commit", "-m", "independent work", "--no-gpg-sign")
        candidate = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "main")
        first, second = self.sources()
        journal = self.root / "shared-journal.md"
        script = """
import pathlib,sys,json
source,realger,repo,journal,mode,head,candidate,args = sys.argv[1:]
sys.path[:0] = [source, str(pathlib.Path(source)/'ger')]
import main_write as mw, main_write_lock as lock, guarded_merge as gm
assert pathlib.Path(mw.__file__).resolve() == (pathlib.Path(source)/'ger/main_write.py').resolve()
assert pathlib.Path(lock.__file__).resolve() == (pathlib.Path(source)/'main_write_lock.py').resolve()
if mode == 'hold-merge':
    with gm.held(gm.Git(pathlib.Path(repo)), 'Holder Agent', 0):
        print('READY', flush=True)
        sys.stdin.readline()
elif mode == 'hold-ger':
    owner = mw.start('valid GER write',head,repo=repo,role='Holder Agent',journal=pathlib.Path(journal))
    print('READY', flush=True)
    sys.stdin.readline()
    mw.end(owner,head,'fixture owner done')
else:
    try:
        if mode == 'merge':
            code = gm.main(['--repo',repo,'--journal',journal,'--role','Contender Agent','--candidate',candidate,
                            '--authority','fixture','--lock-timeout','0','--validate','Pipeline/TaskGraph/taskcontrol.py'])
        else:
            sys.path.append(realger)
            import contract_commit as cc
            cc.ac.REPO=pathlib.Path(repo)
            original_start=mw.start
            def immediate(*a,**kw):
                kw['timeout']=0
                return original_start(*a,**kw)
            mw.start=immediate
            sys.argv=[cc.__file__,*json.loads(args),'--commit','--journal',journal]
            code=cc.main()
        sys.exit(code)
    except lock.MainWriteLockBusy as busy:
        print(busy)
        sys.exit(3)
"""
        common = [str(GER), str(repo), str(journal)]
        def command(source, mode):
            return [sys.executable, "-B", "-c", script, str(source), *common, mode, head, candidate, json.dumps(args)]
        owner = subprocess.Popen(command(first, "hold-" + holder_kind), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual("READY", owner.stdout.readline().strip())
            before_journal = journal.read_bytes() if journal.exists() else b""
            loser = "ger" if holder_kind == "merge" else "merge"
            refused = subprocess.run(command(second, loser), capture_output=True, text=True, timeout=20)
            self.assertEqual(3, refused.returncode, refused.stdout + refused.stderr)
            self.assertIn("Holder Agent", refused.stdout)
            self.assertEqual(head, git(repo, "rev-parse", "HEAD"))
            self.assertEqual("", git(repo, "status", "--porcelain"))
            self.assertEqual(before_journal, journal.read_bytes() if journal.exists() else b"")
            out, err = owner.communicate("release\n", timeout=20)
            self.assertEqual(0, owner.returncode, out + err)
            accepted = subprocess.run(command(second, loser), capture_output=True, text=True, timeout=30)
            self.assertEqual(0, accepted.returncode, accepted.stdout + accepted.stderr)
            self.assertNotEqual(head, git(repo, "rev-parse", "HEAD"))
            self.assertEqual("", git(repo, "status", "--porcelain"))
            self.assertIsNone(lock.inspect(repo=repo))
            self.assertEqual(1, journal.read_text().count("MAIN-WRITE START " + ("Test Agent" if loser == "ger" else "Contender Agent")))
        finally:
            if owner.poll() is None:
                owner.communicate("release\n", timeout=20)

    def test_merger_adapter_excludes_real_ger_committer_then_retry_commits(self):
        self.exercise("merge")

    def test_ger_adapter_excludes_real_merger_then_retry_merges(self):
        self.exercise("ger")


if __name__ == "__main__":
    unittest.main(verbosity=2)
