# ADR-033: Evidence-Derived Current Conformance

- Status: Accepted, amended 2026-08-25
- Date: 2026-08-22
- Scope: Architecture Correction Phase 3A

## Context

Schema-v2 task contracts define approved work but deliberately contain no operational completion truth. A historical delivery can cease to conform when its task contract or implementation conformance surfaces change, when required evidence artifacts are altered, or when other record invariants cease to hold. Working-copy files also cannot be repository authority because they are neither immutable nor integrated.

The original Phase 3A design also treated any byte-level change to the entire canonical GDD as a reason to revalidate every previously delivered task. Production use exposed that boundary as too coarse: adding an approved five-room spatial-layout blockout changed the whole-GDD hash and caused every previously evidenced implementation task to report a stale-current-proof state, including tasks whose requirements and implementation surfaces were untouched.

Schema-v2 task contracts already carry the task-relevant approved requirements and GDD evidence used to define each bounded task. Reconciliation and reviewed graph changes are the mechanism for translating a materially relevant canon change into a revised task contract.

## Decision

Introduce minimal immutable delivery, baseline, and revalidation records under `Pipeline/TaskGraph/evidence/<TASK-ID>/`. Evaluate current conformance exclusively from committed `HEAD` and referenced Git objects. A baseline establishes first trustworthy evidence for an implementation that predates the evidence system without claiming its original authorship or delivery date.

Each record binds an exact semantic task-contract hash and revision, normalized canonical-GDD hash, validated commit/tree, conformance-surface blob set, exact completion-gate result set, committed evidence-artifact blobs, and any required human approval. Delivery records bind the validated state to the integrated state. Baseline records identify the actual integrated state tested without inventing delivery commits and can establish conformance exactly as delivery records can. Revalidation records form an acyclic, same-task ancestry chain from a delivery, baseline, or prior revalidation record.

The canonical-GDD hash in a conformance record is **historical audit provenance**. The evaluator verifies that the recorded hash truthfully matches the canonical GDD at the record's validated commit. It does **not** require the current whole-GDD hash at `HEAD` to remain byte-identical to that historical hash.

Task-relevant canon for current conformance is represented by the current schema-v2 task contract. If a later GDD change materially changes a task's governing requirements, reconciliation/human review must revise that task contract. The evaluator then derives `needs_replan` from the changed contract revision or semantic hash. A GDD edit that does not change the task contract, tracked conformance surfaces, gates, evidence artifacts, or other record invariants does not by itself invalidate the task.

Current conformance is derived, never written. A later unrelated commit preserves conformance when the task contract and bound implementation/evidence surfaces remain unchanged. Contract changes require replanning. If tracked conformance surfaces or record lineage change after prior evidence, the derived state is `needs_testing`: the task was previously completed/evidenced, but current behavior may need testing again before current conformance can be claimed. Invalid or contradictory evidence fails closed.

When several records remain valid, Git commit ancestry selects a unique strict descendant. Incomparable maximal records are ambiguous. `recorded_at` is audit metadata and never selection authority.

## Current invalidation semantics

- **Unrelated GDD edit, unchanged task contract and surfaces:** remains `conformant`.
- **Task-relevant canon change reflected in a task-contract revision/hash change:** `needs_replan`.
- **Tracked implementation/conformance-surface or validated-lineage change:** `needs_testing`.
- **Historical record's GDD hash does not match the GDD at its validated commit:** `invalid_evidence`.
- **Evidence artifact altered or missing:** `invalid_evidence`.

`needs_testing` is deliberately phrased as an action-oriented current-proof state. It does not mean the task was never delivered or that the implementation is known to be broken. It means prior evidence exists, but later changes prevent TaskGraph from claiming that the current `HEAD` is still proven without another testing/revalidation pass.

This keeps the full-GDD identity in the immutable audit record without using global document churn as a project-wide invalidation trigger.

## Consequences

- Evaluation is repeatable for a given committed `HEAD` and does not depend on working-copy formatting or timestamps.
- Evidence is auditable through native Git commits, trees, and blobs.
- Unrelated additions or edits elsewhere in the GDD no longer generate mass testing work for already-delivered tasks.
- Relevant design changes still cannot silently preserve completion: they must flow through reconciliation/review into the bounded task contract, which causes `needs_replan`.
- Historical delivery records remain unchanged; no evidence migration or rewriting is required.
- The evaluator continues to verify each record's historical GDD hash against its validated commit, so the audit provenance remains fail-closed.
- `needs_testing` should not be selected as fresh implementation work merely because it is not currently `conformant`; normal new-work discovery uses `not_delivered`.
- Dependency-readiness and dispatch authorization policy remain outside this decision and are not enabled. Readiness is not derived, authorization remains denied, and zero tasks are autonomously dispatched by conformance inspection alone.
- State inspection alone, including a `conformant` result, never authorizes execution.
- GDDRAG and its index are unchanged.
