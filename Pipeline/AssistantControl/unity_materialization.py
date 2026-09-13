"""Materialize and test an exact crew-reviewed Door Prototype candidate.

This operation is explicit. It runs no model provider and grants no human
approval. Unity-generated assets become a second candidate commit only after
their paths and committed task identity are authenticated. The committed
validation policy then runs against that exact clean commit. Test failure is
recorded as feedback for the assistant to give to the next crew.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from Pipeline.AssistantControl.admission import _source_registry_paths
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.review import _source_integration_lock
from Pipeline.AssistantControl.source_update import (
    _require_no_active_reservation,
    _require_settled_worker,
)
from Pipeline.TaskReviewAgent.authoritative_candidate_validation import (
    AuthoritativeCandidateValidationError,
    run_authoritative_candidate_validations,
)
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan, semantic_sha256, validate_task_id
from Pipeline.TaskReviewAgent.door_prototype_materialization import (
    DoorPrototypeMaterializationError,
    UnityCommandRunner,
    default_unity_command_runner,
    is_door_prototype_builder_output,
    is_unity_serialized,
    resolve_generated_builder,
    resolve_unity_executable,
    run_door_prototype_builder,
)
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
ValidationRunner = Callable[..., tuple[dict[str, Any], ...]]


class MaterializationError(ValueError):
    """The candidate could not be materialized and validated safely."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaterializationError(f"{field} is unreadable") from exc
    if not isinstance(value, dict):
        raise MaterializationError(f"{field} must be an object")
    return value


def _candidate_receipt(record: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    receipt = candidate.get("receipt")
    if not isinstance(receipt, Mapping):
        raise MaterializationError("candidate has no authenticated crew commit receipt")
    receipt = dict(receipt)
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if (receipt.get("schema") != "nsc-local-candidate-commit/v1"
            or receipt.get("receipt_sha256") != semantic_sha256(body)):
        raise MaterializationError("candidate crew commit receipt hash is invalid")
    expected = {
        "task_id": record.get("task_id"),
        "task_contract_sha256": record.get("task_contract_sha256"),
        "candidate_commit": candidate.get("commit"),
        "candidate_tree": candidate.get("tree"),
        "candidate_parent": candidate.get("parent"),
        "plan_id": candidate.get("plan_id"),
        "lease_id": candidate.get("lease_id"),
    }
    if any(not value or receipt.get(key) != value for key, value in expected.items()):
        raise MaterializationError("candidate crew commit receipt identity differs")
    changed = receipt.get("changed_paths")
    if (not isinstance(changed, list) or not changed
            or any(type(path) is not str or not path for path in changed)
            or changed != sorted(set(changed), key=str.casefold)):
        raise MaterializationError("candidate crew changed paths are malformed")
    return receipt


def _generated_paths(scope: Mapping[str, Any], crew_paths: list[str]) -> tuple[str, ...]:
    try:
        plan = ExecutionScopePlan.from_dict(scope["plan"])
    except Exception as exc:
        raise MaterializationError("registered execution scope is malformed") from exc
    implementation = (*plan.existing_implementation_paths, *plan.new_implementation_paths)
    generated = tuple(sorted(
        (path for path in implementation
         if is_door_prototype_builder_output(path) and is_unity_serialized(path)),
        key=str.casefold,
    ))
    if not generated:
        raise MaterializationError("scope registers no Unity asset for a registered Unity builder")
    overlap = sorted(set(generated).intersection(crew_paths), key=str.casefold)
    if overlap:
        raise MaterializationError(
            "crew candidate already edited Unity-generated payloads instead of leaving them "
            f"for deterministic materialization: {overlap}"
        )
    return generated


def _generated_resource_roots(
    task: Mapping[str, Any], checkout: Path, commit: str, crew_paths: list[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return committed task-owned directories and required parent folder metas.

    ExecutionCrew still receives exact-file write authority. This additional
    authority belongs only to the deterministic Windows Unity builder, which
    must import a task-owned art directory containing many source frames.
    """
    roots: set[str] = set()
    companions: set[str] = set()
    for resource in task.get("exclusive_resources") or []:
        if not isinstance(resource, str):
            continue
        kind, separator, value = resource.partition(":")
        path = value.replace("\\", "/").strip("/")
        if not separator or kind != "repo-file" or not path:
            continue
        if not is_door_prototype_builder_output(path):
            continue
        try:
            object_type = git(checkout, "cat-file", "-t", f"{commit}:{path}").decode().strip()
        except RuntimeError:
            continue
        if object_type != "tree":
            continue
        roots.add(path)
        current = Path(path)
        while str(current).replace("\\", "/").startswith(
            "Assets/NoSafeCircle/DoorPrototype/"
        ):
            meta = str(current).replace("\\", "/") + ".meta"
            try:
                git(checkout, "cat-file", "-e", f"{commit}:{meta}")
            except RuntimeError:
                companions.add(meta)
            current = current.parent

    overlaps = sorted(
        (
            path for path in crew_paths
            if is_unity_serialized(path) and any(
                path.casefold().startswith(root.casefold() + "/") for root in roots
            )
        ),
        key=str.casefold,
    )
    if overlaps:
        raise MaterializationError(
            "crew candidate already edited Unity-generated payloads instead of leaving them "
            f"for deterministic materialization: {overlaps}"
        )
    return (
        tuple(sorted(roots, key=str.casefold)),
        tuple(sorted(companions, key=str.casefold)),
    )


def _require_candidate(
    checkouts: Checkouts, record: Mapping[str, Any], expected_candidate: str,
) -> tuple[Path, dict[str, Any], dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    if record.get("task_id") is None or record.get("source") != str(checkouts.source):
        raise MaterializationError("owned task record identity differs")
    if (record.get("status") not in {"awaiting_human", "needs_materialization"}
            or record.get("approval") is not None
            or record.get("human_review") is not None):
        raise MaterializationError(
            "materialization requires the exact unreviewed candidate"
        )
    candidate = record.get("candidate")
    if not isinstance(candidate, Mapping) or candidate.get("commit") != expected_candidate:
        raise MaterializationError("candidate commit differs from the exact request")
    candidate = dict(candidate)
    if (candidate.get("kind", "crew_reviewed") != "crew_reviewed"
            or candidate.get("crew_review", True) is not True):
        raise MaterializationError("only a crew-reviewed code candidate can be materialized")
    receipt = _candidate_receipt(record, candidate)
    scope = record.get("scope")
    if (not isinstance(scope, Mapping) or scope.get("task_id") != record.get("task_id")
            or scope.get("task_contract_sha256") != record.get("task_contract_sha256")
            or scope.get("plan_id") != candidate.get("plan_id")
            or scope.get("lease_id") != candidate.get("lease_id")):
        raise MaterializationError("candidate scope binding differs")
    generated = _generated_paths(scope, receipt["changed_paths"])
    try:
        _build_method, builder_source = resolve_generated_builder(generated)
    except DoorPrototypeMaterializationError as exc:
        raise MaterializationError(str(exc)) from exc
    if builder_source not in receipt["changed_paths"]:
        raise MaterializationError(
            f"crew candidate did not change the {builder_source} builder"
        )
    checkout = Path(str(record.get("checkout", ""))).resolve()
    observed = checkouts.observe(str(record["task_id"]))
    if (Path(observed["checkout"]).resolve() != checkout
            or observed.get("branch") != record.get("branch")
            or observed.get("current_commit") != expected_candidate
            or observed.get("local_changes")):
        raise MaterializationError("candidate checkout is not the exact clean owned commit")
    if git(checkout, "rev-parse", "HEAD^{tree}").decode().strip() != candidate.get("tree"):
        raise MaterializationError("candidate checkout tree differs")
    task = load_committed_task(
        checkout, str(record["task_id"]), commit=expected_candidate,
        expected_sha256=str(record["task_contract_sha256"]),
    )
    roots, companions = _generated_resource_roots(
        task, checkout, expected_candidate, receipt["changed_paths"],
    )
    generated = tuple(sorted(set(generated).union(companions), key=str.casefold))
    return checkout, candidate, receipt, generated, roots


def _finalize(
    record_path: Path, record: dict[str, Any], journal: Mapping[str, Any],
) -> dict[str, Any]:
    previous = copy.deepcopy(record.get("candidate"))
    lineage = record.get("candidate_lineage")
    if not isinstance(lineage, list):
        lineage = []
    lineage.append({
        "kind": (previous or {}).get("kind", "crew_reviewed"),
        "candidate": previous,
        "approval": copy.deepcopy(record.get("approval")),
        "human_review": copy.deepcopy(record.get("human_review")),
        "source_commit": record.get("source_commit"),
    })
    record["candidate_lineage"] = lineage
    record["candidate"] = {
        "kind": "unity_materialized",
        "crew_review": False,
        "source_candidate_crew_review": True,
        "commit": journal["materialized_commit"],
        "tree": journal["materialized_tree"],
        "parent": journal["original_candidate_commit"],
        "task_contract_sha256": journal["task_contract_sha256"],
        "plan_id": journal["plan_id"],
        "lease_id": journal["lease_id"],
        "changed_paths": list(journal["materialized_paths"]),
        "original_candidate": previous,
        "materialization": {
            "builder": journal["builder"],
            "unity_executable": journal["unity_executable"],
            "unity_log": journal["unity_log"],
            "restored_tracked_paths": list(journal["restored_tracked_paths"]),
            "normalized_paths": list(journal["normalized_paths"]),
        },
        "authoritative_validations": list(journal["authoritative_validations"]),
    }
    record["approval"] = None
    record["human_review"] = None
    record["status"] = "awaiting_human"
    record.pop("materialization_failure", None)
    write_record(record_path, record)
    return record


def _finalize_validation_failure(
    record_path: Path, record: dict[str, Any], journal: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish a failed exact commit as machine feedback, never human approval."""
    previous = copy.deepcopy(record.get("candidate"))
    lineage = record.get("candidate_lineage")
    if not isinstance(lineage, list):
        lineage = []
    lineage.append({
        "kind": (previous or {}).get("kind", "crew_reviewed"),
        "candidate": previous,
        "approval": copy.deepcopy(record.get("approval")),
        "human_review": copy.deepcopy(record.get("human_review")),
        "source_commit": record.get("source_commit"),
    })
    record["candidate_lineage"] = lineage
    record["candidate"] = {
        "kind": "unity_materialization_failed",
        "crew_review": False,
        "source_candidate_crew_review": True,
        "commit": journal["materialized_commit"],
        "tree": journal["materialized_tree"],
        "parent": journal["original_candidate_commit"],
        "task_contract_sha256": journal["task_contract_sha256"],
        "plan_id": journal["plan_id"],
        "lease_id": journal["lease_id"],
        "changed_paths": list(journal["materialized_paths"]),
        "original_candidate": previous,
        "materialization": {
            "builder": journal["builder"],
            "unity_executable": journal["unity_executable"],
            "unity_log": journal["unity_log"],
            "restored_tracked_paths": list(journal["restored_tracked_paths"]),
            "normalized_paths": list(journal["normalized_paths"]),
        },
        "validation_failure": {
            "error": journal["validation_error"],
            "failed_at": journal["failed_at"],
        },
    }
    record["approval"] = None
    record["human_review"] = None
    record["status"] = "validation_failed"
    record["materialization_failure"] = dict(journal)
    write_record(record_path, record)
    return record


def _record_materialization_failure(
    record_path: Path,
    record: dict[str, Any],
    failure: Mapping[str, Any],
    *,
    status: str,
) -> None:
    record["approval"] = None
    record["human_review"] = None
    record["status"] = status
    record["materialization_failure"] = dict(failure)
    write_record(record_path, record)


def materialize_candidate(
    checkouts: Checkouts,
    task_id: str,
    expected_candidate: str,
    *,
    unity_executable: Path | str | None = None,
    unity_command_runner: UnityCommandRunner = default_unity_command_runner,
    validation_runner: ValidationRunner = run_authoritative_candidate_validations,
    timeout_seconds: float = 1800.0,
) -> dict[str, Any]:
    """Generate Unity assets, commit them, and run exact committed validation."""
    task_id = validate_task_id(task_id)
    if not _SHA40.fullmatch(expected_candidate):
        raise MaterializationError("candidate commit must be an exact lowercase Git SHA")
    record_path = checkouts.records / f"{task_id}.json"
    journal_path = (
        checkouts.records
        / f"{task_id}.unity-materialization.{expected_candidate}.json"
    )
    registry_lock, _ = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        record = _read(record_path, "owned task record")
        if journal_path.is_file():
            journal = _read(journal_path, "Unity materialization journal")
            current = git(Path(record["checkout"]), "rev-parse", "HEAD").decode().strip()
            candidate = record.get("candidate") or {}
            if (journal.get("phase") == "validated"
                    and journal.get("original_candidate_commit") == expected_candidate
                    and current == journal.get("materialized_commit")):
                if (candidate.get("kind") == "unity_materialized"
                        and candidate.get("commit") == current):
                    return record
                if candidate.get("commit") == expected_candidate:
                    return _finalize(record_path, record, journal)
            raise MaterializationError(
                f"unfinished Unity materialization was retained at {journal_path}"
            )
        _require_settled_worker(record)
        with _source_integration_lock(checkouts.source), _exclusive_file_lock(
            registry_lock, timeout_seconds=10,
        ):
            _require_no_active_reservation(checkouts, task_id)
            checkout, candidate, receipt, generated, generated_roots = _require_candidate(
                checkouts, record, expected_candidate,
            )
            build_method, _builder_source = resolve_generated_builder(generated)
            task = load_committed_task(
                checkout, task_id, commit=expected_candidate,
                expected_sha256=str(record["task_contract_sha256"]),
            )
            try:
                resolved_unity = resolve_unity_executable(checkout, unity_executable)
            except DoorPrototypeMaterializationError as exc:
                failure = {
                    "schema_version": "assistant-unity-materialization/v1",
                    "phase": "preflight_failed",
                    "task_id": task_id,
                    "original_candidate_commit": expected_candidate,
                    "original_candidate_tree": candidate["tree"],
                    "task_contract_sha256": record["task_contract_sha256"],
                    "plan_id": candidate["plan_id"],
                    "lease_id": candidate["lease_id"],
                    "registered_generated_paths": list(generated),
                    "registered_generated_roots": list(generated_roots),
                    "builder": build_method,
                    "materialization_error": str(exc),
                    "retryable": True,
                    "failed_at": _now(),
                }
                _record_materialization_failure(
                    record_path, record, failure, status="needs_materialization",
                )
                raise MaterializationError(
                    f"Unity materialization is unavailable before launch: {exc}"
                ) from exc
            journal: dict[str, Any] = {
                "schema_version": "assistant-unity-materialization/v1",
                "phase": "starting",
                "task_id": task_id,
                "original_candidate_commit": expected_candidate,
                "original_candidate_tree": candidate["tree"],
                "task_contract_sha256": record["task_contract_sha256"],
                "plan_id": candidate["plan_id"],
                "lease_id": candidate["lease_id"],
                "registered_generated_paths": list(generated),
                "registered_generated_roots": list(generated_roots),
                "builder": build_method,
                "started_at": _now(),
            }
            write_record(journal_path, journal)
            try:
                materialized = run_door_prototype_builder(
                    checkout=checkout,
                    task_id=task_id,
                    state_root=checkouts.records,
                    initial_changed_paths=(),
                    unity_executable=resolved_unity,
                    unity_command_runner=unity_command_runner,
                    timeout_seconds=timeout_seconds,
                    allowed_generated_paths=generated,
                    allowed_generated_roots=generated_roots,
                )
                if not materialized.builder_paths:
                    raise MaterializationError(
                        "Unity builder produced no changed generated assets for this candidate"
                    )
                try:
                    git(checkout, "diff", "--check")
                except RuntimeError as exc:
                    raise MaterializationError(
                        "materialized Unity output failed git diff --check"
                    ) from exc
                name, email = validated_agent_git_identity()
                git(checkout, "config", "user.name", name)
                git(checkout, "config", "user.email", email)
                git(checkout, "add", "--", *materialized.builder_paths)
                staged = tuple(sorted(
                    (line for line in git(
                        checkout, "diff", "--cached", "--name-only", "--"
                    ).decode().splitlines() if line),
                    key=str.casefold,
                ))
                if staged != materialized.builder_paths:
                    raise MaterializationError("staged Unity paths differ from builder output")
                git(
                    checkout, "commit", "-m", f"Materialize Unity assets for {task_id}",
                    "-m", (
                        f"Assistant-Original-Candidate: {expected_candidate}\n"
                        f"Task-Contract-SHA256: {record['task_contract_sha256']}\n"
                    ),
                )
                commit = git(checkout, "rev-parse", "HEAD").decode().strip()
                tree = git(checkout, "rev-parse", "HEAD^{tree}").decode().strip()
                parents = git(
                    checkout, "rev-list", "--parents", "-n", "1", commit
                ).decode().strip().split()
                if parents != [commit, expected_candidate]:
                    raise MaterializationError("materialized commit has the wrong parent")
                journal.update({
                    "phase": "committed",
                    "materialized_commit": commit,
                    "materialized_tree": tree,
                    "materialized_paths": list(materialized.builder_paths),
                    "unity_executable": materialized.unity_executable,
                    "unity_log": materialized.unity_log,
                    "restored_tracked_paths": list(materialized.restored_tracked_paths),
                    "normalized_paths": list(materialized.normalized_paths),
                    "committed_at": _now(),
                })
                write_record(journal_path, journal)
                try:
                    validations = validation_runner(
                        checkout=checkout,
                        state_root=checkouts.records,
                        task=task,
                        task_id=task_id,
                        run_id=f"materialize-{commit[:12]}",
                        commit=commit,
                        unity_executable=resolved_unity,
                        command_runner=unity_command_runner,
                        require_plan=True,
                        evidence_phase="post-materialization-validation",
                    )
                except AuthoritativeCandidateValidationError as exc:
                    journal.update({
                        "phase": "validation_failed",
                        "validation_error": str(exc),
                        "failed_at": _now(),
                    })
                    write_record(journal_path, journal)
                    _finalize_validation_failure(record_path, record, journal)
                    raise MaterializationError(
                        "Unity materialized the candidate, but its focused tests failed; "
                        f"give this evidence to the next crew: {exc}"
                    ) from exc
                journal.update({
                    "phase": "validated",
                    "authoritative_validations": list(validations),
                    "validated_at": _now(),
                })
                write_record(journal_path, journal)
                return _finalize(record_path, record, journal)
            except MaterializationError as exc:
                if journal.get("phase") == "starting":
                    journal.update({
                        "phase": "materialization_failed",
                        "materialization_error": str(exc),
                        "retryable": False,
                        "failed_at": _now(),
                    })
                    write_record(journal_path, journal)
                    _record_materialization_failure(
                        record_path, record, journal, status="materialization_failed",
                    )
                raise
            except (DoorPrototypeMaterializationError, RuntimeError, OSError) as exc:
                journal.update({
                    "phase": "materialization_failed",
                    "materialization_error": str(exc),
                    "retryable": False,
                    "failed_at": _now(),
                })
                write_record(journal_path, journal)
                _record_materialization_failure(
                    record_path, record, journal, status="materialization_failed",
                )
                raise MaterializationError(
                    f"Unity materialization stopped with its checkout and journal retained: {exc}"
                ) from exc


__all__ = ["MaterializationError", "materialize_candidate"]
