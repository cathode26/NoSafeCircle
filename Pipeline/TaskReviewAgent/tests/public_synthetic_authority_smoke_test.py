#!/usr/bin/env python3
"""Regression-only component tests for the public synthetic authority boundary.

Repository and command observations are injected. No GitHub, provider, Docker,
Unity, claim, checkout, or tracked repository state is mutated.
"""
from __future__ import annotations

from contextlib import ExitStack, redirect_stderr
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent import issue_workflow as workflow
from Pipeline.TaskReviewAgent import prepare_synthetic_gauntlet as generation
from Pipeline.TaskReviewAgent import run_autonomous_graph as cli
from Pipeline.TaskReviewAgent import synthetic_gauntlet_approver as approver
from Pipeline.TaskReviewAgent.downstream_resilience import require_decomposition_policy_document
from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import (
    FIXTURE_REPOSITORY, synthetic_fixture_authority,
)
from Pipeline.Testing import synthetic_source_validation as source_validation

PUBLIC = "cathode26/NoSafeCircle"


class PublicSyntheticAuthorityTests(unittest.TestCase):
    def runtime(self, enabled=False):
        args = cli.build_parser().parse_args([
            "--run-id", "public-authority-test", "--confirm-repository", PUBLIC])
        return replace(cli._runtime_configuration(args, None), synthetic_evidence_enabled=enabled)

    def test_public_defaults_have_no_automated_repository(self):
        self.assertEqual(workflow.AUTOMATED_VALIDATION_REPOSITORIES, frozenset())
        self.assertEqual(workflow.AUTOMATED_VALIDATION_REPOSITORY, "")
        self.assertEqual(generation.PRIVATE_REPOSITORY, "")
        self.assertFalse(self.runtime().synthetic_evidence_enabled)

    def test_cli_switch_and_repository_privacy_do_not_create_authority(self):
        for repository in (PUBLIC, FIXTURE_REPOSITORY, "another-owner/private-repository", ""):
            with self.subTest(repository=repository):
                with self.assertRaises(workflow.WorkflowContractError):
                    workflow.validate_automated_repository(repository)
                with self.assertRaises(generation.SyntheticGauntletError):
                    generation.authorized_repository(repository)
                with self.assertRaises(cli.AutonomousGraphRunError):
                    cli._require_synthetic_evidence_authority(self.runtime(True), repository)

    def assert_cli_stops_before_mutation(self, resumed):
        argv = ["--source", str(ROOT), "--checkout-root", str(ROOT.parent),
                "--run-id", "public-authority-test", "--confirm-repository", PUBLIC]
        if not resumed:
            argv.append("--enable-synthetic-evidence")
        existing = SimpleNamespace(runtime_configuration=self.runtime(True)) if resumed else None
        store = Mock()
        store.load.return_value = existing
        forbidden = {}
        with ExitStack() as stack:
            stack.enter_context(patch.object(cli, "repo_root", return_value=ROOT))
            stack.enter_context(patch.object(cli, "resolve_issue_backend_repository", return_value=PUBLIC))
            stack.enter_context(patch.object(cli, "JsonManifestStore", return_value=store))
            for name in ("_load_or_create_manifest", "JsonReceiptStore", "build_production_orchestrator", "AutonomousGraphController"):
                forbidden[name] = stack.enter_context(patch.object(cli, name, side_effect=AssertionError(name)))
            error = io.StringIO()
            with redirect_stderr(error):
                result = cli.main(argv)
        self.assertEqual(result, cli.EXIT_ADAPTER_FAILURE)
        self.assertIn("automated synthetic evidence is disabled", error.getvalue())
        store.save.assert_not_called()
        for mock in forbidden.values():
            mock.assert_not_called()

    def test_fresh_cli_enablement_stops_before_claim_or_dispatch(self):
        self.assert_cli_stops_before_mutation(False)

    def test_resumed_enabled_manifest_stops_before_claim_or_dispatch(self):
        self.assert_cli_stops_before_mutation(True)

    def test_ordinary_public_run_keeps_the_human_validation_path(self):
        cli._require_synthetic_evidence_authority(self.runtime(False), PUBLIC)
        from Pipeline.TaskReviewAgent.tests.automated_validation_event_smoke_test import (
            test_existing_human_pass_semantics_remain_unchanged,
        )
        test_existing_human_pass_semantics_remain_unchanged()

    def test_generation_denies_before_network_or_materialization(self):
        commands = []
        def observe(_source, *command):
            commands.append(command)
            if command == ("git", "remote", "get-url", "origin"):
                return f"https://github.com/{FIXTURE_REPOSITORY}.git"
            raise AssertionError(f"unexpected command after authority denial: {command}")
        with patch.object(generation, "_run", observe):
            with self.assertRaises(generation.SyntheticGauntletError):
                generation._preflight_mutation(ROOT, expected_head="1" * 40,
                                               confirmed_repository=FIXTURE_REPOSITORY)
        self.assertEqual(len(commands), 1)

    def test_recent_human_pass_label_gap_waits_with_public_authority_unchanged(self):
        from Pipeline.TaskReviewAgent import issue_workflow_store as store
        from Pipeline.TaskReviewAgent.tests.pending_workflow_write_smoke_test import stamp, frozen_clock
        self.assertEqual(workflow.AUTOMATED_VALIDATION_REPOSITORIES, frozenset())
        state = workflow.initial_state(task_id="NSC-701", task_contract_sha256="7" * 64, now=stamp(0))
        events = []
        for kind, actor, actor_id, target, phase, at, details in (
            (workflow.WorkflowEventType.AGENT_LEASE_ACQUIRED, workflow.WorkflowActor.AGENT,
             "public-fixture-worker", workflow.WorkflowState.AGENT_WORKING,
             workflow.WorkflowPhase.IMPLEMENTATION, 10,
             {"worker_id": "public-fixture-worker", "lease_id": "1" * 64}),
            (workflow.WorkflowEventType.HUMAN_HANDOFF_CREATED, workflow.WorkflowActor.AGENT,
             "public-fixture-worker", workflow.WorkflowState.HUMAN_ACTION_REQUIRED,
             workflow.WorkflowPhase.UNITY_RUNTIME_VALIDATION, 60,
             {"branch": "nsc-701-fixture", "head_commit": "b" * 40,
              "checkout_path": "C:/offline-fixture/NSC-701"}),
            (workflow.WorkflowEventType.HUMAN_VALIDATION_PASSED, workflow.WorkflowActor.HUMAN,
             "cathode26", workflow.WorkflowState.AGENT_READY,
             workflow.WorkflowPhase.DELIVERY_EVIDENCE, 120, {"tested_commit": "b" * 40}),
        ):
            state, event = workflow.transition(state, event_type=kind, actor_type=actor,
                actor_id=actor_id, to_state=target, to_phase=phase, details=details, now=stamp(at))
            events.append(event)
        backend = store.MemoryIssueBackend(now=lambda: stamp(180))
        backend.repository = PUBLIC
        issue = backend.create_issue(title="NSC-701 — Offline human workflow fixture",
            body=workflow.update_issue_body("", state), labels=[], assignees=["cathode26"])
        for event in events:
            backend.add_comment(issue["number"], workflow.render_event_comment(event, "Offline fixture."))
        backend.issue_events[issue["number"]].append({"id": 1, "event": "unlabeled",
            "label": {"name": workflow.STATE_LABELS["human_action_required"]},
            "created_at": stamp(121), "actor": {"login": "cathode26"}})
        with frozen_clock():
            snapshot = store._snapshot(backend, backend.get_issue(issue["number"]))
        self.assertFalse(snapshot.valid)
        self.assertIsNotNone(snapshot.pending_transition, snapshot.reasons)
        self.assertEqual(snapshot.state.human_result, "pass")
        self.assertEqual(snapshot.state, state)
        self.assertEqual(workflow.AUTOMATED_VALIDATION_REPOSITORIES, frozenset())

    def test_source_validator_denies_before_tests_or_evidence_writes(self):
        with patch.object(source_validation, "git", return_value=f"https://github.com/{FIXTURE_REPOSITORY}.git") as git:
            with self.assertRaises(ValueError):
                source_validation.validate(ROOT, "NSC-2000", "Fixture.Test", ROOT / "never-created-evidence")
        git.assert_called_once_with(ROOT, "remote", "get-url", "origin")

    def test_fixture_authority_is_scoped_and_still_excludes_production(self):
        with synthetic_fixture_authority():
            self.assertEqual(workflow.validate_automated_repository(FIXTURE_REPOSITORY), FIXTURE_REPOSITORY)
            self.assertEqual(generation.authorized_repository(FIXTURE_REPOSITORY), FIXTURE_REPOSITORY)
            self.assertIn(FIXTURE_REPOSITORY, approver.AUTOMATED_VALIDATION_REPOSITORIES)
            with self.assertRaises(workflow.WorkflowContractError):
                workflow.validate_automated_repository(PUBLIC)
        self.assertEqual(workflow.AUTOMATED_VALIDATION_REPOSITORIES, frozenset())
        self.assertEqual(approver.AUTOMATED_VALIDATION_REPOSITORIES, frozenset())
        self.assertEqual(generation.PRIVATE_REPOSITORY, "")

    def test_public_unity_policies_are_preserved_without_synthetic_templates(self):
        policy = json.loads((ROOT / "Pipeline/TaskReviewAgent/authoritative_validation_policy.json").read_text(encoding="utf-8"))
        require_decomposition_policy_document(policy)
        self.assertEqual(policy["decomposition_child_templates"], {})
        self.assertTrue({"NSC-020", "NSC-042"}.issubset(policy["tasks"]))
        self.assertEqual(policy["tasks"]["NSC-020"]["test_filters"], {
            "PlayMode": "NoSafeCircle.DoorPrototype.Tests.DoorInteractionPlayModeTests"})
        self.assertEqual(policy["tasks"]["NSC-042"]["test_filters"], {
            "EditMode": "NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
