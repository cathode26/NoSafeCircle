# No Safe Circle — Reconciliation Agent

## Purpose

The Reconciliation Agent is the occasional/global successor to the analysis side of Assignment 5.

Its job is to answer:

> What does No Safe Circle require, what is actually integrated today, and what coarse work graph should Milestone 1 seed?

It does **not**:

- choose the next goal;
- implement code;
- create missing game design;
- create `Tasks/*.yaml`;
- run continuously.

The output is a human-reviewable reconciliation artifact. After approval, a deterministic Work Graph Seeder can turn the approved records into `Tasks/*.yaml`.

## Architecture

```text
Current GDD
   +
Current main checkout
   +
Optional historical evidence
        ↓
Reconciliation Agent (Claude, read-only)
        ↓
Structured reconciliation.json
        ↓
Deterministic semantic validation
        ↓
RECONCILIATION.md
        ↓
Human review
        ↓
Later: deterministic Work Graph Seeder
        ↓
Tasks/*.yaml
```

## Why this is separate from the Progressive Decomposer

The Reconciliation Agent is **global and occasional**. It bootstraps or refreshes the coarse persistent work graph.

The Progressive Decomposer is **local and just-in-time**. It expands one near-frontier feature after Milestone 1 exists.

If reconciliation discovers that a high-level feature lacks enough design to decompose safely, it records:

`decomposition_state: needs_future_decomposition`

It does **not** invent the missing design and does **not** create an artifact proposal. Artifact proposals belong to the Progressive Decomposer in Milestone 2.

## Read-only boundaries

Claude is limited to `Read`, `Glob`, and `Grep`.

Primary truth:

- `Docs/GDD/No_Safe_Circle_GDD.md`
- `Assets/`
- `ProjectSettings/` when relevant

Optional historical evidence:

- `Assignment6GER/README_Assignment6.md`
- `GoalOrientedAgent/outputs/goal_analysis.json`
- `GoalOrientedAgent/outputs/next_goal_selection.json`

Historical files may help locate prior work or validation history, but they never override the current GDD or current checkout.

## Outputs

Running the agent creates:

```text
Pipeline/Reconciliation/outputs/reconciliation.json
Pipeline/Reconciliation/outputs/RECONCILIATION.md
```

`reconciliation.json` is the machine-readable artifact.

`RECONCILIATION.md` is the human review table plus detailed evidence.

## Run

From the repository root:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/reconciliation_agent.py
```

The command is intentionally one line.

## Environment variables

Optional:

```text
RECONCILIATION_MODEL=sonnet
RECONCILIATION_TIMEOUT_SECONDS=1800
RECONCILIATION_MAX_TURNS=50
```

## What the agent records

Each proposed work item contains:

- a stable reconciliation `key`;
- title;
- `kind`: `feature`, `artifact`, or `implementation`;
- parent hierarchy;
- requirement basis;
- GDD evidence;
- current repository state;
- proposed durable graph status (`open` / `complete`);
- repository evidence;
- real `depends_on` relationships;
- decomposition state;
- confidence;
- notes.

`parent_key` means **belongs under**.

`depends_on` means **cannot be executed until**.

They are deliberately separate.

## Important rules

### Complete means evidence exists now

A work item is not `complete` because an old assignment says it was completed.

Current integrated project evidence must support the claim.

Historical evidence can strengthen validation history only when the current implementation is also present.

### Capability-to-create is not current state

Builder/editor/setup code that *could* create a scene object is not proof that object is serialized in the project.

### Missing design is not permission to invent

If the GDD names a high-level feature but lacks enough detail for safe low-level decomposition, keep the feature coarse and mark it for future progressive decomposition.

Do not manufacture room designs, encounters, factions, lore, enemies, spells, or other requirements during reconciliation.

### Keep the graph coarse

This pass is not supposed to create the entire capstone backlog.

It should establish the truthful major hierarchy, known concrete implementation work, real dependencies, and places where future progressive decomposition is required.

## Human review checklist

Before using the output to seed `Tasks/*.yaml`, verify:

1. Required GDD scope is represented.
2. Stretch/excluded scope was not accidentally seeded.
3. `complete` claims are supported by current `main`.
4. Parent hierarchy is sensible.
5. Dependencies are actual prerequisites, not conceptual relationships.
6. Coarse features were not prematurely exploded into speculative microtasks.
7. Missing design was not silently invented.
8. Low-confidence or unresolved items are understood.

## Next step after approval

Build the deterministic Work Graph Seeder / `taskctl` Milestone 1 implementation.

The Reconciliation Agent is intentionally not the system that writes the final task graph.
