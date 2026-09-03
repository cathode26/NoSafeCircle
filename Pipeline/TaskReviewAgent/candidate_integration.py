"""Verify, apply, commit, and push one review-ready ExecutionCrew candidate."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from .contracts import TaskReviewContractError, semantic_sha256
from .execution_bridge import ExecutionCrewBridge, ExecutionCrewReceipt
from .pipeline_scope import RepositoryScopeAuthority
from Pipeline.Testing.validation_manifest import (
    ValidationManifestError,
    load_validation_manifest,
)


INTEGRATION_SCHEMA_VERSION = "1.1"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_UNITY_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]*$")
_DOOR_PROTOTYPE_BUILDER = (
    "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs"
)
_DOOR_PROTOTYPE_ROOT = "Assets/NoSafeCircle/DoorPrototype/"
_DOOR_PROTOTYPE_SCENE = "Assets/Scenes/DoorPrototype.unity"
_DOOR_PROTOTYPE_BUILD_METHOD = (
    "NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build"
)


UnityCommandRunner = Callable[
    [Sequence[str], Path, float], subprocess.CompletedProcess[bytes]
]


class CandidateIntegrationError(TaskReviewContractError):
    """Raised when a review-ready candidate cannot become a durable task commit."""


def _decode(data: bytes, *, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CandidateIntegrationError(f"{label} was not valid UTF-8") from exc


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout_seconds: float = 600.0,
) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    try:
        result = subprocess.run(
            tuple(args),
            cwd=str(cwd),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CandidateIntegrationError(
            f"candidate integration command could not run: {' '.join(args)}"
        ) from exc
    if check and result.returncode != 0:
        stdout = _decode(result.stdout or b"", label="stdout").strip()
        stderr = _decode(result.stderr or b"", label="stderr").strip()
        detail = "\n".join(item for item in (stdout, stderr) if item)
        raise CandidateIntegrationError(
            f"candidate integration command failed ({result.returncode}): {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return _run(("git", "-C", str(root), *args), cwd=root, check=check)


def _git_text(root: Path, *args: str, check: bool = True) -> str:
    return _decode(_git(root, *args, check=check).stdout, label="git stdout").strip()


def _tracked_changed_paths(root: Path) -> tuple[str, ...]:
    output = _git_text(root, "diff", "--name-only", "HEAD", "--")
    return tuple(sorted((line for line in output.splitlines() if line), key=str.casefold))


def _untracked_paths(root: Path) -> tuple[str, ...]:
    output = _git_text(root, "ls-files", "--others", "--exclude-standard")
    return tuple(sorted((line for line in output.splitlines() if line), key=str.casefold))


def _changed_paths(root: Path, *, base: str | None = None) -> tuple[str, ...]:
    tracked = _git_text(
        root,
        "diff",
        "--name-only",
        f"{base}..HEAD" if base is not None else "HEAD",
        "--",
    )
    untracked = "" if base is not None else _git_text(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
    )
    values = {line for line in (*tracked.splitlines(), *untracked.splitlines()) if line}
    return tuple(sorted(values, key=str.casefold))


def _is_door_prototype_builder_output(path: str) -> bool:
    return path.startswith(_DOOR_PROTOTYPE_ROOT) or path == _DOOR_PROTOTYPE_SCENE


def _remote_head(root: Path, branch: str) -> str | None:
    output = _git_text(
        root,
        "ls-remote",
        "--heads",
        "origin",
        f"refs/heads/{branch}",
        check=False,
    )
    parts = output.split()
    return parts[0] if parts else None


@dataclass(frozen=True)
class CandidateIntegrationReceipt:
    task_id: str
    lease_id: str
    plan_id: str
    run_id: str
    provider: str
    branch: str
    base_head: str
    commit: str
    commit_tree: str
    task_contract_sha256: str
    candidate_sha256: str
    changed_paths: tuple[str, ...]
    pre_handoff_validations: tuple[dict[str, Any], ...]
    completed_checks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": INTEGRATION_SCHEMA_VERSION,
            "task_id": self.task_id,
            "lease_id": self.lease_id,
            "plan_id": self.plan_id,
            "run_id": self.run_id,
            "provider": self.provider,
            "branch": self.branch,
            "base_head": self.base_head,
            "commit": self.commit,
            "commit_tree": self.commit_tree,
            "task_contract_sha256": self.task_contract_sha256,
            "candidate_sha256": self.candidate_sha256,
            "changed_paths": list(self.changed_paths),
            "pre_handoff_validations": [
                dict(item) for item in self.pre_handoff_validations
            ],
            "completed_checks": list(self.completed_checks),
        }


class CandidateIntegrator:
    """Keep candidate review authority separate from commit/push verification."""

    def __init__(
        self,
        *,
        checkout: Path | str,
        branch: str,
        task_title: str,
        scope: RepositoryScopeAuthority,
        execution: ExecutionCrewBridge,
        unity_command_runner: UnityCommandRunner | None = None,
        unity_executable: Path | str | None = None,
        unity_timeout_seconds: float = 1800.0,
    ) -> None:
        self.checkout = Path(checkout).resolve()
        self.branch = str(branch).strip()
        self.task_title = str(task_title).strip()
        self.scope = scope
        self.execution = execution
        self.unity_command_runner = unity_command_runner or self._default_unity_command_runner
        self.unity_executable = (
            Path(unity_executable).resolve() if unity_executable is not None else None
        )
        self.unity_timeout_seconds = float(unity_timeout_seconds)
        if not self.branch or not self.task_title:
            raise CandidateIntegrationError("integration requires branch and task title")
        if self.unity_timeout_seconds <= 0:
            raise CandidateIntegrationError("Unity builder timeout must be positive")
        self.state_root = self.checkout.parent / ".task-review-agent"
        self.state_path = self.state_root / f"{self.scope.task_id}.integration.json"
        self._receipt: CandidateIntegrationReceipt | None = None
        self._load_current()

    @property
    def receipt(self) -> CandidateIntegrationReceipt | None:
        return self._receipt

    def integrate(self, run_id: str) -> CandidateIntegrationReceipt:
        execution = self.execution.require(run_id)
        if execution.crew_status != "review_ready":
            raise CandidateIntegrationError(
                f"only review_ready ExecutionCrew output can be integrated; found {execution.crew_status}"
            )
        if execution.candidate_path is None or execution.candidate_sha256 is None:
            raise CandidateIntegrationError("review_ready receipt omitted candidate identity")
        if not execution.final_actual_changed_paths:
            raise CandidateIntegrationError("review_ready candidate has no changed paths")
        if self._receipt is not None:
            self._verify_receipt(self._receipt, execution)
            return self._receipt

        existing_commit = self._existing_commit_for_run(execution)
        if existing_commit is not None:
            commit, integration_base = existing_commit
            validations = self._run_pre_handoff_validations(commit, execution)
            self._push_exact(
                commit,
                allowed_remote_heads=(execution.source_head, integration_base),
            )
            receipt = self._create_receipt(
                commit,
                execution,
                integration_base=integration_base,
                pre_handoff_validations=validations,
            )
            self._persist(receipt)
            self._receipt = receipt
            return receipt

        self._assert_checkout_identity(execution)
        candidate = Path(execution.candidate_path)
        integration_base = self._prepare_current_main_base(candidate, execution)
        self._apply_candidate(self.checkout, candidate, execution)
        try:
            self._verify_applied_state(self.checkout, execution)
            final_changed_paths = execution.final_actual_changed_paths
            if self._requires_door_prototype_builder(execution):
                final_changed_paths = self._run_door_prototype_builder(execution)
                self._normalize_door_prototype_scene(final_changed_paths)
                self._verify_applied_state(
                    self.checkout,
                    execution,
                    expected_paths=final_changed_paths,
                )
            _git(self.checkout, "add", "--", *final_changed_paths)
            staged_lines = _git_text(
                self.checkout,
                "diff",
                "--cached",
                "--name-only",
                "--",
            ).splitlines()
            staged = tuple(sorted((line for line in staged_lines if line), key=str.casefold))
            if staged != final_changed_paths:
                raise CandidateIntegrationError(
                    f"staged paths differ from verified integration paths: {staged} != "
                    f"{final_changed_paths}"
                )
            if _git_text(self.checkout, "diff", "--name-only", "--"):
                raise CandidateIntegrationError("candidate left unstaged tracked changes")
            if _git_text(
                self.checkout,
                "ls-files",
                "--others",
                "--exclude-standard",
            ):
                raise CandidateIntegrationError("candidate left unstaged untracked files")

            self._ensure_git_identity()
            message = f"Implement {self.scope.task_id}: {self.task_title}"
            body = (
                f"ExecutionCrew-Run: {execution.run_id}\n"
                f"ExecutionCrew-Candidate-SHA256: {execution.candidate_sha256}\n"
                f"Task-Contract-SHA256: {execution.task_contract_sha256}\n"
            )
            _git(self.checkout, "commit", "-m", message, "-m", body)
        except Exception as exc:
            raise CandidateIntegrationError(
                "candidate application reached the canonical checkout but could not be "
                "committed. Stop and reconcile this isolated task checkout before retrying: "
                f"{exc}"
            ) from exc

        commit = _git_text(self.checkout, "rev-parse", "HEAD")
        if not _SHA40.fullmatch(commit):
            raise CandidateIntegrationError("Git commit returned an invalid identity")
        parent = _git_text(self.checkout, "rev-parse", "HEAD^")
        if parent != integration_base:
            raise CandidateIntegrationError(
                "candidate commit parent is not the verified pre-handoff main head"
            )
        if _changed_paths(self.checkout, base=integration_base) != final_changed_paths:
            raise CandidateIntegrationError("candidate commit changed an unexpected path set")
        validations = self._run_pre_handoff_validations(commit, execution)
        self._push_exact(
            commit,
            allowed_remote_heads=(execution.source_head, integration_base),
        )
        receipt = self._create_receipt(
            commit,
            execution,
            integration_base=integration_base,
            pre_handoff_validations=validations,
        )
        self._persist(receipt)
        self._receipt = receipt
        return receipt

    def _assert_checkout_identity(self, execution: ExecutionCrewReceipt) -> None:
        top = _git_text(self.checkout, "rev-parse", "--show-toplevel", check=False)
        if not top or Path(top).resolve() != self.checkout:
            raise CandidateIntegrationError("integration checkout is not its standalone Git root")
        branch = _git_text(self.checkout, "branch", "--show-current", check=False)
        if branch != self.branch:
            raise CandidateIntegrationError(
                f"integration branch {branch!r} differs from workflow branch {self.branch!r}"
            )
        head = _git_text(self.checkout, "rev-parse", "HEAD", check=False)
        if head != execution.source_head:
            raise CandidateIntegrationError(
                f"integration checkout HEAD {head!r} differs from ExecutionCrew source "
                f"{execution.source_head!r}"
            )
        status = _git_text(
            self.checkout,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        if status:
            raise CandidateIntegrationError("integration requires a clean task checkout")

    def _existing_commit_for_run(
        self,
        execution: ExecutionCrewReceipt,
    ) -> tuple[str, str] | None:
        head = _git_text(self.checkout, "rev-parse", "HEAD", check=False)
        if head == execution.source_head:
            return None
        status = _git_text(
            self.checkout,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        if status:
            return None
        message = _git_text(self.checkout, "show", "-s", "--format=%B", "HEAD", check=False)
        if f"ExecutionCrew-Run: {execution.run_id}" not in message:
            return None
        parent = _git_text(self.checkout, "rev-parse", "HEAD^", check=False)
        if not parent or (
            _git(
                self.checkout,
                "merge-base",
                "--is-ancestor",
                execution.source_head,
                parent,
                check=False,
            ).returncode
            != 0
        ):
            raise CandidateIntegrationError(
                "existing integration commit is not based on the ExecutionCrew source"
            )
        self._assert_contract_identity(parent, execution)
        changed_paths = _changed_paths(self.checkout, base=parent)
        if not self._paths_match_execution(changed_paths, execution):
            raise CandidateIntegrationError("existing integration commit has the wrong path set")
        return head, parent

    def _assert_contract_identity(
        self,
        commit: str,
        execution: ExecutionCrewReceipt,
    ) -> None:
        contract_path = str(
            self.scope.task.get("contract_path")
            or f"Tasks/{self.scope.task_id}.yaml"
        )
        contract = _git(
            self.checkout,
            "show",
            f"{commit}:{contract_path}",
            check=False,
        )
        if (
            contract.returncode != 0
            or hashlib.sha256(contract.stdout).hexdigest()
            != execution.task_contract_sha256
        ):
            raise CandidateIntegrationError(
                "current main changed the task-contract identity; rerun task planning"
            )

    def _prepare_current_main_base(
        self,
        candidate: Path,
        execution: ExecutionCrewReceipt,
    ) -> str:
        """Refresh main before the first human handoff and rebase the patch safely."""

        _git(
            self.checkout,
            "fetch",
            "origin",
            "+refs/heads/main:refs/remotes/origin/main",
        )
        main_head = _git_text(self.checkout, "rev-parse", "origin/main")
        if not _SHA40.fullmatch(main_head):
            raise CandidateIntegrationError("origin/main did not resolve to a commit")
        if (
            _git(
                self.checkout,
                "merge-base",
                "--is-ancestor",
                execution.source_head,
                main_head,
                check=False,
            ).returncode
            != 0
        ):
            raise CandidateIntegrationError(
                "current main is not descended from the ExecutionCrew source; "
                "manual history reconciliation is required"
            )
        self._assert_contract_identity(main_head, execution)
        self._validate_in_disposable_clone(
            candidate,
            execution,
            base_head=main_head,
        )
        if main_head != execution.source_head:
            _git(self.checkout, "merge", "--ff-only", main_head)
        if _git_text(self.checkout, "rev-parse", "HEAD") != main_head:
            raise CandidateIntegrationError(
                "task branch did not reach the verified pre-handoff main head"
            )
        return main_head

    @staticmethod
    def _apply_candidate(
        root: Path,
        candidate: Path,
        execution: ExecutionCrewReceipt,
    ) -> None:
        _git(root, "apply", "--3way", "--", str(candidate))
        _git(
            root,
            "restore",
            "--staged",
            "--",
            *execution.final_actual_changed_paths,
        )

    @staticmethod
    def _requires_door_prototype_builder(execution: ExecutionCrewReceipt) -> bool:
        return _DOOR_PROTOTYPE_BUILDER in execution.final_actual_changed_paths

    def _paths_match_execution(
        self,
        changed_paths: tuple[str, ...],
        execution: ExecutionCrewReceipt,
    ) -> bool:
        candidate_paths = execution.final_actual_changed_paths
        if not self._requires_door_prototype_builder(execution):
            return changed_paths == candidate_paths
        if tuple(sorted(set(changed_paths), key=str.casefold)) != changed_paths:
            return False
        candidate_set = set(candidate_paths)
        changed_set = set(changed_paths)
        return candidate_set.issubset(changed_set) and all(
            path in candidate_set or _is_door_prototype_builder_output(path)
            for path in changed_paths
        )

    def _run_door_prototype_builder(
        self,
        execution: ExecutionCrewReceipt,
    ) -> tuple[str, ...]:
        executable = self._resolve_unity_executable()
        self.state_root.mkdir(parents=True, exist_ok=True)
        log_directory = Path(
            tempfile.mkdtemp(
                prefix=f"{self.scope.task_id.casefold()}-unity-builder-",
                dir=self.state_root,
            )
        )
        log_path = log_directory / "unity.log"
        candidate_paths = _changed_paths(self.checkout)
        if candidate_paths != execution.final_actual_changed_paths:
            raise CandidateIntegrationError(
                "canonical checkout changed after candidate verification and before the "
                "DoorPrototype builder"
            )
        command = (
            str(executable),
            "-batchmode",
            "-quit",
            "-projectPath",
            str(self.checkout),
            "-executeMethod",
            _DOOR_PROTOTYPE_BUILD_METHOD,
            "-logFile",
            str(log_path),
        )
        try:
            result = self.unity_command_runner(
                command,
                self.checkout,
                self.unity_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CandidateIntegrationError(
                f"DoorPrototype builder could not run; Unity log: {log_path}"
            ) from exc
        if result.returncode != 0:
            stdout = _decode(result.stdout or b"", label="Unity stdout").strip()
            stderr = _decode(result.stderr or b"", label="Unity stderr").strip()
            detail = "\n".join(item for item in (stdout, stderr) if item)
            raise CandidateIntegrationError(
                f"DoorPrototype builder failed ({result.returncode}); Unity log: {log_path}"
                + (f"\n{detail}" if detail else "")
            )

        tracked_paths = _tracked_changed_paths(self.checkout)
        untracked_paths = _untracked_paths(self.checkout)
        candidate_set = set(candidate_paths)
        incidental_tracked = tuple(
            path
            for path in tracked_paths
            if path not in candidate_set and not _is_door_prototype_builder_output(path)
        )
        if incidental_tracked:
            _git(
                self.checkout,
                "restore",
                "--source=HEAD",
                "--staged",
                "--worktree",
                "--",
                *incidental_tracked,
            )

        incidental_untracked = tuple(
            path
            for path in untracked_paths
            if path not in candidate_set and not _is_door_prototype_builder_output(path)
        )
        if incidental_untracked:
            raise CandidateIntegrationError(
                "Unity created untracked paths outside the DoorPrototype builder-owned "
                f"boundary: {incidental_untracked}"
            )

        post_unity_paths = set(tracked_paths).union(untracked_paths)
        builder_paths = {
            path
            for path in post_unity_paths.difference(candidate_set)
            if _is_door_prototype_builder_output(path)
        }
        expected_paths = tuple(sorted(candidate_set.union(builder_paths), key=str.casefold))
        remaining_paths = _changed_paths(self.checkout)
        if remaining_paths != expected_paths:
            raise CandidateIntegrationError(
                "dirty paths after Unity cleanup differ from candidate plus DoorPrototype "
                f"builder output: {remaining_paths} != {expected_paths}"
            )
        return expected_paths

    def _normalize_door_prototype_scene(
        self,
        changed_paths: tuple[str, ...],
    ) -> None:
        """Remove builder-generated trailing space/tab without changing line endings."""

        if _DOOR_PROTOTYPE_SCENE not in changed_paths:
            return
        scene = self.checkout / _DOOR_PROTOTYPE_SCENE
        try:
            original = scene.read_bytes()
            normalized = re.sub(rb"[ \t]+(?=\r?\n|\Z)", b"", original)
            if normalized != original:
                scene.write_bytes(normalized)
        except OSError as exc:
            raise CandidateIntegrationError(
                f"could not normalize DoorPrototype scene output: {scene}"
            ) from exc

    def _resolve_unity_executable(self) -> Path:
        if self.unity_executable is not None:
            executable = self.unity_executable
        else:
            version_path = self.checkout / "ProjectSettings" / "ProjectVersion.txt"
            try:
                version_text = version_path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as exc:
                raise CandidateIntegrationError(
                    f"could not read Unity version from {version_path}"
                ) from exc
            match = re.search(r"^m_EditorVersion:\s*(\S.*?)\s*$", version_text, re.MULTILINE)
            version = match.group(1) if match else ""
            if not _UNITY_VERSION.fullmatch(version):
                raise CandidateIntegrationError(
                    f"ProjectVersion.txt has an invalid m_EditorVersion value: {version!r}"
                )
            program_files = os.getenv("ProgramFiles")
            if not program_files:
                raise CandidateIntegrationError(
                    "ProgramFiles is unavailable for Unity Hub executable discovery"
                )
            executable = (
                Path(program_files)
                / "Unity"
                / "Hub"
                / "Editor"
                / version
                / "Editor"
                / "Unity.exe"
            )
        if not executable.is_file():
            raise CandidateIntegrationError(f"Unity executable does not exist: {executable}")
        return executable

    @staticmethod
    def _default_unity_command_runner(
        args: Sequence[str],
        cwd: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[bytes]:
        return _run(
            args,
            cwd=cwd,
            check=False,
            timeout_seconds=timeout_seconds,
        )

    def _run_pre_handoff_validations(
        self,
        commit: str,
        execution: ExecutionCrewReceipt,
    ) -> tuple[dict[str, Any], ...]:
        """Run committed task-specific Unity checks before publishing the handoff."""

        plan = self._pre_handoff_validation_plan()
        if plan is None:
            return ()

        if _git_text(self.checkout, "rev-parse", "HEAD") != commit:
            raise CandidateIntegrationError(
                "pre-handoff validation commit is not the checked-out task head"
            )
        if _git_text(
            self.checkout,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            raise CandidateIntegrationError(
                "pre-handoff authoritative validation requires a clean task checkout"
            )
        tree = _git_text(self.checkout, "rev-parse", "HEAD^{tree}")
        script = self.checkout / "Pipeline" / "Testing" / "run_unity_tests_clean.ps1"
        if not script.is_file():
            raise CandidateIntegrationError("clean Unity test runner is missing")

        validation_root = (
            self.state_root
            / "outputs"
            / self.scope.task_id
            / execution.run_id
            / "pre-handoff-validation"
        )
        facts: list[dict[str, Any]] = []
        for platform in plan["required_test_platforms"]:
            test_filter = plan["test_filters"][platform]
            destination = validation_root / (
                f"{platform}-"
                f"{hashlib.sha256(test_filter.encode('utf-8')).hexdigest()[:12]}"
            )
            stored_manifest = destination / "validation-manifest.json"
            if stored_manifest.is_file():
                facts.append(
                    self._pre_handoff_validation_fact(
                        stored_manifest,
                        commit=commit,
                        tree=tree,
                        platform=platform,
                        test_filter=test_filter,
                        policy_sha256=plan["policy_sha256"],
                    )
                )
                continue
            if destination.exists() or destination.is_symlink():
                raise CandidateIntegrationError(
                    "pre-handoff validation destination exists with unknown identity: "
                    f"{destination}"
                )

            shell = "powershell.exe" if os.name == "nt" else "pwsh"
            command = [
                shell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-TestPlatform",
                platform,
                "-TestFilter",
                test_filter,
                "-ProjectPath",
                str(self.checkout),
            ]
            if self.unity_executable is not None:
                command.extend(("-UnityExecutable", str(self.unity_executable)))
            try:
                result = self.unity_command_runner(
                    command,
                    self.checkout,
                    float(os.getenv("NSC_TASK_AGENT_UNITY_TIMEOUT_SECONDS", "3600")),
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise CandidateIntegrationError(
                    f"pre-handoff {platform} Unity test could not run"
                ) from exc
            stdout = _decode(result.stdout or b"", label="Unity stdout")
            stderr = _decode(result.stderr or b"", label="Unity stderr")
            if result.returncode != 0:
                detail = "\n".join(item for item in (stdout.strip(), stderr.strip()) if item)
                raise CandidateIntegrationError(
                    f"pre-handoff {platform} Unity test failed ({result.returncode})"
                    + (f"\n{detail}" if detail else "")
                )
            match = re.search(r"(?im)^Validation manifest:\s*(.+?)\s*$", stdout)
            if match is None:
                raise CandidateIntegrationError(
                    f"pre-handoff {platform} Unity test omitted its validation manifest"
                )
            try:
                source_manifest = Path(match.group(1).strip()).resolve(strict=True)
                load_validation_manifest(source_manifest)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source_manifest.parent, destination)
            except (OSError, ValidationManifestError) as exc:
                raise CandidateIntegrationError(
                    f"pre-handoff {platform} Unity validation evidence is invalid: {exc}"
                ) from exc
            facts.append(
                self._pre_handoff_validation_fact(
                    stored_manifest,
                    commit=commit,
                    tree=tree,
                    platform=platform,
                    test_filter=test_filter,
                    policy_sha256=plan["policy_sha256"],
                )
            )
        return tuple(facts)

    def _pre_handoff_validation_plan(self) -> dict[str, Any] | None:
        # Import lazily so the candidate integration primitive remains usable without
        # installing the downstream controller monkey patches.
        from .downstream_resilience import validation_plan_for

        try:
            return validation_plan_for(self.checkout, self.scope.task)
        except TaskReviewContractError as exc:
            raise CandidateIntegrationError(str(exc)) from exc

    @staticmethod
    def _pre_handoff_validation_fact(
        manifest_path: Path,
        *,
        commit: str,
        tree: str,
        platform: str,
        test_filter: str,
        policy_sha256: str,
    ) -> dict[str, Any]:
        try:
            manifest = load_validation_manifest(manifest_path)
            digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        except (OSError, ValidationManifestError) as exc:
            raise CandidateIntegrationError(
                f"stored pre-handoff Unity validation is invalid: {exc}"
            ) from exc
        if (
            manifest.validated_state.commit != commit
            or manifest.validated_state.tree != tree
            or manifest.unity.test_platform != platform
            or manifest.unity.test_filter != test_filter
        ):
            raise CandidateIntegrationError(
                "pre-handoff Unity validation does not match the exact candidate commit"
            )
        return {
            "test_platform": platform,
            "test_filter": test_filter,
            "commit": commit,
            "tree": tree,
            "manifest_path": str(manifest.path),
            "manifest_sha256": digest,
            "policy_sha256": policy_sha256,
            "total": manifest.test_run.total,
            "passed": manifest.test_run.passed,
        }

    def _validate_in_disposable_clone(
        self,
        candidate: Path,
        execution: ExecutionCrewReceipt,
        *,
        base_head: str,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix=f"{self.scope.task_id.casefold()}-candidate-") as temporary:
            clone = Path(temporary) / "candidate"
            _run(
                (
                    "git",
                    "clone",
                    "--no-local",
                    "--no-hardlinks",
                    "--no-checkout",
                    str(self.checkout),
                    str(clone),
                ),
                cwd=self.checkout.parent,
                timeout_seconds=600.0,
            )
            _git(
                clone,
                "fetch",
                str(self.checkout),
                "+refs/remotes/origin/main:refs/remotes/source/main",
            )
            _git(clone, "checkout", "--detach", base_head)
            self._apply_candidate(clone, candidate, execution)
            self._verify_applied_state(clone, execution)

    def _verify_applied_state(
        self,
        root: Path,
        execution: ExecutionCrewReceipt,
        *,
        expected_paths: tuple[str, ...] | None = None,
    ) -> None:
        changed = _changed_paths(root)
        expected = (
            execution.final_actual_changed_paths
            if expected_paths is None
            else expected_paths
        )
        if changed != expected:
            raise CandidateIntegrationError(
                f"applied integration paths differ from the verified path set: "
                f"{changed} != {expected}"
            )
        whitespace = _git(root, "diff", "--check", check=False)
        if whitespace.returncode != 0:
            raise CandidateIntegrationError(
                "candidate failed git diff --check:\n"
                + _decode(whitespace.stdout + whitespace.stderr, label="git diff check").strip()
            )
        taskcontrol = root / "Pipeline" / "TaskGraph" / "taskcontrol.py"
        if not taskcontrol.is_file():
            raise CandidateIntegrationError("candidate checkout is missing taskcontrol.py")
        validation = _run(
            (sys.executable, str(taskcontrol), "validate"),
            cwd=root,
            check=False,
            timeout_seconds=300.0,
        )
        stdout = _decode(validation.stdout, label="taskcontrol validate stdout")
        if validation.returncode != 0 or "taskcontrol validate: PASS" not in stdout:
            raise CandidateIntegrationError("TaskGraph validation failed after candidate application")
        contract_path = str(
            self.scope.task.get("contract_path") or f"Tasks/{self.scope.task_id}.yaml"
        )
        contract = _git(root, "show", f"HEAD:{contract_path}", check=False)
        if contract.returncode != 0 or hashlib.sha256(contract.stdout).hexdigest() != execution.task_contract_sha256:
            raise CandidateIntegrationError("candidate application changed task-contract identity")

    def _ensure_git_identity(self) -> None:
        if not _git_text(self.checkout, "config", "user.name", check=False):
            _git(
                self.checkout,
                "config",
                "user.name",
                os.getenv("NSC_AGENT_GIT_NAME", "No Safe Circle TaskReviewAgent"),
            )
        if not _git_text(self.checkout, "config", "user.email", check=False):
            _git(
                self.checkout,
                "config",
                "user.email",
                os.getenv(
                    "NSC_AGENT_GIT_EMAIL",
                    "task-review-agent@users.noreply.github.com",
                ),
            )

    def _push_exact(
        self,
        commit: str,
        *,
        allowed_remote_heads: Sequence[str],
    ) -> None:
        remote_before = _remote_head(self.checkout, self.branch)
        if remote_before not in (None, commit, *allowed_remote_heads):
            raise CandidateIntegrationError(
                f"remote task branch moved unexpectedly to {remote_before}; refusing to overwrite"
            )
        if remote_before != commit:
            _git(
                self.checkout,
                "push",
                "--set-upstream",
                "origin",
                f"HEAD:refs/heads/{self.branch}",
            )
        if _remote_head(self.checkout, self.branch) != commit:
            raise CandidateIntegrationError("pushed task branch does not equal candidate commit")

    def _create_receipt(
        self,
        commit: str,
        execution: ExecutionCrewReceipt,
        *,
        integration_base: str,
        pre_handoff_validations: tuple[dict[str, Any], ...],
    ) -> CandidateIntegrationReceipt:
        tree = _git_text(self.checkout, "rev-parse", f"{commit}^{{tree}}")
        changed_paths = _changed_paths(self.checkout, base=integration_base)
        if not self._paths_match_execution(changed_paths, execution):
            raise CandidateIntegrationError("integrated commit has an unauthorized path set")
        checks = [
            "ExecutionCrew contract-locality audit and semantic validator completed.",
            "candidate.patch SHA-256 matched crew_result.json.",
            "Current origin/main was fetched immediately before candidate integration.",
            "candidate.patch applied cleanly with three-way resolution in a disposable clone based on current main.",
            "Applied path set exactly matched ExecutionCrew final_actual_changed_paths.",
            "git diff --check passed.",
            "TaskGraph validation passed after candidate application.",
        ]
        if self._requires_door_prototype_builder(execution):
            checks.append(
                "DoorPrototype builder output was limited to its owned asset and scene paths."
            )
            checks.append(
                "DoorPrototype scene trailing whitespace was normalized and the final "
                "builder output passed git diff --check."
            )
        for validation in pre_handoff_validations:
            checks.append(
                "Pre-handoff authoritative Unity "
                f"{validation['test_platform']} validation passed on exact commit {commit}."
            )
        checks.extend(
            (
                "Implementation and tests were committed on the canonical task branch.",
                "The exact commit was pushed as the remote task branch.",
            )
        )
        return CandidateIntegrationReceipt(
            task_id=execution.task_id,
            lease_id=execution.lease_id,
            plan_id=execution.plan_id,
            run_id=execution.run_id,
            provider=execution.provider,
            branch=self.branch,
            base_head=integration_base,
            commit=commit,
            commit_tree=tree,
            task_contract_sha256=execution.task_contract_sha256,
            candidate_sha256=str(execution.candidate_sha256),
            changed_paths=changed_paths,
            pre_handoff_validations=pre_handoff_validations,
            completed_checks=tuple(checks),
        )

    def _verify_receipt(
        self,
        receipt: CandidateIntegrationReceipt,
        execution: ExecutionCrewReceipt,
    ) -> None:
        if (
            receipt.task_id != execution.task_id
            or receipt.lease_id != execution.lease_id
            or receipt.plan_id != execution.plan_id
            or receipt.run_id != execution.run_id
            or receipt.candidate_sha256 != execution.candidate_sha256
        ):
            raise CandidateIntegrationError("integration receipt does not match ExecutionCrew run")
        if not self._paths_match_execution(receipt.changed_paths, execution):
            raise CandidateIntegrationError("integration receipt has an unauthorized path set")
        plan = self._pre_handoff_validation_plan()
        expected = () if plan is None else tuple(
            (platform, plan["test_filters"][platform], plan["policy_sha256"])
            for platform in plan["required_test_platforms"]
        )
        try:
            actual = tuple(
                (
                    item["test_platform"],
                    item["test_filter"],
                    item["policy_sha256"],
                )
                for item in receipt.pre_handoff_validations
            )
            if actual != expected:
                raise CandidateIntegrationError(
                    "integration receipt does not contain the exact committed "
                    "pre-handoff validation plan"
                )
            for validation in receipt.pre_handoff_validations:
                fact = self._pre_handoff_validation_fact(
                    Path(validation["manifest_path"]),
                    commit=receipt.commit,
                    tree=receipt.commit_tree,
                    platform=validation["test_platform"],
                    test_filter=validation["test_filter"],
                    policy_sha256=validation["policy_sha256"],
                )
                if fact != validation:
                    raise CandidateIntegrationError(
                        "pre-handoff Unity validation receipt changed"
                    )
        except (KeyError, TypeError) as exc:
            raise CandidateIntegrationError(
                "pre-handoff Unity validation receipt is malformed"
            ) from exc
        head = _git_text(self.checkout, "rev-parse", "HEAD", check=False)
        branch = _git_text(self.checkout, "branch", "--show-current", check=False)
        status = _git_text(
            self.checkout,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        tree = _git_text(self.checkout, "rev-parse", "HEAD^{tree}", check=False)
        if (
            head != receipt.commit
            or tree != receipt.commit_tree
            or branch != receipt.branch
            or status
        ):
            raise CandidateIntegrationError("integrated task checkout no longer matches its receipt")
        if _remote_head(self.checkout, receipt.branch) != receipt.commit:
            raise CandidateIntegrationError("integrated task commit is no longer the remote branch head")
        if _changed_paths(self.checkout, base=receipt.base_head) != receipt.changed_paths:
            raise CandidateIntegrationError("integrated commit path set changed")

    def _persist(self, receipt: CandidateIntegrationReceipt) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        payload = receipt.to_dict()
        payload["receipt_sha256"] = semantic_sha256(payload)
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, self.state_path)

    def _load_current(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            identity = dict(raw)
            receipt_hash = identity.pop("receipt_sha256")
            receipt = CandidateIntegrationReceipt(
                task_id=identity["task_id"],
                lease_id=identity["lease_id"],
                plan_id=identity["plan_id"],
                run_id=identity["run_id"],
                provider=identity["provider"],
                branch=identity["branch"],
                base_head=identity["base_head"],
                commit=identity["commit"],
                commit_tree=identity["commit_tree"],
                task_contract_sha256=identity["task_contract_sha256"],
                candidate_sha256=identity["candidate_sha256"],
                changed_paths=tuple(identity["changed_paths"]),
                pre_handoff_validations=tuple(
                    dict(item) for item in identity["pre_handoff_validations"]
                ),
                completed_checks=tuple(identity["completed_checks"]),
            )
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
            return
        if raw.get("schema_version") != INTEGRATION_SCHEMA_VERSION:
            return
        if receipt_hash != semantic_sha256(identity):
            return
        execution = self.execution.receipt
        if execution is None:
            return
        try:
            self._verify_receipt(receipt, execution)
        except CandidateIntegrationError:
            return
        self._receipt = receipt
