"""Verify, apply, commit, and push one review-ready ExecutionCrew candidate."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .contracts import TaskReviewContractError, semantic_sha256
from .execution_bridge import ExecutionCrewBridge, ExecutionCrewReceipt
from .pipeline_scope import RepositoryScopeAuthority
from .pre_handoff_unity_generation import (
    DOOR_PROTOTYPE_BUILDER_METHOD,
    PreHandoffUnityGenerationResult,
    PreHandoffUnityGenerator,
    accepted_scope_paths,
    door_prototype_builder_required,
    task_resource_paths,
)


INTEGRATION_SCHEMA_VERSION = "2.0"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


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
        *((f"{base}..HEAD",) if base is not None else ()),
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


def _path_set_sha256(paths: Iterable[str]) -> str:
    return semantic_sha256({"paths": list(paths)})


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
    candidate_changed_paths: tuple[str, ...]
    generated_changed_paths: tuple[str, ...]
    changed_paths: tuple[str, ...]
    unity_builder_required: bool
    unity_builder_ran: bool
    unity_builder_method: str | None
    unity_executable: str | None
    unity_log_path: str | None
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
            "candidate_changed_paths": list(self.candidate_changed_paths),
            "generated_changed_paths": list(self.generated_changed_paths),
            "changed_paths": list(self.changed_paths),
            "unity_builder_required": self.unity_builder_required,
            "unity_builder_ran": self.unity_builder_ran,
            "unity_builder_method": self.unity_builder_method,
            "unity_executable": self.unity_executable,
            "unity_log_path": self.unity_log_path,
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
        unity_executable: Path | str | None = None,
        unity_output_root: Path | str | None = None,
        unity_command_runner=None,
        hygiene_command_runner=None,
        unity_environment=None,
    ) -> None:
        self.checkout = Path(checkout).resolve()
        self.branch = str(branch).strip()
        self.task_title = str(task_title).strip()
        self.scope = scope
        self.execution = execution
        self.unity_executable = unity_executable
        self.unity_output_root = unity_output_root
        self.unity_command_runner = unity_command_runner
        self.hygiene_command_runner = hygiene_command_runner
        self.unity_environment = unity_environment
        if not self.branch or not self.task_title:
            raise CandidateIntegrationError("integration requires branch and task title")
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

        existing = self._existing_commit_for_run(execution)
        if existing is not None:
            existing_commit, generation = existing
            self._push_exact(existing_commit, execution.source_head)
            receipt = self._create_receipt(existing_commit, execution, generation)
            self._persist(receipt)
            self._receipt = receipt
            return receipt

        self._assert_checkout_identity(execution)
        candidate = Path(execution.candidate_path)
        self._validate_in_disposable_clone(candidate, execution)
        _git(self.checkout, "apply", "--check", "--", str(candidate))
        _git(self.checkout, "apply", "--", str(candidate))
        try:
            self._verify_applied_state(
                self.checkout,
                execution,
                expected_paths=execution.final_actual_changed_paths,
                phase="candidate application",
            )
            generation = PreHandoffUnityGenerator(
                checkout=self.checkout,
                task_id=self.scope.task_id,
                task=self.scope.task,
                scope=self.scope,
                unity_executable=self.unity_executable,
                output_root=self.unity_output_root,
                unity_command_runner=self.unity_command_runner,
                hygiene_command_runner=self.hygiene_command_runner,
                unity_environment=self.unity_environment,
            ).run(execution.final_actual_changed_paths)
            self._verify_applied_state(
                self.checkout,
                execution,
                expected_paths=generation.changed_paths,
                phase="post-generation workspace",
            )
            _git(self.checkout, "add", "--", *generation.changed_paths)
            staged_lines = _git_text(
                self.checkout,
                "diff",
                "--cached",
                "--name-only",
                "--",
            ).splitlines()
            staged = tuple(sorted((line for line in staged_lines if line), key=str.casefold))
            if staged != generation.changed_paths:
                raise CandidateIntegrationError(
                    f"staged paths differ from verified final path set: {staged} != "
                    f"{generation.changed_paths}"
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
                f"Pre-Handoff-Unity-Builder: "
                f"{generation.builder_method or 'not-required'}\n"
                f"Candidate-Changed-Paths-SHA256: "
                f"{_path_set_sha256(execution.final_actual_changed_paths)}\n"
                f"Generated-Changed-Paths-SHA256: "
                f"{_path_set_sha256(generation.generated_changed_paths)}\n"
                f"Final-Changed-Paths-SHA256: "
                f"{_path_set_sha256(generation.changed_paths)}\n"
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
        if parent != execution.source_head:
            raise CandidateIntegrationError("candidate commit parent is not ExecutionCrew source HEAD")
        if _changed_paths(self.checkout, base=execution.source_head) != generation.changed_paths:
            raise CandidateIntegrationError("integration commit changed an unexpected final path set")
        self._push_exact(commit, execution.source_head)
        receipt = self._create_receipt(commit, execution, generation)
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
    ) -> tuple[str, PreHandoffUnityGenerationResult] | None:
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
        message_lines = set(message.splitlines())
        if f"ExecutionCrew-Run: {execution.run_id}" not in message_lines:
            return None
        if f"ExecutionCrew-Candidate-SHA256: {execution.candidate_sha256}" not in message_lines:
            raise CandidateIntegrationError("existing integration commit has the wrong candidate SHA-256")
        parent = _git_text(self.checkout, "rev-parse", "HEAD^", check=False)
        if parent != execution.source_head:
            raise CandidateIntegrationError("existing integration commit has the wrong parent")
        changed_paths = _changed_paths(self.checkout, base=execution.source_head)
        candidate_paths = execution.final_actual_changed_paths
        missing_candidate = set(candidate_paths) - set(changed_paths)
        if missing_candidate:
            raise CandidateIntegrationError("existing integration commit omitted candidate paths")
        generated_paths = tuple(
            sorted(set(changed_paths) - set(candidate_paths), key=str.casefold)
        )
        required = door_prototype_builder_required(
            task=self.scope.task,
            candidate_changed_paths=candidate_paths,
            accepted_changed_paths=accepted_scope_paths(self.scope),
        )
        if generated_paths and not required:
            raise CandidateIntegrationError(
                "existing unrelated integration commit contains non-candidate paths"
            )
        authorized = set(task_resource_paths(self.scope.task)) | set(
            accepted_scope_paths(self.scope)
        )
        unauthorized = sorted(set(generated_paths) - authorized, key=str.casefold)
        if unauthorized:
            raise CandidateIntegrationError(
                "existing integration commit contains unauthorized generated paths: "
                + ", ".join(unauthorized)
            )
        builder_identity = (
            DOOR_PROTOTYPE_BUILDER_METHOD if required else "not-required"
        )
        required_trailers = {
            f"Pre-Handoff-Unity-Builder: {builder_identity}",
            f"Candidate-Changed-Paths-SHA256: {_path_set_sha256(candidate_paths)}",
            f"Generated-Changed-Paths-SHA256: {_path_set_sha256(generated_paths)}",
            f"Final-Changed-Paths-SHA256: {_path_set_sha256(changed_paths)}",
        }
        if required and not required_trailers.issubset(message_lines):
            raise CandidateIntegrationError(
                "existing builder-required commit lacks exact pre-handoff generation provenance"
            )
        if not required and any(
            line.startswith("Pre-Handoff-Unity-Builder:") for line in message_lines
        ) and not required_trailers.issubset(message_lines):
            raise CandidateIntegrationError(
                "existing integration commit has inconsistent path provenance"
            )
        generation = PreHandoffUnityGenerationResult(
            builder_required=required,
            builder_ran=required,
            builder_method=DOOR_PROTOTYPE_BUILDER_METHOD if required else None,
            unity_executable=None,
            log_path=None,
            snapshot_path=None,
            generated_changed_paths=generated_paths,
            changed_paths=changed_paths,
        )
        return head, generation

    def _validate_in_disposable_clone(
        self,
        candidate: Path,
        execution: ExecutionCrewReceipt,
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
            _git(clone, "checkout", "--detach", execution.source_head)
            _git(clone, "apply", "--check", "--", str(candidate))
            _git(clone, "apply", "--", str(candidate))
            self._verify_applied_state(
                clone,
                execution,
                expected_paths=execution.final_actual_changed_paths,
                phase="disposable candidate application",
            )

    def _verify_applied_state(
        self,
        root: Path,
        execution: ExecutionCrewReceipt,
        *,
        expected_paths: tuple[str, ...],
        phase: str,
    ) -> None:
        changed = _changed_paths(root)
        if changed != expected_paths:
            raise CandidateIntegrationError(
                f"{phase} paths differ from verified authority: {changed} != "
                f"{expected_paths}"
            )
        whitespace = _git(root, "diff", "--check", check=False)
        if whitespace.returncode != 0:
            raise CandidateIntegrationError(
                f"{phase} failed git diff --check:\n"
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
            raise CandidateIntegrationError(f"TaskGraph validation failed after {phase}")
        contract_path = str(
            self.scope.task.get("contract_path") or f"Tasks/{self.scope.task_id}.yaml"
        )
        contract = _git(root, "show", f"HEAD:{contract_path}", check=False)
        if contract.returncode != 0 or hashlib.sha256(contract.stdout).hexdigest() != execution.task_contract_sha256:
            raise CandidateIntegrationError(f"{phase} changed task-contract identity")

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
                    "task-review-agent@nosafecircle.invalid",
                ),
            )

    def _push_exact(self, commit: str, base_head: str) -> None:
        remote_before = _remote_head(self.checkout, self.branch)
        if remote_before not in (None, base_head, commit):
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
        generation: PreHandoffUnityGenerationResult,
    ) -> CandidateIntegrationReceipt:
        tree = _git_text(self.checkout, "rev-parse", f"{commit}^{{tree}}")
        checks = [
            "ExecutionCrew contract-locality audit and semantic validator completed.",
            "candidate.patch SHA-256 matched crew_result.json.",
            "candidate.patch applied cleanly in a disposable clone.",
            "candidate_changed_paths exactly matched ExecutionCrew final_actual_changed_paths.",
        ]
        if generation.builder_required:
            checks.extend(
                (
                    "Captured the applied candidate as the protected pre-Unity workspace baseline.",
                    f"Ran {DOOR_PROTOTYPE_BUILDER_METHOD} before staging or commit.",
                    "Inspected and cleaned proven-safe Unity workspace churn with the task ID.",
                    "Normalized preserved Unity text-resource EOL churn to each HEAD convention without changing semantic content.",
                    "generated_changed_paths contained only task-resource or accepted-scope paths.",
                )
            )
        checks.extend(
            (
                "The final changed_paths set exactly equaled candidate_changed_paths plus generated_changed_paths.",
                "git diff --check passed on the final pre-handoff workspace.",
                "TaskGraph validation passed on the final pre-handoff workspace.",
                "Implementation, tests, and authorized generated Unity output were committed on the canonical task branch.",
                "The exact clean commit was pushed as the remote task branch before human handoff.",
            )
        )
        return CandidateIntegrationReceipt(
            task_id=execution.task_id,
            lease_id=execution.lease_id,
            plan_id=execution.plan_id,
            run_id=execution.run_id,
            provider=execution.provider,
            branch=self.branch,
            base_head=execution.source_head,
            commit=commit,
            commit_tree=tree,
            task_contract_sha256=execution.task_contract_sha256,
            candidate_sha256=str(execution.candidate_sha256),
            candidate_changed_paths=execution.final_actual_changed_paths,
            generated_changed_paths=generation.generated_changed_paths,
            changed_paths=generation.changed_paths,
            unity_builder_required=generation.builder_required,
            unity_builder_ran=generation.builder_ran,
            unity_builder_method=generation.builder_method,
            unity_executable=generation.unity_executable,
            unity_log_path=generation.log_path,
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
            or receipt.candidate_changed_paths != execution.final_actual_changed_paths
        ):
            raise CandidateIntegrationError("integration receipt does not match ExecutionCrew run")
        expected_union = tuple(
            sorted(
                set(receipt.candidate_changed_paths)
                | set(receipt.generated_changed_paths),
                key=str.casefold,
            )
        )
        if receipt.changed_paths != expected_union:
            raise CandidateIntegrationError("integration receipt final path union is invalid")
        expected_builder = door_prototype_builder_required(
            task=self.scope.task,
            candidate_changed_paths=execution.final_actual_changed_paths,
            accepted_changed_paths=accepted_scope_paths(self.scope),
        )
        if receipt.unity_builder_required != expected_builder:
            raise CandidateIntegrationError("integration receipt has the wrong Unity builder trigger")
        if expected_builder:
            if (
                not receipt.unity_builder_ran
                or receipt.unity_builder_method != DOOR_PROTOTYPE_BUILDER_METHOD
            ):
                raise CandidateIntegrationError(
                    "builder-required integration receipt lacks completed builder identity"
                )
        elif (
            receipt.unity_builder_ran
            or receipt.unity_builder_method is not None
            or receipt.generated_changed_paths
        ):
            raise CandidateIntegrationError(
                "unrelated integration receipt contains Unity builder output"
            )
        authorized = set(task_resource_paths(self.scope.task)) | set(
            accepted_scope_paths(self.scope)
        )
        if not set(receipt.generated_changed_paths).issubset(authorized):
            raise CandidateIntegrationError(
                "integration receipt contains unauthorized generated paths"
            )
        head = _git_text(self.checkout, "rev-parse", "HEAD", check=False)
        branch = _git_text(self.checkout, "branch", "--show-current", check=False)
        status = _git_text(
            self.checkout,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        if head != receipt.commit or branch != receipt.branch or status:
            raise CandidateIntegrationError("integrated task checkout no longer matches its receipt")
        if _remote_head(self.checkout, receipt.branch) != receipt.commit:
            raise CandidateIntegrationError("integrated task commit is no longer the remote branch head")
        if _changed_paths(self.checkout, base=receipt.base_head) != receipt.changed_paths:
            raise CandidateIntegrationError("integrated commit path set changed")
        tree = _git_text(self.checkout, "rev-parse", f"{receipt.commit}^{{tree}}", check=False)
        if tree != receipt.commit_tree:
            raise CandidateIntegrationError("integrated commit tree differs from its receipt")

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
                candidate_changed_paths=tuple(identity["candidate_changed_paths"]),
                generated_changed_paths=tuple(identity["generated_changed_paths"]),
                changed_paths=tuple(identity["changed_paths"]),
                unity_builder_required=identity["unity_builder_required"],
                unity_builder_ran=identity["unity_builder_ran"],
                unity_builder_method=identity["unity_builder_method"],
                unity_executable=identity["unity_executable"],
                unity_log_path=identity["unity_log_path"],
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
