"""Validate the durable retirement proof for a published decomposition undo.

The reset helper preserves a completed decomposition Issue as immutable audit
history.  Its exact authorized recovery comment is the only signal that the
closed workflow no longer owns a replacement run.  This module is shared by
the writer/resume path and completed-Issue discovery so those two boundaries
cannot disagree again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .actor_policy import actor_login, default_actor_policy
from .issue_workflow import (
    ALL_STATE_LABELS,
    STATE_LABELS,
    WorkflowContractError,
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    parse_events,
    parse_state,
    validate_event_chain,
)


RECOVERY_MARKER_PREFIX = "nsc-published-decomposition-undo-recovery:"
_RECOVERY_MARKER_RE = re.compile(
    r"<!-- nsc-published-decomposition-undo-recovery: (?P<undo>[0-9a-f]{40}) -->"
)
_RECOVERY_BINDING_RE = re.compile(
    r"The exact `(?P<task>NSC-[0-9]+)` D1C application "
    r"`(?P<apply>[0-9a-f]{40})` for "
    r"`(?P<plan>GDP-[0-9a-f]{64})` was already additively undone by "
    r"`(?P<undo>[0-9a-f]{40})`\."
)


class PublishedUndoRetirementError(ValueError):
    """Raised when trusted recovery-shaped evidence is malformed or conflicts."""


@dataclass(frozen=True)
class PublishedUndoRetirement:
    task_id: str
    plan_id: str
    apply_commit: str
    undo_commit: str


def render_published_undo_recovery_comment(
    evidence: PublishedUndoRetirement,
) -> str:
    """Render the one authoritative recovery-comment grammar."""

    return (
        "## Published decomposition undo recovered\n\n"
        f"The exact `{evidence.task_id}` D1C application `{evidence.apply_commit}` "
        f"for `{evidence.plan_id}` was already additively undone by "
        f"`{evidence.undo_commit}`. The undo is in current `main` history and "
        "no later commit touched the decomposition or child-owned paths.\n\n"
        "This Issue is being closed to retire stale coordination only. Its "
        "hashed workflow state and audit comments are retained unchanged; no "
        "task delivery or child work is being erased.\n\n"
        "<!-- nsc-published-decomposition-undo-recovery: "
        f"{evidence.undo_commit} -->"
    )


def _issue_labels(issue: Mapping[str, Any]) -> frozenset[str]:
    labels: set[str] = set()
    for item in issue.get("labels") or ():
        name = item.get("name") if isinstance(item, Mapping) else item
        if isinstance(name, str) and name:
            labels.add(name)
    return frozenset(labels)


def parse_authorized_recovery_comment(
    comments: Iterable[Any],
) -> PublishedUndoRetirement | None:
    """Parse exactly one authorized, fully bound recovery comment.

    Unauthorized marker-shaped comments carry no authority and are ignored.
    Once an authorized actor uses the reserved marker prefix, malformed,
    ambiguous, or duplicate evidence fails closed.
    """

    policy = default_actor_policy()
    found: list[PublishedUndoRetirement] = []
    for comment in comments:
        body = comment.get("body") if isinstance(comment, Mapping) else None
        if not isinstance(body, str) or RECOVERY_MARKER_PREFIX not in body:
            continue
        login = actor_login(comment)
        if login is None or not policy.is_authorized_actor(login):
            continue
        if body.count(RECOVERY_MARKER_PREFIX) != 1:
            raise PublishedUndoRetirementError(
                "authorized published-decomposition-undo recovery comment has "
                "ambiguous reserved markers"
            )
        marker_matches = list(_RECOVERY_MARKER_RE.finditer(body))
        binding_matches = list(_RECOVERY_BINDING_RE.finditer(body))
        if len(marker_matches) != 1 or len(binding_matches) != 1:
            raise PublishedUndoRetirementError(
                "authorized published-decomposition-undo recovery comment is malformed"
            )
        marker = marker_matches[0].groupdict()
        binding = binding_matches[0].groupdict()
        if marker["undo"] != binding["undo"]:
            raise PublishedUndoRetirementError(
                "authorized recovery marker does not bind the narrated undo commit"
            )
        evidence = PublishedUndoRetirement(
            task_id=binding["task"],
            plan_id=binding["plan"],
            apply_commit=binding["apply"],
            undo_commit=binding["undo"],
        )
        if body.replace("\r\n", "\n") != render_published_undo_recovery_comment(
            evidence
        ):
            raise PublishedUndoRetirementError(
                "authorized published-decomposition-undo recovery comment does not "
                "match the exact writer grammar"
            )
        found.append(evidence)
    if not found:
        return None
    if len(found) != 1:
        raise PublishedUndoRetirementError(
            "multiple authorized published-decomposition-undo recovery comments exist"
        )
    return found[0]


def classify_retired_decomposition_completion(
    issue: Mapping[str, Any],
    comments: Iterable[Any],
) -> PublishedUndoRetirement | None:
    """Return verified retirement evidence for one closed completed workflow.

    A marker on any other workflow shape has no retirement effect.  If the
    shape is the expected completed decomposition, every Issue, event, and
    recovery binding must agree exactly or classification fails closed.
    """

    comments = tuple(comments)
    evidence = parse_authorized_recovery_comment(comments)
    if evidence is None:
        return None
    if str(issue.get("state") or "").upper() != "CLOSED":
        return None
    login = actor_login(issue)
    if login is None or not default_actor_policy().is_authorized_actor(login):
        raise PublishedUndoRetirementError(
            "published-undo recovery Issue author is not authorized"
        )
    body = issue.get("body")
    if not isinstance(body, str):
        raise PublishedUndoRetirementError(
            "published-undo recovery Issue has no workflow body"
        )
    try:
        state = parse_state(body)
    except WorkflowContractError as exc:
        raise PublishedUndoRetirementError(
            f"published-undo recovery workflow state is invalid: {exc}"
        ) from exc
    if state is None:
        raise PublishedUndoRetirementError(
            "published-undo recovery Issue has no managed workflow state"
        )
    if (
        state.state is not WorkflowState.COMPLETE
        or state.phase is not WorkflowPhase.DECOMPOSITION_APPLY
    ):
        return None
    state_labels = _issue_labels(issue) & frozenset(ALL_STATE_LABELS)
    expected_label = STATE_LABELS[WorkflowState.COMPLETE.value]
    if state_labels != {expected_label}:
        raise PublishedUndoRetirementError(
            "published-undo recovery Issue does not have the exact complete state label"
        )
    try:
        events = validate_event_chain(state, parse_events(comments))
    except WorkflowContractError as exc:
        raise PublishedUndoRetirementError(
            f"published-undo recovery workflow event chain is invalid: {exc}"
        ) from exc
    if not events:
        raise PublishedUndoRetirementError(
            "published-undo recovery workflow has no terminal event"
        )
    terminal = events[-1]
    details = terminal.details
    if (
        terminal.event_type is not WorkflowEventType.COMPLETED
        or terminal.actor_type is not WorkflowActor.AGENT
        or details.get("work_type") != "decomposition"
    ):
        raise PublishedUndoRetirementError(
            "published-undo recovery terminal event is not a decomposition completion"
        )
    plan_id = details.get("graph_delta_plan_id")
    apply_commit = details.get("applied_commit")
    if not isinstance(plan_id, str) or re.fullmatch(r"GDP-[0-9a-f]{64}", plan_id) is None:
        raise PublishedUndoRetirementError(
            "published-undo recovery terminal plan identity is invalid"
        )
    if not isinstance(apply_commit, str) or re.fullmatch(r"[0-9a-f]{40}", apply_commit) is None:
        raise PublishedUndoRetirementError(
            "published-undo recovery terminal apply commit is invalid"
        )
    if evidence.task_id != state.task_id:
        raise PublishedUndoRetirementError(
            "published-undo recovery comment names a different task"
        )
    if evidence.plan_id != plan_id:
        raise PublishedUndoRetirementError(
            "published-undo recovery comment names a different decomposition plan"
        )
    if evidence.apply_commit != apply_commit:
        raise PublishedUndoRetirementError(
            "published-undo recovery comment names a different apply commit"
        )
    return evidence


__all__ = [
    "PublishedUndoRetirement",
    "PublishedUndoRetirementError",
    "RECOVERY_MARKER_PREFIX",
    "classify_retired_decomposition_completion",
    "parse_authorized_recovery_comment",
    "render_published_undo_recovery_comment",
]
