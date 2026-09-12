"""Register a committed assistant-restored Unity candidate for human testing."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from Pipeline.AssistantControl.admission import _read_registry, _source_registry_paths
from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan, validate_task_id
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


class AssistantRestoredCandidateError(ValueError):
    """The committed restored candidate is not safe to expose for review."""


_SHA = re.compile(r"^[0-9a-f]{40}$")
_TERMINAL_WORKER = {"succeeded", "failed", "stopped", "spawn_failed"}


def _read_owned(checkouts: Checkouts, task_id: str) -> tuple[Path, dict[str, Any]]:
    task_id = validate_task_id(task_id)
    path = checkouts.records / f"{task_id}.json"
    if not path.is_file():
        raise AssistantRestoredCandidateError("owned task checkout record does not exist")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssistantRestoredCandidateError("owned task checkout record is unreadable") from exc
    checkout = checkouts.root / task_id
    if (record.get("source") != str(checkouts.source) or record.get("task_id") != task_id
            or record.get("checkout") != str(checkout)):
        raise AssistantRestoredCandidateError("task checkout record identity differs")
    checkouts.observe(task_id)
    return path, record


def _require_settled(checkouts: Checkouts, record: Mapping[str, Any], task_id: str) -> None:
    # Once a worker record exists it is the durable successor to the launch
    # handoff.  The launcher entry may intentionally retain its earlier
    # ready_pending state for diagnosis and must not override final settlement.
    worker = record.get("worker") if record.get("worker") is not None else record.get("launch")
    if worker is not None and (
            not isinstance(worker, Mapping)
            or worker.get("status") not in _TERMINAL_WORKER
            or worker.get("capacity_released") is not True):
        raise AssistantRestoredCandidateError("worker is not settled; restored candidate was not registered")
    lock_path, registry_path = _source_registry_paths(checkouts.source)
    with _exclusive_file_lock(lock_path, timeout_seconds=10):
        registry = _read_registry(registry_path, checkouts.source)
        if any(item.get("task_id") == task_id and item.get("checkout_root") == str(checkouts.root)
               for item in registry["reservations"]):
            raise AssistantRestoredCandidateError("active admission reservation remains; restored candidate was not registered")


def _paths(value: Sequence[str], field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise AssistantRestoredCandidateError(f"{field} must be a list of repository paths")
    result = tuple(value)
    if not result or any(type(item) is not str or not item or "\\" in item
                         or PurePosixPath(item).is_absolute()
                         or any(part in {"", ".", ".."} for part in PurePosixPath(item).parts)
                         for item in result):
        raise AssistantRestoredCandidateError(f"{field} must contain non-empty relative paths")
    if len({item.casefold() for item in result}) != len(result):
        raise AssistantRestoredCandidateError(f"{field} must not contain duplicate paths")
    return tuple(sorted(result, key=str.casefold))


def _provenance(value: Any, field: str) -> Any:
    if not isinstance(value, (Mapping, list, tuple)) or not value:
        raise AssistantRestoredCandidateError(f"{field} must contain explicit provenance")
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise AssistantRestoredCandidateError(f"{field} must be JSON-serializable") from exc


def register_assistant_restored_candidate(
    checkouts: Checkouts,
    task_id: str,
    *,
    base_commit: str,
    candidate_commit: str,
    candidate_tree: str,
    task_contract_sha256: str,
    changed_paths: Sequence[str],
    evidence: Any,
    reference_provenance: Any,
) -> dict[str, Any]:
    """Record a committed restored result without claiming crew review or approval."""
    task_id = validate_task_id(task_id)
    for value, label in ((base_commit, "base_commit"), (candidate_commit, "candidate_commit"),
                         (candidate_tree, "candidate_tree")):
        if type(value) is not str or not _SHA.fullmatch(value):
            raise AssistantRestoredCandidateError(f"{label} must be an exact full Git SHA")
    if type(task_contract_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", task_contract_sha256):
        raise AssistantRestoredCandidateError("task_contract_sha256 must be an exact SHA-256")
    paths = _paths(changed_paths, "changed_paths")
    evidence = _provenance(evidence, "evidence")
    reference_provenance = _provenance(reference_provenance, "reference_provenance")

    with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
        record_path, record = _read_owned(checkouts, task_id)
        _require_settled(checkouts, record, task_id)
        checkout = Path(record["checkout"])
        if record.get("source_commit") != base_commit:
            raise AssistantRestoredCandidateError("candidate base differs from the pinned checkout commit")
        if git(checkout, "branch", "--show-current").decode().strip() != record.get("branch"):
            raise AssistantRestoredCandidateError("task checkout branch changed")
        if git(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
            raise AssistantRestoredCandidateError(
                "task checkout has uncommitted changes; commit or preserve them before review"
            )
        if git(checkout, "rev-parse", "HEAD").decode().strip() != candidate_commit:
            raise AssistantRestoredCandidateError("candidate commit is not the checkout HEAD")
        parents = git(checkout, "rev-list", "--parents", "-n", "1", candidate_commit).decode().split()
        if len(parents) != 2 or parents[1] != base_commit:
            raise AssistantRestoredCandidateError("candidate commit parent differs from the pinned base")
        if git(checkout, "rev-parse", "HEAD^{tree}").decode().strip() != candidate_tree:
            raise AssistantRestoredCandidateError("candidate tree differs from the exact committed tree")
        if record.get("task_contract_sha256") != task_contract_sha256:
            raise AssistantRestoredCandidateError("candidate contract hash differs from the owned task record")
        load_committed_task(checkout, task_id, commit=candidate_commit,
                            expected_sha256=task_contract_sha256)
        raw_scope = record.get("scope")
        if not isinstance(raw_scope, Mapping):
            raise AssistantRestoredCandidateError("candidate requires a registered execution scope")
        plan = ExecutionScopePlan.from_dict(raw_scope["plan"])
        allowed = set(plan.existing_implementation_paths + plan.new_implementation_paths
                      + plan.existing_test_paths + plan.new_test_paths)
        if not set(paths).issubset(allowed):
            raise AssistantRestoredCandidateError("candidate diff is outside the registered path scope")
        actual = tuple(sorted((line for line in git(checkout, "diff", "--name-only",
                                                     f"{base_commit}..{candidate_commit}", "--")
                               .decode().splitlines() if line), key=str.casefold))
        if actual != paths:
            raise AssistantRestoredCandidateError("registered changed_paths do not match the committed diff")
        candidate = {
            "kind": "assistant_restored", "crew_review": False,
            "base_commit": base_commit, "commit": candidate_commit, "tree": candidate_tree,
            "parent": base_commit, "task_contract_sha256": task_contract_sha256,
            "source_base": base_commit, "candidate_commit": candidate_commit,
            "candidate_tree": candidate_tree, "candidate_parent": base_commit,
            "plan_id": raw_scope.get("plan_id"), "lease_id": raw_scope.get("lease_id"),
            "changed_paths": list(paths),
            "evidence": evidence, "reference_provenance": reference_provenance,
        }
        previous = record.get("candidate")
        if previous is not None and previous != candidate:
            raise AssistantRestoredCandidateError("an existing candidate differs; retained for inspection")
        if previous is None:
            record["candidate"] = candidate
            record["approval"] = None
            record["status"] = "awaiting_human"
            write_record(record_path, record)
        return record


register = register_assistant_restored_candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task")
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--task-contract-sha256", required=True)
    parser.add_argument("--changed-paths", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--reference-provenance", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = register_assistant_restored_candidate(
            Checkouts(args.source, args.checkout_root), args.task,
            base_commit=args.base_commit, candidate_commit=args.candidate_commit,
            candidate_tree=args.candidate_tree,
            task_contract_sha256=args.task_contract_sha256,
            changed_paths=json.loads(args.changed_paths.read_text(encoding="utf-8-sig")),
            evidence=json.loads(args.evidence.read_text(encoding="utf-8-sig")),
            reference_provenance=json.loads(args.reference_provenance.read_text(encoding="utf-8-sig")),
        )
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({"status": "command_failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
