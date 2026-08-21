# Milestone 1 Task Graph Bootstrap

This directory contains deterministic tooling for turning one human-approved, independently verified reconciliation snapshot into the initial persistent `Tasks/*.yaml` work graph.

## Safety boundary

Reconciliation and verification never mutate `Tasks/*.yaml`.

Bootstrap proceeds through these stages:

1. Reconciliation creates an immutable candidate and proposed bootstrap graph delta.
2. Independent verification refines/re-verifies the candidate until material findings are zero or the run is rejected.
3. A human explicitly approves one exact verified candidate/delta pair.
4. The deterministic Work Graph Seeder checks the approval manifest and creates the initial persistent graph.
5. Later reconciliation runs propose diffs; they never directly rewrite the graph.

The approval record binds the immutable candidate, graph delta, and verification summary by SHA-256 so a mutable `outputs/current/` pointer cannot silently change what was approved.

## Bootstrap approval check

Run:

```powershell
python Pipeline/TaskGraph/approve_verified_bootstrap.py
```

This performs deterministic checks only and writes nothing.

After reviewing the printed identities and SHA-256 hashes, explicitly record approval with:

```powershell
python Pipeline/TaskGraph/approve_verified_bootstrap.py --approve --approved-by Vincent
```

This creates the intentionally write-once:

```text
Pipeline/TaskGraph/APPROVED_BOOTSTRAP.json
```

## Stage 1 — Approval + immutable input loader

Run:

```powershell
python Pipeline/TaskGraph/bootstrap_inputs_smoke_test.py
python Pipeline/TaskGraph/bootstrap_inputs.py
```

`bootstrap_inputs.py` never reads `outputs/current/` after approval. It loads only the immutable artifacts named by `APPROVED_BOOTSTRAP.json`, recomputes all bound SHA-256 values, checks reconciliation/verification identity and zero final material findings, and confirms every proposed seed key exists in the approved candidate.

## Stage 2 — Stable IDs + in-memory task transform

Run:

```powershell
python Pipeline/TaskGraph/work_graph_transform_smoke_test.py
python Pipeline/TaskGraph/work_graph_transform.py
```

To inspect the complete initial ID allocation:

```powershell
python Pipeline/TaskGraph/work_graph_transform.py --show-id-map
```

This stage still writes nothing under `Tasks/`.

The initial stable IDs are allocated in the exact order of the human-approved `proposed_seed_records` list. Because the approved graph delta itself is SHA-256 bound, the initial allocation is reproducible. Once written by the later seed writer, that `reconciliation_key -> NSC-*` mapping becomes durable state and is never regenerated from a later reconciliation.

The transformer mechanically:

- cross-checks operational identity/topology between the approved delta and approved candidate;
- treats `no-safe-circle` as the project-root sentinel rather than inventing a task for it;
- converts parent/dependency reconciliation keys into stable `NSC-*` IDs;
- keeps exclusive-resource locks separate from dependency edges;
- preserves acceptance criteria, validation requirements, execution/decomposition metadata, provenance, and useful bootstrap repository evidence;
- carries non-code project requirements separately from executable work;
- rejects missing parents/dependencies, self-dependencies, unknown resource-group members, or delta/candidate disagreement instead of guessing.

## Next

Stage 3 adds deterministic graph validation and a dry-run report over the in-memory plan. Only after that passes will the atomic seed writer be allowed to create `Tasks/*.yaml` and the durable ID map.
