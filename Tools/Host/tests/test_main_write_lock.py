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
        started = time.monotonic()
        with mock.patch.object(lock, "inspect", return_value=None):
            with self.assertRaises(lock.MainWriteLockBusy):
                lock.acquire(repo=repo, role="Contender Agent",
                             operation="y", timeout=0.3)
        self.assertLess(time.monotonic() - started, 15,
                        "acquire must honour its timeout on EVERY retry path")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
