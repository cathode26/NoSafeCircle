"""Begin a fresh worker revision after an explicitly rejected candidate."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


_COMMIT = re.compile(r"^[0-9a-f]{40}|[0-9a-f]{64}$")


class RevisionError(ValueError):
    """A rejected candidate cannot safely become a new worker baseline."""


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _record_path(checkouts: Checkouts, task_id: str) -> Path:
    return checkouts.records / f"{validate_task_id(task_id)}.json"


def _source_head_and_tree(source: Path) -> tuple[str, str]:
    head = git(source, "rev-parse", "HEAD").decode().strip()
    tree = git(source, "rev-parse", "HEAD^{tree}").decode().strip()
    return head, tree


def begin_revision(checkouts: Checkouts, task_id: str, expected_candidate: str) -> dict[str, Any]:
    """Reset active review/worker state for one explicitly rejected candidate.

    The candidate commit and its checkout files remain untouched. A new scope,
    lease, and admission are required before another worker can run.
    """
    task_id = validate_task_id(task_id)
    if not isinstance(expected_candidate, str) or not _COMMIT.fullmatch(expected_candidate):
        raise RevisionError("revision requires the exact full candidate commit")
    path = _record_path(checkouts, task_id)
    source_lock, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RevisionError("owned task record is unreadable") from exc
        if record.get("task_id") != task_id or record.get("source") != str(checkouts.source):
            raise RevisionError("task record identity differs")
        try:
            checkouts.observe(task_id)
        except Exception as exc:
            raise RevisionError("owned checkout identity is invalid") from exc
        machine_validation_failure = (
            record.get("status") == "validation_failed"
            and (record.get("candidate") or {}).get("kind")
            == "unity_materialization_failed"
        )
        try:
            ReviewGate(checkouts)._require_candidate(
                record, expected_candidate,
                allow_failed_materialization=machine_validation_failure,
            )
        except Exception as exc:
            raise RevisionError("candidate is not the clean owned reviewed candidate") from exc
        review = record.get("human_review") or {}
        if machine_validation_failure:
            failure = record.get("materialization_failure") or {}
            error = failure.get("validation_error")
            if (failure.get("materialized_commit") != expected_candidate
                    or not isinstance(error, str) or not error.strip()):
                raise RevisionError("Unity validation failure identity is incomplete")
            feedback = {
                "commit": expected_candidate,
                "decision": "reject",
                "message": "Authoritative Unity validation failed:\n" + error.strip(),
                "authority": "authoritative_unity_validation",
                "recorded_at": failure.get("failed_at"),
            }
        elif (record.get("status") == "changes_requested"
              and review.get("decision") == "reject"
              and review.get("commit") == expected_candidate):
            feedback = _copy(review)
        else:
            raise RevisionError("revision requires an exact human changes_requested rejection")
        for field in ("worker", "launch"):
            current = record.get(field)
            if current is not None and not isinstance(current, dict):
                raise RevisionError("prior worker or launch record is malformed")
        worker = record.get("worker")
        launch = record.get("launch")
        if isinstance(worker, dict):
            if (isinstance(launch, dict) and launch.get("run_id") != worker.get("run_id")):
                raise RevisionError("worker and launch records identify different runs")
            if worker.get("capacity_released") is not True:
                raise RevisionError("all prior worker and launch attempts must release capacity")
        elif isinstance(launch, dict) and launch.get("capacity_released") is not True:
            raise RevisionError("all prior worker and launch attempts must release capacity")
        with _exclusive_file_lock(source_lock, timeout_seconds=10):
            registry = _read_registry(registry_path, checkouts.source)
            if any(item.get("task_id") == task_id for item in registry["reservations"]):
                raise RevisionError("task has an active admission; release it before revision")
            source_head, source_tree = _source_head_and_tree(checkouts.source)
            # `--is-ancestor` exits 1 for a proven non-ancestor and 128 when it
            # cannot resolve an argument. The task checkout never fetches later
            # Source commits, so a moved Source reaches 128 -- and reporting
            # that as non-ancestry asserts a fact nobody measured. Resolve the
            # objects first so each refusal names its own cause.
            checkout_root = checkouts.root / task_id
            for label, commit in (("current source HEAD", source_head),
                                  ("the rejected candidate", expected_candidate)):
                try:
                    git(checkout_root, "cat-file", "-e", f"{commit}^{{commit}}")
                except RuntimeError as exc:
                    raise RevisionError(
                        f"{label} {commit} is not present in the task checkout, so its "
                        "ancestry against the rejected candidate was never determined"
                    ) from exc
            try:
                git(checkout_root, "merge-base", "--is-ancestor", source_head,
                    expected_candidate)
            except RuntimeError as exc:
                raise RevisionError(
                    "current source HEAD is not an ancestor of the rejected candidate"
                ) from exc
            contract_sha = record.get("task_contract_sha256")
            from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
            try:
                load_committed_task(checkouts.source, task_id, commit=source_head,
                                    expected_sha256=contract_sha)
            except Exception as exc:
                raise RevisionError("task contract changed at current source HEAD") from exc
            checkout = Path(record["checkout"])
            candidate_tree = git(checkout, "rev-parse", f"{expected_candidate}^{{tree}}").decode().strip()
            history = record.get("revision_history", [])
            if not isinstance(history, list):
                raise RevisionError("revision history is malformed")
            archived = {
                "schema_version": "assistant-revision-history/v1",
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "task_id": task_id,
                "source_commit": record.get("source_commit"),
                "candidate": _copy(record.get("candidate")),
                "candidate_lineage": _copy(record.get("candidate_lineage", [])),
                "previous_revision": _copy(record.get("revision")),
                "approval": _copy(record.get("approval")),
                "human_review": _copy(record.get("human_review")),
                "revision_feedback": _copy(feedback),
                "materialization_failure": _copy(record.get("materialization_failure")),
                "scope": _copy(record.get("scope")),
                "worker": _copy(record.get("worker")),
                "launch": _copy(record.get("launch")),
                "integration": _copy(record.get("integration")),
                "candidate_tree": candidate_tree,
                "task_contract_sha256": contract_sha,
            }
            history_index = len(history)
            history.append(archived)
            record["revision_history"] = history
            record["source_commit"] = expected_candidate
            record["revision"] = {
                "feedback_mode": (
                    "fresh" if (archived.get("candidate") or {}).get("kind") in {
                        "source_synchronized", "unity_materialization_failed",
                    } else "legacy_retry"
                ),
                "candidate_commit": expected_candidate,
                "candidate_tree": candidate_tree,
                "source_commit": source_head,
                "source_tree": source_tree,
                "task_contract_sha256": contract_sha,
                "rejected_review": _copy(feedback),
                "history_index": history_index,
            }
            for field in ("scope", "candidate", "approval", "human_review", "worker",
                          "launch", "integration", "materialization_failure"):
                record.pop(field, None)
            latest_source_head, latest_source_tree = _source_head_and_tree(checkouts.source)
            if latest_source_head != source_head or latest_source_tree != source_tree:
                raise RevisionError("source advanced during revision validation")
            record["status"] = "prepared"
            write_record(path, record)
            return record


__all__ = ["RevisionError", "begin_revision"]
