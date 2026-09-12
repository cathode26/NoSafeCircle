"""Create one verified local candidate commit without publication authority."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .candidate_integration import (
    CandidateCommitValidator,
    CandidateIntegrationError,
)
from .contracts import semantic_sha256
from .execution_bridge import ExecutionCrewBridge, ExecutionCrewReceipt
from .git_identity_guard import validated_agent_git_identity
from .pipeline_scope import RepositoryScopeAuthority


LOCAL_CANDIDATE_COMMIT_SCHEMA = "nsc-local-candidate-commit/v1"


@dataclass(frozen=True)
class LocalCandidateCommitReceipt:
    task_id: str
    lease_id: str
    plan_id: str
    run_id: str
    source_base: str
    candidate_commit: str
    candidate_tree: str
    candidate_parent: str
    task_contract_sha256: str
    execution_result_sha256: str
    candidate_patch_sha256: str
    changed_paths: tuple[str, ...]
    validation_sha256: str

    def body(self) -> dict[str, Any]:
        return {
            "schema": LOCAL_CANDIDATE_COMMIT_SCHEMA,
            "task_id": self.task_id,
            "lease_id": self.lease_id,
            "plan_id": self.plan_id,
            "run_id": self.run_id,
            "source_base": self.source_base,
            "candidate_commit": self.candidate_commit,
            "candidate_tree": self.candidate_tree,
            "candidate_parent": self.candidate_parent,
            "task_contract_sha256": self.task_contract_sha256,
            "execution_result_sha256": self.execution_result_sha256,
            "candidate_patch_sha256": self.candidate_patch_sha256,
            "changed_paths": list(self.changed_paths),
            "validation_sha256": self.validation_sha256,
        }

    def to_dict(self) -> dict[str, Any]:
        body = self.body()
        return {**body, "receipt_sha256": semantic_sha256(body)}


def _write_receipt(path: Path, receipt: LocalCandidateCommitReceipt) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=path.name + ".", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(receipt.to_dict(), stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise CandidateIntegrationError("local candidate receipt could not be persisted") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_local_candidate_commit(path: Path | str) -> LocalCandidateCommitReceipt | None:
    receipt_path = Path(path)
    if not receipt_path.is_file() or receipt_path.is_symlink():
        return None
    try:
        raw = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateIntegrationError("local candidate receipt is unreadable") from exc
    if not isinstance(raw, dict) or raw.get("schema") != LOCAL_CANDIDATE_COMMIT_SCHEMA:
        raise CandidateIntegrationError("local candidate receipt has the wrong schema")
    body = {key: value for key, value in raw.items() if key != "receipt_sha256"}
    if raw.get("receipt_sha256") != semantic_sha256(body):
        raise CandidateIntegrationError("local candidate receipt hash mismatch")
    required_text = (
        "task_id", "lease_id", "plan_id", "run_id", "source_base",
        "candidate_commit", "candidate_tree", "candidate_parent",
        "task_contract_sha256", "execution_result_sha256",
        "candidate_patch_sha256", "validation_sha256",
    )
    if any(type(raw.get(key)) is not str or not raw[key] for key in required_text):
        raise CandidateIntegrationError("local candidate receipt is incomplete")
    paths = raw.get("changed_paths")
    if not isinstance(paths, list) or not paths or any(type(item) is not str or not item for item in paths):
        raise CandidateIntegrationError("local candidate receipt changed paths are malformed")
    return LocalCandidateCommitReceipt(
        task_id=raw["task_id"], lease_id=raw["lease_id"], plan_id=raw["plan_id"],
        run_id=raw["run_id"], source_base=raw["source_base"],
        candidate_commit=raw["candidate_commit"], candidate_tree=raw["candidate_tree"],
        candidate_parent=raw["candidate_parent"],
        task_contract_sha256=raw["task_contract_sha256"],
        execution_result_sha256=raw["execution_result_sha256"],
        candidate_patch_sha256=raw["candidate_patch_sha256"],
        changed_paths=tuple(paths), validation_sha256=raw["validation_sha256"],
    )


def _git_text(root: Path, *args: str) -> str:
    result = subprocess.run(("git", "-C", str(root), *args), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False, timeout=600)
    if result.returncode:
        raise CandidateIntegrationError("local candidate Git command failed: " + " ".join(args))
    return result.stdout.decode("utf-8").strip()


def _changed_paths(root: Path, base: str) -> tuple[str, ...]:
    return tuple(sorted((line for line in _git_text(
        root, "diff", "--name-only", f"{base}..HEAD", "--").splitlines() if line), key=str.casefold))


class LocalCandidateCommitter:
    """Reuse candidate validation while stopping before queueing or publication."""

    def __init__(
        self, *, checkout: Path | str, task_title: str,
        scope: RepositoryScopeAuthority, execution: ExecutionCrewBridge,
        receipt_path: Path | str, validation_source: Path | str | None = None,
        scratch_root: Path | str | None = None,
    ) -> None:
        # CandidateIntegrator.__init__ intentionally refuses local mode and owns
        # production publication state. This local unit sets only the fields
        # used by its validation helpers and never calls a remote operation.
        self.checkout = Path(checkout).resolve()
        self.branch = _git_text(self.checkout, "symbolic-ref", "--short", "HEAD")
        self.task_title = str(task_title).strip()
        self.scope = scope
        self.execution = execution
        self.state_root = Path(receipt_path).resolve().parent
        self.scratch_root = Path(scratch_root).resolve() if scratch_root else self.state_root / "validation-scratch"
        self.validation_source = Path(validation_source).resolve() if validation_source else None
        self.state_path = Path(receipt_path).resolve()
        if not self.task_title:
            raise CandidateIntegrationError("local candidate title must be non-empty")
        self.validator = CandidateCommitValidator(
            checkout=self.checkout, branch=self.branch, scope=self.scope)

    def commit(self, run_id: str) -> LocalCandidateCommitReceipt:
        execution = self.execution.require(run_id)
        self._require_review_ready(execution)
        accepted = self.scope.accepted
        if accepted is None or (
            accepted.task_id != execution.task_id
            or accepted.lease_id != execution.lease_id
            or accepted.plan_id != execution.plan_id
            or accepted.source_head != execution.source_head
            or accepted.task_contract_sha256 != execution.task_contract_sha256
        ):
            raise CandidateIntegrationError("local candidate differs from accepted scope authority")
        generated_paths = self._verified_pipeline_generated_paths(execution)
        allowed_paths = {
            *accepted.plan.existing_implementation_paths,
            *accepted.plan.new_implementation_paths,
            *accepted.plan.existing_test_paths,
            *accepted.plan.new_test_paths,
            *generated_paths,
        }
        if not set(execution.final_actual_changed_paths).issubset(allowed_paths):
            raise CandidateIntegrationError("local candidate changed paths outside accepted scope")
        existing = load_local_candidate_commit(self.state_path)
        if existing is not None:
            self._verify_local_receipt(existing, execution)
            return existing
        recovered = self._recover_committed_candidate(execution)
        if recovered is not None:
            _write_receipt(self.state_path, recovered)
            return recovered

        self.validator.assert_checkout_identity(execution)
        candidate = Path(str(execution.candidate_path))
        self.validator.validate_in_disposable_clone(
            candidate, execution, base_head=execution.source_head, scratch_root=self.scratch_root,
            register_clone=self._register_validation_clone, validation_source=self.validation_source)
        self.validator.apply_candidate(self.checkout, candidate, execution)
        try:
            self.validator.verify_applied_state(self.checkout, execution)
            paths = execution.final_actual_changed_paths
            _git_text(self.checkout, "add", "--", *paths)
            staged = tuple(sorted(_git_text(
                self.checkout, "diff", "--cached", "--name-only", "--",
            ).splitlines(), key=str.casefold))
            if staged != paths:
                raise CandidateIntegrationError("local staged paths differ from verified candidate paths")
            if _git_text(self.checkout, "diff", "--name-only", "--"):
                raise CandidateIntegrationError("local candidate left unstaged tracked changes")
            if _git_text(self.checkout, "ls-files", "--others", "--exclude-standard"):
                raise CandidateIntegrationError("local candidate left unstaged untracked files")
            name, email = validated_agent_git_identity()
            _git_text(self.checkout, "config", "user.name", name)
            _git_text(self.checkout, "config", "user.email", email)
            _git_text(
                self.checkout, "commit", "-m",
                f"Implement {self.scope.task_id}: {self.task_title}", "-m",
                f"ExecutionCrew-Run: {execution.run_id}\n"
                f"ExecutionCrew-Result-SHA256: {execution.result_sha256}\n"
                f"ExecutionCrew-Candidate-SHA256: {execution.candidate_sha256}\n"
                f"Task-Contract-SHA256: {execution.task_contract_sha256}\n"
                "Local-Candidate-Only: true\n",
            )
        except Exception as exc:
            if _git_text(self.checkout, "rev-parse", "HEAD") == execution.source_head:
                _git_text(self.checkout, "reset", "--hard", execution.source_head)
                _git_text(self.checkout, "clean", "-fd", "--")
            raise CandidateIntegrationError(
                "local candidate evidence was preserved after commit preparation failed: " + str(exc)
            ) from exc

        commit = _git_text(self.checkout, "rev-parse", "HEAD")
        parent = _git_text(self.checkout, "rev-parse", "HEAD^")
        tree = _git_text(self.checkout, "rev-parse", "HEAD^{tree}")
        if parent != execution.source_head or _changed_paths(self.checkout, execution.source_head) != paths:
            raise CandidateIntegrationError("local candidate commit identity is invalid")
        receipt = self._receipt_for_commit(execution, commit=commit, tree=tree, parent=parent, paths=paths)
        _write_receipt(self.state_path, receipt)
        return receipt

    def _verified_pipeline_generated_paths(
        self,
        execution: ExecutionCrewReceipt,
    ) -> tuple[str, ...]:
        """Read only exact Unity sidecars from the hash-verified crew result."""

        try:
            result_bytes = Path(execution.result_path).read_bytes()
            if hashlib.sha256(result_bytes).hexdigest() != execution.result_sha256:
                raise CandidateIntegrationError(
                    "local candidate crew result changed while reading generated paths"
                )
            result = json.loads(result_bytes)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CandidateIntegrationError(
                "local candidate crew result cannot authenticate generated paths"
            ) from exc
        raw = result.get("pipeline_generated_paths")
        if raw is None:
            raw = []
        if not isinstance(raw, list) or any(type(path) is not str for path in raw):
            raise CandidateIntegrationError(
                "local candidate crew result has invalid pipeline-generated paths"
            )
        generated = tuple(sorted(raw, key=str.casefold))
        if len({path.casefold() for path in generated}) != len(generated):
            raise CandidateIntegrationError(
                "local candidate crew result has duplicate pipeline-generated paths"
            )
        accepted = self.scope.accepted
        assert accepted is not None
        new_paths = (
            *accepted.plan.new_implementation_paths,
            *accepted.plan.new_test_paths,
        )
        permitted = {f"{path}.meta" for path in new_paths}
        if any(path not in permitted for path in generated):
            raise CandidateIntegrationError(
                "local candidate pipeline-generated path is not an authorized new Unity .meta companion"
            )
        if not set(generated).issubset(execution.final_actual_changed_paths):
            raise CandidateIntegrationError(
                "local candidate pipeline-generated path is absent from final changed paths"
            )
        return generated

    def _receipt_for_commit(self, execution: ExecutionCrewReceipt, *, commit: str, tree: str,
                            parent: str, paths: tuple[str, ...]) -> LocalCandidateCommitReceipt:
        checks = (
            "execution receipt and candidate bytes reverified",
            "candidate applied in disposable clone",
            "TaskGraph validation passed",
            "exact changed paths committed with guarded identity",
            "no publication operation invoked",
        )
        return LocalCandidateCommitReceipt(
            task_id=execution.task_id, lease_id=execution.lease_id,
            plan_id=execution.plan_id, run_id=execution.run_id,
            source_base=execution.source_head, candidate_commit=commit,
            candidate_tree=tree, candidate_parent=parent,
            task_contract_sha256=execution.task_contract_sha256,
            execution_result_sha256=execution.result_sha256,
            candidate_patch_sha256=str(execution.candidate_sha256),
            changed_paths=paths, validation_sha256=semantic_sha256(list(checks)),
        )

    @staticmethod
    def _register_validation_clone(path: Path) -> None:
        from .local_execution_fence import current_local_context, register_local_candidate_clone
        context = current_local_context()
        if context is not None:
            register_local_candidate_clone(context, path)

    def _recover_committed_candidate(
        self, execution: ExecutionCrewReceipt,
    ) -> LocalCandidateCommitReceipt | None:
        head = _git_text(self.checkout, "rev-parse", "HEAD")
        if head == execution.source_head:
            return None
        if _git_text(self.checkout, "status", "--porcelain=v1", "--untracked-files=all"):
            raise CandidateIntegrationError("stranded local candidate checkout is dirty")
        parent = _git_text(self.checkout, "rev-parse", "HEAD^")
        message = _git_text(self.checkout, "show", "-s", "--format=%B", "HEAD")
        required = (
            f"ExecutionCrew-Run: {execution.run_id}",
            f"ExecutionCrew-Result-SHA256: {execution.result_sha256}",
            f"ExecutionCrew-Candidate-SHA256: {execution.candidate_sha256}",
            f"Task-Contract-SHA256: {execution.task_contract_sha256}",
            "Local-Candidate-Only: true",
        )
        paths = _changed_paths(self.checkout, execution.source_head)
        if parent != execution.source_head or any(item not in message for item in required):
            raise CandidateIntegrationError("existing local commit does not match ExecutionCrew evidence")
        if paths != execution.final_actual_changed_paths:
            raise CandidateIntegrationError("existing local commit changed the wrong paths")
        expected_tree = self.validator.expected_candidate_tree(
            Path(str(execution.candidate_path)), execution, base_head=execution.source_head,
            scratch_root=self.scratch_root, register_clone=self._register_validation_clone,
            validation_source=self.validation_source)
        actual_tree = _git_text(self.checkout, "rev-parse", "HEAD^{tree}")
        if actual_tree != expected_tree:
            raise CandidateIntegrationError(
                "existing local commit tree differs from authenticated candidate patch")
        contract_path = str(self.scope.task.get("contract_path")
                            or f"Tasks/{self.scope.task_id}.yaml")
        contract = subprocess.run(("git", "-C", str(self.checkout), "show", f"HEAD:{contract_path}"),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if (contract.returncode != 0 or hashlib.sha256(contract.stdout).hexdigest()
                != execution.task_contract_sha256):
            raise CandidateIntegrationError("existing local commit changed task-contract identity")
        return self._receipt_for_commit(
            execution, commit=head, tree=actual_tree,
            parent=parent, paths=paths)

    @staticmethod
    def _require_review_ready(execution: ExecutionCrewReceipt) -> None:
        if execution.crew_status not in {"review_ready", "materialization_required"}:
            raise CandidateIntegrationError(
                "local candidate requires review_ready or materialization_required ExecutionCrew output"
            )
        if execution.candidate_path is None or execution.candidate_sha256 is None:
            raise CandidateIntegrationError("review_ready output omitted candidate identity")
        if not execution.final_actual_changed_paths:
            raise CandidateIntegrationError("review_ready output has no changed paths")

    def _verify_local_receipt(
        self, receipt: LocalCandidateCommitReceipt, execution: ExecutionCrewReceipt,
    ) -> None:
        expected = (
            execution.task_id, execution.lease_id, execution.plan_id, execution.run_id,
            execution.source_head, execution.task_contract_sha256,
            execution.result_sha256, execution.candidate_sha256,
            execution.final_actual_changed_paths,
        )
        actual = (
            receipt.task_id, receipt.lease_id, receipt.plan_id, receipt.run_id,
            receipt.source_base, receipt.task_contract_sha256,
            receipt.execution_result_sha256, receipt.candidate_patch_sha256,
            receipt.changed_paths,
        )
        if actual != expected:
            raise CandidateIntegrationError("local candidate receipt differs from ExecutionCrew evidence")
        if (
            _git_text(self.checkout, "rev-parse", "HEAD") != receipt.candidate_commit
            or _git_text(self.checkout, "rev-parse", "HEAD^") != receipt.candidate_parent
            or _git_text(self.checkout, "rev-parse", "HEAD^{tree}") != receipt.candidate_tree
            or receipt.candidate_parent != execution.source_head
            or _changed_paths(self.checkout, execution.source_head) != receipt.changed_paths
            or _git_text(self.checkout, "status", "--porcelain=v1", "--untracked-files=all")
        ):
            raise CandidateIntegrationError("persisted local candidate commit no longer verifies")
