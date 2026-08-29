#!/usr/bin/env python3
"""Build a non-destructive, execution-ready Git history migration candidate.

The script consumes a proven identity-rewrite dry run and its reviewed ref plan,
commits the production TaskGraph migration manifest on top of the rewritten main
inside the disposable mirror, proves current TaskGraph conformance, and emits:

* a rewritten-main Git bundle containing the exact candidate main history;
* a rollback Git bundle containing the exact pre-migration remote heads/tags;
* an execution plan bound to SHA-256 identities for both bundles;
* a PowerShell execution script that remains inert until separately approved.

It never contacts a remote and never updates the source repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0"
REPORT_TYPE = "history_identity_final_candidate"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MIGRATION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REMOTE_PREFIX = "refs/remotes/origin/"


class FinalCandidateError(RuntimeError):
    """Raised when the final candidate cannot be proven safe."""


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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(
    cwd: Path,
    args: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        detail = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        raise FinalCandidateError(
            f"command failed ({result.returncode}): {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def _git(cwd: Path, *args: str, env: Mapping[str, str] | None = None) -> str:
    return _run(cwd, ("git", *args), env=env).stdout.strip()


def _sha(value: Any, label: str) -> str:
    text = str(value or "")
    if not GIT_SHA_RE.fullmatch(text):
        raise FinalCandidateError(f"{label} is not a lowercase 40-character Git SHA")
    return text


def _sha256(value: Any, label: str) -> str:
    text = str(value or "")
    if not SHA256_RE.fullmatch(text):
        raise FinalCandidateError(f"{label} is not a lowercase SHA-256")
    return text


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FinalCandidateError(f"unable to read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise FinalCandidateError(f"{label} must contain a JSON object")
    return value


def _is_ancestor(repo: Path, older: str, newer: str) -> bool:
    result = _run(
        repo,
        ("git", "merge-base", "--is-ancestor", older, newer),
        check=False,
    )
    return result.returncode == 0


def _tree(repo: Path, commit: str) -> str:
    return _sha(_git(repo, "rev-parse", f"{commit}^{{tree}}"), f"{commit} tree")


def _blob(repo: Path, commit: str, path: str) -> str:
    return _sha(_git(repo, "rev-parse", f"{commit}:{path}"), f"{path} blob")


def _canonical_commit_map(
    mirror: Path,
    report: Mapping[str, Any],
    raw_target_main: str,
) -> list[dict[str, str]]:
    raw_map = report.get("commit_map")
    if not isinstance(raw_map, list):
        raise FinalCandidateError("dry-run commit_map must be a list")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_map):
        if not isinstance(raw, Mapping):
            raise FinalCandidateError(f"commit_map[{index}] must be an object")
        old_commit = _sha(raw.get("old_commit"), f"commit_map[{index}].old_commit")
        new_commit = _sha(raw.get("new_commit"), f"commit_map[{index}].new_commit")
        tree = _sha(raw.get("tree"), f"commit_map[{index}].tree")
        if not _is_ancestor(mirror, new_commit, raw_target_main):
            continue
        if old_commit in seen:
            raise FinalCandidateError(f"duplicate canonical translation for {old_commit}")
        seen.add(old_commit)
        if _tree(mirror, new_commit) != tree:
            raise FinalCandidateError(
                f"translated commit tree mismatch: {old_commit} -> {new_commit}"
            )
        rows.append(
            {"old_commit": old_commit, "new_commit": new_commit, "tree": tree}
        )
    if not rows:
        raise FinalCandidateError("dry run produced no canonical rewritten commits")
    return sorted(rows, key=lambda item: item["old_commit"])


def _validate_inputs(
    *,
    source: Path,
    mirror: Path,
    dry: Mapping[str, Any],
    plan: Mapping[str, Any],
    expected_source_main: str,
) -> tuple[str, str, str]:
    if dry.get("report_type") != "history_identity_dry_run":
        raise FinalCandidateError("input is not a history identity dry-run report")
    if dry.get("trees_preserved") is not True:
        raise FinalCandidateError("dry run did not prove tree preservation")
    source_main = _sha(dry.get("source_main"), "dry_run.source_main")
    source_tree = _sha(dry.get("source_main_tree"), "dry_run.source_main_tree")
    raw_target_main = _sha(dry.get("target_main"), "dry_run.target_main")
    raw_target_tree = _sha(dry.get("target_main_tree"), "dry_run.target_main_tree")
    if source_main != expected_source_main:
        raise FinalCandidateError(
            f"frozen source main changed: {source_main} != {expected_source_main}"
        )
    if source_tree != raw_target_tree:
        raise FinalCandidateError("raw rewritten main changed the source tree")
    if _sha(_git(source, "rev-parse", "refs/heads/main"), "source main") != source_main:
        raise FinalCandidateError("source checkout main does not match dry-run source_main")
    if _sha(_git(mirror, "rev-parse", "refs/heads/main"), "mirror main") != raw_target_main:
        raise FinalCandidateError("rewritten mirror main does not match dry-run target_main")
    if _tree(mirror, raw_target_main) != raw_target_tree:
        raise FinalCandidateError("rewritten mirror main tree does not match dry-run report")

    if plan.get("report_type") != "history_identity_migration_plan":
        raise FinalCandidateError("input is not a history identity migration plan")
    if plan.get("source_main") != source_main or plan.get("target_main") != raw_target_main:
        raise FinalCandidateError("migration plan main identities disagree with dry run")
    if plan.get("ready_for_destructive_phase") is not True:
        raise FinalCandidateError(
            f"migration plan is not ready: blockers={plan.get('pre_rewrite_blockers')}, "
            f"unclassified={plan.get('unclassified_affected_branches')}"
        )
    if plan.get("pre_rewrite_blockers") or plan.get("unclassified_affected_branches"):
        raise FinalCandidateError("migration plan contains blockers despite ready state")
    return source_main, source_tree, raw_target_main


def _commit_manifest(
    *,
    mirror: Path,
    worktree: Path,
    dry: Mapping[str, Any],
    source_main: str,
    source_tree: str,
    raw_target_main: str,
    migration_id: str,
    approved_by: str,
    approved_at: str,
) -> tuple[str, str, str, str, int]:
    if worktree.exists():
        raise FinalCandidateError(f"candidate worktree already exists: {worktree}")
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _run(mirror, ("git", "worktree", "add", "--detach", str(worktree), raw_target_main))

    report_hash = _sha256(dry.get("report_sha256"), "dry_run.report_sha256")
    raw_target_tree = _tree(worktree, raw_target_main)
    commit_map = _canonical_commit_map(worktree, dry, raw_target_main)
    manifest_path = (
        "Pipeline/TaskGraph/migrations/"
        f"repository-history-identity-{migration_id}.json"
    )
    manifest = {
        "schema_version": "1.0",
        "migration_type": "repository_history_identity",
        "migration_id": migration_id,
        "reason": "git_identity_sanitization",
        "approved_by": approved_by,
        "approved_at": approved_at,
        "source_main": source_main,
        "source_main_tree": source_tree,
        "target_main": raw_target_main,
        "target_main_tree": raw_target_tree,
        "rewrite_report_sha256": report_hash,
        "commit_map": commit_map,
    }
    destination = worktree / manifest_path
    if destination.exists():
        raise FinalCandidateError(f"migration manifest already exists: {manifest_path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    commit_env = dict(os.environ)
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "No Safe Circle History Migration",
            "GIT_AUTHOR_EMAIL": "history-migration@nosafecircle.invalid",
            "GIT_COMMITTER_NAME": "No Safe Circle History Migration",
            "GIT_COMMITTER_EMAIL": "history-migration@nosafecircle.invalid",
            "GIT_AUTHOR_DATE": approved_at,
            "GIT_COMMITTER_DATE": approved_at,
        }
    )
    _run(worktree, ("git", "add", "--", manifest_path), env=commit_env)
    staged = _git(worktree, "diff", "--cached", "--name-only", env=commit_env).splitlines()
    if staged != [manifest_path]:
        raise FinalCandidateError(f"manifest commit staged unexpected paths: {staged}")
    _run(
        worktree,
        (
            "git",
            "-c",
            "commit.gpgSign=false",
            "commit",
            "-m",
            f"Record repository history identity migration {migration_id}",
        ),
        env=commit_env,
    )
    final_main = _sha(_git(worktree, "rev-parse", "HEAD"), "final main")
    final_tree = _tree(worktree, final_main)
    if _git(worktree, "status", "--porcelain"):
        raise FinalCandidateError("candidate worktree is dirty after manifest commit")
    changed = _git(worktree, "diff", "--name-only", raw_target_main, final_main).splitlines()
    if changed != [manifest_path]:
        raise FinalCandidateError(
            f"final candidate changed files other than migration manifest: {changed}"
        )
    if _git(worktree, "rev-list", "--count", f"{raw_target_main}..{final_main}") != "1":
        raise FinalCandidateError("final main must be exactly one manifest commit above rewritten main")
    manifest_blob = _blob(worktree, final_main, manifest_path)
    manifest_sha256 = file_sha256(destination)
    return manifest_path, manifest_blob, manifest_sha256, final_main, len(commit_map)


def _evaluate_taskgraph(worktree: Path, task_id: str) -> dict[str, Any]:
    validation = _run(
        worktree,
        (sys.executable, "Pipeline/TaskGraph/taskcontrol.py", "validate"),
        check=False,
    )
    if validation.returncode:
        raise FinalCandidateError(
            "TaskGraph validation failed on final candidate:\n"
            + validation.stdout
            + validation.stderr
        )
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
        raise FinalCandidateError(
            f"TaskGraph conformance returned invalid JSON: {result.stdout!r}"
        ) from exc
    if not isinstance(conformance, dict) or conformance.get("state") != "conformant":
        raise FinalCandidateError(
            f"final candidate did not preserve {task_id} conformance: {conformance}"
        )
    return conformance


def _list_remote_refs(source: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    output = _git(
        source,
        "for-each-ref",
        "--format=%(refname)%00%(objectname)",
        "refs/remotes/origin",
        "refs/tags",
    )
    branches: list[dict[str, str]] = []
    tags: list[dict[str, str]] = []
    for line in output.splitlines():
        if not line:
            continue
        parts = line.split("\x00")
        if len(parts) != 2:
            raise FinalCandidateError("unexpected for-each-ref output")
        ref, commit = parts
        commit = _sha(commit, f"{ref} target")
        if ref.startswith(REMOTE_PREFIX):
            branch = ref[len(REMOTE_PREFIX) :]
            if branch == "HEAD" or not branch:
                continue
            branches.append({"branch": branch, "commit": commit})
        elif ref.startswith("refs/tags/"):
            tags.append({"ref": ref, "commit": commit})
    if not any(item["branch"] == "main" for item in branches):
        raise FinalCandidateError("rollback inventory did not include origin/main")
    return (
        sorted(branches, key=lambda item: item["branch"].casefold()),
        sorted(tags, key=lambda item: item["ref"].casefold()),
    )


def _delete_ref(repo: Path, ref: str) -> None:
    _run(repo, ("git", "update-ref", "-d", ref), check=False)


def _build_rollback_bundle(
    *,
    source: Path,
    output_dir: Path,
) -> tuple[Path, Path, list[dict[str, str]], list[dict[str, str]]]:
    branches, tags = _list_remote_refs(source)
    rollback_repo = output_dir / "rollback.git"
    bundle_path = output_dir / "rollback-pre-migration.bundle"
    refs_path = output_dir / "rollback-refs.json"
    _run(output_dir, ("git", "clone", "--mirror", "--no-local", str(source), str(rollback_repo)))

    existing = _git(rollback_repo, "for-each-ref", "--format=%(refname)").splitlines()
    for ref in existing:
        _delete_ref(rollback_repo, ref)
    for item in branches:
        _run(
            rollback_repo,
            ("git", "update-ref", f"refs/heads/{item['branch']}", item["commit"]),
        )
    for item in tags:
        _run(rollback_repo, ("git", "update-ref", item["ref"], item["commit"]))
    _run(rollback_repo, ("git", "symbolic-ref", "HEAD", "refs/heads/main"))
    _run(rollback_repo, ("git", "fsck", "--full", "--strict"))
    _run(rollback_repo, ("git", "bundle", "create", str(bundle_path), "--all"))
    _run(rollback_repo, ("git", "bundle", "verify", str(bundle_path)))
    refs_document = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "history_identity_rollback_refs",
        "branches": branches,
        "tags": tags,
    }
    refs_document["report_sha256"] = semantic_sha256(refs_document)
    refs_path.write_text(
        json.dumps(refs_document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    shutil.rmtree(rollback_repo)
    return bundle_path, refs_path, branches, tags


def _build_rewritten_bundle(
    *,
    mirror: Path,
    output_dir: Path,
    raw_target_main: str,
    final_main: str,
) -> Path:
    current = _sha(_git(mirror, "rev-parse", "refs/heads/main"), "mirror main")
    if current != raw_target_main:
        raise FinalCandidateError(
            f"mirror main moved before finalization: {current} != {raw_target_main}"
        )
    _run(mirror, ("git", "update-ref", "refs/heads/main", final_main, raw_target_main))
    bundle = output_dir / "rewritten-main.bundle"
    _run(mirror, ("git", "fsck", "--full", "--strict"))
    _run(mirror, ("git", "bundle", "create", str(bundle), "refs/heads/main"))
    _run(mirror, ("git", "bundle", "verify", str(bundle)))
    return bundle


def _finalize_plan(
    *,
    original_plan: Mapping[str, Any],
    source_main: str,
    source_tree: str,
    raw_target_main: str,
    final_main: str,
    final_tree: str,
    manifest_path: str,
    manifest_blob: str,
    manifest_sha256: str,
    migration_id: str,
    approved_by: str,
    approved_at: str,
    translation_count: int,
    conformance: Mapping[str, Any],
    rewritten_bundle: Path,
    rollback_bundle: Path,
    rollback_refs_path: Path,
    rollback_branches: list[dict[str, str]],
    rollback_tags: list[dict[str, str]],
) -> dict[str, Any]:
    branch_actions = json.loads(json.dumps(original_plan.get("branch_actions")))
    if not isinstance(branch_actions, list):
        raise FinalCandidateError("migration plan branch_actions must be a list")
    for row in branch_actions:
        if isinstance(row, dict) and row.get("branch") == "main":
            row["raw_rewritten_commit"] = row.get("new_commit")
            row["new_commit"] = final_main
    destructive = json.loads(json.dumps(original_plan.get("destructive_operations")))
    if not isinstance(destructive, dict):
        raise FinalCandidateError("migration plan destructive_operations must be an object")
    updates = destructive.get("force_update")
    if not isinstance(updates, list) or len(updates) != 1 or updates[0].get("branch") != "main":
        raise FinalCandidateError("migration plan must contain exactly one main force update")
    updates[0]["raw_rewritten_commit"] = updates[0].get("new_commit")
    updates[0]["new_commit"] = final_main

    candidate: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_type": REPORT_TYPE,
        "repository": original_plan.get("repository"),
        "migration_id": migration_id,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "source_main": source_main,
        "source_main_tree": source_tree,
        "raw_rewritten_main": raw_target_main,
        "raw_rewritten_main_tree": source_tree,
        "final_main": final_main,
        "final_main_tree": final_tree,
        "migration_manifest": {
            "path": manifest_path,
            "blob_sha": manifest_blob,
            "sha256": manifest_sha256,
            "canonical_translation_count": translation_count,
        },
        "taskgraph_conformance": dict(conformance),
        "branch_actions": branch_actions,
        "destructive_operations": destructive,
        "github_actions": original_plan.get("github_actions"),
        "rollback": {
            "bundle": rollback_bundle.name,
            "bundle_sha256": file_sha256(rollback_bundle),
            "refs_report": rollback_refs_path.name,
            "refs_report_sha256": file_sha256(rollback_refs_path),
            "branch_count": len(rollback_branches),
            "tag_count": len(rollback_tags),
        },
        "rewritten_history": {
            "bundle": rewritten_bundle.name,
            "bundle_sha256": file_sha256(rewritten_bundle),
        },
        "execution_preconditions": {
            "remote_main_must_equal": source_main,
            "all_branch_leases_must_match": True,
            "atomic_push_required": True,
            "explicit_human_confirmation_required": True,
        },
        "ready_for_explicit_execution_approval": True,
    }
    candidate["report_sha256"] = semantic_sha256(candidate)
    return candidate


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _write_execution_script(
    *,
    path: Path,
    candidate: Mapping[str, Any],
) -> None:
    source_main = _sha(candidate.get("source_main"), "candidate.source_main")
    final_main = _sha(candidate.get("final_main"), "candidate.final_main")
    candidate_hash = _sha256(candidate.get("report_sha256"), "candidate.report_sha256")
    operations = candidate.get("destructive_operations")
    if not isinstance(operations, Mapping):
        raise FinalCandidateError("candidate destructive_operations must be an object")
    deletions = operations.get("delete_after_migration")
    if not isinstance(deletions, list):
        raise FinalCandidateError("candidate delete_after_migration must be a list")

    deletion_rows = []
    for raw in deletions:
        if not isinstance(raw, Mapping):
            raise FinalCandidateError("candidate deletion row must be an object")
        branch = str(raw.get("branch") or "")
        old_commit = _sha(raw.get("old_commit"), f"delete {branch} old commit")
        deletion_rows.append((branch, old_commit))

    lines = [
        "$ErrorActionPreference = 'Stop'",
        "",
        f"$ExpectedSourceMain = {_powershell_quote(source_main)}",
        f"$ExpectedFinalMain = {_powershell_quote(final_main)}",
        f"$ExpectedCandidateSha256 = {_powershell_quote(candidate_hash)}",
        "$ArtifactDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path",
        "$CandidatePath = Join-Path $ArtifactDirectory 'history-identity-final-candidate.json'",
        "$BundlePath = Join-Path $ArtifactDirectory 'rewritten-main.bundle'",
        "",
        "throw 'INERT BY DESIGN: explicit post-review approval is required before this script may be enabled.'",
        "",
        "# The reviewed execution implementation must remove the throw above only after",
        "# binding a separate approval record to ExpectedCandidateSha256 and ExpectedFinalMain.",
        "# It must then perform one atomic push with exact force-with-lease values:",
        "#",
        "#   git fetch origin --prune",
        "#   git fetch $BundlePath refs/heads/main:refs/heads/history-migration-final-candidate",
        "#   git push --atomic origin `",
        "#       history-migration-final-candidate:refs/heads/main `",
        "#       --force-with-lease=refs/heads/main:$ExpectedSourceMain `",
    ]
    for branch, old_commit in deletion_rows:
        lines.append(f"#       :refs/heads/{branch} `")
        lines.append(f"#       --force-with-lease=refs/heads/{branch}:{old_commit} `")
    lines.extend(
        [
            "#",
            "# Before the push, every remote ref must be re-read and match its recorded lease.",
            "# After the push, origin/main must equal ExpectedFinalMain and every deleted ref",
            "# must be absent before Issue #64 or PR #77 metadata is changed.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_candidate(
    *,
    source: Path,
    mirror: Path,
    dry_run_report: Path,
    migration_plan: Path,
    output_dir: Path,
    worktree: Path,
    expected_source_main: str,
    migration_id: str,
    approved_by: str,
    approved_at: str,
    task_id: str,
) -> dict[str, Any]:
    source = source.resolve()
    mirror = mirror.resolve()
    output_dir = output_dir.resolve()
    worktree = worktree.resolve()
    expected_source_main = _sha(expected_source_main, "expected source main")
    if not MIGRATION_ID_RE.fullmatch(migration_id):
        raise FinalCandidateError("migration_id is invalid")
    if not approved_by.strip():
        raise FinalCandidateError("approved_by must be non-empty")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", approved_at):
        raise FinalCandidateError("approved_at must be UTC YYYY-MM-DDTHH:MM:SSZ")
    if output_dir.exists():
        raise FinalCandidateError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)

    dry = _load_json(dry_run_report, "dry-run report")
    plan = _load_json(migration_plan, "migration plan")
    source_main, source_tree, raw_target_main = _validate_inputs(
        source=source,
        mirror=mirror,
        dry=dry,
        plan=plan,
        expected_source_main=expected_source_main,
    )
    manifest_path, manifest_blob, manifest_sha256, final_main, translation_count = _commit_manifest(
        mirror=mirror,
        worktree=worktree,
        dry=dry,
        source_main=source_main,
        source_tree=source_tree,
        raw_target_main=raw_target_main,
        migration_id=migration_id,
        approved_by=approved_by.strip(),
        approved_at=approved_at,
    )
    final_tree = _tree(worktree, final_main)
    conformance = _evaluate_taskgraph(worktree, task_id)
    if conformance.get("head_commit") != final_main:
        raise FinalCandidateError("TaskGraph conformance did not run on final main")

    manifest_copy = output_dir / "migration-manifest.json"
    shutil.copy2(worktree / manifest_path, manifest_copy)
    rollback_bundle, rollback_refs_path, rollback_branches, rollback_tags = _build_rollback_bundle(
        source=source,
        output_dir=output_dir,
    )
    rewritten_bundle = _build_rewritten_bundle(
        mirror=mirror,
        output_dir=output_dir,
        raw_target_main=raw_target_main,
        final_main=final_main,
    )
    candidate = _finalize_plan(
        original_plan=plan,
        source_main=source_main,
        source_tree=source_tree,
        raw_target_main=raw_target_main,
        final_main=final_main,
        final_tree=final_tree,
        manifest_path=manifest_path,
        manifest_blob=manifest_blob,
        manifest_sha256=manifest_sha256,
        migration_id=migration_id,
        approved_by=approved_by.strip(),
        approved_at=approved_at,
        translation_count=translation_count,
        conformance=conformance,
        rewritten_bundle=rewritten_bundle,
        rollback_bundle=rollback_bundle,
        rollback_refs_path=rollback_refs_path,
        rollback_branches=rollback_branches,
        rollback_tags=rollback_tags,
    )
    candidate_path = output_dir / "history-identity-final-candidate.json"
    candidate_path.write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_execution_script(
        path=output_dir / "execute-history-identity-migration.ps1",
        candidate=candidate,
    )

    _run(mirror, ("git", "bundle", "verify", str(rewritten_bundle)))
    _run(source, ("git", "bundle", "verify", str(rollback_bundle)))
    return candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the final non-destructive history migration candidate.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--mirror", required=True)
    parser.add_argument("--dry-run-report", required=True)
    parser.add_argument("--migration-plan", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--expected-source-main", required=True)
    parser.add_argument("--migration-id", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approved-at", required=True)
    parser.add_argument("--task-id", default="NSC-020")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        candidate = build_candidate(
            source=Path(args.source),
            mirror=Path(args.mirror),
            dry_run_report=Path(args.dry_run_report),
            migration_plan=Path(args.migration_plan),
            output_dir=Path(args.output),
            worktree=Path(args.worktree),
            expected_source_main=args.expected_source_main,
            migration_id=args.migration_id,
            approved_by=args.approved_by,
            approved_at=args.approved_at,
            task_id=args.task_id,
        )
        print(json.dumps(candidate, indent=2, sort_keys=True))
        return 0
    except FinalCandidateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
