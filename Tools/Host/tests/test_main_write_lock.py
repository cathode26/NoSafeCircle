#!/usr/bin/env python
"""The shared main-write lock: what it must refuse, proved by refusing it.

Every case uses a throwaway repository. Nothing here touches canonical `main`,
the live journal or the live lock ref -- `repo` is a required argument with no
default precisely so that a test cannot reach production state by omission.

Contention is exercised across real PROCESSES. A same-process contender proves
nothing about a lock whose authority is a git ref, and would report exclusion
that had never been tested -- the shape that let an eight-concurrent-merger test
pass on git's idempotence without once reaching the lock it claimed to check.
"""
from __future__ import annotations

import json
import contextlib
import os
import io
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HOST = pathlib.Path(__file__).resolve().parents[1]
if str(HOST) not in sys.path:
    sys.path.insert(0, str(HOST))

import main_write_lock as lock  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git(repo: pathlib.Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args],
                            capture_output=True, text=True,
                            creationflags=NO_WINDOW)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {result.stderr}")
    return result.stdout.strip()


class Base(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(lock, "_boot_stamp", return_value="unavailable: test fixture")
        patcher.start()
        self.addCleanup(patcher.stop)

    def repo(self) -> pathlib.Path:
        root = pathlib.Path(tempfile.mkdtemp(prefix="main-write-lock-"))
        self.addCleanup(self._clean, root)
        repo = root / "canonical"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.email", "fixture@nosafecircle.invalid")
        git(repo, "config", "user.name", "Fixture")
        (repo / "base.txt").write_text("base", encoding="utf-8")
        git(repo, "add", "base.txt")
        git(repo, "commit", "-m", "base", "--no-gpg-sign")
        return repo

    @staticmethod
    def _clean(root: pathlib.Path) -> None:
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    def contend(self, repo: pathlib.Path, *, role="Other Agent",
                timeout=0.5) -> tuple[int, str]:
        """Try to acquire from a SEPARATE PROCESS. 3 means refused as busy."""
        script = "\n".join([
            "import sys",
            "sys.path.insert(0, sys.argv[1])",
            "import main_write_lock as lock",
            "lock._boot_stamp = lambda: 'unavailable: test fixture'",
            "try:",
            "    h = lock.acquire(repo=sys.argv[2], role=sys.argv[3],",
            "                     operation='contender', timeout=float(sys.argv[4]))",
            "except lock.MainWriteLockBusy as busy:",
            "    print(busy)",
            "    sys.exit(3)",
            "lock.release(h)",
            "sys.exit(0)",
        ])
        result = subprocess.run(
            [sys.executable, "-c", script, str(HOST), str(repo), role,
             str(timeout)],
            capture_output=True, text=True, creationflags=NO_WINDOW)
        return result.returncode, result.stdout + result.stderr

    def plant(self, repo: pathlib.Path, body: dict) -> str:
        payload = json.dumps(body, sort_keys=True).encode("utf-8")
        oid = subprocess.run(["git", "-C", str(repo), "hash-object", "-w",
                              "--stdin"], input=payload, capture_output=True,
                             creationflags=NO_WINDOW).stdout.decode().strip()
        git(repo, "update-ref", lock.LOCK_REF, oid, "")
        return oid


class ItLocksAndUnlocks(Base):
    def test_acquire_then_release_round_trips(self):
        repo = self.repo()
        self.assertIsNone(lock.inspect(repo=repo))
        handle = lock.acquire(repo=repo, role="Pipeline Maintainer Agent",
                              operation="merge candidate/x")
        found = lock.inspect(repo=repo)
        self.assertIsNotNone(found)
        self.assertEqual(handle.owner_oid, found[0])
        self.assertEqual("merge candidate/x", found[1]["operation"])
        lock.release(handle)
        self.assertIsNone(lock.inspect(repo=repo))

    def test_held_releases_even_when_the_body_raises(self):
        repo = self.repo()
        with self.assertRaises(ZeroDivisionError):
            with lock.held(repo=repo, role="A Agent", operation="x"):
                1 / 0
        self.assertIsNone(lock.inspect(repo=repo),
                          "a raising body must not strand the lock")


class ItExcludesAcrossProcesses(Base):
    def test_a_second_process_is_refused_while_held(self):
        repo = self.repo()
        handle = lock.acquire(repo=repo, role="Pipeline Maintainer Agent",
                              operation="merge candidate/x")
        code, output = self.contend(repo)
        self.assertEqual(3, code, f"a held lock must refuse a contender: {output}")
        self.assertIn("Pipeline Maintainer Agent", output,
                      "the refusal must name who holds it")
        self.assertIn("merge candidate/x", output,
                      "the refusal must say what the holder is doing")
        lock.release(handle)
        self.assertEqual(0, self.contend(repo)[0],
                         "the lock must be takeable once released")

    def test_the_same_role_in_two_processes_still_contends(self):
        """A role is attribution, not ownership."""
        repo = self.repo()
        handle = lock.acquire(repo=repo, role="Same Agent", operation="first")
        code, output = self.contend(repo, role="Same Agent")
        self.assertEqual(3, code,
                         f"same role must not bypass the lock: {output}")
        lock.release(handle)


class ItNeverStealsALiveLock(Base):
    def test_an_ancient_lock_is_NOT_taken_automatically(self):
        """The whole point of the redesign.

        The predecessor deleted any lock older than 1800s and took it. An
        expired timestamp does not revoke a running process's ability to write,
        so age alone is never authority.
        """
        repo = self.repo()
        self.plant(repo, {"schema_version": lock.BLOB_SCHEMA,
                          "operation_id": "ancient", "role": "Ghost Agent",
                          "operation": "a write that never ended",
                          "host": "elsewhere", "pid": 99999,
                          "acquired_epoch": time.time() - 86_400})
        code, output = self.contend(repo, timeout=0.5)
        self.assertEqual(3, code,
                         f"a day-old lock must still refuse: {output}")
        self.assertIn("OVERDUE", output, "an overdue lock must say so")
        self.assertIn("will NOT be taken automatically", output)
        self.assertIsNotNone(lock.inspect(repo=repo),
                             "the holder's lock must survive the attempt")

    def test_a_vanishing_holder_cannot_defeat_the_timeout(self):
        """The retry path that skipped its own deadline.

        When the ref is gone at the moment we look, acquire loops to try again.
        That branch used to `continue` without checking the deadline or
        sleeping, so a ref that kept appearing and disappearing spun forever
        and the caller's timeout meant nothing. Forced here by making `inspect`
        always report no holder while the ref is genuinely held, so the
        update-ref keeps failing and the look keeps finding nothing.
        """
        repo = self.repo()
        blocker = lock.acquire(repo=repo, role="Holder Agent", operation="x")
        script = "\n".join([
            "import sys", "from unittest import mock",
            "sys.path.insert(0, sys.argv[1])", "import main_write_lock as lock",
            "lock._boot_stamp = lambda: 'unavailable: test fixture'",
            "with mock.patch.object(lock, 'inspect', return_value=None):",
            "    try:",
            "        lock.acquire(repo=sys.argv[2], role='Contender Agent', operation='y', timeout=0.3)",
            "    except lock.MainWriteLockError as error:",
            "        print(error)",
            "        sys.exit(0 if 'timed out acquiring' in str(error) else 2)",
            "sys.exit(3)",
        ])
        try:
            try:
                result = subprocess.run([sys.executable, "-B", "-c", script, str(HOST), str(repo)],
                                        capture_output=True, text=True, timeout=8)
            except subprocess.TimeoutExpired:
                self.fail("acquire must honour its timeout on EVERY retry path")
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        finally:
            found = lock.inspect(repo=repo)
            if found and found[0] == blocker.owner_oid:
                lock.release(blocker)

    def test_the_owner_blob_carries_an_identity_not_a_bare_pid(self):
        """A recycled pid makes a dead holder look live.

        Observed on this machine on 2026-09-22, inside five minutes under
        ordinary load. A recovery tool checking only the number would refuse to
        reclaim a genuinely abandoned lock. The field is never absent: when the
        identity cannot be captured it holds a string saying why, so absence
        cannot be read as a pass.
        """
        repo = self.repo()
        handle = lock.acquire(repo=repo, role="A Agent", operation="x")
        _, owner = lock.inspect(repo=repo)
        self.assertIn("process_identity", owner,
                      "the field must always be present")
        identity = owner["process_identity"]
        if os.name == "nt":
            self.assertIsInstance(identity, dict, "Windows identity must be captured in the tracked layout")
        if isinstance(identity, dict):
            self.assertEqual({"pid", "created_ticks", "image"}, set(identity),
                             "an identity must bind pid, creation and image")
            self.assertEqual(owner["pid"], identity["pid"])
        else:
            self.assertTrue(identity.startswith("unavailable:"),
                            f"an absent identity must say why: {identity!r}")
        lock.release(handle)

    def test_a_fresh_lock_is_not_reported_overdue(self):
        repo = self.repo()
        handle = lock.acquire(repo=repo, role="A Agent", operation="x")
        _, owner = lock.inspect(repo=repo)
        self.assertLess(lock.overdue_by(owner), 0,
                        "a just-taken lock must not read as overdue")
        lock.release(handle)

    def test_a_malformed_owner_blob_still_refuses(self):
        """Unreadable is not free."""
        repo = self.repo()
        oid = subprocess.run(["git", "-C", str(repo), "hash-object", "-w",
                              "--stdin"], input=b"not json at all",
                             capture_output=True,
                             creationflags=NO_WINDOW).stdout.decode().strip()
        git(repo, "update-ref", lock.LOCK_REF, oid, "")
        code, output = self.contend(repo)
        self.assertEqual(3, code, f"a malformed lock must refuse: {output}")


class OnlyTheHandleReleases(Base):
    def test_a_stale_handle_cannot_release_a_later_acquisition(self):
        """The defect a module-level 'who holds it' variable would have allowed.

        Also the one a duplicate `end()` in the GER callers would have caused:
        first release succeeds, someone else acquires, the second release from
        the same script drops THEIR lock.
        """
        repo = self.repo()
        first = lock.acquire(repo=repo, role="First Agent", operation="one")
        lock.release(first)
        second = lock.acquire(repo=repo, role="Second Agent", operation="two")

        lock.release(first)          # duplicate release of an old handle
        found = lock.inspect(repo=repo)
        self.assertIsNotNone(found, "the second holder's lock must survive")
        self.assertEqual(second.owner_oid, found[0])
        self.assertEqual("Second Agent", found[1]["role"])
        lock.release(second)

    def test_release_refuses_when_the_lock_was_recovered_from_under_it(self):
        """Reaches the compare-and-swap. The stale-handle case above does NOT.

        Mutation testing found that: removing the CAS from release left the
        stale-handle test passing, because a handle already marked released
        short-circuits before git is ever called. That case proves the
        bookkeeping, not the swap. Here the handle was never released --
        recovery displaced it -- so release must reach git and be refused.
        """
        repo = self.repo()
        crashed = lock.acquire(repo=repo, role="Ghost Agent", operation="x")
        taken = lock.recover(repo=repo, expected_owner_oid=crashed.owner_oid,
                             role="Operator Agent", reason="assumed dead",
                             termination_established=True)
        with self.assertRaises(lock.MainWriteLockError) as caught:
            lock.release(crashed)
        self.assertIn("no longer ours", str(caught.exception))
        self.assertEqual(taken.owner_oid, lock.inspect(repo=repo)[0],
                         "the recovering owner must keep the lock")
        lock.release(taken)

    def test_release_refuses_anything_that_is_not_a_handle(self):
        repo = self.repo()
        handle = lock.acquire(repo=repo, role="A Agent", operation="x")
        for impostor in ("A Agent", handle.owner_oid, None, {"role": "A Agent"}):
            with self.assertRaises(lock.MainWriteLockError):
                lock.release(impostor)
        self.assertIsNotNone(lock.inspect(repo=repo))
        lock.release(handle)

    def test_release_refuses_a_handle_from_another_repository(self):
        one, two = self.repo(), self.repo()
        handle = lock.acquire(repo=one, role="A Agent", operation="x")
        with self.assertRaises(lock.MainWriteLockError):
            lock.release(handle, repo=two)
        lock.release(handle)


class RecoveryIsExplicit(Base):
    def owner_of(self, repo):
        return lock.inspect(repo=repo)[0]

    def test_recovery_refuses_without_an_established_termination(self):
        repo = self.repo()
        handle = lock.acquire(repo=repo, role="Ghost Agent", operation="x")
        with self.assertRaises(lock.MainWriteLockError) as caught:
            lock.recover(repo=repo, expected_owner_oid=handle.owner_oid,
                         role="Operator Agent", reason="crashed",
                         termination_established=False)
        self.assertIn("establish that the holding writer", str(caught.exception))
        self.assertEqual(handle.owner_oid, self.owner_of(repo))

    def test_recovery_takes_the_exact_owner_it_inspected(self):
        repo = self.repo()
        crashed = lock.acquire(repo=repo, role="Ghost Agent", operation="x")
        handle = lock.recover(repo=repo, expected_owner_oid=crashed.owner_oid,
                              role="Operator Agent",
                              reason="pid gone, job object empty",
                              termination_established=True)
        owner_oid, owner = lock.inspect(repo=repo)
        self.assertEqual(handle.owner_oid, owner_oid)
        self.assertEqual(crashed.owner_oid,
                         owner["recovered_from"]["owner_oid"],
                         "recovery must record whose lock it took")
        lock.release(handle)

    def test_recovery_refuses_when_the_lock_changed_hands(self):
        """A recovery that races a legitimate release-and-reacquire must lose."""
        repo = self.repo()
        crashed = lock.acquire(repo=repo, role="Ghost Agent", operation="x")
        stale_oid = crashed.owner_oid
        lock.release(crashed)
        live = lock.acquire(repo=repo, role="Live Agent", operation="real work")

        with self.assertRaises(lock.MainWriteLockError) as caught:
            lock.recover(repo=repo, expected_owner_oid=stale_oid,
                         role="Operator Agent", reason="looked crashed",
                         termination_established=True)
        self.assertIn("changed hands", str(caught.exception))
        self.assertEqual(live.owner_oid, self.owner_of(repo),
                         "the live holder must be untouched")
        lock.release(live)


class TheRepositoryIsTheAuthority(Base):
    def test_repo_is_required_and_never_defaults(self):
        for bad in (None, ""):
            with self.assertRaises(lock.MainWriteLockError):
                lock.acquire(repo=bad, role="A Agent", operation="x")

    def test_a_clone_does_NOT_see_the_canonical_lock(self):
        """Pins the claim that was WRONG in the predecessor's own docstring.

        It said the lock "binds any tool from any clone". Independent clones
        have their own refs, and `refs/locks/*` is outside the default fetch
        refspec, so a clone sees nothing however hard it looks. What binds is
        addressing the same REPOSITORY. A tool that resolved the ref against
        its own clone would read a held lock as free.
        """
        canonical = self.repo()
        handle = lock.acquire(repo=canonical, role="Holder Agent",
                              operation="merge")

        clone = canonical.parent / "clone"
        subprocess.run(["git", "clone", "--quiet", str(canonical), str(clone)],
                       capture_output=True, creationflags=NO_WINDOW)
        git(clone, "fetch", "--all", "--quiet")

        self.assertEqual("", git(clone, "for-each-ref", lock.LOCK_REF),
                         "a clone must not see the canonical lock ref")
        self.assertIsNone(lock.inspect(repo=clone),
                          "inspecting the clone reads FREE while it is held")
        self.assertIsNotNone(lock.inspect(repo=canonical),
                             "and the canonical lock is genuinely held")
        lock.release(handle)

    def test_two_repositories_have_independent_locks(self):
        one, two = self.repo(), self.repo()
        first = lock.acquire(repo=one, role="A Agent", operation="x")
        second = lock.acquire(repo=two, role="B Agent", operation="y")
        self.assertIsNotNone(lock.inspect(repo=one))
        self.assertIsNotNone(lock.inspect(repo=two))
        lock.release(first)
        self.assertIsNone(lock.inspect(repo=one))
        self.assertIsNotNone(lock.inspect(repo=two),
                             "releasing one repo's lock must not touch another")
        lock.release(second)


class ReleaseAndGitFailures(Base):
    def obstruction(self, repo):
        path = repo / ".git/refs/locks/main-write.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture obstruction")
        return path

    def test_release_failure_is_visible_and_retryable(self):
        repo = self.repo()
        owner = lock.acquire(repo=repo, role="A Agent", operation="x")
        obstruction = self.obstruction(repo)
        with self.assertRaisesRegex(lock.MainWriteLockError, "still ours"):
            lock.release(owner)
        self.assertFalse(owner.is_released)
        self.assertEqual(owner.owner_oid, lock.inspect(repo=repo)[0])
        obstruction.unlink()
        lock.release(owner)
        self.assertTrue(owner.is_released)
        self.assertIsNone(lock.inspect(repo=repo))

    def test_held_does_not_hide_release_failure_or_original_error(self):
        repo = self.repo()
        with self.assertRaises(lock.MainWriteLockError) as caught:
            with lock.held(repo=repo, role="A Agent", operation="x") as owner:
                obstruction = self.obstruction(repo)
                raise ValueError("original operation failure")
        self.assertIsInstance(caught.exception.__context__, ValueError)
        obstruction.unlink()
        lock.release(owner)

    def test_acquire_reports_real_git_failure_without_fictional_owner(self):
        repo = self.repo()
        self.obstruction(repo)
        with self.assertRaisesRegex(lock.MainWriteLockError, "could not acquire") as caught:
            lock.acquire(repo=repo, role="A Agent", operation="x", timeout=0)
        self.assertNotIsInstance(caught.exception, lock.MainWriteLockBusy)
        self.assertIn("main-write.lock", str(caught.exception))

    def test_a_broken_ref_is_an_error_not_absence(self):
        repo = self.repo()
        path = repo / ".git/refs/locks/main-write"
        path.parent.mkdir(parents=True)
        path.write_text("not an object id")
        with self.assertRaisesRegex(lock.MainWriteLockError, "cannot inspect"):
            lock.inspect(repo=repo)

    def test_relative_acquisition_survives_cwd_change(self):
        one, two = self.repo(), self.repo()
        previous = pathlib.Path.cwd()
        try:
            os.chdir(one)
            owner = lock.acquire(repo=".", role="A Agent", operation="x")
            self.assertTrue(owner.repo.is_absolute())
            os.chdir(two)
            lock.release(owner)
        finally:
            os.chdir(previous)
        self.assertIsNone(lock.inspect(repo=one))

    def test_linked_worktrees_share_identity_and_contend(self):
        repo = self.repo()
        linked = repo.parent / "linked"
        git(repo, "worktree", "add", "-b", "linked", str(linked))
        owner = lock.acquire(repo=repo, role="A Agent", operation="x")
        with self.assertRaises(lock.MainWriteLockBusy):
            lock.acquire(repo=linked, role="B Agent", operation="y", timeout=0)
        lock.release(owner, repo=linked)
        self.assertIsNone(lock.inspect(repo=repo))

    def test_same_process_new_acquisition_has_a_fresh_nonce(self):
        repo = self.repo()
        a = lock.acquire(repo=repo, role="A Agent", operation="x")
        lock.release(a)
        b = lock.acquire(repo=repo, role="A Agent", operation="x")
        self.assertNotEqual(a.owner_oid, b.owner_oid)
        self.assertNotEqual(a.operation_id, b.operation_id)
        lock.release(b)


class RecoveryReportsAndChildren(Base):
    def test_uncertain_ref_children_report_the_possible_full_owner(self):
        repo = self.repo()
        real_git = lock._git
        def uncertain(target, *args, **kwargs):
            if args[0] == "update-ref":
                raise lock.MutationChildUncertain("fixture Git wait interrupted")
            return real_git(target, *args, **kwargs)
        with mock.patch.object(lock, "_git", side_effect=uncertain):
            with self.assertRaisesRegex(lock.MutationChildUncertain, r"acquisition may hold owner [0-9a-f]{40}"):
                lock.acquire(repo=repo, role="A Agent", operation="x")
        owner = lock.acquire(repo=repo, role="A Agent", operation="x")
        with mock.patch.object(lock, "_git", side_effect=uncertain):
            with self.assertRaisesRegex(lock.MutationChildUncertain, owner.owner_oid):
                lock.release(owner)
            with self.assertRaisesRegex(lock.MutationChildUncertain, r"recovery replacement may hold owner [0-9a-f]{40}"):
                lock.recover(repo=repo, role="Recovery Agent", expected_owner_oid=owner.owner_oid,
                             reason="fixture", termination_established=True)
        self.assertFalse(owner.is_released)
        self.assertEqual(owner.owner_oid, lock.inspect(repo=repo)[0])
        lock.release(owner)

    def test_killed_fixture_owner_requires_explicit_recovery(self):
        repo = self.repo()
        script = ("import sys; sys.path.insert(0,sys.argv[1]); import main_write_lock as lock; "
                  "lock._boot_stamp=lambda:'unavailable: test fixture'; "
                  "h=lock.acquire(repo=sys.argv[2],role='Fixture Agent',operation='fixture'); "
                  "print(h.owner_oid,flush=True); sys.stdin.readline()")
        child = subprocess.Popen([sys.executable, "-B", "-c", script, str(HOST), str(repo)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            token = child.stdout.readline().strip()
            self.assertEqual(token, lock.inspect(repo=repo)[0])
            # At READY all Git children completed; this fixture starts no more.
            child.kill()
            child.communicate(timeout=10)
            self.assertIsNotNone(child.returncode)
            with self.assertRaises(lock.MainWriteLockBusy):
                lock.acquire(repo=repo, role="Next Agent", operation="y", timeout=0)
            lock.recover_and_report(repo=repo, expected_owner_oid=token,
                role="Recovery Agent", reason="fixture process and all children stopped",
                termination_established=True, report=repo.parent / "killed-owner.json")
            self.assertIsNone(lock.inspect(repo=repo))
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)

    def test_recovery_rejects_blank_role_and_abbreviated_oid(self):
        repo = self.repo()
        owner = lock.acquire(repo=repo, role="A Agent", operation="x")
        for role, oid in (("  ", owner.owner_oid), ("B Agent", owner.owner_oid[:12])):
            with self.assertRaises(lock.MainWriteLockError):
                lock.recover(repo=repo, expected_owner_oid=oid, role=role,
                             reason="fixture", termination_established=True)
        self.assertEqual(owner.owner_oid, lock.inspect(repo=repo)[0])
        lock.release(owner)

    def test_recovery_checks_cas_after_python_inspection(self):
        repo = self.repo()
        old = lock.acquire(repo=repo, role="A Agent", operation="x")
        real_write = lock._write_owner_blob
        replacement = []
        def change_after_inspect(target, body):
            lock.release(old)
            replacement.append(lock.acquire(repo=repo, role="B Agent", operation="y"))
            return real_write(target, body)
        with mock.patch.object(lock, "_write_owner_blob", side_effect=change_after_inspect):
            # Avoid recursively intercepting the replacement acquire.
            def once(target, body):
                with mock.patch.object(lock, "_write_owner_blob", side_effect=real_write):
                    return change_after_inspect(target, body)
            with mock.patch.object(lock, "_write_owner_blob", side_effect=once):
                with self.assertRaisesRegex(lock.MainWriteLockError, "compare-and-swap"):
                    lock.recover(repo=repo, expected_owner_oid=old.owner_oid,
                                 role="Recovery Agent", reason="fixture", termination_established=True)
        self.assertEqual(replacement[0].owner_oid, lock.inspect(repo=repo)[0])
        lock.release(replacement[0])

    def test_recovery_report_preserves_dirty_and_in_progress_state(self):
        repo = self.repo()
        owner = lock.acquire(repo=repo, role="A Agent", operation="x")
        (repo / "base.txt").write_text("dirty")
        (repo / ".git/MERGE_HEAD").write_text(git(repo, "rev-parse", "HEAD") + "\n")
        report = repo.parent / "recovery.json"
        state = lock.recover_and_report(repo=repo, expected_owner_oid=owner.owner_oid,
            role="Recovery Agent", reason="fixture owner settled", termination_established=True,
            report=report)
        self.assertIn("base.txt", state["status"])
        self.assertIn("MERGE_HEAD", state["in_progress"])
        self.assertEqual("dirty", (repo / "base.txt").read_text())
        self.assertIsNone(lock.inspect(repo=repo))
        self.assertEqual(state, json.loads(report.read_text()))

    def test_failed_recovery_recording_retains_new_token(self):
        repo = self.repo()
        owner = lock.acquire(repo=repo, role="A Agent", operation="x")
        with self.assertRaisesRegex(lock.MainWriteLockError, "retained recovery owner"):
            lock.recover_and_report(repo=repo, expected_owner_oid=owner.owner_oid,
                role="Recovery Agent", reason="fixture", termination_established=True,
                report=repo.parent / "absent" / "report.json")
        found = lock.inspect(repo=repo)
        self.assertNotEqual(owner.owner_oid, found[0])
        self.assertEqual("Recovery Agent", found[1]["role"])

    def test_uncertain_child_keeps_owner(self):
        repo = self.repo()
        with self.assertRaisesRegex(lock.MutationChildUncertain, "retained"):
            with lock.held(repo=repo, role="A Agent", operation="x") as owner:
                raise lock.MutationChildUncertain("fixture child still running")
        found = lock.inspect(repo=repo)
        self.assertIsNotNone(found, "uncertain mutation must retain ownership")
        self.assertEqual(owner.owner_oid, found[0])
        lock.release(owner)  # synthetic child has no actual process

    def test_process_wrapper_marks_interrupted_mutation_child(self):
        child = mock.Mock(pid=123, args=["fake"], returncode=None)
        child.communicate.side_effect = KeyboardInterrupt()
        with mock.patch.object(lock.subprocess, "Popen", return_value=child):
            with self.assertRaisesRegex(lock.MutationChildUncertain, "child 123"):
                lock.run_process(["fake"])
        child.kill.assert_not_called()

    def test_process_identity_unavailable_and_available_paths(self):
        with mock.patch.object(lock, "_identity_provider", side_effect=ImportError("fixture deployment has no Pipeline")):
            self.assertTrue(lock._process_identity().startswith("unavailable:"))
        module = mock.Mock()
        module.identify.return_value = {"pid": os.getpid(), "created_ticks": "1", "image": "python"}
        with mock.patch.object(lock, "_identity_provider", return_value=module):
            self.assertEqual(module.identify.return_value, lock._process_identity())

    @unittest.skipUnless(os.name == "nt", "maintained identity implementation requires Windows")
    def test_deployed_layout_captures_real_process_identity(self):
        import shutil
        with tempfile.TemporaryDirectory(prefix="deployed-lock-identity-") as tmp:
            workspace = pathlib.Path(tmp)
            tools = workspace / "tools"
            tools.mkdir()
            for name in ("main_write_lock.py", "nsc_paths.py"):
                shutil.copy2(HOST / name, tools / name)
            source = HOST.parents[1] / "Pipeline/AssistantControl/process_identity.py"
            target = workspace / "NSC/NoSafeCircle/Pipeline/AssistantControl/process_identity.py"
            target.parent.mkdir(parents=True)
            shutil.copy2(source, target)
            result = subprocess.run([sys.executable, "-B", "-c",
                "import json, main_write_lock; print(json.dumps(main_write_lock._process_identity()))"],
                cwd=tools, capture_output=True, text=True, timeout=10)
            self.assertEqual(0, result.returncode, result.stderr)
            identity = json.loads(result.stdout)
            self.assertIsInstance(identity, dict, result.stdout)
            self.assertEqual({"pid", "created_ticks", "image"}, set(identity))


class OwnerProcessDiagnostics(Base):
    def owner(self):
        return {"host": "fixture-host", "pid": 23,
                "process_identity": {"pid": 23, "created_ticks": 100, "image": "fixture.exe"}}

    def test_exact_same_host_identity_reports_alive_or_gone(self):
        for matched, expected in ((True, "alive"), (False, "gone")):
            with self.subTest(matched=matched):
                query = mock.Mock(return_value=matched)
                owner = self.owner()
                self.assertEqual(expected, lock.owner_process_status(owner, hostname="FIXTURE-HOST", matches=query))
                query.assert_called_once_with(owner["process_identity"])

    def test_foreign_malformed_or_unavailable_identity_never_queries(self):
        examples = [None, {}, {**self.owner(), "host": "foreign-host"},
                    {**self.owner(), "host": ""}, {**self.owner(), "pid": True},
                    {**self.owner(), "pid": 24}]
        for identity in ("unavailable: fixture", None, {},
                         {"pid": 23, "created_ticks": 100, "image": "fixture.exe", "extra": 1},
                         {"pid": 23, "created_ticks": 100},
                         {"pid": 0, "created_ticks": 100, "image": "fixture.exe"},
                         {"pid": True, "created_ticks": 100, "image": "fixture.exe"},
                         {"pid": 23, "created_ticks": 0, "image": "fixture.exe"},
                         {"pid": 23, "created_ticks": True, "image": "fixture.exe"},
                         {"pid": 23, "created_ticks": "100", "image": "fixture.exe"},
                         {"pid": 23, "created_ticks": 100, "image": " "}):
            examples.append({**self.owner(), "process_identity": identity})
        for owner in examples:
            with self.subTest(owner=owner):
                query = mock.Mock(return_value=False)
                self.assertEqual("unknown", lock.owner_process_status(owner, hostname="fixture-host", matches=query))
                query.assert_not_called()

    def test_query_errors_and_non_boolean_results_are_unknown(self):
        for value in (None, 0, 1, "alive", {}, []):
            self.assertEqual("unknown", lock.owner_process_status(
                self.owner(), hostname="fixture-host", matches=mock.Mock(return_value=value)))
        for error in (OSError("denied"), ValueError("invalid"), SyntaxError("broken module")):
            self.assertEqual("unknown", lock.owner_process_status(
                self.owner(), hostname="fixture-host", matches=mock.Mock(side_effect=error)))
            with mock.patch.object(lock, "_identity_provider", side_effect=error):
                self.assertEqual("unknown", lock.owner_process_status(self.owner(), hostname="fixture-host"))

    def test_identity_capture_provider_and_query_errors_are_diagnostic(self):
        for error in (SyntaxError("broken checkout module"), RuntimeError("fixture query failure")):
            with mock.patch.object(lock, "_identity_provider", side_effect=error):
                self.assertIn("unavailable:", lock._process_identity())
            provider = mock.Mock()
            provider.identify.side_effect = error
            with mock.patch.object(lock, "_identity_provider", return_value=provider):
                self.assertIn("unavailable:", lock._process_identity())

    def test_diagnostics_do_not_swallow_process_interruption(self):
        with mock.patch.object(lock, "_identity_provider", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                lock._process_identity()
        with self.assertRaises(KeyboardInterrupt):
            lock.owner_process_status(self.owner(), hostname="fixture-host",
                                      matches=mock.Mock(side_effect=KeyboardInterrupt))

    def test_busy_description_and_inspect_cli_consume_identity_without_recovery(self):
        repo = self.repo()
        owner = self.owner()
        owner["host"] = lock.socket.gethostname()
        oid = self.plant(repo, owner)
        provider = mock.Mock()
        provider.matches.return_value = False
        output, diagnostic = io.StringIO(), io.StringIO()
        with mock.patch.object(lock, "_identity_provider", return_value=provider):
            text = lock.MainWriteLockBusy(owner, oid, 120).describe()
            self.assertIn("owner process: gone", text)
            self.assertIn("child termination is not established", text)
            self.assertNotIn("is still writing", text)
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(diagnostic):
                self.assertEqual(0, lock.main(["inspect", "--repo", str(repo)]))
        self.assertEqual([oid, owner], json.loads(output.getvalue()))
        self.assertIn("owner process: gone", diagnostic.getvalue())
        self.assertIn("explicit recovery still required", diagnostic.getvalue())
        self.assertEqual(oid, lock.inspect(repo=repo)[0])
        provider.matches.assert_called_with(owner["process_identity"])


def startup_stamp(start="2026-09-18T11:02:36.5000000Z", record=10, host="fixture-host"):
    return {"source": lock.BOOT_SOURCE, "computer": host, "channel": "System",
            "provider": "Microsoft-Windows-Kernel-General", "record_id": record,
            "start_time_utc": start}


def epoch(text):
    return lock.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


class StartupEvidence(unittest.TestCase):
    def response(self, stamp):
        data = {k: v for k, v in stamp.items() if k != "source"}
        return subprocess.CompletedProcess([], 0, json.dumps(data), "")

    def test_provider_selects_only_newest_startup_and_validates_local_response(self):
        stamp = startup_stamp()
        with mock.patch.object(lock.os, "name", "nt"), \
                mock.patch.object(lock.socket, "gethostname", return_value="FIXTURE-HOST"), \
                mock.patch.object(lock.subprocess, "run", return_value=self.response(stamp)) as run:
            self.assertEqual(stamp, lock._boot_stamp())
        command = run.call_args.args[0]
        self.assertIn("-NoProfile", command)
        self.assertIn("-NonInteractive", command)
        self.assertIn('$PSHOME/Modules/Microsoft.PowerShell.Diagnostics/', command[-1])
        self.assertIn("Id=12", command[-1])
        self.assertIn("-MaxEvents 1", command[-1])
        self.assertIn(".ToXml()", command[-1])
        self.assertIn("StartTime", command[-1])
        self.assertNotIn("Message", command[-1])
        self.assertEqual(15, run.call_args.kwargs["timeout"])

    def test_invalid_foreign_and_hibernation_events_are_unavailable(self):
        bad = [None, [], {}, {k: v for k, v in startup_stamp().items() if k != "record_id"}]
        for key, value in (("computer", "foreign"), ("channel", "Application"),
                           ("provider", "Microsoft-Windows-Power-Troubleshooter"),
                           ("record_id", True), ("record_id", 0), ("record_id", "10"),
                           ("start_time_utc", "2026-09-23T01:00:00"),
                           ("start_time_utc", "2026-09-23T01:00:00+02:00"),
                           ("start_time_utc", ["2026-09-23T01:00:00Z"]),
                           ("start_time_utc", "2026-02-30T01:00:00Z")):
            bad.append({**startup_stamp(), key: value})
        for item in bad:
            raw = {k: v for k, v in item.items() if k != "source"} if isinstance(item, dict) else item
            with self.subTest(raw=raw), mock.patch.object(lock.os, "name", "nt"), \
                    mock.patch.object(lock.socket, "gethostname", return_value="fixture-host"), \
                    mock.patch.object(lock.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(raw), "")):
                self.assertTrue(lock._boot_stamp().startswith("unavailable:"))

    def test_query_timeout_errors_and_non_windows_do_not_fallback(self):
        with mock.patch.object(lock.os, "name", "nt"):
            for error in (subprocess.TimeoutExpired("fixture", 15), OSError("denied"), ValueError("bad XML-derived JSON")):
                with mock.patch.object(lock.subprocess, "run", side_effect=error) as run:
                    self.assertTrue(lock._boot_stamp().startswith("unavailable:"))
                    run.assert_called_once()
            for result in (subprocess.CompletedProcess([], 1, "", "event access denied"),
                           subprocess.CompletedProcess([], 0, "not JSON", "")):
                with mock.patch.object(lock.subprocess, "run", return_value=result):
                    self.assertTrue(lock._boot_stamp().startswith("unavailable:"))
        with mock.patch.object(lock.os, "name", "posix"), mock.patch.object(lock.subprocess, "run") as run:
            self.assertTrue(lock._boot_stamp().startswith("unavailable:"))
            run.assert_not_called()

    def test_fractional_start_time_is_preserved_without_float_rounding(self):
        from decimal import Decimal
        stamp = startup_stamp("2026-09-23T00:00:00.1234567Z")
        self.assertEqual(Decimal(int(epoch("2026-09-23T00:00:00Z"))) + Decimal("0.1234567"),
                         lock._boot_time(stamp, "fixture-host"))
        self.assertIsNone(lock._boot_time({**stamp, "start_time_utc": "2026-09-23T00:00:00.12345678Z"}, "fixture-host"))


class RebootPredicate(unittest.TestCase):
    def owner(self):
        return {"host": "FIXTURE-HOST", "acquired_epoch": epoch("2026-09-22T00:00:00Z"),
                "boot_stamp": startup_stamp()}

    def current(self):
        return startup_stamp("2026-09-23T00:00:00Z", 11)

    def proof(self, owner=None, current=None, now=None):
        return lock.reboot_recovery_proof(self.owner() if owner is None else owner,
            self.current() if current is None else current, hostname="fixture-host",
            now=epoch("2026-09-23T01:00:00Z") if now is None else now)

    def test_only_a_later_startup_after_acquisition_produces_proof(self):
        proof = self.proof()
        self.assertIsNotNone(proof)
        self.assertEqual(self.owner(), proof["old_owner"])
        self.assertEqual(self.current(), proof["current_boot_stamp"])
        self.assertEqual("fixture-host", proof["local_host"])

    def test_same_boot_hibernation_and_clock_jumps_never_prove_reboot(self):
        for now in (epoch("2026-09-23T01:00:00Z"), epoch("2030-01-01T00:00:00Z"), epoch("2020-01-01T00:00:00Z")):
            self.assertIsNone(self.proof(current=startup_stamp(), now=now))
            self.assertIsNone(self.proof(current=startup_stamp(record=900), now=now))
        self.assertIsNone(self.proof(owner={**self.owner(), "acquired_epoch": epoch("2026-09-17T00:00:00Z")}))
        self.assertIsNone(self.proof(now=epoch("2026-09-22T23:59:59Z")))
        self.assertIsNone(self.proof(owner={**self.owner(), "acquired_epoch": epoch("2026-09-23T00:00:00Z")}))

    def test_foreign_legacy_malformed_and_unknown_metadata_remains_manual(self):
        for field, value in (("host", "foreign"), ("host", ""), ("host", None),
                             ("boot_stamp", None), ("boot_stamp", "unavailable: fixture"),
                             ("boot_stamp", {}), ("acquired_epoch", True), ("acquired_epoch", -1),
                             ("acquired_epoch", "123"), ("acquired_epoch", float("nan")),
                             ("acquired_epoch", float("inf"))):
            with self.subTest(field=field, value=value):
                self.assertIsNone(self.proof(owner={**self.owner(), field: value}))
        for stamp in ({}, "unavailable: query failed", {**self.current(), "source": "WMI"},
                      {**self.current(), "record_id": False}, {**self.current(), "extra": 1}):
            self.assertIsNone(self.proof(current=stamp))


class AutomaticRebootRecovery(Base):
    def stamps(self):
        host = lock.socket.gethostname()
        return startup_stamp(host=host), startup_stamp("2026-09-23T00:00:00Z", 11, host)

    def old_owner(self, repo, **changes):
        old, _ = self.stamps()
        owner = {"host": lock.socket.gethostname(), "role": "Previous Agent", "boot_stamp": old,
                 "acquired_epoch": epoch("2026-09-22T00:00:00Z")}
        owner.update(changes)
        return self.plant(repo, owner)

    def acquire(self, repo):
        return lock.acquire(repo=repo, role="Next Agent", operation="new request", timeout=0)

    def test_new_owner_captures_one_startup_query(self):
        repo = self.repo()
        _, current = self.stamps()
        with mock.patch.object(lock, "_boot_stamp", return_value=current) as query:
            owner = self.acquire(repo)
        self.assertEqual(current, lock.inspect(repo=repo)[1]["boot_stamp"])
        query.assert_called_once()
        lock.release(owner)

    def test_reboot_records_and_releases_without_entering_business_or_repairing(self):
        repo = self.repo()
        token = self.old_owner(repo)
        _, current = self.stamps()
        head = git(repo, "rev-parse", "HEAD")
        (repo / "base.txt").write_text("staged change")
        git(repo, "add", "base.txt")
        (repo / "base.txt").write_text("unstaged change")
        (repo / ".git/MERGE_HEAD").write_text(head + "\n")
        index = git(repo, "diff", "--cached", "--binary")
        status = git(repo, "status", "--porcelain=v1")
        with mock.patch.object(lock, "_boot_stamp", return_value=current) as query:
            with self.assertRaises(lock.MainWriteLockRecovered) as caught:
                with lock.held(repo=repo, role="Next Agent", operation="must not run", timeout=0):
                    self.fail("automatic recovery must end admission before business body")
        query.assert_called_once()
        self.assertIsNone(lock.inspect(repo=repo))
        report = json.loads(caught.exception.report_path.read_text())
        self.assertEqual((repo / ".git/nsc-main-write-recovery").resolve(), caught.exception.report_path.parent)
        self.assertEqual(token, report["reboot_recovery_proof"]["old_owner_oid"])
        self.assertEqual(current, report["reboot_recovery_proof"]["current_boot_stamp"])
        self.assertEqual(head, report["head"])
        self.assertIn("base.txt", report["index"])
        self.assertIn("MERGE_HEAD", report["in_progress"])
        self.assertEqual(head, git(repo, "rev-parse", "HEAD"))
        self.assertEqual(index, git(repo, "diff", "--cached", "--binary"))
        self.assertEqual(status, git(repo, "status", "--porcelain=v1"))
        with mock.patch.object(lock, "_boot_stamp", return_value=current):
            fresh = self.acquire(repo)  # fresh caller must still apply its normal business preconditions
        lock.release(fresh)

    def test_same_boot_foreign_and_legacy_keep_the_exact_token(self):
        for changes, use_current in (({}, False), ({"host": "foreign"}, True), ({"boot_stamp": None}, True)):
            with self.subTest(changes=changes, use_current=use_current):
                repo = self.repo()
                token = self.old_owner(repo, **changes)
                old, current = self.stamps()
                with mock.patch.object(lock, "_boot_stamp", return_value=current if use_current else old):
                    with self.assertRaises(lock.MainWriteLockBusy):
                        self.acquire(repo)
                self.assertEqual(token, lock.inspect(repo=repo)[0])
                self.assertFalse((repo / ".git/nsc-main-write-recovery").exists())

    def test_recovery_race_does_not_clear_a_changed_owner(self):
        repo = self.repo()
        old_token = self.old_owner(repo)
        _, current = self.stamps()
        real_write = lock._write_owner_blob
        replacement = []
        def racing_write(target, body):
            result = real_write(target, body)
            if "recovered_from" in body:
                live = real_write(target, {"host": lock.socket.gethostname(), "boot_stamp": current,
                    "acquired_epoch": time.time(), "role": "Live Agent"})
                git(repo, "update-ref", lock.LOCK_REF, live, old_token)
                replacement.append(live)
            return result
        with mock.patch.object(lock, "_boot_stamp", return_value=current), \
                mock.patch.object(lock, "_write_owner_blob", side_effect=racing_write):
            with self.assertRaisesRegex(lock.MainWriteLockError, "compare-and-swap"):
                self.acquire(repo)
        self.assertEqual(replacement[0], lock.inspect(repo=repo)[0])

    def test_report_failure_retains_fresh_recovery_owner_and_startup_evidence(self):
        repo = self.repo()
        old_token = self.old_owner(repo)
        _, current = self.stamps()
        with mock.patch.object(lock, "_boot_stamp", return_value=current) as query, \
                mock.patch.object(lock.os, "fsync", side_effect=OSError("fixture disk failure")):
            with self.assertRaisesRegex(lock.MainWriteLockError, "retained recovery owner"):
                self.acquire(repo)
        query.assert_called_once()
        token, owner = lock.inspect(repo=repo)
        self.assertNotEqual(old_token, token)
        self.assertEqual(current, owner["boot_stamp"])
        self.assertFalse(owner["termination_established_by_caller"])
        self.assertEqual(old_token, owner["reboot_recovery_proof"]["old_owner_oid"])
        with mock.patch.object(lock, "_boot_stamp", return_value=current):
            with self.assertRaises(lock.MainWriteLockBusy):
                self.acquire(repo)
        self.assertEqual(token, lock.inspect(repo=repo)[0])

    def test_uncertain_recovery_release_is_not_reclassified_as_ordinary_failure(self):
        repo = self.repo()
        old_token = self.old_owner(repo)
        _, current = self.stamps()
        with mock.patch.object(lock, "_boot_stamp", return_value=current), \
                mock.patch.object(lock, "release", side_effect=lock.MutationChildUncertain("fixture release child unsettled")):
            with self.assertRaisesRegex(lock.MutationChildUncertain, "retained recovery owner"):
                self.acquire(repo)
        token, owner = lock.inspect(repo=repo)
        self.assertNotEqual(old_token, token)
        self.assertEqual(old_token, owner["recovered_from"]["owner_oid"])
        self.assertEqual(1, len(list((repo / ".git/nsc-main-write-recovery").glob("*.json"))))


class TransitionalLegacyWarnings(unittest.TestCase):
    def test_recent_legacy_warns_but_uuid_and_ended_records_do_not(self):
        from datetime import datetime, timezone
        now = datetime(2026, 9, 23, 2, 10, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory(prefix="legacy-writer-warning-") as tmp:
            journal = pathlib.Path(tmp) / "journal.md"
            journal.write_text("\n".join([
                "- 2026-09-23 01:00 UTC MAIN-WRITE START Old Agent: ancient",
                "- 2026-09-23 02:00 UTC MAIN-WRITE START Legacy Agent: active",
                "- 2026-09-23 02:01:01 UTC MAIN-WRITE START New Agent: new; operation 12345678-1234-1234-1234-123456789abc. detail",
                "- 2026-09-23 02:02 UTC MAIN-WRITE START Ended Agent: old",
                "- 2026-09-23 02:03 UTC MAIN-WRITE END Ended Agent: done",
                "- 2026-09-23 02:04 UTC MAIN-WRITE START Ger Agent: old",
                "- MAIN-WRITE END Ger Agent: done",
            ]), encoding="utf-8")
            output = io.StringIO()
            lock.warn_legacy_writers(journal, now=now, stream=output)
            self.assertIn("Legacy Agent", output.getvalue())
            for quiet in ("Old Agent", "New Agent", "Ended Agent", "Ger Agent"):
                self.assertNotIn(quiet, output.getvalue())

    def test_unreadable_journal_warns_honestly(self):
        output = io.StringIO()
        with mock.patch.object(pathlib.Path, "read_text", side_effect=PermissionError("fixture denied")):
            lock.warn_legacy_writers("fixture.md", stream=output)
        self.assertIn("could not be read", output.getvalue())
        self.assertIn("fixture denied", output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
