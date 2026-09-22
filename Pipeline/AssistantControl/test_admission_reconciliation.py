"""Reconciling an admission reservation that no settlement can reach.

Every case builds a throwaway source repository and checkout root; nothing here
reads or writes the live registry.

The liveness cases use THIS process's own identity where they can, rather than a
stub, because the defect being guarded against is a proof that cannot fail. A
stubbed "alive" only proves the branch is reachable; ``process_identity.matches``
against a real running process proves the probe itself answers.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from Pipeline.AssistantControl import (
    admission, admission_reconciliation, docker_workers, process_identity,
    windows_job, worker_launcher)
from Pipeline.AssistantControl.admission import (
    _read_registry, _registry_identity, _source_registry_paths)
from Pipeline.AssistantControl.admission_reconciliation import (
    AdmissionReconciliationError, reconcile_admission)
from Pipeline.AssistantControl.checkouts import Checkouts

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LF = chr(10)
RUN = "task-orch-nsc999-20260918-2"
LEASE = "task-orch-nsc999-20260918b"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, creationflags=NO_WINDOW)


class Base(unittest.TestCase):
    def build(self, *, reservations=None, record=None, controller=None):
        root = Path(tempfile.mkdtemp(prefix="admission-reconcile-"))
        self.addCleanup(self._cleanup, root)
        source = root / "source"
        source.mkdir()
        _git(source, "init", "-b", "main")
        _git(source, "config", "user.email", "fixture@nosafecircle.invalid")
        _git(source, "config", "user.name", "Fixture")
        (source / "base.txt").write_text("base", encoding="utf-8")
        _git(source, "add", "base.txt")
        _git(source, "commit", "-m", "base", "--no-gpg-sign")

        checkouts = Checkouts(source, root / "checkouts")
        checkouts.records.mkdir(parents=True, exist_ok=True)

        _, registry_path = _source_registry_paths(checkouts.source)
        if reservations is None:
            reservations = [self.reservation(checkouts)]
        registry_path.write_text(json.dumps({
            "schema_version": admission.REGISTRY_SCHEMA,
            "source": _registry_identity(registry_path),
            "reservations": reservations,
        }), encoding="utf-8")

        if record is not None:
            (checkouts.records / f"{record['task_id']}.json").write_text(
                json.dumps(record), encoding="utf-8")
        if controller is not None:
            (checkouts.records / "graph-controller.json").write_text(
                json.dumps(controller), encoding="utf-8")
        return checkouts

    @staticmethod
    def _cleanup(root: Path) -> None:
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    @staticmethod
    def reservation(checkouts: Checkouts, *, task_id="NSC-999", run_id=RUN,
                    lease_id=LEASE, resources=("assets/a.cs",)):
        return {
            "schema_version": admission.REGISTRY_SCHEMA, "status": "active",
            "source": str(checkouts.source), "task_id": task_id,
            "run_id": run_id, "lease_id": lease_id,
            "checkout_root": str(checkouts.root),
            "checkout": str(checkouts.root / task_id),
            "source_head": "0" * 40, "task_contract_sha256": "a" * 64,
            "plan_id": "scope-" + "b" * 8, "plan": {},
            "resources": list(resources), "dependency_inspection": {},
            "resource_overlap_authorized": False, "overlap_with": [],
        }

    def reservations_now(self, checkouts: Checkouts) -> list[dict]:
        _, registry_path = _source_registry_paths(checkouts.source)
        return _read_registry(registry_path, checkouts.source)["reservations"]

    def make_run_root(self, checkouts: Checkouts, task_id: str, run_id: str,
                      identity=None) -> Path:
        run_root = admission_reconciliation.run_root_for(
            checkouts.records, task_id, run_id)
        run_root.mkdir(parents=True, exist_ok=True)
        if identity is not None:
            (run_root / "child.identity.json").write_text(
                json.dumps({"run_id": run_id, "process_identity": identity}),
                encoding="utf-8")
        return run_root

    @staticmethod
    def dead_identity() -> dict:
        """A real process identity whose process has since exited.

        Not fabricated. ``process_identity.identify`` RAISES for a pid it
        cannot open -- pid 4, the Windows System process, does exactly that --
        and this module deliberately treats an identity it cannot evaluate as
        live. A made-up identity would therefore exercise the refusal path
        while appearing to test the release path.
        """
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 creationflags=NO_WINDOW)
        try:
            identity = process_identity.identify(child.pid)
            assert identity is not None, "the spawned child must be identifiable"
        finally:
            child.terminate()
            child.wait(timeout=30)
        assert process_identity.matches(identity) is False, (
            "the fixture must hand back an identity that is genuinely dead")
        return identity

    @staticmethod
    def no_containers():
        return mock.patch.object(docker_workers, "inventory",
                                 lambda checkout, worker, **kw: [])


class TheDerivationsMatchTheLauncher(Base):
    def test_run_root_matches_the_launchers_own_derivation(self):
        """Pins the duplication this module documents.

        ``run_root_for`` deliberately re-derives rather than importing the
        launcher. If the launcher ever changes its layout, the absence proof
        would start reading a directory that is never created -- and would then
        release every reservation it was asked about.
        """
        checkouts = self.build()
        self.assertEqual(
            worker_launcher._run_root(checkouts, "NSC-999", RUN),
            admission_reconciliation.run_root_for(
                checkouts.records, "NSC-999", RUN))

    def test_job_name_matches_the_launchers_own_derivation(self):
        checkouts = self.build()
        run_root = worker_launcher._run_root(checkouts, "NSC-999", RUN)
        import hashlib
        self.assertEqual(
            "assistant-job-" + hashlib.sha256(str(run_root).encode()).hexdigest(),
            admission_reconciliation.job_name_for(run_root))


class ANeverLaunchedReservationIsReleased(Base):
    def test_dry_run_reports_but_writes_nothing(self):
        checkouts = self.build()
        with self.no_containers():
            result = reconcile_admission(checkouts, "NSC-999")
        self.assertTrue(result["would_release"])
        self.assertFalse(result["applied"])
        self.assertIn("never launched", result["basis"])
        self.assertEqual(1, len(self.reservations_now(checkouts)),
                         "a dry run must not remove the reservation")

    def test_apply_releases_the_exact_reservation(self):
        checkouts = self.build()
        with self.no_containers():
            result = reconcile_admission(checkouts, "NSC-999", apply=True)
        self.assertTrue(result["released"])
        self.assertEqual([], self.reservations_now(checkouts))

    def test_only_the_named_reservation_is_removed(self):
        """The case that catches releasing the wrong claim."""
        checkouts = self.build()
        other = self.reservation(checkouts, task_id="NSC-998",
                                 run_id="other-run", lease_id="other-lease",
                                 resources=("assets/b.cs",))
        _, registry_path = _source_registry_paths(checkouts.source)
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["reservations"].append(other)
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        with self.no_containers():
            reconcile_admission(checkouts, "NSC-999", apply=True)
        remaining = self.reservations_now(checkouts)
        self.assertEqual(1, len(remaining))
        self.assertEqual("NSC-998", remaining[0]["task_id"])

    def test_a_launched_run_whose_process_is_gone_is_released(self):
        """The other accepted basis: it ran, and it ended."""
        checkouts = self.build()
        self.make_run_root(checkouts, "NSC-999", RUN,
                           identity=self.dead_identity())
        with self.no_containers():
            result = reconcile_admission(checkouts, "NSC-999", apply=True)
        self.assertIn("launched and ended", result["basis"])
        self.assertEqual([], self.reservations_now(checkouts))


class ALiveRunIsRefused(Base):
    def test_a_live_recorded_identity_refuses(self):
        """Probed against a real running process: this test's own.

        Not a stub. ``process_identity.matches`` compares creation ticks and
        image as well as pid, so a fabricated identity would be reported dead
        and this case would pass while proving nothing.
        """
        checkouts = self.build()
        mine = process_identity.identify(os.getpid())
        self.assertIsNotNone(mine, "this process must be identifiable")
        self.make_run_root(checkouts, "NSC-999", RUN, identity=mine)
        with self.no_containers():
            with self.assertRaises(AdmissionReconciliationError) as caught:
                reconcile_admission(checkouts, "NSC-999", apply=True)
        self.assertIn("still live", str(caught.exception))
        self.assertEqual(1, len(self.reservations_now(checkouts)),
                         "a refused reconciliation must not release anything")

    def test_an_identity_that_cannot_be_queried_refuses(self):
        """Unknown is not dead, and this is the pid that proves it.

        pid 4 is the Windows System process: OpenProcess returns
        ACCESS_DENIED, so ``matches`` raises rather than answering. Treating
        that as "not alive" would turn every inaccessible worker into a
        releasable one.
        """
        checkouts = self.build()
        self.make_run_root(checkouts, "NSC-999", RUN,
                           identity={"pid": 4, "created_ticks": 1,
                                     "image": "c:/nothing.exe"})
        with self.no_containers():
            with self.assertRaises(AdmissionReconciliationError) as caught:
                reconcile_admission(checkouts, "NSC-999", apply=True)
        self.assertIn("unverifiable", str(caught.exception))
        self.assertEqual(1, len(self.reservations_now(checkouts)))

    def test_an_active_job_object_refuses(self):
        checkouts = self.build()
        with self.no_containers(), mock.patch.object(
                windows_job, "active_count", lambda name: 3):
            with self.assertRaises(AdmissionReconciliationError) as caught:
                reconcile_admission(checkouts, "NSC-999", apply=True)
        self.assertIn("3 process(es) are alive", str(caught.exception))
        self.assertEqual(1, len(self.reservations_now(checkouts)))

    def test_an_unqueryable_job_object_refuses(self):
        """Unknown is not dead."""
        def boom(name):
            raise windows_job.WindowsJobError("no handle")

        checkouts = self.build()
        with self.no_containers(), mock.patch.object(
                windows_job, "active_count", boom):
            with self.assertRaises(AdmissionReconciliationError) as caught:
                reconcile_admission(checkouts, "NSC-999", apply=True)
        self.assertIn("could not be queried", str(caught.exception))

    def test_running_containers_refuse(self):
        checkouts = self.build()
        with mock.patch.object(
                docker_workers, "inventory",
                lambda checkout, worker, **kw: [{"running": True}]):
            with self.assertRaises(AdmissionReconciliationError) as caught:
                reconcile_admission(checkouts, "NSC-999", apply=True)
        self.assertIn("containers", str(caught.exception))

    def test_unknown_containers_refuse_only_when_the_run_launched(self):
        """Docker being down costs nothing for a run that never started.

        No process existed to create a container. For a run that did start it is
        the difference between proven and assumed, so it refuses there.
        """
        def unavailable(checkout, worker, **kw):
            raise RuntimeError("docker daemon unavailable")

        never = self.build()
        with mock.patch.object(docker_workers, "inventory", unavailable):
            result = reconcile_admission(never, "NSC-999")
        self.assertTrue(result["would_release"])

        launched = self.build()
        self.make_run_root(launched, "NSC-999", RUN,
                           identity=self.dead_identity())
        with mock.patch.object(docker_workers, "inventory", unavailable):
            with self.assertRaises(AdmissionReconciliationError) as caught:
                reconcile_admission(launched, "NSC-999")
        self.assertIn("cannot be proven exited", str(caught.exception))

    def test_a_running_graph_controller_refuses(self):
        checkouts = self.build(controller={"status": "running"})
        with self.no_containers():
            with self.assertRaises(AdmissionReconciliationError) as caught:
                reconcile_admission(checkouts, "NSC-999", apply=True)
        self.assertIn("graph controller is running", str(caught.exception))
        self.assertEqual(1, len(self.reservations_now(checkouts)))


class TheSupportedPathIsPreferred(Base):
    def test_a_record_that_owns_this_run_sends_the_caller_to_settle_worker(self):
        """The boundary between this command and ``settle-worker``.

        A second way to release a reservation that a supported command can
        already reach is how the supported command's extra checks -- crew
        artifacts, containers, the record's own terminal write -- get skipped.
        """
        checkouts = self.build(record={
            "task_id": "NSC-999", "schema_version": "assistant-checkout/v1",
            "launch": {"run_id": RUN, "lease_id": LEASE,
                       "status": "ready_pending"},
        })
        with self.no_containers():
            with self.assertRaises(AdmissionReconciliationError) as caught:
                reconcile_admission(checkouts, "NSC-999", apply=True)
        message = str(caught.exception)
        self.assertIn("settle-worker", message)
        self.assertIn("not finished", message)
        self.assertEqual(1, len(self.reservations_now(checkouts)))

    def test_a_record_naming_a_different_run_does_not_block(self):
        """NSC-046's exact shape: the record describes an older, settled run."""
        checkouts = self.build(record={
            "task_id": "NSC-999", "schema_version": "assistant-checkout/v1",
            "launch": {"run_id": "task-orch-nsc999-20260917-1",
                       "lease_id": "task-orch-nsc999-20260917",
                       "status": "ready_pending"},
            "worker_history": [{"run_id": "task-orch-nsc999-20260917-1",
                                "status": "stopped",
                                "capacity_released": True}],
        })
        with self.no_containers():
            result = reconcile_admission(checkouts, "NSC-999", apply=True)
        self.assertTrue(result["released"])
        self.assertIn("names task-orch-nsc999-20260917-1",
                      result["proofs"]["record_finding"])


class TheProofAndTheReleaseShareOneLock(Base):
    """``checkouts.lock`` must be held across both, or the proof is re-openable.

    ``worker_launcher.launch_worker`` verifies its reservation and creates the
    run directory inside a single hold of ``checkouts.lock``. A reconciliation
    that probed outside that lock could be overtaken between reading "no run
    directory" and writing the release, and would then drop the reservation of a
    run that had just started.

    Contended from a SUBPROCESS deliberately: Windows file locks are owned by
    the process, so a same-process contender can acquire the region again and
    would report exclusion that does not exist.
    """

    CONTENDER = LF.join([
        "import pathlib, sys",
        "sys.path.insert(0, sys.argv[1])",
        "from Pipeline.TaskReviewAgent.execution_session_pool import "
        "_exclusive_file_lock",
        "try:",
        "    with _exclusive_file_lock(pathlib.Path(sys.argv[2]), "
        "timeout_seconds=1):",
        "        pass",
        "except Exception:",
        "    sys.exit(3)",
        "sys.exit(0)",
    ])

    def contend(self, checkouts) -> int:
        root = str(pathlib.Path(__file__).resolve().parents[2])
        return subprocess.run(
            [sys.executable, "-c", self.CONTENDER, root,
             str(checkouts.records / "checkouts.lock")],
            capture_output=True, creationflags=NO_WINDOW).returncode

    def test_the_lock_is_free_before_and_after_but_held_during(self):
        checkouts = self.build()
        self.assertEqual(0, self.contend(checkouts),
                         "the lock must be free before the command runs")

        reached = threading.Event()
        finish = threading.Event()
        outcome = {}

        def slow_probe(run_root):
            reached.set()
            finish.wait(timeout=30)
            return 0

        def run():
            try:
                with self.no_containers(), mock.patch.object(
                        admission_reconciliation, "_job_active", slow_probe):
                    outcome["result"] = reconcile_admission(
                        checkouts, "NSC-999", apply=True)
            except BaseException as error:        # noqa: BLE001
                outcome["error"] = error

        thread = threading.Thread(target=run)
        thread.start()
        try:
            self.assertTrue(reached.wait(timeout=30),
                            "the probe must actually be reached")
            self.assertEqual(
                3, self.contend(checkouts),
                "another process took checkouts.lock while the reconciliation "
                "was mid-proof: the proof and the release are NOT serialised "
                "against a concurrent launch")
        finally:
            finish.set()
            thread.join(timeout=60)

        self.assertNotIn("error", outcome, f"{outcome.get('error')!r}")
        self.assertTrue(outcome["result"]["released"])
        self.assertEqual(0, self.contend(checkouts),
                         "the lock must be released when the command returns")


class TheIdentityMustBeExact(Base):
    def test_a_wrong_run_id_is_refused(self):
        checkouts = self.build()
        with self.assertRaises(AdmissionReconciliationError) as caught:
            reconcile_admission(checkouts, "NSC-999", run_id="not-the-run",
                                lease_id=LEASE)
        self.assertIn("releases an exact identity only", str(caught.exception))
        self.assertEqual(1, len(self.reservations_now(checkouts)))

    def test_two_reservations_require_an_explicit_identity(self):
        checkouts = self.build()
        second = self.reservation(checkouts, run_id="second-run",
                                  lease_id="second-lease")
        _, registry_path = _source_registry_paths(checkouts.source)
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["reservations"].append(second)
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        with self.assertRaises(AdmissionReconciliationError) as caught:
            reconcile_admission(checkouts, "NSC-999")
        self.assertIn("name the exact", str(caught.exception))

    def test_no_reservation_at_all_is_refused(self):
        checkouts = self.build(reservations=[])
        with self.assertRaises(AdmissionReconciliationError) as caught:
            reconcile_admission(checkouts, "NSC-999")
        self.assertIn("nothing to reconcile", str(caught.exception))


class ReleaseStillRefusesOutsideItsLock(Base):
    def test_release_and_the_lock_held_variant_agree(self):
        """The split must not change what ``release`` refuses."""
        checkouts = self.build()
        with self.assertRaises(ValueError):
            admission.release(checkouts, "NSC-999", "wrong-run", LEASE)
        self.assertEqual(1, len(self.reservations_now(checkouts)))
        result = admission.release(checkouts, "NSC-999", RUN, LEASE)
        self.assertTrue(result["released"])
        self.assertEqual([], self.reservations_now(checkouts))


if __name__ == "__main__":
    unittest.main(verbosity=2)
