"""Prepare bounded human rejection feedback for an authenticated retry.

This module only validates and stages retry inputs. It never starts a provider
or calls ``ExecutionCrewBridge.require`` for the archived run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from Pipeline.AssistantControl.admission import _revision_baseline
from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.inspect_project import git


class RevisionFeedbackError(ValueError):
    """The retained rejection cannot be safely used for a retry."""


def _owned(root: Path, path: Path, *, field: str, strict: bool = True) -> Path:
    try:
        root = root.resolve(strict=True)
        resolved = path.resolve(strict=strict)
    except OSError as exc:
        raise RevisionFeedbackError(f"{field} is unavailable") from exc
    if resolved == root or not resolved.is_relative_to(root):
        raise RevisionFeedbackError(f"{field} is outside its owned root")
    return resolved


def _regular_bytes(path: Path, *, field: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RevisionFeedbackError(f"{field} must be an owned regular file")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RevisionFeedbackError(f"{field} could not be read") from exc


def _write_immutable(path: Path, data: bytes, *, field: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or _regular_bytes(path, field=field) != data:
            raise RevisionFeedbackError(f"existing {field} differs; retained evidence was not replaced")
        return
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError:
        if path.is_symlink() or _regular_bytes(path, field=field) != data:
            raise RevisionFeedbackError(f"existing {field} differs; retained evidence was not replaced")
    except OSError as exc:
        raise RevisionFeedbackError(f"{field} could not be written") from exc


def _plan_paths(plan: Mapping[str, Any]) -> tuple[tuple[str, ...], ...]:
    fields = (
        "existing_implementation_paths", "new_implementation_paths",
        "existing_test_paths", "new_test_paths",
    )
    values = []
    for field in fields:
        raw = plan.get(field)
        if not isinstance(raw, list) or any(not isinstance(path, str) for path in raw):
            raise RevisionFeedbackError("reservation plan has invalid scope paths")
        values.append(tuple(sorted(raw, key=str.casefold)))
    return tuple(values)  # type: ignore[return-value]


def _validate_context(context: Any, reservation: Mapping[str, Any], config: Mapping[str, Any],
                      task_id: str, prior_run_id: str) -> None:
    plan = reservation.get("plan")
    if not isinstance(plan, Mapping):
        raise RevisionFeedbackError("reservation plan is missing")
    expected = _plan_paths(plan)
    actual_existing_impl = tuple(path for path in context.implementation_paths
                                 if path not in context.new_implementation_paths)
    actual_existing_test = tuple(path for path in context.test_paths
                                 if path not in context.new_test_paths)
    actual = tuple(tuple(sorted(paths, key=str.casefold)) for paths in (
        actual_existing_impl, context.new_implementation_paths,
        actual_existing_test, context.new_test_paths,
    ))
    if context.task_id != task_id or context.prior_run_id != prior_run_id or actual != expected:
        raise RevisionFeedbackError("retry context differs from the current reservation")

    bridge = config.get("bridge", config)
    if not isinstance(bridge, Mapping):
        raise RevisionFeedbackError("worker bridge config must be an object")
    provider = config.get("provider", bridge.get("provider"))
    model = config.get("execution_model", bridge.get("execution_model"))
    effort = bridge.get("execution_reasoning_effort", config.get("execution_reasoning_effort"))
    crew_profile = bridge.get("crew_profile", "full")
    validation_profile = bridge.get("validation_profile", "full_relevant")
    if (not isinstance(provider, str) or not provider.strip()
            or not isinstance(model, str) or not model.strip()):
        raise RevisionFeedbackError("retry config requires explicit provider and execution_model")
    if (context.provider != provider.strip().casefold()
            or context.execution_model != model.strip()
            or context.execution_reasoning_effort != effort
            or context.crew_profile != crew_profile
            or context.validation_profile != validation_profile):
        raise RevisionFeedbackError("retry provider, model, effort, or rigor profile differs")


def _prepare_fresh_feedback(checkouts, record, reservation, baseline, review):
    """Stage exact rejection notes for a new crew; never seed historical patches."""
    if (reservation.get("task_id") != record.get("task_id")
            or reservation.get("source_head") != baseline
            or not all(reservation.get(key) for key in ("run_id", "lease_id", "plan_id"))):
        raise RevisionFeedbackError("fresh feedback reservation differs from the rejected base")
    message = review.get("message")
    if not isinstance(message, str) or not message.strip() or "\x00" in message:
        raise RevisionFeedbackError("rejection.message must be non-empty text")
    data = message.encode("utf-8")
    if len(data) > 64 * 1024:
        raise RevisionFeedbackError("rejection.message exceeds the bounded feedback size")
    metadata = {
        "schema_version": "assistant-fresh-revision-feedback/v1",
        "task_id": record["task_id"], "rejected_commit": baseline,
        "rejected_tree": record["revision"]["candidate_tree"],
        "history_index": record["revision"]["history_index"],
        **{key: reservation[key] for key in ("run_id", "lease_id", "plan_id")},
        "feedback_sha256": hashlib.sha256(data).hexdigest(),
    }
    encoded = (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode("utf-8")
    key = hashlib.sha256(encoded).hexdigest()
    checkout = _owned(checkouts.root, Path(record["checkout"]), field="task checkout")
    directory = _owned(checkout, checkout / "Pipeline" / "ExecutionCrew" / "outputs" /
                       "assistant-feedback" / key, field="fresh feedback directory", strict=False)
    path = directory / "feedback.txt"
    _write_immutable(path, data, field="fresh revision feedback")
    _write_immutable(directory / "metadata.json", encoded, field="fresh feedback metadata")
    _write_immutable(checkouts.records / "revision-feedback" / f"{key}.json", encoded,
                     field="fresh feedback record")
    return {"revision_feedback_file": path}


def prepare_revision_feedback(
    checkouts: Checkouts, record: Mapping[str, Any], reservation: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Return explicit fresh-feedback or retry kwargs for a verified revision.

    A non-revision record returns ``{}`` without importing ExecutionCrew.
    """
    revision = record.get("revision")
    if not isinstance(revision, Mapping):
        return {}
    task_id = record.get("task_id")
    if not isinstance(task_id, str) or not isinstance(reservation, Mapping):
        raise RevisionFeedbackError("revision record or reservation identity is invalid")
    try:
        current_source_head = git(checkouts.source, "rev-parse", "HEAD").decode().strip()
        baseline = _revision_baseline(checkouts, record, task_id, current_source_head)
    except Exception as exc:
        raise RevisionFeedbackError("revision baseline is not currently authenticated") from exc
    if baseline is None or revision.get("candidate_commit") != baseline:
        raise RevisionFeedbackError("revision baseline does not identify the archived candidate")

    history = record.get("revision_history")
    index = revision.get("history_index")
    if (not isinstance(history, list) or type(index) is not int
            or not 0 <= index < len(history) or not isinstance(history[index], Mapping)):
        raise RevisionFeedbackError("revision history binding is invalid")
    archived = history[index]
    candidate = archived.get("candidate")
    review = archived.get("revision_feedback") or archived.get("human_review")
    if (not isinstance(candidate, Mapping) or not isinstance(review, Mapping)
            or review.get("decision") != "reject"
            or review.get("commit") != baseline
            or revision.get("rejected_review") != dict(review)):
        raise RevisionFeedbackError("revision does not bind an exact rejected candidate")
    if revision.get("feedback_mode") == "fresh":
        return _prepare_fresh_feedback(checkouts, record, reservation, baseline, review)
    receipt = candidate.get("receipt")
    prior_run_id = candidate.get("run_id")
    if (not isinstance(receipt, Mapping) or not isinstance(prior_run_id, str)
            or not prior_run_id.strip() or receipt.get("run_id") != prior_run_id):
        raise RevisionFeedbackError("archived candidate has no exact crew run receipt")
    receipt_identity = {
        "task_id": task_id, "task_contract_sha256": record.get("task_contract_sha256"),
        "lease_id": candidate.get("lease_id"), "plan_id": candidate.get("plan_id"),
        "candidate_commit": baseline, "candidate_tree": candidate.get("tree"),
        "candidate_parent": candidate.get("parent"), "source_base": archived.get("source_commit"),
    }
    for key, value in receipt_identity.items():
        if not value or receipt.get(key) != value:
            raise RevisionFeedbackError("archived candidate receipt identity differs")
    if candidate.get("commit") != baseline:
        raise RevisionFeedbackError("archived candidate commit differs from revision baseline")

    checkout = _owned(checkouts.root, Path(record.get("checkout", "")), field="task checkout")
    output_root = _owned(checkout, checkout / "Pipeline" / "ExecutionCrew" / "outputs",
                         field="ExecutionCrew output root")
    run_root = _owned(output_root, output_root / prior_run_id, field="archived crew run")
    result_path = _owned(run_root, run_root / "crew_result.json", field="archived crew result")
    patch_path = _owned(run_root, run_root / "candidate.patch", field="archived candidate patch")
    result_bytes = _regular_bytes(result_path, field="archived crew result")
    patch_bytes = _regular_bytes(patch_path, field="archived candidate patch")
    if hashlib.sha256(result_bytes).hexdigest() != receipt.get("execution_result_sha256"):
        raise RevisionFeedbackError("archived crew result hash differs from candidate receipt")
    if hashlib.sha256(patch_bytes).hexdigest() != receipt.get("candidate_patch_sha256"):
        raise RevisionFeedbackError("archived candidate patch hash differs from candidate receipt")

    message = review.get("message")
    if not isinstance(message, str) or not message.strip() or "\x00" in message:
        raise RevisionFeedbackError("rejection.message must be non-empty text")
    feedback_bytes = message.encode("utf-8")
    if len(feedback_bytes) > 64 * 1024:
        raise RevisionFeedbackError("rejection.message exceeds the bounded feedback size")
    feedback_hash = hashlib.sha256(prior_run_id.encode("utf-8")).hexdigest()
    feedback_dir = _owned(output_root, output_root / "assistant-feedback" / feedback_hash,
                          field="assistant feedback directory", strict=False)
    feedback_file = feedback_dir / "feedback.txt"
    _write_immutable(feedback_file, feedback_bytes, field="assistant feedback")
    metadata = {
        "schema_version": "assistant-revision-feedback/v1", "task_id": task_id,
        "prior_run_id": prior_run_id, "candidate_commit": baseline,
        "candidate_patch_sha256": receipt.get("candidate_patch_sha256"),
        "execution_result_sha256": receipt.get("execution_result_sha256"),
        "feedback_sha256": hashlib.sha256(feedback_bytes).hexdigest(),
        "feedback_file": str(feedback_file),
    }
    metadata_bytes = (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _write_immutable(checkouts.records / "revision-feedback" / f"{feedback_hash}.json",
                     metadata_bytes, field="revision feedback metadata")
    _write_immutable(feedback_dir / "metadata.json", metadata_bytes,
                     field="revision feedback output metadata")

    # This is intentionally the first import of ExecutionCrew. It is reached
    # only after all record, artifact, feedback, and configuration checks pass.
    from Pipeline.ExecutionCrew.run_crew import capture_source, load_retry_context
    try:
        identity = capture_source(checkout)
        context = load_retry_context(
            source=checkout, identity=identity, output_root=output_root,
            prior_run_id=prior_run_id, feedback_file=feedback_file,
        )
    except Exception as exc:
        raise RevisionFeedbackError("archived retry context could not be authenticated") from exc
    _validate_context(context, reservation, config, task_id, prior_run_id)
    return {"retry_run_id": prior_run_id, "feedback_file": feedback_file}


__all__ = ["RevisionFeedbackError", "prepare_revision_feedback"]
