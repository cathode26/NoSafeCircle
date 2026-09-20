"""A D1B.2 decomposition that stops at its human authority boundary is a human-review state.

NSC-1165 in the 20260913 Gauntlet: decomposition run
assistant-nsc-1165-decompose-c7cb184da82b ended `needs_human` exactly as the
bounded circuit is designed to (a revision on the last allowed call may not be
approved by its own author) and published no decomposition_result.json or
graph_delta.json. AssistantControl demanded those success-only artifacts before
it read the run status, so the proposal record, the decompose job's receipt and
its ticket all landed `failed`. These regressions bind the fix end to end: the
proposal record, read-only inspection, the refusal to apply, the real background
child's receipt and harvest, the planner, the run loop and the viewer.
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl import background_jobs
from Pipeline.AssistantControl import decomposition as decomposition_module
from Pipeline.AssistantControl import test_background_jobs as job_tests
from Pipeline.AssistantControl import test_decomposition as decomposition_tests
from Pipeline.AssistantControl import test_graph_controller as graph_tests
from Pipeline.AssistantControl.automation_policy import is_synthetic_gauntlet
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.graph_controller import GraphController, GraphPolicy
from Pipeline.AssistantControl.viewer import AssistantSnapshot
from Pipeline.TaskDecomposition.tests.test_support import create_repository
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task


# The exact decomposition_run_result.json the NSC-1165 run published in the
# 20260913 Gauntlet (.assistant-control/decomposition-runs/
# assistant-nsc-1165-decompose-c7cb184da82b). `needs_human_run_result` rebinds
# only its identity (run, task, Source commit and tree, parent contract) to each
# fixture repository; every outcome field is the live one.
NSC_1165_RUN_RESULT = json.loads(r"""
{
  "author_corrections_used": 0,
  "authority": "review_only_not_applied",
  "calls_used": 2,
  "context_sha256": "106383e68ed1fc2e5e168215eddf8c5eb7b51dd810d2d0f2acc7b3b3a57a3551",
  "d1a_semantic_parent_identity": {
    "contract_revision": 1,
    "contract_sha256": "b141d1d7e797c4e516e1ab7cf66226014f1832d2cfcc3a8a3c2919aa701ac4fd",
    "task_id": "NSC-1165"
  },
  "decision": "decomposed",
  "decomposition_result_path": null,
  "duration_seconds": 234.45781439499996,
  "finding_history": [
    {
      "findings": [
        {
          "affected_contracts": [
            "NSC-1165",
            "gauntlet-1165-alpha-value",
            "gauntlet-1165-beta-value"
          ],
          "category": "candidate_correctness",
          "finding_id": "round-02-misstated-edit-mode-proof",
          "problem": "Both proposed completion gates say the committed Edit Mode tests confirm that the corresponding type is a public static class. The tests resolve the fully qualified type and inspect its public static literal Value field, but they never assert Type.IsPublic, Type.IsAbstract, or Type.IsSealed. The child acceptance criteria correctly require public static classes, but the completion gates overstate what their named test filters prove.",
          "required_resolution": "Keep the public-static-class requirement in each child acceptance criterion, but rewrite both completion gates to describe only the actual test oracle: the fully qualified type exists and has a public static literal Value field whose raw constant value is 1165.",
          "severity": "blocking"
        }
      ],
      "prior_finding_resolutions": [],
      "reviewed_candidate_sha256": "70b1529ed5e2bb50f270c9c5014c7d2045795397a39a2ec5fe17d9ccbe80e1ae",
      "reviewer_provider": "codex",
      "round_number": 2,
      "summary": "Revision required because both child completion gates overstate what their named Edit Mode tests verify. The replacement keeps the two-child partition, dependencies, resource ownership, and complete parent coverage while correcting the test-proof wording.",
      "verdict": "revise"
    }
  ],
  "graph_delta_path": null,
  "human_next_step": "Inspect unresolved_findings and round artifacts. The bounded independent-review circuit reached a human authority boundary; no candidate was approved or applied.",
  "independent_approver_provider": null,
  "latest_candidate": {
    "author_provider": "codex",
    "decision": "decomposed",
    "graph_delta_plan_id": "GDP-57f5cb462887c7219daa1cccfe82c9d1d34ef5c716c292ea8f0fd807145ce5c5",
    "sha256": "d653721a0c26950143c020ee94e8cc1dbaf722abea95f31a3212eafb3861b94f",
    "version": 2
  },
  "max_calls": 2,
  "mode": "round_robin_d1b2",
  "pooled_sessions": null,
  "provider_order": [
    "claude",
    "codex"
  ],
  "rejection_reasons": [
    "call limit ended immediately after a revision; the latest author may not approve its own candidate"
  ],
  "review_independence": "cross_provider",
  "rounds": [
    {
      "actual_model": "claude-sonnet-5",
      "actual_provider": "claude-code",
      "agent_failure_classification": "none",
      "agent_runtime_result_path": "rounds/01/agent_runtime/nsc-1165-d1b2-r01-task-decomposer-4ded742b4275/result.json",
      "agent_status": "succeeded",
      "authority": "review_only_not_applied",
      "candidate_after": {
        "author_provider": "claude",
        "decision": "decomposed",
        "graph_delta_plan_id": "GDP-0a9e7021b434e716baeb3a61d05cebcdea5a9f884a5dc2646e3524d186e288ee",
        "sha256": "70b1529ed5e2bb50f270c9c5014c7d2045795397a39a2ec5fe17d9ccbe80e1ae",
        "version": 1
      },
      "candidate_before": null,
      "correction_of_round": null,
      "duration_seconds": 89.736,
      "new_finding_ids": [],
      "pooled_session": null,
      "rejection_reasons": [],
      "requested_provider": "claude",
      "role": "task_decomposer",
      "round_number": 1,
      "schema_version": "1.0",
      "status": "candidate_valid",
      "task_execution_request_path": "rounds/01/task_execution/nsc-1165-d1b2-r01-task-decomposer-4ded742b4275/task_request.json",
      "unresolved_finding_ids": [],
      "verdict": null
    },
    {
      "actual_model": "gpt-5.6-sol",
      "actual_provider": "openai-codex",
      "agent_failure_classification": "none",
      "agent_runtime_result_path": "rounds/02/agent_runtime/nsc-1165-d1b2-r02-decomposition-reviewer-fd7db710d32f/result.json",
      "agent_status": "succeeded",
      "authority": "review_only_not_applied",
      "candidate_after": {
        "author_provider": "codex",
        "decision": "decomposed",
        "graph_delta_plan_id": "GDP-57f5cb462887c7219daa1cccfe82c9d1d34ef5c716c292ea8f0fd807145ce5c5",
        "sha256": "d653721a0c26950143c020ee94e8cc1dbaf722abea95f31a3212eafb3861b94f",
        "version": 2
      },
      "candidate_before": {
        "author_provider": "claude",
        "decision": "decomposed",
        "graph_delta_plan_id": "GDP-0a9e7021b434e716baeb3a61d05cebcdea5a9f884a5dc2646e3524d186e288ee",
        "sha256": "70b1529ed5e2bb50f270c9c5014c7d2045795397a39a2ec5fe17d9ccbe80e1ae",
        "version": 1
      },
      "correction_of_round": null,
      "duration_seconds": 81.287,
      "new_finding_ids": [
        "round-02-misstated-edit-mode-proof"
      ],
      "pooled_session": null,
      "rejection_reasons": [],
      "requested_provider": "codex",
      "role": "decomposition_reviewer",
      "round_number": 2,
      "schema_version": "1.0",
      "status": "revised_candidate_valid",
      "task_execution_request_path": "rounds/02/task_execution/nsc-1165-d1b2-r02-decomposition-reviewer-fd7db710d32f/task_request.json",
      "unresolved_finding_ids": [
        "round-02-misstated-edit-mode-proof"
      ],
      "verdict": "revise"
    }
  ],
  "run_id": "assistant-nsc-1165-decompose-c7cb184da82b",
  "run_status": "needs_human",
  "schema_version": "1.0",
  "source_identity": {
    "branch": "gauntlet-test/reviewed-async-1160",
    "head_commit": "c7cb184da82b8c76fc6b4ffcdbb4b4ef988e3afc",
    "head_tree": "bcb26f5d274392b806e41653507ad1f8d45eec29"
  },
  "task_execution_contract_identity": {
    "path": "Tasks/NSC-1165.yaml",
    "revision": 1,
    "sha256": "f66fa1740f55f17922a7e4612f75916bcc30ae8023123dddefc5bcfa123c0ef9"
  },
  "task_id": "NSC-1165",
  "unresolved_findings": [
    {
      "affected_contracts": [
        "NSC-1165",
        "gauntlet-1165-alpha-value",
        "gauntlet-1165-beta-value"
      ],
      "category": "candidate_correctness",
      "finding_id": "round-02-misstated-edit-mode-proof",
      "problem": "Both proposed completion gates say the committed Edit Mode tests confirm that the corresponding type is a public static class. The tests resolve the fully qualified type and inspect its public static literal Value field, but they never assert Type.IsPublic, Type.IsAbstract, or Type.IsSealed. The child acceptance criteria correctly require public static classes, but the completion gates overstate what their named test filters prove.",
      "required_resolution": "Keep the public-static-class requirement in each child acceptance criterion, but rewrite both completion gates to describe only the actual test oracle: the fully qualified type exists and has a public static literal Value field whose raw constant value is 1165.",
      "severity": "blocking"
    }
  ]
}
""")

NSC_1165_REASON = (
    "Rejection reasons: call limit ended immediately after a revision; the latest author "
    "may not approve its own candidate. Unresolved findings: round-02-misstated-edit-mode-proof."
)

COMPOSE_COMMAND = (
    "docker", "compose", "-p", "nosafecircle", "run", "--rm", "-T",
    "round-robin-decompose", "python3",
    "Pipeline/TaskDecomposition/run_round_robin_decomposition.py",
)


def needs_human_run_result(*, run_id: str, task_id: str, task: dict, head: str, tree: str,
                           branch: str) -> dict:
    """The NSC-1165 run result, rebound to one fixture's exact run, Source and parent contract."""
    value = copy.deepcopy(NSC_1165_RUN_RESULT)
    value.update(
        run_id=run_id,
        task_id=task_id,
        source_identity={"branch": branch, "head_commit": head, "head_tree": tree},
        task_execution_contract_identity={
            "path": f"Tasks/{task_id}.yaml",
            "revision": task["contract_revision"],
            "sha256": task["task_contract_sha256"],
        },
    )
    value["d1a_semantic_parent_identity"] = {**value["d1a_semantic_parent_identity"], "task_id": task_id}
    return value


def expected_facts(run_result: dict) -> dict:
    """The bounded needs_human block a run result must leave on its decomposition record."""
    candidate = run_result["latest_candidate"]
    return {
        "rejection_reasons": run_result["rejection_reasons"],
        "unresolved_findings": run_result["unresolved_findings"],
        "human_next_step": run_result["human_next_step"],
        "calls_used": run_result["calls_used"],
        "author_corrections_used": run_result["author_corrections_used"],
        "latest_candidate": {
            field: candidate[field]
            for field in ("version", "author_provider", "sha256", "decision", "graph_delta_plan_id")
        },
    }


def write_needs_human_record(manager: Checkouts, *, task_id: str, task: dict, head: str, tree: str,
                             branch: str, run_id: str, run_result: dict | None = None,
                             facts: dict | None = None) -> dict:
    """Retain one needs_human run and the exact record `decomposition.run` writes for it."""
    if run_result is None:
        run_result = needs_human_run_result(run_id=run_id, task_id=task_id, task=task,
                                            head=head, tree=tree, branch=branch)
    output_root = (manager.records / "decomposition-runs").resolve()
    artifact_root = output_root / run_id
    artifact_root.mkdir(parents=True)
    decomposition_tests._write_json(artifact_root / "decomposition_run_result.json", run_result)
    logs = manager.records / "decomposition-launch" / task_id / run_id
    record = {
        "schema_version": decomposition_module.SCHEMA, "task_id": task_id, "run_id": run_id,
        "source": str(manager.source), "source_commit": head, "source_tree": tree,
        "source_branch": branch, "task_contract_sha256": task["task_contract_sha256"],
        "providers": ["claude", "codex"], "max_calls": 2, "compose_project": "nosafecircle",
        "output_root": str(output_root), "artifact_root": str(artifact_root),
        "stdout_log": str(logs / "stdout.log"), "stderr_log": str(logs / "stderr.log"),
        "container_name": None, "container_labels": None, "status": "needs_human",
        "started_at_utc": "2026-09-13T13:42:33.053271+00:00", "preflight_source_commit": head,
        "needs_human": expected_facts(run_result) if facts is None else facts,
        "completed_at_utc": "2026-09-13T13:46:30.432329+00:00", "exit_code": 0,
    }
    write_record(manager.records / f"{task_id}.decomposition.json", record)
    return record


@contextlib.contextmanager
def fake_compose(run_id: str, publish, *, head: str):
    """Stand in for the provider container.

    `publish(artifact_root)` writes what the D1B.2 run publishes for `run_id`,
    and the container exits 0, which the round-robin entry point does for both
    `review_ready` and `needs_human`. Every other subprocess runs for real.
    """
    real_run = subprocess.run
    launches: list[list[str]] = []

    def run(command, *args, **kwargs):
        if list(command)[:2] != ["docker", "compose"]:
            return real_run(command, *args, **kwargs)
        launches.append(list(command))
        artifact_root = Path(kwargs["env"]["NSC_DECOMPOSITION_HOST_OUTPUT_ROOT"]) / run_id
        artifact_root.mkdir()
        publish(artifact_root)
        return subprocess.CompletedProcess(command, 0)

    with patch.object(decomposition_module, "build_compose_command", return_value=COMPOSE_COMMAND), \
            patch.object(decomposition_module, "decomposition_preflight",
                         return_value={"source_commit": head}), \
            patch.object(decomposition_module.subprocess, "run", side_effect=run):
        yield launches


class NeedsHumanProposalTests(unittest.TestCase):
    """The proposal record, inspection and application boundary of a needs_human run."""

    TASK_ID = "NSC-004"
    RUN_ID = "assistant-nsc-004-decompose-fixture"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="assistant-needs-human-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.source = root / "source"
        self.source.mkdir()
        create_repository(self.source)
        task_path = self.source / "Tasks" / f"{self.TASK_ID}.yaml"
        selected = json.loads(task_path.read_text(encoding="utf-8"))
        selected.update(execution_scope="needs_execution_decomposition",
                        execution_reason="Synthetic needs_human regression requires decomposition.")
        decomposition_tests._write_json(task_path, selected)
        self.git("add", "--", f"Tasks/{self.TASK_ID}.yaml")
        self.git("commit", "-m", "fixture: childless decomposition parent")
        self.head = self.git("rev-parse", "HEAD")
        self.tree = self.git("rev-parse", "HEAD^{tree}")
        self.branch = self.git("branch", "--show-current")
        self.task = load_committed_task(self.source, self.TASK_ID, commit=self.head)
        self.manager = Checkouts(self.source, root / "checkouts")
        self.record_path = self.manager.records / f"{self.TASK_ID}.decomposition.json"

    def git(self, *args: str) -> str:
        return decomposition_tests._git(self.source, *args)

    def run_result(self, run_id: str | None = None) -> dict:
        return needs_human_run_result(run_id=run_id or self.RUN_ID, task_id=self.TASK_ID,
                                      task=self.task, head=self.head, tree=self.tree,
                                      branch=self.branch)

    def propose(self, run_result: dict, *, run_id: str | None = None) -> dict:
        def publish(artifact_root: Path) -> None:
            decomposition_tests._write_json(artifact_root / "decomposition_run_result.json", run_result)

        run_id = run_id or self.RUN_ID
        with fake_compose(run_id, publish, head=self.head) as launches:
            try:
                return decomposition_module.run(
                    self.manager, self.TASK_ID, run_id, providers="claude,codex",
                    compose_project="nosafecircle", execution_authorized=True,
                )
            finally:
                self.assertEqual(1, len(launches))

    def assert_run_refused(self, label: str, mutate, message: str) -> None:
        run_id = f"{self.RUN_ID}-{label}"
        run_result = self.run_result(run_id)
        mutate(run_result)
        # Each refusal is its own proposal attempt; the previous one's failed
        # record would otherwise be preserved and refuse this one first.
        self.record_path.unlink(missing_ok=True)
        with self.assertRaisesRegex(ValueError, message):
            self.propose(run_result, run_id=run_id)
        record = json.loads(self.record_path.read_text(encoding="utf-8"))
        self.assertEqual("failed", record["status"])
        self.assertNotIn("needs_human", record)
        self.assertRegex(record["error"], message)

    # -- the live incident ---------------------------------------------------

    def test_needs_human_run_is_recorded_as_human_review_and_returned_without_raising(self):
        run_result = self.run_result()

        record = self.propose(run_result)

        self.assertEqual("needs_human", record["status"])
        self.assertEqual(0, record["exit_code"])
        self.assertIsInstance(record["completed_at_utc"], str)
        self.assertNotIn("error", record)
        self.assertNotIn("review", record)
        self.assertEqual(expected_facts(run_result), record["needs_human"])
        self.assertEqual(record, json.loads(self.record_path.read_text(encoding="utf-8")))
        # Nothing was published beyond the run result and nothing moved Source.
        self.assertEqual(["decomposition_run_result.json"],
                         sorted(path.name for path in Path(record["artifact_root"]).iterdir()))
        self.assertEqual(self.head, self.git("rev-parse", "HEAD"))
        self.assertEqual("", self.git("status", "--porcelain=v1", "--untracked-files=all"))

    def test_retained_facts_are_bounded_to_stated_reasons_counts_and_candidate_identity(self):
        run_result = self.run_result()
        run_result["latest_candidate"] = {
            **run_result["latest_candidate"], "result": {"children": ["unreviewed-child"]},
        }

        record = self.propose(run_result)

        facts = record["needs_human"]
        self.assertEqual({"rejection_reasons", "unresolved_findings", "human_next_step",
                          "calls_used", "author_corrections_used", "latest_candidate"}, set(facts))
        self.assertEqual({"version", "author_provider", "sha256", "decision", "graph_delta_plan_id"},
                         set(facts["latest_candidate"]))
        retained = json.dumps(record)
        for absent in ("unreviewed-child", "finding_history", "rounds/02", "revised_candidate_valid"):
            self.assertNotIn(absent, retained)

    def test_either_an_unresolved_finding_or_a_rejection_reason_is_a_stated_reason(self):
        """Both D1B.2 needs_human shapes are human-review states.

        A reviewer `needs_human` verdict carries unresolved findings and may carry
        no rejection reason; a call limit that ends before independent review
        carries a rejection reason and no finding.
        """
        shapes = (
            ("findings-only", {"rejection_reasons": []}),
            ("reasons-only", {"unresolved_findings": [], "rejection_reasons": [
                "call limit ended before an independent provider reviewed the initial candidate"]}),
        )
        for label, changes in shapes:
            with self.subTest(label):
                run_id = f"{self.RUN_ID}-{label}"
                run_result = {**self.run_result(run_id), **changes}
                self.record_path.unlink(missing_ok=True)
                record = self.propose(run_result, run_id=run_id)
                self.assertEqual("needs_human", record["status"])
                self.assertEqual(expected_facts(run_result), record["needs_human"])

    # -- fail closed ---------------------------------------------------------

    def test_needs_human_with_another_identity_still_fails(self):
        cases = (
            ("run-id", lambda value: value.update(run_id="assistant-nsc-004-decompose-other"),
             "Decomposition review run_id is"),
            ("task-id", lambda value: value.update(task_id="NSC-003"),
             "Decomposition review task_id is"),
            ("providers", lambda value: value.update(provider_order=["codex", "claude"]),
             "Decomposition review provider_order is"),
            ("max-calls", lambda value: value.update(max_calls=3),
             "Decomposition review max_calls is"),
            ("independence", lambda value: value.update(review_independence="same_provider_separate_sessions"),
             "Decomposition review review_independence is"),
            ("authority", lambda value: value.update(authority="applied"),
             "Decomposition review authority is"),
            ("schema", lambda value: value.update(schema_version="2.0"),
             "Decomposition review schema_version is"),
            ("source-head", lambda value: value["source_identity"].update(head_commit="0" * 40),
             "Decomposition run used another source commit or tree"),
            ("source-tree", lambda value: value["source_identity"].update(head_tree="0" * 40),
             "Decomposition run used another source commit or tree"),
            ("contract-sha", lambda value: value["task_execution_contract_identity"].update(sha256="0" * 64),
             "Decomposition run used another parent contract"),
            ("contract-revision", lambda value: value["task_execution_contract_identity"].update(revision=2),
             "Decomposition run used another parent contract"),
        )
        for label, mutate, message in cases:
            with self.subTest(label):
                self.assert_run_refused(label, mutate, message)

    def test_needs_human_that_states_no_reason_still_fails(self):
        cases = (
            ("no-reason", lambda value: value.update(rejection_reasons=[], unresolved_findings=[]),
             "states no unresolved finding or rejection reason"),
            ("blank-reason", lambda value: value.update(rejection_reasons=["   "], unresolved_findings=[]),
             "rejection_reasons are not stated reasons"),
            ("reasons-not-a-list", lambda value: value.update(rejection_reasons=None),
             "rejection_reasons are not stated reasons"),
            ("findings-not-a-list", lambda value: value.update(unresolved_findings=None),
             "unresolved_findings is not a list"),
            ("malformed-finding", lambda value: value["unresolved_findings"][0].update(finding_id="not a finding id"),
             r"unresolved_findings\[0\]\.finding_id must match"),
        )
        for label, mutate, message in cases:
            with self.subTest(label):
                self.assert_run_refused(label, mutate, message)

    def test_needs_human_that_names_proposal_artifacts_or_overspends_still_fails(self):
        cases = (
            ("result-path", lambda value: value.update(decomposition_result_path="decomposition_result.json"),
             "names a proposal artifact: decomposition_result_path"),
            ("graph-path", lambda value: value.update(graph_delta_path="graph_delta.json"),
             "names a proposal artifact: graph_delta_path"),
            ("result-path-absent", lambda value: value.pop("decomposition_result_path"),
             "names a proposal artifact: decomposition_result_path"),
            ("calls-above-limit", lambda value: value.update(calls_used=3),
             "calls_used is 3, not a count within max_calls"),
            ("calls-boolean", lambda value: value.update(calls_used=True),
             "calls_used is True, not a count within max_calls"),
            ("corrections-above-one", lambda value: value.update(author_corrections_used=2),
             "author_corrections_used is 2, not 0 or 1"),
        )
        for label, mutate, message in cases:
            with self.subTest(label):
                self.assert_run_refused(label, mutate, message)

    def test_any_other_run_status_still_fails_the_proposal(self):
        for status in ("rejected", "agent_failed", "review_ready", None):
            with self.subTest(run_status=status):
                self.assert_run_refused(
                    f"status-{status}".replace("_", "-"),
                    lambda value, status=status: value.update(run_status=status),
                    r"\S",
                )

    # -- inspection and application ------------------------------------------

    def test_inspect_revalidates_the_retained_needs_human_facts_read_only(self):
        run_result = self.run_result()
        record = write_needs_human_record(
            self.manager, task_id=self.TASK_ID, task=self.task, head=self.head, tree=self.tree,
            branch=self.branch, run_id=self.RUN_ID, run_result=run_result,
        )

        def durable_bytes() -> dict[str, bytes]:
            return {str(path.relative_to(self.manager.root)): path.read_bytes()
                    for path in sorted(self.manager.root.rglob("*")) if path.is_file()}

        before = durable_bytes()
        self.assertEqual(record, decomposition_module.inspect(self.manager, self.TASK_ID))
        self.assertEqual(before, durable_bytes())
        self.assertEqual(self.head, self.git("rev-parse", "HEAD"))
        self.assertEqual("", self.git("status", "--porcelain=v1", "--untracked-files=all"))

        # The facts are re-derived from the exact retained run result every time.
        run_path = Path(record["artifact_root"]) / "decomposition_run_result.json"
        original = run_path.read_bytes()
        cases = (
            ("another stated reason", lambda value: value.update(rejection_reasons=["another reason"]),
             "Retained needs_human facts differ from the decomposition run result"),
            ("no stated reason", lambda value: value.update(rejection_reasons=[], unresolved_findings=[]),
             "states no unresolved finding or rejection reason"),
            ("another run", lambda value: value.update(run_id="assistant-nsc-004-decompose-other"),
             "Decomposition review run_id is"),
            ("a review_ready claim", lambda value: value.update(run_status="review_ready"),
             "run_status is 'review_ready', expected 'needs_human'"),
            ("a named proposal artifact", lambda value: value.update(graph_delta_path="graph_delta.json"),
             "names a proposal artifact: graph_delta_path"),
        )
        for label, mutate, message in cases:
            with self.subTest(label):
                changed = copy.deepcopy(run_result)
                mutate(changed)
                decomposition_tests._write_json(run_path, changed)
                try:
                    with self.assertRaisesRegex(ValueError, message):
                        decomposition_module.inspect(self.manager, self.TASK_ID)
                finally:
                    run_path.write_bytes(original)
        self.assertEqual(record, decomposition_module.inspect(self.manager, self.TASK_ID))

    def test_apply_refuses_a_needs_human_record(self):
        record = write_needs_human_record(
            self.manager, task_id=self.TASK_ID, task=self.task, head=self.head, tree=self.tree,
            branch=self.branch, run_id=self.RUN_ID,
        )
        record_bytes = self.record_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "Exact decomposition run is not awaiting local application"):
            decomposition_module.apply(
                self.manager, self.TASK_ID, run_id=record["run_id"],
                expected_source_commit=self.head, target_branch=self.branch,
            )

        self.assertEqual(record_bytes, self.record_path.read_bytes())
        self.assertEqual(self.head, self.git("rev-parse", "HEAD"))
        self.assertFalse((self.source / "Tasks" / "NSC-1001.yaml").exists())


class ReviewReadyUnchangedTests(unittest.TestCase):
    """A review_ready run is still recorded, inspected and refused exactly as before."""

    setUp = decomposition_tests.BoundedAuthorCorrectionReviewTests.setUp
    author_round = decomposition_tests.BoundedAuthorCorrectionReviewTests.author_round
    reviewer_round = decomposition_tests.BoundedAuthorCorrectionReviewTests.reviewer_round

    def test_review_ready_run_is_still_recorded_review_ready_with_its_exact_proof(self):
        run_id = "fixture-review-ready-through-run"
        run_result = {**self.run_result, "run_id": run_id,
                      "rounds": [self.author_round(), self.reviewer_round()]}
        reviewed = self.artifact_root

        def publish(artifact_root: Path) -> None:
            for name in ("decomposition_result.json", "graph_delta.json"):
                (artifact_root / name).write_bytes((reviewed / name).read_bytes())
            decomposition_tests._write_json(artifact_root / "decomposition_run_result.json", run_result)

        head = decomposition_tests._git(self.manager.source, "rev-parse", "HEAD")
        with fake_compose(run_id, publish, head=head):
            record = decomposition_module.run(
                self.manager, self.task_id, run_id, providers="claude,codex",
                compose_project="nosafecircle", execution_authorized=True,
            )

        self.assertEqual(("review_ready", 0), (record["status"], record["exit_code"]))
        self.assertNotIn("needs_human", record)
        self.assertNotIn("error", record)
        self.assertEqual(decomposition_module._verify_review(self.manager, record), record["review"])
        self.assertEqual(self.digest, record["review"]["candidate_sha256"])
        self.assertEqual(["fixture-author", "fixture-reviewer"], record["review"]["models"])
        self.assertEqual(record["review"], decomposition_module.inspect(self.manager, self.task_id)["review"])

    def test_review_ready_record_whose_run_says_needs_human_is_never_applicable(self):
        decomposition_tests._write_json(
            self.artifact_root / "decomposition_run_result.json",
            {**self.run_result, "rounds": [self.author_round(), self.reviewer_round()],
             "run_status": "needs_human"},
        )
        message = "Decomposition review run_status is 'needs_human', expected 'review_ready'"
        with self.assertRaisesRegex(ValueError, message):
            decomposition_module._verify_review(self.manager, self.record)
        write_record(self.manager.records / f"{self.task_id}.decomposition.json", self.record)
        head = decomposition_tests._git(self.manager.source, "rev-parse", "HEAD")
        branch = decomposition_tests._git(self.manager.source, "branch", "--show-current")
        with self.assertRaisesRegex(ValueError, message):
            decomposition_module.inspect(self.manager, self.task_id)
        with self.assertRaisesRegex(ValueError, message):
            decomposition_module.apply(self.manager, self.task_id, run_id=self.record["run_id"],
                                       expected_source_commit=head, target_branch=branch)
        self.assertEqual(head, decomposition_tests._git(self.manager.source, "rev-parse", "HEAD"))


class _GraphFixture:
    """The graph controller test repository plus a childless decomposition parent and one unrelated task."""

    PARENT = "NSC-1200"
    UNRELATED = "NSC-1201"

    git = graph_tests.GraphControllerTests.git
    write_task = graph_tests.GraphControllerTests.write_task
    _graph_setUp = graph_tests.GraphControllerTests.setUp

    def setUp(self):
        self._graph_setUp()
        self.write_task(self.PARENT, origin="human_approved_synthetic_gauntlet",
                        execution_scope="needs_execution_decomposition")
        self.write_task(self.UNRELATED, origin="human_approved_synthetic_gauntlet")
        self.git("add", f"Tasks/{self.PARENT}.yaml", f"Tasks/{self.UNRELATED}.yaml")
        self.git("commit", "-m", "needs_human fixture parent and unrelated task")
        self.head = self.git("rev-parse", "HEAD").decode().strip()
        self.tree = self.git("rev-parse", "HEAD^{tree}").decode().strip()
        self.branch = self.git("branch", "--show-current").decode().strip()
        self.parent_task = load_committed_task(self.source, self.PARENT, commit=self.head)
        self.manager.records.mkdir(parents=True, exist_ok=True)
        self.record_path = self.manager.records / f"{self.PARENT}.decomposition.json"
        self.run_id = f"assistant-{self.PARENT.casefold()}-decompose-{self.head[:12]}"

    def parent_run_result(self) -> dict:
        return needs_human_run_result(run_id=self.run_id, task_id=self.PARENT, task=self.parent_task,
                                      head=self.head, tree=self.tree, branch=self.branch)

    def write_parent_record(self, **overrides) -> dict:
        return write_needs_human_record(
            self.manager, task_id=self.PARENT, task=self.parent_task, head=self.head,
            tree=self.tree, branch=self.branch, run_id=self.run_id, **overrides,
        )

    def graph_controller(self, *targets: str, **options) -> GraphController:
        return GraphController(
            self.manager,
            GraphPolicy(targets=targets, auto_approve_gauntlet=True, target_branch=self.branch),
            {"provider": "claude", "execution_model": "fixture"},
            **options,
        )

    def waiting_entry(self, record: dict) -> dict:
        return {"task_id": self.PARENT, "reason": "decomposition_needs_human",
                "run_id": record["run_id"], "artifact_root": record["artifact_root"]}


class NeedsHumanPlannerTests(_GraphFixture, unittest.TestCase):
    """A needs_human parent waits for a person; it is never an action, blocked or retried."""

    def test_needs_human_parent_waits_for_a_person_while_unrelated_work_continues(self):
        record = self.write_parent_record()

        plan = self.graph_controller(self.PARENT, self.UNRELATED).plan()

        self.assertEqual([self.waiting_entry(record)], plan["waiting_human"])
        self.assertEqual([], plan["blocked"])
        self.assertEqual([{"kind": "prepare", "task_id": self.UNRELATED, "source_commit": self.head}],
                         plan["next_actions"])
        self.assertEqual([], plan["held"])
        self.assertEqual("actionable", plan["status"])

    def test_needs_human_parent_alone_leaves_the_plan_awaiting_human(self):
        record = self.write_parent_record()

        plan = self.graph_controller(self.PARENT).plan()

        self.assertEqual([], plan["next_actions"])
        self.assertEqual([], plan["blocked"])
        self.assertEqual([self.waiting_entry(record)], plan["waiting_human"])
        self.assertEqual("awaiting_human", plan["status"])

    def test_run_loop_ends_awaiting_human_and_auto_approval_never_acts(self):
        self.write_parent_record()
        record_bytes = self.record_path.read_bytes()
        self.assertTrue(is_synthetic_gauntlet(self.manager.source, self.PARENT, self.head))
        clock = job_tests.FixtureClock()
        controller = self.graph_controller(
            self.PARENT, execution_authorized=True, sleep=clock.sleep, clock=clock,
            job_host=job_tests.FixtureHost(clock),
        )
        self.assertTrue(controller.policy.auto_approve_gauntlet)

        with patch.object(controller, "_execute_foreground",
                          side_effect=AssertionError("no graph action may run")), \
                patch.object(controller, "_launch_job",
                             side_effect=AssertionError("no background job may launch")):
            result = controller.run(max_actions=5)

        self.assertEqual("awaiting_human", result["status"])
        self.assertEqual([], result["completed_actions"])
        self.assertEqual([], result["harvested_jobs"])
        self.assertEqual(["decomposition_needs_human"], [item["reason"] for item in result["waiting_human"]])
        saved = json.loads(controller.state_path.read_text(encoding="utf-8"))
        self.assertEqual(("awaiting_human", None), (saved["status"], saved["last_error"]))
        self.assertEqual(record_bytes, self.record_path.read_bytes())
        self.assertEqual(self.head, self.git("rev-parse", "HEAD").decode().strip())


class _HeldJob:
    """The Job Object handle `_child_main` holds for its whole life."""

    def close(self) -> None:
        return None


class _InProcessChildHost:
    """A job host whose child is this test process, so the real `_child_main` binds a real receipt.

    `launch` records this process's exact identity for the child; the test then
    runs `background_jobs._child_main` itself, which authenticates the ticket and
    ready receipt, runs `decomposition.run` and writes its receipt. Docker is the
    fixture CLI from the background job tests.
    """

    def __init__(self, clock: job_tests.FixtureClock):
        self.identity = background_jobs._identity(os.getpid())
        self.docker_cli = job_tests.FixtureDocker(clock)

    def identify_self(self) -> dict:
        return {"pid": 1, "created_ticks": 1, "image": "fixture-controller"}

    def spawn(self, run_root: Path, request: dict) -> dict:
        return {"pid": os.getpid(), "process_identity": dict(self.identity)}

    def handoff(self, run_root: Path, process_identity: dict, job_name: str) -> None:
        return None

    def alive(self, identity: dict) -> None:
        return None

    def tree_active(self, job_name: str) -> int:
        return 0

    def adopt(self, identity: dict, job_name: str) -> None:
        raise background_jobs.BackgroundJobError("the in-process fixture child is never adopted")

    def stop(self, identity: dict, job_name: str) -> dict:
        raise background_jobs.BackgroundJobError("the in-process fixture child is never stopped")

    def docker(self, arguments: list[str]) -> tuple[int, str, str]:
        return self.docker_cli(arguments)


@unittest.skipUnless(os.name == "nt", "the in-process child binds this process's Windows identity")
class NeedsHumanBackgroundJobTests(_GraphFixture, unittest.TestCase):
    """A decompose job whose run ends needs_human succeeds, harvests completed and blocks nothing."""

    def test_needs_human_decompose_job_succeeds_harvests_completed_and_waits_for_a_person(self):
        clock = job_tests.FixtureClock()
        host = _InProcessChildHost(clock)
        controller = self.graph_controller(
            self.PARENT, self.UNRELATED, execution_authorized=True,
            sleep=clock.sleep, clock=clock, job_host=host,
        )
        action = {"kind": "decompose", "task_id": self.PARENT}
        self.assertIn(action, controller.plan()["next_actions"])
        with controller._controller_owner(uuid.uuid4().hex, max_actions=1, allowed_actions=None):
            launched = controller.execute(action)
        self.assertEqual("launched", launched["status"])
        index = background_jobs.read_index(self.manager, self.PARENT)
        self.assertEqual(self.run_id, index["identity"]["run_id"])
        run_result = self.parent_run_result()

        def publish(artifact_root: Path) -> None:
            decomposition_tests._write_json(artifact_root / "decomposition_run_result.json", run_result)

        with fake_compose(self.run_id, publish, head=self.head), \
                patch("Pipeline.AssistantControl.windows_job.is_assigned", return_value=True), \
                patch("Pipeline.AssistantControl.windows_job.open_named", return_value=_HeldJob()):
            exit_code = background_jobs._child_main([
                "--child", "--request", str(index["request"]),
                "--source", str(self.manager.source), "--checkout-root", str(self.manager.root),
                "--task", self.PARENT, "--job", str(index["job_id"]),
            ])

        receipt = json.loads((Path(index["run_root"]) / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(("succeeded", None), (receipt["status"], receipt["error"]), receipt["error"])
        self.assertEqual(0, exit_code)
        self.assertEqual("needs_human", receipt["result"]["status"])
        self.assertEqual(expected_facts(run_result), receipt["result"]["needs_human"])

        with controller._controller_owner(uuid.uuid4().hex, max_actions=1, allowed_actions=None):
            harvested = controller._harvest_jobs()
            plan = controller.plan()

        self.assertEqual([(self.PARENT, "completed", "needs_human", None)],
                         [(item["task_id"], item["status"], item["result_status"], item["error"])
                          for item in harvested])
        index = background_jobs.read_index(self.manager, self.PARENT)
        self.assertEqual(("completed", "needs_human", None),
                         (index["status"], index["result_status"], index["error"]))
        self.assertIsNone(index.get("authentication"))
        self.assertEqual("verified_absent", index["provider_container_cleanup"]["status"])
        # The completed ticket gates nothing and is never relaunched: the parent
        # waits for a person while the unrelated task keeps its action.
        self.assertIsNone(controller._job_gate(self.PARENT, index))
        record = json.loads(self.record_path.read_text(encoding="utf-8"))
        self.assertEqual(("needs_human", 0), (record["status"], record["exit_code"]))
        self.assertEqual([self.waiting_entry(record)], plan["waiting_human"])
        self.assertEqual([], plan["blocked"])
        self.assertEqual([{"kind": "prepare", "task_id": self.UNRELATED, "source_commit": self.head}],
                         plan["next_actions"])
        self.assertEqual("actionable", plan["status"])


class NeedsHumanViewerTests(_GraphFixture, unittest.TestCase):
    """The viewer shows a needs_human parent as waiting on a person, with the reasons it states."""

    def test_needs_human_record_projects_human_action_with_its_stated_reasons(self):
        record = self.write_parent_record()
        reader = AssistantSnapshot(self.source, self.manager.root)

        row = reader.task_row(self.parent_task)

        self.assertEqual("human_action", row["state"])
        progress = row["progress"]
        self.assertEqual("decomposition_needs_human", progress["phase"])
        self.assertEqual(NSC_1165_REASON, progress["human_reason"])
        self.assertEqual(
            "Independent review stopped at a human authority boundary; no children were applied. "
            + NSC_1165_REASON,
            progress["transition_context"],
        )
        self.assertNotIn("blocked_reason", progress)
        self.assertEqual((record["run_id"], record["artifact_root"]),
                         (row["decomposition_run"]["run_id"], row["decomposition_run"]["artifact_root"]))

    def test_needs_human_record_that_states_no_reason_is_not_authenticated(self):
        facts = {**expected_facts(self.parent_run_result()), "rejection_reasons": [],
                 "unresolved_findings": []}
        self.write_parent_record(facts=facts)

        row = AssistantSnapshot(self.source, self.manager.root).task_row(self.parent_task)

        self.assertEqual("blocked", row["state"])
        self.assertEqual("decomposition_record_invalid", row["progress"]["phase"])
        self.assertEqual("needs_human decomposition record states no reason",
                         row["progress"]["blocked_reason"])

    def test_running_auto_approve_controller_leaves_a_needs_human_parent_on_the_person(self):
        (self.manager.records / "graph-controller.json").write_text(json.dumps({
            "schema_version": "assistant-graph-controller/v1", "status": "running",
            "targets": [self.PARENT, "NSC-1104"],
            "current_action": {"kind": "prepare", "task_id": self.UNRELATED},
            "auto_approve_gauntlet": True,
        }), encoding="utf-8")
        reader = AssistantSnapshot(self.source, self.manager.root)
        parent_progress = {
            "phase": "decomposition_needs_human", "human_reason": NSC_1165_REASON,
            "transition_context": "Independent review stopped at a human authority boundary; "
                                  "no children were applied. " + NSC_1165_REASON,
        }
        state = {
            "run": {"targets": [], "source_commit": self.head},
            "tasks": [
                {"id": self.PARENT, "parent": None, "depends_on": [], "in_scope": True,
                 "state": "human_action", "progress": dict(parent_progress)},
                {"id": "NSC-1104", "parent": None, "depends_on": [], "in_scope": True,
                 "state": "human_action", "candidate_commit": "a" * 40,
                 "progress": {"phase": "awaiting_human"}},
            ],
        }

        with patch("Pipeline.AssistantControl.viewer.is_synthetic_gauntlet", return_value=True), \
                patch.object(reader, "_controller_owner_active", return_value=True):
            reader._apply_graph_controller(state, {})

        rows = {row["id"]: row for row in state["tasks"]}
        self.assertEqual(("human_action", parent_progress),
                         (rows[self.PARENT]["state"], rows[self.PARENT]["progress"]))
        # The same projection still shows an automatically approved candidate as automatic.
        self.assertEqual(("active", "automatic_validation"),
                         (rows["NSC-1104"]["state"], rows["NSC-1104"]["progress"]["phase"]))

    def test_preflight_plan_with_a_waiting_human_decomposition_projects_consistently(self):
        self.write_parent_record()
        plan = self.graph_controller(self.PARENT, self.UNRELATED).persist_preflight()
        self.assertEqual(["decomposition_needs_human"], [item["reason"] for item in plan["waiting_human"]])

        state = AssistantSnapshot(self.source, self.manager.root).build()

        self.assertNotIn("inspection_error", state)
        self.assertEqual("preflight", state["run"]["status"])
        self.assertEqual([self.PARENT, self.UNRELATED], state["run"]["targets"])
        rows = {row["id"]: row for row in state["tasks"]}
        self.assertEqual(("human_action", "decomposition_needs_human"),
                         (rows[self.PARENT]["state"], rows[self.PARENT]["progress"]["phase"]))
        self.assertEqual("ready", rows[self.UNRELATED]["state"])
        self.assertEqual({"kind": "human_review", "task_ids": [self.PARENT]}, state["assistant_attention"])


if __name__ == "__main__":
    unittest.main()
