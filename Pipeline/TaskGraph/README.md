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

## Current bootstrap approval check

Run:

```powershell
python Pipeline/TaskGraph/approve_verified_bootstrap.py
```

This performs deterministic checks only and writes nothing.

For the current bootstrap it must prove, among other invariants:

- the current candidate comes from immutable run history;
- reconciliation and verification run IDs agree across the pointer and verification summary;
- the verification status is approvable;
- final material findings are exactly zero;
- human approval is still required;
- neither verification nor the proposed graph delta mutated the persistent graph;
- the delta is a `bootstrap_seed_proposal` and reports that no persistent graph exists;
- the delta contains seed records.

After reviewing the printed identities and SHA-256 hashes, explicitly record approval with:

```powershell
python Pipeline/TaskGraph/approve_verified_bootstrap.py --approve --approved-by Vincent
```

This creates:

```text
Pipeline/TaskGraph/APPROVED_BOOTSTRAP.json
```

The approval manifest is intentionally write-once. The approval tool refuses to overwrite an existing manifest.

## Next

The deterministic Work Graph Seeder consumes only the immutable artifacts named and hashed by `APPROVED_BOOTSTRAP.json`. It will preserve stable `reconciliation_key` traceability while assigning persistent `NSC-*` IDs and creating the first `Tasks/*.yaml` graph.
