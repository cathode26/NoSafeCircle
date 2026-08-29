"""Ground downstream action choices in exact host-verified delivery facts.

The downstream supervisor is allowed to write semantic surface roles and gate
notes, but it must not invent structural identities.  This extension keeps the
operator/model context small while preserving the exact repository surface
paths, artifact IDs, and gate IDs needed by ``create_delivery_review_proposal``.
It also makes lease acquisition outrank checkout repair while an Issue is still
agent-ready; checkout mutation is a leased side effect.
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any, Mapping, Sequence

from .codex_supervisor import CodexSupervisorError


_INSTALLED = False
_ORIGINALS: dict[str, Any] = {}
_PROPOSAL_FACTS: ContextVar[dict[str, Any] | None] = ContextVar(
    "nsc_delivery_review_proposal_facts",
    default=None,
)


def _text(value: Any, *, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CodexSupervisorError(
            f"delivery review {field} must be a non-empty string"
        )
    result = value.strip()
    if len(result) > limit:
        raise CodexSupervisorError(
            f"delivery review {field} exceeds the bounded supervisor context"
        )
    return result


def _optional_text(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    result = value.strip()
    return result if len(result) <= limit else result[: limit - 3] + "..."


def proposal_facts_from_result(value: Any) -> dict[str, Any] | None:
    """Return the exact safe inventory needed to author one proposal.

    External artifact paths, validation-manifest paths, file bytes, Issue
    comments, and human-validation text are deliberately omitted.
    """

    if not isinstance(value, Mapping):
        return None
    raw_surfaces = value.get("surface_candidates")
    raw_artifacts = value.get("artifacts")
    raw_gates = value.get("gates")
    if not all(isinstance(item, list) and item for item in (
        raw_surfaces,
        raw_artifacts,
        raw_gates,
    )):
        return None
    if len(raw_surfaces) > 128 or len(raw_artifacts) > 64 or len(raw_gates) > 64:
        raise CodexSupervisorError(
            "delivery review inventory exceeds the bounded supervisor context"
        )

    surfaces: list[dict[str, Any]] = []
    for index, item in enumerate(raw_surfaces):
        if not isinstance(item, Mapping):
            raise CodexSupervisorError(
                f"delivery review surface candidate {index} is invalid"
            )
        path = _text(item.get("path"), field="surface path", limit=500)
        sources = item.get("sources")
        safe_sources = []
        if isinstance(sources, list):
            safe_sources = [
                text
                for text in (
                    _optional_text(source, limit=160) for source in sources[:12]
                )
                if text is not None
            ]
        surfaces.append(
            {
                "path": path,
                "sources": safe_sources,
                "suggested_role": _optional_text(
                    item.get("suggested_role"),
                    limit=240,
                ),
            }
        )
    surface_paths = [item["path"] for item in surfaces]
    if len(surface_paths) != len(set(surface_paths)):
        raise CodexSupervisorError("delivery review surface paths are not unique")

    artifacts: list[dict[str, str | None]] = []
    for index, item in enumerate(raw_artifacts):
        if not isinstance(item, Mapping):
            raise CodexSupervisorError(
                f"delivery review artifact {index} is invalid"
            )
        artifacts.append(
            {
                "id": _text(item.get("id"), field="artifact ID", limit=200),
                "type": _text(
                    item.get("type"),
                    field="artifact type",
                    limit=200,
                ),
                "name": _optional_text(item.get("name"), limit=240),
            }
        )
    artifact_ids = [str(item["id"]) for item in artifacts]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise CodexSupervisorError("delivery review artifact IDs are not unique")

    gates: list[dict[str, str | None]] = []
    for index, item in enumerate(raw_gates):
        if not isinstance(item, Mapping):
            raise CodexSupervisorError(f"delivery review gate {index} is invalid")
        gates.append(
            {
                "gate_id": _text(
                    item.get("gate_id"),
                    field="gate ID",
                    limit=200,
                ),
                "reference": _optional_text(item.get("reference"), limit=500),
                "requirement": _optional_text(
                    item.get("requirement"),
                    limit=1200,
                ),
            }
        )
    gate_ids = [str(item["gate_id"]) for item in gates]
    if len(gate_ids) != len(set(gate_ids)):
        raise CodexSupervisorError("delivery review gate IDs are not unique")

    result: dict[str, Any] = {
        "surface_candidates": surfaces,
        "artifacts": artifacts,
        "gates": gates,
    }
    for key, limit in (
        ("validated_commit", 40),
        ("draft_sha256", 64),
    ):
        text = _optional_text(value.get(key), limit=limit)
        if text is not None:
            result[key] = text
    return result


def proposal_facts_from_history(
    history: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    for item in reversed(history):
        if (
            isinstance(item, Mapping)
            and item.get("action") == "delivery_review_facts"
            and "result" in item
            and "tool_error" not in item
        ):
            return proposal_facts_from_result(item.get("result"))
    return None


def _proposal_instruction(facts: Mapping[str, Any]) -> str:
    inventory = json.dumps(
        facts,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return (
        " Host-verified proposal inventory follows. Use only these exact "
        "surface paths, artifact IDs, and gate IDs; preserve the displayed "
        "gate order. Every gate_mappings[].evidence entry must be an exact "
        "artifact `id` from this inventory. A validation-manifest path, SHA, "
        "test filter, artifact name, or prose description is not an artifact "
        f"ID. HOST_VERIFIED_DELIVERY_REVIEW_FACTS={inventory}"
    )


def _patched_allowed_actions_for(
    observation: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    actions: Mapping[str, str],
) -> tuple[str, ...]:
    coordination = observation.get("coordination")
    state = (
        coordination.get("workflow_state")
        if isinstance(coordination, Mapping)
        else None
    )
    downstream = observation.get("downstream")
    next_action = (
        downstream.get("next_action")
        if isinstance(downstream, Mapping)
        else None
    )
    if (
        isinstance(state, Mapping)
        and state.get("state") == "agent_ready"
        and next_action == "acquire_agent_lease"
        and "acquire_agent_lease" in actions
    ):
        return ("acquire_agent_lease",)
    return _ORIGINALS["allowed_actions_for"](observation, history, actions)


def _patched_summarize_result(value: Any) -> dict[str, Any]:
    summary = _ORIGINALS["summarize_result"](value)
    if not isinstance(value, Mapping):
        return summary

    artifacts = value.get("artifacts")
    if isinstance(artifacts, list):
        ids = [
            item.get("id")
            for item in artifacts
            if isinstance(item, Mapping)
            and isinstance(item.get("id"), str)
            and item.get("id")
        ]
        summary["artifacts_count"] = len(artifacts)
        if ids:
            summary["artifact_ids"] = ids[:16]

    gates = value.get("gates")
    if isinstance(gates, list):
        ids = [
            item.get("gate_id")
            for item in gates
            if isinstance(item, Mapping)
            and isinstance(item.get("gate_id"), str)
            and item.get("gate_id")
        ]
        summary["gates_count"] = len(gates)
        if ids:
            summary["gate_ids"] = ids[:32]

    surfaces = value.get("surface_candidates")
    if isinstance(surfaces, list):
        paths = [
            item.get("path")
            for item in surfaces
            if isinstance(item, Mapping)
            and isinstance(item.get("path"), str)
            and item.get("path")
        ]
        summary["surface_candidates_count"] = len(surfaces)
        if paths:
            summary["surface_paths"] = paths[:16]

    for key in ("validated_commit", "draft_sha256"):
        item = value.get(key)
        if isinstance(item, str) and item:
            summary[key] = item
    return summary


def _patched_render_supervisor_prompt(
    *,
    task_id: str,
    goal_and_rules: str,
    observation: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    actions: Mapping[str, str],
) -> str:
    _PROPOSAL_FACTS.set(None)
    facts = proposal_facts_from_history(history)
    grounded_actions = dict(actions)
    if facts is not None and "create_delivery_review_proposal" in grounded_actions:
        grounded_actions["create_delivery_review_proposal"] += (
            _proposal_instruction(facts)
        )
        _PROPOSAL_FACTS.set(facts)
    try:
        return _ORIGINALS["render_supervisor_prompt"](
            task_id=task_id,
            goal_and_rules=goal_and_rules,
            observation=observation,
            history=history,
            actions=grounded_actions,
        )
    except BaseException:
        _PROPOSAL_FACTS.set(None)
        raise


def _patched_decision_schema(allowed_actions: Sequence[str]) -> dict[str, Any]:
    facts = _PROPOSAL_FACTS.get()
    try:
        schema = _ORIGINALS["decision_schema"](allowed_actions)
        if (
            facts is None
            or "create_delivery_review_proposal" not in set(allowed_actions)
        ):
            return schema

        arguments = schema["properties"]["arguments"]["properties"]
        surface_paths = [
            item["path"] for item in facts["surface_candidates"]
        ]
        artifact_ids = [item["id"] for item in facts["artifacts"]]
        gate_ids = [item["gate_id"] for item in facts["gates"]]
        arguments["selected_surfaces"]["items"]["properties"]["path"][
            "enum"
        ] = surface_paths
        gate_item = arguments["gate_mappings"]["items"]
        gate_item["properties"]["gate_id"]["enum"] = gate_ids
        gate_item["properties"]["evidence"]["items"]["enum"] = artifact_ids
        return schema
    finally:
        # The schema is built synchronously during the provider call. Clearing
        # here prevents one proposal inventory from leaking into a later turn.
        _PROPOSAL_FACTS.set(None)


def install_downstream_action_grounding() -> None:
    """Install exact proposal grounding and lease-first routing once."""

    global _INSTALLED
    if _INSTALLED:
        return

    from . import codex_supervisor
    from . import downstream_determinism
    from . import openai_downstream
    from . import openai_pipeline
    from . import progress

    _ORIGINALS.update(
        {
            "allowed_actions_for": downstream_determinism.allowed_actions_for,
            "summarize_result": progress.summarize_result,
            "render_supervisor_prompt": openai_downstream.render_supervisor_prompt,
            "decision_schema": codex_supervisor.decision_schema,
        }
    )

    downstream_determinism.allowed_actions_for = _patched_allowed_actions_for

    progress.summarize_result = _patched_summarize_result
    downstream_determinism.summarize_result = _patched_summarize_result
    openai_downstream.summarize_result = _patched_summarize_result
    openai_pipeline.summarize_result = _patched_summarize_result

    openai_downstream.render_supervisor_prompt = (
        _patched_render_supervisor_prompt
    )
    codex_supervisor.decision_schema = _patched_decision_schema
    _INSTALLED = True


__all__ = [
    "install_downstream_action_grounding",
    "proposal_facts_from_history",
    "proposal_facts_from_result",
]
