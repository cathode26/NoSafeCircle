"""Explicit AssistantControl decomposition proposal and local D1C application.

The provider phase receives Source read-only and can only publish review artifacts.
The apply phase rechecks the exact source, contract, candidate, independent review,
and deterministic graph plan before creating the canonical local D1C commit.
Nothing in this module pushes or contacts GitHub.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.decomposition_transport import build_compose_command
from Pipeline.AssistantControl.inspect_project import changes, git
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.decomposition_policy_audit import decomposition_preflight
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock


ROOT = Path(__file__).resolve().parents[2]
TASK_GRAPH_ROOT = ROOT / "Pipeline" / "TaskGraph"
for module_root in (ROOT, ROOT / "Pipeline", TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from TaskDecomposition.contracts import DecompositionResult  # noqa: E402
from TaskDecomposition.round_robin_decomposition import candidate_sha256  # noqa: E402
from apply_graph_delta import apply_graph_delta  # noqa: E402
from graph_apply_plan import plan_graph_apply  # noqa: E402
from graph_delta import GraphDeltaPlan  # noqa: E402
from persistent_work_graph import load_persistent_work_graph  # noqa: E402


SCHEMA = "assistant-decomposition/v1"
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_path(manager: Checkouts, task_id: str) -> Path:
    return manager.records / f"{validate_task_id(task_id)}.decomposition.json"


def _load_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is not one exact regular file: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if type(value) is not dict:
        raise ValueError(f"{label} must contain one JSON object")
    return value, raw


def _read_record(manager: Checkouts, task_id: str) -> dict[str, Any]:
    path = _record_path(manager, task_id)
    value, _ = _load_object(path, "Assistant decomposition record")
    if value.get("schema_version") != SCHEMA or value.get("task_id") != task_id:
        raise ValueError("Assistant decomposition record identity differs")
    if value.get("source") != str(manager.source):
        raise ValueError("Assistant decomposition record belongs to another Source")
    return value


def _require_clean_source(manager: Checkouts) -> tuple[str, str, str]:
    if changes(manager.source):
        raise ValueError("Source must be clean before decomposition")
    head = git(manager.source, "rev-parse", "HEAD").decode().strip()
    tree = git(manager.source, "rev-parse", "HEAD^{tree}").decode().strip()
    branch = git(manager.source, "branch", "--show-current").decode().strip()
    if not branch:
        raise ValueError("Source must be on an attached branch")
    return head, tree, branch


def _source_advancement_proof(
    source: Path, reviewed_head: str, current_head: str,
) -> dict[str, Any]:
    same_commit = reviewed_head == current_head
    ancestor = same_commit or subprocess.run(
        ("git", "--no-optional-locks", "-C", str(source), "merge-base", "--is-ancestor",
         reviewed_head, current_head),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0
    graph_inputs_unchanged = ancestor and (
        same_commit or subprocess.run(
            ("git", "--no-optional-locks", "-C", str(source), "diff", "--quiet",
             reviewed_head, current_head, "--", "Tasks", "Pipeline/TaskGraph",
             "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        ).returncode == 0
    )
    return {
        "reviewed_source_commit": reviewed_head,
        "apply_source_commit": current_head,
        "reviewed_source_is_ancestor": ancestor,
        "authoritative_graph_inputs_unchanged": graph_inputs_unchanged,
    }


def _ensure_owner(manager: Checkouts) -> None:
    manager.records.mkdir(parents=True, exist_ok=True)
    owner = manager.records / "project.json"
    identity = {"source": str(manager.source), "checkout_root": str(manager.root)}
    if owner.exists():
        current, _ = _load_object(owner, "AssistantControl project record")
        if current != identity:
            raise ValueError("Checkout directory belongs to another source project")
    else:
        write_record(owner, identity)


def _artifact_paths(record: dict[str, Any]) -> tuple[Path, Path, Path]:
    root = Path(str(record.get("artifact_root") or "")).resolve()
    expected = (
        Path(record["output_root"]).resolve()
        / record["run_id"]
    )
    if root != expected or not root.is_relative_to(Path(record["output_root"]).resolve()):
        raise ValueError("Decomposition artifact root differs from its durable binding")
    return (
        root / "decomposition_run_result.json",
        root / "decomposition_result.json",
        root / "graph_delta.json",
    )


def _verify_review(manager: Checkouts, record: dict[str, Any]) -> dict[str, Any]:
    head, tree, branch = _require_clean_source(manager)
    if branch != record.get("source_branch"):
        raise ValueError("Source branch changed after the decomposition proposal")
    source_advancement = _source_advancement_proof(
        manager.source, record.get("source_commit"), head,
    )
    if not source_advancement["reviewed_source_is_ancestor"]:
        raise ValueError("Reviewed Source is not an ancestor of the current Source")
    if not source_advancement["authoritative_graph_inputs_unchanged"]:
        raise ValueError("TaskGraph inputs changed after the decomposition proposal")

    run_path, result_path, graph_path = _artifact_paths(record)
    run_result, run_bytes = _load_object(run_path, "Decomposition run result")
    result_payload, result_bytes = _load_object(result_path, "Decomposition result")
    graph_payload, graph_bytes = _load_object(graph_path, "Graph delta")
    decomposition = DecompositionResult.from_dict(result_payload)
    plan = GraphDeltaPlan.from_payload(graph_payload)
    task = load_committed_task(
        manager.source,
        record["task_id"],
        commit=head,
        expected_sha256=record["task_contract_sha256"],
    )

    expected = {
        "schema_version": "1.0",
        "mode": "round_robin_d1b2",
        "run_id": record["run_id"],
        "task_id": record["task_id"],
        "provider_order": record["providers"],
        "max_calls": 2,
        "calls_used": 2,
        "run_status": "review_ready",
        "decision": "decomposed",
        "review_independence": "cross_provider",
        "authority": "review_only_not_applied",
    }
    for field, wanted in expected.items():
        if run_result.get(field) != wanted:
            raise ValueError(
                f"Decomposition review {field} is {run_result.get(field)!r}, expected {wanted!r}"
            )
    if run_result.get("unresolved_findings") != [] or run_result.get("rejection_reasons") != []:
        raise ValueError("Decomposition review carries unresolved findings or rejections")
    identity = run_result.get("source_identity") or {}
    if (identity.get("head_commit") != record.get("source_commit")
            or identity.get("head_tree") != record.get("source_tree")):
        raise ValueError("Decomposition run used another source commit or tree")
    contract = run_result.get("task_execution_contract_identity") or {}
    if (contract.get("sha256") != task["task_contract_sha256"]
            or contract.get("revision") != task.get("contract_revision")):
        raise ValueError("Decomposition run used another parent contract")
    if (decomposition.parent_task.task_id != record["task_id"]
            or decomposition.parent_task.contract_revision != task.get("contract_revision")):
        raise ValueError("Decomposition result names another parent task")

    digest = candidate_sha256(decomposition)
    candidate = run_result.get("latest_candidate") or {}
    rounds = run_result.get("rounds")
    history = run_result.get("finding_history")
    if not isinstance(rounds, list) or len(rounds) != 2:
        raise ValueError("Decomposition review must contain exactly one author and one reviewer round")
    author, reviewer = rounds
    author_candidate = author.get("candidate_after") or {}
    reviewed_candidate = reviewer.get("candidate_before") or {}
    if not (
        candidate.get("sha256") == digest
        and candidate.get("graph_delta_plan_id") == plan.plan_id
        and candidate.get("author_provider") == record["providers"][0]
        and author.get("role") == "task_decomposer"
        and author.get("requested_provider") == record["providers"][0]
        and author.get("agent_status") == "succeeded"
        and author.get("status") == "candidate_valid"
        and author_candidate == candidate
        and reviewer.get("role") == "decomposition_reviewer"
        and reviewer.get("requested_provider") == record["providers"][1]
        and reviewer.get("agent_status") == "succeeded"
        and reviewer.get("status") == "independent_pass"
        and reviewer.get("verdict") == "pass"
        and reviewer.get("candidate_after") is None
        and reviewed_candidate == candidate
        and run_result.get("independent_approver_provider") == record["providers"][1]
    ):
        raise ValueError("Decomposition artifacts do not prove the exact independent author/reviewer pass")
    if (not isinstance(history, list) or not history
            or history[-1].get("verdict") != "pass"
            or history[-1].get("reviewed_candidate_sha256") != digest
            or history[-1].get("findings") != []):
        raise ValueError("Decomposition review history does not end with a clean pass")

    fresh = plan_graph_apply(
        load_persistent_work_graph(manager.source),
        decomposition.parent_task,
        decomposition,
        plan,
    )
    if fresh.status != "fresh" or fresh.stored_plan_id != plan.plan_id:
        raise ValueError(f"Reviewed decomposition plan is not fresh: {fresh.status}: {fresh.reason}")
    parent_semantic_authorization_compatible = (
        fresh.expected_parent_semantic_hash
        == fresh.actual_parent_semantic_hash
        == decomposition.parent_task.contract_sha256
    )
    if not parent_semantic_authorization_compatible:
        raise ValueError("Current parent contract differs from the reviewed semantic authorization")
    child_ids = sorted(plan.allocated_local_key_to_task_id.values())
    if len(child_ids) != len(set(child_ids)) or not child_ids:
        raise ValueError("Reviewed decomposition plan did not allocate unique children")
    return {
        "status": "review_ready",
        "task_id": record["task_id"],
        "run_id": record["run_id"],
        "plan_id": plan.plan_id,
        "child_ids": child_ids,
        "candidate_sha256": digest,
        "artifact_sha256": {
            "decomposition_run_result.json": hashlib.sha256(run_bytes).hexdigest(),
            "decomposition_result.json": hashlib.sha256(result_bytes).hexdigest(),
            "graph_delta.json": hashlib.sha256(graph_bytes).hexdigest(),
        },
        "reviewer_provider": record["providers"][1],
        "models": [author.get("actual_model"), reviewer.get("actual_model")],
        "apply_source_commit": head,
        "reviewed_source_commit": record["source_commit"],
        "source_advancement": {
            **source_advancement,
            "reviewed_source_tree": record["source_tree"],
            "apply_source_tree": tree,
            "parent_contract_exact_byte_sha256": task["task_contract_sha256"],
            "reviewed_parent_semantic_sha256": fresh.expected_parent_semantic_hash,
            "current_parent_semantic_sha256": fresh.actual_parent_semantic_hash,
            "parent_contract_semantic_authorization_compatible": True,
        },
    }


def run(
    manager: Checkouts,
    task_id: str,
    run_id: str,
    *,
    providers: str = "claude,codex",
    compose_project: str = "nosafecircle",
    execution_authorized: bool = False,
) -> dict[str, Any]:
    """Run one two-call, cross-provider decomposition proposal."""

    task_id = validate_task_id(task_id)
    if not execution_authorized:
        raise ValueError("Explicit provider-spend authorization is required; no decomposition started")
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("Decomposition run id contains unsupported characters")
    provider_order = [item.strip() for item in providers.split(",") if item.strip()]
    if len(provider_order) != 2 or len(set(provider_order)) != 2:
        raise ValueError("Assistant decomposition requires two distinct providers")
    _ensure_owner(manager)
    head, tree, branch = _require_clean_source(manager)
    task = load_committed_task(manager.source, task_id, commit=head)
    if (task.get("contract_disposition") != "active"
            or task.get("execution_scope") != "needs_execution_decomposition"
            or task.get("decomposition_state") != "concrete"):
        raise ValueError("Task is not an active concrete decomposition candidate")
    preflight = decomposition_preflight(manager.source, task_id, task, commit=head)

    output_root = (manager.records / "decomposition-runs").resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    artifact_root = output_root / run_id
    if artifact_root.exists():
        raise ValueError(f"Decomposition run already exists and was preserved: {artifact_root}")
    path = _record_path(manager, task_id)
    with _exclusive_file_lock(manager.records / "decomposition.lock", timeout_seconds=10):
        if path.exists():
            prior = _read_record(manager, task_id)
            raise ValueError(
                f"Decomposition record already exists with status {prior.get('status')}; it was preserved"
            )
        logs = manager.records / "decomposition-launch" / task_id / run_id
        logs.mkdir(parents=True)
        record = {
            "schema_version": SCHEMA,
            "task_id": task_id,
            "run_id": run_id,
            "source": str(manager.source),
            "source_commit": head,
            "source_tree": tree,
            "source_branch": branch,
            "task_contract_sha256": task["task_contract_sha256"],
            "providers": provider_order,
            "max_calls": 2,
            "compose_project": compose_project,
            "output_root": str(output_root),
            "artifact_root": str(artifact_root),
            "stdout_log": str(logs / "stdout.log"),
            "stderr_log": str(logs / "stderr.log"),
            "status": "running",
            "started_at_utc": _now(),
            "preflight_source_commit": preflight.get("source_commit"),
        }
        write_record(path, record)

    command = list(build_compose_command(
        task_id=task_id,
        project=compose_project,
        providers=",".join(provider_order),
        max_calls=2,
        run_id=run_id,
    ))
    command.extend(("--source", "/workspace", "--output-root", "/decomposition-output"))
    environment = os.environ.copy()
    environment["NSC_DECOMPOSITION_HOST_OUTPUT_ROOT"] = str(output_root)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        with Path(record["stdout_log"]).open("wb") as stdout, Path(record["stderr_log"]).open("wb") as stderr:
            completed = subprocess.run(
                command,
                cwd=manager.source,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                timeout=3600,
                creationflags=creationflags,
                check=False,
            )
        if completed.returncode != 0:
            detail = Path(record["stderr_log"]).read_text(encoding="utf-8", errors="replace")[-1600:]
            record.update(status="failed", completed_at_utc=_now(), exit_code=completed.returncode,
                          error=" ".join(detail.split()))
            write_record(path, record)
            return record
        review = _verify_review(manager, record)
        record.update(review=review, status="review_ready", completed_at_utc=_now(), exit_code=0)
        write_record(path, record)
        return record
    except BaseException as exc:
        record.update(status="failed", completed_at_utc=_now(), error=f"{type(exc).__name__}: {exc}")
        write_record(path, record)
        raise


def inspect(manager: Checkouts, task_id: str) -> dict[str, Any]:
    record = _read_record(manager, validate_task_id(task_id))
    if record.get("status") == "review_ready":
        review = _verify_review(manager, record)
        return {**record, "review": review}
    return record


def apply(
    manager: Checkouts,
    task_id: str,
    *,
    run_id: str,
    expected_source_commit: str,
    target_branch: str,
) -> dict[str, Any]:
    """Apply the exact independently reviewed plan to the local Source."""

    task_id = validate_task_id(task_id)
    record = _read_record(manager, task_id)
    if record.get("run_id") != run_id or record.get("status") != "review_ready":
        raise ValueError("Exact decomposition run is not awaiting local application")
    review = _verify_review(manager, record)
    if review.get("apply_source_commit") != expected_source_commit:
        raise ValueError("Requested source commit differs from the current compatible Source")
    if git(manager.source, "branch", "--show-current").decode().strip() != target_branch:
        raise ValueError("Source is not on the requested target branch")
    run_path, result_path, graph_path = _artifact_paths(record)
    result_payload, _ = _load_object(result_path, "Decomposition result")
    graph_payload, _ = _load_object(graph_path, "Graph delta")
    decomposition = DecompositionResult.from_dict(result_payload)
    plan = GraphDeltaPlan.from_payload(graph_payload)
    applied = apply_graph_delta(
        manager.source,
        decomposition.parent_task,
        decomposition,
        plan,
        expected_head=review["apply_source_commit"],
    )
    if applied.status != "applied" or not applied.new_commit_sha:
        raise RuntimeError(f"D1C did not apply the reviewed plan: {applied.status}: {applied.reason}")
    head, _tree, branch = _require_clean_source(manager)
    if head != applied.new_commit_sha or branch != target_branch:
        raise RuntimeError("Source identity differs after D1C application")
    parent = load_committed_task(manager.source, task_id, commit=head)
    if sorted(parent.get("decomposition_children") or []) != review["child_ids"]:
        raise RuntimeError("Applied parent does not retain the exact reviewed child IDs")
    for child_id in review["child_ids"]:
        child = load_committed_task(manager.source, child_id, commit=head)
        if child.get("parent") != task_id or child.get("contract_disposition") != "active":
            raise RuntimeError(f"Applied child {child_id} does not bind the reviewed parent")
    record.pop("error", None)
    record.update(
        status="applied",
        exit_code=0,
        applied_at_utc=_now(),
        applied_commit=head,
        child_ids=review["child_ids"],
        application=asdict(applied),
        application_authentication=review,
    )
    write_record(_record_path(manager, task_id), record)
    return record
