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
from typing import Any, Sequence

from .contracts import TaskReviewContractError, semantic_sha256
from .execution_bridge import ExecutionCrewBridge, ExecutionCrewReceipt
from .pipeline_scope import RepositoryScopeAuthority


INTEGRATION_SCHEMA_VERSION = "1.0"
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
    ) -> None:
        self.checkout = Path(checkout).resolve()
        self.branch = str(branch).strip()
        self.task_title = str(task_title).strip()
        self.scope = scope
        self.execution = execution
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

        existing_commit = self._existing_commit_for_run(execution)
        if existing_commit is not None:
            self._push_exact(existing_commit, execution.source_head)
            receipt = self._create_receipt(existing_commit, execution)
            self._persist(receipt)
            self._receipt = receipt
            return receipt

        self._assert_checkout_identity(execution)
        candidate = Path(execution.candidate_path)
        self._validate_in_disposable_clone(candidate, execution)
        _git(self.checkout, "apply", "--check", "--", str(candidate))
        _git(self.checkout, "apply", "--", str(candidate))
        try:
            self._verify_applied_state(self.checkout, execution)
            _git(self.checkout, "add", "--", *execution.final_actual_changed_paths)
            staged_lines = _git_text(
                self.checkout,
                "diff",
                "--cached",
                "--name-only",
                "--",
            ).splitlines()
            staged = tuple(sorted((line for line in staged_lines if line), key=str.casefold))
            if staged != execution.final_actual_changed_paths:
                raise CandidateIntegrationError(
                    f"staged paths differ from verified candidate: {staged} != "
                    f"{execution.final_actual_changed_paths}"
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
        if parent != execution.source_head:
            raise CandidateIntegrationError("candidate commit parent is not ExecutionCrew source HEAD")
        if _changed_paths(self.checkout, base=execution.source_head) != execution.final_actual_changed_paths:
            raise CandidateIntegrationError("candidate commit changed an unexpected path set")
        self._push_exact(commit, execution.source_head)
        receipt = self._create_receipt(commit, execution)
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

    def _existing_commit_for_run(self, execution: ExecutionCrewReceipt) -> str | None:
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
        if parent != execution.source_head:
            raise CandidateIntegrationError("existing integration commit has the wrong parent")
        if _changed_paths(self.checkout, base=execution.source_head) != execution.final_actual_changed_paths:
            raise CandidateIntegrationError("existing integration commit has the wrong path set")
        return head

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
            self._verify_applied_state(clone, execution)

    def _verify_applied_state(
        self,
        root: Path,
        execution: ExecutionCrewReceipt,
    ) -> None:
        changed = _changed_paths(root)
        if changed != execution.final_actual_changed_paths:
            raise CandidateIntegrationError(
                f"applied candidate paths differ from ExecutionCrew result: {changed} != "
                f"{execution.final_actual_changed_paths}"
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
    ) -> CandidateIntegrationReceipt:
        tree = _git_text(self.checkout, "rev-parse", f"{commit}^{{tree}}")
        checks = (
            "ExecutionCrew contract-locality audit and semantic validator completed.",
            "candidate.patch SHA-256 matched crew_result.json.",
            "candidate.patch applied cleanly in a disposable clone.",
            "Applied path set exactly matched ExecutionCrew final_actual_changed_paths.",
            "git diff --check passed.",
            "TaskGraph validation passed after candidate application.",
            "Implementation and tests were committed on the canonical task branch.",
            "The exact commit was pushed as the remote task branch.",
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
            changed_paths=execution.final_actual_changed_paths,
            completed_checks=checks,
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
