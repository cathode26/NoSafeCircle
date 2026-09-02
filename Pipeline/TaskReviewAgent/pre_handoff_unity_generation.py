"""Deterministic DoorPrototype Unity generation before a human handoff."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

from .contracts import TaskReviewContractError


DOOR_PROTOTYPE_BUILDER_PATH = (
    "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs"
)
DOOR_PROTOTYPE_BUILDER_METHOD = (
    "NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build"
)
DOOR_PROTOTYPE_SCENE_PATH = "Assets/Scenes/DoorPrototype.unity"
DOOR_PROTOTYPE_GENERATED_PREFIX = "Assets/NoSafeCircle/DoorPrototype/Generated/"
RESOURCE_PREFIXES = ("repo-file:", "unity-scene:")
_UNITY_VERSION = re.compile(r"^m_EditorVersion:\s*(\S+)\s*$", re.MULTILINE)


class PreHandoffUnityGenerationError(TaskReviewContractError):
    """Raised when builder generation cannot produce an authorized clean tree."""


CommandRunner = Callable[
    [Sequence[str], Path, float], subprocess.CompletedProcess[bytes]
]


@dataclass(frozen=True)
class PreHandoffUnityGenerationResult:
    builder_required: bool
    builder_ran: bool
    builder_method: str | None
    unity_executable: str | None
    log_path: str | None
    snapshot_path: str | None
    generated_changed_paths: tuple[str, ...]
    changed_paths: tuple[str, ...]


def _normalized_paths(values: Iterable[str]) -> tuple[str, ...]:
    result: set[str] = set()
    for value in values:
        if type(value) is not str:
            raise PreHandoffUnityGenerationError("path authority must contain strings")
        text = value.strip().replace("\\", "/")
        path = PurePosixPath(text)
        if not text or path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
            raise PreHandoffUnityGenerationError(
                f"invalid repository-relative generation path: {value!r}"
            )
        result.add(text)
    return tuple(sorted(result, key=str.casefold))


def task_resource_paths(task: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for resource in task.get("exclusive_resources") or []:
        if type(resource) is not str:
            continue
        for prefix in RESOURCE_PREFIXES:
            if resource.startswith(prefix):
                values.append(resource[len(prefix) :])
                break
    return _normalized_paths(values)


def door_prototype_builder_required(
    *,
    task: Mapping[str, Any],
    candidate_changed_paths: Iterable[str],
    accepted_changed_paths: Iterable[str] = (),
) -> bool:
    involved_paths = set(_normalized_paths(candidate_changed_paths)) | set(
        _normalized_paths(accepted_changed_paths)
    )
    if DOOR_PROTOTYPE_BUILDER_PATH not in involved_paths:
        return False
    resources = set(task_resource_paths(task))
    return any(
        path == DOOR_PROTOTYPE_SCENE_PATH
        or path.startswith(DOOR_PROTOTYPE_GENERATED_PREFIX)
        for path in resources
    )


def accepted_scope_paths(scope: Any) -> tuple[str, ...]:
    accepted = getattr(scope, "accepted", None)
    plan = getattr(accepted, "plan", None)
    if plan is None:
        return ()
    return _normalized_paths(
        (
            *plan.existing_implementation_paths,
            *plan.new_implementation_paths,
            *plan.existing_test_paths,
            *plan.new_test_paths,
        )
    )


def discover_unity_executable(
    project_path: Path | str,
    explicit: Path | str | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Use the same project-version/Unity Hub lookup as run_unity_tests_clean.ps1."""

    if explicit is not None and str(explicit).strip():
        executable = Path(str(explicit).strip()).expanduser()
    else:
        project = Path(project_path).resolve()
        version_path = project / "ProjectSettings" / "ProjectVersion.txt"
        try:
            version_text = version_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise PreHandoffUnityGenerationError(
                f"could not read Unity project version: {version_path}"
            ) from exc
        match = _UNITY_VERSION.search(version_text)
        if match is None:
            raise PreHandoffUnityGenerationError(
                f"could not read m_EditorVersion from {version_path}"
            )
        variables = os.environ if environment is None else environment
        program_files = variables.get("ProgramFiles") or variables.get("PROGRAMFILES")
        if not program_files:
            raise PreHandoffUnityGenerationError(
                "default Unity discovery requires the Windows ProgramFiles environment"
            )
        executable = (
            Path(program_files)
            / "Unity"
            / "Hub"
            / "Editor"
            / match.group(1)
            / "Editor"
            / "Unity.exe"
        )
    if not executable.is_file():
        raise PreHandoffUnityGenerationError(
            f"Unity executable does not exist: {executable}"
        )
    return executable.resolve()


def _decode(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


def _default_command_runner(
    command: Sequence[str],
    cwd: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    try:
        return subprocess.run(
            tuple(command),
            cwd=str(cwd),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreHandoffUnityGenerationError(
            f"pre-handoff command could not run: {' '.join(command)}"
        ) from exc


def _run_checked(
    runner: CommandRunner,
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    label: str,
) -> subprocess.CompletedProcess[bytes]:
    completed = runner(tuple(command), cwd, timeout_seconds)
    if completed.returncode != 0:
        detail = "\n".join(
            value.strip()
            for value in (_decode(completed.stdout), _decode(completed.stderr))
            if value.strip()
        )
        raise PreHandoffUnityGenerationError(
            f"{label} failed ({completed.returncode})"
            + (f"\n{detail}" if detail else "")
        )
    return completed


def _git_text(root: Path, *args: str) -> str:
    completed = _default_command_runner(("git", "-C", str(root), *args), root, 180.0)
    if completed.returncode != 0:
        raise PreHandoffUnityGenerationError(
            f"Git inspection failed: git -C {root} {' '.join(args)}\n"
            f"{_decode(completed.stderr).strip()}"
        )
    return _decode(completed.stdout).strip()


def working_changed_paths(root: Path) -> tuple[str, ...]:
    tracked = _git_text(root, "diff", "--name-only", "--").splitlines()
    untracked = _git_text(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return _normalized_paths((*tracked, *untracked))


def _outside_repository(checkout: Path, output_root: Path) -> None:
    try:
        output_root.resolve().relative_to(checkout.resolve())
    except ValueError:
        return
    raise PreHandoffUnityGenerationError(
        "pre-handoff Unity artifacts must live outside the task checkout"
    )


class PreHandoffUnityGenerator:
    """Snapshot, build, clean, and authorize one DoorPrototype workspace."""

    def __init__(
        self,
        *,
        checkout: Path | str,
        task_id: str,
        task: Mapping[str, Any],
        scope: Any,
        unity_executable: Path | str | None = None,
        output_root: Path | str | None = None,
        unity_command_runner: CommandRunner | None = None,
        hygiene_command_runner: CommandRunner | None = None,
        unity_environment: Mapping[str, str] | None = None,
    ) -> None:
        self.checkout = Path(checkout).resolve()
        self.task_id = str(task_id).strip()
        self.task = dict(task)
        self.scope = scope
        self.unity_executable = unity_executable
        self.output_root = Path(
            output_root or (self.checkout.parent / ".task-review-agent" / "unity-generation")
        ).resolve()
        self.unity_command_runner = unity_command_runner or _default_command_runner
        self.hygiene_command_runner = hygiene_command_runner or _default_command_runner
        self.unity_environment = unity_environment

    def run(self, candidate_changed_paths: Iterable[str]) -> PreHandoffUnityGenerationResult:
        candidate_paths = _normalized_paths(candidate_changed_paths)
        required = door_prototype_builder_required(
            task=self.task,
            candidate_changed_paths=candidate_paths,
            accepted_changed_paths=accepted_scope_paths(self.scope),
        )
        if not required:
            return PreHandoffUnityGenerationResult(
                builder_required=False,
                builder_ran=False,
                builder_method=None,
                unity_executable=None,
                log_path=None,
                snapshot_path=None,
                generated_changed_paths=(),
                changed_paths=candidate_paths,
            )

        executable = discover_unity_executable(
            self.checkout,
            self.unity_executable,
            environment=self.unity_environment,
        )
        _outside_repository(self.checkout, self.output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        artifact = Path(
            tempfile.mkdtemp(
                prefix=f"{self.task_id.casefold()}-door-prototype-",
                dir=str(self.output_root),
            )
        )
        snapshot_path = artifact / "workspace-snapshot.json"
        log_path = artifact / "unity-builder.log"
        hygiene_script = self.checkout / "Pipeline" / "Testing" / "unity_workspace_hygiene.py"
        if not hygiene_script.is_file():
            raise PreHandoffUnityGenerationError(
                f"task checkout is missing workspace hygiene helper: {hygiene_script}"
            )

        preserve = accepted_scope_paths(self.scope)
        snapshot_command: list[str] = [
            sys.executable,
            str(hygiene_script),
            "--repo",
            str(self.checkout),
            "snapshot",
            "--task-id",
            self.task_id,
            "--output",
            str(snapshot_path),
        ]
        for path in preserve:
            snapshot_command.extend(("--preserve", path))
        _run_checked(
            self.hygiene_command_runner,
            snapshot_command,
            cwd=self.checkout,
            timeout_seconds=300.0,
            label="Unity workspace snapshot",
        )

        unity_command = (
            str(executable),
            "-batchmode",
            "-quit",
            "-projectPath",
            str(self.checkout),
            "-executeMethod",
            DOOR_PROTOTYPE_BUILDER_METHOD,
            "-logFile",
            str(log_path),
        )
        try:
            _run_checked(
                self.unity_command_runner,
                unity_command,
                cwd=self.checkout,
                timeout_seconds=1800.0,
                label=f"Unity builder {DOOR_PROTOTYPE_BUILDER_METHOD}; log: {log_path}",
            )
        except PreHandoffUnityGenerationError as exc:
            raise PreHandoffUnityGenerationError(
                f"pre-handoff Unity generation stopped before commit/push/handoff: {exc}"
            ) from exc

        inspect_command = (
            sys.executable,
            str(hygiene_script),
            "--repo",
            str(self.checkout),
            "inspect",
            "--snapshot",
            str(snapshot_path),
        )
        _run_checked(
            self.hygiene_command_runner,
            inspect_command,
            cwd=self.checkout,
            timeout_seconds=300.0,
            label="post-builder Unity workspace inspection",
        )
        clean_command = (
            sys.executable,
            str(hygiene_script),
            "--repo",
            str(self.checkout),
            "clean",
            "--snapshot",
            str(snapshot_path),
            "--normalize-preserved-unity-eol",
        )
        _run_checked(
            self.hygiene_command_runner,
            clean_command,
            cwd=self.checkout,
            timeout_seconds=300.0,
            label="post-builder Unity workspace cleanup",
        )

        final_paths = working_changed_paths(self.checkout)
        candidate_set = set(candidate_paths)
        final_set = set(final_paths)
        missing_candidate = sorted(candidate_set - final_set, key=str.casefold)
        if missing_candidate:
            raise PreHandoffUnityGenerationError(
                "Unity generation removed verified candidate paths: "
                + ", ".join(missing_candidate)
            )
        generated_paths = tuple(sorted(final_set - candidate_set, key=str.casefold))
        authorized = set(task_resource_paths(self.task)) | set(preserve)
        unauthorized = sorted(set(generated_paths) - authorized, key=str.casefold)
        if unauthorized:
            raise PreHandoffUnityGenerationError(
                "Unity generation produced paths without task resource or accepted-scope authority: "
                + ", ".join(unauthorized)
            )
        expected_final = tuple(sorted(candidate_set | set(generated_paths), key=str.casefold))
        if final_paths != expected_final:
            raise PreHandoffUnityGenerationError(
                "post-builder path union did not match the inspected workspace"
            )
        return PreHandoffUnityGenerationResult(
            builder_required=True,
            builder_ran=True,
            builder_method=DOOR_PROTOTYPE_BUILDER_METHOD,
            unity_executable=str(executable),
            log_path=str(log_path),
            snapshot_path=str(snapshot_path),
            generated_changed_paths=generated_paths,
            changed_paths=final_paths,
        )


__all__ = (
    "DOOR_PROTOTYPE_BUILDER_METHOD",
    "DOOR_PROTOTYPE_BUILDER_PATH",
    "PreHandoffUnityGenerationError",
    "PreHandoffUnityGenerationResult",
    "PreHandoffUnityGenerator",
    "accepted_scope_paths",
    "discover_unity_executable",
    "door_prototype_builder_required",
    "task_resource_paths",
    "working_changed_paths",
)
