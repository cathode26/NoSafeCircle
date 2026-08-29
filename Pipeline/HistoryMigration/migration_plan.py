#!/usr/bin/env python3
"""Build a fail-closed, non-destructive execution plan from a history dry run.

The planner never updates a ref, closes a PR, or edits an Issue. It turns the exact
remote-ref map from ``history_identity.py`` plus a reviewed branch/GitHub policy
into an explicit preflight plan and rollback inventory. Any newly affected branch
that is missing from policy blocks the destructive phase.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0"
REPORT_TYPE = "history_identity_migration_plan"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_BRANCH_ACTIONS = {
    "rewrite",
    "delete_after_migration",
    "merge_preparation_then_delete",
}
REMOTE_AUDIT_PREFIX = "refs/heads/remote-audit/"


class MigrationPlanError(RuntimeError):
    """Raised when the reviewed ref policy does not cover the exact dry-run state."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def semantic_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _sha(value: Any, label: str) -> str:
    text = str(value or "")
    if not GIT_SHA_RE.fullmatch(text):
        raise MigrationPlanError(f"{label} is not a lowercase 40-character Git SHA")
    return text


def _object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationPlanError(f"unable to read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise MigrationPlanError(f"{label} must contain a JSON object")
    return value


def _load_dry_run(path: Path) -> dict[str, Any]:
    report = _object(path, "dry-run report")
    if report.get("report_type") != "history_identity_dry_run":
        raise MigrationPlanError("input is not a history identity dry-run report")
    if report.get("trees_preserved") is not True:
        raise MigrationPlanError("dry-run report did not prove tree preservation")
    _sha(report.get("source_main"), "dry_run.source_main")
    _sha(report.get("target_main"), "dry_run.target_main")
    source_tree = _sha(report.get("source_main_tree"), "dry_run.source_main_tree")
    target_tree = _sha(report.get("target_main_tree"), "dry_run.target_main_tree")
    if source_tree != target_tree:
        raise MigrationPlanError("dry-run source and target main trees differ")
    return report


def _load_policy(path: Path) -> dict[str, Any]:
    policy = _object(path, "ref policy")
    expected = {"schema_version", "repository", "branch_actions", "github_actions"}
    if set(policy) != expected:
        raise MigrationPlanError(
            "ref policy keys differ from schema; "
            f"missing={sorted(expected-set(policy))}, extras={sorted(set(policy)-expected)}"
        )
    if policy.get("schema_version") != SCHEMA_VERSION:
        raise MigrationPlanError("unsupported ref policy schema_version")
    if not isinstance(policy.get("repository"), str) or not policy["repository"].strip():
        raise MigrationPlanError("ref policy repository must be non-empty")
    if not isinstance(policy.get("branch_actions"), Mapping):
        raise MigrationPlanError("ref policy branch_actions must be an object")
    if not isinstance(policy.get("github_actions"), Mapping):
        raise MigrationPlanError("ref policy github_actions must be an object")
    return policy


def _affected_remote_branches(dry: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    ref_map = dry.get("ref_map")
    if not isinstance(ref_map, list):
        raise MigrationPlanError("dry-run ref_map must be a list")
    affected: dict[str, dict[str, str]] = {}
    for index, raw in enumerate(ref_map):
        if not isinstance(raw, Mapping):
            raise MigrationPlanError(f"ref_map[{index}] must be an object")
        if raw.get("changed") is not True:
            continue
        ref = str(raw.get("ref") or "")
        if not ref.startswith(REMOTE_AUDIT_PREFIX):
            continue
        branch = ref[len(REMOTE_AUDIT_PREFIX):]
        if not branch:
            raise MigrationPlanError(f"ref_map[{index}] has empty remote-audit branch")
        old_commit = _sha(raw.get("old_commit"), f"ref_map[{index}].old_commit")
        new_commit = _sha(raw.get("new_commit"), f"ref_map[{index}].new_commit")
        if old_commit == new_commit:
            raise MigrationPlanError(f"changed ref {branch} did not change commit")
        previous = affected.get(branch)
        row = {"old_commit": old_commit, "new_commit": new_commit}
        if previous is not None and previous != row:
            raise MigrationPlanError(f"conflicting remote-audit rows for {branch}")
        affected[branch] = row
    if "main" not in affected:
        raise MigrationPlanError("remote branch audit did not include affected main")
    return affected


def _validate_policy_entry(branch: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise MigrationPlanError(f"branch policy for {branch} must be an object")
    allowed_keys = {"action", "reason", "pull_request"}
    extras = set(raw) - allowed_keys
    missing = {"action", "reason"} - set(raw)
    if extras or missing:
        raise MigrationPlanError(
            f"branch policy for {branch} has invalid keys; "
            f"missing={sorted(missing)}, extras={sorted(extras)}"
        )
    action = raw.get("action")
    if action not in ALLOWED_BRANCH_ACTIONS:
        raise MigrationPlanError(
            f"branch policy for {branch} has unsupported action {action!r}"
        )
    reason = raw.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise MigrationPlanError(f"branch policy for {branch} requires a reason")
    pull_request = raw.get("pull_request")
    if pull_request is not None and (
        isinstance(pull_request, bool)
        or not isinstance(pull_request, int)
        or pull_request < 1
    ):
        raise MigrationPlanError(f"branch policy for {branch} has invalid pull_request")
    return {
        "action": action,
        "reason": reason.strip(),
        "pull_request": pull_request,
    }


def _github_actions(policy: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw = policy.get("github_actions")
    if not isinstance(raw, Mapping):
        raise MigrationPlanError("github_actions must be an object")
    expected = {"close_before_rewrite", "annotate_after_rewrite"}
    if set(raw) != expected:
        raise MigrationPlanError(
            "github_actions keys differ from schema; "
            f"missing={sorted(expected-set(raw))}, extras={sorted(set(raw)-expected)}"
        )
    result: dict[str, list[dict[str, Any]]] = {}
    for key in sorted(expected):
        rows = raw.get(key)
        if not isinstance(rows, list):
            raise MigrationPlanError(f"github_actions.{key} must be a list")
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(rows):
            if not isinstance(item, Mapping):
                raise MigrationPlanError(f"github_actions.{key}[{index}] must be an object")
            required = {"type", "number", "action", "reason"}
            if set(item) != required:
                raise MigrationPlanError(
                    f"github_actions.{key}[{index}] must contain exactly {sorted(required)}"
                )
            if item.get("type") not in {"issue", "pull_request"}:
                raise MigrationPlanError(f"github_actions.{key}[{index}] has invalid type")
            number = item.get("number")
            if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                raise MigrationPlanError(f"github_actions.{key}[{index}] has invalid number")
            for field in ("action", "reason"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    raise MigrationPlanError(
                        f"github_actions.{key}[{index}].{field} must be non-empty"
                    )
            normalized.append(dict(item))
        result[key] = normalized
    return result


def build_plan(*, dry_run_report: Path, policy_path: Path) -> dict[str, Any]:
    dry = _load_dry_run(dry_run_report)
    policy = _load_policy(policy_path)
    affected = _affected_remote_branches(dry)
    raw_actions = policy["branch_actions"]

    unclassified = sorted(set(affected) - set(raw_actions))
    stale_policy = sorted(set(raw_actions) - set(affected))
    rows: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for branch in sorted(affected):
        raw_policy = raw_actions.get(branch)
        if raw_policy is None:
            blockers.append(
                {
                    "type": "unclassified_branch",
                    "branch": branch,
                    "reason": "Affected remote branch has no reviewed migration action.",
                }
            )
            continue
        entry = _validate_policy_entry(branch, raw_policy)
        row = {
            "branch": branch,
            "old_commit": affected[branch]["old_commit"],
            "new_commit": affected[branch]["new_commit"],
            **entry,
        }
        rows.append(row)
        if entry["action"] == "merge_preparation_then_delete":
            blockers.append(
                {
                    "type": "preparation_branch_not_integrated",
                    "branch": branch,
                    "pull_request": entry["pull_request"],
                    "reason": entry["reason"],
                }
            )

    main_rows = [row for row in rows if row["branch"] == "main"]
    if len(main_rows) != 1 or main_rows[0]["action"] != "rewrite":
        raise MigrationPlanError("main must have exactly one reviewed rewrite action")
    source_main = _sha(dry.get("source_main"), "dry_run.source_main")
    target_main = _sha(dry.get("target_main"), "dry_run.target_main")
    if main_rows[0]["old_commit"] != source_main or main_rows[0]["new_commit"] != target_main:
        raise MigrationPlanError("remote-audit main mapping disagrees with dry-run main mapping")

    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_type": REPORT_TYPE,
        "repository": policy["repository"],
        "source_main": source_main,
        "target_main": target_main,
        "main_tree": _sha(dry.get("source_main_tree"), "dry_run.source_main_tree"),
        "rewrite_report_sha256": dry.get("report_sha256"),
        "affected_remote_branch_count": len(affected),
        "branch_actions": rows,
        "unclassified_affected_branches": unclassified,
        "policy_entries_not_currently_affected": stale_policy,
        "pre_rewrite_blockers": blockers,
        "github_actions": _github_actions(policy),
        "rollback_refs": [
            {"branch": row["branch"], "commit": row["old_commit"]}
            for row in rows
        ],
        "destructive_operations": {
            "force_update": [
                {
                    "branch": row["branch"],
                    "old_commit": row["old_commit"],
                    "new_commit": row["new_commit"],
                }
                for row in rows
                if row["action"] == "rewrite"
            ],
            "delete_after_migration": [
                {"branch": row["branch"], "old_commit": row["old_commit"]}
                for row in rows
                if row["action"] == "delete_after_migration"
            ],
        },
        "ready_for_destructive_phase": not blockers and not unclassified,
    }
    plan["report_sha256"] = semantic_sha256(plan)
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a non-destructive history migration execution and rollback plan."
    )
    parser.add_argument("--dry-run-report", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = Path(args.output)
        if output.exists():
            raise MigrationPlanError(f"output path already exists: {output}")
        plan = build_plan(
            dry_run_report=Path(args.dry_run_report),
            policy_path=Path(args.policy),
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    except MigrationPlanError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
