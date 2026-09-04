#!/usr/bin/env python3
"""Validate and advance exact waiting private synthetic-gauntlet Issues.

This is deliberately not a general human-approval bot. It recognizes only the
committed private rehearsal gauntlet provenance, excludes NSC-042, runs the
exact committed Unity validation plan for implementation handoffs, and reviews
the exact two-child decomposition artifact. Successful checks append explicit
agent-owned evidence events; they never fabricate a human PASS or approval.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    semantic_sha256,
    validate_task_id,
)
from Pipeline.TaskReviewAgent.downstream_resilience import (  # noqa: E402
    decomposition_validation_policy_for,
    validation_plan_for,
)
from Pipeline.TaskReviewAgent.issue_queue import repo_root  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    AUTOMATED_DECOMPOSITION_EVIDENCE_AUTHORITY,
    AUTOMATED_DECOMPOSITION_EVIDENCE_SCHEMA_VERSION,
    AUTOMATED_DECOMPOSITION_POLICY_AUTHORITY,
    AUTOMATED_DECOMPOSITION_REVIEW_AUTHORITY,
    AUTOMATED_DECOMPOSITION_REVIEW_STATUS,
    AUTOMATED_VALIDATION_EVIDENCE_AUTHORITY,
    AUTOMATED_VALIDATION_EVIDENCE_SCHEMA_VERSION,
    AUTOMATED_VALIDATION_REPOSITORY,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
)
from Pipeline.TaskReviewAgent.human_action_wait import publish_resume_hint  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowSnapshot,
    IssueWorkflowStoreError,
    VINCENT_INBOX_TITLE,
)
from Pipeline.TaskReviewAgent.prepare_synthetic_gauntlet import (  # noqa: E402
    GAUNTLET_ID,
    PRESERVED_TASK_ID,
    _repository_from_origin,
    _test_filter,
)
from TaskDecomposition.contracts import DecompositionResult  # noqa: E402
from graph_apply_plan import plan_graph_apply  # noqa: E402
from graph_delta import GraphDeltaPlan, semantic_json_sha256  # noqa: E402
from persistent_work_graph import load_persistent_work_graph  # noqa: E402

if TYPE_CHECKING:
    from Pipeline.TaskReviewAgent.autonomous_graph_run import (  # noqa: E402
        SyntheticEvidencePumpResult,
    )


class SyntheticApprovalError(RuntimeError):
    """The waiting Issue is outside the exact disposable approval policy."""


_MANIFEST_LINE = re.compile(r"^Validation manifest: (?P<path>.+)$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "manifest_type",
        "status",
        "validated_state",
        "unity",
        "test_run",
        "artifacts",
        "runner",
    }
)
_VALIDATED_STATE_KEYS = frozenset(
    {
        "commit",
        "tree",
        "post_commit",
        "post_tree",
        "repository_clean_before",
        "repository_clean_after",
    }
)
_UNITY_KEYS = frozenset(
    {"version", "executable", "exit_code", "test_platform", "test_filter"}
)
_TEST_RUN_KEYS = frozenset({"result", "total", "passed", "failed", "skipped"})
_ARTIFACTS_KEYS = frozenset({"xml", "log"})
_ARTIFACT_KEYS = frozenset({"relative_path", "sha256", "size_bytes"})
_RUNNER_KEYS = frozenset({"path"})
_AUTOMATED_WORKER_ID = "synthetic-gauntlet-approver"
_SESSION_PROOF = object()


@dataclass(frozen=True)
class _SyntheticApproverSession:
    """One repository-verified service binding reused by the process-all CLI."""

    source: Path
    checkout_root: Path
    repository: str
    service: IssueWorkflowService
    proof: object


def _open_synthetic_approver_session(
    *,
    source: Path,
    checkout_root: Path,
    confirm_repository: str,
) -> _SyntheticApproverSession:
    exact_source = repo_root(source.resolve())
    repository = _require_private_rehearsal(exact_source, confirm_repository)
    service = IssueWorkflowService(
        backend=GhIssueBackend(source_root=exact_source),
        task_loader=lambda task_id: load_committed_task(exact_source, task_id),
        worker_id=_AUTOMATED_WORKER_ID,
        vincent_inbox_title=VINCENT_INBOX_TITLE,
    )
    return _SyntheticApproverSession(
        source=exact_source,
        checkout_root=checkout_root.resolve(),
        repository=repository,
        service=service,
        proof=_SESSION_PROOF,
    )


def _require_matching_session(
    session: _SyntheticApproverSession,
    *,
    source: Path,
    checkout_root: Path,
    confirm_repository: str,
) -> None:
    if type(session) is not _SyntheticApproverSession or session.proof is not _SESSION_PROOF:
        raise SyntheticApprovalError("synthetic approver session is not authentic")
    if (
        source.resolve() != session.source
        or checkout_root.resolve() != session.checkout_root
        or confirm_repository.casefold() != session.repository.casefold()
    ):
        raise SyntheticApprovalError(
            "synthetic approver session does not match this exact repository request"
        )


def _exact_object(
    value: Any, *, field: str, keys: frozenset[str]
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SyntheticApprovalError(f"{field} must be an object")
    actual = set(value)
    if actual != keys:
        raise SyntheticApprovalError(
            f"{field} keys mismatch; missing={sorted(keys-actual)}, "
            f"extras={sorted(actual-keys)}"
        )
    return value


def _exact_text(value: Any, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise SyntheticApprovalError(f"{field} must be exact non-empty text")
    return value


def _exact_sha(value: Any, *, field: str, sha256: bool = False) -> str:
    text = _exact_text(value, field=field)
    pattern = _SHA256 if sha256 else _SHA40
    if pattern.fullmatch(text) is None:
        raise SyntheticApprovalError(f"{field} has an invalid identity")
    return text


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _artifact_identity(
    manifest_root: Path,
    value: Any,
    *,
    field: str,
    expected_relative_path: str,
) -> str:
    artifact = _exact_object(value, field=field, keys=_ARTIFACT_KEYS)
    relative_path = _exact_text(
        artifact.get("relative_path"), field=f"{field}.relative_path"
    )
    if relative_path != expected_relative_path:
        raise SyntheticApprovalError(
            f"{field}.relative_path must be exactly {expected_relative_path!r}"
        )
    path = (manifest_root / relative_path).resolve()
    if path.parent != manifest_root or not path.is_file() or path.is_symlink():
        raise SyntheticApprovalError(f"{field} is not one exact regular artifact file")
    data = path.read_bytes()
    expected_hash = _exact_sha(
        artifact.get("sha256"), field=f"{field}.sha256", sha256=True
    )
    size = artifact.get("size_bytes")
    if type(size) is not int or size < 0 or size != len(data):
        raise SyntheticApprovalError(f"{field}.size_bytes does not match the file")
    observed_hash = _sha256_bytes(data)
    if observed_hash != expected_hash:
        raise SyntheticApprovalError(f"{field}.sha256 does not match the file")
    return observed_hash


def _manifest_path(stdout: str) -> Path:
    paths = [
        match.group("path")
        for line in stdout.splitlines()
        if (match := _MANIFEST_LINE.fullmatch(line.strip())) is not None
    ]
    if len(paths) != 1:
        raise SyntheticApprovalError(
            "Unity runner must publish exactly one Validation manifest path"
        )
    path = Path(paths[0]).resolve()
    if not path.is_file() or path.is_symlink():
        raise SyntheticApprovalError("Unity validation manifest is not a regular file")
    return path


def _run_text(
    command: Sequence[str], *, cwd: Path, timeout_seconds: float = 180.0
) -> str:
    completed = subprocess.run(
        tuple(command),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        detail = " ".join((completed.stderr or completed.stdout).split())[:900]
        raise SyntheticApprovalError(
            f"command failed ({completed.returncode}): {' '.join(command)}"
            + (f": {detail}" if detail else "")
        )
    return completed.stdout.strip()


def _require_private_rehearsal(source: Path, confirmed_repository: str) -> str:
    origin = _run_text(
        ("git", "-C", str(source), "remote", "get-url", "origin"), cwd=source
    )
    repository = _repository_from_origin(origin)
    if repository.casefold() != confirmed_repository.casefold():
        raise SyntheticApprovalError(
            f"--confirm-repository must exactly name {repository}"
        )
    if repository.casefold() == "cathode26/nosafecircle":
        raise SyntheticApprovalError("synthetic approval refuses production")
    if repository.casefold() != AUTOMATED_VALIDATION_REPOSITORY.casefold():
        raise SyntheticApprovalError(
            "synthetic approval requires the exact canonical rehearsal repository"
        )
    metadata = json.loads(
        _run_text(
            (
                "gh",
                "repo",
                "view",
                repository,
                "--json",
                "nameWithOwner,isPrivate,defaultBranchRef",
            ),
            cwd=source,
        )
    )
    if (
        str(metadata.get("nameWithOwner") or "").casefold()
        != repository.casefold()
        or metadata.get("isPrivate") is not True
        or (metadata.get("defaultBranchRef") or {}).get("name") != "main"
    ):
        raise SyntheticApprovalError(
            "synthetic approval requires the exact private rehearsal with default main"
        )
    if _run_text(
        ("git", "-C", str(source), "branch", "--show-current"), cwd=source
    ) != "main":
        raise SyntheticApprovalError("synthetic approval requires attached main")
    if _run_text(
        (
            "git",
            "-C",
            str(source),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        cwd=source,
    ):
        raise SyntheticApprovalError("synthetic approval controller must be clean")
    head = _run_text(
        ("git", "-C", str(source), "rev-parse", "HEAD"), cwd=source
    )
    _run_text(("git", "-C", str(source), "fetch", "origin", "main"), cwd=source)
    remote = _run_text(
        ("git", "-C", str(source), "rev-parse", "origin/main"), cwd=source
    )
    if head != remote:
        raise SyntheticApprovalError(
            "synthetic approval controller HEAD must exactly match current origin/main"
        )
    return repository


def _direct_gauntlet_task(task: Mapping[str, Any]) -> bool:
    provenance = task.get("provenance")
    return bool(
        isinstance(provenance, Mapping)
        and provenance.get("origin") == "human_approved_synthetic_gauntlet"
        and provenance.get("gauntlet_id") == GAUNTLET_ID
    )


def _require_gauntlet_task(source: Path, task_id: str) -> dict[str, Any]:
    if task_id == PRESERVED_TASK_ID:
        raise SyntheticApprovalError("NSC-042 always requires Vincent's real validation")
    task = load_committed_task(source, task_id)
    if _direct_gauntlet_task(task):
        return task
    provenance = task.get("provenance")
    if not isinstance(provenance, Mapping) or provenance.get(
        "origin"
    ) != "progressive_decomposition":
        raise SyntheticApprovalError(f"{task_id} is not a synthetic gauntlet task")
    parent_id = provenance.get("parent_task_id")
    if not isinstance(parent_id, str):
        raise SyntheticApprovalError(f"{task_id} has no decomposition parent identity")
    parent = load_committed_task(source, parent_id)
    if not _direct_gauntlet_task(parent):
        raise SyntheticApprovalError(
            f"{task_id} was not decomposed from the exact synthetic gauntlet"
        )
    return task


def _expected_implementation_filter(source: Path, task: Mapping[str, Any]) -> str:
    provenance = task.get("provenance")
    if _direct_gauntlet_task(task):
        value = provenance.get("expected_value") if isinstance(provenance, Mapping) else None
        if type(value) is not int or task.get("execution_scope") != "single_agent":
            raise SyntheticApprovalError("direct synthetic task has no exact expected value")
        return _test_filter(value)
    if not isinstance(provenance, Mapping):
        raise SyntheticApprovalError("synthetic child omitted decomposition provenance")
    parent_id = provenance.get("parent_task_id")
    if not isinstance(parent_id, str):
        raise SyntheticApprovalError("synthetic child omitted its parent task ID")
    parent = load_committed_task(source, parent_id)
    number = int(parent_id.split("-")[1])
    expected_paths = (parent.get("provenance") or {}).get("expected_paths")
    resources = set(task.get("exclusive_resources") or ())
    if not isinstance(expected_paths, list) or len(expected_paths) != 4:
        raise SyntheticApprovalError("synthetic parent has no exact expected child paths")
    if resources == {f"repo-file:{path}" for path in expected_paths[:2]}:
        return _test_filter(number, "Alpha")
    if resources == {f"repo-file:{path}" for path in expected_paths[2:]}:
        return _test_filter(number, "Beta")
    raise SyntheticApprovalError("synthetic child resources do not select one exact test")


def _last_decomposition_handoff(snapshot: IssueWorkflowSnapshot):
    handoffs = [
        event
        for event in snapshot.events
        if event.event_type is WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED
    ]
    if not handoffs:
        raise SyntheticApprovalError("decomposition Issue has no exact plan handoff")
    return handoffs[-1]


def review_decomposition_plan(
    source: Path, snapshot: IssueWorkflowSnapshot, task: Mapping[str, Any]
) -> dict[str, Any]:
    if snapshot.state is None:
        raise SyntheticApprovalError("decomposition Issue omitted workflow state")
    handoff = _last_decomposition_handoff(snapshot)
    details = handoff.details
    artifact_root = Path(str(details.get("artifact_root") or "")).resolve()
    graph_path = artifact_root / "graph_delta.json"
    decomposition_path = artifact_root / "decomposition_result.json"
    if (
        not graph_path.is_file()
        or graph_path.is_symlink()
        or not decomposition_path.is_file()
        or decomposition_path.is_symlink()
    ):
        raise SyntheticApprovalError(
            "decomposition handoff artifacts must be exact regular files"
        )
    graph_bytes = graph_path.read_bytes()
    decomposition_bytes = decomposition_path.read_bytes()
    try:
        graph_payload = json.loads(graph_bytes.decode("utf-8"))
        decomposition_payload = json.loads(decomposition_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SyntheticApprovalError(
            "decomposition handoff artifacts must be valid UTF-8 JSON"
        ) from exc
    graph = GraphDeltaPlan.from_payload(
        graph_payload
    )
    decomposition = DecompositionResult.from_dict(
        decomposition_payload
    )
    plan_id = details.get("graph_delta_plan_id")
    if graph.plan_id != plan_id:
        raise SyntheticApprovalError("artifact plan_id differs from the Issue handoff")
    graph_hash = _sha256_bytes(graph.canonical_json().encode("utf-8"))
    if details.get("graph_delta_sha256") != graph_hash:
        raise SyntheticApprovalError(
            "canonical graph delta hash differs from the durable Issue handoff"
        )
    if not _direct_gauntlet_task(task) or not task.get("provenance", {}).get(
        "requires_decomposition"
    ):
        raise SyntheticApprovalError("decomposition parent is not a gauntlet split task")
    if (
        decomposition.decision != "decomposed"
        or len(decomposition.children) != 2
        or decomposition.unsupported_assumptions
        or decomposition.unresolved_questions
    ):
        raise SyntheticApprovalError(
            "synthetic decomposition must be an exact resolved two-child plan"
        )
    parent_payload = dict(task)
    parent_payload.pop("task_contract_sha256", None)
    parent_hash = semantic_json_sha256(parent_payload)
    preflight = plan_graph_apply(
        load_persistent_work_graph(source),
        decomposition.parent_task,
        decomposition,
        graph,
    )
    if preflight.status != "fresh" or preflight.recomputed_plan_id != graph.plan_id:
        raise SyntheticApprovalError(
            "stored decomposition is not an exact fresh deterministic graph plan: "
            f"{preflight.status}: {preflight.reason}"
        )
    graph_payload = graph.to_dict()
    if (
        graph_payload.get("parent_before_hash") != parent_hash
        or decomposition.parent_task.task_id != task.get("id")
        or decomposition.parent_task.contract_sha256 != parent_hash
    ):
        raise SyntheticApprovalError("decomposition parent contract identity changed")

    contracts = graph.proposed_child_contracts
    if len(contracts) != 2:
        raise SyntheticApprovalError("graph delta does not contain exactly two children")
    expected_paths = task.get("provenance", {}).get("expected_paths")
    expected_resources = set(task.get("exclusive_resources") or ())
    if (
        not isinstance(expected_paths, list)
        or len(expected_paths) != 4
        or len(expected_resources) != 4
        or expected_resources != {f"repo-file:{path}" for path in expected_paths}
    ):
        raise SyntheticApprovalError(
            "synthetic decomposition parent does not own its exact four expected paths"
        )
    owned: set[str] = set()
    child_evidence: list[dict[str, Any]] = []
    number = int(str(task["id"]).split("-")[1])
    for child in contracts:
        resources = set(child.get("exclusive_resources") or ())
        if (
            not isinstance(child.get("id"), str)
            or child.get("execution_scope") != "single_agent"
            or child.get("decomposition_state") != "concrete"
            or child.get("parent") != task.get("id")
            or not resources
            or owned.intersection(resources)
        ):
            raise SyntheticApprovalError(
                "synthetic child identity, scope, or resource ownership is invalid"
            )
        provenance = child.get("provenance") or {}
        if (
            provenance.get("origin") != "progressive_decomposition"
            or provenance.get("parent_contract_sha256") != parent_hash
            or provenance.get("graph_delta_plan_id") != plan_id
        ):
            raise SyntheticApprovalError("synthetic child provenance is not exact")
        if resources == {f"repo-file:{path}" for path in expected_paths[:2]}:
            expected_filter = _test_filter(number, "Alpha")
        elif resources == {f"repo-file:{path}" for path in expected_paths[2:]}:
            expected_filter = _test_filter(number, "Beta")
        else:
            raise SyntheticApprovalError(
                "synthetic child does not own one exact Alpha or Beta resource pair"
            )
        gate_text = "\n".join(
            str(item.get("requirement") or "")
            for item in child.get("completion_gates") or ()
            if isinstance(item, Mapping)
        )
        if expected_filter not in gate_text:
            raise SyntheticApprovalError(
                "synthetic child omitted the exact Unity EditMode filter"
            )
        owned.update(resources)
        child_payload = dict(child)
        child_payload.pop("task_contract_sha256", None)
        child_hash = semantic_json_sha256(child_payload)
        claimed_child_hash = child.get("task_contract_sha256")
        if claimed_child_hash is not None and claimed_child_hash != child_hash:
            raise SyntheticApprovalError(
                "synthetic child contract hash differs from its proposed contract"
            )
        child_evidence.append(
            {
                "task_id": child["id"],
                "task_contract_sha256": child_hash,
                "exclusive_resources": sorted(resources),
            }
        )
    if owned != expected_resources:
        raise SyntheticApprovalError(
            "two children do not exactly partition the parent's four file resources"
        )
    state = snapshot.state
    source_commit = _exact_sha(state.head_commit, field="decomposition source commit")
    if (
        state.human_handoff_commit != source_commit
        or details.get("head_commit") != source_commit
        or details.get("branch") != state.branch
        or handoff.event_id != state.last_event_id
    ):
        raise SyntheticApprovalError(
            "decomposition handoff does not match the current Issue identity"
        )
    source_tree = _run_text(
        ("git", "-C", str(source), "rev-parse", f"{source_commit}^{{tree}}"),
        cwd=source,
    )
    _exact_sha(source_tree, field="decomposition source tree")
    exact_task_hash = _exact_sha(
        task.get("task_contract_sha256"),
        field="decomposition task contract",
        sha256=True,
    )
    if state.task_contract_sha256 != exact_task_hash:
        raise SyntheticApprovalError(
            "decomposition Issue and committed task contract hashes differ"
        )
    child_evidence.sort(key=lambda item: item["task_id"])
    policy = decomposition_validation_policy_for(
        source,
        task,
        parent_semantic_hash=parent_hash,
    )
    return {
        "task_id": task["id"],
        "issue_number": snapshot.issue_number,
        "plan_id": plan_id,
        "artifact_root": str(artifact_root),
        "child_ids": [item["id"] for item in contracts],
        "evidence": {
            "schema_version": AUTOMATED_DECOMPOSITION_EVIDENCE_SCHEMA_VERSION,
            "authority": AUTOMATED_DECOMPOSITION_EVIDENCE_AUTHORITY,
            "repository": AUTOMATED_VALIDATION_REPOSITORY,
            "repository_private": True,
            "gauntlet_id": GAUNTLET_ID,
            "task_id": task["id"],
            "handoff_event_id": handoff.event_id,
            "branch": state.branch,
            "source_commit": source_commit,
            "source_tree": source_tree,
            "task_contract_sha256": exact_task_hash,
            "graph_delta_plan_id": plan_id,
            "graph_delta_sha256": graph_hash,
            "decomposition_result_sha256": _sha256_bytes(decomposition_bytes),
            "parent_contract_sha256": parent_hash,
            "parent_exclusive_resources": sorted(expected_resources),
            "children": child_evidence,
            "validation_policy_authority": AUTOMATED_DECOMPOSITION_POLICY_AUTHORITY,
            "validation_policy_sha256": policy["policy_sha256"],
            "review": {
                "authority": AUTOMATED_DECOMPOSITION_REVIEW_AUTHORITY,
                "status": AUTOMATED_DECOMPOSITION_REVIEW_STATUS,
                "fresh_plan_status": "fresh",
                "recomputed_plan_id": graph.plan_id,
                "exact_child_count": 2,
                "resources_disjoint": True,
                "resources_partition_parent": True,
            },
        },
        "status": "exact_synthetic_decomposition_review_passed",
    }


def _run_unity_validation(
    *,
    source: Path,
    checkout_root: Path,
    repository: str,
    snapshot: IssueWorkflowSnapshot,
    task: dict,
) -> dict[str, Any]:
    assert snapshot.state is not None
    state = snapshot.state
    checkout = Path(str(snapshot.state.checkout_path)).resolve()
    expected_checkout = checkout_root.resolve() / task["id"]
    if checkout != expected_checkout or not checkout.is_dir():
        raise SyntheticApprovalError(
            "implementation handoff is not the exact canonical task checkout"
        )
    plan = validation_plan_for(checkout, task)
    expected_filter = _expected_implementation_filter(source, task)
    if (
        plan is None
        or plan.get("required_test_platforms") != ["EditMode"]
        or plan.get("test_filters", {}).get("EditMode") != expected_filter
    ):
        raise SyntheticApprovalError(
            "synthetic task has no exact committed EditMode validation plan"
        )
    script = checkout / "Pipeline" / "Testing" / "run_unity_tests_clean.ps1"
    source_script = source / "Pipeline" / "Testing" / "run_unity_tests_clean.ps1"
    if (
        not script.is_file()
        or script.is_symlink()
        or not source_script.is_file()
        or source_script.is_symlink()
        or script.read_bytes() != source_script.read_bytes()
    ):
        raise SyntheticApprovalError(
            "task checkout does not contain the exact controller-owned Unity runner"
        )
    commit = _exact_sha(state.head_commit, field="Issue handoff commit")
    if state.human_handoff_commit != commit:
        raise SyntheticApprovalError("Issue head and human handoff commits differ")
    if _run_text(("git", "-C", str(checkout), "rev-parse", "HEAD"), cwd=checkout) != commit:
        raise SyntheticApprovalError("task checkout HEAD differs from the Issue handoff")
    tree = _run_text(
        ("git", "-C", str(checkout), "rev-parse", "HEAD^{tree}"), cwd=checkout
    )
    _exact_sha(tree, field="task checkout tree")
    if _run_text(
        (
            "git",
            "-C",
            str(checkout),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        cwd=checkout,
    ):
        raise SyntheticApprovalError("task checkout is dirty before Unity validation")
    command = (
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-TestPlatform",
        "EditMode",
        "-TestFilter",
        expected_filter,
        "-ProjectPath",
        str(checkout),
    )
    completed = subprocess.run(
        command,
        cwd=str(checkout),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=3600.0,
    )
    output = str(completed.stdout or "")
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    if completed.returncode != 0:
        detail = " ".join(output.split())[-1200:]
        raise SyntheticApprovalError(
            f"exact synthetic Unity validation failed ({completed.returncode})"
            + (f": {detail}" if detail else "")
        )
    manifest_path = _manifest_path(output)
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SyntheticApprovalError(
            "Unity validation manifest is not valid UTF-8 JSON"
        ) from exc
    document = _exact_object(
        manifest, field="Unity validation manifest", keys=_MANIFEST_KEYS
    )
    if (
        document.get("schema_version") != "1.0"
        or document.get("manifest_type") != "unity_test_validation"
        or document.get("status") != "passed"
    ):
        raise SyntheticApprovalError("Unity validation manifest header is invalid")

    validated = _exact_object(
        document.get("validated_state"),
        field="Unity validation manifest validated_state",
        keys=_VALIDATED_STATE_KEYS,
    )
    exact_state = {
        "commit": commit,
        "tree": tree,
        "post_commit": commit,
        "post_tree": tree,
        "repository_clean_before": True,
        "repository_clean_after": True,
    }
    if dict(validated) != exact_state:
        raise SyntheticApprovalError(
            "Unity validation manifest does not bind the exact clean handoff state"
        )

    unity = _exact_object(
        document.get("unity"), field="Unity validation manifest unity", keys=_UNITY_KEYS
    )
    if (
        unity.get("exit_code") != 0
        or unity.get("test_platform") != "EditMode"
        or unity.get("test_filter") != expected_filter
    ):
        raise SyntheticApprovalError(
            "Unity validation manifest does not bind the required invocation"
        )
    _exact_text(unity.get("version"), field="Unity validation manifest unity.version")
    _exact_text(
        unity.get("executable"), field="Unity validation manifest unity.executable"
    )

    test_run = _exact_object(
        document.get("test_run"),
        field="Unity validation manifest test_run",
        keys=_TEST_RUN_KEYS,
    )
    counts: dict[str, int] = {}
    for name in ("total", "passed", "failed", "skipped"):
        value = test_run.get(name)
        if type(value) is not int or value < 0:
            raise SyntheticApprovalError(
                f"Unity validation manifest test_run.{name} is invalid"
            )
        counts[name] = value
    if (
        test_run.get("result") != "Passed"
        or counts["passed"] <= 0
        or counts["failed"] != 0
        or counts["total"]
        != counts["passed"] + counts["failed"] + counts["skipped"]
    ):
        raise SyntheticApprovalError(
            "Unity validation manifest does not prove a non-empty passing run"
        )

    artifacts = _exact_object(
        document.get("artifacts"),
        field="Unity validation manifest artifacts",
        keys=_ARTIFACTS_KEYS,
    )
    manifest_root = manifest_path.parent.resolve()
    xml_sha256 = _artifact_identity(
        manifest_root,
        artifacts.get("xml"),
        field="Unity validation manifest artifacts.xml",
        expected_relative_path="test-results.xml",
    )
    log_sha256 = _artifact_identity(
        manifest_root,
        artifacts.get("log"),
        field="Unity validation manifest artifacts.log",
        expected_relative_path="unity.log",
    )
    runner = _exact_object(
        document.get("runner"),
        field="Unity validation manifest runner",
        keys=_RUNNER_KEYS,
    )
    if runner.get("path") != "Pipeline/Testing/run_unity_tests_clean.ps1":
        raise SyntheticApprovalError("Unity validation manifest names another runner")

    post_commit = _run_text(
        ("git", "-C", str(checkout), "rev-parse", "HEAD"), cwd=checkout
    )
    post_tree = _run_text(
        ("git", "-C", str(checkout), "rev-parse", "HEAD^{tree}"), cwd=checkout
    )
    post_status = _run_text(
        (
            "git",
            "-C",
            str(checkout),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        cwd=checkout,
    )
    if post_commit != commit or post_tree != tree or post_status:
        raise SyntheticApprovalError(
            "task checkout changed after the Unity manifest was produced"
        )
    contract_hash = _exact_sha(
        task.get("task_contract_sha256"),
        field="task contract",
        sha256=True,
    )
    if state.task_contract_sha256 != contract_hash:
        raise SyntheticApprovalError("Issue and committed task contract hashes differ")
    branch = _exact_text(state.branch, field="Issue branch")
    policy_authority = _exact_text(
        plan.get("authority"), field="validation policy authority"
    )
    policy_sha256 = _exact_sha(
        plan.get("policy_sha256"), field="validation policy", sha256=True
    )
    handoff_event_id = _exact_sha(
        state.last_event_id, field="Issue handoff event", sha256=True
    )
    validation = {"test_platform": "EditMode", "test_filter": expected_filter}
    evidence = {
        "schema_version": AUTOMATED_VALIDATION_EVIDENCE_SCHEMA_VERSION,
        "authority": AUTOMATED_VALIDATION_EVIDENCE_AUTHORITY,
        "repository": repository,
        "repository_private": True,
        "gauntlet_id": GAUNTLET_ID,
        "task_id": task["id"],
        "handoff_event_id": handoff_event_id,
        "branch": branch,
        "commit": commit,
        "tree": tree,
        "task_contract_sha256": contract_hash,
        "validation_policy_authority": policy_authority,
        "validation_policy_sha256": policy_sha256,
        "required_validations": [validation],
        "unity_validations": [
            {
                **validation,
                "manifest_sha256": _sha256_bytes(manifest_bytes),
                "xml_sha256": xml_sha256,
                "log_sha256": log_sha256,
                "commit": commit,
                "tree": tree,
                "post_commit": post_commit,
                "post_tree": post_tree,
                "repository_clean_before": True,
                "repository_clean_after": True,
                **counts,
            }
        ],
    }
    return {
        "task_id": task["id"],
        "commit": commit,
        "checkout": str(checkout),
        "test_platform": "EditMode",
        "test_filter": expected_filter,
        "manifest_path": str(manifest_path),
        "evidence": evidence,
        "status": "exact_synthetic_unity_validation_passed",
    }


def _apply_automated_decomposition(
    *,
    source: Path,
    service: IssueWorkflowService,
    task_id: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    transitioned = service.apply_automated_decomposition_result(
        task_id=task_id,
        evidence=evidence,
        actor_id=_AUTOMATED_WORKER_ID,
    )
    verified = service.find(task_id)
    if verified is None or not verified.valid or verified.state is None:
        raise SyntheticApprovalError(
            "automated decomposition transition disappeared after post-verification"
        )
    state = verified.state
    if (
        state.phase is not WorkflowPhase.DECOMPOSITION_APPLY
        or state.human_result is not None
        or state.human_handoff_commit != evidence.get("source_commit")
    ):
        raise SyntheticApprovalError(
            "automated decomposition post-state is not exact D1C authority"
        )
    notification_status = "not_configured"
    try:
        notification_status = service.clear_vincent_notification(task_id)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(
            "SYNTHETIC APPROVER: WARNING\n"
            f"Issue is agent_ready but its exact Vincent notification was not removed: {exc}",
            file=sys.stderr,
        )
        notification_status = "warning"
    hint_path: str | None = None
    try:
        hint_path = str(
            publish_resume_hint(
                source,
                task_id=task_id,
                human_handoff_commit=str(state.human_handoff_commit),
                state_version=state.state_version,
                event_id=str(state.last_event_id),
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            "SYNTHETIC APPROVER: WARNING\n"
            f"Issue is agent_ready but its local architect poke failed: {exc}",
            file=sys.stderr,
        )
    return {
        **transitioned,
        "vincent_notification": notification_status,
        "resume_hint_path": hint_path,
    }


def _apply_automated_validation(
    *,
    source: Path,
    service: IssueWorkflowService,
    task_id: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    transitioned = service.apply_automated_validation(
        task_id=task_id,
        evidence=evidence,
        actor_id=_AUTOMATED_WORKER_ID,
    )
    verified = service.find(task_id)
    if verified is None or not verified.valid or verified.state is None:
        raise SyntheticApprovalError(
            "automated validation transition disappeared after post-verification"
        )
    state = verified.state
    if (
        state.phase is not WorkflowPhase.DELIVERY_EVIDENCE
        or state.human_result is not None
        or state.human_handoff_commit != evidence.get("commit")
    ):
        raise SyntheticApprovalError(
            "automated validation post-state is not exact delivery evidence authority"
        )
    notification_status = "not_configured"
    try:
        notification_status = service.clear_vincent_notification(task_id)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(
            "SYNTHETIC APPROVER: WARNING\n"
            f"Issue is agent_ready but its exact Vincent notification was not removed: {exc}",
            file=sys.stderr,
        )
        notification_status = "warning"
    hint_path: str | None = None
    try:
        hint_path = str(
            publish_resume_hint(
                source,
                task_id=task_id,
                human_handoff_commit=str(state.human_handoff_commit),
                state_version=state.state_version,
                event_id=str(state.last_event_id),
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            "SYNTHETIC APPROVER: WARNING\n"
            f"Issue is agent_ready but its local architect poke failed: {exc}",
            file=sys.stderr,
        )
    return {
        **transitioned,
        "vincent_notification": notification_status,
        "resume_hint_path": hint_path,
    }


def _pump_result(
    *,
    task_id: str,
    evidence: Mapping[str, Any],
    transitioned: Mapping[str, Any],
    event_field: str,
) -> "SyntheticEvidencePumpResult":
    """Bind one verified workflow transition to the controller's pump contract."""

    exact_task_id = validate_task_id(task_id)
    event_id = _exact_sha(
        transitioned.get(event_field), field=event_field, sha256=True
    )
    if transitioned.get("last_event_id") != event_id:
        raise SyntheticApprovalError(
            "automated transition event differs from its verified final Issue event"
        )
    workflow_state = transitioned.get("workflow_state")
    if not isinstance(workflow_state, Mapping):
        raise SyntheticApprovalError(
            "automated transition omitted its verified workflow state"
        )
    if (
        workflow_state.get("task_id") != exact_task_id
        or workflow_state.get("human_result") is not None
    ):
        raise SyntheticApprovalError(
            "automated transition post-state changed task identity or human_result"
        )

    # Import lazily so the autonomous controller may import this adapter without
    # creating a module-load cycle. The returned object is the controller's
    # exact class, not a lookalike dataclass or stdout-derived approximation.
    from Pipeline.TaskReviewAgent.autonomous_graph_run import (
        SyntheticEvidencePumpResult,
    )

    return SyntheticEvidencePumpResult(
        task_id=exact_task_id,
        event_id=event_id,
        evidence_sha256=semantic_sha256(evidence),
    )


def process_one_synthetic_handoff(
    task_id: str,
    *,
    source: Path,
    checkout_root: Path,
    confirm_repository: str,
    apply: bool = True,
    report: Callable[[Mapping[str, Any]], None] | None = None,
    _session: _SyntheticApproverSession | None = None,
) -> "SyntheticEvidencePumpResult | None":
    """Validate and optionally advance one exact synthetic human handoff.

    Normal callers receive a fresh repository/private/default-branch/main
    preflight before any Issue access. The CLI supplies only a module-created,
    proof-bearing session so that its process-all loop can reuse that same
    preflight and GitHub service without weakening the public boundary.

    ``None`` is returned for a dry run because no durable workflow event exists.
    An applied call returns the controller's exact structured pump result. One
    invocation resolves and transitions only ``task_id``; it never enumerates or
    advances another synthetic task.
    """

    exact_task_id = validate_task_id(task_id)
    if exact_task_id == PRESERVED_TASK_ID:
        raise SyntheticApprovalError("NSC-042 always requires Vincent's real validation")
    if type(apply) is not bool:
        raise SyntheticApprovalError("apply must be an exact boolean")
    if report is not None and not callable(report):
        raise SyntheticApprovalError("report must be callable when provided")
    exact_checkout_root = checkout_root.resolve()
    if _session is None:
        session = _open_synthetic_approver_session(
            source=source,
            checkout_root=exact_checkout_root,
            confirm_repository=confirm_repository,
        )
    else:
        _require_matching_session(
            _session,
            source=source,
            checkout_root=exact_checkout_root,
            confirm_repository=confirm_repository,
        )
        session = _session

    # This check categorically excludes NSC-042 and any task outside the exact
    # committed gauntlet lineage before its Issue can be mutated.
    task = _require_gauntlet_task(session.source, exact_task_id)
    snapshot = session.service.find(exact_task_id)
    if (
        snapshot is None
        or not snapshot.valid
        or snapshot.state is None
        or getattr(snapshot, "pending_transition", None) is not None
        or snapshot.state.state is not WorkflowState.HUMAN_ACTION_REQUIRED
    ):
        raise SyntheticApprovalError(
            f"selected managed Issue changed before validation: {exact_task_id}"
        )

    phase = snapshot.state.phase
    if phase is WorkflowPhase.DECOMPOSITION_APPLY_AUTHORIZATION:
        reviewed = review_decomposition_plan(session.source, snapshot, task)
        if report is not None:
            report(reviewed)
        if not apply:
            return None
        evidence = reviewed["evidence"]
        transitioned = _apply_automated_decomposition(
            source=session.source,
            service=session.service,
            task_id=exact_task_id,
            evidence=evidence,
        )
        if report is not None:
            report(transitioned)
        return _pump_result(
            task_id=exact_task_id,
            evidence=evidence,
            transitioned=transitioned,
            event_field="automated_decomposition_event_id",
        )

    if phase is WorkflowPhase.UNITY_RUNTIME_VALIDATION:
        plan = {
            "task_id": exact_task_id,
            "issue_number": snapshot.issue_number,
            "commit": snapshot.state.head_commit,
            "status": "exact_synthetic_unity_validation_ready",
        }
        if report is not None:
            report(plan)
        if not apply:
            return None
        validated = _run_unity_validation(
            source=session.source,
            checkout_root=session.checkout_root,
            repository=session.repository,
            snapshot=snapshot,
            task=task,
        )
        if report is not None:
            report(validated)
        evidence = validated["evidence"]
        transitioned = _apply_automated_validation(
            source=session.source,
            service=session.service,
            task_id=exact_task_id,
            evidence=evidence,
        )
        if report is not None:
            report(transitioned)
        return _pump_result(
            task_id=exact_task_id,
            evidence=evidence,
            transitioned=transitioned,
            event_field="automated_validation_event_id",
        )

    raise SyntheticApprovalError(
        f"unsupported human-owned phase for synthetic task: {phase.value}"
    )


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--confirm-repository", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        session = _open_synthetic_approver_session(
            source=args.source,
            checkout_root=args.checkout_root,
            confirm_repository=args.confirm_repository,
        )
        source = session.source
        repository = session.repository
        service = session.service
        waiting = service.list_human_action_required()
        selected_task_ids: list[str] = []
        for entry in waiting:
            state = entry.get("workflow_state") or {}
            task_id = str(state.get("task_id") or "")
            try:
                _require_gauntlet_task(source, task_id)
            except SyntheticApprovalError:
                continue
            selected_task_ids.append(task_id)
        if not selected_task_ids:
            print(
                json.dumps(
                    {
                        "status": "no_synthetic_human_action_required",
                        "repository": repository,
                        "waiting_issue_count": len(waiting),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        processed: list[str] = []
        for task_id in selected_task_ids:
            # Re-read immediately inside the one-item API. A prior Unity run
            # may be long enough for another actor to change a later Issue.
            process_one_synthetic_handoff(
                task_id,
                source=source,
                checkout_root=args.checkout_root,
                confirm_repository=args.confirm_repository,
                apply=args.apply,
                report=_print_json,
                _session=session,
            )
            processed.append(task_id)
        print(
            json.dumps(
                {
                    "status": "synthetic_human_actions_processed",
                    "processed_task_ids": processed,
                },
                indent=2,
                sort_keys=True,
            )
        )
        print(
            "SYNTHETIC APPROVER: "
            + ("APPLIED" if args.apply else "DRY RUN (add --apply)")
        )
        return 0
    except (
        json.JSONDecodeError,
        OSError,
        RuntimeError,
        subprocess.TimeoutExpired,
        ValueError,
    ) as exc:
        print(f"SYNTHETIC APPROVER: STOP\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
