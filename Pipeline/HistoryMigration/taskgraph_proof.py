#!/usr/bin/env python3
"""Prove TaskGraph conformance on a disposable rewritten history.

The proof models the intended production sequence without touching the real
repository: rewrite the Git identities in an isolated mirror, commit a strict
old-SHA -> new-SHA migration manifest on top of rewritten main, then run the
migration-aware TaskGraph evaluator from the candidate tooling against that
rewritten worktree. Existing evidence bytes are not edited.
"""

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


def _is_ancestor(root: Path, older: str, newer: str) -> bool:
    result = _run(
        root,
        ("git", "merge-base", "--is-ancestor", older, newer),
        check=False,
    )
    return result.returncode == 0


def _canonical_commit_map(
    worktree: Path,
    report: dict[str, Any],
    target_main: str,
) -> list[dict[str, str]]:
    raw_map = report.get("commit_map")
    if not isinstance(raw_map, list):
        raise TaskGraphProofError("dry-run commit_map must be a list")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raw_map:
        if not isinstance(raw, dict):
            raise TaskGraphProofError("dry-run commit_map entry must be an object")
        old_commit = _sha(raw.get("old_commit"), "commit_map.old_commit")
        new_commit = _sha(raw.get("new_commit"), "commit_map.new_commit")
        tree = _sha(raw.get("tree"), "commit_map.tree")
        if not _is_ancestor(worktree, new_commit, target_main):
            continue
        if old_commit in seen:
            raise TaskGraphProofError(f"duplicate canonical translation for {old_commit}")
        seen.add(old_commit)
        if _git(worktree, "rev-parse", f"{new_commit}^{{tree}}") != tree:
            raise TaskGraphProofError(
                f"translated canonical commit tree mismatch: {old_commit} -> {new_commit}"
            )
        rows.append(
            {
                "old_commit": old_commit,
                "new_commit": new_commit,
                "tree": tree,
            }
        )
    if not rows:
        raise TaskGraphProofError("dry run produced no canonical rewritten commits")
    return sorted(rows, key=lambda item: item["old_commit"])


def _commit_proof_manifest(
    *,
    worktree: Path,
    report: dict[str, Any],
    target_main: str,
    target_tree: str,
) -> tuple[str, str, int]:
    source_main = _sha(report.get("source_main"), "dry_run.source_main")
    source_tree = _sha(report.get("source_main_tree"), "dry_run.source_main_tree")
    report_hash = str(report.get("report_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", report_hash):
        raise TaskGraphProofError("dry-run report_sha256 is missing or malformed")
    migration_id = f"proof-{source_main[:12]}"
    path = (
        "Pipeline/TaskGraph/migrations/"
        f"repository-history-identity-{migration_id}.json"
    )
    commit_map = _canonical_commit_map(worktree, report, target_main)
    manifest = {
        "schema_version": "1.0",
        "migration_type": "repository_history_identity",
        "migration_id": migration_id,
        "reason": "git_identity_sanitization",
        "approved_by": "CI dry-run proof only",
        "approved_at": "2026-08-29T00:00:00Z",
        "source_main": source_main,
        "source_main_tree": source_tree,
        "target_main": target_main,
        "target_main_tree": target_tree,
        "rewrite_report_sha256": report_hash,
        "commit_map": commit_map,
    }
    manifest_path = worktree / path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _run(worktree, ("git", "config", "user.name", "No Safe Circle History Migration Proof"))
    _run(
        worktree,
        ("git", "config", "user.email", "history-migration-proof@nosafecircle.invalid"),
    )
    _run(worktree, ("git", "add", "--", path))
    staged = _git(worktree, "diff", "--cached", "--name-only")
    if staged.splitlines() != [path]:
        raise TaskGraphProofError(
            f"proof manifest commit staged unexpected files: {staged!r}"
        )
    _run(worktree, ("git", "commit", "-m", "Proof repository history identity migration"))
    proof_head = _sha(_git(worktree, "rev-parse", "HEAD"), "proof HEAD")
    if _git(worktree, "status", "--porcelain"):
        raise TaskGraphProofError("proof worktree is dirty after manifest commit")
    changed = _git(worktree, "diff", "--name-only", target_main, proof_head).splitlines()
    if changed != [path]:
        raise TaskGraphProofError(
            f"proof commit changed files other than migration authority: {changed}"
        )
    return path, proof_head, len(commit_map)


def _evaluate_with_candidate_tooling(
    *,
    worktree: Path,
    tooling_root: Path,
    task_id: str,
) -> dict[str, Any]:
    script = r'''
import json
import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
tooling_root = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(tooling_root / "Pipeline" / "TaskGraph"))
from current_conformance import evaluate_current_conformance
result = evaluate_current_conformance(root=root, selector=sys.argv[3])
print(json.dumps(result.to_dict(), sort_keys=True))
'''
    result = _run(
        worktree,
        (
            sys.executable,
            "-c",
            script,
            str(worktree),
            str(tooling_root),
            task_id,
        ),
    )
    try:
        conformance = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TaskGraphProofError(
            f"TaskGraph proof returned invalid JSON: {result.stdout!r}"
        ) from exc
    if not isinstance(conformance, dict):
        raise TaskGraphProofError("TaskGraph proof result must be an object")
    return conformance


def prove_taskgraph(
    *,
    mirror: Path,
    dry_run_report: Path,
    worktree: Path,
    task_id: str,
) -> dict[str, Any]:
    mirror = mirror.resolve()
    tooling_root = Path(__file__).resolve().parents[2]
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
    manifest_path, proof_head, translation_count = _commit_proof_manifest(
        worktree=worktree,
        report=report,
        target_main=target_main,
        target_tree=target_tree,
    )

    conformance = _evaluate_with_candidate_tooling(
        worktree=worktree,
        tooling_root=tooling_root,
        task_id=task_id,
    )
    if conformance.get("state") != "conformant":
        raise TaskGraphProofError(
            f"rewritten history did not preserve {task_id} conformance: {conformance}"
        )
    if conformance.get("head_commit") != proof_head:
        raise TaskGraphProofError(
            f"TaskGraph proof did not run on manifest proof HEAD: "
            f"{conformance.get('head_commit')} != {proof_head}"
        )

    proof: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "history_identity_taskgraph_proof",
        "task_id": task_id,
        "source_main": report.get("source_main"),
        "target_main": target_main,
        "target_main_tree": target_tree,
        "proof_head": proof_head,
        "migration_manifest_path": manifest_path,
        "canonical_translation_count": translation_count,
        "translation_mode": "committed_tree_verified_manifest",
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
