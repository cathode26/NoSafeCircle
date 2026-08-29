#!/usr/bin/env python3
"""Inventory repository references affected by an approved-style history rewrite dry run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "1.0"
REPORT_NAME = "history-identity-impact.json"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# These two commits were accidentally created while this migration audit was being
# prepared. Together they add and then immediately remove one empty file. They are
# not dropped by the identity rewriter. This inventory only proves whether they are
# still a tree-neutral contiguous range so a later reviewed migration can decide
# whether to omit them.
DEFAULT_TRANSIENT_RANGES: tuple[dict[str, str], ...] = (
    {
        "label": "accidental empty-file create/remove pair",
        "first_commit": "0bd52993f4675fe9c2a0318064b4889f8ff29adc",
        "last_commit": "2ebcc99a8f9c2a80b63b7e23b5784ec89508c91c",
    },
)


class HistoryImpactError(RuntimeError):
    """Raised when impact inventory cannot be proven against the dry-run source."""


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


def _run(
    root: Path,
    args: Sequence[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        detail = result.stderr.strip()
        raise HistoryImpactError(
            f"command failed ({result.returncode}): {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def _git(root: Path, *args: str) -> str:
    return _run(root, ("git", *args)).stdout.strip()


def _validate_sha(value: Any, label: str) -> str:
    text = str(value or "")
    if not GIT_SHA_RE.fullmatch(text):
        raise HistoryImpactError(f"{label} is not a lowercase 40-character Git SHA")
    return text


def _load_dry_run(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HistoryImpactError(f"unable to read dry-run report: {exc}") from exc
    if not isinstance(report, dict) or report.get("report_type") != "history_identity_dry_run":
        raise HistoryImpactError("input is not a history identity dry-run report")
    if report.get("trees_preserved") is not True:
        raise HistoryImpactError("dry-run report did not prove tree preservation")
    return report


def _classify_path(path: str) -> str:
    if path.startswith("Pipeline/TaskGraph/evidence/"):
        return "taskgraph_evidence"
    if path.startswith("Pipeline/TaskGraph/migrations/"):
        return "taskgraph_migration"
    if path.startswith("Pipeline/TaskReviewAgent/"):
        return "task_review_agent"
    if path.startswith(".github/workflows/"):
        return "github_workflow"
    return "repository_file"


def _grep_hits(root: Path, source_main: str, needle: str) -> list[dict[str, Any]]:
    result = _run(
        root,
        ("git", "grep", "-I", "-n", "-F", needle, source_main, "--"),
        check=False,
    )
    if result.returncode not in (0, 1):
        raise HistoryImpactError(
            f"git grep failed ({result.returncode}) for {needle}: {result.stderr.strip()}"
        )
    hits: list[dict[str, Any]] = []
    prefix = f"{source_main}:"
    for raw in result.stdout.splitlines():
        line = raw
        if not line.startswith(prefix):
            raise HistoryImpactError(f"unexpected git grep output: {line!r}")
        remainder = line[len(prefix):]
        try:
            path, line_number, text = remainder.split(":", 2)
            parsed_line = int(line_number)
        except (ValueError, TypeError) as exc:
            raise HistoryImpactError(f"unable to parse git grep output: {line!r}") from exc
        hits.append(
            {
                "path": path,
                "line": parsed_line,
                "classification": _classify_path(path),
                "text": text[:500],
            }
        )
    return hits


def _tracked_paths(root: Path, source_main: str) -> list[str]:
    output = _git(root, "ls-tree", "-r", "--name-only", source_main)
    return [line for line in output.splitlines() if line]


def _reference_inventory(
    root: Path,
    source_main: str,
    commit_map: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    paths = _tracked_paths(root, source_main)
    rows: list[dict[str, Any]] = []
    for raw in commit_map:
        old_commit = _validate_sha(raw.get("old_commit"), "commit_map.old_commit")
        new_commit = _validate_sha(raw.get("new_commit"), "commit_map.new_commit")
        prefix12 = old_commit[:12]
        exact_hits = _grep_hits(root, source_main, old_commit)
        prefix_hits = _grep_hits(root, source_main, prefix12)
        exact_keys = {(item["path"], item["line"]) for item in exact_hits}
        short_only = [
            item for item in prefix_hits if (item["path"], item["line"]) not in exact_keys
        ]
        filename_hits = [path for path in paths if prefix12 in path or old_commit in path]
        if not exact_hits and not short_only and not filename_hits:
            continue
        rows.append(
            {
                "old_commit": old_commit,
                "new_commit": new_commit,
                "prefix12": prefix12,
                "exact_content_hits": exact_hits,
                "prefix_content_hits": short_only,
                "filename_hits": [
                    {"path": path, "classification": _classify_path(path)}
                    for path in filename_hits
                ],
            }
        )
    return sorted(rows, key=lambda item: item["old_commit"])


def _parents(root: Path, commit: str) -> list[str]:
    line = _git(root, "rev-list", "--parents", "-n", "1", commit)
    parts = line.split()
    if not parts or parts[0] != commit:
        raise HistoryImpactError(f"unable to read parents for {commit}")
    return [_validate_sha(item, f"{commit} parent") for item in parts[1:]]


def _tree(root: Path, commit: str) -> str:
    return _validate_sha(_git(root, "rev-parse", f"{commit}^{{tree}}"), f"{commit} tree")


def _transient_range(
    root: Path,
    reachable: set[str],
    raw: Mapping[str, str],
) -> dict[str, Any]:
    label = str(raw.get("label") or "transient range")
    first = _validate_sha(raw.get("first_commit"), f"{label}.first_commit")
    last = _validate_sha(raw.get("last_commit"), f"{label}.last_commit")
    result: dict[str, Any] = {
        "label": label,
        "first_commit": first,
        "last_commit": last,
        "reachable": first in reachable and last in reachable,
        "contiguous_first_parent_chain": False,
        "net_tree_preserved": False,
        "prunable_candidate": False,
        "commits": [],
        "base_parent": None,
        "base_tree": None,
        "last_tree": None,
    }
    if not result["reachable"]:
        return result

    chain_reversed: list[str] = []
    cursor = last
    seen: set[str] = set()
    while True:
        if cursor in seen:
            return result
        seen.add(cursor)
        chain_reversed.append(cursor)
        if cursor == first:
            break
        parents = _parents(root, cursor)
        if len(parents) != 1:
            return result
        cursor = parents[0]
    chain = list(reversed(chain_reversed))
    first_parents = _parents(root, first)
    if len(first_parents) != 1:
        return result
    base_parent = first_parents[0]
    base_tree = _tree(root, base_parent)
    last_tree = _tree(root, last)
    result.update(
        contiguous_first_parent_chain=True,
        commits=chain,
        base_parent=base_parent,
        base_tree=base_tree,
        last_tree=last_tree,
        net_tree_preserved=base_tree == last_tree,
        prunable_candidate=base_tree == last_tree,
    )
    return result


def build_impact_report(
    *,
    source: Path,
    dry_run_report: Path,
    transient_ranges: Iterable[Mapping[str, str]] = DEFAULT_TRANSIENT_RANGES,
) -> dict[str, Any]:
    source = source.resolve()
    if not (source / ".git").exists():
        raise HistoryImpactError(f"source is not a Git worktree: {source}")
    dry = _load_dry_run(dry_run_report)
    source_main = _validate_sha(dry.get("source_main"), "dry_run.source_main")
    source_main_tree = _validate_sha(
        dry.get("source_main_tree"), "dry_run.source_main_tree"
    )
    if _tree(source, source_main) != source_main_tree:
        raise HistoryImpactError("source repository does not contain the dry-run main tree")

    commit_map = dry.get("commit_map")
    if not isinstance(commit_map, list):
        raise HistoryImpactError("dry-run commit_map must be a list")
    references = _reference_inventory(source, source_main, commit_map)
    reachable = set(_git(source, "rev-list", source_main).splitlines())
    transient = [
        _transient_range(source, reachable, item) for item in transient_ranges
    ]

    affected_paths = sorted(
        {
            hit["path"]
            for row in references
            for group in (row["exact_content_hits"], row["prefix_content_hits"], row["filename_hits"])
            for hit in group
        }
    )
    taskgraph_paths = [
        path for path in affected_paths if path.startswith("Pipeline/TaskGraph/evidence/")
    ]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "history_identity_impact",
        "source_main": source_main,
        "source_main_tree": source_main_tree,
        "dry_run_report_sha256": dry.get("report_sha256"),
        "translated_commit_count": len(commit_map),
        "referenced_translated_commit_count": len(references),
        "affected_tracked_path_count": len(affected_paths),
        "affected_tracked_paths": affected_paths,
        "affected_taskgraph_evidence_paths": taskgraph_paths,
        "tracked_references": references,
        "transient_ranges": transient,
        "external_github_audit_required": True,
        "external_github_surfaces": [
            "managed Issue bodies",
            "append-only Issue event comments",
            "pull request bodies/comments/reviews",
            "live remote branch refs",
        ],
    }
    report["report_sha256"] = semantic_sha256(report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory tracked references affected by a history identity dry run."
    )
    parser.add_argument("--source", default=".")
    parser.add_argument("--dry-run-report", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_impact_report(
            source=Path(args.source),
            dry_run_report=Path(args.dry_run_report),
        )
        output = Path(args.output)
        if output.exists():
            raise HistoryImpactError(f"output path already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": "impact_inventory_complete",
                    "source_main": report["source_main"],
                    "translated_commit_count": report["translated_commit_count"],
                    "referenced_translated_commit_count": report[
                        "referenced_translated_commit_count"
                    ],
                    "affected_tracked_path_count": report[
                        "affected_tracked_path_count"
                    ],
                    "affected_taskgraph_evidence_paths": report[
                        "affected_taskgraph_evidence_paths"
                    ],
                    "transient_ranges": report["transient_ranges"],
                    "output": str(output),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except HistoryImpactError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
