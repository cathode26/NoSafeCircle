"""Deterministic regressions for the base-bound authoritative publication fence.

Every case drives the normally constructed production controller, the real
``IntegrationWindow``/``GitIntegrationGate``, real Issue transitions, the real
mainline guard and a real local Git remote. Only the GitHub ``gh`` transport is
faked; the authoritative branch mutation is a real Git ref transaction against a
real bare repository, so the compare-and-swap under test is the one the server
actually enforces.

Interleavings are produced at controlled transport boundaries -- the exact
command boundary where the competing writer runs -- never by sleeping.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.tests import integration_window_smoke_test as window_fixture
from Pipeline.TaskReviewAgent.tests import mainline_reintegration_smoke_test as mainline
from Pipeline.TaskReviewAgent.downstream_issue import DownstreamIssueCoordinator
from Pipeline.TaskReviewAgent.downstream_pipeline import DownstreamPipelineError, _default_runner
from Pipeline.TaskReviewAgent.integration_gate import (
    LEGACY_OWNER_KEYS,
    RECEIPT_PUBLICATION_KEYS,
    IntegrationGateError,
    LegacyGateOwnerError,
    owner_identity,
)
from Pipeline.TaskReviewAgent.publication_fence import (
    DEFINITELY_PUBLISHED,
    PublicationStatus,
)

TASK = mainline.TASK_ID
BRANCH = mainline.BRANCH
git = mainline.git


def _pull_request(head: str) -> dict:
    """A CLEAN, MERGEABLE pull request whose one check passed on ``head``."""

    return dict(
        number=1,
        url="https://example.invalid/pull/1",
        state="OPEN",
        headRefOid=head,
        baseRefName="main",
        isDraft=False,
        mergeable="MERGEABLE",
        mergeStateStatus="CLEAN",
        statusCheckRollup=[
            dict(
                __typename="CheckRun",
                name="windows-smoke",
                workflowName="TaskReviewAgent Deterministic Validation",
                status="COMPLETED",
                conclusion="SUCCESS",
                startedAt="2026-09-07T00:00:00Z",
                completedAt="2026-09-07T00:00:01Z",
                detailsUrl="https://example.invalid/actions/runs/1/job/1",
                headSha=head,
            )
        ],
    )


class FenceCase(unittest.TestCase):
    """Drive one gated delivery to the exact publication boundary."""

    def setUp(self):
        self.case = window_fixture.WindowTests()
        self.case.setUp()
        self.addCleanup(self.case.tearDown)
        self.controller = self.case.controller
        self.window = self.case.window
        self.gate = self.case.gate
        self.service = self.case.service
        self.root = self.case.root
        self.seed = self.root / "seed"
        self.remote = self.root / "remote.git"
        self.commands: list[tuple[str, ...]] = []
        self.case.acquire()
        self.window.before_action("integrate_current_main")
        self.controller.integrate_current_main()
        self.window.after_action("integrate_current_main")
        self.approved_head = git(self.controller.checkout, "rev-parse", "HEAD")
        body = (
            "## Human validation result\n\nResult: PASS\n"
            f"Tested commit: `{self.approved_head}`\n"
        )
        snapshot = self.service.find(TASK)
        self.service.backend.add_comment(snapshot.issue_number, body)
        self.service.apply_human_result(task_id=TASK, result_body=body, actor_id="cathode26")
        self.controller.workflow.acquire_agent_lease(
            planned_approach="Fenced publication regression",
            expected_validation="Exact committed head",
        )
        DownstreamIssueCoordinator(self.service).accept_unchanged_delivery_after_human_pass(
            task_id=TASK,
            branch=BRANCH,
            head_commit=self.approved_head,
            checkout_path=str(self.controller.checkout),
            draft_path="invented-draft.json",
            draft_sha256="d" * 64,
            proposal_path="invented-proposal.json",
            proposal_sha256="e" * 64,
        )
        self.controller.workflow.acquire_agent_lease(
            planned_approach="Fenced publication attempt",
            expected_validation="Exact committed head",
        )
        self.controller.state.update(
            pull_request_number=1,
            pull_request_url="https://example.invalid/pull/1",
            evidence_commit=self.approved_head,
        )
        self.controller._persist()
        self.controller._bound_repository = lambda: "invented-fixture/offline"
        self.pull_request = _pull_request(self.approved_head)
        self.guarded_main = git(self.controller.checkout, "rev-parse", "origin/main")
        self.controller.command_runner = self.runner
        self.on_publication_push = None

    # -- transport ----------------------------------------------------

    def runner(self, args, cwd, timeout_seconds):
        command = tuple(args)
        self.commands.append(command)
        if command and command[0] == "gh":
            if command[1:3] == ("pr", "view"):
                return subprocess.CompletedProcess(
                    command, 0, json.dumps(self.pull_request).encode(), b""
                )
            raise AssertionError(f"unexpected external command: {command}")
        if self.on_publication_push is not None and self.is_publication_push(command):
            hook, self.on_publication_push = self.on_publication_push, None
            replacement = hook(command)
            if replacement is not None:
                return replacement
        return _default_runner(command, cwd, timeout_seconds)

    @staticmethod
    def is_publication_push(command: tuple[str, ...]) -> bool:
        return "push" in command and any(
            item.endswith(":refs/heads/main") for item in command
        )

    # -- helpers ------------------------------------------------------

    def publish(self):
        self.window.before_action("inspect_or_merge_pull_request")
        try:
            return self.controller.inspect_or_merge_pull_request()
        finally:
            if self.window.held and self.window.in_action:
                self.window.after_action("inspect_or_merge_pull_request")

    def remote_main(self) -> str:
        return git(self.controller.checkout, "ls-remote", "origin", "refs/heads/main").split()[0]

    def publication_pushes(self) -> list:
        return [c for c in self.commands if self.is_publication_push(c)]

    def competing_main_commit(self, path: str, content: str) -> str:
        """A real external writer advancing main on the shared bare remote."""

        git(self.seed, "checkout", "main")
        git(self.seed, "fetch", "origin", "main")
        git(self.seed, "reset", "--hard", "origin/main")
        target = self.seed / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        mainline.commit_all(self.seed, f"Concurrent external main change: {path}")
        git(self.seed, "push", "origin", "main")
        return git(self.seed, "rev-parse", "main")

    def durable_publication(self) -> dict:
        return self.gate.read()[1]["owner"]["publication"]

    def local_publication(self) -> dict:
        return self.controller.state["publication"]


class BaseMovementTests(FenceCase):
    def test_main_changes_exactly_between_validation_and_publication(self):
        """The audit's F1 interleaving, at the authoritative transport boundary."""

        observed = {}

        def advance(command):
            observed["expected_main"] = self.remote_main()
            observed["moved_to"] = self.competing_main_commit(
                "Assets/UnvalidatedConcurrentMain.cs", "concurrent main change\n"
            )
            return None

        self.on_publication_push = advance
        result = self.publish()
        self.assertEqual(observed["expected_main"], self.guarded_main)
        self.assertNotEqual(observed["moved_to"], self.guarded_main)
        self.assertNotEqual(result.get("status"), "merged")
        self.assertEqual(self.remote_main(), observed["moved_to"])
        record = self.local_publication()
        self.assertEqual(record["status"], PublicationStatus.REJECTED_BASE_MOVED.value)
        self.assertEqual(record["expected_main"], self.guarded_main)
        self.assertEqual(record["source_head"], self.approved_head)
        self.assertEqual(
            self.durable_publication()["status"],
            PublicationStatus.REJECTED_BASE_MOVED.value,
        )
        self.assertFalse(
            git(self.controller.checkout, "ls-tree", self.approved_head,
                "Assets/UnvalidatedConcurrentMain.cs")
        )
        self.assertEqual(len(self.publication_pushes()), 1)
        self.assertIn(
            f"--force-with-lease=refs/heads/main:{self.guarded_main}",
            self.publication_pushes()[0],
        )

    def test_disjoint_competing_main_commit_is_a_base_change(self):
        moved = {}
        self.on_publication_push = lambda command: moved.update(
            oid=self.competing_main_commit("Docs/AI-Pipeline/disjoint.md", "disjoint\n")
        ) or None
        result = self.publish()
        moved = moved["oid"]
        self.assertNotEqual(result.get("status"), "merged")
        self.assertEqual(self.remote_main(), moved)
        self.assertEqual(
            self.local_publication()["status"],
            PublicationStatus.REJECTED_BASE_MOVED.value,
        )

    def test_conflicting_competing_main_commit_is_rejected(self):
        moved = {}
        self.on_publication_push = lambda command: moved.update(
            oid=self.competing_main_commit(
                "Pipeline/TaskReviewAgent/runtime.py", "conflicting rewrite\n")
        ) or None
        result = self.publish()
        moved = moved["oid"]
        self.assertNotEqual(result.get("status"), "merged")
        self.assertEqual(self.remote_main(), moved)
        self.assertEqual(
            self.local_publication()["status"],
            PublicationStatus.REJECTED_BASE_MOVED.value,
        )

    def test_moved_base_returns_to_reintegration_not_a_silent_merge(self):
        moved = self.competing_main_commit("Docs/AI-Pipeline/reintegrate.md", "moved\n")
        result = self.publish()
        self.assertNotEqual(result.get("status"), "merged")
        # The existing reintegration path ran: current main is merged into the
        # task branch and a NEW exact handoff awaits renewed human validation.
        self.assertIn(
            result.get("status"),
            {"integrated", "already_integrated", "human_revalidation_required"},
        )
        state = self.service.find(TASK).state.to_dict()
        self.assertEqual(state["state"], "human_action_required")
        self.assertEqual(self.remote_main(), moved)
        integrated = git(self.controller.checkout, "rev-parse", "HEAD")
        self.assertNotEqual(integrated, self.approved_head)
        parents = git(self.controller.checkout, "rev-list", "--parents", "-n", "1", integrated).split()
        self.assertEqual(parents, [integrated, self.approved_head, moved])


class SuccessfulPublicationTests(FenceCase):
    def test_unchanged_main_publishes_exactly_once(self):
        result = self.publish()
        self.assertEqual(result["status"], "merged")
        published = self.controller.state["merged_commit"]
        # The published commit IS the approved, checked candidate: the exact
        # topology the required validation evidence was accepted for.
        self.assertEqual(published, self.approved_head)
        self.assertEqual(self.remote_main(), published)
        self.assertEqual(len(self.publication_pushes()), 1)
        record = self.local_publication()
        self.assertEqual(record["status"], PublicationStatus.PUBLISHED.value)
        self.assertEqual(record["publication_commit"], published)
        self.assertEqual(record["validated_commit"], self.approved_head)
        self.assertEqual(record["observed_pre_image"], self.guarded_main)
        self.assertEqual(
            self.durable_publication()["status"], PublicationStatus.PUBLISHED.value
        )
        # Replaying the settled operation never advances the branch again.
        self.window.in_action = False
        self.pull_request.update(state="MERGED", mergeCommit={"oid": published})
        again = self.publish()
        self.assertEqual(again["status"], "merged")
        self.assertEqual(self.remote_main(), published)

    def test_required_checks_belong_to_the_exact_publication_topology(self):
        checks = self.controller._check_state(self.pull_request["statusCheckRollup"])
        self.assertEqual(checks["failed"], [])
        self.assertEqual(checks["pending"], [])
        self.assertEqual(self.pull_request["headRefOid"], self.approved_head)
        authority = self.controller._latest_validation_authority()
        self.assertEqual(authority["tested_commit"], self.approved_head)
        self.publish()
        published = self.controller.state["merged_commit"]
        # Published commit == checked PR head == validated commit, and the
        # previously proven base is an ancestor of it, so main only appended.
        self.assertEqual(published, self.approved_head)
        self.assertEqual(published, authority["tested_commit"])
        self.assertEqual(self.remote_main(), published)
        self.assertEqual(
            git(self.controller.checkout, "merge-base", "--is-ancestor",
                self.guarded_main, published), ""
        )
        self.assertEqual(self.durable_publication()["validated_commit"], self.approved_head)

    def test_publication_refuses_a_head_the_checks_did_not_cover(self):
        self.pull_request["headRefOid"] = "b" * 40
        unchanged = self.remote_main()
        with self.assertRaises(DownstreamPipelineError):
            self.publish()
        self.assertEqual(self.remote_main(), unchanged)
        self.assertEqual(self.publication_pushes(), [])

    def test_publication_refuses_checks_accepted_for_another_commit(self):
        """A rollup describing a synthetic merge ref never authorizes publication."""

        self.pull_request["statusCheckRollup"][0]["headSha"] = "a" * 40
        unchanged = self.remote_main()
        with self.assertRaisesRegex(DownstreamPipelineError, "did not evaluate"):
            self.publish()
        self.assertEqual(self.remote_main(), unchanged)
        self.assertEqual(self.publication_pushes(), [])

    def test_publication_requires_a_check_that_names_its_commit(self):
        self.pull_request["statusCheckRollup"][0].pop("headSha")
        unchanged = self.remote_main()
        with self.assertRaisesRegex(DownstreamPipelineError, "names the commit it validated"):
            self.publish()
        self.assertEqual(self.remote_main(), unchanged)
        self.assertEqual(self.publication_pushes(), [])

    def test_only_an_exact_lease_is_used_and_no_rewind_is_possible(self):
        self.publish()
        publication = self.publication_pushes()
        self.assertEqual(len(publication), 1)
        command = publication[0]
        self.assertIn("--atomic", command)
        self.assertIn("--porcelain", command)
        # Exactly one lease, in exact-value form, naming the bound expected base.
        leases = [item for item in command if item.startswith("--force-with-lease")]
        self.assertEqual(
            leases, [f"--force-with-lease=refs/heads/main:{self.guarded_main}"]
        )
        self.assertEqual(
            self.durable_publication()["expected_main"], self.guarded_main
        )
        # The update could only append: the leased base is an ancestor of the
        # published commit, so no history was rewound.
        self.assertEqual(
            git(self.controller.checkout, "merge-base", "--is-ancestor",
                self.guarded_main, self.remote_main()), ""
        )
        for issued in self.commands:
            self.assertNotIn("--force", issued)
            self.assertNotIn("-f", issued)
            self.assertNotIn("--force-if-includes", issued)
            self.assertNotIn("reset", issued)
            self.assertNotIn("--hard", issued)
            self.assertNotIn("filter-branch", issued)
            for token in issued:
                if token.startswith("--force-with-lease"):
                    self.assertRegex(token, r"^--force-with-lease=refs/heads/main:[0-9a-f]{40}$")
                if "push" in issued and token.endswith(":refs/heads/main"):
                    self.assertFalse(token.startswith("+"))

    def complete_delivery(self) -> str:
        published = self.controller.state["merged_commit"]
        DownstreamIssueCoordinator(self.service).complete(
            task_id=TASK,
            pull_request_url="https://example.invalid/pull/1",
            pull_request_number=1,
            merged_commit=published,
            conformant_record_id="fixture-conformant",
        )
        return published

    def test_durable_receipt_contains_all_required_identities(self):
        self.publish()
        published = self.complete_delivery()
        self.window.settle(self.controller.observe(), "completed")
        event = self.gate.read()[1]["event"]
        self.assertEqual(event["kind"], "gate_released")
        receipt = event["receipt"]
        for key in RECEIPT_PUBLICATION_KEYS:
            self.assertIn(key, receipt)
        self.assertEqual(receipt["publication_expected_main"], self.guarded_main)
        self.assertEqual(receipt["publication_source_head"], self.approved_head)
        self.assertEqual(receipt["publication_validated_commit"], self.approved_head)
        self.assertEqual(receipt["publication_commit"], published)
        self.assertEqual(receipt["publication_observed_main"], published)
        self.assertEqual(receipt["publication_status"], PublicationStatus.PUBLISHED.value)
        self.assertEqual(receipt["verified_main"], published)
        self.assertEqual(receipt["lease_id"], self.window.identity["lease_id"])


class OperationIdentityTests(FenceCase):
    def bind(self, source_head=None, expected_main=None):
        source_head = source_head or self.approved_head
        return self.gate.bind_publication(
            self.window.identity,
            source_head=source_head,
            validated_commit=source_head,
            expected_main=expected_main or self.guarded_main,
        )

    def test_mismatched_source_commit_does_not_inherit_authority(self):
        record = self.bind()
        _, state = self.gate.read()
        with self.assertRaisesRegex(IntegrationGateError, "different approved source head"):
            self.gate.require_owner(
                state, self.window.identity, source_head="c" * 40,
                expected_main=self.guarded_main,
            )
        rebound = self.bind(source_head="c" * 40)
        self.assertNotEqual(rebound["operation_id"], record["operation_id"])
        self.assertEqual(rebound["base_epoch"], record["base_epoch"] + 1)

    def test_mismatched_expected_main_does_not_inherit_authority(self):
        record = self.bind()
        _, state = self.gate.read()
        with self.assertRaisesRegex(IntegrationGateError, "different approved source head"):
            self.gate.require_owner(
                state, self.window.identity, source_head=self.approved_head,
                expected_main="d" * 40,
            )
        # The SAME candidate may never be re-leased against a newly observed
        # base: only reintegration + revalidation can authorize publication.
        with self.assertRaisesRegex(IntegrationGateError, "re-leased against a newly"):
            self.bind(expected_main="d" * 40)
        self.assertEqual(self.durable_publication()["operation_id"], record["operation_id"])
        self.assertEqual(self.durable_publication()["expected_main"], self.guarded_main)

    def test_validation_evidence_must_name_the_published_candidate(self):
        with self.assertRaisesRegex(IntegrationGateError, "validation evidence for the exact"):
            self.gate.bind_publication(
                self.window.identity, source_head=self.approved_head,
                validated_commit="f" * 40, expected_main=self.guarded_main,
            )

    def test_stale_operation_cannot_record_a_publication(self):
        stale = self.bind()
        self.bind(source_head="c" * 40)
        with self.assertRaisesRegex(IntegrationGateError, "stale or foreign operation"):
            self.gate.record_publication(
                self.window.identity,
                operation_id=stale["operation_id"],
                status=PublicationStatus.PUBLISHED.value,
                publication_commit="e" * 40,
            )

    def test_stale_operation_cannot_complete_the_gate(self):
        self.publish()
        published = self.controller.state["merged_commit"]
        DownstreamIssueCoordinator(self.service).complete(
            task_id=TASK, pull_request_url="https://example.invalid/pull/1",
            pull_request_number=1, merged_commit=published,
            conformant_record_id="fixture-conformant",
        )
        current = self.durable_publication()
        state = self.service.find(TASK).state.to_dict()
        receipt = dict(
            self.window.identity,
            schema_version="1.0",
            status="completed",
            issue_event_id=state["last_event_id"],
            issue_state=state["state"],
            head_commit=state["head_commit"],
            verified_main=published,
            publication_operation_id="0" * 32,
            publication_status=current["status"],
            publication_expected_main=current["expected_main"],
            publication_source_head=current["source_head"],
            publication_validated_commit=current["validated_commit"],
            publication_commit=current["publication_commit"],
            publication_observed_main=published,
            publication_base_epoch=current["base_epoch"],
        )
        with self.assertRaisesRegex(IntegrationGateError, "do not match this owner"):
            self.gate.release(self.window.identity, reason="stale settlement", receipt=receipt)
        self.assertIsNotNone(self.gate.read()[1]["owner"])

    def test_settlement_cannot_claim_a_publication_that_never_happened(self):
        state = self.service.find(TASK).state.to_dict()
        receipt = dict(
            self.window.identity,
            schema_version="1.0",
            status="quiescent",
            issue_event_id=state["last_event_id"],
            publication_operation_id="0" * 32,
        )
        with self.assertRaisesRegex(IntegrationGateError, "never performed"):
            self.gate.release(self.window.identity, reason="forged", receipt=receipt)

    def test_legitimate_reintegration_creates_new_base_bound_authority(self):
        moved = {}
        self.on_publication_push = lambda command: moved.update(
            oid=self.competing_main_commit("Docs/AI-Pipeline/rebind.md", "moved\n")
        ) or None
        self.publish()
        moved = moved["oid"]
        first = self.durable_publication()
        self.assertEqual(first["status"], PublicationStatus.REJECTED_BASE_MOVED.value)
        self.assertEqual(first["expected_main"], self.guarded_main)
        # The refusal already returned to reintegration, which produced a new
        # exact handoff commit awaiting renewed validation; only that new
        # candidate may carry publication authority.
        new_candidate = git(self.controller.checkout, "rev-parse", "HEAD")
        self.assertNotEqual(new_candidate, self.approved_head)
        rebound = self.gate.bind_publication(
            self.window.identity,
            source_head=new_candidate,
            validated_commit=new_candidate,
            expected_main=moved,
        )
        self.assertEqual(rebound["expected_main"], moved)
        self.assertEqual(rebound["base_epoch"], first["base_epoch"] + 1)
        self.assertNotEqual(rebound["operation_id"], first["operation_id"])
        # Durable history is preserved: the prior operation is still in the journal.
        raw = git(self.controller.checkout, "log", "--format=%B", "-n", "12",
                  self.gate.read()[0])
        self.assertIn(first["operation_id"], raw)


class LegacySchemaTests(FenceCase):
    def forge_legacy_owner(self) -> str:
        """Rewrite the journal tip so its owner uses the pre-versioned schema."""

        oid, state = self.gate.read()
        owner = dict(state["owner"])
        for key in set(owner) - set(LEGACY_OWNER_KEYS):
            owner.pop(key)
        state["owner"] = owner
        state["revision"] += 1
        state["event"] = dict(kind="gate_legacy_fixture", occurred_at="2026-09-01T00:00:00+00:00",
                              previous_oid=oid)
        checkout = self.controller.checkout
        tree = git(checkout, "mktree", check=True) if False else git(checkout, "rev-parse", f"{oid}^{{tree}}")
        payload = "nsc-durable-integration-gate\n" + json.dumps(
            state, sort_keys=True, separators=(",", ":")) + "\n"
        forged = subprocess.run(
            ["git", "-C", str(checkout), "commit-tree", tree, "-p", oid],
            input=payload.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        ).stdout.decode().strip()
        git(checkout, "push", f"--force-with-lease={self.gate.ref}:{oid}", "origin",
            f"{forged}:{self.gate.ref}")
        return forged

    def test_old_schema_active_owner_fails_closed_but_stays_readable(self):
        self.forge_legacy_owner()
        # Readable for audit and for explicit operator recovery ...
        _, state = self.gate.read()
        self.assertEqual(set(state["owner"]), set(LEGACY_OWNER_KEYS))
        # ... but never reinterpreted as authorized publication authority.
        with self.assertRaises(LegacyGateOwnerError):
            self.gate.require_owner(state, self.window.identity)
        with self.assertRaises(LegacyGateOwnerError):
            self.gate.bind_publication(
                self.window.identity, source_head=self.approved_head,
                validated_commit=self.approved_head, expected_main=self.guarded_main,
            )
        unchanged = self.remote_main()
        with self.assertRaises(IntegrationGateError):
            self.publish()
        self.assertEqual(self.remote_main(), unchanged)
        self.assertEqual(self.publication_pushes(), [])


class CrashAndUncertaintyTests(FenceCase):
    def test_crash_after_publication_before_receipt_does_not_publish_twice(self):
        def crash(command):
            _default_runner(command, self.controller.checkout, 900.0)
            raise SystemExit("simulated crash after the authoritative mutation")

        self.on_publication_push = crash
        with self.assertRaises(SystemExit):
            self.publish()
        interrupted = self.local_publication()
        self.assertEqual(interrupted["status"], PublicationStatus.ATTEMPTING.value)
        published = interrupted["publication_commit"]
        self.assertEqual(published, self.approved_head)
        self.assertEqual(self.remote_main(), published)
        issued = len(self.publication_pushes())
        self.assertEqual(issued, 1)
        # Recovery adopts the proven remote outcome instead of publishing again.
        self.window.in_action = False
        result = self.publish()
        self.assertEqual(result["status"], "merged")
        self.assertEqual(self.controller.state["merged_commit"], published)
        self.assertEqual(self.remote_main(), published)
        self.assertEqual(len(self.publication_pushes()), issued)
        self.assertIn(
            PublicationStatus(self.local_publication()["status"]), DEFINITELY_PUBLISHED
        )

    def test_uncertain_outcome_quarantines_and_blocks_the_successor(self):
        def unknown(command):
            return subprocess.CompletedProcess(
                command, 128, b"", b"fatal: the remote end hung up unexpectedly\n"
            )

        self.on_publication_push = unknown
        unchanged = self.remote_main()
        with self.assertRaises(DownstreamPipelineError) as caught:
            self.publish()
        self.assertEqual(self.remote_main(), unchanged)
        self.assertEqual(
            self.local_publication()["status"], PublicationStatus.UNCERTAIN.value
        )
        self.assertEqual(
            self.durable_publication()["status"], PublicationStatus.UNCERTAIN.value
        )
        self.window.failure(caught.exception, action="inspect_or_merge_pull_request")
        self.assertEqual(self.gate.read()[1]["owner"]["status"], "quarantined")
        successor = self.case.successor()
        self.assertEqual(self.gate.acquire(successor)["status"], "deferred")
        self.assertEqual(self.remote_main(), unchanged)

    def test_uncertain_operation_is_never_retried(self):
        def unknown(command):
            return subprocess.CompletedProcess(command, 128, b"", b"fatal: transport closed\n")

        self.on_publication_push = unknown
        with self.assertRaises(DownstreamPipelineError):
            self.publish()
        unchanged = self.remote_main()
        issued = len(self.publication_pushes())
        self.window.in_action = False
        with self.assertRaisesRegex(Exception, "unreconciled|uncertain|reconcile"):
            self.publish()
        self.assertEqual(self.remote_main(), unchanged)
        self.assertEqual(len(self.publication_pushes()), issued)


class QueueAndPokeTests(FenceCase):
    def test_queue_order_and_wake_remain_exactly_once_after_a_rejection(self):
        successor = self.case.successor()
        third = owner_identity("NSC-779", "third-run", "third-worker")
        self.gate.enqueue("NSC-779", ready_at="2026-09-07T01:00:00Z", ready_event="b" * 64)
        self.competing_main_commit("Docs/AI-Pipeline/queue.md", "moved\n")
        self.publish()
        _, state = self.gate.read()
        self.assertEqual([w["task_id"] for w in state["queue"]], ["NSC-778", "NSC-779"])
        self.assertEqual(state["owner"]["task_id"], TASK)
        self.assertEqual(self.gate.acquire(successor)["status"], "deferred")
        self.assertEqual(self.gate.acquire(third)["status"], "deferred")
        # A repeated enqueue of the same waiter stays exactly one queue entry.
        self.gate.enqueue("NSC-778", ready_at="2026-09-07T00:00:00Z", ready_event="a" * 64)
        self.assertEqual(
            [w["task_id"] for w in self.gate.read()[1]["queue"]], ["NSC-778", "NSC-779"]
        )


if __name__ == "__main__":
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority

    run_with_synthetic_authority(unittest.main, verbosity=2)
