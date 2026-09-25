"""Focused regressions for authenticated AssistantControl D1C application."""
from __future__ import annotations

from copy import deepcopy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.decomposition import _blocking_findings, _verify_review, apply, run
from Pipeline.TaskDecomposition.round_robin_decomposition import candidate_sha256
from Pipeline.TaskDecomposition.tests.test_support import create_repository, decomposed_result
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from TaskDecomposition.policy import validate_decomposition_result
from apply_graph_delta import inspect_graph_delta_replay
from graph_delta import plan_graph_delta
from persistent_work_graph import load_persistent_work_graph


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return completed.stdout.decode("utf-8", "replace").strip()


class ProposalContainerNameTests(unittest.TestCase):
    """A named proposal container lets an owner stop exactly one proposal; nothing else changes."""

    def test_only_blocking_findings_close_the_clean_pass_gate(self):
        """The gate required findings == [] with NO severity filter.

        FINDING_SEVERITIES is {"blocking", "advisory"} and review_policy.py:82
        blocks only on "blocking", so a pass carrying advisory findings is
        legitimate -- README.md:81 says "no unresolved BLOCKING findings".
        An ABSENT key also failed before, because .get returns None and
        None != []. Anything unreadable counts as blocking: this gate WITHHOLDS.
        """
        advisory = {"finding_id": "A", "severity": "advisory", "category": "style",
                    "affected_contracts": [], "problem": "p", "required_resolution": "r"}
        blocking = {**advisory, "finding_id": "B", "severity": "blocking"}
        cases = {
            "absent key": ({}, False),
            "empty list": ({"findings": []}, False),
            "one advisory": ({"findings": [advisory]}, False),
            "many advisory": ({"findings": [advisory, advisory]}, False),
            "one blocking": ({"findings": [blocking]}, True),
            "advisory and blocking": ({"findings": [advisory, blocking]}, True),
            "not a list": ({"findings": "nope"}, True),
            "entry not an object": ({"findings": ["nope"]}, True),
        }
        for label, (entry, expect_blocked) in cases.items():
            with self.subTest(case=label):
                self.assertEqual(
                    expect_blocked,
                    bool(_blocking_findings(entry)),
                    f"{label} should {'close' if expect_blocked else 'pass'} the gate")

    def test_run_names_the_compose_container_after_the_run_subcommand(self):
        from Pipeline.AssistantControl import decomposition as decomposition_module
        temporary = tempfile.TemporaryDirectory(prefix="assistant-decompose-name-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source"
        source.mkdir()
        create_repository(source)
        task_path = source / "Tasks" / "NSC-004.yaml"
        selected = json.loads(task_path.read_text(encoding="utf-8"))
        selected.update(execution_scope="needs_execution_decomposition",
                        execution_reason="Synthetic container-name regression requires decomposition.")
        _write_json(task_path, selected)
        _git(source, "add", "--", "Tasks/NSC-004.yaml")
        _git(source, "commit", "-m", "fixture: childless decomposition parent")
        head = _git(source, "rev-parse", "HEAD")
        manager = Checkouts(source, root / "checkouts")
        commands: list[list[str]] = []
        real_run = subprocess.run

        def fake_run(command, *args, **kwargs):
            if list(command)[:2] == ["docker", "compose"]:
                commands.append(list(command))
                return subprocess.CompletedProcess(command, 1)
            return real_run(command, *args, **kwargs)

        with patch.object(decomposition_module, "build_compose_command",
                          return_value=("docker", "compose", "-p", "nosafecircle", "run", "--rm", "-T",
                                        "round-robin-decompose", "python3",
                                        "Pipeline/TaskDecomposition/run_round_robin_decomposition.py")), \
                patch.object(decomposition_module, "decomposition_preflight",
                             return_value={"source_commit": head}), \
                patch.object(decomposition_module.subprocess, "run", side_effect=fake_run):
            record = decomposition_module.run(
                manager, "NSC-004", "fixture-run", providers="claude,codex",
                compose_project="nosafecircle", execution_authorized=True,
                container_name="nsc-decompose-fixture000000000000",
                container_labels={"com.nosafecircle.assistant.job": "fixture000000000000",
                                  "com.nosafecircle.assistant.checkout": "abc123"},
            )
        self.assertEqual("failed", record["status"])
        self.assertEqual("nsc-decompose-fixture000000000000", record["container_name"])
        # The container carries the owning ticket and checkout, so only that
        # owner can prove the container is its own before removing it.
        self.assertEqual({"com.nosafecircle.assistant.job": "fixture000000000000",
                          "com.nosafecircle.assistant.checkout": "abc123"},
                         record["container_labels"])
        self.assertEqual(1, len(commands))
        position = commands[0].index("run")
        self.assertEqual(["run", "--name", "nsc-decompose-fixture000000000000",
                          "--label", "com.nosafecircle.assistant.checkout=abc123",
                          "--label", "com.nosafecircle.assistant.job=fixture000000000000",
                          "--rm", "-T"],
                         commands[0][position:position + 9])
        with self.assertRaisesRegex(ValueError, "container name"):
            decomposition_module.run(
                manager, "NSC-004", "fixture-run-2", providers="claude,codex",
                compose_project="nosafecircle", execution_authorized=True,
                container_name="bad name!",
            )
        with self.assertRaisesRegex(ValueError, "container label"):
            decomposition_module.run(
                manager, "NSC-004", "fixture-run-3", providers="claude,codex",
                compose_project="nosafecircle", execution_authorized=True,
                container_name="nsc-decompose-fixture000000000001",
                container_labels={"bad key": "value"},
            )
        with self.assertRaisesRegex(ValueError, "labels require the named container"):
            decomposition_module.run(
                manager, "NSC-004", "fixture-run-4", providers="claude,codex",
                compose_project="nosafecircle", execution_authorized=True,
                container_labels={"com.nosafecircle.assistant.job": "x"},
            )
        self.assertEqual(1, len(commands))


class RetainedReviewConcurrencyTests(unittest.TestCase):
    def reviewed_fixture(self, root: Path, source: Path) -> SimpleNamespace:
        """An authenticated review_ready receipt for a childless parent in `source`."""
        task_id = "NSC-004"
        task_path = source / "Tasks" / f"{task_id}.yaml"
        selected = json.loads(task_path.read_text(encoding="utf-8"))
        selected.update(
            execution_scope="needs_execution_decomposition",
            execution_reason="Synthetic concurrency regression requires decomposition.",
        )
        _write_json(task_path, selected)
        _git(source, "add", "--", f"Tasks/{task_id}.yaml")
        _git(source, "commit", "-m", "fixture: select childless decomposition parent")
        graph = load_persistent_work_graph(source)
        parent = graph.tasks_by_id[task_id]
        proposal = decomposed_result(parent)
        proposal["children"][0]["exclusive_resources"] = []
        proposal["inbound_dependency_rewrites"] = []
        decomposition = validate_decomposition_result(
            proposal,
            parent_task=parent,
            existing_reconciliation_keys=graph.plan.id_map,
        )
        stored_plan = plan_graph_delta(graph, decomposition.parent_task, decomposition)
        reviewed_head = _git(source, "rev-parse", "HEAD")
        manager = Checkouts(source, root / "checkouts")
        manager.records.mkdir(parents=True)

        run_id = "fixture-reviewed-decomposition"
        output_root = (manager.records / "decomposition-runs").resolve()
        artifact_root = output_root / run_id
        artifact_root.mkdir(parents=True)
        branch = _git(source, "branch", "--show-current")
        reviewed_tree = _git(source, "rev-parse", "HEAD^{tree}")
        task = load_committed_task(source, task_id, commit=reviewed_head)
        digest = candidate_sha256(decomposition)
        candidate = {
            "version": 1,
            "author_provider": "claude",
            "sha256": digest,
            "decision": "decomposed",
            "graph_delta_plan_id": stored_plan.plan_id,
        }
        run_result = {
            "schema_version": "1.0",
            "mode": "round_robin_d1b2",
            "run_id": run_id,
            "task_id": task_id,
            "provider_order": ["claude", "codex"],
            "max_calls": 2,
            "calls_used": 2,
            "run_status": "review_ready",
            "decision": "decomposed",
            "review_independence": "cross_provider",
            "authority": "review_only_not_applied",
            "unresolved_findings": [],
            "rejection_reasons": [],
            "source_identity": {
                "head_commit": reviewed_head,
                "head_tree": reviewed_tree,
            },
            "task_execution_contract_identity": {
                "revision": task["contract_revision"],
                "sha256": task["task_contract_sha256"],
            },
            "latest_candidate": candidate,
            "independent_approver_provider": "codex",
            "rounds": [
                {
                    "role": "task_decomposer",
                    "requested_provider": "claude",
                    "actual_model": "fixture-author",
                    "agent_status": "succeeded",
                    "status": "candidate_valid",
                    "candidate_after": candidate,
                },
                {
                    "role": "decomposition_reviewer",
                    "requested_provider": "codex",
                    "actual_model": "fixture-reviewer",
                    "agent_status": "succeeded",
                    "status": "independent_pass",
                    "verdict": "pass",
                    "candidate_before": candidate,
                    "candidate_after": None,
                },
            ],
            "finding_history": [{
                "verdict": "pass",
                "reviewed_candidate_sha256": digest,
                # AN ADVISORY FINDING ON A PASS IS LEGITIMATE and this fixture
                # now proves the apply path accepts one. Before the fix, the
                # gate required findings == [] with NO severity filter, so a
                # reviewer that passed the split and appended one cosmetic note
                # failed the entire paid run -- decomp-nsc066-20260924b died on
                # exactly this. review_policy.py:82 blocks only on "blocking".
                "findings": [{
                    "finding_id": "ADV-1",
                    "severity": "advisory",
                    "category": "style",
                    "affected_contracts": [],
                    "problem": "a cosmetic observation",
                    "required_resolution": "none",
                }],
            }],
        }
        _write_json(artifact_root / "decomposition_run_result.json", run_result)
        _write_json(
            artifact_root / "decomposition_result.json",
            decomposition.to_dict(),
        )
        _write_json(artifact_root / "graph_delta.json", stored_plan.to_dict())
        artifact_bytes = {
            path.name: path.read_bytes() for path in artifact_root.iterdir()
        }
        record = {
            "schema_version": "assistant-decomposition/v1",
            "task_id": task_id,
            "run_id": run_id,
            "source": str(source.resolve()),
            "source_commit": reviewed_head,
            "source_tree": reviewed_tree,
            "source_branch": branch,
            "task_contract_sha256": task["task_contract_sha256"],
            "providers": ["claude", "codex"],
            "output_root": str(output_root),
            "artifact_root": str(artifact_root),
            "status": "review_ready",
        }
        original_review = _verify_review(manager, record)
        record["review"] = original_review
        write_record(manager.records / f"{task_id}.decomposition.json", record)
        return SimpleNamespace(
            task_id=task_id, manager=manager, record=record, run_id=run_id,
            branch=branch, reviewed_head=reviewed_head, artifact_root=artifact_root,
            artifact_bytes=artifact_bytes, original_review=original_review,
            decomposition=decomposition, stored_plan=stored_plan,
        )

    def temporary_root(self) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="assistant-d1c-concurrency-")
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)

    def test_unrelated_integration_retains_review_and_applies_at_current_source(self):
        root = self.temporary_root()
        source = root / "source"
        source.mkdir()
        create_repository(source)
        fixture = self.reviewed_fixture(root, source)
        task_id, manager, record = fixture.task_id, fixture.manager, fixture.record
        run_id, branch, reviewed_head = fixture.run_id, fixture.branch, fixture.reviewed_head
        artifact_root, artifact_bytes = fixture.artifact_root, fixture.artifact_bytes
        original_review = fixture.original_review

        concurrent_path = source / "Assets" / "ConcurrentImplementation.cs"
        concurrent_path.write_text(
            "// Concurrent implementation integrated.\n", encoding="utf-8", newline="\n",
        )
        _git(source, "add", "--", "Assets/ConcurrentImplementation.cs")
        _git(source, "commit", "-m", "fixture: concurrent implementation")
        current_head = _git(source, "rev-parse", "HEAD")
        current_review = _verify_review(manager, record)
        proof = current_review["source_advancement"]
        self.assertEqual(reviewed_head, proof["reviewed_source_commit"])
        self.assertEqual(current_head, proof["apply_source_commit"])
        self.assertTrue(proof["reviewed_source_is_ancestor"])
        self.assertTrue(proof["authoritative_graph_inputs_unchanged"])
        self.assertTrue(proof["parent_contract_semantic_authorization_compatible"])
        self.assertEqual(
            proof["reviewed_parent_semantic_sha256"],
            proof["current_parent_semantic_sha256"],
        )

        with patch.dict(os.environ, {
            "NSC_AGENT_GIT_NAME": "No Safe Circle TaskReviewAgent",
            "NSC_AGENT_GIT_EMAIL": "task-review-agent@nosafecircle.invalid",
        }):
            applied = apply(
                manager,
                task_id,
                run_id=run_id,
                expected_source_commit=current_head,
                target_branch=branch,
            )

        self.assertEqual(current_head, _git(source, "rev-parse", "HEAD^"))
        self.assertEqual(original_review, applied["review"])
        self.assertEqual(current_review, applied["application_authentication"])
        self.assertEqual(
            artifact_bytes,
            {path.name: path.read_bytes() for path in artifact_root.iterdir()},
        )


    def test_a_review_run_with_a_different_author_checklist_is_refused(self):
        root = self.temporary_root()
        source = root / "source"
        source.mkdir()
        create_repository(source)
        fixture = self.reviewed_fixture(root, source)
        record = dict(fixture.record, author_checklist="parent-contract-v1")
        with self.assertRaisesRegex(ValueError, "author checklist is None, expected 'parent-contract-v1'"):
            _verify_review(fixture.manager, record)

    def test_an_unknown_author_checklist_is_refused_before_anything_starts(self):
        root = self.temporary_root()
        (root / "source").mkdir()
        create_repository(root / "source")
        manager = Checkouts(root / "source", root / "checkouts")
        with self.assertRaisesRegex(ValueError, "Unknown decomposition author checklist"):
            run(manager, "NSC-004", "nsc-004-run", execution_authorized=True,
                author_checklist="parent-contract-v9")
        self.assertFalse(manager.records.exists() and any(manager.records.iterdir()))

    AGENT_IDENTITY = {
        "NSC_AGENT_GIT_NAME": "No Safe Circle TaskReviewAgent",
        "NSC_AGENT_GIT_EMAIL": "task-review-agent@nosafecircle.invalid",
    }
    EVIDENCE = "Pipeline/TaskGraph/evidence/NSC-999/records/receiver-evidence.json"

    def commit_evidence(self, repository: Path, text: str) -> str:
        path = repository / self.EVIDENCE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        _git(repository, "add", "--", self.EVIDENCE)
        _git(repository, "commit", "-m", "fixture: delivery evidence")
        return _git(repository, "rev-parse", "HEAD")

    def isolated_clone(self, root: Path, receiver: Path, name: str) -> Path:
        clone = root / name
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(receiver), str(clone)],
                       check=True, capture_output=True)
        _git(clone, "config", "user.name", self.AGENT_IDENTITY["NSC_AGENT_GIT_NAME"])
        _git(clone, "config", "user.email", self.AGENT_IDENTITY["NSC_AGENT_GIT_EMAIL"])
        return clone

    def test_evidence_landing_on_the_proposal_source_still_refuses_the_review(self):
        """Control: the gate that clone isolation sidesteps is still live."""
        root = self.temporary_root()
        receiver = root / "receiver"
        receiver.mkdir()
        create_repository(receiver)
        clone = self.isolated_clone(root, receiver, "proposal")
        fixture = self.reviewed_fixture(root, clone)
        self.commit_evidence(clone, '{"landed": "on the proposal source"}\n')
        with self.assertRaisesRegex(ValueError, "TaskGraph inputs changed"):
            _verify_review(fixture.manager, fixture.record)

    def test_a_plan_applied_in_an_isolated_clone_lands_on_an_advanced_receiver(self):
        root = self.temporary_root()
        receiver = root / "receiver"
        receiver.mkdir()
        create_repository(receiver)
        clone = self.isolated_clone(root, receiver, "proposal")
        fixture = self.reviewed_fixture(root, clone)
        receipt_path = fixture.manager.records / f"{fixture.task_id}.decomposition.json"

        receiver_evidence = '{"landed": "on the receiver while the plan waited"}\n'
        receiver_head = self.commit_evidence(receiver, receiver_evidence)
        with patch.dict(os.environ, self.AGENT_IDENTITY):
            applied = apply(fixture.manager, fixture.task_id, run_id=fixture.run_id,
                            expected_source_commit=fixture.reviewed_head,
                            target_branch=fixture.branch)
        d1c = _git(clone, "rev-parse", "HEAD")
        self.assertEqual(d1c, applied["applied_commit"])
        self.assertEqual(fixture.reviewed_head, _git(clone, "rev-parse", "HEAD^"))
        receipt_bytes = receipt_path.read_bytes()

        _git(receiver, "fetch", "-q", str(clone), d1c)
        _git(receiver, "-c", "user.name=" + self.AGENT_IDENTITY["NSC_AGENT_GIT_NAME"],
             "-c", "user.email=" + self.AGENT_IDENTITY["NSC_AGENT_GIT_EMAIL"],
             "merge", "--no-ff", "-q", "-m", "fixture: land the clone D1C", d1c)
        merged = _git(receiver, "rev-parse", "HEAD")
        for ancestor in (receiver_head, d1c):
            subprocess.run(["git", "-C", str(receiver), "merge-base", "--is-ancestor",
                            ancestor, merged], check=True)

        replay = inspect_graph_delta_replay(
            receiver, fixture.decomposition.parent_task, fixture.stored_plan,
            expected_head=merged)
        self.assertEqual(("already_applied", ()), (replay.status, tuple(replay.failures)))
        load_persistent_work_graph(receiver)
        self.assertEqual(receiver_evidence.strip(), _git(receiver, "show", "HEAD:" + self.EVIDENCE))
        parent = load_committed_task(receiver, fixture.task_id, commit=merged)
        children = applied["child_ids"]
        self.assertEqual("decomposed", parent["decomposition_state"])
        self.assertEqual(sorted(children), sorted(parent["decomposition_children"]))
        for child_id in children:
            child = load_committed_task(receiver, child_id, commit=merged)
            self.assertEqual((fixture.task_id, "active"),
                             (child["parent"], child["contract_disposition"]))
        self.assertEqual(receipt_bytes, receipt_path.read_bytes())
        self.assertEqual(
            fixture.artifact_bytes,
            {path.name: path.read_bytes() for path in fixture.artifact_root.iterdir()},
        )
        self.assertEqual("", _git(receiver, "status", "--porcelain"))
        self.assertEqual("", _git(clone, "status", "--porcelain"))


class ChecklistDeliveryTests(unittest.TestCase):
    """An opted-in review is accepted only with retained proof of delivery."""

    VERSION = "parent-contract-v1"

    def produce(self, *, checklist):
        import TaskDecomposition.tests.round_robin_decomposition_smoke_test as smoke
        from TaskDecomposition.round_robin_decomposition import run_round_robin_decomposition
        from TaskDecomposition.tests.test_support import decomposed_result

        temporary = tempfile.TemporaryDirectory(prefix="assistant-checklist-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source"
        source.mkdir()
        tasks = create_repository(source)
        manager = Checkouts(source, root / "checkouts")
        output_root = (manager.records / "decomposition-runs").resolve()
        output_root.mkdir(parents=True)
        parent = tasks["NSC-010"]
        raw = decomposed_result(parent)
        digest = candidate_sha256(smoke.validated_candidate(raw, parent, tasks))
        run_id = "checklist-delivery"
        result = run_round_robin_decomposition(
            source=source, output_root=output_root, task_id="NSC-010",
            provider_order=("codex", "claude"), max_calls=2, run_id=run_id,
            provider_factory=smoke.provider_factory({
                "codex": smoke.QueueProvider([raw]),
                "claude": smoke.QueueProvider([smoke.pass_review(digest)]),
            }),
            _require_physical_read_only_source=False,
            author_checklist=checklist,
        )
        self.assertEqual("review_ready", result["run_status"], result["rejection_reasons"])
        head = _git(source, "rev-parse", "HEAD")
        record = {
            "schema_version": "assistant-decomposition/v1", "task_id": "NSC-010", "run_id": run_id,
            "source": str(source.resolve()), "source_commit": head,
            "source_tree": _git(source, "rev-parse", "HEAD^{tree}"),
            "source_branch": _git(source, "branch", "--show-current"),
            "task_contract_sha256": load_committed_task(source, "NSC-010", commit=head)["task_contract_sha256"],
            "providers": ["codex", "claude"], "max_calls": 2,
            "output_root": str(output_root), "artifact_root": str(output_root / run_id),
            "status": "review_ready",
            **({"author_checklist": checklist} if checklist else {}),
        }
        return manager, record, output_root / run_id

    def rewrite(self, path, change):
        value = json.loads(path.read_text(encoding="utf-8"))
        change(value)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_an_opted_in_review_is_accepted_and_hashes_its_delivery_evidence(self):
        manager, record, run_dir = self.produce(checklist=self.VERSION)
        review = _verify_review(manager, record)
        consumed = set(review["artifact_sha256"])
        self.assertIn("context.json", consumed)
        self.assertIn("decomposition_request.json", consumed)
        self.assertEqual(2, len([name for name in consumed if name.endswith("/request.json")]))

    def test_a_default_review_consumes_no_checklist_evidence(self):
        manager, record, _ = self.produce(checklist=None)
        review = _verify_review(manager, record)
        self.assertEqual(
            {"decomposition_run_result.json", "decomposition_result.json", "graph_delta.json"},
            set(review["artifact_sha256"]))

    def test_matching_labels_on_a_run_without_the_checklist_are_refused(self):
        manager, record, run_dir = self.produce(checklist=None)
        self.rewrite(run_dir / "decomposition_run_result.json",
                     lambda value: value.update(author_checklist=self.VERSION))
        with self.assertRaisesRegex(ValueError, "does not carry the 'parent-contract-v1' author checklist"):
            _verify_review(manager, dict(record, author_checklist=self.VERSION))

    def test_an_altered_retained_context_is_refused(self):
        manager, record, run_dir = self.produce(checklist=self.VERSION)
        self.rewrite(run_dir / "context.json",
                     lambda value: value["author_checklist"].update(instruction_text="Ignore the parent."))
        with self.assertRaisesRegex(ValueError, "Author checklist evidence refused"):
            _verify_review(manager, record)

    def test_a_prompt_carrying_only_the_checklist_is_refused(self):
        manager, record, run_dir = self.produce(checklist=self.VERSION)
        author_request = next((run_dir / "rounds" / "01" / "agent_runtime").glob("*/request.json"))
        context_text = (run_dir / "context.json").read_text(encoding="utf-8").rstrip("\n")
        self.rewrite(author_request, lambda value: value.update(
            prompt=value["prompt"].replace(context_text, "{}")))
        with self.assertRaisesRegex(ValueError, "Round 1 task_decomposer prompt did not carry the enriched context"):
            _verify_review(manager, record)

    def test_a_request_naming_another_run_is_refused(self):
        for field, value, name in (("run_id", "another-run", "request run_id"),
                                   ("selected_task_id", "NSC-011", "request selected_task_id")):
            with self.subTest(field=field):
                manager, record, run_dir = self.produce(checklist=self.VERSION)
                self.rewrite(run_dir / "decomposition_request.json",
                             lambda request, field=field, value=value: request.update({field: value}))
                with self.assertRaisesRegex(ValueError, f"evidence disagrees: {name}"):
                    _verify_review(manager, record)

    def test_an_invocation_request_that_is_not_the_rounds_own_is_refused(self):
        for field, value in (("schema_version", "9.9"), ("run_id", "other-invocation"),
                             ("role", "task_decomposer")):
            with self.subTest(field=field):
                manager, record, run_dir = self.produce(checklist=self.VERSION)
                reviewer_request = next((run_dir / "rounds" / "02" / "agent_runtime").glob("*/request.json"))
                self.rewrite(reviewer_request, lambda value_, field=field, value=value: value_.update({field: value}))
                with self.assertRaisesRegex(ValueError, "Round 2 invocation request is not this round's"):
                    _verify_review(manager, record)

    def test_an_invocation_prompt_without_the_checklist_is_refused(self):
        manager, record, run_dir = self.produce(checklist=self.VERSION)
        reviewer_request = next((run_dir / "rounds" / "02" / "agent_runtime").glob("*/request.json"))
        self.rewrite(reviewer_request, lambda value: value.update(
            prompt=value["prompt"].replace("BEGIN AUTHOR CHECKLIST", "BEGIN SOMETHING ELSE")))
        with self.assertRaisesRegex(ValueError, "Round 2 decomposition_reviewer prompt did not carry"):
            _verify_review(manager, record)


class BookkeeperReviewTests(unittest.TestCase):
    """A designer/bookkeeper run is accepted only with its sheet and bookkeeping proven."""

    MODEL = "fixture-bookkeeper"

    def produce(self, *, budget: int = 2, record_model: str | None = MODEL, revision: bool = False):
        from TaskDecomposition.ownership_sheet import sheet_from_result, sheet_sha256
        from TaskDecomposition.round_robin_decomposition import run_round_robin_decomposition
        from TaskDecomposition.tests.review_chain_smoke_test import factory
        from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (
            QueueProvider, pass_review, revise_review, validated_candidate,
        )
        from TaskDecomposition.tests.test_support import decomposed_result

        temporary = tempfile.TemporaryDirectory(prefix="assistant-bookkeeper-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source"
        source.mkdir()
        tasks = create_repository(source)
        manager = Checkouts(source, root / "checkouts")
        output_root = (manager.records / "decomposition-runs").resolve()
        output_root.mkdir(parents=True)
        parent = tasks["NSC-010"]
        result_raw = decomposed_result(parent)
        digest = candidate_sha256(validated_candidate(result_raw, parent, tasks))
        run_id = "bookkeeper-review"
        review = pass_review(digest)
        review.pop("revised_decomposition")
        review.update(schema_version="1.1", reviewed_sheet_sha256=sheet_sha256(sheet_from_result(result_raw)),
                      revised_sheet=None)
        outputs = {"claude": [sheet_from_result(result_raw), result_raw], "codex": [review]}
        if revision:
            revised = deepcopy(result_raw)
            revised["children"][0]["notes"] += " Clarify the component's public method ownership."
            revised_sheet = sheet_from_result(revised)
            revised_hash = candidate_sha256(validated_candidate(revised, parent, tasks))
            review = revise_review(digest, revised, round_number=2, suffix="a")
            review.pop("revised_decomposition")
            review.update(schema_version="1.1", revised_sheet=revised_sheet,
                          reviewed_sheet_sha256=sheet_sha256(sheet_from_result(result_raw)))
            final = pass_review(revised_hash, resolutions=[
                {"finding_id": "round-02-a", "status": "resolved", "explanation": "Method owner clarified."}])
            final.pop("revised_decomposition")
            final.update(schema_version="1.1", revised_sheet=None,
                         reviewed_sheet_sha256=sheet_sha256(revised_sheet))
            outputs = {"claude": [sheet_from_result(result_raw), result_raw, revised, final], "codex": [review]}
        result = run_round_robin_decomposition(
            source=source, output_root=output_root, task_id="NSC-010",
            provider_order=("claude", "codex"), max_calls=budget, run_id=run_id,
            provider_factory=factory({name: QueueProvider(items) for name, items in outputs.items()}),
            _require_physical_read_only_source=False, bookkeeper_model=self.MODEL,
        )
        self.assertEqual("review_ready", result["run_status"], result["rejection_reasons"])
        head = _git(source, "rev-parse", "HEAD")
        record = {
            "schema_version": "assistant-decomposition/v1", "task_id": "NSC-010", "run_id": run_id,
            "source": str(source.resolve()), "source_commit": head,
            "source_tree": _git(source, "rev-parse", "HEAD^{tree}"),
            "source_branch": _git(source, "branch", "--show-current"),
            "task_contract_sha256": load_committed_task(source, "NSC-010", commit=head)["task_contract_sha256"],
            "providers": ["claude", "codex"], "max_calls": budget,
            "output_root": str(output_root), "artifact_root": str(output_root / run_id),
            "status": "review_ready",
            "timeout_profile": {"task_decomposer": 1440, "decomposition_reviewer": 1200},
            "bookkeeper_provider": "claude", "designer_bookkeeper_version": "2.0",
            "ownership_sheet_review_version": "1.1",
            **({} if record_model is None else {"bookkeeper_model": record_model}),
        }
        return manager, record, output_root / run_id

    def test_the_outer_timeout_covers_every_call_a_bookkeeper_run_may_make(self):
        from Pipeline.AssistantControl.decomposition import bookkeeper_outer_timeout, continuation_outer_timeout
        self.assertEqual(3 * 1200 + 720, continuation_outer_timeout(3))
        self.assertEqual(6 * 1440 + 1200 + 720, bookkeeper_outer_timeout(2, None))
        self.assertEqual(8 * 100 + 2 * 50 + 720,
                         bookkeeper_outer_timeout(3, {"task_decomposer": 100, "decomposition_reviewer": 50}))

    def test_a_two_call_bookkeeper_run_is_accepted_with_its_evidence(self):
        manager, record, _ = self.produce()
        review = _verify_review(manager, record)
        self.assertEqual(1, review["bookkeeping"]["attempts"])
        self.assertIn("rounds/01/ownership_sheet.json", review["artifact_sha256"])

    def test_a_three_call_bookkeeper_run_is_accepted_with_its_evidence(self):
        manager, record, _ = self.produce(budget=3)
        review = _verify_review(manager, record)
        self.assertEqual(self.MODEL, review["bookkeeping"]["bookkeeper_model"])
        self.assertIn("rounds/01/ownership_sheet.json", review["artifact_sha256"])

    def test_a_recompiled_revision_is_accepted_with_every_compilation_proof(self):
        manager, record, _ = self.produce(budget=3, revision=True)
        review = _verify_review(manager, record)
        self.assertEqual(2, review["bookkeeping"]["bookkeeping_calls_used"])
        self.assertEqual("claude", review["reviewer_provider"])
        self.assertEqual(2, review["bookkeeping"]["latest_sheet"]["round_number"])
        for relative in ("rounds/02/ownership_sheet.json", "rounds/02/bookkeeping_input.json",
                         "rounds/02-bookkeeper-1/bookkeeping_attempt.json", "rounds/03/review.json"):
            self.assertIn(relative, review["artifact_sha256"])

    def test_a_record_and_run_that_disagree_about_the_bookkeeper_are_refused(self):
        for model in (None, "another-model"):
            with self.subTest(model=model):
                manager, record, _ = self.produce(record_model=model)
                with self.assertRaisesRegex(ValueError, "Decomposition bookkeeper model is"):
                    _verify_review(manager, record)

    def test_a_bookkeeper_output_that_is_not_the_candidate_is_refused(self):
        manager, record, run_dir = self.produce()
        result_path = next((run_dir / "rounds" / "01-bookkeeper-1" / "agent_runtime").glob("*/result.json"))
        value = json.loads(result_path.read_text(encoding="utf-8"))
        value["structured_output"]["children"][0]["notes"] += " Changed after the fact."
        result_path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "bookkeeping|BOOKKEEPING"):
            _verify_review(manager, record)

    def test_v2_protocol_settings_cannot_be_removed_or_downgraded(self):
        for field, replacement in (("designer_bookkeeper_version", None),
                                   ("designer_bookkeeper_version", "1.0"),
                                   ("ownership_sheet_review_version", None),
                                   ("bookkeeper_provider", "codex")):
            with self.subTest(field=field, replacement=replacement):
                manager, record, _ = self.produce()
                if replacement is None:
                    record.pop(field)
                else:
                    record[field] = replacement
                with self.assertRaisesRegex(ValueError, "protocol or fixed provider"):
                    _verify_review(manager, record)

    def test_v2_request_settings_and_proof_manifest_are_pinned(self):
        from Pipeline.AssistantControl.decomposition import _require_pinned_proof
        manager, record, run_dir = self.produce()
        review = _verify_review(manager, record)
        manifest = review["artifact_sha256"]
        for relative in ("context.json", "decomposition_request.json", "rounds/01/bookkeeping_input.json",
                         "rounds/01-bookkeeper-1/bookkeeping_attempt.json", "rounds/02/review.json"):
            self.assertIn(relative, manifest)
        record["review"] = review
        changed = deepcopy(review)
        changed["artifact_sha256"]["rounds/02/review.json"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "proof bytes changed"):
            _require_pinned_proof(record, changed)
        request_path = run_dir / "decomposition_request.json"
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request.pop("ownership_sheet_review_version")
        request_path.write_text(json.dumps(request), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "ownership_sheet_review_version"):
            _verify_review(manager, record)

    def test_bookkeeper_timeout_profile_accepts_and_pins_custom_timeouts(self):
        from Pipeline.AssistantControl.decomposition import three_call_timeout_profile
        environment = {"NSC_TASK_DECOMPOSER_TIMEOUT_SECONDS": "1800",
                       "NSC_DECOMPOSITION_REVIEWER_TIMEOUT_SECONDS": "1400"}
        self.assertEqual({"task_decomposer": 1800, "decomposition_reviewer": 1400},
                         three_call_timeout_profile(environment, bookkeeper=True))
        with self.assertRaisesRegex(ValueError, "outer bound"):
            three_call_timeout_profile(environment)

    def test_retained_request_refuses_bookkeeper_continuation_after_result_markers_are_removed(self):
        from TaskDecomposition.continuation import continuable_problem
        prior = {"run_status": "needs_human", "latest_candidate": {"sha256": "a" * 64},
                 "unresolved_findings": [{"finding_id": "round-02-a"}]}
        prior["rounds"] = [{"status": "revised_candidate_valid", "candidate_after": prior["latest_candidate"]}]
        self.assertIsNone(continuable_problem(prior))
        for key, value in (("bookkeeper_model", "compiler"), ("bookkeeper_provider", "claude"),
                           ("designer_bookkeeper_version", "2.0"), ("ownership_sheet_review_version", "1.1")):
            with self.subTest(marker=key):
                self.assertIn("fresh run is required", continuable_problem(prior, request={key: value}))

    def test_bookkeeper_continuation_is_refused_before_archiving(self):
        from Pipeline.AssistantControl.decomposition import _prepare_continuation, _record_path
        from TaskDecomposition.continuation import continuable_problem
        manager, record, run_dir = self.produce()
        path = _record_path(manager, "NSC-010")
        record["status"] = "failed"
        write_record(path, record)
        before = path.read_bytes()
        for evidence in ({}, {"schema_version": "2.0"}):
            self.assertIn("fresh run is required", continuable_problem({"designer_bookkeeper": evidence}))
        with self.assertRaisesRegex(ValueError, "fresh run is required"):
            _prepare_continuation(manager, "NSC-010", record["run_id"], record["providers"],
                                  run_dir.parent, record["source_commit"])
        self.assertEqual(before, path.read_bytes())
        self.assertFalse(list(path.parent.glob("*.failed.archived.json")))


class ContinuationReviewTests(unittest.TestCase):
    """A continuation is applicable only when its whole chain verifies."""

    def produce(self):
        from copy import deepcopy
        from TaskDecomposition.continuation import run_continuation
        from TaskDecomposition.round_robin_decomposition import run_round_robin_decomposition
        from TaskDecomposition.tests.review_chain_smoke_test import factory
        from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (
            QueueProvider, pass_review, revise_review, validated_candidate,
        )
        from TaskDecomposition.tests.test_support import decomposed_result

        temporary = tempfile.TemporaryDirectory(prefix="assistant-continuation-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source"
        source.mkdir()
        tasks = create_repository(source)
        manager = Checkouts(source, root / "checkouts")
        output_root = (manager.records / "decomposition-runs").resolve()
        output_root.mkdir(parents=True)
        parent = tasks["NSC-010"]
        versions = [decomposed_result(parent)]
        for index in (1, 2):
            revised = deepcopy(versions[0])
            revised["children"][0]["notes"] = f"Reviewer revision {index}."
            versions.append(revised)
        hashes = [candidate_sha256(validated_candidate(v, parent, tasks)) for v in versions]
        resolved = lambda finding: [{"finding_id": finding, "status": "resolved", "explanation": "Replaced."}]
        order = ("claude", "codex")
        prior = run_round_robin_decomposition(
            source=source, output_root=output_root, task_id="NSC-010", provider_order=order, max_calls=3,
            run_id="stopped-run", _require_physical_read_only_source=False,
            provider_factory=factory({
                "claude": QueueProvider([versions[0], revise_review(
                    hashes[1], versions[2], round_number=3, suffix="b", resolutions=resolved("round-02-a"))]),
                "codex": QueueProvider([revise_review(hashes[0], versions[1], round_number=2, suffix="a")]),
            }))
        self.assertEqual("needs_human", prior["run_status"])
        result = run_continuation(
            source=source, output_root=output_root, task_id="NSC-010", continue_from="stopped-run",
            provider_order=order, max_calls=4, run_id="continued-run", _require_physical_read_only_source=False,
            provider_factory=factory({
                "codex": QueueProvider([pass_review(hashes[2], resolutions=resolved("round-03-b"))]),
                "claude": QueueProvider([])}))
        self.assertEqual("review_ready", result["run_status"], result["rejection_reasons"])
        head = _git(source, "rev-parse", "HEAD")
        record = {
            "schema_version": "assistant-decomposition/v1", "task_id": "NSC-010", "run_id": "continued-run",
            "source": str(source.resolve()), "source_commit": head,
            "source_tree": _git(source, "rev-parse", "HEAD^{tree}"),
            "source_branch": _git(source, "branch", "--show-current"),
            "task_contract_sha256": load_committed_task(source, "NSC-010", commit=head)["task_contract_sha256"],
            "providers": list(order), "max_calls": 4, "continue_from": "stopped-run",
            "output_root": str(output_root), "artifact_root": str(output_root / "continued-run"),
            "status": "review_ready",
        }
        return manager, record, output_root

    def test_a_continuation_verifies_across_the_whole_chain(self):
        manager, record, _ = self.produce()
        review = _verify_review(manager, record)
        self.assertEqual(["stopped-run"], review["continued_runs"])
        self.assertEqual("codex", review["reviewer_provider"])
        self.assertIn("stopped-run/decomposition_run_result.json", review["artifact_sha256"])

    def test_an_edited_prior_run_breaks_the_chain(self):
        manager, record, output_root = self.produce()
        path = output_root / "stopped-run" / "decomposition_run_result.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["duration_seconds"] = 1.0
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not continue exactly the verified prior run"):
            _verify_review(manager, record)

    def test_a_continuation_record_naming_another_prior_is_refused(self):
        manager, record, _ = self.produce()
        with self.assertRaisesRegex(ValueError, "continues another run than its record names"):
            _verify_review(manager, dict(record, continue_from="some-other-run"))

    def test_a_continuation_of_any_budget_must_match_its_recorded_proof(self):
        from Pipeline.AssistantControl.decomposition import _require_pinned_proof
        manager, record, _ = self.produce()
        review = _verify_review(manager, record)
        for budget in (1, 2, 4):
            pinned = dict(record, max_calls=budget, review=review)
            _require_pinned_proof(pinned, review)
            changed = dict(review, artifact_sha256=dict(review["artifact_sha256"], extra="0" * 64))
            with self.assertRaisesRegex(ValueError, "proof bytes changed since the review was recorded"):
                _require_pinned_proof(pinned, changed)
            with self.assertRaisesRegex(ValueError, "carries no recorded proof"):
                _require_pinned_proof(dict(record, max_calls=budget), review)

    def test_only_the_stopped_runs_own_failed_record_is_archived(self):
        from Pipeline.AssistantControl.decomposition import _prepare_continuation, _record_path
        manager, record, output_root = self.produce()
        head = record["source_commit"]
        path = _record_path(manager, "NSC-010")
        ident = {"schema_version": record["schema_version"], "task_id": "NSC-010", "source": str(manager.source)}
        path.write_text(json.dumps(dict(ident, run_id="stopped-run", status="failed")), encoding="utf-8")
        _prepare_continuation(manager, "NSC-010", "stopped-run", ["claude", "codex"], output_root, head)
        self.assertFalse(path.exists())
        self.assertTrue(path.with_name("NSC-010.decomposition.stopped-run.failed.archived.json").is_file())
        path.write_text(json.dumps(dict(ident, run_id="someone-else", status="running")), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "it was preserved"):
            _prepare_continuation(manager, "NSC-010", "stopped-run", ["claude", "codex"], output_root, head)
        self.assertTrue(path.exists())
        with self.assertRaisesRegex(ValueError, "cannot be continued"):
            _prepare_continuation(manager, "NSC-010", "continued-run", ["claude", "codex"], output_root, head)


class ThreeCallBudgetTests(unittest.TestCase):
    """The opt-in budget-3 profile, verified from producer-shaped runs."""

    def produce(self, *, revise: bool, budget: int = 3):
        from copy import deepcopy
        from TaskDecomposition.round_robin_decomposition import run_round_robin_decomposition
        from TaskDecomposition.tests.review_chain_smoke_test import factory
        from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (
            QueueProvider, pass_review, revise_review, validated_candidate,
        )
        from TaskDecomposition.tests.test_support import decomposed_result

        temporary = tempfile.TemporaryDirectory(prefix="assistant-budget-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source"
        source.mkdir()
        tasks = create_repository(source)
        manager = Checkouts(source, root / "checkouts")
        output_root = (manager.records / "decomposition-runs").resolve()
        output_root.mkdir(parents=True)
        parent = tasks["NSC-010"]
        initial = decomposed_result(parent)
        initial_hash = candidate_sha256(validated_candidate(initial, parent, tasks))
        revised = deepcopy(initial)
        revised["children"][0]["notes"] = "Independent reviewer revision."
        revised_hash = candidate_sha256(validated_candidate(revised, parent, tasks))
        if revise:
            outputs = {"claude": [initial, pass_review(revised_hash, resolutions=[
                {"finding_id": "round-02-a", "status": "resolved", "explanation": "Replaced."}])],
                "codex": [revise_review(initial_hash, revised, round_number=2, suffix="a")]}
        else:
            outputs = {"claude": [initial], "codex": [pass_review(initial_hash)]}
        run_id = "budget-three"
        result = run_round_robin_decomposition(
            source=source, output_root=output_root, task_id="NSC-010",
            provider_order=("claude", "codex"), max_calls=3, run_id=run_id,
            provider_factory=factory({name: QueueProvider(items) for name, items in outputs.items()}),
            _require_physical_read_only_source=False,
        )
        self.assertEqual("review_ready", result["run_status"], result["rejection_reasons"])
        head = _git(source, "rev-parse", "HEAD")
        record = {
            "schema_version": "assistant-decomposition/v1", "task_id": "NSC-010", "run_id": run_id,
            "source": str(source.resolve()), "source_commit": head,
            "source_tree": _git(source, "rev-parse", "HEAD^{tree}"),
            "source_branch": _git(source, "branch", "--show-current"),
            "task_contract_sha256": load_committed_task(source, "NSC-010", commit=head)["task_contract_sha256"],
            "providers": ["claude", "codex"], "max_calls": budget,
            "output_root": str(output_root), "artifact_root": str(output_root / run_id),
            "status": "review_ready",
            **({"timeout_profile": {"task_decomposer": 1440, "decomposition_reviewer": 1200}}
               if budget == 3 else {}),
        }
        return manager, record, output_root / run_id

    def test_a_revision_passed_by_the_other_provider_is_accepted(self):
        manager, record, _ = self.produce(revise=True)
        review = _verify_review(manager, record)
        self.assertEqual((3, 3, "claude"), (review["call_budget"], review["calls_used"], review["reviewer_provider"]))
        self.assertIn("rounds/02/review.json", review["artifact_sha256"])
        self.assertIn("rounds/03/review.json", review["artifact_sha256"])

    def test_an_early_pass_under_budget_three_is_accepted(self):
        manager, record, _ = self.produce(revise=False)
        review = _verify_review(manager, record)
        self.assertEqual((3, 2, "codex"), (review["call_budget"], review["calls_used"], review["reviewer_provider"]))

    def test_a_two_call_record_does_not_accept_a_three_call_run(self):
        manager, record, _ = self.produce(revise=True, budget=2)
        with self.assertRaisesRegex(ValueError, "max_calls is 3, expected 2"):
            _verify_review(manager, record)

    def test_an_unsupported_record_budget_is_refused(self):
        manager, record, _ = self.produce(revise=True)
        for budget in (4, True, "3"):
            with self.subTest(budget=budget), self.assertRaisesRegex(ValueError, "unsupported call budget"):
                _verify_review(manager, dict(record, max_calls=budget))

    def test_a_same_provider_run_cannot_request_budget_three(self):
        root = Path(tempfile.mkdtemp(prefix="assistant-budget-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "source").mkdir()
        create_repository(root / "source")
        manager = Checkouts(root / "source", root / "checkouts")
        for providers, budget, message in (
                ("codex,codex", 3, "requires two distinct providers"),
                ("claude,codex", 4, "must be 2 or 3")):
            with self.subTest(providers=providers), self.assertRaisesRegex(ValueError, message):
                run(manager, "NSC-004", "nsc-004-run", providers=providers,
                    execution_authorized=True, max_calls=budget)
        self.assertFalse(manager.records.exists() and any(manager.records.iterdir()))

    def test_a_budget_three_record_needs_a_valid_timeout_profile(self):
        manager, record, _ = self.produce(revise=True)
        for profile in (None, {"task_decomposer": 1440}, {"task_decomposer": 1440, "decomposition_reviewer": 0}):
            with self.subTest(profile=profile), self.assertRaisesRegex(ValueError, "no valid timeout profile"):
                changed = dict(record)
                changed.pop("timeout_profile")
                if profile is not None:
                    changed["timeout_profile"] = profile
                _verify_review(manager, changed)
        with self.assertRaisesRegex(ValueError, "D3_TIMEOUT"):
            _verify_review(manager, dict(record, timeout_profile={
                "task_decomposer": 1440, "decomposition_reviewer": 900}))

    def test_a_run_request_for_another_budget_or_run_is_refused(self):
        for field, value, name in (("max_calls", 2, "request max_calls"), ("run_id", "x", "request run_id")):
            with self.subTest(field=field):
                manager, record, run_dir = self.produce(revise=True)
                path = run_dir / "decomposition_request.json"
                request = json.loads(path.read_text(encoding="utf-8"))
                request[field] = value
                path.write_text(json.dumps(request), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, f"evidence disagrees: {name}"):
                    _verify_review(manager, record)

    def test_a_stopped_budget_three_run_reports_its_status(self):
        manager, record, run_dir = self.produce(revise=True)
        path = run_dir / "decomposition_run_result.json"
        result = json.loads(path.read_text(encoding="utf-8"))
        result["run_status"] = "needs_human"
        path.write_text(json.dumps(result), encoding="utf-8")
        (run_dir / "decomposition_result.json").unlink()
        with self.assertRaisesRegex(ValueError, "ended 'needs_human'; it has no applicable result"):
            _verify_review(manager, record)

    def test_the_timeout_preflight_bounds_the_whole_chain(self):
        from Pipeline.AssistantControl.decomposition import three_call_timeout_profile
        self.assertEqual({"task_decomposer": 1440, "decomposition_reviewer": 1200},
                         three_call_timeout_profile({}))
        with self.assertRaisesRegex(ValueError, "over the 6000 s outer bound"):
            three_call_timeout_profile({"NSC_TASK_DECOMPOSER_TIMEOUT_SECONDS": "1500"})
        for bad in ("0", "-5", "ten"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                three_call_timeout_profile({"NSC_DECOMPOSITION_REVIEWER_TIMEOUT_SECONDS": bad})

    def test_changed_proof_bytes_are_refused_at_inspection_too(self):
        from Pipeline.AssistantControl.decomposition import inspect
        manager, record, run_dir = self.produce(revise=True)
        record["review"] = _verify_review(manager, record)
        write_record(manager.records / "NSC-010.decomposition.json", record)
        self.assertEqual(record["review"]["artifact_sha256"], inspect(manager, "NSC-010")["review"]["artifact_sha256"])
        (run_dir / "rounds" / "03" / "review_history_entry.json").write_text(
            (run_dir / "rounds" / "03" / "review_history_entry.json").read_text(encoding="utf-8") + " ",
            encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "proof bytes changed"):
            inspect(manager, "NSC-010")

    def test_a_missing_recorded_proof_is_refused_by_inspect_and_apply(self):
        from Pipeline.AssistantControl.decomposition import inspect
        manager, record, _ = self.produce(revise=True)
        write_record(manager.records / "NSC-010.decomposition.json", record)
        with self.assertRaisesRegex(ValueError, "carries no recorded proof"):
            inspect(manager, "NSC-010")
        with patch.dict(os.environ, {
            "NSC_AGENT_GIT_NAME": "No Safe Circle TaskReviewAgent",
            "NSC_AGENT_GIT_EMAIL": "task-review-agent@nosafecircle.invalid",
        }), self.assertRaisesRegex(ValueError, "carries no recorded proof"):
            apply(manager, "NSC-010", run_id=record["run_id"],
                  expected_source_commit=record["source_commit"], target_branch=record["source_branch"])

    def test_proof_bytes_changed_after_review_are_refused_at_apply(self):
        manager, record, run_dir = self.produce(revise=True)
        record["review"] = _verify_review(manager, record)
        write_record(manager.records / "NSC-010.decomposition.json", record)
        entry_path = run_dir / "rounds" / "03" / "review_history_entry.json"
        entry_path.write_text(entry_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with patch.dict(os.environ, {
            "NSC_AGENT_GIT_NAME": "No Safe Circle TaskReviewAgent",
            "NSC_AGENT_GIT_EMAIL": "task-review-agent@nosafecircle.invalid",
        }), self.assertRaisesRegex(ValueError, "proof bytes changed"):
            apply(manager, "NSC-010", run_id=record["run_id"],
                  expected_source_commit=record["source_commit"], target_branch=record["source_branch"])


class BoundedAuthorCorrectionReviewTests(unittest.TestCase):
    """Apply admits the uncorrected pair and exactly one bounded author correction.

    A corrected `review_ready` run retains its deterministically rejected first
    round, so its `rounds` list is three entries long and the round that
    authored the reviewed candidate is the correction. Every other shape stays
    refused, including a run that claims a correction it does not carry.
    """

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="assistant-d1c-correction-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source"
        source.mkdir()
        create_repository(source)
        self.task_id = "NSC-004"
        task_path = source / "Tasks" / f"{self.task_id}.yaml"
        selected = json.loads(task_path.read_text(encoding="utf-8"))
        selected.update(
            execution_scope="needs_execution_decomposition",
            execution_reason="Synthetic bounded-correction regression requires decomposition.",
        )
        _write_json(task_path, selected)
        _git(source, "add", "--", f"Tasks/{self.task_id}.yaml")
        _git(source, "commit", "-m", "fixture: select childless decomposition parent")
        graph = load_persistent_work_graph(source)
        parent = graph.tasks_by_id[self.task_id]
        proposal = decomposed_result(parent)
        proposal["children"][0]["exclusive_resources"] = []
        proposal["inbound_dependency_rewrites"] = []
        decomposition = validate_decomposition_result(
            proposal,
            parent_task=parent,
            existing_reconciliation_keys=graph.plan.id_map,
        )
        stored_plan = plan_graph_delta(graph, decomposition.parent_task, decomposition)
        head = _git(source, "rev-parse", "HEAD")
        tree = _git(source, "rev-parse", "HEAD^{tree}")
        branch = _git(source, "branch", "--show-current")
        task = load_committed_task(source, self.task_id, commit=head)
        self.manager = Checkouts(source, root / "checkouts")
        self.manager.records.mkdir(parents=True)

        run_id = "fixture-corrected-decomposition"
        output_root = (self.manager.records / "decomposition-runs").resolve()
        self.artifact_root = output_root / run_id
        self.artifact_root.mkdir(parents=True)
        _write_json(self.artifact_root / "decomposition_result.json", decomposition.to_dict())
        _write_json(self.artifact_root / "graph_delta.json", stored_plan.to_dict())
        self.digest = candidate_sha256(decomposition)
        self.candidate = {
            "version": 1,
            "author_provider": "claude",
            "sha256": self.digest,
            "decision": "decomposed",
            "graph_delta_plan_id": stored_plan.plan_id,
        }
        self.run_result = {
            "schema_version": "1.0",
            "mode": "round_robin_d1b2",
            "run_id": run_id,
            "task_id": self.task_id,
            "provider_order": ["claude", "codex"],
            "max_calls": 2,
            "calls_used": 2,
            "run_status": "review_ready",
            "decision": "decomposed",
            "review_independence": "cross_provider",
            "authority": "review_only_not_applied",
            "unresolved_findings": [],
            "rejection_reasons": [],
            "source_identity": {"head_commit": head, "head_tree": tree},
            "task_execution_contract_identity": {
                "revision": task["contract_revision"],
                "sha256": task["task_contract_sha256"],
            },
            "latest_candidate": self.candidate,
            "independent_approver_provider": "codex",
            "finding_history": [{
                "verdict": "pass",
                "reviewed_candidate_sha256": self.digest,
                "findings": [],
            }],
        }
        self.record = {
            "schema_version": "assistant-decomposition/v1",
            "task_id": self.task_id,
            "run_id": run_id,
            "source": str(source.resolve()),
            "source_commit": head,
            "source_tree": tree,
            "source_branch": branch,
            "task_contract_sha256": task["task_contract_sha256"],
            "providers": ["claude", "codex"],
            "output_root": str(output_root),
            "artifact_root": str(self.artifact_root),
            "status": "review_ready",
        }

    # -- exact round fixtures ---------------------------------------------

    def author_round(self, **overrides) -> dict:
        return {"role": "task_decomposer", "correction_of_round": None,
                "requested_provider": "claude", "actual_model": "fixture-author",
                "agent_status": "succeeded", "status": "candidate_valid",
                "candidate_after": self.candidate, **overrides}

    def rejected_round(self, **overrides) -> dict:
        return {"role": "task_decomposer", "correction_of_round": None,
                "requested_provider": "claude", "actual_model": "fixture-author",
                "agent_status": "succeeded", "status": "rejected",
                "candidate_after": None,
                "rejection_reasons": [
                    "initial candidate deterministic validation failed: fixture rejection",
                ],
                **overrides}

    def correction_round(self, **overrides) -> dict:
        return {"role": "task_decomposer", "correction_of_round": 1,
                "requested_provider": "claude", "actual_model": "fixture-correction",
                "agent_status": "succeeded", "status": "correction_candidate_valid",
                "candidate_after": self.candidate, **overrides}

    def reviewer_round(self, **overrides) -> dict:
        return {"role": "decomposition_reviewer", "correction_of_round": None,
                "requested_provider": "codex", "actual_model": "fixture-reviewer",
                "agent_status": "succeeded", "status": "independent_pass",
                "verdict": "pass", "candidate_before": self.candidate,
                "candidate_after": None, **overrides}

    def verify(self, rounds, **run_fields) -> dict:
        _write_json(
            self.artifact_root / "decomposition_run_result.json",
            {**self.run_result, "rounds": rounds, **run_fields},
        )
        return _verify_review(self.manager, self.record)

    # -- accepted shapes ---------------------------------------------------

    def test_uncorrected_author_reviewer_pair_still_verifies(self):
        review = self.verify([self.author_round(), self.reviewer_round()])
        self.assertEqual("review_ready", review["status"])
        self.assertEqual(self.digest, review["candidate_sha256"])
        self.assertEqual(["fixture-author", "fixture-reviewer"], review["models"])
        # An explicit zero count is the same uncorrected run.
        self.assertEqual(review["candidate_sha256"], self.verify(
            [self.author_round(), self.reviewer_round()], author_corrections_used=0,
        )["candidate_sha256"])

    def test_one_bounded_correction_between_the_rounds_verifies(self):
        review = self.verify(
            [self.rejected_round(), self.correction_round(), self.reviewer_round()],
            author_corrections_used=1,
        )
        self.assertEqual("review_ready", review["status"])
        self.assertEqual(self.digest, review["candidate_sha256"])
        # The correction, not the rejected first round, authored the candidate
        # the independent reviewer passed.
        self.assertEqual(["fixture-correction", "fixture-reviewer"], review["models"])
        self.assertEqual(
            self.verify([self.author_round(), self.reviewer_round()])["child_ids"],
            review["child_ids"],
        )

    # -- refused shapes ----------------------------------------------------

    def test_correction_with_the_wrong_status_is_refused(self):
        with self.assertRaisesRegex(ValueError, "exact independent author/reviewer pass"):
            self.verify(
                [self.rejected_round(),
                 self.correction_round(status="candidate_valid"),
                 self.reviewer_round()],
                author_corrections_used=1,
            )

    def test_correction_without_author_corrections_used_is_refused(self):
        with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
            self.verify(
                [self.rejected_round(), self.correction_round(), self.reviewer_round()],
            )
        with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
            self.verify(
                [self.rejected_round(), self.correction_round(), self.reviewer_round()],
                author_corrections_used=0,
            )

    def test_uncorrected_pair_may_not_claim_a_correction(self):
        with self.assertRaisesRegex(ValueError, "counts an author correction"):
            self.verify(
                [self.author_round(), self.reviewer_round()], author_corrections_used=1,
            )

    def test_a_second_correction_entry_is_refused(self):
        with self.assertRaisesRegex(ValueError, "exactly one author and one reviewer round"):
            self.verify(
                [self.rejected_round(), self.correction_round(),
                 self.correction_round(), self.reviewer_round()],
                author_corrections_used=1,
            )
        # Three rounds whose last entry is a second correction rather than the
        # independent reviewer are refused by the reviewer checks.
        with self.assertRaisesRegex(ValueError, "exact independent author/reviewer pass"):
            self.verify(
                [self.rejected_round(), self.correction_round(), self.correction_round()],
                author_corrections_used=1,
            )

    def test_correction_must_follow_a_round_that_produced_no_candidate(self):
        with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
            self.verify(
                [self.author_round(), self.correction_round(), self.reviewer_round()],
                author_corrections_used=1,
            )
        with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
            self.verify(
                [self.rejected_round(correction_of_round=1),
                 self.correction_round(), self.reviewer_round()],
                author_corrections_used=1,
            )

    def test_correction_must_name_the_round_it_corrects(self):
        with self.assertRaisesRegex(ValueError, "exact independent author/reviewer pass"):
            self.verify(
                [self.rejected_round(),
                 self.correction_round(correction_of_round=2),
                 self.reviewer_round()],
                author_corrections_used=1,
            )

    def test_a_reviewer_round_may_not_be_a_correction(self):
        with self.assertRaisesRegex(ValueError, "exact independent author/reviewer pass"):
            self.verify(
                [self.rejected_round(), self.correction_round(),
                 self.reviewer_round(correction_of_round=1)],
                author_corrections_used=1,
            )

    def test_correction_from_another_provider_is_refused(self):
        """The correction is the author's own call: another provider cannot author it."""
        with self.assertRaisesRegex(ValueError, "exact independent author/reviewer pass"):
            self.verify(
                [self.rejected_round(), self.correction_round(requested_provider="codex"),
                 self.reviewer_round()],
                author_corrections_used=1,
            )

    def test_boolean_correction_counts_are_refused(self):
        """`author_corrections_used` is an exact integer; JSON booleans are not counts."""
        with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
            self.verify(
                [self.rejected_round(), self.correction_round(), self.reviewer_round()],
                author_corrections_used=True,
            )
        with self.assertRaisesRegex(ValueError, "counts an author correction"):
            self.verify(
                [self.author_round(), self.reviewer_round()],
                author_corrections_used=False,
            )

    def test_rejected_first_round_must_retain_its_rejection(self):
        """The retained round 1 carries the exact deterministic rejection the correction answered."""
        for rejections in ([], None, ["", "x"], "not a list"):
            with self.subTest(rejection_reasons=rejections):
                with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
                    self.verify(
                        [self.rejected_round(rejection_reasons=rejections),
                         self.correction_round(), self.reviewer_round()],
                        author_corrections_used=1,
                    )
        absent = self.rejected_round()
        del absent["rejection_reasons"]
        with self.assertRaisesRegex(ValueError, "exactly one bounded author correction"):
            self.verify([absent, self.correction_round(), self.reviewer_round()],
                        author_corrections_used=1)


POOL_REPOSITORY = "https://example.invalid/NoSafeCircle.git"

def _resolve_unpooled(decomposition_module, provider_order):
    """The unpooled model resolution, with the two model variables pinned."""
    with patch.dict(os.environ, {"NSC_CLAUDE_MODEL": "claude-opus-5",
                                 "NSC_OPENAI_CODEX_MODEL": "gpt-6-astra"}):
        return decomposition_module._unpooled_provider_environment(provider_order)

POOL_MODEL = "claude-fixture-5"
POOL_LEASE_IDS = {
    "claude:task_decomposer": "11111111-1111-4111-8111-111111111111",
    "claude:decomposition_reviewer": "22222222-2222-4222-8222-222222222222",
}


def _decomposition_parent_fixture(test: unittest.TestCase, prefix: str) -> tuple[Checkouts, str]:
    """One committed childless decomposition parent with a configured origin."""

    temporary = tempfile.TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=True)
    test.addCleanup(temporary.cleanup)
    root = Path(temporary.name)
    source = root / "source"
    source.mkdir()
    create_repository(source)
    _git(source, "remote", "add", "origin", POOL_REPOSITORY)
    task_path = source / "Tasks" / "NSC-004.yaml"
    selected = json.loads(task_path.read_text(encoding="utf-8"))
    selected.update(
        execution_scope="needs_execution_decomposition",
        execution_reason="Synthetic pooled-decomposition regression requires decomposition.",
    )
    _write_json(task_path, selected)
    _git(source, "add", "--", "Tasks/NSC-004.yaml")
    _git(source, "commit", "-m", "fixture: childless decomposition parent")
    return Checkouts(source, root / "checkouts"), _git(source, "rev-parse", "HEAD")


class PooledSameProviderLaunchTests(unittest.TestCase):
    """`claude,claude` reserves two role sessions and launches with them mounted."""

    def test_same_provider_launch_reserves_role_leases_and_pins_the_model(self):
        from Pipeline.AssistantControl import decomposition as decomposition_module
        from Pipeline.AssistantControl.decomposition_transport import POOL_LEASE_MOUNT

        manager, head = _decomposition_parent_fixture(self, "assistant-decompose-pooled-")
        commands: list[list[str]] = []
        real_run = subprocess.run

        def fake_run(command, *args, **kwargs):
            if list(command)[:2] == ["docker", "compose"]:
                commands.append(list(command))
                return subprocess.CompletedProcess(command, 1)
            return real_run(command, *args, **kwargs)

        with patch.dict(os.environ, {"NSC_CLAUDE_MODEL": POOL_MODEL}), \
                patch.object(decomposition_module, "decomposition_preflight",
                             return_value={"source_commit": head}), \
                patch.object(decomposition_module.subprocess, "run", side_effect=fake_run):
            record = decomposition_module.run(
                manager, "NSC-004", "nsc-004-pooled-run", providers="claude,claude",
                compose_project="assistant-pool", execution_authorized=True,
            )

        self.assertEqual(["claude", "claude"], record["providers"])
        pool = record["pool"]
        self.assertEqual(
            ["claude:decomposition_reviewer", "claude:task_decomposer"],
            sorted(pool["lease_keys"]),
        )
        self.assertEqual(POOL_REPOSITORY, pool["repository_identity"])
        self.assertTrue(pool["checkout_identity"].startswith("manifest-sha256:"))
        # The manifest whose bytes are that identity is AssistantControl's own
        # record, never a file inside Source.
        manifest = manager.records / "decomposition-pool" / "checkout-identity.json"
        self.assertTrue(manifest.is_file())
        self.assertFalse((manager.source / ".task-review-agent").exists())

        bundle = Path(pool["lease_bundle_path"])
        payload = json.loads(bundle.read_text(encoding="utf-8"))
        self.assertEqual("nsc-004-pooled-run", payload["run_id"])
        self.assertEqual("NSC-004", payload["task_id"])
        self.assertEqual(head, payload["source_commit"])
        self.assertEqual(POOL_REPOSITORY, payload["repository_identity"])
        self.assertEqual(sorted(pool["lease_keys"]), sorted(payload["leases"]))
        self.assertIsNone(payload["codex_resume_sandbox_argument"])

        self.assertEqual(1, len(commands))
        command = commands[0]
        self.assertEqual(
            ["docker", "compose", "-p", "assistant-pool", "run", "--rm", "-T"], command[:7],
        )
        self.assertEqual(["--volume", f"{bundle}:{POOL_LEASE_MOUNT}:ro"], command[7:9])
        self.assertEqual(["--env", f"NSC_CLAUDE_MODEL={POOL_MODEL}"], command[9:11])
        self.assertEqual("round-robin-decompose", command[11])
        self.assertEqual("claude,claude", command[command.index("--providers") + 1])
        self.assertEqual(POOL_LEASE_MOUNT, command[command.index("--role-session-leases") + 1])
        self.assertEqual(
            POOL_REPOSITORY, command[command.index("--scheduler-repository-identity") + 1],
        )
        self.assertEqual("failed", record["status"])

    def test_cross_provider_launch_reserves_nothing(self):
        from Pipeline.AssistantControl import decomposition as decomposition_module

        manager, head = _decomposition_parent_fixture(self, "assistant-decompose-cross-")
        commands: list[list[str]] = []
        real_run = subprocess.run

        def fake_run(command, *args, **kwargs):
            if list(command)[:2] == ["docker", "compose"]:
                commands.append(list(command))
                return subprocess.CompletedProcess(command, 1)
            return real_run(command, *args, **kwargs)

        with patch.object(decomposition_module, "decomposition_preflight",
                          return_value={"source_commit": head}), \
                patch.object(decomposition_module.subprocess, "run", side_effect=fake_run):
            record = decomposition_module.run(
                manager, "NSC-004", "nsc-004-cross-run", providers="claude,codex",
                compose_project="assistant-pool", execution_authorized=True,
            )
        self.assertIsNone(record.get("pool"))
        self.assertIsNone(record.get("pool_lifecycle"))
        self.assertNotIn("--volume", commands[0])
        self.assertNotIn("--role-session-leases", commands[0])

    def test_cross_provider_launch_carries_both_resolved_models(self):
        """The caller half of the mixed-provider model gap.

        Fixing the transport alone would have proved nothing: the defect was
        that ``decomposition.py`` passed no model at all for a mixed pair, so
        the container re-resolved ``provider_configuration`` with none of the
        host's environment and got ``claude-sonnet-5`` and ``gpt-5.6-sol``. The
        run then reported success at a model nobody chose.
        """
        from Pipeline.AssistantControl import decomposition as decomposition_module

        manager, head = _decomposition_parent_fixture(self, "assistant-decompose-crossenv-")
        commands: list[list[str]] = []
        real_run = subprocess.run

        def fake_run(command, *args, **kwargs):
            if list(command)[:2] == ["docker", "compose"]:
                commands.append(list(command))
                return subprocess.CompletedProcess(command, 1)
            return real_run(command, *args, **kwargs)

        with patch.dict(os.environ, {"NSC_CLAUDE_MODEL": "claude-opus-5",
                                     "NSC_OPENAI_CODEX_MODEL": "gpt-6-astra"}), \
                patch.object(decomposition_module, "decomposition_preflight",
                             return_value={"source_commit": head}), \
                patch.object(decomposition_module.subprocess, "run", side_effect=fake_run):
            record = decomposition_module.run(
                manager, "NSC-004", "nsc-004-crossenv-run", providers="claude,codex",
                compose_project="assistant-pool", execution_authorized=True,
            )

        command = commands[0]
        self.assertEqual(
            ["docker", "compose", "-p", "assistant-pool", "run", "--rm", "-T"], command[:7],
        )
        self.assertEqual(
            ["--env", "NSC_CLAUDE_MODEL=claude-opus-5",
             "--env", "NSC_OPENAI_CODEX_MODEL=gpt-6-astra"],
            command[7:11],
        )
        self.assertEqual("round-robin-decompose", command[11])
        # Still no reservation: this is the unpooled route.
        self.assertNotIn("--volume", command)
        self.assertNotIn("--role-session-leases", command)
        self.assertIsNone(record.get("pool"))
        # The record says which models the run was launched with, so an
        # unexpected result can be traced without re-deriving the environment.
        self.assertEqual(
            {"NSC_CLAUDE_MODEL": "claude-opus-5", "NSC_OPENAI_CODEX_MODEL": "gpt-6-astra"},
            record["provider_environment"],
        )

    def test_cross_provider_launch_names_only_the_providers_in_use(self):
        """A codex,codex pair is pooled, so the unpooled resolver must never be
        asked for a provider the run does not use."""
        from Pipeline.AssistantControl import decomposition as decomposition_module

        self.assertEqual(
            {"NSC_CLAUDE_MODEL": "claude-opus-5", "NSC_OPENAI_CODEX_MODEL": "gpt-6-astra"},
            _resolve_unpooled(decomposition_module, ["claude", "codex"]),
        )
        # Duplicates collapse, and only the named provider appears.
        self.assertEqual(
            {"NSC_CLAUDE_MODEL": "claude-opus-5"},
            _resolve_unpooled(decomposition_module, ["claude", "claude"]),
        )

    def test_the_unpooled_models_fall_back_to_the_documented_defaults(self):
        from Pipeline.AssistantControl import decomposition as decomposition_module

        with patch.dict(os.environ, {}, clear=False) as _environment:
            os.environ.pop("NSC_CLAUDE_MODEL", None)
            os.environ.pop("NSC_OPENAI_CODEX_MODEL", None)
            resolved = decomposition_module._unpooled_provider_environment(["claude", "codex"])
        # The same defaults live_decomposition.provider_configuration uses, so
        # the host and the container agree instead of silently differing.
        self.assertEqual(
            {"NSC_CLAUDE_MODEL": "claude-sonnet-5", "NSC_OPENAI_CODEX_MODEL": "gpt-5.6-sol"},
            resolved,
        )

    def test_a_pooled_run_id_the_pool_cannot_own_is_refused_before_any_record(self):
        from Pipeline.AssistantControl import decomposition as decomposition_module

        manager, head = _decomposition_parent_fixture(self, "assistant-decompose-runid-")
        with patch.object(decomposition_module, "decomposition_preflight",
                          return_value={"source_commit": head}):
            with self.assertRaisesRegex(ValueError, "Pooled decomposition run id"):
                decomposition_module.run(
                    manager, "NSC-004", "NSC-004.Pooled_Run", providers="claude,claude",
                    compose_project="assistant-pool", execution_authorized=True,
                )
        self.assertFalse((manager.records / "NSC-004.decomposition.json").exists())


class FakePoolOwner:
    """Records the exact lifecycle calls AssistantControl makes on the pool."""

    def __init__(self, bundle: Path, *, settle_error: BaseException | None = None):
        self.bundle = bundle
        self.settle_error = settle_error
        self.calls: list[tuple] = []

    def prepare(self, **kwargs):
        self.calls.append(("prepare", kwargs))
        return {
            "run_id": kwargs["run_id"],
            "repository_identity": POOL_REPOSITORY,
            "compose_project": "assistant-pool",
            "checkout_identity": "manifest-sha256:" + "0" * 64,
            "lease_bundle_path": str(self.bundle),
            "leases": {key: {"lease_id": value} for key, value in POOL_LEASE_IDS.items()},
            "skipped_keys": [],
            "provider_environment": {"NSC_CLAUDE_MODEL": POOL_MODEL, "NSC_OPENAI_CODEX_MODEL": ""},
        }

    def settle(self, *, run_id, run_dir):
        self.calls.append(("settle", run_id, str(run_dir)))
        if self.settle_error is not None:
            raise self.settle_error
        return {"run_id": run_id, "run_status": "review_ready", "leases": {}}

    def cancel_unstarted(self, *, run_id):
        self.calls.append(("cancel_unstarted", run_id))

    def close(self):
        self.calls.append(("close",))

    def actions(self) -> list[str]:
        return [call[0] for call in self.calls]


class PooledLifecycleTests(unittest.TestCase):
    """Settle from artifacts, cancel only a proven non-start, always close."""

    def launch(self, prefix: str, *, exit_code: int = 0, run_directory: bool = True,
               start_error: BaseException | None = None,
               settle_error: BaseException | None = None):
        from Pipeline.AssistantControl import decomposition as decomposition_module

        manager, head = _decomposition_parent_fixture(self, prefix)
        run_id = "nsc-004-lifecycle-run"
        artifact_root = (manager.records / "decomposition-runs").resolve() / run_id
        bundle = manager.root / "fixture.leases.json"
        manager.root.mkdir(parents=True, exist_ok=True)
        bundle.write_text("{}\n", encoding="utf-8", newline="\n")
        owner = FakePoolOwner(bundle, settle_error=settle_error)
        real_run = subprocess.run

        def fake_run(command, *args, **kwargs):
            if list(command)[:2] == ["docker", "compose"]:
                if run_directory:
                    artifact_root.mkdir(parents=True, exist_ok=True)
                if start_error is not None:
                    raise start_error
                return subprocess.CompletedProcess(command, exit_code)
            return real_run(command, *args, **kwargs)

        context = [
            patch.object(decomposition_module, "_pool_owner", return_value=owner),
            patch.object(decomposition_module, "decomposition_preflight",
                         return_value={"source_commit": head}),
            patch.object(decomposition_module.subprocess, "run", side_effect=fake_run),
            patch.object(decomposition_module, "_verify_review",
                         return_value={"status": "review_ready", "child_ids": ["NSC-1001"]}),
        ]
        for entered in context:
            entered.start()
            self.addCleanup(entered.stop)
        return decomposition_module, manager, owner, run_id, artifact_root

    def test_a_successful_run_settles_from_its_run_directory_and_closes(self):
        module, manager, owner, run_id, artifact_root = self.launch("assistant-pool-settle-")
        record = module.run(
            manager, "NSC-004", run_id, providers="claude,claude",
            compose_project="assistant-pool", execution_authorized=True,
        )
        self.assertEqual("review_ready", record["status"])
        self.assertEqual(["prepare", "settle", "close"], owner.actions())
        self.assertEqual(("settle", run_id, str(artifact_root)), owner.calls[1])
        prepared = owner.calls[0][1]
        self.assertEqual("round_robin_d1b2", prepared["decomposition_mode"])
        self.assertEqual(("claude", "claude"), prepared["provider_order"])
        self.assertEqual(2, prepared["max_calls"])
        self.assertEqual(record["source_commit"], prepared["source_commit"])
        self.assertEqual("settled", record["pool_lifecycle"]["status"])

    def test_a_failed_run_that_produced_a_run_directory_still_settles(self):
        module, manager, owner, run_id, artifact_root = self.launch(
            "assistant-pool-failed-", exit_code=1,
        )
        record = module.run(
            manager, "NSC-004", run_id, providers="claude,claude",
            compose_project="assistant-pool", execution_authorized=True,
        )
        self.assertEqual("failed", record["status"])
        self.assertEqual(["prepare", "settle", "close"], owner.actions())
        self.assertEqual("settled", record["pool_lifecycle"]["status"])

    def test_a_plain_oserror_settles_because_it_does_not_prove_nothing_ran(self):
        # PermissionError from kill() on a live container, and ChildProcessError from
        # waitpid, are raised after the provider has already run, so an OSError that is
        # not a missing executable must settle rather than return the leases uncharged.
        module, manager, owner, run_id, _root = self.launch(
            "assistant-pool-ambiguous-", run_directory=False,
            start_error=OSError("connection reset by the docker daemon"),
        )
        with self.assertRaises(OSError):
            module.run(
                manager, "NSC-004", run_id, providers="claude,claude",
                compose_project="assistant-pool", execution_authorized=True,
            )
        # Neither settled nor cancelled: with no run directory the leases stay active and
        # the next owner reclaims them as stranded, so they are never resumed and never
        # handed back as unused.
        self.assertEqual(["prepare", "close"], owner.actions())
        record = json.loads(
            (manager.records / "NSC-004.decomposition.json").read_text(encoding="utf-8")
        )
        self.assertEqual("run_directory_missing", record["pool_lifecycle"]["status"])
        self.assertEqual("failed", record["status"])

    def test_a_provider_that_never_started_returns_the_leases_uncharged(self):
        # The executable could not be spawned, so nothing ran and no run
        # directory exists.
        module, manager, owner, run_id, _root = self.launch(
            "assistant-pool-unstarted-", run_directory=False,
            start_error=FileNotFoundError("docker: no such file or directory"),
        )
        with self.assertRaises(OSError):
            module.run(
                manager, "NSC-004", run_id, providers="claude,claude",
                compose_project="assistant-pool", execution_authorized=True,
            )
        self.assertEqual(["prepare", "cancel_unstarted", "close"], owner.actions())
        record = json.loads(
            (manager.records / "NSC-004.decomposition.json").read_text(encoding="utf-8")
        )
        self.assertEqual("failed", record["status"])
        self.assertEqual("cancelled_unstarted", record["pool_lifecycle"]["status"])

    def test_an_oserror_raised_after_the_spawn_settles_instead_of_cancelling(self):
        # `subprocess.run` raises OSError after Popen succeeded too: on Windows
        # the timeout handler's kill can raise PermissionError against a live
        # container, and on POSIX the wait can raise ChildProcessError. The run
        # directory exists, so those conversations are real and are retired.
        module, manager, owner, run_id, artifact_root = self.launch(
            "assistant-pool-after-spawn-",
            start_error=ChildProcessError("no child processes"),
        )
        with self.assertRaises(ChildProcessError):
            module.run(
                manager, "NSC-004", run_id, providers="claude,claude",
                compose_project="assistant-pool", execution_authorized=True,
            )
        self.assertEqual(["prepare", "settle", "close"], owner.actions())
        self.assertEqual(("settle", run_id, str(artifact_root)), owner.calls[1])
        record = json.loads(
            (manager.records / "NSC-004.decomposition.json").read_text(encoding="utf-8")
        )
        self.assertEqual("failed", record["status"])
        self.assertEqual("settled", record["pool_lifecycle"]["status"])

    def test_an_oserror_raised_instead_of_the_spawn_still_cancels(self):
        # The executable could not be spawned at all, so no run directory was
        # created and nothing ran.
        module, manager, owner, run_id, _root = self.launch(
            "assistant-pool-no-spawn-", run_directory=False,
            start_error=FileNotFoundError("docker: no such file or directory"),
        )
        with self.assertRaises(FileNotFoundError):
            module.run(
                manager, "NSC-004", run_id, providers="claude,claude",
                compose_project="assistant-pool", execution_authorized=True,
            )
        self.assertEqual(["prepare", "cancel_unstarted", "close"], owner.actions())
        record = json.loads(
            (manager.records / "NSC-004.decomposition.json").read_text(encoding="utf-8")
        )
        self.assertEqual("failed", record["status"])
        self.assertEqual("cancelled_unstarted", record["pool_lifecycle"]["status"])

    def test_a_timed_out_run_settles_instead_of_cancelling(self):
        module, manager, owner, run_id, artifact_root = self.launch(
            "assistant-pool-timeout-",
            start_error=subprocess.TimeoutExpired(["docker", "compose"], 3600),
        )
        with self.assertRaises(subprocess.TimeoutExpired):
            module.run(
                manager, "NSC-004", run_id, providers="claude,claude",
                compose_project="assistant-pool", execution_authorized=True,
            )
        # The container really ran, so both conversations are retired from the
        # run's artifacts; returning them uncharged would resume them later.
        self.assertEqual(["prepare", "settle", "close"], owner.actions())
        self.assertEqual(("settle", run_id, str(artifact_root)), owner.calls[1])
        record = json.loads(
            (manager.records / "NSC-004.decomposition.json").read_text(encoding="utf-8")
        )
        self.assertEqual("failed", record["status"])
        self.assertEqual("settled", record["pool_lifecycle"]["status"])

    def test_an_interrupted_run_settles_instead_of_cancelling(self):
        module, manager, owner, run_id, artifact_root = self.launch(
            "assistant-pool-interrupt-", start_error=KeyboardInterrupt(),
        )
        with self.assertRaises(KeyboardInterrupt):
            module.run(
                manager, "NSC-004", run_id, providers="claude,claude",
                compose_project="assistant-pool", execution_authorized=True,
            )
        self.assertEqual(["prepare", "settle", "close"], owner.actions())
        self.assertEqual(("settle", run_id, str(artifact_root)), owner.calls[1])
        record = json.loads(
            (manager.records / "NSC-004.decomposition.json").read_text(encoding="utf-8")
        )
        self.assertEqual("failed", record["status"])
        self.assertEqual("settled", record["pool_lifecycle"]["status"])

    def test_a_run_without_a_run_directory_is_never_cancelled_as_unstarted(self):
        module, manager, owner, run_id, _root = self.launch(
            "assistant-pool-nodir-", exit_code=1, run_directory=False,
        )
        record = module.run(
            manager, "NSC-004", run_id, providers="claude,claude",
            compose_project="assistant-pool", execution_authorized=True,
        )
        self.assertEqual("failed", record["status"])
        # The provider may have run: the leases stay active and the next owner
        # reclaims them as stranded.
        self.assertEqual(["prepare", "close"], owner.actions())
        self.assertEqual("run_directory_missing", record["pool_lifecycle"]["status"])

    def test_a_settle_failure_degrades_pooling_and_never_fails_a_good_run(self):
        from Pipeline.TaskReviewAgent.decomposition_session_pool import (
            DecompositionSessionPoolError,
        )

        module, manager, owner, run_id, _root = self.launch(
            "assistant-pool-degraded-",
            settle_error=DecompositionSessionPoolError("fixture settlement failure"),
        )
        record = module.run(
            manager, "NSC-004", run_id, providers="claude,claude",
            compose_project="assistant-pool", execution_authorized=True,
        )
        self.assertEqual("review_ready", record["status"])
        self.assertEqual(["prepare", "settle", "close"], owner.actions())
        self.assertEqual("pool_degraded", record["pool_lifecycle"]["status"])
        self.assertIn("fixture settlement failure", record["pool_lifecycle"]["error"])

    def test_a_settle_that_raises_still_leaves_a_failed_record_and_one_settle(self):
        # A settlement failure the pool helper does not classify escapes into
        # the run's own failure path. It must be settled exactly once, it must
        # not hide the error it raised, and it must not leave the record
        # `running` with no process behind it.
        module, manager, owner, run_id, _root = self.launch(
            "assistant-pool-settle-raises-",
            settle_error=KeyError("fixture settlement failure"),
        )
        with self.assertRaises(KeyError) as raised:
            module.run(
                manager, "NSC-004", run_id, providers="claude,claude",
                compose_project="assistant-pool", execution_authorized=True,
            )
        self.assertIn("fixture settlement failure", str(raised.exception))
        self.assertEqual(["prepare", "settle", "close"], owner.actions())
        record_path = manager.records / "NSC-004.decomposition.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual("failed", record["status"])
        self.assertIn("KeyError", record["error"])
        # The task is no longer held mid-flight: a later run meets the settled
        # `failed` record an operator can clear, never a `running` one that no
        # process owns.
        with self.assertRaises(ValueError) as refused:
            module.run(
                manager, "NSC-004", "nsc-004-lifecycle-rerun", providers="claude,claude",
                compose_project="assistant-pool", execution_authorized=True,
            )
        self.assertIn("status failed", str(refused.exception))
        self.assertNotIn("status running", str(refused.exception))
        self.assertEqual(["prepare", "settle", "close"], owner.actions())


class SameProviderReviewIndependenceTests(unittest.TestCase):
    """`same_provider_separate_sessions` is admitted only for a pooled same-provider run."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="assistant-d1c-same-provider-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source"
        source.mkdir()
        create_repository(source)
        self.task_id = "NSC-004"
        task_path = source / "Tasks" / f"{self.task_id}.yaml"
        selected = json.loads(task_path.read_text(encoding="utf-8"))
        selected.update(
            execution_scope="needs_execution_decomposition",
            execution_reason="Synthetic same-provider regression requires decomposition.",
        )
        _write_json(task_path, selected)
        _git(source, "add", "--", f"Tasks/{self.task_id}.yaml")
        _git(source, "commit", "-m", "fixture: select childless decomposition parent")
        graph = load_persistent_work_graph(source)
        parent = graph.tasks_by_id[self.task_id]
        proposal = decomposed_result(parent)
        proposal["children"][0]["exclusive_resources"] = []
        proposal["inbound_dependency_rewrites"] = []
        decomposition = validate_decomposition_result(
            proposal, parent_task=parent, existing_reconciliation_keys=graph.plan.id_map,
        )
        stored_plan = plan_graph_delta(graph, decomposition.parent_task, decomposition)
        head = _git(source, "rev-parse", "HEAD")
        tree = _git(source, "rev-parse", "HEAD^{tree}")
        branch = _git(source, "branch", "--show-current")
        task = load_committed_task(source, self.task_id, commit=head)
        self.manager = Checkouts(source, root / "checkouts")
        self.manager.records.mkdir(parents=True)
        self.run_id = "nsc-004-same-provider-run"
        output_root = (self.manager.records / "decomposition-runs").resolve()
        self.artifact_root = output_root / self.run_id
        self.artifact_root.mkdir(parents=True)
        _write_json(self.artifact_root / "decomposition_result.json", decomposition.to_dict())
        _write_json(self.artifact_root / "graph_delta.json", stored_plan.to_dict())
        self.digest = candidate_sha256(decomposition)
        self.candidate = {
            "version": 1,
            "author_provider": "claude",
            "sha256": self.digest,
            "decision": "decomposed",
            "graph_delta_plan_id": stored_plan.plan_id,
        }
        self.head, self.tree, self.branch, self.task = head, tree, branch, task
        self.output_root = output_root

    # -- exact fixtures ----------------------------------------------------

    def pooled_sessions(self, **overrides) -> dict:
        sessions = {}
        for index, (key, lease_id) in enumerate(sorted(POOL_LEASE_IDS.items())):
            role = key.split(":", 1)[1]
            sessions[key] = {
                "lease_id": lease_id,
                "record_id": f"{index}0000000-0000-4000-8000-000000000000",
                "role": role,
                "provider_identifier": "claude-code",
                "invoked": True,
                "identity_unproven": None,
                "confirmed_session": {
                    "provider_identifier": "claude-code",
                    "role": role,
                    "mode": "start",
                    "session_id": f"{index + 3}3333333-3333-4333-8333-333333333333",
                },
            }
        sessions.update(overrides)
        return sessions

    def run_result(self, providers, *, independence, sessions=None) -> dict:
        return {
            "schema_version": "1.0",
            "mode": "round_robin_d1b2",
            "run_id": self.run_id,
            "task_id": self.task_id,
            "provider_order": list(providers),
            "max_calls": 2,
            "calls_used": 2,
            "run_status": "review_ready",
            "decision": "decomposed",
            "review_independence": independence,
            "authority": "review_only_not_applied",
            "unresolved_findings": [],
            "rejection_reasons": [],
            "source_identity": {"head_commit": self.head, "head_tree": self.tree},
            "task_execution_contract_identity": {
                "revision": self.task["contract_revision"],
                "sha256": self.task["task_contract_sha256"],
            },
            "latest_candidate": self.candidate,
            "independent_approver_provider": providers[1],
            "pooled_sessions": sessions,
            "rounds": [
                {
                    "role": "task_decomposer", "correction_of_round": None,
                    "requested_provider": providers[0], "actual_model": POOL_MODEL,
                    "agent_status": "succeeded", "status": "candidate_valid",
                    "candidate_after": self.candidate,
                },
                {
                    "role": "decomposition_reviewer", "correction_of_round": None,
                    "requested_provider": providers[1], "actual_model": POOL_MODEL,
                    "agent_status": "succeeded", "status": "independent_pass",
                    "verdict": "pass", "candidate_before": self.candidate,
                    "candidate_after": None,
                },
            ],
            "finding_history": [{
                "verdict": "pass",
                "reviewed_candidate_sha256": self.digest,
                "findings": [],
            }],
        }

    def record(self, providers, *, pool=True, lease_ids=None) -> dict:
        value = {
            "schema_version": "assistant-decomposition/v1",
            "task_id": self.task_id,
            "run_id": self.run_id,
            "source": str(self.manager.source),
            "source_commit": self.head,
            "source_tree": self.tree,
            "source_branch": self.branch,
            "task_contract_sha256": self.task["task_contract_sha256"],
            "providers": list(providers),
            "output_root": str(self.output_root),
            "artifact_root": str(self.artifact_root),
            "status": "review_ready",
        }
        if pool:
            value["pool"] = {
                "lease_bundle_path": str(self.manager.records / "fixture.leases.json"),
                "repository_identity": POOL_REPOSITORY,
                "checkout_identity": "manifest-sha256:" + "0" * 64,
                "compose_project": "assistant-pool",
                "lease_keys": sorted(POOL_LEASE_IDS),
                "lease_ids": dict(lease_ids or POOL_LEASE_IDS),
            }
        return value

    def verify(self, providers, *, independence, sessions=None, pool=True, lease_ids=None):
        _write_json(
            self.artifact_root / "decomposition_run_result.json",
            self.run_result(providers, independence=independence, sessions=sessions),
        )
        return _verify_review(self.manager, self.record(providers, pool=pool, lease_ids=lease_ids))

    # -- accepted ----------------------------------------------------------

    def test_pooled_same_provider_run_verifies(self):
        review = self.verify(
            ("claude", "claude"),
            independence="same_provider_separate_sessions",
            sessions=self.pooled_sessions(),
        )
        self.assertEqual("review_ready", review["status"])
        self.assertEqual(self.digest, review["candidate_sha256"])
        self.assertEqual("claude", review["reviewer_provider"])

    def test_cross_provider_verification_is_unchanged(self):
        review = self.verify(("claude", "codex"), independence="cross_provider", pool=False)
        self.assertEqual("review_ready", review["status"])

    # -- refused -----------------------------------------------------------

    def test_a_same_provider_run_may_not_claim_cross_provider_independence(self):
        with self.assertRaisesRegex(ValueError, "review_independence"):
            self.verify(
                ("claude", "claude"), independence="cross_provider",
                sessions=self.pooled_sessions(),
            )

    def test_a_cross_provider_run_may_not_claim_separate_sessions(self):
        with self.assertRaisesRegex(ValueError, "review_independence"):
            self.verify(
                ("claude", "codex"), independence="same_provider_separate_sessions",
                pool=False,
            )

    def test_a_same_provider_record_without_a_lease_reservation_is_refused(self):
        with self.assertRaisesRegex(ValueError, "lease reservation"):
            self.verify(
                ("claude", "claude"), independence="same_provider_separate_sessions",
                sessions=self.pooled_sessions(), pool=False,
            )

    def test_a_reservation_missing_one_role_lease_is_refused(self):
        # The pool skips a key it cannot scope and reserves the rest, so a
        # one-lease reservation whose run used exactly that lease would
        # otherwise verify: one conversation authoring and reviewing.
        author = "claude:task_decomposer"
        sessions = self.pooled_sessions()
        with self.assertRaisesRegex(ValueError, "not one lease per role"):
            self.verify(
                ("claude", "claude"), independence="same_provider_separate_sessions",
                sessions={author: sessions[author]},
                lease_ids={author: POOL_LEASE_IDS[author]},
            )

    def test_a_role_session_without_a_confirmed_conversation_is_refused(self):
        sessions = self.pooled_sessions()
        reviewer = dict(sessions["claude:decomposition_reviewer"])
        reviewer["confirmed_session"] = None
        with self.assertRaisesRegex(ValueError, "no confirmed conversation"):
            self.verify(
                ("claude", "claude"), independence="same_provider_separate_sessions",
                sessions=self.pooled_sessions(**{"claude:decomposition_reviewer": reviewer}),
            )

    def test_two_role_sessions_sharing_one_conversation_are_refused(self):
        sessions = self.pooled_sessions()
        author = sessions["claude:task_decomposer"]
        reviewer = dict(sessions["claude:decomposition_reviewer"])
        reviewer["confirmed_session"] = dict(author["confirmed_session"])
        reviewer["confirmed_session"]["role"] = "decomposition_reviewer"
        with self.assertRaisesRegex(ValueError, "not two distinct ones"):
            self.verify(
                ("claude", "claude"), independence="same_provider_separate_sessions",
                sessions=self.pooled_sessions(**{"claude:decomposition_reviewer": reviewer}),
            )

    def test_a_same_provider_run_that_used_other_leases_is_refused(self):
        with self.assertRaisesRegex(ValueError, "reserved role leases"):
            self.verify(
                ("claude", "claude"), independence="same_provider_separate_sessions",
                sessions=self.pooled_sessions(),
                lease_ids={key: "99999999-9999-4999-8999-999999999999"
                           for key in POOL_LEASE_IDS},
            )
        with self.assertRaisesRegex(ValueError, "reserved role leases"):
            self.verify(
                ("claude", "claude"), independence="same_provider_separate_sessions",
                sessions=None,
            )
        partial = self.pooled_sessions()
        del partial["claude:decomposition_reviewer"]
        with self.assertRaisesRegex(ValueError, "reserved role leases"):
            self.verify(
                ("claude", "claude"), independence="same_provider_separate_sessions",
                sessions=partial,
            )


if __name__ == "__main__":
    unittest.main()
