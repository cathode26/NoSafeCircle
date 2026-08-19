# Progressive Decomposition Pipeline Update

Prepared: 2026-08-18

This package contains proposed replacements for:

- `Docs/AI-Pipeline/START_HERE.md`
- `Docs/AI-Pipeline/CURRENT_STATE.md`
- `Docs/AI-Pipeline/00_MASTER_CONTEXT.md`
- `Docs/AI-Pipeline/DECISIONS.md`
- `Docs/AI-Pipeline/01_MILESTONE_TASK_GRAPH.md`
- `Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md`

## Architectural changes

1. Added progressive, just-in-time task decomposition.
2. Added three work kinds: `feature`, `artifact`, and `implementation`.
3. Kept Milestone 1 deterministic and LLM-free.
4. Moved the Progressive Decomposer into Milestone 2.
5. Added the Artifact Authority Gate before any AI-generated design/content.
6. Added approved artifacts as subordinate, trusted design state under the GDD.
7. Positioned Assignment 7 as a scored Style Evaluator inside Artifact GER.
8. Explicitly separated:
   - deciding that design is missing;
   - authorizing creation of new design;
   - generating it;
   - evaluating its quality;
   - using approved output to decompose implementation work.
9. Added ADR-021 through ADR-024.
10. Preserved Assignment 6 GER as the bounded repair mechanism for both implementation and generated artifacts.

## Important boundary

Milestone 1 does NOT implement Claude-powered decomposition.

Milestone 1 only establishes a truthful persistent work graph.

Milestone 2 introduces RAG/scanner context, progressive decomposition, artifact authority, and artifact generation/evaluation.


---


# Reconciliation Agent — Proposed Files

This package adds a new production-oriented bootstrap agent without modifying Assignment 5.

## Files

- `Pipeline/Reconciliation/reconciliation_agent.py`
- `Pipeline/Reconciliation/prompts/reconcile.md`
- `Pipeline/Reconciliation/README.md`

## Runtime outputs

The agent creates:

- `Pipeline/Reconciliation/outputs/reconciliation.json`
- `Pipeline/Reconciliation/outputs/RECONCILIATION.md`

## Design decisions implemented

- Claude is read-only (`Read,Glob,Grep`).
- Current GDD + current checkout are primary truth.
- Assignment 6 / Assignment 5 outputs are optional historical evidence only.
- The agent creates a coarse hierarchy, not a full backlog.
- `parent_key` and `depends_on` are separate.
- Dependencies cannot target feature nodes.
- Missing design becomes `needs_future_decomposition`; the agent does not invent design or propose artifacts.
- `complete` is conservative and evidence-backed.
- Python validates hierarchy, dependency cycles, evidence, statuses, and repository boundaries.
- Python renders the structured result into a human-reviewable Markdown reconciliation table.
- No `Tasks/*.yaml` are created yet; that happens only after human review.

## Run

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/reconciliation_agent.py
```

---

# Immutable Reconciliation Snapshot Update

## Why

The Reconciliation Agent is reusable, not a one-time bootstrap script.
Therefore its output must not become a mutable project database.

This update separates:

- design truth: GDD;
- implementation truth: current repository;
- operational work truth: `Tasks/*.yaml`;
- reconciliation evidence: immutable point-in-time snapshots.

## Code changes

`Pipeline/Reconciliation/reconciliation_agent.py`

- creates a unique append-only directory for every run;
- preserves raw and validated output per run;
- never overwrites an earlier snapshot;
- writes `PROPOSED_GRAPH_DELTA.json` and `.md`;
- does not mutate `Tasks/*.yaml`;
- emits bootstrap seed proposals before the task graph exists;
- emits `taskctl_diff_required` after a persistent task graph exists;
- updates only `outputs/LATEST.json` as a mutable convenience pointer;
- preserves a failed run directory for inspection.

## Output layout

```text
Pipeline/Reconciliation/outputs/
├── LATEST.json
└── runs/
    └── <timestamp>-<run-id>/
        ├── reconciliation.raw.json
        ├── reconciliation.json
        ├── RECONCILIATION.md
        ├── PROPOSED_GRAPH_DELTA.json
        └── PROPOSED_GRAPH_DELTA.md
```

## Architecture changes

- Added ADR-025: reconciliation results are immutable snapshots.
- Added ADR-026: reconciliation proposes graph deltas and never directly
  mutates the persistent graph.
- Added `reconciliation_key` traceability to the Milestone 1 task schema.
- Clarified that safe cascades such as dependency completion changing
  `taskctl ready` are deterministic graph behavior.
- Clarified that full reconciliation reruns must not cause uncontrolled LLM
  rewrites of task files.

## Still intentionally deferred

Milestone 1 still needs to implement the deterministic task graph, seeder, and
reconciliation diff/apply behavior. The Reconciliation Agent now emits the
correct boundary and proposed-delta artifacts but does not invent that
unfinished `taskctl` functionality inside the LLM agent.
