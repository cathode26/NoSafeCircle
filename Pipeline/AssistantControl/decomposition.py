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
from typing import Any, Mapping

from Pipeline.AssistantControl.checkouts import Checkouts, write_record
from Pipeline.AssistantControl.decomposition_transport import build_compose_command
from Pipeline.AssistantControl.inspect_project import changes, git
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.TaskReviewAgent.contracts import validate_task_id
from Pipeline.TaskReviewAgent.decomposition_policy_audit import decomposition_preflight
from Pipeline.TaskReviewAgent.decomposition_session_pool import (
    DecompositionSessionPoolError,
    DecompositionSessionPoolOwner,
)
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock
from Pipeline.TaskReviewAgent.supervisor_session_pool import (
    codex_resume_activation_from_environment,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_GRAPH_ROOT = ROOT / "Pipeline" / "TaskGraph"
for module_root in (ROOT, ROOT / "Pipeline", TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from TaskDecomposition.contracts import DecompositionResult  # noqa: E402
from TaskDecomposition.live_decomposition import provider_configuration  # noqa: E402
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    candidate_sha256,
    same_provider_role_pair,
)
from apply_graph_delta import apply_graph_delta  # noqa: E402
from graph_apply_plan import plan_graph_apply  # noqa: E402
from graph_delta import GraphDeltaPlan  # noqa: E402
from persistent_work_graph import load_persistent_work_graph  # noqa: E402


SCHEMA = "assistant-decomposition/v1"
POOL_MANIFEST_SCHEMA = "assistant-decomposition-pool-identity/v1"
POOL_DECOMPOSITION_MODE = "round_robin_d1b2"
POOL_WORKER_ID = "assistant-control"
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# The pool and the container both require the stricter lowercase slug, so a
# pooled run id is refused here rather than after the record already exists.
_POOLED_RUN_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_CONTAINER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")
_LABEL_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_LABEL_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")


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
        raise ValueError(
            "Source must be clean before decomposition (content-identical churn,"
            " e.g. stale Unity stat-cache entries, can often be cleared with"
            " `python -B -m Pipeline.TaskReviewAgent.safe_unity_churn"
            " refresh-identical --repo <source> --apply`)"
        )
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


def _pool_manifest(manager: Checkouts, repository_identity: str) -> Path:
    """Write the checkout-identity manifest whose bytes the pool hashes.

    The owner hashes this file into every lease's ``checkout_identity`` and
    compares the stored value at settlement; it never re-reads the file. It
    lives under AssistantControl's own records because Source is the artifact
    under decomposition and nothing here may write into it.
    """

    path = manager.records / "decomposition-pool" / "checkout-identity.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    identity = {
        "schema_version": POOL_MANIFEST_SCHEMA,
        "source": str(manager.source),
        "checkout_root": str(manager.root),
        "repository_identity": repository_identity,
    }
    if path.exists():
        current, _ = _load_object(path, "AssistantControl decomposition pool identity")
        if current == identity:
            return path
    # `write_record` replaces atomically, so the identity a concurrent run is
    # reading is never briefly absent.
    write_record(path, identity)
    return path


def _pool_owner(
    manager: Checkouts, *, provider: str, compose_project: str,
) -> DecompositionSessionPoolOwner:
    """Own the role-scoped sessions one same-provider decomposition needs.

    The model comes from the same routing the production launcher uses, so the
    reservation, the container's resolved route, and settlement all name one
    model. Pool state stays where the owner puts it: one pool per checkout,
    shared with the production launcher.
    """

    _key, configuration = provider_configuration(provider)
    entry = configuration.to_dict()["provider_configurations"][f"{provider}-decomposition"]
    repository_identity = git(manager.source, "remote", "get-url", "origin").decode().strip()
    return DecompositionSessionPoolOwner(
        checkout=manager.source,
        repository_identity=repository_identity,
        provider_models={
            provider: (
                str(entry["models"]["high_reasoning"]),
                "high" if provider == "codex" else None,
            )
        },
        codex_resume_activation=(
            codex_resume_activation_from_environment() if provider == "codex" else None
        ),
        compose_project=compose_project,
        manifest_path=_pool_manifest(manager, repository_identity),
    )


def _settle_pool(
    owner: DecompositionSessionPoolOwner | None, *, run_id: str, run_dir: Path,
) -> dict[str, Any] | None:
    """Settle one run's leases from its artifacts; a pool failure never fails the run."""

    if owner is None:
        return None
    try:
        present = run_dir.is_dir()
    except OSError:
        present = False
    if not present:
        # The provider may have run, so the leases are not returned: they stay
        # active until the next owner reclaims them as stranded.
        return {"action": "settle", "status": "run_directory_missing", "run_id": run_id}
    try:
        settlement = owner.settle(run_id=run_id, run_dir=run_dir)
    except (DecompositionSessionPoolError, OSError, RuntimeError, ValueError) as exc:
        return {
            "action": "settle",
            "status": "pool_degraded",
            "run_id": run_id,
            "error_type": type(exc).__name__,
            "error": " ".join(str(exc).split())[:900],
            "note": ("The decomposition result stands on its own artifacts. The still-active "
                     "leases are reclaimed as stranded by the next owner and are never reused."),
        }
    return {"action": "settle", "status": "settled", "run_id": run_id, "settlement": settlement}


def _cancel_unstarted_pool(
    owner: DecompositionSessionPoolOwner | None, *, run_id: str,
) -> dict[str, Any] | None:
    """Return one run's leases uncharged after a proven provider-start failure."""

    if owner is None:
        return None
    try:
        owner.cancel_unstarted(run_id=run_id)
    except (DecompositionSessionPoolError, OSError, RuntimeError, ValueError) as exc:
        return {
            "action": "cancel_unstarted",
            "status": "pool_degraded",
            "run_id": run_id,
            "error_type": type(exc).__name__,
            "error": " ".join(str(exc).split())[:900],
        }
    return {"action": "cancel_unstarted", "status": "cancelled_unstarted", "run_id": run_id}


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

    pooled = same_provider_role_pair(record["providers"])
    pool = record.get("pool") or {}
    reserved_leases = pool.get("lease_ids") if isinstance(pool.get("lease_ids"), Mapping) else None
    if pooled and not (pool.get("lease_bundle_path") and reserved_leases):
        # One provider proves an independent review only as two separate
        # conversations, and only the host's reservation establishes them.
        raise ValueError(
            "Same-provider decomposition record carries no role-session lease reservation"
        )

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
        # Two distinct providers are independent by provider identity; one
        # provider is independent only through two separate pooled sessions,
        # and neither order may claim the other's proof.
        "review_independence": (
            "same_provider_separate_sessions" if pooled else "cross_provider"
        ),
        "authority": "review_only_not_applied",
    }
    for field, wanted in expected.items():
        if run_result.get(field) != wanted:
            raise ValueError(
                f"Decomposition review {field} is {run_result.get(field)!r}, expected {wanted!r}"
            )
    if pooled:
        sessions = run_result.get("pooled_sessions")
        if not isinstance(sessions, Mapping) or sorted(sessions) != sorted(reserved_leases):
            raise ValueError("Decomposition run did not use this run's reserved role leases")
        confirmed_session_ids: list[str] = []
        for key, lease_id in sorted(reserved_leases.items()):
            session = sessions[key]
            if not isinstance(session, Mapping) or session.get("lease_id") != lease_id:
                raise ValueError("Decomposition run did not use this run's reserved role leases")
            proof = session.get("confirmed_session")
            session_id = proof.get("session_id") if isinstance(proof, Mapping) else None
            if not isinstance(session_id, str) or not session_id:
                raise ValueError(
                    "Decomposition run proved no confirmed conversation for a reserved role session"
                )
            confirmed_session_ids.append(session_id)
        # The producer checks this too, but the guard that admits
        # `same_provider_separate_sessions` must prove it here as well: one
        # provider is an independent reviewer only as a second conversation.
        if len(set(confirmed_session_ids)) != len(confirmed_session_ids):
            raise ValueError(
                "Same-provider decomposition roles proved one shared conversation, not two distinct ones"
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
    corrections = run_result.get("author_corrections_used")
    # Exactly two round shapes may be applied and nothing else. Without a
    # correction the run is the author/reviewer pair it has always been. With
    # the one bounded author correction the rejected first round is retained,
    # the correction authored the candidate the reviewer then passed, and the
    # run result counts exactly that one extra author call.
    if not isinstance(rounds, list) or len(rounds) not in (2, 3):
        raise ValueError("Decomposition review must contain exactly one author and one reviewer round")
    # The count is an exact integer: a JSON boolean is an int to Python and is
    # refused, not read as 0 or 1.
    if len(rounds) == 3:
        initial, author, reviewer = rounds
        author_status, author_correction_of_round = "correction_candidate_valid", 1
        initial_rejections = initial.get("rejection_reasons") if isinstance(initial, Mapping) else None
        if not (
            type(corrections) is int and corrections == 1
            and isinstance(initial, Mapping)
            and initial.get("role") == "task_decomposer"
            and initial.get("requested_provider") == record["providers"][0]
            and initial.get("agent_status") == "succeeded"
            and initial.get("status") == "rejected"
            and initial.get("candidate_after") is None
            and initial.get("correction_of_round") is None
            # The producer always retains the exact deterministic rejection the
            # correction answered; a rejected round without it is not that round.
            and isinstance(initial_rejections, list) and initial_rejections
            and all(isinstance(reason, str) and reason for reason in initial_rejections)
        ):
            raise ValueError("Decomposition review does not prove exactly one bounded author correction")
    else:
        author, reviewer = rounds
        author_status, author_correction_of_round = "candidate_valid", None
        if corrections is not None and not (type(corrections) is int and corrections == 0):
            raise ValueError("Decomposition review counts an author correction its rounds do not carry")
    author_candidate = author.get("candidate_after") or {}
    reviewed_candidate = reviewer.get("candidate_before") or {}
    if not (
        candidate.get("sha256") == digest
        and candidate.get("graph_delta_plan_id") == plan.plan_id
        and candidate.get("author_provider") == record["providers"][0]
        and author.get("role") == "task_decomposer"
        and author.get("requested_provider") == record["providers"][0]
        and author.get("agent_status") == "succeeded"
        and author.get("status") == author_status
        and author.get("correction_of_round") == author_correction_of_round
        and author_candidate == candidate
        and reviewer.get("role") == "decomposition_reviewer"
        and reviewer.get("requested_provider") == record["providers"][1]
        and reviewer.get("agent_status") == "succeeded"
        and reviewer.get("status") == "independent_pass"
        and reviewer.get("verdict") == "pass"
        and reviewer.get("candidate_after") is None
        and reviewer.get("correction_of_round") is None
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
    container_name: str | None = None,
    container_labels: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run one two-call decomposition proposal: an author and an independent reviewer.

    ``providers`` names two Claude/Codex roles. Two distinct providers are
    independent by provider identity and run exactly as they always have. One
    provider serving both roles is independent only as two separate
    conversations, so that route first reserves one durable session per role
    from the decomposition session pool, mounts the lease bundle read-only, and
    settles those leases from the run's own artifacts afterwards.

    ``container_name`` names the ``docker compose run`` container so an owner
    can stop exactly this proposal's provider container by name, and
    ``container_labels`` stamps the owning ticket and checkout onto it so that
    owner can prove the container is its own before removing it. Neither
    changes anything about the proposal itself.
    """

    task_id = validate_task_id(task_id)
    if not execution_authorized:
        raise ValueError("Explicit provider-spend authorization is required; no decomposition started")
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("Decomposition run id contains unsupported characters")
    if container_name is not None and not _CONTAINER_NAME.fullmatch(container_name):
        raise ValueError("Decomposition container name contains unsupported characters")
    labels = dict(container_labels or {})
    for key, value in labels.items():
        if not _LABEL_KEY.fullmatch(str(key)) or not _LABEL_VALUE.fullmatch(str(value)):
            raise ValueError("Decomposition container label contains unsupported characters")
    if labels and container_name is None:
        raise ValueError("Decomposition container labels require the named container")
    provider_order = [item.strip() for item in providers.split(",") if item.strip()]
    if len(provider_order) != 2 or any(name not in {"claude", "codex"} for name in provider_order):
        raise ValueError("Assistant decomposition requires exactly two claude/codex roles")
    pooled = same_provider_role_pair(provider_order)
    if pooled and not _POOLED_RUN_ID.fullmatch(run_id):
        raise ValueError(
            "Pooled decomposition run id must be a lowercase slug of 1..64 characters"
        )
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
            "container_name": container_name,
            "container_labels": labels or None,
            "status": "running",
            "started_at_utc": _now(),
            "preflight_source_commit": preflight.get("source_commit"),
        }
        write_record(path, record)

    environment = os.environ.copy()
    environment["NSC_DECOMPOSITION_HOST_OUTPUT_ROOT"] = str(output_root)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    owner: DecompositionSessionPoolOwner | None = None
    pool_assignment: dict[str, Any] | None = None
    pool_lifecycle: dict[str, Any] | None = None
    # True once the provider process has provably been spawned. Only a run that
    # never reached the spawn may return its leases uncharged.
    spawned = False
    try:
        if pooled:
            owner = _pool_owner(
                manager, provider=provider_order[0], compose_project=compose_project,
            )
            pool_assignment = owner.prepare(
                run_id=run_id,
                task_id=task_id,
                decomposition_mode=POOL_DECOMPOSITION_MODE,
                provider_order=tuple(provider_order),
                max_calls=2,
                source_commit=head,
                worker_id=POOL_WORKER_ID,
            )
            if pool_assignment["compose_project"] != compose_project:
                # The leases name the conversation volumes of one exact
                # project; launching under another would use other sessions.
                raise ValueError(
                    "Reserved decomposition sessions name another Compose project than this launch"
                )
            record["pool"] = {
                "lease_bundle_path": pool_assignment["lease_bundle_path"],
                "repository_identity": pool_assignment["repository_identity"],
                "checkout_identity": pool_assignment["checkout_identity"],
                "compose_project": pool_assignment["compose_project"],
                "lease_keys": sorted(pool_assignment["leases"]),
                "lease_ids": {
                    key: value["lease_id"]
                    for key, value in sorted(pool_assignment["leases"].items())
                },
                "skipped_keys": list(pool_assignment["skipped_keys"]),
            }
            write_record(path, record)

        command = list(build_compose_command(
            task_id=task_id,
            project=compose_project,
            providers=",".join(provider_order),
            max_calls=2,
            run_id=run_id,
            pool_assignment=pool_assignment,
        ))
        if container_name is not None:
            position = command.index("run") + 1
            named: list[str] = ["--name", container_name]
            for key, value in sorted(labels.items()):
                named.extend(["--label", f"{key}={value}"])
            command[position:position] = named
        command.extend(("--source", "/workspace", "--output-root", "/decomposition-output"))
        with Path(record["stdout_log"]).open("wb") as stdout, Path(record["stderr_log"]).open("wb") as stderr:
            try:
                # Marked before the call, not after it returns: a timeout or a
                # KeyboardInterrupt leaves real conversations behind, and those
                # must be retired rather than returned as never invoked.
                spawned = True
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
            except OSError:
                # The spawn itself failed, so Docker never started, no
                # reservation was ever invoked, and every lease is returned
                # uncharged.
                spawned = False
                pool_lifecycle = _cancel_unstarted_pool(owner, run_id=run_id)
                raise
        # Settle from the run's durable artifacts whatever the exit code says:
        # the artifacts, not the process, decide what each conversation proved.
        pool_lifecycle = _settle_pool(owner, run_id=run_id, run_dir=artifact_root)
        if pool_lifecycle is not None:
            record["pool_lifecycle"] = pool_lifecycle
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
        if owner is not None and pool_lifecycle is None:
            if spawned:
                # The provider process really started, so a timeout or an
                # interrupt settles from the run's own artifacts: those
                # conversations are retired as interrupted, never resumed.
                pool_lifecycle = _settle_pool(owner, run_id=run_id, run_dir=artifact_root)
            else:
                # A precondition failed after the reservation and before any
                # provider ran; the leases are returned uncharged.
                pool_lifecycle = _cancel_unstarted_pool(owner, run_id=run_id)
        if pool_lifecycle is not None:
            record["pool_lifecycle"] = pool_lifecycle
        record.update(status="failed", completed_at_utc=_now(), error=f"{type(exc).__name__}: {exc}")
        write_record(path, record)
        raise
    finally:
        if owner is not None:
            # Settling and cancelling release their own run liveness; this
            # releases anything a failure left held, on every path.
            owner.close()


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
    """Apply the exact independently reviewed plan to the local Source.

    Application shares the Source integration lock with candidate integration
    and synchronization, so no two Source-moving operations can interleave.
    """

    from Pipeline.AssistantControl.review import _source_integration_lock

    task_id = validate_task_id(task_id)
    with _source_integration_lock(manager.source):
        return _apply_locked(
            manager, task_id, run_id=run_id,
            expected_source_commit=expected_source_commit, target_branch=target_branch,
        )


def _apply_locked(
    manager: Checkouts,
    task_id: str,
    *,
    run_id: str,
    expected_source_commit: str,
    target_branch: str,
) -> dict[str, Any]:
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
