#!/usr/bin/env python3
"""Regression tests for non-destructive history migration planning."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.HistoryMigration.migration_plan import build_plan  # noqa: E402


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dry_run() -> dict:
    old_main = "1" * 40
    new_main = "2" * 40
    tree = "3" * 40
    old_fix = "4" * 40
    new_fix = "5" * 40
    old_prep = "6" * 40
    new_prep = "7" * 40
    return {
        "report_type": "history_identity_dry_run",
        "trees_preserved": True,
        "source_main": old_main,
        "target_main": new_main,
        "source_main_tree": tree,
        "target_main_tree": tree,
        "report_sha256": "a" * 64,
        "ref_map": [
            {
                "ref": "refs/heads/main",
                "old_commit": old_main,
                "new_commit": new_main,
                "changed": True,
            },
            {
                "ref": "refs/heads/remote-audit/main",
                "old_commit": old_main,
                "new_commit": new_main,
                "changed": True,
            },
            {
                "ref": "refs/heads/remote-audit/fix/merged",
                "old_commit": old_fix,
                "new_commit": new_fix,
                "changed": True,
            },
            {
                "ref": "refs/heads/remote-audit/pipeline/preparation",
                "old_commit": old_prep,
                "new_commit": new_prep,
                "changed": True,
            },
        ],
    }


def policy(*, include_fix: bool = True) -> dict:
    actions = {
        "main": {"action": "rewrite", "reason": "canonical"},
        "pipeline/preparation": {
            "action": "merge_preparation_then_delete",
            "pull_request": 99,
            "reason": "merge first",
        },
    }
    if include_fix:
        actions["fix/merged"] = {
            "action": "delete_after_migration",
            "pull_request": 98,
            "reason": "merged",
        }
    return {
        "schema_version": "1.0",
        "repository": "example/repo",
        "branch_actions": actions,
        "github_actions": {
            "close_before_rewrite": [
                {
                    "type": "pull_request",
                    "number": 97,
                    "action": "close_superseded",
                    "reason": "stale",
                }
            ],
            "annotate_after_rewrite": [
                {
                    "type": "issue",
                    "number": 96,
                    "action": "append_repository_history_migrated_event",
                    "reason": "live identity",
                }
            ],
        },
    }


def test_plan_is_explicit_and_blocks_on_unmerged_preparation_branch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dry_path = root / "dry.json"
        policy_path = root / "policy.json"
        write_json(dry_path, dry_run())
        write_json(policy_path, policy())
        plan = build_plan(dry_run_report=dry_path, policy_path=policy_path)

        require(plan["affected_remote_branch_count"] == 3, "affected branch count is wrong")
        require(plan["unclassified_affected_branches"] == [], "fully covered plan is unclassified")
        require(not plan["ready_for_destructive_phase"], "preparation branch did not block")
        require(
            plan["pre_rewrite_blockers"][0]["type"] == "preparation_branch_not_integrated",
            "wrong preparation blocker",
        )
        require(
            plan["destructive_operations"]["force_update"] == [
                {"branch": "main", "old_commit": "1" * 40, "new_commit": "2" * 40}
            ],
            "main rewrite operation is wrong",
        )
        require(
            plan["destructive_operations"]["delete_after_migration"] == [
                {"branch": "fix/merged", "old_commit": "4" * 40}
            ],
            "merged branch deletion plan is wrong",
        )


def test_new_affected_branch_fails_closed_until_policy_is_updated() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dry_path = root / "dry.json"
        policy_path = root / "policy.json"
        write_json(dry_path, dry_run())
        write_json(policy_path, policy(include_fix=False))
        plan = build_plan(dry_run_report=dry_path, policy_path=policy_path)
        require(
            plan["unclassified_affected_branches"] == ["fix/merged"],
            "missing branch was not exposed",
        )
        require(not plan["ready_for_destructive_phase"], "unclassified branch did not block")
        require(
            any(item["type"] == "unclassified_branch" for item in plan["pre_rewrite_blockers"]),
            "unclassified branch blocker missing",
        )


def test_plan_becomes_ready_only_after_preparation_policy_is_resolved() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dry_path = root / "dry.json"
        policy_path = root / "policy.json"
        write_json(dry_path, dry_run())
        value = policy()
        value["branch_actions"]["pipeline/preparation"] = {
            "action": "delete_after_migration",
            "pull_request": 99,
            "reason": "preparation PR is merged and canonical on frozen main",
        }
        write_json(policy_path, value)
        plan = build_plan(dry_run_report=dry_path, policy_path=policy_path)
        require(plan["pre_rewrite_blockers"] == [], "resolved policy retained blockers")
        require(plan["ready_for_destructive_phase"], "resolved plan did not become ready")


def main() -> int:
    tests = (
        test_plan_is_explicit_and_blocks_on_unmerged_preparation_branch,
        test_new_affected_branch_fails_closed_until_policy_is_updated,
        test_plan_becomes_ready_only_after_preparation_policy_is_resolved,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"History migration plan tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
