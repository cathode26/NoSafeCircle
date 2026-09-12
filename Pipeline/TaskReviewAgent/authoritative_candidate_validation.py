"""Run committed task-specific validation before a candidate reaches a human.

Production and AssistantControl share this host-side boundary.  A passing model
review is not test execution; this component runs the committed validation
policy against the exact clean candidate commit and stores its evidence.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from Pipeline.Testing.validation_manifest import (
    ImportedValidationManifest,
    ValidationManifestError,
    import_validation_manifest,
    load_validation_manifest,
)
from .contracts import TaskReviewContractError
from .door_prototype_materialization import (
    UnityCommandRunner,
    default_unity_command_runner,
)


class AuthoritativeCandidateValidationError(RuntimeError):
    """The exact candidate did not produce authenticated passing validation."""


def _decode(value: bytes, label: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthoritativeCandidateValidationError(
            f"{label} was not valid UTF-8"
        ) from exc


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ("git", "--no-optional-locks", "-C", str(root), *args),
            cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuthoritativeCandidateValidationError(
            "candidate validation Git command could not run"
        ) from exc
    if result.returncode:
        raise AuthoritativeCandidateValidationError(
            _decode(result.stderr, "Git stderr").strip()
            or "candidate validation Git command failed"
        )
    return _decode(result.stdout, "Git stdout").strip()


def _require_source_validation_repository(
    checkout: Path, imported: ImportedValidationManifest,
) -> None:
    if imported.manifest.unity.test_platform != "SyntheticSource":
        return
    from .issue_workflow_store import (
        IssueWorkflowStoreError,
        resolve_issue_backend_repository,
    )
    try:
        repository = resolve_issue_backend_repository(checkout)
    except (IssueWorkflowStoreError, OSError) as exc:
        raise AuthoritativeCandidateValidationError(
            f"source validation repository is unproven: {exc}"
        ) from exc
    recorded = imported.manifest.repository
    if not isinstance(recorded, str) or recorded.casefold() != repository.casefold():
        raise AuthoritativeCandidateValidationError(
            "source validation manifest targets a different repository"
        )


def authoritative_validation_fact(
    *,
    checkout: Path,
    state_root: Path,
    manifest_path: Path,
    commit: str,
    tree: str,
    platform: str,
    test_filter: str,
    policy_sha256: str,
) -> dict[str, Any]:
    try:
        imported = import_validation_manifest(
            manifest_path,
            controller_root=state_root,
            expected_commit=commit,
            expected_tree=tree,
            expected_test_platform=platform,
            expected_test_filter=test_filter,
        )
        _require_source_validation_repository(checkout, imported)
    except (OSError, ValidationManifestError) as exc:
        raise AuthoritativeCandidateValidationError(
            f"stored candidate Unity validation is invalid: {exc}"
        ) from exc
    manifest = imported.manifest
    return {
        "test_platform": platform,
        "test_filter": test_filter,
        "commit": commit,
        "tree": tree,
        "manifest_relative_path": imported.relative_path,
        "policy_sha256": policy_sha256,
        "total": manifest.test_run.total,
        "passed": manifest.test_run.passed,
        **imported.identities(),
    }


def run_authoritative_candidate_validations(
    *,
    checkout: Path | str,
    state_root: Path | str,
    task: Mapping[str, Any],
    task_id: str,
    run_id: str,
    commit: str,
    unity_executable: Path | str | None = None,
    command_runner: UnityCommandRunner = default_unity_command_runner,
    timeout_seconds: float | None = None,
    require_plan: bool = False,
    evidence_phase: str = "pre-handoff-validation",
) -> tuple[dict[str, Any], ...]:
    """Run the committed policy for one exact clean candidate commit."""
    root = Path(checkout).resolve()
    evidence_root = Path(state_root).resolve()
    from .downstream_resilience import validation_plan_for
    try:
        plan = validation_plan_for(root, task)
    except TaskReviewContractError as exc:
        raise AuthoritativeCandidateValidationError(str(exc)) from exc
    if plan is None:
        if not require_plan:
            return ()
        raise AuthoritativeCandidateValidationError(
            f"{task_id} has no committed authoritative validation policy"
        )
    if _git(root, "rev-parse", "HEAD") != commit:
        raise AuthoritativeCandidateValidationError(
            "candidate validation commit is not the checked-out task head"
        )
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise AuthoritativeCandidateValidationError(
            "authoritative validation requires a clean task checkout"
        )
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    script = root / "Pipeline" / "Testing" / "run_unity_tests_clean.ps1"
    if not script.is_file():
        raise AuthoritativeCandidateValidationError("clean Unity test runner is missing")
    if not evidence_phase or "/" in evidence_phase or "\\" in evidence_phase:
        raise AuthoritativeCandidateValidationError("validation evidence phase is invalid")
    validation_root = evidence_root / "outputs" / task_id / run_id / evidence_phase
    facts: list[dict[str, Any]] = []
    test_timeout = timeout_seconds or float(
        os.getenv("NSC_TASK_AGENT_UNITY_TIMEOUT_SECONDS", "3600")
    )
    for platform in plan["required_test_platforms"]:
        test_filter = plan["test_filters"][platform]
        destination = validation_root / (
            f"{platform}-{hashlib.sha256(test_filter.encode('utf-8')).hexdigest()[:12]}"
        )
        stored_manifest = destination / "validation-manifest.json"
        if stored_manifest.is_file():
            facts.append(authoritative_validation_fact(
                checkout=root, state_root=evidence_root,
                manifest_path=stored_manifest, commit=commit, tree=tree,
                platform=platform, test_filter=test_filter,
                policy_sha256=plan["policy_sha256"],
            ))
            continue
        if destination.exists() or destination.is_symlink():
            raise AuthoritativeCandidateValidationError(
                f"candidate validation destination exists with unknown identity: {destination}"
            )
        shell = "powershell.exe" if os.name == "nt" else "pwsh"
        command = [
            shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-TestPlatform", platform, "-TestFilter", test_filter,
            "-ProjectPath", str(root),
        ]
        if unity_executable is not None:
            command.extend(("-UnityExecutable", str(unity_executable)))
        if platform == "SyntheticSource":
            command = [
                sys.executable, "-B",
                str(root / "Pipeline/Testing/synthetic_source_validation.py"),
                "--source", str(root), "--task-id", task_id,
                "--test-filter", test_filter,
            ]
        try:
            result = command_runner(command, root, test_timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AuthoritativeCandidateValidationError(
                f"candidate {platform} Unity test could not run"
            ) from exc
        stdout = _decode(result.stdout or b"", "validation stdout")
        stderr = _decode(result.stderr or b"", "validation stderr")
        if result.returncode:
            detail = "\n".join(item for item in (stdout.strip(), stderr.strip()) if item)
            raise AuthoritativeCandidateValidationError(
                f"candidate {platform} Unity test failed ({result.returncode})"
                + (f"\n{detail}" if detail else "")
            )
        match = re.search(r"(?im)^Validation manifest:\s*(.+?)\s*$", stdout)
        if match is None:
            raise AuthoritativeCandidateValidationError(
                f"candidate {platform} Unity test omitted its validation manifest"
            )
        try:
            source_manifest = Path(match.group(1).strip()).resolve(strict=True)
            load_validation_manifest(source_manifest)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_manifest.parent, destination)
        except (OSError, ValidationManifestError) as exc:
            raise AuthoritativeCandidateValidationError(
                f"candidate {platform} validation evidence is invalid: {exc}"
            ) from exc
        facts.append(authoritative_validation_fact(
            checkout=root, state_root=evidence_root,
            manifest_path=stored_manifest, commit=commit, tree=tree,
            platform=platform, test_filter=test_filter,
            policy_sha256=plan["policy_sha256"],
        ))
    if _git(root, "rev-parse", "HEAD") != commit or _git(
        root, "status", "--porcelain=v1", "--untracked-files=all"
    ):
        raise AuthoritativeCandidateValidationError(
            "candidate changed during authoritative validation"
        )
    return tuple(facts)


__all__ = [
    "AuthoritativeCandidateValidationError", "authoritative_validation_fact",
    "run_authoritative_candidate_validations",
]
