"""Committed TaskGraph evidence for assistant task selection."""
from __future__ import annotations

import sys
import json
import re
from pathlib import Path

from Pipeline.AssistantControl.inspect_project import git
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task


def approved_integration(source: Path, records: Path, task_id: str, head: str) -> dict | None:
    """Prove local dependency acceptance from an approved, integrated commit.

    This is not production delivery evidence or a Unity conformance claim.
    A missing, stale or malformed record never satisfies a dependency.
    """
    from Pipeline.TaskReviewAgent.contracts import validate_task_id
    validate_task_id(task_id)
    try:
        record = json.loads((records / f"{task_id}.json").read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            return None
        approval = record.get("approval") or {}
        candidate = record.get("candidate") or {}
        integration = record.get("integration") or {}
        if not all(isinstance(item, dict) for item in (approval, candidate, integration)):
            return None
        commit = candidate.get("commit")
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            return None
        if (record.get("status") != "integrated" or record.get("task_id") != task_id
                or record.get("source") != str(source.resolve())
                or approval.get("decision") != "approve" or not commit
                or approval.get("commit") != commit or integration.get("candidate") != commit
                or not integration.get("completed_at")):
            return None
        git(source, "merge-base", "--is-ancestor", commit, head)
        if git(source, "rev-parse", f"{commit}^{{tree}}").decode().strip() != candidate.get("tree"):
            return None
        # Both the accepted candidate and today's contract must match. Changed
        # requirements need a new acceptance rather than a stale green overlay.
        for revision in (commit, head):
            load_committed_task(source, task_id, commit=revision,
                                expected_sha256=record.get("task_contract_sha256"))
        if not record.get("task_contract_sha256"):
            return None
        return {"commit": commit, "authority": "assistant_approved_local_integration"}
    except (OSError, ValueError, RuntimeError, TypeError):
        return None


def conformance_context(source: Path):
    """Build one committed-HEAD conformance view of Source.

    Construction validates the repository's history identity and costs several
    git processes; the view memoizes every evaluation at that HEAD, so a caller
    evaluating many tasks at one HEAD should build it once and pass it to
    :func:`inspect_dependencies`.
    """
    # TaskGraph currently uses sibling absolute imports. Reuse its evaluator,
    # rather than interpreting delivery-record filenames or Issue labels here.
    taskgraph = str(Path(__file__).resolve().parents[1] / "TaskGraph")
    if taskgraph not in sys.path:
        sys.path.insert(0, taskgraph)
    from current_conformance import ConformanceEvaluationContext

    return ConformanceEvaluationContext(source)


def inspect_dependencies(
    source: Path, task_id: str, checkout_root: Path | None = None, *, context=None,
) -> dict:
    if context is None:
        context = conformance_context(source)
    elif Path(getattr(context, "root", "")) != Path(source).resolve():
        raise ValueError("conformance context belongs to another Source")
    contract = load_committed_task(source, task_id, commit=context.head)
    dependencies = [context.evaluate(dependency).to_dict()
                    for dependency in contract.get("depends_on", [])]
    own = context.evaluate(task_id).to_dict()
    # Assistant workflow requires integrated dependency work. Legacy evidence
    # can establish this; a human-approved assistant integration receipt will
    # be added at the integration layer. A review-ready patch alone cannot.
    # `needs_testing` can be produced by files simply appearing in Source. It
    # does not prove this AssistantControl run validated, approved and integrated
    # the exact candidate. Current local work therefore needs its receipt.
    satisfied = {"conformant"}
    accepted = {}
    if checkout_root is not None:
        from Pipeline.AssistantControl.checkouts import Checkouts
        manager = Checkouts(source, checkout_root)
        for item in dependencies:
            proof = approved_integration(manager.source, manager.records, item["task_id"], context.head)
            if proof:
                accepted[item["task_id"]] = proof
    blocked = [item["task_id"] for item in dependencies
               if item["state"] not in satisfied and item["task_id"] not in accepted]
    stable = git(source, "rev-parse", "HEAD").decode().strip() == context.head
    return {
        "task_id": task_id, "source_commit": context.head,
        "contract_sha256": contract["task_contract_sha256"],
        "task_state": own, "dependencies": dependencies,
        "blocked_dependencies": blocked,
        "approved_local_dependencies": accepted,
        "source_unchanged_during_read": stable,
        "dependencies_satisfied": stable and not blocked,
        "execution_authorized": False,
        "remaining_checks": ["worker capacity", "active resource ownership", "execution scope"],
    }
