"""Deterministically materialize Door Prototype Unity assets from reviewed C#.

This module owns the Unity batch-mode boundary shared by production candidate
integration and the conversation-operated AssistantControl workflow.  It does
not commit, approve, integrate, push, or launch a model provider.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Sequence


DOOR_PROTOTYPE_BUILDER = (
    "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs"
)
DOOR_PROTOTYPE_ROOT = "Assets/NoSafeCircle/DoorPrototype/"
DOOR_PROTOTYPE_SCENE = "Assets/Scenes/DoorPrototype.unity"
DOOR_PROTOTYPE_BUILD_METHOD = (
    "NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build"
)
UNITY_SERIALIZED_SUFFIXES = (
    ".asset", ".unity", ".prefab", ".mat", ".meta", ".anim", ".controller",
    ".overrideController", ".physicsMaterial2D", ".spriteatlas", ".preset",
    ".renderTexture", ".playable", ".signal", ".mask", ".guiskin", ".fontsettings",
)

_UNITY_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]*$")
UnityCommandRunner = Callable[
    [Sequence[str], Path, float], subprocess.CompletedProcess[bytes]
]


class DoorPrototypeMaterializationError(RuntimeError):
    """Unity materialization could not be authenticated or completed."""


@dataclass(frozen=True)
class DoorPrototypeMaterialization:
    changed_paths: tuple[str, ...]
    builder_paths: tuple[str, ...]
    restored_tracked_paths: tuple[str, ...]
    normalized_paths: tuple[str, ...]
    unity_executable: str
    unity_log: str


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            ("git", "-C", str(root), *args),
            cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DoorPrototypeMaterializationError(
            "materialization Git command could not run: " + " ".join(args)
        ) from exc
    if check and result.returncode:
        detail = _decode(result.stderr or result.stdout, "Git output").strip()
        raise DoorPrototypeMaterializationError(
            "materialization Git command failed: " + " ".join(args)
            + (f"\n{detail}" if detail else "")
        )
    return result


def _decode(value: bytes, label: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DoorPrototypeMaterializationError(f"{label} was not valid UTF-8") from exc


def _git_lines(root: Path, *args: str) -> tuple[str, ...]:
    output = _decode(_git(root, *args).stdout, "Git output")
    return tuple(sorted((line for line in output.splitlines() if line), key=str.casefold))


def changed_paths(root: Path) -> tuple[str, ...]:
    tracked = _git_lines(root, "diff", "--name-only", "HEAD", "--")
    untracked = _git_lines(root, "ls-files", "--others", "--exclude-standard")
    return tuple(sorted(set(tracked).union(untracked), key=str.casefold))


def is_door_prototype_builder_output(path: str) -> bool:
    return path.startswith(DOOR_PROTOTYPE_ROOT) or path == DOOR_PROTOTYPE_SCENE


def is_unity_serialized(path: str) -> bool:
    return path.casefold().endswith(tuple(s.casefold() for s in UNITY_SERIALIZED_SUFFIXES))


def normalize_unity_serialized_whitespace(
    root: Path, paths: Sequence[str],
) -> tuple[str, ...]:
    """Strip Unity-authored trailing spaces without changing line endings."""
    rewritten: list[str] = []
    for relative in paths:
        if not is_unity_serialized(relative):
            continue
        target = root / relative
        if not target.is_file():
            continue
        try:
            original = target.read_bytes()
            normalized = re.sub(rb"[ \t]+(?=\r?\n|\Z)", b"", original)
            if normalized != original:
                target.write_bytes(normalized)
                rewritten.append(relative)
        except OSError as exc:
            raise DoorPrototypeMaterializationError(
                f"could not normalize Unity serialized output: {target}"
            ) from exc
    return tuple(rewritten)


def resolve_unity_executable(
    checkout: Path, unity_executable: Path | str | None = None,
) -> Path:
    if unity_executable is not None:
        executable = Path(unity_executable).resolve()
    else:
        version_path = checkout / "ProjectSettings" / "ProjectVersion.txt"
        try:
            version_text = version_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise DoorPrototypeMaterializationError(
                f"could not read Unity version from {version_path}"
            ) from exc
        match = re.search(r"^m_EditorVersion:\s*(\S.*?)\s*$", version_text, re.MULTILINE)
        version = match.group(1) if match else ""
        if not _UNITY_VERSION.fullmatch(version):
            raise DoorPrototypeMaterializationError(
                f"ProjectVersion.txt has an invalid m_EditorVersion value: {version!r}"
            )
        program_files = os.getenv("ProgramFiles")
        if not program_files:
            raise DoorPrototypeMaterializationError(
                "ProgramFiles is unavailable for Unity Hub executable discovery"
            )
        executable = (
            Path(program_files) / "Unity" / "Hub" / "Editor" / version
            / "Editor" / "Unity.exe"
        )
    if not executable.is_file():
        raise DoorPrototypeMaterializationError(
            f"Unity executable does not exist: {executable}"
        )
    return executable


def default_unity_command_runner(
    args: Sequence[str], cwd: Path, timeout_seconds: float,
) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    return subprocess.run(
        tuple(args), cwd=str(cwd), env=environment, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False, timeout=timeout_seconds,
    )


def run_door_prototype_builder(
    *,
    checkout: Path | str,
    task_id: str,
    state_root: Path | str,
    initial_changed_paths: Sequence[str],
    unity_executable: Path | str | None = None,
    unity_command_runner: UnityCommandRunner = default_unity_command_runner,
    timeout_seconds: float = 1800.0,
    allowed_generated_paths: Sequence[str] | None = None,
    allowed_generated_roots: Sequence[str] | None = None,
) -> DoorPrototypeMaterialization:
    """Run the canonical builder and return its exact authenticated path set.

    ``initial_changed_paths`` is the already verified crew patch in production
    and is empty when AssistantControl starts from a committed code candidate.
    Supplying ``allowed_generated_paths`` narrows the normal Door Prototype
    boundary to those exact paths.
    """
    root = Path(checkout).resolve()
    evidence_root = Path(state_root).resolve()
    initial = tuple(sorted(set(initial_changed_paths), key=str.casefold))
    if tuple(initial_changed_paths) != initial:
        raise DoorPrototypeMaterializationError(
            "initial materialization paths must be sorted and unique"
        )
    if timeout_seconds <= 0:
        raise DoorPrototypeMaterializationError("Unity builder timeout must be positive")
    if changed_paths(root) != initial:
        raise DoorPrototypeMaterializationError(
            "checkout changed after candidate verification and before the DoorPrototype builder"
        )
    allowed = None
    if allowed_generated_paths is not None:
        allowed = tuple(sorted(set(allowed_generated_paths), key=str.casefold))
        if tuple(allowed_generated_paths) != allowed:
            raise DoorPrototypeMaterializationError(
                "allowed generated paths must be sorted and unique"
            )
        if any(not is_door_prototype_builder_output(path) for path in allowed):
            raise DoorPrototypeMaterializationError(
                "allowed generated path is outside the DoorPrototype builder boundary"
            )
    allowed_roots: tuple[str, ...] | None = None
    if allowed_generated_roots is not None:
        allowed_roots = tuple(sorted(set(allowed_generated_roots), key=str.casefold))
        if tuple(allowed_generated_roots) != allowed_roots:
            raise DoorPrototypeMaterializationError(
                "allowed generated roots must be sorted and unique"
            )
        for root_path in allowed_roots:
            parts = PurePosixPath(root_path).parts
            if (
                not root_path.startswith(DOOR_PROTOTYPE_ROOT)
                or root_path == DOOR_PROTOTYPE_ROOT.rstrip("/")
                or root_path.endswith("/")
                or "\\" in root_path
                or any(part in {"", ".", ".."} for part in parts)
            ):
                raise DoorPrototypeMaterializationError(
                    "allowed generated root is outside the DoorPrototype builder boundary"
                )
    if ((allowed_generated_paths is not None or allowed_generated_roots is not None)
            and not allowed and not allowed_roots):
        raise DoorPrototypeMaterializationError(
            "allowed generated authority must contain at least one path or root"
        )

    executable = resolve_unity_executable(root, unity_executable)
    evidence_root.mkdir(parents=True, exist_ok=True)
    log_directory = Path(tempfile.mkdtemp(
        prefix=f"{task_id.casefold()}-unity-builder-", dir=evidence_root,
    ))
    log_path = log_directory / "unity.log"
    command = (
        str(executable), "-batchmode", "-quit", "-projectPath", str(root),
        "-executeMethod", DOOR_PROTOTYPE_BUILD_METHOD, "-logFile", str(log_path),
    )
    ilpp_pid_path = root / "Library" / "ilpp.pid"
    try:
        ilpp_pid_path.unlink(missing_ok=True)
        if os.path.lexists(ilpp_pid_path):
            raise OSError("the path still exists after deletion")
    except OSError as exc:
        raise DoorPrototypeMaterializationError(
            "DoorPrototype builder refused to launch because the stale Unity ILPP "
            f"PID marker could not be removed: {ilpp_pid_path}"
        ) from exc
    try:
        result = unity_command_runner(command, root, timeout_seconds)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DoorPrototypeMaterializationError(
            f"DoorPrototype builder could not run; Unity log: {log_path}"
        ) from exc
    if result.returncode:
        stdout = _decode(result.stdout or b"", "Unity stdout").strip()
        stderr = _decode(result.stderr or b"", "Unity stderr").strip()
        detail = "\n".join(item for item in (stdout, stderr) if item)
        raise DoorPrototypeMaterializationError(
            f"DoorPrototype builder failed ({result.returncode}); Unity log: {log_path}"
            + (f"\n{detail}" if detail else "")
        )

    tracked = _git_lines(root, "diff", "--name-only", "HEAD", "--")
    untracked = _git_lines(root, "ls-files", "--others", "--exclude-standard")
    initial_set = set(initial)

    def permitted(path: str) -> bool:
        if allowed is None and allowed_roots is None:
            return is_door_prototype_builder_output(path)
        if allowed is not None and path in allowed:
            return True
        if allowed_roots is None or not is_unity_serialized(path):
            return False
        folded = path.casefold()
        return any(folded.startswith(root.casefold() + "/") for root in allowed_roots)

    incidental_tracked = tuple(
        path for path in tracked if path not in initial_set and not permitted(path)
    )
    if incidental_tracked:
        _git(root, "restore", "--source=HEAD", "--staged", "--worktree", "--",
             *incidental_tracked)
    incidental_untracked = tuple(
        path for path in untracked if path not in initial_set and not permitted(path)
    )
    if incidental_untracked:
        raise DoorPrototypeMaterializationError(
            "Unity created untracked paths outside the DoorPrototype builder-owned "
            f"boundary: {incidental_untracked}"
        )
    post_unity = set(tracked).union(untracked)
    builder_paths = tuple(sorted(
        (path for path in post_unity.difference(initial_set) if permitted(path)),
        key=str.casefold,
    ))
    expected = tuple(sorted(initial_set.union(builder_paths), key=str.casefold))
    remaining = changed_paths(root)
    if remaining != expected:
        raise DoorPrototypeMaterializationError(
            "dirty paths after Unity cleanup differ from candidate plus DoorPrototype "
            f"builder output: {remaining} != {expected}"
        )
    normalized = normalize_unity_serialized_whitespace(root, expected)
    if changed_paths(root) != expected:
        raise DoorPrototypeMaterializationError(
            "Unity output paths changed during serialized whitespace normalization"
        )
    return DoorPrototypeMaterialization(
        changed_paths=expected, builder_paths=builder_paths,
        restored_tracked_paths=incidental_tracked, normalized_paths=normalized,
        unity_executable=str(executable), unity_log=str(log_path),
    )


__all__ = [
    "DOOR_PROTOTYPE_BUILDER", "DOOR_PROTOTYPE_BUILD_METHOD",
    "DoorPrototypeMaterialization", "DoorPrototypeMaterializationError",
    "UnityCommandRunner", "changed_paths", "default_unity_command_runner",
    "is_door_prototype_builder_output", "is_unity_serialized",
    "normalize_unity_serialized_whitespace", "resolve_unity_executable",
    "run_door_prototype_builder",
]
