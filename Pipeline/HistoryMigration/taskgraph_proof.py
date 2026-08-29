#!/usr/bin/env python3
"""Prove TaskGraph conformance on the disposable rewritten history using Git replace refs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION = "1.0"
REPORT_NAME = "history-identity-taskgraph-proof.json"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class TaskGraphProofError(RuntimeError):
    """Raised when the rewritten-history TaskGraph proof cannot be established."""


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
    cwd: Path,
    args: Sequence[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        raise TaskGraphProofError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def _git(cwd: Path, *args: str) -> str:
    return _run(cwd, ("git", *args)).stdout.strip()


def _sha(value: Any, label: str) -> str:
    text = str(value or "")
    if not GIT_SHA_RE.fullmatch(text):
        raise TaskGraphProofError(f"{label} is not a lowercase 40-character Git SHA")
    return text


def _load_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskGraphProofError(f"unable to read dry-run report: {exc}") from exc
    if not isinstance(report, dict) or report.get("report_type") != "history_identity_dry_run":
        raise TaskGraphProofError("input is not a history identity dry-run report")
    if report.get("trees_preserved") is not True:
        raise TaskGraphProofError("dry-run report did not prove tree preservation")
    return report


def _install_replace_refs(worktree: Path, commit_map: list[dict[str, Any]]) -> int:
    installed = 0
    for row in commit_map:
        old_commit = _sha(row.get("old_commit"), "commit_map.old_commit")
        new_commit = _sha(row.get("new_commit"), "commit_map.new_commit")
        expected_tree = _sha(row.get("tree"), "commit_map.tree")
        if _git(worktree, "rev-parse", f"{new_commit}^{{tree}}") != expected_tree:
            raise TaskGraphProofError(
                f"translated commit tree mismatch before replace install: {old_commit} -> {new_commit}"
            )
        _run(worktree, ("git", "replace", old_commit, new_commit))
        installed += 1
    return installed


def prove_taskgraph(
    *,
    mirror: Path,
    dry_run_report: Path,
    worktree: Path,
    task_id: str,
) -> dict[str, Any]:
    mirror = mirror.resolve()
    report = _load_report(dry_run_report)
    if worktree.exists():
        raise TaskGraphProofError(f"proof worktree already exists: {worktree}")
    if not (mirror / "HEAD").exists():
        raise TaskGraphProofError(f"mirror is not a bare Git repository: {mirror}")

    target_main = _sha(report.get("target_main"), "dry_run.target_main")
    target_tree = _sha(report.get("target_main_tree"), "dry_run.target_main_tree")
    mirror_main = _sha(_git(mirror, "rev-parse", "refs/heads/main"), "mirror main")
    if mirror_main != target_main:
        raise TaskGraphProofError(
            f"mirror main does not match dry-run target: {mirror_main} != {target_main}"
        )
    if _git(mirror, "rev-parse", f"{mirror_main}^{{tree}}") != target_tree:
        raise TaskGraphProofError("mirror main tree does not match dry-run target tree")

    worktree.parent.mkdir(parents=True, exist_ok=True)
    _run(
        mirror,
        ("git", "worktree", "add", "--detach", str(worktree), target_main),
    )
    commit_map = report.get("commit_map")
    if not isinstance(commit_map, list):
        raise TaskGraphProofError("dry-run commit_map must be a list")
    replace_count = _install_replace_refs(worktree, commit_map)

    script = r'''
import json
import sys
from pathlib import Path
root = Path.cwd()
sys.path.insert(0, str(root / "Pipeline" / "TaskGraph"))
from current_conformance import evaluate_current_conformance
result = evaluate_current_conformance(root=root, selector=sys.argv[1])
print(json.dumps(result.to_dict(), sort_keys=True))
'''
    result = _run(worktree, (sys.executable, "-c", script, task_id))
    try:
        conformance = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TaskGraphProofError(
            f"TaskGraph proof returned invalid JSON: {result.stdout!r}"
        ) from exc
    if not isinstance(conformance, dict):
        raise TaskGraphProofError("TaskGraph proof result must be an object")
    if conformance.get("state") != "conformant":
        raise TaskGraphProofError(
            f"rewritten history did not preserve {task_id} conformance: {conformance}"
        )
    if conformance.get("head_commit") != target_main:
        raise TaskGraphProofError("TaskGraph proof did not run on rewritten main")

    proof: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "history_identity_taskgraph_proof",
        "task_id": task_id,
        "source_main": report.get("source_main"),
        "target_main": target_main,
        "target_main_tree": target_tree,
        "replace_ref_count": replace_count,
        "translation_mode": "temporary_git_replace_refs",
        "source_evidence_edited": False,
        "conformance": conformance,
    }
    proof["report_sha256"] = semantic_sha256(proof)
    return proof


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prove TaskGraph conformance on a disposable rewritten-history mirror."
    )
    parser.add_argument("--mirror", required=True)
    parser.add_argument("--dry-run-report", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = Path(args.output)
        if output.exists():
            raise TaskGraphProofError(f"output path already exists: {output}")
        proof = prove_taskgraph(
            mirror=Path(args.mirror),
            dry_run_report=Path(args.dry_run_report),
            worktree=Path(args.worktree),
            task_id=args.task_id,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(proof, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(proof, indent=2, sort_keys=True))
        return 0
    except TaskGraphProofError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
