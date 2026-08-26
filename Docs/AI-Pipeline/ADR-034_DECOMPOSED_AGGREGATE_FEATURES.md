# ADR-034 — Decomposed Contracts Become Aggregate Features

## Status

Accepted for the decomposition pipeline implementation on `pipeline/decomposition-aggregate-semantics`.

## Problem

A contract selected for execution decomposition begins life as executable implementation work, but after decomposition it represents a capability that is implemented by several smaller contracts. Treating the original contract as if it remained an executable task creates hidden work and ambiguous dependencies:

- agents may try to implement the parent again after its children finish;
- a final assembly/wiring pass can be implied without having its own task;
- downstream contracts may continue to depend on a non-executable parent instead of the concrete capability they consume;
- graph validation can remain acyclic while the actual completion order is impossible;
- parent completion can require ad hoc evidence even though all implementation work was delegated.

## Decision

A successful `decomposed` result is a structural transition from an executable contract to a non-executable aggregate feature.

For newly applied decompositions, the parent must have:

```text
kind: feature
execution_scope: not_applicable
decomposition_state: decomposed
exclusive_resources: []
decomposition_children: [<all active direct child task IDs>]
```

`decomposition_children` is the machine-readable completion set for the aggregate. It must exactly name every active direct child under that aggregate, including active children that existed before the current decomposition plus children introduced by the current graph delta.

The parent keeps its NSC identity, hierarchy position, approved requirements, GDD traceability, and provenance. It is no longer implementation work and must not be selected, dispatched, delivered, or tested as a separate implementation task.

## No hidden implementation or integration work

All work required to satisfy the parent must exist in executable descendants.

If component tasks do not themselves produce the finished capability and a later agent must assemble, wire, integrate, or perform an end-to-end construction step, that work is another explicit implementation child with dependencies on the component children.

For example, if three component tasks require a final sewing pass, the valid shape is:

```text
Aggregate Feature
├── component A
├── component B
├── component C
└── integration task
    ├── depends_on A
    ├── depends_on B
    └── depends_on C
```

There is never a hidden "finish the parent" pass after the children. If an existing proposed child already owns the final assembly/integration responsibility, an additional child is unnecessary; the invariant is that no required sewing work is implicit.

## Derived aggregate completion

The aggregate's conformance is derived from its explicit child set:

```text
aggregate conformant
    iff
all decomposition_children are conformant
```

No separate parent delivery record or implementation pass is required. If any delegated child is incomplete, stale, needs human review, or otherwise non-conformant, the aggregate remains an aggregate/incomplete feature.

## Downstream dependency rewrites

An active executable contract may not depend on a decomposed aggregate feature.

When decomposition is proposed, every active direct dependent whose `depends_on` currently names the parent must be accounted for by an explicit inbound dependency rewrite. The rewrite identifies the proposed child local key or keys whose concrete capability the dependent actually consumes.

Graph-delta planning must:

1. discover the exact active direct dependents of the selected parent;
2. require the decomposition result to contain exactly one rewrite for each dependent and no extras;
3. replace the parent dependency with the allocated child task ID or IDs;
4. increment the rewritten dependent's contract revision;
5. reject duplicate, missing, unknown, or stale rewrites;
6. validate the complete proposed graph after all rewrites.

The decomposer must not mechanically choose the numerically last child. A downstream consumer should depend on the child capability it actually needs. When the approved contracts and canon do not establish a safe mapping, the decomposer must return `needs_human` rather than guess.

## Decomposition result schema

New provider-backed decomposition uses result schema `1.1`, which adds required review-only `inbound_dependency_rewrites` records. Schema `1.0` remains readable for immutable historical run artifacts, but new graph deltas use the stricter `1.1` semantics.

A rewrite has this shape:

```json
{
  "dependent_task_id": "NSC-046",
  "replacement_local_keys": ["ranged-archetype-integration"],
  "reason": "The Chapel validation consumes the finished ranged archetype capability."
}
```

These local keys are proposal identities, not preallocated NSC IDs. Deterministic graph-delta planning resolves them after allocating child IDs.

## Resource ownership

The aggregate parent holds no executable exclusive-resource locks. Resource ownership remains on the concrete child contracts that actually write or own those surfaces. Resource groups are recomputed against the proposed overlay after the parent transition and child creation.

## Validation

New graph deltas are valid only when both the normal TaskGraph validator and the decomposition aggregate semantic validator pass. The strict validator requires:

- an explicit non-empty `decomposition_children` set;
- `kind: feature`;
- `execution_scope: not_applicable`;
- `decomposition_state: decomposed`;
- no aggregate exclusive-resource locks;
- every named child exists, is active, and is a direct child;
- the child set exactly matches all active direct children;
- no active contract depends on the aggregate parent.

## Compatibility

Historical reviewed decompositions predate `decomposition_children`. They remain readable and are not silently rewritten by this change. The strict aggregate semantics opt in when `decomposition_children` exists. Historical aggregates can be migrated deliberately in a separate reviewed change.

## Authority boundary

This ADR changes D1A/D1B.1 proposal and TaskGraph semantic validation. It does not implement D1C persistent graph application. `graph_delta.json` remains `review_only_not_applied`; a human/reviewed application step is still required before proposed contracts or dependency rewrites become repository authority.
