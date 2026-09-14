"""Chain the existing candidate and Door Prototype materialization steps.

This module launches no model provider, grants no human approval, and never
integrates, pushes, or publishes. It reuses ``register_candidate`` and
``materialize_candidate`` exactly as they exist; it does not reimplement their
Git, scope, receipt, or Unity-builder logic. Its only job is to run the two
steps for one exact crew run/candidate, classify the result the way Codex
needs it classified (ready for Vincent, blocked on Unity, or a validated
source defect), and return one compact JSON object.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from Pipeline.AssistantControl.candidate import (
    BridgeFactory,
    CommitterFactory,
    register_candidate,
)
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.AssistantControl.unity_materialization import (
    MaterializationError,
    ValidationRunner,
    _candidate_receipt,
    materialize_candidate,
)
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan, validate_task_id
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.door_prototype_materialization import (
    UnityCommandRunner,
    default_unity_command_runner,
    is_door_prototype_builder_output,
    is_unity_serialized,
    resolve_generated_builder,
)
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
from Pipeline.TaskReviewAgent.authoritative_candidate_validation import (
    AuthoritativeCandidateValidationError,
    AuthoritativeValidationPolicyUnavailable,
    policy_unavailable_reason,
    run_authoritative_candidate_validations,
)
from Pipeline.TaskReviewAgent.local_candidate_commit import LocalCandidateCommitter


SCHEMA_VERSION = "assistant-post-crew-workflow/v1"
# How long the post-validation record transaction waits for `checkouts.lock`.
# The validation it persists has already run: in the 20260913 Gauntlet run the
# 10 s budget threw away a finished 75 s Unity validation (NSC-1164 post-crew
# job 8b97d834..., 02:56:21Z) because a foreground `sync_candidate` held the
# lock for 16 s. This transaction is only a record read, verify and write, it
# holds nothing while it waits, and it re-verifies the exact candidate on
# acquisition, so waiting far longer than a launch does is safe and cheap; a
# launch has nothing to lose and is deferred by the graph controller instead.
VALIDATION_PERSIST_LOCK_TIMEOUT_SECONDS = 300.0


class PostCrewWorkflowError(ValueError):
    """The chained candidate/materialization workflow could not proceed safely."""


_REVIEW_ADVANCED_STATUSES = frozenset(
    {"approved", "changes_requested", "integrating", "integrated"}
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_record(checkouts: Checkouts, task_id: str) -> dict[str, Any] | None:
    path = checkouts.records / f"{task_id}.json"
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PostCrewWorkflowError("owned task checkout record is unreadable") from exc
    if not isinstance(record, dict):
        raise PostCrewWorkflowError("owned task checkout record must be an object")
    return record


def _persist_candidate_validation(
    checkouts: Checkouts,
    task_id: str,
    candidate_commit: str,
    *,
    validations: tuple[Mapping[str, Any], ...] | None = None,
    failure: Mapping[str, Any] | None = None,
    unavailable: str | None = None,
) -> dict[str, Any]:
    """Merge a completed validation into the latest exact candidate record.

    Validation can outlive the command that registered the candidate. Re-read
    under the checkout lock so a later human decision or integration receipt is
    never replaced by the stale pre-validation snapshot. The validation itself
    runs with the lock released, and this acquisition waits
    ``VALIDATION_PERSIST_LOCK_TIMEOUT_SECONDS`` rather than a launch's budget so
    a busy lock cannot discard evidence that has already been produced.
    """
    if sum(item is not None for item in (validations, failure, unavailable)) != 1:
        raise PostCrewWorkflowError("candidate validation outcome is ambiguous")
    with _exclusive_file_lock(
        checkouts.records / "checkouts.lock",
        timeout_seconds=VALIDATION_PERSIST_LOCK_TIMEOUT_SECONDS,
    ):
        latest = _read_record(checkouts, task_id)
        candidate = dict((latest or {}).get("candidate") or {})
        if candidate.get("commit") != candidate_commit:
            raise PostCrewWorkflowError(
                "candidate changed while authoritative validation was running; latest state was retained"
            )
        status = latest.get("status")
        if failure is not None:
            if status in _REVIEW_ADVANCED_STATUSES:
                raise PostCrewWorkflowError(
                    "authoritative validation failed after review state advanced; latest state was retained"
                )
            latest["status"] = "validation_failed"
            latest["approval"] = None
            latest["human_review"] = None
            latest["candidate_validation_failure"] = dict(failure)
            latest.pop("candidate_validation_unavailable", None)
        elif unavailable is not None:
            if status in _REVIEW_ADVANCED_STATUSES:
                raise PostCrewWorkflowError(
                    "validation policy became unavailable after review state advanced; latest state was retained"
                )
            candidate_view = copy.deepcopy(latest)
            candidate_view["status"] = "awaiting_human"
            ReviewGate(checkouts)._require_candidate(candidate_view, candidate_commit)
            previous_failure = latest.pop("candidate_validation_failure", None)
            if previous_failure is not None:
                history = latest.setdefault("candidate_validation_failure_history", [])
                if not isinstance(history, list):
                    raise PostCrewWorkflowError("candidate validation failure history is malformed")
                history.append(previous_failure)
            candidate.pop("authoritative_validations", None)
            latest["candidate"] = candidate
            latest["status"] = "awaiting_human"
            latest["approval"] = None
            latest["human_review"] = None
            latest["candidate_validation_unavailable"] = {
                "candidate_commit": candidate_commit,
                "automated_unity_validation": "not_run",
                "reason": unavailable,
                "observed_at": _now(),
            }
        else:
            candidate["authoritative_validations"] = [dict(item) for item in validations or ()]
            latest["candidate"] = candidate
            if status not in _REVIEW_ADVANCED_STATUSES:
                latest["status"] = "awaiting_human"
            latest.pop("candidate_validation_failure", None)
            latest.pop("candidate_validation_unavailable", None)
        write_record(checkouts.records / f"{task_id}.json", latest)
        return latest


def _registered_generated_paths(scope: Any) -> tuple[str, ...]:
    """Return Unity-builder-owned paths from one authenticated scope plan."""
    if not isinstance(scope, Mapping):
        raise PostCrewWorkflowError("registered execution scope is missing")
    try:
        plan = ExecutionScopePlan.from_dict(scope["plan"])
    except Exception as exc:
        raise PostCrewWorkflowError("registered execution scope is malformed") from exc
    implementation = (*plan.existing_implementation_paths, *plan.new_implementation_paths)
    return tuple(sorted(
        (path for path in implementation
         if is_door_prototype_builder_output(path) and is_unity_serialized(path)),
        key=str.casefold,
    ))


def _candidate_generated_paths(
    scope: Any, record: Mapping[str, Any], candidate: Mapping[str, Any],
) -> tuple[str, ...]:
    """Materialize only when this candidate actually changed the registered builder.

    A scope may reserve the scene for a possible builder edit. That reservation
    alone does not make a code-only candidate a scene-builder candidate.
    """
    generated = _registered_generated_paths(scope)
    if not generated:
        return ()
    try:
        changed = _candidate_receipt(record, candidate)["changed_paths"]
    except MaterializationError as exc:
        raise PostCrewWorkflowError("registered candidate receipt is invalid") from exc
    if any(path in changed for path in generated):
        raise PostCrewWorkflowError(
            "candidate edited a registered Unity-generated output; leave that output for the builder"
        )
    builder_sources = {
        resolve_generated_builder((path,))[1] for path in generated
    }
    return generated if builder_sources.intersection(changed) else ()


def _materialization_journal_path(checkouts: Checkouts, task_id: str, crew_candidate: str) -> Path:
    return checkouts.records / f"{task_id}.unity-materialization.{crew_candidate}.json"


def _read_journal(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        journal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return journal if isinstance(journal, dict) else None


def _exact_command(checkouts: Checkouts, command: str, task_id: str, *extra: str) -> str:
    def quote(value: str) -> str:
        if value and all(character not in value for character in " \t'`\""):
            return value
        return "'" + value.replace("'", "''") + "'"

    arguments = (
        "python", "-m", "Pipeline.AssistantControl",
        "--source", str(checkouts.source), "--checkout-root", str(checkouts.root),
        command, task_id, *extra,
    )
    return " ".join(quote(value) for value in arguments)


def _base_result(
    checkouts: Checkouts, task_id: str, checkout: str, crew_candidate_commit: str | None,
    *, status: str, materialized_candidate_commit: str | None = None,
    generated_paths: tuple[str, ...] = (), unity_log_path: str | None = None,
    focused_test_results: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "checkout": checkout,
        "crew_candidate_commit": crew_candidate_commit,
        "materialized_candidate_commit": materialized_candidate_commit,
        "generated_paths": list(generated_paths),
        "unity_log_path": unity_log_path,
        "focused_test_results": [dict(item) for item in focused_test_results],
        "status": status,
    }


def run_post_crew_workflow(
    checkouts: Checkouts,
    task_id: str,
    run_id: str,
    config: Mapping[str, Any] | None = None,
    *,
    unity_executable: Path | str | None = None,
    bridge_factory: BridgeFactory = ExecutionCrewBridge,
    committer_factory: CommitterFactory = LocalCandidateCommitter,
    unity_command_runner: UnityCommandRunner = default_unity_command_runner,
    validation_runner: ValidationRunner = run_authoritative_candidate_validations,
) -> dict[str, Any]:
    """Register a crew candidate, materialize it when a Unity builder applies, report.

    Idempotent: re-running with the same ``task_id``/``run_id`` after a crash
    recovers the same candidate/materialization outcome rather than creating a
    second commit. Never approves, integrates, pushes, publishes, or starts
    another crew; a failed or blocked outcome names the exact next command for
    Codex instead of acting on it.
    """
    task_id = validate_task_id(task_id)
    if type(run_id) is not str or not run_id.strip():
        raise PostCrewWorkflowError("post-crew workflow requires a run_id")
    run_id = run_id.strip()

    existing = _read_record(checkouts, task_id)
    existing_candidate = (existing or {}).get("candidate") or {}
    kind = existing_candidate.get("kind", "crew_reviewed") if existing_candidate else None
    if kind in {"unity_materialized", "unity_materialization_failed", "source_synchronized"}:
        originating_run = (existing_candidate.get("original_candidate") or {}).get("run_id")
    else:
        originating_run = existing_candidate.get("run_id")
    already_this_run = bool(existing_candidate) and originating_run == run_id

    if already_this_run and kind == "unity_materialization_failed":
        # materialize_candidate refuses to retry a validation-failed journal;
        # report its retained terminal state instead of calling it again.
        record = existing
        crew_candidate_commit = (existing_candidate.get("original_candidate") or {}).get("commit")
        checkout = str(record["checkout"])
        failure = record.get("materialization_failure") or {}
        return {
            **_base_result(
                checkouts, task_id, checkout, crew_candidate_commit,
                status="validation_failed",
                materialized_candidate_commit=existing_candidate.get("commit"),
                generated_paths=tuple(existing_candidate.get("changed_paths") or ()),
                unity_log_path=(existing_candidate.get("materialization") or {}).get("unity_log"),
            ),
            "validation_error": failure.get("validation_error"),
            "next_action_command": _exact_command(
                checkouts, "revise", task_id,
                "--candidate-commit", str(existing_candidate.get("commit")),
            ),
        }

    retained_validation_failure = (existing or {}).get("candidate_validation_failure") or {}
    if (already_this_run and kind == "crew_reviewed"
            and (existing or {}).get("status") == "validation_failed"
            and retained_validation_failure.get("candidate_commit")
            == existing_candidate.get("commit")):
        error = retained_validation_failure.get("validation_error")
        if (not isinstance(error, str)
                or not policy_unavailable_reason(task_id, error)
                or existing.get("approval") is not None
                or existing.get("human_review") is not None):
            return {
                **_base_result(
                    checkouts, task_id, str(existing["checkout"]),
                    existing_candidate.get("commit"), status="validation_failed",
                ),
                "validation_error": error,
                "next_action_command": _exact_command(
                    checkouts, "revise", task_id,
                    "--candidate-commit", str(existing_candidate.get("commit")),
                ),
            }
        # A policy omission is not a failed test. Recheck the retained exact,
        # clean candidate before allowing this same-run replay to proceed.
        candidate_view = copy.deepcopy(existing)
        candidate_view["status"] = "awaiting_human"
        ReviewGate(checkouts)._require_candidate(
            candidate_view, str(existing_candidate["commit"])
        )

    if already_this_run and kind in {"crew_reviewed", "unity_materialized", "source_synchronized"}:
        crew_candidate_commit = (
            (existing_candidate.get("original_candidate") or {}).get("commit")
            if kind == "unity_materialized"
            else existing_candidate.get("commit")
        )
    else:
        registered = register_candidate(
            checkouts, task_id, run_id, config,
            bridge_factory=bridge_factory, committer_factory=committer_factory,
        )
        crew_candidate_commit = (registered.get("candidate") or {}).get("commit")
        existing = registered

    if not isinstance(crew_candidate_commit, str) or not crew_candidate_commit:
        raise PostCrewWorkflowError("registered candidate has no commit identity")
    checkout = str(existing["checkout"])
    registered_scope = (
        existing_candidate.get("original_scope")
        if kind == "source_synchronized" else existing.get("scope")
    )
    original_candidate = (
        existing_candidate.get("original_candidate")
        if kind in {"unity_materialized", "source_synchronized"}
        else existing.get("candidate")
    )
    if not isinstance(original_candidate, Mapping):
        raise PostCrewWorkflowError("registered crew candidate is missing")
    generated = _candidate_generated_paths(registered_scope, existing, original_candidate)

    if not generated:
        candidate = (existing.get("candidate") or {})
        validations = tuple(candidate.get("authoritative_validations") or ())
        unavailable = (existing.get("candidate_validation_unavailable") or {})
        if (unavailable.get("candidate_commit") != crew_candidate_commit
                or unavailable.get("automated_unity_validation") != "not_run"
                or existing.get("status") != "awaiting_human"):
            unavailable = {}
        if not validations and not unavailable:
            task = load_committed_task(
                Path(checkout), task_id, commit=crew_candidate_commit,
                expected_sha256=str(existing["task_contract_sha256"]),
            )
            try:
                validations = validation_runner(
                    checkout=Path(checkout),
                    state_root=checkouts.records,
                    task=task,
                    task_id=task_id,
                    run_id=f"candidate-{crew_candidate_commit[:12]}",
                    commit=crew_candidate_commit,
                    unity_executable=unity_executable,
                    command_runner=unity_command_runner,
                    require_plan=True,
                    evidence_phase="post-candidate-validation",
                )
            except AuthoritativeValidationPolicyUnavailable as exc:
                existing = _persist_candidate_validation(
                    checkouts, task_id, crew_candidate_commit, unavailable=str(exc),
                )
                unavailable = existing["candidate_validation_unavailable"]
            except AuthoritativeCandidateValidationError as exc:
                failure = {
                    "candidate_commit": crew_candidate_commit,
                    "validation_error": str(exc),
                    "failed_at": _now(),
                }
                _persist_candidate_validation(
                    checkouts, task_id, crew_candidate_commit, failure=failure,
                )
                return {
                    **_base_result(
                        checkouts, task_id, checkout, crew_candidate_commit,
                        status="validation_failed",
                    ),
                    "validation_error": str(exc),
                    "next_action_command": _exact_command(
                        checkouts, "revise", task_id,
                        "--candidate-commit", crew_candidate_commit,
                    ),
                }
            else:
                existing = _persist_candidate_validation(
                    checkouts, task_id, crew_candidate_commit, validations=validations,
                )
        result_status = str(existing.get("status") or "awaiting_human")
        result = {
            **_base_result(
                checkouts, task_id, checkout, crew_candidate_commit,
                status=result_status,
                focused_test_results=validations,
            ),
            "unity_materialization": "not_applicable",
            "visual_reproduction_instructions": (
                f"This candidate did not change a registered Unity builder. Review the "
                f"code candidate at commit {crew_candidate_commit} in {checkout}."
            ),
        }
        if unavailable:
            result["automated_unity_validation"] = "not_run"
            result["validation_note"] = (
                f"Automated Unity validation did not run: {unavailable['reason']}. "
                "Vincent must review this exact candidate; no test pass is recorded."
            )
        return result

    try:
        materialized = materialize_candidate(
            checkouts, task_id, crew_candidate_commit,
            unity_executable=unity_executable,
            unity_command_runner=unity_command_runner,
            validation_runner=validation_runner,
        )
    except MaterializationError as exc:
        journal_path = _materialization_journal_path(checkouts, task_id, crew_candidate_commit)
        journal = _read_journal(journal_path)
        phase = journal.get("phase") if journal else None
        failed_record = _read_record(checkouts, task_id) or {}
        failure = failed_record.get("materialization_failure") or {}
        if (failed_record.get("status") == "needs_materialization"
                and failure.get("phase") == "preflight_failed"
                and failure.get("original_candidate_commit") == crew_candidate_commit):
            return {
                **_base_result(
                    checkouts, task_id, checkout, crew_candidate_commit,
                    status="NEEDS_MATERIALIZATION",
                    generated_paths=generated,
                ),
                "materialization_error": failure.get("materialization_error") or str(exc),
                "materialization_record_path": str(
                    checkouts.records / f"{task_id}.json"
                ),
                "next_action_command": _exact_command(
                    checkouts, "materialize-candidate", task_id,
                    "--candidate-commit", crew_candidate_commit,
                ),
            }
        if (failed_record.get("status") == "materialization_failed"
                and failure.get("original_candidate_commit") == crew_candidate_commit):
            return {
                **_base_result(
                    checkouts, task_id, checkout, crew_candidate_commit,
                    status="materialization_failed",
                    generated_paths=generated,
                ),
                "materialization_error": failure.get("materialization_error") or str(exc),
                "materialization_journal_path": str(journal_path),
            }
        if phase == "validation_failed":
            record = _read_record(checkouts, task_id) or {}
            candidate = record.get("candidate") or {}
            failure = record.get("materialization_failure") or {}
            return {
                **_base_result(
                    checkouts, task_id, checkout, crew_candidate_commit,
                    status="validation_failed",
                    materialized_candidate_commit=candidate.get("commit"),
                    generated_paths=tuple(candidate.get("changed_paths") or generated),
                    unity_log_path=(candidate.get("materialization") or {}).get("unity_log"),
                ),
                "validation_error": failure.get("validation_error"),
                "next_action_command": _exact_command(
                    checkouts, "revise", task_id,
                    "--candidate-commit", str(candidate.get("commit")),
                ),
            }
        # An unrecognized failure shape (for example a scope/receipt defect
        # caught before any journal was written) is not safe to auto-classify
        # as either recognized outcome; retain state and surface it plainly.
        raise

    candidate = materialized["candidate"]
    materialization = candidate.get("materialization") or {}
    if task_id == "NSC-042":
        visual_instructions = (
            f"Open {checkout} in Unity Editor at commit {candidate.get('commit')}. "
            "Open Assets/Scenes/DoorPrototype.unity and inspect at least three "
            "adjacent wall segments for a continuous seamless course (see the "
            "NSC-042 lesson in Docs/AI-Pipeline/GAME_TASK_LESSONS_LEARNED.md). "
            "A passing focused test does not by itself prove the wall looks right."
        )
    else:
        visual_instructions = (
            f"Open {checkout} in Unity Editor at commit {candidate.get('commit')} and "
            f"visually test the task's acceptance criteria and generated paths: "
            + ", ".join(candidate.get("changed_paths") or generated)
            + "."
        )
    return {
        **_base_result(
            checkouts, task_id, checkout, crew_candidate_commit,
            status="awaiting_human",
            materialized_candidate_commit=candidate.get("commit"),
            generated_paths=tuple(candidate.get("changed_paths") or generated),
            unity_log_path=materialization.get("unity_log"),
            focused_test_results=tuple(candidate.get("authoritative_validations") or ()),
        ),
        "visual_reproduction_instructions": visual_instructions,
    }


__all__ = ["PostCrewWorkflowError", "run_post_crew_workflow"]
