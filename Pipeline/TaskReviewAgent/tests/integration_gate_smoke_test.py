#!/usr/bin/env python3
"""Regression-only component/serialization tests. Real local Git refs; no live services.

The cycle simulation drives real task/main merges and exact commit receipts. Its
ungated schedule is the pre-fix behavior: validate all ready heads, then merge
one at a time, reintegrating every head made stale by an earlier merge.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from Pipeline.TaskReviewAgent.integration_gate import (
    GitIntegrationGate, GateWakeListener, IntegrationGateError, owner_identity,
    repository_identity, ordered_waiters,
)
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity

READY = "2026-09-06T00:00:00+00:00"


def git(root: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if p.returncode:
        raise AssertionError(f"Git {args} failed: {p.stderr}")
    return p.stdout.strip()


def commit(root: Path, path: str, content: str) -> str:
    (root / path).write_text(content, encoding="utf-8")
    git(root, "add", "--", path)
    git(root, "commit", "-m", path)
    return git(root, "rev-parse", "HEAD")


class Fixture:
    def __init__(self, root: Path, count: int = 3):
        self.root = root
        self.remote = root / "remote.git"
        root.mkdir(parents=True, exist_ok=True)
        git(root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.clones = []
        name, email = validated_agent_git_identity()
        for i in range(count):
            clone = root / f"worker-{i}"
            git(root, "clone", str(self.remote), str(clone))
            git(clone, "config", "user.name", name)
            git(clone, "config", "user.email", email)
            self.clones.append(clone)
        self.main = commit(self.clones[0], "base.txt", "base")
        git(self.clones[0], "push", "origin", "HEAD:main")
        for i, clone in enumerate(self.clones):
            git(clone, "fetch", "origin")
            git(clone, "checkout", "-b", f"task-{i}", "origin/main")
            commit(clone, f"task-{i}.txt", str(i))
        self.gates = [GitIntegrationGate(c) for c in self.clones]
        self.identities = [owner_identity(f"NSC-{922+i}", f"run-{i}", f"worker-{i}") for i in range(count)]

    def queue(self, indexes=None):
        for i in indexes if indexes is not None else range(len(self.clones)):
            self.gates[i].enqueue(self.identities[i]["task_id"], ready_at=READY, ready_event=f"{i+1:064x}")

    def receipt(self, i: int, status="quiescent", **fields):
        return dict(self.identities[i], schema_version="1.0", status=status, issue_event_id=f"{i+99:064x}", **fields)


def competing_process(clone, identity, barrier, output):
    try:
        gate = GitIntegrationGate(Path(clone))
        barrier.wait(timeout=30)
        output.put(gate.acquire(identity))
    except BaseException as exc:
        output.put({"error": str(exc)})


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nsc-gate-")
        self.f = Fixture(Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    def test_three_implement_concurrently_only_one_integrates(self):
        # All three independent commits exist before ANY gate entry.
        self.assertEqual(len({git(c, "rev-parse", "HEAD") for c in self.f.clones}), 3)
        self.f.queue()
        results = [g.acquire(i)["status"] for g, i in zip(self.f.gates, self.f.identities)]
        self.assertEqual(results, ["acquired", "deferred", "deferred"])
        self.assertEqual(git(self.f.remote, "rev-parse", "main"), self.f.main)

    def test_equal_time_order_and_durable_queue_survives_restart(self):
        self.f.queue([2, 0, 1])
        restarted = GitIntegrationGate(self.f.clones[1])
        _, state = restarted.read()
        self.assertEqual([w["task_id"] for w in ordered_waiters(state)], ["NSC-922", "NSC-923", "NSC-924"])
        self.assertEqual(restarted.acquire(self.f.identities[1])["status"], "deferred")

    def test_second_process_cannot_acquire_same_domain(self):
        self.f.queue()
        # Two controllers contend for the SAME oldest task with different runs.
        foreign = owner_identity("NSC-922", "foreign-run", "foreign-worker")
        context = multiprocessing.get_context("spawn")
        barrier, output = context.Barrier(2), context.Queue()
        processes = [context.Process(target=competing_process,
                                    args=(str(self.f.clones[i]), identity, barrier, output))
                     for i, identity in enumerate((self.f.identities[0], foreign))]
        for process in processes:
            process.start()
        results = [output.get(timeout=60) for _ in processes]
        for process in processes:
            process.join(60)
            self.assertEqual(process.exitcode, 0)
        self.assertFalse(any("error" in r for r in results), results)
        # A simultaneous server transaction may have zero winners; never two.
        self.assertLessEqual(sum(r["status"] == "acquired" for r in results), 1)
        _, state = self.f.gates[0].read()
        if state["owner"]:
            loser = foreign if state["owner"]["worker_id"] == "worker-0" else self.f.identities[0]
            self.assertEqual(self.f.gates[1].acquire(loser)["status"], "deferred")

    def test_different_domains_are_independent(self):
        self.f.queue()
        self.f.gates[0].acquire(self.f.identities[0])
        other_branch = GitIntegrationGate(self.f.clones[1], target_branch="release")
        other_branch.enqueue("NSC-923", ready_at=READY, ready_event="a" * 64)
        self.assertEqual(other_branch.acquire(self.f.identities[1])["status"], "acquired")
        second = Fixture(self.f.root / "second", 1)
        second.queue()
        self.assertEqual(second.gates[0].acquire(second.identities[0])["status"], "acquired")
        self.assertEqual(repository_identity("git@github.com:Owner/Repo.git"), repository_identity("https://github.com/owner/repo.git"))

    def test_same_owner_resume_is_idempotent_and_not_worker_only(self):
        self.f.queue()
        gate, identity = self.f.gates[0], self.f.identities[0]
        gate.acquire(identity)
        oid, _ = gate.read()
        for _ in range(3):
            self.assertTrue(GitIntegrationGate(self.f.clones[1]).acquire(identity)["resumed"])
            self.assertEqual(gate.read()[0], oid)
        for key in ("run_id", "worker_id", "lease_id"):
            wrong = dict(identity, **{key: "f" * 32})
            self.assertEqual(self.f.gates[1].acquire(wrong)["status"], "deferred")

    def test_foreign_stale_missing_receipt_release_rejected(self):
        self.f.queue()
        gate, identity = self.f.gates[0], self.f.identities[0]
        gate.acquire(identity)
        for key in ("run_id", "worker_id", "lease_id", "task_id"):
            wrong = dict(identity, **{key: "f" * 32})
            with self.assertRaises(IntegrationGateError):
                gate.release(wrong, reason="fake", receipt=self.f.receipt(0))
        with self.assertRaises(IntegrationGateError):
            gate.release(identity, reason="exit_zero", receipt={})
        with self.assertRaises(IntegrationGateError):
            gate.release(identity, reason="fake_completion", receipt=self.f.receipt(0, "completed"))
        gate.release(identity, reason="quiescent", receipt=self.f.receipt(0))
        self.f.gates[1].acquire(self.f.identities[1])
        with self.assertRaises(IntegrationGateError):
            gate.release(identity, reason="stale", receipt=self.f.receipt(0))
        self.assertEqual(gate.read()[1]["owner"]["task_id"], "NSC-923")

    def test_long_unity_and_ci_never_reaped_by_elapsed_time(self):
        self.f.queue()
        gate, identity = self.f.gates[0], self.f.identities[0]
        gate.acquire(identity)
        for operation in ("unity", "ci"):
            gate.progress(identity, operation, operation=operation)
            challenger = GitIntegrationGate(self.f.clones[1], clock=lambda: "2099-01-01T00:00:00Z")
            self.assertEqual(challenger.acquire(self.f.identities[1])["status"], "deferred")
            with self.assertRaises(IntegrationGateError):
                gate.release(identity, reason="subprocess_exit_zero", receipt=self.f.receipt(0))
            gate.progress(identity, operation + "_done")

    def test_crash_requires_explicit_fencing_and_exact_recovery(self):
        self.f.queue()
        gate, identity = self.f.gates[0], self.f.identities[0]
        gate.acquire(identity)
        gate.progress(identity, "merge", operation="merge")
        gate.quarantine(identity, "controller interrupted; remote outcome unknown")
        oid, state = gate.read()
        self.assertEqual(state["owner"]["status"], "quarantined")
        with self.assertRaises(IntegrationGateError):
            gate.acquire(identity)
        self.assertEqual(self.f.gates[1].acquire(self.f.identities[1])["status"], "deferred")
        with self.assertRaises(IntegrationGateError):
            gate.recover(expected_oid=oid, receipt=self.f.receipt(0, "recovered"))
        proof = self.f.receipt(0, "recovered", processes_fenced=True, remote_operations_reconciled=True,
                               verified_main=self.f.main, operator_evidence="preserved-fencing-report.json")
        with self.assertRaises(IntegrationGateError):
            gate.recover(expected_oid="f" * 40, receipt=proof)
        gate.recover(expected_oid=oid, receipt=proof)
        self.assertEqual(self.f.gates[1].acquire(self.f.identities[1])["status"], "acquired")
        self.assertIn("gate_recovery_decision", git(self.f.clones[0], "log", "--format=%B", gate.read()[0]))

    def test_release_immediately_wakes_next_task_via_one_listener(self):
        event = threading.Event()
        gate = self.f.gates[0]
        listener = GateWakeListener(event, gate.domain)
        try:
            for i, g in enumerate(self.f.gates):
                g.enqueue(self.f.identities[i]["task_id"], ready_at=READY,
                          ready_event=f"{i+1:064x}", endpoint=listener.endpoint)
            for i in range(2):
                self.f.gates[i].acquire(self.f.identities[i])
                event.clear()
                result = self.f.gates[i].release(self.f.identities[i], reason="completed",
                                                receipt=self.f.receipt(i, "completed", verified_main=self.f.main))
                self.assertTrue(event.wait(2), "release did not poke the next waiter")
                self.assertEqual(result["next_waiter"], f"NSC-{923+i}")
        finally:
            listener.close()

    def test_history_durations_and_schema_corruption(self):
        self.f.queue()
        gate, identity = self.f.gates[0], self.f.identities[0]
        now = dt.datetime(2026, 9, 6, tzinfo=dt.timezone.utc)
        gate.clock = lambda: now.isoformat()
        gate.acquire(identity)
        gate.progress(identity, "unity", operation="unity")
        now += dt.timedelta(seconds=12)
        gate.progress(identity, "validated")
        gate.progress(identity, "ci", operation="ci")
        now += dt.timedelta(seconds=23)
        gate.progress(identity, "merged")
        gate.release(identity, reason="complete", receipt=self.f.receipt(0, "completed", verified_main=self.f.main))
        oid, state = gate.read()
        event = state["event"]
        self.assertEqual((event["unity_seconds"], event["ci_seconds"], event["integration_seconds"]), (12, 23, 35))
        history = git(self.f.clones[0], "log", "--format=%B", oid)
        self.assertIn("gate_eligible_queued", history)
        self.assertIn("gate_acquired", history)
        self.assertIn("gate_progress_confirmed", history)
        corrupted = copy.deepcopy(state)
        corrupted["schema_version"] = "99.0"
        with self.assertRaises(IntegrationGateError):
            gate.validate(corrupted)
        # A parseable copied receipt with a severed audit chain is corruption,
        # not a fresh free gate. Publish it only to this disposable bare remote.
        tree = git(self.f.clones[0], "rev-parse", f"{oid}^{{tree}}")
        forged = git(self.f.clones[0], "commit-tree", tree, "-m",
                     "nsc-durable-integration-gate\n" + json.dumps(state))
        git(self.f.clones[0], "push", f"--force-with-lease={gate.ref}:{oid}", "origin", f"{forged}:{gate.ref}")
        with self.assertRaisesRegex(IntegrationGateError, "corrupt"):
            gate.read()
        self.assertEqual(git(self.f.clones[0], "status", "--porcelain"), "")

    def test_gate_does_not_hide_or_corrupt_ephemeral_reservations(self):
        from Pipeline.TaskReviewAgent.claim_refs import GitRefClaimClient, ClaimRefsError
        self.f.queue()
        self.f.gates[0].acquire(self.f.identities[0])
        claims = GitRefClaimClient(local_repository=self.f.clones[1], remote="origin",
                                   namespace="refs/nsc/claims", worker_id="claim-worker")
        acquisition = claims.acquire(task_id="NSC-925", exclusive_resources=["repo-file:Assets/X.cs"], source_head=self.f.main)
        self.assertEqual(acquisition.status, "acquired")
        visible = claims.inspect_claims()
        self.assertEqual(len(visible), 2)
        self.assertTrue(all(item["receipt"]["task_id"] == "NSC-925" for item in visible))
        oid = self.f.gates[0].read()[0]
        with self.assertRaises(ClaimRefsError):
            claims.repair_stale_claim(refs=[self.f.gates[0].ref], expected_claim_oid=oid)
        claims.release(acquisition)
        self.assertEqual(self.f.gates[0].read()[0], oid)

    def test_noneligible_waiter_withdrawal_preserves_audit_and_priority(self):
        self.f.queue()
        with self.assertRaises(IntegrationGateError):
            self.f.gates[0].withdraw("NSC-922", issue_state="agent_ready", issue_event_id="a" * 64)
        self.f.gates[0].withdraw("NSC-922", issue_state="human_action_required", issue_event_id="a" * 64)
        self.assertEqual(self.f.gates[1].acquire(self.f.identities[1])["status"], "acquired")
        history = git(self.f.clones[0], "log", "--format=%B", self.f.gates[0].read()[0])
        self.assertIn("gate_waiter_withdrawn", history)


def simulate(root: Path, *, gated: bool, count: int) -> dict:
    fixture = Fixture(root, count)
    fixture.queue() if gated else None
    cycles = [0] * count
    validations, ci_heads, integrations = [[] for _ in range(count)], [[] for _ in range(count)], [0] * count
    def prepare(i):
        clone = fixture.clones[i]
        git(clone, "fetch", "origin")
        git(clone, "merge", "--no-edit", "origin/main")
        integrations[i] += 1
        exact = git(clone, "rev-parse", "HEAD")
        validations[i].append(exact)
        ci_heads[i].append(exact)
        cycles[i] += 1
    # The observed old schedule: everyone spends validation/CI before the
    # previous task finishes. Every later cycle integrates the new main.
    if not gated:
        for i in range(count):
            prepare(i)
    for i in range(count):
        if gated:
            assert fixture.gates[i].acquire(fixture.identities[i])["status"] == "acquired"
            prepare(i)
        clone = fixture.clones[i]
        exact = git(clone, "rev-parse", "HEAD")
        assert validations[i][-1] == ci_heads[i][-1] == exact
        git(clone, "push", "origin", f"{exact}:refs/heads/main")
        assert git(fixture.remote, "rev-parse", "main") == exact
        if gated:
            fixture.gates[i].release(fixture.identities[i], reason="completed",
                                     receipt=fixture.receipt(i, "completed", verified_main=exact))
        else:
            for later in range(i + 1, count):
                prepare(later)
    return dict(cycles=cycles, integration_calls=integrations, validation_cycles=sum(cycles), ci_cycles=sum(cycles))


class CycleTests(unittest.TestCase):
    def test_prefix_simulation_proves_triangular_work_then_one_cycle_each(self):
        with tempfile.TemporaryDirectory(prefix="nsc-gate-cycles-") as directory:
            root = Path(directory)
            before = simulate(root / "before", gated=False, count=3)
            after = simulate(root / "after", gated=True, count=3)
            self.assertEqual(before["cycles"], [1, 2, 3])
            self.assertEqual(after["cycles"], [1, 1, 1])
            self.assertEqual(after["integration_calls"], [1, 1, 1])
            print("CYCLE_EVIDENCE " + json.dumps(dict(before=before, after=after), sort_keys=True), flush=True)

    def test_single_task_has_same_commit_cycle_count(self):
        with tempfile.TemporaryDirectory(prefix="nsc-gate-single-") as directory:
            root = Path(directory)
            self.assertEqual(simulate(root / "before", gated=False, count=1), simulate(root / "after", gated=True, count=1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
