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
from .authoritative_candidate_validation import (
    AuthoritativeCandidateValidationError,
    authoritative_validation_fact,
    run_authoritative_candidate_validations,
)
from .door_prototype_materialization import (
    DOOR_PROTOTYPE_BUILDER as _DOOR_PROTOTYPE_BUILDER,
    DoorPrototypeMaterializationError,
    UnityCommandRunner,
    default_unity_command_runner,
    is_door_prototype_builder_output as _is_door_prototype_builder_output,
    normalize_unity_serialized_whitespace as _normalize_unity_serialized_whitespace,
    resolve_unity_executable,
    run_door_prototype_builder,
)
from .execution_bridge import ExecutionCrewBridge, ExecutionCrewReceipt
from .pipeline_scope import RepositoryScopeAuthority
from Pipeline.Testing.validation_manifest import (
    ImportedValidationManifest,
    controller_relative_path,
    import_validation_manifest,
    resolve_controller_relative_path,
    ValidationManifestError,
    load_validation_manifest,
)


# 1.2 replaced the absolute `manifest_path` in each pre-handoff validation fact
# with a controller-root-relative `manifest_relative_path` plus the XML and log
# identities a later consumer needs to re-prove the same evidence. A 1.1 receipt
# cannot supply those facts, so it fails closed rather than being reinterpreted.
# 1.3 adds a durable candidate-ready stage and preserves the eventual human
# checklist inputs.  Existing 1.2 receipts remain readable as already validated
# pre-handoff commits; they are never reinterpreted as queued candidates.
INTEGRATION_SCHEMA_VERSION = "1.3"
SUPPORTED_INTEGRATION_SCHEMA_VERSIONS = frozenset({"1.2", INTEGRATION_SCHEMA_VERSION})
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_UNITY_TEST_RUNNER = "Pipeline/Testing/run_unity_tests_clean.ps1"


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
    lifecycle: str = "pre_handoff_validated"
    implementation_summary: str | None = None
    human_steps: tuple[str, ...] = ()
    expected_result: str | None = None

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
            "lifecycle": self.lifecycle,
            "implementation_summary": self.implementation_summary,
            "human_steps": list(self.human_steps),
            "expected_result": self.expected_result,
        }


def load_integration_receipt(state_path: Path | str) -> CandidateIntegrationReceipt | None:
    """Load one persisted integration receipt, or return None when there is none.

    Returns ``None`` only for genuine absence or for a receipt this schema cannot
    interpret. Every other defect -- unreadable JSON, a missing field, or a
    ``receipt_sha256`` that does not match the semantic hash of its own body --
    raises, so a tampered receipt is never confused with an absent one.

    The hash is an integrity check on this controller's own state file, not a
    signature: it proves the body was not edited in place, and it is never a
    substitute for the containment and recomputed-path checks a consumer applies
    to the manifest locations the receipt names.
    """

    path = Path(state_path)
    if not path.is_file() or path.is_symlink():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateIntegrationError(
            f"integration receipt is not readable JSON: {path}"
        ) from exc
    if not isinstance(raw, dict):
        raise CandidateIntegrationError("integration receipt must be a JSON object")
    version = raw.get("schema_version")
    if version not in SUPPORTED_INTEGRATION_SCHEMA_VERSIONS:
        # An older receipt cannot supply the controller-relative manifest location
        # or the XML/log identities a reuse consumer must re-prove. Fail closed by
        # treating it as absent so the work is redone rather than reinterpreted.
        return None
    identity = dict(raw)
    receipt_hash = identity.pop("receipt_sha256", None)
    if not isinstance(receipt_hash, str) or not receipt_hash:
        raise CandidateIntegrationError("integration receipt omitted receipt_sha256")
    if receipt_hash != semantic_sha256(identity):
        raise CandidateIntegrationError(
            "integration receipt hash does not match its own recorded body"
        )
    try:
        validations = tuple(dict(item) for item in identity["pre_handoff_validations"])
        legacy = version == "1.2"
        return CandidateIntegrationReceipt(
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
            pre_handoff_validations=validations,
            completed_checks=tuple(identity["completed_checks"]),
            lifecycle=(
                "pre_handoff_validated"
                if legacy
                else identity["lifecycle"]
            ),
            implementation_summary=(
                None if legacy else identity["implementation_summary"]
            ),
            human_steps=(
                () if legacy else tuple(identity["human_steps"])
            ),
            expected_result=(None if legacy else identity["expected_result"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CandidateIntegrationError(
            "integration receipt is missing required identity fields"
        ) from exc


def require_source_validation_repository(
    checkout: Path | str,
    imported: ImportedValidationManifest,
    *,
    expected_repository: str | None = None,
) -> None:
    """Keep source evidence bound to its repository when commits share a tree."""
    if imported.manifest.unity.test_platform != "SyntheticSource":
        return
    from .issue_workflow_store import IssueWorkflowStoreError, resolve_issue_backend_repository
    try:
        repository = resolve_issue_backend_repository(Path(checkout).resolve())
    except (IssueWorkflowStoreError, OSError) as exc:
        raise CandidateIntegrationError(f"source validation repository is unproven: {exc}") from exc
    recorded = imported.manifest.repository
    if (
        not isinstance(recorded, str)
        or recorded.casefold() != repository.casefold()
        or (expected_repository is not None and expected_repository.casefold() != repository.casefold())
    ):
        raise CandidateIntegrationError("source validation manifest targets a different repository")


def _committed_blob(root: Path, revision: str, relative_path: str) -> bytes:
    result = _git(
        root,
        "cat-file",
        "blob",
        f"{revision}:{relative_path}",
        check=False,
    )
    if result.returncode != 0:
        raise CandidateIntegrationError(
            f"trusted runner provenance could not read {relative_path} at {revision}"
        )
    return result.stdout


def _prove_pre_handoff_runner_identity(
    *,
    checkout: Path,
    task_id: str,
    commit: str,
    tree: str,
    trusted_source: Path,
    receipt: CandidateIntegrationReceipt,
) -> dict[str, str]:
    """Prove that a historical handoff inherited its runner from trusted main."""

    if not _SHA40.fullmatch(commit) or not _SHA40.fullmatch(tree):
        raise CandidateIntegrationError(
            "trusted runner provenance requires exact lowercase commit and tree identities"
        )
    if receipt.task_id != task_id:
        raise CandidateIntegrationError(
            "integration receipt task identity cannot prove the historical runner"
        )
    if receipt.commit != commit or receipt.commit_tree != tree:
        raise CandidateIntegrationError(
            "integration receipt commit/tree cannot prove the historical runner"
        )
    if not _SHA40.fullmatch(receipt.base_head):
        raise CandidateIntegrationError(
            "integration receipt base cannot prove the historical runner"
        )

    checkout_head = _git_text(checkout, "rev-parse", "HEAD")
    checkout_tree = _git_text(checkout, "rev-parse", "HEAD^{tree}")
    committed_tree = _git_text(checkout, "rev-parse", f"{commit}^{{tree}}")
    if (
        checkout_head != commit
        or checkout_tree != tree
        or committed_tree != tree
    ):
        raise CandidateIntegrationError(
            "task checkout commit/tree cannot prove the historical runner"
        )

    ancestry = _git_text(checkout, "rev-list", "--parents", "-n", "1", commit)
    ancestry_parts = ancestry.split()
    if ancestry_parts != [commit, receipt.base_head]:
        raise CandidateIntegrationError(
            "historical runner provenance requires the candidate commit's single "
            "parent to equal the integration receipt base"
        )

    trusted_head = _git_text(trusted_source, "rev-parse", "HEAD")
    if not _SHA40.fullmatch(trusted_head):
        raise CandidateIntegrationError(
            "trusted source HEAD cannot prove the historical runner"
        )
    ancestor = _git(
        trusted_source,
        "merge-base",
        "--is-ancestor",
        receipt.base_head,
        trusted_head,
        check=False,
    )
    if ancestor.returncode != 0:
        raise CandidateIntegrationError(
            "integration receipt base is not an ancestor of the trusted source HEAD; "
            "historical runner provenance is unproven"
        )

    runner_path = checkout.joinpath(*_UNITY_TEST_RUNNER.split("/"))
    if runner_path.is_symlink() or not runner_path.is_file():
        raise CandidateIntegrationError(
            "historical Unity runner must be a regular non-symlink file"
        )
    base_runner = _committed_blob(
        trusted_source,
        receipt.base_head,
        _UNITY_TEST_RUNNER,
    )
    candidate_runner = _committed_blob(checkout, commit, _UNITY_TEST_RUNNER)
    if base_runner != candidate_runner:
        raise CandidateIntegrationError(
            "historical Unity runner differs from its trusted integration base"
        )
    committed_runner_oid = _git_text(
        checkout,
        "rev-parse",
        f"{commit}:{_UNITY_TEST_RUNNER}",
    )
    worktree_runner_oid = _git_text(
        checkout,
        "hash-object",
        f"--path={_UNITY_TEST_RUNNER}",
        "--",
        str(runner_path),
    )
    if worktree_runner_oid != committed_runner_oid:
        raise CandidateIntegrationError(
            "historical Unity runner worktree differs from the committed runner"
        )
    try:
        worktree_runner = runner_path.read_bytes()
    except OSError as exc:
        raise CandidateIntegrationError(
            "historical Unity runner could not be read"
        ) from exc

    return {
        "path": _UNITY_TEST_RUNNER,
        "sha256": hashlib.sha256(worktree_runner).hexdigest(),
        "source_commit": commit,
        "source_tree": tree,
    }


def prove_pre_handoff_runner_identity(
    *,
    checkout: Path | str,
    task_id: str,
    commit: str,
    tree: str,
    trusted_source: Path | str,
) -> dict[str, str] | None:
    """Return an independently proven historical runner identity, if recorded.

    Absence, or a receipt for a different candidate, remains an ordinary cache
    miss. Once an exact receipt is found, every provenance defect raises instead
    of silently authorizing its runner or falling back to execution.
    """

    checkout_path = Path(checkout).resolve()
    normalized_task_id = str(task_id).strip()
    state_path = (
        checkout_path.parent
        / ".task-review-agent"
        / f"{normalized_task_id}.integration.json"
    )
    receipt = load_integration_receipt(state_path)
    if receipt is None:
        return None
    if receipt.commit != commit or receipt.commit_tree != tree:
        return None
    return _prove_pre_handoff_runner_identity(
        checkout=checkout_path,
        task_id=normalized_task_id,
        commit=commit,
        tree=tree,
        trusted_source=Path(trusted_source).resolve(),
        receipt=receipt,
    )


def find_pre_handoff_validation(
    *,
    checkout: Path | str,
    task_id: str,
    commit: str,
    tree: str,
    test_platform: str,
    test_filter: str,
    trusted_source: Path | str | None = None,
) -> ImportedValidationManifest | None:
    """Import the pre-handoff Unity evidence for one exact validation, if it exists.

    Returns ``None`` only when there is genuinely nothing to reuse: no integration
    receipt, or a receipt that records no validation for this exact commit, tree,
    platform, and caller-recomputed filter. Every other outcome raises, because a
    receipt that names evidence which no longer verifies is tampering or
    corruption, and silently running Unity again would hide it.

    The manifest location is recomputed from the controller-owned state root; the
    persisted receipt contributes only a relative path and the three artifact
    digests, all of which the shared importer re-proves.

    Supplying ``trusted_source`` additionally proves that this exact candidate
    inherited the Unity runner from its single integration-base parent and that
    the base remains an ancestor of the trusted source. That independent Git
    proof is the only route here that opts a legacy path-only manifest into reuse.
    """

    state_root = Path(checkout).resolve().parent / ".task-review-agent"
    state_path = state_root / f"{str(task_id).strip()}.integration.json"
    receipt = load_integration_receipt(state_path)
    if receipt is None:
        return None
    if receipt.commit != commit or receipt.commit_tree != tree:
        # The receipt describes a different candidate; that is absence of
        # reusable evidence for this state, not corruption.
        return None
    for validation in receipt.pre_handoff_validations:
        try:
            if (
                validation["test_platform"] != test_platform
                or validation["test_filter"] != test_filter
            ):
                continue
            runner_identity = None
            if trusted_source is not None:
                runner_identity = _prove_pre_handoff_runner_identity(
                    checkout=Path(checkout).resolve(),
                    task_id=str(task_id).strip(),
                    commit=commit,
                    tree=tree,
                    trusted_source=Path(trusted_source).resolve(),
                    receipt=receipt,
                )
            if validation["commit"] != commit or validation["tree"] != tree:
                raise CandidateIntegrationError(
                    "pre-handoff validation entry disagrees with its own receipt commit/tree"
                )
            manifest_path = resolve_controller_relative_path(
                validation["manifest_relative_path"], state_root
            )
            imported = import_validation_manifest(
                manifest_path,
                controller_root=state_root,
                expected_commit=commit,
                expected_tree=tree,
                expected_test_platform=test_platform,
                expected_test_filter=test_filter,
                expected_manifest_sha256=validation["manifest_sha256"],
                expected_xml_sha256=validation["xml_sha256"],
                expected_log_sha256=validation["log_sha256"],
                expected_runner_sha256=(
                    runner_identity["sha256"] if runner_identity is not None else None
                ),
                expected_runner_source_commit=(
                    runner_identity["source_commit"]
                    if runner_identity is not None
                    else None
                ),
                expected_runner_source_tree=(
                    runner_identity["source_tree"]
                    if runner_identity is not None
                    else None
                ),
                allow_legacy_runner_identity_if_independently_proven=(
                    runner_identity is not None
                ),
            )
            require_source_validation_repository(checkout, imported)
            return imported
        except (KeyError, TypeError) as exc:
            raise CandidateIntegrationError(
                "pre-handoff Unity validation receipt is malformed"
            ) from exc
        except (OSError, ValidationManifestError) as exc:
            raise CandidateIntegrationError(
                f"recorded pre-handoff Unity evidence no longer verifies: {exc}"
            ) from exc
    return None


class CandidateCommitValidator:
    """Shared local Git validation for production and nonpublishing candidates."""

    def __init__(self, *, checkout: Path | str, branch: str,
                 scope: RepositoryScopeAuthority) -> None:
        self.checkout = Path(checkout).resolve()
        self.branch = str(branch).strip()
        self.scope = scope
        if not self.branch:
            raise CandidateIntegrationError("candidate validation requires a branch")

    def assert_checkout_identity(self, execution: ExecutionCrewReceipt) -> None:
        root = _git_text(self.checkout, "rev-parse", "--show-toplevel")
        branch = _git_text(self.checkout, "symbolic-ref", "--quiet", "--short", "HEAD")
        head = _git_text(self.checkout, "rev-parse", "HEAD")
        if Path(root).resolve() != self.checkout:
            raise CandidateIntegrationError("integration checkout root changed")
        if branch != self.branch:
            raise CandidateIntegrationError(
                f"integration branch {branch!r} differs from workflow branch {self.branch!r}")
        if head != execution.source_head:
            raise CandidateIntegrationError(
                f"integration checkout HEAD {head!r} differs from ExecutionCrew source "
                f"{execution.source_head!r}")
        if _git_text(self.checkout, "status", "--porcelain=v1", "--untracked-files=all"):
            raise CandidateIntegrationError("integration requires a clean task checkout")

    @staticmethod
    def apply_candidate(root: Path, candidate: Path, execution: ExecutionCrewReceipt) -> None:
        _git(root, "apply", "--3way", "--", str(candidate))
        _git(root, "restore", "--staged", "--", *execution.final_actual_changed_paths)

    def verify_applied_state(self, root: Path, execution: ExecutionCrewReceipt,
                             *, expected_paths: tuple[str, ...] | None = None) -> None:
        changed = _changed_paths(root)
        expected = execution.final_actual_changed_paths if expected_paths is None else expected_paths
        if changed != expected:
            raise CandidateIntegrationError(
                f"applied integration paths differ from the verified path set: {changed} != {expected}")
        _normalize_unity_serialized_whitespace(Path(root), changed)
        whitespace = _git(root, "diff", "--check", check=False)
        if whitespace.returncode != 0:
            raise CandidateIntegrationError(
                "candidate failed git diff --check:\n"
                + _decode(whitespace.stdout + whitespace.stderr, label="git diff check").strip())
        taskcontrol = root / "Pipeline" / "TaskGraph" / "taskcontrol.py"
        if not taskcontrol.is_file():
            raise CandidateIntegrationError("candidate checkout is missing taskcontrol.py")
        validation = _run((sys.executable, str(taskcontrol), "validate"), cwd=root,
                          check=False, timeout_seconds=300.0)
        stdout = _decode(validation.stdout, label="taskcontrol validate stdout")
        if validation.returncode != 0 or "taskcontrol validate: PASS" not in stdout:
            raise CandidateIntegrationError("TaskGraph validation failed after candidate application")
        contract_path = str(self.scope.task.get("contract_path")
                            or f"Tasks/{self.scope.task_id}.yaml")
        contract = _git(root, "show", f"HEAD:{contract_path}", check=False)
        if (contract.returncode != 0 or hashlib.sha256(contract.stdout).hexdigest()
                != execution.task_contract_sha256):
            raise CandidateIntegrationError("candidate application changed task-contract identity")

    def validate_in_disposable_clone(self, candidate: Path, execution: ExecutionCrewReceipt,
                                     *, base_head: str, scratch_root: Path | None = None,
                                     register_clone=None, validation_source: Path | None = None) -> None:
        if scratch_root is not None:
            scratch_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"{self.scope.task_id.casefold()}-candidate-",
                                         dir=scratch_root) as temporary:
            clone = Path(temporary) / "candidate"
            _run(("git", "clone", "--no-local", "--no-hardlinks", "--no-checkout",
                  str(validation_source or self.checkout), str(clone)),
                 cwd=self.checkout.parent, timeout_seconds=600.0)
            if register_clone is not None:
                register_clone(clone)
            if scratch_root is None:
                _git(clone, "fetch", str(self.checkout),
                     "+refs/remotes/origin/main:refs/remotes/source/main")
            _git(clone, "checkout", "--detach", base_head)
            self.apply_candidate(clone, candidate, execution)
            self.verify_applied_state(clone, execution)

    def expected_candidate_tree(self, candidate: Path, execution: ExecutionCrewReceipt,
                                *, base_head: str, scratch_root: Path | None = None,
                                register_clone=None, validation_source: Path | None = None) -> str:
        """Return the exact tree produced by the authenticated patch."""
        if scratch_root is not None:
            scratch_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"{self.scope.task_id.casefold()}-tree-",
                                         dir=scratch_root) as temporary:
            clone = Path(temporary) / "candidate"
            _run(("git", "clone", "--no-local", "--no-hardlinks", "--no-checkout",
                  str(validation_source or self.checkout), str(clone)),
                 cwd=self.checkout.parent, timeout_seconds=600.0)
            if register_clone is not None:
                register_clone(clone)
            _git(clone, "checkout", "--detach", base_head)
            self.apply_candidate(clone, candidate, execution)
            self.verify_applied_state(clone, execution)
            _git(clone, "add", "--", *execution.final_actual_changed_paths)
            return _git_text(clone, "write-tree")


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
        from .local_execution_fence import refuse_production_operation
        refuse_production_operation("production candidate integration")
        self.checkout = Path(checkout).resolve()
        self.branch = str(branch).strip()
        self.task_title = str(task_title).strip()
        self.scope = scope
        self.execution = execution
        self.commit_validator = CandidateCommitValidator(
            checkout=self.checkout, branch=self.branch, scope=self.scope)
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

    def stage_candidate(
        self,
        run_id: str,
        *,
        implementation_summary: str,
        human_steps: Sequence[str],
        expected_result: str,
    ) -> CandidateIntegrationReceipt:
        """Commit the reviewed candidate without crossing the merge gate.

        The candidate is intentionally based on the ExecutionCrew source.  It
        is safe to publish as a task-branch queue artifact, but it has not yet
        synchronized current main and must not be exposed as a human handoff.
        The gate owner performs that synchronization and exact-tree validation.
        """

        execution = self.execution.require(run_id)
        if execution.crew_status != "review_ready":
            raise CandidateIntegrationError(
                f"only review_ready ExecutionCrew output can be staged; found {execution.crew_status}"
            )
        if execution.candidate_path is None or execution.candidate_sha256 is None:
            raise CandidateIntegrationError("review_ready receipt omitted candidate identity")
        if not execution.final_actual_changed_paths:
            raise CandidateIntegrationError("review_ready candidate has no changed paths")
        summary = str(implementation_summary).strip()
        steps = tuple(str(item).strip() for item in human_steps if str(item).strip())
        expected = str(expected_result).strip()
        if not summary or not steps or not expected:
            raise CandidateIntegrationError(
                "candidate queueing requires the eventual concrete human checklist"
            )
        if self._receipt is not None:
            self._verify_receipt(self._receipt, execution)
            if (
                self._receipt.lifecycle != "candidate_ready"
                or self._receipt.implementation_summary != summary
                or self._receipt.human_steps != steps
                or self._receipt.expected_result != expected
            ):
                raise CandidateIntegrationError(
                    "staged candidate retry changed its durable handoff inputs"
                )
            return self._receipt

        existing_commit = self._existing_commit_for_run(execution)
        if existing_commit is not None:
            commit, integration_base = existing_commit
            if integration_base != execution.source_head:
                raise CandidateIntegrationError(
                    "queued candidate was already integrated with main outside the merge gate"
                )
            self._push_exact(commit, allowed_remote_heads=(execution.source_head,))
            receipt = self._create_receipt(
                commit,
                execution,
                integration_base=integration_base,
                pre_handoff_validations=(),
                lifecycle="candidate_ready",
                implementation_summary=summary,
                human_steps=steps,
                expected_result=expected,
            )
            self._persist(receipt)
            self._receipt = receipt
            return receipt

        self._assert_checkout_identity(execution)
        candidate = Path(execution.candidate_path)
        self._validate_in_disposable_clone(
            candidate,
            execution,
            base_head=execution.source_head,
        )
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
            staged = tuple(
                sorted(
                    (
                        line
                        for line in _git_text(
                            self.checkout, "diff", "--cached", "--name-only", "--"
                        ).splitlines()
                        if line
                    ),
                    key=str.casefold,
                )
            )
            if staged != final_changed_paths:
                raise CandidateIntegrationError(
                    f"staged paths differ from verified candidate paths: {staged} != {final_changed_paths}"
                )
            if _git_text(self.checkout, "diff", "--name-only", "--"):
                raise CandidateIntegrationError("candidate left unstaged tracked changes")
            if _git_text(self.checkout, "ls-files", "--others", "--exclude-standard"):
                raise CandidateIntegrationError("candidate left unstaged untracked files")
            self._ensure_git_identity()
            _git(
                self.checkout,
                "commit",
                "-m",
                f"Implement {self.scope.task_id}: {self.task_title}",
                "-m",
                (
                    f"ExecutionCrew-Run: {execution.run_id}\n"
                    f"ExecutionCrew-Candidate-SHA256: {execution.candidate_sha256}\n"
                    f"Task-Contract-SHA256: {execution.task_contract_sha256}\n"
                ),
            )
        except Exception as exc:
            raise CandidateIntegrationError(
                "candidate staging reached the canonical checkout but could not be "
                "committed; reconcile the isolated task checkout before retrying: "
                f"{exc}"
            ) from exc

        commit = _git_text(self.checkout, "rev-parse", "HEAD")
        parent = _git_text(self.checkout, "rev-parse", "HEAD^")
        if not _SHA40.fullmatch(commit) or parent != execution.source_head:
            raise CandidateIntegrationError(
                "queued candidate commit is not the exact child of the ExecutionCrew source"
            )
        if _changed_paths(self.checkout, base=execution.source_head) != final_changed_paths:
            raise CandidateIntegrationError("queued candidate changed an unexpected path set")
        self._push_exact(commit, allowed_remote_heads=(execution.source_head,))
        receipt = self._create_receipt(
            commit,
            execution,
            integration_base=execution.source_head,
            pre_handoff_validations=(),
            lifecycle="candidate_ready",
            implementation_summary=summary,
            human_steps=steps,
            expected_result=expected,
        )
        self._persist(receipt)
        self._receipt = receipt
        return receipt

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
        self.commit_validator.assert_checkout_identity(execution)

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

    def _apply_candidate(
        self,
        root: Path,
        candidate: Path,
        execution: ExecutionCrewReceipt,
    ) -> None:
        self.commit_validator.apply_candidate(root, candidate, execution)

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
        try:
            result = run_door_prototype_builder(
                checkout=self.checkout,
                task_id=self.scope.task_id,
                state_root=self.state_root,
                initial_changed_paths=execution.final_actual_changed_paths,
                unity_executable=self.unity_executable,
                unity_command_runner=self.unity_command_runner,
                timeout_seconds=self.unity_timeout_seconds,
            )
        except DoorPrototypeMaterializationError as exc:
            raise CandidateIntegrationError(str(exc)) from exc
        return result.changed_paths

    def _normalize_door_prototype_scene(
        self,
        changed_paths: tuple[str, ...],
    ) -> None:
        """Remove builder-generated trailing space/tab without changing line endings."""

        # The scene and every other Unity-serialised builder output get the same
        # treatment; the builder rewrites them all with Unity's trailing spaces.
        _normalize_unity_serialized_whitespace(self.checkout, tuple(changed_paths))

    def _resolve_unity_executable(self) -> Path:
        try:
            return resolve_unity_executable(self.checkout, self.unity_executable)
        except DoorPrototypeMaterializationError as exc:
            raise CandidateIntegrationError(str(exc)) from exc

    @staticmethod
    def _default_unity_command_runner(
        args: Sequence[str],
        cwd: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[bytes]:
        return default_unity_command_runner(args, cwd, timeout_seconds)

    def _run_pre_handoff_validations(
        self,
        commit: str,
        execution: ExecutionCrewReceipt,
    ) -> tuple[dict[str, Any], ...]:
        """Run committed task-specific Unity checks before publishing the handoff."""
        try:
            return run_authoritative_candidate_validations(
                checkout=self.checkout,
                state_root=self.state_root,
                task=self.scope.task,
                task_id=self.scope.task_id,
                run_id=execution.run_id,
                commit=commit,
                unity_executable=self.unity_executable,
                command_runner=self.unity_command_runner,
            )
        except AuthoritativeCandidateValidationError as exc:
            # Preserve the established production diagnostic prefix for operators
            # and existing recovery checks.
            message = str(exc).replace("candidate ", "pre-handoff ", 1)
            raise CandidateIntegrationError(message) from exc

    def _pre_handoff_validation_plan(self) -> dict[str, Any] | None:
        # Import lazily so the candidate integration primitive remains usable without
        # installing the downstream controller monkey patches.
        from .downstream_resilience import validation_plan_for

        try:
            return validation_plan_for(self.checkout, self.scope.task)
        except TaskReviewContractError as exc:
            raise CandidateIntegrationError(str(exc)) from exc

    def _pre_handoff_validation_fact(
        self,
        manifest_path: Path,
        *,
        commit: str,
        tree: str,
        platform: str,
        test_filter: str,
        policy_sha256: str,
    ) -> dict[str, Any]:
        try:
            return authoritative_validation_fact(
                checkout=self.checkout, state_root=self.state_root,
                manifest_path=manifest_path, commit=commit, tree=tree,
                platform=platform, test_filter=test_filter,
                policy_sha256=policy_sha256,
            )
        except AuthoritativeCandidateValidationError as exc:
            raise CandidateIntegrationError(
                str(exc).replace("stored candidate", "stored pre-handoff", 1)
            ) from exc

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
        _normalize_unity_serialized_whitespace(Path(root), changed)
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
        lifecycle: str = "pre_handoff_validated",
        implementation_summary: str | None = None,
        human_steps: tuple[str, ...] = (),
        expected_result: str | None = None,
    ) -> CandidateIntegrationReceipt:
        tree = _git_text(self.checkout, "rev-parse", f"{commit}^{{tree}}")
        changed_paths = _changed_paths(self.checkout, base=integration_base)
        if not self._paths_match_execution(changed_paths, execution):
            raise CandidateIntegrationError("integrated commit has an unauthorized path set")
        if lifecycle not in {"candidate_ready", "pre_handoff_validated"}:
            raise CandidateIntegrationError("candidate receipt lifecycle is invalid")
        checks = [
            "ExecutionCrew contract-locality audit and semantic validator completed.",
            "candidate.patch SHA-256 matched crew_result.json.",
            (
                "candidate.patch applied cleanly in a disposable clone based on "
                "the ExecutionCrew source; current main remains owned by the merge gate."
                if lifecycle == "candidate_ready"
                else "Current origin/main was fetched immediately before candidate integration."
            ),
            (
                "The queued commit has not been handed to Vincent for testing."
                if lifecycle == "candidate_ready"
                else "candidate.patch applied cleanly with three-way resolution in a disposable clone based on current main."
            ),
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
            kind = "source" if validation["test_platform"] == "SyntheticSource" else "Unity"
            checks.append(
                f"Pre-handoff authoritative {kind} "
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
            lifecycle=lifecycle,
            implementation_summary=implementation_summary,
            human_steps=human_steps,
            expected_result=expected_result,
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
        if receipt.lifecycle not in {"candidate_ready", "pre_handoff_validated"}:
            raise CandidateIntegrationError("integration receipt lifecycle is invalid")
        if receipt.lifecycle == "candidate_ready" and (
            not isinstance(receipt.implementation_summary, str)
            or not receipt.implementation_summary.strip()
            or not receipt.human_steps
            or not isinstance(receipt.expected_result, str)
            or not receipt.expected_result.strip()
        ):
            raise CandidateIntegrationError(
                "queued candidate receipt omitted its eventual human checklist"
            )
        plan = self._pre_handoff_validation_plan()
        expected = (
            ()
            if receipt.lifecycle == "candidate_ready" or plan is None
            else tuple(
                (platform, plan["test_filters"][platform], plan["policy_sha256"])
                for platform in plan["required_test_platforms"]
            )
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
                # The location is recomputed from the controller root this
                # process owns; the persisted receipt never supplies a path.
                fact = self._pre_handoff_validation_fact(
                    resolve_controller_relative_path(
                        validation["manifest_relative_path"], self.state_root
                    ),
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
        # Resume is best-effort: an unusable receipt means the work is redone,
        # never that a defective one is adopted. `load_integration_receipt`
        # still distinguishes corruption from absence for consumers that must
        # refuse rather than silently re-execute.
        try:
            receipt = load_integration_receipt(self.state_path)
        except CandidateIntegrationError:
            return
        if receipt is None:
            return
        execution = self.execution.receipt
        if execution is None:
            return
        try:
            self._verify_receipt(receipt, execution)
        except CandidateIntegrationError:
            return
        self._receipt = receipt
