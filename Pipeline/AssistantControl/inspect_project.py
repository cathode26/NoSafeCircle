"""Read committed task definitions and local edits without changing Git state.

This is inventory, not task admission or proof of delivery. All task reads use
one pinned commit. Working files are deliberately not used as task contracts.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task


def _msys_startup_access_denied(stderr: bytes) -> bool:
    """Recognize Git-for-Windows failing before Git itself can start.

    This is not a repository/authentication failure.  Git's MSYS helper can
    intermittently fail to create its signal pipe or file mapping when the
    child was launched with CREATE_NO_WINDOW.  Retry that exact startup
    failure once without the flag; preserve every other Git failure verbatim.
    """
    if os.name != "nt" or b"Win32 error 5" not in stderr:
        return False
    return any(marker in stderr for marker in (
        b"fatal error - couldn't create signal pipe",
        b"fatal error - CreateFileMapping",
    ))


def _bundle_clone_after_msys_failure(
    source: Path, args: tuple[str, ...], *, timeout_seconds: float,
    creationflags: int,
) -> subprocess.CompletedProcess[bytes] | None:
    """Clone a local repository without Git's failing MSYS upload-pack path."""
    if not args or args[0] != "clone" or "--no-local" not in args or len(args) < 3:
        return None
    clone_source = Path(args[-2])
    destination = Path(args[-1])
    if not clone_source.is_absolute():
        clone_source = (source / clone_source).resolve()
    else:
        clone_source = clone_source.resolve()
    if not clone_source.is_dir() or destination.exists() or destination.is_symlink():
        return None
    bundle = destination.with_name(destination.name + ".bundle")
    if bundle.exists() or bundle.is_symlink():
        return None
    common = ["git", "--no-optional-locks"]
    try:
        bundled = subprocess.run(
            [*common, "-C", str(clone_source), "bundle", "create", str(bundle), "--all"],
            capture_output=True, timeout=timeout_seconds, creationflags=creationflags,
        )
        if bundled.returncode:
            return bundled
        clone_args = tuple(arg for arg in args[:-2] if arg != "--no-local")
        cloned = subprocess.run(
            [*common, "-C", str(source), *clone_args, str(bundle), str(destination)],
            capture_output=True, timeout=timeout_seconds, creationflags=creationflags,
        )
        if cloned.returncode:
            return cloned
        rebound = subprocess.run(
            [*common, "-C", str(destination), "remote", "set-url", "origin", str(clone_source)],
            capture_output=True, timeout=timeout_seconds, creationflags=creationflags,
        )
        return rebound
    finally:
        if bundle.is_file():
            bundle.unlink()


def git(source: Path, *args: str, timeout_seconds: float = 30) -> bytes:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    command = ["git", "--no-optional-locks", "-C", str(source), *args]
    result = subprocess.run(
        command,
        capture_output=True, timeout=timeout_seconds, creationflags=creationflags,
    )
    if result.returncode and _msys_startup_access_denied(result.stderr):
        recovered = _bundle_clone_after_msys_failure(
            source, args, timeout_seconds=timeout_seconds, creationflags=creationflags,
        )
        if recovered is not None:
            result = recovered
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def changes(source: Path) -> list[dict]:
    # -z avoids quoting of spaces, Unicode, tabs and newlines. A rename has
    # two paths: destination first, then original. Preserve both for conflicts.
    parts = iter(git(source, "status", "--porcelain=v1", "-z",
                     "--untracked-files=all").split(b"\0"))
    result = []
    for record in parts:
        if not record:
            continue
        status = record[:2].decode("ascii")
        item = {"status": status, "path": record[3:].decode("utf-8", "surrogateescape")}
        if "R" in status or "C" in status:
            item["original_path"] = next(parts).decode("utf-8", "surrogateescape")
        result.append(item)
    return result


def resource_conflicts(task: dict, edits: list[dict]) -> list[str]:
    resources = set()
    for resource in task.get("exclusive_resources") or []:
        kind, separator, path = resource.partition(":")
        if separator and kind in {"repo-file", "unity-scene"}:
            resources.add(path.replace("\\", "/").casefold())
    return sorted({path for edit in edits
                   for path in (edit["path"], edit.get("original_path"))
                   if path and path.replace("\\", "/").casefold() in resources})


def inspect(source: Path, task_id: str | None = None) -> dict:
    source = Path(git(source, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    head = git(source, "rev-parse", "HEAD").decode().strip()
    branch = git(source, "branch", "--show-current").decode().strip() or None
    edits = changes(source)
    task_paths = git(source, "ls-tree", "-r", "--name-only", "-z", head, "--", "Tasks").split(b"\0")
    ids = sorted(Path(p.decode()).stem for p in task_paths
                 if p.startswith(b"Tasks/NSC-") and p.endswith(b".yaml")
                 and p.count(b"/") == 1)
    if task_id is not None:
        if task_id not in ids:
            raise ValueError(f"No committed task {task_id} at {head}")
        ids = [task_id]
    tasks = []
    for selected in ids:
        task = load_committed_task(source, selected, commit=head)
        item = {key: task.get(key) for key in (
            "id", "title", "kind", "contract_disposition", "depends_on",
            "parent", "exclusive_resources", "task_contract_sha256")}
        item["local_edit_conflicts"] = resource_conflicts(task, edits)
        if task_id is not None:
            item["contract"] = task
        tasks.append(item)
    return {
        "schema_version": "assistant-project-inventory/v1",
        "source": str(source), "head": head, "branch": branch,
        "head_unchanged_during_read": git(source, "rev-parse", "HEAD").decode().strip() == head,
        "local_changes": edits, "tasks": tasks,
        "limitations": [
            "Inventory only: dependency delivery, worker liveness and capacity are not assessed.",
            "Local edits are preserved; snapshots are not a lock against concurrent editing.",
            "Conflict list covers exact repo-file and unity-scene resources, not every possible file overlap.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--task", help="Exact task ID; include its complete committed contract")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.source, args.task), indent=2))
        return 0
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "inspection_failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
