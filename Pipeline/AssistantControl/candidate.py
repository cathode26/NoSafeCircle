"""Register an authenticated ExecutionCrew result as a human-review candidate."""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import stat
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.reconciliation_binding import (
    ReconciliationBindingError,
    human_rejection_binding,
)
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan, validate_task_id
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge, ExecutionCrewReceipt
from Pipeline.TaskReviewAgent.local_candidate_commit import (
    LocalCandidateCommitReceipt,
    LocalCandidateCommitter,
)
from Pipeline.TaskReviewAgent.materialization_bridge import (
    MATERIALIZATION_REQUIRED_STATUS,
    registered_materialization_paths,
)
from Pipeline.TaskReviewAgent.pipeline_scope import (
    AcceptedExecutionScope,
    RepositoryScopeAuthority,
)
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


class CandidateRegistrationError(ValueError):
    """Candidate registration failed; the owned checkout and record are retained."""


BridgeFactory = Callable[..., Any]
CommitterFactory = Callable[..., Any]
# How long candidate registration waits for `checkouts.lock`. `_exclusive_file_lock`
# already retries the acquisition every 50 ms until this deadline, so a longer
# budget *is* the bounded retry. It has to be longer than the graph controller's
# 10 s: registration runs inside a detached post-crew child, and a child that
# loses this wait is recorded as a *failed job*, which blocks its task with
# `background_job_failed` until an operator runs `clear-background-job` (needed
# twice in the 20260913 Gauntlet run). Registration itself held this lock about
# 9 s in that run and a foreground `sync_candidate` 13-16 s, so 10 s could not
# cover one legitimate holder. Nothing is mutated before the lock is taken, so
# waiting costs nothing; the bound keeps a genuinely wedged lock loud.
REGISTRATION_LOCK_TIMEOUT_SECONDS = 300.0


def _cleanup_recovery(root: Path, records: Path) -> None:
    """Remove only the adapter-created disposable clone, including Windows read-only objects."""
    if not root.exists():
        return
    if not root.resolve().is_relative_to(records.resolve()):
        raise CandidateRegistrationError("candidate recovery cleanup escaped owned records")
    for directory, directories, files in os.walk(root, topdown=False):
        for name in (*files, *directories):
            path = Path(directory) / name
            try:
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
    shutil.rmtree(root)


def _read_record(checkouts: Checkouts, task_id: str) -> tuple[Path, dict[str, Any]]:
    task_id = validate_task_id(task_id)
    path = checkouts.records / f"{task_id}.json"
    if not path.is_file():
        raise CandidateRegistrationError("owned task checkout record does not exist")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateRegistrationError("owned task checkout record is unreadable") from exc
    expected = checkouts.root / task_id
    if (record.get("source") != str(checkouts.source)
            or record.get("task_id") != task_id
            or record.get("checkout") != str(expected)):
        raise CandidateRegistrationError("task checkout record identity differs")
    checkouts.observe(task_id)
    return path, record


def _scope(checkouts: Checkouts, record: Mapping[str, Any]) -> RepositoryScopeAuthority:
    raw = record.get("scope")
    if not isinstance(raw, Mapping):
        raise CandidateRegistrationError("task has no registered execution scope")
    try:
        plan = ExecutionScopePlan.from_dict(raw["plan"])
        accepted = AcceptedExecutionScope(
            plan_id=str(raw["plan_id"]), task_id=str(raw["task_id"]),
            lease_id=str(raw["lease_id"]), source_head=str(raw["source_head"]),
            task_contract_sha256=str(raw["task_contract_sha256"]), plan=plan,
        )
        if (accepted.task_id != record["task_id"]
                or accepted.source_head != record.get("source_commit")
                or accepted.task_contract_sha256 != record.get("task_contract_sha256")):
            raise ValueError("scope task identity differs")
        checkout = Path(record["checkout"])
        task = load_committed_task(
            checkout, accepted.task_id, commit=accepted.source_head,
            expected_sha256=accepted.task_contract_sha256,
        )
        authority = RepositoryScopeAuthority(
            checkout=checkout, task=task, lease_id=accepted.lease_id,
            expected_branch=str(record["branch"]),
            state_root=checkouts.records / ".scope-state",
        )
        registered = authority.require(accepted.plan_id)
        if registered.to_dict() != dict(raw):
            raise ValueError("registered scope differs from its authenticated scope receipt")
        return authority
    except Exception as exc:
        raise CandidateRegistrationError(
            "cannot safely reconstruct registered scope at candidate HEAD; retained state"
        ) from exc


def _recovery_scope_and_bridge(
    checkouts: Checkouts, record: Mapping[str, Any], config: Mapping[str, Any], run_id: str,
) -> tuple[RepositoryScopeAuthority, ExecutionCrewBridge, Path]:
    """Build both authorities in an owned disposable base clone for commit recovery."""
    checkout = Path(record["checkout"])
    recovery_root = checkouts.records / (".candidate-recovery-" + uuid.uuid4().hex)
    if not recovery_root.parent.resolve().is_relative_to(checkouts.records.resolve()):
        raise CandidateRegistrationError("candidate recovery path escaped owned records; retained state")
    try:
        current = git(checkout, "rev-parse", "HEAD").decode().strip()
        source_head = record.get("source_commit")
        if (git(checkout, "branch", "--show-current").decode().strip() != record.get("branch")
                or git(checkout, "status", "--porcelain=v1", "--untracked-files=all")
                or git(checkout, "rev-parse", "HEAD^").decode().strip() == ""
                or not source_head):
            raise ValueError("candidate checkout is not a clean child of its recorded base")
        if git(checkout, "rev-parse", "HEAD^").decode().strip() != source_head:
            raise ValueError("candidate checkout parent differs from its recorded base")

        recovery_root.mkdir(parents=True)
        clone = recovery_root / "base"
        clone.mkdir()
        git(clone, "init", "-q")
        git(clone, "fetch", "--no-tags", str(checkout), source_head,
            timeout_seconds=180)
        branch = str(record["branch"])
        git(clone, "checkout", "-b", branch, source_head)

        raw_scope = record.get("scope")
        if not isinstance(raw_scope, Mapping):
            raise ValueError("registered scope is missing")
        scope_state = recovery_root / ".scope-state" / f"{record['task_id']}.scope.json"
        scope_state.parent.mkdir(parents=True, exist_ok=True)
        write_record(scope_state, dict(raw_scope))
        task = load_committed_task(
            clone, str(record["task_id"]), commit=source_head,
            expected_sha256=record.get("task_contract_sha256"),
        )
        scope = RepositoryScopeAuthority(
            checkout=clone, task=task, lease_id=str(raw_scope["lease_id"]),
            expected_branch=branch, state_root=scope_state.parent,
        )
        accepted = scope.require(str(raw_scope["plan_id"]))
        if (accepted.source_head != record.get("source_commit")
                or accepted.task_contract_sha256 != record.get("task_contract_sha256")
                or accepted.to_dict() != dict(raw_scope)):
            raise ValueError("base clone scope differs from owned registered scope")

        execution_state = checkouts.root / ".task-review-agent" / f"{record['task_id']}.execution.json"
        if not execution_state.is_file():
            raise ValueError("authenticated ExecutionCrew receipt state is unavailable")
        recovery_execution = recovery_root / ".task-review-agent" / execution_state.name
        recovery_execution.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(execution_state, recovery_execution)
        bridge = ExecutionCrewBridge(
            checkout=clone, scope=scope, **_bridge_options(config),
        )
        verified = bridge.require(run_id)
        if (verified.task_id != record["task_id"] or verified.lease_id != accepted.lease_id
                or verified.plan_id != accepted.plan_id or verified.source_head != accepted.source_head
                or verified.task_contract_sha256 != accepted.task_contract_sha256):
            raise ValueError("recovered ExecutionCrew receipt differs from registered scope")
        return scope, bridge, recovery_root
    except Exception as exc:
        if recovery_root.exists():
            _cleanup_recovery(recovery_root, checkouts.records)
        raise CandidateRegistrationError(
            "cannot safely reconstruct scope at candidate HEAD; retained state"
        ) from exc


def _bridge_options(config: Mapping[str, Any]) -> dict[str, Any]:
    source = config.get("bridge", config)
    if not isinstance(source, Mapping):
        raise CandidateRegistrationError("candidate bridge config must be an object")
    allowed = {
        "execution_model", "execution_reasoning_effort", "crew_profile",
        "validation_profile", "command_runner", "timeout_seconds",
        "compose_project", "worker_slot_id", "session_pool_owner",
        "enable_session_pool", "provider_allowlist", "quota_fallback_provider",
        "provider_profile", "local_rehearsal_context", "allow_materialization_bridge",
    }
    options = {key: value for key, value in source.items() if key in allowed}
    # JSON configuration represents the bridge's tuple as an array. Preserve
    # ordering and contents so the bridge still rejects invalid provider routes.
    if isinstance(options.get("provider_allowlist"), list):
        options["provider_allowlist"] = tuple(options["provider_allowlist"])
    return options


def register_candidate(
    checkouts: Checkouts,
    task_id: str,
    run_id: str,
    config: Mapping[str, Any] | None = None,
    *,
    bridge_factory: BridgeFactory = ExecutionCrewBridge,
    committer_factory: CommitterFactory = LocalCandidateCommitter,
) -> dict[str, Any]:
    """Require one real bridge receipt, commit it through the shared committer, and persist review state."""
    task_id = validate_task_id(task_id)
    if type(run_id) is not str or not run_id.strip():
        raise CandidateRegistrationError("candidate registration requires a run_id")
    options = dict(config or {})
    with _exclusive_file_lock(
        checkouts.records / "checkouts.lock",
        timeout_seconds=REGISTRATION_LOCK_TIMEOUT_SECONDS,
    ):
        record_path, record = _read_record(checkouts, task_id)
        if (record.get("status") in {"integrating", "integrated", "approved", "changes_requested"}
                and (record.get("candidate") or {}).get("run_id") != run_id.strip()):
            raise CandidateRegistrationError("task is not accepting a new candidate")
        checkout = Path(record["checkout"])
        recovery_root: Path | None = None
        if git(checkout, "rev-parse", "HEAD").decode().strip() == record.get("source_commit"):
            scope = _scope(checkouts, record)
            bridge = bridge_factory(checkout=checkout, scope=scope, **_bridge_options(options))
        else:
            if bridge_factory is not ExecutionCrewBridge:
                raise CandidateRegistrationError(
                    "candidate HEAD recovery requires the real ExecutionCrewBridge; retained state"
                )
            scope, bridge, recovery_root = _recovery_scope_and_bridge(
                checkouts, record, options, run_id.strip()
            )
        try:
            execution = bridge.require(run_id.strip())
        except Exception as exc:
            if recovery_root is not None and recovery_root.exists():
                _cleanup_recovery(recovery_root, checkouts.records)
            raise CandidateRegistrationError(
                "ExecutionCrew receipt was not authenticated; candidate was not registered"
            ) from exc
        accepted = scope.accepted
        if accepted is None or not isinstance(execution, ExecutionCrewReceipt):
            if recovery_root is not None and recovery_root.exists():
                _cleanup_recovery(recovery_root, checkouts.records)
            raise CandidateRegistrationError("bridge did not return a verified real ExecutionCrew receipt")
        if (execution.run_id != run_id.strip() or execution.task_id != task_id
                or execution.lease_id != accepted.lease_id
                or execution.plan_id != accepted.plan_id
                or execution.source_head != accepted.source_head
                or execution.task_contract_sha256 != accepted.task_contract_sha256):
            if recovery_root is not None and recovery_root.exists():
                _cleanup_recovery(recovery_root, checkouts.records)
            raise CandidateRegistrationError("ExecutionCrew receipt identity differs from registered scope")

        # TWO WAYS A RUN CAN OWE FEEDBACK, ONE VERIFICATION. A `fresh` revision
        # binds the rejection through `record["revision"]`; a run dispatched after
        # `revise-on-source` withdrew a human-rejected candidate binds it through
        # the withdrawal entry, because a reconciliation makes the rejected commit
        # and the execution baseline different commits and the ordinary structure
        # cannot express that. Both must be checked, or the second one accepts a
        # candidate produced by a crew that was never given the feedback.
        expected_message = None
        if (record.get("revision") or {}).get("feedback_mode") == "fresh":
            expected_message = record["revision"]["rejected_review"]["message"]
        else:
            try:
                withdrawal = human_rejection_binding(record)
            except ReconciliationBindingError as exc:
                raise CandidateRegistrationError(str(exc)) from exc
            if withdrawal is not None:
                expected_message = withdrawal["rejected_review"]["message"]
        if expected_message is not None:
            # Read the same verified result bytes before accepting its feedback claim.
            result_bytes = Path(execution.result_path).read_bytes()
            if hashlib.sha256(result_bytes).hexdigest() != execution.result_sha256:
                raise CandidateRegistrationError("revision result changed after verification")
            result_data = json.loads(result_bytes)
            expected_feedback = expected_message.encode("utf-8")
            feedback_path = Path(execution.result_path).parent / "human_review_feedback.txt"
            if (result_data.get("revision_feedback_file") != feedback_path.name
                    or result_data.get("revision_feedback_sha256") != hashlib.sha256(expected_feedback).hexdigest()
                    or feedback_path.is_symlink() or feedback_path.read_bytes() != expected_feedback):
                raise CandidateRegistrationError("new crew result does not bind the exact rejection feedback")

        receipt_path = (checkouts.records / "candidate-receipts" / task_id /
                        (hashlib.sha256(run_id.strip().encode("utf-8")).hexdigest() + ".json"))
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        committer_options = options.get("committer", {})
        if not isinstance(committer_options, Mapping):
            raise CandidateRegistrationError("candidate committer config must be an object")
        allowed_committer = {"validation_source", "scratch_root"}
        if recovery_root is not None and "validation_source" not in committer_options:
            committer_options = {
                **committer_options, "validation_source": str(recovery_root / "base")}
        try:
            committer = committer_factory(
                checkout=checkout,
                task_title=str(options.get("task_title") or record.get("title") or task_id),
                scope=scope, execution=bridge, receipt_path=receipt_path,
                **{key: value for key, value in committer_options.items() if key in allowed_committer},
            )
            candidate: LocalCandidateCommitReceipt = committer.commit(run_id.strip())
            if candidate.run_id != run_id.strip() or candidate.task_id != task_id:
                raise CandidateRegistrationError("committer receipt identity differs from requested run")
            durable_candidate = {
                "commit": candidate.candidate_commit,
                "tree": candidate.candidate_tree,
                "parent": candidate.candidate_parent,
                "run_id": candidate.run_id,
                "lease_id": candidate.lease_id,
                "plan_id": candidate.plan_id,
                "receipt": candidate.to_dict(),
            }
            previous = record.get("candidate")
            if previous is not None and previous != durable_candidate:
                raise CandidateRegistrationError("existing candidate receipt differs; retained for inspection")
            if previous == durable_candidate:
                return record  # Re-observation must not erase Vincent's decision.
            record["candidate"] = durable_candidate
            # A deterministic Unity handoff is still pre-human: keep the
            # record in the materialization state until AssistantControl has
            # run the Windows builder and focused validations.
            if (execution.crew_status == MATERIALIZATION_REQUIRED_STATUS
                    and registered_materialization_paths(accepted.plan)):
                record["status"] = "needs_materialization"
            else:
                record["status"] = "awaiting_human"
            record["approval"] = None
            write_record(record_path, record)
            return record
        except CandidateRegistrationError:
            raise
        except Exception as exc:
            raise CandidateRegistrationError(
                "candidate commit failed; checkout and any commit-before-receipt state were retained"
            ) from exc
        finally:
            if recovery_root is not None and recovery_root.exists():
                _cleanup_recovery(recovery_root, checkouts.records)


class CandidateAdapter:
    """Small controller-facing wrapper around :func:`register_candidate`."""

    def __init__(self, checkouts: Checkouts) -> None:
        self.checkouts = checkouts

    def register(
        self, task_id: str, run_id: str, config: Mapping[str, Any] | None = None, *,
        bridge_factory: BridgeFactory = ExecutionCrewBridge,
        committer_factory: CommitterFactory = LocalCandidateCommitter,
    ) -> dict[str, Any]:
        return register_candidate(
            self.checkouts, task_id, run_id, config,
            bridge_factory=bridge_factory, committer_factory=committer_factory,
        )


register = register_candidate
