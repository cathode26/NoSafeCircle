#!/usr/bin/env python3
"""Conservative cleanup helper for interactive Unity iteration.

This helper is intentionally separate from authoritative Unity validation. It records
pre-Unity worktree state, classifies post-Unity churn, and only restores/removes
changes that are provably outside the captured task state and match narrow safe rules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = "1.0"

KNOWN_TRACKED_UNITY_CHURN_EXACT = {
    "ProjectSettings/EditorBuildSettings.asset",
    "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json",
}

KNOWN_TRACKED_UNITY_CHURN_PREFIXES = (
    "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/",
)

KNOWN_GENERATED_UNTRACKED_PREFIXES = (
    "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/",
)

RESOURCE_PREFIXES = ("repo-file:", "unity-scene:")


class HygieneError(RuntimeError):
    pass


@dataclass(frozen=True)
class StatusEntry:
    code: str
    path: str

    @property
    def untracked(self) -> bool:
        return self.code == "??"

    @property
    def index_changed(self) -> bool:
        return not self.untracked and self.code[0] not in (" ", "?")


def run_git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(root), *args),
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def repo_root(start: Path) -> Path:
    try:
        return Path(run_git(start, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HygieneError("current directory is not inside a Git repository") from exc


def head_and_tree(root: Path) -> tuple[str, str]:
    try:
        head = run_git(root, "rev-parse", "--verify", "HEAD").stdout.strip()
        tree = run_git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
        return head, tree
    except subprocess.CalledProcessError as exc:
        raise HygieneError("could not resolve repository HEAD/tree") from exc


def parse_status(root: Path) -> list[StatusEntry]:
    raw = run_git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout
    entries: list[StatusEntry] = []
    for line in raw.splitlines():
        if len(line) < 4:
            continue
        code = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip('"').replace("\\", "/")
        entries.append(StatusEntry(code=code, path=path))
    return entries


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_under_repo(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def task_preserve_paths(root: Path, task_id: str | None) -> set[str]:
    if not task_id:
        return set()
    task_path = root / "Tasks" / f"{task_id}.yaml"
    if not task_path.is_file():
        raise HygieneError(f"task contract does not exist: Tasks/{task_id}.yaml")
    try:
        raw = json.loads(task_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HygieneError(
            f"task contract must be JSON-shaped UTF-8 for workspace hygiene: Tasks/{task_id}.yaml"
        ) from exc
    resources = raw.get("exclusive_resources", [])
    if not isinstance(resources, list):
        raise HygieneError("task exclusive_resources must be an array")
    preserve: set[str] = set()
    for resource in resources:
        if not isinstance(resource, str):
            continue
        for prefix in RESOURCE_PREFIXES:
            if resource.startswith(prefix):
                preserve.add(resource[len(prefix):].replace("\\", "/"))
                break
    return preserve


def normalize_paths(values: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for value in values:
        path = value.strip().replace("\\", "/")
        if not path or path.startswith("/") or ".." in Path(path).parts:
            raise HygieneError(f"invalid repository-relative path: {value!r}")
        result.add(path)
    return result


def snapshot_payload(root: Path, task_id: str | None, extra_preserve: Iterable[str]) -> dict:
    head, tree = head_and_tree(root)
    entries = parse_status(root)
    preserve = task_preserve_paths(root, task_id) | normalize_paths(extra_preserve)
    baseline: dict[str, dict[str, str | None]] = {}
    for entry in entries:
        baseline[entry.path] = {
            "status": entry.code,
            "sha256": sha256_file(root / entry.path),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "repository_root": str(root),
        "head": head,
        "tree": tree,
        "task_id": task_id,
        "preserve_paths": sorted(preserve),
        "baseline_status": baseline,
    }


def write_snapshot(root: Path, output: Path, payload: dict) -> None:
    output = output.expanduser().resolve()
    if is_under_repo(root, output):
        raise HygieneError("snapshot output must live outside the repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise HygieneError(f"refusing to overwrite existing snapshot: {output}")
    temp = output.with_name(output.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, output)


def load_snapshot(root: Path, path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HygieneError(f"could not read valid snapshot JSON: {path}") from exc
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise HygieneError("unsupported workspace-hygiene snapshot schema")
    if Path(raw.get("repository_root", "")).resolve() != root.resolve():
        raise HygieneError("snapshot belongs to a different repository checkout")
    head, _ = head_and_tree(root)
    if raw.get("head") != head:
        raise HygieneError("repository HEAD changed since the hygiene snapshot")
    if not isinstance(raw.get("baseline_status"), dict) or not isinstance(raw.get("preserve_paths"), list):
        raise HygieneError("snapshot is missing required baseline/preserve metadata")
    return raw


def git_diff_quiet(root: Path, path: str, *, ignore_whitespace: bool = False) -> bool:
    args = ["diff"]
    if ignore_whitespace:
        args.append("-w")
    args.extend(["--quiet", "--", path])
    result = run_git(root, *args, check=False)
    if result.returncode not in (0, 1):
        raise HygieneError(f"git diff failed for {path}: {result.stderr.strip()}")
    return result.returncode == 0


def prefixed(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)


def classify(root: Path, snapshot: dict) -> dict[str, list[str]]:
    baseline = snapshot["baseline_status"]
    baseline_paths = set(baseline)
    preserve_paths = set(snapshot["preserve_paths"])
    categories: dict[str, list[str]] = {
        "baseline_preserved": [],
        "baseline_changed_since_snapshot": [],
        "task_preserved": [],
        "safe_stat_only": [],
        "safe_whitespace_only": [],
        "known_unity_churn": [],
        "new_generated_untracked": [],
        "unexpected_tracked": [],
        "unexpected_untracked": [],
        "unexpected_staged": [],
    }

    for entry in parse_status(root):
        path = entry.path
        if path in baseline_paths:
            before_hash = baseline[path].get("sha256")
            after_hash = sha256_file(root / path)
            if before_hash != after_hash:
                categories["baseline_changed_since_snapshot"].append(path)
            else:
                categories["baseline_preserved"].append(path)
            continue

        if path in preserve_paths:
            categories["task_preserved"].append(path)
            continue

        if entry.index_changed:
            categories["unexpected_staged"].append(path)
            continue

        if entry.untracked:
            if prefixed(path, KNOWN_GENERATED_UNTRACKED_PREFIXES):
                categories["new_generated_untracked"].append(path)
            else:
                categories["unexpected_untracked"].append(path)
            continue

        if git_diff_quiet(root, path):
            categories["safe_stat_only"].append(path)
        elif git_diff_quiet(root, path, ignore_whitespace=True):
            categories["safe_whitespace_only"].append(path)
        elif path in KNOWN_TRACKED_UNITY_CHURN_EXACT or prefixed(path, KNOWN_TRACKED_UNITY_CHURN_PREFIXES):
            categories["known_unity_churn"].append(path)
        else:
            categories["unexpected_tracked"].append(path)

    for values in categories.values():
        values.sort()
    return categories


def print_categories(categories: dict[str, list[str]]) -> None:
    titles = {
        "baseline_preserved": "PRE-UNITY TASK STATE (unchanged)",
        "baseline_changed_since_snapshot": "PRE-UNITY TASK STATE MUTATED AFTER SNAPSHOT (manual review)",
        "task_preserved": "TASK RESOURCE CHANGES TO KEEP",
        "safe_stat_only": "SAFE STAT-ONLY CHURN",
        "safe_whitespace_only": "SAFE WHITESPACE-ONLY CHURN",
        "known_unity_churn": "KNOWN UNITY CHURN",
        "new_generated_untracked": "NEW GENERATED UNITY ASSETS (kept unless explicitly removed)",
        "unexpected_tracked": "UNEXPECTED TRACKED CHANGES (block cleanup)",
        "unexpected_untracked": "UNEXPECTED UNTRACKED FILES (block cleanup)",
        "unexpected_staged": "UNEXPECTED STAGED CHANGES (block cleanup)",
    }
    for key, title in titles.items():
        values = categories[key]
        if not values:
            continue
        print(f"\n{title}")
        for path in values:
            print(f"  {path}")


def blockers(categories: dict[str, list[str]]) -> list[str]:
    return sorted(
        categories["baseline_changed_since_snapshot"]
        + categories["unexpected_tracked"]
        + categories["unexpected_untracked"]
        + categories["unexpected_staged"]
    )


def restore_paths(root: Path, paths: Iterable[str]) -> None:
    for path in sorted(set(paths)):
        result = run_git(root, "restore", "--source=HEAD", "--worktree", "--", path, check=False)
        if result.returncode != 0:
            raise HygieneError(f"git restore failed for {path}: {result.stderr.strip()}")
        print(f"restored: {path}")


def remove_generated_untracked(root: Path, paths: Iterable[str]) -> None:
    for path in sorted(set(paths), key=lambda value: (value.count("/"), value), reverse=True):
        target = (root / path).resolve()
        if not is_under_repo(root, target):
            raise HygieneError(f"refusing to remove path outside repository: {path}")
        if not prefixed(path, KNOWN_GENERATED_UNTRACKED_PREFIXES):
            raise HygieneError(f"refusing to remove unapproved generated path: {path}")
        tracked = run_git(root, "ls-files", "--", path).stdout.strip()
        if tracked:
            raise HygieneError(f"refusing to remove tracked path: {path}")
        if target.is_file() or target.is_symlink():
            target.unlink()
            print(f"removed generated untracked: {path}")

    for prefix in KNOWN_GENERATED_UNTRACKED_PREFIXES:
        prefix_root = (root / prefix.rstrip("/")).resolve()
        if not prefix_root.exists():
            continue
        dirs = sorted((p for p in prefix_root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True)
        for directory in dirs:
            try:
                directory.rmdir()
            except OSError:
                pass


def cmd_snapshot(args: argparse.Namespace) -> int:
    root = repo_root(Path(args.repo))
    payload = snapshot_payload(root, args.task_id, args.preserve)
    write_snapshot(root, Path(args.output), payload)
    print(f"Unity workspace snapshot: {Path(args.output).expanduser().resolve()}")
    print(f"HEAD: {payload['head']}")
    print(f"Captured pre-Unity changed paths: {len(payload['baseline_status'])}")
    print(f"Task-preserved resources: {len(payload['preserve_paths'])}")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    root = repo_root(Path(args.repo))
    snapshot = load_snapshot(root, Path(args.snapshot).expanduser().resolve())
    categories = classify(root, snapshot)
    print_categories(categories)
    blocked = blockers(categories)
    if blocked:
        print("\nHYGIENE STATUS: BLOCKED — unexpected or mutated task state requires review.")
        return 2
    print("\nHYGIENE STATUS: SAFE — known cleanup can run without touching captured task state.")
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    root = repo_root(Path(args.repo))
    snapshot = load_snapshot(root, Path(args.snapshot).expanduser().resolve())
    categories = classify(root, snapshot)
    print_categories(categories)
    blocked = blockers(categories)
    if blocked:
        print("\nCLEANUP REFUSED: unexpected or mutated task state requires review.")
        return 2

    restore_paths(
        root,
        categories["safe_stat_only"]
        + categories["safe_whitespace_only"]
        + categories["known_unity_churn"],
    )
    if args.remove_new_untracked:
        remove_generated_untracked(root, categories["new_generated_untracked"])

    after = classify(root, snapshot)
    after_blocked = blockers(after)
    if after_blocked:
        print_categories(after)
        print("\nCLEANUP INCOMPLETE: blocking state remains.")
        return 2

    print("\nUNITY WORKSPACE HYGIENE COMPLETE")
    print("Captured pre-Unity task state and task-preserved resources were not restored or deleted.")
    if after["new_generated_untracked"]:
        print("Generated untracked assets remain for human review/possible commit.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository path (default: current directory)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot", help="capture pre-Unity task/worktree state")
    snapshot.add_argument("--task-id", help="optional task ID used to preserve exclusive repo/scene resources")
    snapshot.add_argument("--preserve", action="append", default=[], help="extra repo-relative path to preserve (repeatable)")
    snapshot.add_argument("--output", required=True, help="snapshot JSON path; must be outside repository")
    snapshot.set_defaults(func=cmd_snapshot)

    inspect = subparsers.add_parser("inspect", help="classify post-Unity changes against a snapshot")
    inspect.add_argument("--snapshot", required=True, help="snapshot JSON produced by snapshot")
    inspect.set_defaults(func=cmd_inspect)

    clean = subparsers.add_parser("clean", help="restore only proven-safe Unity churn")
    clean.add_argument("--snapshot", required=True, help="snapshot JSON produced by snapshot")
    clean.add_argument(
        "--remove-new-untracked",
        action="store_true",
        help="also delete new untracked files under approved generated roots; use for rejected/retry cleanup",
    )
    clean.set_defaults(func=cmd_clean)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except HygieneError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
