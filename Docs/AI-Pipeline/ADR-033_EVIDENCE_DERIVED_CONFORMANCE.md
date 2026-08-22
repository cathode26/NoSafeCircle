# ADR-033: Evidence-Derived Current Conformance

- Status: Accepted
- Date: 2026-08-22
- Scope: Architecture Correction Phase 3A

## Context

Schema-v2 task contracts define approved work but deliberately contain no operational completion truth. A historical delivery can cease to conform when its contract, governing GDD, implementation surfaces, or evidence artifacts change. Working-copy files also cannot be repository authority because they are neither immutable nor integrated.

## Decision

Introduce minimal immutable delivery, baseline, and revalidation records under `Pipeline/TaskGraph/evidence/<TASK-ID>/`. Evaluate current conformance exclusively from committed `HEAD` and referenced Git objects. A baseline establishes first trustworthy evidence for an implementation that predates the evidence system without claiming its original authorship or delivery date.

Each record binds an exact semantic task-contract hash and revision, normalized canonical-GDD hash, validated commit/tree, conformance-surface blob set, exact completion-gate result set, committed evidence-artifact blobs, and any required human approval. Delivery records bind the validated state to the integrated state. Baseline records identify the actual integrated state tested without inventing delivery commits and can establish conformance exactly as delivery records can. Revalidation records form an acyclic, same-task ancestry chain from a delivery, baseline, or prior revalidation record.

Current conformance is derived, never written. A later unrelated commit preserves conformance when all bound surfaces and canon remain unchanged. Contract changes require replanning; canon or tracked-surface changes require revalidation. Invalid or contradictory evidence fails closed.

When several records remain valid, Git commit ancestry selects a unique strict descendant. Incomparable maximal records are ambiguous. `recorded_at` is audit metadata and never selection authority.

## Consequences

- Evaluation is repeatable for a given committed `HEAD` and does not depend on working-copy formatting or timestamps.
- Evidence is auditable through native Git commits, trees, and blobs.
- Record creation remains manual in Phase 3A; no production evidence record, including for NSC-023, is introduced.
- Evidence-derived current-state inspection exists, but production delivery/baseline/revalidation evidence has not yet been proven on a real task.
- Dependency-readiness and dispatch authorization policy remain outside this decision and are not enabled. Readiness is not derived, authorization remains denied, and zero tasks may be autonomously dispatched.
- State inspection alone, including a `conformant` result, never authorizes execution.
- Claiming, attempts, and supervision remain outside this decision and stay disabled.
- GDDRAG and its index are unchanged; the evaluator reads the canonical GDD directly from Git.
