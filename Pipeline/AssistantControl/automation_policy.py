"""Narrow policy shared by the AssistantControl graph runner and review gate."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl.inspect_project import git
from Pipeline.TaskReviewAgent.authoritative_candidate_validation import (
    authoritative_validation_fact,
)
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task


GAUNTLET_ID = "synthetic-architect-gauntlet-v1"
REPLAY_GAUNTLET_ID = "assistant-control-local-replay-v1"
GAUNTLET_IDS = frozenset({GAUNTLET_ID, REPLAY_GAUNTLET_ID})
HUMAN_ONLY_TASKS = frozenset({"NSC-042"})


def is_synthetic_gauntlet(source: Path, task_id: str, commit: str) -> bool:
    """Return true only for the disposable gauntlet or one of its descendants."""
    if task_id in HUMAN_ONLY_TASKS:
        return False
    seen: set[str] = set()
    current = task_id
    while current and current not in seen:
        seen.add(current)
        task = load_committed_task(source, current, commit=commit)
        provenance = task.get("provenance") or {}
        if provenance.get("origin") == "human_approved_synthetic_gauntlet":
            return True
        if provenance.get("gauntlet_id") in GAUNTLET_IDS and current not in HUMAN_ONLY_TASKS:
            return True
        if provenance.get("origin") != "progressive_decomposition":
            return False
        parent = task.get("parent")
        current = parent if isinstance(parent, str) else ""
    return False


def authenticate_passing_validations(
    records_root: Path, record: Mapping[str, Any], tested_commit: str,
) -> tuple[dict[str, Any], ...]:
    """Re-hash every retained validation fact bound to an exact candidate."""
    candidate = record.get("candidate") or {}
    facts = candidate.get("authoritative_validations")
    if not isinstance(facts, list) or not facts:
        raise ValueError("Automated Gauntlet approval requires authoritative validation")
    checkout = Path(str(record.get("checkout", ""))).resolve()
    tree = candidate.get("tree")
    if not isinstance(tree, str) or not tree:
        raise ValueError("Candidate tree is missing")
    verified: list[dict[str, Any]] = []
    for fact in facts:
        if not isinstance(fact, Mapping):
            raise ValueError("Candidate validation fact is invalid")
        relative = fact.get("manifest_relative_path")
        if not isinstance(relative, str) or not relative:
            raise ValueError("Candidate validation manifest path is missing")
        manifest = (records_root / relative).resolve()
        if not manifest.is_relative_to(records_root.resolve()):
            raise ValueError("Candidate validation manifest escapes AssistantControl records")
        actual = authoritative_validation_fact(
            checkout=checkout,
            state_root=records_root,
            manifest_path=manifest,
            commit=tested_commit,
            tree=tree,
            platform=str(fact.get("test_platform", "")),
            test_filter=str(fact.get("test_filter", "")),
            policy_sha256=str(fact.get("policy_sha256", "")),
        )
        if actual != dict(fact):
            raise ValueError("Candidate validation fact changed after it was recorded")
        total, passed = actual.get("total"), actual.get("passed")
        if (type(total) is not int or type(passed) is not int
                or total < 1 or passed != total):
            raise ValueError("Candidate validation did not pass every focused test")
        verified.append(actual)
    return tuple(verified)


def committed_json(source: Path, commit: str, path: str) -> dict[str, Any] | None:
    try:
        value = json.loads(git(source, "show", f"{commit}:{path}").decode("utf-8-sig"))
    except (RuntimeError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


__all__ = [
    "GAUNTLET_ID", "GAUNTLET_IDS", "HUMAN_ONLY_TASKS", "REPLAY_GAUNTLET_ID",
    "authenticate_passing_validations",
    "committed_json", "is_synthetic_gauntlet",
]
