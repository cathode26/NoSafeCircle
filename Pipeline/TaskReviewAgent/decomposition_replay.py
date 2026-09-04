"""Read-only proof that an authorized decomposition plan is present in HEAD."""

from __future__ import annotations

import json
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TASK_GRAPH_ROOT = ROOT / "Pipeline" / "TaskGraph"
if str(TASK_GRAPH_ROOT) not in sys.path:
    sys.path.insert(0, str(TASK_GRAPH_ROOT))

from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    WorkflowEventType,
    WorkflowPhase,
)
from apply_graph_delta import (  # noqa: E402
    GraphApplyReplayInspection,
    inspect_graph_delta_replay,
)
from graph_delta import GraphDeltaPlan  # noqa: E402


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
    approval_index = next(
        (
            index
            for index in range(len(events) - 1, -1, -1)
            if events[index].event_type
            is WorkflowEventType.DECOMPOSITION_APPLICATION_APPROVED
        ),
        None,
    )
    if approval_index is None:
        raise DecompositionReplayError(
            "decomposition_apply Issue has no durable human approval event"
        )
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
    approved_plan_id = events[approval_index].details.get("reviewed_plan_id")
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
    graph_delta = GraphDeltaPlan.from_payload(
        _load_object(artifact_root / "graph_delta.json")
    )
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
