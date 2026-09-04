"""Read-only proof that an authorized decomposition plan is present in HEAD."""

from __future__ import annotations

import json
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
TASK_GRAPH_ROOT = ROOT / "Pipeline" / "TaskGraph"
if str(TASK_GRAPH_ROOT) not in sys.path:
    sys.path.insert(0, str(TASK_GRAPH_ROOT))

from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    AUTOMATED_DECOMPOSITION_POLICY_AUTHORITY,
    WorkflowEventType,
    WorkflowPhase,
)
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_resilience import (  # noqa: E402
    decomposition_validation_policy_for,
)
from apply_graph_delta import (  # noqa: E402
    GraphApplyReplayInspection,
    inspect_graph_delta_replay,
)
from graph_delta import GraphDeltaPlan  # noqa: E402
from TaskDecomposition.contracts import DecompositionResult  # noqa: E402
from TaskDecomposition.policy import semantic_json_sha256  # noqa: E402


_PLAN_ID_RE = re.compile(r"^GDP-[0-9a-f]{64}$")
_GIT_OBJECT_ID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class DecompositionReplayError(RuntimeError):
    """Raised when durable Issue authority cannot prove an exact D1C replay."""


def _git_text(source: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ("git", "-C", str(source), *args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=180.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DecompositionReplayError(
            f"could not inspect D1C Git history: {type(exc).__name__}: {exc}"
        ) from exc
    if completed.returncode != 0:
        detail = " ".join(completed.stderr.split())[:700]
        raise DecompositionReplayError(
            f"git {' '.join(args)} failed while inspecting D1C history"
            + (f": {detail}" if detail else "")
        )
    return completed.stdout.strip()


def find_exact_d1c_commit(
    source: Path,
    *,
    task_id: str,
    plan_id: str,
    authorized_head: str,
    current_head: str,
) -> str:
    """Locate the unique canonical D1C child of the authorized source commit."""

    subject = f"taskgraph: apply {task_id} decomposition {plan_id}"
    commits = tuple(
        line
        for line in _git_text(
            source,
            "rev-list",
            "--ancestry-path",
            f"{authorized_head}..{current_head}",
        ).splitlines()
        if line
    )
    matches = []
    for commit in commits:
        if _git_text(source, "show", "-s", "--format=%s", commit) != subject:
            continue
        parents = _git_text(source, "show", "-s", "--format=%P", commit).split()
        if parents == [authorized_head]:
            matches.append(commit)
    if len(matches) != 1:
        raise DecompositionReplayError(
            "exact already-applied D1C commit could not be identified uniquely "
            f"from {authorized_head} to {current_head}; matches={matches}"
        )
    return matches[0]


@dataclass(frozen=True)
class AuthorizedDecompositionReplay:
    plan_id: str
    authorized_source_head: str
    artifact_root: Path
    graph_delta: GraphDeltaPlan
    inspection: GraphApplyReplayInspection


def _load_object(path: Path) -> dict[str, Any]:
    """Load the legacy human-approved artifact without changing its path policy."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DecompositionReplayError(
            f"authorized graph-delta artifact is unreadable: {type(exc).__name__}: {exc}"
        ) from exc
    if type(value) is not dict:
        raise DecompositionReplayError(
            "authorized graph-delta artifact must contain one JSON object"
        )
    return value


def _load_object_with_bytes(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        if not path.is_file() or path.is_symlink():
            raise OSError("artifact is not one exact regular file")
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DecompositionReplayError(
            f"authorized decomposition artifact is unreadable: {type(exc).__name__}: {exc}"
        ) from exc
    if type(value) is not dict:
        raise DecompositionReplayError(
            "authorized decomposition artifact must contain one JSON object"
        )
    return value, payload


def _semantic_task_hash(task: Mapping[str, Any]) -> str:
    payload = dict(task)
    payload.pop("task_contract_sha256", None)
    return semantic_json_sha256(payload)


def _working_file_matches_committed_blob(
    source: Path, *, authorized_head: str, relative_path: str
) -> bool:
    """Compare through Git's clean filter so a clean CRLF checkout stays valid."""

    path = source / Path(relative_path)
    if not path.is_file() or path.is_symlink():
        return False
    committed_blob = _git_text(
        source, "rev-parse", f"{authorized_head}:{relative_path}"
    )
    working_blob = _git_text(
        source,
        "hash-object",
        f"--path={relative_path}",
        str(path),
    )
    return working_blob == committed_blob


def _validate_automated_authority(
    *,
    source: Path,
    snapshot: Any,
    approval: Any,
    handoff: Any,
    graph_delta: GraphDeltaPlan,
    graph_bytes_hash: str,
    artifact_root: Path,
    authorized_head: str,
) -> None:
    """Recompute every repository/artifact identity carried by machine authority."""

    evidence = approval.details
    if not isinstance(evidence, Mapping):
        raise DecompositionReplayError(
            "automated decomposition approval evidence must be an object"
        )
    if evidence.get("handoff_event_id") != handoff.event_id:
        raise DecompositionReplayError(
            "automated decomposition approval does not bind the exact handoff event"
        )
    if evidence.get("graph_delta_sha256") != graph_bytes_hash:
        raise DecompositionReplayError(
            "automated decomposition graph hash differs from the authorized artifact"
        )

    try:
        source_tree = _git_text(source, "rev-parse", f"{authorized_head}^{{tree}}")
    except DecompositionReplayError:
        raise
    if evidence.get("source_tree") != source_tree:
        raise DecompositionReplayError(
            "automated decomposition source tree differs from the authorized commit"
        )

    state = snapshot.state
    try:
        task = load_committed_task(
            source,
            state.task_id,
            expected_sha256=state.task_contract_sha256,
            commit=authorized_head,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise DecompositionReplayError(
            f"could not prove the committed decomposition parent: {type(exc).__name__}: {exc}"
        ) from exc
    exact_task_hash = task["task_contract_sha256"]
    parent_semantic_hash = _semantic_task_hash(task)
    if (
        evidence.get("task_contract_sha256") != exact_task_hash
        or evidence.get("parent_contract_sha256") != parent_semantic_hash
        or graph_delta.to_dict().get("parent_before_hash") != parent_semantic_hash
    ):
        raise DecompositionReplayError(
            "automated decomposition parent contract identity is stale"
        )

    decomposition_payload, decomposition_bytes = _load_object_with_bytes(
        artifact_root / "decomposition_result.json"
    )
    if evidence.get("decomposition_result_sha256") != hashlib.sha256(
        decomposition_bytes
    ).hexdigest():
        raise DecompositionReplayError(
            "automated decomposition proposal bytes differ from the approved evidence"
        )
    try:
        decomposition = DecompositionResult.from_dict(decomposition_payload)
    except (TypeError, ValueError) as exc:
        raise DecompositionReplayError(
            f"authorized decomposition proposal is invalid: {type(exc).__name__}: {exc}"
        ) from exc
    if (
        decomposition.parent_task.task_id != state.task_id
        or decomposition.parent_task.contract_sha256 != parent_semantic_hash
    ):
        raise DecompositionReplayError(
            "automated decomposition proposal parent identity is stale"
        )

    parent_resources = sorted(task.get("exclusive_resources") or ())
    if evidence.get("parent_exclusive_resources") != parent_resources:
        raise DecompositionReplayError(
            "automated decomposition parent resources differ from the committed contract"
        )
    children: list[dict[str, Any]] = []
    for child in graph_delta.proposed_child_contracts:
        if not isinstance(child, Mapping):
            raise DecompositionReplayError(
                "authorized graph delta contains a malformed proposed child"
            )
        child_payload = dict(child)
        child_payload.pop("task_contract_sha256", None)
        child_id = child_payload.get("id")
        resources = child_payload.get("exclusive_resources")
        if type(child_id) is not str or type(resources) is not list:
            raise DecompositionReplayError(
                "authorized graph delta contains an incomplete proposed child"
            )
        children.append(
            {
                "task_id": child_id,
                "task_contract_sha256": semantic_json_sha256(child_payload),
                "exclusive_resources": sorted(resources),
            }
        )
    children.sort(key=lambda item: item["task_id"])
    if evidence.get("children") != children:
        raise DecompositionReplayError(
            "automated decomposition children differ from the approved evidence"
        )

    policy_relative = "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
    if not _working_file_matches_committed_blob(
        source,
        authorized_head=authorized_head,
        relative_path=policy_relative,
    ):
        raise DecompositionReplayError(
            "working decomposition policy differs from the authorized source commit"
        )
    try:
        policy = decomposition_validation_policy_for(
            source,
            task,
            parent_semantic_hash=parent_semantic_hash,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise DecompositionReplayError(
            f"could not prove the decomposition policy: {type(exc).__name__}: {exc}"
        ) from exc
    if (
        evidence.get("validation_policy_authority")
        != AUTOMATED_DECOMPOSITION_POLICY_AUTHORITY
        or evidence.get("validation_policy_sha256") != policy.get("policy_sha256")
    ):
        raise DecompositionReplayError(
            "automated decomposition validation policy identity is stale"
        )


def inspect_authorized_decomposition_replay(
    *,
    source: Path,
    snapshot: Any,
    expected_head: str,
) -> AuthorizedDecompositionReplay:
    """Validate Issue approval, immutable artifact identity, and exact graph replay."""

    if (
        snapshot is None
        or not getattr(snapshot, "valid", False)
        or getattr(snapshot, "state", None) is None
        or snapshot.state.phase is not WorkflowPhase.DECOMPOSITION_APPLY
    ):
        raise DecompositionReplayError(
            "exact decomposition replay requires a valid decomposition_apply Issue"
        )
    events = tuple(getattr(snapshot, "events", ()))
    approval_types = {
        WorkflowEventType.DECOMPOSITION_APPLICATION_APPROVED,
        WorkflowEventType.AUTOMATED_DECOMPOSITION_APPLICATION_APPROVED,
    }
    approval_index = next(
        (
            index
            for index in range(len(events) - 1, -1, -1)
            if events[index].event_type in approval_types
        ),
        None,
    )
    if approval_index is None:
        raise DecompositionReplayError(
            "decomposition_apply Issue has no durable approval event"
        )
    approval = events[approval_index]
    automated = (
        approval.event_type
        is WorkflowEventType.AUTOMATED_DECOMPOSITION_APPLICATION_APPROVED
    )
    if automated:
        handoff = events[approval_index - 1] if approval_index > 0 else None
        if (
            handoff is None
            or handoff.event_type is not WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED
        ):
            raise DecompositionReplayError(
                "automated decomposition approval must immediately follow its handoff"
            )
    else:
        handoff = next(
            (
                events[index]
                for index in range(approval_index - 1, -1, -1)
                if events[index].event_type
                is WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED
            ),
            None,
        )
    if handoff is None:
        raise DecompositionReplayError(
            "decomposition approval has no preceding durable handoff event"
        )
    details = handoff.details
    plan_id = details.get("graph_delta_plan_id")
    authorized_head = details.get("head_commit")
    artifact_root_text = details.get("artifact_root")
    approved_plan_id = (
        approval.details.get("graph_delta_plan_id")
        if automated
        else approval.details.get("reviewed_plan_id")
    )
    approved_graph_hash = details.get("graph_delta_sha256")
    if type(plan_id) is not str or _PLAN_ID_RE.fullmatch(plan_id) is None:
        raise DecompositionReplayError("durable handoff plan_id is invalid")
    if approved_plan_id != plan_id:
        raise DecompositionReplayError(
            "durable decomposition approval does not match the handoff plan_id"
        )
    if (
        type(authorized_head) is not str
        or _GIT_OBJECT_ID_RE.fullmatch(authorized_head) is None
    ):
        raise DecompositionReplayError("durable handoff source HEAD is invalid")
    if type(artifact_root_text) is not str or not artifact_root_text.strip():
        raise DecompositionReplayError("durable handoff artifact root is invalid")
    artifact_root = Path(artifact_root_text).resolve()
    if automated:
        graph_payload, _graph_bytes = _load_object_with_bytes(
            artifact_root / "graph_delta.json"
        )
    else:
        graph_payload = _load_object(artifact_root / "graph_delta.json")
    graph_delta = GraphDeltaPlan.from_payload(graph_payload)
    if approved_graph_hash is not None and (
        type(approved_graph_hash) is not str
        or re.fullmatch(r"[0-9a-f]{64}", approved_graph_hash) is None
    ):
        raise DecompositionReplayError("durable graph-delta hash is invalid")
    if approved_graph_hash is None and expected_head != authorized_head:
        raise DecompositionReplayError(
            "moved-HEAD decomposition replay requires a hash-bound graph-delta handoff"
        )
    canonical_graph_hash = hashlib.sha256(
        graph_delta.canonical_json().encode("utf-8")
    ).hexdigest()
    if (
        approved_graph_hash is not None
        and canonical_graph_hash != approved_graph_hash
    ):
        raise DecompositionReplayError(
            "authorized graph-delta artifact hash differs from the durable handoff"
        )
    if automated:
        _validate_automated_authority(
            source=source,
            snapshot=snapshot,
            approval=approval,
            handoff=handoff,
            graph_delta=graph_delta,
            graph_bytes_hash=canonical_graph_hash,
            artifact_root=artifact_root,
            authorized_head=authorized_head,
        )
    try:
        payload = graph_delta.to_dict()
        if graph_delta.plan_id != plan_id:
            raise DecompositionReplayError(
                "durable handoff plan_id does not match graph_delta.json"
            )
        parent_before = payload["parent_before_summary"]
        selector = {
            "task_id": parent_before["task_id"],
            "contract_revision": parent_before["contract_revision"],
            "contract_sha256": payload["parent_before_hash"],
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise DecompositionReplayError(
            f"authorized graph-delta identity is invalid: {type(exc).__name__}: {exc}"
        ) from exc
    inspection = inspect_graph_delta_replay(
        source,
        selector,
        graph_delta,
        expected_head=expected_head,
    )
    return AuthorizedDecompositionReplay(
        plan_id=plan_id,
        authorized_source_head=authorized_head,
        artifact_root=artifact_root,
        graph_delta=graph_delta,
        inspection=inspection,
    )


__all__ = [
    "AuthorizedDecompositionReplay",
    "DecompositionReplayError",
    "find_exact_d1c_commit",
    "inspect_authorized_decomposition_replay",
]
