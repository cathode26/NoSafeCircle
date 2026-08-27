"""Deterministic prompts for round-robin decomposition review and revision."""

from __future__ import annotations

import json
from typing import Any, Iterable

from TaskDecomposition.context_builder import ContextPackage
from TaskDecomposition.contracts import DecompositionResult
from TaskDecomposition.review_contracts import ReviewFinding


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )


def graph_delta_review_view(graph_delta: Any | None) -> dict[str, Any] | None:
    if graph_delta is None:
        return None
    payload = graph_delta.to_dict()
    return {
        "graph_delta_schema_version": payload["graph_delta_schema_version"],
        "plan_id": payload["plan_id"],
        "authority": payload["authority"],
        "parent_before_summary": payload["parent_before_summary"],
        "parent_after_summary": payload["parent_after_summary"],
        "allocated_local_key_to_task_id": payload[
            "allocated_local_key_to_task_id"
        ],
        "inbound_dependency_changes": payload["inbound_dependency_changes"],
        "resource_group_changes": payload["resource_group_changes"],
        "proposed_graph_validation": payload["proposed_graph_validation"],
        "proposed_graph_semantic_hash": payload[
            "proposed_graph_semantic_hash"
        ],
    }


def build_decomposition_reviewer_prompt(
    *,
    context: ContextPackage,
    candidate: DecompositionResult,
    candidate_sha256: str,
    candidate_author_provider: str,
    reviewer_provider: str,
    round_number: int,
    graph_delta: Any | None,
    review_history: Iterable[dict[str, Any]],
    unresolved_findings: Iterable[ReviewFinding],
) -> str:
    """Build one exact independent-review prompt for the current candidate."""

    history = list(review_history)
    unresolved = [finding.to_dict() for finding in unresolved_findings]
    finding_prefix = f"round-{round_number:02d}-"
    graph_view = graph_delta_review_view(graph_delta)

    return f"""You are the independent D1B.2 decomposition reviewer for round {round_number}.

The current candidate was most recently authored by provider `{candidate_author_provider}`.
You are running as provider `{reviewer_provider}`. You must independently review the
candidate; do not defer to the previous provider and do not expose private reasoning.

Your output is a structured review. You may do exactly one of the following:

1. `pass`
   - The current candidate is semantically acceptable as-is.
   - Set `revised_decomposition` to null.
   - Introduce no blocking findings.
   - Resolve or withdraw every prior unresolved blocking finding.

2. `revise`
   - The current candidate still has at least one blocking defect.
   - For a NEW defect, emit a new structured finding with this round's finding prefix.
   - For a previously reported defect that remains, mark its prior resolution
     `still_blocking`; do not duplicate it under a new finding ID.
   - Emit a COMPLETE replacement decomposition result in `revised_decomposition`.
   - Never emit a patch, partial child list, prose-only correction, or graph application.
   - The replacement must preserve the exact parent identity and use decomposition schema 1.1.

3. `needs_human`
   - Use this only when approved contracts/canon do not support a safe correction.
   - Set `revised_decomposition` to null.
   - Preserve at least one unresolved blocking finding and explain the authority gap.

Round-robin rules:

- The provider that most recently authored a candidate may not approve that candidate.
- If you revise, you become the new candidate author; another provider must review it.
- Every new finding ID must begin with `{finding_prefix}` and use lowercase kebab-case
  after that prefix, for example `{finding_prefix}duplicate-chapel-validation`.
- `prior_finding_resolutions` must contain exactly one record for every currently
  unresolved blocking finding listed below, and no extras.
- A finding may be `resolved`, `withdrawn`, or `still_blocking`; provide a concrete
  explanation based on the CURRENT candidate.
- Findings are review artifacts only. Do not claim implementation, testing, graph
  application, approval, delivery, conformance, or readiness.

Replacement-candidate invariants when verdict=`revise`:

- Copy the exact current `parent_task` identity; never substitute a byte hash or new revision.
- Use decomposition-result schema `1.1` and return every required top-level field.
- `decision=decomposed` uses `gap_type=execution`, one or more concrete single-agent
  implementation children, complete parent AC/VAL/INT coverage, and exactly one
  `inbound_dependency_rewrites` record for every active direct dependent of the parent.
- A non-decomposed decision contains no children and no inbound dependency rewrites.
- Every parent acceptance criterion, completion gate, and downstream integration
  obligation has exactly one coverage record; every child AC/VAL/INT entry is traced by
  that coverage.
- Every child `local_key` uses stable lowercase kebab-case and is reused exactly in local
  dependencies, coverage targets, and inbound dependency rewrites.
- A child completion gate must be locally completable. A proof that requires later authored
  content belongs in a downstream integration obligation owned by the appropriate later task.
- If separately implemented components require assembly/wiring to become usable, that
  sewing is another explicit child task with dependencies on those components.
- Conversely, do not invent an integration child when another proposed or existing task
  already owns the complete assembly/validation responsibility.
- Set `artifact_proposal` consistently with the selected decision; do not invent design or
  implementation authority absent from the committed context.

Human-facing Unity language review:

- The primary human reader is an experienced Unity game programmer.
- Review child titles, AC/VAL/INT requirements, reasons, notes, and findings for concrete
  Unity wording as well as semantic correctness.
- Treat wording as a blocking candidate-correctness problem when a programmer must translate
  abstract pipeline or design jargon before knowing what Prefab, Component, behavior,
  public method, collision, damage call, or Play Mode/Edit Mode test is required.
- Rewrite materially opaque wording into concrete Unity terms without changing ownership,
  scope, dependency meaning, or observable behavior and without inventing classes, methods,
  files, packages, physics technology, or mechanics not established by the context.
- Prefer `prefab` for a Unity asset and `enemy type` for the design concept instead of using
  `archetype` for both. Prefer `uses/calls/connects` over `consumes`, the named shared system
  over `foundation`, and `public reset method` over `owner-controlled operation`.
- Do not accept slash-compressed wording that hides separate requirements. Target knowledge,
  the decision to fire, line-of-sight checks, projectile collision, and damage must be
  described separately when they are separately required.
- Keep schema taxonomy and identifiers unchanged in machine-facing fields.
- Example: prefer `Ranged Enemy Prefab Setup and Frost Movement Test` over
  `Ranged Enemy Archetype Prefab Assembly and Frost Integration`.

Semantic rubric — inspect all of these explicitly before choosing a verdict:

- duplicate responsibility between proposed children or with existing contracts;
- hidden assembly, wiring, integration, or end-to-end construction work;
- unnecessary integration children when another child already owns final assembly;
- completion gates that require downstream authored content or a task that depends on
  the aggregate being decomposed;
- inbound dependency rewrites mapped to the wrong child capability;
- missing, misleading, or duplicated parent AC/VAL/INT coverage;
- children that are too broad, too narrow, not single-agent bounded, or not locally
  completable;
- ownership conflicts with existing TaskGraph contracts, current canon, or shared
  subsystem boundaries;
- whether completing every proposed child would actually complete the parent feature;
- whether the proposal invents bookkeeping work rather than real implementation work.

The deterministic validators have already checked the current candidate structurally.
Do not treat structural validity as semantic approval.

Reviewed candidate SHA-256 (copy exactly into `reviewed_candidate_sha256`):

{candidate_sha256}

BEGIN IMMUTABLE ORIGINAL CONTEXT
{context.canonical_json()}
END IMMUTABLE ORIGINAL CONTEXT

BEGIN CURRENT DECOMPOSITION CANDIDATE
{_json(candidate.to_dict())}
END CURRENT DECOMPOSITION CANDIDATE

BEGIN CURRENT DETERMINISTIC GRAPH REVIEW VIEW
{_json(graph_view)}
END CURRENT DETERMINISTIC GRAPH REVIEW VIEW

BEGIN PRIOR REVIEW HISTORY
{_json(history)}
END PRIOR REVIEW HISTORY

BEGIN CURRENTLY UNRESOLVED BLOCKING FINDINGS
{_json(unresolved)}
END CURRENTLY UNRESOLVED BLOCKING FINDINGS

Return only the structured object required by the supplied output schema.
"""
