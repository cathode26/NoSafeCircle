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
from typing import Any, Mapping, Sequence

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

from TaskDecomposition.author_checklist import (  # noqa: E402
    CHECKLIST_VERSIONS,
    render_author_checklist,
    verify_author_checklist,
)
from Pipeline.AgentRuntime.contracts import AGENT_INVOCATION_REQUEST_SCHEMA_VERSION  # noqa: E402
from TaskDecomposition.context_builder import ContextPackage, DecompositionPreflightError  # noqa: E402
from TaskDecomposition.bookkeeping_evidence import BookkeepingEvidenceError, verify_bookkeeping  # noqa: E402
from TaskDecomposition.live_decomposition import _model_value_problem  # noqa: E402
from TaskDecomposition.continuation import (  # noqa: E402
    BOOKKEEPER_CONTINUATION_PROBLEM,
    CONTINUATION_MODE,
    continuable_problem,
    source_descends,
)
from TaskDecomposition.continuation_seed import verify_continuation_seed  # noqa: E402
from TaskDecomposition.review_chain import (  # noqa: E402
    ReviewChainError,
    verify_continuation_chain,
    verify_three_call_chain,
)
from TaskDecomposition.run_diagnosis import (  # noqa: E402
    DiagnosisEvidenceError,
    confined,
    expected_invocation_id,
    parse_json_object,
)
from TaskDecomposition.contracts import DecompositionResult  # noqa: E402
from TaskDecomposition.live_decomposition import (  # noqa: E402
    provider_configuration,
    resolve_provider_model_environment,
)
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    _normalize_empty_artifact_placeholder,
    candidate_sha256,
    same_provider_role_pair,
)
from apply_graph_delta import apply_graph_delta  # noqa: E402
from graph_apply_plan import plan_graph_apply  # noqa: E402
from graph_delta import GraphDeltaPlan, plan_graph_delta  # noqa: E402
from TaskDecomposition.policy import validate_decomposition_result  # noqa: E402
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


def _unpooled_provider_environment(provider_order: Sequence[str]) -> dict[str, str]:
    """The model selection for a run with two distinct providers.

    A pooled run pins its model through the lease reservation. A mixed pair has
    no reservation, and until 2026-09-18 it was launched with no ``--env`` at
    all, so ``provider_configuration`` re-ran inside the container with none of
    the host's environment and returned its own defaults. The run reported
    success at ``claude-sonnet-5`` however high the caller had escalated - and
    because the escalation ladder's top rung is the mixed-provider rung, the
    rung whose whole purpose is escalating was the one that silently did not.

    Resolved with the same ``provider_configuration`` the pooled path reserves
    against, so the two answers cannot drift. Only the providers actually in
    this run are named: injecting the other one's default would tell the
    container about a provider it is not using.
    """
    return resolve_provider_model_environment(provider_order)


def _run_directory_started(run_dir: Path) -> bool:
    """True when the run left its own artifact directory behind.

    This is the only never-started signal this module owns. The exception type
    proves nothing: ``subprocess.run`` raises ``OSError`` after a successful
    spawn as well, when its timeout handler cannot kill the live child or when
    the wait cannot reap it.
    """

    try:
        return run_dir.is_dir()
    except OSError:
        return False


def _settle_pool(
    owner: DecompositionSessionPoolOwner | None, *, run_id: str, run_dir: Path,
) -> dict[str, Any] | None:
    """Settle one run's leases from its artifacts; a pool failure never fails the run."""

    if owner is None:
        return None
    if not _run_directory_started(run_dir):
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


def _proves_nothing_started(error: BaseException, run_dir: Path) -> bool:
    """Only an exec that never happened, and no run directory, proves no provider ran.

    `subprocess.run` raises FileNotFoundError or NotADirectoryError when the executable or the
    working directory is missing; nothing started in those cases. Every other OSError is
    ambiguous: `process.kill()` on a live container raises PermissionError on Windows, and
    `os.waitpid` raises ChildProcessError, both after the provider has already run. Treating
    those as unstarted returns used conversations to the pool, where a later run resumes them.
    """

    return isinstance(error, (FileNotFoundError, NotADirectoryError)) and not _run_directory_started(run_dir)


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


def _blocking_findings(entry: Any) -> list[Any]:
    """The BLOCKING findings in one review-history entry.

    This gate used to require `findings == []` -- literally empty, no severity
    filter -- so a reviewer that PASSED the split and appended one ADVISORY note
    failed the entire paid run. `decomp-nsc066-20260924b` died on exactly that.

    `FINDING_SEVERITIES` is {"blocking", "advisory"} and `review_policy` blocks
    only on "blocking"; a pass carrying advisory findings is legitimate and
    `README.md` says so: "One independent PASS ... with no unresolved BLOCKING
    findings, is sufficient for review_ready."

    Kept rather than deleted, at the right granularity: an entry claiming `pass`
    while carrying a blocking finding is still refused. Anything unreadable
    counts as blocking, because this gate withholds rather than grants.
    """
    findings = entry.get("findings")
    if findings is None:
        return []
    if not isinstance(findings, list):
        return [findings]
    blocking = []
    for finding in findings:
        if not isinstance(finding, Mapping) or finding.get("severity") == "blocking":
            blocking.append(finding)
    return blocking


def _verify_checklist_delivery(
    record: dict[str, Any], run_result: dict[str, Any],
) -> dict[str, str]:
    """Prove an opted-in checklist actually reached every invocation.

    Matching labels on the record and the run result are not evidence. The
    retained context must carry an intact checklist of the recorded version
    and hash to the run's context_sha256; the run request must agree; and each
    round's retained invocation request must contain the exact rendered
    checklist for its role. Returns the byte hashes of everything consumed.
    """

    version = record["author_checklist"]
    run_dir = Path(record["artifact_root"])
    hashes: dict[str, str] = {}

    def read(relative: str, label: str) -> dict[str, Any]:
        path = confined(run_dir, relative)
        if not path.is_file():
            raise ValueError(f"Author checklist evidence is missing: {relative}")
        data = path.read_bytes()
        hashes[relative] = hashlib.sha256(data).hexdigest()
        return parse_json_object(data, label)

    try:
        context = ContextPackage.from_payload(read("context.json", "retained context"))
        if verify_author_checklist(context) != version:
            raise ValueError(f"Retained context does not carry the {version!r} author checklist")
        payload = context.to_dict()
        request = read("decomposition_request.json", "decomposition request")
        # The context, the run request and the run result must describe one
        # run: this record's task and run, the reviewed source, and the parent
        # contract the result names.
        bindings = {
            "request run_id": (request.get("run_id"), record["run_id"]),
            "request selected_task_id": (request.get("selected_task_id"), record["task_id"]),
            "request provider_order": (request.get("provider_order"), record["providers"]),
            "request author_checklist": (request.get("author_checklist"), version),
            "request context_sha256": (request.get("context_sha256"), run_result.get("context_sha256")),
            "context hash": (context.semantic_sha256, run_result.get("context_sha256")),
            "request source_identity": (request.get("source_identity"), run_result.get("source_identity")),
            "context source_identity": (payload.get("source_identity"), run_result.get("source_identity")),
            "request task identity": (request.get("task_execution_contract_identity"),
                                      run_result.get("task_execution_contract_identity")),
            "context task identity": ((payload.get("selected_task") or {}).get("task_execution_identity"),
                                      run_result.get("task_execution_contract_identity")),
            "request parent identity": (request.get("d1a_semantic_parent_identity"),
                                        run_result.get("d1a_semantic_parent_identity")),
            "context parent identity": ((payload.get("selected_task") or {}).get("d1a_semantic_parent_identity"),
                                        run_result.get("d1a_semantic_parent_identity")),
        }
        for name, (got, wanted) in bindings.items():
            if got != wanted:
                raise ValueError(f"Author checklist evidence disagrees: {name} is {got!r}, expected {wanted!r}")
        context_text = context.canonical_json()
        rendered = {
            "task_decomposer": render_author_checklist(context, audience="author"),
            "decomposition_reviewer": render_author_checklist(context, audience="reviewer"),
        }
        for entry in run_result.get("rounds") or []:
            role = entry.get("role") if isinstance(entry, Mapping) else None
            if role not in rendered or type(entry.get("round_number")) is not int:
                raise ValueError("A decomposition round has no recognised role for checklist delivery")
            correction = entry.get("correction_of_round") is not None
            invocation = expected_invocation_id(
                record["task_id"], record["run_id"], entry["round_number"], role, correction=correction)
            directory = f"{entry['round_number']:02d}" + ("-correction" if correction else "")
            invocation_request = read(
                f"rounds/{directory}/agent_runtime/{invocation}/request.json", "invocation request")
            if (invocation_request.get("schema_version") != AGENT_INVOCATION_REQUEST_SCHEMA_VERSION
                    or invocation_request.get("run_id") != invocation
                    or invocation_request.get("role") != role):
                raise ValueError(
                    f"Round {entry['round_number']} invocation request is not this round's "
                    f"{role} invocation {invocation}")
            prompt = invocation_request.get("prompt")
            if not isinstance(prompt, str) or rendered[role] not in prompt:
                raise ValueError(
                    f"Round {entry['round_number']} {role} prompt did not carry the author checklist")
            if context_text not in prompt:
                raise ValueError(
                    f"Round {entry['round_number']} {role} prompt did not carry the enriched context")
    except (DecompositionPreflightError, DiagnosisEvidenceError) as exc:
        raise ValueError(f"Author checklist evidence refused: {exc}") from exc
    return hashes


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
    if pooled:
        # The pool skips a key it cannot scope and still reserves what is left,
        # so a reservation that carries one lease is possible and would let one
        # conversation author and review. Both role leases must be present.
        expected_leases = {
            f"{record['providers'][0]}:task_decomposer",
            f"{record['providers'][1]}:decomposition_reviewer",
        }
        if set(reserved_leases) != expected_leases:
            raise ValueError(
                "Same-provider decomposition reserved "
                f"{sorted(reserved_leases)}, not one lease per role"
            )

    if record.get("continue_from") is not None:
        return _verify_continuation_review(
            manager, record, head=head, tree=tree, source_advancement=source_advancement)
    # The budget comes from the durable record the host wrote at launch, never
    # from provider-produced artifacts. A record without one predates the
    # option and is the two-call profile.
    budget = record.get("max_calls", 2)
    if type(budget) is not int or budget not in (2, 3):
        raise ValueError(f"Decomposition record carries unsupported call budget {budget!r}")
    if budget == 3 and pooled:
        raise ValueError("A three-call decomposition budget requires two distinct providers")

    run_path, result_path, graph_path = _artifact_paths(record)
    run_result, run_bytes = _load_object(run_path, "Decomposition run result")
    if budget == 3 and run_result.get("run_status") != "review_ready":
        # A budget-3 run that stopped (a third revision, an authority stop)
        # publishes no approved result; say so instead of a missing-file error.
        raise ValueError(
            f"Three-call decomposition run ended {run_result.get('run_status')!r}; it has no applicable result")
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
        "max_calls": budget,
        **({"calls_used": 2} if budget == 2 else {}),
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
    # The checklist is part of what the reviewed run was asked; a run that
    # used a different one, or none, is not the run this record launched.
    if run_result.get("author_checklist") != record.get("author_checklist"):
        raise ValueError(
            "Decomposition review author checklist is "
            f"{run_result.get('author_checklist')!r}, expected {record.get('author_checklist')!r}"
        )
    checklist_evidence = (
        _verify_checklist_delivery(record, run_result) if "author_checklist" in record else {}
    )
    _verify_bookkeeping_binding(record, run_result)
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
    if budget == 3 or record.get("designer_bookkeeper_version") == "2.0":
        return _verify_three_call_review(
            manager, record, run_result, decomposition, plan, task, digest,
            head=head, tree=tree, source_advancement=source_advancement,
            artifact_bytes=(run_bytes, result_bytes, graph_bytes),
            checklist_evidence=checklist_evidence,
        )
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
            or _blocking_findings(history[-1])):
        raise ValueError("Decomposition review history does not end with a clean pass")
    bookkeeping = None
    if "bookkeeper_model" in record:
        candidate_digest, parent_task = _graph_candidate_digest(manager, record["task_id"])
        try:
            bookkeeping = verify_bookkeeping(
                run_dir=Path(record["artifact_root"]), run_result=run_result, author_entry=author,
                first_provider=record["providers"][0], parent_contract=parent_task,
                candidate_digest=candidate_digest)
        except BookkeepingEvidenceError as exc:
            raise ValueError(f"Decomposition bookkeeping refused: {exc}") from exc

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
            **checklist_evidence,
            **({} if bookkeeping is None else bookkeeping["evidence_sha256"]),
        },
        **({} if bookkeeping is None else {"bookkeeping": {
            key: value for key, value in bookkeeping.items() if key != "evidence_sha256"}}),
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


TIMEOUT_ENVIRONMENT = {
    "task_decomposer": ("NSC_TASK_DECOMPOSER_TIMEOUT_SECONDS", 1440),
    "decomposition_reviewer": ("NSC_DECOMPOSITION_REVIEWER_TIMEOUT_SECONDS", 1200),
}
THREE_CALL_OUTER_TIMEOUT_SECONDS = 6000
# Each candidate compilation permits two attempts at the author timeout.
BOOKKEEPER_ATTEMPTS = 2
THREE_CALL_OVERHEAD_SECONDS = 720


def three_call_timeout_profile(
    environment: Mapping[str, str], *, bookkeeper: bool = False,
) -> dict[str, int]:
    """The author/reviewer timeouts a budget-3 run will be given, or refuse.

    The host chooses them (its override or the engine default), passes them
    to the container explicitly, and records them; review verification then
    requires every round to have run with them. Two author calls (one may be
    the correction) and two reviewer calls plus overhead must fit the outer
    timeout, so a slow round cannot be killed by the host mid-chain.
    """

    profile: dict[str, int] = {}
    for role, (name, default) in TIMEOUT_ENVIRONMENT.items():
        raw = environment.get(name, "") or str(default)
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be a whole number of seconds, not {raw!r}") from exc
        if value <= 0:
            raise ValueError(f"{name} must be positive, not {value}")
        profile[role] = value
    needed = 2 * profile["task_decomposer"] + 2 * profile["decomposition_reviewer"] + THREE_CALL_OVERHEAD_SECONDS
    if needed > THREE_CALL_OUTER_TIMEOUT_SECONDS and not bookkeeper:
        raise ValueError(
            f"Three-call decomposition timeouts need {needed} s, over the "
            f"{THREE_CALL_OUTER_TIMEOUT_SECONDS} s outer bound (2A + 2R + {THREE_CALL_OVERHEAD_SECONDS})")
    return profile


CONTINUATION_MAX_CALLS = 4


def continuation_outer_timeout(
    max_calls: int, profile: Mapping[str, int | float] | None = None, *, bookkeeper: bool = False,
) -> int | float:
    """Every review and optional compilation a continuation may make, plus overhead."""

    if bookkeeper:
        profile = profile or {role: default for role, (_, default) in TIMEOUT_ENVIRONMENT.items()}
        return (BOOKKEEPER_ATTEMPTS * max_calls * profile["task_decomposer"]
                + max_calls * profile["decomposition_reviewer"] + THREE_CALL_OVERHEAD_SECONDS)
    return max_calls * TIMEOUT_ENVIRONMENT["decomposition_reviewer"][1] + THREE_CALL_OVERHEAD_SECONDS


def _verify_inherited_settings(record: Mapping[str, Any], settings: Mapping[str, Any]) -> None:
    """The host must retain the exact compiler protocol and timeouts proved by the prior run."""

    profile = record.get("timeout_profile")
    if not (isinstance(profile, Mapping) and set(profile) == set(TIMEOUT_ENVIRONMENT)
            and all(type(value) in (int, float) and value > 0 for value in profile.values())):
        raise ValueError("Continuation record carries no valid inherited timeout profile")
    for name, wanted in settings.items():
        if record.get(name) != wanted:
            raise ValueError(
                f"Continuation inherited {name} is {record.get(name)!r}, expected {wanted!r}; "
                "bookkeeper settings cannot be overridden")


def _prepare_continuation(
    manager: Checkouts, task_id: str, continue_from: str, provider_order: Sequence[str],
    output_root: Path, head: str,
) -> dict[str, Any] | None:
    """Refuse a continuation that cannot proceed; archive the stopped run's own record.

    Runs under the decomposition lock. Only the record of exactly the run being
    continued, and only when it failed, is moved aside, to the same archive
    name earlier retries used; any other record is preserved and refused.
    """

    prior_path = output_root / continue_from / "decomposition_run_result.json"
    prior, _ = _load_object(prior_path, "Continued decomposition run result")
    prior_request_path = prior_path.with_name("decomposition_request.json")
    prior_request = (_load_object(prior_request_path, "Continued decomposition request")[0]
                     if prior_request_path.exists() else None)
    problem = continuable_problem(prior, request=prior_request)
    if problem == BOOKKEEPER_CONTINUATION_PROBLEM:
        raise ValueError(f"Decomposition run {continue_from} cannot be continued: {problem}")
    if prior.get("task_id") != task_id:
        problem = f"it is a run of {prior.get('task_id')!r}"
    elif list(prior.get("provider_order") or []) != list(provider_order):
        problem = problem or f"it used providers {prior.get('provider_order')!r}"
    elif not source_descends(manager.source, (prior.get("source_identity") or {}).get("head_commit"), head):
        problem = problem or "its source is not an ancestor of the current source; start a fresh run"
    if problem:
        raise ValueError(f"Decomposition run {continue_from} cannot be continued: {problem}")
    settings = None
    if isinstance(prior.get("designer_bookkeeper"), Mapping):
        candidate_digest, parent_task = _graph_candidate_digest(manager, task_id)
        task = load_committed_task(manager.source, task_id, commit=head)
        contract = prior.get("task_execution_contract_identity") or {}
        if (contract.get("sha256") != task["task_contract_sha256"]
                or contract.get("revision") != task.get("contract_revision")):
            raise ValueError("Continuation used another parent contract; a fresh run is required")
        try:
            seed = verify_continuation_seed(
                output_root, prior, parent_contract=parent_task, candidate_digest=candidate_digest)
        except DecompositionPreflightError as exc:
            raise ValueError(f"Decomposition run {continue_from} cannot be continued: {exc}") from exc
        settings = seed["settings"]
        for run_id, value, _ in _continuation_chain(output_root, prior):
            if not source_descends(manager.source, (value.get("source_identity") or {}).get("head_commit"), head):
                raise ValueError(f"Continuation chain run {run_id} reviewed a source that is not an ancestor")
            if value.get("task_execution_contract_identity") != contract:
                raise ValueError(f"Continuation chain run {run_id} reviewed another parent contract")
    path = _record_path(manager, task_id)
    if path.exists():
        current = _read_record(manager, task_id)
        # Name the wrong record first: the settings checks below would otherwise
        # report another run's record as an evidence mismatch.
        if current.get("run_id") != continue_from or current.get("status") != "failed":
            raise ValueError(
                f"Decomposition record for {current.get('run_id')} ({current.get('status')}) is not the "
                f"stopped run {continue_from}; it was preserved")
        if any(key in current for key in ("bookkeeper_model", "bookkeeper_provider",
                                          "designer_bookkeeper_version", "ownership_sheet_review_version")):
            if settings is None:
                raise ValueError(
                    f"Decomposition run {continue_from} cannot be continued: "
                    f"{BOOKKEEPER_CONTINUATION_PROBLEM}")
        if settings is not None:
            _verify_inherited_settings(current, settings)
            _verify_bookkeeping_binding(current, prior)
            _verify_three_call_run_binding(current, prior)
        archived = path.with_name(f"{task_id}.decomposition.{continue_from}.failed.archived.json")
        if archived.exists():
            raise ValueError(f"Archive already exists and was preserved: {archived.name}")
        path.rename(archived)
    return settings


def _continuation_chain(output_root: Path, run_result: Mapping[str, Any]) -> list[tuple[str, dict[str, Any], bytes]]:
    """The runs this continuation continues, oldest first, with their exact bytes."""

    chain: list[tuple[str, dict[str, Any], bytes]] = []
    current = run_result
    while (current.get("continued_from") or {}).get("run_id") is not None:
        prior_id = current["continued_from"]["run_id"]
        if any(run_id == prior_id for run_id, _, _ in chain) or not _RUN_ID.fullmatch(str(prior_id)):
            raise ValueError(f"Continuation chain is malformed at {prior_id!r}")
        value, data = _load_object(output_root / prior_id / "decomposition_run_result.json", "Continued run result")
        chain.insert(0, (prior_id, value, data))
        current = value
    return chain


def _verify_continuation_review(
    manager: Checkouts, record: dict[str, Any], *, head: str, tree: str, source_advancement: dict[str, Any],
) -> dict[str, Any]:
    """A continuation is applicable only when its whole chain verifies from retained bytes."""

    if same_provider_role_pair(record["providers"]):
        raise ValueError("A continuation requires two distinct providers")
    run_path, result_path, graph_path = _artifact_paths(record)
    run_result, run_bytes = _load_object(run_path, "Decomposition run result")
    if run_result.get("run_status") != "review_ready":
        raise ValueError(f"Continuation ended {run_result.get('run_status')!r}; it has no applicable result")
    result_payload, result_bytes = _load_object(result_path, "Decomposition result")
    graph_payload, graph_bytes = _load_object(graph_path, "Graph delta")
    decomposition = DecompositionResult.from_dict(result_payload)
    plan = GraphDeltaPlan.from_payload(graph_payload)
    task = load_committed_task(manager.source, record["task_id"], commit=head,
                               expected_sha256=record["task_contract_sha256"])
    expected = {
        "mode": CONTINUATION_MODE, "run_id": record["run_id"], "task_id": record["task_id"],
        "provider_order": record["providers"], "max_calls": record["max_calls"], "run_status": "review_ready",
        "decision": "decomposed", "review_independence": "cross_provider", "authority": "review_only_not_applied",
        "unresolved_findings": [], "rejection_reasons": [],
    }
    for field, wanted in expected.items():
        if run_result.get(field) != wanted:
            raise ValueError(f"Continuation review {field} is {run_result.get(field)!r}, expected {wanted!r}")
    if (run_result.get("continued_from") or {}).get("run_id") != record["continue_from"]:
        raise ValueError("Continuation continues another run than its record names")
    identity = run_result.get("source_identity") or {}
    if (identity.get("head_commit") != record.get("source_commit")
            or identity.get("head_tree") != record.get("source_tree")):
        raise ValueError("Continuation used another source commit or tree")
    contract = run_result.get("task_execution_contract_identity") or {}
    if (contract.get("sha256") != task["task_contract_sha256"]
            or contract.get("revision") != task.get("contract_revision")):
        raise ValueError("Continuation used another parent contract")

    output_root = Path(record["output_root"])
    chain = _continuation_chain(output_root, run_result)
    candidate_digest, parent_task = _graph_candidate_digest(manager, record["task_id"])
    providers = tuple(record["providers"])
    hashes: dict[str, str] = {}
    settings = None
    _verify_bookkeeping_binding(record, run_result)
    bookkeeper = "designer_bookkeeper" in run_result
    try:
        if not chain:
            raise ValueError("Continuation has no retained prior run")
        base_id, base, base_bytes = chain[0]
        if not bookkeeper and (base.get("mode") != "round_robin_d1b2" or base.get("max_calls") != 3):
            raise ValueError(f"Continuation chain starts at {base_id}, which is not a three-call run")
        for run_id, value, _ in chain:
            if not source_descends(manager.source, (value.get("source_identity") or {}).get("head_commit"),
                                   str(identity.get("head_commit"))):
                raise ValueError(f"Continuation chain run {run_id} reviewed a source that is not an ancestor")
            if value.get("task_execution_contract_identity") != run_result.get("task_execution_contract_identity"):
                raise ValueError(f"Continuation chain run {run_id} reviewed another parent contract")
        if bookkeeper:
            seed = verify_continuation_seed(
                output_root, chain[-1][1], parent_contract=parent_task, candidate_digest=candidate_digest)
            settings = seed["settings"]
            _verify_inherited_settings(record, settings)
            hashes.update(_verify_three_call_run_binding(record, run_result))
            hashes.update(seed["evidence_sha256"])
            prior = seed["proof"]
            previous_bytes = chain[-1][2]
        else:
            prior = verify_three_call_chain(
                run_dir=output_root / base_id, run_result=base, providers=providers,
                candidate_digest=candidate_digest, parent_contract=parent_task, open_end=True)
            hashes.update({f"{base_id}/{key}": value for key, value in prior["evidence_sha256"].items()})
            previous_bytes = base_bytes
            for run_id, value, data in chain[1:]:
                prior = verify_continuation_chain(
                    run_dir=output_root / run_id, run_result=value, prior=prior,
                    prior_run_result_sha256=hashlib.sha256(previous_bytes).hexdigest(), providers=providers,
                    candidate_digest=candidate_digest, open_end=True)
                hashes.update({f"{run_id}/{key}": digest for key, digest in prior["evidence_sha256"].items()})
                previous_bytes = data
        final = verify_continuation_chain(
            run_dir=Path(record["artifact_root"]), run_result=run_result, prior=prior,
            prior_run_result_sha256=hashlib.sha256(previous_bytes).hexdigest(), providers=providers,
            candidate_digest=candidate_digest, parent_contract=parent_task,
            timeouts=None if settings is None else settings["timeout_profile"])
    except (ReviewChainError, DecompositionPreflightError) as exc:
        raise ValueError(f"Continuation review refused: {exc}") from exc
    digest = candidate_sha256(decomposition)
    approved = final["approved_candidate"]
    if approved.get("sha256") != digest or approved.get("graph_delta_plan_id") != plan.plan_id:
        raise ValueError("Continuation review refused: the approved candidate is not this run's result")
    fresh = _fresh_plan_proof(manager, decomposition, plan)
    child_ids = sorted(plan.allocated_local_key_to_task_id.values())
    if len(child_ids) != len(set(child_ids)) or not child_ids:
        raise ValueError("Reviewed decomposition plan did not allocate unique children")
    return {
        "status": "review_ready",
        "task_id": record["task_id"],
        "run_id": record["run_id"],
        "continued_runs": [run_id for run_id, _, _ in chain],
        "plan_id": plan.plan_id,
        "child_ids": child_ids,
        "candidate_sha256": digest,
        "artifact_sha256": {
            "decomposition_run_result.json": hashlib.sha256(run_bytes).hexdigest(),
            "decomposition_result.json": hashlib.sha256(result_bytes).hexdigest(),
            "graph_delta.json": hashlib.sha256(graph_bytes).hexdigest(),
            **{f"{run_id}/decomposition_run_result.json": hashlib.sha256(data).hexdigest()
               for run_id, _, data in chain},
            **hashes,
            **final["evidence_sha256"],
        },
        "reviewer_provider": final["approver_provider"],
        "models": final["models"],
        "calls_used": final["calls_used"],
        **({} if settings is None else {"timeout_profile": dict(settings["timeout_profile"])}),
        **({} if final.get("bookkeeping") is None else {"bookkeeping": final["bookkeeping"]}),
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


def bookkeeper_outer_timeout(max_calls: int, profile: Mapping[str, int] | None) -> int:
    """The host bound for a designer/bookkeeper run: every call it may make, plus overhead.

    Designer and its correction, two compilation attempts per candidate-producing
    round, and every reviewer round the budget allows.
    """

    author = profile["task_decomposer"] if profile is not None else TIMEOUT_ENVIRONMENT["task_decomposer"][1]
    reviewer = (profile["decomposition_reviewer"] if profile is not None
                else TIMEOUT_ENVIRONMENT["decomposition_reviewer"][1])
    return (2 + BOOKKEEPER_ATTEMPTS * max_calls) * author + (max_calls - 1) * reviewer + THREE_CALL_OVERHEAD_SECONDS


def _verify_three_call_run_binding(record: dict[str, Any], run_result: dict[str, Any]) -> dict[str, str]:
    """Bind a budget-3 run's retained request and context to this record.

    Returns the byte hashes of both files.
    """

    run_dir = Path(record["artifact_root"])
    hashes: dict[str, str] = {}

    def read(relative: str, label: str) -> dict[str, Any]:
        path = confined(run_dir, relative)
        if not path.is_file():
            raise ValueError(f"Three-call run evidence is missing: {relative}")
        data = path.read_bytes()
        hashes[relative] = hashlib.sha256(data).hexdigest()
        return parse_json_object(data, label)

    try:
        context = ContextPackage.from_payload(read("context.json", "retained context"))
        request = read("decomposition_request.json", "decomposition request")
    except DiagnosisEvidenceError as exc:
        raise ValueError(f"Three-call run evidence refused: {exc}") from exc
    payload = context.to_dict()
    selected = payload.get("selected_task") or {}
    bindings = {
        "request run_id": (request.get("run_id"), record["run_id"]),
        "request selected_task_id": (request.get("selected_task_id"), record["task_id"]),
        "request provider_order": (request.get("provider_order"), record["providers"]),
        "request max_calls": (request.get("max_calls"), record.get("max_calls", 2)),
        "request context_sha256": (request.get("context_sha256"), run_result.get("context_sha256")),
        "context hash": (context.semantic_sha256, run_result.get("context_sha256")),
        "request source_identity": (request.get("source_identity"), run_result.get("source_identity")),
        "context source_identity": (payload.get("source_identity"), run_result.get("source_identity")),
        "request task identity": (request.get("task_execution_contract_identity"),
                                  run_result.get("task_execution_contract_identity")),
        "context task identity": (selected.get("task_execution_identity"),
                                  run_result.get("task_execution_contract_identity")),
        "request parent identity": (request.get("d1a_semantic_parent_identity"),
                                    run_result.get("d1a_semantic_parent_identity")),
        "context parent identity": (selected.get("d1a_semantic_parent_identity"),
                                    run_result.get("d1a_semantic_parent_identity")),
    }
    if record.get("designer_bookkeeper_version") == "2.0":
        for name in ("designer_bookkeeper_version", "ownership_sheet_review_version",
                     "bookkeeper_provider", "bookkeeper_model"):
            bindings[f"request {name}"] = (request.get(name), record.get(name))
        profile = record["timeout_profile"]
        bindings["request author timeout"] = (
            request.get("author_timeout_seconds"), profile["task_decomposer"])
        bindings["request reviewer timeout"] = (
            request.get("reviewer_timeout_seconds"), profile["decomposition_reviewer"])
    for name, (got, wanted) in bindings.items():
        if got != wanted or (name == "request max_calls" and type(got) is not int):
            raise ValueError(f"Three-call run evidence disagrees: {name} is {got!r}, expected {wanted!r}")
    return hashes


def _require_pinned_proof(record: dict[str, Any], review: dict[str, Any]) -> None:
    """A budget-3 or continuation review's proof bytes must still be the ones recorded."""

    if (record.get("max_calls") != 3 and record.get("continue_from") is None
            and record.get("designer_bookkeeper_version") != "2.0"):
        return
    recorded = (record.get("review") or {}).get("artifact_sha256")
    if not isinstance(recorded, Mapping) or not recorded:
        raise ValueError("Decomposition record carries no recorded proof to check against")
    if recorded != review.get("artifact_sha256"):
        raise ValueError("Decomposition proof bytes changed since the review was recorded")


def _fresh_plan_proof(manager: Checkouts, decomposition: Any, plan: Any) -> Any:
    fresh = plan_graph_apply(
        load_persistent_work_graph(manager.source),
        decomposition.parent_task,
        decomposition,
        plan,
    )
    if fresh.status != "fresh" or fresh.stored_plan_id != plan.plan_id:
        raise ValueError(f"Reviewed decomposition plan is not fresh: {fresh.status}: {fresh.reason}")
    if not (fresh.expected_parent_semantic_hash
            == fresh.actual_parent_semantic_hash
            == decomposition.parent_task.contract_sha256):
        raise ValueError("Current parent contract differs from the reviewed semantic authorization")
    return fresh


def _graph_candidate_digest(manager: Checkouts, task_id: str) -> tuple[Any, dict[str, Any]]:
    """The producer's own candidate normalisation and validation against the current graph."""

    graph = load_persistent_work_graph(manager.source)
    parent_task = graph.tasks_by_id.get(task_id)
    if parent_task is None:
        raise ValueError("Decomposition parent is absent from the current graph")

    def candidate_digest(raw: Mapping[str, Any]) -> tuple[str, str | None]:
        # Exactly the producer's normalisation and validation
        # (round_robin_decomposition._validate_candidate).
        result = validate_decomposition_result(
            _normalize_empty_artifact_placeholder(dict(raw)), parent_task=parent_task,
            existing_reconciliation_keys=graph.plan.id_map.keys())
        plan_id = (plan_graph_delta(graph, result.parent_task, result).plan_id
                   if result.decision == "decomposed" else None)
        return candidate_sha256(result), plan_id
    return candidate_digest, parent_task


def _verify_bookkeeping_binding(record: dict[str, Any], run_result: dict[str, Any]) -> None:
    """A designer/bookkeeper run is exactly the one this record launched, and vice versa."""

    recorded = record.get("bookkeeper_model")
    evidence = run_result.get("designer_bookkeeper")
    pinned = "designer_bookkeeper_version" in record or "ownership_sheet_review_version" in record
    if recorded is None and "designer_bookkeeper" not in run_result and not pinned:
        return
    if recorded is None or not isinstance(evidence, Mapping) or evidence.get("bookkeeper_model") != recorded:
        raise ValueError(
            f"Decomposition bookkeeper model is {evidence.get('bookkeeper_model') if isinstance(evidence, Mapping) else evidence!r}, "
            f"the record launched {recorded!r}")
    if pinned or evidence.get("schema_version") == "2.0":
        if (record.get("designer_bookkeeper_version") != "2.0"
                or record.get("ownership_sheet_review_version") != "1.1"
                or evidence.get("schema_version") != "2.0"
                or record.get("bookkeeper_provider") != record["providers"][0]
                or evidence.get("bookkeeper_provider") != record.get("bookkeeper_provider")):
            raise ValueError("Decomposition bookkeeping protocol or fixed provider disagrees with its launch record")


def _verify_three_call_review(
    manager: Checkouts, record: dict[str, Any], run_result: dict[str, Any],
    decomposition: Any, plan: Any, task: dict[str, Any], digest: str, *,
    head: str, tree: str, source_advancement: dict[str, Any],
    artifact_bytes: tuple[bytes, bytes, bytes],
    checklist_evidence: dict[str, str],
) -> dict[str, Any]:
    """The opt-in budget-3 profile: the whole review chain is replayed.

    Every freshness guard is the same as in the two-call profile; only the
    round-shape proof differs, and it comes from the pure chain verifier.
    """

    profile = record.get("timeout_profile")
    if not (isinstance(profile, Mapping) and set(profile) == set(TIMEOUT_ENVIRONMENT)
            and all(type(value) is int and value > 0 for value in profile.values())):
        raise ValueError("Three-call decomposition record carries no valid timeout profile")
    binding_evidence = _verify_three_call_run_binding(record, run_result)
    candidate_digest, parent_task = _graph_candidate_digest(manager, record["task_id"])

    try:
        chain = verify_three_call_chain(
            run_dir=Path(record["artifact_root"]), run_result=run_result,
            providers=tuple(record["providers"]), candidate_digest=candidate_digest,
            timeouts={role: float(value) for role, value in profile.items()},
            parent_contract=parent_task,
        )
    except ReviewChainError as exc:
        raise ValueError(f"Three-call decomposition review refused: {exc}") from exc
    approved = chain["approved_candidate"]
    if approved.get("sha256") != digest or approved.get("graph_delta_plan_id") != plan.plan_id:
        raise ValueError("Three-call decomposition review refused: D3_FINAL_ARTIFACTS: "
                         "the approved candidate is not this run's decomposition result")
    history = run_result.get("finding_history")
    if (not isinstance(history, list) or not history
            or history[-1].get("verdict") != "pass"
            or history[-1].get("reviewed_candidate_sha256") != digest
            or _blocking_findings(history[-1])):
        raise ValueError("Decomposition review history does not end with a clean pass")
    fresh = _fresh_plan_proof(manager, decomposition, plan)
    child_ids = sorted(plan.allocated_local_key_to_task_id.values())
    if len(child_ids) != len(set(child_ids)) or not child_ids:
        raise ValueError("Reviewed decomposition plan did not allocate unique children")
    run_bytes, result_bytes, graph_bytes = artifact_bytes
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
            **binding_evidence,
            **chain["evidence_sha256"],
            **checklist_evidence,
        },
        "reviewer_provider": chain["approver_provider"],
        "models": chain["models"],
        "call_budget": record.get("max_calls", 2),
        "timeout_profile": dict(profile),
        "calls_used": chain["calls_used"],
        "author_corrections_used": chain["author_corrections_used"],
        **({} if chain.get("bookkeeping") is None else {"bookkeeping": chain["bookkeeping"]}),
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
    author_checklist: str | None = None,
    max_calls: int = 2,
    bookkeeper_model: str | None = None,
    continue_from: str | None = None,
) -> dict[str, Any]:
    """Run one two-call decomposition proposal: an author and an independent reviewer.

    ``continue_from`` names a retained run of this task that stopped right after
    a revision; the new run reviews that candidate further for ``max_calls``
    (1..4) independent review rounds instead of starting a new design. The
    stopped run's failed record is archived beside it, never deleted.

    ``bookkeeper_model`` opts into the designer/bookkeeper split: the author
    writes an ownership sheet and a call on the same provider at that model
    writes the result from it (at most two attempts). Mixed providers only.

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
    if author_checklist is not None and author_checklist not in CHECKLIST_VERSIONS:
        raise ValueError(f"Unknown decomposition author checklist {author_checklist!r}")
    if continue_from is None and (type(max_calls) is not int or max_calls not in (2, 3)):
        raise ValueError(f"Decomposition call budget must be 2 or 3, not {max_calls!r}")
    if continue_from is not None:
        if not _RUN_ID.fullmatch(continue_from) or bookkeeper_model is not None or author_checklist is not None:
            raise ValueError("A continuation takes a run id and review budget only; the checklist, "
                             "bookkeeper provider/model, protocols, and timeouts are inherited")
        if type(max_calls) is not int or not 1 <= max_calls <= CONTINUATION_MAX_CALLS:
            raise ValueError(f"A continuation runs 1..{CONTINUATION_MAX_CALLS} review calls, not {max_calls!r}")
    if bookkeeper_model is not None:
        problem = _model_value_problem(bookkeeper_model)
        if problem:
            raise ValueError(f"Bookkeeper model {problem}: {bookkeeper_model!r}")
        requested = tuple(item.strip() for item in providers.split(",") if item.strip())
        if len(set(requested)) != 2:
            raise ValueError("The designer/bookkeeper split requires two distinct providers")
    timeout_profile = None
    if max_calls == 3 and continue_from is None:
        requested = tuple(item.strip() for item in providers.split(",") if item.strip())
        if len(requested) != 2 or len(set(requested)) != 2:
            raise ValueError("A three-call decomposition budget requires two distinct providers")
        timeout_profile = three_call_timeout_profile(os.environ, bookkeeper=bookkeeper_model is not None)
    elif bookkeeper_model is not None:
        timeout_profile = three_call_timeout_profile(os.environ, bookkeeper=True)
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
    inherited_settings = None
    with _exclusive_file_lock(manager.records / "decomposition.lock", timeout_seconds=10):
        if continue_from is not None:
            inherited_settings = _prepare_continuation(
                manager, task_id, continue_from, provider_order, output_root, head)
            if inherited_settings is not None:
                timeout_profile = dict(inherited_settings["timeout_profile"])
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
            "max_calls": max_calls,
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
            **({} if author_checklist is None else {"author_checklist": author_checklist}),
            **({} if timeout_profile is None else {"timeout_profile": timeout_profile}),
            **({} if bookkeeper_model is None else {
                "bookkeeper_model": bookkeeper_model, "bookkeeper_provider": provider_order[0],
                "designer_bookkeeper_version": "2.0", "ownership_sheet_review_version": "1.1"}),
            **({} if continue_from is None else {"continue_from": continue_from}),
            **({} if inherited_settings is None else inherited_settings),
        }
        write_record(path, record)

    environment = os.environ.copy()
    environment["NSC_DECOMPOSITION_HOST_OUTPUT_ROOT"] = str(output_root)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    owner: DecompositionSessionPoolOwner | None = None
    pool_assignment: dict[str, Any] | None = None
    pool_lifecycle: dict[str, Any] | None = None
    # Whether settlement was attempted, which is not the same fact as whether
    # it produced a lifecycle: a settle that raised must never be retried here.
    settle_attempted = False
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

        # A mixed pair carries no reservation, so its models are resolved here,
        # from the same host function the pooled path reserves against
        # (provider_configuration) rather than from a second reading of the
        # environment that could drift from it.
        unpooled_environment = None if pooled else _unpooled_provider_environment(provider_order)
        if unpooled_environment:
            record["provider_environment"] = dict(unpooled_environment)
            write_record(path, record)

        command = list(build_compose_command(
            task_id=task_id,
            project=compose_project,
            providers=",".join(provider_order),
            max_calls=max_calls,
            run_id=run_id,
            pool_assignment=pool_assignment,
            provider_environment=unpooled_environment,
            author_checklist=author_checklist,
            timeout_environment=(None if timeout_profile is None else {
                TIMEOUT_ENVIRONMENT[role][0]: seconds for role, seconds in timeout_profile.items()}),
            bookkeeper_model=bookkeeper_model,
            continue_from=continue_from,
        ))
        if container_name is not None:
            position = command.index("run") + 1
            named: list[str] = ["--name", container_name]
            for key, value in sorted(labels.items()):
                named.extend(["--label", f"{key}={value}"])
            command[position:position] = named
        command.extend(("--source", "/workspace", "--output-root", "/decomposition-output"))
        with Path(record["stdout_log"]).open("wb") as stdout, Path(record["stderr_log"]).open("wb") as stderr:
            # An OSError here is not proof that the spawn never happened, so it
            # is handled exactly like a timeout or an interrupt: the run's own
            # artifacts decide what each conversation proved.
            completed = subprocess.run(
                command,
                cwd=manager.source,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                # Three rounds plus the optional correction can outlast the
                # two-call hour; only the opt-in profile gets the longer bound.
                timeout=(
                    continuation_outer_timeout(max_calls, timeout_profile, bookkeeper=inherited_settings is not None)
                    if continue_from is not None
                    else (THREE_CALL_OUTER_TIMEOUT_SECONDS if max_calls == 3 else 3600) if bookkeeper_model is None
                    else bookkeeper_outer_timeout(max_calls, timeout_profile)),
                creationflags=creationflags,
                check=False,
            )
        # Settle from the run's durable artifacts whatever the exit code says:
        # the artifacts, not the process, decide what each conversation proved.
        settle_attempted = True
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
        try:
            if owner is not None and pool_lifecycle is None and not settle_attempted:
                if not _proves_nothing_started(exc, artifact_root):
                    # A provider may have run, so both conversations are retired
                    # rather than resumed later. Ambiguity settles: cancelling a
                    # lease that really ran hands a dirty conversation back to the
                    # pool, while settling one that never ran only spends a session.
                    settle_attempted = True
                    pool_lifecycle = _settle_pool(owner, run_id=run_id, run_dir=artifact_root)
                else:
                    # Two independent proofs that nothing ran: the exec itself
                    # failed, and no run directory exists.
                    pool_lifecycle = _cancel_unstarted_pool(owner, run_id=run_id)
        except Exception as pool_exc:
            # The pool is not the run. A settlement failure is recorded here, it
            # never replaces the run's own error, and it never skips the record
            # write below that takes this task out of `running`.
            pool_lifecycle = {
                "action": "settle" if settle_attempted else "cancel_unstarted",
                "status": "pool_degraded",
                "run_id": run_id,
                "error_type": type(pool_exc).__name__,
                "error": " ".join(str(pool_exc).split())[:900],
            }
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
        _require_pinned_proof(record, review)
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
    # The three-call chain is proven from more retained files than the
    # two-call pair; its proof bytes are pinned when the run settles, and
    # evidence that changed since is refused rather than re-accepted.
    _require_pinned_proof(record, review)
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
