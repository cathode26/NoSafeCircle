"""One-time, guarded recovery of NSC-089 after the new-file resource repair."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from .issue_workflow import (
    WorkflowActor, WorkflowEventType, WorkflowState, labels_for_state,
    render_event_comment, transition, update_issue_body, utc_now,
)
from .issue_workflow_store import GhIssueBackend, IssueWorkflowService

TASK_ID = "NSC-089"
ISSUE_NUMBER = 125
OLD_COMMIT = "731c1c10cfb1a2736037e520a388a6e5c38ec226"
REPAIRED_COMMIT = "f2a9a6e1d61ccc3bc0a0ef51a8fad03c3a2d2ed1"
WORKER_ID = "graph-sol-20260914"
ADDED_RESOURCES = {
    "repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/World/GameplayNavigationSurface.cs",
    "repo-file:Assets/NoSafeCircle/DoorPrototype/Tests/Editor/NavMeshAgentConfigurationTests.cs",
}


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ("git", "-C", str(root), *args), capture_output=True, check=False,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.decode(errors='replace')}")
    return result.stdout


def committed_contract(root: Path, commit: str) -> tuple[dict, str]:
    raw = _git(root, "show", f"{commit}:Tasks/{TASK_ID}.yaml")
    contract = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(contract, dict) or contract.get("id") != TASK_ID:
        raise RuntimeError("committed NSC-089 contract is malformed")
    return contract, hashlib.sha256(raw).hexdigest()


def verify_contract_repair(old: dict, new: dict) -> None:
    if old.get("contract_revision") != 1 or new.get("contract_revision") != 2:
        raise RuntimeError("NSC-089 contract revision is not exactly 1 to 2")
    old_resources = old.get("exclusive_resources")
    new_resources = new.get("exclusive_resources")
    if not isinstance(old_resources, list) or not isinstance(new_resources, list):
        raise RuntimeError("NSC-089 resource list is malformed")
    if len(set(old_resources)) != len(old_resources) or len(set(new_resources)) != len(new_resources):
        raise RuntimeError("NSC-089 resources contain duplicates")
    if set(new_resources) != set(old_resources) | ADDED_RESOURCES:
        raise RuntimeError("NSC-089 resource additions differ from the exact repair")
    expected = dict(old)
    expected["contract_revision"] = 2
    expected["exclusive_resources"] = new_resources
    if expected != new:
        raise RuntimeError("NSC-089 contract changed beyond exact resources and revision")


def recover(service: IssueWorkflowService, old_sha: str, new_sha: str) -> dict:
    snapshot = service.find(TASK_ID)
    if (
        snapshot is None or not snapshot.valid or snapshot.issue_number != ISSUE_NUMBER
        or snapshot.state is None or snapshot.state.state is not WorkflowState.BLOCKED
        or snapshot.state.task_contract_sha256 != old_sha
        or snapshot.state.worker_id is not None or snapshot.state.lease_id is not None
        or snapshot.state.branch is not None or snapshot.state.head_commit is not None
        or snapshot.state.checkout_path is not None
        or snapshot.state.human_handoff_commit is not None
        or snapshot.state.human_result is not None
        or len(snapshot.events) != 2
        or snapshot.events[0].event_type is not WorkflowEventType.AGENT_LEASE_ACQUIRED
        or snapshot.events[1].event_type is not WorkflowEventType.BLOCKED
        or snapshot.events[0].actor_id != WORKER_ID
        or snapshot.events[1].actor_id != WORKER_ID
    ):
        raise RuntimeError("Issue #125 is not the exact stopped NSC-089 workflow")
    state = snapshot.state
    next_state, event = transition(
        state, event_type=WorkflowEventType.TASK_CONTRACT_MIGRATED,
        actor_type=WorkflowActor.AGENT, actor_id="nsc089-recovery",
        to_state=WorkflowState.AGENT_READY, to_phase=state.phase,
        details={
            "old_task_contract_sha256": old_sha,
            "new_task_contract_sha256": new_sha,
            "branch": None, "head_commit": None, "checkout_path": None,
            "human_handoff_commit": None, "human_result": None,
        }, now=utc_now(),
    )
    service.backend.add_comment(
        ISSUE_NUMBER,
        render_event_comment(event, "NSC-089's task contract now reserves its two exact new C# files. The stopped task has no candidate or active worker. Graph Sol may reconsider it after fresh graph and checkout checks."),
    )
    service.backend.update_issue(
        ISSUE_NUMBER,
        body=update_issue_body(snapshot.body, next_state, next_action="Graph Sol may reconsider NSC-089 after fresh graph, Issue, and checkout checks."),
        labels=labels_for_state(next_state.state, snapshot.labels),
        assignees=[service.assignee],
    )
    verified = service.verify_post_mutation_state(
        TASK_ID, next_state, transition_name="NSC-089 exact resource repair recovery"
    )
    return {"status": "agent_ready", **verified.to_dict()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.source.resolve()
    checkout = args.checkout.resolve()
    _git(root, "merge-base", "--is-ancestor", REPAIRED_COMMIT, "HEAD")
    if _git(root, "status", "--porcelain"):
        raise RuntimeError("Source is dirty")
    if _git(checkout, "rev-parse", "HEAD").decode().strip() != OLD_COMMIT:
        raise RuntimeError("NSC-089 checkout has a candidate or different base")
    if _git(checkout, "status", "--porcelain"):
        raise RuntimeError("NSC-089 checkout is dirty")
    old, old_sha = committed_contract(root, OLD_COMMIT)
    new, new_sha = committed_contract(root, REPAIRED_COMMIT)
    _current, current_sha = committed_contract(root, "HEAD")
    if current_sha != new_sha:
        raise RuntimeError("current Source does not retain the exact repaired contract")
    verify_contract_repair(old, new)
    service = IssueWorkflowService(
        backend=GhIssueBackend(source_root=root),
        task_loader=lambda task_id: {**new, "task_contract_sha256": new_sha},
        worker_id="nsc089-recovery",
    )
    if not args.apply:
        snapshot = service.find(TASK_ID)
        print(json.dumps({"old_sha": old_sha, "new_sha": new_sha, "issue_valid": snapshot.valid if snapshot else False, "issue_state": snapshot.state.state.value if snapshot and snapshot.state else None}))
        return
    print(json.dumps(recover(service, old_sha, new_sha)))


if __name__ == "__main__":
    main()
