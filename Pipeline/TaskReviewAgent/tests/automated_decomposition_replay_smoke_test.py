#!/usr/bin/env python3
"""Deterministic replay tests for machine-approved synthetic decomposition."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
for module_root in (ROOT, PIPELINE_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.TaskReviewAgent import decomposition_replay as replay  # noqa: E402
import Pipeline.TaskReviewAgent.decomposition_policy_audit as audit  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    AUTOMATED_DECOMPOSITION_POLICY_AUTHORITY,
    WorkflowEventType,
    WorkflowPhase,
)
from graph_delta import GraphDeltaPlan  # noqa: E402


TASK_ID = "NSC-911"
PLAN_ID = "GDP-" + ("3" * 64)
SOURCE_HEAD = "1" * 40
SOURCE_TREE = "2" * 40
EXACT_TASK_HASH = "4" * 64
PARENT_RESOURCES = [
    "repo-file:Assets/Gauntlet/MuffcabbageGauntlet911Alpha.cs",
    "repo-file:Assets/Gauntlet/MuffcabbageGauntlet911Alpha.cs.meta",
    "repo-file:Assets/Gauntlet/MuffcabbageGauntlet911Beta.cs",
    "repo-file:Assets/Gauntlet/MuffcabbageGauntlet911Beta.cs.meta",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_replay_error(action, text: str) -> None:
    try:
        action()
    except replay.DecompositionReplayError as exc:
        require(text in str(exc), f"unexpected error: {exc}")
    else:
        raise AssertionError(f"expected DecompositionReplayError containing {text!r}")


def fixture_task() -> dict:
    return {
        "id": TASK_ID,
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "needs_execution_decomposition",
        "decomposition_state": "candidate",
        "depends_on": [],
        "exclusive_resources": list(PARENT_RESOURCES),
        "acceptance_criteria": [],
        "completion_gates": [],
        "downstream_integration_obligations": [],
        "task_contract_sha256": EXACT_TASK_HASH,
    }


def child(task_id: str, resources: list[str]) -> dict:
    return {
        "id": task_id,
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "parent": TASK_ID,
        "depends_on": [],
        "exclusive_resources": resources,
        "acceptance_criteria": [],
        "completion_gates": [],
        "downstream_integration_obligations": [],
    }


def fixture(root: Path):
    task = fixture_task()
    parent_payload = dict(task)
    parent_payload.pop("task_contract_sha256")
    parent_hash = replay.semantic_json_sha256(parent_payload)
    children = [
        child("NSC-991", PARENT_RESOURCES[:2]),
        child("NSC-992", PARENT_RESOURCES[2:]),
    ]
    graph_payload = {
        "plan_id": PLAN_ID,
        "parent_before_hash": parent_hash,
        "parent_before_summary": {
            "task_id": TASK_ID,
            "contract_revision": 1,
        },
        "proposed_child_contracts": children,
    }
    graph = GraphDeltaPlan.from_payload(graph_payload)
    graph_hash = hashlib.sha256(graph.canonical_json().encode("utf-8")).hexdigest()
    artifact_root = root / "artifacts"
    artifact_root.mkdir(parents=True)
    (artifact_root / "graph_delta.json").write_text(
        json.dumps(graph_payload), encoding="utf-8"
    )
    decomposition_bytes = b'{"fixture":"accepted"}\n'
    (artifact_root / "decomposition_result.json").write_bytes(decomposition_bytes)
    policy_path = (
        root
        / "Pipeline"
        / "TaskReviewAgent"
        / "authoritative_validation_policy.json"
    )
    policy_path.parent.mkdir(parents=True)
    # The worktree form deliberately uses CRLF. Git's clean-filtered blob
    # identity, not raw worktree/blob byte equality, is the Windows authority.
    policy_bytes = b'{"fixture":"policy"}\r\n'
    policy_path.write_bytes(policy_bytes)
    child_evidence = [
        {
            "task_id": item["id"],
            "task_contract_sha256": replay.semantic_json_sha256(item),
            "exclusive_resources": sorted(item["exclusive_resources"]),
        }
        for item in children
    ]
    policy_hash = "5" * 64
    handoff = SimpleNamespace(
        event_type=WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED,
        event_id="6" * 64,
        details={
            "graph_delta_plan_id": PLAN_ID,
            "head_commit": SOURCE_HEAD,
            "artifact_root": str(artifact_root),
            "graph_delta_sha256": graph_hash,
            "branch": "nsc-911-synthetic",
        },
    )
    evidence = {
        "handoff_event_id": handoff.event_id,
        "graph_delta_plan_id": PLAN_ID,
        "graph_delta_sha256": graph_hash,
        "source_tree": SOURCE_TREE,
        "task_contract_sha256": EXACT_TASK_HASH,
        "parent_contract_sha256": parent_hash,
        "decomposition_result_sha256": hashlib.sha256(decomposition_bytes).hexdigest(),
        "parent_exclusive_resources": sorted(PARENT_RESOURCES),
        "children": child_evidence,
        "validation_policy_authority": AUTOMATED_DECOMPOSITION_POLICY_AUTHORITY,
        "validation_policy_sha256": policy_hash,
    }
    approval = SimpleNamespace(
        event_type=WorkflowEventType.AUTOMATED_DECOMPOSITION_APPLICATION_APPROVED,
        details=evidence,
    )
    state = SimpleNamespace(
        phase=WorkflowPhase.DECOMPOSITION_APPLY,
        task_id=TASK_ID,
        task_contract_sha256=EXACT_TASK_HASH,
    )
    snapshot = SimpleNamespace(valid=True, state=state, events=(handoff, approval))
    inspection = SimpleNamespace(status="fresh_source", reason="fixture fresh")
    return SimpleNamespace(
        source=root,
        task=task,
        graph=graph,
        handoff=handoff,
        approval=approval,
        snapshot=snapshot,
        policy_bytes=policy_bytes,
        policy_hash=policy_hash,
        inspection=inspection,
        artifact_root=artifact_root,
    )


def run_with_patches(data, *, audit_error=None):
    originals = (
        replay._git_text,
        replay.load_committed_task,
        replay.DecompositionResult,
        replay.audit_decomposition_policy,
        replay.decomposition_validation_policy_for,
        replay.inspect_graph_delta_replay,
    )
    policy_blob = "7" * 40

    def git_text(_source, *args):
        if args == ("rev-parse", f"{SOURCE_HEAD}^{{tree}}"):
            return SOURCE_TREE
        if args == (
            "rev-parse",
            f"{SOURCE_HEAD}:Pipeline/TaskReviewAgent/authoritative_validation_policy.json",
        ):
            return policy_blob
        if args[0:2] == (
            "hash-object",
            "--path=Pipeline/TaskReviewAgent/authoritative_validation_policy.json",
        ):
            return policy_blob
        raise AssertionError(f"unexpected Git proof: {args}")

    replay._git_text = git_text

    def load_task(_source, task_id, *, expected_sha256, commit):
        require(task_id == TASK_ID, task_id)
        require(expected_sha256 == EXACT_TASK_HASH, expected_sha256)
        require(commit == SOURCE_HEAD, commit)
        return dict(data.task)

    replay.load_committed_task = load_task
    replay.DecompositionResult = SimpleNamespace(
        from_dict=lambda _payload: SimpleNamespace(
            parent_task=SimpleNamespace(
                task_id=TASK_ID,
                contract_sha256=data.approval.details["parent_contract_sha256"],
            )
        )
    )
    audits: list[Any] = []

    def audit(_source, *, commit):
        # The audit must be bound to the authorized commit, never to current main.
        require(commit == SOURCE_HEAD, str(commit))
        audits.append(commit)
        if audit_error is not None:
            raise audit_error
        return {"templates_audited": []}

    replay.audit_decomposition_policy = audit
    data.audited = audits
    replay.decomposition_validation_policy_for = lambda *_args, **_kwargs: {
        "policy_sha256": data.policy_hash
    }
    replay.inspect_graph_delta_replay = lambda *_args, **_kwargs: data.inspection
    try:
        return replay.inspect_authorized_decomposition_replay(
            source=data.source,
            snapshot=data.snapshot,
            expected_head=SOURCE_HEAD,
        )
    finally:
        (
            replay._git_text,
            replay.load_committed_task,
            replay.DecompositionResult,
            replay.audit_decomposition_policy,
            replay.decomposition_validation_policy_for,
            replay.inspect_graph_delta_replay,
        ) = originals


def test_machine_approval_replays_only_after_exact_revalidation() -> None:
    with tempfile.TemporaryDirectory() as text:
        data = fixture(Path(text))
        result = run_with_patches(data)
        # The child-template audit runs, and it runs bound to the authorized
        # source commit rather than to whatever HEAD happens to be now.
        require(data.audited == [SOURCE_HEAD], str(data.audited))
        require(result.plan_id == PLAN_ID, str(result))
        require(result.authorized_source_head == SOURCE_HEAD, str(result))
        require(result.inspection is data.inspection, str(result))


def test_machine_approval_rejects_changed_proposal_bytes() -> None:
    with tempfile.TemporaryDirectory() as text:
        data = fixture(Path(text))
        (data.artifact_root / "decomposition_result.json").write_bytes(
            b'{"fixture":"tampered"}\n'
        )
        expect_replay_error(lambda: run_with_patches(data), "proposal bytes differ")


def test_machine_approval_must_immediately_follow_handoff() -> None:
    with tempfile.TemporaryDirectory() as text:
        data = fixture(Path(text))
        unrelated = SimpleNamespace(
            event_type=WorkflowEventType.BLOCKED,
            details={},
        )
        data.snapshot.events = (data.handoff, unrelated, data.approval)
        expect_replay_error(
            lambda: run_with_patches(data),
            "must immediately follow",
        )


def test_human_approval_remains_compatible() -> None:
    with tempfile.TemporaryDirectory() as text:
        data = fixture(Path(text))
        human = SimpleNamespace(
            event_type=WorkflowEventType.DECOMPOSITION_APPLICATION_APPROVED,
            details={"reviewed_plan_id": PLAN_ID},
        )
        data.snapshot.events = (data.handoff, human)
        result = run_with_patches(data)
        require(result.plan_id == PLAN_ID, str(result))
        # The whole automated-authority proof, audit included, is machine-only.
        require(data.audited == [], str(data.audited))


def test_policy_proof_is_bound_to_the_authorized_commit_not_current_main() -> None:
    """An authorized replay proves the policy that existed when it was authorized.

    The replay recomputes the decomposition policy while current main may have
    moved on. If the child-template audit read the working tree, a later,
    perfectly legitimate policy edit would retroactively invalidate an already
    authorized decomposition. The audit therefore receives the authorized source
    commit, and this test drives the real audit -- not the harness stub -- against
    a real repository whose main has moved.
    """

    with tempfile.TemporaryDirectory() as text:
        source = Path(text)
        relative = "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
        parent_id = "NSC-911"
        alpha = "repo-file:Assets/Fixture/Alpha.cs"
        beta = "repo-file:Assets/Fixture/Beta.cs"
        parent = {
            "schema_version": "2.0",
            "id": parent_id,
            "contract_revision": 1,
            "contract_disposition": "active",
            "title": "Fixture decomposition parent",
            "reconciliation_key": "fixture-replay-parent",
            "kind": "implementation",
            "execution_scope": "needs_execution_decomposition",
            "decomposition_state": "concrete",
            "parent": "NSC-001",
            "depends_on": [],
            "exclusive_resources": [alpha, beta],
            "acceptance_criteria": [],
            "completion_gates": [],
            "downstream_integration_obligations": [],
            "provenance": {"origin": "fixture", "gauntlet_id": "fixture-gauntlet-v1"},
        }

        def write(relative_path: str, payload: str) -> None:
            target = source / Path(relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(payload, encoding="utf-8", newline="\n")

        def run(*command: str) -> None:
            completed = subprocess.run(
                command,
                cwd=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            require(completed.returncode == 0, completed.stderr)

        def policy(templates: dict) -> str:
            return (
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "tasks": {},
                        "decomposition_child_templates": templates,
                    },
                    indent=2,
                )
                + "\n"
            )

        def variant(resources: list, name: str) -> dict:
            return {
                "required_exclusive_resources": resources,
                "required_test_platforms": ["EditMode"],
                "test_filters": {"EditMode": f"NoSafeCircle.Fixture.Tests.{name}"},
            }

        write(f"Tasks/{parent_id}.yaml", json.dumps(parent, indent=2, sort_keys=True) + "\n")
        write(
            relative,
            policy(
                {
                    parent_id: {
                        "parent_task_contract_sha256": audit.parent_semantic_hash(parent),
                        "validation_variants": [
                            variant([alpha], "AlphaTests"),
                            variant([beta], "BetaTests"),
                        ],
                        "authority": audit.DECOMPOSITION_TEMPLATE_AUTHORITY,
                    }
                }
            ),
        )
        run("git", "init", "-b", "main")
        run("git", "config", "user.name", "No Safe Circle TaskReviewAgent")
        run("git", "config", "user.email", "task-review-agent@nosafecircle.invalid")
        run("git", "add", ".")
        run("git", "commit", "-m", "authorized decomposition state")
        authorized_head = replay._git_text(source, "rev-parse", "HEAD")

        # Main moves on: the template is retired and the contract is revised.
        write(relative, policy({}))
        revised = dict(parent, contract_revision=2)
        write(f"Tasks/{parent_id}.yaml", json.dumps(revised, indent=2, sort_keys=True) + "\n")
        run("git", "add", ".")
        run("git", "commit", "-m", "moved main")
        require(
            replay._git_text(source, "rev-parse", "HEAD") != authorized_head,
            "fixture did not move main",
        )

        # Bound to the authorized commit: still provable.
        receipt = audit.audit_decomposition_policy(source, commit=authorized_head)
        require(
            [item["parent_task_id"] for item in receipt["templates_audited"]] == [parent_id],
            str(receipt),
        )
        # Bound to current main: genuinely different, which is why the commit
        # must be stated rather than assumed.
        try:
            audit.audit_decomposition_policy(source)
        except audit.ValidationPolicyAuditError as exc:
            require("no child template" in str(exc), str(exc))
        else:
            raise AssertionError("current main accepted a retired template")

        # The audit the replay imports is the one exercised above, so the
        # commit-bound proof and the replay's proof cannot diverge.
        require(
            replay.audit_decomposition_policy is audit.audit_decomposition_policy,
            "the replay does not use the committed policy audit",
        )


def test_an_unprovable_policy_at_the_authorized_commit_stops_the_replay() -> None:
    """The audit's verdict is load-bearing, not advisory.

    The replay converts a ValidationPolicyAuditError into a typed replay failure.
    Without a test the conversion could be deleted and every other replay test
    would still pass, because the harness stub never fails.
    """

    with tempfile.TemporaryDirectory() as text:
        data = fixture(Path(text))
        try:
            run_with_patches(
                data,
                audit_error=audit.ValidationPolicyAuditError(
                    "decomposition template for NSC-777 is stale"
                ),
            )
        except replay.DecompositionReplayError as exc:
            require(
                "could not prove the decomposition policy at the authorized source "
                "commit" in str(exc),
                str(exc),
            )
            require("is stale" in str(exc), str(exc))
        else:
            raise AssertionError("an unprovable policy did not stop the replay")
        require(data.audited == [SOURCE_HEAD], str(data.audited))


def test_clean_filtered_policy_identity_accepts_crlf_worktree() -> None:
    with tempfile.TemporaryDirectory() as text:
        source = Path(text)
        relative = "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
        policy = source / Path(relative)
        policy.parent.mkdir(parents=True)
        policy.write_bytes(
            b'{\r\n  "fixture": "policy",\n  "mode": "mixed"\r\n}\n'
        )
        commands = (
            ("git", "init", "-b", "main"),
            ("git", "config", "core.autocrlf", "true"),
            ("git", "config", "user.name", "No Safe Circle TaskReviewAgent"),
            ("git", "config", "user.email", "task-review-agent@nosafecircle.invalid"),
            ("git", "add", relative),
            ("git", "commit", "-m", "fixture policy"),
        )
        for command in commands:
            completed = subprocess.run(
                command,
                cwd=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            require(completed.returncode == 0, completed.stderr)
        head = replay._git_text(source, "rev-parse", "HEAD")
        committed = subprocess.run(
            ("git", "show", f"{head}:{relative}"),
            cwd=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        require(committed.returncode == 0, committed.stderr.decode(errors="replace"))
        require(policy.read_bytes() != committed.stdout, "fixture did not create CRLF drift")
        status = replay._git_text(
            source,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        require(
            status == "",
            f"Git did not classify the CRLF worktree as clean: {status!r}",
        )
        eol = replay._git_text(source, "ls-files", "--eol", "--", relative)
        require(
            eol.startswith("i/lf") and "w/mixed" in eol,
            f"fixture did not preserve the expected clean mixed-EOL worktree: {eol!r}",
        )
        raw_blob = replay._git_text(source, "hash-object", "--no-filters", str(policy))
        committed_blob = replay._git_text(
            source, "rev-parse", f"{head}:{relative}"
        )
        require(raw_blob != committed_blob, "fixture did not preserve raw EOL drift")
        require(
            replay._working_file_matches_committed_blob(
                source,
                authorized_head=head,
                relative_path=relative,
            ),
            "clean-filtered policy identity rejected a clean CRLF worktree",
        )


def main() -> int:
    tests = (
        test_machine_approval_replays_only_after_exact_revalidation,
        test_machine_approval_rejects_changed_proposal_bytes,
        test_machine_approval_must_immediately_follow_handoff,
        test_human_approval_remains_compatible,
        test_clean_filtered_policy_identity_accepts_crlf_worktree,
        test_policy_proof_is_bound_to_the_authorized_commit_not_current_main,
        test_an_unprovable_policy_at_the_authorized_commit_stops_the_replay,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS automated decomposition replay smoke suite ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
